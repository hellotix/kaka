"""物品业务层 —— C端家庭内的物资录入、查询、扫码与批次管理。

权限分成两条线，缺一不可
------------------------
1. **角色线**：路由依赖 ``FamilyWriter`` 保证调用者至少是 member，
   只读成员（viewer）连写接口都进不来。
2. **数据行线**：普通成员只能改自己录入的物品。这条放不进路由依赖 ——
   它依赖具体那一行数据的 ``owner_user_id``，路由层拿不到，只能在 service 按行判定。

查询侧不再重复做这两件事：家庭范围与可见范围已经沉到 ``ErpItemCRUD`` 的
``_scope_conditions``（构造时锁定，每条 SQL 自动带），service 只要保证
所有查询都走 ``self.items`` 就不会漏。

写操作为什么先取一次再改
------------------------
``CRUDBase.update`` 内部自己也会 ``get`` 一次，但那一次同样带范围条件，
所以「先取回来判断再改」和「直接改」在越权上等价；
先取一次是为了拿到 ``owner_user_id`` 做「只能改自己的」判定，
并顺带拿到 ``category_id`` 做扩展属性校验。

事务边界
--------
``db_getter`` 已把整个请求包在一个事务里，CRUD 只 flush 不 commit。
所以「建档 + 写入首批批次」是原子的，中途属性校验失败不会留下没有批次的半成品。

为什么写入校验是模块级函数而不是各自私有方法
--------------------------------------------
本文件有两个服务：C端 ``ErpItemService``（绑定 ``FamilyContext``）与后台
``ErpItemAdminService``（走 ``AuthPermission``，没有当前家庭）。两者必须执行同一套
业务规则：条码家庭内查重、扩展属性按分类模板校验、批次的剩余量/日期一致性、
批次默认「在用」等缺省补齐。若后台抄一份自己的实现，两边迟早分叉，
后果是运营从后台写进库的数据 C端读不出应有的样子（模板外的属性、有效期早于生产日期）。
所以这些规则写成不依赖上下文的模块级纯函数，两个服务都调它们；
只有「取哪一行数据、有没有权限动它」这类与身份有关的部分留在各自的类里。
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from redis.asyncio.client import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_schema import AuthSchema, PageResultSchema
from app.core.logger import logger
from app.plugin.module_app.login.user.crud import AppUserCRUD
from app.plugin.module_app.login.user.model import AppUserModel
from app.utils.common_util import search_to_dict

from ...exceptions import BusinessError
from ..attr.service import ErpAttrService
from ..category.crud import ErpCategoryCRUD
from ..core.constants import FAMILY_ITEM_MAX, ErpBatchStatus, ErpFamilyRole, ErpMemberStatus
from ..core.context import FamilyContext, auth_schema
from ..family.crud import ErpFamilyCRUD, ErpFamilyMemberCRUD
from ..family.model import ErpFamilyModel
from .crud import ErpItemAdminCRUD, ErpItemBatchCRUD, ErpItemCRUD
from .model import ErpItemModel
from .schema import (
    ErpBatchAdminOutSchema,
    ErpBatchAdminQueryParam,
    ErpItemAdminCreateSchema,
    ErpItemAdminOutSchema,
    ErpItemAdminQueryParam,
    ErpItemBatchAddSchema,
    ErpItemBatchCreateSchema,
    ErpItemBatchOutSchema,
    ErpItemBatchUpdateSchema,
    ErpItemCreateSchema,
    ErpItemOutSchema,
    ErpItemQueryParam,
    ErpItemScanResultSchema,
    ErpItemScanSchema,
    ErpItemUpdateSchema,
)


class ErpItemService:
    """C端物品服务 —— 所有方法都基于已鉴权的 FamilyContext"""

    def __init__(self, ctx: FamilyContext) -> None:
        """初始化。

        参数:
        - ctx (FamilyContext): 家庭上下文（已完成登录、成员关系与角色校验）。
        """
        self.ctx = ctx
        self.family = ctx.family
        self.db = ctx.db
        self.auth = auth_schema()
        # 管理员及以上可看全家庭物资、可改任意物品；普通成员只看 family 可见的、只改自己录的
        self.can_view_all = ctx.role.weight >= ErpFamilyRole.ADMIN.weight
        self.items = ErpItemCRUD(
            self.auth,
            ctx.db,
            family_ids=[ctx.family_id],
            user_id=ctx.user_id,
            can_view_all=self.can_view_all,
        )
        self.batches = ErpItemBatchCRUD(self.auth, ctx.db)
        self.attrs = ErpAttrService(self.auth, ctx.db)
        self.categories = ErpCategoryCRUD(self.auth, ctx.db)
        self.app_users = AppUserCRUD(self.auth, ctx.db)

    # ── 查询 ──────────────────────────────────────────────────────────

    async def page(
        self,
        page_no: int,
        page_size: int,
        search: ErpItemQueryParam | None = None,
        order_by: list[dict[str, str]] | None = None,
    ) -> PageResultSchema[ErpItemOutSchema]:
        """分页查询物品（列表页）。

        库存指标（批次数/剩余总量/最近到期日）由 ``stats_by_items`` 一条 GROUP BY
        查回来，不给每行单独查一次批次。
        """
        offset = (page_no - 1) * page_size
        result = await self.items.page(
            offset=offset,
            limit=page_size,
            order_by=order_by or [{"id": "desc"}],
            search=search_to_dict(search, {}),
            out_schema=ErpItemOutSchema,
        )
        await self._fill_extras(result.items)
        return result

    async def detail(self, id: int) -> ErpItemOutSchema:
        """获取物品详情（含批次明细）。"""
        item = await self._get_or_raise(id)
        out = ErpItemOutSchema.model_validate(item)
        await self._fill_extras([out])
        rows = await self.batches.list_by_item(id)
        out.batches = [ErpItemBatchOutSchema.model_validate(row) for row in rows]
        return out

    # ── 录入与维护 ────────────────────────────────────────────────────

    async def create(self, data: ErpItemCreateSchema) -> ErpItemOutSchema:
        """录入一件物品（可同时带首批批次）。

        三道校验：家庭物品数上限 → 商品编码家庭内不重复 → 扩展属性符合分类模板。
        编码重复直接拒绝而不是静默归并：用户既然点了「新建」，多半是没察觉到
        家里已经买过同款；静默并进去会让两件不同的东西混成一条档案。
        """
        total = await self.items.count_family_items(self.family.id)
        if total >= FAMILY_ITEM_MAX:
            raise BusinessError(msg=f"单个家庭最多录入 {FAMILY_ITEM_MAX} 件物品，请先清理无用数据")

        owner_user_id = data.owner_user_id or self.ctx.user_id
        if owner_user_id != self.ctx.user_id:
            # 把物品挂到别人名下属于管理动作，普通成员只能录自己的
            self.ctx.require(ErpFamilyRole.ADMIN)
        await ensure_barcode_free(self.items, self.family.id, data.barcode, exclude_id=None)

        payload: dict[str, Any] = data.model_dump(exclude_none=True, exclude={"batches"})
        payload["family_id"] = self.family.id
        payload["owner_user_id"] = owner_user_id
        payload["attrs"] = await normalize_item_attrs(self.attrs, data.category_id, data.attrs)

        item = await self.items.create(data=payload)
        for batch in data.batches:
            await self.batches.create(data=build_batch_payload(item, batch))

        logger.info(f"录入物品: item_id={item.id}, family_id={self.family.id}, name={item.name}, 批次数={len(data.batches)}, operator={self.ctx.user_id}")
        return await self.detail(item.id)

    async def update(self, id: int, data: ErpItemUpdateSchema) -> ErpItemOutSchema:
        """修改物品档案（批次改动走批次接口）。"""
        item = await self._get_writable_or_raise(id)
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        if not changes:
            raise BusinessError(msg="没有需要修改的内容")

        if "owner_user_id" in changes and changes["owner_user_id"] != self.ctx.user_id:
            self.ctx.require(ErpFamilyRole.ADMIN)
        if "barcode" in changes:
            await ensure_barcode_free(self.items, self.family.id, changes["barcode"], exclude_id=id)

        if "attrs" in changes or "category_id" in changes:
            # 换分类时旧属性要按新分类的模板重新过一遍，模板外的键会被丢掉；
            # 只改属性时用物品当前的分类
            category_id = changes.get("category_id", item.category_id)
            raw_attrs = changes["attrs"] if "attrs" in changes else item.attrs
            changes["attrs"] = await normalize_item_attrs(self.attrs, category_id, raw_attrs)

        updated = await self.items.update(id=id, data=changes)
        logger.info(f"修改物品: item_id={id}, family_id={self.family.id}, changes={list(changes)}, operator={self.ctx.user_id}")
        return await self.detail(updated.id)

    async def delete(self, ids: list[int]) -> None:
        """批量删除物品（软删除）。

        逐条做可写判定：只要列表里有一个不是自己能动的，整批拒绝，
        避免「一部分删掉一部分没删」这种用户难以理解的半成功状态。
        """
        if not ids:
            raise BusinessError(msg="删除失败，删除对象不能为空")
        for item_id in ids:
            await self._get_writable_or_raise(item_id)
        await self.items.delete(ids=ids)
        # 批次跟随父物品一起软删：P3 的过期扫描按 family_id + status 扫批次，
        # 留着已删物品的批次会让它们白占一次扫描与提醒
        for item_id in ids:
            batch_ids = [row.id for row in await self.batches.list_by_item(item_id)]
            if batch_ids:
                await self.batches.delete(ids=batch_ids)
        logger.warning(f"删除物品: item_ids={ids}, family_id={self.family.id}, operator={self.ctx.user_id}")

    # ── 扫码 ──────────────────────────────────────────────────────────

    async def scan(self, data: ErpItemScanSchema) -> ErpItemScanResultSchema:
        """扫商品编码：家庭内查重。

        命中 → 返回物品档案 + 最近一次批次（客户端据此预填单价/渠道，用户进「新增批次」表单）；
        未命中 → 原样回传编码（客户端进「新建物品」表单，编码预填好）。
        """
        item = await self.items.get_by_barcode(self.family.id, data.barcode)
        if not item:
            return ErpItemScanResultSchema(matched=False, barcode=data.barcode)

        out = ErpItemOutSchema.model_validate(item)
        await self._fill_extras([out])
        last_batch = await self.batches.get_last_batch(item.id)
        return ErpItemScanResultSchema(
            matched=True,
            barcode=data.barcode,
            item=out,
            last_batch=ErpItemBatchOutSchema.model_validate(last_batch) if last_batch else None,
        )

    # ── 批次 ──────────────────────────────────────────────────────────

    async def create_batch(self, data: ErpItemBatchAddSchema) -> ErpItemBatchOutSchema:
        """给已有物品新增一个批次（复购入口）。

        批次的可见性跟随父物品，所以先取一次物品 —— 那次查询已经带范围条件，
        取不到就等于「不存在或无权操作」，不需要再单独判可见性。
        """
        item = await self._get_writable_or_raise(data.item_id)
        batch = await self.batches.create(data=build_batch_payload(item, data))
        logger.info(f"新增批次: batch_id={batch.id}, item_id={item.id}, family_id={self.family.id}, operator={self.ctx.user_id}")
        return ErpItemBatchOutSchema.model_validate(batch)

    async def update_batch(self, id: int, data: ErpItemBatchUpdateSchema) -> ErpItemBatchOutSchema:
        """修改批次（剩余量、有效期、状态等）。"""
        batch = await self.batches.get(id=id)
        if not batch:
            raise BusinessError(msg="批次不存在", status_code=404)
        await self._get_writable_or_raise(batch.item_id)

        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        if not changes:
            raise BusinessError(msg="没有需要修改的内容")
        check_batch_consistency(batch, changes)

        updated = await self.batches.update(id=id, data=changes)
        logger.info(f"修改批次: batch_id={id}, changes={changes}, operator={self.ctx.user_id}")
        return ErpItemBatchOutSchema.model_validate(updated)

    async def delete_batch(self, id: int) -> None:
        """删除批次（软删除）。录错数量/有效期时用它，比改状态干净。"""
        batch = await self.batches.get(id=id)
        if not batch:
            raise BusinessError(msg="批次不存在", status_code=404)
        await self._get_writable_or_raise(batch.item_id)
        await self.batches.delete(ids=[id])
        logger.warning(f"删除批次: batch_id={id}, item_id={batch.item_id}, operator={self.ctx.user_id}")

    # ── 内部方法 ──────────────────────────────────────────────────────

    async def _get_or_raise(self, id: int) -> ErpItemModel:
        """取物品，取不到统一报「不存在或无权查看」。

        不区分「真的没有」与「有但你看不见」：区分了就等于告诉越权者
        「这个 ID 上确实有别人的私密物品」。
        """
        item = await self.items.get(id=id)
        if not item:
            raise BusinessError(msg="物品不存在或无权查看", status_code=404)
        return item

    async def _get_writable_or_raise(self, id: int) -> ErpItemModel:
        """取物品并校验可写：管理员及以上随意，普通成员只能动自己录的。"""
        item = await self._get_or_raise(id)
        if not self.can_view_all and item.owner_user_id != self.ctx.user_id:
            raise BusinessError(msg="只能修改自己录入的物品，请联系户主或管理员", status_code=403)
        return item

    async def _fill_extras(self, items: Sequence[ErpItemOutSchema]) -> None:
        """批量补齐列表/详情要展示的关联字段（实现见模块级 ``fill_item_extras``）。"""
        await fill_item_extras(items, self.batches, self.app_users, self.categories)


# ══════════════════════════ C端与后台共用的业务规则 ══════════════════════════


async def ensure_barcode_free(items: ErpItemCRUD, family_id: int, barcode: str | None, *, exclude_id: int | None) -> None:
    """校验家庭内商品编码不重复（修改时排除自身）。

    查重必须带 family_id：同一条码在不同家庭是各自独立的物品，
    全局查重会让第二个录入同样商品的用户莫名撞车。

    参数:
    - items (ErpItemCRUD): 调用方的物品数据层。C端传实例已带可见范围裁剪，
      所以「撞到一个看不见的私密物品」时提示语里不会泄露对方的物品名 ——
      不过那次查询本身带范围条件，普通成员压根查不到别人的行。
    - family_id (int): 查重范围所属家庭。
    - barcode (str | None): 待校验的商品编码，空值直接放过（编码本来就允许不填）。
    - exclude_id (int | None): 修改场景下排除的物品ID。
    """
    if not barcode:
        return
    existing = await items.get_by_barcode(family_id, barcode)
    if existing and existing.id != exclude_id:
        raise BusinessError(
            msg=f"家庭内已存在编码为「{barcode}」的物品「{existing.name}」，请直接为它新增批次",
            status_code=409,
        )


async def normalize_item_attrs(attrs_service: ErpAttrService, category_id: int | None, attrs: dict | None) -> dict | None:
    """按分类的有效模板校验扩展属性。

    未选择分类的物品不接受属性值：没有模板就没有校验依据，
    放进去的 JSON 将来无人能解释（该分类后续配了同名 code 时含义还可能对不上）。
    模板之外的键由 ``ErpAttrService.normalize`` 直接丢弃。
    """
    if not attrs:
        return None
    if not category_id:
        raise BusinessError(msg="未选择分类的物品不支持扩展属性，请先选择分类")
    return await attrs_service.normalize(category_id, attrs)


def build_batch_payload(item: ErpItemModel, data: ErpItemBatchCreateSchema) -> dict[str, Any]:
    """把批次入参补全成落库数据。

    - ``remain_qty`` 不填 = 与进货数量一致（刚买回来还没用）；
    - ``purchase_time`` 不填 = 服务器当前时间；
    - ``family_id`` 冗余自父物品，P3 定时扫描不必 join 档案表；
    - ``status`` 恒为「在用」：新建批次就是刚进的一批，耗尽/过期由后续操作或扫描驱动，
      所以后台改状态也只走修改接口，不在创建时开放。
    """
    payload: dict[str, Any] = data.model_dump(exclude_none=True, exclude={"item_id"})
    payload["item_id"] = item.id
    payload["family_id"] = item.family_id
    payload["status"] = ErpBatchStatus.IN_USE.value
    if payload.get("remain_qty") is None:
        payload["remain_qty"] = data.quantity
    if payload.get("purchase_time") is None:
        payload["purchase_time"] = datetime.now(UTC)
    return payload


def check_batch_consistency(batch: Any, changes: dict[str, Any]) -> None:
    """修改批次的跨字段校验（schema 层只能校验单次提交内的字段）。

    改一个字段时另一个字段可能仍是旧值，所以要拿「改后的值」和「库里的值」一起比。
    """
    quantity = changes.get("quantity", batch.quantity)
    remain_qty = changes.get("remain_qty", batch.remain_qty)
    if quantity is not None and remain_qty is not None and float(remain_qty) > float(quantity):
        raise BusinessError(msg="剩余数量不能大于进货数量")

    production_date = changes.get("production_date", batch.production_date)
    expiry_date = changes.get("expiry_date", batch.expiry_date)
    if production_date and expiry_date and expiry_date < production_date:
        raise BusinessError(msg="有效期不能早于生产日期")


async def fill_item_extras(
    items: Sequence[ErpItemOutSchema],
    batches: ErpItemBatchCRUD,
    app_users: AppUserCRUD,
    categories: ErpCategoryCRUD,
) -> None:
    """批量补齐列表/详情要展示的关联字段。

    三种关联各查一次（批次统计、归属人昵称、分类名），
    一页 20 条也只有 3 条 SQL，不给每行单独查。
    """
    if not items:
        return

    stats = await batches.stats_by_items([item.id for item in items if item.id])
    owner_map = await _owner_name_map(app_users, [item.owner_user_id for item in items])

    category_ids = list({item.category_id for item in items if item.category_id})
    category_map: dict[int, str] = {}
    if category_ids:
        rows = await categories.get_list(search={"id": ("in", category_ids)})
        category_map = {row.id: row.name for row in rows}

    for out in items:
        stat = stats.get(out.id or 0, {})
        out.batch_count = stat.get("batch_count", 0)
        out.total_remain_qty = stat.get("total_remain_qty", 0)
        out.nearest_expiry_date = stat.get("nearest_expiry_date")
        out.owner_name = owner_map.get(out.owner_user_id or 0)
        out.category_name = category_map.get(out.category_id or 0)


async def _owner_name_map(app_users: AppUserCRUD, owner_ids: Sequence[int | None]) -> dict[int, str | None]:
    """批量取归属人展示名，返回 {user_id: 昵称或用户名}。"""
    ids = list({item for item in owner_ids if item})
    if not ids:
        return {}
    users = await app_users.get_list(
        search={"id": ("in", ids)},
        load_columns=[AppUserModel.id, AppUserModel.nickname, AppUserModel.username],
    )
    return {user.id: (user.nickname or user.username) for user in users}


class ErpItemAdminService:
    """后台物品与批次管理服务（运营视角）

    和 C端 ``ErpItemService`` 的差别只有一件事：没有 ``FamilyContext``。
    由此派生出三处必须不同的地方：

    1. **归属要显式传**：C端的 ``family_id`` 来自 ``X-Family-Id`` 头、归属人默认当前用户，
       后台两者都不知道，只能由请求体必填（见 ``ErpItemAdminCreateSchema``）。
    2. **数据行不裁剪**：C端每个成员只看得到自己该看的那些行，
       后台要能处理用户的误删找回与数据修复，所以跨家庭、且私密物品同样可见。
       代价是这组接口必须只授予可信岗位（权限标识 ``module_app:erp:item:*``）。
    3. **不判「只能改自己录的」**：那条规则的前提是「录入人=当前用户」，后台操作者不是家庭成员。

    写入校验（数量上限、条码查重、属性模板、批次一致性）与 C端共用本文件顶部的模块级函数，
    两边规则分叉的代价见那段 docstring。
    """

    def __init__(self, auth: AuthSchema, db: AsyncSession, redis: Redis) -> None:
        """初始化。

        参数:
        - auth (AuthSchema): 后台认证上下文（由 ``AuthPermission`` 注入）。
        - db (AsyncSession): 数据库会话。
        - redis (Redis): Redis 连接（与其他后台服务保持一致的构造签名，当前未使用）。
        """
        self.auth = auth
        self.db = db
        self.redis = redis
        # family_id 不锁定 => 跨家庭全量；带 family_id 查询参数的过滤由 search 走 where 条件
        self.items = ErpItemAdminCRUD(auth, db)
        self.batches = ErpItemBatchCRUD(auth, db)
        self.attrs = ErpAttrService(auth, db)
        self.categories = ErpCategoryCRUD(auth, db)
        self.app_users = AppUserCRUD(auth, db)
        self.families = ErpFamilyCRUD(auth, db)
        self.members = ErpFamilyMemberCRUD(auth, db)

    # ── 物品 ──────────────────────────────────────────────────────────

    async def page(
        self,
        page_no: int,
        page_size: int,
        search: ErpItemAdminQueryParam | None = None,
        order_by: list[dict[str, str]] | None = None,
    ) -> PageResultSchema[ErpItemAdminOutSchema]:
        """分页查询全平台物品（可按 ``family_id`` 收敛到某个家庭）。"""
        offset = (page_no - 1) * page_size
        result = await self.items.page(
            offset=offset,
            limit=page_size,
            order_by=order_by or [{"id": "desc"}],
            search=search_to_dict(search, {}),
            out_schema=ErpItemAdminOutSchema,
        )
        await fill_item_extras(result.items, self.batches, self.app_users, self.categories)
        await self._fill_family_names(result.items)
        return result

    async def detail(self, id: int) -> ErpItemAdminOutSchema:
        """获取物品详情（含批次明细）。"""
        item = await self._get_or_raise(id)
        out = ErpItemAdminOutSchema.model_validate(item)
        await fill_item_extras([out], self.batches, self.app_users, self.categories)
        await self._fill_family_names([out])
        rows = await self.batches.list_by_item(id)
        out.batches = [ErpItemBatchOutSchema.model_validate(row) for row in rows]
        return out

    async def create(self, data: ErpItemAdminCreateSchema) -> ErpItemAdminOutSchema:
        """后台代用户录入物品（可同时带首批批次）。

        比 C端多两道前置检查：目标家庭要存在，归属人要是该家庭的**有效**成员。
        放过这两条就会写出「归属人已退出」的记录 —— 那些记录在 C端家庭列表里
        按 ``owner_user_id`` 显示归属人时取不到昵称，用户只会看到一条说不清来历的物品。
        """
        family = await self._get_family_or_raise(data.family_id)
        await self._ensure_member(family.id, data.owner_user_id)

        total = await self.items.count_family_items(family.id)
        if total >= FAMILY_ITEM_MAX:
            raise BusinessError(msg=f"单个家庭最多录入 {FAMILY_ITEM_MAX} 件物品，请先清理无用数据")

        await ensure_barcode_free(self.items, family.id, data.barcode, exclude_id=None)

        payload: dict[str, Any] = data.model_dump(exclude_none=True, exclude={"batches"})
        payload["family_id"] = family.id
        payload["attrs"] = await normalize_item_attrs(self.attrs, data.category_id, data.attrs)

        item = await self.items.create(data=payload)
        for batch in data.batches:
            await self.batches.create(data=build_batch_payload(item, batch))

        logger.info(f"后台录入物品: item_id={item.id}, family_id={family.id}, name={item.name}, 批次数={len(data.batches)}, operator={self._operator()}")
        return await self.detail(item.id)

    async def update(self, id: int, data: ErpItemUpdateSchema) -> ErpItemAdminOutSchema:
        """修改物品档案。

        后台同样不接受改 ``family_id``（复用 C端的 ``ErpItemUpdateSchema``，那里没有这个字段）：
        跨家庭搬一条档案要连带改所有批次的冗余 ``family_id`` 与可见性判定，
        属于数据修复而不是日常运营动作，真要做应该走迁移脚本。
        """
        item = await self._get_or_raise(id)
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        if not changes:
            raise BusinessError(msg="没有需要修改的内容")

        if "barcode" in changes:
            await ensure_barcode_free(self.items, item.family_id, changes["barcode"], exclude_id=id)
        if "owner_user_id" in changes:
            await self._ensure_member(item.family_id, changes["owner_user_id"])
        if "attrs" in changes or "category_id" in changes:
            # 换分类时旧属性按新分类的模板重新过一遍，模板外的键会被丢掉
            category_id = changes.get("category_id", item.category_id)
            raw_attrs = changes["attrs"] if "attrs" in changes else item.attrs
            changes["attrs"] = await normalize_item_attrs(self.attrs, category_id, raw_attrs)

        updated = await self.items.update(id=id, data=changes)
        logger.info(f"后台修改物品: item_id={id}, changes={list(changes)}, operator={self._operator()}")
        return await self.detail(updated.id)

    async def delete(self, ids: list[int]) -> None:
        """批量删除物品（软删除），批次跟随一起删除。

        先整批校验存在性再动手：避免出现「删掉一半另一半还在」这种半成功，
        后台一次点几十个 ID，回滚成本比 C端高得多。
        """
        if not ids:
            raise BusinessError(msg="删除失败，删除对象不能为空")
        rows = await self.items.get_list(search={"id": ("in", list(set(ids)))})
        if len(rows) != len(set(ids)):
            raise BusinessError(msg="删除失败，部分物品不存在", status_code=404)

        for item in rows:
            batch_ids = [row.id for row in await self.batches.list_by_item(item.id)]
            if batch_ids:
                await self.batches.delete(ids=batch_ids)
        await self.items.delete(ids=list(set(ids)))
        logger.warning(f"后台删除物品: item_ids={ids}, operator={self._operator()}")

    # ── 批次 ──────────────────────────────────────────────────────────

    async def batch_page(
        self,
        page_no: int,
        page_size: int,
        search: ErpBatchAdminQueryParam | None = None,
        order_by: list[dict[str, str]] | None = None,
    ) -> PageResultSchema[ErpBatchAdminOutSchema]:
        """分页查询全平台批次（可按家庭/物品/状态过滤，``expiry_date`` 传两个日期即有效期区间）。

        运营最常用的就是「这段时间到期的批次」——P3 的自动提醒上线前，
        这是唯一能提前发现临期物资的入口。
        """
        offset = (page_no - 1) * page_size
        result = await self.batches.page(
            offset=offset,
            limit=page_size,
            order_by=order_by or [{"id": "desc"}],
            search=search_to_dict(search, {}),
            out_schema=ErpBatchAdminOutSchema,
        )
        await self._fill_batch_extras(result.items)
        return result

    async def batch_create(self, data: ErpItemBatchAddSchema) -> ErpBatchAdminOutSchema:
        """给已有物品新增批次。"""
        item = await self._get_or_raise(data.item_id)
        batch = await self.batches.create(data=build_batch_payload(item, data))
        logger.info(f"后台新增批次: batch_id={batch.id}, item_id={item.id}, family_id={item.family_id}, operator={self._operator()}")
        return await self._batch_out(batch)

    async def batch_update(self, id: int, data: ErpItemBatchUpdateSchema) -> ErpBatchAdminOutSchema:
        """修改批次（剩余量、有效期、状态等）。

        后台改批次最常用的动作就是把误录的状态纠正回来（``status`` 1~4），
        这也是 C端「已耗尽/已丢弃」在 P3 扫描误判时唯一的补救入口。
        """
        batch = await self.batches.get(id=id)
        if not batch:
            raise BusinessError(msg="批次不存在", status_code=404)

        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        if not changes:
            raise BusinessError(msg="没有需要修改的内容")
        check_batch_consistency(batch, changes)

        updated = await self.batches.update(id=id, data=changes)
        logger.info(f"后台修改批次: batch_id={id}, changes={changes}, operator={self._operator()}")
        return await self._batch_out(updated)

    async def batch_delete(self, ids: list[int]) -> None:
        """批量删除批次（软删除）。

        删批次不删档案：用户可能只是录重了一次进货，档案还得留着。
        """
        if not ids:
            raise BusinessError(msg="删除失败，删除对象不能为空")
        rows = await self.batches.get_list(search={"id": ("in", list(set(ids)))})
        if len(rows) != len(set(ids)):
            raise BusinessError(msg="删除失败，部分批次不存在", status_code=404)
        await self.batches.delete(ids=list(set(ids)))
        logger.warning(f"后台删除批次: batch_ids={ids}, operator={self._operator()}")

    # ── 内部方法 ──────────────────────────────────────────────────────

    async def _get_or_raise(self, id: int) -> ErpItemModel:
        """取物品，不存在报 404。

        与 C端文案不同：这里没有「无权查看」这一说，范围不裁剪，
        查不到就是真没有。
        """
        item = await self.items.get(id=id)
        if not item:
            raise BusinessError(msg="物品不存在", status_code=404)
        return item

    async def _get_family_or_raise(self, id: int) -> ErpFamilyModel:
        """取家庭，不存在报 404。"""
        family = await self.families.get(id=id)
        if not family:
            raise BusinessError(msg="该家庭不存在", status_code=404)
        return family

    async def _ensure_member(self, family_id: int, user_id: int) -> None:
        """校验归属人确实属于该家庭且状态有效。"""
        member = await self.members.get_member(family_id, user_id)
        if not member:
            raise BusinessError(msg=f"用户 {user_id} 不是家庭 {family_id} 的成员", status_code=400)
        if member.status != ErpMemberStatus.ACTIVE.value:
            raise BusinessError(msg="该用户已退出或被移出此家庭，不能作为物品归属人", status_code=400)

    def _operator(self) -> int | None:
        """当前后台操作人ID（只进日志，不落库到业务字段）。"""
        return self.auth.user.id or None

    async def _fill_family_names(self, items: Sequence[ErpItemAdminOutSchema]) -> None:
        """批量补齐所属家庭名称。"""
        family_ids = list({item.family_id for item in items if item.family_id})
        if not family_ids:
            return
        rows = await self.families.get_list(search={"id": ("in", family_ids)})
        name_map = {row.id: row.name for row in rows}
        for out in items:
            out.family_name = name_map.get(out.family_id or 0)

    async def _fill_batch_extras(self, rows: Sequence[ErpBatchAdminOutSchema]) -> None:
        """批量补齐批次的物品名与家庭名（后台批次列表是跨家庭混排的，只有 ID 没法看）。"""
        if not rows:
            return
        item_ids = list({row.item_id for row in rows if row.item_id})
        if not item_ids:
            return
        items = await self.items.get_list(search={"id": ("in", item_ids)})
        item_map = {item.id: item for item in items}

        family_ids = list({item.family_id for item in items if item.family_id})
        family_map: dict[int, str] = {}
        if family_ids:
            families = await self.families.get_list(search={"id": ("in", family_ids)})
            family_map = {family.id: family.name for family in families}

        for row in rows:
            item = item_map.get(row.item_id or 0)
            if item:
                row.item_name = item.name
                row.family_name = family_map.get(item.family_id or 0)

    async def _batch_out(self, batch: Any) -> ErpBatchAdminOutSchema:
        """批次模型转后台响应（带物品名与家庭名）。"""
        out = ErpBatchAdminOutSchema.model_validate(batch)
        await self._fill_batch_extras([out])
        return out
