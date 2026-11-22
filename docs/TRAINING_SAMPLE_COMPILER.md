# Brain Training-Sample Compiler

The compiler converts DecisionEpisodes into conversational supervised examples for the Brain. It does not train a LoRA adapter and it does not infer new policy labels.

## Admission is fail-closed

Every input bundle must contain an \`episode\`, \`local_verification\`, and \`pm_verification\` record. The local report must match the episode ID, have \`overall_status: pass\`, and mark all three levels (\`extraction_fidelity\`, \`decision_validity\`, and \`outcome_validity\`) as \`pass\`. The independent PM record must have \`status: pass\` and non-empty \`source_evidence_refs\` and \`proposed_record_evidence_refs\`.

The pipeline's preliminary \`training-admission.json\` may say \`held_pending_pm_independent_verification\` after a local pass. Once the independent PM attestation is supplied, the compiler rechecks both gate records together. A local hold or any other failed admission state remains excluded. The episode itself must also be approved for training: \`review.status=approved\`, \`review.approved_for_training=true\`, \`quality.annotation_status\` is \`human_reviewed\` or \`gold\`, \`quality.trainable=true\`, and \`exclusion_reasons=[]\`. Missing, held, mismatched, or malformed evidence is excluded.

## Decision-point contract

A bundle is one DecisionEpisode plus its two gate records. The episode may include \`decision_points\` for multiple cuts; without that array, the episode is treated as one decision point. Every cut is serialized independently. The model-facing user payload contains exactly:

- \`goal\`
- \`current_state\`
- \`available_capabilities\`
- \`last_execution_result\`

\`last_execution_result\` is \`null\` before a Hands action has run. For recovery examples it is the prior Hands return object with status \`success\`, \`partial_success\`, or \`failure\`. It is never populated from the current decision's \`operation\` or \`outcome\` fields. Future-only fields such as \`future_result\`, \`outcome\`, \`state_after\`, and \`postcondition_checks\` are rejected from decision-time input. Evidence-axis and annotation labels are also rejected from model messages. When required context is missing, only an \`ask_user\` decision can be compiled; a delegated execution label is rejected rather than silently rewritten.

Assistant output is a JSON decision object whose \`action\` is exactly one of \`delegate\`, \`ask_user\`, \`request_approval\`, \`replan\`, \`finish\`, or \`stop\`. A delegate action must name a capability present in \`available_capabilities\`. \`ask_user\` must include a question.

## Output files

The compiler writes:

- \`train.jsonl\` and \`test.jsonl\`: one conversational \`{"messages": [...]}\` object per line, with \`system\`, \`user\`, and \`assistant\` roles. This is a common conversational format used by TRL and can be mapped to Axolotl and LLaMA-Factory chat/message templates.
- \`train.training_meta.jsonl\` and \`test.training_meta.jsonl\`: one separate sidecar row per model sample. Each includes \`episode_id\`, \`sample_type\`, \`evidence_tier\`, \`rationale_loss_weight\`, source group, and sample identity. These sidecars must not be included in model training inputs.
- \`dataset_manifest.json\`: split assignments, exclusions, counts, and format declaration.

A sidecar's \`evidence_tier\` preserves both evidence axes (\`observation_channel\` and \`rationale_source\`), per-evidence confidence, and \`user_provided\` status. Evidence labels are not copied into system/user/assistant messages. \`rationale_loss_weight\` is the mean confidence of cited instructor-explicit, behavioral-inference, or hybrid rationale evidence; it is \`0.0\` when no rationale evidence has a usable confidence. Confidence is an annotation score, not a calibrated probability.

The train/test partition is deterministic and grouped by source/course/hash identity. All decision points from the same source group stay together. Conflicting decisions from separate tutorials remain separate records; the compiler never overwrites or deduplicates them. With only one eligible source group, all records remain in train and the manifest reports that a held-out test split is impossible.

## API

\`\`\`python
from aios_work_system.training_data import compile_episodes, write_compilation

result = compile_episodes(review_bundles, seed=42, train_fraction=0.8)
write_compilation(result, "artifacts/brain-training")
\`\`\`

For batch runs, provide a JSON list of review bundles (or an object with an \`episodes\` list):

\`\`\`bash
python scripts/compile_training_samples.py \\
  --input artifacts/reviewed-episodes.json \\
  --output-dir artifacts/brain-training \\
  --seed 42 --train-fraction 0.8
\`\`\`

Each bundle contains:

\`\`\`json
{
  "episode": {"episode_id": "...", "source": {}, "task": {}, "state_before": {}, "decision": {}, "evidence": [], "review": {}, "quality": {}},
  "local_verification": {"episode_id": "...", "overall_status": "pass", "levels": {"extraction_fidelity": {"status": "pass"}, "decision_validity": {"status": "pass"}, "outcome_validity": {"status": "pass"}}},
  "pm_verification": {"status": "pass", "source_evidence_refs": ["..."], "proposed_record_evidence_refs": ["..."]}
}
\`\`\`
