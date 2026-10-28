r"""三个家庭的演示物资种子脚本（每户 8 条，形态刻意做得不一样）。

它做什么
--------
``seed_demo.py`` 只造了「演示家庭」一个户，20 条药品/食品，形态比较整齐。
本脚本把另外两个空家庭也填上，并给演示家庭追加 8 条，目的是让 H5 演示里
**每个可见的界面状态都有数据撑着**，不至于点开列表全是同一副模样。

刻意覆盖的形态（注释里标了 `[覆盖 xx]`）：

- 未归类：``category=None``，分类筛选里落到「未归类」
- 零批次：建档但 ``batches=[]``，详情页批次区是空的
- 已耗尽批次：``remain_qty=0`` 且批次状态改成「已耗尽」
- 无有效期批次：详情页效期显示「未设置」，过期提醒不会误报
- 今天到期 / 刚过期 / 久已过期：三种红黄绿徽标的取值边界
- 小数剩余量：``remain_qty=1.5``，验证数量不是只显示整数
- 仅本人可见 / 私密：只在多人家庭（演示家庭B）里有意义
- 多录入人：同一家庭里分别用两个账号录，列表的「录入人」列才有两种值
- 跨家庭重名：「五常大米」在两个家庭各有一条，验证家庭数据隔离

家庭与账号（现状由脚本自己按名字查，不写死 id）
------------------------------------------------
- ``13900000001``（昵称「大禹」，user_id=40）：户主，名下「演示家庭」「大禹治水」，是「演示家庭B」的普通成员
- ``13900000002``（昵称「演示成员B」，user_id=41）：户主，名下「演示家庭B」
- 密码统一 ``Demo@12345``

为什么有的物品要用别的账号录
--------------------------------
``ErpItemService.create`` 里 ``owner_user_id`` 不填就是当前登录用户，
填别人的 id 需要 admin/owner 角色。所以「多录入人」不是靠传 ``owner_user_id`` 伪造的，
而是真的换两个 token 分别建档 —— 这样后台的「录入人」统计才和手工录入一致。

与 seed_demo.py 的分工
----------------------
- ``seed_demo.py``：建分类树、建扩展属性模板、建演示账号与「演示家庭」+ 20 条整齐数据；
- 本脚本：只往已有家庭里追加物品，分类和模板**复用** seed_demo 的成果。
  若发现所需分类链缺失，会退回调用 ``seed_demo.ensure_categories`` 补建（需要超管账号）。

幂等保证
--------
- 物品按「家庭 + 录入账号可见范围内的名称」查重，命中即跳过，不覆盖手工改过的数据；
- 私密/仅本人可见的物品只有在**它自己的录入账号**视角里才查得到，
  所以查重和创建都按 ``by`` 指定的账号分别进行；
- ``--refresh`` 只软删「名称在本脚本清单里、且归属人是这两个演示账号」的物品，
  演示家庭里 seed_demo 那 20 条、以及页面上手工加的物品都不会被碰
  （万一手工加的物品正好和某条清单项同名，脚本会打一行「[保留]」而不是替用户删）。
  删除用**归属人**的 token 执行 —— service 的按行判定只允许本人改删自己录的，
  普通成员拿别人的 token 删会被整批拒绝。

运行前置
--------
后端已启动、MySQL/Redis 就绪、``system_config:demo_enable`` 为 off、
且已经跑过 ``seed_demo.py``（分类与属性模板是它建的）。

运行方式（在 backend 目录下）::

    PYTHONUTF8=1 PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe app/plugin/module_app/erp/tests/seed_households.py

    # 重灌本脚本那 24 条（只删同名，不删别的）
    PYTHONUTF8=1 PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe app/plugin/module_app/erp/tests/seed_households.py --refresh
"""

import sys
from datetime import date, timedelta
from pathlib import Path

# 先加 tests 目录再 import seed_demo：它要在导入期把 cwd 切到 backend 根、
# 按 ENVIRONMENT 读 env/.env.dev，并准备好共享的 httpx 客户端与常量。
sys.path.insert(0, str(Path(__file__).resolve().parent))

import seed_demo as S  # noqa: E402

MOBILE_A = "13900000001"  # 大禹：演示家庭/大禹治水 的户主，演示家庭B 的成员
MOBILE_B = "13900000002"  # 演示成员B：演示家庭B 的户主

