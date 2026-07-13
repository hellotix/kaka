"""API Token Controller：CRUD + reveal 二次验证
"""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Query, Security
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import ResponseSchema, SuccessResponse
from app.core.base_schema import AuthSchema, PageResultSchema, PaginationQueryParam
from app.core.dependencies import AuthPermission, db_getter
from app.core.router_class import OperationLogRoute

from .schema import (
    ApiTokenCreatedSchema,
    ApiTokenCreateSchema,
    ApiTokenOutSchema,
    ApiTokenQueryParam,
    ApiTokenResetSchema,
    ApiTokenRevealOutSchema,
    ApiTokenRevealSchema,
)
from .service import ApiTokenService

ApiTokenRouter = APIRouter(route_class=OperationLogRoute, prefix="/token", tags=["平台-API令牌"])


@ApiTokenRouter.post("/create", summary="创建 API Token", response_model=ResponseSchema[ApiTokenCreatedSchema])
async def create_token_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_system:token:create"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    data: Annotated[ApiTokenCreateSchema, Body(description="创建参数")],
) -> JSONResponse:
    """创建后会完整返回明文 token，请立即保存。"""
    result = await ApiTokenService(auth, db).create(data=data)
    return SuccessResponse(data=result, msg="创建 token 成功")


@ApiTokenRouter.get("/list", summary="查询 token 列表", response_model=ResponseSchema[PageResultSchema[ApiTokenOutSchema]])
async def get_token_list_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_system:token:query"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    page: Annotated[PaginationQueryParam, Query(description="分页参数")],
    search: Annotated[ApiTokenQueryParam, Query(description="查询参数")],
) -> JSONResponse:
    result = await ApiTokenService(auth, db).page(
        page_no=page.page_no,
        page_size=page.page_size,
        search=search,
        order_by=page.order_by,
    )
    return SuccessResponse(data=result, msg="查询成功")


@ApiTokenRouter.get("/detail/{id}", summary="token 详情", response_model=ResponseSchema[ApiTokenOutSchema])
async def get_token_detail_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_system:token:detail"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    id: Annotated[int, Path(description="token ID", ge=1)],
) -> JSONResponse:
    result = await ApiTokenService(auth, db).detail(id=id)
    return SuccessResponse(data=result, msg="查询成功")


@ApiTokenRouter.post("/{id}/reset", summary="重置 token（重新生成 secret）", response_model=ResponseSchema[ApiTokenCreatedSchema])
async def reset_token_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_system:token:reset"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    id: Annotated[int, Path(description="token ID", ge=1)],
    data: Annotated[ApiTokenResetSchema, Body(description="可选项")],
) -> JSONResponse:
    """重置后会再次返回完整明文（仅此一次）。"""
    result = await ApiTokenService(auth, db).reset(id=id, data=data)
    return SuccessResponse(data=result, msg="重置 token 成功")


@ApiTokenRouter.patch("/{id}/status", summary="启用/禁用 token", response_model=ResponseSchema[None])
async def set_token_status_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_system:token:patch"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    id: Annotated[int, Path(description="token ID", ge=1)],
    status: Annotated[int, Body(description="状态", ge=0, le=2)],
) -> JSONResponse:
    await ApiTokenService(auth, db).set_status(id=id, status=status)
    return SuccessResponse(msg="状态修改成功")


@ApiTokenRouter.delete("/{id}", summary="删除 token", response_model=ResponseSchema[None])
async def delete_token_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_system:token:delete"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    id: Annotated[int, Path(description="token ID", ge=1)],
) -> JSONResponse:
    await ApiTokenService(auth, db).delete(id=id)
    return SuccessResponse(msg="删除成功")


@ApiTokenRouter.post("/{id}/reveal", summary="查看 token 明文（需二次验证）", response_model=ResponseSchema[ApiTokenRevealOutSchema])
async def reveal_token_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_system:token:reveal"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    id: Annotated[int, Path(description="token ID", ge=1)],
    data: Annotated[ApiTokenRevealSchema, Body(description="需输入当前用户密码")],
) -> JSONResponse:
    """高权限端点：会返回完整明文，需要二次密码验证。"""
    result = await ApiTokenService(auth, db).reveal(id=id, data=data)
    return SuccessResponse(data=result, msg="reveal 成功")
