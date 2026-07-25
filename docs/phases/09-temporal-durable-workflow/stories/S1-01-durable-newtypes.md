# Story S1-01 — Newtype identifiers for the durable substrate

**Step:** Step 1 — Domain primitives, typed event contracts, and structural fences
**Status:** HARDENED
**Effort:** S
**Depends on:** —
**ADRs honored:** production ADR-0033, production ADR-0043, Phase-9 ADR-0008

## Validation notes (2026-07-24)

Hardened via `/phase-story-validator`. Full report:
[`_validation/S1-01-durable-newtypes.md`](_validation/S1-01-durable-newtypes.md).

- **Corrected `AttemptId` duplication (Consistency-BLOCK).** The original
  story listed **seven** new Newtypes including `AttemptId`. `AttemptId`
  was already landed in Phase-4 S1-01 (`src/codegenie/types/identifiers.py`
  line 168, `_NEWTYPE_REGISTRY` entry). Reduced to **six** genuinely-new
  additions: `CorrelationId`, `WorkflowSeq`, `ProjectionId`, `TaskQueueName`,
  `ActivityName`, `PrUrl`. `AttemptId` joins the "already exists — reuse,
  do not redefine" list.
- **Corrected `_DEFINITIONS` → `_NEWTYPE_REGISTRY` (Consistency-BLOCK).**
  Original story named a non-existent module symbol; actual registry is
  `_NEWTYPE_REGISTRY` at `identifiers.py` line 314.
- **Added existing-test drift-fence extension (Coverage-BLOCK).**
  `tests/unit/types/test_identifiers_phase3.py` carries three exact-set
  drift-fences (`test_all_is_exact_set`, `test_newtype_registry_matches_all`,
  and the shape of `test_pairwise_distinct`) that fail on any addition to
  `__all__`. Now covered explicitly by AC and Files-to-touch — sanctioned
  loud edits per production ADR-0043 §1.
- **Strengthened credential-class tests (Test-Quality-HARDEN).** Model-
  config introspection alone would pass with `frozen=False, extra="ignore"`
  if the raw-dict form is used. Added behavioural tests: instance mutation
  must raise; extra field at construction must raise; `SECRET_TYPES` must
  be a runtime `frozenset` (Final is a type-checker hint only) that
  refuses `.add`.
- **Added pairwise-distinct + int-swap fences (Test-Quality-HARDEN).**
  `WorkflowSeq is not AttemptNumber` and Phase-9 pairwise distinctness.
- **Design-pattern notes added.** `SECRET_TYPES` frozenset-as-registry is
  correct at day-1 scale (rule of three met); the smart-constructor parser
  trigger for Phase-9 IDs surfaces at the third external-input callsite.