FAMILY_A = "演示家庭"  # seed_demo 已灌 20 条，这里只追加
FAMILY_B = "演示家庭B"  # 两人共同家庭，专门用来演示可见性与多录入人
FAMILY_C = "大禹治水"  # 单人家庭，换个生活场景（独居 + 健身 + 养猫）

# ══════════════════════════ 演示数据定义 ══════════════════════════
# 批次日期同样用「相对今天」描述（days_ago / expiry_days），不管哪天跑效果一致。
# 列含义见文件底部 build_payload / build_batch 的注释。

HOUSEHOLDS: list[dict] = [
    {
        "family_name": FAMILY_A,
        "default_by": MOBILE_A,
        "items": [
            {  # [覆盖 已耗尽批次 + 备注] 两条批次：先用完的那批留在档案里当记录
                "name": "藿香正气口服液",
                "category": ("药品", "肠胃消化"),
                "barcode": "6901000000110",
                "brand": "太极",
                "spec": "10ml×10支",
                "unit": "盒",
                "channel": "京东健康",
                "price": 22.5,
                "location": "家庭药箱",
                "attrs": {"dosage_form": "口服液", "rx": "否", "shelf_life": 24},
                "remark": "夏天中暑用；先买的那批已经喝完，批次留着当记录",
                "batches": [
                    {"quantity": 2, "remain_qty": 0, "unit_price": 22.5, "days_ago": 200, "expiry_days": 100, "depleted": True},
                    {"quantity": 1, "unit_price": 21.0, "days_ago": 20, "expiry_days": 300, "channel": "阿里健康大药房"},
                ],
            },
            {  # [覆盖 无有效期批次] 消毒液一般只标生产日期，没有到期日
                "name": "碘伏消毒液",
                "category": ("药品", "外用急救"),
                "barcode": "6901000000127",
                "brand": "利尔康",
                "spec": "100ml/瓶",
                "unit": "瓶",
                "channel": "线下药店",
                "price": 9.9,
                "location": "卫生间镜柜",
                "attrs": {"rx": "否"},
                "batches": [{"quantity": 1, "unit_price": 9.9, "days_ago": 40}],
            },
            {  # [覆盖 零批次] 先建档后补批次是常见顺序
                "name": "医用外科口罩",
                "category": ("药品", "外用急救"),
                "barcode": "6901000000134",
                "brand": "振德",
                "spec": "50只/盒",
                "unit": "盒",
                "channel": "天猫超市",
                "price": 19.9,
                "location": "储物间",
                "remark": "囤的货，还没拆封就没录批次",
                "batches": [],
            },
            {  # [覆盖 未归类] 血压计既不是药品也不是食品，分类树里没有它的位置
                "name": "电子血压计",
                "category": None,
                "barcode": "6901000000141",
                "brand": "欧姆龙",
                "spec": "上臂式 U10",
                "unit": "台",
                "channel": "京东自营",
                "price": 199.0,
                "location": "客厅抽屉",
                "remark": "双十一买的，主机保修五年，没有到期日",
                "batches": [{"quantity": 1, "unit_price": 199.0, "days_ago": 300}],
            },
            {  # [覆盖 久已过期] 过期 45 天，P3 的过期提醒会把它列为长期滞留
                "name": "山西老陈醋",
                "category": ("食品", "米面粮油"),
                "barcode": "6902000000119",
                "brand": "东湖",
                "spec": "500ml/瓶",
                "unit": "瓶",
                "channel": "永辉超市",
                "price": 12.8,
                "location": "厨房储物柜",
                "attrs": {"storage": "常温", "net_weight": 500, "sugar_free": "否"},
                "remark": "过期一个半月了，一直藏在柜子最里面",
                "batches": [{"quantity": 1, "unit_price": 12.8, "days_ago": 200, "expiry_days": -45}],
            },
            {  # [覆盖 今天到期] 边界值 expiry_days=0，列表徽标应该显示最紧急的一档
                "name": "三文鱼寿司拼盘",
                "category": ("食品", "生鲜食材"),
                "barcode": "6902000000126",
                "brand": "盒马工坊",
                "spec": "480g/盒",
                "unit": "盒",
                "channel": "盒马鲜生",
                "price": 59.9,
                "location": "冰箱冷藏",
                "attrs": {"storage": "冷藏", "net_weight": 480, "sugar_free": "否"},
                "remark": "今晚必须吃完",
                "batches": [{"quantity": 1, "unit_price": 59.9, "days_ago": 2, "expiry_days": 0}],
            },
            {  # [覆盖 小数剩余量 + 快到期] 按重量计的消耗品，剩余 1.5 组
                "name": "无糖希腊酸奶",
                "category": ("食品", "乳品饮料"),
                "barcode": "6902000000133",
                "brand": "和润",
                "spec": "100g×6杯",
                "unit": "组",
                "channel": "盒马鲜生",
                "price": 32.9,
                "location": "冰箱冷藏",
                "attrs": {"storage": "冷藏", "net_weight": 600, "sugar_free": "是"},
                "batches": [{"quantity": 3, "remain_qty": 1.5, "unit_price": 32.9, "days_ago": 6, "expiry_days": 18}],
            },
            {  # 普通样本：整箱常温奶，没有任何边界特征
                "name": "金典纯牛奶",
                "category": ("食品", "乳品饮料"),
                "barcode": "6902000000140",
                "brand": "伊利",
                "spec": "250ml×12盒",
                "unit": "箱",
                "channel": "山姆会员店",
                "price": 62.9,
                "location": "储物间",
                "attrs": {"storage": "常温", "net_weight": 3000, "sugar_free": "否"},
                "batches": [{"quantity": 2, "unit_price": 62.9, "days_ago": 10, "expiry_days": 150}],
            },
        ],
    },
    {
        # 两人家庭：可见性和「录入人」两种取值只有在这里才演示得出来。
        # 前 4 条由户主 41 录，后 4 条由成员 40 录（各自 token 分别建档）。
        "family_name": FAMILY_B,
        "default_by": MOBILE_B,
        "items": [
            {
                "name": "复方感冒灵颗粒",
                "category": ("药品", "感冒发热"),
                "barcode": "6903000000018",
                "brand": "999",
                "spec": "10g×9袋",
                "unit": "盒",
                "channel": "线下药店",
                "price": 16.5,
                "location": "家庭药箱",
                "attrs": {"dosage_form": "颗粒", "rx": "否", "shelf_life": 36},
                "batches": [{"quantity": 2, "unit_price": 16.5, "days_ago": 30, "expiry_days": 400}],
            },
            {  # [覆盖 已耗尽批次] 吃完不删档，方便复购时扫码命中
                "name": "维生素D3软胶囊",
                "category": ("药品", "维生素矿物质"),
                "barcode": "6903000000025",
                "brand": "星鲨",
                "spec": "400IU×30粒",
                "unit": "瓶",
                "channel": "天猫健康",
                "price": 39.0,
                "location": "药品柜",
                "attrs": {"dosage_form": "胶囊", "rx": "否", "shelf_life": 24},
                "remark": "上个月吃完了，档案留着下次扫码用",
                "batches": [{"quantity": 1, "remain_qty": 0, "unit_price": 39.0, "days_ago": 120, "expiry_days": 200, "depleted": True}],
            },
            {  # [覆盖 仅本人可见] member：其他成员列表里查不到，但仍算家庭库存
                "name": "布洛芬混悬液（儿童）",
                "category": ("药品", "感冒发热"),
                "barcode": "6903000000032",
                "brand": "美林",
                "spec": "100ml/瓶",
                "unit": "瓶",
                "channel": "京东健康",
                "price": 25.9,
                "location": "冰箱冷藏",
                "attrs": {"dosage_form": "口服液", "rx": "否", "shelf_life": 36},
                "visibility": "member",
                "remark": "仅本人可见：家庭B 的另一位成员（大禹）列表里查不到这条",
                "batches": [{"quantity": 1, "unit_price": 25.9, "days_ago": 15, "expiry_days": 500}],
            },
            {  # [覆盖 未归类 + 无有效期]
                "name": "电子体温计",
                "category": None,
                "barcode": "6903000000049",
                "brand": "鱼跃",
                "spec": "1支/盒",
                "unit": "支",
                "channel": "线下药店",
                "price": 12.0,
                "location": "家庭药箱",
                "remark": "医疗器械，分类树里没有对应类目",
                "batches": [{"quantity": 1, "unit_price": 12.0, "days_ago": 400}],
            },
            {  # ↓ 以下 4 条由成员 40（大禹）录入，于是家庭B 的列表里有两种「录入人」
                "name": "咖啡胶囊",
                "by": MOBILE_A,
                "category": None,
                "barcode": "6903000000056",
                "brand": "雀巢",
                "spec": "52颗/盒",
                "unit": "盒",
                "channel": "山姆会员店",
                "price": 69.9,
                "location": "公司茶水间",
                "remark": "我的口粮，随手放在公司",
                "batches": [{"quantity": 1, "unit_price": 69.9, "days_ago": 25, "expiry_days": 200}],
            },
            {  # [覆盖 跨家庭重名] 与演示家庭里那条「五常大米」同名，验证家庭数据隔离
                "name": "五常大米",
                "by": MOBILE_A,
                "category": ("食品", "米面粮油"),
                "barcode": "6903000000063",
                "brand": "金龙鱼",
                "spec": "5kg/袋",
                "unit": "袋",
                "channel": "永辉超市",
                "price": 55.0,
                "location": "厨房储物柜",
                "attrs": {"storage": "常温", "net_weight": 5000, "sugar_free": "否"},
                "remark": "和「演示家庭」里的同名大米是两条独立档案，切家庭就能看到不同数据",
                "batches": [{"quantity": 1, "unit_price": 55.0, "days_ago": 60, "expiry_days": 240}],
            },
            {  # [覆盖 私密] private：仅本人可见，且不参与家庭统计
                "name": "正山小种茶叶",
                "by": MOBILE_A,
                "category": ("食品", "乳品饮料"),
                "barcode": "6903000000070",
                "brand": "元正",
                "spec": "100g/罐",
                "unit": "罐",
                "channel": "天猫超市",
                "price": 128.0,
                "location": "书房茶叶罐",
                "attrs": {"storage": "常温", "net_weight": 100, "sugar_free": "是"},
                "visibility": "private",
                "remark": "私密物品：别人看不到，也不计入家庭统计",
                "batches": [{"quantity": 1, "unit_price": 128.0, "days_ago": 90, "expiry_days": 400}],
            },
            {  # [覆盖 小数剩余量]
                "name": "白桃味气泡水",
                "by": MOBILE_A,
                "category": ("食品", "乳品饮料"),
                "barcode": "6903000000084",
                "brand": "元气森林",
                "spec": "480ml×12瓶",
                "unit": "箱",
                "channel": "京东超市",
                "price": 49.9,
                "location": "储物间",
                "attrs": {"storage": "常温", "net_weight": 5760, "sugar_free": "是"},
                "remark": "上周开会剩下的半箱",
                "batches": [{"quantity": 1, "remain_qty": 0.5, "unit_price": 49.9, "days_ago": 5, "expiry_days": 150}],
            },
        ],
    },
    {
        # 单人家庭：换个生活场景（独居 + 健身 + 养猫），边界形态只补差异项。
        "family_name": FAMILY_C,
        "default_by": MOBILE_A,
        "items": [
            {  # [覆盖 未归类] 补剂在分类树里没有类目
                "name": "乳清蛋白粉（巧克力味）",
                "category": None,
                "barcode": "6904000000017",
                "brand": "汤臣倍健",
                "spec": "900g/罐",
                "unit": "罐",
                "channel": "天猫健康",
                "price": 268.0,
                "location": "厨房储物柜",
                "remark": "训练后一勺。不是药品也不是常规食品，先归到未归类",
                "batches": [{"quantity": 1, "unit_price": 268.0, "days_ago": 40, "expiry_days": 300}],
            },
            {
                "name": "复合维生素矿物质片",
                "category": ("药品", "维生素矿物质"),
                "barcode": "6904000000024",
                "brand": "善存",
                "spec": "100片/瓶",
                "unit": "瓶",
                "channel": "京东健康",
                "price": 89.0,
                "location": "办公桌抽屉",
                "attrs": {"dosage_form": "片剂", "rx": "否", "shelf_life": 36},
                "batches": [{"quantity": 1, "unit_price": 89.0, "days_ago": 100, "expiry_days": 620}],
            },
            {  # [覆盖 刚过期] 滴眼液开封后按 4 周算，过期 3 天正是该扔的状态
                "name": "玻璃酸钠滴眼液",
                "category": ("药品", "外用急救"),
                "barcode": "6904000000031",
                "brand": "瑞珠",
                "spec": "0.8ml×20支",
                "unit": "盒",
                "channel": "阿里健康大药房",
                "price": 29.5,
                "location": "床头柜",
                "attrs": {"rx": "否", "shelf_life": 24},
                "remark": "开封后一个月内用完，现在已经超三天了",
                "batches": [{"quantity": 1, "unit_price": 29.5, "days_ago": 31, "expiry_days": -3}],
            },
            {  # [覆盖 已耗尽批次]
                "name": "对乙酰氨基酚片",
                "category": ("药品", "感冒发热"),
                "barcode": "6904000000045",
                "brand": "泰诺林",
                "spec": "16片/盒",
                "unit": "盒",
                "channel": "线下药店",
                "price": 15.5,
                "location": "家庭药箱",
                "attrs": {"dosage_form": "片剂", "rx": "否", "shelf_life": 36},
                "remark": "上次发烧买的一盒已经吃完",
                "batches": [{"quantity": 1, "remain_qty": 0, "unit_price": 15.5, "days_ago": 150, "expiry_days": 400, "depleted": True}],
            },
            {  # [覆盖 久已过期] 同一物品既有正常批次也有过期批次，详情页两个状态并存
                "name": "红烧牛肉面",
                "category": ("食品", "米面粮油"),
                "barcode": "6904000000052",
                "brand": "康师傅",
                "spec": "12袋/箱",
                "unit": "箱",
                "channel": "京东超市",
                "price": 45.9,
                "location": "书桌下储物箱",
                "attrs": {"storage": "常温", "net_weight": 4320, "sugar_free": "否"},
                "remark": "整箱分两次买的，早的那箱过了最佳风味期",
                "batches": [
                    {"quantity": 1, "remain_qty": 0.3, "unit_price": 42.0, "days_ago": 200, "expiry_days": -20},
                    {"quantity": 1, "unit_price": 45.9, "days_ago": 15, "expiry_days": 180},
                ],
            },
            {  # [覆盖 小数剩余量 + 冷冻]
                "name": "冷冻鸡胸肉",
                "category": ("食品", "生鲜食材"),
                "barcode": "6904000000069",
                "brand": "泰森",
                "spec": "1kg/袋",
                "unit": "袋",
                "channel": "盒马鲜生",
                "price": 39.9,
                "location": "冰箱冷冻",
                "attrs": {"storage": "冷冻", "net_weight": 1000, "sugar_free": "否"},
                "batches": [{"quantity": 2, "remain_qty": 1.2, "unit_price": 39.9, "days_ago": 12, "expiry_days": 30}],
            },
            {  # [覆盖 零批次] 整箱还没到货，先把档案建好
                "name": "无糖可乐",
                "category": ("食品", "乳品饮料"),
                "barcode": "6904000000076",
                "brand": "可口可乐",
                "spec": "330ml×24罐",
                "unit": "箱",
                "channel": "山姆会员店",
                "price": 59.9,
                "location": "客厅小冰箱",
                "attrs": {"storage": "冷藏", "net_weight": 7920, "sugar_free": "是"},
                "remark": "整箱还没到货，先把档案建好",
                "batches": [],
            },
            {  # [覆盖 未归类] 宠物用品同样不在药品/食品两棵树里
                "name": "猫处方粮",
                "category": None,
                "barcode": "6904000000083",
                "brand": "皇家",
                "spec": "1.5kg/袋",
                "unit": "袋",
                "channel": "宠物医院",
                "price": 168.0,
                "location": "阳台储物柜",
                "remark": "医院开的处方粮，吃完要复诊",
                "batches": [{"quantity": 1, "remain_qty": 0.6, "unit_price": 168.0, "days_ago": 25, "expiry_days": 120}],
            },
        ],
    },
]


