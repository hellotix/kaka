"""物品分类业务层：后台维护三级分类树，C端只读。

层级与路径的维护
----------------
``level`` 与 ``path`` 都是写入时计算的冗余字段：

- 一级分类：``level=1``，``path="/{自身id}"``
- N 级分类：``level=父级+1``，``path=父级path + "/{自身id}"``

因为 path 含自身 ID，必须先 INSERT 拿到 ID 再 UPDATE 一次 path。
这两步在同一个请求事务里（``db_getter`` 的 ``session.begin()``），不会留下半成品。

不提供「移动分类」
------------------
移动会改变整棵子树的 level/path，而物品档案还挂在旧分类上，级联刷新的复杂度和
出错代价都远高于收益。需要调整层级时：新建目标分类 → 停用旧分类。

隐藏分类的语义
--------------
``is_visible=False`` 会让该分类**及其整棵子树**从 C端选择器消失
（组树时遇到不可见节点直接不展开子级）。这样 C端永远不会看到
「父级看不见但子级冒出来」的悬空节点。已挂在隐藏分类上的物品数据不受影响。
"""

from collections.abc import Sequence

from redis.asyncio.client import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_schema import AuthSchema, BatchSetAvailable, PageResultSchema
from app.core.logger import logger
from app.utils.common_util import search_to_dict

from ...exceptions import BusinessError
from ..attr.crud import ErpAttrTemplateCRUD
from ..core.constants import CATEGORY_MAX_LEVEL
from .crud import ErpCategoryCRUD
from .model import ErpCategoryModel
from .schema import (
    ErpCategoryCreateSchema,
    ErpCategoryOutSchema,
    ErpCategoryQueryParam,
    ErpCategoryTreeSchema,
    ErpCategoryUpdateSchema,
)


