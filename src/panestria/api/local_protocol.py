"""Deadline extension for the pinned HTTP parser, without parsing HTTP ourselves."""

from __future__ import annotations

import asyncio

from uvicorn.protocols.http.h11_impl import H11Protocol


class LocalHttpProtocol(H11Protocol):
    header_deadline_seconds = 5.0
    header_timer: asyncio.TimerHandle | None = None

    def _cancel_header_timer(self) -> None:
        if self.header_timer is not None:
            self.header_timer.cancel()
            self.header_timer = None

    def _arm_header_timer(self) -> None:
        self._cancel_header_timer()
        self.header_timer = self.loop.call_later(self.header_deadline_seconds, self.transport.close)

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
