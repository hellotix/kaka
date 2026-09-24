"""C端客户端插件（module_app）—— C端所有接口的统一入口。

目录约定
--------
每个子板块一个文件夹，文件夹名即路由的子板块名，接口路径为
``/api/v1/app/{子板块名}/{业务路径}``（``/api/v1/app`` 由插件目录名自动生成）::

    module_app/
    ├── login/          子板块：注册登录、令牌会话、C端用户
    │   ├── core/       JWT、Redis 会话、登录校验依赖、常量
    │   ├── auth/       controller / service / crud / model / schema / sms / third_party
    │   └── user/       controller / service / crud / model / schema
    └── <新子板块>/      同上结构，controller.py 会被自动扫描注册

每个子板块内部再按 ``core / auth / user / ...`` 分层，controller.py 可位于任意深度，
``app/core/discover.py`` 会递归扫描 ``module_*/**/controller.py`` 并挂载。

跨子板块复用
------------
登录校验依赖统一从插件根导出，其他子板块直接引用::

    from app.plugin.module_app import CurrentAppUser, MaybeAppUser, AppAuth, AppPlatform

    @SomeRouter.get("/xxx")
    async def xxx(user: CurrentAppUser) -> JSONResponse: ...   # 必须登录

    @SomeRouter.get("/yyy")
    async def yyy(user: MaybeAppUser) -> JSONResponse: ...     # 登录可选

    @SomeRouter.get("/zzz")
    async def zzz(
        user: Annotated[AppAuthContext, Depends(AppAuth(platforms=[AppPlatform.IOS]))],
    ) -> JSONResponse: ...                                     # 限制终端
"""

from .login import (
    AppAuth,
    AppAuthContext,
    AppLoginLogModel,
    AppLoginType,
    AppPlatform,
    AppRegisterType,
    AppSmsScene,
    AppUserBriefSchema,
    AppUserModel,
    AppUserOauthModel,
    AppUserOutSchema,
    AppUserPerm,
    CurrentAppUser,
    MaybeAppUser,
    OptionalAppAuth,
    ThirdPartyProvider,
    get_current_app_user,
    resolve_app_auth,
)

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
