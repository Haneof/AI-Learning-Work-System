"""Cheap frame-change detection, timestamped OCR, and inferred cursor tracking."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def _cv_modules() -> tuple[Any, Any]:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "OpenCV and NumPy are required: install the 'video' project extra."
        ) from exc
    return cv2, np


def extract_sampled_frames(
    video_path: str | Path,
    output_dir: str | Path,
    sample_fps: float = 2.0,
    max_width: int = 960,
) -> list[dict[str, Any]]:
    """Decode a local video file to timestamped stills using FFmpeg."""
    if sample_fps <= 0:
        raise ValueError("sample_fps must be positive")
    source = Path(video_path)
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    pattern = target / "frame-%06d.jpg"
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-vf",
        f"fps={sample_fps},scale='min({max_width},iw)':-2",
        "-q:v",
        "3",
        str(pattern),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("FFmpeg is not installed or is not on PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"FFmpeg frame extraction failed: {exc.stderr[-2000:]}") from exc

    frames = []
    for index, path in enumerate(sorted(target.glob("frame-*.jpg"))):
        frames.append(
            {
                "frame_index": index,
                "timestamp_ms": round(index * 1000 / sample_fps),
                "path": str(path),
            }
        )
    if not frames:
        raise RuntimeError("FFmpeg completed but produced no frames")
    return frames


def detect_frame_changes(
    frames: list[dict[str, Any]],
    change_ratio_threshold: float = 0.004,
    mean_difference_threshold: float = 1.8,
    minimum_gap_ms: int = 750,
) -> list[dict[str, Any]]:
    """Compare adjacent sampled frames using cheap grayscale pixel differences."""
    cv2, np = _cv_modules()
    analyzed: list[dict[str, Any]] = []
    previous = None
    last_selected = -minimum_gap_ms

    for frame in frames:
        image = cv2.imread(frame["path"])
        if image is None:
            analyzed.append({**frame, "decode_ok": False, "is_change": False})
            continue
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (320, 180), interpolation=cv2.INTER_AREA)
        if previous is None:
            analyzed.append(
                {
                    **frame,
                    "decode_ok": True,
                    "is_change": False,
                    "is_initial": True,
                    "change_ratio": 0.0,
                    "mean_difference": 0.0,
                    "changed_bbox": None,
                }
            )
            previous = gray
            continue

        difference = cv2.absdiff(previous, gray)
        changed_mask = (difference >= 24).astype("uint8") * 255
        changed_ratio = float(np.count_nonzero(changed_mask)) / float(changed_mask.size)
        mean_difference = float(np.mean(difference))
        is_change = (
            changed_ratio >= change_ratio_threshold
            and mean_difference >= mean_difference_threshold
            and int(frame["timestamp_ms"]) - last_selected >= minimum_gap_ms
        )
        bbox = None
        if is_change:
            contours, _ = cv2.findContours(
                changed_mask,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE,
            )
            candidates = [
                cv2.boundingRect(contour)
                for contour in contours
                if cv2.contourArea(contour) >= 3
            ]
            if candidates:
                x1 = min(item[0] for item in candidates)
                y1 = min(item[1] for item in candidates)
                x2 = max(item[0] + item[2] for item in candidates)
                y2 = max(item[1] + item[3] for item in candidates)
                scale_x = image.shape[1] / 320
                scale_y = image.shape[0] / 180
                bbox = [
                    round(x1 * scale_x),
                    round(y1 * scale_y),
                    round(x2 * scale_x),
                    round(y2 * scale_y),
                ]
                last_selected = int(frame["timestamp_ms"])
        analyzed.append(
            {
                **frame,
                "decode_ok": True,
                "is_change": bool(is_change),
                "is_initial": False,
                "change_ratio": round(changed_ratio, 6),
                "mean_difference": round(mean_difference, 4),
                "changed_bbox": bbox,
            }
        )
        previous = gray

    return analyzed


def select_ocr_frames(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """OCR the initial state and frames where the screen actually changed."""
    return [frame for frame in frames if frame.get("is_initial") or frame.get("is_change")]


def run_ocr(
    frames: list[dict[str, Any]],
    language: str = "eng",
    minimum_confidence: float = 25.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read visible UI text and bounding boxes from selected keyframes with Tesseract."""
    try:
        import pytesseract
        from pytesseract import Output
    except ImportError as exc:
        raise RuntimeError("pytesseract is required: install the 'video' project extra") from exc

    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for frame in select_ocr_frames(frames):
        try:
            data = pytesseract.image_to_data(
                frame["path"],
                lang=language,
                config="--psm 6",
                output_type=Output.DICT,
            )
            regions = []
            for index, raw_text in enumerate(data["text"]):
                text = " ".join(str(raw_text).split())
                try:
                    confidence = float(data["conf"][index])
                except (TypeError, ValueError):
                    confidence = -1.0
                if not text or confidence < minimum_confidence:
                    continue
                regions.append(
                    {
                        "text": text,
                        "confidence": round(confidence / 100, 3),
                        "bbox": {
                            "x": int(data["left"][index]),
                            "y": int(data["top"][index]),
                            "width": int(data["width"][index]),
                            "height": int(data["height"][index]),
                        },
                    }
                )
            records.append(
                {
                    "frame_index": frame["frame_index"],
                    "timestamp_ms": frame["timestamp_ms"],
                    "frame_path": frame["path"],
                    "text": " ".join(item["text"] for item in regions),
                    "regions": regions,
                    "status": "completed",
                }
            )
        except Exception as exc:
            errors.append(
                {
                    "frame_path": frame["path"],
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            records.append(
                {
                    "frame_index": frame["frame_index"],
                    "timestamp_ms": frame["timestamp_ms"],
                    "frame_path": frame["path"],
                    "text": "",
                    "regions": [],
                    "status": "failed",
                }
            )

    report = {
        "status": "completed" if records and not errors else "partial" if records else "failed",
        "frames_processed": len(records),
        "text_regions": sum(len(item["regions"]) for item in records),
        "frames_with_text": sum(bool(item["regions"]) for item in records),
        "errors": errors,
        "language": language,
    }
    return records, report


class CursorTracker:
    """Track visible Windows-style pointer candidates; all detections remain inferred."""

    def __init__(self, confidence_threshold: float = 0.56) -> None:
        self.confidence_threshold = confidence_threshold

    @staticmethod
    def _templates(cv2: Any, np: Any) -> list[Any]:
        templates = []
        for size in (12, 15, 18):
            height = int(size * 1.35)
            template = np.full((height, size), 127, dtype="uint8")
            outer = np.array(
                [
                    [1, 1],
                    [1, height - 3],
                    [size * 0.28, height * 0.66],
                    [size * 0.43, height - 1],
                    [size * 0.62, height * 0.91],
                    [size * 0.47, height * 0.61],
                    [size - 1, height * 0.60],
                ],
                dtype="int32",
            )
            inner = outer.copy()
            inner[:, 0] = np.clip(inner[:, 0] + 2, 0, size - 1)
            inner[:, 1] = np.clip(inner[:, 1] + 2, 0, height - 1)
            cv2.fillPoly(template, [outer], 255)
            cv2.polylines(template, [outer], True, 0, 2)
            cv2.fillPoly(template, [inner], 0)
            templates.append(template)
        return templates

    def track(self, frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Run small multi-scale template matching on sampled frames."""
        cv2, np = _cv_modules()
        templates = self._templates(cv2, np)
        detections: list[dict[str, Any]] = []
        previous = None

        for frame in frames:
            image = cv2.imread(frame["path"])
            if image is None:
                detections.append({**frame, "cursor": None, "cursor_confidence": 0.0})
                continue
            scale = min(1.0, 320 / image.shape[1])
            resized = cv2.resize(
                image,
                (max(1, int(image.shape[1] * scale)), max(1, int(image.shape[0] * scale))),
                interpolation=cv2.INTER_AREA,
            )
            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
            best = None
            for template in templates:
                if template.shape[0] >= gray.shape[0] or template.shape[1] >= gray.shape[1]:
                    continue
                match = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
                _minimum, maximum, _minimum_location, maximum_location = cv2.minMaxLoc(match)
                if best is None or maximum > best["score"]:
                    best = {
                        "score": float(maximum),
                        "x": int((maximum_location[0] + template.shape[1] / 2) / scale),
                        "y": int((maximum_location[1] + template.shape[0] / 2) / scale),
                    }
            cursor = None
            score = best["score"] if best else 0.0
            if best and score >= self.confidence_threshold:
                cursor = {"x": best["x"], "y": best["y"]}
            if cursor and previous and previous.get("cursor"):
                prior = previous["cursor"]
                cursor["movement_px"] = round(
                    ((cursor["x"] - prior["x"]) ** 2 + (cursor["y"] - prior["y"]) ** 2)
                    ** 0.5,
                    1,
                )
            detections.append(
                {
                    **frame,
                    "cursor": cursor,
                    "cursor_confidence": round(score, 3),
                    "cursor_method": "multiscale_arrow_template_match",
                }
            )
            previous = detections[-1]
        return detections


def infer_click_candidates(
    cursor_frames: list[dict[str, Any]],
    proximity_px: int = 140,
) -> list[dict[str, Any]]:
    """Infer possible clicks from pointer settling near a detected screen change."""
    candidates: list[dict[str, Any]] = []
    for current in cursor_frames:
        if not current.get("is_change") or not current.get("cursor"):
            continue
        bbox = current.get("changed_bbox")
        if not bbox:
            continue
        x, y = current["cursor"]["x"], current["cursor"]["y"]
        distance_x = max(bbox[0] - x, 0, x - bbox[2])
        distance_y = max(bbox[1] - y, 0, y - bbox[3])
        distance = (distance_x**2 + distance_y**2) ** 0.5
        if distance > proximity_px:
            continue
        movement = current["cursor"].get("movement_px")
        if movement is None or movement > 45:
            continue
        candidates.append(
            {
                "event_id": f"inferred-click-{len(candidates) + 1:04d}",
                "timestamp_ms": current["timestamp_ms"],
                "event_type": "possible_click",
                "target": {
                    "cursor_x": x,
                    "cursor_y": y,
                    "changed_bbox": bbox,
                },
                "confidence": round(
                    max(0.05, min(0.49, current["cursor_confidence"] * 0.5)),
                    3,
                ),
                "source": "cursor_and_frame_change_heuristic",
                "certainty": "inferred_from_video",
                "warning": (
                    "No click event is present in a downloaded video; "
                    "this is only a visual inference."
                ),
            }
        )
    return candidates
