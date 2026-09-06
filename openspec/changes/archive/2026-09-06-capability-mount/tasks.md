# Tasks — capability-mount

> 任务级能力装配：4 实体表(schema-only) + 4 关联表 + PUT/GET `/api/tasks/<id>/caps` + capability 服务。
> 前置决策：实体表原属 P5，本提案前置落表供挂载校验与验收（proposal/design 已定）。
> 验收基线：`uv run pytest backend/tests -q` 全绿；curl 走真实库（迁移自动含演示 seed）。

## 1. 数据模型与迁移

- [x] 1.1 `models.py` 新增四实体模型 `Skill`/`MCPConnector`/`KnowledgeBase`/`Expert`：字段一字对齐设计 §5.2（Skill: name/description/skill_md/version/enabled；MCPConnector: name/transport/command/args/env/url/headers/trust/enabled，args/env/headers 为 JSON 文本列；KnowledgeBase: name/space_id(FK→spaces SET NULL)/embedding_provider/chunk_size/status；Expert: name/description/system_prompt/role/composed_of(json)/enabled），各带 TimestampMixin 与 `to_dict()`（不吐 env 等密钥类字段）；models.py 顶部集中白名单常量（transport∈stdio/http 等）（验收：模型可被 SQLAlchemy 映射、to_dict 无密钥字段）
- [x] 1.2 `models.py` 新增四关联模型 `TaskSkill`/`TaskMcp`/`TaskKb`/`TaskExpert`：`task_id` FK→tasks ON DELETE CASCADE、目标 id FK→对应实体 ON DELETE CASCADE，`UniqueConstraint(task_id, target_id)` 防重复挂载；`Task` 增 `passive_deletes=True` 关联关系（验收：两两关联唯一约束存在、ORM 引用可建）
- [x] 1.3 新迁移 `backend/migrations/0003_task_caps.sql`：建 4 实体表 + 4 关联表（FK/唯一/按 task_id 索引，顺序对齐依赖）+ 演示 seed 每类 1~2 行（skill: sql-analysis/safe-shell；mcp: db-ro trust=0；kb: ops-knowledge 全局；expert: ops-sme），固定 UTC 时间文本与 0002 风格一致（验收：`uv run flask --app backend.app run` 后 schema_version 升至 3，新库含 8 表与 seed 行）

## 2. 服务与接口

- [x] 2.1 `services/capability.py`：`parse_caps(payload)` 严格校验（未知分类键→400；元素须为正整数 int，bool/str/float/负数/同数组重复→400；每类目标实体须存在，否则指出非法 id）；`get_task_caps(task_id)` 返回 `{task_id,skills,mcps,kbs,experts}`（id 升序）；`set_task_caps(task_id, payload)` 先全量校验、后单事务 delete→insert 全量覆盖（缺键=清空），失败整体回滚不改动原挂载（验收：非法输入抛 ValidationError、校验失败前零写入）
- [x] 2.2 `services/capability.py` 增 `load_mounted(task_id)`（供 P8）：按任务聚合返回 `{skills:[Skill..],mcps:[...],kbs:[...],experts:[...]}` 实体列表，未挂载分类为空表，读回与最近一次成功挂载一致（验收：挂一条 skill+一条 kb 后 load_mounted 含对应实体、mcps/experts 为空）
- [x] 2.3 新 `api/capability.py`：`capability_bp`（url_prefix=/api），实现 `PUT /tasks/<int:task_id>/caps`（调 set_task_caps，成功 200 返回清单）与 `GET /tasks/<int:task_id>/caps`（调 get_task_caps）；任务不存在 404；docstring 写明请求/响应字段与 400/404 语义；在 `app.py` create_app 内 import+register（验收：curl PUT/GET 可达、与 P2/P3 子路径无冲突）
- [x] 2.4 级联验证：删除任务后其挂载关联经 DB 级联清除（SQLite FK pragma 已开）；如 P2 删除链路有需同步处一并补齐，并以「删任务后 GET caps 404 且关联表无残留」为判据（验收：见 3.1 测试断言）

## 3. 测试与联调

- [x] 3.1 `backend/tests/test_capability.py`（沿用 app(tmp_path) 夹具，测试内 ORM 自建实体拿真实 id）：空挂载读回四组空 → PUT 多类后 GET 一致 → 覆盖替换旧值 → 缺键清空 → 不存在 id 400 / 元素类型非法 400 / 同数组重复 400 / 未知分类键 400 → 校验失败不改动原挂载 → 任务不存在 404 → 删除任务后级联清除（spec 各 Scenario 覆盖）（验收：`uv run pytest backend/tests/test_capability.py -q` 绿）
- [x] 3.2 测试 `load_mounted` 聚合：挂技能+知识库返回实体记录、未挂分类为空、删任务后抛/404（验收：并入 3.1 文件后同绿）
- [x] 3.3 全量回归 + 手工 curl 验收：`uv run pytest backend/tests -q` 全绿；重启后端后 `curl -X PUT /api/tasks/<id>/caps -d '{"skills":[],"mcps":[],"kbs":[],"experts":[]}'` 读回空；用 seed 演示 id 挂载（skill=1 等）后 `curl GET .../caps` 回显一致；再挂不存在的 id 得 400；删除任务后 GET 404 且挂载记录消失（spec 手工验收点；任务书 P4 ⑤）
