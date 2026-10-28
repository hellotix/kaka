"""ERP 演示数据种子脚本（10 条药品 + 10 条食品）。

它做什么
--------
给本地演示环境（H5 demo / Swagger 手测 / 截图）灌一份「像真的」家庭数据：

1. 后台分类树：药品、食品 两棵一级树，各挂 4 个二级分类
2. 后台扩展属性模板：药品「剂型 / 处方药 / 保质期」+ 食品「保存方式 / 净含量 / 无糖」
   （品牌是一等字段，不做模板，见 ATTR_TEMPLATES 上方注释）
3. C端演示账号（固定手机号与密码）与「演示家庭」
4. 20 条物品档案（10 药品 + 10 食品），每条带 1~2 个批次；
   效期刻意留了「快到期」与「已过期」样本，方便演示过期提醒

与 smoke_http.py 的分工
-----------------------
- smoke_* 是测试：数据带时间戳后缀、跑完就删、以「通过 / 失败」断言收尾。
- 本脚本是种子：名字固定、重复运行**复用已有数据**、以「新建 / 复用 / 跳过」收尾。
  想重来一遍可以加 ``--reset``（软删演示家庭的全部物品后重新灌入）。

固定身份（H5 demo 直接用它登录）
--------------------------------
- 手机号 ``13900000001`` / 密码 ``Demo@12345``（昵称「演示户主」）
- 家庭名「演示家庭」
- 若该手机号已注册但密码不是 ``Demo@12345``，脚本会明确报错而不是偷偷改密码 ——
  「演示账号密码被人改过」属于需要人工确认的状态，静默重置会掩盖真实问题。

幂等保证（重复运行不会堆数据）
------------------------------
- 分类：按「父链 + 名字」在后台分类树里查，命中即复用；
- 属性模板：按 ``(category_id, code)`` 查，命中即复用；
- 物品：按「演示家庭内的名称」查，命中即跳过（不会覆盖在页面上手工改过的演示数据）；
- 演示账号 / 家庭：能登录、能读到即复用。

反过来脚本**只增不删**：改小 ``ATTR_TEMPLATES`` 或 ``CATEGORY_TREE`` 后重跑，
旧库里多余的模板/分类仍然在，C端详情页就会多出一条取不到值的空属性
（例如曾经挂过又删掉的全局「品牌」）。清理走后台接口
``DELETE /api/v1/app/erp/admin/attr/delete``，body 是 ID 数组，软删除。

运行前置
--------
1. 后端已启动：``.venv/Scripts/python.exe main.py run --env=dev``（默认 8001 端口）
2. MySQL、Redis 就绪
3. 超管 ``super / 123456`` 可用
4. ``system_config:demo_enable`` 为 off —— 演示模式会拦掉全部非 GET 请求，种子灌不进去
   （脚本检测到该拦截时会给出明确提示）

运行方式（在 backend 目录下）::

    PYTHONUTF8=1 PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe app/plugin/module_app/erp/tests/seed_demo.py

    # 先把演示家庭里的物品软删一遍，再重新灌入
    PYTHONUTF8=1 PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe app/plugin/module_app/erp/tests/seed_demo.py --reset
"""

import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
import redis as sync_redis
from loguru import logger

BACKEND_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)  # settings 用相对路径读 env/.env.dev
os.environ.setdefault("ENVIRONMENT", "dev")  # settings 在导入期按该变量选择 env 文件

from app.config.setting import settings  # noqa: E402
from app.plugin.module_app.erp.core.constants import FAMILY_HEADER  # noqa: E402
from app.plugin.module_app.login.core.constants import (  # noqa: E402
    sms_code_key,
    sms_daily_key,
    sms_interval_key,
)

# settings 导入期给 loguru 装了 DEBUG 级 sink，httpcore 会把每条请求报文都写出来，
# 把脚本自己的报告淹掉。本脚本是独立进程，直接移除 sink；不会影响正在运行的后端。
logger.remove()

REDIS_HOST = settings.REDIS_HOST
REDIS_PORT = settings.REDIS_PORT
REDIS_DB = settings.REDIS_DB_NAME
REDIS_PASSWORD = settings.REDIS_PASSWORD

BASE_URL = "http://127.0.0.1:8001/api/v1"
DOCS_REFERER = f"{BASE_URL}/docs"  # 后台登录豁免图形验证码（非生产环境特性）

