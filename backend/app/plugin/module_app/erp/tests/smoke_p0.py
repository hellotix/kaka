"""ERP P0 服务层冒烟测试（直连 MySQL，全程单事务，结束回滚，不留数据）。

运行方式（在 backend 目录下）::

    .venv/Scripts/python.exe app/plugin/module_app/erp/tests/smoke_p0.py

不需要 Redis、不需要起 HTTP 服务：直接构造 service 与 ``FamilyAuth`` 依赖的入参对象，
所以能在 Redis 未就绪时验证 P0 的全部业务规则。

覆盖：分类三级上限/树组装/隐藏连带、属性模板就近覆盖与校验、JSON 过滤条件渲染、
家庭创建-加入-角色-转让-授权、以及 FamilyAuth 依赖的越权拦截。

注意：回滚只能撤销数据，MySQL 的 AUTO_INCREMENT 计数器不会回退，
所以反复运行会看到 id 递增、表里始终 0 行 —— 这是正常的。

结束时可能打印一段 ``RuntimeError: Event loop is closed``（来自 aiomysql 连接对象的
``__del__``，Windows Proactor 事件循环下的已知噪音），只要「失败 0 项」就可以忽略。
"""

import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)  # settings 用相对路径读 env/.env.dev
os.environ["ENVIRONMENT"] = "dev"

from pydantic import ValidationError  # noqa: E402
from redis.asyncio import Redis  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.dialects import mysql  # noqa: E402

from app.core.database import create_async_engine_and_session  # noqa: E402
from app.core.exceptions import CustomException  # noqa: E402
from app.plugin.module_app.erp.attr.schema import ErpAttrCreateSchema  # noqa: E402
from app.plugin.module_app.erp.attr.service import ErpAttrService  # noqa: E402
from app.plugin.module_app.erp.category.schema import ErpCategoryCreateSchema, ErpCategoryUpdateSchema  # noqa: E402
from app.plugin.module_app.erp.category.service import ErpCategoryService  # noqa: E402
from app.plugin.module_app.erp.core.attrs import build_attr_conditions  # noqa: E402
from app.plugin.module_app.erp.core.constants import ErpFamilyRole, ErpMemberStatus  # noqa: E402
from app.plugin.module_app.erp.core.context import FamilyAuth, auth_schema  # noqa: E402
from app.plugin.module_app.erp.family.model import ErpFamilyModel  # noqa: E402
from app.plugin.module_app.erp.family.schema import (  # noqa: E402
    ErpFamilyAdminUpdateSchema,
    ErpFamilyCreateSchema,
    ErpFamilyUpdateSchema,
    ErpGrantAdminCreateSchema,
    ErpGrantCreateSchema,
    ErpMemberHandleSchema,
    ErpMemberInviteSchema,
    ErpMemberJoinSchema,
)
from app.plugin.module_app.erp.family.service import ErpFamilyAdminService, ErpFamilyPortalService, ErpFamilyService  # noqa: E402
from app.plugin.module_app.login.core.constants import AppPlatform  # noqa: E402
from app.plugin.module_app.login.core.dependencies import AppAuthContext  # noqa: E402
from app.plugin.module_app.login.user.model import AppUserModel  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'OK ' if cond else 'FAIL'} {name}" + (f"   -> {extra}" if extra and not cond else ""))


async def expect_raise(name, coro, keyword=None):
    try:
        await coro
    except CustomException as e:
        check(name, keyword is None or keyword in str(e.msg), f"实际报错: {e.msg}")
        return
    except Exception as e:
        check(name, False, f"抛了非业务异常 {type(e).__name__}: {e}")
        return
    check(name, False, "没有抛异常")


def login_as(user, db) -> AppAuthContext:
    """构造 C端登录上下文。redis 用未连接的实例占位（P0 的服务层不碰 Redis）。"""
    return AppAuthContext(
        user_id=user.id,
        session_id="smoke",
        platform=AppPlatform.WEB,
        user=user,
        db=db,
        redis=Redis(host="127.0.0.1", port=6379, db=1),
    )


