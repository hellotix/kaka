/**
 * 录入 / 编辑表单。
 *
 * 两处与后端强相关的约定：
 * 1. 扩展属性按分类动态渲染：模板来自 GET /app/erp/attr/schema/{category_id}，
 *    值的类型转换见 collectAttrs()，与后端 erp/core/attrs.py 的校验一一对应
 *    （number→数字、bool→布尔、multi_select→字符串数组、未填的可选属性不写键）。
 * 2. 更新接口是 exclude_unset 语义 —— 没传的字段就当没改，
 *    所以「清空输入框」并不会把字段改回 NULL（后端 exclude_none 也过滤了 null），
 *    演示里如实保留这个行为，不额外造一套「清空」状态。
 *
 * 批次只在新建时一起录入（初始批次）；后续复购/改批次在详情页做，
 * 对应后端的 item/batch/create 与 batch/update 接口。
 */

import { ApiError, api } from '../api'
import { nav } from '../router'
import type { FormPrefill } from '../router'
import type {
  AttrTemplate,
  AttrValueType,
  BatchPayload,
  CategoryNode,
  Item,
  ItemPayload,
  ItemVisibility,
} from '../types'
import { optionLabel, optionValue } from '../types'
import { VISIBILITY_TEXT, h, loadingNode, mount, toast } from '../ui'

/** 图片数量上限：与后端上传单文件、前端一屏 4 列的展示都匹配 */
const MAX_IMAGES = 9

