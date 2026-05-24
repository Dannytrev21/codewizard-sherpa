# Validation Report — S6-06 `typecheck.typescript` applicability matrix

**Story:** `docs/phases/04-vuln-llm-fallback-rag/stories/S6-06-typecheck-applicability-matrix.md`
**Validator run:** 2026-05-23 (automated `phase-story-validator` skill, scheduled-task pass)
**Verdict:** **HARDENED**
**Sibling precedent:** `_validation/S6-05-typecheck-typescript-signal.md` (BLOCK-heavy hardening of the base collector; six clusters of stale class/API references corrected)

---

## Context Brief

### Story snapshot
- **Goal (verbatim):** "Add `TypeScript-in-scope` detection to `TypecheckTypescriptSignal.collect`: presence of `tsconfig.json` AND any `.ts` files in the repo. Dispatch the four-case applicability matrix per arch §Gap 4; emit `TrustSignal(passed=True, details={'applicable': False}, confidence='high')` for JS-only repos so they pass strict-AND instead of failing it."
- **Non-goals:** promotion to shared `vulnerability-remediation--node--*` base plugin; tsconfig project-references / path-mapped subdirs; re-invoking tsc on the vacuous case.

### Sibling-family lineage (Design-Patterns critic)
- **2nd concrete story in the typecheck.typescript family** (after S6-05 — base collector + registration). Rule of three NOT YET reached for the `typecheck.<lang>` kernel extract (defer to Phase 7.5 Python sibling).
- **Prior validation framings carried forward from S6-05:**
  - `TrustSignal` has no `confidence` field; Pydantic `extra="forbid"` (Cluster B).
  - `details: dict[str, str | int | bool | float]` (shipped is wider than arch §line 763) (Cluster B).
  - Collector is a plain `async def` function, **not** a `Signal` class with `.collect(...)`; no `SignalCollector` Protocol exists (Cluster A).
  - Collector signature: `collect_typecheck_typescript_signal(repo_root: Path, baseline_repo_sha: RepoSha, timeout_s: float = 30.0) -> TrustSignal` — no `ctx`, no `RepoSnapshot` (Cluster A).
  - Subprocess surface is `run_allowlisted`, not `SubprocessJail` (Cluster D).
  - Plugin module loader uses the **literal hyphenated slug**; `importlib.import_module("plugins.vulnerability-remediation--node--npm...")` (Cluster E).
  - Sum types are `@dataclass(frozen=True)` discriminated unions (`ErrorCount | UnparseableOutput`), not `Literal` or enum (Cluster H).
  - Mutation-barrier tests assert **both directions** in the same test (positive AND negative outcome) (Cluster I, Cluster J).
  - Purity AST-fence covers the pure parser + comparator helpers (AC-12).

### Phase / arch constraints reviewed
- **ADR-04-0015 §Tradeoffs / §Consequences** — applicability is "plugin-local" (no shared `node--*` base plugin yet); missing-tsc → degraded path; OK.
- **phase-arch-design.md §Gap analysis Gap 4** — the source of the four-case matrix. The matrix in the gap analysis IS the load-bearing prescription; S6-06 implements it.
- **CLAUDE.md "Extension by addition"** — applicability dispatch must not edit Phase-3 transforms; lives in the plugin module.
- **CLAUDE.md "Functional core / imperative shell"** — applicability detection should be pure logic over a bounded filesystem read; tested in isolation.

