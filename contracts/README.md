# Workflow Decision Data Contracts (v0.1)

**Status: proposal frozen for implementation review; not validated for production or LoRA training.**

This directory defines the merged v0.1 data contract for teaching a language-model **Brain** to reason about business workflows and delegate page operations to an existing **Hands** model (for example, UI-TARS). The Brain chooses the business step, strategy, conditions, and verification requirements. Hands performs concrete UI interaction and reports observable results.

The three contracts are deliberately separate:

| Contract | File | Purpose |
|---|---|---|
| A — DecisionEpisode | decision-episode.schema.json | A source-grounded decision episode: goal, state, narration, decision, delegated operation, outcome, evidence, review and quality gates |
| B — WorkflowDefinition | workflow.schema.json | HTN task hierarchy, methods, conditions, graph edges, ordering constraints, invariants, capability mappings and recovery rules |
| C — BrainHandsProtocol | brain-hands-protocol.schema.json | Runtime JSON messages for Brain-to-Hands delegation and Hands-to-Brain execution results |

The shop example is in examples/shop-list-product.episode.json. It is a structural fixture only and is explicitly not approved for training.

## Version and freeze note

All three schemas use version **0.1**. Do not relabel this as 1.0.0 or treat it as a stable production standard.

Version 0.1 remains **unvalidated until a real-tutorial end-to-end sample audit** verifies that:
1. a real tutorial's event stream and narration can be aligned into one or more Decision Episodes;
2. independent reviewers agree on the decision, evidence axes, conditions and outcome labels;
3. WorkflowDefinition instances can represent the tutorial's actual alternatives and conditional paths without turning one demonstrated path into the only valid path;
4. a Brain LoRA training record can be produced without leaking future execution outcomes into the assistant target; and
5. the Brain-to-Hands request and result can execute and verify a task through a real registered Hands adapter.

Changes made before that audit should remain within v0.1 and be reviewed against the examples and tests. A version bump should follow the audit and any resulting breaking changes.

## Contract A — DecisionEpisode

A DecisionEpisode is the smallest source-grounded business decision example. It is not a plain click list or an entire tutorial transcript. It represents:

**goal at the time → current situation → why the choice was made → selected next action → operation status/result → what should happen next.**

Important groups:

- task: the business objective, success criteria and applicable constraints;
- state_before: only facts available at the decision point, each linked to evidence;
- narration: aligned instructor transcript segments, optionally with word timestamps;
- decision: decision type, selected strategy, concise rationale, conditions and one of the six decision actions;
- operation and outcome: what was executed or not executed, what was actually observed, which postconditions were checked and the next action;
- evidence: provenance and confidence for every important claim;
- review and quality: two independent gates before training.

### Evidence axes and confidence

Each evidence item has two orthogonal axes:

- observation_channel: direct_capture, inferred_from_video, not_applicable or unknown;
- rationale_source: instructor_explicit, behavioral_inference, hybrid, not_applicable or unknown.

It also has confidence in the inclusive range 0–1. This is an annotator/model confidence score, **not a calibrated probability** unless calibration is separately established.

The optional labels array retains the user_provided marker. Use it for project-owner/user-supplied rules, requirements or scenario facts. Do not relabel them as instructor words or behavioral inference.

Interpretation examples:

| Evidence | observation_channel | rationale_source | labels |
|---|---|---|---|
| rrweb / Playwright / Windows UIA event received directly | direct_capture | not_applicable | omitted |
| Instructor explicitly says why a step is needed | direct_capture (audio/transcript directly captured) | instructor_explicit | omitted |
| Historical MP4 suggests a click or state change | inferred_from_video | not_applicable | omitted |
| Historical MP4 behavior is used to infer a purpose | inferred_from_video | behavioral_inference | omitted |
| Instructor explanation and independent behavior both support the same rationale | direct_capture or inferred_from_video, as applicable | hybrid | omitted |
| Project owner states a workflow rule | not_applicable | not_applicable | user_provided |
| Source does not establish the fact or reason | unknown | unknown | omitted |

The axes answer different questions. A directly captured click does not prove the instructor's reason. An instructor's spoken claim is directly captured speech, but it is not automatically a verified business rule. A video-inferred state must not be relabelled as a directly collected DOM/UIA event.

### Decision types

The decision_type enum contains:
- task_decomposition
- step_selection
- sequence_decision
- branch_selection
- parameter_decision
- exception_handling
- recovery
- stop_decision
- completion_decision
- verify_state

The selected_next_step action is one of:
- delegate
- ask_user
- request_approval
- replan
- finish
- stop

### Two review gates

A record is eligible for training only when **both** gates pass:

1. review.status is approved **and** review.approved_for_training is true;
2. quality.trainable is true, quality.annotation_status is human_reviewed or gold, and quality.exclusion_reasons is empty.

