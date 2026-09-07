## MODIFIED Requirements

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
