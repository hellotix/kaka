"""家庭接口 —— C端门户、C端家庭内操作、后台运营管理。

完整路径前缀 ``/api/v1/app``（来自插件目录 ``module_app``），本文件三组路由：

- ``ErpFamilyPortalRouter``  ``/erp/family/*``       C端跨家庭操作（创建、我的家庭、加入、邀请处理、退出）
- ``ErpFamilyRouter``        ``/erp/family/*``       C端家庭内操作，需带 ``X-Family-Id`` 头
- ``ErpFamilyAdminRouter``   ``/erp/admin/family/*`` 后台运营接口，走 ``AuthPermission`` 权限标识

为什么门户和家庭内共用 ``/erp/family`` 前缀
--------------------------------------------
它们操作的是同一类资源，拆成 ``/erp/family-portal`` 这种前缀只会让路径变长且语义重复。
区分靠具体子路径：门户的都是「我自己」视角（create/my/join/quit），
家庭内的都在 ``info`` / ``member`` / ``grant`` / ``dissolve`` 这些子资源下。

路由注册顺序
------------
``PUT /member/my-nickname`` 必须注册在 ``PUT /member/{id}`` 之前。FastAPI 按注册顺序
首次匹配，``my-nickname`` 会被 ``{id}`` 当成路径参数捕获，然后 int 解析失败返回 422。
``check_route_conflicts`` 检测不出这种冲突（它只比对完全相同的路径模式）。
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

from ..core.constants import ErpFamilyPerm
from ..core.context import CurrentFamily, FamilyAdmin, FamilyOwner
from .schema import (
    ErpFamilyAdminUpdateSchema,
    ErpFamilyBriefSchema,
    ErpFamilyCreateSchema,
    ErpFamilyOutSchema,
    ErpFamilyQueryParam,
    ErpFamilyUpdateSchema,
    ErpGrantAdminCreateSchema,
    ErpGrantCreateSchema,
    ErpGrantOutSchema,
    ErpGrantQueryParam,
    ErpMemberHandleSchema,
    ErpMemberInviteSchema,
    ErpMemberJoinSchema,
    ErpMemberOutSchema,
    ErpMemberQueryParam,
    ErpMemberSelfUpdateSchema,
    ErpMemberUpdateSchema,
)
from .service import ErpFamilyAdminService, ErpFamilyPortalService, ErpFamilyService

# C端门户与家庭内操作都不挂 OperationLogRoute：那是后台操作日志，
# 且它会把请求体原文落库，C端数据（家庭成员关系）不应进后台日志表。
ErpFamilyPortalRouter = APIRouter(prefix="/erp/family", tags=["ERP-我的家庭"])
ErpFamilyRouter = APIRouter(prefix="/erp/family", tags=["ERP-家庭管理"])
ErpFamilyAdminRouter = APIRouter(route_class=OperationLogRoute, prefix="/erp/admin/family", tags=["ERP-家庭管理(后台)"])


# ══════════════════════════ C端：跨家庭操作 ══════════════════════════


@ErpFamilyPortalRouter.post("/create", status_code=status.HTTP_201_CREATED, summary="创建家庭", response_model=ResponseSchema[ErpFamilyOutSchema])
async def create_family_controller(
    user: CurrentAppUser,
    data: Annotated[ErpFamilyCreateSchema, Body(description="家庭信息")],
) -> JSONResponse:
    """创建家庭，创建者自动成为户主。"""
    result = await ErpFamilyPortalService(user).create(data=data)
    return SuccessResponse(data=result, msg="创建家庭成功")


@ErpFamilyPortalRouter.get("/my", summary="我的家庭列表", response_model=ResponseSchema[list[ErpFamilyBriefSchema]])
async def my_families_controller(user: CurrentAppUser) -> JSONResponse:
    """获取我已加入的全部家庭（App 顶部家庭切换器数据源）。"""
    result = await ErpFamilyPortalService(user).my_families()
    return SuccessResponse(data=result, msg="查询我的家庭成功")


@ErpFamilyPortalRouter.get("/pending-invite", summary="待我确认的邀请", response_model=ResponseSchema[list[ErpMemberOutSchema]])
async def pending_invites_controller(user: CurrentAppUser) -> JSONResponse:
    """获取定向邀请中待我处理的记录。"""
    result = await ErpFamilyPortalService(user).pending_invites()
    return SuccessResponse(data=result, msg="查询待确认邀请成功")


@ErpFamilyPortalRouter.post("/join", summary="凭邀请码加入家庭", response_model=ResponseSchema[ErpFamilyBriefSchema])
async def join_family_controller(
    user: CurrentAppUser,
    data: Annotated[ErpMemberJoinSchema, Body(description="邀请码")],
) -> JSONResponse:
    """输入或扫描家庭邀请码直接加入（加入即生效）。"""
    result = await ErpFamilyPortalService(user).join(data=data)
    return SuccessResponse(data=result, msg="加入家庭成功")


@ErpFamilyPortalRouter.put("/invite/{member_id}", summary="处理家庭邀请", response_model=ResponseSchema[None])
async def handle_invite_controller(
    user: CurrentAppUser,
    member_id: Annotated[int, Path(description="成员记录ID(来自待确认邀请列表)")],
    data: Annotated[ErpMemberHandleSchema, Body(description="接受或拒绝")],
) -> JSONResponse:
    """接受或拒绝定向邀请，只能处理属于自己的邀请。"""
    await ErpFamilyPortalService(user).handle_invite(member_id=member_id, data=data)
    return SuccessResponse(msg="已接受邀请" if data.accept else "已拒绝邀请")


@ErpFamilyPortalRouter.delete("/quit/{family_id}", summary="退出家庭", response_model=ResponseSchema[None])
async def quit_family_controller(
    user: CurrentAppUser,
    family_id: Annotated[int, Path(description="家庭ID")],
) -> JSONResponse:
    """退出指定家庭。户主需先转让户主或解散家庭。"""
    await ErpFamilyPortalService(user).quit(family_id=family_id)
    return SuccessResponse(msg="已退出家庭")


# ══════════════════════════ C端：家庭内操作 ══════════════════════════
# 以下接口都要求请求头 X-Family-Id，由 FamilyContext 依赖完成成员关系与角色校验。


@ErpFamilyRouter.get("/info", summary="获取当前家庭信息", response_model=ResponseSchema[ErpFamilyOutSchema])
async def family_info_controller(family: CurrentFamily) -> JSONResponse:
    """获取 ``X-Family-Id`` 指定家庭的详情（含我的角色与成员数）。"""
    result = await ErpFamilyService(family).detail()
    return SuccessResponse(data=result, msg="获取家庭信息成功")


@ErpFamilyRouter.put("/info", summary="修改当前家庭信息", response_model=ResponseSchema[ErpFamilyOutSchema])
async def update_family_controller(
    family: FamilyAdmin,
    data: Annotated[ErpFamilyUpdateSchema, Body(description="家庭信息")],
) -> JSONResponse:
    """修改家庭名称/头像/备注（管理员及以上）。"""
    result = await ErpFamilyService(family).update(data=data)
    return SuccessResponse(data=result, msg="修改家庭信息成功")


@ErpFamilyRouter.post("/invite-code/refresh", summary="重置家庭邀请码", response_model=ResponseSchema[str])
async def refresh_invite_code_controller(family: FamilyAdmin) -> JSONResponse:
    """重新生成邀请码，旧码立即失效（管理员及以上）。"""
    code = await ErpFamilyService(family).refresh_invite_code()
    return SuccessResponse(data=code, msg="邀请码已重置")


@ErpFamilyRouter.delete("/dissolve", summary="解散家庭", response_model=ResponseSchema[None])
async def dissolve_family_controller(family: FamilyOwner) -> JSONResponse:
    """解散家庭并撤销全部共享授权（仅户主）。"""
    await ErpFamilyService(family).dissolve()
    return SuccessResponse(msg="家庭已解散")


# ── 成员 ──────────────────────────────────────────────────────────


@ErpFamilyRouter.get("/member/list", summary="家庭成员列表", response_model=ResponseSchema[list[ErpMemberOutSchema]])
async def family_member_list_controller(
    family: CurrentFamily,
    member_status: Annotated[int | None, Query(description="按状态过滤(0:待确认 1:已加入 2:已拒绝 3:已移除)，不传默认只看已加入")] = None,
) -> JSONResponse:
    """列出当前家庭的成员。"""
    result = await ErpFamilyService(family).member_list(status=member_status)
    return SuccessResponse(data=result, msg="查询家庭成员成功")


@ErpFamilyRouter.post("/member/invite", status_code=status.HTTP_201_CREATED, summary="邀请成员", response_model=ResponseSchema[ErpMemberOutSchema])
async def invite_member_controller(
    family: FamilyAdmin,
    data: Annotated[ErpMemberInviteSchema, Body(description="被邀请人(用户ID或手机号)与角色")],
) -> JSONResponse:
    """定向邀请成员，生成待确认记录等对方接受（管理员及以上）。"""
    result = await ErpFamilyService(family).invite(data=data)
    return SuccessResponse(data=result, msg="邀请已发出")


# 注意：本路由必须注册在 /member/{member_id} 之前，否则 my-nickname 会被当成 member_id
@ErpFamilyRouter.put("/member/my-nickname", summary="修改我的家庭内称呼", response_model=ResponseSchema[ErpMemberOutSchema])
async def update_my_nickname_controller(
    family: CurrentFamily,
    data: Annotated[ErpMemberSelfUpdateSchema, Body(description="家庭内称呼")],
) -> JSONResponse:
    """修改自己在当前家庭里的称呼（如「妈妈」）。"""
    result = await ErpFamilyService(family).update_my_nickname(data=data)
    return SuccessResponse(data=result, msg="修改称呼成功")


@ErpFamilyRouter.put("/member/{member_id}", summary="修改成员角色或称呼", response_model=ResponseSchema[ErpMemberOutSchema])
async def update_member_controller(
    family: FamilyAdmin,
    member_id: Annotated[int, Path(description="成员记录ID")],
    data: Annotated[ErpMemberUpdateSchema, Body(description="角色或称呼")],
) -> JSONResponse:
    """修改成员角色（仅户主）或家庭内称呼（管理员及以上）。"""
    result = await ErpFamilyService(family).update_member(member_id=member_id, data=data)
    return SuccessResponse(data=result, msg="修改成员信息成功")


@ErpFamilyRouter.delete("/member/{member_id}", summary="移除成员", response_model=ResponseSchema[None])
async def remove_member_controller(
    family: FamilyAdmin,
    member_id: Annotated[int, Path(description="成员记录ID")],
) -> JSONResponse:
    """移除成员（不能移除户主，也不能移除同级或更高级别的成员）。"""
    await ErpFamilyService(family).remove_member(member_id=member_id)
    return SuccessResponse(msg="已移除该成员")


@ErpFamilyRouter.post("/member/transfer/{user_id}", summary="转让户主", response_model=ResponseSchema[None])
async def transfer_owner_controller(
    family: FamilyOwner,
    user_id: Annotated[int, Path(description="接任户主的C端用户ID")],
) -> JSONResponse:
    """把户主转让给家庭内的有效成员，原户主降级为管理员（仅户主）。"""
    await ErpFamilyService(family).transfer_owner(user_id=user_id)
    return SuccessResponse(msg="户主已转让")


# ── 共享授权 ──────────────────────────────────────────────────────


@ErpFamilyRouter.get("/grant/list", summary="共享授权列表", response_model=ResponseSchema[list[ErpGrantOutSchema]])
async def grant_list_controller(family: CurrentFamily) -> JSONResponse:
    """列出与当前家庭相关的全部共享授权（我授出的 + 授给我的）。"""
    result = await ErpFamilyService(family).grant_list()
    return SuccessResponse(data=result, msg="查询共享授权成功")


@ErpFamilyRouter.post("/grant", status_code=status.HTTP_201_CREATED, summary="授权其他家庭查看", response_model=ResponseSchema[ErpGrantOutSchema])
async def create_grant_controller(
    family: FamilyOwner,
    data: Annotated[ErpGrantCreateSchema, Body(description="被授权家庭与到期时间")],
) -> JSONResponse:
    """把当前家庭的物资数据只读开放给另一个家庭（仅户主）。"""
    result = await ErpFamilyService(family).create_grant(data=data)
    return SuccessResponse(data=result, msg="授权成功")


@ErpFamilyRouter.delete("/grant/{grant_id}", summary="撤销共享授权", response_model=ResponseSchema[None])
async def revoke_grant_controller(
    family: FamilyOwner,
    grant_id: Annotated[int, Path(description="授权记录ID")],
) -> JSONResponse:
    """撤销户主自助授权。后台强制授权不可自行撤销（仅户主）。"""
    await ErpFamilyService(family).revoke_grant(grant_id=grant_id)
    return SuccessResponse(msg="已撤销授权")


@ErpFamilyRouter.get("/grant/visible-family", summary="可查看数据的家庭ID", response_model=ResponseSchema[list[int]])
async def visible_family_controller(family: CurrentFamily) -> JSONResponse:
    """返回当前家庭可查看数据的家庭ID集合（自身 + 被授权的）。

    前端可用它做「查看全部 / 仅看我家」的切换，后端 P1 起的物品查询也走同一套逻辑。
    """
    result = await ErpFamilyService(family).visible_family_ids()
    return SuccessResponse(data=result, msg="查询可见家庭成功")


# ══════════════════════════ 后台：家庭运营 ══════════════════════════


@ErpFamilyAdminRouter.get("/list", summary="分页查询家庭", response_model=ResponseSchema[PageResultSchema[ErpFamilyOutSchema]])
async def admin_family_list_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpFamilyPerm.QUERY]))],
    page: Annotated[PaginationQueryParam, Depends()],
    search: Annotated[ErpFamilyQueryParam, Query()],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """后台分页查询家庭列表。"""
    service = ErpFamilyAdminService(auth, db, redis)
    result = await service.page(page_no=page.page_no, page_size=page.page_size, search=search, order_by=page.order_by)
    return SuccessResponse(data=result, msg="查询家庭列表成功")


@ErpFamilyAdminRouter.get("/detail/{id}", summary="获取家庭详情", response_model=ResponseSchema[ErpFamilyOutSchema])
async def admin_family_detail_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpFamilyPerm.DETAIL]))],
    id: Annotated[int, Path(description="家庭ID")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """后台获取家庭详情。"""
    service = ErpFamilyAdminService(auth, db, redis)
    result = await service.detail(id=id)
    return SuccessResponse(data=result, msg="获取家庭详情成功")


@ErpFamilyAdminRouter.put("/update/{id}", summary="修改家庭", response_model=ResponseSchema[ErpFamilyOutSchema])
async def admin_family_update_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpFamilyPerm.UPDATE]))],
    id: Annotated[int, Path(description="家庭ID")],
    data: Annotated[ErpFamilyAdminUpdateSchema, Body(description="家庭信息")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """后台修改家庭资料、成员上限或状态。"""
    service = ErpFamilyAdminService(auth, db, redis)
    result = await service.update(id=id, data=data)
    return SuccessResponse(data=result, msg="修改家庭成功")


@ErpFamilyAdminRouter.delete("/delete", summary="删除家庭", response_model=ResponseSchema[None])
async def admin_family_delete_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpFamilyPerm.DELETE]))],
    ids: Annotated[list[int], Body(description="家庭ID列表")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """后台批量删除家庭（软删除），同时清理成员与共享授权。"""
    service = ErpFamilyAdminService(auth, db, redis)
    await service.delete(ids=ids)
    return SuccessResponse(msg="删除家庭成功")


@ErpFamilyAdminRouter.patch("/status/batch", summary="批量修改家庭状态", response_model=ResponseSchema[None])
async def admin_family_status_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpFamilyPerm.PATCH]))],
    data: Annotated[BatchSetAvailable, Body(description="状态设置")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """批量启用/停用家庭。停用后其成员无法再通过 X-Family-Id 访问数据。"""
    service = ErpFamilyAdminService(auth, db, redis)
    await service.set_available(data=data)
    return SuccessResponse(msg="批量修改家庭状态成功")


@ErpFamilyAdminRouter.get("/member/list", summary="分页查询家庭成员", response_model=ResponseSchema[PageResultSchema[ErpMemberOutSchema]])
async def admin_member_list_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpFamilyPerm.MEMBER]))],
    page: Annotated[PaginationQueryParam, Depends()],
    search: Annotated[ErpMemberQueryParam, Query()],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """后台分页查询家庭成员（可跨家庭）。"""
    service = ErpFamilyAdminService(auth, db, redis)
    result = await service.member_page(page_no=page.page_no, page_size=page.page_size, search=search, order_by=page.order_by)
    return SuccessResponse(data=result, msg="查询家庭成员成功")


@ErpFamilyAdminRouter.delete("/member/{id}", summary="移除家庭成员", response_model=ResponseSchema[None])
async def admin_member_remove_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpFamilyPerm.MEMBER]))],
    id: Annotated[int, Path(description="成员记录ID")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """后台移除家庭成员（户主不可移除）。"""
    service = ErpFamilyAdminService(auth, db, redis)
    await service.remove_member(id=id)
    return SuccessResponse(msg="移除成员成功")


@ErpFamilyAdminRouter.get("/grant/list", summary="分页查询共享授权", response_model=ResponseSchema[PageResultSchema[ErpGrantOutSchema]])
async def admin_grant_list_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpFamilyPerm.GRANT_QUERY]))],
    page: Annotated[PaginationQueryParam, Depends()],
    search: Annotated[ErpGrantQueryParam, Query()],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """后台分页查询家庭间共享授权。"""
    service = ErpFamilyAdminService(auth, db, redis)
    result = await service.grant_page(page_no=page.page_no, page_size=page.page_size, search=search, order_by=page.order_by)
    return SuccessResponse(data=result, msg="查询共享授权成功")


@ErpFamilyAdminRouter.post("/grant", status_code=status.HTTP_201_CREATED, summary="强制授权共享", response_model=ResponseSchema[ErpGrantOutSchema])
async def admin_force_grant_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpFamilyPerm.GRANT_CREATE]))],
    data: Annotated[ErpGrantAdminCreateSchema, Body(description="强制授权参数(必须带到期时间)")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """后台强制把一个家庭的数据授权给另一个家庭，户主不可自行撤销。"""
    service = ErpFamilyAdminService(auth, db, redis)
    result = await service.force_grant(data=data)
    return SuccessResponse(data=result, msg="强制授权成功")


@ErpFamilyAdminRouter.delete("/grant/{id}", summary="撤销共享授权", response_model=ResponseSchema[None])
async def admin_revoke_grant_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission([ErpFamilyPerm.GRANT_REVOKE]))],
    id: Annotated[int, Path(description="授权记录ID")],
    db: Annotated[AsyncSession, Depends(db_getter, scope="function")],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    """后台撤销任意来源的共享授权。"""
    service = ErpFamilyAdminService(auth, db, redis)
    await service.revoke_grant(id=id)
    return SuccessResponse(msg="已撤销授权")
