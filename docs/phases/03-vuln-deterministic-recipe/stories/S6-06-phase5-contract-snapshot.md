# Story S6-06 — Phase 5 contract snapshot test (failure means Phase 5 cannot ship)

**Step:** Step 6 — RemediationOrchestrator, TrustScorer, two-stream EventLog, SubgraphNode Protocol, end-to-end happy path
**Status:** Ready
**Effort:** M
**Depends on:** S6-04
**ADRs honored:** ADR-0001 (ship the Phase-5 contract surface; the snapshot test is the CI-gating handshake), ADR-0007 (Phase 3 runs `_validate_stage6` inside `SubprocessJail`; Phase 5 wraps the retry envelope), ADR-0010 (every contract symbol is a typed Pydantic / dataclass / Protocol with `extra="forbid"`)

## Context

ADR-0001 commits Phase 3 to shipping six named contract symbols (`RemediationOrchestrator`, `TrustScorer`, `Transform` ABC, `ApplyContext`, `RecipeEngine`, `remediation-report.yaml`) that Phase 5 wraps additively. The ADR's §Consequences row 2 names a **CI-gating contract snapshot test** as the mechanism that prevents drift: *"`tests/integration/test_phase5_contract_snapshot.py` is CI-required; failure blocks Phase 3 merges."*

This story lands that test. The test reads the public surfaces of the six symbols, canonicalizes their shape (Pydantic JSON schema for models, `inspect.signature` for methods, `inspect.getmembers` for classes), and compares to a golden file under `tests/golden/phase5-contract/`. Failure means **Phase 5 cannot ship** because Phase 5's `GateRunner.run(transition=stage6_validate, ctx=GateContext(...))` decorates symbols by name + signature; any drift means Phase 5's wrap doesn't compose.

**Critical distinction** (per `High-level-impl.md §Implementation-level risks #4`): the test allows **additive** deltas (a new optional field with `default_factory`, a new method on a class, a new variant on a discriminated union) but rejects **breaking** deltas (rename, remove, required-add, signature-change). Breaking deltas require an explicit **ADR amendment + golden refresh** in the same PR. Encoding this distinction in the test (not in reviewer judgment) is the explicit risk-mitigation strategy from High-level-impl.

The six symbols and what their snapshot captures:

| Symbol | Snapshot content |
|---|---|
| `RemediationOrchestrator` | `inspect.signature(__init__)`, `inspect.signature(run)`, `inspect.signature(_validate_stage6)`; class MRO |
| `TrustScorer` | `inspect.signature(__init__)`, `inspect.signature(score)`; `TrustSignal` + `TrustOutcome` JSON schemas |
| `Transform` (ABC) | abstract method names + signatures; concrete subclass list (sealed hierarchy snapshot) |
| `ApplyContext` | Pydantic JSON schema; `AttemptSummary` JSON schema; `prior_attempts` default-factory shape |
| `RecipeEngine` (Protocol) | Protocol method signatures; `@runtime_checkable` decorator presence |
| `remediation-report.yaml` schema | Pydantic JSON schema of `RemediationReport` (from S5-05) |

The architecture spec's §Testing strategy lists this test explicitly: *"`tests/integration/test_phase5_contract_snapshot.py` — the Phase-5 contract handshake; failure means Phase 5 cannot ship."*

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy — CI gates (required jobs)` — names this test as a CI-required job.
  - `../phase-arch-design.md §Component design C1–C5` — the public interfaces of the six symbols. The snapshot freezes these.
  - `../phase-arch-design.md §Path to production end state — Deferred ADRs this phase makes resolvable` — names P3-001 (Phase-5 contract surface) as the ADR this snapshot enforces.
- **Phase ADRs:**
  - `../ADRs/0001-ship-phase5-contract-surface-by-name.md` — full read. §Decision names the six symbols; §Consequences mandates this test; §Reversibility (Low) is the reason brittleness is acceptable.
  - `../ADRs/0007-run-npm-install-and-npm-test-in-phase3-jail.md` §Consequences — `_validate_stage6` signature is fixed by ADR-0001 contract snapshot.
- **Cross-phase contract:**
  - `../../05-sandbox-trust-gates/final-design.md §Component design — GateRunner` — the call site whose composition with `_validate_stage6` this snapshot protects.
  - `../../05-sandbox-trust-gates/ADRs/0001-two-chokepoint-sandbox-seam.md` — names `RemediationOrchestrator._validate_stage6` as the Stage-6 callsite swap point.
  - `../../05-sandbox-trust-gates/ADRs/0002-additive-prior-attempts-kwarg.md` — `ApplyContext.prior_attempts` is the additive amendment; the snapshot must permit it.
  - `../../05-sandbox-trust-gates/ADRs/0003-trustscorer-extension-via-signal-kind-registry.md` — `@register_signal_kind` is the additive extension; the snapshot must permit new kinds.
- **High-level-impl risk callout:**
  - `../High-level-impl.md §Implementation-level risks #4` — the explicit additive-vs-breaking distinction this test must encode.
