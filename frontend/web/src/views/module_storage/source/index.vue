<!-- 存储源管理：存储源 CRUD + 连接测试 -->
<template>
  <div class="fa-full-height">
    <FaSearchBar
      v-show="showSearchBar"
      ref="searchBarRef"
      v-model="searchForm"
      :items="sourceSearchItems"
      :rules="searchBarRules"
      :is-expand="false"
      :show-expand="true"
      :show-reset="true"
      :show-search="true"
      :default-expanded="false"
      include-audit
      @search="handleSearchBarSearch"
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
          <FaTableHeaderLeft
            :remove-ids="selectedIds"
            :perm-create="['module_storage:source:create']"
            :perm-delete="['module_storage:source:delete']"
            :delete-loading="batchDeleting"
            :create-loading="createLoading"
            @add="handleAdd"
            @delete="handleBatchDelete"
          />
        </template>
      </FaTableHeader>

      <FaTable
        ref="faTableRef"
        :loading="loading"
        :data="data"
        :columns="columns"
        :pagination="pagination"
        @selection-change="onTableSelectionChange"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      />
    </ElCard>

    <FaDialog
      v-model="dialogVisible.visible"
      :title="dialogVisible.title"
      width="720px"
      dialog-class="crud-embed-dialog"
      modal-class="crud-embed-dialog"
      :form-mode="dialogVisible.type"
      :confirm-loading="submitLoading"
      @cancel="handleCloseDialog"
      @confirm="dialogVisible.type === 'detail' ? handleCloseDialog() : handleSubmit()"
    >
      <template v-if="dialogVisible.type === 'detail'">
        <FaDescriptions :column="2" :data="detailFormData" :items="sourceDetailItems" max-height="70vh">
          <template #protocol="{ row }">
            <span>{{ protocolLabel((row as unknown as SourceTable)?.protocol) }}</span>
          </template>
        <template #is_default="{ row }">
            <FaStatusTag v-if="row?.is_default" type="success" label="默认" />
            <FaStatusTag v-else type="info" label="否" />
          </template>
          <template #is_secure="{ row }">
            <span>{{ row?.is_secure ? "是" : "否" }}</span>
          </template>
          <template #has_password="{ row }">
            <span>{{ row?.has_password ? "已配置" : "未配置" }}</span>
          </template>
        </FaDescriptions>
      </template>
      <template v-else>
        <FaForm
          :key="sourceFormRenderKey"
          scrollbar
          max-height="70vh"
          ref="dataFormRef"
          v-model="formData"
          :items="sourceDialogFormItems"
          :rules="rules"
          label-suffix=":"
          :label-width="110"
          label-position="right"
          :span="24"
          :gutter="16"
          :show-reset="false"
          :show-submit="false"
          class="crud-dialog-art-form"
        />
      </template>
      <template #footer>
        <div v-if="dialogVisible.type === 'detail'" class="fa-dialog-footer" style="padding-right: var(--el-dialog-padding-primary)">
          <ElButton type="primary" @click="handleCloseDialog">关闭</ElButton>
        </div>
        <div v-else class="fa-dialog-footer" style="padding-right: var(--el-dialog-padding-primary)">
          <ElButton :loading="testing" style="margin-right: auto" @click="handleTestConfig">测试连接</ElButton>
          <ElButton type="primary" plain @click="handleCloseDialog">取消</ElButton>
          <ElButton type="primary" :loading="submitLoading" @click="handleSubmit">确定</ElButton>
        </div>
      </template>
    </FaDialog>
  </div>
</template>

<script setup lang="ts">
import { useCrudForm } from "@/hooks/core/useCrudForm";
import { resolveStatusColumns, renderTableOperationCell, type TableOperationAction } from "@utils";
import SourceAPI, { type SourceForm, type SourceTable } from "@/api/module_storage/source";
import type { SearchFormItem } from "@/components/forms/fa-search-bar/index.vue";
import type FaSearchBar from "@/components/forms/fa-search-bar/index.vue";
import type { FormItem } from "@/components/forms/fa-form/index.vue";
import FaForm from "@/components/forms/fa-form/index.vue";
import FaDescriptions from "@/components/display/fa-descriptions/index.vue";
import FaTableHeader from "@/components/tables/fa-table-header/index.vue";

defineOptions({
  name: "StorageSource",
  inheritAttrs: false,
});

