/**
 * 个人中心 —— 账号资料、我的家庭、安全设置、在线设备。
 *
 * 数据来自三处接口，彼此独立：
 * - api.profileInfo()：账号完整资料（注册来源、最近登录终端与 IP 都在这里）。
 *   这一条拉不到就是本页拉不到，直接错误页 + 重试。
 * - refreshFamilies()：家庭列表（顺带把当前家庭回退到有效值）。失败只让家庭卡片降级，
 *   本地缓存还能显示。
 * - api.mySessions()：Redis 里的在线会话。失败只让设备卡片显示重试，
 *   因为它和资料无关，不该拖累整页。
 *
 * 为什么改完资料要 store.setUser()：
 * 顶栏和列表页读的是 store.user（登录响应里那份精简快照）。后端已经把新的
 * 昵称/头像同步进了 Redis 会话，但本地这份 localStorage 缓存不会自己变，
 * 不同步就会「改完昵称，回列表页还顶着旧名字」。
 *
 * 分工：安全设置卡片放动作（改密码、下线其他设备），在线设备卡片只做展示，
 * 同一个操作出现在两个地方会让人怀疑它们做的是不是同一件事。
 *
 * 两处刻意的取舍：
 * - 不做「忘记密码」入口：找回密码属于登录流程，该放在登录页而不是登录之后。
 * - 不做第三方绑定卡片：dev 环境微信/Apple 渠道都是关的，接口返回永远是空列表，
 *   摆一张永远为空的卡片只会让人以为功能坏了。
 */

import { ApiError, api } from '../api'
import { nav } from '../router'
import { doLogout, refreshFamilies } from '../session'
import { store } from '../store'
import type { AppUserBrief, AppUserProfile, ProfilePayload, SessionInfo } from '../types'
import { GENDER_TEXT, LOGIN_TYPE_TEXT, PLATFORM_TEXT, REGISTER_TYPE_TEXT } from '../types'
import type { Child, ModalField } from '../ui'
import { confirmBox, fmtDateTime, h, loadingNode, mount, openFormModal, toast } from '../ui'

const FAMILY_ROLE_TEXT: Record<string, string> = {
  owner: '户主',
  admin: '管理员',
  member: '成员',
  viewer: '只读',
}

/** 性别下拉：值必须和后端一致（字符串 '0'/'1'/'2'，不是数字） */
const GENDER_OPTIONS = [
  { value: '0', label: '男' },
  { value: '1', label: '女' },
  { value: '2', label: '未知' },
]

