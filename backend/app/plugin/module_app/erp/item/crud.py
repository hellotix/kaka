"""物品与批次数据访问层。

可见范围在这里落地，而不是散在各个 service 方法里
--------------------------------------------------
``ErpItemCRUD`` 构造时就固定「本次请求的家庭 + 当前用户 + 能否看全」，
每次查询由 ``_build_conditions`` 自动追加可见性条件。
这样做的原因很直接：只要有一次查询忘了加可见性判断，用户就能看到别人的私密物资，
而这类漏洞靠 code review 很难兜住。把条件绑在数据层上，忘不掉。

例外有两处，都在本文件里：
1. 数量上限统计走 ``count_family_items``，它统计的是「这个家庭一共有多少条档案」，
   必须绕开可见范围（见方法注释）。
2. 后台运营视角的 ``ErpItemAdminCRUD`` 用子类整段覆写范围条件（跨家庭、不做成员级裁剪），
   而不是给 C端那个类加「不裁剪」开关 —— 理由见该类的 docstring。
"""

from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.base_crud import CRUDBase
from app.core.base_schema import AuthSchema

from ..core.constants import BATCH_ACTIVE_STATUSES, ErpItemVisibility
from .model import ErpItemBatchModel, ErpItemModel
from .schema import (
    ErpItemBatchCreateSchema,
    ErpItemBatchUpdateSchema,
    ErpItemCreateSchema,
    ErpItemUpdateSchema,
)


class ErpItemCRUD(CRUDBase[ErpItemModel, ErpItemCreateSchema, ErpItemUpdateSchema]):
    """物品档案数据层（构造即锁定家庭与可见范围）"""

    def __init__(self, auth: AuthSchema, db: AsyncSession, *, family_ids: Sequence[int], user_id: int, can_view_all: bool) -> None:
        """初始化。

        参数:
        - auth (AuthSchema): 认证信息（C端流程传 ``AuthSchema()``）。
        - db (AsyncSession): 数据库会话。
        - family_ids (Sequence[int]): 允许查到的家庭ID。P1 固定为「当前家庭」一个；
          P2 开放共享授权后扩展为「当前家庭 + 授权给我的家庭」，条件自动跟着变。
        - user_id (int): 当前登录的C端用户ID（判定「自己录入的物品」）。
        - can_view_all (bool): 户主/管理员为 True，可看全家庭物资；
          普通成员/只读成员为 False，只看 ``visibility=family`` 或自己录入的。
        """
        super().__init__(model=ErpItemModel, auth=auth, db=db)
        self.family_ids = list(family_ids)
        self.user_id = user_id
        self.can_view_all = can_view_all

    async def _build_conditions(self, include_deleted: bool = False, **kwargs) -> list[ColumnElement]:
        """在基类条件之上强制追加数据范围条件（所有查询路径都会经过这里）。"""
        conditions = await super()._build_conditions(include_deleted=include_deleted, **kwargs)
        conditions.extend(self._scope_conditions())
        return conditions

    def _scope_conditions(self) -> list[ColumnElement]:
        """数据范围条件 —— 先按家庭收敛，再按可见范围收敛。

        - 家庭：``family_id IN family_ids``，防止越权者猜 ID 读到别人家的物品。
        - 可见范围：户主/管理员不加限制；其他成员只能看 ``visibility=family``
          或 ``owner_user_id=自己``。

        ``share_to``（物品级共享名单）刻意不参与判定：JSON 数组用 LIKE 匹配用户ID
        会出现「共享给 3 号，13 号也能看到」这类误命中，而误命中在权限上是越权而不是脏数据，
        所以宁可不生效。P2 落物品级共享时改用精确的 JSON 包含判断再打开。
        """
        conditions: list[ColumnElement] = [ErpItemModel.family_id.in_(self.family_ids)]
        if not self.can_view_all:
            conditions.append(
                or_(
                    ErpItemModel.visibility == ErpItemVisibility.FAMILY.value,
                    ErpItemModel.owner_user_id == self.user_id,
                )
            )
        return conditions

    # ── 业务查询 ──────────────────────────────────────────────────────

    async def get_by_barcode(self, family_id: int, barcode: str) -> ErpItemModel | None:
        """家庭内按商品编码查物品（扫码录入用）。

        查重同样受可见范围约束：否则任何人都能靠试条码探测出别人私密物品是否存在。
        """
        if not barcode:
            return None
        return await self.get(family_id=family_id, barcode=barcode)

    async def count_family_items(self, family_id: int) -> int:
        """统计家庭内的物品档案总数（用于 1000 条上限校验）。

        刻意绕开 ``_build_conditions``：上限是家庭级配额，
        不能因为「当前用户看不见某些物品」就允许超量录入。
        """
        sql = select(func.count()).select_from(ErpItemModel).where(
            ErpItemModel.family_id == family_id,
            ErpItemModel.is_deleted == false(),
        )
        result = await self.db.execute(sql)
        return result.scalar() or 0


