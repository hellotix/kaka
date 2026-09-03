<!-- 文件管理：存储源文件浏览/上传/下载/删除 -->
<template>
  <div class="fa-full-height flex flex-col gap-3">
    <ElCard class="fa-table-card" shadow="never">
      <div class="flex flex-wrap items-center gap-3">
        <ElSelect
          v-model="sourceId"
          :placeholder="'默认存储源'"
          style="width: 240px"
          clearable
          filterable
          @change="handleSourceChange"
        >
          <ElOption v-for="s in sourceOptions" :key="s.id" :label="s.name" :value="s.id!" />
        </ElSelect>
        <ElInput v-model="keyword" placeholder="搜索文件名" clearable style="width: 220px">
          <template #prefix>
            <ElIcon><Search /></ElIcon>
          </template>
        </ElInput>
        <ElSelect v-model="typeFilter" style="width: 110px">
          <ElOption label="全部" value="all" />
          <ElOption label="文件" value="file" />
          <ElOption label="目录" value="dir" />
        </ElSelect>
        <div class="flex-1" />
        <ElButton type="primary" :icon="UploadFilled" :disabled="uploading" @click="uploadVisible = true">
          上传文件
        </ElButton>
        <ElButton :icon="Refresh" :loading="loading" @click="loadFiles">刷新</ElButton>
      </div>
    </ElCard>

    <ElCard class="fa-table-card" shadow="never">
      <div class="flex flex-wrap items-center gap-1 text-sm">
        <ElButton text :type="prefix ? '' : 'primary'" @click="goRoot">根目录</ElButton>
        <template v-for="(seg, idx) in pathSegments" :key="idx">
          <span class="text-(--el-text-color-placeholder)">/</span>
          <ElButton
            text
            :type="idx === pathSegments.length - 1 ? 'primary' : ''"
            @click="goPath(idx)"
          >
            {{ seg }}
          </ElButton>
        </template>
      </div>
    </ElCard>

    <ElCard class="fa-table-card flex-1 min-h-0">
      <FaTable :loading="loading" :data="filteredData" :columns="columns" />
    </ElCard>

    <ElDialog
      v-model="uploadVisible"
      title="上传文件"
      width="520px"
      :close-on-click-modal="false"
    >
      <ElUpload
        ref="uploadRef"
        drag
        multiple
        :show-file-list="true"
        :http-request="handleUploadRequest"
      >
        <ElIcon class="el-icon--upload"><UploadFilled /></ElIcon>
        <div class="el-upload__text">将文件拖到此处，或<em>点击上传</em></div>
        <template #tip>
          <div class="el-upload__tip">支持多个文件，上传到当前目录（{{ prefix || "根目录" }}）</div>
        </template>
      </ElUpload>
      <template #footer>
        <ElButton @click="uploadVisible = false">关闭</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
import { h } from "vue";
import { Document, Folder, Refresh, Search, UploadFilled } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox, type UploadRequestOptions } from "element-plus";
import { renderTableOperationCell, type TableOperationAction } from "@utils";
import type { ColumnOption } from "@/types/component";
import FileAPI, { type StorageObject } from "@/api/module_storage/file";
import SourceAPI, { type SourceTable } from "@/api/module_storage/source";

defineOptions({
  name: "StorageFile",
  inheritAttrs: false,
});

const sourceId = ref<number | undefined>(undefined);
const sourceOptions = ref<SourceTable[]>([]);
const prefix = ref("");
const data = ref<StorageObject[]>([]);
const loading = ref(false);

const keyword = ref("");
const typeFilter = ref<"all" | "file" | "dir">("all");

const uploadVisible = ref(false);
const pendingUploads = ref(0);
const uploading = computed(() => pendingUploads.value > 0);
const uploadRef = ref<{ clearFiles: () => void } | null>(null);

const pathSegments = computed(() => prefix.value.split("/").filter(Boolean));

/** 本地过滤：按名称关键字 + 文件/目录类型 */
const filteredData = computed(() => {
  const kw = keyword.value.trim().toLowerCase();
  return data.value.filter((item) => {
    if (typeFilter.value === "file" && item.is_dir) return false;
    if (typeFilter.value === "dir" && !item.is_dir) return false;
    if (kw && !(item.name ?? "").toLowerCase().includes(kw)) return false;
    return true;
  });
});

async function loadSources() {
  try {
    const res = await SourceAPI.listSource({ status: 0 });
    sourceOptions.value = res.data?.data ?? [];
  } catch {
    // 无存储源查询权限时忽略
  }
}

async function loadFiles() {
  loading.value = true;
  try {
    const res = await FileAPI.listFiles({ source_id: sourceId.value, prefix: prefix.value });
    data.value = res.data?.data ?? [];
  } finally {
    loading.value = false;
  }
}

function handleSourceChange() {
  prefix.value = "";
  void loadFiles();
}

function openDir(item: StorageObject) {
  prefix.value = item.key ?? "";
  void loadFiles();
}

function goRoot() {
  prefix.value = "";
  void loadFiles();
}

function goPath(index: number) {
  prefix.value = pathSegments.value.slice(0, index + 1).join("/");
  void loadFiles();
}

