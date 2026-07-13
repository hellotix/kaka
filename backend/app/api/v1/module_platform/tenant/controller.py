from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Query, Security, status
from fastapi.responses import JSONResponse
from fastapi_cache import FastAPICache
from fastapi_cache.decorator import cache
from redis.asyncio.client import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import ResponseSchema, SuccessResponse
from app.core.base_schema import AuthSchema, BatchSetAvailable, PageResultSchema, PaginationQueryParam
from app.core.dependencies import AuthPermission, db_getter, get_current_user, redis_getter
from app.core.router_class import OperationLogRoute

from .schema import (
    PackageAvailableOut,
    PackageChangePreviewOut,
    PackagePreviewOut,
    SelfOrderCreate,
    SelfOrderDetailOut,
    SelfOrderListOut,
    SelfOrderOut,
    TenantConfigItem,
    TenantConfigOutSchema,
    TenantCreateSchema,
    TenantOutSchema,
    TenantQueryParam,
    TenantRenewSchema,
    TenantUpdateSchema,
    TenantUserAddSchema,
    TenantUserOutSchema,
    WorkspaceOut,
)
from .service import TenantService

TenantRouter = APIRouter(route_class=OperationLogRoute, prefix="/tenant", tags=["租户管理"])

_TENANT_NS = "tenant"


@TenantRouter.get("/detail/{id}", summary="获取租户详情", response_model=ResponseSchema[TenantOutSchema])
@cache(expire=120, namespace=_TENANT_NS)
async def get_obj_detail_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:tenant:query"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    id: Annotated[int, Path(description="租户ID", ge=1)],
) -> JSONResponse:
    result_dict = await TenantService(auth, db).detail(id=id)
    return SuccessResponse(data=result_dict, msg="获取租户详情成功")


@TenantRouter.get("/list", summary="查询租户列表", response_model=ResponseSchema[PageResultSchema[TenantOutSchema]])
async def get_obj_list_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:tenant:query"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    page: Annotated[PaginationQueryParam, Query(description="分页参数")],
    search: Annotated[TenantQueryParam, Query(description="查询参数")],
) -> JSONResponse:
    order_by = [{"id": "asc"}]
    if page.order_by:
        order_by = page.order_by
    result_dict = await TenantService(auth, db).page(
        page_no=page.page_no,
        page_size=page.page_size,
        search=search,
        order_by=order_by,
    )
    return SuccessResponse(data=result_dict, msg="查询租户列表成功")


@TenantRouter.post("/create", status_code=status.HTTP_201_CREATED, summary="创建租户", response_model=ResponseSchema[TenantOutSchema])
async def create_obj_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:tenant:create"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    data: Annotated[TenantCreateSchema, Body(description="租户创建参数")],
) -> JSONResponse:
    result_dict = await TenantService(auth, db).create(data=data)
    await FastAPICache.clear(namespace=_TENANT_NS)
    return SuccessResponse(data=result_dict, msg="创建租户成功")


@TenantRouter.put("/update/{id}", summary="修改租户", response_model=ResponseSchema[TenantOutSchema])
async def update_obj_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:tenant:update"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    id: Annotated[int, Path(description="租户ID", ge=1)],
    data: Annotated[TenantUpdateSchema, Body(description="租户更新参数")],
) -> JSONResponse:
    result_dict = await TenantService(auth, db).update(id=id, data=data)
    await FastAPICache.clear(namespace=_TENANT_NS)
    return SuccessResponse(data=result_dict, msg="修改租户成功")


@TenantRouter.delete("/delete", summary="删除租户", response_model=ResponseSchema[None])
async def delete_obj_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:tenant:delete"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    ids: Annotated[list[int], Body(description="租户ID列表")],
) -> JSONResponse:
    await TenantService(auth, db).delete(ids=ids)
    await FastAPICache.clear(namespace=_TENANT_NS)
    return SuccessResponse(msg="删除租户成功")


