# Story S1-06 — `LangGraphCheckpointerPort` Protocol + capability types

**Step:** Step 1 — Domain primitives, typed event contracts, and structural fences
**Status:** Ready
**Effort:** S
**Depends on:** S1-01, S1-04
**ADRs honored:** ADR-0008 (typed-credential blocklist + capability pattern — process-level, not cryptographic), ADR-0011 (Postgres checkpointer adapter behind a port), production ADR-0043 (additive Capability types)

## Context
Two contracts must exist before any code that consumes them ships: (1) the `LangGraphCheckpointerPort` Protocol that S5-01's `PostgresCheckpointerAdapter` will implement (arch §C4 — adapter port, not "forwarder"); (2) the three Capability types (`EventLogWriteCapability`, `PrOpenCapability`, `LlmSpendCapability`) that activities will thread explicitly per ADR-0008. ADR-0008's load-bearing claim is that the *type* of a field is the trust root — `mypy --strict` and `tests/fence/test_activity_payload_typing.py` (S4-06) need these types to exist before they bite. The Capability records are Pydantic-frozen-forbid; **no HMAC**.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C4 — Postgres checkpointer adapter` — `LangGraphCheckpointerPort` Protocol shape; `CheckpointerHealth(pool_in_use, pool_idle, last_write_age_seconds)`
  - `../phase-arch-design.md §Capability types (Contract)` — `EventLogWriteCapability` / `PrOpenCapability` / `LlmSpendCapability` exact fields
  - `../phase-arch-design.md §Design patterns applied #9 — Capability pattern (process-level, not cryptographic)` — explicit-thread + max 3 frames; no `ContextVar`
- **Phase ADRs:**
  - `../ADRs/0008-typed-credential-blocklist-not-regex.md` — Consequences §"Capability tokens are typed Pydantic records, **not** cryptographically signed; threaded as explicit arguments — no `ContextVar`"
  - `../ADRs/0011-checkpointer-backend-postgres.md` — Postgres-as-default; `LangGraphCheckpointerPort` is the port behind which the adapter lives
  - `../ADRs/0013-no-temporal-port-abstraction.md` — *contrasts* with this story: a `TemporalPort` is rejected as ceremony; the `LangGraphCheckpointerPort` lives because it's a genuine Adapter port for upstream-class wrapping
- **Production ADRs:**
  - `../../../production/adrs/0016-checkpointer-backend.md` — Postgres-as-default mandate; phase ADR-0011 resolves it
  - `../../../production/adrs/0008-secret-redaction.md` — secret-redaction discipline; capability is the structured alternative to credential-in-payload
- **Source design:**
  - `../final-design.md §Synthesis ledger — Capability-as-Pydantic-record row`
- **Existing code:**
  - `src/codegenie/types/identifiers.py` — `TaskQueueName`, `WorkflowId` (landed by S1-01)
  - `langgraph_checkpoint_postgres.PostgresSaver` (pinned in `pyproject.toml`) — the wrapped class; for now this story does *not* import it, only declares the Port the adapter will satisfy
- **External docs:**
  - `https://langchain-ai.github.io/langgraph/reference/checkpoints/#basecheckpointsaver` — `BaseCheckpointSaver` upstream type; the Port returns one via `saver()`

## Goal
Ship `src/codegenie/durable/checkpointer.py` with the `LangGraphCheckpointerPort` Protocol + `CheckpointerHealth` Pydantic record, and `src/codegenie/durable/capabilities.py` with the three Capability types. Both ship without their adapter implementations (those are Step 5 + Step 6).

## Acceptance criteria
- [ ] `src/codegenie/durable/checkpointer.py` exports:
  - `CheckpointerHealth` frozen Pydantic `BaseModel` (`ConfigDict(frozen=True, extra="forbid")`) with `pool_in_use: NonNegativeInt`, `pool_idle: NonNegativeInt`, `last_write_age_seconds: NonNegativeFloat`.
  - `@runtime_checkable class LangGraphCheckpointerPort(Protocol)` with `saver(self) -> BaseCheckpointSaver` and `health(self) -> CheckpointerHealth`.
