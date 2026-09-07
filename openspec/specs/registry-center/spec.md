## Purpose

注册中心（design AD-01~04）：为技能 / MCP 连接器 / 知识库 / 运维专家档案四类能力实体提供统一 REST 管理面——CRUD、密钥保护、连接器连通性测试、知识库文档上传切块与关键词检索、运维专家档案组装（预设技能/MCP/RAG/资料与可选默认模型）；作为 P4 任务挂载与 P8 运行时装配的实体供给方。仅管理实体与字段，不含运行时执行与装配门控。

## Requirements

### Requirement: 技能中心管理（AD-01）

系统 SHALL 提供 `/api/skills` 的完整 CRUD：`GET /api/skills`（列表）与 `POST /api/skills`（新建）与 `GET /api/skills/<id>` / `PATCH /api/skills/<id>`（部分更新）/ `DELETE /api/skills/<id>`。技能字段含 name/description/skill_md/version/enabled；name 必填且全局唯一（重名返回 400）；新建默认 version=1、enabled=true。PATCH 只应用请求中出现的字段；当提供的 skill_md 与现值不同时 version SHALL 自增 1（记录指令文本迭代，供运行时缓存失效判断）。enabled 经 PATCH 启停。删除技能 SHALL 级联清除其在各任务上的挂载，不留孤儿子行。

#### Scenario: 新建技能、编辑 SKILL.md 与启停

- **WHEN** 用户 POST 新建技能 {name, description, skill_md} 成功，随后 PATCH 提供不同的 skill_md 并设 enabled=false
- **THEN** 创建响应含 id、version=1、enabled=true；PATCH 后读回该技能 version=2、enabled=false、skill_md 为新文本

#### Scenario: 重名技能被拒绝

- **WHEN** 用户再次 POST 一个已存在的 name
- **THEN** 返回 400，消息指明 name 冲突，不产生新行

#### Scenario: 删除被任务挂载的技能级联清理挂载

- **WHEN** 某任务已挂载该技能，用户 DELETE 该技能
- **THEN** 返回成功且该技能消失；随后 GET 该任务的挂载清单不再包含该技能 id，关联表无遗留行

### Requirement: MCP 连接器管理（AD-02）

系统 SHALL 提供 `/api/mcp` 的完整 CRUD。字段含 name/transport/command/args/url/trust/enabled 及 env/headers。name 必填唯一（重名 400）；transport 取值白名单 {stdio,http}，默认 stdio；transport=stdio 时 command 必填，transport=http 时 url 必填（缺必填返回 400）；args 为字符串数组，env 与 headers 为字符串键值对象。新建默认 trust=false、enabled=true。PATCH 只应用请求出现的字段；env/headers 提供对象即整体替换、提供 null 即清除、不提供保持不变。连接器在删除时 SHALL 级联清除其任务挂载。

#### Scenario: transport 依赖的必填字段校验

- **WHEN** 用户 POST 一个 transport=http 但没有 url 的连接器，或 transport=stdio 但没有 command 的连接器
- **THEN** 返回 400，消息指明缺失字段，不创建行

#### Scenario: 连接器出口不泄露 env/headers 值

- **WHEN** 用户创建含 env={KEY1:secret,KEY2:x} 与 headers={Authorization:bearer} 的连接器后读取之
- **THEN** 任何读取出口都不含 secret/bearer 等明文或密文本身，只以键名列表呈现已配置的 env_keys/headers_keys；提供的值仅影响内部存储

#### Scenario: 清除与替换 env/headers

- **WHEN** 用户 PATCH 该连接器 headers=null 且换新 env 对象
- **THEN** 读回 headers_keys 为空、env_keys 为新对象的键，旧 env 全部被替换

### Requirement: MCP 连接器连通性测试（AD-02）

系统 SHALL 提供 `POST /api/mcp/<id>/test` 对连接器做真实连通性测试：连接器不存在返回 404；transport=stdio 时以 command+args（并携带其 env）启动子进程完成最小 MCP 握手并请求工具列表，transport=http 时向 url（携带其 headers）发起探测。单次测试须设超时（默认 10s）并确保进程回收。测试不通过属预期业务结果而非服务异常：SHALL 返回 200 且 ok=false 并附可读 reason（含进程未找到/超时/握手失败等），绝不 5xx；成功返回 200 且 ok=true 并含返回的工具名清单与工具数量。

#### Scenario: 测试不存在的连接器