class ErpItemAdminCRUD(ErpItemCRUD):
    """物品档案数据层（后台运营视角）

    为什么不复用 ``ErpItemCRUD`` 加一个「不裁剪」的开关
    ----------------------------------------------------
    ``ErpItemCRUD`` 把 ``family_ids`` / ``user_id`` / ``can_view_all`` 设为必填关键字参数，
    就是为了让「忘了加范围条件」在写代码时直接报错。若把其中某个改成可选（None=不裁剪），
    C端某次重构漏传一次参数，得到的不是异常而是「看到了别人全家的物品」——
    越权不会以报错的形式被发现。

    所以这里用子类显式覆写范围条件，C端那道强制保持原样。
    ``user_id`` / ``can_view_all`` 传占位值仅为满足父类构造签名：本类的
    ``_scope_conditions`` 已经整段覆写，这两个字段不会被读到。
    """

    def __init__(self, auth: AuthSchema, db: AsyncSession, *, family_id: int | None = None) -> None:
        """初始化。

        参数:
        - auth (AuthSchema): 后台认证信息。
        - db (AsyncSession): 数据库会话。
        - family_id (int | None): 锁定到某个家庭；None 表示跨家庭（后台全量列表）。
        """
        super().__init__(auth, db, family_ids=[family_id] if family_id else [], user_id=0, can_view_all=True)
        self.family_id = family_id

    def _scope_conditions(self) -> list[ColumnElement]:
        """后台范围条件：可选按家庭收敛，永远不做成员级可见性裁剪。

        私密物品在后台列表里是可见的 —— 运营要能处理用户的误删与找回诉求，
        但这组接口的权限标识（``module_app:erp:item:*``）本身就该只发给可信岗位。
        """
        if self.family_id is None:
            return []
        return [ErpItemModel.family_id == self.family_id]


class ErpItemBatchCRUD(CRUDBase[ErpItemBatchModel, ErpItemBatchCreateSchema, ErpItemBatchUpdateSchema]):
    """物品批次数据层

    批次的可见性跟随父物品：service 层每次操作批次前都先用 ``ErpItemCRUD``
    取一次物品（该查询已带可见范围条件），取不到就直接拒绝，
    所以本类不需要再做一遍可见性过滤。
    """

    def __init__(self, auth: AuthSchema, db: AsyncSession) -> None:
        """初始化。

        参数:
        - auth (AuthSchema): 认证信息。
        - db (AsyncSession): 数据库会话。
        """
        super().__init__(model=ErpItemBatchModel, auth=auth, db=db)

    async def list_by_item(self, item_id: int) -> Sequence[ErpItemBatchModel]:
        """列出某物品的全部批次（新买的排前面）。"""
        return await self.get_list(
            search={"item_id": ("eq", item_id)},
            order_by=[{"purchase_time": "desc"}, {"id": "desc"}],
        )

    async def get_last_batch(self, item_id: int) -> ErpItemBatchModel | None:
        """取最近一次批次（扫码命中后预填单价/渠道用）。"""
        rows = await self.get_list(
            search={"item_id": ("eq", item_id)},
            order_by=[{"purchase_time": "desc"}, {"id": "desc"}],
        )
        return rows[0] if rows else None

    async def stats_by_items(self, item_ids: Sequence[int]) -> dict[int, dict[str, Any]]:
        """批量统计多个物品的批次指标，避免列表页 N+1。

        参数:
        - item_ids (Sequence[int]): 物品档案ID列表。

        返回:
        - dict[int, dict]: ``{item_id: {"batch_count": 批次数, "total_remain_qty": 在用批次剩余量之和,
          "nearest_expiry_date": 在用批次中最早的有效期}}``。没有批次的物品不会出现在字典里。
        """
        if not item_ids:
            return {}
        sql = (
            select(
                ErpItemBatchModel.item_id,
                func.count(ErpItemBatchModel.id).label("batch_count"),
                func.coalesce(func.sum(ErpItemBatchModel.remain_qty), 0).label("total_remain_qty"),
                func.min(ErpItemBatchModel.expiry_date).label("nearest_expiry_date"),
            )
            .where(
                ErpItemBatchModel.item_id.in_(list(item_ids)),
                ErpItemBatchModel.is_deleted == false(),
                # 只统计「在用」批次：已耗尽/过期/丢弃的不算库存
                ErpItemBatchModel.status.in_(sorted(BATCH_ACTIVE_STATUSES)),
            )
            .group_by(ErpItemBatchModel.item_id)
        )
        result = await self.db.execute(sql)
        stats: dict[int, dict[str, Any]] = {}
        for item_id, batch_count, total_remain_qty, nearest_expiry in result.all():
            stats[item_id] = {
                "batch_count": int(batch_count or 0),
                "total_remain_qty": float(total_remain_qty or 0),
                "nearest_expiry_date": nearest_expiry if isinstance(nearest_expiry, date) else None,
            }
        return stats
