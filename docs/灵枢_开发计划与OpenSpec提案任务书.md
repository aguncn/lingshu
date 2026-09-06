# 灵枢 (Lingshu) 开发计划与 OpenSpec 提案任务书

> 配套：《技术方案与架构设计》＋《开发执行手册》
> 目标：把 PRD 主要功能需求拆成 **10 个 P0 提案**，每个提案 ~10 条可验收任务，逐个 `/opsx:apply` 落地。
> 工作流：Claude Code ＋ ccswitch → DeepSeek V4 Flash ＋ OpenSpec（extended profile）。

---

## 0. 速查：OpenSpec 命令（Claude Code 斜杠命令）

| 阶段 | 命令 | 作用 |
|---|---|---|
| 想清楚 | `/opsx:explore <想法>` | 只思考不写码，理清范围 |
| 出计划 | `/opsx:propose <name>` | 生成 changes/<name>/{proposal.md, specs/, design.md, tasks.md} |
| 审查 | （你直接改文件 / 让 agent 改） | 改范围、改 specs、改 tasks |
| 实现 | `/opsx:apply <name>` | agent 按 tasks.md 逐条实现并打勾（**新开干净会话**） |
| 校验 | `/opsx:verify <name>` | 对照 specs/ 核验实现是否匹配 |
| 归档 | `/opsx:archive <name>` | Delta Specs 合入 openspec/specs/，变更进 archive/ |

> 命令前缀可能为 `/opsx:`（新版）或 `/openspec-`（旧版），以 `openspec --help` 为准。
> `verify` 属 **extended profile**，需在初始化后开启（见《开发执行手册》§2）。

---

## 1. 开发阶段总览（里程碑）

| 里程碑 | 提案 | 交付物 | 对应 PRD |
|---|---|---|---|
| **M0 脚手架** | P1 scaffold | 前后端能跑、OpenSpec 就绪、CLAUDE.md | 基础 |
| **M1 资产与任务** | P2 space-task / P3 model-prompt | 空间/任务/模型/提示词 | TR, MD |
| **M2 能力装配** | P4 capability / P5 registry | 技能/MCP/KB/专家装配与注册中心 | CAP, AD |
| **M3 工作台** | P6 library / P7 workbench-ui | 资料库 + 三栏工业风 UI | LB, UI-01~07 |
| **M4 智能体内核** | P8 agentscope-runtime / P9 scenario | AgentScope 运行时 + 十二域模板 | §8,§9 |
| **M5 安全收尾** | P10 security-audit | 密钥加密 + 审计 + 最小权限 | NF |
| （后续）P1/P2 | AU / 深度 MCP / 多专家 | 自动化与深度编排 | AU, P1 |

**建议执行顺序**：P1 → P2 → P3 → P4 → P5 → P6 → P7 → P8 → P9 → P10。P7(UI) 可在 P2~P6 任一后端就绪后并行，但单人建议串行到 M3 再集中做 UI，避免反复改接口。

---

## 2. Proposal ↔ PRD 需求映射表

| 提案(name) | 覆盖 PRD | 一句话目标 |
|---|---|---|
| `scaffold-lingshu` | 基础 | uv+Flask+SQLite+Vue+Vite 跑通，OpenSpec/CLAUDE.md 就位 |
| `space-task-mgmt` | TR-01~06 | 空间/任务 CRUD、权限、工作空间文件落盘 |
| `model-prompt-config` | MD-01~04 | 模型供应商配置、任务绑模型、提示词库版本化、常用类型 |
| `capability-mount` | CAP-01~04 | 任务挂载 技能/MCP/知识库/专家 的数据与 API |
| `registry-center` | AD-01~04 | 技能/MCP/知识库/专家 统一管理后台 |
| `library` | LB-01 | 跨任务集中资料库 |
| `workbench-ui` | UI-01~07 | 三栏工业风工作台 + 命令面板 + 细节栏 + 设置 |
| `agentscope-runtime` | §8 技术底座 | AgentScope 集成：模型工厂+SSE+内置工具+权限 |
| `scenario-templates` | §8,§9 | 十二运维域提示词模板 + 场景装配 |
| `security-audit` | NF | 密钥加密 + 全量审计 + MCP 最小权限 |

---

## 3. 任务颗粒度原则（务必遵守）

