# Validation report — S5-02 Lockfile + exec adversarial corpus (yarn regex-DoS, planted `node` shim, unsafe YAML tag)

**Story:** [S5-02-adversarial-lockfile-exec.md](../S5-02-adversarial-lockfile-exec.md)
**Validated:** 2026-05-15
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

S5-02 owns the **untrusted-input-into-stateful-component** quadrant of the Phase 1 adversarial corpus — three tests pinning that (a) the hand-rolled yarn-lock state machine cannot regex-DoS, (b) a hostile `node` shim on `$PATH` runs without leaking secrets via either env surface, and (c) `CSafeLoader` refuses `!!python/object` without side-effect. The story was directionally correct (the right three tests, the right cross-references to ADR-0001/0003/0008/0009, the right "no per-probe sandbox, the env chokepoint is the load-bearing defense" framing) but had **four block-tier failure modes** that would have made the executor's first attempt fail for the wrong reason, and **eight harden-tier weaknesses** around mutation-resistance.

The four block-tier failures shared a common root cause: **the story's TDD-plan code samples did not match the actual signatures and semantics of `exec.run_allowlisted`, `safe_yaml.load`, and the codebase's env-strip model**:

1. **`run_allowlisted` is `async`, takes `cwd: Path` (required), and `timeout_s: float` (not `timeout`).** The original sample call (`exec_mod.run_allowlisted(["node", "--version"], timeout=5)`) would have raised `TypeError` — the wrong kwarg, missing `cwd`, and a non-awaited coroutine. The shim would never have run. **Resolution:** every code sample now `await`s the call with `cwd=tmp_path, timeout_s=…` inside an `async def` test. Mirrors `tests/adv/test_env_var_strip.py:55-85`.
2. **`SENTINEL_FILE` cannot reach the child via `monkeypatch.setenv`** because `_filter_env` (`exec.py:124-150`) builds the child env by **inclusion** of a 4-key safe baseline (`PATH`/`HOME`/`LANG`/`LC_ALL`) plus sanitized `env_extra`; the parent `os.environ` is never copied. The original test set `SENTINEL_FILE` on the parent process; the shim's `> "$SENTINEL_FILE"` would have redirected to `""` (empty path) and `sentinel.read_text()` would have raised `FileNotFoundError`. **Resolution:** the shim's PATH override and `SENTINEL_FILE` are now passed through `env_extra` (the documented narrow passthrough), where they reach the child.
3. **`safe_yaml.load(f)` is missing the mandatory `max_bytes` kwarg.** `parsers/safe_yaml.py:80` declares `def load(path: Path, *, max_bytes: int, max_depth: int = 64)`. The original call raises `TypeError` before the YAML body parses; `CSafeLoader` is never the surface under test. **Resolution:** call site is `safe_yaml.load(path, max_bytes=1_000_000)` everywhere.
4. **AC-8 referenced a non-existent structlog event name (`exec.run_allowlisted.env_stripped`).** The actual events emitted by `exec.py` are `subproc.spawn`, `subproc.exit`, `subproc.timeout`, and `subproc.env_extra.sensitive_key_dropped` (the only sensitive-key event; the parent-env-inclusion path is silent by design). **Resolution:** AC-8 now binds to the real `subproc.env_extra.sensitive_key_dropped` event, captured via `structlog.testing.capture_logs`, with one event expected per sensitive key passed through `env_extra`.

The eight harden-tier weaknesses:

