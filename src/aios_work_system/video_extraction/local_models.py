"""Local open-weight model adapters. No hosted inference providers are used."""

from __future__ import annotations

import ast
import json
import re
import time
from pathlib import Path
from typing import Any

SHOWUI_MODEL_ID = "showlab/ShowUI-2B"
UI_TARS_SMALL_MODEL_ID = "ByteDance-Seed/UI-TARS-2B-SFT"
UI_TARS_FALLBACK_MODEL_ID = "ByteDance-Seed/UI-TARS-7B-SFT"
EPISODE_SMALL_MODEL_ID = "2Beyes/Aurum-4B-Uncensored"
EPISODE_FALLBACK_MODEL_ID = "yan2026/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic-GGUF"
EPISODE_SMALL_GGUF_REPO = "2Beyes/Aurum-4B-Uncensored-GGUF"
EPISODE_SMALL_GGUF_NAME = "Aurum-4B-Q4_K_M.gguf"
EPISODE_FALLBACK_GGUF_NAME = "DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic-Q4_K_M.gguf"


class LocalModelUnavailable(RuntimeError):
    """Raised when the requested local model weights or runtime are unavailable."""


def ensure_hf_snapshot(
    repo_id: str,
    local_dir: str | Path,
    *,
    allow_download: bool = False,
) -> Path:
    """Resolve local model weights; optional Hub access downloads weights only."""
    target = Path(local_dir)
    if target.is_dir() and any(target.iterdir()):
        return target
    if not allow_download:
        raise LocalModelUnavailable(
            f"local model files are missing: {target}; "
            "run scripts/download_video_models.py before offline inference"
        )
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise LocalModelUnavailable(
            "huggingface-hub is required to download model weights"
        ) from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(target),
        local_files_only=False,
    )
    if not target.is_dir() or not any(target.iterdir()):
        raise LocalModelUnavailable(f"model download produced no files: {target}")
    return target


def ensure_hf_file(
    repo_id: str,
    filename: str,
    local_path: str | Path,
    *,
    allow_download: bool = False,
) -> Path:
    """Resolve one local GGUF weight file; no hosted inference is performed."""
    target = Path(local_path)
    if target.is_file():
        return target
    if not allow_download:
        raise LocalModelUnavailable(
            f"local GGUF is missing: {target}; "
            "run scripts/download_video_models.py before offline inference"
        )
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise LocalModelUnavailable(
            "huggingface-hub is required to download model weights"
        ) from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    downloaded = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=str(target.parent),
        local_files_only=False,
    )
    downloaded_path = Path(downloaded)
    if downloaded_path.resolve() != target.resolve():
        target.write_bytes(downloaded_path.read_bytes())
    return target


def parse_normalized_point(text: str) -> tuple[float, float] | None:
    """Parse normalized [x,y] output; reject pixel coordinates or malformed output."""
    candidate = str(text).replace(chr(96), "").strip()
    parsed: Any = None
    try:
        parsed = ast.literal_eval(candidate)
    except (ValueError, SyntaxError):
        match = re.search(
            r"\[\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*,\s*"
            r"(-?(?:\d+(?:\.\d*)?|\.\d+))\s*\]",
            candidate,
        )
        if match:
            parsed = [float(match.group(1)), float(match.group(2))]
    if isinstance(parsed, dict):
        parsed = (
            parsed.get("point")
            or parsed.get("position")
            or parsed.get("coordinates")
            or parsed.get("click_point")
        )
    if not isinstance(parsed, (list, tuple)) or len(parsed) < 2:
        return None
    try:
        x, y = float(parsed[0]), float(parsed[1])
    except (TypeError, ValueError):
        return None
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        return None
    return x, y


