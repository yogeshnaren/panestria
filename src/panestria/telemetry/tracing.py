"""Bounded local spans; no body, SQL, headers, paths or exception messages leave here."""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from threading import Lock
from typing import Any

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor, TracerProvider
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

_IDS = {"panestria.goal_id", "panestria.task_id", "panestria.attempt_id", "panestria.project_id", "panestria.owner_id"}
_NUMBERS = {"panestria.epoch", "panestria.input_tokens", "panestria.output_tokens", "http.response.status_code"}
_ENUMS = {
    "panestria.privacy_label": {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "PRIVATE", "UNKNOWN"},
    "panestria.provider": {"local-ollama", "openai-api", "claude-code"},
    "http.request.method": {"GET", "POST", "HEAD", "DELETE", "PATCH"},
}
_HASHES = {"panestria.contract_sha256", "panestria.context_sha256", "panestria.policy_sha256"}
_NAMES = {
    "api.request",
    "kernel.ask",
    "kernel.transaction",
    "inference.local",
    "inference.sdk",
    "worker.adapter",
    "verifier.run",
}
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def safe_attributes(attributes: dict[str, Any]) -> dict[str, str | int]:
    safe: dict[str, str | int] = {}
    for key, value in attributes.items():
        if key in _IDS and isinstance(value, str) and _UUID.fullmatch(value):
            safe[key] = value
        elif key in _NUMBERS and type(value) is int and 0 <= value < 2**63:
            safe[key] = value
        elif key in _ENUMS and isinstance(value, str) and value in _ENUMS[key]:
            safe[key] = value
        elif key in _HASHES and isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value):
            safe[key] = value
    return safe


class MetadataProcessor(SpanProcessor):
    def __init__(self, *, public_sink: Callable[[dict[str, object]], None] | None = None, max_spans: int = 512) -> None:
        if not 1 <= max_spans <= 4096:
            raise ValueError("span_buffer_limit")
        self.records: deque[dict[str, object]] = deque(maxlen=max_spans)
        self.sink, self.failures, self.lock = public_sink, 0, Lock()

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        pass

    def on_end(self, span: ReadableSpan) -> None:
        attributes = safe_attributes(dict(span.attributes or {}))
        label = attributes.setdefault("panestria.privacy_label", "RESTRICTED")
        context = span.context
        if context is None:
            return
        record: dict[str, object] = {
            "name": span.name if span.name in _NAMES else "dbos.operation",
            "trace_id": format(context.trace_id, "032x"),
            "span_id": format(context.span_id, "016x"),
            "parent_span_id": format(span.parent.span_id, "016x") if span.parent else None,
            "attributes": attributes,
            "start_time_ns": span.start_time,
            "end_time_ns": span.end_time,
            "status": span.status.status_code.name,
        }
        with self.lock:
            self.records.append(record)
        # Callback only receives sanitized metadata and only explicitly Public spans.
        # Restricted/Private/Unknown data never reaches an exporter, even on failure.
        if self.sink is not None and label == "PUBLIC":
            try:
                self.sink(record)
            except Exception:
                with self.lock:
                    self.failures += 1

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True

    def snapshot(self) -> list[dict[str, object]]:
        with self.lock:
            return list(self.records)


class Telemetry:
    def __init__(self, processor: MetadataProcessor | None = None) -> None:
        self.processor = processor or MetadataProcessor()
        self.provider = TracerProvider(resource=Resource({"service.name": "panestria"}))
        self.provider.add_span_processor(self.processor)
        self.tracer = self.provider.get_tracer("panestria")

    def install_global(self) -> None:
        current = trace.get_tracer_provider()
        if not isinstance(current, trace.ProxyTracerProvider):
            raise ValueError("existing_telemetry_provider_requires_review")
        trace.set_tracer_provider(self.provider)

    def shutdown(self) -> None:
        self.provider.shutdown()


@contextmanager
def metadata_span(name: str, **attributes: Any) -> Iterator[trace.Span]:
    tracer = trace.get_tracer("panestria")
    with tracer.start_as_current_span(
        name,
        attributes=safe_attributes(attributes),
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        yield span


def current_trace_id() -> str | None:
    context = trace.get_current_span().get_span_context()
    return format(context.trace_id, "032x") if context.is_valid else None


def trusted_context(trace_id: str, parent_span_id: str) -> Context:
    # Internal, persisted capsules only. HTTP middleware never extracts caller IDs.
    if not re.fullmatch(r"[0-9a-f]{32}", trace_id) or not re.fullmatch(r"[0-9a-f]{16}", parent_span_id):
        raise ValueError("trace_capsule_invalid")
    if int(trace_id, 16) == 0 or int(parent_span_id, 16) == 0:
        raise ValueError("trace_capsule_invalid")
    return trace.set_span_in_context(
        NonRecordingSpan(
            SpanContext(
                trace_id=int(trace_id, 16),
                span_id=int(parent_span_id, 16),
                is_remote=True,
                trace_flags=TraceFlags(1),
            )
        )
    )
