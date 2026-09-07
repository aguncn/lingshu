"""从 sim/incidents.py 的 RUNBOOKS（单一事实来源）生成 qa/fault-*.md 与 exports/lingshu-kb/*.md。

每个故障一页 runbook：症状、可执行的日志 SQL / PromQL、疑似根因、处置、诊断对话示例。
指标示例里给出的 PromQL 均以 sim/metrics.py 实际写入的 metric 名/label 为准（RUNBOOKS 里个别旧名会被这里修正）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim import incidents as inc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
QA = ROOT / "qa"
KB = ROOT / "exports" / "lingshu-kb"
QA.mkdir(exist_ok=True)
KB.mkdir(parents=True, exist_ok=True)

# 各故障实际会出现的、被系统日志采样/面板引用到的关键词（供人快速定位窗口）
KEYWORDS = {
    "F1": ["ER_LOCK_WAIT_TIMEOUT", "pool exhausted", "query too slow", "circuit OPEN",
           "PROCESSLIST: 31 threads", "InnoDB: lock waits rising", "connection leak detected"],
    "F2": ["cache MISS burst", "cache stampede", "maxmemory 90%", "qps spike", "evicting keys",
           "read amplification"],
    "F3": ["kafka consumer group payment-callback", "lag=", "max.poll.interval",
           "paid but state still pending", "消费积压"],
    "F4": ["rate limit exceeded", "connection refused", "marked down", "limiting requests", "429"],
    "F5": ["disk pressure", "91.8% used", "No space left on device", "SSL certificate expired",
           "certificate has expired", "log rotation", "backup job ec-db-backup failed"],
    "F6": ["app.7f3a.chunk.js", "404", "Uncaught (in promise)", "Cannot read properties"],
}

# 修正/验证过的 PromQL 示例：metric 名与 label 以 sim/metrics.py 为准
METRICS = {
    "F1": ["ec_db_conn_pool_active{component=\"ec-order-db\"}",
           "ec_db_conn_pool_waiting{component=\"ec-order-db\"}",
           "ec_http_error_rate{service=\"ec-order\"}",
           "ec_http_p99_ms{service=\"ec-order\"}"],
    "F2": ["ec_redis_hit_ratio", "ec_mysql_qps{component=\"ec-shop-db\"}",
           "ec_http_p99_ms{service=\"ec-product\"}",
           "ec_http_request_rate{service=\"ec-product\"}"],
    "F3": ["ec_kafka_consumer_lag", "ec_http_request_rate{service=\"ec-payment\"}",
           "ec_payment_confirm_pct"],
    "F4": ["ec_http_request_rate{service=\"ec-product\"}", "ec_http_error_rate{service=\"ec-product\"}"],
    "F5": ["ec_node_disk_pct{node=\"ec-node-2\"}", "ec_node_cpu_pct{node=\"ec-node-2\"}"],
    "F6": ["ec_rum_js_error_rate", "ec_rum_lcp_ms"],
}

# 故障源头变更线索（audit_msgs 里真正的“变更者”，帮助讲清根因链）
AUDIT_HINT = {
    "F1": "变更源头：有人对 orders 表执行 DDL 建索引(INPLACE)，期间配合一个每 2 分钟跑 COUNT(*) 全表扫描的报表任务 → 连接占满。",
    "F2": "变更源头：运营把 SKU-778 设为主推位但没预热；随后把 maxmemory-policy 改成 allkeys-lru → 命中率暴跌、整片回源。",
    "F3": "变更源头：ec-payment v2.3.1 在回调消费线程加了「远程库存一致性校验(3 次重试)」→ 单条耗时 4ms→42ms。",
    "F4": "变更源头：网关路由权重误配 100/0 且误启 orders_burst 限流 zone → 单实例被打满、健康检查剔除。",
    "F5": "变更源头：上个月停用了 /data/backups 清理 cron；证书续期 ACME 因磁盘满写不了文件连续失败。",
    "F6": "变更源头：ec-web 灰度 distVersion=2.4.0-7f3a，但部分 index.html 仍引用 2.3.9 的 chunk 哈希 → 404 JS。",
}


def _sql_window(s: str, s_h: str = "<窗口起点>", e_h: str = "<窗口终点>") -> str:
    # 把 SQL 里的 <s>/<e> 占位换成文档里人可读的窗口说明
    return s.replace("<s>", s_h).replace("<e>", e_h)


def _norm_sql(q: str) -> str:
    """ec_access_logs.status 是整数；RUNBOOKS 里的字符串字面量在这里归一成整数比较。"""
    q = q.replace("in ('504','500')", "in (504,500)")
    q = q.replace("status='429'", "status=429").replace("'429'", "429")
    return q


def build(fid: str) -> str:
    rb = inc.RUNBOOKS[fid]
    f = inc.FAULTS[fid]
    audit = "\n".join(f"- {lvl.upper()} `{actor}` `{action}` → {detail}"
                      for rel, lvl, actor, action, detail in f.audit_msgs)
    kw = "、".join(f"`{k}`" for k in KEYWORDS[fid])
    sqls = "\n".join(f"```sql\n{_sql_window(_norm_sql(q))}\n```" for q in rb["sql_queries"])
    mets = "\n".join(f"`{m}`" for m in METRICS[fid])
    syms = "\n".join(f"- {s}" for s in rb["symptoms"])
    steps = "\n".join(f"{i+1}. {s}" for i, s in enumerate(rb["next_steps"]))
    srcdoc = f"sim/incidents.py FAULTS['{fid}'] + RUNBOOKS['{fid}']"

    tpl = f"""# {rb['title']}（{rb['severity']} · runbook）

