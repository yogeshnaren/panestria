"""Trusted standalone Unix HTTP bridge inside a network-none model container."""

from __future__ import annotations

import http.client
import json
import os
import signal
import socketserver
import subprocess
import time
from http.server import BaseHTTPRequestHandler
from threading import BoundedSemaphore

MODEL = "qwen2.5:1.5b-instruct"
_ALLOWED = {"/api/tags": "GET", "/api/ps": "GET", "/api/generate": "POST", "/api/chat": "POST", "/api/show": "POST"}
_CAPACITY = BoundedSemaphore(1)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, format: str, *args: object) -> None:
        pass  # Request bodies and sensitive paths never enter Docker/host logs.

    def do_GET(self) -> None:
        self.proxy()

    def do_POST(self) -> None:
        self.proxy()

    def proxy(self) -> None:
        self.close_connection = True
        self.connection.settimeout(65)
        if _ALLOWED.get(self.path) != self.command or self.headers.get("Transfer-Encoding"):
            self.send_error(403, "endpoint_denied")
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 <= size <= 32768:
                raise ValueError()
            body = self.rfile.read(size)
            if len(body) != size:
                raise ValueError()
            if self.command == "POST":
                payload = json.loads(body)
                if not isinstance(payload, dict) or payload.get("model") != MODEL:
                    raise ValueError()
                allowed = {"model", "prompt", "messages", "stream", "options", "keep_alive"}
                if self.path == "/api/show":
                    allowed = {"model"}
                if set(payload) - allowed or payload.get("keep_alive", "5m") not in {"5m", 0}:
                    raise ValueError()
                options = payload.get("options", {})
                if set(options) - {"num_ctx", "num_predict", "temperature", "seed", "num_thread", "num_gpu"}:
                    raise ValueError()
                if not 512 <= options.get("num_ctx", 2048) <= 4096:
                    raise ValueError()
                if not 0 <= options.get("num_predict", 128) <= 1024 or options.get("num_thread", 2) != 2:
                    raise ValueError()
                prompt = payload.get("prompt", "")
                if not isinstance(prompt, str) or len(prompt.encode()) > 8192:
                    raise ValueError()
                messages = payload.get("messages", [])
                if not isinstance(messages, list) or len(messages) > 4 or len(json.dumps(messages).encode()) > 8192:
                    raise ValueError()
                if any(
                    set(m) != {"role", "content"} or m["role"] not in {"system", "user", "assistant"} for m in messages
                ):
                    raise ValueError()
        except (ValueError, TypeError, KeyError, OSError):
            self.send_error(400, "request_invalid")
            return
        if not _CAPACITY.acquire(blocking=False):
            self.send_error(429, "model_capacity")
            return
        upstream = http.client.HTTPConnection("127.0.0.1", 11434, timeout=60)
        try:
            upstream.request(self.command, self.path, body=body, headers={"Content-Type": "application/json"})
            response = upstream.getresponse()
            self.send_response(response.status)
            self.send_header("Content-Type", response.getheader("Content-Type", "application/json"))
            self.send_header("Connection", "close")
            self.end_headers()
            total = 0
            # read1 preserves token delivery; read(4096) would buffer short streams.
            while chunk := response.read1(4096):
                total += len(chunk)
                if total > 1024 * 1024:
                    break  # No terminal frame: client must treat this as incomplete.
                self.wfile.write(chunk)
                self.wfile.flush()
        except (OSError, http.client.HTTPException):
            pass  # Broken stream is never rewritten as a completed response.
        finally:
            upstream.close()
            _CAPACITY.release()


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def main() -> None:
    environment = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/tmp",
        "OLLAMA_MODELS": "/models",
        "OLLAMA_HOST": "127.0.0.1:11434",
        "OLLAMA_MAX_LOADED_MODELS": "1",
        "OLLAMA_NUM_PARALLEL": "1",
        "OLLAMA_MAX_QUEUE": "1",
        "OLLAMA_NOHISTORY": "1",
        "OLLAMA_CONTEXT_LENGTH": "2048",
        "LD_LIBRARY_PATH": "/driver:/usr/local/lib/ollama/cuda_v12:/usr/local/lib/ollama",
    }
    child = subprocess.Popen(
        ["/usr/local/bin/ollama", "serve"],
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    def terminate(signum: int, frame: object) -> None:
        child.terminate()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, terminate)
    try:
        deadline = time.monotonic() + 20
        while True:
            connection = http.client.HTTPConnection("127.0.0.1", 11434, timeout=1)
            try:
                connection.request("GET", "/api/tags")
                if connection.getresponse().status == 200:
                    break
            except OSError:
                if child.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("model_start_failed") from None
                time.sleep(0.1)
            finally:
                connection.close()
        socket_path = "/bridge/model.sock"
        if os.path.exists(socket_path):
            os.unlink(socket_path)
        with Server(socket_path, Handler) as server:
            os.chmod(socket_path, 0o600)
            server.serve_forever(poll_interval=0.2)
    finally:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


if __name__ == "__main__":
    main()
