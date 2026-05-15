# Story S5-02 — Lockfile + exec adversarial corpus: yarn regex-DoS, planted `node` shim, unsafe YAML tag

**Step:** Step 5 — Adversarial corpus + integration end-to-end + fixture portfolio
**Status:** Done — 2026-05-15. See `_attempts/S5-02.md`. All 16 ACs across 5 named groups verified by tests in `tests/adv/test_regex_dos_yarn_lock.py`, `tests/adv/test_planted_node_on_path_ignored.py`, `tests/adv/test_yaml_unsafe_tag.py`. Full suite green (1474 passed); walltime 0.65 s.
**Effort:** M
**Depends on:** S3-04 (yarn parity oracle ⇒ confirms hand-rolled path), S5-01 (registers the `adv` pytest marker in `pyproject.toml` so `pytest -m adv` selects this story's tests)
**ADRs honored:** [Phase 0 ADR-0012](../../00-bullet-tracer-foundations/ADRs/0012-subprocess-allowlist-chokepoint.md) (subprocess chokepoint — env built by *inclusion*, not deletion), ADR-0001 (`node` in `ALLOWED_BINARIES`), ADR-0003 (`pyarn` vs hand-rolled yarn-lock parser; land-time selection chose hand-rolled), ADR-0007 (typed-exception → ID mapping lands on `errors`, never `warnings`), ADR-0008 (in-process parse caps; `CSafeLoader` only), ADR-0009 (no new C-extension parser dependencies)

## Validation notes

Hardened on 2026-05-15 by phase-story-validator. Changes from the first-draft story (see `_validation/S5-02-adversarial-lockfile-exec.md` for the full audit log):

- **Wrong `run_allowlisted` invocation rewritten end-to-end.** `run_allowlisted` is `async`, requires `cwd: Path`, and the kwarg is `timeout_s` (not `timeout`). The original TDD-plan code (sync call, missing `cwd`, wrong kwarg name) failed at `TypeError` before any shim ran — the env-strip path was never exercised. Every code sample now `await`s the call with `cwd=tmp_path, timeout_s=…` inside an `async def` test.
- **`SENTINEL_FILE` cannot reach the shim via `monkeypatch.setenv` and must be passed through `env_extra`.** Per `exec.py:124-150`, the child env is built by *inclusion* of `{PATH, HOME, LANG, LC_ALL}` plus sanitized `env_extra`. The parent `os.environ` is **never copied**. The original test set `SENTINEL_FILE` and the sensitive-var sentinels via `monkeypatch.setenv`, where they were structurally invisible to the child — the shim's `$SENTINEL_FILE` redirect would have written to `""` and the test would have failed for the wrong reason. The hardened test now passes `SENTINEL_FILE` (and a `PATH` override that prepends the shim dir) through `env_extra`, which is the documented narrow passthrough.
- **Two distinct env-leak surfaces now pinned, with a positive control.** The original test only exercised the *parent-env inclusion* surface (which is also already pinned by `tests/adv/test_env_var_strip.py` from S4-05). A mutation that removed `_is_sensitive` entirely would have silently passed. The hardened test ALSO passes sensitive keys via `env_extra` (where `_is_sensitive` is the defense) and asserts the `subproc.env_extra.sensitive_key_dropped` structlog event fires for each — exercising the denylist directly. A `MY_LEGIT_VAR` positive control proves the spawn primitive honored the `env=` kwarg (catches a regression that drops `env=env` from `create_subprocess_exec`).
- **Bogus structlog event name removed.** Original AC-8 asserted `exec.run_allowlisted.env_stripped` — no such event exists. Actual events emitted by `exec.py` are `subproc.spawn`, `subproc.exit`, `subproc.timeout`, `subproc.env_extra.sensitive_key_dropped`. The AC now binds to the real `subproc.env_extra.sensitive_key_dropped` event, captured via `structlog.testing.capture_logs`.
- **`safe_yaml.load` signature fixed.** Original test called `safe_yaml.load(f)` — but `safe_yaml.py:80` requires the `max_bytes` kwarg. Test would have raised `TypeError` before the YAML body parsed and `CSafeLoader` was never the surface under test. Hardened call is `safe_yaml.load(f, max_bytes=1_000_000)`.
- **Pathological yarn-lock input replaced.** The original `PATHOLOGICAL` constant is a ~50 KB fixture that does not actually exercise any worst-case path in `_parse_handrolled` (which is a pure line-by-line state machine with no regex). A regression introducing O(n²) per-line work would still beat 1 s on a 50 KB input. The hardened test ALSO scales the input toward the 50 MB cap (~5 MB body) AND adds a structural assertion — `inspect.getsource(_yarn).count("re.")` checks plus an AST scan — pinning the "no regex over the full body" contract from `_yarn.py:116` and ADR-0003. Both a runtime budget (≤ 2 s) and a structural invariant (no `import re` in `_yarn.py`) are now required; the structural assertion is the deterministic complement to the flake-prone wall-clock bound (per CLAUDE.md "Determinism over probabilism").
- **Empty-return / shape mutation guard added to yarn test.** A regression that early-returns `{"entries": {}}` on any large input would satisfy the original timing assertion without raising. Hardened AC: if the call returns, `len(entries) > 0` AND result has the expected `YarnLock` shape; the only acceptable alternatives are a successful parse with non-empty entries OR `MalformedLockfileError`. The silent-empty path is explicitly forbidden.
- **YAML test gained a positive control + `__cause__` assertion.** A mutation replacing `safe_yaml.load` with `raise MalformedYAMLError("everything fails")` would have silently passed the original test. The hardened test now also loads a minimal valid `pnpm-lock.yaml` in the same module and asserts it returns; and asserts `exc_info.value.__cause__` is a `yaml.YAMLError` subclass — proving the translation path in `safe_yaml._parse_one` ran.
- **YAML hostile body unified on hermetic side-effect.** Original story had `echo adv_canary` in the TDD red-code (no filesystem side-effect) but `touch /tmp/codegenie-adv-canary` in the implementation outline (non-hermetic). Unified on a `tmp_path`-scoped sentinel via an f-string YAML body so the "no side-effect" assertion is observable and parallel-safe.
- **Garbage-output AC inherited from ADR-0001 acknowledged but scope-deferred.** ADR-0001 §Consequences line 34 names this file as the regression for `^v\d+\.\d+\.\d+`-garbage rejection. That assertion belongs at the **probe** level (`NodeBuildSystemProbe` is where the regex parse lives, per ADR-0001 line 26) and is owned by S2-02's unit tests; the chokepoint-level test in this story does not have visibility into the probe's parse-failure path. Notes-for-implementer makes this seam explicit so a future reader does not look for the AC here.
- **Probabilism guard.** The 1 s yarn assertion is supplemented by the structural AST/source-text assertion described above; the shim test now declares `@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell required")` as an AC, not just a Note.
- **`_HAS_PYARN` attribute existence pre-check.** Added `assert hasattr(codegenie.probes._lockfiles._yarn, "_HAS_PYARN")` before `monkeypatch.setattr(..., raising=True)` — guards against a future rename silently no-op'ing the patch on a contributor's machine where `pyarn` is installed.
- **Test-helper extraction deferred (rule of three not met).** S5-03 needs neither a shim-factory nor a PATH-prepend primitive. The shim body, hostile-YAML body, and pathological-yarn-lock body stay as module-level constants/single-use functions per Rule 2. If a Phase-2 story introduces a second consumer of any of these, lift then.
- **Verdict:** HARDENED — original story had 4 block-tier failure modes (structurally wrong invocation, sentinel unreachable, bogus event name, wrong `safe_yaml` signature) that would have made the executor's first attempt fail for the wrong reason; 5 harden-tier weaknesses around mutation-resistance; 3 Notes-only design clarifications. The original 8 ACs are now reorganised into 5 named AC groups with 19 individually-verifiable assertions.

## Context

The second of three adversarial-test stories in Step 5. S5-02 owns the **untrusted-input-into-stateful-component** family: the yarn-lock hand-rolled parser's regex-DoS surface, the `node --version` subprocess's hostile-binary surface, and `CSafeLoader`'s `!!python/object` refusal. Each defense lives in a different module (`_lockfiles/_yarn.py`, `exec.py`, `parsers/safe_yaml.py`), but they share the property that "the input is hostile and the component must refuse without side-effect."

The yarn regex-DoS test (`phase-arch-design.md §"Adversarial tests"` #9) is the load-bearing test for `High-level-impl.md §"Implementation-level risks"` item 4: the yarn-lock hand-rolled scanner is "the single most regex-DoS-prone piece of code in the phase." Local fuzzing before the S3-03 PR was non-negotiable; this story is the CI gate.

The planted-node-shim test (`phase-arch-design.md §"Adversarial tests"` #7, `final-design.md §"Adversarial tests"`) is the explicit acknowledgement that `node` on `$PATH` is not RCE-proof — the env-strip carries the load-bearing weight. The test does not assert that the shim cannot run; it asserts that `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `AWS_*`, `SSH_AUTH_SOCK` are not in the child process's environment when the shim is invoked.

The `!!python/object` test (`phase-arch-design.md §"Adversarial tests"` #4) is the simplest of the three but pins ADR-0008's "CSafeLoader only, never `yaml.Loader`" commitment.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Adversarial tests"` items 4, 7, 9 — the three tests this story lands.
  - `../phase-arch-design.md §"Edge cases"` row 6 — the in-system behavior the shim test asserts.
  - `../phase-arch-design.md §"Component design" #8` — parsers; `CSafeLoader` only, no `yaml.Loader`.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0001-add-node-to-allowed-binaries.md` — what `ALLOWED_BINARIES += "node"` permits, and what env-strip prevents.
  - `../ADRs/0003-yarn-lock-parser-choice.md` — the hand-rolled parser is the test's target when `_HAS_PYARN = False`; the test forces this path.
  - `../ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md` — `CSafeLoader` is the parser; `!!python/object` must raise `MalformedYAMLError`.
  - `../ADRs/0009-no-new-c-extension-parser-dependencies.md` — no new C-extension parser added to handle hostile YAML tags; refusal is the only option.
- **Source design:**
  - `../final-design.md §"Adversarial tests"` — items #4, #7, #9 with explicit "env-strip carries the load-bearing weight" framing.
  - `../High-level-impl.md §"Step 5"` adversarial-test list items 4, 7, 9.
- **Existing code (lands earlier — must be on disk before this story starts):**
  - `src/codegenie/probes/_lockfiles/_yarn.py` (S3-03).
  - `src/codegenie/exec.py` — `ALLOWED_BINARIES`, env-strip (Phase 0 + S1-10 extension).
  - `src/codegenie/parsers/safe_yaml.py` (S1-03) — `CSafeLoader` only.
  - `src/codegenie/errors.py` — `MalformedYAMLError`, `MalformedLockfileError` (S1-01).
- **Style reference:** `../../00-bullet-tracer-foundations/stories/S2-04-exec-allowlist.md` (sister story shape for exec-allowlist tests).

## Goal

Three adversarial tests under `tests/adv/` exist and pass: (a) the hand-rolled yarn parser completes a pathological `yarn.lock` in under 1 s with `_HAS_PYARN = False` forced; (b) a hostile `node` shim on `$PATH` runs but does not see any stripped env var via a sentinel-file mechanism; (c) a `pnpm-lock.yaml` containing `!!python/object` raises `MalformedYAMLError` and no Python object is constructed.

## Acceptance criteria

### Group 1 — Yarn-lock regex-DoS test (`tests/adv/test_regex_dos_yarn_lock.py`)

- [ ] **AC-1 (runtime budget on realistic worst case).** Test synthesizes a pathological `yarn.lock` body of approximately **5 MB** (well within the 50 MB cap but large enough that any introduced O(n²) per-byte work fails) by repeating multi-spec headers `"foo@^1.0.N", "foo@^2.0.N":\n  version "1.0.0"\n` — the only string-allocation surface in `_parse_handrolled` is `_dequote_entry_header`'s `split('", "')` call (`_yarn.py:110`), which a regex-backtracking regression would worst-case quadratically. Monkeypatches `codegenie.probes._lockfiles._yarn._HAS_PYARN` to `False` with `monkeypatch.setattr(..., raising=True)`; pre-asserts `hasattr(codegenie.probes._lockfiles._yarn, "_HAS_PYARN")` so a future rename surfaces loudly. Calls `codegenie.probes._lockfiles._yarn.parse(path)` (via `open_capped`); measures wall-clock via `time.monotonic()`; asserts elapsed `< 2.0` s.
- [ ] **AC-2 (no silent-empty mutation; shape contract).** When `parse(...)` returns successfully, the test asserts `isinstance(result, dict) and "entries" in result and len(result["entries"]) > 0` — rules out a regression that silently early-returns `{"entries": {}}` on any large input. The only acceptable alternative is `pytest.raises(MalformedLockfileError)`. The empty-return-on-non-empty-body path is **explicitly forbidden**.
- [ ] **AC-3 (structural assertion — no regex over the full body).** A separate test in the same file imports `codegenie.probes._lockfiles._yarn` and uses `inspect.getsource(_yarn)` plus an `ast.parse`-driven walker to assert: (a) no `import re` (or `from re import …`) at module level, and (b) no `re.match` / `re.search` / `re.findall` / `re.finditer` / `re.compile` call name appears in any function body of `_parse_handrolled` or any helper it calls. This pins the "line-by-line state machine; no regex over the full body" contract from `_yarn.py:116` and ADR-0003 §Decision (line 41 — "no regex over the full file"). The deterministic complement to AC-1's wall-clock budget.

### Group 2 — Planted `node` shim test (`tests/adv/test_planted_node_on_path_ignored.py`)

- [ ] **AC-4 (chokepoint, not probe, is under test).** The test invokes `codegenie.exec.run_allowlisted(["node", "--version"], cwd=tmp_path, timeout_s=5.0, env_extra={...})` directly (matching the spy pattern in `tests/adv/test_env_var_strip.py`). The test is `async def` and `await`s the call (mirrors the existing pytest-asyncio mode used by `test_env_var_strip.py:55`). Tests at the probe level (going through `NodeBuildSystemProbe`) are **explicitly out of scope** — the chokepoint is the load-bearing defense; the probe is one of N callers.
- [ ] **AC-5 (the shim actually ran — positive control).** Test writes an executable POSIX shim to `tmp_path / "fake-bin" / "node"` (`#!/bin/sh` + body that captures `$OPENAI_API_KEY`, `$ANTHROPIC_API_KEY`, `$GITHUB_TOKEN`, `$AWS_ACCESS_KEY_ID`, `$AWS_SECRET_ACCESS_KEY`, `$SSH_AUTH_SOCK`, `$MY_LEGIT_VAR` and writes them as `key=value\n` records to `$SENTINEL_FILE`, then writes `node-shim-invoked\n` as the last line, then `echo v20.0.0` on stdout). `os.chmod(shim, 0o755)`. The shim path is prepended to PATH **via `env_extra["PATH"]`**, not `monkeypatch.setenv` — same rationale as AC-6. After the call, the test asserts `sentinel.exists()` and `sentinel.read_text().splitlines()[-1] == "node-shim-invoked"` — proving the shim ran (test is not vacuously green).
- [ ] **AC-6 (env-by-inclusion surface — parent `os.environ` never copied).** `monkeypatch.setenv("OPENAI_API_KEY", "PARENT_LEAK_CANARY")` (and same for `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `SSH_AUTH_SOCK`) on the parent process. The shim's sentinel-file output is read; the test asserts **none** of the value `PARENT_LEAK_CANARY` appears in the sentinel for any of those keys (the shim records each as `KEY=` with an empty value, because the wrapper never copied them from `os.environ`). Catches a refactor that swaps the spawn primitive to one that ignores the explicit `env=` kwarg (e.g., drops `env=env` from `create_subprocess_exec`) — the shim would then inherit the parent env wholesale.
- [ ] **AC-7 (env_extra denylist surface — `_is_sensitive` is actually exercised).** The same call passes `env_extra` containing legitimate `MY_LEGIT_VAR="passes-through"` AND sensitive sentinels `OPENAI_API_KEY="EXTRA_LEAK_CANARY_OPENAI"`, `ANTHROPIC_API_KEY="EXTRA_LEAK_CANARY_ANTHROPIC"`, `AWS_SECRET_ACCESS_KEY="EXTRA_LEAK_CANARY_AWS"` (AWS prefix variant), `GITHUB_TOKEN="EXTRA_LEAK_CANARY_GH"`. Sentinel-file output is parsed line-by-line. Test asserts: `MY_LEGIT_VAR=passes-through` line is present (chokepoint did not over-filter), `EXTRA_LEAK_CANARY_*` does not appear anywhere in the sentinel (the `_is_sensitive` denylist in `exec.py:112-121` filtered each — exact + prefix paths). Catches a regression that deletes the `if _is_sensitive(key): continue` branch at `exec.py:143-148`.
- [ ] **AC-8 (structlog event observability — the real event name).** Test wraps the call in `structlog.testing.capture_logs()`. After the call, asserts exactly four `subproc.env_extra.sensitive_key_dropped` events (one per sensitive key in AC-7's `env_extra`), each with a `key=` field matching one of `{"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN"}`. **No** event named `exec.run_allowlisted.env_stripped` is expected (no such event exists — the parent-env-omission path is silent by design).
- [ ] **AC-9 (POSIX-only skip).** Test is decorated with `@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell required")` — pins the cross-platform invariant in code, not just in Notes. CI matrix is macOS + Linux per Phase 0 docs.

### Group 3 — Unsafe-YAML-tag test (`tests/adv/test_yaml_unsafe_tag.py`)

- [ ] **AC-10 (hostile tag rejected, hermetically).** Test writes `tmp_path / "pnpm-lock.yaml"` whose body is an f-string interpolating `tmp_path` into the hostile tag: `lockfileVersion: '6.0'\nadversarial: !!python/object/apply:os.system ["touch {tmp_path}/adv-canary.txt"]\n`. Calls `safe_yaml.load(path, max_bytes=1_000_000)` (the `max_bytes` kwarg is **mandatory** per `safe_yaml.py:80`). `pytest.raises(MalformedYAMLError) as exc_info`. Asserts `not (tmp_path / "adv-canary.txt").exists()` — no side-effect.
- [ ] **AC-11 (translation contract proven).** `exc_info.value.__cause__` is an instance of `yaml.YAMLError` (the parent class of `yaml.constructor.ConstructorError`). Proves the `_parse_one` translation path in `safe_yaml.py:142-145` ran — rules out a regression where the function raises `MalformedYAMLError` from a different layer (e.g., the size cap firing first) and silently passing.
- [ ] **AC-12 (positive control — `safe_yaml.load` still works on valid YAML).** The same test module includes a second test that writes a minimal valid `pnpm-lock.yaml` (`lockfileVersion: '6.0'\n`) to `tmp_path` and calls `safe_yaml.load(path, max_bytes=1_000_000)`, asserting the result is a non-empty mapping containing `lockfileVersion`. Catches a degenerate mutation where `safe_yaml.load` is replaced with `raise MalformedYAMLError("…")` unconditionally.

### Group 4 — Cross-cutting test hygiene

- [ ] **AC-13 (typed-exception + specific outcome, not exit-code 0).** Per `High-level-impl.md §"Step 5 — Risks"`: each test asserts the **specific** typed exception (yarn: `MalformedLockfileError` or successful return; shim: `ProcessResult.returncode == 0`; yaml: `MalformedYAMLError`) and a **specific** in-system outcome (yarn: entries shape; shim: sentinel-file contents pattern; yaml: no side-effect file). No test passes solely because "no exception was raised."
- [ ] **AC-14 (per-test state hygiene).** Each test uses `pytest`'s `monkeypatch` fixture for every state mutation. No raw `os.environ[...] = ...`, no raw `sys.path.insert`, no module-level mutation of `_HAS_PYARN`. The fixture's autorestore behaviour is the contract.
- [ ] **AC-15 (`adv` marker; depends on S5-01 owning registration).** All five tests in this story are decorated `@pytest.mark.adv`. The `adv` marker registration in `pyproject.toml [tool.pytest.ini_options].markers` is owned by S5-01 (per S5-01 §AC-5 hardened block). If this story merges before S5-01's marker registration, `--strict-markers` (already enabled at `pyproject.toml:178`) will fail loud — that's the correct surfacing, not something to work around.
- [ ] **AC-16 (walltime budget).** `pytest -m adv tests/adv/test_regex_dos_yarn_lock.py tests/adv/test_planted_node_on_path_ignored.py tests/adv/test_yaml_unsafe_tag.py` completes in **under 10 s p95** on the developer's machine and in CI. (Increased from the original 5 s — the yarn AC-1 needs ≤ 2 s headroom, the shim spawn needs ~300 ms p95 on macOS CI, the YAML test plus positive control is sub-100 ms — 10 s accommodates jitter without burning Step-5's 30 s overall budget.)

### Group 5 — Out-of-scope cross-references (not ACs; surfaced so the executor doesn't try to land them here)

- [ ] **OOS-1.** The "garbage output from `node --version`" path (per ADR-0001 §Consequences line 34 — `^v\d+\.\d+\.\d+` parsing failure → `node_version_resolved_locally: null`) is owned by `NodeBuildSystemProbe`'s unit tests (S2-02), not this story. The chokepoint test in this story has no visibility into the probe's parse-failure path.
- [ ] **OOS-2.** Property-based / metamorphic fuzz of `_parse_handrolled` is owned by `tools/fuzz_yarn_lock.py` (S3-03 local fuzz harness, per ADR-0003 line 81-82+94). This story's `test_regex_dos_yarn_lock.py` is the CI permanent fixture; the fuzz harness is the first-line defense (per `phase-arch-design.md §"Implementation-level risks"` #4).

## Implementation outline

1. **`tests/adv/test_regex_dos_yarn_lock.py`** (two tests; both marked `@pytest.mark.adv`):
   - *Test 1 (runtime budget, AC-1/AC-2).* Build a ~5 MB body by repeating multi-spec headers and a `version` line: `body = "".join(f'"foo@^1.0.{i}", "foo@^2.0.{i}":\n  version "1.0.0"\n' for i in range(N))` with `N` chosen so `len(body.encode()) ≈ 5_000_000`. Write to `tmp_path / "yarn.lock"`. Pre-assert `hasattr(codegenie.probes._lockfiles._yarn, "_HAS_PYARN")`. `monkeypatch.setattr("codegenie.probes._lockfiles._yarn._HAS_PYARN", False, raising=True)`. `t0 = time.monotonic(); try: result = _yarn.parse(path); except MalformedLockfileError: result = None; elapsed = time.monotonic() - t0`. Assert `elapsed < 2.0`. If `result is not None`: assert `isinstance(result, dict) and "entries" in result and len(result["entries"]) > 0`.
   - *Test 2 (structural — no regex, AC-3).* `import inspect, ast, codegenie.probes._lockfiles._yarn as m; src = inspect.getsource(m); tree = ast.parse(src)`. Walk the AST: assert no `Import`/`ImportFrom` node with name `"re"` at module scope; assert no `Attribute` node `re.match`/`re.search`/`re.findall`/`re.finditer`/`re.compile` in any descendant of `_parse_handrolled`'s function definition or any helper it calls (`_dequote_entry_header`). One canonical structural assertion message string in the failure: `"_yarn must remain a line-by-line state machine; no regex over the full body (ADR-0003)"`.
2. **`tests/adv/test_planted_node_on_path_ignored.py`** (one `async def` test, marked `@pytest.mark.adv` and `@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell required")`):
   - Write the shim to `tmp_path / "fake-bin" / "node"`:
     ```sh
     #!/bin/sh
     {
       printf 'OPENAI_API_KEY=%s\n' "${OPENAI_API_KEY:-}"
       printf 'ANTHROPIC_API_KEY=%s\n' "${ANTHROPIC_API_KEY:-}"
       printf 'GITHUB_TOKEN=%s\n' "${GITHUB_TOKEN:-}"
       printf 'AWS_ACCESS_KEY_ID=%s\n' "${AWS_ACCESS_KEY_ID:-}"
       printf 'AWS_SECRET_ACCESS_KEY=%s\n' "${AWS_SECRET_ACCESS_KEY:-}"
       printf 'SSH_AUTH_SOCK=%s\n' "${SSH_AUTH_SOCK:-}"
       printf 'MY_LEGIT_VAR=%s\n' "${MY_LEGIT_VAR:-}"
       printf 'node-shim-invoked\n'
     } > "$SENTINEL_FILE"
     echo v20.0.0
     ```
     `shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)`.
   - On the **parent process** (`monkeypatch.setenv`, AC-6): set `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`/`GITHUB_TOKEN`/`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`SSH_AUTH_SOCK` to `"PARENT_LEAK_CANARY"`. These are NEVER copied to the child (env-by-inclusion); the test pins that structural fact.
   - In **`env_extra`** (the only documented narrow passthrough to the child, AC-5/AC-7) pass:
     - `"PATH": f"{shim_dir}{os.pathsep}{os.environ['PATH']}"` — prepend the shim dir so the spawn resolves `node` to the shim. (PATH is not in the sensitive set; `_is_sensitive` allows it.)
     - `"SENTINEL_FILE": str(tmp_path / "sentinel.txt")` — out-of-band channel for the shim's output.
     - `"MY_LEGIT_VAR": "passes-through"` — positive control proving the chokepoint did not over-filter.
     - `"OPENAI_API_KEY": "EXTRA_LEAK_CANARY_OPENAI"`, `"ANTHROPIC_API_KEY": "EXTRA_LEAK_CANARY_ANTHROPIC"`, `"AWS_SECRET_ACCESS_KEY": "EXTRA_LEAK_CANARY_AWS"`, `"GITHUB_TOKEN": "EXTRA_LEAK_CANARY_GH"` — sensitive sentinels (exercises `_is_sensitive` exact + `AWS_` prefix paths).
   - Inside `structlog.testing.capture_logs() as logs`: `await codegenie.exec.run_allowlisted(["node", "--version"], cwd=tmp_path, timeout_s=5.0, env_extra=…)`. (Mirrors `tests/adv/test_env_var_strip.py:55-85`.)
   - Parse the sentinel file as `dict(line.split("=", 1) for line in sentinel.read_text().splitlines() if "=" in line)` plus the trailing `node-shim-invoked` marker line. Assert:
     - `sentinel.read_text().splitlines()[-1] == "node-shim-invoked"` (AC-5).
     - For each parent-env-canary key in AC-6: parsed value is `""` (not `"PARENT_LEAK_CANARY"`). The grep also asserts `"PARENT_LEAK_CANARY" not in sentinel.read_text()`.
     - For each `EXTRA_LEAK_CANARY_*` value (AC-7): not present in the sentinel text.
     - `parsed["MY_LEGIT_VAR"] == "passes-through"` (AC-7 positive control).
   - From `logs` (AC-8): `drops = [e for e in logs if e["event"] == "subproc.env_extra.sensitive_key_dropped"]`. Assert `len(drops) == 4` and `{e["key"] for e in drops} == {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN"}`. (`PATH`, `SENTINEL_FILE`, `MY_LEGIT_VAR` are not sensitive — no event.)
3. **`tests/adv/test_yaml_unsafe_tag.py`** (two tests, both marked `@pytest.mark.adv`):
   - *Test 1 (hostile tag, AC-10/AC-11).* Build YAML body via f-string interpolating `tmp_path` to keep the side-effect hermetic:
     ```python
     UNSAFE_YAML = (
         "lockfileVersion: '6.0'\n"
         f'adversarial: !!python/object/apply:os.system ["touch {tmp_path / "adv-canary.txt"}"]\n'
     )
     ```
     Write to `tmp_path / "pnpm-lock.yaml"`. `with pytest.raises(MalformedYAMLError) as exc_info: safe_yaml.load(path, max_bytes=1_000_000)`. Assert `isinstance(exc_info.value.__cause__, yaml.YAMLError)`. Assert `not (tmp_path / "adv-canary.txt").exists()`.
   - *Test 2 (positive control, AC-12).* Write `lockfileVersion: '6.0'\n` to `tmp_path / "pnpm-lock-valid.yaml"`. Call `result = safe_yaml.load(path, max_bytes=1_000_000)`. Assert `isinstance(result, dict)` and `result.get("lockfileVersion") == "6.0"`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Start with the unsafe-tag test (cheapest, no subprocess); then the yarn regex-DoS; then the planted-shim test (slowest setup, exercises the chokepoint).

```python
# tests/adv/test_yaml_unsafe_tag.py
from pathlib import Path

import pytest
import yaml

from codegenie.errors import MalformedYAMLError
from codegenie.parsers import safe_yaml


@pytest.mark.adv
def test_unsafe_python_object_tag_refused(tmp_path: Path) -> None:
    """Pins: ``!!python/object/apply:os.system`` cannot construct anything via
    ``safe_yaml.load`` — the CSafeLoader chokepoint refuses; no side-effect.
    Catches: a regression that switches to ``yaml.Loader`` / ``yaml.SafeLoader``
             (the C-only constraint), or one that catches the ConstructorError
             too late, after a side-effect would have fired.
    """
    canary = tmp_path / "adv-canary.txt"
    body = (
        "lockfileVersion: '6.0'\n"
        f'adversarial: !!python/object/apply:os.system ["touch {canary}"]\n'
    )
    target = tmp_path / "pnpm-lock.yaml"
    target.write_text(body)

    with pytest.raises(MalformedYAMLError) as exc_info:
        safe_yaml.load(target, max_bytes=1_000_000)

    assert isinstance(exc_info.value.__cause__, yaml.YAMLError), (
        f"translation contract broken: __cause__={type(exc_info.value.__cause__).__name__}"
    )
    assert not canary.exists(), "os.system fired — CSafeLoader chokepoint failed"


@pytest.mark.adv
def test_safe_yaml_positive_control_loads_minimal_lockfile(tmp_path: Path) -> None:
    """Positive control — guards against a degenerate ``safe_yaml.load``
    replacement that always raises ``MalformedYAMLError`` (which would
    trivially-pass the negative test above)."""
    target = tmp_path / "pnpm-lock-valid.yaml"
    target.write_text("lockfileVersion: '6.0'\n")
    result = safe_yaml.load(target, max_bytes=1_000_000)
    assert isinstance(result, dict)
    assert result.get("lockfileVersion") == "6.0"
```

If S1-03 wired `CSafeLoader` correctly, the negative test passes immediately. The red moment is the structural commitment: this test must exist as a permanent fixture. If a future contributor switches to `yaml.Loader`, the test goes red because `ConstructorError` no longer fires and the canary file appears.

```python
# tests/adv/test_regex_dos_yarn_lock.py
import ast
import inspect
import time
from pathlib import Path

import pytest

import codegenie.probes._lockfiles._yarn as _yarn
from codegenie.errors import MalformedLockfileError


def _pathological_yarn_lock(approx_bytes: int = 5_000_000) -> bytes:
    """Functional-core fixture builder. Returns a well-formed but large
    yarn.lock body that exercises ``_dequote_entry_header``'s comma-split
    path — the only string-allocation surface in the hand-rolled scanner.
    A regression introducing O(n²) backtracking on a multi-spec header
    would worst-case this body quadratically; the linear state machine
    handles it in O(bytes).
    """
    block = '"foo@^1.0.{i}", "foo@^2.0.{i}":\n  version "1.0.0"\n'
    one_size = len(block.format(i=0).encode())
    n = approx_bytes // one_size + 1
    parts = (block.format(i=i) for i in range(n))
    return "".join(parts).encode("utf-8")


@pytest.mark.adv
def test_yarn_pathological_input_under_runtime_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pins: AC-1 + AC-2 — ~5 MB pathological lockfile parses in < 2 s on the
    hand-rolled path; result is non-empty OR ``MalformedLockfileError``.
    Catches: a hand-rolled-scanner regression that introduces a regex with
             backtracking, or one that early-returns ``{"entries": {}}`` on
             any large input.
    """
    assert hasattr(_yarn, "_HAS_PYARN"), (
        "_HAS_PYARN attribute was renamed — monkeypatch below is now a no-op; "
        "update this test to the new attribute name (or surface the rename)."
    )
    monkeypatch.setattr(
        "codegenie.probes._lockfiles._yarn._HAS_PYARN", False, raising=True
    )
    path = tmp_path / "yarn.lock"
    path.write_bytes(_pathological_yarn_lock(approx_bytes=5_000_000))

    t0 = time.monotonic()
    try:
        result: dict | None = _yarn.parse(path)
    except MalformedLockfileError:
        result = None
    elapsed = time.monotonic() - t0

    assert elapsed < 2.0, (
        f"hand-rolled scanner took {elapsed:.2f}s on ~5 MB body — "
        f"suggests O(n²) work or a regex with backtracking (ADR-0003 §Decision)"
    )
    if result is not None:
        assert isinstance(result, dict), result
        assert "entries" in result, result
        assert len(result["entries"]) > 0, (
            "scanner returned {'entries': {}} on a non-empty body — "
            "this is the explicit-forbidden silent-empty mutation (AC-2)"
        )


@pytest.mark.adv
def test_yarn_handrolled_scanner_uses_no_regex() -> None:
    """Pins: AC-3 — _yarn module imports no `re`, and ``_parse_handrolled`` /
    ``_dequote_entry_header`` invoke no regex functions. The deterministic
    complement to the wall-clock budget — catches a regex backtracking regression
    structurally (CLAUDE.md "Determinism over probabilism")."""
    src = inspect.getsource(_yarn)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "re", (
                    "_yarn must remain a line-by-line state machine; "
                    "no regex over the full body (ADR-0003)"
                )
        elif isinstance(node, ast.ImportFrom):
            assert node.module != "re", (
                "_yarn must remain a line-by-line state machine; "
                "no regex over the full body (ADR-0003)"
            )
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            assert not (
                node.value.id == "re"
                and node.attr in {"match", "search", "findall", "finditer", "compile", "sub", "split"}
            ), (
                f"_yarn references re.{node.attr} — forbidden by ADR-0003 (state-machine only)"
            )
```

This test gates `High-level-impl.md §"Implementation-level risks"` #4. If S3-03 used regex with backtracking against the full file (forbidden), the runtime test goes red; the structural test catches even the case where the regex happens to be linear-time on the test fixture.

```python
# tests/adv/test_planted_node_on_path_ignored.py
import os
import stat
import sys
from pathlib import Path

import pytest
from structlog.testing import capture_logs

from codegenie import exec as cg_exec

SHIM_BODY = """#!/bin/sh
{
  printf 'OPENAI_API_KEY=%s\\n' "${OPENAI_API_KEY:-}"
  printf 'ANTHROPIC_API_KEY=%s\\n' "${ANTHROPIC_API_KEY:-}"
  printf 'GITHUB_TOKEN=%s\\n' "${GITHUB_TOKEN:-}"
  printf 'AWS_ACCESS_KEY_ID=%s\\n' "${AWS_ACCESS_KEY_ID:-}"
  printf 'AWS_SECRET_ACCESS_KEY=%s\\n' "${AWS_SECRET_ACCESS_KEY:-}"
  printf 'SSH_AUTH_SOCK=%s\\n' "${SSH_AUTH_SOCK:-}"
  printf 'MY_LEGIT_VAR=%s\\n' "${MY_LEGIT_VAR:-}"
  printf 'node-shim-invoked\\n'
} > "$SENTINEL_FILE"
echo v20.0.0
"""

_PARENT_LEAK_CANARY = "PARENT_LEAK_CANARY"
_EXTRA_CANARY_PREFIX = "EXTRA_LEAK_CANARY_"


@pytest.mark.adv
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell required")
async def test_planted_node_shim_runs_in_stripped_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pins: AC-4 through AC-8.
    Catches:
      - a refactor swapping the spawn primitive to one that ignores ``env=``
        (parent ``os.environ`` would leak); the parent-canary assertion fails.
      - a regression deleting ``_is_sensitive``; ``EXTRA_LEAK_CANARY_*`` would
        appear in the shim sentinel for the four sensitive keys.
      - a regression deleting the structlog ``sensitive_key_dropped`` event;
        the four-events assertion fails.
      - a regression over-filtering ``env_extra`` (e.g. dropping unknown keys);
        ``MY_LEGIT_VAR=passes-through`` would be empty in the sentinel.
    """
    shim_dir = tmp_path / "fake-bin"
    shim_dir.mkdir()
    shim = shim_dir / "node"
    shim.write_text(SHIM_BODY)
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    sentinel = tmp_path / "sentinel.txt"

    # Parent-env canaries (AC-6) — never copied to child by design.
    for key in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GITHUB_TOKEN",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "SSH_AUTH_SOCK",
    ):
        monkeypatch.setenv(key, _PARENT_LEAK_CANARY)

    env_extra = {
        # PATH override + sentinel out-of-band channel (AC-5) — non-sensitive.
        "PATH": f"{shim_dir}{os.pathsep}{os.environ['PATH']}",
        "SENTINEL_FILE": str(sentinel),
        "MY_LEGIT_VAR": "passes-through",
        # Sensitive sentinels (AC-7) — must be dropped by ``_is_sensitive``.
        "OPENAI_API_KEY": f"{_EXTRA_CANARY_PREFIX}OPENAI",
        "ANTHROPIC_API_KEY": f"{_EXTRA_CANARY_PREFIX}ANTHROPIC",
        "AWS_SECRET_ACCESS_KEY": f"{_EXTRA_CANARY_PREFIX}AWS",  # tests AWS_ prefix path
        "GITHUB_TOKEN": f"{_EXTRA_CANARY_PREFIX}GH",
    }

    with capture_logs() as logs:
        result = await cg_exec.run_allowlisted(
            ["node", "--version"],
            cwd=tmp_path,
            timeout_s=5.0,
            env_extra=env_extra,
        )

    # The shim must have actually run (AC-5).
    body = sentinel.read_text()
    lines = body.splitlines()
    assert lines and lines[-1] == "node-shim-invoked", (
        f"shim did not write the trailing marker — sentinel body was {body!r}"
    )
    parsed: dict[str, str] = dict(
        line.split("=", 1) for line in lines if "=" in line
    )

    # AC-6 — parent ``os.environ`` was never copied; each sensitive var is empty.
    for key in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GITHUB_TOKEN",
        "AWS_ACCESS_KEY_ID",
        "SSH_AUTH_SOCK",
    ):
        assert parsed.get(key, "<missing>") != _PARENT_LEAK_CANARY, (
            f"parent-env leak: {key} reached child as {parsed[key]!r}"
        )
    assert _PARENT_LEAK_CANARY not in body, (
        f"PARENT_LEAK_CANARY appears somewhere in shim output: {body!r}"
    )

    # AC-7 — ``_is_sensitive`` filtered the env_extra sensitives.
    assert _EXTRA_CANARY_PREFIX not in body, (
        f"sensitive env_extra reached the child: {body!r}"
    )
    # Positive control — legitimate env_extra var DID pass through.
    assert parsed.get("MY_LEGIT_VAR") == "passes-through", (
        f"MY_LEGIT_VAR was dropped; chokepoint over-filtered: {parsed!r}"
    )

    # AC-8 — structlog event observability for the denylist path.
    drops = [e for e in logs if e.get("event") == "subproc.env_extra.sensitive_key_dropped"]
    assert len(drops) == 4, (
        f"expected exactly 4 sensitive_key_dropped events; got {len(drops)}: {drops!r}"
    )
    assert {e["key"] for e in drops} == {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "GITHUB_TOKEN",
    }, drops

    # Sanity — the shim returned 0 and stdout looked like a version.
    assert result.returncode == 0, result
    assert result.stdout.strip() == b"v20.0.0"
```

Run all reds (the structural-no-regex test passes on green code from day one — that's intended; its job is to fail on regression, not to drive new code); commit; then green.

### Green — make it pass

The three components (yarn parser, exec chokepoint, `CSafeLoader`) all exist after Steps 1 and 3. If any test goes red **for the wrong reason** — e.g. the yarn test fails because `_HAS_PYARN` no longer exists as a module attribute, or `safe_yaml.load`'s signature changed — that's a Step-1/Step-3 contract drift; surface it in this PR with an explicit follow-up reference rather than silently working around it.

`SENTINEL_FILE` only reaches the child through `env_extra` — this is the documented narrow passthrough in `exec.py:124-150` and the chokepoint behavior that makes the test meaningful. Do **not** try to make `monkeypatch.setenv("SENTINEL_FILE", …)` work — that would require changing `_filter_env` to copy parent `os.environ`, which is precisely the regression this test is designed to catch.

### Refactor — clean up

After green:

- Confirm `SHIM_BODY`'s POSIX-shell portability on Linux + macOS — `${VAR:-}` and `printf '%s\n'` are POSIX (work in `sh`, `bash`, `dash`).
- Verify `monkeypatch` cleans `os.environ` after exiting (the fixture does this automatically; spot-check that no second test in the file inherits a polluted env).
- `mypy --strict`-clean type hints on `_pathological_yarn_lock` and any module-level helpers.
- **Do NOT** lift `SHIM_BODY` / `UNSAFE_YAML` / `_pathological_yarn_lock` into `tests/adv/_helpers.py`. The rule-of-three threshold is not met (S5-03 needs none of them); module-level inlines are correct per Rule 2. If a Phase-2 story introduces a second consumer of any of these, lift then.

## Files to touch

| Path | Why |
|---|---|
| `tests/adv/test_regex_dos_yarn_lock.py` | New test file — hand-rolled yarn parser must not regex-DoS |
| `tests/adv/test_planted_node_on_path_ignored.py` | New test file — env-strip prevents secret leak to hostile shim |
| `tests/adv/test_yaml_unsafe_tag.py` | New test file — `CSafeLoader` refuses `!!python/object` |

## Out of scope

- **Cap-family adversarial tests (yaml billion-laughs, JSON bombs, oversized lockfile)** — owned by S5-01.
- **Symlink-escape / zip-slip / pathological `tsconfig` adversarial tests** — owned by S5-03.
- **Refining the hand-rolled yarn parser to handle pathological input gracefully** — if the parser raises `MalformedLockfileError` under 1 s, that's acceptable. Improvements to the parser belong in a separate S3-03 follow-up.
- **Sandbox/seccomp/bwrap-style isolation for `node --version`** — explicitly refused per ADR-0008. The env-strip is the load-bearing defense.
- **`node` binary signature verification / PATH integrity checks** — Phase 14 deployment-layer concern.

## Notes for the implementer

- **The shim test is not asserting `node` cannot be hijacked.** It is asserting that *if* `node` is hijacked, *no secret leaks*. This is the wording in `final-design.md §"Adversarial tests"` item #7 verbatim — read that paragraph before writing the test. Do not accidentally assert the hijack is prevented (it isn't, and that's by design per ADR-0001 + ADR-0008).
- **The env model is INCLUSION, not deletion.** `exec.py:14-18` and `_filter_env` (lines 124-150) build the child env from a 4-key safe baseline `{PATH, HOME, LANG, LC_ALL}` plus sanitized `env_extra`. The parent `os.environ` is **never copied**. Calling the chokepoint with no `env_extra` produces a child with only those four keys. Sensitive vars in the parent are structurally absent (the AC-6 surface); sensitive vars in `env_extra` are filtered by `_is_sensitive` (the AC-7 surface). These are two distinct surfaces; the hardened test exercises both.
- **`SENTINEL_FILE` is the test's own out-of-band channel and must be passed through `env_extra` — NOT through `monkeypatch.setenv`.** The 4-key baseline does not include `SENTINEL_FILE`; if you set it on the parent process, it is structurally invisible to the child and the shim's redirect writes to nowhere usable. The original story tried `monkeypatch.setenv("SENTINEL_FILE", …)` and was structurally broken; the hardened test uses `env_extra={"SENTINEL_FILE": …, "PATH": …}`. The same is true for the shim-dir PATH override.
- **Test at the chokepoint, not the probe.** The test invokes `exec.run_allowlisted` directly rather than going through `NodeBuildSystemProbe`. The chokepoint is the load-bearing defense per ADR-0001 + ADR-0008; the probe is one of N future callers. Do not refactor this test to go through a probe — that would couple the security invariant to an incidental caller and weaken mutation-resistance. (Mirrors `tests/adv/test_env_var_strip.py`'s spy-at-the-chokepoint pattern, S4-05.)
- **Use `monkeypatch.setattr`, not module-level mutation.** The `_HAS_PYARN` patch is the canonical example. Mutation via `_yarn._HAS_PYARN = False` without `monkeypatch` leaks across tests and produces ghost failures in parallel CI runs. Use `raising=True` plus a `hasattr(...)` pre-assert so a future rename surfaces loudly rather than silently no-op'ing.
- **`_HAS_PYARN` redundant on CI, load-bearing locally.** Per ADR-0003 §"Implementer's land-time selection" (chose hand-rolled, 2026-05-14), `pyarn` is NOT in `pyproject.toml`'s `gather` extras, so `_HAS_PYARN` is `False` on CI by default. The monkeypatch is no-op on CI but load-bearing on a contributor's machine that has `pip install pyarn` for S3-04 parity-test work. Keep it regardless — defense in depth.
- **The `MalformedYAMLError` raised by `safe_yaml` on an unsafe tag is the structural defense.** The translation contract is fixed by `safe_yaml.py:140-162`: `yaml.YAMLError` (parent class of `yaml.constructor.ConstructorError`) → `MalformedYAMLError` with the original on `__cause__`. AC-11 pins the `__cause__` invariant so a regression where another layer raises `MalformedYAMLError` (e.g., the size cap firing first) is caught.
- **`safe_yaml.load` signature is `(path, *, max_bytes: int, max_depth: int = 64)`.** `max_bytes` is mandatory (`safe_yaml.py:80`). The original story called `safe_yaml.load(f)` and would have raised `TypeError` before `CSafeLoader` was the surface under test. Always pass `max_bytes` explicitly — `1_000_000` (1 MB) is fine for the test fixtures.
- **The structlog event names are `subproc.spawn`, `subproc.exit`, `subproc.timeout`, `subproc.env_extra.sensitive_key_dropped`.** There is no event called `exec.run_allowlisted.env_stripped` and no event for the parent-env-inclusion path (env-by-omission is silent by design — there is nothing to drop). The hardened AC-8 binds to the real `subproc.env_extra.sensitive_key_dropped` event.
- **Pathological yarn-lock fixture is parametrized by size.** `_pathological_yarn_lock(approx_bytes=5_000_000)` returns bytes. Keep at ~5 MB for CI; bumping toward the 50 MB cap is fine for local stress but the 50 MB upper bound is exercised separately by S5-01's `test_oversized_lockfile.py`. The fuzz harness `tools/fuzz_yarn_lock.py` (S3-03) is the local-first-defense; this story is the CI gate.
- **Yarn structural assertion (AC-3) is the deterministic complement to the wall-clock budget.** The 2 s wall-clock assertion can flake under CI load; the AST scan ("no `import re`; no `re.<func>` call in `_parse_handrolled` or helpers") catches a regex-backtracking regression structurally even if the introduced regex happens to be linear-time on the test input. Both assertions live in the same file; both are required (per CLAUDE.md "Determinism over probabilism").
- **`adv` marker registration is owned by S5-01**, not this story. If this story merges first, `--strict-markers` (enabled at `pyproject.toml:178`) will fail loud — that's the correct surfacing. Do **not** "fix" by editing `pyproject.toml` here; doing so would step on S5-01's scope (Rule 3 — surgical changes).
- **Cross-platform: shim test requires POSIX shell.** `pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell required")` is now an AC (AC-9), not just a Note. CI matrix is macOS + Linux only (Phase 0 docs).
- **Garbage-output regression for `^v\d+\.\d+\.\d+`** (ADR-0001 §Consequences line 34) is owned by `NodeBuildSystemProbe`'s unit tests (S2-02), not this story. The chokepoint test in this file has no visibility into the probe's parse-failure path. See OOS-1 in the AC list.
- **Helper extraction (rule of three).** The shim factory, hostile YAML body, and pathological yarn-lock builder each have exactly one consumer in Phase 1 (just this story). Per Rule 2 they stay as module-level constants/single-use functions; do NOT pre-emptively extract to `tests/adv/_helpers.py`. If a Phase-2 story adds a second consumer of any of them, lift then.
