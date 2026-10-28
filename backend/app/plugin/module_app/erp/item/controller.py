"""物品接口 —— C端家庭的物资录入、查询、扫码、图片上传与批次管理，外加后台运营面。

完整路径前缀 ``/api/v1/app``（来自插件目录 ``module_app``），本文件三组路由：

- ``ErpItemRouter``        ``/erp/item/*``        C端，写操作需带 ``X-Family-Id`` 头
- ``ErpItemAdminRouter``   ``/erp/admin/item/*``  后台运营：跨家庭的物品档案增删改查
- ``ErpBatchAdminRouter``  ``/erp/admin/batch/*`` 后台运营：跨家庭的批次增删改查

后台为什么要单独两组前缀，而不是在 C端前缀下加一层 admin
--------------------------------------------------------
后台和 C端是两套互不相通的鉴权体系（``AuthPermission`` 权限标识 vs 家庭上下文 + JWT 域），
把路径写成 ``/erp/item/admin/...`` 会让人误以为它也吃 ``X-Family-Id``，
而且和已有的 ``/erp/admin/family`` 惯例反了。
批次独立成 ``/erp/admin/batch`` 是因为它有自己的权限标识：运营改有效期、
纠正误录状态是日常动作，频率远高于改档案，权限要能单独下放。
另外后台批次最常用的查询是「这段时间到期的所有批次」，跨物品跨家庭，
挂在 ``/erp/admin/item/batch`` 下反而像是必须先知道 item_id 才能查。

为什么读接口用 ``CurrentFamily``、写接口用 ``FamilyWriter``
----------------------------------------------------------
只读成员（viewer）能查不能写，这个差别只在依赖上体现一次：
读接口最小角色是「有效成员」，写接口最小角色是「member」。
service 内部还有第二道按数据行的判定（普通成员只能改自己录的物品），
两处配合而不是合并，是因为路由层拿不到具体那一行数据。

为什么 C端物品接口不挂 ``OperationLogRoute``，后台两组挂
--------------------------------------
那是后台操作日志表（``sys_operation_log``），且会把请求体原文落库。
C端物资数据（药品、母婴用品）不该进后台日志表，所以 C端只靠 service 里的
logger.info 记录关键动作，不做全量落库。
后台两组接口相反：调用者是内部运营人员，每一步都要留痕可追责，所以照常挂。

为什么上传接口不带家庭头
----------------------
图片先传、物品后建是常见顺序（用户还在挑图时物品档案还不存在）。
上传本身不涉及家庭数据，只要求已登录（``CurrentAppUser``），
传回来的 URL 由后续的建档/改档接口写进 ``images``。
"""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, Path, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse
from redis.asyncio.client import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import ResponseSchema, SuccessResponse
from app.core.base_schema import AuthSchema, PageResultSchema, PaginationQueryParam, UploadResponseSchema
from app.core.dependencies import AuthPermission, db_getter, redis_getter
from app.core.router_class import OperationLogRoute
from app.plugin.module_app.login.core.dependencies import CurrentAppUser
from app.utils.upload_util import UploadUtil

from ..core.constants import ErpBatchPerm, ErpItemPerm
from ..core.context import CurrentFamily, FamilyWriter
from .schema import (
    ErpBatchAdminOutSchema,
    ErpBatchAdminQueryParam,
    ErpItemAdminCreateSchema,
    ErpItemAdminOutSchema,
    ErpItemAdminQueryParam,
    ErpItemBatchAddSchema,
    ErpItemBatchOutSchema,
    ErpItemBatchUpdateSchema,
    ErpItemCreateSchema,
    ErpItemOutSchema,
    ErpItemQueryParam,
    ErpItemScanResultSchema,
    ErpItemScanSchema,
    ErpItemUpdateSchema,
)
from .service import ErpItemAdminService, ErpItemService

ErpItemRouter = APIRouter(prefix="/erp/item", tags=["ERP-物品管理"])
ErpItemAdminRouter = APIRouter(route_class=OperationLogRoute, prefix="/erp/admin/item", tags=["ERP-物品管理(后台)"])
ErpBatchAdminRouter = APIRouter(route_class=OperationLogRoute, prefix="/erp/admin/batch", tags=["ERP-物品批次(后台)"])