# ══════════════════════════ 数据组装 ══════════════════════════


def build_batch(spec: dict) -> dict:
    """把「相对天数」的批次描述翻译成接口要的绝对日期。

    和 ``seed_demo.build_batch`` 的区别有两个，所以没有直接复用：
    - ``expiry_days`` 缺省 → 不传 ``expiry_date``，用来造「无有效期」样本；
    - 支持 ``depleted`` 标记（真正落库要再改一次批次状态，见 mark_depleted）。
    """
    today = date.today()
    purchase_day = today - timedelta(days=spec["days_ago"])
    batch: dict = {
        "quantity": spec["quantity"],
        "purchase_time": f"{purchase_day.isoformat()}T10:00:00",
        "production_date": (purchase_day - timedelta(days=spec.get("prod_offset", 15))).isoformat(),
    }
    if spec.get("unit_price") is not None:
        batch["unit_price"] = spec["unit_price"]
    if spec.get("remain_qty") is not None:
        batch["remain_qty"] = spec["remain_qty"]
    if spec.get("channel"):
        batch["channel"] = spec["channel"]
    if spec.get("expiry_days") is not None:
        batch["expiry_date"] = (today + timedelta(days=spec["expiry_days"])).isoformat()
    if spec.get("remark"):
        batch["remark"] = spec["remark"]
    return batch


