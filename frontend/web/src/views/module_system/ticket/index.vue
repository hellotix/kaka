<template>
  <div class="fa-full-height">
    <FaSearchBar
      v-show="showSearchBar"
      v-model="searchForm"
      :items="ticketSearchItems"
      :is-expand="false"
      :show-expand="true"
      :show-reset="true"
      :show-search="true"
      :disabled-search="false"
      :default-expanded="false"
      include-audit
      :audit-item-options="{ showTenantId: true }"
      @search="handleSearchBarSearch"
      @reset="onResetSearch"
    />

    <ElCard class="fa-table-card" :style="{ 'margin-top': showSearchBar ? '12px' : '0' }">
      <FaTableHeader
        v-model:columns="columnChecks"
        v-model:showSearchBar="showSearchBar"
        :loading="loading"
        layout="search,refresh"
        @refresh="fetchData"
      >
        <template #left>
          <ElButton
            v-if="hasAuth('module_system:ticket:create')"
            type="primary"
            @click="handleOpenDialog('create')"
          >
            <ElIcon><Plus /></ElIcon>
            提交工单
          </ElButton>
          <ElButton
            v-if="hasAuth('module_system:ticket:delete') && selectedIds.length"
            type="danger"
            :loading="batchDeleting"
            @click="handleBatchDelete"
          >
            <ElIcon><Delete /></ElIcon>
            批量删除
          </ElButton>
        </template>
      </FaTableHeader>

      <!-- 加载骨架 -->
      <ElSkeleton v-if="loading && !data.length" :rows="4" animated style="margin-top: 16px">
        <template #template>
          <div class="ticket-skeleton-grid">
            <div v-for="i in 6" :key="i" style="height: 320px">
              <ElSkeletonItem
                variant="rect"
                style="width: 100%; height: 100%; border-radius: var(--custom-radius)"
              />
            </div>
          </div>
        </template>
      </ElSkeleton>

      <!-- 卡片网格 -->
      <ElScrollbar v-else-if="data.length" class="ticket-scroll">
        <div class="ticket-grid">
          <div
            v-for="item in data"
            :key="item.id"
            class="ticket-card fa-card"
            :class="[`status-${item.status}`]"
          >
            <!-- 头部：类型图标 + 标题 + 状态徽章 -->
            <div class="card-header">
              <span class="card-icon" :class="typeIconClass(item.ticket_type!)">
                <FaSvgIcon :icon="typeIcon(item.ticket_type!)" />
              </span>
              <div class="card-title-group">
                <span class="card-title" :title="item.title">{{ item.title }}</span>
                <ElTag size="small" :type="statusTagType(String(item.status))" effect="plain">
                  {{ statusLabel(String(item.status)) }}
                </ElTag>
              </div>
            </div>

            <!-- 内容摘要 -->
            <p class="card-desc">{{ contentSummary(item.ticket_content) }}</p>

            <!-- 标签行 -->
            <div class="card-tags">
              <ElTag size="small" effect="plain" :type="typeTag(item.ticket_type!)">
                {{ typeLabel(item.ticket_type!) }}
              </ElTag>
              <span v-if="item.assigned_by" class="tag-assignee">
                <FaSvgIcon icon="ri:user-3-line" />
                {{ item.assigned_by.name }}
              </span>
              <span v-else class="tag-unassigned">未分配</span>
              <span v-if="item.reply" class="tag-replied">
                <FaSvgIcon icon="ri:chat-1-line" />已回复
              </span>
            </div>

            <!-- 底部 -->
            <div class="card-footer">
              <span class="footer-meta">
                {{ item.created_by?.name ?? "—" }}
                &nbsp;·&nbsp;
                {{ item.created_time?.slice(0, 10) ?? "" }}
              </span>
              <div class="footer-actions">
                <ElButton
                  size="small"
                  link
                  type="primary"
                  @click="handleOpenDialog('detail', item.id!)"
                >
                  详情
                </ElButton>
                <ElButton
                  v-if="hasAuth('module_system:ticket:update') && item.status! < 3"
                  size="small"
                  type="primary"
                  @click="handleOpenDialog('update', item.id!)"
                >
                  处理
                </ElButton>
                <ElDropdown v-if="showCardMore(item)" trigger="click">
                  <ElButton size="small" link type="primary" class="more-btn">
                    <ElIcon><MoreFilled /></ElIcon>
                  </ElButton>
                  <template #dropdown>
                    <ElDropdownMenu>
                      <ElDropdownItem
                        v-if="hasAuth('module_system:ticket:update') && item.status! < 3"
                        @click="closeTicket(item.id!)"
                      >
                        <ElIcon><CircleClose /></ElIcon>关闭
                      </ElDropdownItem>
                      <ElDropdownItem
                        v-if="hasAuth('module_system:ticket:delete')"
                        divided
                        @click="deleteTicketRow(item.id!)"
                      >
                        <ElIcon><Delete /></ElIcon>删除
                      </ElDropdownItem>
                    </ElDropdownMenu>
                  </template>
                </ElDropdown>
              </div>
            </div>
          </div>
        </div>
      </ElScrollbar>

      <ElEmpty v-else-if="!loading" description="暂无工单" style="margin-top: 40px" />

      <!-- 分页 -->
      <div v-if="total > 0" class="ticket-pagination">
        <FaPagination
          :page="pageNo"
          :limit="pageSize"
          :total="total"
          :page-sizes="[12, 24, 48]"
          :disabled="loading"
          @pagination="onPaginationChange"
        />
      </div>
    </ElCard>

    <!-- ─── 对话框 ─── -->
    <FaDialog
      v-model="dialogVisible.visible"
      :title="dialogVisible.title"
      width="960px"
      dialog-class="crud-embed-dialog"
      modal-class="crud-embed-dialog"
      :form-mode="dialogVisible.type"
      :confirm-loading="submitLoading"
      @cancel="handleCloseDialog"
      @confirm="dialogVisible.type === 'detail' ? handleCloseDialog() : handleSubmit()"
    >
      <template v-if="dialogVisible.type === 'detail'">
        <FaDescriptions
          :column="4"
          :data="detailFormData"
          :items="ticketDetailItems"
          label-width="120px"
          max-height="40vh"
        >
          <template #ticket_type="{ row }">
            <FaStatusTag
              :type="typeTag(row?.ticket_type as string)"
              :label="typeLabel(row?.ticket_type as string)"
            />
          </template>
          <template #status="{ row }">
            <FaStatusTag
              :type="statusTagType(String(row?.status ?? 0))"
              :label="statusLabel(String(row?.status ?? 0))"
            />
          </template>
          <template #ticket_content>
            <ElScrollbar class="ticket-html-preview" view-class="p-3">
              <template v-if="detailHasRenderableContent">
                <div v-html="detailContentHtml" />
              </template>
              <p v-else class="ticket-html-empty">暂无内容</p>
            </ElScrollbar>
          </template>
          <template #reply_content>
            <ElScrollbar v-if="detailFormData.reply" class="ticket-html-preview" view-class="p-3">
              <div v-html="sanitizedReply" />
            </ElScrollbar>
            <p v-else class="ticket-html-empty">暂无回复</p>
          </template>
        </FaDescriptions>

        <!-- ── 评论区 ── -->
        <ElDivider content-position="left">
          <span class="comment-divider-title">
            <FaSvgIcon icon="ri:chat-3-line" style="margin-right: 6px" />
            评论（{{ commentsTotal }}）
          </span>
        </ElDivider>
        <div class="comment-section">
          <ElScrollbar max-height="280px" class="comment-list-scroll">
            <div v-if="commentsLoading" class="comment-loading">
              <ElSkeleton :rows="2" animated />
            </div>
            <template v-else-if="comments.length">
              <div v-for="c in comments" :key="c.id" class="comment-item">
                <div class="comment-avatar">
                  <FaSvgIcon icon="ri:user-6-fill" />
                </div>
                <div class="comment-body">
                  <div class="comment-meta">
                    <span class="comment-author">{{
                      c.created_by_name || c.created_by?.name || "匿名"
                    }}</span>
                    <span class="comment-time">{{ c.created_time?.slice(0, 16) ?? "" }}</span>
                  </div>
                  <div class="comment-content" v-html="sanitizeComment(c.content)" />
                </div>
              </div>
            </template>
            <ElEmpty v-else description="暂无评论" :image-size="60" />
          </ElScrollbar>

          <!-- 提交评论 -->
          <div class="comment-input-row">
            <ElInput
              v-model="commentInput"
              type="textarea"
              :rows="2"
              placeholder="输入评论内容..."
              :disabled="commentSubmitting"
              resize="none"
            />
            <ElButton
              type="primary"
              :loading="commentSubmitting"
              :disabled="!commentInput.trim()"
              @click="handleSubmitComment"
            >
              发表评论
            </ElButton>
          </div>
        </div>
      </template>
      <template v-else>
        <FaForm
          :key="ticketFormRenderKey"
          scrollbar
          max-height="75vh"
          ref="dataFormRef"
          v-model="formData"
          :items="ticketDialogFormItems"
          :rules="rules"
          label-suffix=":"
          :label-width="100"
          label-position="right"
          :span="24"
          :gutter="16"
          :show-reset="false"
          :show-submit="false"
          class="crud-dialog-art-form"
        >
          <template #ticket_type>
            <ElSelect v-model="formData.ticket_type" placeholder="请选择工单类型">
              <ElOption label="💡 建议" value="suggestion" />
              <ElOption label="🐛 缺陷" value="bug" />
              <ElOption label="⚡ 优化" value="optimize" />
              <ElOption label="📋 其他" value="other" />
            </ElSelect>
          </template>
          <template #status>
            <ElRadioGroup v-model="formData.status">
              <ElRadio :value="0">待处理</ElRadio>
              <ElRadio :value="1">处理中</ElRadio>
              <ElRadio :value="2">已完成</ElRadio>
              <ElRadio :value="3">已关闭</ElRadio>
            </ElRadioGroup>
          </template>
          <template #assigned_id>
            <FaUserTableSelect
              :model-value="formData.assigned_id == null ? undefined : formData.assigned_id"
              @update:model-value="
                (v: number | undefined) => (formData.assigned_id = v ?? undefined)
              "
            />
          </template>
          <template #ticket_content>
            <FaWangEditor
              :model-value="formData.ticket_content ?? ''"
              height="min(38vh, 320px)"
              placeholder="请详细描述您的问题、建议或优化想法..."
              :exclude-keys="[]"
              @update:model-value="(v: string) => (formData.ticket_content = v)"
            />
          </template>
          <template #reply_content>
            <FaWangEditor
              :model-value="formData.reply_content ?? ''"
              height="min(38vh, 280px)"
              placeholder="请输入回复内容..."
              :exclude-keys="[]"
              @update:model-value="(v: string) => (formData.reply_content = v)"
            />
          </template>
        </FaForm>
      </template>
    </FaDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from "vue";
