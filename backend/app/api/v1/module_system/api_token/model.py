"""API Token 数据模型

设计要点：
- token 全名：``fastpat_<tenant_code>_<tenant_id_hex>_<48-random>``，明文存 ``token_plain`` 字段
  （按业务需求选择明文存储，便于长期使用的 webhook / 集成 token）
- ``token_prefix`` 字段存前 12 字符用于列表展示，剩余部分用 ``fp_xxxx****yz`` 形式脱敏
- 支持 ``scopes``、``expires_at``、``rate_limit``、``status`` 等运营字段
- ``last_used_at`` 与 ``used_count`` 提供审计
"""
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, TenantMixin, UserMixin


class ApiTokenModel(ModelMixin, TenantMixin, UserMixin):
    """租户 API 访问令牌（用于外部系统/集成调用）

    token 全名格式：
        fastpat_<tenant_code>_<tenant_id_hex>_<48-char-base64url-secret>

    字段：
        - ``token_plain``：明文令牌（创建时一次性返回，后续可读但不推荐直接读）
        - ``token_prefix``：用于列表展示的前 12 字符
        - ``scopes``：JSON 数组（``["order:read", "user:write"]``），控制 API 可访问范围
        - ``expires_at``：过期时间（空=永久）
        - ``rate_limit``：每小时请求配额（默认 1000）
        - ``status``：0=启用 1=禁用 2=吊销
        - ``last_used_at/used_count/last_used_ip``：调用审计
    """

    __tablename__: str = "sys_api_token"
    __table_args__ = (
        Index("idx_tenant_token_prefix", "tenant_id", "token_prefix"),
        {"comment": "租户 API 访问令牌"},
    )
    __loader_options__: list[str] = ["tenant_by", "created_by", "updated_by"]

    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="令牌名称（业务语义，如：CRM-对账集成）")
    token_prefix: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="明文 token 前 12 字符（用于展示）")
    token_plain: Mapped[str] = mapped_column(Text, nullable=False, comment="明文 token（自管理，按需用于外部集成）")
    owner_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("sys_user.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True, index=True, comment="所属用户ID（创建者/操作者）")
    scopes: Mapped[str] = mapped_column(String(255), nullable=False, default="*", comment="可用 scope（逗号或 JSON 数组字符串）")
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True, comment="过期时间（NULL=永不过期）")
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="状态(0:启用 1:禁用 2:吊销)", index=True)
    rate_limit: Mapped[int] = mapped_column(Integer, default=1000, nullable=False, comment="每小时请求上限")
    used_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="累计调用次数")
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True, comment="最近一次调用时间")
    last_used_ip: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="最近一次调用 IP")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
