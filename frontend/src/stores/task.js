// 任务（design D3/D8）：后端无「全局任务列表」接口，故按空间逐组拉取合并；
// 懒加载只在首次展开某空间时请求一次（bySpace + loadedSpaces），选中任务即载入
// 其文件树与模型绑定。会话（P8 agentscope-runtime + 保活 session-keepalive）为真会话：
//   历史来自 GET /messages，发送走 SSE POST /chat，气泡实时流式渲染。
// 会话保活语义（升级：切走≠断流）：同标签页内切走任务时本地 SSE **不断开**——后台任务的
//   text_delta/thinking/tool 事件照常折叠进 messages[taskId]，返回该任务即见实时流式进度、
//   思考进行态与确认卡，后端 run 也从不被 stop；只有显式「停止」才 POST /chat/stop 真取消。
// 由于一个任务同时至多一条 run（后端注册表 409 保证）、但不同任务可并发，故 run 态按任务登记在
//   runs 表里，streaming/confirm/polling/busy 均为「当前选中任务」的派生视图——后台 run 不打扰
//   其它任务的输入与界面。无本地流的「采纳 run」（页面刷新/他窗口启动、SSE 帧不可回放）才降级走
//   GET /chat/status 轮询感知结束与确认；结束时以权威历史兜底最终结果。
import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'

import {
  createTaskInSpace,
  deleteTask as apiDeleteTask,
  listTasksInSpace,
  updateTask,
} from '../api/tasks'
import { getTaskCaps, putTaskCaps } from '../api/capabilities'
import { applyExpertProfile } from '../api/experts'
import { listTaskFiles } from '../api/files'
import { getChatStatus, listChatMessages, sendChatDecision, stopChat, streamChat } from '../api/chat'
import { decideStep, foldTraceEvent, normalizeTrace } from '../utils/trace'
import { useModelStore } from './model'
import { useSpaceStore } from './space'
import { useUiStore } from './ui'

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

