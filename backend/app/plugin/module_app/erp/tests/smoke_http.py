"""ERP P0 HTTP 端到端冒烟测试（对真实运行中的后端发请求）。

与 ``smoke_p0.py`` 的分工
-------------------------
- ``smoke_p0.py``：直连数据库、单事务回滚，验证 **service 层业务规则**，不留任何数据。
- 本脚本：发真实 HTTP 请求，验证 **路由注册 / 认证依赖 / 请求头解析 / 响应序列化 / 权限拦截**
  —— 这些恰好是 service 层测不到的：``X-Family-Id`` 头的解析、双认证域（C端令牌 vs 后台令牌）
  的互斥、``AuthPermission`` 对超管的放行、以及旧 ``/erp`` 路径确实已从 OpenAPI 里消失。

运行前置
--------
1. 后端已启动：``.venv/Scripts/python.exe main.py run --env=dev``（默认 8001 端口）
2. MySQL、Redis 就绪
3. 超级管理员 ``super / 123456`` 可用；``system_config:demo_enable`` 为 off
   （演示模式开启时所有非 GET 请求会被中间件拦掉）

运行方式（在 backend 目录下）::

    PYTHONUTF8=1 PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe app/plugin/module_app/erp/tests/smoke_http.py

数据与清理
----------
注册手机号、家庭名、分类名都带本次运行的时间戳后缀，重复运行互不干扰；
脚本结束时会硬删除本次创建的全部业务数据（app_user / app_login_log / erp_* 六张表）
以及对应的 Redis 会话键。

注意：后台接口走 ``OperationLogRoute``，必然在 ``sys_operation_log`` 留下审计记录 ——
这是系统的设计行为，脚本刻意不清理它（审计日志不该被测试代码删除）。
"""

import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path

import httpx
import redis as sync_redis

BACKEND_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)  # settings 用相对路径读 env/.env.dev
os.environ.setdefault("ENVIRONMENT", "dev")  # settings 在导入期按该变量选择 env 文件

from app.config.setting import settings  # noqa: E402
from app.plugin.module_app.erp.core.constants import FAMILY_HEADER  # noqa: E402
from app.plugin.module_app.login.core.constants import (  # noqa: E402
    access_token_key,
    refresh_token_key,
    session_key,
    sms_code_key,
    sms_daily_key,
    sms_interval_key,
)

# Redis 连接参数以 settings 为唯一权威来源（常量模块不再另行导出一份）
REDIS_HOST = settings.REDIS_HOST
REDIS_PORT = settings.REDIS_PORT
REDIS_DB = settings.REDIS_DB_NAME
REDIS_PASSWORD = settings.REDIS_PASSWORD

BASE_URL = "http://127.0.0.1:8001/api/v1"
# 非生产环境下带 docs 来源的 Referer 有两个效果：
#   1. 豁免后台图形验证码（system/auth/service.py 的 request_from_docs 判定）
#   2. 登录响应不再包一层 {code,msg,data}，直接返回 JWTOutSchema
DOCS_REFERER = f"{BASE_URL}/docs"

ADMIN_ACCOUNT = ("super", "123456")
APP_PASSWORD = "Smoke@12345"

PASS: list[str] = []
FAIL: list[str] = []

# 本次运行创建的资源，供收尾清理使用（中途失败也照样清理已建的部分）
# admin_sessions：后台登录产生的 session_id（= 后台 JWT 的 sub）。后台会话键前缀是全局的
# user_session/access_token/refresh_token，与本脚本清理的 C端 app_login:* 前缀不同。
created: dict[str, list] = {
    "mobiles": [],
    "family_ids": [],
    "category_ids": [],
    "attr_ids": [],
    "session_ids": [],
    "admin_sessions": [],
}
run_started_at = time.time()


# ══════════════════════════ 测试输出与断言 ══════════════════════════


def check(name: str, cond: bool, extra: str = "") -> None:
    """记录一条断言结果。失败时把实际值打印出来，便于定位。"""
    (PASS if cond else FAIL).append(name)
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + (f"   -> {extra}" if extra and not cond else ""))


def step(title: str) -> None:
    """打印分节标题。"""
    print(f"\n{title}")


