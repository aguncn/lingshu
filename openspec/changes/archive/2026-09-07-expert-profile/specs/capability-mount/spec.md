## MODIFIED Requirements

### Requirement: 四类能力实体的持久化基础

系统 SHALL 持久化 Skill、MCPConnector、KnowledgeBase、Expert 四类能力实体（字段对齐 §5.2：技能含 name/description/skill_md/enabled，MCP 含 transport/command/args/url/trust/enabled，知识库含 name/space_id/embedding_provider/chunk_size/status；专家 C5 起为**运维专家档案**，含 name/description/system_prompt/role/enabled + preset_skills/preset_mcp/preset_kb/preset_library（JSON id 数组）+ default_provider_id/default_model_name，composed_of 为遗留列），作为任务挂载的目标；系统 SHALL 以任务到每类实体的多对多关联表承载挂载，同一任务对同一实体至多关联一次。

#### Scenario: 迁移后实体与关联可承载挂载

- **WHEN** 数据库完成迁移（含四类实体表与关联表），且存在至少一个任务与一条技能实体
- **THEN** 该任务可成功挂载该技能，挂载结果可读取回显，证明实体与关联存储可用

#### Scenario: 重复挂载同一实体被拒绝

- **WHEN** 用户在一条挂载请求中对同一技能的 id 重复给出两次
- **THEN** 请求以 400 拒绝，数据库不写入重复关联

## ADDED Requirements

### Requirement: 档案快照装配到任务（专家档案套用）

系统 SHALL 提供 `POST /api/tasks/<id>/expert/apply`（请求体 JSON 必填 `expert_id`），把一份运维专家档案**快照装配**到一个任务：任务不存在 → 404；档案不存在 → 404；档案 `enabled=false` → 400（均不产生任何副作用）。成功时系统 SHALL 依序装配：

- **四类 caps 全量覆盖**：复用 `PUT /api/tasks/<id>/caps` 的既有存储/引用规则写挂载——`experts` 恰为 `[档案自身]`（档案=该任务人设提供者）；`skills`/`mcps`/`kbs` 取档案对应 `preset_*` 中**现存且可用**的实体 id（技能/MCP 须 `enabled`、知识库须 `status='ready'`）；预设引用已被删除或停用/未就绪 SHALL 计入 `skipped`（含原因）而不中断套用。
- **预设资料库补挂为任务引用**：对 `preset_library` 中引用的 LibraryFile，任务已引用则跳过、文件已删则计 skipped，缺失的调 `attach_library` 补挂；**只增不拆**——不解除任务既有的手工资料引用。
- **默认模型（可选）**：档案设了 `default_provider_id` 才把任务模型绑定落成该供应商（`default_model_name` 空 → 用该供应商 default_model）；未设则**不动**任务既有模型绑定，不因套用档案抢走用户显式选的模型。

套用即快照：挂载专家时 SHALL 把其 `system_prompt` 定格为 `task_expert.persona_snapshot`（停用档案此刻不落快照），此后编辑/停用档案不影响已建任务（运行时人设解析见 agentscope-runtime「任务挂载能力注入」）。响应 SHALL 返回装配汇总 `{task_id, expert_id, mounted{skills,mcps,kbs,experts}, skipped[], library{added,existing,skipped}, model|null}` 供前端提示。

#### Scenario: 套用后挂载与资料库引用反映档案

- **WHEN** 对一个已手工挂载其它能力的任务套用一份含预设技能/MCP/RAG/资料且均可用的启用档案
- **THEN** 返回 200 与汇总；四类 caps 被覆盖（experts=[档案]、技能/MCP/RAG=可用预设 id），资料引用补齐为档案 preset_library，读回一致

#### Scenario: 失效预设计入 skipped 不中断

- **WHEN** 档案预设引用了已被删除或停用/未就绪的技能、MCP、知识库或库文件
- **THEN** 套用仍成功（200），`skipped` 逐项列 {category,id,reason}；已删除实体不产生挂载、无错误副作用

#### Scenario: 档案默认模型只在给了供应商时落绑定

- **WHEN** 档案设 default_provider_id 且任务已有其它绑定；另对一份未设 provider 的档案套用到显式绑了模型的任务
- **THEN** 前者任务模型绑定切到该档案供应商（model_name 空回落 default_model）；后者任务既有模型绑定原样保留

#### Scenario: 停用档案与缺失任务被拒

- **WHEN** 对不存在的任务、停用档案、或不存在的档案发起 apply
- **THEN** 分别返回 404 / 400 / 404，任务的既有挂载、资料引用与模型绑定均不变

#### Scenario: 二次套用幂等、改档案不影响已套任务

- **WHEN** 同一档案对已套用过的任务再次 apply；另一份档案被套用后其 system_prompt/启停被修改
- **THEN** 二次 apply 不重复补挂已存在的资料引用（幂等）；改档案后已套用任务的挂载与人设快照不变（快照已定格）
