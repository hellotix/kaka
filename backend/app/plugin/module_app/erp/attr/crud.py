"""扩展属性模板数据访问层。"""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_crud import CRUDBase
from app.core.base_schema import AuthSchema

from .model import ErpAttrTemplateModel
from .schema import ErpAttrCreateSchema, ErpAttrUpdateSchema


class ErpAttrTemplateCRUD(CRUDBase[ErpAttrTemplateModel, ErpAttrCreateSchema, ErpAttrUpdateSchema]):
    """扩展属性模板数据层"""

    def __init__(self, auth: AuthSchema, db: AsyncSession) -> None:
        """初始化。

        参数:
        - auth (AuthSchema): 认证信息。
        - db (AsyncSession): 数据库会话。
        """
        super().__init__(model=ErpAttrTemplateModel, auth=auth, db=db)

    async def list_by_category(self, category_id: int | None, *, only_enabled: bool = True) -> Sequence[ErpAttrTemplateModel]:
        """列出某分类直接配置的模板。

        参数:
        - category_id (int | None): None 表示查全局模板。
        - only_enabled (bool): 只要启用状态的模板。
        """
        search: dict[str, object] = {"category_id": category_id if category_id else ("None", None)}
        if only_enabled:
            search["status"] = 0
        return await self.get_list(search=search, order_by=[{"sort": "asc"}, {"id": "asc"}])

    async def list_by_categories(self, category_ids: list[int], *, only_enabled: bool = True) -> Sequence[ErpAttrTemplateModel]:
        """一次取出多个分类的模板（合并祖先链时用，避免逐级查询）。"""
        if not category_ids:
            return []
        search: dict[str, object] = {"category_id": ("in", category_ids)}
        if only_enabled:
            search["status"] = 0
        return await self.get_list(search=search, order_by=[{"sort": "asc"}, {"id": "asc"}])

    async def get_by_code(self, category_id: int | None, code: str) -> ErpAttrTemplateModel | None:
        """查同一作用域内是否已有同名标识（唯一性校验）。"""
        search: dict[str, object] = {"code": code, "category_id": category_id if category_id else ("None", None)}
        return await self.get(**search)
