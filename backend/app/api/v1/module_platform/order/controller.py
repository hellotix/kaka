from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Query, Request, Security, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import RET, EnvironmentEnum
from app.common.response import ErrorResponse, ResponseSchema, SuccessResponse
from app.config.setting import settings
from app.core.base_schema import AuthSchema, PageResultSchema, PaginationQueryParam
from app.core.dependencies import AuthPermission, db_getter
from app.core.exceptions import CustomException
from app.core.logger import logger
from app.core.router_class import OperationLogRoute
from app.utils.payment import get_mock_gateway

from .schema import (
    OrderCreateSchema,
    OrderOutSchema,
    OrderQueryParam,
    OrderStatusMessage,
    PaymentCreateOut,
    PaymentStatusOut,
    RefundApplySchema,
    RefundReviewSchema,
)
from .service import OrderService, PaymentService, RefundService

OrderRouter = APIRouter(route_class=OperationLogRoute, prefix="/order", tags=["订单管理"])


@OrderRouter.post("/create", status_code=status.HTTP_201_CREATED, summary="创建订单", response_model=ResponseSchema[OrderOutSchema])
async def order_create_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:order:create"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    data: Annotated[OrderCreateSchema, Body(description="订单创建参数")],
) -> JSONResponse:
    result = await OrderService.create_order(auth=auth, db=db, data=data)
    return SuccessResponse(data=result, msg="订单创建成功")


@OrderRouter.get("/detail/{order_id}", summary="订单详情", response_model=ResponseSchema[OrderOutSchema])
async def order_detail_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:order:query"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    order_id: Annotated[int, Path(description="订单ID", ge=1)],
) -> JSONResponse:
    order = await OrderService.get_detail(auth=auth, db=db, order_id=order_id)
    if not order:
        raise CustomException(msg="订单不存在", code=RET.NOT_FOUND.code, status_code=404)
    return SuccessResponse(data=order)


@OrderRouter.get("/list", summary="订单列表", response_model=ResponseSchema[PageResultSchema[OrderOutSchema]])
async def order_list_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:order:query"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    page: Annotated[PaginationQueryParam, Query(description="分页参数")],
    search: Annotated[OrderQueryParam, Query(description="查询参数")],
) -> JSONResponse:
    items, total = await OrderService.get_list(
        auth=auth,
        db=db,
        page_no=page.page_no,
        page_size=page.page_size,
        order_by=page.order_by,
        search=search,
    )
    offset = (page.page_no - 1) * page.page_size
    result = PageResultSchema(
        page_no=page.page_no,
        page_size=page.page_size,
        total=total,
        has_next=offset + page.page_size < total,
        items=items,
    )
    return SuccessResponse(data=result)


@OrderRouter.post("/cancel/{order_id}", summary="取消订单", response_model=ResponseSchema[OrderStatusMessage])
async def order_cancel_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:order:update"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    order_id: Annotated[int, Path(description="订单ID", ge=1)],
) -> JSONResponse:
    result = await OrderService.cancel_order(auth=auth, db=db, order_id=order_id)
    return SuccessResponse(data=result, msg=result.message)


@OrderRouter.post("/pay/{order_id}", summary="创建支付（获取支付 URL/二维码）", response_model=ResponseSchema[PaymentCreateOut])
async def order_pay_create_controller(
    request: Request,
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:order:update"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    order_id: Annotated[int, Path(description="订单ID", ge=1)],
    method: Annotated[str, Query(description="支付渠道: alipay / wxpay(留空=自动)")] = "",
) -> JSONResponse:
    base_url = str(request.base_url).rstrip("/")
    result = await PaymentService.create_payment(auth=auth, db=db, order_id=order_id, method=method, notify_base_url=base_url)
    return SuccessResponse(data=result, msg="支付信息已生成")


@OrderRouter.get("/status/{order_id}", summary="查询支付状态（供前端轮询）", response_model=ResponseSchema[PaymentStatusOut])
async def order_pay_status_controller(
    db: Annotated[AsyncSession, Depends(db_getter)],
    order_id: Annotated[int, Path(description="订单ID", ge=1)],
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:order:query"], check_data_scope=False))],
) -> JSONResponse:
    result = await OrderService.check_payment_status(auth=auth, db=db, order_id=order_id)
    return SuccessResponse(data=result)


@OrderRouter.post("/callback/{method}", summary="支付回调（统一入口）", response_model=ResponseSchema[dict])
async def order_pay_callback_controller(
    db: Annotated[AsyncSession, Depends(db_getter)],
    method: Annotated[str, Path(description="支付渠道: alipay / wxpay / mock")],
    data: Annotated[dict, Body(description="支付回调数据")],
) -> JSONResponse:
    try:
        auth = AuthSchema(check_data_scope=False)
        result = await PaymentService.handle_callback(auth=auth, db=db, method=method, callback_data=data)
        logger.info(f"支付回调处理成功: {result}")
        return SuccessResponse(data=result)
    except CustomException as e:
        logger.warning(f"支付回调处理失败: {e}")
        return ErrorResponse(msg=str(e))