ADMIN_ACCOUNT = ("super", "123456")
DEMO_MOBILE = "13900000001"
DEMO_PASSWORD = "Demo@12345"
DEMO_NICKNAME = "演示户主"
DEMO_FAMILY_NAME = "演示家庭"

# ══════════════════════════ 演示数据定义 ══════════════════════════
# 说明：批次日期一律用「相对今天的天数」描述（days_ago / expiry_days），
# 这样不管哪天跑，数据里的「快过期 / 已过期」样本都保持同样的演示效果。

# 分类树：一级 → 二级（三级演示用前端手工建即可，这里保持树形简洁）
CATEGORY_TREE: dict[str, list[str]] = {
    "药品": ["感冒发热", "肠胃消化", "维生素矿物质", "外用急救"],
    "食品": ["乳品饮料", "米面粮油", "休闲零食", "生鲜食材"],
}

DOSAGE_OPTIONS = ["片剂", "胶囊", "颗粒", "散剂", "口服液", "喷雾剂", "贴剂"]
STORAGE_OPTIONS = ["常温", "冷藏", "冷冻"]
YES_NO_OPTIONS = ["是", "否"]


def _options(values: list[str]) -> list[dict]:
    """候选项的 value 与 label 都用中文：演示时 attrs 里的值直接可读。"""
    return [{"value": value, "label": value} for value in values]


# 属性模板：分类链为 None 表示全局模板（所有分类继承）
# 列含义：(分类链, code, label, type, unit, options, is_required, is_filterable, sort, default_value)
# 刻意不放「品牌」：它是 erp_item 的一等字段（brand 列），表单和详情页已经在显示了，
# 再挂一个同 code 的模板就会出现两条「品牌」（一条填一等字段、一条进 attrs JSON）。
ATTR_TEMPLATES: list[tuple] = [
    (("药品",), "dosage_form", "剂型", "select", None, _options(DOSAGE_OPTIONS), False, True, 2, None),
    (("药品",), "rx", "处方药", "select", None, _options(YES_NO_OPTIONS), False, True, 3, "否"),
    (("药品",), "shelf_life", "保质期", "number", "月", None, False, False, 4, None),
    (("食品",), "storage", "保存方式", "select", None, _options(STORAGE_OPTIONS), False, True, 2, "常温"),
    (("食品",), "net_weight", "净含量", "number", "g", None, False, False, 3, None),
    (("食品",), "sugar_free", "无糖", "select", None, _options(YES_NO_OPTIONS), False, True, 4, "否"),
]

