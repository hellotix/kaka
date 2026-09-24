"""短信验证码服务。

真实短信渠道通过 ``@register_sms_sender("aliyun")`` 注册后，
将环境变量 ``APP_SMS_PROVIDER`` 指向对应名称即可启用；
默认 ``logging`` 渠道仅把验证码写入日志，便于本地联调。
"""

import secrets
import string
from abc import ABC, abstractmethod
from datetime import UTC, datetime

from redis.asyncio.client import Redis

from app.core.exceptions import CustomException
from app.core.logger import logger
from app.core.redis_crud import RedisCURD

from ..core.constants import (
    SMS_CODE_EXPIRE_SECONDS,
    SMS_CODE_LENGTH,
    SMS_DAILY_LIMIT,
    SMS_MAX_VERIFY_FAIL,
    SMS_PROVIDER,
    SMS_RESEND_INTERVAL_SECONDS,
    AppSmsScene,
    sms_code_key,
    sms_daily_key,
    sms_fail_key,
    sms_interval_key,
)
from .schema import AppSmsSendOutSchema


def mask_mobile(mobile: str) -> str:
    """手机号脱敏：保留前3位与后4位。"""
    if not mobile or len(mobile) < 7:
        return mobile or ""
    return f"{mobile[:3]}****{mobile[-4:]}"


class SmsSender(ABC):
    """短信发送渠道抽象基类 —— 接入真实服务商时实现此接口"""

    name: str = "base"

    @abstractmethod
    async def send(self, mobile: str, code: str, scene: AppSmsScene) -> bool:
        """发送验证码短信。

        参数:
        - mobile (str): 手机号。
        - code (str): 验证码。
        - scene (AppSmsScene): 使用场景（不同场景可对应不同模板）。

        返回:
        - bool: 是否发送成功。
        """


class LoggingSmsSender(SmsSender):
    """默认渠道：仅记录日志，不对接真实短信服务"""

    name = "logging"

    async def send(self, mobile: str, code: str, scene: AppSmsScene) -> bool:
        logger.warning(f"[短信验证码-未接入真实渠道] scene={scene.value}, mobile={mask_mobile(mobile)}, code={code}")
        return True


_SENDER_REGISTRY: dict[str, type[SmsSender]] = {LoggingSmsSender.name: LoggingSmsSender}


def register_sms_sender(name: str):
    """注册短信渠道的类装饰器。

    参数:
    - name (str): 渠道名称，与环境变量 ``APP_SMS_PROVIDER`` 对应。

    返回:
    - Callable: 装饰器。
    """

    def wrapper(sender_cls: type[SmsSender]) -> type[SmsSender]:
        sender_cls.name = name
        _SENDER_REGISTRY[name] = sender_cls
        return sender_cls

    return wrapper


def get_sms_sender() -> SmsSender:
    """按配置获取短信渠道实例，未注册的渠道回退到日志渠道。"""
    sender_cls = _SENDER_REGISTRY.get(SMS_PROVIDER)
    if sender_cls is None:
        logger.warning(f"短信渠道 {SMS_PROVIDER!r} 未注册，已回退到 logging 渠道")
        sender_cls = LoggingSmsSender
    return sender_cls()


class SmsService:
    """验证码发送与校验（含发送频控、每日上限、错误次数限制）"""

    def __init__(self, redis: Redis) -> None:
        self.redis = redis
        self.cache = RedisCURD(redis)

    async def send_code(self, mobile: str, scene: AppSmsScene = AppSmsScene.LOGIN) -> AppSmsSendOutSchema:
        """发送短信验证码。

        参数:
        - mobile (str): 手机号。
        - scene (AppSmsScene): 使用场景。

        返回:
        - AppSmsSendOutSchema: 发送结果（含脱敏手机号与重发间隔）。

        异常:
        - CustomException: 触发频控、超出每日上限或渠道发送失败。
        """
        mobile = (mobile or "").strip()
        if not mobile:
            raise CustomException(msg="手机号不能为空")

        interval_key = sms_interval_key(mobile)
        if await self.cache.exists(interval_key):
            ttl = await self.cache.ttl(key=interval_key)
            raise CustomException(msg=f"验证码发送过于频繁，请 {max(int(ttl), 1)} 秒后重试")

        today = datetime.now(UTC).strftime("%Y%m%d")
        daily_key = sms_daily_key(mobile, today)
        sent_today = int(await self.cache.get(daily_key) or 0)
        if sent_today >= SMS_DAILY_LIMIT:
            raise CustomException(msg=f"今日验证码发送次数已达上限({SMS_DAILY_LIMIT}次)")

        code = "".join(secrets.choice(string.digits) for _ in range(SMS_CODE_LENGTH))
        if not await get_sms_sender().send(mobile=mobile, code=code, scene=scene):
            raise CustomException(msg="验证码发送失败，请稍后重试")

        await self.cache.set(key=sms_code_key(scene, mobile), value=code, expire=SMS_CODE_EXPIRE_SECONDS)
        await self.cache.set(key=interval_key, value="1", expire=SMS_RESEND_INTERVAL_SECONDS)
        await self.cache.delete(sms_fail_key(scene, mobile))

        count = await self.redis.incr(daily_key)
        if count == 1:
            await self.redis.expire(daily_key, 24 * 60 * 60)

        logger.info(f"短信验证码已发送: scene={scene.value}, mobile={mask_mobile(mobile)}")
        return AppSmsSendOutSchema(mobile=mask_mobile(mobile))

    async def verify_code(self, mobile: str, code: str, scene: AppSmsScene = AppSmsScene.LOGIN) -> None:
        """校验短信验证码，校验通过后立即失效。

        参数:
        - mobile (str): 手机号。
        - code (str): 用户提交的验证码。
        - scene (AppSmsScene): 使用场景。

        异常:
        - CustomException: 验证码为空、过期、错误或错误次数超限。
        """
        mobile = (mobile or "").strip()
        code = (code or "").strip()
        if not mobile or not code:
            raise CustomException(msg="手机号和验证码不能为空")

        key = sms_code_key(scene, mobile)
        fail_key = sms_fail_key(scene, mobile)

        cached = await self.cache.get(key)
        if not cached:
            raise CustomException(msg="验证码已过期，请重新获取")
        if isinstance(cached, bytes):
            cached = cached.decode("utf-8")

        fail_count = int(await self.cache.get(fail_key) or 0)
        if fail_count >= SMS_MAX_VERIFY_FAIL:
            await self.cache.delete(key, fail_key)
            raise CustomException(msg="验证码错误次数过多，请重新获取")

        if not secrets.compare_digest(str(cached), code):
            count = await self.redis.incr(fail_key)
            if count == 1:
                await self.redis.expire(fail_key, SMS_CODE_EXPIRE_SECONDS)
            raise CustomException(msg="验证码错误")

        await self.cache.delete(key, fail_key)
