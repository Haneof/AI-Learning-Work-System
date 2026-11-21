"""Contract tests for the OpenAI-compatible llama-server adapter."""

import io
import json
from urllib.error import URLError

import pytest

import aios_work_system.benchmark.llama_server as llama_server
from aios_work_system.benchmark import BenchmarkCase, LlamaServerBackend, LlamaServerError


def _sse_response(*events: dict[str, object] | str) -> io.BytesIO:
    lines: list[str] = []
    for event in events:
        payload = event if isinstance(event, str) else json.dumps(event)
        lines.extend((f"data: {payload}\n".encode(), b"\n"))
    return io.BytesIO(b"".join(lines))


def test_backend_streams_chat_completion_and_records_real_usage(monkeypatch):
    response = _sse_response(
        {"model": "Qwen3.5-4B", "choices": [{"delta": {"role": "assistant"}}]},
        {"choices": [{"delta": {"content": "Hello "}}]},
        {"choices": [{"delta": {"content": "world"}}]},
        {"choices": [], "usage": {"prompt_tokens": 11, "completion_tokens": 2}},
        "[DONE]",
    )
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return response

    monkeypatch.setattr(llama_server, "urlopen", fake_urlopen)
    backend = LlamaServerBackend(
        base_url="http://127.0.0.1:8080/v1/",
        model_id="Qwen3.5-4B",
        timeout=42,
        generation_parameters={"temperature": 0.0, "top_p": 1.0, "max_tokens": 128},
    )
    case = BenchmarkCase(
        case_id="stream-001",
        category="reasoning",
        prompt="Say hello.",
        checks={"mock_response": "this must not be sent"},
    )

    generated = backend.generate(case)

    request = captured["request"]
    assert request.full_url == "http://127.0.0.1:8080/v1/chat/completions"
    payload = json.loads(request.data.decode("utf-8"))
    assert captured["timeout"] == 42
    assert payload["model"] == "Qwen3.5-4B"
    assert payload["messages"] == [{"role": "user", "content": "Say hello."}]
    assert payload["stream"] is True
    assert payload["stream_options"] == {"include_usage": True}
    assert "this must not be sent" not in request.data.decode("utf-8")
    assert generated.text == "Hello world"
    assert generated.input_tokens == 11
    assert generated.output_tokens == 2
    assert generated.time_to_first_token_ms is not None
    assert generated.time_to_first_token_ms >= 0
    assert generated.metadata == {
        "backend_mode": "llama-server",
        "server_model": "Qwen3.5-4B",
        "usage_available": True,
    }


def test_backend_does_not_estimate_tokens_when_server_omits_usage(monkeypatch):
    monkeypatch.setattr(
        llama_server,
        "urlopen",
        lambda request, timeout: _sse_response(
            {"choices": [{"delta": {"content": "A response."}}]},
            "[DONE]",
        ),
    )
    generated = LlamaServerBackend().generate(
        BenchmarkCase(case_id="usage-001", category="test", prompt="Generate.")
    )

    assert generated.text == "A response."
    assert generated.input_tokens is None
    assert generated.output_tokens is None
    assert generated.metadata["usage_available"] is False


def test_backend_reports_connection_errors_with_stable_code(monkeypatch):
    def fail_request(request, timeout):
        raise URLError("server is offline")

    monkeypatch.setattr(llama_server, "urlopen", fail_request)
    backend = LlamaServerBackend()

    with pytest.raises(LlamaServerError, match="CONNECTION_ERROR"):
        backend.generate(
            BenchmarkCase(case_id="offline-001", category="test", prompt="Hello")
        )


def test_backend_rejects_malformed_sse_json(monkeypatch):
    monkeypatch.setattr(
        llama_server,
        "urlopen",
        lambda request, timeout: _sse_response("{not-json"),
    )
    backend = LlamaServerBackend()

    with pytest.raises(LlamaServerError, match="INVALID_RESPONSE"):
        backend.generate(
            BenchmarkCase(case_id="invalid-001", category="test", prompt="Hello")
        )


def test_backend_rejects_invalid_configuration():
    with pytest.raises(ValueError, match="base_url"):
        LlamaServerBackend(base_url="127.0.0.1:8080/v1")
    with pytest.raises(ValueError, match="timeout"):
        LlamaServerBackend(timeout=0)
