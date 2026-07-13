from fastapi import APIRouter

from .controller import SSERouter

__all__ = ["SSERouter"]

common_sse_router = APIRouter(prefix="/sse")
common_sse_router.include_router(SSERouter)
