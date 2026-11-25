"""Deadline and refusal extensions for the pinned HTTP parser, without parsing HTTP ourselves.

A request whose headers do not arrive within ``header_deadline_seconds`` gets
``408 request_deadline_exceeded``; an idle keep-alive connection is closed
without a reply. Malformed HTTP (a bad request line, a negative or conflicting
``Content-Length``, an oversized incomplete event) gets the shared JSON
``400 invalid_request`` envelope instead of the parser's plain-text message, and
nothing from the request is echoed.
"""

from __future__ import annotations

import asyncio
import json

from uvicorn.protocols.http.h11_impl import H11Protocol

from panestria.api.auth import error_body

_REASONS = {400: "Bad Request", 408: "Request Timeout"}


class LocalHttpProtocol(H11Protocol):
    header_deadline_seconds = 5.0
    header_timer: asyncio.TimerHandle | None = None

    def _cancel_header_timer(self) -> None:
        if self.header_timer is not None:
            self.header_timer.cancel()
            self.header_timer = None

    def _arm_header_timer(self) -> None:
        self._cancel_header_timer()
        self.header_timer = self.loop.call_later(self.header_deadline_seconds, self._header_deadline)

    def _header_deadline(self) -> None:
        # Bytes of a new request arrived but never formed a complete header block.
        if self.conn.trailing_data[0]:
            self._refuse(408, "request_deadline_exceeded")
        else:
            self.transport.close()

    def _refuse(self, status: int, code: str) -> None:
        if self.transport.is_closing():
            return
        payload = json.dumps(error_body(code), separators=(",", ":")).encode()
        head = (
            f"HTTP/1.1 {status} {_REASONS[status]}\r\ncontent-type: application/json\r\n"
            f"content-length: {len(payload)}\r\nconnection: close\r\n\r\n"
        )
        self.transport.write(head.encode() + payload)
        self.transport.close()

    def send_400_response(self, msg: str) -> None:
        del msg  # The parser's text may quote the request; send the shared envelope instead.
        self._refuse(400, "invalid_request")

    def connection_made(self, transport: asyncio.Transport) -> None:  # type: ignore[override]
        super().connection_made(transport)
        self._arm_header_timer()

    def handle_events(self) -> None:
        previous = self.cycle
        super().handle_events()
        if self.cycle is not previous:
            self._cancel_header_timer()

    def on_response_complete(self) -> None:
        self._arm_header_timer()
        # The parent can immediately parse a pipelined request; arm first so
        # handle_events can cancel the timer for the newly recognized request.
        super().on_response_complete()

    def connection_lost(self, exc: Exception | None) -> None:
        self._cancel_header_timer()
        super().connection_lost(exc)
