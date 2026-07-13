from fastapi import APIRouter

from app.api.v1.module_platform.invoice.controller import InvoiceRouter
from app.api.v1.module_platform.menu.controller import MenuRouter
from app.api.v1.module_platform.order.controller import OrderRouter
from app.api.v1.module_platform.package.controller import PackageRouter
from app.api.v1.module_platform.tenant.controller import TenantRouter

platform_router = APIRouter(prefix="/platform")

platform_router.include_router(TenantRouter)
platform_router.include_router(PackageRouter)
platform_router.include_router(OrderRouter)
platform_router.include_router(InvoiceRouter)
platform_router.include_router(MenuRouter)
