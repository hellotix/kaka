from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.common.enums import PermissionFilterStrategy
from app.core.base_schema import AuthSchema
from app.utils.common_util import get_child_id_map, get_child_recursion


class Permission:
    """为业务模型提供数据权限过滤功能

    使用策略模式，根据模型的 __permission_strategy__ 属性选择合适的过滤策略
    """

    # 数据权限常量定义，提高代码可读性
    DATA_SCOPE_SELF = 1  # 仅本人数据
    DATA_SCOPE_DEPT = 2  # 本部门数据
    DATA_SCOPE_DEPT_AND_CHILD = 3  # 本部门及以下数据
    DATA_SCOPE_ALL = 4  # 全部数据
    DATA_SCOPE_CUSTOM = 5  # 自定义数据

    def __init__(self, model: Any, auth: AuthSchema, db: AsyncSession) -> None:
        """初始化权限过滤器实例"""
        self.model = model
        self.auth = auth
        self.db = db
        self.conditions: list[ColumnElement] = []  # 权限条件列表

    async def filter_query(self, query: Any) -> Any:
        """按数据权限为 SQLAlchemy 查询追加 WHERE 条件。

        参数:
        - query (Any): SQLAlchemy 查询对象。

        返回:
        - Any: 附加条件后的查询对象（无权限条件时原样返回）。
        """
        condition = await self.__permission_condition()
        return query.where(condition) if condition is not None else query

    async def __permission_condition(self) -> ColumnElement | None:
        """根据模型的权限过滤策略，选择合适的过滤方法

        注意：当 ``auth.user.is_superuser=True`` 时直接返回 ``None``（不应用任何过滤），
        以便平台超管能查看/管理所有角色的菜单授权（``USER_BINDING`` 等策略对超管不生效）。
        """
        if not self.auth.user or not self.auth.user.id or not self.auth.check_data_scope or self.auth.user.is_superuser:
            return None

        strategy = getattr(self.model, "__permission_strategy__", PermissionFilterStrategy.DATA_SCOPE)
        method = {
            PermissionFilterStrategy.MENU_AUTH: self.__filter_by_menu_auth,
            PermissionFilterStrategy.DEPT_RELATION: self.__filter_by_dept_relation,
            PermissionFilterStrategy.OWN: self.__filter_by_own,
            PermissionFilterStrategy.USER_BINDING: self.__filter_by_user_binding,
        }.get(strategy, self.__filter_by_data_scope)
        return await method()

    async def __filter_by_menu_auth(self) -> ColumnElement | None:
        """基于角色-菜单授权的过滤（适用于菜单模型）

        只显示用户角色授权的菜单，同时受租户套餐约束。
        """
        menu_ids = set(self.auth.menu_ids)
        if not menu_ids:
            return self.__id_eq(-1)

        if self.auth.user and self.auth.user.tenant_id:
            cache_attr = "_cached_package_menu_ids"
            cached = getattr(self.auth, cache_attr, None)
            if cached is None:
                from app.api.v1.module_platform.package.service import PackageService

                cached = set[int](await PackageService(self.auth, self.db).get_tenant_available_menu_ids(self.auth.user.tenant_id))
            object.__setattr__(self.auth, cache_attr, cached)
            menu_ids = menu_ids & cached

        return self.__id_in(menu_ids) if menu_ids else self.__id_eq(-1)

    async def __filter_by_user_binding(self) -> ColumnElement | None:
        """基于当前用户绑定角色的过滤（适用于角色模型）

        只显示当前用户绑定的角色。超管场景下不应用此过滤（参见 `__permission_condition`）。
        """
        role_ids = self.auth.role_ids
        return self.__id_in(role_ids) if role_ids else self.__id_eq(-1)

    async def __filter_by_dept_relation(self) -> ColumnElement | None:
        """基于部门关联的过滤（适用于部门模型、用户模型）

        根据用户的部门权限范围过滤数据
        """
        assert self.auth.user is not None

        data_scopes = set(self.auth.data_scopes)
        custom_dept_ids = set(self.auth.custom_dept_ids)

        if not data_scopes:
            # 无数据权限范围：仅能看本部门
            user_dept_id = self.auth.user.dept_id
            return self.__id_eq(user_dept_id) if user_dept_id else None

        if self.DATA_SCOPE_ALL in data_scopes:
            return None

        accessible_dept_ids = await self.__get_accessible_dept_ids(data_scopes, custom_dept_ids)

        if self.model.__name__ == "DeptModel":
            return self.__filter_dept_model(accessible_dept_ids)
        if self.model.__name__ == "UserModel":
            return self.__filter_user_model(accessible_dept_ids)
        return None

    async def __filter_by_own(self) -> ColumnElement | None:
        """仅本人数据过滤"""
        assert self.auth.user is not None
        return self.__created_id_eq(self.auth.user.id)

    async def __filter_by_data_scope(self) -> ColumnElement | None:
        """基于数据范围权限的通用过滤（默认策略）

        适用于大多数业务模型
        """
        assert self.auth.user is not None

        created_id_attr = getattr(self.model, "created_id", None)
        if created_id_attr is None:
            return None

        data_scopes = set(self.auth.data_scopes)
        custom_dept_ids = set(self.auth.custom_dept_ids)

        if not data_scopes or self.DATA_SCOPE_SELF in data_scopes:
            return created_id_attr == self.auth.user.id

        if self.DATA_SCOPE_ALL in data_scopes:
            return None

        accessible_dept_ids = await self.__get_accessible_dept_ids(data_scopes, custom_dept_ids)
        if not accessible_dept_ids:
            return created_id_attr == self.auth.user.id

        if self.model.__name__ == "UserModel" and hasattr(self.model, "dept_id"):
            dept_id_attr = getattr(self.model, "dept_id", None)
            if dept_id_attr is not None:
                return dept_id_attr.in_(list[int](accessible_dept_ids))

        creator_rel = getattr(self.model, "created_by", None)
        if creator_rel is not None:
            from app.api.v1.module_system.user.model import UserModel

            return creator_rel.has(UserModel.dept_id.in_(list(accessible_dept_ids)))

        return created_id_attr == self.auth.user.id

    async def __get_accessible_dept_ids(self, data_scopes: set[int], custom_dept_ids: set[int]) -> set[int]:
        """获取用户可访问的所有部门ID"""
        assert self.auth.user is not None
        accessible_dept_ids: set[int] = set(custom_dept_ids)
        user_dept_id = self.auth.user.dept_id

        if self.DATA_SCOPE_DEPT in data_scopes and user_dept_id is not None:
            accessible_dept_ids.add(user_dept_id)

        if self.DATA_SCOPE_DEPT_AND_CHILD in data_scopes and user_dept_id is not None:
            try:
                from app.api.v1.module_system.dept.model import DeptModel

                dept_objs = (await self.db.execute(select(DeptModel))).scalars().all()
                id_map = get_child_id_map(dept_objs)
                accessible_dept_ids.update(get_child_recursion(id=user_dept_id, id_map=id_map))
            except Exception:
                accessible_dept_ids.add(user_dept_id)

        return accessible_dept_ids

    def __filter_dept_model(self, accessible_dept_ids: set[int]) -> ColumnElement | None:
        """过滤部门模型"""
        assert self.auth.user is not None
        if accessible_dept_ids:
            return self.__id_in(accessible_dept_ids)
        user_dept_id = self.auth.user.dept_id
        return self.__id_eq(user_dept_id) if user_dept_id else None

    def __filter_user_model(self, accessible_dept_ids: set[int]) -> ColumnElement | None:
        """过滤用户模型"""
        if not accessible_dept_ids:
            return None
        dept_id_attr = getattr(self.model, "dept_id", None)
        return dept_id_attr.in_(list(accessible_dept_ids)) if dept_id_attr is not None else None

    def __id_eq(self, value: int | None) -> ColumnElement | None:
        """主键等于指定值"""
        if value is None:
            return None
        id_attr = getattr(self.model, "id", None)
        return id_attr == value if id_attr is not None else None

    def __id_in(self, values: set[int] | list[int]) -> ColumnElement | None:
        """主键在指定集合中"""
        if not values:
            return None
        id_attr = getattr(self.model, "id", None)
        return id_attr.in_(list(values)) if id_attr is not None else None

    def __created_id_eq(self, value: int) -> ColumnElement | None:
        """created_id 等于指定值"""
        created_id_attr = getattr(self.model, "created_id", None)
        return created_id_attr == value if created_id_attr is not None else None
