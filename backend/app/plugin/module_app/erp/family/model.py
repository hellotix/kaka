"""家庭、家庭成员、家庭间共享授权三张表的 ORM 定义。

为什么只用 ``ModelMixin`` 不用 ``UserMixin``
--------------------------------------------
``UserMixin`` 的 created_id/updated_id 外键指向后台 ``sys_user``，并会被后台数据权限
（按 created_id 过滤）纳入管辖。家庭数据属于 C端用户（``app_user``），套上 UserMixin
会让 C端记录被后台数据权限误伤，故与 ``AppUserModel`` 保持一致：只继承 ``ModelMixin``，
另手工声明 ``deleted_id`` 以启用 CRUDBase 的软删除能力（``_supports_soft_delete``
要求 is_deleted / deleted_time / deleted_id 三者齐备）。

审计字段语义
------------
``created_id`` / ``updated_id`` / ``deleted_id`` 存的都是 **C端用户ID**（app_user.id）；
后台运营强制授权时写入操作管理员ID，并由 ``source`` 字段区分来源，不加外键约束以免
两套用户体系互相牵连。
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin


class ErpFamilyModel(ModelMixin):
    """家庭表 —— C端物资数据的归属主体

    一个用户可属于多个家庭（``erp_family_member`` 多对多），因此家庭ID绝不写入 JWT，
    而是每次请求通过 ``X-Family-Id`` 头指定。
    """

    __tablename__: str = "erp_family"
    __table_args__: dict[str, str] = {"comment": "ERP-家庭"}

    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="家庭名称")
    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("app_user.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
        comment="户主的C端用户ID",
    )
    avatar: Mapped[str | None] = mapped_column(String(500), default=None, nullable=True, comment="家庭头像URL")
    # 邀请码用于「扫码/输码入群」，全库唯一；泄露后由户主重新生成即可失效旧码
    invite_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True, comment="邀请码")
    member_limit: Mapped[int] = mapped_column(Integer, default=20, nullable=False, comment="成员数上限")
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True, comment="状态(0:正常 1:停用)")
    remark: Mapped[str | None] = mapped_column(Text, default=None, nullable=True, comment="备注")
    extra: Mapped[dict | None] = mapped_column(JSON, default=None, nullable=True, comment="扩展信息(JSON)")
    deleted_id: Mapped[int | None] = mapped_column(Integer, default=None, nullable=True, comment="删除人ID")


class ErpFamilyMemberModel(ModelMixin):
    """家庭成员表 —— 用户与家庭的多对多关系，同时承载角色与加入状态

    退出/被踢不物理删除，而是把 status 置为 REMOVED 留痕，这样物品档案上的
    「录入人」仍能追溯到具体成员。重新加入时复用原记录（status 改回 ACTIVE）。
    """

    __tablename__: str = "erp_family_member"
    __table_args__: dict[str, str] = {"comment": "ERP-家庭成员"}

    family_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("erp_family.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
        comment="家庭ID",
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("app_user.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
        comment="C端用户ID",
    )
    role: Mapped[str] = mapped_column(String(16), default="member", nullable=False, index=True, comment="角色(owner/admin/member/viewer)")
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True, comment="状态(0:待确认 1:已加入 2:已拒绝 3:已移除)")
    nickname: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True, comment="家庭内称呼(如:妈妈)")
    joined_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None, nullable=True, comment="正式加入时间")
    deleted_id: Mapped[int | None] = mapped_column(Integer, default=None, nullable=True, comment="删除人ID")


class ErpFamilyGrantModel(ModelMixin):
    """家庭间共享授权表 —— A 家庭把自己的物资数据开放给 B 家庭只读查看

    两套来源并存：
    - ``source=family``：户主自助授权，户主可随时撤销，expire_time 可空（长期有效）。
    - ``source=admin``：后台运营强制授权，户主不可自行撤销，expire_time 必填。

    status 只记录「人为撤销」，过期与否在查询时按 expire_time 惰性判定，
    避免为了改状态而起定时任务。
    """

    __tablename__: str = "erp_family_grant"
    __table_args__: dict[str, str] = {"comment": "ERP-家庭间共享授权"}

    family_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("erp_family.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
        comment="数据所属家庭ID(授权方)",
    )
    target_family_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("erp_family.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
        comment="被授权家庭ID(受权方)",
    )
    source: Mapped[str] = mapped_column(String(16), default="family", nullable=False, index=True, comment="授权来源(family:户主自助 admin:后台强制)")
    granted_by: Mapped[int | None] = mapped_column(Integer, default=None, nullable=True, comment="授权操作人ID(source=family 为C端用户ID，admin 为后台用户ID)")
    expire_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None, nullable=True, comment="到期时间(空表示长期有效；admin 来源必填)")
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True, comment="状态(0:生效 1:已撤销)")
    revoked_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None, nullable=True, comment="撤销时间")
    reason: Mapped[str | None] = mapped_column(String(255), default=None, nullable=True, comment="授权原因/备注")
    deleted_id: Mapped[int | None] = mapped_column(Integer, default=None, nullable=True, comment="删除人ID")
