import json
from collections.abc import Sequence

from redis.asyncio.client import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import RedisInitKeyConfig
from app.core.base_schema import AuthSchema, PageResultSchema
from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import logger
from app.core.middlewares import invalidate_middleware_config_cache
from app.core.redis_crud import RedisCURD
from app.utils.common_util import search_to_dict
from app.utils.excel_util import ExcelUtil

from .crud import ParamsCRUD
from .schema import (
    ParamsCreateSchema,
    ParamsOutSchema,
    ParamsQueryParam,
    ParamsUpdateSchema,
)


class ParamsService:
    """参数管理服务

    设计：实例方法承载「当前用户上下文 (auth)」，``redis`` 仍是方法参数
    （因为不是每个端点都用到）。调用方写法由
    ``ParamsService.method_service(auth=...)`` 改为 ``ParamsService(auth).method(...)``。
    """

    def __init__(self, auth: AuthSchema, db: AsyncSession) -> None:
        self.auth = auth
        self.db = db

    async def detail(self, id: int) -> ParamsOutSchema:
        """获取参数详情

        参数:
        - id (int): 参数ID

        返回:
        - ParamsOutSchema: 参数响应模型
        """
        obj = await ParamsCRUD(self.auth, self.db).get_or_404(id=id)
        return ParamsOutSchema.model_validate(obj)

    async def get_by_key(self, config_key: str) -> ParamsOutSchema:
        """根据配置键获取参数详情

        参数:
        - config_key (str): 参数键名

        返回:
        - ParamsOutSchema: 参数响应模型
        """
        obj = await ParamsCRUD(self.auth, self.db).get(config_key=config_key)
        if not obj:
            raise CustomException(msg="该数据不存在")
        return ParamsOutSchema.model_validate(obj)

    async def get_list(
        self,
        search: ParamsQueryParam | None = None,
        order_by: list[dict] | None = None,
    ) -> list[ParamsOutSchema]:
        """获取配置管理型列表

        参数:
        - search (ParamsQueryParam | None): 查询参数对象
        - order_by (list[dict] | None): 排序参数列表

        返回:
        - list[ParamsOutSchema]: 参数响应模型列表
        """
        obj_list = await ParamsCRUD(self.auth, self.db).get_list(search=search_to_dict(search), order_by=order_by)
        return [ParamsOutSchema.model_validate(obj) for obj in obj_list]

    async def page(
        self,
        page_no: int,
        page_size: int,
        search: ParamsQueryParam | None = None,
        order_by: list[dict[str, str]] | None = None,
    ) -> PageResultSchema[ParamsOutSchema]:
        """分页查询系统参数（数据库 OFFSET/LIMIT）。

        参数:
        - page_no (int): 页码（从 1 开始）
        - page_size (int): 每页条数
        - search (ParamsQueryParam | None): 查询条件
        - order_by (list[dict[str, str]] | None): 排序字段列表

        返回:
        - PageResultSchema[ParamsOutSchema]: 分页结果
        """
        offset = (page_no - 1) * page_size
        return await ParamsCRUD(self.auth, self.db).page(
            offset=offset,
            limit=page_size,
            order_by=order_by or [{"id": "asc"}],
            search=search_to_dict(search),
            out_schema=ParamsOutSchema,
        )

    async def create(self, redis: Redis, data: ParamsCreateSchema) -> ParamsOutSchema:
        """创建配置管理型

        参数:
        - redis (Redis): Redis 客户端实例
        - data (ParamsCreateSchema): 配置管理型创建模型

        返回:
        - ParamsOutSchema: 新创建的参数响应模型
        """
        exist_obj = await ParamsCRUD(self.auth, self.db).get(config_key=data.config_key)
        if exist_obj:
            raise CustomException(msg="创建失败，该数据已存在")
        obj = await ParamsCRUD(self.auth, self.db).create(data=data)

        out = ParamsOutSchema.model_validate(obj)

        # 同步redis
        user = self.auth.user
        if not user:
            raise CustomException(msg="未登录")
        redis_key = f"{RedisInitKeyConfig.SYSTEM_CONFIG.key}:{user.tenant_id}:{data.config_key}"
        try:
            redis_payload = out.model_dump(mode="json")
            value = json.dumps(redis_payload, ensure_ascii=False)
            result = await RedisCURD(redis).set(
                key=redis_key,
                value=value,
                expire=None,
            )
            if not result:
                logger.error(f"同步配置到缓存失败: {out}")
                raise CustomException(msg="同步配置到缓存失败")
        except Exception as e:
            logger.error(f"创建字典类型失败: {e}")
            raise CustomException(msg="同步配置到缓存失败") from e

        return out

    async def update(self, redis: Redis, id: int, data: ParamsUpdateSchema) -> ParamsOutSchema:
        """更新参数

        参数:
        - redis (Redis): Redis 客户端实例
        - id (int): 参数ID
        - data (ParamsUpdateSchema): 参数更新模型

        返回:
        - ParamsOutSchema: 更新后的参数响应模型
        """
        exist_obj = await ParamsCRUD(self.auth, self.db).get_or_404(id=id, msg="更新失败，该数据不存在")
        if exist_obj.config_key != data.config_key:
            raise CustomException(msg="更新失败，系统配置key不允许修改")

        new_obj = await ParamsCRUD(self.auth, self.db).update(id=id, data=data)
        if not new_obj:
            raise CustomException(msg="更新失败，系统配置不存在")
        out = ParamsOutSchema.model_validate(new_obj)
        redis_payload = out.model_dump(mode="json")

        # 同步redis
        user = self.auth.user
        if not user:
            raise CustomException(msg="未登录")
        redis_key = f"{RedisInitKeyConfig.SYSTEM_CONFIG.key}:{user.tenant_id}:{new_obj.config_key}"
        try:
            value = json.dumps(redis_payload, ensure_ascii=False)
            result = await RedisCURD(redis).set(
                key=redis_key,
                value=value,
                expire=None,
            )
            if not result:
                logger.error(f"同步配置到缓存失败: {out}")
                raise CustomException(msg="同步配置到缓存失败")
        except Exception as e:
            logger.error(f"更新系统配置失败: {e}")
            raise CustomException(msg="同步配置到缓存失败") from e

        # 失效中间件内存缓存，让下次请求重新加载
        invalidate_middleware_config_cache(user.tenant_id)

        return out

    async def delete(self, redis: Redis, ids: list[int]) -> None:
        """删除配置管理型

        参数:
        - redis (Redis): Redis 客户端实例
        - ids (list[int]): 配置管理型ID列表

        返回:
        - None
        """
        if not ids:
            raise CustomException(msg="删除失败，删除对象不能为空")
        # 批量校验参数存在性
        objs = await ParamsCRUD(self.auth, self.db).get_list(search={"id": ("in", ids)})
        obj_map = {o.id: o for o in objs}
        for pid in ids:
            obj = obj_map.get(pid)
            if not obj:
                raise CustomException(msg="删除失败，该数据不存在")
            if obj.config_type:
                raise CustomException(msg=f"{obj.config_name} 删除失败，系统初始化配置不可以删除")

        await ParamsCRUD(self.auth, self.db).delete(ids=ids)

        # 同步删除Redis缓存（使用删除前已获取的对象信息）
        user = self.auth.user
        if not user:
            raise CustomException(msg="未登录")
        for obj in objs:
            redis_key = f"{RedisInitKeyConfig.SYSTEM_CONFIG.key}:{user.tenant_id}:{obj.config_key}"
            try:
                await RedisCURD(redis).delete(redis_key)
            except Exception as e:
                logger.error(f"删除系统配置失败: {e}")
                raise CustomException(msg="同步删除缓存失败") from e

        # 失效中间件内存缓存
        invalidate_middleware_config_cache(user.tenant_id)

    async def batch_set_status(self, redis: Redis, ids: list[int], status: int) -> None:
        """批量设置系统参数状态

        参数:
        - redis: Redis 客户端（用于同步缓存）
        - ids (list[int]): 系统参数ID列表
        - status (int): 状态值

        返回:
        - None
        """
        if not ids:
            raise CustomException(msg="请选择要操作的数据")

        # 先查参数列表获取 config_key 和 tenant_id
        params = await ParamsCRUD(self.auth, self.db).get_list(search={"id": ("in", list(ids))})
        await ParamsCRUD(self.auth, self.db).set(ids=ids, status=status)
        # 同步删除对应 Redis 缓存
        for param in params:
            redis_key = f"{RedisInitKeyConfig.SYSTEM_CONFIG.key}:{param.tenant_id}:{param.config_key}"
            try:
                await RedisCURD(redis).delete(redis_key)
            except Exception as e:
                logger.error(f"同步删除系统配置缓存失败: {e}")
        invalidate_middleware_config_cache(None)

    @staticmethod
    def export(data_list: list[dict]) -> bytes:
        """导出参数列表（无状态工具方法）

        参数:
        - data_list (list[dict]): 参数字典列表

        返回:
        - bytes: Excel 文件字节流
        """
        mapping_dict = {
            "id": "编号",
            "config_name": "参数名称",
            "config_key": "参数键名",
            "config_value": "参数键值",
            "config_type": "系统内置((True:是 False:否))",
            "description": "备注",
            "created_time": "创建时间",
            "updated_time": "更新时间",
            "created_id": "创建者ID",
            "updated_id": "更新者ID",
        }

        # 复制数据并转换状态
        data = data_list.copy()
        for item in data:
            # 处理状态
            item["config_type"] = "是" if item.get("config_type") else "否"

        return ExcelUtil.export_list2excel(list_data=data, mapping_dict=mapping_dict)

    @staticmethod
    async def _load_all_configs_from_db() -> Sequence[object]:
        async with async_db_session() as session, session.begin():
            init_auth = AuthSchema(check_data_scope=False)
            return await ParamsCRUD(init_auth, session).get_list()

    @staticmethod
    async def _sync_configs_to_redis(redis: Redis, config_obj: Sequence) -> list[dict]:
        """将 DB 配置写入 Redis，返回对应的 dict 列表。"""
        configs: list[dict] = []
        for config in config_obj:
            redis_key = f"{RedisInitKeyConfig.SYSTEM_CONFIG.key}:{config.tenant_id}:{config.config_key}"
            out = ParamsOutSchema.model_validate(config)
            payload = out.model_dump(mode="json")
            try:
                await RedisCURD(redis).set(redis_key, json.dumps(payload, ensure_ascii=False))
                configs.append(out.model_dump())
            except Exception as e:
                logger.error(f"❌️ 缓存系统配置失败: {redis_key}: {e}")
        return configs

    @staticmethod
    async def init_cache(redis: Redis) -> None:
        """启动时初始化系统参数到 Redis。"""
        config_obj = await ParamsService._load_all_configs_from_db()
        if not config_obj:
            raise CustomException(msg="该数据不存在")
        await ParamsService._sync_configs_to_redis(redis, config_obj)

    @staticmethod
    async def get_init_cache(redis: Redis, tenant_id: int = 1) -> list[dict]:
        """从 Redis 读取系统配置；为空时自动回源 DB。"""
        redis_keys = await RedisCURD(redis).get_keys(f"{RedisInitKeyConfig.SYSTEM_CONFIG.key}:{tenant_id}:*")
        redis_configs = await RedisCURD(redis).mget(redis_keys)
        configs = []
        for raw in redis_configs:
            if not raw:
                continue
            try:
                configs.append(json.loads(raw))
            except Exception as e:
                logger.error(f"解析系统配置数据失败: {e}")

        if not configs:
            config_obj = await ParamsService._load_all_configs_from_db()
            if config_obj:
                configs = await ParamsService._sync_configs_to_redis(redis, config_obj)
        return configs
