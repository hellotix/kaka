/**
 * 主题运行时页面级增强(与主题骨架解耦,index.ts 只保留声明式结构):
 * - guide 页面启用 medium-zoom 图片缩放(首页用不上,避免 ~60KB 浪费)
 * - 移除 VitePress 默认注入的 Inter Web 字体 preload(我们用 system-ui 优先)
 */
import { onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute } from 'vitepress'

/** 仅在 guide/ 路径下启用图片缩放(首页用不上,避免 ~60KB 浪费) */
function isGuidePath(path: string): boolean {
  return path.includes('/guide/') || path.startsWith('/en/guide/')
}

/** 移除 VitePress 默认注入的 Inter Web 字体 preload(我们用 system-ui 优先) */
function removeInterPreloads(): void {
  if (typeof document === 'undefined') return
  document.querySelectorAll('link[rel="preload"][as="font"][href*="/inter-"]').forEach((el) => {
    el.remove()
  })
  // 移除字体 @font-face 规则(已经不用)
  document.querySelectorAll('style').forEach((styleEl) => {
    try {
      if (styleEl.textContent && styleEl.textContent.includes('@font-face') && styleEl.textContent.includes('Inter')) {
        styleEl.remove()
      }
    } catch {
      // ignore CORS
    }
  })
}

/** 挂载时初始化 guide 图片缩放与字体清理 */
export function setupPageEnhance(): void {
  const route = useRoute()
  let zoom: { detach: () => void } | null = null
  let zoomLoading = false

  const initZoom = async () => {
    if (!isGuidePath(route.path)) {
      // 非 guide 页面,清理并跳过
      if (zoom) {
        zoom.detach()
        zoom = null
      }
      return
    }
    if (zoomLoading) return
    zoomLoading = true
    try {
      // 动态 import,首页不下载 medium-zoom ~60KB
      const { default: mediumZoom } = await import('medium-zoom')
      if (!isGuidePath(route.path)) return // 用户可能已经切走
      if (zoom) zoom.detach()
      await nextTick()
      zoom = mediumZoom('.vp-doc img:not(.logo):not([alt*="badge"]):not([alt*="Badge"]):not([alt*="Stars"]):not([alt*="License"]):not([alt*="Python"]):not([alt*="NodeJS"]):not([alt*="MySQL"]):not([alt*="Redis"])', {
        background: 'rgba(0, 0, 0, 0.8)',
        margin: 24,
        scrollOffset: 0,
      })
    } finally {
      zoomLoading = false
    }
  }

  onMounted(() => {
    // 异步执行,让首屏渲染先完成
    requestIdleCallback?.(() => initZoom()) ?? setTimeout(() => initZoom(), 0)
    // 移除 Inter 字体 preload(节省 68KB)
    removeInterPreloads()
    // 路由变化时也尝试移除(防止某些路径动态插入)
    const observer = new MutationObserver(() => removeInterPreloads())
    observer.observe(document.head, { childList: true, subtree: true })
    // 路由切换时重新初始化
    watch(() => route.path, () => {
      initZoom()
      removeInterPreloads()
    })
    // 卸载时释放观察器(防泄漏)
    onUnmounted(() => observer.disconnect())
  })
}