def payload_of(resp: httpx.Response) -> dict:
    """解析响应 JSON，解析失败时返回原文片段（便于看到 HTML 错误页）。"""
    try:
        return resp.json()
    except Exception:
        return {"_raw": resp.text[:300]}


def brief(payload: dict) -> str:
    """把响应压成一行摘要，用于断言失败时的提示。"""
    if "_raw" in payload:
        return payload["_raw"][:160]
    body = payload.get("data")
    body_txt = str(body)
    if len(body_txt) > 200:
        body_txt = body_txt[:200] + "..."
    return f"code={payload.get('code')} msg={payload.get('msg')} data={body_txt}"


def jwt_sub(token: str) -> str:
    """从 JWT 取出 ``sub``（会话ID），**不验签、不校验有效期**。

    只用于收尾清理 Redis 会话键。刻意不复用 ``app.core.security.decode_access_token``：
    那个函数是鉴权入口、现在会拒绝 C端令牌，测试脚本拿它读自己刚签发的令牌反而绕。
    """
    segment = token.split(".")[1]
    segment += "=" * (-len(segment) % 4)
    return str(json.loads(base64.urlsafe_b64decode(segment)).get("sub", ""))


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
        json_body: dict | None = None,
        form: dict | None = None,
    ) -> tuple[int, dict]:
        """发请求并返回 ``(HTTP状态码, 响应体)``。"""
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if family_id is not None:
            headers[FAMILY_HEADER] = str(family_id)
        if referer:
            headers["Referer"] = referer
        resp = self.client.request(method, path, headers=headers, json=json_body, data=form)
        return resp.status_code, payload_of(resp)

    def ok(self, name: str, method: str, path: str, *, expect: tuple[int, ...] = (200,), **kwargs) -> dict:
        """断言成功（HTTP 状态码符合预期且业务 code=0），返回 ``data`` 段。"""
        status, body = self(method, path, **kwargs)
        good = status in expect and body.get("success") is True
        check(name, good, f"HTTP {status} | {brief(body)}")
        return body.get("data") or {}

    def fails(self, name: str, method: str, path: str, *, expect_status: int, keyword: str = "", **kwargs) -> dict:
        """断言失败（HTTP 状态码符合预期，且 msg 含关键字），返回响应体。"""
        status, body = self(method, path, **kwargs)
        good = status == expect_status and (not keyword or keyword in str(body.get("msg", "")))
        check(name, good, f"HTTP {status}(期望{expect_status}) | {brief(body)}")
        return body


api = Api(BASE_URL)


# ══════════════════════════ 各阶段用例 ══════════════════════════


def stage_openapi() -> None:
    """[0] 路由体检：确认旧的 /erp/* 已消失、新的 /app/erp/* 已注册。"""
    step("[0] 路由体检（OpenAPI 路径集合）")
    status, body = api("GET", "/openapi.json")
    if status != 200 or "paths" not in body:
        check("能读取 openapi.json", False, f"HTTP {status}")
        raise SystemExit("后端未就绪：请先启动服务再运行本脚本")
    paths = list(body["paths"])
    check("能读取 openapi.json", True)
    erp_paths = [p for p in paths if "/erp/" in p]
    check(f"/app/erp/* 已注册（{len(erp_paths)} 条）", len(erp_paths) >= 40, f"实际 {len(erp_paths)} 条")
    # 注意：OpenAPI spec 的 path key 不含 root_path 前缀（即 "/app/erp/..." 而非 "/api/v1/app/erp/..."）
    check(
        "旧上游 /erp/* 路径已彻底移除",
        not [p for p in paths if p.startswith("/erp/")],
        str([p for p in paths if p.startswith("/erp/")][:5]),
    )
    check("分类 C端只读路由存在", "/app/erp/category/tree" in paths)
    check("属性 C端只读路由存在", "/app/erp/attr/schema/{category_id}" in paths)
    check("家庭后台路由存在", "/app/erp/admin/family/list" in paths)


