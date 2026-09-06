// Axios 统一实例：所有请求走 /api（开发态由 Vite 代理到 5000）。
// 错误在此归一为带中文 message 的 Error，视图无需感知 HTTP 细节。
// 部分请求把「失败」当预期态（如 GET model-config 的 404=未绑定）：传 { silent:true }
// 可跳过全局错误弹窗，改由调用方静默处理；其余请求依旧全局 ElMessage.error。
import axios from 'axios'
import { ElMessage } from 'element-plus'

const http = axios.create({
  baseURL: '/api',
  timeout: 8000,
})

// 响应拦截：直接取 data，让 api/*.js 拿到 JSON 体
http.interceptors.response.use(
  (response) => response.data,
  (error) => {
    // 后端不可达：浏览器层面连不上，通常是后端没起
    const down = !error.response || error.code === 'ECONNABORTED' || error.message === 'Network Error'
    const message = down ? '后端服务不可达，请确认已运行 uv run flask --app backend.app run --port 5000' : (error.response?.data?.message || '请求失败')
    if (!error.config?.silent) ElMessage.error(message)
    return Promise.reject(new Error(message))
  },
)

export default http
