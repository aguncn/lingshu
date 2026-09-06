## Context

P2（space-task-mgmt）已落地 `Space/Task/User/Membership/FileRecord` 5 表、REST 骨架与「service 层做业务、API 只转发、错误统一 `{"message":..}`」的分层，并在 `tasks.model_config_id` 预留了**可空整数占位列（无 FK）**，注释约定「P3 建 model_configs 后接管」。单人项目约束（CLAUDE.md）：不引 Redis/MQ，密钥 Fernet 加密、明文不下库；`cryptography>=50.0.1` 已在 pyproject。行为契约见 specs；动机见 proposal。本文只讲落地方式。

## Goals / Non-Goals

**Goals:**
- 建 `ModelProvider / ModelConfig / PromptTemplate` 3 表 + 迁移 0002，让 P2 占位列有真实资产可指。
- 供应商密钥 Fernet 加密落 `api_key_enc`；响应一律掩码，永不出明文。
- 任务级绑模型（MD-01）：每任务唯一 `ModelConfig`，写后同步 `tasks.model_config_id`。
- 提示词库（MD-03）：以 `name` 为链标识，「保存即升版」，`parent_id` 串联，列表只回链头。
- 4 条常用任务类型预设（MD-02：写文档/写代码/数据分析/排障）随迁移种子写入。

**Non-Goals:**
- 不实现 AgentScope 运行时/`model_factory.py`（P8）；不做 chat、不做模型连通性测试。
- 不做「解绑模型」/删 `ModelConfig` 的显式接口（P8 需要时再补；本期删任务即级联清理配置）。
- 不做提示词历史子路由 `/versions`：旧版本经 `GET /api/prompts/<id>`（任一版本行 id）取回。
- 不重排 P2 任务类型枚举（`fault/change/alert/general` 保持不动）；四预设是提示词库的种子，不是新的 task_type 枚举。
- 供应商不做空间隔离（全局资产，对齐 §5.2）；不做 UI（P7）。

## Decisions

**D1 — 主密钥保障：Fernet 密钥缺失时自动生成并持久化到根 `.env`。**
`crypto.py` 提供 `encrypt/decrypt/mask/get_key`。密钥读取顺序：`LINGSHU_MASTER_KEY` 环境变量 → 根 `.env`（`backend/__init__.py` 启动时已 `load_dotenv`，根 `.env` 在 gitignore）→ 两者皆缺时生成一把 urlsafe Fernet key 并**追加** `LINGSHU_MASTER_KEY=<key>` 到根 `.env`。为什么持久化而非每次生成：否则重启后旧密文（供应商 api_key）永久不可解。若 `.env` 不可写（只读部署），退化为本进程内临时 key 并打印告警（单人本地开发不会走到）。

**D2 — `api_key` 输入明文、`api_key_enc` 存密文、响应只吐掩码。**
POST/PATCH 请求体字段名用 `api_key`（明文），服务层 `crypto.encrypt()` 后写 `api_key_enc`；`type=local` 或未提供时 `api_key_enc=NULL`。任何序列化出口（list/detail）都不带密文也不解密，只算掩码 `mask_key`：有值回 `"****"+末4`（不足 4 位则全 `****`），无值回 `None`。掩码逻辑放 service（model `to_dict` 不含密钥字段），保证纯模型不透明文。

**D3 — Task 与 ModelConfig 的 1:1 + P2 占位列同步（不重建 tasks 表）。**
SQLite 不能 `ALTER TABLE ADD CONSTRAINT`（加 FK 需整表重建），P2 的 `tasks.model_config_id` 已提交为普通整数列。决策：
- 新表 `model_configs.task_id` 为 `UNIQUE + FK→tasks(id) ON DELETE CASCADE`，作为**权威绑定**；`provider_id FK→model_providers(id) ON DELETE RESTRICT`。
- `tasks.model_config_id` 保留为**运行时便捷指针**（P8 按 task 读模型时免反向查）：绑定时在**同一事务**里写回该列，删配置（随任务级联）时无需单独回清——任务都没了。
- 两处由 `model_service`（config 部分）单点维护，避免漂移；测试断言二者一致（spec「绑模型」场景）。
- ModelConfig 字段含 `is_default`（对齐 §5.2），本期恒默认 false、无接口修改，供未来每空间默认模型用。

**D4 — 供应商删除引用保护：service 预查 + DB 兜底。**
`DELETE /api/model-providers/<id>` 先查 `ModelConfig where provider_id=<id>` 有则抛 400（`ValidationError`）；迁移 FK 用 `ON DELETE RESTRICT` 作 DB 层兜底，防止未来绕开 service 直删造成悬空绑定。

