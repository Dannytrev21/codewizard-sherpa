# Story S2-06 — Cost-tag env shim + Phase 5 ADR-0010 `bench_invocation` amendment

**Step:** Step 2 — Build harness internals: loader, cache, audit chain extension, canary + cost-tag shims
**Status:** Ready (HARDENED 2026-05-26)
**Effort:** S
**Depends on:** S1-02 *(in-phase)*; **Phase 5 S7-03 (`CostEmitter` + `SandboxCostEntry`)** must be **GREEN** before the cross-phase amendment in §Files-to-touch row 2–3 can land — the shim itself (`src/codegenie/eval/cost_tag.py`) can ship independently and the Phase 5 amendment trails as a follow-up PR if S7-03 has not yet shipped at execution time.
**ADRs honored:** ADR-0007 (bench-invocation tagging on `SandboxCostEntry`), Phase 5 ADR-0010 amendment (additive `bench_invocation: bool` field)

## Validation notes (2026-05-26 — HARDENED)

Validator changes (full report: [`_validation/S2-06-cost-tag-shim.md`](_validation/S2-06-cost-tag-shim.md)):

1. **Concurrency contract surfaced.** `phase-arch-design.md` line 826
   has the runner calling `tag_invocation(...) → await SUT.ainvoke(case)`
   inside an `asyncio.Semaphore(N=4)` fan-out. The env var is
   process-global; concurrent entry races. The shim does **not** add a
   lock (Rule 2 — only one caller today). Instead: the docstring and
   AC-12 now declare the non-concurrent contract; S3-02 (the runner)
   owns serialization. ADR-0007 §Tradeoffs row 3's "deterministic
   teardown" claim is true only under that contract.
2. **Phase 5 sequencing gate** — `src/codegenie/sandbox/cost.py` does
   not yet exist (Phase 5 S7-03 is HARDENED, not GREEN). The shim
   ships standalone; the cross-phase amendment trails behind S7-03.
3. **Pure-impure split** — `_build_tag(...) -> str` extracted as a
   pure helper (functional core / imperative shell). Testable
   without env-var monkey-patching.
4. **Env-var name promoted to `Final[str]` export.** Phase 5's
   `CostEmitter` imports `BENCH_INVOCATION_ENV_VAR` from
   `codegenie.eval.cost_tag` rather than duplicating the literal.
5. **TDD plan strengthened** — added nested-call test, metamorphic
   determinism pair, Hypothesis property, concurrent-entry contract
   assertion, parametrized prior-value (including empty-string),
   pure-helper direct-import test. Removed exact-string couplings in
   favor of rebuilding via the pure helper.
6. **Deferred extracts noted** — scoped-env-var primitive (rule-of-
   three; only one consumer today), `BenchInvocationTag` newtype,
   and the phase-wide `TaskClassName` / `CaseId` newtype
   consolidation (S1-03 precedent).

## Context

