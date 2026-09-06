// 前端入口：挂载 Vue + Router + Pinia + Element Plus（脚手架全量引入，省去按需配置成本）。
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import './styles/index.css'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import router from './router'
import { initDarkMode } from './stores/ui'

// 渲染前先把暗色 class 挂到 <html>，避免首帧亮色闪一下再切暗（design D6）。
// 必须在 createApp().mount() 之前执行。
initDarkMode()

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(ElementPlus)

app.mount('#app')
