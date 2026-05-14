# Story S4-01 — `IndexHealthProbe` (B2) + registry-dispatched freshness loop

**Step:** Step 4 — Ship `IndexHealthProbe` (B2) + Layer B structural probes
**Status:** Ready
**Effort:** L
**Depends on:** S1-02 (`@register_index_freshness_check` registry + `IndexFreshness` sum type on disk), S1-08 (`@register_probe(heaviness=, runs_last=)` decorator kwargs + coordinator sort-order edit), S3-03 (writer-chokepoint `SecretRedactor` lands before any probe persists output — B2 reads sibling slices that have already been through redaction)
**ADRs honored:** 02-ADR-0003 (`runs_last=True` is a registry annotation, NOT a `Probe` ABC field — scheduling concern at the coordinator's layer), 02-ADR-0006 (`IndexFreshness` lives at `codegenie.indices.freshness`; B2 is its primary Phase-2 producer; `confidence_section.py` is the consumer), Phase 0 ADR — probe contract preserved (the `Probe` ABC is untouched; B2 subclasses the frozen ABC), Phase 1 ADR-0004 (sub-schema `additionalProperties: false` at root — sub-schema lands in S4-07), Phase 1 ADR-0007 (warning/error ID pattern — every emitted ID conforms), Phase 1 ADR-0010 (slice optional at envelope — B2's slice is OPTIONAL when the probe is skipped, which it never is by default)

## Context

