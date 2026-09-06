## Purpose

跨任务集中资料库（LB-01）：为可跨任务复用的文件资产提供统一 REST 管理——按空间或全局上传 / 下载 / 列表 / 删除、分享标记开关，以及让任务以不复制字节的「引用」方式挂载库文档；与任务私有工作空间文件（space-task-mgmt 域）区分，实体文件归 `data/library/`。知识库(KB)上传与本能力不耦合，切块回填留 P8。

## Requirements

### Requirement: 资料库文件上传

系统 SHALL 提供 `POST /api/library`（multipart，表单字段名 `file`）上传一个文件进资料库并建立 LibraryFile 记录：缺 `file` 或文件名为空 → 400；可选 `space_id` 表单字段决定归属——省略或为空视为**全局库**（space_id 记 NULL），为字符串正整数则须指向已存在空间否则 400。文件名只取原文件名 basename 并净化（去目录分隔符、拒空）。实体文件 SHALL 落盘于资料库专用目录 `data/library/`，绝不写入任何任务工作空间目录；记录须含该库文件自身归属/元数据，不依赖任何任务。成功后返回 201，响应含 id、space_id（可为 null）、filename、size、mime、shared=false 与时间戳，绝不返回内部存储路径。

#### Scenario: 上传到全局库

- **WHEN** 用户不带 space_id 上传一个文件
- **THEN** 返回 201 且 space_id 为 null；随后以 scope=global 的列表可看到该文件，其下载内容与上传一致

#### Scenario: 上传到指定空间

- **WHEN** 用户携带已存在空间的 space_id 上传一个文件
- **THEN** 返回 201 且 space_id 等于该空间；scope=space 过滤该空间时可看到，scope=global 看不到

#### Scenario: 缺文件或目标空间不存在

- **WHEN** 用户不携带 file 字段上传，或 space_id 指向不存在的空间
- **THEN** 返回 400 并给出可读消息，资料库不发生任何变化

### Requirement: 资料库列表（scope 过滤）

系统 SHALL 提供 `GET /api/library` 返回资料库文件元数据数组，query 参数 `scope` 决定可见集合，取值 `all`/`global`/`shared`/`space`、缺省 `all`：all 返回全部；global 仅返回全局文件（space_id 为 NULL）；shared 仅返回已开启分享标记的文件；space 需另带正整数 `space_id` 参数且该空间须存在否则 400。返回元素含 id、space_id（可为 null）、filename、size、mime、shared、时间戳，不含内部存储路径；按 id 升序；资料库为空时返回 200 与空数组。

#### Scenario: 全局与空间互斥可见

- **WHEN** 库中同时存在全局文件与归属某空间 A 的文件，用户分别以 scope=global 与 scope=space&space_id=A 请求
- **THEN** global 视图只含全局文件、A 视图只含 A 的文件，两个集合不重叠

#### Scenario: 共享视图与不存在的空间

- **WHEN** 用户把某文件 shared 置 true 后以 scope=shared 请求；或对 scope=space 传入不存在的空间 id
- **THEN** shared 视图出现该文件；不存在的空间返回 400

### Requirement: 资料库下载

系统 SHALL 提供 `GET /api/library/<id>/download` 返回该文件二进制内容：Content-Type 为记录 mime、Content-Disposition 为 attachment 且文件名取记录原名。记录不存在 → 404；记录存在但其实体文件已从磁盘丢失 → 404 并给出可读消息（属业务性缺失，不返回 5xx）。

#### Scenario: 下载内容与上传一致

- **WHEN** 用户先上传一段文本文件，再对其 id 发起下载
- **THEN** 返回 200，响应体与上传字节完全一致，且响应头文件名等于上传原名

#### Scenario: 下载不存在的文件

- **WHEN** 用户对不存在于资料库的 id 发起下载，或记录存在而磁盘文件已丢失
- **THEN** 返回 404

### Requirement: 资料库部分更新（分享标记与改名）

系统 SHALL 提供 `PATCH /api/library/<id>` 做部分更新：body 中出现的字段决定动作——`shared` 为布尔则开关分享标记（置 true 时同时记录分享时刻）；`filename` 为净化后的非空字符串则改名（净化规则同上传）。出现未知字段、shared 非布尔、filename 为空或净化后为空 → 400；记录不存在 → 404。成功返回更新后的完整元数据（含 shared 与时间戳）。

#### Scenario: 开启分享并改名

- **WHEN** 用户 PATCH {shared:true, filename:"新名字.md"}
- **THEN** 返回 200，读回该文件 shared=true 且 filename 为新值；scope=shared 视图可见

#### Scenario: 非法更新被拒

- **WHEN** 用户 PATCH 提供未知字段，或 shared 传非布尔，或 filename 传空
- **THEN** 返回 400，记录保持不变

### Requirement: 资料库删除与引用完整性

系统 SHALL 提供 `DELETE /api/library/<id>`：若该文件正被任一任务的引用型 FileRecord 指向（见 space-task-mgmt 修改需求）→ 返回 400 并说明其仍被引用、不删除；否则删除记录并同步删除其磁盘实体文件。记录不存在 → 404。资料库删除 SHALL 绝不影响知识库切块（本能力与 KB 不耦合）。

#### Scenario: 删除后记录与磁盘文件都消失

- **WHEN** 用户删除一个未被任何任务引用的库文件
- **THEN** 返回 200 {ok:true}；再以任意 scope 列表看不到它，其磁盘实体文件随之消失

#### Scenario: 仍被引用时拒绝删除

- **WHEN** 某任务已引用该库文件，用户仍尝试删除它
- **THEN** 返回 400，消息说明其仍被引用，库记录与磁盘文件原样保留

### Requirement: 跨任务引用（挂载与解除）

系统 SHALL 让任务以「引用」方式使用资料库文档而不复制字节：`POST /api/tasks/<tid>/library-files`、body 含 `library_file_id`——任务不存在或库文件不存在 → 404，参数缺失/非正整数 → 400；同一任务重复引用同一库文件 → 400。成功后 SHALL 建立一条引用型 FileRecord（归属任务所在空间与该任务，library_file_id 指向库文件，filename/mime/size 抄录自库文件，且不向任务工作空间目录落任何字节），返回 201 含该引用 id、library_file_id 与归属。解除引用：`DELETE /api/tasks/<tid>/library-files/<fid>`——仅当该 FileRecord 存在、归属该任务且确为库引用时删除（只删引用记录，绝不删除资料库实体文件），否则 404。

#### Scenario: 任务引用库文件并可读回

- **WHEN** 用户先上传一个全局库文件，再 POST /api/tasks/<tid>/library-files 挂载它
- **THEN** 返回 201；随后 GET /api/tasks/<tid>/files 的合并清单中出现一条 kind=ref 且 library_file_id 指向该库文件的条目

#### Scenario: 重复引用与引用不存在的文件

- **WHEN** 用户对同一任务重复挂载同一库文件，或挂载不存在的库文件 id
- **THEN** 重复挂载返回 400；不存在的库文件返回 404

#### Scenario: 解除引用后库文件仍在

- **WHEN** 用户对某任务删除其引用记录
- **THEN** 返回 200 {ok:true}；该库文件仍存在于资料库并可被其它任务再次引用
