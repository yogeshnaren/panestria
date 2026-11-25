"""Read-only loopback snapshot of one observed synthetic demo run.

No credentials, filesystem serving, API proxy, or mutation routes are exposed.
The snapshot does not certify the release gate or constitute owner approval.
"""

from __future__ import annotations

import html
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, cast


def render_report(report: dict[str, Any]) -> bytes:
    def escaped(value: object) -> str:
        return html.escape(str(value))

    status = report["status"]
    artifact = report["artifact"]
    rows = "".join(
        f"<tr><td>{escaped(item['check_key'])}</td><td>{escaped(item['verdict'])}</td></tr>"
        for item in artifact["verdicts"]
    )
    if not rows:
        verification = report.get("verification", {})
        matches = (
            verification.get("artifact_id") == artifact["artifact_id"]
            and verification.get("artifact_sha256") == artifact["sha256"]
        )
        verdict = verification.get("verdict", "UNKNOWN") if matches else "UNKNOWN"
        rows = "<tr><td>Combined required-check result</td><td>" + escaped(verdict) + "</td></tr>"
    approvals = "".join(
        "<article><h3>"
        + escaped(item["label"])
        + "</h3><p>Decision: "
        + escaped(item["receipt"]["state"])
        + "</p><details><summary>View exact approval</summary><pre>"
        + escaped(json.dumps(item, indent=2))
        + "</pre></details></article>"
        for item in report["approvals"]
    )
    events = "".join(
        "<tr><td>"
        + escaped(item["seq"])
        + "</td><td>"
        + escaped(item["kind"])
        + "</td><td><details><summary>View details</summary><pre>"
        + escaped(json.dumps(item["payload"], indent=2))
        + "</pre></details></td></tr>"
        for item in report["events"]["events"]
    )
    result = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Panestria — R0 review</title><style>
:root{font:16px system-ui,sans-serif;color:#17243b;background:#f3f5fa}
body{margin:0}main{max-width:1000px;margin:44px auto;padding:0 24px}
h1{font-size:34px;margin-bottom:8px}h2{font-size:22px}p{line-height:1.6}
section,article{background:white;border:1px solid #dce3ed;border-radius:14px;padding:24px;margin:20px 0}
article{padding:16px}table{width:100%;border-collapse:collapse;text-align:left}
td,th{padding:12px;border-bottom:1px solid #e6eaf1;vertical-align:top}
.status{background:#e0f5e9;color:#175435;display:inline-block;padding:8px 16px;border-radius:24px}
pre{font-size:13px;white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f8fc;padding:14px}
code{overflow-wrap:anywhere}summary{cursor:pointer;color:#245b9d}.muted{color:#516079}
@media(max-width:600px){main{padding:0 12px;margin:20px auto}section{padding:14px}h1{font-size:28px}}
</style><main><p class="muted">Panestria · Local synthetic demo</p><h1>R0 review</h1>
<p>A recorded run of the goal → approval → worker → checks → merge approval → completion journey.</p>
"""
    result += '<section><span class="status">' + escaped(status["status"]) + "</span>"
    result += "<p>Goal: <code>" + escaped(status["goal_id"]) + "</code></p>"
    result += "<p>Observed: " + escaped(report["observed_at"]) + "</p>"
    result += "<p>Demo source commit: <code>" + escaped(report["source_commit"]) + "</code></p>"
    result += "<p>API: " + escaped(report["base_url"]) + "</p></section>"
    result += "<section><h2>Independent checks</h2><table><tr><th>Check</th><th>Result</th></tr>"
    result += rows + "</table><p>Evidence SHA256: <code>" + escaped(artifact["sha256"]) + "</code></p>"
    result += "<p>Artifact: <code>" + escaped(artifact["artifact_id"]) + "</code></p></section>"
    result += "<section><h2>Recorded approvals</h2><p>The demo CLI made these synthetic decisions.</p>"
    result += approvals + "</section><section><h2>Event history</h2><table>"
    result += "<tr><th>Sequence</th><th>Event</th><th>Details</th></tr>" + events + "</table></section>"
    result += "<section><h2>Review scope</h2><p>This page is a read-only snapshot. It does not start "
    result += "new work or record your R0 acceptance. The worker and repository are synthetic; "
    result += "these are actual run results, not an AI research or multi-worker MVP demonstration.</p>"
    result += "<details><summary>View the complete run receipt</summary><pre>"
    result += escaped(json.dumps(report, indent=2)) + "</pre></details></section></main></html>"
    return result.encode()


def review_server(page: bytes, port: int) -> HTTPServer:
    if not 1 <= port <= 65535:
        raise ValueError("review port must be between 1 and 65535")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.headers.get("Host") not in {
                f"127.0.0.1:{cast(HTTPServer, self.server).server_port}",
                f"localhost:{cast(HTTPServer, self.server).server_port}",
            }:
                self.send_error(403)
                return
            if "Origin" in self.headers:
                self.send_error(403)
                return
            if self.path != "/":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; "
                "base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
            )
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, format: str, *args: object) -> None:
            pass

    return HTTPServer(("127.0.0.1", port), Handler)


def serve_report(report: dict[str, Any], port: int) -> None:
    try:
        server = review_server(render_report(report), port)
    except (OSError, ValueError):
        sys.stderr.write("review_port_unavailable: choose another --review-port\n")
        raise SystemExit(2) from None
    with server:
        sys.stderr.write(f"R0 review: http://127.0.0.1:{server.server_port}/ (Ctrl+C to stop)\n")
        sys.stderr.flush()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
