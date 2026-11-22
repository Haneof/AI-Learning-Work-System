# Tutorial Acquisition and Learning Pipeline

## Purpose and priority

This document defines the target pipeline for collecting hundreds of gigabytes of tutorials and turning them into verified, reusable training knowledge for vertical LoRA experts.

**Quality ranks first; efficiency ranks second.** A transcript, frame dump, or fluent video summary is not a successful extraction. The full extraction stage must understand the demonstrated operation, its intent, the visible UI state transition, the action target, and the result. An uncertain action must remain an inference, never be promoted to a recorded fact.

The current repository contains an acquisition prototype and media interfaces, not this complete production pipeline. This design does not claim that the cloud downloader, real ASR, video-understanding models, action-grounding model, joint review, or LoRA training workflow are already implemented.

## Step 1 — Download and course archive

1. Search the web for tutorials in the selected target vertical.
2. Download with a cloud downloader directly into the user's 5TB Google Drive. Do not use scattered single-video folders or make a local workstation the bulk-download staging destination.
3. Organize the archive hierarchically by **creator and series/course**. A platform grouping may sit above the creator level, but the course structure must remain intact:

   ```text
   AI-Learning/
     <platform>/
       <creator>/
         <series-or-course>/
           <video-file>
   ```

4. Keep one download record for every video. At minimum, record the canonical source link and platform. Also retain creator, series/course, title, discovery/download time, Drive file ID/link/path, byte size, content SHA-256, and download status when available.
5. Preserve original source metadata and attribution/license information where available. Unknown license metadata stays unknown; it must not be guessed.

The downloader's final archive target is Drive. The repository's current Google Drive API OAuth helper is an integration component, not proof that a cloud downloader-to-Drive production flow already exists.

## Step 2 — Clean first, then perform intelligent extraction

### 2a. Cheap text pre-filter

This stage runs before expensive multimodal extraction:

1. Check the downloaded video for existing subtitle tracks or associated subtitle files.
2. Prefer and extract existing subtitles when available.
3. Only when subtitles are unavailable, run ASR on the audio to create a timestamped subtitle/transcript.
4. Use this text to classify whether the video is both (a) a tutorial and (b) relevant to the selected target vertical.
5. Drop unrelated videos, non-tutorial content, and clear false positives from the full-extraction queue. Retain the download record and a rejection reason; do not erase acquisition history.
6. Only matching videos proceed to full video understanding.

This filter is intentionally cheap: subtitle extraction or ASR plus text classification. It reduces GPU use by rejecting unsuitable material before full visual reasoning. Passing the text filter is not proof that the video has been understood or that its instructions are correct.

### 2b. Full multimodal understanding and operation trajectory extraction

The selected model must watch the relevant video frames/clips and listen to the audio, using subtitles/transcription as supporting context. It must extract a temporally aligned operation trajectory and knowledge, including:

- What the person is doing and the task goal.
- Why the person is taking the action, separating spoken explanation from model-inferred intent.
- Which UI/application/page and controls are visible.
- What appears to be clicked, selected, typed, dragged, or changed, and where on screen the target is located.
- The UI state before and after the action, including dialogs, navigation, values, status messages, and other visible effects.
- Whether the expected result is visible, absent, ambiguous, or contradicted.
- Preconditions, alternative paths, exceptions, recovery options, and applicability/version constraints that can be supported by evidence.

The extraction is not “video-to-subtitles and done.” Transcription-only output does not qualify. The output is a structured, time-aligned knowledge package whose steps link to source video intervals and visual/audio evidence.

### Model responsibilities

| Model | Assigned job | Expected output |
|---|---|---|
| Qwen3-VL | Video understanding: watch frames/clips and reason over the tutorial and its context | Text descriptions of events, intent, UI state, outcomes, and evidence-linked knowledge |
| Mage-VL | Video understanding candidate, evaluated on the same job independently | Text descriptions of events, intent, UI state, outcomes, and evidence-linked knowledge |
| Magma | Action grounding, not the primary semantic explainer | Coordinate/action output such as candidate click points, target regions, and trajectories |

