from __future__ import annotations

import json
import secrets
from datetime import datetime
from typing import Any

from redis.asyncio.client import Redis
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.module_platform.tenant.crud import TenantCRUD
from app.api.v1.module_system.user.crud import UserCRUD
from app.core.base_schema import AuthSchema, PageResultSchema
from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import logger
from app.utils.password_util import PwdUtil

from .crud import ApiTokenCRUD
from .model import ApiTokenModel
from .schema import (
    ApiTokenCreatedSchema,
    ApiTokenCreateSchema,
    ApiTokenOutSchema,
    ApiTokenQueryParam,
    ApiTokenResetSchema,
    ApiTokenRevealOutSchema,
    ApiTokenRevealSchema,
)

_TOKEN_PREFIX_HEADER = "fastpat_"
_TOKEN_PREFIX_DISPLAY_LEN = 12
_REDIS_RATE_KEY_PREFIX = "api_token:rate:"


def _generate_full_token(tenant_code: str, tenant_id: int) -> str:
    """生成完整 token：``fastpat_<tenant_code>_<tenant_id_hex>_<48-base64url>``"""
    secret_part = secrets.token_urlsafe(36)
    return f"{_TOKEN_PREFIX_HEADER}{tenant_code}_{tenant_id:x}_{secret_part}"


def _mask_token(full_token: str) -> str:
    """脱敏展示：保留头部 + ``****`` + 尾部 4 字符"""
    if len(full_token) <= 16:
        return "****"
    return f"{full_token[:14]}****{full_token[-4:]}"


def _to_out_schema(token: ApiTokenModel) -> ApiTokenOutSchema:
    return ApiTokenOutSchema(
        id=token.id,
        name=token.name,
        token_prefix=token.token_prefix,
        token_mask=_mask_token(token.token_plain),
        owner_user_id=token.owner_user_id,
        scopes=token.scopes,
        status=token.status,
        rate_limit=token.rate_limit,
        expires_at=token.expires_at,
        used_count=token.used_count,
        last_used_at=token.last_used_at,
        last_used_ip=token.last_used_ip,
        description=token.description,
        tenant_id=token.tenant_id,
        created_id=token.created_id,
        updated_id=token.updated_id,
        created_time=token.created_time,
        updated_time=token.updated_time,
    )


def _parse_scopes(scopes_str: str) -> list[str]:
    if not scopes_str:
        return []
    if scopes_str == "*":
        return ["*"]
    try:
        loaded = json.loads(scopes_str)
        if isinstance(loaded, list):
            return loaded
    except (json.JSONDecodeError, ValueError):
        pass
    return [s.strip() for s in scopes_str.split(",") if s.strip()]


# ──────────────────────────────────────────────────────────
#  Service
# ──────────────────────────────────────────────────────────


