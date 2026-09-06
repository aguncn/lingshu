## Context

后端现为 P2/P3 全量：`users/spaces/memberships/tasks/file_records/model_providers/model_configs/prompt_templates`（迁移 0001/0002），无任何能力实体或「任务↔能力」关联。P7 工作台细节栏对 技能/资料/MCP/权限 四个分区为 EmptyState 占位，数据源空缺。任务书 P4(capability-mount) 先于 P5(registry-center)：**四张能力实体表原属 P5，但本提案的「挂载校验目标存在」「手工验收挂真实 id」都需要实体先行**——proposal 阶段经用户确认采用**前置实体表**：P4 一次落 4 实体表 + 4 关联表（schema-only，不做 CRUD/解析/连通等 P5 逻辑），P5 届时在其上补四中心 CRUD。详见 proposal.md。

## Goals / Non-Goals

**Goals:**
- 一次迁移建齐 8 张表，schema 字段对齐 §5.2，使 P5 可直接加 CRUD 而无需 ALTER。
- 提供全量覆盖式 `PUT /api/tasks/<id>/caps` 与 `GET`，及存在性/格式校验（防脏引用），整体事务。
- 任务删除级联清理挂载（DB 级，随 P2 删除链路自动生效）。
- `services/capability.py` 提供 P8 需要的「按任务聚合加载已挂载实体」读取。
- 迁移内 seed 极少量演示行（每类 1~2 条），保证 curl/手工验收无需先建库即可挂载。

**Non-Goals:**
- 不做 Skill/MCPConnector/KnowledgeBase/Expert 的 CRUD 接口（P5 registry-center）。
- 不做 MCP 连通性、KB 解析/切块/检索、专家编排、技能注入运行（P5/P8）。
- 不做「enabled/trust 生效才可挂载」的装配期门控（P5 定义 trust 语义后再加；本提案校验只认实体存在）。
- 不做空间/可见性越权过滤（单人 owner；KB 的 space_id 仅落 schema，越权检查留待权限域）。
- 不改前端、不加新第三方依赖、不改既有表。

## Decisions

**D1 — 四实体表 schema 完全按 §5.2 落盘，一步到位防 P5 返工。**
`Skill(name,description,skill_md,version,enabled)`、`MCPConnector(name,transport,command,args,env,url,headers,trust,enabled)`、`KnowledgeBase(name,space_id,embedding_provider,chunk_size,status)`、`Expert(name,description,system_prompt,role,composed_of,enabled)`，各带 TimestampMixin。`args/env/headers/composed_of` 为 JSON 文本列（SQLite TEXT，存 `json.dumps`），与 §5.2 的 `(json)` 一致，P5 无需改列型。`KnowledgeBase.space_id` 设 nullable FK→`spaces.id` ON DELETE SET NULL（null=全局库，删空间保留全局库）。每实体提供 `to_dict()`（不含任何密钥字段——MCP env 脱敏由 P5 出口处理）。白名单常量（如 transport∈stdio/http、KB status、Expert role）集中 models.py 顶部。
- 备选：实体表留给 P5 建、本提案关联列用普通整数无 FK（沿用 `Task.model_config_id` 先例）→ 会让「校验目标存在」与手工验收落空，用户已否。

**D2 — 关联表走真 FK + 双向 CASCADE + (task,目标) 唯一。**
`task_skill(task_id FK→tasks ON DELETE CASCADE, skill_id FK→skills ON DELETE CASCADE)` 等四表同构；`UniqueConstraint(task_id, target_id)` 承载「同一任务对同一实体至多一次」。删除任务或删除被挂实体均自动清关联（SQLite FK pragma 已在 app 工厂开启，P2 删除链路无需改）。ORM 层 `Task` 上加 `passive_deletes=True` 关系（`skill_mounts` 等）供联表直觉，但不是正确性来源——正确性由 DB 级联保证。

**D3 — `PUT /tasks/<id>/caps` = PUT 全状态语义（缺键=清空）+ 严格校验 + 整体事务。**
- 解析：四键 `skills/mcps/kbs/experts` 任一缺失视为 `[]`；含未知键 → 400。
- 元素校验（在写库前全部完成）：须为 `int` 且 `>0`（bool/str/float/负数 → 400 并指明）；同数组重复 → 400；每类 `SELECT id FROM <实体表> WHERE id IN (...)` 确认存在，缺失 id → 400 指明。
- 写入：全部校验通过后，单事务内 delete 该任务四类既有行 → 依提供的数组批量插入 → commit；失败整体回滚（无部分更新）。
- 成功返回 200 与 GET 同构的完整清单。
- 校验先于任何 delete，天然满足「失败不改动原挂载」。

