## Purpose

模型供应商、任务级绑模型参数与可版本化提示词库的数据与 REST 契约：供应商密钥加密脱敏、任务可绑定并调参、提示词按 name 生成版本链，并有常用任务类型开箱预设。作为 P8 AgentScope 运行时与 P7 设置/细节栏 UI 的消费入口。

## Requirements

### Requirement: 创建模型供应商

系统 SHALL 支持 `POST /api/model-providers` 创建模型供应商：请求体含必填 `name`、受控枚举内 `type`（`openai`/`deepseek`/`dashscope`/`local`）、`base_url`，可选 `default_model` 与明文 `api_key`。`api_key` 非空时 SHALL 以 Fernet 加密后写入 `api_key_enc`，明文不下库；任何返回体 SHALL 只含掩码 `api_key`（不吐明文）。创建成功返回 201 与供应商对象。

#### Scenario: 正常创建并加密落库

- **WHEN** 以合法 JSON `{name:"deepseek", type:"deepseek", base_url:"https://api.deepseek.com/v1", default_model:"deepseek-v4-flash", api_key:"sk-abc"}` 请求 `POST /api/model-providers`
- **THEN** 返回 201 与含 `id` 的供应商对象，返回的 `api_key` 为掩码（非明文）；数据库中 `api_key_enc` 为该明文的 Fernet 密文

#### Scenario: 缺少必填或 type 非法

- **WHEN** 请求体缺 `name` 或 `type`，或 `type` 不在受控枚举内
- **THEN** 返回 400 且不产生任何供应商记录

#### Scenario: 本地类型可不带密钥

- **WHEN** 以 `type:"local"` 创建且不提供 `api_key`
- **THEN** 返回 201，供应商对象 `api_key` 为空/掩码占位，可正常创建

### Requirement: 模型供应商列表与单查

系统 SHALL 支持 `GET /api/model-providers` 返回全部供应商列表、`GET /api/model-providers/<id>` 返回单个供应商；对象含 `id/name/type/base_url/default_model/api_key`（掩码）。供应商不存在时单查返回 404。

#### Scenario: 列表全部返回且密钥掩码

- **WHEN** 系统中已存在若干供应商后请求 `GET /api/model-providers`
- **THEN** 返回 200 与含这些供应商的数组，每个 `api_key` 均为掩码（无任何明文）

#### Scenario: 单查不存在供应商

- **WHEN** 对不存在的供应商 id 请求 `GET /api/model-providers/<id>`
- **THEN** 返回 404

### Requirement: 修改模型供应商

系统 SHALL 支持 `PATCH /api/model-providers/<id>` 部分更新 `name/type/base_url/default_model/api_key`；仅当提供新 `api_key` 时才重新加密写入，未提供则保留原密文。成功返回 200 与更新后的供应商对象（`api_key` 掩码）；供应商不存在返回 404。

#### Scenario: 部分更新配置不触碰密钥

- **WHEN** 对已存在供应商 `PATCH` 仅提交新的 `base_url`
- **THEN** 返回更新后的对象 `base_url` 为新值、`api_key` 仍为掩码，且解密后与原密钥一致（未被覆盖）

#### Scenario: 更新密钥重新加密

- **WHEN** 对已存在供应商 `PATCH` 提交新的明文 `api_key`
- **THEN** 数据库中 `api_key_enc` 更新为新密钥的 Fernet 密文，返回体仍为掩码

### Requirement: 删除模型供应商

系统 SHALL 支持 `DELETE /api/model-providers/<id>` 删除供应商；供应商不存在返回 404。若该供应商已被任一任务级 `ModelConfig` 引用，SHALL 拒绝删除并返回 4xx（400）且不产生删除，避免产生悬空绑定。

#### Scenario: 删除未被引用的供应商

- **WHEN** 对不存在任何 ModelConfig 引用的供应商 id 发起 `DELETE`
- **THEN** 返回 200，供应商记录消失，后续单查为 404

#### Scenario: 删除已被引用的供应商被拒

- **WHEN** 对已被某任务 ModelConfig 引用的供应商 id 发起 `DELETE`
- **THEN** 返回 400（拒绝），供应商记录仍存在

### Requirement: 任务绑模型参数

系统 SHALL 支持 `GET/POST/PATCH /api/tasks/<task_id>/model-config` 为任务维护唯一一份 `ModelConfig`：含 `provider_id`（须存在）、`model_name`（缺省取供应商 `default_model`）、`temperature`（0–2 浮点）、`max_tokens`（正整数）、`timeout`（正整数秒）。绑定成功后任务的 `model_config_id` SHALL 指向该配置。任务不存在返回 404；`provider_id` 不存在或数值越界返回 400。首次创建返回 201，替换/更新返回 200。

