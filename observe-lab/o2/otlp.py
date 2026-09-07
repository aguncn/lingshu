"""OTLP protobuf 构造器：把 dict 记录变成可直接 POST 的序列化字节。

只依赖 opentelemetry-proto 提供的消息类型，不引 OTEL SDK。
时间戳一律纳秒；traces 需要 16B trace_id / 8B span_id（本模块自带 id 生成）。
"""
from __future__ import annotations

import hashlib
import os
from typing import Iterable, Optional

from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.proto.common.v1.common_pb2 import InstrumentationScope, KeyValue
from opentelemetry.proto.metrics.v1.metrics_pb2 import (
    Gauge,
    Metric,
    NumberDataPoint,
    ResourceMetrics,
    ScopeMetrics,
    Sum,
)
from opentelemetry.proto.resource.v1.resource_pb2 import Resource
from opentelemetry.proto.trace.v1.trace_pb2 import (
    ResourceSpans,
    ScopeSpans,
    Span,
    Status,
)

_SCOPE_NAME = "observe-lab"
_SCOPE_VERSION = "0.1.0"


def _kv(key: str, value) -> KeyValue:
    kv = KeyValue()
    kv.key = key
    v = kv.value
    if isinstance(value, bool):
        v.bool_value = value
    elif isinstance(value, int):
        v.int_value = value
    elif isinstance(value, float):
        v.double_value = value
    else:
        v.string_value = str(value)
    return kv


def _set_resource(res: Resource, res_attrs: dict):
    for k, v in (res_attrs or {}).items():
        res.attributes.append(_kv(k, v))


# ================================================================ Traces
class SpanRecord:
    """一条待写入的 span（构建时的中间表示）。"""

    __slots__ = ("trace_id", "span_id", "parent_span_id", "name", "kind",
                 "start_ns", "end_ns", "status", "service", "attrs")

    def __init__(self, name: str, *, trace_id: bytes, span_id: bytes,
                 parent_span_id: Optional[bytes] = None, start_ns: int, end_ns: int,
                 kind: int = Span.SPAN_KIND_INTERNAL,
                 status: int = Status.STATUS_CODE_UNSET,
                 service: str = "", attrs: Optional[dict] = None):
        self.name = name
        self.trace_id = trace_id
        self.span_id = span_id
        self.parent_span_id = parent_span_id or b""
        self.start_ns = start_ns
        self.end_ns = end_ns
        self.kind = kind
        self.status = status
        self.service = service
        self.attrs = attrs or {}


def trace_id_hex() -> str:
    return os.urandom(16).hex()


def span_id_hex() -> str:
    return os.urandom(8).hex()


def deterministic_id(raw: str, bits: int = 128) -> bytes:
    """按 raw 字符串生成确定性 id（方便同一种子下 trace/span 可复现）。"""
    return hashlib.sha256(raw.encode("utf-8")).digest()[: bits // 8]


def build_trace_export(spans: Iterable[SpanRecord]) -> bytes:
    """把 SpanRecord 分组进 ResourceSpans(按 service)并序列化。"""
    req = ExportTraceServiceRequest()
    by_service: dict[str, list[SpanRecord]] = {}
    for sp in spans:
        by_service.setdefault(sp.service or "unknown", []).append(sp)
    for svc, srs in by_service.items():
        rs = ResourceSpans()
        _set_resource(rs.resource, {
            "service.name": svc,
            "telemetry.sdk.name": "observe-lab",
        })
        sspans = ScopeSpans()
        sspans.scope.name = _SCOPE_NAME
        sspans.scope.version = _SCOPE_VERSION
        for sr in srs:
            sp = sspans.spans.add()
            sp.trace_id = sr.trace_id
            sp.span_id = sr.span_id
            if sr.parent_span_id:
                sp.parent_span_id = sr.parent_span_id
            sp.name = sr.name
            sp.kind = sr.kind
            sp.start_time_unix_nano = sr.start_ns
            sp.end_time_unix_nano = sr.end_ns
            if sr.status:
                sp.status.code = sr.status
            if sr.status == Status.STATUS_CODE_ERROR:
                sp.status.message = sr.attrs.pop("error.message", "") or "error"
            for k, v in sr.attrs.items():
                sp.attributes.append(_kv(k, v))
        rs.scope_spans.append(sspans)
        req.resource_spans.append(rs)
    return req.SerializeToString()


# ================================================================ Metrics
class MetricPoint:
    """一条指标样本：metric 名即 O2 流名；kind=gauge|sum。"""

    __slots__ = ("name", "kind", "value", "labels", "time_ns", "unit")

    def __init__(self, name: str, kind: str, value: float, *,
                 labels: Optional[dict] = None, time_ns: int, unit: str = ""):
        self.name = name
        self.kind = kind              # 'gauge' | 'sum'
        self.value = value
        self.labels = labels or {}
        self.time_ns = time_ns
        self.unit = unit


def build_metric_export(points: Iterable[MetricPoint]) -> bytes:
    """把 MetricPoint 按 metric 名分组为一个 ResourceMetrics 序列化。"""
    req = ExportMetricsServiceRequest()
    rm = ResourceMetrics()
    _set_resource(rm.resource, {
        "service.name": "ec-observe-lab",
        "telemetry.sdk.name": "observe-lab",
    })
    sm = ScopeMetrics()
    sm.scope.name = _SCOPE_NAME
    sm.scope.version = _SCOPE_VERSION

    grouped: dict[str, list[MetricPoint]] = {}
    for p in points:
        grouped.setdefault(p.name, []).append(p)

    for name, pts in grouped.items():
        m = Metric()
        m.name = name
        m.unit = pts[0].unit or ""
        kind = pts[0].kind
        if kind == "sum":
            m.sum.aggregation_temporality = 2  # CUMULATIVE
            m.sum.is_monotonic = True
            dp_field = m.sum.data_points
        else:
            dp_field = m.gauge.data_points
        for p in pts:
            dp = NumberDataPoint()
            dp.time_unix_nano = p.time_ns
            for k, v in p.labels.items():
                dp.attributes.append(_kv(k, v))
            if isinstance(p.value, float) or isinstance(p.value, int):
                if isinstance(p.value, int) and not isinstance(p.value, bool):
                    dp.as_int = int(p.value)
                else:
                    dp.as_double = float(p.value)
            dp_field.append(dp)
        sm.metrics.append(m)
    rm.scope_metrics.append(sm)
    req.resource_metrics.append(rm)
    return req.SerializeToString()
