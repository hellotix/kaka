"""家庭、成员、共享授权的请求/响应模型。

命名约定
--------
- ``*CreateSchema`` / ``*UpdateSchema``：写入模型，Update 全部字段可选，
  由 ``CRUDBase.update`` 的 ``exclude_unset`` 语义决定「没传就是不改」。
- ``*OutSchema``：响应模型，继承 ``BaseSchema`` 以带上 id/uuid/时间戳。
- ``*QueryParam``：查询参数，字段上的 ``json_schema_extra={"q": "op"}``
  会被 ``search_to_dict`` 翻译成 ``CRUDBase`` 认识的 ``(op, value)`` 元组。
"""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from app.core.base_schema import BaseQueryParam, BaseSchema
from app.core.validator import DateTimeStr, Telephone

from ..core.constants import ErpFamilyRole

# 角色可选范围：户主不能通过「新增/改角色」接口直接产生，只能由转让产生
_ASSIGNABLE_ROLES: tuple[str, ...] = (ErpFamilyRole.ADMIN.value, ErpFamilyRole.MEMBER.value, ErpFamilyRole.VIEWER.value)


def is_expired(expire_time: datetime | None) -> bool:
    """判断授权是否已过期（时区安全）。

    MySQL 的 DATETIME 列不保存时区，SQLAlchemy 读回来是 naive datetime，
    而写入时用的是 ``datetime.now(UTC)``，因此这里统一按 UTC 解读后比较，
    避免 ``naive < aware`` 直接抛 TypeError。
    """
    if expire_time is None:
        return False
    value = expire_time if expire_time.tzinfo else expire_time.replace(tzinfo=UTC)
    return value < datetime.now(UTC)


# ══════════════════════════ 家庭 ══════════════════════════


class ErpFamilyCreateSchema(BaseModel):
    """创建家庭（C端）"""

    name: str = Field(..., min_length=1, max_length=64, description="家庭名称")
    avatar: str | None = Field(default=None, max_length=500, description="家庭头像URL")
    remark: str | None = Field(default=None, description="备注")

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("家庭名称不能为空")
        return v


class ErpFamilyUpdateSchema(BaseModel):
    """修改家庭资料（C端，户主/管理员）"""

    name: str | None = Field(default=None, min_length=1, max_length=64, description="家庭名称")
    avatar: str | None = Field(default=None, max_length=500, description="家庭头像URL")
    remark: str | None = Field(default=None, description="备注")

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("家庭名称不能为空")
        return v


class ErpFamilyAdminUpdateSchema(BaseModel):
    """后台修改家庭（可含成员上限与状态）"""

    name: str | None = Field(default=None, max_length=64, description="家庭名称")
    avatar: str | None = Field(default=None, max_length=500, description="家庭头像URL")
    remark: str | None = Field(default=None, description="备注")
    member_limit: int | None = Field(default=None, ge=1, le=100, description="成员数上限")
    status: int | None = Field(default=None, ge=0, le=1, description="状态(0:正常 1:停用)")


class ErpFamilyOutSchema(BaseSchema):
    """家庭响应模型"""

    model_config = ConfigDict(from_attributes=True)

    name: str | None = Field(default=None, description="家庭名称")
    owner_id: int | None = Field(default=None, description="户主C端用户ID")
    avatar: str | None = Field(default=None, description="家庭头像URL")
    invite_code: str | None = Field(default=None, description="邀请码")
    member_limit: int | None = Field(default=None, description="成员数上限")
    status: int | None = Field(default=None, description="状态(0:正常 1:停用)")
    remark: str | None = Field(default=None, description="备注")
    # 以下三个字段 ORM 上没有，由 service 组装后填充
    member_count: int = Field(default=0, description="当前有效成员数")
    my_role: str | None = Field(default=None, description="当前登录用户在该家庭中的角色")
    owner_name: str | None = Field(default=None, description="户主昵称")


