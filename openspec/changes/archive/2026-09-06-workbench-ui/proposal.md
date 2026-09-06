## Why

当前前端只有 P1 脚手架（HomeView + 后端健康检查），没有任何操作入口。PRD 的核心差异点是「生产级工业风三栏工作台」，它决定产品的可用性；P2（空间/任务/文件）与 P3（模型供应商/绑模型/提示词库）后端已交付，需要一个把数据与后续智能体能力呈现出来的唯一可见入口——P7 工作台就是这张皮，也是 P8/P9 注入智能体的宿主。

## What Changes

用 Vue3 + Element Plus 把 `HomeView` 重构成三栏工业风工作台（仅前端，调用已交付的 P2/P3 接口）：

- **左栏全高四区块**：① 新建任务按钮；② 导航（专家·技能·MCP / 自动化 / 资料库）；③ 任务列表（按空间分组、可搜索、状态徽标）；④ 底部个人信息 + 设置入口。
- **右栏三段**：顶部「常用任务分类 + 提示词模板」快捷入口（数据源：`/api/prompts?category=task-preset`）；中部「会话区（对话气泡 + 文件树/预览）」；底部「可折叠细节栏（模型/技能/资料/MCP/工作空间/权限模板）+ 输入框」，细节栏默认收起（模型段消费 `/api/model-providers`、`/api/tasks/<id>/model-config`）。
- **命令面板** `Ctrl/Cmd+K`（自定义组件）：新建空间/任务、切换暗色、打开设置/注册中心等动作索引。
- **抽屉承载**：注册中心（技能/MCP/知识库/专家）、设置中心（含暗色模式）用 `ElDrawer`。
- **横切**：`ElTag` 状态徽标、`ElTimeline` 时间线（会话/审计占位）、暗色模式（Element Plus `dark` + CSS 变量 + localStorage 持久化）。
- **api/ 层**：为已交付后端封装模块（spaces / tasks / files / model-providers / model-config / prompts）。

**范围约定（本提案的显式边界，见下方 Capabilities/Impact）：**
- 只实连**已交付**的 P2/P3 接口；SSE 会话输入框与详情栏「时间线」保留接口位（P8 接，本期回车不做真实对话，仅做前端占位态）。
- P4/P5/P6 后端**未交付**：左栏导航（技能/MCP/自动化/资料库）、注册中心抽屉、细节栏的「技能/资料/MCP/权限模板」区块**全部照常搭建 UI，以稳定的空态/引导占位呈现**，并在 api/ 留薄封装；待 P4~P6 落地后回填数据，不动工作台外壳。验收口径聚焦工作台外壳 + 命令面板 + 暗色/徽标/时间线 + P2/P3 真实联调。

## Capabilities

### New Capabilities

- `workbench-ui`: 三栏工业风工作台 UI——空间/任务浏览与新建、会话与文件呈现骨架、可折叠细节栏（模型真实配置、其余能力占位）、提示词模板快捷入口、命令面板、注册中心/设置抽屉、暗色模式、状态徽标与时间线。纯前端行为契约。

### Modified Capabilities

（无——本提案不动任何后端 spec；P2/P3 接口仅被消费，不改行为。）

## Impact

- **frontend/src**：`router/`（新增工作台路由与布局）、`views/`（Workbench、Space/Task 相关、Settings/Registry 承载）、`components/`（布局区、CommandPalette、FileTree、DetailPanel、Timeline 等）、`store/`（新增 Pinia：space/task/provider/prompt/ui 状态）、`api/`（spaces/tasks/files/providers/model-config/prompts 封装）、`styles/`（工业风变量 + 暗色主题）、`main.js`/`App.vue`（挂 Element Plus dark、全局快捷键、路由壳）。
- **前端依赖**：Element Plus 与基础封装沿用 P1 脚手架；导航/状态图标题按需补 `@element-plus/icons-vue`。
- **后端**：仅补一条只读内容端点 `GET /api/tasks/<id>/files/<filename>`（任务工作空间文件内联返回 bytes，供文本/图片预览；复用 P2 白名单路径解析），零迁移、无其他改动（apply 阶段确认：P2 只有文件元数据列表接口，无内容接口，不加则文件预览验收无法成立）。
- **验收**：`cd frontend && npm run dev`（5173，代理 `/api`→5000，后端须在跑）；逐项点验 UI-01~07 + 与 P2/P3 的真实增删改回显。
