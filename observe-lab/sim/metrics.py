"""指标生成：把 Env 变成本分钟的 OTLP gauge 样本点列表。

设计原则：全部用 gauge（瞬时值），避免累计 counter 在回填/截断下语义混乱；
PromQL 里直接读原值即可，演示最直观。metric 名即 O2 流名(带 ec_ 前缀)。
"""
from __future__ import annotations

from o2.otlp import MetricPoint

from . import topology as topo
from .flow import Env
from .rng import SimRandom


def generate(env: Env, rng: SimRandom) -> list[MetricPoint]:
    t_ns = int(env.dt.timestamp() * 1_000_000_000)
    pts: list[MetricPoint] = []
    add = pts.append

    # ---- 服务 HTTP 维度（labels: service = upstream 服务）----
    for svc, st in env.svc.items():
        if svc == "ec-gateway":
            continue
        labels = {"service": svc, "host": st.host, "region": st.region}
        add(MetricPoint("ec_http_request_rate", "gauge", max(0, st.lines) / 60.0, labels=labels, time_ns=t_ns))
        add(MetricPoint("ec_http_error_rate", "gauge", round(min(100, st.err_frac * 100), 3), labels=labels, time_ns=t_ns))
        add(MetricPoint("ec_http_p99_ms", "gauge", round(st.p99_ms, 1), labels=labels, time_ns=t_ns))

    # ---- 数据库池 / QPS ----
    for comp, d in env.dbs.items():
        lbl = {"component": comp, "host": d.host}
        add(MetricPoint("ec_db_conn_pool_active", "gauge", d.active_frac * d.max_conn, labels=lbl, time_ns=t_ns))
        add(MetricPoint("ec_db_conn_pool_waiting", "gauge", d.waiting, labels=lbl, time_ns=t_ns))
        add(MetricPoint("ec_db_conn_pool_max", "gauge", d.max_conn, labels=lbl, time_ns=t_ns))
        add(MetricPoint("ec_mysql_qps", "gauge", d.qps, labels=lbl, time_ns=t_ns))
        add(MetricPoint("ec_mysql_slow_ratio", "gauge", d.slow_ratio, labels=lbl, time_ns=t_ns))

    # ---- Redis ----
    rl = {"redis": "ec-redis-cache", "host": topo.REDIS_HOSTS["ec-redis-cache"]}
    add(MetricPoint("ec_redis_hit_ratio", "gauge", env.redis_hit, labels=rl, time_ns=t_ns))
    add(MetricPoint("ec_redis_memory_bytes", "gauge", int(env.redis_mem_gb * 1e9), labels=rl, time_ns=t_ns))

    # ---- Kafka ----
    kl = {"consumer": "payment-callback", "topic": "ec-payment-events", "host": topo.KAFKA_HOST}
    add(MetricPoint("ec_kafka_consumer_lag", "gauge", env.kafka_lag, labels=kl, time_ns=t_ns))

    # ---- K8s 节点 ----
    for node, v in env.node.items():
        nl = {"node": node}
        add(MetricPoint("ec_node_cpu_pct", "gauge", round(v["cpu"], 1), labels=nl, time_ns=t_ns))
        add(MetricPoint("ec_node_mem_pct", "gauge", round(v["mem"], 1), labels=nl, time_ns=t_ns))
        add(MetricPoint("ec_node_disk_pct", "gauge", round(v["disk"], 1), labels=nl, time_ns=t_ns))

    # ---- 业务 KPI ----
    add(MetricPoint("ec_order_placed_rate", "gauge", round(env.order_rate, 3),
                    labels={"service": "ec-order"}, time_ns=t_ns))
    add(MetricPoint("ec_payment_confirm_pct", "gauge", round(env.pay_confirm_pct, 2),
                    labels={"channel": "callback"}, time_ns=t_ns))
    # ---- 前端体验(RUM) 指标 ----
    add(MetricPoint("ec_rum_pv_rate", "gauge", env.web_pv / 60.0, labels={"page": "/"}, time_ns=t_ns))
    add(MetricPoint("ec_rum_lcp_ms", "gauge", round(env.web_lcp_ms, 1), labels={"page": "/"}, time_ns=t_ns))
    add(MetricPoint("ec_rum_js_error_rate", "gauge", round(min(100, env.web_js_err_rate * 100), 3),
                    labels={"page": "/"}, time_ns=t_ns))
    return pts
