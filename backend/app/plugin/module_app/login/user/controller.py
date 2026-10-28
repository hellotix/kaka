"""C端用户接口 —— 后台管理 + C端个人中心。

完整路径：``/api/v1/app/login/user/*``（后台管理）、``/api/v1/app/login/profile/*``（C端个人中心）。
``/api/v1/app`` 来自插件目录 ``module_app``，``/login`` 为子板块名。

路由拆分为三组：

- ``AppUserRouter``       后台管理接口，挂 ``OperationLogRoute`` 记录操作日志。
- ``AppUserSecureRouter`` 后台含明文密码的接口（创建用户 / 重置密码）。
  ``OperationLogRoute`` 会把请求体原文写入操作日志，密码类接口一律不挂，避免明文密码落库。
- ``AppProfileRouter``    C端个人中心接口，凭 ``CurrentAppUser`` 登录态访问，同样不挂操作日志。
  在线会话查询与下线属于登录生命周期，统一放在 ``/login/sessions`` 下，此处不重复提供。
"""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Query, status
from fastapi.responses import JSONResponse
from redis.asyncio.client import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import ResponseSchema, SuccessResponse
from app.core.base_schema import AuthSchema, BatchSetAvailable, PageResultSchema, PaginationQueryParam
from app.core.dependencies import AuthPermission, db_getter, redis_getter
from app.core.router_class import OperationLogRoute

from ..auth.schema import AppLoginLogOutSchema, AppLoginLogQueryParam
from ..core.constants import AppUserPerm
from ..core.dependencies import CurrentAppUser
from ..core.session import AppSessionInfo
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
from .service import AppUserProfileService, AppUserService

AppUserRouter = APIRouter(route_class=OperationLogRoute, prefix="/login/user", tags=["C端用户管理"])
AppUserSecureRouter = APIRouter(prefix="/login/user", tags=["C端用户管理"])
AppProfileRouter = APIRouter(prefix="/login/profile", tags=["C端个人中心"])


# ══════════════════════════ 后台管理 ══════════════════════════


@AppUserRouter.get("/detail/{id}", summary="获取C端用户详情", response_model=ResponseSchema[AppUserOutSchema])
async def get_app_user_detail_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([AppUserPerm.DETAIL]))],
    id: Annotated[int, Path(description="C端用户ID")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """按ID查询C端用户详情。"""
    service = AppUserService(auth, db, redis)
    result = await service.detail(id=id)
    return SuccessResponse(data=result, msg="获取C端用户详情成功")


@AppUserRouter.get("/list", summary="分页查询C端用户", response_model=ResponseSchema[PageResultSchema[AppUserOutSchema]])
async def get_app_user_list_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([AppUserPerm.QUERY]))],
    page: Annotated[PaginationQueryParam, Depends()],
    search: Annotated[AppUserQueryParam, Query()],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """分页查询C端用户列表。"""
    service = AppUserService(auth, db, redis)
    result = await service.page(page_no=page.page_no, page_size=page.page_size, search=search, order_by=page.order_by)
    return SuccessResponse(data=result, msg="查询C端用户列表成功")