每条任务满足 **INVEST-lite**：单条可独立完成、可独立验收。具体：
- 一条 = 一个接口 / 一张表 / 一个 Vue 视图 / 一个迁移脚本 / 一个服务函数。
- 不在一条里塞「前后端 + 数据库」三件事；跨层拆多条。
- 每条后标注「验收方法」（pytest / curl / 手动点）。
- 每提案 8–12 条；超出则拆提案。
- agent 实现一条就打勾一条；中断后新会话 `/opsx:apply` 从首个未勾处续做。

---

## 4. 十个 P0 提案详述

> 每个提案含：① `/opsx:propose` 提示词（你打给 Claude Code）② proposal.md ③ tasks.md（~10）④ 验收命令 ⑤ 手工验收清单。
> 提示词里 `@` 引用的文档路径，请替换成本机实际路径（即本文档与《技术方案》路径）。

---

### P1 · `scaffold-lingshu`（脚手架）

**① /opsx:propose 提示词**
```
/opsx:propose scaffold-lingshu
参照 @灵枢_技术方案与架构设计.md 第4/9节 与 @灵枢_开发执行手册.md ，搭建灵枢项目骨架：
- Windows + uv 创建 backend 虚拟环境（Python 3.12），依赖 Flask、Flask-CORS、SQLAlchemy、agentscope>=2.06、pyfernet(密钥加密)、python-dotenv。
- Vue3 + Vite + Element Plus 前端骨架，含 router/pinia/axios 基础封装与 /api 代理到 5000。
- backend/app.py 提供 GET /api/health 返回 {"ok":true}；frontend 首页调用并展示。
- 建立 openspec/ 目录与 project.md；写入 CLAUDE.md（内容见执行手册）。
- 仅做能跑通的最小骨架，不实现任何业务功能。
```

**② proposal.md**
```
## Why
灵枢需要可运行的工程骨架，统一前后端技术栈、目录结构与 OpenSpec 工作流，后续提案才能在其上增量开发。

## What Changes
- 新增 backend/（Flask + SQLite + SQLAlchemy + AgentScope 依赖，uv 管理）
- 新增 frontend/（Vue3 + Vite + Element Plus + Pinia + Axios）
- 新增 openspec/project.md 与 CLAUDE.md
- 前后端联调跑通 /api/health

## Impact
无业务表；仅基础设施。后续 P2+ 在其上建表与接口。
```

**③ tasks.md**
```
- [ ] 1. 用 uv 初始化 backend：pyproject.toml + uv.lock，安装 Flask/Flask-CORS/SQLAlchemy/agentscope(py)/cryptography/python-dotenv
- [ ] 2. 建 backend/app.py：Flask 实例 + CORS + GET /api/health 返回 {"ok":true,"ts":...}
- [ ] 3. 建 backend/config.py 与 extensions.py（db 单例，SQLite 路径 data/app.db）
- [ ] 4. 写 backend/migrate.py 轻量迁移器骨架（读 schema_version，执行 migrations/*.sql）
- [ ] 5. 用 Vite 初始化 frontend，安装 element-plus/pinia/axios，配 vite.config 代理 /api→5000
- [ ] 6. frontend 首页调用 /api/health 并展示状态（验证联调）
- [ ] 7. 建 openspec/ 目录与 openspec/project.md（项目简述）
- [ ] 8. 写 CLAUDE.md（见《开发执行手册》§3 全文）
- [ ] 9. 写 .env.example（LINGSHU_MASTER_KEY、上传目录、CORS 来源）与 .gitignore（.venv/data/node_modules）
- [ ] 10. 写 README.md：启动前后端的两条命令；验证 pytest 空跑通过
```

**④ 验收命令**
```powershell
cd backend; uv run flask --app app.py --debug run --port 5000   # 另开终端
curl http://127.0.0.1:5000/api/health                           # 应返回 {"ok":true,...}
cd frontend; npm run dev                                        # 浏览器打开，首页显示“后端就绪”
```

**⑤ 手工验收**
- [ ] 后端 5000 端口起得来，`/api/health` 返回 ok。
- [ ] 前端 5173 起得来，首页显示后端就绪状态。
- [ ] `openspec/project.md` 存在；`CLAUDE.md` 存在且内容完整。
- [ ] `git status` 未见 `.venv`、`data/`、`node_modules` 被跟踪。

---

### P2 · `space-task-mgmt`（空间与任务管理 · TR-01~06）