- **The original test exercised only the parent-env inclusion surface.** A mutation that deleted `_is_sensitive` (the denylist for `env_extra`) would have silently passed. The hardened test now passes sensitive vars through `env_extra` in addition to the parent — and a `MY_LEGIT_VAR` positive control proves the chokepoint did not over-filter.
- **The "pathological" yarn-lock input did not actually stress `_parse_handrolled`.** The original 50 KB input had no quadratic surface against the line-by-line state machine; a regression introducing O(n²) on a 50 KB body would still beat 1 s. The hardened input is ~5 MB and exercises `_dequote_entry_header`'s `split('", "')` path (the only string-allocation surface in the scanner). An additional **structural assertion** scans the AST of `_yarn` for any regex import/call, pinning the "no regex over the full body" contract from `_yarn.py:116` and ADR-0003 deterministically.
- **The yarn test silently accepted `{"entries": {}}` as a passing return.** A future "fast path" that early-returns empty on any large input would have satisfied the timing assertion. The hardened test asserts `len(entries) > 0` on the success path; the only acceptable alternatives are non-empty parse or `MalformedLockfileError`.
- **The YAML test had no positive control.** A degenerate `safe_yaml.load` replacement (`raise MalformedYAMLError(...)` unconditionally) would have passed. The hardened test adds a second test loading a minimal valid `pnpm-lock.yaml` and asserting it returns.
- **The YAML test's "no side-effect" assertion was unreachable as written.** The TDD-plan red-code used `echo adv_canary` (no filesystem side-effect), but the implementation outline used `touch /tmp/codegenie-adv-canary` (non-hermetic). The hardened test uses an f-string interpolating `tmp_path` into the hostile YAML body, asserting `not (tmp_path / "adv-canary.txt").exists()` — hermetic, parallel-safe.
- **No `__cause__` assertion on the YAML test.** A regression where `MalformedYAMLError` is raised from a different layer (e.g., the size cap firing first) would have silently passed. The hardened AC-11 asserts `exc_info.value.__cause__` is a `yaml.YAMLError` subclass, proving the translation path in `safe_yaml._parse_one:142-145` ran.
- **`_HAS_PYARN` attribute existence was not pre-checked.** A future rename to `_PYARN_AVAILABLE` would have silently no-op'd the `monkeypatch.setattr` on a contributor's machine where `pyarn` is installed, and the test would have exercised pyarn instead of the hand-rolled path — missing the regex-DoS mutation entirely. The hardened test pre-asserts `hasattr(_yarn, "_HAS_PYARN")` and uses `raising=True`.
- **Cross-platform skip was only in Notes, not an AC.** Promoted to AC-9: `@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell required")`.

The synthesizer also resolved **three consistency issues**:

- **Missing dependency on S5-01** for the `adv` pytest marker registration (`pyproject.toml [tool.pytest.ini_options]` only registers `bench` per pyproject.toml:183-185; `--strict-markers` is enabled at line 178, so unregistered `pytest.mark.adv` would fail loud). Added to the **Depends on:** line and to AC-15 with a note that this story does NOT add the registration itself (S5-01 owns it; Rule 3 — surgical changes).
- **Missing Phase 0 ADR-0012** from the "ADRs honored" line. The planted-shim test directly exercises ADR-0012's chokepoint contract (env built by inclusion, `shell=False`, `stdin=DEVNULL`). Added with the relative path to the Phase 0 ADR.
- **"env-strip" language clarified.** The story used "env-strip" loosely to describe both the parent-env-inclusion model and the `_is_sensitive` denylist on `env_extra`. The Notes-for-implementer now distinguishes the two surfaces explicitly, and clarifies that the inclusion model is silent (no structlog event) while the denylist emits `subproc.env_extra.sensitive_key_dropped`.

Three design-pattern observations were filed as Notes (not ACs), per CLAUDE.md Rule 2 ("three similar lines is better than premature abstraction"):

- **Helper extraction deferred.** The shim factory, hostile YAML body, and pathological yarn-lock builder each have exactly one consumer in Phase 1 (just S5-02). S5-03 needs none of them. The rule-of-three threshold is not met; module-level inlines are correct.
- **Functional-core fixture builders affirmed.** `_pathological_yarn_lock(approx_bytes)` is now a pure bytes-in/bytes-out function (size-parametrized), but `SHIM_BODY` and `UNSAFE_YAML` stay as module-level f-string/text constants — they have no parametrization story.
- **"Test at the chokepoint, not the probe" architectural intent surfaced.** The story now explicitly says that `exec.run_allowlisted` is the surface under test, not `NodeBuildSystemProbe`. Mirrors the S4-05 spy-at-the-chokepoint pattern in `tests/adv/test_env_var_strip.py`.

