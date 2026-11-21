"""OpenAI-compatible streaming adapter for a local llama-server instance."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from aios_work_system.benchmark.types import BenchmarkCase, GenerationOutput


class LlamaServerError(RuntimeError):
    """A stable, actionable error raised by the llama-server adapter."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class LlamaServerBackend:
    """Call llama-server's OpenAI-compatible chat completions endpoint.

    SSE streaming measures time-to-first-token from the start of the HTTP
    request to the first non-empty content delta. Token counts are populated
    only when the server sends a usage object; they are never inferred.
    """

    name = "llama-server"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080/v1",
        model_id: str = "Qwen3.5-4B",
        timeout: float = 300.0,
        generation_parameters: dict[str, Any] | None = None,
    ) -> None:
        normalized_url = base_url.rstrip("/")
        if not normalized_url.startswith(("http://", "https://")):
            raise ValueError("base_url must use http:// or https://")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if not model_id.strip():
            raise ValueError("model_id must not be empty")

        self.base_url = normalized_url
        self.model_id = model_id
        self.timeout = timeout
        self.generation_parameters = dict(generation_parameters or {})

    def generate(self, case: BenchmarkCase) -> GenerationOutput:
        payload: dict[str, Any] = {
            "model": self.model_id,
            "messages": [{"role": "user", "content": case.prompt}],
            "temperature": self.generation_parameters.get("temperature", 0.0),
            "top_p": self.generation_parameters.get("top_p", 1.0),
            "max_tokens": self.generation_parameters.get("max_tokens", 512),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        request = Request(
            url=f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Accept": "text/event-stream",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        started = time.perf_counter()
        first_token_ms: float | None = None
        chunks: list[str] = []
        usage: dict[str, Any] = {}
        response_model: str | None = None

        try:
            with urlopen(request, timeout=self.timeout) as response:
                for event_data in _iter_sse_data(response):
                    if event_data == "[DONE]":
                        break
                    try:
                        event = json.loads(event_data)
                    except json.JSONDecodeError as exc:
                        raise LlamaServerError(
                            "INVALID_RESPONSE", "server returned a malformed SSE JSON event"
                        ) from exc

                    if not isinstance(event, dict):
                        continue
                    if "error" in event:
                        raise LlamaServerError(
                            "SERVER_ERROR", _format_server_error(event["error"])
                        )

                    event_model = event.get("model")
                    if isinstance(event_model, str):
                        response_model = event_model

                    event_usage = event.get("usage")
                    if isinstance(event_usage, dict):
                        usage = event_usage

                    choices = event.get("choices", [])
                    if not isinstance(choices, list) or not choices:
                        continue
                    first_choice = choices[0]
                    if not isinstance(first_choice, dict):
                        continue
                    delta = first_choice.get("delta", {})
                    if not isinstance(delta, dict):
                        continue
                    text_delta = _content_to_text(delta.get("content"))
                    if text_delta:
                        if first_token_ms is None:
                            first_token_ms = (time.perf_counter() - started) * 1000
                        chunks.append(text_delta)
        except HTTPError as exc:
            try:
                detail = exc.read(500).decode("utf-8", errors="replace").strip()
            except OSError:
                detail = ""
            suffix = f": {detail}" if detail else ""
            raise LlamaServerError(
                "HTTP_ERROR", f"llama-server returned HTTP {exc.code}{suffix}"
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise LlamaServerError(
                "CONNECTION_ERROR", f"could not reach {self.base_url}: {exc}"
            ) from exc

        generated_text = "".join(chunks)
        if not generated_text:
            raise LlamaServerError(
                "EMPTY_RESPONSE", "llama-server completed without returning text content"
            )

        input_tokens = _optional_int(usage.get("prompt_tokens"))
        output_tokens = _optional_int(usage.get("completion_tokens"))
        return GenerationOutput(
            text=generated_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            time_to_first_token_ms=first_token_ms,
            metadata={
                "backend_mode": self.name,
                "server_model": response_model,
                "usage_available": bool(usage),
            },
        )


def _iter_sse_data(response: Any) -> Iterator[str]:
    """Yield the data payload from each server-sent event."""
    data_lines: list[str] = []
    for raw_line in response:
        if isinstance(raw_line, bytes):
            line = raw_line.decode("utf-8", errors="replace")
        else:
            line = str(raw_line)
        line = line.rstrip("\r\n")
        if not line:
            if data_lines:
                yield "\n".join(data_lines)
                data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())

    if data_lines:
        yield "\n".join(data_lines)


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            str(item["text"])
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        return "".join(parts)
    return ""


def _optional_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _format_server_error(error: Any) -> str:
    if isinstance(error, dict):
        message = error.get("message") or error.get("type") or "unspecified server error"
        return str(message)[:500]
    return str(error)[:500]
