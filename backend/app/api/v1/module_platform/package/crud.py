from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_crud import CRUDBase
from app.core.base_schema import AuthSchema

from .model import PackageModel
from .schema import PackageCreateSchema, PackageUpdateSchema


class PackageCRUD(CRUDBase[PackageModel, PackageCreateSchema, PackageUpdateSchema]):
    """套餐模块 CRUD"""

    def __init__(self, auth: AuthSchema, db: AsyncSession) -> None:
        super().__init__(model=PackageModel, auth=auth, db=db)

    async def get_options(self) -> list[dict[str, Any]]:
        """获取套餐下拉选项，返回 [{value, label}]"""
        items = await self.get_list(search={"status": 0})
        return [{"value": item.id, "label": item.name} for item in items]
