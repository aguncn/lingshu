## Context

- 动机见 proposal.md（P4 已落四实体表 schema-only + 任务挂载/load_mounted，实体缺管理面）。
- 现状事实（来自代码，非臆测）：四实体模型集中在 `backend/models.py` P4 区（Skill/MCPConnector/KnowledgeBase/Expert，行号 307~417），白名单常量已就位（MCP_TRANSPORTS/KB_STATUSES/EXPERT_ROLES 等）；能力列 args/env/headers/composed_of 为 `db.JSON`；`MCPConnector.to_dict()` 刻意不吐 env/headers（见其 docstring）。迁移 0001~0003 建表、0003 建 skills/mcp_connectors/knowledge_bases/experts + 关联表，级联（ON DELETE CASCADE/SET NULL）依赖 app.py 每连接 `PRAGMA foreign_keys=ON`。
- 密钥先例：`crypto.py` 提供 `encrypt/decrypt/mask_key`（LINGSHU_MASTER_KEY → 根 .env 生成持久化），`model_service.create_provider` 把 api_key 立即 Fernet 加密落 `api_key_enc`(db.Text token)，出口只出掩码——本提案沿用同一模式。
- 契约先例：api 层蓝本 = `api/model_prompt.py`——POST 创建返 `(dict, 201)`、PATCH 只转发请求中出现的字段、DELETE 返 `{"ok": True}`、service 抛 AppError 由域 errorhandler 收敛为 `{"message"}`；重名/被引用删除等业务拒绝 = `ValidationError(400)`。
- 两处任务书文字与本提案范围冲突，已被用户决策覆盖：① 任务书 P5 手工验收「未信任不可在任务挂载」与 P4 已归档挂载行为（trust=0 可挂载、load_mounted 不过滤）矛盾 → 决策 A：信任门控归 **P8 运行时门控**，本提案只做 trust/status/enabled 字段管理，不改挂载/load_mounted；② 任务书 tasks#9「接入 agentscope.rag.TextParser(txt/md/pdf/docx)」 → 决策 B：**轻量零新依赖**，txt/md 标准库解析切块，pdf/docx 报「本期暂不支持」留 P1。

## Goals / Non-Goals

**Goals：**
- 四中心各一套 CRUD REST（技能/MCP/知识库/专家），行为即 spec 的 SHALL 条款，可 pytest + curl 双通道验收。
- 敏感字段（MCP env/headers）不落明文、不出明文/密文，复用 crypto 而非造轮子。
- 知识库 txt/md 真解析切块 + 关键词 top-k 检索，覆盖 AD-03 主路径；MCP 连通测试对 stdio 做真实工具握手。
- 与既有层约定（service 校验+事务、API 只转发、AppError、201/PATCH/DELETE 形态、models.py 白名单）保持一致。

**Non-Goals：**
- 不做运行时装配门控（trust/status/enabled 只作字段 PATCH，不在挂载/load_mounted 过滤）——留 P8。
- 不改前端页面：skill_md「预览」由 P5 的 GET 出口给出全文，渲染归前端提案；四中心工作台界面不在本期。
- 不做向量化 embedding / pdf/docx 解析 / 跨库聚合检索——留 P1。
- 不改动 P4 归档 spec、挂载 PUT/GET 契约与 load_mounted 签名。
- 不引入新第三方依赖（零依赖原则延伸到 MCP 测试与 KB 解析切块，均用标准库）。

## Decisions

**D1 路由与服务模块划分（沿用每域一个 service 文件 + 每域一个 blueprint）**
- `services/registry_skill.py`、`registry_mcp.py`、`mcp_test.py`、`registry_kb.py`、`registry_expert.py`；`api/skills.py`、`api/mcp_center.py`、`api/kb.py`、`api/experts.py`（各自 url_prefix=`/api`，AppError errorhandler 同构）。app.py 注册四个新 blueprint。
- 理由：单文件承载四中心会让 service 破千行（对比 model_service 单文件已 400 行）；按能力拆文件让 apply/verify 各任务落点清晰。备选「全并入既有域文件」被否：会与 model_prompt 等文件揉在一起、验收难对号。