**① /opsx:propose 提示词**
```
/opsx:propose space-task-mgmt
参照 @灵枢_技术方案与架构设计.md 第5.2节(Space/Task/FileRecord) 与第6节接口，实现：
- Space/Task/User/Membership/FileRecord 模型与迁移脚本
- 空间 CRUD + 切换 + 删除；任务 CRUD（必属空间、选类型、绑模型占位）
- 权限字段(visibility: private/team/public) 与 Membership 角色(Owner/Editor/Viewer)
- 任务重命名同步；打开工作空间列出 data/spaces/<space>/<task>/ 下文件
- 文件按「空间→任务」两级落盘，删除任务可清理文件
```

**② proposal.md**
```
## Why
空间是隔离与协作边界，任务是最小运行单元；没有它们，其余能力（模型/技能/对话）无挂载主体。

## What Changes
- 新增 5 张表 + 迁移脚本
- 新增 /api/spaces、/api/tasks、/api/tasks/<id>/files 端点
- 文件两级目录落盘与清理

## Impact
被 MD/CAP/AD/LB/UI 全部依赖；是核心骨架。
```

**③ tasks.md**
```
- [ ] 1. 在 models.py 定义 Space/User/Membership/Task/FileRecord（字段见设计§5.2）
- [ ] 2. 写迁移脚本 0001_spaces_tasks.sql 建表 + 初始化内置管理员 User
- [ ] 3. 实现 GET/POST /api/spaces（列表/新建，含 visibility）
- [ ] 4. 实现 PATCH/DELETE /api/spaces/<id>（改名/删除，删除清目录）
- [ ] 5. 实现 GET/POST /api/spaces/<sid>/tasks（建任务：命名+类型+绑 model_config 占位）
- [ ] 6. 实现 GET/PATCH/DELETE /api/tasks/<id>（打开/改名/删，删清文件目录）
- [ ] 7. 实现任务权限字段与 Membership 角色写入（TR-03）
- [ ] 8. 实现文件落盘服务 file_store.py（data/spaces/<space>/<task>/）
- [ ] 9. 实现 GET /api/tasks/<id>/files 列出工作空间文件（TR-05）
- [ ] 10. 写 pytest 冒烟：建空间→建任务→列文件→删任务清目录 全通过
```

**④ 验收命令**
```powershell
uv run pytest backend/tests/test_space_task.py -q
curl -X POST http://127.0.0.1:5000/api/spaces -H "Content-Type: application/json" -d "{\"name\":\"demo\",\"visibility\":\"private\"}"
curl http://127.0.0.1:5000/api/spaces
```

**⑤ 手工验收**
- [ ] 新建空间出现在列表；改名/删除生效。
- [ ] 在空间下新建任务，必选类型；任务出现在该空间分组下。
- [ ] 删除任务后，`data/spaces/<space>/<task>/` 目录被清理。
- [ ] 文件接口返回空列表（尚未有文件，目录存在即可）。

---

### P3 · `model-prompt-config`（模型与提示词 · MD-01~04）

**① /opsx:propose 提示词**
```
/opsx:propose model-prompt-config
参照设计§5.2(ModelProvider/ModelConfig/PromptTemplate) 与第6节接口，实现：
- ModelProvider 增删（name/type/base_url/default_model/api_key_enc 加密）
- ModelConfig 任务级绑定（model_name/temperature/max_tokens/timeout）
- 提示词库 PromptTemplate（保存/分类/版本化 parent_id）
- 常用任务类型预设（写文档/写代码/数据分析/排障）作为种子
- 设置中心用的供应商配置接口（MD-04）
```

**② proposal.md**
```
## Why
模型与提示词是智能体运行的燃料；需支持多供应商 + 任务级参数 + 可复用提示词。

## What Changes
- 新增 ModelProvider/ModelConfig/PromptTemplate 表 + 迁移
- /api/model-providers、/api/tasks/<id>/model-config、/api/prompts
- api_key 加密存储（cryptography.Fernet），明文不入库

## Impact
被 agentscope-runtime(P8) 消费；被 UI 细节栏(P7)调用。
```

