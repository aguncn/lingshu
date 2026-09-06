## MODIFIED Requirements

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
