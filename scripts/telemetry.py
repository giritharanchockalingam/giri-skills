"""Run telemetry in OpenTelemetry's OTLP/JSON shape: one trace per delivery run, a span per stage, step and model call.

    tr = Tracer(service="deliver", run_id="ab12")
    with tr.span("stage build", stage="build") as s:
        s.set(verdict="pass")
    tr.write(path)          # trace.json, readable by any OTLP/JSON tool
    tr.export()             # POST to $OTEL_EXPORTER_OTLP_ENDPOINT/v1/traces when set (Langfuse, Arize, LangSmith, a collector)

Stdlib only. Export failures are reported, never raised: telemetry must not fail a delivery run.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


def _id(seed: str, n: int) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:n]


def _attr(k: str, v) -> dict:
    if isinstance(v, bool):
        return {"key": k, "value": {"boolValue": v}}
    if isinstance(v, int):
        return {"key": k, "value": {"intValue": str(v)}}
    if isinstance(v, float):
        return {"key": k, "value": {"doubleValue": v}}
    return {"key": k, "value": {"stringValue": str(v)}}


class Span:
    def __init__(self, tracer: "Tracer", name: str, parent: str | None, attrs: dict):
        self.tracer, self.name, self.parent = tracer, name, parent
        self.span_id = _id(f"{tracer.trace_id}:{len(tracer.spans)}:{name}:{time.time_ns()}", 16)
        self.start_ns, self.end_ns, self.attrs, self.error = time.time_ns(), None, dict(attrs), None

    def set(self, **attrs) -> None:
        self.attrs.update({k: v for k, v in attrs.items() if v is not None})

    def otlp(self) -> dict:
        d = {"traceId": self.tracer.trace_id, "spanId": self.span_id, "name": self.name, "kind": 1,
             "startTimeUnixNano": str(self.start_ns), "endTimeUnixNano": str(self.end_ns or time.time_ns()),
             "attributes": [_attr(k, v) for k, v in sorted(self.attrs.items())],
             "status": {"code": 2, "message": self.error[:500]} if self.error else {"code": 1}}
        if self.parent:
            d["parentSpanId"] = self.parent
        return d


class Tracer:
    def __init__(self, service: str, run_id: str, **resource):
        self.service, self.trace_id = service, _id(f"{service}:{run_id}:{time.time_ns()}", 32)
        self.resource = {"service.name": service, "run.id": run_id, **resource}
        self.spans: list[Span] = []
        self._stack: list[Span] = []

    @contextlib.contextmanager
    def span(self, name: str, **attrs):
        s = Span(self, name, self._stack[-1].span_id if self._stack else None, attrs)
        self.spans.append(s)
        self._stack.append(s)
        try:
            yield s
        except BaseException as e:            # recorded, then re-raised: the span shows the failure
            s.error = f"{type(e).__name__}: {e}"
            raise
        finally:
            s.end_ns = time.time_ns()
            self._stack.pop()

    def start(self, name: str, parent: Span | None = None, **attrs) -> Span:
        """An open span (for code that cannot use a `with` block); close it with end()."""
        s = Span(self, name, parent.span_id if parent else (self._stack[-1].span_id if self._stack else None), attrs)
        self.spans.append(s)
        return s

    @staticmethod
    def end(span: Span, error: str | None = None, **attrs) -> None:
        span.set(**attrs)
        span.error = error or span.error
        span.end_ns = time.time_ns()

    def record(self, name: str, start_ns: int, end_ns: int, parent: Span | None = None, **attrs) -> Span:
        """A finished span (a model call measured elsewhere), under `parent` or the current one."""
        s = Span(self, name, parent.span_id if parent else (self._stack[-1].span_id if self._stack else None), attrs)
        s.start_ns, s.end_ns = start_ns, end_ns
        self.spans.append(s)
        return s

    def payload(self) -> dict:
        return {"resourceSpans": [{
            "resource": {"attributes": [_attr(k, v) for k, v in sorted(self.resource.items())]},
            "scopeSpans": [{"scope": {"name": "giri-skills.deliver"}, "spans": [s.otlp() for s in self.spans]}]}]}

    def totals(self) -> dict:
        calls = [s for s in self.spans if s.attrs.get("llm.call")]
        return {"model_calls": len(calls),
                "cost_usd": round(sum(float(s.attrs.get("llm.cost_usd") or 0) for s in calls), 4),
                "input_tokens": sum(int(s.attrs.get("llm.input_tokens") or 0) for s in calls),
                "output_tokens": sum(int(s.attrs.get("llm.output_tokens") or 0) for s in calls)}

    def write(self, path: Path) -> None:
        path.write_text(json.dumps(self.payload(), indent=1) + "\n", encoding="utf-8")

    def export(self, endpoint: str | None = None, headers: str | None = None) -> str:
        """POST OTLP/JSON to <endpoint>/v1/traces. Returns 'exported', 'not configured' or the failure (never raises)."""
        endpoint = endpoint if endpoint is not None else os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
        if not endpoint:
            return "not configured"
        hdrs = {"Content-Type": "application/json"}
        for pair in (headers if headers is not None else os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "")).split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                hdrs[k.strip()] = v.strip()
        url = endpoint.rstrip("/") + ("" if endpoint.rstrip("/").endswith("/v1/traces") else "/v1/traces")
        req = urllib.request.Request(url, data=json.dumps(self.payload()).encode("utf-8"), headers=hdrs, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return f"exported (HTTP {r.status})"
        except (urllib.error.URLError, OSError) as e:
            return f"export failed: {e}"
