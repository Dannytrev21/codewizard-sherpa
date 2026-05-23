# Story S1-01 — Newtype identifiers for the durable substrate

**Step:** Step 1 — Domain primitives, typed event contracts, and structural fences
**Status:** Ready
**Effort:** S
**Depends on:** —
**ADRs honored:** production ADR-0033, production ADR-0043

## Context
Every later Phase-9 story (the EventPayload union, the activity registry, the workflow body, the Postgres schema) threads `WorkflowId`, `EventId`, `AttemptId`, `WorkflowSeq`, `ProjectionId`, `TaskQueueName`, `ActivityName`, `CorrelationId`, and `PrUrl` simultaneously — `mypy --strict` must reject confusing one for another at compile time. The kernel-tier `codegenie.types.identifiers` module already ships the Phase-3 catalog (including `WorkflowId`, `EventId`, `BlobDigest`, `TaskClassId`); this story adds the Phase-9 names additively (ADR-0043) and lands the typed-credential class registry under `codegenie.types.credentials` so the sanitizer in Step 3 can blocklist by *type*, not name or value (ADR-0008's load-bearing layer).

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Data model — Newtype identifiers (Contract)` — names + intent for each Newtype
  - `../phase-arch-design.md §Capability types (Contract)` — `EventLogWriteCapability`/`PrOpenCapability`/`LlmSpendCapability` reference `TaskQueueName` + `WorkflowId`
  - `../phase-arch-design.md §Design patterns applied #3 — Newtype for domain identifiers` — what these buy
- **Phase ADRs:**
  - `../ADRs/0008-typed-credential-blocklist-not-regex.md` — `SECRET_TYPES` is the trust root; load-bearing layer
- **Production ADRs:**
  - `../../../production/adrs/0033-sum-types-for-domain-state.md` — primitive-obsession is a review blocker; `NewType` is the canonical fix
  - `../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md` — additions to `codegenie.types.identifiers` are extension; no edits
- **Source design:**
  - `../final-design.md §Synthesis ledger` — Phase-9 type catalog row
- **Existing code:**
  - `src/codegenie/types/identifiers.py` — Phase-1/2/3 catalog already present; `WorkflowId`, `EventId`, `BlobDigest`, `TaskClassId` already exist (do **not** redefine)
  - `src/codegenie/types/identifiers.py §__all__` — every Newtype is exported via the explicit `__all__`; mirror that discipline
  - `src/codegenie/types/identifiers.py §_DEFINITIONS` (the `Mapping[str, str]` description table at the tail) — each new Newtype gets a docstring row

## Goal
Add the seven new Phase-9 Newtypes to `codegenie.types.identifiers` and ship the `SECRET_TYPES` typed-credential registry under `codegenie.types.credentials` so every later module can import the names without re-defining them.

## Acceptance criteria
- [ ] `codegenie.types.identifiers` exports the seven new Newtypes: `AttemptId`, `CorrelationId`, `WorkflowSeq` (int-backed), `ProjectionId`, `TaskQueueName`, `ActivityName`, `PrUrl`.
- [ ] Each new Newtype appears in the module's `__all__` and in the `_DEFINITIONS` description table with a one-line provenance note ("Phase-9 S1-01 — …").
- [ ] `codegenie.types.identifiers` is *not* edited to redefine `WorkflowId`, `EventId`, `BlobDigest`, or `TaskClassId` (those already exist; reuse).
- [ ] `codegenie.types.credentials` ships `GitHubToken`, `LlmApiKey`, `MicroVmCredential`, `PostgresPassword`, `SshPrivateKey` (each a frozen Pydantic `BaseModel` with `extra="forbid"`) and `SECRET_TYPES: Final[frozenset[type]]` containing exactly those five types.
- [ ] `mypy --strict src/codegenie/types/` is clean.
- [ ] `tests/unit/types/test_phase09_identifiers.py` asserts each name is `NewType`-backed (`hasattr(WorkflowSeq, "__supertype__")`) and that `WorkflowSeq.__supertype__ is int` while the rest supertype `str`.
- [ ] `tests/unit/types/test_phase09_secret_types.py` asserts `SECRET_TYPES` has exactly five members and that every member is a Pydantic `BaseModel` subclass with `frozen=True` and `extra="forbid"`.
- [ ] The TDD plan's red tests exist, were committed, and are green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on touched files.

## Implementation outline
1. Re-read `src/codegenie/types/identifiers.py` end-to-end (header docstring tells you where Phase-3 catalog ends and Phase-9 begins).
2. Append a new section header `# --- Phase-9 catalog (S1-01) ---` after the Phase-3 catalog.
3. Add the seven `NewType` declarations with single-line provenance comments. `WorkflowSeq` is `int`-backed; the rest are `str`-backed.
4. Extend the module's `__all__` (additive — do not reorder) and the `_DEFINITIONS` description map.
5. Create `src/codegenie/types/credentials.py` with five frozen Pydantic credential classes (each carrying exactly one string field — e.g., `GitHubToken.value: str`) and the `SECRET_TYPES: Final[frozenset[type]] = frozenset({...})` registry.
6. Land the two test files; iterate until both green and `mypy --strict` is clean.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/types/test_phase09_identifiers.py`
```python
def test_phase09_newtypes_present_and_typed():
    from codegenie.types import identifiers as ids
    # str-backed names
    for name in ("AttemptId", "CorrelationId", "ProjectionId",
                 "TaskQueueName", "ActivityName", "PrUrl"):
        nt = getattr(ids, name)
        assert hasattr(nt, "__supertype__"), f"{name} is not a NewType"
        assert nt.__supertype__ is str, f"{name} must supertype str"
    # int-backed
    assert ids.WorkflowSeq.__supertype__ is int

def test_phase09_newtypes_in_dunder_all():
    from codegenie.types import identifiers as ids
    for name in ("AttemptId", "CorrelationId", "WorkflowSeq", "ProjectionId",
                 "TaskQueueName", "ActivityName", "PrUrl"):
        assert name in ids.__all__, f"{name} missing from __all__"
```

Test file path: `tests/unit/types/test_phase09_secret_types.py`
```python
def test_secret_types_registry_membership():
    from codegenie.types.credentials import (
        SECRET_TYPES, GitHubToken, LlmApiKey, MicroVmCredential,
        PostgresPassword, SshPrivateKey,
    )
    assert SECRET_TYPES == frozenset({
        GitHubToken, LlmApiKey, MicroVmCredential,
        PostgresPassword, SshPrivateKey,
    })
    assert len(SECRET_TYPES) == 5

def test_secret_types_are_frozen_pydantic():
    from pydantic import BaseModel
    from codegenie.types.credentials import SECRET_TYPES
    for cls in SECRET_TYPES:
        assert issubclass(cls, BaseModel)
        cfg = cls.model_config
        assert cfg.get("frozen") is True
        assert cfg.get("extra") == "forbid"
```

### Green — make it pass
Append seven `NewType` lines + `__all__`/`_DEFINITIONS` entries to `identifiers.py`. Create `credentials.py` with five Pydantic classes (single `value: str` field each) plus the `Final[frozenset[type]]` registry.

### Refactor — clean up
- Provenance comment on every new Newtype: `# Phase-9 S1-01 — <one line of why>`.
- `credentials.py` carries a module-level docstring citing ADR-0008 §"typed-credential-class blocklist".
- `SECRET_TYPES` must be `Final` after import — do not expose a mutator.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/types/identifiers.py` | Append seven Phase-9 Newtypes additively |
| `src/codegenie/types/credentials.py` | New module — five credential classes + `SECRET_TYPES` registry |
| `tests/unit/types/test_phase09_identifiers.py` | New — assert Newtypes are present and properly typed |
| `tests/unit/types/test_phase09_secret_types.py` | New — assert `SECRET_TYPES` membership + frozen/forbid config |

## Out of scope
- **`@critical_event` registry** — landed by S1-03.
- **`EventPayload` discriminated union** — landed by S1-02; consumes these Newtypes but does not require them to ship first beyond `WorkflowId`/`EventId`/`BlobDigest` (already present).
- **`RedactedActivityResult.seal()` consumption of `SECRET_TYPES`** — Step 3 (S3-06) wires the sanitizer; this story only lands the registry.
- **Smart-constructor parsers** for the Newtypes (e.g., `WorkflowId.parse(...)`) — Phase-9 does not need them; consumers cast at module boundaries.

## Notes for the implementer
- `WorkflowId`, `EventId`, `BlobDigest`, `TaskClassId` already exist in `identifiers.py` (Phase-3 S1-01) — do **not** redefine them; just import-and-use elsewhere.
- The arch's "Newtype identifiers (Contract)" code block shows `ActivityName = NewType("ActivityName", str)` — `str`-backed throughout except `WorkflowSeq`.
- `SECRET_TYPES` is the *type* registry, not a value registry — each member is a class, not an instance. The frozenset is over `type` objects.
- Pydantic v2 `model_config = ConfigDict(frozen=True, extra="forbid")` on every credential class; the inner `value: str` field is fine — the security guarantee is the *type* of the field downstream consumers declare, not the field name.
- `__all__` is the public surface — append to keep the existing tail alphabetization if `identifiers.py` already maintains alphabetical order; otherwise just append.
- Do not over-engineer credential classes with secret-handling logic (no `SecretStr`, no `__repr__` masking) — that's Step 3's sanitizer's job.