@TenantRouter.patch("/status/batch", summary="批量修改租户状态", response_model=ResponseSchema[None])
async def batch_set_available_obj_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:tenant:patch"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    data: Annotated[BatchSetAvailable, Body(description="状态设置")],
) -> JSONResponse:
    await TenantService(auth, db).set_available(data=data)
    await FastAPICache.clear(namespace=_TENANT_NS)
    return SuccessResponse(msg="批量修改租户状态成功")


@TenantRouter.put("/status/{id}", summary="启/禁用租户", response_model=ResponseSchema[None])
async def toggle_tenant_status_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:tenant:patch"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    id: Annotated[int, Path(description="租户ID", ge=1)],
) -> JSONResponse:
    await TenantService(auth, db).toggle_status(id=id)
    await FastAPICache.clear(namespace=_TENANT_NS)
    return SuccessResponse(msg="修改租户状态成功")


@TenantRouter.get("/{id}/users", summary="获取租户用户列表", response_model=ResponseSchema[list[TenantUserOutSchema]])
@cache(expire=120, namespace=_TENANT_NS)
async def get_tenant_users_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:tenant:query"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    id: Annotated[int, Path(description="租户ID", ge=1)],
) -> JSONResponse:
    result = await TenantService(auth, db).get_tenant_users(tenant_id=id)
    return SuccessResponse(data=result, msg="获取租户用户列表成功")


@TenantRouter.post("/{id}/users", status_code=status.HTTP_201_CREATED, summary="向租户添加用户", response_model=ResponseSchema[None])
async def add_tenant_user_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:tenant:create"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    id: Annotated[int, Path(description="租户ID")],
    data: Annotated[TenantUserAddSchema, Body(description="添加用户参数")],
) -> JSONResponse:
    await TenantService(auth, db).add_tenant_user(tenant_id=id, data=data)
    await FastAPICache.clear(namespace=_TENANT_NS)
    return SuccessResponse(msg="添加用户成功")


@TenantRouter.delete("/{id}/users/{uid}", summary="从租户移除用户", response_model=ResponseSchema[None])
async def remove_tenant_user_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:tenant:delete"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    id: Annotated[int, Path(description="租户ID", ge=1)],
    uid: Annotated[int, Path(description="用户ID", ge=1)],
) -> JSONResponse:
    await TenantService(auth, db).remove_tenant_user(tenant_id=id, user_id=uid)
    await FastAPICache.clear(namespace=_TENANT_NS)
    return SuccessResponse(msg="移除用户成功")


@TenantRouter.get("/{id}/config", summary="获取租户配置", response_model=ResponseSchema[list[TenantConfigOutSchema]])
async def get_tenant_config_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:tenant:query"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    id: Annotated[int, Path(description="租户ID")],
) -> JSONResponse:
    result = await TenantService(auth, db).get_config_items(tenant_id=id)
    return SuccessResponse(data=result, msg="获取租户配置成功")


@TenantRouter.get("/{id}/config/info", summary="获取租户配置（公开-缓存）", response_model=ResponseSchema[list[TenantConfigOutSchema]])
async def get_tenant_config_info_controller(
    redis: Annotated[Redis, Depends(redis_getter)],
    id: Annotated[int, Path(description="租户ID")],
) -> JSONResponse:
    result = await TenantService.get_config_cache_items(redis=redis, tenant_id=id)
    return SuccessResponse(data=result, msg="获取租户配置成功")


@TenantRouter.put("/{id}/config", summary="更新租户配置", response_model=ResponseSchema[list[TenantConfigOutSchema]])
async def update_tenant_config_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:tenant:update"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    redis: Annotated[Redis, Depends(redis_getter)],
    id: Annotated[int, Path(description="租户ID")],
    data: Annotated[list[TenantConfigItem], Body(description="配置项列表")],
) -> JSONResponse:
    config_dict = {item.key: item.value for item in data}
    result = await TenantService(auth, db).update_config(redis=redis, tenant_id=id, config=config_dict)
    await FastAPICache.clear(namespace=_TENANT_NS)
    return SuccessResponse(data=result, msg="更新租户配置成功")