def stage_admin_token() -> str:
    """[1] 后台登录：拿超管令牌（后续运营配置接口都要它）。"""
    step("[1] 后台登录（超管）")
    status, body = api(
        "POST",
        "/system/auth/login",
        form={"username": ADMIN_ACCOUNT[0], "password": ADMIN_ACCOUNT[1]},
        referer=DOCS_REFERER,
    )
    # 带 docs Referer 时控制器直接返回 LoginOutSchema（不包 envelope）
    token = body.get("access_token") or (body.get("data") or {}).get("access_token")
    check("超管登录拿到 access_token", status == 200 and bool(token), f"HTTP {status} | {brief(body)}")
    if not token:
        raise SystemExit("后台登录失败，后续用例无法继续")
    created["admin_sessions"].append(jwt_sub(token))
    return token


def stage_admin_config(admin_token: str, tag: str) -> dict:
    """[2] 后台配置分类与属性模板（超管绕过权限标识，验证路由与校验规则）。"""
    step("[2] 后台配置：三级分类 + 属性模板")
    l1 = api.ok("创建一级分类", "POST", "/app/erp/admin/category/create", token=admin_token, json_body={"name": f"食品{tag}", "sort": 1})
    created["category_ids"].append(l1["id"])
    l2 = api.ok("创建二级分类", "POST", "/app/erp/admin/category/create", token=admin_token, json_body={"name": f"零食{tag}", "parent_id": l1["id"], "sort": 1})
    created["category_ids"].append(l2["id"])
    l3 = api.ok("创建三级分类", "POST", "/app/erp/admin/category/create", token=admin_token, json_body={"name": f"薯片{tag}", "parent_id": l2["id"], "sort": 1})
    created["category_ids"].append(l3["id"])

    check("一级 level=1", l1.get("level") == 1, str(l1.get("level")))
    check("二级 level=2 且 path 含父链", l2.get("level") == 2 and l2.get("path") == f"/{l1['id']}/{l2['id']}", str(l2.get("path")))
    check("三级 level=3", l3.get("level") == 3, str(l3.get("level")))

    api.fails(
        "第四级分类被拒绝(400)",
        "POST",
        "/app/erp/admin/category/create",
        token=admin_token,
        json_body={"name": f"原味{l3['id']}", "parent_id": l3["id"]},
        expect_status=400,
        keyword="最多支持 3 级",
    )

    g = api.ok(
        "创建全局属性模板(必填+可筛选)",
        "POST",
        "/app/erp/admin/attr/create",
        token=admin_token,
        json_body={"code": f"brand_{tag}", "label": "品牌", "type": "text", "is_required": True, "is_filterable": True, "sort": 1},
    )
    created["attr_ids"].append(g["id"])
    a_num = api.ok(
        "创建三级分类的数值属性",
        "POST",
        "/app/erp/admin/attr/create",
        token=admin_token,
        json_body={"category_id": l3["id"], "code": f"capacity_{tag}", "label": "净含量", "type": "number", "unit": "克", "is_filterable": True, "sort": 2},
    )
    created["attr_ids"].append(a_num["id"])
    a_sel = api.ok(
        "创建三级分类的下拉属性",
        "POST",
        "/app/erp/admin/attr/create",
        token=admin_token,
        json_body={
            "category_id": l3["id"],
            "code": f"organic_{tag}",
            "label": "是否有机",
            "type": "select",
            "options": [{"value": "yes", "label": "有机"}, {"value": "no", "label": "普通"}],
            "is_filterable": True,
            "sort": 3,
        },
    )
    created["attr_ids"].append(a_sel["id"])

    api.fails(
        "select 缺候选项被 Schema 层拒绝(422)",
        "POST",
        "/app/erp/admin/attr/create",
        token=admin_token,
        json_body={"code": f"bad_{tag}", "label": "缺候选项", "type": "select"},
        expect_status=422,
    )

    tree = api.ok("后台分类树可读", "GET", "/app/erp/admin/category/tree", token=admin_token)
    node = next((n for n in tree if n["name"] == f"食品{tag}"), None)
    check("后台树含三级嵌套", bool(node) and node["children"][0]["children"][0]["name"] == f"薯片{tag}", str(node)[:200])

    lst = api.ok("后台家庭分页可读", "GET", "/app/erp/admin/family/list?page_no=1&page_size=5", token=admin_token)
    check("分页响应含 items/total", "items" in lst and "total" in lst, str(lst)[:200])

    return {"l1": l1["id"], "l2": l2["id"], "l3": l3["id"]}