# 物品清单：每条含 1~2 个批次；prod_offset 是「生产日 = 购买日 - N 天」，
# 默认 15；药品保质期长，统一给 120 更符合「买到的药已出厂几个月」的直觉。
ITEMS: list[dict] = [
    # ── 药品 ──
    {
        "name": "布洛芬缓释胶囊",
        "brand": "芬必得",
        "spec": "0.3g×20粒",
        "unit": "盒",
        "category": ("药品", "感冒发热"),
        "barcode": "6901000000011",
        "location": "家庭药箱",
        "channel": "京东健康",
        "ref_price": 32.8,
        "attrs": {"dosage_form": "胶囊", "rx": "否", "shelf_life": 24},
        "batches": [
            {"quantity": 2, "remain_qty": 1, "unit_price": 32.8, "days_ago": 120, "expiry_days": 12, "channel": "京东健康", "prod_offset": 180},
            {"quantity": 1, "unit_price": 29.9, "days_ago": 10, "expiry_days": 400, "channel": "阿里健康大药房", "prod_offset": 60},
        ],
    },
    {
        "name": "连花清瘟胶囊",
        "brand": "以岭药业",
        "spec": "0.35g×24粒",
        "unit": "盒",
        "category": ("药品", "感冒发热"),
        "barcode": "6901000000028",
        "location": "家庭药箱",
        "channel": "阿里健康大药房",
        "ref_price": 28.5,
        "attrs": {"dosage_form": "胶囊", "rx": "否", "shelf_life": 30},
        "batches": [{"quantity": 2, "unit_price": 28.5, "days_ago": 60, "expiry_days": 500, "channel": "阿里健康大药房", "prod_offset": 120}],
    },
    {
        "name": "复方氨酚烷胺片",
        "brand": "感康",
        "spec": "12片/盒",
        "unit": "盒",
        "category": ("药品", "感冒发热"),
        "barcode": "6901000000035",
        "location": "家庭药箱",
        "channel": "线下药店",
        "ref_price": 18.9,
        "attrs": {"dosage_form": "片剂", "rx": "否", "shelf_life": 36},
        "batches": [{"quantity": 1, "unit_price": 18.9, "days_ago": 90, "expiry_days": 620, "channel": "同仁堂药店", "prod_offset": 180}],
    },
    {
        "name": "蒙脱石散",
        "brand": "思密达",
        "spec": "3g×10袋",
        "unit": "盒",
        "category": ("药品", "肠胃消化"),
        "barcode": "6901000000042",
        "location": "家庭药箱",
        "channel": "京东健康",
        "ref_price": 25.0,
        "attrs": {"dosage_form": "散剂", "rx": "否", "shelf_life": 36},
        "batches": [{"quantity": 1, "unit_price": 25.0, "days_ago": 45, "expiry_days": 700, "channel": "京东健康", "prod_offset": 180}],
    },
    {
        "name": "奥美拉唑肠溶胶囊",
        "brand": "洛赛克",
        "spec": "20mg×14粒",
        "unit": "盒",
        "category": ("药品", "肠胃消化"),
        "barcode": "6901000000059",
        "location": "药品柜",
        "channel": "阿里健康大药房",
        "ref_price": 35.6,
        "attrs": {"dosage_form": "胶囊", "rx": "是", "shelf_life": 30},
        "batches": [{"quantity": 1, "unit_price": 35.6, "days_ago": 30, "expiry_days": 540, "channel": "阿里健康大药房", "prod_offset": 120}],
    },
    {
        "name": "枯草杆菌二联活菌颗粒",
        "brand": "妈咪爱",
        "spec": "1g×20袋",
        "unit": "盒",
        "category": ("药品", "肠胃消化"),
        "barcode": "6901000000066",
        "location": "冰箱冷藏",
        "channel": "京东健康",
        "ref_price": 46.0,
        "attrs": {"dosage_form": "颗粒", "rx": "否", "shelf_life": 24},
        "batches": [{"quantity": 1, "unit_price": 46.0, "days_ago": 20, "expiry_days": 430, "channel": "京东健康", "prod_offset": 90}],
    },
    {
        "name": "维生素C咀嚼片",
        "brand": "汤臣倍健",
        "spec": "100片/瓶",
        "unit": "瓶",
        "category": ("药品", "维生素矿物质"),
        "barcode": "6901000000073",
        "location": "药品柜",
        "channel": "天猫健康",
        "ref_price": 89.0,
        "attrs": {"dosage_form": "片剂", "rx": "否", "shelf_life": 24},
        "batches": [{"quantity": 1, "unit_price": 89.0, "days_ago": 150, "expiry_days": 300, "channel": "天猫健康", "prod_offset": 120}],
    },
    {
        "name": "碳酸钙D3片",
        "brand": "钙尔奇",
        "spec": "60片/瓶",
        "unit": "瓶",
        "category": ("药品", "维生素矿物质"),
        "barcode": "6901000000080",
        "location": "药品柜",
        "channel": "天猫健康",
        "ref_price": 98.0,
        "attrs": {"dosage_form": "片剂", "rx": "否", "shelf_life": 36},
        "batches": [{"quantity": 2, "unit_price": 98.0, "days_ago": 100, "expiry_days": 800, "channel": "天猫健康", "prod_offset": 180}],
    },
    {
        "name": "云南白药气雾剂",
        "brand": "云南白药",
        "spec": "85g+30g",
        "unit": "套",
        "category": ("药品", "外用急救"),
        "barcode": "6901000000097",
        "location": "家庭药箱",
        "channel": "线下药店",
        "ref_price": 42.5,
        "attrs": {"dosage_form": "喷雾剂", "rx": "否", "shelf_life": 36},
        "batches": [{"quantity": 1, "unit_price": 42.5, "days_ago": 200, "expiry_days": 600, "channel": "同仁堂药店", "prod_offset": 180}],
    },
    {
        "name": "苯扎氯铵贴（创可贴）",
        "brand": "邦迪",
        "spec": "100片/盒",
        "unit": "盒",
        "category": ("药品", "外用急救"),
        "barcode": "6901000000103",
        "location": "家庭药箱",
        "channel": "永辉超市",
        "ref_price": 19.9,
        "attrs": {"dosage_form": "贴剂", "rx": "否", "shelf_life": 36},
        "batches": [{"quantity": 1, "unit_price": 19.9, "days_ago": 400, "expiry_days": 900, "channel": "永辉超市", "prod_offset": 180}],
    },
    # ── 食品 ──
    {
        "name": "特仑苏纯牛奶",
        "brand": "蒙牛",
        "spec": "250ml×12盒",
        "unit": "箱",
        "category": ("食品", "乳品饮料"),
        "barcode": "6902000000012",
        "location": "冰箱冷藏",
        "channel": "山姆会员店",
        "ref_price": 79.9,
        "attrs": {"storage": "冷藏", "net_weight": 3000, "sugar_free": "否"},
        "batches": [
            {"quantity": 2, "remain_qty": 1, "unit_price": 79.9, "days_ago": 20, "expiry_days": 120, "channel": "山姆会员店", "prod_offset": 10},
            {"quantity": 1, "unit_price": 74.9, "days_ago": 5, "expiry_days": 150, "channel": "京东超市", "prod_offset": 5},
        ],
    },
    {
        "name": "安慕希希腊风味酸奶",
        "brand": "伊利",
        "spec": "205g×12盒",
        "unit": "箱",
        "category": ("食品", "乳品饮料"),
        "barcode": "6902000000029",
        "location": "冰箱冷藏",
        "channel": "永辉超市",
        "ref_price": 69.9,
        "attrs": {"storage": "冷藏", "net_weight": 2460, "sugar_free": "否"},
        # 快过期样本：6 天后到期
        "batches": [{"quantity": 1, "unit_price": 69.9, "days_ago": 15, "expiry_days": 6, "channel": "永辉超市", "prod_offset": 3}],
    },
    {
        "name": "农夫山泉饮用天然水",
        "brand": "农夫山泉",
        "spec": "550ml×24瓶",
        "unit": "箱",
        "category": ("食品", "乳品饮料"),
        "barcode": "6902000000036",
        "location": "储物间",
        "channel": "京东超市",
        "ref_price": 35.0,
        "attrs": {"storage": "常温", "net_weight": 13200, "sugar_free": "否"},
        "batches": [{"quantity": 2, "unit_price": 35.0, "days_ago": 30, "expiry_days": 365, "channel": "京东超市", "prod_offset": 30}],
    },
    {
        "name": "五常大米",
        "brand": "金龙鱼",
        "spec": "5kg/袋",
        "unit": "袋",
        "category": ("食品", "米面粮油"),
        "barcode": "6902000000043",
        "location": "厨房储物柜",
        "channel": "永辉超市",
        "ref_price": 49.9,
        "attrs": {"storage": "常温", "net_weight": 5000, "sugar_free": "否"},
        "batches": [{"quantity": 1, "unit_price": 49.9, "days_ago": 40, "expiry_days": 240, "channel": "永辉超市", "prod_offset": 60}],
    },
    {
        "name": "压榨一级花生油",
        "brand": "鲁花",
        "spec": "5L/桶",
        "unit": "桶",
        "category": ("食品", "米面粮油"),
        "barcode": "6902000000050",
        "location": "厨房储物柜",
        "channel": "山姆会员店",
        "ref_price": 139.0,
        "attrs": {"storage": "常温", "net_weight": 5000, "sugar_free": "否"},
        "batches": [{"quantity": 1, "unit_price": 139.0, "days_ago": 25, "expiry_days": 540, "channel": "山姆会员店", "prod_offset": 60}],
    },
    {
        "name": "原味薯片",
        "brand": "乐事",
        "spec": "104g/袋",
        "unit": "袋",
        "category": ("食品", "休闲零食"),
        "barcode": "6902000000067",
        "location": "客厅零食柜",
        "channel": "京东超市",
        "ref_price": 8.5,
        "attrs": {"storage": "常温", "net_weight": 104, "sugar_free": "否"},
        # 已过期样本：10 天前到期（P3 过期提醒上线后会被扫出来）
        "batches": [{"quantity": 1, "unit_price": 8.5, "days_ago": 60, "expiry_days": -10, "channel": "京东超市", "prod_offset": 30}],
    },
    {
        "name": "每日坚果",
        "brand": "三只松鼠",
        "spec": "750g/盒",
        "unit": "盒",
        "category": ("食品", "休闲零食"),
        "barcode": "6902000000074",
        "location": "客厅零食柜",
        "channel": "天猫超市",
        "ref_price": 89.9,
        "attrs": {"storage": "常温", "net_weight": 750, "sugar_free": "是"},
        "batches": [{"quantity": 1, "unit_price": 89.9, "days_ago": 35, "expiry_days": 150, "channel": "天猫超市", "prod_offset": 30}],
    },
    {
        "name": "丝滑牛奶巧克力",
        "brand": "德芙",
        "spec": "84g/碗",
        "unit": "碗",
        "category": ("食品", "休闲零食"),
        "barcode": "6902000000081",
        "location": "客厅零食柜",
        "channel": "京东超市",
        "ref_price": 15.9,
        "attrs": {"storage": "常温", "net_weight": 84, "sugar_free": "否"},
        "batches": [{"quantity": 2, "remain_qty": 1, "unit_price": 15.9, "days_ago": 80, "expiry_days": 200, "channel": "京东超市", "prod_offset": 60}],
    },
    {
        "name": "鲜鸡蛋",
        "brand": "正大",
        "spec": "30枚/盒",
        "unit": "盒",
        "category": ("食品", "生鲜食材"),
        "barcode": "6902000000098",
        "location": "冰箱冷藏",
        "channel": "盒马鲜生",
        "ref_price": 29.9,
        "attrs": {"storage": "冷藏", "net_weight": 1500, "sugar_free": "否"},
        "batches": [{"quantity": 1, "unit_price": 29.9, "days_ago": 5, "expiry_days": 25, "channel": "盒马鲜生", "prod_offset": 2}],
    },
    {
        "name": "挪威三文鱼刺身",
        "brand": "挪威海产",
        "spec": "200g/盒",
        "unit": "盒",
        "category": ("食品", "生鲜食材"),
        "barcode": "6902000000104",
        "location": "冰箱冷冻",
        "channel": "盒马鲜生",
        "ref_price": 68.0,
        "attrs": {"storage": "冷冻", "net_weight": 200, "sugar_free": "否"},
        # 快过期样本：4 天后到期
        "batches": [{"quantity": 1, "unit_price": 68.0, "days_ago": 3, "expiry_days": 4, "channel": "盒马鲜生", "prod_offset": 2}],
    },
]


