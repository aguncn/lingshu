## Why

模型与提示词是智能体运行的燃料：任务要跑，就得先有「绑定的模型参数」与「可复用的系统提示词」。P2 已提供 Space/Task 骨架并预留 `tasks.model_config_id` 占位列，本提案补齐其指向的模型资产层，让 P8 AgentScope 运行时（`ModelProvider+ModelConfig → OpenAIChatModel`）与 P7 设置/细节栏 UI 有数据可消费。

## What Changes

- 新增 3 张表 + 迁移 `0002_models_prompts.sql`：`ModelProvider`（供应商）、`ModelConfig`（任务级绑模型参数）、`PromptTemplate`（提示词库，`parent_id`+`version` 实现版本链）。
- 新增模型供应商接口：`GET/POST /api/model-providers`、`GET/PATCH/DELETE /api/model-providers/<id>`（MD-04，供设置中心）；密钥 `api_key` 用 Fernet 加密存 `api_key_enc`，任何返回体不吐明文、只吐掩码。
- 新增任务绑模型接口：`GET/POST/PATCH /api/tasks/<task_id>/model-config`（MD-01）：为任务 upsert 一份 `ModelConfig`（provider_id/model_name/temperature/max_tokens/timeout），并同步写回 P2 预留的 `tasks.model_config_id`。
- 新增提示词库接口：`GET/POST /api/prompts`、`GET/PATCH/DELETE /api/prompts/<id>`（MD-03）：按 `name` 作为版本链标识，「再保存即生成新版本」——写入 `parent_id` 指向旧版、`version` 递增。
- 常用任务类型预设种子（MD-02）：迁移里种入 4 条 `category='task-preset'` 的 PromptTemplate（写文档/写代码/数据分析/排障），作为提示词库可复用的开箱预设。

## Capabilities

### New Capabilities

- `model-prompt-config`: 模型供应商/任务绑模型参数/提示词库（含版本化与常用类型预设种子）的数据模型、REST 接口与密钥加密脱敏约定。

### Modified Capabilities

（无。P2 `space-task-mgmt` 主 spec 的需求不因本提案行为改变：`tasks.model_config_id` 由「占位可空整数」演变为「绑定后指向 model_configs 的一行」，语义增强但接口契约不变，故不修改其 spec。）

## Impact

- 数据模型：`backend/models.py` 新增 `ModelProvider/ModelConfig/PromptTemplate` 及类型白名单常量；新增迁移 `backend/migrations/0002_models_prompts.sql`（3 表 + 索引 + 4 条预设种子）。
- 接口：新增 `/api/model-providers`、`/api/tasks/<id>/model-config`、`/api/prompts` 三组端点（新 blueprint `api/model_prompt.py`，url_prefix=`/api`，与既有 `space_task_bp` 并存）。
- 代码：新增 `backend/crypto.py`（Fernet 加解密 + 密钥读取/自动生成）；新增 `backend/services/model_service.py`（供应商/绑模型/提示词三个 service）；`backend/services/space_task.py`（或独立文件）按需拆出可复用路径逻辑。`backend/app.py` 注册新 blueprint。
- 文件系统：无新落盘目录（纯库内资产）。
- 依赖：无新增（`cryptography>=50.0.1` 已在 pyproject）。
- 密钥面：主密钥取 `LINGSHU_MASTER_KEY`（或根 `.env`），缺失时自动生成并持久化到根 `.env`（已 gitignore）；供应商 `api_key` 永不明文入库/出库。
- 风险面：`ModelConfig` 绑定的供应商被删除会导致悬空绑定 → 服务层拒绝删除「已被任一 ModelConfig 引用」的供应商；任务删/级联时 ModelConfig 随任务 `ON DELETE CASCADE`。
