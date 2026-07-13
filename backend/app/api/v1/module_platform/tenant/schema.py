from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.enums import OrderTypeEnum, QueueEnum
from app.core.base_schema import BaseQueryParam, BaseSchema
from app.core.validator import DateTimeStr, email_validator, mobile_validator

PackageAction = Literal["buy", "renew", "upgrade", "downgrade"]
PayMethod = Literal["alipay", "wxpay", "free"]


class TenantCreateSchema(BaseModel):
    """新增租户"""

    name: str = Field(..., min_length=1, max_length=100, description="租户名称")
    code: str = Field(..., min_length=2, max_length=100, description="租户编码")
    status: int = Field(default=0, ge=0, le=1, description="状态(0:启动 1:停用)")
    description: str | None = Field(default=None, description="描述")
    start_time: DateTimeStr | None = Field(default=None, description="开始时间")
    end_time: DateTimeStr | None = Field(default=None, description="结束时间")
    contact_name: str | None = Field(default=None, max_length=64, description="联系人姓名")
    contact_phone: str | None = Field(default=None, max_length=20, description="联系人电话")
    contact_email: str | None = Field(default=None, max_length=128, description="联系人邮箱")
    address: str | None = Field(default=None, max_length=255, description="地址")
    domain: str | None = Field(default=None, max_length=255, description="域名")
    logo_url: str | None = Field(default=None, max_length=500, description="Logo URL")
    sort: int = Field(default=0, ge=0, description="排序")
    package_id: int = Field(..., gt=0, description="关联套餐ID（必选，决定租户可用的菜单与配额）")
    version: str | None = Field(default=None, max_length=20, description="版本号")
    favicon: str | None = Field(default=None, max_length=500, description="favicon地址")
    login_bg: str | None = Field(default=None, max_length=500, description="登录背景地址")
    copyright: str | None = Field(default=None, max_length=255, description="版权信息")
    keep_record: str | None = Field(default=None, max_length=100, description="备案号")
    help_doc: str | None = Field(default=None, max_length=500, description="帮助文档地址")
    privacy: str | None = Field(default=None, max_length=500, description="隐私政策地址")
    clause: str | None = Field(default=None, max_length=500, description="服务条款地址")
    git_code: str | None = Field(default=None, max_length=500, description="源码地址")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("租户名称不能为空")
        return v

    @field_validator("code")
    @classmethod
    def _validate_code(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("租户编码不能为空")
        if not v.isalnum():
            raise ValueError("租户编码仅允许字母和数字")
        return v

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: int) -> int:
        if v not in {0, 1}:
            raise ValueError("状态仅支持 0(正常) 或 1(禁用)")
        return v

    @field_validator("contact_phone")
    @classmethod
    def _validate_contact_phone(cls, v: str | None) -> str | None:
        return mobile_validator(v)

    @field_validator("contact_email")
    @classmethod
    def _validate_contact_email(cls, v: str | None) -> str | None:
        if not v:
            return v
        return email_validator(v)

    @model_validator(mode="after")
    def _validate_time_range(self):
        if self.start_time and self.end_time and self.start_time > self.end_time:
            raise ValueError("结束时间不能早于开始时间")
        return self


