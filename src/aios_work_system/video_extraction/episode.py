"""Align timestamped narration and build auditable DecisionEpisode v0.1 objects."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def align_transcript_to_events(
    transcript: list[dict[str, Any]],
    visual_events: list[dict[str, Any]],
    window_ms: int = 3500,
) -> dict[str, Any]:
    """Attach nearby visual changes to each spoken segment by timestamp overlap."""
    alignment = []
    for segment in transcript:
        start_ms = int(segment["start_ms"])
        end_ms = int(segment["end_ms"])
        nearby = [
            event
            for event in visual_events
            if start_ms - window_ms <= int(event["timestamp_ms"]) <= end_ms + window_ms
        ]
        alignment.append(
            {
                "segment_id": segment["segment_id"],
                "start_ms": start_ms,
                "end_ms": end_ms,
                "matched_event_ids": [event["event_id"] for event in nearby],
                "alignment_method": "timestamp_window",
                "window_ms": window_ms,
            }
        )
    return {"alignment": alignment}


def build_decision_episode(
    *,
    video_path: str | Path,
    video_metadata: dict[str, Any],
    transcript: list[dict[str, Any]],
    frames: list[dict[str, Any]],
    ocr_records: list[dict[str, Any]],
    cursor_events: list[dict[str, Any]],
    vlm_results: list[dict[str, Any]],
    alignment: dict[str, Any],
) -> dict[str, Any]:
    """Build an episode without converting model/cursor guesses into observed facts."""
    video = Path(video_path)
    duration_ms = int(video_metadata.get("duration_ms", 0))
    visual_events = [
        {
            "event_id": f"frame-change-{frame['frame_index']:06d}",
            "timestamp_ms": int(frame["timestamp_ms"]),
            "event_type": "screen_change",
            "certainty": "observed_from_video",
        }
        for frame in frames
        if frame.get("is_change")
    ]
    changed_frame_refs = [event["event_id"] for event in visual_events]
    grounded_results = [
        result
        for result in vlm_results
        if result.get("status") == "completed"
        and str(result.get("likely_action", "unknown")).lower() != "unknown"
        and str(result.get("visible_ui_element", "unknown")).lower() != "unknown"
    ]
    inferred_refs = [str(item["event_id"]) for item in cursor_events if item.get("event_id")]
    inferred_refs.extend(
        f"vlm-grounding-{index:04d}"
        for index, result in enumerate(vlm_results, start=1)
        if result in grounded_results
    )

    ocr_lines = [
        f"{int(record['timestamp_ms'])} ms: {record.get('text', '')}"
        for record in ocr_records
        if record.get("text")
    ]
    first_visible = ocr_lines[0] if ocr_lines else "No readable text was returned by OCR."
    final_visible = ocr_lines[-1] if ocr_lines else "No readable text was returned by OCR."
    start_ms = min((int(segment["start_ms"]) for segment in transcript), default=0)
    end_ms = max((int(segment["end_ms"]) for segment in transcript), default=0)
    end_ms = min(end_ms, duration_ms) if duration_ms else end_ms

    narration = []
    for segment in transcript[:300]:
        narration.append(
            {
                "segment_id": str(segment["segment_id"]),
                "start_ms": int(segment["start_ms"]),
                "end_ms": int(segment["end_ms"]),
                "speaker_role": "unknown",
                "text": str(segment["text"]),
                "transcript_method": segment.get("transcript_method", "unknown"),
                "words": segment.get("words", []),
                "evidence_refs": ["ev-instructor-words"],
            }
        )

    evidence = [
        {
            "evidence_id": "ev-observed-video",
            "evidence_type": "ui_event",
            "observation_channel": "observed_from_video",
            "rationale_source": "not_applicable",
            "confidence": 1.0,
            "labels": ["observed_from_video"],
            "capture_method": "FFmpeg decoded frames + Tesseract OCR + pixel-difference detector",
            "source_locator": {
                "start_ms": 0,
                "end_ms": duration_ms,
                "event_ids": changed_frame_refs,
            },
            "raw_record_ref": "video-extraction/frames-and-ocr.json",
            "claim": (
                "Visible screen text and frame changes were read from the downloaded video "
                "file. This is observation of video pixels, not live browser telemetry."
            ),
        }
    ]
    if transcript:
        evidence.append(
            {
                "evidence_id": "ev-instructor-words",
                "evidence_type": "narration",
                "observation_channel": "not_applicable",
                "rationale_source": "instructor_explicit",
                "confidence": 0.9,
                "labels": ["instructor_words"],
                "capture_method": (
                    transcript[0].get("transcript_method", "unknown") + "_with_timestamps"
                ),
                "source_locator": {
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "transcript_segment_ids": [
                        str(segment["segment_id"]) for segment in transcript[:300]
                    ],
                },
                "raw_record_ref": "video-extraction/transcript.json",
                "claim": (
                    "Timestamped tutorial narration transcribed from subtitles or ASR. "
                    "The speaker is not diarized; the words are contextual evidence, not proof "
                    "that an on-screen action occurred or a business rule."
                ),
            }
        )
    if inferred_refs:
        confidence_values = [float(item.get("confidence", 0.0)) for item in cursor_events]
        confidence_values.extend(float(item.get("confidence", 0.0)) for item in grounded_results)
        evidence.append(
            {
                "evidence_id": "ev-inferred-actions",
                "evidence_type": "ui_event",
                "observation_channel": "inferred_from_video",
                "rationale_source": "behavioral_inference",
                "confidence": min(0.49, max(confidence_values + [0.0])),
                "labels": ["inferred_from_video"],
                "capture_method": (
                    "cursor-settle heuristic and Qwen3-VL grounding on changed frames only"
                ),
                "source_locator": {
                    "start_ms": 0,
                    "end_ms": duration_ms,
                    "event_ids": inferred_refs,
                },
                "raw_record_ref": "video-extraction/inferred-actions.json",
                "claim": (
                    "Possible target elements and actions are inferred from cursor candidates, "
                    "screen changes, OCR, narration context, and VLM outputs. No click telemetry "
                    "exists in the downloaded video; these are not observed click facts."
                ),
            }
        )

    evidence_refs = ["ev-observed-video"]
    if transcript:
        evidence_refs.append("ev-instructor-words")
    if inferred_refs:
        evidence_refs.append("ev-inferred-actions")

    if grounded_results:
        first = grounded_results[0]
        selected_strategy = (
            f"VLM inference at {first['timestamp_ms']} ms: "
            f"{first.get('likely_action')} involving "
            f"{first.get('visible_ui_element') or 'an uncertain UI element'}."
        )
        basis = ["behavioral_inference"]
        rationale = (
            "Qwen3-VL was prompted only with frames selected by the frame-change detector. "
            "Its UI target/action is an inference grounded with OCR and nearby narration, "
            "not a directly observed click or a general business rule."
        )
    elif cursor_events:
        first = cursor_events[0]
        selected_strategy = (
            f"A possible pointer interaction was inferred near {first['timestamp_ms']} ms; "
            "the target remains uncertain."
        )
        basis = ["behavioral_inference"]
        rationale = (
            "The cursor-settle heuristic found a pointer candidate near a changed screen area. "
            "This is a low-confidence video inference, not an observed click."
        )
    else:
        selected_strategy = (
            "Record the visible screen changes; no UI action could be grounded "
            "with sufficient evidence."
        )
        basis = ["unknown"]
        rationale = (
            "OCR and frame changes describe the visible screen. No reliable cursor/click or VLM "
            "grounding result was produced, so the action remains unknown."
        )

    facts_before = []
    facts_after = []
    if ocr_lines:
        facts_before.append(
            {
                "fact_id": "initial-visible-text",
                "path": "screen.initial_ocr_text",
                "value": first_visible,
                "evidence_refs": ["ev-observed-video"],
            }
        )
        facts_after.append(
            {
                "fact_id": "final-visible-text",
                "path": "screen.final_ocr_text",
                "value": final_visible,
                "evidence_refs": ["ev-observed-video"],
            }
        )

    session_id = str(video_metadata.get("video_id") or video.stem)
    return {
        "schema_version": "0.1",
        "episode_id": f"downloaded-video-{session_id}",
        "expert_id": "software-tutorial-operator",
        "workflow_ref": {
            "workflow_id": "software_tutorial.demonstration",
            "version": "0.1",
            "node_id": "video_grounding",
        },
        "source": {
            "source_id": session_id,
            "source_kind": "downloaded_tutorial_video",
            "sha256": sha256_file(video),
            "platform": str(video_metadata.get("extractor") or "local_video_file"),
            "application": "unknown_ui",
            "recording_session_id": session_id,
            "recorder_version": "video-file-extraction-v0.1",
            "source_duration_ms": duration_ms,
        },
        "task": {
            "business_domain": "software_tutorial",
            "goal": (
                "Identify UI state changes and likely demonstrated operations "
                "from a downloaded tutorial video."
            ),
            "user_request": (
                "Extract timestamped narration, visible UI text, screen changes, "
                "cursor candidates, and grounded action hypotheses."
            ),
            "success_criteria": [
                {
                    "criterion_id": "evidence-aligned-ui-operation",
                    "description": (
                        "A timestamped UI operation hypothesis is linked to visual "
                        "and narration evidence, or explicitly left unknown."
                    ),
                    "verification_type": "state_check",
                }
            ],
            "business_constraints": [],
            "risk_level": "low",
        },
        "state_before": {
            "application": "unknown_ui",
            "page": "video_initial_frame",
            "business_state": {"visible_text": first_visible},
            "facts": facts_before,
        },
        "narration": narration,
        "decision": {
            "decision_type": "step_selection",
            "selected_strategy": selected_strategy,
            "rationale_summary": rationale,
            "decision_basis": basis,
            "applicable_conditions": [],
            "selected_next_step": {
                "action": "ask_user",
                "objective": (
                    "Review the video-grounded UI operation hypothesis before "
                    "accepting it as a workflow step."
                ),
                "question": (
                    "Does the inferred UI target and action match the demonstrated operation?"
                ),
            },
            "alternatives_considered": [],
            "uncertainties": [
                "A downloaded video contains no native click or DOM event telemetry.",
                "Cursor locations and click actions, when present, are inferred and must not "
                "be treated as observed facts.",
                "One tutorial demonstration does not establish a general business rule.",
            ],
            "evidence_refs": evidence_refs,
        },
        "operation": {
            "execution_status": "not_observed",
            "event_refs": inferred_refs,
            "execution_trace_ref": f"downloaded-video:{session_id}",
        },
        "outcome": {
            "status": "not_verified",
            "state_after": {
                "application": "unknown_ui",
                "page": "video_final_frame",
                "business_state": {"visible_text": final_visible},
                "facts": facts_after,
            },
            "postcondition_checks": [],
            "next_action": "ask_user",
            "next_step_reason": (
                "Visual tutorial evidence is not a live-system postcondition check."
            ),
        },
        "evidence": evidence,
        "review": {
            "status": "needs_review",
            "approved_for_training": False,
            "review_notes": (
                "Automatically extracted from one downloaded tutorial video; "
                "inferred operations need independent review."
            ),
        },
        "quality": {
            "annotation_status": "auto_extracted",
            "trainable": False,
            "exclusion_reasons": [
                "Video-derived operations and cursor clicks are inferences, "
                "not direct event telemetry.",
                "Automatically extracted episode has not been independently reviewed for training.",
            ],
        },
    }