const PROTOCOL_OPTIONS = [
  { label: "FTP", value: "ftp" },
  { label: "FTPS", value: "ftps" },
  { label: "SFTP", value: "sftp" },
  { label: "S3", value: "s3" },
  { label: "OBS(华为云)", value: "obs" },
  { label: "OSS(阿里云)", value: "oss" },
  { label: "COS(腾讯云)", value: "cos" },
  { label: "本地目录", value: "local" },
] as const;

const STATUS_OPTIONS = [
  { label: "启用", value: 0 },
  { label: "停用", value: 1 },
] as const;

type SourceSearchForm = {
  name?: string;
  protocol?: string;
  status?: number;
  created_id?: number;
  updated_id?: number;
  created_time?: string[];
  updated_time?: string[];
};

function buildSourceReplaceParams(p: SourceSearchForm): Record<string, unknown> {
  return {
    name: p.name,
    protocol: p.protocol,
    status: p.status,
    created_id: p.created_id,
    updated_id: p.updated_id,
    created_time:
      Array.isArray(p.created_time) && p.created_time.length === 2 ? p.created_time : undefined,
    updated_time:
      Array.isArray(p.updated_time) && p.updated_time.length === 2 ? p.updated_time : undefined,
  };
}

function protocolLabel(value?: string): string {
  const opt = PROTOCOL_OPTIONS.find((o) => o.value === value);
  return opt ? opt.label : (value ?? "-");
}

function buildSourceRowActions(
  row: SourceTable,
  ctx: {
    onTest: (id: number) => void;
    onDetail: (id: number) => void;
    onEdit: (id: number) => void;
    onDelete: (id: number, name: string) => void;
  }
): TableOperationAction[] {
  return [
    {
      key: "test",
      label: "测试连接",
      artType: "view",
      icon: "ri:link",
      iconColor: "var(--el-color-primary)",
      perm: "module_storage:source:query",
      run: () => ctx.onTest(row.id!),
    },
    {
      key: "detail",
      label: "详情",
      artType: "view",
      perm: "module_storage:source:query",
      run: () => ctx.onDetail(row.id!),
    },
    {
      key: "edit",
      label: "编辑",
      artType: "edit",
      icon: "ri:edit-2-line",
      perm: "module_storage:source:update",
      run: () => ctx.onEdit(row.id!),
    },
    {
      key: "delete",
      label: "删除",
      artType: "delete",
      icon: "ri:delete-bin-4-line",
      perm: "module_storage:source:delete",
      run: () => ctx.onDelete(row.id!, row.name ?? ""),
    },
  ];
}

function formatSourceOperationCell(row: SourceTable, ctx: Parameters<typeof buildSourceRowActions>[1]) {
  return renderTableOperationCell(buildSourceRowActions(row, ctx), {
    wrapperClass: "inline-flex flex-wrap items-center justify-end gap-1 source-table-actions",
  });
}

const searchForm = ref<SourceSearchForm>({
  name: undefined,
  protocol: undefined,
  status: undefined,
  created_id: undefined,
  updated_id: undefined,
  created_time: undefined,
  updated_time: undefined,
});

const showSearchBar = ref(true);
const searchBarRef = ref<InstanceType<typeof FaSearchBar> | null>(null);
const searchBarRules: Record<string, unknown> = {};

const sourceSearchItems = computed<SearchFormItem[]>(() => [
  {
    label: "存储名称",
    key: "name",
    type: "input",
    placeholder: "请输入存储名称",
    clearable: true,
    span: 6,
  },
  {
    label: "协议",
    key: "protocol",
    type: "select",
    props: {
      placeholder: "请选择协议",
      options: PROTOCOL_OPTIONS,
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
      options: STATUS_OPTIONS,
      clearable: true,
    },
    span: 6,
  },
]);

const faTableRef = ref<{ elTableRef?: { clearSelection: () => void } } | null>(null);

// ─── 表格多选 ───
const { selectedRows, selectedIds, batchDeleting, onTableSelectionChange } =
  useTableSelection<SourceTable>();

const createLoading = ref(false);

async function deleteSourceRow(id: number, name: string) {
  try {
    await confirmDelete(`确定删除「${name}」吗？`);
    await SourceAPI.deleteSource([id]);
    faTableRef.value?.elTableRef?.clearSelection();
    await refreshRemove();
  } catch {
    // 用户取消
  }
}

