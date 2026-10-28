"""第三方登录渠道。

已内置微信小程序、微信开放平台（App/扫码）、Sign in with Apple 三种实现；
新增渠道只需继承 ``ThirdPartyAuthenticator`` 并调用 ``register_authenticator``，
登录接口无需改动。渠道未配置对应密钥时统一抛出可读的业务异常。
"""

import asyncio
from abc import ABC, abstractmethod

import httpx
import jwt
from pydantic import BaseModel, Field

from app.config.setting import settings
from app.core.logger import logger

from ...exceptions import BusinessError
from ..core.constants import (
    APPLE_CLIENT_ID,
    APPLE_ISSUER,
    APPLE_JWKS_URL,
    ThirdPartyProvider,
)


class ThirdPartyCredential(BaseModel):
    """第三方登录凭证（各渠道按需取用）"""

    code: str | None = Field(default=None, description="授权码/临时登录凭证")
    identity_token: str | None = Field(default=None, description="苹果 identityToken")
    authorization_code: str | None = Field(default=None, description="苹果 authorizationCode")
    access_token: str | None = Field(default=None, description="已换取的 access_token(预留)")
    nickname: str | None = Field(default=None, description="昵称(前端授权后回传)")
    avatar: str | None = Field(default=None, description="头像(前端授权后回传)")
    email: str | None = Field(default=None, description="邮箱(苹果首次授权返回)")


class ThirdPartyUserInfo(BaseModel):
    """第三方账号统一用户信息"""

    provider: str = Field(..., description="渠道标识")
    openid: str = Field(..., description="渠道内唯一标识")
    unionid: str | None = Field(default=None, description="跨应用唯一标识")
    nickname: str | None = Field(default=None, description="昵称")
    avatar: str | None = Field(default=None, description="头像")
    mobile: str | None = Field(default=None, description="手机号(仅部分渠道可获取)")
    email: str | None = Field(default=None, description="邮箱")
    raw: dict = Field(default_factory=dict, description="渠道原始返回")


class ThirdPartyAuthenticator(ABC):
    """第三方登录渠道抽象基类"""

    provider: ThirdPartyProvider

    @abstractmethod
    async def authenticate(self, credential: ThirdPartyCredential) -> ThirdPartyUserInfo:
        """用前端凭证换取第三方用户信息。

        参数:
        - credential (ThirdPartyCredential): 登录凭证。

        返回:
        - ThirdPartyUserInfo: 统一的第三方用户信息。
        """

    @classmethod
    def is_configured(cls) -> bool:
        """渠道密钥是否已配置（用于登录方式开关接口）。"""
        return False


async def _http_get_json(url: str, params: dict) -> dict:
    """发起 GET 请求并解析 JSON 响应。"""
    try:
        async with httpx.AsyncClient(timeout=settings.HTTPX_DEFAULT_TIMEOUT) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error(f"第三方登录请求失败: url={url}, err={e!s}")
        raise BusinessError(msg="第三方服务请求失败，请稍后重试", status_code=502)


