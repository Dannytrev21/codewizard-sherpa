# Story S4-01 — RetryPolicy table + `retry_policies` module

**Step:** Step 4 — Activity catalog (one file per activity, typed in and out, registry-collected)
**Status:** Ready
**Effort:** S
**Depends on:** S1-04 (`@register_activity` kernel + `_ACTIVITIES: dict[ActivityName, ActivityRegistration]`)
**ADRs honored:** ADR-0010 (asymmetric activity granularity — per-activity timeouts); ADR-0007 (two task queues — the policy table is the catalog); production ADR-0034 (G3 — zero application-level retry loops; framework owns retry)

## Context

Phase 9's G3 exit criterion says "all retries are framework-level — application code contains no retry loops." That fence is enforced by S8-05 (`tests/fence/test_no_retry_loop_in_workflow.py`); this story ships the **other half**: the canonical `RetryPolicy` table the workflow body reads, so every `workflow.execute_activity(...)` call can grab its policy from `_POLICIES[activity_name]` instead of inlining a Temporal `RetryPolicy` literal at the call site. The module-level `Final` dict is the load-bearing seam — workflow code becomes pure dispatch over typed names, and the policy catalog becomes the single review surface for "did we bump max_attempts somewhere we shouldn't have?".

Per-activity timeouts come straight from `phase-arch-design.md §C2 Activity catalog`: `resolve_plugin p95 < 50 ms`, `build_bundle p95 < 200 ms`, `route p95 < 20 ms`, `run_vuln_subgraph p50 ~4 min / p95 ~8 min` (timeout `20 min`), `emit_event p95 < 15 ms` (timeout `5 s`), `write_blob_ref` / `resolve_blob_ref` timeout `10 s`, `github_open_pr` timeout `60 s`, `sandbox_build_and_test` timeout `15 min`. **`non_retryable` lists carry the tier-descent triggers** — `RecipeMissedError` and `RagMissedError` are *not* retryable; they signal Phase-4 `FallbackTier` descent which the workflow body owns (`phase-arch-design.md §C1` line 463, "Hidden assumption #3 from critic-1 on [P] fixed here").

