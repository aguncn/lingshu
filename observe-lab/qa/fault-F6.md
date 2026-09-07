# 前端发版引入 JS 报错（P2 · runbook）

> 本页与 observe-lab 的模拟数据**一一对应**：导入灵枢「知识库(RAG)」后，遇到同类告警可让 SRE 专家检索本页进行比对。
> 数据源头：`sim/incidents.py FAULTS['F6'] + RUNBOOKS['F6']`；模拟持续约 40 分钟。

## 影响面
- 受影响：ec-web（RUM：/ 与 /checkout）
- 时长：约 40 分钟

## 症状清单
- `ec_rum_error` JS runtime/resource 报错突增（TypeError null.map / chunk 404）
- `ec_rum_js_error_rate` 冲到 ~10%+
- 结算页 LCP 抬升、`ec_web_lcp_ms` 上升
- 服务端 5xx 并不高——问题在前端资源与缓存不一致

**一眼定位关键词（日志全文搜即可见）**：`app.7f3a.chunk.js`、`404`、`Uncaught (in promise)`、`Cannot read properties`

## 现场线索（审计/变更，解释“为什么会发生”）
- INFO `release-bot` `release` → ec-web distVersion=2.4.0-7f3a 灰度 100%（旧 index.html 仍引用 2.3.9 的 chunk 哈希）
- INFO `release-bot` `rollback` → 回滚至 distVersion 2.3.9，index.html 与 chunk 哈希一致，报错归零

**变更源头一句话**：变更源头：ec-web 灰度 distVersion=2.4.0-7f3a，但部分 index.html 仍引用 2.3.9 的 chunk 哈希 → 404 JS。

## 该查什么（可执行查询）
### 日志 SQL（stream 已是 observe-lab 实际的 ec_* 流）
```sql
select error_type, count(*) from "ec_rum_error" where _timestamp between <窗口起点> and <窗口终点> group by error_type
```
```sql
select route, count(*) from "ec_rum_error" group by route order by count(*) desc
```

窗口时间注意：O2 日志 `_timestamp` 是**微秒**；查询面板里选对时间范围即可，示例里的 `<窗口起点>/<窗口终点>` 指故障起止，一般把范围放大 10~20% 更稳。

### 指标（PromQL，metric 名/label 以 observe-lab 实际写入为准）
`ec_rum_js_error_rate`
`ec_rum_lcp_ms`

> 灌完数据先等 1~3 分钟让指标历史索引进度追上，PromQL/面板再查最稳；若面板偶发空白，点一下刷新即可。

### 链路（Traces）
- 该故障时段的链路里有 ERROR status span（`ec-order`/`ec-payment`/`ec-product` 等 `service_name` 以 `ec-` 开头），在 O2 Traces 页按 `service_name = ec-*` + 时间窗过滤查看瀑布图与错误段。

## 疑似根因
ec-web 灰度 v2.4.0-7f3a，但仍有用户命中引用旧 chunk 哈希的 index.html，加载 404 的 JS → 运行时异常。

## 处置步骤
1. 按 route/error_type 收敛报错
2. 核对 distVersion 与 index.html 引用
3. 回滚到 2.3.9 并清 CDN 缓存

## 让模型/人诊断的提问话术
1. 「帮我看看最近有没有下单/支付相关异常？」
2. 「把故障窗口的告警拉出来，按级别排个序。」
3. 「查 前端发版引入 JS 报错 相关日志和指标，给出根因和处置建议。」

期望链路：告警 → 按上方关键词收敛到 `ec_application_logs`/`ec_system_logs` → 拉对应 PromQL → 看到上述特征 → 命中本 runbook 根因 → 输出结论。
