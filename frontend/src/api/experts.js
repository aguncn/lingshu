// 运维专家中心（P5 registry-center AD-04 / C5 expert-profile）。
// Expert 为自包含「运维专家档案」：人设(system_prompt) + 预设技能/MCP/RAG/资料库(id 数组) + 默认模型。
// role ∈ {ops-sme, general}（内部短标签）；composed_of 已随 C5 移出前端语义（后端保留列）。
import http from './http'

export const listExperts = () => http.get('/experts')
export const getExpert = (id) => http.get(`/experts/${id}`) // 出口含 composed=[{id,name,role}]
export const createExpert = (data) => http.post('/experts', data)
export const updateExpert = (id, data) => http.patch(`/experts/${id}`, data)
export const removeExpert = (id) => http.delete(`/experts/${id}`)

// 快照装配：把一份运维专家档案「套用」到任务（人设快照 + 预设四类 caps 覆盖 + 资料补挂 + 默认模型）。
// 返回 { task_id, expert_id, mounted:{skills,mcps,kbs,experts}, skipped:[...], library:{...}, model:{...}|null }
export const applyExpertProfile = (taskId, expertId) =>
  http.post(`/tasks/${taskId}/expert/apply`, { expert_id: expertId })
