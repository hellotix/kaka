"""异步事件总线 — SSE 通知推送的核心组件

职责：
- 维护每个用户的 asyncio.Queue（用户退出后自动清理）
- 提供 publish / publish_tenant / subscribe / unsubscribe 接口

使用方：
- SSE 端点 → subscribe / unsubscribe
- 各业务服务 → publish / publish_tenant
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.logger import logger


@dataclass
class _Subscriber:
    """订阅者信息"""

    user_id: int
    tenant_id: int
    queue: asyncio.Queue[str] = field(default_factory=lambda: asyncio.Queue(maxsize=256))


class EventBus:
    """异步事件总线（全局单例）"""

    _subscribers: dict[int, _Subscriber] = {}

    @classmethod
    def subscribe(cls, user_id: int, tenant_id: int) -> asyncio.Queue[str]:
        """为用户创建一个事件队列（已存在则返回现有队列）"""
        sub = cls._subscribers.get(user_id)
        if sub:
            return sub.queue
        sub = _Subscriber(user_id=user_id, tenant_id=tenant_id)
        cls._subscribers[user_id] = sub
        logger.debug(f"SSE 订阅: user_id={user_id} tenant_id={tenant_id}")
        return sub.queue

    @classmethod
    def unsubscribe(cls, user_id: int) -> None:
        """移除用户的事件队列"""
        cls._subscribers.pop(user_id, None)
        logger.debug(f"SSE 取消订阅: user_id={user_id}")

    @classmethod
    async def publish(cls, user_id: int, event: dict[str, Any]) -> None:
        """向指定用户推送事件（用户不在线则静默丢弃）"""
        sub = cls._subscribers.get(user_id)
        if sub is None:
            return
        payload = _build_sse_payload(event)
        try:
            await asyncio.wait_for(sub.queue.put(payload), timeout=2)
        except (TimeoutError, asyncio.QueueFull):
            logger.warning(f"SSE 推送超时或队列满: user_id={user_id}, event={event.get('type')}")

    @classmethod
    async def publish_tenant(cls, tenant_id: int, event: dict[str, Any]) -> None:
        """向租户下所有在线用户推送事件"""
        payload = _build_sse_payload(event)
        tasks = []
        for sub in cls._subscribers.values():
            if sub.tenant_id == tenant_id:
                tasks.append(_put(sub.queue, payload))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @classmethod
    async def publish_all(cls, event: dict[str, Any]) -> None:
        """向所有在线用户广播事件"""
        payload = _build_sse_payload(event)
        tasks = [_put(sub.queue, payload) for sub in cls._subscribers.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @classmethod
    def online_count(cls) -> int:
        """当前在线 SSE 连接数"""
        return len(cls._subscribers)


def _build_sse_payload(event: dict[str, Any]) -> str:
    """将事件字典序列化为 SSE data 行"""
    event.setdefault("timestamp", datetime.now().isoformat())
    return json.dumps(event, ensure_ascii=False)


async def _put(queue: asyncio.Queue[str], payload: str) -> None:
    try:
        await asyncio.wait_for(queue.put(payload), timeout=1)
    except (TimeoutError, asyncio.QueueFull):
        pass