// 模块级 SSE 控制器表：taskId → AbortController，某任务正有本地 SSE 流（sendMessage await 期间）时登记。
// 与旧版「全局单条聊天一个 chatAbort」不同：同页可同时有多个任务的 run 后台流式（切走不断流），
// 故按任务各自登记/释放。abort 只断开连接，是否真停由后端语义决定——仅显式「停止」走 /chat/stop 才取消。
const sseControllers = {}
// 轮询句柄/归属任务：仅用于「无本地流的采纳 run」（刷新/他窗口启动），且只跟随当前选中视图，
// 切走即停（该任务再次被选中时由 adoptRun 重新采纳）。放模块级，无需响应式。
let runPollTimer = null
let pollingTaskId = null

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
    messages: {}, // taskId -> 气泡 [{ id?, role, content, time, model?, live, error?, steps?, thinkingLive? }]
    chatLoaded: {}, // taskId -> true（历史已从服务端对齐，force 可覆盖）
    chatLoading: false, // 正在拉历史
    // —— 运行态（保活升级：切走≠断流）——
    // 同页切走本地 SSE 不断开：后台任务事件照常折叠进 messages[taskId]，返回即见实时进度；
    // 一个任务同时至多一条 run，但不同任务可并发。runs 按任务登记「是否有活动 run + 待回执确认」，
    // streaming/confirm/polling/busy 均取「当前选中任务」的派生值，后台 run 不打扰其它任务。
    runs: {}, // taskId -> { confirm: null | {taskId,runId,confirmId,name,action,reason} }；存在即该任务有活动 run
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
    // 会话进行中（本地流 or 采纳的后台 run 或待确认）：输入框据此禁用发送
    busy(state) {
      const t = state.activeTaskId
      return !!(t && state.runs[t])
    },
    // 当前任务有对话运行中（语义同 busy，ChatPane 滚动到底键用）
    streaming(state) {
      const t = state.activeTaskId
      return !!(t && state.runs[t])
    },
    // 该运行「无本地流、纯 /chat/status 轮询采纳」（刷新/他窗口恢复，看不到逐字流式）→ 提示后台运行
    polling(state) {
      const t = state.activeTaskId
      return !!(t && state.runs[t] && !sseControllers[t])
    },
    // 当前任务待回执确认的工具；无则 null（确认卡独立于气泡渲染，见 ChatPane）
    confirm(state) {
      const t = state.activeTaskId
      const r = t && state.runs[t]
      return r ? r.confirm || null : null
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
    // 选中任务：同页切换【不断流】——正在跑的本地 SSE 继续折叠（保活升级），
    // 仅停掉当前视图的状态轮询、放弃「纯采纳」任务的本端跟踪，再载入新任务的文件树/
    // 能力挂载/会话历史/模型绑定，并采纳新任务可能的运行态。
    async selectTask(task) {
      if (!task) return
      // C4：选中任务即回到「工作区」整页（若当前停在能力广场页签）
      useUiStore().showChat()
      if (this.activeTaskId === task.id) {
        // 重选当前任务：同步可能更新的字段即可；不要打断正在跑的本地流/已采纳运行态
        this.tasksById[task.id] = { ...this.tasksById[task.id], ...task }
        return
      }
      const leaving = this.activeTaskId
      this._clearRunPoll() // 轮询只跟随当前视图，切换即停
      if (leaving) this._leaveViewOf(leaving)
      this.activeTaskId = task.id
      this.tasksById[task.id] = { ...this.tasksById[task.id], ...task }
      this.loadFiles(task.id)
      this.loadCaps(task.id)
      // 采纳运行态并拉一次权威历史（adoptRun 收敛：有本地流直接跳过、无则问 status）
      this.adoptRun(task.id)
      useModelStore().loadConfig(task.id)
    },
    // —— 切走该任务的本端跟踪清理 ——
    // 本地 SSE 仍活着的任务：断流既不发生也不该发生，气泡由 sendMessage 折叠、结束后自刷新，
    //   返回即见实时进度与确认卡 → 保留 runs/chatLoaded；
    // 纯采纳（无本地流）的后台 run：放弃跟踪并删缓存，下次进入由 adoptRun 重拉权威历史
    //   （覆盖「run 在离开期间结束、返回需看到最终结果」）。
    _leaveViewOf(tid) {
      if (!tid) return
      if (sseControllers[tid]) return
      delete this.runs[tid]
      delete this.chatLoaded[tid]
    },
    // —— session-keepalive：运行态采纳 / 轮询 / 显式停止 ——
    // 采纳：进入某任务时对齐其真实运行态。
    //   有本地 SSE 流（同页切回自己启动的 run）→ 真流即权威，直接返回不打扰；
    //   否则问一次 /chat/status：无活动 run → 复位并载入历史（含刚结束的后台 run 最终回复）；
    //   有活动 run（刷新/他窗口启动，帧不可回放）→ 置「运行中/待确认」，起轮询，结束时 force 拉历史。
    async adoptRun(taskId) {
      if (!taskId || this.activeTaskId !== taskId) return // 只在被选中任务的上下文里采纳
      if (sseControllers[taskId]) return // 本地流正开着：无需 status/轮询，流事件即实时真相
      this._clearRunPoll()
      let s = null
      try {
        s = await getChatStatus(taskId)
      } catch {
        this.ensureHistory(taskId) // 状态查询失败（服务未就绪等）：至少把历史载上，不阻塞任务
        return
      }
      if (this.activeTaskId !== taskId) return // 请求期间已切走：放弃，避免覆盖新任务状态
      if (!s || !s.active) {
        // 无活动 run（含刚被 reaper 回收/已自然结束）：复位运行态，历史此刻即权威最终
        delete this.runs[taskId]
        this.ensureHistory(taskId)
        return
      }
      // 活动远程 run：置运行记录 + 待确认（若有），起轮询等到其结束（帧不可回放，无法给实时进度）
      this.runs[taskId] = { confirm: this._mapConfirm(taskId, s) }
      this.ensureHistory(taskId) // 至少载入已落库的用户消息，让确认卡片有气泡上下文
      this._ensureRunPoll(taskId)
    },
    // 起/续轮询：仅当该任务无本地 SSE 流且已有运行记录时才有意义（本地流事件已足够）
    _ensureRunPoll(taskId) {
      if (!this.runs[taskId]) return
      if (sseControllers[taskId]) {
        this._clearRunPoll()
        return
      }
      if (pollingTaskId === taskId) return
      this._clearRunPoll()
      pollingTaskId = taskId
      // 采纳 run 无事件可收，只能靠 status 心跳推进：短间隔感知结束/确认，也顺带 touch 防误回收
      runPollTimer = setInterval(() => {
        if (this.activeTaskId !== taskId) {
          this._clearRunPoll()
          return
        }
        this.pollStatus(taskId)
      }, 2000)
    },
    async pollStatus(taskId) {
      if (this.activeTaskId !== taskId) {
        this._clearRunPoll()
        return
      }
      let s = null
      try {
        s = await getChatStatus(taskId)
      } catch {
        this._clearRunPoll() // 查询持续失败：停轮询，避免后台空转；下次进入任务会重新采纳
        return
      }
      if (this.activeTaskId !== taskId) {
        this._clearRunPoll() // 请求期间已切走
        return
      }
      if (!s || !s.active) {
        // 采纳的后台 run 结束：清运行态，以权威历史刷新出最终回复
        delete this.runs[taskId]
        this._clearRunPoll()
        this.ensureHistory(taskId, { force: true })
        return
      }
      // 仍活动：刷新待确认（用户回执后下一拍恢复 confirm=null）
      this.runs[taskId] = { confirm: this._mapConfirm(taskId, s) }
    },
    _clearRunPoll() {
      if (runPollTimer) {
        clearInterval(runPollTimer)
        runPollTimer = null
      }
      pollingTaskId = null
    },
    // 显式停止（输入框「停止」按钮）：真取消【当前任务】的后台 run 并权威刷新。
    // 只作用于当前选中任务——其它任务正在后台流的 run 不受影响。
    async stopChat() {
      const tid = this.activeTaskId
      if (!tid) return
      const live = sseControllers[tid]
      if (live) {
        live.abort() // 断本任务本地流；sendMessage 收尾见控制器已被取走即不再接管
        delete sseControllers[tid]
      }
      delete this.runs[tid]
      this._clearRunPoll()
      delete this.chatLoaded[tid] // 等待后端落库后重对齐
      try {
        await stopChat(tid) // 后端 cancel+join+释放槽位；幂等 ok
      } catch {
        // 停止接口异常（极少）：不阻塞收尾，历史刷新会让界面回到服务端真态
      }
      this.ensureHistory(tid, { force: true })
    },
    // /chat/status 的 confirm 摘要 → 确认卡对象（无则 null）
    _mapConfirm(taskId, s) {
      if (!s || !s.confirm) return null
      return {
        taskId,
        runId: s.run_id,
        confirmId: s.confirm.confirm_id,
        name: s.confirm.name || '',
        action: s.confirm.action || '',
        reason: s.confirm.reason || '',
      }
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
    // 单字段 PATCH 当前任务（细节栏权限模式切换等）：服务端返回更新后的权威 dict，
    // 同步回本地缓存让选中态/输入框立即反映；不整组重拉（避免闪列表）
    async patchTask(payload) {
      const id = this.activeTaskId
      if (!id) return null
      const t = await updateTask(id, payload) // 失败上抛（拦截器已提示）
      if (this.tasksById[id]) this.tasksById[id] = { ...this.tasksById[id], ...t }
      // 同步空间分组里的同一对象，保持列表与缓存一致
      const group = this.bySpace[t.space_id]
      if (Array.isArray(group)) {
        const idx = group.findIndex((x) => x.id === id)
        if (idx !== -1) group[idx] = { ...group[idx], ...t }
      }
      return t
    },
    async createTask(payload) {
      // payload: { space_id, title, visibility?, permission_mode?, expert_id? }
      // expert_id = 可选的运维专家档案：选中后建任务再 apply 快照装配（人设快照 + 预设四类 caps 覆盖
      //   + 资料补挂 + 默认模型绑定）。task_type 已随 C5 从新建入口移除，服务端默认 'general'。
      const task = await createTaskInSpace(payload.space_id, {
        title: payload.title,
        visibility: payload.visibility,
        permission_mode: payload.permission_mode, // 三档权限：未给 → 服务端默认 strict
      }) // 失败上抛
      // 套用档案失败不阻断创建（任务已落库）：降级为「已建未装配」，提示去细节栏手动补挂载。
      let apply = null
      if (payload.expert_id) {
        try {
          const r = await applyExpertProfile(task.id, payload.expert_id)
          apply = {
            expert_name: payload.expert_name || '',
            mounted: r.mounted || null,
            skipped: r.skipped || [],
            library: r.library || null,
            model: r.model || null,
          }
        } catch (e) {
          apply = { expert_name: payload.expert_name || '', error: e?.message || '未知错误' }
        }
      }
      await this.reloadSpace(payload.space_id) // 成功后重拉该空间 → 新任务入分组
      await this.selectTask(task)
      return { task, apply }
    },
    // —— 左栏空间树行内操作（C1）：改名/改状态不一定先选中该任务，故按条目寻址 ——
    // 服务端 PATCH 返回权威 dict → 同步 tasksById 与对应空间分组，列表与详情同步反映。
    async updateTaskEntry(task, payload) {
      const t = await updateTask(task.id, payload) // 失败上抛（拦截器已提示）
      this._applyTask(t)
      return t
    },
    // 删除单个任务：DB 级联清挂载/消息/文件；前端清理本任务全部缓存，
    // 若删的是当前选中任务则复位活动态（ChatPane 回到空态，避免悬空引用）。
    async deleteTaskEntry(task) {
      const id = task.id
      await apiDeleteTask(id) // 失败上抛（拦截器已提示）
      this._dropTask(id)
    },
    // 删除整空间（space store 委托）：清掉该空间所有任务缓存与分组
    dropSpace(spaceId) {
      const arr = [...(this.bySpace[spaceId] || [])]
      for (const t of arr) this._dropTask(t.id)
      delete this.bySpace[spaceId]
      delete this.loadedSpaces[spaceId]
    },
    // —— 内部缓存同步/清理 ——
    _applyTask(t) {
      if (!t) return
      if (this.tasksById[t.id]) this.tasksById[t.id] = { ...this.tasksById[t.id], ...t }
      else this.tasksById[t.id] = t
      const group = this.bySpace[t.space_id]
      if (Array.isArray(group)) {
        const idx = group.findIndex((x) => x.id === t.id)
        if (idx !== -1) group[idx] = { ...group[idx], ...t }
      }
    },
    // 从所有缓存/运行态摘掉一个任务；删活动任务时一并复位视图态
    _dropTask(id) {
      const t = this.tasksById[id]
      if (t && Array.isArray(this.bySpace[t.space_id])) {
        const group = this.bySpace[t.space_id]
        const idx = group.findIndex((x) => x.id === id)
        if (idx !== -1) group.splice(idx, 1)
      }
      delete this.tasksById[id]
      delete this.filesByTask[id]
      delete this.messages[id]
      delete this.chatLoaded[id]
      delete this.runs[id]
      delete this._msgVer[id]
      if (this.capsLoadedTaskId === id) {
        this.caps = { skills: [], mcps: [], kbs: [], experts: [] }
        this.capsLoadedTaskId = null
      }
      if (this.activeTaskId === id) {
        const ctrl = sseControllers[id]
        if (ctrl) {
          ctrl.abort() // 断开可能的本地流；sendMessage 收尾见控制器已被取走即不再接管
          delete sseControllers[id]
        }
        this._clearRunPoll()
        this.activeTaskId = null
      }
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
          // session-trace-ui：服务端 trace → 气泡同构 steps；旧消息/纯文本无 trace → []（不渲染摘要行）
          steps: normalizeTrace(m.trace),
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
    // false=发生了「值得保留输入框」的失败（如模型不可用、或后端已有 run 未采纳 → 改后可重发）。
    // 本方法的流折叠只认发起时抓取的 tid：期间切走不打断，事件继续折进 messages[tid]，
    // 收尾也按「仍是该任务控制器持有者」判据，避免覆盖已被 stop/409-adopt 接管的状态。
    async sendMessage(text) {
      const tid = this.activeTaskId
      if (!tid) return false
      if (this.runs[tid]) return false // 防御：busy 时按钮已禁用

      // 清掉上一次失败遗留的报错气泡；成功的会被本轮 end 的权威历史整体替换，无需清
      if (this.messages[tid]) {
        this.messages[tid] = this.messages[tid].filter((b) => !(b.live && b.error))
        this._bump(tid)
      }
      // 乐观上屏：用户消息立即可见，助手气泡占位等首段文本（steps 供工具事件实时累积）
      this.pushBubble(tid, { role: 'user', content: text, time: fmtTime(new Date()), live: true })
      this.pushBubble(tid, {
        role: 'assistant',
        content: '',
        time: '',
        live: true,
        steps: [],
        thinkingLive: false,
      })
      const controller = new AbortController()
      sseControllers[tid] = controller // 登记为本地流持有者（切走不断流）
      this.runs[tid] = { confirm: null }

      let sawError = false // SSE error 事件或 HTTP 失败：保留内联报错，不做权威刷新
      let completed = false // SSE 正常读到终帧结束（区别于异常/主动中断）
      try {
        await streamChat(tid, text, {
          signal: controller.signal,
          onEvent: (evt) => this._onChatEvent(tid, evt, () => { sawError = true }),
        })
        completed = true
      } catch (e) {
        if (e?.name === 'AbortError') {
          // 主动中断（点「停止」stopChat）：已由其接管收尾（清控制器+拉权威历史），此处静默
        } else if (e?.status === 409) {
          // 后端已有另一条 run（他窗口/未采纳的旧 run）：本次未建 run、未落库，
          // 撤掉乐观气泡与本端登记回到真实态，并采纳既有 run → 重显其运行态/待确认卡片
          if (this.messages[tid]) {
            this.messages[tid] = this.messages[tid].filter((b) => !b.live)
            this._bump(tid)
          }
          if (sseControllers[tid] === controller) delete sseControllers[tid]
          delete this.runs[tid]
          ElMessage.warning('该任务已有对话正在运行，已为你转到该运行态（可放行/拒绝待确认操作或停止）')
          this.adoptRun(tid)
          sawError = true // 保留输入框文本便于用户决定后重发/停止
        } else {
          // 其它 HTTP/网络失败（模型不可用、404 等）：内联报错
          this._failAssistant(tid, e?.message || '会话请求失败')
          sawError = true
        }
      } finally {
        // 收尾复位：仅当本方法仍是该任务本地流的持有者才清理（切走不断流故不受 active 影响）；
        // 已被 stop/409-adopt 接管（控制器被取走/runs 被清）时绝不覆盖它们的采纳结果。
        if (sseControllers[tid] === controller) {
          delete sseControllers[tid]
          delete this.runs[tid]
        }
        // 自然跑完 → 以服务端权威历史替换乐观气泡（含真实时间/模型标识/权威 trace）；
        // 出错/主动中断 → 保留内联报错或交由调用方收尾，不在此刷新
        if (completed && !sawError) {
          this.ensureHistory(tid, { force: true })
          this.loadFiles(tid) // C3：一轮跑完即刷新文件缓存（智能体可能落了新文件，抽屉打开即见）
        }
      }
      return !sawError
    },
    // 逐事件更新视图气泡（SSE 事件契约见 runtime 端点）
    _onChatEvent(tid, evt, markError) {
      switch (evt.type) {
        case 'text_delta': {
          // 首段正文出现 → 先闭合悬挂思考再追加正文（foldTraceEvent 纯函数累积，跑完被权威历史覆盖）
          const b = this._liveOrCreate(tid)
          if (b) foldTraceEvent(b, { type: 'text_delta', delta: evt.delta || '' })
          else this._appendAssistant(tid, evt.delta || '') // 防御：异常时序下兜底建气泡
          break
        }
        case 'thinking_delta':
          // 思考增量：进 live 气泡 thinking 缓冲 + 置 thinkingLive（正文未产出时呈 "…" 进行态）
          foldTraceEvent(this._liveOrCreate(tid), { type: 'thinking_delta', delta: evt.delta || '' })
          break
        case 'tool_call':
          // 工具调用结束帧（参数已齐）：闭合思考 + append tool_call 步骤 → 摘要行实时累积
          foldTraceEvent(this._liveOrCreate(tid), { type: 'tool_call', name: evt.name || '', arguments: evt.arguments })
          break
        case 'tool_result':
          foldTraceEvent(this._liveOrCreate(tid), {
            type: 'tool_result',
            name: evt.name || '',
            ok: !!evt.ok,
            summary: evt.summary || '',
          })
          break
        case 'confirm_request':
          // 挂起等待用户回执：卡片级联渲染。后端逐条广播（同批工具确认是串行的），
          // 故同时只有一个 confirm；新请求会覆盖旧的（旧卡片已收起）。写入该任务 run 记录，
          // 后台任务的确认不打扰当前任务视图，返回该任务时自然呈现。
          if (!this.runs[tid]) this.runs[tid] = { confirm: null }
          this.runs[tid].confirm = {
            taskId: tid,
            runId: evt.run_id,
            confirmId: evt.confirm_id,
            name: evt.name || '',
            action: evt.action || '',
            reason: evt.reason || '',
          }
          // 标记待确认的工具调用步骤（foldTraceEvent 内）→ 回执后由 decideStep 写回 decision
          foldTraceEvent(this._liveOrCreate(tid), { type: 'confirm_request' })
          break
        case 'error':
          // 模型不可用/运行异常：把占位助手气泡换成报错文案（已累积的 steps 保留，下次发送被权威覆盖）
          markError()
          this._failAssistant(tid, evt.message || '智能体运行出错')
          break
        default:
          break
      }
    },
    // 危险工具二次确认：放行/拒绝（跨请求唤醒 worker）。
    // 本地 SSE 流会继续在同一连接收后续帧；远程采纳恢复的确认（无本地流）→ 回执唤醒后台 run，
    // 交由轮询感知其结束并拉权威历史。只对【当前任务】的确认卡生效。
    async decideConfirm(allow) {
      const tid = this.activeTaskId
      const rec = tid ? this.runs[tid] : null
      if (!rec || !rec.confirm) return
      const c = rec.confirm
      rec.confirm = null // 先收起卡片，防双击重复回执（repeat submit → 404 兜底）
      try {
        await sendChatDecision(c.taskId, {
          run_id: c.runId,
          confirm_id: c.confirmId,
          allow,
        })
        // 决策写回待确认的工具调用步骤（本地流时 confirm_request 已标记；
        // 远程恢复无 live 气泡则 decideStep 空操作，最终由权威 trace 展示决策）
        decideStep(this._liveOrCreate(c.taskId), allow)
        if (!allow) ElMessage.info('已拒绝该工具操作')
        // run 未结束（会继续跑到自然完成）：本地流自行续跑；纯采纳则保证轮询在跟，结束即刷新
        if (!sseControllers[c.taskId]) this._ensureRunPoll(c.taskId)
      } catch (e) {
        // 404=run 已结束/confirm 已被回执（双击、他窗口或超时）：重新采纳真实态（可能已结束→刷历史）
        ElMessage.warning(e?.message || '确认提交失败，会话可能已结束')
        if (this.activeTaskId === c.taskId) this.adoptRun(c.taskId)
      }
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
      else this.pushBubble(tid, {
        role: 'assistant', content: delta, time: fmtTime(new Date()), live: true,
        steps: [], thinkingLive: false,
      })
    },
    // —— session-trace-ui：live 气泡实时 steps 累积 ——
    // 步骤累积/思考归并/决策写回收敛在 utils/trace（foldTraceEvent/decideStep，纯函数可 Node 断言），
    // store 只负责取到当前 live 气泡；跑完由服务端权威 trace 整段覆盖（ensureHistory force）。
    _liveOrCreate(tid) {
      const b = this._liveAssistant(tid)
      if (!b) return null
      if (!Array.isArray(b.steps)) b.steps = []
      return b
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
