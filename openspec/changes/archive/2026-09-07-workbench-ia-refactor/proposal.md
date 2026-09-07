## Why

工作台外层交互经多轮浏览器手工验收后沉淀为三项「信息架构 + 主区呈现」重构（C1/C3/C4），代码已交付、回归全绿，现回填规范并归档。三处动机：

1. **左栏空间无管理入口、铺不开**（C1）：空间横向铺成 pill 一行放不下、无折叠/改名/删除入口；任务行的 改名/改状态/删除 也无操作点。需要「全部空间(N) + 新建空间」头 + 可交互**空间树**：折叠/展开、点名字选作用域、行内 ⋯ 管理操作。
2. **聊天区右文件列常驻、会话/时间线分段多余**（C3）：原「会话/时间线」顶部分段中"会话"概念用户认为多余，右侧还常驻 240px 文件列占走宽度。改为头部「文件 / 时间线」两个按钮 → 同一右侧抽屉：文件按需打开、时间线列本任务输入的问题、点某条定位滚动回对应提问气泡。
3. **能力管理是右下角小窗而非一等公民、专家/自动化占导航位**（C4）：技能/MCP/资料库挤在 660px 注册中心抽屉 + 540px 资料库抽屉里；专家定位未定、自动化属 P1/P2 却占导航。改为**能力广场主区整页**：资料库/技能/MCP/RAG 各自左栏独立菜单 + 主区整页（顶部卡片式大页签来回切 + 双列卡片网格 CRUD），**专家/自动化退出一切导航/广场表面**（后端实体与已挂载任务不受影响）；资料库与知识库命名与口径在此理顺——资料库=**原文全文引用**，知识库 UI 更名 **RAG**=切块检索·相似召回。顺带把正式会话输出宽度放开到主区 ≥90%（用户/助手气泡以宽度错落区分回合）。

本提案**纯前端**（workbench-ui 域）：只消费既有 `/api/*`，无后端/数据改动；代码已实现并通过 `npm run build`。

## What Changes

- **C1 · 左栏空间树导航**：`LeftPanel` 中段改为「全部空间 (N)」头 +「新建空间」按钮 + `SpaceTree`（新组件，取代原横向 pill 与只读分组列表 `TaskGroupList`）。空间=树节点：chevron 折叠/展开、点空间名选中为作用域（再点回全部）、悬停 ⋯ 下拉「在此空间新建任务 / 重命名 / 删除」；删除二次确认并级联删任务、会话与工作文件。任务行悬停 ⋯ 下拉「重命名 / 置为待处理·进行中·已完成 / 删除」，改名经 `PATCH /api/tasks/<id>`、状态经既有字段同步，删除经既有删除接口并清理本地缓存。搜索框同时匹配任务标题与空间名。配套 `SpaceRenameDialog.vue`/`TaskRenameDialog.vue` 与 space/task store 的新增动作（`updateSpace/deleteSpace/deleteTaskEntry/updateTaskEntry`），空间/任务删除的后端接口与 DB 级联为既有已交付能力，此处纯接线。
- **C3 · 聊天区「文件 / 时间线」右抽屉**：删除右栏常驻文件列与顶部「会话/时间线」分段；`ChatPane` 头部（任务上下文行右侧）出现「文件 / 时间线」两个按钮，共用一个右侧抽屉（`ChatSideDrawer.vue`，size≈min(460px,92vw)）：文件态内嵌 `FileTree(bare)`（工作区文件 + 资料引用、预览/添加引用，打开即 `loadFiles` 刷新展示本轮新产物）；时间线态为 `TimelinePanel.vue`，列当前任务服务端历史中**用户输入**（序号/时间/首行摘要、升序），点某条收起抽屉并平滑滚动定位到对应提问气泡并短暂高亮。每气泡挂 `data-anchor`（服务端消息 `m<id>`、本地乐观气泡按序兜底）；切任务自动收起抽屉、不残留他任务内容。
- **C4 · 能力广场主区整页 + RAG 口径**：`ui` store 主区视图改为 `mainView: 'chat' | 'plaza'` + `plazaTab`；`Workbench` 主区按 `mainView` 用 `v-show` 在右栏工作区与 `CapabilityPlaza` 间切换（广场懒挂载、切回不销毁）。`LeftPanel` 导航改数据驱动「能力广场：资料库 / 技能 / MCP / RAG」四个独立菜单项（点→`openPlaza(page)`，高亮随广场页签）；底部「注册中心」入口移除、设置保留；`CommandPalette` 的「打开注册中心」命令改为「打开能力广场」。`CapabilityPlaza` 顶部一排卡片式大页签（图标+主名+副名）来回切四页（资料库=原文全文引用 / 技能=可复用技能指令 / MCP=外部工具连接器 / RAG=切块检索·相似召回），右侧「回到工作区」；四页体常驻 DOM（`v-show`）保留各自滚动/展开/表单态。三个旧抽屉 `RegistryDrawer/CapabilityDrawer/LibraryDrawer` 与 `ExpertCenter` 组件删除；资料库内容升格为 `LibraryPage` 整页。四页列表一律**双列卡片网格**（`repeat(2, minmax(0,1fr))`），避免单列稀疏。`KbCenter`（RAG 管理页）/细节栏挂载分区/挂载编辑分组/建任务与模板条装配摘要/追溯桶文案统一把「知识库」改称 **RAG**（挂载分区仍列专家 tile、专家组保留——场景预设会自动装配专家，仅不提供导航/广场入口）；`LibraryPage` 页头注明「原文全文引用（区别于 RAG 的切块检索）」。
- **会话输出宽度放开**（伴随 C3 的小优化）：`.cp-msgs` 不再用 `max-width:860px` 居中收窄列，改为占满主区；助手气泡 `max-width:94%`、用户气泡 `max-width:86%` 靠右且略收，两者以宽度错落区分回合、正式输出占会话区 ≥90%。