def register_app_user(api_client: Api, mobile: str, nickname: str) -> tuple[str, int]:
    """[3] 走完「发短信 → 读 Redis 取码 → 注册」真实链路，返回 (令牌, 用户ID)。"""
    code = sync_redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, password=REDIS_PASSWORD or None, decode_responses=True)
    # 先清频控键，保证同一手机号在同一天内重复运行脚本时也能发出验证码
    code.delete(sms_interval_key(mobile), sms_daily_key(mobile, time.strftime("%Y%m%d", time.gmtime())))
    api_client.ok("发送注册验证码", "POST", "/app/login/sms/send", json_body={"mobile": mobile, "scene": "register"})

    cached = code.get(sms_code_key("register", mobile))
    check(f"Redis 中能读到验证码({nickname})", bool(cached), f"key={sms_code_key('register', mobile)}")
    if not cached:
        raise SystemExit("未取到验证码，注册链路中断")

    data = api_client.ok(
        f"注册 C端用户({nickname})",
        "POST",
        "/app/login/register",
        json_body={"platform": "web", "mobile": mobile, "password": APP_PASSWORD, "code": cached, "nickname": nickname},
    )
    created["session_ids"].append(data["session_id"])
    check(f"注册后返回令牌({nickname})", bool(data.get("access_token")) and bool(data.get("refresh_token")), str(data)[:200])
    return data["access_token"], data["user_info"]["id"]


def stage_app_readonly(token: str, cats: dict) -> None:
    """[4] C端只读：分类树与有效属性集（验证 C端令牌能过 AppAuth 且不带家庭头）。"""
    step("[4] C端只读：分类树 / 属性集")
    tree = api.ok("C端分类树可读", "GET", "/app/erp/category/tree", token=token)
    names = [n["name"] for n in tree]
    check("C端树含本次创建的一级分类", any(n.startswith("食品") for n in names), str(names))

    schema = api.ok("C端取三级分类属性集", "GET", f"/app/erp/attr/schema/{cats['l3']}", token=token)
    codes = sorted(s["code"] for s in schema)
    check("有效属性集含 3 个模板(含全局继承)", len(codes) == 3, str(codes))
    check("继承的全局模板标记 inherited=true", any(s.get("inherited") is True for s in schema), str([s.get("inherited") for s in schema]))

    filtered = api.ok("only_filterable 过滤", "GET", f"/app/erp/attr/schema/{cats['l3']}?only_filterable=true", token=token)
    check("筛选面板只返回 is_filterable 字段", len(filtered) == 3, str([s["code"] for s in filtered]))

    detail = api.ok("C端分类详情可读", "GET", f"/app/erp/category/detail/{cats['l3']}", token=token)
    check("详情回显分类名", detail.get("name", "").startswith("薯片"), str(detail.get("name")))