async function handleTest(id: number) {
  await SourceAPI.testSource(id);
}

const testing = ref(false);

async function handleTestConfig() {
  try {
    await dataFormRef.value?.validate?.();
  } catch {
    return; // 表单校验不通过时不发起测试
  }
  testing.value = true;
  try {
    await SourceAPI.testSourceConfig({ ...formData.value, source_id: formData.value.id });
  } catch {
    // 失败原因由全局拦截器提示
  } finally {
    testing.value = false;
  }
}

// ─── 对话框状态 ───
const { dialogVisible } = useCrudDialog();

const detailFormData = ref<SourceTable>({} as SourceTable);

const sourceDetailItems: import("@/components/display/fa-descriptions/index.vue").DescriptionsItem[] =
  [
    { label: "存储源名称", prop: "name" },
    { label: "协议", prop: "protocol", slot: "protocol" },
    { label: "主机地址", prop: "host" },
    { label: "端口", prop: "port" },
    { label: "用户名", prop: "username" },
    { label: "密码", prop: "has_password", slot: "has_password" },
    { label: "Bucket", prop: "bucket" },
    { label: "接入点", prop: "endpoint" },
    { label: "区域", prop: "region" },
    { label: "路径前缀", prop: "path_prefix" },
    { label: "TLS(FTPS)", prop: "is_secure", slot: "is_secure" },
    { label: "默认存储源", prop: "is_default", slot: "is_default" },
    { label: "状态", prop: "status", tag: { map: { 0: { type: "success", text: "启用" }, 1: { type: "danger", text: "停用" } } } },
    { label: "备注", prop: "description" },
    { label: "创建时间", prop: "created_time" },
    { label: "更新时间", prop: "updated_time" },
  ];

const initialFormData: SourceForm = {
  id: undefined,
  name: undefined,
  protocol: "ftp",
  host: undefined,
  port: undefined,
  username: undefined,
  password: undefined,
  bucket: undefined,
  endpoint: undefined,
  region: undefined,
  path_prefix: undefined,
  is_secure: false,
  implicit_tls: false,
  is_default: false,
  status: 0,
  description: undefined,
};

const formData = ref<SourceForm>({ ...initialFormData });

const rules = reactive({
  name: [{ required: true, message: "请输入存储源名称", trigger: "blur" }],
  host: [{ required: true, message: "请输入主机地址/根目录", trigger: "blur" }],
});

const dataFormRef = ref<InstanceType<typeof FaForm> | null>(null);
const sourceFormRenderKey = ref(0);

// ─── CRUD 表单 ───
const { submitLoading, handleCloseDialog, handleOpenDialog, handleSubmit } = useCrudForm<SourceForm>({
  formData,
  initialFormData,
  dialogVisible,
  dataFormRef,
  formRenderKey: sourceFormRenderKey,
  detailApi: SourceAPI.detailSource,
  createApi: SourceAPI.createSource,
  updateApi: SourceAPI.updateSource,
  titles: { create: "新增存储源", update: "修改存储源", detail: "存储源详情" },
  detailFormData,
  onCreateSuccess: async () => {
    await refreshCreate();
  },
  onUpdateSuccess: async () => {
    await refreshUpdate();
  },
});

async function handleAdd() {
  createLoading.value = true;
  try {
    await handleOpenDialog("create");
  } finally {
    createLoading.value = false;
  }
}

