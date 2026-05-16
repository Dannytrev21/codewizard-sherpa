# Story S4-01 — `IndexHealthProbe` (B2) + registry-dispatched freshness loop

**Step:** Step 4 — Ship `IndexHealthProbe` (B2) + Layer B structural probes
**Status:** Done · 2026-05-16 (see `_attempts/S4-01.md` for the GREEN log).
  Evidence:
  - Probe: `src/codegenie/probes/layer_b/index_health.py` — `IndexHealthProbe` (`runs_last=True`, `cache_strategy="none"`), `scip_freshness` (six AC-5 branches), four pure helpers, three imperative-shell helpers.
  - Registry additive surface: `FreshnessRegistry.dispatch_one` at `src/codegenie/indices/registry.py:166-183`.
  - Forbidden-patterns: four mtime rules scoped to `index_health.py` at `scripts/check_forbidden_patterns.py:159-186`.
  - Tests: 49 PASS in `tests/unit/probes/layer_b/test_index_health_probe.py` + `…_mypy_warn_unreachable.py`. Full suite: 2143 pass, 0 fail. Per-module coverage `index_health.py`: 97 / 80 (line / branch).
  - Pre-commit + mypy --strict + lint-imports all green.
**Effort:** L
**Depends on:** S1-02 (`@register_index_freshness_check` registry + `IndexFreshness` sum type on disk), S1-08 (`@register_probe(heaviness=, runs_last=)` decorator kwargs + coordinator sort-order edit), S3-03 (writer-chokepoint `SecretRedactor` lands before any probe persists output — B2 reads sibling slices that have already been through redaction)

## Validation notes (2026-05-16)

Eight BLOCK-severity inconsistencies with master closed; six harden findings closed; four design-pattern notes added. Full audit: `_validation/S4-01-index-health-probe.md`. Highlights:

1. **`Probe.run` is two-argument** `(repo: RepoSnapshot, ctx: ProbeContext)`. The frozen ABC (Phase 0 ADR-0007) has no `sibling_slices` field on `ProbeContext`; only `parsed_manifest`, `input_snapshot`, `image_digest_resolver` are admitted.
2. **No `ctx.sibling_slices`.** B2 reads sibling slices from `<repo>/.codegenie/context/raw/*.json` via a pluggable `read_raw_slices` pure helper that uses `codegenie.output.paths.raw_dir(repo.root)`. Cross-story handoff: S4-03 (SCIP), S5-05 (runtime_trace), S6-08 (semgrep/gitleaks/conventions) MUST each write a `<index_name>.json` raw artifact under that directory during their `run()`.
3. **`iter_freshness_checks` / `_clear_for_tests` do not exist.** The actual API is `default_freshness_registry.dispatch_all(slices, head)` (loop is inside) + `default_freshness_registry.registered_names()` + `default_freshness_registry.unregister_for_tests(index_name)` (per-name).
4. **`FreshnessCheck` is positional** `(dict[str, object], str) -> IndexFreshness`. `dispatch_all` passes `slices.get(name, {})` — an **empty dict**, never `None`. "Upstream unavailable" is detected by `not slice` or by missing required keys.
5. **`run_allowlisted` exception taxonomy:** raises `ToolMissingError` (binary missing), `ProbeTimeoutError` (timeout), `DisallowedSubprocessError`, `FileNotFoundError` (cwd missing). It does **NOT** raise `subprocess.CalledProcessError` — non-zero exits return a `ProcessResult` with `returncode != 0`.
6. **`ProcessResult.stdout: bytes`** (not `str`); field name is `returncode` (not `return_code`). The HEAD sha is `result.stdout.decode("utf-8").strip()`.
7. **`Probe.version` is a Phase 0/1 convention, not an ABC field** (per `src/codegenie/probes/registry.py:30-36`). AC-1's `version="0.1.0"` is correct *as a convention*; the contract-freeze test (`tests/unit/test_probe_contract.py`) does NOT enforce it.
8. **`dispatch_all` IS the no-branches enforcement.** AC-4's AST-walk test remains as defense-in-depth, but the primary discipline is that `run()` calls `dispatch_all(...)` exactly once.

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

Running `codegenie gather` against any analyzed repo produces an `index_health` slice in `repo-context.yaml` containing one nested `IndexFreshness` value per registered index source. Every value is either `Fresh(indexed_at=...)` or `Stale(reason=<one of CommitsBehind|DigestMismatch|CoverageGap|IndexerError>)`. The probe **never raises** — every failure surface (git not a workdir, sibling raw artifact missing, registry empty) becomes a typed `Stale(IndexerError(...))`. `cache_strategy="none"` is enforced at runtime AND by per-module pre-commit hook. `runs_last=True` is observable: B2's start timestamp is strictly later than every sibling probe's end timestamp in the structured-log stream. B2's `run(repo, ctx)` reads sibling slice data from `<repo>/.codegenie/context/raw/*.json` (via `codegenie.output.paths.raw_dir(repo.root)` and a pluggable pure helper `read_raw_slices`); the `ProbeContext` ABC stays frozen — `sibling_slices` is NOT a contract addition.

## Acceptance criteria

