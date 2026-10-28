"""扩展属性模板接口 —— 后台维护模板，C端按分类取有效属性集。

完整路径前缀 ``/api/v1/app``（来自插件目录 ``module_app``），本文件两组路由：

- ``ErpAttrAdminRouter``  ``/erp/admin/attr/*``  后台运营接口，走 ``AuthPermission`` 权限标识
- ``ErpAttrRouter``       ``/erp/attr/*``        C端只读，仅需登录

C端 ``GET /erp/attr/schema/{category_id}`` 的用途
-------------------------------------------------
返回该分类「有效属性集」（自身 + 各级祖先 + 全局模板，同 code 就近覆盖）。
录入表单和筛选面板都由它驱动渲染，前端不需要硬编码任何字段。
带 ``only_filterable=true`` 时只返回运营勾了「可筛选」的模板，给筛选面板瘦身。
"""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Query, status
from fastapi.responses import JSONResponse
from redis.asyncio.client import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import ResponseSchema, SuccessResponse
from app.core.base_schema import AuthSchema, BatchSetAvailable, PageResultSchema, PaginationQueryParam
from app.core.dependencies import AuthPermission, db_getter, redis_getter
from app.core.router_class import OperationLogRoute
from app.plugin.module_app.login.core.dependencies import CurrentAppUser

from ..core.constants import ErpAttrPerm
from ..core.context import auth_schema
from .schema import ErpAttrCreateSchema, ErpAttrOutSchema, ErpAttrQueryParam, ErpAttrUpdateSchema
from .service import ErpAttrService

# C端只读接口不挂 OperationLogRoute：那是后台操作日志，属性集查询是高频只读请求。
ErpAttrAdminRouter = APIRouter(route_class=OperationLogRoute, prefix="/erp/admin/attr", tags=["ERP-扩展属性(后台)"])
ErpAttrRouter = APIRouter(prefix="/erp/attr", tags=["ERP-扩展属性"])


# ══════════════════════════ 后台：模板运营 ══════════════════════════


@ErpAttrAdminRouter.get("/list", summary="分页查询属性模板", response_model=ResponseSchema[PageResultSchema[ErpAttrOutSchema]])
async def admin_attr_list_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpAttrPerm.QUERY]))],
    page: Annotated[PaginationQueryParam, Depends()],
    search: Annotated[ErpAttrQueryParam, Query()],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """后台分页查询属性模板。"""
    service = ErpAttrService(auth, db, redis)
    result = await service.page(page_no=page.page_no, page_size=page.page_size, search=search, order_by=page.order_by)
    return SuccessResponse(data=result, msg="查询属性模板成功")


@ErpAttrAdminRouter.get("/detail/{id}", summary="获取属性模板详情", response_model=ResponseSchema[ErpAttrOutSchema])
async def admin_attr_detail_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpAttrPerm.DETAIL]))],
    id: Annotated[int, Path(description="属性模板ID")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """后台获取属性模板详情。"""
    service = ErpAttrService(auth, db, redis)
    result = await service.detail(id=id)
    return SuccessResponse(data=result, msg="获取属性模板详情成功")


@ErpAttrAdminRouter.get("/list-by-category/{category_id}", summary="按分类查询模板", response_model=ResponseSchema[list[ErpAttrOutSchema]])
async def admin_attr_list_by_category_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpAttrPerm.QUERY]))],
    category_id: Annotated[int, Path(description="分类ID")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """列出某分类**直接配置**的模板（不含继承），后台编辑页用。

    要看「这个分类最终会长出哪些字段」请用 C端的 ``/erp/attr/schema/{category_id}``。
    """
    service = ErpAttrService(auth, db, redis)
    result = await service.list_by_category(category_id=category_id)
    return SuccessResponse(data=result, msg="查询属性模板成功")


@ErpAttrAdminRouter.post("/create", status_code=status.HTTP_201_CREATED, summary="新增属性模板", response_model=ResponseSchema[ErpAttrOutSchema])
async def admin_attr_create_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpAttrPerm.CREATE]))],
    data: Annotated[ErpAttrCreateSchema, Body(description="属性模板信息")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """新增属性模板。同一作用域（同分类或全局）内 code 不可重复。"""
    service = ErpAttrService(auth, db, redis)
    result = await service.create(data=data)
    return SuccessResponse(data=result, msg="新增属性模板成功")


@ErpAttrAdminRouter.put("/update/{id}", summary="修改属性模板", response_model=ResponseSchema[ErpAttrOutSchema])
async def admin_attr_update_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpAttrPerm.UPDATE]))],
    id: Annotated[int, Path(description="属性模板ID")],
    data: Annotated[ErpAttrUpdateSchema, Body(description="属性模板信息")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """修改属性模板（code 不可改，它是历史物品 attrs JSON 的键名，改了会让旧数据失去解释）。"""
    service = ErpAttrService(auth, db, redis)
    result = await service.update(id=id, data=data)
    return SuccessResponse(data=result, msg="修改属性模板成功")


@ErpAttrAdminRouter.delete("/delete", summary="删除属性模板", response_model=ResponseSchema[None])
async def admin_attr_delete_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpAttrPerm.DELETE]))],
    ids: Annotated[list[int], Body(description="属性模板ID列表")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """批量删除属性模板（软删除）。配错时用删除，不想再收集新值时优先用停用。"""
    service = ErpAttrService(auth, db, redis)
    await service.delete(ids=ids)
    return SuccessResponse(msg="删除属性模板成功")


@ErpAttrAdminRouter.patch("/status/batch", summary="批量修改模板状态", response_model=ResponseSchema[None])
async def admin_attr_status_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpAttrPerm.PATCH]))],
    data: Annotated[BatchSetAvailable, Body(description="状态设置")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """批量启用/停用属性模板。停用后立即从 C端表单与筛选面板消失。"""
    service = ErpAttrService(auth, db, redis)
    await service.set_available(data=data)
    return SuccessResponse(msg="批量修改属性模板状态成功")


# ══════════════════════════ C端：属性集只读 ══════════════════════════


@ErpAttrRouter.get("/schema/{category_id}", summary="分类的有效属性集", response_model=ResponseSchema[list[ErpAttrOutSchema]])
async def client_attr_schema_controller(
    user: CurrentAppUser,
    category_id: Annotated[int, Path(description="分类ID")],
    only_filterable: Annotated[bool, Query(description="只返回可筛选的属性(筛选面板用)")] = False,
) -> JSONResponse:
    """取某分类的有效属性集（含继承），录入表单与筛选面板都由它驱动渲染。

    合并规则：自身模板 > 各级祖先模板 > 全局模板，同一个 code 就近覆盖。
    返回项里 ``inherited=true`` 表示该字段来自祖先分类或全局模板。
    """
    service = ErpAttrService(auth_schema(), user.db, user.redis)
    result = await service.effective_schema(category_id=category_id, only_filterable=only_filterable)
    return SuccessResponse(data=result, msg="查询属性集成功")
