"""家庭、成员、共享授权的数据访问层。

这一层只做「怎么查/怎么写」，不做权限判断 —— 权限在 ``core/context.py``（家庭上下文）
和 ``service.py``（业务规则）里。C端流程统一传 ``AuthSchema()``，
后台管理接口传 ``AuthPermission`` 注入的 auth，两者共用同一套 CRUD。
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_crud import CRUDBase
from app.core.base_schema import AuthSchema

from ..core.constants import ErpGrantStatus, ErpMemberStatus
from .model import ErpFamilyGrantModel, ErpFamilyMemberModel, ErpFamilyModel
from .schema import (
    ErpFamilyCreateSchema,
    ErpFamilyUpdateSchema,
    ErpGrantCreateSchema,
    ErpMemberInviteSchema,
    ErpMemberUpdateSchema,
)


class ErpFamilyCRUD(CRUDBase[ErpFamilyModel, ErpFamilyCreateSchema, ErpFamilyUpdateSchema]):
    """家庭数据层"""

    def __init__(self, auth: AuthSchema, db: AsyncSession) -> None:
        """初始化。

        参数:
        - auth (AuthSchema): 认证信息（C端流程传 ``AuthSchema()``）。
        - db (AsyncSession): 数据库会话。
        """
        super().__init__(model=ErpFamilyModel, auth=auth, db=db)

    async def get_by_invite_code(self, invite_code: str) -> ErpFamilyModel | None:
        """按邀请码查家庭（加入家庭时用）。"""
        code = (invite_code or "").strip()
        if not code:
            return None
        return await self.get(invite_code=code)


class ErpFamilyMemberCRUD(CRUDBase[ErpFamilyMemberModel, ErpMemberInviteSchema, ErpMemberUpdateSchema]):
    """家庭成员数据层"""

    def __init__(self, auth: AuthSchema, db: AsyncSession) -> None:
        """初始化。

        参数:
        - auth (AuthSchema): 认证信息。
        - db (AsyncSession): 数据库会话。
        """
        super().__init__(model=ErpFamilyMemberModel, auth=auth, db=db)

    async def get_member(self, family_id: int, user_id: int, *, include_deleted: bool = False) -> ErpFamilyMemberModel | None:
        """查某用户在某家庭的成员记录（不区分状态）。"""
        return await self.get(family_id=family_id, user_id=user_id, include_deleted=include_deleted)

    async def count_active_members(self, family_id: int) -> int:
        """统计家庭的有效成员数（不含待确认/已拒绝/已移除）。"""
        return await self.count(family_id=family_id, status=ErpMemberStatus.ACTIVE.value)

    async def count_active_members_batch(self, family_ids: Sequence[int]) -> dict[int, int]:
        """批量统计多个家庭的有效成员数。

        「我的家庭」列表要为每个家庭展示成员数，逐个 count 会产生 N 次往返；
        这里用一条 GROUP BY 拿全。没有成员的家庭不会出现在结果里，调用方按 0 处理。
        """
        if not family_ids:
            return {}
        sql = (
            select(ErpFamilyMemberModel.family_id, func.count(ErpFamilyMemberModel.id))
            .where(ErpFamilyMemberModel.is_deleted.is_(False))
            .where(ErpFamilyMemberModel.family_id.in_(list(family_ids)))
            .where(ErpFamilyMemberModel.status == ErpMemberStatus.ACTIVE.value)
            .group_by(ErpFamilyMemberModel.family_id)
        )
        rows = await self.db.execute(sql)
        return dict(rows.all())

    async def list_by_user(self, user_id: int, status: int | None = None) -> Sequence[ErpFamilyMemberModel]:
        """列出某用户的全部成员记录（跨家庭），可按状态过滤。"""
        search: dict[str, object] = {"user_id": user_id}
        if status is not None:
            search["status"] = status
        return await self.get_list(search=search, order_by=[{"id": "asc"}])

    async def list_members(self, family_id: int, status: int | None = None) -> Sequence[ErpFamilyMemberModel]:
        """列出家庭成员，可按状态过滤。"""
        search: dict[str, object] = {"family_id": family_id}
        if status is not None:
            search["status"] = status
        return await self.get_list(search=search, order_by=[{"id": "asc"}])


class ErpFamilyGrantCRUD(CRUDBase[ErpFamilyGrantModel, ErpGrantCreateSchema, ErpGrantCreateSchema]):
    """家庭间共享授权数据层"""

    def __init__(self, auth: AuthSchema, db: AsyncSession) -> None:
        """初始化。

        参数:
        - auth (AuthSchema): 认证信息。
        - db (AsyncSession): 数据库会话。
        """
        super().__init__(model=ErpFamilyGrantModel, auth=auth, db=db)

    async def get_active_grant(self, family_id: int, target_family_id: int) -> ErpFamilyGrantModel | None:
        """查两个家庭之间「生效中」的授权。

        只看 status=ACTIVE，到期与否由调用方按 ``expire_time`` 判定：
        已过期但未撤销的记录仍应能被找到，以便复用（续期）而不是插一条新的。
        """
        return await self.get(
            family_id=family_id,
            target_family_id=target_family_id,
            status=ErpGrantStatus.ACTIVE.value,
        )

    async def list_granted_to(self, family_id: int) -> Sequence[ErpFamilyGrantModel]:
        """列出「授权给某家庭」的全部生效记录（该家庭可查看哪些家庭的数据）。"""
        return await self.get_list(
            search={"target_family_id": family_id, "status": ErpGrantStatus.ACTIVE.value},
            order_by=[{"id": "asc"}],
        )

    async def list_granted_by(self, family_id: int) -> Sequence[ErpFamilyGrantModel]:
        """列出「某家庭授出」的全部生效记录。"""
        return await self.get_list(
            search={"family_id": family_id, "status": ErpGrantStatus.ACTIVE.value},
            order_by=[{"id": "asc"}],
        )

    async def mark_revoked(self, grant_id: int) -> None:
        """把授权标记为已撤销，并记录撤销时间。"""
        await self.set(ids=[grant_id], status=ErpGrantStatus.REVOKED.value, revoked_time=datetime.now(UTC))

    async def list_active_family_ids_for(self, family_id: int) -> list[int]:
        """返回某家庭当前可查看数据的授权方家庭ID列表。

        过期判定放在这里统一做，避免各调用方重复实现「expire_time 为空即长期有效」。
        """
        grants = await self.list_granted_to(family_id)
        now = datetime.now(UTC)
        result: list[int] = []
        for grant in grants:
            expire = grant.expire_time
            if expire is not None:
                expire = expire if expire.tzinfo else expire.replace(tzinfo=UTC)
                if expire < now:
                    continue
            result.append(grant.family_id)
        return result
