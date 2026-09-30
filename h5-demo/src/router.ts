/**
 * 视图路由 —— 解开「views 互相跳转」与「main 装配 views」之间的循环依赖。
 *
 * 依赖方向刻意定成单向：
 *     main.ts ──import──▶ views/*.ts
 *     views/*.ts ──import──▶ router.ts（只依赖这里暴露的 nav 函数）
 *
 * views 之间要跳转时只调用 nav.xxx()，具体渲染函数由 main.ts 在启动时注入，
 * 谁都不需要 import 谁。
 *
 * 之所以不做 hash / history 路由：
 * 演示只有 5 个视图（登录 / 列表 / 表单 / 详情 / 个人中心），浏览器前进后退不是验收项，
 * 状态直接放在各视图闭包里比维护一个路由表更简单。
 */

export interface RouterImpl {
  /** 登录页（含注册、短信登录 Tab） */
  login(): void
  /** 物品列表（首页） */
  list(): void
  /** 录入/编辑表单；itemId 有值 = 编辑已有物品 */
  form(itemId?: number, prefill?: FormPrefill): void
  /** 物品详情（含批次管理） */
  detail(id: number): void
  /** 个人中心（账号资料、改密码、在线设备） */
  profile(): void
}

/** 新建物品时的预填值（目前只有扫码带过来的条码） */
export interface FormPrefill {
  barcode?: string
}

let impl: RouterImpl | null = null

/** 由 main.ts 在启动时调用一次 */
export function bindRouter(router: RouterImpl): void {
  impl = router
}

function current(): RouterImpl {
  if (!impl) throw new Error('路由尚未初始化：请确认 main.ts 已调用 bindRouter')
  return impl
}

export const nav = {
  login: (): void => current().login(),
  list: (): void => current().list(),
  form: (itemId?: number, prefill?: FormPrefill): void => current().form(itemId, prefill),
  detail: (id: number): void => current().detail(id),
  profile: (): void => current().profile(),
}
