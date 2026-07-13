import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.common.enums import EnvironmentEnum
from app.config.path_conf import BASE_DIR, ENV_DIR


class Settings(BaseSettings):
    """系统配置类"""

    model_config = SettingsConfigDict(
        env_file=ENV_DIR / f".env.{os.getenv('ENVIRONMENT')}",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,  # 区分大小写
    )

    # ================================================= #
    # ******************* 项目环境 ****************** #
    # ================================================= #
    ENVIRONMENT: EnvironmentEnum = EnvironmentEnum.DEV

    # ================================================= #
    # ******************* 服务器配置 ****************** #
    # ================================================= #
    SERVER_HOST: str = "0.0.0.0"  # 允许访问的IP地址
    SERVER_PORT: int = 8001  # 服务端口

    # ================================================= #
    # ******************* API文档配置 ****************** #
    # ================================================= #
    DEBUG: bool = True  # 调试模式
    TITLE: str = "🎉 FastapiAdmin 🎉 "  # 文档标题
    VERSION: str = "0.1.0"  # 版本号
    DESCRIPTION: str = "后台接口文档"  # 文档描述
    SUMMARY: str = "接口汇总"  # 文档概述
    DOCS_URL: str = "/docs"  # Swagger UI路径
    REDOC_URL: str = "/redoc"  # ReDoc路径
    WEB_URL: str = "/web"  # 前端路径
    ROOT_PATH: str = "/api/v1"  # API路由前缀

    # ================================================= #
    # ******************** 日志配置 ******************** #
    # ================================================= #
    LOGGER_LEVEL: str = "DEBUG"  # 日志级别

    # ================================================= #
    # ******************** 跨域配置 ******************** #
    # ================================================= #
    ALLOW_ORIGINS: list[str] = ["*"]  # 允许的域名列表
    ALLOW_METHODS: list[str] = ["*"]  # 允许的HTTP方法
    ALLOW_HEADERS: list[str] = ["*"]  # 允许的请求头
    ALLOW_CREDENTIALS: bool = True  # 是否允许携带cookie
    CORS_EXPOSE_HEADERS: list[str] = ["X-Request-ID"]

    # ================================================= #
    # ******************* 登录认证配置 ****************** #
    # ================================================= #
    SECRET_KEY: str = "fastapiadmin-dev-secret-key-do-not-use-in-production"  # JWT密钥（必须通过环境变量 SECRET_KEY 设置，无默认值）
    ALGORITHM: str = "HS256"  # JWT算法
    ACCESS_TOKEN_EXPIRE_SECONDS: int = 60 * 60 * 12  # access_token过期时间(秒)12 小时
    REFRESH_TOKEN_EXPIRE_SECONDS: int = 60 * 60 * 12  # refresh_token过期时间(秒)12 小时
    TOKEN_TYPE: str = "Bearer"  # token类型（RFC 6750 标准大小写）
    TOKEN_SLIDING_EXPIRE: bool = True  # 是否启用滑动过期(用户操作时自动续期)

    # 多租户中间件白名单路径（不需要租户上下文的公开接口）
    TENANT_WHITELIST_PATHS: list[str] = [
        "/api/v1/system/auth/",
        "/api/v1/health",
        "/api/v1/common/health",
    ]

    # ================================================= #
    # ******************* 支付配置 ******************* #
    # ================================================= #
    # 支付宝
    PAYMENT_ALIPAY_APP_ID: str = ""
    PAYMENT_ALIPAY_PRIVATE_KEY: str = ""
    PAYMENT_ALIPAY_PUBLIC_KEY: str = ""
    PAYMENT_ALIPAY_SANDBOX: bool = True
    # 站点 URL（用于生成支付通知 URL）
    SITE_URL: str = "http://localhost:8001"

    # ================================================= #
    # ******************** 数据库配置 ******************* #
    # ================================================= #
    SQL_DB_ENABLE: bool = True  # 是否启用数据库
    DATABASE_ECHO: bool | Literal["debug"] = False  # 是否显示SQL日志
    ECHO_POOL: bool | Literal["debug"] = False  # 是否显示连接池日志
    POOL_SIZE: int = 10  # 连接池大小
    MAX_OVERFLOW: int = 20  # 最大溢出连接数
    POOL_TIMEOUT: int = 30  # 连接超时时间(秒)
    POOL_RECYCLE: int = 1800  # 连接回收时间(秒)
    POOL_USE_LIFO: bool = True  # 是否使用LIFO连接池
    POOL_PRE_PING: bool = True  # 是否开启连接预检
    FUTURE: bool = True  # 是否使用SQLAlchemy 2.0特性
    AUTOCOMMIT: bool = False  # 是否自动提交（映射 SQLAlchemy sessionmaker(autocommit=...)）
    AUTOFLUSH: bool = False  # 是否自动刷新（映射 SQLAlchemy sessionmaker(autoflush=...)）
    AUTOFETCH: bool | None = None  # AUTOFLUSH 别名（优先级高于 AUTOFLUSH，兼容旧环境变量名）
    EXPIRE_ON_COMMIT: bool = False  # 是否在提交时过期

    # MySQL/PostgreSQL数据库连接
    DATABASE_TYPE: Literal["mysql", "postgres", "sqlite"] = "mysql"
    DATABASE_HOST: str = "localhost"
    DATABASE_PORT: int = 3306
    DATABASE_USER: str = "root"
    DATABASE_PASSWORD: str = ""
    DATABASE_NAME: str = "fastapiadmin"

    # ================================================= #
    # ******************** Redis配置 ******************* #
    # ================================================= #
    REDIS_ENABLE: bool = True  # 是否启用Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB_NAME: int = 1
    REDIS_USER: str = ""
    REDIS_PASSWORD: str = ""
    REDIS_HEALTH_CHECK_INTERVAL: int = 20  # Redis 健康检查间隔（秒，对应 async_pool 的 health_check_interval）
    REDIS_DEFAULT_CACHE_TTL: int = 86400  # RedisCURD.set() 默认 TTL（秒，24 小时）

    # ================================================= #
    # ******************** 验证码配置 ******************* #
    # ================================================= #
    CAPTCHA_ENABLE: bool = True  # 是否启用验证码
    CAPTCHA_EXPIRE_SECONDS: int = 60 * 1  # 验证码过期时间(秒) 1分钟
    CAPTCHA_FONT_SIZE: int = 32  # 字体大小
    CAPTCHA_FONT_PATH: str = "static/assets/font/Arial.ttf"  # 字体路径

    # ================================================= #
    # ***************** 第三方 OAuth 登录（可选）********* #
    # ================================================= #
    # 自动注册用户的默认角色 ID 列表（须与库中角色主键一致）
    OAUTH_DEFAULT_ROLE_IDS: list[int] = [2]
    # 回调异常时回跳的前端地址（与前端实际 /login 一致，含协议与端口）
    OAUTH_FRONTEND_FALLBACK: str = "http://127.0.0.1:5173/login"
    OAUTH_GITHUB_CLIENT_ID: str = ""
    OAUTH_GITHUB_CLIENT_SECRET: str = ""
    OAUTH_GITEE_CLIENT_ID: str = ""
    OAUTH_GITEE_CLIENT_SECRET: str = ""
    OAUTH_WECHAT_OPEN_APP_ID: str = ""
    OAUTH_WECHAT_OPEN_APP_SECRET: str = ""
    OAUTH_QQ_APP_ID: str = ""
    OAUTH_QQ_APP_SECRET: str = ""
    OAUTH_STATE_TTL: int = 600  # OAuth state 参数过期时间（秒）

    # ================================================= #
    # ******************* 租户配置 ******************* #
    # ================================================= #
    TENANT_TRIAL_DAYS: int = 7  # 租户注册默认试用天数

    # ================================================= #
    # ******************* 外部 HTTP（httpx）******************* #
    # ================================================= #
    HTTPX_DEFAULT_TIMEOUT: float = 10.0  # 对外 HTTP 请求默认超时（秒）
    IP_LOCATION_ENABLE: bool = True  # 是否启用 IP 归属地查询（登录时对外发起 HTTP 请求）
    IP_LOCATION_CACHE_TTL: int = 604800  # IP 归属地缓存时间（秒，默认 7 天）
    IP_LOCATION_QUERY_TIMEOUT: float = 3.0  # IP 归属地查询单次 HTTP 超时（秒）

    # ================================================= #
    # ******************* SSE 事件推送 ******************* #
    # ================================================= #
    SSE_PUSH_TIMEOUT: int = 2  # SSE 单用户推送超时（秒）
    EVENT_QUEUE_TIMEOUT: int = 1  # 事件队列写入超时（秒）

    # ================================================= #
    # ********************* 日志配置 ******************* #
    # ================================================= #
    OPERATION_RECORD_METHOD: list[str] = [
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "HEAD",
        "OPTIONS",
    ]  # 需要记录的请求方法

    # ================================================= #
    # ******************* Gzip压缩配置 ******************* #
    # ================================================= #
    GZIP_MIN_SIZE: int = 1000  # 最小压缩大小(字节)
    GZIP_COMPRESS_LEVEL: int = 9  # 压缩级别(1-9)

    # ================================================= #
    # ******************* 安全中间件配置 ****************** #
    # ================================================= #
    ALLOWED_HOSTS: list[str] = ["service.fastapiadmin.com", "*.fastapiadmin.com"]  # 允许访问的主机名列表

    # 操作日志保留天数（调度器按此天数定期清理过期日志）
    OPERATION_LOG_RETENTION_DAYS: int = 90

    # 接口白名单（无需认证即可访问的接口路径，支持 * 开头表示前缀匹配）
    WHITE_API_LIST_PATH: list[str] = [
        "/api/v1/system/auth/login",
        "/api/v1/system/auth/token/refresh",
        "/api/v1/system/auth/captcha/get",
        "/api/v1/system/auth/captcha/slider/complete",
        "/api/v1/system/auth/logout",
        "/api/v1/system/auth/tenant-options",
        "/api/v1/system/auth/tenant-search",
        "/api/v1/system/config/info",
        "/api/v1/system/user/current/info",
        "/api/v1/system/notice/available",
        "/api/v1/system/auth/auto-login/users",
        "/api/v1/system/auth/auto-login/token",
        "/api/v1/system/auth/auto-login",
        "/api/v1/common/health",
        "/api/v1/common/health/ready",
        "/api/v1/common/health/live",
        "/metrics",
    ]

    # ================================================= #
    # ***************** 静态文件配置 ***************** #
    # ================================================= #
    STATIC_ENABLE: bool = True  # 是否启用静态文件
    STATIC_URL: str = "/static"  # 访问路由
    STATIC_DIR: str = "static"  # 目录名
    STATIC_ROOT: Path = BASE_DIR.joinpath(STATIC_DIR)  # 绝对路径

    # ================================================= #
    # ***************** 动态文件配置 ***************** #
    # ================================================= #
    UPLOAD_FILE_PATH: Path = Path("static/upload")  # 上传目录
    UPLOAD_MACHINE: str = "A"  # 上传机器标识
    ALLOWED_EXTENSIONS: list[str] = [  # 允许的文件类型
        ".gif",
        ".jpg",
        ".jpeg",
        ".png",
        ".ico",
        ".svg",
        ".xls",
        ".xlsx",
    ]
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 最大文件大小(10MB)

    # ================================================= #
    # ***************** Swagger配置 ***************** #
    # ================================================= #
    SWAGGER_CSS_URL: str = "static/swagger/swagger-ui/swagger-ui.css"
    SWAGGER_JS_URL: str = "static/swagger/swagger-ui/swagger-ui-bundle.js"
    REDOC_JS_URL: str = "static/swagger/redoc/bundles/redoc.standalone.js"
    FAVICON_URL: str = "static/image/favicon.ico"

    # ================================================= #
    # ******************* AI大模型配置 ****************** #
    # ================================================= #
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = ""
    OPENAI_BASE_URL: str = ""  # API Base URL，如 https://api.minimax.chat/v1

    # ================================================= #
    # ******************* 请求限制配置 ****************** #
    # ================================================= #
    @property
    def REDIS_URI(self) -> str:
        """构建 Redis 连接 URI（供 slowapi / 其他模块复用）。"""
        auth_part = ""
        if self.REDIS_USER and self.REDIS_PASSWORD:
            auth_part = f"{self.REDIS_USER}:{self.REDIS_PASSWORD}@"
        elif self.REDIS_PASSWORD:
            auth_part = f":{self.REDIS_PASSWORD}@"
        return f"redis://{auth_part}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB_NAME}"

    # ================================================= #
    # ******************* 动态配置 ******************* #
    # ================================================= #
    @property
    def MIDDLEWARE_LIST(self) -> list[str | None]:
        # 中间件列表（注册时逆序叠加：下列第一项在列表中最前，最终位于最外层，优先生效）
        # 中间件执行顺序（从外到内）：
        #   HTTPSRedirect → TrustedHost → CORS → RequestLog → GZip → CorrelationId → 业务路由
        # 安全响应头（X-Content-Type-Options / Referrer-Policy / Permissions-Policy / HSTS）
        # 由前置 Nginx / 反向代理通过 add_header 设置，避免应用层 BaseHTTPMiddleware 开销。
        MIDDLEWARES: list[str | None] = [
            "app.core.middlewares.CustomHTTPSRedirectMiddleware" if self.ENVIRONMENT == EnvironmentEnum.PROD else None,
            "app.core.middlewares.CustomTrustedHostMiddleware" if self.ENVIRONMENT == EnvironmentEnum.PROD else None,
            "app.core.middlewares.CustomCORSMiddleware",
            "app.core.middlewares.RequestLogMiddleware",
            "app.core.middlewares.CustomGZipMiddleware",
            "app.core.middlewares.CorrelationIdMiddleware",  # 请求上下文
            "app.core.middlewares.TenantMiddleware",  # 租户上下文（需 JWT）
            "slowapi.middleware.SlowAPIMiddleware",  # 接口限流（读取 app.state.limiter）
        ]
        return MIDDLEWARES

    @property
    def ASYNC_DB_URI(self) -> str:
        if self.DATABASE_TYPE not in ("mysql", "postgres", "sqlite"):
            raise ValueError(f"数据库驱动不支持: {self.DATABASE_TYPE}, 异步数据库请选择 mysql、postgres、sqlite")
        db_connect: str = ""
        if self.DATABASE_TYPE == "mysql":
            db_connect = f"mysql+aiomysql://{self.DATABASE_USER}:{quote_plus(self.DATABASE_PASSWORD)}@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}?charset=utf8mb4"
        elif self.DATABASE_TYPE == "postgres":
            db_connect = f"postgresql+asyncpg://{self.DATABASE_USER}:{quote_plus(self.DATABASE_PASSWORD)}@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"
        else:
            db_connect = f"sqlite+aiosqlite:///{self.DATABASE_NAME}.db"
        return db_connect

    @property
    def DB_URI(self) -> str:
        if self.DATABASE_TYPE not in ("mysql", "postgres", "sqlite"):
            raise ValueError(f"数据库驱动不支持: {self.DATABASE_TYPE}, 同步数据库请选择 mysql、postgres、sqlite")
        db_connect: str = ""
        if self.DATABASE_TYPE == "mysql":
            db_connect = f"mysql+pymysql://{self.DATABASE_USER}:{quote_plus(self.DATABASE_PASSWORD)}@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}?charset=utf8mb4"
        elif self.DATABASE_TYPE == "postgres":
            db_connect = f"postgresql+psycopg://{self.DATABASE_USER}:{quote_plus(self.DATABASE_PASSWORD)}@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"
        else:
            db_connect = f"sqlite:///{self.DATABASE_NAME}.db"
        return db_connect

    @property
    def FASTAPI_CONFIG(self) -> dict[str, Any]:
        return {
            "debug": self.DEBUG,
            "title": self.TITLE,
            "version": self.VERSION,
            "description": self.DESCRIPTION,
            "summary": self.SUMMARY,
            "docs_url": None,
            "redoc_url": None,
            "root_path": self.ROOT_PATH,
            "openapi_tags": [
                # ── 系统管理 ──
                {"name": "认证授权", "description": "用户登录、Token刷新、密码找回等"},
                {"name": "用户管理", "description": "系统用户的新增、编辑、导入导出"},
                {"name": "部门管理", "description": "组织架构的维护"},
                {"name": "角色管理", "description": "角色权限分配"},
                {"name": "岗位管理", "description": "岗位信息的维护"},
                {"name": "菜单管理", "description": "系统菜单与权限按钮管理"},
                {"name": "字典管理", "description": "数据字典的类型与值维护"},
                {"name": "参数管理", "description": "系统参数配置"},
                {"name": "公告通知", "description": "系统公告发布与维护"},
                {"name": "工单管理", "description": "用户工单提交与处理"},
                {"name": "日志管理", "description": "操作日志、登录日志的查询"},
                {"name": "SSE 事件推送", "description": "服务端实时事件推送"},
                # ── 租户运营 ──
                {"name": "租户管理", "description": "多租户的创建、配置与套餐管理"},
                {"name": "套餐管理", "description": "套餐定义与定价"},
                {"name": "订单管理", "description": "套餐订单的支付与退款"},
                {"name": "发票管理", "description": "发票申请与PDF导出"},
                # ── 系统监控 ──
                {"name": "在线用户", "description": "查看当前在线用户"},
                {"name": "缓存监控", "description": "Redis 缓存管理与监控"},
                {"name": "资源管理", "description": "服务器资源文件管理"},
                {"name": "服务器监控", "description": "服务器性能指标查看"},
                # ── 通用功能 ──
                {"name": "文件管理", "description": "文件上传与存储"},
                {"name": "健康检查", "description": "服务健康状态检查"},
                # ── AI 助手 ──
                {"name": "AI管理", "description": "AI 对话会话与模型管理"},
                {"name": "智能助手WebSocket", "description": "AI 智能助手实时对话"},
                # ── 任务编排 ──
                {"name": "流程编排", "description": "工作流流程定义与管理"},
                {"name": "工作流节点", "description": "工作流节点类型管理"},
                {"name": "定时任务管理", "description": "定时任务的创建与执行"},
                {"name": "定时任务节点管理", "description": "定时任务节点处理器管理"},
                # ── 代码生成 ──
                {"name": "代码生成", "description": "根据数据表生成 CRUD 代码"},
            ],
            "responses": {
                200: {"description": "成功"},
                400: {"description": "请求参数错误"},
                401: {"description": "未认证"},
                403: {"description": "未授权"},
                404: {"description": "资源不存在"},
                422: {"description": "请求参数验证错误"},
                500: {"description": "服务器内部错误"},
            },
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
