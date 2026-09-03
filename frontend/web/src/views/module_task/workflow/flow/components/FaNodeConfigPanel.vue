<template>
  <div class="flex flex-col h-full">
    <div
      class="flex items-center justify-between px-4 py-3 font-semibold border-b border-(--el-border-color-lighter)"
    >
      <span>节点配置</span>
      <ElButton type="text" class="p-1" @click="handleClose">
        <ElIcon><Close /></ElIcon>
      </ElButton>
    </div>

    <ElScrollbar class="flex-1" view-class="p-4">
      <div
        v-if="currentType"
        class="mb-3 flex items-start gap-2 rounded-lg border border-(--el-border-color-lighter) bg-(--el-fill-color-light) px-3 py-2.5"
      >
        <ElIcon :size="16" :color="currentType.color"><component :is="currentType.icon" /></ElIcon>
        <div class="flex flex-col min-w-0 leading-tight">
          <div class="flex items-center gap-2">
            <span class="text-xs font-semibold text-(--el-text-color-primary)">{{ currentType.name }}</span>
            <ElTag size="small" :type="currentType.tagType" effect="light">{{ currentType.categoryText }}</ElTag>
          </div>
          <span v-if="currentType.description" class="mt-0.5 text-[11px] text-(--el-text-color-secondary)">
            {{ currentType.description }}
          </span>
        </div>
      </div>
      <FaForm
        v-model="formData"
        :items="nodePanelFormItems"
        label-width="80px"
        size="small"
        label-position="right"
        :span="24"
        :gutter="12"
        :show-reset="false"
        :show-submit="false"
        class="panel-art-form"
      >
        <template #type>
          <ElSelect v-model="formData.type" placeholder="请选择节点类型" @change="handleTypeChange">
            <ElOption v-for="t in nodeTypes" :key="t.id ?? t.code" :label="t.name" :value="t.code" />
          </ElSelect>
        </template>
        <template #args>
          <div>
            <ElInput
              v-model="formData.args"
              placeholder="多个参数用逗号分隔，如: arg1, arg2, arg3"
            />
            <div class="mt-1 text-xs text-(--el-text-color-secondary)">多个参数用逗号分隔</div>
          </div>
        </template>
        <template #kwargsStr>
          <div>
            <ElInput
              v-model="formData.kwargsStr"
              type="textarea"
              :rows="4"
              placeholder='JSON格式，如: {"key": "value", "count": 10}'
            />
            <div class="mt-1 text-xs text-(--el-text-color-secondary)">JSON 格式的关键字参数</div>
          </div>
        </template>
      </FaForm>

      <div
        class="flex gap-2 pt-4 border-t border-(--el-border-color-lighter) [&_.el-button]:flex-1"
      >
        <ElButton type="primary" size="small" @click="handleSave">保存</ElButton>
        <ElButton type="danger" size="small" @click="handleDelete">删除节点</ElButton>
      </div>
    </ElScrollbar>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed, type Component } from "vue";
import {
  ElButton,
  ElInput,
  ElSelect,
  ElOption,
  ElMessage,
  ElIcon,
  ElScrollbar,
  ElTag,
} from "element-plus";
import { Close, UploadFilled, Download, Link, CircleCheckFilled, Delete, Promotion, Bell, ChatDotRound, Connection, Odometer, QuestionFilled, SetUp } from "@element-plus/icons-vue";
import type { FormItem } from "@/components/forms/fa-form/index.vue";
import FaForm from "@/components/forms/fa-form/index.vue";
import WorkflowNodeTypeAPI, { type WorkflowNodeTypeOption } from "@/api/module_task/workflow/nodes";

interface Props {
  node?: Record<string, any>;
}

const props = withDefaults(defineProps<Props>(), {
  node: () => ({}),
});

const emit = defineEmits(["close", "save", "delete"]);

const nodeTypes = ref<WorkflowNodeTypeOption[]>([]);