auto_extracted records are not trainable until reviewed and promoted to human_reviewed or gold. rejected records cannot be trainable. A schema-valid example is not automatically a training example.

## Contract B — WorkflowDefinition

WorkflowDefinition combines an HTN task hierarchy with a conditional workflow graph.

- tasks contain compound and primitive tasks;
- methods decompose a compound task into subtasks when applicable_when conditions hold;
- primitive tasks point to registered capability_id values;
- edges distinguish hard_dependency from soft_preference;
- ordering_constraints express explicit required precedence;
- invariants declare conditions that must hold before specific tasks;
- transitions choose the next path based on state conditions;
- recovery_rules declare how to respond to failure or blocked conditions.

A hard_dependency is a non-bypassable dependency. A soft_preference expresses a preferred order but may be changed by the Brain when its rationale and the workflow policy allow it. ordering_constraints are explicit precedence constraints and are treated as hard requirements by the v0.1 validator.

Key preconditions are expressed as structured conditions (path/operator/value), not executable expressions. The validator checks that each invariant condition is repeated in the preconditions of every task listed in must_hold_before_task_ids. This prevents a task from appearing executable when a required guard is absent from its own contract.

Cross-tutorial workflow conflicts must **not overwrite** one another. Preserve separate workflow versions/variants and their source references, software versions and applicability conditions. A WorkflowDefinition should be scoped to where it applies, not silently promoted to a universal rule.

Volatile business rules belong in the local HTN workflow slice passed to the Brain at runtime. The LoRA should learn how to interpret the workflow, check its preconditions, choose among methods, request missing information and recover from Hands errors. Updating a volatile rule in the versioned HTN should not require retraining the LoRA.

## Contract C — BrainHandsProtocol

The Brain does not emit mouse coordinates, DOM selectors or low-level UI-TARS actions as its business plan. It emits a high-level operation_delegation:

- objective and registered capability_id;
- arguments;
- preconditions and allowed scope;
- must / must_not constraints;
- expected postconditions;
- observation requirements;
- risk and approval requirements;
- idempotency key.

A Hands adapter translates this request into the native request format of the selected operation model. It returns an operation_result with status, observed_state, postcondition_results, actions_summary, error and evidence references.

The Brain decides what to do next based on the returned result. A click or successful tool call alone is not proof that the business postcondition passed. A succeeded result must include at least one passed postcondition with evidence.

The validator checks capability_id against an external capability registry supplied to the command. A schema-valid but unregistered capability must be rejected.

## Brain LoRA training samples

Training records are JSONL with a conversational messages array containing system, user and assistant messages. The assistant target is a JSON decision object with one of the six decision_action values. This message format is intended for conversational supervised fine-tuning pipelines (including TRL, Axolotl and LLaMA-Factory); each trainer still needs its model chat template and dataset mapping configured.

**Do not put training metadata in messages.** Keep a separate training_meta JSONL sidecar joined by training_example_id. It contains evidence_tier and rationale_loss_weight and is never fed to the model.

Suggested evidence_tier labels are categorical project metadata, not externally standardized scores:
- direct_explicit
- direct_behavioral_or_hybrid
- video_reconstructed
- user_provided_rule
- mixed
- unknown

rationale_loss_weight is nullable. Leave it null until a training profile has a measured reason to set it; do not invent per-tier weights in the data contract.

### Normal decision sample

Input contains the goal, facts known at the decision point, the relevant local HTN workflow slice, allowed capabilities and null last_execution_result when no prior Hands result exists. Assistant output contains only the next decision/delegation.

    {
      "messages": [
        {
          "role": "system",
          "content": "Return one JSON decision. Do not claim an operation has executed."
        },
        {
          "role": "user",
          "content": "{\"goal\":\"List a new product\",\"current_state\":{\"photos.status\":\"complete\",\"title.status\":\"missing\",\"price.status\":\"not_set\"},\"workflow_slice\":{\"invariant\":\"title.status must equal verified before set_price\"},\"available_capabilities\":[\"shop.listing.enter_title\"],\"last_execution_result\":null}"
        },
        {
          "role": "assistant",
          "content": "{\"decision_action\":\"ask_user\",\"rationale_summary\":\"The title is missing and must be written and verified before setting the price. The title text was not supplied.\",\"question\":\"Please provide the product information needed to write its title.\"}"
        }
      ]
    }

Sidecar line:

    {
      "training_example_id": "shop-normal-001",
      "sample_type": "normal_decision",
      "episode_refs": ["shop-list-product-title-first-001"],
      "evidence_tier": "user_provided_rule",
      "rationale_loss_weight": null
    }

### Error-recovery sample

