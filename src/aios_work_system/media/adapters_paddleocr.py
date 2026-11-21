"""Optional PaddleOCR 3.x implementation of the stable OCR adapter contract."""

from __future__ import annotations

import json
import math
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable

from aios_work_system.media.adapters import OCRSegment


def _package_version() -> str:
    try:
        return version("paddleocr")
    except PackageNotFoundError:
        return "not-installed"


class PaddleOCRAdapter:
    """Lazy-load PaddleOCR's PP-OCRv6 pipeline and retain frame-time evidence."""

    name = "paddleocr"

    def __init__(
        self,
        *,
        lang: str = "ch",
        device: str = "cpu",
        model_version: str = "PP-OCRv6",
        text_detection_model_name: str | None = None,
        text_recognition_model_name: str | None = None,
        engine: str | None = None,
        cpu_threads: int = 4,
        min_confidence: float = 0.0,
        ocr_factory: Callable[..., Any] | None = None,
        package_version: str | None = None,
    ) -> None:
        if not lang.strip():
            raise ValueError("lang must not be empty")
        if not device.strip():
            raise ValueError("device must not be empty")
        if model_version not in {"PP-OCRv6", "PP-OCRv5", "PP-OCRv4", "PP-OCRv3"}:
            raise ValueError("unsupported PaddleOCR model version")
        if cpu_threads < 1 or isinstance(cpu_threads, bool):
            raise ValueError("cpu_threads must be a positive integer")
        if (
            isinstance(min_confidence, bool)
            or not math.isfinite(min_confidence)
            or not 0 <= min_confidence <= 1
        ):
            raise ValueError("min_confidence must be between 0 and 1")

        self.lang = lang
        self.device = device
        self.model_version = model_version
        self.text_detection_model_name = text_detection_model_name
        self.text_recognition_model_name = text_recognition_model_name
        self.engine = engine
        self.cpu_threads = cpu_threads
        self.min_confidence = min_confidence
        self._ocr_factory = ocr_factory
        self._package_version = package_version or _package_version()
        self._pipeline: Any | None = None

    @property
    def version(self) -> str:
        return self._package_version

    @property
    def config(self) -> dict[str, Any]:
        return {
            "lang": self.lang,
            "device": self.device,
            "model_version": self.model_version,
            "text_detection_model_name": self.text_detection_model_name,
            "text_recognition_model_name": self.text_recognition_model_name,
            "engine": self.engine,
            "cpu_threads": self.cpu_threads,
            "min_confidence": self.min_confidence,
        }

    def _get_pipeline(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline
        factory = self._ocr_factory
        if factory is None:
            try:
                from paddleocr import PaddleOCR
            except ImportError as exc:
                raise RuntimeError(
                    "PaddleOCR is optional; install with "
                    "pip install 'aios-work-system[ocr]' and install the "
                    "matching PaddlePaddle inference engine"
                ) from exc
            factory = PaddleOCR

        if (self.text_detection_model_name is None) != (
            self.text_recognition_model_name is None
        ):
            raise ValueError(
                "text detection and recognition model names must be provided together"
            )
        kwargs: dict[str, Any] = {
            "device": self.device,
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
            "cpu_threads": self.cpu_threads,
        }
        if self.text_detection_model_name is None:
            kwargs["lang"] = self.lang
            kwargs["ocr_version"] = self.model_version
        else:
            kwargs["text_detection_model_name"] = self.text_detection_model_name
            kwargs["text_recognition_model_name"] = self.text_recognition_model_name
        if self.engine is not None:
            kwargs["engine"] = self.engine
        self._pipeline = factory(**kwargs)
        return self._pipeline

    @staticmethod
    def _result_payload(result: Any) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="aios-paddleocr-") as temp_dir:
            result.save_to_json(temp_dir)
            json_files = sorted(Path(temp_dir).glob("*.json"))
            if len(json_files) != 1:
                raise ValueError(
                    "PaddleOCR result did not produce exactly one JSON result file"
                )
            payload = json.loads(json_files[0].read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("PaddleOCR result JSON must be an object")
        inner = payload.get("res", payload)
        if not isinstance(inner, dict):
            raise ValueError("PaddleOCR result JSON has an invalid res field")
        return inner

    @staticmethod
    def _normalize_box(raw_box: Any) -> list[float] | None:
        try:
            values = raw_box.tolist()
        except AttributeError:
            values = raw_box
        if not isinstance(values, (list, tuple)) or len(values) != 4:
            return None

        try:
            if all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                for value in values
            ):
                return [float(value) for value in values]

            points: list[tuple[float, float]] = []
            for point in values:
                try:
                    coordinates = point.tolist()
                except AttributeError:
                    coordinates = point
                if (
                    not isinstance(coordinates, (list, tuple))
                    or len(coordinates) != 2
                    or any(
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(value)
                        for value in coordinates
                    )
                ):
                    return None
                points.append((float(coordinates[0]), float(coordinates[1])))
        except (TypeError, ValueError, OverflowError):
            return None

        return [
            min(point[0] for point in points),
            min(point[1] for point in points),
            max(point[0] for point in points),
            max(point[1] for point in points),
        ]

    def recognize(self, image_path: Path, timestamp_ms: int) -> list[OCRSegment]:
        source = Path(image_path).expanduser().resolve(strict=True)
        if not source.is_file():
            raise ValueError(f"OCR input is not a file: {source}")
        if (
            isinstance(timestamp_ms, bool)
            or not isinstance(timestamp_ms, int)
            or timestamp_ms < 0
        ):
            raise ValueError("timestamp_ms must be a non-negative integer")

        results = self._get_pipeline().predict(input=str(source))
        output: list[OCRSegment] = []
        for result in results:
            payload = self._result_payload(result)
            texts = payload.get("rec_texts", [])
            boxes = payload.get("rec_boxes", payload.get("rec_polys", []))
            scores = payload.get("rec_scores", [])
            if not isinstance(texts, list):
                raise ValueError("PaddleOCR rec_texts must be a list")
            if not isinstance(boxes, list):
                try:
                    boxes = boxes.tolist()
                except AttributeError as exc:
                    raise ValueError("PaddleOCR text boxes must be a list") from exc
            if not isinstance(scores, list):
                try:
                    scores = scores.tolist()
                except AttributeError:
                    scores = []

            for index, raw_text in enumerate(texts):
                text = str(raw_text).strip()
                if not text:
                    continue
                score: float | None = None
                if index < len(scores):
                    try:
                        candidate_score = float(scores[index])
                    except (TypeError, ValueError):
                        candidate_score = float("nan")
                    if math.isfinite(candidate_score):
                        score = min(1.0, max(0.0, candidate_score))
                if score is not None and score < self.min_confidence:
                    continue

                bbox = (
                    self._normalize_box(boxes[index])
                    if index < len(boxes)
                    else None
                )

                output.append(
                    OCRSegment(
                        timestamp_ms=timestamp_ms,
                        text=text,
                        bounding_box=bbox,
                        confidence=score,
                    )
                )
        return output
