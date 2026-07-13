from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_crud import CRUDBase
from app.core.base_schema import AuthSchema

from .model import ApiTokenModel
from .schema import ApiTokenCreateSchema


class ApiTokenCRUD(CRUDBase[ApiTokenModel, ApiTokenCreateSchema, ApiTokenCreateSchema]):
    """平台 API Token CRUD 基础实现"""

    def __init__(self, auth: AuthSchema, db: AsyncSession) -> None:
        super().__init__(auth=auth, model=ApiTokenModel, db=db)
