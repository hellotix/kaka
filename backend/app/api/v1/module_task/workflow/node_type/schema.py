import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.enums import QueueEnum
from app.core.base_schema import BaseQueryParam, BaseSchema, TenantByQueryParam, TenantBySchema, UserByQueryParam, UserBySchema


class WorkflowNodeTypeCreateSchema(BaseModel):
    """创建节点类型"""

    name: str = Field(..., max_length=128, description="显示名称")
    code: str = Field(..., max_length=64, description="节点编码")
    category: str = Field(default="action", max_length=32, description="trigger/action/condition/control")
    func: str = Field(..., description="代码块，须定义 handler")
    args: str | None = Field(default=None, description="默认位置参数")
    kwargs: str | None = Field(default=None, description="默认 kwargs JSON")
    sort_order: int = Field(default=0, ge=0, description="排序")
    is_active: bool = Field(default=True, description="是否启用")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 1 or len(v) > 128:
            raise ValueError("显示名称长度必须在1-128个字符之间")
        return v

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2 or len(v) > 64:
            raise ValueError("节点编码长度必须在2-64个字符之间")
        if not re.match(r"^[A-Za-z][A-Za-z0-9_]*$", v):
            raise ValueError("节点编码必须以字母开头，仅允许字母、数字、下划线")
        return v

    @field_validator("category")
    @classmethod
    def _cat(cls, v: str) -> str:
        allowed = {"trigger", "action", "condition", "control"}
        v = v.strip()
        if v not in allowed:
            raise ValueError(f"category 须为: {allowed}")
        return v

    @model_validator(mode="after")
    def _func_nonempty(self):
        if not self.func or not str(self.func).strip():
            raise ValueError("必须提供 func 代码块")
        return self


class WorkflowNodeTypeUpdateSchema(WorkflowNodeTypeCreateSchema):
    """更新节点类型"""


class WorkflowNodeTypeOutSchema(WorkflowNodeTypeCreateSchema, BaseSchema, UserBySchema, TenantBySchema):
    """输出（含审计与用户信息）"""

    model_config = ConfigDict(from_attributes=True)


class WorkflowNodeTypeQueryParam(BaseQueryParam, UserByQueryParam, TenantByQueryParam):
    """查询"""

    name: str | tuple[str, str] | None = Field(None, description="名称")
    code: str | tuple[str, str] | None = Field(None, description="编码")
    category: str | tuple[str, str] | None = Field(None, description="分类")
    is_active: bool | tuple[str, bool] | None = Field(None, description="是否启用")
    status: int | tuple[str, int] | None = Field(None, ge=0, le=1, description="状态(0:启动 1:停用)")

    @model_validator(mode="after")
    def validate_query_params(self) -> "WorkflowNodeTypeQueryParam":
        if isinstance(self.name, str):
            self.name = (QueueEnum.like.value, self.name)
        if isinstance(self.code, str):
            self.code = (QueueEnum.like.value, self.code)
        if isinstance(self.category, str):
            self.category = (QueueEnum.eq.value, self.category)
        if isinstance(self.is_active, bool):
            self.is_active = (QueueEnum.eq.value, self.is_active)
        if isinstance(self.status, int):
            self.status = (QueueEnum.eq.value, self.status)
        return self
