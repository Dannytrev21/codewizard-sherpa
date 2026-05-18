# Story S6-06 — `Semgrep` + `AstGrep` + `RipgrepCurated` Layer G scanners

**Step:** Step 6 — Ship Layer D + E + G probes (skills, conventions, ADRs, ownership, scanners)
**Status:** HARDENED (validated 2026-05-17)
**Effort:** M
**Depends on:** S1-07 (`run_external_cli` wrapper — async, `probe_name: ProbeId` first-positional, `cwd=`/`timeout_s=` kwargs, 64 MB tail-truncation, env strip, optional bwrap), S3-03 (writer signature + sanitizer composition — scanner findings flow through `SecretRedactor` at the writer chokepoint), S5-01 (`ScannerOutcome = ScannerRan | ScannerSkipped | ScannerFailed` shared sum type; **closed set** — `reason` enums are NOT extensible without ADR-amendment), S1-08 (`@register_probe(heaviness=..., runs_last=...)` decorator — kernel kwargs are `heaviness`+`runs_last` ONLY), S5-04 (`SbomProbe` / `CveProbe` precedent: dual-form identity `_PROBE_ID: Final[ProbeId]` + `name: str`, pure-total `_classify_*_outcome` classifier, `_envelope` helper, two-file write split, `monkeypatch.setattr(mod, "run_external_cli", _spy)` test pattern)
**ADRs honored:** 02-ADR-0001 (`semgrep`, `ast-grep`, `ripgrep` added to `ALLOWED_BINARIES`), 02-ADR-0005 (no plaintext persistence — findings flow through `SecretRedactor`), 02-ADR-0006 (**`ScannerOutcome` variants AND each variant's `reason` enum are closed sets**; "output truncation" is NOT a new `reason` value — see AC-13 reframing), 02-ADR-0010 (`RedactedSlice` smart constructor at writer boundary — the four scanners' outputs reach the writer via that single typed door)
**Phase-2 load-bearing design discipline:** [`../phase-arch-design.md` §"Design patterns applied"](../phase-arch-design.md) **row 7** — *"One file per Layer G scanner; no shared `ScannerRunner` abstraction"* — SRP + Rule of Three. Four scanners have four genuinely different I/O shapes; ~60 LOC saved by sharing is not worth the speculative coupling. **This story is the test of that discipline.** Helper-level sharing (Final constants, `_envelope`, `_stderr_tail`) at the *module* level is allowed under the same row 7's "no shared **class/base**" — and the rule-of-three trigger for extracting such helpers to a new `codegenie.probes._shared.scanner_common` module fires when S6-07 (`gitleaks.py`) lands. See Notes-for-implementer #2.

## Validation notes (2026-05-17)

Twenty-six in-place edits applied — see [`_validation/S6-06-layer-g-curated-scanners.md`](_validation/S6-06-layer-g-curated-scanners.md). Categories:

- **Four block-severity Consistency fixes** (kernel-drift identical in shape to S5-04 / S6-01..05): `_run(ctx)` → `async def run(self, repo, ctx)`; `probe_id = ProbeId(...)` → `name: str = "..."` class attribute + module-level `_PROBE_ID: Final[ProbeId]` constant (dual-form identity); `ProbeOutput(probe_id=..., schema_slice=..., errors=[])` (4 wrong kwargs) → six-field `ProbeOutput(schema_slice, raw_artifacts, confidence, duration_ms, warnings, errors)`; `from codegenie.ids import ProbeId` → `from codegenie.types.identifiers import ProbeId`; `from codegenie.exec import ToolMissingError` → `from codegenie.errors import ToolMissingError`; `ProbeContext.for_test(...)` phantom → `_make_repo()` / `_make_ctx()` fixtures (sbom/cve conftest precedent); `run_external_cli(binary, argv, timeout_seconds=...)` synchronous → `await run_external_cli(_PROBE_ID, argv, cwd=repo.root, timeout_s=60.0)` async; `applies_to_*: tuple[str, ...] = ("*",)` → `list[str] = ["*"]`.
- **One structural Coverage fix**: per-scanner Pydantic `Finding` models with different fields (`SemgrepFinding`, `AstGrepFinding`, `RipgrepFinding`) cannot serve as `ScannerRan.findings: list[Finding]` payload (the shared S5-01 model is `Finding(kind, id, severity, metadata: dict[str, JSONValue])`, closed). Fix per S5-04 sbom precedent: keep `ScannerRan(findings=[])` (empty — the typed sum signals "scanner ran"), put the rich per-scanner shape on the **slice** as `findings_detail: list[SemgrepFinding]`. The closed-set discipline is preserved; the rich shape is preserved; sibling consumers (renderer, Phase-3 planner) read the slice for detail.
- **One structural Coverage fix**: AC-13's phantom `OutputTooLarge` exception and invented `ScannerFailed(reason="output_too_large")` value do not exist. `run_external_cli` tail-truncates and returns `ProcessResult` with truncated bytes; `ScannerFailed.reason` is `Literal["invalid_json", "sbom_artifact_missing"] | None` (closed per ADR-0006). Reframed AC-13: truncation-tolerance — the tail still parses → `ScannerRan`, the tail starts mid-token → `ScannerFailed(reason="invalid_json")`.
- **Six new ACs** for coverage gaps: AC-T1 (timeout path), AC-E1 (empty-findings success), AC-R1 (registry-membership smoke + no-`requires`-kwarg defense), AC-N1 (name-identity dual-form discipline), AC-B1 (eight ABC class attributes pinned), AC-W1 (two-file write split — typed slice + raw scanner bytes).
- **Three Test-Quality hardens**: source-grep → AST audit (AC-16/AC-8); per-scanner Hypothesis property-based classifier-totality test; mutation-resistance smoke table per scanner (6+ wrong stubs each).
- **Three Design-Patterns hardens**: pure-total per-scanner classifier `_classify_<scanner>_outcome(attempt: <Scanner>Attempt) -> ScannerOutcome` (S5-04 precedent — functional core / imperative shell + `match`-exhaustive `assert_never` + property-based totality); `Final[...]` annotations on every module constant; rule-of-three trigger for `_shared.scanner_common` helper module documented for the S6-07 author.

Verdict: HARDENED.

## Context

The Layer G scanners are where the temptation to abstract is highest and the cost is most visible. All four (`semgrep`, `ast-grep`, `ripgrep`, `gitleaks`) follow the same five-step shape:

1. Check the tool is available via Phase 0's `tool_cache`.
2. Invoke via `run_external_cli` with explicit argv (no shell, scanner-specific flags).
3. Parse stdout JSON via a Pydantic smart constructor.
4. Map findings into `ScannerOutcome = ScannerRan | ScannerSkipped | ScannerFailed`.
5. Return `ProbeOutput` whose `schema_slice` round-trips through the writer's redactor.

A naive reading says "abstract steps 1-5 into a `ScannerRunner` base class." The design table says no: each scanner's flags are different (`semgrep --metrics=off --json`, `ast-grep run --json=stream`, `rg --json`, `gitleaks detect --no-banner`), each scanner's JSON shape is different (Semgrep's `results: [{check_id, path, start: {line}, extra: {message}}]`, ast-grep's `[{file, range, message}]`, ripgrep's NDJSON stream, gitleaks' `[{Description, RuleID, File, StartLine, Match}]`), and each scanner's error model is different (semgrep's `errors:` array, gitleaks' exit-code-1-on-findings vs. exit-code-2-on-error). Abstracting them produces a base class with five `abstractmethod`s — at which point you've made each scanner harder to read in isolation in exchange for saving ~60 LOC.

This story ships **three** of the four (semgrep, ast-grep, ripgrep-curated). The fourth (gitleaks) ships in S6-07 *because* it's the load-bearing security scanner — the `test_secret_in_source.py` adversarial test pins the writer-chokepoint guarantee, and isolating it as a separate story prevents review pressure from collapsing the four scanners into a shared abstraction (which would invalidate the test's coverage).

