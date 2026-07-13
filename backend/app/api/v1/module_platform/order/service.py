import secrets
import string
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.module_system.dept.model import DeptModel
from app.api.v1.module_system.role.model import RoleModel
from app.api.v1.module_system.user.model import UserModel
from app.core.base_schema import AuthSchema
from app.core.database import async_db_session
from app.core.event_bus import EventBus
from app.core.exceptions import CustomException
from app.core.logger import logger
from app.utils.payment import create_payment_gateway

from ..package.model import PackageModel
from ..tenant.model import TenantModel
from .crud import OrderCRUD
from .model import OrderModel
from .schema import (
    OrderCreateInternalSchema,
    OrderCreateSchema,
    OrderOutSchema,
    OrderQueryParam,
    OrderStatusMessage,
    OrderUpdateInternalSchema,
    PaymentCreateOut,
    PaymentStatusOut,
    RefundApplySchema,
    RefundReviewSchema,
)


def _generate_order_no() -> str:
    """生成订单号：YYYYMMDD + 10位加密安全随机数（碰撞概率极低）。

    使用 :func:`secrets.choice` 而非 ``random``，避免伪随机带来的可预测性。
    """
    today = datetime.now().strftime("%Y%m%d")
    rand = "".join(secrets.choice(string.digits) for _ in range(10))
    return f"{today}{rand}"


def _generate_refund_no() -> str:
    """生成退款单号"""
    today = datetime.now().strftime("%Y%m%d")
    suffix = "".join(secrets.choice(string.digits) for _ in range(6))
    return f"RF{today}{suffix}"


class OrderService:
    """订单管理服务
    """

    @classmethod
    async def get_by_id(cls, auth: AuthSchema, db: AsyncSession, order_id: int) -> OrderModel | None:
        """获取订单模型（仅供内部 mock 等场景使用）"""
        return await OrderCRUD(auth, db).get_by_id(order_id)

    @classmethod
    async def create_order(cls, auth: AuthSchema, db: AsyncSession, data: OrderCreateSchema, amount: int | None = None) -> OrderOutSchema:
        """创建订单

        套餐订单：amount 从套餐价格自动计算
        免费订单（amount=0）：自动激活

        参数:
        - auth (AuthSchema): 认证信息模型
        - data (OrderCreateSchema): 订单创建模型
        - amount (int | None): 订单金额(分)，None 时自动计算

        返回:
        - OrderOutSchema: 新创建的订单详情
        """
        if amount is None:
            pkg = await db.get(PackageModel, data.package_id)
            if not pkg:
                raise CustomException(msg=f"套餐[{data.package_id}]不存在或已删除")
            amount = pkg.price

        order = await OrderCRUD(auth, db).create(
            OrderCreateInternalSchema(
                order_no=_generate_order_no(),
                tenant_id=data.tenant_id,
                package_id=data.package_id,
                order_type=data.order_type,
                amount=amount,
                expire_time=datetime.now() + timedelta(minutes=15),
            ),
        )

        # 免费订单自动激活
        if amount == 0:
            await OrderCRUD(auth, db).update(
                order.id,
                OrderUpdateInternalSchema(status=1, pay_method="free", pay_time=datetime.now()),
            )
            await PaymentService._activate_tenant_package(auth, db, order)
            await db.refresh(order)

        return OrderOutSchema.model_validate(order)

    @classmethod
    async def get_detail(cls, auth: AuthSchema, db: AsyncSession, order_id: int) -> OrderOutSchema | None:
        """订单详情

        参数:
        - auth (AuthSchema): 认证信息模型
        - order_id (int): 订单ID

        返回:
        - OrderOutSchema | None: 订单详情，不存在时返回 None
        """
        order = await OrderCRUD(auth, db).get_by_id(order_id)
        return OrderOutSchema.model_validate(order) if order else None

    @classmethod
    async def get_list(
        cls,
        auth: AuthSchema,
        db: AsyncSession,
        page_no: int,
        page_size: int,
        search: OrderQueryParam,
        order_by: list[dict[str, str]] | None = None,
    ) -> tuple[list, int]:
        """订单列表

        参数:
        - auth (AuthSchema): 认证信息模型
        - page_no (int): 当前页码
        - page_size (int): 每页数量
        - search (OrderQueryParam): 查询参数
        - order_by (list[dict] | None): 排序字段

        返回:
        - tuple[list, int]: (订单列表, 总数)
        """
        offset = (page_no - 1) * page_size
        tenant_id = search.tenant_id[1] if isinstance(search.tenant_id, tuple) else search.tenant_id
        status = search.status[1] if isinstance(search.status, tuple) else search.status
        refund_status = search.refund_status[1] if isinstance(search.refund_status, tuple) else search.refund_status
        order_type = search.order_type[1] if isinstance(search.order_type, tuple) else search.order_type
        rows, total = await OrderCRUD(auth, db).query(
            tenant_id=tenant_id,
            status=status,
            refund_status=refund_status,
            order_type=order_type,
            offset=offset,
            limit=page_size,
        )
        items = [OrderOutSchema.model_validate(r) for r in rows]
        return items, total

    @classmethod
    async def cancel_order(cls, auth: AuthSchema, db: AsyncSession, order_id: int) -> OrderStatusMessage:
        """取消订单

        参数:
        - auth (AuthSchema): 认证信息模型
        - order_id (int): 订单ID

        返回:
        - OrderStatusMessage: 取消结果
        """
        crud = OrderCRUD(auth, db)
        order = await crud.get_by_id(order_id)
        if not order:
            raise CustomException(msg="该数据不存在")
        if order.status != 0:
            raise CustomException(msg="仅待支付订单可取消")
        await crud.update(order_id, OrderUpdateInternalSchema(status=2))
        return OrderStatusMessage(id=order.id, status=2, message="已取消")

    @classmethod
    async def check_payment_status(cls, auth: AuthSchema, db: AsyncSession, order_id: int) -> PaymentStatusOut:
        """查询订单支付状态（供前端轮询用）

        参数:
        - auth (AuthSchema): 认证信息模型
        - order_id (int): 订单ID

        返回:
        - PaymentStatusOut: 支付状态信息
        """
        order = await OrderCRUD(auth, db).get_by_id(order_id)
        if not order:
            return PaymentStatusOut(exists=False)
        return PaymentStatusOut(
            exists=True,
            order_id=order.id,
            status=order.status,
            paid=order.status == 1,
            pay_method=order.pay_method,
            pay_time=order.pay_time.isoformat() if order.pay_time else None,
        )

    @staticmethod
    async def cancel_expired_orders() -> None:
        now = datetime.now()
        async with async_db_session() as session:
            async with session.begin():
                result = await session.execute(
                    sa_update(OrderModel)
                    .where(OrderModel.status == 0)
                    .where(OrderModel.expire_time < now)
                    .where(OrderModel.is_deleted == False)  # noqa: E712
                    .values(status=2),
                )
            rowcount = getattr(result, "rowcount", 0)
            logger.info(f"超时订单取消: 已取消 {rowcount} 条订单")


