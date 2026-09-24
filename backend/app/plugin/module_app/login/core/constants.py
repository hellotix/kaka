import os
from enum import Enum, unique


def _env_int(name: str, default: int) -> int:
    """读取整型环境变量，非法值回退默认值。"""
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    """读取布尔型环境变量（true/1/yes/on 视为真）。"""
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


@unique
class AppPlatform(str, Enum):
    """C端用户终端类型"""

    IOS = "ios"
    ANDROID = "android"
    WINDOWS = "windows"
    MAC = "mac"
    MINIAPP = "miniapp"
    WEB = "web"


@unique
class AppLoginType(str, Enum):
    """C端登录方式"""

    PASSWORD = "password"
    SMS = "sms"
    WECHAT = "wechat"
    APPLE = "apple"


@unique
class AppRegisterType(str, Enum):
    """C端用户注册来源"""

    PASSWORD = "password"
    SMS = "sms"
    WECHAT = "wechat"
    APPLE = "apple"
    ADMIN = "admin"


@unique
class AppTokenType(str, Enum):
    """令牌类型"""

    ACCESS = "access"
    REFRESH = "refresh"


@unique
class AppSmsScene(str, Enum):
    """短信验证码使用场景"""

    LOGIN = "login"
    REGISTER = "register"
    RESET_PASSWORD = "reset_password"
    BIND_MOBILE = "bind_mobile"


@unique
class ThirdPartyProvider(str, Enum):
    """第三方登录渠道"""

    WECHAT_MINI = "wechat_mini"
    WECHAT_OPEN = "wechat_open"
    WECHAT_MP = "wechat_mp"
    APPLE = "apple"


@unique
class AppLoginStatus(int, Enum):
    """登录日志状态"""

    SUCCESS = 1
    FAILURE = 2


# ── JWT 私有声明：与管理后台 token 隔离，双向互不通用 ──────────────────
APP_TOKEN_TYP = "app"
APP_TOKEN_ISS = "kaka-app"

# ── 令牌有效期（秒）──────────────────────────────────────────────────
ACCESS_TOKEN_EXPIRE_SECONDS: int = _env_int("APP_ACCESS_TOKEN_EXPIRE_SECONDS", 2 * 60 * 60)
REFRESH_TOKEN_EXPIRE_SECONDS: int = _env_int("APP_REFRESH_TOKEN_EXPIRE_SECONDS", 30 * 24 * 60 * 60)
TOKEN_SLIDING_EXPIRE: bool = _env_bool("APP_TOKEN_SLIDING_EXPIRE", True)

# ── 短信验证码 ───────────────────────────────────────────────────────
SMS_PROVIDER: str = os.getenv("APP_SMS_PROVIDER", "logging").strip() or "logging"
SMS_CODE_LENGTH: int = _env_int("APP_SMS_CODE_LENGTH", 6)
SMS_CODE_EXPIRE_SECONDS: int = _env_int("APP_SMS_CODE_EXPIRE_SECONDS", 300)
SMS_RESEND_INTERVAL_SECONDS: int = _env_int("APP_SMS_RESEND_INTERVAL_SECONDS", 60)
SMS_DAILY_LIMIT: int = _env_int("APP_SMS_DAILY_LIMIT", 10)
SMS_MAX_VERIFY_FAIL: int = _env_int("APP_SMS_MAX_VERIFY_FAIL", 5)
SMS_LOGIN_AUTO_REGISTER: bool = _env_bool("APP_SMS_LOGIN_AUTO_REGISTER", True)
SMS_REGISTER_ENABLE: bool = _env_bool("APP_SMS_REGISTER_ENABLE", True)

# ── 密码策略与防爆破 ─────────────────────────────────────────────────
PASSWORD_MIN_LENGTH: int = _env_int("APP_PASSWORD_MIN_LENGTH", 6)
PASSWORD_STRICT: bool = _env_bool("APP_PASSWORD_STRICT", False)
PASSWORD_MAX_FAIL_TIMES: int = _env_int("APP_PASSWORD_MAX_FAIL_TIMES", 5)
PASSWORD_LOCK_SECONDS: int = _env_int("APP_PASSWORD_LOCK_SECONDS", 900)

# ── 苹果登录 ─────────────────────────────────────────────────────────
APPLE_CLIENT_ID: str = os.getenv("APP_APPLE_CLIENT_ID", "").strip()
APPLE_ISSUER: str = "https://appleid.apple.com"
APPLE_JWKS_URL: str = "https://appleid.apple.com/auth/keys"

# ── Redis 键名（独立前缀，避免与后台 user_session / access_token 冲突）──
REDIS_PREFIX: str = "app_login"


def session_key(session_id: str) -> str:
    return f"{REDIS_PREFIX}:session:{session_id}"


def access_token_key(session_id: str) -> str:
    return f"{REDIS_PREFIX}:access_token:{session_id}"


def refresh_token_key(session_id: str) -> str:
    return f"{REDIS_PREFIX}:refresh_token:{session_id}"


def user_sessions_key(user_id: int) -> str:
    return f"{REDIS_PREFIX}:user:{user_id}:sessions"


def sms_code_key(scene: AppSmsScene | str, mobile: str) -> str:
    scene_value = scene.value if isinstance(scene, AppSmsScene) else str(scene)
    return f"{REDIS_PREFIX}:sms:{scene_value}:{mobile}"


def sms_interval_key(mobile: str) -> str:
    return f"{REDIS_PREFIX}:sms:interval:{mobile}"


def sms_daily_key(mobile: str, day: str) -> str:
    return f"{REDIS_PREFIX}:sms:daily:{mobile}:{day}"


def sms_fail_key(scene: AppSmsScene | str, mobile: str) -> str:
    scene_value = scene.value if isinstance(scene, AppSmsScene) else str(scene)
    return f"{REDIS_PREFIX}:sms:fail:{scene_value}:{mobile}"


def password_fail_key(account: str) -> str:
    return f"{REDIS_PREFIX}:password:fail:{account}"


class AppUserPerm:
    """管理后台权限标识 —— 需在「系统管理-菜单管理」中登记后分配给角色"""

    QUERY = "module_app:login:user:query"
    DETAIL = "module_app:login:user:detail"
    CREATE = "module_app:login:user:create"
    UPDATE = "module_app:login:user:update"
    DELETE = "module_app:login:user:delete"
    PATCH = "module_app:login:user:patch"
    RESET_PASSWORD = "module_app:login:user:resetpwd"
    SESSION = "module_app:login:user:session"
    FORCE_LOGOUT = "module_app:login:user:forcelogout"
    LOGIN_LOG = "module_app:login:user:loginlog"
    OAUTH = "module_app:login:user:oauth"
