"""Explicit loopback SearXNG transport; no discovery, fallback, cookies or actor tools.

The trusted caller MUST atomically admit/count the query and commit its outbound
disclosure in before_send. This transport never grants permission or declares a
research task complete. Its configured local endpoint is a separate trusted
operator service, not an exception for fetching private search-result URLs.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import socket
import threading
import time
from collections.abc import Callable
from typing import Protocol
from urllib.parse import urlencode, urlsplit

from pydantic import SecretStr, ValidationError

from panestria.brokers.research.fetch import FetchDenied, _HttpSocket, _remaining, https_target
from panestria.contracts.search import (
    LocalSearchSettings,
    SearchCandidate,
    SearchDisclosure,
    SearchQuery,
    SearchResults,
)


class SearchUnavailable(ValueError):
    pass


class SearchProvider(Protocol):
    def search(
        self,
        query: SearchQuery,
        before_send: Callable[[SearchDisclosure], None],
        *,
        cancel: threading.Event | None = None,
    ) -> SearchResults: ...


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_search_json_key")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError("nonfinite_search_json")


class LocalSearxngProvider:
    def __init__(self, settings: LocalSearchSettings) -> None:
        self.settings = LocalSearchSettings.model_validate_json(settings.model_dump_json())

    def search(
        self,
        query: SearchQuery,
        before_send: Callable[[SearchDisclosure], None],
        *,
        cancel: threading.Event | None = None,
    ) -> SearchResults:
        try:
            # JSON serializers redact SecretStr. Revalidate the object and take
            # an immutable plaintext copy only for this authorized wire request.
            query = SearchQuery.model_validate(query)
            text = query.query.get_secret_value()
            settings = self.settings
            body = urlencode({"q": text, "format": "json", "categories": "general", "pageno": "1"}).encode()
            disclosure = SearchDisclosure(
                request_id=query.request_id,
                scope=query.scope,
                provider=settings.provider,
                configuration_sha256=hashlib.sha256(settings.model_dump_json().encode()).hexdigest(),
                request_sha256=hashlib.sha256(body).hexdigest(),
                query_sha256=hashlib.sha256(text.encode()).hexdigest(),
                query_bytes=len(text.encode()),
            )
            stop = cancel if cancel is not None else threading.Event()
            deadline = time.monotonic() + settings.deadline_seconds
            _remaining(deadline, stop)
            before_send(disclosure)  # No socket exists before acknowledged admission/commit.
            _remaining(deadline, stop)
            target = urlsplit(settings.origin)
            family = socket.AF_INET6 if target.hostname == "::1" else socket.AF_INET
            with socket.socket(family, socket.SOCK_STREAM) as connection:
                connection.settimeout(_remaining(deadline, stop))
                assert target.hostname is not None and target.port is not None
                connection.connect((target.hostname, target.port))  # Literal loopback, no DNS/proxy.
                host = f"[{target.hostname}]" if family == socket.AF_INET6 else target.hostname
                headers = (
                    "POST /search HTTP/1.1\r\nHost: "
                    + host
                    + ":"
                    + str(target.port)
                    + "\r\nContent-Type: application/x-www-form-urlencoded\r\nAccept: application/json"
                    + "\r\nAccept-Encoding: identity\r\nConnection: close\r\nContent-Length: "
                    + str(len(body))
                    + "\r\n\r\n"
                ).encode()
                connection.settimeout(_remaining(deadline, stop))
                connection.sendall(headers + body)
                with http.client.HTTPResponse(_HttpSocket(connection, deadline, stop)) as response:  # type: ignore[arg-type]
                    response.begin()
                    if response.status == 403:
                        raise SearchUnavailable("search_json_disabled_or_denied")
                    if response.status == 429:
                        raise SearchUnavailable("search_quota_unavailable")
                    if response.status != 200:
                        raise SearchUnavailable("configured_search_unavailable")
                    if (
                        response.getheader("Content-Type", "").split(";", 1)[0].lower() != "application/json"
                        or response.getheader("Content-Encoding", "identity").lower() != "identity"
                    ):
                        raise SearchUnavailable("search_json_response_required")
                    raw = response.read(settings.max_response_bytes + 1)
            _remaining(deadline, stop)
            if len(raw) > settings.max_response_bytes:
                raise SearchUnavailable("search_response_byte_limit")
            return self._parse(raw, text, disclosure, settings.max_results)
        except SearchUnavailable:
            raise
        except FetchDenied:
            raise SearchUnavailable("search_cancelled_or_deadline") from None
        except (OSError, http.client.HTTPException):
            raise SearchUnavailable("configured_search_transport_unavailable") from None
        except (ValueError, TypeError, UnicodeError, RecursionError, ValidationError):
            raise SearchUnavailable("invalid_search_response_or_request") from None

    def _parse(self, raw: bytes, text: str, disclosure: SearchDisclosure, maximum: int) -> SearchResults:
        data = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
        if not isinstance(data, dict) or data.get("query") != text or not isinstance(data.get("results"), list):
            raise ValueError
        rows = data["results"]
        if len(rows) > 128 or not isinstance(data.get("unresponsive_engines", []), list):
            raise ValueError
        candidates: list[SearchCandidate] = []
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError
            url, title, snippet = row.get("url"), row.get("title", ""), row.get("content", "")
            if type(url) is not str or type(title) is not str or type(snippet) is not str:
                raise ValueError
            try:
                https_target(url)  # Syntax only. Public fetch resolves/checks addresses separately.
                candidate = SearchCandidate(url=SecretStr(url), title=SecretStr(title), snippet=SecretStr(snippet))
            except (FetchDenied, ValidationError):
                continue
            if url not in seen and len(candidates) < maximum:
                seen.add(url)
                candidates.append(candidate)
        return SearchResults(
            disclosure=disclosure,
            response_sha256=hashlib.sha256(raw).hexdigest(),
            candidates=tuple(candidates),
            omitted=len(rows) - len(candidates),
            engine_error_count=len(data.get("unresponsive_engines", [])),
        )
