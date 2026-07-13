import json
import uuid
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, NewType

import ua_parser
from fastapi import BackgroundTasks, Request
from redis.asyncio.client import Redis
from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.module_platform.package.model import PackageMenuModel, PackageModel
from app.api.v1.module_platform.tenant.model import TenantModel, TenantUserModel
from app.api.v1.module_system.log.crud import LoginLogCRUD
from app.api.v1.module_system.log.model import LoginLogModel
from app.api.v1.module_system.log.schema import LoginLogCreateSchema
from app.api.v1.module_system.role.model import RoleMenusModel, RoleModel
from app.api.v1.module_system.user.crud import UserCRUD
from app.api.v1.module_system.user.model import UserModel, UserRolesModel
from app.api.v1.module_system.user.schema import UserOutSchema
from app.common.enums import RedisInitKeyConfig
from app.config.setting import settings
from app.core.base_schema import AuthSchema, JWTOutSchema, JWTPayloadSchema
from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import logger
from app.core.redis_crud import RedisCURD
from app.core.request_context import (
    RequestContext,
    clear_current_tenant,
    set_current_tenant,
)
from app.core.security import (
    CustomOAuth2PasswordRequestForm,
    create_access_token,
    decode_access_token,
)
from app.utils.common_util import get_random_character
from app.utils.ip_local_util import IpLocalUtil, get_client_ip
from app.utils.password_util import PwdUtil

from .schema import (
    CaptchaOutSchema,
    EnterPlatformOutSchema,
    ImpersonateOutSchema,
    LoginWithTenantsSchema,
    SelectTenantOutSchema,
    TenantOptionSchema,
    TenantRegisterOutSchema,
)

CaptchaKey = NewType("CaptchaKey", str)
CaptchaBase64 = NewType("CaptchaBase64", str)


async def _write_login_log(
    username: str,
    status: int,
    login_ip: str | None = None,
    login_location: str | None = None,
    request_os: str | None = None,
    request_browser: str | None = None,
    msg: str | None = None,
) -> int | None:
    """写入登录日志；返回日志 ID（用于后台补全归属地）。"""
    try:
        async with async_db_session() as session, session.begin():
            _auth = AuthSchema(check_data_scope=False)
            obj = await LoginLogCRUD(_auth, session).create(
                data=LoginLogCreateSchema(
                    username=username,
                    status=status,
                    login_ip=login_ip,
                    login_location=login_location,
                    request_os=request_os,
                    request_browser=request_browser,
                    msg=msg,
                ),
            )
            return obj.id if obj else None
    except Exception:
        return None


async def _async_fill_login_location(redis, login_log_id: int, ip: str | None) -> None:
    """后台异步补全登录日志的归属地。"""
    if not ip:
        return
    try:
        location = await IpLocalUtil.resolve_location_async(redis, ip)
        logger.info(f"异步解析IP归属地结果: ip={ip}, log_id={login_log_id}, location={location}")
        if location == "归属地查询中" or not location:
            return
        async with async_db_session() as session, session.begin():
            await session.execute(sa_update(LoginLogModel).where(LoginLogModel.id == login_log_id).values(login_location=location))
            logger.info(f"登录日志归属地已更新: log_id={login_log_id}, location={location}")
    except Exception as e:
        logger.warning(f"异步补全登录归属地失败: {e}")