async def main():
    engine, session_maker = create_async_engine_and_session()
    async with session_maker() as db:
        trans = await db.begin()
        try:
            await run(db)
        finally:
            await trans.rollback()

    # 回滚后复查：所有测试数据都不该留下
    async with session_maker() as db:
        leftover = {}
        for t in ("app_user", "erp_family", "erp_family_member", "erp_family_grant", "erp_category", "erp_attr_template"):
            leftover[t] = (await db.execute(text(f"select count(*) from {t}"))).scalar()
        await engine.dispose()
    print("\n[10] 回滚后残留（应全为 0）:", leftover)
    check("回滚后无残留数据", all(v == 0 for v in leftover.values()), str(leftover))

    print(f"\n通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败项:")
        for name in FAIL:
            print(f"  - {name}")
        sys.exit(1)


async def run(db):
    auth = auth_schema()

    users = []
    for uname, nick, mobile in [("smoke_owner", "户主甲", "13800000001"), ("smoke_spouse", "配偶乙", "13800000002"), ("smoke_parent", "长辈丙", "13800000003")]:
        u = AppUserModel(username=uname, nickname=nick, mobile=mobile, status=0, register_type="password")
        db.add(u)
        users.append(u)
    await db.flush()
    for u in users:
        await db.refresh(u)
    owner, spouse, parent = users
    print(f"[准备] app_user ids = {[u.id for u in users]}")

    # ══════════════ 1. 分类三级上限与树组装 ══════════════
    print("\n[1] 分类三级上限与树组装")
    cats = ErpCategoryService(auth, db)
    c1 = await cats.create(data=ErpCategoryCreateSchema(name="食品", sort=1))
    c2 = await cats.create(data=ErpCategoryCreateSchema(name="生鲜", parent_id=c1.id, sort=1))
    c3 = await cats.create(data=ErpCategoryCreateSchema(name="叶菜", parent_id=c2.id, sort=1))
    check("一级 level=1 path=/{id}", c1.level == 1 and c1.path == f"/{c1.id}", f"{c1.level} {c1.path}")
    check("二级 level=2 path 含父链", c2.level == 2 and c2.path == f"/{c1.id}/{c2.id}", f"{c2.level} {c2.path}")
    check("三级 level=3 path 含完整链", c3.level == 3 and c3.path == f"/{c1.id}/{c2.id}/{c3.id}", f"{c3.level} {c3.path}")
    await expect_raise("第四级被拒绝", cats.create(data=ErpCategoryCreateSchema(name="菠菜", parent_id=c3.id)), "最多支持 3 级")
    await expect_raise("同级重名被拒绝", cats.create(data=ErpCategoryCreateSchema(name="食品")), "已存在名为")

    h1 = await cats.create(data=ErpCategoryCreateSchema(name="药品", sort=2))
    await cats.create(data=ErpCategoryCreateSchema(name="处方药", parent_id=h1.id, sort=1))

    tree_admin = await cats.tree(client_view=False)
    names = [n.name for n in tree_admin]
    check("后台树含两棵一级分类", {"食品", "药品"} <= set(names), str(names))
    food = next(n for n in tree_admin if n.name == "食品")
    check("后台树三级正确嵌套", food.children[0].name == "生鲜" and food.children[0].children[0].name == "叶菜")

    await cats.update(id=h1.id, data=ErpCategoryUpdateSchema(is_visible=False))
    client_names = [n.name for n in await cats.tree(client_view=True)]
    check("C端树不含被隐藏的一级分类", "药品" not in client_names, str(client_names))
    check("C端树仍含未隐藏的食品", "食品" in client_names, str(client_names))

    chain = await cats.ancestor_ids(c3.id)
    check("ancestor_ids 解析物化路径", chain == [c1.id, c2.id, c3.id], str(chain))

    # ══════════════ 2. 属性模板就近覆盖 ══════════════
    print("\n[2] 属性模板继承与就近覆盖")
    attrs = ErpAttrService(auth, db)
    await attrs.create(data=ErpAttrCreateSchema(code="brand", label="品牌", type="text", is_required=True, is_filterable=True, sort=1))
    await attrs.create(data=ErpAttrCreateSchema(category_id=c1.id, code="capacity", label="容量", type="number", unit="克", is_filterable=True, sort=2))
    await attrs.create(data=ErpAttrCreateSchema(category_id=c3.id, code="capacity", label="净含量", type="number", unit="毫升", is_filterable=True, sort=2))
    await attrs.create(
        data=ErpAttrCreateSchema(
            category_id=c3.id,
            code="organic",
            label="是否有机",
            type="select",
            options=[{"value": "yes", "label": "有机"}, {"value": "no", "label": "普通"}],
            is_filterable=True,
            sort=3,
        )
    )
    await attrs.create(data=ErpAttrCreateSchema(category_id=c3.id, code="note", label="备注", type="textarea", sort=9))

    schema3 = await attrs.effective_schema(c3.id)
    codes = {s.code for s in schema3}
    check("三级有效属性集含全部 4 个 code", codes == {"brand", "capacity", "organic", "note"}, str(codes))
    cap = next(s for s in schema3 if s.code == "capacity")
    check("就近覆盖：capacity 取三级定义", cap.label == "净含量" and cap.unit == "毫升", f"{cap.label}/{cap.unit}")
    check("自身模板 inherited=False", cap.inherited is False, str(cap.inherited))
    brand = next(s for s in schema3 if s.code == "brand")
    check("全局模板 inherited=True 且名为「全局」", brand.inherited is True and brand.category_name == "全局", f"{brand.inherited}/{brand.category_name}")

    schema1 = await attrs.effective_schema(c1.id)
    cap1 = next(s for s in schema1 if s.code == "capacity")
    check("一级分类取自己的 capacity", cap1.unit == "克" and cap1.inherited is False, f"{cap1.unit}/{cap1.inherited}")
    check("一级分类拿不到三级的 organic", "organic" not in {s.code for s in schema1})

    only_filter = [s.code for s in await attrs.effective_schema(c3.id, only_filterable=True)]
    check("only_filterable 过滤掉不可筛选字段", only_filter == ["brand", "capacity", "organic"], str(only_filter))

    await expect_raise("同作用域 code 重复被拒绝", attrs.create(data=ErpAttrCreateSchema(code="brand", label="重复", type="text")), "已存在标识")
    # select 缺候选项在 Schema 层就被 model_validator 拦下（对外表现为 422），到不了 service
    try:
        ErpAttrCreateSchema(code="x1", label="x", type="select")
    except ValidationError as e:
        check("select 缺候选项在 Schema 层被拒绝", "候选项" in str(e))
    else:
        check("select 缺候选项在 Schema 层被拒绝", False, "没有抛 ValidationError")

    # ══════════════ 3. 属性值规范化 ══════════════
    print("\n[3] 属性值规范化")
    ok = await attrs.normalize(c3.id, {"brand": "  光明 ", "capacity": "500", "organic": "yes", "note": "冷藏", "hacked": "非法字段"})
    check("text 被 strip", ok["brand"] == "光明", str(ok))
    check("number 字符串转数值", isinstance(ok["capacity"], (int, float)) and ok["capacity"] == 500, str(ok.get("capacity")))
    check("模板外的键被丢弃", "hacked" not in ok, str(ok))
    ok2 = await attrs.normalize(c3.id, {"brand": "光明", "capacity": 1, "organic": "no"})
    check("可选字段未提交则不写键", "note" not in ok2, str(ok2))
    await expect_raise("必填缺失被拒绝", attrs.normalize(c3.id, {"capacity": 1, "organic": "no"}), "品牌")
    await expect_raise("候选项越界被拒绝", attrs.normalize(c3.id, {"brand": "a", "capacity": 1, "organic": "maybe"}), "是否有机")

    # ══════════════ 4. JSON 过滤条件渲染 ══════════════
    print("\n[4] JSON 过滤条件渲染（MySQL 方言）")
    conds = build_attr_conditions(
        ErpFamilyModel.extra,
        {
            "brand": "光明",
            "capacity": {"op": "between", "value": [10, 20]},
            "organic": {"op": "in", "value": ["yes", "no"]},
            "note": {"op": "like", "value": "冷"},
            "purchase_date": {"op": "not_null"},
            "evil": {"op": "drop table", "value": 1},
        },
    )
    check("非法 op 被跳过，得到 5 条条件", len(conds) == 5, f"实际 {len(conds)} 条")
    sqls = [str(c.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True})) for c in conds]
    joined = " | ".join(sqls)
    check("等值渲染成 JSON_UNQUOTE(JSON_EXTRACT)", "JSON_UNQUOTE(JSON_EXTRACT" in joined, joined[:300])
    check("between 走数值比较（MySQL 用 +0.0... 触发隐式转换）", "BETWEEN 10.0 AND 20.0" in joined and "+0.0000000000000000000000" in joined, joined[:400])
    check("like 渲染成参数化 LIKE", "LIKE" in joined and "冷" in joined, joined[:300])
    check("not_null 渲染成 IS NOT NULL", "IS NOT NULL" in joined, joined[:300])
    for s in sqls:
        print(f"    {s}")

    # ══════════════ 5. 家庭创建 / 加入 / 角色 ══════════════
    print("\n[5] 家庭创建 / 加入 / 角色")
    portal_owner = ErpFamilyPortalService(login_as(owner, db))
    fam = await portal_owner.create(data=ErpFamilyCreateSchema(name="甲的家"))
    check("创建家庭返回 id", bool(fam.id))
    check("邀请码 8 位且去掉易混字符", len(fam.invite_code) == 8 and not (set(fam.invite_code) & set("0O1I")), fam.invite_code)
    check("创建者 my_role=owner", fam.my_role == ErpFamilyRole.OWNER.value, str(fam.my_role))
    check("创建者 member_count=1", fam.member_count == 1, str(fam.member_count))

    my = await portal_owner.my_families()
    check("我的家庭列表返回该家庭", len(my) == 1 and my[0].id == fam.id, str(my))

    joined = await ErpFamilyPortalService(login_as(spouse, db)).join(data=ErpMemberJoinSchema(invite_code=fam.invite_code))
    check("配偶凭邀请码加入，角色 member", joined.my_role == ErpFamilyRole.MEMBER.value, str(joined.my_role))
    check("加入后成员数=2", joined.member_count == 2, str(joined.member_count))
    await expect_raise("错误邀请码被拒绝", ErpFamilyPortalService(login_as(spouse, db)).join(data=ErpMemberJoinSchema(invite_code="ZZZZZZZZ")), "邀请码")

    ctx_owner = await FamilyAuth(min_role=ErpFamilyRole.ADMIN)(login_as(owner, db), fam.id)
    svc_owner = ErpFamilyService(ctx_owner)
    invite = await svc_owner.invite(data=ErpMemberInviteSchema(user_id=parent.id, role="member", nickname="外婆"))
    check("定向邀请生成待确认记录", invite.status == ErpMemberStatus.PENDING.value, str(invite.status))
    pending = await ErpFamilyPortalService(login_as(parent, db)).pending_invites()
    check("长辈看到 1 条待确认邀请", len(pending) == 1 and pending[0].id == invite.id, str(pending))
    await ErpFamilyPortalService(login_as(parent, db)).handle_invite(member_id=invite.id, data=ErpMemberHandleSchema(accept=True))
    members = await svc_owner.member_list()
    check("接受后有效成员数=3", len(members) == 3, str(len(members)))
    check("家庭内称呼已写入", any(m.nickname == "外婆" for m in members))

    svc_spouse = ErpFamilyService(await FamilyAuth()(login_as(spouse, db), fam.id))
    await expect_raise("member 邀请他人被拒绝", svc_spouse.invite(data=ErpMemberInviteSchema(user_id=999999, role="member")), "权限不足")
    await expect_raise("member 改家庭信息被拒绝", svc_spouse.update(data=ErpFamilyUpdateSchema(name="改名")), "权限不足")
    renamed = await svc_owner.update(data=ErpFamilyUpdateSchema(name="甲的家(改)"))
    check("admin 及以上可改家庭名", renamed.name == "甲的家(改)", str(renamed.name))

    await svc_owner.transfer_owner(user_id=spouse.id)
    ctx_old_owner = await FamilyAuth()(login_as(owner, db), fam.id)
    check("原户主降级为 admin", ctx_old_owner.role is ErpFamilyRole.ADMIN, str(ctx_old_owner.role))
    ctx_new_owner = await FamilyAuth(min_role=ErpFamilyRole.OWNER)(login_as(spouse, db), fam.id)
    check("接任者成为 owner 且 is_owner=True", ctx_new_owner.role is ErpFamilyRole.OWNER and ctx_new_owner.is_owner)
    await expect_raise("非户主不能再次转让", ErpFamilyService(ctx_old_owner).transfer_owner(user_id=owner.id), "权限不足")

    # ══════════════ 6. 家庭间共享授权 ══════════════
    print("\n[6] 家庭间共享授权")
    fam2 = await ErpFamilyPortalService(login_as(parent, db)).create(data=ErpFamilyCreateSchema(name="丙的家"))
    svc_new_owner = ErpFamilyService(ctx_new_owner)
    grant = await svc_new_owner.create_grant(data=ErpGrantCreateSchema(target_family_id=fam2.id, reason="给外婆看"))
    check("户主自助授权创建成功且可撤销", bool(grant.id) and grant.revocable is True, f"{grant.id}/{grant.revocable}")
    ctx_parent_fam2 = await FamilyAuth()(login_as(parent, db), fam2.id)
    visible = await ErpFamilyService(ctx_parent_fam2).visible_family_ids()
    check("受权方可见家庭含授权方", fam.id in visible and fam2.id in visible, str(visible))

    admin_svc = ErpFamilyAdminService(auth, db, None)
    forced = await admin_svc.force_grant(data=ErpGrantAdminCreateSchema(family_id=fam2.id, target_family_id=fam.id, expire_time=datetime.now(UTC) + timedelta(days=7), reason="运营强制"))
    check("后台强制授权 source=admin", forced.source == "admin", str(forced.source))
    # forced 是 fam2 → fam 的授权，只有授权方(fam2 户主=长辈丙)才有资格尝试撤销
    svc_fam2_owner = ErpFamilyService(ctx_parent_fam2)
    await expect_raise("授权方户主不能撤销后台强制授权", svc_fam2_owner.revoke_grant(grant_id=forced.id), "后台")
    await expect_raise("受权方户主撤销他人授权被拒", svc_new_owner.revoke_grant(grant_id=forced.id), "不存在")
    await admin_svc.revoke_grant(id=forced.id)
    check("后台可撤销强制授权", True)

    await svc_new_owner.revoke_grant(grant_id=grant.id)
    visible2 = await ErpFamilyService(ctx_parent_fam2).visible_family_ids()
    check("撤销后受权方不再看到授权方", fam.id not in visible2, str(visible2))

    # ══════════════ 7. FamilyAuth 依赖拦截 ══════════════
    print("\n[7] FamilyAuth 依赖拦截")
    dep = FamilyAuth()
    await expect_raise("缺 X-Family-Id 被拒绝(400)", dep(login_as(owner, db), None), "X-Family-Id")
    await expect_raise("家庭不存在返回 404", dep(login_as(owner, db), 999999), "不存在")

    outsider = AppUserModel(username="smoke_out", nickname="路人", mobile="13800000009", status=0)
    db.add(outsider)
    await db.flush()
    await db.refresh(outsider)
    await expect_raise("非家庭成员被拒绝(403)", dep(login_as(outsider, db), fam.id), "不是该家庭的成员")

    await admin_svc.update(id=fam2.id, data=ErpFamilyAdminUpdateSchema(status=1))
    await expect_raise("家庭被停用后拒绝访问", dep(login_as(parent, db), fam2.id), "已停用")

    # ══════════════ 8. 退出与删除保护 ══════════════
    print("\n[8] 退出与删除保护")
    await expect_raise("户主不能直接退出家庭", ErpFamilyPortalService(login_as(spouse, db)).quit(family_id=fam.id), "户主")
    await ErpFamilyPortalService(login_as(parent, db)).quit(family_id=fam.id)
    left = await svc_new_owner.member_list()
    check("长辈退出后有效成员数=2", len(left) == 2, str(len(left)))

    await expect_raise("有子分类时删除被拒绝", cats.delete(ids=[c1.id]), "子分类")
    await expect_raise("挂着属性模板时删除被拒绝", cats.delete(ids=[c3.id]), "扩展属性模板")

    print("\n[9] 回滚前各表写入量（应均 > 0）")
    for t in ("app_user", "erp_family", "erp_family_member", "erp_family_grant", "erp_category", "erp_attr_template"):
        n = (await db.execute(text(f"select count(*) from {t}"))).scalar()
        print(f"    {t} = {n}")
        if not n:
            check(f"{t} 有写入", False, f"count={n}")


asyncio.run(main())
