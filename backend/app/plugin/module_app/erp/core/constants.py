"""家庭 ERP 常量与枚举 —— 子板块内所有魔法值的唯一出处。

设计取舍
--------
1. 家庭归属不进 JWT：一个人可以同时属于多个家庭，令牌里塞 family_id 会导致
   切换家庭必须重新登录。因此家庭上下文靠请求头 ``X-Family-Id`` 逐请求解析
   （见 ``core/context.py``）。
2. 分类三级硬上限：需求明确「最多三级」，第四级直接 400，不做可配置项，
   避免前端渲染层级与后端校验不一致。
3. 扩展属性只由后台运营配置，C端只读。属性值落在物品档案的 JSON 列上，
   过滤逻辑集中在 ``core/attrs.py``，将来数据量涨到万级只改那一处。
"""

from enum import Enum, unique

# ── 请求头 ───────────────────────────────────────────────────────────
# C端所有「家庭内」接口都必须携带该头，指明本次操作的目标家庭。
FAMILY_HEADER: str = "X-Family-Id"

# ── 业务上限 ─────────────────────────────────────────────────────────
CATEGORY_MAX_LEVEL: int = 3  # 分类层级硬上限（一级/二级/三级）
FAMILY_MEMBER_MAX: int = 20  # 单个家庭成员数上限（含户主）
FAMILY_ITEM_MAX: int = 1000  # 单家庭物品档案数上限（需求按千级估算）
INVITE_CODE_LENGTH: int = 8  # 家庭邀请码长度


@unique
class ErpFamilyRole(str, Enum):
    """家庭成员角色（权限从大到小）"""

    OWNER = "owner"  # 户主：唯一，可解散家庭、管理成员与共享授权
    ADMIN = "admin"  # 管理员：可管理成员与物品，不能解散家庭、不能转让户主
    MEMBER = "member"  # 普通成员：可录入与管理物品
    VIEWER = "viewer"  # 只读成员：仅可查看

    @property
    def weight(self) -> int:
        """角色权重，用于「至少某角色」的比较。"""
        return _ROLE_WEIGHT[self]


# 角色权重单独成表，避免在 Enum 里再塞成员导致 str(Enum) 行为异常
_ROLE_WEIGHT: dict["ErpFamilyRole", int] = {
    ErpFamilyRole.OWNER: 40,
    ErpFamilyRole.ADMIN: 30,
    ErpFamilyRole.MEMBER: 20,
    ErpFamilyRole.VIEWER: 10,
}


@unique
class ErpMemberStatus(int, Enum):
    """家庭成员状态"""

    PENDING = 0  # 待确认：户主/管理员定向邀请后，等被邀请人接受
    ACTIVE = 1  # 已加入：正常成员
    REJECTED = 2  # 已拒绝：被邀请人拒绝，记录留痕
    REMOVED = 3  # 已移除：被踢出或主动退出，记录留痕


@unique
class ErpGrantSource(str, Enum):
    """共享授权来源

    - FAMILY：户主自助授权，可随时自行撤销，到期时间可选。
    - ADMIN：后台运营强制授权（如社区共享、活动场景），户主不可自行撤销，
      且必须带到期时间，避免永久性的强制共享。
    """

    FAMILY = "family"
    ADMIN = "admin"


@unique
class ErpGrantStatus(int, Enum):
    """共享授权状态"""

    ACTIVE = 0  # 生效中
    REVOKED = 1  # 已撤销
    EXPIRED = 2  # 已过期（到期时间已过，查询时惰性判定）


@unique
class ErpAttrType(str, Enum):
    """扩展属性值类型 —— 决定 C端渲染哪种输入控件、以及过滤时如何比较"""

    TEXT = "text"  # 单行文本
    TEXTAREA = "textarea"  # 多行文本
    NUMBER = "number"  # 数值（支持范围过滤）
    DATE = "date"  # 日期（YYYY-MM-DD）
    BOOL = "bool"  # 布尔
    SELECT = "select"  # 单选（options 必填）
    MULTI_SELECT = "multi_select"  # 多选（options 必填）


# 需要 options 的属性类型
_ATTR_TYPES_NEED_OPTIONS: frozenset[ErpAttrType] = frozenset({ErpAttrType.SELECT, ErpAttrType.MULTI_SELECT})


