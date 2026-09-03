<template>
  <div class="home-sections">
    <SectionNav />

    <!-- 分隔线:hero 与端到端区块之间的渐变过渡 -->
    <hr class="section-divider" aria-hidden="true" />

    <!-- 端到端 S 型展示(Linear 风格 alternate 4 段,末尾含产品全览画廊) -->
    <section
      id="end-to-end"
      ref="endToEndSection"
      class="home-section animate-section"
      style="--reveal-delay: 0.1s"
    >
      <EndToEndShowcase />
    </section>

    <!-- CTA 由 StickyCta 承担:滚过 #end-to-end 后整底显示(异步加载 + 仅客户端,节省首屏) -->
    <ClientOnly>
      <StickyCta trigger-selector="#end-to-end" />
    </ClientOnly>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent, ref } from 'vue'
import { useRevealOnScroll } from '../composables/useRevealOnScroll'
import EndToEndShowcase from './EndToEndShowcase.vue'
import SectionNav from './SectionNav.vue'

// ✅ R5 P1-1:首屏优化 — StickyCta 滚过 #end-to-end 才显示,异步加载节省首屏
const StickyCta = defineAsyncComponent(() => import('./StickyCta.vue'))

const endToEndSection = ref<HTMLElement | null>(null)
useRevealOnScroll(endToEndSection)
</script>

<style scoped>
.home-sections {
  padding-bottom: 3rem;
}

/* 分隔线:hero 与端到端区块之间的渐变强调线 */
.section-divider {
  position: relative;
  border: none;
  height: 2px;
  max-width: 720px;
  margin: 4rem auto;
  background: linear-gradient(90deg, transparent, rgba(139, 92, 246, 0.35), rgba(91, 108, 247, 0.5), rgba(236, 72, 153, 0.35), transparent);
  box-shadow: 0 0 16px rgba(139, 92, 246, 0.25);
  border-radius: 2px;
}

.section-divider::before,
.section-divider::after {
  content: '';
  position: absolute;
  top: 50%;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  transform: translateY(-50%);
  background: #a78bfa;
  box-shadow: 0 0 12px #a78bfa;
}

.section-divider::before { left: 30%; opacity: 0.6; }
.section-divider::after { right: 30%; opacity: 0.6; }

.home-section {
  position: relative;
  z-index: 20;
}

/* 滚动渐入:未触发时隐藏,useRevealOnScroll 命中后加 .animate-in
   延迟由 CSS 变量 --reveal-delay 控制,JS 不参与 timing
   用 animation(而非 transition):fill-mode: both 使动画结束后 transform
   恢复为 none —— 避免残留 translateY(0) 让本 section 成为 position:fixed
   后代(如灯箱)的 containing block,劫持其相对视口定位 */
.animate-section {
  opacity: 0;
  transform: translateY(30px);
}

.animate-section.animate-in {
  animation: reveal-section 0.6s cubic-bezier(0.16, 1, 0.3, 1) both;
  animation-delay: var(--reveal-delay, 0s);
}

@keyframes reveal-section {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

@media (max-width: 640px) {
  .section-divider {
    max-width: 85%;
    margin: 2.5rem auto;
  }
  .section-divider::before,
  .section-divider::after {
    display: none;
  }
}
</style>