class ApiTokenService:
    """API Token 业务逻辑层"""

    MAX_TOKENS_PER_TENANT: int = 50

    def __init__(self, auth: AuthSchema, db: AsyncSession) -> None:
        self.auth = auth
        self.db = db

    # ── 租户隔离检查 ──────────────────────────────────────

    def _check_tenant_access(self, token: ApiTokenModel) -> None:
        """非超管只能访问本租户 token"""
        if not self.auth.user.is_superuser and token.tenant_id != self.auth.user.tenant_id:
            raise CustomException(msg="无权操作其他租户的 token")

    # ── 创建 ──────────────────────────────────────────────

    async def create(self, data: ApiTokenCreateSchema) -> ApiTokenCreatedSchema:
        tenant = await TenantCRUD(self.auth, self.db).get(id=self.auth.user.tenant_id)
        if not tenant:
            raise CustomException(msg="租户上下文失效，无法创建 token")

        existing = await ApiTokenCRUD(self.auth, self.db).get_list(
            search={"tenant_id": tenant.id},
        )
        active_count = sum(1 for t in existing if t.status == 0 and not t.is_deleted)
        if active_count >= self.MAX_TOKENS_PER_TENANT:
            raise CustomException(msg=f"该租户 API Token 数量已达上限 ({self.MAX_TOKENS_PER_TENANT})，请先删除或禁用旧 token")

        full_token = _generate_full_token(tenant_code=tenant.code, tenant_id=tenant.id)
        token_prefix = full_token[:_TOKEN_PREFIX_DISPLAY_LEN]

        scopes_str = ",".join(data.scopes) if data.scopes else "*"
        crud = ApiTokenCRUD(self.auth, self.db)
        token_obj = await crud.create(
            data={  # pyright: ignore[reportArgumentType]
                "name": data.name,
                "token_prefix": token_prefix,
                "token_plain": full_token,
                "owner_user_id": self.auth.user.id,
                "scopes": scopes_str,
                "expires_at": data.expires_at,
                "status": 0,
                "rate_limit": data.rate_limit,
                "description": data.description,
            },
        )
        if not token_obj:
            raise CustomException(msg="创建 token 失败")

        logger.info(f"租户[{tenant.id}]新 token 创建成功: id={token_obj.id} name={data.name}")
        return ApiTokenCreatedSchema(
            id=token_obj.id,
            name=token_obj.name,
            token=full_token,
            token_prefix=token_prefix,
            scopes=data.scopes,
            expires_at=token_obj.expires_at,
            rate_limit=token_obj.rate_limit,
            status=token_obj.status,
            tenant_id=token_obj.tenant_id,
            created_time=token_obj.created_time,
        )

    # ── 查询 ──────────────────────────────────────────────

    async def page(
        self,
        page_no: int,
        page_size: int,
        search: ApiTokenQueryParam,
        order_by: list[dict[str, str]] | None = None,
    ) -> PageResultSchema[ApiTokenOutSchema]:
        crud = ApiTokenCRUD(self.auth, self.db)
        search_dict: dict[str, Any] = {}
        if search.name:
            search_dict["name"] = ("like", f"%{search.name}%")
        if search.status is not None:
            search_dict["status"] = search.status
        result = await crud.page(
            offset=(page_no - 1) * page_size,
            limit=page_size,
            search=search_dict,
            order_by=order_by or [{"id": "asc"}],
        )
        items_out = [_to_out_schema(row) for row in result.items]
        return PageResultSchema[ApiTokenOutSchema](
            page_no=result.page_no,
            page_size=result.page_size,
            total=result.total,
            has_next=result.has_next,
            items=items_out,
        )

    async def detail(self, id: int) -> ApiTokenOutSchema:
        crud = ApiTokenCRUD(self.auth, self.db)
        token = await crud.get_or_404(id=id)
        self._check_tenant_access(token)
        return _to_out_schema(token)

    # ── 状态/重置 ──────────────────────────────────────────

    async def reset(self, id: int, data: ApiTokenResetSchema) -> ApiTokenCreatedSchema:
        crud = ApiTokenCRUD(self.auth, self.db)
        token = await crud.get_or_404(id=id)
        self._check_tenant_access(token)

        tenant = await TenantCRUD(self.auth, self.db).get(id=token.tenant_id)
        if not tenant:
            raise CustomException(msg="租户不存在")

        full_token = _generate_full_token(tenant_code=tenant.code, tenant_id=tenant.id)
        token_prefix_new = full_token[:_TOKEN_PREFIX_DISPLAY_LEN]

        values: dict[str, Any] = {
            "token_prefix": token_prefix_new,
            "token_plain": full_token,
            "used_count": 0,
        }
        if data.name is not None:
            values["name"] = data.name
        if data.scopes is not None:
            values["scopes"] = ",".join(data.scopes)
        if data.expires_at is not None:
            values["expires_at"] = data.expires_at
        if data.rate_limit is not None:
            values["rate_limit"] = data.rate_limit

        await self.db.execute(sa_update(ApiTokenModel).where(ApiTokenModel.id == id).values(**values))
        await self.db.flush()
        await self.db.refresh(token)

        logger.info(f"租户[{tenant.id}] token[{id}] 已重置，新前缀={token_prefix_new}")
        return ApiTokenCreatedSchema(
            id=token.id,
            name=token.name,
            token=full_token,
            token_prefix=token_prefix_new,
            scopes=_parse_scopes(token.scopes),
            expires_at=token.expires_at,
            rate_limit=token.rate_limit,
            status=token.status,
            tenant_id=token.tenant_id,
            created_time=token.created_time,
        )

    async def set_status(self, id: int, status: int) -> None:
        if status not in (0, 1, 2):
            raise CustomException(msg="状态值不合法（0:启用 1:禁用 2:吊销）")
        crud = ApiTokenCRUD(self.auth, self.db)
        token = await crud.get_or_404(id=id)
        self._check_tenant_access(token)
        await crud.update(id=id, data={"status": status})  # pyright: ignore[reportArgumentType]

    async def delete(self, id: int) -> None:
        crud = ApiTokenCRUD(self.auth, self.db)
        token = await crud.get_or_404(id=id)
        self._check_tenant_access(token)
        await crud.delete(ids=[id])

    # ── reveal：二次验证后展示明文 ─────────────────────────

    async def reveal(self, id: int, data: ApiTokenRevealSchema) -> ApiTokenRevealOutSchema:
        user_row = await UserCRUD(self.auth, self.db).get(id=self.auth.user.id)
        if not user_row:
            raise CustomException(msg="用户不存在")
        if not PwdUtil.verify_password(plain_password=data.password, password_hash=user_row.password):
            logger.warning(f"reveal 二次验证失败: user_id={self.auth.user.id}")
            raise CustomException(msg="密码错误，无法 reveal 明文")

        crud = ApiTokenCRUD(self.auth, self.db)
        token = await crud.get_or_404(id=id)
        self._check_tenant_access(token)

        return ApiTokenRevealOutSchema(token=token.token_plain, name=token.name)


