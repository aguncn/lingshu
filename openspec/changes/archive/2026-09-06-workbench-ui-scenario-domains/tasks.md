## 1. 顶部十二场景域分类快捷入口（spec「顶部场景域分类快捷入口」，设计 D1/D2）

- [x] 1.1 场景域清单 store 与 api：`stores/scenario.js` 持有 `domains/byDomain/labelOf/ensureLoaded({force})`，消费 `GET /api/scenarios`；`api/scenarios.js` 封装 `listScenarios`（列表接口按固定十二域序返回，含 name 与预设装配摘要计数）
- [x] 1.2 顶部条改为场景域条：`TemplateBar.vue` 以 chip 按域序渲染十二域 `name`，装配摘要进 `title` 悬停提示；点击某域调 `ui.openCreateTask(d.domain)` 打开新建任务对话框并预选该域；清单为空/加载失败时显示「场景域暂不可用」轻量空态与「重试」按钮（`ensureLoaded({force:true})`），不阻塞会话区
- [x] 1.3 移除 P3 提示词模板快捷条残留：`LeftPanel.vue`/`PromptInput.vue` 去掉 `usePromptStore`/`fetchPresets`/「已选模板」横幅；删除 `stores/prompt.js`、`api/prompts.js`（grep 全仓确认无残留引用）

## 2. 建任务选场景域并自动套用预设（spec R2 MODIFIED，设计 D3/D4）

- [x] 2.1 UI 状态接线：`stores/ui.js` 增 `taskDialogDomain` 状态与 `openCreateTask(domain='')` 动作；对话框关闭即清 `taskDialogDomain`，顶部 chip `active` 仅存在于「对话框开启且域匹配」时
- [x] 2.2 新建任务对话框「场景模板」下拉：`TaskCreateDialog.vue` 选项 = 「不绑定（手动挂载）」+ 十二场景域；选中域下方回显该域装配摘要（如「创建后自动套用该域预设：MCP 3 · 专家 1」）；对话框打开时预选 `ui.taskDialogDomain`
- [x] 2.3 `task` store `createTask` 支持 `scenario_domain` 自动套用：先 `POST /api/spaces/<sid>/tasks` 建任务，带域时再 `POST /api/tasks/<id>/scenario/apply`，把返回 `r.domain` 写回本地任务对象；`r.skipped` 非空 → warning 列出原因提示可去细节栏补挂载；apply 异常 → warning「任务已创建，可稍后手动挂载」，均不阻断创建
- [x] 2.4 提交成功后展开细节栏并提示：绑域任务创建成功 → `ui.detailOpen = true` + success「任务已创建并套用「域」预设」；未绑域 → 原「任务已创建」提示，行为与旧版一致

## 3. 细节栏场景域标记与四类挂载展示（spec R6 MODIFIED，设计 D5/D6）

- [x] 3.1 场景域标记（纯展示层，读 P2 `task.scenario_domain`）：`DetailDock.vue` 开关行在绑域任务上渲染域 `el-tag`，展开体顶部渲染「场景」标记条（含「已按该域预设装配；增删改请用各分区编辑挂载」说明）；未绑域不渲染
- [x] 3.2 四类挂载 tile 同构展示：`DetailDock.vue` 以 `MOUNT_KINDS=['skills','mcps','kbs','experts']` 渲染技能/MCP/知识库/专家四个独立分区，各自读 `task.caps[kind]` 真实挂载、行名经注册表 map 译为可读名（缺失回退 `#id` 不空白）、停用/未就绪实体弱化标注「· 停用」、无挂载类显示分类型空态文案（如「未挂载技能」）；四类共用同一 `CapMountDialog` 全量编辑器，避免单类改动清空其余挂载
- [x] 3.3 冷启动清单装载：`DetailDock.vue` onMounted 补拉 `reg.ensureLoaded()` + `scenario.ensureLoaded()`，`LeftPanel.vue` onMounted `scenario.ensureLoaded()`，使挂载 id 与域键可译为可读名

## 4. 验收

- [x] 4.1 前端构建通过：`cd frontend && npm run build` 无报错（删除 prompts 模块后无悬空 import）
- [x] 4.2 手工验收复核（起后端 5000 + 前端 5173，对照 spec 三个 ADDED/MODIFIED 场景）：顶部按序出 12 域 chip；点某域开对话框已预选并可建任务、提交后细节栏自动展开显示该域预设装配（如故障诊断 = 监控/日志/链路三 MCP + SRE 专家）；绑域任务细节栏可见域标记与四类挂载/停用弱化/空态
