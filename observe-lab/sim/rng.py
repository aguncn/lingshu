"""确定性随机源 + 电商日波动曲线 + 常用小工具。

固定 seed → 相同参数重跑产出完全一致，便于复现与核对。
"""
from __future__ import annotations

import random
from datetime import datetime

from . import topology as topo


class SimRandom:
    """带固定种子的随机源（包一层，方便以后换算法不四处改）。"""

    def __init__(self, seed: int):
        self._r = random.Random(seed)
        self.seed = seed

    # ---- 基础
    def rand(self) -> float:
        return self._r.random()

    def uniform(self, a: float, b: float) -> float:
        return self._r.uniform(a, b)

    def choice(self, seq):
        return self._r.choice(seq)

    def choices(self, seq, k: int):
        return self._r.choices(seq, k=k)

    def randint(self, a: int, b: int) -> int:
        return self._r.randint(a, b)

    def gauss(self, mu: float, sigma: float) -> float:
        return max(0.0, self._r.gauss(mu, sigma))

    def expov(self, rate: float) -> float:
        """泊松到达间隔（分钟为单位的换算由调用方处理）。"""
        return self._r.expovariate(rate)

    def chance(self, p: float) -> bool:
        return self._r.random() < p


# 一天内的业务强度折线点 (hour 带小数, 强度 0..1)。电商双高峰。
_DAILY_POINTS = [
    (0.0, 0.10), (2.0, 0.05), (5.0, 0.04), (7.0, 0.12), (8.5, 0.30),
    (10.0, 0.75), (11.5, 1.00), (13.0, 0.72), (15.0, 0.80), (17.0, 0.72),
    (18.5, 0.85), (20.0, 0.98), (21.5, 0.90), (23.0, 0.55), (23.999, 0.20),
]


def day_intensity(dt: datetime) -> float:
    """返回某时刻的业务基础强度 0..1（工作日 + 周末打折）。"""
    h = dt.hour + dt.minute / 60.0
    # 折线段插值
    lo = _DAILY_POINTS[0]
    v = lo[1]
    for hi in _DAILY_POINTS[1:]:
        if h <= hi[0]:
            f = (h - lo[0]) / max(1e-9, hi[0] - lo[0])
            v = lo[1] + f * (hi[1] - lo[1])
            break
        lo = hi
    else:
        v = _DAILY_POINTS[-1][1]
    # 周末整体降约 45%
    if dt.weekday() >= 5:
        v *= 0.55
    return v


def minute_key(dt: datetime) -> str:
    return dt.strftime("%Y%m%d%H%M")


def ip_of(rng: SimRandom) -> str:
    return f"10.{rng.randint(0, 30)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"


def fake_user_ip(rng: SimRandom) -> str:
    """模拟互联网出口 IP（按 region 加权）——演示即可，不回源校验。"""
    if rng.chance(0.72):
        return f"113.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(2, 254)}"
    if rng.chance(0.5):
        return f"202.{rng.randint(0, 100)}.{rng.randint(0, 255)}.{rng.randint(2, 254)}"
    return f"47.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(2, 254)}"


def host_of_service(rng: SimRandom, service: str) -> str:
    hosts = topo.SERVICE_HOSTS.get(service) or topo.NODES
    return rng.choice(hosts)


def region_of_service(rng: SimRandom) -> str:
    return rng.choice(topo.REGIONS)


def trace_token(rng: SimRandom, n: int = 32) -> str:
    """生成 hex 串（用作 trace_id 展示）。实际 trace_id 由 otlp 模块 hex。"""
    return "".join(rng.choice("0123456789abcdef") for _ in range(n))