class _Qwen2VLGrounder:
    """Shared local Qwen2-VL adapter used by ShowUI and UI-TARS model weights."""

    model_id = ""
    license = "Apache-2.0"
    parameter_class = ""
    role = "ui_element_grounding"

    def __init__(self, model_path: str | Path, *, local_files_only: bool = True) -> None:
        path = Path(model_path)
        if not path.is_dir():
            raise LocalModelUnavailable(f"model directory does not exist: {path}")
        try:
            import torch
            from qwen_vl_utils import process_vision_info
            from transformers import AutoProcessor, Qwen2VLForConditionalGeneration
        except Exception as exc:
            raise LocalModelUnavailable(
                "Qwen2-VL grounding requires torch, transformers and qwen-vl-utils: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        self.torch = torch
        self.process_vision_info = process_vision_info
        self.processor = AutoProcessor.from_pretrained(
            str(path),
            min_pixels=256 * 28 * 28,
            max_pixels=1344 * 28 * 28,
            local_files_only=local_files_only,
            trust_remote_code=False,
        )
        model_kwargs: dict[str, Any] = {
            "device_map": "auto",
            "local_files_only": local_files_only,
            "trust_remote_code": False,
            "torch_dtype": "auto",
        }
        # Quantize only the larger fallback when CUDA + bitsandbytes are available.
        if self.parameter_class == "7B" and torch.cuda.is_available():
            try:
                from transformers import BitsAndBytesConfig

                model_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_use_double_quant=True,
                )
            except ImportError:
                pass
        try:
            self.model = Qwen2VLForConditionalGeneration.from_pretrained(
                str(path),
                **model_kwargs,
            )
        except Exception as exc:
            raise LocalModelUnavailable(
                f"failed to load local {self.model_id}: {type(exc).__name__}: {exc}"
            ) from exc
        self.model.eval()

    def ground(
        self,
        frame_path: str | Path,
        timestamp_ms: int,
        target_query: str,
        ocr_text: str,
        narration_context: str,
    ) -> dict[str, Any]:
        """Return a normalized target point for one changed video frame."""
        started = time.perf_counter()
        system = (
            "Locate the single visible UI element described by the target request in this "
            "screenshot. Return ONLY a normalized center coordinate [x, y], where both values "
            "are in the range 0..1 relative to the full screenshot width and height. "
            "Do not return pixel coordinates, explanations, or a click-action claim. "
            "If the target is not visible or you cannot identify it, return []."
        )
        context = (
            f"Frame timestamp: {timestamp_ms} ms\n"
            f"Target request: {target_query}\n"
            f"Visible OCR text (context only): {ocr_text[:2200]}\n"
            f"Nearby instructor narration (context only): {narration_context[:1800]}\n"
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": system},
                    {"type": "image", "image": str(frame_path)},
                    {"type": "text", "text": context},
                ],
            }
        ]
        prompt = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        image_inputs, video_inputs = self.process_vision_info(messages)
        inputs = self.processor(
            text=[prompt],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        ).to(self.model.device)
        with self.torch.inference_mode():
            generated = self.model.generate(
                **inputs,
                max_new_tokens=48,
                do_sample=False,
            )
        trimmed = [
            output[len(source) :]
            for source, output in zip(inputs.input_ids, generated, strict=True)
        ]
        response = self.processor.batch_decode(
            trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0].strip()
        point = parse_normalized_point(response)
        return {
            "status": "completed" if point else "unparsed_or_not_visible",
            "timestamp_ms": int(timestamp_ms),
            "frame_path": str(frame_path),
            "model_id": self.model_id,
            "model_license": self.license,
            "parameter_class": self.parameter_class,
            "point_norm": list(point) if point else None,
            "raw_response": response,
            "target_query": target_query,
            "inference_backend": "transformers_local",
            "local_only": True,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "certainty": "inferred_from_video",
            "likely_action": "target_localization",
        }


class ShowUI2BGrounder(_Qwen2VLGrounder):
    """ShowUI-2B local UI grounding model (MIT)."""

    model_id = SHOWUI_MODEL_ID
    license = "MIT"
    parameter_class = "2B"


class UITARS2BGrounder(_Qwen2VLGrounder):
    """UI-TARS-2B local peer candidate (Apache-2.0)."""

    model_id = UI_TARS_SMALL_MODEL_ID
    license = "Apache-2.0"
    parameter_class = "2B"


class UITARS7BGrounder(_Qwen2VLGrounder):
    """UI-TARS-7B local large fallback (Apache-2.0)."""

    model_id = UI_TARS_FALLBACK_MODEL_ID
    license = "Apache-2.0"
    parameter_class = "7B"


