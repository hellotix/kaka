from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.base_schema import BaseQueryParam, BaseSchema
from app.core.validator import DateTimeStr, Email, Telephone
from app.utils.password_util import PwdUtil

from ..core.constants import PASSWORD_MIN_LENGTH, PASSWORD_STRICT


def validate_password_strength(value: str) -> str:
    """C端密码强度校验。

    参数:
    - value (str): 明文密码。

    返回:
    - str: 原样返回（不做裁剪，避免改变密码语义）。

    异常:
    - ValueError: 长度或强度不符合要求。
    """
    if not value:
        raise ValueError("密码不能为空")
    if len(value) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"密码长度至少{PASSWORD_MIN_LENGTH}位")
    if PASSWORD_STRICT:
        error = PwdUtil.check_password_strength(value)
        if error:
            raise ValueError(error)
    return value


class AppUserCreateSchema(BaseModel):
    """C端用户新增模型（后台创建）"""

    username: str | None = Field(default=None, max_length=64, description="用户名/登录账号")
    mobile: Telephone | None = Field(default=None, description="手机号")
    email: Email | None = Field(default=None, description="邮箱")
    password: str | None = Field(default=None, description="密码(不填则该用户仅能短信/第三方登录)")
    nickname: str = Field(default="", max_length=64, description="昵称")
    avatar: str | None = Field(default=None, max_length=500, description="头像URL")
    gender: str | None = Field(default="2", pattern=r"^[012]$", description="性别(0:男 1:女 2:未知)")
    status: int = Field(default=0, ge=0, le=1, description="状态(0:正常 1:禁用)")
    remark: str | None = Field(default=None, description="备注")
    extra: dict | None = Field(default=None, description="扩展信息(JSON)")

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return validate_password_strength(v)

    @field_validator("username", "nickname")
    @classmethod
    def _strip_text(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v


class AppUserUpdateSchema(BaseModel):
    """C端用户更新模型（后台）"""

    username: str | None = Field(default=None, max_length=64, description="用户名/登录账号")
    mobile: Telephone | None = Field(default=None, description="手机号")
    email: Email | None = Field(default=None, description="邮箱")
    nickname: str | None = Field(default=None, max_length=64, description="昵称")
    avatar: str | None = Field(default=None, max_length=500, description="头像URL")
    gender: str | None = Field(default=None, pattern=r"^[012]$", description="性别(0:男 1:女 2:未知)")
    status: int | None = Field(default=None, ge=0, le=1, description="状态(0:正常 1:禁用)")
    remark: str | None = Field(default=None, description="备注")
    extra: dict | None = Field(default=None, description="扩展信息(JSON)")


class AppUserOutSchema(BaseSchema):
    """C端用户响应模型"""

    model_config = ConfigDict(from_attributes=True)

    username: str | None = Field(default=None, description="用户名/登录账号")
    mobile: str | None = Field(default=None, description="手机号")
    email: str | None = Field(default=None, description="邮箱")
    nickname: str | None = Field(default=None, description="昵称")
    avatar: str | None = Field(default=None, description="头像URL")
    gender: str | None = Field(default=None, description="性别(0:男 1:女 2:未知)")
    status: int | None = Field(default=None, description="状态(0:正常 1:禁用)")
    register_type: str | None = Field(default=None, description="注册来源")
    register_platform: str | None = Field(default=None, description="注册终端")
    register_ip: str | None = Field(default=None, description="注册IP")
    last_login_time: DateTimeStr | None = Field(default=None, description="最后登录时间")
    last_login_platform: str | None = Field(default=None, description="最后登录终端")
    last_login_ip: str | None = Field(default=None, description="最后登录IP")
    remark: str | None = Field(default=None, description="备注")
    extra: dict | None = Field(default=None, description="扩展信息(JSON)")


class AppUserBriefSchema(BaseModel):
    """C端用户精简信息（登录响应、认证上下文使用）"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="用户ID")
    username: str | None = Field(default=None, description="用户名")
    nickname: str | None = Field(default=None, description="昵称")
    mobile: str | None = Field(default=None, description="手机号")
    avatar: str | None = Field(default=None, description="头像URL")
    gender: str | None = Field(default=None, description="性别(0:男 1:女 2:未知)")
    status: int = Field(default=0, description="状态(0:正常 1:禁用)")


class AppUserQueryParam(BaseQueryParam):
    """C端用户查询参数"""

    username: str | None = Field(None, description="用户名", json_schema_extra={"q": "like"})
    nickname: str | None = Field(None, description="昵称", json_schema_extra={"q": "like"})
    mobile: str | None = Field(None, description="手机号", json_schema_extra={"q": "like"})
    email: str | None = Field(None, description="邮箱", json_schema_extra={"q": "like"})
    status: int | None = Field(None, description="状态(0:正常 1:禁用)", json_schema_extra={"q": "eq"})
    gender: str | None = Field(None, description="性别", json_schema_extra={"q": "eq"})
    register_type: str | None = Field(None, description="注册来源", json_schema_extra={"q": "eq"})
    register_platform: str | None = Field(None, description="注册终端", json_schema_extra={"q": "eq"})
    last_login_platform: str | None = Field(None, description="最后登录终端", json_schema_extra={"q": "eq"})
    last_login_time: list[DateTimeStr] | None = Field(None, description="最后登录时间范围")


class AppUserOauthCreateSchema(BaseModel):
    """第三方绑定新增模型"""

    user_id: int = Field(..., description="C端用户ID")
    provider: str = Field(..., max_length=32, description="第三方渠道")
    openid: str = Field(..., max_length=128, description="第三方用户唯一标识")
    unionid: str | None = Field(default=None, max_length=128, description="第三方 UnionID")
    nickname: str | None = Field(default=None, max_length=64, description="第三方昵称")
    avatar: str | None = Field(default=None, max_length=500, description="第三方头像")
    extra: dict | None = Field(default=None, description="第三方原始信息(JSON)")


class AppUserOauthUpdateSchema(BaseModel):
    """第三方绑定更新模型"""

    unionid: str | None = Field(default=None, max_length=128, description="第三方 UnionID")
    nickname: str | None = Field(default=None, max_length=64, description="第三方昵称")
    avatar: str | None = Field(default=None, max_length=500, description="第三方头像")
    extra: dict | None = Field(default=None, description="第三方原始信息(JSON)")


class AppUserOauthOutSchema(BaseSchema):
    """第三方绑定响应模型"""

    model_config = ConfigDict(from_attributes=True)

    user_id: int | None = Field(default=None, description="C端用户ID")
    provider: str | None = Field(default=None, description="第三方渠道")
    openid: str | None = Field(default=None, description="第三方用户唯一标识")
    unionid: str | None = Field(default=None, description="第三方 UnionID")
    nickname: str | None = Field(default=None, description="第三方昵称")
    avatar: str | None = Field(default=None, description="第三方头像")
    last_login_time: DateTimeStr | None = Field(default=None, description="最后登录时间")


class AppUserProfileUpdateSchema(BaseModel):
    """C端用户自助修改资料"""

    nickname: str | None = Field(default=None, max_length=64, description="昵称")
    avatar: str | None = Field(default=None, max_length=500, description="头像URL")
    gender: str | None = Field(default=None, pattern=r"^[012]$", description="性别(0:男 1:女 2:未知)")
    email: Email | None = Field(default=None, description="邮箱")

    @field_validator("nickname")
    @classmethod
    def _strip_nickname(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("昵称不能为空")
        return v


class AppUserChangePasswordSchema(BaseModel):
    """C端用户自助修改密码"""

    old_password: str | None = Field(default=None, description="原密码(首次设置密码可不传)")
    new_password: str = Field(..., description="新密码")

    @field_validator("new_password")
    @classmethod
    def _check_new_password(cls, v: str) -> str:
        return validate_password_strength(v)


class AppUserResetPasswordSchema(BaseModel):
    """后台重置C端用户密码"""

    password: str = Field(..., description="新密码")

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        return validate_password_strength(v)
