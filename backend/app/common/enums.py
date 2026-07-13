from enum import Enum, unique


@unique
class EnvironmentEnum(str, Enum):
    """应用运行环境（开发 / 生产）。"""

    DEV = "dev"
    PROD = "prod"


@unique
class BusinessType(Enum):
    """业务操作类型

    OTHER: 其它
    INSERT: 新增
    UPDATE: 修改
    DELETE: 删除
    GRANT: 授权
    EXPORT: 导出
    IMPORT: 导入
    FORCE: 强退
    GENCODE: 生成代码
    CLEAN: 清空数据
    """

    OTHER = 0
    INSERT = 1
    UPDATE = 2
    DELETE = 3
    GRANT = 4
    EXPORT = 5
    IMPORT = 6
    FORCE = 7
    GENCODE = 8
    CLEAN = 9


@unique
class RedisInitKeyConfig(Enum):
    """系统内置Redis键名枚举"""

    ACCESS_TOKEN = {"key": "access_token", "remark": "登录令牌信息"}
    REFRESH_TOKEN = {"key": "refresh_token", "remark": "刷新令牌信息"}
    USER_SESSION = {"key": "user_session", "remark": "用户会话信息"}
    CAPTCHA_CODES = {"key": "captcha_codes", "remark": "图片验证码"}
    SYSTEM_CONFIG = {"key": "system_config", "remark": "系统配置"}
    TENANT_CONFIG = {"key": "tenant_config", "remark": "租户配置"}
    SYSTEM_DICT = {"key": "system_dict", "remark": "数据字典"}
    APSCHEDULER_LOCK_KEY = {
        "key": "scheduler_job_lock",
        "remark": "定时任务初始化锁",
    }
    AI_MODEL_CONFIG = {"key": "ai_model_config", "remark": "用户AI模型配置"}

    @property
    def key(self) -> str:
        """获取 Redis 键名。

        返回:
        - str: 键名字符串。
        """
        return self.value.get("key", "")

    @property
    def remark(self) -> str:
        """获取 Redis 键说明。

        返回:
        - str: 说明文案。
        """
        return self.value.get("remark", "")


@unique
class QueueEnum(str, Enum):
    """队列枚举"""

    none = "None"
    not_none = "not None"
    date = "date"
    month = "month"
    like = "like"
    eq = "eq"
    in_ = "in"
    between = "between"
    ne = "!="
    gt = ">"
    ge = ">="
    lt = "<"
    le = "<="


class PermissionFilterStrategy(str, Enum):
    """权限过滤策略枚举

    每个策略对应一种过滤实现，模型通过 ``__permission_strategy__`` 选择。
    注意：``DATA_SCOPE`` 是 dispatcher（基于 ``data_scope`` 字段再分发到
    5 个具体的 data_scope 子策略），其余是具体策略。
    """

    DATA_SCOPE = "data_scope"  # 数据范围权限分发器（默认）
    MENU_AUTH = "menu_auth"  # 菜单授权（用于 MenuModel，按角色-菜单绑定过滤）
    DEPT_RELATION = "dept_relation"  # 部门关联（用于 DeptModel、RoleModel，按所属部门过滤）
    OWN = "own"  # 仅本人数据
    USER_BINDING = "user_binding"  # 用户绑定角色（用于 RoleModel，仅显示当前用户绑定的角色）


@unique
class OrderTypeEnum(str, Enum):
    """订单类型"""

    NEW = "new"
    BUY = "buy"
    RENEW = "renew"
    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"


@unique
class InvoiceTypeEnum(str, Enum):
    """发票类型"""

    VAT_NORMAL = "vat_normal"
    VAT_SPECIAL = "vat_special"


@unique
class TicketTypeEnum(str, Enum):
    """工单类型"""

    SUGGESTION = "suggestion"
    BUG = "bug"
    OPTIMIZE = "optimize"
    OTHER = "other"


@unique
class TenantStatusEnum(int, Enum):
    """租户状态枚举

    状态流转：
    NORMAL(正常) ←→ TRIAL(试用) ←→ ARREARS(欠费) → FROZEN(冻结) → CANCELLED(注销)
    """

    NORMAL = 0
    TRIAL = 1
    ARREARS = 2
    FROZEN = 3
    CANCELLED = 4


# ==================== 系统返回码 ====================


class RET(Enum):
    """系统返回码枚举

    0~200: 成功状态码
    400~600: HTTP标准错误码
    4000+: 自定义业务错误码
    """

    # 成功状态码
    OK = (0, "成功")
    SUCCESS = (200, "操作成功")
    CREATED = (201, "创建成功")
    ACCEPTED = (202, "请求已接受")
    NO_CONTENT = (204, "操作成功,无返回数据")

    # HTTP标准错误码
    ERROR = (1, "请求错误")
    BAD_REQUEST = (400, "参数错误")
    UNAUTHORIZED = (401, "未授权")
    FORBIDDEN = (403, "访问受限")
    NOT_FOUND = (404, "资源不存在")
    BAD_METHOD = (405, "不支持的请求方法")
    NOT_ACCEPTABLE = (406, "不接受的请求")
    CONFLICT = (409, "资源冲突")
    GONE = (410, "资源已删除")
    PRECONDITION_FAILED = (412, "前提条件失败")
    UNSUPPORTED_MEDIA_TYPE = (415, "不支持的媒体类型")
    UNPROCESSABLE_ENTITY = (422, "无法处理的实体")
    TOO_MANY_REQUESTS = (429, "请求过于频繁")

    # 服务器错误码
    INTERNAL_SERVER_ERROR = (500, "服务器内部错误")
    NOT_IMPLEMENTED = (501, "功能未实现")
    BAD_GATEWAY = (502, "网关错误")
    SERVICE_UNAVAILABLE = (503, "服务不可用")
    GATEWAY_TIMEOUT = (504, "网关超时")
    HTTP_VERSION_NOT_SUPPORTED = (505, "HTTP版本不支持")

    # 自定义业务错误码
    EXCEPTION = (-1, "系统异常")
    DATAEXIST = (4003, "数据已存在")
    DATAERR = (4004, "数据错误")
    PARAMERR = (4103, "参数错误")
    IOERR = (4302, "IO错误")
    SERVERERR = (4500, "服务错误")
    UNKOWNERR = (4501, "未知错误")
    TIMEOUT = (4502, "请求超时")
    RATE_LIMIT_EXCEEDED = (4503, "访问频率超限")

    # Token相关错误码
    INVALID_TOKEN = (4504, "无效令牌")
    EXPIRED_TOKEN = (4505, "令牌过期")

    # 认证授权错误码
    INVALID_CREDENTIALS = (4506, "无效凭证")

    def __init__(self, code: int, msg: str) -> None:
        self._code = code
        self._msg = msg

    @property
    def code(self) -> int:
        return self._code

    @property
    def msg(self) -> str:
        return self._msg