### Open ambiguities resolved before critics
- Story claims `_is_typescript_in_scope` is "Pure: no I/O outside the repo snapshot" but there is no `repo_snapshot` (signal collectors don't receive a `RepoSnapshot`). **Resolved:** function takes `repo_root: Path` and performs bounded directory I/O (stat + scandir); reframe as "bounded I/O, deterministic, no subprocess / no network / no mutation" rather than "pure".

---

## Critic findings

### Critic 1 — Coverage

| Tag | Severity | Finding |
|---|---|---|
| C1.1 | BLOCK | Goal text says "presence of `tsconfig.json` AND any `.ts` files" but the matrix is OR/AND. Goal mis-describes the predicate (the matrix has four cases including `tsconfig=False, ts_files=True`). |
| C1.2 | HARDEN | No AC pins that `run_allowlisted` is **not** called when `NotApplicable` — a wasteful implementation that runs `tsc` then overrides the result would pass every functional test. Need a mock-call-count assertion. |
| C1.3 | HARDEN | `node_modules/` exclusion is mentioned but untested. Every `npm install` creates thousands of `.ts` files under `node_modules/`; a walker that doesn't exclude it misclassifies every JS-only repo with installed packages as having TypeScript present. |
| C1.4 | HARDEN | Empty repo (no files at all) → predictable case. Not explicitly tested but covered by `(no tsconfig, no .ts files)` → `NotApplicable`. Confirm by listing as a degenerate case in the parametrize table. |
| C1.5 | HARDEN | Documentation amendments: arch §Gap 4 already prescribes the matrix; **no ADR/design-doc amendment is needed for the matrix itself**. But the `details["applicable"]` and `details["ts_files_count"]` key contract should be mentioned in ADR-04-0015 §Consequences for forensics readers. Optional AC, not required. |
| C1.6 | NIT | Out-of-scope is explicit and tight. |

### Critic 2 — Test Quality

| Tag | Severity | Finding |
|---|---|---|
| C2.1 | BLOCK | `test_tsx_files_count_as_typescript_in_scope` uses `tsconfig=True, ts_files=False, tsx_files=True` → asserts `applicable`. **Bug**: `tsconfig=True` alone already returns `applicable`; the test passes whether or not `.tsx` detection works. Correct test: `tsconfig=False, ts_files=False, tsx_files=True → DegradedNoTsconfig` (verifies that `.tsx` triggers the "ts files present" branch). |
| C2.2 | BLOCK | `test_d_ts_only_repo_treated_as_in_scope`: same bug shape (`tsconfig=True, ts_files=False, d_ts_files=True → applicable`). Correct test: `tsconfig=False, ts_files=False, d_ts_files=True → DegradedNoTsconfig`. |
| C2.3 | BLOCK | `collect_all_signals(js_only_fixture_repo)` referenced in integration test does not exist in shipped Phase-3 code. Test would `AttributeError` at import. Replace with explicit construction: call `await collect_typecheck_typescript_signal(repo_root, baseline_sha)`, then pass `[signal, ...]` to `TrustScorer(event_log=event_log_fixture).score(...)` — mirrors S6-05 AC-5. |
| C2.4 | BLOCK | Tests use `.value == "applicable"` string comparison. Per Cluster J below, the sum type should be frozen-dataclass variants — use `isinstance(result, mod.Applicable)` for type-discipline and mypy exhaustiveness. |
| C2.5 | HARDEN | Performance AC `≤ 50 ms` is wall-clock-flaky on CI. Replace with structural assertion: walker uses `os.scandir` (or `Path.iterdir`) iteratively; does not recurse into `node_modules/` (asserted by a fixture with 10K `.ts` files under `node_modules/` returning `NotApplicable` in under a generous bound, e.g., 2s, while a 10-file project root returns in under the same bound). |
| C2.6 | HARDEN | Integration test asserts only the positive direction (JS-only → pass). A constant `applicable=False` mutation passes both unit and integration tests. Mirror S6-05 AC-5: assert **both directions** in same test — JS-only-pass AND TS-repo-with-failing-`tsc` produces `outcome.passed is False`. |
| C2.7 | HARDEN | `repo_factory` fixture is referenced but never specified. Pin shape in TDD plan so executor doesn't drift: takes `tmp_path` plus boolean flags, creates files with minimal content (`tsconfig.json` = `{}`, `*.ts` = empty), returns `repo_root: Path`. |

### Critic 3 — Consistency

| Tag | Severity | Finding |
|---|---|---|
| C3.1 | BLOCK | **`confidence` field doesn't exist on `TrustSignal`** (`outcomes.py:377-388`; Pydantic `extra="forbid"`). S6-06's Goal, AC table row 4 ("not applicable; pass not degrade"), AC-1 bullet, AC-4, integration test, etc. set `confidence="high"` / `"medium"` extensively. Every such assertion is mechanically wrong against shipped code — `extra="forbid"` raises `ValidationError` at construction. S6-05's Cluster B already fixed this for the prior story; S6-06 re-introduces. |
| C3.2 | BLOCK | **`TypecheckTypescriptSignal` class doesn't exist.** S6-05 ships a plain `async def collect_typecheck_typescript_signal(repo_root, baseline_repo_sha, timeout_s=30.0) -> TrustSignal`. S6-06 tests instantiate `sig = TypecheckTypescriptSignal()` and call `await sig.collect(repo, ctx)`. Won't import. Re-frame in terms of the function. |
| C3.3 | BLOCK | **`RepoSnapshot` is the wrong input type.** `RepoSnapshot` (`src/codegenie/probes/base.py:32`) is a Phase-0 probe input with fields `root, git_commit, detected_languages, config` — **no file list**. Signal collectors (post-patch evaluation tier) don't receive it. The applicability helper should take `repo_root: Path` and walk the filesystem locally. |
| C3.4 | BLOCK | **`details` type widening contradicts S6-05.** AC-6 says "`details: dict[str, str|int|bool]` shape from arch §Type contracts (line 763) unchanged". S6-05 already widened the spec to match shipped `dict[str, str|int|bool|float]`. Adopt the wider shape; do not narrow. |
| C3.5 | BLOCK | **Plugin module import path uses underscores.** Test code shows `from plugins.vulnerability_remediation__node__npm.adapters.ts_typecheck_signal import ...`. Per S7-01 hardening + S6-05 Cluster E, the loader uses the literal hyphenated slug; tests must use `importlib.import_module("plugins.vulnerability-remediation--node--npm.adapters.ts_typecheck_signal")`. |
| C3.6 | BLOCK | **`collect_all_signals(...)` is not a shipped API.** See C2.3. Re-write integration test to construct the signal list explicitly and call `TrustScorer(event_log=...).score(signals)`. |
| C3.7 | HARDEN | **Goal text "AND" is misleading** vs the matrix's "OR" (any combination of two booleans triggers applicability except the both-false row). Tighten Goal. |
| C3.8 | NIT | "Use the existing repo-snapshot file list" in the Refactor section — there is no such field on `RepoSnapshot`. Replace with "walk `repo_root` once with `os.scandir`, skip `node_modules`, collect file-suffix presence". |

### Critic 4 — Design Patterns

| Tag | Severity | Finding |
|---|---|---|
| C4.1 | HARDEN | **Sum-type framing should mirror S6-05's `ErrorCount | UnparseableOutput` pattern** — frozen dataclass variants, not `Literal[...]` or enum. Yields `Applicable | DegradedNoTsconfig | NotApplicable` where `Applicable` can carry a `ts_files_count: int` payload (forensics). Enables `match`-statement exhaustiveness via `assert_never` and adds zero overhead vs `Literal`. |
| C4.2 | HARDEN | **Function name `_is_typescript_in_scope` reads as a boolean predicate** but returns a sum type. Rename to `_typescript_applicability(repo_root: Path) -> TypeScriptApplicability` per S6-05 naming hygiene (`_parse_tsc_error_count` returns sum, named for the action). |
| C4.3 | HARDEN | **Dispatch in `collect` should be `match`-exhaustive with `assert_never`**, not an `isinstance` ladder. Adding a fifth applicability variant later then triggers mypy non-exhaustive error rather than silently falling through. |
| C4.4 | HARDEN | **AST-walking purity / boundedness fence** for the new helper. The helper has bounded I/O (path stat + directory scan) — not strictly pure. Re-frame the fence AC: assert no `subprocess`, no `asyncio`, no `network`, no file content reads (`.read_text` / `.read_bytes` / `open(... 'r')`), no mutation. Extend `tests/fence/test_phase4_typecheck_purity.py` (added by S6-05) rather than creating a new fence file. |
| C4.5 | HARDEN | **Open/Closed pre-check.** S6-06 must not edit `src/codegenie/transforms/*` — applicability is plugin-local. Reuse S6-05 AC-6's `tests/fence/test_phase4_no_trust_scorer_edits.py` (extend the date / scope to cover S6-06's commits) rather than creating a new fence. |
| C4.6 | NIT | **Future-sibling note (Notes-for-implementer only).** When Phase 7.5 lands `typecheck.python`, the (`tsconfig.json` + `*.ts`) ↔ (`pyproject.toml` + `*.py`) parallel triggers the kernel extract: `TypecheckApplicabilityKit(language: str, manifest_files: list[str], source_suffixes: list[str], exclude_dirs: list[str]) -> Applicability`. **First sibling ships flat** per Rule of Three + Rule 2 (three similar lines beats premature abstraction). Surface as Notes-for-implementer; **not** an AC. |