class PaymentService:
    """支付管理服务
    """

    @classmethod
    async def create_payment(cls, auth: AuthSchema, db: AsyncSession, order_id: int, method: str, notify_base_url: str) -> PaymentCreateOut:
        """创建支付（调用支付网关）

        参数:
        - auth (AuthSchema): 认证信息模型
        - order_id (int): 订单ID
        - method (str): 支付方式(alipay/wxpay)
        - notify_base_url (str): 回调基础URL

        返回:
        - PaymentCreateOut: 支付创建结果（支付URL/二维码）
        """
        order = await OrderCRUD(auth, db).get_by_id(order_id)
        if not order:
            raise CustomException(msg="该数据不存在")
        if order.status != 0:
            raise CustomException(msg="订单状态异常，无法支付")
        if order.amount <= 0:
            raise CustomException(msg="免费订单无需支付")

        pkg = await db.get(PackageModel, order.package_id)
        subject = f"FastapiAdmin - {pkg.name}" if pkg else "FastapiAdmin 套餐"

        notify_url = f"{notify_base_url}/api/v1/platform/payment/callback/{method}" if method else ""

        gateway = create_payment_gateway(method)
        info = await gateway.create_payment(
            order_no=order.order_no,
            amount=order.amount,
            subject=subject,
            notify_url=notify_url,
        )
        return PaymentCreateOut(
            pay_url=info.pay_url,
            qr_code_url=info.qr_code_url,
            trade_no=info.trade_no,
            order_id=order.id,
            order_no=order.order_no,
            amount=order.amount,
        )

    @classmethod
    async def handle_callback(cls, auth: AuthSchema, db: AsyncSession, method: str, callback_data: dict) -> dict:
        """处理支付回调

        参数:
        - auth (AuthSchema): 认证信息模型
        - method (str): 支付方式
        - callback_data (dict): 支付网关回调数据

        返回:
        - dict: 处理结果
        """
        gateway = create_payment_gateway(method)
        callback_result = await gateway.verify_callback(callback_data)

        if not callback_result.verified:
            logger.warning(f"支付回调验签失败: method={method} data={callback_data}")
            raise CustomException(msg="支付回调验签失败")

        order_no = callback_data.get("order_no") or callback_data.get("out_trade_no", "")
        o_crud = OrderCRUD(auth, db)
        order = None
        if order_no:
            order = await o_crud.get_by_order_no(order_no)
        elif callback_result.order_id:
            order = await o_crud.get_by_id(callback_result.order_id)

        if not order:
            raise CustomException(msg="该数据不存在")
        if order.status != 0:
            raise CustomException(msg="订单状态异常")
        if order.amount != callback_result.amount and callback_result.amount > 0:
            raise CustomException(msg="金额不一致")

        pid = order.package_id
        tid = order.tenant_id
        otype = order.order_type
        oid = order.id

        await o_crud.update(
            oid,
            OrderUpdateInternalSchema(
                status=1,
                pay_method=method,
                pay_time=datetime.now(),
                transaction_id=callback_result.transaction_id,
                raw_response=str(callback_result.raw) if callback_result.raw else None,
            ),
        )

        # order 已被 update refresh，直接传给激活方法
        await PaymentService._activate_tenant_package(auth, db, order)

        logger.info(f"支付回调处理完成: order_id={oid} method={method} tenant_id={tid} type={otype}")

        # SSE 推送支付成功通知
        _pkg = await db.get(PackageModel, pid)
        await EventBus.publish_tenant(
            tid,
            {
                "type": "payment_success",
                "order_no": order.order_no,
                "amount": order.amount,
                "package_name": _pkg.name if _pkg else "",
            },
        )

        return {"order_id": oid, "status": 1, "message": "支付成功"}

    @classmethod
    async def _activate_tenant_package(cls, auth: AuthSchema, db: AsyncSession, order: OrderModel) -> None:
        """支付成功后激活套餐

        参数:
        - auth (AuthSchema): 认证信息模型
        - order (OrderModel): 订单模型

        返回:
        - None
        """
        pkg = await db.get(PackageModel, order.package_id)
        if not pkg:
            logger.warning(f"支付回调：套餐 {order.package_id} 不存在，跳过激活")
            return

        tenant = await db.get(TenantModel, order.tenant_id)
        if not tenant:
            logger.warning(f"支付回调：租户 {order.tenant_id} 不存在，跳过激活")
            return

        now = datetime.now()
        period_months = order.period_count or 1
        duration = timedelta(days=30 * period_months)

        if order.order_type == "new":
            tenant.package_id = order.package_id
            tenant.start_time = now
            tenant.end_time = now + duration
            tenant.status = 0
            logger.info(f"租户[{tenant.name}]新开通 {pkg.name}，有效期至 {tenant.end_time}")

        elif order.order_type == "renew":
            base = tenant.end_time if tenant.end_time and tenant.end_time > now else now
            tenant.end_time = base + duration
            tenant.status = 0
            logger.info(f"租户[{tenant.name}]续费 {pkg.name}，续至 {tenant.end_time}")

        elif order.order_type in ("upgrade", "downgrade"):
            if order.order_type == "downgrade":
                await PaymentService._check_downgrade_quota(auth, db, order.tenant_id, pkg)
            tenant.package_id = order.package_id
            tenant.status = 0
            logger.info(f"租户[{tenant.name}]套餐变更 {'升级' if order.order_type == 'upgrade' else '降级'} → {pkg.name}")

        await db.flush()

    @classmethod
    async def _check_downgrade_quota(cls, auth: AuthSchema, db: AsyncSession, tenant_id: int, new_pkg: "PackageModel") -> None:
        """降级前检查：租户当前资源数是否超过新套餐限额

        参数:
        - auth (AuthSchema): 认证信息模型
        - tenant_id (int): 租户ID
        - new_pkg (object): 目标套餐

        返回:
        - None
        """
        checks = {
            "用户": (UserModel, new_pkg.max_users),
            "角色": (RoleModel, new_pkg.max_roles),
            "部门": (DeptModel, new_pkg.max_depts),
        }

        for label, (model, limit) in checks.items():
            if limit <= 0:
                continue
            count_stmt = (
                select(func.count())
                .select_from(model)
                .where(
                    model.tenant_id == tenant_id,
                    model.is_deleted.is_(False),
                )
            )
            result = await db.execute(count_stmt)
            current = result.scalar() or 0
            if current > limit:
                raise CustomException(msg=f"降级失败：当前租户已有 {current} 个{label}，超过目标套餐限额 {limit}")


