// 健康检查接口封装：首页/设置抽屉用它探测后端是否就绪。
// opts 透传给 http（如 { silent:true } 时后端不可达不弹全局错误，由调用方展示状态）。
import http from './http'

export function getHealth(opts) {
  return http.get('/health', opts)
}
