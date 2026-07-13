import { request } from "@utils";

const API_PATH = "/system/token";

const ApiTokenAPI = {
  /** 创建 API Token */
  createToken(body: ApiTokenCreateForm) {
    return request<ApiResponse<ApiTokenCreatedSchema>>({
      url: `${API_PATH}/create`,
      method: "post",
      data: body,
    });
  },

  /** 分页列表 */
  listToken(query: ApiTokenPageQuery) {
    return request<ApiResponse<PageResult<ApiTokenTable>>>({
      url: `${API_PATH}/list`,
      method: "get",
      params: query,
    });
  },

  /** 详情 */
  detailToken(id: number) {
    return request<ApiResponse<ApiTokenTable>>({
      url: `${API_PATH}/detail/${id}`,
      method: "get",
    });
  },

  /** 重置 token */
  resetToken(id: number, body: { name?: string; description?: string }) {
    return request<ApiResponse<ApiTokenCreatedSchema>>({
      url: `${API_PATH}/${id}/reset`,
      method: "post",
      data: body,
    });
  },

  /** 启用/禁用 */
  setTokenStatus(id: number, body: { status: number }) {
    return request<ApiResponse>({
      url: `${API_PATH}/${id}/status`,
      method: "patch",
      data: body,
    });
  },

  /** 删除 */
  deleteToken(id: number) {
    return request<ApiResponse>({
      url: `${API_PATH}/${id}`,
      method: "delete",
    });
  },

  /** 查看明文（二次验证） */
  revealToken(id: number, body: { password: string }) {
    return request<ApiResponse<ApiTokenRevealSchema>>({
      url: `${API_PATH}/${id}/reveal`,
      method: "post",
      data: body,
    });
  },
};

export default ApiTokenAPI;

export interface ApiTokenPageQuery extends PageQuery {
  name?: string;
  status?: number;
}

export interface ApiTokenTable extends BaseType {
  name?: string;
  token_prefix?: string;
  scopes?: string[];
  expires_at?: string;
  rate_limit?: number;
  status?: number;
  last_used_at?: string;
  used_count?: number;
  description?: string;
  tenant_id?: number;
}

export interface ApiTokenCreateForm extends BaseFormType {
  name: string;
  scopes?: string[];
  expires_at?: string;
  rate_limit?: number;
  status?: number;
  description?: string;
}

export interface ApiTokenCreatedSchema {
  id: number;
  name: string;
  token_prefix: string;
  /** 创建时完整返回，请立即保存 */
  token_plain: string;
  expires_at?: string;
}

export interface ApiTokenRevealSchema {
  id: number;
  token_plain: string;
  expires_at?: string;
}
