from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.module_system.position.crud import PositionCRUD
from app.api.v1.module_system.role.crud import RoleCRUD
from app.core.base_crud import CRUDBase
from app.core.base_schema import AuthSchema
from app.core.exceptions import CustomException

from .model import UserModel
from .schema import (
    UserCreateSchema,
    UserUpdateSchema,
)


class UserCRUD(CRUDBase[UserModel, UserCreateSchema, UserUpdateSchema]):
    """用户模块数据层"""

    def __init__(self, auth: AuthSchema, db: AsyncSession) -> None:
        super().__init__(model=UserModel, auth=auth, db=db)

    async def update_last_login(self, id: int) -> None:
        """更新用户最后登录时间

        参数:
        - id (int): 用户ID
        """
        await self.set([id], last_login=datetime.now())

    async def set_user_roles(self, user_ids: list[int], role_ids: list[int]) -> None:
        """批量设置用户角色（带租户隔离验证）

        参数:
        - user_ids (list[int]): 用户ID列表
        - role_ids (list[int]): 角色ID列表

        返回:
        - None
        """
        user_objs = await self.get_list(search={"id": ("in", user_ids)})
        if role_ids:
            role_objs = await RoleCRUD(self.auth, self.db).get_list(search={"id": ("in", role_ids)})
            auth_user = self.auth.user
            if auth_user and not auth_user.is_superuser:
                for role in role_objs:
                    if role.tenant_id != auth_user.tenant_id:
                        raise CustomException(msg=f"角色 {role.name} 不属于当前租户")
        else:
            role_objs = []

        for obj in user_objs:
            relationship = obj.roles
            relationship.clear()
            relationship.extend(role_objs)
        await self.db.flush()

    async def set_user_positions(self, user_ids: list[int], position_ids: list[int]) -> None:
        """批量设置用户岗位（带租户隔离验证）

        参数:
        - user_ids (list[int]): 用户ID列表
        - position_ids (list[int]): 岗位ID列表

        返回:
        - None
        """
        user_objs = await self.get_list(search={"id": ("in", user_ids)})
        if position_ids:
            position_objs = await PositionCRUD(self.auth, self.db).get_list(search={"id": ("in", position_ids)})
            auth_user = self.auth.user
            if auth_user and not auth_user.is_superuser:
                for position in position_objs:
                    if position.tenant_id != auth_user.tenant_id:
                        raise CustomException(msg=f"岗位 {position.name} 不属于当前租户")
        else:
            position_objs = []

        for obj in user_objs:
            relationship = obj.positions
            relationship.clear()
            relationship.extend(position_objs)
        await self.db.flush()

    async def change_password(self, id: int, password_hash: str) -> UserModel:
        """修改用户密码

        参数:
        - id (int): 用户ID
        - password_hash (str): 密码哈希值

        返回:
        - UserModel: 更新后的用户信息
        """
        return await self.update(id=id, data=UserUpdateSchema(password=password_hash))

    async def forget_password(self, id: int, password_hash: str) -> UserModel:
        """重置密码（与 change_password 逻辑相同）"""
        return await self.change_password(id=id, password_hash=password_hash)

    async def bump_token_version(self, user_id: int) -> None:
        """递增指定用户的 token_version 字段，使所有现有 JWT 立即失效。

        配合 invalidate_user_sessions（service 层调用）可在用户改密/重置/禁用时
        同时清掉 Redis 中的活跃会话。

        参数:
        - user_id (int): 用户ID
        """
        from sqlalchemy import update as sa_update

        from .model import UserModel

        await self.db.execute(
            sa_update(UserModel)
            .where(UserModel.id == user_id)
            .values(token_version=UserModel.token_version + 1)
        )
        await self.db.flush()