class LocalGGUFDecisionModel:
    """Local llama.cpp GGUF adapter for structured DecisionEpisode JSON generation."""

    def __init__(
        self,
        model_path: str | Path,
        *,
        model_id: str,
        license: str,
        n_ctx: int = 8192,
        n_gpu_layers: int = -1,
    ) -> None:
        self.model_path = Path(model_path)
        if not self.model_path.is_file():
            raise LocalModelUnavailable(f"local GGUF model file does not exist: {self.model_path}")
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise LocalModelUnavailable(
                "llama-cpp-python is required for local GGUF episode synthesis"
            ) from exc
        self.model_id = model_id
        self.license = license
        self.llm = Llama(
            model_path=str(self.model_path),
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            verbose=False,
        )

    def synthesize_decision(
        self,
        *,
        episode_context: dict[str, Any],
        allowed_evidence_ids: list[str],
    ) -> dict[str, Any]:
        """Generate only the decision object; fixed source facts/evidence remain code-owned."""
        system = (
            "You are a local open-weight structured data annotator. Convert the supplied "
            "structured video events and instructor narration into ONE DecisionEpisode v0.1 "
            "decision JSON object. Output JSON only. Do not output Markdown or chain-of-thought.\n"
            "Required keys: decision_type, selected_strategy, rationale_summary, decision_basis, "
            "applicable_conditions, selected_next_step, alternatives_considered, uncertainties, "
            "evidence_refs.\n"
            "Evidence rules:\n"
            "1. A downloaded video has no native click/DOM telemetry. Never call a click observed. "
            "Cursor/click and UI target coordinates are inferred_from_video.\n"
            "2. Visible pixels, OCR and frame changes are observed_from_video. Narration is "
            "instructor_words and is context, not a business rule by itself.\n"
            "3. Do not invent business constraints, mandatory ordering, policy, prices, "
            "commission rules or application state not present in the supplied events.\n"
            "4. Use only the supplied evidence IDs. Do not fabricate evidence references.\n"
            '5. If the operation is uncertain, use decision_basis ["unknown"], say why, '
            'and request human review. Otherwise use ["behavioral_inference"].\n'
            "6. Keep applicable_conditions empty for this video-only example.\n"
            '7. selected_next_step must be {"action":"ask_user","objective":"Review '
            'the proposed interpretation before accepting it"}; question may be included.\n'
            "8. Describe one demonstration, not a universal workflow rule.\n"
            "Return a compact and externally auditable decision object. rationale_summary must "
            "be a short evidence summary, not private reasoning."
        )
        user = {
            "allowed_evidence_ids": allowed_evidence_ids,
            "episode_context": episode_context,
        }
        started = time.perf_counter()
        result = self.llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": json.dumps(user, ensure_ascii=False, separators=(",", ":")),
                },
            ],
            temperature=0.0,
            max_tokens=512,
            response_format={"type": "json_object"},
        )
        content = result["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("local GGUF model returned no text content")
        try:
            decision = json.loads(content)
        except json.JSONDecodeError as exc:
            return {
                "decision": None,
                "raw_response": content,
                "json_parse_valid": False,
                "model_id": self.model_id,
                "model_license": self.license,
                "inference_backend": "llama_cpp_local",
                "local_only": True,
                "generation_attempted": True,
                "generation_output_received": True,
                "parse_error": str(exc),
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "prompt_tokens": result.get("usage", {}).get("prompt_tokens"),
                "completion_tokens": result.get("usage", {}).get("completion_tokens"),
            }
        if not isinstance(decision, dict):
            return {
                "decision": None,
                "raw_response": content,
                "json_parse_valid": False,
                "model_id": self.model_id,
                "model_license": self.license,
                "inference_backend": "llama_cpp_local",
                "local_only": True,
                "generation_attempted": True,
                "generation_output_received": True,
                "parse_error": "model output is not a JSON object",
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "prompt_tokens": result.get("usage", {}).get("prompt_tokens"),
                "completion_tokens": result.get("usage", {}).get("completion_tokens"),
            }
        return {
            "decision": decision,
            "raw_response": content,
            "json_parse_valid": True,
            "model_id": self.model_id,
            "model_license": self.license,
            "inference_backend": "llama_cpp_local",
            "local_only": True,
            "generation_attempted": True,
            "generation_output_received": True,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "prompt_tokens": result.get("usage", {}).get("prompt_tokens"),
            "completion_tokens": result.get("usage", {}).get("completion_tokens"),
        }
