# Story S4-03 — `TestInventoryProbe` + sub-schema + lcov scanner

**Step:** Step 4 — Ship `CIProbe`, `DeploymentProbe`, and `TestInventoryProbe`
**Status:** Ready
**Effort:** M
**Depends on:** S2-01 (`LanguageDetectionProbe` extension — `framework_hints`, monorepo, `ctx.parsed_manifest` plumbing), S2-02 (`NodeBuildSystemProbe` — `requires` for `engines.node` resolution and probe-shape conventions)
**ADRs honored:** ADR-0002 (`ParsedManifestMemo` + `input_snapshot` on `ProbeContext`), ADR-0004 (`additionalProperties: false`), ADR-0007 (warning-ID pattern), ADR-0009 (no new C-extension parser deps), ADR-0010 (Layer A slices optional at envelope)

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

- [ ] `src/codegenie/probes/test_inventory.py` exists; `TestInventoryProbe(Probe)` declares `name = "test_inventory"`, `layer = "A"`, `tier = "base"`, `applies_to_languages = ["javascript", "typescript"]`, `applies_to_tasks = ["*"]`, `requires = ["language_detection", "node_build_system"]`, `timeout_seconds = 10`, `version: str`, and `declared_inputs` per `phase-arch-design.md §"Component design" #7`.
- [ ] `src/codegenie/schema/probes/test_inventory.schema.json` exists, Draft 2020-12, `additionalProperties: false` at root and every nested block, declares slice **optional** at envelope level, validates `TestInventorySlice` shape including `unit_test_count_is_file_count: bool` (always `true` in Phase 1 — annotated in `description`).
- [ ] Red unit tests at `tests/unit/probes/test_test_inventory.py` cover: (a) `vitest` detected when `devDependencies.vitest` present; (b) `jest`, `mocha`, `tap`, `@playwright/test`, `cypress` — one test each; (c) `node:test` reported **only** when `engines.node >= 18` AND no other framework declared (two paths: engines `>=18` no-other-framework → `node_test`; engines `>=18` with vitest → `vitest`, `warnings: ["test_framework.ambiguous"]` if multiple); (d) `unit_test_file_count == 15` on a fixture with 15 `*.test.ts` files and a sentinel `node_modules/foo/bar.test.ts` that must **not** be counted (Phase 0 noise-dir exclusion); (e) companion `unit_test_count_is_file_count: True` always present.
- [ ] **lcov scanner unit tests** at `tests/unit/probes/test_lcov_scanner.py` (separate file — the scanner is the single piece of bespoke Phase-1 code in this probe; isolate it): (i) happy path — small `coverage/lcov.info` parses cleanly into totals; (ii) malformed lines skipped — partial parse + `warnings: ["coverage.lcov_parse_error"]`; (iii) 50 MB cap — `>= 50 MB` triggers `SizeCapExceeded` pre-parse → `coverage_data.present: false, parse_error: true`, `warnings: ["coverage.size_cap_exceeded"]`, gather continues; (iv) **adversarial-style local fuzz**: a 1 MB file of pathological repeating tokens (`"SF:" * 100000`, unterminated records) parses in `< 1 s` (use `time.monotonic()`; assert wall-clock `< 1.0`).
- [ ] `package.json#scripts` extraction unit test: `{"test": "...", "test:unit": "...", "test:integration": "...", "test:smoke": "...", "test:e2e": "...", "test:coverage": "..."}` → `commands` dict contains all six keys with verbatim values; no script evaluated.
- [ ] Smoke-script detection unit test: `scripts/smoke.sh` exists → `smoke_test_path == "scripts/smoke.sh"`; `tests/smoke/` directory exists → `smoke_test_path == "tests/smoke"`; neither → `smoke_test_path: None`.
- [ ] Memo consumption test: `tests/unit/probes/test_test_inventory.py::test_memo_used_when_available` patches `ctx.parsed_manifest` to a `MagicMock` returning a known dict; assert it was called once for `package.json`. Inverse: `test_memo_none_falls_back_to_safe_json` sets `ctx.parsed_manifest = None`; assert `safe_json.load` is called (monkeypatch) and the same slice is produced.
- [ ] `additionalProperties: false` rejection test on the sub-schema (synthetic envelope `probes.test_inventory.unknown: 1`) fails `SchemaValidator` at the right JSON Pointer.
- [ ] `src/codegenie/probes/__init__.py` adds one explicit additive import registering `TestInventoryProbe`.
- [ ] No new dependencies added: grep `pyproject.toml` for `lcov`, `coverage-parse`, etc. — empty. ADR-0009 compliance.
- [ ] Definition-of-done: `ruff check`, `ruff format --check`, `mypy --strict` on `test_inventory.py` and the scanner module pass; `pytest tests/unit/probes/test_test_inventory.py tests/unit/probes/test_lcov_scanner.py -q` passes; per-probe local coverage reported in PR body (90/80 — this probe is **not** carved out; the lcov scanner must earn its coverage with intent-verifying tests).

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

