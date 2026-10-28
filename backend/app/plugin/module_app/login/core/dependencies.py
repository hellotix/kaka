"""C端登录校验依赖 —— module_app 各子板块的引用入口。

用法（在任意子板块的 controller.py 中）::

    from typing import Annotated
    from fastapi import Depends
    from app.plugin.module_app import AppAuth, AppAuthContext, CurrentAppUser

    # 方式一：类型别名（推荐）
    @SomeRouter.get("/xxx")
    async def xxx(user: CurrentAppUser) -> JSONResponse: ...

    # 方式二：显式依赖，可限制终端
    @SomeRouter.get("/yyy")
    async def yyy(user: Annotated[AppAuthContext, Depends(AppAuth(platforms=[AppPlatform.IOS]))]): ...

    # 方式三：登录可选（未登录返回 None）
    @SomeRouter.get("/zzz")
    async def zzz(user: MaybeAppUser) -> JSONResponse: ...
"""

from collections.abc import Sequence
from typing import Annotated

from fastapi import Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio.client import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import RET
from app.core.base_schema import AuthSchema
from app.core.dependencies import db_getter, redis_getter
from app.core.exceptions import CustomException
from app.core.logger import logger

from ..user.crud import AppUserCRUD
from ..user.model import AppUserModel
from .constants import TOKEN_SLIDING_EXPIRE, AppPlatform, AppTokenType
from .security import AppTokenPayload, decode_app_token, extract_bearer_token, unauthorized
from .session import AppSessionStore


class AppAuthContext(BaseModel):
    """C端登录上下文 —— 依赖注入后传递给业务层"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    user_id: int = Field(..., description="C端用户ID")
    session_id: str = Field(..., description="会话ID")
    platform: AppPlatform = Field(..., description="登录终端")
    login_type: str = Field(default="", description="登录方式")
    username: str | None = Field(default=None, description="用户名")
    nickname: str | None = Field(default=None, description="昵称")
    mobile: str | None = Field(default=None, description="手机号")
    avatar: str | None = Field(default=None, description="头像")
    login_time: str | None = Field(default=None, description="登录时间")
    token: AppTokenPayload = Field(default_factory=lambda: AppTokenPayload(sub="", uid=0, typ="app", tt="access", plat="web"), description="令牌载荷")
    user: AppUserModel = Field(exclude=True, description="C端用户 ORM 对象")
    db: AsyncSession = Field(exclude=True, description="数据库会话")
    redis: Redis = Field(exclude=True, description="Redis 连接")


def _to_platform(value: str | None) -> AppPlatform:
    """会话中的终端字符串转枚举，未知值按 web 处理。"""
    try:
        return AppPlatform(value) if value else AppPlatform.WEB
    except ValueError:
        return AppPlatform.WEB


async def resolve_app_auth(
    token: str | None,
    db: AsyncSession,
    redis: Redis,
    *,
    sliding: bool = True,
) -> AppAuthContext:
    """校验 C端令牌并构建登录上下文。

    参数:
    - token (str | None): Authorization 头中解析出的令牌。
    - db (AsyncSession): 数据库会话。
    - redis (Redis): Redis 连接。
    - sliding (bool): 是否在校验通过后做滑动续期。

    返回:
    - AppAuthContext: 登录上下文。

    异常:
    - CustomException: 未携带令牌、令牌非法/过期、会话失效或用户被禁用时抛出 401。
    """
    if not token:
        raise unauthorized("未登录或登录已失效，请先登录")

    payload = decode_app_token(token, token_type=AppTokenType.ACCESS, verify_exp=not TOKEN_SLIDING_EXPIRE)

    store = AppSessionStore(redis)
    info = await store.get(payload.sub)
    if not info:
        raise unauthorized("登录已失效，请重新登录")
    if info.user_id != payload.uid:
        logger.warning(f"C端令牌与会话不匹配: token_uid={payload.uid}, session_uid={info.user_id}")
        raise unauthorized("无效凭证，请重新登录")

    user = await AppUserCRUD(AuthSchema(), db).get(id=info.user_id)
    if not user:
        raise unauthorized("用户不存在，请重新登录")
    if user.status == 1:
        raise CustomException(msg="账号已被禁用，请联系客服", code=RET.FORBIDDEN.code, status_code=403)

    if sliding and TOKEN_SLIDING_EXPIRE:
        await store.renew(payload.sub)

    return AppAuthContext(
        user_id=user.id,
        session_id=info.session_id,
        platform=_to_platform(info.platform),
        login_type=info.login_type,
        username=info.username,
        nickname=info.nickname,
        mobile=info.mobile,
        avatar=info.avatar,
        login_time=info.login_time.strftime("%Y-%m-%d %H:%M:%S") if info.login_time else None,
        token=payload,
        user=user,
        db=db,
        redis=redis,
    )


class AppAuth:
    """C端登录校验依赖（必须登录）

    参数:
    - platforms (Sequence[AppPlatform] | None): 允许访问的终端，None 表示不限制。
    """

    def __init__(self, platforms: Sequence[AppPlatform] | None = None) -> None:
        self.platforms = tuple(platforms) if platforms else None

    async def __call__(
        self,
        request: Request,
        db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
        redis: Annotated[Redis, Depends(redis_getter)],
    ) -> AppAuthContext:
        """执行校验并返回登录上下文。"""
        context = await resolve_app_auth(extract_bearer_token(request), db, redis)
        if self.platforms and context.platform not in self.platforms:
            allowed = ", ".join(item.value for item in self.platforms)
            raise CustomException(msg=f"当前终端无权访问，仅支持: {allowed}", code=RET.FORBIDDEN.code, status_code=403)
        return context


class OptionalAppAuth:
    """C端登录校验依赖（登录可选）

    未携带令牌或令牌失效时返回 None，不抛异常，适用于登录前后展示不同的接口。
    """

    async def __call__(
        self,
        request: Request,
        db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
        redis: Annotated[Redis, Depends(redis_getter)],
    ) -> AppAuthContext | None:
        """尝试解析登录态，失败返回 None。"""
        token = extract_bearer_token(request)
        if not token:
            return None
        try:
            return await resolve_app_auth(token, db, redis)
        except CustomException as e:
            logger.debug(f"可选登录态解析失败，按未登录处理: {e.msg}")
            return None


async def get_current_app_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> AppAuthContext:
    """函数式登录依赖，等价于 ``AppAuth()``。"""
    return await resolve_app_auth(extract_bearer_token(request), db, redis)


CurrentAppUser = Annotated[AppAuthContext, Depends(AppAuth())]
MaybeAppUser = Annotated[AppAuthContext | None, Depends(OptionalAppAuth())]
