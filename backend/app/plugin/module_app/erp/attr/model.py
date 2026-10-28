"""扩展属性模板表 —— 后台运营按分类配置，C端录入时按模板渲染表单。

模板生效范围
------------
一条模板挂在某个分类上（``category_id``），或 ``category_id IS NULL`` 表示全局模板。
某分类的**有效属性集** = 全局模板 + 自身及各级祖先分类的模板，由 ``core/attrs.py``
沿分类树向上收集（分类最多三级，最多 4 次合并）。

属性值存哪里
------------
不存在本表。本表只是「schema 定义」，实际值落在物品档案 ``erp_item.attrs`` 这个
JSON 列上，形如 ``{"color": "红", "capacity_ml": 500}``。这样新增一个属性不需要 DDL，
后台配一条模板即可生效。

过滤能力
--------
``is_filterable=True`` 的属性会进入 C端筛选面板，过滤条件由 ``core/attrs.py``
统一翻译成 MySQL JSON 表达式（``JSON_EXTRACT`` + 类型转换）。需求按千级数据量估算，
配合 ``erp_item.family_id`` 索引先收敛行集再算 JSON 表达式即可，不引入生成列或 ES。
"""

from sqlalchemy import JSON, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin


class ErpAttrTemplateModel(ModelMixin):
    """扩展属性模板表"""

    __tablename__: str = "erp_attr_template"
    __table_args__: dict[str, str] = {"comment": "ERP-扩展属性模板"}

    category_id: Mapped[int | None] = mapped_column(Integer, default=None, nullable=True, index=True, comment="所属分类ID(空表示全局模板)")
    # code 是 attrs JSON 里的键名，必须稳定：改动 code 会让历史物品上的该属性失联，
    # 因此 service 层禁止修改已启用模板的 code，只允许停用后新建。
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="属性标识(attrs 的 JSON 键)")
    label: Mapped[str] = mapped_column(String(64), nullable=False, comment="属性显示名")
    type: Mapped[str] = mapped_column(String(16), default="text", nullable=False, index=True, comment="值类型(text/textarea/number/date/bool/select/multi_select)")
    options: Mapped[list | None] = mapped_column(JSON, default=None, nullable=True, comment="候选项(select/multi_select 必填，形如 [{value,label}])")
    unit: Mapped[str | None] = mapped_column(String(16), default=None, nullable=True, comment="单位(如 ml/g/片)")
    default_value: Mapped[str | None] = mapped_column(String(255), default=None, nullable=True, comment="默认值(按字符串存，渲染时按 type 转换)")
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="录入时是否必填")
    is_filterable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="是否进入C端筛选面板")
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="排序值(升序)")
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True, comment="状态(0:启用 1:停用)")
    remark: Mapped[str | None] = mapped_column(Text, default=None, nullable=True, comment="备注")
    deleted_id: Mapped[int | None] = mapped_column(Integer, default=None, nullable=True, comment="删除人ID")