### Red — write failing tests first

```python
# tests/unit/probes/test_test_inventory.py
"""Pins: TestInventoryProbe records facts (framework, file count, scripts verbatim, smoke path);
node:test only when engines.node >= 18 AND no other framework;
memo consumed when available.
Traces to: phase-arch-design.md §Component design #7 + #3; ADR-0002; ADR-0004."""
import pytest
from pathlib import Path
from codegenie.probes.test_inventory import TestInventoryProbe

@pytest.mark.asyncio
async def test_vitest_detected_from_devdeps(tmp_path):
    (tmp_path / "package.json").write_text('{"devDependencies": {"vitest": "^1.0.0"}}')
    s = (await TestInventoryProbe().run(_snapshot(tmp_path), _ctx(tmp_path))).schema_slice
    assert s["framework"] == "vitest"
    assert s["unit_test_count_is_file_count"] is True

@pytest.mark.asyncio
async def test_node_test_only_when_engines_18_and_no_other_framework(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"engines": {"node": ">=18"}, "dependencies": {}, "devDependencies": {}}'
    )
    s = (await TestInventoryProbe().run(_snapshot(tmp_path), _ctx(tmp_path))).schema_slice
    assert s["framework"] == "node_test"

@pytest.mark.asyncio
async def test_node_test_yields_to_explicit_framework(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"engines": {"node": ">=20"}, "devDependencies": {"vitest": "^1.0.0"}}'
    )
    s = (await TestInventoryProbe().run(_snapshot(tmp_path), _ctx(tmp_path))).schema_slice
    assert s["framework"] == "vitest"  # node:test NOT picked

@pytest.mark.asyncio
async def test_test_file_count_excludes_node_modules(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "src").mkdir()
    for i in range(15):
        (tmp_path / "src" / f"a{i}.test.ts").write_text("")
    nm = tmp_path / "node_modules" / "x"; nm.mkdir(parents=True)
    (nm / "decoy.test.ts").write_text("")  # MUST NOT be counted
    s = (await TestInventoryProbe().run(_snapshot(tmp_path), _ctx(tmp_path))).schema_slice
    assert s["unit_test_file_count"] == 15

@pytest.mark.asyncio
async def test_scripts_captured_verbatim(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"scripts": {"test": "vitest", "test:unit": "vitest run", '
        '"test:smoke": "./scripts/smoke.sh", "test:e2e": "playwright test"}}'
    )
    s = (await TestInventoryProbe().run(_snapshot(tmp_path), _ctx(tmp_path))).schema_slice
    assert s["commands"]["test:smoke"] == "./scripts/smoke.sh"
    # facts not judgments: the script string is captured, never executed.

@pytest.mark.asyncio
async def test_smoke_path_detection(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "smoke.sh").write_text("#!/bin/sh\n")
    s = (await TestInventoryProbe().run(_snapshot(tmp_path), _ctx(tmp_path))).schema_slice
    assert s["smoke_test_path"] == "scripts/smoke.sh"

@pytest.mark.asyncio
async def test_memo_used_when_available(tmp_path):
    from unittest.mock import MagicMock
    (tmp_path / "package.json").write_text('{"devDependencies": {"jest": "^29"}}')
    memo = MagicMock(return_value={"devDependencies": {"jest": "^29"}})
    ctx = _ctx(tmp_path, parsed_manifest=memo)
    await TestInventoryProbe().run(_snapshot(tmp_path), ctx)
    assert memo.call_count == 1
    assert memo.call_args.args[0].name == "package.json"

@pytest.mark.asyncio
async def test_memo_none_falls_back_to_safe_json(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text('{"devDependencies": {"jest": "^29"}}')
    called = []
    from codegenie.parsers import safe_json
    real = safe_json.load
    monkeypatch.setattr(safe_json, "load", lambda p, **kw: (called.append(p), real(p, **kw))[1])
    ctx = _ctx(tmp_path, parsed_manifest=None)
    s = (await TestInventoryProbe().run(_snapshot(tmp_path), ctx)).schema_slice
    assert s["framework"] == "jest"
    assert any(p.name == "package.json" for p in called)
```

