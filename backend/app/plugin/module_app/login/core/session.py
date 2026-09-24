"""C端登录会话仓储（Redis）。

会话结构与后台 ``user_session`` 完全隔离：
- ``app_login:session:{session_id}``  会话详情 JSON（TTL = refresh token 有效期）
- ``app_login:access_token:{session_id}`` / ``app_login:refresh_token:{session_id}``  令牌留档，便于后台强制下线与排查
- ``app_login:user:{user_id}:sessions``  该用户在线会话 ID 集合，用于多端在线列表与批量下线
"""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio.client import Redis

from app.core.logger import logger
from app.core.redis_crud import RedisCURD
from app.core.validator import DateTimeStr

from .constants import (
    ACCESS_TOKEN_EXPIRE_SECONDS,
    REFRESH_TOKEN_EXPIRE_SECONDS,
    access_token_key,
    refresh_token_key,
    session_key,
    user_sessions_key,
)


class AppSessionInfo(BaseModel):
    """Redis 中存储的 C端会话信息"""

    model_config = ConfigDict(from_attributes=True)

    session_id: str = Field(..., description="会话ID")
    user_id: int = Field(..., description="C端用户ID")
    username: str | None = Field(default=None, description="用户名")
    nickname: str | None = Field(default=None, description="昵称")
    mobile: str | None = Field(default=None, description="手机号")
    avatar: str | None = Field(default=None, description="头像")
    platform: str = Field(..., description="登录终端")
    login_type: str = Field(..., description="登录方式")
    login_ip: str | None = Field(default=None, description="登录IP")
    login_location: str | None = Field(default=None, description="登录归属地")
    device_os: str | None = Field(default=None, description="操作系统")
    device_browser: str | None = Field(default=None, description="浏览器/客户端")
    user_agent: str | None = Field(default=None, description="原始 User-Agent")
    login_time: DateTimeStr | None = Field(default=None, description="登录时间")


class AppSessionStore:
    """C端会话读写封装"""

    def __init__(self, redis: Redis) -> None:
        self.redis = redis
        self.cache = RedisCURD(redis)

    async def save(self, info: AppSessionInfo, *, access_token: str, refresh_token: str) -> AppSessionInfo:
        """写入会话、令牌与用户在线集合。"""
        index_key = user_sessions_key(info.user_id)
        await self.cache.set(key=session_key(info.session_id), value=info.model_dump_json(), expire=REFRESH_TOKEN_EXPIRE_SECONDS)
        await self.cache.set(key=access_token_key(info.session_id), value=access_token, expire=ACCESS_TOKEN_EXPIRE_SECONDS)
        await self.cache.set(key=refresh_token_key(info.session_id), value=refresh_token, expire=REFRESH_TOKEN_EXPIRE_SECONDS)
        await self.redis.sadd(index_key, info.session_id)
        await self.redis.expire(index_key, REFRESH_TOKEN_EXPIRE_SECONDS)
        return info

    async def get(self, session_id: str) -> AppSessionInfo | None:
        """读取会话详情，不存在或已过期返回 None。"""
        if not session_id:
            return None
        raw = await self.cache.get(session_key(session_id))
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            return AppSessionInfo.model_validate_json(raw)
        except Exception as e:
            logger.error(f"C端会话数据解析失败: session_id={session_id}, err={e!s}")
            return None

    async def get_token(self, session_id: str, *, token_type: str) -> str | None:
        """读取留档令牌（access / refresh）。"""
        key = access_token_key(session_id) if token_type == "access" else refresh_token_key(session_id)
        value = await self.cache.get(key)
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value

    async def renew(self, session_id: str) -> None:
        """滑动续期：会话与令牌 TTL 重置。"""
        await self.cache.expire(key=session_key(session_id), expire=REFRESH_TOKEN_EXPIRE_SECONDS)
        await self.cache.expire(key=access_token_key(session_id), expire=ACCESS_TOKEN_EXPIRE_SECONDS)
        await self.cache.expire(key=refresh_token_key(session_id), expire=REFRESH_TOKEN_EXPIRE_SECONDS)

    async def update_token(self, session_id: str, *, access_token: str, refresh_token: str) -> None:
        """刷新令牌后覆盖留档并续期会话。"""
        await self.cache.set(key=access_token_key(session_id), value=access_token, expire=ACCESS_TOKEN_EXPIRE_SECONDS)
        await self.cache.set(key=refresh_token_key(session_id), value=refresh_token, expire=REFRESH_TOKEN_EXPIRE_SECONDS)
        await self.cache.expire(key=session_key(session_id), expire=REFRESH_TOKEN_EXPIRE_SECONDS)

    async def update_info(self, info: AppSessionInfo) -> None:
        """覆盖会话详情（保留剩余 TTL）。"""
        ttl = await self.cache.ttl(key=session_key(info.session_id))
        await self.cache.set(key=session_key(info.session_id), value=info.model_dump_json(), expire=max(int(ttl), 1))

    async def remove(self, session_id: str) -> None:
        """下线单个会话：删除会话、令牌并从用户在线集合移除。"""
        info = await self.get(session_id)
        await self.cache.delete(session_key(session_id), access_token_key(session_id), refresh_token_key(session_id))
        if info:
            await self.redis.srem(user_sessions_key(info.user_id), session_id)

    async def list_by_user(self, user_id: int) -> list[AppSessionInfo]:
        """列出用户在线会话，顺带清理已过期的会话ID。"""
        index_key = user_sessions_key(user_id)
        session_ids: list[str] = list(await self.redis.smembers(index_key))
        if not session_ids:
            return []

        sessions: list[AppSessionInfo] = []
        expired: list[str] = []
        for session_id in session_ids:
            info = await self.get(session_id)
            if info:
                sessions.append(info)
            else:
                expired.append(session_id)

        if expired:
            await self.redis.srem(index_key, *expired)

        sessions.sort(key=lambda item: item.login_time or datetime.now(UTC), reverse=True)
        return sessions

    async def remove_by_user(self, user_id: int, *, exclude_session_id: str | None = None) -> int:
        """下线用户全部会话，可排除当前会话；返回实际下线数量。"""
        index_key = user_sessions_key(user_id)
        session_ids: list[str] = list(await self.redis.smembers(index_key))
        count = 0
        for session_id in session_ids:
            if exclude_session_id and session_id == exclude_session_id:
                continue
            await self.cache.delete(session_key(session_id), access_token_key(session_id), refresh_token_key(session_id))
            await self.redis.srem(index_key, session_id)
            count += 1
        return count
