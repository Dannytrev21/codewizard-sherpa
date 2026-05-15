# Validation report — S4-03 `TestInventoryProbe` + sub-schema + lcov scanner

**Story:** [S4-03-test-inventory-probe.md](../S4-03-test-inventory-probe.md)
**Validated:** 2026-05-14
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

S4-03 is the third and final probe in Step 4 — the unique piece is the **lcov scanner**, the single security-load-bearing piece of bespoke Phase-1 code. The story was directionally sound — ADR-0009 (no `lcov-parse` dep) cleanly pinned, the 50 MB cap correctly identified, the four-probe-consumer memo pattern recognized — but **three critical Consistency findings** and the same recurring **Coverage / Test-Quality / Design-Patterns** patterns from S4-01 (CIProbe) and S4-02 (DeploymentProbe) all reappeared. The story did not learn from the S4-01 / S4-02 hardening reports cited indirectly through its dependency chain.

Three load-bearing critical bugs were present:

- **CN-1 [CRITICAL] — `e2e_framework` slice field completely unaddressed.** `TestInventorySlice` (arch line 749–758) declares `e2e_framework: Literal["playwright","cypress"] | None` as a **separate** field. Original story enumerated `playwright`/`cypress` inside the `framework`-detection list as if they were unit-test frameworks. Production consumers (Phase 3+ recipes) read `framework` for unit-test orchestration and `e2e_framework` for E2E gating — conflating them silently breaks downstream logic. Resolution per Rule 7 (Consistency > Coverage): split detection into two parallel registries with parametrized 9-row matrix proving orthogonality.
- **CN-2 [CRITICAL] — `coverage_data` field shape contradiction (arch line 570 vs 757).** Arch line 757: `coverage_data: CoverageBlock | None`. Arch line 570: "Missing `coverage/lcov.info` → `coverage_data.present: false`." The two readings are mutually exclusive without explicit resolution. Resolution per Rule 7: arch line 570 wins (failure-mode docs are authoritative on slice-emission semantics); always emit `CoverageBlock` with four-state matrix `{file-absent, file-parsed-OK, file-size-capped, file-other-parse-error}`. `None` reserved as the "probe didn't even check" escape hatch (unreachable in Phase 1).
- **CN-3 [CRITICAL] — ADR-0007 colon-suffix repeat-trap mitigated structurally before writing.** S4-01 CN-1 and S4-02 CN-1 both fixed the same drift (`<id>:<path>` violation of `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`). S4-03's emitted IDs (`coverage.lcov_parse_error`, `coverage.size_cap_exceeded`, `test_framework.ambiguous`) happen to be bare-form already, but the *structural* defense (frozenset + import-time pattern loop) was absent. New AC-42 + AC-43 + AC-44 lift the defense in place — future typos fail at module import, before tests run.

Plus the same recurring patterns: missing test-helper preamble (TQ-1/TQ-2), `@pytest.mark.asyncio` vs sibling `asyncio.run` (TQ-2 / Rule 11), wall-clock-only fuzz assertion (TQ-3 — flaky in CI), missing contract-attributes test (TQ-5 — S2-02 frozen-ABC regression), missing registry-membership test (TQ-6), missing schema-rejection-at-exact-JSON-Pointer test (TQ-7), missing walk-every-nested-block test (TQ-7), missing two-run determinism test (TQ-8 / CV-8), missing `package.json` typed-exception routing (CN-4), inline framework-map without Open/Closed seam (DP-1), no `_WARNING_IDS` / `_ERROR_IDS` frozensets (DP-5), no `LcovTotals` NamedTuple (DP-7), no `CoverageBlock` TypedDict (DP-7), no `_LCOV_PREFIX_MAP` dispatch (DP-2), no `_NOISE_DIRS` import discipline (DP-5), no kernel reuse of `parsers._io.open_capped` (DP-4 — the lcov scanner re-implemented `O_NOFOLLOW + fstat + close`), no pure-helper extraction (DP-6), no memo-allowlist enforcement (CV-4 / ADR-0002), no confidence-field-rejection test (CV-5 — TestInventorySlice has NO confidence field).