class ErpCategoryService:
    """分类服务层（后台管理 + C端只读共用）"""

    def __init__(self, auth: AuthSchema, db: AsyncSession, redis: Redis | None = None) -> None:
        """初始化。

        参数:
        - auth (AuthSchema): 认证信息。后台接口传 ``AuthPermission`` 注入的 auth；
          C端只读接口传 ``AuthSchema()``。
        - db (AsyncSession): 数据库会话。
        - redis (Redis | None): Redis 连接，暂未使用，保留以对齐其他 service 的构造签名。
        """
        self.auth = auth
        self.db = db
        self.redis = redis
        self.categories = ErpCategoryCRUD(auth, db)
        self.attrs = ErpAttrTemplateCRUD(auth, db)

    # ── 查询 ──────────────────────────────────────────────────────────

    async def page(
        self,
        page_no: int,
        page_size: int,
        search: ErpCategoryQueryParam | None = None,
        order_by: list[dict[str, str]] | None = None,
    ) -> PageResultSchema[ErpCategoryOutSchema]:
        """后台分页查询分类（平铺，配合树形表格组件自行组装）。"""
        offset = (page_no - 1) * page_size
        result = await self.categories.page(
            offset=offset,
            limit=page_size,
            order_by=order_by or [{"level": "asc"}, {"sort": "asc"}, {"id": "asc"}],
            search=search_to_dict(search, {}),
            out_schema=ErpCategoryOutSchema,
        )
        await self._fill_parent_names(result.items)
        return result

    async def detail(self, id: int) -> ErpCategoryOutSchema:
        """获取分类详情。"""
        obj = await self._get_or_raise(id)
        out = ErpCategoryOutSchema.model_validate(obj)
        if obj.parent_id:
            parent = await self.categories.get(id=obj.parent_id)
            out.parent_name = parent.name if parent else None
        return out

    async def tree(self, *, client_view: bool = False) -> list[ErpCategoryTreeSchema]:
        """构建分类树。

        参数:
        - client_view (bool): True 表示 C端视角 —— 只保留「启用 + 可见」的节点，
          且不可见节点的整棵子树都不展开；False 为后台视角，返回全量。

        返回:
        - list[ErpCategoryTreeSchema]: 一级分类列表，子级嵌在 children 里。
        """
        rows = await self.categories.list_all(only_enabled=client_view, only_visible=client_view)
        return self._build_tree(rows, client_view=client_view)

    async def list_by_ids(self, ids: Sequence[int]) -> dict[int, ErpCategoryModel]:
        """批量取分类对象，返回 {id: model}（物品列表回显分类名用）。"""
        if not ids:
            return {}
        rows = await self.categories.get_list(search={"id": ("in", list(set(ids)))})
        return {row.id: row for row in rows}

    async def ancestor_ids(self, category_id: int) -> list[int]:
        """返回某分类的祖先ID链（从一级到自身），用于收集继承而来的属性模板。

        直接解析物化路径 ``/1/5/12``，不需要逐级查库。路径异常时回退为只含自身，
        保证属性收集不会因为一条脏数据而整个失败。
        """
        obj = await self.categories.get(id=category_id)
        if not obj:
            raise BusinessError(msg="分类不存在", status_code=404)
        parts = [int(part) for part in (obj.path or "").split("/") if part.isdigit()]
        return parts or [category_id]

    # ── 写入（后台）──────────────────────────────────────────────────

    async def create(self, data: ErpCategoryCreateSchema) -> ErpCategoryOutSchema:
        """新增分类。层级由父分类推导，超过三级直接拒绝。"""
        parent: ErpCategoryModel | None = None
        level = 1
        if data.parent_id:
            parent = await self.categories.get(id=data.parent_id)
            if not parent:
                raise BusinessError(msg="父分类不存在", status_code=404)
            level = (parent.level or 1) + 1
            if level > CATEGORY_MAX_LEVEL:
                raise BusinessError(msg=f"分类最多支持 {CATEGORY_MAX_LEVEL} 级，无法在该父分类下继续新增")

        await self._ensure_name_unique(name=data.name.strip(), parent_id=data.parent_id)

        payload = data.model_dump(exclude_none=True)
        payload["level"] = level
        # path 含自身ID，先占位空串，拿到ID后立刻回填（同一事务内完成）
        payload["path"] = ""
        obj = await self.categories.create(data=payload)

        path = f"{parent.path}/{obj.id}" if parent else f"/{obj.id}"
        await self.categories.set(ids=[obj.id], path=path)
        obj = await self.categories.get(id=obj.id) or obj
        logger.info(f"新增分类: id={obj.id}, name={obj.name}, level={level}, operator={self._operator()}")
        return ErpCategoryOutSchema.model_validate(obj)

    async def update(self, id: int, data: ErpCategoryUpdateSchema) -> ErpCategoryOutSchema:
        """修改分类（不支持改父级，理由见模块 docstring）。"""
        obj = await self._get_or_raise(id)
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        if not changes:
            raise BusinessError(msg="没有需要修改的内容")
        if "name" in changes and changes["name"] != obj.name:
            await self._ensure_name_unique(name=str(changes["name"]).strip(), parent_id=obj.parent_id, exclude_id=id)

        # 停用一级/二级分类会让整棵子树在 C端不可选，这里只做提示不阻断：
        # 运营可能就是需要「先停用父级、逐个整理子级」的操作顺序。
        updated = await self.categories.update(id=id, data=data)
        logger.info(f"修改分类: id={id}, changes={changes}, operator={self._operator()}")
        return ErpCategoryOutSchema.model_validate(updated)

    async def delete(self, ids: list[int]) -> None:
        """删除分类（软删除）。

        两道前置校验：
        1. 有子分类时拒绝 —— 否则子分类会变成 parent_id 指向已删记录的孤儿，
           组树时永远挂不上去，界面上表现为「分类凭空消失但数据还在」。
        2. 有属性模板挂在该分类上时拒绝 —— 模板定义着历史物品 attrs JSON 的含义，
           随分类一起消失会让那些数据无法解释。请先停用或迁移模板。
        """
        if not ids:
            raise BusinessError(msg="删除失败，删除对象不能为空")
        objs = await self.categories.get_list(search={"id": ("in", ids)})
        found = {obj.id: obj for obj in objs}
        for id_ in ids:
            if id_ not in found:
                raise BusinessError(msg="删除失败，部分分类不存在", status_code=404)

        for id_ in ids:
            children = await self.categories.count_children(id_)
            if children:
                raise BusinessError(msg=f"分类「{found[id_].name}」下还有 {children} 个子分类，请先处理子分类")
            templates = await self.attrs.count(category_id=id_)
            if templates:
                raise BusinessError(msg=f"分类「{found[id_].name}」上还挂着 {templates} 个扩展属性模板，请先停用或迁移")

        await self.categories.delete(ids=ids)
        logger.warning(f"删除分类: ids={ids}, operator={self._operator()}")

    async def set_available(self, data: BatchSetAvailable) -> None:
        """批量启用/停用分类。"""
        if not data.ids:
            raise BusinessError(msg="操作失败，对象不能为空")
        await self.categories.set(ids=data.ids, status=data.status)
        logger.info(f"批量修改分类状态: ids={data.ids}, status={data.status}, operator={self._operator()}")

    # ── 内部方法 ──────────────────────────────────────────────────────

    async def _get_or_raise(self, id: int) -> ErpCategoryModel:
        """取分类，不存在则抛业务异常。"""
        obj = await self.categories.get(id=id)
        if not obj:
            raise BusinessError(msg="该分类不存在", status_code=404)
        return obj

    async def _ensure_name_unique(self, *, name: str, parent_id: int | None, exclude_id: int | None = None) -> None:
        """校验同级下分类名不重复。"""
        if not name:
            raise BusinessError(msg="分类名称不能为空")
        exists = await self.categories.get_by_parent_and_name(parent_id, name)
        if exists and exists.id != exclude_id:
            raise BusinessError(msg=f"同级下已存在名为「{name}」的分类", status_code=409)

    def _build_tree(self, rows: Sequence[ErpCategoryModel], *, client_view: bool) -> list[ErpCategoryTreeSchema]:
        """把平铺的分类列表组装成树。

        一次遍历建索引、一次遍历挂父子，O(n)。父节点缺失（被删或被过滤掉）的节点
        直接丢弃：C端视角下这正是「隐藏父级连带隐藏子级」的实现方式。
        """
        nodes: dict[int, ErpCategoryTreeSchema] = {}
        for row in rows:
            nodes[row.id] = ErpCategoryTreeSchema(
                id=row.id,
                name=row.name,
                parent_id=row.parent_id,
                level=row.level,
                sort=row.sort,
                icon=row.icon,
                is_visible=row.is_visible,
                status=row.status,
            )

        roots: list[ErpCategoryTreeSchema] = []
        for row in rows:
            node = nodes[row.id]
            parent = nodes.get(row.parent_id) if row.parent_id else None
            if parent is not None:
                parent.children.append(node)
            elif not row.parent_id:
                roots.append(node)
            elif not client_view:
                # 后台视角保留孤儿节点（父级已删但数据还在），便于运营发现脏数据；
                # C端视角丢弃，避免渲染出没有父级的悬空分类。
                roots.append(node)

        def sort_nodes(items: list[ErpCategoryTreeSchema]) -> None:
            items.sort(key=lambda item: (item.sort, item.id))
            for item in items:
                sort_nodes(item.children)

        sort_nodes(roots)
        return roots

    async def _fill_parent_names(self, items: Sequence[ErpCategoryOutSchema]) -> None:
        """为分页结果批量补父分类名称。"""
        parent_ids = list({item.parent_id for item in items if item.parent_id})
        if not parent_ids:
            return
        parents = await self.categories.get_list(search={"id": ("in", parent_ids)})
        name_map = {parent.id: parent.name for parent in parents}
        for item in items:
            if item.parent_id:
                item.parent_name = name_map.get(item.parent_id)

    def _operator(self) -> int | None:
        """当前操作人ID（C端只读流程为 None）。"""
        return self.auth.user.id or None