Phase 5 ships `SandboxCostEntry` (one ledger row per `GateRunner` attempt at `.codegenie/cost/sandbox.jsonl`) consumed by Phase 13's ROI dashboard (production ADR-0024). Every nightly bench run invokes the SUT, which invokes Phase 5's sandbox, which writes a `SandboxCostEntry` — indistinguishable from a real production PR-work entry. Without a marker, Phase 13's denominator (`$ spent / $ delivered`) silently inflates. ADR-0007 fixes this with two additive changes: (1) Phase 5's `CostEmitter` reads `CODEGENIE_BENCH_INVOCATION_TAG`; when set, `SandboxCostEntry.workflow_id` becomes the tag and `bench_invocation=True`. (2) `SandboxCostEntry` gains `bench_invocation: bool = False` (additive; default preserves Phase 5's `extra="forbid"` discipline). `src/codegenie/eval/cost_tag.py` exposes the `tag_invocation(...)` context manager that sets/clears the env var around each SUT call. The Phase 5 ADR-0010 amendment lands in the same PR train as this story.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — src/codegenie/eval/cost_tag.py` — public-interface signature, env-var contract, "graceful degradation" if Phase 5's field hasn't landed
  - `../phase-arch-design.md §Edge cases #15` — cross-phase invariant: Phase 13's consumer filters `WHERE bench_invocation IS NOT TRUE`
  - `../phase-arch-design.md §Testing strategy — Adversarial tests` — `test_cost_ledger_pollution.py`
- **Phase ADRs:**
  - `../ADRs/0007-bench-invocation-tagging-on-sandbox-cost-entry.md` — full rationale; env-var name; the four-options rejection trail; reversibility = Medium
- **Production ADRs:**
  - `../../../production/adrs/0024-cost-observability-end-to-end.md` — the downstream consumer that needs the filter
- **Source design:**
  - `../final-design.md §Bench-run cost-ledger tagging` — original synthesis
- **Existing code:**
  - `src/codegenie/sandbox/cost.py` (Phase 5) — `CostEmitter`; `SandboxCostEntry` definition with `extra="forbid"`, `frozen=True`
  - Phase 5 ADR-0010 — `SandboxCostEntry` schema; the file gets an additive amendment

## Goal

`codegenie.eval.cost_tag.tag_invocation(task_class, case_id, run_started_iso)` is a context manager that sets `CODEGENIE_BENCH_INVOCATION_TAG=f"bench:{run_started_iso}:{task_class}:{case_id}"` on entry and clears it on exit; Phase 5's `CostEmitter` reads the env var to mark `SandboxCostEntry.bench_invocation=True` and route `workflow_id` to the tag.

## Acceptance criteria

- [ ] **AC-1:** `tag_invocation(task_class: str, case_id: str, run_started_iso: str) -> ContextManager[None]` is importable from `codegenie.eval.cost_tag`.
- [ ] **AC-2 (tag construction via pure helper):** A module-private `_build_tag(task_class: str, case_id: str, run_started_iso: str) -> str` is also defined in `codegenie.eval.cost_tag`, returns exactly `f"bench:{run_started_iso}:{task_class}:{case_id}"`, has **no I/O** (no env access, no logging, no clock), and is directly unit-testable without `monkeypatch.setenv`. `tag_invocation` calls `_build_tag` to compute the value it writes. (Functional core / imperative shell — F-DP-1.)
- [ ] **AC-3 (env-var name as exported `Final[str]`):** The constant is declared at module scope as `BENCH_INVOCATION_ENV_VAR: Final[str] = "CODEGENIE_BENCH_INVOCATION_TAG"` and is publicly importable. Phase 5's `CostEmitter` (`src/codegenie/sandbox/cost.py`) imports this name rather than duplicating the string literal. (Capability constant / single-source-of-truth — F-DP-2.)
- [ ] **AC-4 (enter sets):** Entering the `with` block sets `os.environ[BENCH_INVOCATION_ENV_VAR]` to exactly `_build_tag(task_class, case_id, run_started_iso)` (assert equality against the helper, not a hand-typed literal).
- [ ] **AC-5 (normal exit clears):** On normal exit, if no prior value existed, `BENCH_INVOCATION_ENV_VAR not in os.environ`.
- [ ] **AC-6 (exception exit clears):** Raising **any** exception inside the `with` block still clears (or restores) the env var; the exception propagates unchanged.
- [ ] **AC-7 (save-restore prior — all three priors):** If `BENCH_INVOCATION_ENV_VAR` was set before the `with` block, exit restores it to **exactly** the prior bytes. This must hold for prior values `""` (empty string, set but blank), `"prior-value"` (arbitrary string), and `"bench:older"` (a previous bench tag — operator running nested experiments). Distinct from the "unset" case where the env var is `os.environ.pop`-ed.
- [ ] **AC-8 (nested `tag_invocation` calls):** Two `tag_invocation(...)` calls deliberately stacked **in the same task** must each restore the *immediately-enclosing* tag on exit (LIFO save/restore). Concretely: with `tag_invocation("a", "1", "iso1")` outer and `tag_invocation("b", "2", "iso2")` inner, the inner exit restores the outer tag (not the pre-outer value or `None`); the outer exit restores the pre-outer value.
- [ ] **AC-9 (metamorphic determinism):** For any fixed `(task_class, case_id, run_started_iso)`, two successive calls to `_build_tag` return byte-identical strings. For any pair of inputs that differ in at least one component, the resulting tags differ. (Defeats the constant-impl trivially-passes failure mode.)
- [ ] **AC-10 (tag-shape contract):** The tag begins literally with `bench:` (Phase 13's reader may filter on either `bench_invocation==True` OR `workflow_id.startswith("bench:")` — ADR-0007 §Tradeoffs row 4). The tag *also* contains each of `task_class`, `case_id`, and `run_started_iso` as a substring such that recomputing `_build_tag(...)` over the same inputs yields the same value.
- [ ] **AC-11 (Phase 5 cross-phase amendment — gated on S7-03 GREEN):** When Phase 5 S7-03 is GREEN: `SandboxCostEntry` (Phase 5) gains `bench_invocation: bool = False` (additive field). `CostEmitter` (Phase 5) reads `os.environ.get(BENCH_INVOCATION_ENV_VAR)` via the imported constant; when present, sets `workflow_id` to the tag and `bench_invocation=True`. ADR-0010's §Consequences is updated to enumerate the new field. **The shim in §Files-to-touch row 1 can ship in a PR ahead of S7-03 going GREEN; the amendment rows 2–3 land only when the file they edit exists.**
- [ ] **AC-12 (non-concurrent contract — load-bearing):** The module docstring of `cost_tag.py` declares: "MUST NOT be entered concurrently from the same Python process. The env var is process-global; concurrent entry from two `asyncio.Task`s or threads will race and corrupt each other's tags. Callers are responsible for serializing entry — see S3-02 (runner) for the in-phase example." A unit test asserts the docstring contains the literal string `"MUST NOT be entered concurrently"` and references `S3-02`. This is a *documented contract*, not a runtime check (Rule 2 — only one caller today).
- [ ] **AC-13 (cross-phase contract test — concrete fixture):** `tests/unit/test_cost_ledger_tagging.py` defines a concrete `stub_cost_emitter` fixture matching Phase 5's `CostEmitter.emit(...)` signature once S7-03 is GREEN (until then, the test is `pytest.skip("phase 5 S7-03 not yet GREEN")` with the skip-reason gated on `importlib.util.find_spec("codegenie.sandbox.cost")`). Once unskipped, wraps a `CostEmitter.emit(...)` call in `tag_invocation(...)` and asserts the emitted `SandboxCostEntry` carries `bench_invocation=True` and `workflow_id == _build_tag(...)`; without the wrapper, both revert to defaults.
- [ ] **AC-14 (adversarial filter-discipline test):** `tests/adv/test_cost_ledger_pollution.py` — names the filter-discipline contract it tests (Phase 13's `WHERE bench_invocation IS NOT TRUE`), constructs both a bench-tagged and an untagged entry, asserts the filter cleanly separates them. (Same skip-discipline as AC-13 until S7-03 GREEN.)
- [ ] **AC-15 (graceful degradation):** If Phase 5 hasn't landed `bench_invocation` yet (in-flight amendment), the env var is silently ignored at the Phase 5 reader — the contract test in AC-13 fails loudly (or skips per the gate), but a runner integration test does not crash. (Documented; not enforced in code.)
- [ ] **AC-16 (toolchain clean):** TDD red test exists, committed, green. `ruff format`, `ruff check`, `mypy --strict` clean.

## Implementation outline

1. **Create `src/codegenie/eval/cost_tag.py`.** Module docstring quotes ADR-0007 §Decision, the Phase 5 amendment dependency, AND the load-bearing non-concurrent contract (AC-12) verbatim. The first sentence is the concurrency warning.
2. **Export the env-var name as a `Final[str]` constant** (AC-3):
   ```python
   from typing import Final
   BENCH_INVOCATION_ENV_VAR: Final[str] = "CODEGENIE_BENCH_INVOCATION_TAG"
   ```
   Phase 5 imports this name; no string-literal duplication.
3. **Define the pure tag builder** (AC-2 — functional core):
   ```python
   def _build_tag(task_class: str, case_id: str, run_started_iso: str) -> str:
       return f"bench:{run_started_iso}:{task_class}:{case_id}"
   ```
   No env access, no logging, no clock. Directly unit-testable.
4. **Define the impure context manager** (the imperative shell):
   ```python
   @contextlib.contextmanager
   def tag_invocation(task_class: str, case_id: str, run_started_iso: str) -> Iterator[None]:
       tag = _build_tag(task_class, case_id, run_started_iso)
       sentinel = object()
       prior: str | object = os.environ.get(BENCH_INVOCATION_ENV_VAR, sentinel)
       os.environ[BENCH_INVOCATION_ENV_VAR] = tag
       try:
           yield
       finally:
           if prior is sentinel:
               os.environ.pop(BENCH_INVOCATION_ENV_VAR, None)
           else:
               os.environ[BENCH_INVOCATION_ENV_VAR] = prior  # restores "", "prior-value", "bench:older" equally
   ```
   The sentinel pattern correctly distinguishes `prior is None / ""` (env var was set to blank) from "env var unset" — `os.environ.get(...)` returns `None` only when unset, but using a sentinel is unambiguous and self-documenting.
5. **Amend `src/codegenie/sandbox/cost.py`** (Phase 5 — gated on S7-03 GREEN; AC-11):
   - Add `bench_invocation: bool = False` to `SandboxCostEntry` (Pydantic `extra="forbid", frozen=True` discipline — this is **additive**, fine).
   - In `CostEmitter.emit(...)` (or whatever the construction site is), `from codegenie.eval.cost_tag import BENCH_INVOCATION_ENV_VAR` and read `os.environ.get(BENCH_INVOCATION_ENV_VAR)`; when truthy, set `workflow_id=tag` and `bench_invocation=True` on the constructed entry. **One-way import:** `codegenie.sandbox` may import from `codegenie.eval`; the reverse is forbidden by import-linter (eval is application-side; sandbox is infrastructure).
6. **Amend Phase 5 ADR-0010** markdown to document the new field in §Consequences (gated on S7-03 GREEN; the amendment commit cites this story by ID).

## TDD plan — red / green / refactor

### Red

Test file: `tests/unit/eval/test_cost_tag.py`

```python
import os
import pytest
from typing import Final
from hypothesis import given, strategies as st

from codegenie.eval.cost_tag import (
    BENCH_INVOCATION_ENV_VAR,
    _build_tag,
    tag_invocation,
)

_TC: Final = "vuln-remediation"
_CASE: Final = "001-x"
_ISO: Final = "2026-05-12T00:00:00+00:00"


# AC-2 — pure helper directly importable and pure
def test_build_tag_is_pure_and_round_trips():
    """Pure helper has no I/O; same inputs → same output; round-trip via env-var sees the same value."""
    expected = f"bench:{_ISO}:{_TC}:{_CASE}"
    assert _build_tag(_TC, _CASE, _ISO) == expected
    # Same inputs, byte-identical (AC-9 first half)
    assert _build_tag(_TC, _CASE, _ISO) == _build_tag(_TC, _CASE, _ISO)


# AC-3 — env-var name is a Final[str] export
def test_env_var_name_is_exported_final_constant():
    assert BENCH_INVOCATION_ENV_VAR == "CODEGENIE_BENCH_INVOCATION_TAG"
    # `Final` is structural; the import succeeding from the public name is the contract


# AC-4 + AC-10 — strengthened tag-shape: equals helper output AND varies with inputs
def test_tag_invocation_sets_env_var_to_build_tag_output():
    with tag_invocation(_TC, _CASE, _ISO):
        assert os.environ[BENCH_INVOCATION_ENV_VAR] == _build_tag(_TC, _CASE, _ISO)
        assert os.environ[BENCH_INVOCATION_ENV_VAR].startswith("bench:")


# AC-9 second half — metamorphic: different inputs → different tags (defeats constant-impl)
@pytest.mark.parametrize(
    "a,b",
    [
        ((_TC, _CASE, _ISO), ("other-tc", _CASE, _ISO)),
        ((_TC, _CASE, _ISO), (_TC, "002-y", _ISO)),
        ((_TC, _CASE, _ISO), (_TC, _CASE, "2026-05-13T00:00:00+00:00")),
    ],
)
def test_build_tag_metamorphic_differs_on_any_axis(a, b):
    assert _build_tag(*a) != _build_tag(*b)


# AC-5 — normal exit clears when no prior
def test_tag_invocation_clears_on_normal_exit(monkeypatch):
    monkeypatch.delenv(BENCH_INVOCATION_ENV_VAR, raising=False)
    with tag_invocation(_TC, _CASE, _ISO):
        assert BENCH_INVOCATION_ENV_VAR in os.environ
    assert BENCH_INVOCATION_ENV_VAR not in os.environ


# AC-6 — exception cleanup
def test_tag_invocation_clears_on_exception(monkeypatch):
    monkeypatch.delenv(BENCH_INVOCATION_ENV_VAR, raising=False)
    with pytest.raises(RuntimeError):
        with tag_invocation(_TC, _CASE, _ISO):
            raise RuntimeError("boom")
    assert BENCH_INVOCATION_ENV_VAR not in os.environ


# AC-7 — save-restore prior over three prior shapes (empty string is load-bearing)
@pytest.mark.parametrize("prior", ["", "prior-value", "bench:older"])
def test_tag_invocation_save_restores_prior_value(monkeypatch, prior):
    monkeypatch.setenv(BENCH_INVOCATION_ENV_VAR, prior)
    with tag_invocation(_TC, _CASE, _ISO):
        # Inside the with, the new tag wins
        assert os.environ[BENCH_INVOCATION_ENV_VAR] == _build_tag(_TC, _CASE, _ISO)
    # After exit, exact prior bytes restored — including the empty-string case
    assert os.environ[BENCH_INVOCATION_ENV_VAR] == prior


# AC-8 — nested tag_invocation in same task: LIFO save/restore
def test_tag_invocation_nested_calls_lifo_restore(monkeypatch):
    monkeypatch.delenv(BENCH_INVOCATION_ENV_VAR, raising=False)
    outer_tag = _build_tag("a", "1", "iso1")
    inner_tag = _build_tag("b", "2", "iso2")
    with tag_invocation("a", "1", "iso1"):
        assert os.environ[BENCH_INVOCATION_ENV_VAR] == outer_tag
        with tag_invocation("b", "2", "iso2"):
            assert os.environ[BENCH_INVOCATION_ENV_VAR] == inner_tag
        # Inner exit restores outer (NOT the pre-outer value)
        assert os.environ[BENCH_INVOCATION_ENV_VAR] == outer_tag
    # Outer exit restores pre-outer (unset)
    assert BENCH_INVOCATION_ENV_VAR not in os.environ


# AC-9 — Hypothesis property: round-trip determinism over arbitrary slug-shaped inputs
@given(
    task_class=st.from_regex(r"^[a-z][a-z0-9-]{1,30}[a-z0-9]$", fullmatch=True),
    case_id=st.from_regex(r"^[a-z0-9-]{1,30}$", fullmatch=True),
    run_started_iso=st.from_regex(r"^20\d{2}-[01]\d-[0-3]\dT[0-2]\d:[0-5]\d:[0-5]\d\+00:00$", fullmatch=True),
)
def test_build_tag_property_deterministic_round_trip(task_class, case_id, run_started_iso):
    once = _build_tag(task_class, case_id, run_started_iso)
    twice = _build_tag(task_class, case_id, run_started_iso)
    assert once == twice
    # The three inputs are recoverable as substrings (the prefix isolates them)
    assert once.startswith("bench:")
    assert run_started_iso in once
    assert task_class in once
    assert case_id in once


# AC-12 — non-concurrent contract is documented in the module docstring
def test_docstring_declares_non_concurrent_contract():
    import codegenie.eval.cost_tag as mod

    assert mod.__doc__ is not None
    assert "MUST NOT be entered concurrently" in mod.__doc__
    assert "S3-02" in mod.__doc__
```

Cross-phase contract test: `tests/unit/test_cost_ledger_tagging.py`

```python
import importlib.util
import os

import pytest

from codegenie.eval.cost_tag import BENCH_INVOCATION_ENV_VAR, _build_tag, tag_invocation

# Skip until Phase 5 S7-03 is GREEN (the file exists)
_PHASE5_READY = importlib.util.find_spec("codegenie.sandbox.cost") is not None
pytestmark = pytest.mark.skipif(not _PHASE5_READY, reason="Phase 5 S7-03 (cost.py) not yet GREEN")


@pytest.fixture
def stub_cost_emitter():
    """Minimal `CostEmitter` shape — matches Phase 5 S7-03's signature once GREEN.

    The stub constructs a `SandboxCostEntry` from the env-var read; production
    `CostEmitter` does the same but with a real ledger append. Once Phase 5 is
    GREEN, replace the stub body with `from codegenie.sandbox.cost import CostEmitter`
    and call the real emitter.
    """
    from codegenie.sandbox.cost import SandboxCostEntry  # type: ignore[import-not-found]

    class _StubEmitter:
        def emit(self, *, workflow_id: str = "prod-workflow", **fields: object) -> SandboxCostEntry:
            tag = os.environ.get(BENCH_INVOCATION_ENV_VAR)
            return SandboxCostEntry(
                entry_type="cost.sandbox.run",
                workflow_id=tag if tag else workflow_id,
                bench_invocation=bool(tag),
                **fields,  # type: ignore[arg-type]
            )

    return _StubEmitter()


def test_emitter_marks_bench_invocation_under_tag(stub_cost_emitter):
    with tag_invocation("vuln-remediation", "001-x", "2026-05-12T00:00:00+00:00"):
        entry = stub_cost_emitter.emit()
    assert entry.bench_invocation is True
    assert entry.workflow_id == _build_tag("vuln-remediation", "001-x", "2026-05-12T00:00:00+00:00")


def test_emitter_defaults_outside_tag(stub_cost_emitter, monkeypatch):
    monkeypatch.delenv(BENCH_INVOCATION_ENV_VAR, raising=False)
    entry = stub_cost_emitter.emit()
    assert entry.bench_invocation is False
    assert entry.workflow_id == "prod-workflow"
```

Adversarial: `tests/adv/test_cost_ledger_pollution.py`

```python
# Same Phase 5 skip-discipline as the contract test.
def test_bench_entries_filterable_from_production_entries(stub_cost_emitter, monkeypatch):
    """Asserts the Phase 13 filter discipline `WHERE bench_invocation IS NOT TRUE`
    cleanly separates bench-tagged from production entries. (Phase 13's reader
    composes this filter; this test asserts the *producer-side* contract is
    sufficient to support it.)"""
    monkeypatch.delenv(BENCH_INVOCATION_ENV_VAR, raising=False)
    with tag_invocation("a", "b", "2026-05-12T00:00:00+00:00"):
        bench_entry = stub_cost_emitter.emit()
    prod_entry = stub_cost_emitter.emit()
    production_only = [e for e in [bench_entry, prod_entry] if not e.bench_invocation]
    assert production_only == [prod_entry]
```

### Green

Smallest impl: §Implementation outline; ~25 lines for the eval shim (sentinel-based save/restore + pure helper + `Final` constant + load-bearing docstring). Phase 5 amendment is ~6 lines (1 field, 4 lines in `CostEmitter.emit`, 1 import). ADR-0010 markdown edit is the §Consequences bullet.

### Refactor

- Add structlog `debug cost_tag.env_set` and `cost_tag.env_cleared` events with `tag` attribute — observable during S5-05 integration runs.
- Add an import-linter contract enforcing the one-way `codegenie.sandbox → codegenie.eval` direction. (May already be covered by the existing phase-5 fence; verify and extend if not.)

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/cost_tag.py` | New module — `tag_invocation` context manager + env-var name constant |
| `src/codegenie/sandbox/cost.py` | Phase 5 amendment — additive `bench_invocation` field + env-var read in `CostEmitter` |
| `docs/phases/05-sandbox-trust-gates/ADRs/0010-cost-sandbox-run-ledger-schema.md` | Phase 5 ADR amendment — §Consequences updated with new field |
| `tests/unit/eval/test_cost_tag.py` | Red tests for the shim |
| `tests/unit/test_cost_ledger_tagging.py` | Cross-phase contract test |
| `tests/adv/test_cost_ledger_pollution.py` | Adversarial filter test |

## Out of scope

- **Phase 13's reader** — out of scope; `WHERE bench_invocation IS NOT TRUE` is documented but Phase 13 implementation is future work.
- **The eventual S7-03 re-confirmation pass** — the Phase 5 amendment is **landed** here; S7-03 only re-checks that the amendment is merged before the phase merge train.
- **The runner's invocation of `tag_invocation` around each `SUT(case)` call** — handled by S3-02; this story only ships the context manager.
- **Runner-side serialization of concurrent `tag_invocation` entries** — S3-02 owns it (AC-12 only commits to documenting the non-concurrent contract; the implementation of `asyncio.Lock` or concurrency=1 is the runner's design choice).
- **Multiple tag flavors** (dev, regression, etc.) — ADR-0007 §Reversibility documents this as future additive ADR work.
- **Generic `scoped_env_var(name, value)` primitive** — the rule-of-three trigger is the second new tag flavor; today there is one consumer. Deferred.
- **`BenchInvocationTag` newtype / `TaskClassName` / `CaseId` newtypes** — phase-wide deferred (S1-03 / S2-01 / S2-02 precedent).

## Notes for the implementer

- **Env-var save/restore semantics:** the load-bearing case is the operator who manually sets `CODEGENIE_BENCH_INVOCATION_TAG` for an ad-hoc experiment, then runs `codegenie eval run`. The shim must restore their value on exit, not erase it. Use a sentinel-vs-`None` discriminator (see Implementation outline step 4) so empty-string prior values restore correctly — `os.environ.get(..., sentinel)` is the clean idiom.
- **Non-concurrent contract is the load-bearing constraint (AC-12).** The env var is process-global. `phase-arch-design.md` line 826 has the runner calling `tag_invocation(...) → await SUT.ainvoke(case)` inside an `asyncio.Semaphore(N=min(os.cpu_count(), 4))` fan-out. Two concurrent tasks would race. **The shim does NOT add an `asyncio.Lock`** (Rule 2 — only one caller today; a lock here imposes cost on every future caller and obscures the real architectural decision). Serialization is **S3-02's purview**: the runner must either (a) hold an `asyncio.Lock` around the entire `tag_invocation(...) → await SUT.ainvoke(case)` block, OR (b) lower runner concurrency to 1 for cost-tagged runs, OR (c) pass the tag through a non-env-var mechanism. S3-02 owns that decision; this story owns the documented contract. Cross-reference: ADR-0007 §Tradeoffs row 3 ("deterministic teardown" — true only under non-concurrent entry).
- **Cross-phase amendment train (gated):** Per `phase-arch-design.md §Risks #4` and ADR-0007 §Consequences, the Phase 5 ADR-0010 amendment PR opens *with* this story **only when Phase 5 S7-03 is GREEN**. As of 2026-05-26 S7-03 is HARDENED, not GREEN — the file `src/codegenie/sandbox/cost.py` does not exist. The shim ships first (rows 1, 4, 5, 6 in §Files-to-touch); the amendment (rows 2–3) trails until S7-03 lands. The pattern is the opposite of S2-05's failed Phase 4 amendment: there, Phase 4 had *already shipped* a different surface than the ADR assumed; here, Phase 5's surface is well-specified and the order-of-operations is the only constraint.
- **Phase 5's `extra="forbid"` discipline (Phase 5 ADR-0014):** adding `bench_invocation: bool = False` to `SandboxCostEntry` is a Pydantic-frozen-model extension. Every downstream consumer in Phase 5's tests must be re-run; the default value preserves the existing on-disk shape (False is unambiguous; readers that don't read the field aren't affected). This is the explicit "additive only" discipline ADR-0007 enumerates in §Tradeoffs row 2.
- **`workflow_id` collision risk:** the tag value uses colons (`bench:<iso>:<tc>:<case>`); the ISO timestamp also contains colons (`2026-05-12T00:00:00+00:00`). The result has many colons but is unambiguous because the `bench:` prefix is fixed and the remainder is parsed end-to-start when needed. Document the format and do NOT change it without a follow-up ADR (Phase 13 will key on the prefix). If `task_class` or `case_id` were ever to contain `:`, parsing breaks — S2-01's name regex (`^[a-z][a-z0-9-]*[a-z0-9]$`) excludes colons by construction; case-id validation lives in S2-02's `BenchCase` model.
- **Residual `os._exit` / `SIGKILL` leak (ADR-0007 §Tradeoffs row 3):** if the Python interpreter dies inside the `with` block (`os._exit(0)`, `SIGKILL`, OOM-killer), the env var leaks to the parent shell. This is **not** a unit-test concern — the `try/finally` discipline handles every exception type a Python process can observe. Documented as residual risk; the next `codegenie eval run` sets the env var afresh, masking the leak.
- **Reversibility (from ADR-0007):** Medium. Once Phase 13's ROI math depends on `bench_invocation` being present, removal breaks the dashboard. Treat as one-way additive.
- **Deferred extracts (rule of three not yet hit):**
  - *Scoped env-var primitive.* ADR-0007 §Consequences row 8 anticipates future tags (`CODEGENIE_DEV_INVOCATION_TAG`, regression-mode, etc.). Today there is one consumer (this shim). Per CLAUDE.md + Rule 2, do NOT extract a `scoped_env_var(name, value)` helper now. The **trigger** is the third concrete consumer (the second new tag flavor) — at that point a `codegenie.eval._scoped_env.py` primitive becomes leverage-positive.
  - *`BenchInvocationTag` newtype.* Wrapping the tag string in a smart constructor that enforces the `bench:` prefix at construction would close primitive-obsession. Surface area is one variable; payoff is low. Deferred — same trigger condition as above.
  - *`TaskClassName` / `CaseId` newtypes.* Phase-wide deferred per S1-03 / S2-01 / S2-02 precedent. Identifier-consolidation is its own future story.
- The graceful-degradation case (Phase 5 hasn't landed the field yet) is **not** an integration test in CI — it's a manual reminder. The `tests/unit/test_cost_ledger_tagging.py` skips on `importlib.util.find_spec("codegenie.sandbox.cost") is None` until S7-03 GREEN; once unskipped, it fails loud if the env-var read is missing or the field is mis-typed.