class WechatMiniAuthenticator(ThirdPartyAuthenticator):
    """微信小程序登录（code2Session）"""

    provider = ThirdPartyProvider.WECHAT_MINI

    @classmethod
    def is_configured(cls) -> bool:
        return bool(settings.WX_MINI_APP_ID and settings.WX_MINI_APP_SECRET)

    async def authenticate(self, credential: ThirdPartyCredential) -> ThirdPartyUserInfo:
        if not credential.code:
            raise BusinessError(msg="微信登录凭证 code 不能为空")
        if not self.is_configured():
            raise BusinessError(msg="未配置微信小程序 AppID/AppSecret，无法使用微信登录", status_code=503)

        data = await _http_get_json(
            "https://api.weixin.qq.com/sns/jscode2session",
            {
                "appid": settings.WX_MINI_APP_ID,
                "secret": settings.WX_MINI_APP_SECRET,
                "js_code": credential.code,
                "grant_type": "authorization_code",
            },
        )
        self._raise_for_error(data, "微信 code2Session")

        openid = data.get("openid")
        if not openid:
            raise BusinessError(msg="微信返回数据不完整，登录失败", status_code=502)

        return ThirdPartyUserInfo(
            provider=self.provider.value,
            openid=str(openid),
            unionid=str(data["unionid"]) if data.get("unionid") else None,
            nickname=credential.nickname,
            avatar=credential.avatar,
            raw=data,
        )

    @staticmethod
    def _raise_for_error(data: dict, action: str) -> None:
        """微信接口以 errcode/errmsg 返回错误。"""
        if data.get("errcode"):
            logger.error(f"{action} 失败: {data.get('errcode')} {data.get('errmsg')}")
            raise BusinessError(msg=f"{action}失败: {data.get('errmsg') or data.get('errcode')}", status_code=502)


class WechatOpenAuthenticator(ThirdPartyAuthenticator):
    """微信开放平台登录（App 端 / 网页扫码 OAuth2）"""

    provider = ThirdPartyProvider.WECHAT_OPEN

    @classmethod
    def is_configured(cls) -> bool:
        return bool(settings.OAUTH_WECHAT_OPEN_APP_ID and settings.OAUTH_WECHAT_OPEN_APP_SECRET)

    async def authenticate(self, credential: ThirdPartyCredential) -> ThirdPartyUserInfo:
        if not credential.code:
            raise BusinessError(msg="微信登录凭证 code 不能为空")
        if not self.is_configured():
            raise BusinessError(msg="未配置微信开放平台 AppID/AppSecret，无法使用微信登录", status_code=503)

        token_data = await _http_get_json(
            "https://api.weixin.qq.com/sns/oauth2/access_token",
            {
                "appid": settings.OAUTH_WECHAT_OPEN_APP_ID,
                "secret": settings.OAUTH_WECHAT_OPEN_APP_SECRET,
                "code": credential.code,
                "grant_type": "authorization_code",
            },
        )
        WechatMiniAuthenticator._raise_for_error(token_data, "微信 OAuth2 换取 access_token")

        openid = token_data.get("openid")
        if not openid:
            raise BusinessError(msg="微信返回数据不完整，登录失败", status_code=502)

        nickname = credential.nickname
        avatar = credential.avatar
        access_token = token_data.get("access_token")
        if access_token:
            profile = await _http_get_json(
                "https://api.weixin.qq.com/sns/userinfo",
                {"access_token": access_token, "openid": openid, "lang": "zh_CN"},
            )
            if not profile.get("errcode"):
                nickname = nickname or profile.get("nickname")
                avatar = avatar or profile.get("headimgurl")
                token_data["userinfo"] = profile

        return ThirdPartyUserInfo(
            provider=self.provider.value,
            openid=str(openid),
            unionid=str(token_data["unionid"]) if token_data.get("unionid") else None,
            nickname=nickname,
            avatar=avatar,
            raw=token_data,
        )


class WechatMpAuthenticator(ThirdPartyAuthenticator):
    """微信公众号网页授权登录（预留）

    与开放平台流程一致，仅 AppID/AppSecret 来源不同；
    配置 ``APP_WECHAT_MP_APP_ID`` / ``APP_WECHAT_MP_APP_SECRET`` 后在此实现即可启用。
    """

    provider = ThirdPartyProvider.WECHAT_MP

    async def authenticate(self, credential: ThirdPartyCredential) -> ThirdPartyUserInfo:
        raise BusinessError(msg="微信公众号登录尚未接入，请使用其他登录方式", status_code=503)


_apple_jwk_client: jwt.PyJWKClient | None = None


def _get_apple_jwk_client() -> jwt.PyJWKClient:
    """惰性创建并复用苹果 JWKS 客户端（内置公钥缓存）。"""
    global _apple_jwk_client
    if _apple_jwk_client is None:
        _apple_jwk_client = jwt.PyJWKClient(APPLE_JWKS_URL, cache_keys=True)
    return _apple_jwk_client