**Scope reminder.** S4-01 ships only the table + the `RetryPolicy` Pydantic record + the registry-completeness assertion. The activity *modules* themselves land in S4-02..S4-05; their tests assert `_POLICIES[their_name]` exists. This story is the "policy declarations come before consumers" foundation.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C2 — Activity catalog` (lines 465-486) — public interface for `@register_activity`; per-activity timeouts and `non_retryable` framing.
  - `../phase-arch-design.md §C1 — Workflow worker` (line 463) — `non_retryable` includes tier-descent triggers (`RecipeMissedError`, `RagMissedError`).
  - `../phase-arch-design.md §Anti-patterns avoided` — "while ... retry loop in workflow code" row; `_POLICIES` is the alternative pattern.
- **Phase ADRs:**
  - `../ADRs/0010-activity-granularity-asymmetric.md` §Consequences — `run_vuln_subgraph` is the single fat activity at `20 min`; Supervisor activities (`resolve_plugin`, `build_bundle`, `route`) are short and cheap.
  - `../ADRs/0007-two-task-queue-partitioning-and-expansion-by-addition.md` — defines the two task queues (`vuln-remediation-node-npm`, `system`); policy rows must align (`emit_event` runs on `system`; the rest on `vuln-remediation-node-npm`).
- **Production ADRs:**
  - `../../../production/adrs/0034-event-sourcing-canonical-primitive.md` — frames "retries are infra concerns, not application logic."
- **Existing code (precedent to mirror):**
  - `src/codegenie/probes/registry.py` — module-level `Final` table pattern; the `_POLICIES` dict mirrors this shape.
  - `src/codegenie/types/identifiers.py` — `ActivityName` newtype lands in S1-01; import it.
  - `src/codegenie/depgraph/registry.py:30-38` — sibling deferral docstring for the registry shape.
- **External reference:**
  - `temporalio.common.RetryPolicy` — the wire-shape this story's Pydantic record adapts into.

## Goal

Ship `src/codegenie/durable/activities/retry_policies.py` with a Pydantic `RetryPolicy` model + module-level `Final` `_POLICIES: dict[ActivityName, RetryPolicy]` whose **keys span every name S4-02..S4-05 will register**; expose `policy_for(name: ActivityName) -> RetryPolicy` as the sole read path. Add a registry-completeness test asserting every name in `_POLICIES` is also in `_ACTIVITIES` once all S4-* stories land (today: the table predates the registrations; the test xfails on the rows whose activities are not yet shipped, with explicit per-row markers — see TDD §Required follow-on).

## Acceptance criteria

- [ ] **AC-1 — `RetryPolicy` Pydantic model.** `src/codegenie/durable/activities/retry_policies.py` exports `class RetryPolicy(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")` and exactly these fields: `initial_interval: timedelta`, `backoff_coefficient: float` (default `2.0`), `maximum_interval: timedelta`, `maximum_attempts: int` (≥1), `non_retryable_error_types: tuple[str, ...]` (default `()`), `start_to_close_timeout: timedelta`, `heartbeat_timeout: timedelta | None` (default `None`; required for `run_vuln_subgraph` and `sandbox_build_and_test`).
- [ ] **AC-2 — `_POLICIES` table coverage.** `_POLICIES: Final[Mapping[ActivityName, RetryPolicy]] = MappingProxyType({...})` covers exactly these nine activity names from `phase-arch-design.md §C2`: `resolve_plugin`, `build_bundle`, `route`, `run_vuln_subgraph`, `sandbox_build_and_test`, `github_open_pr`, `emit_event`, `write_blob_ref`, `resolve_blob_ref`. No extra rows; no missing rows. Adding a row requires bumping `_EXPECTED_POLICY_NAMES` (see AC-6).
- [ ] **AC-3 — Per-activity timeout fidelity.** Each row's `start_to_close_timeout` matches `phase-arch-design.md §C2`'s envelope, with explicit timeouts asserted by name (the assertion catches a typo'd `5` vs `50`): `resolve_plugin=30 s`, `build_bundle=120 s`, `route=20 s`, `run_vuln_subgraph=20 min`, `sandbox_build_and_test=15 min`, `github_open_pr=60 s`, `emit_event=5 s`, `write_blob_ref=10 s`, `resolve_blob_ref=10 s`. Each row's `maximum_attempts` ≤ 5; `run_vuln_subgraph` and `sandbox_build_and_test` carry a `heartbeat_timeout=30 s` (sub the Temporal default).
- [ ] **AC-4 — Tier-descent non-retryable list.** `_POLICIES[ActivityName("run_vuln_subgraph")].non_retryable_error_types` includes the string-name of `RecipeMissedError` and `RagMissedError` (the Phase-4 tier-descent triggers — `phase-arch-design.md §C1` line 463). A negative test asserts a Pydantic `extra="forbid"` violation is NOT in the non-retryable list (Pydantic errors are caller-side bugs, not retry signals).
- [ ] **AC-5 — `policy_for(name)` read path + `KeyError` shape.** `policy_for(name: ActivityName) -> RetryPolicy` is the only public read; missing keys raise `KeyError(name)` whose `.args[0]` is the typed `ActivityName` (NOT a stringified message). `policy_for` does NOT fall back to a default policy — silent defaults would defeat the whole G3 narrative.
- [ ] **AC-6 — Registry-completeness assertion (today: tolerant; once S4-02..S4-05 ship: strict).** `tests/unit/durable/activities/test_retry_policies.py::test_every_policy_name_eventually_registers` walks `_POLICIES.keys()` and asserts each name either (a) is in `_ACTIVITIES` (registered) OR (b) is in a module-level `_EXPECTED_BUT_UNSHIPPED: Final[frozenset[ActivityName]]` set that S4-02..S4-05 trim as their activities land. The test fails loud the day all nine activities ship but `_EXPECTED_BUT_UNSHIPPED` is non-empty — that's the executor's signal to delete the constant.
- [ ] **AC-7 — Mutation-resistant table integrity.** A property test (`hypothesis`-based; dev-dep) generates a random `ActivityName` not in `_POLICIES`; asserts `policy_for(name)` raises `KeyError`. A second non-property test asserts `_POLICIES[ActivityName("resolve_plugin")].maximum_attempts == 3` (named identity catches a `return 1` mutant on `maximum_attempts`).
- [ ] **AC-8 — Immutability.** `_POLICIES` is wrapped in `types.MappingProxyType` (or an equivalent `Final[Mapping[...]]` posture). A test asserts `with pytest.raises(TypeError): _POLICIES[ActivityName("x")] = ...` — runtime mutation must fail loud, not silently succeed.
- [ ] **AC-9 — Workflow-import-cleanliness.** `tests/fence/test_workflow_determinism.py` (S1-07) already rejects `random`/`time`/`datetime`/`uuid`/etc. from `codegenie.durable.workflows.*`. This story re-asserts that **`codegenie.durable.activities.retry_policies` is importable from a workflow** (it carries `timedelta` literals only — no `datetime.now`, no `time.sleep`). A targeted test in `tests/unit/durable/activities/test_retry_policies.py` imports the module and asserts no forbidden module appears in `sys.modules` deltas around the import.
- [ ] **AC-10 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean on `src/codegenie/durable/activities/retry_policies.py` and the new test file. `make lint-imports` clean (no new import-linter contract violation).

## Implementation outline

1. Create `src/codegenie/durable/activities/retry_policies.py`:
   - Imports: `from datetime import timedelta`; `from types import MappingProxyType`; `from typing import Final, Mapping`; `from pydantic import BaseModel, ConfigDict, Field`; `from codegenie.types.identifiers import ActivityName`.
   - `class RetryPolicy(BaseModel)` per AC-1.
   - `_POLICIES_RAW: dict[ActivityName, RetryPolicy] = { ActivityName("resolve_plugin"): RetryPolicy(start_to_close_timeout=timedelta(seconds=30), ...), ... }`.
   - `_POLICIES: Final[Mapping[ActivityName, RetryPolicy]] = MappingProxyType(_POLICIES_RAW)`.
   - `_EXPECTED_BUT_UNSHIPPED: Final[frozenset[ActivityName]] = frozenset({ ActivityName("resolve_plugin"), ActivityName("build_bundle"), ... })` — today's transitive set; S4-02..S4-05 trim each row as it ships.
   - `def policy_for(name: ActivityName) -> RetryPolicy: return _POLICIES[name]` — let the bare `KeyError` propagate (AC-5).
   - Module docstring cites ADR-0010 and `phase-arch-design.md §C2`; names this file as the **single review surface for retry posture**.
2. Create `tests/unit/durable/__init__.py` and `tests/unit/durable/activities/__init__.py` (empty markers) if missing.
3. Create `tests/unit/durable/activities/test_retry_policies.py` per the TDD plan below.
4. Wire `_EXPECTED_BUT_UNSHIPPED` to the activity-completeness test (AC-6); S4-02..S4-05 each ship a one-line `_EXPECTED_BUT_UNSHIPPED - {name}` discipline as their AC.

## TDD plan — red / green / refactor

### Red — failing test first

```python
# tests/unit/durable/activities/test_retry_policies.py
import pytest
from datetime import timedelta

from codegenie.durable.activities.retry_policies import (
    _POLICIES,
    RetryPolicy,
    policy_for,
)
from codegenie.types.identifiers import ActivityName


def test_resolve_plugin_policy_exists_with_30s_timeout():
    """AC-3 — explicit timeout assertion catches a 5-vs-50 typo on the value.
    The reason it matters: a wrong timeout silently inflates Temporal worker
    occupancy under load; G6 throughput regresses; the bench catches it
    weeks later. Land the assertion at the source."""
    policy = policy_for(ActivityName("resolve_plugin"))
    assert policy.start_to_close_timeout == timedelta(seconds=30)
    assert policy.maximum_attempts == 3
```

Why it fails: `codegenie.durable.activities.retry_policies` doesn't exist yet — `ImportError`.

### Green — minimal pass

- Create the module; ship `RetryPolicy` model and the nine `_POLICIES` rows per AC-3.
- `policy_for` is a one-line lookup.

### Required follow-on tests (one per AC; named identity per test)

```python
def test_policy_for_unknown_raises_typed_keyerror():
    """AC-5 — KeyError.args[0] is the typed ActivityName, not a stringified
    message. Downstream code must be able to introspect the failure key."""
    name = ActivityName("never-registered")
    with pytest.raises(KeyError) as exc_info:
        policy_for(name)
    assert exc_info.value.args[0] == name


def test_run_vuln_subgraph_carries_tier_descent_non_retryable():
    """AC-4 — Phase-4 tier-descent triggers must NOT retry; they signal a
    descent decision the workflow body owns. Without this, a missed-recipe
    branch would loop until max_attempts before descending — that's the exact
    G3 failure mode this policy table prevents (arch C1 line 463)."""
    policy = policy_for(ActivityName("run_vuln_subgraph"))
    assert "RecipeMissedError" in policy.non_retryable_error_types
    assert "RagMissedError" in policy.non_retryable_error_types


def test_policies_table_has_exactly_the_nine_named_activities():
    """AC-2 — exact-set equality. Catches both an extra row added by mistake
    AND a missing row that would silently fall back to a Temporal default."""
    expected = {
        ActivityName(n) for n in {
            "resolve_plugin", "build_bundle", "route",
            "run_vuln_subgraph", "sandbox_build_and_test", "github_open_pr",
            "emit_event", "write_blob_ref", "resolve_blob_ref",
        }
    }
    assert set(_POLICIES.keys()) == expected


def test_policies_table_is_immutable_at_runtime():
    """AC-8 — MappingProxyType raises TypeError on mutation; without this,
    a contributor could mutate _POLICIES at import time of some other module
    and the workflow body would silently start using the changed policy."""
    with pytest.raises(TypeError):
        _POLICIES[ActivityName("resolve_plugin")] = None  # type: ignore[index]


def test_every_policy_name_eventually_registers(activity_registry):
    """AC-6 — registry-completeness. Today the activities are not yet shipped,
    so unshipped names live in _EXPECTED_BUT_UNSHIPPED. When S4-02..S4-05 ship,
    this set drains to empty; the day it hits empty AND policy names == registry
    names is the day _EXPECTED_BUT_UNSHIPPED gets deleted."""
    from codegenie.durable.activities import _ACTIVITIES
    from codegenie.durable.activities.retry_policies import _EXPECTED_BUT_UNSHIPPED
    for name in _POLICIES.keys():
        assert name in _ACTIVITIES or name in _EXPECTED_BUT_UNSHIPPED, (
            f"policy declared for {name!r} but neither registered nor "
            f"in _EXPECTED_BUT_UNSHIPPED — delete the row or register"
        )


def test_heartbeat_timeout_only_on_long_activities():
    """AC-3 — heartbeat_timeout is None for short activities (catches a
    contributor adding a 30 s heartbeat to a 5 s emit_event by accident)."""
    assert policy_for(ActivityName("emit_event")).heartbeat_timeout is None
    assert policy_for(ActivityName("resolve_plugin")).heartbeat_timeout is None
    assert policy_for(ActivityName("run_vuln_subgraph")).heartbeat_timeout == timedelta(seconds=30)
    assert policy_for(ActivityName("sandbox_build_and_test")).heartbeat_timeout == timedelta(seconds=30)
```

### Refactor

- Module docstring names the per-activity envelopes citation (`phase-arch-design.md §C2`); names this file as **the single retry-posture review surface**.
- The `RetryPolicy` model docstring cites `temporalio.common.RetryPolicy` and notes the wire-shape adapter lives in S5-02 (workflow body) — keeps the policy module dependency-free of `temporalio`.
- The `_EXPECTED_BUT_UNSHIPPED` constant carries an inline comment naming the four trimming stories (S4-02, S4-03, S4-04, S4-05) and that AC-6 fails the day the set is empty AND the activities are all registered — the executor's signal to delete the constant.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/durable/activities/retry_policies.py` | `RetryPolicy` model, `_POLICIES` table, `policy_for`, `_EXPECTED_BUT_UNSHIPPED`. |
| `tests/unit/durable/__init__.py` | Namespace marker. |
| `tests/unit/durable/activities/__init__.py` | Namespace marker. |
| `tests/unit/durable/activities/test_retry_policies.py` | Red test + named follow-on tests per AC. |
| `tests/unit/durable/activities/conftest.py` | `activity_registry` fixture (mirror S1-04's `restore_activity_registry` if present). |

## Out of scope

- The `@activity.defn` decorations and the activity function bodies — S4-02..S4-05.
- The wire-shape adapter that converts `RetryPolicy` → `temporalio.common.RetryPolicy` — lives in `S5-02-vuln-remediation-workflow.md` (workflow body owns the dispatch call site).
- Per-task-queue routing — the task-queue *name* an activity runs on is not a policy concern; it lives in S6-01's worker bootstrap.
- The G3 no-retry-loop fence — S8-05 owns the fence; this story ships the alternative pattern that fence's existence presupposes.
- Continue-as-new behaviour for `run_vuln_subgraph` exceeding 20 min — open-question #1, deferred to Phase 10.

## Notes for the implementer

### §1 — `_POLICIES` is the canonical review surface

Phase 9's G3 narrative says "retries are framework-level, never application." That sentence is enforceable ONLY if there's ONE place to review retry posture changes — `_POLICIES`. The fence in S8-05 forbids retry loops in workflow code; this module is what makes "no retry loops" survivable. Treat any future PR that adds an inline `RetryPolicy(...)` literal at a `workflow.execute_activity` call site as a P0 regression: it bypasses the catalog and silently re-creates the "every contributor invents their own retry posture" anti-pattern.

### §2 — Don't add a default

`policy_for(name)` raises `KeyError` on miss; no fallback. A silent default of "3 attempts, 30 s timeout" sounds defensive but is the exact failure mode this table prevents — a workflow registers a new activity name, forgets to land its policy row, and silently inherits a wrong-for-its-shape policy. Loud is better.

### §3 — `MappingProxyType` over `dict`

Per ADR-0010's discipline that "configuration is data, not code." A bare `dict[ActivityName, RetryPolicy]` is mutable at runtime; a contributor could do `_POLICIES[name].maximum_attempts = 99` from a test fixture (or worse, from a production import-time side effect). `MappingProxyType` makes mutation a runtime `TypeError`. Pydantic `frozen=True` on `RetryPolicy` itself blocks `_POLICIES[name].maximum_attempts = 99` — together they form the "config is read-only after import" contract.

### §4 — `_EXPECTED_BUT_UNSHIPPED` is a forward-reference, not a permanent escape hatch

This story is the *first* to populate the policy table; S4-02..S4-05 register the activities. The set starts as `frozenset({all nine names})` and shrinks to `frozenset()` as each activity story lands. The day it hits empty AND AC-6's test passes without the OR-branch is the day the constant gets deleted (the executor for the last shipping activity story removes it). Leaving a permanent `_EXPECTED_BUT_UNSHIPPED` constant in place after all activities ship would re-create exactly the silent-drift failure mode this story exists to prevent.

### §5 — Re-asserted under future phases

Phase 10 may add `vuln-remediation-python-pip` activities; Phase 11 may add `discovery_*` activities. Each new activity = one row in `_POLICIES` + one bump to `_EXPECTED_BUT_UNSHIPPED` if the activity ships in a separate commit from the policy row. The same "single review surface" discipline must apply.