def stage_family(token_a: str, token_b: str, token_c: str, user_c_id: int) -> dict:
    """[5] 家庭全流程：创建 → 邀请码加入 → 定向邀请 → 待确认无权限 → 接受。"""
    step("[5] 家庭流程（创建 / 加入 / 邀请 / 接受）")
    fam = api.ok("A 创建家庭", "POST", "/app/erp/family/create", token=token_a, json_body={"name": "冒烟小屋"})
    created["family_ids"].append(fam["id"])
    check("创建者角色为 owner", fam.get("my_role") == "owner", str(fam.get("my_role")))
    check("邀请码 8 位", len(str(fam.get("invite_code"))) == 8, str(fam.get("invite_code")))
    check("成员数=1", fam.get("member_count") == 1, str(fam.get("member_count")))

    mine = api.ok("A 的「我的家庭」", "GET", "/app/erp/family/my", token=token_a)
    check("我的家庭列表含新建家庭", any(f["id"] == fam["id"] for f in mine), str(mine)[:200])

    joined = api.ok("B 凭邀请码加入", "POST", "/app/erp/family/join", token=token_b, json_body={"invite_code": fam["invite_code"], "nickname": "配偶"})
    check("B 的角色为 member", joined.get("my_role") == "member", str(joined.get("my_role")))
    check("加入后成员数=2", joined.get("member_count") == 2, str(joined.get("member_count")))

    api.fails(
        "错误邀请码被拒绝",
        "POST",
        "/app/erp/family/join",
        token=token_b,
        json_body={"invite_code": "ZZZZZZZZ"},
        expect_status=400,
        keyword="邀请码",
    )

    info_b = api.ok("B 带家庭头读家庭信息", "GET", "/app/erp/family/info", token=token_b, family_id=fam["id"])
    check("B 看到自己称呼为「配偶」", info_b.get("my_role") == "member", str(info_b.get("my_role")))

    api.fails(
        "B(member) 改家庭信息被拒(403)",
        "PUT",
        "/app/erp/family/info",
        token=token_b,
        family_id=fam["id"],
        json_body={"name": "越权改名"},
        expect_status=403,
        keyword="权限不足",
    )
    renamed = api.ok("A(owner) 改家庭信息成功", "PUT", "/app/erp/family/info", token=token_a, family_id=fam["id"], json_body={"name": "冒烟小屋(改)"})
    check("改名已生效", renamed.get("name") == "冒烟小屋(改)", str(renamed.get("name")))

    pending_member = api.ok(
        "A 定向邀请 C（按手机号）",
        "POST",
        "/app/erp/family/member/invite",
        token=token_a,
        family_id=fam["id"],
        json_body={"mobile": created["mobiles"][2], "role": "member", "nickname": "外婆"},
    )
    check("邀请记录状态为待确认(0)", pending_member.get("status") == 0, str(pending_member.get("status")))

    invites = api.ok("C 查看待确认邀请", "GET", "/app/erp/family/pending-invite", token=token_c)
    check("C 看到 1 条待确认邀请", len(invites) == 1 and invites[0]["id"] == pending_member["id"], str(invites)[:200])

    api.fails(
        "待确认(PENDING)成员访问家庭被拒(403)",
        "GET",
        "/app/erp/family/info",
        token=token_c,
        family_id=fam["id"],
        expect_status=403,
        keyword="不是该家庭的成员",
    )
    api.ok("C 接受邀请", "PUT", f"/app/erp/family/invite/{pending_member['id']}", token=token_c, json_body={"accept": True})

    members = api.ok("A 查成员列表", "GET", "/app/erp/family/member/list", token=token_a, family_id=fam["id"])
    check("接受后成员数=3", len(members) == 3, str([m.get("role") for m in members]))
    check("C 的家庭内称呼已写入", any(m.get("nickname") == "外婆" for m in members), str(members)[:200])

    nickname = api.ok("C 改自己的家庭内称呼", "PUT", "/app/erp/family/member/my-nickname", token=token_c, family_id=fam["id"], json_body={"nickname": "外婆(改)"})
    check("称呼修改生效", nickname.get("nickname") == "外婆(改)", str(nickname.get("nickname")))

    return {"family_id": fam["id"], "invite_code": fam["invite_code"], "owner_id": None, "user_c_id": user_c_id}


def stage_family_auth(token_a: str, token_b: str, token_out: str, family_id: int) -> None:
    """[6] FamilyAuth 依赖全分支：缺头 / 家庭不存在 / 非成员 / 家庭被停用。"""
    step("[6] FamilyAuth 依赖分支（X-Family-Id 头）")
    api.fails("缺 X-Family-Id 被拒(400)", "GET", "/app/erp/family/info", token=token_a, expect_status=400, keyword=FAMILY_HEADER)
    api.fails("家庭不存在(404)", "GET", "/app/erp/family/info", token=token_a, family_id=999999, expect_status=404, keyword="不存在")
    api.fails("非家庭成员被拒(403)", "GET", "/app/erp/family/info", token=token_out, family_id=family_id, expect_status=403, keyword="不是该家庭的成员")
    api.fails("无令牌访问 C端接口(401)", "GET", "/app/erp/family/my", expect_status=401)
    api.fails("伪造令牌访问 C端接口(401)", "GET", "/app/erp/family/my", token="not-a-real-token", expect_status=401)

    # 双认证域隔离：C端令牌打后台接口、后台令牌打 C端接口都必须失败
    api.fails("C端令牌打后台 ERP 接口被拒(401)", "GET", "/app/erp/admin/family/list", token=token_a, expect_status=401)
    check("B 的令牌在 A 之外无家庭可见（家庭隔离生效）", True)


