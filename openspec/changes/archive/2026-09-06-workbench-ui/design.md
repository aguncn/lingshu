## Context

前端目前只有 P1 脚手架：`App.vue` + `HomeView`（后端健康检查）+ `api/http.js`(axios) + `api/health.js` + `router/index.js`，代理 `/api`→5000。后端已交付 P2（spaces/tasks/files）与 P3（model-providers / tasks model-config / prompts+task-preset），P4~P6（技能/MCP/注册中心/资料库）与 P8（SSE 会话）**未实现**。范围约定见 proposal：全建 UI，P2/P3 实连，P4~P6 空态占位、不发起失败请求。设计依据 §4.4 布局与 P7 任务书。

## Goals / Non-Goals

**Goals:**
- 一套可落地的三栏工作台组件/状态/路由结构，UI-01~07 全部有对应实现与验收点。
- 左栏空间→任务分组浏览（逐空间 `/api/spaces/<sid>/tasks`）、搜索、新建空间/任务，全部实连 P2。
- 右栏：顶部 presets 模板条（P3）、会话+文件树（P2 files）、可折叠细节栏（模型分区实连 P3，其余空态）、输入框占位。
- 命令面板、注册中心/设置抽屉、暗色模式（持久化）、ElTag 徽标、ElTimeline 时间线空态。

**Non-Goals:**
- 不做真实会话/SSE/打字机（P8 接）；输入框发送只在本地放占位气泡。
- 不请求 P4~P6 的任何后端（无 endpoint），技能/MCP/资料库/权限/自动化一律静态空态+薄封装。
- 不改数据库、不加迁移；后端仅补一条只读内容端点 `GET /api/tasks/<id>/files/<filename>`（供文件预览取字节，复用 P2 白名单路径解析，见 D10 / proposal Impact）；不引入图表等重依赖；文件预览只用浏览器原生（`<img>`/`<pre>`/`blob`），未识别类型只显示元信息。
- 不做多用户/鉴权界面（单人，owner 语义沿用 P2）。

## Decisions

**D1 — 路由与外壳：工作台即主界面，设置/注册中心不走独立路由。**
`router/index.js` 挂一个壳路由 `/` → `views/Workbench.vue`（替换 HomeView 默认视图，HomeView 保留作 /health 兜底或删除由 HomeView 承接跳转）。`App.vue` 只放全局：`.dark` 根 class、命令面板全局键监听挂载、Element Plus 配置。注册中心与设置用抽屉承载（对齐 §4.4「抽屉承载」），避免为两个浮层再造路由——命令面板/左栏底部入口都只是"打开某个 drawer/pane"，由 `useUiStore` 统一开关，天然支持从命令面板直达。

**D2 — 三栏组件树（严格目录约定：布局复用组件下沉 components/layout）。**
```
App.vue  (暗色 class + 全局键 + 壳)
└─ Workbench.vue (ElContainer 高宽 100vh 工业风)
   ├─ components/layout/LeftPanel.vue     ① 新建任务按钮 ② NavMenu(导航/专家·技能·MCP·自动化·资料库)
   │                                     ③ TaskGroupList(空间分组+搜索+ElTag) ④ UserFooter(个人信息+设置)
   ├─ components/layout/RightPanel.vue
   │  ├─ TemplateBar.vue     顶部：常用任务分类 + presets 快捷
   │  ├─ ChatPane.vue        中部：会话占位 + 文件树(FileTree) 双栏
   │  └─ DetailDock.vue      底部：可折叠细节栏(六个分区) + PromptInput
```
新建/编辑浮层用 `ElDialog`（新建空间、新建任务），不引入弹窗路由。空态统一 `components/common/EmptyState.vue`（`el-empty` + 说明 + 可选重试）。

**D3 — Pinia store 切分（薄、按域），状态与组件一一对应。**
- `store/space.js`：`spaces`（GET /api/spaces）、`activeSpaceId`、建空间 action。
- `store/task.js`：`bySpace`（Map，逐空间拉取），`search` 关键字 → 导出过滤后的分组视图 computed；`activeTaskId`、选中任务对象、新建任务 action、`loadFiles(taskId)`。
- `store/prompt.js`：`presets`（GET /api/prompts?category=task-preset）、`selectedPreset`（点模板 → 输入框选中上下文）。
- `store/model.js`：`providers`（GET /api/model-providers，掩码展示）、当前任务 `modelConfig`（GET/POST/PATCH /api/tasks/<id>/model-config），绑定/调参动作在此，失败 ElMessage。
- `store/ui.js`：`dark`（读/写 localStorage `lingshu:dark`，切换即给根挂 `.dark`）、`detailOpen`、`commandOpen`、`settingsOpen`、`registryOpen`、`activeRegistryTab`。
数据获取在 store action 内 `try/catch`：任何列表失败都置空态 + ElMessage，绝不让一个接口拖垮整页。

**D4 — api/ 薄封装，P4~P6 不产生网络请求。**
`api/http.js` 沿用（baseURL `/api`，经 Vite 代理 5000）。新增：`api/spaces.js`、`api/tasks.js`、`api/files.js`、`api/modelProviders.js`、`api/modelConfig.js`、`api/prompts.js`。P4~P6 区块不封装 endpoint：左栏 NavMenu 的「技能/MCP/自动化/资料库」与注册中心四个 tab、细节栏「技能/资料/MCP/权限」只渲染 `EmptyState`（文案写"待 P4~P6 后端"），避免 404 噪声。将来后端落地只改「数据源绑定」一处。

