# Knowledge and Evidence Contract

## Purpose

Represent extracted knowledge separately from its source evidence. Knowledge statements are typed as direct quote, extracted fact, inference, or recommendation. Evidence links identify the source segment and whether it supports, contradicts, or contextualizes the statement.

## Rules

- Every knowledge item belongs to one expert scope.
- Source segments retain source ID and a page/time/frame locator.
- APPROVED items require at least one valid SUPPORTS link.
- DIRECT_QUOTE items require an excerpt that exactly occurs in the referenced segment text.
- An evidence link must reference an existing segment and matching source ID.
- Cross-expert evidence is denied unless the source segment explicitly lists the target expert in its sharing allowlist.
- Duplicate statements are identified by normalized SHA-256 within the same expert and epistemic type.
- Different statements with the same conflict key coexist; both move to REVIEW_REQUIRED instead of overwriting each other.

## Current implementation boundary

The current registry is an in-memory PoC. It validates contracts and access scope but is not a database, authentication system, or production authorization service. The API layer must derive expert identity from authenticated context rather than trusting caller-supplied IDs.

## Test coverage

Tests cover missing support evidence, incorrect quotes, cross-expert access, explicit sharing, duplicate normalization, and conflicting source statements. Source storage, database transactions, reviewer workflows, and durable audit events remain subsequent integration work.
