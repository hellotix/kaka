"""扩展属性模板业务层：后台维护模板，C端按分类取「有效属性集」。

有效属性集的合并规则
--------------------
某个分类的有效属性 = 全局模板（``category_id IS NULL``）+ 自身及各级祖先分类的模板。
分类最多三级，所以最多合并 4 组模板。

冲突处理：**就近覆盖** —— 同一个 ``code`` 出现在多处时，离当前分类越近的越优先
（自身 > 三级中的父级 > … > 一级 > 全局）。这样运营可以在一级分类上配一个通用定义，
再在三级分类上针对具体品类覆盖它（例如「容量」在「饮料」下 unit 改成 ml，
在「粮油」下改成 L）。

为什么不建索引表
----------------
需求按「单家庭最多 1000 条物品」估算，模板数量是后台配置量级（几十到几百条），
一次查出沿路径的模板在内存里合并，比维护「分类-模板」关联表简单得多，
也不会有缓存一致性问题。
"""

from collections.abc import Sequence

from redis.asyncio.client import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_schema import AuthSchema, BatchSetAvailable, PageResultSchema
from app.core.logger import logger
from app.utils.common_util import search_to_dict

from ...exceptions import BusinessError
from ..category.crud import ErpCategoryCRUD
from ..category.service import ErpCategoryService
from ..core.attrs import AttrValidationError, normalize_attrs
from ..core.constants import ErpAttrType
from .crud import ErpAttrTemplateCRUD
from .model import ErpAttrTemplateModel
from .schema import ErpAttrCreateSchema, ErpAttrOutSchema, ErpAttrQueryParam, ErpAttrUpdateSchema


