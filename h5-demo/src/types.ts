/**
 * 后端 Schema 的 TypeScript 镜像 —— 前端所有数据的唯一类型出处。
 *
 * 对照的后端文件（backend/app/plugin/module_app/...）：
 * - login/auth/schema.py   → AppTokenOut / AppLoginOut / AppSmsSendOut
 * - login/user/schema.py   → AppUserBrief / AppUserProfile / ProfilePayload
 * - login/core/session.py  → SessionInfo
 * - erp/family/schema.py   → FamilyBrief / FamilyDetail
 * - erp/category/schema.py → CategoryNode
 * - erp/attr/schema.py     → AttrTemplate
 * - erp/item/schema.py     → Item / ItemBatch / ScanResult
 *
 * 约定：后端 Pydantic 的可空字段（`str | None`）序列化后是 `null`，
 * 因此这里统一写成 `| null`；消费端展示前用 `??` / `||` 兜底。
 */

// ══════════════════ 通用信封与分页 ══════════════════

/** 后端统一响应包装（backend/app/common/response.py 的 ResponseSchema） */
export interface ApiEnvelope<T> {
  code: number
  msg: string
  data: T
  status_code: number
  success: boolean
}

/** 分页结果（app/core/base_schema.py 的 PageResultSchema） */
export interface PageResult<T> {
  page_no: number
  page_size: number
  total: number
  has_next: boolean
  items: T[]
}

// ══════════════════ C端用户与认证 ══════════════════

/**
 * C端用户简要信息（login/user/schema.py: AppUserBriefSchema）。
 *
 * 注意 gender 是字符串而不是数字：后端 AppUserModel.gender 存的是
 * 定长字符 '0'/'1'/'2'（Pydantic 用 pattern=^[012]$ 校验），
 * 之前这里标成 number 是靠 JSON 不做类型校验蒙过去的，展示时必须按字符串查表。
 */
export interface AppUserBrief {
  id: number
  username: string | null
  nickname: string | null
  mobile: string | null
  avatar: string | null
  gender: string | null
  status: number | null
}

/** 令牌对（login/auth/schema.py: AppTokenOutSchema） */
export interface AppTokenOut {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  refresh_expires_in: number
}

/** 登录/注册响应（AppLoginOutSchema = 令牌对 + 会话与用户信息） */
export interface AppLoginOut extends AppTokenOut {
  session_id: string
  is_new_user: boolean
  user_info: AppUserBrief
}

/** 短信发送结果（AppSmsSendOutSchema，mobile 已脱敏） */
export interface SmsSendOut {
  mobile: string
  expire_seconds: number
  resend_after: number
}

/** 短信场景（后端 AppSmsScene 枚举值） */
export type SmsScene = 'login' | 'register' | 'reset_password' | 'bind_mobile'

/** 登录方式开关（login/auth/schema.py: AppLoginTypeOutSchema，供登录页渲染） */
export interface LoginConfig {
  password: boolean
  sms: boolean
  wechat: boolean
  apple: boolean
  platforms: string[]
  login_types: string[]
  sms_scenes: string[]
  providers: string[]
}

/** 登录终端（后端 AppPlatform 枚举值，H5 固定 web） */
export type AppPlatform = 'web' | 'ios' | 'android' | 'mini_program'

// ══════════════════ 个人中心（/login/profile/*、/login/sessions） ══════════════════

/**
 * 当前用户完整资料（login/user/schema.py: AppUserOutSchema + BaseSchema 审计字段）。
 *
 * 后端 BaseSchema 还会带 uuid / is_deleted / deleted_time，
 * 演示页面不展示也不判断，这里就不逐一镜像了。
 */
export interface AppUserProfile {
  id: number | null
  created_time: string | null
  updated_time: string | null
  username: string | null
  mobile: string | null
  email: string | null
  nickname: string | null
  avatar: string | null
  /** '0' 男 / '1' 女 / '2' 未知（字符串，见 AppUserBrief 的说明） */
  gender: string | null
  /** 0 正常 / 1 禁用 */
  status: number | null
  register_type: string | null
  register_platform: string | null
  register_ip: string | null
  last_login_time: string | null
  last_login_platform: string | null
  last_login_ip: string | null
  remark: string | null
}

