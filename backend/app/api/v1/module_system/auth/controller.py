import json
import secrets
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Path, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi_cache import FastAPICache
from fastapi_cache.decorator import cache
from redis.asyncio.client import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import ErrorResponse, RedirectContentResponse, ResponseSchema, SuccessResponse
from app.config.setting import settings
from app.core.base_schema import AuthSchema, JWTOutSchema
from app.core.dependencies import db_getter, get_current_user, redis_getter
from app.core.exceptions import CustomException
from app.core.logger import logger
from app.core.redis_crud import RedisCURD
from app.core.router_class import OperationLogRoute
from app.core.security import CustomOAuth2PasswordRequestForm

from .oauth_service import (
    STATE_PREFIX,
    OAuthProvider,
    _callback_url,
    build_authorize_url,
    complete_oauth_login,
    oauth_service_error_redirect,
    oauth_service_frontend_redirect_from_token,
    save_oauth_state,
)
from .schema import (
    CaptchaOutSchema,
    EnterPlatformOutSchema,
    ImpersonateOutSchema,
    ImpersonateSchema,
    LoginWithTenantsSchema,
    SelectTenantOutSchema,
    SelectTenantSchema,
    SliderCompleteOutSchema,
    SliderCompleteSchema,
    TenantLookupOutSchema,
    TenantOptionSchema,
    TenantRegisterOutSchema,
    TenantRegisterSchema,
)
from .service import (
    CaptchaService,
    LoginService,
    TenantLookupService,
    TenantRegisterService,
)

AuthRouter = APIRouter(route_class=OperationLogRoute, prefix="/auth", tags=["认证授权"])

_AUTH_TENANTS_NS = "auth_tenants"


@AuthRouter.get("/tenant/{code}", summary="通过编码查询租户", response_model=ResponseSchema[TenantLookupOutSchema])
async def lookup_tenant_controller(
    db: Annotated[AsyncSession, Depends(db_getter)],
    code: Annotated[str, Path(description="租户编码")],
) -> JSONResponse:
    """根据租户编码查询租户信息（用于登录页自动加载租户品牌配置）"""
    data = await TenantLookupService.lookup_by_code(db=db, code=code)
    return SuccessResponse(data=data, msg="查询成功")


@AuthRouter.get("/tenant-by-domain", summary="通过域名查询租户", response_model=ResponseSchema[TenantLookupOutSchema])
async def lookup_tenant_by_domain_controller(
    db: Annotated[AsyncSession, Depends(db_getter)],
    domain: Annotated[str, Query(description="域名（如 tenant.example.com）")],
) -> JSONResponse:
    """根据域名查询租户信息（用于登录页通过访问域名自动识别租户品牌）"""
    data = await TenantLookupService.lookup_by_domain(db=db, domain=domain)
    return SuccessResponse(data=data, msg="查询成功")


@AuthRouter.get("/tenant-options", summary="获取所有租户选项（登录页下拉选择）", response_model=ResponseSchema[list[TenantOptionSchema]])
async def get_tenant_options_controller(
    db: Annotated[AsyncSession, Depends(db_getter)],
) -> JSONResponse:
    """获取所有活跃租户下拉选项"""
    data = await TenantLookupService.list_options(db=db)
    return SuccessResponse(data=data, msg="查询成功")


@AuthRouter.get("/tenant-search", summary="搜索租户（按编码/名称模糊匹配）", response_model=ResponseSchema[list[TenantOptionSchema]])
async def search_tenant_controller(
    db: Annotated[AsyncSession, Depends(db_getter)],
    q: Annotated[str, Query(description="搜索关键字")],
) -> JSONResponse:
    """模糊搜索租户"""
    data = await TenantLookupService.search(db=db, q=q)
    return SuccessResponse(data=data, msg="查询成功")


@AuthRouter.post("/login", summary="登录", response_model=LoginWithTenantsSchema)
async def login_for_access_token_controller(
    request: Request,
    background_tasks: BackgroundTasks,
    redis: Annotated[Redis, Depends(redis_getter)],
    db: Annotated[AsyncSession, Depends(db_getter)],
    login_form: Annotated[CustomOAuth2PasswordRequestForm, Depends()],
) -> JSONResponse | LoginWithTenantsSchema:
    login_result = await LoginService.authenticate_user(request=request, redis=redis, login_form=login_form, db=db, background_tasks=background_tasks)

    logger.info(f"用户{login_form.username}登录成功")

    if settings.DOCS_URL in request.headers.get("referer", ""):
        return login_result
    return SuccessResponse(data=login_result, msg="登录成功")


