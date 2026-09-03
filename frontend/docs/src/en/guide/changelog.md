---
layout: doc
title: Changelog
description: "Version changelog: feature iterations, performance optimizations, bug fixes across v1.0 → v3.1.0."
sidebar: false
aside: false
---

<script setup>
import { versions } from '../../data/changelog'

const labels = {
  features: '✨ New Features',
  improvements: '🚀 Improvements',
  fixes: '🐛 Bug Fixes',
}
</script>

<div class="changelog-page">
  <div class="changelog-hero">
    <h1 class="changelog-title">What's New</h1>
    <p class="changelog-subtitle">Continuous iteration to improve development efficiency</p>
  </div>

  <div class="timeline">
    <div
      v-for="(item, index) in versions"
      :key="item.version"
      class="timeline-item"
      :class="{ 'timeline-item--last': index === versions.length - 1 }"
    >
      <div class="timeline-marker">
        <div class="timeline-dot"></div>
      </div>
      <div class="timeline-content">
        <div class="version-header">
          <span class="version-tag">{{ item.version }}</span>
          <span class="version-date">{{ item.date }}</span>
        </div>
        <div class="version-card">
          <div v-if="item.features.length" class="version-section">
            <div class="section-label section-label--new">{{ labels.features }}</div>
            <ul class="feature-list">
              <li v-for="feature in item.features" :key="feature">{{ feature }}</li>
            </ul>
          </div>
          <div v-if="item.improvements.length" class="version-section">
            <div class="section-label section-label--improved">{{ labels.improvements }}</div>
            <ul class="feature-list">
              <li v-for="improvement in item.improvements" :key="improvement">{{ improvement }}</li>
            </ul>
          </div>
          <div v-if="item.fixes.length" class="version-section">
            <div class="section-label section-label--fixed">{{ labels.fixes }}</div>
            <ul class="feature-list">
              <li v-for="fix in item.fixes" :key="fix">{{ fix }}</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

<style scoped>
.changelog-page {
  max-width: 800px;
  margin: 0 auto;
  padding: 4rem 2rem 8rem;
}

.changelog-hero {
  text-align: center;
  margin-bottom: 5rem;
}

.changelog-title {
  font-size: clamp(2.5rem, 6vw, 2rem);
  font-weight: 800;
  background: var(--vp-brand-gradient);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: 1rem;
  letter-spacing: -0.02em;
}

.changelog-subtitle {
  font-size: 1.2rem;
  color: var(--vp-c-text-2);
}

.timeline {
  position: relative;
}

.timeline::before {
  content: '';
  position: absolute;
  left: 7px;
  top: 8px;
  bottom: 0;
  width: 2px;
  background: linear-gradient(180deg, #5B6CF7, #8B5CF6, #EC4899);
  border-radius: 1px;
}

.timeline-item {
  position: relative;
  padding-left: 40px;
  padding-bottom: 3rem;
}

.timeline-item--last {
  padding-bottom: 0;
}

.timeline-marker {
  position: absolute;
  left: 0;
  top: 6px;
}

.timeline-dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: linear-gradient(135deg, #5B6CF7, #8B5CF6);
  border: 3px solid var(--vp-c-bg);
  box-shadow: 0 0 0 2px #5B6CF7;
}

.timeline-content {
  flex: 1;
}

.version-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
}

.version-tag {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--vp-c-text-1);
}

.version-date {
  font-size: 0.9rem;
  color: var(--vp-c-text-3);
}

.version-card {
  background: var(--vp-c-bg-soft);
  border: 1px solid var(--vp-c-divider);
  border-radius: 16px;
  padding: 1.5rem 2rem;
  transition: transform 0.3s, border-color 0.3s, box-shadow 0.3s;
}

.version-card:hover {
  border-color: var(--vp-c-brand-1);
  transform: translateY(-2px);
  box-shadow: 0 8px 30px rgba(91, 108, 247, 0.15);
}

.version-section {
  margin-bottom: 1.25rem;
}

.version-section:last-child {
  margin-bottom: 0;
}

.section-label {
  display: inline-block;
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.25rem 0.75rem;
  border-radius: 6px;
  margin-bottom: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.section-label--new {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.section-label--improved {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
}

.section-label--fixed {
  background: rgba(249, 115, 22, 0.15);
  color: #f97316;
}

.feature-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.feature-list li {
  position: relative;
  padding-left: 1.25rem;
  margin-bottom: 0.5rem;
  color: var(--vp-c-text-2);
  line-height: 1.6;
}

.feature-list li:last-child {
  margin-bottom: 0;
}

.feature-list li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0.6rem;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--vp-c-text-3);
}

@media (max-width: 640px) {
  .changelog-page {
    padding: 2rem 1rem 4rem;
  }

  .timeline::before {
    left: 4px;
  }

  .timeline-item {
    padding-left: 30px;
  }

  .timeline-dot {
    width: 12px;
    height: 12px;
  }

  .version-card {
    padding: 1.25rem;
  }
}
</style>
