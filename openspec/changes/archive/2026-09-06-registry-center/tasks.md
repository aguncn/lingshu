# registry-center 任务清单

实现纪律：每条独立可验收；完成一条即把 `- [ ]` 改 `- [x]`。验收口径 = spec 各 SHALL/Scenario + 提案验收命令。

## 1. 模型与迁移

- [x] 1.1 models.py：把 MCPConnector.env/headers 列类型由 db.JSON 改 db.Text（存「整段 JSON Fernet 加密」token，补中文注释说明为什么；SQL 层本就 TEXT，无数据迁移），args 保持 db.JSON；新增 KnowledgeChunk 模型（id、kb_id FK→knowledge_bases ON DELETE CASCADE、file_id 可空、content TEXT NOT NULL、meta db.JSON、embedding db.LargeBinary 可空、时间戳），含 `KnowledgeBase.chunks` 关系(passive_deletes=True)。
- [x] 1.2 迁移 `migrations/0004_registry.sql`：建 knowledge_chunks 表 + `idx_knowledge_chunks_kb_id` 索引（对齐 design D3）；确认真实/临时库迁移链 0003→0004 后 schema_version 升到 4，既有测试不破坏。

## 2. 技能中心（AD-01）

- [x] 2.1 `services/registry_skill.py`：列表/新建/单查/部分更新/删除。name 必填唯一(400)；PATCH 只应用出现字段、skill_md 变更→version+1、enabled 启停；删除技能靠 DB 级联清 task_skill（无手工删关联代码）。
- [x] 2.2 `api/skills.py`：`GET/POST /api/skills` + `GET/PATCH/DELETE /api/skills/<id>`（POST→201、DELETE→{"ok":true}、AppError 收敛）。GET 出口含 skill_md 全文（供预览，渲染归前端）。

## 3. MCP 连接器中心（AD-02）

- [x] 3.1 `services/registry_mcp.py`：列表/新建/单查/部分更新/删除。name 唯一(400)；transport 白名单默认 stdio、stdio 缺 command→400、http 缺 url→400；args 须字符串数组、env/headers 须对象否则 400；trust/enabled 字段可 PATCH；env/headers 写时整体 Fernet 加密落库、出口只附 env_keys/headers_keys（永不含值，design D2）；删除级联清 task_mcp。
- [x] 3.2 `api/mcp_center.py`：`GET/POST /api/mcp` + `GET/PATCH/DELETE /api/mcp/<id>`（形态沿用 model_prompt 域）。

## 4. MCP 连通性测试（AD-02）

- [x] 4.1 新增 `tests/fixtures/mcp_fake_server.py`：极简 MCP stdio JSON-RPC 服务端（initialize→notifications/initialized→tools/list 回 2~3 个工具），供测试离线驱动「成功」路径。
- [x] 4.2 `services/mcp_test.py` + `api/mcp_center.py` 内 `POST /api/mcp/<id>/test`：stdio 以 command+args(合并解密 env) 起子进程做最小握手并数 tools/list；http 向 url(带解密 headers) 探测；10s 超时且进程必回收；失败回 `200 {ok:false,reason}`（含 stderr 摘要，不 5xx）、成功回 `ok:true+tools+tool_count`；连接器不存在→404。

## 5. 知识库中心（AD-03）

- [x] 5.1 `services/registry_kb.py`：列表/新建/部分更新/删除。name 唯一(400)；chunk_size 正整数默认 400；status 白名单(draft/ready/disabled)默认 ready；PATCH status=disabled 后 upload/search 拒绝(400)；删除靠 DB 级联清 knowledge_chunks 与 task_kb。
- [x] 5.2 `api/kb.py`：`GET/POST /api/kb` + `PATCH/DELETE /api/kb/<id>`。

## 6. 知识库上传与检索（AD-03）

- [x] 6.1 上传解析切块：`POST /api/kb/<id>/upload`（multipart 字段 file）。仅 .txt/.md 且 UTF-8 严格解码受理；.pdf/.docx 或解码失败→400 并明确「本期暂不支持/编码不可解」；文本按 chunk_size 按字符切窗入 knowledge_chunks（meta 记 filename/chunk_index/chars，file_id 恒 NULL）；单事务内「同库同名文件整体替换旧块、异名保留」（design D4）。返回 200 {kb_id, filename, chars, chunk_count}。库不存在→404、disabled→400。
- [x] 6.2 关键词检索：`POST /api/kb/<id>/search`（body {query, top_k?}）。query 必填非空否则 400；top_k 默认 5、超 20 收敛；分词含空白切词 + 整句一词的精确子串计分，按 (-score, chunk_index) 取 top-k，每块出口含 content+来源 filename+chunk_index+score；无命中→200 空数组（design D5）。库不存在→404、disabled→400。

## 7. 专家中心（AD-04）

- [x] 7.1 `services/registry_expert.py` + `api/experts.py`：`GET/POST /api/experts` + `GET/PATCH/DELETE /api/experts/<id>`。name 唯一(400)；role 白名单(ops-sme/general)默认 general；composed_of 写时校验：元素正整数、表中存在、≠自身、去重，否则 400；`GET /api/experts/<id>` 出口额外含 composed=[{id,name,role}] 对象列表；enabled 启停；DELETE 被其它专家 composed_of 引用→400（引用完整性），否则删除且级联清 task_expert。

## 8. 集成与一致性修正

- [x] 8.1 app.py 注册 4 个新 blueprint（skills/mcp_center/kb/experts）；把 `capability.py` load_mounted docstring 里「装配期门控属 P5」过期字样更正为 P8（纯注释，design D9，不改行为）。

## 9. 验收测试

- [x] 9.1 新增 `backend/tests/test_registry.py`：覆盖 spec 各 Scenario 判据——技能 新建编辑(version+1/启停)/重名400/删级联清挂载；MCP  transport 必填校验/env-keys 无明文/清除替换；MCP test 未知404/假 server 成功(工具数>0)/不可用 ok=false；KB  建库默认值+停用门控/删库级联清切块；upload md 切块数>0/pdf 400/同名替换异名保留；search 命中/空 query 400/无命中空数组；专家 组合读回 composed 明细/非法组合400/删被引用400。测试沿用 app(tmp_path) 夹具 + `_make_entity` 风格拿真实 id。
- [x] 9.2 全量回归与手工冒烟：`uv run pytest backend/tests/ -q` 全绿（含既有 33 例无回归）；按提案验收命令起后端(临时 LINGSHU_DATA_DIR)对四中心 + mcp test + kb upload/search 逐条 curl 冒烟后清理。

<!-- 完成标准：全部 [x]，openspec validate registry-center 通过，spec 的 Requirement/Scenario 均有测试或手工判据覆盖。 -->