- [ ] `src/codegenie/durable/capabilities.py` exports:
  - `EventLogWriteCapability(BaseModel)`: `task_queue: TaskQueueName`, `allowed_kinds: frozenset[str]`, `minted_at: datetime`.
  - `PrOpenCapability(BaseModel)`: `repo: RepoId | str` (use `RepoId` if already typed in the codebase; else `str` with a comment marking the future Newtype promotion), `expires_at: datetime`.
  - `LlmSpendCapability(BaseModel)`: `budget_remaining_usd: Decimal`, `workflow_id: WorkflowId`.
  - Every Capability class uses `ConfigDict(frozen=True, extra="forbid")`.
- [ ] `tests/unit/durable/test_capability_records.py` covers: (a) construction with valid values succeeds; (b) `frozen=True` enforced — mutating raises `ValidationError`; (c) `extra="forbid"` enforced — unknown field raises `ValidationError`; (d) `allowed_kinds` round-trips as `frozenset[str]` via `model_dump_json`/`model_validate_json`.
- [ ] `tests/unit/durable/test_checkpointer_port.py` covers: (a) `CheckpointerHealth` construction validates; (b) a deliberately constructed dummy class with `saver()` + `health()` methods satisfies `isinstance(x, LangGraphCheckpointerPort)`; (c) a class missing `health()` does *not* satisfy the Protocol.
- [ ] `tests/fence/test_capabilities_no_hmac_field.py` greps `src/codegenie/durable/capabilities.py` for tokens that would indicate cryptographic-capability drift (`hmac`, `signature`, `signed_by`, `sign_key`); zero matches (ADR-0008 fence).
- [ ] `mypy --strict src/codegenie/durable/` is clean.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on touched files.

## Implementation outline
1. Create `src/codegenie/durable/checkpointer.py`:
   - Module docstring citing ADR-0011 + the Port-not-Forwarder reasoning from arch §C4.
   - `CheckpointerHealth` Pydantic model.
   - `LangGraphCheckpointerPort(Protocol)` with `@runtime_checkable`; the `saver()` return-type is `BaseCheckpointSaver` (`from langgraph.checkpoint.base import BaseCheckpointSaver`).
2. Create `src/codegenie/durable/capabilities.py`:
   - Module docstring citing ADR-0008 §"Capability tokens are typed Pydantic records, not cryptographically signed".
   - Three Capability classes; one common ConfigDict.
3. Land the unit tests + the no-HMAC fence.
4. `mypy --strict`; iterate until clean.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/durable/test_capability_records.py`
```python
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from pydantic import ValidationError
from codegenie.types.identifiers import TaskQueueName, WorkflowId

def test_event_log_write_capability_round_trip():
    from codegenie.durable.capabilities import EventLogWriteCapability
    cap = EventLogWriteCapability(
        task_queue=TaskQueueName("system"),
        allowed_kinds=frozenset({"workflow_started", "merge_outcome"}),
        minted_at=datetime.now(tz=timezone.utc),
    )
    revived = EventLogWriteCapability.model_validate_json(cap.model_dump_json())
    assert revived == cap
    assert isinstance(revived.allowed_kinds, frozenset)

def test_capability_is_frozen():
    from codegenie.durable.capabilities import LlmSpendCapability
    cap = LlmSpendCapability(
        budget_remaining_usd=Decimal("10.00"),
        workflow_id=WorkflowId("wf-1"),
    )
    with pytest.raises(ValidationError):
        cap.budget_remaining_usd = Decimal("0.00")  # type: ignore[misc]

def test_capability_extra_forbid():
    from codegenie.durable.capabilities import PrOpenCapability
    with pytest.raises(ValidationError):
        PrOpenCapability(
            repo="org/x",
            expires_at=datetime.now(tz=timezone.utc),
            stray="nope",  # type: ignore[call-arg]
        )
```

Test file path: `tests/unit/durable/test_checkpointer_port.py`
```python
def test_checkpointer_health_validates():
    from codegenie.durable.checkpointer import CheckpointerHealth
    h = CheckpointerHealth(pool_in_use=2, pool_idle=8, last_write_age_seconds=0.5)
    assert h.pool_in_use == 2

