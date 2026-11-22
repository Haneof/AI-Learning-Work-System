# Knowledge, Trajectory, and Evidence Contract

## Purpose

Represent extracted tutorial knowledge separately from the source evidence and from model interpretation. The system's useful output is a verified, time-aligned operation trajectory and a reusable knowledge package—not a transcript.

Each package explains what a person did, the apparent purpose, what changed on screen, where an action was directed, whether the expected result occurred, and under which conditions the knowledge applies.

## Four-step provenance path

1. Download record: original video URL and platform, creator, series/course, Drive location, content hash.
2. Prefilter record: subtitle source (embedded/sidecar or ASR fallback), language, timecodes, vertical/tutorial classification, and rejection reason if not selected.
3. Extraction record: source video intervals, frame/audio evidence, understanding model and version, action-grounding model and version, trajectory steps, and uncertainty.
4. Review/training lineage: GPT first review, PM Sangou independent evidence/test verification, SQLite approval, and the immutable LoRA training dataset snapshot.

## Observed versus inferred

Every action/knowledge claim must declare its epistemic source:

- **OBSERVED**: directly visible in the source video or captured in synchronized screen/input event telemetry. Cite the exact frames/time range or event record.
- **INFERRED**: reasoned from visible pointer movement, UI feedback, spoken explanation, surrounding context, model prediction, or before/after states. Store confidence and the observations supporting it.
- **MIXED**: the step combines direct observations and explicitly separated inferences.
- **UNKNOWN**: the video does not provide enough evidence.

Do not label a predicted coordinate as an actual mouse click unless the click is visibly evidenced or synchronized event telemetry exists. Do not represent inferred intent as a spoken statement. Keep alternate interpretations when ambiguity remains.

## Trajectory evidence contract

Each step should identify:

- source video ID/hash and start/end milliseconds;
- pre-action and post-action UI state;
- visible application, page, dialog, control, and text evidence;
- action description and target element;
- observed pointer/click/keyboard evidence, when actually present;
- inferred target point/coordinates and inference confidence, when predicted;
- spoken instruction or explanation with subtitle/audio timecode;
- apparent intent and whether it was stated or inferred;
- expected outcome and whether the outcome is visible;
- relevant preconditions, software/version scope, exceptions, and recovery evidence;
- understanding/grounding model identities and versions.

Textual explanation, coordinates, UI state, and visual references must remain linked to the same temporal event. An unsupported or conflicting claim is not silently normalized into a clean instruction.

## Knowledge typing and conflicts

Knowledge statements distinguish direct quote, extracted fact, inference, and recommendation. Support, contradict, and context evidence links remain separately represented.

- Exact duplicate video content is identified by SHA-256.
- Duplicate statements may be linked to canonical content within the relevant expert/vertical.
- Conflicting claims, versions, and applicability conditions coexist and retain their original evidence.
- A newer claim does not overwrite older claims merely because it was extracted later.
- Approved items require valid source evidence and both review gates.

## Review gates

GPT reviews first for evidence match, temporal/causal trajectory consistency, UI before/after consistency, observed/inferred separation, uncertainty, and unsupported claims.

PM Sangou then independently checks the original video evidence and relevant tests. There is no additional external or general manual-review queue. A package is eligible for approved storage and LoRA training only after both gates pass.

## Storage and implementation boundary

SQLite is the selected structured store for download records, content hashes, transcripts, trajectory steps, evidence references, conflicts, review events, approved packages, and training-dataset membership. Original videos are archived in Google Drive.

The existing repository has knowledge/evidence contract code and SQLite-oriented repository components in the skill/knowledge area, but the complete video trajectory schema and dual review workflow are still target design. Existing timestamped quote extraction must not be described as full operation understanding.
