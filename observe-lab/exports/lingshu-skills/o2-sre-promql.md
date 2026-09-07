# 技能：用 O2 MCP 查指标 PromQL（o2-sre-promql）

> 适用：需要看曲线趋势/量化影响面（连接池、命中率、Kafka lag、P99、节点磁盘、前端体验指标）。
> 目标：用对 family 与 label，读出“异常形状”并据此判断根因方向。

## 工具
- OpenObserve MCP（挂载名以 `openobserve-ec` 为例）：`mcp__openobserve-ec__PrometheusRangeQuery`（区间查）。按工具签名给 start/end/step/query。
- 时间起止**用秒**（与日志 SQL 的微秒不同！）。
- 指标名即流名，一律 `ec_` 前缀；全 gauge，直接读值。

## 记住这 6 条“故障→指标”捷径
| 怀疑 | 首选 PromQL | 佐证 |
|---|---|---|
| 连接池/慢SQL | `ec_db_conn_pool_active{component="ec-order-db"}`、`ec_db_conn_pool_waiting{component="ec-order-db"}` | `ec_http_p99_ms{service="ec-order"}`、`ec_http_error_rate{service="ec-order"}` |
| 缓存击穿 | `ec_redis_hit_ratio`（0..1，×100 看%） | `ec_mysql_qps{component="ec-shop-db"}` 冲高 |
| Kafka 积压 | `ec_kafka_consumer_lag` | `ec_payment_confirm_pct` 下滑 |
| 网关/上游异常 | `ec_http_error_rate{service="ec-product"}` | 网关 429/502 明细去 `ec_access_logs`（网关自身不出 HTTP 指标） |
| 磁盘/证书 | `ec_node_disk_pct{node="ec-node-2"}` | `ec_node_cpu_pct`/`ec_node_mem_pct` |
| 前端发版 | `ec_rum_js_error_rate` | `ec_rum_lcp_ms`、配合 `ec_rum_error` 日志 |

常用 label：`service`(除 ec-gateway 外的 8 个)、`component`(ec-order-db/ec-shop-db)、`node`(ec-node-1/2/3)、`page`(/)。

## 写法与阅读
- 读“形状”而非单点：是否该窗口前正常、故障期突变/爬升、事后回落。配合时间窗判断起止。
- 例：F1 应看到 active≈max 平台期 + waiting>0；F3 应看到 lag 单调爬升；F5 应看到 disk 逼近 100%。
- 空结果处理：**指标灌完要等 1~3 分钟**；把查询范围放大/切更宽 step 再刷一次；仍空则如实说明，不硬编一个数字。

## 收尾
- 结论必须带具体值/趋势，如“ec_db_conn_pool_waiting 从 0 升到 8、active 顶到 50/50”，让人能复核。