class LoginService:
    """登录认证服务"""

    def __init__(self, auth: AuthSchema, db: AsyncSession) -> None:
        self.auth = auth
        self.db = db

    @staticmethod
    def _collect_permissions(
        user: UserModel,
    ) -> tuple[list[str], dict[str, int], list[int], list[int], list[int], list[int]]:
        """收集用户角色下的权限、菜单、数据范围及角色 ID

        遍历用户角色，聚合所有关联菜单的 permission、menu_id、
        data_scope、自定义部门 ID 和角色 ID 列表。

        参数:
        - user (UserModel): 用户对象

        返回:
        - tuple[list[str], dict[str, int], list[int], list[int], list[int], list[int]]:
          (permissions, permissions_with_menu, menu_ids, data_scopes, custom_dept_ids, role_ids)
        """
        permissions: list[str] = []
        permissions_with_menu: dict[str, int] = {}
        menu_ids: list[int] = []
        data_scopes: list[int] = []
        custom_dept_ids: list[int] = []
        role_ids: list[int] = []
        if not user.is_superuser and hasattr(user, "roles"):
            for role in user.roles:
                if role and role.status == 0:
                    role_ids.append(role.id)
                    if hasattr(role, "menus"):
                        for menu in role.menus:
                            if menu and menu.status == 0:
                                menu_ids.append(menu.id)
                                if menu.permission:
                                    permissions.append(menu.permission)
                                    permissions_with_menu[menu.permission] = menu.id
                    if hasattr(role, "data_scope"):
                        data_scopes.append(role.data_scope)
                    if hasattr(role, "depts") and role.depts:
                        for dept in role.depts:
                            if dept:
                                custom_dept_ids.append(dept.id)
        return permissions, permissions_with_menu, menu_ids, data_scopes, custom_dept_ids, role_ids

    @classmethod
    async def authenticate_user(
        cls,
        request: Request,
        background_tasks: BackgroundTasks,
        redis: Redis,
        login_form: CustomOAuth2PasswordRequestForm,
        db: AsyncSession,
    ) -> LoginWithTenantsSchema:
        """用户认证"""
        ua_result = ua_parser.parse(request.headers.get("user-agent") or "")
        request_ip = get_client_ip(request)
        login_location = await IpLocalUtil.resolve_location_for_log(redis, request_ip)
        _login_os = ua_result.os.family if ua_result.os else "Unknown"
        _login_browser = ua_result.user_agent.family if ua_result.user_agent else "Unknown"
        _login_username = login_form.username

        referer = request.headers.get("referer", "")
        request_from_docs = referer.endswith(("docs", "redoc"))

        if settings.CAPTCHA_ENABLE and not request_from_docs:
            if not login_form.captcha_key:
                raise CustomException(msg="验证码不能为空")
            # 滑块模式：slider_complete 已验证身份，此处仅校验状态
            await CaptchaService.check_captcha(
                redis=redis,
                key=login_form.captcha_key,
            )

        auth = AuthSchema(check_data_scope=False)
        user = await UserCRUD(auth, db).get(username=login_form.username)

        if not user:
            await _write_login_log(
                username=_login_username,
                status=2,
                login_ip=request_ip,
                login_location=login_location,
                request_os=_login_os,
                request_browser=_login_browser,
                msg="用户不存在",
            )
            raise CustomException(msg="用户不存在")

        if not PwdUtil.verify_password(plain_password=login_form.password, password_hash=user.password):
            await _write_login_log(
                username=_login_username,
                status=2,
                login_ip=request_ip,
                login_location=login_location,
                request_os=_login_os,
                request_browser=_login_browser,
                msg="账号或密码错误",
            )
            raise CustomException(msg="账号或密码错误")
        if user.status == 1:
            await _write_login_log(
                username=_login_username,
                status=2,
                login_ip=request_ip,
                login_location=login_location,
                request_os=_login_os,
                request_browser=_login_browser,
                msg="用户已被停用",
            )
            raise CustomException(msg="用户已被停用")

        tenant_stmt = select(TenantModel).where(TenantModel.id == user.tenant_id, TenantModel.status == 0, TenantModel.is_deleted.is_(False)).limit(1)
        tenant_result = await db.execute(tenant_stmt)
        if not tenant_result.scalar_one_or_none():
            await _write_login_log(
                username=_login_username,
                status=2,
                login_ip=request_ip,
                login_location=login_location,
                request_os=_login_os,
                request_browser=_login_browser,
                msg="所属租户已被禁用",
            )
            raise CustomException(msg="所属租户已被禁用，请联系平台管理员")

        await UserCRUD(auth, db).update_last_login(id=user.id)

        if not user:
            raise CustomException(msg="用户不存在")
        if not login_form.login_type:
            raise CustomException(msg="登录类型不能为空")

        token = await cls.create_token(
            request=request,
            redis=redis,
            user=user,
            login_type=login_form.login_type,
        )

        tenants_auth = AuthSchema(user=UserOutSchema.model_validate(user), check_data_scope=False)
        tenants = await LoginService(tenants_auth, db).get_user_tenants(user_id=user.id)

        user_info = {
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "avatar": user.avatar,
            "is_superuser": user.is_superuser,
        }

        log_id = await _write_login_log(
            username=user.username,
            status=1,
            login_ip=request_ip,
            login_location=login_location,
            request_os=_login_os,
            request_browser=_login_browser,
            msg="登录成功",
        )
        # 登录成功后异步补全归属地，不阻塞返回
        if log_id and login_location == "归属地查询中":
            background_tasks.add_task(_async_fill_login_location, redis, log_id, request_ip)

        return LoginWithTenantsSchema(
            access_token=token.access_token,
            refresh_token=token.refresh_token,
            expires_in=token.expires_in,
            token_type=token.token_type,
            tenants=tenants,
            user_info=user_info,
        )

    @staticmethod
    def _build_session_dict(
        user: UserModel,
        session_id: str,
        permissions: list[str],
        permissions_with_menu: dict[str, int],
        menu_ids: list[int],
        data_scopes: list[int],
        custom_dept_ids: list[int],
        role_ids: list[int],
        request_ip: str,
        login_location: str | None,
        ua_result: Any,
        login_type: str,
    ) -> dict:
        """构建会话信息字典

        参数:
        - user (UserModel): 用户对象
        - session_id (str): 会话ID
        - permissions (list[str]): 权限标识列表
        - permissions_with_menu (dict[str, int]): 权限与菜单ID映射
        - menu_ids (list[int]): 菜单ID列表
        - data_scopes (list[int]): 数据范围列表
        - custom_dept_ids (list[int]): 自定义部门ID列表
        - role_ids (list[int]): 角色ID列表
        - request_ip (str): 请求IP
        - login_location (str): 登录地点
        - ua_result: User-Agent 解析结果
        - login_type (str): 登录类型

        返回:
        - dict: 会话信息字典
        """
        tenant_status = getattr(user.tenant, "status", 0) if hasattr(user, "tenant") and user.tenant else 0
        return {
            "session_id": session_id,
            "user_id": user.id,
            "tenant_id": user.tenant_id if not user.is_superuser else 0,
            "tenant_status": tenant_status,
            "is_superuser": user.is_superuser,
            "user_status": user.status,
            "name": user.name,
            "user_name": user.username,
            "dept_id": user.dept_id,
            "mobile": user.mobile,
            "email": user.email,
            "gender": user.gender,
            "avatar": user.avatar,
            "permissions": permissions,
            "permissions_with_menu": permissions_with_menu,
            "menu_ids": menu_ids,
            "data_scopes": data_scopes,
            "custom_dept_ids": custom_dept_ids,
            "role_ids": role_ids,
            "ipaddr": request_ip,
            "login_location": login_location,
            "os": ua_result.os.family if ua_result.os else "Unknown",
            "browser": ua_result.user_agent.family if ua_result.user_agent else "Unknown",
            "login_time": user.last_login,
            "login_type": login_type,
        }

    @classmethod
    async def create_token(cls, request: Request, redis: Redis, user: UserModel, login_type: str) -> JWTOutSchema:
        """创建访问令牌和刷新令牌"""
        session_id = str(uuid.uuid4())
        ua_result = ua_parser.parse(request.headers.get("user-agent") or "")
        request_ip = get_client_ip(request)

        login_location = await IpLocalUtil.resolve_location_for_log(redis, request_ip)

        base_ctx = getattr(request.state, "ctx", None) or RequestContext()
        request.state.ctx = replace(
            base_ctx,
            session_id=session_id,
            user_username=user.username,
            login_location=login_location,
        )

        access_expires = timedelta(seconds=settings.ACCESS_TOKEN_EXPIRE_SECONDS)
        refresh_expires = timedelta(seconds=settings.REFRESH_TOKEN_EXPIRE_SECONDS)

        now = datetime.now()

        permissions, permissions_with_menu, menu_ids, data_scopes, custom_dept_ids, role_ids = LoginService._collect_permissions(user)

        session_dict = LoginService._build_session_dict(
            user=user,
            session_id=session_id,
            permissions=permissions,
            permissions_with_menu=permissions_with_menu,
            menu_ids=menu_ids,
            data_scopes=data_scopes,
            custom_dept_ids=custom_dept_ids,
            role_ids=role_ids,
            request_ip=request_ip,
            login_location=login_location,
            ua_result=ua_result,
            login_type=login_type,
        )
        session_info = json.dumps(session_dict, default=str)

        # 会话信息存 Redis（完整 JSON），JWT sub 仅含 session_id
        await RedisCURD(redis).set(
            key=f"{RedisInitKeyConfig.USER_SESSION.key}:{session_id}",
            value=session_info,
            expire=int(refresh_expires.total_seconds()),
        )

        access_token = create_access_token(
            payload=JWTPayloadSchema(
                sub=session_id,
                is_refresh=False,
                exp=now + access_expires,
            ),
        )
        refresh_token = create_access_token(
            payload=JWTPayloadSchema(
                sub=session_id,
                is_refresh=True,
                exp=now + refresh_expires,
            ),
        )

        await RedisCURD(redis).set(
            key=f"{RedisInitKeyConfig.ACCESS_TOKEN.key}:{session_id}",
            value=access_token,
            expire=int(access_expires.total_seconds()),
        )

        await RedisCURD(redis).set(
            key=f"{RedisInitKeyConfig.REFRESH_TOKEN.key}:{session_id}",
            value=refresh_token,
            expire=int(refresh_expires.total_seconds()),
        )

        return JWTOutSchema(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=int(access_expires.total_seconds()),
            token_type=settings.TOKEN_TYPE,
        )

    @classmethod
    async def refresh_token(
        cls,
        db: AsyncSession,
        redis: Redis,
        refresh_token: str,
    ) -> JWTOutSchema:
        """刷新访问令牌"""
        token_payload: JWTPayloadSchema = decode_access_token(token=refresh_token)
        if not token_payload.is_refresh:
            raise CustomException(msg="非法凭证，请传入刷新令牌")

        session_id = token_payload.sub
        session_info = await RedisCURD(redis).get(f"{RedisInitKeyConfig.USER_SESSION.key}:{session_id}")
        if not session_info:
            raise CustomException(msg="会话已过期，请重新登录")

        user_id = json.loads(session_info).get("user_id")

        if not session_id or not user_id:
            raise CustomException(msg="非法凭证,无法获取会话编号或用户ID")

        auth = AuthSchema(check_data_scope=False)
        user = await UserCRUD(auth, db).get(id=user_id)
        if not user:
            raise CustomException(msg="刷新token失败，用户不存在")
        if user.status == 1:
            raise CustomException(msg="用户已被停用")

        access_expires = timedelta(seconds=settings.ACCESS_TOKEN_EXPIRE_SECONDS)
        refresh_expires = timedelta(seconds=settings.REFRESH_TOKEN_EXPIRE_SECONDS)
        now = datetime.now()

        # 延长会话信息 Redis TTL
        await RedisCURD(redis).expire(
            key=f"{RedisInitKeyConfig.USER_SESSION.key}:{session_id}",
            expire=int(refresh_expires.total_seconds()),
        )

        access_token = create_access_token(
            payload=JWTPayloadSchema(
                sub=session_id,
                is_refresh=False,
                exp=now + access_expires,
            ),
        )

        refresh_token_new = create_access_token(
            payload=JWTPayloadSchema(
                sub=session_id,
                is_refresh=True,
                exp=now + refresh_expires,
            ),
        )

        await RedisCURD(redis).set(
            key=f"{RedisInitKeyConfig.ACCESS_TOKEN.key}:{session_id}",
            value=access_token,
            expire=int(access_expires.total_seconds()),
        )

        await RedisCURD(redis).set(
            key=f"{RedisInitKeyConfig.REFRESH_TOKEN.key}:{session_id}",
            value=refresh_token_new,
            expire=int(refresh_expires.total_seconds()),
        )

        return JWTOutSchema(
            access_token=access_token,
            refresh_token=refresh_token_new,
            token_type=settings.TOKEN_TYPE,
            expires_in=int(access_expires.total_seconds()),
        )

    @staticmethod
    async def logout(redis: Redis, token: str) -> bool:
        """退出登录"""
        payload: JWTPayloadSchema = decode_access_token(token=token)
        session_id = payload.sub

        if not session_id:
            raise CustomException(msg="非法凭证,无法获取会话编号")

        await RedisCURD(redis).delete(f"{RedisInitKeyConfig.ACCESS_TOKEN.key}:{session_id}")
        await RedisCURD(redis).delete(f"{RedisInitKeyConfig.REFRESH_TOKEN.key}:{session_id}")
        await RedisCURD(redis).delete(f"{RedisInitKeyConfig.USER_SESSION.key}:{session_id}")

        logger.info(f"用户退出登录成功,会话编号:{session_id}")

        return True

    async def get_user_tenants(
        self,
        user_id: int | None = None,
    ) -> list[TenantOptionSchema]:
        """获取用户关联的租户列表"""
        from sqlalchemy import select

        user = self.auth.user
        if not user:
            raise CustomException(msg="未认证用户")

        uid = user_id or user.id
        if not uid:
            return []

        if user.is_superuser:
            stmt = select(TenantModel).where(TenantModel.status == 0, TenantModel.is_deleted.is_(False)).order_by(TenantModel.sort, TenantModel.id)
            result = await self.db.execute(stmt)
            tenant_objs = result.scalars().all()
            return [TenantOptionSchema(id=t.id, name=t.name, code=t.code) for t in tenant_objs]

        stmt = (
            select(TenantModel)
            .join(TenantUserModel, TenantUserModel.tenant_id == TenantModel.id)
            .where(
                TenantUserModel.user_id == uid,
                TenantModel.status == 0,
                TenantModel.is_deleted.is_(False),
            )
            .order_by(TenantUserModel.is_default.desc(), TenantModel.sort, TenantModel.id)
        )
        result = await self.db.execute(stmt)
        tenant_objs = result.scalars().all()
        return [TenantOptionSchema(id=t.id, name=t.name, code=t.code) for t in tenant_objs]

    async def select_tenant(
        self,
        request: Request,
        redis: Redis,
        tenant_id: int,
    ) -> SelectTenantOutSchema:
        """选择租户：验证用户归属并签发含租户上下文的新 JWT Token"""
        user = self.auth.user
        if not user:
            raise CustomException(msg="未认证用户")

        if not user.is_superuser:
            exist_stmt = (
                select(TenantUserModel)
                .where(
                    TenantUserModel.user_id == user.id,
                    TenantUserModel.tenant_id == tenant_id,
                )
                .limit(1)
            )
            result = await self.db.execute(exist_stmt)
            if not result.scalar_one_or_none():
                raise CustomException(msg="您不属于该租户，无法切换")

        tenant_stmt = select(TenantModel).where(TenantModel.id == tenant_id, TenantModel.status == 0).limit(1)
        result = await self.db.execute(tenant_stmt)
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise CustomException(msg="租户不存在或已被禁用")

        new_access_token, _new_refresh_token, access_expires = await self._rebuild_tokens(
            request, redis, {"tenant_id": tenant_id}
        )

        set_current_tenant(tenant_id)

        logger.info(f"用户 {user.username}(id={user.id}) 切换到租户 {tenant.name}(id={tenant_id})")

        return SelectTenantOutSchema(
            access_token=new_access_token,
            token_type=settings.TOKEN_TYPE,
            expires_in=int(access_expires.total_seconds()),
        )

    async def _rebuild_tokens(
        self,
        request: Request,
        redis: Redis,
        session_updates: dict,
    ) -> tuple[str, str, timedelta]:
        """从请求上下文重建全套令牌（access + refresh + session）

        提取会话信息，应用更新后写入 Redis，签发新 JWT。

        参数:
        - request (Request): FastAPI 请求对象
        - redis (Redis): Redis 客户端
        - session_updates (dict): 需更新到 session_info 的键值对

        返回:
        - tuple[str, str, timedelta]: (access_token, refresh_token, access_expires)
        """
        ctx = getattr(request.state, "ctx", None)
        session_id = ctx.session_id if ctx else None
        session_info = ctx.session_info if ctx else None

        if not session_id or not session_info:
            raise CustomException(msg="会话已失效")

        session_info.update(session_updates)
        refresh_expires = timedelta(seconds=settings.REFRESH_TOKEN_EXPIRE_SECONDS)

        await RedisCURD(redis).set(
            key=f"{RedisInitKeyConfig.USER_SESSION.key}:{session_id}",
            value=json.dumps(session_info) if isinstance(session_info, dict) else session_info,
            expire=int(refresh_expires.total_seconds()),
        )

        access_expires = timedelta(seconds=settings.ACCESS_TOKEN_EXPIRE_SECONDS)
        now = datetime.now()

        new_access_token = create_access_token(
            payload=JWTPayloadSchema(
                sub=session_id,
                is_refresh=False,
                exp=now + access_expires,
            ),
        )

        await RedisCURD(redis).set(
            key=f"{RedisInitKeyConfig.ACCESS_TOKEN.key}:{session_id}",
            value=new_access_token,
            expire=int(access_expires.total_seconds()),
        )

        new_refresh_token = create_access_token(
            payload=JWTPayloadSchema(
                sub=session_id,
                is_refresh=True,
                exp=now + refresh_expires,
            ),
        )
        await RedisCURD(redis).set(
            key=f"{RedisInitKeyConfig.REFRESH_TOKEN.key}:{session_id}",
            value=new_refresh_token,
            expire=int(refresh_expires.total_seconds()),
        )

        return new_access_token, new_refresh_token, access_expires

    async def enter_platform(
        self,
        request: Request,
        redis: Redis,
    ) -> EnterPlatformOutSchema:
        """进入平台管理模式：清除会话中的 tenant_id，返回平台作用域 JWT"""
        user = self.auth.user
        if not user:
            raise CustomException(msg="未认证用户")

        new_access_token, _new_refresh_token, access_expires = await self._rebuild_tokens(
            request, redis, {"tenant_id": 0}
        )

        clear_current_tenant()

        logger.info(f"用户 {user.username}(id={user.id}) 返回平台管理模式")

        return EnterPlatformOutSchema(
            access_token=new_access_token,
            token_type=settings.TOKEN_TYPE,
            expires_in=int(access_expires.total_seconds()),
        )

    async def impersonate(
        self,
        request: Request,
        redis: Redis,
        tenant_id: int,
    ) -> ImpersonateOutSchema:
        """平台管理员代签入：以指定租户身份登录（仅超级管理员可用）"""
        user = self.auth.user
        if not user or not user.is_superuser:
            raise CustomException(msg="仅平台管理员可执行代签入")

        tenant_stmt = select(TenantModel).where(TenantModel.id == tenant_id, TenantModel.is_deleted.is_(False)).limit(1)
        result = await self.db.execute(tenant_stmt)
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise CustomException(msg="租户不存在")

        new_access_token, new_refresh_token, access_expires = await self._rebuild_tokens(
            request, redis, {"tenant_id": tenant_id, "is_impersonate": True}
        )

        set_current_tenant(tenant_id)

        logger.warning(f"平台管理员 {user.username}(id={user.id}) 代签入租户 {tenant.name}(id={tenant_id})")

        return ImpersonateOutSchema(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type=settings.TOKEN_TYPE,
            expires_in=int(access_expires.total_seconds()),
            tenant_id=tenant_id,
            tenant_name=tenant.name,
        )


