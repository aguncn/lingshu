## Purpose

空间与任务管理（TR）：以空间作为隔离与协作边界、任务作为最小运行单元，提供空间与任务的 CRUD、可见性与成员角色字段，并支撑文件按「空间→任务」两级目录落盘与任务工作空间文件列举，作为 P3+ 各能力挂载的主体骨架。

## Requirements

### Requirement: 内置管理员用户

系统 SHALL 在数据库初始化时种入一个内置管理员 `User`（`username=admin`、`role=owner`），作为单人模式下的默认归属人，用于创建空间时写入 Owner 成员关系。

#### Scenario: 初始化后存在内置管理员

- **WHEN** 完成数据库迁移与种子初始化
- **THEN** `users` 表存在且包含 `username=admin`、`role=owner` 的记录

### Requirement: 创建空间

系统 SHALL 支持 `POST /api/spaces` 创建空间：请求体含必填 `name`、可选 `description` 与 `visibility`（取值 `private`/`team`/`public`，缺省 `private`）。创建成功返回 201 与空间对象（含 `id`），并为内置管理员写入 `Owner` 角色的 Membership。

#### Scenario: 正常创建空间

- **WHEN** 以合法 JSON `{name:"demo", visibility:"private"}` 请求 `POST /api/spaces`
- **THEN** 返回 201 与含唯一 `id` 的空间对象，且该空间在后续列表接口中可见

#### Scenario: 缺 name 或 visibility 非法

- **WHEN** 请求体缺 `name`，或 `visibility` 不是 `private/team/public` 之一
- **THEN** 返回 4xx（400），且不产生任何空间记录

#### Scenario: 创建即写入 Owner 成员

- **WHEN** 内置管理员创建一个空间
- **THEN** 该空间存在一条 `(space, admin)` 且 `role=Owner` 的 Membership 记录

### Requirement: 列出空间

系统 SHALL 支持 `GET /api/spaces` 返回全部空间列表，每个空间对象含 `id`、`name`、`description`、`visibility` 与创建时间。

#### Scenario: 有多个空间时全部返回

- **WHEN** 系统中已创建若干空间后请求 `GET /api/spaces`
- **THEN** 返回 200 与含这些空间的数组，按创建时间倒序

### Requirement: 修改空间

系统 SHALL 支持 `PATCH /api/spaces/<id>` 修改空间的 `name`/`description`/`visibility`（部分更新），成功返回更新后的空间对象；空间不存在时返回 404。

#### Scenario: 合法部分更新

- **WHEN** 对已存在空间 `PATCH` 提交新的 `name` 与 `visibility`
- **THEN** 返回更新后的空间对象，`name`/`visibility` 反映新值且 `id` 不变

#### Scenario: 修改不存在的空间

- **WHEN** 对不存在的空间 id 发起 `PATCH`
- **THEN** 返回 404

### Requirement: 删除空间

系统 SHALL 支持 `DELETE /api/spaces/<id>`：删除空间记录及其全部 Membership 与子任务，并递归清理该空间落盘目录 `data/spaces/<space>/`；空间不存在返回 404。

#### Scenario: 删除存在空间

- **WHEN** 对存在（可能含子任务与落盘文件）的空间 id 发起 `DELETE /api/spaces/<id>`
- **THEN** 返回成功（200/204），空间记录与其子任务记录消失，`data/spaces/<id>/` 目录被清除

#### Scenario: 删除不存在的空间

- **WHEN** 对不存在的空间 id 发起 `DELETE`
- **THEN** 返回 404

### Requirement: 在空间下创建任务

系统 SHALL 支持 `POST /api/spaces/<sid>/tasks` 创建任务：请求体含必填 `title`，可选 `task_type`、`model_config_id`（模型占位，可为空）、`visibility`（缺省 `private`）与 `permission_mode`（三档 `strict`/`limited`/`trusted`，缺省 `strict`）。`task_type` 取值受控白名单 {fault,change,alert,general} 内；C5 起新建入口（对话框）不再暴露该字段，请求缺省时 SHALL 回落 `'general'`（列与任务对象、左栏/徽标展示保留，PATCH 仍可改）。任务必属该空间；空间不存在返回 404；`title` 缺失返回 400；`task_type` **提供但**不在白名单返回 400。套用运维专家档案不属于创建请求体：前端先建任务、再经 `POST /api/tasks/<id>/expert/apply` 快照装配（见 capability-mount「档案快照装配到任务（专家档案套用）」）。

#### Scenario: 正常创建任务

- **WHEN** 对存在的空间以合法 JSON `{title:"排查订单延迟", task_type:"fault"}` 请求
- **THEN** 返回 201 与任务对象（含 `id`、`space_id`、`task_type`、`permission_mode`），任务出现在该空间的任务列表中

#### Scenario: 参数缺失或非法

- **WHEN** 请求体缺 `title`，或提供了不在受控白名单内的 `task_type`
- **THEN** 返回 400 且不产生任务记录

#### Scenario: 空间不存在

- **WHEN** 对不存在的空间 id 发起建任务
- **THEN** 返回 404

#### Scenario: 新建任务带权限模式

