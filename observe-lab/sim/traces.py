"""链路生成：网关→服务→(MySQL/Redis/Kafka/ES) 的 span 树。

每个采样请求产出一条可点的瀑布；故障窗口里会给对应的子 span 打上 ERROR + 真实错误文案，
并让响应码、耗时与 Env 的 p99/错误率自洽。返回 (spans, trace_pool)。
"""
from __future__ import annotations

from typing import Optional

from o2 import otlp
from o2.client import now_ns

from . import topology as topo
from .flow import Env
from .rng import SimRandom

# 每种服务采样时挂的子依赖
_SVC_DEP = {
    "ec-web": [],                                   # 纯前端静态/BFF 轻调用
    "ec-product": ["redis:ec-redis-cache:get product:detail", "mysql:ec-shop-db:select product"],
    "ec-search": ["es:ec-es-1:search index=product"],
    "ec-cart": ["redis:ec-redis-cache:get cart:8812"],
    "ec-inventory": ["redis:ec-redis-cache:get sku:778", "mysql:ec-shop-db:select inventory"],
    "ec-order": ["mysql:ec-order-db:insert orders", "redis:ec-redis-cache:set order:88231"],
    "ec-payment": ["mysql:ec-order-db:update payments", "kafka:ec-kafka-1:publish ec-payment-events"],
    "ec-user": ["redis:ec-redis-session:set session:8812"],
}

# 故障 → 根因 span 的错误文案（挂在最接近根因的子 span 上）
_SPAN_ERROR = {
    "F1": "ER_LOCK_WAIT_TIMEOUT: Lock wait timeout exceeded; try restarting transaction",
    "F2": "cache stampede: 32 rebuilders waiting on distributed lock, DB read amplification",
    "F3": "kafka produce/consume slowed: remote stock check retry, max.poll.interval near limit",
    "F4": "upstream http://10.1.8.12:8080 connect refused (rate limited / instance drained)",
    "F5": "outbound HTTPS failed: SSL certificate expired",
    "F6": "resource 404 /static/js/app.7f3a.chunk.js — 前端 JS 运行时异常",
}

_STATUS_ERR = {"F1": "500", "F2": "500", "F3": "500", "F4": "429", "F5": "502", "F6": "200"}


def _span_err_for(env: Env, svc: str) -> Optional[str]:
    """本分钟激活且影响 svc 的故障，返回要打 error 文案的 (fid,msg)；否则 None。"""
    for f in env.faults:
        if f.id in _SPAN_ERROR and svc in f.services and f.intensity_at(env.dt) > 0.15:
            return f.id
    return None


