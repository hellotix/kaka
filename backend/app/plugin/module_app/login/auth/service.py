"""C端登录认证服务：登录、注册、令牌、会话与密码管理。"""

import uuid
from datetime import UTC, datetime
from typing import Any

import ua_parser
from fastapi import Request
from redis.asyncio.client import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import RET
from app.config.setting import settings
from app.core.base_schema import AuthSchema
from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import logger
from app.core.redis_crud import RedisCURD
from app.utils.ip_local_util import IpLocalUtil, get_client_ip
from app.utils.password_util import PwdUtil

from ..core.constants import (
    ACCESS_TOKEN_EXPIRE_SECONDS,
    PASSWORD_LOCK_SECONDS,
    PASSWORD_MAX_FAIL_TIMES,
    REFRESH_TOKEN_EXPIRE_SECONDS,
    SMS_LOGIN_AUTO_REGISTER,
    SMS_REGISTER_ENABLE,
    AppLoginStatus,
    AppLoginType,
    AppPlatform,
    AppRegisterType,
    AppSmsScene,
    AppTokenType,
    password_fail_key,
)
from ..core.security import create_app_token, decode_app_token, unauthorized
from ..core.session import AppSessionInfo, AppSessionStore
from ..user.crud import AppUserCRUD, AppUserOauthCRUD
from ..user.model import AppUserModel
from ..user.schema import AppUserBriefSchema
from .crud import AppLoginLogCRUD
from .schema import (
    AppLoginLogCreateSchema,
    AppLoginOutSchema,
    AppPasswordLoginSchema,
    AppRefreshTokenSchema,
    AppRegisterSchema,
    AppSmsLoginSchema,
    AppTokenOutSchema,
)
from .sms import SmsService
from .third_party import ThirdPartyCredential, ThirdPartyUserInfo, get_authenticator


async def write_login_log(**data: Any) -> None:
    """写入C端登录日志。

    使用独立会话，保证登录失败抛异常回滚业务事务时日志仍然落库。
    """
    try:
        async with async_db_session() as session, session.begin():
            await AppLoginLogCRUD(AuthSchema(), session).create(data=AppLoginLogCreateSchema(**data))
    except Exception as e:
        logger.error(f"C端登录日志写入失败: {e!s}")


async def collect_request_meta(request: Request, redis: Redis) -> dict[str, Any]:
    """采集请求端信息（IP、归属地、UA 解析结果）。"""
    user_agent = request.headers.get("user-agent") or ""
    ua_result = ua_parser.parse(user_agent)
    ip = get_client_ip(request)
    location = await IpLocalUtil.resolve_location_for_log(redis, ip)
    return {
        "login_ip": ip or None,
        "login_location": location,
        "device_os": ua_result.os.family if ua_result.os else "Unknown",
        "device_browser": ua_result.user_agent.family if ua_result.user_agent else "Unknown",
        "user_agent": user_agent[:500] or None,
    }


