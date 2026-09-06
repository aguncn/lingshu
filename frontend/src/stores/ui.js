// UI 全局状态（design D3/D6）：暗色、浮层开关、细节栏收起、各类对话框。
// 暗色持久化到 localStorage 'lingshu:dark'；Element Plus 用 <html class="dark"> 驱动。
// 初始值必须在渲染前读取并落 class（见 main.js initDarkMode），避免首帧闪白。
import { defineStore } from 'pinia'

const DARK_KEY = 'lingshu:dark'

export function readInitialDark() {
  const raw = localStorage.getItem(DARK_KEY)
  return raw === null ? false : raw === '1' || raw === 'true'
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
    // —— 浮层与面板 ——
    detailOpen: false, // 右栏底部细节栏是否展开（默认收起）
    commandOpen: false, // 命令面板 Ctrl/Cmd+K
    settingsOpen: false, // 设置抽屉
    registryOpen: false, // 注册中心抽屉
    activeRegistryTab: 'skills', // skills | mcp | knowledge | experts
    libraryOpen: false, // 资料库抽屉（P6 library）
    capabilityOpen: false, // 左栏主导航（P4~P6 能力）占位抽屉
    capability: { key: '', title: '', phase: '', desc: '' },
    activeNavKey: null, // 左栏导航高亮
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
    // 左栏导航打开 P4~P6 能力占位抽屉：meta { key, title, phase, desc }
    openCapability(meta) {
      this.activeNavKey = meta.key
      this.capability = { ...meta }
      this.capabilityOpen = true
    },
    openRegistry(tab = 'skills') {
      this.activeRegistryTab = tab
      this.registryOpen = true
    },
    openLibrary() {
      this.activeNavKey = 'library'
      this.libraryOpen = true
    },
  },
})