class CaptchaService:
    """验证码服务 — 滑块拖动模式"""

    @staticmethod
    async def get_captcha(redis: Redis) -> CaptchaOutSchema:
        """获取验证码（滑块模式：仅生成 key，无需算术图片）"""
        if not settings.CAPTCHA_ENABLE:
            raise CustomException(msg="未开启验证码服务")

        captcha_key = get_random_character()
        redis_key = f"{RedisInitKeyConfig.CAPTCHA_CODES.key}:{captcha_key}"
        # 存储滑块状态：pending（待验证）/ verified（已验证通过）
        await RedisCURD(redis).set(
            key=redis_key,
            value="pending",
            expire=settings.CAPTCHA_EXPIRE_SECONDS,
        )

        return CaptchaOutSchema(
            enable=settings.CAPTCHA_ENABLE,
            key=CaptchaKey(captcha_key),
            img_base=CaptchaBase64(""),
        )

    @staticmethod
    async def slider_complete(redis: Redis, captcha_key: str) -> dict:
        """标记滑块验证完成"""
        if not captcha_key:
            raise CustomException(msg="验证码标识不能为空")

        redis_key = f"{RedisInitKeyConfig.CAPTCHA_CODES.key}:{captcha_key}"
        status = await RedisCURD(redis).get(redis_key)
        if not status:
            raise CustomException(msg="验证码已过期，请刷新")

        if isinstance(status, bytes):
            status = status.decode()

        if status == "verified":
            raise CustomException(msg="验证码已使用")

        # 标记为已验证
        await RedisCURD(redis).set(
            key=redis_key,
            value="verified",
            expire=settings.CAPTCHA_EXPIRE_SECONDS,
        )

        return {"captcha_key": captcha_key, "verified": True}

    @staticmethod
    async def check_captcha(redis: Redis, key: str) -> bool:
        """校验滑块验证码：检查 key 状态是否为 verified"""
        redis_key = f"{RedisInitKeyConfig.CAPTCHA_CODES.key}:{key}"
        status = await RedisCURD(redis).get(redis_key)
        if not status:
            raise CustomException(msg="验证码已过期，请刷新")

        if isinstance(status, bytes):
            status = status.decode()

        if status != "verified":
            raise CustomException(msg="请先完成滑块验证")

        await RedisCURD(redis).delete(redis_key)
        return True


