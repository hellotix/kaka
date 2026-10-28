"""家庭业务层：C端家庭门户、家庭内操作、后台管理三套服务。

为什么拆成三个 Service
----------------------
- ``ErpFamilyPortalService``：不需要家庭上下文的操作（创建家庭、我的家庭列表、
  凭邀请码加入、处理定向邀请、退出）。此时用户可能一个家庭都没有，
  强行套 ``X-Family-Id`` 头会让「创建第一个家庭」这个接口无法调用。
- ``ErpFamilyService``：家庭内操作，入参是已鉴权的 ``FamilyContext``，
  角色不足直接 403，不需要每个方法重复校验成员关系。
- ``ErpFamilyAdminService``：后台运营视角，走 ``AuthPermission`` 权限标识，
  与 C端完全不同的鉴权体系，不能混用。

事务边界
--------
``db_getter`` 已把整个请求包在一个事务里，CRUD 只 flush 不 commit。
所以「创建家庭 + 写入户主成员记录」这类多表操作天然是原子的，
中途抛异常会整体回滚，不会留下没有户主的孤儿家庭。
"""

import secrets
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from redis.asyncio.client import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_schema import AuthSchema, BatchSetAvailable, PageResultSchema
from app.core.logger import logger
from app.plugin.module_app.login.core.dependencies import AppAuthContext
from app.plugin.module_app.login.user.crud import AppUserCRUD
from app.plugin.module_app.login.user.model import AppUserModel
from app.utils.common_util import search_to_dict

from ...exceptions import BusinessError
from ..core.constants import (
    FAMILY_MEMBER_MAX,
    ErpFamilyRole,
    ErpGrantSource,
    ErpGrantStatus,
    ErpMemberStatus,
)
from ..core.context import FamilyContext, auth_schema
from .crud import ErpFamilyCRUD, ErpFamilyGrantCRUD, ErpFamilyMemberCRUD
from .model import ErpFamilyGrantModel, ErpFamilyMemberModel, ErpFamilyModel
from .schema import (
    ErpFamilyAdminUpdateSchema,
    ErpFamilyBriefSchema,
    ErpFamilyCreateSchema,
    ErpFamilyOutSchema,
    ErpFamilyQueryParam,
    ErpFamilyUpdateSchema,
    ErpGrantAdminCreateSchema,
    ErpGrantCreateSchema,
    ErpGrantOutSchema,
    ErpGrantQueryParam,
    ErpMemberHandleSchema,
    ErpMemberInviteSchema,
    ErpMemberJoinSchema,
    ErpMemberOutSchema,
    ErpMemberQueryParam,
    ErpMemberSelfUpdateSchema,
    ErpMemberUpdateSchema,
    is_expired,
)

# 邀请码字符集：去掉 0/O/1/I 这些肉眼难分辨的字符，方便家人电话里口述
_INVITE_CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def generate_invite_code(length: int = 8) -> str:
    """生成家庭邀请码（大写字母数字，无易混字符）。"""
    return "".join(secrets.choice(_INVITE_CODE_ALPHABET) for _ in range(length))


