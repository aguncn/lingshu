// 任务（P2）：任务挂空间下，故列表/新建是嵌套路由；单条 CRUD 走 /tasks/<id>。
import http from './http'

// 某空间下任务列表（逐空间拉取合并的语义在 task store 内实现）
export const listTasksInSpace = (spaceId) => http.get(`/spaces/${spaceId}/tasks`)

// 在空间下新建任务：data { title, task_type, visibility? }
export const createTaskInSpace = (spaceId, data) =>
  http.post(`/spaces/${spaceId}/tasks`, data)

export const getTask = (id) => http.get(`/tasks/${id}`)

export const updateTask = (id, data) => http.patch(`/tasks/${id}`, data)

export const deleteTask = (id) => http.delete(`/tasks/${id}`)
