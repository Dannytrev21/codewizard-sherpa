# Validation report — S5-02 `RuntimeTraceProbe` (sequential 5-scenario harness + image-digest token)

**Story:** [`../S5-02-runtime-trace-probe.md`](../S5-02-runtime-trace-probe.md)
**Validated:** 2026-05-16
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

`RuntimeTraceProbe` is "the single most valuable probe for distroless confidence" (`localv2.md §5.3 C4`) and the densest single probe in Phase 2. The draft was structurally sound — sequential per-scenario discipline, container hardening triple, image-digest cache token, macOS-permanent fallback, writer-chokepoint redaction were all named correctly and trace cleanly to `02-ADR-0001`, `02-ADR-0003`, `02-ADR-0004`, `02-ADR-0007`, and `phase-arch-design.md §"Component design" #6`. But four classes of problem surfaced under the four critics and could not be ignored:

1. **Contract violation (block).** The draft prescribes `ProbeOutput.confidence="unavailable"` four times. The frozen `Probe` contract at `src/codegenie/probes/base.py:68` (and `localv2.md §4 line 328`) types it `Literal["high", "medium", "low"]`. ADR-0007 makes this surface ungrowable without a contract amendment that explicitly does NOT exist. The fix routes `"unavailable"` to the slice's `trace_coverage_confidence` and pins the envelope's `confidence` at `"low"` per the contract.
2. **Variant-location conflict with S5-01 (block).** Draft AC-12 / AC-13 emit `TraceScenarioSkipped(reason=ImageDigestUnresolved())`. S5-01's HARDENED variant set places `ImageDigestUnresolved` in `TraceFailureReason`, NOT `TraceSkipReason`. Editing S5-01 to relocate is non-surgical (Rule 3) and would invert S5-01's validated discipline. Resolution: `image_digest_resolver` returning/being `None` emits `TraceScenarioFailed(reason=ImageDigestUnresolved())` (not Skipped), because semantically the scenario *was* attempted but failed at the digest-resolution prerequisite. `docker build` failure remains `TraceScenarioSkipped(reason=ImageBuildUnavailable())` (the existing S5-01 skip variant).
3. **Phase-0-cache extension not in scope of any prior story (block).** AC-2 + Context assert that "Phase 0 `Cache`'s special-token resolver calls `ctx.image_digest_resolver(repo_root)`" and AC-10 tests the cache HIT path. Inspection of `src/codegenie/cache/keys.py::declared_inputs_for` (lines 94–126) confirms this resolver does NOT exist — the function literally `rglob`s every entry in `declared_inputs` and silently drops non-matches. S1-09 added the `ProbeContext.image_digest_resolver` field but did NOT extend `cache/keys.py`. Since S1-09 is **Done** and S5-02 is the **first** consumer, S5-02 MUST land the `_resolve_special_token` dispatch arm itself (~30 LOC) with its own dedicated ACs. The token-recognition pattern is the right Open/Closed seam for future tokens (`scip-index-output:`, `tree-sitter-grammar-set:`, etc.) — landing it once via this story sets the precedent.
4. **Pattern under-specified (harden).** The draft has good patterns (sum-type discipline, sequential discipline, smart constructors for caps) but multiple seams that *should* be observable ACs are buried in `Notes for implementer`: pure parser, exhaustive `_aggregate_scenarios` match, hardening-flags-as-constant, image-ref smart constructor, pure argv builders, operator-extensibility for scenarios.yaml. Each becomes an explicit AC so the executor can verify it; pattern names stay in Notes per the skill's "ACs must be observable" rule.

