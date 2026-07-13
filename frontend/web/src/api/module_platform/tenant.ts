import { request, NO_AUTH_FLAG } from "@utils";

const API_PATH = "/platform/tenant";

const TenantAPI = {
  listTenant(query?: TenantPageQuery) {
    return request<ApiResponse<PageResult<TenantTable>>>({
      url: `${API_PATH}/list`,
      method: "get",
      params: query,
    });
  },

  detailTenant(id: number) {
    return request<ApiResponse<TenantTable>>({
      url: `${API_PATH}/detail/${id}`,
      method: "get",
    });
  },

  createTenant(body: TenantCreateForm) {
    return request<ApiResponse>({
      url: `${API_PATH}/create`,
      method: "post",
      data: body,
    });
  },

  updateTenant(id: number, body: TenantUpdateForm) {
    return request<ApiResponse>({
      url: `${API_PATH}/update/${id}`,
      method: "put",
      data: body,
    });
  },

  deleteTenant(body: number[]) {
    return request<ApiResponse>({
      url: `${API_PATH}/delete`,
      method: "delete",
      data: body,
    });
  },

  /** 批量修改租户状态 */
  batchTenantStatus(body: BatchType) {
    return request<ApiResponse>({
      url: `${API_PATH}/status/batch`,
      method: "patch",
      data: body,
    });
  },

  /** 切换单个租户启用/禁用状态 */
  toggleTenantStatus(id: number) {
    return request<ApiResponse>({
      url: `${API_PATH}/status/${id}`,
      method: "put",
    });
  },

  /** 租户续期 */
  renewTenant(id: number, body: { end_time: string }) {
    return request<ApiResponse<TenantTable>>({
      url: `${API_PATH}/renew/${id}`,
      method: "put",
      data: body,
    });
  },

  /** 套餐变更预览 */
  previewPackageChange(packageId: number) {
    return request<ApiResponse<PackageChangePreview>>({
      url: `${API_PATH}/package/preview`,
      method: "get",
      params: { target_package_id: packageId },
    });
  },

  /** 可选购的套餐列表 */
  getAvailablePackages() {
    return request<ApiResponse<{ packages: AvailablePackage[] }>>({
      url: `${API_PATH}/package/available`,
      method: "get",
    });
  },

  /** 公开接口：无需登录即可获取租户配置（用于登录页等场景） */
  getTenantConfigInfo(tenantId: number) {
    return request<ApiResponse<TenantConfigItem[]>>({
      url: `${API_PATH}/${tenantId}/config/info`,
      method: "get",
      headers: {
        Authorization: NO_AUTH_FLAG,
      },
    });
  },

  /** 创建自助订单 */
  createOrder(body: SelfServiceOrderForm) {
    return request<ApiResponse<{ order_id: number; amount: number }>>({
      url: `${API_PATH}/order/create`,
      method: "post",
      data: body,
    });
  },

  /** 我的订单列表 */
  listMyOrders(query?: PageQuery) {
    return request<ApiResponse<PageResult<SelfServiceOrderItem>>>({
      url: `${API_PATH}/order/list`,
      method: "get",
      params: query,
    });
  },

  /** 订单详情 */
  detailMyOrder(orderId: number) {
    return request<ApiResponse<SelfServiceOrderItem>>({
      url: `${API_PATH}/order/detail/${orderId}`,
      method: "get",
    });
  },

  /** 租户工作台概览 */
  getWorkspace() {
    return request<ApiResponse<WorkspaceData>>({
      url: `${API_PATH}/workspace`,
      method: "get",
    });
  },
};

export default TenantAPI;

export interface TenantPageQuery extends PageQuery, UserByQueryParams, TenantByQueryParams {
  name?: string;
  code?: string;
  status?: number;
}

