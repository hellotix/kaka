from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_crud import CRUDBase
from app.core.base_schema import AuthSchema

from .model import OrderModel
from .schema import OrderCreateInternalSchema, OrderUpdateInternalSchema


class OrderCRUD(CRUDBase[OrderModel, OrderCreateInternalSchema, OrderUpdateInternalSchema]):
    """订单 CRUD"""

    def __init__(self, auth: AuthSchema, db: AsyncSession) -> None:
        super().__init__(model=OrderModel, auth=auth, db=db)

    async def get_by_order_no(self, order_no: str) -> OrderModel | None:
        return await self.get(order_no=order_no)

    async def query(
        self,
        *,
        tenant_id: int | None = None,
        status: int | None = None,
        refund_status: int | None = None,
        order_type: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[OrderModel], int]:
        result = await self.page(
            search={"tenant_id": tenant_id, "status": status, "refund_status": refund_status, "order_type": order_type},
            order_by=[{"created_time": "desc"}],
            offset=offset,
            limit=limit,
        )
        return result.items, result.total
