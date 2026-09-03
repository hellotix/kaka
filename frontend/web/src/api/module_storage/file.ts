import { request } from "@utils";

const API_PATH = "/storage/file";

const FileAPI = {
  listFiles(params?: FileListParams) {
    return request<ApiResponse<StorageObject[]>>({
      url: `${API_PATH}/list`,
      method: "get",
      params,
    });
  },

  uploadFile(formData: FormData) {
    return request<ApiResponse<Record<string, unknown>>>({
      url: `${API_PATH}/upload`,
      method: "post",
      data: formData,
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  downloadFile(body: FilePathBody) {
    return request<Blob>({
      url: `${API_PATH}/download`,
      method: "post",
      data: body,
      responseType: "blob",
    });
  },

  deleteFile(body: FilePathBody) {
    return request<ApiResponse>({
      url: `${API_PATH}/delete`,
      method: "delete",
      data: body,
    });
  },

  getFileUrl(params: FileUrlParams) {
    return request<ApiResponse<string | null>>({
      url: `${API_PATH}/url`,
      method: "get",
      params,
    });
  },
};

export default FileAPI;

export interface FileListParams {
  source_id?: number | null;
  prefix?: string;
}

export interface FilePathBody {
  remote_path: string;
  source_id?: number | null;
}

export interface FileUrlParams extends FilePathBody {
  expire?: number;
}

export interface StorageObject {
  name?: string;
  key?: string;
  is_dir?: boolean;
  size?: number;
  modified_time?: string;
}
