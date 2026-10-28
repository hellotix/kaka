"""物品分类接口 —— 后台维护三级分类树，C端只读。

完整路径前缀 ``/api/v1/app``（来自插件目录 ``module_app``），本文件两组路由：

- ``ErpCategoryAdminRouter``  ``/erp/admin/category/*``  后台运营接口，走 ``AuthPermission`` 权限标识
- ``ErpCategoryRouter``       ``/erp/category/*``        C端只读，仅需登录

为什么 C端分类接口不挂 ``X-Family-Id``
--------------------------------------
分类是运营统一维护的全局配置（不区分家庭），C端拿它渲染录入表单的分类选择器。
挂上家庭头反而会让人误以为「换个家庭分类会不一样」。真正按家庭隔离的是物品数据，
那些接口在 P1 的 item 板块里，必须带家庭头。
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

from ..core.constants import ErpCategoryPerm
from ..core.context import auth_schema
from .schema import (
    ErpCategoryCreateSchema,
    ErpCategoryOutSchema,
    ErpCategoryQueryParam,
    ErpCategoryTreeSchema,
    ErpCategoryUpdateSchema,
)
from .service import ErpCategoryService

# C端只读接口不挂 OperationLogRoute：那是后台操作日志，分类树查询是高频只读请求，
# 逐条落库只会把日志表撑爆。
ErpCategoryAdminRouter = APIRouter(route_class=OperationLogRoute, prefix="/erp/admin/category", tags=["ERP-分类管理(后台)"])
ErpCategoryRouter = APIRouter(prefix="/erp/category", tags=["ERP-分类查询"])


# ══════════════════════════ 后台：分类运营 ══════════════════════════


@ErpCategoryAdminRouter.get("/list", summary="分页查询分类", response_model=ResponseSchema[PageResultSchema[ErpCategoryOutSchema]])
async def admin_category_list_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpCategoryPerm.QUERY]))],
    page: Annotated[PaginationQueryParam, Depends()],
    search: Annotated[ErpCategoryQueryParam, Query()],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """后台分页查询分类（平铺结果，配合树形表格组件自行组装）。"""
    service = ErpCategoryService(auth, db, redis)
    result = await service.page(page_no=page.page_no, page_size=page.page_size, search=search, order_by=page.order_by)
    return SuccessResponse(data=result, msg="查询分类列表成功")


# 注意：/tree 必须注册在 /detail/{id} 之前，否则 tree 会被当成 id 捕获后 int 解析失败返回 422
@ErpCategoryAdminRouter.get("/tree", summary="分类树(后台视角)", response_model=ResponseSchema[list[ErpCategoryTreeSchema]])
async def admin_category_tree_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpCategoryPerm.QUERY]))],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """后台分类树，返回全量（含停用、不可见、以及父级已删的孤儿节点，便于发现脏数据）。"""
    service = ErpCategoryService(auth, db, redis)
    result = await service.tree(client_view=False)
    return SuccessResponse(data=result, msg="查询分类树成功")


@ErpCategoryAdminRouter.get("/detail/{id}", summary="获取分类详情", response_model=ResponseSchema[ErpCategoryOutSchema])
async def admin_category_detail_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpCategoryPerm.DETAIL]))],
    id: Annotated[int, Path(description="分类ID")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """后台获取分类详情。"""
    service = ErpCategoryService(auth, db, redis)
    result = await service.detail(id=id)
    return SuccessResponse(data=result, msg="获取分类详情成功")


@ErpCategoryAdminRouter.post("/create", status_code=status.HTTP_201_CREATED, summary="新增分类", response_model=ResponseSchema[ErpCategoryOutSchema])
async def admin_category_create_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpCategoryPerm.CREATE]))],
    data: Annotated[ErpCategoryCreateSchema, Body(description="分类信息")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """新增分类。层级由父分类推导，超过三级会被拒绝。"""
    service = ErpCategoryService(auth, db, redis)
    result = await service.create(data=data)
    return SuccessResponse(data=result, msg="新增分类成功")


@ErpCategoryAdminRouter.put("/update/{id}", summary="修改分类", response_model=ResponseSchema[ErpCategoryOutSchema])
async def admin_category_update_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpCategoryPerm.UPDATE]))],
    id: Annotated[int, Path(description="分类ID")],
    data: Annotated[ErpCategoryUpdateSchema, Body(description="分类信息")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """修改分类（不支持改父分类，移动会级联改写整棵子树的层级与路径，风险过高）。"""
    service = ErpCategoryService(auth, db, redis)
    result = await service.update(id=id, data=data)
    return SuccessResponse(data=result, msg="修改分类成功")


@ErpCategoryAdminRouter.delete("/delete", summary="删除分类", response_model=ResponseSchema[None])
async def admin_category_delete_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpCategoryPerm.DELETE]))],
    ids: Annotated[list[int], Body(description="分类ID列表")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """批量删除分类（软删除）。有子分类或挂着扩展属性模板时会被拒绝。"""
    service = ErpCategoryService(auth, db, redis)
    await service.delete(ids=ids)
    return SuccessResponse(msg="删除分类成功")


@ErpCategoryAdminRouter.patch("/status/batch", summary="批量修改分类状态", response_model=ResponseSchema[None])
async def admin_category_status_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpCategoryPerm.PATCH]))],
    data: Annotated[BatchSetAvailable, Body(description="状态设置")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """批量启用/停用分类。停用后 C端不再可选，已挂在上面的物品数据不受影响。"""
    service = ErpCategoryService(auth, db, redis)
    await service.set_available(data=data)
    return SuccessResponse(msg="批量修改分类状态成功")


# ══════════════════════════ C端：分类只读 ══════════════════════════


@ErpCategoryRouter.get("/tree", summary="分类树(C端)", response_model=ResponseSchema[list[ErpCategoryTreeSchema]])
async def client_category_tree_controller(user: CurrentAppUser) -> JSONResponse:
    """C端分类树，只含「启用 + 可见」的分类。

    隐藏一个分类会连带隐藏它的整棵子树，所以不会出现「父级看不见但子级冒出来」的悬空节点。
    """
    service = ErpCategoryService(auth_schema(), user.db, user.redis)
    result = await service.tree(client_view=True)
    return SuccessResponse(data=result, msg="查询分类成功")


@ErpCategoryRouter.get("/detail/{id}", summary="分类详情(C端)", response_model=ResponseSchema[ErpCategoryOutSchema])
async def client_category_detail_controller(
    user: CurrentAppUser,
    id: Annotated[int, Path(description="分类ID")],
) -> JSONResponse:
    """C端获取单个分类详情（回显物品所属分类名时用）。"""
    service = ErpCategoryService(auth_schema(), user.db, user.redis)
    result = await service.detail(id=id)
    return SuccessResponse(data=result, msg="获取分类详情成功")