**D2 MCP env/headers 改 Fernet 密文列（决策 C 落实）**
- `MCPConnector.env`/`headers` 列类型从 `db.JSON` 改 `db.Text`，存「整段 JSON 序列化后整体 Fernet 加密」的 token（与 `api_key_enc` 同构）。SQL 层两列本就 TEXT，0003 真实库尚未应用、更无任何明文数据 → **无 DDL/数据迁移**，仅改模型列类型。
- 写路径：service 收对象 → `json.dumps`（sort_keys, ensure_ascii=False）→ `crypto.encrypt` → 存 token。读路径：需要值时（仅连通测试与键名出口）`crypto.decrypt` → `json.loads`；`args` 非敏感维持 `db.JSON`。
- 出口：registry 层输出在 `to_dict()` 基础上附加 `env_keys`/`headers_keys`（解密后键名排序列表，永不含值）。解密失败（如换了 MASTER_KEY）回空列表不 500——沿用 `mask_key` 的容错取向。
- 备选：把 env/headers 拆成 N 个 `*_enc` 单值列被否——对象是可变集合、拆列爆炸且违背「整体加密」决策。

**D3 迁移 0004 建 knowledge_chunks（对齐 §5.2 字段）**
- 新增 `migrations/0004_registry.sql`：`knowledge_chunks(id, kb_id NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE, file_id INTEGER NULL, content TEXT NOT NULL, meta TEXT NOT NULL, embedding BLOB NULL, created_at, updated_at)` + `CREATE INDEX idx_knowledge_chunks_kb_id ON knowledge_chunks(kb_id)`。meta 存 `db.JSON`（含 filename/chunk_index/chars），embedding 可空 `db.LargeBinary` 本期恒 NULL（向量 P1 回填）。删知识库靠 DB 级联一次清切块与 task_kb 挂载。file_id 本期恒 NULL，语义 = 将来指向 P6 资料库的文件行，先占列后回填。
- 模型 `KnowledgeChunk` 加入 models.py 能力区；ORM 关系 `KnowledgeBase.chunks = relationship(..., cascade="all, delete-orphan", passive_deletes=True)` 仅作便利、真正级联仍走 DB。

**D4 KB 上传语义（决策 B 落实，spec R5）**
- multipart 字段 `file`；白名单扩展名 `{.txt,.md}`，文件内容按 UTF-8 严格解码（`UnicodeDecodeError` → 400「无法按 UTF-8 解码」）。
- 切块：去掉 BOM/规整换行后按 `chunk_size`（正整数，默认 400）**按字符**贪心切窗，不做词边界/句边界（单机小语料，语义损失可接受、零依赖）；产出 `chunk_index` 自 0 递增。空文档 → 0 块（合法）。
- 「同名替换、异名保留」：单事务内先 `DELETE ... WHERE kb_id=? AND json_extract(meta,'$.filename')=?` 再插入新块。SQLite 若缺 JSON1（json_extract 不可用）则回落：事务内先把该库切块全部读出、Python 侧剔除同 filename 行再重写——实现时二选一，测试保证「同名替换 + 异名保留」结果正确即可（设计不锁实现）。

**D5 KB 关键词检索（spec R6）**
- 分词 = `re.split(r'\s+', query)` 过滤空词；为让中文整句短语可命中，再附整段 trim 后的 query 作为一个词（子串精确匹配，无新依赖）。
- 计分：单块 score = Σ 每个词在 content 中 `count()`；排序 `(-score, chunk_index)`，取 top_k（默认 5、>20 收敛 20）。实现读取该库全部切块在 Python 侧计分——库小、单机、关键词默认检索定位，刻意不做全文索引，文档化为 trade-off；若 P1 引入向量再替换。

**D6 MCP 连通性测试（spec R3）**
- stdio：`subprocess.Popen([command, *args], stdin=PIPE, stdout=PIPE, stderr=PIPE, text=True, env=decrypted_env∪os.environ)`，进程启动即视为尝试连通；按 MCP stdio 换行分隔 JSON-RPC：发 `initialize`（id=1）→ 读响应 → 发 `notifications/initialized` → 发 `tools/list`（id=2）→ 取 `result.tools[].name`。任何环节抛错/超时(10s)/进程非零退出 → 杀进程并回 `ok=false` + reason（含 stderr 摘要，截断）。成功 → `ok=true, tools=[name...], tool_count=n`。
- http：向 url（携带解密 headers、Accept 覆盖 text/event-stream）POST `initialize`，收到可解析的 JSON-RPC 响应即视为连通 `ok=true`（不承诺拿全工具表——真实 http MCP server 本期罕见，详化握手留 P2 真连接器）。
- 选 stdlib 手写而非 AgentScope 异步 MCP client：本平台 Flask 同步请求路径里绕异步 event loop + queue 只为一次连通测试成本过高；一次最小握手即可达成「测真连通」意图。备选（AsyncIO 桥接 AgentScope client）记录在案，若真实连接器增多再换。
- 测试替身：`tests/fixtures/mcp_fake_server.py`（极简 JSON-RPC stdio 服务端，回 2~3 个 tools），测试用 `command=sys.executable, args=[fixture路径]` 驱动「成功」路径，与真实 `npx` 无关、可离线复现。

