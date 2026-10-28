"""物品分类表 —— 后台运营配置，C端只读。

层级策略
--------
需求明确「最多三级」，用 ``level`` + 物化路径 ``path`` 双字段表达：

- ``level`` 冗余存储便于校验（第四级直接 400）和按层查询；
- ``path`` 形如 ``/1/5/12``（各级祖先ID，含自身），查某分类的整棵子树只需
  ``path LIKE '/1/5/%'``，不用递归 CTE，MySQL 5.x/8.x 行为一致。

``path`` 在 service 层写入时计算并随父级变更级联刷新，模型层不做校验。
"""

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin


class ErpCategoryModel(ModelMixin):
    """物品分类表（三级树）"""

    __tablename__: str = "erp_category"
    __table_args__: dict[str, str] = {"comment": "ERP-物品分类(三级)"}

    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="分类名称")
    parent_id: Mapped[int | None] = mapped_column(Integer, default=None, nullable=True, index=True, comment="父分类ID(空表示一级分类)")
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False, index=True, comment="层级(1/2/3)")
    path: Mapped[str] = mapped_column(String(191), default="", nullable=False, index=True, comment="物化路径(/一级ID/二级ID/三级ID)")
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="同级排序值(升序)")
    icon: Mapped[str | None] = mapped_column(String(255), default=None, nullable=True, comment="图标(名称或URL)")
    # is_visible=False 表示后台隐藏该分类：已有物品仍保留归属，但 C端选择器不再展示，
    # 用于「下线一个分类但不想动历史数据」的场景。
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, comment="C端是否可见")
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True, comment="状态(0:启用 1:停用)")
    remark: Mapped[str | None] = mapped_column(Text, default=None, nullable=True, comment="备注")
    deleted_id: Mapped[int | None] = mapped_column(Integer, default=None, nullable=True, comment="删除人ID")