import { useCrudDialog } from "@/hooks/core/useCrudDialog";
import { useCrudForm } from "@/hooks/core/useCrudForm";
import { confirmDelete, confirmBatchDelete } from "@/hooks/core/useConfirm";
import TicketAPI, {
  getTicketComments,
  createTicketComment,
  type TicketForm,
  type TicketPageQuery,
  type TicketTable,
  type TicketCommentTable,
} from "@/api/module_system/ticket";
import { useAuth } from "@/hooks/core/useAuth";
import type { SearchFormItem } from "@/components/forms/fa-search-bar/index.vue";
import type { FormItem } from "@/components/forms/fa-form/index.vue";
import type FaForm from "@/components/forms/fa-form/index.vue";
import {
  ElTag,
  ElButton,
  ElIcon,
  ElDropdown,
  ElDropdownMenu,
  ElDropdownItem,
  ElSelect,
  ElOption,
  ElRadioGroup,
  ElRadio,
  ElScrollbar,
  ElDivider,
  ElInput,
  ElMessageBox,
} from "element-plus";
import { Plus, Delete, MoreFilled, CircleClose } from "@element-plus/icons-vue";
import DOMPurify from "dompurify";

defineOptions({
  name: "TicketCard",
  inheritAttrs: false,
});

const { hasAuth } = useAuth();

