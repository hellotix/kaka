/**
 * 极简 DOM 工具集 —— 不引入任何 UI 框架，够这个演示用。
 *
 * 核心是 h()：一个 hyperscript 风格的构建函数，
 *
 *   h('div', { class: 'card' },
 *     h('b', { text: '标题' }),
 *     '正文',
 *   )
 *
 * 支持的特殊属性：
 * - class / text：类名（string）与纯文本（用 textContent，天然防 XSS）
 * - style：样式对象 { color: 'red' }
 * - onclick 等 on*：事件监听函数
 * - 其余键：走 setAttribute（值为 true 时设空串，false/null/undefined 跳过）
 */

export type Child = Node | string | number | boolean | null | undefined | Child[]

type Attrs = Record<string, unknown>

// 两个重载：传字面量标签（'input'）时返回精确元素类型，
// 这样 input.value / select.value 这类属性访问才通得过 strict 类型检查；
// 传变量标签时退回 HTMLElement。
export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs?: Attrs | null,
  ...children: Child[]
): HTMLElementTagNameMap[K]
export function h(tag: string, attrs?: Attrs | null, ...children: Child[]): HTMLElement
export function h(tag: string, attrs: Attrs | null = null, ...children: Child[]): HTMLElement {
  const el = document.createElement(tag)

  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (value === null || value === undefined || value === false) continue
      if (key === 'class') {
        el.className = String(value)
      } else if (key === 'text') {
        el.textContent = String(value)
      } else if (key === 'value') {
        // value 必须走 property 而不是 attribute：
        // textarea 的初始内容无法通过 attribute 设置；select 也要 property 赋值才会选中对应 option
        ;(el as HTMLInputElement).value = String(value)
      } else if (key === 'style' && typeof value === 'object') {
        Object.assign(el.style, value as Partial<CSSStyleDeclaration>)
      } else if (key.startsWith('on') && typeof value === 'function') {
        el.addEventListener(key.slice(2).toLowerCase(), value as EventListener)
      } else if (value === true) {
        el.setAttribute(key, '')
      } else {
        el.setAttribute(key, String(value))
      }
    }
  }

  appendChildren(el, children)
  return el
}

function appendChildren(parent: Node, children: Child[]): void {
  for (const child of children) {
    if (child === null || child === undefined || child === false || child === true) continue
    if (Array.isArray(child)) {
      appendChildren(parent, child)
    } else {
      parent.appendChild(child instanceof Node ? child : document.createTextNode(String(child)))
    }
  }
}

/** 整页替换：清空 #app 并挂入新内容（所有视图都通过它渲染） */
export function mount(...children: Child[]): void {
  const root = document.getElementById('app')
  if (!root) return
  root.replaceChildren()
  appendChildren(root, children)
}

// ══════════════════ 提示与弹层 ══════════════════

let toastTimer = 0

/** 轻提示：2.4 秒后自动消失，同一时刻只保留一条 */
export function toast(message: string, type: 'info' | 'error' | 'success' = 'info'): void {
  document.querySelectorAll('.toast').forEach((node) => node.remove())
  const node = h('div', { class: `toast${type === 'info' ? '' : ` toast-${type}`}`, text: message })
  document.body.appendChild(node)
  window.clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => node.remove(), 2400)
}

/** 确认框：resolve(true)=用户点了确定 */
export function confirmBox(
  message: string,
  options: { title?: string; okText?: string; danger?: boolean } = {},
): Promise<boolean> {
  return new Promise((resolve) => {
    const close = (result: boolean): void => {
      mask.remove()
      resolve(result)
    }
    const mask = h(
      'div',
      {
        class: 'modal-mask',
        onclick: (event: MouseEvent) => {
          if (event.target === mask) close(false)
        },
      },
      h(
        'div',
        { class: 'modal' },
        h('div', { class: 'modal-title', text: options.title ?? '请确认' }),
        h('div', { class: 'modal-body', text: message }),
        h(
          'div',
          { class: 'modal-actions' },
          h('button', { class: 'btn', onclick: () => close(false) }, '取消'),
          h(
            'button',
            { class: `btn ${options.danger ? 'btn-danger' : 'btn-primary'}`, onclick: () => close(true) },
            options.okText ?? '确定',
          ),
        ),
      ),
    )
    document.body.appendChild(mask)
  })
}

