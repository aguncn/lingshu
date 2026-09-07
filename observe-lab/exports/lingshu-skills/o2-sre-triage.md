# 技能：SRE 值班 · 拉取现场异常清单（o2-sre-triage）

> 适用：接到“看看有没有异常 / 拉一下现在的告警与错误”这类值班任务的第一步。
> 目标：用工具把“谁在什么时间段出了什么错”收敛成一张可继续追问的清单，而不是空谈。

## 前置
- 你的数据源是 OpenObserve MCP（挂载名以 `openobserve-ec` 为例，工具前缀 `mcp__openobserve-ec__…`；把其中的挂载名换成实际值）。
- 若无法确定 O2 暴露了哪些工具，先调 StreamList / tools/list 之类看有哪些可用（不同版本工具名可能不同）。

## 步骤
1. **锁窗口**：确定起止时间（默认最近 30~60 分钟，异常集中在故障窗口则扩到窗口前后）。
2. **优先用“告警类”工具**：如果 MCP 暴露 `ListAlerts / GetIncident / TriggerAlert` 一类工具，先列出近窗口的告警（按 severity/triggered 过滤）。
3. **兜底/交叉验证（很多自托管版没有可用的告警 CRUD，务必会走这条）**：不依赖告警接口，直接对现场反查：
   - 对 `ec_application_logs` 统计 `level='ERROR'` 按 `service` 分组取 TOP；
   - 网关层看 `ec_access_logs` 里 `status in (4xx,5xx)` 计数与 TOP path；
   - 前端看 `ec_rum_error` 是否突增；
   - 系统层看 `ec_system_logs` 的 WARN/ERROR。
4. **按流名 `ec_` 开头过滤**，忽略 fin/tel/rum_data 等旧数据（实验台只关心 `ec_*`）。
5. **产出清单**（每项）：时间窗 / 服务或流 / 现象（关键字或指标特征）/ 计数或幅度 / 建议下一查。

## 反例 vs 正例
- ✗ “看起来有 429，可能是网关问题。”（无窗口、无数据支撑）
- ✓ “最近 15 分钟 `ec_access_logs` 里 `status=429` 有 N 条、集中在 `/checkout`，`ec-http-*` 里 product 服务 error rate 同步抬升 → 疑似网关对下单链路限流。”（有时间、有工具结果、有关键字）

## 注意
- 时间范围要写在查询里/参数里；日志 `_timestamp` 是微秒、PromQL 起止用秒。
- 不要只列原始行不归纳；也不要在没查任何工具时就下结论。
- 字段名不确定先读 StreamSchema 或资料库 `02/03` 速查，别编造。
