# Validation report — S3-03 — Subprocess rubric invocation with scrubbed env

**Validator run:** 2026-05-27 (scheduled task `story-validation-corrector`)
**Story file:** `../S3-03-subprocess-rubric-invocation.md`
**Verdict:** **HARDENED** — story had 27 fixable weaknesses, including 7 block-severity contract drifts; edits applied in place.
**Skip Stage 3:** no findings tagged `NEEDS RESEARCH` (everything resolvable against canonical phase docs + sibling HARDENED story S3-02).

## Context Brief (Stage 1)

S3-03 ships the concrete `SubprocessRubricRunner` that substitutes — by addition — for the in-process stub rubric S3-02 wired through the `RubricRunner` Protocol seam. S3-02 is `HARDENED 2026-05-27` and is therefore the **canonical contract source** for the runner shape; S3-03 must conform without re-shaping the Protocol.

The load-bearing constraints S3-03 inherits:

- **ADR-0001 (Rubric runs as scrubbed-env subprocess)** — `SCRUBBED_ENV` carries `PYTHONPATH`, `PYTHONHASHSEED=0`, and a minimal `PATH`. No `ANTHROPIC_API_KEY`, `AWS_*`, `HOME`, or `USER`. Killed at `case.rubric_wall_clock_seconds` (default 60 s, max 300 s). Bench-author unit tests bypass subprocess isolation.
- **ADR-0004 (Per-task-class failure modes taxonomy)** — rubric subprocess failure paths produce typed `FailureMode(severity="block")` and the run continues; the runner **does not re-raise**.
- **ADR-0010 (`isolation_class` annotation)** — `BenchRunReport.isolation_class = "subprocess"` flows from this story's runner-shape; the audit chain refuses to mix populations.
- **Phase 5 ADR-0012 (env allowlist discipline)** — the `env_allowlist.filter({})` precedent; divergence between the Phase 5 sandbox and the Phase 6.5 rubric scrub list is a CODEOWNERS-visible audit risk (ADR-0001 §Tradeoffs row 4).
- **S3-02 AC-3 (HARDENED `RubricRunner` Protocol)** — `async def run(self, rubric_path: Path, case: BenchCase, harness_output: Mapping[str, Any], *, wall_clock_cap_seconds: float) -> BenchScore`. The Protocol is at `src/codegenie/eval/rubric_runner.py`. S3-03 substitutes the concrete implementation **without re-shaping the signature**.
- **S1-04 (HARDENED `Rubric` Protocol)** — exists for bench-author in-process type-checking; the runner does *not* type-check across the subprocess boundary.
- **`final-design.md` lines 168–179** — `python -I -B <rubric_runner_entrypoint>`; rubric `.py` bytes copied into scratch dir (not imported); `env={}` baseline; subprocess `BenchScore` shape is identical across the eventual microVM upgrade so the audit chain stays comparable.
- **CLAUDE.md** — Rule 7 (surface conflicts, don't average); Rule 9 (tests verify intent); Rule 11 (match conventions — the more recent / more tested wins); Rule 12 (fail loud); "Extension by addition — no silent edits"; "Honest confidence".

## Stage 2 — Critic findings

Four critics ran in parallel. **27 findings total. Severity counts: 7 block, 15 harden, 5 nit.**

### Coverage (F-COV-1 … F-COV-9) — 9 findings

| ID | Sev | Issue (short) | Resolution |
|---|---|---|---|
| F-COV-1 | block | No AC for `RubricRunner` Protocol conformance — the load-bearing seam | New AC-1 (structural Protocol conformance + `isinstance` + `typing._get_protocol_attrs` symmetry) |
| F-COV-2 | block | Class signature `async __call__(self, case, harness_output)` doesn't match S3-02 Protocol `async def run(self, rubric_path, case, harness_output, *, wall_clock_cap_seconds)` | AC-2 (method name + signature pinned bytes-for-bytes to S3-02 AC-3) |
| F-COV-3 | block | Module path `src/codegenie/eval/rubric_subprocess.py` doesn't match S3-02's `src/codegenie/eval/rubric_runner.py` — Protocol + concrete impl must co-locate | AC-3 (module path corrected; `SubprocessRubricRunner` lands beside `RubricRunner` Protocol) |
| F-COV-4 | harden | No AC for `SubprocessRubricRunner` exported via `codegenie.eval.__all__` | New AC-4 |
| F-COV-5 | harden | "Wire into `Runner.run_eval`" — wrong method name (S3-02 names it `Runner.execute`) and wrong wiring boundary (no default; the CLI in S4-02 instantiates) | AC-5 + Out-of-scope note: no runtime wiring in this story; S4-02 owns construction at CLI assembly |
| F-COV-6 | harden | No AC asserts `cwd` is actually under `tempfile.gettempdir()` (a wrong impl using `cwd=os.getcwd()` would pass the existing tests) | New AC-9 (cwd-is-tempdir + cwd ≠ harness cwd) |
| F-COV-7 | harden | No AC asserts `proc.wait()` is awaited after `proc.kill()` on timeout — implementer note flags it as the tempdir-cleanup race, no test enforces it | New AC-10 (subprocess fully reaped after timeout) |
| F-COV-8 | harden | No AC for non-zero exit with empty stderr (boundary: `stderr[:200].decode(...)` on empty bytes) | New AC-13 |
| F-COV-9 | harden | No AC for concurrent runner invocations producing independent tempdirs (S3-02 fans out under a semaphore — concurrent rubric subprocesses are the production path) | New AC-14 |

### Test-Quality (F-TQ-1 … F-TQ-10) — 10 findings

| ID | Sev | Issue | Wrong-impl that passes today | Resolution |
|---|---|---|---|---|
| F-TQ-1 | harden | `test_happy_path` asserts `wall_clock_ms > 0` — a rubric emitting `wall_clock_ms=1_000_000` and a runner that passes it through would pass | Strengthen: rubric emits `wall_clock_ms=999_999_999`; runner *overrides* with a measured value; assert `1 ≤ ms ≤ 5000` AND `ms != 999_999_999` |
| F-TQ-2 | block | `test_subprocess_cannot_read_anthropic_api_key` asserts substring absence — a wrong impl that base64-encodes stderr would pass; assertion is exact-key-not-in-list, not exact-set-equality | New `test_subprocess_env_keys_are_exactly_scrubbed` enumerates the *exact* set of keys visible inside the subprocess |
| F-TQ-3 | harden | `test_subprocess_timeout_maps_to_failure_mode` doesn't measure elapsed wall-clock — a wrong impl that waits 60 s anyway would still pass (just slower) | Strengthen: timeout=0.5; assert measured elapsed ≤ 5 s (proves the runner enforced the cap, not the rubric's natural exit) |
| F-TQ-4 | harden | `test_malformed_json_stdout` doesn't assert detail carries a non-empty validation summary — a wrong impl returning empty detail would pass | Strengthen: assert `len(fm.detail) > 0` AND detail contains a Pydantic field name or `"validation"` substring |
| F-TQ-5 | harden | `test_tempdir_is_cleaned_after_subprocess` uses f-string-injected path (Windows path-escape bug); race window on slow CI when `proc.wait()` is missing | Switch to `repr(str(...))`; combine with new AC-10 (`proc.wait()` enforced) |
| F-TQ-6 | harden | No test asserts `sys.flags.isolated == 1` (i.e., `python -I` was actually applied) | New `test_subprocess_runs_with_isolated_flag` — rubric emits `{"isolated": sys.flags.isolated, "dont_write_bytecode": sys.flags.dont_write_bytecode}`; assert both `== 1` |
| F-TQ-7 | harden | No metamorphic test on rubric-determinism — running the same rubric+case+harness_output twice should produce byte-identical `model_dump_json()` modulo `wall_clock_ms` | New `test_rubric_invocation_is_deterministic_modulo_wall_clock` |
| F-TQ-8 | harden | No property-based test on JSON ser/de round-trip — a wrong impl truncating stdout at 1024 bytes would pass small-payload tests | New Hypothesis test: arbitrary `BenchScore` JSON round-trips through stdin/stdout via an `echo` rubric |
| F-TQ-9 | block | `test_subprocess_cannot_read_anthropic_api_key` exits 2 with stderr → only checks the rubric *saw* `None` and the captured detail doesn't leak. Missing the inverse: a malicious impl that *strips* keys before exec but logs the original env elsewhere would pass | New `test_subprocess_env_keys_are_exactly_scrubbed`: parent has 50 env vars; subprocess reports `len(os.environ) == len(SCRUBBED_ENV)` AND `set(os.environ) == set(SCRUBBED_ENV)` |
| F-TQ-10 | nit | `test_tempdir_is_cleaned_after_subprocess` only checks the tempdir vanished — doesn't check the rubric had a writable cwd in the first place (regression: a wrong impl `cwd="/"` would also "clean up" because there'd be no tempdir to clean) | Combine: rubric writes a marker into cwd; assert (a) marker existed at write time, (b) tempdir resolves under `tempfile.gettempdir()`, (c) directory vanishes |

