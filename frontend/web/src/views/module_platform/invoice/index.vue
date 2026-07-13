<template>
  <div class="fa-full-height">
    <ElCard class="fa-table-card" :style="{ 'margin-top': '0' }">
      <FaTableHeader :loading="loading" @refresh="getData">
        <template #left>
          <FaTableHeaderLeft
            perm-create="tenant:admin"
            :create-loading="createLoading"
            @add="handleAdd"
          />
        </template>
      </FaTableHeader>

      <FaTable
        ref="tableRef"
        :loading="loading"
        :data="tableData"
        :columns="columns"
        :pagination="pagination"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      />
    </ElCard>

    <!-- 申请开票弹窗 -->
    <FaDialog v-model="applyDialogVisible" title="申请开票" width="520px">
      <FaForm
        ref="applyFormRef"
        v-model="applyFormData"
        :items="applyFormItems"
        :rules="applyRules"
        :show-footer="false"
      />
      <template #footer>
        <ElButton @click="applyDialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="applySubmitting" @click="submitApply">提交申请</ElButton>
      </template>
    </FaDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
import { ElButton } from "element-plus";
import { useTable } from "@/hooks/core/useTable";
import InvoiceAPI from "@/api/module_platform/invoice";
import type { InvoiceTable } from "@/api/module_platform/invoice";
import type { FormItem } from "@/components/forms/fa-form/index.vue";
import { resolveStatusColumns } from "@utils";

defineOptions({ name: "Invoice" });

const {
  columns,
  data: tableData,
  loading,
  pagination,
  getData,
  handleSizeChange,
  handleCurrentChange,
} = useTable({
  core: {
    apiFn: InvoiceAPI.tenantListInvoices,
    apiParams: {
      page_no: 1,
      page_size: 50,
    },
    columnsFactory: resolveStatusColumns<InvoiceTable>(() => [
      { prop: "invoice_no", label: "发票号", width: 180, showOverflowTooltip: true },
      { prop: "title", label: "抬头", minWidth: 180, showOverflowTooltip: true },
      {
        prop: "invoice_type",
        label: "类型",
        width: 110,
        formatter: (row) => row.invoice_type || "—",
      },
      {
        prop: "amount",
        label: "金额",
        width: 120,
        formatter: (row) => `¥${((row.amount || 0) / 100).toFixed(2)}`,
      },
      {
        prop: "status",
        label: "状态",
        width: 100,
        status: {
          0: { type: "warning", text: "待开具" },
          1: { type: "success", text: "已开具" },
          2: { type: "danger", text: "开票失败" },
          3: { type: "info", text: "已作废" },
        },
      },
      {
        prop: "created_time",
        label: "申请时间",
        width: 160,
        showOverflowTooltip: true,
        formatter: (row) => row.created_time || "—",
      },
    ]),
  },
});

// ══════════════════ 申请开票弹窗 ════════════════════

const applyDialogVisible = ref(false);
const applySubmitting = ref(false);
const applyFormRef = ref();
let applyFormData = reactive({
  order_id: null as number | null,
  title: "",
  invoice_type: "vat_normal",
  tax_no: "",
  address_info: "",
  bank_info: "",
});

const applyFormItems: FormItem[] = [
  {
    label: "关联订单ID",
    key: "order_id",
    type: "inputNumber",
    span: 24,
    props: { min: 1, placeholder: "输入已支付订单ID" },
  },
  {
    label: "发票抬头",
    key: "title",
    type: "input",
    span: 24,
    props: { placeholder: "公司全称或个人姓名", maxlength: 100 },
  },
  {
    label: "发票类型",
    key: "invoice_type",
    type: "select",
    span: 24,
    props: {
      options: [
        { label: "普通发票", value: "vat_normal" },
        { label: "增值税专用发票", value: "vat_special" },
      ],
    },
  },
  {
    label: "税号",
    key: "tax_no",
    type: "input",
    span: 24,
    props: { placeholder: "统一社会信用代码（可选）", maxlength: 30 },
  },
  {
    label: "银行信息",
    key: "bank_info",
    type: "input",
    span: 24,
    props: { placeholder: "开户行及账号（可选）", maxlength: 100 },
  },
  {
    label: "地址电话",
    key: "address_info",
    type: "input",
    span: 24,
    props: { placeholder: "注册地址及电话（专票必填）", maxlength: 200 },
  },
];

const applyRules = {
  order_id: [{ required: true, message: "请输入订单ID", trigger: "blur" }],
  title: [{ required: true, message: "请输入发票抬头", trigger: "blur" }],
};

const createLoading = ref(false);

async function handleAdd() {
  createLoading.value = true;
  try {
    openApplyDialog();
  } finally {
    createLoading.value = false;
  }
}

function openApplyDialog() {
  Object.assign(applyFormData, {
    order_id: null,
    title: "",
    invoice_type: "vat_normal",
    tax_no: "",
    address_info: "",
    bank_info: "",
  });
  applyFormRef.value?.resetFields?.();
  applyDialogVisible.value = true;
}

async function submitApply() {
  const form: any = applyFormRef.value;
  if (!form) return;
  const valid = await form.validate().catch(() => false);
  if (!valid) return;
  applySubmitting.value = true;
  try {
    await InvoiceAPI.applyInvoice({
      order_id: applyFormData.order_id!,
      title: applyFormData.title,
      invoice_type: applyFormData.invoice_type,
      tax_no: applyFormData.tax_no || undefined,
      address_info: applyFormData.address_info || undefined,
      bank_info: applyFormData.bank_info || undefined,
    });
    applyDialogVisible.value = false;
    getData();
  } catch {
    /* ignore */
  } finally {
    applySubmitting.value = false;
  }
}

// ══════════════════ 初始化 ════════════════════

getData();
</script>

<style scoped lang="scss">
.fa-full-height {
  display: flex;
  flex-direction: column;
}
</style>
