<template>
  <!-- Teleport 到 body:父级 section 的动画 transform(即使 translateY(0))
       会让其成为 position:fixed 的 containing block,劫持灯箱定位。
       挂到 body 彻底规避,保证 fixed 相对视口、图片垂直居中 -->
  <Teleport to="body">
    <Transition name="lightbox">
      <div
        v-if="visible"
        class="lightbox-overlay"
        role="dialog"
        aria-modal="true"
        :aria-label="alt || '图片预览'"
        @click.self="close"
        @keydown.escape="close"
        tabindex="0"
        ref="overlayRef"
      >
      <!-- Close button -->
      <button class="lightbox-close" @click="close" :aria-label="t.close">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg>
      </button>

      <!-- 关闭通知(WCAG 4.1.3 status messages) -->
      <div class="lightbox-announcer visually-hidden" role="status" aria-live="polite" aria-atomic="true">
        {{ closeAnnouncement }}
      </div>

      <!-- Counter -->
      <div v-if="total > 1" class="lightbox-counter" aria-live="polite" aria-atomic="true">
        {{ currentIndex + 1 }} / {{ total }}
      </div>

      <!-- Previous -->
      <button v-if="total > 1" class="lightbox-nav lightbox-nav--prev" @click="prev" :aria-label="t.prev">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg>
      </button>

      <!-- Image -->
      <div class="lightbox-image-wrap">
        <img
          :src="src"
          :alt="alt"
          class="lightbox-image"
          @load="loaded = true"
          :class="{ 'is-loaded': loaded }"
          :aria-describedby="alt ? captionId : undefined"
        />
        <div v-if="!loaded" class="lightbox-loader" role="status" aria-live="polite">
          <div class="lightbox-spinner" aria-hidden="true"></div>
          <span class="visually-hidden">{{ t.loading }}</span>
        </div>
        <div class="lightbox-caption" v-if="alt" :id="captionId">{{ alt }}</div>
      </div>

      <!-- Next -->
      <button v-if="total > 1" class="lightbox-nav lightbox-nav--next" @click="next" :aria-label="t.next">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg>
      </button>
    </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, computed } from 'vue'
import { useData } from 'vitepress'

const { lang } = useData()
const isEn = computed(() => lang.value === 'en')

const t = computed(() => isEn.value
    ? { close: 'Close', prev: 'Previous', next: 'Next', loading: 'Loading image...', closed: 'Image preview closed.' }
    : { close: '关闭', prev: '上一张', next: '下一张', loading: '图片加载中...', closed: '图片预览已关闭。' }
)

const props = withDefaults(defineProps<{
  visible: boolean
  src: string
  alt?: string
  currentIndex?: number
  total?: number
}>(), {
  alt: '',
  currentIndex: 0,
  total: 1,
})

const emit = defineEmits<{
  close: []
  prev: []
  next: []
}>()

const loaded = ref(false)
const overlayRef = ref<HTMLDivElement | null>(null)
const captionId = `lightbox-caption-${Math.random().toString(36).slice(2, 9)}`
const closeAnnouncement = ref('')

/** 打开 lightbox 时记录触发元素,关闭时焦点返回(WCAG 2.4.3) */
let returnFocusEl: HTMLElement | null = null

const close = () => {
  loaded.value = false
  emit('close')
}

const prev = () => {
  loaded.value = false
  emit('prev')
}

const next = () => {
  loaded.value = false
  emit('next')
}

/** focus trap:在 lightbox 内可聚焦元素之间循环(WCAG 2.1.2) */
const FOCUSABLE_SELECTOR = 'button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'
const handleTabKey = (e: KeyboardEvent) => {
  if (e.key !== 'Tab' || !overlayRef.value) return
  const focusables = Array.from(
    overlayRef.value.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
  ).filter((el) => el.offsetParent !== null)
  if (focusables.length === 0) {
    // 兜底:把焦点保持在 overlay 自己上,避免 Tab 逃出 modal
    e.preventDefault()
    overlayRef.value.focus()
    return
  }
  const first = focusables[0]
  const last = focusables[focusables.length - 1]
  const active = document.activeElement as HTMLElement | null
  if (e.shiftKey && (active === first || !overlayRef.value.contains(active))) {
    e.preventDefault()
    last.focus()
  } else if (!e.shiftKey && active === last) {
    e.preventDefault()
    first.focus()
  }
}

// Focus trap and keyboard
watch(
  () => props.visible,
  (val) => {
    if (val) {
      // 记录触发元素,关闭时恢复焦点
      returnFocusEl = (document.activeElement as HTMLElement) ?? null
      closeAnnouncement.value = ''
      nextTick(() => overlayRef.value?.focus())
    } else {
      // 关闭:焦点返回触发元素
      nextTick(() => {
        if (returnFocusEl && document.contains(returnFocusEl)) {
          returnFocusEl.focus()
        }
        returnFocusEl = null
      })
      // 屏幕阅读器宣告对话框关闭
      closeAnnouncement.value = t.value.closed
    }
  }
)