# ══════════════════════════ 物品档案 ══════════════════════════


@ErpItemRouter.get("/list", summary="物品列表", response_model=ResponseSchema[PageResultSchema[ErpItemOutSchema]])
async def item_list_controller(
    ctx: CurrentFamily,
    page: Annotated[PaginationQueryParam, Depends()],
    search: Annotated[ErpItemQueryParam, Query()],
) -> JSONResponse:
    """分页查询当前家庭的物品（只读成员也能查）。

    列表里带的是库存摘要（批次数、剩余总量、最近到期日），
    批次明细只在详情接口返回，避免列表响应体过大。
    """
    result = await ErpItemService(ctx).page(page_no=page.page_no, page_size=page.page_size, search=search, order_by=page.order_by)
    return SuccessResponse(data=result, msg="查询物品列表成功")


@ErpItemRouter.get("/detail/{id}", summary="物品详情", response_model=ResponseSchema[ErpItemOutSchema])
async def item_detail_controller(
    ctx: CurrentFamily,
    id: Annotated[int, Path(description="物品ID")],
) -> JSONResponse:
    """获取物品详情（含批次明细）。"""
    result = await ErpItemService(ctx).detail(id=id)
    return SuccessResponse(data=result, msg="获取物品详情成功")


@ErpItemRouter.post("/create", status_code=status.HTTP_201_CREATED, summary="录入物品", response_model=ResponseSchema[ErpItemOutSchema])
async def item_create_controller(
    ctx: FamilyWriter,
    data: Annotated[ErpItemCreateSchema, Body(description="物品信息(可带首批批次)")],
) -> JSONResponse:
    """录入一件物品。家庭归属取自 ``X-Family-Id`` 请求头，请求体不接受 family_id。"""
    result = await ErpItemService(ctx).create(data=data)
    return SuccessResponse(data=result, msg="录入物品成功")


@ErpItemRouter.put("/update/{id}", summary="修改物品", response_model=ResponseSchema[ErpItemOutSchema])
async def item_update_controller(
    ctx: FamilyWriter,
    id: Annotated[int, Path(description="物品ID")],
    data: Annotated[ErpItemUpdateSchema, Body(description="物品信息")],
) -> JSONResponse:
    """修改物品档案。普通成员只能改自己录入的，管理员及以上可改全家庭的。"""
    result = await ErpItemService(ctx).update(id=id, data=data)
    return SuccessResponse(data=result, msg="修改物品成功")


@ErpItemRouter.delete("/delete", summary="删除物品", response_model=ResponseSchema[None])
async def item_delete_controller(
    ctx: FamilyWriter,
    ids: Annotated[list[int], Body(description="物品ID列表")],
) -> JSONResponse:
    """批量删除物品（软删除），批次跟随一起删除。"""
    await ErpItemService(ctx).delete(ids=ids)
    return SuccessResponse(msg="删除物品成功")


@ErpItemRouter.post("/scan", summary="扫码查重", response_model=ResponseSchema[ErpItemScanResultSchema])
async def item_scan_controller(
    ctx: CurrentFamily,
    data: Annotated[ErpItemScanSchema, Body(description="商品编码")],
) -> JSONResponse:
    """扫商品编码，在当前家庭内查重。

    用 POST 而不是 GET：扫码是「提交一次业务动作」，不是可缓存的资源读取；
    且让它和后续的建档/新增批次同属写路径，客户端处理更连贯。
    """
    result = await ErpItemService(ctx).scan(data=data)
    return SuccessResponse(data=result, msg="命中已有物品" if result.matched else "未命中，请新建物品")


# ══════════════════════════ 图片上传 ══════════════════════════


