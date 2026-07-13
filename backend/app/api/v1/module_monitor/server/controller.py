import asyncio
from collections.abc import AsyncIterable
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.api.v1.module_monitor.server.schema import ServerMonitorSchema
from app.common.response import ResponseSchema, SuccessResponse
from app.core.base_schema import AuthSchema
from app.core.dependencies import AuthPermission, get_current_user_ws
from app.core.router_class import OperationLogRoute

from .service import ServerService

ServerRouter = APIRouter(route_class=OperationLogRoute, prefix="/server", tags=["服务器监控"])

# ── 服务器监控推送间隔 ──
_SERVER_STREAM_INTERVAL = 5  # 秒


@ServerRouter.get("/info", summary="查询服务器监控信息", response_model=ResponseSchema[ServerMonitorSchema], dependencies=[Security(AuthPermission(["module_monitor:server:query"]))])
async def get_monitor_server_info_controller() -> JSONResponse:
    result_dict = await ServerService.get_server_monitor_info()
    return SuccessResponse(data=result_dict, msg="获取服务器监控信息成功")


@ServerRouter.get("/stream", summary="服务器资源实时推送", response_class=EventSourceResponse)
async def server_monitor_stream(
    token: Annotated[str, Query(..., description="认证 token")],
    auth: Annotated[AuthSchema, Depends(get_current_user_ws)],
) -> AsyncIterable[ServerSentEvent]:
    """SSE 实时推送服务器资源使用情况，每 5 秒推送一次。

    由于 EventSource 不支持自定义请求头，通过查询参数 token 传递认证信息。
    """
    # 手动验证权限（SSE 端点通过查询参数 token 认证，无法使用 Security(AuthPermission)）
    perm_check = AuthPermission(["module_monitor:server:query"])
    await perm_check(auth)

    while True:
        data = await ServerService.get_server_monitor_info()
        yield ServerSentEvent(data=data, event="server_status")
        await asyncio.sleep(_SERVER_STREAM_INTERVAL)
