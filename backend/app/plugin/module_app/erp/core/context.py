"""家庭上下文解析 —— ERP 子板块所有「家庭内」接口的统一入口依赖。

为什么不用 JWT 携带 family_id
-----------------------------
一个用户可以同时属于多个家庭（自己的家、父母的家）。若把 family_id 写进令牌，
切换家庭就得重新登录，多端还会互相踢。因此家庭归属按请求维度传递：

    GET /api/v1/app/erp/item/list
    Authorization: Bearer <C端令牌>
    X-Family-Id: 12

``FamilyAuth`` 依赖负责三件事：解析头 → 校验成员关系有效 → 校验角色权限。
业务层拿到的是已经鉴权完毕的 ``FamilyContext``，不需要再关心越权问题。

注意：这里刻意从 ``module_app.login`` 的具体路径导入登录依赖，而不是从
``app.plugin.module_app`` 包根导入。包根的 ``__init__`` 会导入本子板块，
反向引用会在包初始化未完成时触发 ImportError。
"""

from typing import Annotated, Any

from fastapi import Depends, Header
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio.client import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import RET
from app.core.exceptions import CustomException
from app.plugin.module_app.login.core.dependencies import AppAuthContext, CurrentAppUser

from ..family.model import ErpFamilyMemberModel, ErpFamilyModel
from .constants import FAMILY_HEADER, ErpFamilyRole, ErpMemberStatus


class FamilyContext(BaseModel):
    """家庭上下文 —— 依赖注入后传给 service 层

    字段:
    - family_id / family: 本次请求操作的家庭。
    - member: 当前用户在该家庭中的成员记录（含角色、家庭内称呼）。
    - role: 成员角色的枚举形式，便于比较权限。
    - user_id: 当前C端用户ID（等价于 ``auth.user_id``，冗余一份方便业务层直接使用）。
    - db / redis: 请求级会话，与登录上下文同一个实例（同一事务边界内）。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    family_id: int = Field(..., description="家庭ID")
    family: ErpFamilyModel = Field(exclude=True, description="家庭 ORM 对象")
    member: ErpFamilyMemberModel = Field(exclude=True, description="成员 ORM 对象")
    role: ErpFamilyRole = Field(..., description="当前用户在该家庭中的角色")
    user_id: int = Field(..., description="C端用户ID")
    auth: AppAuthContext = Field(exclude=True, description="C端登录上下文")
    db: AsyncSession = Field(exclude=True, description="数据库会话")
    redis: Redis = Field(exclude=True, description="Redis 连接")

    @property
    def is_owner(self) -> bool:
        """是否为户主。"""
        return self.role is ErpFamilyRole.OWNER

    def require(self, min_role: ErpFamilyRole) -> None:
        """断言当前角色不低于 ``min_role``，否则抛 403。

        参数:
        - min_role (ErpFamilyRole): 所需最低角色。

        异常:
        - CustomException: 角色权重不足时抛出 403。
        """
        if self.role.weight < min_role.weight:
            raise CustomException(
                msg=f"权限不足，该操作需要「{min_role.value}」及以上角色",
                code=RET.FORBIDDEN.code,
                status_code=403,
            )


class FamilyAuth:
    """家庭上下文依赖（必须登录 + 必须指定家庭 + 必须是有效成员）

    参数:
    - min_role (ErpFamilyRole | None): 要求的最低角色，None 表示只要是有效成员即可。
    """

    def __init__(self, min_role: ErpFamilyRole | None = None) -> None:
        self.min_role = min_role

    async def __call__(
        self,
        auth: CurrentAppUser,
        family_id: Annotated[int | None, Header(alias=FAMILY_HEADER, description="目标家庭ID")] = None,
    ) -> FamilyContext:
        """解析并校验家庭上下文。

        参数:
        - auth (AppAuthContext): C端登录上下文，由 ``CurrentAppUser`` 注入。
        - family_id (int | None): ``X-Family-Id`` 请求头。

        返回:
        - FamilyContext: 校验通过的家庭上下文。

        异常:
        - CustomException: 缺少请求头(400)、家庭不存在或已停用(404)、
          不是该家庭成员或成员状态非「已加入」(403)、角色不足(403)。
        """
        # 延迟导入：family.crud 依赖本模块之外的 schema，放函数内可彻底规避导入环
        from ..family.crud import ErpFamilyCRUD, ErpFamilyMemberCRUD

        if not family_id:
            raise CustomException(
                msg=f"缺少请求头 {FAMILY_HEADER}，请先选择要操作的家庭",
                code=RET.BAD_REQUEST.code,
                status_code=400,
            )

        families = ErpFamilyCRUD(auth_schema(), auth.db)
        family = await families.get(id=family_id)
        if not family:
            raise CustomException(msg="家庭不存在或已解散", code=RET.NOT_FOUND.code, status_code=404)
        if family.status != 0:
            raise CustomException(msg="该家庭已停用，请联系户主或客服", code=RET.FORBIDDEN.code, status_code=403)

        members = ErpFamilyMemberCRUD(auth_schema(), auth.db)
        member = await members.get(family_id=family_id, user_id=auth.user_id)
        # 待确认/已拒绝/已移除的成员一律视为无权限：邀请未接受前不应看到任何家庭数据
        if not member or member.status != ErpMemberStatus.ACTIVE.value:
            raise CustomException(msg="您不是该家庭的成员，无权访问", code=RET.FORBIDDEN.code, status_code=403)

        context = FamilyContext(
            family_id=family.id,
            family=family,
            member=member,
            role=_to_role(member.role),
            user_id=auth.user_id,
            auth=auth,
            db=auth.db,
            redis=auth.redis,
        )
        if self.min_role is not None:
            context.require(self.min_role)
        return context


def _to_role(value: str | None) -> ErpFamilyRole:
    """成员角色字符串转枚举，脏数据按最低权限 viewer 处理（不放大权限）。"""
    try:
        return ErpFamilyRole(value) if value else ErpFamilyRole.VIEWER
    except ValueError:
        return ErpFamilyRole.VIEWER


def auth_schema() -> Any:
    """构造空的后台认证模型。

    C端流程没有后台登录态，``AuthSchema()`` 的 user.id 为 0/None，
    ``CRUDBase`` 因此不会填充审计人、``Permission`` 也不会追加数据权限条件。
    """
    from app.core.base_schema import AuthSchema

    return AuthSchema()


# 常用依赖别名：controller 里直接当类型注解用即可
CurrentFamily = Annotated[FamilyContext, Depends(FamilyAuth())]
FamilyAdmin = Annotated[FamilyContext, Depends(FamilyAuth(min_role=ErpFamilyRole.ADMIN))]
FamilyWriter = Annotated[FamilyContext, Depends(FamilyAuth(min_role=ErpFamilyRole.MEMBER))]
FamilyOwner = Annotated[FamilyContext, Depends(FamilyAuth(min_role=ErpFamilyRole.OWNER))]
