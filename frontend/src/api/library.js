// 集中资料库（P6 library）。列表出口不含存储键；下载取 blob 供预览/落盘。
// 跨任务引用路由挂在 /api/tasks/<tid>/library-files（kind=ref 的行 id 即 detach 用的 FileRecord id）。
import http from './http'

// scope: all | global | shared | space；scope=space 需 space_id
export const listLibrary = (params = {}) => http.get('/library', { params })

export const uploadLibrary = (file, spaceId) => {
  const fd = new FormData()
  fd.append('file', file) // 后端字段名须为 file
  if (spaceId) fd.append('space_id', String(spaceId))
  return http.post('/library', fd)
}

export const getLibraryBlob = (libraryFileId) =>
  http.get(`/library/${libraryFileId}/download`, { responseType: 'blob' })

export const updateLibrary = (id, data) => http.patch(`/library/${id}`, data)
export const removeLibrary = (id) => http.delete(`/library/${id}`)

// —— 跨任务引用 ——
export const attachLibraryFile = (taskId, libraryFileId) =>
  http.post(`/tasks/${taskId}/library-files`, { library_file_id: libraryFileId })
export const detachLibraryFile = (taskId, fileRecordId) =>
  http.delete(`/tasks/${taskId}/library-files/${fileRecordId}`)