## Capabilities

### New Capabilities
<!-- 无新增能力域。 -->

### Modified Capabilities
- `workbench-ui`: 左栏空间/任务浏览改交互空间树并补行内管理操作；聊天区文件改头部按钮+右抽屉、时间线抽屉可定位高亮；能力管理（技能/MCP/资料库/RAG）由抽屉升格为主区能力广场整页 + 双列卡片网格，专家/自动化退出导航与广场表面，知识库 UI 更名 RAG；正式会话输出宽度放开至主区 ≥90% 且以气泡宽度错落区分回合。

## Impact

- 前端：`stores/ui.js`（mainView/plazaTab/openPlaza/showChat）、`stores/task.js`（selectTask 回 chat、deleteTaskEntry/updateTaskEntry/deleteTask 等）、`stores/space.js`（updateSpace/deleteSpace）、`views/Workbench.vue`、`components/layout/LeftPanel.vue`、`SpaceTree.vue`（新）、`SpaceRenameDialog.vue`/`TaskRenameDialog.vue`（新）、`ChatPane.vue`、`ChatSideDrawer.vue`/`TimelinePanel.vue`（新）、`FileTree.vue`（bare 态）、`CapabilityPlaza.vue`/`LibraryPage.vue`（新，抽屉内容升格整页）、`registry/SkillCenter.vue`/`McpCenter.vue`/`KbCenter.vue`（卡片网格 + RAG 文案）、`components/common/CommandPalette.vue`、`components/layout/CapMountDialog.vue`/`TaskCreateDialog.vue`/`TemplateBar.vue`/`AssistantTrace.vue`/`DetailDock.vue`（RAG 文案）、`utils/trace.js`（桶标签 kb→RAG）、`constants.js`；删除 `RegistryDrawer/CapabilityDrawer/LibraryDrawer/TaskGroupList/ExpertCenter`。
- 后端/数据：无改动、无迁移。已挂专家仍经 `caps.experts` 生效（场景预设自动装配），仅前端不再提供导航/广场级管理入口。
- 验证：`npm run build` 通过；手工按每步验收清单核验（空间树操作、抽屉文件/时间线定位、广场整页双列卡片 CRUD、RAG 文案口径、会话宽度 ≥90%）。
