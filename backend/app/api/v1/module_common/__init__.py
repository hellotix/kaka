from fastapi import APIRouter

from .file.controller import FileRouter
from .health import HealthRouter
from .sse import common_sse_router

common_router = APIRouter(prefix="/common")

common_router.include_router(FileRouter)
common_router.include_router(HealthRouter)
common_router.include_router(common_sse_router)