export interface TenantTable extends BaseType {
  name: string;
  code: string;
  package_id?: number;
  start_time?: string;
  end_time?: string;
  contact_name?: string;
  contact_phone?: string;
  contact_email?: string;
  address?: string;
  domain?: string;
  logo_url?: string;
  sort?: number;
  version?: string;
  favicon?: string;
  login_bg?: string;
  copyright?: string;
  keep_record?: string;
  help_doc?: string;
  privacy?: string;
  clause?: string;
  git_code?: string;
  status?: number;
  description?: string;
}

export interface TenantForm extends BaseFormType {
  name?: string;
  code?: string;
  package_id?: number;
  start_time?: string;
  end_time?: string;
  contact_name?: string;
  contact_phone?: string;
  contact_email?: string;
  address?: string;
  domain?: string;
  logo_url?: string;
  sort?: number;
  version?: string;
  favicon?: string;
  login_bg?: string;
  copyright?: string;
  keep_record?: string;
  help_doc?: string;
  privacy?: string;
  clause?: string;
  git_code?: string;
  status?: number;
  description?: string;
}

export interface TenantCreateForm extends BaseFormType {
  name: string;
  code: string;
  package_id?: number;
  start_time?: string;
  end_time?: string;
  contact_name?: string;
  contact_phone?: string;
  contact_email?: string;
  address?: string;
  domain?: string;
  logo_url?: string;
  sort?: number;
  version?: string;
  favicon?: string;
  login_bg?: string;
  copyright?: string;
  keep_record?: string;
  help_doc?: string;
  privacy?: string;
  clause?: string;
  git_code?: string;
  status?: number;
  description?: string;
}

export interface TenantUpdateForm extends BaseFormType {
  name?: string;
  code?: string;
  package_id?: number;
  start_time?: string;
  end_time?: string;
  contact_name?: string;
  contact_phone?: string;
  contact_email?: string;
  address?: string;
  domain?: string;
  logo_url?: string;
  sort?: number;
  version?: string;
  favicon?: string;
  login_bg?: string;
  copyright?: string;
  keep_record?: string;
  help_doc?: string;
  privacy?: string;
  clause?: string;
  git_code?: string;
  status?: number;
  description?: string;
}

export interface AvailablePackage {
  id: number;
  name: string;
  price: number;
  period: string;
  trial_days: number;
  max_users: number;
  max_roles: number;
  max_depts: number;
  max_storage_mb: number;
  description: string | null;
  is_current: boolean;
  available_actions: string[];
}

/** 租户配置项 */
export interface TenantConfigItem {
  config_key: string;
  config_value: string | null;
}

export interface PackageChangePreview {
  current_package: string;
  target_package: string;
  action: string;
  amount: number;
  period: string;
  gained_menus: { id: number; name: string; path: string }[];
  lost_menus: { id: number; name: string; path: string }[];
  affected_roles: Record<string, unknown>[];
  affected_users: number;
}

export interface SelfServiceOrderForm {
  package_id: number;
  order_type: "buy" | "renew" | "upgrade" | "downgrade";
  pay_method?: string;
}

export interface SelfServiceOrderItem {
  id: number;
  order_no: string;
  package_name: string;
  order_type: string;
  amount: number;
  status: number;
  pay_method?: string;
  pay_time?: string;
  created_at: string;
}

export interface WorkspaceData {
  tenant: {
    id: number;
    name: string;
    code: string;
    status: number;
    status_label: string;
    start_time: string | null;
    end_time: string | null;
    days_remaining: number;
  };
  package: {
    id: number;
    name: string;
    price: number;
    period: string;
  } | null;
  quota: {
    max_users: number;
    max_roles: number;
    max_depts: number;
    current_users: number;
    current_roles: number;
    current_depts: number;
    usage_percent: {
      users: number;
      roles: number;
      depts: number;
    };
  };
  recent_orders: {
    id: number;
    order_no: string;
    amount: number;
    order_type: string;
    status: number;
    created_at: string | null;
  }[];
}
