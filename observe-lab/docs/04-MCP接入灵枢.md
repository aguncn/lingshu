# 04 · MCP 接入灵枢：把 O2 变成模型手里的工具

让灵枢的模型**自己动手查** O2 的告警/日志/指标/链路，靠的是给任务挂一个「O2 MCP 连接器」。连接器里的工具对模型就是：查流结构、跑 SQL、PromQL 拉指标、取最新 traces 等。

灵枢 MCP 连接器只支持两种 transport：**`http`** 与 **`stdio`**。对自托管 O2 有两条路（**首选 http 原生 MCP**）：

| | 首选：http 原生 MCP | 兜底：stdio community MCP |
|---|---|---|
| 连什么 | O2 自带的 `/api/default/mcp`（v0.92.2 本实例实测可用） | `openobserve-community-mcp`（read-only，走普通 REST） |
| 好处 | 零额外进程；工具多（含告警/追踪/PromQL） | 老版本 O2 没有原生 MCP 时可用 |
| 前提 | O2 版本 >= 0.6.x 且开了原生 MCP | 机器上能跑 `uvx` |
| 工具 | `mcp__<挂载名>__StreamList / StreamSchema / SearchSQL / PrometheusRangeQuery / GetLatestTraces / …` | O2 REST 只读工具集 |
| 安全 | ⚠️ Community 版原生 MCP **全权限**（含删流/改配置），仅限本实验台 | read-only，更安全 |

> **安全提示**：自托管 OpenObserve Community 的 MCP 没有 RBAC 隔离，等于把 O2 管理权限交给了模型。做实验可以；**别对生产/含真实数据的实例这么挂**。

---

## 前置：拿到 Basic 凭据字符串

灵枢 http MCP 通过 `Authorization` 请求头把登录信息带给 O2。用你 `.env` 里的账号拼 base64（走项目自己的配置读取，保证和生成/自检同一套配置）：

```bash
uv run python -c "import base64;from o2 import config as c;s=c.settings();print('Basic '+base64.b64encode((s['OO_EMAIL']+':'+s['OO_PASSWORD']).encode()).decode())"
```

记下输出，形如 `Basic YWRtaW5AYWJjLmNvbTpSb290QDEyMzQ=`（本仓库示例凭据的编码值，仅供对照格式）。`exports/import_via_api.py` 也会自动现算，不需要手记。

---

## 首选：http 原生 MCP 连接器（推荐）

在灵枢「能力广场 → MCP 连接器中心」新建一个连接器，按下表填：

| 字段 | 填什么 |
|---|---|
| 名称 name | `openobserve-ec`（全局唯一，别与已有的 prometheus-mcp 等撞名） |
| transport | `http` |
| url | `http://localhost:5080/api/default/mcp`（org 不是 default 就把路径里换成你的 org） |
| headers | `{"Authorization": "Basic <上一步输出的串>"}`（服务端会 Fernet 加密落库，界面永远只显示键名） |
| enabled | ✅ 打开 |
| trust | ✅ 打开（**必须**：运行时 `is_mountable = enabled 且 trust`，trust 不开会被静默跳过） |

保存后点该连接器行的 **测试** —— 灵枢会做一次 `initialize` 握手并嗅探工具：

- `{"ok": true, "tools": ["..."]}` → 通了，工具名就是模型会看到的 `mcp__openobserve-ec__SearchSQL` 这类前缀。
- `{"ok": false, "reason": "..."}` → 按 reason 改（多为 base64 拼错、url/org 不对）。

> http 模式的「测试」只做握手+列工具，可能返回空 tools 数组也属正常（工具要真正挂到会话才全量列出）。以状态 ok 为准。

之后把它挂到任务的技能/能力挂载里（或在专家预设里带上，见 docs/05），**下一轮会话生效**（灵枢每次 `POST /chat` 重建 agent，改挂载后重启会话/发下一条即生效）。

---

## 兜底：stdio community MCP

老版本 O2 没有原生 MCP 端点时，改挂 `openobserve-community-mcp`（只读、走普通 REST，工具集更小但够用）：

| 字段 | 填什么 |
|---|---|
| 名称 name | `openobserve-community` |
| transport | `stdio` |
| command | `uvx`（Windows 需是 PATH 上的 `uvx.exe`；灵枢 stdio 无 shell，只找可执行） |
| args | `["--from", "openobserve-community-mcp", "openobserve-mcp"]` |
| env | `OO_BASE_URL=http://localhost:5080`、`OO_ORG=default`、`OO_AUTH_MODE=basic`、`OO_USERNAME=<你的邮箱>`、`OO_PASSWORD=<你的密码>`（整体 Fernet 加密入库，只显示键名） |
| enabled / trust | ✅ / ✅（同样两个都要） |

保存 → 测试 → 应看到 ok + 只读工具列表。

---

## 连接器在灵枢里的几种“生效”口径（写文档、排查用）

1. **能不能被挂载**：capability/专家挂载到任务时**只按 `enabled` 过滤**；但 agent 实际跑起来会跳过 `enabled 或 trust` 任一为假者。→ 调试时若模型“看不到 MCP 工具”，先查 trust 是不是 true。
2. **http vs stdio 挂载时机**：http MCP 立即挂进 toolkit；stdio MCP 延迟到会话驱动里 connect。首选用 http 也是这个原因——少一步。
3. **改挂载后何时生效**：每轮聊天都重建 agent，所以**发下一条消息**即可，无需重启灵枢。
4. **人设来源**：首个挂载的专家 persona_snapshot（`expert/apply` 时快照，之后改专家不影响已挂任务的既有会话）。
5. 验证最直观的路径：建一个任务套上该连接器 → 问“列出 O2 里 `ec_` 开头的流” → 模型应调用 `StreamList` 并返回 `ec_access_logs …` 那 6 个。

---

## 自动化（可选）：用 REST 直接建

不想在界面点，可以跑 `exports/import_via_api.py`（见 docs/05 / `exports/import-checklist.md`）。它内部就是 `POST /api/mcp` + `POST /api/mcp/<id>/test`。注意：**灵枢接口全开放、无鉴权、name 全局唯一、重名返回 400**——脚本与文档都会把“已存在”当成功跳过。

下一份：docs/05 讲技能 / 知识库(RAG) / 资料库 / SRE 专家的设计，以及它们怎么拼成一套“能自助诊断”的档案。