# ══════════════════════════ 输出与 HTTP 封装 ══════════════════════════


def step(title: str) -> None:
    """打印分节标题。"""
    print(f"\n{title}")


def say(text: str) -> None:
    """打印缩进的明细行。"""
    print(f"  {text}")


def payload_of(resp: httpx.Response) -> dict:
    """解析响应 JSON，解析失败时返回原文片段（便于看到 HTML 错误页）。

    注意：FastAPI 的 422 校验错误体是一个 **list**（每个元素一条错误），
    这里统一兜底成 dict，避免调用处 ``body.get(...)`` 直接抛 AttributeError。
    """
    try:
        parsed = resp.json()
    except Exception:
        return {"_raw": resp.text[:300]}
    if not isinstance(parsed, dict):
        return {"_raw": str(parsed)[:300]}
    return parsed


def brief(payload: dict) -> str:
    """把响应压成一行摘要，用于报错提示。"""
    if "_raw" in payload:
        return payload["_raw"][:160]
    body = payload.get("data")
    body_txt = str(body)
    if len(body_txt) > 200:
        body_txt = body_txt[:200] + "..."
    return f"code={payload.get('code')} msg={payload.get('msg')} data={body_txt}"


class Api:
    """极简 HTTP 客户端：统一注入令牌与 ``X-Family-Id`` 头。"""

    def __init__(self, base_url: str) -> None:
        self.client = httpx.Client(base_url=base_url, timeout=30.0, follow_redirects=False)

    def __call__(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        family_id: int | str | None = None,
        referer: str | None = None,
        json_body: object | None = None,
        form: dict | None = None,
    ) -> tuple[int, dict]:
        """发请求并返回 ``(HTTP状态码, 响应体)``。

        ``form`` 用于后台登录这类 OAuth2 表单接口（``application/x-www-form-urlencoded``），
        与 ``json_body`` 二选一。
        """
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if family_id is not None:
            headers[FAMILY_HEADER] = str(family_id)
        if referer:
            headers["Referer"] = referer
        resp = self.client.request(method, path, headers=headers, json=json_body, data=form)
        return resp.status_code, payload_of(resp)

    def call(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        family_id: int | str | None = None,
        referer: str | None = None,
        json_body: object | None = None,
    ) -> object:
        """发请求并断言成功（2xx 且业务 success=true），返回 ``data`` 段。

        种子脚本与测试脚本的区别：这里失败即中断 —— 少灌一条数据比灌半份数据更难排查。
        """
        status, body = self(method, path, token=token, family_id=family_id, referer=referer, json_body=json_body)
        msg = str(body.get("msg") or "")
        if not (200 <= status < 300) or body.get("success") is not True:
            if "演示环境" in msg:
                raise SystemExit(
                    f"[中断] {method} {path} 被演示模式拦截（{msg}）。\n"
                    "       请到后台把系统参数 demo_enable 关掉后重跑本脚本。"
                )
            raise SystemExit(f"[中断] {method} {path} -> HTTP {status} | {brief(body)}")
        return body.get("data")