The original **8 ACs** are now reorganised into **5 named AC groups with 19 individually-verifiable assertions** plus a **2-item out-of-scope cross-reference list** (`OOS-1`/`OOS-2`) preventing the executor from accidentally landing the ADR-0001 garbage-output AC (owned by S2-02) or the property-based yarn fuzz (owned by `tools/fuzz_yarn_lock.py`).

**No `NEEDS RESEARCH` findings.** Every weakness was resolvable from authority docs (ADR-0001 + ADR-0003 + ADR-0008 + Phase 0 ADR-0012 + `phase-arch-design.md §"Adversarial tests"` + the existing implementations of `exec.py`, `safe_yaml.py`, and `_yarn.py` + the S4-05 sibling test `tests/adv/test_env_var_strip.py`). Stage 3 skipped per skill's token-economy guidance.

## Critic findings

### Coverage (CV-)

- **CV-1 [block] — `run_allowlisted` invocation in AC-2 is structurally wrong (sync call, wrong kwargs, missing `cwd`).** Original AC-2 said `exec.run_allowlisted(["node", "--version"], timeout=5)`. Actual signature (`exec.py:175-181`) is `async def run_allowlisted(argv, *, cwd: Path, timeout_s: float, env_extra=None)`. Test would raise `TypeError` before the shim ran; env-strip never exercised. **Resolution:** rewrote AC-4/AC-5 + TDD plan to `await cg_exec.run_allowlisted([...], cwd=tmp_path, timeout_s=5.0, env_extra={...})` inside `async def` test.
- **CV-2 [block] — `SENTINEL_FILE` cannot reach the shim under env-by-inclusion model.** `_filter_env` (`exec.py:135-140`) starts from `{PATH, HOME, LANG, LC_ALL}` only; `monkeypatch.setenv("SENTINEL_FILE", ...)` sets it on the parent process, which is never copied. Shim's `$SENTINEL_FILE` is empty; redirect fails or writes nowhere; `sentinel.read_text()` raises before assertions. **Resolution:** `SENTINEL_FILE` (and the shim-dir `PATH` override) now travel via `env_extra={"SENTINEL_FILE": ..., "PATH": ...}`.
- **CV-3 [block] — Env-strip test vacuous against actual implementation.** `monkeypatch.setenv("OPENAI_API_KEY", ...)` doesn't exercise `_is_sensitive` — the wrapper never reads from `os.environ` for sensitive keys. A regression deleting `_is_sensitive` entirely would have passed the original test. **Resolution:** AC-7 now passes sensitive vars through `env_extra` (where `_is_sensitive` is the defense) and asserts `subproc.env_extra.sensitive_key_dropped` fires for each — exercises the denylist directly. AC-6 retains the parent-env path as a second, separate guard.
- **CV-4 [block] — AC-8 cites non-existent structlog event name.** No `exec.run_allowlisted.env_stripped` event exists. Real events: `subproc.spawn`, `subproc.exit`, `subproc.timeout`, `subproc.env_extra.sensitive_key_dropped`. **Resolution:** AC-8 now binds to `subproc.env_extra.sensitive_key_dropped` and asserts exactly 4 events (one per sensitive `env_extra` key in AC-7).
- **CV-5 [harden] — `_HAS_PYARN` attribute existence not pre-checked.** A future rename would silently no-op the monkeypatch. **Resolution:** AC-1 now requires `assert hasattr(_yarn, "_HAS_PYARN")` plus `monkeypatch.setattr(..., raising=True)`.
- **CV-6 [harden] — Walltime budget of 5 s too tight.** The yarn AC-1 needs ≤ 2 s headroom; shim spawn ~300 ms p95 on macOS CI. **Resolution:** AC-16 raises the budget to 10 s p95.
- **CV-7 [harden] — YAML test missing positive control.** A `safe_yaml.load = raise(...)` mutation passes trivially. **Resolution:** AC-12 + second test in the YAML file load a minimal valid `pnpm-lock.yaml`.
- **CV-8 [nit] — Notes para on "SENTINEL_FILE survives env-strip" was stale.** Implied a denylist model that doesn't exist. **Resolution:** Notes rewritten to describe the inclusion model and the `env_extra` passthrough explicitly.