### Consistency (F-CON-1 … F-CON-6) — 6 findings

| ID | Sev | Issue | Source of truth | Resolution |
|---|---|---|---|---|
| F-CON-1 | block | Story signature contradicts S3-02 HARDENED `RubricRunner` Protocol (module, method name, parameters, kwarg-only `wall_clock_cap_seconds`) | S3-02 AC-3 (HARDENED 2026-05-27) | Story restructured: same module `rubric_runner.py`, `async def run(self, rubric_path, case, harness_output, *, wall_clock_cap_seconds)`, no constructor-injected `rubric_root` or `timeout_default` |
| F-CON-2 | block | `SCRUBBED_ENV` keys diverge from ADR-0001 (PYTHONPATH, PYTHONHASHSEED, PATH). Story has PATH, LANG, PYTHONHASHSEED, PYTHONIOENCODING — and explicitly bans PYTHONPATH in a Notes paragraph, silently contradicting the ADR | ADR-0001 §Decision; arch §Tool-use safety. Per Rule 7 (surface conflicts, don't average) | Story aligned to ADR-0001: 3 keys (`PATH`, `PYTHONHASHSEED`, `PYTHONPATH`). `PYTHONPATH=""` (empty — the `-I` flag below makes its value moot anyway). Implementer note rewritten to point at the ADR rather than overriding it; any future change requires ADR-0001 amendment |
| F-CON-3 | block | Timeout source contradicts S3-02 Protocol — story reaches into `case.rubric_wall_clock_seconds`; S3-02 AC-3 binds the timeout to the kwarg `wall_clock_cap_seconds` (which the *worker* sources from the threaded-through `timeout_per_case_seconds`) | S3-02 AC-3 (HARDENED) | `SubprocessRubricRunner.run` consumes `wall_clock_cap_seconds` only. The case-level `rubric_wall_clock_seconds` selection is the **worker's** concern (S3-04 amendment, called out in Out-of-scope) |
| F-CON-4 | block | Story uses bare `sys.executable str(rubric_path)`; final-design.md mandates `python -I -B <entrypoint>`. `-I` is the load-bearing isolation flag — without it, `PYTHONPATH` / `PYTHONSTARTUP` / user site-packages can still influence the child even with a scrubbed env (a `PYTHONPATH` *not* in env is still picked up from `~/.pythonrc` if `PYTHONSTARTUP` is set elsewhere) | final-design.md lines 168–179 | AC-7 mandates `[sys.executable, "-I", "-B", str(rubric_path)]` |
| F-CON-5 | harden | "Wire into `Runner.run_eval`" — method name is wrong; HARDENED S3-02 names the method `Runner.execute` and threads `rubric_runner` as a kwarg with no default. The default-constructor lives at the CLI assembly point (S4-02) | S3-02 AC-1 | AC-5 corrected; story explicitly out-of-scopes runner wiring (S4-02 owns) |
| F-CON-6 | nit | `make_bench_case` helper file path: story says `tests/helpers/bench.py`; S3-02 puts test helpers under the same module — verified consistent. Note acknowledges S2-02 as the canonical source if it pre-shipped | (no change needed; already correct) | Wording sharpened |

### Design-Patterns (F-DP-1 … F-DP-2) — 2 findings

| ID | Sev | Issue | Trigger / rule | Resolution |
|---|---|---|---|---|
| F-DP-1 | block | Story misses the Protocol/Strategy/DIP seam ADR-0001 + final-design.md prescribe. As drafted, the concrete `SubprocessRubricRunner` is a different shape than the Protocol — meaning the eventual `MicroVMRubricRunner` (Phase 16) would need a constructor-shape change OR a wrapper, breaking "extension by addition" | "Extension by addition — no silent edits" (CLAUDE.md load-bearing); Open/Closed; DIP | Story restructured to *be* a Protocol implementation (no constructor parameters; parameters flow via `run`); ACs added to enforce structural Protocol conformance |
| F-DP-2 | harden | The three-failure-paths-now-six-after-S3-04 invites a registry/dispatch pattern (`@register_rubric_failure(code, factory)`) at rule-of-three. S3-03 sees 3; S3-04 lands 3 more; that's the precise rule-of-three threshold | Rule-of-three + Open/Closed | Notes-for-implementer surfaces the deferred extract: keep a `_to_failure_score(code, *, detail="")` helper in S3-03 (refactor pass), and S3-04 elevates to a dispatch table or registry — not now, but the helper-extraction AC is the staging surface |

Both surfaced as Notes-for-implementer paragraphs per the editor rule "pattern advice is contextual, not an AC" (the design-pattern *adoption* is observable — see new ACs phrased as "adding a new RubricRunner implementation requires zero edits to `rubric_runner.py`" — but the *implementation technique* is not).

## Stage 3 — Researcher

Skipped — every finding resolves against canonical phase docs + the HARDENED S3-02 contract; no methodology gap requires arXiv / external pattern lookup.

## Stage 4 — Synthesizer

**Conflict resolution (Consistency > Coverage > Test-Quality > Design-Patterns):**

| Conflict | Resolution | Wins because |
|---|---|---|
| Story's 4-key `SCRUBBED_ENV` vs ADR-0001's 3-key (PYTHONPATH, PYTHONHASHSEED, PATH) | Align to ADR-0001 | Consistency > Coverage; Rule 7 ("surface conflicts, don't average"); ADR-0001 §Tradeoffs row 4 makes divergence a CODEOWNERS-visible audit risk |
| Story's `case.rubric_wall_clock_seconds or 60.0` vs S3-02 Protocol's `wall_clock_cap_seconds` kwarg | S3-02 Protocol wins | S3-02 is HARDENED and the canonical Protocol source; per-case timeout selection moves to the worker layer |
| Story's `rubric_subprocess.py` vs S3-02's `rubric_runner.py` | Co-locate in `rubric_runner.py` | Protocol + concrete impl belong together (sibling Protocol-port files in this repo — `vuln_index/protocol.py`, `fallback/leaf/port.py` — co-locate the Protocol and the canonical implementation in the same package) |
| Story's `async __call__` callable shape vs Protocol's `async def run` method shape | `async def run` wins | Protocol is the seam; matching its signature *is* the design pattern (Strategy/DIP) |

**Edits applied to the story** (full list in the §"Validation notes" block now at the top of the story):

1. **Header** — `Status: Ready` → `Status: Ready (HARDENED 2026-05-27)`; `Depends on` widened to include the HARDENED commitment on S3-02; `ADRs honored` adds explicit pin to S3-02 AC-3 conformance.
2. **Validation notes block** appended after the `Context` section (full audit trail of every change applied).
3. **Goal** — rewritten to bind the runner shape to the `RubricRunner` Protocol (S3-02 AC-3) rather than describing an independent `async __call__` callable.
4. **Acceptance criteria** — renumbered AC-1…AC-17; old ACs preserved where verbatim-correct, replaced where they contradicted source-of-truth. Added 9 net new ACs.
5. **Implementation outline** — restructured to match the Protocol signature; constructor takes no parameters; `rubric_path` flows via `run(...)` kwarg.
6. **TDD plan** — 6 new tests, 4 existing tests strengthened. Mutation-resistance documented inline.
7. **Files to touch** — `rubric_subprocess.py` removed; updates land *inside* the same `rubric_runner.py` S3-02 introduces.
8. **Notes for implementer** — `Do not extend SCRUBBED_ENV to include PYTHONPATH` paragraph removed (it contradicted ADR-0001). Replaced with: ADR-0001 alignment commentary, Protocol-conformance enforcement, `-I -B` flag rationale, deferred `_to_failure_score` helper extraction, MicroVMRubricRunner extension path, no `rubric_root` constructor field (worker passes `rubric_path` directly).
9. **Out of scope** — added: per-case timeout selection (S3-04), CLI default-runner construction (S4-02), the `_to_failure_score` registry promotion (S3-04 rule-of-three).

## Verdict

**HARDENED.** The story is now compatible with HARDENED S3-02, conformant with ADR-0001 + ADR-0004 + ADR-0010, and would catch a wrong implementation via 11 mutation-resistant tests (up from 6) including 1 Hypothesis property test and 1 metamorphic determinism test. The Protocol-conformance AC makes the eventual Phase-16 `MicroVMRubricRunner` substitution mechanically additive — no edit to `rubric_runner.py`'s seam required.

Ready for `phase-story-executor`.