// Global keyboard handler
const handleKeydown = (e: KeyboardEvent) => {
  if (!props.visible) return
  if (e.key === 'Escape') close()
  if (e.key === 'ArrowLeft' && props.total && props.total > 1) prev()
  if (e.key === 'ArrowRight' && props.total && props.total > 1) next()
  handleTabKey(e)
}

if (typeof window !== 'undefined') {
  // 缓存 body overflow 原始值,关闭时恢复(避免破坏 lightbox 打开前已设置的 overflow:hidden)
  const PREV_OVERFLOW_KEY = 'data-prev-overflow'
  watch(
    () => props.visible,
    (val) => {
      if (val) {
        document.addEventListener('keydown', handleKeydown)
        if (typeof document.body.style.overflow === 'string' && document.body.style.overflow !== 'hidden') {
          document.body.setAttribute(PREV_OVERFLOW_KEY, document.body.style.overflow)
        }
        document.body.style.overflow = 'hidden'
      } else {
        document.removeEventListener('keydown', handleKeydown)
        const prev = document.body.getAttribute(PREV_OVERFLOW_KEY)
        document.body.style.overflow = prev ?? ''
        document.body.removeAttribute(PREV_OVERFLOW_KEY)
      }
    }
  )
}
</script>

<style scoped>
.lightbox-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--vp-z-index-lightbox);  /* 200 — 完整 modal,必须高于所有 sticky 元素 */
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.92);
  backdrop-filter: blur(12px);
  cursor: zoom-out;
}

.lightbox-close {
  position: absolute;
  top: 1.2rem;
  right: 1.2rem;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.3s, background 0.2s, border-color 0.2s, box-shadow 0.3s;
  z-index: 10;
}

.lightbox-close:hover {
  background: rgba(255, 255, 255, 0.15);
  border-color: rgba(255, 255, 255, 0.3);
}

.lightbox-close:focus-visible,
.lightbox-nav:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 2px;
}

.lightbox-close svg {
  width: 1.2rem;
  height: 1.2rem;
}

.lightbox-counter {
  position: absolute;
  top: 1.3rem;
  left: 1.5rem;
  color: rgba(255, 255, 255, 0.6);
  font-size: 0.85rem;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  z-index: 10;
}

.lightbox-nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 3rem;
  height: 3rem;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(0, 0, 0, 0.4);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.3s, background 0.2s, border-color 0.2s, box-shadow 0.3s;
  z-index: 10;
}

.lightbox-nav:hover {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.25);
}

.lightbox-nav svg {
  width: 1.4rem;
  height: 1.4rem;
}

.lightbox-nav--prev {
  left: 1.2rem;
}

.lightbox-nav--next {
  right: 1.2rem;
}

.lightbox-image-wrap {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  max-width: 90vw;
  max-height: 88vh;
}

.lightbox-image {
  display: block;
  /* 禁止 flex 压缩,保证图片保持自身比例与约束尺寸,不被 wrap 高度压缩变形 */
  flex-shrink: 0;
  max-width: 100%;
  /* 预留 caption 空间,避免 wrap 超限后被压缩影响居中 */
  max-height: 78vh;
  object-fit: contain;
  border-radius: var(--vp-radius-sm);
  opacity: 0;
  transform: scale(0.92);
  transition: transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1), background 0.3s, border-color 0.3s, box-shadow 0.4s;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

.lightbox-image.is-loaded {
  opacity: 1;
  transform: scale(1);
}

.lightbox-caption {
  flex-shrink: 0;
  margin-top: 0.8rem;
  color: rgba(255, 255, 255, 0.6);
  font-size: 0.85rem;
}

.lightbox-loader {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}

.lightbox-spinner {
  width: 2rem;
  height: 2rem;
  border: 2px solid rgba(255, 255, 255, 0.1);
  border-top-color: #8b5cf6;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Transition */
.lightbox-enter-active {
  transition: transform 0.3s, background 0.2s, border-color 0.2s, box-shadow 0.3s;
}
.lightbox-leave-active {
  transition: transform 0.25s, background 0.2s, border-color 0.2s;
}
.lightbox-enter-from {
  opacity: 0;
}
.lightbox-leave-to {
  opacity: 0;
}
.lightbox-enter-from .lightbox-image,
.lightbox-leave-to .lightbox-image {
  transform: scale(0.92);
}

@media (max-width: 640px) {
  .lightbox-nav {
    width: 2.2rem;
    height: 2.2rem;
  }
  .lightbox-nav svg {
    width: 1rem;
    height: 1rem;
  }
  .lightbox-image {
    max-width: 96vw;
    max-height: 70vh;
  }
}
</style>