The synthesizer rewrote ACs from **10 bundled bullets + 7 TDD tests** to **57 individually-verifiable ACs + ~38 TDD tests** (most parametrized). New module-level Open/Closed seams: `_FRAMEWORK_DETECTORS`, `_E2E_FRAMEWORK_DETECTORS`, `_CANONICAL_SCRIPT_NAMES`, `_TEST_FILE_PATTERNS`, `_SMOKE_PATH_PRECEDENCE`, `_LCOV_PREFIX_MAP`, `_LCOV_MAX_BYTES`, `_WARNING_IDS`, `_ERROR_IDS`, `_ID_PATTERN`. New shapes: `LcovTotals = NamedTuple`, `CoverageBlock = TypedDict`. Pure helpers extracted (functional core / imperative shell): `_engines_at_least`, `_select_framework`, `_select_e2e_framework`, `_count_test_files`, `_select_smoke_path`, `_extract_canonical_scripts`, `_classify_node_test`. Each pure helper has a corresponding table-driven unit test.

**No `NEEDS RESEARCH` findings.** Every weakness was resolvable from authority docs (Phase 1 arch + ADR-0001..ADR-0013 + production ADR-0005) plus the S2-02 / S4-01 / S4-02 hardened-story precedents and the existing `node_build_system.py` reference implementation. Stage 3 (researcher) skipped per skill's token-economy guidance.

## Most load-bearing fixes (block-tier)

1. **CN-1 (CRITICAL) — `e2e_framework` field surfaced.** New AC-7 + AC-8 + AC-9 split detection into `_FRAMEWORK_DETECTORS` (unit) + `_E2E_FRAMEWORK_DETECTORS` (E2E). 9-row parametrized matrix proves orthogonality. The Goal sentence updated to reference both fields explicitly.

2. **CN-2 (CRITICAL) — `coverage_data` four-state matrix.** New AC-30 + AC-31 + AC-32 pin: file absent → `CoverageBlock(present=False, parse_error=False, totals=None)`; file present + OK → `CoverageBlock(present=True, parse_error=False, totals=LcovTotals(...))`; file present + SizeCapExceeded → `CoverageBlock(present=True, parse_error=True, totals=None) + warnings=["coverage.size_cap_exceeded"]`; file present + other parse error → `CoverageBlock(present=True, parse_error=True, totals=None) + warnings=["coverage.lcov_parse_error"]`. The Python `None` is structurally permitted by the schema but the Phase-1 probe never emits it (AC-32 meta-test).

3. **CN-3 (CRITICAL) — `_WARNING_IDS` / `_ERROR_IDS` frozenset + import-time ADR-0007 loop.** New AC-42 (4-entry warning frozenset) + AC-43 (3-entry error frozenset) + AC-44 (`_ID_PATTERN` compile-time check). Mirrors `node_build_system.py:212-254` verbatim. Future colon-suffix typos fail at module import.

4. **TQ-1 / TQ-2 (BLOCK) — Test-helper preamble + `asyncio.run`.** TDD plan now opens with the complete preamble (`_snapshot`, `_ctx`, `_run`) inlined from `tests/unit/probes/test_node_build_system.py:67-94`. Every `async def test_*` switched to `def test_*` with `_run(root)` (synchronous; uses `asyncio.run` internally). Matches sibling conventions per Rule 11.

5. **TQ-3 (BLOCK / SECURITY) — Byte-budget fuzz, not wall-clock-only.** New AC-28 replaces `time.monotonic() - t0 < 1.0` with two complementary assertions: (a) `bytes_scanned / elapsed_s >= 5_000_000` (5 MB/s structural ReDoS-defense floor); (b) wall-clock 5 s soft canary. Resilient under noisy-neighbour CI; structurally meaningful upper bound.

6. **TQ-4 (BLOCK / SECURITY) — Symlink-via-coverage sentinel-style test.** New AC-27 + the corresponding red test: `coverage/lcov.info` is a symlink to a file outside the repo carrying `LF:31337`; the scanner raises `SymlinkRefusedError`; the probe converts to the `coverage_data` parse_error state; the sentinel value `31337` MUST NOT appear in any emitted slice field. Smoking-gun assertion mirrors S4-02's zip-slip sentinel-exfiltration discipline.

7. **TQ-5 (BLOCK) — Contract-attributes test.** New AC-2 + AC-3 pin every class attribute including `isinstance(declared_inputs, list)` (NOT tuple — S2-02 regression) and the 12-entry `declared_inputs` list verbatim against arch line 560.

