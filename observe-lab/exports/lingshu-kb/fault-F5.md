# 节点磁盘 90% + 外呼证书过期（P2 · runbook）

> 本页与 observe-lab 的模拟数据**一一对应**：导入灵枢「知识库(RAG)」后，遇到同类告警可让 SRE 专家检索本页进行比对。
> 数据源头：`sim/incidents.py FAULTS['F5'] + RUNBOOKS['F5']`；模拟持续约 50 分钟。

## 影响面
- 受影响：ec-node-2 / ec-web / ec-payment（外呼 HTTPS）
- 时长：约 50 分钟

## 症状清单
- `ec_node_disk_pct` 顶到 91–94%
- 外呼 webhook 502/SSL 证书错误（`SSL certificate expired`）
- 备份任务失败：`No space left on device`
- 日志轮转被跳过，journald 因磁盘压力丢消息

**一眼定位关键词（日志全文搜即可见）**：`disk pressure`、`91.8% used`、`No space left on device`、`SSL certificate expired`、`certificate has expired`、`log rotation`、`backup job ec-db-backup failed`

## 现场线索（审计/变更，解释“为什么会发生”）
- WARN `ops-console` `cron` → 定时清理 /data/backups 未执行（cron 被上月变更停用）
- INFO `cert-bot` `renew` → 证书续期任务尝试 *.example.com 失败: ACME http-01 无法写文件(磁盘满)
- INFO `ops-console` `fix` → 清理 60G 旧备份 + 重启 cert-bot，磁盘 54%，证书已续

**变更源头一句话**：变更源头：上个月停用了 /data/backups 清理 cron；证书续期 ACME 因磁盘满写不了文件连续失败。

## 该查什么（可执行查询）
### 日志 SQL（stream 已是 observe-lab 实际的 ec_* 流）
```sql
select * from "ec_system_logs" where host='ec-node-2' and _timestamp between <窗口起点> and <窗口终点> order by _timestamp desc
```

窗口时间注意：O2 日志 `_timestamp` 是**微秒**；查询面板里选对时间范围即可，示例里的 `<窗口起点>/<窗口终点>` 指故障起止，一般把范围放大 10~20% 更稳。

### 指标（PromQL，metric 名/label 以 observe-lab 实际写入为准）
`ec_node_disk_pct{node="ec-node-2"}`
`ec_node_cpu_pct{node="ec-node-2"}`

> 灌完数据先等 1~3 分钟让指标历史索引进度追上，PromQL/面板再查最稳；若面板偶发空白，点一下刷新即可。

### 链路（Traces）
- 该故障时段的链路里有 ERROR status span（`ec-order`/`ec-payment`/`ec-product` 等 `service_name` 以 `ec-` 开头），在 O2 Traces 页按 `service_name = ec-*` + 时间窗过滤查看瀑布图与错误段。

## 疑似根因
清理 cron 被停用 + 日志轮转失败 → 磁盘 92%；证书续期 ACME 因写不了文件连续失败，外呼 HTTPS 报证书过期。

## 处置步骤
1. 清理 /data/backups 旧备份
2. 重启 cert-bot 续期
3. 恢复日志轮转 cron

## 让模型/人诊断的提问话术
1. 「帮我看看最近有没有下单/支付相关异常？」
2. 「把故障窗口的告警拉出来，按级别排个序。」
3. 「查 节点磁盘 90% + 外呼证书过期 相关日志和指标，给出根因和处置建议。」

期望链路：告警 → 按上方关键词收敛到 `ec_application_logs`/`ec_system_logs` → 拉对应 PromQL → 看到上述特征 → 命中本 runbook 根因 → 输出结论。