@TenantRouter.put("/renew/{id}", summary="租户续期", response_model=ResponseSchema[TenantOutSchema])
async def renew_tenant_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:tenant:update"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    id: Annotated[int, Path(description="租户ID", ge=1)],
    data: Annotated[TenantRenewSchema, Body(description="续费参数")],
) -> JSONResponse:
    end_time_str = data.end_time.isoformat() if hasattr(data.end_time, "isoformat") else str(data.end_time)
    result = await TenantService(auth, db).renew(tenant_id=id, end_time=end_time_str)
    await FastAPICache.clear(namespace=_TENANT_NS)
    return SuccessResponse(data=result, msg="租户续期成功")


@TenantRouter.get("/{id}/package-change-preview", summary="套餐变更影响预览", response_model=ResponseSchema[PackageChangePreviewOut])
async def package_change_preview_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:tenant:query"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    id: Annotated[int, Path(description="租户ID")],
    new_package_id: Annotated[int, Query(description="目标套餐ID")],
) -> JSONResponse:
    result = await TenantService(auth, db).package_change_preview(tenant_id=id, new_package_id=new_package_id)
    return SuccessResponse(data=result, msg="套餐变更预览成功")


@TenantRouter.get("/package/available", summary="可选套餐列表", response_model=ResponseSchema[PackageAvailableOut])
async def package_available_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["tenant:package:query"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
) -> JSONResponse:
    result = await TenantService.get_available_packages(auth=auth, db=db, tenant_id=auth.user.tenant_id if auth.user else 0)
    return SuccessResponse(data=result, msg="查询成功")


@TenantRouter.get("/package/preview", summary="套餐变更影响预览", response_model=ResponseSchema[PackagePreviewOut])
async def package_preview_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["tenant:package:query"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    target_package_id: Annotated[int, Query(ge=1, description="目标套餐ID")],
) -> JSONResponse:
    result = await TenantService.preview_package_change(auth=auth, db=db, tenant_id=auth.user.tenant_id if auth.user else 0, target_package_id=target_package_id)
    return SuccessResponse(data=result, msg="查询成功")


@TenantRouter.post("/order/create", status_code=status.HTTP_201_CREATED, summary="创建自助订单", response_model=ResponseSchema[SelfOrderOut])
async def order_create_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["tenant:order:create"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    data: Annotated[SelfOrderCreate, Body(description="自助订单创建参数")],
) -> JSONResponse:
    result = await TenantService.create_self_order(auth=auth, db=db, tenant_id=auth.user.tenant_id if auth.user else 0, data=data)
    return SuccessResponse(data=result, msg="订单创建成功")


@TenantRouter.get("/order/list", summary="我的订单列表", response_model=ResponseSchema[SelfOrderListOut])
async def order_list_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["tenant:order:query"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    page: Annotated[PaginationQueryParam, Query(description="分页参数")],
) -> JSONResponse:
    result = await TenantService.get_self_order_list(
        auth=auth,
        db=db,
        tenant_id=auth.user.tenant_id if auth.user else 0,
        page_no=page.page_no,
        page_size=page.page_size,
        order_by=page.order_by,
    )
    return SuccessResponse(data=result, msg="查询成功")


@TenantRouter.get("/order/detail/{order_id}", summary="订单详情", response_model=ResponseSchema[SelfOrderDetailOut])
async def order_detail_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["tenant:order:query"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    order_id: Annotated[int, Path(ge=1, description="订单ID")],
) -> JSONResponse:
    result = await TenantService.get_self_order_detail(auth=auth, db=db, order_id=order_id)
    return SuccessResponse(data=result, msg="查询成功")


@TenantRouter.get("/workspace", summary="租户工作台概览", response_model=ResponseSchema[WorkspaceOut])
async def tenant_workspace_controller(
    auth: Annotated[AuthSchema, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(db_getter)],
) -> JSONResponse:
    result = await TenantService.get_workspace_data(auth=auth, db=db, tenant_id=auth.user.tenant_id if auth.user else 0)
    return SuccessResponse(data=result, msg="查询成功")
