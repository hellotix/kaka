"""C端用户管理服务层：后台管理 + C端自助。"""

from typing import Any

from redis.asyncio.client import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_schema import AuthSchema, BatchSetAvailable, PageResultSchema
from app.core.logger import logger
from app.utils.common_util import search_to_dict
from app.utils.password_util import PwdUtil

from ...exceptions import BusinessError
from ..auth.crud import AppLoginLogCRUD
from ..auth.schema import AppLoginLogOutSchema, AppLoginLogQueryParam
from ..auth.service import AppLoginService
from ..core.constants import AppRegisterType
from ..core.dependencies import AppAuthContext
from ..core.session import AppSessionInfo, AppSessionStore
from .crud import AppUserCRUD, AppUserOauthCRUD
from .model import AppUserModel
from .schema import (
    AppUserChangePasswordSchema,
    AppUserCreateSchema,
    AppUserOauthOutSchema,
    AppUserOutSchema,
    AppUserProfileUpdateSchema,
    AppUserQueryParam,
    AppUserResetPasswordSchema,
    AppUserUpdateSchema,
)


class AppUserService:
    """C端用户后台管理服务层"""

    def __init__(self, auth: AuthSchema, db: AsyncSession, redis: Redis) -> None:
        """初始化服务层

        参数:
        - auth (AuthSchema): 后台认证上下文
        - db (AsyncSession): 数据库会话
        - redis (Redis): Redis 连接
        """
        self.auth = auth
        self.db = db
        self.redis = redis
        self.users = AppUserCRUD(auth, db)
        self.oauths = AppUserOauthCRUD(auth, db)
        self.login_logs = AppLoginLogCRUD(auth, db)
        self.sessions = AppSessionStore(redis)

    # ── 查询 ──────────────────────────────────────────────────────────

    async def detail(self, id: int) -> AppUserOutSchema:
        """获取C端用户详情。"""
        obj = await self.users.get(id=id)
        if not obj:
            raise BusinessError(msg="该用户不存在", status_code=404)
        return AppUserOutSchema.model_validate(obj)

    async def get_list(
        self,
        search: AppUserQueryParam | None = None,
        order_by: list[dict[str, str]] | None = None,
    ) -> list[AppUserOutSchema]:
        """获取C端用户列表（不分页）。"""
        obj_list = await self.users.get_list(search=search_to_dict(search), order_by=order_by)
        return [AppUserOutSchema.model_validate(obj) for obj in obj_list]

    async def page(
        self,
        page_no: int,
        page_size: int,
        search: AppUserQueryParam | None = None,
        order_by: list[dict[str, str]] | None = None,
    ) -> PageResultSchema[AppUserOutSchema]:
        """分页查询C端用户。"""
        offset = (page_no - 1) * page_size
        return await self.users.page(
            offset=offset,
            limit=page_size,
            order_by=order_by or [{"id": "desc"}],
            search=search_to_dict(search, {}),
            out_schema=AppUserOutSchema,
        )

    async def login_log_page(
        self,
        page_no: int,
        page_size: int,
        search: AppLoginLogQueryParam | None = None,
        order_by: list[dict[str, str]] | None = None,
    ) -> PageResultSchema[AppLoginLogOutSchema]:
        """分页查询C端登录日志。"""
        offset = (page_no - 1) * page_size
        return await self.login_logs.page(
            offset=offset,
            limit=page_size,
            order_by=order_by or [{"id": "desc"}],
            search=search_to_dict(search, {}),
            out_schema=AppLoginLogOutSchema,
        )

    async def oauth_list(self, id: int) -> list[AppUserOauthOutSchema]:
        """查询C端用户的第三方登录绑定。"""
        await self._get_or_raise(id)
        objs = await self.oauths.get_list(search={"user_id": id}, order_by=[{"id": "asc"}])
        return [AppUserOauthOutSchema.model_validate(obj) for obj in objs]

    # ── 写入 ──────────────────────────────────────────────────────────

    async def create(self, data: AppUserCreateSchema) -> AppUserOutSchema:
        """后台创建C端用户（密码自动哈希）。"""
        payload: dict[str, Any] = data.model_dump(exclude_none=True)
        password = payload.pop("password", None)
        if not (payload.get("username") or payload.get("mobile")):
            raise BusinessError(msg="创建失败，用户名与手机号至少填写一项")

        await self._ensure_unique(
            username=payload.get("username"),
            mobile=payload.get("mobile"),
            email=payload.get("email"),
        )

        if password:
            payload["password"] = PwdUtil.hash_password(password)
        payload["register_type"] = AppRegisterType.ADMIN.value
        payload.setdefault("nickname", "")

        obj = await self.users.create(data=payload)
        return AppUserOutSchema.model_validate(obj)

    async def update(self, id: int, data: AppUserUpdateSchema) -> AppUserOutSchema:
        """后台修改C端用户资料。"""
        obj = await self._get_or_raise(id)
        changes = data.model_dump(exclude_unset=True, exclude_none=True)

        await self._ensure_unique(
            exclude_id=id,
            username=changes.get("username"),
            mobile=changes.get("mobile"),
            email=changes.get("email"),
        )

        obj = await self.users.update(id=id, data=data)
        # 禁用后立刻下线，避免旧令牌继续可用
        if changes.get("status") == 1:
            await self.sessions.remove_by_user(id)
        else:
            await self._sync_session_info(obj)
        return AppUserOutSchema.model_validate(obj)

    async def delete(self, ids: list[int]) -> None:
        """删除C端用户（软删除）并强制下线全部会话。"""
        if not ids:
            raise BusinessError(msg="删除失败，删除对象不能为空")
        objs = await self.users.get_list(search={"id": ("in", ids)})
        obj_map = {o.id: o for o in objs}
        for id_ in ids:
            if id_ not in obj_map:
                raise BusinessError(msg="删除失败，该用户不存在", status_code=404)

        await self.users.delete(ids=ids)
        for id_ in ids:
            await self.sessions.remove_by_user(id_)

    async def set_available(self, data: BatchSetAvailable) -> None:
        """批量启用/禁用C端用户，禁用时强制下线。"""
        if not data.ids:
            raise BusinessError(msg="操作失败，对象不能为空")
        await self.users.set(ids=data.ids, status=data.status)
        if data.status == 1:
            for id_ in data.ids:
                await self.sessions.remove_by_user(id_)

    async def reset_password(self, id: int, data: AppUserResetPasswordSchema) -> None:
        """后台重置C端用户密码，成功后全端下线。"""
        await self._get_or_raise(id)
        await self.users.set(ids=[id], password=PwdUtil.hash_password(data.password))
        await self.sessions.remove_by_user(id)
        logger.info(f"后台重置C端用户密码: user_id={id}, operator={self.auth.user.id if self.auth.user else None}")

    async def unbind_oauth(self, id: int) -> None:
        """解绑C端用户的第三方登录。"""
        obj = await self.oauths.get(id=id)
        if not obj:
            raise BusinessError(msg="解绑失败，该绑定不存在", status_code=404)
        await self.oauths.delete(ids=[id])

    # ── 会话 ──────────────────────────────────────────────────────────

    async def list_sessions(self, id: int) -> list[AppSessionInfo]:
        """查询C端用户在线会话（多端登录列表）。"""
        await self._get_or_raise(id)
        return await self.sessions.list_by_user(id)

    async def force_logout(self, id: int, session_id: str | None = None) -> int:
        """后台强制下线：不传 session_id 则下线该用户全部会话。

        返回:
        - int: 实际下线的会话数量。
        """
        await self._get_or_raise(id)
        if session_id:
            info = await self.sessions.get(session_id)
            if not info:
                raise BusinessError(msg="会话不存在或已下线", status_code=404)
            if info.user_id != id:
                raise BusinessError(msg="该会话不属于此用户", status_code=403)
            await self.sessions.remove(session_id)
            return 1
        return await self.sessions.remove_by_user(id)

    # ── 内部方法 ──────────────────────────────────────────────────────

    async def _get_or_raise(self, id: int) -> AppUserModel:
        """取用户，不存在则抛业务异常。"""
        obj = await self.users.get(id=id)
        if not obj:
            raise BusinessError(msg="该用户不存在", status_code=404)
        return obj

    async def _ensure_unique(
        self,
        *,
        exclude_id: int | None = None,
        username: str | None = None,
        mobile: str | None = None,
        email: str | None = None,
    ) -> None:
        """校验用户名/手机号/邮箱唯一（未删除数据范围内）。"""
        for field, value, label in (
            ("username", username, "用户名"),
            ("mobile", mobile, "手机号"),
            ("email", email, "邮箱"),
        ):
            if not value:
                continue
            exists = await self.users.get(**{field: value})
            if exists and exists.id != exclude_id:
                raise BusinessError(msg=f"{label}已被占用", status_code=409)

    async def _sync_session_info(self, user: AppUserModel) -> None:
        """资料变更后同步在线会话中的展示信息。"""
        for info in await self.sessions.list_by_user(user.id):
            info.nickname = user.nickname
            info.avatar = user.avatar
            info.mobile = user.mobile
            info.username = user.username
            await self.sessions.update_info(info)


