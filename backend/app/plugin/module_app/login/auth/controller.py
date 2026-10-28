"""C端认证接口 —— 登录、注册、令牌与会话管理。

完整路径：``/api/v1/app/login/*``（``/api/v1/app`` 来自插件目录 ``module_app``，
``/login`` 为子板块名，其后直接是业务路径，不再叠加 ``auth``/``login`` 分组）。

安全说明：本路由刻意不使用 ``OperationLogRoute``，避免登录密码等敏感字段
被写入后台操作日志表；C端登录行为由本子板块的 ``app_login_log`` 单独记录。
"""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Request
from fastapi.responses import JSONResponse
from redis.asyncio.client import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import ResponseSchema, SuccessResponse
from app.core.dependencies import db_getter, redis_getter

from ..core.constants import ThirdPartyProvider
from ..core.dependencies import CurrentAppUser
from ..core.session import AppSessionInfo
from .schema import (
    AppAppleLoginSchema,
    AppLoginOutSchema,
    AppLoginTypeOutSchema,
    AppPasswordLoginSchema,
    AppRefreshTokenSchema,
    AppRegisterSchema,
    AppResetPasswordSchema,
    AppSmsLoginSchema,
    AppSmsSendOutSchema,
    AppSmsSendSchema,
    AppTokenOutSchema,
    AppWechatLoginSchema,
)
from .service import AppLoginService
from .sms import SmsService
from .third_party import ThirdPartyCredential, available_providers

AppAuthRouter = APIRouter(prefix="/login", tags=["C端认证"])


@AppAuthRouter.get("/config", summary="获取C端登录配置", response_model=ResponseSchema[AppLoginTypeOutSchema])
async def get_login_config_controller() -> JSONResponse:
    """返回已开启的登录方式与支持终端，供客户端渲染登录页。"""
    providers = set(available_providers())
    wechat_providers = {ThirdPartyProvider.WECHAT_MINI.value, ThirdPartyProvider.WECHAT_OPEN.value, ThirdPartyProvider.WECHAT_MP.value}
    data = AppLoginTypeOutSchema(
        wechat=bool(providers & wechat_providers),
        apple=ThirdPartyProvider.APPLE.value in providers,
        providers=sorted(providers),
    )
    return SuccessResponse(data=data, msg="获取登录配置成功")


@AppAuthRouter.post("/register", summary="C端用户注册", response_model=ResponseSchema[AppLoginOutSchema])
async def register_controller(
    request: Request,
    data: Annotated[AppRegisterSchema, Body(description="注册参数")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    service = AppLoginService(db, redis)
    result = await service.register(data=data, request=request)
    return SuccessResponse(data=result, msg="注册成功")


@AppAuthRouter.post("/password", summary="密码登录", response_model=ResponseSchema[AppLoginOutSchema])
async def login_by_password_controller(
    request: Request,
    data: Annotated[AppPasswordLoginSchema, Body(description="登录参数")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    service = AppLoginService(db, redis)
    result = await service.login_by_password(data=data, request=request)
    return SuccessResponse(data=result, msg="登录成功")


@AppAuthRouter.post("/sms", summary="短信验证码登录", response_model=ResponseSchema[AppLoginOutSchema])
async def login_by_sms_controller(
    request: Request,
    data: Annotated[AppSmsLoginSchema, Body(description="登录参数")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    service = AppLoginService(db, redis)
    result = await service.login_by_sms(data=data, request=request)
    return SuccessResponse(data=result, msg="登录成功")


@AppAuthRouter.post("/wechat", summary="微信登录", response_model=ResponseSchema[AppLoginOutSchema])
async def login_by_wechat_controller(
    request: Request,
    data: Annotated[AppWechatLoginSchema, Body(description="微信登录参数")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """小程序端传 ``provider=wechat_mini``，App/网页扫码传 ``provider=wechat_open``。"""
    service = AppLoginService(db, redis)
    result = await service.login_by_third_party(
        credential=ThirdPartyCredential(code=data.code, nickname=data.nickname, avatar=data.avatar),
        provider=data.provider.value,
        platform=data.platform,
        request=request,
    )
    return SuccessResponse(data=result, msg="登录成功")


@AppAuthRouter.post("/apple", summary="苹果登录", response_model=ResponseSchema[AppLoginOutSchema])
async def login_by_apple_controller(
    request: Request,
    data: Annotated[AppAppleLoginSchema, Body(description="苹果登录参数")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    service = AppLoginService(db, redis)
    result = await service.login_by_third_party(
        credential=ThirdPartyCredential(
            identity_token=data.identity_token,
            authorization_code=data.authorization_code,
            nickname=data.nickname,
            email=data.email,
        ),
        provider=ThirdPartyProvider.APPLE.value,
        platform=data.platform,
        request=request,
    )
    return SuccessResponse(data=result, msg="登录成功")


@AppAuthRouter.post("/sms/send", summary="发送短信验证码", response_model=ResponseSchema[AppSmsSendOutSchema])
async def send_sms_code_controller(
    data: Annotated[AppSmsSendSchema, Body(description="发送参数")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    result = await SmsService(redis).send_code(mobile=data.mobile, scene=data.scene)
    return SuccessResponse(data=result, msg="验证码发送成功")


@AppAuthRouter.post("/password/reset", summary="短信验证码重置密码", response_model=ResponseSchema[None])
async def reset_password_controller(
    data: Annotated[AppResetPasswordSchema, Body(description="重置密码参数")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    service = AppLoginService(db, redis)
    await service.reset_password_by_sms(mobile=data.mobile, code=data.code, new_password=data.password)
    return SuccessResponse(msg="密码重置成功，请重新登录")


@AppAuthRouter.post("/refresh", summary="刷新令牌", response_model=ResponseSchema[AppTokenOutSchema])
async def refresh_token_controller(
    data: Annotated[AppRefreshTokenSchema, Body(description="刷新令牌参数")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    service = AppLoginService(db, redis)
    result = await service.refresh_token(data=data)
    return SuccessResponse(data=result, msg="刷新成功")


@AppAuthRouter.post("/logout", summary="退出登录", response_model=ResponseSchema[None])
async def logout_controller(
    user: CurrentAppUser,
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    await AppLoginService(db, redis).logout(session_id=user.session_id)
    return SuccessResponse(msg="退出成功")


@AppAuthRouter.get("/sessions", summary="获取当前账号在线会话", response_model=ResponseSchema[list[AppSessionInfo]])
async def list_sessions_controller(
    user: CurrentAppUser,
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    sessions = await AppLoginService(db, redis).list_sessions(user_id=user.user_id)
    return SuccessResponse(data=sessions, msg="获取在线会话成功")


@AppAuthRouter.delete("/sessions/others", summary="下线当前账号的其他会话", response_model=ResponseSchema[int])
async def remove_other_sessions_controller(
    user: CurrentAppUser,
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    count = await AppLoginService(db, redis).remove_other_sessions(user.user_id, user.session_id)
    return SuccessResponse(data=count, msg=f"已下线 {count} 个会话")


@AppAuthRouter.delete("/sessions/{session_id}", summary="下线指定会话", response_model=ResponseSchema[None])
async def remove_session_controller(
    user: CurrentAppUser,
    session_id: Annotated[str, Path(description="会话ID")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    await AppLoginService(db, redis).remove_session(user.user_id, session_id)
    return SuccessResponse(msg="下线成功")
