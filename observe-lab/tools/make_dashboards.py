"""生成 OpenObserve v0.92.x 的 v8 电商仪表盘 JSON（dashboards/ec-*.json）。

本文件按 O2 v0.92.2 后端真实接受的 v8 schema 生成（与官方 UI 导出一致）：
  Panel -> config(show_legends…), queryType, queries[];
  Query -> { query: 完整 SQL, vrlFunctionQuery, customQuery, fields{stream,stream_type,x,y,z,breakdown,filter}, config{promql_legend,…} }
早期那种“queries[] 里带 queryType/sql/stream”的旧 v8 在这版后端会被整段丢弃（建出空仪表盘），所以改走上面的结构。

产物既能被 main.py 用 API 建（create/upsert），也能在 O2 界面手动导入。
运行:  uv run python tools/make_dashboards.py    (输出到 dashboards/)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUT = Path(__file__).resolve().parent.parent / "dashboards"
OUT.mkdir(exist_ok=True)


# ---------------------------------------------------------------- 面板/查询构造
def _panel_config(**kw) -> dict:
    cfg = {
        "show_legends": True,
        "legends_position": "bottom",
        "decimals": 2,
        "top_results_others": False,
        "axis_border_show": False,
        "connect_nulls": False,
        "no_value_replacement": "",
        "wrap_table_cells": False,
    }
    cfg.update(kw)
    return cfg


def _query(sql: str, stream: str, stream_type: str = "logs",
           x_agg: str | None = "histogram", y_axis: list | None = None) -> dict:
    """构造一条 SQL 查询。fields 只是编辑器元数据，真正执行的是 query 里的 SQL。"""
    y_axis = y_axis if y_axis is not None else [
        {"label": "Count", "alias": "y_axis_1", "column": "_timestamp", "color": None}]
    x = [{"label": "Time", "alias": "x_axis_1", "column": "_timestamp", "color": None}]
    fields = {
        "stream": stream,
        "stream_type": stream_type,
        "x": x if x_agg else [],
        "y": y_axis,
        "z": [],
        "breakdown": [],
        "filter": {"filterType": "group", "logicalOperator": "AND", "conditions": []},
    }
    return {
        "query": sql,
        "vrlFunctionQuery": "",
        "customQuery": False,
        "fields": fields,
        "config": {"promql_legend": "", "layer_type": "scatter", "weight_fixed": 1,
                   "limit": 0, "min": 0, "max": 100},
    }


def panel(pid: str, ptype: str, title: str, sqls: list[str] | str, stream: str,
          layout: dict, x_agg: str | None = "histogram",
          y_axis: list | None = None) -> dict:
    """通用面板：sqls 可以是单条或多条(多查询叠加)。"""
    if isinstance(sqls, str):
        sqls = [sqls]
    queries = [_query(s, stream, x_agg=x_agg, y_axis=y_axis) for s in sqls]
    return {
        "id": pid, "type": ptype, "title": title, "description": "",
        "config": _panel_config(),
        "queryType": "sql",
        "queries": queries,
        "layout": layout,
        "htmlContent": "", "markdownContent": "",
    }


def table(pid: str, title: str, sql: str, stream: str, layout: dict) -> dict:
    """表格面板：无 x 轴，直接列出原始行。"""
    return panel(pid, "table", title, sql, stream, layout, x_agg=None)


# ---------------------------------------------------------------- 快捷 SQL
def _hist(stream: str, where: str = "", y: str = "count(*) as y_axis_1") -> str:
    """select histogram(_timestamp) as x_axis_1, <y> from "stream" [where] group by x_axis_1 order by x_axis_1"""
    w = f" where {where}" if where else ""
    return (f'select histogram(_timestamp) as x_axis_1, {y} '
            f'from "{stream}"{w} group by x_axis_1 order by x_axis_1')


# ---------------------------------------------------------------- 仪表盘定义
def dash_overview() -> dict:
    """1) 电商全链路总览"""
    panels = [
        panel("ov-req", "line", "访问量趋势（全站 PV，1m 桶）",
              _hist("ec_access_logs", y="count(*) as y_axis_1"),
              "ec_access_logs", dict(x=0, y=0, w=48, h=12, i=1)),
        panel("ov-non2xx", "line", "异常响应趋势（4xx / 5xx）",
              [_hist("ec_access_logs", "status >= 500", "count(*) as y_axis_1"),
               _hist("ec_access_logs", "status >= 400 and status < 500", "count(*) as y_axis_1")],
              "ec_access_logs", dict(x=0, y=12, w=48, h=12, i=2)),
        panel("ov-slow", "line", "网关高延迟请求（>3s，疑似下游抖动）",
              _hist("ec_access_logs", "request_time_ms > 3000", "count(*) as y_axis_1"),
              "ec_access_logs", dict(x=0, y=24, w=24, h=12, i=3)),
        panel("ov-apperr", "line", "应用日志 ERROR / WARN 量",
              [_hist("ec_application_logs", "level = 'ERROR'", "count(*) as y_axis_1"),
               _hist("ec_application_logs", "level = 'WARN'", "count(*) as y_axis_1")],
              "ec_application_logs", dict(x=24, y=24, w=24, h=12, i=4)),
        panel("ov-pv", "line", "RUM 前端 PV 趋势",
              _hist("ec_rum_pageview", y="count(*) as y_axis_1"),
              "ec_rum_pageview", dict(x=0, y=36, w=24, h=12, i=5)),
        panel("ov-js", "line", "前端 JS 报错趋势",
              _hist("ec_rum_error", y="count(*) as y_axis_1"),
              "ec_rum_error", dict(x=24, y=36, w=24, h=12, i=6)),
        table("ov-tb", "最近 ERROR 应用日志",
              'select _timestamp, service, host, level, message from "ec_application_logs" '
              "where level = 'ERROR' order by _timestamp desc limit 20",
              "ec_application_logs", dict(x=0, y=48, w=48, h=14, i=7)),
    ]
    return _doc("E-commerce SRE Overview · 电商全链路总览",
                "observe-lab 生成的电商在线交易总览：流量/错误/前端体验/应用日志。", panels)


def dash_fault() -> dict:
    """2) 故障现场：按故障症状关键词把对应信号拉出来"""
    panels = [
        panel("ft-5xx", "line", "订单/支付 5xx 与 4xx 波动",
              [_hist("ec_access_logs", "status >= 500", "count(*) as y_axis_1"),
               _hist("ec_access_logs", "status >= 400 and status < 500", "count(*) as y_axis_1")],
              "ec_access_logs", dict(x=0, y=0, w=48, h=11, i=1)),
        panel("ft-pool", "line", "F1 连接池耗尽/超时/慢SQL 症状",
              _hist("ec_application_logs",
                    "message like '%pool exhausted%' or message like '%ER_LOCK_WAIT_TIMEOUT%' or message like '%query too slow%'",
                    "count(*) as y_axis_1"),
              "ec_application_logs", dict(x=0, y=11, w=24, h=11, i=2)),
        panel("ft-circuit", "line", "F1 熔断 circuit OPEN",
              _hist("ec_application_logs", "message like '%circuit OPEN%'", "count(*) as y_axis_1"),
              "ec_application_logs", dict(x=24, y=11, w=24, h=11, i=3)),
        panel("ft-kafka", "line", "F3 Kafka 消费积压告警日志",
              _hist("ec_system_logs", "message like '%kafka%lag%'", "count(*) as y_axis_1"),
              "ec_system_logs", dict(x=0, y=22, w=24, h=11, i=4)),
        panel("ft-redis", "line", "F2 Redis 淘汰 / 缓存命中下降",
              _hist("ec_system_logs", "message like '%redis-server%'", "count(*) as y_axis_1"),
              "ec_system_logs", dict(x=24, y=22, w=24, h=11, i=5)),
        panel("ft-rum", "line", "F6 前端 JS 报错 / 资源 404",
              _hist("ec_rum_error", "error_type = 'typeerror' or error_type = 'promise'", "count(*) as y_axis_1"),
              "ec_rum_error", dict(x=0, y=33, w=24, h=11, i=6)),
        panel("ft-404", "line", "F6 静态资源 404（发版 chunk 丢失）",
              _hist("ec_rum_error", "error_type = 'resource'", "count(*) as y_axis_1"),
              "ec_rum_error", dict(x=24, y=33, w=24, h=11, i=7)),
        table("ft-tb", "最近系统级告警日志（WARN/ERROR）",
              'select _timestamp, host, message from "ec_system_logs" '
              "where level in ('WARN','ERROR') order by _timestamp desc limit 20",
              "ec_system_logs", dict(x=0, y=44, w=48, h=13, i=8)),
    ]
    return _doc("E-commerce Fault Scene · 故障现场",
                "故障窗口专用：4xx/5xx、连接池/熔断、Kafka、Redis、前端发版。", panels)


def dash_rum() -> dict:
    """3) RUM 前端体验"""
    panels = [
        panel("rum-pv", "line", "前端 PV 趋势",
              _hist("ec_rum_pageview", y="count(*) as y_axis_1"),
              "ec_rum_pageview", dict(x=0, y=0, w=24, h=12, i=1)),
        panel("rum-err", "line", "JS 报错 / 资源失败趋势",
              [_hist("ec_rum_error", "error_type = 'typeerror' or error_type = 'promise'", "count(*) as y_axis_1"),
               _hist("ec_rum_error", "error_type = 'resource'", "count(*) as y_axis_1")],
              "ec_rum_error", dict(x=24, y=0, w=24, h=12, i=2)),
        panel("rum-lcp", "line", "LCP（最大内容绘制，均值 ms）",
              _hist("ec_rum_pageview", "lcp_ms > 0", "avg(lcp_ms) as y_axis_1"),
              "ec_rum_pageview", dict(x=0, y=12, w=24, h=11, i=3)),
        panel("rum-ttfb", "line", "TTFB（首字节，均值 ms）",
              _hist("ec_rum_pageview", "ttfb_ms > 0", "avg(ttfb_ms) as y_axis_1"),
              "ec_rum_pageview", dict(x=24, y=12, w=24, h=11, i=4)),
        panel("rum-route", "line", "下单页 PV（转化漏斗前端段）",
              _hist("ec_rum_pageview", "route like '%order%'", "count(*) as y_axis_1"),
              "ec_rum_pageview", dict(x=0, y=23, w=24, h=11, i=5)),
        panel("rum-dist", "line", "按发版版本 PV（正常 2.3.9 / 异常 2.4.0）",
              [_hist("ec_rum_pageview", "dist_version = '2.3.9'", "count(*) as y_axis_1"),
               _hist("ec_rum_pageview", "dist_version = '2.4.0'", "count(*) as y_axis_1")],
              "ec_rum_pageview", dict(x=24, y=23, w=24, h=11, i=6)),
        table("rum-tb", "最近前端报错明细",
              'select _timestamp, route, error_type, message from "ec_rum_error" '
              "order by _timestamp desc limit 20",
              "ec_rum_error", dict(x=0, y=34, w=48, h=13, i=7)),
    ]
    return _doc("E-commerce RUM · 前端体验",
                "RUM 前端体验：pageview、JS error、资源 404、LCP/TTFB、发版版本。", panels)


def dash_biz() -> dict:
    """4) 业务与审计"""
    panels = [
        panel("bz-order", "line", "下单请求趋势（POST /api/v1/orders）",
              _hist("ec_access_logs", "path like '%/api/v1/orders%' and method = 'POST'",
                    "count(*) as y_axis_1"),
              "ec_access_logs", dict(x=0, y=0, w=24, h=12, i=1)),
        panel("bz-gateway", "line", "支付/回调路径流量",
              _hist("ec_access_logs", "path like '%/api/v1/payments%' or path like '%/callback%'",
                    "count(*) as y_axis_1"),
              "ec_access_logs", dict(x=24, y=0, w=24, h=12, i=2)),
        panel("bz-rollback", "line", "变更/回滚动作（审计 rollback/ddl）",
              _hist("ec_audit_logs", "action in ('rollback','ddl')", "count(*) as y_axis_1"),
              "ec_audit_logs", dict(x=0, y=12, w=24, h=11, i=3)),
        panel("bz-ops", "line", "运维动作总量（部署/配置/登录）",
              _hist("ec_audit_logs", "action not in ('rollback','ddl')", "count(*) as y_axis_1"),
              "ec_audit_logs", dict(x=24, y=12, w=24, h=11, i=4)),
        table("bz-tb", "最近变更/操作审计",
              'select _timestamp, action, actor, service, detail from "ec_audit_logs" '
              "order by _timestamp desc limit 25",
              "ec_audit_logs", dict(x=0, y=23, w=48, h=13, i=5)),
    ]
    return _doc("E-commerce Biz & Audit · 业务与审计",
                "业务关键动作（下单/支付）+ 审计事件（部署/回滚/变更），配合故障剧本定位变更源头。", panels)


def _doc(title: str, description: str, panels: list) -> dict:
    return {
        "version": 8,
        "dashboardId": "",
        "title": title,
        "description": description,
        "role": "",
        "owner": "",
        "tabs": [{"tabId": "tab_default", "name": "Default", "panels": panels}],
    }


def main() -> None:
    dashs = [("ec-1-overview", dash_overview()),
             ("ec-2-fault", dash_fault()),
             ("ec-3-rum", dash_rum()),
             ("ec-4-biz-audit", dash_biz())]
    for stem, doc in dashs:
        fp = OUT / f"{stem}.json"
        fp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        n = sum(len(t.get("panels") or []) for t in doc["tabs"])
        print(f"✓ {fp.name}  ({len(doc['tabs'])} tab, {n} panels): {doc['title']}")


if __name__ == "__main__":
    main()
