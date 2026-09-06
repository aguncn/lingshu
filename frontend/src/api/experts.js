// 专家中心（P5 registry-center AD-04）。role ∈ {ops-sme, general}；composed_of=协作子专家 id 数组。
import http from './http'

export const listExperts = () => http.get('/experts')
export const getExpert = (id) => http.get(`/experts/${id}`) // 出口含 composed=[{id,name,role}]
export const createExpert = (data) => http.post('/experts', data)
export const updateExpert = (id, data) => http.patch(`/experts/${id}`, data)
export const removeExpert = (id) => http.delete(`/experts/${id}`)