api = Api(BASE_URL)

# 分页接口的 page_size 上限是 100（见 app/core/base_schema.py 的 PaginationQueryParam），
# 想拉全量就必须翻页 —— 这里封一个循环翻页的辅助函数，避免各处重复写。
PAGE_SIZE_MAX = 100


def page_all(path: str, *, token: str | None = None, family_id: int | str | None = None) -> list[dict]:
    """按 100/页循环拉取分页接口，直到取完，返回全部 items。"""
    items: list[dict] = []
    page_no = 1
    while True:
        page: dict = api.call("GET", f"{path}?page_no={page_no}&page_size={PAGE_SIZE_MAX}", token=token, family_id=family_id)
        rows = page.get("items", [])
        items.extend(rows)
        if len(rows) < PAGE_SIZE_MAX:
            return items
        page_no += 1


# ══════════════════════════ 各阶段逻辑 ══════════════════════════


def stage_admin_login() -> str:
    """后台超管登录，返回令牌（后续运营配置接口都要它）。"""
    step("[1/6] 后台登录（超管）")
    status, body = api(
        "POST",
        "/system/auth/login",
        referer=DOCS_REFERER,
        form={"username": ADMIN_ACCOUNT[0], "password": ADMIN_ACCOUNT[1]},
    )
    token = body.get("access_token") or (body.get("data") or {}).get("access_token")
    if status != 200 or not token:
        raise SystemExit(f"[中断] 超管登录失败 -> HTTP {status} | {brief(body)}")
    say(f"超管 {ADMIN_ACCOUNT[0]} 登录成功")
    return token