**D4 — `GET /tasks/<id>/caps` 返回清单。**
`{task_id, skills:[...], mcps:[...], kbs:[...], experts:[...]}`，各数组按 id 升序。任务不存在走 `task_service.get_task_or_raise` → 404。

**D5 — `services/capability.py` 三个入口。**
- `parse_caps(payload)` → 校验后四组 int 列表（抛 ValidationError，供 API/service 复用）。
- `get_task_caps(task_id)` → D4 形状（供 GET）。
- `set_task_caps(task_id, payload)` → 校验+事务替换，返回 D4 形状（供 PUT）。
- `load_mounted(task_id)` → **P8 用**：返回 `{skills:[Skill...], mcps:[...], kbs:[...], experts:[...]}`（ORM 实体列表，空类为空表）；运行时据此装 Toolkit/注入技能/RAG/编排，不直接读关联表。本提案只保证读回与最近一次成功挂载一致，不做 enabled/trust 过滤。
与既有 service 同风格：异常抛 `errors.NotFoundError/ValidationError`，API 层 `errorhandler(AppError)` 统一转 `{"message":..}+状态码`（沿用 space_task.py D6）。

**D6 — 路由与注册。**
新建 `api/capability.py`：`capability_bp = Blueprint("capability", __name__, url_prefix="/api")`，`GET/PUT /tasks/<int:task_id>/caps`；在 `app.py` create_app 内 import+register（与 space_task/model_prompt 并列）。与 P2 `/tasks/<id>/files`、P3 `/tasks/<id>/model-config` 子路径不冲突。函数 docstring 注明请求/响应字段（任务书接口文档注释要求）。

**D7 — 迁移 0003_task_caps.sql：建表 + 演示 seed。**
建 8 表顺序对齐 FK 依赖（skills → task_skill 等），唯一约束、必要索引（按 task_id）。演示 seed 每类 1~2 行，固定 UTC 时间文本与既有迁移一致：
- skill：`sql-analysis`（SKILL.md 文本）、`safe-shell`（排障纪律）；
- mcp：`db-ro`（stdio, npx sqlite server 示意，trust=0——仅供挂载演示，P5 才做连通与信任）；
- kb：`ops-knowledge`（space_id NULL=全局，status='ready'，chunk_size 400）；
- expert：`ops-sme`（运维专家人设 system_prompt）。
seed 幂等由 migrate.py 的 schema_version 保证（只跑一次）。演示行随库新装即可用：curl 挂载 id 1 等即可回显。

**D8 — 测试策略（tmp 库内动态建实体，不依赖 seed id 恒定）。**
`test_capability.py` 沿用现有 `app(tmp_path)` 夹具（跑迁移含 seed），测试内用 ORM 自建 skill/等实体拿真实 id 做断言；覆盖：空挂载读回 → 挂多类 → GET 一致 → 覆盖替换 → 缺键清空 → 不存在 id/类型/重复/未知键 各 400 → 404 → 删任务后关联清除。`load_mounted` 单独断言实体回显与空分类。

## Risks / Trade-offs

- **[P4 提前建实体表，schema 若不满足 P5 会返工]** → 字段一字对齐 §5.2；P5 只增 CRUD 与 to_dict 出口脱敏，不动列。提案 Impact/design 均写明此分界，P5 归档时不再重复建表。
- **[严格校验（缺键清空/重复拒绝/未知键 400）可能显得苛刻]** → PUT 本就全状态幂等语义，P7 细节栏保存发送完整四类；对调用方更可预期。缺点已权衡接受。
- **[MCP trust/enabled、KB 越权未在此门控]** → 明确为 P5/权限域后续语义；本提案以「存在性」为唯一装配期约束，避免把 P5 逻辑提前。
- **[seed 演示行侵入库]** → 每类仅 1~2 条、命名带 demo 色彩；由 schema_version 保证只插一次，P5 提供 CRUD 后用户可增删覆盖。
- **[SQLite FK 依赖 pragma]** → app 工厂已对所有连接开启；若忘开会静默留孤儿——测试含「删任务后无残留」断言兜底。

## Migration Plan

新增 `backend/migrations/0003_task_caps.sql`，随 migrate.py 在启动时按 schema_version 顺序执行（当前 schema_version=2 → 应用 0003 → 升 3）。纯新增表 + 演示 seed，不回改既有表，无数据迁移风险；回滚 = 从 schema_version 降回并 DROP 新表（单人项目按需处理，通常不执行）。

## Open Questions

无阻塞项。P5 registry-center 将复用本表补四中心 CRUD/连通/信任；P8 运行时消费 `load_mounted`；P7 细节栏挂载 UI 由 registry-center 对接提案接通数据源——均为后续提案边界，不在本提案展开。
