import { request } from "@utils";

const API_PATH = "/system/auth";

/** 方案提供方 */
export type OAuthProvider = "wechat" | "qq" | "github" | "gitee";

const AuthAPI = {
  /**
   * 登录
   * @param body 登录参数
   * @returns 登录响应
   */
  login(body: LoginFormData) {
    return request<ApiResponse<LoginResult>>({
      url: `${API_PATH}/login`,
      method: "post",
      headers: {
        "Content-Type": "multipart/form-data",
      },
      data: body,
    });
  },

  refreshToken(refreshToken: string) {
    return request<ApiResponse<JWTOut>>({
      url: `${API_PATH}/token/refresh`,
      method: "post",
      data: refreshToken,
    });
  },

  getCaptcha() {
    return request<ApiResponse<CaptchaInfo>>({
      url: `${API_PATH}/captcha/get`,
      method: "get",
    });
  },

  logout(body: LogoutBody) {
    return request<ApiResponse>({
      url: `${API_PATH}/logout`,
      method: "post",
      data: body,
    });
  },

  /** 获取当前用户的可选租户列表 */
  getTenants() {
    return request<ApiResponse<TenantOption[]>>({
      url: `${API_PATH}/tenants`,
      method: "get",
    });
  },

  /** 选择租户，返回含 tenant_id 的新 JWT */
  selectTenant(tenantId: number) {
    return request<ApiResponse<SelectTenantResult>>({
      url: `${API_PATH}/select-tenant`,
      method: "post",
      data: { tenant_id: tenantId },
    });
  },

  /** 返回平台管理模式，清除 tenant_id 返回平台作用域 JWT */
  enterPlatform() {
    return request<ApiResponse<SelectTenantResult>>({
      url: `${API_PATH}/enter-platform`,
      method: "post",
    });
  },

  /** 平台管理员代签入（以指定租户身份登录） */
  impersonate(tenantId: number) {
    return request<ApiResponse<ImpersonateResult>>({
      url: `${API_PATH}/impersonate`,
      method: "post",
      data: { tenant_id: tenantId },
    });
  },

  /** 租户自助注册（PRD §4.5） */
  tenantRegister(body: TenantRegisterForm) {
    return request<ApiResponse<TenantRegisterResult>>({
      url: `${API_PATH}/tenant/register`,
      method: "post",
      data: body,
    });
  },

  /** 根据编码查询租户 */
  lookupTenant(code: string) {
    return request<ApiResponse>({
      url: `${API_PATH}/tenant/${encodeURIComponent(code)}`,
      method: "get",
    });
  },

  /** 根据域名查询租户 */
  lookupTenantByDomain(domain: string) {
    return request<ApiResponse>({
      url: `${API_PATH}/tenant-by-domain`,
      method: "get",
      params: { domain },
    });
  },

  /** 搜索租户（根据关键字模糊搜索编码或名称） */
  tenantSearch(q: string) {
    return request<ApiResponse<TenantOption[]>>({
      url: `${API_PATH}/tenant-search`,
      method: "get",
      params: { q },
    });
  },

  /** 获取所有活跃租户选项，用于登录页下拉选择 */
  getTenantOptions() {
    return request<ApiResponse<TenantOption[]>>({
      url: `${API_PATH}/tenant-options`,
      method: "get",
    });
  },

  /** 滑块验证完成后端标记 */
  sliderComplete(captchaKey: string) {
    return request<ApiResponse<{ captcha_key: string; verified: boolean }>>({
      url: `${API_PATH}/captcha/slider/complete`,
      method: "post",
      data: { captcha_key: captchaKey },
    });
  },
};

export default AuthAPI;

export interface TenantRegisterForm {
  username: string;
  password: string;
  email: string;
  tenant_name?: string;
}

export interface TenantRegisterResult {
  user_id: number;
  username: string;
  tenant_id: number;
  tenant_name: string;
  tenant_code: string;
  package: string | null;
  trial_end: string;
  message: string;
}

// ─── Auth 类型定义 ───

/** 登录表单 */
export interface LoginFormData {
  username: string;
  password: string;
  captcha_key?: string;
  remember?: boolean;
  login_type?: string;
}

/** JWT 响应 (JWTOutSchema) */
export interface JWTOut {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

/** 登录成功返回 */
export interface LoginResult extends JWTOut {
  tenants?: TenantOption[];
}

/** 退出登录请求体 */
export interface LogoutBody {
  token: string;
}

/** 租户选项 */
export interface TenantOption {
  id: number;
  name: string;
  code: string;
}

/** 选择租户返回 (SelectTenantOutSchema) */
export interface SelectTenantResult {
  access_token: string;
  token_type: string;
  expires_in: number;
}

/** 平台管理员代签入返回 (ImpersonateOutSchema) */
export interface ImpersonateResult {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  tenant_id: number;
  tenant_name: string;
}

/** 验证码信息 */
export interface CaptchaInfo {
  enable: boolean;
  key: string;
  img_base: string;
}