```python
# tests/unit/probes/test_lcov_scanner.py
"""Pins: lcov scanner is stdlib-only, no regex backtracking, 50 MB cap, fast on pathological input.
Traces to: phase-arch-design.md §Component design #7; ADR-0009."""
import time
import pytest
from pathlib import Path
from codegenie.probes._lcov_scanner import scan
from codegenie.errors import SizeCapExceeded

def test_happy_path_totals(tmp_path):
    p = tmp_path / "lcov.info"
    p.write_text("SF:/a.js\nLF:10\nLH:8\nFNF:3\nFNH:2\nBRF:4\nBRH:3\nend_of_record\n")
    t = scan(p)
    assert t.lines_found == 10 and t.lines_hit == 8
    assert t.functions_found == 3 and t.functions_hit == 2

def test_malformed_lines_ignored(tmp_path):
    p = tmp_path / "lcov.info"
    p.write_text("SF:/a.js\nGARBAGE\nLF:10\nLH:5\nend_of_record\n")
    t = scan(p)
    assert t.lines_found == 10 and t.lines_hit == 5

def test_size_cap_raises(tmp_path, monkeypatch):
    p = tmp_path / "lcov.info"
    p.write_bytes(b"x" * 64)
    with pytest.raises(SizeCapExceeded):
        scan(p, max_bytes=32)

def test_fuzz_pathological_input_completes_under_one_second(tmp_path):
    p = tmp_path / "lcov.info"
    p.write_text("SF:" * 100_000 + "\n" + "GARBAGE\n" * 10_000)
    t0 = time.monotonic()
    _ = scan(p)
    assert time.monotonic() - t0 < 1.0
```

Run both. All fail.

### Green — make it pass

1. Implement `_lcov_scanner.scan` first; iterate the scanner tests to green. **No regex over file bytes.** If you reach for `re.match` against `r"SF:(.+)"`, stop — use `line.startswith("SF:")` and `line[3:].rstrip()`.
2. Implement `_engines_at_least` helper.
3. Implement `TestInventoryProbe.run`; iterate the probe tests.
4. Write the sub-schema; wire into envelope.
5. Register.

### Refactor — clean up

- The lcov scanner stays under 50 LOC. If it grows, extract `_parse_line(line: str, state: _ScannerState) -> None` and keep `scan(...)` as the orchestration shell.
- `_engines_at_least(constraint, major)` should have one or two clear test cases inlined as docstring examples (`>=18`, `^20`, `~18.10.0`, garbage). Document the strictly-conservative behavior: garbage → return `False` (no `node:test` reported).
- The framework-detection loop is dict iteration — keep it as-is; do not extract a class.
- Confirm `ruff format`, `ruff check`, `mypy --strict` pass on both `test_inventory.py` and `_lcov_scanner.py`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/test_inventory.py` | New — `TestInventoryProbe` implementation |
| `src/codegenie/probes/_lcov_scanner.py` | New — 40-LOC stdlib state-machine scanner, isolated for testability |
| `src/codegenie/schema/probes/test_inventory.schema.json` | New — strict slice schema |
| `src/codegenie/probes/__init__.py` | Edit — one additive import |
| `src/codegenie/schema/repo_context.schema.json` | Edit — `$ref` compose under `probes.test_inventory` (optional) |
| `tests/unit/probes/test_test_inventory.py` | New — probe unit tests including memo-on / memo-off paths |
| `tests/unit/probes/test_lcov_scanner.py` | New — scanner unit tests including local-fuzz wall-clock pin |

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
- **The `framework` enum is closed.** `vitest`, `jest`, `mocha`, `tap`, `node_test`, `playwright`, `cypress`. New frameworks land via a Phase 2 sub-schema bump + a probe-version constant bump (open question #9). Do not let this list drift silently.
