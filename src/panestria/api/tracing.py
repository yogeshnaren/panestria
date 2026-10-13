"""Root trace IDs are server-generated; hostile headers never select a parent's trace."""

from __future__ import annotations

from opentelemetry.context import Context
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from panestria.telemetry.tracing import Telemetry


class TraceRequests:
    def __init__(self, app: ASGIApp, telemetry: Telemetry) -> None:
        self.app, self.telemetry = app, telemetry

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        with self.telemetry.tracer.start_as_current_span(
            "api.request",
            context=Context(),
            attributes={"http.request.method": scope["method"], "panestria.privacy_label": "RESTRICTED"},
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            trace_id = format(span.get_span_context().trace_id, "032x")
            scope.setdefault("state", {})["trace_id"] = trace_id

            async def sending(message: Message) -> None:
                if message["type"] == "http.response.start":
                    span.set_attribute("http.response.status_code", message["status"])
                    message["headers"] = [*message.get("headers", []), (b"x-panestria-trace-id", trace_id.encode())]
                await send(message)

            await self.app(scope, receive, sending)
