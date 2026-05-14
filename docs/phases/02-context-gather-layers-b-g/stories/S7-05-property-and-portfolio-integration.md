# Story S7-05 — Property tests + portfolio integration sweep

**Step:** Step 7 — Plant five-repo fixture portfolio + per-probe golden files + remaining adversarial corpus
**Status:** Ready
**Effort:** M
**Depends on:** S7-03 (~70 goldens exist; the portfolio sweep diffs against them; the regen script proves canonical-JSON discipline holds)
**ADRs honored:** ADR-0006 (`IndexFreshness` location — property test asserts round-trip identity over every `StaleReason` variant), ADR-0007 (no plugin loader — `dep_graph` strategy registry has zero strategies in Phase 2; property test asserts the dispatch is total over the closed `PackageManager` enum), ADR-0009 (pytest-xdist veto — property tests run serially under the same `--max-examples=200` budget), ADR-0010 (`RedactedSlice` smart constructor — property tests against `ScannerOutcome` round-trip exercise the `RedactedSlice` JSON shape without re-constructing it outside the sanitizer).

## Context

This story closes Step 7 with two complementary surfaces:

1. **Hypothesis property tests under `tests/property/`** — four files covering the round-trip / dispatch-totality / well-formedness invariants of the Phase-2 typed surfaces. Each runs with `--max-examples=200` (Hypothesis convention; tradeoff between coverage and CI wall-clock). These are **invariant tests over generated data**, complementing S7-03's **literal-data goldens** and S7-04's **adversarial cases**:
   - `test_index_freshness_roundtrip.py` — every `IndexFreshness` variant + every `StaleReason` variant round-trips through `model_dump_json` / `model_validate_json` to identity. Extends S1-01's single-example test to portfolio-wide hypothesis coverage. Catches: missing field, type-coercion silent loss, discriminator drift.
   - `test_scanner_outcome_roundtrip.py` — every `ScannerOutcome` variant (`ScannerRan | ScannerSkipped | ScannerFailed`) round-trips. Plus `ScenarioResult` (Layer C). Catches: same class of bug as above, separate type tree.
   - `test_dep_graph_strategy_dispatch.py` — the `@register_dep_graph_strategy` registry's dispatch is **total** over the closed `PackageManager` enum (Phase 1 ADR-0013). Phase 2 has zero strategies registered; every input produces `Result.Err(DepGraphRegistryError(reason="no_strategy_for_ecosystem"))` — that's the Phase-2 invariant. Phase 3 fills strategies; the property test grows with the strategy set. Catches: a future implementer who silently adds a strategy AND silently drops the Phase-2 total-dispatch property.
   - `test_trace_coverage_well_formed.py` — `TraceCoverage` is well-formed across any combination of `ScenarioResult` variants. Specifically: scenario count ≥ 0; completed-and-failed counts sum to total minus skipped; no scenario name appears twice.