class TenantUpdateSchema(TenantCreateSchema):
    """更新租户"""

    name: str | None = Field(default=None, max_length=100, description="租户名称")  # type: ignore[assignment]
    code: str | None = Field(default=None, max_length=100, description="租户编码")  # type: ignore[assignment]
    status: int | None = Field(default=None, ge=0, le=1, description="状态(0:启动 1:停用)")
    description: str | None = Field(default=None, description="描述")
    start_time: DateTimeStr | None = Field(default=None, description="开始时间")
    end_time: DateTimeStr | None = Field(default=None, description="结束时间")
    contact_name: str | None = Field(default=None, max_length=64, description="联系人姓名")
    contact_phone: str | None = Field(default=None, max_length=20, description="联系人电话")
    contact_email: str | None = Field(default=None, max_length=128, description="联系人邮箱")
    address: str | None = Field(default=None, max_length=255, description="地址")
    domain: str | None = Field(default=None, max_length=255, description="域名")
    logo_url: str | None = Field(default=None, max_length=500, description="Logo URL")
    sort: int | None = Field(default=None, ge=0, description="排序")
    package_id: int | None = Field(default=None, gt=0, description="关联套餐ID")
    version: str | None = Field(default=None, max_length=20, description="版本号")
    favicon: str | None = Field(default=None, max_length=500, description="favicon地址")
    login_bg: str | None = Field(default=None, max_length=500, description="登录背景地址")
    copyright: str | None = Field(default=None, max_length=255, description="版权信息")
    keep_record: str | None = Field(default=None, max_length=100, description="备案号")
    help_doc: str | None = Field(default=None, max_length=500, description="帮助文档地址")
    privacy: str | None = Field(default=None, max_length=500, description="隐私政策地址")
    clause: str | None = Field(default=None, max_length=500, description="服务条款地址")
    git_code: str | None = Field(default=None, max_length=500, description="源码地址")

    @field_validator("code")
    @classmethod
    def _validate_code(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v.isalnum():
            raise ValueError("租户编码仅允许字母和数字")
        return v

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: int | None) -> int | None:
        if v is None:
            return v
        if v not in {0, 1}:
            raise ValueError("状态仅支持 0(正常) 或 1(禁用)")
        return v

    @field_validator("contact_phone")
    @classmethod
    def _validate_contact_phone(cls, v: str | None) -> str | None:
        return mobile_validator(v)

    @field_validator("contact_email")
    @classmethod
    def _validate_contact_email(cls, v: str | None) -> str | None:
        if not v:
            return v
        return email_validator(v)

    @model_validator(mode="after")
    def _validate_time_range(self):
        if self.start_time and self.end_time and self.start_time > self.end_time:
            raise ValueError("结束时间不能早于开始时间")
        return self


class TenantOutSchema(TenantCreateSchema, BaseSchema):
    """租户响应"""

    model_config = ConfigDict(from_attributes=True)


class TenantAdminInfo(BaseModel):
    """租户初始化管理员账号信息（密码仅在创建租户时一次性返回）"""

    model_config = ConfigDict(from_attributes=True)

    username: str = Field(..., description="初始管理员用户名")
    initial_password: str = Field(..., description="初始明文密码（仅此一次返回，调用方需妥善保管）")
    must_change_password: bool = Field(default=True, description="是否必须修改初始密码（首次登录强制改密）")


class TenantCreateResult(BaseModel):
    """创建租户响应：租户基础信息 + 初始化管理员账号信息"""

    tenant: TenantOutSchema
    admin: TenantAdminInfo


class TenantQueryParam(BaseQueryParam):
    """租户查询参数"""

    name: str | tuple[str, str] | None = Field(None, description="租户名称")
    code: str | tuple[str, str] | None = Field(None, description="租户编码")
    status: int | tuple[str, int] | None = Field(None, ge=0, le=1, description="状态(0:启动 1:停用)")

    @model_validator(mode="after")
    def validate_query_params(self) -> "TenantQueryParam":
        if isinstance(self.name, str):
            self.name = (QueueEnum.like.value, self.name)
        if isinstance(self.code, str):
            self.code = (QueueEnum.like.value, self.code)
        if isinstance(self.status, int):
            self.status = (QueueEnum.eq.value, self.status)
        return self


class TenantUserAddSchema(BaseModel):
    """向租户添加用户"""

    user_id: int = Field(..., gt=0, description="用户ID")
    role: str = Field(default="member", max_length=20, description="租户内角色(owner/admin/member)")
    is_default: int = Field(default=0, ge=0, le=1, description="是否默认租户(0:否 1:是)")

    @field_validator("role")
    @classmethod
    def _validate_role(cls, v: str) -> str:
        if v not in {"owner", "admin", "member"}:
            raise ValueError("租户角色仅支持 owner(拥有者)、admin(管理员)、member(成员)")
        return v

    @field_validator("is_default")
    @classmethod
    def _validate_is_default(cls, v: int) -> int:
        if v not in {0, 1}:
            raise ValueError("是否默认仅支持 0(否) 或 1(是)")
        return v