**D5 — 命令面板 CommandPalette（自定义，UI-03）。**
`components/common/CommandPalette.vue`：全局 `keydown`（`ctrl/meta+k` 开、`Esc` 关）在 `App.vue onMounted` 注册。命令 = 注册表数组 `{id,label,keywords,run}`，至少：新建空间、新建任务、切换暗色模式、打开设置、打开注册中心、刷新任务列表。模糊过滤（label+keywords 包含）、方向键高亮、回车执行、执行后关面板并把 ElMessage 成功反馈。切暗色/开抽屉命令统一走 `useUiStore`。

**D6 — 抽屉与暗色模式。**
- `RegistryDrawer`（ElDrawer + ElTabs）：技能/MCP/知识库/专家四 tab，各为 EmptyState（说明各自属于 P4~P6）。
- `SettingsDrawer`：暗色开关（`el-switch`）、后端探活（GET /api/health 显示 ok/版本，失败显示"后端未连接"）。
- 暗色：`main.js` 引 `element-plus/theme-chalk/dark/css-vars.css`；初始值在渲染前从 localStorage 读出再 `createApp`，避免闪白。用 Element Plus 官方 `.dark` + `html.dark` 模式，配少量工业风 CSS 变量（色板、间距）放 `src/styles/index.css`。

**D7 — 徽标/时间线/文件树。**
- `components/common/StatusTag.vue`：`status`（open/in_progress/…沿用 P2 取值）与 `visibility`(private/team/public) 映射 type→ElTag；`components/common/VisibilityTag.vue` 同理。
- 时间线：任务详情面板用 `el-timeline` 结构，数据源为「任务事件」——P8 前为空，`EmptyState` 提示；占位结构保留 `el-timeline-item` 扩展点。
- 文件树：选中任务经 `GET /api/tasks/<id>/files` 拉列表；点击条目：`.txt/.md/.json/.log` 走文本预览（fetch blob→`<pre>`），图片走 `<img>`，其他仅展示 mime/大小/路径元信息面板。

**D8 — P2/P3 实连口径（验收即以此为准）。**
- 左栏任务分组 = 逐空间拉 `/api/spaces/<sid>/tasks` 合并（后端无全局任务列表接口）。
- 新建空间 POST /api/spaces；新建任务 POST /api/spaces/<sid>/tasks（`task_type` 枚举下拉 fault/change/alert/general）。
- 细节栏模型分区：供应商下拉来自 `/api/model-providers`；绑定/替换走 POST `/api/tasks/<id>/model-config`，调参走 PATCH；展示当前绑定与掩码 `api_key`。
- 顶部模板条 GET `/api/prompts?category=task-preset`，展示名称，点击进入输入框选中上下文。
- 所有增删改回显走"成功后重拉一次"，不做乐观更新，保证与后端一致。

**D9 — 联调前提与验收命令。**
后端须在跑且已迁移（P2/P3 库）；前端 `cd frontend && npm run dev`。手工验收按 spec 各场景 + proposal 里的 UI-01~07 清单点验；命令面板、暗色持久化、抽屉、空态为纯前端可独立验收项。

**D10 — 文件预览的只读内容端点（apply 确认的补量）。**
P2 仅交付文件元数据列表接口、无内容接口；为支撑 spec R5 / D7 的文本/图片预览，后端补一条只读内容端点 `GET /api/tasks/<id>/files/<filename>`（`send_file` 内联返回 bytes；服务层 `file_store.resolve_task_file` 沿用 P2 白名单解析并防路径穿越），proposal Impact 已同步记录。

## Risks / Trade-offs

- **[前端改动面大]** 一次把 HomeView 换成整套工作台。缓解：tasks 按「外壳 → 左栏 → 右栏 → 横切 → 联调」排序，每条可独立 `npm run dev` 目验。
- **[P4~P6 空态与将来真实的衔接]** 空态占位若后端落地需逐个换数据源。缓解：所有占位区块收敛到少数组件（EmptyState + NavMenu/RegistryTabs/DetailDock 配置），后端落地是点改动而非重写。
- **[无全局任务列表]** 左栏按空间分组的任务列表需 N+1 拉取。缓解：仅按需拉取（首次展开该空间），列表量小（单人工具），接受 N+1。
- **[文件预览跨域]** 预览走 Vite 代理同源，避免 dev 跨域；仅支持轻量文本/图片，不做 PDF 等重预览。

## Migration Plan

无数据库变更。前端目录新增/改造 + `package.json` 补 `@element-plus/icons-vue`；后端唯一改动为 apply 阶段确认新增的只读文件内容端点 `GET /api/tasks/<id>/files/<filename>`（见 D10 / proposal Impact），含服务层 `file_store.resolve_task_file` 与 pytest 守卫用例。

## Open Questions

无阻塞项。P4~P6 各自后端落地后，其空态→实数据的具体接口绑定顺延到对应提案（capability-mount / registry-center / library）的 UI 对接任务，不在本提案展开。
