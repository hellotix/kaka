import { request } from "@utils";

const API_PATH = "/platform/invoice";

const InvoiceAPI = {
  // ─── 租户端 ───
  tenantListInvoices(query?: InvoicePageQuery) {
    return request<ApiResponse<{ list: InvoiceTable[]; total: number }>>({
      url: `${API_PATH}/mine/list`,
      method: "get",
      params: query,
    });
  },

  applyInvoice(body: InvoiceApplyForm) {
    return request<ApiResponse>({
      url: `${API_PATH}/apply`,
      method: "post",
      data: body,
    });
  },

  downloadInvoice(invoiceId: number) {
    return request<Blob>({
      url: `${API_PATH}/${invoiceId}/download`,
      method: "get",
      responseType: "blob",
    });
  },
};

export default InvoiceAPI;

export interface InvoicePageQuery extends PageQuery, TenantByQueryParams {
  invoice_type?: string;
}

export interface InvoiceTable {
  id: number;
  tenant_id: number;
  order_id: number;
  invoice_no: string;
  invoice_type: string;
  title: string;
  tax_no?: string;
  amount: number;
  tax_amount: number;
  status: number;
  bank_info?: string;
  address_info?: string;
  pdf_url?: string;
  description?: string;
  created_time?: string;
}

export interface InvoiceApplyForm {
  order_id: number;
  invoice_type: string;
  title: string;
  tax_no?: string;
  address_info?: string;
  bank_info?: string;
  description?: string;
}
