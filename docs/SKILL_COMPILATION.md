# Knowledge Package Compilation MVP

## Purpose

Compile approved, source-grounded knowledge into a declarative knowledge package.
A package records what problem it addresses, when it applies, how correctness is
judged, what experience has been observed, misleading counterexamples, and how to
recover from failure. It does not prescribe a mandatory click-by-click route.

## Knowledge package contract

Required manifest fields:

- purpose: the problem this knowledge package helps solve.
- conditions: applicable_when and not_applicable_when arrays.
- judgement_criteria: observable criteria for judging correctness.
- experience: success and failure arrays.
- counterexamples: plausible-looking approaches that are actually wrong.
- recovery: how to stop, restore, or reassess after failure.

procedure.json uses schema version 2.0 and stores suggested_steps, an optional
reference flow. It may be empty or incomplete. Suggested steps do not define a
mandatory execution sequence and are not required to be exhaustive.

## Evidence and review gates

- Every selected knowledge item must be APPROVED, have SUPPORTS evidence for the
  requested source, and have a recorded human approval event.
- At least one package-level evidence reference is required. Evidence kind must
  match the source segment modality, and timestamps must fall inside its locator.
- Every package evidence reference must be linked as SUPPORTS by a selected
  approved knowledge item. CONTEXT and CONTRADICTS links do not count.
- Evidence attached to a suggested step is independently checked using the same
  source, modality, timestamp, and SUPPORTS requirements.
- Unreviewed or synthetic suggested steps cannot self-promote to frame_verified.
- Reviewed packages require a persisted APPROVED review of the exact knowledge
  fingerprint, an independent reviewer, and visual frame/UI evidence. Review is
  not conditioned on a fixed number of suggested steps.
- Only reviewed, statically validated packages are registered as immutable versions.
  Draft packages remain unregistered and SPEC_ONLY.

## Package contents

- SKILL.md: the six knowledge sections and an explicit optional-steps warning.
- manifest.json: the six structured knowledge sections, identity, scope, risk,
  evidence IDs, and package test.
- procedure.json: source/expert identity, package evidence, and suggested_steps.
- tests/test_knowledge_contract.py: generated structural/evidence-presence test.
- references/evidence_manifest.json: package and per-suggestion evidence map.

The staged output is validated before it is published at the requested new
directory. Existing output paths are never overwritten.

## Repositories

KnowledgeRepository persists source segments, knowledge, and human review history
in SQLite, enforces expert boundaries, and uses the knowledge validator.
SkillVersionRepository persists review attestations and immutable registered
package versions. Registration remains limited to reviewed packages.

Both repositories record caller-supplied identity values. They are not
authentication systems; a future application service must derive identities
from trusted sessions.

## Example

The compiler input requires the six knowledge sections plus timestamped evidence.
Suggested steps are optional:

~~~python
spec = ProcedureSkillSpec(
    expert_id="office-expert",
    skill_id="office.account-settings",
    version="1.0.0",
    title="Account settings knowledge",
    purpose="Choose a safe way to reach and verify account settings.",
    scope="Office application account management",
    source_id="tutorial-source-1",
    knowledge_ids=("approved-knowledge",),
    conditions={
        "applicable_when": ["The user is authorized to manage settings."],
        "not_applicable_when": ["The account is locked."],
    },
    judgement_criteria=("The resulting setting is independently observable.",),
    experience={
        "success": ["Verify the resulting state."],
        "failure": ["A click alone does not prove success."],
    },
    counterexamples=("A click animation is not proof of a changed setting.",),
    recovery=("Stop and reassess from a known state.",),
    evidence_refs=({"kind": "video_frame", "ref": "frame-1", "timestamp_seconds": 1.0},),
    suggested_steps=(),
)
~~~

A draft package may be compiled for review but cannot be registered or treated as
executable. The compiler does not run suggested steps.
