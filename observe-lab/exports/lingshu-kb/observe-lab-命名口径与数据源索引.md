# observe-lab 命名口径与数据源索引（知识库索引件）

> 与 `qa/fault-F*.md` 一起供知识库(RAG)检索。本件解决“名字”问题：被问到数据在哪/怎么叫，先命中本件。
> 详细字段字典/全部 SQL·PromQL 在资料库 `lingshu-library/02..03`，诊断时可去引用。

## 数据都在哪
- 平台：自托管 **OpenObserve**（org=default，实验台）。
- **一切 `ec_`/`ec-` 前缀**，与旧数据(fin/tel/rum_data)隔离。
- 日志流：`ec_access_logs`(网关nginx) / `ec_application_logs`(应用) / `ec_system_logs`(节点/系统) / `ec_audit_logs`(变更审计，带 `fault_id`) / `ec_rum_pageview` / `ec_rum_error`(前端)。
- 指标：metric 即流名，一律 `ec_` 前缀；有 label `service`(除网关)、`component`(库：ec-order-db/ec-shop-db)、`node`(ec-node-1/2/3)、`redis`/`consumer`/`channel`。
- 链路：OTLP 落 `default` traces，`service_name=ec-*`，不能用 SQL 查，用 GetLatestTraces。

## 服务（9 个）
ec-gateway(nginx) · ec-order · ec-payment · ec-product · ec-search · ec-cart · ec-inventory · ec-user · ec-web(前端)
中间件：MySQL ec-order-db/ec-shop-db · Redis ec-redis-cache/ec-redis-session · Kafka ec-kafka-1。运行在 ec-node-1/2/3。

## 故障 → 信号 索引
| 关键词/现象 | 故障 | 主要信号位置 |
|---|---|---|
| 连接池耗尽/慢 SQL/锁等待 | F1 | `ec_application_logs`(order/payment) + `ec_db_conn_pool_active/waiting{component="ec-order-db"}` |
| 缓存击穿/雪崩/MISS | F2 | `ec_application_logs`(product) + `ec_redis_hit_ratio` + `ec_mysql_qps{component="ec-shop-db"}` |
| Kafka 积压/支付回调卡 | F3 | `ec_application_logs`(payment) + `ec_kafka_consumer_lag` + `ec_payment_confirm_pct` |
| 429/502/上游剔除 | F4 | `ec_access_logs`(status int) + `ec_http_error_rate{service="ec-product"}` |
| 磁盘/证书过期 | F5 | `ec_system_logs`(WARN/ERROR) + `ec_node_disk_pct{node="ec-node-2"}` |
| JS 报错/资源404/发版 | F6 | `ec_rum_error`(error_type/route) + `ec_rum_js_error_rate` |

## 每次诊断先记住
1. 时间窗先选对；日志 `_timestamp` 微秒、PromQL 起止用秒、指标灌完等 1~3 分钟。
2. `status` 是整数（别加引号）；流名用双引号、字符串用单引号。
3. 看变更源头去 `ec_audit_logs`（按 `fault_id` 或 `actor/action`）。
4. 不确定字段/流名 → StreamSchema / 查速查，不要编造。
