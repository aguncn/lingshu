"""OpenObserve HTTP 客户端。

统一封装鉴权、时间单位、日志/指标/追踪写入与查询、仪表盘、流管理等。
原则：
- 所有网络错误都转成带中文说明的 O2Error，方便 selftest 和 main 直接给人看。
- 时间单位严格区分：日志 _search 用「微秒」，PromQL 查询用「秒」，OTLP 时间戳用「纳秒」。
"""
from __future__ import annotations

import base64
import json
import time
from typing import Any, Optional

import requests

from . import config as cfg


class O2Error(Exception):
    """OpenObserve 调用失败；message 是给人看的中文说明。"""


# ---------------------------------------------------------------- 时间工具
def now_us() -> int:
    return int(time.time() * 1_000_000)


def now_ns() -> int:
    return int(time.time() * 1_000_000_000)


def us_to_ns(us: int) -> int:
    return us * 1000


def us_to_s(us: int) -> float:
    return us / 1_000_000.0


# ---------------------------------------------------------------- 客户端
class O2Http:
    """针对单个 org 的 OpenObserve HTTP 客户端。"""

    def __init__(self, s: Optional[dict] = None, verbose: Optional[bool] = None):
        s = s or cfg.settings()
        self.base = (s.get("OO_BASE_URL") or "http://localhost:5080").rstrip("/")
        self.org = s.get("OO_ORG") or "default"
        email = s.get("OO_EMAIL") or ""
        pw = s.get("OO_PASSWORD") or ""
        self.timeout = cfg.int_setting(s, "OO_HTTP_TIMEOUT")
        # basic auth: 空格键值对在 basic 里必须 URL 编码（O2 依 RFC7617 解析）
        token = base64.b64encode(
            f"{email}:{pw}".encode("utf-8")
        ).decode("ascii")
        self._auth = {"Authorization": f"Basic {token}"}
        self.verbose = cfg.int_setting(s, "OO_VERBOSE") == 1 if verbose is None else verbose
        self._session = requests.Session()

    # ------------------------------------------------------------ 基础请求
    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"[o2] {msg}")

    def _url(self, path: str) -> str:
        """path 以 /api/... 开头则原样拼接；否则自动补 /api/{org}/。"""
        if path.startswith("/api/") or path.startswith("/rum/"):
            return f"{self.base}{path}"
        return f"{self.base}/api/{self.org}/{path.lstrip('/')}"

    def _request(self, method: str, path: str, *, timeout: Optional[int] = None,
                 headers: Optional[dict] = None, **kw) -> Any:
        url = self._url(path)
        hd = dict(self._auth)
        if headers:
            hd.update(headers)
        try:
            resp = self._session.request(
                method, url, headers=hd, timeout=timeout or self.timeout, **kw
            )
        except requests.RequestException as e:
            raise O2Error(f"连不上 OpenObserve：{url} —— {e}") from e

        body = resp.text or ""
        # 读出响应，便于报错时把后端 message 透出
        try:
            data = resp.json() if body else None
        except ValueError:
            data = None

        if resp.status_code >= 400:
            msg = self._friendly_error(method, path, resp.status_code, body, data)
            raise O2Error(msg)
        if self.verbose:
            self._log(f"{method} {path} -> {resp.status_code} ({len(body)}B)")
        return data if data is not None else body

    @staticmethod
    def _friendly_error(method: str, path: str, code: int, body: str, data) -> str:
        detail = ""
        if isinstance(data, dict):
            for k in ("message", "msg", "error", "detail"):
                v = data.get(k)
                if isinstance(v, str) and v:
                    detail = v
                    break
                if isinstance(v, dict):
                    detail = json.dumps(v, ensure_ascii=False)[:500]
                    break
        elif body:
            detail = body[:500]
        hint = ""
        if "Too old data" in (detail or body):
            hint = "（这是 OpenObserve 默认只允许灌最近 5 小时数据所致：请把服务端环境变量 "
            hint += "ZO_INGEST_ALLOWED_UPTO 调大（如 96）后重启 O2 再跑多天回填，见 docs/02）"
        return f"{method} {path} -> HTTP {code}: {detail or '无返回体'}{hint}"

    # ------------------------------------------------------------ 流与数据写入
    def list_streams(self, stream_type: Optional[str] = None) -> list[dict]:
        """列组织下流；stream_type ∈ {logs, metrics, traces} 可过滤。"""
        path = f"/api/{self.org}/streams"
        params = {"type": stream_type} if stream_type else None
        data = self._session.request(
            "GET", self._url(path), headers=self._auth, params=params,
            timeout=self.timeout,
        )
        if data.status_code >= 400:
            raise O2Error(self._friendly_error("GET", path, data.status_code, data.text, None))
        j = data.json()
        return j.get("streams") or j.get("list") or (j if isinstance(j, list) else [])

    def stream_names(self, stream_type: Optional[str] = None) -> list[str]:
        return [st.get("name") for st in self.list_streams(stream_type)]

    def ingest_logs(self, stream: str, rows: list[dict]) -> dict:
        """JSON 数组灌日志流。rows 需含 _timestamp(微秒)。返回后端响应。"""
        if not rows:
            return {}
        # _json 一次一条数组即一行记录；分批外层做，这里整批传
        data = self._request("POST", f"/api/{self.org}/{stream}/_json", json=rows)
        if isinstance(data, dict) and data.get("status"):
            failed = 0
            for st in data["status"]:
                if isinstance(st, dict):
                    failed += int(st.get("failed") or 0)
            if failed:
                errs = [str(st.get("error")) for st in data["status"]
                        if isinstance(st, dict) and st.get("error")]
                raise O2Error(f"灌入 {stream} 失败 {failed} 条: {errs}")
        return data

    def post_otlp(self, signal: str, payload: bytes, *,
                  stream_name: Optional[str] = None,
                  content_type: str = "application/x-protobuf") -> dict:
        """OTLP protobuf 推送。signal ∈ {traces, metrics, logs}。"""
        headers = {"Content-Type": content_type}
        if stream_name:
            headers["stream-name"] = stream_name
        path = f"/api/{self.org}/v1/{signal}"
        return self._request("POST", path, data=payload, headers=headers)

    # ------------------------------------------------------------ 查询
    def search_sql(self, sql: str, start_us: int, end_us: int, *,
                   size: int = 200, stream_type: Optional[str] = None) -> dict:
        """对日志/追踪流做 SQL 查询，时间单位=微秒。返回原始响应 JSON。"""
        q = {"sql": sql, "start_time": start_us, "end_time": end_us,
             "from": 0, "size": size}
        if stream_type:
            q["query_type"] = stream_type
        body = {"query": q, "size": size}
        return self._request("POST", f"/api/{self.org}/_search", json=body)

    def query_sql(self, sql: str, start_us: int, end_us: int, *,
                  size: int = 200) -> list[dict]:
        """search_sql 后抽出 hit 列表（兼容新旧响应形状）。"""
        data = self.search_sql(sql, start_us, end_us, size=size)
        hits = data.get("hits")
        if isinstance(hits, dict):
            return hits.get("hits") or []
        if isinstance(hits, list):
            return hits
        return []

    def query_promql(self, query: str, start_s: int, end_s: int, step: int = 60) -> list[dict]:
        """PromQL 区间查询，时间单位=秒。返回 series 列表。"""
        params = {"query": query, "start": start_s, "end": end_s, "step": step}
        resp = self._request(
            "GET", f"/api/{self.org}/prometheus/api/v1/query_range",
            params=params,
        )
        return resp.get("data", {}).get("result") or []

    # ------------------------------------------------------------ 流管理（清场/幂等用）
    def delete_stream(self, name: str, stream_type: str) -> bool:
        """尽力删一个流；端点/响应在不同版本不同。返回是否成功(404 视为已删=成功)。"""
        attempts = [
            ("DELETE", f"/api/{self.org}/streams/{name}?stream_type={stream_type}"),
            ("DELETE", f"/api/{self.org}/streams?type={stream_type}&name={name}"),
            ("DELETE", f"/api/{self.org}/streams/{name}"),
        ]
        for method, path in attempts:
            try:
                r = self._session.request(method, self._url(path), headers=self._auth,
                                          timeout=self.timeout)
            except requests.RequestException:
                continue
            if r.status_code == 404:
                return True  # 已不存在 = 达到目的
            if r.status_code < 400:
                return True
        return False

    # ------------------------------------------------------------ 仪表盘
    def list_dashboards(self) -> list[dict]:
        """返回各仪表盘的 v8 内层对象（兼容旧版本无 v8 包装的返回）。"""
        return [d["v8"] if isinstance(d, dict) and d.get("v8") else d
                for d in self._dashboard_raw()]

    def _dashboard_raw(self) -> list[dict]:
        data = self._request("GET", f"/api/{self.org}/dashboards")
        return data.get("dashboards") or data.get("list") or []

    def upsert_dashboard(self, inner: dict) -> dict:
        """按 title 幂等建/更新仪表盘。

        O2 v0.92 的 dashboard v8 面板只有在「后端能严格反序列化」时才会存进去；
        这里直接把完整 v8 内层对象 POST；若同名已存在则 PUT（需带列表返回的 hash）。
        返回说明 dict。任何一步失败抛 O2Error（上层给 UI 手工导入兜底）。
        """
        title = inner.get("title") or ""
        # 1) 同名已存在 → PUT 整体覆盖（带 hash 冲突检测）
        for d in self._dashboard_raw():
            if (d.get("v8") or d).get("title") == title and d.get("v8"):
                did = d.get("dashboard_id")
                hv = d.get("hash")
                body = dict(inner)
                body["dashboardId"] = body.get("dashboardId") or did
                if body.get("dashboardId") != did:
                    body["dashboardId"] = did
                # created 缺省即可（后端有 default）
                params = {"folder": d.get("folder_id") or "default", "hash": hv}
                self._request("PUT", f"/api/{self.org}/dashboards/{did}",
                              params=params, json=body)
                return {"updated": title, "dashboard_id": did}
        # 2) 无同名 → 新建
        resp = self._request("POST", f"/api/{self.org}/dashboards",
                             params={"folder": "default"}, json=inner)
        return {"created": title, "resp": resp}

    def create_dashboard(self, inner: dict) -> dict:
        """用 v8 内层对象建仪表盘（旧入口，保留兼容；新代码请用 upsert_dashboard）。"""
        params = {"folder": "default"}
        return self._request("POST", f"/api/{self.org}/dashboards",
                             params=params, json=inner)

    def delete_dashboard(self, dashboard_id: str) -> bool:
        """删除一张仪表盘。404 视为成功(已不存在)。"""
        try:
            self._request("DELETE", f"/api/{self.org}/dashboards/{dashboard_id}",
                          params={"folder": "default"})
            return True
        except O2Error as e:
            if "404" in str(e) or "not found" in str(e).lower():
                return True
            raise

    # ------------------------------------------------------------ 告警（版本差异大，尽力而为）
    def alert_endpoint_candidates(self, rule: dict) -> list[str]:
        """构造本版本候选告警规则端点，供 create_alert 逐个试。"""
        return [
            f"/api/{self.org}/alerts",              # v2 文件夹化之后的形态
            f"/api/{self.org}/{rule.get('stream_type', 'logs')}/alerts",  # 老形态按流
        ]

    def create_alert(self, rule: dict) -> tuple[bool, str, dict]:
        """建一条告警规则；返回 (是否成功, 说明, 后端响应)。"""
        # 先探测哪个端点存在
        found = None
        for ep in self.alert_endpoint_candidates(rule):
            try:
                self._session.request("GET", self._url(ep), headers=self._auth,
                                      timeout=self.timeout)
                found = ep
                break
            except requests.RequestException:
                continue
        if not found:
            # 直接试老端点建
            return self._try_create_alert(rule)
        return self._try_create_alert(rule, override=found)

    def _try_create_alert(self, rule: dict, override: Optional[str] = None) -> tuple[bool, str, dict]:
        ep = override or rule.get("endpoint") or f"/api/{self.org}/alerts"
        try:
            resp = self._request("POST", ep, json=rule.get("payload", rule))
            return True, f"建告警成功 @ {ep}", resp
        except O2Error as e:
            return False, f"建告警失败 @ {ep}: {e}", {}

    def list_alerts(self) -> list[dict]:
        """尽力列告警；版本不支持时抛错由上层捕获。"""
        for ep in (f"/api/{self.org}/alerts",
                   f"/api/{self.org}/logs/alerts",
                   f"/api/{self.org}/default/alerts"):
            try:
                d = self._request("GET", ep)
                lst = d.get("alerts") or d.get("data") or d.get("list")
                if isinstance(lst, list):
                    return lst
                if isinstance(d, list):
                    return d
            except O2Error:
                continue
        raise O2Error("此版本无公开的告警规则列接口（alerts/*.json 可供 UI 手工建）")
