# 支付回调 Kafka 消费积压（P1 · runbook）

> 本页与 observe-lab 的模拟数据**一一对应**：导入灵枢「知识库(RAG)」后，遇到同类告警可让 SRE 专家检索本页进行比对。
> 数据源头：`sim/incidents.py FAULTS['F3'] + RUNBOOKS['F3']`；模拟持续约 50 分钟。

## 影响面
- 受影响：ec-payment / ec-order / Kafka(ec-kafka-1)
- 时长：约 50 分钟

## 症状清单
- 用户已支付但订单状态迟迟不更新（支付『确认』延后）
- `ec_kafka_consumer_lag` 单调爬升到几万~十几万
- `ec_application_logs`: `lag=...` / `paid but state still pending` / `max.poll.interval`
- 支付成功率口径异常：下单→支付成功，但 支付确认率 走低

**一眼定位关键词（日志全文搜即可见）**：`kafka consumer group payment-callback`、`lag=`、`max.poll.interval`、`paid but state still pending`、`消费积压`

## 现场线索（审计/变更，解释“为什么会发生”）
- INFO `release-bot` `deploy` → ec-payment v2.3.1：回调消费线程内新增『远程库存一致性校验』(含 3 次重试)
- INFO `ops-console` `rollback` → 回滚 ec-payment 至 v2.3.0，消费吞吐恢复 128 msg/s

**变更源头一句话**：变更源头：ec-payment v2.3.1 在回调消费线程加了「远程库存一致性校验(3 次重试)」→ 单条耗时 4ms→42ms。

## 该查什么（可执行查询）
### 日志 SQL（stream 已是 observe-lab 实际的 ec_* 流）
```sql
select * from "ec_application_logs" where message like '%lag=%' and _timestamp between <窗口起点> and <窗口终点> order by _timestamp desc
```

窗口时间注意：O2 日志 `_timestamp` 是**微秒**；查询面板里选对时间范围即可，示例里的 `<窗口起点>/<窗口终点>` 指故障起止，一般把范围放大 10~20% 更稳。

### 指标（PromQL，metric 名/label 以 observe-lab 实际写入为准）
`ec_kafka_consumer_lag`
`ec_http_request_rate{service="ec-payment"}`
`ec_payment_confirm_pct`

> 灌完数据先等 1~3 分钟让指标历史索引进度追上，PromQL/面板再查最稳；若面板偶发空白，点一下刷新即可。

### 链路（Traces）
- 该故障时段的链路里有 ERROR status span（`ec-order`/`ec-payment`/`ec-product` 等 `service_name` 以 `ec-` 开头），在 O2 Traces 页按 `service_name = ec-*` + 时间窗过滤查看瀑布图与错误段。

## 疑似根因
ec-payment v2.3.1 在消费线程里加了『远程库存一致性校验(3 次重试)』，单条消费耗时从 4ms 涨到 42ms，吞吐不足形成积压。

## 处置步骤
1. 看 lag 增速定积压量
2. 检查消费线程异常重试
3. 回滚 v2.3.1 或扩容消费者

## 让模型/人诊断的提问话术
1. 「帮我看看最近有没有下单/支付相关异常？」
2. 「把故障窗口的告警拉出来，按级别排个序。」
3. 「查 支付回调 Kafka 消费积压 相关日志和指标，给出根因和处置建议。」

期望链路：告警 → 按上方关键词收敛到 `ec_application_logs`/`ec_system_logs` → 拉对应 PromQL → 看到上述特征 → 命中本 runbook 根因 → 输出结论。