class ErpFamilyPortalService:
    """C端家庭门户服务 —— 不依赖 X-Family-Id 的操作"""

    def __init__(self, ctx: AppAuthContext) -> None:
        """初始化。

        参数:
        - ctx (AppAuthContext): C端登录上下文。
        """
        self.ctx = ctx
        self.user_id = ctx.user_id
        self.db = ctx.db
        self.auth = auth_schema()
        self.families = ErpFamilyCRUD(self.auth, ctx.db)
        self.members = ErpFamilyMemberCRUD(self.auth, ctx.db)
        self.app_users = AppUserCRUD(self.auth, ctx.db)

    # ── 查询 ──────────────────────────────────────────────────────────

    async def my_families(self) -> list[ErpFamilyBriefSchema]:
        """列出我已加入的家庭（用于 App 顶部的家庭切换器）。"""
        records = await self.members.list_by_user(self.user_id, status=ErpMemberStatus.ACTIVE.value)
        if not records:
            return []
        return await self._assemble_brief(records)

    async def pending_invites(self) -> list[ErpMemberOutSchema]:
        """列出待我确认的定向邀请。"""
        records = await self.members.list_by_user(self.user_id, status=ErpMemberStatus.PENDING.value)
        if not records:
            return []
        families = await self.families.get_list(search={"id": ("in", [item.family_id for item in records])})
        family_map = {item.id: item for item in families}
        result: list[ErpMemberOutSchema] = []
        for record in records:
            out = ErpMemberOutSchema.model_validate(record)
            family = family_map.get(record.family_id)
            # 家庭可能已被解散，这类邀请直接跳过，避免用户点了才发现无效
            if family and family.status == 0 and not family.is_deleted:
                result.append(out)
        return result

    # ── 创建与加入 ────────────────────────────────────────────────────

    async def create(self, data: ErpFamilyCreateSchema) -> ErpFamilyOutSchema:
        """创建家庭，创建者自动成为户主并直接生效。"""
        payload: dict[str, Any] = data.model_dump(exclude_none=True)
        payload["owner_id"] = self.user_id
        payload["member_limit"] = FAMILY_MEMBER_MAX
        payload["invite_code"] = await self._unique_invite_code()

        family = await self.families.create(data=payload)
        await self.members.create(
            data={
                "family_id": family.id,
                "user_id": self.user_id,
                "role": ErpFamilyRole.OWNER.value,
                "status": ErpMemberStatus.ACTIVE.value,
                "nickname": None,
                "joined_time": datetime.now(UTC),
            }
        )
        logger.info(f"创建家庭: family_id={family.id}, owner_id={self.user_id}")
        return await self._family_out(family, member_count=1, my_role=ErpFamilyRole.OWNER.value)

    async def join(self, data: ErpMemberJoinSchema) -> ErpFamilyBriefSchema:
        """凭邀请码加入家庭（加入即生效，无需户主二次确认）。"""
        family = await self.families.get_by_invite_code(data.invite_code)
        if not family:
            raise BusinessError(msg="邀请码无效，请向户主确认")
        if family.status != 0:
            raise BusinessError(msg="该家庭已停用，无法加入", status_code=403)

        await self._ensure_can_join(family)
        record = await self._activate_or_create_member(
            family_id=family.id,
            role=ErpFamilyRole.MEMBER.value,
            nickname=data.nickname,
        )
        logger.info(f"凭邀请码加入家庭: family_id={family.id}, user_id={self.user_id}")
        return await self._brief_one(record, family)

    async def handle_invite(self, member_id: int, data: ErpMemberHandleSchema) -> None:
        """接受或拒绝定向邀请（只能处理自己的邀请）。"""
        record = await self.members.get(id=member_id)
        if not record or record.user_id != self.user_id:
            raise BusinessError(msg="邀请不存在", status_code=404)
        if record.status != ErpMemberStatus.PENDING.value:
            raise BusinessError(msg="该邀请已处理，无需重复操作", status_code=409)

        family = await self.families.get(id=record.family_id)
        if not family or family.status != 0:
            raise BusinessError(msg="该家庭已解散或停用，邀请失效", status_code=403)

        if data.accept:
            await self._ensure_can_join(family)
            await self.members.set(
                ids=[record.id],
                status=ErpMemberStatus.ACTIVE.value,
                joined_time=datetime.now(UTC),
            )
            logger.info(f"接受家庭邀请: family_id={family.id}, user_id={self.user_id}")
        else:
            await self.members.set(ids=[record.id], status=ErpMemberStatus.REJECTED.value)
            logger.info(f"拒绝家庭邀请: family_id={family.id}, user_id={self.user_id}")

    async def quit(self, family_id: int) -> None:
        """退出家庭。

        户主不能直接退出：家庭数据（物品、批次、授权）都以家庭为主体，
        户主一走就没人能管理。必须先转让户主或解散家庭。
        """
        record = await self.members.get_member(family_id, self.user_id)
        if not record or record.status != ErpMemberStatus.ACTIVE.value:
            raise BusinessError(msg="您不是该家庭的成员", status_code=403)
        if record.role == ErpFamilyRole.OWNER.value:
            raise BusinessError(msg="户主不能直接退出，请先转让户主或解散家庭", status_code=403)

        await self.members.set(ids=[record.id], status=ErpMemberStatus.REMOVED.value)
        logger.info(f"退出家庭: family_id={family_id}, user_id={self.user_id}")

    # ── 内部方法 ──────────────────────────────────────────────────────

    async def _ensure_can_join(self, family: ErpFamilyModel) -> None:
        """校验家庭是否还能接收新成员。"""
        count = await self.members.count_active_members(family.id)
        if count >= (family.member_limit or FAMILY_MEMBER_MAX):
            raise BusinessError(msg="该家庭成员已满，请联系户主调整上限", status_code=409)

    async def _unique_invite_code(self) -> str:
        """生成不重复的邀请码。

        34^8 ≈ 1.8万亿 的空间下碰撞概率极低，但仍做有限次重试兜底；
        连续 10 次都撞上说明库里有异常数据，直接报错而不是死循环。
        """
        for _ in range(10):
            code = generate_invite_code()
            if not await self.families.get(invite_code=code, include_deleted=True):
                return code
        raise BusinessError(msg="邀请码生成失败，请重试")

    async def _activate_or_create_member(self, *, family_id: int, role: str, nickname: str | None) -> ErpFamilyMemberModel:
        """把成员记录置为已加入；不存在则新建，已存在（曾退出/被移除）则复用原记录。

        复用而非新建，是为了让历史物品上的「录入人」始终指向同一条成员记录，
        追溯链条不会因为一次退出再加入而断掉。
        """
        record = await self.members.get_member(family_id, self.user_id, include_deleted=True)
        if record:
            values: dict[str, Any] = {
                "status": ErpMemberStatus.ACTIVE.value,
                "role": role,
                "joined_time": datetime.now(UTC),
                "is_deleted": False,
                "deleted_time": None,
            }
            if nickname:
                values["nickname"] = nickname.strip()
            await self.members.set(ids=[record.id], include_deleted=True, **values)
            updated = await self.members.get(id=record.id)
            return updated or record

        return await self.members.create(
            data={
                "family_id": family_id,
                "user_id": self.user_id,
                "role": role,
                "status": ErpMemberStatus.ACTIVE.value,
                "nickname": nickname.strip() if nickname else None,
                "joined_time": datetime.now(UTC),
            }
        )

    async def _assemble_brief(self, records: Sequence[ErpFamilyMemberModel]) -> list[ErpFamilyBriefSchema]:
        """把成员记录批量组装成家庭精简信息（两条 SQL 搞定，避免 N+1）。"""
        family_ids = [item.family_id for item in records]
        families = await self.families.get_list(search={"id": ("in", family_ids)})
        family_map = {item.id: item for item in families}
        counts = await self.members.count_active_members_batch(family_ids)

        result: list[ErpFamilyBriefSchema] = []
        for record in records:
            family = family_map.get(record.family_id)
            if not family or family.is_deleted:
                continue
            result.append(
                ErpFamilyBriefSchema(
                    id=family.id,
                    name=family.name,
                    avatar=family.avatar,
                    my_role=record.role,
                    my_nickname=record.nickname,
                    member_count=counts.get(family.id, 0),
                    status=family.status,
                )
            )
        return result

    async def _brief_one(self, record: ErpFamilyMemberModel, family: ErpFamilyModel) -> ErpFamilyBriefSchema:
        """单个家庭加入成功后的响应。"""
        count = await self.members.count_active_members(family.id)
        return ErpFamilyBriefSchema(
            id=family.id,
            name=family.name,
            avatar=family.avatar,
            my_role=record.role,
            my_nickname=record.nickname,
            member_count=count,
            status=family.status,
        )

    async def _family_out(self, family: ErpFamilyModel, *, member_count: int, my_role: str) -> ErpFamilyOutSchema:
        """组装家庭详情响应（含成员数、我的角色、户主昵称）。"""
        out = ErpFamilyOutSchema.model_validate(family)
        out.member_count = member_count
        out.my_role = my_role
        owner = await self.app_users.get(id=family.owner_id)
        out.owner_name = (owner.nickname or owner.username) if owner else None
        return out