def build_payload(spec: dict, cats: dict[tuple[str, ...], int]) -> dict:
    """物品描述 → ``POST /erp/item/create`` 的请求体。

    ``category`` 为 None 时不传 ``category_id``（未归类），此时 ``attrs`` 也必须为空 ——
    service 的 ``_normalize_attrs`` 会拒绝「没有分类却带扩展属性」。
    """
    chain = spec.get("category")
    payload: dict = {"name": spec["name"], "visibility": spec.get("visibility", "family")}
    if chain:
        payload["category_id"] = cats[chain]
    for key, field in (
        ("barcode", "barcode"),
        ("brand", "brand"),
        ("spec", "spec"),
        ("unit", "unit"),
        ("channel", "purchase_channel"),
        ("price", "ref_price"),
        ("location", "location"),
        ("attrs", "attrs"),
        ("remark", "remark"),
    ):
        if spec.get(key) is not None:
            payload[field] = spec[key]
    payload["batches"] = [build_batch(batch) for batch in spec.get("batches", [])]
    return payload


def mark_depleted(token: str, family_id: int, created: dict, spec: dict) -> int:
    """把标了 ``depleted`` 的批次改成「已耗尽」，返回处理条数。

    为什么建档时不能一步到位：``ErpItemService._batch_payload`` 把新批次状态固定写成
    ``IN_USE``，「耗尽」是用完之后的动作，只能走 ``PUT /app/erp/item/batch/update/{id}``。

    对位不能按提交下标：批次接口返回是「新买的排前面」（见 crud.list_by_item），
    和 ``batches`` 的提交顺序无关，所以按 ``(进货数量, 有效期)`` 找那一行。
    """
    rows = created.get("batches", [])
    row_by_key = {(float(row["quantity"]), (row.get("expiry_date") or "")[:10]): row for row in rows}
    count = 0
    for batch_spec in spec.get("batches", []):
        if not batch_spec.get("depleted"):
            continue
        absolute = build_batch(batch_spec)
        key = (float(absolute["quantity"]), absolute.get("expiry_date", ""))
        row = row_by_key.get(key)
        if row is None:
            S.say(f"[警告] {spec['name']} 没匹配到待标记批次（quantity/expiry={key}），跳过")
            continue
        S.api.call("PUT", f"/app/erp/item/batch/update/{row['id']}", token=token, family_id=family_id, json_body={"status": 2})
        count += 1
    return count


