"""observe-lab 自检：验 .env 连接 + 逐项探活 OpenObserve 能力。

用法：
  uv run --project observe-lab python selftest.py [--verbose] [--oldest 2026-09-04T00:00]

逐项输出 PASS / WARN / FAIL 与修复指引；同时把结论写到 .cache/capabilities.json，
供后续生成/文档按实际能力取用（例如 trace 流名、告警端点、是否允许老数据回填）。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Windows 控制台默认 GBK 打不了 emoji；强制 UTF-8 输出（在 Windows Terminal 里显示正常）
for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from o2 import config as cfg          # noqa: E402
from o2 import otlp                  # noqa: E402
from o2.client import O2Error, O2Http  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent


def _auth_headers(s: dict) -> dict:
    import base64
    token = base64.b64encode(f"{s['OO_EMAIL']}:{s['OO_PASSWORD']}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--oldest", help="额外探测：尝试灌入该历史时刻，判断服务端回填上限 如 2026-09-04T00:00")
    args = ap.parse_args()

    s = cfg.settings()
    missing = cfg.check_credentials(s)
    if missing:
        sys.exit("❌ 缺配置项: " + "、".join(missing) +
                 "\n   请复制 observe-lab/.env.example 为 .env，填入你的 OpenObserve 登录邮箱/密码。")
    c = O2Http(s, verbose=args.verbose)
    base, org = c.base, c.org
    results: list[dict] = []
    ok = {"PASS": 0, "WARN": 0, "FAIL": 0}

    def rec(name: str, status: str, detail: str):
        results.append({"name": name, "status": status, "detail": detail})
        ok[status] += 1
        mark = {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌"}[status]
        print(f"{mark} {name:<26} {detail}")

    print("=" * 72)
    print(f"OpenObserve 自检 → {base}  org={org}")
    print("=" * 72)

    # 1) 连接与鉴权
    try:
        streams = c.stream_names()
        rec("连接 + 登录鉴权", "PASS", f"GET /api/{org}/streams 成功，当前已有 {len(streams)} 个流")
    except O2Error as e:
        rec("连接 + 登录鉴权", "FAIL", str(e)[:200] + " → 请检查 OO_BASE_URL/OO_EMAIL/OO_PASSWORD")
        print("\n鉴权失败，中止其余探测。")
        _dump(results)
        sys.exit(1)

    # 2) 版本
    try:
        import requests
        r = requests.get(f"{base}/api/version", headers=_auth_headers(s), timeout=10)
        ver = r.json().get("version", "?") if r.status_code == 200 else f"HTTP {r.status_code}"
        rec("服务端版本", "PASS" if r.status_code == 200 else "WARN", ver)
    except Exception as e:
        rec("服务端版本", "WARN", f"取版本失败: {e}")

    # 3) 日志写入路径（_json）—— 用唯一探针流名，避免 O2 删除是异步的、同名的会撞上“being deleted”
    probe = "ec__probe_" + f"{time.time_ns():x}"[-6:]
    try:
        row = [{"_timestamp": int(time.time() * 1_000_000), "level": "INFO", "message": "selftest probe",
                "service": "ec-probe"}]
        c.ingest_logs(probe, row)
        rec("日志 _json 写入", "PASS", f"POST /{probe}/_json ok")
        # 查回
        try:
            hits = c.query_sql(f'select count(*) as c from "{probe}"',
                               int(time.time() * 1e6) - 120_000_000, int(time.time() * 1e6) + 1, size=1)
            got = hits[0].get("c") if hits else 0
            rec("日志可查回(_search/us)", "PASS" if got else "WARN", f"count={got}")
        except O2Error as e:
            rec("日志可查回(_search/us)", "WARN", str(e)[:160])
    except O2Error as e:
        rec("日志 _json 写入", "FAIL", str(e)[:240])
    finally:
        c.delete_stream(probe, "logs")

    def _docs(stream: str, stype: str):
        try:
            for st in c.list_streams(stype):
                if st.get("name") == stream:
                    return (st.get("stats") or {}).get("doc_num")
        except O2Error:
            pass
        return None

    # 4) OTLP 链路写入（本版本 OTLP 一律落 type=traces 的 default 流；SQL 不可直查 trace）
    trace_stream = s.get("OO_TRACE_STREAM") or "default"
    try:
        now = int(time.time())
        d0 = _docs(trace_stream, "traces")
        root = otlp.SpanRecord("selftest /probe", trace_id=otlp.deterministic_id("st-root", 128),
                               span_id=otlp.deterministic_id("st-s", 64),
                               start_ns=int(now * 1e9) - 2_000_000_000,
                               end_ns=int(now * 1e9) - 1_000_000_000,
                               kind=2, service="ec-probe",
                               attrs={"http.status_code": 200})
        c.post_otlp("traces", otlp.build_trace_export([root]), stream_name=trace_stream)
        time.sleep(2)
        d1 = _docs(trace_stream, "traces")
        delta = "" if d0 is None or d1 is None else f" doc 数 {d0}→{d1}"
        rec("OTLP 链路写入", "PASS",
            f"推送成功(流 {trace_stream}, service_name=ec-*) {delta}；SQL 不可直查 trace，命中请在 Traces 页/MCP GetLatestTraces 核对")
    except O2Error as e:
        rec("OTLP 链路写入", "FAIL", str(e)[:240])

    # 5) OTLP 指标写入 + PromQL 可查
    mname = "ec_probe_metric"
    try:
        now = int(time.time())
        c.post_otlp("metrics", otlp.build_metric_export([otlp.MetricPoint(
            mname, "gauge", 7.7, labels={"service": "ec-probe"}, time_ns=int(now * 1e9))]))
        time.sleep(2)
        try:
            res = c.query_promql(mname, now - 300, now + 30)
            n = len(res)
            rec("OTLP 指标写入", "PASS" if n else "WARN",
                f"PromQL query_range 序列数={n}" + (f" 值={res[0]['values'][-1][1]}" if n else ""))
        except O2Error as e:
            rec("OTLP 指标写入", "WARN", f"PromQL 查回失败: {e}")
    except O2Error as e:
        rec("OTLP 指标写入", "FAIL", str(e)[:240])
    finally:
        c.delete_stream(mname, "metrics")

    # 6) 原生 MCP 可达性
    try:
        import requests
        url = f"{base}/api/{org}/mcp"
        r = requests.get(url, headers=_auth_headers(s), timeout=10,
                         stream=True, params={"protocolVersion": "2025-11-25", "capabilities": "{}"})
        body_head = ""
        try:
            for ln in r.iter_lines(decode_unicode=True):
                body_head = (body_head + ln)[:160]
                if ln.startswith("data:"):
                    break
        except Exception:
            pass
        rec("原生 MCP 端点", "PASS" if r.status_code == 200 else "FAIL",
            f"GET /api/{org}/mcp → HTTP {r.status_code} {body_head[:120]}")
    except Exception as e:
        rec("原生 MCP 端点", "FAIL", f"{e} → 若本版本无原生 MCP，文档给 stdio community 兜底方案")

    # 7) 告警端点形态探测（试列）
    try:
        lst = c.list_alerts()
        rec("告警规则列接口", "PASS", f"GET /api/{org}/alerts → {len(lst)} 条")
    except O2Error as e:
        rec("告警规则列接口", "WARN", str(e)[:200])

    # 8) 仪表盘列接口
    try:
        ds = c.list_dashboards()
        rec("仪表盘接口", "PASS", f"GET /api/{org}/dashboards → {len(ds)} 张")
    except O2Error as e:
        rec("仪表盘接口", "FAIL", str(e)[:200])

    # 9) 历史回填深度（服务端 ZO_INGEST_ALLOWED_UPTO）
    def _probe_old(dt_old: datetime, label: str):
        try:
            c.ingest_logs(probe, [{"_timestamp": int(dt_old.timestamp() * 1e6), "old": 1}])
            c.delete_stream(probe, "logs")
            return True, f"{label}: 服务端允许灌入 {dt_old:%m-%d %H:%M} 的老数据"
        except O2Error as e:
            c.delete_stream(probe, "logs")
            if "Too old" in str(e) or "ZO_INGEST_ALLOWED_UPTO" in str(e):
                return False, (f"{label}: 只允许最近 ~5h（服务端默认）。要回填更多天，请在 O2 启动环境设 "
                               "ZO_INGEST_ALLOWED_UPTO=120 并重启（见 docs/02）")
            if "being deleted" in str(e):
                return True, f"{label}: 探针流正在删除，跳过（不影响回填判断）"
            return False, f"{label}: {str(e)[:160]}"

    okb, detb = _probe_old(datetime.now() - timedelta(hours=6), "回填6h")
    rec("回填深度 6h 探测", "PASS" if okb else "WARN", detb)
    if args.oldest:
        try:
            dt_old = datetime.strptime(args.oldest, "%Y-%m-%dT%H:%M")
        except ValueError:
            sys.exit("--oldest 格式应为 2026-09-04T00:00")
        oko, deto = _probe_old(dt_old, f"回填 {args.oldest}")
        rec("指定历史点回填", "PASS" if oko else "WARN", deto)

    print("=" * 72)
    print(f"自检结论：PASS {ok['PASS']}  WARN {ok['WARN']}  FAIL {ok['FAIL']}")
    need_env = any("ZO_INGEST_ALLOWED_UPTO" in r["detail"] for r in results)
    if ok["FAIL"]:
        print("存在 FAIL：按上方指引修复后重跑；WARN 多属能力差异，不影响继续。")
    else:
        print("核心能力全绿：可以跑数据生成了（python sim/main.py --help 看选项）。")
    if need_env:
        print("提示：探测到历史回填被服务端默认限制（最近 5h）。要多天回填，请先设 "
              "ZO_INGEST_ALLOWED_UPTO 并重启 O2（见 docs/02）；最近几小时窗口可直接生成。")
    _dump(results)


def _dump(results: list[dict]):
    capdir = PROJECT_ROOT / ".cache"
    capdir.mkdir(exist_ok=True)
    (capdir / "capabilities.json").write_text(
        json.dumps({"probed_at": datetime.now().isoformat(timespec="seconds"),
                    "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
