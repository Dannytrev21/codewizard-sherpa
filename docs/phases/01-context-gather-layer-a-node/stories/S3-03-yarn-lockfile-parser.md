# Story S3-03 — `_yarn` lockfile parser + ADR-0003 finalization

**Step:** Step 3 — Ship `NodeManifestProbe` and the three lockfile parsers
**Status:** Ready
**Effort:** L
**Depends on:** S1-03 (`safe_yaml` — for the path resolution / size-cap symmetry; the hand-rolled scanner runs over bytes, not YAML)
**ADRs honored:** ADR-0003 (`pyarn` if maintained, else hand-rolled — **finalized in this PR**), ADR-0008 (in-process caps), ADR-0009 (`pyarn` is the one conditional dep addition)

## Context

`yarn.lock` is the only Phase 1 lockfile that doesn't have a stdlib-clean parse path: it's neither valid YAML nor JSON. Yarn classic emits a custom indent-sensitive format ("version 1") and Yarn berry emits a YAML-ish format with custom tag conventions. This story ships both code paths and **finalizes ADR-0003 at land-time** by appending an implementer's-selection block to that ADR.

**The decision rule** (ADR-0003):

- `pyarn` last release < 18 months ago AND fixture suite passes AND no open CVE → ship `pyarn`, list it in `[project.optional-dependencies] gather`.
- Otherwise → ship the hand-rolled line-by-line state-machine scanner (~100 LOC, no regex over full file).

Both code paths return the same `YarnLock` `TypedDict` and produce identical output on the fixture portfolio — that's the load-bearing invariant validated by S3-04's parity + oracle tests.