function formatSize(size?: number): string {
  if (size === undefined || size === null) return "-";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(2)} MB`;
}

function nameCell(row: StorageObject) {
  return h("span", { class: "inline-flex items-center gap-1.5 min-w-0" }, [
    h(row.is_dir ? Folder : Document, {
      style: {
        color: row.is_dir ? "var(--el-color-warning)" : "var(--el-color-primary)",
        flexShrink: 0,
      },
    }),
    h("span", { class: "truncate" }, row.name ?? ""),
  ]);
}

function buildActions(row: StorageObject): TableOperationAction[] {
  if (row.is_dir) {
    return [
      {
        key: "open",
        label: "打开",
        artType: "view",
        icon: "ri:folder-open-line",
        iconColor: "var(--el-color-warning)",
        perm: "module_storage:file:query",
        run: () => openDir(row),
      },
      {
        key: "delete",
        label: "删除",
        artType: "delete",
        icon: "ri:delete-bin-4-line",
        perm: "module_storage:file:delete",
        run: () => void deleteItem(row),
      },
    ];
  }
  return [
    {
      key: "download",
      label: "下载",
      artType: "view",
      icon: "ri:download-2-line",
      iconColor: "var(--el-color-primary)",
      perm: "module_storage:file:download",
      run: () => void downloadItem(row),
    },
    {
      key: "url",
      label: "获取链接",
      artType: "view",
      icon: "ri:link",
      perm: "module_storage:file:query",
      run: () => void getFileUrl(row),
    },
    {
      key: "delete",
      label: "删除",
      artType: "delete",
      icon: "ri:delete-bin-4-line",
      perm: "module_storage:file:delete",
      run: () => void deleteItem(row),
    },
  ];
}

function formatOperationCell(row: StorageObject) {
  return renderTableOperationCell(buildActions(row), {
    wrapperClass: "inline-flex flex-wrap items-center justify-end gap-1 file-table-actions",
  });
}

const columns = computed<ColumnOption<StorageObject>[]>(() => [
  { type: "globalIndex", width: 56, label: "序号" },
  { prop: "name", label: "名称", minWidth: 300, showOverflowTooltip: true, formatter: nameCell },
  {
    prop: "is_dir",
    label: "类型",
    width: 90,
    formatter: (row: StorageObject) => (row.is_dir ? "目录" : "文件"),
  },
  {
    prop: "size",
    label: "大小",
    width: 110,
    formatter: (row: StorageObject) => formatSize(row.size),
  },
  { prop: "modified_time", label: "修改时间", width: 180, showOverflowTooltip: true },
  {
    prop: "operation",
    label: "操作",
    width: 200,
    fixed: "right",
    align: "center",
    formatter: (row: StorageObject) => formatOperationCell(row),
  },
]);

async function handleUploadRequest(options: UploadRequestOptions) {
  pendingUploads.value += 1;
  let batchFailed = false;
  try {
    const fd = new FormData();
    fd.append("file", options.file);
    if (sourceId.value) fd.append("source_id", String(sourceId.value));
    if (prefix.value) fd.append("remote_path", prefix.value);
    await FileAPI.uploadFile(fd);
    void loadFiles();
    options.onSuccess({});
  } catch (error) {
    batchFailed = true;
    const errObj = error instanceof Error ? error : new Error(String(error));
    options.onError({
      ...errObj,
      status: 0,
      method: "POST",
      url: "/storage/file/upload",
    });
  } finally {
    pendingUploads.value -= 1;
    if (pendingUploads.value === 0 && !batchFailed) {
      uploadRef.value?.clearFiles();
      uploadVisible.value = false;
    }
  }
}

async function downloadItem(item: StorageObject) {
  try {
    const response = await FileAPI.downloadFile({ remote_path: item.key ?? "", source_id: sourceId.value });
    const blob = response.data;
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = item.name ?? "download";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  } catch {
    // 失败提示由全局拦截器处理
  }
}

async function getFileUrl(item: StorageObject) {
  try {
    const res = await FileAPI.getFileUrl({
      remote_path: item.key ?? "",
      source_id: sourceId.value,
      expire: 3600,
    });
    const url = res.data?.data;
    if (!url) {
      ElMessage.warning("当前存储源不支持获取访问 URL");
      return;
    }
    await ElMessageBox.alert(url, "文件访问 URL", {
      confirmButtonText: "复制",
      showCancelButton: false,
    });
    await navigator.clipboard.writeText(url).catch(() => undefined);
    ElMessage.success("已复制到剪贴板");
  } catch {
    // 失败提示由全局拦截器处理
  }
}

async function deleteItem(item: StorageObject) {
  try {
    await ElMessageBox.confirm(
      item.is_dir ? `确定删除目录「${item.name}」及其全部内容吗？` : `确定删除文件「${item.name}」吗？`,
      "确认删除",
      {
        confirmButtonText: "确定",
        cancelButtonText: "取消",
        type: "warning",
      }
    );
    await FileAPI.deleteFile({ remote_path: item.key ?? "", source_id: sourceId.value });
    void loadFiles();
  } catch {
    // 用户取消或失败（失败提示由全局拦截器处理）
  }
}

onMounted(() => {
  void loadSources();
  void loadFiles();
});
</script>
