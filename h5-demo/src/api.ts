/**
 * HTTP 客户端 —— 全应用唯一发请求的地方。
 *
 * 这一层替视图挡掉三件事，视图里只写 `await api.itemList()`：
 *
 * 1. 响应信封拆包：后端所有接口都包一层 { code, msg, data, success }
 *    （见 backend/app/common/response.py），这里负责把 data 掏出来，
 *    失败时把中文 msg 变成 ApiError 抛出 —— 视图统一 catch 后 toast。
 * 2. 令牌管理：请求自动带 Authorization: Bearer；
 *    遇到 401 且本地还有 refresh_token 时，静默换新令牌并把原请求重放一次，
 *    只有刷新也失败才真正登出（调用 onUnauthorized 回调回登录页）。
 * 3. 家庭上下文：需要家庭数据的接口统一带 X-Family-Id 头
 *    （后端 FamilyAuth 依赖读它，见 erp/core/context.py）。
 *
 * 路径前缀说明：后端 ROOT_PATH=/api/v1，C端插件目录是 module_app，
 * 因此完整路径形如 /api/v1/app/erp/item/list，这里 BASE 之后写 /app/... 即可。
 */

import { store } from './store'
import type {
  ApiEnvelope,
  AppLoginOut,
  AppTokenOut,
  AppUserProfile,
  AttrTemplate,
  BatchPayload,
  CategoryNode,
  FamilyBrief,
  FamilyDetail,
  Item,
  ItemBatch,
  ItemPayload,
  LoginConfig,
  PageResult,
  ProfilePayload,
  ScanResult,
  SessionInfo,
  SmsScene,
  SmsSendOut,
  UploadResult,
} from './types'

const BASE = '/api/v1'

/** 业务异常：视图 catch 到它时 message 已经是可以直接展示给用户的中文 */
export class ApiError extends Error {
  constructor(
    message: string,
    /** HTTP 状态码；0 表示请求没发出去（断网/后端没启动） */
    readonly status: number = 0,
    /** 后端业务状态码（信封里的 code），排查日志时用 */
    readonly code: number = -1,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/** 查询参数：null / undefined / 空串会被自动跳过，不用调用方拼字符串 */
export type QueryValues = Record<string, string | number | boolean | null | undefined>

interface RequestOptions {
  query?: QueryValues
  /** JSON 请求体 */
  body?: unknown
  /** 文件上传用的表单体（与 body 二选一） */
  form?: FormData
  /** 默认 true：自动带 Authorization；登录前接口传 false */
  auth?: boolean
  /** 默认 false：需要家庭上下文的接口传 true，自动带 X-Family-Id */
  family?: boolean
  /** 内部使用：刷新令牌后重放原请求的标记，防止 401 无限循环 */
  retried?: boolean
}

function buildQuery(query?: QueryValues): string {
  if (!query) return ''
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === null || value === undefined || value === '') continue
    params.append(key, String(value))
  }
  const text = params.toString()
  return text ? `?${text}` : ''
}

/** 后端返回体不一定是 JSON（比如网关的 HTML 错误页），解析失败返回 null 而不是抛异常 */
async function parsePayload(response: Response): Promise<unknown> {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

/** 从错误响应里提取可展示的文案：优先信封的 msg，其次 FastAPI 422 的 detail 数组 */
function extractMessage(payload: unknown, status: number): string {
  if (payload && typeof payload === 'object') {
    const body = payload as { msg?: unknown; detail?: unknown }
    if (typeof body.msg === 'string' && body.msg) return body.msg
    if (typeof body.detail === 'string' && body.detail) return body.detail
    // 422 校验失败：detail 是 [{ loc: ["body", "mobile"], msg: "..." }, ...]
    if (Array.isArray(body.detail) && body.detail.length > 0) {
      const first = body.detail[0] as { loc?: unknown; msg?: unknown }
      const field = Array.isArray(first.loc) ? first.loc.filter((part) => part !== 'body').join('.') : ''
      if (typeof first.msg === 'string') return field ? `${field}：${first.msg}` : first.msg
    }
  }
  if (status === 0) return '网络异常，请确认后端服务已启动'
  return `请求失败（HTTP ${status}）`
}

function readCode(payload: unknown): number {
  if (payload && typeof payload === 'object') {
    const code = (payload as { code?: unknown }).code
    if (typeof code === 'number') return code
  }
  return -1
}

/** 令牌彻底失效时的回调（由 main.ts 注入：清空会话后回登录页） */
let onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler
}

