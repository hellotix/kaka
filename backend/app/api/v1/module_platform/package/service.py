from typing import Any

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.module_platform.menu.model import MenuModel
from app.api.v1.module_platform.tenant.model import TenantModel
from app.core.base_schema import AuthSchema, PageResultSchema
from app.core.exceptions import CustomException, require_superadmin
from app.core.logger import logger
from app.utils.common_util import search_to_dict

from .crud import PackageCRUD
from .model import PackageMenuModel, PackageModel
from .schema import (
    PackageCreateSchema,
    PackageMenuSetSchema,
    PackageOutSchema,
    PackageQueryParam,
    PackageUpdateSchema,
)


class PackageService:
    """套餐管理服务（仅超级管理员可操作）"""

    def __init__(self, auth: AuthSchema, db: AsyncSession) -> None:
        self.auth = auth
        self.db = db

    @require_superadmin
    async def get_options(self) -> list[dict[str, Any]]:
        """获取套餐下拉选项，委托给 PackageCRUD"""
        return await PackageCRUD(self.auth, self.db).get_options()

    @require_superadmin
    async def detail(self, id: int) -> PackageOutSchema:
        obj = await PackageCRUD(self.auth, self.db).get_or_404(id=id)
        return PackageOutSchema.model_validate(obj)

    @require_superadmin
    async def page(
        self,
        page_no: int,
        page_size: int,
        search: PackageQueryParam | None = None,
        order_by: list[dict[str, str]] | None = None,
    ) -> PageResultSchema[PackageOutSchema]:
        return await PackageCRUD(self.auth, self.db).page(
            offset=(page_no - 1) * page_size,
            limit=page_size,
            order_by=order_by or [{"sort": "asc"}, {"id": "asc"}],
            search=search_to_dict(search),
            out_schema=PackageOutSchema,
        )

    @require_superadmin
    async def create(self, data: PackageCreateSchema) -> PackageOutSchema:
        if await PackageCRUD(self.auth, self.db).get(name=data.name):
            raise CustomException(msg="创建失败，套餐名称已存在")
        if await PackageCRUD(self.auth, self.db).get(code=data.code):
            raise CustomException(msg="创建失败，套餐编码已存在")

        obj = await PackageCRUD(self.auth, self.db).create(data=data)
        result = PackageOutSchema.model_validate(obj)
        logger.info(f"创建套餐成功: {result.name}")
        return result

    @require_superadmin
    async def update(self, id: int, data: PackageUpdateSchema) -> PackageOutSchema:
        obj = await PackageCRUD(self.auth, self.db).get_or_404(id=id)

        if data.name is not None:
            exist = await PackageCRUD(self.auth, self.db).get(name=data.name)
            if exist and exist.id != id:
                raise CustomException(msg="更新失败，名称重复")
        if data.code is not None:
            exist = await PackageCRUD(self.auth, self.db).get(code=data.code)
            if exist and exist.id != id:
                raise CustomException(msg="更新失败，编码重复")

        if data.status is not None and data.status == 1 and obj.status == 0:
            await self.disable_cascade(package_id=id)

        updated = await PackageCRUD(self.auth, self.db).update(id=id, data=data)
        return PackageOutSchema.model_validate(updated)

    @require_superadmin
    async def delete(self, ids: list[int]) -> None:
        if not ids:
            raise CustomException(msg="删除失败，删除对象不能为空")

        # 批量查询套餐被租户引用情况（一次查询代替 N 次）
        stmt = select(TenantModel.package_id, func.count()).where(
            TenantModel.package_id.in_(ids)
        ).group_by(TenantModel.package_id)
        result = await self.db.execute(stmt)
        rows = result.all()
        used_map = {row[0]: row[1] for row in rows}
        for pid in ids:
            count = used_map.get(pid, 0)
            if count and count > 0:
                raise CustomException(msg=f"套餐 ID={pid} 已被 {count} 个租户使用，无法删除")

        await PackageCRUD(self.auth, self.db).delete(ids=ids)

    async def disable_cascade(self, package_id: int) -> None:
        """停用套餐的级联动作：

        - 把所有引用此套餐的状态为 normal 的租户切换为 ``suspended``（不再可登录）
        - 不会物理删除租户或业务数据（避免误伤）；管理员后续可恢复

        注意：原实现只 log 不生效，已修复。
        """
        from sqlalchemy import update as sa_update  # noqa

        # 先 SELECT 统计受影响行数（SQLAlchemy 2.x async 下 ``Result.rowcount`` 不可用）
        stmt_count = (
            select(func.count(TenantModel.id))
            .where(TenantModel.package_id == package_id, TenantModel.status == 0)
        )
        count = (await self.db.execute(stmt_count)).scalar_one()

        if count == 0:
            return

        stmt = (
            sa_update(TenantModel)
            .where(TenantModel.package_id == package_id, TenantModel.status == 0)
            .values(status=2)  # TenantStatusEnum.SUSPENDED
        )
        await self.db.execute(stmt)
        await self.db.flush()
        logger.warning(f"套餐[{package_id}]已禁用，已级联冻结 {count} 个租户（status=2 suspended）")

    async def get_menus(self, package_id: int) -> list[int]:
        stmt = select(PackageMenuModel.menu_id).where(PackageMenuModel.package_id == package_id)
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]

    async def set_menus(self, package_id: int, data: PackageMenuSetSchema) -> None:
        await self.db.execute(sa.delete(PackageMenuModel).where(PackageMenuModel.package_id == package_id))
        for menu_id in data.menu_ids:
            self.db.add(PackageMenuModel(package_id=package_id, menu_id=menu_id))
        await self.db.flush()
        logger.info(f"套餐[{package_id}]菜单权限已设置, count={len(data.menu_ids)}")

    async def get_package_menu_ids(self, package_id: int) -> list[int]:
        stmt = select(PackageMenuModel.menu_id).where(PackageMenuModel.package_id == package_id)
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]

    async def get_tenant_available_menu_ids(self, tenant_id: int) -> list[int]:
        if tenant_id == 1:
            menu_stmt = select(MenuModel.id).where(MenuModel.status == 0)
            result = await self.db.execute(menu_stmt)
            return [row[0] for row in result.all()]

        stmt = select(TenantModel).where(TenantModel.id == tenant_id).limit(1)
        result = await self.db.execute(stmt)
        tenant = result.scalar_one_or_none()
        if not tenant:
            return []

        if not tenant.package_id:
            return []

        pkg_stmt = select(PackageModel.status).where(PackageModel.id == tenant.package_id).limit(1)
        pkg_result = await self.db.execute(pkg_stmt)
        pkg_status = pkg_result.scalar_one_or_none()
        if pkg_status != 0:
            return []

        menu_stmt = select(PackageMenuModel.menu_id).where(PackageMenuModel.package_id == tenant.package_id)
        result = await self.db.execute(menu_stmt)
        return [row[0] for row in result.all()]
