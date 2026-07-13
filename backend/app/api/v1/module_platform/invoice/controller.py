from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Query, Security, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import ResponseSchema, SuccessResponse
from app.core.base_schema import AuthSchema, PageResultSchema, PaginationQueryParam
from app.core.dependencies import AuthPermission, db_getter
from app.core.router_class import OperationLogRoute

from .schema import InvoiceApplySchema, InvoiceOutSchema, InvoiceQueryParam
from .service import InvoiceTenantService

InvoiceRouter = APIRouter(prefix="/invoice", route_class=OperationLogRoute, tags=["发票管理"])


@InvoiceRouter.post("/apply", status_code=status.HTTP_201_CREATED, summary="申请开票", response_model=ResponseSchema[InvoiceOutSchema])
async def invoice_apply_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:invoice:create"]))],
    data: Annotated[InvoiceApplySchema, Body(description="发票申请参数")],
    db: Annotated[AsyncSession, Depends(db_getter)],
) -> JSONResponse:
    result = await InvoiceTenantService.apply(auth=auth, db=db, data=data, tenant_id=auth.user.tenant_id if auth.user else 0)
    return SuccessResponse(data=result, msg="发票申请成功")


@InvoiceRouter.get("/mine/list", summary="我的发票列表", response_model=ResponseSchema[PageResultSchema[InvoiceOutSchema]])
async def invoice_list_my_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:invoice:query"]))],
    page: Annotated[PaginationQueryParam, Query(description="分页参数")],
    search: Annotated[InvoiceQueryParam, Query(description="发票查询参数")],
    db: Annotated[AsyncSession, Depends(db_getter)],
) -> JSONResponse:
    result = await InvoiceTenantService.list_my(
        auth=auth,
        db=db,
        tenant_id=auth.user.tenant_id if auth.user else 0,
        page_no=page.page_no,
        page_size=page.page_size,
        order_by=page.order_by,
        search=search,
    )
    return SuccessResponse(data=result, msg="查询成功")


@InvoiceRouter.get("/{id}/download", summary="下载发票PDF", response_model=ResponseSchema[dict])
async def invoice_download_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:invoice:download"]))],
    id: Annotated[int, Path(description="发票ID", ge=1)],
    db: Annotated[AsyncSession, Depends(db_getter)],
) -> JSONResponse:
    pdf_url = await InvoiceTenantService.download(auth=auth, db=db, invoice_id=id, tenant_id=auth.user.tenant_id if auth.user else 0)
    return SuccessResponse(msg="下载地址", data={"pdf_url": pdf_url})