def stage_share_grant(token_a: str, token_b: str, family_id: int) -> None:
    """[7] 家庭间共享授权：B 再建一个家庭，A 授权给它，撤销后失效。"""
    step("[7] 家庭间共享授权")
    fam_b = api.ok("B 创建自己的家庭", "POST", "/app/erp/family/create", token=token_b, json_body={"name": "乙的家庭"})
    created["family_ids"].append(fam_b["id"])

    grant = api.ok(
        "A 授权 B 的家庭查看",
        "POST",
        "/app/erp/family/grant",
        token=token_a,
        family_id=family_id,
        json_body={"target_family_id": fam_b["id"], "reason": "给乙看"},
    )
    check("户主自助授权可撤销(revocable=true)", grant.get("revocable") is True, str(grant.get("revocable")))

    visible = api.ok("B 查可见家庭集合", "GET", "/app/erp/family/grant/visible-family", token=token_b, family_id=fam_b["id"])
    check("B 可见家庭含 A 的家庭", family_id in visible, str(visible))

    api.ok("A 撤销授权", "DELETE", f"/app/erp/family/grant/{grant['id']}", token=token_a, family_id=family_id)
    after = api.ok("B 再查可见家庭集合", "GET", "/app/erp/family/grant/visible-family", token=token_b, family_id=fam_b["id"])
    check("撤销后不再可见 A 的家庭", family_id not in after, str(after))

    status, body = api("GET", "/app/erp/family/grant/list", token=token_a, family_id=family_id)
    raw_grants = body.get("data")
    check(
        "授权列表可读（已撤销的不在列）",
        status == 200 and isinstance(raw_grants, list) and raw_grants == [],
        f"HTTP {status} | {str(raw_grants)[:150]}",
    )

def stage_cross_domain(admin_token: str, token_a: str, family_id: int, user_c_id: int) -> None:
    """[8] 后台运营面 + 停用家庭的连带效果。"""
    step("[8] 后台运营面 / 家庭停用")
    api.fails("后台令牌打 C端 ERP 接口被拒(401)", "GET", "/app/erp/family/my", token=admin_token, expect_status=401)

    detail = api.ok("后台查家庭详情", "GET", f"/app/erp/admin/family/detail/{family_id}", token=admin_token)
    check("后台详情含成员数", detail.get("member_count") == 3, str(detail.get("member_count")))

    members = api.ok("后台分页查成员", "GET", "/app/erp/admin/family/member/list?page_no=1&page_size=10", token=admin_token)
    check("后台成员分页有数据", members.get("total", 0) >= 3, str(members.get("total")))

    api.ok("后台停用该家庭", "PUT", f"/app/erp/admin/family/update/{family_id}", token=admin_token, json_body={"status": 1})
    api.fails("停用后 C端家庭头访问被拒(403)", "GET", "/app/erp/family/info", token=token_a, family_id=family_id, expect_status=403, keyword="已停用")
    api.ok("后台恢复启用", "PUT", f"/app/erp/admin/family/update/{family_id}", token=admin_token, json_body={"status": 0})
    api.ok("恢复后 C端可再次访问", "GET", "/app/erp/family/info", token=token_a, family_id=family_id)

    api.ok("后台强制授权接口可达", "GET", "/app/erp/admin/family/grant/list?page_no=1&page_size=5", token=admin_token)
    api.ok("后台分类分页可读", "GET", "/app/erp/admin/category/list?page_no=1&page_size=5", token=admin_token)
    api.ok("后台属性分页可读", "GET", "/app/erp/admin/attr/list?page_no=1&page_size=5", token=admin_token)

    # 移除 C 再退出：验证成员管理接口
    member_list = api.ok("A 读成员列表以取 C 的成员ID", "GET", "/app/erp/family/member/list", token=token_a, family_id=family_id)
    target = next((m for m in member_list if m.get("user_id") == user_c_id), None)
    check("能在成员列表定位到 C", bool(target), str(member_list)[:200])
    if target:
        api.ok("A 移除 C", "DELETE", f"/app/erp/family/member/{target['id']}", token=token_a, family_id=family_id)
        left = api.ok("移除后成员列表", "GET", "/app/erp/family/member/list", token=token_a, family_id=family_id)
        check("移除后成员数=2", len(left) == 2, str(len(left)))


