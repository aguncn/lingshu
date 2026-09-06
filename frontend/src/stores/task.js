// 任务（design D3/D8）：后端无「全局任务列表」接口，故按空间逐组拉取合并；
// 懒加载只在首次展开某空间时请求一次（bySpace + loadedSpaces），选中任务即载入
// 其文件树与模型绑定。会话（P8 agentscope-runtime）为真会话：历史来自
//   GET /messages，发送走 SSE POST /chat，气泡实时流式渲染；全站同时只跑一条
//   前台对话流（工作台右栏一次只呈现一个任务），切任务即中断旧流，避免后台悬挂。
import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'

import { createTaskInSpace, listTasksInSpace } from '../api/tasks'
import { getTaskCaps, putTaskCaps } from '../api/capabilities'
import { listTaskFiles } from '../api/files'
import { listChatMessages, sendChatDecision, streamChat } from '../api/chat'
import { useModelStore } from './model'
import { useSpaceStore } from './space'

// 时间展示：历史 created_at / 即时气泡统一成「MM-DD HH:mm」，与服务端无关，纯前端观感
function fmtTime(input) {
  const d = input instanceof Date ? input : new Date(input)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString('zh-CN', {
    hour12: false,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// 模块级 SSE AbortController：当前流的中止句柄（切任务/点停止时调 abort() 断开连接，
// 后端感知连接断开即 cancel 该 run）。放模块级而非 state，因控制器无需响应式。
let chatAbort = null

export const useTaskStore = defineStore('task', {
  state: () => ({
    bySpace: {}, // spaceId -> Task[]
    loadedSpaces: {}, // spaceId -> true（已拉过，懒加载去重）
    loading: false,
    tasksById: {}, // 见过的任务缓存（activeTask 取详情展示用）
    activeTaskId: null,
    search: '', // 左栏搜索关键字（标题/空间名即时过滤在组件 computed 内做）
    filesByTask: {}, // taskId -> FileMeta[]
    filesLoading: false,
    // —— P4 能力挂载（caps）：只对当前选中任务持一份，切任务重新拉 ——
    caps: { skills: [], mcps: [], kbs: [], experts: [] },
    capsLoadedTaskId: null, // 已载入 caps 的任务；避免切回已载任务重复请求
    capsLoading: false,
    // —— P8 真会话：消息气泡按任务隔离，服务端权威历史兜底 ——
    messages: {}, // taskId -> 气泡 [{ id?, role, content, time, model?, live, error? }]
    chatLoaded: {}, // taskId -> true（历史已从服务端对齐，force 可覆盖）
    chatLoading: false, // 正在拉历史
    streaming: false, // 前台 SSE 流式进行中（含等待二次确认）
    chatStreamTaskId: null, // 流所属任务；切走后用于清旧任务残留
    confirm: null, // 待确认工具：{ taskId, runId, confirmId, name, action, reason }
    _msgVer: {}, // taskId -> 本地气泡变更计数：防迟到的权威历史覆盖新一轮乐观气泡
  }),
  getters: {
    activeTask(state) {
      return state.activeTaskId ? state.tasksById[state.activeTaskId] ?? null : null
    },
    activeTaskFiles(state) {
      return state.activeTaskId ? state.filesByTask[state.activeTaskId] ?? [] : []
    },
    // 当前任务消息气泡（无历史 → []）
    activeMessages(state) {
      return state.activeTaskId ? state.messages[state.activeTaskId] ?? [] : []
    },
    // 会话进行中（流式 or 等待确认）：输入框据此禁用发送
    busy(state) {
      return state.streaming || state.confirm !== null
    },
  },
  actions: {
    // 单空间懒加载；已加载则跳过（force/reloadSpace 用于增删后重拉保一致，D8）
    async ensureSpaceLoaded(spaceId) {
      if (this.loadedSpaces[spaceId]) return
      try {
        const tasks = await listTasksInSpace(spaceId)
        this.bySpace[spaceId] = tasks
        for (const t of tasks) this.tasksById[t.id] = t
        this.loadedSpaces[spaceId] = true
      } catch {
        // 拉取失败：不标已加载，下次 refresh 会重试；先给空态避免整页崩
        this.bySpace[spaceId] = []
        delete this.loadedSpaces[spaceId]
      }
    },
    reloadSpace(spaceId) {
      delete this.loadedSpaces[spaceId]
      return this.ensureSpaceLoaded(spaceId)
    },
    // 全量：刷新任务列表（命令面板/冷启动）——拉全部空间的任务
    async loadAll() {
      const spaceStore = useSpaceStore()
      await spaceStore.ensureLoaded()
      this.loading = true
      try {
        await Promise.all(spaceStore.spaces.map((s) => this.ensureSpaceLoaded(s.id)))
      } finally {
        this.loading = false
      }
    },
    // 选中任务 → 中断旧对话流，再并行载入文件树、能力挂载、模型绑定与会话历史
    async selectTask(task) {
      if (!task) return
      // 切任务即中止旧任务进行中的流：连接断开 → 后端 cancel，不留悬挂 run / 悬空确认
      this.abortChat()
      this.activeTaskId = task.id
      this.tasksById[task.id] = { ...this.tasksById[task.id], ...task }
      this.loadFiles(task.id)
      this.loadCaps(task.id)
      this.ensureHistory(task.id)
      useModelStore().loadConfig(task.id)
    },
    // —— P4 挂载：拉当前任务 caps；同一任务只拉一次（force 供保存后刷新） ——
    async loadCaps(taskId, { force = false } = {}) {
      if (!taskId) return
      if (this.capsLoadedTaskId === taskId && !force) return
      this.capsLoading = true
      try {
        const d = await getTaskCaps(taskId)
        this.caps = {
          skills: d.skills || [],
          mcps: d.mcps || [],
          kbs: d.kbs || [],
          experts: d.experts || [],
        }
        this.capsLoadedTaskId = taskId
      } catch {
        // 拉取失败给空态，不阻断任务切换（拦截器已提示）
        this.caps = { skills: [], mcps: [], kbs: [], experts: [] }
      } finally {
        this.capsLoading = false
      }
    },
    // 全量覆盖式保存挂载后重拉一次，让细节栏与后续操作拿到服务端权威结果
    async updateCaps(payload) {
      await putTaskCaps(this.activeTaskId, payload) // 失败上抛（拦截器已提示）
      await this.loadCaps(this.activeTaskId, { force: true })
    },
    async createTask(payload) {
      // payload: { space_id, title, task_type, visibility? }
      const task = await createTaskInSpace(payload.space_id, payload) // 失败上抛
      await this.reloadSpace(payload.space_id) // 成功后重拉该空间 → 新任务入分组
      await this.selectTask(task)
      return task
    },
    async loadFiles(taskId) {
      this.filesLoading = true
      try {
        this.filesByTask[taskId] = await listTaskFiles(taskId)
      } catch {
        this.filesByTask[taskId] = []
      } finally {
        this.filesLoading = false
      }
    },

    // ============================================================
    // P8 会话：历史读取 / 发送(SSE) / 二次确认 / 中止
    // ============================================================
    // 拉任务历史为视图气泡（升序）；已有权威历史则跳过（force 供跑完/出错后对齐）
    async ensureHistory(taskId, { force = false } = {}) {
      if (!taskId) return
      if (this.chatLoaded[taskId] && !force) return
      const version = this._msgVer[taskId] ?? 0 // 快照本地变更数，返回后比对防覆盖
      this.chatLoading = true
      try {
        const d = await listChatMessages(taskId)
        // 拉取期间该任务又产生本地乐观气泡（新一轮发送已开始）→ 放弃本次覆盖：
        // 把 fetch 结果整段替换会清掉刚上屏的新用户消息，故让该轮结束后再对齐
        if ((this._msgVer[taskId] ?? 0) !== version) return
        this.messages[taskId] = (d.messages || []).map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          time: fmtTime(m.created_at),
          model: m.model || null,
          live: false,
        }))
        this.chatLoaded[taskId] = true
      } catch {
        // 拉取失败给空态；不置已加载，切回再试（silent 请求不弹错）
        this.messages[taskId] = []
        delete this.chatLoaded[taskId]
      } finally {
        this.chatLoading = false
      }
    },
    // 发送一条消息 → SSE 流式渲染。返回 true=本次已跑完/已入流（调用方可清输入框）；
    // false=发生了「值得保留输入框」的失败（如模型不可用，改好配置后可直接重发）。
    async sendMessage(text) {
      const tid = this.activeTaskId
      if (!tid) return false
      if (this.streaming || this.confirm) return false // 防御：busy 时按钮已禁用

      // 清掉上一次失败遗留的报错气泡；成功的会被本轮 end 的权威历史整体替换，无需清
      if (this.messages[tid]) {
        this.messages[tid] = this.messages[tid].filter((b) => !(b.live && b.error))
        this._bump(tid)
      }
      // 乐观上屏：用户消息立即可见，助手气泡占位等首段文本
      this.pushBubble(tid, { role: 'user', content: text, time: fmtTime(new Date()), live: true })
      this.pushBubble(tid, { role: 'assistant', content: '', time: '', live: true })
      this.streaming = true
      this.chatStreamTaskId = tid

      let sawError = false // SSE error 事件或 HTTP 失败：保留内联报错，不做权威刷新
      const controller = new AbortController()
      chatAbort = controller
      try {
        await streamChat(tid, text, {
          signal: controller.signal,
          onEvent: (evt) => this._onChatEvent(tid, evt, () => { sawError = true }),
        })
      } catch (e) {
        // AbortError=主动取消（切任务/点停止）：不发报错，交由收尾刷新对齐
        if (e?.name !== 'AbortError') {
          this._failAssistant(tid, e?.message || '会话请求失败')
          sawError = true
        }
      } finally {
        this.streaming = false
        this.confirm = null
        this.chatStreamTaskId = null
        chatAbort = null
        // 正常跑完 → 以服务端权威历史替换乐观气泡（含真实时间/模型标识）；
        // 主动取消 → 服务端可能只留 user（或空），同样以权威历史对齐。
        if (!sawError) this.ensureHistory(tid, { force: true })
        // sawError 分支保留内联报错气泡让用户看清原因；下一次成功发送即被权威历史覆盖
      }
      return !sawError
    },
    // 逐事件更新视图气泡（SSE 事件契约见 runtime 端点）
    _onChatEvent(tid, evt, markError) {
      switch (evt.type) {
        case 'text_delta':
          // 打字机：追加进当前「直播中」的助手气泡（放行工具后继续的文本也进同一气泡）
          this._appendAssistant(tid, evt.delta || '')
          break
        case 'confirm_request':
          // 挂起等待用户回执：卡片级联渲染。后端逐条广播（同批工具确认是串行的），
          // 故同时只有一个 confirm；新请求会覆盖旧的（旧卡片已收起）
          this.confirm = {
            taskId: tid,
            runId: evt.run_id,
            confirmId: evt.confirm_id,
            name: evt.name || '',
            action: evt.action || '',
            reason: evt.reason || '',
          }
          break
        case 'error':
          // 模型不可用/运行异常：把占位助手气泡换成报错文案
          markError()
          this._failAssistant(tid, evt.message || '智能体运行出错')
          break
        default:
          break // thinking/tool 事件本期不渲染：工具行为以最终产物文本呈现
      }
    },
    // 危险工具二次确认：放行/拒绝（跨请求唤醒 worker，SSE 流继续在同一连接里收后续帧）
    async decideConfirm(allow) {
      const c = this.confirm
      if (!c) return
      this.confirm = null // 先收起卡片，防双击重复回执（repeat submit → 404 兜底）
      if (this.activeTaskId !== c.taskId) return // 已切走（正常不会，切走会先 abort）
      try {
        await sendChatDecision(c.taskId, {
          run_id: c.runId,
          confirm_id: c.confirmId,
          allow,
        })
        if (!allow) ElMessage.info('已拒绝该工具操作')
        // allow：worker 已续跑，后续 text_delta 会继续流入当前流，无需额外动作
      } catch (e) {
        // 404=run 已结束/confirm 已被回执（双击或已超时）：提示并让 sendMessage 收尾
        ElMessage.warning(e?.message || '确认提交失败，会话可能已结束')
      }
    },
    // 中止当前对话流（切任务/点停止）。断开会话连接 → 后端 cancel 该 run 并释放注册表
    abortChat() {
      if (chatAbort) {
        chatAbort.abort()
        chatAbort = null
      }
      const oldTask = this.chatStreamTaskId
      this.streaming = false
      this.confirm = null
      this.chatStreamTaskId = null
      // 中断后以服务端权威历史对齐旧任务视图（可能只留 user 消息或为空）
      if (oldTask) this.ensureHistory(oldTask, { force: true })
    },
    // —— 气泡构建内部工具 ——
    _bump(tid) {
      this._msgVer[tid] = (this._msgVer[tid] ?? 0) + 1
    },
    pushBubble(tid, bubble) {
      if (!this.messages[tid]) this.messages[tid] = []
      this.messages[tid].push(bubble)
      this._bump(tid)
    },
    _liveAssistant(tid) {
      const arr = this.messages[tid] || []
      for (let i = arr.length - 1; i >= 0; i--) {
        const b = arr[i]
        if (b.live && b.role === 'assistant') return b
      }
      return null
    },
    _appendAssistant(tid, delta) {
      const b = this._liveAssistant(tid)
      if (b) b.content += delta
      else this.pushBubble(tid, { role: 'assistant', content: delta, time: fmtTime(new Date()), live: true })
    },
    // 助手占位气泡 → 报错文案；标记 chatLoaded=false，下次进任务会重拉服务端真历史
    _failAssistant(tid, message) {
      const text = message || '会话出错'
      const b = this._liveAssistant(tid)
      if (b) {
        b.content = text
        b.error = true
      } else {
        this.pushBubble(tid, { role: 'assistant', content: text, time: fmtTime(new Date()), live: true, error: true })
      }
      delete this.chatLoaded[tid]
    },
  },
})
