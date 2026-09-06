## Why

工作台当前把"场景域"这条链路收口在前端三处观感上（顶部域条、建任务选域、细节栏展示装配结果），是 P9 `scenario-templates` 验收成立的关键载体，也是让"十二域、建任务自动装配、细节栏可见挂载"产品闭环可见的最后一公里。但这批前端行为是在 P9 验收时以临时补丁形态实现的，`workbench-ui` 主规范仍停留在 P3 阶段：顶部需求描述的是"提示词模板快捷入口"（对应 `GET /api/prompts?category=task-preset`），而该功能已被实现为"十二场景域快捷入口"（消费 `GET /api/scenarios`），代码与规范已分叉。本提案把这批已实现并验证的前端行为正式立案、改写对应需求文本，使主规范回到与代码一致的可验收状态。

## What Changes

- **顶部快捷条：P3 提示词模板 → 十二场景域分类（MODIFIED，改写既有顶部需求）**：顶部条数据源从 `GET /api/prompts?category=task-preset` 改为 `GET /api/scenarios`（固定十二域序）；每域以 chip 展示 `name`，装配摘要入工具提示；点击某域 = 打开新建任务对话框并**预选该域**（走 `ui.taskDialogDomain`）；接口加载失败降级为"场景域暂不可用"轻量空态并可重试，不阻塞会话区。被替换的 P3 `prompts` store / api 与 PromptInput 内"已选模板"提示已一并删除（无残留消费）。
- **建任务选域并自动套用预设（MODIFIED，给"空间与任务浏览、新建与搜索"补场景）**：新建任务对话框新增"场景模板"下拉（`''`=不绑定手动挂载 + 十二域），下方回显该域装配摘要提示；提交时若带域，先 `POST /api/spaces/<sid>/tasks` 建任务、再调 `POST /api/tasks/<id>/scenario/apply` 自动套用预设（置 `task.scenario_domain` + 全量覆盖挂载 caps），跳过项给 warning 提示、套用失败不阻断创建（降级为已建未装配，提示去细节栏手动挂载）；成功后自动展开细节栏让装配立即可见。
- **细节栏：场景域标记 + 技能/MCP/知识库/专家四类挂载展示（MODIFIED，改写"可折叠细节栏与任务模型绑定"）**：绑定场景域的任务在开关行与展开体顶部呈现域 tag/场景条（"已按该域预设装配…"）；挂载区从笼统的"技能/MCP"扩展为 `skills/mcps/kbs/experts` 四类同构 tile，各 tile 经 `GET /api/tasks/<id>/caps` 读真实挂载、逐行标注停用/未就绪弱化态（`· 停用`），空态分类型文案占位；冷启动补拉注册中心与场景域清单以把 id 翻译成可读名。

## Capabilities

### New Capabilities
<!-- 无：本提案不改后端契约，只消费 scenario-templates（/api/scenarios、/scenario/apply）与既有 caps/messages 前端接口。 -->

### Modified Capabilities
- `workbench-ui`: 三个既有需求因上述前端行为被改写——顶部快捷入口需求从"提示词模板"改为"十二场景域分类"；"空间与任务浏览、新建与搜索"补建任务选域套用预设的行为；"可折叠细节栏与任务模型绑定"补场景域标记与知识库/专家挂载展示。纯前端展示层变化，后端零改动。

## Impact

- 前端（均为本会话已实现、随 P9 验收运行过的代码，立案不改动其逻辑）：
  - `frontend/src/components/layout/TemplateBar.vue`：重写为场景域条（删除对 `usePromptStore`/`fetchPresets` 的依赖）。
  - `frontend/src/components/layout/TaskCreateDialog.vue`：新增"场景模板"下拉 + 预设摘要回显 + 成功后自动展开细节栏。
  - `frontend/src/stores/task.js`：`createTask` 支持 `scenario_domain` → 建任务后自动 `applyScenario`。
  - `frontend/src/components/layout/DetailDock.vue`：四类挂载 tile + 场景域 tag/场景条展示。
  - `frontend/src/components/layout/LeftPanel.vue` / `PromptInput.vue` / `stores/ui.js`：建任务开关预选域接线；`PromptInput` 移除模板 banner。
  - `frontend/src/stores/scenario.js`、`frontend/src/api/scenarios.js`：新场景域清单 store/api（冷启动/细节栏共用）。
  - 删除：`frontend/src/stores/prompt.js`、`frontend/src/api/prompts.js`（P3 快捷条唯一数据源，无残留引用）。
- 后端 / 数据库 / 依赖：**零改动**。消费 P9 scenario-templates 的 `GET /api/scenarios` 与 `POST /api/tasks/<id>/scenario/apply`。