class TenantUserOutSchema(BaseModel):
    """租户用户响应"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="关联ID")
    user_id: int = Field(..., description="用户ID")
    tenant_id: int = Field(..., description="租户ID")
    role: str = Field(..., description="租户内角色")
    is_default: int = Field(..., description="是否默认租户")
    create_time: DateTimeStr | None = Field(default=None, description="创建时间")
    username: str = Field(default="", description="用户名")
    name: str = Field(default="", description="用户姓名")


class TenantConfigItem(BaseModel):
    """租户配置项"""

    key: str = Field(..., description="配置键")
    value: str | None = Field(default=None, description="配置值")


class TenantConfigOutSchema(BaseModel):
    """租户配置响应"""

    model_config = ConfigDict(from_attributes=True)

    config_key: str = Field(..., description="配置键")
    config_value: str | None = Field(default=None, description="配置值")


class TenantRenewSchema(BaseModel):
    """租户续期"""

    end_time: DateTimeStr = Field(..., description="新的结束时间")

    @model_validator(mode="after")
    def _validate_end_time(self):
        from datetime import datetime

        if self.end_time <= datetime.now():
            raise ValueError("续期时间必须晚于当前时间")
        return self


class PackageChangePreviewOut(BaseModel):
    """套餐变更影响预览响应"""

    new_package_id: int = Field(..., description="新套餐ID")
    new_package_name: str = Field(default="", description="新套餐名称")
    affected_roles: list[dict] = Field(default_factory=list, description="受影响的角色列表（名称、用户数）")
    removed_menus: list[dict] = Field(default_factory=list, description="将被移除的菜单清单（名称、路径）")
    added_menus: list[dict] = Field(default_factory=list, description="新增的菜单清单（名称、路径）")
    quota_changes: dict = Field(default_factory=dict, description="配额变化对比")
    total_affected_users: int = Field(default=0, description="受影响用户数总计")


class PackageAvailableItem(BaseModel):
    """可选套餐项
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="套餐ID")
    name: str = Field(..., description="套餐名称")
    price: int = Field(..., ge=0, description="价格(分)")
    period: str = Field(..., description="计费周期(month/year)")
    trial_days: int = Field(default=0, ge=0, description="试用天数")
    max_users: int = Field(default=0, ge=0, description="最大用户数")
    max_roles: int = Field(default=0, ge=0, description="最大角色数")
    max_depts: int = Field(default=0, ge=0, description="最大部门数")
    max_storage_mb: int = Field(default=0, ge=0, description="最大存储(MB)")
    description: str | None = Field(default=None, description="套餐描述")
    is_current: bool = Field(default=False, description="是否为当前套餐")
    available_actions: list[PackageAction] = Field(default_factory=list, description="可执行操作列表")


class PackageAvailableOut(BaseModel):
    """可选套餐列表
    """

    model_config = ConfigDict(from_attributes=True)

    current_package_id: int | None = Field(default=None, description="当前套餐ID")
    packages: list[PackageAvailableItem] = Field(default_factory=list, description="可选套餐列表")


class PackagePreviewOut(BaseModel):
    """套餐变更预览结果
    """

    model_config = ConfigDict(from_attributes=True)

    current_package: str = Field(default="", description="当前套餐名称")
    target_package: str = Field(default="", description="目标套餐名称")
    action: PackageAction = Field(default="buy", description="操作类型")
    amount: int = Field(default=0, ge=0, description="金额(分)")
    period: str = Field(default="", description="计费周期")
    gained_menus: list[dict] = Field(default_factory=list, description="新增菜单清单")
    lost_menus: list[dict] = Field(default_factory=list, description="移除菜单清单")
    affected_roles: list[str] = Field(default_factory=list, description="受影响的角色名")
    affected_users: int = Field(default=0, ge=0, description="受影响用户数")


class SelfOrderCreate(BaseModel):
    """自助订单创建
    """

    package_id: int = Field(..., ge=1, description="套餐ID")
    order_type: PackageAction = Field(..., description="订单类型(buy/renew/upgrade/downgrade)")


class SelfOrderOut(BaseModel):
    """自助订单创建结果
    """

    model_config = ConfigDict(from_attributes=True)

    order_id: int = Field(..., description="订单ID")
    order_no: str = Field(..., description="订单号")
    amount: int = Field(..., ge=0, description="订单金额(分)")
    need_pay: bool = Field(..., description="是否需要支付")