# ──────────────────────────────────────────────────────────
#  外部 API Bearer 验证（公开接口）
# ──────────────────────────────────────────────────────────


async def authenticate_api_token(token: str, request_ip: str | None = None, redis: Redis | None = None) -> ApiTokenModel:
    """外部 API 鉴权：从 Authorization Bearer 中解析 fastpat token，记录调用次数。"""
    if not token or not token.startswith(_TOKEN_PREFIX_HEADER):
        raise CustomException(msg="API Token 格式不合法", code=10401, status_code=401)

    async with async_db_session() as db:
        crud = ApiTokenCRUD(AuthSchema(check_data_scope=False), db)
        candidate = await crud.get_list(search={"token_plain": ("=", token)})
        if not candidate:
            raise CustomException(msg="API Token 无效", code=10401, status_code=401)
        token_row = candidate[0]

        if token_row.status != 0:
            raise CustomException(msg="API Token 已禁用或吊销", code=10401, status_code=401)
        if token_row.expires_at is not None and token_row.expires_at < datetime.now():
            raise CustomException(msg="API Token 已过期", code=10401, status_code=401)
        if token_row.is_deleted:
            raise CustomException(msg="API Token 已删除", code=10401, status_code=401)

        # 限流（每小时）
        if redis is not None:
            try:
                key = f"{_REDIS_RATE_KEY_PREFIX}{token_row.id}:{datetime.now().strftime('%Y%m%d%H')}"
                current = await redis.incr(key)
                if current == 1:
                    await redis.expire(key, 3600)
                if current > token_row.rate_limit:
                    raise CustomException(
                        msg=f"API Token 限流：本小时已调用 {current} 次，上限 {token_row.rate_limit}",
                        code=10429,
                        status_code=429,
                    )
            except CustomException:
                raise
            except Exception as e:
                logger.warning(f"API Token 限流检查失败（继续放行）: {e!s}")

        await db.execute(
            sa_update(ApiTokenModel)
            .where(ApiTokenModel.id == token_row.id)
            .values(
                used_count=ApiTokenModel.used_count + 1,
                last_used_at=datetime.now(),
                last_used_ip=request_ip,
            ),
        )
        await db.commit()
        return token_row
