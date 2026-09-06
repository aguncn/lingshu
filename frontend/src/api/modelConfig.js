// 任务绑模型参数（P3）。
// GET：任务尚未绑定会 404（后端 message「任务尚未绑定模型配置」），
// 这是工作台的「未绑定」常态而非错误 → silent，由 model store 置 config=null。
// POST=首次绑定(201)/替换(200)；PATCH=部分调参(200)。
import http from './http'

export const getTaskModelConfig = (taskId) =>
  http.get(`/tasks/${taskId}/model-config`, { silent: true })

export const bindTaskModel = (taskId, data) =>
  http.post(`/tasks/${taskId}/model-config`, data)

export const patchTaskModel = (taskId, data) =>
  http.patch(`/tasks/${taskId}/model-config`, data)