- **Existing snapshot test precedent:**
  - `tests/unit/test_probe_contract.py` (Phase 0) — already snapshots the `Probe` ABC byte-for-byte against `docs/localv2.md §4`. Same pattern, different scope.
  - `tests/unit/probes/test_repo_context_envelope_extra.py` (Phase 1) — JSON-schema-based snapshot precedent.
- **This phase, parallel stories:**
  - S6-04 — the `RemediationOrchestrator` whose three signatures this test pins.
  - S6-02 — the `TrustScorer` whose constructor-injection shape this test pins.
  - S5-05 — the `RemediationReport` Pydantic model whose JSON schema is part of the snapshot.
  - S1-04 — the `Transform` ABC + `ApplyContext` Pydantic.
  - S5-01 — the `RecipeEngine` Protocol.

## Goal

Land `tests/integration/test_phase5_contract_snapshot.py` and a golden file under `tests/golden/phase5-contract/` that, together, freeze the public surface of the six ADR-0001 named symbols. The test allows **additive** deltas (optional fields with defaults, new discriminated-union variants, new methods on classes) and rejects **breaking** deltas (rename, remove, required-add, signature-change); failure is CI-gating; the failure message explicitly tells the reader to either revert the breaking change or land an ADR amendment + golden refresh in the same PR.

## Acceptance criteria

- [ ] `tests/integration/test_phase5_contract_snapshot.py` exists and is collected by `pytest tests/integration/`.
- [ ] The test produces a canonical snapshot of all six ADR-0001 symbols:
  - `RemediationOrchestrator.__init__`, `.run`, `._validate_stage6` signatures (via `inspect.signature`).
  - `TrustScorer.__init__`, `.score` signatures; `TrustSignal` JSON schema; `TrustOutcome` JSON schema.
  - `Transform` ABC abstract method names + signatures + the list of concrete subclasses currently in `src/codegenie/transforms/` and `plugins/*/recipes/`.
  - `ApplyContext` JSON schema + `AttemptSummary` JSON schema.
  - `RecipeEngine` Protocol method signatures + `@runtime_checkable` decorator presence.
  - `RemediationReport` JSON schema (from S5-05).
- [ ] The canonical snapshot is **deterministic**: same source → same bytes. Pydantic JSON schemas are dumped with `indent=2, sort_keys=True`. Method signatures are stringified via `str(inspect.signature(method))`. The MRO of each class is sorted by qualified name.
- [ ] The golden file `tests/golden/phase5-contract/snapshot.json` lives in the repo and is the source of truth. On first commit, it captures the green state of S6-01 through S6-05.
- [ ] **Additive deltas pass**: a new optional Pydantic field with `default_factory=list` does NOT break the test. The diff algorithm classifies each delta as:
  - **Additive (pass)**: new optional field with default, new method (not removing or modifying existing), new discriminated-union variant, new abstract subclass, new optional kwarg with default.
  - **Breaking (fail)**: rename, remove, signature change to an existing method, required-add (new field without default), `extra="forbid"`-violating field-type narrowing.
- [ ] **Breaking deltas fail with a directive message**: on mismatch, the test prints a multi-line message:
  ```
  PHASE 5 CONTRACT SNAPSHOT MISMATCH — BREAKING CHANGE DETECTED.

  Symbol: RemediationOrchestrator._validate_stage6
  Before: (self, transform: Transform, ctx: ApplyContext) -> StageOutcome
  After:  (self, transform: Transform, ctx: ApplyContext, *, retry: int = 0) -> StageOutcome

  This is a breaking change. Phase 5's GateRunner wraps this method by signature.
  If this change is intentional:
    1. Add or amend a Phase 3 ADR under docs/phases/03-vuln-deterministic-recipe/ADRs/.
    2. Add or amend the corresponding Phase 5 ADR.
    3. Regenerate the golden: pytest tests/integration/test_phase5_contract_snapshot.py --update-golden.
    4. Reference both ADRs in the PR description.
  ```
