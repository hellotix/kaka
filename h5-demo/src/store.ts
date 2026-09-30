/**
 * 会话状态 —— 登录令牌、当前用户、家庭列表与当前家庭。
 *
 * 为什么直接用 localStorage 持久化：
 * 演示应用不引入状态管理库，刷新页面后保持登录态即可；
 * 真正的会话有效性由后端 Redis 判定 —— access_token 过期时
 * 由 api.ts 用 refresh_token 静默换新，刷新也失败才踢回登录页。
 *
 * 关于「当前家庭」：
 * 一个人可同时属于多个家庭，所以 family_id 刻意不进 JWT，
 * 每次请求通过 X-Family-Id 头告诉后端「这次操作哪个家庭」；
 * 这里存的只是「本机选中的那个家庭」。
 */

import type { AppLoginOut, AppTokenOut, AppUserBrief, FamilyBrief } from './types'

const STORAGE_KEY = 'kaka-h5-demo/session'

/**
 * 内存中的会话快照（页面生命周期内直接读写，变更后同步落 localStorage）
 *
 * sessionId 是后端给本次登录发的会话 ID：
 * 个人中心要标出「这就是你现在这台设备」，靠它和 /login/sessions 的返回值对比。
 * access_token 里也编了它，但前端拿不到明文，所以登录时存下来。
 */
interface Session {
  accessToken: string
  refreshToken: string
  sessionId: string
  user: AppUserBrief | null
  families: FamilyBrief[]
  familyId: number | null
}

function emptySession(): Session {
  return { accessToken: '', refreshToken: '', sessionId: '', user: null, families: [], familyId: null }
}

function loadSession(): Session {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return emptySession()
    // 与空快照合并：旧版本数据缺字段也不会让页面崩掉
    return { ...emptySession(), ...(JSON.parse(raw) as Partial<Session>) }
  } catch {
    return emptySession()
  }
}

let session: Session = loadSession()

function persist(): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
  } catch {
    // 隐私模式 / 存储写满时写不进去：忽略即可，本次会话仍能正常用
  }
}

export const store = {
  get accessToken(): string {
    return session.accessToken
  },
  get refreshToken(): string {
    return session.refreshToken
  },
  get sessionId(): string {
    return session.sessionId
  },
  get user(): AppUserBrief | null {
    return session.user
  },
  get families(): FamilyBrief[] {
    return session.families
  },
  get familyId(): number | null {
    return session.familyId
  },
  get isLoggedIn(): boolean {
    return Boolean(session.accessToken)
  },

  /** 登录 / 注册成功后写入令牌、会话 ID 与用户信息 */
  setLogin(data: AppLoginOut): void {
    session.accessToken = data.access_token
    session.refreshToken = data.refresh_token
    session.sessionId = data.session_id
    session.user = data.user_info
    persist()
  },

  /**
   * 个人中心改完资料后同步本地快照。
   *
   * 只替换 user 不碰令牌：顶栏、列表页都在读 store.user，
   * 改完昵称不刷新的话还会顶着旧名字显示。
   */
  setUser(user: AppUserBrief): void {
    session.user = user
    persist()
  },

  /** 静默刷新成功后只更换令牌对 */
  setTokens(data: AppTokenOut): void {
    session.accessToken = data.access_token
    session.refreshToken = data.refresh_token
    persist()
  },

  /** 更新家庭列表；若当前选中家庭已不在列表里（被解散/被移出），自动回退到第一个 */
  setFamilies(list: FamilyBrief[]): void {
    session.families = list
    if (!list.some((item) => item.id === session.familyId)) {
      session.familyId = list[0]?.id ?? null
    }
    persist()
  },

  /** 切换当前家庭（App 顶部家庭切换器） */
  setFamilyId(id: number | null): void {
    session.familyId = id
    persist()
  },

  /** 退出登录 / 令牌彻底失效时清空 */
  clear(): void {
    session = emptySession()
    persist()
  },
}
