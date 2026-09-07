## Purpose

任务级能力装配（CAP-01~04）：以关联表把 技能/Skill、MCP/MCPConnector、知识库/KnowledgeBase、专家/Expert 四类能力按任务粒度挂载持久化，提供全量覆盖式更新与读取 REST 契约及存在性校验，作为 P5 注册中心供给实体、P7 细节栏呈现、P8 运行时装配的统一数据底座。仅数据关联，不含运行时执行。

## Requirements

### Requirement: 四类能力实体的持久化基础

系统 SHALL 持久化 Skill、MCPConnector、KnowledgeBase、Expert 四类能力实体（字段对齐 §5.2：技能含 name/description/skill_md/enabled，MCP 含 transport/command/args/url/trust/enabled，知识库含 name/space_id/embedding_provider/chunk_size/status；专家 C5 起为**运维专家档案**，含 name/description/system_prompt/role/enabled + preset_skills/preset_mcp/preset_kb/preset_library（JSON id 数组）+ default_provider_id/default_model_name，composed_of 为遗留列），作为任务挂载的目标；系统 SHALL 以任务到每类实体的多对多关联表承载挂载，同一任务对同一实体至多关联一次。

#### Scenario: 迁移后实体与关联可承载挂载

- **WHEN** 数据库完成迁移（含四类实体表与关联表），且存在至少一个任务与一条技能实体
- **THEN** 该任务可成功挂载该技能，挂载结果可读取回显，证明实体与关联存储可用

#### Scenario: 重复挂载同一实体被拒绝

- **WHEN** 用户在一条挂载请求中对同一技能的 id 重复给出两次
- **THEN** 请求以 400 拒绝，数据库不写入重复关联

### Requirement: 全量覆盖式更新挂载

系统 SHALL 支持 `PUT /api/tasks/<id>/caps`：请求体含 `skills`/`mcps`/`kbs`/`experts` 四类 id 数组，将当前挂载全量覆盖为请求体所描述的集合；请求体缺失的分类 SHALL 视为清空该分类（PUT 全状态语义，幂等）；成功返回 200 与更新后的完整挂载清单。任务不存在时 SHALL 返回 404。

#### Scenario: 挂载后读取回显一致

- **WHEN** 用户对某任务 PUT `{skills:[1], mcps:[1], kbs:[1], experts:[1]}`（各 id 均为已存在实体）
- **THEN** 返回 200，且随后 GET 读回的四类清单与本次请求完全一致

#### Scenario: 覆盖式替换旧挂载

- **WHEN** 某任务已挂载 skill 1、2，用户再 PUT `{skills:[2,3]}`
- **THEN** 读取该任务只含 skill 2、3，skill 1 的旧关联被覆盖清除

#### Scenario: 缺失分类被清空

- **WHEN** 某任务已挂载 mcp 1，用户 PUT 仅含 `{skills:[]}`（缺省其余分类）
- **THEN** 读取该任务 skills 为空且 mcp 亦为空——未被写到的分类一并清空

### Requirement: 挂载引用校验

系统 SHALL 在写入挂载前校验请求：`task` 不存在返回 404；四类数组的元素 SHALL 为对应实体表中已存在的正整数 id（布尔/字符串/浮点/非正整数均视为非法）；同一数组内重复 id 视为非法；请求含未知分类键视为非法。任一类校验失败 SHALL 返回 400 且不改变既有挂载（整体事务，不部分写入）。

#### Scenario: 挂载不存在的实体被拒绝

- **WHEN** 用户挂载一个不存在于任何实体表中的 id（如 99999）
- **THEN** 返回 400，消息指出非法 id，且该任务既有挂载保持不变

#### Scenario: 非法元素类型被拒绝

- **WHEN** 请求数组中含字符串/负数/浮点等非正整数元素
- **THEN** 返回 400，不写入任何关联

#### Scenario: 校验失败不改动原挂载

- **WHEN** 某任务已挂载 skill 1，再 PUT `{skills:[1,99999]}` 因 99999 不存在而失败
- **THEN** 返回 400 后读取，该任务仍只含 skill 1（无部分更新）

#### Scenario: 任务不存在返回 404

- **WHEN** 对不存在的 task id 调用挂载更新
- **THEN** 返回 404

### Requirement: 读取当前挂载清单

系统 SHALL 支持 `GET /api/tasks/<id>/caps` 返回该任务当前的完整挂载清单（`skills`/`mcps`/`kbs`/`experts` 四组 id，随带任务 id）。任务不存在返回 404。新建任务默认无任何挂载，读回四组为空。

#### Scenario: 新任务挂载为空

- **WHEN** 新建一个任务且从未挂载任何能力
- **THEN** GET 该任务 caps 返回四组均为空数组

#### Scenario: 读回与最近一次挂载一致

- **WHEN** 任务经过若干次 PUT 后调用 GET
- **THEN** 返回的清单与最近一次成功 PUT 的请求体一致

### Requirement: 删除任务级联清理挂载

系统 SHALL 在删除任务时级联清除该任务的全部能力挂载关联，不留孤儿子行。

#### Scenario: 删任务后挂载消失

- **WHEN** 删除一个已挂载多种能力的任务，随后尝试读取其挂载
- **THEN** 任务已不存在（GET caps 返回 404），且数据库关联表中无该任务遗留行

### Requirement: 运行时装配读取（供 P8）

系统 SHALL 提供按任务聚合读取已挂载实体的能力（service 层，非 REST），供后续运行时在不触碰关联表细节的情况下取到该任务已挂载的 Skill/MCPConnector/KnowledgeBase/Expert 实体记录；未挂载某类时该类返回空。此读取 SHALL 反映最近一次成功挂载的结果。

#### Scenario: 聚合读到已挂载实体

- **WHEN** 某任务已挂载一条技能与一条知识库，调用聚合读取
- **THEN** 返回中技能类含该技能实体记录、知识库类含该知识库实体记录，其余类别为空，且与最近挂载一致

#### Scenario: 未挂载分类聚合为空

- **WHEN** 读取一个仅挂载了技能的聚合
- **THEN** 未挂载的 MCP/知识库/专家分类返回空集，调用不报错

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