#### Scenario: 首次为任务绑定模型

- **WHEN** 对存在任务且尚无绑定的请求 `POST /api/tasks/<id>/model-config` 提交 `{provider_id:1, model_name:"x", temperature:0.7}`
- **THEN** 返回 201 与配置对象；随后 `GET` 同端点能回读一致参数；`tasks.model_config_id` 等于该配置的 `id`

#### Scenario: 重复绑定即更新

- **WHEN** 对已绑定的任务再次 `POST`/`PATCH` 提交新的 `temperature`
- **THEN** 返回 200，回读 `temperature` 为新值，配置仍唯一且任务指向不变

#### Scenario: provider 不存在或越界参数

- **WHEN** 请求绑定一个不存在的 `provider_id`，或 `temperature` 不在 0–2、`max_tokens`/`timeout` 非正整数
- **THEN** 返回 400 且不改动既有绑定

### Requirement: 提示词库新建与版本化

系统 SHALL 支持 `POST /api/prompts` 保存提示词：请求体含必填 `name`、`category`、`content`，可选 `domain`。以 `name` 作为版本链标识——首次出现则创建 `version=1`、`parent_id` 为空；同名再次保存 SHALL 创建新版本（`version`=该链当前最大+1），新行的 `parent_id` 指向当前链头（旧最新版）。成功返回 201 与提示词对象。

#### Scenario: 新建得到首个版本

- **WHEN** 以新 `name` 请求 `POST /api/prompts`
- **THEN** 返回 201，对象 `version=1` 且 `parent_id` 为空

#### Scenario: 同名再保存生成新版本

- **WHEN** 以已存在 `name` 再次请求 `POST /api/prompts`（content 不同）
- **THEN** 返回 201，新对象 `version` 较旧链头 +1，且 `parent_id` 等于旧链头的 `id`；旧版仍可经其 id 取回

#### Scenario: 缺少必填字段

- **WHEN** 请求体缺 `name`/`category`/`content` 之一
- **THEN** 返回 400 且不产生提示词记录

### Requirement: 提示词列表与查看

系统 SHALL 支持 `GET /api/prompts` 返回提示词库列表，每个 `name` 只返回其最新版本（链头），可按 `category`/`domain`/`name` 过滤；`GET /api/prompts/<id>` 返回指定 id 的提示词对象（可为任一历史版本）。对象含 `id/name/category/domain/content/version/parent_id`。查看不存在的 id 返回 404。

#### Scenario: 同名多版本列表只回链头

- **WHEN** 某 `name` 已有多个版本后请求 `GET /api/prompts`
- **THEN** 该 `name` 在列表中只出现一次，且为其最大 `version` 的最新版

#### Scenario: 按分类过滤与按 id 取历史版

- **WHEN** 请求 `GET /api/prompts?category=<c>`，或对某个历史版本的 id 请求 `GET /api/prompts/<id>`
- **THEN** 前者仅返回该分类的链头；后者返回该 id 对应的具体历史版本对象

### Requirement: 提示词修改与删除

系统 SHALL 支持 `PATCH /api/prompts/<id>` 对指定版本「再保存」：以 `id` 所在链生成新版本（`parent_id=<id>`、`version` 递增），可更新 `content/category/domain`；`name` 为版本链标识、经此接口不可变。SHALL 支持 `DELETE /api/prompts/<id>` 删除该版本行；操作不存在的 id 返回 404。

#### Scenario: 对版本再保存生成子版本

- **WHEN** 对某链头版本 `PATCH` 提交新的 `content`
- **THEN** 返回 200/201 与新对象，其 `parent_id` 指向被编辑的版本，原版本仍存在且可经 id 取回

#### Scenario: 删除单版本行

- **WHEN** 对存在的一个提示词版本 id 发起 `DELETE /api/prompts/<id>`
- **THEN** 返回 200，该行消失，再按该 id 单查返回 404

### Requirement: 常用任务类型预设种子

系统 SHALL 在数据库初始化时种入 4 条 `category='task-preset'` 的 `PromptTemplate`（名称：写文档/写代码/数据分析/排障，各含一段可用系统提示词、`version=1`、`parent_id` 为空），供任务创建/细节栏开箱选用，并 SHALL 可经 `GET /api/prompts?category=task-preset` 正常取回。

#### Scenario: 初始化后存在四条预设

- **WHEN** 完成数据库迁移初始化后请求 `GET /api/prompts?category=task-preset`
- **THEN** 返回 200 且包含名称为「写文档/写代码/数据分析/排障」的四条链头（各 `version=1`）
