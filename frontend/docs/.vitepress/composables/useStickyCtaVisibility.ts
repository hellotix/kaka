/**
 * StickyCta 可见性控制器
 *
 * 标准的"fixed 元素不与其他 UI 元素重叠"模式:
 *   1. 监听 VitePress 侧边栏抽屉状态(.VPSidebar.open) — 打开时隐藏
 *   2. 监听 FooterNav 是否进入视口 — 接近页底时隐藏
 *   3. 移动端 < 768px 默认收起(由 CSS 处理)
 *   4. 用户主动 dismiss(24h localStorage TTL)— 同原逻辑
 *
 * 使用 MutationObserver 监听 .VPSidebar.open class 变化
 * 使用 IntersectionObserver 监听 .footer-nav 元素
 */

import { onMounted, onUnmounted, ref, watch } from 'vue'

interface StickyCtaVisibilityOptions {
  /** 触发显示的 section id */
  triggerSelector: string
  /** FooterNav 选择器(用于 IntersectionObserver) */
  footerSelector?: string
  /** 移动端断点(px),默认 768 */
  mobileBreakpoint?: number
}

export function useStickyCtaVisibility(options: StickyCtaVisibilityOptions) {
  const {
    triggerSelector,
    footerSelector = '.footer-nav',
    mobileBreakpoint = 768,
  } = options

  const visible = ref(false)
  const dismissed = ref(false)
  const sidebarOpen = ref(false)
  const nearBottom = ref(false)
  const isMobile = ref(false)
  /** 移动端不隐藏,而是切换为 pill 模式(更紧凑) */
  const compact = ref(false)

  let triggerObserver: IntersectionObserver | null = null
  let footerObserver: IntersectionObserver | null = null
  let sidebarObserver: MutationObserver | null = null
  let mediaQuery: MediaQueryList | null = null
  /** media query listener 引用 — 必须在 onUnmounted 引用同一引用,否则 removeEventListener 失效 */
  let mediaChangeHandler: ((e: MediaQueryListEvent) => void) | null = null

  const STORAGE_KEY = 'fastapiadmin-sticky-cta-dismissed'
  const TTL_MS = 24 * 60 * 60 * 1000

  /** 检查 24h TTL 是否过期 */
  const isDismissed = (): boolean => {
    if (typeof localStorage === 'undefined') return false
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return false
      const ts = Number(raw)
      if (!Number.isFinite(ts)) return false
      return Date.now() - ts < TTL_MS
    } catch {
      return false
    }
  }

  /** 重新计算是否应该显示(综合所有条件) */
  const updateVisibility = () => {
    if (dismissed.value || sidebarOpen.value || nearBottom.value) {
      visible.value = false
      return
    }
    // 移动端不阻止显示(改用 pill 模式而不是隐藏,避免转化漏斗断裂)
    compact.value = isMobile.value
    // 其他条件由 trigger observer 控制
  }

  /**
   * 通过 body class 让 CSS 知道 sticky 是否激活,从而:
   *   - VPContent 加 padding-bottom 避免 doc pager/FooterNav 被遮挡
   *   - 移动端彻底隐藏(若 sticky 显示,fixed 元素会盖住底栏菜单)
   */
  const syncBodyClass = (active: boolean) => {
    if (typeof document === 'undefined') return
    document.body.classList.toggle('has-sticky-cta', active)
  }

  // 监听 visible 变化,同步 body class
  // (用 watch 比 :class 更精确,因为 visible 会被多处修改)
  watch(visible, (val) => syncBodyClass(val), { immediate: false })

  /** 用户主动关闭(写入 TTL) */
  const dismiss = () => {
    dismissed.value = true
    visible.value = false
    if (typeof localStorage !== 'undefined') {
      try {
        localStorage.setItem(STORAGE_KEY, String(Date.now()))
      } catch {
        // localStorage 不可用
      }
    }
  }

  onMounted(() => {
    if (typeof window === 'undefined') return

    // 1. localStorage TTL 检查
    if (isDismissed()) {
      dismissed.value = true
      return
    }

    // 2. 移动端检测
    mediaQuery = window.matchMedia(`(max-width: ${mobileBreakpoint}px)`)
    isMobile.value = mediaQuery.matches
    mediaChangeHandler = (e: MediaQueryListEvent) => {
      isMobile.value = e.matches
      updateVisibility()
    }
    mediaQuery.addEventListener('change', mediaChangeHandler)

    // 3. Trigger section 监听(滚过 end-to-end 之后才显示)
    if (typeof IntersectionObserver === 'undefined') return
    const trigger = document.querySelector(triggerSelector)
    if (trigger) {
      triggerObserver = new IntersectionObserver(
        (entries) => {
          const entry = entries[0]
          if (!entry) return
          if (!entry.isIntersecting && entry.boundingClientRect.top < 0) {
            // 滚过 trigger section → 显示(其他条件可能否决)
            updateVisibility()
            if (!dismissed.value && !sidebarOpen.value && !nearBottom.value) {
              visible.value = true
            }
          } else if (entry.isIntersecting && entry.intersectionRatio > 0.5) {
            // 回到 trigger section → 隐藏
            visible.value = false
          }
        },
        { threshold: [0, 0.3, 0.5, 0.8] }
      )
      triggerObserver.observe(trigger)
    }

    // 4. FooterNav 监听(滚到页底时隐藏,避免和 footer 重叠)
    const footer = document.querySelector(footerSelector)
    if (footer) {
      footerObserver = new IntersectionObserver(
        (entries) => {
          const entry = entries[0]
          if (!entry) return
          // footer 进入视口 → 隐藏
          nearBottom.value = entry.isIntersecting
          if (entry.isIntersecting) {
            visible.value = false
          } else {
            updateVisibility()
          }
        },
        { threshold: 0, rootMargin: '0px 0px -100px 0px' }
      )
      footerObserver.observe(footer)
    }

    // 5. VitePress 侧边栏抽屉监听(.VPSidebar.open class 变化)
    const sidebar = document.querySelector('.VPSidebar')
    if (sidebar) {
      sidebarObserver = new MutationObserver(() => {
        const isOpen = sidebar.classList.contains('open')
        if (isOpen !== sidebarOpen.value) {
          sidebarOpen.value = isOpen
          updateVisibility()
        }
      })
      sidebarObserver.observe(sidebar, {
        attributes: true,
        attributeFilter: ['class'],
      })
    }
  })

  onUnmounted(() => {
    if (triggerObserver) triggerObserver.disconnect()
    if (footerObserver) footerObserver.disconnect()
    if (sidebarObserver) sidebarObserver.disconnect()
    if (mediaQuery && mediaChangeHandler) {
      // 必须用 addEventListener 时保存的同一引用,否则 listener 不会清理
      mediaQuery.removeEventListener('change', mediaChangeHandler)
    }
    mediaChangeHandler = null
    syncBodyClass(false)
  })

  return {
    visible,
    dismissed,
    sidebarOpen,
    nearBottom,
    isMobile,
    compact,
    dismiss,
  }
}