8. **TQ-6 / CV-6 (BLOCK) — Registry membership across 5 language sets.** New AC-5 parametrizes over `frozenset({"javascript"})`, `frozenset({"typescript"})`, `frozenset({"javascript","typescript"})`, `frozenset({"go"})`, `frozenset()`. Catches accidental `applies_to_languages` narrowing or `requires` mis-ordering.

9. **TQ-7 / CV-7 (BLOCK) — Schema rejection at exact JSON Pointer + walk-every-nested-block.** New AC-45 walks the schema asserting `additionalProperties: false` at every `type:object` node. New AC-46 parametrizes over 4 injection sites including the `framework: "playwright"` rejection (which proves AC-41 enum closure).

10. **TQ-8 / CV-8 (BLOCK) — Two-run byte-equal determinism.** TestInventoryProbe is highly nondeterminism-exposed (single `os.walk`, dict iteration over framework map, glob over `coverage/`, `scripts/smoke.*` glob). New AC-48 mtime-shuffles all inputs and asserts `json.dumps(s1, sort_keys=True) == json.dumps(s2, sort_keys=True)`. Forces `os.walk(topdown=True)` with `sorted(dirs)` + `sorted(files)`; `commands` alpha-sorted; `_FRAMEWORK_DETECTORS` iteration deterministic.

11. **CN-4 (HIGH) — `package.json` typed-exception routing.** New AC-37 parametrizes over `SizeCapExceeded`, `MalformedJSONError`, `SymlinkRefusedError`. All three route into `ProbeOutput.errors` with `package_json.*` IDs from `_ERROR_IDS`; the probe still emits a minimal slice (zero file count, empty commands, four-state `coverage_data` with `present=False`).

12. **CV-4 (BLOCK) — Memo allowlist enforcement (ADR-0002).** New AC-36 asserts `ctx.parsed_manifest` is called ONLY with paths whose `.name == "package.json"`. Catches a future drift where a developer adds `ctx.parsed_manifest(tsconfig.json)` — which would be a Phase-1 ADR-0002 contract violation.

13. **CV-5 (BLOCK) — `confidence` field NOT in `TestInventorySlice`.** New AC-47 pins the schema rejection of `confidence: "high"` at slice root. Distinguishes "TestInventory has no confidence semantics in Phase 1" (intentional design) from "missing confidence is a bug."

14. **DP-1 (BLOCK) — `_FRAMEWORK_DETECTORS` Open/Closed registry.** Original framework detection was an inline 6-entry dict. New AC-6 + AC-7 lift to two parallel module-level tuples (`_FRAMEWORK_DETECTORS` for unit; `_E2E_FRAMEWORK_DETECTORS` for E2E) with import-time precedence anchors. Adding a future framework (`uvu`, `bun:test`) is one tuple-entry insertion + one schema enum bump + one fixture row.

15. **DP-2 (BLOCK) — `_LCOV_PREFIX_MAP` dispatch registry.** Original scanner used inline `if line.startswith("SF:") elif ...` chain. New AC-22 lifts to module-level `Mapping[str, str]`. Adding `DA:` (per-line execution counts) is one entry. Catches the bug class where a typo'd `elif` branch silently drops data.

16. **DP-4 (BLOCK) — Kernel reuse: `parsers._io.open_capped`.** The lcov scanner is the 4th consumer of the symlink-refusal + size-cap kernel (after `safe_json`, `safe_yaml`, `jsonc`); rule-of-three threshold decisively met. AC-25 requires the import and AST-walks for the absence of `os.open` / `os.fstat` / `os.close` symbols. Eliminates the symlink-handling-drift class of bug.

17. **DP-5 (BLOCK) — `_NOISE_DIRS` import, not duplicate.** Original story said "if not exported, mirror with TODO." `language_detection._SKIP_DIRS` is private but stable. New AC-15 requires `from codegenie.probes.language_detection import _SKIP_DIRS as _NOISE_DIRS` (single-line alias) with object-identity assertion `is _SKIP_DIRS`. Drift-proof.

18. **DP-6 (BLOCK) — Seven pure helpers (functional core / imperative shell).** New AC-50 requires 7 pure helpers each with table-driven unit tests. Mirrors S4-02's 8-helper structure (one fewer because raw-manifest extraction was deeper than any TestInventory sub-step).

