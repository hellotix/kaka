"""家庭物品表 —— 档案与批次两层结构。

为什么拆两层
------------
「阿莫西林」是一**件**物资，但一年可能买好几次，每次的购买渠道、单价、有效期都不同。
若把有效期/数量直接挂在档案上，第二次购买只能覆盖第一次的数据，过期管理随之失效。
因此：

- ``erp_item``       档案：名称/编码/品牌/规格/单位/图片/归属人/扩展属性 —— 「这是什么」
- ``erp_item_batch`` 批次：数量/剩余量/单价/购买时间/有效期/状态 —— 「这次买了多少、什么时候过期」

过期管理挂批次（P3 定时扫描 ``expiry_date``），库存统计也是对批次求和；
档案层只做展示聚合（剩余总量、最近到期日）。

家庭隔离
--------
两张表都带 ``family_id``：档案上的用于按家庭收敛查询（单家庭最多 1000 条），
批次上的冗余一份是为了 P3 定时扫描能直接 ``WHERE family_id IN (...)`` 而不用 join 档案表。

软删除
------
两张表都软删（``is_deleted`` + ``deleted_time`` + ``deleted_id``），删物品时批次跟随一起软删
（记录还在、可追溯，但 P3 的过期扫描不会再扫到已删物品的批次）。
审计人存 C端用户ID，不做外键（C端用户与后台 ``sys_user`` 无关）。
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin

from ..core.constants import ErpBatchStatus, ErpItemVisibility


class ErpItemModel(ModelMixin):
    """物品档案表（一件物资一行，与家庭强绑定）"""

    __tablename__: str = "erp_item"
    __table_args__: dict[str, str] = {"comment": "ERP-物品档案"}

    family_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("erp_family.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
        comment="所属家庭ID",
    )
    # 分类可空：用户先录入、后归类是常态，强制必填会打断扫码录入的连贯性
    category_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("erp_category.id", ondelete="SET NULL", onupdate="CASCADE"),
        default=None,
        nullable=True,
        index=True,
        comment="分类ID(可空=未归类)",
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="物品名称")
    # barcode 就是「商品编码」字段本身，不是外部主数据键：扫码只是把手输换成扫一下，
    # 查重范围仅限当前家庭（同一条码在不同家庭是各自独立的物品）。
    barcode: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True, index=True, comment="商品编码/条码")
    brand: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True, comment="品牌")
    spec: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True, comment="规格")
    unit: Mapped[str | None] = mapped_column(String(16), default=None, nullable=True, comment="计量单位(盒/瓶/包/斤)")
    images: Mapped[list | None] = mapped_column(JSON, default=list, nullable=False, comment="物品图片URL列表")
    purchase_channel: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True, comment="常用购买渠道")
    ref_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), default=None, nullable=True, comment="参考单价")
    owner_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True, comment="归属人(C端用户ID)")
    location: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True, comment="存放位置")
    visibility: Mapped[str] = mapped_column(
        String(16),
        default=ErpItemVisibility.FAMILY.value,
        nullable=False,
        comment="可见范围(family:全家 member:仅本人 private:私密)",
    )
    share_to: Mapped[list | None] = mapped_column(
        JSON,
        default=None,
        nullable=True,
        comment="物品级共享对象用户ID列表(预留字段，P2 物品级共享落地时才写入并参与可见性判定)",
    )
    attrs: Mapped[dict | None] = mapped_column(JSON, default=None, nullable=True, comment="扩展属性(按模板校验后的JSON)")
    remark: Mapped[str | None] = mapped_column(Text, default=None, nullable=True, comment="备注")
    deleted_id: Mapped[int | None] = mapped_column(Integer, default=None, nullable=True, comment="删除人ID(C端用户ID)")


class ErpItemBatchModel(ModelMixin):
    """物品批次表（一次进货一行，过期管理与库存统计的载体）"""

    __tablename__: str = "erp_item_batch"
    __table_args__: dict[str, str] = {"comment": "ERP-物品批次"}

    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("erp_item.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
        comment="物品档案ID",
    )
    # 冗余 family_id：P3 过期扫描按家庭批量查「即将过期的批次」，不必 join 档案表
    family_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("erp_family.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
        comment="所属家庭ID(冗余，便于按家庭扫描)",
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0, nullable=False, comment="进货数量")
    remain_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0, nullable=False, comment="剩余数量")
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), default=None, nullable=True, comment="单价")
    purchase_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None, nullable=True, comment="购买时间")
    channel: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True, comment="购买渠道")
    production_date: Mapped[date | None] = mapped_column(Date, default=None, nullable=True, comment="生产日期")
    # 过期管理的核心字段，P3 扫描任务按它挑出待提醒批次
    expiry_date: Mapped[date | None] = mapped_column(Date, default=None, nullable=True, index=True, comment="有效期至")
    status: Mapped[int] = mapped_column(
        Integer,
        default=ErpBatchStatus.IN_USE.value,
        nullable=False,
        index=True,
        comment="批次状态(1:在用 2:已耗尽 3:已过期 4:已丢弃)",
    )
    remark: Mapped[str | None] = mapped_column(Text, default=None, nullable=True, comment="备注")
    deleted_id: Mapped[int | None] = mapped_column(Integer, default=None, nullable=True, comment="删除人ID(C端用户ID)")
