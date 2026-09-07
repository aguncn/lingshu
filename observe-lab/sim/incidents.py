"""故障目录：F1..F6 六个真实感剧本。

每个 Fault 描述：影响服务、时间窗(运行时由 main 指定)、对指标/日志/链路/前端体验的
叠加效果（用 ramp 波形把 0..1 的窗口进度映射到强度），以及症状消息模板。
文档/技能/知识库所需的 runbook 文案也集中在 RUNBOOKS（单一事实来源，docs 与 qa 从这里生成）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from . import topology as topo


def ramp(rel: float) -> float:
    """梯形波：0→峰(0.2)→平(0.8)→0。rel∈[0,1]。"""
    rel = max(0.0, min(1.0, rel))
    if rel < 0.2:
        return rel / 0.2
    if rel > 0.8:
        return (1.0 - rel) / 0.2
    return 1.0


# ---------------------------------------------------------------- 波形/进度
@dataclass
class Fault:
    id: str
    name: str
    severity: str          # P0/P1/P2
    services: set          # 受影响服务
    hosts: set             # 受影响主机(系统日志)
    profile: dict          # 各叠加效果的峰值
    app_msgs: list         # [(服务, level, message, weight)]
    sys_msgs: list         # [(host, level, message)]
    audit_msgs: list       # [(rel∈[0,1] 触发点, level, actor, action, detail)]
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    duration: timedelta = field(default=timedelta(minutes=45))

    # ---- 运行时由 main 设置窗口 ----
    def set_window(self, start: datetime, end: datetime):
        self.start = start
        self.end = end
        self.duration = end - start

    def rel_at(self, t: datetime) -> float:
        if not self.start or not self.end:
            return 0.0
        if t <= self.start:
            return 0.0
        if t >= self.end:
            return 0.0
        total = max(1, int((self.end - self.start).total_seconds()))
        return (t - self.start).total_seconds() / total

    def active_at(self, t: datetime) -> bool:
        return bool(self.start and self.end and self.start <= t < self.end)

    # ---- 各叠加项（调用方把 baseline 乘以 ramp 再叠加）----
    def intensity_at(self, t: datetime) -> float:
        return ramp(self.rel_at(t))

    def service_error_rate(self, svc: str, t: datetime) -> float:
        """返回该时刻对 svc 的额外错误率(0..1)。"""
        p = self.profile.get("svc_err") or {}
        return (p.get(svc) or 0.0) * self.intensity_at(t)

    def service_p99_ms(self, svc: str, t: datetime) -> Optional[float]:
        p = self.profile.get("svc_p99") or {}
        v = p.get(svc)
        return v * self.intensity_at(t) if v else None

    def status_bump(self, t: datetime) -> dict:
        """该时刻要额外把多少比例的请求变成某状态码 -> {svc:{code:frac}}"""
        out = {}
        p = self.profile.get("http_status") or {}
        a = self.intensity_at(t)
        for svc, codes in p.items():
            out[svc] = {code: frac * a for code, frac in codes.items()}
        return out

    def scalar(self, key: str, t: datetime) -> float:
        """通用数值型叠加（redis_hit_ratio / kafka_lag / rum_js_err ...）。"""
        v = self.profile.get(key)
        if v is None:
            return 0.0
        if isinstance(v, (int, float)):
            return v * self.intensity_at(t)
        # dict[node-or-svc] 形态
        return v

    def node_scalar(self, key: str, node: str, t: datetime) -> float:
        p = self.profile.get(key) or {}
        return (p.get(node) or 0.0) * self.intensity_at(t)

    def db(self, key: str, t: datetime) -> float:
        p = self.profile.get("db") or {}
        return (p.get(key) or 0.0) * self.intensity_at(t)

    # ---- 症状日志采样（logs 生成器每窗口分钟内调用）----
    def sample_app_msg(self, rng) -> Optional[tuple[str, str, str]]:
        """按权重抽一条 app 症状消息；返回 (service, level, message) 或 None。"""
        if not self.app_msgs:
            return None
        import random as _r
        total = sum(w for *_, w in self.app_msgs)
        r = _r.uniform(0, total)
        acc = 0.0
        for svc, lvl, msg, w in self.app_msgs:
            acc += w
            if r <= acc:
                return svc, lvl, msg
        return self.app_msgs[0][:3]

    def sample_sys_msg(self, rng) -> Optional[tuple[str, str, str]]:
        if not self.sys_msgs:
            return None
        return rng.choice(self.sys_msgs)


# ================================================================ 六条故障定义
# 消息里用 {host}/{svc} 占位，生成时替换成实际 host/svc。

F1 = Fault(
    id="F1",
    name="订单库连接池耗尽 / 慢 SQL",
    severity="P1",
    services={"ec-order", "ec-payment", "ec-gateway"},
    hosts={"ec-db-mysql-1"},
    profile={
        "svc_err": {"ec-order": 0.35, "ec-payment": 0.18},
        "svc_p99": {"ec-order": 820, "ec-payment": 620, "ec-gateway": 680},
        "http_status": {
            "ec-gateway": {"504": 0.22, "500": 0.08},
        },
        "db": {"active_frac": 1.0, "wait": 9.0, "qps_boost": 3.2, "slow_ratio": 0.6},
    },
    app_msgs=[
        ("ec-order", "ERROR", "db: connection pool exhausted max=50 active=50 wait=9 HikariPool-1", 2),
        ("ec-order", "ERROR", "query too slow: SELECT * FROM orders WHERE status='paid' AND create_time>? ORDER BY id (3.24s > slow=500ms)", 2),
        ("ec-payment", "ERROR", "ER_LOCK_WAIT_TIMEOUT: Lock wait timeout exceeded; try restarting transaction", 1),
        ("ec-order", "WARN", "SQL may use full table scan: EXPLAIN shows type=ALL on orders where user_id=88231", 1),
        ("ec-gateway", "WARN", "upstream connect timeout after 3000ms while POST /api/v1/orders", 1),
        ("ec-order", "WARN", "connection leak detected: statement not closed, active conns rising 46->50", 1),
    ],
    sys_msgs=[
        ("ec-db-mysql-1", "WARN", "PROCESSLIST: 31 threads in 'Sending data', longest query 11.8s on orders"),
        ("ec-db-mysql-1", "WARN", "InnoDB: lock waits rising, avg wait 2.1s, innodb_buffer_pool free < 5%"),
    ],
    audit_msgs=[
        (0.02, "WARN", "re-deployer", "ddl", "ALTER TABLE orders ADD INDEX idx_user_created (user_id, create_time), ALGORITHM=INPLACE target=ec-order-db"),
        (0.2, "ERROR", "sqe-worker", "batch", "SELECT COUNT(*) FROM orders (full scan) from scheduled report job every 2min — 排查"),
        (0.95, "INFO", "ops-console", "rollback", "回收多余连接 / 关闭大促报表任务，连接池恢复"),
    ],
)

F2 = Fault(
    id="F2",
    name="Redis 热点键击穿 / 缓存雪崩",
    severity="P1",
    services={"ec-product", "ec-inventory", "ec-cart"},
    hosts={"ec-db-redis-1", "ec-db-mysql-1"},
    profile={
        "svc_err": {"ec-product": 0.06, "ec-inventory": 0.04},
        "svc_p99": {"ec-product": 540, "ec-inventory": 470, "ec-cart": 390},
        "redis_hit_ratio": 42.0,          # 命中率跌到 ~42%
        "redis_mem_boost": 0.35,
        "db": {"qps_boost": 2.6},
    },
    app_msgs=[
        ("ec-product", "WARN", "cache MISS burst key=product:detail:38412 qps≈4300, 回源 DB 受互斥锁保护", 2),
        ("ec-inventory", "WARN", "cache stampede on SKU-778: 32 rebuilders waiting on distributed lock", 2),
        ("ec-product", "INFO", "cache rebuilt product:detail:38412 from db (took 180ms), TTL set 300s", 1),
        ("ec-cart", "WARN", "cart items reload from db due to cache eviction of session:cart:8812", 1),
        ("ec-product", "ERROR", "db read amplification: 900 qps on ec-shop-db from single hot key", 1),
    ],
    sys_msgs=[
        ("ec-db-redis-1", "WARN", "redis-server: maxmemory 90%, evicting keys (allkeys-lru), miss ratio climbing"),
        ("ec-db-mysql-1", "WARN", "MySQL: SELECT product ... qps spike ×2.6 from cache-miss fanout"),
    ],
    audit_msgs=[
        (0.03, "INFO", "marketing-ops", "campaign", "商品 SKU-778 设为首页主推位，预热未做（无缓存预热任务）"),
        (0.05, "WARN", "ops-console", "config", "set maxmemory-policy allkeys-lru on ec-redis-cache（此前为 noeviction）"),
        (0.9, "INFO", "ops-console", "fix", "热点 key 加逻辑过期+单飞重建，命中率恢复"),
    ],
)

F3 = Fault(
    id="F3",
    name="支付回调 Kafka 消费积压",
    severity="P1",
    services={"ec-payment", "ec-order"},
    hosts={"ec-kafka-1"},
    profile={
        "svc_p99": {"ec-payment": 300},
        "kafka_lag": 120_000,
        "http_status": {"ec-payment": {"200": 0.0}},   # 保留占位
    },
    app_msgs=[
        ("ec-payment", "WARN", "kafka consumer group payment-callback: lag=83210 on topic ec-payment-events-0", 2),
        ("ec-payment", "WARN", "order 88231 已支付但状态仍 pending，5s 后重投递 (attempt 7/10)", 2),
        ("ec-payment", "ERROR", "consumer batch process exceeded max.poll.interval.ms; rebalance in progress", 1),
        ("ec-payment", "INFO", "processing callback msg offset=3481209 ... remote 库存校验 重试, 单条耗时 42ms(基线 4ms)", 1),
        ("ec-order", "WARN", "支付确认延时: order 88231 paid_at=21:32:11 confirmed_at 未更新, 关联回调队列积压", 1),
    ],
    sys_msgs=[
        ("ec-kafka-1", "WARN", "kafka: consumer group payment-callback lag high on topic ec-payment-events partition 0"),
    ],
    audit_msgs=[
        (0.02, "INFO", "release-bot", "deploy", "ec-payment v2.3.1：回调消费线程内新增『远程库存一致性校验』(含 3 次重试)"),
        (0.97, "INFO", "ops-console", "rollback", "回滚 ec-payment 至 v2.3.0，消费吞吐恢复 128 msg/s"),
    ],
)

F4 = Fault(
    id="F4",
    name="网关误限流 + 上游单实例剔除",
    severity="P1",
    services={"ec-gateway", "ec-product", "ec-order"},
    hosts={"ec-node-1"},
    profile={
        "svc_err": {"ec-product": 0.12},
        "svc_p99": {"ec-gateway": 480},
        "http_status": {
            "ec-gateway": {"429": 0.19, "502": 0.09, "503": 0.05},
        },
    },
    app_msgs=[
        ("ec-gateway", "WARN", "rate limit exceeded zone=orders_burst burst=200 rate=100r/s exceeded_key=10.1.4.12", 2),
        ("ec-gateway", "ERROR", "upstream http://10.1.8.12:8080 failed: connection refused (ec-product-2)", 2),
        ("ec-gateway", "WARN", "healthcheck ec-product-2 marked down after 3 consecutive failures", 1),
        ("ec-order", "ERROR", "POST /api/v1/orders -> 429 from gateway retry budget exhausted", 1),
        ("ec-product", "WARN", "no healthy upstream instance, 502s to checkout service", 1),
    ],
    sys_msgs=[
        ("ec-node-1", "WARN", "nginx: [warn] limiting requests, excess: 18.22 req/s by zone orders_burst"),
    ],
    audit_msgs=[
        (0.02, "WARN", "ops-console", "config", "gateway route: 误把 product_weight 配成 100/0，并启用 orders_burst 限流 zone(rate 100r/s burst 200)"),
        (0.04, "ERROR", "ops-console", "config", "route 保存失败? 状态码 422——上游 ec-product-2 被摘除"),
        (0.92, "INFO", "ops-console", "rollback", "恢复 product_weight 50/50，移除 orders_burst，流量回升"),
    ],
)

F5 = Fault(
    id="F5",
    name="节点磁盘 90% + 外呼证书过期",
    severity="P2",
    services={"ec-web", "ec-payment"},
    hosts={"ec-node-2"},
    profile={
        "svc_err": {"ec-web": 0.10},
        "http_status": {"ec-gateway": {"502": 0.06}},
        "node_disk": {"ec-node-2": 92.0},
        "svc_p99": {"ec-web": 150},
    },
    app_msgs=[
        ("ec-web", "ERROR", "push/webhook https://notify.example.com/api/send failed: SSL certificate expired (verify failed)", 2),
        ("ec-payment", "ERROR", "callback POST https://pay-cb.example.com/notify failed: certificate has expired or is not yet valid", 1),
        ("ec-web", "WARN", "disk pressure: /data 91% used, log rotation skipped (max 200MB reached)", 2),
        ("ec-payment", "WARN", "outbound HTTPS cert for *.example.com expires in 1 day — 未自动续期", 1),
    ],
    sys_msgs=[
        ("ec-node-2", "WARN", "df /: 91.8% used 183.6G/200G on /dev/vda1"),
        ("ec-node-2", "ERROR", "backup job ec-db-backup failed: No space left on device (/data/backups/mysql)"),
        ("ec-node-2", "WARN", "journald: log rotation delayed due to disk pressure"),
    ],
    audit_msgs=[
        (0.03, "WARN", "ops-console", "cron", "定时清理 /data/backups 未执行（cron 被上月变更停用）"),
        (0.05, "INFO", "cert-bot", "renew", "证书续期任务尝试 *.example.com 失败: ACME http-01 无法写文件(磁盘满)"),
        (0.9, "INFO", "ops-console", "fix", "清理 60G 旧备份 + 重启 cert-bot，磁盘 54%，证书已续"),
    ],
)

F6 = Fault(
    id="F6",
    name="前端发版引入 JS 报错",
    severity="P2",
    services={"ec-web"},
    hosts={"ec-node-1"},
    profile={
        "rum_js_err": 0.16,          # 页面级 JS 报错率 0.16
        "rum_res_missing": 0.10,     # 资源 404
        "rum_lcp_boost": 240,        # LCP ms 抬升
        "svc_p99": {"ec-web": 300},
    },
    app_msgs=[
        ("ec-web", "ERROR", "served SPA index referencing /static/js/app.7f3a.chunk.js (404 — 发版缓存不一致)", 1),
    ],
    sys_msgs=[
        ("ec-node-1", "WARN", "nginx: 404s on /static/js/app.7f3a.chunk.js from referer /checkout"),
    ],
    audit_msgs=[
        (0.02, "INFO", "release-bot", "release", "ec-web distVersion=2.4.0-7f3a 灰度 100%（旧 index.html 仍引用 2.3.9 的 chunk 哈希）"),
        (0.9, "INFO", "release-bot", "rollback", "回滚至 distVersion 2.3.9，index.html 与 chunk 哈希一致，报错归零"),
    ],
)

FAULTS: dict[str, Fault] = {"F1": F1, "F2": F2, "F3": F3, "F4": F4, "F5": F5, "F6": F6}
ORDER = ["F1", "F2", "F3", "F4", "F5", "F6"]
# 每条故障的标准时长(分钟) —— 与 RUNBOOKS 的 duration_min 对齐
_DUR_MIN = {"F1": 45, "F2": 45, "F3": 50, "F4": 40, "F5": 50, "F6": 40}
for _fid, _d in _DUR_MIN.items():
    FAULTS[_fid].duration = timedelta(minutes=_d)


# ================================================================ 每个故障的中文 runbook（单一事实来源）
RUNBOOKS: dict[str, dict] = {
    fid: _doc for fid, _doc in [
        (
            "F1",
            dict(
                id="F1",
                title="订单库连接池耗尽 / 慢 SQL",
                severity="P1",
                duration_min=45,
                affected="ec-order / ec-payment / ec-gateway / MySQL(ec-order-db)",
                symptoms=[
                    "下单/支付接口大量 504、500（网关层 `upstream connect timeout`）",
                    "`ec_http_p99_ms` 对 order/payment 冲高到 700–900ms",
                    "`ec_db_conn_pool_active` 顶到 max=50 且 `ec_db_conn_pool_waiting>0`",
                    "`ec_application_logs` 出现 `ER_LOCK_WAIT_TIMEOUT` / `pool exhausted` / `query too slow`",
                ],
                probable_root_cause="订单表 DDL 后查询走全表扫描 + 报表任务长查询占用连接未释放，主库连接池耗尽、锁等待连锁放大。",
                sql_queries=[
                    "select count(*) from \"ec_application_logs\" where service='ec-order' and level='ERROR' and _timestamp between <s> and <e>",
                    "select * from \"ec_access_logs\" where status in ('504','500') and _timestamp between <s> and <e> order by _timestamp desc",
                ],
                metric_queries=["ec_db_conn_pool_active{service=\"ec-order\"}", "ec_http_p99_ms{service=\"ec-order\"}"],
                next_steps=["查 mysql 慢日志/连接数", "EXPLAIN 订单查询计划", "关停大促报表任务、回收连接"],
            ),
        ),
        (
            "F2",
            dict(
                id="F2",
                title="Redis 热点键击穿 / 缓存雪崩",
                severity="P1",
                duration_min=45,
                affected="ec-product / ec-inventory / ec-cart / Redis(ec-redis-cache) / MySQL",
                symptoms=[
                    "商品/库存接口 P99 上升(400–550ms)，但错误率不高",
                    "`ec_redis_hit_ratio` 从 98% 跌到 ~45%",
                    "`ec_db_conn_active`/mysql QPS 冲高(读放大)",
                    "`ec_application_logs`: `cache MISS burst key=product:detail:...` / `cache stampede on SKU-778`",
                ],
                probable_root_cause="大促主推造成单热点 key；促销侧清缓存 + maxmemory 策略改为 allkeys-lru 引发整片过期回源、DB 被击穿。",
                sql_queries=[
                    "select service, count(*) from \"ec_application_logs\" where (message like '%stampede%' or message like '%MISS burst%') and _timestamp between <s> and <e> group by service",
                ],
                metric_queries=["ec_redis_hit_ratio", "ec_http_p99_ms{service=\"ec-product\"}"],
                next_steps=["查 Redis 命中率/memory", "热点 key 加逻辑过期 + 互斥重建", "补缓存预热"],
            ),
        ),
        (
            "F3",
            dict(
                id="F3",
                title="支付回调 Kafka 消费积压",
                severity="P1",
                duration_min=50,
                affected="ec-payment / ec-order / Kafka(ec-kafka-1)",
                symptoms=[
                    "用户已支付但订单状态迟迟不更新（支付『确认』延后）",
                    "`ec_kafka_consumer_lag` 单调爬升到几万~十几万",
                    "`ec_application_logs`: `lag=...` / `paid but state still pending` / `max.poll.interval`",
                    "支付成功率口径异常：下单→支付成功，但 支付确认率 走低",
                ],
                probable_root_cause="ec-payment v2.3.1 在消费线程里加了『远程库存一致性校验(3 次重试)』，单条消费耗时从 4ms 涨到 42ms，吞吐不足形成积压。",
                sql_queries=[
                    "select * from \"ec_application_logs\" where message like '%lag=%' and _timestamp between <s> and <e> order by _timestamp desc",
                ],
                metric_queries=["ec_kafka_consumer_lag{consumer=\"payment-callback\"}"],
                next_steps=["看 lag 增速定积压量", "检查消费线程异常重试", "回滚 v2.3.1 或扩容消费者"],
            ),
        ),
        (
            "F4",
            dict(
                id="F4",
                title="网关误限流 + 上游单实例剔除",
                severity="P1",
                duration_min=40,
                affected="ec-gateway / ec-product / ec-order",
                symptoms=[
                    "结算/下单接口 429 陡增，紧接 502/503",
                    "错误集中在 ec-product 单实例（另一实例被健康检查剔除）",
                    "`ec_access_logs` 出现大量 429 与 `upstream ... connection refused`",
                    "网关日志 `rate limit exceeded zone=orders_burst`",
                ],
                probable_root_cause="发版路由权重误配为 100/0 + 误开 orders_burst 限流 zone，单实例被打满、被摘除后雪崩到限流。",
                sql_queries=[
                    "select status, count(*) from \"ec_access_logs\" where _timestamp between <s> and <e> group by status order by count(*) desc",
                    "select * from \"ec_access_logs\" where status='429' and _timestamp between <s> and <e> order by _timestamp desc limit 50",
                ],
                metric_queries=["ec_http_errors_total{service=\"ec-gateway\"}", "ec_http_request_rate{service=\"ec-product\"}"],
                next_steps=["恢复网关路由权重 50/50", "检查健康检查/摘除记录", "观察 429/5xx 回落"],
            ),
        ),
        (
            "F5",
            dict(
                id="F5",
                title="节点磁盘 90% + 外呼证书过期",
                severity="P2",
                duration_min=50,
                affected="ec-node-2 / ec-web / ec-payment（外呼 HTTPS）",
                symptoms=[
                    "`ec_node_disk_pct` 顶到 91–94%",
                    "外呼 webhook 502/SSL 证书错误（`SSL certificate expired`）",
                    "备份任务失败：`No space left on device`",
                    "日志轮转被跳过，journald 因磁盘压力丢消息",
                ],
                probable_root_cause="清理 cron 被停用 + 日志轮转失败 → 磁盘 92%；证书续期 ACME 因写不了文件连续失败，外呼 HTTPS 报证书过期。",
                sql_queries=[
                    "select * from \"ec_system_logs\" where host='ec-node-2' and _timestamp between <s> and <e> order by _timestamp desc",
                ],
                metric_queries=["ec_node_disk_pct{node=\"ec-node-2\"}"],
                next_steps=["清理 /data/backups 旧备份", "重启 cert-bot 续期", "恢复日志轮转 cron"],
            ),
        ),
        (
            "F6",
            dict(
                id="F6",
                title="前端发版引入 JS 报错",
                severity="P2",
                duration_min=40,
                affected="ec-web（RUM：/ 与 /checkout）",
                symptoms=[
                    "`ec_rum_error` JS runtime/resource 报错突增（TypeError null.map / chunk 404）",
                    "`ec_rum_js_error_rate` 冲到 ~10%+",
                    "结算页 LCP 抬升、`ec_web_lcp_ms` 上升",
                    "服务端 5xx 并不高——问题在前端资源与缓存不一致",
                ],
                probable_root_cause="ec-web 灰度 v2.4.0-7f3a，但仍有用户命中引用旧 chunk 哈希的 index.html，加载 404 的 JS → 运行时异常。",
                sql_queries=[
                    "select error_type, count(*) from \"ec_rum_error\" where _timestamp between <s> and <e> group by error_type",
                    "select route, count(*) from \"ec_rum_error\" group by route order by count(*) desc",
                ],
                metric_queries=[],
                next_steps=["按 route/error_type 收敛报错", "核对 distVersion 与 index.html 引用", "回滚到 2.3.9 并清 CDN 缓存"],
            ),
        ),
    ]
}