@OrderRouter.post("/mock/callback", summary="Mock 支付回调（仅开发/测试环境可用）", response_model=ResponseSchema[dict])
async def order_pay_mock_callback_controller(
    db: Annotated[AsyncSession, Depends(db_getter)],
    order_id: Annotated[int, Body(description="订单ID", ge=1)],
) -> JSONResponse:
    # Mock 回调仅在 DEV 环境暴露；生产环境必须通过真实支付网关的 webhook 触发
    if settings.ENVIRONMENT != EnvironmentEnum.DEV:
        raise CustomException(
            msg="Mock 支付回调仅在开发环境可用",
            code=RET.FORBIDDEN.code,
            status_code=403,
        )

    from .service import OrderService

    auth = AuthSchema(check_data_scope=False)
    order = await OrderService.get_by_id(auth, db, order_id)
    if not order:
        raise CustomException(msg="订单不存在", code=RET.NOT_FOUND.code, status_code=404)

    mock_gw = get_mock_gateway()
    callback_data = mock_gw.get_mock_callback_data(order.id, order.order_no)
    result = await PaymentService.handle_callback(auth=auth, db=db, method="mock", callback_data=callback_data)
    logger.info(f"Mock 支付回调触发: order_id={order_id}")
    return SuccessResponse(data=result, msg="模拟支付成功")


@OrderRouter.get("/refund/list", summary="退款审核列表", response_model=ResponseSchema[PageResultSchema[OrderOutSchema]])
async def order_refund_list_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:order:query"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    page: Annotated[PaginationQueryParam, Query(description="分页参数")],
    status: Annotated[int | None, Query(description="退款状态筛选")] = None,
) -> JSONResponse:
    offset = (page.page_no - 1) * page.page_size
    items, total = await RefundService.get_list(auth=auth, db=db, refund_status=status, offset=offset, limit=page.page_size)
    result = PageResultSchema(
        page_no=page.page_no,
        page_size=page.page_size,
        total=total,
        has_next=offset + page.page_size < total,
        items=items,
    )
    return SuccessResponse(data=result)


@OrderRouter.put("/approve/{refund_id}", summary="批准退款", response_model=ResponseSchema[OrderStatusMessage])
async def order_refund_approve_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:order:update"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    refund_id: Annotated[int, Path(description="订单ID", ge=1)],
) -> JSONResponse:
    result = await RefundService.approve(
        auth=auth,
        db=db,
        refund_id=refund_id,
        reviewer_id=auth.user.id,
        operator_name=auth.user.name or "",
    )
    return SuccessResponse(data=result, msg=result.message)


@OrderRouter.put("/reject/{refund_id}", summary="驳回退款", response_model=ResponseSchema[OrderStatusMessage])
async def order_refund_reject_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:order:update"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    refund_id: Annotated[int, Path(description="订单ID", ge=1)],
    data: Annotated[RefundReviewSchema, Body(description="退款驳回数据")],
) -> JSONResponse:
    result = await RefundService.reject(
        auth=auth,
        db=db,
        refund_id=refund_id,
        reviewer_id=auth.user.id,
        data=data,
        operator_name=auth.user.name or "",
    )
    return SuccessResponse(data=result, msg=result.message)


@OrderRouter.post("/tenant/create", status_code=status.HTTP_201_CREATED, summary="创建订单", response_model=ResponseSchema[OrderOutSchema])
async def tenant_order_create_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:order:create"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    data: Annotated[OrderCreateSchema, Body(description="订单创建数据")],
) -> JSONResponse:
    if auth.user is None or data.tenant_id != auth.user.tenant_id:
        raise CustomException(msg="无权操作", code=RET.FORBIDDEN.code, status_code=403)
    result = await OrderService.create_order(auth=auth, db=db, data=data)
    return SuccessResponse(data=result, msg="订单创建成功")


@OrderRouter.post("/tenant/refund/apply/{order_id}", summary="申请退款", response_model=ResponseSchema[OrderOutSchema])
async def order_refund_apply_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_platform:order:refund"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    order_id: Annotated[int, Path(description="订单ID", ge=1)],
    data: Annotated[RefundApplySchema, Body(description="退款申请数据")],
) -> JSONResponse:
    result = await RefundService.apply(auth=auth, db=db, data=data, order_id=order_id)
    return SuccessResponse(data=result, msg="退款申请已提交")