### Test-Quality (TQ-)

- **TQ-1 [block] — `safe_yaml.load(f)` missing required `max_bytes` kwarg.** `safe_yaml.py:80` makes it mandatory. **Resolution:** every call site is `safe_yaml.load(path, max_bytes=1_000_000)`.
- **TQ-2 [block] — `exec_mod.run_allowlisted([...], timeout=5)` broken on 3 counts** (async, missing `cwd`, wrong kwarg name). **Resolution:** see CV-1.
- **TQ-3 [block] — `SENTINEL_FILE` unreachable via `monkeypatch.setenv`.** Same root as CV-2. **Resolution:** `env_extra` passthrough.
- **TQ-4 [harden] — Mutation-resistance framing misstated.** Original test only catches a regression in the *parent-env inclusion* path; the `_is_sensitive` *denylist* path was untested. **Resolution:** dual-surface test (CV-3); docstring rewrites the catch-list explicitly.
- **TQ-5 [block] — Pathological yarn input does not exercise `_parse_handrolled`'s worst case.** `_parse_handrolled` is a pure line-by-line state machine; a 50 KB input has no quadratic surface. **Resolution:** AC-1 now uses a ~5 MB input via `_pathological_yarn_lock(approx_bytes=5_000_000)` exercising the `_dequote_entry_header` split path; AC-3 adds a structural AST-scan complement.
- **TQ-6 [harden] — Yarn test silently passes on `{"entries": {}}`.** **Resolution:** AC-2 forbids empty entries on non-empty body.
- **TQ-7 [block] — Original pathological input is malformed.** Repeated `dependencies:` blocks within one entry are not structurally pathological; the second `pkg@^1.0.0:` is overwritten. **Resolution:** new input is well-formed (many entries with multi-spec headers).
- **TQ-8 [harden] — YAML positive control missing.** Same as CV-7. **Resolution:** AC-12 + test.
- **TQ-9 [harden] — YAML side-effect assertion unreachable.** `echo adv_canary` doesn't touch the filesystem. **Resolution:** f-string YAML body interpolates `tmp_path / "adv-canary.txt"` into the `os.system "touch ..."` payload; assertion is hermetic.
- **TQ-10 [harden] — `__cause__` not asserted.** **Resolution:** AC-11.
- **TQ-11 [nit] — `adv` marker not registered.** S5-01 owns the registration; this story now declares the dependency. **Resolution:** AC-15 + **Depends on:** line.
- **TQ-12 [block] — `env_stripped` event misnamed.** Same as CV-4. **Resolution:** AC-8 fixed.
- **TQ-13 [nit] — Helper-extraction threshold not yet met.** **Resolution:** Notes explicitly say "do NOT extract".

### Consistency (CN-)

