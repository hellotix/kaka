/**
 * 物品列表（首页）—— 搜索 / 分类筛选 / 翻页 / 家庭切换 / 扫码。
 *
 * 渲染策略：
 * - 输入框、分类条、列表区这三个节点只创建一次，搜索与翻页只重刷列表区，
 *   这样输入过程中不会因为整页重渲染而丢焦点（手机上键盘会跟着收起）。
 * - 切换家庭要清空全部筛选状态，才走一次整页重渲染。
 *
 * 家庭上下文：列表/详情/提交这类接口都要求 X-Family-Id（api.ts 里标了 family: true），
 * 没有家庭时本页直接降级成「创建/加入家庭」引导页 —— 否则一进首页就是 400。
 */

import { ApiError, api } from '../api'
import { nav } from '../router'
import { refreshFamilies } from '../session'
import { store } from '../store'
import type { CategoryNode, FamilyBrief, Item } from '../types'
import type { SheetItem } from '../ui'
import {
  VISIBILITY_TEXT,
  emptyNode,
  expiryBadge,
  fmtQty,
  h,
  loadingNode,
  mount,
  openFormModal,
  openSheet,
  toast,
} from '../ui'

/** 每页条数：后端 page_size 上限 100，20 差不多是手机上一屏半的量 */
const PAGE_SIZE = 20
/** 搜索防抖间隔（毫秒）：边打字边发请求既费流量，列表也会闪 */
const SEARCH_DELAY = 350

const FAMILY_ROLE_TEXT: Record<string, string> = {
  owner: '户主',
  admin: '管理员',
  member: '成员',
  viewer: '只读',
}

