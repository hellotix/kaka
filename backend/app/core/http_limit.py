from math import ceil

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.websockets import WebSocket

from app.config.setting import settings

# 全局限流器 —— slowapi 通过 storage_uri 创建自己的 Redis 连接
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200/10seconds"],
    storage_uri=settings.REDIS_URI,
)


async def ws_limit_callback(ws: WebSocket, expire: int) -> None:
    """WebSocket 触发限流时的默认回调：关闭连接。"""
    expires = ceil(expire / 1000)
    await ws.close(
        code=1008,
        reason=f"请求过于频繁，请稍后重试！{expires} 秒后重试",
    )


class WebSocketRateLimiter:
    """WebSocket 限流依赖（slowapi 不内置支持 WS，自行实现）。"""

    def __init__(self, max_calls: int = 200, period: int = 10):
        self.max_calls = max_calls
        self.period = period

    async def __call__(self, ws: WebSocket) -> None:
        import time

        redis = getattr(ws.app.state, "redis", None)
        if not redis:
            return

        now = int(time.time())
        window = now // self.period
        key = f"fastapiadmin:request_limiter:ws:{ws.client.host if ws.client else 'unknown'}:{window}"

        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, self.period + 1)

        if count > self.max_calls:
            retry_after = self.period - (now % self.period) + 1
            await ws.close(
                code=1008,
                reason=f"请求过于频繁，请稍后重试！{retry_after} 秒后重试",
            )