19. **DP-7 (HARDEN) — `CoverageBlock` TypedDict + `LcovTotals` NamedTuple.** AC-23 + AC-30 pin both shapes. `mypy --strict` catches missing-field constructions; pure dict access becomes a type error at slice-construction sites.

20. **DP-8 (HARDEN) — Constant tuples for canonical lists.** New AC-17 (`_CANONICAL_SCRIPT_NAMES`), AC-13 (`_TEST_FILE_PATTERNS`), AC-20 (`_SMOKE_PATH_PRECEDENCE`). Each is one tuple-entry insertion to extend.

## Design-pattern lifts elevated to ACs (Open/Closed at file boundary)

The rule-of-three threshold is decisively met for the kernel-reuse pattern (S4-03 is the 4th consumer of `parsers._io.open_capped`) and the precedence-tuple-registry pattern (4 sibling probes now share the shape). Mirrors `node_build_system.py:104-263` and S4-01-hardened / S4-02-hardened shapes verbatim.

- **AC-6 / AC-7 — `_FRAMEWORK_DETECTORS` + `_E2E_FRAMEWORK_DETECTORS` precedence tuples.** Import-time anchors `_FRAMEWORK_DETECTORS[0] == "vitest"`, `_E2E_FRAMEWORK_DETECTORS == ("playwright","cypress")`. (DP-1)
- **AC-17 — `_CANONICAL_SCRIPT_NAMES: Final[tuple[str, ...]]`** with import-time 6-entry anchor. (DP-8)
- **AC-13 — `_TEST_FILE_PATTERNS: Final[tuple[str, ...]]`** for `.test.{ext}` / `.spec.{ext}`. (DP-8)
- **AC-20 — `_SMOKE_PATH_PRECEDENCE: Final[tuple[str, ...]]`** with precedence anchor `_SMOKE_PATH_PRECEDENCE[0] == "scripts/smoke.sh"`. (DP-8)
- **AC-22 — `_LCOV_PREFIX_MAP: Final[Mapping[str, str]]`** with import-time 6-entry anchor. (DP-2)
- **AC-23 — `LcovTotals = NamedTuple`** as the scanner's return shape. (DP-7)
- **AC-30 — `CoverageBlock = TypedDict`** as the slice's nested shape. (DP-7)
- **AC-25 — Kernel reuse of `parsers._io.open_capped`** in `_lcov_scanner.py`. (DP-4)
- **AC-15 — `_NOISE_DIRS = _SKIP_DIRS` object-identity import.** (DP-5)
- **AC-42 / AC-43 — `_WARNING_IDS` / `_ERROR_IDS` frozensets** with import-time ADR-0007 loop (AC-44). (DP-5 / CN-3 / TQ-12)
- **AC-50 — Seven pure helpers extracted** (`_engines_at_least`, `_select_framework`, `_select_e2e_framework`, `_count_test_files`, `_select_smoke_path`, `_extract_canonical_scripts`, `_classify_node_test`). Functional core / imperative shell. (DP-6)

## Patterns DELIBERATELY deferred (premature-abstraction guard — Rule 2)

Documented in story Notes:

- **`TestFrameworkDetector` ABC + plugin discovery** — defer to Phase 2+ if a fourth probe consumes the same precedence-tuple shape.
- **Shared `probes/_walking.py` for `_SKIP_DIRS`** — alias-import suffices in Phase 1; lift when Phase-2's `IndexHealthProbe` becomes the 4th consumer.
- **Shared `probes/_warning_ids.py`** — per-probe frozenset suffices; lift in S5/S6 (rule-of-three threshold met but deferred for parity with S4-02's deferral).
- **`FrameworkName` `NewType`** — `Literal` arm suffices in Phase 1; lift if a cross-module helper needs to type-narrow.
- **Discriminated-union `_ScanOutcome` (`_ScanSuccess | _ScanFailure`)** — `LcovTotals` NamedTuple + propagating typed exception suffices in Phase 1.
- **`open_capped_lines(path, max_bytes)` streaming primitive** — 50 MB in-memory allocation is fine inside `timeout_seconds=10`; add the streaming variant if a Phase 2 consumer demands it.
- **`uvu` / `bun:test` framework arms** — out-of-scope for Phase 1; canonical extension example documented in Notes.

## Conflict resolutions surfaced (per Rule 7)

- **Arch line 570 (`coverage_data.present: false`) vs arch line 757 (`CoverageBlock | None`) — CN-2.** Validator priority: Consistency wins, and within Consistency, the failure-mode spec wins over the type signature. Probe always emits `CoverageBlock` when it ran; `None` reserved as escape hatch.
- **Arch line 751 `framework` Literal arm includes `playwright,cypress` vs arch line 756 separate `e2e_framework` — CN-1.** Phase 1 probe routes E2E exclusively to `e2e_framework`. The `framework`-arm inclusion of `playwright`/`cypress` is documented as the migration-period escape hatch; arch-doc Literal pruning flagged for follow-up.
- **`@pytest.mark.asyncio` vs sibling `asyncio.run` — TQ-2.** Sibling wins per Rule 11; no `pytest-asyncio` in declared dev-deps; matches S2-02 / S4-01 / S4-02 hardened precedent.
- **Scanner-raises vs probe-handles for `SizeCapExceeded` — TQ-3.** Both correct at different layers. Scanner raises (`pytest.raises(SizeCapExceeded)`); probe catches into the four-state `coverage_data` matrix. Two layers, two contracts; both tested (AC-25 scanner-level + AC-31 probe-level).
- **`framework_map` inline dict vs `_FRAMEWORK_DETECTORS` registry — DP-1.** Original story argued "framework-detection loop is dict iteration — keep it as-is." Per Rule 7 (S4-01 / S4-02 precedent + rule-of-three threshold), registry wins. Adding a future framework must be one tuple-entry insertion; the inline dict locks editors out of the kernel.

## Departures from arch surfaced (per Rule 7)

- **Arch line 757 `coverage_data: CoverageBlock | None`** — story honors `None`-as-escape-hatch but Phase-1 probe never emits `None`. Arch-doc may want to tighten to `CoverageBlock` (no `None`) — flagged for follow-up.
- **Arch line 751 `framework` Literal includes `playwright,cypress`** — story routes them to `e2e_framework` exclusively per arch line 756 + 570. Arch-doc Literal arm pruning flagged.
- **Cross-slice `unit_test_command` (CISlice line 728) vs `commands["test:unit"]` (TestInventorySlice line 754)** — asymmetric capture. CI captures one verbatim command; TestInventory captures all 6 canonical scripts. Consumer convention documented in Notes; no story change needed.

## Context Brief (Stage 1)

**Story intent.** Lands `TestInventoryProbe` — the fifth new Phase 1 probe and the last in Step 4. Populates `test_inventory` slice (arch lines 749–758) from `package.json#devDependencies` (unit framework + E2E framework, two parallel registries), `os.walk` over the repo (test-file count with noise-dir exclusion), `package.json#scripts` (6 canonical script names captured verbatim), filesystem existence checks (`scripts/smoke.{sh,js,ts}`, `tests/smoke/`), and `coverage/lcov.info` parsed by a stdlib state-machine scanner that REUSES `parsers._io.open_capped`. No regex over file bytes; no `lcov-parse` dep; no test-runner invocation. The load-bearing security pin is the byte-budget fuzz assertion on the scanner (`bytes_scanned/elapsed_s >= 5_000_000`) plus AST-walk verification of zero `re` imports.

**Phase-1 exit criteria the story must satisfy.** ADR-0002 (memo allowlist enforcement — Phase 1 = `{"package.json"}`), ADR-0004 (sub-schema `additionalProperties: false` at root + every nested), ADR-0007 (warning-ID pattern; `_WARNING_IDS` + `_ERROR_IDS` frozensets + import-time loop), ADR-0009 (no new C-extension parser deps — no `lcov-parse`, no `coverage-parser`), ADR-0010 (envelope-level optionality), production ADR-0005 (no LLM in gather; scripts captured verbatim). Phase-0 chokepoints (`base.py`, `registry.py`, sanitizer, coordinator) untouched — extension by addition.

**Load-bearing constraints from arch.** Component design #7 (lines 557–570) prescribes the 5-piece probe shape; data model (lines 749–758) pins `TestInventorySlice` including the separate `e2e_framework` field; failure behaviour (line 570) is authoritative on `coverage_data` slice-emission semantics; component design #8 (lines 572–596) provides the `open_capped` kernel the scanner MUST reuse.

**Sibling patterns to mirror.** `src/codegenie/probes/node_build_system.py` (S2-02 hardened) — `_LOCKFILE_PRECEDENCE`, `_BUNDLERS_SORTED`, `_BERRY_MARKERS` precedence-tuples; `_WARNING_IDS` + `_ERROR_IDS` frozensets + `_ID_PATTERN` import-time loop; pure-helper extraction; `asyncio.run` test harness; `isinstance(declared_inputs, list)` contract-attributes test. Plus S4-01 (CIProbe hardened) and S4-02 (DeploymentProbe hardened) dispatch-registry + sentinel-exfiltration discipline. Plus `src/codegenie/parsers/_io.py:open_capped` (the kernel S4-03 reuses).

## Critic reports (Stage 2 — condensed)

### Coverage critic — Verdict: HARDEN

13 findings (10 block, 3 harden). Highlights:
- CV-1 [BLOCK]: `e2e_framework` field completely unaddressed — major slice-coverage gap.
- CV-2 [BLOCK]: `coverage_data` four-state matrix not pinned.
- CV-3 [BLOCK]: Framework × E2E framework orthogonality not tested.
- CV-4 [BLOCK]: Memo allowlist enforcement (ADR-0002 line 47) not pinned.
- CV-5 [BLOCK]: `confidence` field structural-rejection test missing (TestInventorySlice has no confidence semantics).
- CV-6 [BLOCK]: Registry membership across languages not parametrized.
- CV-7 [BLOCK]: Schema rejection at exact JSON Pointer + walk-every-nested-block missing.
- CV-8 [BLOCK]: Two-run byte-equal determinism missing.
- CV-9 [BLOCK]: `package.json` typed-exception routing into `ProbeOutput.errors` unaddressed.
- CV-10 [BLOCK]: lcov-dialect tolerance matrix (Istanbul vs lcov-1.x vs lcov-2.x) missing.
- CV-11 [HARDEN]: `_engines_at_least` strictly-conservative behaviour not pinned.
- CV-12 [HARDEN]: `unit_test_count_is_file_count: True` invariant across all tests not pinned as parametrized invariant.
- CV-13 [HARDEN]: `commands` dict ordering not pinned (determinism).

### Test-Quality critic — Verdict: HARDEN

14 findings (8 block, 6 harden). Highlights:
- TQ-1 [BLOCK]: Test-helper preamble undefined.
- TQ-2 [BLOCK]: `@pytest.mark.asyncio` vs sibling `asyncio.run` (Rule 11).
- TQ-3 [BLOCK / SECURITY]: Wall-clock fuzz assertion flaky; byte-budget needed.
- TQ-4 [BLOCK / SECURITY]: Symlink-to-coverage test missing; sentinel-style needed.
- TQ-5 [BLOCK]: Contract-attributes test missing (S2-02 frozen-ABC regression).
- TQ-6 [BLOCK]: Registry membership test missing.
- TQ-7 [BLOCK]: Schema rejection test missing despite AC.
- TQ-8 [BLOCK]: Two-run determinism test missing.
- TQ-9 [HARDEN]: `e2e_framework.ambiguous` warning case missing.
- TQ-10 [HARDEN]: `test_framework.ambiguous` only checked in one scenario.
- TQ-11 [HARDEN]: AST-walk tests for "regex-free" and "kernel-reuse" not implemented.
- TQ-12 [HARDEN]: `_WARNING_IDS` frozenset not enforced.
- TQ-13 [HARDEN]: lcov happy-path test thin — only one dialect tested.
- TQ-14 [HARDEN]: Memo `MagicMock` test doesn't enforce path-name on all calls.

### Consistency critic — Verdict: HARDEN

8 findings (3 critical, 2 high, 2 medium, 1 info). Highlights:
- CN-1 [CRITICAL]: `e2e_framework` slice field unaddressed; arch line 756 ignored.
- CN-2 [CRITICAL]: `coverage_data: CoverageBlock | None` vs `coverage_data.present: false` contradiction.
- CN-3 [CRITICAL]: `_WARNING_IDS` / `_ERROR_IDS` frozenset + ADR-0007 pattern loop missing (structural defense).
- CN-4 [HIGH]: `package.json` typed-exception routing (errors vs warnings) unaddressed.
- CN-5 [HIGH]: `confidence` field structural rejection not pinned.
- CN-6 [MEDIUM]: `_NOISE_DIRS` import vs local duplication: original story permits either; tighten to alias-import.
- CN-7 [MEDIUM]: Memo allowlist enforcement (ADR-0002) not pinned.
- CN-8 [INFO]: `unit_test_command` (CISlice) vs `commands["test:unit"]` (TestInventorySlice) cross-slice asymmetry — consumer convention documented.

### Design-Patterns critic — Verdict: HARDEN

10 findings (5 block, 4 harden, 1 nit). Highlights:
- DP-1 [BLOCK]: `_FRAMEWORK_DETECTORS` Open/Closed registry replaces inline dict; `_E2E_FRAMEWORK_DETECTORS` parallel.
- DP-2 [BLOCK]: `_LCOV_PREFIX_MAP` dispatch registry replaces inline `elif` chain.
- DP-3 [BLOCK]: Two-run determinism (functional core / imperative shell discipline forces it).
- DP-4 [BLOCK]: Kernel reuse — `parsers._io.open_capped` (rule-of-three threshold met).
- DP-5 [BLOCK]: `_NOISE_DIRS` import (DP discipline at module boundary).
- DP-6 [HARDEN]: Seven pure helpers extracted (functional core / imperative shell).
- DP-7 [HARDEN]: `LcovTotals` NamedTuple + `CoverageBlock` TypedDict.
- DP-8 [HARDEN]: Module-level tuples for canonical lists.
- DP-9 [HARDEN]: Reuse `_demote` / `_CONFIDENCE_RANK` — NOT needed; TestInventorySlice has no confidence.
- DP-10 [NIT]: `FrameworkName` NewType — deferred per Rule 2.

## Final stats

- ACs: 10 → **57** (one observable per AC; all individually-verifiable)
- TDD tests: 7 → **~38** (most parametrized; explicit `asyncio.run` preamble; AST-walked import check; symlink sentinel-exfiltration; schema-walk + JSON-Pointer rejection; byte-budget fuzz; framework × E2E orthogonality matrix; lcov-dialect tolerance matrix; pure-helper unit tests)
- New typed warning IDs added: 1 (`e2e_framework.ambiguous`); total now 4.
- New typed error IDs: 3 (`package_json.size_cap_exceeded`, `package_json.malformed`, `package_json.symlink_refused`).
- New module-level Open/Closed seams: 10 (`_FRAMEWORK_DETECTORS`, `_E2E_FRAMEWORK_DETECTORS`, `_CANONICAL_SCRIPT_NAMES`, `_TEST_FILE_PATTERNS`, `_SMOKE_PATH_PRECEDENCE`, `_LCOV_PREFIX_MAP`, `_LCOV_MAX_BYTES`, `_WARNING_IDS`, `_ERROR_IDS`, `_ID_PATTERN`).
- Pure helpers required: 7 (functional core / imperative shell; one fewer than S4-02 because lcov scanning is delegated to its own module).
- TypedDicts / NamedTuples at slice boundary: 2 (`CoverageBlock` TypedDict, `LcovTotals` NamedTuple).
- Critical contradictions resolved: 3 (CN-1 `e2e_framework` unaddressed; CN-2 `coverage_data` shape; CN-3 structural ADR-0007 defense).
- Block-tier internal contradictions resolved: 4 (TQ-1 / TQ-2 / TQ-3 / TQ-4 — all repeats from prior story validations).
- Arch-doc drifts flagged for follow-up: 2 (arch line 757 `| None` retention; arch line 751 `framework`-arm `playwright,cypress` inclusion).
- Kernel reuse threshold crossed: 4th consumer of `parsers._io.open_capped` (`safe_json`, `safe_yaml`, `jsonc`, now `_lcov_scanner`) — kernel-reuse mandatory per rule-of-three.

## Verdict

**HARDENED.** Story is ready for `phase-story-executor`. All critical contradictions resolved by edit; no `NEEDS RESEARCH` findings; no structural problems requiring RESCUE.