def attr_type_need_options(attr_type: str) -> bool:
    """判断某属性类型是否必须配置候选项。"""
    return attr_type in {item.value for item in _ATTR_TYPES_NEED_OPTIONS}


class ErpFamilyPerm:
    """后台权限标识 —— 家庭管理（需在「系统管理-菜单管理」登记后分配给角色）"""

    QUERY = "module_app:erp:family:query"
    DETAIL = "module_app:erp:family:detail"
    UPDATE = "module_app:erp:family:update"
    DELETE = "module_app:erp:family:delete"
    PATCH = "module_app:erp:family:patch"
    MEMBER = "module_app:erp:family:member"
    GRANT_QUERY = "module_app:erp:family:grantquery"
    GRANT_CREATE = "module_app:erp:family:grantcreate"
    GRANT_REVOKE = "module_app:erp:family:grantrevoke"


class ErpCategoryPerm:
    """后台权限标识 —— 物品分类"""

    QUERY = "module_app:erp:category:query"
    DETAIL = "module_app:erp:category:detail"
    CREATE = "module_app:erp:category:create"
    UPDATE = "module_app:erp:category:update"
    DELETE = "module_app:erp:category:delete"
    PATCH = "module_app:erp:category:patch"


class ErpAttrPerm:
    """后台权限标识 —— 扩展属性模板"""

    QUERY = "module_app:erp:attr:query"
    DETAIL = "module_app:erp:attr:detail"
    CREATE = "module_app:erp:attr:create"
    UPDATE = "module_app:erp:attr:update"
    DELETE = "module_app:erp:attr:delete"
    PATCH = "module_app:erp:attr:patch"


@unique
class ErpItemVisibility(str, Enum):
    """物品可见范围 —— 决定同一家庭内其他成员能否看到该物品。

    - FAMILY：全家可见（默认），适合柴米油盐等共享物资。
    - MEMBER：仅本人可见，适合个人私人物品。
    - PRIVATE：私密，仅本人可见且不在家庭统计中展示（如药品等敏感物）。
    """

    FAMILY = "family"  # 全家可见
    MEMBER = "member"  # 仅本人可见
    PRIVATE = "private"  # 私密（仅本人可见且不参与家庭统计）


@unique
class ErpBatchStatus(int, Enum):
    """物品批次状态 —— 库存与过期管理挂在批次维度。

    一个物品档案（如「阿莫西林」）可以有多个批次（不同购买时间/有效期），
    批次状态由用户操作或 P3 定时扫描驱动流转。
    """

    IN_USE = 1  # 在用：数量未耗尽、未过期，正常可消耗
    DEPLETED = 2  # 已耗尽：数量归零，正常用完
    EXPIRED = 3  # 已过期：超过有效期（P3 定时扫描自动置位，也可手动标记）
    DISCARDED = 4  # 已丢弃：过期或损坏后人为丢弃，留痕


# 批次「仍可消耗」的状态集合 —— 消耗扣减、剩余量统计等只认这些状态
BATCH_ACTIVE_STATUSES: frozenset[int] = frozenset({ErpBatchStatus.IN_USE.value})


class ErpItemPerm:
    """后台权限标识 —— 物品管理（C端接口不走权限标识，只认家庭上下文）

    刻意没有 ``PATCH``：物品档案表上没有状态列（在用/耗尽这些状态挂在批次上），
    所以后台物品接口不存在「批量启停」这一类操作，留着标识只会让人去点一个不存在的按钮。
    """

    QUERY = "module_app:erp:item:query"
    DETAIL = "module_app:erp:item:detail"
    CREATE = "module_app:erp:item:create"
    UPDATE = "module_app:erp:item:update"
    DELETE = "module_app:erp:item:delete"


class ErpBatchPerm:
    """后台权限标识 —— 物品批次管理

    单独一组而不是复用 ``ErpItemPerm``：批次是「这次买了多少、什么时候过期」，
    运营改批次的频率远高于改档案（改有效期、标记已丢弃都是日常），
    分成两组标识才能只把批次维护权下放给客服/运营岗。
    """

    QUERY = "module_app:erp:batch:query"
    CREATE = "module_app:erp:batch:create"
    UPDATE = "module_app:erp:batch:update"
    DELETE = "module_app:erp:batch:delete"