/**
 * 刷新令牌（共享同一个进行中的 Promise）。
 *
 * 为什么要共享：首页会并发发好几个请求，令牌过期时它们会同时收到 401。
 * 若每个都去刷新，后端会创建多个会话，先返回的令牌反而可能被后一次刷新作废
 * （表现为「刚刷新完又是 401」）。共享后同一时刻只发一次刷新请求。
 */
let refreshing: Promise<boolean> | null = null

function doRefresh(): Promise<boolean> {
  return (async () => {
    try {
      const data = await request<AppTokenOut>('POST', '/app/login/refresh', {
        body: { refresh_token: store.refreshToken },
        auth: false,
        retried: true,
      })
      store.setTokens(data)
      return true
    } catch {
      return false
    }
  })()
}

async function refreshAccessToken(): Promise<boolean> {
  const pending = refreshing ?? (refreshing = doRefresh())
  const ok = await pending
  if (refreshing === pending) refreshing = null
  return ok
}

async function request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
  const { query, body, form, auth = true, family = false, retried = false } = options

  const headers: Record<string, string> = {}
  if (auth && store.accessToken) headers.Authorization = `Bearer ${store.accessToken}`
  if (family) {
    if (!store.familyId) throw new ApiError('请先选择要操作的家庭', 400, 400)
    headers['X-Family-Id'] = String(store.familyId)
  }

  let payload: BodyInit | undefined
  if (form) {
    // FormData 不手动设 Content-Type：浏览器要自己补 multipart 的 boundary
    payload = form
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }

  let response: Response
  try {
    response = await fetch(`${BASE}${path}${buildQuery(query)}`, { method, headers, body: payload })
  } catch {
    // fetch 只在网络层失败时 reject（后端没启动、断网），业务错误都是正常 resolve
    throw new ApiError('网络异常，请确认后端服务已启动', 0, 0)
  }

  // 401 且有 refresh_token：静默换新令牌后原样重放一次
  if (response.status === 401 && auth && !retried && store.refreshToken) {
    if (await refreshAccessToken()) {
      return request<T>(method, path, { ...options, retried: true })
    }
    store.clear()
    onUnauthorized?.()
    throw new ApiError('登录已过期，请重新登录', 401, 401)
  }

  const data = await parsePayload(response)
  if (!response.ok) throw new ApiError(extractMessage(data, response.status), response.status, readCode(data))
  if (!data || typeof data !== 'object') throw new ApiError('响应格式异常，请检查后端日志', response.status)

  const envelope = data as ApiEnvelope<T>
  if (envelope.success === false) throw new ApiError(extractMessage(data, response.status), response.status, envelope.code)
  return envelope.data
}