// ─── 搜索表单 ───
type TicketSearchForm = {
  title?: string;
  ticket_type?: string;
  status?: number;
  created_id?: number;
  assigned_id?: number;
};

const searchForm = ref<TicketSearchForm>({
  title: "",
  ticket_type: "",
  status: undefined,
  created_id: undefined,
  assigned_id: undefined,
});
const showSearchBar = ref(true);

const statusOptions = ref([
  { label: "待处理", value: "0" },
  { label: "处理中", value: "1" },
  { label: "已完成", value: "2" },
  { label: "已关闭", value: "3" },
]);

const ticketTypeSearchOptions = ref([
  { label: "💡 建议", value: "suggestion" },
  { label: "🐛 缺陷", value: "bug" },
  { label: "⚡ 优化", value: "optimize" },
  { label: "📋 其他", value: "other" },
]);

const ticketSearchItems = computed<SearchFormItem[]>(() => [
  {
    label: "工单标题",
    key: "title",
    type: "input",
    placeholder: "请输入工单标题",
    clearable: true,
    span: 6,
  },
  {
    label: "工单类型",
    key: "ticket_type",
    type: "select",
    props: {
      placeholder: "请选择类型",
      options: ticketTypeSearchOptions.value,
      clearable: true,
    },
    span: 6,
  },
  {
    label: "状态",
    key: "status",
    type: "select",
    props: {
      placeholder: "请选择状态",
      options: statusOptions.value,
      clearable: true,
    },
    span: 6,
  },
  {
    label: "处理人",
    key: "assigned_id",
    type: "input",
    span: 6,
  },
]);