- **WHEN** 创建任务时请求体携带 `permission_mode` 为 `limited`/`trusted`，或为白名单外值，或缺省该字段
- **THEN** `limited`/`trusted` 任务创建成功且该字段反映所选值；白名单外值返回 400 不产生记录；缺省时任务 `permission_mode='strict'`

#### Scenario: 缺省 task_type 回落 general

- **WHEN** 创建任务时请求体不携带 `task_type`（新建对话框自 C5 起不再提供该字段）
- **THEN** 返回 201，任务对象 `task_type='general'`（列/徽标仍可读可改），不报缺失字段错误

### Requirement: 列出与查看任务

系统 SHALL 支持 `GET /api/spaces/<sid>/tasks` 返回该空间的任务列表（含 `id`、`title`、`task_type`、`visibility`、`status`），并按创建时间倒序；支持 `GET /api/tasks/<id>` 返回单个任务详情。

#### Scenario: 按空间列出任务

- **WHEN** 请求某空间的任务列表
- **THEN** 返回 200 且仅含属于该空间的任务，按创建时间倒序

#### Scenario: 查看单个任务

- **WHEN** 对存在的任务 id 请求 `GET /api/tasks/<id>`
- **THEN** 返回 200 与任务详情；任务不存在返回 404

### Requirement: 修改任务（改名同步）

系统 SHALL 支持 `PATCH /api/tasks/<id>` 修改 `title`、`task_type`、`visibility`、`permission_mode` 等字段（部分更新；`permission_mode` 取值须在三档白名单内）。任务落盘目录名基于任务 `id` 而非 `title`，因此改名不影响文件归属。

#### Scenario: 重命名任务

- **WHEN** 对已存在任务 `PATCH` 新的 `title`
- **THEN** 返回更新后的任务且 `title` 反映新值；该任务目录名不变，已有文件仍归属该任务

#### Scenario: 修改不存在的任务

- **WHEN** 对不存在的任务 id 发起 `PATCH`
- **THEN** 返回 404

### Requirement: 删除任务并清理文件

系统 SHALL 支持 `DELETE /api/tasks/<id>`：删除任务记录及其 `FileRecord`，并递归清理该任务落盘目录 `data/spaces/<space>/<task>/`；任务不存在返回 404。

#### Scenario: 删除存在任务

- **WHEN** 对存在且目录下有文件的某任务发起 `DELETE /api/tasks/<id>`
- **THEN** 返回成功，任务记录消失，`data/spaces/<space>/<task>/` 目录连同其下文件被清除

### Requirement: 任务工作空间文件列举

系统 SHALL 支持 `GET /api/tasks/<id>/files` 返回该任务工作空间目录 `data/spaces/<space>/<task>/` 下现有文件列表（含文件名、大小、mime、路径），并把该任务已挂载的资料库引用并入同一清单（见 library 能力「跨任务引用」）；任务不存在返回 404。工作区实体文件条目以 `kind=file` 标记并含 filename/path/size/mime；资料库引用条目以 `kind=ref` 标记，含引用 FileRecord 的 id、`library_file_id`、文件名/大小/mime（抄录自库文件，供直接展示）且不要求字节存在于任务目录。清单顺序 SHALL 稳定：实体文件在前、引用条目在后。

#### Scenario: 目录为空返回空列表

- **WHEN** 请求一个尚无文件的已存在任务的文件列表
- **THEN** 返回 200 与空数组

#### Scenario: 目录有文件时列出

- **WHEN** 该任务工作空间目录下已存在若干文件后请求列表
- **THEN** 返回 200 与含这些文件元数据的数组，条目 `kind=file`

#### Scenario: 合并展示资料库引用

- **WHEN** 某任务既在工作空间有实体文件，又挂载了若干资料库引用
- **THEN** 返回 200，实体文件条目在前（kind=file）、引用条目在后（kind=ref 且带 library_file_id），互不重复

### Requirement: 文件两级落盘与元数据记录

系统 SHALL 提供文件落盘服务：工作空间实体文件按 `data/spaces/<space_id>/<task_id>/` 两级目录物理存储，并用 `FileRecord` 记录元数据（space_id、task_id、filename、path、mime、size）；目录与路径均以数据库 id 生成，杜绝路径穿越。除实体文件外，`FileRecord` SHALL 也可充当**资料库引用型记录**：当 `library_file_id` 非空时，该条记录不向任务目录落任何字节，filename/mime/size 抄录自被引用的 LibraryFile，space/task 仍记归属，用于把资料库文档并入任务文件视图。删除任务 SHALL 级联删除其全部 FileRecord（含引用型），但绝不因此删除资料库实体文件（字节归 library 能力所有）。

#### Scenario: 记录与目录一致

- **WHEN** 一个文件按空间→任务两级目录落盘
- **THEN** 物理路径位于 `data/spaces/<space_id>/<task_id>/` 下，且存在对应的 `FileRecord` 记录（可经文件列举接口观察到）

#### Scenario: 引用型记录不落盘、删任务不动资料库

- **WHEN** 一个任务挂载了资料库引用（library_file_id 非空），随后该任务被删除
- **THEN** 删除后该引用 FileRecord 随任务消失，但被引用的资料库文件记录与磁盘文件原样保留，仍可被其它任务引用

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
