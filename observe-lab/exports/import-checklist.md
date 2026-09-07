# 把 observe-lab 导入灵枢 · 手工核对单（主通道）

> 顺序即依赖顺序（专家预设要引用前几类建好的 id）。每类都是「**在能力广场对应中心新建/上传 + 勾选**」。
> 界面入口/按钮名以你当前灵枢前端为准，下面是通用说法；拿不准哪一步对应哪个 Center，就对着右侧的 REST 路由找。
> 撞名（`name 已存在`）一律当作“已经有了”，跳过即可。想一键自动化可跑 `uv run python exports/import_via_api.py`。

前置：灵枢 backend 起着（`uv run flask --app backend.app run --port 5000`），前端可访问能力广场。

---

## ① 技能（5 条）— `POST /api/skills`
在「技能」中心逐个新建，**名称**用文件名（去 `.md`），**说明/描述**抄文件首行，**SKILL.md 正文**整篇粘贴：

| 名称 | 用途 |
|---|---|
| `o2-sre-triage` | SRE 值班·拉现场异常清单（入口） |
| `o2-sre-log-sql` | 用 MCP SearchSQL 查 ec_* 日志的正确姿势 |
| `o2-sre-promql` | 用 MCP 查指标 PromQL（含故障→指标捷径） |
| `o2-sre-traces` | 用 MCP 查链路 Traces |
| `o2-sre-report` | 诊断收敛→根因→处置→报告模板 |

文件在 `exports/lingshu-skills/`。5 条都勾 **enabled**。

## ② MCP 连接器 — `POST /api/mcp`
「MCP」中心新建一个 **http** 连接器（推荐只建这个；stdio 兜底可选）：

- 名称 `openobserve-ec`、transport **http**、url `http://localhost:5080/api/default/mcp`
- **请求头 headers**：`{"Authorization": "Basic <BASE64>"}`，`<BASE64>` = `base64(你的O2邮箱:密码)`，命令见 `docs/04`。
- **enabled 与 trust 都打开**（runtime `is_mountable` 两个都要，缺 trust 会被静默跳过）。
- 保存 → 点该行「测试」，应为 ok（http 模式可能返回空 tools，属正常，看 ok）。
- 兜底 stdio（O2 老版本无原生 MCP 时）：名称 `openobserve-community`、transport stdio、command `uvx`、args `["--from","openobserve-community-mcp","openobserve-mcp"]`、env 填 `OO_BASE_URL/OO_ORG/OO_AUTH_MODE=basic/OO_USERNAME/OO_PASSWORD`（env/headers 会被加密落库，只显示键名）。

## ③ 知识库 RAG — `POST /api/kb` + `POST /api/kb/<id>/upload`
「知识库」中心新建一条 KB：名称 **`observe-lab-sre-kb`**（全局，无需挂空间），状态 **ready**，chunk 400。
然后**把 `exports/lingshu-kb/` 下全部 7 篇 .md 逐个上传**到这条 KB（一次传一个文件；同名重传会覆盖）：

| 文件 | 内容 |
|---|---|
| `fault-F1.md` … `fault-F6.md` | 6 条故障 runbook（症状/SQL/PromQL/根因/处置） |
| `observe-lab-命名口径与数据源索引.md` | 命名与数据源索引（供“这数据在哪儿/叫什么”检索） |

## ④ 资料库 — `POST /api/library`（multipart file）
「资料库」中心把 `exports/lingshu-library/` 下 **3 篇 .md 逐篇上传**（全局即可）：

| 文件 | 用途 |
|---|---|
| `01-模拟实验台环境说明.md` | 环境底稿：这是什么、ec_ 命名、6 故障、3 个版本事实 |
| `02-O2-SQL日志查询速查.md` | 6 个日志流字段字典 + SQL 模板 + 踩坑 |
| `03-O2-PromQL指标查询速查.md` | 全部 metric 族 + label + 故障→指标地图 |

资料库文件可让模型在会话里**引用原文**（防编造字段名）。

## ⑤ 专家 — `POST /api/experts`
「专家」中心新建「**SRE 值班专家·observe-lab**」，照 `exports/lingshu-expert-sre.json`：
- 角色 **ops-sme**；`system_prompt` 整段粘贴（档案里已写好）。
- **预设技能**：勾上面 5 条 o2-sre-*；**预设 MCP**：勾 `openobserve-ec`；
- **预设知识库**：勾 `observe-lab-sre-kb`；**预设资料库**：勾上传的 3 篇文件名。
- enabled 打开。

## ⑥ 建任务并应用专家（端到端冒烟）
1. 在「空间/任务」建一个任务（标题随意，如「电商下单异常诊断演示」；权限模式 strict 即可）。
2. 进任务 → 能力/专家挂载 → 应用专家 **SRE 值班专家·observe-lab**（或 REST `POST /api/tasks/<tid>/expert/apply {"expert_id": <专家id>}`）。
3. 应用后**发一条消息**触发下一轮重建 agent（挂载与模型生效以“下一条消息”为准）。
4. 冒烟提问：「列出 O2 里 ec_ 开头的日志流」→ 应看到模型经 MCP 调工具返回 6 个流名。

---

## 常见问题
- **专家预设勾不上/为空**：前置 id 没建好——按 ①→⑤ 顺序重来；或直接用 `import_via_api.py`（会自动按名接线）。
- **MCP 测试 ok:false**：多是 Basic 头/url/org 不对；`docs/04` 有生成命令。trust 忘开则运行时看不到工具。
- **知识库搜索没命中**：确认 KB 状态是 ready、文件已上传（每篇 upload 返回 chunk_count）；向量是关的，走关键词检索，问题里带“连接池/Kafka lag/429”这类词更准。
- **重复跑/撞名**：灵枢 name 全局唯一，`name 已存在` 返回 400 —— 当作已存在，人工核对预设即可。