**D5 — 提示词版本链语义（name = 链标识）。**
- 「链头」= 该 `name` 下 `version` 最大的一行（按 `(name, version)` 唯一）。
- `POST /api/prompts`：`name` 首次出现 → `version=1, parent_id=NULL`；已存在 → `version=链头+1, parent_id=链头.id`。content/category/domain 均可变。
- `GET /api/prompts`：在 Python 侧按 name 分组取每名链头（SQLite 无窗口函数跨版本简取，N 小不必 SQL 复杂化），支持 `category/domain/name` 过滤。
- `GET /api/prompts/<id>`：返回任意版本行（含历史）。
- `PATCH /api/prompts/<id>`：仅当 `<id>` 是链头时允许「再保存」，以该行为父生成新版本；对**非链头**（历史版）再保存会分叉，返回 400——链保持单线。`name` 不可改（改链名请走 POST 新 name）。
- `DELETE /api/prompts/<id>`：删除该版本行；自引用 `parent_id ON DELETE SET NULL`（SQLite FK 已开启）避免删祖先行触发约束报错。允许删历史行，其后代 `parent_id` 置空（trade-off 见下）。
- `category` 自由字符串；种子用固定常量 `PRESET_CATEGORY="task-preset"`。

**D6 — 分层与路由：新域 blueprint `model_prompt_bp` + 集中 service。**
对齐 P2 D5「后续域再各建 blueprint」：`backend/api/model_prompt.py` 定义 `model_prompt_bp`（url_prefix=`/api`），承载 `/model-providers(/<id>)`、`/tasks/<int:task_id>/model-config`、`/prompts(/<int:id>)`。与既有 `space_task_bp` 规则无冲突（`/api/tasks/<int:task_id>/model-config` 与 `/files` 等是不同 rule）。`backend/services/model_service.py` 内聚 `providers / configs / prompts` 三个子区；`crypto.py` 纯工具；错误复用 `services/errors.AppError`，blueprint 级 `errorhandler(AppError)` 与 P2 一致。`app.py` 注册新 bp。

**D7 — 绑模型数值白名单校验。**
`provider_id` 必填且须存在（否则 400）；`model_name` 缺省取 provider.`default_model`；`temperature` 须 0–2 浮点；`max_tokens`/`timeout` 须正整数（`timeout` 缺省 60，单位秒）。越界/缺必填 → 400。ModelConfig 提供 `to_dict()`（含 task_id、provider_id、model_name、temperature、max_tokens、timeout、is_default、时间戳）。

**D8 — 迁移 `0002_models_prompts.sql`：一次建 3 表 + 预设种子。**
建表顺序无跨表循环依赖：`model_providers` → `model_configs`（FK task/provider）→ `prompt_templates`（自引用 parent）。索引：`idx_model_configs_task (task_id) UNIQUE`、`idx_prompt_name_version (name, version) UNIQUE`、`idx_prompt_category (category)`、`idx_providers_name (name) UNIQUE`。种子：`INSERT` 4 条 `PromptTemplate(name=写文档/写代码/数据分析/排障, category='task-preset', version=1, parent_id=NULL, content=<一段中文系统提示词>, domain=NULL)`，时间戳与 0001 同源 UTC ISO。幂等由 `schema_version` 保证（0002 只新增表，对已有 P1/P2 库增量补跑）。供 0002 引用的 `tasks`/`users` 表已在 0001 存在，无需 `ALTER`。

## Risks / Trade-offs

- **[主密钥丢失 → 供应商密钥永不可解]** 密钥持久化在根 `.env`（gitignore）而非库内；文档注明 `.env` 需备份，丢失后只能删除供应商重建。
- **[删提示词历史行破坏后代 parent 指向]** `ON DELETE SET NULL` 后后代 `parent_id=NULL`，其版本链可视化中断（列表/单查不受影响）。单人工具可接受；若要严格历史，改走「只许删链头」需重做 spec，暂不取。
- **[tasks.model_config_id 与 model_configs 双写]** 单点维护于 model_service，测试断言一致；若未来出现绕开 service 的写路径才需收敛为单一外键（届时整表重建一次）。
- **[自动写 `.env` 副作用]** crypto import 时若缺主密钥会写根 `.env`——单人本地可预期；已 gitignore，不会入库。

## Migration Plan

`0002_models_prompts.sql` 为纯新增 DDL + 种子，编号由 `schema_version` 防重跑；对现存 P1/P2 库增量执行（仅新增 3 表，引用既有表）。回滚：删 3 表即可（业务数据在 gitignore 库内，非基线）；若需彻底重置，删 `backend/data/app.db` 重跑 `uv run flask --app backend.app run` 即按 0001→0002 全量重建。

## Open Questions

无阻塞性开放问题。
