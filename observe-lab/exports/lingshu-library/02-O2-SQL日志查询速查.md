# O2 日志 SQL 查询速查（资料库参考件 02）

写 O2 SQL 前先读本件，避免编造流名/字段名。数据全在 `ec_` 命名空间。
日志以 JSON 行写入，O2 自动建流；SQL 里**流名用双引号**、字符串用单引号。时间范围由查询面板/调用方给，不写在 SQL 里（`_timestamp` 是微秒整数）。

## 六个日志流的字段字典

### 1) `"ec_access_logs"` — 网关 nginx 访问日志
`service`(=ec-gateway) · `host` · `upstream`(后端服务名) · `method` · `path` · `status`(**整数**) · `remote_addr` · `region` · `request_time_ms` · `upstream_time_ms` · `body_bytes` · `user_agent` · `referer` · `level`
- `level`：正常 INFO；4xx→WARN、5xx→ERROR。

### 2) `"ec_application_logs"` — 应用服务日志
`service`(ec-order/ec-payment/…) · `host` · `level` · `logger`(`com.ec.<svc>.*`) · `message` · `trace_id`(约一半行有)
- 慢查询、连接池、缓存雪崩等故障关键字都出现在 `message`。

### 3) `"ec_system_logs"` — 基础设施/节点日志
`service`(system|node-exporter|kubelet/system) · `host`(ec-node-N) · `level` · `logger` · `message` · `namespace`
- 磁盘/证书故障：`logger=ops` 的 WARN/ERROR 行；`node-exporter` 的 INFO 行带 `disk_pct=` 巡检值。

### 4) `"ec_audit_logs"` — 变更/操作审计（解释“为什么会发生”）
`service`(=audit) · `host`(=ec-ops-1) · `level` · `logger`(=audit) · `actor` · `action` · `detail` · `result`(ok/denied/fail) · `namespace` · `fault_id`(F1..F6，故障相关) · `message`
- 查某故障的变更源头：按时间窗 + `fault_id='F4'` 或按 `actor/action` 过滤。

### 5) `"ec_rum_pageview"` — 前端页面浏览（体验）
`service`(=ec-web) · `route`(/、/products/38412、/cart、/checkout、/orders…) · `page` · `lcp_ms` · `cls` · `inp_ms` · `ttfb_ms` · `dist_version`(发版标识) · `session_id` · `browser` · `os` · `device` · `country`/`city` · `domain` · `message`

### 6) `"ec_rum_error"` — 前端 JS/资源报错（仅错误事件）
`service`(=ec-web) · `level`(=ERROR) · `route`/`page` · `error_type`(runtime|resource|promise|typeerror) · `filename`(/static/js/*.js) · `lineno` · `stack_sample` · `message` · `dist_version` · `browser` · `session_id`

## 常用查询模板

```sql
-- 按服务看最近错误 TOP（诊断入口）
select service, level, count(*) c
from "ec_application_logs"
where level='ERROR' group by service, level order by c desc

-- 关键字收敛（F1：连接池/慢 SQL）
select _timestamp, service, message
from "ec_application_logs"
where service in ('ec-order','ec-payment') and level='ERROR'
  and (message like '%pool exhausted%' or message like '%ER_LOCK_WAIT_TIMEOUT%'
       or message like '%query too slow%' or message like '%circuit OPEN%')
order by _timestamp desc

-- 网关异常码（F4；status 是整数，别加引号）
select status, count(*) c from "ec_access_logs"
where (status in (429,502,503))
  and (path like '%checkout%' or path like '%orders%')
group by status order by c desc

-- 慢访问 TOP（网关视角）
select path, status, request_time_ms, upstream, message
from "ec_access_logs" where request_time_ms > 3000 order by request_time_ms desc limit 50

-- 基础设施异常（F5 磁盘/证书）
select host, logger, message from "ec_system_logs"
where level in ('WARN','ERROR')
  and (message like '%disk%' or message like '%No space left%' or message like '%certificate%')

-- 前端报错按类型/路由收敛（F6）
select error_type, route, count(*) c from "ec_rum_error"
group by error_type, route order by c desc

-- 变更审计找源头（结合 fault_id）
select _timestamp, actor, action, result, detail
from "ec_audit_logs" where fault_id='F3' order by _timestamp
```

## 容易踩的坑
1. `status` 是**整数**：`status=429` 或 `status in (429,502,503)`；加引号 `'429'` 查不到。
2. 全文搜索关键字与 `_timestamp` 分选：先选对时间窗（面板/参数），关键字在 `like '%…%'` 里。
3. `message` 里中文/长日志：用关键字定位而不是整句等值。
4. 想联查链路：从日志取 `trace_id` → Traces 页 / GetLatestTraces 按 trace_id 或 `service_name=ec-*` 过滤（见 03/04）。
5. `%`/`_` 是通配符，想查字面量需转义——演示数据基本用不到。

## 结论
**先确定窗口 → 锁 `ec_` 流 → 用 `message like '%关键字%'` 收敛 → 对字段字典取名。**
指标/PromQL 部分见 `03-O2-PromQL指标查询速查.md`。