# ══════════════════════════ 各阶段逻辑 ══════════════════════════


def login(mobile: str) -> tuple[str, int]:
    """C端密码登录，返回 (access_token, user_id)。

    这两个账号都已注册（seed_demo 建的），所以不走注册兜底链路：
    登录失败就是环境问题，报出来比自作主张重建更省事。
    """
    try:
        data = S.api.call("POST", "/app/login/password", json_body={"platform": "web", "account": mobile, "password": S.DEMO_PASSWORD})
    except SystemExit as exc:
        raise SystemExit(
            f"[中断] {mobile} 登录失败。本脚本假定演示账号已由 seed_demo.py 建好：\n"
            f"       .venv/Scripts/python.exe app/plugin/module_app/erp/tests/seed_demo.py\n       {exc}"
        ) from exc
    return data["access_token"], data["user_info"]["id"]


def locate_family(token: str, family_name: str, mobile: str) -> int:
    """按家庭名查 id；查不到就报错，脚本不擅自建家庭（家庭名是人工定的）。"""
    families = S.api.call("GET", "/app/erp/family/my", token=token)
    for family in families:
        if family.get("name") == family_name:
            return family["id"]
    raise SystemExit(
        f"[中断] 账号 {mobile} 名下没有「{family_name}」。"
        f"现有家庭：{[f.get('name') for f in families] or '无'}"
    )