// ─── 数据管理 ───
const data = ref<TicketTable[]>([]);
const loading = ref(false);
const pageNo = ref(1);
const pageSize = ref(12);
const total = ref(0);

function normalizeTicketQuery(params: Record<string, unknown>): TicketPageQuery {
  const r: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") {
      r[k] = v;
    }
  }
  return r as unknown as TicketPageQuery;
}

async function fetchData() {
  loading.value = true;
  try {
    const res = await TicketAPI.listTicket({
      ...normalizeTicketQuery(searchForm.value as unknown as Record<string, unknown>),
      page_no: pageNo.value,
      page_size: pageSize.value,
    });
    const result = res.data?.data;
    data.value = (result?.items as TicketTable[]) || [];
    total.value = result?.total || 0;
  } catch {
    // ignore
  } finally {
    loading.value = false;
  }
}

function onPaginationChange({ page, limit }: { page: number; limit: number }) {
  pageNo.value = page;
  pageSize.value = limit;
  fetchData();
}

const columnChecks = ref([]);

async function handleSearchBarSearch(params: Record<string, unknown>) {
  searchForm.value = {
    title: (params.title as string) ?? "",
    ticket_type: (params.ticket_type as string) ?? "",
    status: params.status !== undefined ? Number(params.status) : undefined,
    created_id: params.created_id as number | undefined,
    assigned_id: params.assigned_id as number | undefined,
  };
  pageNo.value = 1;
  await fetchData();
}

async function onResetSearch() {
  searchForm.value = {
    title: "",
    ticket_type: "",
    status: undefined,
    created_id: undefined,
    assigned_id: undefined,
  };
  pageNo.value = 1;
  await fetchData();
}

// ─── 类型/状态辅助 ───
const TYPE_MAP: Record<string, string> = {
  suggestion: "建议",
  bug: "缺陷",
  optimize: "优化",
  other: "其他",
};

const STATUS_MAP: Record<string, string> = {
  "0": "待处理",
  "1": "处理中",
  "2": "已完成",
  "3": "已关闭",
};

function typeLabel(t: string) {
  return TYPE_MAP[t] || t;
}
function statusLabel(s: string) {
  return STATUS_MAP[s] || s;
}
function typeTag(t: string): any {
  return { suggestion: "success", bug: "danger", optimize: "warning", other: "info" }[t] || "info";
}
function statusTagType(s: string): "warning" | "info" | "success" | "danger" | undefined {
  return { "0": "warning", "1": "info", "2": "success", "3": "info" }[s] as any;
}
function typeIcon(t: string): string {
  return (
    {
      suggestion: "ri:lightbulb-line",
      bug: "ri:bug-line",
      optimize: "ri:rocket-line",
      other: "ri:file-list-3-line",
    }[t] || "ri:file-list-3-line"
  );
}
function typeIconClass(t: string): string {
  return (
    {
      suggestion: "icon-bg-warning",
      bug: "icon-bg-danger",
      optimize: "icon-bg-success",
      other: "icon-bg-info",
    }[t] || "icon-bg-info"
  );
}
function contentSummary(html?: string): string {
  if (!html) return "暂无内容";
  const plain = html
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return plain.length > 120 ? plain.slice(0, 120) + "…" : plain || "暂无内容";
}
function showCardMore(row: TicketTable): boolean {
  return (
    (hasAuth("module_system:ticket:update") && row.status! < 3) ||
    hasAuth("module_system:ticket:delete")
  );
}