## Context
Every later Phase-9 story (the EventPayload union, the activity registry, the workflow body, the Postgres schema) threads `WorkflowId`, `EventId`, `AttemptId`, `WorkflowSeq`, `ProjectionId`, `TaskQueueName`, `ActivityName`, `CorrelationId`, and `PrUrl` simultaneously — `mypy --strict` must reject confusing one for another at compile time. The kernel-tier `codegenie.types.identifiers` module already ships the Phase-1/2/3/4/6/7 catalog (including `WorkflowId`, `EventId`, `BlobDigest`, `TaskClassId`, **and `AttemptId`** — the last landed in Phase-4 S1-01 as the `AttemptAnchor` primary key); this story adds the **six** genuinely-new Phase-9 names additively (production ADR-0043 §1 — loud compiler-policed edits are the enforcement mechanism, not violations) and lands the typed-credential class registry under `codegenie.types.credentials` so the sanitizer in Step 3 can blocklist by *type*, not name or value (Phase-9 ADR-0008's load-bearing layer (b)).

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Data model — Newtype identifiers (Contract)` — names + intent for each Newtype. **Caveat:** the arch's contract block lists 11 names as "additions" but four of them (`WorkflowId`, `EventId`, `BlobDigest`, `AttemptId`) and one closed-set (`TaskClassId`) already ship in `identifiers.py`; the *genuinely-new* Phase-9 additions are six.
  - `../phase-arch-design.md §Capability types (Contract)` — `EventLogWriteCapability`/`PrOpenCapability`/`LlmSpendCapability` reference `TaskQueueName` + `WorkflowId`
  - `../phase-arch-design.md §Design patterns applied #3 — Newtype for domain identifiers` — what these buy; the arch explicitly declines smart-constructor parsers on `WorkflowId` ("bare Newtype is fine; the constructor would be ceremonial")
- **Phase ADRs:**
  - `../ADRs/0008-typed-credential-blocklist-not-regex.md` — `SECRET_TYPES` is the trust root; load-bearing layer (b) of `RedactedActivityResult.seal()`
- **Production ADRs:**
  - `../../../production/adrs/0033-sum-types-for-domain-state.md` — primitive-obsession is a review blocker; `NewType` is the canonical fix
  - `../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md` §1 — adding a `Literal`/`Enum` member, appending to `__all__`, extending `_NEWTYPE_REGISTRY`, and extending a per-phase test set are **loud compiler-/snapshot-policed edits** — sanctioned enforcement mechanism, not violations
- **Source design:**
  - `../final-design.md §Synthesis ledger` — Phase-9 type catalog row
- **Existing code:**
  - `src/codegenie/types/identifiers.py` — Phase-1/2/3/4/6/7 catalog already present; `WorkflowId`, `EventId`, `BlobDigest`, `TaskClassId`, **`AttemptId`** already exist (do **not** redefine)
  - `src/codegenie/types/identifiers.py §__all__` (line 254) — strictly alphabetized; append additively and preserve the sort
  - `src/codegenie/types/identifiers.py §_NEWTYPE_REGISTRY` (line 314) — the machine-verifiable docstring registry (**not** `_DEFINITIONS`); each new Newtype gets one row with a Phase-9-specific ADR citation
- **Existing tests (drift-fences that MUST be extended, ADR-0043 §1 loud edits):**
  - `tests/unit/types/test_identifiers_phase3.py::test_all_is_exact_set` — exact-set equality; add `PHASE9_NEWTYPE_NAMES` to the union
  - `tests/unit/types/test_identifiers_phase3.py::test_newtype_registry_matches_all` — add a Phase-9 branch asserting the docstring cites production ADR-0033 + Phase-9 ADR-0008
  - Precedent for how this extension shape lands: the Phase-4/6/7 `PHASE*_NAMES` sets already in that file (lines 253–284)

## Goal
Add the **six** new Phase-9 Newtypes (`CorrelationId`, `WorkflowSeq`, `ProjectionId`, `TaskQueueName`, `ActivityName`, `PrUrl`) to `codegenie.types.identifiers` — additively, preserving alphabetization — and ship the `SECRET_TYPES` typed-credential registry under `codegenie.types.credentials` (five frozen Pydantic classes: `GitHubToken`, `LlmApiKey`, `MicroVmCredential`, `PostgresPassword`, `SshPrivateKey`). Extend the existing Phase-3 test-file drift-fences so `__all__` and `_NEWTYPE_REGISTRY` remain the source of truth for the identifier catalog.

## Acceptance criteria
- [ ] `codegenie.types.identifiers` exports the **six** new Newtypes: `CorrelationId`, `WorkflowSeq` (int-backed), `ProjectionId`, `TaskQueueName`, `ActivityName`, `PrUrl`.
- [ ] Each new Newtype appears in the module's `__all__` (which remains strictly sorted per `test_all_is_exact_set`'s `ids.__all__ == sorted(ids.__all__)` sentinel) and in `_NEWTYPE_REGISTRY` (**not** `_DEFINITIONS`) with a one-line docstring citing **both** production ADR-0033 **and** Phase-9 ADR-0008 (or ADR-0010 — whichever the extended `test_newtype_registry_matches_all` Phase-9 branch enforces; see the next AC).
- [ ] `codegenie.types.identifiers` is *not* edited to redefine `WorkflowId`, `EventId`, `BlobDigest`, `TaskClassId`, or **`AttemptId`** (all already exist; reuse via import).
- [ ] `codegenie.types.credentials` ships `GitHubToken`, `LlmApiKey`, `MicroVmCredential`, `PostgresPassword`, `SshPrivateKey` (each a frozen Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")` and one `value: str` field) and `SECRET_TYPES: Final[frozenset[type]]` containing exactly those five types.
- [ ] `mypy --strict src/codegenie/types/` is clean.
- [ ] `tests/unit/types/test_phase09_identifiers.py` asserts:
  - each new name is `NewType`-backed (`hasattr(nt, "__supertype__")`)
  - `WorkflowSeq.__supertype__ is int`; the other five supertype `str`
  - `WorkflowSeq is not AttemptNumber` (both int-backed; must not accidentally alias)
  - the six new names are pairwise distinct objects (`test_phase09_pairwise_distinct`)
  - the six new names are present in `identifiers.__all__` and `identifiers.__all__ == sorted(identifiers.__all__)` (alphabetization sentinel)
- [ ] `tests/unit/types/test_phase09_secret_types.py` asserts:
  - `SECRET_TYPES == frozenset({GitHubToken, LlmApiKey, MicroVmCredential, PostgresPassword, SshPrivateKey})` and `len(SECRET_TYPES) == 5`
  - `SECRET_TYPES` is a runtime `frozenset` — `isinstance(SECRET_TYPES, frozenset)` and `with pytest.raises(AttributeError): SECRET_TYPES.add(str)` (Final is a type-checker hint; frozenness must be enforced at runtime)
  - every member is a Pydantic v2 `BaseModel` subclass with `model_config["frozen"] is True` and `model_config["extra"] == "forbid"`
  - **behavioural mutation test:** for one representative credential class, `tok = GitHubToken(value="ghp_x"); with pytest.raises(pydantic.ValidationError): tok.value = "ghp_y"`
  - **behavioural extra-field test:** `with pytest.raises(pydantic.ValidationError): GitHubToken(value="ghp_x", extra="oops")`
- [ ] `tests/unit/types/test_identifiers_phase3.py` gains:
  - a `PHASE9_NEWTYPE_NAMES = {"CorrelationId", "WorkflowSeq", "ProjectionId", "TaskQueueName", "ActivityName", "PrUrl"}` module-level constant
  - the set appears in the `test_all_is_exact_set` union (alongside the existing Phase-2/3/4/6/7 sets)
  - `test_newtype_registry_matches_all` grows a `PHASE9_NEWTYPE_NAMES` branch asserting the docstring cites production ADR-0033 **and** either "Phase-9 ADR-0008" or "ADR-0010" (pick one, use it consistently in the docstrings)
- [ ] The TDD-plan red tests were committed and then transitioned to green (attempt log records both the red output and the green output).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/types/` all pass on touched files (no `--no-cov` shortcut — the whole `tests/unit/types/` suite is covered by the coverage-fence baseline).

## Implementation outline
1. Re-read `src/codegenie/types/identifiers.py` end-to-end. Note the phase-section header pattern (`# --- Phase-N catalog (S…) ---`) and confirm `AttemptId` is at line 168 in the Phase-4 section — do **not** touch it.
2. Append a new section header `# --- Phase-9 catalog (S1-01) ---` after the Phase-7 catalog (before `__all__`).
3. Add the **six** `NewType` declarations with single-line provenance comments (`# Phase-9 S1-01 — <one line of why>`). `WorkflowSeq` is `int`-backed; the rest are `str`-backed.
4. Extend `__all__` with the six new names, preserving strict alphabetization (`test_all_is_exact_set` fails otherwise). Extend `_NEWTYPE_REGISTRY` with six new rows; each docstring **must** cite production ADR-0033 **and** Phase-9 ADR-0008 (naming both is unambiguous; the `test_newtype_registry_matches_all` Phase-9 branch will assert the citation).
5. Create `src/codegenie/types/credentials.py` with five frozen Pydantic credential classes (each carrying `value: str` and `model_config = ConfigDict(frozen=True, extra="forbid")`) and `SECRET_TYPES: Final[frozenset[type]] = frozenset({...})`. Module docstring cites Phase-9 ADR-0008 §"typed-credential-class blocklist".
6. Extend `tests/unit/types/test_identifiers_phase3.py`: add `PHASE9_NEWTYPE_NAMES`, add it to the `test_all_is_exact_set` union, and add a Phase-9 branch to `test_newtype_registry_matches_all` that mirrors the Phase-4/6/7 pattern. This is a sanctioned loud edit per production ADR-0043 §1.
7. Land the two new test files; iterate red → green until both green and `mypy --strict` on `src/codegenie/types/` is clean.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/types/test_phase09_identifiers.py`
```python
from __future__ import annotations

import pytest

PHASE9_NEW = ("CorrelationId", "ProjectionId", "TaskQueueName", "ActivityName", "PrUrl")


def test_phase09_str_newtypes_present_and_typed() -> None:
    from codegenie.types import identifiers as ids
    for name in PHASE9_NEW:
        nt = getattr(ids, name)
        assert hasattr(nt, "__supertype__"), f"{name} is not a NewType"
        assert nt.__supertype__ is str, f"{name} must supertype str"


def test_workflow_seq_is_int_backed_and_distinct_from_attempt_number() -> None:
    from codegenie.types import identifiers as ids
    assert hasattr(ids.WorkflowSeq, "__supertype__")
    assert ids.WorkflowSeq.__supertype__ is int
    # Both are int-backed — accidentally aliasing them would make mypy accept
    # a per-workflow monotonic where a retry counter is expected (and vice
    # versa). Distinct object identity is the compile-time defence.
    assert ids.WorkflowSeq is not ids.AttemptNumber


def test_phase09_names_in_dunder_all_and_sorted() -> None:
    from codegenie.types import identifiers as ids
    for name in (*PHASE9_NEW, "WorkflowSeq"):
        assert name in ids.__all__, f"{name} missing from __all__"
    # Existing sentinel: __all__ must remain strictly sorted.
    assert ids.__all__ == sorted(ids.__all__), "__all__ must be alphabetically sorted"


def test_phase09_pairwise_distinct() -> None:
    from codegenie.types import identifiers as ids
    names = sorted((*PHASE9_NEW, "WorkflowSeq"))
    objs = [getattr(ids, n) for n in names]
    for i, a in enumerate(objs):
        for b in objs[i + 1 :]:
            assert a is not b, "two Phase-9 NewTypes accidentally alias"
```

Test file path: `tests/unit/types/test_phase09_secret_types.py`
```python
from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError


def test_secret_types_registry_membership() -> None:
    from codegenie.types.credentials import (
        SECRET_TYPES, GitHubToken, LlmApiKey, MicroVmCredential,
        PostgresPassword, SshPrivateKey,
    )
    assert SECRET_TYPES == frozenset({
        GitHubToken, LlmApiKey, MicroVmCredential,
        PostgresPassword, SshPrivateKey,
    })
    assert len(SECRET_TYPES) == 5


def test_secret_types_is_runtime_frozenset() -> None:
    """``Final`` is a type-checker hint; frozenness must hold at runtime too."""
    from codegenie.types.credentials import SECRET_TYPES
    assert isinstance(SECRET_TYPES, frozenset)
    with pytest.raises(AttributeError):
        SECRET_TYPES.add(str)  # type: ignore[attr-defined]


def test_secret_types_are_frozen_pydantic_config() -> None:
    from codegenie.types.credentials import SECRET_TYPES
    for cls in SECRET_TYPES:
        assert issubclass(cls, BaseModel)
        cfg = cls.model_config
        assert cfg.get("frozen") is True, f"{cls.__name__} not frozen in config"
        assert cfg.get("extra") == "forbid", f"{cls.__name__} extra != forbid"


def test_credential_instance_rejects_mutation() -> None:
    """Introspecting ``model_config`` alone would pass for a wrongly-shaped
    class; this test catches the case where the config is a plain dict that
    Pydantic ignores, or where ``frozen=True`` is claimed but not enforced."""
    from codegenie.types.credentials import GitHubToken
    tok = GitHubToken(value="ghp_x")
    with pytest.raises(ValidationError):
        tok.value = "ghp_y"  # type: ignore[misc]


def test_credential_instance_rejects_extra_field() -> None:
    from codegenie.types.credentials import GitHubToken
    with pytest.raises(ValidationError):
        GitHubToken(value="ghp_x", extra="oops")  # type: ignore[call-arg]
```

Existing-file extension (`tests/unit/types/test_identifiers_phase3.py`) — add near the other `PHASE*_NAMES` constants:
```python
# Phase 9 S1-01 — durable-substrate additions.
PHASE9_NEWTYPE_NAMES = {
    "CorrelationId",
    "WorkflowSeq",
    "ProjectionId",
    "TaskQueueName",
    "ActivityName",
    "PrUrl",
}
```
…and:
- add `| PHASE9_NEWTYPE_NAMES` to the `test_all_is_exact_set` union
- add a branch to `test_newtype_registry_matches_all`:
  ```python
  elif name in PHASE9_NEWTYPE_NAMES:
      assert "ADR-0033" in doc, f"{name} Phase-9 docstring missing production ADR-0033 citation"
      assert "ADR-0008" in doc or "ADR-0010" in doc, (
          f"{name} Phase-9 docstring missing Phase-9 ADR-0008 (or ADR-0010) citation"
      )
  ```

### Green — make it pass
Append six `NewType` lines + `__all__`/`_NEWTYPE_REGISTRY` entries to `identifiers.py`, preserving alphabetization of `__all__`. Create `credentials.py` with five Pydantic classes (single `value: str` field each, `model_config = ConfigDict(frozen=True, extra="forbid")`) plus the `Final[frozenset[type]]` registry. Extend `test_identifiers_phase3.py` with the `PHASE9_NEWTYPE_NAMES` set and the two additive assertions.

### Refactor — clean up
- Provenance comment on every new Newtype: `# Phase-9 S1-01 — <one line of why>`.
- `credentials.py` carries a module-level docstring citing Phase-9 ADR-0008 §"typed-credential-class blocklist".
- `SECRET_TYPES` must remain a runtime `frozenset` after import — do not expose a mutator or replace it with a plain set.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/types/identifiers.py` | Append six Phase-9 Newtypes additively; extend `__all__` (sorted) and `_NEWTYPE_REGISTRY` |
| `src/codegenie/types/credentials.py` | New module — five credential classes + `SECRET_TYPES` registry |
| `tests/unit/types/test_phase09_identifiers.py` | New — assert Newtypes present, properly typed, alphabetized, pairwise-distinct, and `WorkflowSeq` distinct from `AttemptNumber` |
| `tests/unit/types/test_phase09_secret_types.py` | New — assert `SECRET_TYPES` membership + runtime frozenset + frozen/forbid model config + behavioural mutation and extra-field rejection |
| `tests/unit/types/test_identifiers_phase3.py` | **Extend** existing drift-fences — add `PHASE9_NEWTYPE_NAMES` constant to `test_all_is_exact_set` union and a Phase-9 branch to `test_newtype_registry_matches_all`. Sanctioned loud edit per production ADR-0043 §1. |

## Out of scope
- **`@critical_event` registry** — landed by S1-03.
- **`EventPayload` discriminated union** — landed by S1-02; consumes these Newtypes but does not require them to ship first beyond `WorkflowId`/`EventId`/`BlobDigest`/`AttemptId` (all already present).
- **`RedactedActivityResult.seal()` consumption of `SECRET_TYPES`** — Step 3 (S3-06) wires the sanitizer; this story only lands the registry.
- **Smart-constructor parsers** for the Newtypes (e.g., `WorkflowId.parse(...)`) — Phase-9 does not need them; the arch explicitly declines them for `WorkflowId` ("bare Newtype is fine; the constructor would be ceremonial"). Rule-of-three trigger for a later phase: three external-input construction callsites for the same NewType.

## Notes for the implementer
- **The already-exists list is:** `WorkflowId`, `EventId`, `BlobDigest`, `TaskClassId`, and `AttemptId`. The arch's contract block lists all of these (plus the six new names) as "additions" — that framing is descriptive of the *complete* Phase-9-relevant set, not of what this story physically adds. This story adds exactly six.
- The arch's "Newtype identifiers (Contract)" code block shows `ActivityName = NewType("ActivityName", str)` — `str`-backed throughout except `WorkflowSeq`.
- **`SECRET_TYPES` is a type registry, not a value registry** — each member is a class, not an instance. The frozenset is over `type` objects. Adding a sixth secret type is one line in the frozenset + one new Pydantic class — no `@register_credential_type(…)` decorator machinery (five members day-1; the ceremony would exceed the benefit; a frozenset with a compiler-policed edit satisfies ADR-0043's Open/Closed criterion).
- Pydantic v2: `model_config = ConfigDict(frozen=True, extra="forbid")` on every credential class; the inner `value: str` field is fine — the security guarantee is the *type* of the field downstream consumers declare, not the field name. Behavioural tests (mutation + extra-field) fence the config against `model_config = {"frozen": True, ...}` (raw dict, ignored by Pydantic) or `frozen=False, extra="ignore"` typos.
- Do not over-engineer credential classes with secret-handling logic (no `SecretStr`, no `__repr__` masking) — that's Step 3's sanitizer's job.
- `__all__` is the public surface AND a snapshot-tested contract (`test_all_is_exact_set` asserts `set(__all__) == PHASE2∪PHASE3∪…∪PHASE9` AND `__all__ == sorted(__all__)`). Insert new names in sort order; do not just append.
- `_NEWTYPE_REGISTRY` is the machine-verifiable docstring registry — every name in `__all__ − PHASE7_TYPE_ALIAS_NAMES` MUST appear there with a non-empty docstring citing the correct ADR family for its phase.
- Extending `test_identifiers_phase3.py` (adding a new `PHASE9_NEWTYPE_NAMES` set and one branch) is a **loud compiler-/snapshot-policed edit** and is explicitly permitted by production ADR-0043 §1 ("Edits the compiler or a snapshot test fully polices … are the enforcement mechanism, not violations"). Do not skip this or work around the fence.
- **Rule-of-three parser trigger (deferred, not this story's scope):** when a third external-input callsite emerges that needs to construct a Phase-9 NewType from raw bytes (e.g., a CLI arg + a Postgres row loader + an HTTP body), a smart-constructor parser under `codegenie.types.parsers` becomes justified (mirrors Phase-3 S3-03's `parse_semver` shape). Until then, cast at module boundaries.