/** 自助改资料提交体（AppUserProfileUpdateSchema，全部可选，没传=不改） */
export interface ProfilePayload {
  nickname?: string
  avatar?: string | null
  gender?: string
  email?: string | null
}

/** 在线会话（login/core/session.py: AppSessionInfo，存在 Redis 里） */
export interface SessionInfo {
  session_id: string
  user_id: number
  username: string | null
  nickname: string | null
  mobile: string | null
  avatar: string | null
  platform: string
  login_type: string
  login_ip: string | null
  login_location: string | null
  device_os: string | null
  device_browser: string | null
  login_time: string | null
}

/** 性别取值是字符串枚举，展示统一走这张表 */
export const GENDER_TEXT: Record<string, string> = { '0': '男', '1': '女', '2': '未知' }

/** 登录终端中文（后端 AppPlatform 枚举） */
export const PLATFORM_TEXT: Record<string, string> = {
  ios: 'iOS',
  android: 'Android',
  windows: 'Windows',
  mac: 'macOS',
  miniapp: '小程序',
  web: '网页端',
}

/** 登录方式中文（后端 AppLoginType 枚举） */
export const LOGIN_TYPE_TEXT: Record<string, string> = {
  password: '密码',
  sms: '短信',
  wechat: '微信',
  apple: 'Apple',
}

/** 注册来源中文（后端 AppRegisterType 枚举） */
export const REGISTER_TYPE_TEXT: Record<string, string> = {
  password: '密码注册',
  sms: '手机号注册',
  wechat: '微信注册',
  apple: 'Apple 注册',
  admin: '后台创建',
}

// ══════════════════ 家庭 ══════════════════

/** 家庭简要信息（erp/family/schema.py: ErpFamilyBriefSchema） */
export interface FamilyBrief {
  id: number | null
  name: string | null
  avatar: string | null
  my_role: string | null
  my_nickname: string | null
  member_count: number | null
  status: number | null
}

/** 家庭详情（ErpFamilyOutSchema，= 简要信息 + 户主/邀请码/上限等） */
export interface FamilyDetail extends FamilyBrief {
  owner_id: number | null
  invite_code: string | null
  member_limit: number | null
  remark: string | null
  owner_name: string | null
}

/** 家庭角色（erp/core/constants.py: ErpFamilyRole） */
export type FamilyRole = 'owner' | 'admin' | 'member' | 'viewer'

// ══════════════════ 分类与扩展属性 ══════════════════

/** 分类树节点（erp/category/schema.py: ErpCategoryTreeSchema，children 自引用） */
export interface CategoryNode {
  id: number | null
  name: string | null
  parent_id: number | null
  level: number | null
  sort: number | null
  icon: string | null
  is_visible: boolean | null
  status: number | null
  children: CategoryNode[]
}

/** 扩展属性值类型（erp/core/constants.py: ErpAttrType） */
export type AttrValueType = 'text' | 'textarea' | 'number' | 'date' | 'bool' | 'select' | 'multi_select'

/**
 * 扩展属性模板（erp/attr/schema.py: ErpAttrOutSchema）。
 *
 * options 兼容两种后台配法（见 erp/core/attrs.py 的 _option_values）：
 *   ["红", "蓝"]  或  [{ value: "red", label: "红" }, ...]
 * 前端用下面的 optionValue / optionLabel 统一取值。
 */
export interface AttrTemplate {
  category_id: number | null
  code: string | null
  label: string | null
  type: string | null
  options: unknown[] | null
  unit: string | null
  default_value: string | null
  is_required: boolean | null
  is_filterable: boolean | null
  sort: number | null
  status: number | null
  remark: string | null
  category_name: string | null
  /** true 表示该字段继承自祖先分类或全局模板 */
  inherited: boolean
}