### Findings tagged `NEEDS RESEARCH`
- None. All findings have known canonical patterns from S6-05's validation precedent or shipped-code source-of-truth.

---

## Synthesis

**No critic conflicts** — all four critic threads point at the same root cause: S6-06 was written **before** S6-05 went through validation, so it carries the same class-based / `confidence`-field / `SubprocessJail` framings that S6-05's hardening corrected. The same six clusters need re-doing here. No conflict between Coverage and Consistency / Test-Quality and Design-Patterns.

**Priority resolution** — Consistency wins where it conflicts with anything; shipped code is the source of truth. Test-Quality bug fixes (C2.1, C2.2) are independent of design-pattern wisdom; both apply.

**Verdict: HARDENED.** All findings are fixable by editing the story. No structural rescue needed (the Goal is correct, the matrix is the right shape, the scope is single-purpose).

---

## Edits applied to the story

### Cluster A — Stale class-based API replaced with shipped function-based collector
- Goal rewritten to call the plain `async def collect_typecheck_typescript_signal` and add a pre-dispatch helper `_typescript_applicability(repo_root)` that gates the existing call.
- All test references to `TypecheckTypescriptSignal()` / `sig.collect(repo, ctx)` removed; tests now construct via `await mod.collect_typecheck_typescript_signal(repo_root=tmp_path, baseline_repo_sha=RepoSha("..."), timeout_s=30.0)`.
- Removed every `ctx` and `RepoSnapshot` reference.

