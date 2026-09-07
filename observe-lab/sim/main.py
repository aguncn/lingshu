"""observe-lab 生成器 CLI。

用法示例：
  python main.py                          # 默认：最近 3 天基线 + F1 live(近 45 分钟) + 能放下的历史故障
  python main.py --days 1 --live-fault F3 # 最近 1 天，F3 打 live(其余历史故障按空间放)
  python main.py --hours 3                # 短窗快速演示（默认 5h 灌入限制内可直接跑）
  python main.py --live-fault none --history none   # 只灌干净基线
  python main.py --purge-own              # 先清掉上次 ec_* 数据再灌（幂等重跑）

时间：--end 默认「当前时间-1min」，--days/--hours 往前推。所有数据为确定性(seeded)。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# 允许以 `python -m sim.main` 与 `python sim/main.py` 两种方式运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows 控制台默认 GBK 打不了 emoji；强制 UTF-8 输出（在 Windows Terminal 里显示正常）
for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from o2 import config as cfg          # noqa: E402
from o2 import otlp                  # noqa: E402
from o2.client import O2Error, O2Http  # noqa: E402
from sim import incidents as inc      # noqa: E402
from sim import logs as L             # noqa: E402
from sim import metrics as M          # noqa: E402
from sim import rum as RUM            # noqa: E402
from sim import traces as T          # noqa: E402
from sim.flow import build_env        # noqa: E402
from sim.rng import SimRandom         # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent

LOG_STREAMS = ["ec_access_logs", "ec_application_logs", "ec_system_logs",
               "ec_audit_logs", "ec_rum_pageview", "ec_rum_error"]


# ---------------------------------------------------------------- 帮助函数
def parse_end(args) -> datetime:
    if args.end:
        try:
            return datetime.strptime(args.end, "%Y-%m-%dT%H:%M")
        except ValueError:
            sys.exit(f"❌ --end 格式不对，示例 2026-09-07T14:30（当前传入 {args.end}）")
    # 默认终点 = 现在(对齐到分钟) -1min，保证灌入的时间都不在未来
    return (datetime.now().replace(second=0, microsecond=0) - timedelta(minutes=1))


def place_faults(chosen: list[str], live_fid: Optional[str], start: datetime, end: datetime) -> tuple[list[inc.Fault], dict]:
    """返回 (已落窗的 Fault 列表, 摘要)。live 的结束对准 end；历史从 end 往前排。"""
    placed: list[inc.Fault] = []
    notes: dict[str, str] = {}

    def put(f: inc.Fault, s: datetime, e: datetime) -> None:
        f.set_window(s, e)
        placed.append(f)
        notes[f.id] = f"{s:%m-%d %H:%M} → {e:%m-%d %H:%M}"

    # 1) live 故障：窗口紧贴 end
    if live_fid and live_fid in chosen:
        f = inc.FAULTS[live_fid]
        put(f, end - f.duration, end)
    # 2) 历史故障：非 live 且被选中的，从 live 之前由近及远排（留 gap 不重叠）
    hist = [fid for fid in chosen if fid != live_fid]
    live = next((f for f in placed if f.id == live_fid), None)
    cursor = (live.start - timedelta(minutes=20)) if live else end
    for fid in inc.ORDER:                       # 固定顺序，保证可复现
        if fid not in hist:
            continue
        f = inc.FAULTS[fid]
        s = cursor - f.duration
        if s >= start:
            put(f, s, cursor)
            cursor = s - timedelta(minutes=20)
        else:
            notes[fid] = "跳过：剩余窗口不足"
    return placed, notes


# ---------------------------------------------------------------- 幂等清场
def purge_own(client: O2Http, s: dict) -> None:
    """只删 ec_* 名下的数据/仪表盘/告警；绝不碰 fin/tel/rum_data 等 legacy。"""
    print("── 清场(仅 ec_* ) ...")
    try:
        for st in client.list_streams():
            name = st.get("name") or ""
            stype = st.get("stream_type") or st.get("type") or "logs"
            if name.startswith("ec_") or name in ("ec_traces",):
                client.delete_stream(name, stype)
                print(f"  删除流 {name} ({stype})")
    except O2Error as e:
        print(f"  列出流失败(可忽略，继续): {e}")
    # 等 O2 异步删除落定：O2 删流后可能残留“空壳”仍列出，所以只等固定时间+尽量早退，
    # 真正挡住“being deleted”的是灌入时的瞬态重试(_retry)，两者配合才幂等。
    gone = False
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            names = [st.get("name") or "" for st in client.list_streams()]
            if not any(n.startswith("ec_") or n == "ec_traces" for n in names):
                gone = True
                break
        except O2Error:
            pass
        time.sleep(2)
    print(f"  删除落定: {'流已清空' if gone else '流列表仍有残留空壳(删除为异步，交由灌入重试兜底)'}")
    # 仪表盘：不删，保留后由 try_dashboards 按同名 upsert 幂等更新（避免删库重建的抖动）
    dts = ("E-commerce", "电商", "ec-")
    try:
        for d in client.list_dashboards():
            t = (d.get("title") or "")
            if any(k in t for k in dts):
                print(f"  保留同名仪表盘(稍后 upsert 幂等更新): {t}")
    except O2Error as e:
        print(f"  列仪表盘失败(可忽略): {e}")


def _transient(e: O2Error) -> bool:
    """是否 O2 删除/创建异步导致的瞬态错误（可重试）。"""
    t = str(e)
    return ("being deleted" in t) or ("being created" in t) or ("still being" in t) or ("deleted stream" in t)


def _retry(fn, tries: int = 12, wait: float = 5.0) -> None:
    """对瞬态(O2 删流异步)错误重试；非瞬态立刻抛。12 次 * 5s 最多拖 ~1 分钟，覆盖删除落定。"""
    last: O2Error | None = None
    for i in range(tries):
        try:
            fn()
            return
        except O2Error as e:
            last = e
            if not _transient(e) or i == tries - 1:
                raise
            time.sleep(wait)


# 日志流「删除中」迟迟不落定的处置指引（本实例实测：删流要先等 O2 后台把该流底层文件清干净，
# 大流需数十分钟；期间流从列表消失、同名仍拒绝写入、报 is being deleted。清理完成后，
# 下一次重启 O2 或 O2 的周期批量才会把「删除中」标记放掉）
WEDGE_HINT = (
    "  OpenObserve 删流是异步的：本实例实测要等后台先把流的底层文件清完(大流数十分钟)才放行，\n"
    "  期间流从列表消失、同名仍拒绝写入。请任选：\n"
    "    1) 演示等不及就别用 --purge-own：直接重跑普通命令(不删流、秒级)即可刷新数据；\n"
    "    2) 想彻底清空：跑 --purge-own 后，若遇 is being deleted，稍等一段时间重跑(删流在后台继续，\n"
    "       重跑不会重置进度)；清理完成后重启 O2 或等周期批量即放行；\n"
    "    3) 超过 1~2 小时仍不落定，才到 O2 界面 Streams 页 / 服务端日志排查删流后台是否异常。"
)


# ---------------------------------------------------------------- 灌入封装
class Pusher:
    def __init__(self, client: O2Http, s: dict):
        self.c = client
        self.batch = cfg.int_setting(s, "OO_BATCH_LOGS")
        self.buf: dict[str, list] = {k: [] for k in LOG_STREAMS}
        self.counts: dict[str, int] = {k: 0 for k in LOG_STREAMS}
        self.metric_buf: list = []
        self.metric_total = 0
        self.span_buf: list = []
        self.span_total = 0
        self.trace_stream = s.get("OO_TRACE_STREAM") or "ec_traces"
        self.err = 0
        self.skip: dict[str, int] = {}  # 各目标连续瞬态跳过次数(成功即清零)，超限=流卡死，终止

    def log(self, stream: str, rows: list[dict]) -> None:
        if not rows:
            return
        b = self.buf[stream]
        b.extend(rows)
        while len(b) >= self.batch:
            chunk = b[:self.batch]
            del b[:self.batch]
            self._push_log(stream, chunk)

    def _push_log(self, stream: str, rows: list[dict]) -> None:
        try:
            # 灌入要能扛住 purge 后 O2 删流的异步窗口（being deleted）：瞬态自动重试
            _retry(lambda: self.c.ingest_logs(stream, rows))
            self.counts[stream] += len(rows)
            self.skip[stream] = 0
        except O2Error as e:
            if _transient(e):
                # 重试耗尽仍瞬态失败 = O2 删流还在落定：连续多次仍不行=卡死，别再空转，明确终止
                self.skip[stream] = self.skip.get(stream, 0) + 1
                print(f"  ! 灌 {stream} 瞬态失败(删流未落定，跳过本批 ×{self.skip[stream]}): {str(e)[:130]}")
                if self.skip[stream] >= 3:
                    sys.exit(f"✗ 日志流 {stream} 连续多次拒绝写入(仍 is being deleted)。\n{WEDGE_HINT}")
                return
            self.err += 1
            print(f"  ✗ 灌 {stream} 失败: {e}")
            if self.err > 6:
                sys.exit("多次灌入失败，终止。请先看上面报错。")

    def metric(self, points: list) -> None:
        self.metric_buf.extend(points)
        self.metric_total += len(points)
        if len(self.metric_buf) >= 220:
            self._push_metric()

    def _push_metric(self) -> None:
        if not self.metric_buf:
            return
        data = self.metric_buf
        self.metric_buf = []
        try:
            _retry(lambda: self.c.post_otlp("metrics", otlp.build_metric_export(data)))
            self.skip["metrics"] = 0
        except O2Error as e:
            if _transient(e):
                self.skip["metrics"] = self.skip.get("metrics", 0) + 1
                print(f"  ! 灌指标瞬态失败(跳过本批 ×{self.skip['metrics']}): {str(e)[:130]}")
                if self.skip["metrics"] >= 3:
                    sys.exit(f"✗ 指标流连续多次拒绝写入(仍 is being deleted)。\n{WEDGE_HINT}")
                return
            self.err += 1
            print(f"  ✗ 灌指标失败: {e}")

    def span(self, spans: list) -> None:
        self.span_buf.extend(spans)
        self.span_total += len(spans)
        if len(self.span_buf) >= 260:
            self._push_span()

    def _push_span(self) -> None:
        if not self.span_buf:
            return
        data = self.span_buf
        self.span_buf = []
        try:
            _retry(lambda: self.c.post_otlp("traces", otlp.build_trace_export(data), stream_name=self.trace_stream))
            self.skip["traces"] = 0
        except O2Error as e:
            if _transient(e):
                self.skip["traces"] = self.skip.get("traces", 0) + 1
                print(f"  ! 灌链路瞬态失败(跳过本批 ×{self.skip['traces']}): {str(e)[:130]}")
                if self.skip["traces"] >= 3:
                    sys.exit(f"✗ 链路流连续多次拒绝写入(仍 is being deleted)。\n{WEDGE_HINT}")
                return
            self.err += 1
            print(f"  ✗ 灌链路失败: {e}")

    def flush(self) -> None:
        for st, rows in self.buf.items():
            if rows:
                self._push_log(st, rows)
                self.buf[st] = []
        self._push_metric()
        self._push_span()


def prime_log_streams(pusher: Pusher, budget_s: int = 4500) -> None:
    """purge 后 O2 删日志流是异步的，且本实例实测按「后台周期批量」落定(一轮可能 ~1 小时)。

    周期内流从列表消失但同名仍拒绝写入(报 is being deleted)，只能等下一轮批量把它一并放掉。
    做法：每个日志流轮询写入 1 条探针行，就绪即记下；全部就绪即提前结束(快时数十秒~几分钟)。
    预算默认 75 分钟≈覆盖一轮完整批量，仍超时则明确终止并给处置指引。
    探针行(service=ec-bootstrap)每流 1 条，不影响核对。
    """
    pending = set(LOG_STREAMS)
    print(f"  预热日志流(等 O2 删流批量落定，预算 {budget_s//60} 分钟；每流就绪写入 1 条探针行)…")
    t0 = time.time()
    last_beat = time.time()
    while pending and time.time() - t0 < budget_s:
        for st in list(pending):
            row = [{"_timestamp": int(time.time() * 1_000_000), "level": "INFO", "service": "ec-bootstrap",
                    "message": f"observe-lab priming {st}"}]
            try:
                pusher.c.ingest_logs(st, row)
                print(f"    ✓ {st} 可写 ({(time.time() - t0):.0f}s)")
                pending.discard(st)
            except O2Error as e:
                if not _transient(e):
                    # 非瞬态(如鉴权/端点错)会一直失败：预热阶段就暴露，别拖到灌入
                    sys.exit(f"✗ 探针 {st} 遇到非瞬态错误(预热阶段即失败，重跑也没意义)。\n   {e}")
        if pending:
            now = time.time()
            if now - last_beat >= 60:  # 每 ~60s 打一次心跳，避免长时间静默
                last_beat = now
                print(f"    … {now - t0:.0f}s 仍等待删流批量落定: {sorted(pending)}")
            time.sleep(5)
    if pending:
        sys.exit(
            f"✗ 预热 {budget_s//60} 分钟仍未见落定(按 O2 删流批量周期判断已属异常)："
            f"{sorted(pending)}。\n{WEDGE_HINT}"
        )


# ---------------------------------------------------------------- 探活回填允许深度
def probe_backfill(client: O2Http, start: datetime, s: dict) -> None:
    """往开始时刻灌一条探针，探测服务端是否允许这么老的数据。"""
    if start > datetime.now() - timedelta(hours=4):
        return  # 远小于默认 5h，无需探
    probe_stream = "ec__probe"
    row = {"_timestamp": int(start.timestamp() * 1_000_000), "probe": 1, "message": "backfill probe"}
    print(f"  探针: 尝试灌入时间点 {start:%Y-%m-%d %H:%M} (判断 ZO_INGEST_ALLOWED_UPTO) ...")
    try:
        client.ingest_logs(probe_stream, [row])
        client.delete_stream(probe_stream, "logs")
        print("  ✓ 服务端允许该时间点的回填")
    except O2Error as e:
        client.delete_stream(probe_stream, "logs")
        sys.exit(
            f"\n✗ OpenObserve 拒绝灌入 {start:%Y-%m-%d %H:%M} 的数据。\n"
            f"   原因: {e}\n\n"
            f"  要在本机做多天回填，请给 O2 服务端放宽历史灌入限制：\n"
            f"   1) 在启动 O2 的 docker-compose/environment 里设  ZO_INGEST_ALLOWED_UPTO=<小时数>（按窗口给 >=120）\n"
            f"   2) 重启 O2 后重跑本脚本。\n"
            f"  只想先看效果：用 --hours 3（在默认最近 5h 内，可直接跑）。"
        )


# ---------------------------------------------------------------- 告警 / 仪表盘（best-effort）
def try_alerts(client: O2Http, placed: list[inc.Fault]) -> None:
    """从 alerts/*.json 逐个尝试建告警；建不了的打印 UI 手工指引，绝不中断。"""
    adir = PROJECT_ROOT / "alerts"
    if not adir.exists():
        print("  (alerts/ 目录不存在，跳过 API 建告警；稍后用 alerts/*.json + UI 手工建)")
        return
    for jf in sorted(adir.glob("*.json")):
        try:
            rule = json.loads(jf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"  ✗ alerts/{jf.name} 解析失败: {e}")
            continue
        ok, msg, _ = client.create_alert(rule)
        if ok:
            print(f"  ✓ 建告警成功: {rule.get('name')}")
        else:
            print(f"  · 告警规则已交付(API 此版本建不了会自动降级 UI 手工建): {jf.name} — {msg}")


def try_dashboards(client: O2Http) -> None:
    ddir = PROJECT_ROOT / "dashboards"
    if not ddir.exists():
        print("  (dashboards/ 目录不存在，跳过 API 建仪表盘)")
        return
    for jf in sorted(ddir.glob("*.json")):
        try:
            inner = json.loads(jf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"  ✗ dashboards/{jf.name} 解析失败: {e}")
            continue
        try:
            r = client.upsert_dashboard(inner)
            if r.get("updated"):
                print(f"  ✓ 更新仪表盘(同名已存在): {r['updated']}")
            else:
                print(f"  ✓ 建仪表盘: {inner.get('title')}")
        except O2Error as e:
            print(f"  · 仪表盘需 UI 手工导入: dashboards/{jf.name} — {e}")


# ---------------------------------------------------------------- 主流程
def main() -> None:
    ap = argparse.ArgumentParser(description="observe-lab 电商模拟数据生成器")
    ap.add_argument("--end", help="结束时刻(含)，如 2026-09-07T14:30；默认=当前-1min")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--days", type=int, default=None, help="回填天数(默认 3)")
    g.add_argument("--hours", type=float, help="回填小时数(短窗快速演示)")
    ap.add_argument("--seed", type=int, default=20260907, help="随机种子")
    ap.add_argument("--faults", default="all", help="故障子集 如 F1,F2 / all / none")
    ap.add_argument("--live-fault", default="F1", help="作为 live(贴现在触发告警)的故障; 默认 F1; none=不要")
    ap.add_argument("--history", default="auto", help="历史故障 none|auto")
    ap.add_argument("--purge-own", action="store_true", help="先清上次 ec_* 再灌")
    ap.add_argument("--verbose", action="store_true", help="打印每条 API 调用")
    args = ap.parse_args()

    s = cfg.settings()
    missing = cfg.check_credentials(s)
    if missing:
        sys.exit("❌ 缺配置项: " + "、".join(missing) +
                 "\n   请先复制 observe-lab/.env.example 为 .env 并填好 OpenObserve 登录账号。")
    client = O2Http(s, verbose=args.verbose)
    end = parse_end(args)
    if args.hours:
        start = end - timedelta(hours=args.hours)
    else:
        start = end - timedelta(days=args.days or 3)

    # 解析要放置的故障：none=纯基线；all=六条；或逗号列表
    if args.faults in (None, "none"):
        chosen = []
    elif args.faults == "all":
        chosen = list(inc.ORDER)
    else:
        chosen = [x.strip() for x in args.faults.split(",") if x.strip() in inc.ORDER]
    live_fid = args.live_fault if args.live_fault in chosen else None
    faults_all, notes = place_faults(chosen, live_fid, start, end)

    print("=" * 72)
    print(f"OpenObserve 电商模拟 · 窗口 {start:%Y-%m-%d %H:%M} → {end:%Y-%m-%d %H:%M}  seed={args.seed}")
    if faults_all:
        print("故障窗口：")
        for f in faults_all:
            print(f"   {f.id} {f.name:<20} {notes.get(f.id,'')}")
    else:
        print("（纯基线，未放置故障）")
    print("=" * 72)

    # 0) 清场（幂等）
    if args.purge_own:
        purge_own(client, s)
    # 0.5) 回填深度探活
    probe_backfill(client, start, s)
    # 0.7) 建仪表盘/告警（best-effort，在灌数据前让规则先就位，便于 live 窗口能触发）
    try_dashboards(client)
    try_alerts(client, faults_all)

    rng = SimRandom(args.seed)
    pusher = Pusher(client, s)
    if args.purge_own:
        prime_log_streams(pusher)
    dt = start
    t0 = time.time()
    minutes = 0
    # 分钟步进
    while dt <= end:
        active = [f for f in faults_all if f.active_at(dt)]
        env = build_env(rng, dt, active)
        # 先出链路(供 access/app 日志引用 trace_id)，再出其余
        spans, pool = T.generate(env, rng)
        acc = L.access_lines(env, rng, pool)
        app = L.application_lines(env, rng, pool)
        sysl = L.system_lines(env, rng)
        aud = L.audit_lines(env, rng, minutes)
        pv, err = RUM.generate(env, rng)
        pusher.log("ec_access_logs", acc)
        pusher.log("ec_application_logs", app)
        pusher.log("ec_system_logs", sysl)
        pusher.log("ec_audit_logs", aud)
        pusher.log("ec_rum_pageview", pv)
        pusher.log("ec_rum_error", err)
        pusher.metric(M.generate(env, rng))
        pusher.span(spans)
        minutes += 1
        if minutes % 60 == 0:
            print(f"  …已生成 {minutes} 分钟 (到 {dt:%H:%M}) "
                  f"日志={sum(pusher.counts.values())} 指标={pusher.metric_total} span={pusher.span_total} "
                  f"耗时={time.time()-t0:.0f}s")
        dt += timedelta(minutes=1)
    pusher.flush()

    print("\n── 灌入统计 ──")
    for st, n in pusher.counts.items():
        print(f"   {st:<24} {n:>8} 条")
    print(f"   metrics(点)              {pusher.metric_total:>8}")
    print(f"   traces(span)             {pusher.span_total:>8}  (流 {pusher.trace_stream})")
    print(f"   共 {minutes} 分钟, 耗时 {time.time()-t0:.0f}s, 错误批次 {pusher.err}")

    # 收尾：抽样核对每个日志流确实可查回
    print("\n── 抽样核对(能查回才算灌成功) ──")
    start_us = int(start.timestamp() * 1_000_000)
    end_us = int(end.timestamp() * 1_000_000)
    for st in LOG_STREAMS:
        try:
            hits = client.query_sql(f'select count(*) as c from "{st}"', start_us, end_us, size=1)
            c = hits[0].get("c") if hits else 0
            print(f"   {st:<24} count={c}")
        except O2Error as e:
            print(f"   {st:<24} 查询失败: {e}")
    try:
        mt = next(iter(pusher.counts), None)
        if mt:
            res = client.query_promql("ec_http_request_rate", int(start.timestamp()), int(end.timestamp()))
            print(f"   ec_http_request_rate 序列数 = {len(res)} (非0说明指标流已可 PromQL 查询)")
    except O2Error as e:
        print(f"   PromQL 核对失败(可忽略): {e}")

    # 写日志
    PROJECT_ROOT.joinpath("main.log").write_text(
        json.dumps({"window": [str(start), str(end)], "seed": args.seed,
                    "minutes": minutes, "log_counts": pusher.counts,
                    "metric_points": pusher.metric_total, "spans": pusher.span_total,
                    "faults": {f.id: [str(f.start), str(f.end)] for f in faults_all}},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n✅ 完成。核对/导入灵枢请按 docs/00-总览与流程.md 继续。")


if __name__ == "__main__":
    main()
