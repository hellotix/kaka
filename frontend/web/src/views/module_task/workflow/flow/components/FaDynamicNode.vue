<template>
  <div
    class="wf-node"
    :class="{ 'is-selected': selected }"
    @mouseenter="showHandles = true"
    @mouseleave="showHandles = false"
  >
    <div class="node-body" :style="{ '--node-color': color }">
      <span class="node-flag" :style="{ background: color }" />
      <ElIcon :size="16" :color="color"><component :is="nodeIcon" /></ElIcon>
      <div class="node-text">
        <span class="node-label">{{ nodeData.label }}</span>
        <span class="node-category">{{ categoryText }}</span>
      </div>
      <span v-if="badgeCount" class="node-badge" :style="{ background: color }">
        {{ badgeCount }}
      </span>
    </div>
    <Handle
      v-if="nodeType.code !== 'input'"
      :id="'top-' + id"
      type="target"
      :position="Position.Top"
      :class="{ 'handle-visible': showHandles }"
      :style="{ background: color }"
    />
    <Handle
      v-if="nodeType.code !== 'input'"
      :id="'left-' + id"
      type="target"
      :position="Position.Left"
      :class="{ 'handle-visible': showHandles }"
      :style="{ background: color }"
    />
    <Handle
      v-if="nodeType.code !== 'output'"
      :id="'right-' + id"
      type="source"
      :position="Position.Right"
      :class="{ 'handle-visible': showHandles }"
      :style="{ background: color }"
    />
    <Handle
      v-if="nodeType.code !== 'output'"
      :id="'bottom-' + id"
      type="source"
      :position="Position.Bottom"
      :class="{ 'handle-visible': showHandles }"
      :style="{ background: color }"
    />
  </div>
</template>

<script lang="ts" setup>
import { ref, computed, type Component } from "vue";
import { Handle, Position } from "@vue-flow/core";
import { ElIcon } from "element-plus";
import {
  Bell,
  ChatDotRound,
  CircleCheckFilled,
  Connection,
  Delete,
  Download,
  Link,
  Odometer,
  Promotion,
  QuestionFilled,
  SetUp,
  UploadFilled,
} from "@element-plus/icons-vue";

interface Props {
  id?: string;
  data?: Record<string, any>;
  selected?: boolean;
}

const props = withDefaults(defineProps<Props>(), {});

const showHandles = ref(false);

const nodeData = computed(() => props.data ?? { label: "", config: {}, type: undefined, category: undefined });

const nodeType = computed(() => {
  const category = nodeData.value?.category || "action";
  return {
    code: nodeData.value?.type || "custom",
    name: nodeData.value?.label || "自定义节点",
    category,
    color: getCategoryColor(category),
  };
});

function getCategoryColor(category: string | undefined) {
  const colorMap: Record<string, string> = {
    trigger: "#e6a23c",
    action: "#409eff",
    condition: "#67c23a",
    control: "#909399",
  };
  return colorMap[category || "action"] || "#409eff";
}

const CATEGORY_TEXT: Record<string, string> = {
  trigger: "触发器",
  action: "动作",
  condition: "条件",
  control: "控制",
};

const categoryText = computed(() => CATEGORY_TEXT[nodeType.value.category] || "节点");

const CATEGORY_ICON: Record<string, Component> = {
  trigger: Odometer,
  action: Promotion,
  condition: QuestionFilled,
  control: SetUp,
};

const NODE_ICON: Record<string, Component> = {
  storage_upload: UploadFilled,
  storage_download: Download,
  storage_url: Link,
  storage_exists: CircleCheckFilled,
  storage_delete: Delete,
  notice_send: Bell,
  ai_chat: ChatDotRound,
  http_check: Connection,
};

const nodeIcon = computed<Component>(() => {
  const code = nodeType.value.code;
  if (NODE_ICON[code]) return NODE_ICON[code];
  return CATEGORY_ICON[nodeType.value.category] || Promotion;
});

const badgeCount = computed(() => {
  const config = nodeData.value?.config;
  return config && typeof config === "object" ? Object.keys(config).length : 0;
});

const color = computed(() => nodeType.value.color);
</script>

<style scoped lang="scss">
.vue-flow__node-input {
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  width: 80px !important;
  height: 80px !important;
  padding: 0 !important;
  color: #fff !important;
  cursor: pointer !important;
  background: linear-gradient(135deg, #67c23a 0%, #5daf34 100%) !important;
  border: 3px solid #5daf34 !important;
  border-radius: 50% !important;
  box-shadow:
    0 6px 12px rgb(103 194 58 / 40%),
    0 2px 4px rgb(0 0 0 / 10%) !important;
}

.vue-flow__node-output {
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  width: 80px !important;
  height: 80px !important;
  padding: 0 !important;
  color: #fff !important;
  cursor: pointer !important;
  background: linear-gradient(135deg, #f56c6c 0%, #e04e4e 100%) !important;
  border: 3px solid #e04e4e !important;
  border-radius: 50% !important;
  box-shadow:
    0 6px 12px rgb(245 108 108 / 40%),
    0 2px 4px rgb(0 0 0 / 10%) !important;
}

.vue-flow__node-input .wf-node,
.vue-flow__node-output .wf-node {
  padding: 0;
  background: transparent;
  border: none;
  border-radius: 0;
  box-shadow: none;
}

.wf-node {
  position: relative;
  cursor: pointer;

  .node-body {
    position: relative;
    display: flex;
    gap: 8px;
    align-items: center;
    min-width: 168px;
    padding: 10px 14px;
    overflow: hidden;
    background: #fff;
    border: 1.5px solid color-mix(in srgb, var(--node-color) 45%, #d1d5db);
    border-radius: 10px;
    box-shadow: 0 1px 4px rgb(0 0 0 / 6%);
    transition:
      box-shadow 0.2s ease,
      transform 0.2s ease,
      border-color 0.2s ease;

    &:hover {
      box-shadow: 0 6px 16px rgb(0 0 0 / 14%);
      transform: translateY(-1px);
    }
  }

  .node-flag {
    position: absolute;
    top: 50%;
    left: 0;
    width: 4px;
    height: 70%;
    border-radius: 0 4px 4px 0;
    transform: translateY(-50%);
  }

  .node-text {
    display: flex;
    flex-direction: column;
    min-width: 0;
    line-height: 1.3;

    .node-label {
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.3px;
      white-space: nowrap;
    }

    .node-category {
      font-size: 10px;
      color: var(--el-text-color-secondary);
    }
  }

  .node-badge {
    margin-left: auto;
    padding: 0 6px;
    font-size: 10px;
    font-weight: 500;
    line-height: 16px;
    color: #fff;
    border-radius: 10px;
  }

  &.is-selected .node-body {
    border-color: var(--node-color);
    box-shadow:
      0 0 0 2px color-mix(in srgb, var(--node-color) 22%, transparent),
      0 6px 18px rgb(0 0 0 / 14%);
  }
}

.vue-flow__handle {
  opacity: 0;
  transition: opacity 0.2s ease;
}

.vue-flow__handle.handle-visible,
.vue-flow__handle.vue-flow__handle-connecting,
.vue-flow__handle.vue-flow__handle-valid {
  opacity: 1;
}
</style>
