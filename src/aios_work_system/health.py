"""Minimal HTTP health endpoint using only the Python standard library."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from aios_work_system import __version__


class HealthHandler(BaseHTTPRequestHandler):
    """Expose a minimal liveness endpoint without leaking environment details."""

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if self.path != "/health":
            self._write_json(404, {"status": "not_found"})
            return
        self._write_json(200, {"status": "ok", "service": "aios-work-system", "version": __version__})

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """Keep the default HTTP server quiet; structured logging is a later task."""
        return


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the local health server."""
    server = ThreadingHTTPServer((host, port), HealthHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
