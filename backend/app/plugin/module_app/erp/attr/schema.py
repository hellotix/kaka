"""扩展属性模板的请求/响应模型（后台可写，C端只读）。"""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.base_schema import BaseQueryParam, BaseSchema

from ..core.constants import ErpAttrType, attr_type_need_options

# 合法的值类型集合，供 schema 校验与前端下拉复用
ATTR_TYPES: tuple[str, ...] = tuple(item.value for item in ErpAttrType)


class ErpAttrOptionSchema(BaseModel):
    """select / multi_select 的候选项"""

    value: str = Field(..., min_length=1, max_length=64, description="候选值(落库到 attrs 的值)")
    label: str = Field(..., min_length=1, max_length=64, description="展示文案")


class ErpAttrCreateSchema(BaseModel):
    """新增扩展属性模板（后台）"""

    category_id: int | None = Field(default=None, description="所属分类ID(不填为全局模板，所有分类都继承)")
    code: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]{0,63}$",
        description="属性标识(小写字母开头，仅含小写字母/数字/下划线)",
    )
    label: str = Field(..., min_length=1, max_length=64, description="属性显示名")
    type: str = Field(default=ErpAttrType.TEXT.value, description="值类型(text/textarea/number/date/bool/select/multi_select)")
    options: list[ErpAttrOptionSchema] | None = Field(default=None, description="候选项(select/multi_select 必填)")
    unit: str | None = Field(default=None, max_length=16, description="单位(如 ml/g/片)")
    default_value: str | None = Field(default=None, max_length=255, description="默认值(按字符串存，渲染时按 type 转换)")
    is_required: bool = Field(default=False, description="录入时是否必填")
    is_filterable: bool = Field(default=False, description="是否进入C端筛选面板")
    sort: int = Field(default=0, ge=0, description="排序值(升序)")
    status: int = Field(default=0, ge=0, le=1, description="状态(0:启用 1:停用)")
    remark: str | None = Field(default=None, description="备注")

    @model_validator(mode="after")
    def _check_options(self) -> "ErpAttrCreateSchema":
        """校验类型合法性，以及 select 类必须配候选项。"""
        if self.type not in ATTR_TYPES:
            raise ValueError(f"值类型不合法，可选: {', '.join(ATTR_TYPES)}")
        if attr_type_need_options(self.type):
            if not self.options:
                raise ValueError(f"类型为 {self.type} 时必须配置候选项 options")
            values = [item.value for item in self.options]
            if len(values) != len(set(values)):
                raise ValueError("候选项 value 不能重复")
        elif self.options:
            # 非选择型带了候选项通常是配错了类型，直接拒绝比默默丢弃更容易发现问题
            raise ValueError(f"类型为 {self.type} 时不应配置候选项 options")
        return self


class ErpAttrUpdateSchema(BaseModel):
    """修改扩展属性模板（后台）

    刻意不提供 ``code``：它是物品 ``attrs`` JSON 里的键名，改了会让历史物品上的
    该属性瞬间失联（数据还在 JSON 里，但没有模板能解释它）。需要换标识时请
    停用旧模板再新建一条。
    """

    label: str | None = Field(default=None, min_length=1, max_length=64, description="属性显示名")
    type: str | None = Field(default=None, description="值类型")
    options: list[ErpAttrOptionSchema] | None = Field(default=None, description="候选项")
    unit: str | None = Field(default=None, max_length=16, description="单位")
    default_value: str | None = Field(default=None, max_length=255, description="默认值")
    is_required: bool | None = Field(default=None, description="录入时是否必填")
    is_filterable: bool | None = Field(default=None, description="是否进入C端筛选面板")
    sort: int | None = Field(default=None, ge=0, description="排序值(升序)")
    status: int | None = Field(default=None, ge=0, le=1, description="状态(0:启用 1:停用)")
    remark: str | None = Field(default=None, description="备注")

    @field_validator("type")
    @classmethod
    def _check_type(cls, v: str | None) -> str | None:
        if v is not None and v not in ATTR_TYPES:
            raise ValueError(f"值类型不合法，可选: {', '.join(ATTR_TYPES)}")
        return v


class ErpAttrOutSchema(BaseSchema):
    """扩展属性模板响应模型"""

    model_config = ConfigDict(from_attributes=True)

    category_id: int | None = Field(default=None, description="所属分类ID(空为全局模板)")
    code: str | None = Field(default=None, description="属性标识")
    label: str | None = Field(default=None, description="属性显示名")
    type: str | None = Field(default=None, description="值类型")
    options: list | None = Field(default=None, description="候选项")
    unit: str | None = Field(default=None, description="单位")
    default_value: str | None = Field(default=None, description="默认值")
    is_required: bool | None = Field(default=None, description="是否必填")
    is_filterable: bool | None = Field(default=None, description="是否可筛选")
    sort: int | None = Field(default=None, description="排序值")
    status: int | None = Field(default=None, description="状态(0:启用 1:停用)")
    remark: str | None = Field(default=None, description="备注")
    # service 关联 erp_category 后填充
    category_name: str | None = Field(default=None, description="所属分类名称")
    # C端 schema 接口填充：True 表示该属性继承自祖先分类或全局模板
    inherited: bool = Field(default=False, description="是否继承而来")


class ErpAttrQueryParam(BaseQueryParam):
    """后台扩展属性模板查询参数"""

    category_id: int | None = Field(None, description="所属分类ID", json_schema_extra={"q": "eq"})
    code: str | None = Field(None, description="属性标识", json_schema_extra={"q": "like"})
    label: str | None = Field(None, description="属性显示名", json_schema_extra={"q": "like"})
    type: str | None = Field(None, description="值类型", json_schema_extra={"q": "eq"})
    is_required: bool | None = Field(None, description="是否必填", json_schema_extra={"q": "eq"})
    is_filterable: bool | None = Field(None, description="是否可筛选", json_schema_extra={"q": "eq"})
    status: int | None = Field(None, description="状态(0:启用 1:停用)", json_schema_extra={"q": "eq"})
