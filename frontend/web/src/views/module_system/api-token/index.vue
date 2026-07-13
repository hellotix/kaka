<!-- API 令牌管理 CRUD -->
<template>
  <div class="fa-full-height">
    <FaSearchBar
      v-show="showSearchBar"
      v-model="searchForm"
      :items="searchItems"
      :is-expand="false"
      :show-expand="true"
      :show-reset="true"
      :show-search="true"
      :default-expanded="false"
      @search="handleSearch"
      @reset="onResetSearch"
    />

    <ElCard class="fa-table-card" :style="{ 'margin-top': showSearchBar ? '12px' : '0' }">
      <FaTableHeader
        v-model:columns="columnChecks"
        v-model:showSearchBar="showSearchBar"
        :loading="loading"
        @refresh="refreshData"
      >
        <template #left>
          <ElButton v-hasPerm="['module_system:token:create']" type="primary" @click="handleAdd">
            <ElIcon><Plus /></ElIcon>
            新增 Token
          </ElButton>
        </template>
      </FaTableHeader>

      <FaTable
        ref="faTableRef"
        :loading="loading"
        :data="data"
        :columns="columns"
        :pagination="pagination"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      />
    </ElCard>

    <!-- 新增/编辑/详情弹窗 -->
    <FaDialog
      v-model="dialogVisible.visible"
      :title="dialogVisible.title"
      width="680px"
      dialog-class="crud-embed-dialog"
      modal-class="crud-embed-dialog"
      :form-mode="dialogVisible.type"
      :confirm-loading="submitLoading"
      :show-footer="dialogVisible.type !== 'detail'"
      @cancel="handleCloseDialog"
      @confirm="dialogVisible.type === 'detail' ? handleCloseDialog() : handleSubmit()"
    >
      <!-- 详情模式 -->
      <template v-if="dialogVisible.type === 'detail'">
        <FaDescriptions
          :column="2"
          :data="detailFormData"
          :items="detailItems"
          label-width="120px"
          max-height="70vh"
        >
          <template #status="{ row }">
            <ElTag :type="statusTagType(String((row as any)?.status ?? 0))" effect="plain">
              {{ statusLabel(String((row as any)?.status ?? 0)) }}
            </ElTag>
          </template>
          <template #scopes="{ row }">
            <div class="flex flex-wrap gap-1">
              <ElTag v-for="s in (row as any)?.scopes || []" :key="s" size="small" type="info">
                {{ s }}
              </ElTag>
              <span v-if="!(row as any)?.scopes?.length" class="text-g-400">无限制</span>
            </div>
          </template>
          <template #token_prefix="{ row }">
            <span class="font-mono text-sm">{{ (row as any)?.token_prefix || '—' }}</span>
          </template>
        </FaDescriptions>
      </template>

      <!-- 表单模式 -->
      <template v-else>
        <FaForm
          :key="formRenderKey"
          ref="dataFormRef"
          v-model="formData"
          :items="formItems"
          :rules="rules"
          label-suffix=":"
          :label-width="100"
          label-position="right"
          :span="24"
          :gutter="16"
          :show-reset="false"
          :show-submit="false"
          class="crud-dialog-art-form"
          scrollbar
          max-height="70vh"
        >
          <template #status>
            <ElSelect v-model="formData.status" placeholder="请选择状态">
              <ElOption :value="0" label="启用" />
              <ElOption :value="1" label="停用" />
            </ElSelect>
          </template>
        </FaForm>
      </template>
    </FaDialog>

    <!-- 查看明文弹窗（二次验证） -->
    <FaDialog
      v-model="revealDialog.visible"
      title="查看 Token 明文"
      width="520px"
      :form-mode="'detail'"
      :confirm-loading="revealLoading"
      @cancel="revealDialog.visible = false"
      @confirm="handleReveal"
    >
      <ElAlert type="warning" :closable="false" class="mb-4" show-icon>
        查看明文需要输入当前登录用户的密码以二次验证身份
      </ElAlert>
      <FaForm
        ref="revealFormRef"
        v-model="revealForm"
        :items="revealFormItems"
        :rules="revealRules"
        label-suffix=":"
        :label-width="80"
        label-position="right"
        :span="24"
        :show-reset="false"
        :show-submit="false"
      >
        <template #password>
          <ElInput
            v-model="revealForm.password"
            type="password"
            placeholder="请输入当前用户密码"
            show-password
            autocomplete="off"
          />
        </template>
      </FaForm>
      <template v-if="revealResult" #extra>
        <ElDivider />
        <div class="space-y-3">
          <div>
            <div class="text-sm text-g-500 mb-1">Token 明文</div>
            <div class="flex items-center gap-2">
              <ElInput
                :model-value="revealResult.token_plain"
                readonly
                class="font-mono"
              />
              <ElButton type="primary" @click="copyTokenPlain">复制</ElButton>
            </div>
          </div>
          <div v-if="revealResult.expires_at" class="text-xs text-g-400">
            过期时间：{{ revealResult.expires_at }}
          </div>
        </div>
      </template>
    </FaDialog>

    <!-- 创建成功弹窗 -->
    <FaDialog
      v-model="createdDialog.visible"
      title="Token 创建成功"
      width="520px"
      :form-mode="'detail'"
      :show-footer="false"
      @cancel="createdDialog.visible = false"
    >
      <ElAlert type="success" :closable="false" class="mb-4" show-icon>
        Token 已创建成功，请立即复制保存。关闭后不再显示完整 Token。
      </ElAlert>
      <div>
        <div class="text-sm text-g-500 mb-1">Token</div>
        <div class="flex items-center gap-2">
          <ElInput
            :model-value="createdDialog.tokenPlain"
            readonly
            class="font-mono"
          />
          <ElButton type="primary" @click="copyCreatedToken">复制</ElButton>
        </div>
      </div>
    </FaDialog>
  </div>
