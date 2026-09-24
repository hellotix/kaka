from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.base_schema import BaseQueryParam
from app.core.validator import DateTimeStr, Telephone

from ..core.constants import (
    ACCESS_TOKEN_EXPIRE_SECONDS,
    REFRESH_TOKEN_EXPIRE_SECONDS,
    SMS_CODE_EXPIRE_SECONDS,
    SMS_RESEND_INTERVAL_SECONDS,
    AppLoginType,
    AppPlatform,
    AppSmsScene,
    ThirdPartyProvider,
)
from ..user.schema import AppUserBriefSchema, validate_password_strength


class AppLoginBaseSchema(BaseModel):
    """登录请求公共字段"""

    platform: AppPlatform = Field(default=AppPlatform.WEB, description="登录终端(ios/android/windows/mac/miniapp/web)")
    device_id: str | None = Field(default=None, max_length=128, description="设备唯一标识(可选，用于多端管理)")


class AppPasswordLoginSchema(AppLoginBaseSchema):
    """密码登录请求"""

    account: str = Field(..., min_length=2, max_length=64, description="手机号或用户名")
    password: str = Field(..., min_length=1, max_length=128, description="密码")

    @field_validator("account", "password")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class AppRegisterSchema(AppLoginBaseSchema):
    """手机号注册请求"""

    mobile: Telephone = Field(..., description="手机号")
    password: str = Field(..., description="密码")
    code: str | None = Field(default=None, max_length=10, description="短信验证码(开启短信校验时必填)")
    username: str | None = Field(default=None, max_length=64, description="用户名(可选)")
    nickname: str | None = Field(default=None, max_length=64, description="昵称(可选)")

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        return validate_password_strength(v)


class AppSmsSendSchema(BaseModel):
    """发送短信验证码请求"""

    mobile: Telephone = Field(..., description="手机号")
    scene: AppSmsScene = Field(default=AppSmsScene.LOGIN, description="使用场景(login/register/reset_password/bind_mobile)")


class AppSmsSendOutSchema(BaseModel):
    """发送短信验证码响应"""

    mobile: str = Field(..., description="脱敏手机号")
    expire_seconds: int = Field(default=SMS_CODE_EXPIRE_SECONDS, description="验证码有效期(秒)")
    resend_after: int = Field(default=SMS_RESEND_INTERVAL_SECONDS, description="重发间隔(秒)")


class AppSmsLoginSchema(AppLoginBaseSchema):
    """短信验证码登录请求"""

    mobile: Telephone = Field(..., description="手机号")
    code: str = Field(..., min_length=4, max_length=10, description="短信验证码")


class AppWechatLoginSchema(AppLoginBaseSchema):
    """微信登录请求

    - 小程序端：``provider=wechat_mini`` + ``code``（uni.login 返回）
    - App/网页扫码：``provider=wechat_open`` + ``code``（OAuth2 授权码）
    """

    provider: ThirdPartyProvider = Field(default=ThirdPartyProvider.WECHAT_MINI, description="微信渠道")
    code: str = Field(..., min_length=1, max_length=256, description="微信授权码")
    nickname: str | None = Field(default=None, max_length=64, description="昵称(小程序端可由前端传入)")
    avatar: str | None = Field(default=None, max_length=500, description="头像(小程序端可由前端传入)")

    @field_validator("provider")
    @classmethod
    def _check_provider(cls, v: ThirdPartyProvider) -> ThirdPartyProvider:
        if v not in (ThirdPartyProvider.WECHAT_MINI, ThirdPartyProvider.WECHAT_OPEN, ThirdPartyProvider.WECHAT_MP):
            raise ValueError("该接口仅支持微信渠道登录")
        return v


class AppAppleLoginSchema(AppLoginBaseSchema):
    """苹果登录请求"""

    identity_token: str = Field(..., min_length=1, description="Sign in with Apple 返回的 identityToken")
    authorization_code: str | None = Field(default=None, description="Sign in with Apple 返回的 authorizationCode(可选)")
    nickname: str | None = Field(default=None, max_length=64, description="昵称(仅首次授权时苹果返回)")
    email: str | None = Field(default=None, max_length=64, description="邮箱(仅首次授权时苹果返回，可能为私有中继邮箱)")


