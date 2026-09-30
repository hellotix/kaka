/**
 * 物品详情页 —— 档案信息 / 扩展属性 / 批次管理，以及物品本身的编辑与删除。
 *
 * 数据来自两处接口：
 * - api.itemDetail(id)：档案 + 批次明细（列表接口不返回 batches，细节都在这里）
 * - api.attrSchema(category_id)：扩展属性的中文 label、单位、候选项。
 *   attrs 里存的键是 code（如 "shelf_life"），没有模板就只能显示 code 本身，
 *   所以这一步失败也照常渲染，不挡详情页。
 *
 * 批次的新增/修改/删除都走 openFormModal 而不跳整页表单：
 * 批次只有几个短字段，弹窗里改完直接回到详情看新结果，路径更短。
 *
 * 一个刻意的设计：任何批次操作之后都重新拉一次详情（而不是本地改数字）。
 * 因为「剩余总量 / 最近到期日 / 批次数」是后端算出来的，
 * 前端自己加减一遍迟早和后端口径分叉 —— 演示项目更没必要省这一次请求。
 */

import { api } from '../api'
import { nav } from '../router'
import type { AttrTemplate, BatchPayload, Item, ItemBatch } from '../types'
import { BATCH_STATUS_TEXT, optionLabel, optionValue } from '../types'
import type { Child, ModalField } from '../ui'
import {
  confirmBox,
  daysUntil,
  expiryBadge,
  fmtDate,
  fmtDateTime,
  fmtMoney,
  fmtQty,
  h,
  loadingNode,
  mount,
  openFormModal,
  openSheet,
  toast,
  VISIBILITY_TEXT,
} from '../ui'

/** 批次状态标签配色：在用=绿，已过期=红，其余（耗尽/丢弃）用中性灰 */
const BATCH_STATUS_TAG: Record<number, string> = {
  1: 'tag tag-green',
  2: 'tag',
  3: 'tag tag-red',
  4: 'tag',
}

const BATCH_STATUS_OPTIONS = Object.entries(BATCH_STATUS_TEXT).map(([value, label]) => ({ value, label }))