- **CN-1 [block] — Missing dependency on S5-01 for `adv` marker.** `--strict-markers` is enabled at `pyproject.toml:178`; only `bench` is registered. **Resolution:** `Depends on:` and AC-15 added.
- **CN-2 [block] — Phase 0 ADR-0012 missing from "ADRs honored".** The chokepoint contract is exactly what the shim test pins. **Resolution:** added to the header line with relative path.
- **CN-3 [harden] — "env-strip" language imprecise.** **Resolution:** Notes-for-implementer now distinguishes the inclusion model (silent) from the `_is_sensitive` denylist (emits structlog event).
- **CN-4 [block] — AC-2 silently green: `SENTINEL_FILE` cannot reach shim via `monkeypatch.setenv`.** Same root as CV-2/TQ-3. **Resolution:** see above.
- **CN-5 [harden] — AC-2 sensitive-vars assertion redundant with inclusion model.** **Resolution:** Notes paragraph explicitly states the parent-env path is structural; the denylist surface is separately covered by AC-7.
- **CN-6 [harden] — Garbage-output AC from ADR-0001 §Consequences line 34 missing.** **Resolution:** scope-deferred to S2-02's probe-level unit tests; OOS-1 surfaces the seam explicitly so the executor doesn't try to land it here.
- **CN-7 [harden] — `_HAS_PYARN` redundant on CI but load-bearing locally.** **Resolution:** Notes paragraph documents.
- **CN-8 [harden] — `tools/fuzz_yarn_lock.py` not in References.** **Resolution:** added; OOS-2 cross-references.
- **CN-9 [harden] — Timing assertion alone is probabilistic.** Added structural AST scan (AC-3) as the deterministic complement per CLAUDE.md "Determinism over probabilism".
- **CN-10 [nit] — `env_stripped` event name guess stale.** Same as CV-4. **Resolution:** AC-8 fixed.
- **CN-11 [nit] — Style-reference path correct.** No action.
- **CN-12 [nit] — `MalformedYAMLError` "or whatever" hedge stale.** S1-03 has landed; the contract is deterministic. **Resolution:** AC-10/AC-11 use the deterministic phrasing.

### Design-Patterns (DP-)

- **DP-1 [Notes] — Affirm "inline; rule-of-three not yet met" for shim factory.** S5-03 needs neither shim nor PATH-prepend primitive; 1-consumer; inline is correct per Rule 2. **Resolution:** Notes paragraph explicitly says "do NOT lift to `tests/adv/_helpers.py`".
- **DP-2 [Notes] — Articulate "test at the chokepoint, not the probe" architectural intent.** **Resolution:** Notes paragraph explains why `exec.run_allowlisted` is the surface, not `NodeBuildSystemProbe`. Mirrors S4-05.
- **DP-3 [Notes] — Functional-core deferred; module-level constants fine at 1 consumer.** **Resolution:** `_pathological_yarn_lock(approx_bytes)` is now a pure function (size-parametrized); `SHIM_BODY` + `UNSAFE_YAML` stay as module-level f-string/text constants — no second consumer.

## Story edits applied

- Header: added Phase 0 ADR-0012 to "ADRs honored"; updated "Depends on" to add S5-01; added the **Validation notes** block.
- Acceptance criteria: rewrote from 8 → 19 individually-verifiable ACs in 5 named groups (`Yarn` / `Shim` / `YAML` / `Hygiene` / `Out-of-scope`).
- Implementation outline: rewrote every code-shape detail to match the actual `exec.run_allowlisted` / `safe_yaml.load` / `_yarn.parse` signatures; SENTINEL_FILE travels through `env_extra`; sensitive vars passed through both parent (AC-6) and `env_extra` (AC-7); positive controls added.
- TDD plan red-code: every sample rewritten end-to-end to compile and exercise the right surface. New `_pathological_yarn_lock(approx_bytes)` pure builder. New AST-scan structural test. New positive-control YAML test. New `MY_LEGIT_VAR` chokepoint positive control.
- TDD plan green / refactor: rewritten to reflect the corrected env model and explicit "do not lift helpers" Rule-2 guidance.
- Notes for the implementer: expanded from 7 → 14 paragraphs covering the inclusion-model env semantics, the `env_extra` passthrough mechanism, the chokepoint-vs-probe scope, the `_HAS_PYARN` CI-vs-local nuance, the actual structlog event names, the `adv` marker dependency on S5-01, the rule-of-three deferral, and the ADR-0001 garbage-output scope deferral.

## Verdict: HARDENED

Original story had four block-tier failure modes that would have made the executor's first attempt fail for the wrong reason. Story now compiles against the real signatures and exercises both env-strip surfaces with mutation-resistant assertions, a deterministic AST-scan complement to the wall-clock budget, and explicit out-of-scope cross-references that prevent scope creep. Ready for `phase-story-executor`.