@ErpItemRouter.post("/upload", summary="上传物品图片", response_model=ResponseSchema[UploadResponseSchema])
async def item_upload_controller(
    user: CurrentAppUser,
    request: Request,
    file: Annotated[UploadFile, File(description="图片文件")],
) -> JSONResponse:
    """上传物品图片，返回可访问的 URL 供 ``images`` 字段使用。

    复用后台同一套 ``UploadUtil``：文件大小上限、危险扩展名、文件名路径穿越、
    扩展名与内容 MIME 一致性都在那里校验，C端不另开一套校验规则
    （两套规则早晚会分叉，而分叉的那一套往往就是被绕过的那一套）。
    """
    _, _, file_url = await UploadUtil.upload_file(file=file, base_url=str(request.base_url), upload_type="file")
    result = UploadResponseSchema(file_name=file.filename, origin_name=file.filename, file_url=file_url)
    return SuccessResponse(data=result, msg="上传图片成功")


# ══════════════════════════ 批次 ══════════════════════════


@ErpItemRouter.post("/batch/create", status_code=status.HTTP_201_CREATED, summary="新增批次", response_model=ResponseSchema[ErpItemBatchOutSchema])
async def item_batch_create_controller(
    ctx: FamilyWriter,
    data: Annotated[ErpItemBatchAddSchema, Body(description="批次信息")],
) -> JSONResponse:
    """给已有物品新增一个批次（复购入口，扫码命中后走这里）。"""
    result = await ErpItemService(ctx).create_batch(data=data)
    return SuccessResponse(data=result, msg="新增批次成功")


@ErpItemRouter.put("/batch/update/{id}", summary="修改批次", response_model=ResponseSchema[ErpItemBatchOutSchema])
async def item_batch_update_controller(
    ctx: FamilyWriter,
    id: Annotated[int, Path(description="批次ID")],
    data: Annotated[ErpItemBatchUpdateSchema, Body(description="批次信息")],
) -> JSONResponse:
    """修改批次（剩余量、有效期、状态等）。流转到「已丢弃」这类状态也走这里。"""
    result = await ErpItemService(ctx).update_batch(id=id, data=data)
    return SuccessResponse(data=result, msg="修改批次成功")


@ErpItemRouter.delete("/batch/delete/{id}", summary="删除批次", response_model=ResponseSchema[None])
async def item_batch_delete_controller(
    ctx: FamilyWriter,
    id: Annotated[int, Path(description="批次ID")],
) -> JSONResponse:
    """删除批次（软删除）。录错数量/有效期时用它比改状态干净。"""
    await ErpItemService(ctx).delete_batch(id=id)
    return SuccessResponse(msg="删除批次成功")


# ══════════════════════════ 后台：物品档案 ══════════════════════════


@ErpItemAdminRouter.get("/list", summary="分页查询物品", response_model=ResponseSchema[PageResultSchema[ErpItemAdminOutSchema]])
async def admin_item_list_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpItemPerm.QUERY]))],
    page: Annotated[PaginationQueryParam, Depends()],
    search: Annotated[ErpItemAdminQueryParam, Query()],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """后台分页查询全平台物品，可用 ``family_id`` 收敛到某个家庭。

    与 C端列表的差别只在裁剪：这里跨家庭、且不按成员可见性过滤，
    所以每条都会回 ``family_name``，否则一堆 ID 分不清是谁家的。
    """
    service = ErpItemAdminService(auth, db, redis)
    result = await service.page(page_no=page.page_no, page_size=page.page_size, search=search, order_by=page.order_by)
    return SuccessResponse(data=result, msg="查询物品列表成功")