// ══════════════════ 物品与批次 ══════════════════

/** 物品可见范围（erp/core/constants.py: ErpItemVisibility） */
export type ItemVisibility = 'family' | 'member' | 'private'

/** 批次状态（erp/core/constants.py: ErpBatchStatus） */
export const BATCH_STATUS_TEXT: Record<number, string> = {
  1: '在用',
  2: '已耗尽',
  3: '已过期',
  4: '已丢弃',
}

/** 物品批次（erp/item/schema.py: ErpItemBatchOutSchema） */
export interface ItemBatch {
  id: number | null
  item_id: number | null
  family_id: number | null
  quantity: number | null
  remain_qty: number | null
  unit_price: number | null
  /** "YYYY-MM-DD HH:mm:ss" */
  purchase_time: string | null
  channel: string | null
  /** "YYYY-MM-DD" */
  production_date: string | null
  expiry_date: string | null
  status: number | null
  remark: string | null
}

/** 物品档案（erp/item/schema.py: ErpItemOutSchema，后 5 个字段由 service 组装） */
export interface Item {
  id: number | null
  created_time?: string | null
  updated_time?: string | null
  family_id: number | null
  category_id: number | null
  name: string | null
  barcode: string | null
  brand: string | null
  spec: string | null
  unit: string | null
  images: string[]
  purchase_channel: string | null
  ref_price: number | null
  owner_user_id: number | null
  location: string | null
  visibility: ItemVisibility | null
  attrs: Record<string, unknown> | null
  remark: string | null
  // ── service 组装字段 ──
  category_name: string | null
  owner_name: string | null
  batch_count: number
  total_remain_qty: number
  nearest_expiry_date: string | null
  /** 批次明细：仅详情接口（/erp/item/detail/{id}）返回，列表为 [] */
  batches: ItemBatch[]
}

/** 扫码结果（erp/item/schema.py: ErpItemScanResultSchema） */
export interface ScanResult {
  matched: boolean
  barcode: string
  item: Item | null
  last_batch: ItemBatch | null
}

/** 上传结果（app/core/base_schema.py: UploadResponseSchema） */
export interface UploadResult {
  file_name: string | null
  origin_name: string | null
  file_url: string | null
}

// ══════════════════ 请求体 ══════════════════

/** 新增/编辑物品的提交体（erp/item/schema.py: Create/Update 的并集，字段都可选） */
export interface ItemPayload {
  category_id?: number | null
  name?: string
  barcode?: string | null
  brand?: string | null
  spec?: string | null
  unit?: string | null
  images?: string[]
  purchase_channel?: string | null
  ref_price?: number | null
  location?: string | null
  visibility?: ItemVisibility
  attrs?: Record<string, unknown> | null
  remark?: string | null
  /** 仅新增时使用：随档案一起创建的初始批次 */
  batches?: BatchPayload[]
}

/** 批次提交体（ErpItemBatchCreateSchema / ErpItemBatchUpdateSchema） */
export interface BatchPayload {
  item_id?: number
  quantity?: number
  remain_qty?: number | null
  unit_price?: number | null
  purchase_time?: string | null
  channel?: string | null
  production_date?: string | null
  expiry_date?: string | null
  status?: number
  remark?: string | null
}

// ══════════════════ 工具函数 ══════════════════

/** 取属性候选项的 value（兼容字符串与 {value,label} 两种配法） */
export function optionValue(option: unknown): string {
  if (option && typeof option === 'object' && 'value' in option) {
    return String((option as { value: unknown }).value)
  }
  return String(option)
}

/** 取属性候选项的展示文案（无 label 时回退到 value） */
export function optionLabel(option: unknown): string {
  if (option && typeof option === 'object') {
    const obj = option as { value?: unknown; label?: unknown }
    if (obj.label !== undefined && obj.label !== null) return String(obj.label)
    if (obj.value !== undefined) return String(obj.value)
  }
  return String(option)
}