The hand-rolled scanner is **the single most regex-DoS-prone surface in Phase 1** (`High-level-impl.md §"Implementation-level risks"` #4). Local adversarial fuzzing before the PR is non-negotiable; the dedicated adversarial CI test (`test_regex_dos_yarn_lock.py`) lands in S5-02, not here.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #9 Lockfile parsers` — `_yarn.py` with `_HAS_PYARN: bool` module-level guard; line-by-line state machine (no regex over full file); ~80 ms p50 (`pyarn`) vs. ~200 ms p50 (hand-rolled).
  - `../phase-arch-design.md §"Edge cases"` row 10 — `pyarn` uninstall path during gather → `ImportError` falls back to hand-rolled.
  - `../phase-arch-design.md §"Gap analysis" Gap 3` — two-direction parity (this story enables; S3-04 implements the tests).
- **Phase ADRs:**
  - `../ADRs/0003-yarn-lock-parser-choice.md` — **THE ADR THIS STORY FINALIZES.** Read all of it; the "Implementer's land-time selection" block is empty and **must be filled in this PR**.
  - `../ADRs/0009-no-new-c-extension-parser-dependencies.md` — `pyarn` is the only Phase 1 dep addition; the conditional adoption rule lives here.
- **Source design:**
  - `../final-design.md §"Components" #4` — three-way lockfile parsers (provenance attribution).
  - `../final-design.md §"Conflict-resolution table"` row 5 — the synthesized choice.
  - `../final-design.md §"Open questions deferred to implementation"` #1 — the land-time decision rule.
  - `../critique.md §"Attacks on the performance-first design"` #4 — the 16-ms-average-latency demolition that ruled out hand-rolled-by-default.
  - `../High-level-impl.md §"Step 3"` + `§"Implementation-level risks"` #3, #4.
- **Existing code:**
  - `src/codegenie/parsers/safe_yaml.py` (size-cap helper for the pre-parse fd read).
  - `src/codegenie/errors.py` (`SizeCapExceeded`, `MalformedLockfileError`, `SymlinkRefusedError`).
  - `pyproject.toml` — Phase 0 ADR-0006 extras shape; the `[project.optional-dependencies] gather` list is the one place `pyarn` may land.
- **External docs:**
  - PyPI page for `pyarn` (https://pypi.org/project/pyarn/) — **read at PR-open time** to pin last-release date in the ADR.
  - `pyarn` GitHub repo issue tracker — scan for open CVEs / unmaintained-fork warnings.

## Goal

Implement `src/codegenie/probes/_lockfiles/_yarn.py` with `_HAS_PYARN: bool` module-level dispatch, ship the hand-rolled scanner unconditionally, and append the implementer's land-time selection note to `ADR-0003` — so `NodeManifestProbe` can call `_yarn.parse(path)` and get a `YarnLock` `TypedDict` regardless of `pyarn` install state.

## Acceptance criteria

- [ ] `src/codegenie/probes/_lockfiles/_yarn.py` exports `parse(path: Path) -> YarnLock`, a `YarnLock` `TypedDict`, and a module-level `_HAS_PYARN: bool` computed via `importlib.util.find_spec("pyarn") is not None`.
- [ ] `parse(path)` dispatches: if `_HAS_PYARN` is `True`, call `pyarn.parse(path)`; else call the in-module `_parse_handrolled(path)`.
- [ ] **Both** dispatch paths perform the pre-parse 50 MB size check via `os.open(path, os.O_RDONLY | os.O_NOFOLLOW)` + `os.fstat` before reading bytes — i.e., they delegate the open + size check to the same helper, not to `pyarn` (so the size-cap defense holds regardless of `pyarn`'s internal behavior).
- [ ] The hand-rolled scanner is a line-by-line state machine (entry header → key/value pairs → next header). **No `re.compile(...).match(entire_file_bytes)` — no regex over the full file.** Per-line bounded regex is allowed; full-file regex is rejected at review.
- [ ] On `SizeCapExceeded`, `SymlinkRefusedError` raised by the open/size-check helper, the function re-raises unchanged. On any other parse failure (`pyarn` exception or hand-rolled state-machine error), re-raise as `MalformedLockfileError(path=path, cause=e)`.
- [ ] `YarnLock(TypedDict, total=False)` declares at minimum `entries: dict[str, YarnLockEntry]` where `YarnLockEntry(TypedDict, total=False)` declares `version: str`, `resolved: str`, `integrity: str`, `dependencies: dict[str, str]`.
- [ ] `pyproject.toml` lists `pyarn` under `[project.optional-dependencies] gather` **iff the land-time decision selects it**. If the decision is hand-rolled, `pyarn` is **not** in the dependency closure.
- [ ] `ADR-0003`'s "Implementer's land-time selection" block is **filled in this PR** with: today's date, the selection (`pyarn` or `hand-rolled`), pinned `pyarn` last-release date, the CVE-scan result, the fixture-suite pass/fail confirmation.
- [ ] Local fuzzing of the hand-rolled scanner against ≥ 1000 random byte mutations of a real `yarn.lock` completed before opening the PR — note in PR body: "fuzzed N=… iterations, max wall-clock per iteration: X ms, no parser hangs."
- [ ] TDD red test exists, was committed red, now green; happy path for both code paths + the size-cap + malformed paths covered.
- [ ] `ruff format --check`, `ruff check`, `mypy --strict`, `pytest` all pass.
- [ ] `fence` CI job continues green — `pyarn` is **not** an LLM SDK and `fence` confirms.

## Implementation outline

1. **First — evaluate `pyarn`'s status.** Open the PyPI page and the GitHub repo. Pin the last-release date. Scan open issues / GitHub Security Advisories for `pyarn`. Run the heuristic in ADR-0003:
   - Last release < 18 months ago? (vs. today's date)
   - No open CVE in the OSV / GHSA feed?
   - Does `pyarn` parse the Phase 1 fixture `tests/fixtures/node_yarn_legacy/yarn.lock` (S3-06) without error? (You may need to land this story alongside S3-06 or pre-land the fixture as part of this PR — note which path you take.)
2. **Implement the open + size-check helper** as a private function `_open_with_size_check(path, max_bytes)` in this module (or import an existing equivalent from `parsers/`). It returns `bytes` (the full file body) and raises `SizeCapExceeded` / `SymlinkRefusedError` per the standard parser contract.
3. **Implement `_parse_handrolled(body: bytes) -> YarnLock`** — a line-by-line state machine:
   - Iterate `body.decode("utf-8").splitlines()`.
   - States: `awaiting_entry`, `in_entry_header`, `in_entry_body`.
   - Entry header: starts at column 0, no leading whitespace, ends with `:`.
   - Entry body: lines starting with 2-space indent; parse `key value` or `key "value"`.
   - Sub-blocks (`dependencies:`, `optionalDependencies:`): 4-space indent.
   - **No regex** over the full body; per-line `str.startswith` / `str.split` are fine.
4. **Implement `parse(path)`**: open + size-check, then dispatch on `_HAS_PYARN`. Translate exceptions to `MalformedLockfileError`. If `_HAS_PYARN` is True and `pyarn.parse(path)` raises, log the exception type + fall back to **NO** — fall back is a different decision; this story implements **either-or** dispatch per `_HAS_PYARN`. (Phase 1's edge case row 10 covers the fallback; but the "fall back on error" behavior would muddy the parity test. Don't fall back on parse error; raise. The fallback is on `ImportError`, captured by `_HAS_PYARN`.)
5. **Update `pyproject.toml`**: conditionally add `pyarn` to `[project.optional-dependencies] gather` (only if land-time decision selects `pyarn`).
6. **Local fuzz before PR**: write a throwaway script that mutates a real `yarn.lock` (byte flips, truncations, indent swaps) ≥ 1000 times and runs `_parse_handrolled` with a 1-second per-iteration timeout. Record the longest iteration in PR body.
7. **Append the land-time selection** to `ADR-0003` per the documented "Implementer's land-time selection" block.
8. **Update `src/codegenie/probes/_lockfiles/__init__.py`** with the `YarnLock` re-export (additive).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/probes/_lockfiles/test_yarn.py`.

```python
# tests/unit/probes/_lockfiles/test_yarn.py
from pathlib import Path
import pytest
from codegenie.errors import SizeCapExceeded, MalformedLockfileError, SymlinkRefusedError
from codegenie.probes._lockfiles import _yarn

YARN_LOCK_MINIMAL = """\
# THIS IS AN AUTOGENERATED FILE. DO NOT EDIT THIS FILE DIRECTLY.
# yarn lockfile v1


bcrypt@^5.1.0:
  version "5.1.1"
  resolved "https://registry.yarnpkg.com/bcrypt/-/bcrypt-5.1.1.tgz"
  integrity sha512-AGBHOG5..."
  dependencies:
    node-addon-api "^5.0.0"
"""

def test_parse_happy_path_yields_entries(tmp_path: Path):
    lockfile = tmp_path / "yarn.lock"
    lockfile.write_text(YARN_LOCK_MINIMAL)
    result = _yarn.parse(lockfile)
    assert "bcrypt@^5.1.0" in result["entries"]
    assert result["entries"]["bcrypt@^5.1.0"]["version"] == "5.1.1"

def test_parse_oversized_file_raises_size_cap(tmp_path: Path):
    lockfile = tmp_path / "yarn.lock"
    lockfile.write_bytes(b"a:\n  version \"1.0\"\n" * (60 * 1024 * 1024 // 20))
    with pytest.raises(SizeCapExceeded):
        _yarn.parse(lockfile)

def test_parse_malformed_raises_malformed_lockfile(tmp_path: Path):
    lockfile = tmp_path / "yarn.lock"
    lockfile.write_text("malformed garbage with no entry header structure\n@@@@@\n")
    with pytest.raises(MalformedLockfileError) as exc:
        _yarn.parse(lockfile)
    assert exc.value.path == lockfile

def test_handrolled_path_forced_via_monkeypatch(tmp_path: Path, monkeypatch):
    # Force the hand-rolled path even if pyarn is installed locally.
    monkeypatch.setattr(_yarn, "_HAS_PYARN", False)
    lockfile = tmp_path / "yarn.lock"
    lockfile.write_text(YARN_LOCK_MINIMAL)
    result = _yarn.parse(lockfile)
    assert "bcrypt@^5.1.0" in result["entries"]
```

Confirm `ModuleNotFoundError`. Commit red.

### Green — make it pass

```python
# src/codegenie/probes/_lockfiles/_yarn.py
import importlib.util
import os
from pathlib import Path
from typing import Any, TypedDict, cast

from codegenie.errors import (
    MalformedLockfileError, SizeCapExceeded, SymlinkRefusedError,
)

YARN_LOCKFILE_MAX_BYTES = 50 * 1024 * 1024
_HAS_PYARN: bool = importlib.util.find_spec("pyarn") is not None


class YarnLockEntry(TypedDict, total=False):
    version: str
    resolved: str
    integrity: str
    dependencies: dict[str, str]


class YarnLock(TypedDict, total=False):
    entries: dict[str, YarnLockEntry]


def _open_with_size_check(path: Path, max_bytes: int) -> bytes:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as e:
        if e.errno in (40, 62):  # ELOOP variants across macOS/Linux
            raise SymlinkRefusedError(path=path) from e
        raise
    try:
        st = os.fstat(fd)
        if st.st_size > max_bytes:
            raise SizeCapExceeded(path=path, size=st.st_size, cap=max_bytes)
        return os.read(fd, st.st_size)
    finally:
        os.close(fd)


def _parse_handrolled(body: bytes) -> YarnLock:
    # Line-by-line state machine; no full-file regex.
    entries: dict[str, YarnLockEntry] = {}
    current_key: str | None = None
    current_entry: YarnLockEntry = {}
    current_subblock: str | None = None  # "dependencies" / None
    for raw_line in body.decode("utf-8", errors="replace").splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            if current_key is not None:
                entries[current_key] = current_entry
            if not line.endswith(":"):
                raise ValueError(f"expected entry header ending in ':', got {line!r}")
            current_key = line[:-1].strip().strip('"')
            current_entry = {}
            current_subblock = None
        elif line.startswith("    ") and current_subblock is not None:
            k, _, v = line.strip().partition(" ")
            current_entry.setdefault(current_subblock, {})[k.strip('"')] = v.strip('"')  # type: ignore[literal-required]
        elif line.startswith("  "):
            stripped = line.strip()
            if stripped in ("dependencies:", "optionalDependencies:"):
                current_subblock = stripped[:-1]
                continue
            current_subblock = None
            k, _, v = stripped.partition(" ")
            current_entry[k.strip('"')] = v.strip('"')  # type: ignore[literal-required]
    if current_key is not None:
        entries[current_key] = current_entry
    if not entries:
        raise ValueError("no yarn.lock entries parsed")
    return {"entries": entries}


def parse(path: Path) -> YarnLock:
    body = _open_with_size_check(path, YARN_LOCKFILE_MAX_BYTES)
    try:
        if _HAS_PYARN:
            import pyarn  # type: ignore[import-not-found]
            return cast(YarnLock, pyarn.parse(body.decode("utf-8")))
        return _parse_handrolled(body)
    except (SizeCapExceeded, SymlinkRefusedError):
        raise
    except Exception as e:
        raise MalformedLockfileError(path=path, cause=e) from e
```

### Refactor

- The `_open_with_size_check` helper duplicates parts of `safe_json.load` / `safe_yaml.load`. **Don't extract** unless S3-01 and S3-02 also need it (they don't — `safe_yaml`/`safe_json` already wrap their reads). Yarn is the odd parser out because `pyarn` reads strings, not files.
- The `pyarn.parse` interface may take a path or a string — adapt locally; do **not** add a `pyarn`-version-pin check to the module itself, that's an ADR-amendment-level concern.
- The state machine intentionally over-decodes (UTF-8 with `errors="replace"`); the size-cap test triggers before decode, so adversarial-byte attacks hit `SizeCapExceeded` first.
- The hand-rolled scanner's `entries` dict keys are the raw yarn-lock identifier (e.g., `"bcrypt@^5.1.0"`, possibly comma-joined for shared resolutions like `"foo@^1.0, foo@^1.1"`); the probe parses these in S3-05, not here.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/_lockfiles/_yarn.py` | New file — `_HAS_PYARN` dispatch + hand-rolled state-machine. |
| `src/codegenie/probes/_lockfiles/__init__.py` | Edit — additive `YarnLock` re-export. |
| `tests/unit/probes/_lockfiles/test_yarn.py` | New file — four-path test (happy + size-cap + malformed + forced-handrolled). |
| `pyproject.toml` | Edit (conditional) — add `pyarn` to `[project.optional-dependencies] gather` if land-time decision selects it. |
| `docs/phases/01-context-gather-layer-a-node/ADRs/0003-yarn-lock-parser-choice.md` | Edit — fill in the "Implementer's land-time selection" block per the ADR's documented shape. |

## Out of scope

- **Parity + oracle tests** — S3-04. This story ships the parser; S3-04 validates that `pyarn` and hand-rolled agree.
- **Adversarial regex-DoS test** — S5-02 (`test_regex_dos_yarn_lock.py`). Local fuzzing before PR is required; the CI-gated adversarial test lives in Step 5.
- **`NodeManifestProbe` integration** — S3-05. This module is a leaf.
- **Yarn Berry (yarn 2/3/4) `.pnp.cjs`** — not in scope; berry repos with `yarn.lock` still parse here, but `.pnp.cjs` is not consumed.
- **Lockfile-version detection** — yarn classic v1 vs. v2+ YAML-style is `pyarn`'s problem in the `_HAS_PYARN=True` path; the hand-rolled scanner targets v1 (the dominant legacy format the fixture portfolio carries).

## Notes for the implementer

- **The land-time selection is the body of the work.** Do not punt it to a follow-up PR — `High-level-impl.md §"Implementation-level risks"` #3 explicitly calls out ADR-0003 drift as the failure mode.
- **Local fuzzing IS required before opening the PR.** `High-level-impl.md §"Implementation-level risks"` #4 names this: "adversarial fuzzing in S5-02 is the CI gate but not the first defense." A 1000-iteration loop with byte-mutated `yarn.lock` and a 1-second-per-iteration timeout is sufficient evidence; capture the worst-case wall-clock in the PR body.
- The `os.O_NOFOLLOW` `ELOOP` errno is `62` on Linux and `40` on Darwin — both surface as `SymlinkRefusedError`. The simpler approach is to import the same helper `parsers/` uses if S1-02/S1-03 factored one; if not, the inline version above is the shape.
- **Don't add a `pyarn` fall-back on parse-error path.** If `pyarn` is installed but fails on a real lockfile, that's a fixture portfolio issue worth surfacing (the parity test in S3-04 catches it). Silent fall-back muddies the parity contract.
- The `entries` dict in `YarnLock` is intentionally raw — yarn-lock can have a single header line like `"foo@^1.0, foo@^1.1":` covering multiple specifier ranges. The hand-rolled scanner currently keys on the entire line; `NodeManifestProbe` (S3-05) splits on `, ` when reconciling.
- The `fence` CI job verifies no LLM SDK in `src/codegenie/`. Adding `pyarn` as an optional extra does not change `fence`'s assertion — but **re-run `fence` locally** before opening the PR per `High-level-impl.md §"Step 3" "Done criteria"` last line.
- If `pyarn`'s last release is exactly at the 18-month boundary, default to hand-rolled and document the borderline decision in the ADR note. Rule 12 (Fail loud): a "close call" is a decision, not a deferral.
- Per ADR-0003's "Reversibility" section, switching parsers later is a `_HAS_PYARN` flip + pyproject edit; nothing in the cache / wire format depends on the parser identity. That property must remain true after this PR — if you find yourself adding parser-specific fields to `YarnLock`, stop.
