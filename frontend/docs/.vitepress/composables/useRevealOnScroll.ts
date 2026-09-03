import { onMounted, onUnmounted, type Ref } from 'vue'

/**
 * 滚动渐入 — 目标元素进入视口后添加 `.animate-in` 类
 *
 * 设计原则:
 *  - 职责单一:JS 只负责"何时触发"(IntersectionObserver),
 *    delay 与过渡完全交给 CSS(`transition-delay: var(--reveal-delay, 0s)`),
 *    避免在 JS 里管理 setTimeout / data-delay 解析
 *  - 组件卸载(SPA 路由切换)时自动 disconnect,无监听器泄漏
 *
 * 用法:
 * ```html
 * <section ref="el" class="animate-section" style="--reveal-delay: 0.1s">...</section>
 * ```
 * ```ts
 * const el = ref<HTMLElement | null>(null)
 * useRevealOnScroll(el)
 * ```
 */
export function useRevealOnScroll(target: Ref<HTMLElement | null>) {
  let observer: IntersectionObserver | null = null

  onMounted(() => {
    if (!('IntersectionObserver' in window)) return
    const el = target.value
    if (!el) return

    observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return
          entry.target.classList.add('animate-in')
          observer?.unobserve(entry.target)
        })
      },
      { threshold: 0.08, rootMargin: '0px 0px -60px 0px' }
    )
    observer.observe(el)
  })

  onUnmounted(() => {
    observer?.disconnect()
    observer = null
  })
}