export function renderList(): void {
  // ── 列表状态（切换家庭时整体重置） ──
  let keyword = ''
  let categoryId: number | null = null
  let pageNo = 1
  let items: Item[] = []
  let total = 0
  let hasNext = false
  let loading = false
  let appending = false
  let categories: CategoryNode[] = []
  let searchTimer: number | null = null
  /**
   * 请求序号：筛选条件变化很快时，先发的请求可能后回来。
   * 每次发起请求都自增，回调里对不上号的结果直接丢弃，避免旧数据覆盖新列表。
   */
  let seq = 0

  // ── 只创建一次的骨架节点 ──
  const searchInput = h('input', {
    type: 'search',
    placeholder: '搜索物品名称',
    oninput: () => {
      if (searchTimer !== null) window.clearTimeout(searchTimer)
      searchTimer = window.setTimeout(() => {
        searchTimer = null
        keyword = searchInput.value.trim()
        void load(false)
      }, SEARCH_DELAY)
    },
  })
  const chipsEl = h('div', { class: 'chips' })
  const listArea = h('div')

  void bootstrap()

  // ══════════════════ 启动与页面骨架 ══════════════════

  async function bootstrap(): Promise<void> {
    try {
      await refreshFamilies()
    } catch (error) {
      // 拉不到家庭列表时本地缓存还能用就先顶着；缓存也是空才展示错误页
      if (store.families.length === 0) {
        renderErrorPage(error instanceof ApiError ? error.message : '家庭列表加载失败')
        return
      }
      toast('家庭列表刷新失败，正在展示本地缓存', 'error')
    }
    renderPage()
  }

  function renderPage(): void {
    const family = currentFamily()
    if (!family) {
      renderNoFamily()
      return
    }
    mount(
      h(
        'div',
        { class: 'page' },
        navbar(),
        h(
          'div',
          { class: 'content' },
          h(
            'div',
            { class: 'search-bar' },
            searchInput,
            h('button', { class: 'btn', text: '扫码', onclick: () => void scanFlow() }),
          ),
          chipsEl,
          listArea,
        ),
        h('button', { class: 'fab', text: '+', onclick: () => nav.form() }),
      ),
    )
    renderChips()
    void loadCategories()
    void load(false)
  }

  /** 一个家庭都没有时的引导页（创建 / 邀请码加入） */
  function renderNoFamily(): void {
    mount(
      h(
        'div',
        { class: 'page' },
        navbar(),
        h(
          'div',
          { class: 'content no-fab' },
          h(
            'div',
            { class: 'card' },
            h('div', { class: 'item-name', text: '还没有加入任何家庭' }),
            h('div', {
              style: { marginTop: '6px', fontSize: '13px', color: 'var(--text-2)', lineHeight: '1.7' },
              text: '物品数据按家庭隔离，先创建一个家庭，或用家人分享的邀请码加入。',
            }),
            h(
              'div',
              { class: 'form-actions' },
              h('button', { class: 'btn btn-primary', text: '创建家庭', onclick: () => void createFamilyFlow() }),
              h('button', { class: 'btn', text: '邀请码加入', onclick: () => void joinFamilyFlow() }),
            ),
          ),
        ),
      ),
    )
  }

  function renderErrorPage(message: string): void {
    mount(
      h(
        'div',
        { class: 'page' },
        navbar(),
        h(
          'div',
          { class: 'content no-fab' },
          h(
            'div',
            { class: 'empty' },
            h('div', { class: 'icon', text: '!' }),
            h('div', { text: message }),
            h('button', {
              class: 'btn',
              style: { marginTop: '12px' },
              text: '重试',
              onclick: () => {
                mount(loadingNode())
                void bootstrap()
              },
            }),
          ),
        ),
      ),
    )
  }

  function navbar(): HTMLElement {
    const family = currentFamily()
    const user = store.user
    const sub = [
      user?.nickname ?? user?.mobile ?? '已登录',
      family ? `${family.member_count ?? 1} 位成员` : null,
    ]
      .filter((part): part is string => Boolean(part))
      .join(' · ')
    return h(
      'div',
      { class: 'navbar' },
      h(
        'div',
        { class: 'navbar-title' },
        family?.name ?? '咔咔家庭物资',
        h('span', { class: 'sub', text: sub }),
      ),
      h(
        'div',
        { class: 'navbar-actions' },
        h('button', { class: 'btn btn-sm', text: '家庭', onclick: () => familySheet() }),
        h('button', { class: 'btn btn-sm icon-btn', text: '我', onclick: () => nav.profile() }),
      ),
    )
  }

  function currentFamily(): FamilyBrief | null {
    return store.families.find((family) => family.id === store.familyId) ?? null
  }

  // ══════════════════ 家庭切换（账号相关操作在个人中心） ══════════════════

  function familySheet(): void {
    const sheetItems: SheetItem[] = []
    for (const family of store.families) {
      const id = family.id
      if (id === null) continue
      const role = family.my_role ? (FAMILY_ROLE_TEXT[family.my_role] ?? family.my_role) : ''
      sheetItems.push({
        label: `${family.name ?? '未命名家庭'}${role ? `（${role}）` : ''}`,
        active: id === store.familyId,
        onClick: () => void switchFamily(id),
      })
    }
    sheetItems.push({ label: '创建新家庭', icon: '+', onClick: () => void createFamilyFlow() })
    sheetItems.push({ label: '用邀请码加入家庭', icon: '>', onClick: () => void joinFamilyFlow() })
    openSheet('选择家庭', sheetItems)
  }

  async function switchFamily(id: number): Promise<void> {
    if (id === store.familyId) return
    store.setFamilyId(id)
    resetState()
    renderPage()
  }

  async function createFamilyFlow(): Promise<void> {
    openFormModal(
      '创建家庭',
      [{ key: 'name', label: '家庭名称', placeholder: '例如：幸福之家', required: true }],
      async (values) => {
        const family = await api.createFamily(values.name)
        await refreshFamilies()
        if (family.id !== null) store.setFamilyId(family.id)
        toast(`家庭「${family.name ?? ''}」已创建`, 'success')
        resetState()
        renderPage()
      },
    )
  }

  async function joinFamilyFlow(): Promise<void> {
    openFormModal(
      '加入家庭',
      [{ key: 'invite_code', label: '邀请码', placeholder: '请输入家人分享的邀请码', required: true }],
      async (values) => {
        // 后端是「加入即生效」，不需要户主二次确认
        const family = await api.joinFamily(values.invite_code)
        await refreshFamilies()
        if (family.id !== null) store.setFamilyId(family.id)
        toast(`已加入「${family.name ?? ''}」`, 'success')
        resetState()
        renderPage()
      },
    )
  }

  // ══════════════════ 扫码 ══════════════════

  /** 扫码查重：命中已有物品直接进详情（可对照后补批次），未命中带着条码去新建 */
  async function scanFlow(): Promise<void> {
    openFormModal(
      '扫码 / 条码查询',
      [{ key: 'barcode', label: '商品条码', placeholder: '扫码枪输入或手动填写', required: true }],
      async (values) => {
        const result = await api.itemScan(values.barcode)
        if (result.matched && result.item?.id !== null && result.item?.id !== undefined) {
          toast('已找到同条码物品', 'success')
          nav.detail(result.item.id)
          return
        }
        toast('未找到该条码，去新建物品', 'info')
        nav.form(undefined, { barcode: result.barcode || values.barcode })
      },
    )
  }

  // ══════════════════ 分类筛选 ══════════════════

  async function loadCategories(): Promise<void> {
    try {
      const tree = await api.categoryTree()
      categories = flatten(tree)
    } catch {
      // 分类拿不到不影响浏览：只剩「全部」一个筛选项
      categories = []
    }
    renderChips()
  }

  /** 拍平分类树（只取前两级，chips 一行放不下三级） */
  function flatten(nodes: CategoryNode[], level = 1): CategoryNode[] {
    const result: CategoryNode[] = []
    if (level > 2) return result
    for (const node of nodes) {
      result.push(node)
      if (node.children.length > 0) result.push(...flatten(node.children, level + 1))
    }
    return result
  }

  function renderChips(): void {
    const chip = (label: string, id: number | null): HTMLElement =>
      h('div', {
        class: `chip${categoryId === id ? ' active' : ''}`,
        text: label,
        onclick: () => {
          if (categoryId === id) return
          categoryId = id
          renderChips()
          void load(false)
        },
      })
    chipsEl.replaceChildren(
      chip('全部', null),
      ...categories.map((node) => chip(node.name ?? '未命名分类', node.id)),
    )
  }

  // ══════════════════ 列表加载 ══════════════════

  /** 清空筛选与列表（切换家庭、家庭信息变更后调用） */
  function resetState(): void {
    keyword = ''
    categoryId = null
    pageNo = 1
    items = []
    total = 0
    hasNext = false
    appending = false
    seq += 1
    searchInput.value = ''
    if (searchTimer !== null) {
      window.clearTimeout(searchTimer)
      searchTimer = null
    }
  }

  /** more=true 追加下一页；false 从头加载（首次进入、换关键词、换分类） */
  async function load(more: boolean): Promise<void> {
    if (more && loading) return
    loading = true
    const current = ++seq
    const target = more ? pageNo : 1

    if (more) {
      appending = true
      renderItems()
    } else {
      listArea.replaceChildren(loadingNode())
    }

    let errorMessage: string | null = null
    try {
      const result = await api.itemList({
        page_no: target,
        page_size: PAGE_SIZE,
        name: keyword || undefined,
        category_id: categoryId ?? undefined,
      })
      // 本次请求已过期（用户又改了筛选条件）：结果直接丢弃，状态留给最新那次请求维护
      if (current !== seq) return
      items = more ? [...items, ...result.items] : result.items
      total = result.total
      hasNext = result.has_next
      pageNo = target + 1
    } catch (error) {
      if (current !== seq) return
      errorMessage = error instanceof ApiError ? error.message : '列表加载失败'
    }

    // 走到这里说明本次请求仍是最新的一次，可以安全复位状态与重绘
    loading = false
    appending = false
    if (errorMessage !== null) {
      toast(errorMessage, 'error')
      if (more) renderItems()
      else listArea.replaceChildren(errorBox(errorMessage))
      return
    }
    renderItems()
  }

  function errorBox(message: string): HTMLElement {
    return h(
      'div',
      { class: 'empty' },
      h('div', { class: 'icon', text: '!' }),
      h('div', { text: message }),
      h('button', {
        class: 'btn',
        style: { marginTop: '12px' },
        text: '重试',
        onclick: () => void load(false),
      }),
    )
  }

  function renderItems(): void {
    const nodes: HTMLElement[] = []
    const summary = summaryText()
    if (summary) nodes.push(h('div', { class: 'list-summary', text: summary }))

    if (items.length === 0) {
      const filtered = Boolean(keyword) || categoryId !== null
      nodes.push(emptyNode('物', filtered ? '没有符合条件的物品' : '还没有物品，点右下角「+」录入第一件'))
    } else {
      for (const item of items) nodes.push(itemCard(item))
      if (appending) {
        nodes.push(h('div', { class: 'load-more', text: '加载中…' }))
      } else if (hasNext) {
        nodes.push(h('div', { class: 'load-more', text: '加载更多', onclick: () => void load(true) }))
      }
    }
    listArea.replaceChildren(...nodes)
  }

  function summaryText(): string {
    if (items.length === 0) return ''
    const parts = [`共 ${total} 条`]
    if (keyword) parts.push(`搜索「${keyword}」`)
    const category = categories.find((node) => node.id === categoryId)
    if (category?.name) parts.push(category.name)
    return parts.join(' · ')
  }

  function itemCard(item: Item): HTMLElement {
    const thumb = h('div', { class: 'item-thumb' })
    const image = item.images[0]
    if (image) {
      thumb.appendChild(h('img', { src: image, alt: item.name ?? '物品图片' }))
    } else {
      // 没有图片时用一个字占位，比灰块更像个列表项
      thumb.textContent = '物'
    }

    const subtitle = [item.category_name, item.brand, item.spec]
      .filter((part): part is string => Boolean(part))
      .join(' · ')

    return h(
      'div',
      { class: 'card item-card', onclick: () => nav.detail(item.id ?? 0) },
      thumb,
      h(
        'div',
        { class: 'item-main' },
        h('div', { class: 'item-name', text: item.name ?? '未命名物品' }),
        h('div', { class: 'item-sub', text: subtitle || '暂无品牌 / 规格' }),
        h(
          'div',
          { class: 'item-meta' },
          expiryBadge(item.nearest_expiry_date),
          item.location ? h('span', { class: 'tag tag-blue', text: item.location }) : null,
          item.visibility && item.visibility !== 'family'
            ? h('span', { class: 'tag', text: VISIBILITY_TEXT[item.visibility] ?? item.visibility })
            : null,
        ),
      ),
      h(
        'div',
        { class: 'item-qty' },
        h('b', { text: fmtQty(item.total_remain_qty) }),
        h('span', { text: `${item.unit ?? '件'} · ${item.batch_count} 批` }),
      ),
    )
  }
}
