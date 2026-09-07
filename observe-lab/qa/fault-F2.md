# Redis 热点键击穿 / 缓存雪崩（P1 · runbook）

> 本页与 observe-lab 的模拟数据**一一对应**：导入灵枢「知识库(RAG)」后，遇到同类告警可让 SRE 专家检索本页进行比对。
> 数据源头：`sim/incidents.py FAULTS['F2'] + RUNBOOKS['F2']`；模拟持续约 45 分钟。

## 影响面
- 受影响：ec-product / ec-inventory / ec-cart / Redis(ec-redis-cache) / MySQL
- 时长：约 45 分钟

## 症状清单
- 商品/库存接口 P99 上升(400–550ms)，但错误率不高
- `ec_redis_hit_ratio` 从 98% 跌到 ~45%
- `ec_db_conn_active`/mysql QPS 冲高(读放大)
- `ec_application_logs`: `cache MISS burst key=product:detail:...` / `cache stampede on SKU-778`

**一眼定位关键词（日志全文搜即可见）**：`cache MISS burst`、`cache stampede`、`maxmemory 90%`、`qps spike`、`evicting keys`、`read amplification`

## 现场线索（审计/变更，解释“为什么会发生”）
- INFO `marketing-ops` `campaign` → 商品 SKU-778 设为首页主推位，预热未做（无缓存预热任务）
- WARN `ops-console` `config` → set maxmemory-policy allkeys-lru on ec-redis-cache（此前为 noeviction）
- INFO `ops-console` `fix` → 热点 key 加逻辑过期+单飞重建，命中率恢复

**变更源头一句话**：变更源头：运营把 SKU-778 设为主推位但没预热；随后把 maxmemory-policy 改成 allkeys-lru → 命中率暴跌、整片回源。

## 该查什么（可执行查询）
### 日志 SQL（stream 已是 observe-lab 实际的 ec_* 流）
```sql
select service, count(*) from "ec_application_logs" where (message like '%stampede%' or message like '%MISS burst%') and _timestamp between <窗口起点> and <窗口终点> group by service
```

窗口时间注意：O2 日志 `_timestamp` 是**微秒**；查询面板里选对时间范围即可，示例里的 `<窗口起点>/<窗口终点>` 指故障起止，一般把范围放大 10~20% 更稳。

### 指标（PromQL，metric 名/label 以 observe-lab 实际写入为准）
`ec_redis_hit_ratio`
`ec_mysql_qps{component="ec-shop-db"}`
`ec_http_p99_ms{service="ec-product"}`
`ec_http_request_rate{service="ec-product"}`

> 灌完数据先等 1~3 分钟让指标历史索引进度追上，PromQL/面板再查最稳；若面板偶发空白，点一下刷新即可。

### 链路（Traces）
- 该故障时段的链路里有 ERROR status span（`ec-order`/`ec-payment`/`ec-product` 等 `service_name` 以 `ec-` 开头），在 O2 Traces 页按 `service_name = ec-*` + 时间窗过滤查看瀑布图与错误段。

## 疑似根因
大促主推造成单热点 key；促销侧清缓存 + maxmemory 策略改为 allkeys-lru 引发整片过期回源、DB 被击穿。

## 处置步骤
1. 查 Redis 命中率/memory
2. 热点 key 加逻辑过期 + 互斥重建
3. 补缓存预热

## 让模型/人诊断的提问话术
1. 「帮我看看最近有没有下单/支付相关异常？」
2. 「把故障窗口的告警拉出来，按级别排个序。」
3. 「查 Redis 热点键击穿 / 缓存雪崩 相关日志和指标，给出根因和处置建议。」

期望链路：告警 → 按上方关键词收敛到 `ec_application_logs`/`ec_system_logs` → 拉对应 PromQL → 看到上述特征 → 命中本 runbook 根因 → 输出结论。
