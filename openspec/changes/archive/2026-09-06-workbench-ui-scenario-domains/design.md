## Context

`workbench-ui` 主规范在顶部条、建任务、细节栏三处仍停留在 P3 描述：顶部需求写的是"提示词模板快捷入口"（消费 `GET /api/prompts?category=task-preset`）。P9 `scenario-templates` 交付了 `GET /api/scenarios`（固定十二域序 + name + 装配摘要）与 `POST /api/tasks/<id>/scenario/apply`（置 `scenario_domain` + 按预设覆盖挂载 caps），并在其 D1 Non-Goal 声明"新建任务选域/顶部分类/细节栏展示属 workbench-ui 后续提案"。本会话以验收补丁实现了这批前端行为并随 P9 验收跑通，现正式立案——**设计文档是对既有已实现行为的权威记录**，改写主规范使其回到与代码一致的可验收状态。动机见 proposal.md；实现文件清单见 proposal.md - Impact。

## Goals / Non-Goals

**Goals:**
- 主规范顶部条/建任务/细节栏三条需求与当前代码语义一致（场景域驱动）。
- 记录"域条点选 → 建任务自动套用 → 细节栏可见装配"这条产品闭环的前端装配方式与共享状态归属。
- 让 tasks 每条 = 一个已实现且可单独验收的行为锚点，供 verify 逐条核对。

**Non-Goals:**
- 不改后端契约：本域纯前端，只消费 scenario-templates 与既有 caps/messages/模型接口。
- 不重建"提示词模板快捷条"：其语义已被场景域条取代（spec REMOVED）。
- 不做运行时行为改动：域注入、apply 服务端语义均在 scenario-templates 域已定，本域只消费。

## Decisions

- **D1 顶部条语义级替换：P3 提示词模板 → 十二场景域条（spec REMOVED + ADDED）。** 选 `/api/scenarios` 而非提示词接口的原因：域条点击要落到"装配真实预设"（P9 apply 置 `scenario_domain` + 挂载），而 P3 提示词 chip 只能带一段文本、其"带入会话"注入从未落地，且与 P9 域提示词重复。故顶部条 chip 点击 = `ui.openCreateTask(d.domain)`（预选域 → 建任务自动套用）；连带删除 `frontend/src/stores/prompt.js`、`frontend/src/api/prompts.js` 与 PromptInput"已选模板"横幅（grep 确认无残留消费，vite build 通过）。
- **D2 域清单一次装载、三处共享，放 pinia store。** `stores/scenario.js` 单例持有 `domains/byDomain/labelOf/ensureLoaded({force})`；顶部条、建任务下拉、细节栏场景名翻译（labelOf 键→中文名，清单未载/键未知时原样回退键、不空白）共用同一份数据。装载编排：左栏 onMounted `ensureLoaded()` 冷启动拉取；注册表清单同理供细节栏把挂载 id 译为可读名（详情 dock onMounted 补拉 reg + scenario，getter 有缓存、空转 cheap）。
- **D3 选域是瞬时动作，落地 `ui.taskDialogDomain`，关闭即清空。** "点顶部哪个域建任务"是一次性编排意图，不适合做持久选中态。`ui.taskDialogDomain` 在建任务对话框打开时写入预选值、对话框关闭即置 `''`；顶部 chip 的 `active` 高亮只存在于「对话框开启且域匹配」时，避免上次选域残留误导。左栏「新建任务」按钮 `openCreateTask()`（无参）→ 默认不绑域，与旧行为一致。
- **D4 建任务自动套用 = 前端两段编排，不合并后端接口。** `task.createTask(payload)` 收到 `scenario_domain` 时：先 `POST /api/spaces/<sid>/tasks` 建任务（P2 契约零改动）→ 成功后再 `POST /api/tasks/<id>/scenario/apply`；返回 `r.domain` 写回本地任务对象使选中态/细节栏立即可读。错误分级：`r.skipped` 非空 → warning 列原因（提示去细节栏「编辑挂载」补全）；apply 抛错 → warning「任务已创建，套用失败可稍后手动挂载」，绝不阻断创建（任务已落库）。成功后 `ui.detailOpen = true` + success「已创建并套用「域」预设」，让装配立即可见。两段编排保持 P2/P9 各自单职责，前端仅在"绑了域"时多调一次。
- **D5 细节栏四类挂载 tile 同构渲染 + 共用同一全量覆盖编辑器。** 挂载区用 `MOUNT_KINDS = ['skills','mcps','kbs','experts']` 驱动四类 tile（标题、编辑按钮、行/空态文案同一套模板），各自独立读 `task.caps[kind]` 真实挂载；行名经 `reg.bySkillId/byMcpId/byKbId/byExpertId` 译为可读名（缺失回退 `#id`），`itemOk` 判定停用（`enabled`）/未就绪（kb `status==='ready'`）→ 弱化标注「· 停用」。四类共用同一个 `CapMountDialog` 的原因：caps 是 `PUT` 全量覆盖语义，若每类一个独立编辑器，用户改某一类时提交会把其余三类清空；单一编辑器在提交时带全量四类即无此风险。主规范 R6 原仅显式写技能/MCP 分区，本设计把知识库/专家也提为同级独立分区（spec MODIFIED 同步）。
- **D6 场景域标记是纯展示层，不新增存储。** 细节栏开关行（`el-tag`）与展开体顶部「场景」条的值均取自 `task.scenario_domain`（P2 既有列）经 `scenario.labelOf` 译名；未绑域不渲染。展开体场景条附注「已按该域预设装配；增删改请用下方各分区编辑挂载」——引导用户在 apply 之后走既有 PUT caps 微调，与 scenario-templates D4 的"模板装配 + 人工微调"流程一致。
- **D7 验收以"行为锚点 + 前端可运行"为准。** 本域纯前端且后端场景域测试已在 scenario-templates 覆盖（`backend/tests/test_scenarios.py`，104 全绿），故前端不自建单测体系；tasks 每条锚定一个 spec 场景的静态证据（组件/接口引用），验收 = `cd frontend && npm run build` 通过 + 启动前后端按「验收清单」手工复核三处观感。

## Risks / Trade-offs

- [主规范 REMOVED 提示词模板条，若未来要恢复 P3 提示词快捷入口需另立案] → 提示词库能力若由 model-prompt-config 后端保留，仅不再经顶部条暴露；恢复是 ADDED，非破坏。
- [顶部条横向滚动承载十二域，窄屏观感依赖 flex/overflow-x] → chip 容器 `overflow-x: auto` 不换行挤高，域名固定不截断；超出可横向滚动。
- [清单接口失败 → 顶部条降级空态，建任务下拉少 12 域但手动挂载路径完整可用] → 降级文案 + 重试按钮，`ensureLoaded({force})` 可重拉；会话区与左栏不受阻。
- [apply 自动覆盖 caps 会清掉此前手工挂载] → 仅在"绑了域的新建任务"触发，模板语义使然；套用后仍可 PUT caps 微调，D6 注明。
- [纯前端立案无自动化测试，verify 主要靠代码证据 + build] → tasks 每条带精确文件锚点，verify 逐条核对；前端 build 作为机器可跑的最小门禁。

## Migration Plan

无数据库迁移、无后端部署步骤。交付 = 前端重新构建发布；本域消费的 `GET /api/scenarios` 与 `POST /api/tasks/<id>/scenario/apply` 依赖后端已完成的 scenario-templates 迁移与种子（独立交付过）。回滚：git 还原本批前端改动即回到 P3 提示词条形态，但主规范文本已随归档同步为新语义——如需真回退提示词条需另立案恢复，属预期。

## Open Questions

无。