export function renderProfile(): void {
  let profile: AppUserProfile | null = null
  let sessions: SessionInfo[] = []
  /** 在线会话是否拉成功：失败要显示「读取失败 + 重试」，而不是谎报「没有活跃会话」 */
  let sessionsLoaded = false

  // 头像上传用隐藏 input：点「换头像」只负责触发它，真正处理在 change 回调里
  const avatarInput = h('input', {
    type: 'file',
    accept: 'image/*',
    style: { display: 'none' },
    onchange: () => void uploadAvatar(),
  })

  void load()

  // ══════════════════ 加载与渲染 ══════════════════

  async function load(): Promise<void> {
    mount(h('div', { class: 'page' }, navbar(), content(loadingNode())))
    try {
      profile = await api.profileInfo()
    } catch (error) {
      const message = error instanceof ApiError ? error.message : '账号信息加载失败'
      mount(h('div', { class: 'page' }, navbar(), content(errorBox(message))))
      return
    }
    // 家庭与在线会话都允许失败：各自卡片降级，不影响整页
    await refreshFamilies().catch(() => [])
    await loadSessions()
    render()
  }

  async function loadSessions(): Promise<void> {
    try {
      sessions = await api.mySessions()
      sessionsLoaded = true
    } catch {
      sessions = []
      sessionsLoaded = false
    }
  }

  function render(): void {
    const data = profile
    if (!data) return
    mount(
      h(
        'div',
        { class: 'page' },
        navbar(),
        content(
          avatarInput,
          headCard(data),
          accountCard(data),
          familyCard(),
          securityCard(),
          deviceCard(),
          h('button', {
            class: 'btn btn-danger btn-block',
            style: { marginTop: '6px' },
            text: '退出登录',
            onclick: () => void logoutFlow(),
          }),
        ),
      ),
    )
  }

  function navbar(): HTMLElement {
    return h(
      'div',
      { class: 'navbar' },
      h('button', { class: 'btn btn-ghost', text: '返回', onclick: () => nav.list() }),
      h('div', { class: 'navbar-title' }, '个人中心'),
    )
  }

  function content(...children: Child[]): HTMLElement {
    return h('div', { class: 'content no-fab' }, ...children)
  }

  function errorBox(message: string): HTMLElement {
    return h(
      'div',
      { class: 'empty' },
      h('div', { class: 'icon', text: '!' }),
      h('div', { text: message }),
      h('button', { class: 'btn', style: { marginTop: '12px' }, text: '重试', onclick: () => void load() }),
    )
  }

  // ══════════════════ 头像与昵称 ══════════════════

  function headCard(data: AppUserProfile): HTMLElement {
    return h(
      'div',
      { class: 'card profile-head' },
      h(
        'div',
        { class: 'profile-avatar', onclick: () => avatarInput.click() },
        data.avatar ? h('img', { src: data.avatar, alt: '头像' }) : h('span', { text: '我' }),
      ),
      h(
        'div',
        { class: 'profile-main' },
        h('div', { class: 'profile-name', text: data.nickname ?? data.username ?? '未设置昵称' }),
        h('div', { class: 'profile-sub', text: maskMobile(data.mobile) }),
      ),
      h(
        'div',
        { class: 'profile-actions' },
        h('button', { class: 'btn btn-sm', text: '编辑资料', onclick: () => editProfileFlow() }),
        h('button', { class: 'btn btn-sm', text: '换头像', onclick: () => avatarInput.click() }),
      ),
    )
  }

  /** 手机号只露前 3 后 4：手机可能正被举在别人面前 */
  function maskMobile(mobile: string | null): string {
    if (!mobile) return '未绑定手机号'
    if (mobile.length < 7) return mobile
    return `${mobile.slice(0, 3)}****${mobile.slice(-4)}`
  }

  async function uploadAvatar(): Promise<void> {
    const file = avatarInput.files?.[0]
    // 立刻清空，否则连续选同一个文件不会再触发 change
    avatarInput.value = ''
    if (!file) return
    try {
      const uploaded = await api.uploadImage(file)
      if (!uploaded.file_url) throw new ApiError('上传失败：响应里没有文件地址')
      syncProfile(await api.profileUpdate({ avatar: uploaded.file_url }))
      toast('头像已更新', 'success')
    } catch (error) {
      toast(error instanceof ApiError ? error.message : '头像更新失败', 'error')
    }
  }

  function editProfileFlow(): void {
    const data = profile
    if (!data) return
    const fields: ModalField[] = [
      { key: 'nickname', label: '昵称', value: data.nickname ?? '', placeholder: '家人看到的名字' },
      { key: 'gender', label: '性别', type: 'select', value: data.gender ?? '2', options: GENDER_OPTIONS },
      { key: 'email', label: '邮箱', value: data.email ?? '', placeholder: '选填' },
    ]
    openFormModal('编辑资料', fields, async (values) => {
      const payload: ProfilePayload = {}
      // 只把「真的改了」的字段发出去：后端按 exclude_unset 只更新出现的键，
      // 全量提交会把没填的邮箱当成空值覆盖。（清空邮箱请走后台管理，这里不提供）
      if (values.nickname && values.nickname !== (data.nickname ?? '')) payload.nickname = values.nickname
      if (values.email && values.email !== (data.email ?? '')) payload.email = values.email
      if (values.gender !== (data.gender ?? '2')) payload.gender = values.gender
      if (Object.keys(payload).length === 0) throw new ApiError('没有需要保存的修改')
      syncProfile(await api.profileUpdate(payload))
      toast('资料已更新', 'success')
    })
  }

  /** 资料变更后：换本地缓存 + 重绘（后端已同步 Redis 会话里的昵称与头像） */
  function syncProfile(data: AppUserProfile): void {
    profile = data
    const brief: AppUserBrief = {
      id: data.id ?? 0,
      username: data.username,
      nickname: data.nickname,
      mobile: data.mobile,
      avatar: data.avatar,
      gender: data.gender,
      status: data.status ?? 0,
    }
    store.setUser(brief)
    render()
  }

  // ══════════════════ 账号信息 ══════════════════

  function accountCard(data: AppUserProfile): HTMLElement {
    const zh = (table: Record<string, string>, value: string | null): string | null =>
      value ? (table[value] ?? value) : null
    return h(
      'div',
      { class: 'card' },
      h('div', { class: 'card-title', text: '账号信息' }),
      kv('用户 ID', data.id),
      kv('用户名', data.username),
      kv('手机号', data.mobile),
      kv('性别', zh(GENDER_TEXT, data.gender)),
      kv('邮箱', data.email),
      kv('状态', data.status === null ? null : data.status === 0 ? '正常' : '已禁用'),
      kv('注册来源', zh(REGISTER_TYPE_TEXT, data.register_type)),
      kv('注册终端', zh(PLATFORM_TEXT, data.register_platform)),
      kv('注册时间', fmtDateTime(data.created_time)),
      kv('最近登录', fmtDateTime(data.last_login_time)),
      kv('登录终端', zh(PLATFORM_TEXT, data.last_login_platform)),
      kv('登录 IP', data.last_login_ip),
    )
  }

  /** kv 行：空值统一显示成 —，不留出一行空白让人以为页面坏了 */
  function kv(key: string, value: string | number | null | undefined): HTMLElement {
    const text = value === null || value === undefined || value === '' ? '—' : String(value)
    return h('div', { class: 'kv' }, h('div', { class: 'kv-k', text: key }), h('div', { class: 'kv-v', text }))
  }

  // ══════════════════ 我的家庭 ══════════════════

  function familyCard(): HTMLElement {
    const families = store.families
    const rows: Child[] = []
    if (families.length === 0) {
      rows.push(h('div', { class: 'field-hint', text: '还没有加入任何家庭，回首页可以创建或用邀请码加入' }))
    } else {
      for (const family of families) {
        const role = family.my_role ? (FAMILY_ROLE_TEXT[family.my_role] ?? family.my_role) : '成员'
        rows.push(
          h(
            'div',
            { class: 'menu-item', onclick: () => switchFamily(family.id) },
            family.name ?? '未命名家庭',
            h('span', { class: 'tag', text: `${role} · ${family.member_count ?? 1} 人` }),
            family.id === store.familyId ? h('span', { class: 'check', text: '✓' }) : null,
          ),
        )
      }
    }
    return h('div', { class: 'card' }, h('div', { class: 'card-title', text: '我的家庭' }), ...rows)
  }

  function switchFamily(id: number | null): void {
    if (id === null || id === store.familyId) return
    store.setFamilyId(id)
    // 切完直接回列表：家庭是列表页的上下文，留在个人中心看一串看不到的物品没意义
    toast('已切换家庭', 'success')
    nav.list()
  }

  // ══════════════════ 安全设置 ══════════════════

  function securityCard(): HTMLElement {
    return h(
      'div',
      { class: 'card' },
      h('div', { class: 'card-title', text: '安全设置' }),
      h('div', { class: 'menu-item', onclick: () => changePasswordFlow() }, '修改密码'),
      h('div', { class: 'menu-item', onclick: () => void kickOthers() }, '退出其他设备登录'),
    )
  }

  function changePasswordFlow(): void {
    openFormModal(
      '修改密码',
      [
        { key: 'old_password', label: '原密码', type: 'password', placeholder: '该账号未设置过密码时留空' },
        { key: 'new_password', label: '新密码', type: 'password', required: true },
        { key: 'confirm_password', label: '确认新密码', type: 'password', required: true },
      ],
      async (values) => {
        // 长度与复杂度规则由后端配置（PASSWORD_MIN_LENGTH / 强度开关），
        // 前端不复制一份，否则两边口径迟早分叉；报错直接用后端返回的中文
        if (values.new_password !== values.confirm_password) throw new ApiError('两次输入的新密码不一致')
        await api.changePassword(values.old_password, values.new_password)
        // 后端会作废除当前会话外的所有会话，设备列表要重拉才不会显示已经失效的那几台
        await loadSessions()
        render()
        toast('密码已修改，其他设备已下线', 'success')
      },
    )
  }

  async function kickOthers(): Promise<void> {
    const ok = await confirmBox('将退出除当前设备以外的所有登录，确定吗？', {
      title: '退出其他设备',
      okText: '确定',
      danger: true,
    })
    if (!ok) return
    try {
      const count = await api.kickOtherSessions()
      await loadSessions()
      render()
      toast(count > 0 ? `已下线 ${count} 个其他设备会话` : '当前没有其他设备在线', 'success')
    } catch (error) {
      toast(error instanceof ApiError ? error.message : '操作失败', 'error')
    }
  }

  // ══════════════════ 在线设备 ══════════════════

  function deviceCard(): HTMLElement {
    const rows: Child[] = [h('div', { class: 'card-title', text: '在线设备' })]
    if (!sessionsLoaded) {
      rows.push(
        h('div', { class: 'field-hint', text: '在线设备读取失败' }),
        h('button', {
          class: 'btn btn-sm',
          style: { marginTop: '8px' },
          text: '重试',
          onclick: () => void loadSessions().then(render),
        }),
      )
    } else if (sessions.length === 0) {
      rows.push(h('div', { class: 'field-hint', text: '当前没有活跃会话' }))
    } else {
      for (const session of sessions) rows.push(sessionRow(session))
    }
    return h('div', { class: 'card' }, ...rows)
  }

  function sessionRow(session: SessionInfo): HTMLElement {
    // store.sessionId 来自登录响应：JWT 里也编了它，但前端读不到明文，只能登录时存下来对比
    const current = session.session_id === store.sessionId
    const device = [PLATFORM_TEXT[session.platform] ?? session.platform, session.device_os, session.device_browser]
      .filter((part): part is string => Boolean(part))
      .join(' · ')
    return h(
      'div',
      { class: 'kv' },
      h(
        'div',
        { class: 'kv-v' },
        h('div', {
          text: `${device} · ${LOGIN_TYPE_TEXT[session.login_type] ?? session.login_type}登录`,
        }),
        h('div', {
          style: { fontSize: '12px', color: 'var(--text-3)' },
          text: `${fmtDateTime(session.login_time)}${session.login_ip ? ` · ${session.login_ip}` : ''}`,
        }),
      ),
      current ? h('span', { class: 'tag tag-green', text: '本机' }) : null,
    )
  }

  // ══════════════════ 退出登录 ══════════════════

  async function logoutFlow(): Promise<void> {
    const ok = await confirmBox('退出后需要重新登录，确定退出吗？', { okText: '退出登录', danger: true })
    if (!ok) return
    await doLogout()
    toast('已退出登录')
    nav.login()
  }
}