def needed_chains() -> set[tuple[str, ...]]:
    """收集本脚本用到的分类链（None=未归类，不需要分类）。"""
    return {spec["category"] for household in HOUSEHOLDS for spec in household["items"] if spec.get("category")}


def ensure_categories_if_needed(admin_token: str) -> dict[tuple[str, ...], int]:
    """先只读分类树定位；缺分类才交给 seed_demo 建（会打印它自己的分节标题）。"""
    tree = S.api.call("GET", "/app/erp/admin/category/tree", token=admin_token)
    resolved = {chain: S.find_category(tree, chain) for chain in needed_chains()}
    if all(cid is not None for cid in resolved.values()):
        S.say(f"分类树齐全，复用 {len(resolved)} 个分类链")
        return resolved
    missing = sorted("／".join(chain) for chain, cid in resolved.items() if cid is None)
    S.say(f"缺分类 {'、'.join(missing)}，转由 seed_demo.ensure_categories 补建")
    return S.ensure_categories(admin_token)[0]


def occurrences(name: str, actors: dict[str, dict]) -> dict[int, dict]:
    """在所有录入账号的视角里找同名物品，返回 ``{item_id: 行数据}``。

    为什么要跨账号找：「仅本人可见 / 私密」的物品只有在它自己的录入人视角里才查得到，
    只看某一个账号的列表会漏掉它们，于是重复运行时会把同一条物品再建一遍。
    """
    found: dict[int, dict] = {}
    for actor in actors.values():
        row = actor["existing"].get(name)
        if row:
            found[row["id"]] = row
    return found


