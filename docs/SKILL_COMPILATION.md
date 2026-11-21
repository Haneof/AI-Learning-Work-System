# Procedural Skill Compilation MVP

## Purpose

Compile an explicitly described procedure into a declarative, evidence-backed skill
package. The compiler does not generate executable action code and does not run the
procedure.

## Inputs and gates

- The procedure is scoped to one `expert_id`, one source, and approved PROCEDURE
  knowledge IDs.
- Every selected knowledge item must be APPROVED, have SUPPORTS evidence for the
  requested source, and have a recorded human approval event.
- Each step identifies its knowledge item and one or more time-grounded evidence
  references. Evidence kind must match the source segment modality, and timestamps
  must fall inside the source segment locator.
- Unreviewed or synthetic steps are always emitted as
  `pending_frame_review`; a caller cannot self-promote them.
- Reviewed skills require a persisted APPROVED review against the exact procedure
  fingerprint and at least eight visually verified steps. The reviewer must differ
  from the annotator.
- Only a reviewed, statically validated package is registered as an immutable skill
  version. Draft packages remain unregistered and `SPEC_ONLY`.

## Package contents

Each successful compilation produces:

- `SKILL.md`: human-readable goal, scope and lifecycle warning.
- `manifest.json`: identity, version, contract, risk, evidence IDs and package test.
- `procedure.json`: normalized steps, knowledge IDs and exact review record (when reviewed).
- `tests/test_procedure_contract.py`: generated structural and evidence-presence test.
- `references/evidence_manifest.json`: source, expert, knowledge and per-step evidence map.

The staged output is passed to the existing `validate_skill_package` before it is
published at the requested new directory. Existing output paths are never overwritten.

## Repositories

`KnowledgeRepository` persists source segments, knowledge and human review history
in SQLite, enforces expert boundaries and uses the existing knowledge validator.
`SkillVersionRepository` persists skill review attestations and immutable registered
versions. It reuses the main-branch `SkillVersionRecord`; the main-branch
`SkillVersionRegistry` remains unchanged.

Both repositories record caller-supplied identity values. They are not authentication
systems: a future application service must derive expert/reviewer IDs from trusted
sessions.

## Example

~~~python
from aios_work_system.knowledge.repository import KnowledgeRepository
from aios_work_system.skills import (
    ProceduralSkillCompiler,
    ProcedureSkillSpec,
    SkillVersionRepository,
)

compiler = ProceduralSkillCompiler(
    KnowledgeRepository("data/knowledge.sqlite3"),
    SkillVersionRepository("data/skills.sqlite3"),
)
spec = ProcedureSkillSpec(
    expert_id="office-expert",
    skill_id="office.account-settings",
    version="1.0.0",
    title="Account settings",
    goal="Navigate to account settings",
    scope="Office application account management",
    source_id="tutorial-source-1",
    knowledge_ids=("approved-procedure-knowledge",),
    steps=(),
)
# Add explicit, timestamp-grounded steps before compilation.
result = compiler.compile(spec, "artifacts/skills/office-account-settings")
~~~

A draft may be compiled for review but cannot be registered or treated as executable.
