// 智能体运行时会话（P8 agentscope-runtime）前端桥。
// 为什么 SSE 流走 fetch 而非 axios：axios 不支持流式读取响应体；fetch 的
//   ReadableStream 可逐段消费 text/event-stream，边收边把 text_delta 推给视图。
// 帧切分：后端每帧单行 `data: {json}\n\n`（json.dumps ensure_ascii=False，控制字符
//   已被转义，帧内无裸换行），把多次 read 的字节拼到缓冲，再按空行切出完整帧。
// 错误语义：HTTP 非 200（400/404/409）→ 上抛后端 message 的 Error；HTTP 200 但
//   模型不可用 → SSE 首帧即 error 事件，由 onEvent 处理（不抛）。
import http from './http'

// 发起一次对话并消费 SSE 事件流。onEvent(evt) 收 {type, ...}；传给 signal 的
// AbortController 触发后 fetch 以 AbortError 拒绝 —— 调用方据此区分「主动取消」与「真失败」。
export async function streamChat(taskId, message, { signal, onEvent }) {
  const res = await fetch(`/api/tasks/${taskId}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({ message }),
    signal,
  })
  if (!res.ok) {
    // 校验/并发等失败走纯 JSON 错误体，不属于 SSE 事件流
    let msg = `会话请求失败（HTTP ${res.status}）`
    try {
      const j = await res.json()
      if (j && j.message) msg = j.message
    } catch {
      // 非 JSON 响应体：保留默认文案即可
    }
    throw Object.assign(new Error(msg), { status: res.status })
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
    let cut
    while ((cut = buf.indexOf('\n\n')) !== -1) {
      const line = buf.slice(0, cut).trim()
      buf = buf.slice(cut + 2)
      if (!line.startsWith('data:')) continue // 忽略非 data: 行
      const payload = line.slice(5).trim()
      if (!payload) continue
      let evt
      try {
        evt = JSON.parse(payload)
      } catch {
        continue // 脏帧直接跳过，不因单帧解析失败中断整条流
      }
      onEvent(evt)
    }
  }
}

// 危险工具二次确认回执：{run_id, confirm_id, allow}。
// 404=run 结束/confirm 已消费属预期态（用户双击或超时），silent 交给调用方提示。
export const sendChatDecision = (taskId, data) =>
  http.post(`/tasks/${taskId}/chat/decision`, data, { silent: true })

// 升序读任务历史：{task_id, messages:[{id,role,content,run_id,model,created_at}]}
export const listChatMessages = (taskId) =>
  http.get(`/tasks/${taskId}/messages`, { silent: true })
