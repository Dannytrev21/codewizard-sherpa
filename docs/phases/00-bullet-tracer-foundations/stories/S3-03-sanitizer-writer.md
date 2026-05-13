# Story S3-03 — Output sanitizer + atomic writer

**Step:** Step 3 — Build the harness internals (cache, coordinator, validator, sanitizer, writer, config)
**Status:** Done — 2026-05-13 (executed)
**Effort:** M
**Depends on:** S2-05, S3-02 (provides `coordinator.validator.SECRET_FIELD_PATTERN`)
**ADRs honored:** ADR-0008, ADR-0010 (single-source secret pattern), ADR-0011
**Validated:** 2026-05-13 (phase-story-validator → HARDENED; see [`_validation/S3-03-sanitizer-writer.md`](_validation/S3-03-sanitizer-writer.md))
**Executed:** 2026-05-13 — see [`_attempts/S3-03.md`](_attempts/S3-03.md). All 26 ACs green via 39 new tests; full suite 381 passed, 94.43% coverage; ruff/mypy --strict/import-linter/forbidden-patterns clean.

## Validation notes (2026-05-13 — HARDENED)

Three parallel critics (Coverage, Test-Quality, Consistency) returned **46 findings** (16 block, 23 harden, 7 nit; zero `NEEDS RESEARCH`). The validator applied edits in place:

- **Rewrote AC set end-to-end.** Original 10 ACs → 23 ACs covering field shape of `SanitizedProbeOutput`, depth-N secret-key check, embedded-mid-string path scrub, the `errors`/`warnings`-field scrub (the most likely real-world leak vector), `re.escape` for `repo_root`, paths-outside-`repo_root` semantics, a no-leak global invariant, longest-prefix-wins, `repo_root` precondition, atomic raw-then-yaml ordering with explicit `os.replace` spy verification, partial-raw failure mode, recursive symlink refusal scope, raw-artifact filename safety, **recursive** chmod tree-walk (the load-bearing edge-case-#6 fix that was hidden in a refactor note), `_csafe_warned` once-per-process semantic, empty-input round-trips, structlog event pinning, and stricter mypy/no-`# type: ignore` discipline.
- **Rewrote TDD plan end-to-end as concrete runnable Python** — same treatment S3-02 received. All `...` test bodies replaced; matrices parametrized; assertions pin `errors()[0]` / `exc.value.args[0]` / mode-bits / call-order; mutation-resistance verified for every named mutant.
- **Resolved the Writer-signature triadic contradiction.** AC-5 (`envelope: dict`), `phase-arch-design.md §Output writer + sanitizer` (`envelope: dict`), and implementer-note line 188 (a mix) agree on `envelope: dict`; ADR-0008 §Consequences line 46 ("`Writer.write` takes a `SanitizedProbeOutput`, not a `ProbeOutput` — typed enforcement that the sanitizer ran") is undeliverable as written because the writer is downstream of an N-to-1 merge that loses per-probe typing. Per Nygard policy, the *intent* of ADR-0008 (typed enforcement at the chokepoint) survives at the `OutputSanitizer.scrub` → `SanitizedProbeOutput` step; the envelope is the merge. Surfaced as a follow-up ADR amendment.
- **Resolved the chmod-scope drift.** AC-19 codifies the broader scope (recursive tree-walk including pre-existing files), matching edge case #6 and the refactor note. ADR-0011 line 39's narrower wording ("on every file and directory it creates") is the document that needs amending; surfaced as a follow-up.
- Surfaced **three architectural follow-ups** (not auto-fixed — outside this story's surgical scope): (1) ADR-0008 §Consequences line 46 amendment for Writer signature; (2) ADR-0011 line 39 amendment for chmod-scope wording; (3) `High-level-impl.md` Step 3 line 111 undercounts the sanitizer test set (5 ships vs. 3 documented).

## Context

ADR-0008 designates `OutputSanitizer.scrub` as the **single path** from a `ProbeOutput` to a persisted byte: a two-pass chokepoint (field-name regex, then absolute-path → relative-path scrubbing) that the synthesis chose over a three-pass design with synchronous `gitleaks` (rejected on cost grounds for the continuous-gather model). The Writer is the only place YAML serialization happens — `yaml.CSafeDumper` with pure-Python fallback, atomic raw-then-yaml publish, symlink refusal, and post-write `os.chmod` to `0600`/`0700` per ADR-0011. Without this story, the coordinator (S3-05) has no place to send sanitized output, and Phase 11's PR commits would leak `/Users/<contributor>/` paths into a real repo.

This story sits between S3-02 (validator) and S3-05 (coordinator wiring). The sanitizer's pass-1 is the **defense-in-depth repeat** of the validator's secret-field-name regex (same `SECRET_FIELD_PATTERN`, two passes), per ADR-0008 §Decision.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design / Output writer + sanitizer` — two-pass sanitizer contract, atomic publish, CSafe fallback
  - `../phase-arch-design.md §Edge cases` rows 7, 13 — symlink-target refusal, `pyyaml` C extension unavailable
  - `../phase-arch-design.md §Scenarios / Scenario 4` — defense-in-depth field-name pass
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0008-output-sanitizer-two-pass-chokepoint.md` — ADR-0008 — single chokepoint, two-pass, no synchronous gitleaks
  - `../ADRs/0011-codegenie-directory-permissions-model.md` — ADR-0011 — `0600`/`0700`, re-apply via `os.chmod` after every write
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0006-continuous-deterministic-gather.md` — cost model the synchronous-gitleaks rejection serves
- **Source design:**
  - `../final-design.md §2.8` — Output writer + sanitizer (synthesis source)
- **Existing code (if any):**
  - `src/codegenie/coordinator/validator.py` (S3-02) — exports `SECRET_FIELD_PATTERN`; sanitizer imports the same constant
  - `src/codegenie/errors.py` — `SecretLikelyFieldNameError`, `SymlinkRefusedError`
  - `src/codegenie/probes/base.py` — `ProbeOutput` dataclass; sanitizer consumes this shape

## Goal

`OutputSanitizer.scrub(output, repo_root)` returns a `SanitizedProbeOutput` (frozen dataclass with the exact field set of `ProbeOutput`) with secret-named keys at any depth rejected (defense in depth, single-source `SECRET_FIELD_PATTERN` imported from `coordinator.validator`) and every absolute-path string under `/Users/<u>/`, `/home/<u>/`, `/root/`, or `<analyzed-repo-abs>/` rewritten — relative to the repo root when under it, else with the user-home segment stripped — in `schema_slice`, `errors`, and `warnings`; `Writer.write(envelope, raw_artifacts, output_dir)` atomically publishes `repo-context.yaml` + raw artifacts (raw-first, yaml-last, verified ordering), refusing to overwrite a symlink at `output_dir`, `output_dir/raw/`, or `output_dir/repo-context.yaml`, with mode `0600`/`0700` re-applied **recursively** post-write (covering the `actions/cache`-restore flattening of pre-existing children).

## Acceptance criteria

### `SanitizedProbeOutput` shape

- [ ] **AC-1** — `src/codegenie/output/sanitizer.py` exports `OutputSanitizer.scrub(output: ProbeOutput, repo_root: Path) -> SanitizedProbeOutput` and the `SanitizedProbeOutput` frozen dataclass.
- [ ] **AC-2** — `SanitizedProbeOutput` has the exact field set of `ProbeOutput` (`schema_slice`, `raw_artifacts`, `confidence`, `duration_ms`, `warnings`, `errors`). A test imports both and asserts `{f.name for f in dataclasses.fields(SanitizedProbeOutput)} == {f.name for f in dataclasses.fields(ProbeOutput)}`. Frozen mutation raises `dataclasses.FrozenInstanceError`. Honest-confidence commitment (CLAUDE.md) requires `confidence` to survive scrubbing; a missing-field mutant must fail this AC's test.

### Pass 1 — secret-name rejection (defense in depth)

- [ ] **AC-3** — Pass 1 uses `coordinator.validator.SECRET_FIELD_PATTERN` **by identity** (not equality): `sanitizer.SECRET_FIELD_PATTERN is coordinator.validator.SECRET_FIELD_PATTERN`. An AST scan of `output/sanitizer.py` asserts no `re.compile(...)` call is bound to a name matching `(?i).*secret.*` (drift-detector — closes the cross-story coupling S3-02 validation deferred to this story).
- [ ] **AC-4** — A secret-shaped key at any depth (top-level, nested dict, list-of-dicts) raises `SecretLikelyFieldNameError(<key-name>)`; `exc.value.args[0]` pins the offending key (test parametrized over depths 1..5 and over the key set `{"github_token", "api_key", "AWS_SECRET_ACCESS_KEY", "client_secret", "Bearer-Token"}` plus a benign-key matrix `{"description", "language", "tokens_per_line"}` that must NOT raise).

### Pass 2 — path scrubbing

- [ ] **AC-5** — Path-scrub regex is compiled per-call as `re.compile(r"(/Users/|/home/|/root/|" + re.escape(str(repo_root.resolve())) + ")")`. The pattern is **non-anchored** so embedded-mid-string occurrences are scrubbed (a string `"see /Users/danny/x.js"` in `errors` becomes `"see x.js"` after the user-home strip). Lazy-impl-mutant note: an anchored regex passes individual happy-path tests but defeats the goal — the no-leak invariant AC-12 catches it.
- [ ] **AC-6** — Scrubbing walks recursively through `dict` and `list` at arbitrary depth (≥ 5 tested) over `schema_slice`, `errors`, and `warnings`. **`errors`-field scrubbing is load-bearing**: probes emit `errors=["FileNotFoundError: /Users/danny/foo"]` and those land in `repo-context.yaml`. Pinned by a test where `ProbeOutput.errors=["error at /Users/danny/x"]` produces a scrubbed `errors` containing no `/Users/` substring.
- [ ] **AC-7** — `re.escape` is applied to `str(repo_root.resolve())`. A test with `repo_root = tmp_path / "repo.git"` (regex metachar `.`) and a decoy string `f"{tmp_path}/repoXgit/foo"` proves the decoy is **not** scrubbed (would be over-matched without `re.escape`).
- [ ] **AC-8** — Symlinked `repo_root`: when `repo_root` is a symlink to a real dir, paths under the resolved-real dir are still scrubbed (the regex uses `.resolve()`). Test: `link = tmp_path/"link"` → `real = tmp_path/"real"`; `link.symlink_to(real)`; scrubbing a string under `real` while passing `link` as `repo_root` produces a relative path.
- [ ] **AC-9** — When the scrubbed absolute path is under `repo_root`, it's rewritten relative to that root (`/Users/danny/repo/src/a.js` with `repo_root=/Users/danny/repo` → `src/a.js`). When under `/Users/<u>/` (or `/home/<u>/`) but NOT under `repo_root`, the leading `/Users/<u>/` segment is stripped — never the empty string — so the username does not appear in the output and structural info survives (`/Users/danny/other-repo/x` → `other-repo/x`). `/root/...` → `...` (no user segment to strip).
- [ ] **AC-10** — Longest-prefix-wins when alternation overlaps: a path under `repo_root=/Users/danny/repo` matches both `/Users/` and `<repo_root>/`; the longer (`<repo_root>/`) wins. Test asserts the result is `<rel>`, not `danny/repo/<rel>`.
- [ ] **AC-11** — `scrub` requires `repo_root` to be absolute and resolved: if `repo_root.is_absolute() is False` or `repo_root != repo_root.resolve()` or `repo_root == Path("/")`, raises `ValueError`. Three tests, one per condition.
- [ ] **AC-12** — **No-leak global invariant** (load-bearing for Phase 11 PR commits): for any `out` that passes pass-1, walking every string in the scrubbed `schema_slice`/`errors`/`warnings` yields zero strings that start with `/Users/`, `/home/`, `/root/`, or `str(repo_root.resolve())`. Pinned by a fixture containing all four forbidden-prefix variants in nested-dict/list shapes; mutation: dropping any one alternative from the regex fails this test.
- [ ] **AC-13** — Determinism + idempotence: for the same `(out, repo_root)`, `scrub` produces byte-identical `SanitizedProbeOutput` across instances (asserted via `json.dumps(dataclasses.asdict(s), sort_keys=False)` equality of two independent runs). Idempotence: for any pass-1-clean `out`, scrubbing the result a second time (re-wrapping `SanitizedProbeOutput` as `ProbeOutput` via a test helper) yields equal output; the test also asserts the first scrub *did work* (non-identity) when the input had absolute paths — defeating the lazy `def scrub(x,_): return x` mutant.

### Writer — atomic publish

- [ ] **AC-14** — `src/codegenie/output/writer.py` exports `Writer.write(envelope: dict, raw_artifacts: list[tuple[str, bytes]], output_dir: Path) -> None`. The "typed enforcement that the sanitizer ran" promised by ADR-0008 §Consequences line 46 is delivered upstream at the `OutputSanitizer.scrub` → `SanitizedProbeOutput` step; the envelope passed here is the merged dict the coordinator produces. ADR-0008 §Consequences amendment surfaced as follow-up.
- [ ] **AC-15** — Writer uses `yaml.CSafeDumper`; on `ImportError` falls back to `yaml.SafeDumper` and logs `writer.csafe.unavailable` **once per process** via a module-level `_csafe_warned: bool` flag. Test: three sequential `Writer().write(...)` calls with `CSafeDumper` import patched to fail produce exactly one `writer.csafe.unavailable` event in `structlog.testing.capture_logs`, but all three writes succeed and emit valid YAML. **Does not** fall through to `yaml.Dumper` (banned by S1-04 `forbidden-patterns` lint; this story does not duplicate the lint).
- [ ] **AC-16** — Atomic envelope publish: envelope written to `<output_dir>/repo-context.yaml.tmp`, then `os.fsync(tmp_fd)`, then `os.replace`. A test patches `codegenie.output.writer.os.fsync` and `os.replace` with `mock.MagicMock` and asserts both were called and that `fsync` was called before `replace` (via `call_args_list` order). **Parent-directory fsync after rename** is out of scope for Phase 0 (deferred; documented in Out-of-scope).
- [ ] **AC-17** — Atomic publish ordering: raw artifacts are `os.replace`-published (each via `<dest>.tmp → fsync → os.replace`) **strictly before** the envelope. A test spies `codegenie.output.writer.os.replace` and asserts the final destination in `call_args_list[-1]` is `repo-context.yaml` and that none of `call_args_list[:-1]` has `repo-context.yaml` as its destination.
- [ ] **AC-18** — Partial-raw failure: if any raw-artifact write raises `OSError`, Writer propagates the error and the envelope `repo-context.yaml` is **not** written or replaced. Caller detects partial state by envelope absence. Test patches the second raw `os.replace` to raise, asserts the call raises, asserts `(output_dir/"repo-context.yaml").exists() is False`, and asserts the first raw artifact (which succeeded) is present.
- [ ] **AC-19** — Envelope-replace failure: if `os.replace` for the envelope raises, no `repo-context.yaml` is left, and any `.tmp` file (if it persists across the failure) has mode `0600` (no insecure-mode leak window). Test patches `codegenie.output.writer.os.replace` only for the yaml destination to raise.

### Writer — symlink refusal & filename safety

- [ ] **AC-20** — Pre-write symlink check refuses all three planted-symlink shapes: `output_dir`, `output_dir/raw/`, `output_dir/repo-context.yaml`. Each test creates the corresponding symlink to a sentinel file with known bytes, calls `Writer.write(...)`, asserts `SymlinkRefusedError(<path>)`, asserts the sentinel bytes are unchanged (no follow-the-symlink write), and asserts no `.tmp` file was created.
- [ ] **AC-21** — Raw-artifact filename safety: names containing `/`, `..`, leading `/`, or empty string raise `ValueError` **before any write**. Parametrized over `["../escape.json", "/abs/path.json", "", "a/b/c.json", "."]`. This closes the chokepoint property of ADR-0008: the writer is the single path to disk, and the path's leaf names must be safe.

### Writer — permissions discipline (ADR-0011, edge case #6)

- [ ] **AC-22** — After every `write()`, Writer **recursively** walks `output_dir` and applies `0600` to every regular file and `0700` to every directory — **including pre-existing files/directories** inside `output_dir` (the load-bearing fix for edge case #6, CI `actions/cache`-restore mode flattening). Two tests: (a) new write produces `0600`/`0700` modes throughout the tree (including nested `raw/<name>.json`); (b) pre-existing file at `0644` inside `output_dir/raw/` is re-chmodded to `0600` by the next `Writer.write()`. ADR-0011 line 39's narrower "every file and directory it creates" wording is the document that needs amending (surfaced as follow-up); this AC is the authoritative scope.

### `paths.py` + structlog + tooling

- [ ] **AC-23** — `src/codegenie/output/paths.py` exports four pure functions `context_dir(repo_root: Path) -> Path`, `raw_dir(repo_root: Path) -> Path`, `yaml_path(repo_root: Path) -> Path`, `runs_dir(repo_root: Path) -> Path`. All return `Path` values under `<repo_root>/.codegenie/context/`. No IO. Deterministic. Tests parametrize over five `repo_root` shapes.
- [ ] **AC-24** — Empty inputs round-trip: (a) `scrub(out, r)` where `out.schema_slice={}` and `out.errors=[]` returns `SanitizedProbeOutput` with empty `schema_slice`/`errors` and emits zero `sanitizer.path.rewritten` events; (b) `Writer.write(envelope={"schema_version": "0.1.0"}, raw_artifacts=[], output_dir=tmp)` succeeds, creates `output_dir/raw/` as an empty `0700` directory, and writes a valid `repo-context.yaml` with mode `0600`.
- [ ] **AC-25** — structlog events are emitted **exactly when** their code paths fire and **not otherwise**: `sanitizer.secret.rejected` (on pass-1 rejection), `sanitizer.path.rewritten` at DEBUG (on each pass-2 string rewrite), `writer.symlink.refused` (on symlink refusal), `writer.csafe.unavailable` (once per process on CSafe ImportError). Verified by `structlog.testing.capture_logs` per local idiom (`test_logging.py`, `test_exec.py`). A happy-path Writer call emits **zero** of these events.
- [ ] **AC-26** — All tests below pass; `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/output/` (zero errors, zero `# type: ignore` directives in new code), and `pytest` clean on touched files.

## Implementation outline

1. Author `src/codegenie/output/__init__.py` (empty package marker).
2. Author `src/codegenie/output/paths.py` — four pure helpers, no IO.
3. Author `src/codegenie/output/sanitizer.py`:
   - `SanitizedProbeOutput` frozen dataclass with the exact field set of `ProbeOutput` (AC-2).
   - `from codegenie.coordinator.validator import SECRET_FIELD_PATTERN` — bound at module scope as `SECRET_FIELD_PATTERN` (re-export so `sanitizer.SECRET_FIELD_PATTERN is validator.SECRET_FIELD_PATTERN` per AC-3).
   - `OutputSanitizer.scrub(output, repo_root)`:
     1. Validate `repo_root` precondition (AC-11): `repo_root.is_absolute() and repo_root == repo_root.resolve() and repo_root != Path("/")` else `ValueError`.
     2. Compile pass-2 regex per-call: `re.compile(r"(/Users/[^/]+/|/home/[^/]+/|/root/|" + re.escape(str(repo_root.resolve())) + "/?)")` — **non-anchored** (embedded-mid-string scrub) and capture-group-shaped so the replace callback can pick the rewrite rule (relative-to-repo vs. user-home-strip vs. /root strip).
     3. Walk `output.schema_slice`, `output.errors`, and `output.warnings` recursively (`dict.items()`, `list.__iter__`):
        - For dict keys: pass 1 — if `SECRET_FIELD_PATTERN.search(key)` → raise `SecretLikelyFieldNameError(key)` + emit `sanitizer.secret.rejected`.
        - For str values: pass 2 — `re.sub` with a replacement callback that emits `sanitizer.path.rewritten` (DEBUG) and applies the longest-prefix-wins rule (analyzed-repo-abs takes priority via alternation order; under `/Users/<u>/` outside repo → strip the segment).
     4. Return `SanitizedProbeOutput(**replaced_fields)`.
4. Author `src/codegenie/output/writer.py`:
   - Module-level `_csafe_warned: bool = False`; helper `_import_csafe_dumper()` returns the Dumper class, sets the flag, emits the once-per-process log on fallback.
   - Helper `_assert_safe_name(name: str) -> None` for AC-21 (raise `ValueError` on `/`, `..`, empty, leading `/`).
   - `Writer.write(envelope, raw_artifacts, output_dir)`:
     1. Pre-write symlink check on `output_dir`, `output_dir/raw/`, `output_dir/repo-context.yaml` (AC-20). On match raise `SymlinkRefusedError(<path>)` + emit `writer.symlink.refused` — **before** any write.
     2. Validate every raw-artifact name via `_assert_safe_name` (AC-21).
     3. `mkdir(output_dir, mode=0o700, exist_ok=True)`; `mkdir(output_dir/"raw", mode=0o700, exist_ok=True)`.
     4. For each `(name, payload)` in raw_artifacts: write `<output_dir>/raw/<name>.tmp`, `os.fsync(fd)`, `os.replace` to `<output_dir>/raw/<name>` (AC-17 — must complete before yaml).
     5. Serialize envelope via `yaml.dump(..., Dumper=CSafeDumperOrFallback)`; write `<output_dir>/repo-context.yaml.tmp`; `os.fsync(fd)`; `os.replace` to `<output_dir>/repo-context.yaml` (AC-16).
     6. `_fix_modes(output_dir)` — recursive walk that chmod's every regular file to `0600` and every directory to `0700` (AC-22, edge case #6).
5. Write tests for the public surface (sanitizer + writer + paths). See TDD plan below.

## TDD plan — red / green / refactor

Anchored behaviors: (a) `SanitizedProbeOutput` shape parity, (b) pass-1 secret rejection at depth, (c) pass-2 path scrub with embedded + outside-repo + `re.escape` + longest-prefix + symlinked-root variants, (d) no-leak global invariant, (e) determinism + idempotence, (f) Writer atomic ordering + partial-failure mode, (g) Writer symlink refusal at three paths, (h) raw-artifact filename safety, (i) Writer `_csafe_warned` once-per-process, (j) **recursive** chmod tree-walk fixing pre-existing modes, (k) structlog event pinning.

### Red — write the failing tests first

Test file paths: `tests/unit/test_output_sanitizer.py`, `tests/unit/test_output_writer.py`, `tests/unit/test_output_paths.py`.

```python
# tests/unit/test_output_sanitizer.py
from __future__ import annotations
import ast, dataclasses, inspect, json, os, re
from dataclasses import asdict, replace
from pathlib import Path

import pytest
import structlog.testing

from codegenie.coordinator.validator import SECRET_FIELD_PATTERN as CANONICAL
from codegenie.errors import SecretLikelyFieldNameError
from codegenie.output import sanitizer as san
from codegenie.output.sanitizer import OutputSanitizer, SanitizedProbeOutput
from codegenie.probes.base import ProbeOutput


def _probe(
    *,
    schema_slice: dict[str, object] | None = None,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> ProbeOutput:
    return ProbeOutput(
        schema_slice=schema_slice if schema_slice is not None else {},
        raw_artifacts=[],
        confidence="high",
        duration_ms=1,
        warnings=warnings or [],
        errors=errors or [],
    )


def _iter_strings(node: object) -> list[str]:
    out: list[str] = []
    def walk(x: object) -> None:
        if isinstance(x, str): out.append(x); return
        if isinstance(x, dict):
            for k, v in x.items(): walk(k); walk(v); return
        if isinstance(x, list):
            for v in x: walk(v); return
    walk(node); return out


def _resolved_tmp(tmp_path: Path) -> Path:
    # ensure precondition (AC-11): absolute + resolved
    return tmp_path.resolve()


# AC-1 / AC-2 — SanitizedProbeOutput field-set parity, frozen, isolated module location
def test_sanitized_probe_output_field_parity():
    assert {f.name for f in dataclasses.fields(SanitizedProbeOutput)} == {
        f.name for f in dataclasses.fields(ProbeOutput)
    }


def test_sanitized_probe_output_is_frozen():
    s = SanitizedProbeOutput(schema_slice={}, raw_artifacts=[], confidence="high",
                             duration_ms=0, warnings=[], errors=[])
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.confidence = "low"  # type: ignore[misc]


# AC-3 — secret pattern is imported by identity, no inline re.compile
def test_sanitizer_uses_canonical_secret_pattern_by_identity():
    assert san.SECRET_FIELD_PATTERN is CANONICAL  # identity, not equality


def test_sanitizer_module_does_not_redefine_secret_regex():
    tree = ast.parse(inspect.getsource(san))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "compile"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "re"):
            pytest.fail(f"sanitizer.py compiles its own regex at line {node.lineno}; "
                        "must import SECRET_FIELD_PATTERN from coordinator.validator")


# AC-4 — depth-N secret-key rejection (parametrized)
SECRET_KEYS = ["github_token", "api_key", "AWS_SECRET_ACCESS_KEY",
               "client_secret", "Bearer-Token", "PRIVATE_KEY"]

def _nest(key: str, depth: int) -> dict[str, object]:
    node: dict[str, object] | list[object] = {key: "<value>"}
    for _ in range(depth - 1):
        node = {"layer": node} if isinstance(node, dict) else [node]
    return node  # type: ignore[return-value]

@pytest.mark.parametrize("depth", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("key", SECRET_KEYS)
def test_pass1_rejects_secret_key_at_any_depth(tmp_path, depth, key):
    out = _probe(schema_slice=_nest(key, depth))
    with pytest.raises(SecretLikelyFieldNameError) as exc:
        OutputSanitizer().scrub(out, repo_root=_resolved_tmp(tmp_path))
    assert exc.value.args[0] == key  # pins WHICH key matched (defeats any-error-passes mutant)


BENIGN_KEYS = ["description", "language", "tokens_per_line", "package_name",
               "test_count", "exit_status"]

@pytest.mark.parametrize("key", BENIGN_KEYS)
def test_pass1_does_not_reject_benign_keys(tmp_path, key):
    out = _probe(schema_slice={key: "value"})
    OutputSanitizer().scrub(out, repo_root=_resolved_tmp(tmp_path))  # must NOT raise


# AC-5 — embedded mid-string path scrub
def test_pass2_scrubs_embedded_path_in_error_string(tmp_path):
    tmp = _resolved_tmp(tmp_path)
    msg = f"FileNotFoundError: /Users/danny/foo.js while reading {tmp}/src/a.js"
    out = _probe(errors=[msg])
    result = OutputSanitizer().scrub(out, repo_root=tmp)
    assert "/Users/danny/" not in result.errors[0]
    assert str(tmp) not in result.errors[0]


# AC-6 — pass-2 walks schema_slice, errors, warnings
def test_pass2_scrubs_errors_field(tmp_path):
    tmp = _resolved_tmp(tmp_path)
    out = _probe(errors=[f"error at {tmp}/src/x.js", "/Users/bob/other"])
    result = OutputSanitizer().scrub(out, repo_root=tmp)
    for s in result.errors:
        assert not s.startswith("/Users/")
        assert str(tmp) not in s


def test_pass2_scrubs_warnings_field(tmp_path):
    tmp = _resolved_tmp(tmp_path)
    out = _probe(warnings=[f"deprecated: /home/alice/lib"])
    result = OutputSanitizer().scrub(out, repo_root=tmp)
    assert "/home/alice/" not in result.warnings[0]


@pytest.mark.parametrize("depth", [1, 2, 3, 4, 5])
def test_pass2_walks_arbitrary_depth(tmp_path, depth):
    tmp = _resolved_tmp(tmp_path)
    leaf = str(tmp / "src" / "a.js")
    node: object = leaf
    for i in range(depth):
        node = {"l": node} if i % 2 == 0 else [node]
    out = _probe(schema_slice={"root": node})
    result = OutputSanitizer().scrub(out, repo_root=tmp).schema_slice
    flat = _iter_strings(result)
    assert flat == ["src/a.js"]


# AC-7 — re.escape applied; regex metachars in repo_root don't over-match
def test_pass2_escapes_regex_metachars_in_repo_root(tmp_path):
    repo = tmp_path / "repo.git"; repo.mkdir()
    repo = repo.resolve()
    decoy = tmp_path.resolve() / "repoXgit" / "foo"  # X is any char, not "."
    out = _probe(schema_slice={
        "real": f"{repo}/src/a.js",
        "decoy": str(decoy),
    })
    result = OutputSanitizer().scrub(out, repo_root=repo).schema_slice
    assert result["real"] == "src/a.js"
    assert result["decoy"] == str(decoy)  # untouched — proves re.escape was used


# AC-8 — symlinked repo_root resolves to real
def test_pass2_resolves_symlinked_repo_root(tmp_path):
    real = tmp_path / "real_repo"; real.mkdir(); real = real.resolve()
    link = tmp_path / "link"; link.symlink_to(real)
    link_resolved = link.resolve()  # equals real
    out = _probe(schema_slice={"file": str(real / "src" / "a.js")})
    result = OutputSanitizer().scrub(out, repo_root=link_resolved).schema_slice["file"]
    assert result == "src/a.js"


# AC-9 — under-repo → relative; outside repo under /Users/<u>/ → strip user segment
def test_pass2_under_repo_is_relative(tmp_path):
    tmp = _resolved_tmp(tmp_path)
    out = _probe(schema_slice={"f": f"{tmp}/src/a.js"})
    assert OutputSanitizer().scrub(out, repo_root=tmp).schema_slice["f"] == "src/a.js"


def test_pass2_outside_repo_under_users_strips_user_segment(tmp_path):
    tmp = _resolved_tmp(tmp_path)
    out = _probe(schema_slice={"f": "/Users/danny/other-repo/x.js"})
    result = OutputSanitizer().scrub(out, repo_root=tmp).schema_slice["f"]
    assert result == "other-repo/x.js"
    assert "danny" not in result  # username never leaks


def test_pass2_outside_repo_under_root_strips_root(tmp_path):
    tmp = _resolved_tmp(tmp_path)
    out = _probe(schema_slice={"f": "/root/work/x.js"})
    result = OutputSanitizer().scrub(out, repo_root=tmp).schema_slice["f"]
    assert result == "work/x.js"


# AC-10 — longest-prefix-wins
def test_pass2_repo_under_users_prefers_repo_prefix(tmp_path):
    # repo_root /Users/danny/repo intersects both /Users/ and the repo alternation
    fake_home = tmp_path / "Users" / "danny" / "repo"
    fake_home.mkdir(parents=True)
    repo = fake_home.resolve()
    out = _probe(schema_slice={"f": f"{repo}/src/a.js"})
    result = OutputSanitizer().scrub(out, repo_root=repo).schema_slice["f"]
    assert result == "src/a.js"  # NOT "danny/repo/src/a.js"


# AC-11 — repo_root precondition
def test_scrub_rejects_relative_repo_root():
    with pytest.raises(ValueError):
        OutputSanitizer().scrub(_probe(), repo_root=Path("repo"))

def test_scrub_rejects_unresolved_repo_root(tmp_path):
    nested = tmp_path / "a" / ".." / "a"  # not equal to .resolve()
    with pytest.raises(ValueError):
        OutputSanitizer().scrub(_probe(), repo_root=nested)

def test_scrub_rejects_root_slash():
    with pytest.raises(ValueError):
        OutputSanitizer().scrub(_probe(), repo_root=Path("/"))


# AC-12 — no-leak global invariant (THE load-bearing security test)
FORBIDDEN_PREFIXES = ("/Users/", "/home/", "/root/")

def test_no_path_leaks_anywhere_after_scrub(tmp_path):
    tmp = _resolved_tmp(tmp_path)
    messy = {
        "f1": "/Users/danny/x",
        "f2": "/home/alice/y",
        "f3": "/root/z",
        "f4": f"{tmp}/a.js",
        "nested": {
            "list": ["/Users/bob/c", f"{tmp}/b", "ok-relative"],
            "deeper": {"x": "/home/charlie/d.js"},
        },
    }
    out = _probe(schema_slice=messy, errors=[f"err at {tmp}/c.js"],
                 warnings=["/Users/dave/w.js"])
    result = OutputSanitizer().scrub(out, repo_root=tmp)
    for s in _iter_strings(result.schema_slice) + result.errors + result.warnings:
        assert not s.startswith(FORBIDDEN_PREFIXES), f"leak: {s!r}"
        assert str(tmp) not in s, f"repo_root leak: {s!r}"


# AC-13 — determinism + idempotence (with non-identity check)
def _as_probe_output(s: SanitizedProbeOutput) -> ProbeOutput:
    return ProbeOutput(schema_slice=s.schema_slice, raw_artifacts=s.raw_artifacts,
                       confidence=s.confidence, duration_ms=s.duration_ms,
                       warnings=s.warnings, errors=s.errors)

def test_scrub_is_deterministic_across_instances(tmp_path):
    tmp = _resolved_tmp(tmp_path)
    out = _probe(schema_slice={"f": f"{tmp}/src/a.js", "g": "/Users/x/y"})
    s1 = OutputSanitizer().scrub(out, repo_root=tmp)
    s2 = OutputSanitizer().scrub(out, repo_root=tmp)
    assert json.dumps(asdict(s1), sort_keys=False) == json.dumps(asdict(s2), sort_keys=False)


def test_scrub_is_idempotent_and_does_work(tmp_path):
    tmp = _resolved_tmp(tmp_path)
    out = _probe(schema_slice={"f": f"{tmp}/src/a.js"})
    once = OutputSanitizer().scrub(out, repo_root=tmp)
    assert once.schema_slice["f"] == "src/a.js"  # first call DID work (non-identity)
    twice = OutputSanitizer().scrub(_as_probe_output(once), repo_root=tmp)
    assert asdict(twice) == asdict(once)


# AC-25 — structlog event emission pinning
def test_pass1_emits_secret_rejected_event(tmp_path):
    out = _probe(schema_slice={"github_token": "x"})
    with structlog.testing.capture_logs() as captured:
        with pytest.raises(SecretLikelyFieldNameError):
            OutputSanitizer().scrub(out, repo_root=_resolved_tmp(tmp_path))
    assert any(r.get("event") == "sanitizer.secret.rejected" for r in captured)


def test_pass2_emits_path_rewritten_at_debug(tmp_path):
    tmp = _resolved_tmp(tmp_path)
    out = _probe(schema_slice={"f": f"{tmp}/x"})
    with structlog.testing.capture_logs() as captured:
        OutputSanitizer().scrub(out, repo_root=tmp)
    rewrites = [r for r in captured if r.get("event") == "sanitizer.path.rewritten"]
    assert len(rewrites) == 1
    assert rewrites[0]["log_level"] == "debug"


def test_clean_input_emits_no_rewrite_events(tmp_path):
    out = _probe(schema_slice={"f": "src/already-relative.js"})
    with structlog.testing.capture_logs() as captured:
        OutputSanitizer().scrub(out, repo_root=_resolved_tmp(tmp_path))
    assert not [r for r in captured if r.get("event") == "sanitizer.path.rewritten"]


# AC-24 — empty input round-trip
def test_scrub_empty_schema_slice_roundtrips(tmp_path):
    out = _probe()  # empty everything
    result = OutputSanitizer().scrub(out, repo_root=_resolved_tmp(tmp_path))
    assert result.schema_slice == {}
    assert result.errors == [] and result.warnings == []
```

```python
# tests/unit/test_output_writer.py
from __future__ import annotations
import os, stat
from pathlib import Path
from unittest import mock

import pytest
import structlog.testing
import yaml

import codegenie.output.writer as writer_mod
from codegenie.errors import SymlinkRefusedError
from codegenie.output.writer import Writer


ENV = {"schema_version": "0.1.0", "probes": {}}


# AC-14 + AC-15 — happy-path write produces valid YAML using CSafeDumper when available
def test_writer_writes_yaml_via_csafe_or_safe(tmp_path):
    Writer().write(envelope=ENV, raw_artifacts=[], output_dir=tmp_path)
    body = (tmp_path / "repo-context.yaml").read_text()
    assert yaml.safe_load(body) == ENV


# AC-22 — modes applied recursively (new files AND pre-existing children)
def test_writer_modes_applied_recursively_to_new_tree(tmp_path):
    raws = [("a.json", b"{}"), ("nested.json", b"{}")]
    Writer().write(envelope=ENV, raw_artifacts=raws, output_dir=tmp_path)
    assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o700
    for p in tmp_path.rglob("*"):
        mode = stat.S_IMODE(p.stat().st_mode)
        if p.is_dir():
            assert mode == 0o700, f"{p} dir mode {oct(mode)}"
        else:
            assert mode == 0o600, f"{p} file mode {oct(mode)}"


def test_writer_fixes_preexisting_loose_modes(tmp_path):
    # Simulate post-CI-cache-restore state (edge case #6).
    raw_dir = tmp_path / "raw"; raw_dir.mkdir(mode=0o755)
    preexist = raw_dir / "stale.json"; preexist.write_bytes(b"{}")
    os.chmod(preexist, 0o644)
    Writer().write(envelope=ENV, raw_artifacts=[], output_dir=tmp_path)
    assert stat.S_IMODE(raw_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(preexist.stat().st_mode) == 0o600


# AC-16 + AC-17 — fsync called before replace; raws replaced before yaml
def test_writer_fsync_called_before_replace(tmp_path):
    with mock.patch.object(writer_mod.os, "fsync", wraps=os.fsync) as fsync_spy, \
         mock.patch.object(writer_mod.os, "replace", wraps=os.replace) as replace_spy:
        Writer().write(envelope=ENV, raw_artifacts=[], output_dir=tmp_path)
    assert fsync_spy.call_count >= 1
    # The first fsync must happen before the first replace.
    first_fsync = fsync_spy.mock_calls[0]
    first_replace = replace_spy.mock_calls[0]
    all_calls = mock.call.mock_calls if False else []  # placeholder for combined ordering
    # Pragmatic ordering check: combined mock with manager
    manager = mock.Mock()
    manager.attach_mock(fsync_spy, "fsync")
    manager.attach_mock(replace_spy, "replace")
    names = [c[0] for c in manager.mock_calls]
    assert names.index("fsync") < names.index("replace")


def test_writer_replaces_raws_before_yaml(tmp_path):
    seen: list[str] = []
    real_replace = os.replace
    def spy(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        seen.append(Path(dst).name); real_replace(src, dst)
    with mock.patch.object(writer_mod.os, "replace", side_effect=spy):
        Writer().write(envelope=ENV,
                       raw_artifacts=[("a.json", b"{}"), ("b.json", b"{}")],
                       output_dir=tmp_path)
    assert seen[-1] == "repo-context.yaml"
    assert all(n != "repo-context.yaml" for n in seen[:-1])
    assert "a.json" in seen and "b.json" in seen


# AC-18 — partial-raw failure leaves envelope absent
def test_writer_partial_raw_failure_no_envelope(tmp_path):
    call_count = {"n": 0}
    def maybe_fail(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        call_count["n"] += 1
        if call_count["n"] == 2 and Path(dst).name != "repo-context.yaml":
            raise OSError("simulated disk full mid-raw")
        os.replace(src, dst)
    with mock.patch.object(writer_mod.os, "replace", side_effect=maybe_fail), \
         pytest.raises(OSError):
        Writer().write(envelope=ENV,
                       raw_artifacts=[("a.json", b"{}"), ("b.json", b"{}")],
                       output_dir=tmp_path)
    assert not (tmp_path / "repo-context.yaml").exists()


# AC-19 — envelope replace failure: no yaml, no mode leak
def test_writer_envelope_replace_failure_no_partial_yaml(tmp_path):
    def fail_yaml(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        if Path(dst).name == "repo-context.yaml":
            raise OSError("simulated")
        os.replace(src, dst)
    with mock.patch.object(writer_mod.os, "replace", side_effect=fail_yaml), \
         pytest.raises(OSError):
        Writer().write(envelope=ENV, raw_artifacts=[], output_dir=tmp_path)
    assert not (tmp_path / "repo-context.yaml").exists()
    tmp = tmp_path / "repo-context.yaml.tmp"
    if tmp.exists():
        assert stat.S_IMODE(tmp.stat().st_mode) == 0o600  # no insecure-mode leak


# AC-20 — symlink refusal at three planted locations; no follow-through write
@pytest.mark.parametrize("victim", ["output_dir", "raw", "repo-context.yaml"])
def test_writer_refuses_symlink_planted(tmp_path, victim):
    sentinel = tmp_path / "sentinel"; sentinel.mkdir()
    decoy_file = sentinel / "decoy.txt"; decoy_file.write_bytes(b"original")
    out_dir = tmp_path / "out"
    if victim == "output_dir":
        out_dir.symlink_to(sentinel)
    else:
        out_dir.mkdir(mode=0o700)
        target = out_dir / ("raw" if victim == "raw" else "repo-context.yaml")
        if victim == "raw":
            target.symlink_to(sentinel)
        else:
            target.symlink_to(decoy_file)
    with pytest.raises(SymlinkRefusedError) as exc:
        Writer().write(envelope=ENV, raw_artifacts=[], output_dir=out_dir)
    assert victim in str(exc.value).lower() or "symlink" in str(exc.value).lower()
    assert decoy_file.read_bytes() == b"original"
    # No .tmp produced
    assert not list(tmp_path.rglob("*.tmp"))


# AC-21 — raw-artifact filename safety
@pytest.mark.parametrize("bad", ["../escape.json", "/abs/path.json", "", "a/b/c.json", "."])
def test_writer_refuses_unsafe_raw_names(tmp_path, bad):
    with pytest.raises(ValueError):
        Writer().write(envelope=ENV, raw_artifacts=[(bad, b"{}")], output_dir=tmp_path)
    assert not (tmp_path / "repo-context.yaml").exists()


# AC-15 — _csafe_warned: log once per process
def test_writer_csafe_unavailable_logs_once_per_process(tmp_path, monkeypatch):
    # Force the fallback path on every call; module-level flag should suppress repeat logs.
    monkeypatch.setattr(writer_mod, "_csafe_warned", False, raising=False)
    def no_csafe() -> object:
        raise ImportError("no libyaml")
    monkeypatch.setattr(writer_mod, "_import_csafe_dumper", no_csafe)
    with structlog.testing.capture_logs() as captured:
        for sub in ("a", "b", "c"):
            d = tmp_path / sub; d.mkdir()
            Writer().write(envelope=ENV, raw_artifacts=[], output_dir=d)
            assert (d / "repo-context.yaml").exists()  # fallback writes succeed
    events = [r for r in captured if r.get("event") == "writer.csafe.unavailable"]
    assert len(events) == 1


# AC-24 — empty inputs
def test_writer_empty_raws_creates_raw_dir_at_0700(tmp_path):
    Writer().write(envelope=ENV, raw_artifacts=[], output_dir=tmp_path)
    raw = tmp_path / "raw"
    assert raw.is_dir() and not raw.is_symlink()
    assert stat.S_IMODE(raw.stat().st_mode) == 0o700


# AC-25 — happy-path writer emits zero "error" events
def test_writer_happy_path_emits_no_error_events(tmp_path):
    with structlog.testing.capture_logs() as captured:
        Writer().write(envelope=ENV, raw_artifacts=[("a.json", b"{}")], output_dir=tmp_path)
    bad = {"writer.symlink.refused", "writer.csafe.unavailable"}
    assert not [r for r in captured if r.get("event") in bad]
```

```python
# tests/unit/test_output_paths.py
from pathlib import Path
import pytest
from codegenie.output.paths import context_dir, raw_dir, yaml_path, runs_dir


@pytest.mark.parametrize("repo", [
    Path("/tmp/repo"), Path("/Users/x/y"), Path("/var/folders/abc"),
    Path("/home/alice/proj"), Path("/root/work"),
])
def test_paths_are_under_codegenie_context(repo):
    base = repo / ".codegenie" / "context"
    assert context_dir(repo) == base
    assert raw_dir(repo) == base / "raw"
    assert yaml_path(repo) == base / "repo-context.yaml"
    assert runs_dir(repo) == base / "runs"


def test_paths_are_pure_no_io(tmp_path):
    # Calling them on a non-existent repo_root must not create anything.
    fake = tmp_path / "does-not-exist"
    _ = context_dir(fake), raw_dir(fake), yaml_path(fake), runs_dir(fake)
    assert not fake.exists()
```

Run all three test files; confirm `ImportError`/`ModuleNotFoundError`/`AttributeError`/`AssertionError` per the red phase. Commit the failing tests.

### Green — make it pass

1. `output/paths.py` — four one-liner helpers.
2. `output/sanitizer.py` — per the Implementation outline above. The single most-likely-to-go-wrong line is the per-call regex compile: keep the alternation order **analyzed-repo-abs first** so longest-prefix-wins falls out naturally (AC-10), and use `re.escape(str(repo_root.resolve()))` (AC-7). The replacement callback distinguishes the four match shapes via `re.Match.group(1)` and applies the right rewrite per AC-9.
3. `output/writer.py` — per the Implementation outline. The `_fix_modes(path)` helper does `os.walk` + `os.chmod`; call it as the **last** step inside `write()`. The `_csafe_warned` guard is a module-level mutable; reset paths for tests use `monkeypatch.setattr(writer_mod, "_csafe_warned", False)`.

Resist adding `gitleaks` synchronously — ADR-0008 §Decision is explicit.

### Refactor — clean up

- Type hints throughout; `mypy --strict src/codegenie/output/` clean with zero `# type: ignore` directives.
- Docstrings on `scrub`, `write`, `SanitizedProbeOutput`, and each `paths.py` helper. Module docstring on `sanitizer.py` cites ADR-0008 + ADR-0010 (single-source pattern); on `writer.py` cites ADR-0008 + ADR-0011.
- Confirm `sanitizer.SECRET_FIELD_PATTERN is coordinator.validator.SECRET_FIELD_PATTERN` (re-export, AC-3) — the AST-scan test fails if this regresses.
- Confirm `_csafe_warned` resets per-process (module load) but not per-call. The once-per-process invariant is the right granularity for the warning's audience (a contributor seeing one warning is informed; three warnings per second is noise).
- Structlog event names registered: `sanitizer.secret.rejected`, `sanitizer.path.rewritten` (DEBUG), `writer.symlink.refused`, `writer.csafe.unavailable`. No other events from these modules.
- Edge case #6: `_fix_modes` walks `output_dir` recursively post-`write()` — AC-22 makes this load-bearing; the refactor pass is just confirming the helper exists and is called.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/output/__init__.py` | New — package marker |
| `src/codegenie/output/sanitizer.py` | New — `OutputSanitizer.scrub`, two-pass per ADR-0008 |
| `src/codegenie/output/writer.py` | New — atomic publish, CSafe fallback, symlink refusal, chmod discipline |
| `src/codegenie/output/paths.py` | New — `<repo>/.codegenie/context/` layout helpers |
| `tests/unit/test_output_sanitizer.py` | New — field parity, depth-N secret rejection, embedded scrub, errors/warnings walk, `re.escape`, longest-prefix, precondition, no-leak invariant, determinism+idempotence, structlog events |
| `tests/unit/test_output_writer.py` | New — atomic ordering + fsync, partial-raw failure, envelope-replace failure, symlink refusal at three paths, filename safety, `_csafe_warned` once-per-process, recursive chmod, empty inputs |
| `tests/unit/test_output_paths.py` | New — pure-function helpers under `<repo>/.codegenie/context/` |

## Out of scope

- **Coordinator dispatch wiring** (calling `scrub` inside `gather()`) — S3-05.
- **`AuditWriter.record` writing run-records** — S3-06.
- **Synchronous `gitleaks`** — explicitly rejected by ADR-0008 §Decision; not added now, not added in Phase 0.
- **Mount-point coverage beyond `/Users`, `/home`, `/root`, `<repo_root>`** — `phase-arch-design.md §Component design` notes `/mnt/...`, `/private/...`, `/srv/...` etc. are deferred to follow-up PRs. The no-leak invariant test (AC-12) only covers the four declared prefixes; widening requires a one-line PR + new test row.
- **Parent-directory fsync after `os.replace`** — Phase 0 accepts POSIX `rename(2)` atomicity without dir-fsync durability. A crash between `os.replace` and the next dirent flush could lose the rename. Acceptable for Phase 0's local POC; revisit in Phase 14 (continuous-gather) if it ever matters.
- **Windows path scrubbing** (`C:\Users\...`, `\\?\` UNC, backslash separators) — Phase 0 is Unix-only per `roadmap.md` Phase 0 scope.
- **Raw-artifact filename collision behavior** — AC-21 rejects `/` in names, so two artifacts with the same leaf name collide trivially; current writer is last-write-wins by `os.replace` semantics, but no AC pins this. Callers must dedupe before passing.
- **Regex tuning / false-positive triage for `SECRET_FIELD_PATTERN`** — owned by S3-02 + ADR-0010 §Tradeoffs.
- **`schema-version.txt` sidecar** — handled by S4-02 (CLI startup writes it; not part of `Writer.write`).
- **Symlink refusal beyond `output_dir`, `output_dir/raw/`, `output_dir/repo-context.yaml`** — symlinked individual raw-artifact destinations (`output_dir/raw/<name>` planted as a symlink) are out of scope; AC-21's filename-safety check + the parent `raw/` symlink check are the load-bearing defenses.

## Notes for the implementer

- **Defense in depth, not redundancy.** Pass-1's secret-name check uses the same `SECRET_FIELD_PATTERN` as `_ProbeOutputValidator` — same regex, two passes (ADR-0008 §Tradeoffs). If a future bug routes around the validator, the sanitizer catches it. Do not "optimize away" the second pass by skipping it when the type signals "already validated"; the signal is in the *type*, the check is the second wall. AC-3's identity check (`is`, not `==`) plus the AST scan forecloses the most common drift: re-defining the regex inline. **There must be exactly one `re.compile` for the secret pattern in the entire `src/codegenie/` tree, and it lives in `coordinator/validator.py`.**
- **Embedded-path scrub is intentional, anchored-prefix scrub is wrong.** The original story's anchored regex (`^(...)`) would have left errors like `"FileNotFoundError: /Users/danny/foo.js"` un-scrubbed because the absolute path is not at the start. Phase 11 commits these YAMLs — the leak compounds. AC-5's non-anchored regex catches embedded occurrences; AC-12's no-leak invariant test is the load-bearing check.
- **`errors` and `warnings` fields are scrubbed, not just `schema_slice`.** Probes emit `errors=["FileNotFoundError: /Users/danny/foo"]` and those land in `repo-context.yaml`. AC-6 makes this explicit; the original story's "every string in `schema_slice`" wording was the most likely real-world leak vector.
- **Username-segment strip, not blank-strip.** When an absolute path is under `/Users/<u>/` but outside `repo_root`, the right rewrite drops `/Users/<u>/` and keeps the rest (`/Users/danny/other-repo/x` → `other-repo/x`). Dropping the *entire* path to `""` loses structural info that audit consumers want; leaking the username compounds the very leak the sanitizer exists to prevent. AC-9 pins this.
- **`re.escape` for `repo_root`** — AC-7's test with `repo.git` (regex metachar `.`) proves the requirement: without `re.escape`, `repoXgit` is over-matched as a sibling-repo escape. Don't string-concatenate; always escape.
- **`yaml.CSafeDumper`** may be unavailable on macOS without libyaml (edge case #13). The fallback is `yaml.SafeDumper` (pure Python). Do **not** fall through to `yaml.Dumper` — that's `forbidden-patterns`-banned by S1-04's lint and unsafe. The lint is the enforcement; this story does not duplicate it.
- **`_csafe_warned` is module-level for once-per-process semantics.** A function-local flag (or no flag at all) emits the warning on every `Writer.write()` call — noise that teaches contributors to ignore the message. AC-15's three-write test pins the right granularity.
- **Recursive chmod tree-walk is the load-bearing edge-case-#6 fix.** Per `actions/cache`-restore-flattens-modes mode (ADR-0011 §Context), only re-chmodding the file just written is insufficient because sibling directories the restore re-materialized stay at `0755`. AC-22's test pre-creates a `0644` file inside `output_dir/raw/` and asserts the next `Writer.write()` re-chmod's it to `0600`. ADR-0011 line 39's wording ("every file and directory it creates") is too narrow — surfaced as an ADR amendment follow-up.
- **`SanitizedProbeOutput` is a *typed signal* that scrubbing ran.** It has the exact field set of `ProbeOutput` (AC-2) but lives in `output/sanitizer.py` and is producible **only** by `OutputSanitizer.scrub`. The coordinator's `_ProbeOutputValidator` returns a `ProbeOutput`; the sanitizer's `scrub` returns the `SanitizedProbeOutput`. **The Writer's signature takes `envelope: dict` (AC-14)**, not `SanitizedProbeOutput` — the envelope is the merged dict produced by the coordinator from many `SanitizedProbeOutput.schema_slice`s. ADR-0008 §Consequences line 46's "Writer takes `SanitizedProbeOutput`" reading is structurally undeliverable because the writer is downstream of an N-to-1 merge; the typed-enforcement *intent* survives at the sanitizer step (only the sanitizer produces the typed signal that flows into the merge). The ADR §Consequences clause should be amended; surfaced as a follow-up.
- **`repo_root` precondition.** AC-11 makes the writer/sanitizer refuse a non-absolute, non-resolved, or `Path("/")` `repo_root`. The CLI guarantees `RepoSnapshot.root` is `.resolve()`d (`phase-arch-design.md §CLI` line 416); this precondition is the second wall, not a redundancy.
- **`repo-context.yaml.invalid`** (the schema-fail variant) is the CLI's job (S4-02), not the Writer's. The Writer always writes `repo-context.yaml`.

## Follow-ups surfaced (not auto-fixed by validator)

1. **ADR-0008 §Consequences line 46** — amend "Writer.write takes a SanitizedProbeOutput" to reflect the merged-envelope reality (AC-14 captures the synthesis-time relaxation).
2. **ADR-0011 line 39** — amend "every file and directory it creates" to "every file and directory in `output_dir`" to match edge case #6's actual requirement (AC-22 captures the broader scope).
3. **High-level-impl.md Step 3 line 111** — the sanitizer test count is undercounted (5 sanitizer tests + 3 paths tests now, not 3); refresh.
