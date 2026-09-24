from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_crud import CRUDBase
from app.core.base_schema import AuthSchema

from .model import AppUserModel, AppUserOauthModel
from .schema import (
    AppUserCreateSchema,
    AppUserOauthCreateSchema,
    AppUserOauthUpdateSchema,
    AppUserUpdateSchema,
)


class AppUserCRUD(CRUDBase[AppUserModel, AppUserCreateSchema, AppUserUpdateSchema]):
    """C端用户数据层"""

    def __init__(self, auth: AuthSchema, db: AsyncSession) -> None:
        """初始化CRUD数据层

        参数:
        - auth (AuthSchema): 认证信息模型（C端流程传 ``AuthSchema()`` 即可，不触发后台数据权限过滤）
        - db (AsyncSession): 数据库会话
        """
        super().__init__(model=AppUserModel, auth=auth, db=db)

    async def get_by_account(self, account: str) -> AppUserModel | None:
        """按登录账号查询：11位纯数字视为手机号，否则视为用户名。

        参数:
        - account (str): 手机号或用户名。

        返回:
        - AppUserModel | None: 用户对象，不存在返回 None。
        """
        account = (account or "").strip()
        if not account:
            return None
        if account.isdigit() and len(account) == 11:
            return await self.get(mobile=account)
        return await self.get(username=account)

    async def touch_login(self, user_id: int, *, platform: str | None = None, ip: str | None = None) -> None:
        """更新最后登录信息。"""
        values: dict[str, object] = {"last_login_time": datetime.now(UTC)}
        if platform is not None:
            values["last_login_platform"] = platform
        if ip:
            values["last_login_ip"] = ip
        await self.set(ids=[user_id], **values)


class AppUserOauthCRUD(CRUDBase[AppUserOauthModel, AppUserOauthCreateSchema, AppUserOauthUpdateSchema]):
    """C端用户第三方绑定数据层"""

    def __init__(self, auth: AuthSchema, db: AsyncSession) -> None:
        """初始化CRUD数据层

        参数:
        - auth (AuthSchema): 认证信息模型
        - db (AsyncSession): 数据库会话
        """
        super().__init__(model=AppUserOauthModel, auth=auth, db=db)

    async def get_by_provider(self, provider: str, openid: str) -> AppUserOauthModel | None:
        """按渠道 + openid 查询绑定记录。"""
        if not provider or not openid:
            return None
        return await self.get(provider=provider, openid=openid)