export interface SheetItem {
  label: string
  icon?: string
  active?: boolean
  danger?: boolean
  onClick: () => void
}

/** 底部动作菜单（家庭切换、更多操作都用它） */
export function openSheet(title: string, items: SheetItem[]): void {
  const close = (): void => mask.remove()
  const mask = h(
    'div',
    {
      class: 'sheet-mask',
      onclick: (event: MouseEvent) => {
        if (event.target === mask) close()
      },
    },
    h(
      'div',
      { class: 'sheet' },
      h('div', { class: 'sheet-title', text: title }),
      items.map((item) =>
        h(
          'div',
          {
            class: `menu-item${item.danger ? ' danger' : ''}`,
            onclick: () => {
              close()
              item.onClick()
            },
          },
          item.icon ? `${item.icon} ` : '',
          item.label,
          item.active ? h('span', { class: 'check', text: '✓' }) : null,
        ),
      ),
    ),
  )
  document.body.appendChild(mask)
}

// ══════════════════ 弹窗表单 ══════════════════

export interface ModalFieldOption {
  value: string
  label: string
}

// password 单独列出来：改密码弹窗不能把用户输入的密码明文显示在屏幕上
export type ModalFieldType = 'text' | 'password' | 'number' | 'date' | 'datetime' | 'textarea' | 'select'

export interface ModalField {
  key: string
  label: string
  type?: ModalFieldType
  value?: string | number | null
  placeholder?: string
  required?: boolean
  /** type='select' 的候选项 */
  options?: ModalFieldOption[]
}

/**
 * 弹出式表单（详情页的「再入一批 / 编辑批次」用它）。
 *
 * onSubmit 抛异常时弹窗保持打开，让用户改完再提交（错误文案由调用方 toast）；
 * 返回值统一是字符串（表单天然产出字符串），数字/日期由调用方自己转换。
 */
