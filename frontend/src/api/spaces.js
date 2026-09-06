// 空间（P2）：只封空间自身 CRUD；「空间下任务」的接口归 tasks.js（域名归属任务）。
import http from './http'

export const listSpaces = () => http.get('/spaces')

export const createSpace = (data) => http.post('/spaces', data)

export const updateSpace = (id, data) => http.patch(`/spaces/${id}`, data)

export const deleteSpace = (id) => http.delete(`/spaces/${id}`)
