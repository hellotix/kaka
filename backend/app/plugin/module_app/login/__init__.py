"""C端登录子板块（module_app/login）。

对外暴露的核心入口：

- 登录校验依赖：``AppAuth`` / ``OptionalAppAuth`` / ``CurrentAppUser`` / ``MaybeAppUser`` / ``AppAuthContext``
- 枚举与常量：``AppPlatform`` / ``AppLoginType`` / ``AppUserPerm``
- 数据模型：``AppUserModel`` / ``AppUserOauthModel`` / ``AppLoginLogModel``
- 输出模型：``AppUserOutSchema`` / ``AppUserBriefSchema``

路由分组（容器前缀 ``/api/v1/app`` 由插件目录名 ``module_app`` 自动生成）：

- ``/app/login/*``          C端认证：注册、登录、令牌、登出、在线会话
- ``/app/login/user/*``     后台管理：C端用户、登录日志、强制下线（走后台鉴权）
- ``/app/login/profile/*``  C端个人中心：资料、密码、第三方绑定
"""

from .auth.model import AppLoginLogModel
from .core.constants import AppLoginType, AppPlatform, AppRegisterType, AppSmsScene, AppUserPerm, ThirdPartyProvider
from .core.dependencies import (
    AppAuth,
    AppAuthContext,
    CurrentAppUser,
    MaybeAppUser,
    OptionalAppAuth,
    get_current_app_user,
    resolve_app_auth,
)
from .user.model import AppUserModel, AppUserOauthModel
from .user.schema import AppUserBriefSchema, AppUserOutSchema

__all__ = [
    "AppAuth",
    "AppAuthContext",
    "AppLoginLogModel",
    "AppLoginType",
    "AppPlatform",
    "AppRegisterType",
    "AppSmsScene",
    "AppUserBriefSchema",
    "AppUserModel",
    "AppUserOauthModel",
    "AppUserOutSchema",
    "AppUserPerm",
    "CurrentAppUser",
    "MaybeAppUser",
    "OptionalAppAuth",
    "ThirdPartyProvider",
    "get_current_app_user",
    "resolve_app_auth",
]