- [ ] The test exposes a `--update-golden` mode (custom pytest CLI flag or env var `PHASE5_CONTRACT_UPDATE_GOLDEN=1`) that rewrites the golden file with the current snapshot. The mode is INTENTIONALLY explicit — a developer must opt in.
- [ ] Additive deltas update the golden **automatically** in the test's golden-regen mode, but a **regenerated golden must still be committed** (the test fails in CI if the golden file is out of date even for additive changes — encoded as a separate assertion that compares `actual_snapshot` vs `golden_snapshot` strictly when in CI).
- [ ] The test is registered in `make check` and runs in CI on every PR (lift the existing integration-test invocation pattern).
- [ ] A meta-test `tests/integration/test_phase5_contract_snapshot_meta.py` exists that intentionally introduces a synthetic breaking change in a fixture module and asserts the diff algorithm correctly classifies it as breaking — proves the classifier works.
- [ ] The test docstring quotes ADR-0001 §Consequences row 2 verbatim and explains: *"Failure of this test means Phase 5 cannot ship. Treat snapshot mismatches as load-bearing."*
- [ ] The test file imports the six symbols via the public re-export path (`from codegenie.transforms import RemediationOrchestrator, TrustScorer, Transform, ApplyContext, RecipeEngine` per ADR-0001 §Consequences row 1) — not deep-import paths. This ensures the re-export contract is part of the snapshot.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff format`, `ruff check`, `mypy --strict` clean.

## Implementation outline

1. Write `tests/integration/test_phase5_contract_snapshot_meta.py` first (red) — the meta-test that proves the classifier works against synthetic breaking + additive changes.
2. Write `tests/integration/test_phase5_contract_snapshot.py` (red) — the main test that compares actual to golden.
3. Create `tests/golden/phase5-contract/snapshot.json` initially as an empty `{}` — first test run in "update" mode populates it from the actual S6-01..S6-05 surface.
4. Implement the snapshot-builder helpers in `tests/integration/_phase5_contract_helpers.py`:
   - `def snapshot_symbol(name: str, obj: Any) -> dict[str, Any]` — dispatches on `obj` type (class, Protocol, Pydantic model, ABC) and returns a canonical dict.
   - `def diff_snapshots(before: dict, after: dict) -> list[Delta]` where `Delta = Additive(...) | Breaking(...)`.
   - `def format_breaking_delta_message(delta: Breaking) -> str` — the directive message.
5. Wire the `--update-golden` flag (custom pytest option via `conftest.py` `pytest_addoption`).
6. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest tests/integration/test_phase5_contract_snapshot.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/integration/test_phase5_contract_snapshot_meta.py
"""Meta-test: prove the snapshot diff classifier distinguishes additive vs breaking."""
import pytest
from pydantic import BaseModel, Field

from tests.integration._phase5_contract_helpers import (
    snapshot_symbol, diff_snapshots, Additive, Breaking,
)


# Each stub builder returns a locally-defined class with one variation.
def _stub_v1():
    class S:
        def method_a(self, x: int) -> str: ...
    return S


def _stub_plus_method_b():       # ADDITIVE: new method
    class S:
        def method_a(self, x: int) -> str: ...
        def method_b(self, y: int) -> str: ...
    return S


def _stub_renamed():             # BREAKING: rename method_a → method_z
    class S:
        def method_z(self, x: int) -> str: ...
    return S


def _stub_required_arg_added():  # BREAKING: new required positional
    class S:
        def method_a(self, x: int, y: int) -> str: ...
    return S


def _stub_optional_kwarg():      # ADDITIVE: new kw-only with default
    class S:
        def method_a(self, x: int, *, z: int = 0) -> str: ...
    return S


@pytest.mark.parametrize("builder,is_additive", [
    (_stub_plus_method_b,        True),
    (_stub_optional_kwarg,       True),
    (_stub_renamed,              False),
    (_stub_required_arg_added,   False),
])
def test_class_method_delta_classification(builder, is_additive):
    before = snapshot_symbol("S", _stub_v1())
    after = snapshot_symbol("S", builder())
    deltas = diff_snapshots(before, after)
    if is_additive:
        assert all(isinstance(d, Additive) for d in deltas)
    else:
        assert any(isinstance(d, Breaking) for d in deltas)


# Pydantic-specific deltas (one parametrized test, same shape):
def _model_v1():
    class M(BaseModel):
        a: int
    return M

def _model_plus_optional():       # ADDITIVE
    class M(BaseModel):
        a: int
        b: list[str] = Field(default_factory=list)
    return M

def _model_plus_required():       # BREAKING
    class M(BaseModel):
        a: int
        b: int
    return M


@pytest.mark.parametrize("builder,is_additive", [
    (_model_plus_optional, True),
    (_model_plus_required, False),
])
def test_pydantic_field_delta_classification(builder, is_additive):
    before = snapshot_symbol("M", _model_v1())
    after = snapshot_symbol("M", builder())
    deltas = diff_snapshots(before, after)
    if is_additive:
        assert all(isinstance(d, Additive) for d in deltas)
    else:
        assert any(isinstance(d, Breaking) for d in deltas)
```