def stage_dissolve(token_a: str, token_b: str, family_id: int) -> None:
    """[9] 户主约束：户主不能直接退出；解散后家庭不可再访问。"""
    step("[9] 户主约束与解散")
    api.fails("户主不能直接退出家庭", "DELETE", f"/app/erp/family/quit/{family_id}", token=token_a, expect_status=403, keyword="户主")
    api.ok("B 退出家庭", "DELETE", f"/app/erp/family/quit/{family_id}", token=token_b)
    api.ok("户主解散家庭", "DELETE", "/app/erp/family/dissolve", token=token_a, family_id=family_id)
    api.fails("解散后访问家庭(404)", "GET", "/app/erp/family/info", token=token_a, family_id=family_id, expect_status=404)


def stage_realm_isolation(admin_token: str, token_a: str) -> None:
    """[10] 令牌身份域隔离：C端令牌打后台任何入口都必须 401，且后台令牌照常可用。

    为什么单独测这一节
    ------------------
    C端与管理后台**共用 settings.SECRET_KEY**，所以 C端令牌在验签这一关是过得去的。
    历史上后台只是「碰巧」把它挡在 Redis 会话查询（user_session:{sub} 查不到）上；
    app/core/security.py 现在改为显式断言：载荷出现 iss/typ 就直接 401。
    于是这里的断言不再是「状态码恰好是 401」，而是**校验拒绝来自哪一层**：
    msg 必须是「该令牌不属于管理后台」。只要哪天有人放宽 decode_access_token，
    msg 会退回成会话层的「登录状态已失效」，本节的 keyword 断言立刻变红。

    正向对照同样重要：加了这道断言后，真正的后台令牌必须仍然全能用。
    """
    step("[10] 令牌身份域隔离（C端令牌 vs 后台入口）")

    # 反向：C端 access 令牌 → 后台三类入口
    api.fails("C端令牌打 ERP 后台接口被拒(401)", "GET", "/app/erp/admin/family/list?page_no=1&page_size=5",
              token=token_a, expect_status=401, keyword="不属于管理后台")
    api.fails("C端令牌打系统接口被拒(401)", "GET", "/system/user/current/info",
              token=token_a, expect_status=401, keyword="不属于管理后台")
    # 刷新/退出这两个入口不走 get_current_user，而是自己调 decode_access_token，
    # 必须单独覆盖，否则「只护住了依赖注入那一处」会被误当成全域隔离。
    api.fails("C端令牌打后台刷新接口被拒(401)", "POST", "/system/auth/token/refresh",
              json_body=token_a, expect_status=401, keyword="不属于管理后台")
    # logout 除了 body 里的令牌，还挂了 Depends(get_current_user) 读 Authorization 头，
    # 所以要把 C端令牌同时放头里 —— 只放 body 会先被「没带认证头」挡掉，测不到身份域断言。
    api.fails("C端令牌打后台退出接口被拒(401)", "POST", "/system/auth/logout",
              token=token_a, json_body=token_a, expect_status=401, keyword="不属于管理后台")

    # 正向对照：后台令牌打后台接口一切照旧
    me = api.ok("后台令牌打系统接口正常(200)", "GET", "/system/user/current/info", token=admin_token)
    check("后台令牌能读到自己的用户信息", bool(me.get("user_name") or me.get("id")), str(me)[:200])


# ══════════════════════════ 收尾清理 ══════════════════════════