def find_category(nodes: list[dict], chain: tuple[str, ...]) -> int | None:
    """在分类树里按「名字链」找分类 id，找不到返回 None。"""
    current = nodes
    found_id: int | None = None
    for name in chain:
        found_id = None
        for node in current:
            if node.get("name") == name:
                found_id = node.get("id")
                current = node.get("children") or []
                break
        if found_id is None:
            return None
    return found_id


def ensure_categories(admin_token: str) -> tuple[dict[tuple[str, ...], int], int, int]:
    """确保分类树存在，返回 (分类链→id 映射, 新建数, 复用数)。

    逐级向下查：命中的层级复用，缺失的层级创建；每次创建后重拉一次树
    （只有十来个分类，请求数可以忽略，换来逻辑上「以服务端为准」）。
    """
    step("[2/6] 后台分类树（药品 / 食品）")
    ids: dict[tuple[str, ...], int] = {}
    created = reused = 0

    tree: list[dict] = api.call("GET", "/app/erp/admin/category/tree", token=admin_token)
    for root_name, children in CATEGORY_TREE.items():
        for chain in [(root_name,)] + [(root_name, child) for child in children]:
            found = find_category(tree, chain)
            if found is not None:
                ids[chain] = found
                reused += 1
                continue
            payload: dict = {"name": chain[-1], "sort": 1 if len(chain) == 1 else len(ids)}
            if len(chain) > 1:
                payload["parent_id"] = ids[(chain[0],)]
            data = api.call("POST", "/app/erp/admin/category/create", token=admin_token, json_body=payload)
            ids[chain] = data["id"]
            created += 1
            tree = api.call("GET", "/app/erp/admin/category/tree", token=admin_token)
    say(f"分类就绪：新建 {created} 个，复用 {reused} 个；一级树：{list(CATEGORY_TREE)}")
    return ids, created, reused


def ensure_attrs(admin_token: str, cats: dict[tuple[str, ...], int]) -> tuple[int, int]:
    """确保扩展属性模板存在，返回 (新建数, 复用数)。

    查重键是 ``(category_id, code)``：同一个 code 挂在全局或不同分类下是三个模板，不能只按 code 查。
    """
    step("[3/6] 后台扩展属性模板")
    existing = {(item.get("category_id"), item.get("code")) for item in page_all("/app/erp/admin/attr/list", token=admin_token)}

    created = reused = 0
    for chain, code, label, attr_type, unit, options, required, filterable, sort, default in ATTR_TEMPLATES:
        category_id = cats[chain] if chain else None
        if (category_id, code) in existing:
            say(f"复用属性模板 {code}（{label}）")
            reused += 1
            continue
        payload = {
            "category_id": category_id,
            "code": code,
            "label": label,
            "type": attr_type,
            "unit": unit,
            "options": options,
            "is_required": required,
            "is_filterable": filterable,
            "sort": sort,
            "default_value": default,
        }
        api.call("POST", "/app/erp/admin/attr/create", token=admin_token, json_body=payload)
        say(f"新建属性模板 {code}（{label}）")
        created += 1
    say(f"属性模板就绪：新建 {created} 个，复用 {reused} 个")
    return created, reused