const opCtx = {
  onTest: handleTest,
  onDetail: (id: number) => void handleOpenDialog("detail", id),
  onEdit: (id: number) => void handleOpenDialog("update", id),
  onDelete: deleteSourceRow,
};
const sourceDialogFormItems = computed<FormItem[]>(() => [
  {
    label: "存储源名称",
    key: "name",
    type: "input",
    span: 24,
    props: { placeholder: "请输入存储源名称", maxlength: 64, showWordLimit: true },
  },
  {
    label: "协议",
    key: "protocol",
    type: "select",
    span: 12,
    props: { placeholder: "请选择协议", options: PROTOCOL_OPTIONS },
  },
  {
    label: "主机地址",
    key: "host",
    type: "input",
    span: 12,
    props: { placeholder: "IP / 域名 / 根目录", maxlength: 255 },
  },
  {
    label: "端口",
    key: "port",
    type: "number",
    span: 12,
    props: { controlsPosition: "right", min: 0, max: 65535, placeholder: "留空使用协议默认端口" },
  },
  {
    label: "用户名",
    key: "username",
    type: "input",
    span: 12,
    props: { placeholder: "用户名 / AccessKey", maxlength: 255 },
  },
  {
    label: "密码",
    key: "password",
    type: "input",
    span: 12,
    props: { type: "password", showPassword: true, placeholder: "密码 / SecretKey(修改时留空则不修改)" },
  },
  {
    label: "Bucket",
    key: "bucket",
    type: "input",
    span: 12,
    props: { placeholder: "桶名 / 空间名 / 根目录", maxlength: 255 },
  },
  {
    label: "接入点",
    key: "endpoint",
    type: "input",
    span: 12,
    props: { placeholder: "对象存储接入点(可选)", maxlength: 255 },
  },
  {
    label: "区域",
    key: "region",
    type: "input",
    span: 12,
    props: { placeholder: "区域(可选)", maxlength: 64 },
  },
  {
    label: "路径前缀",
    key: "path_prefix",
    type: "input",
    span: 12,
    props: { placeholder: "统一路径前缀(可选)", maxlength: 255 },
  },
  {
    label: "TLS(FTPS)",
    key: "is_secure",
    type: "switch",
    span: 12,
  },
  {
    label: "默认存储源",
    key: "is_default",
    type: "switch",
    span: 12,
  },
  {
    label: "状态",
    key: "status",
    type: "radiogroup",
    span: 12,
  },
  {
    label: "备注",
    key: "description",
    type: "input",
    span: 24,
    props: { type: "textarea", rows: 3, maxlength: 255, showWordLimit: true, placeholder: "请输入备注" },
  },
]);

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
    apiFn: SourceAPI.pageSource,
    apiParams: {
      page_no: 1,
      page_size: 10,
    },
    columnsFactory: resolveStatusColumns<SourceTable>(() => [
      { type: "selection", width: 48, fixed: "left" },
      { type: "globalIndex", width: 56, label: "序号" },
      { prop: "name", label: "存储源名称", minWidth: 140, showOverflowTooltip: true },
      {
        prop: "protocol",
        label: "协议",
        width: 110,
        formatter: (row: SourceTable) => protocolLabel(row.protocol),
      },
      { prop: "host", label: "主机地址", minWidth: 140, showOverflowTooltip: true },
      { prop: "port", label: "端口", width: 80 },
      { prop: "bucket", label: "Bucket", minWidth: 110, showOverflowTooltip: true },
      {
        prop: "is_default",
        label: "默认",
        width: 80,
        formatter: (row: SourceTable) => (row.is_default ? "是" : "否"),
      },
      {
        prop: "status",
        label: "状态",
        width: 80,
        status: {
          0: { type: "success", text: "启用" },
          1: { type: "danger", text: "停用" },
        },
      },
      { prop: "description", label: "备注", minWidth: 120, showOverflowTooltip: true },
      {
        prop: "created_time",
        label: "创建时间",
        width: 168,
        sortable: true,
        showOverflowTooltip: true,
      },
      {
        prop: "operation",
        label: "操作",
        width: 220,
        fixed: "right",
        align: "center",
        formatter: (row: SourceTable) => formatSourceOperationCell(row, opCtx),
      },
    ]),
  },
});

async function handleSearchBarSearch(params: SourceSearchForm) {
  await searchBarRef.value?.validate?.();
  replaceSearchParams(buildSourceReplaceParams(params));
  await getData();
}

async function onResetSearch() {
  searchForm.value = {
    name: undefined,
    protocol: undefined,
    status: undefined,
    created_id: undefined,
    updated_id: undefined,
    created_time: undefined,
    updated_time: undefined,
  };
  await resetSearchParams();
}

async function handleBatchDelete() {
  const ids = selectedIds.value;
  if (ids.length === 0) return;
  try {
    await confirmBatchDelete(
      ids.length,
      selectedRows.value.map((r) => String(r.name ?? r.id))
    );
    batchDeleting.value = true;
    await SourceAPI.deleteSource(ids);
    faTableRef.value?.elTableRef?.clearSelection();
    await refreshRemove();
  } catch {
    // 用户取消
  } finally {
    batchDeleting.value = false;
  }
}
</script>