class TenantRegisterService:
    """PRD §4.5 租户自助注册：一次性创建租户 + 管理员 + owner 角色 + 菜单分配"""

    DEFAULT_TRIAL_DAYS: int = settings.TENANT_TRIAL_DAYS

    @classmethod
    async def register(
        cls,
        db: AsyncSession,
        username: str,
        password: str,
        email: str,
        tenant_name: str | None = None,
    ) -> TenantRegisterOutSchema:
        """租户自助注册：一次性创建租户 + 管理员 + owner 角色 + 菜单分配"""
        from sqlalchemy.exc import IntegrityError

        exists_stmt = (
            select(func.count())
            .select_from(UserModel)
            .where(
                UserModel.is_deleted.is_(False),
                (UserModel.username == username) | (UserModel.email == email),
            )
        )
        cnt = (await db.execute(exists_stmt)).scalar() or 0
        if cnt > 0:
            raise CustomException(msg="用户名或邮箱已被占用")

        pkg_stmt = select(PackageModel).where(PackageModel.status == 0).order_by(PackageModel.id).limit(1)
        default_pkg = (await db.execute(pkg_stmt)).scalar_one_or_none()

        now = datetime.now()
        trial_end = now + timedelta(days=cls.DEFAULT_TRIAL_DAYS)

        base = tenant_name or username
        code_suffix = base.encode("utf-8").hex()[:6].upper()
        tenant_code = f"T{code_suffix}"

        tenant = TenantModel(
            name=tenant_name or f"{username}的租户",
            code=tenant_code,
            contact_name=username,
            package_id=default_pkg.id if default_pkg else None,
            start_time=now,
            end_time=trial_end,
            status=0,
        )
        db.add(tenant)
        await db.flush()

        user = UserModel(
            name=username,
            username=username,
            password=PwdUtil.hash_password(password),
            email=email,
            tenant_id=tenant.id,
            status=0,
        )
        db.add(user)
        await db.flush()

        tenant_user = TenantUserModel(
            user_id=user.id,
            tenant_id=tenant.id,
            role="owner",
            is_default=1,
        )
        db.add(tenant_user)
        await db.flush()

        owner_role = RoleModel(
            name="租户管理员",
            code="owner",
            tenant_id=tenant.id,
            order=1,
            data_scope=4,
            description="自助注册创建的管理员角色",
        )
        db.add(owner_role)
        await db.flush()

        user_role = UserRolesModel(user_id=user.id, role_id=owner_role.id)
        db.add(user_role)

        if default_pkg:
            pkg_menu_stmt = select(PackageMenuModel).where(
                PackageMenuModel.package_id == default_pkg.id,
            )
            pkg_menus = (await db.execute(pkg_menu_stmt)).scalars().all()
            for pm in pkg_menus:
                db.add(RoleMenusModel(role_id=owner_role.id, menu_id=pm.menu_id))

        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise CustomException(msg="租户编码或用户名已被占用，请重试")

        return TenantRegisterOutSchema(
            user_id=user.id,
            username=username,
            tenant_id=tenant.id,
            tenant_name=tenant.name,
            tenant_code=tenant_code,
            package=default_pkg.name if default_pkg else None,
            trial_end=trial_end.strftime("%Y-%m-%d"),
            message="注册成功",
        )