`ScannerOutcome` is the typed sum across all four scanners — that's the **shared discriminated union**, the level the discipline allows sharing at. It lands in S5-01 (`src/codegenie/probes/_shared/scanner_outcome.py`); this story imports it.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md` §"Design patterns applied"](../phase-arch-design.md) **row 7** — the load-bearing "no shared `ScannerRunner`" decision; this story is the test of it.
  - [`../phase-arch-design.md` §"Component design" #5 Layer G scanners](../phase-arch-design.md) — one file per scanner, ≤ 200 LOC each.
  - [`../phase-arch-design.md` §"Component design" #3 `run_external_cli`](../phase-arch-design.md) — env strip, 64 MB stdout/stderr cap, `asyncio.wait_for` timeout, optional bubblewrap.
  - [`../phase-arch-design.md` §"Edge cases"](../phase-arch-design.md) rows 1–3 + 13 — tool missing, non-zero exit, bad JSON, hostile JSON (truncated/oversized/deeply nested).
  - [`../phase-arch-design.md` §"Anti-patterns avoided"](../phase-arch-design.md) "Inheritance for code reuse" — every Phase 2 class inherits only `Probe` or `BaseModel`.
- **Phase ADRs:**
  - [`../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md`](../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md) — `semgrep`, `ast-grep`, `ripgrep` in the allowlist; the only auditable list.
  - [`../ADRs/0005-secret-findings-no-plaintext-persistence.md`](../ADRs/0005-secret-findings-no-plaintext-persistence.md) — findings flow through `SecretRedactor` at the writer.
- **Source design:**
  - [`../High-level-impl.md` §"Step 6"](../High-level-impl.md) — per-probe timeouts (semgrep 60s, ast-grep 30s, ripgrep-curated 30s); `--metrics=off` for semgrep; `@register_probe(heaviness="medium")`.
  - [`../../localv2.md` §5.6 G1 / G2 / G5](../../../localv2.md) — slice shapes.
- **Existing kernel:**
  - `src/codegenie/exec.py` (S1-07) — `run_external_cli(binary, argv, *, timeout_seconds, ...) -> ProcessResult`.
  - `src/codegenie/probes/_shared/scanner_outcome.py` (S5-01) — `ScannerRan | ScannerSkipped | ScannerFailed`.
  - `src/codegenie/output/sanitizer.py` (S3-01..03) — `SecretRedactor`; this probe doesn't call it (writer does).

## Goal

Ship three files under `src/codegenie/probes/layer_g/`: `semgrep.py`, `ast_grep.py`, `ripgrep_curated.py`. Each:

- Is `@register_probe(heaviness="medium")`.
- Is **≤ 200 LOC** (including Pydantic models, imports, docstring).
- Imports **no** code from another scanner in this set.
- Follows the five-step shape — but the five steps are inline, not behind a base class.
- Routes invocation through `run_external_cli`; parses stdout JSON via a per-scanner Pydantic smart constructor; returns `ScannerOutcome` as the slice payload.

The fourth scanner (`gitleaks.py`) is S6-07; same shape, different story.

## Acceptance criteria

**Numbered for traceability to the TDD plan.** ACs are corrected against the frozen Phase-0 `Probe` ABC (`src/codegenie/probes/base.py:74-96`), the actual `run_external_cli` signature (`src/codegenie/exec/__init__.py:485-599`), the closed `ScannerOutcome` variant set (`src/codegenie/probes/_shared/scanner_outcome.py`), and the S5-04 sbom/cve sibling-precedent.

- [ ] **AC-1.** Three new files exist under `src/codegenie/probes/layer_g/` plus a `layer_g/__init__.py` package marker. Each file's `__all__` declares exactly the slice model + probe class (e.g. `__all__ = ["SemgrepProbe", "SemgrepSlice"]`).
- [ ] **AC-2.** Each probe file is **≤ 200 LOC** including Pydantic models, imports, docstring. Verified by `tests/unit/probes/layer_g/test_scanner_loc_ceiling.py`.
- [ ] **AC-3.** Each probe is `@register_probe(heaviness="medium", runs_last=False)` (the decorator's ONLY kwargs are `heaviness` + `runs_last` per 02-ADR-0003 Option D; `requires=` is NOT a decorator kwarg). Class-level `name: str` matches the filename stem (`"semgrep"`, `"ast_grep"`, `"ripgrep_curated"`). `applies_to_tasks: list[str] = ["*"]` and `applies_to_languages: list[str] = ["*"]` — **`list[str]`**, not tuple.
- [ ] **AC-4.** Per-probe `timeout_seconds: int` class attribute: `SemgrepProbe.timeout_seconds = 60`, `AstGrepProbe.timeout_seconds = 30`, `RipgrepCuratedProbe.timeout_seconds = 30`. Mutation caught: any drift across the three values would be visible in the per-probe assertion test.
- [ ] **AC-5.** **`SemgrepProbe`** invokes `await run_external_cli(_PROBE_ID, ["semgrep", "--config", config, "--json", "--metrics=off", "--quiet", str(repo.root)], cwd=repo.root, timeout_s=60.0)`. The first positional argument is the `ProbeId` (`_PROBE_ID: Final[ProbeId] = ProbeId("semgrep")`), NOT the binary string. The binary `"semgrep"` is `argv[0]` (`run_external_cli` allowlist-checks it). `--metrics=off` is mandatory (verified by captured-argv spy in test); `--quiet` keeps stderr minimal for the 64 MB tail. Mutation hint: any future `argv.remove("--metrics=off")` fires the argv-introspection assertion.
- [ ] **AC-6.** **`AstGrepProbe`** invokes `await run_external_cli(_PROBE_ID, ["ast-grep", "scan", "--config", config, "--json=stream", str(repo.root)], cwd=repo.root, timeout_s=30.0)`. `--json=stream` (NDJSON one-finding-per-line) is mandatory — `--json=compact` (single buffered array) is forbidden because it inverts the peak-memory profile from O(one finding) to O(all findings) under the 64 MB tail. Captured-argv spy asserts both flags.
- [ ] **AC-7.** **`RipgrepCuratedProbe`** invokes `await run_external_cli(_PROBE_ID, ["rg", "--json", "--max-count", "100", "--type-not", "lock", *_PATTERN_ARGS, str(repo.root)], cwd=repo.root, timeout_s=30.0)`. `--max-count 100` is **per-file** (rg's documented semantics — caps matches per file per pattern, not per-pattern globally); `--type-not lock` skips lockfiles. The curated pattern set is the closed `_CURATED_PATTERNS: Final[tuple[str, ...]]` from `localv2.md §5.6 G5`: `("/bin/", "/usr/bin/", "/sbin/", r"exec\(", r"spawn\(", r"execSync\(", r"process\.platform", r"os\.platform\(", "LD_PRELOAD", "LD_LIBRARY_PATH")`. `_PATTERN_ARGS` is `[arg for p in _CURATED_PATTERNS for arg in ("-e", p)]` — each pattern preceded by `-e` so it's parsed as a regex, not a path. Argv-order test pins the position of `--type-not lock` (must precede patterns) and verifies every curated pattern is present.
- [ ] **AC-8.** **No shared `ScannerRunner` base class — AST audit, not source-grep.** Architectural test parametrized over the three modules: parse the source with `ast.parse`; assert no `ClassDef` named `ScannerRunner` / `BaseScanner` / `AbstractScanner`; assert no `ImportFrom` whose module is another sibling scanner module; assert each `ClassDef.bases` resolves to `Probe` only (not a sibling-scanner base). The shared types are `ScannerOutcome` (S5-01, `_shared/scanner_outcome.py`) and `run_external_cli` (S1-07, `exec/__init__.py`) — both at the **kernel** level, not the scanner-family level. Mutation caught: any future contributor extracting a base class fails this AST audit immediately.
- [ ] **AC-9.** **Per-scanner rich `Finding` model lives on the SLICE, not on `ScannerRan.findings`.** Each scanner declares its own Pydantic Finding type (`SemgrepFinding{check_id, path, line, severity, message}`, `AstGrepFinding{file, line, message, rule_id}`, `RipgrepFinding{pattern, file, line, snippet}`) with `model_config = ConfigDict(frozen=True, extra="forbid")`. The **slice** carries `findings_detail: list[<ScannerFinding>]`; the **`ScannerRan.findings`** field stays as the empty `list[Finding]` from S5-01 (the closed sum's contract). Reason: `ScannerRan.findings: list[Finding]` is typed against the shared S5-01 `Finding` and ADR-0006 closes the set; widening the union to accept per-scanner shapes would force every Phase-2 / Phase-3 consumer to re-discriminate. Mirror sbom.py:244-254 precedent (`ScannerRan(findings=[])` while rich shape lives in slice's `packages_by_source` / `package_count`).
- [ ] **AC-10.** **Tool missing → `ScannerSkipped(reason="tool_missing")`.** When `run_external_cli` raises `ToolMissingError` (from `codegenie.errors`, re-exported by `codegenie.exec`), the probe returns a `ProbeOutput` whose slice's `outcome` is `ScannerSkipped(reason="tool_missing")` and whose `confidence == "low"`. Mutation caught: any `raise` past the probe boundary, or any `reason="missing"` typo (closed set: `Literal["tool_missing", "tool_unhealthy", "upstream_unavailable"]`).
- [ ] **AC-11.** **Non-zero exit → `ScannerFailed(exit_code, stderr_tail)`** for `ast_grep` and `ripgrep_curated`. **Semgrep is the carve-out** — see AC-15. For ast-grep and ripgrep, any `result.returncode != 0` → `ScannerFailed(exit_code=result.returncode, stderr_tail=_stderr_tail(result.stderr))`. Per-probe parametrized test pins the convention.
- [ ] **AC-12.** **Invalid JSON → `ScannerFailed(reason="invalid_json", ...)`.** When stdout fails the Pydantic smart constructor (`<Scanner>JsonSchema.model_validate_json` raises), the probe returns `ScannerFailed(exit_code=result.returncode, stderr_tail=<tail>, reason="invalid_json")`. The `reason` field is the closed-set `Literal["invalid_json", "sbom_artifact_missing"] | None` from ADR-0006; `"invalid_json"` is the load-bearing value for this story. Mutation caught: any `try: ... except ValidationError: pass` silent swallow; any invented `reason` string.
- [ ] **AC-13.** **64 MB tail-truncation tolerance.** `run_external_cli` tail-truncates rather than raising (`src/codegenie/exec/__init__.py:579-598`). Test parametrized across the three probes: mock `run_external_cli` to return a `ProcessResult` whose `stdout` is a `<scanner>-truncated bytes block` prefixed with the `_TRUNC_MARKER`. Assert two cases: (a) if the truncated tail still parses as valid JSON → `ScannerRan(findings=[])` (slice's `findings_detail` may be partial — `confidence="medium"` to signal honest uncertainty); (b) if the truncated tail starts mid-token → `ScannerFailed(reason="invalid_json", ...)` (AC-12 path). **No new `reason` value is introduced** ("output_too_large" is NOT in the closed set; ADR-0006 §Consequences). Mutation caught: any probe that bypasses the wrapper.
- [ ] **AC-14.** **Platform-independent probe — bwrap handling is the wrapper's concern.** AST audit: each layer_g probe module imports zero of `{sys.platform, platform.system, shutil.which, subprocess, asyncio.create_subprocess_*}` (assert via `ast.walk` over `ImportFrom` + `Attribute` nodes). The platform-detection / bwrap-availability concern lives entirely inside `run_external_cli` (S1-07). Behavioral consequence test: monkeypatching `run_external_cli` to the same stub on a Linux and macOS spy returns the same `ProbeOutput` shape.
- [ ] **AC-15.** **Semgrep exit code 1 = findings present (carve-out).** Semgrep documents exit code 1 as "rule findings present, no error" (semgrep CLI reference). `SemgrepProbe`'s pure classifier MUST treat `exit_code in (0, 1)` as "parse stdout"; `exit_code >= 2` is `ScannerFailed`. The other two scanners use the default "non-zero = error". **This is the textbook example of why a shared `ScannerRunner` is wrong.** Two tests: exit code 1 with findings → `ScannerRan(findings=[])` AND slice `findings_detail` populated; exit code 2 → `ScannerFailed(exit_code=2, ...)`. Mutation caught: any default-error convention applied to semgrep silently mis-classifies findings-present runs.
- [ ] **AC-16.** **All scanner invocations route through `run_external_cli` — AST audit.** For each layer_g module: parse source, walk `ast.Call`; assert no call whose `.func` resolves to `subprocess.run` / `subprocess.Popen` / `asyncio.create_subprocess_exec` / `asyncio.create_subprocess_shell` / `os.system` / `os.popen`. Additionally assert `run_allowlisted` is **not imported** in any layer_g module (Layer G uses the `run_external_cli` wrapper; Layer C uses `run_allowlisted` directly per 02-ADR-0001 §Consequences). The single chokepoint is `run_external_cli` — `grep -rn run_external_cli src/codegenie/` is the auditable invocation list.
- [ ] **AC-17.** **`mypy --strict`** passes on all three files. The per-scanner `findings_detail: list[<Scanner>Finding]` types make every consumer position-typed; `Any` escapes only via the `ctx.config: dict[str, Any]` boundary (mirror sbom/cve discipline).
- [ ] **AC-18a.** **Pydantic-level schema discipline.** Each slice model (`SemgrepSlice`, `AstGrepSlice`, `RipgrepCuratedSlice`) declares `model_config = ConfigDict(frozen=True, extra="forbid")`. JSON-Schema sub-schema files (`src/codegenie/schema/probes/layer_g/{semgrep,ast_grep,ripgrep_curated}.schema.json`) with `additionalProperties: false` at every level and `ScannerOutcome` discriminator `kind` ∈ {`"ran"`, `"skipped"`, `"failed"`} **land in S6-08**; S6-06 closes the Pydantic side only.
- [ ] **AC-19.** **Subprocess invocations mocked via `monkeypatch.setattr(<module>, "run_external_cli", _spy)`** — the repo-precedent pattern (10+ call sites: `tests/unit/probes/layer_c/test_sbom.py:140`, `test_cve.py:141-363`). The spy is an `AsyncMock` (or plain coroutine) returning a `ProcessResult(returncode, stdout, stderr)`. The wrapper itself is exercised by `tests/unit/exec/test_run_external_cli.py` (S1-07's test suite); this story's tests pin the **probe-side contract surface** (correct `_PROBE_ID`, correct argv, correct `cwd`, correct `timeout_s`, correct error-handling on each raised typed exception). Integration lane (S7-05) runs the real binaries.

### New ACs (validator additions, 2026-05-17)

- [ ] **AC-T1.** **Timeout → `ScannerFailed(exit_code=124, stderr_tail="<scanner>.timeout")`.** When `run_external_cli` raises `ProbeTimeoutError` (`codegenie.errors`), the probe catches it and emits `ScannerFailed(exit_code=124, stderr_tail="semgrep.timeout")` (mirror sbom.py:275-276 / cve.py:246-247). Per-probe test: monkeypatch `run_external_cli` to `raise ProbeTimeoutError("...")` → probe returns `ScannerFailed` with `exit_code=124` and `confidence="low"`. Mutation caught: any timeout that escapes past the probe boundary would break the coordinator's per-probe isolation.
- [ ] **AC-E1.** **Empty-findings success.** Semgrep `exit 0` + `{"results": [], "paths": {"scanned": [], "skipped": []}}` → `ScannerRan(findings=[])` with `confidence="high"` and slice `findings_detail == []`. Same shape for ast-grep (empty stdout: zero NDJSON lines) and ripgrep (empty NDJSON stream). Mutation caught: an implementation that returned `ScannerSkipped(...)` on empty findings.
- [ ] **AC-R1.** **Registry-membership smoke.** For each scanner: `_PROBE_REGISTRY["<scanner>"].heaviness == "medium"`; `_PROBE_REGISTRY["<scanner>"].runs_last is False`; the entry has **no** `requires` key (defensive — `@register_probe(requires=...)` is NOT a kernel kwarg per 02-ADR-0003 Option D; passing it must fail at import). Per S5-04 K2 / S6-05 AC-NEW-2 precedent.
- [ ] **AC-N1.** **Dual-form identity discipline.** Each module declares `_PROBE_ID: Final[ProbeId] = ProbeId("<scanner>")` at module scope (the value passed to `run_external_cli(probe_name=_PROBE_ID, ...)`). The probe class declares `name: str = "<scanner>"` as a class attribute (the kernel-introspected identity, ABC contract). Both strings are equal to the filename stem. Mutation caught: drift between `name`, `_PROBE_ID`, filename — any one of three would silently break either dispatch or argv-validation.
- [ ] **AC-B1.** **Eight ABC class attributes pinned per probe.** Mirror cve.py:177-185: `name: str = "<scanner>"`, `version: str = "0.1.0"`, `layer = "G"`, `tier = "base"`, `applies_to_tasks: list[str] = ["*"]`, `applies_to_languages: list[str] = ["*"]`, `requires: list[str] = []` (class attribute — empty list; per 02-ADR-0003 Option D `requires` is metadata-only, not load-bearing for dispatch), `declared_inputs: list[str] = [<per-scanner globs>]` (e.g. `["**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx"]` for semgrep; `["**/*"]` for ripgrep-curated), `timeout_seconds: int = <60|30|30>`. Per-probe test asserts every one of these — a `layer = "F"` typo would slip past `mypy --strict` otherwise.
- [ ] **AC-W1.** **Two-file write split per probe.** Each probe writes (a) `<raw_dir>/<scanner>.json` (the typed slice as JSON-mode-`model_dump`; this is the `IndexName("<scanner>")` key for downstream sibling-slice readers via `read_raw_slices`) AND (b) `<raw_dir>/<scanner>-raw.json` (the raw scanner stdout bytes, retained for audit and re-parse). Failure paths (`ScannerFailed` / `ScannerSkipped`) only write the slice file, NOT the malformed raw file (mirror sbom.py:201-206 contract). `ProbeOutput.raw_artifacts` lists the actual files written. Mutation caught: a probe that writes the raw file on the failure path would persist potentially-secret-containing malformed bytes to disk in violation of 02-ADR-0005.

## Implementation outline

Each scanner file mirrors the **S5-04 sbom/cve precedent** — pure-total classifier + `_envelope` helper + dual-form identity:

```python
# 1. Module docstring (S5-04 shape: discipline + arch references + ADR cross-refs)
# 2. Module-level Final constants:
#    _PROBE_ID: Final[ProbeId] = ProbeId("<scanner>")
#    _TIMEOUT_S: Final[int] = <60 | 30 | 30>
#    _SLICE_FILENAME: Final[str] = "<scanner>.json"
#    _RAW_TOOL_FILENAME: Final[str] = "<scanner>-raw.json"
# 3. Per-scanner rich Finding model (frozen, extra="forbid")
# 4. Per-scanner slice model: outcome: ScannerOutcome + findings_detail: list[<Finding>]
#    + scanner-specific metadata (semgrep: rules_run, files_scanned; rg: patterns_matched; etc.)
# 5. Private tagged-union ScannerAttempt = _ToolMissing | _ProcessTimedOut | _ProcessExited(...)
# 6. Pure, total classifier _classify_<scanner>_outcome(attempt: <Scanner>Attempt) -> ScannerOutcome
#    (match-exhaustive with assert_never; never raises; the property-based test pins totality)
# 7. Probe class:
#    - 8 ABC class attributes pinned (AC-B1)
#    - async def run(self, repo, ctx) -> ProbeOutput  (the only impure method)
#    - @staticmethod async def _attempt(...) -> <Scanner>Attempt  (the I/O wrapper)
#    - @staticmethod def _envelope(slice_dict, raw_artifacts, confidence, t0) -> ProbeOutput
#      (the six-field ProbeOutput constructor; mirror sbom.py:289-297)
```

Concretely:

1. **`semgrep.py`** (~170 LOC including classifier and tagged union):
   - `_PROBE_ID = ProbeId("semgrep")`, `_TIMEOUT_S = 60`, `_SLICE_FILENAME = "semgrep.json"`, `_RAW_TOOL_FILENAME = "semgrep-raw.json"`.
   - `SemgrepFinding{check_id, path, line, severity: Literal["info","warning","error"], message}`.
   - `SemgrepSlice{outcome: ScannerOutcome, findings_detail: list[SemgrepFinding], rules_run: int | None, files_scanned: int | None}` — `frozen=True, extra="forbid"`.
   - `SemgrepAttempt = _ToolMissing | _ProcessTimedOut | _ProcessExited` (`_ProcessExited` carries `exit_code: int`, `stdout: bytes`, `stderr_tail: str`).
   - `_classify_semgrep_outcome(attempt) -> ScannerOutcome`: `match attempt`: `_ToolMissing()` → `ScannerSkipped(reason="tool_missing")`; `_ProcessTimedOut(...)` → `ScannerFailed(exit_code=124, stderr_tail="semgrep.timeout")`; `_ProcessExited(exit_code, stdout, stderr_tail)` with `exit_code >= 2` → `ScannerFailed(exit_code, stderr_tail)`; `exit_code in (0, 1)` → try `_parse_semgrep_stdout(stdout)`; on success → `ScannerRan(findings=[])` (slice carries rich findings); on `ValidationError`/`json.JSONDecodeError` → `ScannerFailed(exit_code, stderr_tail, reason="invalid_json")`. **The exit-1 carve-out is the load-bearing line.**
   - `SemgrepProbe.run(repo, ctx)`: build `attempt = await self._attempt(repo.root, ctx.config)`; `outcome = _classify_semgrep_outcome(attempt)`; build slice; write two files (slice + raw bytes, raw only on `ScannerRan`); return `_envelope(...)`.

2. **`ast_grep.py`** (~140 LOC):
   - Same Final constants pattern with `_TIMEOUT_S = 30`.
   - `AstGrepFinding{file, line, message, rule_id}`.
   - `AstGrepSlice{outcome, findings_detail, rules_run: int | None}`.
   - NDJSON parser: `_parse_ast_grep_stdout(stdout: bytes) -> list[AstGrepFinding]` walks line-by-line, `json.loads` each, validates via Pydantic; on any failure raises `ValidationError`-or-`JSONDecodeError` for the classifier to convert.
   - **Default error convention**: classifier maps any non-zero exit (no carve-out) to `ScannerFailed`.

3. **`ripgrep_curated.py`** (~160 LOC):
   - `_CURATED_PATTERNS: Final[tuple[str, ...]] = ("/bin/", "/usr/bin/", "/sbin/", r"exec\(", r"spawn\(", r"execSync\(", r"process\.platform", r"os\.platform\(", "LD_PRELOAD", "LD_LIBRARY_PATH")`.
   - `_PATTERN_ARGS: Final[tuple[str, ...]]` derived as `tuple(arg for p in _CURATED_PATTERNS for arg in ("-e", p))` at module load.
   - `RipgrepFinding{pattern, file, line, snippet}` — `pattern` is the curated regex the line matched.
   - NDJSON parser: ripgrep emits `{"type": "match", "data": {"path": {"text": ...}, "lines": {"text": ...}, "line_number": N, "submatches": [...]}}`. The parser walks only `"type": "match"` lines, extracts the matched pattern by submatch index, ignores `"type": "begin" | "end" | "summary"`.
   - **Default error convention**: any non-zero exit → `ScannerFailed`.
   - **Exit code 1** for ripgrep means "no matches found, no error" — must be classified as `ScannerRan(findings=[])`, NOT `ScannerFailed`. Per-probe carve-out, second textbook example of why a shared abstraction is wrong.

## TDD plan — red / green / refactor

### Red — write the failing tests first

The tests use **`monkeypatch.setattr(<module>, "run_external_cli", _spy)`** — the repo's canonical mocking pattern (10+ precedent sites in `tests/unit/probes/layer_c/`). The spy is an async callable that returns a `ProcessResult` and captures positional/keyword args for argv assertions. `pytest-subprocess` is **not** used — it is not in `pyproject.toml`'s dev deps, and the wrapper itself (`run_external_cli`) is exercised by `tests/unit/exec/test_run_external_cli.py` (S1-07's own test suite).

```python
# tests/unit/probes/layer_g/conftest.py
"""Test fixtures for Layer G scanner probes (S6-06). Mirrors
tests/unit/probes/layer_c/conftest.py shape."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from codegenie.probes.base import ProbeContext, RepoSnapshot


def _make_repo(root: Path) -> RepoSnapshot:
    return RepoSnapshot(root=root, git_commit=None, detected_languages={"typescript": 100}, config={})


def _make_ctx(tmp_path: Path) -> ProbeContext:
    return ProbeContext(
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "out",
        workspace=tmp_path / "ws",
        logger=logging.getLogger("test"),
        config={},
    )


@pytest.fixture
def repo(tmp_path: Path) -> RepoSnapshot:
    return _make_repo(tmp_path / "repo")


@pytest.fixture
def ctx(tmp_path: Path) -> ProbeContext:
    return _make_ctx(tmp_path)
```

```python
# tests/unit/probes/layer_g/test_semgrep.py
"""Unit tests for SemgrepProbe (S6-06)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from codegenie.errors import ProbeTimeoutError, ToolMissingError
from codegenie.exec import ProcessResult
from codegenie.probes.layer_g import semgrep as sg_mod
from codegenie.probes.layer_g.semgrep import SemgrepProbe, SemgrepSlice
from codegenie.probes._shared.scanner_outcome import ScannerRan, ScannerSkipped, ScannerFailed
from codegenie.probes.registry import _PROBE_REGISTRY  # path per S5-04 precedent


# ---- AC-5: argv pinning via captured spy --------------------------------

@pytest.mark.asyncio
async def test_semgrep_argv_includes_metrics_off_and_quiet(monkeypatch, repo, ctx):
    """AC-5. Mutation: dropping `--metrics=off` would let semgrep phone
    home; dropping `--quiet` would let stderr breach the 64 MB cap.
    Both flags are pinned by argv capture, not by string-substring."""
    captured = {}

    async def _spy(probe_name, argv, *, cwd, timeout_s, **kwargs):
        captured["probe_name"] = probe_name
        captured["argv"] = list(argv)
        captured["cwd"] = cwd
        captured["timeout_s"] = timeout_s
        return ProcessResult(returncode=0, stdout=b'{"results": [], "paths": {"scanned": [], "skipped": []}}', stderr=b"")

    monkeypatch.setattr(sg_mod, "run_external_cli", _spy)
    output = await SemgrepProbe().run(repo, ctx)

    assert captured["probe_name"] == sg_mod._PROBE_ID  # AC-N1 + AC-T7
    assert captured["argv"][0] == "semgrep"
    assert "--metrics=off" in captured["argv"]
    assert "--quiet" in captured["argv"]
    assert "--json" in captured["argv"]
    assert captured["cwd"] == repo.root
    assert captured["timeout_s"] == 60.0
    assert output.confidence == "high"


# ---- AC-15: exit code 1 = findings present ------------------------------

@pytest.mark.asyncio
async def test_semgrep_exit_code_1_is_findings_not_failure(monkeypatch, repo, ctx):
    """AC-15. Mutation: a default-error convention applied to semgrep
    silently mis-classifies findings-present runs as ScannerFailed."""
    findings_stdout = json.dumps({
        "results": [{
            "check_id": "p/nodejs.eval-detected",
            "path": "src/loader.ts",
            "start": {"line": 42},
            "extra": {"severity": "ERROR", "message": "eval call"},
        }],
        "paths": {"scanned": ["src/loader.ts"], "skipped": []},
    }).encode()

    async def _spy(*a, **kw):
        return ProcessResult(returncode=1, stdout=findings_stdout, stderr=b"")

    monkeypatch.setattr(sg_mod, "run_external_cli", _spy)
    output = await SemgrepProbe().run(repo, ctx)
    slice_ = SemgrepSlice.model_validate(output.schema_slice["semgrep"])

    assert isinstance(slice_.outcome, ScannerRan)
    assert slice_.outcome.findings == []  # AC-9: ScannerRan.findings is empty
    assert len(slice_.findings_detail) == 1  # rich shape is slice-side
    assert slice_.findings_detail[0].check_id == "p/nodejs.eval-detected"
    assert slice_.findings_detail[0].line == 42


# ---- AC-15: exit code 2 = real failure ----------------------------------

@pytest.mark.asyncio
async def test_semgrep_exit_code_2_is_scanner_failed(monkeypatch, repo, ctx):
    """AC-15. Mutation: treating exit code 2 as findings (parse-then-
    emit-empty) would mask real semgrep config errors."""

    async def _spy(*a, **kw):
        return ProcessResult(returncode=2, stdout=b"", stderr=b"Error: invalid rule config")

    monkeypatch.setattr(sg_mod, "run_external_cli", _spy)
    output = await SemgrepProbe().run(repo, ctx)
    slice_ = SemgrepSlice.model_validate(output.schema_slice["semgrep"])

    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.exit_code == 2
    assert "invalid rule config" in slice_.outcome.stderr_tail
    assert output.confidence == "low"


# ---- AC-12: invalid JSON → ScannerFailed(reason="invalid_json") --------

@pytest.mark.asyncio
async def test_semgrep_invalid_json_yields_scanner_failed_invalid_json(monkeypatch, repo, ctx):
    """AC-12. Mutation: silent ValidationError swallow would emit
    ScannerRan(findings=[]) for what is actually corrupted output."""

    async def _spy(*a, **kw):
        return ProcessResult(returncode=0, stdout=b"not json at all", stderr=b"")

    monkeypatch.setattr(sg_mod, "run_external_cli", _spy)
    output = await SemgrepProbe().run(repo, ctx)
    slice_ = SemgrepSlice.model_validate(output.schema_slice["semgrep"])

    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.reason == "invalid_json"  # closed-set check (AC-12 + ADR-0006)


# ---- AC-10: tool missing → ScannerSkipped ------------------------------

@pytest.mark.asyncio
async def test_semgrep_tool_missing_yields_scanner_skipped(monkeypatch, repo, ctx):
    """AC-10. Mutation: a `raise` past the probe boundary would break
    coordinator per-probe isolation."""

    async def _raise(*a, **kw):
        raise ToolMissingError("semgrep")

    monkeypatch.setattr(sg_mod, "run_external_cli", _raise)
    output = await SemgrepProbe().run(repo, ctx)
    slice_ = SemgrepSlice.model_validate(output.schema_slice["semgrep"])

    assert isinstance(slice_.outcome, ScannerSkipped)
    assert slice_.outcome.reason == "tool_missing"
    assert output.confidence == "low"


# ---- AC-T1: timeout → ScannerFailed(exit_code=124) ----------------------

@pytest.mark.asyncio
async def test_semgrep_timeout_yields_scanner_failed_124(monkeypatch, repo, ctx):
    """AC-T1. Mutation: any timeout that escapes past the probe boundary
    breaks coordinator isolation (the next probe sees the exception)."""

    async def _timeout(*a, **kw):
        raise ProbeTimeoutError("semgrep exceeded 60s")

    monkeypatch.setattr(sg_mod, "run_external_cli", _timeout)
    output = await SemgrepProbe().run(repo, ctx)
    slice_ = SemgrepSlice.model_validate(output.schema_slice["semgrep"])

    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.exit_code == 124
    assert slice_.outcome.stderr_tail == "semgrep.timeout"


# ---- AC-E1: empty findings on exit 0 ------------------------------------

@pytest.mark.asyncio
async def test_semgrep_empty_findings_yields_scanner_ran_high_confidence(monkeypatch, repo, ctx):
    """AC-E1. Mutation: returning ScannerSkipped on empty findings would
    erase a real "scanned, found nothing" signal."""
    empty_stdout = json.dumps({"results": [], "paths": {"scanned": [], "skipped": []}}).encode()

    async def _spy(*a, **kw):
        return ProcessResult(returncode=0, stdout=empty_stdout, stderr=b"")

    monkeypatch.setattr(sg_mod, "run_external_cli", _spy)
    output = await SemgrepProbe().run(repo, ctx)
    slice_ = SemgrepSlice.model_validate(output.schema_slice["semgrep"])

    assert isinstance(slice_.outcome, ScannerRan)
    assert slice_.findings_detail == []
    assert output.confidence == "high"


# ---- AC-13: truncation tolerance ----------------------------------------

@pytest.mark.asyncio
async def test_semgrep_truncated_tail_still_parses_or_invalid_json(monkeypatch, repo, ctx):
    """AC-13. Mutation: any probe that raised on cap-exceeded would
    break the wrapper's tail-truncation contract (no invented
    `reason="output_too_large"` value — ADR-0006 closed set)."""
    # Case (b): tail starts mid-token → invalid_json
    truncated_garbage = b'<TRUNC>...}, "extra": {"sev'

    async def _spy(*a, **kw):
        return ProcessResult(returncode=0, stdout=truncated_garbage, stderr=b"")

    monkeypatch.setattr(sg_mod, "run_external_cli", _spy)
    output = await SemgrepProbe().run(repo, ctx)
    slice_ = SemgrepSlice.model_validate(output.schema_slice["semgrep"])

    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.reason == "invalid_json"
    # explicitly NOT == "output_too_large" — that value does not exist.


# ---- AC-B1: ABC class attributes pinned ---------------------------------

def test_semgrep_abc_class_attributes_pinned():
    """AC-B1. Mutation: a `layer = "F"` typo would slip past mypy
    --strict; this test pins every one of the eight required attrs."""
    assert SemgrepProbe.name == "semgrep"
    assert SemgrepProbe.layer == "G"
    assert SemgrepProbe.tier == "base"
    assert SemgrepProbe.applies_to_tasks == ["*"]
    assert SemgrepProbe.applies_to_languages == ["*"]
    assert SemgrepProbe.requires == []
    assert SemgrepProbe.timeout_seconds == 60
    assert isinstance(SemgrepProbe.declared_inputs, list)
    assert all(isinstance(p, str) for p in SemgrepProbe.declared_inputs)


# ---- AC-N1: dual-form identity discipline -------------------------------

def test_semgrep_dual_form_identity():
    """AC-N1. Mutation: drift between filename, _PROBE_ID, and name
    would silently break either argv-validation or kernel dispatch."""
    assert sg_mod._PROBE_ID == "semgrep"  # ProbeId is str-newtype
    assert SemgrepProbe.name == "semgrep"
    assert sg_mod.__name__.endswith(".semgrep")


# ---- AC-R1: registry-membership smoke -----------------------------------

def test_semgrep_registry_entry_carries_heaviness_only():
    """AC-R1. Mutation: dropping the decorator silently loses dispatch;
    adding a `requires=` kwarg phantom would fail at import (kernel
    only accepts heaviness + runs_last per 02-ADR-0003 Option D)."""
    entry = _PROBE_REGISTRY["semgrep"]
    assert entry.heaviness == "medium"
    assert entry.runs_last is False
    # Defensive: assert there is no `requires` attribute on the entry
    # (the registry stores `heaviness` + `runs_last` only).
    assert not hasattr(entry, "requires") or entry.requires is None


# ---- AC-W1: two-file write split ----------------------------------------

@pytest.mark.asyncio
async def test_semgrep_writes_slice_and_raw_on_success(monkeypatch, repo, ctx, tmp_path):
    """AC-W1. Mutation: writing the raw file on a failure path would
    persist potentially-secret-containing malformed bytes (ADR-0005)."""
    repo.root.mkdir(parents=True, exist_ok=True)
    findings_stdout = b'{"results": [], "paths": {"scanned": [], "skipped": []}}'

    async def _spy(*a, **kw):
        return ProcessResult(returncode=0, stdout=findings_stdout, stderr=b"")

    monkeypatch.setattr(sg_mod, "run_external_cli", _spy)
    output = await SemgrepProbe().run(repo, ctx)
    paths = {p.name for p in output.raw_artifacts}
    assert "semgrep.json" in paths
    assert "semgrep-raw.json" in paths  # raw written only on ScannerRan


@pytest.mark.asyncio
async def test_semgrep_does_not_write_raw_on_failure(monkeypatch, repo, ctx, tmp_path):
    """AC-W1. The malformed raw bytes must NOT be persisted."""
    repo.root.mkdir(parents=True, exist_ok=True)

    async def _spy(*a, **kw):
        return ProcessResult(returncode=2, stdout=b"not json", stderr=b"err")

    monkeypatch.setattr(sg_mod, "run_external_cli", _spy)
    output = await SemgrepProbe().run(repo, ctx)
    paths = {p.name for p in output.raw_artifacts}
    assert "semgrep.json" in paths
    assert "semgrep-raw.json" not in paths
```

```python
# tests/unit/probes/layer_g/test_classifier_totality.py
"""Property-based totality tests for per-scanner classifiers (S6-06).

Each scanner declares a private tagged-union ScannerAttempt and a pure
classifier. The classifier MUST be total (every input → exactly one
ScannerOutcome, never raises) and side-effect-free.

T3 (mirror S5-04 T3): a property-based test is the kernel of the
mutation-resistance argument. An implementation that always returned
ScannerRan(findings=[]) would pass most happy-path tests but would fail
the totality property as soon as Hypothesis drew a _ProcessExited(exit_code=2, ...).
"""
from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from codegenie.probes._shared.scanner_outcome import (
    ScannerOutcome, ScannerRan, ScannerSkipped, ScannerFailed,
)
from codegenie.probes.layer_g.semgrep import (
    _ProcessExited as SgExited, _ToolMissing as SgMissing, _ProcessTimedOut as SgTO,
    _classify_semgrep_outcome,
)


@given(
    exit_code=st.integers(min_value=-128, max_value=255),
    stdout=st.binary(max_size=4096),
    stderr_tail=st.text(max_size=512),
)
def test_semgrep_classifier_is_total_on_process_exited(exit_code, stdout, stderr_tail):
    """T3-Semgrep totality: every (exit_code, stdout, stderr_tail) →
    exactly one ScannerOutcome variant; never raises."""
    attempt = SgExited(exit_code=exit_code, stdout=stdout, stderr_tail=stderr_tail)
    outcome = _classify_semgrep_outcome(attempt)
    assert isinstance(outcome, (ScannerRan, ScannerSkipped, ScannerFailed))


def test_semgrep_classifier_is_total_on_tool_missing():
    """T3-Semgrep: tool-missing always → ScannerSkipped(tool_missing)."""
    outcome = _classify_semgrep_outcome(SgMissing())
    assert isinstance(outcome, ScannerSkipped)
    assert outcome.reason == "tool_missing"


def test_semgrep_classifier_is_total_on_timeout():
    """T3-Semgrep: timeout always → ScannerFailed(exit_code=124)."""
    outcome = _classify_semgrep_outcome(SgTO())
    assert isinstance(outcome, ScannerFailed)
    assert outcome.exit_code == 124
```

```python
# tests/unit/probes/layer_g/test_scanner_loc_ceiling.py
"""Architectural tests for Layer G scanners (S6-06)."""
from __future__ import annotations

import ast
import importlib
import inspect

import pytest

SCANNER_MODULES = [
    "codegenie.probes.layer_g.semgrep",
    "codegenie.probes.layer_g.ast_grep",
    "codegenie.probes.layer_g.ripgrep_curated",
]


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_each_scanner_under_200_loc(module_path):
    """AC-2. A scanner past 200 LOC is the signal that either (a) the
    scanner's contract is genuinely complex (split it), or (b) a shared
    kernel is overdue (extract to `_shared.scanner_common`, additive
    new module, not edits to existing scanners). The ceiling forces the
    conversation."""
    mod = importlib.import_module(module_path)
    src_path = inspect.getsourcefile(mod)
    assert src_path is not None
    with open(src_path) as f:
        line_count = sum(1 for _ in f)
    assert line_count <= 200, f"{module_path} has {line_count} LOC (ceiling 200)"


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_no_shared_scanner_base_class_via_ast(module_path):
    """AC-8 (AST audit, not source-grep — defeats string-concat bypass).
    A future contributor extracting a `ScannerRunner` / `BaseScanner` /
    `AbstractScanner` base fails this immediately. final-design row 7."""
    mod = importlib.import_module(module_path)
    tree = ast.parse(inspect.getsource(mod))
    forbidden_class_names = {"ScannerRunner", "BaseScanner", "AbstractScanner"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            assert node.name not in forbidden_class_names
            for base in node.bases:
                if isinstance(base, ast.Name):
                    assert base.id not in forbidden_class_names
                elif isinstance(base, ast.Attribute):
                    assert base.attr not in forbidden_class_names


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_no_cross_scanner_imports(module_path):
    """AC-8. Each scanner imports zero from its siblings."""
    mod = importlib.import_module(module_path)
    tree = ast.parse(inspect.getsource(mod))
    sibling_paths = {p for p in SCANNER_MODULES if p != module_path}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module not in sibling_paths


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_no_direct_subprocess_or_asyncio_spawn(module_path):
    """AC-16 (AST audit). Bypassing run_external_cli would skip
    env-strip, the 64 MB tail-cap, and the optional bwrap wrap."""
    mod = importlib.import_module(module_path)
    tree = ast.parse(inspect.getsource(mod))
    forbidden = {
        ("subprocess", "run"), ("subprocess", "Popen"),
        ("asyncio", "create_subprocess_exec"), ("asyncio", "create_subprocess_shell"),
        ("os", "system"), ("os", "popen"),
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            assert (node.value.id, node.attr) not in forbidden, (
                f"{module_path} calls {node.value.id}.{node.attr} directly"
            )


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_no_run_allowlisted_import_in_layer_g(module_path):
    """AC-16. Layer G uses the `run_external_cli` wrapper exclusively;
    `run_allowlisted` is reserved for Layer C (`docker`, `strace`)."""
    mod = importlib.import_module(module_path)
    src = inspect.getsource(mod)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                assert alias.name != "run_allowlisted"


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_each_scanner_imports_run_external_cli(module_path):
    """AC-16. Positive structural check: every scanner imports the
    wrapper from the canonical kernel module."""
    mod = importlib.import_module(module_path)
    tree = ast.parse(inspect.getsource(mod))
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "codegenie.exec":
            for alias in node.names:
                if alias.name == "run_external_cli":
                    found = True
    assert found, f"{module_path} does not import run_external_cli from codegenie.exec"


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_no_platform_detection_in_probe(module_path):
    """AC-14. The platform-detection / bwrap-availability concern lives
    entirely inside `run_external_cli` (S1-07); each layer_g probe is
    platform-independent."""
    mod = importlib.import_module(module_path)
    tree = ast.parse(inspect.getsource(mod))
    forbidden_attrs = {
        ("sys", "platform"), ("platform", "system"),
        ("shutil", "which"),
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            assert (node.value.id, node.attr) not in forbidden_attrs


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_each_scanner_class_attributes_pinned(module_path):
    """AC-B1. Mirror S5-04 K5 + S6-05 AC-NEW pattern. Every probe pins
    the eight ABC class attributes."""
    mod = importlib.import_module(module_path)
    probe_class = next(
        c for _, c in inspect.getmembers(mod, inspect.isclass)
        if c.__module__ == module_path and hasattr(c, "layer")
    )
    assert probe_class.layer == "G"
    assert probe_class.tier == "base"
    assert probe_class.applies_to_tasks == ["*"]
    assert probe_class.applies_to_languages == ["*"]
    assert probe_class.requires == []
    assert isinstance(probe_class.timeout_seconds, int)
    assert isinstance(probe_class.declared_inputs, list)
    assert isinstance(probe_class.name, str)
    assert probe_class.name == module_path.rsplit(".", 1)[-1]
```

Equivalent test files `test_ast_grep.py` and `test_ripgrep_curated.py` mirror the semgrep file: same monkeypatch / argv-capture pattern; same AC mapping; per-probe argv flags; **default error convention** (any non-zero exit → `ScannerFailed`, **with the exception** of ripgrep's exit-code-1-means-no-matches carve-out — see implementation outline §3 and `test_ripgrep_exit_code_1_is_no_matches`); per-probe Hypothesis totality property test (in `test_classifier_totality.py` for all three).

### Mutation-resistance smoke (T5 — mirror S5-04 / S6-05)

Per-scanner table in `tests/unit/probes/layer_g/test_<scanner>_mutation_smoke.py` that lists 6+ intentionally-wrong stub implementations:

| Stub | Mutation | Catching test(s) |
|---|---|---|
| always returns `ScannerRan(findings=[])` regardless of exit code | drops exit-code carve-out | `test_*_exit_code_2_is_scanner_failed`, `test_*_invalid_json_yields_scanner_failed_invalid_json` |
| always returns `ScannerSkipped(reason="tool_missing")` | swallows actual results | `test_*_argv_includes_*`, `test_*_empty_findings_yields_scanner_ran_high_confidence` |
| always returns `ScannerFailed(exit_code=0, stderr_tail="")` | inverts the outcome polarity | `test_*_empty_findings_*`, `test_*_tool_missing_yields_scanner_skipped` |
| silent `except ValidationError: return ScannerRan(findings=[])` | swallow on parse failure | `test_*_invalid_json_yields_scanner_failed_invalid_json` |
| raises `ToolMissingError` past the probe boundary | breaks coordinator isolation | `test_*_tool_missing_yields_scanner_skipped` (asserts a `ProbeOutput`, not a raise) |
| treats semgrep exit 1 as failure | breaks the carve-out (semgrep only) | `test_semgrep_exit_code_1_is_findings_not_failure` |
| treats ripgrep exit 1 as failure | breaks the no-matches carve-out (ripgrep only) | `test_ripgrep_exit_code_1_is_no_matches` |
| writes the raw file on `ScannerFailed` | violates ADR-0005 no-plaintext on malformed | `test_*_does_not_write_raw_on_failure` |

A meta-test loads each stub via `monkeypatch.setattr` on `_classify_<scanner>_outcome` (or on `run_external_cli` for I/O-side mutations) and asserts at least one named test in the per-scanner suite fails.

```python
# tests/unit/probes/layer_g/test_scanner_loc_ceiling.py
"""Architectural tests for Layer G scanners (S6-06)."""
from __future__ import annotations

import ast
import importlib
import inspect

import pytest

SCANNER_MODULES = [
    "codegenie.probes.layer_g.semgrep",
    "codegenie.probes.layer_g.ast_grep",
    "codegenie.probes.layer_g.ripgrep_curated",
]


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_each_scanner_under_200_loc(module_path: str) -> None:
    """AC-2. Mutation caught: a scanner creeping past 200 LOC is the
    signal that either the scanner's contract is complex enough to
    warrant a split, OR a shared kernel is overdue. The ceiling forces
    the conversation."""
    mod = importlib.import_module(module_path)
    src_path = inspect.getsourcefile(mod)
    assert src_path is not None
    line_count = sum(1 for _ in open(src_path))
    assert line_count <= 200, f"{module_path} has {line_count} LOC"


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_no_shared_scanner_base_class_import(module_path: str) -> None:
    """AC-8. Mutation caught: a future contributor extracting a
    `ScannerRunner` / `BaseScanner` base class — final-design
    Design-patterns row 7 forbids it."""
    mod = importlib.import_module(module_path)
    src = inspect.getsource(mod)
    for forbidden in ("ScannerRunner", "BaseScanner", "AbstractScanner"):
        assert forbidden not in src, (
            f"{module_path} references {forbidden!r}; the final-design table "
            "row 7 forbids this abstraction (SRP + Rule of Three)."
        )


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_no_cross_scanner_imports(module_path: str) -> None:
    """AC-8. Mutation caught: importing one scanner from another."""
    mod = importlib.import_module(module_path)
    src = inspect.getsource(mod)
    for sibling in SCANNER_MODULES:
        if sibling == module_path:
            continue
        assert sibling not in src


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_no_direct_subprocess_calls(module_path: str) -> None:
    """AC-16. Mutation caught: bypassing run_external_cli would skip
    env-strip, the 64 MB cap, and the asyncio timeout."""
    mod = importlib.import_module(module_path)
    tree = ast.parse(inspect.getsource(mod))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr in {"run", "Popen", "create_subprocess_exec", "create_subprocess_shell"}:
                # Check if the value is `subprocess` or `asyncio`.
                if isinstance(node.value, ast.Name) and node.value.id in {"subprocess", "asyncio"}:
                    pytest.fail(f"{module_path} calls {node.value.id}.{node.attr} directly")


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_each_scanner_routes_through_run_external_cli(module_path: str) -> None:
    """AC-16. Mutation caught: any future direct invocation that
    bypasses the chokepoint."""
    mod = importlib.import_module(module_path)
    src = inspect.getsource(mod)
    assert "run_external_cli" in src
```

Equivalent test files `test_ast_grep.py` and `test_ripgrep_curated.py` mirror the semgrep file but with their per-scanner argv, stdout shapes, and the default-error convention (non-zero = failure, no exit-code-1-is-findings carve-out).

### Green — make it pass

Skeleton for `semgrep.py` (~170 LOC including classifier + tagged union). The shape mirrors `src/codegenie/probes/layer_c/sbom.py` (S5-04, the canonical scanner-probe precedent):

```python
# src/codegenie/probes/layer_g/semgrep.py
"""SemgrepProbe — Layer G, medium heaviness.

Runs semgrep via :func:`~codegenie.exec.run_external_cli` (S1-07) and
classifies the attempt into a typed
:data:`~codegenie.probes._shared.scanner_outcome.ScannerOutcome` (S5-01).

Load-bearing carve-out: semgrep's documented exit-code convention
treats exit 0 = "no findings" and exit 1 = "findings present" as BOTH
success (parse stdout); only exit >= 2 is a real error. This carve-out
is the textbook reason a shared ``ScannerRunner`` base would be wrong
(``phase-arch-design.md §"Design patterns applied" row 7``).

The five-step shape lives inline by design — but the I/O is concentrated
in :meth:`SemgrepProbe._attempt` (the imperative shell) and the
classification is a pure, total function :func:`_classify_semgrep_outcome`
over a private tagged union :data:`SemgrepAttempt` (the functional core).
Property-based totality is pinned by
``tests/unit/probes/layer_g/test_classifier_totality.py``.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/S6-06-layer-g-curated-scanners.md``
- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md``
  §"Component design" #5, §"Design patterns applied" row 7.
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0001-...md`` —
  ``semgrep`` allowlist entry.
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0006-...md`` —
  ``ScannerOutcome`` closed-set discipline.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from codegenie.errors import ProbeTimeoutError, ToolMissingError
from codegenie.exec import ProcessResult, run_external_cli
from codegenie.output.paths import raw_dir
from codegenie.probes._shared.scanner_outcome import (
    STDERR_TAIL_CAP_BYTES,
    ScannerFailed,
    ScannerOutcome,
    ScannerRan,
    ScannerSkipped,
)
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe
from codegenie.types.identifiers import ProbeId

__all__ = ["SemgrepProbe", "SemgrepFinding", "SemgrepSlice"]

_PROBE_ID: Final[ProbeId] = ProbeId("semgrep")
_TIMEOUT_S: Final[int] = 60
_SLICE_FILENAME: Final[str] = "semgrep.json"
_RAW_TOOL_FILENAME: Final[str] = "semgrep-raw.json"
_DEFAULT_CONFIG: Final[str] = "p/nodejs"


# ---------- Models -----------------------------------------------------------

class SemgrepFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    check_id: str
    path: str
    line: int
    severity: Literal["info", "warning", "error"]
    message: str


class SemgrepSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    outcome: ScannerOutcome
    findings_detail: list[SemgrepFinding]
    rules_run: int | None
    files_scanned: int | None


# ---------- Private tagged union: SemgrepAttempt -----------------------------

@dataclass(frozen=True)
class _ToolMissing:
    pass


@dataclass(frozen=True)
class _ProcessTimedOut:
    pass


@dataclass(frozen=True)
class _ProcessExited:
    exit_code: int
    stdout: bytes
    stderr_tail: str


SemgrepAttempt = _ToolMissing | _ProcessTimedOut | _ProcessExited


# ---------- Pure helpers -----------------------------------------------------

def _stderr_tail(b: bytes) -> str:
    return b[-STDERR_TAIL_CAP_BYTES:].decode("utf-8", errors="replace")


def _parse_semgrep_stdout(stdout: bytes) -> tuple[list[SemgrepFinding], int | None, int | None]:
    """Parse semgrep JSON; raises ValidationError or JSONDecodeError on bad input."""
    data = json.loads(stdout)
    if not isinstance(data, dict) or "results" not in data:
        raise ValueError("semgrep stdout missing 'results' key")
    findings: list[SemgrepFinding] = []
    for r in data["results"]:
        findings.append(SemgrepFinding(
            check_id=r["check_id"],
            path=r["path"],
            line=r["start"]["line"],
            severity=r["extra"]["severity"].lower(),
            message=r["extra"]["message"],
        ))
    paths = data.get("paths", {})
    files_scanned = len(paths.get("scanned", [])) if isinstance(paths, dict) else None
    rules_run = len({f.check_id for f in findings}) or None
    return findings, files_scanned, rules_run


# ---------- Pure, total classifier ------------------------------------------

def _classify_semgrep_outcome(
    attempt: SemgrepAttempt,
) -> tuple[ScannerOutcome, list[SemgrepFinding], int | None, int | None]:
    """Total over SemgrepAttempt; never raises. Returns (outcome, findings_detail, rules_run, files_scanned)."""
    match attempt:
        case _ToolMissing():
            return ScannerSkipped(reason="tool_missing"), [], None, None
        case _ProcessTimedOut():
            return ScannerFailed(exit_code=124, stderr_tail="semgrep.timeout"), [], None, None
        case _ProcessExited(exit_code=ec, stdout=stdout, stderr_tail=tail):
            # Carve-out: exit 0 or 1 = success; >= 2 = real error.
            if ec >= 2:
                return ScannerFailed(exit_code=ec, stderr_tail=tail), [], None, None
            try:
                findings, fs, rr = _parse_semgrep_stdout(stdout)
            except (json.JSONDecodeError, ValidationError, KeyError, ValueError):
                return (
                    ScannerFailed(exit_code=ec, stderr_tail=tail, reason="invalid_json"),
                    [], None, None,
                )
            return ScannerRan(findings=[]), findings, rr, fs


# ---------- Probe ------------------------------------------------------------

@register_probe(heaviness="medium", runs_last=False)
class SemgrepProbe(Probe):
    name: str = "semgrep"
    version: str = "0.1.0"
    layer = "G"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    declared_inputs: list[str] = ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx"]
    timeout_seconds: int = _TIMEOUT_S

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        attempt = await self._attempt(repo.root, ctx.config)
        outcome, findings_detail, rules_run, files_scanned = _classify_semgrep_outcome(attempt)
        slice_model = SemgrepSlice(
            outcome=outcome,
            findings_detail=findings_detail,
            rules_run=rules_run,
            files_scanned=files_scanned,
        )
        slice_dict = slice_model.model_dump(mode="json")
        raw_bytes = attempt.stdout if isinstance(attempt, _ProcessExited) and isinstance(outcome, ScannerRan) else b""
        artifacts = _write_files(repo.root, slice_dict, raw_bytes)
        confidence: Literal["high", "medium", "low"] = "high" if isinstance(outcome, ScannerRan) else "low"
        return self._envelope(slice_dict, artifacts, confidence, t0)

    @staticmethod
    async def _attempt(repo_root: Path, config: dict[str, Any]) -> SemgrepAttempt:
        cfg = str(config.get("semgrep_config", _DEFAULT_CONFIG))
        try:
            result: ProcessResult = await run_external_cli(
                _PROBE_ID,
                ["semgrep", "--config", cfg, "--json", "--metrics=off", "--quiet", str(repo_root)],
                cwd=repo_root,
                timeout_s=float(_TIMEOUT_S),
            )
        except ToolMissingError:
            return _ToolMissing()
        except ProbeTimeoutError:
            return _ProcessTimedOut()
        return _ProcessExited(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr_tail=_stderr_tail(result.stderr),
        )

    @staticmethod
    def _envelope(
        slice_dict: dict[str, Any],
        raw_artifacts: list[Path],
        confidence: Literal["high", "medium", "low"],
        t0: float,
    ) -> ProbeOutput:
        return ProbeOutput(
            schema_slice={"semgrep": slice_dict},
            raw_artifacts=raw_artifacts,
            confidence=confidence,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=[],
            errors=[],
        )


def _write_files(repo_root: Path, slice_dict: dict[str, Any], tool_bytes: bytes) -> list[Path]:
    rd = raw_dir(repo_root)
    rd.mkdir(parents=True, exist_ok=True)
    slice_path = rd / _SLICE_FILENAME
    slice_path.write_text(json.dumps(slice_dict, sort_keys=True))
    out = [slice_path]
    if tool_bytes:  # AC-W1: raw only on ScannerRan
        tool_path = rd / _RAW_TOOL_FILENAME
        tool_path.write_bytes(tool_bytes)
        out.append(tool_path)
    return out
```

`ast_grep.py` and `ripgrep_curated.py` mirror this shape line-for-line: same module-constant pattern, same private tagged union `<Scanner>Attempt`, same pure classifier `_classify_<scanner>_outcome`, same `_envelope` helper and two-file writer, same ABC class-attribute block. **They differ only in:** per-scanner argv, per-scanner Finding model, per-scanner stdout parser (NDJSON for ast-grep and ripgrep), and per-scanner exit-code convention (ast-grep: default; ripgrep: exit-1-is-no-matches carve-out, mirror of semgrep's discipline). **None imports the other.**

### Refactor

1. **Pure-total classifier per scanner.** Extract the `match attempt:` block as a free function with three explicit `case` arms (`_ToolMissing`, `_ProcessTimedOut`, `_ProcessExited`). The exhaustiveness is enforced by `mypy --warn-unreachable` (Phase 2 ADR-0006 §"Consumer discipline"); the totality property is enforced by `tests/unit/probes/layer_g/test_classifier_totality.py`. **Do not extract a `_classify_scanner_outcome(...)` shared kernel** — the carve-out shapes differ (semgrep: exit 0+1 success; ripgrep: exit 0+1 success; ast-grep: exit 0 success; gitleaks: exit 0 + exit 1 carries a "secrets found" signal), so a "generic" version parameterized by `success_codes: frozenset[int]` would push the carve-out into a config dict — the exact obfuscation final-design row 7 rejects.
2. **`Final[...]` annotations on every module constant.** `_PROBE_ID`, `_TIMEOUT_S`, `_SLICE_FILENAME`, `_RAW_TOOL_FILENAME`, `_DEFAULT_CONFIG`, `_CURATED_PATTERNS` (ripgrep). The annotation buys mypy's rebinding backstop — a future contributor who does `_TIMEOUT_S = 30` mid-module fails type-check.
3. **Two-file write split**, AC-W1. The typed slice JSON is `read_raw_slices`-keyed (downstream sibling consumers); the raw scanner bytes are audit-only. Failure paths write only the slice; the raw file is never persisted with malformed bytes (ADR-0005 hygiene).
4. **No `_call_scanner(name, argv, timeout) -> ScannerOutcome` helper.** Even though all three scanners have a `try: run_external_cli except ToolMissingError except ProbeTimeoutError` block, the carve-outs differ (semgrep exit-1, ripgrep exit-1, ast-grep default). A generic wrapper either (a) silently mis-classifies one scanner's carve-out as failure, or (b) parameterizes the success-codes set, which is the inline-conditional in different syntax. Inline is honest.
5. **Rule-of-three trigger for `codegenie.probes._shared.scanner_common`.** When S6-07 (`gitleaks.py`) lands, three of the four scanners will share verbatim: (a) `_ToolMissing` / `_ProcessTimedOut` / `_ProcessExited` dataclass triple (b) `_stderr_tail` helper (c) `_envelope` static method shape. **At that point — not before** — extract these to a new module `codegenie/probes/_shared/scanner_common.py`. Imports of `_ToolMissing` / `_ProcessTimedOut` / `_ProcessExited` / `_stderr_tail` move from per-scanner modules to the shared module; per-scanner classifiers and Finding models stay. This is "extract by addition" — a new module, not edits to existing scanner files (`final-design.md` row 7 admits `_shared/` as the kernel level; the discipline forbids only a shared **class/base**).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/layer_g/__init__.py` | New file — package marker. Explicit-import the three new probe classes so the registry decorator runs at coordinator-import time (mirrors `src/codegenie/probes/__init__.py` convention). |
| `src/codegenie/probes/layer_g/semgrep.py` | New file ≤ 200 LOC. Pure-total `_classify_semgrep_outcome`; exit-1-is-findings carve-out. |
| `src/codegenie/probes/layer_g/ast_grep.py` | New file ≤ 200 LOC. NDJSON parser; default error convention. |
| `src/codegenie/probes/layer_g/ripgrep_curated.py` | New file ≤ 200 LOC. NDJSON parser; exit-1-is-no-matches carve-out; closed `_CURATED_PATTERNS` `Final[tuple[str, ...]]`. |
| `src/codegenie/probes/__init__.py` | **One line each** — three additive imports for the new modules (Open/Closed at the file boundary; no edits to existing imports). |
| `tests/unit/probes/layer_g/__init__.py` | New file — empty marker. |
| `tests/unit/probes/layer_g/conftest.py` | New file — `_make_repo()` / `_make_ctx()` fixtures (mirror `tests/unit/probes/layer_c/conftest.py` shape). |
| `tests/unit/probes/layer_g/test_semgrep.py` | New file — ~14 tests (AC-5, AC-9, AC-10, AC-12, AC-13, AC-15 x2, AC-T1, AC-E1, AC-B1, AC-N1, AC-R1, AC-W1 x2). |
| `tests/unit/probes/layer_g/test_ast_grep.py` | New file — ~12 tests mirroring semgrep (default error convention). |
| `tests/unit/probes/layer_g/test_ripgrep_curated.py` | New file — ~13 tests mirroring semgrep (NDJSON parse, curated-pattern set, exit-1-is-no-matches carve-out, `-e` prefix on every pattern). |
| `tests/unit/probes/layer_g/test_classifier_totality.py` | New file — Hypothesis property test per scanner (T3). |
| `tests/unit/probes/layer_g/test_scanner_loc_ceiling.py` | New file — 8 parametrized architectural tests across all three modules (AC-2, AC-8 AST audit, AC-14 AST audit, AC-16 AST audit + positive run_external_cli import check, AC-B1 ABC attrs). |
| `tests/unit/probes/layer_g/test_semgrep_mutation_smoke.py` | New file — mutation-resistance smoke table (T5). |
| `tests/unit/probes/layer_g/test_ast_grep_mutation_smoke.py` | New file — same. |
| `tests/unit/probes/layer_g/test_ripgrep_curated_mutation_smoke.py` | New file — same. |

## Out of scope

- **`GitleaksProbe`.** S6-07 (load-bearing security scanner; isolated so review pressure doesn't collapse the four into a shared abstraction).
- **`TestCoverageMappingProbe`.** S6-08 (Layer G but a different shape — reads coverage data, not a CLI tool with a scanning convention).
- **Custom rule pack authoring.** This story uses the curated packs (`p/nodejs`, `p/dockerfile`, etc.); the `semgrep_config` is overridable via `ctx.config["semgrep_config"]`.
- **Cross-validation between semgrep + ast-grep findings.** Each scanner emits independently; the Planner correlates if it wants.
- **`SecretRedactor` invocation.** That's the writer chokepoint's job (S3-03). The probes return raw findings; the writer redacts before disk.

## Notes for the implementer

1. **The "no shared `ScannerRunner` base class" discipline is the story's whole point.** A reviewer who asks "why is this duplicated" gets the same answer the design table gives: Rule of Three + four genuinely different I/O shapes + semgrep's exit-code-1-is-findings carve-out + ripgrep's exit-code-1-is-no-matches carve-out. If you find yourself writing the third copy and reaching for a base class, **the right move is to write the third copy** and move on. The fourth copy (gitleaks, S6-07) lives in its own story to make the discipline visible in the PR queue. **The discipline is "no shared class/base", not "no shared module"** — helper-level sharing under `_shared/` is admitted by final-design row 7 (`ScannerOutcome` itself is the precedent).
2. **Rule-of-three trigger for `_shared.scanner_common` (S6-07 author, read me).** When `gitleaks.py` lands, three of the four scanners will share verbatim: (a) `_ToolMissing` + `_ProcessTimedOut` + `_ProcessExited` dataclass triple, (b) `_stderr_tail` helper, (c) `_envelope` static method shape. At that point — **not before** — extract these to a new module `src/codegenie/probes/_shared/scanner_common.py`. Imports of the dataclass triple + helpers move from per-scanner modules to the shared module; **per-scanner classifiers and Finding models stay** (they encode the carve-outs and the rich shape, both of which are scanner-specific). This is the canonical "extract by addition": new module, no edits to existing scanner files.
3. **`run_external_cli` is the *only* subprocess door.** Direct `subprocess.run` / `asyncio.create_subprocess_exec` / `os.system` calls bypass env strip + the 64 MB tail-truncation + the optional bwrap wrap. AC-16's AST audit enforces this — any future violation fires immediately and points at the chokepoint. `run_allowlisted` is also forbidden in `layer_g/` (Layer C reserve only).
4. **Repo-precedent mocking is `monkeypatch.setattr(<scanner_module>, "run_external_cli", _spy)`** — NOT `pytest-subprocess`. `pytest-subprocess` is not in `pyproject.toml`'s dev-deps; the wrapper itself is exercised by `tests/unit/exec/test_run_external_cli.py` (S1-07's own test suite, 100+ tests already pinning env-strip, cap-truncation, bwrap, timeouts). Scanner tests pin the **probe-side contract surface only** (correct `_PROBE_ID`, correct argv, correct `cwd`, correct `timeout_s`, correct error-handling on each typed exception). See `tests/unit/probes/layer_c/test_sbom.py` and `test_cve.py` for the canonical pattern (10+ call sites already).
5. **`--metrics=off` for semgrep is belt-and-suspenders.** The env-strip in `run_external_cli._filter_env` is the structural defense (it drops `SEMGREP_SEND_METRICS` and `SEMGREP_USER_AGENT` from the child env on every call). `--metrics=off` is the second layer — if a future maintainer accidentally widens the env allowlist, the argv flag still refuses phone-home. Both must hold; AC-5's captured-argv spy pins the argv side.
6. **Semgrep's exit-code convention is the load-bearing example.** Exit 0 = no findings, parsed normally → `ScannerRan(findings=[])` with `findings_detail=[]` and `confidence="high"`. Exit 1 = findings present, parsed normally → `ScannerRan(findings=[])` with `findings_detail` populated and `confidence="high"`. Exit 2+ = error, no parse → `ScannerFailed(exit_code, stderr_tail)` and `confidence="low"`. The shared-`ScannerRunner` abstraction would either (a) lose this nuance and treat exit 1 as failure (silent bug), or (b) parameterize the success-codes per scanner — which is the inline-conditional in different syntax. Inline is honest.
7. **Ripgrep's exit-code convention has its own carve-out: exit 1 = no matches.** `rg` exits 1 when zero matches are found and 2 on real error. The classifier must mirror semgrep's shape with `exit_code in (0, 1)` → parse-stdout (yielding `ScannerRan(findings=[])` and empty `findings_detail`), `exit_code >= 2` → `ScannerFailed`. **This is the second textbook example of why a shared abstraction is wrong** — the success-codes set differs per scanner (semgrep: {0, 1}; rg: {0, 1}; ast-grep: {0}; gitleaks: documented exit-1-on-findings, also a carve-out, see S6-07).
8. **Ripgrep's curated pattern set is closed.** Adding a new pattern is a code change with a test fixture, not a config option. The pattern list lives in `_CURATED_PATTERNS: Final[tuple[str, ...]]` — a future contributor adding patterns must update both the constant and the per-pattern argv-position test in `test_ripgrep_curated.py`. Each pattern is prefixed with `-e` in `_PATTERN_ARGS` so rg parses it as a regex (not a path); without `-e` a leading `/` like `/bin/` would be interpreted as a filesystem path.
9. **`--max-count 100` is per-file** (rg's documented semantics — caps matches per file per pattern, not per-pattern globally). The original story claim ("per-pattern, per-file") is precise about the per-file bound; the per-pattern interaction is via the `-e` prefix. Without the cap, an `LD_LIBRARY_PATH` hit in 5,000 files would emit 5,000 JSON lines and risk the 64 MB tail-truncation path.
10. **`ast-grep --json=stream` over `--json=compact`.** Stream emits one JSON object per line (NDJSON); compact emits a single buffered array. NDJSON peak memory is O(one finding); compact is O(all findings). The 64 MB cap is on the *wire*, but stream lets the probe parse incrementally — a future enhancement, not a Phase-2 requirement, but the flag choice keeps the door open.
11. **`ScannerOutcome` is the shared sum type (S5-01); each scanner's rich `Finding` model lives on the SLICE, not on `ScannerRan.findings`.** The discipline is: share the **outcome** (typed sum across all scanners — `ScannerRan` / `ScannerSkipped` / `ScannerFailed` with closed `reason` enums per ADR-0006), don't share the **inputs** (different field shapes per scanner). `ScannerRan.findings` stays as the empty `list[Finding]` (the closed sum's contract); the rich shape lives in slice's `findings_detail: list[<Scanner>Finding]`. Sibling consumers `match` on the outcome discriminator; rich consumers (renderer, Phase-3 planner) read the slice. A `BaseFinding` class with `file: str, line: int` would force every scanner's quirks into a lowest common denominator — exactly the inheritance-for-reuse pattern `phase-arch-design.md §"Anti-patterns avoided"` calls out.
12. **Dual-form identity is non-negotiable.** Module-level `_PROBE_ID: Final[ProbeId] = ProbeId("<scanner>")` is what feeds `run_external_cli(probe_name=_PROBE_ID, ...)` (it flows into `tempfile.mkdtemp(prefix=...)` on the bwrap path — `ProbeId` is validated against `^[a-z][a-z0-9_]{0,63}$`). Class-level `name: str = "<scanner>"` is what the kernel introspects for dispatch and reporting. Both strings AND the filename stem are equal. AC-N1's test asserts the three are pinned together — drift means either argv-validation fails or kernel dispatch silently breaks.
13. **`mypy --strict` + `--warn-unreachable`** is what makes the `match attempt:` block in each classifier exhaustive. The three `case` arms (`_ToolMissing`, `_ProcessTimedOut`, `_ProcessExited`) cover the full union; mypy errors on a missed case statically. The property-based totality test (`test_classifier_totality.py`) is the runtime backstop — it draws random `ScannerAttempt`s and asserts the classifier returns exactly one `ScannerOutcome` variant and never raises.
14. **02-ADR-0006 closed-set discipline is the hard constraint.** `ScannerSkipped.reason` is `Literal["tool_missing", "tool_unhealthy", "upstream_unavailable"]`. `ScannerFailed.reason` is `Literal["invalid_json", "sbom_artifact_missing"] | None`. Inventing `"output_too_large"` (the original AC-13's draft) is a validation error at construction time — the smart constructor refuses it. If a Phase-3+ scanner genuinely needs a new `reason` value, the path is an ADR amendment to 02-ADR-0006, not a `metadata: dict` escape hatch.