```python
# tests/integration/test_phase5_contract_snapshot.py
"""
Phase 5 contract snapshot test (ADR-0001 §Consequences row 2).
FAILURE OF THIS TEST MEANS PHASE 5 CANNOT SHIP.

Additive deltas permitted; breaking deltas (rename, remove, required-add,
signature change) fail CI and require ADR amendment + golden refresh in the
same PR.
"""
import json, os
from pathlib import Path
import pytest

# Import via the public re-export path (ADR-0001 §Consequences row 1).
from codegenie.transforms import (
    RemediationOrchestrator, TrustScorer, Transform, ApplyContext, RecipeEngine,
)
from codegenie.transforms.trust_scorer import TrustSignal, TrustOutcome
from codegenie.transforms.apply_context import AttemptSummary
from codegenie.transforms.report import RemediationReport  # from S5-05

from tests.integration._phase5_contract_helpers import (
    snapshot_symbol, diff_snapshots, Additive, Breaking, format_breaking_delta_message,
)

GOLDEN_PATH = Path(__file__).parent.parent / "golden" / "phase5-contract" / "snapshot.json"

SYMBOLS = {
    "RemediationOrchestrator": RemediationOrchestrator,
    "TrustScorer": TrustScorer, "TrustSignal": TrustSignal, "TrustOutcome": TrustOutcome,
    "Transform": Transform, "ApplyContext": ApplyContext, "AttemptSummary": AttemptSummary,
    "RecipeEngine": RecipeEngine, "RemediationReport": RemediationReport,
}


def test_phase5_contract_snapshot_matches_golden():
    actual = {n: snapshot_symbol(n, obj) for n, obj in SYMBOLS.items()}
    if os.environ.get("PHASE5_CONTRACT_UPDATE_GOLDEN") == "1":
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(json.dumps(actual, indent=2, sort_keys=True))
        pytest.skip("golden refreshed; rerun without the env var")
    assert GOLDEN_PATH.exists(), (
        f"Golden missing at {GOLDEN_PATH}. "
        "First-run: PHASE5_CONTRACT_UPDATE_GOLDEN=1 pytest <this file>"
    )
    golden = json.loads(GOLDEN_PATH.read_text())
    deltas = diff_snapshots(golden, actual)
    breaking = [d for d in deltas if isinstance(d, Breaking)]
    if breaking:
        msg = "\n\n".join(format_breaking_delta_message(d) for d in breaking)
        pytest.fail(f"PHASE 5 CONTRACT SNAPSHOT MISMATCH — BREAKING CHANGE.\n\n{msg}\n\n"
                    "Phase 5 cannot ship. See ADR-0001 §Consequences row 2.")
    additive = [d for d in deltas if isinstance(d, Additive)]
    if additive:
        pytest.fail("Additive deltas detected; golden is stale. Rerun with "
                    "PHASE5_CONTRACT_UPDATE_GOLDEN=1 and commit the updated golden.")


def test_phase5_named_symbols_re_exported_from_transforms_package():
    import codegenie.transforms as pkg
    for name in ["RemediationOrchestrator", "TrustScorer", "Transform",
                 "ApplyContext", "RecipeEngine"]:
        assert hasattr(pkg, name), f"missing re-export: codegenie.transforms.{name}"
```

Run; confirm `ImportError` until helpers exist + `AssertionError` from golden absence.

### Green — make it pass

- The `snapshot_symbol` dispatcher uses `inspect.isclass`, `issubclass(_, BaseModel)`, `inspect.isabstract`, etc. and returns a typed dict with keys `kind` ("class" / "pydantic_model" / "abc" / "protocol"), `signatures`, `fields`, `mro`, etc.
- The `diff_snapshots` walker recursively compares dicts; for each delta, classifies as `Additive` or `Breaking` based on the rules from the meta-test.
- The `format_breaking_delta_message` is a multi-line f-string per the directive-message acceptance criterion.
- First run with `PHASE5_CONTRACT_UPDATE_GOLDEN=1` populates the golden; commit it.

### Refactor — clean up

