# Tasks — model-prompt-config

> 分组沿用任务书 P3 十项并补强：模型与迁移 / 密钥工具 / 供应商 API（MD-04）/ 绑模型（MD-01）/ 提示词库（MD-03）/ 种子与验收。

## 1. 模型与迁移

- [x] 1.1 在 `backend/models.py` 定义 `ModelProvider/ModelConfig/PromptTemplate`（字段对齐设计 §5.2/D8），补 `MODEL_PROVIDER_TYPES={openai,deepseek,dashscope,local}`、`PRESET_CATEGORY="task-preset"` 常量；relationship 用 `passive_deletes=True`（级联靠 DB FK，见 P2 惯例）
- [x] 1.2 写迁移 `backend/migrations/0002_models_prompts.sql`：建 `model_providers`→`model_configs`（task_id UNIQUE FK→tasks ON DELETE CASCADE、provider_id FK→providers ON DELETE RESTRICT）→`prompt_templates`（自引用 parent_id ON DELETE SET NULL）+ 索引；末尾 `INSERT` 4 条预设种子（写文档/写代码/数据分析/排障，category='task-preset'，version=1）

## 2. 密钥工具

- [x] 2.1 新建 `backend/crypto.py`：`get_key()`（取 LINGSHU_MASTER_KEY / 根 `.env`，缺则生成 Fernet key 追加写 `.env`）、`encrypt/decrypt/mask`；`mask_key` 有值回 `"****"+末4`、无值回 `None`

## 3. 供应商 API（MD-04）

- [x] 3.1 建 `backend/api/model_prompt.py` 域 blueprint（url_prefix=`/api`）并在 `app.py` 注册；承载 `GET/POST /api/model-providers`：POST 收明文 `api_key`→`crypto.encrypt` 写 `api_key_enc`，name/type 校验→400；响应一律走 service 掩码出口（无明文）
- [x] 3.2 同 blueprint 承载 `GET/PATCH/DELETE /api/model-providers/<int:pid>`：列表/单查脱敏、PATCH 部分更新（仅提供新 `api_key` 才重加密）、DELETE 引用保护（被任一 ModelConfig 引用→400）、不存在→404

## 4. 任务绑模型（MD-01）

- [x] 4.1 写 `backend/services/model_service.py` 之 config 子区：`get/create_or_replace/update` 单任务唯一 ModelConfig（provider_id 必填须存在、model_name 缺省取 provider.default_model、temperature 0–2/max_tokens·timeout 正整数白名单→400）；创建/更新**同一事务**写回 `tasks.model_config_id`；任务不存在→404
- [x] 4.2 blueprint 承载 `GET/POST/PATCH /api/tasks/<int:task_id>/model-config`：GET 无绑定→404、有则 200；POST 首建 201 / 替换 200；PATCH 部分调参→200；4.1 校验透传

## 5. 提示词库（MD-03）

- [x] 5.1 写 `model_service.py` 之 prompts 子区 + blueprint `GET/POST /api/prompts`：列表按 name 分组只回链头（支持 category/domain/name 过滤）、POST 首次 version=1 / 同名 version=链头+1 且 parent_id=链头.id；name/category/content 校验→400
- [x] 5.2 同 blueprint 承载 `GET/PATCH/DELETE /api/prompts/<int:id>`：GET 取任意版本行（历史可读）、PATCH 仅允许对链头「再保存」生成子版本（parent_id=<id>，非链头→400，name 不可改）、DELETE 删除该版本行；不存在→404

## 6. 种子与测试验收

- [x] 6.1 预设种子验收：迁移后 `GET /api/prompts?category=task-preset` 返回 4 条链头（写文档/写代码/数据分析/排障，各 version=1、含非空 content）
- [x] 6.2 写 `backend/tests/test_model_prompt.py`：建供应商→列表密钥掩码且 DB 为密文→回读解密一致；任务绑模型→回读一致且 `tasks.model_config_id` 同步；提示词保存→版本链 parent_id 正确、列表只回链头；被引用供应商删除→400；预设种子可取