class ErpAttrService:
    """扩展属性模板服务层（后台管理 + C端只读共用）"""

    def __init__(self, auth: AuthSchema, db: AsyncSession, redis: Redis | None = None) -> None:
        """初始化。

        参数:
        - auth (AuthSchema): 认证信息。后台传 ``AuthPermission`` 注入的 auth，C端传 ``AuthSchema()``。
        - db (AsyncSession): 数据库会话。
        - redis (Redis | None): Redis 连接，暂未使用，保留以对齐其他 service 的构造签名。
        """
        self.auth = auth
        self.db = db
        self.redis = redis
        self.attrs = ErpAttrTemplateCRUD(auth, db)
        self.categories = ErpCategoryCRUD(auth, db)
        self.category_service = ErpCategoryService(auth, db, redis)

    # ── 查询（后台）──────────────────────────────────────────────────

    async def page(
        self,
        page_no: int,
        page_size: int,
        search: ErpAttrQueryParam | None = None,
        order_by: list[dict[str, str]] | None = None,
    ) -> PageResultSchema[ErpAttrOutSchema]:
        """后台分页查询属性模板。"""
        offset = (page_no - 1) * page_size
        result = await self.attrs.page(
            offset=offset,
            limit=page_size,
            order_by=order_by or [{"category_id": "asc"}, {"sort": "asc"}, {"id": "asc"}],
            search=search_to_dict(search, {}),
            out_schema=ErpAttrOutSchema,
        )
        await self._fill_category_names(result.items)
        return result

    async def detail(self, id: int) -> ErpAttrOutSchema:
        """获取属性模板详情。"""
        obj = await self._get_or_raise(id)
        out = ErpAttrOutSchema.model_validate(obj)
        if obj.category_id:
            category = await self.categories.get(id=obj.category_id)
            out.category_name = category.name if category else None
        return out

    async def list_by_category(self, category_id: int | None) -> list[ErpAttrOutSchema]:
        """列出某分类直接配置的模板（不含继承，后台编辑页用）。"""
        rows = await self.attrs.list_by_category(category_id, only_enabled=False)
        result = [ErpAttrOutSchema.model_validate(row) for row in rows]
        await self._fill_category_names(result)
        return result

    # ── 查询（C端）───────────────────────────────────────────────────

    async def effective_schema(self, category_id: int, *, only_filterable: bool = False) -> list[ErpAttrOutSchema]:
        """取某分类的有效属性集（含继承），C端录入表单与筛选面板都靠它渲染。

        参数:
        - category_id (int): 目标分类ID。
        - only_filterable (bool): True 时只返回 ``is_filterable=True`` 的模板（筛选面板用）。

        返回:
        - list[ErpAttrOutSchema]: 按「就近覆盖」去重后的模板列表，已按 sort 升序排列。
          ``inherited=True`` 表示该条来自祖先分类或全局模板。
        """
        chain = await self.category_service.ancestor_ids(category_id)
        # chain 是 [一级, 二级, 三级(自身)]，反转后从最近到最远，便于就近覆盖
        ordered = list(reversed(chain))

        rows = await self.attrs.list_by_categories(ordered, only_enabled=True)
        globals_ = await self.attrs.list_by_category(None, only_enabled=True)

        # 距离越近优先级越高：按 ordered 的下标排序，下标小的先写入 merged，后写入的不覆盖
        rank = {cid: index for index, cid in enumerate(ordered)}
        merged: dict[str, ErpAttrTemplateModel] = {}
        inherited: dict[str, bool] = {}

        for row in sorted(rows, key=lambda item: rank.get(item.category_id, len(rank))):
            if row.code in merged:
                continue
            merged[row.code] = row
            inherited[row.code] = row.category_id != category_id
        for row in globals_:
            if row.code in merged:
                continue
            merged[row.code] = row
            inherited[row.code] = True

        category_names = await self._category_name_map([*ordered])
        result: list[ErpAttrOutSchema] = []
        for row in merged.values():
            if only_filterable and not row.is_filterable:
                continue
            out = ErpAttrOutSchema.model_validate(row)
            out.inherited = inherited.get(row.code, False)
            out.category_name = "全局" if not row.category_id else category_names.get(row.category_id)
            result.append(out)

        result.sort(key=lambda item: (item.sort or 0, item.id or 0))
        return result

    async def normalize(self, category_id: int, attrs: dict | None) -> dict:
        """按分类的有效模板校验并规范化前端提交的属性值。

        P1 的物品新增/修改直接调用本方法，保证落到 ``erp_item.attrs`` 的 JSON
        类型可预测（数值就是数值、日期就是 YYYY-MM-DD），JSON 过滤才不会失真。

        参数:
        - category_id (int): 物品所属分类ID。
        - attrs (dict | None): 前端提交的原始属性值。

        返回:
        - dict: 规范化后的属性值。

        异常:
        - BusinessError: 属性值不符合模板定义（必填缺失、类型错误、候选项越界）。
        """
        templates = await self.effective_schema(category_id)
        try:
            return normalize_attrs(templates, attrs)
        except AttrValidationError as e:
            raise BusinessError(msg=str(e)) from e

    # ── 写入（后台）──────────────────────────────────────────────────

    async def create(self, data: ErpAttrCreateSchema) -> ErpAttrOutSchema:
        """新增属性模板。同一作用域内 code 不可重复。"""
        if data.category_id:
            category = await self.categories.get(id=data.category_id)
            if not category:
                raise BusinessError(msg="所属分类不存在", status_code=404)
        if await self.attrs.get_by_code(data.category_id, data.code):
            raise BusinessError(msg=f"该作用域下已存在标识为「{data.code}」的属性", status_code=409)

        payload = data.model_dump(exclude_none=True)
        # options 是 Pydantic 模型列表，落 JSON 列前必须先转成纯 dict
        if data.options:
            payload["options"] = [item.model_dump() for item in data.options]
        obj = await self.attrs.create(data=payload)
        logger.info(f"新增属性模板: id={obj.id}, code={obj.code}, category_id={obj.category_id}, operator={self._operator()}")
        return await self.detail(obj.id)

    async def update(self, id: int, data: ErpAttrUpdateSchema) -> ErpAttrOutSchema:
        """修改属性模板（code 不可改，理由见 schema 注释）。"""
        obj = await self._get_or_raise(id)
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        if not changes:
            raise BusinessError(msg="没有需要修改的内容")

        new_type = changes.get("type", obj.type)
        new_options = data.options if data.options is not None else _parse_options(obj.options)
        self._check_type_options(new_type, new_options, obj.code)

        if data.options is not None:
            changes["options"] = [item.model_dump() for item in data.options]
        updated = await self.attrs.update(id=id, data=changes)
        logger.info(f"修改属性模板: id={id}, changes={list(changes)}, operator={self._operator()}")
        return await self.detail(updated.id)

    async def delete(self, ids: list[int]) -> None:
        """删除属性模板（软删除）。

        删除只影响「之后的录入不再出现该字段」，历史物品 attrs JSON 里已存的值
        不会被清除，但也不再被任何模板解释 —— 所以运营更常用的操作是「停用」，
        删除留给配错的模板。
        """
        if not ids:
            raise BusinessError(msg="删除失败，删除对象不能为空")
        objs = await self.attrs.get_list(search={"id": ("in", ids)})
        if len(objs) != len(set(ids)):
            raise BusinessError(msg="删除失败，部分属性模板不存在", status_code=404)
        await self.attrs.delete(ids=ids)
        logger.warning(f"删除属性模板: ids={ids}, operator={self._operator()}")

    async def set_available(self, data: BatchSetAvailable) -> None:
        """批量启用/停用属性模板。停用后立即从 C端表单与筛选面板消失。"""
        if not data.ids:
            raise BusinessError(msg="操作失败，对象不能为空")
        await self.attrs.set(ids=data.ids, status=data.status)
        logger.info(f"批量修改属性模板状态: ids={data.ids}, status={data.status}, operator={self._operator()}")

    # ── 内部方法 ──────────────────────────────────────────────────────

    async def _get_or_raise(self, id: int) -> ErpAttrTemplateModel:
        """取模板，不存在则抛业务异常。"""
        obj = await self.attrs.get(id=id)
        if not obj:
            raise BusinessError(msg="该属性模板不存在", status_code=404)
        return obj

    @staticmethod
    def _check_type_options(attr_type: str | None, options: Sequence[dict] | None, code: str) -> None:
        """校验类型与候选项的搭配是否合法（改类型时必须同步检查旧候选项）。"""
        if not attr_type:
            return
        need_options = attr_type in {ErpAttrType.SELECT.value, ErpAttrType.MULTI_SELECT.value}
        if need_options and not options:
            raise BusinessError(msg=f"属性「{code}」类型为 {attr_type}，必须配置候选项")
        if not need_options and options:
            raise BusinessError(msg=f"属性「{code}」类型为 {attr_type}，不应配置候选项，请先清空 options")

    async def _fill_category_names(self, items: Sequence[ErpAttrOutSchema]) -> None:
        """为模板列表批量补分类名称，全局模板显示为「全局」。"""
        ids = list({item.category_id for item in items if item.category_id})
        name_map = await self._category_name_map(ids)
        for item in items:
            item.category_name = "全局" if not item.category_id else name_map.get(item.category_id)

    async def _category_name_map(self, ids: Sequence[int]) -> dict[int, str | None]:
        """批量取分类名称，返回 {category_id: name}。"""
        unique_ids = list({item for item in ids if item})
        if not unique_ids:
            return {}
        rows = await self.categories.get_list(search={"id": ("in", unique_ids)})
        return {row.id: row.name for row in rows}

    def _operator(self) -> int | None:
        """当前操作人ID（C端只读流程为 None）。"""
        return self.auth.user.id or None


def _parse_options(raw: object) -> list[dict]:
    """把库里存的 options（JSON 列读出来是 list[dict]）转成 list[dict]，脏数据返回空列表。"""
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]
