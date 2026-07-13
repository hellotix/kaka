from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.common.enums import QueueEnum
from app.core.base_schema import SessionInfoSchema


class OnlineOutSchema(SessionInfoSchema):
    """在线用户响应模型 — ``SessionInfoSchema`` 的公开子集。"""


class OnlineQueryParam(BaseModel):
    """在线用户查询参数"""

    name: str | tuple[str, str] | None = Field(None, description="登录名称")
    ipaddr: str | tuple[str, str] | None = Field(None, description="登陆IP地址")
    login_location: str | tuple[str, str] | None = Field(None, description="登录所属地")

    @model_validator(mode="after")
    def validate_query_params(self) -> "OnlineQueryParam":
        if isinstance(self.name, str):
            self.name = (QueueEnum.like.value, self.name)
        if isinstance(self.ipaddr, str):
            self.ipaddr = (QueueEnum.like.value, self.ipaddr)
        if isinstance(self.login_location, str):
            self.login_location = (QueueEnum.like.value, self.login_location)
        return self


class RecentLoginItem(BaseModel):
    """最近登录记录"""
    username: str
    status: int
    login_time: datetime
    login_ip: str | None = None
    login_location: str | None = None


class DashboardStatsSchema(BaseModel):
    """仪表盘统计数据"""
    online_users: int = 0
    total_users: int = 0
    total_tenants: int = 0
    total_orders: int = 0
    today_login_count: int = 0
    today_unique_users: int = 0
    week_user_created: int = 0
    week_tenant_created: int = 0
    paid_orders: int = 0
    recent_logins: list[RecentLoginItem] = []