**③ tasks.md**
```
- [ ] 1. 定义 ModelProvider/ModelConfig/PromptTemplate 模型（§5.2）
- [ ] 2. 迁移 0002_models_prompts.sql 建表 + 种子常用任务类型
- [ ] 3. 实现加解密工具 crypto.py（Fernet，密钥取 LINGSHU_MASTER_KEY）
- [ ] 4. GET/POST /api/model-providers（建供应商，密钥加密落库）
- [ ] 5. PATCH/DELETE /api/model-providers/<id>（改/删，列表脱敏显示密钥）
- [ ] 6. GET/POST/PATCH /api/tasks/<id>/model-config（任务绑模型+调参 MD-01）
- [ ] 7. GET/POST/PATCH/DELETE /api/prompts（提示词库 CRUD MD-03）
- [ ] 8. 提示词版本化：保存时写 parent_id 副本（MD-03）
- [ ] 9. 常用任务类型种子数据写入（写文档/写代码/数据分析/排障 MD-02）
- [ ] 10. pytest：建供应商→绑任务→取回配置解密一致；提示词版本链正确
```

**④ 验收命令**
```powershell
uv run pytest backend/tests/test_model_prompt.py -q
curl -X POST http://127.0.0.1:5000/api/model-providers -H "Content-Type: application/json" -d "{\"name\":\"deepseek\",\"type\":\"deepseek\",\"base_url\":\"https://api.deepseek.com/v1\",\"default_model\":\"deepseek-v4-flash\",\"api_key_enc\":\"<明文，后端加密>\"}"
curl http://127.0.0.1:5000/api/model-providers   # 密钥应脱敏（如 ****）
```

**⑤ 手工验收**
- [ ] 新建供应商后，列表里密钥显示为掩码，DB 里为密文。
- [ ] 给任务绑模型并设置 temperature，回读一致。
- [ ] 提示词库能新建/分类/再保存生成新版本（parent_id 链正确）。

---

### P4 · `capability-mount`（能力装配 · CAP-01~04）

**① /opsx:propose 提示词**
```
/opsx:propose capability-mount
参照设计§5.2 关联表(task_skill/task_mcp/task_kb/task_expert) 与第6节 PUT /api/tasks/<id>/caps，
实现任务级挂载 技能/MCP/知识库/专家 的关联表与 API；仅做数据关联，不接运行时（运行时在 P8）。
```

**② proposal.md**
```
## Why
PRD 核心交互：能力按任务粒度按需挂载、可折叠（UI-06），避免全局污染。

## What Changes
- 新增 4 张关联表
- PUT /api/tasks/<id>/caps 接收 {skills:[], mcps:[], kbs:[], experts:[]}
- GET 返回当前挂载

## Impact
被 registry-center(P5) 提供实体；被 agentscope-runtime(P8) 消费。
```

**③ tasks.md**
```
- [ ] 1. 定义关联表 task_skill/task_mcp/task_kb/task_expert（task_id + 目标 id）
- [ ] 2. 迁移 0003_task_caps.sql
- [ ] 3. PUT /api/tasks/<id>/caps 全量覆盖式更新挂载
- [ ] 4. GET /api/tasks/<id>/caps 返回当前挂载清单
- [ ] 5. 挂载校验：目标实体存在才允许关联（防脏引用）
- [ ] 6. 任务删除时级联清理关联（CAP 挂载随任务走）
- [ ] 7. 写 service/capability.py 聚合读取（供 P8 用）
- [ ] 8. pytest：挂载→读取→改→删 一致
- [ ] 9. 接口文档注释（请求/响应字段）写入代码中
- [ ] 10. 与 P2 任务接口联调：建任务后挂载空能力可读回空
```

**④ 验收命令**
```powershell
uv run pytest backend/tests/test_capability.py -q
curl -X PUT http://127.0.0.1:5000/api/tasks/<id>/caps -H "Content-Type: application/json" -d "{\"skills\":[],\"mcps\":[],\"kbs\":[],\"experts\":[]}"
curl http://127.0.0.1:5000/api/tasks/<id>/caps
```

**⑤ 手工验收**
- [ ] PUT 挂载后 GET 回显一致。
- [ ] 关联不存在的实体 id 被拒绝（400）。
- [ ] 删任务后其挂载记录消失。

---

### P5 · `registry-center`（注册中心 · AD-01~04）

**① /opsx:propose 提示词**
```
/opsx:propose registry-center
参照设计§5.2(Skill/MCPConnector/KnowledgeBase/Expert) 与第6节接口，实现四中心：
- 技能中心：SKILL.md 编辑/预览/启用（AD-01）
- MCP 连接器中心：command/args/env/headers/url 配置 + 连通性测试 POST /api/mcp/<id>/test（AD-02）
- 知识库中心：文件上传/解析/切块/检索状态（AD-03，向量可选）
- 专家中心：创建/组合(composed_of 多专家)/启停（AD-04）
```