### Cluster B — `confidence` field on `TrustSignal` removed everywhere
- AC table column "confidence" deleted; replaced with `details` key annotations (e.g., `details={"applicable": False}` for the not-applicable case).
- `TrustSignal(...)` constructions in tests drop `confidence=`; `Pydantic extra="forbid"` would raise otherwise.

### Cluster C — `details` shape adopts the shipped `dict[str, str|int|bool|float]`
- AC-6 (shape preserved) renumbered and rewritten to track the shipped wider type and reference S6-05 Cluster B precedent.

### Cluster D — `RepoSnapshot` replaced with `repo_root: Path`
- `_typescript_applicability(repo_root: Path) -> TypeScriptApplicability`. Walks the filesystem locally using `os.scandir`; excludes `node_modules/`; collects suffix counts.
- Refactor note "use the existing repo-snapshot file list" deleted (no such field).

### Cluster E — Module import path uses hyphenated slug via `importlib`
- Tests use `importlib.import_module("plugins.vulnerability-remediation--node--npm.adapters.ts_typecheck_signal")` (consistent with S6-05 AC-1 + S7-01 hardening).

### Cluster F — Integration test rewritten to use shipped surface
- `collect_all_signals(...)` removed; integration test calls the collector directly, builds the signal list, and passes to `TrustScorer(event_log=in_memory_event_log).score(signals)` — mirrors S6-05 AC-5 both-directions assertion.

