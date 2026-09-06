// MCP 连接器中心（P5 registry-center AD-02）。
// 出口只含 env_keys/headers_keys（键名，值 Fernet 加密不入 API），新建/编辑传完整 env/headers 对象。
import http from './http'

export const listMcps = () => http.get('/mcp')
export const getMcp = (id) => http.get(`/mcp/${id}`)
export const createMcp = (data) => http.post('/mcp', data)
export const updateMcp = (id, data) => http.patch(`/mcp/${id}`, data)
export const removeMcp = (id) => http.delete(`/mcp/${id}`)

// 连通性测试：成功 {ok:true,tools,tool_count}，失败 {ok:false,reason}；连接器不存在 404
export const testMcp = (id) => http.post(`/mcp/${id}/test`, {})
