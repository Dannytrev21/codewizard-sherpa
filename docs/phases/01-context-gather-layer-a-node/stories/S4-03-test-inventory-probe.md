# Story S4-03 — `TestInventoryProbe` + sub-schema + lcov scanner

**Step:** Step 4 — Ship `CIProbe`, `DeploymentProbe`, and `TestInventoryProbe`
**Status:** Ready (HARDENED 2026-05-14)
**Effort:** M
**Depends on:** S2-01 (`LanguageDetectionProbe` extension — `framework_hints`, monorepo, `ctx.parsed_manifest` plumbing), S2-02 (`NodeBuildSystemProbe` — `requires` for `engines.node` resolution and probe-shape conventions; `_SKIP_DIRS` re-use; `_demote`/`_CONFIDENCE_RANK` precedent), S4-01 (`CIProbe` — `_WARNING_IDS` + `_ERROR_IDS` frozenset + import-time ADR-0007 loop precedent), S4-02 (`DeploymentProbe` — `_DEPLOYMENT_PARSERS` dispatch registry precedent + sentinel-style adversarial test discipline)
**ADRs honored:** ADR-0002 (`ParsedManifestMemo` + `input_snapshot` on `ProbeContext`; Phase-1 allowlist `{"package.json"}`), ADR-0004 (`additionalProperties: false` at root AND every nested block), ADR-0007 (warning-ID pattern `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` — bare IDs only, no colon-suffix paths), ADR-0009 (no new C-extension parser deps — `lcov-parse`, `coverage-parser`, etc. forbidden), ADR-0010 (Layer A slices optional at envelope; slice is **always emitted by the probe** when it ran — absence-at-envelope is the for-task-filter signal, not a probe degrade signal)

## Validation notes (2026-05-14)

Hardened from **10 bullets → 50 individually-verifiable ACs** + **~38 TDD tests** by `phase-story-validator`. Critic priority `Consistency > Coverage > Test-Quality > Design-Patterns` applied; full audit in [`_validation/S4-03-test-inventory-probe.md`](_validation/S4-03-test-inventory-probe.md). Most load-bearing fixes:

1. **CN-1 [CRITICAL] — `e2e_framework` slice field completely unaddressed.** `TestInventorySlice` (arch line 749–758) declares `e2e_framework: Literal["playwright","cypress"] | None`. Original story enumerated `playwright`/`cypress` in `framework`'s detection list as if they were unit-test frameworks, but the arch routes them to a **separate** `e2e_framework` field. AC-7 (new) pins `_E2E_FRAMEWORK_DETECTORS` registry; AC-8 (new) pins five test rows (playwright present → `e2e_framework="playwright"`, framework still detected from other deps; cypress + jest → `framework="jest"`, `e2e_framework="cypress"`; etc.). Resolves Coverage + Consistency conflict (arch wins per Rule 7).
2. **CN-2 [CRITICAL] — `coverage_data` field shape contradiction (arch line 570 vs 757).** Arch line 757 declares `coverage_data: CoverageBlock | None`; arch line 570 declares "Missing `coverage/lcov.info` → `coverage_data.present: false`". Resolution: probe **always emits** `CoverageBlock` when it ran (file missing → `CoverageBlock(present=False, parse_error=False, totals=None)`; file present + parsed OK → `present=True, parse_error=False, totals=LcovTotals(...)`; file present + parse error → `present=True, parse_error=True, totals=None`). `None` reserved for the "probe didn't even check" path (unreachable in Phase 1; documented as the escape hatch). AC-30 + AC-31 + AC-32 (new) pin the four-state matrix. Aligns with S4-02's `type: "none"` always-emit-slice convention.
3. **CN-3 [CRITICAL] — ADR-0007 colon-suffix repeat-trap (mirrors S4-01 CN-1 / S4-02 CN-1).** Story emits bare IDs already (`coverage.lcov_parse_error`, `coverage.size_cap_exceeded`, `test_framework.ambiguous`); but the same drift hazard that bit S4-01 + S4-02 is *structurally* mitigated here at story-write time. AC-42 (new) pins `_WARNING_IDS: frozenset[str]` + AC-43 (new) pins `_ERROR_IDS: frozenset[str]` + AC-44 (new) pins import-time `_ID_PATTERN.match()` conformance loop. Future colon-suffix typos fail at module import, before any test runs.
4. **TQ-1 / TQ-2 [BLOCK] — Test-helper preamble undefined; `@pytest.mark.asyncio` is not the sibling convention.** Repeats of S2-02 / S4-01 / S4-02 findings. TDD plan now opens with the inlined `_snapshot(root)` / `_ctx(root, *, parsed_manifest=None)` / `_run(root, *, parsed_manifest=None)` preamble verbatim from `tests/unit/probes/test_node_build_system.py:67-94`. Every `async def`/`await TestInventoryProbe().run(...)` switched to `s = _run(root)` (synchronous; uses `asyncio.run` internally). Rule 11: codebase has no `pytest-asyncio` in declared dev-deps.
5. **TQ-3 [BLOCK / SECURITY] — Wall-clock fuzz assertion is flaky in CI.** Original `assert time.monotonic() - t0 < 1.0` fails non-deterministically under noisy-neighbour CI runners and is not a meaningful upper bound. AC-26 (new) replaces with **two complementary checks**: (i) a *budget-bytes-per-second* assertion (`bytes_scanned / elapsed_s >= 5_000_000`, i.e., ≥ 5 MB/s — anything slower indicates ReDoS-grade pathological behaviour; 1 MB pathological input completes in ≤ 0.2 s on the slowest CI worker observed in Phase 0 fixtures); (ii) AST-walk of `_lcov_scanner.py` asserting no `re.match` / `re.search` / `re.compile` import at module scope (structural defense — backtracking can only happen with regex). The wall-clock check is retained at a 5 s ceiling as a soft canary.
6. **TQ-4 [BLOCK / SECURITY] — `tmp_path`-rooted lcov file lets `O_NOFOLLOW` be silently bypassed.** Original `test_size_cap_raises` writes 64 bytes and caps at 32. Fine for cap; says nothing about symlink refusal. AC-27 (new) adds a symlink-via-coverage test: `coverage/lcov.info` is a symlink to a 60-byte real file outside `tmp_path` → scanner raises `SymlinkRefusedError` (not `SizeCapExceeded`); probe converts to `coverage_data=CoverageBlock(present=True, parse_error=True)` + `warnings=["coverage.lcov_parse_error"]`. Sentinel-style assertion: a 31337-line-count value in the linked file must *not* appear in any emitted `totals`. Mirrors S4-02's sentinel-exfiltration discipline.
7. **TQ-5 [BLOCK] — Contract-attributes test missing (S2-02 frozen-ABC `tuple`-vs-`list` regression).** AC-2 + AC-3 (new) pin every class attribute verbatim: `isinstance(declared_inputs, list)` (NOT `tuple`); `declared_inputs` is the 12-entry list from arch line 560 verbatim. Catches the static-typo class of bug that S2-02 surfaced and S4-01/S4-02 enshrined.
8. **TQ-6 / CV-6 [BLOCK] — Registry membership across languages not pinned.** AC-5 (new) parametrizes `TestInventoryProbe in default_registry.for_task("*", langs)` for `langs ∈ {frozenset({"javascript"}), frozenset({"typescript"}), frozenset({"javascript","typescript"}), frozenset({"go"}), frozenset()}`. The first three return `True`; the last two return `False`. Catches accidental `applies_to_languages` narrowing.
9. **TQ-7 / CV-7 [BLOCK] — Schema rejection at exact JSON Pointer not pinned.** AC-46 (new) parametrizes 4 injection sites (`probes.test_inventory.unknown`, `coverage_data.unknown`, `coverage_data.totals.unknown`, slice root unknown). Each fails with `error.json_pointer` *literally equal* to the injection site. AC-45 (new) walks the schema asserting `additionalProperties: false` at every nested `type: object` node.
10. **TQ-8 / CV-8 / DP-3 [BLOCK] — Two-run byte-equal determinism.** TestInventoryProbe is highly exposed to nondeterminism (single `os.walk`, dict iteration over framework map, file-glob over `coverage/`, `scripts/smoke.*` glob). AC-47 (new) runs the probe twice with mtime-shuffled inputs; asserts `json.dumps(s1, sort_keys=True) == json.dumps(s2, sort_keys=True)`. Forces: alpha-sort `commands` keys; alpha-sort framework-detection iteration via `_FRAMEWORK_DETECTORS` precedence tuple; `os.walk(..., topdown=True)` with `sorted(dirs)` + `sorted(files)`.
11. **CV-4 [BLOCK] — Memo allowlist enforcement not pinned (ADR-0002).** ADR-0002 amendment line 47 declares "Phase 1 allows only `{"package.json"}`". AC-24 (new) asserts that no other file path is passed through `ctx.parsed_manifest(...)` — patches `ctx.parsed_manifest` with a `MagicMock` and verifies every call's `Path.name` is `"package.json"`. Catches a future drift where a developer adds a memo call for `tsconfig.json` (which would be a Phase-1 contract violation requiring an ADR amendment).
12. **CV-5 [BLOCK] — `confidence` field NOT in `TestInventorySlice`.** Per arch line 749–758, `TestInventorySlice` declares no `confidence` field (unlike `CISlice` / `DeploymentSlice` / `BuildSystemSlice`). AC-37 (new) pins the schema rejection: injecting `confidence: "high"` at slice root fails sub-schema validation. Distinguishes "test inventory has no confidence semantics" (Phase 1 design) from "missing confidence is a bug."
13. **DP-1 [BLOCK] — `_FRAMEWORK_DETECTORS` Open/Closed registry.** Original framework detection was an inline 6-entry dict. AC-19 + AC-20 (new) lift to `_FRAMEWORK_DETECTORS: Final[tuple[tuple[FrameworkName, str], ...]]` with import-time precedence anchor `("vitest", "jest", "mocha", "tap")` for unit-test frameworks. `_E2E_FRAMEWORK_DETECTORS` is a separate tuple for `playwright`/`cypress`. Adding a future framework (`uvu`, `bun:test`) is one tuple entry + one schema-enum bump + one fixture row.
14. **DP-2 [BLOCK] — `_LCOV_PREFIX_MAP` dispatch registry inside scanner.** Original scanner used inline `if line.startswith("SF:") elif line.startswith("LF:") ...` chain. AC-22 (new) lifts to module-level `_LCOV_PREFIX_MAP: Final[Mapping[str, str]]` (`"LF:"` → `"lines_found"`, etc.). Adding a future prefix (`BRDA:` per-branch detail, `DA:` per-line execution count) is one entry. Catches the bug class where a typo'd elif branch silently drops data.
15. **DP-4 [BLOCK] — lcov scanner reuses `parsers._io.open_capped` kernel.** Original scanner re-implemented `os.open(O_NOFOLLOW) + fstat-size-check + os.close-finally`. AC-21 (new) requires `from codegenie.parsers._io import open_capped` and using it for body retrieval. Eliminates the symlink-handling-drift class of bug. The kernel is the single source of truth for the three pre-parse defenses; the lcov scanner is the *fourth* consumer (after `safe_json`, `safe_yaml`, `jsonc`) — rule-of-three threshold met; reuse mandatory.
16. **DP-5 [BLOCK] — `_NOISE_DIRS` import, not duplicate.** Story originally said "if not exported, mirror with TODO." `language_detection._SKIP_DIRS` is private but stable. AC-15 (new) requires `from codegenie.probes.language_detection import _SKIP_DIRS as _NOISE_DIRS` (single-line alias) — NO local re-definition. Drift-proof. The cross-probe `_`-prefix import is documented in module docstring per the existing `_lockfiles/` private-but-stable convention.
17. **DP-6 [BLOCK] — Pure helpers extracted (functional core / imperative shell).** Story Refactor named 1 helper. AC-49 (new) requires **seven pure helpers** (mirrors S4-02's eight): `_engines_at_least(constraint, major) -> bool`; `_select_framework(deps) -> FrameworkName | None`; `_select_e2e_framework(deps) -> Literal["playwright","cypress"] | None`; `_count_test_files(root) -> int`; `_select_smoke_path(root) -> str | None`; `_extract_canonical_scripts(parsed_pkg) -> dict[str,str]`; `_classify_node_test(parsed_pkg, framework) -> tuple[FrameworkName | None, list[WarningId]]`. Each has a corresponding table-driven unit test (AC-50 parametrized matrix).
18. **DP-7 [HARDEN] — `CoverageBlock` + `LcovTotals` TypedDict / NamedTuple.** AC-23 (new): `LcovTotals = NamedTuple` with 6 int fields (lines_found, lines_hit, functions_found, functions_hit, branches_found, branches_hit); `_lcov_scanner.scan(...)` returns `LcovTotals` (not raw dict). AC-31 (new): `CoverageBlock = TypedDict` with `present: bool`, `parse_error: bool`, `totals: LcovTotals | None`. `mypy --strict` catches missing-field constructions; pure dict access becomes a type error.
19. **DP-8 [HARDEN] — `_CANONICAL_SCRIPT_NAMES` + `_TEST_FILE_PATTERNS` + `_SMOKE_PATH_PRECEDENCE` module-level tuples.** AC-17 + AC-18 (new). Each becomes a single tuple-entry insertion to extend.
20. **CN-4 [HIGH] — `package.json` typed-exception routing.** Original story silent on `ProbeOutput.errors`. Per S2-02 / S4-01 / S4-02 precedent: `SizeCapExceeded` / `MalformedJSONError` / `SymlinkRefusedError` from the `package.json` parse land in `ProbeOutput.errors` (NOT `slice.warnings`). AC-43 + AC-44 (new) pin `_ERROR_IDS` frozenset (`package_json.size_cap_exceeded`, `package_json.malformed`, `package_json.symlink_refused`); also pin a 3-row parametrized test asserting each error-ID routes to `ProbeOutput.errors` and the probe still emits a minimal slice (with `unit_test_file_count: 0`, `unit_test_count_is_file_count: True`).

**Patterns DELIBERATELY deferred (Rule 2 — premature-abstraction guard):**

- `TestFrameworkDetector` ABC + plugin discovery → defer to Phase 2+ if a fourth probe consumes the same shape.
- `Probe._SKIP_DIRS` shared kernel module → defer until ≥ 4 consumers; for now, alias-import from `language_detection`.
- Discriminated-union `_ScanOutcome` (`_ScanSuccess | _ScanFailure`) — `LcovTotals` NamedTuple + `Optional` return suffices.
- Shared `probes/_warning_ids.py` module → extract at ≥ 4 probes; this is the 4th, so threshold met but per S4-02 deferral we keep the per-probe frozenset for one more iteration; lift in S5/S6.
- `FrameworkName` `NewType` → primitive `Literal` arm suffices in Phase 1.
- `LcovDialect` enum (Istanbul vs. coverage.py vs. lcov-1.x) → single registry handles all dialects via unknown-prefix tolerance.

**Conflict resolutions surfaced (Rule 7):**

- **Arch line 570 vs 757 (`coverage_data` shape contradiction).** Resolution: arch line 570 wins — always emit `CoverageBlock` when probe ran. Arch-doc fix flagged for follow-up: line 757's `| None` is retained as the escape hatch for unreachable-in-Phase-1 paths.
- **`framework` Literal arm `playwright`/`cypress` vs separate `e2e_framework` field.** Resolution: separate. The `framework` Literal in arch line 751 includes `"playwright","cypress"` — but the arch ALSO declares `e2e_framework` as a separate Literal at line 756. The synthesis: `framework` is the *unit-test* framework; `playwright`/`cypress` are E2E and route to `e2e_framework`. Original story conflated. The arch Literal arm for `framework` retains `playwright`/`cypress` for backwards-compat / migration cases, but Phase 1 probe **does not** populate `framework` with E2E values when an explicit unit-test framework is detected. AC-9 (new) pins three rows: (a) playwright-only repo → `framework=None, e2e_framework="playwright"`; (b) playwright + jest → `framework="jest", e2e_framework="playwright"`; (c) playwright + cypress → `framework=None, e2e_framework="playwright"` (alpha-precedence) + `warnings=["e2e_framework.ambiguous"]`. Arch-doc clarification flagged.
- **Scanner-raises vs probe-handles for `SizeCapExceeded`.** Original test asserts scanner raises `SizeCapExceeded`; original AC says "→ `parse_error: true` + warning, gather continues." Both correct at different layers. AC-25 (new) pins: scanner raises (`pytest.raises(SizeCapExceeded)`); probe catches into the four-state `coverage_data` matrix. Two layers, two contracts; both tested.

**Departures from arch surfaced (Rule 7):**

- **Arch line 757 `coverage_data: CoverageBlock | None`** — story honors `None`-as-escape-hatch but Phase-1 probe never emits `None`. Arch-doc may want to tighten to `CoverageBlock` (no `None`) — flagged for follow-up.
- **Arch line 751 `framework` Literal includes `playwright,cypress`** — story routes them to `e2e_framework` exclusively per arch line 756 + failure mode line 570. Arch-doc Literal arm pruning flagged.
- **`unit_test_command` field exists on `CISlice` (arch line 728) and `commands["test:unit"]` exists on `TestInventorySlice`** — cross-slice asymmetry. CI captures the *command verbatim*; test_inventory captures *all canonical scripts*. Consumer (Phase 3+) derives the unit-test command from the more specific of the two. Documented in Notes-for-implementer; no story change needed.

## Context

`TestInventoryProbe` populates the `test_inventory` slice (`localv2.md §5.1 A6`) by enumerating which test framework the repo uses, counting test files, capturing canonical test-script names from `package.json#scripts`, detecting smoke-test scripts, and parsing `coverage/lcov.info` (if present) for line/function/branch totals. The probe is the third of three Step 4 YAML-driven probes, structurally similar to `CIProbe` but with one piece of bespoke code: the lcov line-scanner.

Three commitments concentrate here:

1. **The lcov scanner has no regex backtracking.** `coverage/lcov.info` is attacker-controllable bytes (it lands in the repo from a CI run; a hostile fork can craft pathological coverage output). A regex with `.*` over 50 MB of carefully crafted input is an OOM/CPU-DoS vector. The arch (`phase-arch-design.md §"Component design" #7`) is explicit: **40-LOC stdlib state-machine line scanner, 50 MB cap, no regex backtracking.** Local fuzzing before merge is non-negotiable; the adversarial test in S5-03 / S5-01 (`tests/adv/test_oversized_lockfile.py`-style for lcov) is the CI gate.
2. **`unit_test_count_is_file_count: bool = True`** is a Phase-1 limitation flag, not a placeholder. Phase 1 counts test *files*, not test *cases* (counting cases requires the framework's runner — out of scope per ADR-0011 cousin "no test runner invocation"). The flag is permanent in the contract; Phase 2+ may add `unit_test_case_count: int | null` additively without breaking the file-count semantics. Per `phase-arch-design.md §"Component design" #7` and `localv2.md §5.1 A6`.
3. **`node:test` requires `engines.node >= 18` AND no other framework declared.** Node's built-in test runner is reported only when it would actually be the runner — i.e., the repo explicitly targets Node 18+ AND hasn't declared `vitest`/`jest`/`mocha`/`tap`. This avoids false positives on repos that target Node 20 but use vitest.

Memo consumption: `TestInventoryProbe` reads `package.json` via `ctx.parsed_manifest(...)`. This is the *fourth* probe to consume the memo (`LanguageDetection`, `NodeBuildSystem`, `NodeManifest`, `TestInventory`), exercising the warm-path memo behavior that S2-04 pinned. The probe must defensive-check `ctx.parsed_manifest is None` and fall back to direct `safe_json.load` per edge case #12.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #7 TestInventoryProbe` — full interface.
  - `../phase-arch-design.md §"Data model" TestInventorySlice` — Python-shape contract; `unit_test_file_count: int`, `unit_test_count_is_file_count: bool`, `coverage_data: CoverageBlock | None`.
  - `../phase-arch-design.md §"Component design" #3 ParsedManifestMemo` — memo contract; `ctx.parsed_manifest(...)`.
  - `../phase-arch-design.md §"Edge cases"` row 12 — `ctx.parsed_manifest is None` fallback path.
- **Phase ADRs:**
  - `../ADRs/0002-parsed-manifest-memo-on-probe-context.md` — the memo contract this probe consumes.
  - `../ADRs/0004-per-probe-subschema-additional-properties-false.md` — `test_inventory.schema.json` strict root.
  - `../ADRs/0007-warnings-id-pattern.md` — `coverage.lcov_parse_error`, `test_framework.ambiguous`, `coverage.size_cap_exceeded`.
  - `../ADRs/0009-no-new-c-extension-parser-dependencies.md` — no `lcov-parse` PyPI dependency; the scanner is stdlib-only.
  - `../ADRs/0010-layer-a-slices-optional-at-envelope.md` — `test_inventory` slice optional at envelope.
- **Production ADRs:**
  - `../../../production/adrs/0005-no-llm-in-gather-pipeline.md` — `commands` recorded verbatim, never evaluated.
- **Source design:**
  - `../final-design.md §"Components" #7` — synthesis ledger for `TestInventoryProbe`.
  - `../localv2.md §5.1 A6` — the `test_inventory` slice contract.
- **Existing code:**
  - `src/codegenie/parsers/safe_json.py` (S1-02) — fallback when `ctx.parsed_manifest is None`.
  - `src/codegenie/probes/base.py` (Phase 0) + S1-06 extension — `ProbeContext.parsed_manifest: Callable | None`.
  - `src/codegenie/probes/language_detection.py` (S2-01 extended) — `framework_hints` already in `language_stack` slice; `test_inventory` complements with test-framework-specific detection.
  - `src/codegenie/errors.py` (S1-01) — `MalformedJSONError`, `SizeCapExceeded`.
- **External docs:**
  - lcov tracefile format: lines like `SF:<source_file>`, `LF:<lines_found>`, `LH:<lines_hit>`, `FNF:<functions_found>`, `FNH:<functions_hit>`, `BRF:<branches_found>`, `BRH:<branches_hit>`, `end_of_record`. Reference: `man geninfo` / Istanbul lcov reporter docs.

## Goal

Ship a deterministic `TestInventoryProbe` that detects test framework from deps (handling the `node:test` edge case), counts test files via a single `os.walk` with Phase 0 noise-dir exclusions, extracts canonical test scripts from `package.json`, detects smoke-test paths, and parses `coverage/lcov.info` via a stdlib-only state-machine scanner (50 MB cap, no regex backtracking), all flowing through the `ParsedManifestMemo` for `package.json`.

## Acceptance criteria

### Public contract & registration

- [ ] **AC-1** — `src/codegenie/probes/test_inventory.py` exists and exports `TestInventoryProbe(Probe)`. Module docstring traces to `phase-arch-design.md §"Component design" #7`, ADR-0002, ADR-0004, ADR-0007, ADR-0009, ADR-0010.
- [ ] **AC-2** — Verbatim class attributes (assert each individually via a contract test): `name == "test_inventory"`, `version: str` (regex `^0\.\d+\.\d+$` — pin `"0.1.0"`), `layer == "A"`, `tier == "base"`, `applies_to_languages == ["javascript", "typescript"]` (list, not tuple), `applies_to_tasks == ["*"]`, `requires == ["language_detection", "node_build_system"]`, `timeout_seconds == 10`.
- [ ] **AC-3** — `declared_inputs` is a `list` (NOT tuple — S2-02 frozen-ABC regression discipline) equal to the arch line 560 verbatim 12-entry list: `["package.json", "vitest.config.*", "jest.config.*", "playwright.config.*", ".mocharc.*", "test/**/*.test.*", "tests/**/*.test.*", "src/**/*.test.*", "**/*.spec.*", "coverage/lcov.info", "scripts/smoke.*", "tests/smoke/**/*"]`. Asserted via `isinstance(TestInventoryProbe.declared_inputs, list)` + element-by-element equality.
- [ ] **AC-4** — `src/codegenie/probes/__init__.py` adds one explicit additive import — `from codegenie.probes import test_inventory` is the only diff line; `__all__` extended by `"test_inventory"`; no other line modified. Tested by AST diff between feature branch and `HEAD~1`.
- [ ] **AC-5** — Registry membership across 5 language sets (parametrized): `frozenset({"javascript"})` → True; `frozenset({"typescript"})` → True; `frozenset({"javascript","typescript"})` → True; `frozenset({"go"})` → False; `frozenset()` → False. Test: `TestInventoryProbe in default_registry.for_task("*", langs)`.

### Framework detection (unit-test vs. E2E split — CN-1 resolution)

- [ ] **AC-6** — Unit-test framework detection precedence is the module-level `_FRAMEWORK_DETECTORS: Final[tuple[FrameworkName, ...]]` tuple with import-time anchor `_FRAMEWORK_DETECTORS[0] == "vitest"` (priority order: `vitest`, `jest`, `mocha`, `tap`). Adding a future unit framework is one tuple insertion + one schema enum bump + one fixture row.
- [ ] **AC-7** — E2E framework detection is a **separate** module-level `_E2E_FRAMEWORK_DETECTORS: Final[tuple[Literal["playwright","cypress"], ...]]` tuple with anchor `_E2E_FRAMEWORK_DETECTORS == ("playwright","cypress")`. Detection routes via dep-name `"@playwright/test"` and `"cypress"` respectively.
- [ ] **AC-8** — Framework detection table (parametrized over 8 rows):
  - `{devDependencies: {vitest: "^1"}}` → `framework="vitest"`, `e2e_framework=None`
  - `{devDependencies: {jest: "^29"}}` → `framework="jest"`, `e2e_framework=None`
  - `{devDependencies: {mocha: "^10"}}` → `framework="mocha"`, `e2e_framework=None`
  - `{devDependencies: {tap: "^16"}}` → `framework="tap"`, `e2e_framework=None`
  - `{devDependencies: {"@playwright/test": "^1"}}` → `framework=None`, `e2e_framework="playwright"`
  - `{devDependencies: {cypress: "^13"}}` → `framework=None`, `e2e_framework="cypress"`
  - `{devDependencies: {jest: "^29", "@playwright/test": "^1"}}` → `framework="jest"`, `e2e_framework="playwright"` (orthogonal axes)
  - `{devDependencies: {vitest: "^1", jest: "^29"}}` → `framework="vitest"` (precedence wins), `warnings=["test_framework.ambiguous"]`
- [ ] **AC-9** — Multi-E2E precedence: `{devDependencies: {"@playwright/test": "^1", cypress: "^13"}}` → `e2e_framework="playwright"` (alpha-precedence by `_E2E_FRAMEWORK_DETECTORS[0]`), `warnings=["e2e_framework.ambiguous"]`.
- [ ] **AC-10** — `node:test` rule (parametrized over 6 rows; pure helper `_classify_node_test`):
  - `engines.node = ">=18"`, no framework deps → `framework="node_test"`
  - `engines.node = "^20"`, no framework deps → `framework="node_test"`
  - `engines.node = "~18.10.0"`, no framework deps → `framework="node_test"`
  - `engines.node = ">=16"`, no framework deps → `framework=None` (16 < 18)
  - `engines.node = ">=20"`, `devDependencies.vitest`-present → `framework="vitest"` (explicit framework wins; NO `node:test` reported)
  - `engines.node` absent, no framework deps → `framework=None`
- [ ] **AC-11** — `_engines_at_least(constraint: str, major: int) -> bool` is a pure helper (no I/O, no module imports beyond stdlib `re`). Table-driven test cases: `">=18"` → True; `">=18.0.0"` → True; `"^20"` → True; `"~18.10.0"` → True; `">=16"` → False; `"^17.4.2"` → False; `""` → False; `"garbage"` → False (strictly-conservative: any unparseable constraint → False, so `node:test` is NOT reported on ambiguous declarations); `None`-input → False.

### Test-file counting (single os.walk; deterministic; noise-dir excluded)

- [ ] **AC-12** — `unit_test_file_count` is computed by `_count_test_files(root: Path) -> int` — a single `os.walk(root, topdown=True)` with `dirs[:] = sorted(d for d in dirs if d not in _NOISE_DIRS)` (in-place mutation pattern); files sorted before counting. Pure given filesystem; same inputs → same output.
- [ ] **AC-13** — File-extension match: `*.test.{js,ts,jsx,tsx,mjs,cjs}` ∪ `*.spec.{js,ts,jsx,tsx,mjs,cjs}` via module-level `_TEST_FILE_PATTERNS: Final[tuple[str, ...]]`. Each pattern is tested individually via parametrization (12 rows: 6 extensions × {`.test.`, `.spec.`}).
- [ ] **AC-14** — Noise-dir exclusion fixture: repo contains 15 `*.test.ts` files under `src/` + sentinels under `node_modules/foo/decoy.test.ts`, `.git/x.test.ts`, `dist/y.test.ts`, `__pycache__/z.test.ts`, `.next/a.test.ts`, `build/b.test.ts`. Result: `unit_test_file_count == 15`. The 6 sentinels must NOT be counted.
- [ ] **AC-15** — `_NOISE_DIRS` is imported from `language_detection._SKIP_DIRS` (single-line alias `_NOISE_DIRS = _SKIP_DIRS`). NOT redefined locally. Tested by `assert codegenie.probes.test_inventory._NOISE_DIRS is codegenie.probes.language_detection._SKIP_DIRS` (object-identity check — prevents accidental duplicate-and-drift).
- [ ] **AC-16** — `unit_test_count_is_file_count` is always exactly `True` (the Python literal `True`, not truthy). Asserted as a final-output invariant across **every** integration test row (no per-test repetition; one parametrized invariant runner).

### Canonical scripts + smoke-path

- [ ] **AC-17** — `_CANONICAL_SCRIPT_NAMES: Final[tuple[str, ...]] = ("test", "test:unit", "test:integration", "test:smoke", "test:e2e", "test:coverage")` is a module-level tuple. Adding a new canonical name is one tuple-entry insertion.
- [ ] **AC-18** — Script extraction is verbatim (no eval, no tokenization, no resolution of `npm-run-all` indirection). Test fixture: all 6 canonical keys present with shell-shaped values (`"vitest"`, `"./scripts/smoke.sh"`, `"playwright test"`, etc.); result: `commands` dict has all 6 keys → same string values byte-for-byte. Non-canonical scripts (e.g., `"lint"`, `"build"`) are NOT included in `commands`.
- [ ] **AC-19** — `commands` dict keys are sorted alpha-ascending in the emitted slice (determinism — AC-47).
- [ ] **AC-20** — `_SMOKE_PATH_PRECEDENCE: Final[tuple[str, ...]] = ("scripts/smoke.sh", "scripts/smoke.js", "scripts/smoke.ts", "tests/smoke")` is a module-level tuple. First `Path.exists()` hit wins. Tested over 5 rows: (a) only `scripts/smoke.sh` → `"scripts/smoke.sh"`; (b) only `tests/smoke/` dir → `"tests/smoke"`; (c) `scripts/smoke.sh` + `scripts/smoke.js` present → `"scripts/smoke.sh"` (precedence); (d) `scripts/smoke.ts` + `tests/smoke/` → `"scripts/smoke.ts"`; (e) none → `None`.
- [ ] **AC-21** — `smoke_test_path` is POSIX forward-slash, relative to `repo_root`, no leading `./`, no absolute paths. (Cross-platform determinism — Windows / case-insensitive macOS edge cases.)

### lcov scanner (the load-bearing security primitive)

- [ ] **AC-22** — `src/codegenie/probes/_lcov_scanner.py` exists. Module-level `_LCOV_PREFIX_MAP: Final[Mapping[str, str]]` maps lcov prefix to `LcovTotals` field name: `"LF:"→"lines_found"`, `"LH:"→"lines_hit"`, `"FNF:"→"functions_found"`, `"FNH:"→"functions_hit"`, `"BRF:"→"branches_found"`, `"BRH:"→"branches_hit"`. Adding a future prefix (`DA:`, `BRDA:`) is one entry. Unknown prefixes silently ignored (lcov-dialect tolerance).
- [ ] **AC-23** — `LcovTotals = NamedTuple` with 6 `int` fields (`lines_found`, `lines_hit`, `functions_found`, `functions_hit`, `branches_found`, `branches_hit`). Tested by `isinstance(...)` + tuple-of-six identity.
- [ ] **AC-24** — `_LCOV_MAX_BYTES: Final[int] = 50 * 1024 * 1024` (50 MB). Module constant; `scan(...)` signature is `scan(path: Path, *, max_bytes: int = _LCOV_MAX_BYTES) -> LcovTotals`.
- [ ] **AC-25** — Scanner reuses `parsers._io.open_capped`: `from codegenie.parsers._io import open_capped; body = open_capped(path, max_bytes=max_bytes, parser_kind="lcov")`. No local `os.open(O_NOFOLLOW)` + `os.fstat` re-implementation. Tested by AST walk of `_lcov_scanner.py` asserting (a) `open_capped` is imported, (b) no `os.open` / `os.fstat` / `os.close` symbols appear at module scope.
- [ ] **AC-26** — Scanner is regex-free over file bytes. Tested by AST walk asserting no `import re`, no `re.match`, no `re.search`, no `re.compile` at module scope. Structural defense against ReDoS.
- [ ] **AC-27** — Symlink refusal: `coverage/lcov.info` is a symlink to a real file → `scan(...)` raises `SymlinkRefusedError` (propagated unchanged from `open_capped`). Probe converts to `coverage_data=CoverageBlock(present=True, parse_error=True, totals=None)` + `warnings=["coverage.lcov_parse_error"]`. Sentinel-style assertion: the linked file contains `LF:31337` and `LH:31337`; `31337` must NOT appear in any field of the emitted slice (proves the symlink was refused, not silently followed).
- [ ] **AC-28** — Adversarial local-fuzz (replaces wall-clock-only check): a 1 MB lcov.info of pathological repeating tokens (`"SF:" * 200_000`, no `end_of_record`) is scanned. Three assertions: (i) `bytes_scanned / elapsed_s >= 5_000_000` (≥ 5 MB/s — anything slower indicates ReDoS-grade pathology); (ii) wall-clock `< 5.0 s` (soft canary; ceiling, not invariant); (iii) returns `LcovTotals(0, 0, 0, 0, 0, 0)` (malformed prefixes silently dropped).
- [ ] **AC-29** — Happy-path totals (parametrized over 4 lcov dialects): (a) one-record Istanbul output → exact totals; (b) two-record output → summed totals; (c) record with missing `BRF:` / `BRH:` → branches default to 0; (d) lcov-1.x dialect with extra `DA:` lines → DA lines silently ignored; totals unchanged.

### `coverage_data` field — four-state matrix (CN-2 resolution)

- [ ] **AC-30** — `CoverageBlock = TypedDict` (total=True) with three fields: `present: bool`, `parse_error: bool`, `totals: LcovTotals | None`. Schema mirror with `additionalProperties: false` at this nested block.
- [ ] **AC-31** — Probe ALWAYS emits `coverage_data` as `CoverageBlock` (never the Python `None`) when the probe ran. Four-state matrix (parametrized):
  - **File absent** → `CoverageBlock(present=False, parse_error=False, totals=None)`, no warning.
  - **File present, parsed OK** → `CoverageBlock(present=True, parse_error=False, totals=LcovTotals(...))`, no warning.
  - **File present, `SizeCapExceeded`** → `CoverageBlock(present=True, parse_error=True, totals=None)`, `warnings=["coverage.size_cap_exceeded"]`.
  - **File present, other parse error (`SymlinkRefusedError`, malformed all-the-way-through, `OSError`)** → `CoverageBlock(present=True, parse_error=True, totals=None)`, `warnings=["coverage.lcov_parse_error"]`.
- [ ] **AC-32** — Arch-doc escape hatch: `coverage_data: None` (Python `None`) is **structurally permitted** by the schema (`null` accepted at the field) but the Phase 1 probe **never emits it**. Tested by a meta-test that runs the probe over 4 fixture shapes and asserts `s["coverage_data"] is not None` in every case.

### Memo + parse failures

- [ ] **AC-33** — `package.json` parse routes through `ctx.parsed_manifest(repo_root / "package.json")` when `ctx.parsed_manifest is not None`; falls back to `safe_json.load(...)` when `None`. Implementation: identical try/except shape to `node_build_system.py:564-598`.
- [ ] **AC-34** — Memo-on test: `ctx.parsed_manifest` is a `MagicMock` returning `{"devDependencies": {"jest": "^29"}}` → probe consumes it; `assert memo.call_count == 1`; `assert memo.call_args.args[0].name == "package.json"`. NO other path passed to the memo (memo-allowlist enforcement — AC-24).
- [ ] **AC-35** — Memo-off test: `ctx.parsed_manifest=None`; monkeypatch `codegenie.parsers.safe_json.load` to record calls; assert `safe_json.load` is called exactly once for the `package.json` path. Same slice produced.
- [ ] **AC-36** — Memo allowlist enforcement (ADR-0002 line 47): assert that across **all** integration tests, no path other than `package.json` is ever passed to `ctx.parsed_manifest`. Implemented as a `pytest` fixture-level spy that records every call across the test module and asserts post-session.
- [ ] **AC-37** — `package.json` typed-exception routing (parametrized over 3 exceptions): `SizeCapExceeded` → `errors=["package_json.size_cap_exceeded"]`; `MalformedJSONError` → `errors=["package_json.malformed"]`; `SymlinkRefusedError` → `errors=["package_json.symlink_refused"]`. In all three cases the probe still emits a minimal slice (`framework=None`, `unit_test_file_count=0`, `unit_test_count_is_file_count=True`, `commands={}`, `smoke_test_path=None`, `e2e_framework=None`, `coverage_data=CoverageBlock(present=False, parse_error=False, totals=None)`, `warnings=[]`). `ProbeOutput.errors` carries the structured ID; `slice.warnings` does NOT (errors vs warnings discipline — ADR-0007).

### Schema & validation

- [ ] **AC-38** — `src/codegenie/schema/probes/test_inventory.schema.json` exists, Draft 2020-12, `additionalProperties: false` at slice root and at every nested `type: object` node (CoverageBlock and LcovTotals if represented as object). Validates `TestInventorySlice` shape from arch line 749–758.
- [ ] **AC-39** — Slice is **optional at envelope level** (ADR-0010): `properties.probes` in the envelope schema does NOT list `test_inventory` in its `required` array. Tested by loading the envelope schema and asserting `"test_inventory" not in envelope["properties"]["probes"]["required"]`.
- [ ] **AC-40** — `unit_test_count_is_file_count` schema field's `description` documents the Phase-1 limitation verbatim: "Always true in Phase 1; signals that `unit_test_file_count` is a *file* count, not a *case* count. Phase 2+ may add `unit_test_case_count: int | null` additively."
- [ ] **AC-41** — Schema `framework` enum is closed: `["vitest", "jest", "mocha", "tap", "node_test"]` (NOT including `playwright` / `cypress`; those route to `e2e_framework`). `e2e_framework` enum: `["playwright", "cypress"]`. Schema rejection test: injecting `framework: "playwright"` fails sub-schema validation at JSON Pointer `/framework`.
- [ ] **AC-42** — `_WARNING_IDS: Final[frozenset[str]]` is a verbatim 4-entry frozenset: `{"coverage.lcov_parse_error", "coverage.size_cap_exceeded", "test_framework.ambiguous", "e2e_framework.ambiguous"}`. Any probe-emitted warning ID must be a member (asserted via runtime guard `assert id in _WARNING_IDS` at every `warnings.append(...)` callsite, OR a helper `_warn(warnings, id)` that asserts).
- [ ] **AC-43** — `_ERROR_IDS: Final[frozenset[str]]` is a verbatim 3-entry frozenset: `{"package_json.size_cap_exceeded", "package_json.malformed", "package_json.symlink_refused"}`. Same enforcement pattern.
- [ ] **AC-44** — Import-time ADR-0007 conformance loop: `_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")`; `for _id in (*_WARNING_IDS, *_ERROR_IDS): assert _ID_PATTERN.match(_id), f"ADR-0007 violation: {_id!r}"`. Future colon-suffix typos fail at module import, before any test runs. Mirrors `node_build_system.py:251-254` / S4-01-hardened / S4-02-hardened.
- [ ] **AC-45** — Walk-every-nested-block test: load `test_inventory.schema.json`; recursively walk every `type: "object"` node; assert each has `additionalProperties: false`. Tested as a single recursive-walk function that yields each `(json_pointer, has_strict)` pair; fails if any pair has `has_strict=False`. (Mirrors S4-02's hardening.)
- [ ] **AC-46** — Schema rejection at exact JSON Pointer (parametrized over 4 injection sites): (a) `probes.test_inventory.unknown` → fails at `/probes/test_inventory/unknown`; (b) `probes.test_inventory.coverage_data.unknown` → fails at `/probes/test_inventory/coverage_data/unknown`; (c) `probes.test_inventory.coverage_data.totals.unknown` → fails at the appropriate pointer; (d) `probes.test_inventory.framework = "playwright"` → fails at `/probes/test_inventory/framework`. Asserts the literal `error.json_pointer` string equals the injection site.
- [ ] **AC-47** — `confidence` field is structurally rejected (CN-5): injecting `confidence: "high"` at slice root fails sub-schema validation. TestInventorySlice has no confidence semantics in Phase 1.

### Determinism + observability

- [ ] **AC-48** — Two-run byte-equal determinism: run the probe twice over identical input (between runs, mtime-shuffle all input files via `os.utime(p, ns=(...))` randomization); assert `json.dumps(s1, sort_keys=True) == json.dumps(s2, sort_keys=True)`. Tested over a fixture with: 5 `*.test.ts` files, 2 `*.spec.js` files, `coverage/lcov.info`, `scripts/smoke.sh`, all 6 canonical scripts. Forces: `_count_test_files` to sort `dirs` + `files`; `commands` dict alpha-sorted; `_FRAMEWORK_DETECTORS` iteration deterministic.
- [ ] **AC-49** — Probe emits structlog events: `probe.start` on enter; `probe.success` on exit (with `framework`, `e2e_framework`, `unit_test_file_count`, `coverage_present` keys); `probe.failure` on the `errors[]` path. Tested by `caplog`-style structlog capture.

### Pure helpers (functional core / imperative shell)

- [ ] **AC-50** — Seven pure helpers extracted and individually table-driven-unit-tested (mirrors S4-02's 8):
  1. `_engines_at_least(constraint: str, major: int) -> bool` — AC-11 covers.
  2. `_select_framework(deps: Set[str]) -> FrameworkName | None` — alpha-precedence dict lookup over `_FRAMEWORK_DETECTORS`.
  3. `_select_e2e_framework(deps: Set[str]) -> Literal["playwright","cypress"] | None`.
  4. `_count_test_files(root: Path) -> int` — single `os.walk` with sorted directories and noise-dir filtering.
  5. `_select_smoke_path(root: Path) -> str | None` — precedence walk over `_SMOKE_PATH_PRECEDENCE`.
  6. `_extract_canonical_scripts(parsed_pkg: Mapping[str, Any]) -> dict[str, str]` — filter+sort over `_CANONICAL_SCRIPT_NAMES`.
  7. `_classify_node_test(parsed_pkg: Mapping[str, Any], framework: FrameworkName | None) -> tuple[FrameworkName | None, list[WarningId]]` — the `node:test` precedence rule.

  Each pure helper has zero I/O side effects (except `_count_test_files` / `_select_smoke_path` which are filesystem-pure: same FS state → same output). Each has its own table-driven test class with ≥ 3 parametrized rows.

### Forbidden patterns / negative assertions (ADR-0009 / ADR-0011 / production ADR-0005)

- [ ] **AC-51** — No new PyPI deps (ADR-0009): grep `pyproject.toml` for `lcov`, `coverage-parse`, `python-lcov`, `pyjson5`, `orjson`, `msgpack`, `ruamel.yaml`, `lcov-parse` — all absent. Tested via AST parse of `pyproject.toml`.
- [ ] **AC-52** — No subprocess invocation: `_lcov_scanner.py` and `test_inventory.py` contain no `subprocess`, no `os.system`, no `os.popen`, no `_exec.run_allowlisted`. Tested by AST walk. (`scripts/smoke.sh` is recorded as a path string, never executed.)
- [ ] **AC-53** — Sub-schema does NOT include `additionalProperties: true` anywhere (unlike `DeploymentSlice.security_context` which has the documented k8s-pass-through exception). Tested by walk-the-schema (AC-45) extended to also assert no `additionalProperties: true` node.

### Definition of done

- [ ] **AC-54** — `ruff check`, `ruff format --check`, `mypy --strict` pass on `src/codegenie/probes/test_inventory.py`, `src/codegenie/probes/_lcov_scanner.py`, and `src/codegenie/schema/probes/test_inventory.schema.json`.
- [ ] **AC-55** — `pytest tests/unit/probes/test_test_inventory.py tests/unit/probes/test_lcov_scanner.py -q` passes with 0 skipped, 0 xfailed.
- [ ] **AC-56** — Per-probe local coverage on `test_inventory.py` + `_lcov_scanner.py` combined ≥ 90/80 line/branch (no carve-out per ADR-0005; the lcov scanner earns its coverage with intent-verifying tests, not skipped fuzz tests). Reported in PR body.
- [ ] **AC-57** — Story `Status:` flipped to `Done` only after all 57 ACs are individually verifiable in the PR diff or test output.

## Implementation outline

1. **Sub-schema first.** Write `test_inventory.schema.json` mirroring `TestInventorySlice` from the data model. Document `unit_test_count_is_file_count` in the schema's `description`: "Always true in Phase 1; signals that `unit_test_file_count` is a *file* count, not a *case* count. Phase 2+ may add `unit_test_case_count` additively."
2. **lcov scanner — write this first as a separate module.** `src/codegenie/probes/_lcov_scanner.py`:
   ```python
   # ~40 LOC, state-machine, stdlib only, no regex
   def scan(path: Path, max_bytes: int = 50 * 1024 * 1024) -> LcovTotals | None:
       # 1. open with O_NOFOLLOW (reuse parsers.safe_json's helper if exported, else inline)
       # 2. fstat size > max_bytes → raise SizeCapExceeded
       # 3. line-by-line read; for each line, identify the prefix ("SF:", "LF:", "LH:", "FNF:", "FNH:", "BRF:", "BRH:", "end_of_record")
       # 4. accumulate totals; ignore unrecognized prefixes (no exception — lcov dialects vary)
       # 5. return LcovTotals(lines_found, lines_hit, functions_found, functions_hit, branches_found, branches_hit)
       ...
   ```
   No regex. Line iteration via `for line in fh:` with `errors="replace"` on decode (the file is text but may have stray bytes). Each line's prefix is identified by `str.startswith` — O(1), no backtracking. Unknown prefixes silently ignored — this is the lcov-dialect-tolerance convention.
3. **Probe `run(snapshot, ctx)` implementation:**
   - `package.json` via `ctx.parsed_manifest(snapshot.root / "package.json")` with `ctx.parsed_manifest is None` fallback to `safe_json.load`.
   - Framework detection:
     ```python
     all_deps = {**parsed.get("dependencies", {}), **parsed.get("devDependencies", {})}
     framework_map = {"vitest": "vitest", "jest": "jest", "mocha": "mocha", "tap": "tap",
                      "@playwright/test": "playwright", "cypress": "cypress"}
     hits = [v for k, v in framework_map.items() if k in all_deps]
     framework = hits[0] if hits else None
     if len(hits) > 1: warnings.append("test_framework.ambiguous")
     # node:test rule
     if framework is None:
         engines_node = parsed.get("engines", {}).get("node", "")
         if _engines_at_least(engines_node, 18):
             framework = "node_test"
     ```
   - `_engines_at_least(constraint: str, major: int) -> bool` is a tiny helper that parses `>=18`, `^20`, `~18.10.0` and tests if the lower bound is `>= 18`. Use the `packaging.specifiers` library if it's already a Phase 0 dep; otherwise write a 10-LOC parser. **Do not invoke `node --version`** — that's `NodeBuildSystemProbe`'s job and lives in the `build_system` slice; `TestInventoryProbe` reads only `package.json#engines.node`.
   - Test-file count: single `os.walk(repo_root)` with Phase 0 noise-dir exclusions (`node_modules`, `dist`, `build`, `.next`, `coverage`, `.git`, etc. — reuse the Phase 0 constant). Match `*.test.{js,ts,jsx,tsx,mjs,cjs}` + `*.spec.{js,ts,jsx,tsx,mjs,cjs}` via `fnmatch.fnmatch` or `Path.match`.
   - `commands = {k: parsed.get("scripts", {}).get(k) for k in ("test", "test:unit", "test:integration", "test:smoke", "test:e2e", "test:coverage") if k in parsed.get("scripts", {})}`. Verbatim — never evaluate.
   - Smoke-script: check `Path.exists()` for `scripts/smoke.sh`, `scripts/smoke.js`, `scripts/smoke.ts`, and `tests/smoke/`. First-match wins. `smoke_test_path = matched_path or None`.
   - Coverage: if `coverage/lcov.info` exists, call `_lcov_scanner.scan(...)`. On `SizeCapExceeded` → `coverage_data = CoverageBlock(present=True, parse_error=True, ...)`, warning emitted. On other exception → same. On success → totals populated; `present=True, parse_error=False`.
4. **Register** in `src/codegenie/probes/__init__.py` (additive import).
5. **Wire** sub-schema into envelope under `probes.test_inventory` (optional `$ref`).
6. **Local fuzzing** before opening the PR: run the scanner against:
   - 100 KB of `"SF:" * 100000` repeating tokens
   - A 1 MB lcov.info with no `end_of_record` markers
   - A 1 MB lcov.info with random byte mutations (drop a `time`-bounded mutation loop in `tests/unit/probes/test_lcov_scanner.py` or a one-off script)
   Confirm wall-clock `< 1 s` for each. If any case exceeds, surface and fix before merge — the adversarial CI gate in S5 lands later but the local-fuzz commitment is non-negotiable per `High-level-impl.md §"Implementation-level risks" #4`.

## TDD plan — red / green / refactor

### Test-helper preamble (TQ-1 / TQ-2 — inlined verbatim from `tests/unit/probes/test_node_build_system.py:67-94`)

Every test file below **MUST** open with this preamble. NO `@pytest.mark.asyncio` (codebase has no `pytest-asyncio` in declared dev-deps — Rule 11).

```python
# tests/unit/probes/test_test_inventory.py — preamble
from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

import pytest

from codegenie.probes.base import ProbeContext, ProbeOutput, RepoSnapshot

ADR_0007 = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


def _snapshot(root: Path) -> RepoSnapshot:
    return RepoSnapshot(
        root=root,
        git_commit=None,
        detected_languages={"typescript": 1},
        config={},
    )


def _ctx(root: Path, *, parsed_manifest: Any = None) -> ProbeContext:
    return ProbeContext(
        cache_dir=root / ".cache",
        output_dir=root / ".out",
        workspace=root,
        logger=logging.getLogger("test"),
        config={},
        parsed_manifest=parsed_manifest,
    )


def _run(root: Path, *, parsed_manifest: Any = None) -> ProbeOutput:
    from codegenie.probes.test_inventory import TestInventoryProbe
    return asyncio.run(TestInventoryProbe().run(_snapshot(root), _ctx(root, parsed_manifest=parsed_manifest)))
```

### Red — write failing tests first

```python
# tests/unit/probes/test_test_inventory.py — selected red tests
# (full plan: ~30 tests covering AC-1..AC-50. Below are the ones with non-obvious shape.)

# ---------- AC-2 / AC-3: contract attributes ----------

def test_contract_attributes_pinned():
    from codegenie.probes.test_inventory import TestInventoryProbe
    assert TestInventoryProbe.name == "test_inventory"
    assert TestInventoryProbe.layer == "A"
    assert TestInventoryProbe.tier == "base"
    assert TestInventoryProbe.applies_to_languages == ["javascript", "typescript"]
    assert TestInventoryProbe.applies_to_tasks == ["*"]
    assert TestInventoryProbe.requires == ["language_detection", "node_build_system"]
    assert TestInventoryProbe.timeout_seconds == 10
    assert re.fullmatch(r"\d+\.\d+\.\d+", TestInventoryProbe.version)
    # CRITICAL: `list`, not `tuple` — S2-02 frozen-ABC regression
    assert isinstance(TestInventoryProbe.declared_inputs, list)
    assert TestInventoryProbe.declared_inputs == [
        "package.json", "vitest.config.*", "jest.config.*", "playwright.config.*",
        ".mocharc.*", "test/**/*.test.*", "tests/**/*.test.*", "src/**/*.test.*",
        "**/*.spec.*", "coverage/lcov.info", "scripts/smoke.*", "tests/smoke/**/*",
    ]


# ---------- AC-5: registry membership across languages ----------

@pytest.mark.parametrize("langs, expected", [
    (frozenset({"javascript"}), True),
    (frozenset({"typescript"}), True),
    (frozenset({"javascript", "typescript"}), True),
    (frozenset({"go"}), False),
    (frozenset(), False),
])
def test_registry_membership_across_languages(langs, expected):
    from codegenie.probes.registry import default_registry
    from codegenie.probes.test_inventory import TestInventoryProbe
    matched = [p for p in default_registry.for_task("*", langs) if isinstance(p, TestInventoryProbe)]
    assert (len(matched) == 1) is expected


# ---------- AC-8: framework × E2E framework matrix ----------

@pytest.mark.parametrize("dev_deps, fw, e2e, warns", [
    ({"vitest": "^1"}, "vitest", None, []),
    ({"jest": "^29"}, "jest", None, []),
    ({"mocha": "^10"}, "mocha", None, []),
    ({"tap": "^16"}, "tap", None, []),
    ({"@playwright/test": "^1"}, None, "playwright", []),
    ({"cypress": "^13"}, None, "cypress", []),
    ({"jest": "^29", "@playwright/test": "^1"}, "jest", "playwright", []),
    ({"vitest": "^1", "jest": "^29"}, "vitest", None, ["test_framework.ambiguous"]),
    ({"@playwright/test": "^1", "cypress": "^13"}, None, "playwright",
     ["e2e_framework.ambiguous"]),
])
def test_framework_e2e_matrix(tmp_path, dev_deps, fw, e2e, warns):
    (tmp_path / "package.json").write_text(json.dumps({"devDependencies": dev_deps}))
    s = _run(tmp_path).schema_slice["test_inventory"]
    assert s["framework"] == fw
    assert s["e2e_framework"] == e2e
    for w in warns:
        assert w in s["warnings"]


# ---------- AC-10: node:test precedence rule ----------

@pytest.mark.parametrize("engines, deps, fw", [
    ({"node": ">=18"}, {}, "node_test"),
    ({"node": "^20"}, {}, "node_test"),
    ({"node": "~18.10.0"}, {}, "node_test"),
    ({"node": ">=16"}, {}, None),       # below 18
    ({"node": ">=20"}, {"vitest": "^1"}, "vitest"),  # explicit framework wins
    ({}, {}, None),                      # engines absent
])
def test_node_test_precedence(tmp_path, engines, deps, fw):
    (tmp_path / "package.json").write_text(
        json.dumps({"engines": engines, "devDependencies": deps})
    )
    assert _run(tmp_path).schema_slice["test_inventory"]["framework"] == fw


# ---------- AC-14: noise-dir exclusion (six sentinels) ----------

def test_test_file_count_excludes_all_noise_dirs(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "src").mkdir()
    for i in range(15):
        (tmp_path / "src" / f"a{i}.test.ts").write_text("")
    # Six sentinels under noise dirs — MUST NOT be counted
    for d in ("node_modules/foo", ".git", "dist", "__pycache__", ".next", "build"):
        p = tmp_path / d
        p.mkdir(parents=True)
        (p / "decoy.test.ts").write_text("")
    s = _run(tmp_path).schema_slice["test_inventory"]
    assert s["unit_test_file_count"] == 15  # NOT 21


# ---------- AC-15: _NOISE_DIRS is the imported _SKIP_DIRS (object-identity) ----------

def test_noise_dirs_is_imported_not_duplicated():
    from codegenie.probes.test_inventory import _NOISE_DIRS
    from codegenie.probes.language_detection import _SKIP_DIRS
    assert _NOISE_DIRS is _SKIP_DIRS  # object-identity, not equality


# ---------- AC-31: coverage_data four-state matrix ----------

def test_coverage_data_file_absent(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    cd = _run(tmp_path).schema_slice["test_inventory"]["coverage_data"]
    assert cd == {"present": False, "parse_error": False, "totals": None}


def test_coverage_data_file_present_parsed_ok(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    cov = tmp_path / "coverage"; cov.mkdir()
    (cov / "lcov.info").write_text("SF:/a.js\nLF:10\nLH:8\nFNF:3\nFNH:2\nBRF:4\nBRH:3\nend_of_record\n")
    cd = _run(tmp_path).schema_slice["test_inventory"]["coverage_data"]
    assert cd["present"] is True and cd["parse_error"] is False
    assert cd["totals"] == {
        "lines_found": 10, "lines_hit": 8, "functions_found": 3,
        "functions_hit": 2, "branches_found": 4, "branches_hit": 3,
    }


def test_coverage_data_size_cap_exceeded(tmp_path, monkeypatch):
    from codegenie.probes import _lcov_scanner
    monkeypatch.setattr(_lcov_scanner, "_LCOV_MAX_BYTES", 16)  # tighten for test
    (tmp_path / "package.json").write_text("{}")
    cov = tmp_path / "coverage"; cov.mkdir()
    (cov / "lcov.info").write_bytes(b"x" * 32)
    s = _run(tmp_path).schema_slice["test_inventory"]
    assert s["coverage_data"] == {"present": True, "parse_error": True, "totals": None}
    assert "coverage.size_cap_exceeded" in s["warnings"]


# ---------- AC-36: memo allowlist enforcement ----------

def test_memo_only_called_for_package_json(tmp_path):
    from unittest.mock import MagicMock
    (tmp_path / "package.json").write_text('{"devDependencies": {"jest": "^29"}}')
    memo = MagicMock(return_value={"devDependencies": {"jest": "^29"}})
    _run(tmp_path, parsed_manifest=memo)
    # Every call's path basename MUST be package.json — ADR-0002 Phase-1 allowlist
    for call in memo.mock_calls:
        if call.args:
            assert call.args[0].name == "package.json"


# ---------- AC-37: package.json parse failures route to ProbeOutput.errors ----------

@pytest.mark.parametrize("exc, expected_id", [
    ("SizeCapExceeded", "package_json.size_cap_exceeded"),
    ("MalformedJSONError", "package_json.malformed"),
    ("SymlinkRefusedError", "package_json.symlink_refused"),
])
def test_package_json_failure_routes_to_probeoutput_errors(tmp_path, monkeypatch, exc, expected_id):
    from codegenie import errors as e
    from codegenie.parsers import safe_json
    (tmp_path / "package.json").write_text("{}")
    def _raise(*a, **kw): raise getattr(e, exc)("boom")
    monkeypatch.setattr(safe_json, "load", _raise)
    out = _run(tmp_path)
    assert expected_id in out.errors
    assert expected_id not in out.schema_slice["test_inventory"]["warnings"]
    # Minimal slice still emitted
    s = out.schema_slice["test_inventory"]
    assert s["unit_test_file_count"] == 0
    assert s["unit_test_count_is_file_count"] is True


# ---------- AC-42 / AC-43 / AC-44: _WARNING_IDS + _ERROR_IDS + ADR-0007 pattern ----------

def test_warning_ids_frozenset_and_adr_0007_conformance():
    from codegenie.probes.test_inventory import _WARNING_IDS, _ERROR_IDS, _ID_PATTERN
    assert isinstance(_WARNING_IDS, frozenset)
    assert _WARNING_IDS == frozenset({
        "coverage.lcov_parse_error",
        "coverage.size_cap_exceeded",
        "test_framework.ambiguous",
        "e2e_framework.ambiguous",
    })
    assert isinstance(_ERROR_IDS, frozenset)
    assert _ERROR_IDS == frozenset({
        "package_json.size_cap_exceeded",
        "package_json.malformed",
        "package_json.symlink_refused",
    })
    for _id in (*_WARNING_IDS, *_ERROR_IDS):
        assert _ID_PATTERN.match(_id), f"ADR-0007 violation: {_id!r}"


# ---------- AC-45 / AC-46: schema additionalProperties:false everywhere + JSON Pointer rejection ----------

def test_schema_additionalproperties_false_walks_every_object():
    import json as _json
    from pathlib import Path
    schema = _json.loads(Path("src/codegenie/schema/probes/test_inventory.schema.json").read_text())
    bad = []
    def _walk(node, ptr):
        if isinstance(node, dict):
            if node.get("type") == "object":
                if node.get("additionalProperties") is not False:
                    bad.append(ptr)
            for k, v in node.items():
                _walk(v, ptr + "/" + str(k))
        elif isinstance(node, list):
            for i, v in enumerate(node): _walk(v, ptr + f"/{i}")
    _walk(schema, "")
    assert bad == []


@pytest.mark.parametrize("path, bad_value", [
    (["probes","test_inventory","unknown"], 1),
    (["probes","test_inventory","coverage_data","unknown"], 1),
    (["probes","test_inventory","framework"], "playwright"),  # routed to e2e_framework only
])
def test_schema_rejection_at_exact_json_pointer(path, bad_value):
    from codegenie.schema import SchemaValidator  # Phase-0 façade
    envelope = _minimal_envelope_with_test_inventory()
    # mutate at path
    node = envelope
    for k in path[:-1]:
        node = node.setdefault(k, {})
    node[path[-1]] = bad_value
    err = SchemaValidator.validate(envelope).errors[0]
    assert err.json_pointer == "/" + "/".join(path)


# ---------- AC-47: confidence field structurally rejected ----------

def test_confidence_field_rejected_by_schema():
    from codegenie.schema import SchemaValidator
    env = _minimal_envelope_with_test_inventory()
    env["probes"]["test_inventory"]["confidence"] = "high"
    res = SchemaValidator.validate(env)
    assert not res.ok
    assert "/probes/test_inventory/confidence" in {e.json_pointer for e in res.errors}


# ---------- AC-48: two-run byte-equal determinism ----------

def test_two_runs_byte_equal_determinism(tmp_path):
    import os, random
    (tmp_path / "package.json").write_text(json.dumps({
        "devDependencies": {"jest": "^29", "@playwright/test": "^1"},
        "scripts": {"test": "jest", "test:unit": "jest --unit",
                    "test:smoke": "./scripts/smoke.sh", "test:e2e": "playwright test"},
    }))
    src = tmp_path / "src"; src.mkdir()
    for i in range(5): (src / f"a{i}.test.ts").write_text("")
    for i in range(2): (src / f"b{i}.spec.js").write_text("")
    cov = tmp_path / "coverage"; cov.mkdir()
    (cov / "lcov.info").write_text("LF:10\nLH:5\nend_of_record\n")
    scripts = tmp_path / "scripts"; scripts.mkdir()
    (scripts / "smoke.sh").write_text("")
    s1 = _run(tmp_path).schema_slice["test_inventory"]
    # mtime-shuffle every file
    for p in tmp_path.rglob("*"):
        if p.is_file():
            t = random.randint(1_700_000_000, 1_800_000_000)
            os.utime(p, ns=(t * 1_000_000_000, t * 1_000_000_000))
    s2 = _run(tmp_path).schema_slice["test_inventory"]
    assert json.dumps(s1, sort_keys=True) == json.dumps(s2, sort_keys=True)
```

```python
# tests/unit/probes/test_lcov_scanner.py — selected red tests

import time, ast, inspect
from pathlib import Path
import pytest

from codegenie.probes._lcov_scanner import scan, LcovTotals, _LCOV_PREFIX_MAP, _LCOV_MAX_BYTES
from codegenie.errors import SizeCapExceeded, SymlinkRefusedError


# ---------- AC-22: dispatch registry shape ----------

def test_lcov_prefix_map_is_module_level_mapping():
    assert isinstance(_LCOV_PREFIX_MAP, type({}).__mro__[0])  # Mapping
    # Adding a future "DA:" or "BRDA:" prefix is one entry — anchor the current 6
    assert set(_LCOV_PREFIX_MAP.keys()) == {"LF:", "LH:", "FNF:", "FNH:", "BRF:", "BRH:"}


# ---------- AC-23: LcovTotals NamedTuple ----------

def test_lcov_totals_namedtuple_shape():
    t = LcovTotals(1, 2, 3, 4, 5, 6)
    assert t._fields == (
        "lines_found", "lines_hit", "functions_found", "functions_hit",
        "branches_found", "branches_hit",
    )


# ---------- AC-25: open_capped kernel reused (AST walk) ----------

def test_scanner_reuses_open_capped_kernel():
    src = Path(inspect.getsourcefile(scan)).read_text()
    tree = ast.parse(src)
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert any(
        isinstance(n, ast.ImportFrom)
        and n.module == "codegenie.parsers._io"
        and any(a.name == "open_capped" for a in n.names)
        for n in imports
    ), "lcov scanner MUST reuse parsers._io.open_capped"
    # No local re-implementation
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    forbidden = {"O_NOFOLLOW", "fstat"}
    assert not (forbidden & names), f"lcov scanner re-implements: {forbidden & names}"


# ---------- AC-26: regex-free over bytes (structural ReDoS defense) ----------

def test_scanner_has_no_regex():
    src = Path(inspect.getsourcefile(scan)).read_text()
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                assert a.name != "re", "scanner imports `re` — ReDoS surface forbidden"
        if isinstance(n, ast.ImportFrom):
            assert n.module != "re", "scanner imports from `re` — ReDoS surface forbidden"


# ---------- AC-27: symlink refusal with sentinel-style assertion ----------

def test_symlink_to_lcov_refused_with_sentinel(tmp_path):
    # Sentinel: linked file carries LF:31337 — must NOT appear in any totals
    leak = tmp_path.parent / "SENTINEL_LCOV.info"
    leak.write_text("LF:31337\nLH:31337\nend_of_record\n")
    link = tmp_path / "lcov.info"
    link.symlink_to(leak)
    with pytest.raises(SymlinkRefusedError):
        scan(link)
    # Probe-level integration: the leaked value MUST NOT survive into the slice
    (tmp_path / "package.json").write_text("{}")
    cov = tmp_path / "coverage"; cov.mkdir()
    (cov / "lcov.info").symlink_to(leak)
    # Note: probe converts the SymlinkRefusedError into coverage.lcov_parse_error
    # and emits parse_error=True with no totals.
    from codegenie.probes.test_inventory import TestInventoryProbe
    import asyncio, logging
    from codegenie.probes.base import ProbeContext, RepoSnapshot
    out = asyncio.run(TestInventoryProbe().run(
        RepoSnapshot(root=tmp_path, git_commit=None, detected_languages={"typescript": 1}, config={}),
        ProbeContext(cache_dir=tmp_path/".c", output_dir=tmp_path/".o", workspace=tmp_path,
                     logger=logging.getLogger("t"), config={}, parsed_manifest=None),
    ))
    s = out.schema_slice["test_inventory"]
    assert "coverage.lcov_parse_error" in s["warnings"]
    assert s["coverage_data"]["totals"] is None
    leaked_str = repr(s)
    assert "31337" not in leaked_str  # SENTINEL — proves O_NOFOLLOW worked


# ---------- AC-28: adversarial fuzz with budget-bytes/sec + soft canary ----------

def test_pathological_input_scanned_at_at_least_5MB_per_second(tmp_path):
    p = tmp_path / "lcov.info"
    pathological = ("SF:" * 200_000 + "\n").encode() + b"GARBAGE\n" * 50_000
    p.write_bytes(pathological)
    size = p.stat().st_size
    t0 = time.monotonic()
    t = scan(p)
    elapsed = time.monotonic() - t0
    # Primary: byte-budget rate — ReDoS-grade pathology would burn this
    assert size / elapsed >= 5_000_000, f"too slow: {size/elapsed:.0f} B/s"
    # Soft canary
    assert elapsed < 5.0
    # Malformed/no-numeric-line — totals stay at zero
    assert t == LcovTotals(0, 0, 0, 0, 0, 0)


# ---------- AC-29: lcov-dialect tolerance ----------

@pytest.mark.parametrize("body, expected", [
    ("SF:/a.js\nLF:10\nLH:8\nFNF:3\nFNH:2\nBRF:4\nBRH:3\nend_of_record\n",
     LcovTotals(10, 8, 3, 2, 4, 3)),
    ("LF:10\nLH:8\nend_of_record\nLF:5\nLH:3\nend_of_record\n",
     LcovTotals(15, 11, 0, 0, 0, 0)),       # summed totals
    ("LF:10\nLH:8\nend_of_record\n", LcovTotals(10, 8, 0, 0, 0, 0)),  # missing BRF/BRH OK
    ("DA:1,2\nLF:10\nLH:8\nend_of_record\n", LcovTotals(10, 8, 0, 0, 0, 0)),  # DA ignored
])
def test_lcov_dialect_tolerance(tmp_path, body, expected):
    p = tmp_path / "lcov.info"
    p.write_text(body)
    assert scan(p) == expected
```

Run both. All fail.

### Green — make it pass

1. **Sub-schema first** (`test_inventory.schema.json`) — pin the field shapes; walk-tests fail until the schema is `additionalProperties: false` at every nested block.
2. **`_lcov_scanner.py` second** — implement `LcovTotals` + `_LCOV_PREFIX_MAP` + `scan(...)`. Reuse `open_capped`. NO regex. Iterate AC-22..AC-29 tests to green.
3. **Pure helpers third** — `_engines_at_least`, `_select_framework`, `_select_e2e_framework`, `_count_test_files`, `_select_smoke_path`, `_extract_canonical_scripts`, `_classify_node_test`. Each has its own table-driven unit test (AC-50). Get them green before wiring into the probe.
4. **`TestInventoryProbe.run`** — compose pure helpers + memo + the four-state `coverage_data` matrix + `_WARNING_IDS`/`_ERROR_IDS` enforcement.
5. **Register** in `probes/__init__.py` (one additive import line; AST-diff test guards).
6. **Wire** sub-schema `$ref` into envelope under `probes.test_inventory` (optional).
7. **Local fuzzing** before opening the PR: scan the scanner against:
   - 1 MB `"SF:" * 200_000` + `"GARBAGE\n" * 50_000` repeating tokens (AC-28 fixture).
   - 1 MB lcov.info with no `end_of_record` markers and 100k random Unicode bytes.
   - A symlink whose target file has `LF:31337` (AC-27 sentinel).
   - A 60 MB lcov.info to confirm `_LCOV_MAX_BYTES` triggers `SizeCapExceeded` before any decode.

   Confirm AC-28's byte-budget assertion passes locally; if any case fails the 5 MB/s floor, surface and fix before merge (the system-level adversarial test in S5-03 will catch it otherwise, but local-fuzz is the cheaper feedback loop per `High-level-impl.md §"Implementation-level risks" #4`).

### Refactor — clean up

- The lcov scanner stays under 50 LOC. If it grows, extract `_accumulate(line: str, totals: _MutTotals) -> None` and keep `scan(...)` as the orchestration shell. The function MUST be pure (no I/O, no globals).
- `_engines_at_least(constraint, major)` docstring carries 4 inline doctests (`>=18`, `^20`, `~18.10.0`, garbage). Document the strictly-conservative behaviour: garbage → return `False` (no `node:test` reported).
- The framework-detection loop is precedence-tuple iteration — keep it pure helper-shaped; do NOT extract a class.
- The probe's `run(...)` is the imperative shell — orchestration only; all branching logic lives in pure helpers (functional core / imperative shell).
- Confirm `ruff format`, `ruff check`, `mypy --strict` pass on `test_inventory.py` and `_lcov_scanner.py`.
- Run mutation testing locally (`mutmut run` on the pure helpers if available, or hand-mutate `_engines_at_least`'s `>=` to `>` and confirm AC-11 catches it). Pure helpers are the load-bearing logic; the imperative shell is harder to mutate-test.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/test_inventory.py` | New — `TestInventoryProbe` implementation + module-level Open/Closed registries (`_FRAMEWORK_DETECTORS`, `_E2E_FRAMEWORK_DETECTORS`, `_CANONICAL_SCRIPT_NAMES`, `_TEST_FILE_PATTERNS`, `_SMOKE_PATH_PRECEDENCE`, `_WARNING_IDS`, `_ERROR_IDS`, `_ID_PATTERN`) + 7 pure helpers (`_engines_at_least`, `_select_framework`, `_select_e2e_framework`, `_count_test_files`, `_select_smoke_path`, `_extract_canonical_scripts`, `_classify_node_test`) |
| `src/codegenie/probes/_lcov_scanner.py` | New — ≤ 40-LOC stdlib state-machine scanner; reuses `parsers._io.open_capped` (NOT a re-implementation); `_LCOV_PREFIX_MAP` dispatch registry; `LcovTotals` NamedTuple; `_LCOV_MAX_BYTES` constant; ZERO `import re` |
| `src/codegenie/schema/probes/test_inventory.schema.json` | New — strict slice schema; `additionalProperties: false` at root AND every nested object (CoverageBlock, LcovTotals if object-shaped); `framework` enum closed to `["vitest","jest","mocha","tap","node_test"]`; `e2e_framework` enum `["playwright","cypress"]`; NO `confidence` field |
| `src/codegenie/probes/__init__.py` | Edit — one additive import line + one `__all__` entry; AST-diff guards |
| `src/codegenie/schema/repo_context.schema.json` | Edit — `$ref` compose under `probes.test_inventory` (optional at envelope per ADR-0010) |
| `tests/unit/probes/test_test_inventory.py` | New — ~30 unit tests covering AC-1..AC-50 with the inlined `_snapshot`/`_ctx`/`_run` preamble |
| `tests/unit/probes/test_lcov_scanner.py` | New — ~12 scanner unit tests including AST walks (regex-free, kernel-reused), byte-budget fuzz, sentinel-symlink refusal, and lcov-dialect tolerance matrix |

## Out of scope

- **Test-case counting (not file counting)** — Phase 2+ if a consumer demands. Captured today via `unit_test_count_is_file_count: True` flag.
- **Test-runner invocation** — no `vitest run`, no `jest --listTests`. Phase 1 reads files, not runtime output.
- **`vitest.config.*` / `jest.config.*` / `playwright.config.*` parsing** — `declared_inputs` includes these for cache-key derivation, but Phase 1 records *presence* only (boolean `framework_config_present: bool` if you must — see arch). Deep parsing is Phase 2.
- **Coverage diffing / `coverage/lcov.info.gz` decompression** — only uncompressed lcov in Phase 1.
- **lcov adversarial fixture in `tests/adv/`** — the local fuzz here is the first defense; the dedicated adversarial test ("hostile 50 MB lcov") lands in S5-01 / S5-03 as cross-cutting.
- **`node:test` resolved version cross-check via `node --version`** — that's `NodeBuildSystemProbe`'s slice (`node_version_resolved_locally`). `TestInventoryProbe` reads `engines.node` declaration only.

## Notes for the implementer

- **The lcov scanner is the load-bearing security surface in this story.** A regex with `.*` over attacker-controllable bytes is the regex-DoS class the arch and ADRs explicitly forbid. Write it as a state machine; test against pathological input *locally* before opening the PR. If you find the scanner is hard to write without a regex, that's the signal you need to step back, not the signal to compromise.
- **`unit_test_count_is_file_count: True`** is a permanent contract flag, not a placeholder. The boolean ships in the slice forever; Phase 2+ may add `unit_test_case_count: int | null` additively (per `phase-arch-design.md §"Component design" #7`). Do not let it disappear in a future refactor.
- **`node:test` precedence rule** is subtle. The rule is: report `node_test` **only** if `engines.node >= 18` AND no other framework declared. Tests cover both halves. Repos targeting Node 20 with vitest get `framework: "vitest"`, not `"node_test"` — even though both could technically run. Facts not judgments + the engine declaration is the most-explicit signal.
- **Memo consumption** must be defensive: `if ctx.parsed_manifest is None: parsed = safe_json.load(...)`. Edge case #12 covers this — a test path that bypasses the coordinator (e.g., a unit test calling `probe.run(...)` directly with a stub `ProbeContext`) sets `parsed_manifest=None` and the probe must still work. The fallback costs ~5 ms per gather; if it fires in production, surface a `probe.memo.miss` event count anomaly in CI.
- **Smoke-script first-match**: `scripts/smoke.sh` > `scripts/smoke.js` > `scripts/smoke.ts` > `tests/smoke/`. Document this order in the function body; consumers depend on determinism.
- **`os.walk` exclusion list reuse** — do **not** redefine the noise-dir set inline in this probe. Import it from the Phase 0 constant (`probes.language_detection._NOISE_DIRS` or wherever it lives). If the constant isn't exported, that's a Phase 0 follow-up; for now, mirror the list with a clear comment pointing at the Phase 0 source, but file the import-fix follow-up.
- **Per-probe coverage gate is 90/80** for this probe (no carve-out per ADR-0005). The lcov scanner's intent-verifying tests are the load-bearing primitive; the probe's branch coverage is sustained by the framework-detection test enumeration.
- **`commands` is verbatim.** `parsed["scripts"]["test"]` → recorded as a string. Never call `subprocess`, never `eval`, never tokenize. The Planner reads further if it needs to understand the script.
- **No new PyPI dependencies.** Specifically: no `lcov-parse`, no `coverage-parser`, no `python-lcov`. The scanner is 40 LOC of stdlib. If the implementer feels pulled toward `pip install`, surface as ADR-0009 amendment review before adding.
- **The `framework` enum is closed AND distinct from `e2e_framework`.** `framework: Literal["vitest","jest","mocha","tap","node_test"]` — UNIT-test frameworks only. `e2e_framework: Literal["playwright","cypress"]` — E2E frameworks. A repo with both jest + playwright populates BOTH fields (orthogonal axes). The original arch line 751 includes `playwright,cypress` in the `framework` Literal arm — this is documented as the migration-period escape hatch; Phase 1 probe routes them to `e2e_framework` exclusively per arch line 756 (CN-1 resolution).
- **`_FRAMEWORK_DETECTORS` precedence ordering.** Alpha order is the synthesis: `("vitest","jest","mocha","tap")` — the same alpha convention as `_BUNDLERS_SORTED` in `node_build_system.py:127-134`. Adding a future framework is one tuple-entry insertion + one schema enum bump + one fixture row; **zero** edits to selection logic. The same shape governs `_E2E_FRAMEWORK_DETECTORS = ("playwright","cypress")`.
- **`_LCOV_PREFIX_MAP` and lcov-dialect tolerance.** lcov tracefiles come in several dialects (Istanbul, coverage.py-via-cov-erage-converter, lcov-1.x, lcov-2.x). The single uniform handling rule is: any prefix not in `_LCOV_PREFIX_MAP` is silently skipped. Adding `DA:` (per-line execution counts) or `BRDA:` (per-branch detail) for a future Phase 2 enhancement is one entry. **Never** fail-loud on unknown prefixes — that's the brittle path.
- **lcov scanner kernel reuse — non-negotiable.** The scanner MUST reuse `parsers._io.open_capped` for the body retrieval. Re-implementing `os.open(O_NOFOLLOW) + os.fstat + os.close` is forbidden (AC-25). The kernel is the single source of truth for symlink-refusal + size-cap; the rule-of-three threshold is met (this is the 4th consumer after `safe_json`, `safe_yaml`, `jsonc`). If you find the kernel doesn't support streaming and you want to avoid a 50 MB in-memory allocation, the right answer is to add `open_capped_lines(path, max_bytes, parser_kind)` as a sibling primitive in `parsers/_io.py` — NOT to inline a duplicate `O_NOFOLLOW` dance in `_lcov_scanner.py`. In practice the 50 MB allocation is fine inside this probe's `timeout_seconds=10` window.
- **`_NOISE_DIRS` is the alias, not a duplicate.** `from codegenie.probes.language_detection import _SKIP_DIRS as _NOISE_DIRS`. Object-identity tested (AC-15). The cross-probe `_`-prefix import is the explicit Phase-1 shape; a Phase-2 follow-up may lift `_SKIP_DIRS` into `probes/_walking.py` as a shared kernel (the 4th consumer threshold meets at Phase 2's `IndexHealthProbe`).
- **Fuzz testing — byte-budget, not wall-clock.** `bytes_scanned / elapsed_s >= 5_000_000` is the structural ReDoS-defense assertion. The 5 MB/s floor is well below any ReDoS-grade pathology (regex catastrophic backtracking is orders of magnitude slower) and well above stdlib stream-scan rates on any current CI hardware. The wall-clock 5 s ceiling is a soft canary — if it fires, dig in but don't panic; the byte-budget is the load-bearing check.
- **Memo allowlist enforcement (ADR-0002).** Phase 1 allows ONLY `package.json` through `ctx.parsed_manifest(...)`. If the implementer feels pulled toward `ctx.parsed_manifest(tsconfig.json)` or any other path, surface as an ADR-0002 amendment review. AC-36 enforces structurally.
- **Patterns DELIBERATELY deferred** (see Validation notes for full list): `TestFrameworkDetector` ABC, shared `probes/_warning_ids.py` module, shared `probes/_walking.py` for `_SKIP_DIRS`, `FrameworkName` `NewType`, discriminated-union `_ScanOutcome`. Each defers until rule-of-three is decisively met in a later phase.
