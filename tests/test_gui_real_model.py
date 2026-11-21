"""Offline tests for the OpenAI-compatible multimodal GUI model adapter."""

from __future__ import annotations

import asyncio
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from aios_work_system.gui.real_model import (
    API_KEY_ENV,
    BASE_URL_ENV,
    MODEL_ENV,
    ModelConfigurationError,
    ModelResponseError,
    OpenAICompatibleDecisionModel,
)


def _fixture_response(action: dict[str, Any]) -> bytes:
    return json.dumps(
        {"choices": [{"message": {"content": json.dumps(action)}}]},
    ).encode("utf-8")


def test_missing_model_configuration_fails_without_fallback() -> None:
    with pytest.raises(ModelConfigurationError, match=BASE_URL_ENV):
        OpenAICompatibleDecisionModel.from_env({})


def test_invalid_base_url_is_rejected() -> None:
    with pytest.raises(ModelConfigurationError, match=BASE_URL_ENV):
        OpenAICompatibleDecisionModel(
            base_url="file:///not-an-api",
            model_name="local-test-model",
            api_key="unit-test-placeholder",
        )


def test_openai_compatible_multimodal_request_uses_local_fake_endpoint() -> None:
    captured: dict[str, Any] = {}
    action = {
        "action": "type",
        "target": "the Name field",
        "selector": "#name",
        "value": "Ada",
        "expected_result": {
            "kind": "value_equals",
            "selector": "#name",
            "value": "Ada",
        },
    }
    response_body = _fixture_response(action)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            captured["path"] = self.path
            captured["authorization"] = self.headers.get("Authorization")
            captured["payload"] = json.loads(self.rfile.read(length))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        environment = {
            BASE_URL_ENV: f"http://127.0.0.1:{server.server_port}/v1",
            MODEL_ENV: "local-test-model",
            API_KEY_ENV: "unit-test-placeholder",
        }
        model = OpenAICompatibleDecisionModel.from_env(environment)
        request = {
            "objective": "Enter Ada in the Name field",
            "correction": False,
            "history": [],
            "observation": {
                "url": f"http://127.0.0.1:{server.server_port}/index.html",
                "screenshot_b64": base64.b64encode(b"fake-png-bytes").decode("ascii"),
                "dom_snapshot": (
                    '<main><label for="name">Name</label>'
                    '<input id="name" name="name" type="text">'
                    '<button id="save">Save</button></main>'
                    "<script>ignored-secret-looking-node()</script>"
                ),
                "accessibility_snapshot": "main\n  textbox Name\n  button Save",
            },
        }

        decision = asyncio.run(model.decide(request))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert decision == action
    assert captured["path"] == "/v1/chat/completions"
    assert captured["authorization"] == "Bearer unit-test-placeholder"
    payload = captured["payload"]
    assert payload["model"] == "local-test-model"
    assert payload["response_format"] == {"type": "json_object"}
    content = payload["messages"][1]["content"]
    text_part = next(item["text"] for item in content if item["type"] == "text")
    image_part = next(item for item in content if item["type"] == "image_url")
    assert "Name" in text_part
    assert "Save" in text_part
    assert "textbox Name" in text_part
    assert "script" not in text_part
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")


def test_model_action_json_must_satisfy_gui_contract() -> None:
    response_body = json.dumps(
        {"choices": [{"message": {"content": '{"action":"navigate","target":"leave fixture"}'}}]}
    ).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        model = OpenAICompatibleDecisionModel(
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
            model_name="local-test-model",
            api_key="unit-test-placeholder",
        )
        request = {
            "objective": "Do not leave the fixture",
            "observation": {
                "screenshot_b64": base64.b64encode(b"png").decode("ascii"),
                "dom_snapshot": "<main></main>",
                "accessibility_snapshot": "main",
            },
        }
        with pytest.raises(ModelResponseError, match="contract validation"):
            asyncio.run(model.decide(request))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