- [x] **AC-1 — Probe contract attributes.** `src/codegenie/probes/layer_b/index_health.py` defines `class IndexHealthProbe(Probe)` with class attributes matching the frozen `Probe` ABC (`list[str]` annotations, **not** tuples): `name="index_health"`, `version="0.1.0"` (Phase 0/1 *convention* per `src/codegenie/probes/registry.py:30-36` — **not** an ABC field; the contract-freeze test `tests/unit/test_probe_contract.py` does not enforce it, but `CacheStore.key_for` reads it via the `_ProbeLike` Protocol), `layer="B"`, `tier="base"`, `applies_to_languages=["*"]`, `applies_to_tasks=["*"]`, `requires: list[str] = []` (B2 reads sibling raw artifacts from disk, NOT via topological ordering — see Goal + `phase-arch-design.md §"Component design" #1 line 453–455`), `timeout_seconds=10`, `cache_strategy: Literal["none"] = "none"`, `declared_inputs=[".codegenie/context/raw/*.json", ".git/HEAD", "<scip-index-output>", "<image-digest-token>"]`. The async-run signature is `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` (two-arg per `src/codegenie/probes/base.py:94`). The decorator is `@register_probe(runs_last=True)` (heaviness defaults to `"light"`).

- [x] **AC-2 — `cache_strategy="none"` is load-bearing AND mechanically enforced.** The literal type annotation `cache_strategy: Literal["none"] = "none"` is present. A per-module `forbidden-patterns` pre-commit hook entry (added to `.pre-commit-config.yaml` under the existing Phase 0 hook stanza) fails CI on any occurrence of `os.path.getmtime`, `Path.stat().st_mtime`, `os.stat(.*).st_mtime`, or `lstat(.*).st_mtime` under `src/codegenie/probes/layer_b/index_health.py` — mtime is not a freshness signal ([phase-arch-design.md §"Harness engineering"](../phase-arch-design.md)). A unit test programmatically grep-checks the hook config exists so a future contributor removing the hook fails the test.

- [x] **AC-3 — `runs_last=True` registry annotation is respected by the coordinator.** Two checks:
  - **AC-3a (registry-side):** `default_registry.sorted_for_dispatch()` returns a tuple whose last entry is the `IndexHealthProbe` entry (`ProbeRegEntry.runs_last is True`). Asserted in `tests/unit/probes/layer_b/test_index_health_probe.py::test_sorted_for_dispatch_places_b2_last`.
  - **AC-3b (coordinator-side, end-to-end):** Real-coordinator harness — `await coordinator.gather(snapshot, task, [mock_light, mock_heavy, IndexHealthProbe()], config, cache, sanitizer, runs_last_names=frozenset({"index_health"}))`; instrument probe-start timestamps via a structlog capture; assert `IndexHealthProbe`'s start timestamp is strictly greater than every other probe's end timestamp. This is the only AC that depends on Step 1's coordinator hoist edit — failure here means S1-08 regressed, not this story. The CLI seam `_seam_coordinator_gather` (`src/codegenie/cli.py:281`) is the bridge that derives `runs_last_names` from `default_registry.sorted_for_dispatch()`; the test reuses the seam's shape, not a synthetic semaphore.

- [x] **AC-4 — Registry-loop dispatcher (Gap 3 — Open/Closed at the file boundary).** `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`:
  1. reads `git rev-parse HEAD` exactly once via `await _exec.run_allowlisted(["git", "rev-parse", "HEAD"], cwd=repo.root, timeout_s=5)`; the SHA is `result.stdout.decode("utf-8").strip()` (typed `head: str`);
  2. builds the per-source slice dict via a **pluggable pure helper** `read_raw_slices(raw_dir: Path) -> dict[IndexName, dict[str, object]]` at module level — reads every `<index_name>.json` under `codegenie.output.paths.raw_dir(repo.root)`, parses with `json.loads`, returns `{}` for any file that fails to parse (each check function is responsible for its own malformed-slice handling per AC-5);
  3. calls `default_freshness_registry.dispatch_all(slices, head)` **exactly once** — the registry's `dispatch_all` is itself the no-branches enforcement; the body of `run()` contains zero `if index_name == "..."` branches.

  Verified by **two complementary tests**: (a) `test_run_body_has_no_per_index_branches` AST-walks the `run` method and asserts no `Compare` node has a constant string equal to a known index name (`scip`, `runtime_trace`, `sbom`, `semgrep`); (b) `test_run_invokes_dispatch_all_exactly_once` AST-walks `run` and asserts there is exactly one `Await` node whose target is an attribute access ending in `.dispatch_all` (positive structural invariant).

- [x] **AC-5 — SCIP freshness check registers in this story.** `src/codegenie/probes/layer_b/index_health.py` (or a colocated `_freshness_scip.py` — implementer choice; both must be imported by `probes/__init__.py`) ships **one** `@register_index_freshness_check(IndexName("scip"))` function with signature **matching the `FreshnessCheck` type alias at `src/codegenie/indices/registry.py:56`**: `def scip_freshness(slice: dict[str, object], head: str) -> IndexFreshness` — **positional**, slice is `dict[str, object]` (never `None` — `FreshnessRegistry.dispatch_all` passes `{}` as the empty-dict sentinel for absent siblings). The function:
  - **(a) `not slice` (empty dict, sentinel for absent sibling JSON file)** → `Stale(IndexerError(message="upstream_scip_unavailable"))`.
  - **(b) all required keys present AND `slice["last_indexed_commit"] == head` AND `slice["files_indexed"] == slice["files_in_repo"]` AND `slice["indexer_errors"] == 0`** → `Fresh(indexed_at=datetime.fromisoformat(slice["last_indexed_at"]))`.
  - **(c) `slice["last_indexed_commit"] != head`** → `Stale(CommitsBehind(n=<see AC-6>, last_indexed=slice["last_indexed_commit"]))`.
  - **(d) `slice["files_indexed"] < slice["files_in_repo"]` AND commit matches** → `Stale(CoverageGap(files_indexed=…, files_in_repo=…))`.
  - **(e) `slice["indexer_errors"] > 0` AND commit matches AND coverage matches** → `Stale(IndexerError(message=f"indexer_reported_{slice['indexer_errors']}_errors"))`.
  - **(f) required key missing OR key type mismatch (e.g., `last_indexed_commit` is an `int`)** → `Stale(IndexerError(message="scip_slice_malformed"))`. This branch is distinct from (a): "upstream skipped entirely" vs. "upstream wrote a malformed slice."

  The six branches are tested independently in T-04 through T-08 + T-09. The function MUST NOT raise — every code path returns an `IndexFreshness`.