@AppUserSecureRouter.post("/create", status_code=status.HTTP_201_CREATED, summary="创建C端用户", response_model=ResponseSchema[AppUserOutSchema])
async def create_app_user_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([AppUserPerm.CREATE]))],
    data: Annotated[AppUserCreateSchema, Body(description="创建参数")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """后台创建C端用户，密码以哈希存储。"""
    service = AppUserService(auth, db, redis)
    result = await service.create(data=data)
    return SuccessResponse(data=result, msg="创建C端用户成功")


@AppUserRouter.put("/update/{id}", summary="修改C端用户", response_model=ResponseSchema[AppUserOutSchema])
async def update_app_user_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([AppUserPerm.UPDATE]))],
    id: Annotated[int, Path(description="C端用户ID")],
    data: Annotated[AppUserUpdateSchema, Body(description="修改参数")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """修改C端用户资料，禁用时同步强制下线。"""
    service = AppUserService(auth, db, redis)
    result = await service.update(id=id, data=data)
    return SuccessResponse(data=result, msg="修改C端用户成功")


@AppUserRouter.delete("/delete", summary="删除C端用户", response_model=ResponseSchema[None])
async def delete_app_user_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([AppUserPerm.DELETE]))],
    ids: Annotated[list[int], Body(description="C端用户ID列表")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """批量删除C端用户（软删除）并强制下线全部会话。"""
    service = AppUserService(auth, db, redis)
    await service.delete(ids=ids)
    return SuccessResponse(msg="删除C端用户成功")


@AppUserRouter.patch("/status/batch", summary="批量修改C端用户状态", response_model=ResponseSchema[None])
async def batch_set_app_user_status_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([AppUserPerm.PATCH]))],
    data: Annotated[BatchSetAvailable, Body(description="状态设置")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """批量启用/禁用C端用户，禁用后立即失效其在线会话。"""
    service = AppUserService(auth, db, redis)
    await service.set_available(data=data)
    return SuccessResponse(msg="批量修改C端用户状态成功")


@AppUserSecureRouter.put("/password/reset/{id}", summary="重置C端用户密码", response_model=ResponseSchema[None])
async def reset_app_user_password_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([AppUserPerm.RESET_PASSWORD]))],
    id: Annotated[int, Path(description="C端用户ID")],
    data: Annotated[AppUserResetPasswordSchema, Body(description="新密码")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """后台重置C端用户密码，成功后该用户全端下线。"""
    service = AppUserService(auth, db, redis)
    await service.reset_password(id=id, data=data)
    return SuccessResponse(msg="重置C端用户密码成功")


@AppUserRouter.get("/session/{id}", summary="查询C端用户在线会话", response_model=ResponseSchema[list[AppSessionInfo]])
async def get_app_user_session_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([AppUserPerm.SESSION]))],
    id: Annotated[int, Path(description="C端用户ID")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """查询指定C端用户的多端在线会话。"""
    service = AppUserService(auth, db, redis)
    result = await service.list_sessions(id=id)
    return SuccessResponse(data=result, msg="查询在线会话成功")


@AppUserRouter.delete("/session/{id}", summary="强制下线C端用户全部会话", response_model=ResponseSchema[int])
async def force_logout_app_user_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([AppUserPerm.FORCE_LOGOUT]))],
    id: Annotated[int, Path(description="C端用户ID")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """强制下线指定C端用户的全部在线会话。"""
    service = AppUserService(auth, db, redis)
    count = await service.force_logout(id=id)
    return SuccessResponse(data=count, msg=f"已强制下线 {count} 个会话")


@AppUserRouter.delete("/session/{id}/{session_id}", summary="强制下线C端用户指定会话", response_model=ResponseSchema[int])
async def force_logout_app_user_session_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([AppUserPerm.FORCE_LOGOUT]))],
    id: Annotated[int, Path(description="C端用户ID")],
    session_id: Annotated[str, Path(description="会话ID")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """强制下线指定C端用户的单个会话。"""
    service = AppUserService(auth, db, redis)
    count = await service.force_logout(id=id, session_id=session_id)
    return SuccessResponse(data=count, msg="强制下线成功")


@AppUserRouter.get("/log", summary="分页查询C端登录日志", response_model=ResponseSchema[PageResultSchema[AppLoginLogOutSchema]])
async def get_app_login_log_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([AppUserPerm.LOGIN_LOG]))],
    page: Annotated[PaginationQueryParam, Depends()],
    search: Annotated[AppLoginLogQueryParam, Query()],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """分页查询C端登录日志（含登录失败记录）。"""
    service = AppUserService(auth, db, redis)
    result = await service.login_log_page(page_no=page.page_no, page_size=page.page_size, search=search, order_by=page.order_by)
    return SuccessResponse(data=result, msg="查询C端登录日志成功")


@AppUserRouter.get("/oauth/{id}", summary="查询C端用户第三方绑定", response_model=ResponseSchema[list[AppUserOauthOutSchema]])
async def get_app_user_oauth_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([AppUserPerm.OAUTH]))],
    id: Annotated[int, Path(description="C端用户ID")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """查询指定C端用户的第三方登录绑定列表。"""
    service = AppUserService(auth, db, redis)
    result = await service.oauth_list(id=id)
    return SuccessResponse(data=result, msg="查询第三方绑定成功")


@AppUserRouter.delete("/oauth/{id}", summary="解绑C端用户第三方登录", response_model=ResponseSchema[None])
async def unbind_app_user_oauth_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([AppUserPerm.OAUTH]))],
    id: Annotated[int, Path(description="第三方绑定记录ID")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """解绑C端用户的第三方登录记录。"""
    service = AppUserService(auth, db, redis)
    await service.unbind_oauth(id=id)
    return SuccessResponse(msg="解绑第三方登录成功")


# ══════════════════════════ C端个人中心 ══════════════════════════


@AppProfileRouter.get("/info", summary="获取当前登录用户信息", response_model=ResponseSchema[AppUserOutSchema])
async def get_app_profile_controller(user: CurrentAppUser) -> JSONResponse:
    """获取当前C端登录用户的资料。"""
    result = await AppUserProfileService(user).profile()
    return SuccessResponse(data=result, msg="获取用户信息成功")


@AppProfileRouter.put("/update", summary="修改当前登录用户资料", response_model=ResponseSchema[AppUserOutSchema])
async def update_app_profile_controller(
    user: CurrentAppUser,
    data: Annotated[AppUserProfileUpdateSchema, Body(description="资料修改参数")],
) -> JSONResponse:
    """修改当前C端登录用户的昵称、头像、性别、邮箱。"""
    result = await AppUserProfileService(user).update_profile(data=data)
    return SuccessResponse(data=result, msg="修改资料成功")


@AppProfileRouter.put("/password", summary="修改当前登录用户密码", response_model=ResponseSchema[None])
async def change_app_password_controller(
    user: CurrentAppUser,
    data: Annotated[AppUserChangePasswordSchema, Body(description="密码修改参数")],
) -> JSONResponse:
    """修改当前C端登录用户密码，成功后其他会话自动下线。"""
    await AppUserProfileService(user).change_password(data=data)
    return SuccessResponse(msg="修改密码成功")


@AppProfileRouter.get("/oauth", summary="获取当前登录用户第三方绑定", response_model=ResponseSchema[list[AppUserOauthOutSchema]])
async def get_app_profile_oauth_controller(user: CurrentAppUser) -> JSONResponse:
    """获取当前C端登录用户的第三方登录绑定列表。"""
    result = await AppUserProfileService(user).oauth_list()
    return SuccessResponse(data=result, msg="获取第三方绑定成功")
