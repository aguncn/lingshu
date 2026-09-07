## 1. 只读自定义工具基座（探索/加固）

- [x] 1.1 确认 `agentscope.tool.FunctionTool` 注册只读同步函数的可行封装：`FunctionTool(func, name=…, description=…, is_read_only=True)`，验证返回 `ToolChunk(content=…, state="success", is_last=True)` 即可被既有 `_map_event`（ToolCall/ToolResultEnd）当作普通工具流转
- [x] 1.2 权限探针：在 strict/limited/trusted 三档下确认只读工具调用**不**产生 `RequireUserConfirmEvent`；若 DEFAULT 档仍会问确认，则在装配层给两类工具挂「只读免确认」兜底并记录（补单测断言）
- [x] 1.3 slug 工具名归一化辅助：ASCII 小写化 + 非法字符清洗 + 唯一化（冲突/无法归一化回退 `skill_<id>`）

## 2. 技能改「按需取用的只读工具」

- [x] 2.1 `_skills_block`/常驻注入移除：`_compose_system_prompt` 不再把 `skill_md` 全文拼进系统提示；系统提示只保留角色 + 任务上下文（+ 域模板段）
- [x] 2.2 `build()` 为「挂载且启用且 `skill_md` 非空」的技能各装配一个 `skill_<slug>` 只读工具（描述含技能名/用途），调用返回 `skill_md` 全文；停用/空 md 不出现
- [x] 2.3 装配面 desc 增技能工具清单（`skill_tools`），替换原注入技能名语义；单测：可用技能→工具可调用且返回其文本、停用/空 md→不出现、无技能→不装配

## 3. 知识库检索工具（复用关键词 search）

- [x] 3.1 `registry_kb` 增跨库合并 `search_kbs(kb_ids, query, top_k)`：复用既有单库关键词计分，各库取 top 后按 (score,来源) 全局归并 top-k；单测覆盖跨库合并/空库/无命中
- [x] 3.2 `build()` 装配只读 `knowledge_search` 工具：闭包快照任务挂载且 `status=='ready'` 的库 id；入参 `query` 必填、`top_k` 可选（默认 5、上限 10 收敛）；结果每条带 `[来源: 库/文件 第n块 得分]`
- [x] 3.3 未挂载可用库时：工具仍装配、调用返回明确「无可用库/无命中」文本不报错；desc 反映检索工具装配与否

## 4. 追溯/摘要自动承接（后端事件通道 + 前端分类）

- [x] 4.1 后端验证：技能取用/知识库检索调用后，SSE `tool_call`/`tool_result` 与 `GET /messages` 的助手回合 trace 自动含对应步骤（提案 1 追溯模型，无需新记录）
- [x] 4.2 前端 `utils/trace.js`：`classifyTool` 增桶——`skill_` 前缀 → `skill`（技能）、`knowledge_search` → `kb`（知识库）；`BUCKET_LABEL`/`BUCKET_ORDER`/`summarizeSteps` 纳入新桶；未知仍落 `tool`
- [x] 4.3 前端 `AssistantTrace.vue` 装配弱化标记与「已装配 vs 已调用」口径对齐（kbs 措辞统一为「知识库」），新桶调用与弱化标记不双计

## 5. 测试与验收收尾

- [x] 5.1 `uv run pytest backend/tests/ -q`：新增技能取用工具/检索工具/权限探针/改挂载生效/跨库合并用例全绿；既有系统提示断言同步为「技能经工具取用」
- [x] 5.2 `cd frontend && npm run build` 通过
- [x] 5.3 浏览器手工验收：挂技能任务让模型取用→摘要出现「技能」、过程可展开；挂两个知识库→检索返回带来源文本、摘要出现「知识库」；strict 档下写类仍确认、检索/取用不确认；未调用能力仍只弱化标「已装配」
