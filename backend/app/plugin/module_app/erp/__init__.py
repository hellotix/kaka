"""家庭物资管理子板块（module_app/erp）。

对外暴露的核心入口：

- 家庭上下文依赖：``FamilyContext`` / ``CurrentFamily`` / ``FamilyAdmin`` / ``FamilyWriter`` / ``FamilyOwner`` / ``auth_schema``
- 枚举与常量：``ErpFamilyRole`` / ``ErpMemberStatus`` / ``ErpGrantSource`` / ``ErpAttrType`` / ``ErpItemVisibility`` / ``ErpBatchStatus`` / ``CATEGORY_MAX_LEVEL`` / ``FAMILY_HEADER``
- 数据模型：``ErpFamilyModel`` / ``ErpFamilyMemberModel`` / ``ErpFamilyGrantModel`` / ``ErpCategoryModel`` / ``ErpAttrTemplateModel`` / ``ErpItemModel`` / ``ErpItemBatchModel``

路由分组（容器前缀 ``/api/v1/app`` 由插件目录名 ``module_app`` 自动生成）：

- ``/app/erp/family/*``         C端家庭：门户（创建/我的/加入/退出）与家庭内操作（需带 ``X-Family-Id`` 头）
- ``/app/erp/category/*``       C端分类只读：分类树、分类详情
- ``/app/erp/attr/*``           C端扩展属性只读：按分类取有效属性集
- ``/app/erp/item/*``           C端物品：列表、详情、录入、修改、删除、扫码、图片上传、批次增改删
- ``/app/erp/admin/family/*``   后台运营：家庭、成员、共享授权
- ``/app/erp/admin/category/*`` 后台运营：三级分类树维护
- ``/app/erp/admin/attr/*``     后台运营：扩展属性模板维护
- ``/app/erp/admin/item/*``     后台运营：跨家庭的物品档案增删改查
- ``/app/erp/admin/batch/*``    后台运营：跨家庭的批次增删改查

分层约定
--------
每个业务域一个文件夹（``family`` / ``category`` / ``attr`` / ``item``），内部统一
``model.py`` → ``schema.py`` → ``crud.py`` → ``service.py`` → ``controller.py``。
跨域复用的常量、枚举、家庭上下文、JSON 属性处理放在 ``core/``。

``controller.py`` 由 ``app/core/discover.py`` 递归扫描自动注册，不需要在本文件里导出路由。
"""

from .attr.model import ErpAttrTemplateModel
from .category.model import ErpCategoryModel
from .core.constants import (
    CATEGORY_MAX_LEVEL,
    FAMILY_HEADER,
    FAMILY_ITEM_MAX,
    FAMILY_MEMBER_MAX,
    ErpAttrPerm,
    ErpAttrType,
    ErpBatchPerm,
    ErpBatchStatus,
    ErpCategoryPerm,
    ErpFamilyPerm,
    ErpFamilyRole,
    ErpGrantSource,
    ErpGrantStatus,
    ErpItemPerm,
    ErpItemVisibility,
    ErpMemberStatus,
)
from .core.context import (
    CurrentFamily,
    FamilyAdmin,
    FamilyAuth,
    FamilyContext,
    FamilyOwner,
    FamilyWriter,
    auth_schema,
)
from .family.model import ErpFamilyGrantModel, ErpFamilyMemberModel, ErpFamilyModel
from .item.model import ErpItemBatchModel, ErpItemModel

__all__ = [
    "CATEGORY_MAX_LEVEL",
    "CurrentFamily",
    "ErpAttrPerm",
    "ErpAttrTemplateModel",
    "ErpAttrType",
    "ErpBatchPerm",
    "ErpBatchStatus",
    "ErpCategoryModel",
    "ErpCategoryPerm",
    "ErpFamilyGrantModel",
    "ErpFamilyMemberModel",
    "ErpFamilyModel",
    "ErpFamilyPerm",
    "ErpFamilyRole",
    "ErpGrantSource",
    "ErpGrantStatus",
    "ErpItemBatchModel",
    "ErpItemModel",
    "ErpItemPerm",
    "ErpItemVisibility",
    "ErpMemberStatus",
    "FAMILY_HEADER",
    "FAMILY_ITEM_MAX",
    "FAMILY_MEMBER_MAX",
    "FamilyAdmin",
    "FamilyAuth",
    "FamilyContext",
    "FamilyOwner",
    "FamilyWriter",
    "auth_schema",
]