class ErpFamilyBriefSchema(BaseModel):
    """家庭精简信息（「我的家庭」列表、家庭切换器用）"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="家庭ID")
    name: str = Field(..., description="家庭名称")
    avatar: str | None = Field(default=None, description="家庭头像URL")
    my_role: str = Field(..., description="我在该家庭中的角色")
    my_nickname: str | None = Field(default=None, description="我在该家庭中的称呼")
    member_count: int = Field(default=0, description="有效成员数")
    status: int = Field(default=0, description="家庭状态(0:正常 1:停用)")


class ErpFamilyQueryParam(BaseQueryParam):
    """后台家庭查询参数"""

    name: str | None = Field(None, description="家庭名称", json_schema_extra={"q": "like"})
    owner_id: int | None = Field(None, description="户主用户ID", json_schema_extra={"q": "eq"})
    invite_code: str | None = Field(None, description="邀请码", json_schema_extra={"q": "eq"})
    status: int | None = Field(None, description="状态(0:正常 1:停用)", json_schema_extra={"q": "eq"})


# ══════════════════════════ 成员 ══════════════════════════


class ErpMemberInviteSchema(BaseModel):
    """定向邀请成员（户主/管理员操作）

    ``user_id`` 与 ``mobile`` 二选一：填 mobile 时由 service 反查 C端用户，
    便于「只知道家人手机号」的场景。
    """

    user_id: int | None = Field(default=None, description="被邀请的C端用户ID")
    mobile: Telephone | None = Field(default=None, description="被邀请人手机号(与 user_id 二选一)")
    role: str = Field(default=ErpFamilyRole.MEMBER.value, description="角色(admin/member/viewer)")
    nickname: str | None = Field(default=None, max_length=64, description="家庭内称呼(如:妈妈)")

    @model_validator(mode="after")
    def _check_target(self) -> "ErpMemberInviteSchema":
        if not self.user_id and not self.mobile:
            raise ValueError("user_id 与 mobile 至少填写一项")
        if self.role not in _ASSIGNABLE_ROLES:
            raise ValueError(f"角色不合法，可选值: {', '.join(_ASSIGNABLE_ROLES)}")
        return self


class ErpMemberJoinSchema(BaseModel):
    """凭邀请码加入家庭（被邀请人自己操作，加入即生效）"""

    invite_code: str = Field(..., min_length=4, max_length=32, description="家庭邀请码")
    nickname: str | None = Field(default=None, max_length=64, description="家庭内称呼")


class ErpMemberUpdateSchema(BaseModel):
    """修改成员信息（角色/称呼）"""

    role: str | None = Field(default=None, description="角色(admin/member/viewer)")
    nickname: str | None = Field(default=None, max_length=64, description="家庭内称呼")

    @field_validator("role")
    @classmethod
    def _check_role(cls, v: str | None) -> str | None:
        if v is not None and v not in _ASSIGNABLE_ROLES:
            raise ValueError(f"角色不合法，可选值: {', '.join(_ASSIGNABLE_ROLES)}")
        return v


class ErpMemberSelfUpdateSchema(BaseModel):
    """成员自助修改自己的家庭内称呼"""

    nickname: str | None = Field(default=None, max_length=64, description="家庭内称呼")


class ErpMemberHandleSchema(BaseModel):
    """处理定向邀请：接受或拒绝"""

    accept: bool = Field(..., description="true 接受，false 拒绝")


class ErpMemberOutSchema(BaseSchema):
    """成员响应模型"""

    model_config = ConfigDict(from_attributes=True)

    family_id: int | None = Field(default=None, description="家庭ID")
    user_id: int | None = Field(default=None, description="C端用户ID")
    role: str | None = Field(default=None, description="角色")
    status: int | None = Field(default=None, description="状态(0:待确认 1:已加入 2:已拒绝 3:已移除)")
    nickname: str | None = Field(default=None, description="家庭内称呼")
    joined_time: DateTimeStr | None = Field(default=None, description="加入时间")
    # 以下为 service 关联 app_user 后填充的展示字段
    username: str | None = Field(default=None, description="用户账号")
    user_nickname: str | None = Field(default=None, description="用户昵称")
    avatar: str | None = Field(default=None, description="用户头像")
    mobile: str | None = Field(default=None, description="用户手机号")


class ErpMemberQueryParam(BaseQueryParam):
    """后台成员查询参数"""

    family_id: int | None = Field(None, description="家庭ID", json_schema_extra={"q": "eq"})
    user_id: int | None = Field(None, description="C端用户ID", json_schema_extra={"q": "eq"})
    role: str | None = Field(None, description="角色", json_schema_extra={"q": "eq"})
    status: int | None = Field(None, description="状态", json_schema_extra={"q": "eq"})


# ══════════════════════════ 共享授权 ══════════════════════════


class ErpGrantCreateSchema(BaseModel):
    """户主自助授权（source=family，可无限期，可随时撤销）"""

    target_family_id: int = Field(..., description="被授权家庭ID")
    expire_time: DateTimeStr | None = Field(default=None, description="到期时间(不填表示长期有效)")
    reason: str | None = Field(default=None, max_length=255, description="授权原因")


class ErpGrantAdminCreateSchema(BaseModel):
    """后台强制授权（source=admin，必须带到期时间）"""

    family_id: int = Field(..., description="数据所属家庭ID(授权方)")
    target_family_id: int = Field(..., description="被授权家庭ID(受权方)")
    expire_time: DateTimeStr = Field(..., description="到期时间(强制授权必填)")
    reason: str | None = Field(default=None, max_length=255, description="授权原因")

    @model_validator(mode="after")
    def _check_expire(self) -> "ErpGrantAdminCreateSchema":
        # 强制授权会绕过户主意愿，必须有明确的时间边界，否则等于永久开放他人数据
        if is_expired(self.expire_time):
            raise ValueError("到期时间必须晚于当前时间")
        if self.family_id == self.target_family_id:
            raise ValueError("授权方与受权方不能是同一个家庭")
        return self


class ErpGrantOutSchema(BaseSchema):
    """共享授权响应模型"""

    model_config = ConfigDict(from_attributes=True)

    family_id: int | None = Field(default=None, description="授权方家庭ID")
    target_family_id: int | None = Field(default=None, description="受权方家庭ID")
    source: str | None = Field(default=None, description="来源(family/admin)")
    granted_by: int | None = Field(default=None, description="操作人ID")
    expire_time: DateTimeStr | None = Field(default=None, description="到期时间")
    status: int | None = Field(default=None, description="状态(0:生效 1:已撤销)")
    revoked_time: DateTimeStr | None = Field(default=None, description="撤销时间")
    reason: str | None = Field(default=None, description="授权原因")
    # service 填充的展示字段
    family_name: str | None = Field(default=None, description="授权方家庭名称")
    target_family_name: str | None = Field(default=None, description="受权方家庭名称")
    revocable: bool = Field(default=False, description="当前用户是否可撤销该授权(admin 来源不可)")

    @computed_field(description="是否已过期")  # type: ignore[prop-decorator]
    @property
    def expired(self) -> bool:
        """按 expire_time 惰性判定是否过期。"""
        return is_expired(self.expire_time)


class ErpGrantQueryParam(BaseQueryParam):
    """共享授权查询参数"""

    family_id: int | None = Field(None, description="授权方家庭ID", json_schema_extra={"q": "eq"})
    target_family_id: int | None = Field(None, description="受权方家庭ID", json_schema_extra={"q": "eq"})
    source: str | None = Field(None, description="来源(family/admin)", json_schema_extra={"q": "eq"})
    status: int | None = Field(None, description="状态(0:生效 1:已撤销)", json_schema_extra={"q": "eq"})