def test_dummy_satisfies_port():
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from codegenie.durable.checkpointer import (
        LangGraphCheckpointerPort, CheckpointerHealth,
    )
    class _Dummy:
        def saver(self) -> BaseCheckpointSaver: ...
        def health(self) -> CheckpointerHealth:
            return CheckpointerHealth(pool_in_use=0, pool_idle=0,
                                       last_write_age_seconds=0.0)
    assert isinstance(_Dummy(), LangGraphCheckpointerPort)

def test_missing_health_fails_port_check():
    from codegenie.durable.checkpointer import LangGraphCheckpointerPort
    class _NoHealth:
        def saver(self): ...
    assert not isinstance(_NoHealth(), LangGraphCheckpointerPort)
```

Test file path: `tests/fence/test_capabilities_no_hmac_field.py`
```python
def test_no_cryptographic_signing_in_capabilities():
    from pathlib import Path
    src = Path("src/codegenie/durable/capabilities.py").read_text().lower()
    for token in ("hmac", "signature", "signed_by", "sign_key"):
        assert token not in src, (
            f"{token!r} found in capabilities.py — ADR-0008 §'Capability "
            "tokens are typed Pydantic records, NOT cryptographically signed'"
        )
```

### Green — make it pass
Two files; six classes total. Capability records use `Pydantic.NonNegativeFloat` / `NonNegativeInt` from `pydantic.types` where applicable.

### Refactor — clean up
- `CheckpointerHealth` docstring cites arch §C4 "the upstream class does not expose this, which is the translation that earns the 'Adapter' name".
- `LangGraphCheckpointerPort` docstring cites the contrast with ADR-0013 (no `TemporalPort`) — this Port lives because it wraps an upstream class with a non-trivial translation; a Temporal Port would be a forwarder.
- All capability docstrings cite "no HMAC; trust root is the worker process" so a future contributor doesn't drift toward signed capabilities.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/durable/checkpointer.py` | `LangGraphCheckpointerPort` Protocol + `CheckpointerHealth` |
| `src/codegenie/durable/capabilities.py` | Three Capability types |
| `tests/unit/durable/test_capability_records.py` | Round-trip + frozen + extra-forbid |
| `tests/unit/durable/test_checkpointer_port.py` | Protocol runtime-check positive + negative |
| `tests/fence/test_capabilities_no_hmac_field.py` | No-cryptographic-drift fence |

## Out of scope
- **`PostgresCheckpointerAdapter` implementation** — Step 5 (S5-01); this story ships only the Port.
- **`alembic_init` migration / `langgraph_checkpoint_postgres` schema setup** — Step 2.
- **Capability *minting* from K8s ServiceAccount mount** — Step 6 (S6-02); this story ships only the Pydantic records.
- **`EventLogWriteCapability.allowed_kinds` validation against `_CRITICAL_EVENTS`** — Step 3/4 enforcement.
- **`RepoId` Newtype** — promote in a follow-up if not already in `identifiers.py`; for now `PrOpenCapability.repo` may be plain `str` with a comment.

## Notes for the implementer
- `BaseCheckpointSaver` lives at `from langgraph.checkpoint.base import BaseCheckpointSaver` (pinned in `pyproject.toml`). The Port uses it as a return type only; no instances are constructed in Phase-9 Step-1.
- `frozenset[str]` is JSON-serializable by Pydantic v2 — verifying it round-trips via `model_dump_json` is the cheap defense against a `set[str]` typo.
- `Decimal` for `budget_remaining_usd` is load-bearing (G11 cost-tracking discipline + production ADR-0040 audit-class retention); do **not** use `float`.
- The Capability classes are intentionally *thin* records — no methods. ADR-0008's "max 3 frames worker → activity wrapper → side-effect site" is a *threading* discipline; the record itself is just data.
- The no-HMAC fence (`test_capabilities_no_hmac_field.py`) is the structural defense against a Step-6/7 contributor adding signed capabilities in a "while we're here" moment. Keep the fence minimal but loud.
- `LangGraphCheckpointerPort.saver()` returns a `BaseCheckpointSaver`. The arch shows `def saver(self) -> BaseCheckpointSaver: ...` — that's an abstract method on the Protocol; concrete classes implement it (Step 5).
- The arch (§"Class diagram") shows `runtime_checkable` on the projection Protocol — apply the same decorator to `LangGraphCheckpointerPort` so the fence test can `isinstance()`-check conformance without importing the concrete adapter.