**D7 专家组合与删除完整性（spec R7）**
- 写入校验（create/update 共用）：composed_of 为 id 数组 → 元素正整数、`!= self.id`（防自引用）、去重、逐一在 experts 表存在 → 否则 400。允许嵌套引用其它组合型专家、暂不做环检测（P8 编排时校验；文档化为风险）。
- 出口：`GET /api/experts` 列表每项 = to_dict（含原始 composed_of id 数组）；`GET /api/experts/<id>` 附加 `composed` = 对 composed_of 解析出的 `[{id,name,role}]` 对象列表，供组合展示。
- 删除：先扫描全部专家 composed_of，若含被删 id → `ValidationError(400, "仍被专家 X 引用")`；否则删除（task_expert 挂载行由 DB 级联清）。同 model_service.delete_provider 的 ref_count 先例。

**D8 字段默认与校验汇总（对齐 spec + 既有先例）**
- 技能：name 必填唯一(400)、skill_md/description 可空、PATCH 触发 skill_md 变更→version+1、enabled 启停。
- MCP：name 必填唯一；transport∈{stdio,http} 默认 stdio；stdio 缺 command→400、http 缺 url→400；args 须字符串数组、env/headers 须对象否则 400；trust/enabled PATCH 可置。
- 知识库：name 必填唯一；chunk_size 正整数默认 400；status∈KB_STATUSES 默认 ready；disabled 的库 upload/search 拒绝(400)；space_id 空=全局库。
- 专家：name 必填唯一；role∈EXPERT_ROLES 默认 general；composed_of 默认空。
- 删除保护只对「专家被 composed_of 引用」这一处设防；实体被任务挂载的删除是放行并级联（沿 P4 语义）。

**D9 一致性修正**
- `capability.py` load_mounted 的 docstring 有「装配期门控属 P5」的过期字样（P4 期注释把门控估在 P5，用户决策已定 P8）。本期顺带把该注释更正为 P8，纯注释、不改行为，避免 verify 阶段判「设计不一致」。

## Risks / Trade-offs

- [stdio 测试对真实外部命令敏感（npx/Node 未装即 ok=false）] → 失败即业务结果非异常，reason 含 stderr 摘要；CI/验收用 `tests/fixtures/mcp_fake_server.py`（`sys.executable` 驱动）离线可复现「成功」，真实 server 留给手工验收。
- [http 连通判据偏弱（收到响应即通）] → 本期罕见真实 http 连接器，收紧握手留 P2；风险记录不阻塞。
- [关键词检索无索引，块多时 O(n) 扫描] → 库定位为单机小语料；P1 向量化/全文索引再替换；不为此引依赖。
- [纯字符切块会切断句/词，检索语义略降] → 接受零依赖换取的简单性；chunk 带 meta 可追溯来源便于人工纠偏。
- [env/headers 换 MASTER_KEY 后不可解 → 出口键名空、连通测试失败] → 与 mask_key 同款容错；改 key 属运维事故，失败可见可查。
- [composed_of 允许嵌套与潜在环] → P5 只做引用完整性与防自引用，环由 P8 编排期校验；如被引专家删除被 400 挡住，不会静默悬空。

## Migration Plan

1. 改模型（env/headers → db.Text、新增 KnowledgeChunk）→ 新增 `migrations/0004_registry.sql`（仅建 knowledge_chunks + 索引）。
2. `uv run pytest backend/tests/ -q`（旧测全绿）后再写 test_registry.py；真实库 `backend/data/app.db` 尚未应用 0003，重启后端时 migrate.py 按序 0003→0004（无数据需转换）。
3. 手工验收按提案验收命令跑 curl 链路（skills/mcp/kb/experts + mcp test + kb upload/search），随后清理临时数据。
4. 回滚：本提案无破坏性数据迁移；退回即回退 0004 文件并重启（knowledge_chunks 空表可弃）。

## Open Questions

- http 传输的详细工具握手成功判据：在首个真实 http MCP server 接入前无法定稿，收窄或扩展不影响本提案 spec/任务，P2 真连接器时再答。
- knowledge_chunks.file_id 与 P6 资料库的精确外键/去重规则：P6 建文件行后回填，本提案留 NULL 不阻塞。
- 切块是否引入句边界重叠：当前零依赖纯字符切窗可验收，是否升级为「重叠窗」由 P1 向量化一并决策。