class AppLoginService:
    """C端登录服务层"""

    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        """初始化服务层

        参数:
        - db (AsyncSession): 数据库会话
        - redis (Redis): Redis 连接
        """
        self.db = db
        self.redis = redis
        self.cache = RedisCURD(redis)
        self.users = AppUserCRUD(AuthSchema(), db)
        self.oauths = AppUserOauthCRUD(AuthSchema(), db)
        self.sessions = AppSessionStore(redis)
        self.sms = SmsService(redis)

    # ── 登录 ──────────────────────────────────────────────────────────

    async def login_by_password(self, data: AppPasswordLoginSchema, request: Request) -> AppLoginOutSchema:
        """账号密码登录（账号为手机号或用户名）。

        参数:
        - data (AppPasswordLoginSchema): 登录参数。
        - request (Request): 请求对象，用于采集登录端信息。

        返回:
        - AppLoginOutSchema: 令牌与用户信息。

        异常:
        - CustomException: 账号或密码错误、触发锁定、账号被禁用。
        """
        account = data.account
        meta = await collect_request_meta(request, self.redis)
        fail_key = password_fail_key(account)

        fail_times = int(await self.cache.get(fail_key) or 0)
        if fail_times >= PASSWORD_MAX_FAIL_TIMES:
            ttl = await self.cache.ttl(key=fail_key)
            raise CustomException(msg=f"密码连续错误次数过多，请 {max(int(ttl), 0)} 秒后再试")

        user = await self.users.get_by_account(account)
        if not user:
            await self._log_failure(account=account, msg="账号或密码错误", platform=data.platform, login_type=AppLoginType.PASSWORD, meta=meta)
            raise CustomException(msg="账号或密码错误")

        if not user.password:
            msg = "该账号未设置密码，请使用短信验证码登录"
            await self._log_failure(account=account, msg=msg, platform=data.platform, login_type=AppLoginType.PASSWORD, meta=meta, user=user)
            raise CustomException(msg=msg)

        if not PwdUtil.verify_password(plain_password=data.password, password_hash=user.password):
            count = await self.redis.incr(fail_key)
            if count == 1:
                await self.redis.expire(fail_key, PASSWORD_LOCK_SECONDS)
            await self._log_failure(account=account, msg="账号或密码错误", platform=data.platform, login_type=AppLoginType.PASSWORD, meta=meta, user=user)
            raise CustomException(msg="账号或密码错误")

        await self.cache.delete(fail_key)
        await self._ensure_enabled(user, account=account, platform=data.platform, login_type=AppLoginType.PASSWORD, meta=meta)

        return await self._issue(user=user, platform=data.platform, login_type=AppLoginType.PASSWORD, meta=meta)

    async def login_by_sms(self, data: AppSmsLoginSchema, request: Request) -> AppLoginOutSchema:
        """短信验证码登录，未注册手机号按配置自动注册。

        参数:
        - data (AppSmsLoginSchema): 登录参数。
        - request (Request): 请求对象。

        返回:
        - AppLoginOutSchema: 令牌与用户信息。
        """
        await self.sms.verify_code(mobile=data.mobile, code=data.code, scene=AppSmsScene.LOGIN)

        meta = await collect_request_meta(request, self.redis)
        user = await self.users.get(mobile=data.mobile)
        is_new_user = False

        if not user:
            if not SMS_LOGIN_AUTO_REGISTER:
                await self._log_failure(account=data.mobile, msg="该手机号尚未注册", platform=data.platform, login_type=AppLoginType.SMS, meta=meta)
                raise CustomException(msg="该手机号尚未注册")
            user = await self.create_user(
                mobile=data.mobile,
                nickname=self._default_nickname(data.mobile),
                platform=data.platform,
                register_type=AppRegisterType.SMS,
                ip=meta.get("login_ip"),
            )
            is_new_user = True

        await self._ensure_enabled(user, account=data.mobile, platform=data.platform, login_type=AppLoginType.SMS, meta=meta)
        return await self._issue(user=user, platform=data.platform, login_type=AppLoginType.SMS, meta=meta, is_new_user=is_new_user)

    async def login_by_third_party(
        self,
        credential: ThirdPartyCredential,
        provider: str,
        platform: AppPlatform,
        request: Request,
    ) -> AppLoginOutSchema:
        """第三方登录（微信、苹果等），首次登录自动建号并绑定。

        参数:
        - credential (ThirdPartyCredential): 第三方登录凭证。
        - provider (str): 渠道标识。
        - platform (AppPlatform): 登录终端。
        - request (Request): 请求对象。

        返回:
        - AppLoginOutSchema: 令牌与用户信息。
        """
        authenticator = get_authenticator(provider)
        info = await authenticator.authenticate(credential)

        meta = await collect_request_meta(request, self.redis)
        login_type = AppLoginType.WECHAT if info.provider.startswith("wechat") else AppLoginType.APPLE
        register_type = AppRegisterType.WECHAT if login_type == AppLoginType.WECHAT else AppRegisterType.APPLE

        binding = await self.oauths.get_by_provider(provider=info.provider, openid=info.openid)
        is_new_user = False

        if binding:
            user = await self.users.get(id=binding.user_id)
            if not user:
                await self._log_failure(
                    account=info.openid,
                    msg="第三方账号绑定的用户不存在",
                    platform=platform,
                    login_type=login_type,
                    provider=info.provider,
                    meta=meta,
                )
                raise CustomException(msg="第三方账号绑定的用户不存在，请联系客服")
            await self._refresh_binding(binding.id, info)
        else:
            user = await self.users.get(mobile=info.mobile) if info.mobile else None
            if user:
                await self._create_binding(user_id=user.id, info=info)
            else:
                user = await self.create_user(
                    mobile=info.mobile,
                    email=info.email,
                    nickname=info.nickname or self._default_nickname(info.mobile),
                    avatar=info.avatar,
                    platform=platform,
                    register_type=register_type,
                    ip=meta.get("login_ip"),
                )
                await self._create_binding(user_id=user.id, info=info)
                is_new_user = True

        await self._ensure_enabled(
            user,
            account=info.openid,
            platform=platform,
            login_type=login_type,
            provider=info.provider,
            meta=meta,
        )
        return await self._issue(
            user=user,
            platform=platform,
            login_type=login_type,
            meta=meta,
            is_new_user=is_new_user,
            provider=info.provider,
        )

    async def register(self, data: AppRegisterSchema, request: Request) -> AppLoginOutSchema:
        """手机号 + 密码注册，注册成功后直接登录。

        参数:
        - data (AppRegisterSchema): 注册参数。
        - request (Request): 请求对象。

        返回:
        - AppLoginOutSchema: 令牌与用户信息。
        """
        if not SMS_REGISTER_ENABLE:
            raise CustomException(msg="注册功能已关闭，请联系管理员")
        if not data.code:
            raise CustomException(msg="请输入短信验证码")

        await self.sms.verify_code(mobile=data.mobile, code=data.code, scene=AppSmsScene.REGISTER)

        if await self.users.get(mobile=data.mobile):
            raise CustomException(msg="该手机号已注册，请直接登录")
        if data.username and await self.users.get(username=data.username):
            raise CustomException(msg="该用户名已被占用")

        meta = await collect_request_meta(request, self.redis)
        user = await self.create_user(
            mobile=data.mobile,
            username=data.username,
            password=data.password,
            nickname=data.nickname or self._default_nickname(data.mobile),
            platform=data.platform,
            register_type=AppRegisterType.PASSWORD,
            ip=meta.get("login_ip"),
        )
        return await self._issue(user=user, platform=data.platform, login_type=AppLoginType.PASSWORD, meta=meta, is_new_user=True)

    # ── 令牌与会话 ────────────────────────────────────────────────────

    async def refresh_token(self, data: AppRefreshTokenSchema) -> AppTokenOutSchema:
        """使用刷新令牌换取新的访问令牌与刷新令牌。

        参数:
        - data (AppRefreshTokenSchema): 刷新令牌参数。

        返回:
        - AppTokenOutSchema: 新令牌。

        异常:
        - CustomException: 刷新令牌非法、已被使用过、会话过期或账号被禁用。
        """
        payload = decode_app_token(data.refresh_token, token_type=AppTokenType.REFRESH)
        info = await self.sessions.get(payload.sub)
        if not info:
            raise unauthorized("登录已过期，请重新登录")

        # 刷新令牌一次性使用：与 Redis 留档比对，旧令牌刷新后立即作废
        stored_refresh = await self.sessions.get_token(info.session_id, token_type=AppTokenType.REFRESH.value)
        if stored_refresh and stored_refresh != data.refresh_token:
            raise unauthorized("刷新令牌已失效，请重新登录")

        user = await self.users.get(id=info.user_id)
        if not user:
            raise unauthorized("用户不存在，请重新登录")
        if user.status == 1:
            raise CustomException(msg="账号已被禁用，请联系客服", code=RET.FORBIDDEN.code, status_code=403)

        access_token = create_app_token(
            session_id=info.session_id,
            user_id=user.id,
            platform=info.platform,
            token_type=AppTokenType.ACCESS,
            expire_seconds=ACCESS_TOKEN_EXPIRE_SECONDS,
        )
        refresh_token = create_app_token(
            session_id=info.session_id,
            user_id=user.id,
            platform=info.platform,
            token_type=AppTokenType.REFRESH,
            expire_seconds=REFRESH_TOKEN_EXPIRE_SECONDS,
        )
        await self.sessions.update_token(info.session_id, access_token=access_token, refresh_token=refresh_token)
        await self.sessions.update_info(
            info.model_copy(update={"username": user.username, "nickname": user.nickname, "mobile": user.mobile, "avatar": user.avatar})
        )

        return AppTokenOutSchema(access_token=access_token, refresh_token=refresh_token, token_type=settings.TOKEN_TYPE)

    async def logout(self, session_id: str) -> None:
        """登出：销毁会话与全部令牌。

        参数:
        - session_id (str): 当前会话ID。
        """
        await self.sessions.remove(session_id)
        logger.info(f"C端用户登出成功: session_id={session_id}")

    async def list_sessions(self, user_id: int) -> list[AppSessionInfo]:
        """列出用户在线会话。"""
        return await self.sessions.list_by_user(user_id)

    async def remove_session(self, user_id: int, session_id: str) -> None:
        """下线指定会话（校验会话归属）。"""
        info = await self.sessions.get(session_id)
        if not info:
            raise CustomException(msg="会话不存在或已下线")
        if info.user_id != user_id:
            raise CustomException(msg="无权操作该会话", code=RET.FORBIDDEN.code, status_code=403)
        await self.sessions.remove(session_id)

    async def remove_other_sessions(self, user_id: int, current_session_id: str) -> int:
        """下线除当前会话外的全部会话，返回下线数量。"""
        return await self.sessions.remove_by_user(user_id, exclude_session_id=current_session_id)

    async def remove_all_sessions(self, user_id: int) -> int:
        """下线用户全部会话（后台强制下线/重置密码使用）。"""
        return await self.sessions.remove_by_user(user_id)

    # ── 密码 ──────────────────────────────────────────────────────────

    async def change_password(self, user: AppUserModel, *, old_password: str | None, new_password: str, current_session_id: str) -> None:
        """修改密码，成功后下线其他会话。

        参数:
        - user (AppUserModel): 当前登录用户。
        - old_password (str | None): 原密码，首次设置密码时可为空。
        - new_password (str): 新密码（明文，内部哈希存储）。
        - current_session_id (str): 当前会话ID，保留不下线。
        """
        if user.password:
            if not old_password:
                raise CustomException(msg="请输入原密码")
            if not PwdUtil.verify_password(plain_password=old_password, password_hash=user.password):
                raise CustomException(msg="原密码不正确")
        elif old_password:
            raise CustomException(msg="该账号尚未设置密码，无需填写原密码")

        await self.users.set(ids=[user.id], password=PwdUtil.hash_password(new_password))
        await self.sessions.remove_by_user(user.id, exclude_session_id=current_session_id)

    async def reset_password_by_sms(self, *, mobile: str, code: str, new_password: str) -> None:
        """短信验证码重置密码，成功后全端下线。

        参数:
        - mobile (str): 手机号。
        - code (str): 短信验证码。
        - new_password (str): 新密码。
        """
        await self.sms.verify_code(mobile=mobile, code=code, scene=AppSmsScene.RESET_PASSWORD)
        user = await self.users.get(mobile=mobile)
        if not user:
            raise CustomException(msg="该手机号尚未注册")
        await self.users.set(ids=[user.id], password=PwdUtil.hash_password(new_password))
        await self.sessions.remove_by_user(user.id)

    # ── 内部方法 ──────────────────────────────────────────────────────

    async def create_user(
        self,
        *,
        mobile: str | None = None,
        username: str | None = None,
        password: str | None = None,
        nickname: str = "",
        avatar: str | None = None,
        email: str | None = None,
        platform: AppPlatform | None = None,
        register_type: AppRegisterType = AppRegisterType.SMS,
        ip: str | None = None,
    ) -> AppUserModel:
        """创建C端用户（密码自动哈希）。

        参数:
        - mobile (str | None): 手机号。
        - username (str | None): 用户名。
        - password (str | None): 明文密码。
        - nickname (str): 昵称。
        - avatar (str | None): 头像。
        - email (str | None): 邮箱。
        - platform (AppPlatform | None): 注册终端。
        - register_type (AppRegisterType): 注册来源。
        - ip (str | None): 注册IP。

        返回:
        - AppUserModel: 新建的用户对象。
        """
        payload: dict[str, Any] = {
            "mobile": mobile,
            "username": username,
            "email": email,
            "nickname": nickname,
            "avatar": avatar,
            "status": 0,
            "register_type": register_type.value,
            "register_platform": platform.value if platform else None,
            "register_ip": ip,
        }
        if password:
            payload["password"] = PwdUtil.hash_password(password)
        return await self.users.create(data=payload)

    async def _issue(
        self,
        *,
        user: AppUserModel,
        platform: AppPlatform,
        login_type: AppLoginType,
        meta: dict[str, Any],
        is_new_user: bool = False,
        provider: str | None = None,
    ) -> AppLoginOutSchema:
        """签发令牌、写入会话与登录日志。"""
        session_id = str(uuid.uuid4())
        access_token = create_app_token(
            session_id=session_id,
            user_id=user.id,
            platform=platform.value,
            token_type=AppTokenType.ACCESS,
            expire_seconds=ACCESS_TOKEN_EXPIRE_SECONDS,
        )
        refresh_token = create_app_token(
            session_id=session_id,
            user_id=user.id,
            platform=platform.value,
            token_type=AppTokenType.REFRESH,
            expire_seconds=REFRESH_TOKEN_EXPIRE_SECONDS,
        )

        await self.sessions.save(
            AppSessionInfo(
                session_id=session_id,
                user_id=user.id,
                username=user.username,
                nickname=user.nickname,
                mobile=user.mobile,
                avatar=user.avatar,
                platform=platform.value,
                login_type=login_type.value,
                login_time=datetime.now(UTC),
                **meta,
            ),
            access_token=access_token,
            refresh_token=refresh_token,
        )
        await self.users.touch_login(user.id, platform=platform.value, ip=meta.get("login_ip"))
        await write_login_log(
            user_id=user.id,
            account=user.mobile or user.username,
            nickname=user.nickname,
            platform=platform.value,
            login_type=login_type.value,
            provider=provider,
            session_id=session_id,
            status=AppLoginStatus.SUCCESS.value,
            msg="登录成功",
            **meta,
        )

        logger.info(f"C端用户登录成功: user_id={user.id}, platform={platform.value}, login_type={login_type.value}")
        return AppLoginOutSchema(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type=settings.TOKEN_TYPE,
            session_id=session_id,
            is_new_user=is_new_user,
            user_info=AppUserBriefSchema.model_validate(user),
        )

    async def _ensure_enabled(
        self,
        user: AppUserModel,
        *,
        account: str | None,
        platform: AppPlatform,
        login_type: AppLoginType,
        meta: dict[str, Any],
        provider: str | None = None,
    ) -> None:
        """账号状态校验，禁用账号记录失败日志并抛出 403。"""
        if user.status != 1:
            return
        await self._log_failure(
            account=account,
            msg="账号已被禁用",
            platform=platform,
            login_type=login_type,
            provider=provider,
            meta=meta,
            user=user,
        )
        raise CustomException(msg="账号已被禁用，请联系客服", code=RET.FORBIDDEN.code, status_code=403)

    async def _log_failure(
        self,
        *,
        account: str | None,
        msg: str,
        platform: AppPlatform,
        login_type: AppLoginType,
        meta: dict[str, Any],
        provider: str | None = None,
        user: AppUserModel | None = None,
    ) -> None:
        """记录登录失败日志。"""
        await write_login_log(
            user_id=user.id if user else None,
            account=account,
            nickname=user.nickname if user else None,
            platform=platform.value,
            login_type=login_type.value,
            provider=provider,
            status=AppLoginStatus.FAILURE.value,
            msg=msg,
            **meta,
        )

    async def _create_binding(self, *, user_id: int, info: ThirdPartyUserInfo) -> None:
        """新增第三方绑定。"""
        await self.oauths.create(
            data={
                "user_id": user_id,
                "provider": info.provider,
                "openid": info.openid,
                "unionid": info.unionid,
                "nickname": info.nickname,
                "avatar": info.avatar,
                "last_login_time": datetime.now(UTC),
                "extra": info.raw or None,
            }
        )

    async def _refresh_binding(self, binding_id: int, info: ThirdPartyUserInfo) -> None:
        """更新第三方绑定的资料与最后登录时间。"""
        values: dict[str, Any] = {"last_login_time": datetime.now(UTC)}
        if info.unionid:
            values["unionid"] = info.unionid
        if info.nickname:
            values["nickname"] = info.nickname
        if info.avatar:
            values["avatar"] = info.avatar
        if info.raw:
            values["extra"] = info.raw
        await self.oauths.set(ids=[binding_id], **values)

    @staticmethod
    def _default_nickname(mobile: str | None) -> str:
        """生成默认昵称。"""
        if mobile and len(mobile) >= 4:
            return f"用户{mobile[-4:]}"
        return f"用户{uuid.uuid4().hex[:6]}"
