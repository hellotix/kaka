"""C端 JWT 签发与解析。

令牌载荷使用私有声明 ``typ=app`` / ``iss=kaka-app``，与管理后台令牌
（``app.core.security``）互相拒绝，避免 C端令牌访问后台接口或反向越权。
"""

import time

import jwt
from fastapi import Request
from fastapi.security.utils import get_authorization_scheme_param
from pydantic import BaseModel, Field

from app.common.enums import RET
from app.config.setting import settings
from app.core.exceptions import CustomException

from .constants import APP_TOKEN_ISS, APP_TOKEN_TYP, AppTokenType


class AppTokenPayload(BaseModel):
    """C端令牌载荷"""

    sub: str = Field(..., description="会话ID")
    uid: int = Field(..., description="C端用户ID")
    typ: str = Field(..., description="令牌归属(app:C端)")
    tt: str = Field(..., description="令牌类型(access/refresh)")
    plat: str = Field(..., description="登录终端")
    iss: str | None = Field(default=None, description="签发者")
    iat: int = Field(default=0, description="签发时间戳")
    exp: int = Field(default=0, description="过期时间戳")


def unauthorized(msg: str) -> CustomException:
    """统一的 401 异常构造。"""
    return CustomException(msg=msg, code=RET.UNAUTHORIZED.code, status_code=401)


def create_app_token(
    *,
    session_id: str,
    user_id: int,
    platform: str,
    token_type: AppTokenType | str,
    expire_seconds: int,
) -> str:
    """签发 C端 JWT。

    参数:
    - session_id (str): 会话ID，作为 sub 声明。
    - user_id (int): C端用户ID。
    - platform (str): 登录终端。
    - token_type (AppTokenType | str): access / refresh。
    - expire_seconds (int): 有效期（秒）。

    返回:
    - str: 编码后的 JWT。
    """
    now = int(time.time())
    payload = {
        "sub": session_id,
        "uid": user_id,
        "typ": APP_TOKEN_TYP,
        "tt": token_type.value if isinstance(token_type, AppTokenType) else str(token_type),
        "plat": platform,
        "iss": APP_TOKEN_ISS,
        "iat": now,
        "exp": now + int(expire_seconds),
    }
    return jwt.encode(payload=payload, key=settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_app_token(
    token: str,
    *,
    token_type: AppTokenType | str,
    verify_exp: bool = True,
) -> AppTokenPayload:
    """解析并校验 C端 JWT。

    参数:
    - token (str): JWT 字符串。
    - token_type (AppTokenType | str): 期望的令牌类型。
    - verify_exp (bool): 是否校验 exp（滑动续期场景传 False，由 Redis 会话决定有效期）。

    返回:
    - AppTokenPayload: 校验通过的载荷。

    异常:
    - CustomException: 令牌缺失、非法、过期或类型不符时抛出 401。
    """
    if not token:
        raise unauthorized("认证不存在，请重新登录")

    options = {} if verify_exp else {"verify_exp": False}
    try:
        payload = jwt.decode(
            jwt=token,
            key=settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options=options,  # type: ignore[arg-type]
        )
    except jwt.ExpiredSignatureError:
        raise unauthorized("登录已过期，请重新登录")
    except (jwt.InvalidSignatureError, jwt.DecodeError):
        raise unauthorized("无效认证，请重新登录")
    except jwt.InvalidTokenError:
        raise unauthorized("令牌已失效，请重新登录")

    if payload.get("typ") != APP_TOKEN_TYP or payload.get("iss") != APP_TOKEN_ISS:
        raise unauthorized("无效凭证，请重新登录")

    expected = token_type.value if isinstance(token_type, AppTokenType) else str(token_type)
    if payload.get("tt") != expected:
        raise unauthorized("令牌类型不正确，请重新登录")

    if not payload.get("sub") or not payload.get("uid"):
        raise unauthorized("无效凭证，请重新登录")

    try:
        return AppTokenPayload(**payload)
    except Exception as e:
        raise unauthorized(f"令牌载荷非法: {e!s}")


def extract_bearer_token(request: Request) -> str | None:
    """从 Authorization 头提取令牌， scheme 不匹配或未携带时返回 None。"""
    authorization = request.headers.get("Authorization")
    if not authorization:
        return None
    scheme, token = get_authorization_scheme_param(authorization)
    if not token or scheme.lower() != settings.TOKEN_TYPE.lower():
        return None
    return token