**② proposal.md**
```
## Why
技能/MCP/知识库/专家需统一编辑管理入口（左栏注册中心），是能力供给方。

## What Changes
- Skill/MCPConnector/KnowledgeBase/Expert 表 + 迁移
- 四组 CRUD 接口；MCP 连通性测试；KB 上传+切块+检索
- trust 开关（启用前需信任 AD-02）

## Impact
实体被 P4 挂载；被 P8 运行时消费。
```

**③ tasks.md**
```
- [ ] 1. 定义 Skill/MCPConnector/KnowledgeBase/Expert 模型（§5.2）
- [ ] 2. 迁移 0004_registry.sql 建表
- [ ] 3. 技能中心 CRUD：GET/POST/PATCH/DELETE /api/skills（skill_md 编辑/启用 AD-01）
- [ ] 4. MCP 中心 CRUD：/api/mcp；trust 字段默认 false，启用前需显式信任（AD-02）
- [ ] 5. MCP 连通性测试：POST /api/mcp/<id>/test 按 transport 启动/请求 list_tools
- [ ] 6. 知识库中心：/api/kb CRUD + POST /api/kb/<id>/upload（解析+切块入 KnowledgeChunk）
- [ ] 7. KB 检索：POST /api/kb/<id>/search 返回 top-k（默认关键词，可选向量）
- [ ] 8. 专家中心：/api/experts CRUD + composed_of 多专家组合（AD-04）
- [ ] 9. 文件解析接入 agentscope.rag.TextParser（txt/md/pdf/docx）
- [ ] 10. pytest：四中心 CRUD + MCP 测试连通 + KB 上传检索 冒烟
```

**④ 验收命令**
```powershell
uv run pytest backend/tests/test_registry.py -q
curl -X POST http://127.0.0.1:5000/api/skills -H "Content-Type: application/json" -d "{\"name\":\"sql-analysis\",\"skill_md\":\"# SQL 分析技能...\"}"
curl -X POST http://127.0.0.1:5000/api/mcp -H "Content-Type: application/json" -d "{\"name\":\"db-ro\",\"transport\":\"stdio\",\"command\":\"npx\",\"args\":[\"-y\",\"@modelcontextprotocol/server-sqlite\",\"--db\",\"/tmp/ro.db\"]}"
curl -X POST http://127.0.0.1:5000/api/mcp/<id>/test   # 返回 list_tools 数量
```

**⑤ 手工验收**
- [ ] 技能可新建/编辑/预览/启用/停用。
- [ ] MCP 连接器配置后「测试连接」返回工具列表；未信任不可在任务挂载。
- [ ] 知识库上传一个 md，检索能返回相关片段。
- [ ] 专家可建单专家，也可组合多专家（composed_of）。

---

### P6 · `library`（集中资料库 · LB-01）

**① /opsx:propose 提示词**
```
/opsx:propose library
参照设计§5.2 与第6节 /api/library，实现跨任务集中资料库：上传/下载/列表/分享标记/跨任务引用。
复用 P2 的 file_store 落盘，但库文件归空间或全局，不绑单一任务。
```

**② proposal.md**
```
## Why
避免文件散落；资料库是跨任务可复用的文件资产（区别于任务工作空间文件）。

## What Changes
- /api/library CRUD（基于 FileRecord 扩展或独立 LibraryFile 表）
- 上传/下载/列表/引用关系

## Impact
被 CAP-03 知识库引用；被 UI 资料库导航(P7)展示。
```

**③ tasks.md**
```
- [ ] 1. 定义 LibraryFile 模型（space_id 可空=全局，filename/path/size/owner）
- [ ] 2. 迁移 0005_library.sql
- [ ] 3. POST /api/library 上传（落 data/library/）
- [ ] 4. GET /api/library 列表（按空间/全局过滤 LB-01）
- [ ] 5. GET /api/library/<id>/download 下载
- [ ] 6. DELETE /api/library/<id> 删除（同步清文件）
- [ ] 7. 分享标记字段 shared（团队/公开可见性）
- [ ] 8. 跨任务引用：FileRecord 可指向 LibraryFile id（引用不复制）
- [ ] 9. 与 file_store 复用落盘逻辑
- [ ] 10. pytest：上传→列表→下载→删除 一致
```