// ─── 多选 ───
const selectedIds = ref<number[]>([]);
const batchDeleting = ref(false);

// ─── 对话框 ───
const { dialogVisible } = useCrudDialog();

const detailFormData = ref<TicketTable & { reply_content?: string }>(
  {} as TicketTable & { reply_content?: string }
);

const ticketDetailItems: import("@/components/others/fa-descriptions/index.vue").DescriptionsItem[] =
  [
    { label: "工单标题", prop: "title", span: 4 },
    { label: "工单类型", prop: "ticket_type", slot: "ticket_type" },
    { label: "状态", prop: "status", slot: "status" },
    { label: "处理人", prop: "assigned_by.name" },
    { label: "描述", prop: "description", span: 4 },
    { label: "详细内容", prop: "ticket_content", slot: "ticket_content", span: 4 },
    { label: "回复内容", prop: "reply", slot: "reply_content", span: 4 },
    { label: "创建人", prop: "created_by.name" },
    { label: "更新人", prop: "updated_by.name" },
    { label: "创建时间", prop: "created_time" },
    { label: "更新时间", prop: "updated_time" },
    { label: "所属租户", prop: "tenant_by.name" },
  ];

const detailContentHtml = computed({
  get: () => DOMPurify.sanitize(detailFormData.value.ticket_content ?? ""),
  set: (v: string) => {
    detailFormData.value.ticket_content = v;
  },
});

const sanitizedReply = computed(() => {
  const raw = detailFormData.value.reply ?? "";
  return raw ? DOMPurify.sanitize(raw) : "";
});

const detailHasRenderableContent = computed(() => {
  const raw = detailFormData.value.ticket_content ?? "";
  if (!raw.trim()) return false;
  const plain = raw
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return plain.length > 0;
});

const formData = ref<TicketForm & { reply_content?: string }>({
  id: undefined,
  title: "",
  ticket_type: "suggestion",
  ticket_content: "",
  status: 0,
  description: undefined,
  assigned_id: undefined,
  reply_content: undefined,
});

const rules = reactive({
  title: [{ required: true, message: "请输入工单标题", trigger: "blur" }],
  ticket_type: [{ required: true, message: "请选择工单类型", trigger: "blur" }],
  ticket_content: [{ required: true, message: "请输入工单内容", trigger: "blur" }],
  status: [{ required: true, message: "请选择状态", trigger: "blur" }],
});

const dataFormRef = ref<InstanceType<typeof FaForm> | null>(null);
const ticketFormRenderKey = ref(0);

const initialFormData: TicketForm & { reply_content?: string } = {
  id: undefined,
  title: "",
  ticket_type: "suggestion",
  ticket_content: "",
  status: 0,
  description: undefined,
  assigned_id: undefined,
  reply_content: undefined,
};

const { submitLoading, handleCloseDialog, handleOpenDialog, handleSubmit } = useCrudForm<
  TicketForm & { reply_content?: string }
>({
  formData,
  initialFormData,
  dialogVisible,
  dataFormRef,
  formRenderKey: ticketFormRenderKey,
  detailApi: TicketAPI.detailTicket,
  createApi: TicketAPI.createTicket,
  updateApi: TicketAPI.updateTicket,
  titles: { create: "提交工单", update: "处理工单", detail: "工单详情" },
  detailFormData,
  onCreateSuccess: async () => {
    await fetchData();
  },
  onUpdateSuccess: async () => {
    await fetchData();
  },
  onSubmitSuccess: async () => {
    await fetchData();
  },
});

