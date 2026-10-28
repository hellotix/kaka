"""物品分类的请求/响应模型（后台可写，C端只读）。"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.base_schema import BaseQueryParam, BaseSchema

from ..core.constants import CATEGORY_MAX_LEVEL


class ErpCategoryCreateSchema(BaseModel):
    """新增分类（后台）"""

    name: str = Field(..., min_length=1, max_length=64, description="分类名称")
    parent_id: int | None = Field(default=None, description="父分类ID(不填为一级分类)")
    sort: int = Field(default=0, ge=0, description="同级排序值(升序)")
    icon: str | None = Field(default=None, max_length=255, description="图标")
    is_visible: bool = Field(default=True, description="C端是否可见")
    status: int = Field(default=0, ge=0, le=1, description="状态(0:启用 1:停用)")
    remark: str | None = Field(default=None, description="备注")

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("分类名称不能为空")
        return v


class ErpCategoryUpdateSchema(BaseModel):
    """修改分类（后台）

    刻意不提供 ``parent_id``：移动分类需要级联刷新整棵子树的 level 与 path，
    一旦漏刷就会出现「层级说是2、路径却是3段」的脏数据，而物品档案还挂在旧分类上。
    需要调整层级时请新建目标分类、停用旧分类。
    """

    name: str | None = Field(default=None, min_length=1, max_length=64, description="分类名称")
    sort: int | None = Field(default=None, ge=0, description="同级排序值(升序)")
    icon: str | None = Field(default=None, max_length=255, description="图标")
    is_visible: bool | None = Field(default=None, description="C端是否可见")
    status: int | None = Field(default=None, ge=0, le=1, description="状态(0:启用 1:停用)")
    remark: str | None = Field(default=None, description="备注")


class ErpCategoryOutSchema(BaseSchema):
    """分类响应模型"""

    model_config = ConfigDict(from_attributes=True)

    name: str | None = Field(default=None, description="分类名称")
    parent_id: int | None = Field(default=None, description="父分类ID")
    level: int | None = Field(default=None, description="层级(1/2/3)")
    path: str | None = Field(default=None, description="物化路径")
    sort: int | None = Field(default=None, description="排序值")
    icon: str | None = Field(default=None, description="图标")
    is_visible: bool | None = Field(default=None, description="C端是否可见")
    status: int | None = Field(default=None, description="状态(0:启用 1:停用)")
    remark: str | None = Field(default=None, description="备注")
    parent_name: str | None = Field(default=None, description="父分类名称")
    item_count: int = Field(default=0, description="该分类下直接挂载的物品数(P1 起填充)")


class ErpCategoryTreeSchema(BaseModel):
    """分类树节点（C端级联选择器 / 后台树形表格共用）"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="分类ID")
    name: str = Field(..., description="分类名称")
    parent_id: int | None = Field(default=None, description="父分类ID")
    level: int = Field(default=1, description="层级")
    sort: int = Field(default=0, description="排序值")
    icon: str | None = Field(default=None, description="图标")
    is_visible: bool = Field(default=True, description="C端是否可见")
    status: int = Field(default=0, description="状态(0:启用 1:停用)")
    children: list["ErpCategoryTreeSchema"] = Field(default_factory=list, description="子分类")


# 自引用模型必须显式 rebuild，否则 FastAPI 生成 OpenAPI 时会报未解析的前向引用
ErpCategoryTreeSchema.model_rebuild()


class ErpCategoryQueryParam(BaseQueryParam):
    """后台分类查询参数"""

    name: str | None = Field(None, description="分类名称", json_schema_extra={"q": "like"})
    parent_id: int | None = Field(None, description="父分类ID", json_schema_extra={"q": "eq"})
    level: int | None = Field(None, ge=1, le=CATEGORY_MAX_LEVEL, description="层级", json_schema_extra={"q": "eq"})
    is_visible: bool | None = Field(None, description="C端是否可见", json_schema_extra={"q": "eq"})
    status: int | None = Field(None, description="状态(0:启用 1:停用)", json_schema_extra={"q": "eq"})