> 本页与 observe-lab 的模拟数据**一一对应**：导入灵枢「知识库(RAG)」后，遇到同类告警可让 SRE 专家检索本页进行比对。
> 数据源头：`{srcdoc}`；模拟持续约 {rb['duration_min']} 分钟。

## 影响面
- 受影响：{rb['affected']}
- 时长：约 {rb['duration_min']} 分钟

## 症状清单
{syms}

**一眼定位关键词（日志全文搜即可见）**：{kw}

## 现场线索（审计/变更，解释“为什么会发生”）
{audit}

**变更源头一句话**：{AUDIT_HINT[fid]}

## 该查什么（可执行查询）
### 日志 SQL（stream 已是 observe-lab 实际的 ec_* 流）
{sqls}

窗口时间注意：O2 日志 `_timestamp` 是**微秒**；查询面板里选对时间范围即可，示例里的 `<窗口起点>/<窗口终点>` 指故障起止，一般把范围放大 10~20% 更稳。

### 指标（PromQL，metric 名/label 以 observe-lab 实际写入为准）
{mets}

> 灌完数据先等 1~3 分钟让指标历史索引进度追上，PromQL/面板再查最稳；若面板偶发空白，点一下刷新即可。

### 链路（Traces）
- 该故障时段的链路里有 ERROR status span（`ec-order`/`ec-payment`/`ec-product` 等 `service_name` 以 `ec-` 开头），在 O2 Traces 页按 `service_name = ec-*` + 时间窗过滤查看瀑布图与错误段。

## 疑似根因
{rb['probable_root_cause']}

## 处置步骤
{steps}

## 让模型/人诊断的提问话术
1. 「帮我看看最近有没有下单/支付相关异常？」
2. 「把故障窗口的告警拉出来，按级别排个序。」
3. 「查 {rb['title']} 相关日志和指标，给出根因和处置建议。」

期望链路：告警 → 按上方关键词收敛到 `ec_application_logs`/`ec_system_logs` → 拉对应 PromQL → 看到上述特征 → 命中本 runbook 根因 → 输出结论。
"""
    return tpl


def main() -> None:
    for fid in inc.ORDER:
        text = build(fid)
        (QA / f"fault-{fid}.md").write_text(text, encoding="utf-8")
        (KB / f"fault-{fid}.md").write_text(text, encoding="utf-8")
        print(f"✓ qa/fault-{fid}.md + exports/lingshu-kb/fault-{fid}.md")


if __name__ == "__main__":
    main()
