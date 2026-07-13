import json
from collections.abc import AsyncGenerator
from dataclasses import replace
from typing import Any

from fastapi import Depends, Query, Request
from redis.asyncio.client import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import RET, RedisInitKeyConfig, TenantStatusEnum
from app.config.setting import settings
from app.core.base_schema import AuthSchema, CoreUserSchema
from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import logger
from app.core.redis_crud import RedisCURD
from app.core.request_context import RequestContext
from app.core.security import OAuth2Schema, decode_access_token


async def db_getter() -> AsyncGenerator[AsyncSession, None]:
    """数据库会话 — 请求级生命周期管理。

    一个 HTTP 请求内所有 SQL 共享同一个事务：要么全成功，要么全失败。
    读操作也走这个事务（牺牲一点 MVCC 隔离换取读已写一致性）。
    """
    async with async_db_session() as session, session.begin():
        yield session


async def redis_getter(request: Request) -> Redis:
    """获取Redis连接

    参数:
    - request (Request): 请求对象

    返回:
    - Redis: Redis连接
    """
    return request.app.state.redis


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(db_getter),
    redis: Redis = Depends(redis_getter),
    token: str = Depends(OAuth2Schema),
) -> AuthSchema:
    """获取当前用户

    用户查询使用独立的只读数据库会话（不参与请求事务，查询完成后立即释放快照），
    返回的 auth.db 指向请求级事务会话供后续写操作使用。

    参数:
    - request (Request): 请求对象
    - db (AsyncSession): 请求级事务会话
    - redis (Redis): Redis连接
    - token (str): 访问令牌

    返回:
    - AuthSchema: 已认证的信息模型
    """
    return await _authenticate(token, db, redis, request)


async def get_current_user_ws(
    token: str = Query(..., description="认证token"),
    db: AsyncSession = Depends(db_getter),
    redis: Redis = Depends(redis_getter),
) -> AuthSchema:
    """获取当前用户（WebSocket专用，从查询参数获取token）

    参数:
    - token (str): 认证token
    - db (AsyncSession): 数据库会话
    - redis (Redis): Redis连接

    返回:
    - AuthSchema: 已认证的信息模型
    """
    return await _authenticate(token, db, redis)


