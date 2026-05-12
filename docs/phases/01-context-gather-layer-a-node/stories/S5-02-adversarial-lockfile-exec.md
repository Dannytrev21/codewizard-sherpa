# Story S5-02 — Lockfile + exec adversarial corpus: yarn regex-DoS, planted `node` shim, unsafe YAML tag

**Step:** Step 5 — Adversarial corpus + integration end-to-end + fixture portfolio
**Status:** Ready
**Effort:** M
**Depends on:** S3-04
**ADRs honored:** ADR-0001 (`node` in `ALLOWED_BINARIES`), ADR-0003 (`pyarn` vs hand-rolled yarn-lock parser), ADR-0008 (in-process parse caps), ADR-0009 (no new C-extension parser dependencies)

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

- [ ] `tests/adv/test_regex_dos_yarn_lock.py` synthesizes a pathological `yarn.lock` (mutation of a real `yarn.lock`: long string of `"` interleaved with `,`; deeply nested dependency blocks; `version: "x"` repeated 10,000 times; chosen to exercise the hand-rolled scanner's worst-case path); monkeypatches `codegenie.probes._lockfiles._yarn._HAS_PYARN = False`; calls `_yarn.parse(...)` inside `signal.alarm(2)` or a `concurrent.futures.ThreadPoolExecutor` with `.result(timeout=1.0)`; asserts the call returns or raises `MalformedLockfileError` in under 1 s — never times out.
- [ ] `tests/adv/test_planted_node_on_path_ignored.py` writes a hostile `node` shim shell script to `tmp_path / "fake-bin" / "node"` (`#!/bin/sh` + `echo "$OPENAI_API_KEY $ANTHROPIC_API_KEY $GITHUB_TOKEN $AWS_ACCESS_KEY_ID $SSH_AUTH_SOCK" > "$SENTINEL_FILE"`); prepends the dir to `$PATH`; sets the listed env vars to known sentinel values (e.g. `"DO_NOT_LEAK_OPENAI_KEY"`); invokes `exec.run_allowlisted(["node", "--version"], ...)`; reads the sentinel file; asserts **none** of the sentinel values appears (the shim ran, wrote a sentinel, but each env var was empty).
- [ ] `tests/adv/test_planted_node_on_path_ignored.py` additionally asserts that the shim was actually invoked (sentinel file exists after the call) — proves the test is meaningful (not "test passes because shim never ran").
- [ ] `tests/adv/test_yaml_unsafe_tag.py` writes a `pnpm-lock.yaml` whose body contains `!!python/object:builtins.print [args]` or similar instantiation tag; calls `safe_yaml.load(...)`; asserts `MalformedYAMLError` is raised (or whatever the parser raises for a forbidden tag — confirm at land-time against the S1-03 implementation); asserts no side-effect — e.g. a sentinel file the YAML would create is not present after the call.
- [ ] Each test installs / restores its own state (monkeypatched `_HAS_PYARN`; restored `$PATH`; restored env vars; no `tmp_path` leakage). The `monkeypatch` fixture is the canonical mechanism.
- [ ] Each test asserts the specific typed exception or specific in-system outcome, not just exit code 0 (per `High-level-impl.md §"Step 5 — Risks"`).
- [ ] All three tests are marked with `pytest.mark.adv` and `pytest -m adv tests/adv/test_regex_dos_yarn_lock.py tests/adv/test_planted_node_on_path_ignored.py tests/adv/test_yaml_unsafe_tag.py` completes in under 5 s on the developer's machine.
- [ ] At least one test (the shim test is the natural fit) asserts the env-strip is observable via the structlog event Phase 0 emits when `run_allowlisted` strips env (`exec.run_allowlisted.env_stripped` or whichever event constant Phase 0 registered — verify at land-time).

## Implementation outline

1. **`tests/adv/test_regex_dos_yarn_lock.py`:**
   - Construct a `yarn.lock` mutation in `tmp_path` designed to exercise the hand-rolled scanner's pathological branches. Pull a real `yarn.lock` from `tests/fixtures/node_yarn_legacy/` (S3-06) as a baseline; mutate by inserting 10,000 escaped-quote pairs, deeply nested block indentation, repeated `version:` keys, and a malformed trailing block.
   - `monkeypatch.setattr("codegenie.probes._lockfiles._yarn._HAS_PYARN", False)` — forces hand-rolled path.
   - Time the call: `t0 = time.monotonic(); ... ; assert time.monotonic() - t0 < 1.0`. Alternatively use `pytest-timeout` with `@pytest.mark.timeout(1.0)` (verify the project already depends on `pytest-timeout`; if not, use the manual timing pattern).
   - The call either returns a `YarnLock` TypedDict (lossy but bounded) or raises `MalformedLockfileError`. Both are acceptable outcomes — the test asserts non-timeout.
2. **`tests/adv/test_planted_node_on_path_ignored.py`:**
   - Define a "shim factory" inline (no shared helper for this single-use thing): write a `#!/bin/sh` script that captures `$OPENAI_API_KEY`, `$ANTHROPIC_API_KEY`, `$GITHUB_TOKEN`, `$AWS_ACCESS_KEY_ID`, `$AWS_SECRET_ACCESS_KEY`, `$SSH_AUTH_SOCK` and writes them comma-separated to `$SENTINEL_FILE`; also writes `node-shim-invoked` so we know the shim ran.
   - `os.chmod(shim_path, 0o755)`.
   - `monkeypatch.setenv("PATH", str(shim_dir) + os.pathsep + os.environ["PATH"])`.
   - For each sensitive var: `monkeypatch.setenv("OPENAI_API_KEY", "DO_NOT_LEAK_OPENAI_KEY")` (etc.).
   - `monkeypatch.setenv("SENTINEL_FILE", str(tmp_path / "sentinel.txt"))`.
   - Invoke `exec.run_allowlisted(["node", "--version"], timeout=5)`.
   - Read the sentinel file; assert `"node-shim-invoked"` is present (proves the shim ran); assert none of the `DO_NOT_LEAK_*` sentinel strings appears in the file (proves env-strip).
3. **`tests/adv/test_yaml_unsafe_tag.py`:**
   - Write `pnpm-lock.yaml` body:
     ```yaml
     lockfileVersion: '6.0'
     adversarial: !!python/object/apply:os.system ["touch /tmp/codegenie-adv-canary"]
     ```
   - `tmp_path / "adv-canary.txt"` is the sentinel path the YAML would try to touch (use a path under `tmp_path`, not `/tmp`, to keep the test hermetic — adjust the YAML body accordingly).
   - `pytest.raises(MalformedYAMLError)` on `safe_yaml.load(...)`.
   - `assert not (tmp_path / "adv-canary.txt").exists()` — no side-effect.

## TDD plan — red / green / refactor

### Red — write the failing test first

Start with the unsafe-tag test (cheapest, no subprocess); then the yarn regex-DoS; then the planted-shim test (slowest setup).

```python
# tests/adv/test_yaml_unsafe_tag.py
from pathlib import Path

import pytest

from codegenie.errors import MalformedYAMLError
from codegenie.parsers import safe_yaml

UNSAFE_YAML = """\
lockfileVersion: '6.0'
adversarial: !!python/object/apply:os.system ["echo adv_canary"]
"""


def test_unsafe_python_object_tag_refused(tmp_path):
    f = tmp_path / "pnpm-lock.yaml"
    f.write_text(UNSAFE_YAML)
    with pytest.raises(MalformedYAMLError):
        safe_yaml.load(f)
```

If S1-03 wired `CSafeLoader` correctly, this should pass immediately. The red moment is the structural commitment: this test must exist as a permanent fixture. If a future contributor switches to `yaml.Loader`, the test goes red.

```python
# tests/adv/test_regex_dos_yarn_lock.py
import time
from pathlib import Path

import pytest

from codegenie.errors import MalformedLockfileError
from codegenie.probes._lockfiles import _yarn

PATHOLOGICAL = (
    '# yarn lockfile v1\n'
    + 'pkg@^1.0.0:\n  version "1.0.0"\n'
    + ('  dependencies:\n' + '    a "' + '\\"' * 10000 + '"\n') * 50
)


def test_yarn_lock_pathological_input_completes_under_one_second(tmp_path, monkeypatch):
    monkeypatch.setattr("codegenie.probes._lockfiles._yarn._HAS_PYARN", False)
    f = tmp_path / "yarn.lock"
    f.write_text(PATHOLOGICAL)
    t0 = time.monotonic()
    try:
        _yarn.parse(f)
    except MalformedLockfileError:
        pass
    elapsed = time.monotonic() - t0
    assert elapsed < 1.0, f"hand-rolled scanner took {elapsed:.2f}s on pathological input"
```

This test gates `High-level-impl.md §"Implementation-level risks"` #4. If S3-03 used regex with backtracking against the full file (forbidden), this test fails — that's the design-correcting red signal.

```python
# tests/adv/test_planted_node_on_path_ignored.py
import os
import stat
from pathlib import Path

from codegenie import exec as exec_mod


SHIM = """#!/bin/sh
echo "${OPENAI_API_KEY:-}|${ANTHROPIC_API_KEY:-}|${GITHUB_TOKEN:-}|${AWS_ACCESS_KEY_ID:-}|${SSH_AUTH_SOCK:-}" > "$SENTINEL_FILE"
echo "node-shim-invoked" >> "$SENTINEL_FILE"
echo "v20.0.0"
"""


def test_planted_node_shim_runs_in_stripped_env(tmp_path, monkeypatch):
    shim_dir = tmp_path / "fake-bin"
    shim_dir.mkdir()
    shim = shim_dir / "node"
    shim.write_text(SHIM)
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    sentinel = tmp_path / "sentinel.txt"
    monkeypatch.setenv("PATH", str(shim_dir) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("SENTINEL_FILE", str(sentinel))
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GITHUB_TOKEN",
             "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "SSH_AUTH_SOCK"):
        monkeypatch.setenv(k, f"DO_NOT_LEAK_{k}")

    exec_mod.run_allowlisted(["node", "--version"], timeout=5)

    body = sentinel.read_text()
    assert "node-shim-invoked" in body, "shim never ran — test is not exercising the surface"
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GITHUB_TOKEN",
             "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "SSH_AUTH_SOCK"):
        assert f"DO_NOT_LEAK_{k}" not in body, f"{k} leaked to subprocess: {body}"
```

Run all three reds; commit; then green.

### Green — make it pass

The three components (yarn parser, exec env-strip, `CSafeLoader`) all exist after Steps 1 and 3. If any test goes red **for the wrong reason** — e.g. the yarn test fails because `_HAS_PYARN` doesn't exist as a module attribute — that's a Step-3 gap; surface it in this PR with an explicit follow-up reference.

If `SENTINEL_FILE` survives env-strip (because Phase 0's env-strip only strips a known-bad list, not unknown vars), that's intended behavior — `SENTINEL_FILE` is the test's own out-of-band channel. The env-strip's job is to block the listed secrets, not arbitrary user-set vars. Confirm by reading Phase 0's env-strip implementation in `exec.py` at land-time.

### Refactor — clean up

After green:

- Convert the `PATHOLOGICAL` constant into a function that returns mutated bytes given a base `yarn.lock`, to make the mutation strategy explicit (helps Phase 2 contributors understand what was tested).
- Confirm `SHIM`'s POSIX-shell portability on Linux + macOS — `${VAR:-}` syntax is POSIX (works in `sh`, `bash`, `dash`).
- Verify the test cleans `$PATH` after exiting (the `monkeypatch` fixture does this automatically; spot-check that no second test inherits a polluted `$PATH`).
- Add `mypy --strict`-clean type hints to the helper functions.

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

- **The shim test is not asserting `node` cannot be hijacked.** It is asserting that *if* `node` is hijacked, *no secret leaks*. This is the wording in `final-design.md §"Adversarial tests"` item #7 verbatim — read that paragraph before writing the test. Don't accidentally assert the hijack is prevented (it isn't, and that's by design per ADR-0001 + ADR-0008).
- **`SENTINEL_FILE` is the test's own out-of-band channel, not a secret being smuggled.** It survives env-strip because it's not in Phase 0's strip-list. If the env-strip is rewritten to use an allowlist (vs. denylist), `SENTINEL_FILE` must be added to the test's `monkeypatch.setenv` and verify the shim still has it; otherwise the test goes silently green (shim runs but writes nothing visible). Check Phase 0's strip mechanism before merging.
- **Use `monkeypatch.setattr`, not module-level mutation.** The `_HAS_PYARN` patch is the canonical example. Mutation via `_yarn._HAS_PYARN = False` without `monkeypatch` leaks across tests and produces ghost failures in parallel CI runs.
- **The `MalformedYAMLError` raised by `safe_yaml` on an unsafe tag is the structural defense.** If S1-03 maps PyYAML's `ConstructorError` to `MalformedJSONError` instead of `MalformedYAMLError`, fix S1-03's exception mapping before merging this story; this test is the canary. Surface the fix in the PR body.
- **Cross-platform note:** the shim test requires a POSIX shell. CI matrix is macOS + Linux only (Phase 0 docs). Add `pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell required")` to be safe even though Windows isn't in scope.
- **The structlog `exec.run_allowlisted.env_stripped` event** is a Phase 0 deliverable; if it doesn't exist by name, capture whatever Phase 0 emits when env is stripped — the structlog capture fixture is the same one S5-01 uses.
- **Pathological yarn-lock corpus reuse:** if you generate especially nasty mutations during local fuzzing, save the worst three under `tests/adv/data/yarn_lock_pathological/` (small files, KB-scale) and load them in addition to the inline pathological string. This is acceptable: the size budget for `tests/adv/data/` is implicit (small text files, KB-range, not the 600 MB JSON bomb scale).
