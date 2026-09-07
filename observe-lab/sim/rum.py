"""前端 RUM 生成：ec_rum_pageview / ec_rum_error 两个日志流 + 会话。

真实 SPA 用户会话数据（web vitals、路由、发版版本、JS 报错）。F6 故障在这里放大报错与资源 404。
"""
from __future__ import annotations

from . import rng as R
from .flow import Env
from .rng import SimRandom

_PAGES = [
    ("/", "首页"),
    ("/products/38412", "商品详情"),
    ("/products?category=digital", "商品列表"),
    ("/cart", "购物车"),
    ("/checkout", "结算"),
    ("/orders/20260901093821-88231", "订单详情"),
    ("/user/profile", "个人中心"),
]
_ROUTE_WEIGHT = {"/": 0.34, "/products/38412": 0.16, "/products?category=digital": 0.14,
                 "/cart": 0.12, "/checkout": 0.08, "/orders/20260901093821-88231": 0.06,
                 "/user/profile": 0.10}
_BROWSERS = ["Chrome 126", "Chrome 125", "Safari 17", "Edge 126", "WeChat iOS", "Alipay H5"]
_OS = ["Windows 10", "Android 14", "iOS 17.5", "macOS 14", "HarmonyOS 4"]
_DEV = ["desktop", "mobile", "tablet"]
_CTY = ["北京", "上海", "深圳", "杭州", "广州", "成都", "武汉", "西安"]


def _session(rng: SimRandom) -> str:
    return "sess_" + "".join(rng.choice("0123456789abcdef") for _ in range(16))


def _micro_now(env: Env, rng: SimRandom) -> int:
    return int(env.dt.timestamp() * 1_000_000) + int(rng.uniform(0, 59.9) * 1_000_000)


def _route(rng: SimRandom) -> str:
    tot = sum(_ROUTE_WEIGHT.values())
    r = rng.uniform(0, tot)
    acc = 0.0
    for rt, w in _ROUTE_WEIGHT.items():
        acc += w
        if r <= acc:
            return rt
    return "/"


def generate(env: Env, rng: SimRandom) -> tuple[list[dict], list[dict]]:
    """返回 (pageviews, errors)。pageviews 里每行一个 PV。"""
    f6 = next((f for f in env.faults if f.id == "F6"), None)
    ver = "2.4.0-7f3a" if f6 and f6.intensity_at(env.dt) > 0.1 else "2.3.9"

    n_pv = max(1, int(round(env.web_pv * rng.uniform(0.45, 0.75))))
    pageviews: list[dict] = []
    errors: list[dict] = []
    for _ in range(n_pv):
        route = _route(rng)
        page = dict(_PAGES).get(route, route)
        brow = rng.choice(_BROWSERS)
        # web vital：LCP 以 env.web_lcp_ms 为中枢，异常页更高
        if route in ("/checkout", "/products/38412"):
            lcp = env.web_lcp_ms * rng.uniform(1.0, 1.6)
        else:
            lcp = env.web_lcp_ms * rng.uniform(0.7, 1.2)
        pageviews.append({
            "_timestamp": _micro_now(env, rng),
            "service": "ec-web", "level": "INFO", "app": "ec-web",
            "route": route, "page": page,
            "session_id": _session(rng),
            "user_agent": brow, "browser": brow.split()[0],
            "os": rng.choice(_OS), "device": rng.choice(_DEV),
            "country": "CN", "city": rng.choice(_CTY),
            "lcp_ms": round(lcp, 1), "cls": round(rng.uniform(0, 0.2), 3),
            "inp_ms": round(rng.uniform(20, 220), 1),
            "ttfb_ms": round(rng.uniform(40, 260), 1),
            "domain": "www.ecshop.example.com",
            "dist_version": ver,
            "message": f"pageview {route}",
        })
    # 错误事件：基线低、F6 放大（结算页 + 首页为主）
    if f6:
        a = f6.intensity_at(env.dt)
        n_js = int(round(n_pv * 0.16 * a * rng.uniform(0.7, 1.3)))
        n_res = int(round(n_pv * 0.10 * a * rng.uniform(0.6, 1.2)))
        n_err_total = n_js + n_res
    else:
        n_err_total = 1 if rng.chance(env.web_js_err_rate * 10) else 0
    for _ in range(n_err_total):
        route = _route(rng)
        is_res = bool(f6 and rng.chance(0.4)) or (not f6 and rng.chance(0.2))
        if is_res:
            etype = "resource"
            msg = "Failed to load resource: the server responded with a status of 404 (…/static/js/app.7f3a.chunk.js)"
            fname = "/static/js/app.7f3a.chunk.js"
        else:
            etype = rng.choice(["runtime", "runtime", "promise", "typeerror"])
            fname = rng.choice(["/static/js/checkout.88ab.chunk.js", "/static/js/app.2d4f.js",
                                "/static/js/vendor.90cd.chunk.js"])
            msg = rng.choice([
                "TypeError: Cannot read properties of undefined (reading 'map')",
                "ReferenceError: X is not defined",
                "Uncaught (in promise) TypeError: Cannot read properties of null (reading 'price')",
            ])
        errors.append({
            "_timestamp": _micro_now(env, rng),
            "service": "ec-web", "level": "ERROR", "app": "ec-web",
            "route": route, "page": dict(_PAGES).get(route, route),
            "session_id": _session(rng), "user_agent": rng.choice(_BROWSERS),
            "error_type": etype, "filename": fname, "lineno": rng.randint(8, 512),
            "browser": rng.choice(_BROWSERS).split()[0],
            "country": "CN", "city": rng.choice(_CTY),
            "dist_version": ver, "stack_sample": msg,
            "message": msg,
        })
    return pageviews, errors
