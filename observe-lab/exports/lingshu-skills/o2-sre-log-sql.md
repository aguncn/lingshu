# 技能：用 O2 MCP 查日志 SQL（o2-sre-log-sql）

> 适用：需要从日志里取证（错误关键字、慢请求、审计变更、RUM 报错）。
> 目标：写对、跑通、能引用——字段与流名都对得上，绝不编造。

## 工具
- OpenObserve MCP（挂载名以 `openobserve-ec` 为例）：`mcp__openobserve-ec__SearchSQL`（跑 SQL）、`…__StreamSchema`（看字段）、`…__StreamList`（看有哪些流）。
- 拿不准字段就先 StreamSchema / StreamList，再写 SQL。

## 写 SQL 的铁律（每条都别破）
1. **只查 `ec_` 流**：`"ec_access_logs" "ec_application_logs" "ec_system_logs" "ec_audit_logs" "ec_rum_pageview" "ec_rum_error"`。流名用**双引号**。
2. **`status` 是整数**：`status in (429,502,503)`，别加引号，否则查不到。
3. 全文搜索用 `message like '%关键字%'` 收敛，别用等值猜整句。
4. `_timestamp` 微秒、由面板/参数给时间窗；SQL 里不写绝对时间常量。
5. 取数限制：习惯性加 `limit N`，避免整流扫。

## 常用配方
```sql
-- 错误 TOP（值班入口）
select service, level, count(*) c from "ec_application_logs"
where level='ERROR' group by service, level order by c desc limit 20

-- 关键字取证（F1 示例）
select _timestamp, service, host, message
from "ec_application_logs"
where service in ('ec-order','ec-payment') and level='ERROR'
  and (message like '%pool exhausted%' or message like '%ER_LOCK_WAIT_TIMEOUT%')
order by _timestamp desc limit 100

-- 网关异常码+慢请求（F4）
select status, count(*) c from "ec_access_logs"
where status in (429,502,503) and (path like '%checkout%' or path like '%orders%')
group by status

-- 审计找变更源头
select _timestamp, actor, action, result, detail
from "ec_audit_logs" where fault_id='F3' order by _timestamp desc limit 50

-- 前端报错（F6）
select error_type, route, count(*) c from "ec_rum_error"
group by error_type, route order by c desc limit 20
```

## 收尾
- 引用结论时必须带“哪条 SQL / 哪个关键字 / 命中多少条”，让结论可复核。
- 若窗口内没查到，把时间窗放大 10~20% 再查一次（异步/边界），仍空就明说“该窗口无此信号”。