/** 接口清单 —— 路径与后端 controller 一一对应，改后端路由时记得同步这里 */
export const api = {
  // ── 认证（登录前可访问，auth: false 不带令牌） ──

  /** 登录方式开关，用于登录页决定显示哪些 Tab */
  loginConfig: (): Promise<LoginConfig> => request('GET', '/app/login/config', { auth: false }),

  /** 注册（后端强制校验短信验证码，code 必填） */
  register: (data: { mobile: string; password: string; code: string; nickname?: string }): Promise<AppLoginOut> =>
    request('POST', '/app/login/register', { body: { ...data, platform: 'web' }, auth: false }),

  /** 密码登录，account 可填手机号或用户名 */
  loginByPassword: (account: string, password: string): Promise<AppLoginOut> =>
    request('POST', '/app/login/password', { body: { account, password, platform: 'web' }, auth: false }),

  /** 短信验证码登录 */
  loginBySms: (mobile: string, code: string): Promise<AppLoginOut> =>
    request('POST', '/app/login/sms', { body: { mobile, code, platform: 'web' }, auth: false }),

  /** 发送短信验证码；dev 环境不发真短信，验证码打在后端控制台日志里 */
  sendSms: (mobile: string, scene: SmsScene): Promise<SmsSendOut> =>
    request('POST', '/app/login/sms/send', { body: { mobile, scene }, auth: false }),

  /** 退出登录：后端作废当前会话（同时作废 refresh_token） */
  logout: (): Promise<void> =>
    request('POST', '/app/login/logout', { body: { refresh_token: store.refreshToken || null } }),

  // ── 个人中心（/login/profile/* 与 /login/sessions，只认登录态，不带家庭头） ──

  /** 当前用户完整资料：注册来源、最近登录时间/终端/IP 都在这里 */
  profileInfo: (): Promise<AppUserProfile> => request('GET', '/app/login/profile/info'),

  /** 自助改资料（昵称/性别/邮箱/头像），只传改过的字段 */
  profileUpdate: (data: ProfilePayload): Promise<AppUserProfile> =>
    request('PUT', '/app/login/profile/update', { body: data }),

  /**
   * 改密码。
   *
   * old_password 只有「账号还没设过密码」（例如纯短信注册的用户）才留空，
   * 后端两种情况都会明确报错，前端不做推断。
   * 成功后后端下线除当前会话以外的所有会话，当前设备保持登录。
   */
  changePassword: (oldPassword: string, newPassword: string): Promise<void> =>
    request('PUT', '/app/login/profile/password', {
      body: oldPassword ? { old_password: oldPassword, new_password: newPassword } : { new_password: newPassword },
    }),

  /** 当前账号的在线会话（多端登录记录，来自 Redis） */
  mySessions: (): Promise<SessionInfo[]> => request('GET', '/app/login/sessions'),

  /** 下线除当前会话以外的所有会话 */
  kickOtherSessions: (): Promise<number> => request('DELETE', '/app/login/sessions/others'),

  // ── 家庭（/my 不需要家庭头；其余读接口需要 X-Family-Id） ──

  myFamilies: (): Promise<FamilyBrief[]> => request('GET', '/app/erp/family/my'),

  createFamily: (name: string): Promise<FamilyDetail> => request('POST', '/app/erp/family/create', { body: { name } }),

  joinFamily: (inviteCode: string): Promise<FamilyBrief> =>
    request('POST', '/app/erp/family/join', { body: { invite_code: inviteCode } }),

  familyInfo: (): Promise<FamilyDetail> => request('GET', '/app/erp/family/info', { family: true }),

  // ── 分类与扩展属性（只读） ──

  categoryTree: (): Promise<CategoryNode[]> => request('GET', '/app/erp/category/tree'),

  /** 某分类的有效属性集（含继承）；onlyFilterable=true 只返回可筛选的 */
  attrSchema: (categoryId: number, onlyFilterable = false): Promise<AttrTemplate[]> =>
    request('GET', `/app/erp/attr/schema/${categoryId}`, {
      query: { only_filterable: onlyFilterable ? true : undefined },
    }),

  // ── 物品档案 ──

  itemList: (params: QueryValues = {}): Promise<PageResult<Item>> =>
    request('GET', '/app/erp/item/list', { query: params, family: true }),

  itemDetail: (id: number): Promise<Item> => request('GET', `/app/erp/item/detail/${id}`, { family: true }),

  itemCreate: (data: ItemPayload): Promise<Item> => request('POST', '/app/erp/item/create', { body: data, family: true }),

  itemUpdate: (id: number, data: ItemPayload): Promise<Item> =>
    request('PUT', `/app/erp/item/update/${id}`, { body: data, family: true }),

  /** 批量删除（软删除），后端 body 直接收 ID 数组 */
  itemDelete: (ids: number[]): Promise<void> => request('DELETE', '/app/erp/item/delete', { body: ids, family: true }),

  /** 扫码查重：命中返回已有物品与最近批次，未命中用于新建时预填条码 */
  itemScan: (barcode: string): Promise<ScanResult> =>
    request('POST', '/app/erp/item/scan', { body: { barcode }, family: true }),

  /** 上传物品图片：只要求登录，不带家庭头（此时物品档案可能还不存在） */
  uploadImage: (file: File): Promise<UploadResult> => {
    const form = new FormData()
    form.append('file', file)
    return request('POST', '/app/erp/item/upload', { form })
  },

  // ── 批次 ──

  batchCreate: (data: BatchPayload): Promise<ItemBatch> =>
    request('POST', '/app/erp/item/batch/create', { body: data, family: true }),

  batchUpdate: (id: number, data: BatchPayload): Promise<ItemBatch> =>
    request('PUT', `/app/erp/item/batch/update/${id}`, { body: data, family: true }),

  batchDelete: (id: number): Promise<void> => request('DELETE', `/app/erp/item/batch/delete/${id}`, { family: true }),
}
