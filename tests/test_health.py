from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from aios_work_system.health import HealthHandler


def test_health_endpoint_returns_service_status() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/health") as response:
            payload = json.loads(response.read())
            assert response.status == 200
            assert payload["status"] == "ok"
            assert payload["service"] == "aios-work-system"
            assert "version" in payload
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_unknown_route_returns_404() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/unknown")
            raise AssertionError("expected HTTPError")
        except urllib.error.HTTPError as error:
            assert error.code == 404
            assert json.loads(error.read())["status"] == "not_found"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