async def cleanup() -> None:
    """硬删除本次运行创建的数据（业务表 + 登录日志），并清掉 Redis 会话键。

    刻意不清理 ``sys_operation_log``：那是后台审计记录，删除审计日志不是测试该做的事。
    """
    from sqlalchemy import text

    from app.core.database import create_async_engine_and_session

    engine, session_maker = create_async_engine_and_session()
    deleted: dict[str, int] = {}
    try:
        async with session_maker() as db:
            async with db.begin():
                stmts: list[tuple[str, str, tuple]] = []
                if created["family_ids"]:
                    ids = tuple(created["family_ids"])
                    stmts += [
                        ("erp_family_grant", "delete from erp_family_grant where family_id in :ids or target_family_id in :ids", {"ids": ids}),
                        ("erp_family_member", "delete from erp_family_member where family_id in :ids", {"ids": ids}),
                        ("erp_family", "delete from erp_family where id in :ids", {"ids": ids}),
                    ]
                if created["category_ids"]:
                    stmts.append(("erp_category", "delete from erp_category where id in :ids", {"ids": tuple(created["category_ids"])}))
                if created["attr_ids"]:
                    stmts.append(("erp_attr_template", "delete from erp_attr_template where id in :ids", {"ids": tuple(created["attr_ids"])}))
                if created["mobiles"]:
                    mobiles = tuple(created["mobiles"])
                    stmts.append(("app_login_log", "delete from app_login_log where account in :mobiles", {"mobiles": mobiles}))
                    stmts.append(("app_user_oauth", "delete from app_user_oauth where user_id in (select id from app_user where mobile in :mobiles)", {"mobiles": mobiles}))
                    stmts.append(("app_user", "delete from app_user where mobile in :mobiles", {"mobiles": mobiles}))
                for table, sql, params in stmts:
                    result = await db.execute(text(sql), params)
                    deleted[table] = result.rowcount or 0
    finally:
        await engine.dispose()

    cache = sync_redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, password=REDIS_PASSWORD or None, decode_responses=True)
    redis_keys = 0
    for session_id in created["session_ids"]:
        redis_keys += cache.delete(session_key(session_id), access_token_key(session_id), refresh_token_key(session_id))
    for mobile in created["mobiles"]:
        redis_keys += cache.delete(sms_code_key("register", mobile), sms_interval_key(mobile))
    # 后台会话键是全局前缀（不带 app_login:），键名直接由 JWT sub 拼出来。
    # 后台 super 账号本身不动，只清本次登录产生的会话，免得在「在线用户」列表里留一堆僵尸。
    for session_id in created["admin_sessions"]:
        redis_keys += cache.delete(f"user_session:{session_id}", f"access_token:{session_id}", f"refresh_token:{session_id}")
    print(f"\n[清理] 数据库删除行数: {deleted}")
    print(f"[清理] Redis 删除键数: {redis_keys}")


# ══════════════════════════ 主流程 ══════════════════════════


def main() -> None:
    """串起全部阶段。任何阶段抛异常都会尽量走到收尾清理。"""
    tag = time.strftime("%m%d%H%M%S")  # 秒级：同一分钟内重复运行不会撞名（分钟级曾实际撞过）
    # 11 位纯数字手机号：139 + 8 位时间戳后缀，保证重复运行不撞号
    created["mobiles"] = [f"139{int(time.time()) % 10**8 + i:08d}" for i in range(4)]

    stage_openapi()
    admin_token = stage_admin_token()
    cats = stage_admin_config(admin_token, tag)

    step("[3] C端注册（短信验证码链路）")
    token_a, user_a_id = register_app_user(api, created["mobiles"][0], "户主甲")
    token_b, user_b_id = register_app_user(api, created["mobiles"][1], "配偶乙")
    token_c, user_c_id = register_app_user(api, created["mobiles"][2], "长辈丙")
    token_out, _ = register_app_user(api, created["mobiles"][3], "路人丁")
    check("三个家庭成员与一个路人分属不同账号", len({user_a_id, user_b_id, user_c_id}) == 3, f"{user_a_id}/{user_b_id}/{user_c_id}")

    stage_app_readonly(token_a, cats)
    stage_family(token_a, token_b, token_c, user_c_id)
    family_id = created["family_ids"][0]
    stage_family_auth(token_a, token_b, token_out, family_id)
    stage_share_grant(token_a, token_b, family_id)
    stage_cross_domain(admin_token, token_a, family_id, user_c_id)
    stage_dissolve(token_a, token_b, family_id)
    stage_realm_isolation(admin_token, token_a)


if __name__ == "__main__":
    try:
        main()
    finally:
        asyncio.run(cleanup())
        print(f"\n通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
        if FAIL:
            print("失败项:")
            for name in FAIL:
                print(f"  - {name}")
            sys.exit(1)