class ErpFamilyService:
    """C端家庭内服务 —— 所有方法都基于已鉴权的 FamilyContext"""

    def __init__(self, ctx: FamilyContext) -> None:
        """初始化。

        参数:
        - ctx (FamilyContext): 家庭上下文（已完成登录、成员关系与角色校验）。
        """
        self.ctx = ctx
        self.family = ctx.family
        self.member = ctx.member
        self.db = ctx.db
        self.auth = auth_schema()
        self.families = ErpFamilyCRUD(self.auth, ctx.db)
        self.members = ErpFamilyMemberCRUD(self.auth, ctx.db)
        self.grants = ErpFamilyGrantCRUD(self.auth, ctx.db)
        self.app_users = AppUserCRUD(self.auth, ctx.db)

    # ── 家庭资料 ──────────────────────────────────────────────────────

    async def detail(self) -> ErpFamilyOutSchema:
        """获取当前家庭详情。"""
        count = await self.members.count_active_members(self.family.id)
        return await self._family_out(self.family, member_count=count, my_role=self.member.role)

    async def update(self, data: ErpFamilyUpdateSchema) -> ErpFamilyOutSchema:
        """修改家庭资料（管理员及以上）。"""
        self.ctx.require(ErpFamilyRole.ADMIN)
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        if not changes:
            raise BusinessError(msg="没有需要修改的内容")
        family = await self.families.update(id=self.family.id, data=data)
        count = await self.members.count_active_members(family.id)
        return await self._family_out(family, member_count=count, my_role=self.member.role)

    async def refresh_invite_code(self) -> str:
        """重置邀请码（管理员及以上）。旧码立即失效，用于邀请码泄露后止血。"""
        self.ctx.require(ErpFamilyRole.ADMIN)
        for _ in range(10):
            code = generate_invite_code()
            if not await self.families.get(invite_code=code, include_deleted=True):
                break
        else:
            raise BusinessError(msg="邀请码生成失败，请重试")
        await self.families.set(ids=[self.family.id], invite_code=code)
        logger.info(f"重置家庭邀请码: family_id={self.family.id}, operator={self.ctx.user_id}")
        return code

    async def dissolve(self) -> None:
        """解散家庭（仅户主）。

        软删除家庭与全部成员记录，共享授权一并撤销 —— 授权记录留着的话，
        受权方仍可能查到这个家庭的历史数据，属于越权。
        """
        self.ctx.require(ErpFamilyRole.OWNER)
        member_ids = [item.id for item in await self.members.list_members(self.family.id)]
        if member_ids:
            await self.members.delete(ids=member_ids)
        for grant in await self.grants.list_granted_by(self.family.id):
            await self.grants.mark_revoked(grant.id)
        for grant in await self.grants.list_granted_to(self.family.id):
            await self.grants.mark_revoked(grant.id)
        await self.families.delete(ids=[self.family.id])
        logger.warning(f"解散家庭: family_id={self.family.id}, operator={self.ctx.user_id}")

    # ── 成员管理 ──────────────────────────────────────────────────────

    async def member_list(self, status: int | None = None) -> list[ErpMemberOutSchema]:
        """列出家庭成员（默认只看已加入的）。"""
        records = await self.members.list_members(self.family.id, status=status if status is not None else ErpMemberStatus.ACTIVE.value)
        return await self._members_out(records)

    async def invite(self, data: ErpMemberInviteSchema) -> ErpMemberOutSchema:
        """定向邀请成员（管理员及以上），生成待确认记录等对方接受。"""
        self.ctx.require(ErpFamilyRole.ADMIN)
        target = await self._resolve_invite_target(data)
        if target.id == self.ctx.user_id:
            raise BusinessError(msg="不能邀请自己")

        member_count = await self.members.count_active_members(self.family.id)
        if member_count >= (self.family.member_limit or FAMILY_MEMBER_MAX):
            raise BusinessError(msg="家庭成员已满，无法继续邀请", status_code=409)

        # 户主唯一：即使传入 role=owner 也只能落到 admin，转让户主走 transfer_owner
        role = ErpFamilyRole.ADMIN.value if data.role == ErpFamilyRole.OWNER.value else data.role

        record = await self.members.get_member(self.family.id, target.id, include_deleted=True)
        if record and record.status == ErpMemberStatus.ACTIVE.value:
            raise BusinessError(msg="该用户已是家庭成员", status_code=409)
        if record and record.status == ErpMemberStatus.PENDING.value:
            # 已有待确认邀请：更新角色与称呼即可，重复插入会让对方看到两条一样的邀请
            await self.members.set(ids=[record.id], role=role, nickname=(data.nickname or record.nickname), is_deleted=False, deleted_time=None)
            refreshed = await self.members.get(id=record.id)
            record = refreshed or record
        elif record:
            await self.members.set(
                ids=[record.id],
                role=role,
                nickname=data.nickname,
                status=ErpMemberStatus.PENDING.value,
                is_deleted=False,
                deleted_time=None,
            )
            refreshed = await self.members.get(id=record.id)
            record = refreshed or record
        else:
            record = await self.members.create(
                data={
                    "family_id": self.family.id,
                    "user_id": target.id,
                    "role": role,
                    "status": ErpMemberStatus.PENDING.value,
                    "nickname": data.nickname,
                }
            )
        logger.info(f"邀请成员: family_id={self.family.id}, target={target.id}, role={role}, operator={self.ctx.user_id}")
        return (await self._members_out([record]))[0]

    async def update_member(self, member_id: int, data: ErpMemberUpdateSchema) -> ErpMemberOutSchema:
        """修改成员角色或称呼（管理员及以上；改角色仅户主可操作）。"""
        record = await self._get_member_or_raise(member_id)
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        if not changes:
            raise BusinessError(msg="没有需要修改的内容")

        if "role" in changes:
            self.ctx.require(ErpFamilyRole.OWNER)
            if record.role == ErpFamilyRole.OWNER.value:
                raise BusinessError(msg="不能修改户主的角色，请使用转让户主", status_code=403)
            if changes["role"] == ErpFamilyRole.OWNER.value:
                raise BusinessError(msg="户主只能通过转让产生", status_code=403)
        else:
            self.ctx.require(ErpFamilyRole.ADMIN)

        if record.status != ErpMemberStatus.ACTIVE.value:
            raise BusinessError(msg="该成员尚未加入或已退出，无法修改", status_code=409)

        updated = await self.members.update(id=member_id, data=data)
        logger.info(f"修改成员: family_id={self.family.id}, member_id={member_id}, changes={changes}, operator={self.ctx.user_id}")
        return (await self._members_out([updated]))[0]

    async def update_my_nickname(self, data: ErpMemberSelfUpdateSchema) -> ErpMemberOutSchema:
        """成员自助修改自己在家庭内的称呼。"""
        nickname = (data.nickname or "").strip()
        if not nickname:
            raise BusinessError(msg="称呼不能为空")
        await self.members.set(ids=[self.member.id], nickname=nickname)
        record = await self.members.get(id=self.member.id)
        return (await self._members_out([record or self.member]))[0]

    async def remove_member(self, member_id: int) -> None:
        """移除成员（管理员及以上）。

        规则：不能移除户主；管理员只能移除普通成员/只读成员，不能移除其他管理员。
        移除是改状态而非删除记录，物品上的录入人仍可追溯。
        """
        self.ctx.require(ErpFamilyRole.ADMIN)
        record = await self._get_member_or_raise(member_id)
        if record.user_id == self.ctx.user_id:
            raise BusinessError(msg="不能移除自己，请使用退出家庭")
        if record.role == ErpFamilyRole.OWNER.value:
            raise BusinessError(msg="不能移除户主", status_code=403)
        target_role = _to_role(record.role)
        if target_role.weight >= self.ctx.role.weight:
            raise BusinessError(msg="不能移除与自己同级或更高级别的成员", status_code=403)

        await self.members.set(ids=[record.id], status=ErpMemberStatus.REMOVED.value)
        logger.info(f"移除成员: family_id={self.family.id}, member_id={member_id}, operator={self.ctx.user_id}")

    async def transfer_owner(self, user_id: int) -> None:
        """转让户主（仅户主）。原户主降级为管理员，家庭数据归属不变。"""
        self.ctx.require(ErpFamilyRole.OWNER)
        if user_id == self.ctx.user_id:
            raise BusinessError(msg="您已经是户主", status_code=409)
        target = await self.members.get_member(self.family.id, user_id)
        if not target or target.status != ErpMemberStatus.ACTIVE.value:
            raise BusinessError(msg="目标用户不是该家庭的有效成员")

        await self.members.set(ids=[target.id], role=ErpFamilyRole.OWNER.value)
        await self.members.set(ids=[self.member.id], role=ErpFamilyRole.ADMIN.value)
        await self.families.set(ids=[self.family.id], owner_id=user_id)
        logger.warning(f"转让户主: family_id={self.family.id}, from={self.ctx.user_id}, to={user_id}")

    # ── 共享授权 ──────────────────────────────────────────────────────

    async def grant_list(self) -> list[ErpGrantOutSchema]:
        """列出与当前家庭相关的全部授权（我授出的 + 授给我的）。"""
        granted_by = list(await self.grants.list_granted_by(self.family.id))
        granted_to = list(await self.grants.list_granted_to(self.family.id))
        return await self._grants_out([*granted_by, *granted_to])

    async def create_grant(self, data: ErpGrantCreateSchema) -> ErpGrantOutSchema:
        """户主授权其他家庭只读查看本家庭数据。

        仅限户主：共享出去的是全家的物资（可能含药品、母婴用品等隐私信息），
        管理员也不应有权决定。
        """
        self.ctx.require(ErpFamilyRole.OWNER)
        if data.target_family_id == self.family.id:
            raise BusinessError(msg="不能授权给自己所在的家庭", status_code=403)

        target = await self.families.get(id=data.target_family_id)
        if not target:
            raise BusinessError(msg="目标家庭不存在", status_code=404)
        if target.status != 0:
            raise BusinessError(msg="目标家庭已停用，无法授权", status_code=403)
        if data.expire_time and is_expired(data.expire_time):
            raise BusinessError(msg="到期时间必须晚于当前时间")

        existing = await self.grants.get_active_grant(self.family.id, data.target_family_id)
        if existing:
            # 已有生效授权：覆盖到期时间与原因，而不是插第二条 —— 两条同时生效时
            # 「是否可见」的判断会变得含糊，撤销也只能撤掉其中一条。
            await self.grants.update(
                id=existing.id,
                data={
                    "expire_time": data.expire_time,
                    "reason": data.reason,
                    "granted_by": self.ctx.user_id,
                    "source": ErpGrantSource.FAMILY.value,
                },
            )
            refreshed = await self.grants.get(id=existing.id)
            grant = refreshed or existing
        else:
            grant = await self.grants.create(
                data={
                    "family_id": self.family.id,
                    "target_family_id": data.target_family_id,
                    "source": ErpGrantSource.FAMILY.value,
                    "granted_by": self.ctx.user_id,
                    "expire_time": data.expire_time,
                    "reason": data.reason,
                    "status": ErpGrantStatus.ACTIVE.value,
                }
            )
        logger.info(f"户主授权共享: family_id={self.family.id}, target={data.target_family_id}, operator={self.ctx.user_id}")
        return (await self._grants_out([grant]))[0]

    async def revoke_grant(self, grant_id: int) -> None:
        """撤销户主自助授权。后台强制授权（source=admin）不允许户主自行撤销。"""
        self.ctx.require(ErpFamilyRole.OWNER)
        grant = await self.grants.get(id=grant_id)
        if not grant or grant.family_id != self.family.id:
            raise BusinessError(msg="授权记录不存在", status_code=404)
        if grant.source == ErpGrantSource.ADMIN.value:
            raise BusinessError(msg="该授权由后台运营设置，无法自行撤销，请联系客服", status_code=403)
        if grant.status != ErpGrantStatus.ACTIVE.value:
            raise BusinessError(msg="该授权已撤销", status_code=409)

        await self.grants.mark_revoked(grant.id)
        logger.info(f"撤销共享授权: grant_id={grant.id}, family_id={self.family.id}, operator={self.ctx.user_id}")

    async def visible_family_ids(self) -> list[int]:
        """返回当前家庭可查看数据的家庭ID集合（自身 + 授权给我的）。

        P1 起的物品查询统一用它构造 ``family_id IN (...)`` 条件，
        配合 ``erp_item.family_id`` 索引先收敛行集，再算 JSON 属性表达式。
        """
        granted = await self.grants.list_active_family_ids_for(self.family.id)
        return [self.family.id, *granted]

    # ── 内部方法 ──────────────────────────────────────────────────────

    async def _get_member_or_raise(self, member_id: int) -> ErpFamilyMemberModel:
        """取本家庭的成员记录，不存在或不属于本家庭则抛异常。"""
        record = await self.members.get(id=member_id)
        if not record or record.family_id != self.family.id:
            raise BusinessError(msg="成员不存在", status_code=404)
        return record

    async def _resolve_invite_target(self, data: ErpMemberInviteSchema) -> AppUserModel:
        """把邀请参数（user_id 或 mobile）解析成 C端用户。"""
        if data.user_id:
            user = await self.app_users.get(id=data.user_id)
            if not user:
                raise BusinessError(msg="被邀请的用户不存在", status_code=404)
            if user.status == 1:
                raise BusinessError(msg="被邀请的用户已被禁用", status_code=403)
            return user

        user = await self.app_users.get(mobile=data.mobile)
        if not user:
            # 不自动注册：手机号输错就会凭空造出一个账号，且被邀请方毫不知情
            raise BusinessError(msg="该手机号尚未注册，请让对方先注册后再邀请", status_code=404)
        if user.status == 1:
            raise BusinessError(msg="被邀请的用户已被禁用", status_code=403)
        return user

    async def _family_out(self, family: ErpFamilyModel, *, member_count: int, my_role: str) -> ErpFamilyOutSchema:
        """组装家庭详情响应。"""
        out = ErpFamilyOutSchema.model_validate(family)
        out.member_count = member_count
        out.my_role = my_role
        owner = await self.app_users.get(id=family.owner_id)
        out.owner_name = (owner.nickname or owner.username) if owner else None
        return out

    async def _members_out(self, records: Sequence[ErpFamilyMemberModel]) -> list[ErpMemberOutSchema]:
        """批量组装成员响应（一次查出全部关联用户，避免 N+1）。"""
        if not records:
            return []
        user_ids = list({item.user_id for item in records})
        users = await self.app_users.get_list(search={"id": ("in", user_ids)})
        user_map = {item.id: item for item in users}

        result: list[ErpMemberOutSchema] = []
        for record in records:
            out = ErpMemberOutSchema.model_validate(record)
            user = user_map.get(record.user_id)
            if user:
                out.username = user.username
                out.user_nickname = user.nickname
                out.avatar = user.avatar
                out.mobile = user.mobile
            result.append(out)
        return result

    async def _grants_out(self, records: Sequence[ErpFamilyGrantModel]) -> list[ErpGrantOutSchema]:
        """批量组装授权响应，并标注当前家庭是否有权撤销。"""
        if not records:
            return []
        family_ids = list({item.family_id for item in records} | {item.target_family_id for item in records})
        families = await self.families.get_list(search={"id": ("in", family_ids)})
        name_map = {item.id: item.name for item in families}

        result: list[ErpGrantOutSchema] = []
        for record in records:
            out = ErpGrantOutSchema.model_validate(record)
            out.family_name = name_map.get(record.family_id)
            out.target_family_name = name_map.get(record.target_family_id)
            # 只有「我是授权方 + 来源是户主自助 + 仍生效」才可撤销
            out.revocable = record.family_id == self.family.id and record.source == ErpGrantSource.FAMILY.value and record.status == ErpGrantStatus.ACTIVE.value
            result.append(out)
        return result