def generate(env: Env, rng: SimRandom, trace_no: int = 0) -> tuple[list[otlp.SpanRecord], dict]:
    """返回 (span_records, trace_pool)。trace_no 是本次运行累计计数，保证 id 稳定。"""
    # 采样规模：随负载；每服务一笔的“命中率”由 traces_plan 决定（main 已算 T）
    # 本函数内部按 env.svc 行数比例分配，T 由调用方传 minu… 简化：由 env 推导
    spans: list[otlp.SpanRecord] = []
    pool: dict[str, list[str]] = {svc: [] for svc in env.svc if svc != "ec-gateway"}

    total_w = sum(max(0.0, st.weight) for st in env.svc.values() if st.service != "ec-gateway")
    if total_w <= 0:
        return spans, pool
    budget = max(0, int(round((0.5 + env.intensity * 11) * rng.uniform(0.8, 1.25))))
    if budget <= 0:
        return spans, pool

    minute_base_ns = int(env.dt.timestamp() * 1_000_000_000)
    assigned = 0
    # 按权重给服务分批；至少给每服务少量机会
    weights = [(svc, st) for svc, st in env.svc.items() if svc != "ec-gateway" and st.weight > 0]
    attempts = 0
    while assigned < budget and attempts < budget * 6:
        attempts += 1
        svc, st = rng.choice(weights)
        if rng.rand() > st.weight * (budget / (0.5 + env.intensity * 11)) / 0.3:
            continue
        t = trace_no + assigned
        fid = _span_err_for(env, svc)
        tok = f"m{env.dt.strftime('%Y%m%d%H%M')}n{t}"
        tid = otlp.deterministic_id(f"t{tok}", 128)
        rsid = otlp.deterministic_id(f"r{tok}", 64)
        host = st.host
        # 起点：分钟内的随机偏移
        off_ns = int(rng.uniform(0.2, 0.95) * 59.0 * 1e9)
        gw_start = minute_base_ns + off_ns
        # 响应码
        is_err = fid is not None and rng.chance(0.75)
        if not is_err and rng.rand() < st.err_frac:
            is_err = True
            fid = fid or "X"
        code = (_STATUS_ERR.get(fid, "500") if is_err else "200")

        # 服务处理时长：均值≈p99*0.32，对数正态抖动
        dur_mean = st.p99_ms * 0.32
        dur_ms = rng.gauss(dur_mean, dur_mean * 0.45)
        dur_ms = max(1.0, dur_ms)
        gw_extra = dur_ms * rng.uniform(0.08, 0.18)   # 网关额外转发/排队

        # root = gateway
        root = otlp.SpanRecord(
            "GET /api/v1/upstream", trace_id=tid, span_id=rsid,
            start_ns=gw_start, end_ns=gw_start + int((dur_ms + gw_extra) * 1e6),
            kind=2, service="ec-gateway",
            attrs={"http.method": "GET", "http.route": "/api/v1/{svc}",
                   "http.status_code": int(code) if code.isdigit() else 200,
                   "upstream": svc, "host": topo.NODES[0] if host else "ec-node-1"},
        )
        if is_err:
            root.status = 2
            root.attrs["error.message"] = _SPAN_ERROR.get(fid, "request failed")
        spans.append(root)

        # 调用服务 span（SERVER 层，gateway 的下游）
        ssid = otlp.deterministic_id(f"s{tok}", 64)
        s_start = root.start_ns + int(gw_extra * 1e6)
        s_end = s_start + int(dur_ms * 1e6)
        svc_span = otlp.SpanRecord(
            f"{svc} handle", trace_id=tid, span_id=ssid, parent_span_id=rsid,
            start_ns=s_start, end_ns=s_end, kind=3, service=svc,
            attrs={"peer.service": svc, "host.name": host, "http.status_code": int(code) if code.isdigit() else 200},
        )
        if is_err:
            svc_span.status = 2
            svc_span.attrs["error.message"] = _SPAN_ERROR.get(fid, "error")
        spans.append(svc_span)

        # 子依赖 span（CLIENT）
        for i, dep in enumerate(_SVC_DEP.get(svc, [])):
            cid = otlp.deterministic_id(f"c{tok}{i}", 64)
            kind_s, name = (dep.split(":", 1) + ["", ""])[:2]
            base_ms = rng.uniform(2, 14)
            if "mysql" in kind_s:
                base_ms = rng.uniform(8, 40)
            elif "redis" in kind_s:
                base_ms = rng.uniform(0.5, 3)
            dep_err = False
            if fid and _is_root(fid, svc) and rng.chance(0.8):
                dep_err = True
                base_ms *= rng.uniform(4, 12)
            c_start = s_start + int(rng.uniform(0, dur_ms * 0.2) * 1e6)
            c_end = min(s_end, c_start + int(base_ms * 1e6))
            dep_span = otlp.SpanRecord(
                name, trace_id=tid, span_id=cid, parent_span_id=ssid,
                start_ns=c_start, end_ns=c_end, kind=4, service=svc,
                attrs={"db.system": kind_s.split(":")[0], "peer": dep},
            )
            if dep_err:
                dep_span.status = 2
                dep_span.attrs["error.message"] = _SPAN_ERROR.get(fid, "downstream error")
            spans.append(dep_span)
        pool[svc].append(tid.hex())
        assigned += 1
    return spans, pool


def _is_root(fid: str, svc: str) -> bool:
    # 只把依赖错误挂到最像“根因宿主”的服务组合上（简化：F1 挂 order 依赖，F2 挂 product…）
    return (fid, svc) in {("F1", "ec-order"), ("F2", "ec-product"), ("F3", "ec-payment"),
                          ("F4", "ec-gateway"), ("F5", "ec-web"), ("F6", "ec-web")}