- [x] **AC-6 — `CommitsBehind.n` derivation.** `n` is computed via `await _exec.run_allowlisted(["git", "rev-list", "--count", f"{last_indexed}..{head}"], cwd=repo.root, timeout_s=5)`; the raw stdout is `result.stdout.decode("utf-8").strip()` and parsed via `int(...)`. If the rev-list fails (e.g., `last_indexed` not in the repo's history — shallow clone, force-push, fixture-seeded commit) — detected by **either** `ProbeTimeoutError`/`ToolMissingError`/`DisallowedSubprocessError`/`FileNotFoundError` (cwd missing) raised, **or** `result.returncode != 0`, **or** `ValueError` from `int(...)` on non-numeric stdout — `n` falls back to `1` (the structural minimum — "at least one commit behind, exact count unknown") and a `warnings` entry `index_health.commits_behind_count_unknown` is added. **`n >= 1` is the load-bearing structural invariant** asserted in S4-02 — the test must survive `last_indexed` not being reachable from `head`. Note: `run_allowlisted` does **not** raise `subprocess.CalledProcessError` on non-zero exit (`src/codegenie/exec.py:216-272`); the caller checks `result.returncode` directly.

- [x] **AC-7 — `git rev-parse HEAD` failure path.** If `await _exec.run_allowlisted(["git", "rev-parse", "HEAD"], ...)`:
  - raises `ToolMissingError` (git not on `PATH` — impossible per Phase 0 tool-check, but defensively handled),
  - raises `DisallowedSubprocessError` (defensive — should never fire for `git`),
  - raises `FileNotFoundError` or `NotADirectoryError` (cwd missing/not a dir),
  - raises `ProbeTimeoutError`,
  - **OR** returns a `ProcessResult` with `returncode != 0` (e.g., the analyzed repo is not a git work tree — `git rev-parse HEAD` exits 128),

  the probe emits `Stale(IndexerError(message="repo_not_a_git_workdir"))` for **every** registered index source AND short-circuits (does not invoke `dispatch_all`). Per-source `confidence="low"`; envelope-level `ProbeOutput.confidence="low"`; `warnings` contains `index_health.head_unresolvable`. **No `subprocess.CalledProcessError`/`TimeoutExpired` exception types** — `run_allowlisted`'s taxonomy is `ToolMissingError`/`ProbeTimeoutError`/`DisallowedSubprocessError`/`FileNotFoundError`/`NotADirectoryError` per `src/codegenie/exec.py:242-249`.

- [x] **AC-8 — `IndexFreshness` construction failures and check-function exceptions are typed, never raised.** B2 is the exception-isolation site for the registry's check functions, per `src/codegenie/indices/registry.py:157-162` ("an exception escaping a check is a bug, and the coordinator at S4-01 is the right place to catch"). Mechanism: B2 calls `default_freshness_registry.dispatch_all(slices, head)` inside a `try`; on `pydantic.ValidationError` **or** any other `Exception` from any check, B2 falls back to a per-name loop iterating `default_freshness_registry.registered_names()` and re-invoking checks one at a time through a tiny **public** `FreshnessRegistry.dispatch_one(name, slices, head) -> IndexFreshness` method that this story adds to `indices/registry.py` (additive, with a docstring documenting the per-name isolation use case). Each failed check is replaced by `Stale(IndexerError(message=f"freshness_construction_failed_{name}_{type(e).__name__}"))`; successful checks keep their typed value. **No exception reaches the coordinator.** Unit-test T-09 forces this by registering a check that raises `pydantic.ValidationError` alongside the SCIP check, then asserts both names appear in the result (the SCIP check succeeded; the malformed check was wrapped). The `dispatch_one` addition is the only edit to S1-02's `indices/registry.py` this story makes; it is additive (no caller of `dispatch_all` is affected).

- [x] **AC-9 — Per-source `confidence: "high" | "medium" | "low"` derivation + envelope-level demote-min.** A pure module-level helper `_derive_confidence(freshness: IndexFreshness) -> Literal["high","medium","low"]` pattern-matches the typed value:
  - `Fresh(...)` → `"high"`
  - `Stale(reason=CoverageGap(files_indexed=i, files_in_repo=t))` if `i / t >= 0.90` (and `t > 0`) → `"medium"`, else `"low"` (the `t == 0` divide-by-zero degenerate path returns `"low"`)
  - `Stale(reason=DigestMismatch(...) | CommitsBehind(...))` → `"medium"`
  - `Stale(reason=IndexerError(...))` → `"low"`

  Exhaustive `match` with `assert_never` on the unreachable branch (mypy `--warn-unreachable` per-module enforces a build error if a new `StaleReason` variant is added without updating this match — AC-15 verifies the build error).

  The **envelope-level** `ProbeOutput.confidence` is the demote-min over the per-source confidences with the ordering `"low" < "medium" < "high"` (i.e., `ProbeOutput.confidence = min(per_source_confidences)`). Empty-registry path: envelope `confidence="high"` (no degraded source observed).

- [x] **AC-10 — Slice shape per `localv2.md §5.2 B2` + outer-key invariant.** Output slice is `{"index_health": {<index_name>: {"freshness": <IndexFreshness JSON via model_dump(mode="json")>, "confidence": "high"|"medium"|"low", "last_indexed_at": <iso8601 str | None>, "current_commit": <sha str>}, ...}}`. The typed `IndexFreshness` value is included as `"freshness"` (nested object with `"kind"` discriminator); the flat `"confidence"` string is derived per AC-9 (backward compat with `localv2.md` slice shape). `"last_indexed_at"` is the ISO8601 string from `Fresh.indexed_at.isoformat()` only when the variant is `Fresh`; on every `Stale(...)` variant it is `None` (the indexed_at is no longer authoritative).

  **Outer-key invariant** (mutation-resistance): `set(slice["index_health"].keys()) == set(default_freshness_registry.registered_names())` — every registered name appears exactly once; no silent re-keying (e.g., `.lower()`) is permitted. Verified by T-20.

  Both representations exist at the slice boundary; the renderer (S8-01) is the source of truth for the typed value.

- [x] **AC-11 — Empty registry path.** If `default_freshness_registry.registered_names()` returns `frozenset()` (no Phase-2 source registered yet — would only happen on a misconfigured deployment), B2's slice is `{}` (empty dict, NOT `null`), `warnings` contains `index_health.no_sources_registered`, envelope `ProbeOutput.confidence="high"` (no degraded source observed; the demote-min of an empty list yields the "high" default), and the probe returns success (not failure — empty is a valid state for an Open/Closed registry).

- [x] **AC-12 — Sibling-missing path (defensive).** For each registered `(index_name, check_fn)`, if the per-source raw artifact `<repo>/.codegenie/context/raw/<index_name>.json` is absent or unparseable, `read_raw_slices` omits the key from the returned dict; `FreshnessRegistry.dispatch_all` then passes `{}` (empty dict — the registry's sentinel, NOT `None`) to the check function per `src/codegenie/indices/registry.py:163`. The check function (per AC-5(a) contract) emits `Stale(IndexerError(message=f"upstream_{index_name}_unavailable"))` on the empty-dict input. B2 does NOT branch on this case itself — it delegates to the check function, which is the right shape (each source knows its own absence semantics). Verified by registering a mock check function that asserts it received an empty dict `{}` (positive `isinstance(slice, dict) and not slice`) and explicitly NOT `None`.

- [x] **AC-13 — No imports from sibling probe modules.** `index_health.py` imports **only** from `codegenie.probes.base`, `codegenie.probes.registry`, `codegenie.indices.freshness`, `codegenie.indices.registry`, `codegenie.exec` (aliased as `_exec` per Rule 11 / S2-02), `codegenie.types.identifiers` (for `IndexName`), `codegenie.output.paths` (for `raw_dir`), `codegenie.errors` (for the typed-exception catch list in AC-7), and stdlib (`json`, `re`, `datetime`, `logging`, `typing`, etc.). A unit test (`test_no_sibling_probe_imports`) AST-walks the module and asserts no import statement targets `codegenie.probes.layer_b.*` (other than itself) or `codegenie.probes.layer_a.*`/`layer_c.*`/`layer_d.*`/`layer_e.*`/`layer_g.*`. Coupling B2 to sibling probe internals would defeat the registry pattern.

- [x] **AC-14 — Warning + error ID frozenset + import-time assertion.** All warning IDs (`index_health.head_unresolvable`, `index_health.no_sources_registered`, `index_health.commits_behind_count_unknown`) are declared in a module-level `_WARNING_IDS: frozenset[str]`. An import-time `assert` verifies every member matches the Phase 1 ADR-0007 regex `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. If any drifts, the module fails to import (loud-fail per Rule 12).

- [x] **AC-15 — Mypy strict + warn-unreachable enforcement.** `mypy --strict src/codegenie/probes/layer_b/index_health.py` passes. `mypy --warn-unreachable` per-module on `codegenie.probes.layer_b.index_health` passes ([ADR-0006 §Consequences](../ADRs/0006-index-freshness-sum-type-location.md)). A deliberate removal of one `case Stale(reason=IndexerError(...)):` arm from the AC-9 match block fails the build with `Statement is unreachable` — verified by `tests/unit/probes/layer_b/test_index_health_mypy_warn_unreachable.py` which uses `subprocess.run(["mypy", "--warn-unreachable", ...])` on a temp copy with the arm removed.

- [x] **AC-16 — Registry membership.** `src/codegenie/probes/__init__.py` imports `IndexHealthProbe` via an explicit additive line (`from codegenie.probes.layer_b import index_health  # noqa: F401`); `default_registry.all_probes()` includes it with `runs_last=True` set on the registry entry. `for_task("*", frozenset({"javascript"}))` returns a tuple containing the probe (applies to all languages).

- [x] **AC-17 — Tooling green.** `ruff check src/codegenie/probes/layer_b/index_health.py`, `ruff format --check`, `mypy --strict`, `pytest tests/unit/probes/layer_b/test_index_health_probe.py` all pass. Per-module coverage line/branch ≥ 90/80.

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

4. **`async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`** — the dispatcher.

    ```python
    # Pseudocode shape, ~45 LOC:
    from codegenie.errors import (
        DisallowedSubprocessError, ProbeTimeoutError, ToolMissingError,
    )
    from codegenie.output.paths import raw_dir

    # 1) Resolve HEAD via the Phase 0 chokepoint. Failure modes are all typed.
    try:
        result = await _exec.run_allowlisted(
            ["git", "rev-parse", "HEAD"], cwd=repo.root, timeout_s=5,
        )
    except (ToolMissingError, ProbeTimeoutError, DisallowedSubprocessError,
            FileNotFoundError, NotADirectoryError):
        return _emit_head_unresolvable_for_all_registered_sources()
    if result.returncode != 0:
        return _emit_head_unresolvable_for_all_registered_sources()
    head: str = result.stdout.decode("utf-8").strip()

    # 2) Build slices via the pluggable pure helper (functional core).
    slices: dict[IndexName, dict[str, object]] = read_raw_slices(raw_dir(repo.root))

    # 3) Dispatch — single-call no-branches enforcement (AC-4). On any check
    #    exception, fall back to per-name isolation via dispatch_one (AC-8).
    try:
        freshness_by_name = default_freshness_registry.dispatch_all(slices, head)
    except Exception:
        freshness_by_name = _dispatch_per_name_isolated(slices, head)

    # 4) Shape the slice (AC-10).
    results: dict[str, dict[str, object]] = {}
    for name, freshness in freshness_by_name.items():
        results[str(name)] = {
            "freshness": freshness.model_dump(mode="json"),
            "confidence": _derive_confidence(freshness),         # AC-9 exhaustive match
            "current_commit": head,
            "last_indexed_at": _last_indexed_at(freshness),       # None when Stale
        }

    warnings = [] if results else ["index_health.no_sources_registered"]
    envelope_confidence = _demote_min([r["confidence"] for r in results.values()]) or "high"
    return ProbeOutput(
        schema_slice={"index_health": results},
        raw_artifacts=[],
        confidence=envelope_confidence,
        duration_ms=0,  # coordinator overwrites
        warnings=warnings,
        errors=[],
    )
    ```

5. **`read_raw_slices(raw_dir: Path) -> dict[IndexName, dict[str, object]]` (pure helper, module-level).** For each `*.json` file under `raw_dir`, parses with `json.loads` and keys the result by `IndexName(<filename stem>)`. Returns `{}` for any file that fails to parse OR that doesn't decode to a dict (defensive — each check function handles malformed-slice semantics per AC-5(f)). DP2: keeps the disk-read isolated as a pure injectable function — tests inject in-memory slices without touching disk.

6. **`_derive_confidence` (pure helper).** Exhaustive `match` with `assert_never` per AC-9. Module level (functional core — testable in isolation).

7. **`_last_indexed_at(freshness: IndexFreshness) -> str | None` (pure helper).** Returns `freshness.indexed_at.isoformat()` for `Fresh`; `None` for every `Stale` variant (AC-10).

8. **`_dispatch_per_name_isolated(slices, head) -> dict[IndexName, IndexFreshness]`** (AC-8 fallback). Iterates `default_freshness_registry.registered_names()`; calls `default_freshness_registry.dispatch_one(name, slices, head)` inside a per-name `try`/`except`; substitutes `Stale(IndexerError("freshness_construction_failed_..."))` on any `Exception`.

9. **`_emit_head_unresolvable_for_all_registered_sources` (pure helper).** Iterates `registered_names()`; emits `Stale(IndexerError(message="repo_not_a_git_workdir"))` for each; sets per-source `confidence="low"` and envelope `confidence="low"`; returns a `ProbeOutput` with `warnings=["index_health.head_unresolvable"]`.

10. **`indices/registry.py` additive edit:** add `dispatch_one(self, name: IndexName, slices: dict[IndexName, dict[str, object]], head: str) -> IndexFreshness` public method that wraps `self._checks[name](slices.get(name, {}), head)`. Docstring notes the per-name isolation use case (B2 / S4-01) and that exceptions still propagate to the caller — the **caller** wraps. This is the only edit to S1-02's file in this story.

11. **Logging.** Emit `EVENT_PROBE_START` / `EVENT_PROBE_SUCCESS` / `EVENT_PROBE_FAILURE` (Phase 0 constants). One INFO log line per registered source with structured fields `index_name`, `kind` (= "fresh" or "stale"), `reason_kind` (when stale). No log line includes the sha — provenance is in the slice.

12. **Register the probe** via `src/codegenie/probes/__init__.py` additive import.

## TDD plan — red / green / refactor

### Test helpers preamble (define inline at the top of the test file)

```python
# tests/unit/probes/layer_b/test_index_health_probe.py
from __future__ import annotations
import asyncio, datetime as dt, json
from pathlib import Path
import pytest
from codegenie.indices.freshness import (
    Fresh, Stale, CommitsBehind, CoverageGap, DigestMismatch, IndexerError,
)
from codegenie.indices.registry import (
    default_freshness_registry, register_index_freshness_check,
)
from codegenie.types.identifiers import IndexName
from codegenie.probes.layer_b.index_health import IndexHealthProbe

@pytest.fixture
def clean_freshness_registry():
    """Snapshot + restore the singleton freshness registry around each test.

    The S1-02 registry exposes `unregister_for_tests(name)` (per-name) but no
    global clear; we snapshot `_checks` + `_origins` and restore in
    `finally:` so independent tests register their own scaffolding without
    leaking, AND so a real registration (e.g., the SCIP check imported by
    the module under test) is restored after the test.
    """
    saved_checks = dict(default_freshness_registry._checks)
    saved_origins = dict(default_freshness_registry._origins)
    default_freshness_registry._checks.clear()
    default_freshness_registry._origins.clear()
    try:
        yield default_freshness_registry
    finally:
        default_freshness_registry._checks.clear()
        default_freshness_registry._origins.clear()
        default_freshness_registry._checks.update(saved_checks)
        default_freshness_registry._origins.update(saved_origins)
```

### RED — write failing tests first (in order)

- **T-01** `test_probe_contract_attributes`: instantiate `IndexHealthProbe`; assert every attribute per AC-1; assert `cache_strategy == "none"` (literal) AND `IndexHealthProbe.run.__code__.co_argcount == 3` (self+repo+ctx — pins the two-arg signature against accidental drift); `mypy --strict` of the module exits 0 (subprocess check; positive-control fixture verifies the harness).
- **T-02** `test_runs_last_registry_annotation_present`: locate the `IndexHealthProbe` entry in `default_registry.sorted_for_dispatch()` and assert its `runs_last is True`; AND assert it is the **last** entry of the tuple (positional invariant covered by AC-3a).
- **T-03a** `test_sorted_for_dispatch_places_b2_last` (AC-3a): with `IndexHealthProbe` plus two mock siblings registered, `default_registry.sorted_for_dispatch()[-1].cls is IndexHealthProbe`.
- **T-03b** `test_runs_last_dispatch_order` (AC-3b): construct mock `Probe` subclasses with instrumented `run()` that records `time.monotonic()` to a shared dict; call `await coordinator.gather(snapshot, task, [mock_heavy, mock_light, ihp], config, cache, sanitizer, runs_last_names=frozenset({"index_health"}))`; assert `start_ts["index_health"] >= max(end_ts[other] for other in others)`. The real `gather()` is the harness; no synthetic semaphore.
- **T-04** `test_scip_freshness_fresh_path` (AC-5b): positional call `scip_freshness({"last_indexed_commit": head, "files_indexed": 247, "files_in_repo": 247, "indexer_errors": 0, "last_indexed_at": "2026-01-01T00:00:00+00:00"}, head)` → `Fresh(indexed_at=dt.datetime(2026,1,1, tzinfo=dt.timezone.utc))`.
- **T-05** `test_scip_freshness_commits_behind_path` (AC-5c, AC-6): positional call with `last_indexed_commit="abc..." != head="def..."`; mock `_exec.run_allowlisted` for the rev-list call to return a `ProcessResult(returncode=0, stdout=b"3\n", stderr=b"")` → `Stale(CommitsBehind(n=3, last_indexed="abc..."))`.
- **T-06** `test_scip_freshness_coverage_gap_path` (AC-5d): commit matches but `files_indexed=240 < files_in_repo=247` → `Stale(CoverageGap(files_indexed=240, files_in_repo=247))`.
- **T-07** `test_scip_freshness_indexer_error_path` (AC-5e): commit matches, coverage matches, `indexer_errors=2` → `Stale(IndexerError(message="indexer_reported_2_errors"))`.
- **T-08** `test_scip_freshness_upstream_unavailable_path` (AC-5a, AC-12): positional call `scip_freshness({}, head)` (empty dict — the registry's sentinel for absent sibling JSON file) → `Stale(IndexerError(message="upstream_scip_unavailable"))`. The test additionally asserts `slice is not None` (positive — distinguishing from a `None` sentinel that does NOT match the contract).
- **T-08b** `test_scip_freshness_malformed_slice_path` (AC-5f): positional call with `{"last_indexed_commit": 42, "files_indexed": 0, ...}` (type-wrong) → `Stale(IndexerError(message="scip_slice_malformed"))`.
- **T-09** `test_freshness_construction_failure_is_typed` (AC-8): register a check named `"broken"` that raises `pydantic.ValidationError` alongside the real SCIP check; build slices map; run B2's `run()`; assert the result contains BOTH `IndexName("scip")` (the SCIP check succeeded) AND `IndexName("broken")` mapped to `Stale(IndexerError(message=f"freshness_construction_failed_broken_ValidationError"))`; **no exception escapes `run()`**.
- **T-10** `test_head_unresolvable_path` (AC-7): parametrize over the failure surfaces — `ToolMissingError`, `ProbeTimeoutError`, `DisallowedSubprocessError`, `FileNotFoundError`, AND a `ProcessResult(returncode=128, stdout=b"", stderr=b"fatal: not a git repository\n")` (the "not a workdir" path). For each, assert every registered source emits `Stale(IndexerError(message="repo_not_a_git_workdir"))`; `warnings` contains `"index_health.head_unresolvable"`; per-source AND envelope `confidence="low"`. The test does NOT reference `subprocess.CalledProcessError` or `TimeoutExpired` — those are not in `run_allowlisted`'s exception set.
- **T-11** `test_commits_behind_count_unknown_fallback` (AC-6): mock `_exec.run_allowlisted` so the `git rev-list --count` call returns `ProcessResult(returncode=128, stdout=b"", stderr=b"fatal: ...")` (not in repo); assert `n == 1`; `warnings` contains `"index_health.commits_behind_count_unknown"`. Also test the `ValueError` path: `ProcessResult(returncode=0, stdout=b"not-a-number\n", stderr=b"")` → same fallback.
- **T-12** `test_no_sources_registered_path` (AC-11): with `clean_freshness_registry` empty; `default_freshness_registry.registered_names()` returns `frozenset()`; B2's slice is `{}`; `warnings == ["index_health.no_sources_registered"]`; envelope `confidence="high"` (no degraded source observed); probe returns success.
- **T-13** `test_confidence_derivation_exhaustive` (AC-9): parametrize via a four-row `pytest.mark.parametrize` table mapping each `StaleReason` variant + boundary inputs to the expected `confidence`. Rows: `(Fresh(...), "high")`, `(Stale(CoverageGap(files_indexed=95, files_in_repo=100)), "medium")` (`>= 0.90`), `(Stale(CoverageGap(89, 100)), "low")` (< 0.90), `(Stale(CoverageGap(0, 0)), "low")` (divide-by-zero degenerate), `(Stale(CommitsBehind(1, "abc")), "medium")`, `(Stale(DigestMismatch("x","y")), "medium")`, `(Stale(IndexerError("z")), "low")`. Plus: assert that constructing an `IndexFreshness` instance with an unknown variant raises a `pydantic.ValidationError` at construction time (the smart-constructor is the actual `assert_never` enforcement; the unreachable arm is enforced by T-19's mypy check).
- **T-14** `test_no_sibling_probe_imports` (AC-13): AST-walk `index_health.py`; assert no `import` or `from` targets `codegenie.probes.layer_a.*`/`layer_b.<not-self>`/`layer_c.*`/`layer_d.*`/`layer_e.*`/`layer_g.*`. Positive control: assert the imports DO target `codegenie.probes.{base, registry}`, `codegenie.indices.{freshness, registry}`, `codegenie.exec`, `codegenie.types.identifiers`, `codegenie.output.paths`, `codegenie.errors`.
- **T-15a** `test_run_body_has_no_per_index_branches` (AC-4 negative): AST-walk `IndexHealthProbe.run`; collect every `Compare` node's right-hand constant; assert none matches a known index name (`scip`, `runtime_trace`, `sbom`, `semgrep`, `gitleaks`, `conventions`).
- **T-15b** `test_run_invokes_dispatch_all_exactly_once` (AC-4 positive): AST-walk `IndexHealthProbe.run`; count `Await` nodes whose target attribute name is `"dispatch_all"`; assert count is exactly 1.
- **T-16** `test_cache_strategy_none_hook_present` (AC-2): read `.pre-commit-config.yaml`; assert there is a hook entry that scopes `forbidden-patterns` to `src/codegenie/probes/layer_b/index_health.py` and includes the four mtime patterns. Mutation: temporarily replace one pattern with a typo and assert the hook fails on that file.
- **T-17** `test_warning_ids_match_adr_0007` (AC-14): every member of `_WARNING_IDS` matches the regex (this is the import-time `assert` reverified at test time so removal of the import-time `assert` is caught).
- **T-18** `test_registry_membership_and_for_task_filter` (AC-16): `IndexHealthProbe` in `default_registry.all_probes()`; `for_task("*", frozenset({"javascript"}))` includes it; `for_task("*", frozenset({"go"}))` includes it too (`applies_to_languages=["*"]`).
- **T-19** `test_mypy_warn_unreachable_fires_on_removed_arm` (AC-15): copy `index_health.py` to a tempdir; remove one `case Stale(reason=IndexerError(...))` arm from `_derive_confidence`; run `python -m mypy --strict --warn-unreachable` on the copy; assert exit code != 0 AND stderr contains `"unreachable"`. Positive control: unmodified copy passes `mypy --warn-unreachable` with exit 0.
- **T-20** `test_slice_shape_localv2_compliance` (AC-10): construct a snapshot with the SCIP raw artifact present; run B2; assert (a) `set(slice["index_health"].keys()) == set(default_freshness_registry.registered_names())` — outer-key invariant; (b) per-source keys are exactly `{"freshness", "confidence", "current_commit", "last_indexed_at"}`; (c) `freshness` is a dict with `"kind"` discriminator; (d) `last_indexed_at is None` when the variant is `Stale`, otherwise is an ISO8601 string.
- **T-21** `test_read_raw_slices_pure_helper`: under `tmp_path`, plant `scip.json` (valid), `bad.json` (not parseable), `not_a_dict.json` (a JSON list); call `read_raw_slices(tmp_path)`; assert only `IndexName("scip")` is in the result; the other two are silently omitted (each check function is responsible for its own malformed-slice semantics).

All 22+ tests (T-01..T-21 + sub-tests) must fail before any production code is written.

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
- `src/codegenie/indices/registry.py` — additive: new public method `FreshnessRegistry.dispatch_one(name, slices, head)` per Implementation step 10 (supports AC-8). No edit to `dispatch_all` / `register` / `registered_names` / `unregister_for_tests`. Update module docstring with an "S4-01 (additive)" line.
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

- **Import discipline.** `from codegenie import exec as _exec` (consistent with S2-02 / Rule 11). `from codegenie.indices.freshness import Fresh, Stale, CommitsBehind, CoverageGap, IndexerError, IndexFreshness`. `from codegenie.indices.registry import default_freshness_registry, register_index_freshness_check`. `from codegenie.types.identifiers import IndexName`. `from codegenie.output.paths import raw_dir`. `from codegenie.errors import DisallowedSubprocessError, ProbeTimeoutError, ToolMissingError`. Do NOT import from `codegenie.probes.layer_a.*` or `layer_b.*` (sibling) — AC-13 enforces.
- **The `cache_strategy="none"` discipline.** A future contributor will propose "let's cache B2 for performance." The answer is in three places: this story (Notes), the per-module pre-commit hook (AC-2), and [phase-arch-design.md §"Harness engineering"](../phase-arch-design.md) (the "caching `Date.now()`" framing). Memo all three.
- **`runs_last=True` is one probe per gather.** ADR-0003 documents this as a constraint of the registry annotation. Phase 2 has exactly one `runs_last=True` probe (B2). Phase 3+ adding a second is an ADR amendment to ADR-0003.
- **The structural assertion B2 enables.** S4-02's adversarial test asserts `isinstance(freshness, Stale)` AND `isinstance(freshness.reason, CommitsBehind)` AND `freshness.reason.n >= 1` AND `freshness.reason.last_indexed != current_HEAD`. Both inequalities are load-bearing (implementation risk #3 from the manifest) — `n >= 1` alone would pass if `n` were unconditionally `1` due to a fallback (AC-6 — that's exactly the fallback path); the `last_indexed != current_HEAD` check catches the case where the fallback fires AND the structural fact (different commits) still holds. Do not relax AC-6's fallback to "always `n=1`" — the rev-list path is the source of truth when it works.
- **Empty registry is valid.** AC-11 codifies this. The Open/Closed seam means "no sources registered" is a temporary deployment state, not an error. The warning `index_health.no_sources_registered` exists so a CI-state regression (e.g., `S5-05` accidentally not registered) is loud.
- **Rule 9 (tests verify intent).** Every test in the TDD plan encodes a *why*: T-15 (no per-index branches) encodes the Open/Closed discipline; T-09 (typed construction failures) encodes the "never raise" failure-isolation discipline; T-19 (mypy --warn-unreachable fires) encodes the exhaustive-match discipline. None of them check "the code returns a value" without checking what *kind* of value and why.
- **No `pytest.skip` on missing `git`.** Phase 0 tool-check refuses to start `codegenie gather` without `git`; the unit tests stub `run_allowlisted` and never invoke real git. The integration suite is downstream of this story (S7-05's portfolio sweep) and gates on real-tool presence with loud warning.

### Design-pattern notes (from validation, 2026-05-16)

- **DP1 — `dispatch_all` IS the no-branches enforcement.** The `run()` body's only call into the registry is `await default_freshness_registry.dispatch_all(slices, head)`. T-15a (AST-walk for missing per-index `Compare` nodes) is defense-in-depth; T-15b (AST-walk asserting *exactly one* `Await` of `dispatch_all`) is the positive structural invariant. A future contributor who adds an `if name == "scip":` shortcut "for performance" must defeat both.
- **DP2 — Pluggable sibling-slice reader (functional core / imperative shell).** `read_raw_slices(raw_dir: Path) -> dict[IndexName, dict[str, object]]` is pure (the only I/O is the file read; the function returns a fully-realized dict). Tests inject in-memory slices by constructing the same dict shape, skipping the disk entirely. This mirrors `_derive_confidence` (pure helper) and `_last_indexed_at` (pure helper). B2's `run()` is the imperative shell that composes the three pure helpers + the registry call. **No hidden state, no class to carry state across calls.**
- **DP3 — Producer/consumer `assert_never` ladder closed at B2.** B2 is the *producer* of `IndexFreshness`; S8-01's `confidence_section.py` is the *consumer*. Both ends exhaustively `match` on the sum type with `assert_never` in the default arm, and `mypy --warn-unreachable` per-module on both modules enforces the discipline. A new `StaleReason` variant requires an ADR amendment to 02-ADR-0006 AND coordinated edits at both ends; the structural enforcement is the `assert_never` in both `_derive_confidence` (here) and `confidence_section.render` (S8-01). Document this ladder in this module's docstring.
- **DP4 — `IndexName` newtype rule-of-three reached here; kernel-extract deferred.** S1-02 (registry key — 1st), S5-05 (runtime_trace check registration — 2nd), S4-01 (B2 enumerates `registered_names()` — 3rd). The kernel-extract opportunity (`KernelRegistry[K, V]` base shared across `codegenie.probes.registry`, `codegenie.indices.registry`, `codegenie.depgraph.registry`) crosses the rule-of-three threshold here, but this story does NOT pre-extract (Rule 2 — simplicity first; Rule 3 — surgical changes). The refactor is queued for a dedicated story when the 4th registry arrives; the comment in `src/codegenie/indices/registry.py:26-31` already names this.
- **Cross-story integration handoff.** S4-03 (SCIP probe) MUST write `<repo>/.codegenie/context/raw/scip.json` during its `run()` containing keys `{"last_indexed_commit", "files_indexed", "files_in_repo", "indexer_errors", "last_indexed_at"}`. Without that file, B2 emits `Stale(IndexerError("upstream_scip_unavailable"))` (AC-12). The S4-03 story acceptance criteria must include this filename + key set as a contract.
- **Additive edit to `indices/registry.py`.** This story adds one method — `FreshnessRegistry.dispatch_one(name, slices, head)` — to support AC-8's per-name exception isolation. The method is a 3-line wrapper around `self._checks[name](slices.get(name, {}), head)`. It does NOT change `dispatch_all`'s signature or behavior. No existing callers are affected. Document the addition in `indices/registry.py`'s module docstring under "S4-01 (additive)".
