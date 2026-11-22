# Knowledge Package Compilation and Validation Harness

## Purpose

The product goal is a capable vertical LoRA expert built from verified tutorial knowledge. The approved knowledge packages are **training data**, not the end product.

The skill-package compiler turns selected verified knowledge into a structured, inspectable validation artifact. It helps check evidence, conditions, success criteria, exceptions, and recovery guidance before training and during expert evaluation. It does not define a mandatory click-by-click route and does not replace the LoRA expert.

## Knowledge package contract

Required manifest fields:

- purpose: the problem this knowledge package helps solve.
- conditions: applicable_when and not_applicable_when arrays.
- judgement_criteria: observable criteria for judging correctness.
- experience: success and failure arrays.
- counterexamples: plausible-looking approaches that are actually wrong.
- recovery: how to stop, restore, or reassess after failure.

procedure.json uses schema version 2.0 and stores suggested_steps, an optional reference flow. It may be empty or incomplete. Suggested steps do not define a mandatory execution sequence and are not required to be exhaustive. The model should learn the goal, conditions, reasoning, UI evidence, and recovery principles—not memorize one route.

## Evidence and dual-review gates

- Every selected knowledge item must be approved for the exact source/video and vertical.
- Package evidence must point to source video identity/hash, timestamped segments, and relevant visual/audio evidence.
- Evidence kind must match the source segment modality, and timestamps must fall inside the referenced locator.
- Every package evidence reference must be supported by a selected knowledge item; CONTEXT and CONTRADICTS links do not count as support.
- Direct observations and inferred claims must remain separately typed. Inferred coordinates, intent, or causality cannot be written as observed historical events.
- GPT performs the first validation: evidence match, trajectory/time consistency, before/after UI state, uncertainty, and observed/inferred separation.
- PM Sangou independently verifies the candidate against original video evidence and relevant tests.
- There is no separate human-review queue. Both gates must pass before a package is eligible for the approved SQLite corpus or LoRA training snapshot.
- Rejected, conflicting, and unresolved packages remain traceable and cannot be promoted by the compiler.

## Compiler output and role

A compiled validation package may contain:

- SKILL.md: purpose, conditions, judgement criteria, experience, counterexamples, recovery, and an explicit warning that suggested steps are not mandatory.
- manifest.json: structured knowledge sections, identity, scope, risk, evidence IDs, and validation metadata.
- procedure.json: source/expert identity, package evidence, and optional suggested_steps.
- tests/: generated structural/evidence-presence tests.
- references/evidence_manifest.json: package and per-suggestion evidence map.

Only packages backed by approved knowledge and both review gates should be compiled as verified training/validation material. A draft may be compiled for diagnostics but stays unapproved and cannot enter the training snapshot.

## Repositories

KnowledgeRepository persists source segments, knowledge, and review history in SQLite and enforces expert boundaries. SkillVersionRepository persists review attestations and immutable registered package versions. Registration must be restricted to the dual-approved package state.

Repositories record identity values supplied by their caller; they are not authentication systems. An application service must derive identities from trusted sessions and verify the PM review gate.

## Validation harness use

The compiler and Docker sandbox support two checks:

1. **Training-material validation**: verify package structure, source provenance, evidence links, conditions, contradictions, and tests before a dataset snapshot is frozen.
2. **Expert-behavior validation**: use package criteria to test the trained LoRA expert in the sandbox and GUI operation loop, including changed starting states and unseen task variations.

The compiler does not train LoRA, execute suggested steps, or by itself prove that an expert has learned to generalize.
