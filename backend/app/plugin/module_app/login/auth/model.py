from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin


class AppLoginLogModel(ModelMixin):
    """C端登录日志表

    未声明 ``deleted_id``，CRUD 删除时为物理删除，便于定期清理历史日志。
    """

    __tablename__: str = "app_login_log"
    __table_args__: dict[str, str] = {"comment": "C端登录日志表"}

    user_id: Mapped[int | None] = mapped_column(Integer, default=None, nullable=True, index=True, comment="C端用户ID(登录失败时可能为空)")
    account: Mapped[str | None] = mapped_column(String(128), default=None, nullable=True, index=True, comment="登录账号(手机号/用户名/openid)")
    nickname: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True, comment="昵称")
    platform: Mapped[str | None] = mapped_column(String(16), default=None, nullable=True, index=True, comment="登录终端")
    login_type: Mapped[str | None] = mapped_column(String(16), default=None, nullable=True, comment="登录方式(password/sms/wechat/apple)")
    provider: Mapped[str | None] = mapped_column(String(32), default=None, nullable=True, comment="第三方渠道")
    session_id: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True, index=True, comment="会话ID")
    status: Mapped[int] = mapped_column(Integer, default=1, nullable=False, index=True, comment="状态(1:成功 2:失败)")
    msg: Mapped[str | None] = mapped_column(String(255), default=None, nullable=True, comment="提示信息")
    login_ip: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True, comment="登录IP")
    login_location: Mapped[str | None] = mapped_column(String(128), default=None, nullable=True, comment="登录归属地")
    device_os: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True, comment="操作系统")
    device_browser: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True, comment="浏览器/客户端")
    user_agent: Mapped[str | None] = mapped_column(String(500), default=None, nullable=True, comment="原始 User-Agent")