- **WHEN** 用户对不存在的 id 调用连通性测试
- **THEN** 返回 404

#### Scenario: 可响应工具列表的 stdio 服务端

- **WHEN** 用户对一台能完成 initialize 握手并响应 tools/list 的 stdio 服务端调用测试
- **THEN** 返回 200 且 ok=true，含非空工具清单与工具数量（数量等于该服务端声明工具数）

#### Scenario: 服务端不可用或启动失败

- **WHEN** 连接器的 command 在本机不存在、启动即退出、或握手超时
- **THEN** 返回 200 且 ok=false，reason 概述失败环节（如无法启动/超时/握手失败），调用方不收到 5xx

### Requirement: 知识库中心管理（AD-03）

系统 SHALL 提供 `/api/kb` 的 CRUD：`GET /api/kb` 与 `POST /api/kb` 与 `PATCH /api/kb/<id>` 与 `DELETE /api/kb/<id>`。字段含 name/space_id/embedding_provider/chunk_size/status；name 必填唯一（重名 400）；chunk_size 为正整数、默认 400；status 取值白名单 {draft,ready,disabled}、默认 ready。PATCH 只应用请求出现的字段。删除知识库 SHALL 级联删除其全部切块与其任务挂载。status=disabled 的知识库不接受 upload 与 search（返回 400）；draft/ready 供界面标记，本提案不做额外门控，装配门控归 P8。

#### Scenario: 建库、改状态与停用门控

- **WHEN** 用户 POST 新建 {name, chunk_size} 成功后 PATCH status=disabled
- **THEN** 创建响应默认 status=ready；停用后对该库调用 upload 或 search 返回 400；再 PATCH status=ready 后恢复可用

#### Scenario: 删除知识库级联清理切块

- **WHEN** 一个已含若干切块且被任务挂载的知识库被 DELETE
- **THEN** 返回成功；该库及其全部切块行消失，任务挂载清单不再包含该库，关联表无遗留行

### Requirement: 知识库文档上传与切块（AD-03）

系统 SHALL 提供 `POST /api/kb/<id>/upload`（multipart，字段 file）将文本文档解析并切块写入该库：库不存在返回 404、库已停用返回 400。仅受理 `.txt` 与 `.md` 且能以 UTF-8 解码的文件；其它类型（如 .pdf/.docx）返回 400 并明确提示本期暂不支持。文本 SHALL 按该库 chunk_size 切分为有序切块（每条含正文内容与来源元数据，file 引用字段本期置空、留待 P6 资料库回填）。同一知识库内以文件名区分文档：再次上传同名文件 SHALL 以本次为准替换该文件的旧切块，其它文件切块不受影响。成功后返回文件名、字符数与切块数。

#### Scenario: 上传 md 并切块

- **WHEN** 用户向某库上传一个 UTF-8 的 .md 文件且内容长度超过其 chunk_size
- **THEN** 返回 200 含该文件名、字符数与大于 1 的切块数；切块行按序落在该库名下且携带来源文件名元数据

#### Scenario: 不支持的文档类型

- **WHEN** 用户上传 .pdf 或 .docx 或无法按 UTF-8 解码的文件
- **THEN** 返回 400，消息明确该类型本期暂不支持（或编码不可解），该库切块不变

#### Scenario: 同名重传替换旧块、异名保留

- **WHEN** 用户先上传 a.md 与 b.md，再上传内容更短的同一 a.md
- **THEN** a.md 的切块被本次内容整体替换（数量随新内容变化），b.md 的切块原样保留

### Requirement: 知识库关键词检索（AD-03）

系统 SHALL 提供 `POST /api/kb/<id>/search`，请求体含必填非空 query 与可选 top_k（默认 5、上限 20，超限收敛到上限）。库不存在返回 404、库停用返回 400、query 为空返回 400。检索 SHALL 以关键词对库内切块做命中计分并返回分数降序的 top-k 切块，每块含正文、来源文件名与块序号；无命中的词返回空数组。这是默认关键词检索；向量化检索本期关闭。

#### Scenario: 命中相关切块

- **WHEN** 用户对已含某关键词文本切块的库提交含该关键词的 query
- **THEN** 返回 top-k 中该切块分数最高在前，且带其正文与来源文件名

#### Scenario: 空查询与无命中

- **WHEN** 用户提交空 query，或提交在库内无任何命中的 query
- **THEN** 空 query 返回 400；无命中返回 200 且结果为空数组

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
