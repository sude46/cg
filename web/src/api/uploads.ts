import { http, unwrap } from './http'

export interface UploadResult {
  url: string
  key: string
}

/** 后端中转上传：multipart/form-data，字段名 file；axios 自动带 boundary */
export function uploadImage(file: File) {
  const fd = new FormData()
  fd.append('file', file)
  return unwrap(http.post('/uploads', fd)) as Promise<UploadResult>
}
