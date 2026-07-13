from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.common.enums import InvoiceTypeEnum, QueueEnum
from app.core.base_schema import BaseQueryParam, BaseSchema, TenantBySchema, UserBySchema


class InvoiceCreateSchema(BaseModel):
    """创建发票（内部使用）"""

    invoice_no: str = Field(..., description="发票号码")
    order_id: int = Field(..., description="关联订单 ID")
    invoice_type: InvoiceTypeEnum = Field(..., description="发票类型")
    title: str = Field(..., max_length=200, description="发票抬头")
    tax_no: str | None = Field(default=None, max_length=50, description="纳税人识别号")
    bank_info: str | None = Field(default=None, description="开户行及账号")
    address_info: str | None = Field(default=None, description="注册地址及电话")
    amount: int = Field(..., ge=0, description="发票金额(分)")
    tax_amount: int = Field(default=0, ge=0, description="税额(分)")
    status: int = Field(default=0, ge=0, le=3, description="状态(0:待开票 1:已开票 2:开票失败 3:已作废)")
    description: str | None = Field(default=None, description="备注")


class InvoiceUpdateSchema(BaseModel):
    """更新发票（内部使用）"""

    status: int | None = Field(default=None, ge=0, le=3, description="状态(0:待开票 1:已开票 2:开票失败 3:已作废)")
    pdf_url: str | None = Field(default=None, max_length=500, description="发票 PDF 下载地址")
    oss_license_pdf_url: str | None = Field(default=None, max_length=500, description="开源授权函 PDF 下载地址")
    api_response: str | None = Field(default=None, description="第三方 API 响应")
    description: str | None = Field(default=None, description="备注")


class InvoiceApplySchema(BaseModel):
    """申请开票"""

    order_id: int = Field(..., description="订单 ID")
    invoice_type: InvoiceTypeEnum = Field(..., description="发票类型")
    title: str = Field(..., max_length=200, description="发票抬头")
    tax_no: str | None = Field(default=None, max_length=50, description="纳税人识别号")
    bank_info: str | None = Field(default=None, description="开户行及账号")
    address_info: str | None = Field(default=None, description="注册地址及电话")
    description: str | None = Field(default=None, description="备注")


class InvoiceOutSchema(InvoiceCreateSchema, BaseSchema, UserBySchema, TenantBySchema):
    """发票响应"""

    model_config = ConfigDict(from_attributes=True)

    pdf_url: str | None = Field(default=None, description="发票 PDF 下载地址")
    oss_license_pdf_url: str | None = Field(default=None, description="开源授权函 PDF 下载地址")
    api_response: str | None = Field(default=None, description="第三方 API 响应")


class InvoiceQueryParam(BaseQueryParam):
    """发票查询参数"""

    invoice_type: InvoiceTypeEnum | tuple[str, InvoiceTypeEnum] | None = Field(None, description="发票类型")
    status: int | tuple[str, int] | None = Field(None, description="状态")
    tenant_id: int | tuple[str, int] | None = Field(None, description="租户ID")

    @model_validator(mode="after")
    def validate_query_params(self) -> "InvoiceQueryParam":
        if isinstance(self.invoice_type, InvoiceTypeEnum):
            self.invoice_type = (QueueEnum.eq.value, self.invoice_type)
        if isinstance(self.status, int):
            self.status = (QueueEnum.eq.value, self.status)
        if isinstance(self.tenant_id, int):
            self.tenant_id = (QueueEnum.eq.value, self.tenant_id)
        return self
