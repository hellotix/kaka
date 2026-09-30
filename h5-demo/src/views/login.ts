/**
 * 登录页 —— 密码登录 / 注册 / 短信登录 三个 Tab。
 *
 * 与后端约定的两处细节：
 * - 注册必须带短信验证码（后端 AppLoginService.register 强制校验），
 *   因此「注册」Tab 的验证码是必填项，不是可选项。
 * - dev 环境短信渠道是 LoggingSmsSender（backend/.../login/auth/sms.py），
 *   验证码只打在后端控制台日志里，不发真短信 —— 页面上做了提示。
 */

import { ApiError, api } from '../api'
import { nav } from '../router'
import { refreshFamilies } from '../session'
import { store } from '../store'
import type { AppLoginOut, SmsScene } from '../types'
import { h, mount, toast } from '../ui'

type Tab = 'password' | 'register' | 'sms'

/** 演示数据（seed_demo.py 造的账号），预填省得每次手输 */
const DEMO_ACCOUNT = '13900000001'
const DEMO_PASSWORD = 'Demo@12345'

export function renderLogin(): void {
  let tab: Tab = 'password'
  let tabs: Tab[] = ['password', 'register', 'sms']
  let countdownTimer: number | null = null

  /** 后端配置里被关掉的登录方式不显示（拿不到配置时保持默认三个 Tab） */
  void api
    .loginConfig()
    .then((config) => {
      if (!config.password && !config.sms) return
      const next: Tab[] = []
      if (config.password) next.push('password')
      if (config.sms) next.push('register', 'sms')
      tabs = next
      if (!tabs.includes(tab)) tab = tabs[0]
      render()
    })
    .catch(() => {
      // 登录配置接口挂了不该挡住登录，保持默认 Tab
    })

  render()

  function stopCountdown(): void {
    if (countdownTimer !== null) {
      window.clearInterval(countdownTimer)
      countdownTimer = null
    }
  }

  function render(): void {
    // 每次重渲染都会丢弃旧按钮，倒计时必须一起停掉，否则会一直写已卸载的节点
    stopCountdown()
    mount(
      h(
        'div',
        { class: 'auth-page' },
        h(
          'div',
          { class: 'auth-hero' },
          h('div', { class: 'auth-logo', text: '家' }),
          h('h1', { class: 'auth-title', text: '咔咔家庭物资' }),
          h('div', { class: 'auth-sub', text: '药品食品登记 · 效期提醒 · 全家共享' }),
        ),
        h(
          'div',
          { class: 'auth-tabs' },
          tabs.map((value) =>
            h('div', {
              class: `auth-tab${tab === value ? ' active' : ''}`,
              text: TAB_LABEL[value],
              onclick: () => {
                tab = value
                render()
              },
            }),
          ),
        ),
        tab === 'password' ? passwordForm() : tab === 'register' ? registerForm() : smsForm(),
        h(
          'div',
          { class: 'auth-hint' },
          h('div', { text: `演示账号：${DEMO_ACCOUNT} / ${DEMO_PASSWORD}（自带「演示家庭」20 条物资）` }),
          h('div', { text: '短信验证码不发真短信，开发环境请查看后端控制台日志' }),
        ),
      ),
    )
  }

  // ── 密码登录 ──

  function passwordForm(): HTMLElement {
    const account = h('input', { type: 'text', value: DEMO_ACCOUNT, placeholder: '手机号或用户名' })
    const password = h('input', { type: 'password', value: DEMO_PASSWORD, placeholder: '密码' })
    const submit = h('button', { class: 'btn btn-primary btn-block', type: 'submit', text: '登 录' })

    return h(
      'form',
      {
        onsubmit: (event: Event) => {
          event.preventDefault()
          void run(submit, async () => {
            const data = await api.loginByPassword(account.value.trim(), password.value)
            await afterLogin(data, false)
          })
        },
      },
      field('账号', account),
      field('密码', password),
      submit,
    )
  }

  // ── 注册 ──

  function registerForm(): HTMLElement {
    const mobile = h('input', { type: 'tel', value: DEMO_ACCOUNT, placeholder: '11 位手机号' })
    const code = h('input', { type: 'text', placeholder: '短信验证码' })
    const sendBtn = h('button', {
      class: 'btn',
      type: 'button',
      text: '获取验证码',
      onclick: () => void sendCode(mobile, sendBtn, 'register'),
    })
    const password = h('input', { type: 'password', value: DEMO_PASSWORD, placeholder: '设置密码' })
    const nickname = h('input', { type: 'text', placeholder: '昵称（可选）' })
    const submit = h('button', { class: 'btn btn-primary btn-block', type: 'submit', text: '注册并登录' })

    return h(
      'form',
      {
        onsubmit: (event: Event) => {
          event.preventDefault()
          void run(submit, async () => {
            if (!code.value.trim()) throw new ApiError('请输入短信验证码')
            const data = await api.register({
              mobile: mobile.value.trim(),
              password: password.value,
              code: code.value.trim(),
              nickname: nickname.value.trim() || undefined,
            })
            await afterLogin(data, true)
          })
        },
      },
      field('手机号', mobile),
      field('验证码', h('div', { class: 'sms-row' }, code, sendBtn)),
      field('密码', password, '至少 6 位'),
      field('昵称', nickname),
      submit,
    )
  }

  // ── 短信登录 ──

  function smsForm(): HTMLElement {
    const mobile = h('input', { type: 'tel', value: DEMO_ACCOUNT, placeholder: '11 位手机号' })
    const code = h('input', { type: 'text', placeholder: '短信验证码' })
    const sendBtn = h('button', {
      class: 'btn',
      type: 'button',
      text: '获取验证码',
      onclick: () => void sendCode(mobile, sendBtn, 'login'),
    })
    const submit = h('button', { class: 'btn btn-primary btn-block', type: 'submit', text: '登 录' })

    return h(
      'form',
      {
        onsubmit: (event: Event) => {
          event.preventDefault()
          void run(submit, async () => {
            const data = await api.loginBySms(mobile.value.trim(), code.value.trim())
            await afterLogin(data, false)
          })
        },
      },
      field('手机号', mobile),
      field('验证码', h('div', { class: 'sms-row' }, code, sendBtn)),
      submit,
    )
  }

  // ── 公共动作 ──

  function field(label: string, control: HTMLElement, hint?: string): HTMLElement {
    return h(
      'div',
      { class: 'field' },
      h('label', { class: 'field-label', text: label }),
      control,
      hint ? h('div', { class: 'field-hint', text: hint }) : null,
    )
  }

  /** 统一的按钮忙碌态 + 错误提示，避免每个表单各写一遍 */
  async function run(button: HTMLButtonElement, action: () => Promise<void>): Promise<void> {
    const label = button.textContent
    button.disabled = true
    button.textContent = '处理中…'
    try {
      await action()
    } catch (error) {
      toast(error instanceof ApiError ? error.message : '操作失败，请稍后重试', 'error')
      button.disabled = false
      button.textContent = label
    }
  }

  /** 发送验证码并进入 60 秒倒计时（间隔由后端返回，避免前后端各写一个常量） */
  async function sendCode(mobile: HTMLInputElement, button: HTMLButtonElement, scene: SmsScene): Promise<void> {
    const value = mobile.value.trim()
    if (!value) {
      toast('请先填写手机号', 'error')
      mobile.focus()
      return
    }
    button.disabled = true
    try {
      const result = await api.sendSms(value, scene)
      toast(`验证码已发送至 ${result.mobile}，请查看后端控制台日志`, 'success')
      let remain = result.resend_after
      const tick = (): void => {
        if (remain <= 0) {
          stopCountdown()
          button.disabled = false
          button.textContent = '获取验证码'
          return
        }
        button.textContent = `${remain} 秒后重发`
        remain -= 1
      }
      tick()
      countdownTimer = window.setInterval(tick, 1000)
    } catch (error) {
      button.disabled = false
      toast(error instanceof ApiError ? error.message : '验证码发送失败', 'error')
    }
  }

  /** 登录/注册成功后的统一收尾：写会话 → 拉家庭列表 → 进首页 */
  async function afterLogin(data: AppLoginOut, isNew: boolean): Promise<void> {
    store.setLogin(data)
    try {
      await refreshFamilies()
    } catch {
      // 家庭列表拉取失败不挡进首页（首页自己会再拉一次并显示错误）
    }
    toast(isNew ? '注册成功，已自动登录' : '登录成功', 'success')
    nav.list()
  }
}

const TAB_LABEL: Record<Tab, string> = {
  password: '密码登录',
  register: '注册',
  sms: '短信登录',
}