</template>

<script setup lang="ts">
import { useCrudDialog } from "@/hooks/core/useCrudDialog";
import { useTable } from "@/hooks/core/useTable";
import { confirmDelete } from "@/hooks/core/useConfirm";
import { renderTableOperationCell, type TableOperationAction } from "@/utils/table";
import ApiTokenAPI, {
  type ApiTokenTable,
  type ApiTokenCreateForm,
  type ApiTokenRevealSchema,
} from "@/api/module_system/api-token";
import { Plus } from "@element-plus/icons-vue";
import type { ColumnOption } from "@/types/component";
import type { AuditSearchFormParams } from "@/components/forms/fa-search-bar/auditSearchFormItems";
import type { FormItem } from "@/components/forms/fa-form/index.vue";
import { ElMessage } from "element-plus";
import { useClipboard } from "@vueuse/core";

defineOptions({
  name: "ApiToken",
  inheritAttrs: false,
});

// ─── 常量 ───
const TOKEN_STATUS_OPTIONS = [
  { label: "启用", value: 0 },
  { label: "停用", value: 1 },
  { label: "已过期", value: 2 },
] as const;

const TOKEN_STATUS_MAP: Record<string, string> = {
  "0": "启用",
  "1": "停用",
  "2": "已过期",
};

function statusLabel(s: string) {
  return TOKEN_STATUS_MAP[s] || s;
}

function statusTagType(s: string): "success" | "info" | "danger" | undefined {
  return { "0": "success" as const, "1": "info" as const, "2": "danger" as const }[s];
}

const createInitialFormData = (): ApiTokenCreateForm => ({
  id: undefined,
  name: "",
  scopes: [],
  expires_at: undefined,
  rate_limit: undefined,
  description: "",
});

// ─── 搜索 ───
type TokenSearchFormParams = { name?: string; status?: number } & AuditSearchFormParams;

const searchForm = ref<TokenSearchFormParams>({
  name: undefined,
  status: undefined,
});

const showSearchBar = ref(true);

const searchItems = computed(() => [
  {
    label: "名称",
    key: "name",
    type: "input",
    props: { placeholder: "请输入名称", clearable: true },
    span: 6,
  },
  {
    label: "状态",
    key: "status",
    type: "select",
    props: {
      placeholder: "请选择状态",
      options: TOKEN_STATUS_OPTIONS,
      clearable: true,
    },
    span: 6,
  },
]);

