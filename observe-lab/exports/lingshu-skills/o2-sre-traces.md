# 技能：用 O2 MCP 查链路 Traces（o2-sre-traces）

> 适用：从“整条调用”看失败发生在哪一跳（下单链路 gateway→order→MySQL/Redis…）。
> 目标：取出真实 span 树，定位第一个出错的 span / 超时点。

## 工具与前提
- OpenObserve MCP（挂载名以 `openobserve-ec` 为例）：`mcp__openobserve-ec__GetLatestTraces`（取最近链路）。
- **不能用 SQL 查 traces**（会报 Search stream not found，属正常）。链路数据在 O2 的 traces 流里，只能走 Traces 类工具/页面。
- 服务名：`service_name` 以 `ec-` 开头（ec-gateway/ec-order/ec-payment/ec-product/…）。

## 步骤
1. 锁定时间窗；用 `GetLatestTraces` 拉最近 N 条，或先按 `service_name=ec-<目标>` / trace_id 过滤。
2. 有具体 `trace_id` 时（来自日志/告警），直接按 trace_id 取那一条链路。
3. 阅读瀑布：
   - 找 **ERROR / timeout 的 span**（哪一跳、哪个 service、哪个操作：查 SQL/调 Redis/写 Kafka）；
   - 对比同一接口的正常与异常 trace，确认瓶颈/报错点与**首错**（首错通常才是根因，下游报错多为传导）。
4. 把链路证据与日志/指标串起来：日志同 `trace_id` 有对应 ERROR，指标（如 p99、db waiting）解释“为什么慢/失败”。

## 常见对应
- 下单慢/失败：看 gateway→ec-order 的 span，ec-order 里 `SELECT`/事务 span 超时 → 对齐 `ec_db_conn_pool_waiting`。
- 支付回调卡住：ec-payment 消费 Kafka 的 span 长时间 pending → 对齐 `ec_kafka_consumer_lag`。
- 全部超时但库里等待高：很可能是连接池耗尽排队（F1 类），不是单条 SQL 问题。

## 收尾
- 引用时带 trace_id / service_name / 出错 span 名与状态，结论可复核。
- 拉不到 traces：检查时间窗与过滤（service_name 是否 `ec-*`），说明工具/数据现实后不要编造瀑布。