Qwen3-VL and Mage-VL are competing video-understanding candidates and must be evaluated on understanding quality. Magma performs a different action-grounding job and must be evaluated on coordinate/trajectory accuracy. Do not rank unlike task metrics in one score. The Qwen3-VL vs Mage-VL blind test on Colab T4 is currently running; this document records no winner.

Use the understanding model to describe **what happened and why**. Use the grounding model to propose **where the action was aimed and what coordinate/action sequence is consistent with the frames**. Cross-check them. A grounding prediction is not proof of an actual historical mouse event.

### Evidence epistemology

Every trajectory step must distinguish:

- `observed`: explicitly visible in the video or captured in synchronized input-event logs. Store the exact source/time/frame evidence.
- `inferred`: a reasoned interpretation not directly recorded, such as an inferred click when the cursor or click feedback is ambiguous, inferred intent, or inferred causal connection. Store the inference, confidence, and supporting observations.

Do not create `observed` mouse/keyboard events when the video does not visibly show them or a synchronized event log does not exist. If the action is ambiguous, preserve the uncertainty and the candidate interpretations.

## Step 3 — Content deduplication, two-stage review, and SQLite storage

1. Deduplicate by content hash (SHA-256 of the downloaded video bytes). Exact duplicate content is processed once and linked to the existing source record.
2. Different or conflicting knowledge entries coexist. Never overwrite a conflicting statement, trajectory, applicability scope, or source version. Preserve both claims, evidence, and provenance so that disagreement remains inspectable.
3. GPT performs the first review:
   - every claim and action is supported by the cited video/audio evidence;
   - trajectory steps are temporally and causally consistent;
   - before/after UI states agree with the frames;
   - observed and inferred claims are correctly separated;
   - inferred mouse/click coordinates are not mislabeled as recorded events;
   - uncertainty and contradictions are not hidden.
4. PM Sangou independently verifies GPT-passed candidates against the original video evidence and the relevant tests. There is **no separate human-review queue or outside manual reviewer**; these are the two required project gates.
5. Only items passing both GPT review and PM verification enter the approved SQLite store. Rejected or unresolved candidates remain traceable with their review status but are not admitted as verified training data.

## Step 4 — Train and validate vertical LoRA experts

1. Build the training dataset from verified knowledge packages. The packages are training data, not the final product.
2. Train the LoRA adapter on a cloud GPU. Current capacity-planning assumption: a 16GB NVIDIA T4 fits 4B BF16 LoRA; the 9B variant requires a 24GB-or-larger GPU. Confirm the exact base revision, sequence length, batch, optimizer, checkpointing, and peak VRAM in the training run before treating a resource estimate as measured.
3. Bring the trained adapter back to the deployment environment and mount it on the 4B base model.
4. Use one base model with different vertical LoRAs to create different domain experts. Keep each adapter, dataset snapshot, training configuration, base revision, and evaluation report versioned.
5. Validate each trained expert in the Docker sandbox and the GUI operation loop. Test goal understanding, action selection, state verification, recovery, and unseen variations—not just replay of the tutorial's exact sequence.

The skill-package compiler and Docker sandbox are validation harnesses for training material and expert behavior. They are not the destination product and do not replace the trained LoRA expert.

## Storage and provenance

- Original videos and course groupings live in Google Drive.
- Download records link each item to source URL, platform, creator, series, Drive location, and content hash.
- Approved structured knowledge, review decisions, trajectory steps, conflicts, and training-dataset membership are stored in SQLite.
- Each extracted step links back to video ID/hash, start/end time, relevant frames, transcript evidence, model identity/version, and observed/inferred status.
- Keep failed, rejected, and superseded records for traceability; they are excluded from the verified training snapshot.

## Current implementation boundary

The repository currently has a YouTube acquisition prototype, Drive API storage code, FFmpeg audio/frame extraction, ASR/OCR Protocol interfaces, deterministic static adapters, and a simple video-learning evidence path. The static ASR/OCR adapters consume supplied fixtures; they do not perform real transcription or recognition. The current extractor protocol does not yet express full video reasoning, action grounding, or a temporally aligned operation trajectory. Those are the principal design-to-implementation gaps.
