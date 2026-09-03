import urllib.parse
from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, Path, Query, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import ResponseSchema, StreamResponse, SuccessResponse
from app.core.base_schema import AuthSchema, BatchSetAvailable, PageResultSchema, PaginationQueryParam
from app.core.dependencies import AuthPermission, db_getter
from app.core.router_class import OperationLogRoute
from app.utils.common_util import bytes2file_response

from .schema import ErpCreateSchema, ErpOutSchema, ErpQueryParam, ErpUpdateSchema
from .service import ErpService

ErpRouter = APIRouter(route_class=OperationLogRoute, prefix="/inv", tags=["家庭ERP"])


@ErpRouter.get("/detail/{id}", summary="获取示例详情", response_model=ResponseSchema[ErpOutSchema])
async def get_obj_detail_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_erp:detail"]))],
    id: Annotated[int, Path(description="示例ID")],
    db: Annotated[AsyncSession, Depends(db_getter)],
) -> JSONResponse:
    service = ErpService(auth, db)
    result_dict = await service.detail(id=id)
    return SuccessResponse(data=result_dict, msg="获取示例详情成功")


@ErpRouter.get("/list", summary="分页查询示例", response_model=ResponseSchema[PageResultSchema[ErpOutSchema]])
async def get_obj_list_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_erp:query"]))],
    page: Annotated[PaginationQueryParam, Depends()],
    search: Annotated[ErpQueryParam, Query()],
    db: Annotated[AsyncSession, Depends(db_getter)],
) -> JSONResponse:
    service = ErpService(auth, db)
    result_dict = await service.page(
        page_no=page.page_no,
        page_size=page.page_size,
        search=search,
        order_by=page.order_by,
    )
    return SuccessResponse(data=result_dict, msg="查询示例列表成功")


@ErpRouter.post("/create", status_code=status.HTTP_201_CREATED, summary="创建示例", response_model=ResponseSchema[ErpOutSchema])
async def create_obj_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_erp:create"]))],
    data: Annotated[ErpCreateSchema, Body(description="创建参数")],
    db: Annotated[AsyncSession, Depends(db_getter)],
) -> JSONResponse:
    service = ErpService(auth, db)
    result_dict = await service.create(data=data)
    return SuccessResponse(data=result_dict, msg="创建示例成功")


@ErpRouter.put("/update/{id}", summary="修改示例", response_model=ResponseSchema[ErpOutSchema])
async def update_obj_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_erp:update"]))],
    id: Annotated[int, Path(description="示例ID")],
    data: Annotated[ErpUpdateSchema, Body(description="修改参数")],
    db: Annotated[AsyncSession, Depends(db_getter)],
) -> JSONResponse:
    service = ErpService(auth, db)
    result_dict = await service.update(id=id, data=data)
    return SuccessResponse(data=result_dict, msg="修改示例成功")


@ErpRouter.delete("/delete", summary="删除示例", response_model=ResponseSchema[None])
async def delete_obj_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_erp:delete"]))],
    ids: Annotated[list[int], Body(description="ID列表")],
    db: Annotated[AsyncSession, Depends(db_getter)],
) -> JSONResponse:
    service = ErpService(auth, db)
    await service.delete(ids=ids)
    return SuccessResponse(msg="删除示例成功")


@ErpRouter.patch("/status/batch", summary="批量修改示例状态", response_model=ResponseSchema[None])
async def batch_set_available_obj_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_erp:patch"]))],
    data: Annotated[BatchSetAvailable, Body(description="状态设置")],
    db: Annotated[AsyncSession, Depends(db_getter)],
) -> JSONResponse:
    service = ErpService(auth, db)
    await service.set_available(data=data)
    return SuccessResponse(msg="批量修改示例状态成功")


@ErpRouter.post("/export", summary="导出示例")
async def export_obj_list_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_erp:export"]))],
    search: Annotated[ErpQueryParam, Query()],
    db: Annotated[AsyncSession, Depends(db_getter)],
) -> StreamingResponse:
    service = ErpService(auth, db)
    result_dict_list = await service.get_list(search=search)
    export_result = ErpService.batch_export(obj_list=[item.model_dump() for item in result_dict_list])

    return StreamResponse(
        data=bytes2file_response(export_result),
        Erp_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Erp.xlsx"},
    )


@ErpRouter.post("/import", summary="导入示例", response_model=ResponseSchema[str])
async def import_obj_list_controller(
    file: Annotated[UploadFile, File(description="导入文件")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_erp:import"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
) -> JSONResponse:
    service = ErpService(auth, db)
    batch_import_result = await service.batch_import(file=file, update_support=True)
    return SuccessResponse(data=batch_import_result, msg="导入示例成功")


@ErpRouter.post("/download/template", summary="获取示例导入模板", dependencies=[Depends(AuthPermission(["module_erp:download"]))])
async def export_obj_template_controller() -> StreamingResponse:
    import_template_result = ErpService.import_template_download()

    return StreamResponse(
        data=bytes2file_response(import_template_result),
        Erp_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={urllib.parse.quote('示例导入模板.xlsx')}",
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