`IndexHealthProbe` is **the load-bearing citizen of Phase 2** ([phase-arch-design.md §"Component design" #1](../phase-arch-design.md), [final-design §"Components" #1](../final-design.md), [production design.md §2.3](../../../production/design.md), [`CLAUDE.md`](../../../../CLAUDE.md) "Honest confidence" commitment). Silent index staleness is the worst failure mode of the entire system: a `RepoContext` slice that *says* it's current but isn't propagates wrong evidence through every downstream consumer — the Planner, the renderer, the Phase-3 plugin, every adapter. Phase 2's roadmap exit criterion is operational: a deliberately-seeded `stale-scip` fixture must be caught by B2, build FAILS otherwise (encoded in S4-02). This probe is what makes the commitment real.

Two design disciplines are load-bearing and **must not erode** under any future "optimization" pressure:

1. **`cache_strategy="none"`.** B2 observes a *moving* fact (HEAD vs. last_indexed). Caching that is "the same bug as caching `Date.now()`" ([phase-arch-design.md §"Harness engineering"](../phase-arch-design.md), §"Component design" #1 line 460). A per-module pre-commit hook bans `os.path.getmtime` and `Path.stat().st_mtime` inside `src/codegenie/probes/layer_b/index_health.py` — mtime is not a freshness signal and a future contributor proposing "let's cache B2 for performance" must be redirected to the hook + this story.
2. **`runs_last=True`** ([ADR-0003](../ADRs/0003-coordinator-heaviness-sort-annotation.md)). B2 dispatches **after** every sibling probe — enforced by the registry annotation, not by topological `requires=[every-other-probe]` (which the performance lens proposed and the synthesis rejected; that hack scales O(N) and lies about dependencies since B2 reads sibling *outputs*, not their *execution*).

The Gap-3 improvement ([phase-arch-design.md §"Gap analysis & improvements"](../phase-arch-design.md), [ADR-0006 §Consequences last bullet](../ADRs/0006-index-freshness-sum-type-location.md)) makes B2 Open/Closed at the file boundary: rather than B2's `run()` containing a chain of `if index_name == "scip": ... elif "runtime_trace": ...` branches, it **loops the `@register_index_freshness_check` registry** (planted in Step 1 at `src/codegenie/indices/registry.py`). Each Phase-2 index source registers a small function `(slice: dict[str, JSONValue], head: str) -> IndexFreshness` in its **own** file (S5-05 for `runtime_trace`, S6-08 for `semgrep`/`gitleaks`/`conventions`). Adding a Phase-3 index source is a new file + new decorator, **never an edit to `index_health.py`**. Pattern symmetry with `@register_probe` and `@register_dep_graph_strategy` is itself a documentation win.

This story lands the probe shell, the registry-loop dispatcher, the SCIP-specific freshness check (the only freshness check Phase 2 owns in this story — the rest are registered in their owning probe stories), and the unit tests that exercise every `IndexFreshness` variant through synthetic sibling slices. The CI-gating `test_stale_scip_fixture.py` adversarial lands in S4-02; the SCIP probe that produces the `semantic_index` slice B2 reads lands in S4-03. The story chain `S3-03 → S4-01 → S4-02 → S7-02 → S7-03 → S7-04 → S8-01` is the longest in Phase 2 and ties the security chokepoint → load-bearing-adversarial → goldens → renderer path.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md §"Component design" #1`](../phase-arch-design.md) — full internal structure, perf envelope, failure behavior, the `cache_strategy="none"` mypy-flag forbidden-list.
  - [`../phase-arch-design.md §"Component design" #2`](../phase-arch-design.md) — `IndexFreshness` Pydantic shape (`Fresh`, `Stale`, four `StaleReason` variants); consumer requirement.
  - [`../phase-arch-design.md §"Process view"`](../phase-arch-design.md) — load-bearing properties 1 (`runs_last=True`) and 3 (sibling-output read, not `requires=` topology); Scenario 2 (Stale-SCIP catches in CI) sequence diagram.
  - [`../phase-arch-design.md §"Data model"`](../phase-arch-design.md) lines 660–691 — `CommitsBehind`, `DigestMismatch`, `CoverageGap`, `IndexerError`, `Fresh`, `Stale`; the four reasons + two top-level variants.
  - [`../phase-arch-design.md §"Edge cases"`](../phase-arch-design.md) rows 6 (`strace` macOS — B2 emits `Stale(IndexerError("strace_unavailable"))`), 11 (stale-SCIP fixture).
  - [`../phase-arch-design.md §"Gap analysis & improvements" Gap 3`](../phase-arch-design.md) — `@register_index_freshness_check` rationale.
  - [`../phase-arch-design.md §"Harness engineering"`](../phase-arch-design.md) — "caching a moving fact is the Date.now() bug" framing.
- **Phase 2 ADRs:**
  - [`../ADRs/0003-coordinator-heaviness-sort-annotation.md`](../ADRs/0003-coordinator-heaviness-sort-annotation.md) — `runs_last=True` is registry-side; the `Probe` ABC is untouched.
  - [`../ADRs/0006-index-freshness-sum-type-location.md`](../ADRs/0006-index-freshness-sum-type-location.md) — `IndexFreshness` location, variants are stable, ADR-amend on a fifth.
  - [`../ADRs/0004-image-digest-as-declared-input-token.md`](../ADRs/0004-image-digest-as-declared-input-token.md) — image-digest-token shape (B2 reads `last_traced_image_digest` and `built_image_digest` for the `runtime_trace` source).
- **Source design:**
  - [`docs/localv2.md §5.2 B2`](../../../localv2.md) — `index_health` slice shape (per-index-source nested dict).
  - [`docs/production/design.md §2.3`](../../../production/design.md) — Honest confidence commitment.
- **Existing code:**
  - `src/codegenie/probes/base.py` (frozen — subclass; do not edit).
  - `src/codegenie/probes/__init__.py` — explicit additive import for B2.
  - `src/codegenie/probes/registry.py` (extended in S1-08) — `@register_probe(runs_last=True)`.
  - `src/codegenie/indices/freshness.py` (from S1-02) — sum type + Pydantic shapes; **do not redefine**.
  - `src/codegenie/indices/registry.py` (from S1-02) — `@register_index_freshness_check` decorator; loop **this** registry from B2's `run()`.
  - `src/codegenie/exec.py` (extended in S1-08) — `run_allowlisted(["git", "rev-parse", "HEAD"], ...)`. Note: B2 uses `run_allowlisted` directly, **not** `run_external_cli`, because `git` predates the Layer-B chokepoint and is governed by Phase 0/1 ADRs.

## Goal

Running `codegenie gather` against any analyzed repo produces an `index_health` slice in `repo-context.yaml` containing one nested `IndexFreshness` value per registered index source. Every value is either `Fresh(indexed_at=...)` or `Stale(reason=<one of CommitsBehind|DigestMismatch|CoverageGap|IndexerError>)`. The probe **never raises** — every failure surface (git not a workdir, sibling slice missing, registry empty) becomes a typed `Stale(IndexerError(...))`. `cache_strategy="none"` is enforced at runtime AND by per-module pre-commit hook. `runs_last=True` is observable: B2's start timestamp is strictly later than every sibling probe's end timestamp in the structured-log stream.

## Acceptance criteria

- [ ] **AC-1 — Probe contract attributes.** `src/codegenie/probes/layer_b/index_health.py` defines `class IndexHealthProbe(Probe)` with class attributes matching the frozen `Probe` ABC (`list[str]` annotations, **not** tuples): `name="index_health"`, `version="0.1.0"`, `layer="B"`, `tier="base"`, `applies_to_languages=["*"]`, `applies_to_tasks=["*"]`, `requires=[]` (B2 reads sibling OUTPUTS via the coordinator-provided slice map, NOT via topological ordering — [phase-arch-design.md §"Component design" #1 line 453–455](../phase-arch-design.md)), `timeout_seconds=10`, `cache_strategy: Literal["none"] = "none"`, `declared_inputs=[".codegenie/context/raw/*.json", ".git/HEAD", "<scip-index-output>", "<image-digest-token>"]`. The decorator is `@register_probe(runs_last=True)` (heaviness defaults to `"light"`).

- [ ] **AC-2 — `cache_strategy="none"` is load-bearing AND mechanically enforced.** The literal type annotation `cache_strategy: Literal["none"] = "none"` is present. A per-module `forbidden-patterns` pre-commit hook entry (added to `.pre-commit-config.yaml` under the existing Phase 0 hook stanza) fails CI on any occurrence of `os.path.getmtime`, `Path.stat().st_mtime`, `os.stat(.*).st_mtime`, or `lstat(.*).st_mtime` under `src/codegenie/probes/layer_b/index_health.py` — mtime is not a freshness signal ([phase-arch-design.md §"Harness engineering"](../phase-arch-design.md)). A unit test programmatically grep-checks the hook config exists so a future contributor removing the hook fails the test.

- [ ] **AC-3 — `runs_last=True` registry annotation is respected by the coordinator.** Synthetic registry test (`tests/unit/probes/layer_b/test_index_health_probe.py::test_runs_last_dispatch_order`) registers a mock light probe, a mock heavy probe, and `IndexHealthProbe`; instruments probe-start timestamps; asserts `IndexHealthProbe`'s start timestamp is strictly greater than every other probe's end timestamp under `Semaphore(min(cpu_count(), 8))`. This is the only AC that depends on Step 1's coordinator sort-order edit — failure here means Step 1 regressed, not this story.

- [ ] **AC-4 — Registry-loop dispatcher (Gap 3 — Open/Closed at the file boundary).** `async def run(self, ctx) -> ProbeOutput` reads `git rev-parse HEAD` exactly once via `exec.run_allowlisted(["git", "rev-parse", "HEAD"], cwd=ctx.snapshot.root, timeout_s=5)`, then loops `codegenie.indices.registry.iter_freshness_checks()` (the iterator landed in S1-02). For each `(index_name, check_fn)` pair, calls `check_fn(slice=ctx.sibling_slices.get(index_name, None), head=head_sha)` and collects the typed `IndexFreshness` result into a dict keyed by `index_name`. **The body of `run()` contains zero `if index_name == "..."` branches** — verified by a code-shape unit test (`test_run_body_has_no_per_index_branches`) that AST-walks the `run` method and asserts no `Compare` node has a constant string equal to a known index name.

- [ ] **AC-5 — SCIP freshness check registers in this story.** `src/codegenie/probes/layer_b/index_health.py` (or a colocated `_freshness_scip.py` — implementer choice; both must be imported by `probes/__init__.py`) ships **one** `@register_index_freshness_check(IndexName("scip"))` function with signature `def scip_freshness(slice: dict[str, JSONValue] | None, head: str) -> IndexFreshness`. The function: (a) slice is `None` → `Stale(IndexerError(message="upstream_scip_unavailable"))`; (b) `slice["last_indexed_commit"] == head` and `slice["files_indexed"] == slice["files_in_repo"]` and `slice["indexer_errors"] == 0` → `Fresh(indexed_at=datetime.fromisoformat(slice["last_indexed_at"]))`; (c) `slice["last_indexed_commit"] != head` → `Stale(CommitsBehind(n=<see AC-6>, last_indexed=slice["last_indexed_commit"]))`; (d) `files_indexed < files_in_repo` AND commit matches → `Stale(CoverageGap(files_indexed=…, files_in_repo=…))`; (e) `slice["indexer_errors"] > 0` AND commit matches AND coverage matches → `Stale(IndexerError(message=f"indexer_reported_{slice['indexer_errors']}_errors"))`. The five branches are tested independently in T-04 through T-08.

- [ ] **AC-6 — `CommitsBehind.n` derivation.** `n` is computed via `exec.run_allowlisted(["git", "rev-list", "--count", f"{last_indexed}..{head}"], cwd=ctx.snapshot.root, timeout_s=5)` and parsed as `int`. If the rev-list fails (e.g., `last_indexed` not in the repo's history — shallow clone, force-push, fixture-seeded commit), `n` falls back to `1` (the structural minimum — "at least one commit behind, exact count unknown") and a `warnings` entry `index_health.commits_behind_count_unknown` is added. **`n >= 1` is the load-bearing structural invariant** asserted in S4-02 — the test must survive `last_indexed` not being reachable from `head`.

- [ ] **AC-7 — `git rev-parse HEAD` failure path.** If `run_allowlisted(["git", "rev-parse", "HEAD"], ...)` raises `FileNotFoundError` (git not installed — impossible per Phase 0 tool-check, but defensively handled), `subprocess.CalledProcessError` (non-zero exit — e.g., the analyzed repo is not a git work tree), or `TimeoutExpired`, the probe emits `Stale(IndexerError(message="repo_not_a_git_workdir"))` for **every** registered index source AND short-circuits (does not invoke any registered check function). `confidence="low"` on the slice; `warnings` contains `index_health.head_unresolvable`.

- [ ] **AC-8 — `IndexFreshness` construction failures are typed, never raised.** Every call site that constructs a `Stale(reason=...)` value catches `pydantic.ValidationError` (defensive — e.g., a sibling slice with `last_indexed_commit=42` instead of a string would break `CommitsBehind.last_indexed: str`) and substitutes `Stale(IndexerError(message=f"freshness_construction_failed_{index_name}_{type(e).__name__}"))`. No `pydantic.ValidationError` reaches the coordinator. Unit-test T-09 forces this by registering a malformed-slice check function.

- [ ] **AC-9 — Per-source `confidence: "high" | "medium" | "low"` derivation.** Pattern-matches the typed `IndexFreshness` value:
  - `Fresh(...)` → `confidence="high"`
  - `Stale(reason=CoverageGap(...))` if `files_indexed / files_in_repo >= 0.90` → `confidence="medium"`, else `"low"`
  - `Stale(reason=DigestMismatch(...) | CommitsBehind(...))` → `confidence="medium"`
  - `Stale(reason=IndexerError(...))` → `confidence="low"`
  Exhaustive `match` with `assert_never` on the unreachable branch (mypy `--warn-unreachable` per-module enforces a build error if a new `StaleReason` variant is added without updating this match).

- [ ] **AC-10 — Slice shape per `localv2.md §5.2 B2`.** Output slice is `{<index_name>: {freshness: <IndexFreshness JSON>, confidence: "high"|"medium"|"low", last_indexed_at: <iso8601 | null>, current_commit: <sha>, ...}}`. The typed `IndexFreshness` value is included as `freshness` (nested object with `kind` discriminator); the flat `confidence` string is derived per AC-9 (backward compat with `localv2.md` slice shape). Both representations exist at the slice boundary; the renderer (S8-01) is the source of truth for the typed value.

- [ ] **AC-11 — Empty registry path.** If `codegenie.indices.registry.iter_freshness_checks()` returns an empty iterator (no Phase-2 source registered yet — would only happen on a misconfigured deployment), B2's slice is `{}` (empty dict, NOT `null`), `confidence` is not emitted at slice root, `warnings` contains `index_health.no_sources_registered`, and the probe returns success (not failure — empty is a valid state for an Open/Closed registry).

- [ ] **AC-12 — Sibling-missing path (defensive).** For each registered `(index_name, check_fn)`, if `ctx.sibling_slices.get(index_name)` is `None`, the check function (per AC-5 contract) emits `Stale(IndexerError(message=f"upstream_{index_name}_unavailable"))`. B2 does NOT branch on this case itself — it delegates to the check function, which is the right shape (each source knows its own absence semantics). Verified by registering a mock check function that asserts it received `slice=None`.

- [ ] **AC-13 — No imports from sibling probe modules.** `index_health.py` imports **only** from `codegenie.probes.base`, `codegenie.probes.registry`, `codegenie.indices.freshness`, `codegenie.indices.registry`, `codegenie.exec`, and stdlib. A unit test (`test_no_sibling_probe_imports`) AST-walks the module and asserts no import statement targets `codegenie.probes.layer_b.*` (other than itself) or `codegenie.probes.layer_a.*`/`layer_c.*`/`layer_d.*`/`layer_e.*`/`layer_g.*`. Coupling B2 to sibling probe internals would defeat the registry pattern.

- [ ] **AC-14 — Warning + error ID frozenset + import-time assertion.** All warning IDs (`index_health.head_unresolvable`, `index_health.no_sources_registered`, `index_health.commits_behind_count_unknown`) are declared in a module-level `_WARNING_IDS: frozenset[str]`. An import-time `assert` verifies every member matches the Phase 1 ADR-0007 regex `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. If any drifts, the module fails to import (loud-fail per Rule 12).

- [ ] **AC-15 — Mypy strict + warn-unreachable enforcement.** `mypy --strict src/codegenie/probes/layer_b/index_health.py` passes. `mypy --warn-unreachable` per-module on `codegenie.probes.layer_b.index_health` passes ([ADR-0006 §Consequences](../ADRs/0006-index-freshness-sum-type-location.md)). A deliberate removal of one `case Stale(reason=IndexerError(...)):` arm from the AC-9 match block fails the build with `Statement is unreachable` — verified by `tests/unit/probes/layer_b/test_index_health_mypy_warn_unreachable.py` which uses `subprocess.run(["mypy", "--warn-unreachable", ...])` on a temp copy with the arm removed.

- [ ] **AC-16 — Registry membership.** `src/codegenie/probes/__init__.py` imports `IndexHealthProbe` via an explicit additive line (`from codegenie.probes.layer_b import index_health  # noqa: F401`); `default_registry.all_probes()` includes it with `runs_last=True` set on the registry entry. `for_task("*", frozenset({"javascript"}))` returns a tuple containing the probe (applies to all languages).

- [ ] **AC-17 — Tooling green.** `ruff check src/codegenie/probes/layer_b/index_health.py`, `ruff format --check`, `mypy --strict`, `pytest tests/unit/probes/layer_b/test_index_health_probe.py` all pass. Per-module coverage line/branch ≥ 90/80.

## Implementation outline

The shape is **dispatch-table-on-registry** (Rule 2 / Rule 7 — surface registry-pattern conflicts, don't blend with topological dispatch). The `run` body is ≤ 40 LOC; all branching lives inside the registered check functions, not in B2 itself.

1. **Create `src/codegenie/probes/layer_b/index_health.py`.** Subclass `Probe` from `probes/base.py`. Import `from codegenie import exec as _exec` (consistent with S2-02 / Rule 11 — match codebase convention). Declare class attributes per AC-1.

2. **Module-level constants.**

    ```python
    _WARNING_IDS: Final[frozenset[str]] = frozenset({
        "index_health.head_unresolvable",
        "index_health.no_sources_registered",
        "index_health.commits_behind_count_unknown",
    })

    _ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    for _id in _WARNING_IDS:
        assert _ID_PATTERN.match(_id), f"ADR-0007 violation: {_id!r}"
    ```

3. **`@register_index_freshness_check(IndexName("scip"))` function** (per AC-5). This is colocated for now; S5-05 and S6-08 will register their own checks in their owning probe modules.

4. **`async def run(self, ctx: ProbeContext) -> ProbeOutput`** — the dispatcher loop.

    ```python
    # Pseudocode shape, ~35 LOC:
    try:
        head = _exec.run_allowlisted(["git", "rev-parse", "HEAD"], cwd=ctx.snapshot.root, timeout_s=5).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError, TimeoutExpired):
        return _emit_head_unresolvable_for_all_registered_sources()

    results: dict[str, dict[str, JSONValue]] = {}
    for index_name, check_fn in iter_freshness_checks():
        sibling = ctx.sibling_slices.get(index_name)
        try:
            freshness = check_fn(slice=sibling, head=head)
        except pydantic.ValidationError as e:
            freshness = Stale(reason=IndexerError(message=f"freshness_construction_failed_{index_name}_{type(e).__name__}"))
        results[index_name] = {
            "freshness": freshness.model_dump(mode="json"),
            "confidence": _derive_confidence(freshness),  # AC-9 exhaustive match
            "current_commit": head,
            "last_indexed_at": _last_indexed_at(freshness),  # None when Stale
        }

    warnings = [] if results else ["index_health.no_sources_registered"]
    return ProbeOutput(schema_slice={"index_health": results}, warnings=warnings, ...)
    ```

5. **`_derive_confidence` (pure helper).** Exhaustive `match` with `assert_never` per AC-9. Lives at module level (functional core — testable in isolation).

6. **`_emit_head_unresolvable_for_all_registered_sources` (pure helper).** Iterates the registry; emits `Stale(IndexerError(message="repo_not_a_git_workdir"))` for each; sets `confidence="low"`; returns a `ProbeOutput` with `warnings=["index_health.head_unresolvable"]`.

7. **Logging.** Emit `EVENT_PROBE_START` / `EVENT_PROBE_SUCCESS` / `EVENT_PROBE_FAILURE` (Phase 0 constants). One INFO log line per registered source with structured fields `index_name`, `kind` (= "fresh" or "stale"), `reason_kind` (when stale). No log line includes the sha — provenance is in the slice.

8. **Register the probe** via `src/codegenie/probes/__init__.py` additive import.

## TDD plan — red / green / refactor

### Test helpers preamble (define inline at the top of the test file)

```python
# tests/unit/probes/layer_b/test_index_health_probe.py
from __future__ import annotations
import asyncio, types, datetime as dt
from pathlib import Path
import pytest
from codegenie.indices.freshness import Fresh, Stale, CommitsBehind, CoverageGap, DigestMismatch, IndexerError
from codegenie.indices.registry import register_index_freshness_check, iter_freshness_checks, _clear_for_tests  # test-only helper added in S1-02
from codegenie.probes.layer_b.index_health import IndexHealthProbe

@pytest.fixture
def clean_freshness_registry():
    _clear_for_tests()
    yield
    _clear_for_tests()
```

### RED — write failing tests first (in order)

- **T-01** `test_probe_contract_attributes`: instantiate `IndexHealthProbe`; assert every attribute per AC-1; assert `cache_strategy == "none"` and `mypy --strict` of the module exits 0 (subprocess check).
- **T-02** `test_runs_last_registry_annotation_present`: `default_registry.entry_for("index_health").runs_last is True`.
- **T-03** `test_runs_last_dispatch_order` (AC-3): synthetic registry of light + medium + heavy + B2; coordinator under `Semaphore(2)` (forced via `CODEGENIE_FORCE_CPU_COUNT=2`); assert `B2.start_ts > max(other.end_ts for other in others)`.
- **T-04** `test_scip_freshness_fresh_path` (AC-5b): sibling slice with `last_indexed_commit == head`, full coverage, zero errors → `Fresh(indexed_at=<parsed>)`.
- **T-05** `test_scip_freshness_commits_behind_path` (AC-5c, AC-6): sibling slice with `last_indexed_commit != head`; mock `git rev-list --count` returns `"3\n"` → `Stale(CommitsBehind(n=3, last_indexed="abc..."))`.
- **T-06** `test_scip_freshness_coverage_gap_path` (AC-5d): commit matches but `files_indexed < files_in_repo` → `Stale(CoverageGap(files_indexed=240, files_in_repo=247))`.
- **T-07** `test_scip_freshness_indexer_error_path` (AC-5e): commit matches, coverage matches, `indexer_errors > 0` → `Stale(IndexerError(message="indexer_reported_2_errors"))`.
- **T-08** `test_scip_freshness_upstream_unavailable_path` (AC-5a, AC-12): sibling slice is `None` → `Stale(IndexerError(message="upstream_scip_unavailable"))`.
- **T-09** `test_freshness_construction_failure_is_typed` (AC-8): register a check function that raises `pydantic.ValidationError`; B2 emits `Stale(IndexerError(message="freshness_construction_failed_..."))`; **no exception escapes `run()`**.
- **T-10** `test_head_unresolvable_path` (AC-7): stub `run_allowlisted` to raise `subprocess.CalledProcessError`; assert every registered source emits `Stale(IndexerError(message="repo_not_a_git_workdir"))`; `warnings` contains `"index_health.head_unresolvable"`; `confidence="low"` on every slice entry.
- **T-11** `test_commits_behind_count_unknown_fallback` (AC-6): stub `git rev-list --count` to fail; `n == 1`; `warnings` contains `"index_health.commits_behind_count_unknown"`.
- **T-12** `test_no_sources_registered_path` (AC-11): clear registry; B2's slice is `{}`; `warnings == ["index_health.no_sources_registered"]`; probe returns success.
- **T-13** `test_confidence_derivation_exhaustive` (AC-9): parametrize over every variant of `IndexFreshness`; assert `_derive_confidence` returns the expected `"high"|"medium"|"low"`; assert `_derive_confidence(<malformed sentinel>)` raises (the `assert_never` arm).
- **T-14** `test_no_sibling_probe_imports` (AC-13): AST-walk `index_health.py`; assert no `import` or `from` targets `codegenie.probes.layer_a.*`/`layer_b.<not-self>`/`layer_c.*` etc.
- **T-15** `test_run_body_has_no_per_index_branches` (AC-4): AST-walk `IndexHealthProbe.run`; collect every `Compare` node's right-hand constant; assert none matches a known index name (`scip`, `runtime_trace`, `sbom`, `semgrep`).
- **T-16** `test_cache_strategy_none_hook_present` (AC-2): read `.pre-commit-config.yaml`; assert there is a hook entry that scopes `forbidden-patterns` to `src/codegenie/probes/layer_b/index_health.py` and includes the four mtime patterns.
- **T-17** `test_warning_ids_match_adr_0007` (AC-14): every member of `_WARNING_IDS` matches the regex (this is the import-time `assert` reverified at test time so removal of the import-time `assert` is caught).
- **T-18** `test_registry_membership_and_for_task_filter` (AC-16): `IndexHealthProbe` in `default_registry.all_probes()`; `for_task("*", frozenset({"javascript"}))` includes it; `for_task("*", frozenset({"go"}))` includes it too (`applies_to_languages=["*"]`).
- **T-19** `test_mypy_warn_unreachable_fires_on_removed_arm` (AC-15): copy `index_health.py` to a tempdir; remove one `case Stale(reason=IndexerError(...))` arm from `_derive_confidence`; run `mypy --warn-unreachable` on the copy; assert exit code != 0 AND stderr contains "unreachable".
- **T-20** `test_slice_shape_localv2_compliance` (AC-10): assert slice keys per source are exactly `{"freshness", "confidence", "current_commit", "last_indexed_at"}`; `freshness` is a dict with `kind` discriminator.

All 20 tests must fail before any production code is written.

### GREEN — make tests pass with minimum code

Implement the module per the outline section. Keep `run()` ≤ 40 LOC. Resist the temptation to inline freshness logic — every per-index branch must live inside a registered check function.

### REFACTOR

- Extract `_derive_confidence` and `_last_indexed_at` to module-level pure helpers (callable as `_derive_confidence(freshness) -> str` from tests without touching the probe).
- Consider colocating the `scip` freshness check in `_freshness_scip.py` if the file exceeds 200 LOC (style preference: one freshness check per file when there are > 1; inline when there is exactly 1). Phase 5/6 will add more — the second arrival is the time to split.
- Run `mypy --strict --warn-unreachable` per-module to confirm AC-15.

## Files to touch

**Create:**
- `src/codegenie/probes/layer_b/__init__.py` (empty — package marker)
- `src/codegenie/probes/layer_b/index_health.py`
- `tests/unit/probes/layer_b/__init__.py`
- `tests/unit/probes/layer_b/test_index_health_probe.py`
- `tests/unit/probes/layer_b/test_index_health_mypy_warn_unreachable.py`

**Edit (additive):**
- `src/codegenie/probes/__init__.py` — one new import line.
- `.pre-commit-config.yaml` — new hook entry scoping `forbidden-patterns` to `index_health.py` with the four mtime patterns (AC-2).
- `pyproject.toml` — `[[tool.mypy.overrides]]` block for `codegenie.probes.layer_b.index_health` with `warn_unreachable = true` (likely already present from S1-08; verify and extend).

## Out of scope

- **The CI-gating stale-SCIP adversarial.** S4-02 owns `tests/adv/phase02/test_stale_scip_fixture.py`. This story ships the probe; that story wires it to the fixture and the `adv-phase02` CI job.
- **The full `stale-scip` fixture materialization.** S4-02 stubs it; S7-02 fully materializes it with `regenerate.sh` and the README policy.
- **`runtime_trace` / `sbom` / `semgrep` / `gitleaks` / `conventions` freshness checks.** S5-05 (runtime_trace), S6-08 (semgrep + gitleaks + conventions) register their checks in their owning probe stories. B2 sees them appear via the registry; this story registers only `scip`.
- **The renderer.** S8-01 ships `src/codegenie/report/confidence_section.py` which pattern-matches every `IndexFreshness` value with `assert_never`. This story produces the typed value; the renderer consumes it.
- **Sub-schema for `index_health`.** S4-07 lands all seven Layer-B sub-schemas (`additionalProperties: false` at root + sub-schema rejection test). This story emits the slice; that story validates it.
- **The `image_digest_resolver` ProbeContext field.** Landed in S1-08 (Step 1) per [ADR-0004](../ADRs/0004-image-digest-as-declared-input-token.md). B2's `declared_inputs` lists `<image-digest-token>` but the resolver is bound at coordinator setup.

## Notes for the implementer

- **Import discipline.** `from codegenie import exec as _exec` (consistent with S2-02). `from codegenie.indices.freshness import Fresh, Stale, CommitsBehind, CoverageGap, IndexerError`. `from codegenie.indices.registry import iter_freshness_checks, register_index_freshness_check`. Do NOT import from `codegenie.probes.layer_a.*` or `layer_b.*` (sibling) — AC-13 enforces.
- **The `cache_strategy="none"` discipline.** A future contributor will propose "let's cache B2 for performance." The answer is in three places: this story (Notes), the per-module pre-commit hook (AC-2), and [phase-arch-design.md §"Harness engineering"](../phase-arch-design.md) (the "caching `Date.now()`" framing). Memo all three.
- **`runs_last=True` is one probe per gather.** ADR-0003 documents this as a constraint of the registry annotation. Phase 2 has exactly one `runs_last=True` probe (B2). Phase 3+ adding a second is an ADR amendment to ADR-0003.
- **The structural assertion B2 enables.** S4-02's adversarial test asserts `isinstance(freshness, Stale)` AND `isinstance(freshness.reason, CommitsBehind)` AND `freshness.reason.n >= 1` AND `freshness.reason.last_indexed != current_HEAD`. Both inequalities are load-bearing (implementation risk #3 from the manifest) — `n >= 1` alone would pass if `n` were unconditionally `1` due to a fallback (AC-6 — that's exactly the fallback path); the `last_indexed != current_HEAD` check catches the case where the fallback fires AND the structural fact (different commits) still holds. Do not relax AC-6's fallback to "always `n=1`" — the rev-list path is the source of truth when it works.
- **Empty registry is valid.** AC-11 codifies this. The Open/Closed seam means "no sources registered" is a temporary deployment state, not an error. The warning `index_health.no_sources_registered` exists so a CI-state regression (e.g., `S5-05` accidentally not registered) is loud.
- **Rule 9 (tests verify intent).** Every test in the TDD plan encodes a *why*: T-15 (no per-index branches) encodes the Open/Closed discipline; T-09 (typed construction failures) encodes the "never raise" failure-isolation discipline; T-19 (mypy --warn-unreachable fires) encodes the exhaustive-match discipline. None of them check "the code returns a value" without checking what *kind* of value and why.
- **No `pytest.skip` on missing `git`.** Phase 0 tool-check refuses to start `codegenie gather` without `git`; the unit tests stub `run_allowlisted` and never invoke real git. The integration suite is downstream of this story (S7-05's portfolio sweep) and gates on real-tool presence with loud warning.
