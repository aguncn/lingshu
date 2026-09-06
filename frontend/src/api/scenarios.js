// 场景域（P9 scenario-templates）：顶部十二域分类条 + 建任务时选域套用预设装配。
// GET /scenarios 列表（固定十二域序 + name + 装配摘要）；单查详情供调试；
// POST /tasks/<id>/scenario/apply 置 task.scenario_domain 并按域预设覆盖挂载能力。
import http from './http'

export const listScenarios = () => http.get('/scenarios')

export const getScenarioDetail = (domain) => http.get(`/scenarios/${domain}`)

// 返回 { task_id, domain, mounted:{skills,mcps,kbs,experts}, skipped:[{category,id,reason}] }
export const applyScenario = (taskId, domain) =>
  http.post(`/tasks/${taskId}/scenario/apply`, { domain })