class AppleAuthenticator(ThirdPartyAuthenticator):
    """Sign in with Apple 登录

    校验客户端上报的 identityToken：验签（苹果 JWKS 公钥）+ 校验 iss / aud / exp，
    通过后取 sub 作为 openid。需在环境变量 ``APP_APPLE_CLIENT_ID`` 配置 Bundle ID。
    """

    provider = ThirdPartyProvider.APPLE

    @classmethod
    def is_configured(cls) -> bool:
        return bool(APPLE_CLIENT_ID)

    async def authenticate(self, credential: ThirdPartyCredential) -> ThirdPartyUserInfo:
        if not credential.identity_token:
            raise BusinessError(msg="苹果登录凭证 identityToken 不能为空")
        if not self.is_configured():
            raise BusinessError(msg="未配置 APP_APPLE_CLIENT_ID，无法使用苹果登录", status_code=503)

        claims = await asyncio.to_thread(self._decode_identity_token, credential.identity_token)

        openid = claims.get("sub")
        if not openid:
            raise BusinessError(msg="苹果身份令牌缺少 sub 声明，登录失败", status_code=401)

        return ThirdPartyUserInfo(
            provider=self.provider.value,
            openid=str(openid),
            nickname=credential.nickname,
            email=credential.email or (str(claims["email"]) if claims.get("email") else None),
            raw={k: v for k, v in claims.items() if k not in ("sub", "email")},
        )

    @staticmethod
    def _decode_identity_token(identity_token: str) -> dict:
        """验签并解析苹果 identityToken。"""
        try:
            signing_key = _get_apple_jwk_client().get_signing_key_from_jwt(identity_token)
            return jwt.decode(
                jwt=identity_token,
                key=signing_key.key,
                algorithms=["RS256"],
                audience=APPLE_CLIENT_ID,
                issuer=APPLE_ISSUER,
            )
        except jwt.PyJWTError as e:
            logger.error(f"苹果 identityToken 校验失败: {e!s}")
            raise BusinessError(msg="苹果身份令牌校验失败，请重新登录", status_code=401)


_AUTHENTICATOR_REGISTRY: dict[str, type[ThirdPartyAuthenticator]] = {}


def register_authenticator(authenticator_cls: type[ThirdPartyAuthenticator]) -> type[ThirdPartyAuthenticator]:
    """注册第三方登录渠道。

    参数:
    - authenticator_cls (type[ThirdPartyAuthenticator]): 渠道实现类。

    返回:
    - type[ThirdPartyAuthenticator]: 原类（便于作为装饰器使用）。
    """
    _AUTHENTICATOR_REGISTRY[authenticator_cls.provider.value] = authenticator_cls
    return authenticator_cls


register_authenticator(WechatMiniAuthenticator)
register_authenticator(WechatOpenAuthenticator)
register_authenticator(WechatMpAuthenticator)
register_authenticator(AppleAuthenticator)


def get_authenticator(provider: ThirdPartyProvider | str) -> ThirdPartyAuthenticator:
    """获取渠道实例。

    参数:
    - provider (ThirdPartyProvider | str): 渠道标识。

    返回:
    - ThirdPartyAuthenticator: 渠道实例。

    异常:
    - BusinessError: 渠道未注册。
    """
    name = provider.value if isinstance(provider, ThirdPartyProvider) else str(provider)
    authenticator_cls = _AUTHENTICATOR_REGISTRY.get(name)
    if authenticator_cls is None:
        raise BusinessError(msg=f"暂不支持的第三方登录渠道: {name}")
    return authenticator_cls()


def available_providers() -> list[str]:
    """返回已完成密钥配置的渠道列表。"""
    return [name for name, cls in _AUTHENTICATOR_REGISTRY.items() if cls.is_configured()]
