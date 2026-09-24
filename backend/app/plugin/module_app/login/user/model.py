from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin


class AppUserModel(ModelMixin):
    """C端用户表

    仅继承 ``ModelMixin``（不含 ``UserMixin``）：C端用户与后台 ``sys_user`` 无审计关联，
    避免被后台数据权限（created_id 过滤）误伤；``deleted_id`` 单独声明以启用软删除。
    """

    __tablename__: str = "app_user"
    __table_args__: dict[str, str] = {"comment": "C端用户表"}

    username: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True, index=True, comment="用户名/登录账号")
    mobile: Mapped[str | None] = mapped_column(String(20), default=None, nullable=True, index=True, comment="手机号")
    email: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True, index=True, comment="邮箱")
    password: Mapped[str | None] = mapped_column(String(255), default=None, nullable=True, comment="密码哈希(仅密码注册用户有值)")
    nickname: Mapped[str] = mapped_column(String(64), default="", nullable=False, comment="昵称")
    avatar: Mapped[str | None] = mapped_column(String(500), default=None, nullable=True, comment="头像URL")
    gender: Mapped[str | None] = mapped_column(String(1), default="2", nullable=True, comment="性别(0:男 1:女 2:未知)")
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True, comment="状态(0:正常 1:禁用)")

    register_type: Mapped[str | None] = mapped_column(String(16), default=None, nullable=True, comment="注册来源(password/sms/wechat/apple/admin)")
    register_platform: Mapped[str | None] = mapped_column(String(16), default=None, nullable=True, comment="注册终端")
    register_ip: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True, comment="注册IP")

    last_login_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None, nullable=True, comment="最后登录时间")
    last_login_platform: Mapped[str | None] = mapped_column(String(16), default=None, nullable=True, comment="最后登录终端")
    last_login_ip: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True, comment="最后登录IP")

    extra: Mapped[dict | None] = mapped_column(JSON, default=None, nullable=True, comment="扩展信息(JSON)")
    remark: Mapped[str | None] = mapped_column(Text, default=None, nullable=True, comment="备注")
    deleted_id: Mapped[int | None] = mapped_column(Integer, default=None, nullable=True, comment="删除人ID(后台操作人)")


class AppUserOauthModel(ModelMixin):
    """C端用户第三方登录绑定表"""

    __tablename__: str = "app_user_oauth"
    __table_args__: dict[str, str] = {"comment": "C端用户第三方登录绑定表"}

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("app_user.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
        comment="C端用户ID",
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="第三方渠道(wechat_mini/wechat_open/apple...)")
    openid: Mapped[str] = mapped_column(String(128), nullable=False, index=True, comment="第三方用户唯一标识")
    unionid: Mapped[str | None] = mapped_column(String(128), default=None, nullable=True, index=True, comment="第三方 UnionID")
    nickname: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True, comment="第三方昵称")
    avatar: Mapped[str | None] = mapped_column(String(500), default=None, nullable=True, comment="第三方头像")
    last_login_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None, nullable=True, comment="最后登录时间")
    extra: Mapped[dict | None] = mapped_column(JSON, default=None, nullable=True, comment="第三方原始信息(JSON)")