@ErpItemAdminRouter.get("/detail/{id}", summary="获取物品详情", response_model=ResponseSchema[ErpItemAdminOutSchema])
async def admin_item_detail_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpItemPerm.DETAIL]))],
    id: Annotated[int, Path(description="物品ID")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """后台获取物品详情（含批次明细）。"""
    service = ErpItemAdminService(auth, db, redis)
    result = await service.detail(id=id)
    return SuccessResponse(data=result, msg="获取物品详情成功")


@ErpItemAdminRouter.post("/create", status_code=status.HTTP_201_CREATED, summary="录入物品", response_model=ResponseSchema[ErpItemAdminOutSchema])
async def admin_item_create_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpItemPerm.CREATE]))],
    data: Annotated[ErpItemAdminCreateSchema, Body(description="物品信息(必填 family_id 与 owner_user_id，可带首批批次)")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """后台代用户录入物品。

    这里必须显式传 ``family_id`` 和 ``owner_user_id``：后台操作者不是家庭成员，
    没有 ``X-Family-Id`` 也没有「当前用户」可以兜底。
    """
    service = ErpItemAdminService(auth, db, redis)
    result = await service.create(data=data)
    return SuccessResponse(data=result, msg="录入物品成功")


@ErpItemAdminRouter.put("/update/{id}", summary="修改物品", response_model=ResponseSchema[ErpItemAdminOutSchema])
async def admin_item_update_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpItemPerm.UPDATE]))],
    id: Annotated[int, Path(description="物品ID")],
    data: Annotated[ErpItemUpdateSchema, Body(description="物品信息")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """修改物品档案（批次改动走批次接口，归属家庭不可改）。"""
    service = ErpItemAdminService(auth, db, redis)
    result = await service.update(id=id, data=data)
    return SuccessResponse(data=result, msg="修改物品成功")


@ErpItemAdminRouter.delete("/delete", summary="删除物品", response_model=ResponseSchema[None])
async def admin_item_delete_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpItemPerm.DELETE]))],
    ids: Annotated[list[int], Body(description="物品ID列表")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """批量删除物品（软删除），批次跟随一起删除。"""
    service = ErpItemAdminService(auth, db, redis)
    await service.delete(ids=ids)
    return SuccessResponse(msg="删除物品成功")


# ══════════════════════════ 后台：物品批次 ══════════════════════════


@ErpBatchAdminRouter.get("/list", summary="分页查询批次", response_model=ResponseSchema[PageResultSchema[ErpBatchAdminOutSchema]])
async def admin_batch_list_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpBatchPerm.QUERY]))],
    page: Annotated[PaginationQueryParam, Depends()],
    search: Annotated[ErpBatchAdminQueryParam, Query()],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """后台分页查询全平台批次。

    可按 ``family_id`` / ``item_id`` / ``status`` 过滤，
    ``expiry_date`` 传两个日期就是「这段时间到期的批次」，
    这也是 P3 过期提醒上线前运营手工核对库存的唯一入口。
    """
    service = ErpItemAdminService(auth, db, redis)
    result = await service.batch_page(page_no=page.page_no, page_size=page.page_size, search=search, order_by=page.order_by)
    return SuccessResponse(data=result, msg="查询批次列表成功")


@ErpBatchAdminRouter.post("/create", status_code=status.HTTP_201_CREATED, summary="新增批次", response_model=ResponseSchema[ErpBatchAdminOutSchema])
async def admin_batch_create_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpBatchPerm.CREATE]))],
    data: Annotated[ErpItemBatchAddSchema, Body(description="批次信息(带 item_id)")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """给已有物品新增批次。家庭归属由所属物品推导，请求体不接受 ``family_id``。"""
    service = ErpItemAdminService(auth, db, redis)
    result = await service.batch_create(data=data)
    return SuccessResponse(data=result, msg="新增批次成功")


@ErpBatchAdminRouter.put("/update/{id}", summary="修改批次", response_model=ResponseSchema[ErpBatchAdminOutSchema])
async def admin_batch_update_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpBatchPerm.UPDATE]))],
    id: Annotated[int, Path(description="批次ID")],
    data: Annotated[ErpItemBatchUpdateSchema, Body(description="批次信息")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """修改批次（剩余量、有效期、状态等）。纠正误录状态就走这里。"""
    service = ErpItemAdminService(auth, db, redis)
    result = await service.batch_update(id=id, data=data)
    return SuccessResponse(data=result, msg="修改批次成功")


@ErpBatchAdminRouter.delete("/delete", summary="删除批次", response_model=ResponseSchema[None])
async def admin_batch_delete_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpBatchPerm.DELETE]))],
    ids: Annotated[list[int], Body(description="批次ID列表")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """批量删除批次（软删除）。只删批次不动档案，用户录重一次进货时用它。"""
    service = ErpItemAdminService(auth, db, redis)
    await service.batch_delete(ids=ids)
    return SuccessResponse(msg="删除批次成功")
