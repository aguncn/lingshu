# 网关误限流 + 上游单实例剔除（P1 · runbook）

> 本页与 observe-lab 的模拟数据**一一对应**：导入灵枢「知识库(RAG)」后，遇到同类告警可让 SRE 专家检索本页进行比对。
> 数据源头：`sim/incidents.py FAULTS['F4'] + RUNBOOKS['F4']`；模拟持续约 40 分钟。

## 影响面
- 受影响：ec-gateway / ec-product / ec-order
- 时长：约 40 分钟

## 症状清单
- 结算/下单接口 429 陡增，紧接 502/503
- 错误集中在 ec-product 单实例（另一实例被健康检查剔除）
- `ec_access_logs` 出现大量 429 与 `upstream ... connection refused`
- 网关日志 `rate limit exceeded zone=orders_burst`

**一眼定位关键词（日志全文搜即可见）**：`rate limit exceeded`、`connection refused`、`marked down`、`limiting requests`、`429`

## 现场线索（审计/变更，解释“为什么会发生”）
- WARN `ops-console` `config` → gateway route: 误把 product_weight 配成 100/0，并启用 orders_burst 限流 zone(rate 100r/s burst 200)
- ERROR `ops-console` `config` → route 保存失败? 状态码 422——上游 ec-product-2 被摘除
- INFO `ops-console` `rollback` → 恢复 product_weight 50/50，移除 orders_burst，流量回升

**变更源头一句话**：变更源头：网关路由权重误配 100/0 且误启 orders_burst 限流 zone → 单实例被打满、健康检查剔除。

## 该查什么（可执行查询）
### 日志 SQL（stream 已是 observe-lab 实际的 ec_* 流）
```sql
select status, count(*) from "ec_access_logs" where _timestamp between <窗口起点> and <窗口终点> group by status order by count(*) desc
```
```sql
select * from "ec_access_logs" where status=429 and _timestamp between <窗口起点> and <窗口终点> order by _timestamp desc limit 50
```

窗口时间注意：O2 日志 `_timestamp` 是**微秒**；查询面板里选对时间范围即可，示例里的 `<窗口起点>/<窗口终点>` 指故障起止，一般把范围放大 10~20% 更稳。

### 指标（PromQL，metric 名/label 以 observe-lab 实际写入为准）
`ec_http_request_rate{service="ec-product"}`
`ec_http_error_rate{service="ec-product"}`

> 灌完数据先等 1~3 分钟让指标历史索引进度追上，PromQL/面板再查最稳；若面板偶发空白，点一下刷新即可。

### 链路（Traces）
- 该故障时段的链路里有 ERROR status span（`ec-order`/`ec-payment`/`ec-product` 等 `service_name` 以 `ec-` 开头），在 O2 Traces 页按 `service_name = ec-*` + 时间窗过滤查看瀑布图与错误段。

## 疑似根因
发版路由权重误配为 100/0 + 误开 orders_burst 限流 zone，单实例被打满、被摘除后雪崩到限流。

## 处置步骤
1. 恢复网关路由权重 50/50
2. 检查健康检查/摘除记录
3. 观察 429/5xx 回落

## 让模型/人诊断的提问话术
1. 「帮我看看最近有没有下单/支付相关异常？」
2. 「把故障窗口的告警拉出来，按级别排个序。」
3. 「查 网关误限流 + 上游单实例剔除 相关日志和指标，给出根因和处置建议。」

期望链路：告警 → 按上方关键词收敛到 `ec_application_logs`/`ec_system_logs` → 拉对应 PromQL → 看到上述特征 → 命中本 runbook 根因 → 输出结论。
