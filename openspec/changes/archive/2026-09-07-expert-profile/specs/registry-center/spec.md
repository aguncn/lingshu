## MODIFIED Requirements

### Requirement: 专家管理与多专家组合（AD-04）

系统 SHALL 提供 `/api/experts` 的 CRUD：`GET /api/experts` 与 `POST /api/experts` 与 `GET /api/experts/<id>` / `PATCH /api/experts/<id>` 与 `DELETE /api/experts/<id>`。C5 起专家为**可复用「运维专家」档案**：字段含 name/description/system_prompt（人设）/role/enabled，以及档案预设——`preset_skills`/`preset_mcp`/`preset_kb`/`preset_library`（JSON id 数组，分别指向 Skill/MCPConnector/KnowledgeBase/LibraryFile）与可选默认模型 `default_provider_id`（→ ModelProvider）/`default_model_name`（空=用供应商 default_model）。name 必填唯一（重名 400）；role 取值白名单 {ops-sme,general}、默认 general；新建默认 enabled=true。档案预设 id 数组写入时 SHALL 逐维校验：元素须为正整数、同一数组内不重复、每个 id 在对应实体表中存在（否则 400）；`default_provider_id` 非空须指向现存供应商（否则 400）。`composed_of` 为 P1 多专家协作的**遗留列（deprecated）**：保留列与删除守卫、前端不再暴露，写入语义不变——元素须正整数、在专家表中存在、不含自身、同一数组内不重复，否则 400。列表类出口返回原始 composed_of 与基础字段（含 preset_*/default_*）；单条读取额外把子专家解析为含 {id,name,role} 的对象列表字段。PATCH 只应用请求出现的字段；enabled 经 PATCH 启停。删除专家 SHALL 级联清除其任务挂载；若该专家正被其它专家的 composed_of 引用则返回 400（引用完整性），防止悬空组合。把档案「套用」（快照装配）到一个任务见 capability-mount「档案快照装配到任务（专家档案套用）」；套用时停用档案 SHALL 被拒。

#### Scenario: 组合多专家并可读回子专家明细

- **WHEN** 用户先建专家 A，再新建专家 B 并在 composed_of 中给 A 的 id
- **THEN** 创建 B 成功；GET /api/experts/<B> 返回 composed_of=[A] 且含解析出的子专家对象（A 的 id/name/role）（composed_of 为遗留兼容语义，前端组装不再暴露）

#### Scenario: 非法组合被拒绝

- **WHEN** 用户在 composed_of 中包含自身 id、或不存在于专家表的 id、或重复 id
- **THEN** 返回 400，不写入

#### Scenario: 引用完整性拒绝删除与非法角色

- **WHEN** 用户尝试删除一个被其它专家 composed_of 引用的专家，或为专家设置不在白名单的 role
- **THEN** 删除被拒绝返回 400 并说明其仍被引用；非法 role 返回 400

#### Scenario: 档案预设与默认模型的写时校验

- **WHEN** 用户 POST/PATCH 档案时 preset_skills/preset_mcp/preset_kb/preset_library 内混入不存在或非正整数/重复的 id，或 default_provider_id 指向不存在的供应商
- **THEN** 返回 400 且不写入该字段（新建/更新整体失败，不产生悬空引用）