class AppUserProfileService:
    """C端用户自助服务层（个人中心）"""

    def __init__(self, ctx: AppAuthContext) -> None:
        """初始化服务层

        参数:
        - ctx (AppAuthContext): C端登录上下文。
        """
        self.ctx = ctx
        self.db = ctx.db
        self.users = AppUserCRUD(AuthSchema(), ctx.db)
        self.oauths = AppUserOauthCRUD(AuthSchema(), ctx.db)
        self.sessions = AppSessionStore(ctx.redis)
        self.login = AppLoginService(ctx.db, ctx.redis)

    async def profile(self) -> AppUserOutSchema:
        """获取当前登录用户资料。"""
        return AppUserOutSchema.model_validate(self.ctx.user)

    async def update_profile(self, data: AppUserProfileUpdateSchema) -> AppUserOutSchema:
        """修改当前登录用户资料。"""
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        if not changes:
            raise BusinessError(msg="没有需要修改的内容")
        if changes.get("email"):
            exists = await self.users.get(email=changes["email"])
            if exists and exists.id != self.ctx.user_id:
                raise BusinessError(msg="该邮箱已被其他账号使用", status_code=409)

        obj = await self.users.update(id=self.ctx.user_id, data=data)

        info = await self.sessions.get(self.ctx.session_id)
        if info:
            info.nickname = obj.nickname
            info.avatar = obj.avatar
            await self.sessions.update_info(info)
        return AppUserOutSchema.model_validate(obj)

    async def change_password(self, data: AppUserChangePasswordSchema) -> None:
        """修改当前登录用户密码，成功后下线其他会话。"""
        await self.login.change_password(
            self.ctx.user,
            old_password=data.old_password,
            new_password=data.new_password,
            current_session_id=self.ctx.session_id,
        )

    async def oauth_list(self) -> list[AppUserOauthOutSchema]:
        """获取当前登录用户的第三方绑定列表。"""
        objs = await self.oauths.get_list(search={"user_id": self.ctx.user_id}, order_by=[{"id": "asc"}])
        return [AppUserOauthOutSchema.model_validate(obj) for obj in objs]
