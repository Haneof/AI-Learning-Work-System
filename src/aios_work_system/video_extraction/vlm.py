"""Qwen3-VL grounding adapter restricted to detected screen-change frames."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_JSON_OBJECT = re.compile(r"\{[\s\S]*\}")


class Qwen3VLGrounder:
    """Load Qwen3-VL once and infer the likely UI target for each changed frame."""

    def __init__(self, model_id: str = "Qwen/Qwen3-VL-2B-Instruct") -> None:
        try:
            import torch
            from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
        except Exception as exc:
            raise RuntimeError(
                f"Qwen3-VL requires torch and transformers>=4.57.0: {type(exc).__name__}: {exc}"
            ) from exc

        self.model_id = model_id
        self.torch = torch
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.model = Qwen3VLForConditionalGeneration.from_pretrained(
            model_id,
            dtype="auto",
            device_map="cpu",
        )
        self.model.eval()

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        match = _JSON_OBJECT.search(text)
        if not match:
            raise ValueError("model response contains no JSON object")
        payload = json.loads(match.group(0))
        if not isinstance(payload, dict):
            raise ValueError("model response JSON must be an object")
        return payload

    def ground(
        self,
        frame_path: str | Path,
        timestamp_ms: int,
        ocr_text: str,
        narration_context: str,
    ) -> dict[str, Any]:
        """Ground one screen-change frame; no unchanged frame is ever passed here."""
        from PIL import Image

        image = Image.open(frame_path).convert("RGB")
        prompt = (
            "You are grounding a UI operation from one frame extracted from a tutorial video. "
            "This frame was selected because a cheap frame-difference detector found a real "
            "screen change. Do not assume a click happened. Identify only what the pixels "
            "support. Use OCR and narration as context, not as proof of a click or a business "
            "rule. Return ONLY a JSON object with keys: visible_ui_element, likely_action, "
            "visible_evidence, cursor_visible (boolean), confidence (0 to 1), uncertainty. "
            "Set likely_action to 'unknown' when the action cannot be grounded. Confidence "
            "must stay below 0.5 when the exact target or action is ambiguous.\n"
            f"Frame timestamp: {timestamp_ms} ms\n"
            f"OCR from this frame: {ocr_text[:1800]}\n"
            f"Nearby instructor narration: {narration_context[:1800]}\n"
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        inputs = self.processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        )
        inputs = inputs.to(self.model.device)
        with self.torch.inference_mode():
            generated = self.model.generate(
                **inputs,
                max_new_tokens=192,
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
        )[0]
        parsed = self._parse_json(response)
        confidence = parsed.get("confidence", 0.0)
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            confidence = 0.0
        confidence = max(0.0, min(1.0, float(confidence)))
        return {
            "status": "completed",
            "model_id": self.model_id,
            "timestamp_ms": timestamp_ms,
            "frame_path": str(frame_path),
            "visible_ui_element": str(parsed.get("visible_ui_element") or "unknown"),
            "likely_action": str(parsed.get("likely_action") or "unknown"),
            "visible_evidence": str(parsed.get("visible_evidence") or ""),
            "cursor_visible": parsed.get("cursor_visible") is True,
            "confidence": confidence,
            "uncertainty": str(parsed.get("uncertainty") or ""),
            "source": "qwen3_vl_changed_frame_grounding",
            "certainty": "inferred_from_video",
            "raw_response": response,
        }
