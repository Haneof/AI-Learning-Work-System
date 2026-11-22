# Knowledge, Workflow, and Evidence Contract

## Purpose

Represent tutorial-derived workflow knowledge separately from its source evidence and from model interpretation. The useful output is a verified Decision Episode and reusable workflow definition—not a transcript or a list of clicks.

The system learns how an instructor pursued a business goal, what was known at each decision point, why a path was selected, what operation was delegated, what state changed, and what should happen next.

## Provenance path

1. **Download record:** original tutorial URL and platform, creator, series/course, archive location, content hash, and license status.
2. **Video-file extraction:** FFmpeg-decoded frames, screen-change timestamps, OCR regions, inferred cursor/click and UI-target candidates, and source-frame references.
3. **Narration:** supplied subtitles first, local ASR only when needed, and transcript segments with source language and word/segment timestamps.
4. **Decision extraction and verification:** DecisionEpisodes link current state, conditions, instructor explanations, inferred operation hypotheses, supported outcomes, and next decisions to the extracted video and narration evidence; the local verifier scores extraction fidelity, decision validity, and outcome validity.
5. **Review and training lineage:** independent PM review, HTN workflow version, approved storage, training-example JSONL, separate metadata sidecar, source-grouped split manifest, and immutable LoRA dataset snapshot.

## Evidence dimensions

Each evidence item records two independent dimensions:

- **observation_channel:** direct_capture, inferred_from_video, not_applicable, or unknown.
- **rationale_source:** instructor_explicit, behavioral_inference, hybrid, not_applicable, or unknown.

Each evidence item also has a confidence value from 0 to 1. This is an annotator/model confidence score, not a calibrated probability unless calibration is separately established.

The optional user_provided label is reserved for rules, constraints, or scenario facts supplied by the project owner/user. Do not relabel such requirements as instructor words or behavioral inference.

### How to interpret evidence

- Directly captured rrweb or Windows UI Automation event: observation_channel is direct_capture. It proves the event was recorded by the capture tool; it does not automatically prove business success.
- Instructor's actual spoken explanation: observation_channel is direct_capture for the recorded audio/transcript and rationale_source is instructor_explicit.
- Historical MP4 reconstruction: observation_channel is inferred_from_video. It is not a direct DOM, UIA, mouse, or keyboard event.
- Purpose inferred from demonstrated behavior: rationale_source is behavioral_inference.
- Both an explicit explanation and behavior support a reason: rationale_source is hybrid, with the two supports separately referenced.
- Project-owner-provided workflow rule: labels includes user_provided; both axes are normally not_applicable unless a distinct observation is also attached.
- Insufficient source information: use unknown. Do not invent a click, reason, or business result.

An instructor's words record what the instructor said; they do not automatically prove the statement is a correct universal business rule. A directly captured click is an observed interaction; it does not prove that the intended business postcondition passed.

## Decision Episode evidence requirements

Every important Decision Episode claim must reference one or more source evidence IDs. Preserve:
- source video/session ID and content hash;
- event IDs and timestamp ranges;
- narration segment IDs and transcript method;
- pre-decision state and post-operation state evidence;
- instructor-explicit rationale separately from inferred rationale;
- applicable workflow, software version, and conditions;
- confidence, uncertainty, and conflicting interpretations.

Do not use a future execution result to justify an earlier Brain decision. The training example for an earlier decision point must contain only information available at that time.

## Workflow evidence and conflicts

- Exact duplicate source content is identified by SHA-256.
- Different tutorials and software versions may demonstrate different valid workflows.
- Conflicting claims, workflow methods, and applicability scopes coexist with their original sources.
- A later claim does not overwrite an older claim merely because it was extracted later.
- Workflow rules are reviewed before becoming approved training knowledge.
- Volatile business rules are stored in the local HTN workflow data so they can be updated at runtime without retraining the Brain.

## Review and training gates

The first review checks evidence resolution, event/narration alignment, decision correctness, condition and branch consistency, observed/inferred separation, and uncertainty. PM Sangou independently verifies the source tutorial and relevant tests.

A Decision Episode is trainable only when both conditions pass:
1. review.status is approved and approved_for_training is true;
2. annotation quality is human_reviewed or gold, trainable is true, and exclusion_reasons is empty.

Auto-extracted, rejected, unresolved, or contradictory examples do not become training data automatically.

## Storage and implementation boundary

SQLite is the selected structured store for download records, semantic UI events, narration segments, Decision Episodes, workflow versions, evidence links, review events, and training-dataset membership. Original tutorial videos remain in Google Drive.

The repository now implements downloaded-video extraction and DecisionEpisode validation (#38), local open-weight verification (#39), fail-closed training-sample compilation (#40), Brain LoRA dataset preparation/configuration (#41), and a Brain/Hands closed-loop harness (#42). These are separate components, not a deployed production service or a trained domain expert. PR #41 did not train an adapter; PR #42 CI uses a deterministic WorkflowBrain stand-in and SimulatedHands. The PM evidence gate, real approved corpus, actual LoRA training run, and real Hands evaluation remain distinct requirements.
