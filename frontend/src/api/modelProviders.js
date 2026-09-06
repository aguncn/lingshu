// 模型供应商（P3）：CRUD 全封；任何出口的 api_key 已是后端掩码（明文绝不下行）。
import http from './http'

export const listProviders = () => http.get('/model-providers')

export const getProvider = (id) => http.get(`/model-providers/${id}`)

export const createProvider = (data) => http.post('/model-providers', data)

export const updateProvider = (id, data) => http.patch(`/model-providers/${id}`, data)

export const deleteProvider = (id) => http.delete(`/model-providers/${id}`)