def ensure_demo_user() -> tuple[str, int]:
    """确保演示账号可登录，返回 (access_token, user_id)。

    先走密码登录（已注册的正常情况，无任何副作用）；
    失败再走「发码 → 读 Redis 取码 → 注册」链路（本机短信是 mock，验证码落在 Redis）。
    """
    step("[4/6] C端演示账号")
    status, body = api(
        "POST",
        "/app/login/password",
        json_body={"platform": "web", "account": DEMO_MOBILE, "password": DEMO_PASSWORD},
    )
    if status == 200 and body.get("success") is True:
        data = body["data"]
        say(f"复用演示账号 {DEMO_MOBILE}（昵称「{data['user_info'].get('nickname')}」）")
        return data["access_token"], data["user_info"]["id"]

    say(f"密码登录未成功（{body.get('msg')}），按新账号注册")

    cache = sync_redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, password=REDIS_PASSWORD or None, decode_responses=True)
    # 清掉短信频控键：同一手机号当天重复试跑脚本时也能发出验证码
    cache.delete(sms_interval_key(DEMO_MOBILE), sms_daily_key(DEMO_MOBILE, time.strftime("%Y%m%d", time.gmtime())))
    api.call("POST", "/app/login/sms/send", json_body={"mobile": DEMO_MOBILE, "scene": "register"})

    code = cache.get(sms_code_key("register", DEMO_MOBILE))
    if not code:
        raise SystemExit("[中断] Redis 里没读到注册验证码，注册链路中断")
    status, body = api(
        "POST",
        "/app/login/register",
        json_body={"platform": "web", "mobile": DEMO_MOBILE, "password": DEMO_PASSWORD, "code": code, "nickname": DEMO_NICKNAME},
    )
    if status in (200, 201) and body.get("success") is True:
        data = body["data"]
        say(f"新建演示账号 {DEMO_MOBILE}（昵称「{DEMO_NICKNAME}」）")
        return data["access_token"], data["user_info"]["id"]

    raise SystemExit(
        f"[中断] 演示账号注册失败 -> HTTP {status} | {brief(body)}\n"
        f"       提示：{DEMO_MOBILE} 可能已被注册但密码不是 {DEMO_PASSWORD}（密码被人改过需要人工确认，脚本不擅自重置）。"
    )


def ensure_demo_family(app_token: str) -> int:
    """确保「演示家庭」存在且演示账号是成员，返回家庭 id。"""
    step("[5/6] 演示家庭")
    families: list[dict] = api.call("GET", "/app/erp/family/my", token=app_token)
    for family in families:
        if family.get("name") == DEMO_FAMILY_NAME:
            say(f"复用家庭「{DEMO_FAMILY_NAME}」（id={family['id']}，我的角色 {family.get('my_role')}）")
            return family["id"]
    data = api.call("POST", "/app/erp/family/create", token=app_token, json_body={"name": DEMO_FAMILY_NAME})
    say(f"新建家庭「{DEMO_FAMILY_NAME}」（id={data['id']}，邀请码 {data.get('invite_code')}）")
    return data["id"]


def reset_items(app_token: str, family_id: int) -> int:
    """软删演示家庭里的全部物品（``--reset`` 用），返回删除条数。

    走 C端删除接口而不是直连数据库：软删会同时清理批次，
    且软删后同名物品可以重新创建（查重只看未删除记录）。
    """
    ids: list[int] = [row["id"] for row in page_all("/app/erp/item/list", token=app_token, family_id=family_id)]
    if ids:
        api.call("DELETE", "/app/erp/item/delete", token=app_token, family_id=family_id, json_body=ids)
    say(f"已软删演示家庭的 {len(ids)} 条物品（批次一并软删）")
    return len(ids)


