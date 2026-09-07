"""日志生成：ec_access_logs / ec_application_logs / ec_system_logs / ec_audit_logs。

时间戳为微秒（对齐 O2 _json 约定）。trace_pool 由 main 从当分钟 traces 传进来，
用于部分日志与链路 trace_id 对齐（可点日志跳瀑布）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from . import incidents as inc
from . import rng as R
from . import topology as topo
from .flow import Env
from .rng import SimRandom

# ---------------------------------------------------------------- 报文素材
_UA = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Mobile Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) Chrome/125.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
    "okhttp/4.12.0", "PostmanRuntime/7.37.0", "python-requests/2.31",
]
_REFERERS = ["https://www.ecshop.example.com/", "https://www.ecshop.example.com/cart",
             "https://www.ecshop.example.com/products/38412", "-"]

# 每服务的典型 path（供 access log 与错误注入）; {svc: [(method, path, weight)]}
SVC_PATHS = {
    "ec-web": [("GET", "/", 5), ("GET", "/static/{asset}", 4), ("GET", "/checkout", 2),
               ("GET", "/order/confirm/{oid}", 1)],
    "ec-product": [("GET", "/api/v1/products/38412", 4), ("GET", "/api/v1/products/90321", 2),
                   ("GET", "/api/v1/products?category=digital&page={p}", 2),
                   ("GET", "/api/v1/products/38412/reviews", 1)],
    "ec-search": [("GET", "/api/v1/search?q={q}&page={p}", 3)],
    "ec-cart": [("GET", "/api/v1/cart", 3), ("GET", "/api/v1/cart/8812", 2),
                ("POST", "/api/v1/cart/items", 2), ("POST", "/api/v1/cart/8812/checkout", 1)],
    "ec-inventory": [("GET", "/api/v1/inventory/SKU-778", 2), ("GET", "/api/v1/inventory/{sku}", 2)],
    "ec-order": [("POST", "/api/v1/orders", 3), ("GET", "/api/v1/orders/{oid}", 2)],
    "ec-payment": [("POST", "/api/v1/payments/88231/callback", 2), ("GET", "/api/v1/payments/{pid}/status", 2)],
    "ec-user": [("POST", "/api/v1/users/{uid}/login", 2), ("GET", "/api/v1/users/{uid}/profile", 2)],
}
_ASSET_POOL = ["app.2d4f.js", "app.1ab9.css", "logo.c4d2.png", "checkout.88ab.chunk.js",
               "app.7f3a.chunk.js", "vendor.90cd.chunk.js"]
_QRY = {"q": ["%E7%94%B5%E8%84%91", "手机", "夏日连衣裙", "机械键盘"], "p": ["1", "2", "3"],
        "sku": ["SKU-778", "SKU-112", "SKU-909"], "oid": ["20260901093821-88231", "20260901074219-11203"],
        "uid": ["33812", "8812", "52390"], "pid": ["88231", "99122"]}


def _fill(path: str, rng: SimRandom) -> str:
    """把 path 里的 {占位} 随机填上真实值（模拟真实 URL 多样性）。"""
    for key, vals in _QRY.items():
        if "{" + key + "}" in path:
            path = path.replace("{" + key + "}", rng.choice(vals))
    if "{asset}" in path:
        path = path.replace("{asset}", rng.choice(_ASSET_POOL))
    return path


def _micro(dt: datetime, rng: SimRandom) -> int:
    """分钟起始时刻 + 分钟内的随机秒偏移（微秒）。"""
    base = int(dt.timestamp() * 1_000_000)
    return base + int(rng.uniform(0, 59.9) * 1_000_000)


def _trace_token(rng: SimRandom, n: int) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(n))


# 供 trace 池匹配：svc -> list[trace_hex]
TracePool = dict[str, list[str]]


# ---------------------------------------------------------------- access
def access_lines(env: Env, rng: SimRandom, pool: Optional[TracePool] = None) -> list[dict]:
    out: list[dict] = []
    pool = pool or {}
    for svc, st in env.svc.items():
        if svc == "ec-gateway" or st.lines <= 0:
            continue
        n = st.lines
        err_n = max(0, int(round(st.err_frac * n)))
        bump_codes = list(st.status_bump.keys())
        for _ in range(n):
            method, path, _w = rng.choice(SVC_PATHS.get(svc, [("GET", "/", 1)]))
            full_path = _fill(path, rng)
            # 状态码采样：优先故障 bump，其次按错误率出 5xx/4xx
            roll = rng.rand()
            code = "200"
            extra = st.status_bump
            if extra:
                cdf = 0.0
                for c, frac in extra.items():
                    cdf += frac
                    if roll < cdf:
                        code = c
                        break
            if code == "200":
                if err_n > 0 and rng.rand() < st.err_frac:
                    code = rng.choice(["500", "503", "502"] if svc != "ec-web" else ["500"])
                elif rng.chance(0.004):
                    code = "404" if svc == "ec-web" else "400"
            is_err = not code.startswith("2")
            rt = st.p99_ms / 1000.0
            request_time = rng.gauss(rt, rt * 0.5) if is_err else rng.uniform(0.004, rt * 0.9)
            upstream_time = request_time * rng.uniform(0.7, 0.98)
            trace = rng.choice(pool.get(svc) or [""])
            rec = {
                "_timestamp": _micro(env.dt, rng),
                "service": "ec-gateway",
                "host": st.host,
                "upstream": svc,
                "method": method,
                "path": full_path,
                "status": code,
                "remote_addr": R.fake_user_ip(rng),
                "region": st.region,
                "request_time_ms": round(max(0.0, request_time) * 1000, 2),
                "upstream_time_ms": round(max(0.0, upstream_time) * 1000, 2),
                "body_bytes": rng.randint(120, 96000),
                "user_agent": rng.choice(_UA),
                "referer": rng.choice(_REFERERS),
                "level": "INFO",
            }
            if trace:
                rec["trace_id"] = trace
                rec["span_id"] = _trace_token(rng, 16)
            if is_err:
                rec["level"] = "WARN" if code.startswith("4") else "ERROR"
            out.append(rec)
    return out


# ---------------------------------------------------------------- application
# 各服务正常业务日志模板（INFO），扣住真实事件
_APP_INFO = {
    "ec-order": ["POST /api/v1/orders 201 created order {oid} user {uid} paid_amount=299.00",
                 "order {oid} state updated created->confirmed (user {uid})"],
    "ec-payment": ["payment {pid} captured amount=299.00 channel=alipay result=success",
                   "callback {pid} verified signature OK, 投递 kafka topic=ec-payment-events"],
    "ec-product": ["GET product:detail:38412 cache hit ttl=247s",
                   "stock check sku=SKU-778 avail=863"],
    "ec-inventory": ["reserve sku=SKU-778 qty=1 ok remaining=862"],
    "ec-cart": ["cart 8812: merged 2 items user {uid}"],
    "ec-search": ["search q=手机 hits=1284 took=38ms"],
    "ec-user": ["login {uid} ok device=android session=... "],
    "ec-web": ["serve index.html distVersion=2.3.9 ttl=0 (dynamic)"],
}
_APP_WARN = {
    "ec-order": ["GET /api/v1/orders/{oid} slow query 312ms (>200ms 阈值)", "retry insert order {oid} attempt 2/3"],
    "ec-payment": ["callback {pid} delayed 1.2s (>500ms)", "signature verify warning: clock skew +3s"],
    "ec-product": ["cache MISS product:detail:38412 (single) rebuild 18ms"],
    "ec-inventory": ["redis get SKU-778 MISS then GET 1 ok"],
    "ec-cart": ["cart 8812 item stale, refetch price ok"],
    "ec-user": ["login {uid} 2FA code resent"],
    "ec-web": ["static 404 /static/app.7f3a.chunk.js from /"],   # F6 也有
    "ec-search": ["es slow query q=空 took 210ms"],
}


def application_lines(env: Env, rng: SimRandom, pool: Optional[TracePool] = None) -> list[dict]:
    out: list[dict] = []
    pool = pool or {}
    for svc, st in env.svc.items():
        if svc == "ec-gateway":
            continue
        # INFO 主业务日志 ~ 每服务若干条（低流量服务少）
        n_info = max(1, int(round(st.lines * 0.10 * rng.uniform(0.6, 1.4))))
        for _ in range(n_info):
            tmpl = rng.choice(_APP_INFO.get(svc, ["heartbeat ok"]))
            msg = tmpl.format(oid="2026090" + str(rng.randint(100000, 999999)),
                              pid=rng.randint(10000, 99999), uid=rng.randint(10000, 99999))
            rec = {
                "_timestamp": _micro(env.dt, rng), "service": svc, "host": st.host,
                "level": "INFO", "logger": f"com.ec.{svc}.service", "message": msg,
            }
            t = rng.choice(pool.get(svc) or [""])
            if t and rng.chance(0.4):
                rec["trace_id"] = t
            out.append(rec)
        # WARN 层（慢/重试/缓存未命中等），跟随负载出现
        n_warn = int(round(st.lines * 0.008 * rng.uniform(0.5, 1.6)))
        for _ in range(n_warn):
            tmpl = rng.choice(_APP_WARN.get(svc, ["warn: unusual timing"]))
            rec = {
                "_timestamp": _micro(env.dt, rng), "service": svc, "host": st.host,
                "level": "WARN", "logger": f"com.ec.{svc}.metric", "message": tmpl.format(
                    oid="2026090" + str(rng.randint(100000, 999999)),
                    pid=rng.randint(10000, 99999), uid=rng.randint(10000, 99999)),
            }
            out.append(rec)
        # ERROR 基线
        if rng.chance(min(0.5, st.err_frac * st.lines / 3.0)):
            out.append({
                "_timestamp": _micro(env.dt, rng), "service": svc, "host": st.host,
                "level": "ERROR", "logger": f"com.ec.{svc}.err",
                "message": rng.choice([f"exception processing request: {svc} BusinessException(code=1001)",
                                       "circuit OPEN after 5 failures",
                                       "timeout calling internal downstream"]),
            })
    # 故障症状消息：窗口内逐分钟抽症状（带权重）
    for f in env.faults:
        a = f.intensity_at(env.dt)
        n_sym = int(round(6 * a * rng.uniform(0.7, 1.3)))
        host_ph = next(iter(f.hosts)) if f.hosts else "ec-node-1"
        for _ in range(n_sym):
            m = f.sample_app_msg(rng)
            if not m:
                continue
            svc, lvl, msg = m
            msg = msg.replace("{host}", host_ph).replace("{svc}", svc)
            rec = {
                "_timestamp": _micro(env.dt, rng), "service": svc,
                "host": rng.choice(topo.SERVICE_HOSTS.get(svc, topo.NODES)),
                "level": lvl, "logger": f"com.ec.{svc}.fault", "message": msg,
                "trace_id": _trace_token(rng, 32) if rng.chance(0.5) else "",
            }
            if rec["trace_id"] == "":
                rec.pop("trace_id")
            out.append(rec)
    return out


# ---------------------------------------------------------------- system
_SYS_INFO = [
    ("ec-node-1", "kubelet", "node ec-node-1 Ready (containers ready 18/18)"),
    ("ec-node-2", "systemd", "Started session of user ops"),
    ("ec-node-3", "kubelet", "SyncLoop (PLEG): healthy"),
    ("ec-kafka-1", "kafka", "Metrics recorded: request rate 12.3 req/s"),
]
_SYS_WARN = [
    ("ec-db-mysql-1", "mysqld", "InnoDB: page read 120/s, buffer pool hit 99.6%"),
    ("ec-db-redis-1", "redis", "INFO memory.used 3.1G / maxmemory 4.0G"),
    ("ec-node-2", "journald", "Vacuuming old logs, deleting 20 files"),
]


def system_lines(env: Env, rng: SimRandom) -> list[dict]:
    out: list[dict] = []
    # 基线：低频轮询/事件
    if rng.chance(0.30):
        host, unit, msg = rng.choice(_SYS_INFO)
        out.append({"_timestamp": _micro(env.dt, rng), "service": "kubelet/system",
                    "host": host, "level": "INFO", "logger": unit, "message": msg,
                    "namespace": topo.K8S_NAMESPACE})
    if rng.chance(0.10):
        host, unit, msg = rng.choice(_SYS_WARN)
        out.append({"_timestamp": _micro(env.dt, rng), "service": "system",
                    "host": host, "level": "WARN", "logger": unit, "message": msg})
    # 节点负载快照（每 5 分钟一次，作为 host 维度体检）
    if env.dt.minute % 5 == 0:
        for node, vals in env.node.items():
            for unit, key in (("df", "disk"), ("vmstat", "cpu")):
                pass
            out.append({"_timestamp": _micro(env.dt, rng), "service": "node-exporter",
                        "host": node, "level": "INFO", "logger": "collector",
                        "message": f"node {node} disk_pct={vals['disk']:.0f} cpu={vals['cpu']:.0f}% mem={vals['mem']:.0f}%"})
    # 故障系统症状
    for f in env.faults:
        if f.sys_msgs and rng.chance(0.8 * f.intensity_at(env.dt)):
            host, lvl, msg = f.sample_sys_msg(rng)
            out.append({"_timestamp": _micro(env.dt, rng), "service": "system",
                        "host": host, "level": lvl, "logger": "ops", "message": msg})
    return out


# ---------------------------------------------------------------- audit
_ACTORS = ["ops-console", "release-bot", "re-deployer", "cert-bot", "sqe-worker"]
_ROT = [
    "登录控制台 ip={ip} user=agunc", "查看配置中心 namespace=prod",
    "下载审计日志 2026-08-31~2026-09-05", "导出账单数据 size=3.2GB",
    "更新 runbook 文档 fault=磁盘清理", "执行 kubectl rollout status deploy/ec-order",
]


def audit_lines(env: Env, rng: SimRandom, minute_index: int) -> list[dict]:
    out: list[dict] = []
    # 平时稀疏的审计动作
    if minute_index % 11 == 0 or rng.chance(0.06):
        actor = rng.choice(_ACTORS)
        action = rng.choice(_ROT).format(ip=R.ip_of(rng))
        out.append({"_timestamp": _micro(env.dt, rng), "service": "audit",
                    "host": "ec-ops-1", "level": "INFO", "logger": "audit",
                    "actor": actor, "action": action,
                    "result": rng.choice(["ok", "ok", "ok", "denied"]),
                    "namespace": topo.K8S_NAMESPACE, "message": f"{actor} {action}"})
    # 故障触发点审计（rel 触发点在窗口边缘出现一次）
    for f in env.faults:
        if not (f.start and f.end):
            continue
        rel = f.rel_at(env.dt)
        for (at_rel, lvl, actor, action, detail) in f.audit_msgs:
            near = abs(rel - at_rel) < (1.0 / max(1, int((f.end - f.start).total_seconds() // 60)))
            # 仅在命中触发点的那一分钟生成一次（用 env.dt.minute 判重可省，下面用时间比较）
            if near and rng.chance(0.9):
                out.append({"_timestamp": _micro(env.dt, rng), "service": "audit",
                            "host": "ec-ops-1", "level": lvl, "logger": "audit",
                            "actor": actor, "action": action, "detail": detail,
                            "result": "ok" if lvl == "INFO" else "fail",
                            "fault_id": f.id, "message": f"{actor} {action}: {detail}"})
                break
    return out
