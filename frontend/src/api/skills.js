// 技能中心（P5 registry-center AD-01）。GET /skills/<id> 出口含 skill_md 全文供预览。
import http from './http'

export const listSkills = () => http.get('/skills')
export const getSkill = (id) => http.get(`/skills/${id}`)
export const createSkill = (data) => http.post('/skills', data)
export const updateSkill = (id, data) => http.patch(`/skills/${id}`, data)
export const removeSkill = (id) => http.delete(`/skills/${id}`)
