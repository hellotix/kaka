<template>
  <Transition name="sticky-cta">
    <div
      v-if="visible"
      ref="rootEl"
      class="sticky-cta"
      :class="{ 'sticky-cta--compact': compact }"
      role="region"
      :aria-label="t.label"
    >
      <div class="sticky-cta-inner">
        <div class="sticky-cta-text">
          <span v-if="!compact" class="sticky-cta-eyebrow">{{ t.eyebrow }}</span>
          <span class="sticky-cta-title">{{ compact ? t.compactTitle : t.title }}</span>
        </div>
        <div class="sticky-cta-actions">
          <a :href="primaryHref" class="sticky-cta-btn sticky-cta-btn--primary">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
            {{ t.primary }}
          </a>
          <a v-if="!compact" :href="secondaryHref" target="_blank" rel="noreferrer" class="sticky-cta-btn sticky-cta-btn--ghost">
            {{ t.secondary }}
          </a>
        </div>
        <button
          class="sticky-cta-close"
          @click="dismiss"
          :aria-label="t.dismiss"
          type="button"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick, onUnmounted } from 'vue'
import { useData } from 'vitepress'
import { useStickyCtaVisibility } from '../composables/useStickyCtaVisibility'

interface Props {
  /** 触发显示的 section id(滚过这个 section 底部时显示) */
  triggerSelector?: string
}

const props = withDefaults(defineProps<Props>(), {
  triggerSelector: '#end-to-end',
})

const { lang } = useData()
const isEn = computed(() => lang.value === 'en')

const t = computed(() => isEn.value
  ? {
      label: 'Sticky call to action',
      eyebrow: '👀  Still reading?',
      title: 'Clone the repo and try it locally',
      compactTitle: 'Try it locally',
      primary: 'Quick Start',
      secondary: 'Live Demo',
      dismiss: 'Dismiss',
    }
  : {
      label: '操作提示',
      eyebrow: '👀  看到这了',
      title: '把项目 clone 下来,本地跑跑看',
      compactTitle: '本地跑跑看 →',
      primary: '立即开始',
      secondary: '在线预览',
      dismiss: '关闭',
    }
)

const primaryHref = computed(() => isEn.value ? '/en/guide/start' : '/guide/start')
const secondaryHref = 'https://service.fastapiadmin.com/web'

/**
 * 标准 4-条件互斥显示控制器:
 *   1. trigger section 滚过 → 显示
 *   2. 侧边栏抽屉打开 → 隐藏(避免和左 nav 重叠)
 *   3. FooterNav 进入视口 → 隐藏(避免和页底重叠)
 *   4. 移动端 < 768px → 隐藏(避免和底栏手势冲突)
 *   5. 用户主动 dismiss → 24h 内不再显示
 */
const { visible, compact, dismiss } = useStickyCtaVisibility({
  triggerSelector: props.triggerSelector,
  footerSelector: '.footer-nav',
  mobileBreakpoint: 768,
})

/**
 * ✅ R5 P0-10:Focus trap + 焦点返回
 *   之前只有 focus-visible 焦点环,无 Tab 循环 trap、关闭后焦点不返回
 *   - 显示时:记录之前 activeElement,焦点进 StickyCta 第一项
 *   - Tab/Shift+Tab 在最后/第一项循环,焦点不会跑出 StickyCta
 *   - 关闭时:焦点返回之前的 activeElement
 *   - onUnmounted 清理 keyboard listener 防泄漏
 */
const rootEl = ref<HTMLElement | null>(null)
let returnFocusEl: HTMLElement | null = null

const FOCUSABLE_SELECTOR =
  'a[href]:not([tabindex^="-"]):not([aria-hidden="true"]), button:not([disabled]):not([tabindex^="-"]):not([aria-hidden="true"]), [tabindex]:not([tabindex^="-"]):not([aria-hidden="true"])'

function getFocusableEls(): HTMLElement[] {
  if (!rootEl.value) return []
  return Array.from(rootEl.value.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key !== 'Tab') return
  if (!rootEl.value) return
  const focusables = getFocusableEls()
  if (focusables.length === 0) {
    // 没有可聚焦元素,完全锁住焦点
    e.preventDefault()
    return
  }
  const first = focusables[0]
  const last = focusables[focusables.length - 1]
  const active = document.activeElement as HTMLElement
  // 焦点已离开 StickyCta → 强制拉回第一项
  if (!rootEl.value.contains(active)) {
    e.preventDefault()
    first.focus()
    return
  }
  if (e.shiftKey && active === first) {
    e.preventDefault()
    last.focus()
  } else if (!e.shiftKey && active === last) {
    e.preventDefault()
    first.focus()
  }
}

