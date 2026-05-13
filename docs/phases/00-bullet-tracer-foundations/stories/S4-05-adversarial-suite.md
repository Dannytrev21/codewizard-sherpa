# Story S4-05 — Adversarial test suite

**Step:** Step 4 — Cut the vertical slice: CLI, `LanguageDetectionProbe`, fixtures, end-to-end smoke
**Status:** Done (2026-05-13)
**Effort:** M
**Depends on:** S4-02
**ADRs honored (directly asserted):** ADR-0008, ADR-0010, ADR-0012
**ADRs honored (transitively via dispatch):** ADR-0007 (synthetic probe respects the §4 dataclass contract), ADR-0009 (gather continues when at least one probe survived)

## Done evidence (2026-05-13)

Implemented in one attempt — see [`_attempts/S4-05.md`](_attempts/S4-05.md). Full validator-pass against every AC; runtime evidence below.

| AC | Test name | File |
|---|---|---|
| AC-1 | (package marker) | `tests/adv/__init__.py` |
| AC-2a, AC-2c | `test_path_traversal_nonexistent_refused` | `tests/adv/test_path_traversal.py:24` |
| AC-2b | `test_path_traversal_existing_outside_root_refused` (`xfail(strict=True)`) | `tests/adv/test_path_traversal.py:57` |
| AC-3, AC-3-platform | `test_symlink_out_of_repo_skipped` | `tests/adv/test_symlink_escape.py:34` |
| AC-4a | `test_secret_field_rejected_by_validator_top_level` | `tests/adv/test_secret_leak.py:63` |
| AC-4b | `test_secret_field_rejected_by_validator_at_depth_3_via_list` | `tests/adv/test_secret_leak.py:84` |
| AC-4c | `test_secret_leaking_probe_caught_at_coordinator_boundary` | `tests/adv/test_secret_leak.py:159` |
| AC-4d | `test_secret_leak_defense_in_depth_via_sanitizer` | `tests/adv/test_secret_leak.py:226` |
| AC-5a | `test_parent_env_built_by_omission` | `tests/adv/test_env_var_strip.py:54` |
| AC-5b (filter) | `test_env_extra_sensitive_keys_filtered` | `tests/adv/test_env_var_strip.py:103` |
| AC-5b (case-insensitive) | `test_env_extra_case_insensitivity` | `tests/adv/test_env_var_strip.py:158` |
| AC-6 | `pytest tests/adv/ -q` → **9 passed, 1 xfailed** | runtime |
| AC-7 | every test function carries the `Pins/Traces to/Catches` triple | inspection |
| AC-8 | `ruff check tests/adv/` clean · `ruff format --check tests/adv/` clean · `mypy --strict src/` clean · full `pytest tests/` → 586 passed, 1 xfailed, coverage 93.36% | runtime |

Open questions (Q1: seven-vs-four scope; Q2: containment plan for AC-2b; Q3: catch-vs-propagate for sanitizer raise) carried forward in [`_attempts/S4-05.md`](_attempts/S4-05.md). Q1 blocks Phase 0 exit per `High-level-impl.md §Step 5 Done criteria`.

## Validation notes

Validated by `phase-story-validator` on 2026-05-13 — verdict **HARDENED**. Full audit at [`_validation/S4-05-adversarial-suite.md`](_validation/S4-05-adversarial-suite.md). Six block-/harden-level findings drove the edits below:

1. **Path-traversal test was pinning the wrong chokepoint** (TQ-1 / COV-1). The story claimed `Path.resolve(strict=True)` was the rejection mechanism; the actual chokepoint is `click.Path(exists=True, file_okay=False, path_type=Path)` at [`cli.py:544`](../../../../src/codegenie/cli.py). The test as written (`tmp_path / "sub" / ".." / ".." / "etc"`) only verifies "non-existent paths are refused," which a removal of the in-repo-root check would *not* fail. References corrected; AC-2 split into two assertions (non-existent path AND existing out-of-root path).
2. **Secret-leak coordinator-boundary test was a stub** (TQ-2). The TDD plan's `test_secret_leaking_probe_does_not_poison_gather` had a literal `...  # full body in green phase` body. The implementer was left to derive the `coordinator.gather(...)` six-arg dispatch on their own. Concrete skeleton wired into the green-phase plan; AC-4 now pins the error-string format regex from S3-05 AC-13 (`^SecretLikelyFieldNameError: .+ at \(.+\)$`).
3. **Env-strip test missed the only mutation-relevant attack surface** (TQ-3 / COV-2). The parent-env path is invariant by construction (`exec.py:14-18` documents "built by omission"); the test never exercised the `env_extra` filter, which is the *only* path a future regression can plausibly weaken. AC-5 expanded to cover both attack surfaces and to assert closed-world env (`set(env.keys()) == {PATH, HOME, LANG, LC_ALL} | env_extra.keys()`).
4. **Defense-in-depth (ADR-0008 second pass) was unasserted** (CON-2). ADR-0008 §Decision item 1 names the sanitizer's repeat-pass "the second wall in case a future bug routes around the validator"; the original story honored only pass 1. New AC pins: bypassing `_ProbeOutputValidator` (monkeypatched to a no-op) still causes the sanitizer to reject — the two-pass invariant is the test's intent.
5. **Symlink-escape event payload value was unasserted** (COV-4 / TQ-4). AC said "referencing the offending entry's repo-relative path" but the test only checked `len(escaped) == 1`. A regression that emitted the event without the `path=` field, or for the wrong entry, would pass. AC-3 now pins `escaped[0]["path"] == "link.js"`, asserts no resolved-target leak (`/etc/hosts` must not appear in the event payload), and parses the YAML (not substring-matches) to assert `language_stack.counts["javascript"] == 1`.
6. **The story falsely claimed Step 2 had landed the three AST-scan tests** (CON-1). `tests/adv/` does not yet exist; [`exec.py:32-35`](../../../../src/codegenie/exec.py) attributes `test_no_shell_true.py` to **this story (S4-05)**, not S2-04. The discrepancy between `High-level-impl.md §Step 2 Done criteria` and the actual landed code is real. Context block corrected; an open question is filed for the user (expand S4-05 to seven tests, or file a sibling story before Step 5's done-criteria can be met).

Harden-level edits also: AC-4 now pins the `probe.failure` structlog event with `reason` matching the S3-05 regex; the synthetic probe's depth-3 path (key nested inside a list inside a dict) is exercised to mirror `test_probe_output_validator.py::test_secret_key_at_depth_3_via_list_rejected`; AC-4 explicitly forbids `default_registry` pollution; docstring schema formalized in AC-7 (`Pins: … Traces to: … Catches: …`); cache-side-effect (`if not sanitized.errors: cache.put(...)` per `coordinator.py:365`) pinned by AC-4.

## Context

The architecture commits a posture of "structural defenses, not runtime checks" (`phase-arch-design.md §Agentic best practices — Tool-use safety`; `final-design.md §2.5`). The `tests/adv/` suite is the executable form of that posture: each test pins one structural invariant — no `shell=True`, no network imports, env strip works, paths don't escape, secrets don't leak, YAML loaders are safe — so that a regression silently widening any of these surfaces fails CI on the same PR that introduces it.

This story ships **four** of the seven Phase-0 adversarial tests: `test_path_traversal.py`, `test_symlink_escape.py`, `test_secret_leak.py`, `test_env_var_strip.py` — each a behavioral assertion against the CLI, the coordinator, or `exec.run_allowlisted`. The remaining three (`test_no_shell_true.py`, `test_no_network_imports.py`, `test_yaml_unsafe_load.py`) are pure AST-scan tests over `src/codegenie/`.

> **Reality check (recorded by validator 2026-05-13):** `High-level-impl.md §Step 2 Done criteria` lines 76-78 list the three AST-scan tests as **Step 2** deliverables, but they have **not** yet landed (`tests/adv/` does not exist in the repo; S2-04 closed without them). `src/codegenie/exec.py:32-35` already attributes `test_no_shell_true.py` to "Phase 0 adversarial suite, **S4-05**" — i.e., the implementation expects this story to land it. **Until that contradiction is resolved by the user**, this story keeps the four-test scope as designed by `phase-story-writer`; an Open question below surfaces the choice (expand S4-05 to seven, or file a sibling story). Step 5's done-criteria (`High-level-impl.md:189`) requires all seven to exist — that gate must close before phase exit.

These tests are deliberately small. Each pins one invariant. The value is the *set* — together they form the structural belt to the harness's suspenders.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy — Adversarial tests` — the seven-test enumeration; this story owns the four not landed in Step 2.
  - `../phase-arch-design.md §Edge cases` — row 4 (symlink-escape), row 5 (secret-shaped field), row 7 (symlink output target), row 9 (fence — already covered).
  - `../phase-arch-design.md §Scenarios — Scenario 4` — the secret-leak path; the test pins the structural defense.
  - `../phase-arch-design.md §Agentic best practices — Tool-use safety` — env-stripping, no network egress.
  - `../phase-arch-design.md §Component design — CLI` — the CLI uses `click.Path(exists=True, file_okay=False, path_type=Path)` to reject non-existent paths; the test pins the rejection. **Note:** the original story claimed `Path.resolve(strict=True)` was the chokepoint; the actual implementation at [`cli.py:544`](../../../../src/codegenie/cli.py) uses click's validator (line 360 calls `path.resolve()` *without* `strict=True`). Validator 2026-05-13 corrected the reference.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0008-output-sanitizer-two-pass-chokepoint.md` — ADR-0008 — `test_secret_leak.py` pins the defense-in-depth: the validator catches secret-shaped fields (pass 1); the sanitizer repeats the pass (pass 2). AC-4 covers BOTH passes — the second-pass assertion neutralizes the validator and asserts the sanitizer still rejects.
  - `../ADRs/0010-pydantic-probe-output-validator.md` — ADR-0010 — `test_secret_leak.py` asserts `_ProbeOutputValidator` raises `SecretLikelyFieldNameError` on a secret-shaped key (top-level AND nested-in-list, mirroring `tests/unit/test_probe_output_validator.py::test_secret_key_at_depth_3_via_list_rejected`).
  - `../ADRs/0012-subprocess-allowlist-chokepoint.md` — ADR-0012 — `test_env_var_strip.py` pins `OPENAI_API_KEY` / `AWS_*` / `SSH_AUTH_SOCK` never reaching the child of `run_allowlisted` via **either** attack surface: (a) the parent-env path (invariant by construction — env is built by *omission*, see `exec.py:14-18`) and (b) the `env_extra` path (enforced by `_is_sensitive`, the only mutation-relevant surface).
- **Source design:**
  - `../final-design.md §7.3` — adversarial-tests enumeration and rationale.
- **Existing code:**
  - [`src/codegenie/cli.py:544`](../../../../src/codegenie/cli.py) — `click.Path(exists=True, file_okay=False, path_type=Path)` is the chokepoint for path-traversal (the gather argument's validator); line 360 then calls `path.resolve()` to normalize before passing to the coordinator.
  - [`src/codegenie/exec.py:111-148`](../../../../src/codegenie/exec.py) — `_filter_env` builds the child env by *omission*: only `{PATH, HOME, LANG, LC_ALL}` are explicitly pulled from `os.environ`; `env_extra` is overlaid with sensitive keys dropped via `_is_sensitive`. A `subproc.env_extra.sensitive_key_dropped` structlog event fires on each drop (line 143).
  - [`src/codegenie/probes/language_detection.py:142-200`](../../../../src/codegenie/probes/language_detection.py) — `_classify_symlink` returns `"in_tree"`/`"escaped"`/`"broken"`; the walker emits `probe.symlink.escaped` with `path=<relative path>` (line 198) and `probe=<probe.name>` (line 197) but never with the resolved target. The test pins both the field-value and the no-leak invariant.
  - [`src/codegenie/coordinator/validator.py:103-125`](../../../../src/codegenie/coordinator/validator.py) — `_walk_and_enforce` raises `SecretLikelyFieldNameError` on a secret-shaped key at any depth (iterative walk through dicts AND lists).
  - [`src/codegenie/coordinator/coordinator.py:176-201,317-344,365`](../../../../src/codegenie/coordinator/coordinator.py) — `_format_secret_error` produces the pinned `^SecretLikelyFieldNameError: .+ at \(.+\)$` string (S3-05 AC-13); the validator-rejection path emits `probe.failure` with `reason=` containing that string; `if not sanitized.errors: cache.put(...)` is the *cache-side-effect* invariant — failed probes are NEVER cached.
  - [`src/codegenie/output/sanitizer.py:143-159`](../../../../src/codegenie/output/sanitizer.py) — `scrub` calls `_walk_pass1_keys` and raises `SecretLikelyFieldNameError` on the same regex (defense-in-depth, ADR-0008 §Decision item 1). A `sanitizer.secret.rejected` structlog event fires immediately before the raise (line 156).
  - `src/codegenie/errors.py` — `SecretLikelyFieldNameError`, `SymlinkRefusedError`, `DisallowedSubprocessError`.

## Goal

`pytest tests/adv/ -q` exits 0; the four new test files (`test_path_traversal.py`, `test_symlink_escape.py`, `test_secret_leak.py`, `test_env_var_strip.py`) each pin one structural invariant; a single deliberate regression to the corresponding chokepoint causes the respective test to fail.

## Acceptance criteria

- [ ] **AC-1 — package marker.** `tests/adv/__init__.py` exists (empty; pytest package marker). The story should not assume Step 2 created it — see Context block: until the user resolves the seven-vs-four scope question, S4-05 owns the marker.

### Path traversal — `tests/adv/test_path_traversal.py`

- [ ] **AC-2a — non-existent path refused.** Invoking `cli` with `["gather", str(tmp_path / "sub" / ".." / ".." / "etc")]` is refused with a non-zero exit code. The structural invariant pinned here is "click's `exists=True` validator at [`cli.py:544`](../../../../src/codegenie/cli.py) rejects paths whose final component does not exist on disk." Test does **not** assert a specific exit code (1 for unhandled, 2 for click usage error, or any other non-zero — pinning a code couples the test to the rejection mechanism, which violates `CLAUDE.md` Rule 3).
- [ ] **AC-2b — existing out-of-root path documented as a gap.** A second test case (`test_existing_path_outside_caller_root`) creates a `tmp_path/outside/` directory and a separate `tmp_path/repo/` directory; invokes `cli` with `["gather", str(tmp_path / "repo" / ".." / "outside")]` (a `..`-bearing path that resolves to a real existing directory). **Current behavior** (per `cli.py:360`'s `path.resolve()` without `strict=True`): gather succeeds against `outside/` because no repo-root containment check exists. The test is `@pytest.mark.xfail(reason="Phase 0 does not enforce repo-root containment for the gather argument; tracked as a follow-up — surface to S4-02 author")` with `strict=True` (so a future implementation of repo-root containment flips the test to PASS, which xfail-strict treats as a failure → the test must be un-xfail'd at that point). This documents the gap *executably* per `CLAUDE.md` Rule 12 (fail loud).
- [ ] **AC-2c — no side-effects on rejection.** When the rejection in AC-2a fires, no `.codegenie/` directory is created anywhere under `tmp_path` (asserted via `not any((tmp_path).rglob(".codegenie"))`). A regression that wrote artifacts before validating the path would fail this.

### Symlink escape — `tests/adv/test_symlink_escape.py`

- [ ] **AC-3 — symlink resolving out-of-repo is skipped.** The test:
  - Creates `tmp_path/a.js` (valid file), `tmp_path/link.js` (symlink → `/etc/hosts`).
  - Runs `cli` via `CliRunner().invoke(cli, ["gather", str(tmp_path), "--no-gitignore"])` inside `with capture_logs() as logs:` (from `structlog.testing`).
  - **Asserts exit 0** (`result.exit_code == 0, result.output`).
  - **Asserts the YAML's parsed structure** — not a substring: load `(tmp_path / ".codegenie" / "context" / "repo-context.yaml").read_text()` via `yaml.safe_load`, then `assert data["language_stack"]["counts"] == {"javascript": 1}` (closed-world dict equality, so a regression that added an extra spurious language would fail).
  - **Asserts a `probe.symlink.escaped` event was emitted exactly once.** `escaped = [e for e in logs if e.get("event") == "probe.symlink.escaped"]; assert len(escaped) == 1`.
  - **Asserts the event payload binds to the offender:** `assert escaped[0]["path"] == "link.js"` (the relative path; matches `_relative_path` at [`language_detection.py:130`](../../../../src/codegenie/probes/language_detection.py)). A regression that emitted the event for the wrong entry, or with no `path` field, would fail.
  - **Asserts no resolved-target leak:** `assert "/etc/hosts" not in str(escaped[0])` and `assert "/etc/hosts" not in result.output`. The mirror invariant from `tests/unit/test_language_detection_probe.py:177-181` — the log payload must not become a fingerprinting oracle for host paths.
- [ ] **AC-3-platform.** The test is `@pytest.mark.skipif(sys.platform == "win32", reason="symlink test requires POSIX")`.

### Secret leak — `tests/adv/test_secret_leak.py` (three sub-tests)

- [ ] **AC-4a — validator-direct rejection (top-level key).** `_ProbeOutputValidator(schema_slice={"github_token": "ghp_AAAAAAAAAA"}, confidence="high")` raises `pydantic.ValidationError`; the typed error retrieved via `errors()[0]["ctx"]["error"]` (preferred surface) or `__cause__` (fallback) is a `SecretLikelyFieldNameError` instance. The unwrap idiom mirrors `tests/unit/test_probe_output_validator.py::_unwrap_typed_error` (lines 168-180) — inline it; cross-test-dir helper imports are discouraged.
- [ ] **AC-4b — validator-direct rejection at depth-3 via list.** Same assertion as AC-4a but with `schema_slice={"a": {"b": [{"github_token": "ghp_AAAAAAAAAA"}]}}`. This mirrors `test_probe_output_validator.py::test_secret_key_at_depth_3_via_list_rejected` and pins the walker's list-traversal branch (a regression that narrowed `_walk_and_enforce` to `if isinstance(v, dict):` would slip through without this assertion).
- [ ] **AC-4c — coordinator-boundary rejection (`_SecretLeakingProbe` through `coordinator.gather`).** A one-off `class _SecretLeakingProbe(Probe)` defined inline in the test file (NOT decorated with `@register_probe`; the test must NOT mutate `default_registry`). Dispatched alongside `LanguageDetectionProbe` via `await coordinator.gather(snapshot, task, probes=[_SecretLeakingProbe(), LanguageDetectionProbe()], config, cache, sanitizer)` against `tmp_path`. The test asserts:
  - `executions["_secret_leak"]` is a `Ran` instance (not `CacheHit` / `Skipped`) — the probe ran and the coordinator caught the validator's error.
  - `executions["_secret_leak"].output.confidence == "low"`.
  - `executions["_secret_leak"].output.errors` is non-empty and its first entry **matches the regex** `r"^SecretLikelyFieldNameError: .+ at \(.+\)$"` (S3-05 AC-13 contract; produced by `_format_secret_error` at [`coordinator.py:176-201`](../../../../src/codegenie/coordinator/coordinator.py)). A mutation that dropped the `at (path)` suffix from the formatter would fail this regex.
  - A `probe.failure` structlog event was emitted with `probe="_secret_leak"` and `reason` matching the same regex. A regression that bypassed `_format_secret_error` (e.g., emitting a raw `str(exc)`) would fail.
  - **Cache-side-effect invariant:** the `_secret_leak` entry is NOT persisted to the cache. Specifically, after the gather, no blob under `.codegenie/cache/blobs/` contains the literal string `"github_token"` (recursive walk). This pins `coordinator.py:365` (`if not sanitized.errors: cache.put(...)`).
  - The gather as a whole exited 0 (because `LanguageDetectionProbe` succeeded; per ADR-0009 the surviving probe's success is enough). The exit-2 branch (all probes failed) is **out of scope** here — covered by `tests/unit/test_cli_exit_codes.py` (S4-02).
- [ ] **AC-4d — defense-in-depth: sanitizer's pass-2 catches when validator is neutralized** (ADR-0008 §Decision item 1; phase-arch-design.md §Edge cases row 5). The test monkeypatches `codegenie.coordinator.validator._ProbeOutputValidator.model_validate` to a no-op (`lambda *a, **kw: None`), simulating "a future bug routes around the validator." Then dispatches `_SecretLeakingProbe` through `coordinator.gather` as in AC-4c and asserts:
  - The sanitizer raises `SecretLikelyFieldNameError` (uncaught by the current coordinator — propagates from `sanitizer.scrub` at `coordinator.py:347`). The test asserts the raise via `pytest.raises(SecretLikelyFieldNameError)` around the `asyncio.run(...)` of the gather, **or** if the coordinator is later updated to catch sanitizer errors and downgrade to `ProbeOutput.errors`, the test asserts the catch-and-degrade path with `executions["_secret_leak"].output.errors` containing `"SecretLikelyFieldNameError"`. **Either form is acceptable** — the structural invariant is "the secret-shaped key does NOT survive to disk." Concretely the test also asserts no `repo-context.yaml` written under `tmp_path/.codegenie/` contains the literal `"github_token"` (recursive read).
  - A `sanitizer.secret.rejected` structlog event was emitted with `key="github_token"` (`sanitizer.py:156`).

### Env-var strip — `tests/adv/test_env_var_strip.py` (two sub-tests)

- [ ] **AC-5a — parent-env never copied (build-by-omission invariant).** `monkeypatch.setenv` is used for `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `AWS_SECRET_ACCESS_KEY`, `SSH_AUTH_SOCK`, `GITHUB_TOKEN`. `asyncio.create_subprocess_exec` is patched via `monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)` (matching the idiom in `tests/unit/test_exec.py`) to capture the `env=` kwarg. `await run_allowlisted(["git", "rev-parse", "HEAD"], cwd=tmp_path, timeout_s=10)` is invoked via `asyncio.run`. Assertions:
  - **Closed-world env.** `set(env.keys()) == {"PATH", "HOME", "LANG", "LC_ALL"}` (no `env_extra` in this sub-test). This is *stronger* than asserting absence of sensitive keys — it pins the *structural* invariant from [`exec.py:14-18`](../../../../src/codegenie/exec.py) ("built by omission, not by deletion"). A regression that switched to `env = {**os.environ}; for k in sensitive: env.pop(k, None)` would fail the closed-world check even though sensitive keys are still absent.
  - For each sensitive var name, `assert var not in env` (redundant given closed-world, but a clearer failure message if the assertion fires).
- [ ] **AC-5b — `env_extra` sanitization (the mutation-relevant surface).** Same fake_create patch as AC-5a. Invokes `await run_allowlisted(["git", "rev-parse", "HEAD"], cwd=tmp_path, timeout_s=10, env_extra={"OPENAI_API_KEY": "leak", "AWS_SECRET_ACCESS_KEY": "leak", "SSH_AUTH_SOCK": "leak", "GITHUB_TOKEN": "leak", "ANTHROPIC_API_KEY": "leak", "MY_LEGIT_VAR": "kept"})`. Assertions:
  - **None of the sensitive keys appear** in the captured `env`. A removal of `_is_sensitive` (or of the `if _is_sensitive(key): continue` branch at [`exec.py:142`](../../../../src/codegenie/exec.py)) would fail this — and this is the ONLY mutation that can plausibly land in a future PR (the parent-env-omission is structural).
  - **`MY_LEGIT_VAR` IS present** in the env (proves `env_extra` overlay still works for non-sensitive keys).
  - **`subproc.env_extra.sensitive_key_dropped` structlog event was emitted at least once.** This pins that the chokepoint *ran*; a regression that silently widened the allowlist (e.g., `_SENSITIVE_EXACT = frozenset()`) would not emit the event and would fail the assertion. Capture via `structlog.testing.capture_logs()`.
  - **Case-insensitivity invariant.** A separate call with `env_extra={"openai_api_key": "leak"}` (lowercase) also drops it — pins `_is_sensitive`'s `upper()` normalization at [`exec.py:117`](../../../../src/codegenie/exec.py). A regression that removed `upper()` would let lowercase variants through.

### Cross-cutting

- [ ] **AC-6 — all assertions green on clean Phase 0.** `pytest tests/adv/test_path_traversal.py tests/adv/test_symlink_escape.py tests/adv/test_secret_leak.py tests/adv/test_env_var_strip.py -q` exits 0 on a clean Phase 0 implementation.
- [ ] **AC-7 — docstring schema formalized.** Each new test function's docstring follows a three-line schema:
  ```
  """
  Pins: <one-sentence statement of the structural invariant>
  Traces to: <ADR-NNNN or phase-arch-design.md §Edge cases row N>
  Catches: <one example mutation that this test would fail under>
  """
  ```
  The "Catches:" line is what makes the test mutation-explicit for future reviewers per `CLAUDE.md` Rule 9 ("tests verify intent, not just behavior"). Per-file top-of-module docstrings also exist (already in the TDD plan sketches).
- [ ] **AC-8 — toolchain green.** `ruff check tests/adv/`, `ruff format --check tests/adv/`, and the pytest invocation in AC-6 all exit 0. `mypy --strict tests/adv/` (if the project's mypy config covers tests) passes.

## Implementation outline

1. **Create `tests/adv/__init__.py`** (empty file; pytest package marker). Per the Context block, this file does not exist yet — S4-05 owns it until the seven-vs-four scope question is resolved.
2. **`test_path_traversal.py`** — Two test cases (AC-2a, AC-2b, AC-2c). Use `CliRunner` from `click.testing`. AC-2a: a `..`-bearing non-existent path is rejected with non-zero exit. AC-2b: a `..`-bearing existing-out-of-root path is documented as a gap via `@pytest.mark.xfail(strict=True, reason="Phase 0 does not enforce repo-root containment for the gather argument")` — if S4-02 is later updated to enforce containment, the xfail flips to PASS and `strict=True` makes the suite fail until the test is un-xfail'd. AC-2c: no `.codegenie/` is written under `tmp_path` on rejection.
3. **`test_symlink_escape.py`** — Create the symlink via `os.symlink("/etc/hosts", tmp_path/"link.js")`. Use `structlog.testing.capture_logs()` around the `CliRunner.invoke(...)` call. Parse the written YAML via `yaml.safe_load` (NOT substring match); assert `data["language_stack"]["counts"] == {"javascript": 1}` (closed-world). Assert `escaped[0]["path"] == "link.js"` and `"/etc/hosts" not in str(escaped[0])`. POSIX-only via `@pytest.mark.skipif`.
4. **`test_secret_leak.py`** — Four test functions:
   - `test_secret_field_rejected_by_validator_top_level` (AC-4a): `_ProbeOutputValidator(schema_slice={"github_token": "..."}, confidence="high")` raises; unwrap typed error inline (mirror `tests/unit/test_probe_output_validator.py::_unwrap_typed_error`).
   - `test_secret_field_rejected_by_validator_at_depth_3_via_list` (AC-4b): same with `schema_slice={"a": {"b": [{"github_token": "..."}]}}`.
   - `test_secret_leaking_probe_caught_at_coordinator_boundary` (AC-4c): synthetic `_SecretLeakingProbe` (NOT decorated with `@register_probe`); dispatch via `await coordinator.gather(snapshot, task, probes=[_SecretLeakingProbe(), LanguageDetectionProbe()], config, cache, sanitizer)`; assert error-string regex, `probe.failure` event, cache absence. Use a fresh `CacheStore(tmp_path/".cache")` to avoid polluting any shared state.
   - `test_secret_leak_defense_in_depth_via_sanitizer` (AC-4d): monkeypatch `codegenie.coordinator.validator._ProbeOutputValidator.model_validate = lambda *a, **kw: None`; dispatch as in 4c; assert `pytest.raises(SecretLikelyFieldNameError)` around `asyncio.run(...)` of the gather (or, if the coordinator is later updated to catch+degrade, assert via `executions[...].output.errors`); assert no written `repo-context.yaml` contains `"github_token"`; assert `sanitizer.secret.rejected` event with `key="github_token"`.
5. **`test_env_var_strip.py`** — Two test functions:
   - `test_parent_env_built_by_omission` (AC-5a): `monkeypatch.setenv(...)` for the sensitive vars; `monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)`; invoke `run_allowlisted(...)` without `env_extra`; assert `set(env.keys()) == {"PATH", "HOME", "LANG", "LC_ALL"}`.
   - `test_env_extra_sensitive_keys_filtered` (AC-5b): same patch; invoke with `env_extra={...sensitive..., "MY_LEGIT_VAR": "kept"}`; assert sensitive vars absent, `MY_LEGIT_VAR` present, `subproc.env_extra.sensitive_key_dropped` event emitted. Run twice (once with uppercase, once with lowercase keys) to pin `_is_sensitive`'s `upper()` normalization.
6. **One invariant per test function.** Per `phase-arch-design.md §Testing strategy — Adversarial tests`, the suite is a set of clearly named individual tests — resist combining invariants. The two-or-three sub-tests per file structure each pin one structural invariant; file-level grouping is by chokepoint (CLI / probe / coordinator / exec wrapper), not by invariant.

### Concrete coordinator dispatch skeleton (AC-4c, AC-4d)

The validator surfaced the `coordinator.gather(...)` six-arg signature as the load-bearing implementation gap (TQ-2). The executor SHOULD start from this skeleton:

```python
# tests/adv/test_secret_leak.py — coordinator-boundary fixture
import asyncio
from pathlib import Path
from types import SimpleNamespace
from structlog.testing import capture_logs
import pytest

from codegenie.coordinator.coordinator import gather, Ran
from codegenie.cache.store import CacheStore
from codegenie.output.sanitizer import OutputSanitizer
from codegenie.probes.base import Probe, ProbeOutput, RepoSnapshot, Task
from codegenie.probes.language_detection import LanguageDetectionProbe


class _SecretLeakingProbe(Probe):
    # NOT decorated — must NOT pollute default_registry (AC-4c isolation invariant).
    name = "_secret_leak"
    version = "0.0.0"
    tier = "task_specific"
    applies_to_tasks = ("*",)
    applies_to_languages = ("*",)
    declared_inputs = ("**/*",)
    timeout_seconds = 10

    async def run(self, snapshot, ctx):
        return ProbeOutput(
            schema_slice={"github_token": "ghp_AAAAAAAAAA"},
            raw_artifacts=[],
            confidence="high",
            duration_ms=0,
            warnings=[],
            errors=[],
        )


def _make_snapshot(repo_root: Path) -> RepoSnapshot:
    # Cross-reference RepoSnapshot's exact field list against probes/base.py
    # (frozen by ADR-0007). The executor must read the dataclass and pass the
    # required fields verbatim — do NOT improvise field names here.
    return RepoSnapshot(root=repo_root.resolve(), detected_languages={}, config={})


def test_secret_leaking_probe_caught_at_coordinator_boundary(tmp_path):
    """
    Pins: a synthetic probe emitting a secret-shaped key is caught at the coordinator
          boundary by _ProbeOutputValidator; the probe is marked failed; the gather
          continues; the cache does NOT persist the failed probe's output.
    Traces to: ADR-0010; phase-arch-design.md §Edge cases row 5; §Scenarios — Scenario 4.
    Catches: a regression that removed the validator call at coordinator.py:322 — the
             probe.failure event would not fire and `errors[]` would be empty.
    """
    snapshot = _make_snapshot(tmp_path)
    task = Task(name="__bullet_tracer__", languages=frozenset({"unknown"}))
    config = SimpleNamespace(max_concurrent_probes=4, cache_ttl_hours=24)
    cache = CacheStore(tmp_path / ".codegenie" / "cache")
    sanitizer = OutputSanitizer()

    with capture_logs() as logs:
        result = asyncio.run(
            gather(snapshot, task, [_SecretLeakingProbe(), LanguageDetectionProbe()],
                   config, cache, sanitizer)
        )

    exe = result.executions["_secret_leak"]
    assert isinstance(exe, Ran)
    assert exe.output.confidence == "low"
    assert exe.output.errors, "validator must have populated errors[]"
    import re
    assert re.match(r"^SecretLikelyFieldNameError: .+ at \(.+\)$", exe.output.errors[0]), \
        f"error-string format drift (S3-05 AC-13): {exe.output.errors[0]!r}"

    # Cache-side-effect invariant: failed probes are NEVER cached (coordinator.py:365).
    cache_blobs = list((tmp_path / ".codegenie" / "cache").rglob("*.json"))
    for blob in cache_blobs:
        assert "github_token" not in blob.read_text(), \
            f"failed probe's output leaked into cache: {blob}"

    # probe.failure structlog event with the regex-matching reason.
    failures = [e for e in logs if e.get("event") == "probe.failure" and e.get("probe") == "_secret_leak"]
    assert len(failures) == 1
    assert re.match(r"^SecretLikelyFieldNameError: .+ at \(.+\)$", failures[0]["reason"])
```

**Note:** the exact dataclass field names for `RepoSnapshot` and `Task` (and the `Task` constructor signature) are byte-frozen by ADR-0007 — read [`src/codegenie/probes/base.py`](../../../../src/codegenie/probes/base.py) at implementation time and reconcile against `localv2.md §4`. The skeleton above shows the dispatch *shape*; the field list must be verified against the snapshot.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths: `tests/adv/test_path_traversal.py`, `tests/adv/test_symlink_escape.py`, `tests/adv/test_secret_leak.py`, `tests/adv/test_env_var_strip.py`.

Each test pins one behavior. Write one red test per file.

```python
# tests/adv/test_path_traversal.py
"""Adversarial: CLI `gather` path argument is rejected via click's exists=True validator.

The structural invariant is "non-existent paths cannot be gathered." A separate
xfail-strict test (test_existing_path_outside_caller_root) documents the current
gap: Phase 0 does NOT enforce repo-root containment for paths that resolve to
real directories outside the caller's intended root (cli.py:360 uses .resolve()
without strict=True; see story Validation notes 2026-05-13).
"""
import pytest
from click.testing import CliRunner

def test_path_traversal_nonexistent_refused(tmp_path):
    """
    Pins: a `..`-bearing path whose final resolved component does not exist is
          refused by click.Path(exists=True) at cli.py:544 with a non-zero exit.
    Traces to: phase-arch-design.md §Component design — CLI; cli.py:544.
    Catches: a regression that removed exists=True from the click.Path validator —
             the path would be accepted and downstream code would fail with a less
             specific error (file-not-found at probe-walk time) instead of fast.
    """
    escapeful = str(tmp_path / "sub" / ".." / ".." / "etc")
    from codegenie.cli import cli
    result = CliRunner().invoke(cli, ["gather", escapeful])
    assert result.exit_code != 0
    # No .codegenie/ written anywhere under tmp_path on rejection (AC-2c).
    assert not list(tmp_path.rglob(".codegenie"))


@pytest.mark.xfail(
    strict=True,
    reason="Phase 0 does not enforce repo-root containment for the gather "
    "argument when the resolved path exists. Tracked as a follow-up against "
    "S4-02; when containment lands, this xfail flips to PASS and strict=True "
    "fails the suite until this test is un-xfail'd."
)
def test_path_traversal_existing_outside_root_refused(tmp_path):
    """
    Pins (aspirationally): a `..`-bearing path that resolves to an existing
          directory outside the caller's intended root is refused.
    Traces to: phase-arch-design.md §Edge cases (path traversal is a structural
          defense); documents the gap surfaced by phase-story-validator 2026-05-13.
    Catches: a future regression to any repo-root-containment check S4-02 ships.
    """
    (tmp_path / "repo").mkdir()
    (tmp_path / "outside").mkdir()
    escapeful = str(tmp_path / "repo" / ".." / "outside")
    from codegenie.cli import cli
    result = CliRunner().invoke(cli, ["gather", escapeful])
    assert result.exit_code != 0, (
        f"escape to existing out-of-root directory was NOT refused; "
        f"exit_code={result.exit_code}, output={result.output!r}"
    )
```

```python
# tests/adv/test_symlink_escape.py
"""Adversarial: out-of-repo symlinks are skipped, not followed.

The probe walker classifies a symlink whose resolved target is outside the
analyzed-repo root as "escaped" and emits `probe.symlink.escaped` with a
relative path. The structural invariants pinned here are: skip (count must
not bump), event-emitted-exactly-once, event-payload-binds-to-offender, and
no resolved-target leak in the log payload.
"""
import os, sys, pytest
import yaml
from pathlib import Path
from click.testing import CliRunner
from structlog.testing import capture_logs


@pytest.mark.skipif(sys.platform == "win32", reason="symlink test requires POSIX")
def test_symlink_out_of_repo_skipped(tmp_path):
    """
    Pins: a symlink whose target resolves outside the repo root is skipped by
          LanguageDetectionProbe and emits probe.symlink.escaped with the
          offender's repo-relative path and no resolved target.
    Traces to: ADR-0007 (LanguageDetectionProbe contract); phase-arch-design.md
               §Edge cases row 4; language_detection.py:142-200.
    Catches:
      - A regression that dropped the `if classification == "escaped": continue`
        line — the symlink would be followed → counts["javascript"] == 2 → YAML
        parse assertion fails (closed-world dict equality).
      - A regression that dropped the `path=` kwarg from the structlog call —
        the path-value assertion fails.
      - A regression that added a `target=<resolved>` field — the no-leak
        assertion fails.
    """
    (tmp_path / "a.js").write_text("//")
    os.symlink("/etc/hosts", tmp_path / "link.js")

    from codegenie.cli import cli
    with capture_logs() as logs:
        result = CliRunner().invoke(cli, ["gather", str(tmp_path), "--no-gitignore"])

    # 1) gather succeeds
    assert result.exit_code == 0, result.output

    # 2) probe.symlink.escaped emitted exactly once, bound to link.js, no leak
    escaped = [e for e in logs if e.get("event") == "probe.symlink.escaped"]
    assert len(escaped) == 1, f"expected exactly 1 escaped event, got {len(escaped)}: {escaped}"
    assert escaped[0].get("path") == "link.js", f"event bound to wrong entry: {escaped[0]!r}"
    assert "/etc/hosts" not in str(escaped[0]), f"resolved target leaked into log: {escaped[0]!r}"
    assert "/etc/hosts" not in result.output, f"resolved target leaked into stdout/stderr"

    # 3) YAML parse (not substring): closed-world counts
    yaml_path = tmp_path / ".codegenie" / "context" / "repo-context.yaml"
    data = yaml.safe_load(yaml_path.read_text())
    assert data["language_stack"]["counts"] == {"javascript": 1}, (
        f"language_stack.counts drifted: {data['language_stack']['counts']!r}"
    )
```

```python
# tests/adv/test_secret_leak.py
"""Adversarial: secret-shaped field names are rejected at TWO chokepoints.

Pass 1: _ProbeOutputValidator at the coordinator boundary (ADR-0010). Pass 2:
OutputSanitizer in the write path (ADR-0008 defense in depth). The two-pass
invariant is the whole point of the suite — pass-2 catches when pass-1 is
bypassed by a future bug.
"""
import asyncio, re
import pytest
from pathlib import Path
from types import SimpleNamespace
from pydantic import ValidationError
from structlog.testing import capture_logs

from codegenie.coordinator.validator import _ProbeOutputValidator
from codegenie.errors import SecretLikelyFieldNameError


def _unwrap_typed(exc: ValidationError):
    """Mirror tests/unit/test_probe_output_validator.py::_unwrap_typed_error (lines 168-180).
    Inline (not imported) — cross-test-dir helper imports are discouraged."""
    for e in exc.errors():
        ctx = e.get("ctx") or {}
        err = ctx.get("error")
        if isinstance(err, BaseException):
            return err
    return exc.__cause__


def test_secret_field_rejected_by_validator_top_level():
    """
    Pins: a secret-shaped key at the top of schema_slice raises ValidationError
          whose typed inner error (via errors()[0]['ctx']['error']) is
          SecretLikelyFieldNameError.
    Traces to: ADR-0010 §Decision; validator.py:108-109.
    Catches: a regression that removed the SECRET_FIELD_PATTERN.search(k) check.
    """
    with pytest.raises(ValidationError) as ei:
        _ProbeOutputValidator(schema_slice={"github_token": "ghp_AAAAAAAAAA"}, confidence="high")
    assert isinstance(_unwrap_typed(ei.value), SecretLikelyFieldNameError)


def test_secret_field_rejected_by_validator_at_depth_3_via_list():
    """
    Pins: the walker descends through dicts AND lists (depth 3+); a secret key
          inside `{a: {b: [{github_token: ...}]}}` still raises.
    Traces to: ADR-0010; validator.py:118-124 (list branch of _walk_and_enforce).
    Catches: a regression that narrowed the recursion to dicts only
             (e.g., dropping the `elif isinstance(node, list):` branch).
    """
    with pytest.raises(ValidationError) as ei:
        _ProbeOutputValidator(
            schema_slice={"a": {"b": [{"github_token": "ghp_AAAAAAAAAA"}]}},
            confidence="high",
        )
    assert isinstance(_unwrap_typed(ei.value), SecretLikelyFieldNameError)


# AC-4c — see "Concrete coordinator dispatch skeleton" in the Implementation
# outline above for the full body. Key assertions: Ran instance, confidence="low",
# errors[0] matches r"^SecretLikelyFieldNameError: .+ at \(.+\)$", probe.failure
# event emitted, cache has no entry containing "github_token".


def test_secret_leak_defense_in_depth_via_sanitizer(tmp_path, monkeypatch):
    """
    Pins: bypassing _ProbeOutputValidator (simulating a future bug) does NOT let
          the secret-shaped key survive to disk — OutputSanitizer.scrub catches
          it (ADR-0008 second pass).
    Traces to: ADR-0008 §Decision item 1; phase-arch-design.md §Edge cases row 5.
    Catches: a regression that removed pass-1 from sanitizer.py:159 (which would
             leave only the validator as the defense; this test would then write
             a file containing "github_token" to disk, and the assertion fails).
    """
    # Neutralize pass-1 to simulate the regression scenario.
    monkeypatch.setattr(
        "codegenie.coordinator.validator._ProbeOutputValidator.model_validate",
        classmethod(lambda cls, *a, **kw: None),
    )

    # Reuse the _SecretLeakingProbe + dispatch from AC-4c (extract a helper if both
    # tests share the fixture, or define the class once at module scope).
    from .test_secret_leak import _SecretLeakingProbe  # if extracted; else redefine inline
    # ... build snapshot/task/config/cache/sanitizer per the skeleton above ...

    with capture_logs() as logs:
        with pytest.raises(SecretLikelyFieldNameError):
            asyncio.run(...)  # gather(...) — see skeleton in Implementation outline

    # Either the sanitizer raised (current coordinator does not catch sanitizer
    # errors) OR the coordinator was updated to catch+degrade. Either way:
    sanitizer_events = [e for e in logs if e.get("event") == "sanitizer.secret.rejected"]
    assert len(sanitizer_events) == 1
    assert sanitizer_events[0].get("key") == "github_token"

    # And NOTHING containing "github_token" was persisted to disk.
    for yaml_file in tmp_path.rglob("repo-context.yaml"):
        assert "github_token" not in yaml_file.read_text()
```

```python
# tests/adv/test_env_var_strip.py
"""Adversarial: sensitive env vars never reach a subprocess via exec.run_allowlisted.

The chokepoint at codegenie/exec.py has TWO attack surfaces: the parent-env
path (invariant by construction — env is built by omission, see exec.py:14-18)
and the env_extra path (enforced by _is_sensitive, the only mutation-relevant
surface). The suite pins BOTH; a regression that loosens either fails.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock
from structlog.testing import capture_logs


def _make_fake_create():
    """Build a fake create_subprocess_exec spy that captures the env kwarg."""
    captured = {}
    async def fake_create(*args, **kwargs):
        captured["env"] = kwargs.get("env", {})
        mock = AsyncMock()
        mock.communicate = AsyncMock(return_value=(b"", b""))
        mock.returncode = 0
        return mock
    return captured, fake_create


def test_parent_env_built_by_omission(tmp_path, monkeypatch):
    """
    Pins: the child env is constructed by INCLUSION of {PATH, HOME, LANG, LC_ALL}
          (closed-world) — NOT by deletion from os.environ. Sensitive vars in
          the parent environment are structurally absent.
    Traces to: ADR-0012 §Decision line 31; exec.py:14-18 ("built by omission, not
               by deletion").
    Catches: a regression that switched to `env = {**os.environ}; env.pop(k, ...)
             for k in SENSITIVE` — that would leak any env var not in SENSITIVE
             (e.g. an internal `MY_API_TOKEN` someone forgot to enumerate). The
             closed-world set equality assertion fails.
    """
    import asyncio as _asyncio
    for v in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AWS_SECRET_ACCESS_KEY",
              "SSH_AUTH_SOCK", "GITHUB_TOKEN", "ROGUE_TOKEN"):
        monkeypatch.setenv(v, "secret-must-not-leak")
    captured, fake_create = _make_fake_create()
    monkeypatch.setattr(_asyncio, "create_subprocess_exec", fake_create)

    from codegenie import exec as cg_exec
    asyncio.run(cg_exec.run_allowlisted(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, timeout_s=10,
    ))

    env = captured["env"]
    # Closed-world: the child env has ONLY the four baseline keys (no env_extra here).
    assert set(env.keys()) == {"PATH", "HOME", "LANG", "LC_ALL"}, (
        f"env should be exactly the build-by-omission baseline; got {set(env.keys())!r}"
    )
    # Redundant-but-clear: each sensitive var is absent.
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AWS_SECRET_ACCESS_KEY",
                "SSH_AUTH_SOCK", "GITHUB_TOKEN", "ROGUE_TOKEN"):
        assert var not in env, f"{var} leaked into subprocess env"


def test_env_extra_sensitive_keys_filtered(tmp_path, monkeypatch):
    """
    Pins: caller-supplied env_extra is sanitized — sensitive keys are silently
          dropped (and logged) while legitimate keys pass through.
    Traces to: ADR-0012 §Decision; exec.py:111-148 (_is_sensitive + _filter_env).
    Catches: a regression that removed `_is_sensitive` or its caller — the only
             plausible regression surface for env-stripping, because the parent
             path is structural. The 'sensitive_key_dropped' event-emitted-once
             assertion adds a positive signal that the chokepoint ran.
    """
    import asyncio as _asyncio
    captured, fake_create = _make_fake_create()
    monkeypatch.setattr(_asyncio, "create_subprocess_exec", fake_create)

    from codegenie import exec as cg_exec
    with capture_logs() as logs:
        asyncio.run(cg_exec.run_allowlisted(
            ["git", "rev-parse", "HEAD"], cwd=tmp_path, timeout_s=10,
            env_extra={
                "OPENAI_API_KEY": "leak",
                "ANTHROPIC_API_KEY": "leak",
                "AWS_SECRET_ACCESS_KEY": "leak",
                "SSH_AUTH_SOCK": "leak",
                "GITHUB_TOKEN": "leak",
                "MY_LEGIT_VAR": "kept",
            },
        ))

    env = captured["env"]
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AWS_SECRET_ACCESS_KEY",
                "SSH_AUTH_SOCK", "GITHUB_TOKEN"):
        assert var not in env, f"{var} smuggled via env_extra"
    assert env.get("MY_LEGIT_VAR") == "kept", "legitimate env_extra key not passed through"

    drops = [e for e in logs if e.get("event") == "subproc.env_extra.sensitive_key_dropped"]
    assert len(drops) == 5, f"expected 5 drop events, got {len(drops)}: {drops}"


def test_env_extra_case_insensitivity(tmp_path, monkeypatch):
    """
    Pins: _is_sensitive normalizes to upper() — lowercase/mixed-case sensitive keys
          are also dropped.
    Traces to: ADR-0012; exec.py:117 (`upper = key.upper()`).
    Catches: a regression that removed the .upper() normalization — lowercase
             variants would slip through `_SENSITIVE_EXACT`.
    """
    import asyncio as _asyncio
    captured, fake_create = _make_fake_create()
    monkeypatch.setattr(_asyncio, "create_subprocess_exec", fake_create)

    from codegenie import exec as cg_exec
    asyncio.run(cg_exec.run_allowlisted(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, timeout_s=10,
        env_extra={"openai_api_key": "leak", "aws_secret": "leak"},
    ))

    env = captured["env"]
    assert "openai_api_key" not in env
    assert "OPENAI_API_KEY" not in env
    assert "aws_secret" not in env
```

Run each. Expected failures:
- `test_path_traversal.py::test_path_traversal_nonexistent_refused` — fails if `cli.py:544`'s `click.Path(exists=True)` is removed (gather would accept the bad path; downstream failure is less specific than fast-rejection).
- `test_path_traversal.py::test_path_traversal_existing_outside_root_refused` — `xfail(strict=True)` initially; flips to PASS (and the strict-xfail fails the suite) when S4-02 adds repo-root containment.
- `test_symlink_escape.py` — fails if S4-01's walker doesn't emit the structured event, follows the symlink, drops the `path=` kwarg, or leaks the resolved target.
- `test_secret_leak.py::test_secret_field_rejected_by_validator_top_level` and `::test_secret_field_rejected_by_validator_at_depth_3_via_list` — fail if S3-02's `_ProbeOutputValidator` (or its iterative `_walk_and_enforce`) doesn't raise on the secret-shaped key at top-level or at depth-3-via-list, respectively.
- `test_secret_leak.py::test_secret_leaking_probe_caught_at_coordinator_boundary` — fails if the coordinator doesn't (a) call the validator, (b) format the error per `_format_secret_error`, (c) emit `probe.failure`, (d) skip `cache.put` for failed probes.
- `test_secret_leak.py::test_secret_leak_defense_in_depth_via_sanitizer` — fails if S3-03's `OutputSanitizer.scrub` doesn't perform pass-1 (secret-shaped-key rejection); this is the load-bearing defense-in-depth assertion for ADR-0008.
- `test_env_var_strip.py::test_parent_env_built_by_omission` — fails if S2-04's `_filter_env` switches from build-by-inclusion to delete-from-os.environ.
- `test_env_var_strip.py::test_env_extra_sensitive_keys_filtered` and `::test_env_extra_case_insensitivity` — fail if `_is_sensitive` is removed or if its `upper()` normalization is dropped.

Commit all tests as the red marker. **Note**: AC-2b is `xfail(strict=True)` from day one — the red marker for it is "xfail recorded by pytest"; it converts to a real red only when S4-02 adds repo-root containment, at which point the test must be un-xfail'd in the same PR.

### Green — make it pass

In most cases, the four tests should pass against a properly implemented Phase 0. If a test reveals a real defect (e.g., `_ProbeOutputValidator` doesn't actually raise on `"github_token"` because the regex is too permissive), open a one-line fix PR in the relevant upstream story's module (S3-02 for the validator, S2-04 for the exec wrapper, etc.) **before** marking this story Done — surface the issue per `CLAUDE.md`'s global Rule 12.

If the tests pass straight away, that's the expected behavior: each adversarial test is a regression gate for an invariant the harness already honors. The tests' value is *future* regression detection, not present defect uncovering.

### Refactor — clean up

- Add docstrings on each test file (top-of-file, one paragraph) explaining the invariant and the ADR / phase-arch row it traces to.
- Where the test uses `capture_logs()` or `monkeypatch.setattr` over a specific module, add a comment with the rationale — these tests are read by future contributors who need to understand "why is this brittle-looking patch necessary?"
- Confirm `pytest tests/adv/` runs all seven tests (the three from Step 2 plus the four from this story); the suite should be a hermetic, fast-running set (target: each test < 500 ms; the full adversarial suite < 5 s).
- If a test relies on `CliRunner`, prefer `result.output` over `result.stderr` for assertions about logged events (click's `CliRunner` captures stdout and stderr together by default).
- Run `ruff format` over the new test files.

## Files to touch

| Path | Why |
|---|---|
| `tests/adv/test_path_traversal.py` | New test — pins the `Path.resolve(strict=True)` chokepoint |
| `tests/adv/test_symlink_escape.py` | New test — pins the `LanguageDetectionProbe` walker's symlink-escape skip |
| `tests/adv/test_secret_leak.py` | New test — pins `_ProbeOutputValidator`'s secret-shaped-field rejection + the coordinator's "gather continues" policy |
| `tests/adv/test_env_var_strip.py` | New test — pins `exec.run_allowlisted`'s env-allowlist filter |
| `tests/adv/__init__.py` | New if not already from Step 2 — pytest package marker |

## Out of scope

- **`test_no_shell_true.py`, `test_no_network_imports.py`, `test_yaml_unsafe_load.py`** — already landed in Step 2 per `High-level-impl.md §Step 2 Done criteria`. This story does not duplicate them.
- **`test_pyproject_fence.py`** — landed in Step 1 per `High-level-impl.md §Step 1`. The `fence` job is its own CI step; this story does not extend it.
- **Adversarial fuzz testing of attacker-controlled inputs** (e.g., crafted YAML files in the analyzed repo) — Phase 1 introduces the first probe (`NodeManifestProbe`) that reads attacker-controllable files; the fuzz suite lives there.
- **CVE feed adversarials** — Phase 3, per `phase-arch-design.md §Testing strategy — Adversarial tests`.
- **Prompt-injection adversarials** — Phase 4, per the same.
- **Performance regression tests** (`tests/bench/`) — handled by S5-01.
- **Documentation of the adversarial-suite contributor convention** — Phase 5 (`docs/contributing.md` extension per S5-02).

## Notes for the implementer

- Each adversarial test pins **one** invariant. If you find yourself adding a second assertion, ask: is that assertion the same invariant phrased differently, or a new invariant? If new, it goes in its own test file.
- The tests are not load-bearing in the bullet-tracer sense (S4-04 owns that). These are *regression* gates: they catch a future PR that silently weakens an invariant. The right shape is "small, fast, focused, and brittle in the *right* way — they fail if the invariant fails."
- `test_symlink_escape.py` requires POSIX. Skip on Windows. Symlink tests are notoriously flaky on Windows even with admin (developer-mode varies); the `@pytest.mark.skipif` is the right defense.
- `test_env_var_strip.py` mocks `asyncio.create_subprocess_exec`. This is intentional: the goal is to inspect what `run_allowlisted` *would have passed* to the subprocess, not to actually spawn one. A real-subprocess test is a Phase 2+ concern (real `git` invocation against the chokepoint) and lives in the `test_exec.py` unit test from S2-04.
- `test_secret_leak.py`'s synthetic `_SecretLeakingProbe` class is **only** in the test file — do **not** register it via `@register_probe` (it would pollute `default_registry`). Either instantiate the coordinator with a fresh `Registry()` containing just this probe (and `LanguageDetectionProbe`), or pass the probe class explicitly to `coordinator.gather(probes=[...])`.
- The secret regex from S3-02's `_ProbeOutputValidator` is `(?i)^.*(secret|token|password|credential|api[_-]?key|auth[_-]?token|bearer|access[_-]?key|private[_-]?key).*$` (per ADR-0010 §Decision; matches `final-design.md §2.6`). `"github_token"` matches `"token"`; `"api_key"` matches `"api[_-]?key"`; `"aws_access_key"` matches `"access[_-]?key"`. The regex matches on **field name** only (not the value), so `ghp_`/`sk-`-shaped *values* are NOT what triggers rejection — the key `github_token` is. If a test fails because the regex didn't match a name you expected, the regex needs widening — surface this as a follow-up to S3-02 (file an ADR-0010 amendment), do not loosen the adversarial assertion.
- The path-traversal test deliberately does **not** assert a specific exit code. Different rejection mechanisms (click's `exists=True` → exit 2; a `CodegenieError` subclass → exit per the dispatch table; an unhandled exception → exit 1) are all acceptable; the structural invariant is "this is refused with a non-zero exit." Pinning a specific exit code couples the test to the mechanism, which violates `CLAUDE.md` Rule 3.
- Avoid `pytest.mark.parametrize` here. Each test pins one invariant; parametrized adversarial tests obscure which invariant failed. Per `phase-arch-design.md §Testing strategy — Adversarial tests`, the suite is a set of clearly named individual tests.
- **Why two `test_secret_leak.py` validator-direct tests** (AC-4a and AC-4b) when `tests/unit/test_probe_output_validator.py` already covers them: the adversarial suite is the *single place* a future contributor looks to see "what regressions does the secret defense catch?" Mirroring the depth-3 unit-test assertion in the adversarial file makes the invariant inventory self-contained — a reviewer doesn't need to cross-walk to the unit-test directory to verify list-traversal coverage.
- **Why AC-2b is `xfail(strict=True)` rather than omitted entirely**: the validator surfaced a real gap (`cli.py:360` calls `path.resolve()` without `strict=True`; no repo-root containment exists for the gather argument). Omitting the test would silently leave the architecture's "path traversal is refused" claim unenforced. Using `xfail(strict=True)` documents the gap *executably* — when S4-02 lands the containment check, the test flips to PASS, the strict flag fires, and the suite forces a follow-up PR to remove the xfail. This is the right shape for "we know about this gap; we have not yet decided to close it; we want a hard reminder when someone else does."

## Open questions surfaced by the validator (not blocking; flagged for user / executor)

- **Q1 (high priority, blocks Phase 0 exit) — Scope of S4-05 vs. the three AST-scan tests.** `High-level-impl.md §Step 2 Done criteria` (lines 76-78) lists `test_no_shell_true.py`, `test_no_network_imports.py`, `test_yaml_unsafe_load.py` as Step 2 deliverables, but **they did not land** — `tests/adv/` does not exist and `src/codegenie/exec.py:32-35` already attributes `test_no_shell_true.py` to **S4-05**. `High-level-impl.md §Step 5 Done criteria` (line 189) requires all seven adversarial tests to pass before phase exit. The user must decide:
  - **Option A**: Expand S4-05 to seven tests (preferred — the three AST-scan tests share `tests/adv/__init__.py` and the structlog/AST-scan idioms; bundling avoids a sibling story).
  - **Option B**: File a sibling story (S4-05b or S5-03) for the three AST-scan tests before Step 5's done-criteria can be met.
  Either way, the comment in `exec.py:32-35` should be reconciled with whichever story actually lands `test_no_shell_true.py`.
- **Q2 (medium) — Does S4-02 plan to add repo-root containment for the gather argument?** AC-2b's `xfail(strict=True)` documents the gap. If the answer is "no, the gather argument is whatever the user passes; containment is the symlink walker's job," AC-2b should be **removed**, not kept as a permanent xfail (xfail-as-documentation is a smell when the documented state is intentional). If the answer is "yes, S4-02 plans to add it in Phase 1," keep AC-2b as-is.
- **Q3 (low) — Does the coordinator catch sanitizer errors and downgrade to `ProbeOutput.errors`, or does the sanitizer raise propagate?** AC-4d permits either form ("Either form is acceptable — the structural invariant is the secret-shaped key does NOT survive to disk"). The executor should pick one form based on the current `coordinator.py` behavior (today: sanitizer error propagates uncaught past `_dispatch_one`; the gather would surface this as a task exception). If the executor adds a try/except for `SecretLikelyFieldNameError` in `_dispatch_one` to graceful-degrade, that's an architectural change worth surfacing in an ADR amendment (ADR-0008 §Decision touched).