**④ 验收命令**
```powershell
uv run pytest backend/tests/test_library.py -q
curl -X POST http://127.0.0.1:5000/api/library -F "file=@./some.md"
curl http://127.0.0.1:5000/api/library
```

**⑤ 手工验收**
- [ ] 上传文件出现在资料库列表；下载内容一致。
- [ ] 删除后磁盘文件消失。
- [ ] 全局库与空间库切换可见。

---

### P7 · `workbench-ui`（三栏工作台 · UI-01~07）

**① /opsx:propose 提示词**
```
/opsx:propose workbench-ui
参照设计§4.4（左栏/右栏布局）与 PRD UI-01~07，用 Vue3+Element Plus 实现三栏工业风工作台：
- 左栏：新建任务/导航(专家·技能·MCP/自动化/资料库)/任务列表(按空间分组可搜索)/个人信息+设置
- 右栏：顶部分类+提示词模板；中部会话(对话+文件树)；底部可折叠细节栏(模型/技能/资料/MCP/工作空间/权限)+输入框
- 命令面板 Ctrl/Cmd+K；抽屉承载注册中心与设置；暗色模式；状态徽标；时间线
仅前端，调用已完成的 P2~P6 接口。
```

**② proposal.md**
```
## Why
PRD 核心差异点是「生产级工业风三栏工作台」，决定产品可用性。

## What Changes
- Vue 路由/视图/组件：Workbench、SpaceList、TaskList、RegistryDrawer、Settings、CommandPalette
- 调用 P2~P6 全部接口；SSE 会话留接口占位（P8 接）

## Impact
用户唯一可见入口；被 P8/P9 注入智能体能力。
```

**③ tasks.md**
```
- [ ] 1. 搭布局：ElContainer 左栏(全高)+右栏，左栏四区块（UI-01）
- [ ] 2. 左栏：新建任务按钮 + 导航(专家·技能·MCP/自动化/资料库) + 任务列表(按空间分组、可搜索)
- [ ] 3. 左栏底部：个人信息 + 设置入口（UI-01/07）
- [ ] 4. 右栏顶部：常用任务分类 + 提示词模板快捷入口
- [ ] 5. 右栏中部：会话区（对话气泡 + 文件树/预览占位）
- [ ] 6. 右栏底部：可折叠细节栏（模型/技能/资料/MCP/工作空间/权限模板），默认收起（UI-06）
- [ ] 7. 命令面板 Ctrl/Cmd+K 组件（UI-03）
- [ ] 8. 抽屉：注册中心(技能/MCP/知识库/专家) 与 设置中心（UI-03/07）
- [ ] 9. 状态徽标 ElTag + 时间线 ElTimeline + 暗色模式切换（UI-02/03/05）
- [ ] 10. 接通 P2~P6 接口联调：建空间/任务、挂能力、开资料库 全可点
```

**④ 验收命令**
```powershell
cd frontend; npm run build   # 构建通过无类型/语法错误
npm run dev                  # 打开浏览器手动走查
```

**⑤ 手工验收**
- [ ] 左栏四区块齐全，任务按空间分组、可搜索。
- [ ] 右栏三区（分类/会话/细节栏）布局正确，细节栏默认收起可展开。
- [ ] Ctrl+K 打开命令面板；设置抽屉可切暗色模式。
- [ ] 实际点一遍：建空间→建任务→挂能力→开注册中心编辑技能→资料库上传。

---

### P8 · `agentscope-runtime`（AgentScope 集成底座 · §8 技术底座）

**① /opsx:propose 提示词**
```
/opsx:propose agentscope-runtime
参照设计§7(7.1~7.7) 实现智能体运行时：
- ModelFactory：ModelProvider+ModelConfig → AgentScope OpenAIChatModel（OpenAI 兼容，接 DeepSeek/ccswitch）
- AgentRuntime.build()：组装 Agent(ReAct)+Toolkit(内置工具+Bash/Read/Write/Edit/Grep/Glob)+拼系统提示
- SSE 桥接：Flask 生成器+线程队列，把 agent.reply_stream() 事件流转 SSE（§7.6）
- Permission(confirm 模式) + 审计中间件（写 AuditLog）
- POST /api/tasks/<id>/chat(SSE) 与 GET /api/tasks/<id>/messages
消费 P2~P5 的数据（任务/模型/挂载能力）。
```