const ticketDialogFormItems = computed<FormItem[]>(() => [
  {
    label: "工单标题",
    key: "title",
    type: "input",
    span: 24,
    props: { placeholder: "请输入工单标题", maxlength: 200 },
  },
  {
    label: "工单类型",
    key: "ticket_type",
    type: "select",
    span: 12,
    props: { placeholder: "请选择类型", clearable: true },
  },
  {
    label: "状态",
    key: "status",
    type: "input",
    span: 12,
    placeholder: "",
  },
  {
    label: "处理人",
    key: "assigned_id",
    type: "input",
    span: 24,
    placeholder: "",
  },
  {
    label: "详细描述",
    key: "ticket_content",
    type: "input",
    span: 24,
    placeholder: "",
  },
  {
    label: "回复内容",
    key: "reply_content",
    type: "input",
    span: 24,
    placeholder: "",
  },
]);

// ─── 操作 ───
async function deleteTicketRow(id: number) {
  try {
    await confirmDelete();
    await TicketAPI.deleteTicket([id]);
    await fetchData();
  } catch {
    // 用户取消
  }
}

async function closeTicket(id: number) {
  try {
    await ElMessageBox.confirm("确认关闭该工单?", "警告", {
      confirmButtonText: "确定",
      cancelButtonText: "取消",
      type: "warning",
    });
    await TicketAPI.updateTicket(id, { status: 3 });
    await fetchData();
  } catch {
    /* 用户取消或接口错误已由拦截器提示 */
  }
}

async function handleBatchDelete() {
  const ids = selectedIds.value;
  if (ids.length === 0) return;
  try {
    await confirmBatchDelete(ids.length);
    batchDeleting.value = true;
    selectedIds.value = [];
    await TicketAPI.deleteTicket(ids);
    await fetchData();
  } catch {
    // 用户取消
  } finally {
    batchDeleting.value = false;
  }
}

onMounted(() => {
  fetchData();
});

// ─── 评论 ───
const comments = ref<TicketCommentTable[]>([]);
const commentsTotal = ref(0);
const commentsLoading = ref(false);
const commentInput = ref("");
const commentSubmitting = ref(false);

// 打开详情时自动加载评论
watch(
  () => detailFormData.value.id,
  (newId) => {
    if (newId && dialogVisible.visible && dialogVisible.type === "detail") {
      loadComments(newId);
    }
  }
);

async function loadComments(ticketId: number) {
  commentsLoading.value = true;
  try {
    const res = await getTicketComments(ticketId, { page_no: 1, page_size: 50 });
    const result = res.data?.data;
    comments.value = (result?.items as TicketCommentTable[]) || [];
    commentsTotal.value = result?.total || 0;
  } catch {
    // ignore
  } finally {
    commentsLoading.value = false;
  }
}

function sanitizeComment(html: string): string {
  return DOMPurify.sanitize(html || "");
}

async function handleSubmitComment() {
  const tid = detailFormData.value.id;
  if (!tid || !commentInput.value.trim()) return;
  commentSubmitting.value = true;
  try {
    await createTicketComment(tid, { content: commentInput.value.trim() });
    commentInput.value = "";
    await loadComments(tid);
  } catch {
    // ignore
  } finally {
    commentSubmitting.value = false;
  }
}
</script>

<style scoped lang="scss">
.fa-full-height {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}

.ticket-skeleton-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.ticket-scroll {
  flex: 1;
  min-height: 0;
  margin-top: 16px;
}