const CATEGORY_META: Record<string, { label: string; color: string; tagType: any; icon: Component }> = {
  trigger: { label: "触发器", color: "#e6a23c", tagType: "warning", icon: Odometer },
  action: { label: "动作", color: "#409eff", tagType: "primary", icon: Promotion },
  condition: { label: "条件", color: "#67c23a", tagType: "success", icon: QuestionFilled },
  control: { label: "控制", color: "#909399", tagType: "info", icon: SetUp },
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

const currentType = computed(() => {
  const code = formData.value.type;
  if (!code) return null;
  const t = nodeTypes.value.find((item) => item.code === code);
  const category = t?.category || "action";
  const meta = CATEGORY_META[category] || CATEGORY_META.action!;
  return {
    name: t?.name || code,
    description: t?.description || "",
    color: meta.color,
    icon: NODE_ICON[code] || meta.icon,
    categoryText: meta.label,
    tagType: meta.tagType,
  };
});

const formData = ref({
  type: props.node?.type || "",
  label: props.node?.data?.label || "",
  args: props.node?.data?.args || "",
  kwargsStr: props.node?.data?.kwargsStr || "{}",
  description: props.node?.data?.description || "",
});

const nodePanelFormItems = computed<FormItem[]>(() => [
  {
    label: "节点类型",
    key: "type",
    type: "input",
    span: 24,
    placeholder: "",
  },
  {
    label: "节点名称",
    key: "label",
    type: "input",
    span: 24,
    props: { placeholder: "请输入节点名称" },
  },
  {
    label: "位置参数",
    key: "args",
    type: "input",
    span: 24,
    placeholder: "",
  },
  {
    label: "关键字参数",
    key: "kwargsStr",
    type: "input",
    span: 24,
    placeholder: "",
  },
  {
    label: "描述",
    key: "description",
    type: "input",
    span: 24,
    props: {
      type: "textarea",
      rows: 2,
      placeholder: "请输入描述信息",
    },
  },
]);

const loadNodeTypes = async () => {
  try {
    const res = await WorkflowNodeTypeAPI.getWorkflowNodeTypeOptions();
    if (res.data) {
      nodeTypes.value = res.data.data || [];
    }
  } catch {
    ElMessage.error("加载节点类型失败");
  }
};

const handleTypeChange = async (typeCode: string) => {
  const nodeType = nodeTypes.value.find((t) => t.code === typeCode);
  if (nodeType) {
    formData.value.args = nodeType.args || "";
    formData.value.kwargsStr = nodeType.kwargs || "{}";
  }
};

watch(
  () => props.node,
  (newNode) => {
    if (newNode) {
      const kwargsData = newNode.data?.kwargs;
      let kwargsStr = "{}";
      if (kwargsData) {
        if (typeof kwargsData === "string") {
          kwargsStr = kwargsData;
        } else if (typeof kwargsData === "object") {
          kwargsStr = JSON.stringify(kwargsData, null, 2);
        }
      }

      Object.assign(formData.value, {
        type: newNode.type || "",
        label: newNode.data?.label || "",
        args: newNode.data?.args || "",
        kwargsStr,
        description: newNode.data?.description || "",
      });
    }
  },
  { deep: true, immediate: true }
);

function handleClose() {
  emit("close");
}

function handleSave() {
  try {
    if (formData.value.kwargsStr && formData.value.kwargsStr.trim()) {
      JSON.parse(formData.value.kwargsStr);
    }
  } catch {
    ElMessage.error("关键字参数 JSON 格式错误");
    return;
  }

  emit("save", {
    type: formData.value.type,
    label: formData.value.label,
    args: formData.value.args,
    kwargs: formData.value.kwargsStr,
    description: formData.value.description,
  });
}

function handleDelete() {
  emit("delete");
}

onMounted(() => {
  loadNodeTypes();
  if (props.node?.type) {
    handleTypeChange(props.node.type);
  }
});
</script>

<style scoped lang="scss">
.panel-art-form :deep(.el-row > .el-col:last-child) {
  display: none;
}

.panel-art-form :deep(.el-form-item__content) {
  max-width: 100%;
}

.panel-art-form :deep(section) {
  padding: 0;
}
</style>