### Cluster G — Edge-case tests now actually test the edge
- `.tsx` test: `tsconfig=False, ts_files=False, tsx_files=True → DegradedNoTsconfig` (verifies `.tsx` triggers the "ts files present" branch).
- `.d.ts` test: `tsconfig=False, ts_files=False, d_ts_files=True → DegradedNoTsconfig` (same).
- `tsconfig=True, ts_files=False` retained as a separate vacuous-applicable case.

### Cluster H — NotApplicable short-circuits before `run_allowlisted`
- New AC: when `_typescript_applicability` returns `NotApplicable`, `run_allowlisted` mock has `call_count == 0`. Test asserts the early-return path.

### Cluster I — `node_modules/` exclusion test pinned
- New AC: a fixture with `node_modules/some-pkg/index.ts` (and no source-root `.ts` files or `tsconfig.json`) is classified `NotApplicable`. Bounded-walker test reinforces.

### Cluster J — Sum type framing aligned with S6-05's discriminated-union precedent
- `TypeScriptApplicability = Applicable | DegradedNoTsconfig | NotApplicable` — each a `@dataclass(frozen=True)`. `Applicable` carries `ts_files_count: int` for forensics.
- Dispatch in `collect` uses `match`/`case` with `assert_never` exhaustiveness.

### Cluster K — Same-test-both-directions mutation barriers
- Integration test asserts JS-only-pass AND TS-with-broken-types-fail in the same test.
- Parametrize table asserts all four matrix cases dispatch correctly (any constant-returning mutation fails at least one row).

### Cluster L — `_is_typescript_in_scope` renamed to `_typescript_applicability`
- Function name now matches return-type shape.

### Cluster M — Purity AST-fence extended to cover the new helper, scope clarified
- AC extends `tests/fence/test_phase4_typecheck_purity.py` (S6-05's fence) to include `_typescript_applicability`.
- Bounded-I/O scope: no `subprocess`, no `asyncio`, no network, no file-content reads (only stat + scandir); no module-level state mutation.

### Cluster N — Performance AC replaced with structural / bounded assertion
- Wall-clock `≤ 50 ms` deleted; replaced with: (a) walker uses `os.scandir` iteratively, (b) does not recurse into `node_modules/`, (c) fixture with 10K-files-under-`node_modules/` returns within 2 s (generous envelope, not flaky).

### Cluster O — Goal text reframed
- Goal now says "presence of `tsconfig.json` and/or any `.ts` / `.tsx` / `.d.ts` file in the working tree (excluding `node_modules/`)" — accurate vs the matrix.

### Cluster P — Documentation amendments
- No ADR amendment required (arch §Gap 4 already prescribes the matrix verbatim). Notes-for-implementer documents that the `details["applicable"]` + `details["ts_files_count"]` key contract is forensic-only — no doc change needed.

### Cluster Q — Open/Closed verified via existing fence
- AC reuses `tests/fence/test_phase4_no_trust_scorer_edits.py` (S6-05) rather than adding a new fence — same intent.

### Cluster U — Future-sibling kernel extract surfaced as Notes-for-implementer
- Notes paragraph added pointing to the second sibling (`typecheck.python` in Phase 7.5) as the rule-of-three trigger for a `TypecheckApplicabilityKit(language, manifest_files, source_suffixes, exclude_dirs)` extract. First sibling ships flat per Rule 2.

---

## Final story strength (post-edit)

- Every AC is verifiable against shipped code (Cluster A–F resolved).
- Mutation-resistance: same-test-both-directions for integration; non-trivial edge-case fixtures for `.tsx` / `.d.ts` / `node_modules/`; explicit no-spawn assertion for `NotApplicable`.
- Pattern fit: discriminated-union sum type with `match`-exhaustive dispatch (mirrors S6-05); rule-of-three deferred extract documented as Notes-only.
- Open/Closed: reuses S6-05's `test_phase4_no_trust_scorer_edits.py` fence; no kernel edits.
- Out-of-scope intact; future-sibling cleanly deferred.

The story is now ready for `phase-story-executor`. Mark status `HARDENED`.
