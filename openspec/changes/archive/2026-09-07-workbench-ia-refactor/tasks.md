> 三个外层重构（C1 空间树 / C3 文件·时间线抽屉 / C4 能力广场 + RAG 口径）同属 workbench-ui 域，本变更合并落地。代码已实现、`npm run build` 通过，逐条回填验收口径。后端零改动（删除/级联为既有接口）。

## 1. 左栏空间树导航（C1）

- [x] 1.1 新增 `components/layout/SpaceTree.vue`：以「空间节点（chevron 折叠/展开 + 可见性点 + 名称 + 任务数 + ⋯ 下拉）→ 任务行」树形替代原横向 pill 与只读分组列表；删除 `TaskGroupList.vue`。点空间名 = 选中为作用域（再点回全部，复用 `space.selectSpace`）；搜索框按任务标题或空间名即时过滤。验收：多空间/多任务下折叠展开、作用域高亮、搜索过滤均即时且无整页刷新。
- [x] 1.2 `LeftPanel.vue` 中段改「全部空间 (N) + 新建空间」头，`SpaceTree` 挂载其中；`SpaceCreateDialog`/`TaskCreateDialog` 沿左栏承载。验收：新空间出现于树头计数并进入树；「新建空间」按钮直开对话框。
- [x] 1.3 空间行内操作：空间 ⋯ 下拉 在此空间新建任务（先选中该空间）/重命名/删除；删除 `ElMessageBox` 二次确认、文案明示级联删 N 个任务+会话+工作文件。新增 `SpaceRenameDialog.vue`；`stores/space.js` 增 `updateSpace/deleteSpace`（删除后当前作用域为该空间则复位 null，并同步 task 按空间分组缓存）。验收：重命名即时反映；删除后树移除、级联文件/会话清除、作用域复位。
- [x] 1.4 任务行内操作：任务行 ⋯ 下拉 重命名 / 置为待处理·进行中·已完成 / 删除；改名与状态经 `PATCH /api/tasks/<id>`。新增 `TaskRenameDialog.vue`；`stores/task.js` 增 `updateTaskEntry/deleteTaskEntry`（删除同步清 bySpace/tasksById/messages/files/caps，删除当前活动任务则复位工作区为空态）。验收：改名/改状态即时上屏；删活动任务后会话区回到空态、无悬空；`npm run build` 通过。

## 2. 能力广场主区整页（C4）

- [x] 2.1 `stores/ui.js` 主区视图模型改造：state 增 `mainView:'chat'|'plaza'`、`plazaTab`、`activeNavKey`；动作 `showChat()`（置 chat 并清导航高亮）/`openPlaza(page)`/`openCreateTask(domain)`；移除 openRegistry/openLibrary/openCapability 及对应抽屉态。`stores/task.js` 的 `selectTask` 首先 `useUiStore().showChat()`——任何任务点选即回工作区。验收：任务点选/新建后主区回工作区；广场内点「回到工作区」同样返回。
- [x] 2.2 新增 `components/layout/CapabilityPlaza.vue`：顶部卡片式大页签（资料库·原文全文引用 / 技能·可复用技能指令 / MCP·外部工具连接器 / RAG·切块检索·相似召回）+「回到工作区」；四页体 `v-show` 常驻保留滚动/展开/表单态；`onMounted` 冷启动 `reg.ensureLoaded()`。`views/Workbench.vue`：主区按 `mainView` 在 RightPanel 与 `CapabilityPlaza`（懒挂载 `plazaAlive`）间切换，仅保留 SettingsDrawer 浮层。验收：广场页签来回切不丢页内状态；首次打开才实例化；主区 chat/plaza 互斥无残影。
- [x] 2.3 `LeftPanel.vue` 导航改数据驱动「能力广场」四项（key 与 `ui.plazaTab` 一一对应），高亮条件 `mainView==='plaza' && activeNavKey===key`；专家/自动化不出现于导航与广场页签；底部注册中心入口移除（保留设置）；`CommandPalette.vue` 的 open-registry 命令改「打开能力广场」。验收：四项点开=主区整页对应页；全站无 registry/library/capability 抽屉弹出。
- [x] 2.4 三个旧抽屉组件删除：`RegistryDrawer.vue`/`CapabilityDrawer.vue`/`LibraryDrawer.vue`、及无入口的 `registry/ExpertCenter.vue`；其引用全部清理。资料库内容升格为新增 `components/layout/LibraryPage.vue` 整页（头=标题+计数+「原文全文引用（区别于 RAG 的切块检索）」说明+刷新；工具栏=全部/全局/共享/空间 过滤 + 存入空间上传；卡片网格 + 预览/下载/共享/改名/删除（被引用禁止））。验收：资料库上传/预览/分享/改名/删除/空间过滤在整页可用，旧抽屉不再出现。

