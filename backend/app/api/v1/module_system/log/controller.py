from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Query, Security
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import ResponseSchema, SuccessResponse
from app.core.base_schema import AuthSchema, PageResultSchema, PaginationQueryParam
from app.core.dependencies import AuthPermission, db_getter, get_current_user
from app.core.router_class import OperationLogRoute

from .schema import (
    LoginLogDetailOutSchema,
    LoginLogOutSchema,
    LoginLogQueryParam,
    OperationLogDetailOutSchema,
    OperationLogOutSchema,
    OperationLogQueryParam,
)
from .service import LoginLogService, OperationLogService

LogRouter = APIRouter(route_class=OperationLogRoute, prefix="/log", tags=["日志管理"])


@LogRouter.get("/login/detail/{id}", summary="获取登录日志详情", response_model=ResponseSchema[LoginLogDetailOutSchema])
async def get_log_detail_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_system:login_log:query"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    id: Annotated[int, Path(description="登录日志ID", ge=1)],
) -> JSONResponse:
    result_dict = await LoginLogService(auth, db).detail(id=id)
    return SuccessResponse(data=result_dict, msg="获取登录日志详情成功")


@LogRouter.get("/login/list", summary="查询登录日志列表", response_model=ResponseSchema[PageResultSchema[LoginLogOutSchema]])
async def get_log_list_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_system:login_log:query"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    page: Annotated[PaginationQueryParam, Query(description="分页参数")],
    search: Annotated[LoginLogQueryParam, Query(description="登录日志查询参数")],
) -> JSONResponse:
    result_dict = await LoginLogService(auth, db).page(
        page_no=page.page_no,
        page_size=page.page_size,
        search=search,
        order_by=page.order_by,
    )
    return SuccessResponse(data=result_dict, msg="查询登录日志列表成功")


@LogRouter.delete("/login/delete", summary="删除登录日志", response_model=ResponseSchema)
async def delete_log_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_system:login_log:delete"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    ids: Annotated[list[int], Body(description="ID列表")],
) -> JSONResponse:
    await LoginLogService(auth, db).delete(ids=ids)
    return SuccessResponse(msg="删除登录日志成功")


@LogRouter.get("/operation/detail/{id}", summary="获取操作日志详情", response_model=ResponseSchema[OperationLogDetailOutSchema], dependencies=[Security(AuthPermission(["module_system:log:query"]))])
async def get_operation_log_detail_controller(
    auth: Annotated[AuthSchema, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(db_getter)],
    id: Annotated[int, Path(description="操作日志ID", gt=0)],
) -> JSONResponse:
    result_dict = await OperationLogService(auth, db).detail(id=id)
    return SuccessResponse(data=result_dict, msg="获取操作日志详情成功")


@LogRouter.get(
    "/operation/list", summary="获取操作日志列表", response_model=ResponseSchema[PageResultSchema[OperationLogOutSchema]], dependencies=[Security(AuthPermission(["module_system:log:query"]))],
)
async def get_operation_log_list_controller(
    auth: Annotated[AuthSchema, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(db_getter)],
    page: Annotated[PaginationQueryParam, Query(description="分页参数")],
    search: Annotated[OperationLogQueryParam, Query(description="操作日志查询参数")],
) -> JSONResponse:
    result_dict = await OperationLogService(auth, db).page(
        page_no=page.page_no,
        page_size=page.page_size,
        search=search,
        order_by=page.order_by,
    )
    return SuccessResponse(data=result_dict, msg="查询操作日志列表成功")


@LogRouter.delete("/operation/delete", summary="删除操作日志", response_model=ResponseSchema, dependencies=[Security(AuthPermission(["module_system:log:delete"]))])
async def delete_operation_log_controller(
    auth: Annotated[AuthSchema, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(db_getter)],
    ids: Annotated[list[int], Body(description="ID列表")],
) -> JSONResponse:
    await OperationLogService(auth, db).delete(ids=ids)
    return SuccessResponse(msg="删除操作日志成功")