2. **A portfolio-sweep integration test** — `tests/integration/portfolio/test_portfolio_sweep.py` — runs `codegenie gather` against every fixture in `tests/fixtures/portfolio/` **serially** (per ADR-0009; no pytest-xdist) and asserts: (a) every gather succeeds (exit 0); (b) the resulting `repo-context.yaml` validates against the Phase-2 envelope schema; (c) the golden diff (S7-03's regen script in `--check` mode) is empty. This is the "every probe runs against every fixture without crashing" smoke at the portfolio level; the CI `portfolio` job (S8-03) consumes it.

Both surfaces are **complementary**, not redundant:

- **Goldens** (S7-03) pin specific byte sequences for specific (probe × fixture) pairs.
- **Property tests** (this story) assert invariants over generated inputs the goldens cannot exhaustively cover (e.g., every `StaleReason` variant including ones the fixtures don't exercise).
- **Portfolio sweep** (this story) verifies the integration surface — every probe runs against every fixture without crashing, and the gather output remains shape-consistent across the portfolio.

This is the **final Step-7 story**. After it lands: Step 8 (Confidence renderer + CI ratchet + bench canaries + Phase-3 handoff issues) wires everything together. The cross-cutting invariant this story locks: every Phase-2 typed surface that participates in serialization has a Hypothesis round-trip property test; the portfolio sweep proves no fixture × probe combination crashes the gatherer.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Testing strategy" → "Property tests"` — the inventory of round-trip / dispatch / well-formed properties.
  - `../phase-arch-design.md §"Testing strategy" → "Test pyramid"` — property tests are the second-narrowest tier (above adversarial, below unit).
  - `../phase-arch-design.md §"Component design"` #2 (`IndexFreshness`), #5 (`ScannerOutcome`), #11 (`DepGraphProbe` strategy registry), and §"Component design" #6 (`TraceCoverage`).
- **Phase ADRs:**
  - ADR-0006 (`IndexFreshness` location — `frozen=True, extra="forbid"`; round-trip identity is the load-bearing property).
  - ADR-0010 (`RedactedSlice` smart constructor — property test for `ScannerOutcome` round-trip must NOT construct `RedactedSlice` outside `redact_secrets`; instead generates JSON-shaped `RedactedSlice` payloads and verifies they round-trip through `model_validate_json`).
- **Implementation plan:** `../High-level-impl.md §"Step 7"` — property-test bullets + portfolio-sweep bullet.
- **Existing code:**
  - `src/codegenie/indices/freshness.py` (S1-01 — the type under property test).
  - `src/codegenie/probes/_shared/scanner_outcome.py` (S5-01 — the type under property test).
  - `src/codegenie/probes/layer_c/scenario_result.py` (S5-01).
  - `src/codegenie/depgraph/registry.py` (S1-10 — the registry).
  - `src/codegenie/probes/layer_c/runtime_trace.py` (S5-02 — `TraceCoverage` lives here or in a sibling module).
  - All five fixtures from S7-01 + S7-02.
  - `scripts/regen_golden.py --check --portfolio` (S7-03).
- **Existing Hypothesis test precedents:** Phase 0 / Phase 1 property tests if any exist (search `tests/property/` and `tests/unit/` for `@given` decorators).

## Goal

Five new test files exist:

1. `tests/property/test_index_freshness_roundtrip.py` — Hypothesis property test over `IndexFreshness` + every `StaleReason` variant; `--max-examples=200`.
2. `tests/property/test_scanner_outcome_roundtrip.py` — Hypothesis property test over `ScannerOutcome` + `ScenarioResult` variants; `--max-examples=200`.
3. `tests/property/test_dep_graph_strategy_dispatch.py` — Hypothesis property test that dispatch is total over `PackageManager`; in Phase 2 every input produces typed `Result.Err`; mock strategies exercised; `--max-examples=200`.
4. `tests/property/test_trace_coverage_well_formed.py` — Hypothesis property test that `TraceCoverage` is well-formed across any combination of `ScenarioResult` variants; `--max-examples=200`.
5. `tests/integration/portfolio/test_portfolio_sweep.py` — serial portfolio sweep; gathers every fixture; asserts schema validation + golden diff empty.

## Acceptance criteria

**`test_index_freshness_roundtrip.py`**

- [ ] **AC-1.** `tests/property/test_index_freshness_roundtrip.py` exists; uses `hypothesis` with `@given` strategies that generate every `IndexFreshness` variant (`Fresh`, `Stale(reason=<each StaleReason variant>)`).
- [ ] **AC-2 — variant coverage.** Every `StaleReason` variant is reachable: `CommitsBehind(n, last_indexed)`, `DigestMismatch(last_traced, current_built)`, `CoverageGap(missing_files, indexed_files, total_files)`, `IndexerError(message)`. A `@given(reason=hypothesis.strategies.one_of(...))` composition covers all.
- [ ] **AC-3 — round-trip identity.** For every generated `IndexFreshness` instance `x`: `IndexFreshness.model_validate_json(x.model_dump_json()) == x`. The Pydantic discriminated-union should make this trivial; the property test catches accidental field-drift or discriminator-name changes.
- [ ] **AC-4 — `--max-examples=200`.** The test uses Hypothesis's `@settings(max_examples=200, deadline=None)` (deadline disabled because round-trip latency is variable on CI).
- [ ] **AC-5 — assert_never enforcement.** A separate (non-property) test exhaustively pattern-matches on `IndexFreshness` AND on every `StaleReason` with `assert_never` on the closing case. A missing `case` triggers `mypy --warn-unreachable` failure (the per-module override from S1-11 applies to this test). Extends S1-01's single-example test.
- [ ] **AC-6 — wall-clock < 30 s on CI.** `--max-examples=200` × round-trip should fit easily. If not, the type itself is non-trivial in its round-trip path; investigate.

**`test_scanner_outcome_roundtrip.py`**

- [ ] **AC-7.** `tests/property/test_scanner_outcome_roundtrip.py` exists; uses Hypothesis to generate every `ScannerOutcome` variant (`ScannerRan`, `ScannerSkipped`, `ScannerFailed`) and every `ScenarioResult` variant (`TraceScenarioCompleted`, `TraceScenarioFailed`, `TraceScenarioSkipped`).
- [ ] **AC-8 — `ScannerRan` `findings_count` matches `fingerprints` length.** A custom Hypothesis strategy enforces the invariant. The round-trip preserves it.
- [ ] **AC-9 — `ScannerRan.fingerprints` are 8-hex strings only.** Per ADR-0005 + ADR-0010 — never plaintext. Hypothesis generates 8-hex strings (`hypothesis.strategies.from_regex(r"^[0-9a-f]{8}$", fullmatch=True)`).
- [ ] **AC-10 — round-trip identity.** For every generated `ScannerOutcome` AND every generated `ScenarioResult`: `T.model_validate_json(x.model_dump_json()) == x`.
- [ ] **AC-11 — `--max-examples=200`** with `deadline=None`.
- [ ] **AC-12 — `RedactedSlice` is NOT constructed outside the sanitizer.** Inherited from S7-04's structural test — but cross-check: this story's property test must NOT construct a `RedactedSlice` directly (it can construct `ScannerRan` which references `RedactedSlice`, BUT only via `RedactedSlice.model_validate_json(...)` of a JSON shape, which is allowed inside the `codegenie.output.sanitizer` module — but this is a property test, not the sanitizer). Resolution: the property test generates `ScannerRan` instances WITHOUT a `RedactedSlice` field directly; it tests `ScannerOutcome` round-trip at the **outer** layer, treating the redacted_slice payload as opaque. If `ScannerRan` carries a `RedactedSlice` field by design (per S5-01), the property test generates `ScannerRan` from a pre-redacted slice obtained by calling `redact_secrets(<test-only synthetic ProbeOutput>)`. This is the **one** allowed way to obtain a `RedactedSlice` outside the sanitizer module — and it goes THROUGH the sanitizer, not around it. The S7-04 structural test allows the `redact_secrets` call from anywhere (it only forbids `RedactedSlice` construction outside the sanitizer).

**`test_dep_graph_strategy_dispatch.py`**

- [ ] **AC-13.** `tests/property/test_dep_graph_strategy_dispatch.py` exists.
- [ ] **AC-14 — dispatch totality.** Hypothesis generates every `PackageManager` enum member (closed set per Phase 1 ADR-0013: `npm`, `pnpm`, `yarn-classic`, `yarn-berry`, plus any others ADR-0013 added). For every member, `dep_graph_registry.lookup(<member>)` returns either a `Result.Ok(strategy)` (Phase 3+) or a typed `Result.Err(DepGraphRegistryError(reason="no_strategy_for_ecosystem", ecosystem=<member>))` (Phase 2). **NEVER** raises an uncaught exception.
- [ ] **AC-15 — Phase 2 invariant.** With zero strategies registered (the Phase-2 state per S1-10), every `PackageManager` member returns `Result.Err`. The property test asserts this; if Phase 3 lands a strategy that registers globally at import time, the test will fail loudly — which is the desired contract trip-wire (the Phase-3 PR must explicitly update this test, NOT silently break it).
- [ ] **AC-16 — mock strategy registration.** A separate (non-property) test registers a mock strategy for one `PackageManager` member via the registry's decorator, runs the property test (restricted to that one member), asserts `Result.Ok`, and unregisters the mock in teardown. This proves the registry's Open/Closed seam works.
- [ ] **AC-17 — `--max-examples=200`** with `deadline=None` (overkill for the closed enum, but consistent with the other property tests; Hypothesis quickly exhausts the closed set and moves to repeats, which is harmless).
- [ ] **AC-18 — wall-clock < 10 s on CI.**

**`test_trace_coverage_well_formed.py`**

- [ ] **AC-19.** `tests/property/test_trace_coverage_well_formed.py` exists.
- [ ] **AC-20 — well-formedness invariants.** Hypothesis generates a list of `ScenarioResult` (any combination of `Completed`, `Failed`, `Skipped`); constructs `TraceCoverage` from it; asserts:
  - `total >= 0`.
  - `completed + failed + skipped == total`.
  - `len(set(scenario.name for scenario in results)) == len(results)` — no scenario name appears twice (uniqueness invariant).
  - If `total == 0`, `TraceCoverage`'s confidence is `"unavailable"` (the canonical-empty case).
- [ ] **AC-21 — round-trip identity.** `TraceCoverage.model_validate_json(x.model_dump_json()) == x`.
- [ ] **AC-22 — `--max-examples=200`** with `deadline=None`.
- [ ] **AC-23 — assert_never on `ScenarioResult` variants** in a separate exhaustive-match unit test. Mirrors AC-5's discipline.
- [ ] **AC-24 — wall-clock < 30 s on CI.**

**`test_portfolio_sweep.py` — serial portfolio integration**

- [ ] **AC-25.** `tests/integration/portfolio/test_portfolio_sweep.py` exists; gathers every fixture under `tests/fixtures/portfolio/` serially (`for fixture in sorted(fixtures): subprocess.run(...)`) via `run_allowlisted`.
- [ ] **AC-26 — every gather exits 0.** For each fixture, `codegenie gather <fixture>` returns exit code 0; stderr is empty or contains only documented warnings (`skill_shadowed`, the macOS `strace` warning if applicable). Stderr containing the word `Error` or `Traceback` fails the test.
- [ ] **AC-27 — envelope schema validation.** For each fixture's resulting `repo-context.yaml`, the test loads it via `safe_yaml.load` AND validates against the Phase-2 envelope schema (`src/codegenie/schema/repo_context.schema.json` extended in Steps 4–6). Validation failure fails the test with the JSONSchema error path.
- [ ] **AC-28 — golden diff empty.** After gathering, the test invokes `scripts/regen_golden.py --check --portfolio` and asserts exit 0. (Redundant with `tests/golden/test_goldens_match.py` from S7-03, but appropriate here because the portfolio sweep is the integration-level gate; the golden harness is the unit-test-level gate.)
- [ ] **AC-29 — wall-clock budget ≤ 6 minutes.** Per `phase-arch-design.md §"Testing strategy"` `portfolio` job budget. If the sweep exceeds 6 min on the CI runner, escalate to the hosted-runner bench escape valve documented in `final-design.md §"Open questions"` #6 (commit per-fixture `.codegenie/cache/` blobs — but **not** as part of this story; the escape valve is an S8-03+ concern). For this story, target ≤ 5 min on the developer's local machine to leave CI headroom.
- [ ] **AC-30 — serial dispatch.** No `pytest-xdist`, no `multiprocessing`, no `asyncio.gather` — for-loop iteration with sequential `subprocess.run`. ADR-0009 honored.
- [ ] **AC-31 — clean tmpdir per fixture.** Each fixture is copied to a fresh `tmp_path` before gathering (`cp -R`), so the canonical fixture tree is never dirtied. Cache + context outputs land in the tmpdir.
- [ ] **AC-32 — wall-clock per fixture recorded.** The test prints (via pytest's `-s` or via a `tests/integration/portfolio/walltimes.json` artifact) the per-fixture wall-clock; this is the seed dataset S8-03's `bench_portfolio_walltime.py` consumes for baseline.

**Determinism, audit hygiene, type cleanliness**

- [ ] **AC-33 — every property test passes `mypy --strict`.** Hypothesis's `@given` decorators carry full type annotations; no `Any` outside what Hypothesis's API demands.
- [ ] **AC-34 — Hypothesis strategies are explicit, not `from_type`-magic.** Each property test declares its strategies explicitly (e.g., `commits_behind_strategy = hypothesis.strategies.builds(CommitsBehind, n=integers(min_value=1), last_indexed=text(...))`). `hypothesis.strategies.from_type(IndexFreshness)` would silently DTRT (or fail to) — explicit beats implicit, especially for discriminated unions.
- [ ] **AC-35 — no flakes.** Each property test passes 100/100 runs on CI with the same Hypothesis seed (`@settings(database=None)` disables Hypothesis's persistent example database to keep CI runs reproducible; alternatively, commit the database under `tests/property/.hypothesis/`). Implementer's call; document the choice in the PR.
- [ ] **AC-36 — portfolio sweep passes against all five fixtures** (smoke-verified locally before opening PR).

## Implementation outline

1. **TDD red — write `test_index_freshness_roundtrip.py` first.** Plant the `@given` decorators; assert round-trip identity. With S1-01's types in place, the test should pass on first run. **If it doesn't, the type is buggy** — Pydantic discriminator drift or `frozen=True` violation. Fix the type, not the test.
2. **Add the `assert_never` exhaustive-match test** (AC-5). Run mypy `--warn-unreachable`; observe pass. Temporarily comment out one `case` line and re-run; observe mypy failure. Restore. Commit.
3. **Write `test_scanner_outcome_roundtrip.py`.** Same pattern. The `RedactedSlice` invariant (AC-12) is the subtle bit: if `ScannerRan` carries a `RedactedSlice` field, the property test must obtain `RedactedSlice` instances **only** via `redact_secrets(<synthetic input>)` — never via direct `RedactedSlice(...)` construction. Document this in the test file's top comment.
4. **Write `test_dep_graph_strategy_dispatch.py`.** The Phase-2 invariant (zero strategies → every member returns `Err`) is the load-bearing case. Implement the mock-strategy registration / unregistration as a pytest fixture (`@pytest.fixture` with explicit teardown). Run; observe pass.
5. **Write `test_trace_coverage_well_formed.py`.** Hypothesis strategy for `list[ScenarioResult]` is the non-trivial bit — generate combinations with the uniqueness constraint (`unique_by=lambda s: s.name`); construct `TraceCoverage`; assert invariants. Run; observe pass.
6. **Write `test_portfolio_sweep.py`.** Serial for-loop; copy each fixture to `tmp_path`; `run_allowlisted(...)`; check exit + schema + golden-diff. Run; observe pass (or debug the failing fixture + probe combination).
7. **Stabilize.** Run each property test 100 times locally with the same `--hypothesis-seed=0`. Confirm 100/100 passes. If any flake, investigate — Hypothesis's persistent database is a common culprit (it remembers shrinking examples that may have race-conditioned in a prior run); set `database=None` per AC-35.
8. Run the portfolio sweep locally; record per-fixture wall-clock; sanity-check the 6-min budget headroom (AC-29). If a fixture exceeds expectation, debug — usually a probe regressing into a worst-case path.
9. Final pass: `mypy --strict`, `ruff check`, `ruff format --check`. Run the full Phase 2 test suite (including the property tests + portfolio sweep). Green.

## TDD plan — red / green / refactor

### Red — failing property tests first

```python
# tests/property/test_index_freshness_roundtrip.py
from __future__ import annotations
import hypothesis
import hypothesis.strategies as st
from hypothesis import given, settings
from codegenie.indices.freshness import (
    Fresh, Stale, CommitsBehind, DigestMismatch, CoverageGap, IndexerError,
    IndexFreshness, StaleReason,
)

# Explicit strategies — AC-34
_sha_strategy = st.text(alphabet="0123456789abcdef", min_size=40, max_size=40)
_commits_behind = st.builds(CommitsBehind, n=st.integers(min_value=1, max_value=10000), last_indexed=_sha_strategy)
_digest_mismatch = st.builds(DigestMismatch,
                              last_traced=st.text(min_size=64, max_size=64),
                              current_built=st.text(min_size=64, max_size=64))
_coverage_gap = st.builds(CoverageGap,
                          missing_files=st.integers(min_value=0),
                          indexed_files=st.integers(min_value=0),
                          total_files=st.integers(min_value=0))
_indexer_error = st.builds(IndexerError, message=st.text(min_size=1, max_size=200))

_stale_reason = st.one_of(_commits_behind, _digest_mismatch, _coverage_gap, _indexer_error)
_stale = st.builds(Stale, reason=_stale_reason)
_fresh = st.builds(Fresh)
_index_freshness = st.one_of(_fresh, _stale)

@given(x=_index_freshness)
@settings(max_examples=200, deadline=None, database=None)
def test_index_freshness_roundtrip(x: IndexFreshness) -> None:
    """AC-3 — round-trip identity through model_dump_json/model_validate_json."""
    serialized = x.model_dump_json()
    deserialized = IndexFreshness.model_validate_json(serialized)
    assert deserialized == x

# AC-5 — exhaustive match with assert_never (separate, non-property)
from typing import assert_never

def _stringify(x: IndexFreshness) -> str:
    match x:
        case Fresh():
            return "fresh"
        case Stale(reason=CommitsBehind(n=n)):
            return f"stale_commits_behind_{n}"
        case Stale(reason=DigestMismatch()):
            return "stale_digest_mismatch"
        case Stale(reason=CoverageGap()):
            return "stale_coverage_gap"
        case Stale(reason=IndexerError()):
            return "stale_indexer_error"
        case _:
            assert_never(x)

def test_exhaustive_match_assert_never() -> None:
    """AC-5 — match is exhaustive over every StaleReason variant; mypy --warn-unreachable enforces it."""
    assert _stringify(Fresh()) == "fresh"
    assert _stringify(Stale(reason=CommitsBehind(n=1, last_indexed="a"*40))).startswith("stale_commits_behind_")
    assert _stringify(Stale(reason=DigestMismatch(last_traced="x"*64, current_built="y"*64))) == "stale_digest_mismatch"
    assert _stringify(Stale(reason=CoverageGap(missing_files=0, indexed_files=0, total_files=0))) == "stale_coverage_gap"
    assert _stringify(Stale(reason=IndexerError(message="boom"))) == "stale_indexer_error"
```

`test_portfolio_sweep.py` skeleton:

```python
# tests/integration/portfolio/test_portfolio_sweep.py
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
import pytest
import yaml
from jsonschema import validate
from codegenie.exec import run_allowlisted

_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_PORTFOLIO = _REPO_ROOT / "tests" / "fixtures" / "portfolio"
_SCHEMA = _REPO_ROOT / "src" / "codegenie" / "schema" / "repo_context.schema.json"

def _enumerate_fixtures() -> list[Path]:
    return sorted(p for p in _PORTFOLIO.iterdir() if p.is_dir() and not p.name.startswith("_"))

@pytest.mark.serial  # AC-30
def test_portfolio_sweep(tmp_path: Path) -> None:
    """AC-25..AC-31 — serial sweep over the five fixtures; schema + golden diff verified."""
    schema = json.loads(_SCHEMA.read_text())
    walltimes: dict[str, float] = {}

    for fixture in _enumerate_fixtures():
        # AC-31: clean tmpdir per fixture
        workdir = tmp_path / fixture.name
        subprocess.run(["cp", "-R", str(fixture), str(workdir)], check=True)

        import time
        t0 = time.perf_counter()
        result = run_allowlisted(
            [sys.executable, "-m", "codegenie", "gather", str(workdir)],
            cwd=_REPO_ROOT, timeout_seconds=180,
        )
        walltimes[fixture.name] = time.perf_counter() - t0

        # AC-26
        assert result.exit_code == 0, f"{fixture.name}: stderr={result.stderr_tail!r}"
        assert b"Traceback" not in result.stderr_tail, f"{fixture.name}: Traceback in stderr"

        # AC-27: envelope schema validation
        ctx = workdir / ".codegenie" / "context" / "repo-context.yaml"
        validate(instance=yaml.safe_load(ctx.read_text()), schema=schema)

    # AC-28: golden diff empty
    check_result = run_allowlisted(
        [sys.executable, str(_REPO_ROOT / "scripts" / "regen_golden.py"), "--check", "--portfolio"],
        cwd=_REPO_ROOT, timeout_seconds=120,
    )
    assert check_result.exit_code == 0, (
        f"Golden diff non-empty:\n{check_result.stderr_tail.decode()}"
    )

    # AC-32: record walltimes for S8-03's bench seed
    (_REPO_ROOT / "tests" / "integration" / "portfolio" / "walltimes.json").write_text(
        json.dumps(walltimes, sort_keys=True, indent=2) + "\n"
    )
```

### Green — make it pass

With S1-01, S5-01, S1-10, and S5-02 types in place AND S7-03's goldens committed AND all five fixtures from S7-01/S7-02 on disk, every test in this story should pass on first run. If any fails, the failure points to a real bug — fix the production code, not the test.

### Mutation-resistance witness table

| Mutation | Test that catches it |
|---|---|
| Add `IndexFreshness` variant `Stale.NetworkPartition` (missing discriminator) | `test_index_freshness_roundtrip` — `model_validate_json` fails on round-trip; `test_exhaustive_match_assert_never` fires mypy `--warn-unreachable` |
| Drop the `n` field from `CommitsBehind` | `test_index_freshness_roundtrip` round-trip fails |
| Allow plaintext-secret string in `ScannerRan.fingerprints` (regex regression) | `test_scanner_outcome_roundtrip` — Hypothesis 8-hex strategy catches it in the strategy's `from_regex` |
| Future contributor adds a dep-graph strategy without updating `test_dep_graph_strategy_dispatch.py` | The Phase-2 invariant (zero strategies → every member returns `Err`) fails — the test fails loudly, forcing the Phase-3 PR to explicitly update |
| `TraceCoverage` accepts duplicate scenario names | `test_trace_coverage_well_formed` uniqueness invariant fails |
| `TraceCoverage` constructor allows `completed + failed + skipped != total` | Same — well-formedness invariant fails |
| A fixture × probe combination crashes (e.g., `DepGraphProbe` against `monorepo-pnpm` hits an unhandled `KeyError`) | `test_portfolio_sweep` — exit-code-non-zero assertion fires; `Traceback` in stderr fires |
| A probe's slice schema drifts (e.g., adds a new field without updating `repo_context.schema.json`) | `test_portfolio_sweep` — `jsonschema.validate` fails |
| Golden file silently goes stale | `test_portfolio_sweep` AC-28 — `regen_golden.py --check` returns non-zero |
| Implementer enables `pytest-xdist` for the portfolio sweep | `@pytest.mark.serial` annotation + the for-loop iteration make this impossible to silently enable; an explicit edit would fire on review |

### Refactor — clean up

- The four property-test files share a structural pattern (Hypothesis strategy declarations → `@given` round-trip → `assert_never` exhaustive match). **DO NOT extract a kernel** — four consumers is at the Rule-of-Three boundary, but the variant-strategy declarations are specific to each type (`StaleReason` for one, `ScenarioResult` for another); extracting would require dependency-injecting the type, which obscures more than it clarifies. Re-evaluate at the fifth property test (Phase 3+).
- `test_portfolio_sweep.py`'s walltime recording (AC-32) is the seed S8-03's `bench_portfolio_walltime.py` consumes. The file format (`{fixture_name: walltime_seconds}`) is documented in this story's PR description; S8-03 inherits the contract.
- `--max-examples=200` is a Hypothesis convention; the budget assumes round-trip work is cheap. If a property test exceeds its AC-budget (AC-6, AC-11, AC-18, AC-22, AC-24, AC-29), the bottleneck is either Hypothesis shrinking (set `phases=[...]` to skip shrinking on CI) OR the type's round-trip latency itself (investigate Pydantic field count, custom validators).

## Files to touch

| Path | Why |
|---|---|
| `tests/property/test_index_freshness_roundtrip.py` | Hypothesis round-trip + assert_never exhaustive match |
| `tests/property/test_scanner_outcome_roundtrip.py` | Same for `ScannerOutcome` + `ScenarioResult` |
| `tests/property/test_dep_graph_strategy_dispatch.py` | Dispatch totality over `PackageManager`; Phase-2 zero-strategy invariant |
| `tests/property/test_trace_coverage_well_formed.py` | Well-formedness invariants over `TraceCoverage` |
| `tests/integration/portfolio/test_portfolio_sweep.py` | Serial sweep + schema + golden-diff |
| `tests/integration/portfolio/walltimes.json` | Per-fixture wall-clock seed for S8-03 bench |
| `tests/property/conftest.py` (optional) | Hypothesis settings profile (`max_examples`, `deadline`, `database`) |

## Out of scope

- **CI wiring** (`portfolio` + `property` job lanes) — S8-03.
- **`bench_portfolio_walltime.py` + baselines** — S8-03.
- **Hosted-runner bench (Gap 2)** — S8-03.
- **Confidence-renderer + `assert_never` mypy --warn-unreachable enforcement at the renderer site** — S8-01.
- **A generic property-test kernel** — premature; four consumers.
- **Hypothesis stateful tests** (state-machine-based) — out; the Phase-2 types under property test are immutable / Pydantic frozen; stateful testing offers no advantage.
- **A `--max-examples=2000` deep-property CI lane** — out; `200` is the convention; deepening it is a bench-driven decision, not a Phase-2 story.

## Notes for the implementer

- **The property tests should pass on first run.** If `test_index_freshness_roundtrip` fails, the bug is in `codegenie.indices.freshness` (S1-01) — investigate the Pydantic model. Don't paper over with strategy restrictions.
- **Hypothesis's persistent example database is a CI flake source.** Set `database=None` in `@settings(...)` for CI determinism, OR commit `tests/property/.hypothesis/` under git (an interesting choice — Hypothesis maintains shrinking history; committing it means CI starts from a "warm" set of edge cases). Recommendation: `database=None` for Phase 2; commit history can come in Phase 4+ if the property tests grow.
- **`--max-examples=200` is the Hypothesis convention.** Not 100 (under-coverage), not 2000 (over-budget). The Phase-2 types are small enough that 200 examples cover the variant space and find any discriminator regression quickly.
- **Use `hypothesis.strategies.builds(...)` not `from_type(...)`.** The discriminated unions are not Hypothesis-introspectable by default; explicit strategies are predictable. AC-34 names this.
- **The `assert_never` test is the load-bearing Phase-2 type-safety enforcement.** `mypy --warn-unreachable` on the per-module override (S1-11) fires if any `case` is missing. Test this manually: temporarily comment out one `case` in `_stringify`, run `mypy --warn-unreachable src/codegenie/indices/freshness.py tests/property/test_index_freshness_roundtrip.py`, observe failure, restore. Document the deliberate-fail-then-pass in PR.
- **`test_portfolio_sweep.py`'s per-fixture wall-clock budget is generous (180 s timeout per fixture).** That's far more than the cold p50 (≤ 90 s) target. The 6-minute sweep budget (AC-29) covers all five fixtures with headroom. If a single fixture's gather exceeds 90 s in development, that's a probe-regression signal — investigate before merging.
- **The `tests/integration/portfolio/walltimes.json` artifact is committed empty initially.** It is updated by the test run; the file is regenerated each time (the test writes it unconditionally). S8-03 will hook into this — the bench script reads the file to seed baselines. Document the cross-story handoff in this story's PR.
- **Why `serial` mark on `test_portfolio_sweep`.** Pytest's `pytest-xdist` is vetoed (ADR-0009); the `serial` mark is a pytest convention for tests that explicitly opt out of parallelization. The portfolio sweep is the canonical serial-only test in Phase 2. The mark is a documentation aid + a future-proofing hook in case a future contributor enables xdist for unit tests but forgets to exclude this one.
- **The Phase-2 zero-strategy invariant (AC-15) is the load-bearing Phase-3 trip-wire.** When Phase 3 lands its first `@register_dep_graph_strategy(PackageManager.npm) def npm_strategy(...)`, this property test fails on the Phase 3 PR — which is correct. The Phase 3 author updates the test to reflect "Phase 3 has at least one strategy; for `PackageManager.npm`, expect `Result.Ok(...)`; for the others, still expect `Result.Err`". This is the explicit Open/Closed seam Phase 2 documented. Document this handoff in the test file's top comment and in S8-04's Phase-3-handoff issue.

### Patterns DELIBERATELY deferred (per Rule 2)

- **A generic property-test kernel** — four consumers; deferred until a fifth.
- **Stateful property tests** — out; types are immutable.
- **Hypothesis `database` committed under git** — out; `database=None` is the simpler choice for Phase 2.
- **A `--max-examples=2000` "deep" CI lane** — out until bench data shows the shallow lane misses real bugs.
- **A `tests/property/test_redacted_slice_roundtrip.py`** — explicitly out. `RedactedSlice` round-trip is covered structurally by S7-04 and implicitly by `test_scanner_outcome_roundtrip` (when `ScannerRan` carries a `RedactedSlice`); a dedicated property test would either (a) construct `RedactedSlice` outside the sanitizer (violates S7-04's structural test) or (b) go through `redact_secrets` for every Hypothesis example (slow, redundant with the `ScannerOutcome` test). The trade-off is documented; revisit if Gap 4 surfaces a new failure mode.
