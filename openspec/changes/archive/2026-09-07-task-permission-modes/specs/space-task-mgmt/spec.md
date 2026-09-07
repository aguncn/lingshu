## ADDED Requirements

### Requirement: 任务权限模式字段与迁移回填

系统 SHALL 在 `tasks` 表持久化 `permission_mode` 字段，其取值白名单 SHALL 恰为 `strict`/`limited`/`trusted` 三档；新增该列的迁移（migrations/0009）SHALL 使既有任务回填 `strict`，列值 SHALL 非空。任务对象（创建响应、详情、列表项）SHALL 暴露该字段。`permission_mode` 决定该任务内置工具调用的二次确认档位（档位语义见 agentscope-runtime「内置工具调用权限档位映射」），在会话发起装配时按任务当前值生效。任务不存在或对不存在的任务读写该字段 → 404。

#### Scenario: 迁移后既有任务回填严格档

- **WHEN** 对含既有任务记录的库应用迁移 0009
- **THEN** `tasks` 表新增 `permission_mode` 列且所有既有任务取值为 `strict`，无 NULL

#### Scenario: 三档取值受控、任务对象可见

- **WHEN** 查看一个任务（详情/列表/创建响应）且其 `permission_mode` 为三档之一
- **THEN** 任务对象含该字段且与库内一致；任何写路径提交白名单外值 → 400（不落库、不改值）

### Requirement: 修改任务时调整权限模式

系统 SHALL 支持经 `PATCH /api/tasks/<id>` 修改 `permission_mode`（部分更新，取值须在三档白名单内，越界 400）；成功返回更新后任务对象且该字段反映新值。权限模式属任务级配置，调整 SHALL 不影响任务落盘目录名与既有文件归属，SHALL 不打断正在运行的会话，只作用于该任务之后新发起的对话 run。

#### Scenario: 修改不存在的任务

- **WHEN** 对不存在的任务 id 发起 `PATCH`
- **THEN** 返回 404

#### Scenario: 合法切换权限档位

- **WHEN** 对已存在任务 `PATCH` 提交新的合法 `permission_mode`（如 `limited`）
- **THEN** 返回 200/更新后任务且 `permission_mode` 反映新值，`id` 不变；对非法值提交返回 400

## MODIFIED Requirements

### Requirement: 在空间下创建任务

系统 SHALL 支持 `POST /api/spaces/<sid>/tasks` 创建任务：请求体含必填 `title` 与受控枚举内的 `task_type`，可选 `model_config_id`（模型占位，可为空）、`visibility`（缺省 `private`）与 `permission_mode`（三档 `strict`/`limited`/`trusted`，缺省 `strict`）。任务必属该空间；空间不存在返回 404；`title` 缺失或 `task_type` 不在枚举返回 400。

#### Scenario: 正常创建任务

- **WHEN** 对存在的空间以合法 JSON `{title:"排查订单延迟", task_type:"fault"}` 请求
- **THEN** 返回 201 与任务对象（含 `id`、`space_id`、`task_type`、`permission_mode`），任务出现在该空间的任务列表中

#### Scenario: 参数缺失或非法

- **WHEN** 请求体缺 `title`，或 `task_type` 不在受控枚举内
- **THEN** 返回 400 且不产生任务记录

#### Scenario: 空间不存在

- **WHEN** 对不存在的空间 id 发起建任务
- **THEN** 返回 404

#### Scenario: 新建任务带权限模式

- **WHEN** 创建任务时请求体携带 `permission_mode` 为 `limited`/`trusted`，或为白名单外值，或缺省该字段
- **THEN** `limited`/`trusted` 任务创建成功且该字段反映所选值；白名单外值返回 400 不产生记录；缺省时任务 `permission_mode='strict'`

### Requirement: 修改任务（改名同步）

系统 SHALL 支持 `PATCH /api/tasks/<id>` 修改 `title`、`task_type`、`visibility`、`permission_mode` 等字段（部分更新；`permission_mode` 取值须在三档白名单内）。任务落盘目录名基于任务 `id` 而非 `title`，因此改名不影响文件归属。

#### Scenario: 重命名任务

- **WHEN** 对已存在任务 `PATCH` 新的 `title`
- **THEN** 返回更新后的任务且 `title` 反映新值；该任务目录名不变，已有文件仍归属该任务

#### Scenario: 修改不存在的任务

- **WHEN** 对不存在的任务 id 发起 `PATCH`
- **THEN** 返回 404