export function renderDetail(itemId: number): void {
  let item: Item | null = null
  let attrTemplates: AttrTemplate[] = []

  void load()

  // ══════════════════ 加载 ══════════════════

  async function load(): Promise<void> {
    mount(h('div', { class: 'page' }, navbarShell('物品详情'), content(loadingNode())))
    let data: Item
    try {
      data = await api.itemDetail(itemId)
    } catch (error) {
      const message = error instanceof Error ? error.message : '详情加载失败'
      mount(h('div', { class: 'page' }, navbarShell('物品详情'), content(errorBox(message))))
      return
    }
    item = data
    // 属性模板只用于把 code 翻成中文 label；拉不到就退回显示 code
    attrTemplates = data.category_id ? await api.attrSchema(data.category_id).catch(() => []) : []
    render()
  }

  function render(): void {
    const data = item
    if (!data) return
    mount(
      h(
        'div',
        { class: 'page' },
        navbarShell(data.name ?? '物品详情', data.category_name ?? '未归类', true),
        content(imagesCard(data), infoCard(data), attrsCard(data), batchesCard(data)),
      ),
    )
  }

  function content(...children: Child[]): HTMLElement {
    // no-fab：详情页的操作都在顶栏和卡片里，不需要悬浮按钮腾出的底部留白
    return h('div', { class: 'content no-fab' }, ...children)
  }

  // ══════════════════ 顶栏 ══════════════════

  function navbarShell(title: string, sub?: string, withActions = false): HTMLElement {
    return h(
      'div',
      { class: 'navbar' },
      h('button', { class: 'btn btn-ghost', text: '返回', onclick: () => nav.list() }),
      h('div', { class: 'navbar-title' }, title, sub ? h('span', { class: 'sub', text: sub }) : null),
      withActions
        ? h(
            'div',
            { class: 'navbar-actions' },
            h('button', { class: 'btn btn-sm', text: '编辑', onclick: () => nav.form(itemId) }),
            h('button', {
              class: 'btn btn-sm btn-ghost',
              text: '更多',
              onclick: () =>
                openSheet('物品操作', [{ label: '删除该物品', danger: true, onClick: () => void deleteItem() }]),
            }),
          )
        : null,
    )
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

  // ══════════════════ 展示区块 ══════════════════

  function imagesCard(data: Item): Child {
    if (data.images.length === 0) return null
    return h(
      'div',
      { class: 'card' },
      h(
        'div',
        { class: 'img-grid' },
        data.images.map((url) =>
          h(
            'div',
            {
              class: 'img-cell',
              // 手机上缩略图太小，点开新标签看原图（在用户手势里打开，不会被拦截）
              onclick: () => window.open(url, '_blank'),
            },
            h('img', { src: url, alt: '物品图片' }),
          ),
        ),
      ),
    )
  }

  function infoCard(data: Item): HTMLElement {
    const unit = data.unit ?? '件'
    return h(
      'div',
      { class: 'card' },
      kv('分类', data.category_name ?? '未归类'),
      kv('剩余库存', `${fmtQty(data.total_remain_qty)} ${unit}（${data.batch_count} 个批次）`),
      kv('最近效期', data.nearest_expiry_date ? expiryBadge(data.nearest_expiry_date) : null),
      kv('品牌', data.brand),
      kv('规格', data.spec),
      kv('单位', data.unit),
      kv('存放位置', data.location),
      kv('参考单价', data.ref_price === null || data.ref_price === undefined ? null : fmtMoney(data.ref_price)),
      kv('购买渠道', data.purchase_channel),
      kv('条码', data.barcode),
      kv('可见范围', data.visibility ? (VISIBILITY_TEXT[data.visibility] ?? data.visibility) : null),
      kv('录入人', data.owner_name),
      kv('录入时间', data.created_time ? fmtDateTime(data.created_time) : null),
      kv('备注', data.remark),
    )
  }

  function attrsCard(data: Item): Child {
    const rows = attrRows(data)
    return rows.length === 0 ? null : h('div', { class: 'card' }, ...rows)
  }

  function batchesCard(data: Item): HTMLElement {
    const batches = data.batches
    return h(
      'div',
      { class: 'card' },
      h(
        'div',
        { class: 'batch-head' },
        h('b', { text: `批次记录（${batches.length}）` }),
        h('span', { class: 'spacer' }),
        h('button', { class: 'btn btn-sm', text: '再入一批', onclick: () => addBatch(data) }),
      ),
      batches.length === 0
        ? h('div', { class: 'field-hint', text: '还没有批次：点「再入一批」记录第一次入库' })
        : batches.map((batch) => batchCard(data, batch)),
    )
  }

  function batchCard(data: Item, batch: ItemBatch): HTMLElement {
    const status = batch.status ?? 1
    const unit = data.unit ?? '件'
    return h(
      'div',
      { class: 'batch-card' },
      h(
        'div',
        { class: 'batch-head' },
        h('b', { text: `剩 ${fmtQty(batch.remain_qty)} / ${fmtQty(batch.quantity)} ${unit}` }),
        h('span', { class: BATCH_STATUS_TAG[status] ?? 'tag', text: BATCH_STATUS_TEXT[status] ?? `状态 ${status}` }),
        h('span', { class: 'spacer' }),
        h('button', { class: 'btn btn-sm btn-ghost', text: '修改', onclick: () => editBatch(batch) }),
        h('button', { class: 'btn btn-sm btn-ghost', text: '删除', onclick: () => void removeBatch(batch) }),
      ),
      h('div', { class: 'batch-line', text: `购入 ${fmtDate(batch.purchase_time)} · 单价 ${fmtMoney(batch.unit_price)}` }),
      h(
        'div',
        { class: 'batch-line' },
        `生产 ${fmtDate(batch.production_date)} · 有效期至 ${fmtDate(batch.expiry_date)} `,
        expiryWarn(batch.expiry_date),
      ),
      batch.channel ? h('div', { class: 'batch-line', text: `渠道 ${batch.channel}` }) : null,
      batch.remark ? h('div', { class: 'batch-line', text: `备注 ${batch.remark}` }) : null,
    )
  }

  /**
   * 批次的效期告警：只在「已过期 / 临近 30 天」时冒红黄标签。
   *
   * 没直接复用 ui.ts 的 expiryBadge：那个在效期还远时会显示灰色「xx 到期」，
   * 而批次行前面已经把日期写全了，再补一个日期标签就是重复信息。
   */
  function expiryWarn(dateStr: string | null): Child {
    const days = daysUntil(dateStr)
    if (days === null) return null
    if (days < 0) return h('span', { class: 'tag tag-red', text: `已过期 ${-days} 天` })
    if (days === 0) return h('span', { class: 'tag tag-red', text: '今天到期' })
    if (days <= 30) return h('span', { class: 'tag tag-amber', text: `${days} 天后到期` })
    return null
  }

  function kv(key: string, value: Child): Child {
    if (value === null || value === undefined || value === '') return null
    return h('div', { class: 'kv' }, h('div', { class: 'kv-k', text: key }), h('div', { class: 'kv-v' }, value))
  }

  // ══════════════════ 扩展属性取值 ══════════════════

  /** 先按模板顺序出行，再补模板里没有的键（换过分类、删过模板时旧数据不静默丢） */
  function attrRows(data: Item): HTMLElement[] {
    const values = data.attrs ?? {}
    const rows: HTMLElement[] = []
    const used = new Set<string>()

    for (const template of attrTemplates) {
      const code = template.code
      if (!code || used.has(code) || isEmptyAttr(values[code])) continue
      used.add(code)
      addRow(rows, template.label ?? code, attrText(values[code], template))
    }
    for (const [code, value] of Object.entries(values)) {
      if (used.has(code) || isEmptyAttr(value)) continue
      addRow(rows, code, attrText(value, undefined))
    }
    return rows
  }

  function addRow(rows: HTMLElement[], key: string, text: string): void {
    if (!text) return
    rows.push(h('div', { class: 'kv' }, h('div', { class: 'kv-k', text: key }), h('div', { class: 'kv-v', text })))
  }

  function isEmptyAttr(value: unknown): boolean {
    if (value === null || value === undefined || value === '') return true
    return Array.isArray(value) && value.length === 0
  }

  /** 属性值 → 展示文案：布尔转是/否，选项值换成中文 label，数字补单位 */
  function attrText(value: unknown, template: AttrTemplate | undefined): string {
    if (typeof value === 'boolean') return value ? '是' : '否'

    const options = template?.options ?? []
    const toLabel = (raw: unknown): string => {
      const hit = options.find((option) => optionValue(option) === String(raw))
      return hit === undefined ? String(raw) : optionLabel(hit)
    }

    let text: string
    if (Array.isArray(value)) text = value.map(toLabel).join('、')
    else if (template?.type === 'select') text = toLabel(value)
    else text = String(value)

    return template?.unit ? `${text} ${template.unit}` : text
  }

  // ══════════════════ 批次操作 ══════════════════

  /** 新增批次：单价与渠道从最近一批预填，复购时通常只改数量 */
  function addBatch(data: Item): void {
    const last = data.batches[0]
    openFormModal(
      '再入一批',
      [
        { key: 'quantity', label: `进货数量（${data.unit ?? '件'}）`, type: 'number', required: true },
        { key: 'unit_price', label: '单价（元）', type: 'number', value: last?.unit_price ?? null },
        { key: 'production_date', label: '生产日期', type: 'date' },
        { key: 'expiry_date', label: '有效期至', type: 'date' },
        { key: 'channel', label: '购买渠道', value: last?.channel ?? null },
        { key: 'remark', label: '备注' },
      ],
      async (values) => {
        const quantity = Number(values.quantity)
        if (!Number.isFinite(quantity) || quantity <= 0) throw new Error('进货数量必须是大于 0 的数字')
        const payload: BatchPayload = { ...buildBatchPayload(values), quantity, item_id: itemId }
        await api.batchCreate(payload)
        toast('已新增批次', 'success')
        await load()
      },
    )
  }

  function editBatch(batch: ItemBatch): void {
    const fields: ModalField[] = [
      { key: 'quantity', label: '进货数量', type: 'number', value: batch.quantity },
      { key: 'remain_qty', label: '剩余数量', type: 'number', value: batch.remain_qty },
      { key: 'unit_price', label: '单价（元）', type: 'number', value: batch.unit_price },
      { key: 'production_date', label: '生产日期', type: 'date', value: batch.production_date },
      { key: 'expiry_date', label: '有效期至', type: 'date', value: batch.expiry_date },
      { key: 'channel', label: '购买渠道', value: batch.channel },
      {
        key: 'status',
        label: '批次状态',
        type: 'select',
        value: String(batch.status ?? 1),
        // 首项「不修改」：后端 update 是 exclude_unset 语义，空串即不提交该字段
        options: [{ value: '', label: '不修改' }, ...BATCH_STATUS_OPTIONS],
      },
      { key: 'remark', label: '备注', value: batch.remark },
    ]

    openFormModal('修改批次', fields, async (values) => {
      const id = batch.id
      if (id === null || id === undefined) throw new Error('批次缺少 ID，无法修改')

      const payload = buildBatchPayload(values)
      if (values.status) {
        const status = Number(values.status)
        if (Number.isFinite(status)) payload.status = status
      }
      if (Object.keys(payload).length === 0) throw new Error('没有需要修改的内容')

      await api.batchUpdate(id, payload)
      toast('批次已更新', 'success')
      await load()
    })
  }

  async function removeBatch(batch: ItemBatch): Promise<void> {
    const id = batch.id
    if (id === null || id === undefined) {
      toast('批次缺少 ID，无法删除', 'error')
      return
    }
    const ok = await confirmBox('删除后这一批的库存和效期提醒都会消失，确定删除吗？', {
      title: '删除批次',
      okText: '删除',
      danger: true,
    })
    if (!ok) return
    try {
      await api.batchDelete(id)
      toast('已删除批次', 'success')
      await load()
    } catch (error) {
      toast(error instanceof Error ? error.message : '删除失败', 'error')
    }
  }

  /**
   * 弹窗产出的字符串 → 批次提交体：只带「填了且合法」的字段。
   *
   * 后端 update 用 exclude_unset（没传的字段不改），新增时空字段也不必发出去，
   * 所以这里宁可不写键，也不要传个空串过去撞 Pydantic 的校验。
   */
  function buildBatchPayload(values: Record<string, string>): BatchPayload {
    const payload: BatchPayload = {}
    const num = (key: string, min: number): number | null => {
      const raw = values[key]
      if (!raw) return null
      const parsed = Number(raw)
      return Number.isFinite(parsed) && parsed >= min ? parsed : null
    }

    const remain = num('remain_qty', 0)
    if (remain !== null) payload.remain_qty = remain
    const price = num('unit_price', 0)
    if (price !== null) payload.unit_price = price
    if (values.production_date) payload.production_date = values.production_date.slice(0, 10)
    if (values.expiry_date) payload.expiry_date = values.expiry_date.slice(0, 10)
    if (values.channel) payload.channel = values.channel
    if (values.remark) payload.remark = values.remark
    return payload
  }

  // ══════════════════ 删除物品 ══════════════════

  async function deleteItem(): Promise<void> {
    const data = item
    const ok = await confirmBox(`「${data?.name ?? '该物品'}」及其 ${data?.batch_count ?? 0} 个批次都会被删除，确定吗？`, {
      title: '删除物品',
      okText: '删除',
      danger: true,
    })
    if (!ok) return
    try {
      await api.itemDelete([itemId])
      toast('已删除物品', 'success')
      nav.list()
    } catch (error) {
      toast(error instanceof Error ? error.message : '删除失败', 'error')
    }
  }
}