export function openFormModal(
  title: string,
  fields: ModalField[],
  onSubmit: (values: Record<string, string>) => Promise<void> | void,
): void {
  const inputs = new Map<string, HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>()
  const mask = h('div', {
    class: 'modal-mask',
    onclick: (event: MouseEvent) => {
      if (event.target === mask) close()
    },
  })

  const close = (): void => mask.remove()

  function fieldRow(field: ModalField): HTMLElement {
    const type = field.type ?? 'text'
    const value = field.value === null || field.value === undefined ? '' : String(field.value)

    let control: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
    if (type === 'textarea') {
      control = h('textarea', { class: 'modal-input', rows: 2, value })
    } else if (type === 'select') {
      control = h(
        'select',
        { class: 'modal-input' },
        (field.options ?? []).map((option) => h('option', { value: option.value, text: option.label })),
      )
      control.value = value
    } else {
      // datetime-local 的取值格式是 2026-09-30T10:00，后端 datetime 字段能直接解析
      // number 必须给 step=any：默认 step=1 会让 45.5 这种金额卡在浏览器原生校验里，
      // 表单连 submit 事件都不派发（表现就是「点保存没反应」）
      control = h('input', {
        class: 'modal-input',
        type: type === 'datetime' ? 'datetime-local' : type,
        step: type === 'number' ? 'any' : null,
        value,
      })
      if (field.placeholder) control.setAttribute('placeholder', field.placeholder)
    }
    inputs.set(field.key, control)

    return h(
      'div',
      { class: 'field' },
      h(
        'label',
        { class: 'field-label' },
        field.label,
        field.required ? h('span', { class: 'required', text: '*' }) : null,
      ),
      control,
    )
  }

  async function submit(): Promise<void> {
    const values: Record<string, string> = {}
    for (const [key, control] of inputs) values[key] = control.value.trim()

    for (const field of fields) {
      if (field.required && !values[field.key]) {
        toast(`请填写「${field.label}」`)
        inputs.get(field.key)?.focus()
        return
      }
    }

    const button = form.querySelector<HTMLButtonElement>('button[type="submit"]')
    if (button) {
      button.disabled = true
      button.textContent = '保存中…'
    }
    try {
      await onSubmit(values)
      close()
    } catch (error) {
      toast(error instanceof Error ? error.message : '保存失败', 'error')
    } finally {
      if (button) {
        button.disabled = false
        button.textContent = '保存'
      }
    }
  }

  const form = h(
    'form',
    {
      class: 'modal',
      // 关掉原生校验：必填/格式由下面的 submit 统一判，提示口径才和整页表单一致
      novalidate: true,
      onsubmit: (event: Event) => {
        event.preventDefault()
        void submit()
      },
    },
    h('div', { class: 'modal-title', text: title }),
    h('div', { class: 'modal-body' }, fields.map((field) => fieldRow(field))),
    h(
      'div',
      { class: 'modal-actions' },
      h('button', { class: 'btn', type: 'button', onclick: () => close() }, '取消'),
      h('button', { class: 'btn btn-primary', type: 'submit', text: '保存' }),
    ),
  )

  mask.appendChild(form)
  document.body.appendChild(mask)
  // 自动聚焦第一个输入项，手机上省一次点击
  inputs.values().next().value?.focus()
}

// ══════════════════ 展示小工具 ══════════════════

export const VISIBILITY_TEXT: Record<string, string> = {
  family: '全家可见',
  member: '仅本人可见',
  private: '私密',
}

export function fmtDate(value: string | null | undefined): string {
  return value ? value.slice(0, 10) : '—'
}

export function fmtDateTime(value: string | null | undefined): string {
  return value ? value.slice(0, 16) : '—'
}

/** 距今天数：正数=还没到期，0=今天，负数=已过期；解析失败返回 null */
export function daysUntil(dateStr: string | null | undefined): number | null {
  if (!dateStr) return null
  const target = new Date(`${dateStr.slice(0, 10)}T00:00:00`)
  if (Number.isNaN(target.getTime())) return null
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.round((target.getTime() - today.getTime()) / 86400000)
}

/** 效期标签：已过期/今天到期=红，30 天内=黄，更远=灰 */
export function expiryBadge(dateStr: string | null | undefined): HTMLElement | null {
  const days = daysUntil(dateStr)
  if (days === null) return null
  if (days < 0) return h('span', { class: 'tag tag-red', text: `已过期 ${-days} 天` })
  if (days === 0) return h('span', { class: 'tag tag-red', text: '今天到期' })
  if (days <= 30) return h('span', { class: 'tag tag-amber', text: `${days} 天后到期` })
  return h('span', { class: 'tag', text: `${fmtDate(dateStr).slice(5)} 到期` })
}

export function loadingNode(text = '加载中…'): HTMLElement {
  return h('div', { class: 'loading', text })
}

export function emptyNode(icon: string, text: string): HTMLElement {
  return h('div', { class: 'empty' }, h('div', { class: 'icon', text: icon }), h('div', { text }))
}

/** 数字展示：整数不带小数点，小数最多两位 */
export function fmtQty(value: number | null | undefined): string {
  if (value === null || value === undefined) return '0'
  return Number.isInteger(value) ? String(value) : value.toFixed(2)
}

/** 金额展示：¥12.5 / ¥12.50，null 显示为 — */
export function fmtMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return `¥${Number.isInteger(value) ? value : value.toFixed(2)}`
}
