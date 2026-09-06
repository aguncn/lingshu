// 路由表：默认直达三栏工作台；HomeView 收敛为探活兜底页（/health，排障用）。
import { createRouter, createWebHistory } from 'vue-router'

import HomeView from '../views/HomeView.vue'
import Workbench from '../views/Workbench.vue'

const routes = [
  { path: '/', name: 'workbench', component: Workbench },
  { path: '/health', name: 'health', component: HomeView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