**② proposal.md**
```
## Why
没有运行时，平台只是个空壳；AgentScope 提供 ReAct+MCP+流式+权限，正好对齐 PRD。

## What Changes
- services/agent_runtime.py、model_factory.py、mcp_client.py、skill_loader.py、audit.py
- /api/tasks/<id>/chat(SSE)、/api/tasks/<id>/messages
- 内置工具默认 confirm（危险操作二次确认）

## Impact
被 P9 场景模板注入；被 UI 会话区(P7)消费。
```

**③ tasks.md**
```
- [ ] 1. model_factory.py：provider+cfg → OpenAIChatModel（base_url/api_key/model）
- [ ] 2. AgentRuntime.build()：读取 Task+ModelConfig+挂载，组装 Agent+Toolkit
- [ ] 3. 内置工具接入 Bash/Read/Write/Edit/Grep/Glob（AgentScope tool）
- [ ] 4. Permission 中间件：内置写类工具默认 confirm（危险操作二次确认 NF）
- [ ] 5. SSE 桥接：Flask 生成器+线程队列转 agent.reply_stream 事件（§7.6）
- [ ] 6. POST /api/tasks/<id>/chat 接收消息→流式返回；落 Message 表
- [ ] 7. GET /api/tasks/<id>/messages 返回历史
- [ ] 8. 审计中间件：模型调用/工具调用写 AuditLog（NF 安全）
- [ ] 9. mcp_client.py：按 MCPConnector 配置实例化 StdIO/HTTP 客户端并注册工具（接 P5）
- [ ] 10. pytest/集成测：给一个任务发消息，SSE 收到文本事件，Message 落库
```

**④ 验收命令**
```powershell
uv run pytest backend/tests/test_runtime.py -q
# 前端或 curl 模拟 SSE：
curl -N -X POST http://127.0.0.1:5000/api/tasks/<id>/chat -H "Content-Type: application/json" -d "{\"message\":\"你好\"}"
```

**⑤ 手工验收**
- [ ] 在 UI 会话区发一句「你好」，看到打字机流式回复。
- [ ] 触发 Bash/Write 类工具时，出现「二次确认」提示（confirm 模式）。
- [ ] 审计日志出现本次对话与工具调用记录。
- [ ] 挂载一个 MCP 连接器后，Agent 能调用其工具（list_tools 可见）。

---

### P9 · `scenario-templates`（十二域场景模板 · §8,§9）

**① /opsx:propose 提示词**
```
/opsx:propose scenario-templates
参照设计§8 十二域表与§9 统一约束，实现：
- ScenarioTemplate 表 + 种子十二域（system_prompt + task_template + preset_skills/mcp/kb/expert）
- 新建任务选域即套用预设装配（写 P2 建任务逻辑或 P4 挂载逻辑）
- 统一约束段（禁臆造/二次确认/引来源/结构化输出）拼进系统提示
- 十二域系统提示词模板落 prompts/ 目录供版本管理
```

**② proposal.md**
```
## Why
十二运维域是 PRD 核心差异点；每域差异化提示词+装配，决定智能体「专业不像玩具」。

## What Changes
- ScenarioTemplate 表 + 迁移 + 十二域种子
- 建任务时按 domain 套用预设（调用 P4 caps 接口）
- 统一约束注入 AgentRuntime（P8）

## Impact
让 P8 运行时按域产出专业结论；被 UI 顶部分类(P7)展示。
```

**③ tasks.md**
```
- [ ] 1. 定义 ScenarioTemplate 模型（domain/name/system_prompt/task_template/preset_*）
- [ ] 2. 迁移 0006_scenarios.sql + 种子十二域数据
- [ ] 3. 写 prompts/ 下十二域系统提示词模板 .md（按设计§8 要点）
- [ ] 4. 统一约束段常量（禁臆造/二次确认/引来源/结构化）注入 AgentRuntime 系统提示
- [ ] 5. 建任务选 domain 时调用 P4 套用 preset_skills/mcp/kb/expert
- [ ] 6. GET /api/scenarios 返回十二域列表（UI 分类用）
- [ ] 7. 每域预设装配示例数据（至少监控巡检/故障诊断两域有真实 preset）
- [ ] 8. AgentRuntime 读取 ScenarioTemplate 拼系统提示
- [ ] 9. pytest：选域建任务→caps 含预设；发消息系统提示含域约束
- [ ] 10. 文档：十二域提示词设计说明写入 prompts/README.md
```