class AppResetPasswordSchema(BaseModel):
    """短信验证码重置密码请求（忘记密码）"""

    mobile: Telephone = Field(..., description="手机号")
    code: str = Field(..., min_length=4, max_length=10, description="短信验证码")
    password: str = Field(..., description="新密码")

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        return validate_password_strength(v)


class AppRefreshTokenSchema(BaseModel):
    """刷新令牌请求"""

    refresh_token: str = Field(..., min_length=1, description="刷新令牌")


class AppLogoutSchema(BaseModel):
    """登出请求"""

    refresh_token: str | None = Field(default=None, description="刷新令牌(可选，传入则一并作废)")


class AppTokenOutSchema(BaseModel):
    """令牌响应"""

    access_token: str = Field(..., description="访问令牌")
    refresh_token: str = Field(..., description="刷新令牌")
    token_type: str = Field(default="Bearer", description="令牌类型")
    expires_in: int = Field(default=ACCESS_TOKEN_EXPIRE_SECONDS, description="访问令牌有效期(秒)")
    refresh_expires_in: int = Field(default=REFRESH_TOKEN_EXPIRE_SECONDS, description="刷新令牌有效期(秒)")


class AppLoginOutSchema(AppTokenOutSchema):
    """登录响应"""

    session_id: str = Field(..., description="会话ID")
    is_new_user: bool = Field(default=False, description="是否为新注册用户")
    user_info: AppUserBriefSchema = Field(..., description="用户信息")


class AppLoginLogCreateSchema(BaseModel):
    """登录日志写入模型"""

    user_id: int | None = Field(default=None, description="C端用户ID")
    account: str | None = Field(default=None, max_length=128, description="登录账号")
    nickname: str | None = Field(default=None, max_length=64, description="昵称")
    platform: str | None = Field(default=None, max_length=16, description="登录终端")
    login_type: str | None = Field(default=None, max_length=16, description="登录方式")
    provider: str | None = Field(default=None, max_length=32, description="第三方渠道")
    session_id: str | None = Field(default=None, max_length=64, description="会话ID")
    status: int = Field(default=1, ge=1, le=2, description="状态(1:成功 2:失败)")
    msg: str | None = Field(default=None, max_length=255, description="提示信息")
    login_ip: str | None = Field(default=None, max_length=64, description="登录IP")
    login_location: str | None = Field(default=None, max_length=128, description="登录归属地")
    device_os: str | None = Field(default=None, max_length=64, description="操作系统")
    device_browser: str | None = Field(default=None, max_length=64, description="浏览器/客户端")
    user_agent: str | None = Field(default=None, max_length=500, description="原始 User-Agent")


class AppLoginLogOutSchema(AppLoginLogCreateSchema):
    """登录日志响应模型"""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(default=None, description="主键ID")
    created_time: DateTimeStr | None = Field(default=None, description="登录时间")


class AppLoginLogQueryParam(BaseQueryParam):
    """登录日志查询参数"""

    account: str | None = Field(None, description="登录账号", json_schema_extra={"q": "like"})
    user_id: int | None = Field(None, description="C端用户ID", json_schema_extra={"q": "eq"})
    platform: str | None = Field(None, description="登录终端", json_schema_extra={"q": "eq"})
    login_type: str | None = Field(None, description="登录方式", json_schema_extra={"q": "eq"})
    status: int | None = Field(None, description="状态(1:成功 2:失败)", json_schema_extra={"q": "eq"})
    login_ip: str | None = Field(None, description="登录IP", json_schema_extra={"q": "like"})


class AppLoginTypeOutSchema(BaseModel):
    """登录方式开关（供客户端渲染登录页）"""

    password: bool = Field(default=True, description="是否开启密码登录")
    sms: bool = Field(default=True, description="是否开启短信登录")
    wechat: bool = Field(default=False, description="是否开启微信登录")
    apple: bool = Field(default=False, description="是否开启苹果登录")
    platforms: list[str] = Field(default_factory=lambda: [item.value for item in AppPlatform], description="支持的终端列表")
    login_types: list[str] = Field(default_factory=lambda: [item.value for item in AppLoginType], description="支持的登录方式")
    sms_scenes: list[str] = Field(default_factory=lambda: [item.value for item in AppSmsScene], description="短信验证码场景")
    providers: list[str] = Field(default_factory=list, description="已完成配置的第三方渠道")