export function renderForm(itemId?: number, prefill?: FormPrefill): void {
  const editId: number | null = typeof itemId === 'number' ? itemId : null
  const editing = editId !== null

  let item: Item | null = null
  let categories: CategoryNode[] = []
  let templates: AttrTemplate[] = []
  let attrFields: AttrField[] = []
  const images: string[] = []

  // ── 基础字段控件（先建出来，数据载入后再填值） ──
  const nameInput = h('input', { type: 'text', maxlength: 128, placeholder: '例如：布洛芬缓释胶囊' })
  // 换分类要立刻重拉该分类的属性模板：扩展属性是跟着分类走的，
  // 不刷新的话用户看到的还是上一个分类的字段（提交时会被后端按新模板丢弃）
  const categorySelect = h('select', { onchange: () => void loadAttrs() }, h('option', { value: '', text: '未归类' }))
  const barcodeInput = h('input', { type: 'text', maxlength: 64, placeholder: '扫一扫或手动填写' })
  const brandInput = h('input', { type: 'text', maxlength: 64, placeholder: '例如：芬必得' })
  const specInput = h('input', { type: 'text', maxlength: 64, placeholder: '例如：0.3g*20 粒' })
  const unitInput = h('input', { type: 'text', maxlength: 16, placeholder: '盒 / 瓶 / 袋' })
  const locationInput = h('input', { type: 'text', maxlength: 64, placeholder: '例如：客厅药箱' })
  const priceInput = h('input', { type: 'number', step: 'any', min: '0', placeholder: '参考单价' })
  const channelInput = h('input', { type: 'text', maxlength: 64, placeholder: '例如：京东 / 楼下超市' })
  const visibilitySelect = h(
    'select',
    {},
    (['family', 'member', 'private'] as ItemVisibility[]).map((value) =>
      h('option', { value, text: VISIBILITY_TEXT[value] }),
    ),
  )
  const remarkInput = h('textarea', { maxlength: 500, placeholder: '备注（如：儿童慎用、开封后冷藏）' })

  // ── 图片 ──
  const imgGrid = h('div', { class: 'img-grid' })
  const fileInput = h('input', {
    type: 'file',
    accept: 'image/*',
    style: { display: 'none' },
    onchange: () => void uploadFile(),
  })

  // ── 初始批次（仅新建时展示） ──
  const batchToggle = h('input', { type: 'checkbox', checked: true })
  const batchQty = h('input', { type: 'number', step: 'any', min: '0', placeholder: '本次进货数量' })
  const batchPrice = h('input', { type: 'number', step: 'any', min: '0', placeholder: '单价（可空）' })
  const batchProduction = h('input', { type: 'date' })
  const batchExpiry = h('input', { type: 'date' })
  const batchChannel = h('input', { type: 'text', maxlength: 64, placeholder: '例如：京东' })
  const batchBody = h(
    'div',
    { style: { display: batchToggle.checked ? '' : 'none' } },
    h('div', { class: 'field-row' }, field('数量', batchQty), field('单价', batchPrice)),
    h('div', { class: 'field-row' }, field('生产日期', batchProduction), field('有效期至', batchExpiry)),
    field('购买渠道', batchChannel),
  )
  batchToggle.addEventListener('change', () => {
    batchBody.style.display = batchToggle.checked ? '' : 'none'
  })

  const attrBox = h('div')
  const submitButton = h('button', {
    class: 'btn btn-primary',
    text: editing ? '保存修改' : '保存并入库',
    onclick: () => void submit(),
  })

  mount(loadingNode('正在准备表单…'))
  void load()

  // ══════════════════ 载入 ══════════════════

  async function load(): Promise<void> {
    try {
      categories = flatten(await api.categoryTree())
    } catch {
      // 分类拿不到也能录入，只是不能归类
      categories = []
    }
    renderCategoryOptions() // 必须先把 option 填进 select，后面赋值才有意义

    if (editId !== null) {
      try {
        item = await api.itemDetail(editId)
      } catch (error) {
        toast(error instanceof ApiError ? error.message : '物品加载失败', 'error')
        nav.list()
        return
      }
      fillFromItem()
    } else if (prefill?.barcode) {
      barcodeInput.value = prefill.barcode
    }

    await loadAttrs()
    renderImages()
    mount(page())
  }

  function flatten(nodes: CategoryNode[], level = 1): CategoryNode[] {
    const result: CategoryNode[] = []
    if (level > 2) return result
    for (const node of nodes) {
      result.push(node)
      if (node.children.length > 0) result.push(...flatten(node.children, level + 1))
    }
    return result
  }

  function renderCategoryOptions(): void {
    // 第二项是数组，必须展开成逐个节点（replaceChildren 不递归吃数组）
    categorySelect.replaceChildren(
      h('option', { value: '', text: '未归类' }),
      ...categories.map((node) =>
        h('option', {
          value: node.id === null ? '' : String(node.id),
          // 二级分类缩进一格，一眼能看出层级
          text: `${node.level && node.level > 1 ? '　' : ''}${node.name ?? '未命名分类'}`,
        }),
      ),
    )
  }

  function fillFromItem(): void {
    if (!item) return
    nameInput.value = item.name ?? ''
    categorySelect.value = item.category_id === null ? '' : String(item.category_id)
    barcodeInput.value = item.barcode ?? ''
    brandInput.value = item.brand ?? ''
    specInput.value = item.spec ?? ''
    unitInput.value = item.unit ?? ''
    locationInput.value = item.location ?? ''
    priceInput.value = item.ref_price === null ? '' : String(item.ref_price)
    channelInput.value = item.purchase_channel ?? ''
    visibilitySelect.value = item.visibility ?? 'family'
    remarkInput.value = item.remark ?? ''
    images.splice(0, images.length, ...item.images)
  }

  // ══════════════════ 扩展属性 ══════════════════

  async function loadAttrs(): Promise<void> {
    const categoryId = categorySelect.value ? Number(categorySelect.value) : null
    if (categoryId === null) {
      templates = []
      renderAttrs()
      return
    }
    try {
      templates = await api.attrSchema(categoryId)
    } catch (error) {
      templates = []
      toast(error instanceof ApiError ? error.message : '扩展属性加载失败', 'error')
    }
    renderAttrs()
  }

  function renderAttrs(): void {
    attrFields = []
    if (templates.length === 0) {
      attrBox.replaceChildren(
        h('div', { class: 'field-hint', text: '未选择分类，或该分类没有配置扩展属性' }),
      )
      return
    }
    attrBox.replaceChildren(...templates.map((tpl) => renderAttrField(tpl)))
  }

  /** 已有值优先，其次是模板默认值；新建时基本都走默认值分支 */
  function attrValue(tpl: AttrTemplate): unknown {
    const attrs = item?.attrs ?? null
    const current = attrs === null ? undefined : attrs[tpl.code ?? '']
    if (current !== undefined && current !== null) return current
    return tpl.default_value ?? undefined
  }

  function renderAttrField(tpl: AttrTemplate): HTMLElement {
    const label = tpl.label ?? tpl.code ?? '扩展属性'
    const type = (tpl.type ?? 'text') as AttrValueType
    const value = attrValue(tpl)
    let control: HTMLElement
    let read: () => unknown

    switch (type) {
      case 'textarea': {
        const el = h('textarea', { value: str(value) })
        control = el
        read = () => el.value.trim() || undefined
        break
      }
      case 'number': {
        const el = h('input', { type: 'number', step: 'any', value: str(value) })
        control = el
        read = () => {
          const text = el.value.trim()
          if (!text) return undefined
          const num = Number(text)
          return Number.isNaN(num) ? undefined : num
        }
        break
      }
      case 'date': {
        const el = h('input', { type: 'date', value: str(value).slice(0, 10) })
        control = el
        read = () => el.value || undefined
        break
      }
      case 'bool': {
        // 用三态下拉而不是勾选框：勾选框分不出「没填」和「否」，
        // 而后端把布尔值当成必填项时会要求显式的 true/false
        const el = h(
          'select',
          {},
          h('option', { value: '', text: '未填写' }),
          h('option', { value: 'true', text: '是' }),
          h('option', { value: 'false', text: '否' }),
        )
        el.value = value === true ? 'true' : value === false ? 'false' : ''
        control = el
        read = () => (el.value === '' ? undefined : el.value === 'true')
        break
      }
      case 'select': {
        const el = h(
          'select',
          {},
          h('option', { value: '', text: '未填写' }),
          (tpl.options ?? []).map((option) =>
            h('option', { value: optionValue(option), text: optionLabel(option) }),
          ),
        )
        el.value = value === undefined || value === null ? '' : String(value)
        control = el
        read = () => el.value || undefined
        break
      }
      case 'multi_select': {
        const selected = toArray(value)
        const entries = (tpl.options ?? []).map((option) => {
          const optionValueText = optionValue(option)
          const box = h('input', { type: 'checkbox', checked: selected.includes(optionValueText) })
          return {
            value: optionValueText,
            box,
            node: h('label', { class: 'checkbox-item' }, box, optionLabel(option)),
          }
        })
        control = h('div', { class: 'checkbox-group' }, entries.map((entry) => entry.node))
        read = () => {
          const picked = entries.filter((entry) => entry.box.checked).map((entry) => entry.value)
          return picked.length > 0 ? picked : undefined
        }
        break
      }
      default: {
        const el = h('input', { type: 'text', value: str(value) })
        control = el
        read = () => el.value.trim() || undefined
        break
      }
    }

    attrFields.push({ tpl, read })
    return h(
      'div',
      { class: 'field' },
      h(
        'label',
        { class: 'field-label' },
        tpl.unit ? `${label}（${tpl.unit}）` : label,
        tpl.is_required ? h('span', { class: 'required', text: '*' }) : null,
      ),
      control,
      tpl.inherited ? h('div', { class: 'field-hint', text: `继承自「${tpl.category_name ?? '上级分类'}」` }) : null,
    )
  }

  function collectAttrs(): Record<string, unknown> | undefined {
    if (templates.length === 0) return undefined
    const result: Record<string, unknown> = {}
    for (const field of attrFields) {
      const code = field.tpl.code
      if (!code) continue
      const value = field.read()
      if (value === undefined) {
        if (field.tpl.is_required) throw new ApiError(`请填写「${field.tpl.label ?? code}」`)
        continue // 没填的可选属性不写键，避免库里出现一堆空值
      }
      result[code] = value
    }
    return result
  }

  // ══════════════════ 图片上传 ══════════════════

  function renderImages(): void {
    // 显式标成 HTMLElement[]：map 推出的是 HTMLDivElement[]，再 push 删除按钮会不兼容
    const cells: HTMLElement[] = images.map((url, index) =>
      h(
        'div',
        { class: 'img-cell' },
        h('img', { src: url, alt: '物品图片' }),
        h('button', {
          class: 'img-del',
          type: 'button',
          text: '✕',
          onclick: () => {
            images.splice(index, 1)
            renderImages()
          },
        }),
      ),
    )
    if (images.length < MAX_IMAGES) {
      cells.push(h('button', { class: 'img-add', type: 'button', text: '+', onclick: () => fileInput.click() }))
    }
    imgGrid.replaceChildren(...cells)
  }

  async function uploadFile(): Promise<void> {
    const file = fileInput.files?.[0]
    // 立刻清空，否则连续选同一个文件不会再触发 change
    fileInput.value = ''
    if (!file) return
    try {
      const result = await api.uploadImage(file)
      if (!result.file_url) throw new ApiError('上传失败：响应里没有文件地址')
      images.push(result.file_url)
      renderImages()
      toast('图片已上传', 'success')
    } catch (error) {
      toast(error instanceof ApiError ? error.message : '图片上传失败', 'error')
    }
  }

  // ══════════════════ 提交 ══════════════════

  async function submit(): Promise<void> {
    const name = nameInput.value.trim()
    if (!name) {
      toast('请填写物品名称', 'error')
      nameInput.focus()
      return
    }

    let attrs: Record<string, unknown> | undefined
    try {
      attrs = collectAttrs()
    } catch (error) {
      toast(error instanceof ApiError ? error.message : '扩展属性填写有误', 'error')
      return
    }

    // 分类树没拉到时不要把已归类的物品改成「未归类」
    const picked = categorySelect.value ? Number(categorySelect.value) : null
    const categoryId = categories.length === 0 && item ? item.category_id : picked

    const payload: ItemPayload = {
      name,
      category_id: categoryId,
      barcode: textOrNull(barcodeInput.value),
      brand: textOrNull(brandInput.value),
      spec: textOrNull(specInput.value),
      unit: textOrNull(unitInput.value),
      location: textOrNull(locationInput.value),
      purchase_channel: textOrNull(channelInput.value),
      ref_price: priceInput.value.trim() ? Number(priceInput.value) : null,
      images: [...images],
      visibility: (visibilitySelect.value || 'family') as ItemVisibility,
      remark: textOrNull(remarkInput.value),
    }
    if (attrs !== undefined) payload.attrs = attrs

    if (!editing && batchToggle.checked) {
      const batch = buildBatch()
      if (!batch) return
      payload.batches = [batch]
    }

    submitButton.disabled = true
    submitButton.textContent = '保存中…'
    try {
      const saved = editing ? await api.itemUpdate(editId as number, payload) : await api.itemCreate(payload)
      toast(editing ? '修改已保存' : '已保存并入库', 'success')
      if (saved.id !== null && saved.id !== undefined) nav.detail(saved.id)
      else nav.list()
    } catch (error) {
      toast(error instanceof ApiError ? error.message : '保存失败', 'error')
      submitButton.disabled = false
      submitButton.textContent = editing ? '保存修改' : '保存并入库'
    }
  }

  function buildBatch(): BatchPayload | null {
    const quantity = batchQty.value.trim()
    if (!quantity || Number(quantity) <= 0) {
      toast('请填写首批进货数量（或取消「同时录入首批批次」）', 'error')
      batchQty.focus()
      return null
    }
    return {
      quantity: Number(quantity),
      unit_price: batchPrice.value.trim() ? Number(batchPrice.value) : null,
      production_date: batchProduction.value || null,
      expiry_date: batchExpiry.value || null,
      channel: textOrNull(batchChannel.value),
    }
  }

  // ══════════════════ 页面 ══════════════════

  function goBack(): void {
    if (editId !== null) nav.detail(editId)
    else nav.list()
  }

  function batchSection(): HTMLElement {
    return h(
      'div',
      { class: 'card' },
      h(
        'div',
        { class: 'form-section-title', style: { marginTop: '0' } },
        h('label', { class: 'checkbox-item' }, batchToggle, '同时录入首批批次'),
      ),
      batchBody,
    )
  }

  function page(): HTMLElement {
    return h(
      'div',
      { class: 'page' },
      h(
        'div',
        { class: 'navbar' },
        h('button', { class: 'btn btn-ghost', text: '返回', onclick: () => goBack() }),
        h('div', { class: 'navbar-title', text: editing ? '编辑物品' : '新增物品' }),
      ),
      h(
        'div',
        { class: 'content no-fab' },
        h(
          'div',
          { class: 'card' },
          field('物品名称', nameInput, undefined, true),
          field('分类', categorySelect, '扩展属性按分类的模板出现'),
          h('div', { class: 'field-row' }, field('品牌', brandInput), field('规格', specInput)),
          h('div', { class: 'field-row' }, field('单位', unitInput), field('存放位置', locationInput)),
          h('div', { class: 'field-row' }, field('参考单价', priceInput), field('购买渠道', channelInput)),
          field('条码', barcodeInput),
          field('可见范围', visibilitySelect, '「仅本人可见」的物品其他家庭成员看不到'),
          h('div', { class: 'form-section-title', text: '图片' }),
          imgGrid,
          fileInput,
        ),
        editing ? null : batchSection(),
        h(
          'div',
          { class: 'card' },
          h('div', { class: 'form-section-title', style: { marginTop: '0' }, text: '扩展属性' }),
          attrBox,
        ),
        h('div', { class: 'card' }, h('div', { class: 'form-section-title', style: { marginTop: '0' }, text: '备注' }), remarkInput),
        h(
          'div',
          { class: 'form-actions' },
          h('button', { class: 'btn', text: '取消', onclick: () => goBack() }),
          submitButton,
        ),
      ),
      fileInput,
    )
  }

  function field(label: string, control: HTMLElement, hint?: string, required = false): HTMLElement {
    return h(
      'div',
      { class: 'field' },
      h(
        'label',
        { class: 'field-label' },
        label,
        required ? h('span', { class: 'required', text: '*' }) : null,
      ),
      control,
      hint ? h('div', { class: 'field-hint', text: hint }) : null,
    )
  }
}

// ══════════════════ 工具 ══════════════════

/** 一个动态属性控件：tpl 是模板，read 把控件当前值转成后端要的类型 */
interface AttrField {
  tpl: AttrTemplate
  read: () => unknown
}

function str(value: unknown): string {
  if (value === null || value === undefined) return ''
  return String(value)
}

/** multi_select 的值可能是数组，也可能后台配成逗号分隔的默认值 */
function toArray(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((entry) => String(entry))
  if (typeof value === 'string' && value) return value.split(',').map((entry) => entry.trim())
  return []
}

/** 可空文本：空串统一成 null，别让库里同时存在 '' 和 NULL 两种空 */
function textOrNull(value: string): string | null {
  const text = value.trim()
  return text || null
}
