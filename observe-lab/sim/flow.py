"""分钟级上下文：把「基线 + 故障叠加」合成单个 Env，日志/指标/链路/RUM 都从它读数。

避免各生成器各自算一遍，保证同一分钟所有信号自洽（例如 rps 与 access 行数对应）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from . import incidents as inc
from . import rng as R
from . import topology as topo
from .rng import SimRandom


# 各服务每分钟“代表请求行数”权重（归一后乘 PEAK_LINES）。下单/支付低频、浏览高频。
_SVC_WEIGHT = {
    "ec-gateway": 0.0,      # 网关不单独产生业务行，行都归到 upstream
    "ec-product": 0.30,
    "ec-search": 0.14,
    "ec-cart": 0.13,
    "ec-inventory": 0.09,
    "ec-order": 0.10,
    "ec-payment": 0.07,
    "ec-user": 0.06,
    "ec-web": 0.11,
}
_PEAK_LINES = 180          # 强度=1.0 时全服务每分钟代表请求行数（折衷体量与观感）

_P99_BASE = {
    "ec-gateway": 70, "ec-web": 45, "ec-product": 120, "ec-search": 90,
    "ec-cart": 95, "ec-inventory": 85, "ec-order": 150, "ec-payment": 190,
    "ec-user": 60,
}
_ERR_BASE = {
    "ec-gateway": 0.0015, "ec-web": 0.0012, "ec-product": 0.0016,
    "ec-search": 0.0012, "ec-cart": 0.0014, "ec-inventory": 0.0014,
    "ec-order": 0.0025, "ec-payment": 0.0020, "ec-user": 0.0012,
}
_DB_POOL_MAX = {"ec-order-db": 50, "ec-shop-db": 30}


@dataclass
class SvcStat:
    service: str
    host: str
    weight: float
    lines: int                 # 本分钟代表请求行数
    err_frac: float            # 该服务错误率(含故障叠加)
    p99_ms: float
    region: str
    # 由故障加出来的“额外转成某状态码”的比例
    status_bump: dict = field(default_factory=dict)


@dataclass
class DbStat:
    component: str
    host: str
    max_conn: int
    active_frac: float         # 0..1.15（>1 表示排队）
    waiting: int
    qps: float
    slow_ratio: float


@dataclass
class Env:
    dt: datetime
    intensity: float
    minute_lines: int
    faults: list                 # 该分钟处于激活态的 Fault 列表
    svc: dict[str, SvcStat] = field(default_factory=dict)
    dbs: dict[str, DbStat] = field(default_factory=dict)
    redis_hit: float = 98.5
    redis_mem_gb: float = 3.1
    kafka_lag: int = 320
    node: dict = field(default_factory=dict)   # node -> {cpu,mem,disk}
    web_lcp_ms: float = 210
    web_js_err_rate: float = 0.003
    web_res_missing: float = 0.0
    web_pv: int = 0
    order_rate: float = 0.0      # 每分钟下单量(rps)
    pay_confirm_pct: float = 99.5

    def active(self, fid: str) -> bool:
        return any(f.id == fid for f in self.faults)


def _weighted_lines(intensity: float, weekday: bool) -> dict:
    """返回 {svc: 代表行数}。周末/深夜按曲线打折。"""
    out = {}
    wsum = sum(_SVC_WEIGHT.values())
    base = _PEAK_LINES * max(0.0, intensity) / wsum
    for svc, w in _SVC_WEIGHT.items():
        out[svc] = max(1, int(round(base * w)))
    return out


def build_env(rng: SimRandom, dt: datetime, faults: list) -> Env:
    """构造某分钟的 Env。faults = 本分钟激活的 Fault 列表（可为空）。"""
    intensity = R.day_intensity(dt)
    svc_lines = _weighted_lines(intensity, dt.weekday() < 5)
    env = Env(dt=dt, intensity=intensity,
              minute_lines=sum(svc_lines.values()), faults=faults)
    svc = env.svc
    for name in topo.SERVICES:
        w = _SVC_WEIGHT.get(name, 0.0)
        stat = SvcStat(
            service=name,
            host=rng.choice(topo.SERVICE_HOSTS[name]) if topo.SERVICE_HOSTS[name] else "ec-node-1",
            weight=w,
            lines=svc_lines.get(name, 1),
            err_frac=_ERR_BASE.get(name, 0.0015),
            p99_ms=_P99_BASE.get(name, 100),
            region=rng.choice(topo.REGIONS),
        )
        # 叠加所有本分钟激活且影响该服务的故障
        for f in faults:
            if name in f.services:
                stat.err_frac += f.service_error_rate(name, dt)
                p = f.service_p99_ms(name, dt)
                if p is not None:
                    stat.p99_ms = max(stat.p99_ms, p)
                bump = f.status_bump(dt).get(name)
                if bump:
                    for code, frac in bump.items():
                        stat.status_bump[code] = stat.status_bump.get(code, 0.0) + frac
        # 抖动：p99 基线 ±15%
        stat.p99_ms = max(20, stat.p99_ms * rng.uniform(0.85, 1.15))
        stat.lines = max(0, int(round(stat.lines * rng.uniform(0.9, 1.12))))
        svc[name] = stat

    # ---- 中间件状态 ----
    f1 = next((f for f in faults if f.id == "F1"), None)
    f2 = next((f for f in faults if f.id == "F2"), None)
    f3 = next((f for f in faults if f.id == "F3"), None)
    f5 = next((f for f in faults if f.id == "F5"), None)

    for comp in ("ec-order-db", "ec-shop-db"):
        mx = _DB_POOL_MAX[comp]
        base_active = rng.uniform(0.28, 0.5)
        active_frac = base_active
        waiting = 0
        qps = rng.uniform(300, 900)
        slow = rng.uniform(0.02, 0.05)
        if f1 and comp == "ec-order-db":
            a = f1.intensity_at(dt)
            active_frac = min(1.18, base_active + (1.0 - base_active) * a)
            waiting = int(round(f1.db("wait", dt)))
            qps += f1.db("qps_boost", dt) * 500
            slow = min(0.95, slow + f1.db("slow_ratio", dt))
        if f2 and comp == "ec-shop-db":
            qps += f2.db("qps_boost", dt) * 550
        env.dbs[comp] = DbStat(comp, topo.MYSQL_HOSTS[comp], mx, active_frac,
                               waiting, qps, slow)

    env.redis_hit = rng.uniform(97.5, 99.3)
    env.redis_mem_gb = rng.uniform(3.0, 3.4)
    if f2:
        a = f2.intensity_at(dt)
        env.redis_hit = 45 + (env.redis_hit - 45) * (1 - a)   # 命中率滑向 45%
        env.redis_mem_gb += 1.2 * a

    env.kafka_lag = int(rng.randint(150, 900))
    if f3:
        env.kafka_lag = int(900 + f3.scalar("kafka_lag", dt))

    # ---- 节点 ----
    for node in topo.NODES:
        disk = rng.uniform(58, 74)
        if f5 and node in f5.hosts:
            target = (f5.profile.get("node_disk") or {}).get(node, 60.0)
            disk = 60 + (target - 60) * f5.intensity_at(dt)
        disk = min(97, disk)
        env.node[node] = {
            "cpu": rng.uniform(18, 45),
            "mem": rng.uniform(50, 68),
            "disk": disk,
        }

    # ---- 前端体验 ----
    env.web_pv = int(svc["ec-web"].lines * rng.uniform(0.9, 1.1))
    env.web_lcp_ms = rng.uniform(170, 260)
    env.web_js_err_rate = rng.uniform(0.001, 0.008)
    if any(f.id == "F6" for f in faults):
        f6 = next(f for f in faults if f.id == "F6")
        a = f6.intensity_at(dt)
        env.web_js_err_rate = 0.16 * a
        env.web_res_missing = 0.10 * a
        env.web_lcp_ms += f6.scalar("rum_lcp_boost", dt)

    # ---- 业务 KPI（每分钟下单≈成交；支付确认率受 F3 拖累）----
    order_lines = max(1, svc["ec-order"].lines)
    env.order_rate = order_lines / 60.0 * rng.uniform(0.7, 0.95)
    env.pay_confirm_pct = rng.uniform(99.2, 99.8)
    if f3:
        env.pay_confirm_pct = max(40, env.pay_confirm_pct - (99.0 - 55) * f3.intensity_at(dt) * 0.6)
    return env
