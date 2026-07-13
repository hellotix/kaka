import json
from datetime import datetime, timedelta
from typing import Any

from redis.asyncio.client import Redis
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.module_platform.menu.model import MenuModel
from app.api.v1.module_platform.order.crud import OrderCRUD
from app.api.v1.module_platform.order.model import OrderModel
from app.api.v1.module_platform.order.schema import (
    OrderCreateInternalSchema,
    OrderUpdateInternalSchema,
)
from app.api.v1.module_platform.package.crud import PackageCRUD
from app.api.v1.module_platform.package.model import PackageModel
from app.api.v1.module_platform.package.service import PackageService
from app.api.v1.module_system.dept.crud import DeptCRUD
from app.api.v1.module_system.dept.model import DeptModel
from app.api.v1.module_system.position.crud import PositionCRUD
from app.api.v1.module_system.role.crud import RoleCRUD
from app.api.v1.module_system.role.model import RoleMenusModel, RoleModel
from app.api.v1.module_system.role.schema import RoleCreateSchema
from app.api.v1.module_system.user.crud import UserCRUD
from app.api.v1.module_system.user.model import UserModel
from app.api.v1.module_system.user.schema import UserCreateSchema
from app.common.enums import OrderTypeEnum, RedisInitKeyConfig
from app.core.base_schema import AuthSchema, BatchSetAvailable, PageResultSchema
from app.core.database import async_db_session
from app.core.exceptions import CustomException, require_superadmin
from app.core.logger import logger
from app.core.redis_crud import RedisCURD
from app.utils.common_util import search_to_dict
from app.utils.password_util import PwdUtil

from .crud import TenantCRUD
from .model import TenantModel, TenantUserModel
from .schema import (
    PackageAction,
    PackageAvailableItem,
    PackageAvailableOut,
    PackageChangePreviewOut,
    PackagePreviewOut,
    SelfOrderCreate,
    SelfOrderDetailOut,
    SelfOrderListItem,
    SelfOrderListOut,
    SelfOrderOut,
    TenantAdminInfo,
    TenantConfigOutSchema,
    TenantCreateResult,
    TenantCreateSchema,
    TenantOutSchema,
    TenantQueryParam,
    TenantUpdateSchema,
    TenantUserAddSchema,
    TenantUserOutSchema,
    WorkspaceOrderItem,
    WorkspaceOut,
    WorkspacePackageInfo,
    WorkspaceQuotaInfo,
    WorkspaceTenantInfo,
    WorkspaceUsagePercent,
)