class ErpFamilyAdminService:
    """后台家庭管理服务（运营视角）"""

    def __init__(self, auth: AuthSchema, db: AsyncSession, redis: Redis) -> None:
        """初始化。

        参数:
        - auth (AuthSchema): 后台认证上下文（由 ``AuthPermission`` 注入）。
        - db (AsyncSession): 数据库会话。
        - redis (Redis): Redis 连接。
        """
        self.auth = auth
        self.db = db
        self.redis = redis
        self.families = ErpFamilyCRUD(auth, db)
        self.members = ErpFamilyMemberCRUD(auth, db)
        self.grants = ErpFamilyGrantCRUD(auth, db)
        self.app_users = AppUserCRUD(auth, db)

    # ── 家庭 ──────────────────────────────────────────────────────────

    async def page(
        self,
        page_no: int,
        page_size: int,
        search: ErpFamilyQueryParam | None = None,
        order_by: list[dict[str, str]] | None = None,
    ) -> PageResultSchema[ErpFamilyOutSchema]:
        """分页查询家庭。"""
        offset = (page_no - 1) * page_size
        result = await self.families.page(
            offset=offset,
            limit=page_size,
            order_by=order_by or [{"id": "desc"}],
            search=search_to_dict(search, {}),
            out_schema=ErpFamilyOutSchema,
        )
        # 分页结果里逐条补成员数与户主昵称：一页最多 100 条，批量查询两次即可
        family_ids = [item.id for item in result.items if item.id]
        counts = await self.members.count_active_members_batch(family_ids)
        owners = await self._owner_name_map([item.owner_id for item in result.items if item.owner_id])
        for item in result.items:
            item.member_count = counts.get(item.id or 0, 0)
            item.owner_name = owners.get(item.owner_id or 0)
        return result

    async def detail(self, id: int) -> ErpFamilyOutSchema:
        """获取家庭详情（含成员与授权概览）。"""
        family = await self._get_family_or_raise(id)
        out = ErpFamilyOutSchema.model_validate(family)
        out.member_count = await self.members.count_active_members(id)
        owner = await self.app_users.get(id=family.owner_id)
        out.owner_name = (owner.nickname or owner.username) if owner else None
        return out

    async def update(self, id: int, data: ErpFamilyAdminUpdateSchema) -> ErpFamilyOutSchema:
        """后台修改家庭资料/成员上限/状态。"""
        await self._get_family_or_raise(id)
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        if not changes:
            raise BusinessError(msg="没有需要修改的内容")
        family = await self.families.update(id=id, data=data)
        out = ErpFamilyOutSchema.model_validate(family)
        out.member_count = await self.members.count_active_members(id)
        logger.info(f"后台修改家庭: family_id={id}, changes={changes}, operator={self._operator()}")
        return out

    async def delete(self, ids: list[int]) -> None:
        """后台删除家庭（软删除），同时清理成员与授权。"""
        if not ids:
            raise BusinessError(msg="删除失败，删除对象不能为空")
        objs = await self.families.get_list(search={"id": ("in", ids)})
        if len(objs) != len(set(ids)):
            raise BusinessError(msg="删除失败，部分家庭不存在", status_code=404)

        for family_id in ids:
            member_ids = [item.id for item in await self.members.list_members(family_id)]
            if member_ids:
                await self.members.delete(ids=member_ids)
            for grant in await self.grants.list_granted_by(family_id):
                await self.grants.mark_revoked(grant.id)
            for grant in await self.grants.list_granted_to(family_id):
                await self.grants.mark_revoked(grant.id)
        await self.families.delete(ids=ids)
        logger.warning(f"后台删除家庭: family_ids={ids}, operator={self._operator()}")

    async def set_available(self, data: BatchSetAvailable) -> None:
        """批量启用/停用家庭。停用后该家庭所有成员都无法通过 X-Family-Id 访问。"""
        if not data.ids:
            raise BusinessError(msg="操作失败，对象不能为空")
        await self.families.set(ids=data.ids, status=data.status)
        logger.info(f"后台批量修改家庭状态: ids={data.ids}, status={data.status}, operator={self._operator()}")

    # ── 成员 ──────────────────────────────────────────────────────────

    async def member_page(
        self,
        page_no: int,
        page_size: int,
        search: ErpMemberQueryParam | None = None,
        order_by: list[dict[str, str]] | None = None,
    ) -> PageResultSchema[ErpMemberOutSchema]:
        """分页查询家庭成员。"""
        offset = (page_no - 1) * page_size
        result = await self.members.page(
            offset=offset,
            limit=page_size,
            order_by=order_by or [{"id": "desc"}],
            search=search_to_dict(search, {}),
            out_schema=ErpMemberOutSchema,
        )
        users = await self.app_users.get_list(search={"id": ("in", [item.user_id for item in result.items if item.user_id])})
        user_map = {item.id: item for item in users}
        for item in result.items:
            user = user_map.get(item.user_id or 0)
            if user:
                item.username = user.username
                item.user_nickname = user.nickname
                item.avatar = user.avatar
                item.mobile = user.mobile
        return result

    async def remove_member(self, id: int) -> None:
        """后台移除成员（置为已移除，保留记录以便追溯）。"""
        record = await self.members.get(id=id)
        if not record:
            raise BusinessError(msg="成员不存在", status_code=404)
        if record.role == ErpFamilyRole.OWNER.value:
            raise BusinessError(msg="不能移除户主，请先在后台调整户主归属", status_code=403)
        await self.members.set(ids=[id], status=ErpMemberStatus.REMOVED.value)
        logger.info(f"后台移除家庭成员: member_id={id}, operator={self._operator()}")

    # ── 共享授权 ──────────────────────────────────────────────────────

    async def grant_page(
        self,
        page_no: int,
        page_size: int,
        search: ErpGrantQueryParam | None = None,
        order_by: list[dict[str, str]] | None = None,
    ) -> PageResultSchema[ErpGrantOutSchema]:
        """分页查询共享授权。"""
        offset = (page_no - 1) * page_size
        result = await self.grants.page(
            offset=offset,
            limit=page_size,
            order_by=order_by or [{"id": "desc"}],
            search=search_to_dict(search, {}),
            out_schema=ErpGrantOutSchema,
        )
        ids = {item.family_id for item in result.items if item.family_id} | {item.target_family_id for item in result.items if item.target_family_id}
        families = await self.families.get_list(search={"id": ("in", list(ids))}) if ids else []
        name_map = {item.id: item.name for item in families}
        for item in result.items:
            item.family_name = name_map.get(item.family_id or 0)
            item.target_family_name = name_map.get(item.target_family_id or 0)
            # 后台视角：任何生效中的授权都可以由运营撤销，因此 revocable 只看状态
            item.revocable = item.status == ErpGrantStatus.ACTIVE.value
        return result

    async def force_grant(self, data: ErpGrantAdminCreateSchema) -> ErpGrantOutSchema:
        """后台强制授权（source=admin），必须带到期时间，户主不可自行撤销。"""
        family = await self._get_family_or_raise(data.family_id)
        target = await self._get_family_or_raise(data.target_family_id)
        if family.id == target.id:
            raise BusinessError(msg="授权方与受权方不能是同一个家庭", status_code=403)

        existing = await self.grants.get_active_grant(family.id, target.id)
        payload: dict[str, Any] = {
            "family_id": family.id,
            "target_family_id": target.id,
            "source": ErpGrantSource.ADMIN.value,
            "granted_by": self._operator(),
            "expire_time": data.expire_time,
            "reason": data.reason,
            "status": ErpGrantStatus.ACTIVE.value,
        }
        if existing:
            # 已存在的授权一律升级为 admin 来源：强制授权的语义优先级高于户主自助，
            # 否则户主可以先撤掉自己那条，让后台的强制授权失去意义。
            await self.grants.update(id=existing.id, data=payload)
            grant = await self.grants.get(id=existing.id)
        else:
            grant = await self.grants.create(data=payload)

        logger.warning(f"后台强制授权共享: family_id={family.id}, target={target.id}, expire={data.expire_time}, operator={self._operator()}")
        out = ErpGrantOutSchema.model_validate(grant)
        out.family_name = family.name
        out.target_family_name = target.name
        out.revocable = True
        return out

    async def revoke_grant(self, id: int) -> None:
        """后台撤销授权（不限来源）。"""
        grant = await self.grants.get(id=id)
        if not grant:
            raise BusinessError(msg="授权记录不存在", status_code=404)
        if grant.status != ErpGrantStatus.ACTIVE.value:
            raise BusinessError(msg="该授权已撤销", status_code=409)
        await self.grants.mark_revoked(id)
        logger.info(f"后台撤销共享授权: grant_id={id}, operator={self._operator()}")

    # ── 内部方法 ──────────────────────────────────────────────────────

    async def _get_family_or_raise(self, id: int) -> ErpFamilyModel:
        """取家庭，不存在则抛业务异常。"""
        family = await self.families.get(id=id)
        if not family:
            raise BusinessError(msg="该家庭不存在", status_code=404)
        return family

    async def _owner_name_map(self, owner_ids: Sequence[int | None]) -> dict[int, str | None]:
        """批量取户主昵称，返回 {user_id: 展示名}。"""
        ids = list({item for item in owner_ids if item})
        if not ids:
            return {}
        users = await self.app_users.get_list(search={"id": ("in", ids)}, load_columns=[AppUserModel.id, AppUserModel.nickname, AppUserModel.username])
        return {user.id: (user.nickname or user.username) for user in users}

    def _operator(self) -> int | None:
        """当前后台操作人ID（写入日志与 granted_by）。"""
        return self.auth.user.id or None


def _to_role(value: str | None) -> ErpFamilyRole:
    """角色字符串转枚举，脏数据按最低权限处理。"""
    try:
        return ErpFamilyRole(value) if value else ErpFamilyRole.VIEWER
    except ValueError:
        return ErpFamilyRole.VIEWER