class RefundService:
    """退款管理服务
    """

    @classmethod
    async def apply(cls, auth: AuthSchema, db: AsyncSession, data: RefundApplySchema, order_id: int) -> OrderOutSchema:
        """申请退款

        参数:
        - auth (AuthSchema): 认证信息模型
        - data (RefundApplySchema): 退款申请模型
        - order_id (int): 订单ID

        返回:
        - OrderOutSchema: 更新后的订单详情
        """
        crud = OrderCRUD(auth, db)
        order = await crud.get_by_id(order_id)
        if not order:
            raise CustomException(msg="该数据不存在")
        if order.status != 1:
            raise CustomException(msg="仅已支付订单可退款")
        if order.amount == 0:
            raise CustomException(msg="免费套餐不支持退款")
        if order.pay_time and (datetime.now() - order.pay_time).days > 7:
            raise CustomException(msg="已超过 7 天退款时限")
        if order.refund_status and order.refund_status != 3:
            raise CustomException(msg="存在进行中的退款申请")

        orders = await crud.update(
            order_id,
            OrderUpdateInternalSchema(
                refund_no=_generate_refund_no(),
                refund_amount=order.amount,
                refund_reason=data.reason,
                refund_status=1,
            ),
        )
        return OrderOutSchema.model_validate(orders)

    @classmethod
    async def get_list(cls, auth: AuthSchema, db: AsyncSession, refund_status: int | None, offset: int, limit: int) -> tuple[list, int]:
        """退款列表

        参数:
        - auth (AuthSchema): 认证信息模型
        - refund_status (int | None): 退款状态筛选
        - offset (int): 偏移量
        - limit (int): 每页数量

        返回:
        - tuple[list, int]: (订单列表, 总数)
        """
        rows, total = await OrderCRUD(auth, db).query(refund_status=refund_status, offset=offset, limit=limit)
        items = [OrderOutSchema.model_validate(r) for r in rows]
        return items, total

    @classmethod
    async def approve(cls, auth: AuthSchema, db: AsyncSession, refund_id: int, reviewer_id: int, operator_name: str = "") -> OrderStatusMessage:
        """批准退款

        参数:
        - auth (AuthSchema): 认证信息模型
        - refund_id (int): 订单ID（即 refund_id 就是 order_id）
        - reviewer_id (int): 审核人ID
        - operator_name (str): 操作人名称

        返回:
        - OrderStatusMessage: 审核结果
        """
        crud = OrderCRUD(auth, db)
        order = await crud.get_by_id(refund_id)
        if not order:
            raise CustomException(msg="该数据不存在")
        if order.refund_status != 1:
            raise CustomException(msg="仅申请中可审核")
        await crud.update(
            refund_id,
            OrderUpdateInternalSchema(
                refund_status=2,
                status=1,
                reviewer_id=reviewer_id,
                review_time=datetime.now(),
            ),
        )
        return OrderStatusMessage(id=order.id, status=2, message="已批准退款")

    @classmethod
    async def reject(
        cls,
        auth: AuthSchema,
        db: AsyncSession,
        refund_id: int,
        reviewer_id: int,
        data: RefundReviewSchema,
        operator_name: str = "",
    ) -> OrderStatusMessage:
        """驳回退款

        参数:
        - auth (AuthSchema): 认证信息模型
        - refund_id (int): 订单ID（即 refund_id 就是 order_id）
        - reviewer_id (int): 审核人ID
        - data (RefundReviewSchema): 驳回原因
        - operator_name (str): 操作人名称

        返回:
        - OrderStatusMessage: 审核结果
        """
        crud = OrderCRUD(auth, db)
        order = await crud.get_by_id(refund_id)
        if not order:
            raise CustomException(msg="该数据不存在")
        if order.refund_status != 1:
            raise CustomException(msg="仅申请中可审核")
        await crud.update(
            refund_id,
            OrderUpdateInternalSchema(
                refund_status=3,
                reviewer_id=reviewer_id,
                review_time=datetime.now(),
                reject_reason=data.reject_reason,
            ),
        )
        return OrderStatusMessage(id=order.id, status=3, message="已驳回")