@AuthRouter.post("/token/refresh", summary="刷新token", response_model=ResponseSchema[JWTOutSchema])
async def get_new_token_controller(
    db: Annotated[AsyncSession, Depends(db_getter)],
    redis: Annotated[Redis, Depends(redis_getter)],
    payload: Annotated[str, Body(description="刷新token参数")],
) -> JSONResponse:
    new_token = await LoginService.refresh_token(db=db, redis=redis, refresh_token=payload)
    return SuccessResponse(data=new_token, msg="刷新成功")


@AuthRouter.get("/captcha/get", summary="获取验证码", response_model=ResponseSchema[CaptchaOutSchema])
async def get_captcha_for_login_controller(
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    captcha = await CaptchaService.get_captcha(redis=redis)
    return SuccessResponse(data=captcha, msg="获取验证码成功")


@AuthRouter.post("/captcha/slider/complete", summary="滑块验证完成", response_model=ResponseSchema[SliderCompleteOutSchema])
async def slider_complete_controller(
    redis: Annotated[Redis, Depends(redis_getter)],
    body: SliderCompleteSchema,
) -> JSONResponse:
    result = await CaptchaService.slider_complete(redis=redis, captcha_key=body.captcha_key)
    return SuccessResponse(data=result, msg="滑块验证成功")


@AuthRouter.post("/logout", summary="退出登录", response_model=ResponseSchema[None], dependencies=[Depends(get_current_user)])
async def logout_controller(
    redis: Annotated[Redis, Depends(redis_getter)],
    payload: Annotated[str, Body(description="退出登录参数")],
) -> JSONResponse:
    if await LoginService.logout(redis=redis, token=payload):
        logger.info("退出成功")
        return SuccessResponse(msg="退出成功")
    return ErrorResponse(msg="退出失败")


@AuthRouter.post("/select-tenant", summary="选择租户", response_model=ResponseSchema[SelectTenantOutSchema], dependencies=[Depends(get_current_user)])
async def select_tenant_controller(
    request: Request,
    auth: Annotated[AuthSchema, Depends(get_current_user)],
    redis: Annotated[Redis, Depends(redis_getter)],
    db: Annotated[AsyncSession, Depends(db_getter)],
    data: Annotated[SelectTenantSchema, Body(description="租户选择参数")],
) -> JSONResponse:
    result = await LoginService(auth, db).select_tenant(request=request, redis=redis, tenant_id=data.tenant_id)
    await FastAPICache.clear(namespace=_AUTH_TENANTS_NS)
    return SuccessResponse(data=result, msg="租户切换成功")


@AuthRouter.post("/enter-platform", summary="进入平台管理模式", response_model=ResponseSchema[EnterPlatformOutSchema], dependencies=[Depends(get_current_user)])
async def enter_platform_controller(
    request: Request,
    auth: Annotated[AuthSchema, Depends(get_current_user)],
    redis: Annotated[Redis, Depends(redis_getter)],
    db: Annotated[AsyncSession, Depends(db_getter)],
) -> JSONResponse:
    result = await LoginService(auth, db).enter_platform(request=request, redis=redis)
    await FastAPICache.clear(namespace=_AUTH_TENANTS_NS)
    return SuccessResponse(data=result, msg="已返回平台管理模式")


@AuthRouter.get("/tenants", summary="获取可选租户列表", response_model=ResponseSchema[list[TenantOptionSchema]], dependencies=[Depends(get_current_user)])
@cache(expire=120, namespace=_AUTH_TENANTS_NS)
async def get_user_tenants_controller(
    auth: Annotated[AuthSchema, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(db_getter)],
) -> JSONResponse:
    service = LoginService(auth, db)
    tenants = await service.get_user_tenants()
    return SuccessResponse(data=tenants, msg="获取租户列表成功")


@AuthRouter.post("/impersonate", summary="平台管理员代签入", response_model=ResponseSchema[ImpersonateOutSchema], dependencies=[Depends(get_current_user)])
async def impersonate_controller(
    request: Request,
    auth: Annotated[AuthSchema, Depends(get_current_user)],
    redis: Annotated[Redis, Depends(redis_getter)],
    db: Annotated[AsyncSession, Depends(db_getter)],
    data: Annotated[ImpersonateSchema, Body(description="代签入参数")],
) -> JSONResponse:
    result = await LoginService(auth, db).impersonate(request=request, redis=redis, tenant_id=data.tenant_id)
    await FastAPICache.clear(namespace=_AUTH_TENANTS_NS)
    return SuccessResponse(data=result, msg="代签入成功")


@AuthRouter.get("/oauth/{provider}/login", summary="第三方OAuth跳转")
async def oauth_login_redirect_controller(
    request: Request,
    redis: Annotated[Redis, Depends(redis_getter)],
    provider: Annotated[OAuthProvider, Path(description="wechat | qq | github | gitee")],
    redirect_uri: Annotated[str | None, Query(description="OAuth 完成后浏览器回到的前端登录页完整 URL")] = None,
) -> RedirectResponse:
    allowed = {"wechat", "qq", "github", "gitee"}
    fe = redirect_uri or settings.OAUTH_FRONTEND_FALLBACK
    if provider not in allowed:
        return RedirectContentResponse(
            url=oauth_service_error_redirect(fe, "不支持的 OAuth 渠道"),
            status_code=302,
        )
    if not redirect_uri:
        return RedirectContentResponse(
            url=oauth_service_error_redirect(fe, "缺少 redirect_uri 参数"),
            status_code=302,
        )
    try:
        state = secrets.token_urlsafe(32)
        await save_oauth_state(
            redis=redis,
            state=state,
            provider=provider,
            frontend_redirect=redirect_uri,
        )
        cb = _callback_url(request, provider)
        url = build_authorize_url(provider=provider, callback_url=cb, state=state)
        return RedirectContentResponse(url=url, status_code=302)
    except CustomException as e:
        return RedirectContentResponse(
            url=oauth_service_error_redirect(redirect_uri, e.msg),
            status_code=302,
        )


@AuthRouter.get("/oauth/{provider}/callback", summary="第三方OAuth回调", include_in_schema=False)
async def oauth_callback_controller(
    request: Request,
    redis: Annotated[Redis, Depends(redis_getter)],
    db: Annotated[AsyncSession, Depends(db_getter)],
    provider: Annotated[OAuthProvider, Path(description="wechat | qq | github | gitee")],
    code: Annotated[str | None, Query(description="OAuth 授权码")] = None,
    state: Annotated[str | None, Query(description="OAuth 状态参数")] = None,
) -> RedirectResponse:
    fe_fallback = settings.OAUTH_FRONTEND_FALLBACK

    async def resolve_frontend() -> str:
        if not state:
            return fe_fallback
        raw = await RedisCURD(redis).get(f"{STATE_PREFIX}{state}")
        if not raw:
            return fe_fallback
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            payload = json.loads(raw)
            return str(payload.get("frontend_redirect") or fe_fallback).strip() or fe_fallback
        except json.JSONDecodeError:
            return fe_fallback

    if provider not in {"wechat", "qq", "github", "gitee"}:
        url = oauth_service_error_redirect(await resolve_frontend(), "不支持的 OAuth 渠道")
        return RedirectContentResponse(url=url, status_code=302)
    if not code or not state:
        url = oauth_service_error_redirect(await resolve_frontend(), "授权被取消或参数不完整")
        return RedirectContentResponse(url=url, status_code=302)
    try:
        token, fe = await complete_oauth_login(
            request=request,
            redis=redis,
            db=db,
            provider=provider,
            code=code,
            state=state,
        )
        success_url = oauth_service_frontend_redirect_from_token(fe, token)
        return RedirectContentResponse(url=success_url, status_code=302)
    except CustomException as e:
        fe = await resolve_frontend()
        return RedirectContentResponse(url=oauth_service_error_redirect(fe, e.msg), status_code=302)


@AuthRouter.post("/tenant/register", status_code=status.HTTP_201_CREATED, summary="租户自助注册", response_model=ResponseSchema[TenantRegisterOutSchema])
async def tenant_register_controller(
    db: Annotated[AsyncSession, Depends(db_getter)],
    data: Annotated[TenantRegisterSchema, Body(description="租户注册参数")],
) -> JSONResponse:
    result = await TenantRegisterService.register(
        db=db,
        username=data.username,
        password=data.password,
        email=data.email,
        tenant_name=data.tenant_name,
    )
    logger.info(f"新租户注册: username={data.username} tenant={result.tenant_name}")
    return SuccessResponse(data=result, msg=result.message)
