from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.module_platform.menu.crud import MenuCRUD
from app.api.v1.module_platform.package.service import PackageService
from app.api.v1.module_system.dept.crud import DeptCRUD
from app.core.base_crud import CRUDBase
from app.core.base_schema import AuthSchema
from app.core.exceptions import CustomException
from app.core.logger import logger as _lg

from .model import RoleModel
from .schema import RoleCreateSchema, RoleUpdateSchema


class RoleCRUD(CRUDBase[RoleModel, RoleCreateSchema, RoleUpdateSchema]):
    """角色模块数据层"""

    def __init__(self, auth: AuthSchema, db: AsyncSession) -> None:
        super().__init__(model=RoleModel, auth=auth, db=db)

    async def set_role_menus_crud(self, role_ids: list[int], menu_ids: list[int]) -> None:
        """设置角色的菜单权限

        参数:
        - role_ids (list[int]): 角色ID列表
        - menu_ids (list[int]): 菜单ID列表

        返回:
        - None
        """
        if not role_ids:
            raise CustomException(msg="角色ID列表不能为空")

        roles = await self.get_list(search={"id": ("in", role_ids)})
        # 校验：传入的 role_ids 必须全部存在（否则容易被 IDOR silent no-op）
        if len(roles) != len(set(role_ids)):
            missing = sorted(set(role_ids) - {r.id for r in roles})
            raise CustomException(msg=f"角色不存在: {missing}")

        menus = [] if not menu_ids else await MenuCRUD(self.auth, self.db).get_list(search={"id": ("in", menu_ids)})

        # 校验：传入的所有菜单必须存在
        if menu_ids and len(menus) != len(set(menu_ids)):
            missing = sorted(set(menu_ids) - {m.id for m in menus})
            raise CustomException(msg=f"菜单不存在: {missing}")

        # 非超管：按"调用方的租户套餐"校验；同时校验所有目标角色是否都在调用方租户内，
        # 防止超管以外的人通过传入其他租户角色 ID 跨租户授权菜单。
        user = self.auth.user
        if user and user.tenant_id:
            user_allowed = set[int](
                await PackageService(self.auth, self.db).get_tenant_available_menu_ids(user.tenant_id)
            )

            # 调用方可见的角色必须在自己的租户内（防跨租户角色 IDOR）
            for obj in roles:
                if getattr(obj, "tenant_id", None) and obj.tenant_id != user.tenant_id:
                    if user.is_superuser:
                        continue  # 超管放行（含 system tenant=1）
                    raise CustomException(msg=f"无权操作跨租户角色: {obj.name}")

            for menu in menus:
                if int(menu.id) not in user_allowed:
                    if user.is_superuser:
                        continue
                    raise CustomException(msg=f"菜单[{menu.name}]不在当前租户的功能组内，无法分配")

            # 超管给跨租户角色授权菜单时，也需校验菜单至少在目标租户套餐内
            # —— 这一行为按业务灵活控制：默认通过，但记日志
            if user.is_superuser:
                cross_tenant_roles = [
                    r for r in roles if getattr(r, "tenant_id", None) and r.tenant_id != user.tenant_id
                ]
                if cross_tenant_roles and menus:
                    _lg.info(
                        "超管跨租户授权菜单：roles={} menus={}",
                        [r.id for r in cross_tenant_roles],
                        [m.id for m in menus],
                    )

        for obj in roles:
            obj.menus.clear()
            obj.menus.extend(menus)
        await self.db.flush()

    async def set_role_depts_crud(self, role_ids: list[int], dept_ids: list[int]) -> None:
        """设置角色的部门权限（含存在性校验 + 跨租户隔离）

        参数:
        - role_ids (list[int]): 角色ID列表
        - dept_ids (list[int]): 部门ID列表

        返回:
        - None
        """
        if not role_ids:
            raise CustomException(msg="角色ID列表不能为空")

        roles = await self.get_list(search={"id": ("in", role_ids)})
        if len(roles) != len(set(role_ids)):
            missing = sorted(set(role_ids) - {r.id for r in roles})
            raise CustomException(msg=f"角色不存在: {missing}")

        depts = [] if not dept_ids else await DeptCRUD(self.auth, self.db).get_list(search={"id": ("in", dept_ids)})
        if dept_ids and len(depts) != len(set(dept_ids)):
            missing = sorted(set(dept_ids) - {d.id for d in depts})
            raise CustomException(msg=f"部门不存在: {missing}")

        # 跨租户隔离：非超管不能操作其他租户的角色
        user = self.auth.user
        if user and not user.is_superuser:
            for obj in roles:
                if getattr(obj, "tenant_id", None) and obj.tenant_id != user.tenant_id:
                    raise CustomException(msg=f"无权操作跨租户角色: {obj.name}")
            for obj in depts:
                if getattr(obj, "tenant_id", None) and obj.tenant_id != user.tenant_id:
                    raise CustomException(msg=f"无权操作跨租户部门: {obj.name}")

        for obj in roles:
            relationship = obj.depts
            relationship.clear()
            relationship.extend(depts)
        await self.db.flush()

    async def get_options(self) -> list[dict[str, Any]]:
        """获取角色下拉选项，返回 [{value, label}]（自动按当前用户租户过滤）"""
        search: dict[str, Any] = {"status": 0}
        user = self.auth.user
        if user and user.tenant_id and not user.is_superuser:
            search["tenant_id"] = user.tenant_id
        items = await self.get_list(search=search)
        return [{"value": item.id, "label": item.name} for item in items]