**④ 验收命令**
```powershell
uv run pytest backend/tests/test_scenarios.py -q
curl http://127.0.0.1:5000/api/scenarios   # 返回 12 个域
```

**⑤ 手工验收**
- [ ] UI 顶部出现 12 个域分类。
- [ ] 选「故障诊断」建任务，细节栏自动挂上监控+日志+链路 MCP 与 SRE 专家预设。
- [ ] 对该任务发「排查某服务 5xx 升高」，回复含影响面/时间线/MTTR 结构。

---

### P10 · `security-audit`（安全与审计 · NF）

**① /opsx:propose 提示词**
```
/opsx:propose security-audit
参照设计§7.7 与 PRD NF，补齐安全基线：
- 密钥加密落库已含(P3)，此处补齐密钥不落地策略（环境变量优先覆盖）
- 全量操作审计：对 spaces/tasks/skills/mcp/kb/experts/automations 写操作统一记 AuditLog
- MCP 最小权限约定（DB 只读描述、trust 前置）+ 危险工具 confirm 已在 P8
- 统一的错误处理与 401/403/400 响应；敏感字段脱敏
```

**② proposal.md**
```
## Why
PRD NF 明确安全/审计/最小权限；单人项目也要有可追溯与基本边界。

## What Changes
- AuditService 统一装饰器/中间件记录写操作
- 密钥环境变量覆盖逻辑（LINGSHU_*_API_KEY）
- 统一错误响应与脱敏

## Impact
横切所有已有接口；是上线前最后一道基线。
```

**③ tasks.md**
```
- [ ] 1. AuditService：提供 audit(action, target_type, target_id, detail) 封装
- [ ] 2. 在 P2~P6 写接口统一调用 AuditService（谁/动作/对象/详情/时间）
- [ ] 3. GET /api/audit 列表接口（分页/过滤）
- [ ] 4. 密钥环境变量优先：ModelFactory 支持 LINGSHU_<PROVIDER>_API_KEY 覆盖 DB
- [ ] 5. MCP 最小权限：DB 只读约定写入连接器描述模板；trust 前置已在 P5
- [ ] 6. 统一异常处理：401/403/400/500 标准 JSON 响应
- [ ] 7. 敏感字段脱敏工具（密钥/ env 展示掩码）
- [ ] 8. 危险工具 confirm 已在 P8，补充审计其确认结果
- [ ] 9. pytest：写操作均产生 AuditLog；脱敏正确
- [ ] 10. 安全说明写入 README 安全章节
```

**④ 验收命令**
```powershell
uv run pytest backend/tests/test_security.py -q
curl http://127.0.0.1:5000/api/audit   # 能看到历史写操作
```

**⑤ 手工验收**
- [ ] 任意建/改/删操作后，`/api/audit` 出现对应记录（含 actor/动作/对象/时间）。
- [ ] 设 `LINGSHU_DEEPSEEK_API_KEY` 环境变量后，运行时优先用它而非 DB 密文。
- [ ] 返回体里密钥字段均为掩码。

---

## 5. P1 / P2 提案清单（路线图，非本次必做）

| 提案 | 覆盖 | 备注 |
|---|---|---|
| `automation` | AU-01 | cron/一次性/事件触发，复用任务模板，APScheduler 单进程 |
| `deep-mcp` | P0 基础 MCP 深化 | 监控/日志/DB/CMDB 真实连接器落地 |
| `expert-collab` | AD-04 组合 | AgentScope MsgHub/Team 多专家编排 |
| `deep-orchestration` | 变更/告警/故障 | Pipeline 深度编排 |
| `capacity-forecast` | P2 | 容量预测模型 |
| `kg-rag` | P2 | 运维知识图谱 + 向量化 RAG |

---

## 6. 收尾建议

- 每个 P0 提案走完 `apply → verify → archive` 再开下一个。
- `verify` 不通过就回 `proposal.md`/`tasks.md` 改，再 `apply` 续做。
- 全部 P0 完成后，跑一次端到端冒烟（建空间→选故障诊断域建任务→挂 MCP→对话→看审计），确认「能运行起来」。
- 详细命令流、环境准备、CLAUDE.md 全文见《灵枢_开发执行手册.md》。
