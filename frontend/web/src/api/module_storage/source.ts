import { request } from "@utils";

const API_PATH = "/storage/source";

const SourceAPI = {
  pageSource(query?: TablePageQuery) {
    return request<ApiResponse<PageResult<SourceTable>>>({
      url: `${API_PATH}/page`,
      method: "get",
      params: query,
    });
  },

  listSource(query?: Omit<TablePageQuery, "page_no" | "page_size">) {
    return request<ApiResponse<SourceTable[]>>({
      url: `${API_PATH}/list`,
      method: "get",
      params: query,
    });
  },

  detailSource(id: number) {
    return request<ApiResponse<SourceTable>>({
      url: `${API_PATH}/detail/${id}`,
      method: "get",
    });
  },

  createSource(body: SourceForm) {
    return request<ApiResponse<SourceTable>>({
      url: `${API_PATH}/create`,
      method: "post",
      data: body,
    });
  },

  updateSource(id: number, body: SourceForm) {
    return request<ApiResponse<SourceTable>>({
      url: `${API_PATH}/update/${id}`,
      method: "put",
      data: body,
    });
  },

  deleteSource(ids: number[]) {
    return request<ApiResponse>({
      url: `${API_PATH}/delete`,
      method: "delete",
      data: ids,
    });
  },

  testSource(id: number) {
    return request<ApiResponse<boolean>>({
      url: `${API_PATH}/test/${id}`,
      method: "post",
    });
  },

  testSourceConfig(body: SourceForm & { source_id?: number }) {
    return request<ApiResponse<boolean>>({
      url: `${API_PATH}/test`,
      method: "post",
      data: body,
    });
  },
};

export default SourceAPI;

export interface SourceForm extends BaseFormType {
  name?: string;
  protocol?: string;
  host?: string;
  port?: number;
  username?: string;
  password?: string;
  bucket?: string;
  endpoint?: string;
  region?: string;
  path_prefix?: string;
  is_secure?: boolean;
  implicit_tls?: boolean;
  is_default?: boolean;
  status?: number;
  description?: string;
}

export interface SourceTable extends BaseType {
  name?: string;
  protocol?: string;
  host?: string;
  port?: number;
  username?: string;
  has_password?: boolean;
  bucket?: string;
  endpoint?: string;
  region?: string;
  path_prefix?: string;
  is_secure?: boolean;
  implicit_tls?: boolean;
  is_default?: boolean;
  status?: number;
  description?: string;
}

export interface TablePageQuery extends PageQuery {
  name?: string;
  protocol?: string;
  status?: number;
}