async def _authenticate(
    token: str,
    db: AsyncSession,
    redis: Redis,
    request: Request | None = None,
) -> AuthSchema:
    """核心认证逻辑（HTTP 与 WebSocket 共享）

    参数:
    - token: 访问令牌
    - db: 请求级事务会话
    - redis: Redis连接
    - request: HTTP 请求对象（WebSocket 场景为 None）

    返回:
    - AuthSchema: 认证信息模型
    """
    if not token:
        raise CustomException(msg="认证已失效", code=RET.UNAUTHORIZED.code, status_code=401)

    # 处理Bearer token
    if token.startswith("Bearer"):
        token = token.split(" ")[1]

    # 优先使用 TenantMiddleware 缓存在 request.state.ctx 中的会话信息（避免重复 Redis 读取）
    user_info = None
    if request:
        ctx = getattr(request.state, "ctx", None)
        user_info = ctx.jwt_user_info if ctx else None

    if not user_info:
        # 降级路径：自行解码 token + 从 Redis 读取会话信息
        payload = decode_access_token(token)
        if not payload or not hasattr(payload, "is_refresh") or payload.is_refresh:
            raise CustomException(msg="非法凭证", code=RET.INVALID_CREDENTIALS.code, status_code=401)
        session_id = payload.sub
        if not session_id:
            raise CustomException(msg="认证已失效", code=RET.UNAUTHORIZED.code, status_code=401)
        raw = await RedisCURD(redis).get(f"{RedisInitKeyConfig.USER_SESSION.key}:{session_id}")
        if not raw:
            raise CustomException(msg="认证已失效", code=RET.UNAUTHORIZED.code, status_code=401)
        user_info = json.loads(raw)

    session_id = user_info.get("session_id")
    if not session_id:
        raise CustomException(msg="认证已失效", code=RET.UNAUTHORIZED.code, status_code=401)

    # 滑动过期续期（仅在 token 剩余不足一半时触发）
    if settings.TOKEN_SLIDING_EXPIRE:
        ttl = await RedisCURD(redis).ttl(key=f"{RedisInitKeyConfig.ACCESS_TOKEN.key}:{session_id}")
        expire_seconds = settings.ACCESS_TOKEN_EXPIRE_SECONDS
        if ttl > 0 and ttl < expire_seconds // 2:
            await RedisCURD(redis).expire(key=f"{RedisInitKeyConfig.ACCESS_TOKEN.key}:{session_id}", expire=expire_seconds)
            await RedisCURD(redis).expire(key=f"{RedisInitKeyConfig.REFRESH_TOKEN.key}:{session_id}", expire=settings.REFRESH_TOKEN_EXPIRE_SECONDS)

    username = user_info.get("user_name")
    if not username:
        raise CustomException(msg="认证已失效", code=RET.UNAUTHORIZED.code, status_code=401)

    user_status = user_info.get("user_status", 0)
    tenant_status = user_info.get("tenant_status", 0)
    is_superuser = user_info.get("is_superuser", False)
    tenant_id = user_info.get("tenant_id", 0)
    user_id = user_info.get("user_id")

    if user_status == 1:
        raise CustomException(msg="用户已被停用", code=RET.UNAUTHORIZED.code, status_code=401)

    if not is_superuser and tenant_id > 0:
        if tenant_status == TenantStatusEnum.FROZEN:
            raise CustomException(msg="租户已被冻结，请联系平台管理员", code=RET.FORBIDDEN.code, status_code=423)
        if tenant_status == TenantStatusEnum.CANCELLED:
            raise CustomException(msg="租户已注销", code=RET.FORBIDDEN.code, status_code=423)
        if tenant_status == TenantStatusEnum.ARREARS:
            raise CustomException(msg="租户已欠费，仅允许查看操作，请联系平台管理员续费", code=RET.FORBIDDEN.code, status_code=423)
        if tenant_status == TenantStatusEnum.TRIAL:
            raise CustomException(msg="租户处于试用期，部分功能受限，请升级正式套餐", code=RET.FORBIDDEN.code, status_code=423)

    if request:
        request.state.ctx = replace(
            (getattr(request.state, "ctx", None) or RequestContext()),
            user_id=user_id,
            user_username=username,
            session_id=session_id,
            session_info=user_info,
        )

    if not user_id:
        raise CustomException(msg="认证已失效", code=RET.UNAUTHORIZED.code, status_code=401)
    from app.api.v1.module_system.user.model import UserModel

    stmt = select(UserModel).where(UserModel.id == user_id, UserModel.is_deleted == False)
    result = await db.execute(stmt)
    user_obj = result.scalars().first()
    if not user_obj:
        raise CustomException(msg="用户不存在", code=RET.NOT_FOUND.code, status_code=401)
    user = CoreUserSchema.model_validate(user_obj)

    # token_version 比对：用户登出、改密码、被踢下线等场景会使 DB 版本递增，从而使旧 token 失效
    session_token_version = user_info.get("token_version", 0) or 0
    if user.token_version != session_token_version:
        raise CustomException(msg="认证已失效", code=RET.UNAUTHORIZED.code, status_code=401)

    auth = AuthSchema(
        check_data_scope=False,
        user=user,
        permissions=user_info.get("permissions", []),
        permissions_with_menu=user_info.get("permissions_with_menu", {}),
        menu_ids=user_info.get("menu_ids", []),
        data_scopes=user_info.get("data_scopes", []),
        custom_dept_ids=user_info.get("custom_dept_ids", []),
        role_ids=user_info.get("role_ids", []),
        is_impersonate=user_info.get("is_impersonate", False),
    )
    return auth


class AuthPermission:
    """权限验证类"""

    def __init__(
        self,
        permissions: list[str] | None = None,
        check_data_scope: bool = True,
    ) -> None:
        """初始化权限验证

        参数:
        - permissions (list[str] | None): 权限标识列表。
        - check_data_scope (bool): 是否启用严格模式校验。
        """
        self.permissions = permissions or []
        self.check_data_scope = check_data_scope

    async def __call__(self, auth: AuthSchema = Depends(get_current_user), db: AsyncSession = Depends(db_getter)) -> AuthSchema:
        """调用权限验证

        参数:
        - auth (AuthSchema): 认证信息对象。

        返回:
        - AuthSchema: 已认证的权限信息对象。
        """
        auth = auth.model_copy(update={"check_data_scope": self.check_data_scope})

        user = auth.user
        if user.id is None or user.is_superuser:
            return auth

        if not self.permissions:
            return auth

        if "*" in self.permissions or "*:*:*" in self.permissions:
            return auth

        user_permissions = set[Any](auth.permissions)

        if not user_permissions:
            raise CustomException(msg="无权限操作", code=RET.FORBIDDEN.code, status_code=403)

        if user.tenant_id:
            from app.api.v1.module_platform.package.service import PackageService
            result = await PackageService(auth, db).get_tenant_available_menu_ids(user.tenant_id)
            allowed_ids = set[int](result)
            user_permissions = {p for p, mid in auth.permissions_with_menu.items() if mid in allowed_ids}

        if not any(perm in user_permissions for perm in self.permissions):
            logger.error(f"用户缺少任何所需的权限: {self.permissions}")
            raise CustomException(msg="无权限操作", code=10403, status_code=403)

        return auth
