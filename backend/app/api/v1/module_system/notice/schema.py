from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.common.enums import QueueEnum
from app.core.base_schema import BaseQueryParam, BaseSchema, TenantByQueryParam, TenantBySchema, UserByQueryParam, UserBySchema
from app.utils.xss_util import sanitize_html


class NoticeCreateSchema(BaseModel):
    """公告通知创建模型"""

    notice_title: str = Field(..., min_length=1, max_length=64, description="公告标题")
    notice_type: str = Field(..., max_length=1, description="公告类型(1:通知 2:公告)")
    notice_content: str | None = Field(default=None, max_length=65535, description="公告内容")
    status: int = Field(default=0, ge=0, le=1, description="状态(0:启动 1:停用)")
    description: str | None = Field(default=None, max_length=255, description="描述")

    @field_validator("notice_type")
    @classmethod
    def _validate_notice_type(cls, value: str):
        if value not in {"1", "2"}:
            raise ValueError("公告类型仅支持 1(通知) 或 2(公告)")
        return value

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: int):
        if value not in {0, 1}:
            raise ValueError("状态仅支持 0(正常) 或 1(禁用)")
        return value

    @field_validator("notice_content")
    @classmethod
    def _sanitize_notice_content(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return sanitize_html(value)

    @model_validator(mode="after")
    def _validate_after(self):
        if not self.notice_title.strip():
            raise ValueError("公告标题不能为空")
        if self.notice_content and not self.notice_content.strip():
            raise ValueError("公告内容不能为空")
        return self


class NoticeUpdateSchema(NoticeCreateSchema):
    """公告通知更新模型"""


class NoticeOutSchema(NoticeCreateSchema, BaseSchema, UserBySchema, TenantBySchema):
    """公告通知响应模型"""

    model_config = ConfigDict(from_attributes=True)


class NoticeQueryParam(BaseQueryParam, UserByQueryParam, TenantByQueryParam):
    """公告通知查询参数"""

    notice_title: str | tuple[str, str] | None = Field(None, description="公告标题")
    notice_type: str | tuple[str, str] | None = Field(None, description="公告类型")
    status: int | tuple[str, int] | None = Field(None, ge=0, le=1, description="状态(0:启动 1:停用)")

    @model_validator(mode="after")
    def validate_query_params(self) -> "NoticeQueryParam":
        if isinstance(self.notice_title, str):
            self.notice_title = (QueueEnum.like.value, self.notice_title)
        if isinstance(self.notice_type, str):
            self.notice_type = (QueueEnum.eq.value, self.notice_type)
        if isinstance(self.status, int):
            self.status = (QueueEnum.eq.value, self.status)
        return self
