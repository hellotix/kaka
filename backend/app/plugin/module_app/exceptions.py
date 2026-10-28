"""C端插件统一业务异常（module_app 根级，供各子板块复用）。

为什么要有这个类
----------------
``CustomException`` 的默认 ``status_code`` 是 **500**。业务规则拒绝（例如「分类最多 3 级」
「验证码已过期」「该手机号已注册」）如果直接 ``raise CustomException(msg=...)``，
HTTP 层就会返回「500 服务器内部错误」：

- 客户端会把可预期的业务分支当成服务端故障去重试或上报崩溃；
- 监控与日志会把正常的业务拒绝统计成服务端错误；
- 与实施方案文档的约定不符（文档写明「第四级分类请求返回 400」）。

因此 C端所有**业务规则拒绝**统一抛 ``BusinessError``：默认 400，
资源不存在 / 状态冲突 / 触发限流 / 渠道异常等场景按 HTTP 语义显式传 ``status_code``。

用法::

    from ...exceptions import BusinessError

    raise BusinessError(msg="分类最多支持 3 级")                # 400（默认）
    raise BusinessError(msg="该分类不存在", status_code=404)     # 404
    raise BusinessError(msg="同级下已存在同名分类", status_code=409)
    raise BusinessError(msg="验证码错误次数过多", status_code=429)

分工说明：认证/鉴权类异常（401 未登录、403 无权限头、令牌失效等）仍由
``login/core/security.py`` 的 ``unauthorized()`` 与 ``login/core/dependencies.py``
直接抛 ``CustomException``（它们本来就带正确的 401/403），不经过本类。
"""

from typing import Any

from fastapi import status

from app.core.exceptions import CustomException


class BusinessError(CustomException):
    """业务规则拒绝异常（默认 HTTP 400，而不是 500）。

    参数:
    - msg (str): 展示给用户的错误提示。
    - code (int | None): 业务错误码，默认与 ``status_code`` 保持一致
      （正好与 ``RET`` 中 400/403/404/409/429 等取值对应）。
    - status_code (int): HTTP 状态码，默认 400。
    - data (Any | None): 附加数据（如字段级错误明细），默认 None。

    返回:
    - None
    """

    def __init__(
        self,
        msg: str,
        *,
        code: int | None = None,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        data: Any | None = None,
    ) -> None:
        super().__init__(
            msg=msg,
            code=status_code if code is None else code,
            status_code=status_code,
            data=data,
        )