class TenantService:
    """租户管理服务（查询操作租户可见，写操作仅超级管理员可操作）

    设计：实例方法承载「当前用户上下文 (auth)」，``redis`` 仍是方法参数。
    内部跨方法调用从 ``cls.xxx(auth, ...)`` 改为 ``self.xxx(...)``。
    定时任务方法与静态工具方法保持 ``@staticmethod``（无 auth）。
    """

    CONFIG_FIELDS = [
        "name",
        "description",
        "version",
        "logo_url",
        "favicon",
        "login_bg",
        "copyright",
        "keep_record",
        "help_doc",
        "privacy",
        "clause",
        "git_code",
    ]

    def __init__(self, auth: AuthSchema, db: AsyncSession) -> None:
        self.auth = auth
        self.db = db

    async def detail(self, id: int) -> TenantOutSchema:
        """租户详情

        参数:
        - id (int): 租户ID

        返回:
        - TenantOutSchema: 租户详情
        """
        obj = await TenantCRUD(self.auth, self.db).get_or_404(id=id)
        return TenantOutSchema.model_validate(obj)

    async def page(
        self,
        page_no: int,
        page_size: int,
        search: TenantQueryParam | None = None,
        order_by: list[dict[str, str]] | None = None,
    ) -> PageResultSchema[TenantOutSchema]:
        return await TenantCRUD(self.auth, self.db).page(
            offset=(page_no - 1) * page_size,
            limit=page_size,
            order_by=order_by or [{"id": "asc"}],
            search=search_to_dict(search),
            out_schema=TenantOutSchema,
        )

    @require_superadmin
    async def create(self, data: TenantCreateSchema) -> TenantCreateResult:
        # ① 预校验：name / code 唯一
        if await TenantCRUD(self.auth, self.db).get(name=data.name):
            raise CustomException(msg="创建失败，名称已存在")
        if await TenantCRUD(self.auth, self.db).get(code=data.code):
            raise CustomException(msg="创建失败，编码已存在")

        # ② 校验套餐：必须存在且启用

        package = await PackageCRUD(self.auth, self.db).get(id=data.package_id)
        if not package:
            raise CustomException(msg=f"套餐[{data.package_id}]不存在")
        if package.status != 0:
            raise CustomException(msg=f"套餐[{package.name}]已停用，无法注册租户")

        # ③ 生成初始管理员账号（用户名 = code_admin），随机密码仅此一次返回
        username = f"{data.code}_admin"

        if await UserCRUD(self.auth, self.db).get(username=username):
            raise CustomException(msg=f"初始管理员用户名已存在: {username}，请更换租户编码后重试")

        password = PwdUtil.generate_strong_password(length=12)

        # ④ 创建租户（事务起点）
        tenant_obj = await TenantCRUD(self.auth, self.db).create(data=data)
        if not tenant_obj:
            raise CustomException(msg="创建租户失败")

        # ⑤ 创建「管理员」角色（tenant_id 已建立，code 用 f"{tenant_code}_admin" 避免与编码冲突）

        admin_role = RoleCreateSchema(
            name=f"{tenant_obj.name}管理员",
            code=f"{tenant_obj.code}_admin",
            order=1,
            data_scope=4,  # 全部数据权限
            status=0,
            description="租户初始管理员角色（由系统开通时自动创建）",
        )
        role_obj = await RoleCRUD(self.auth, self.db).create(data=admin_role)
        if not role_obj:
            raise CustomException(msg="创建租户管理员角色失败")
        # 强制同步 tenant_id（CRUD.create 不会从 auth 写入新模型，避免被默认 0 覆盖）
        role_obj.tenant_id = tenant_obj.id
        await self.db.flush()

        # ⑥ 创建初始管理员用户，并关联管理员角色
        admin_user = UserCreateSchema(
            username=username,
            password=PwdUtil.hash_password(password=password),
            name=f"{tenant_obj.name}管理员",
            tenant_id=tenant_obj.id,
            status=0,
            is_superuser=False,
            role_ids=[role_obj.id],
        )
        try:
            user_obj = await UserCRUD(self.auth, self.db).create(data=admin_user)
            if not user_obj:
                raise CustomException(msg="创建租户初始管理员失败")
        except CustomException:
            raise
        except Exception as e:
            logger.error(f"为租户[{tenant_obj.name}]创建初始管理员失败: {e!s}")
            raise CustomException(msg="创建租户初始管理员失败") from e

        # ⑦ 把套餐所有菜单授权给管理员角色（快照模式：复制 ID，不维护引用）

        menu_ids = await PackageService(self.auth, self.db).get_package_menu_ids(data.package_id)
        if menu_ids:
            await RoleCRUD(self.auth, self.db).set_role_menus_crud(
                role_ids=[role_obj.id],
                menu_ids=menu_ids,
            )

        # ⑧ 缓存刷新（失败不阻塞：DB 已是真相，后续 _sync_all_configs_to_redis 会补偿）
        try:
            await self.db.commit()
            logger.info(
                f"✅ 租户[{tenant_obj.name}]开通完成 "
                f"(套餐={package.name}, 菜单授权={len(menu_ids)}, 管理员={username})"
            )
        except Exception as e:
            logger.warning(f"租户[{tenant_obj.name}]缓存刷新失败（事务已提交，可后续补偿）: {e!s}")

        await self.db.refresh(tenant_obj)

        return TenantCreateResult(
            tenant=TenantOutSchema.model_validate(tenant_obj),
            admin=TenantAdminInfo(
                username=username,
                initial_password=password,
                must_change_password=True,
            ),
        )

    @require_superadmin
    async def update(self, id: int, data: TenantUpdateSchema) -> TenantOutSchema:
        """更新租户

        参数:
        - id (int): 租户ID
        - data (TenantUpdateSchema): 租户更新模型

        返回:
        - TenantOutSchema: 租户详情
        """
        obj = await TenantCRUD(self.auth, self.db).get_or_404(id=id)
        old_package_id = obj.package_id

        await self._validate_tenant_update(id, obj, data)

        updated = await TenantCRUD(self.auth, self.db).update(id=id, data=data)
        if not updated:
            raise CustomException(msg="更新失败")

        # 套餐变更后：清理角色中不再可用的菜单关联；如果是降级，先校验不超额再清理
        if data.package_id is not None and data.package_id != old_package_id:
            await self._handle_package_change(id, old_package_id, data.package_id)

        return TenantOutSchema.model_validate(updated)

    async def _validate_tenant_update(self, id: int, obj: TenantModel, data: TenantUpdateSchema) -> None:
        """校验租户更新约束"""
        if id == 1:
            if data.code is not None and data.code != obj.code:
                raise CustomException(msg="系统租户编码不可修改")
            if data.status is not None and data.status == 1:
                raise CustomException(msg="系统租户不允许禁用")

        # 套餐变更：仅超管可操作，防止租户管理员自行升级/降级套餐
        if data.package_id is not None and data.package_id != obj.package_id:
            if not self.auth.user or not self.auth.user.is_superuser:
                raise CustomException(msg="仅平台管理员可变更租户套餐")

        if data.name is not None:
            exist = await TenantCRUD(self.auth, self.db).get(name=data.name)
            if exist and exist.id != id:
                raise CustomException(msg="更新失败，名称重复")
        if data.code is not None:
            exist = await TenantCRUD(self.auth, self.db).get(code=data.code)
            if exist and exist.id != id:
                raise CustomException(msg="更新失败，编码重复")

    async def _handle_package_change(self, tenant_id: int, old_package_id: int | None, new_package_id: int) -> None:
        """处理套餐变更：降级预检 + 菜单清理"""

        new_pkg = await PackageCRUD(self.auth, self.db).get(id=new_package_id)
        if not new_pkg:
            raise CustomException(msg=f"套餐[{new_package_id}]不存在")

        # 降级前的超额预检：升级和首次绑定跳过；降级时若现有资源超过新套餐上限则拒
        if old_package_id is not None:
            counts_stmt_user = select(func.count(UserModel.id)).where(
                UserModel.tenant_id == tenant_id, UserModel.is_deleted.is_(False)
            )
            counts_stmt_role = select(func.count(RoleModel.id)).where(
                RoleModel.tenant_id == tenant_id, RoleModel.is_deleted.is_(False)
            )
            counts_stmt_dept = select(func.count(DeptModel.id)).where(
                DeptModel.tenant_id == tenant_id, DeptModel.is_deleted.is_(False)
            )
            user_count = (await self.db.execute(counts_stmt_user)).scalar_one()
            role_count = (await self.db.execute(counts_stmt_role)).scalar_one()
            dept_count = (await self.db.execute(counts_stmt_dept)).scalar_one()

            exceed_msgs = []
            if new_pkg.max_users and user_count > new_pkg.max_users:
                exceed_msgs.append(f"用户({user_count}>{new_pkg.max_users})")
            if new_pkg.max_roles and role_count > new_pkg.max_roles:
                exceed_msgs.append(f"角色({role_count}>{new_pkg.max_roles})")
            if new_pkg.max_depts and dept_count > new_pkg.max_depts:
                exceed_msgs.append(f"部门({dept_count}>{new_pkg.max_depts})")
            if exceed_msgs:
                raise CustomException(
                    msg="降级失败：当前资源超过新套餐上限，请先清理或升级套餐: " + " ".join(exceed_msgs),
                )

        available_ids = await PackageService(self.auth, self.db).get_tenant_available_menu_ids(tenant_id)
        if not available_ids:
            return
        role_ids_stmt = select(RoleModel.id).where(RoleModel.tenant_id == tenant_id)
        result = await self.db.execute(role_ids_stmt)
        tenant_role_ids = [row[0] for row in result.all()]
        if tenant_role_ids:
            await self.db.execute(
                delete(RoleMenusModel).where(
                    RoleMenusModel.role_id.in_(tenant_role_ids),
                    RoleMenusModel.menu_id.notin_(available_ids),
                ),
            )
            await self.db.flush()
            logger.info(f"租户[{tenant_id}]套餐变更：已清理角色中不再可用的菜单关联, available_menus={len(available_ids)}, roles_affected={len(tenant_role_ids)}")

    @require_superadmin
    async def delete(self, ids: list[int]) -> None:
        """批量删除租户（含级联资源检查：用户/部门/角色/岗位）

        参数:
        - ids (list[int]): 租户ID列表

        返回:
        - None
        """
        if not ids:
            raise CustomException(msg="删除失败，删除对象不能为空")
        if 1 in ids:
            raise CustomException(msg="系统租户不允许删除")

        # 批量检查所有租户是否有关联资源（一次查询代替 N*4 次）
        resource_checks = [
            ("用户", UserCRUD, "tenant_id"),
            ("部门", DeptCRUD, "tenant_id"),
            ("角色", RoleCRUD, "tenant_id"),
            ("岗位", PositionCRUD, "tenant_id"),
        ]
        tid_set = set(ids)
        for name, crud_cls, field in resource_checks:
            existing = await crud_cls(self.auth, self.db).get_list(search={field: ("in", list(tid_set))})
            used_tids = {getattr(obj, field) for obj in existing if getattr(obj, field, None) is not None}
            conflict = tid_set & used_tids
            if conflict:
                raise CustomException(msg=f"租户下已存在{name}，操作失败")

        await TenantCRUD(self.auth, self.db).delete(ids=ids)

    async def set_available(self, data: BatchSetAvailable) -> None:
        """批量设置租户状态

        参数:
        - data (BatchSetAvailable): 批量状态设置

        返回:
        - None
        """
        if data.status == 1 and 1 in data.ids:
            raise CustomException(msg="系统租户不允许禁用")
        await TenantCRUD(self.auth, self.db).set(ids=data.ids, status=data.status)

    async def toggle_status(self, id: int) -> None:
        """切换单个租户的启用/禁用状态

        参数:
        - id (int): 租户ID

        返回:
        - None
        """
        obj = await TenantCRUD(self.auth, self.db).get_or_404(id=id)
        if id == 1:
            raise CustomException(msg="系统租户不允许禁用")
        new_status = 0 if obj.status == 1 else 1
        await TenantCRUD(self.auth, self.db).set(ids=[id], status=new_status)

    async def get_tenant_users(self, tenant_id: int) -> list[TenantUserOutSchema]:
        """获取租户下的用户列表"""

        stmt = (
            select(TenantUserModel, UserModel)
            .join(UserModel, UserModel.id == TenantUserModel.user_id)
            .where(TenantUserModel.tenant_id == tenant_id)
            .order_by(TenantUserModel.is_default.desc(), TenantUserModel.id)
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        users = []
        for tenant_user, user_row in rows:
            users.append(
                TenantUserOutSchema(
                    id=tenant_user.id,
                    user_id=tenant_user.user_id,
                    tenant_id=tenant_user.tenant_id,
                    role=tenant_user.role,
                    is_default=tenant_user.is_default,
                    create_time=tenant_user.create_time,
                    username=user_row.username,
                    name=user_row.name,
                ),
            )
        return users

    async def add_tenant_user(self, tenant_id: int, data: TenantUserAddSchema) -> None:
        """向租户添加用户

        参数:
        - tenant_id (int): 租户ID
        - data (TenantUserAddSchema): 用户添加参数

        返回:
        - None
        """
        # 验证租户存在
        tenant = await TenantCRUD(self.auth, self.db).get(id=tenant_id)
        if not tenant:
            raise CustomException(msg="该数据不存在")

        # 验证用户存在

        user = await UserCRUD(self.auth, self.db).get(id=data.user_id)
        if not user:
            raise CustomException(msg="该数据不存在")

        # 检查是否已关联
        exist_stmt = (
            select(TenantUserModel)
            .where(
                TenantUserModel.user_id == data.user_id,
                TenantUserModel.tenant_id == tenant_id,
            )
            .limit(1)
        )
        result = await self.db.execute(exist_stmt)
        if result.scalar_one_or_none():
            raise CustomException(msg="该用户已关联此租户")

        # 如果设为默认租户，先取消其他默认
        if data.is_default == 1:
            await self.db.execute(update(TenantUserModel).where(TenantUserModel.user_id == data.user_id).values(is_default=0))
        elif data.is_default == 0:
            # 检查是否是该用户的第一个租户关联
            count_result = await self.db.execute(select(func.count()).select_from(TenantUserModel).where(TenantUserModel.user_id == data.user_id))
            count = count_result.scalar()
            if count == 0:
                # 第一个租户自动设为默认
                data.is_default = 1

        tu = TenantUserModel(
            user_id=data.user_id,
            tenant_id=tenant_id,
            role=data.role,
            is_default=data.is_default,
            create_time=datetime.now(),
        )
        self.db.add(tu)
        await self.db.flush()

        logger.info(f"向租户[{tenant.name}]添加用户[{user.username}]成功, role={data.role}")

    async def remove_tenant_user(self, tenant_id: int, user_id: int) -> None:
        """从租户移除用户

        参数:
        - tenant_id (int): 租户ID
        - user_id (int): 用户ID

        返回:
        - None
        """
        # 查找关联记录
        exist_stmt = (
            select(TenantUserModel)
            .where(
                TenantUserModel.user_id == user_id,
                TenantUserModel.tenant_id == tenant_id,
            )
            .limit(1)
        )
        result = await self.db.execute(exist_stmt)
        tu = result.scalar_one_or_none()
        if not tu:
            raise CustomException(msg="该用户未关联此租户")

        # 不允许移除租户最后一个 owner
        if tu.role == "owner":
            count_result = await self.db.execute(
                select(func.count())
                .select_from(TenantUserModel)
                .where(
                    TenantUserModel.tenant_id == tenant_id,
                    TenantUserModel.role == "owner",
                ),
            )
            owner_count = count_result.scalar() or 0
            if owner_count <= 1:
                raise CustomException(msg="租户至少需要保留一个拥有者(owner)")

        await self.db.delete(tu)
        await self.db.flush()

        logger.info(f"从租户[{tenant_id}]移除用户[{user_id}]成功")

    async def get_quota(self, tenant_id: int) -> dict:
        """获取租户配额（从关联套餐读取，系统租户返回无限配额）

        参数:
        - tenant_id (int): 租户ID

        返回:
        - dict: 配额信息
        """
        if tenant_id == 1:
            return {
                "tenant_id": 1,
                "max_users": 999999,
                "max_roles": 999999,
                "max_storage_mb": 999999,
                "max_depts": 999999,
                "package_name": "系统租户(无限)",
            }
        tenant = await TenantCRUD(self.auth, self.db).get(id=tenant_id)
        if not tenant:
            raise CustomException(msg="该数据不存在")
        if not tenant.package_id:
            return {
                "tenant_id": tenant.id,
                "max_users": 0,
                "max_roles": 0,
                "max_storage_mb": 0,
                "max_depts": 0,
                "package_name": "未绑定套餐",
            }

        pkg = await PackageCRUD(self.auth, self.db).get(id=tenant.package_id)
        if not pkg:
            return {
                "tenant_id": tenant.id,
                "max_users": 0,
                "max_roles": 0,
                "max_storage_mb": 0,
                "max_depts": 0,
                "package_name": "套餐已删除",
            }
        return {
            "tenant_id": tenant.id,
            "max_users": pkg.max_users,
            "max_roles": pkg.max_roles,
            "max_depts": pkg.max_depts,
            "max_storage_mb": getattr(pkg, "max_storage_mb", 0),
            "package_name": pkg.name,
        }

    async def check_quota(self, tenant_id: int, resource_type: str) -> None:
        """检查租户配额是否充足，不足时抛出异常（系统租户跳过检查）"""
        if tenant_id == 1:
            return
        from sqlalchemy import func, select

        tenant = await TenantCRUD(self.auth, self.db).get(id=tenant_id)
        if not tenant or not tenant.package_id:
            return

        pkg = await PackageCRUD(self.auth, self.db).get(id=tenant.package_id)
        if not pkg:
            return

        # resource_type → (model_class, label, max_field)
        resource_map: dict[str, tuple[Any, str, str]] = {}

        resource_map["user"] = (UserModel, "用户", "max_users")
        resource_map["role"] = (RoleModel, "角色", "max_roles")
        resource_map["dept"] = (DeptModel, "部门", "max_depts")

        entry = resource_map.get(resource_type)
        if not entry:
            return  # storage 和未知类型跳过
        model_cls, label, max_field = entry

        max_limit = getattr(pkg, max_field, None)
        if max_limit is None or max_limit == 0:
            return

        count_stmt = (
            select(func.count())
            .select_from(model_cls)
            .where(
                model_cls.tenant_id == tenant_id,
                model_cls.is_deleted.is_(False),
            )
        )
        result = await self.db.execute(count_stmt)
        current_count = result.scalar() or 0

        if current_count >= max_limit:
            raise CustomException(msg=f"租户{label}数量已达套餐上限（{max_limit}），无法继续创建")

    async def get_config(self, tenant_id: int) -> dict:
        """获取租户所有配置（从租户主表读取，返回原始 dict 供内部使用）

        参数:
        - tenant_id (int): 租户ID

        返回:
        - dict: 配置字典
        """
        tenant = await TenantCRUD(self.auth, self.db).get(id=tenant_id)
        if not tenant:
            raise CustomException(msg="该数据不存在")

        config = {field: getattr(tenant, field, None) for field in self.CONFIG_FIELDS}
        return config

    @staticmethod
    def _config_to_items(config: dict) -> list[TenantConfigOutSchema]:
        """将配置字典转换为结构化列表"""
        return [TenantConfigOutSchema(config_key=k, config_value=str(v) if v is not None else None) for k, v in config.items()]

    async def get_config_items(self, tenant_id: int) -> list[TenantConfigOutSchema]:
        return TenantService._config_to_items(await self.get_config(tenant_id))

    @staticmethod
    async def get_config_cache(redis: Redis, tenant_id: int) -> dict:
        """从 Redis 缓存获取租户配置，缓存未命中则从 DB 加载并回写缓存

        参数:
        - redis (Redis): Redis 客户端实例
        - tenant_id (int): 租户ID

        返回:
        - dict: 租户配置字典
        """
        redis_key = f"{RedisInitKeyConfig.TENANT_CONFIG.key}:{tenant_id}"
        redis_config = await RedisCURD(redis).get(key=redis_key)

        if redis_config:
            try:
                return json.loads(redis_config)
            except Exception as e:
                logger.error(f"解析租户配置数据失败: {e}")

        logger.info(f"Redis 中没有租户[{tenant_id}]配置数据，从数据库中加载")
        async with async_db_session() as session, session.begin():
            _auth = AuthSchema(check_data_scope=False)
            svc = TenantService(_auth, session)
            config = await svc.get_config(tenant_id)
            await TenantService._sync_configs_to_redis(redis, tenant_id, config)
            logger.info("✅ 已从数据库加载租户配置到缓存")

        return config

    @staticmethod
    async def get_config_cache_items(redis: Redis, tenant_id: int) -> list[TenantConfigOutSchema]:
        return TenantService._config_to_items(await TenantService.get_config_cache(redis, tenant_id))

    @staticmethod
    async def _sync_configs_to_redis(redis: Redis, tenant_id: int, config: dict) -> None:
        """将租户配置写入 Redis 缓存"""
        redis_key = f"{RedisInitKeyConfig.TENANT_CONFIG.key}:{tenant_id}"
        value = json.dumps(config, ensure_ascii=False)
        await RedisCURD(redis).set(key=redis_key, value=value, expire=None)

    @staticmethod
    async def _del_configs_from_redis(redis: Redis, tenant_id: int) -> None:
        """删除租户配置的 Redis 缓存"""
        redis_key = f"{RedisInitKeyConfig.TENANT_CONFIG.key}:{tenant_id}"
        await RedisCURD(redis).delete(redis_key)

    async def update_config(self, redis: Redis, tenant_id: int, config: dict) -> list[TenantConfigOutSchema]:
        """更新租户配置（同步 Redis 缓存）

        参数:
        - redis (Redis): Redis 客户端
        - tenant_id (int): 租户ID
        - config (dict): 配置字典

        返回:
        - list[TenantConfigOutSchema]: 更新后的配置项列表
        """
        tenant = await TenantCRUD(self.auth, self.db).get(id=tenant_id)
        if not tenant:
            raise CustomException(msg="该数据不存在")

        for field in self.CONFIG_FIELDS:
            if field in config:
                setattr(tenant, field, config[field])

        await self.db.flush()

        # 刷新 DB 数据并同步到 Redis
        new_config = await self.get_config(tenant_id)
        await TenantService._sync_configs_to_redis(redis, tenant_id, new_config)
        logger.info(f"租户[{tenant_id}]配置已更新")
        return TenantService._config_to_items(new_config)

    @staticmethod
    async def init_cache(redis: Redis) -> None:
        """初始化所有租户配置到 Redis 缓存（应用启动时调用）。

        参数:
        - redis (Redis): Redis 客户端实例

        返回:
        - None
        """
        async with async_db_session() as session, session.begin():
            stmt = select(TenantModel)
            result = await session.execute(stmt)
            tenants = result.scalars().all()

            for tenant in tenants:
                config = {field: getattr(tenant, field, None) for field in TenantService.CONFIG_FIELDS}

                await TenantService._sync_configs_to_redis(redis, tenant.id, config)
                logger.info(f"✅ 租户[{tenant.name}](id={tenant.id}) 配置已缓存到 Redis")

    async def renew(self, tenant_id: int, end_time: str) -> TenantOutSchema:
        """租户续期：延长 end_time 并恢复为 active 状态

        仅 active(0)/grace(1)/suspended(2) 状态可续期。
        expired(4)/frozen(3)/archived(5) 不可续期。

        参数:
        - tenant_id (int): 租户ID
        - end_time (str): 新的结束时间

        返回:
        - dict: 更新后的租户信息
        """
        tenant = await TenantCRUD(self.auth, self.db).get(id=tenant_id)
        if not tenant:
            raise CustomException(msg="该数据不存在")

        if tenant.status not in (0, 1, 2):
            status_labels = {0: "正常", 1: "宽限期", 2: "暂停", 3: "冻结", 4: "过期", 5: "归档"}
            current_label = status_labels.get(tenant.status, str(tenant.status))
            raise CustomException(msg=f"当前租户状态为「{current_label}」，仅正常/宽限期/暂停状态可续期")

        new_end = datetime.fromisoformat(end_time) if isinstance(end_time, str) else end_time
        if new_end <= datetime.now():
            raise CustomException(msg="续期结束时间必须晚于当前时间")

        tenant.end_time = new_end
        tenant.status = 0
        tenant.grace_start_time = None

        await self.db.flush()
        logger.info(f"租户[{tenant.name}]续期成功, 新的结束时间: {end_time}")

        return TenantOutSchema.model_validate(tenant)

    async def package_change_preview(self, tenant_id: int, new_package_id: int) -> PackageChangePreviewOut:
        """套餐变更影响预览

        返回受影响角色、菜单清单、配额对比等，供超管确认后再执行变更。

        参数:
        - tenant_id (int): 租户ID
        - new_package_id (int): 目标套餐ID

        返回:
        - PackageChangePreviewOut: 预览结果
        """
        from sqlalchemy import func, select

        tenant = await TenantCRUD(self.auth, self.db).get(id=tenant_id)
        if not tenant:
            raise CustomException(msg="该数据不存在")

        new_package = await PackageCRUD(self.auth, self.db).get(id=new_package_id)
        if not new_package:
            raise CustomException(msg="该数据不存在")

        # 当前可用菜单
        current_menu_ids = set(await PackageService(self.auth, self.db).get_tenant_available_menu_ids(tenant_id))

        # 新套餐可用菜单（直接取套餐菜单，不再包含自定义授权）
        new_menu_ids = set(await PackageService(self.auth, self.db).get_package_menu_ids(new_package_id))
        final_menu_ids = new_menu_ids  # 不再合并租户自定义菜单

        # 差异计算
        removed_ids = current_menu_ids - final_menu_ids
        added_ids = final_menu_ids - current_menu_ids

        removed_menus = []
        added_menus = []
        if removed_ids:
            menu_stmt = select(MenuModel).where(MenuModel.id.in_(removed_ids))
            menu_result = await self.db.execute(menu_stmt)
            removed_menus = [{"id": m.id, "name": m.name, "route_path": m.route_path} for m in menu_result.scalars().all()]
        if added_ids:
            menu_stmt = select(MenuModel).where(MenuModel.id.in_(added_ids))
            menu_result = await self.db.execute(menu_stmt)
            added_menus = [{"id": m.id, "name": m.name, "route_path": m.route_path} for m in menu_result.scalars().all()]

        # 受影响角色
        role_stmt = select(RoleModel).where(RoleModel.tenant_id == tenant_id)
        role_result = await self.db.execute(role_stmt)
        roles = role_result.scalars().all()

        affected_roles = []
        total_affected_users = 0
        for role in roles:
            # 查该角色下有多少菜单会被移除
            role_menu_stmt = select(RoleMenusModel.menu_id).where(RoleMenusModel.role_id == role.id)
            rm_result = await self.db.execute(role_menu_stmt)
            role_menu_ids = {row[0] for row in rm_result.all()}
            affected_menu_count = len(role_menu_ids & removed_ids)

            # 查该角色下用户数
            user_count_stmt = select(func.count()).select_from(UserModel).join(UserModel.roles).where(RoleModel.id == role.id)
            uc_result = await self.db.execute(user_count_stmt)
            user_count = uc_result.scalar() or 0

            affected_roles.append(
                {
                    "id": role.id,
                    "name": role.name,
                    "code": role.code,
                    "affected_menu_count": affected_menu_count,
                    "user_count": user_count,
                },
            )
            total_affected_users += user_count

        # 配额对比（从套餐读取）
        old_pkg = None
        if tenant.package_id:
            old_pkg = await PackageCRUD(self.auth, self.db).get(id=tenant.package_id)
        quota_changes = {
            "max_users": {
                "current": old_pkg.max_users if old_pkg else 0,
                "new": new_package.max_users,
            },
            "max_roles": {
                "current": old_pkg.max_roles if old_pkg else 0,
                "new": new_package.max_roles,
            },
            "max_depts": {
                "current": old_pkg.max_depts if old_pkg else 0,
                "new": new_package.max_depts,
            },
        }

        return PackageChangePreviewOut(
            new_package_id=new_package.id,
            new_package_name=new_package.name,
            affected_roles=affected_roles,
            removed_menus=removed_menus,
            added_menus=added_menus,
            quota_changes=quota_changes,
            total_affected_users=total_affected_users,
        )

    @staticmethod
    async def check_tenant_expiry() -> None:
        """定时任务：多阶段租户到期自动处理

        PRD §9 到期阶段：
          grace(1)   → 到期后第 1-7 天，仅提醒
          suspended(2) → 到期后第 8-14 天，禁用登录
          frozen(3)     → 到期后第 15-30 天，只读模式
          expired(4)    → 第 31 天起，归档候选
        """
        from sqlalchemy import text

        now = datetime.now()

        async with async_db_session() as session:
            # 获取所有已过期的活跃租户（status=0）
            rows = await session.execute(
                text("SELECT id, name, end_time, status FROM platform_tenant WHERE status = '0' AND end_time IS NOT NULL AND end_time < :now"),
                {"now": now},
            )
            expired_tenants = rows.fetchall()

            for t in expired_tenants:
                tenant_id, tenant_name, end_time, cur_status = t
                days_past = (now - end_time).days if end_time else 0

                if days_past <= 7:
                    new_status, label = 1, "宽限期"
                elif days_past <= 14:
                    new_status, label = 2, "已停用"
                elif days_past <= 30:
                    new_status, label = 3, "已冻结"
                else:
                    new_status, label = 4, "已过期"

                if new_status == cur_status:
                    continue

                await session.execute(
                    text("UPDATE platform_tenant SET status = :s WHERE id = :tid"),
                    {"s": new_status, "tid": tenant_id},
                )
                logger.info(f"租户状态切换: id={tenant_id} name={tenant_name} status={cur_status}→{new_status} ({label})")

            await session.commit()

        logger.info(f"到期检查完成，处理了 {len(expired_tenants)} 个过期租户")

    @staticmethod
    async def clean_expired_tenants() -> None:
        """定时任务：将过期超 90 天租户归档，清理旧审计日志（每月 1 号 02:00）"""
        from datetime import datetime, timedelta

        from sqlalchemy import text

        cutoff = datetime.now() - timedelta(days=90)

        async with async_db_session() as session:
            # 归档过期租户
            result = await session.execute(
                text("SELECT COUNT(*) FROM platform_tenant WHERE status = '4' AND end_time < :cutoff"),
                {"cutoff": cutoff},
            )
            count = result.scalar() or 0
            if count > 0:
                await session.execute(
                    text("UPDATE platform_tenant SET status = '5' WHERE status = '4' AND end_time < :cutoff"),
                    {"cutoff": cutoff},
                )
                await session.commit()
                logger.info(f"已将 {count} 个过期超过 90 天的租户标记为归档")

    @classmethod
    async def get_available_packages(cls, auth: AuthSchema, db: AsyncSession, tenant_id: int) -> PackageAvailableOut:
        """获取可选套餐列表

        参数:
        - auth (AuthSchema): 认证信息模型
        - db (AsyncSession): 数据库会话
        - tenant_id (int): 租户ID

        返回:
        - PackageAvailableOut: 可选套餐列表
        """
        tenant = await db.get(TenantModel, tenant_id)
        current_pkg_id = tenant.package_id if tenant else None

        # 一次性获取当前套餐价格（可能未启用，不在后续结果中）
        current_price: int | None = None
        if current_pkg_id:
            cp = await db.get(PackageModel, current_pkg_id)
            current_price = cp.price if cp else 0

        stmt = select(PackageModel).where(PackageModel.status == 0).order_by(PackageModel.price)
        result = await db.execute(stmt)
        packages = result.scalars().all()

        items: list[PackageAvailableItem] = []
        for pkg in packages:
            is_current = pkg.id == current_pkg_id
            actions: list[PackageAction] = []
            if is_current:
                actions = ["renew"]
            elif current_pkg_id is None:
                actions = ["buy"]
            elif current_price is not None:
                actions = ["upgrade"] if pkg.price > current_price else ["downgrade"]

            items.append(
                PackageAvailableItem(
                    id=pkg.id,
                    name=pkg.name,
                    price=pkg.price,
                    period=pkg.period,
                    trial_days=pkg.trial_days,
                    max_users=pkg.max_users,
                    max_roles=pkg.max_roles,
                    max_depts=pkg.max_depts,
                    max_storage_mb=pkg.max_storage_mb,
                    description=pkg.description,
                    is_current=is_current,
                    available_actions=actions,
                ),
            )

        return PackageAvailableOut(
            current_package_id=current_pkg_id,
            packages=items,
        )

    @classmethod
    async def preview_package_change(cls, auth: AuthSchema, db: AsyncSession, tenant_id: int, target_package_id: int) -> PackagePreviewOut:
        """套餐变更预览（委托给 package_change_preview 并映射输出）"""
        svc = cls(auth, db)
        preview = await svc.package_change_preview(tenant_id, target_package_id)

        tenant = await db.get(TenantModel, tenant_id)
        target_pkg = await db.get(PackageModel, target_package_id)

        current_pkg = None
        if tenant and tenant.package_id:
            current_pkg = await db.get(PackageModel, tenant.package_id)

        # 确定操作类型
        if not tenant or not tenant.package_id:
            action = "buy"
        elif current_pkg and target_pkg and target_pkg.price > current_pkg.price:
            action = "upgrade"
        elif current_pkg and target_pkg and target_pkg.price < current_pkg.price:
            action = "downgrade"
        else:
            action = "renew"

        return PackagePreviewOut(
            current_package=current_pkg.name if current_pkg else "",
            target_package=target_pkg.name if target_pkg else "",
            action=action,
            amount=target_pkg.price if target_pkg else 0,
            period=target_pkg.period if target_pkg else "",
            gained_menus=preview.added_menus,
            lost_menus=preview.removed_menus,
            affected_roles=[r.get("name", "") for r in preview.affected_roles],
            affected_users=preview.total_affected_users,
        )

    @classmethod
    async def create_self_order(cls, auth: AuthSchema, db: AsyncSession, tenant_id: int, data: SelfOrderCreate) -> SelfOrderOut:
        """创建自助订单（套餐购买/续费/升级/降级；免费订单自动激活）

        参数:
        - auth (AuthSchema): 认证信息模型
        - db (AsyncSession): 数据库会话
        - tenant_id (int): 租户ID
        - data (SelfOrderCreate): 自助订单创建参数

        返回:
        - SelfOrderOut: 自助订单创建结果
        """
        tenant = await db.get(TenantModel, tenant_id)
        if not tenant:
            raise CustomException(msg="该数据不存在")
        if tenant.status not in (0, 1, 2):
            raise CustomException(msg="租户状态不允许操作")

        pkg = await db.get(PackageModel, data.package_id)
        if not pkg or pkg.status == 1:
            raise CustomException(msg="该数据不存在")

        # 校验 order_type 与当前套餐状态的一致性：
        # - 未购套餐时只能 buy / renew（不能用 upgrade/downgrade）
        # - 已有套餐时禁止 buy（应走 upgrade 等）
        if not tenant.package_id:
            if data.order_type not in ("buy", "renew"):
                raise CustomException(msg="当前租户未购买套餐，只能 buy 或 renew")
        else:
            if data.order_type == "buy":
                raise CustomException(msg="该租户已存在套餐，请使用 upgrade/renew/downgrade")

        amount = pkg.price

        from app.api.v1.module_platform.order.service import PaymentService, _generate_order_no

        order = await OrderCRUD(auth, db).create(
            OrderCreateInternalSchema(
                order_no=_generate_order_no(),
                tenant_id=tenant_id,
                package_id=data.package_id,
                order_type=data.order_type,
                amount=amount,
                expire_time=datetime.now() + timedelta(minutes=15),
            ),
        )
        await db.flush()

        # 免费订单自动激活
        if amount == 0:
            await OrderCRUD(auth, db).update(
                order.id,
                OrderUpdateInternalSchema(status=1, pay_method="free", pay_time=datetime.now()),
            )
            await PaymentService._activate_tenant_package(auth, db, order)

        logger.info(f"自助订单创建: order_no={order.order_no} tenant={tenant_id} amount={amount}")
        return SelfOrderOut(
            order_id=order.id,
            order_no=order.order_no,
            amount=amount,
            need_pay=amount > 0,
        )

    @classmethod
    async def get_self_order_list(
        cls,
        auth: AuthSchema,
        db: AsyncSession,
        tenant_id: int,
        page_no: int = 1,
        page_size: int = 20,
        order_by: list[dict] | None = None,
    ) -> SelfOrderListOut:
        """我的订单列表

        参数:
        - auth (AuthSchema): 认证信息模型
        - db (AsyncSession): 数据库会话
        - tenant_id (int): 租户ID
        - page_no (int): 页码
        - page_size (int): 每页数量
        - order_by (list[dict] | None): 排序参数

        返回:
        - SelfOrderListOut: 订单分页列表
        """
        offset = (page_no - 1) * page_size
        page_result = await OrderCRUD(auth, db).page(
            offset=offset,
            limit=page_size,
            order_by=order_by or [{"created_time": "desc"}],
            search={"tenant_id": tenant_id},
        )

        # 批量查询关联套餐，避免 N+1
        package_ids = [o.package_id for o in page_result.items if hasattr(o, "package_id") and o.package_id]
        pkg_map: dict[int, str] = {}
        if package_ids:
            pkg_result = await db.execute(select(PackageModel.id, PackageModel.name).where(PackageModel.id.in_(package_ids)))
            pkg_map = {row[0]: row[1] for row in pkg_result.all()}

        items = []
        for o in page_result.items:
            pkg_name = pkg_map.get(o.package_id, "") if hasattr(o, "package_id") and o.package_id else ""
            items.append(
                SelfOrderListItem(
                    id=o.id,
                    order_no=o.order_no,
                    package_name=pkg_name,
                    order_type=o.order_type,
                    amount=o.amount,
                    status=o.status,
                    pay_method=o.pay_method,
                    pay_time=o.pay_time.isoformat() if o.pay_time else None,
                    created_at=o.created_time.isoformat() if o.created_time else None,
                ),
            )

        return SelfOrderListOut(
            items=items,
            total=page_result.total,
            page_no=page_no,
            page_size=page_size,
        )

    @classmethod
    async def get_self_order_detail(cls, auth: AuthSchema, db: AsyncSession, order_id: int) -> SelfOrderDetailOut:
        """订单详情

        参数:
        - auth (AuthSchema): 认证信息模型
        - db (AsyncSession): 数据库会话
        - order_id (int): 订单ID

        返回:
        - SelfOrderDetailOut: 订单详情
        """
        order = await OrderCRUD(auth, db).get_or_404(id=order_id, msg="该数据不存在")

        pkg_name = ""
        if order.package_id:
            p = await db.get(PackageModel, order.package_id)
            if p:
                pkg_name = p.name

        return SelfOrderDetailOut(
            id=order.id,
            order_no=order.order_no,
            package_id=order.package_id,
            package_name=pkg_name,
            amount=order.amount,
            order_type=OrderTypeEnum(order.order_type),
            status=order.status,
            pay_method=order.pay_method,
            pay_time=order.pay_time.isoformat() if order.pay_time else None,
            created_at=order.created_time.isoformat() if order.created_time else None,
        )

    @classmethod
    async def get_workspace_data(cls, auth: AuthSchema, db: AsyncSession, tenant_id: int) -> WorkspaceOut:
        """获取租户工作台概览（租户信息、套餐、配额用量、近期订单）

        参数:
        - auth (AuthSchema): 认证信息模型
        - db (AsyncSession): 数据库会话
        - tenant_id (int): 租户ID

        返回:
        - WorkspaceOut: 工作台概览数据
        """
        tenant = await db.get(TenantModel, tenant_id)
        if not tenant:
            return WorkspaceOut(
                tenant=WorkspaceTenantInfo(id=0, name="", code="", status=0, status_label="未知"),
                quota=WorkspaceQuotaInfo(),
            )

        package = None
        if tenant.package_id:
            package = await db.get(PackageModel, tenant.package_id)

        async def _count(model_cls) -> int:
            stmt = (
                select(func.count())
                .select_from(model_cls)
                .where(
                    model_cls.tenant_id == tenant_id,
                    model_cls.is_deleted.is_(False),
                )
            )
            return (await db.execute(stmt)).scalar() or 0

        user_count = await _count(UserModel)
        role_count = await _count(RoleModel)
        dept_count = await _count(DeptModel)

        now = datetime.now()
        days_remaining = (tenant.end_time - now).days if tenant.end_time else 0

        status_labels = {
            "0": "正常",
            "1": "宽限期",
            "2": "已暂停",
            "3": "已冻结",
            "4": "已过期",
            "5": "已归档",
        }

        orders_stmt = select(OrderModel).where(OrderModel.tenant_id == tenant_id).order_by(OrderModel.created_time.desc()).limit(5)
        orders_result = await db.execute(orders_stmt)
        recent_orders = []
        for o in orders_result.scalars().all():
            recent_orders.append(
                WorkspaceOrderItem(
                    id=o.id,
                    order_no=o.order_no,
                    amount=o.amount,
                    order_type=OrderTypeEnum(o.order_type),
                    status=o.status,
                    created_at=o.created_time.isoformat() if o.created_time else None,
                ),
            )

        return WorkspaceOut(
            tenant=WorkspaceTenantInfo(
                id=tenant.id,
                name=tenant.name,
                code=tenant.code,
                status=tenant.status,
                status_label=status_labels.get(str(tenant.status), "未知"),
                start_time=tenant.start_time.isoformat() if tenant.start_time else None,
                end_time=tenant.end_time.isoformat() if tenant.end_time else None,
                days_remaining=max(days_remaining, 0),
            ),
            package=WorkspacePackageInfo(
                id=package.id,
                name=package.name,
                price=package.price,
                period=package.period,
                max_users=package.max_users,
                max_roles=package.max_roles,
                max_depts=package.max_depts,
            )
            if package
            else None,
            quota=WorkspaceQuotaInfo(
                max_users=package.max_users if package else 0,
                max_roles=package.max_roles if package else 0,
                max_depts=package.max_depts if package else 0,
                current_users=user_count,
                current_roles=role_count,
                current_depts=dept_count,
                usage_percent=WorkspaceUsagePercent(
                    users=round(user_count / package.max_users * 100, 1) if package and package.max_users > 0 else 0,
                    roles=round(role_count / package.max_roles * 100, 1) if package and package.max_roles > 0 else 0,
                    depts=round(dept_count / package.max_depts * 100, 1) if package and package.max_depts > 0 else 0,
                ),
            ),
            recent_orders=recent_orders,
        )
