# 订单库连接池耗尽 / 慢 SQL（P1 · runbook）

> 本页与 observe-lab 的模拟数据**一一对应**：导入灵枢「知识库(RAG)」后，遇到同类告警可让 SRE 专家检索本页进行比对。
> 数据源头：`sim/incidents.py FAULTS['F1'] + RUNBOOKS['F1']`；模拟持续约 45 分钟。

## 影响面
- 受影响：ec-order / ec-payment / ec-gateway / MySQL(ec-order-db)
- 时长：约 45 分钟

## 症状清单
- 下单/支付接口大量 504、500（网关层 `upstream connect timeout`）
- `ec_http_p99_ms` 对 order/payment 冲高到 700–900ms
- `ec_db_conn_pool_active` 顶到 max=50 且 `ec_db_conn_pool_waiting>0`
- `ec_application_logs` 出现 `ER_LOCK_WAIT_TIMEOUT` / `pool exhausted` / `query too slow`

**一眼定位关键词（日志全文搜即可见）**：`ER_LOCK_WAIT_TIMEOUT`、`pool exhausted`、`query too slow`、`circuit OPEN`、`PROCESSLIST: 31 threads`、`InnoDB: lock waits rising`、`connection leak detected`

## 现场线索（审计/变更，解释“为什么会发生”）
- WARN `re-deployer` `ddl` → ALTER TABLE orders ADD INDEX idx_user_created (user_id, create_time), ALGORITHM=INPLACE target=ec-order-db
- ERROR `sqe-worker` `batch` → SELECT COUNT(*) FROM orders (full scan) from scheduled report job every 2min — 排查
- INFO `ops-console` `rollback` → 回收多余连接 / 关闭大促报表任务，连接池恢复

**变更源头一句话**：变更源头：有人对 orders 表执行 DDL 建索引(INPLACE)，期间配合一个每 2 分钟跑 COUNT(*) 全表扫描的报表任务 → 连接占满。

## 该查什么（可执行查询）
### 日志 SQL（stream 已是 observe-lab 实际的 ec_* 流）
```sql
select count(*) from "ec_application_logs" where service='ec-order' and level='ERROR' and _timestamp between <窗口起点> and <窗口终点>
```
```sql
select * from "ec_access_logs" where status in (504,500) and _timestamp between <窗口起点> and <窗口终点> order by _timestamp desc
```

窗口时间注意：O2 日志 `_timestamp` 是**微秒**；查询面板里选对时间范围即可，示例里的 `<窗口起点>/<窗口终点>` 指故障起止，一般把范围放大 10~20% 更稳。

### 指标（PromQL，metric 名/label 以 observe-lab 实际写入为准）
`ec_db_conn_pool_active{component="ec-order-db"}`
`ec_db_conn_pool_waiting{component="ec-order-db"}`
`ec_http_error_rate{service="ec-order"}`
`ec_http_p99_ms{service="ec-order"}`

> 灌完数据先等 1~3 分钟让指标历史索引进度追上，PromQL/面板再查最稳；若面板偶发空白，点一下刷新即可。

### 链路（Traces）
- 该故障时段的链路里有 ERROR status span（`ec-order`/`ec-payment`/`ec-product` 等 `service_name` 以 `ec-` 开头），在 O2 Traces 页按 `service_name = ec-*` + 时间窗过滤查看瀑布图与错误段。

## 疑似根因
订单表 DDL 后查询走全表扫描 + 报表任务长查询占用连接未释放，主库连接池耗尽、锁等待连锁放大。

## 处置步骤
1. 查 mysql 慢日志/连接数
2. EXPLAIN 订单查询计划
3. 关停大促报表任务、回收连接

## 让模型/人诊断的提问话术
1. 「帮我看看最近有没有下单/支付相关异常？」
2. 「把故障窗口的告警拉出来，按级别排个序。」
3. 「查 订单库连接池耗尽 / 慢 SQL 相关日志和指标，给出根因和处置建议。」

期望链路：告警 → 按上方关键词收敛到 `ec_application_logs`/`ec_system_logs` → 拉对应 PromQL → 看到上述特征 → 命中本 runbook 根因 → 输出结论。
