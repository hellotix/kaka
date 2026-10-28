"""物品与批次的请求/响应模型。

命名约定
--------
- ``*CreateSchema`` / ``*UpdateSchema``：写入模型。Update 全部字段可选，
  ``CRUDBase.update`` 的 ``exclude_unset`` 语义决定「没传就是不改」。
- ``*OutSchema``：响应模型，继承 ``BaseSchema`` 以带上 id/uuid/时间戳。
- ``*QueryParam``：查询参数，字段上的 ``json_schema_extra={"q": "op"}``
  会被 ``search_to_dict`` 翻译成 ``CRUDBase`` 认识的 ``(op, value)`` 元组。

关键约束：``family_id`` 绝不接受请求体传入
------------------------------------------
家庭归属一律由 ``X-Family-Id`` 请求头经 ``FamilyContext`` 注入。若允许 body 传 family_id，
越权者只要改一个数字就能把物品写进别人家 —— 这是本项目最需要防的一类漏洞。

唯一的例外是 ``ErpItemAdminCreateSchema``：后台运营接口没有「当前家庭」这个概念，
必须显式指定归属，其可信性由 ``AuthPermission`` 的后台权限标识保证，而不是由请求头保证。

后台模型为什么单独开一节而不是给 C端模型加可选字段
--------------------------------------------------
往 C端 ``*CreateSchema`` 上加一个可选 ``family_id``，就等于在入口最密集的地方放一个
平时没人用、一旦被前端误传就会改变归属语义的字段。命名分开的代价只是多几个类。
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.base_schema import BaseQueryParam, BaseSchema
from app.core.validator import DateTimeStr

from ..core.constants import ErpItemVisibility

# 可见范围的字面量类型：直接复用枚举成员，避免两处字符串写歪
ItemVisibilityLiteral = Literal["family", "member", "private"]


# ══════════════════════════ 批次 ══════════════════════════


class ErpItemBatchCreateSchema(BaseModel):
    """新增批次（一次进货）"""

    quantity: float = Field(..., gt=0, description="进货数量")
    remain_qty: float | None = Field(default=None, ge=0, description="剩余数量(不填=与进货数量相同)")
    unit_price: float | None = Field(default=None, ge=0, description="单价")
    purchase_time: datetime | None = Field(default=None, description="购买时间(不填=服务器当前时间)")
    channel: str | None = Field(default=None, max_length=64, description="购买渠道")
    production_date: date | None = Field(default=None, description="生产日期")
    expiry_date: date | None = Field(default=None, description="有效期至")
    remark: str | None = Field(default=None, description="备注")

    @model_validator(mode="after")
    def _check_dates(self) -> "ErpItemBatchCreateSchema":
        """有效期不能早于生产日期 —— 录错这两个字段是过期提醒误报的头号来源。"""
        if self.production_date and self.expiry_date and self.expiry_date < self.production_date:
            raise ValueError("有效期不能早于生产日期")
        if self.remain_qty is not None and self.remain_qty > self.quantity:
            raise ValueError("剩余数量不能大于进货数量")
        return self


class ErpItemBatchUpdateSchema(BaseModel):
    """修改批次（全部可选，没传就是不改）"""

    quantity: float | None = Field(default=None, gt=0, description="进货数量")
    remain_qty: float | None = Field(default=None, ge=0, description="剩余数量")
    unit_price: float | None = Field(default=None, ge=0, description="单价")
    purchase_time: datetime | None = Field(default=None, description="购买时间")
    channel: str | None = Field(default=None, max_length=64, description="购买渠道")
    production_date: date | None = Field(default=None, description="生产日期")
    expiry_date: date | None = Field(default=None, description="有效期至")
    status: int | None = Field(default=None, ge=1, le=4, description="批次状态(1:在用 2:已耗尽 3:已过期 4:已丢弃)")
    remark: str | None = Field(default=None, description="备注")


class ErpItemBatchAddSchema(ErpItemBatchCreateSchema):
    """给已有物品新增批次（带物品ID）

    独立成一个 Schema 而不是把 ``item_id`` 加进 ``ErpItemBatchCreateSchema``：
    建档时的初始批次不接受物品ID（那时物品还没落库、ID 也不存在），
    两个场景的字段本来就不同，合成一个会让「建档时也能传 item_id」变得含糊。
    """

    item_id: int = Field(..., description="物品档案ID")


class ErpItemBatchOutSchema(BaseSchema):
    """批次响应模型"""

    item_id: int | None = Field(default=None, description="物品档案ID")
    family_id: int | None = Field(default=None, description="所属家庭ID")
    quantity: float | None = Field(default=None, description="进货数量")
    remain_qty: float | None = Field(default=None, description="剩余数量")
    unit_price: float | None = Field(default=None, description="单价")
    purchase_time: DateTimeStr | None = Field(default=None, description="购买时间")
    channel: str | None = Field(default=None, description="购买渠道")
    production_date: date | None = Field(default=None, description="生产日期")
    expiry_date: date | None = Field(default=None, description="有效期至")
    status: int | None = Field(default=None, description="批次状态(1:在用 2:已耗尽 3:已过期 4:已丢弃)")
    remark: str | None = Field(default=None, description="备注")


class ErpBatchAdminOutSchema(ErpItemBatchOutSchema):
    """后台批次响应模型

    ``item_name`` / ``family_name`` 由 service 批量补齐：后台批次列表是全家庭混排的，
    只有 ID 运营看不出是哪家的哪件东西。
    """

    item_name: str | None = Field(default=None, description="物品名称")
    family_name: str | None = Field(default=None, description="所属家庭名称")


class ErpBatchAdminQueryParam(BaseQueryParam):
    """后台批次查询参数

    没有可见性条件：后台是运营视角，跨家庭且不按成员裁剪。
    """

    item_id: int | None = Field(None, description="物品档案ID", json_schema_extra={"q": "eq"})
    family_id: int | None = Field(None, description="所属家庭ID", json_schema_extra={"q": "eq"})
    status: int | None = Field(None, description="批次状态(1:在用 2:已耗尽 3:已过期 4:已丢弃)", json_schema_extra={"q": "eq"})
    channel: str | None = Field(None, description="购买渠道(模糊)", json_schema_extra={"q": "like"})
    # 有效期区间：?expiry_date=2026-10-01&expiry_date=2026-10-31 → 「这段时间到期的批次」，
    # P3 过期提醒上线前运营核对库存就靠这一个筛选。
    # 为什么不用框架的 expiry_date_start/end 命名约定：那两个键在只传一边时不会被合并成
    # 真实列名，会带着「_start」这个数据库里不存在的列名去拼条件（直接报错）。
    # 单字段 + between 天然要求成对，配合下面的校验把「只传一个」在入口就挡掉。
    expiry_date: list[date] | None = Field(None, description="有效期区间(两个日期，含边界)", json_schema_extra={"q": "between"})

    @field_validator("expiry_date")
    @classmethod
    def _check_range(cls, v: list[date] | None) -> list[date] | None:
        if v is None:
            return None
        if len(v) != 2:
            raise ValueError("有效期区间必须传两个日期(起、止)")
        if v[0] > v[1]:
            raise ValueError("有效期区间的起始日期不能晚于结束日期")
        return v


# ══════════════════════════ 物品档案 ══════════════════════════


class ErpItemCreateSchema(BaseModel):
    """新增物品档案（可同时带首批批次）

    ``batches`` 允许为空：先建档、后补批次是常见录入顺序（例如别人送的还没拆封）。
    """

    category_id: int | None = Field(default=None, description="分类ID(可空=未归类)")
    name: str = Field(..., min_length=1, max_length=128, description="物品名称")
    barcode: str | None = Field(default=None, max_length=64, description="商品编码/条码")
    brand: str | None = Field(default=None, max_length=64, description="品牌")
    spec: str | None = Field(default=None, max_length=64, description="规格")
    unit: str | None = Field(default=None, max_length=16, description="计量单位")
    images: list[str] = Field(default_factory=list, description="图片URL列表")
    purchase_channel: str | None = Field(default=None, max_length=64, description="常用购买渠道")
    ref_price: float | None = Field(default=None, ge=0, description="参考单价")
    owner_user_id: int | None = Field(default=None, description="归属人(不填=当前登录用户)")
    location: str | None = Field(default=None, max_length=64, description="存放位置")
    visibility: ItemVisibilityLiteral = Field(default=ErpItemVisibility.FAMILY.value, description="可见范围")
    attrs: dict | None = Field(default=None, description="扩展属性(按该分类的有效模板校验)")
    remark: str | None = Field(default=None, description="备注")
    batches: list[ErpItemBatchCreateSchema] = Field(default_factory=list, description="初始批次列表(可空)")

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("物品名称不能为空")
        return v

    @field_validator("barcode", "brand", "spec", "unit", "purchase_channel", "location")
    @classmethod
    def _strip_optional(cls, v: str | None) -> str | None:
        """可空字段统一去空白，空串归一为 None（避免库里同时存在 "" 与 NULL 两种空值）。"""
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v


class ErpItemUpdateSchema(BaseModel):
    """修改物品档案（全部可选，没传就是不改；批次不走这里）

    换 ``category_id`` 时 ``attrs`` 会按新分类的有效模板重新校验，
    没在新模板里的旧键会被丢弃。
    """

    category_id: int | None = Field(default=None, description="分类ID")
    name: str | None = Field(default=None, min_length=1, max_length=128, description="物品名称")
    barcode: str | None = Field(default=None, max_length=64, description="商品编码/条码")
    brand: str | None = Field(default=None, max_length=64, description="品牌")
    spec: str | None = Field(default=None, max_length=64, description="规格")
    unit: str | None = Field(default=None, max_length=16, description="计量单位")
    images: list[str] | None = Field(default=None, description="图片URL列表")
    purchase_channel: str | None = Field(default=None, max_length=64, description="常用购买渠道")
    ref_price: float | None = Field(default=None, ge=0, description="参考单价")
    owner_user_id: int | None = Field(default=None, description="归属人(仅户主/管理员可改)")
    location: str | None = Field(default=None, max_length=64, description="存放位置")
    visibility: ItemVisibilityLiteral | None = Field(default=None, description="可见范围")
    attrs: dict | None = Field(default=None, description="扩展属性(按该分类的有效模板校验)")
    remark: str | None = Field(default=None, description="备注")

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("物品名称不能为空")
        return v

    @field_validator("barcode", "brand", "spec", "unit", "purchase_channel", "location")
    @classmethod
    def _strip_optional(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v


class ErpItemOutSchema(BaseSchema):
    """物品档案响应模型

    ``category_name`` / ``owner_name`` / ``batch_*`` 系列 ORM 上都没有，
    由 service 批量补齐（列表页一次查完，不逐行查库）。
    """

    family_id: int | None = Field(default=None, description="所属家庭ID")
    category_id: int | None = Field(default=None, description="分类ID")
    name: str | None = Field(default=None, description="物品名称")
    barcode: str | None = Field(default=None, description="商品编码/条码")
    brand: str | None = Field(default=None, description="品牌")
    spec: str | None = Field(default=None, description="规格")
    unit: str | None = Field(default=None, description="计量单位")
    images: list[str] = Field(default_factory=list, description="图片URL列表")
    purchase_channel: str | None = Field(default=None, description="常用购买渠道")
    ref_price: float | None = Field(default=None, description="参考单价")
    owner_user_id: int | None = Field(default=None, description="归属人(C端用户ID)")
    location: str | None = Field(default=None, description="存放位置")
    visibility: str | None = Field(default=None, description="可见范围(family/member/private)")
    attrs: dict | None = Field(default=None, description="扩展属性")
    remark: str | None = Field(default=None, description="备注")
    # 以下为 service 组装字段
    category_name: str | None = Field(default=None, description="分类名称")
    owner_name: str | None = Field(default=None, description="归属人昵称")
    batch_count: int = Field(default=0, description="批次数")
    total_remain_qty: float = Field(default=0, description="剩余总量(所有在用批次求和)")
    nearest_expiry_date: date | None = Field(default=None, description="最近到期日(在用批次中最早的)")
    batches: list[ErpItemBatchOutSchema] = Field(default_factory=list, description="批次明细(仅详情接口返回)")

    @field_validator("images", mode="before")
    @classmethod
    def _none_to_empty_list(cls, v: object) -> object:
        """JSON 列的 NULL 归一为空列表，前端不必再判空。"""
        return v if v is not None else []


class ErpItemQueryParam(BaseQueryParam):
    """C端物品列表查询参数"""

    name: str | None = Field(None, description="物品名称(模糊)", json_schema_extra={"q": "like"})
    barcode: str | None = Field(None, description="商品编码", json_schema_extra={"q": "eq"})
    category_id: int | None = Field(None, description="分类ID", json_schema_extra={"q": "eq"})
    owner_user_id: int | None = Field(None, description="归属人ID", json_schema_extra={"q": "eq"})
    visibility: str | None = Field(None, description="可见范围", json_schema_extra={"q": "eq"})


# ══════════════════════════ 后台运营：物品档案 ══════════════════════════


class ErpItemAdminCreateSchema(ErpItemCreateSchema):
    """后台新增物品档案

    与 C端唯一实质差别是这两个必填字段：C端的家庭归属来自 ``X-Family-Id`` 请求头、
    归属人默认当前登录用户，而后台操作者既不是家庭成员也没有「当前家庭」，
    所以必须由请求体显式指定，不能让 service 去猜。
    ``family_id`` 在 C端是绝对禁止从 body 传入的（见本文件顶部），
    这里放开是因为调用方已经过 ``AuthPermission`` 的后台权限校验，属于可信运营入口。
    """

    family_id: int = Field(..., description="所属家庭ID")
    owner_user_id: int = Field(..., description="归属人(C端用户ID，必须是该家庭成员)")


class ErpItemAdminOutSchema(ErpItemOutSchema):
    """后台物品响应模型

    ``family_name`` 只在后台列表/详情返回：C端永远只查当前家庭，不需要这个字段。
    """

    family_name: str | None = Field(default=None, description="所属家庭名称")


class ErpItemAdminQueryParam(ErpItemQueryParam):
    """后台物品查询参数（跨家庭，可指定家庭）"""

    family_id: int | None = Field(None, description="所属家庭ID", json_schema_extra={"q": "eq"})


# ══════════════════════════ 扫码 ══════════════════════════


class ErpItemScanSchema(BaseModel):
    """扫码请求：扫码枪/摄像头扫到的商品编码"""

    barcode: str = Field(..., min_length=1, max_length=64, description="商品编码/条码")

    @field_validator("barcode")
    @classmethod
    def _strip_barcode(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("商品编码不能为空")
        return v


class ErpItemScanResultSchema(BaseModel):
    """扫码结果

    - ``matched=True``：家庭内已有该编码的物品，客户端进「新增批次」表单
      （``item`` 带出物品信息，``last_batch`` 带出上次的单价/渠道，用户改几个数字就能提交）。
    - ``matched=False``：家庭内没有，客户端进「新建物品」表单，``barcode`` 原样回传以便预填。
    """

    matched: bool = Field(..., description="家庭内是否已存在该编码的物品")
    barcode: str = Field(..., description="本次扫描的商品编码")
    item: ErpItemOutSchema | None = Field(default=None, description="命中的物品档案")
    last_batch: ErpItemBatchOutSchema | None = Field(default=None, description="该物品最近一次批次(用于预填单价/渠道)")