// ─── 表格 ───
const {
  columns,
  columnChecks,
  data,
  loading,
  pagination,
  getData,
  replaceSearchParams,
  resetSearchParams,
  handleSizeChange,
  handleCurrentChange,
  refreshData,
  refreshCreate,
  refreshUpdate,
  refreshRemove,
} = useTable({
  core: {
    apiFn: ApiTokenAPI.listToken,
    apiParams: { page_no: 1, page_size: 10, name: undefined, status: undefined },
    columnsFactory: (): ColumnOption<ApiTokenTable>[] => [
      { type: "globalIndex", width: 56, label: "序号" },
      { prop: "name", label: "名称", minWidth: 140, showOverflowTooltip: true },
      {
        prop: "token_prefix",
        label: "前缀",
        minWidth: 120,
        showOverflowTooltip: true,
        formatter: (row: ApiTokenTable) =>
          row.token_prefix ? (
            h("span", { class: "font-mono text-sm" }, row.token_prefix + "***")
          ) : (
            h("span", { class: "text-g-400" }, "—")
          ),
      },
      {
        prop: "status",
        label: "状态",
        width: 90,
        status: {
          0: { type: "success", text: "启用" },
          1: { type: "info", text: "停用" },
          2: { type: "danger", text: "已过期" },
        },
      },
      { prop: "used_count", label: "已用次数", width: 100, align: "center" },
      { prop: "expires_at", label: "过期时间", width: 170, showOverflowTooltip: true },
      { prop: "created_time", label: "创建时间", width: 168, showOverflowTooltip: true },
      {
        prop: "operation",
        label: "操作",
        width: 320,
        fixed: "right",
        align: "center",
        formatter: (row: ApiTokenTable) => renderTokenOperationCell(row),
      },
    ],
  },
});

const faTableRef = ref<{ elTableRef?: { clearSelection: () => void } } | null>(null);

function renderTokenOperationCell(row: ApiTokenTable) {
  return renderTableOperationCell(buildTokenRowActions(row), {
    wrapperClass: "inline-flex flex-wrap items-center justify-end gap-1",
  });
}

function buildTokenRowActions(row: ApiTokenTable): TableOperationAction[] {
  return [
    {
      key: "detail",
      label: "详情",
      artType: "view",
      run: () => void openDetailDialog(row),
    },
    {
      key: "edit",
      label: "编辑",
      artType: "edit",
      run: () => void openEditDialog(row),
    },
    {
      key: "reveal",
      label: "查看明文",
      artType: "more",
      run: () => void openRevealDialog(row),
    },
    {
      key: "status",
      label: "变更状态",
      artType: "more",
      run: () => {},
    },
    {
      key: "delete",
      label: "删除",
      artType: "delete",
      run: () => deleteTokenRow(row),
    },
  ];
}

// ─── 主弹窗 ───
const { dialogVisible } = useCrudDialog();

const detailFormData = ref<ApiTokenTable>({});

const detailItems: import("@/components/others/fa-descriptions/index.vue").DescriptionsItem[] = [
  { label: "名称", prop: "name" },
  { label: "前缀", prop: "token_prefix", slot: "token_prefix" },
  { label: "状态", prop: "status", slot: "status" },
  { label: "权限范围", prop: "scopes", slot: "scopes" },
  { label: "过期时间", prop: "expires_at" },
  { label: "每小时限额", prop: "rate_limit" },
  { label: "已用次数", prop: "used_count" },
  { label: "最近使用", prop: "last_used_at" },
  { label: "描述", prop: "description", span: 2 },
  { label: "创建时间", prop: "created_time" },
  { label: "更新时间", prop: "updated_time" },
];

const formItems: FormItem[] = [
  {
    key: "name",
    label: "名称",
    type: "input",
    span: 12,
    props: { placeholder: "请输入 Token 名称", maxlength: 100 },
  },
  {
    key: "expires_at",
    label: "过期时间",
    type: "date",
    span: 12,
    props: { placeholder: "留空=永不过期", valueFormat: "YYYY-MM-DD HH:mm:ss" },
  },
  {
    key: "rate_limit",
    label: "每小时限额",
    type: "number",
    span: 12,
    props: { placeholder: "留空=不限", controlsPosition: "right", min: 0, max: 100000 },
  },
  {
    key: "status",
    label: "状态",
    type: "select",
    span: 12,
    props: { placeholder: "请选择状态" },
  },
  {
    key: "description",
    label: "描述",
    type: "input",
    span: 24,
    props: { type: "textarea", rows: 3, placeholder: "请输入描述" },
  },
];

const formData = ref<ApiTokenCreateForm>(createInitialFormData());

const rules = reactive({
  name: [{ required: true, message: "请输入名称", trigger: "blur" }],
});

const dataFormRef = ref<{
  resetFields: () => void;
  clearValidate: () => void;
  validate: (cb: (valid: boolean) => void) => void;
} | null>(null);

const submitLoading = ref(false);
const formRenderKey = ref(0);

// ─── 查看明文弹窗 ───
const revealDialog = reactive({ visible: false, row: null as ApiTokenTable | null });
const revealLoading = ref(false);
const revealForm = reactive({ password: "" });
const revealResult = ref<ApiTokenRevealSchema | null>(null);
const revealFormRef = ref<{
  resetFields: () => void;
  clearValidate: () => void;
  validate: (cb: (valid: boolean) => void) => void;
} | null>(null);