def ensure_items(household: dict, family_id: int, actors: dict[str, dict], owners: dict[int, str], cats: dict, refresh: bool) -> tuple[int, int]:
    """把一个家庭的物品灌进去，返回 (新建数, 跳过数)。

    两个按「人」走的细节：
    - 创建用 ``by`` 指定账号的 token，这样 ``owner_user_id`` 是真实的录入人；
    - 删除必须用**物品归属人**的 token：service 的按行判定只允许本人改删自己录的
      （普通成员不是 admin），拿别人的 token 删会整批被拒。
    """
    created = skipped = 0
    for spec in household["items"]:
        actor = actors[spec.get("by", household["default_by"])]
        hits = occurrences(spec["name"], actors)

        if refresh:
            for item_id, row in hits.items():
                recorder = owners.get(row.get("owner_user_id"))
                if recorder is None:
                    # 同名但不是演示账号录的：那是用户在页面上手工加的东西，脚本不碰
                    S.say(f"[保留] {spec['name']}（id={item_id}）归属 {row.get('owner_user_id')} 不是演示账号，不代删")
                    continue
                S.api.call("DELETE", "/app/erp/item/delete", token=actors[recorder]["token"], family_id=family_id, json_body=[item_id])
                S.say(f"预删 {spec['name']}（id={item_id}，录入人 {recorder[-3:]}）")
            hits = {}

        if hits:
            skipped += 1
            continue
        payload = build_payload(spec, cats)
        data = S.api.call("POST", "/app/erp/item/create", token=actor["token"], family_id=family_id, json_body=payload)
        depleted = mark_depleted(actor["token"], family_id, data, spec)
        chain = spec.get("category")
        label = "／".join(chain) if chain else "未归类"
        note = f"{len(spec.get('batches', []))} 个批次" + (f"（{depleted} 个已耗尽）" if depleted else "")
        S.say(f"新建 {label}｜{spec['name']}（{note}，录入人 {spec.get('by', household['default_by'])[-3:]}，可见性 {payload['visibility']}）")
        created += 1
    return created, skipped


