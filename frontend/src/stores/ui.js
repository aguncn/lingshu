// UI 全局状态（design D3/D6）：暗色、浮层开关、主区视图、细节栏收起、各类对话框。
// 暗色持久化到 localStorage 'lingshu:dark'；Element Plus 用 <html class="dark"> 驱动。
// 初始值必须在渲染前读取并落 class（见 main.js initDarkMode），避免首帧闪白。
// C4：三个能力抽屉（注册中心/资料库/占位）退役 → 主区改为整页切换：
//   mainView='chat'（工作区） ｜ 'plaza'（能力广场：技能/资料库/MCP/知识库/运维专家 整页）。
import { defineStore } from 'pinia'

const DARK_KEY = 'lingshu:dark'
const LEFT_W_KEY = 'lingshu:leftWidth'
const LEFT_COL_KEY = 'lingshu:leftCollapsed'

// 左栏宽度可拖拽调宽 + 可整栏折叠（Workbench 左导航）。宽上下限常量供 Workbench 拖拽沿用。
export const LEFT_MIN = 200
export const LEFT_MAX = 520
const LEFT_DEFAULT = 290

export function readInitialDark() {
  const raw = localStorage.getItem(DARK_KEY)
  return raw === null ? false : raw === '1' || raw === 'true'
}

function numOr(raw, fallback) {
  const n = Number(raw)
  return Number.isFinite(n) ? n : fallback
}
function readLeftWidth() {
  return numOr(localStorage.getItem(LEFT_W_KEY), LEFT_DEFAULT)
}
function readLeftCollapsed() {
  return localStorage.getItem(LEFT_COL_KEY) === '1'
}

// main.js 渲染前调用：把持久化的暗色提前挂到 <html>
export function initDarkMode() {
  document.documentElement.classList.toggle('dark', readInitialDark())
}

function applyDark(dark) {
  document.documentElement.classList.toggle('dark', dark)
  localStorage.setItem(DARK_KEY, dark ? '1' : '0')
}

export const useUiStore = defineStore('ui', {
  state: () => ({
    dark: readInitialDark(),
    // —— 左栏（Workbench）：宽度可拖拽调宽、可整栏折叠，均持久化 ——
    leftWidth: readLeftWidth(), // 展开态宽度 px（拖拽调宽时更新；折叠时保留原值以便还原）
    leftCollapsed: readLeftCollapsed(), // true=整栏折叠（宽度收起，仅留浮动展开钮）
    // —— 浮层与面板 ——
    detailOpen: false, // 右栏底部细节栏是否展开（默认收起）
    commandOpen: false, // 命令面板 Ctrl/Cmd+K
    settingsOpen: false, // 设置抽屉
    // —— 主区视图（C4 能力广场）——
    mainView: 'chat', // 'chat' = 工作区（会话+细节）｜ 'plaza' = 能力广场整页
    plazaTab: 'library', // 广场顶部大页签当前项：library | skills | mcps | kbs | experts
    activeNavKey: null, // 左栏导航高亮（=广场当前页；回到工作区后清空，避免残留高亮）
    // —— 新建对话框（命令面板与左栏按钮共用同一开关）——
    spaceDialogOpen: false,
    taskDialogOpen: false,
  }),
  actions: {
    toggleDark() {
      this.dark = !this.dark
      applyDark(this.dark)
    },
    setDark(v) {
      this.dark = !!v
      applyDark(this.dark)
    },
    // 左栏拖拽调宽：夹在 [LEFT_MIN, LEFT_MAX]；折叠中不写宽度（保持原值供还原）
    setLeftWidth(px) {
      const w = Math.min(LEFT_MAX, Math.max(LEFT_MIN, Math.round(px)))
      this.leftWidth = w
      if (!this.leftCollapsed) localStorage.setItem(LEFT_W_KEY, String(w))
    },
    // 整栏折叠/展开：折叠=收起宽度（原值留在 leftWidth），展开=回到原宽
    setLeftCollapsed(v) {
      this.leftCollapsed = !!v
      localStorage.setItem(LEFT_COL_KEY, v ? '1' : '0')
    },
    // 回到工作区整页（chat）。由任务选中/新建等「要干活」的动作触发；
    // 广场内仅点顶栏「回到工作区」按钮也走这里。
    showChat() {
      this.mainView = 'chat'
      if (this.activeNavKey) this.activeNavKey = null // 导航不再指向任一广场页
    },
    // 打开能力广场整页并切到指定页签（page 与左栏导航 key、广场顶栏一致）：
    //   library=资料库（集中文档）｜ skills=技能 ｜ mcps=MCP ｜ kbs=知识库（可检索切块）｜ experts=运维专家
    openPlaza(page = 'library') {
      this.plazaTab = page
      this.activeNavKey = page
      this.mainView = 'plaza'
    },
    // 打开新建任务对话框（是否选运维专家由用户在对话框内决定，不再外部预选）
    openCreateTask() {
      this.taskDialogOpen = true
    },
  },
})