const revealFormItems: FormItem[] = [
  {
    key: "password",
    label: "登录密码",
    type: "input",
    span: 24,
  },
];

const revealRules = reactive({
  password: [{ required: true, message: "请输入当前用户密码", trigger: "blur" }],
});

// ─── 创建成功弹窗 ───
const createdDialog = reactive({ visible: false, tokenPlain: "" });

// ─── 搜索事件 ───
const handleSearch = async (params: TokenSearchFormParams) => {
  replaceSearchParams({
    name: params.name ?? undefined,
    status: params.status ?? undefined,
  } as Record<string, unknown>);
  getData();
};

const onResetSearch = async () => {
  searchForm.value = { name: undefined, status: undefined };
  await resetSearchParams();
};

// ─── 主弹窗事件 ───
async function openDetailDialog(row: ApiTokenTable) {
  if (!row.id) return;
  const response = await ApiTokenAPI.detailToken(row.id);
  dialogVisible.type = "detail";
  dialogVisible.title = "Token 详情";
  detailFormData.value = response.data.data ?? { ...row };
  dialogVisible.visible = true;
}

async function handleAdd() {
  await openEditDialog();
}

async function openEditDialog(row?: ApiTokenTable) {
  dialogVisible.type = row ? "update" : "create";
  dialogVisible.title = row ? "编辑 Token" : "新增 Token";
  formRenderKey.value += 1;
  if (row) {
    const response = await ApiTokenAPI.detailToken(row.id!);
    const data = response.data.data ?? {};
    Object.assign(formData.value, data);
  } else {
    Object.assign(formData.value, createInitialFormData());
  }
  dialogVisible.visible = true;
}

async function resetForm() {
  if (dataFormRef.value) {
    dataFormRef.value.resetFields();
    dataFormRef.value.clearValidate();
  }
  Object.assign(formData.value, createInitialFormData());
}

async function handleCloseDialog() {
  dialogVisible.visible = false;
  await resetForm();
}

async function handleSubmit() {
  dataFormRef.value?.validate(async (valid: boolean) => {
    if (!valid) return;
    const id = formData.value.id;
    try {
      if (id) {
        // 编辑模式：调用 reset API 更新基本信息
        const res = await ApiTokenAPI.resetToken(id, {
          name: formData.value.name,
          description: formData.value.description,
        });
        dialogVisible.visible = false;
        await resetForm();
        await refreshUpdate();
        // 如果 reset 也返回了新 token，展示创建成功弹窗
        if (res.data.data?.token_plain) {
          createdDialog.tokenPlain = res.data.data.token_plain;
          createdDialog.visible = true;
        }
      } else {
        // 新增模式
        const res = await ApiTokenAPI.createToken(formData.value);
        dialogVisible.visible = false;
        await resetForm();
        await refreshCreate();
        const created = res.data.data;
        if (created?.token_plain) {
          createdDialog.tokenPlain = created.token_plain;
          createdDialog.visible = true;
        }
      }
    } catch (error: unknown) {
      console.error(error);
    }
  });
}

// ─── 删除事件 ───
const deleteTokenRow = async (row: ApiTokenTable) => {
  if (!row.id) return;
  try {
    await confirmDelete(`确定删除 Token「${row.name ?? row.id}」吗？此操作不可恢复！`);
    await ApiTokenAPI.deleteToken(row.id!);
    faTableRef.value?.elTableRef?.clearSelection();
    await refreshRemove();
  } catch {
    // 用户取消
  }
};

// ─── 查看明文事件 ───
async function openRevealDialog(row: ApiTokenTable) {
  revealDialog.row = row;
  revealForm.password = "";
  revealResult.value = null;
  revealDialog.visible = true;
}

async function handleReveal() {
  revealFormRef.value?.validate(async (valid: boolean) => {
    if (!valid || !revealDialog.row?.id) return;
    revealLoading.value = true;
    try {
      const res = await ApiTokenAPI.revealToken(revealDialog.row.id, {
        password: revealForm.password,
      });
      revealResult.value = res.data.data ?? null;
    } catch {
      // 错误由全局拦截处理
    } finally {
      revealLoading.value = false;
    }
  });
}

const { copy } = useClipboard();

function copyTokenPlain() {
  if (revealResult.value?.token_plain) {
    copy(revealResult.value.token_plain);
    ElMessage.success("已复制到剪贴板");
  }
}

function copyCreatedToken() {
  if (createdDialog.tokenPlain) {
    copy(createdDialog.tokenPlain);
    ElMessage.success("已复制到剪贴板");
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
</style>
