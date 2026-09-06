// 提示词库（P3）：列表支持 category/domain/name 过滤；同名多版本只回链头。
import http from './http'

// params 例：{ category: 'task-preset' } 取常用任务类型预设
export const listPrompts = (params) => http.get('/prompts', { params })

export const getPrompt = (id) => http.get(`/prompts/${id}`)

export const createPrompt = (data) => http.post('/prompts', data)
