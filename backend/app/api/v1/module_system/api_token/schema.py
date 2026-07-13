from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.base_schema import PaginationQueryParam


class ApiTokenCreateSchema(BaseModel):
    """创建 API Token"""

    name: str = Field(..., min_length=2, max_length=64, description="令牌业务名称")
    scopes: list[str] = Field(default_factory=lambda: ["*"], description="可用 scope，``*`` 表示全部")
    expires_at: datetime | None = Field(default=None, description="过期时间（NULL=永不过期）")
    rate_limit: int = Field(default=1000, ge=1, le=1_000_000, description="每小时请求上限")
    description: str | None = Field(default=None, max_length=512, description="备注")


class ApiTokenResetSchema(BaseModel):
    """重置（重新生成 secret）— 沿用同名 token，仅替换 secret 段"""

    name: str | None = Field(default=None, max_length=64, description="新名称（不传则保持原值）")
    scopes: list[str] | None = Field(default=None, description="新 scope（不传则保持原值）")
    expires_at: datetime | None = Field(default=None, description="新过期时间")
    rate_limit: int | None = Field(default=None, ge=1, le=1_000_000, description="新配额（NULL 保持原值）")


class ApiTokenQueryParam(PaginationQueryParam):
    """列表查询条件"""

    name: str | None = Field(default=None, description="名称模糊匹配")
    status: int | None = Field(default=None, description="状态精确匹配")


class ApiTokenRevealSchema(BaseModel):
    """查看明文 — 需当前用户密码二次验证"""

    password: str = Field(..., min_length=6, max_length=128, description="当前用户登录密码")


class ApiTokenOutSchema(BaseModel):
    """列表/详情输出：脱敏（不含 token_plain）"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    token_prefix: str = Field(..., description="明文 token 前 12 字符，用于识别")
    token_mask: str = Field(..., description="脱敏展示，例如 ``fastpat_xxxx****yz3w``")
    owner_user_id: int | None
    scopes: str
    status: int
    rate_limit: int
    expires_at: datetime | None
    used_count: int
    last_used_at: datetime | None
    last_used_ip: str | None
    description: str | None
    tenant_id: int
    created_id: int | None
    updated_id: int | None
    created_time: datetime | None
    updated_time: datetime | None


class ApiTokenCreatedSchema(BaseModel):
    """创建/重置响应：唯一含明文 token 的输出"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    token: str = Field(..., description="完整明文 token（仅此一次返回，请妥善保管）")
    token_prefix: str
    scopes: list[str]
    expires_at: datetime | None
    rate_limit: int
    status: int
    tenant_id: int
    created_time: datetime | None
    warning: str = Field(
        default="请立即保存此 token。关闭此页面后将无法再次完整查看明文，如遗失请重置。",
        description="安全提示",
    )


class ApiTokenRevealOutSchema(BaseModel):
    """reveal 响应：含完整明文 + 警告"""

    token: str
    name: str
    warning: str = "此为完整明文，仅高权限场景下返回，请勿写入日志/代码/对话。"
