"""SSE 事件推送端点"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.core.base_schema import AuthSchema
from app.core.dependencies import get_current_user_ws
from app.core.event_bus import EventBus
from app.core.logger import logger

SSERouter = APIRouter(prefix="/events", tags=["SSE 事件推送"])


@SSERouter.get("", response_class=EventSourceResponse)
async def sse_event_stream(
    token: Annotated[str, Query(..., description="认证 token")],
    auth: Annotated[AuthSchema, Depends(get_current_user_ws)],
    last_event_id: Annotated[str | None, Header()] = None,
) -> AsyncIterable[ServerSentEvent]:
    """SSE 事件流端点

    客户端通过 EventSource 连接后可持续接收服务端推送的事件。
    连接断开后浏览器自动重连，并通过 Last-Event-ID 恢复断连期间的事件。

    ## 事件类型
    - `notification` — 系统通知
    - `payment_success` — 支付成功
    - `ticket_reply` — 工单回复

    连接保活由 FastAPI 自动处理（每 15 秒发送 ping 注释）。
    """
    user_id = auth.user.id
    tenant_id = auth.user.tenant_id

    queue = EventBus.subscribe(user_id, tenant_id)
    logger.info(f"SSE 连接建立: user_id={user_id} tenant_id={tenant_id}")

    # 解析断连前最后收到的事件 ID，用于恢复
    event_id = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0

    try:
        while True:
            payload = await queue.get()
            event_id += 1
            yield _to_sse_event(payload, str(event_id))
    except asyncio.CancelledError:
        pass
    finally:
        EventBus.unsubscribe(user_id)
        logger.info(f"SSE 连接断开: user_id={user_id}")


def _to_sse_event(payload: str, event_id: str) -> ServerSentEvent:
    """将 EventBus JSON 消息转换为 ServerSentEvent"""
    try:
        data = json.loads(payload)
        event_type = data.pop("type", "message")
        return ServerSentEvent(data=data, event=event_type, id=event_id)
    except json.JSONDecodeError:
        return ServerSentEvent(raw_data=payload, id=event_id, event="raw")