.ticket-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.ticket-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: 20px;
  overflow: hidden;
  transition:
    box-shadow 0.3s,
    transform 0.25s;

  &:hover {
    box-shadow: 0 8px 24px rgb(0 0 0 / 8%);
    transform: translateY(-3px);
  }

  &.status-0 {
    border-left: 3px solid var(--el-color-warning);
  }

  &.status-1 {
    border-left: 3px solid var(--el-color-info);
  }

  &.status-2 {
    border-left: 3px solid var(--el-color-success);
  }

  &.status-3 {
    border-left: 3px solid var(--el-border-color);
  }

  .card-header {
    display: flex;
    gap: 12px;
    align-items: center;
    margin-bottom: 12px;
  }

  .card-icon {
    display: flex;
    flex-shrink: 0;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    font-size: 20px;
    border-radius: 10px;

    &.icon-bg-default {
      color: var(--el-text-color-secondary);
      background: var(--el-fill-color);
    }

    &.icon-bg-warning {
      color: var(--el-color-warning);
      background: var(--el-color-warning-light-9);
    }

    &.icon-bg-success {
      color: var(--el-color-success);
      background: var(--el-color-success-light-9);
    }

    &.icon-bg-info {
      color: var(--el-color-info);
      background: var(--el-color-info-light-9);
    }

    &.icon-bg-danger {
      color: var(--el-color-danger);
      background: var(--el-color-danger-light-9);
    }
  }

  .card-title-group {
    display: flex;
    flex: 1;
    gap: 8px;
    align-items: center;
    min-width: 0;
  }

  .card-title {
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: 15px;
    font-weight: 600;
    color: var(--el-text-color-primary);
    white-space: nowrap;
  }

  .card-desc {
    display: -webkit-box;
    min-height: calc(13px * 1.6 * 2);
    margin: 0 0 12px;
    overflow: hidden;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    font-size: 13px;
    line-height: 1.6;
    color: var(--el-text-color-secondary);
    -webkit-box-orient: vertical;
  }

  .card-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    margin-bottom: 14px;
  }

  .tag-assignee {
    display: inline-flex;
    gap: 4px;
    align-items: center;
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  .tag-unassigned {
    font-size: 12px;
    color: var(--el-text-color-placeholder);
  }

  .tag-replied {
    display: inline-flex;
    gap: 4px;
    align-items: center;
    font-size: 12px;
    color: var(--el-color-primary);
  }

  .card-footer {
    display: flex;
    gap: 8px;
    align-items: center;
    justify-content: space-between;
    padding-top: 12px;
    margin-top: auto;
    border-top: 1px solid var(--el-border-color-lighter);
  }

  .footer-meta {
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: 12px;
    color: var(--el-text-color-secondary);
    white-space: nowrap;
  }

  .footer-actions {
    display: flex;
    flex-shrink: 0;
    gap: 4px;
    align-items: center;
  }

  .more-btn {
    padding: 2px 4px;
    font-size: 16px;
  }
}

.ticket-pagination {
  flex-shrink: 0;
  padding-top: 16px;
}

/* ─── 富文本预览样式 ─── */
.ticket-html-preview {
  box-sizing: border-box;
  min-height: 120px;
  max-height: min(360px, 45vh);
  background-color: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: calc(var(--custom-radius) / 3 + 2px);
}

.ticket-html-empty {
  margin: 0;
  font-size: 14px;
  color: var(--el-text-color-placeholder);
}

.ticket-html-preview :deep(h1),
.ticket-html-preview :deep(h2),
.ticket-html-preview :deep(h3) {
  margin: 12px 0 8px;
}

.ticket-html-preview :deep(p) {
  margin: 8px 0;
  line-height: 1.6;
}

.ticket-html-preview :deep(table) {
  margin: 12px 0;
}

.ticket-html-preview :deep(table th),
.ticket-html-preview :deep(table td) {
  padding: 8px 12px;
}

.ticket-html-preview :deep(pre) {
  padding: 12px;
  margin: 12px 0;
  overflow-x: auto;
  background-color: var(--el-fill-color-light);
  border-radius: 4px;
}

.ticket-html-preview :deep(blockquote) {
  padding-left: 16px;
  margin: 12px 0;
  color: var(--el-text-color-regular);
  border-left: 4px solid var(--el-color-primary);
}

.ticket-html-preview :deep(img) {
  max-width: 100%;
  height: auto;
}

/* ─── 评论区 ─── */
.comment-divider-title {
  display: inline-flex;
  align-items: center;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.comment-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 400px;
}

.comment-list-scroll {
  padding: 0 4px;
}

.comment-loading {
  padding: 12px 0;
}

.comment-item {
  display: flex;
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);

  &:last-child {
    border-bottom: none;
  }
}

.comment-avatar {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  font-size: 16px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 50%;
}

.comment-body {
  flex: 1;
  min-width: 0;
}

.comment-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
}

.comment-author {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.comment-time {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

.comment-content {
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  overflow-wrap: anywhere;
}

.comment-content :deep(p) {
  margin: 4px 0;
}

.comment-content :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: 4px;
}

.comment-input-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);

  .el-textarea {
    flex: 1;
  }

  .el-button {
    flex-shrink: 0;
    margin-top: 2px;
  }
}
</style>
