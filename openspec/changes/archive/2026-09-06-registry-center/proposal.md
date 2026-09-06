## Why

P4（capability-mount）已为 Skill/MCPConnector/KnowledgeBase/Expert 落实体表与任务↔能力挂载底座，但这四类能力实体目前只能靠 SQL seed 生成，缺少面向用户的编辑/管理契约。本提案为「注册中心」补齐四中心的 REST 管理面（design AD-01~04），作为任务挂载/load_mounted 的实体供给方，供 P7 工作台左栏注册中心与 P8 运行时装配消费。

## What Changes

- **技能中心（AD-01）**：`GET/POST/PATCH/DELETE /api/skills`。SKILL.md（skill_md）可新建/编辑，内容变更时 version 自增；enabled 启停；name 唯一；删除技能经 DB 级联清理其任务挂载。
- **MCP 连接器中心（AD-02）**：`GET/POST/PATCH/DELETE /api/mcp`。command/args/env/headers/url 配置；按 transport 做依赖必填校验（stdio 需 command，http 需 url）；env/headers 以 Fernet 整体加密落库，任何出口只给键名/掩码不吐值（复用 crypto）；trust/enabled 字段管理（trust 默认 false）。
- **MCP 连通性测试（AD-02）**：`POST /api/mcp/<id>/test`。stdio 用 stdlib 子进程做最小 MCP 握手（initialize→tools/list），http 探测其端点；超时/失败返回不通过与原因，不 500。
- **知识库中心（AD-03）**：`GET/POST/PATCH/DELETE /api/kb` + `POST /api/kb/<id>/upload` + `POST /api/kb/<id>/search`。upload 仅 `.txt/.md`（UTF-8）真解析并按 chunk_size 切块入新表 knowledge_chunks，同名重传替换旧块，pdf/docx 返回 400「本期暂不支持」（P1 计划）；search 关键词计分返回 top-k 相关块与来源文件（默认关键词检索，向量本期关闭）。
- **专家中心（AD-04）**：`GET/POST/PATCH/DELETE /api/experts`。role 白名单；composed_of 多专家组合（元素存在且非自身、去重；detail 出口把子专家 id 解析为 {id,name,role}）；enabled 启停；删除被其它专家 composed_of 引用者为 400（引用完整性）。
- **数据与迁移**：`migrations/0004_registry.sql` 新增 knowledge_chunks 表（kb_id ON DELETE CASCADE + 按 kb_id 索引）；MCPConnector.env/headers 列由 db.JSON 改 db.Text 承载 Fernet 密文（SQL 层本就 TEXT，真实库亦未写任何明文，无数据迁移）。
- **运行门控语义**：trust/status/enabled 本期只做字段管理（PATCH 显式置位）；「未信任不可挂载 / 停用不可装配」的运行时门控归 P8 运行时装配，本提案不改动挂载接口与 load_mounted。
- **仅后端**：不改前端页面（四中心工作台交互归后续前端提案），REST 契约按前端可消费设计。

## Capabilities

### New Capabilities
- `registry-center`: 技能 / MCP 连接器 / 知识库 / 专家 四中心的实体管理面：CRUD、密钥保护、MCP 连通性测试、KB 上传切块与关键词检索、专家组合。

### Modified Capabilities
<!-- 无：P4 已归档的 capability-mount 主 spec 不改动；trust/status/enabled 门控语义本提案只管理字段，运行时语义留 P8（届时以新提案改主 spec 或新增能力）。 -->

## Impact

- **代码**：`backend/models.py`（MCP env/headers 列类型、新增 KnowledgeChunk 模型）、`backend/migrations/0004_registry.sql`、`backend/services/`（registry_skill / registry_mcp / mcp_test / registry_kb / registry_expert，或等价拆分）、`backend/api/`（skills / mcp_center / kb / experts 四个 blueprint，或并入既有域）、`backend/app.py`（注册 blueprint）、`backend/tests/test_registry.py`。
- **接口契约**：新增 4 组 REST 端点与 2 个 KB 动作端点，沿用既有 PATCH 部分更新 / POST→201 / DELETE→{ok:true} / AppError 收敛约定。
- **依赖**：无新增第三方库（密钥复用 cryptography.Fernet；MCP 测试用 stdlib subprocess；KB 解析切块用标准库字符串处理）。
- **受影响既有行为**：`capability-mount` 归档 spec 与挂载 API 不改；load_mounted 不受影响；真实库 `backend/data/app.db` 尚未应用 0003，重启后端后 migrate.py 将按序执行 0003→0004。
