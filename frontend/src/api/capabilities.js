// 任务能力装配（P4 capability-mount）。
// GET 返回 {task_id, skills:[], mcps:[], kbs:[], experts:[]}（各类 id 升序）；
// PUT 全量覆盖式更新，请求体四键任一缺省即清空该类。
import http from './http'

export const getTaskCaps = (taskId) => http.get(`/tasks/${taskId}/caps`)
export const putTaskCaps = (taskId, payload) => http.put(`/tasks/${taskId}/caps`, payload)