- The `_phase5_contract_helpers.py` module has its own unit tests (the meta-test); confirm coverage.
- Pin the directive message to a single helper for testability (the meta-test can assert the format).
- Document at the top of the test file: this is a load-bearing CI gate; treat mismatches with care.
- Ensure the helpers module is **not** in `src/codegenie/` (it's test-only); place under `tests/integration/_phase5_contract_helpers.py`.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_phase5_contract_snapshot.py` | New file — the main snapshot test |
| `tests/integration/test_phase5_contract_snapshot_meta.py` | New file — meta-test proves the additive-vs-breaking classifier |
| `tests/integration/_phase5_contract_helpers.py` | New file — `snapshot_symbol`, `diff_snapshots`, `Additive`/`Breaking`, `format_breaking_delta_message` |
| `tests/golden/phase5-contract/snapshot.json` | New file — frozen golden snapshot (first generated, then committed) |
| `tests/conftest.py` (extend if needed) | `--update-golden` pytest option wiring or env-var documentation |

## Out of scope

- **Modifying any of the six symbols** — they ship in S6-01..S6-05 and S1-03/S1-04/S5-01/S5-05; this story only freezes them.
- **A snapshot of `EventLog`** — `EventLog` is NOT one of the six ADR-0001 named symbols (Phase 5 does not depend on it directly; it depends on `TrustScorer` which constructor-injects an `EventLog`). The internal events taxonomy is gated by ADR-0005, not ADR-0001.
- **A snapshot of `SubgraphNode` Protocol** — internal to Phase 3's orchestrator (S6-03); Phase 6's LangGraph migration wraps it but that's not Phase 5's concern.
- **Cross-language snapshot (e.g., JSON-schema-of-JSON-schema)** — JSON schemas dumped at `indent=2, sort_keys=True` is enough; no canonicalization library.
- **Per-platform snapshot variations** — the test runs on Linux + macOS CI; the snapshot must be platform-independent.
- **Snapshot of recipe registrations** — recipes are open-for-extension; per-plugin registries are out of scope (ADR-0001 contract is the kernel, not the plugins).
- **`remediation-report.yaml` content (not schema) snapshot** — that's golden-file territory under `tests/golden/remediation-reports/`, owned by S8-02.

## Notes for the implementer

- **This is the most load-bearing test in Phase 3.** A passing snapshot is necessary-but-not-sufficient for Phase 5; a failing snapshot is *sufficient* to block Phase 5. Treat every CI failure as P0.
- **The additive-vs-breaking classifier is the heart of the story.** False-positive breaking → developers dismiss the test; false-positive additive → Phase 5 silently breaks. The meta-test is the safety net; extend it with every new classifier rule.
- **`extra="forbid"` → `extra="allow"` is BREAKING.** Phase 5 tests assume `extra="forbid"`; flipping it changes Pydantic's rejection semantics. The classifier must mark `model_config` deltas accordingly.
- **Discriminated-union variant additions are ADDITIVE** (per ADR-0001 §Tradeoffs row 5 + Phase 5 ADR-0003). A new `RecipeOutcome` variant from Phase 4 does not break Phase 5; `case _:` fallthroughs handle it. Add a variant-addition case to the meta-test.
- **The directive message in the failure output is intentional UX.** A future dev hitting this in CI is confused by default — they touched an unrelated file. The message must answer in one screen: (a) what changed, (b) why it's blocking, (c) the exact resolution procedure.
- **The golden file lives in the repo, not CI cache.** Committing makes drift visible in PR diffs (`git log -p tests/golden/phase5-contract/snapshot.json`).
- **`PHASE5_CONTRACT_UPDATE_GOLDEN=1` is an env var, not a CLI flag** — pytest's `--update-golden` may collide with other plugins.
- **The re-export check is a separate test from the snapshot.** A symbol renamed *only in the re-export* (not in the source module) would pass the snapshot (imported via `codegenie.transforms`) but break Phase 5 consumers using the deep-import path. Both must stay in sync.
- **`_validate_stage6` is in the snapshot despite the underscore prefix** (ADR-0001 §Tradeoffs load-bearing-but-private-looking). Renaming → breaking → caught.
- **Meta-test fixtures use locally-defined classes**, NOT modules under `src/codegenie/` — so they can be intentionally broken without affecting real code (same isolation as Phase 0 ADR-0002's per-test registry discipline).
- **CI integration: runs under `make check`** (per architecture spec §Testing strategy). If `make check` doesn't include `tests/integration/`, extend it to invoke this specific test path.
- **First-run setup**: golden absent → test fails with the directive; run `PHASE5_CONTRACT_UPDATE_GOLDEN=1 pytest <file>`, commit golden in same PR, PR description references ADR-0001 + the S6-06 landing.