watch(visible, (val) => {
  if (val) {
    // 记录关闭/跳转前用户所在的焦点(用于恢复)
    returnFocusEl = (document.activeElement as HTMLElement) || null
    nextTick(() => {
      const focusables = getFocusableEls()
      if (focusables.length > 0) {
        focusables[0].focus()
      }
      document.addEventListener('keydown', handleKeydown)
    })
  } else {
    document.removeEventListener('keydown', handleKeydown)
    // 焦点返回关闭前的元素
    if (returnFocusEl && document.contains(returnFocusEl)) {
      returnFocusEl.focus()
    }
    returnFocusEl = null
  }
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
.sticky-cta {
  position: fixed;
  bottom: 1.5rem;
  left: 50%;
  transform: translateX(-50%);
  z-index: var(--vp-z-index-sticky-cta);  /* 70 — 高于 VitePress backdrop (50),低于 lightbox (200) */
  max-width: 640px;
  width: calc(100% - 2rem);
  pointer-events: auto;
}

.sticky-cta-inner {
  position: relative;
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.85rem 1rem 0.85rem 1.5rem;
  background: var(--vp-home-card-bg);
  backdrop-filter: blur(16px) saturate(1.4);
  -webkit-backdrop-filter: blur(16px) saturate(1.4);
  border: 1px solid var(--vp-home-card-border);
  border-radius: var(--vp-radius-md);
  box-shadow:
    0 16px 40px rgba(0, 0, 0, 0.18),
    0 0 30px rgba(99, 102, 241, 0.1);
  transition: background 0.3s, border-color 0.3s, box-shadow 0.3s;
}

.dark .sticky-cta-inner {
  background: rgba(20, 20, 32, 0.92);
  border-color: rgba(139, 92, 246, 0.25);
  box-shadow:
    0 16px 40px rgba(0, 0, 0, 0.4),
    0 0 30px rgba(99, 102, 241, 0.12);
}

.sticky-cta-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.sticky-cta-eyebrow {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--vp-brand-accent-light);
}

.sticky-cta-title {
  font-size: 0.92rem;
  font-weight: 600;
  color: var(--vp-home-text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sticky-cta-actions {
  display: flex;
  gap: 0.5rem;
  flex-shrink: 0;
}

.sticky-cta-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.5rem 1rem;
  font-size: 0.85rem;
  font-weight: 600;
  text-decoration: none;
  border-radius: var(--vp-radius-sm);
  transition: transform 0.2s, background 0.2s, border-color 0.2s, box-shadow 0.2s;
  white-space: nowrap;
}

.sticky-cta-btn:focus-visible {
  outline: 2px solid var(--vp-brand-accent);
  outline-offset: 2px;
}

.sticky-cta-btn svg {
  width: 0.9rem;
  height: 0.9rem;
}

.sticky-cta-btn--primary {
  background: var(--vp-brand-gradient);
  color: var(--vp-button-brand-text);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.35);
}

.sticky-cta-btn--primary:hover {
  transform: translateY(calc(-1 * var(--vp-hover-lift) / 4));  /* -1px 轻提 */
  box-shadow: 0 6px 16px rgba(99, 102, 241, 0.5);
}

.sticky-cta-btn--ghost {
  background: transparent;
  color: var(--vp-home-text-2);
  border: 1px solid var(--vp-home-card-border);
}

.sticky-cta-btn--ghost:hover {
  background: var(--vp-home-card-hover-bg);
  border-color: var(--vp-brand-accent);
  color: var(--vp-home-text-1);
}

.sticky-cta-close {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.2rem;  /* 35.2px,符合 WCAG 2.5.5 24x24 */
  height: 2.2rem;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--vp-home-text-3);
  cursor: pointer;
  border-radius: var(--vp-radius-sm);
  transition: background 0.2s, color 0.2s;
}

.sticky-cta-close:focus-visible {
  outline: 2px solid var(--vp-brand-accent);
  outline-offset: 2px;
}

.sticky-cta-close:hover {
  background: var(--vp-home-card-hover-bg);
  color: var(--vp-home-text-1);
}

.sticky-cta-close svg {
  width: 0.9rem;
  height: 0.9rem;
}

/* Enter/Leave transition */
.sticky-cta-enter-active,
.sticky-cta-leave-active {
  transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.25s;
}

.sticky-cta-enter-from,
.sticky-cta-leave-to {
  transform: translateX(-50%) translateY(20px);
  opacity: 0;
}

/* Mobile — 缩小字号,弱化背景(保留 ghost 按钮的占位) */
@media (max-width: 640px) {
  .sticky-cta {
    bottom: 0.75rem;
    width: calc(100% - 1.5rem);
  }
  .sticky-cta-inner {
    padding: 0.7rem 0.75rem 0.7rem 1rem;
    gap: 0.6rem;
  }
  .sticky-cta-eyebrow {
    display: none;
  }
  .sticky-cta-title {
    font-size: 0.82rem;
  }
  .sticky-cta-btn {
    padding: 0.4rem 0.7rem;
    font-size: 0.78rem;
  }
  .sticky-cta-btn--ghost {
    display: none;
  }
}

/* Mobile compact 模式(pill bar)— 不再隐藏,避免转化漏斗断裂
   触发条件:移动端 + composable 切到 compact = true */
.sticky-cta--compact {
  bottom: 0.75rem;
  width: auto;
  max-width: calc(100% - 1.5rem);
}

.sticky-cta--compact .sticky-cta-inner {
  padding: 0.5rem 0.75rem 0.5rem 1rem;
  gap: 0.5rem;
  border-radius: 9999px;  /* pill 形状 */
}

.sticky-cta--compact .sticky-cta-title {
  font-size: 0.82rem;
  font-weight: 600;
}

.sticky-cta--compact .sticky-cta-btn--primary {
  padding: 0.4rem 0.85rem;
  font-size: 0.78rem;
  border-radius: 9999px;
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  .sticky-cta,
  .sticky-cta-inner,
  .sticky-cta-btn,
  .sticky-cta-close {
    transition: none;
  }
  .sticky-cta-enter-active,
  .sticky-cta-leave-active {
    transition: opacity 0.1s;
  }
  .sticky-cta-enter-from,
  .sticky-cta-leave-to {
    transform: translateX(-50%);
  }
}
</style>
