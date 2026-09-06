// 任务工作空间文件（P2 列表 + P7 补的只读内容端点）。
// 列表返回元数据数组 { filename, path, size, mime }；内容端点内联返回 bytes，
// 供文件预览以 <pre>/<img>/blob 渲染。
import http from './http'

export const listTaskFiles = (taskId) => http.get(`/tasks/${taskId}/files`)

// 取单文件字节：responseType blob，调用方按 mime 决定 <img>/文本解码/仅元信息
export const getTaskFileContent = (taskId, filename) =>
  http.get(`/tasks/${taskId}/files/${encodeURIComponent(filename)}`, {
    responseType: 'blob',
  })
