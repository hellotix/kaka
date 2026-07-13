from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query, Security
from fastapi.responses import JSONResponse
from fastapi_cache import FastAPICache
from fastapi_cache.decorator import cache
from redis.asyncio.client import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.request import PaginationService
from app.common.response import ResponseSchema, SuccessResponse
from app.core.base_schema import AuthSchema, PaginationQueryParam
from app.core.dependencies import AuthPermission, db_getter, get_current_user, redis_getter
from app.core.router_class import OperationLogRoute

from .schema import DashboardStatsSchema, OnlineOutSchema, OnlineQueryParam
from .service import OnlineService

OnlineRouter = APIRouter(route_class=OperationLogRoute, prefix="/online", tags=["在线用户"])

_STATS_NS = "online_stats"


@OnlineRouter.get("/list", summary="获取在线用户列表", response_model=ResponseSchema[list[OnlineOutSchema]], dependencies=[Security(AuthPermission(["module_monitor:online:query"]))])
async def get_online_list_controller(
    redis: Annotated[Redis, Depends(redis_getter)],
    page: Annotated[PaginationQueryParam, Query(description="分页参数")],
    search: Annotated[OnlineQueryParam, Query(description="在线用户查询参数")],
) -> JSONResponse:
    result_dict_list = await OnlineService.get_online_list(redis=redis, search=search)
    result_dict = await PaginationService.paginate(
        data_list=result_dict_list,
        page_no=page.page_no,
        page_size=page.page_size,
    )
    return SuccessResponse(data=result_dict, msg="获取成功")


@OnlineRouter.delete("/delete", summary="强制下线", response_model=ResponseSchema[None], dependencies=[Security(AuthPermission(["module_monitor:online:delete"]))])
async def delete_online_controller(
    session_id: Annotated[str, Body(description="会话编号")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    await OnlineService.delete_online(redis=redis, session_id=session_id)
    await FastAPICache.clear(namespace=_STATS_NS)
    return SuccessResponse(msg="强制下线成功")


@OnlineRouter.delete("/clear", summary="清除所有在线用户", response_model=ResponseSchema[None], dependencies=[Security(AuthPermission(["module_monitor:online:delete"]))])
async def clear_online_controller(
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    await OnlineService.clear_online(redis=redis)
    await FastAPICache.clear(namespace=_STATS_NS)
    return SuccessResponse(msg="清除所有在线用户成功")


@OnlineRouter.get("/stats", summary="获取仪表盘统计数据", response_model=ResponseSchema[DashboardStatsSchema])
@cache(expire=15, namespace=_STATS_NS)
async def get_dashboard_stats_controller(
    db: Annotated[AsyncSession, Depends(db_getter)],
    redis: Annotated[Redis, Depends(redis_getter)],
    _auth: Annotated[AuthSchema, Depends(get_current_user)],
) -> JSONResponse:
    data = await OnlineService.get_dashboard_stats(db=db, redis=redis)
    return SuccessResponse(data=data, msg="获取仪表盘统计成功")
