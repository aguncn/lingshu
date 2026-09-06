# Tasks — workbench-ui

> 三栏工业风工作台。范围约定：P2/P3 实连、P4~P6 空态占位（见 proposal/design）。
> 每条可独立 `npm run dev` 目验；联调需后端在跑且库已迁移。
> apply 补充：为满足文件预览，后端新增只读内容端点 `GET /api/tasks/<id>/files/<filename>`（见 proposal Impact）。

## 1. 外壳与基建

- [x] 1.1 升级前端骨架：`router/index.js` 默认路由 `/` 指向 `views/Workbench.vue`（ElContainer 三栏工业风占位壳），`HomeView` 收敛为探活兜底或由工作台承接；`main.js`/`App.vue` 挂 Element Plus 与全局壳（验收：打开 5173 直达三栏工作台，无报错）
- [x] 1.2 新建 `store/ui.js`（Pinia）：`dark`（localStorage `lingshu:dark`）、`detailOpen/commandOpen/settingsOpen/registryOpen/activeRegistryTab`；`main.js` 引入 `element-plus/theme-chalk/dark/css-vars.css` 且渲染前读初始暗色避免闪白（验收：切暗色即时生效、刷新保持）
- [x] 1.3 `api/` 新增封装：`spaces.js`、`tasks.js`、`files.js`、`modelProviders.js`、`modelConfig.js`、`prompts.js`（复用 `http.js`；列表方法 try/catch 容错）（验收：各模块对现有后端 GET 可用）
- [x] 1.4 新建 `components/common/EmptyState.vue`（el-empty + 说明 + 可选重试）与 `components/common/StatusTag.vue`/`VisibilityTag.vue`（status/visibility 枚举 → ElTag 类型样式）（验收：空态与徽标组件可在页面复用渲染）

## 2. 左栏

- [x] 2.1 `store/space.js` + 左栏空间区块：`GET /api/spaces` 拉空间；新建空间 `ElDialog`（`POST /api/spaces`，成功即重拉并出现在分组头）（验收：新建空间后左侧出现）
- [x] 2.2 `store/task.js` + 任务分组列表：选中空间/全部分组，逐空间 `GET /api/spaces/<sid>/tasks` 合并展示、标题/空间名即时过滤；`ElTag` 状态徽标随行；点击任务置 `activeTaskId`（验收：建/选任务正确分组、搜索过滤有效）
- [x] 2.3 新建任务入口：左栏「新建任务」按钮 + `ElDialog`（选空间、`title`、`task_type` 枚举 fault/change/alert/general、可选 visibility）→ `POST /api/spaces/<sid>/tasks` 成功后重拉并选中（验收：新任务出现于对应分组且可选中）
- [x] 2.4 左栏 NavMenu + 底部个人信息/设置：主导航（专家·技能·MCP / 自动化 / 资料库）各条目打开对应占位（P4~P6 空态，不发起网络请求）；底部用户区提供「设置」入口（验收：导航可点、空态不报错、设置入口可开抽屉）

## 3. 右栏

- [x] 3.1 `RightPanel` + 顶部 `TemplateBar`：右栏三段布局；顶部 `GET /api/prompts?category=task-preset` 展示常用任务分类模板（写文档/写代码/数据分析/排障），点击置选中上下文（P8 前体现为输入框选中提示；接口失败降级空态）（验收：四类预设出现、点击有选中态、失败不阻塞）
- [x] 3.2 中部 `ChatPane` + `FileTree`：会话区空态占位（"智能体会话待 P8 接入"）；选中任务 `GET /api/tasks/<id>/files` 列文件，点击文本/图片条目走 blob 预览（`<pre>`/`<img>`，经新只读端点取字节），其余仅展示 mime/大小/路径元信息（验收：切换任务文件树正确、预览/元信息可达、空任务为空态）
- [x] 3.3 底部 `DetailDock` 可折叠细节栏：默认收起、可展开/收起，含 模型/技能/资料/MCP/工作空间/权限模板 六分区；工作空间分区显示所属空间；技能/资料/MCP/权限模板分区 `EmptyState` 占位（验收：收起展开正常、状态不串任务、占位不报错）
- [x] 3.4 细节栏模型分区 + `PromptInput`：模型分区实连 `/api/model-providers`（掩码密钥展示）与 `GET/POST/PATCH /api/tasks/<id>/model-config`（绑定/替换/调 temperature·max_tokens·timeout，ElMessage 反馈）；输入框发送在 P8 前仅生成本地占位气泡并提示"待接入"，切任务重置占位会话（验收：绑定调参经真实接口回写一致；发送仅本地占位；切任务不残留）

## 4. 横切与联调

- [x] 4.1 `CommandPalette`：全局 `Ctrl/Cmd+K` 开关、Esc 关闭、模糊过滤 + 方向键 + 回车执行；命令含 新建空间/新建任务/切换暗色模式/打开设置/打开注册中心/刷新任务列表（验收：任意页快捷键弹出、执行生效、Esc 还原焦点）
- [x] 4.2 `RegistryDrawer`（ElDrawer+ElTabs：技能/MCP/知识库/专家 → EmptyState）与 `SettingsDrawer`（暗色开关 + `GET /api/health` 探活显示）（验收：两抽屉可开合、health ok/失败态正确、空态展示）
- [x] 4.3 时间线占位 + 全量自检：任务详情 `el-timeline` 结构（P8 前无事件 → EmptyState 占位）；按 spec 各场景走一遍手工验收（左栏建空间/任务/搜索、右栏模板/文件/细节栏、命令面板、暗色持久化、抽屉、空态）（验收：spec 场景全部走通——实现齐备，浏览器手工点验待用户 `npm run dev` 执行）