# ══════════════════════════ 主流程 ══════════════════════════


def main() -> None:
    refresh = "--refresh" in sys.argv

    S.step("[1/4] 后台登录 + 分类树")  # 复用 seed_demo 的后台登录，它自己会打 [1/6] 标题
    admin_token = S.stage_admin_login()
    cats = ensure_categories_if_needed(admin_token)

    S.step("[2/4] C端账号登录")
    tokens: dict[str, dict] = {}
    for mobile in {MOBILE_A, MOBILE_B}:
        token, user_id = login(mobile)
        tokens[mobile] = {"token": token, "user_id": user_id}
        S.say(f"{mobile} 登录成功（user_id={user_id}）")
    # 归属人 user_id → 手机号：--refresh 时要用「物品主人」的 token 才能删掉它
    owners = {entry["user_id"]: mobile for mobile, entry in tokens.items()}

    total_created = total_skipped = 0
    reports: list[tuple[str, int, str, list[dict]]] = []

    for household in HOUSEHOLDS:
        family_name = household["family_name"]
        S.step(f"[3/4] {family_name}")
        # 家庭归属用该家庭默认账号去查：成员账号看不到别人的家庭，但三个家庭至少各有一个主人能查到
        family_id = locate_family(tokens[household["default_by"]]["token"], family_name, household["default_by"])
        S.say(f"家庭「{family_name}」id={family_id}")

        # 每个录入账号各拉一份「自己视角」的现有清单：可见性会按账号裁剪结果
        actors: dict[str, dict] = {}
        for spec in household["items"]:
            mobile = spec.get("by", household["default_by"])
            if mobile in actors:
                continue
            entry = tokens[mobile]
            rows = S.page_all("/app/erp/item/list", token=entry["token"], family_id=family_id)
            actors[mobile] = {"token": entry["token"], "existing": {row["name"]: row for row in rows}}
            S.say(f"{mobile} 视角现有物品 {len(rows)} 条")

        created, skipped = ensure_items(household, family_id, actors, owners, cats, refresh)
        total_created += created
        total_skipped += skipped
        # 汇总用家庭默认账号的视角：私密/仅本人可见会按人裁剪，别人的私人物品本来就不在这个列表里
        rows = S.page_all("/app/erp/item/list", token=tokens[household["default_by"]]["token"], family_id=family_id)
        reports.append((family_name, family_id, household["default_by"], rows))

    S.step("[4/4] 自检汇总")
    today = date.today()
    print("\n" + "═" * 66)
    print("  三个家庭的演示数据就绪")
    print("─" * 66)
    for family_name, family_id, mobile, rows in reports:
        expiring = [r for r in rows if r.get("nearest_expiry_date") and 0 <= (date.fromisoformat(r["nearest_expiry_date"]) - today).days <= 30]
        expired = [r for r in rows if r.get("nearest_expiry_date") and (date.fromisoformat(r["nearest_expiry_date"]) - today).days < 0]
        # batch_count 只统计「在用」批次，所以「真零批次」和「批次全部耗尽」都会落进这一档
        no_batch = [r for r in rows if not r.get("batch_count")]
        unclassified = [r for r in rows if not r.get("category_id")]
        owners = sorted({r.get("owner_name") or "?" for r in rows})
        private = [r for r in rows if r.get("visibility") != "family"]
        print(f"  {family_name}（id={family_id}）{mobile} 视角可见 {len(rows)} 条")
        print(f"    · 30 天内到期 {len(expiring)}｜已过期 {len(expired)}｜无在用批次 {len(no_batch)}｜未归类 {len(unclassified)}｜非全家可见 {len(private)}")
        print(f"    · 录入人：{'、'.join(owners)}")
        if expired:
            print("    · 已过期：" + "、".join(r["name"] for r in expired))
    print("─" * 66)
    print(f"  本次新建 {total_created} 条，跳过 {total_skipped} 条（同名已存在；重灌请加 --refresh）")
    print(f"  登录：{MOBILE_A} / {MOBILE_B}  密码均为 {S.DEMO_PASSWORD}")
    print("═" * 66)
    S.say("提示：私密与仅本人可见的物品不会出现在别人的列表和家庭统计里，换账号登录才能看到差异。")


if __name__ == "__main__":
    main()
