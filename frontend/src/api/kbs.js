// 知识库中心（P5 registry-center AD-03）。上传走 multipart 的 file 字段（仅 .txt/.md）。
import http from './http'

export const listKbs = () => http.get('/kb')
export const getKb = (id) => http.get(`/kb/${id}`)
export const createKb = (data) => http.post('/kb', data)
export const updateKb = (id, data) => http.patch(`/kb/${id}`, data)
export const removeKb = (id) => http.delete(`/kb/${id}`)

export const uploadDocument = (kbId, file) => {
  const fd = new FormData()
  fd.append('file', file) // 后端字段名须为 file；axios 对 FormData 自动带 multipart boundary
  return http.post(`/kb/${kbId}/upload`, fd)
}

// 返回分数降序切块 [{chunk_id, content, filename, chunk_index, score}]
export const searchKb = (kbId, query, topK = 5) =>
  http.post(`/kb/${kbId}/search`, { query, top_k: topK })