Plus 5 smaller corrections: `_DEFAULT_SCENARIOS` type drift (list[str] vs list[ScenarioSpec]); the docstring citation `final-design.md §"Implementation risks" #7` does not exist (no such enumerated list — the sequential-scenario rationale lives in §"Components" #6 + §"Tradeoffs accepted" + §"Where security/best-practices traded off perf"); `_image_built` instance-local state is fragile under retry-reuse; the macOS-detection mechanism (`sys.platform` vs `os.uname().sysname`) needs pinning; bare-except resilience pattern not pinned.

Eighteen in-place edits applied; the story is now ready for `phase-story-executor`. No `NEEDS RESEARCH` findings — every gap was answerable from the existing codebase (`exec/__init__.py`, `cache/keys.py`, `probes/base.py`, `probes/layer_b/dep_graph.py` as the strategy-registry precedent), S5-01's HARDENED report, `02-ADR-0001/03/04/07`, `phase-arch-design.md §"Component design" #6`, `final-design.md §"Components" #6 + §"Tradeoffs accepted"`, and `localv2.md §4 + §5.3 C4`.

## Context Brief (Stage 1)

- **Goal as written:** Implement `src/codegenie/probes/layer_c/runtime_trace.py` — a heavy probe that runs five scenarios sequentially under container-hardening, captures syscalls via strace (Linux) or emits `StraceUnavailable` (macOS) deterministically, declares `image-digest:<resolved>` as a special declared-input token, round-trips through the writer chokepoint with `RedactedSlice`, and degrades gracefully when the image isn't built yet.
- **Phase 2 exit criteria touched:**
  - G1 — IndexHealthProbe surfaces ≥1 staleness case (S5-02 produces the `built_image_digest` / `last_traced_image_digest` slice fields B2 consumes; S5-05 wires the freshness check).
  - G3 — `localv2.md §5.3 C4` slice schema landed.
  - G9 — kernel scaffolding ships before consumers (this story is a Layer-C consumer of S5-01's `ScenarioResult`, S1-08's heaviness annotation, S1-09's `image_digest_resolver` field).
- **Load-bearing commitments touched:**
  - `production/design.md §2.1` — no LLM in gather. Probe is deterministic end-to-end.
  - `production/design.md §2.3` — honest confidence; this probe's slice carries `trace_coverage_confidence: high|medium|low|unavailable`.
  - `production/design.md §2.6` — extension by addition: adding a 6th scenario is a `scenarios.yaml` edit, not a code edit (operator-side Open/Closed).
  - `CLAUDE.md` "Determinism over probabilism" — sequential scenarios + macOS-`StraceUnavailable` are the deterministic shape.
  - `02-ADR-0001` — `docker`/`strace` direct via `run_allowlisted`, NOT through `run_external_cli`.
  - `02-ADR-0003` — `@register_probe(heaviness="heavy")` so coordinator schedules first.
  - `02-ADR-0004` — image digest is a `declared_inputs` special token, NOT a `cache_key()` override.
  - `02-ADR-0007` — no Plugin Loader; probe is in-tree under `probes/layer_c/`.
  - `02-ADR-0010` (cross) — `RedactedSlice` smart constructor at the writer boundary.
- **Open/Closed boundaries touched:**
  - **Operator-side (open):** A 6th scenario lands as a `scenarios.yaml` operator edit. Zero `runtime_trace.py` edit required.
  - **Canonical-defaults seam (deliberately closed/data-only):** Adding to `_DEFAULT_SCENARIOS` requires a `localv2.md §5.3 C4` doc amendment + module-constant edit. NOT a registry. Mirrors S5-01's sum-type discipline.
  - **Trace-backend seam (today: closed branch; future: Protocol):** Linux→strace; macOS→deterministic StraceUnavailable. A 3rd backend (Phase 5 microVM? Phase 7 dtrace?) becomes a `_TraceBackend` Protocol — refused today per Rule 2 (premature abstraction with only two variants).
  - **Cache special-token resolver (new — landed by this story):** `cache/keys.py::_resolve_special_token` dispatch arm. Today: one arm (`image-digest:`). Future tokens add arms via ADR amendment to 02-ADR-0004.
- **Sibling-family lineage:**
  - 1st canonical consumer of S5-01's `ScenarioResult` (S5-02 is the producer-of-results; S5-05 + S8-01 are downstream consumers via slice).
  - 1st canonical consumer of S1-08's `heaviness="heavy"` (the SCIPIndexProbe is registered heavy at S4-03 — landed earlier).
  - 1st canonical consumer of S1-09's `ProbeContext.image_digest_resolver`.
  - 1st (and so far only) Layer-C probe; it MUST set the precedent that Layer C calls `run_allowlisted` **directly** (no `run_external_cli` wrapper) per 02-ADR-0001.
- **Existing kernels to consume:**
  - `codegenie.exec.run_allowlisted` (Phase 0; allowlist extended for `docker`+`strace` by 02-ADR-0001).
  - `codegenie.cache.keys.declared_inputs_for` — TO BE EXTENDED with `_resolve_special_token` dispatch arm (this story).
  - `codegenie.probes.registry.register_probe` (`heaviness="heavy"`).
  - `codegenie.probes._shared.scanner_outcome` — NOT consumed (this probe emits `ScenarioResult`, not `ScannerOutcome`).
  - `codegenie.probes.layer_c.scenario_result.{TraceScenarioCompleted,TraceScenarioFailed,TraceScenarioSkipped,TraceFailureReason,TraceSkipReason}` (from S5-01).
  - `codegenie.parsers.safe_yaml.load` (Phase 1) — for `.codegenie/scenarios.yaml`.
  - `codegenie.output.SecretRedactor` + `RedactedSlice` (Phase 2 S3-01/S3-02/S3-03).
- **Existing files that may be edited (Rule 3 scope):**
  - `src/codegenie/cache/keys.py::declared_inputs_for` — **edit required** (extend with `_resolve_special_token`).
  - `src/codegenie/probes/base.py` — **not touched** (S1-09 already added `image_digest_resolver`).
  - `docs/localv2.md §4` — **not touched** (special-token form already permitted by `localv2.md §4`).
  - `pyproject.toml` `[tool.mypy]` — already repo-wide `warn_unreachable = true` (S1-11 / S5-01 finding) — no per-module override.
  - `scripts/check_forbidden_patterns.py` — extend if `probes/layer_c/runtime_trace.py` is not under an existing ban (verify; mirrors S5-01 NF-C).
- **Arch tension to flag:** The story cites `final-design.md §"Implementation risks" #7` (line 23, line 83, lines 131); `final-design.md` has no such enumeration. The sequential-scenario rationale lives in §"Components" #6, §"Tradeoffs accepted", and §"Where security/best-practices traded off perf" (a). Citation fix landed; do NOT edit `final-design.md` (Rule 3).

## Stage 2 — critic reports

### Coverage critic (verdict: COVERAGE-HARDEN with 1 block)

- **CF1 (block→harden).** `confidence="unavailable"` appears in the Goal (line 34) and AC-9 / AC-11 / AC-12 (lines 47, 49, 50). The frozen `Probe` contract (`src/codegenie/probes/base.py:68` and `localv2.md §4 line 328`) pins `confidence: Literal["high", "medium", "low"]` — no `"unavailable"`. mypy --strict would refuse the emission. ADR-0007 makes the surface ungrowable without amendment that does NOT exist in this story's dependencies. **Fix:** envelope `confidence` is `"low"` when ANY of the unavailable conditions fires; the slice's `trace_coverage_confidence` is `"unavailable"` (a Phase-2 extension of `localv2.md §5.3 C4`'s tri-state, surfaced explicitly as a documentation extension). Rewrite AC-9 / AC-11 / AC-12 + the Goal accordingly; add a new AC pinning the `confidence ∈ {"high", "medium", "low"}` contract preservation.
- **CF2 (harden).** AC-3 says `cache_strategy` is "NOT `none`" but does not pin the literal value. **Fix:** AC-3 asserts `cache_strategy: Literal["content"] = "content"` exactly (matches the `Probe.cache_strategy` default and the dep_graph/scip precedent).
- **CF3 (harden).** No AC pins the `image_ref` tag format. The implementation outline step 4f says `codegenie-trace:<short-digest>` but no test catches a regression to (e.g.) `codegenie:trace-<digest>` or `codegenie-trace:<full-digest>`. **Fix:** add AC requiring a pure helper `_image_ref_for_digest(digest: str) -> str` that returns exactly `"codegenie-trace:" + _short(digest)` where `_short` is the first 12 chars after stripping any `"sha256:"` prefix; a parametrized test pins the format.
- **CF4 (harden).** `scenarios_failed` derivation isn't anchored. Are `Skipped` scenarios in the `scenarios_failed` list? In `scenarios_run`? Neither? **Fix:** add AC pinning: `scenarios_run = [r.scenario_name for r in results if isinstance(r, TraceScenarioCompleted)]`; `scenarios_failed = [r.scenario_name for r in results if isinstance(r, TraceScenarioFailed)]`; Skipped scenarios appear in neither list, only in `per_scenario_artifacts` with a `None` value and in the structured log.
- **CF5 (harden).** `.codegenie/scenarios.yaml` with > 5 scenarios is unspecified. AC-4 says "Pydantic-validates against `ScenariosConfig` with required `scenarios: list[ScenarioSpec]`" but does not cap the list size or specify aggregate-timeout behavior. **Fix:** add AC pinning that the probe consumes ALL N declared scenarios; aggregate timeout `_AGGREGATE_TIMEOUT_S = 600` applies regardless; if N > 6 a structured-log WARN line is emitted naming the count (operator-discoverable, not a refusal).
- **CF6 (harden).** `image_digest_resolver` raising (not returning `None`) is unspecified. The story says "the probe never raises" (line 50) but only for None-return / None-binding paths. **Fix:** add AC pinning that any exception from `ctx.image_digest_resolver(repo_root)` is caught at the call site and translated to `TraceScenarioFailed(reason=ImageDigestUnresolved())` per scenario + structured log `image_digest_unresolved_reason="resolver_raised"`. A test mocks the resolver to raise; asserts the probe completes; asserts the structured-log field.
- **CF7 (block→harden).** The cache-HIT-via-image-digest test (AC-10, lines 48) presumes `cache/keys.py::declared_inputs_for` recognizes `image-digest:<resolved>` and resolves via `ctx.image_digest_resolver(snapshot.root)`. Inspection confirms this resolver does NOT exist. The literal pattern `image-digest:<resolved>` is silently rglobbed (zero matches) and dropped from the input list (`keys.py:113–125`). **Fix:** add three new ACs scoping the Phase-0-cache `_resolve_special_token` extension into this story (the first story to need the mechanism): (a) `cache/keys.py::declared_inputs_for` recognizes any string matching `r"^[a-z0-9_-]+:<resolved>$"` as a special token rather than a glob; (b) the `image-digest:` arm calls `ctx.image_digest_resolver(snapshot.root)` and folds the resulting digest string (or `None`-fallback) into the content-hash tuple alongside file content hashes; (c) unknown special tokens raise `CacheKeyError(reason="unknown_special_token", token=…)` — fail loud per Rule 12. Mirror the precedent that S1-08's heaviness lived inside the registry rather than as a probe-level override.
- **CF8 (harden).** No AC explicitly says the slice fields documented in `localv2.md §5.3 C4` (lines 859–890 in `localv2.md`) are the **complete** observable surface — a future drift adding a 13th slice field would slip through. **Fix:** add an `__all__`-style pin: a snapshot test asserts the slice dict's keys are EXACTLY the documented set (no extras, no missing — drift in either direction flips the test red).
- **CF9 (nit).** `wall_clock_ms` is named per `TraceScenarioCompleted` in S5-01 step 7 but not asserted at this story's level. **Fix:** AC-8's structured-log assertion (`probe.runtime_trace.scenario_finished` carries `wall_clock_ms`) already covers it.

### Test-Quality critic (verdict: TESTS-HARDEN)

Mutation analysis (15 plausible wrong implementations):

| # | Wrong implementation | Caught by draft TDD? | Severity |
|---|---|---|---|
| 1 | Use `asyncio.gather` over scenarios silently | **Yes** — Test 3 `test_concurrent_task_count_le_one` observes task count ≤ 1 at ≥10 sampled points | clean |
| 2 | Drop `--network=none` from `docker run` argv | **Yes** — Test 6 `test_hardening_flags_in_argv` | clean |
| 3 | Drop the explicit `--` separator before `docker` in strace argv | **No** — story says "explicit `--`" but Test 6 only set-checks the three flags | harden |
| 4 | Add `dtruss`/`sudo` to macOS path silently | **Yes** — Test 4 + Test 5 spy on `run_allowlisted` argv | clean |
| 5 | Use `os.uname()` vs `sys.platform` inconsistently (mock one, miss other) | **Partial** — AC line 46 parenthetical mentions both but only `sys.platform` is canonical in Test 4 | harden |
| 6 | Use `run_external_cli` for docker (wrong wrapper) | **Yes** — Test 7 source-grep | clean |
| 7 | `image_digest_resolver` raises silently swallowed | **No** — see CF6 | harden |
| 8 | `_parse_strace_lines` returns empty on malformed input silently | **Partial** — outline step 5 names a fixture but no AC asserts the parser's contract under malformed lines | harden |
| 9 | `_aggregate_scenarios` non-exhaustive `match` (missing one variant) | **No (until consumer exists)** — outline-step refactor 1 + Notes line 143 promise this but no AC pins it | harden |
| 10 | `_HARDENING_FLAGS` inlined as 3 string literals at the call site → one literal mutates | **Partial** — Test 6 catches missing flag but a typo in one flag (e.g., `--network=none-` with trailing dash) is undetected | harden |
| 11 | `_image_ref_for_digest` returns `"codegenie:trace-" + digest` (wrong tag shape) | **No** — see CF3 | harden |
| 12 | `cache/keys.py` silently drops `image-digest:<resolved>` instead of resolving | **No** — Test 14 expects HIT/MISS asymmetry but the underlying resolver isn't built; the test would fail at construction time, not pin the regression in production | block→harden |
| 13 | Concurrent task instrumentation only fires at start-of-scenario (not during execution) | **Partial** — Test 3 mentions "≥ 10 sampled points across the run" but the hook implementation isn't pinned | harden |
| 14 | Aggregate-timeout path skips ALL not-yet-started scenarios as `Failed` (wrong variant) | **Yes** — Test 10 documents "Skipped(ScenarioTimeout())" for not-yet-started; AC-7 line 45 affirms aggregate behavior | hardened |
| 15 | `_image_built` instance state from prior gather leaks (probe instance reused) | **No** — Notes line 137 prescribes instance-local flag; if coordinator reuses instances this state poisons next gather | harden |

Other test-quality concerns:

- **TF-A (harden).** Test 3's `_per_scenario_started_event` hook is named but not specified. Without a concrete hook, the implementer may shortcut to "sample every 100ms"; that's fragile. **Fix:** pin the hook as an instance-local `asyncio.Event` set inside `_execute_scenario` and a test-side `_observer_task` that loops `await asyncio.sleep(0); count = …` until the run completes. The story should name the hook in the implementation outline.
- **TF-B (harden).** No property test (`hypothesis`) for `_parse_strace_lines`. Strace output is line-oriented and the parser should be commutative under line-ordering for syscall counts (i.e., `parse(lines)` should yield the same `binaries_executed` set regardless of `lines` order, with the exception of `execve` ordering for shell_invocations counting). **Fix:** add a Hypothesis property test entry — `tests/property/test_strace_parser_commutativity.py` — generating random permutations of a known-good fixture; asserting set-valued fields are permutation-stable.
- **TF-C (harden).** `_aggregate_scenarios` must be a pure function (refactor goal) and exhaustive-`match` on `ScenarioResult.kind` with `assert_never`. Add a dedicated test that constructs a list with one of each top-level variant and asserts the aggregation; AND a static-analysis test (`mypy --warn-unreachable`) that removing one `case` produces a build error.
- **TF-D (harden).** Force the macOS-detection mechanism. **Fix:** AC says canonical detector is `sys.platform != "linux"`; the parenthetical `os.uname().sysname` reference is removed. Test monkey-patches `sys.platform`; no `os.uname` test variant.
- **TF-E (harden).** `_image_built` instance state leak. **Fix:** lift `image_built` to a `_run_all_scenarios(...) -> ScenariosResult` local — pass it explicitly into `_execute_scenario`. Add a test that runs the probe twice on the same instance and asserts both runs invoke `docker build` exactly once per run.
- **TF-F (harden).** Test 14 (`test_cache_hit_skips_scenarios`) presumes the cache resolver exists. **Fix:** split into two tests — (a) `test_cache_special_token_resolves_image_digest` (unit test of `cache/keys.py::declared_inputs_for` over a synthetic probe with the token in `declared_inputs` and a fixed resolver — proves the new dispatch arm works) and (b) `test_runtime_trace_cache_hit_skips_scenarios` (integration test that depends on (a)).

### Consistency critic (verdict: CONSISTENCY-HARDEN with 3 corrections)

- **NF-A (block→harden).** `Skipped(ImageDigestUnresolved())` (AC line 49, line 50) conflicts with S5-01's HARDENED variant set — `ImageDigestUnresolved` lives in `TraceFailureReason`, NOT `TraceSkipReason` (S5-01 AC #12, line 68). Editing S5-01 to relocate is non-surgical (Rule 3). **Fix:** route the image-digest-unresolved paths to `TraceScenarioFailed(reason=ImageDigestUnresolved())` (not Skipped); preserves S5-01's variant set verbatim. Semantically defensible: the scenario *was* attempted but failed at the digest prerequisite — it didn't skip (a skip is operator-driven; "no built image yet" is a probe-side failure to acquire the prereq).
- **NF-B (block→harden).** `ProbeOutput.confidence` Literal contract. Already covered as CF1 — listed here for cross-critic anchoring: `Probe.confidence: Literal["high","medium","low"]` (`base.py:68`, `localv2.md §4 line 328`); the probe MUST emit `"low"` (not `"unavailable"`) at the envelope; the slice's `trace_coverage_confidence` is the `"unavailable"` field.
- **NF-C (block→harden).** Cache special-token resolver scope. Already covered as CF7 — surfaced here for cross-critic anchoring: this story is the **first** consumer of the special-token mechanism. S1-09 added `ProbeContext.image_digest_resolver` but did NOT extend `cache/keys.py`. **Fix:** scope `cache/keys.py::declared_inputs_for` extension into this story with its own ACs and tests; future tokens (`scip-index-output:`, etc.) follow the precedent set here.
- **NF-D (harden).** `_DEFAULT_SCENARIOS` type. AC line 41 says `_DEFAULT_SCENARIOS = ["startup", "smoke_test", ...]` (list of strings); Implementation outline step 2 says `_DEFAULT_SCENARIOS: list[ScenarioSpec]` (list of model instances). **Fix:** pick `list[ScenarioSpec]` (the implementation outline form — string-only would force every scenario to share a hardcoded command, defeating the point of `ScenarioSpec.command`); rewrite AC-4 accordingly. The string-only fallback becomes a `_DEFAULT_SCENARIO_NAMES: Final[tuple[str, ...]]` constant for any place a name list is needed.
- **NF-E (harden).** `final-design.md §"Implementation risks" #7` citation (Context line 11, References line 23, AC-3 line 42, Notes line 131) does NOT exist — `final-design.md` has §"Risks (top 5)". The sequential-scenario rationale is in §"Components" #6, §"Tradeoffs accepted" (in #6), §"Cold gather (first time on a 50k-LOC service…)" line 369 ("5 trace scenarios (~75 s sequential)"), and §"Where security/best-practices traded off perf" (a). **Fix:** rewrite the four citations to point to §"Components" #6 + §"Where security/best-practices traded off perf" (a). Do not edit `final-design.md` (Rule 3).
- **NF-F (harden).** `applies_to_languages` not stated. The probe is language-agnostic (Dockerfile-driven, not source-language-driven). **Fix:** AC pinning `applies_to_languages = ["*"]` and `applies_to_tasks = ["*"]` — matches the language-agnostic posture; pre-empts a future contributor narrowing.
- **NF-G (harden).** `requires` not stated. The probe does not require sibling probe artifacts (image digest resolution is via `ProbeContext`, not via sibling slice). **Fix:** AC pinning `requires: list[str] = []` — explicit; matches the design (image digest is a `ProbeContext` callable, not a sibling-probe artifact).
- **NF-H (harden).** `forbidden-patterns` extension for `probes/layer_c/runtime_trace.py`. S5-01 / S1-11 established `_is_under_phase2_banned_package` covers `{indices, tccm, skills, conventions, adapters, depgraph, output}` and (after S5-01) `probes/_shared/` + `probes/layer_c/scenario_result.py`. This story is the second `probes/layer_c/` module — verify the predicate is path-scoped enough to cover the whole `probes/layer_c/` subdirectory, not just the `scenario_result.py` file. **Fix:** AC asserting `runtime_trace.py` is covered; if the existing predicate is narrower, this story extends it (mirroring S5-01 AC-11).
- **NF-I (clean).** Module location `src/codegenie/probes/layer_c/runtime_trace.py` matches `phase-arch-design.md §"Component design" #6 row 6` and `phase-arch-design.md §"Development view" P2C` block. ✓
- **NF-J (clean).** `@register_probe(heaviness="heavy", runs_last=False)` matches 02-ADR-0003 prescription and `phase-arch-design.md §"Components" #6` line 542. ✓
- **NF-K (clean).** No `gather`-extras change required; `py-tree-sitter` is the only new dep Phase 2 admitted. ✓

### Design-Patterns critic (verdict: DESIGN-HARDEN — 7 patterns surfaced as ACs, 0 mandated as names)

- **DF-1 (harden — observable AC).** Pure functional core / imperative shell. `_parse_strace_lines`, `_build_strace_argv`, `_build_docker_run_argv`, `_image_ref_for_digest`, `_aggregate_scenarios`, `_resolve_special_token` (in `cache/keys.py`) are all pure functions. Each should be importable and unit-testable without subprocess mocking. **Fix:** add AC requiring each is importable from the module's `__all__`-or-module-private namespace; each has a dedicated unit test that does NOT mock `run_allowlisted` (pure-function discipline). Mandate the underscore-prefix discipline so they remain module-private but importable in tests.
- **DF-2 (harden — observable AC).** Strategy-via-data for scenarios: `ScenarioSpec` is the strategy; `_DEFAULT_SCENARIOS` is the data-driven defaults; the operator-side `.codegenie/scenarios.yaml` is the extension surface. **Open/Closed for scenarios: a 6th scenario lands via `scenarios.yaml` operator-side, NOT a `runtime_trace.py` edit.** **Fix:** add observable AC requiring a 7-scenario fixture (`tests/fixtures/scenarios/seven_scenarios.yaml`) that runs end-to-end with no `runtime_trace.py` edit; AND a source-scan test asserting `_DEFAULT_SCENARIOS` is the ONLY in-source scenario list (so a future drift adding a hardcoded 6th to a different module is caught).
- **DF-3 (harden — observable AC).** Smart constructor for `image_ref`: `_image_ref_for_digest(digest: str) -> str` is the only path from digest to image tag. **Fix:** AC requires the helper is a pure module-private function; a parametrized test pins format `codegenie-trace:` + first-12-hex-after-stripping-sha256:-prefix; tests for empty / non-hex / sha256-prefixed-and-non-prefixed inputs.
- **DF-4 (harden — observable AC).** Hardening flags as a named module-level constant. **Fix:** AC requires `_HARDENING_FLAGS: Final[tuple[str, ...]] = ("--network=none", "--cap-drop=ALL", "--security-opt=no-new-privileges")` exposed at module level. The argv builder consumes it; the test imports the constant; magic-string drift in one of the three is impossible because there is only one source.
- **DF-5 (harden — observable AC).** Exhaustive-match discipline on `ScenarioResult` consumers. `_aggregate_scenarios(results: list[ScenarioResult]) -> SliceFields` `match`es on `result` and `assert_never`s the otherwise branch. Mirrors S5-01's `_describe` discipline for the producer/consumer ladder. **Fix:** AC requires the pure function exists, is unit-tested with one of each variant in the input list, and a `mypy --warn-unreachable` deletion smoke-test (matches S5-01 AC-6).
- **DF-6 (harden — Notes).** Newtype deferral for `image_ref: str`, `image_digest: str`, `scenario_name: str`. Each crosses ≥ 2 boundaries (probe ↔ cache; probe ↔ slice; probe ↔ structured-log). S1-05 is the canonical newtype story; mirror S5-01 DF-5's deferral. **Fix:** Notes paragraph naming the deferral + rationale; do NOT add an AC (Rule 2 — premature abstraction).
- **DF-7 (harden — Notes).** Trace-backend Protocol deferral. The macOS/Linux split is one `if` today (Rule 2: two cases is below the rule-of-three threshold). When a 3rd backend lands (microVM ptrace? Phase 5? Phase 7 dtrace?), refactor `_TraceBackend = Protocol` with `Strace`, `Unavailable`, `Ptrace` impls. **Fix:** Notes paragraph naming the deferral + named-trigger condition; do NOT add an AC.
- **DF-8 (harden — observable AC).** Open/Closed at the cache layer. The cache `_resolve_special_token` dispatch is the new Open/Closed seam for future tokens. **Fix:** AC requires the dispatch is `match`-based with `assert_never` on the unknown-token branch raising `CacheKeyError(reason="unknown_special_token", token=…)`; a test asserts an unknown token (`bogus:<resolved>`) raises with both the token name AND the reason field; future tokens (e.g., `scip-index-output:`) extend the `match` via ADR amendment.
- **DF-9 (harden — observable AC).** Producer/consumer assert_never ladder. This story is the 1st canonical producer of `ScenarioResult` (S5-01 was the type-introduction). Document in module docstring: producers = {`RuntimeTraceProbe`}; consumers = {`_aggregate_scenarios`, downstream slice-readers in S5-05 freshness, S8-01 renderer}.
- **DF-10 (clean).** Composition over inheritance: `RuntimeTraceProbe(Probe)` — single inheritance from kernel ABC. No mixins. ✓
- **DF-11 (clean).** No registry for scenarios — explicitly rejected per CLAUDE.md Rule 2 / `phase-arch-design.md §"Anti-patterns avoided"`. `ScenarioSpec` is data; defaults are a constant; operator-extensibility is via YAML, not via decorator. ✓
- **DF-12 (clean).** Tagged union discipline: every per-scenario outcome is a `ScenarioResult` variant; no dict-shuffling, no `dict[str, Any]` for outcomes. ✓
- **DF-13 (clean).** Phase-0 chokepoint preservation: every subprocess call routes through `run_allowlisted`; no direct `subprocess.run` / `asyncio.create_subprocess_exec`. ✓
- **DF-14 (clean).** No Plugin Loader. The probe is `@register_probe`-registered in-tree; the operator-side `.codegenie/scenarios.yaml` is the data surface. 02-ADR-0007 honored. ✓

No `block`-tier design findings. No `NEEDS RESEARCH` findings — every pattern question was answerable from the existing precedents (`dep_graph.py` for strategy-via-data, S5-01 for sum-type discipline, S4-01 for `runs_last`+`cache_strategy="none"` precedent — though this probe is the opposite, `cache_strategy="content"`).

## Stage 3 — Researcher

Not invoked. No critic tagged `NEEDS RESEARCH`.

## Stage 4 — Edits applied (18 in-place changes)

1. **Validation notes block** appended after the story metadata header summarizing the 18 edits + the `_validation/` pointer.
2. **AC-1 (line 38) — `applies_to_tasks` / `applies_to_languages` / `requires` pinned.** Add explicit `applies_to_tasks = ["*"]`, `applies_to_languages = ["*"]`, `requires: list[str] = []` per NF-F + NF-G.
3. **AC-3 (line 40) — `cache_strategy = "content"` pinned literally.** NOT "not `none`" — exact value. Mirrors CF2.
4. **AC-4 (line 41) — `_DEFAULT_SCENARIOS: list[ScenarioSpec]`.** Resolves NF-D type drift between AC + outline.
5. **NEW AC — `applies_to_tasks/languages/requires` pin** (extracted from AC-1).
6. **AC-9 (line 47) — envelope `confidence="low"`, slice `trace_coverage_confidence="unavailable"`.** Rewrite to honor contract per CF1 / NF-B. Docker-build failure → `Skipped(ImageBuildUnavailable())` (S5-01 variant set preserved).
7. **AC-11 (line 49) — resolver returns `None` → `Failed(ImageDigestUnresolved())` (NOT Skipped).** Per NF-A.
8. **AC-12 (line 50) — resolver is `None` → `Failed(ImageDigestUnresolved())` (NOT Skipped).** Per NF-A.
9. **NEW AC — `image_digest_resolver` raising is caught and translated.** Per CF6.
10. **NEW AC — `confidence ∈ {"high","medium","low"}` contract preservation pin.** Pinns the envelope-side `Literal` per CF1.
11. **NEW ACs (3 of them) — Phase-0 cache `_resolve_special_token` extension** scoped into this story per CF7 / NF-C: (a) recognition syntax `r"^[a-z0-9_-]+:<resolved>$"`; (b) `image-digest:` arm calls `ctx.image_digest_resolver(snapshot.root)` and folds digest into content-hash; (c) unknown tokens raise `CacheKeyError(reason="unknown_special_token", token=…)`. Also adds DF-8 dispatch-via-`match` discipline.
12. **NEW AC — `_HARDENING_FLAGS: Final[tuple[str, ...]]` module constant** per DF-4.
13. **NEW AC — `_image_ref_for_digest` pure helper + parametrized test** per CF3 / DF-3.
14. **NEW AC — `_parse_strace_lines` pure function + golden-fixture test + property-test entry** per TF-B / DF-1.
15. **NEW AC — `_aggregate_scenarios` exhaustive `match` with `assert_never`** per TF-C / DF-5; mirrors S5-01 AC-6.
16. **NEW AC — `_build_strace_argv` / `_build_docker_run_argv` pure functions, importable, dedicated tests including the explicit `--` separator** per TF-3 / DF-1. The explicit `--` separator gets its own argv-shape pin.
17. **NEW AC — `scenarios_run` / `scenarios_failed` / Skipped routing pinned** per CF4.
18. **NEW AC — slice schema is the COMPLETE observable surface** (no extra keys, no missing keys) per CF8; pinned via snapshot test.
19. **NEW AC — `applies_to_languages = ["*"]` operator-extensibility test for 6+ scenarios via `scenarios.yaml`** per DF-2. Adds `tests/fixtures/scenarios/seven_scenarios.yaml` + a zero-source-edit test.
20. **NEW AC — `_image_built` lifted from instance state to local** per TF-E; image-build runs once per `run()` invocation, not once per probe instance.
21. **NEW AC — macOS-detection mechanism pinned to `sys.platform`** (`os.uname` parenthetical removed) per TF-D.
22. **NEW AC — strace-argv `--` separator pin** per mutation #3.
23. **NEW AC — `forbidden-patterns` covers `probes/layer_c/runtime_trace.py`** (asserted + extended if needed) per NF-H; mirrors S5-01 AC-11.
24. **NEW AC — source-scan: `_DEFAULT_SCENARIOS` is the only in-source scenario list** per DF-2.
25. **NEW TDD entries:** Tests 18–27 added (mirror the new ACs above). Existing test 14 split into 14a (cache-resolver unit) + 14b (runtime-trace integration). Property test entry added (`tests/property/test_strace_parser_commutativity.py`).
26. **References list extended:** Phase 0 `cache/keys.py::declared_inputs_for` (the extension point) explicitly listed.
27. **Notes for the implementer extended** with seven new paragraphs: contract-confidence routing (envelope vs slice); image-ref smart-constructor format; macOS detection canonical mechanism (`sys.platform`); cache special-token dispatch lives in this story (not deferred); newtype deferral for `image_ref` / `image_digest` / `scenario_name` (S1-05) per DF-6; trace-backend Protocol deferral (named-trigger: 3rd backend) per DF-7; `_image_built` per-`run()` not per-instance.
28. **Citation corrections** at lines 11, 23, 42, 131 — `final-design.md §"Implementation risks" #7` → `final-design.md §"Components" #6` + `§"Where security/best-practices traded off perf" (a)`.

## Verdict

**HARDENED.** The story now (a) honors the frozen `Probe.confidence` contract, (b) consumes S5-01's variant set without contradiction, (c) explicitly scopes the cache special-token resolver extension this story is the first consumer of, (d) surfaces 7 pattern observable ACs that were previously buried in Notes, and (e) corrects 4 citation paths. The story remains ~155 lines; the additions are all observable / verifiable. The implementer can now write the executor pass with no judgment calls left for the validator to second-guess.

Ready for `phase-story-executor`.
