from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.enums import QueueEnum
from app.core.base_schema import BaseQueryParam, BaseSchema, TenantByQueryParam, TenantBySchema

ALLOWED_REQUEST_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]


class LoginLogCreateSchema(BaseModel):
    """新增登录日志"""

    username: str = Field(..., min_length=1, max_length=64, description="用户名")
    status: int = Field(default=1, ge=1, le=2, description="登录状态(1成功 2失败)")
    login_ip: str | None = Field(default=None, max_length=50, description="登录IP地址")
    login_location: str | None = Field(default=None, max_length=255, description="登录位置")
    request_os: str | None = Field(default=None, max_length=64, description="操作系统")
    request_browser: str | None = Field(default=None, max_length=64, description="浏览器")
    msg: str | None = Field(default=None, max_length=255, description="提示消息")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("用户名不能为空")
        if len(v) > 64:
            raise ValueError("用户名长度不能超过64个字符")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: int) -> int:
        if v not in [1, 2]:
            raise ValueError("登录状态只能为1(成功)或2(失败)")
        return v


class LoginLogOutSchema(LoginLogCreateSchema, BaseSchema, TenantBySchema):
    """登录日志响应"""

    model_config = ConfigDict(from_attributes=True)


class LoginLogDetailOutSchema(LoginLogOutSchema):
    """登录日志详情响应"""


class LoginLogQueryParam(BaseQueryParam, TenantByQueryParam):
    """登录日志查询参数"""

    username: str | tuple[str, str] | None = Field(None, max_length=64, description="用户名")
    status: int | tuple[str, int] | None = Field(None, description="登录状态(1:成功 2:失败)")

    @model_validator(mode="after")
    def validate_query_params(self) -> "LoginLogQueryParam":
        if isinstance(self.username, str):
            self.username = (QueueEnum.like.value, self.username)
        if isinstance(self.status, int):
            self.status = (QueueEnum.eq.value, self.status)
        return self


class OperationLogQueryParam(BaseQueryParam, TenantByQueryParam):
    """操作日志查询参数"""

    request_path: str | tuple[str, str] | None = Field(None, description="请求路径")
    request_method: str | tuple[str, str] | None = Field(None, description="请求方式")
    username: str | tuple[str, str] | None = Field(None, description="用户名")
    status: int | tuple[str, int] | None = Field(None, ge=0, le=1, description="状态(0:成功 1:失败)")
    request_ip: str | tuple[str, str] | None = Field(None, description="请求IP")

    @model_validator(mode="after")
    def validate_query_params(self) -> "OperationLogQueryParam":
        if isinstance(self.request_path, str):
            self.request_path = (QueueEnum.like.value, self.request_path)
        if isinstance(self.request_method, str):
            self.request_method = (QueueEnum.eq.value, self.request_method)
        if isinstance(self.username, str):
            self.username = (QueueEnum.like.value, self.username)
        if isinstance(self.status, int):
            self.status = (QueueEnum.eq.value, self.status)
        if isinstance(self.request_ip, str):
            self.request_ip = (QueueEnum.eq.value, self.request_ip)
        return self


class OperationLogOutSchema(BaseSchema, TenantBySchema):
    """操作日志响应模型"""

    model_config = ConfigDict(from_attributes=True)

    status: int | None = Field(default=None, description="状态(0:启动 1:停用)")
    description: str | None = Field(default=None, description="描述")
    request_path: str = Field(..., description="请求路径")
    request_method: str = Field(..., description="请求方式")
    response_code: int = Field(..., description="响应状态码")
    process_time: str | None = Field(default=None, description="处理时间")
    request_ip: str | None = Field(default=None, description="请求IP")


class OperationLogDetailOutSchema(OperationLogOutSchema):
    """操作日志详情响应模型"""

    request_payload: str | None = Field(default=None, description="请求体")
    response_json: str | None = Field(default=None, description="响应体")


class OperationLogCreateSchema(BaseModel):
    request_path: str = Field(..., min_length=1, max_length=255, description="请求路径")
    request_method: str = Field(..., description="请求方式")
    request_payload: str | None = Field(None, description="请求体")
    response_code: int = Field(200, ge=100, le=599, description="响应状态码")
    response_json: str | None = Field(None, description="响应体")
    process_time: str | None = Field(None, max_length=20, description="处理时间")
    description: str | None = Field(None, description="备注")
    request_ip: str | None = Field(None, max_length=50, description="请求IP")

    @field_validator("request_method")
    @classmethod
    def validate_request_method(cls, value: str) -> str:
        upper_value = value.upper()
        if upper_value not in ALLOWED_REQUEST_METHODS:
            raise ValueError(f"请求方式必须是: {', '.join(ALLOWED_REQUEST_METHODS)}")
        return upper_value