def build_batch(spec: dict) -> dict:
    """把「相对天数」的批次描述翻译成接口要的绝对日期。"""
    today = date.today()
    purchase_day = today - timedelta(days=spec["days_ago"])
    batch: dict = {
        "quantity": spec["quantity"],
        "unit_price": spec["unit_price"],
        "purchase_time": f"{purchase_day.isoformat()}T10:00:00",
        "channel": spec.get("channel"),
        # 生产日按「购买日往前推」估算：药品给 120~180 天，生鲜只给 2~3 天
        "production_date": (purchase_day - timedelta(days=spec.get("prod_offset", 15))).isoformat(),
        # 到期日以「今天 + N 天」计算，负值即已过期
        "expiry_date": (today + timedelta(days=spec["expiry_days"])).isoformat(),
    }
    if spec.get("remain_qty") is not None:
        batch["remain_qty"] = spec["remain_qty"]
    return batch


def ensure_items(app_token: str, family_id: int, cats: dict[tuple[str, ...], int]) -> tuple[int, int]:
    """确保 20 条演示物品存在，返回 (新建数, 跳过数)。

    查重按「演示家庭内的物品名称」；命中即跳过，不覆盖手工在页面上改过的演示数据。
    """
    step("[6/6] 演示物品（10 条药品 + 10 条食品）")
    existing = {row.get("name") for row in page_all("/app/erp/item/list", token=app_token, family_id=family_id)}

    created = skipped = 0
    for spec in ITEMS:
        if spec["name"] in existing:
            skipped += 1
            continue
        payload = {
            "category_id": cats[spec["category"]],
            "name": spec["name"],
            "barcode": spec["barcode"],
            "brand": spec["brand"],
            "spec": spec["spec"],
            "unit": spec["unit"],
            "purchase_channel": spec["channel"],
            "ref_price": spec["ref_price"],
            "location": spec["location"],
            "attrs": spec["attrs"],
            "batches": [build_batch(batch) for batch in spec["batches"]],
        }
        api.call("POST", "/app/erp/item/create", token=app_token, family_id=family_id, json_body=payload)
        say(f"新建 {spec['category'][0]}｜{spec['name']}（{spec['brand']} {spec['spec']}，{len(spec['batches'])} 个批次）")
        created += 1
    say(f"物品就绪：新建 {created} 条，跳过 {skipped} 条（同名已存在）")
    return created, skipped


def stage_summary(app_token: str, family_id: int) -> None:
    """把「本次实际入库的样子」重新拉一遍，打印最终摘要。"""
    step("[自检] 拉取演示家庭数据")
    rows = page_all("/app/erp/item/list", token=app_token, family_id=family_id)
    today = date.today()
    expiring = [row for row in rows if row.get("nearest_expiry_date") and 0 <= (date.fromisoformat(row["nearest_expiry_date"]) - today).days <= 30]
    expired = [row for row in rows if row.get("nearest_expiry_date") and (date.fromisoformat(row["nearest_expiry_date"]) - today).days < 0]
    medicine = [row for row in rows if (row.get("category_name") or "") in CATEGORY_TREE["药品"]]
    food = [row for row in rows if (row.get("category_name") or "") in CATEGORY_TREE["食品"]]

    print("\n" + "═" * 62)
    print("  演示数据就绪")
    print("─" * 62)
    print(f"  演示账号：{DEMO_MOBILE}  密码：{DEMO_PASSWORD}（昵称「{DEMO_NICKNAME}」）")
    print(f"  家庭名称：{DEMO_FAMILY_NAME}（id={family_id}）")
    print(f"  物品总数：{len(rows)}（药品 {len(medicine)} / 食品 {len(food)}）")
    print(f"  效期样本：30 天内到期 {len(expiring)} 条，已过期 {len(expired)} 条")
    if expiring:
        print("    · 快到期：" + "、".join(row["name"] for row in expiring))
    if expired:
        print("    · 已过期：" + "、".join(row["name"] for row in expired))
    print("─" * 62)
    print("  H5 demo / Swagger 都可以用上面这个账号登录查看。")
    print("═" * 62)


# ══════════════════════════ 主流程 ══════════════════════════


def main() -> None:
    reset = "--reset" in sys.argv
    admin_token = stage_admin_login()
    cats, _, _ = ensure_categories(admin_token)
    ensure_attrs(admin_token, cats)
    app_token, user_id = ensure_demo_user()
    family_id = ensure_demo_family(app_token)
    if reset:
        reset_items(app_token, family_id)
    ensure_items(app_token, family_id, cats)
    stage_summary(app_token, family_id)
    say(f"演示账号 user_id={user_id}")


if __name__ == "__main__":
    main()