class TenantLookupService:
    """租户查询服务（登录页根据编码查找租户）"""

    @staticmethod
    async def lookup_by_code(db: AsyncSession, code: str) -> dict:
        stmt = select(TenantModel).where(
            TenantModel.code == code,
            TenantModel.is_deleted.is_(False),
        )
        result = (await db.execute(stmt)).scalar_one_or_none()
        if not result:
            raise CustomException(msg="未找到该租户")

        return {
            "id": result.id,
            "name": result.name,
            "code": result.code,
            "logo_url": result.logo_url,
            "login_bg": result.login_bg,
            "version": result.version,
        }

    @staticmethod
    async def lookup_by_domain(db: AsyncSession, domain: str) -> dict:
        stmt = select(TenantModel).where(
            TenantModel.domain == domain,
            TenantModel.is_deleted.is_(False),
        )
        result = (await db.execute(stmt)).scalar_one_or_none()
        if not result:
            raise CustomException(msg="未找到该域名对应的租户")

        return {
            "id": result.id,
            "name": result.name,
            "code": result.code,
            "logo_url": result.logo_url,
            "login_bg": result.login_bg,
            "version": result.version,
        }

    @staticmethod
    async def list_options(db: AsyncSession) -> list[dict]:
        """获取所有活跃租户选项（登录页下拉选择）"""
        stmt = (
            select(TenantModel)
            .where(TenantModel.is_deleted.is_(False), TenantModel.status == 0)
            .order_by(TenantModel.id)
        )
        results = (await db.execute(stmt)).scalars().all()
        return [
            {"id": r.id, "name": r.name, "code": r.code}
            for r in results
        ]

    @staticmethod
    async def search(db: AsyncSession, q: str) -> list[dict]:
        """模糊搜索租户（按编码或名称）"""
        pattern = f"%{q}%"
        stmt = (
            select(TenantModel)
            .where(
                TenantModel.is_deleted.is_(False),
                TenantModel.status == 0,
                (TenantModel.code.ilike(pattern) | TenantModel.name.ilike(pattern)),
            )
            .order_by(TenantModel.id)
            .limit(20)
        )
        results = (await db.execute(stmt)).scalars().all()
        return [
            {"id": r.id, "name": r.name, "code": r.code}
            for r in results
        ]
