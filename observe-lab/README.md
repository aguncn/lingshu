# observe-lab · 为灵枢搭一个「OpenObserve 模拟可观测实验台」

把一台自托管 **OpenObserve**（本文档按 `localhost:5080` 为例）变成一家**电商·在线交易企业**的线上观测环境，
里面灌入可指定时间范围的：**日志 / 指标 / 追踪 / RUM / 仪表盘 / 告警**，并模拟 **6 条真实故障**（F1–F6）。
数据全部经由 O2 **真实 API/OTLP 写入**，不是摆拍文件——在 O2 里都能点开、能 SQL / PromQL 查询、能触发告警。

配套还交付给 **灵枢平台**：MCP 连接配置、SRE 值班专家、技能、知识库(RAG)、资料库，以及一份实践指导，
让灵枢模型可以真的拿着 O2 的观测数据 + 告警做**模拟故障智能诊断**。

> 只做实验台，**不修改** 灵枢 backend/frontend/openspec 的任何产品代码。

---

## 5 步走

| 步骤 | 做什么 | 文档 |
|---|---|---|
| 0 | 填好 OpenObserve 登录信息 | [docs/01-环境与凭据.md](docs/01-环境与凭据.md) |
| 1 | 自检探活：逐项确认当前 O2 支持什么 | `uv run python selftest.py` |
| 2 | 生成模拟数据（可指定时间范围/故障） | [docs/02-数据生成与核对.md](docs/02-数据生成与核对.md) |
| 3 | 在 O2 各页核对（日志/指标/追踪/RUM/仪表盘/告警） | [docs/02] + [docs/03-故障剧本与告警.md](docs/03-故障剧本与告警.md) |
| 4 | 接入灵枢：MCP + 技能 + 知识库 + 资料库 + SRE 专家 | [docs/04-MCP接入灵枢.md](docs/04-MCP接入灵枢.md) · [docs/05-技能·知识库·资料库·专家设计.md](docs/05-技能·知识库·资料库·专家设计.md) |
| 5 | 让灵枢做一轮「模拟故障智能诊断」 | [docs/06-模拟故障智能诊断实战.md](docs/06-模拟故障智能诊断实战.md) |

最快路径：**填 .env → selftest → `python sim/main.py --hours 3`（最近 3 小时可直接灌，无需改 O2）→ 开 O2 看 F1 告警/仪表盘 → 按 docs/06 提问。**

---

## 目录

```
observe-lab/
  README.md / .env.example / pyproject.toml / uv.lock
  .env                    # 你的 O2 连接配置（勿提交；含明文账号）
  selftest.py             # 自检：鉴权 + 逐项探活能力 → .cache/capabilities.json
  o2/                     # O2 HTTP/OTLP 客户端封装（client / otlp / config）
  sim/                    # 电商模拟器（topology/rng/logs/metrics/traces/rum/incidents/flow/main）
  tools/
    make_dashboards.py    # 生成 dashboards/*.json（O2 v0.92 真实 v8 schema）
    make_qa_docs.py       # 从 sim/incidents.py 生成 qa/ + exports/lingshu-kb 的故障 runbook
  dashboards/*.json       # 4 张电商仪表盘（API 直建 / UI 导入两用）
  alerts/*.json           # F1..F6 告警规则定义（UI 手工建 fill-form + 目标 SQL）
  qa/fault-F1..F6.md      # 每条故障的 runbook（症状/查询/根因/处置）
  docs/00..06             # 实践指导
  exports/                # 导入灵枢的一整套配置与资料
    lingshu-mcp.json / lingshu-expert-sre.json / import-checklist.md / import_via_api.py
    lingshu-skills/*.md   # 5 条 o2-sre 技能：拉现场/查日志SQL/查PromQL/查链路/写诊断报告
    lingshu-kb/*.md       # 供知识库(RAG)：fault-F1..F6 runbook + 命名口径与数据源索引
    lingshu-library/*.md  # 供资料库：环境说明 + O2 SQL 字段字典 + PromQL/label 速查
```

## 命名约定（贯穿生成/仪表盘/告警/文档/灵枢接入）

- 业务蓝本：**电商在线交易**。为不污染你 O2 里已有的旧数据，observe-lab 的一切都落在 **`ec_` 命名空间**：
  - 日志流：`ec_access_logs / ec_application_logs / ec_system_logs / ec_audit_logs / ec_rum_pageview / ec_rum_error`
  - 指标：OTLP metric family 名一律 `ec_` 前缀（`ec_http_request_rate`、`ec_db_conn_pool_waiting`、`ec_redis_hit_ratio`、`ec_kafka_consumer_lag`、`ec_node_disk_pct` …）
  - 链路：服务名 `ec-gateway / ec-order / ec-payment / ec-product / ec-search / ec-cart / ec-inventory / ec-user / ec-web`
  - 仪表盘标题、告警规则名都以 `E-commerce` / `ec-` 标识
- **旧数据（fin/tel/rum_data 等）一律不动**。清场命令 `--purge-own` 只删 `ec_*` 自己的流（仪表盘保留、按同名自动更新），且能自动扛过 O2 删流异步窗口。日志流删流要先等 O2 后台清完底层文件（大流需数十分钟）才放行，期间同名报 `is being deleted`；**演示/上课想秒级出数就别用 `--purge-own`，直接重跑普通命令（不删流）即可**。
- 版本相关事实以 `selftest.py` 探测结果为准（你装的 O2 版本不同，个别能力会有差异），已内置兜底。