class SelfOrderListItem(BaseModel):
    """我的订单列表项
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="订单ID")
    order_no: str = Field(..., description="订单号")
    package_name: str = Field(default="", description="套餐名称")
    order_type: OrderTypeEnum = Field(..., description="订单类型")
    amount: int = Field(..., ge=0, description="订单金额(分)")
    status: int = Field(..., description="订单状态(0:待支付 1:已支付 2:已取消 3:已退款)")
    pay_method: str | None = Field(default=None, description="支付方式")
    pay_time: str | None = Field(default=None, description="支付时间")
    created_at: str | None = Field(default=None, description="创建时间")


class SelfOrderListOut(BaseModel):
    """我的订单列表
    """

    model_config = ConfigDict(from_attributes=True)

    items: list[SelfOrderListItem] = Field(default_factory=list, description="订单列表")
    total: int = Field(..., ge=0, description="总记录数")
    page_no: int = Field(..., ge=1, description="页码")
    page_size: int = Field(..., ge=1, description="每页数量")


class SelfOrderDetailOut(BaseModel):
    """订单详情
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="订单ID")
    order_no: str = Field(..., description="订单号")
    package_id: int | None = Field(default=None, description="套餐ID")
    package_name: str = Field(default="", description="套餐名称")
    amount: int = Field(..., ge=0, description="订单金额(分)")
    order_type: OrderTypeEnum = Field(..., description="订单类型")
    status: int = Field(..., description="订单状态(0:待支付 1:已支付 2:已取消 3:已退款)")
    pay_method: str | None = Field(default=None, description="支付方式")
    pay_time: str | None = Field(default=None, description="支付时间")
    created_at: str | None = Field(default=None, description="创建时间")


class WorkspaceTenantInfo(BaseModel):
    """工作台-租户信息
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="租户ID")
    name: str = Field(..., description="租户名称")
    code: str = Field(..., description="租户编码")
    status: int = Field(..., description="租户状态(0:正常 1:宽限期 2:已暂停 3:已冻结 4:已过期 5:已归档)")
    status_label: str = Field(..., description="租户状态描述")
    start_time: str | None = Field(default=None, description="开始时间")
    end_time: str | None = Field(default=None, description="结束时间")
    days_remaining: int = Field(default=0, description="剩余天数")


class WorkspacePackageInfo(BaseModel):
    """工作台-套餐信息
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="套餐ID")
    name: str = Field(..., description="套餐名称")
    price: int = Field(..., ge=0, description="价格(分)")
    period: str = Field(..., description="计费周期")
    max_users: int = Field(..., ge=0, description="最大用户数")
    max_roles: int = Field(..., ge=0, description="最大角色数")
    max_depts: int = Field(..., ge=0, description="最大部门数")


class WorkspaceUsagePercent(BaseModel):
    """工作台-用量百分比
    """

    model_config = ConfigDict(from_attributes=True)

    users: float = Field(default=0.0, ge=0, description="用户用量占比(%)")
    roles: float = Field(default=0.0, ge=0, description="角色用量占比(%)")
    depts: float = Field(default=0.0, ge=0, description="部门用量占比(%)")


class WorkspaceQuotaInfo(BaseModel):
    """工作台-配额用量
    """

    model_config = ConfigDict(from_attributes=True)

    max_users: int = Field(default=0, ge=0, description="最大用户数")
    max_roles: int = Field(default=0, ge=0, description="最大角色数")
    max_depts: int = Field(default=0, ge=0, description="最大部门数")
    current_users: int = Field(default=0, ge=0, description="当前用户数")
    current_roles: int = Field(default=0, ge=0, description="当前角色数")
    current_depts: int = Field(default=0, ge=0, description="当前部门数")
    usage_percent: WorkspaceUsagePercent = Field(default_factory=WorkspaceUsagePercent, description="用量占比")


class WorkspaceOrderItem(BaseModel):
    """工作台-近期订单项
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="订单ID")
    order_no: str = Field(..., description="订单号")
    amount: int = Field(..., ge=0, description="订单金额(分)")
    order_type: OrderTypeEnum = Field(..., description="订单类型")
    status: int = Field(..., description="订单状态(0:待支付 1:已支付 2:已取消 3:已退款)")
    created_at: str | None = Field(default=None, description="创建时间")


class WorkspaceOut(BaseModel):
    """工作台概览
    """

    model_config = ConfigDict(from_attributes=True)

    tenant: WorkspaceTenantInfo = Field(..., description="租户信息")
    package: WorkspacePackageInfo | None = Field(default=None, description="当前套餐信息")
    quota: WorkspaceQuotaInfo = Field(..., description="配额用量")
    recent_orders: list[WorkspaceOrderItem] = Field(default_factory=list, description="近期订单(最多5条)")
