"""物品分类数据访问层。"""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_crud import CRUDBase
from app.core.base_schema import AuthSchema

from .model import ErpCategoryModel
from .schema import ErpCategoryCreateSchema, ErpCategoryUpdateSchema


class ErpCategoryCRUD(CRUDBase[ErpCategoryModel, ErpCategoryCreateSchema, ErpCategoryUpdateSchema]):
    """分类数据层"""

    def __init__(self, auth: AuthSchema, db: AsyncSession) -> None:
        """初始化。

        参数:
        - auth (AuthSchema): 认证信息（C端只读流程传 ``AuthSchema()``）。
        - db (AsyncSession): 数据库会话。
        """
        super().__init__(model=ErpCategoryModel, auth=auth, db=db)

    async def list_all(self, *, only_enabled: bool = False, only_visible: bool = False) -> Sequence[ErpCategoryModel]:
        """一次性取出全部分类。

        分类总量受三级上限约束（后台配置量级，通常几十到几百条），
        直接全量查出来在内存里组树，比递归查子级省掉 N 次往返。

        参数:
        - only_enabled (bool): 只要启用状态的分类。
        - only_visible (bool): 只要 C端可见的分类（隐含 only_enabled）。
        """
        search: dict[str, object] = {}
        if only_enabled or only_visible:
            search["status"] = 0
        if only_visible:
            search["is_visible"] = True
        return await self.get_list(search=search, order_by=[{"sort": "asc"}, {"id": "asc"}])

    async def get_by_parent_and_name(self, parent_id: int | None, name: str) -> ErpCategoryModel | None:
        """查同级同名分类（用于唯一性校验）。"""
        search: dict[str, object] = {"name": name}
        search["parent_id"] = parent_id if parent_id else ("None", None)
        return await self.get(**search)

    async def count_children(self, category_id: int) -> int:
        """统计直接子分类数量（删除前校验是否有下级）。"""
        return await self.count(parent_id=category_id)