## 3. 聊天区「文件 / 时间线」抽屉（C3）

- [x] 3.1 `ChatPane.vue` 移除顶部「会话/时间线」分段与右侧常驻 `<FileTree>` 文件列；会话区 `.cp-msgs` 不再 `max-width:860px` 收窄（`width:100%`），`.cp-bubble` 助手 `max-width:94%`、`.cp-msg.user .cp-bubble` 用户 `max-width:86%` 靠右略窄。验收：正式输出占会话带 ≥90%；用户/助手以宽度错落一眼可分。
- [x] 3.2 头部上下文行右侧增「文件 / 时间线」两按钮（带图标+tooltip），共用新增 `components/layout/ChatSideDrawer.vue`（`el-drawer` rtl、size `min(460px,92vw)`、append-to-body）。「文件」打开即 `task.loadFiles(tid)` 并内嵌 `FileTree(bare)`（工作文件 + 资料引用两段、预览/添加引用）；「时间线」未载历史先 `ensureHistory` 并内嵌新增 `TimelinePanel.vue`。切任务自动收起抽屉。验收：文件抽屉按需打开即见本轮新产物、可预览加引用；时间线抽屉列当前任务提问；切任务抽屉收且不残留。
- [x] 3.3 时间线定位：每气泡 `data-anchor`（服务端消息 `m<id>`、本地乐观气泡按序兜底）；`TimelinePanel` 只列用户提问（序号/时间/首行摘要，跳空与 '…' 占位）；点某条 → 收抽屉 + `scrollIntoView({block:'center'})` + `.cp-flash` 外发光高亮（`offsetWidth` 重触发可连点复现）。验收：点提问定位滚动并高亮到对应气泡；空任务显示「暂无输入问题」占位。

## 4. 卡片双列网格与 RAG 口径（C4 收尾）

- [x] 4.1 四类管理页条目改**每行两列**卡片网格：`SkillCenter/McpCenter/KbCenter/LibraryPage` 统一 `grid-template-columns: repeat(2, minmax(0, 1fr))`；卡片含名/说明/状态与操作、窄内容省略不溢出。验收：四页条目两两成行、不单列稀疏，缩放自适应。
- [x] 4.2 知识库 UI 全局更名 **RAG**：`KbCenter.vue`（标题「RAG」、新建 RAG、空态「暂无 RAG」、对话框「新建/编辑 RAG 库」、删除确认文案、消息文案）；`DetailDock.vue` 挂载分区 `KIND_META.kbs`（title 与 empty=「RAG」/「未挂载 RAG」）；`CapMountDialog.vue` 分组「RAG」+ 说明「检索增强：任务按关键词召回库内切块」；`TaskCreateDialog.vue`/`TemplateBar.vue` 装配摘要 `RAG ${p.kbs}`；`AssistantTrace.vue` 弱标记 `RAG×${a.kbs}`；`utils/trace.js` `BUCKET_LABEL.kb='RAG'`。验收：全站管理与追溯界面不再出现「知识库」字样（专家挂载分区/专家组保留）。
- [x] 4.3 全量回归 + 手工清单：`npm run build` 通过；手工逐项过 spec 各场景（空间树操作、广场整页双列 CRUD、抽屉文件/时间线定位、RAG 文案、宽度 ≥90% 与气泡错落）。
