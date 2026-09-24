from datetime import date, datetime, time
from sqlalchemy import BIGINT, JSON, Boolean, Date, DateTime, Float, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column
from app.core.base_model import ModelMixin, UserMixin


class ErpModel(ModelMixin, UserMixin):
    """示例表 - 涵盖大多数常用数据类型
    """
    __tablename__: str = "erp_inv"
    __table_args__: dict[str, str] = {"comment": "家庭仓储模块"}
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="名称")
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="状态(0:启动 1:停用)", index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None, nullable=True, comment="备注")
    int_val: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="整数")
    bigint_val: Mapped[int | None] = mapped_column(BIGINT, nullable=True, comment="大整数")
    float_val: Mapped[float | None] = mapped_column(Float, nullable=True, comment="浮点数")
    bool_val: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, comment="布尔型")
    date_val: Mapped[date | None] = mapped_column(Date, nullable=True, comment="日期")
    time_val: Mapped[time | None] = mapped_column(Time, nullable=True, comment="时间")
    datetime_val: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="日期时间")
    text_val: Mapped[str | None] = mapped_column(Text, nullable=True, comment="长文本")
    json_val: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="元数据(JSON格式)")


class ErpBaseModel(ModelMixin, UserMixin):
    """
    ERP家庭物品 抽象基类【不会生成数据库表】
    家里物品通用属性：名称、品牌、进货渠道、购买时间、过期时间、数量、状态、备注
    """
    __abstract__ = True  # 关键：标记为抽象，不生成物理表

    # 物品名称
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True, comment="物品名称")
    # 品牌
    brand: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="品牌")
    # 进货渠道：0淘宝 1京东 2拼多多 3线下商超 4菜市场 5亲友赠送 6其他
    source_channel: Mapped[int] = mapped_column(
        Integer, default=6, nullable=False,
        comment="进货渠道 0淘宝 1京东 2拼多多 3线下商超 4菜市场 5亲友赠送 6其他", index=True
    )
    # 购买时间
    buy_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="购买/获得日期")
    # 采购单价
    buy_price: Mapped[float | None] = mapped_column(Float, nullable=True, comment="采购单价(元)")
    # 生产日期
    produce_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="生产日期")
    # 过期时间
    expire_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="过期/失效日期")
    # 是否开启过期预警
    warn_expire: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, comment="是否开启过期预警")
    # 存放位置：哪个房间/柜子/冰箱
    location: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True, comment="存放位置")
    # 库存数量
    stock_num: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="当前库存数量")
    # 状态：0正常在用 1已过期 2已消耗完毕 3闲置封存
    status: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, index=True,
        comment="物品状态 0正常在用 1已过期 2已消耗完毕 3闲置封存"
    )
    # 简短备注
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="简短备注")
    # 扩展详细备注
    remark_ext: Mapped[str | None] = mapped_column(Text, nullable=True, comment="扩展详细备注")
    # 计量单位：个/瓶/包/盒/千克
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="计量单位：个/瓶/包/盒/千克")
    # 上传图片附件，url数组
    attach_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="图片附件url列表")


# ---------------- 子类1：家庭药品 erp_goods_medicine ----------------
class ErpMedicineModel(ErpBaseModel):
    """家庭药品｜内服、外用、医疗器械、保健品"""
    __tablename__ = "erp_goods_medicine"
    __table_args__ = {"comment": "家庭‑药品"}

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True, comment="主键")
    medicine_type: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, index=True,
        comment="药品类型 0内服 1外用 2医疗器械 3保健品"
    )
    spec: Mapped[str | None] = mapped_column(String(256), nullable=True, comment="药品规格")
    manufacturer: Mapped[str | None] = mapped_column(String(256), nullable=True, comment="生产厂家")
    batch_no: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="生产批号")
    storage_mode: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="储存方式 0常温 1冷藏")
    usage_dosage: Mapped[str | None] = mapped_column(Text, nullable=True, comment="用法用量")
    contraindication: Mapped[str | None] = mapped_column(Text, nullable=True, comment="禁忌")
    is_prescription: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="是否处方药")


# ---------------- 子类2：食品 erp_goods_food ----------------
class ErpFoodModel(ErpBaseModel):
    """食品食材"""
    __tablename__ = "erp_goods_food"
    __table_args__ = {"comment": "家庭‑食品食材"}

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True, comment="主键")
    food_type: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, index=True,
        comment="食品类型 0生鲜果蔬 1零食 2速食 3饮料酒水 4速冻冷冻"
    )
    production_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="生产日期")
    shelf_life: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="保质期文字描述")
    storage_require: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="储存条件 0常温 1冷藏 2冷冻")


# ---------------- 子类3：家居用品 erp_goods_home ----------------
class ErpHomeGoodsModel(ErpBaseModel):
    """家居用品（纸巾、洗漱用品等）"""
    __tablename__ = "erp_goods_home"
    __table_args__ = {"comment": "家庭‑家居用品"}

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True, comment="主键")
    home_category: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, index=True,
        comment="家居分类 0洗漱个护 1清洁消杀 2纸类杂货"
    )


# ---------------- 子类4：电器 erp_goods_electric ----------------
class ErpElectricModel(ErpBaseModel):
    """家用电器"""
    __tablename__ = "erp_goods_electric"
    __table_args__ = {"comment": "家庭‑电器"}

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True, comment="主键")
    electric_category: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, index=True,
        comment="电器分类 0大家电 1小家电 2数码配件"
    )
    model_no: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="设备型号")
    warranty_expire: Mapped[date | None] = mapped_column(Date, nullable=True, comment="保修到期时间")


# ---------------- 子类5：调料 erp_goods_seasoning ----------------
class ErpSeasoningModel(ErpBaseModel):
    """厨房调料"""
    __tablename__ = "erp_goods_seasoning"
    __table_args__ = {"comment": "家庭‑厨房调料"}

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True, comment="主键")
    seasoning_type: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, index=True,
        comment="调料分类 0油盐酱醋 1香辛料 2复合调味酱"
    )
    production_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="生产日期")
    storage_require: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="储存条件 0常温 1冷藏")