For an error-recovery sample, put the previous Hands return in **user.last_execution_result**. The assistant target is the Brain's next decision after seeing that result. Do not put the actual execution result into the assistant target.

    {
      "messages": [
        {
          "role": "system",
          "content": "Return one JSON decision. Choose a safe next action from the allowed decision actions."
        },
        {
          "role": "user",
          "content": "{\"goal\":\"List a new product\",\"current_state\":{\"title.status\":\"missing\",\"price.status\":\"not_set\"},\"workflow_slice\":{\"invariant\":\"title.status must equal verified before set_price\"},\"available_capabilities\":[\"shop.listing.enter_title\"],\"last_execution_result\":{\"status\":\"failed\",\"error\":{\"category\":\"validation_error\",\"code\":\"TITLE_REJECTED\",\"message\":\"The page rejected the submitted title.\"},\"postcondition_results\":[{\"condition_id\":\"title-saved\",\"result\":\"failed\"}]}}"
        },
        {
          "role": "assistant",
          "content": "{\"decision_action\":\"replan\",\"rationale_summary\":\"The title was not saved. Do not proceed to price configuration; diagnose the rejection and obtain any missing or corrected title information before retrying.\",\"next_objective\":\"Diagnose the title validation failure and determine the corrected title input.\"}"
        }
      ]
    }

Sidecar line:

    {
      "training_example_id": "shop-recovery-001",
      "sample_type": "error_recovery",
      "episode_refs": ["shop-list-product-title-first-001"],
      "evidence_tier": "mixed",
      "rationale_loss_weight": null
    }

### No execution-outcome leakage

The assistant target must stop at the Brain's decision. It must not contain future Hands results, actual postcondition results, the observed state after the delegated operation or an execution_outcome field. For recovery samples, a prior Hands result is permitted only in user.last_execution_result because it is already part of the Brain's input at that decision point.

Training examples are generated from Decision Episodes as multiple decision-point samples. Never use future fields from an Episode as input to an earlier decision point.

### Split policy

Split by tutorial/course/source group, not by individual episode or event. All fragments, episodes and near-duplicates from the same tutorial/course/source must remain in one partition. Where available, use course_id as the grouping key; otherwise use tutorial_id, then source_id. Deduplication or near-duplicate grouping must also prevent equivalent fragments from crossing train/test boundaries.

## Validation

Install the existing development extras (the contracts validator uses jsonschema):

    python -m pip install -e ".[dev]"

Validate one document:

    python -m contracts.validate --kind episode contracts/examples/shop-list-product.episode.json
    python -m contracts.validate --kind workflow contracts/examples/shop-list-product.workflow.json --evidence-registry contracts/examples/shop-list-product.episode.json
    python -m contracts.validate --kind protocol path/to/delegation.json --capability-registry path/to/capabilities.json
    python -m contracts.validate --kind training-jsonl path/to/train.jsonl --sidecar path/to/training_meta.jsonl

The validator performs two layers:

**Layer 1 — JSON Schema Draft 2020-12**
- type, required field, enum, bounds and structure checks;
- date-time and confidence format checks;
- additional fields are rejected where the contract is closed.

**Layer 2 — semantic checks**
- Episode evidence references resolve within the Episode; Workflow evidence references resolve through the supplied evidence registry;
- timestamp ranges are ordered and remain within the source duration when known;
- a decision has evidence references or explicitly declares unknown as a decision basis;
- a successful outcome has a passed postcondition backed by directly captured verification evidence;
- review.approved_for_training and quality.trainable gates are consistent;
- workflow task and capability IDs are unique and references resolve;
- hard dependency / hard ordering cycles are rejected;
- every primitive task maps to a capability declared by the WorkflowDefinition;
- invariant preconditions are present on each guarded task and cannot be silently bypassed;
- Brain delegation capability IDs must exist in the supplied capability registry;
- successful Hands results require passed postcondition verification evidence;
- training messages use system/user/assistant roles, the six decision actions, the correct normal/recovery input shape, and no future execution outcome in the assistant target.

The validator is a contract checker, not a workflow theorem prover. In particular, v0.1 does not prove that arbitrary condition expressions are mutually exclusive, that a tutorial's explanation is factually correct, or that a workflow will succeed in every live application state. Those require human review and real-task tests.

## References

- JSON Schema Draft 2020-12: https://json-schema.org/draft/2020-12
- W3C PROV-O provenance ontology: https://www.w3.org/TR/prov-o/
- SHOP2 / hierarchical task-network planning research: https://www.cs.umd.edu/projects/shop/
- TRL conversational dataset formats: https://huggingface.co/docs/trl/dataset_formats
- Axolotl documentation: https://docs.axolotl.ai/
- LLaMA-Factory documentation: https://llamafactory.readthedocs.io/

The references are design background, not a claim that these project-specific contracts are prescribed by those standards.
