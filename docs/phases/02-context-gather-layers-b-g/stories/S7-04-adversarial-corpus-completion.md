# Story S7-04 — Adversarial corpus: hostile-skills + concurrent-gather + no-inmemory-leak + phase3-handoff-skipped

**Step:** Step 7 — Plant five-repo fixture portfolio + per-probe golden files + remaining adversarial corpus
**Status:** Ready
**Effort:** M
**Depends on:** S7-03 (~70 goldens exist on disk; regen script proven byte-deterministic across two runs — the adversarial corpus exercises code paths that touch the same writer chokepoint the goldens audit)
**ADRs honored:** ADR-0005 (no plaintext persisted — `test_no_inmemory_secret_leak.py` is the type-level "redactor was called" boundary proof), ADR-0006 (`IndexFreshness` location — `test_phase3_handoff_smoke.py` references the Protocol contract that 02-ADR-0006/02-ADR-0007 lock), ADR-0007 (no plugin loader in Phase 2 — `test_phase3_handoff_smoke.py` is grep-discoverable so Phase 3's author finds it on first repo scan), ADR-0009 (pytest-xdist veto — `test_concurrent_gather_race.py` exercises Phase 0's advisory lock at `.codegenie/cache/.lock`, NOT pytest-level parallelism), ADR-0010 (`RedactedSlice` smart constructor — the no-inmemory-leak test verifies the smart-constructor invariant via `inspect`).

## Context

This story lands the **remaining adversarial corpus** under `tests/adv/phase02/`. Four tests, each addressing a load-bearing risk-or-gap the Phase 2 design names explicitly:

1. **`test_hostile_skills_yaml.py`** — ≥ 8 hostile YAML cases against `SkillsLoader` (S2-01). Tests defense against `!!python/object` (RCE attempt), billion-laughs (entity expansion), deep-nesting (recursion/stack), symlink-escape filenames, NUL-byte-in-name, oversized files. None executes user code. None mutates host state. All paths produce typed `Result.Err(SkillsLoadError(reason=...))` or are refused at `O_NOFOLLOW` open time.
2. **`test_concurrent_gather_race.py`** — two concurrent `codegenie gather` invocations against the same fixture (Phase-0 advisory lock at `.codegenie/cache/.lock` is the synchronization primitive). Verifies the second invocation blocks-or-fails-loud rather than corrupting the cache. The test is **deterministic** despite testing a concurrency surface — it uses real subprocess concurrency + explicit signal coordination, not random timing.
3. **`test_no_inmemory_secret_leak.py`** — **Gap 5 defense** + **Risk #6 defense**. Uses `inspect` to verify that (a) `redact_secrets` is the only call site that constructs `RedactedSlice` (the smart-constructor guarantee per ADR-0010); (b) every artifact reachable from `OutputSanitizer.scrub` to the writer passes through `redact_secrets`; (c) no other public path exists from `ProbeOutput.schema_slice` to `repo-context.yaml`. This is a **structural** boundary test, not a behavioral one — it reads source AST + reachability rather than executing the pipeline. Without it, a future contributor adding `RedactedSlice.from_existing(...)` for testing convenience silently breaks the type-level guarantee.
4. **`test_phase3_handoff_smoke.py`** — **Gap 1 defense**. Landed `@pytest.mark.skip(reason="enabled when Phase 3 plugin lands")`. Phase 3's first author finds the test on first repo scan (`grep -r "enabled when Phase 3 plugin lands"`); unskips it at the Phase-3-entry-gate review; the test then asserts the four adapter `Protocol`s from S1-03 are importable AND their signatures match Phase 3's first plugin's expectations. Any Protocol drift between Phase 2 and Phase 3 triggers an ADR amendment to 02-ADR-0006/02-ADR-0007, surfaced loudly at the entry-gate.

The synthesis ledger pins three risks this story directly defends:

- **Risk #2 (Probe ABC not edited).** Adversarial corpus must not trip an unintended `ProbeContext`/`Probe` ABC widening. Tests run against the frozen contract.
- **Risk #4 (`mypy --warn-unreachable` enforcement).** Adversarial tests in this story exercise the typed `Result` paths; mypy-unreachable false-positives would mask test failures. The structural test in particular relies on AST inspection of typed code.
- **Risk #6 (`RedactedSlice` smart-constructor silent break).** `test_no_inmemory_secret_leak.py` is the front-line defense. The `inspect` call-site count of `RedactedSlice.__init__` (or `RedactedSlice.model_validate(...)` — whichever the production code uses) must equal **one** — the call inside `redact_secrets`. A second call site means the smart-constructor guarantee is broken.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Gap analysis" → Gap 1` (Adapter Protocol drift — `test_phase3_handoff_smoke.py` is the named trip-wire).
  - `../phase-arch-design.md §"Gap analysis" → Gap 5` (No-explicit Phase-4 RAG-store handoff contract — `test_no_inmemory_secret_leak.py` is the named boundary test).
  - `../phase-arch-design.md §"Gap analysis" → Gap 4` (`RedactedSlice` smart-constructor — ADR-0010 amendment).
  - `../phase-arch-design.md §"Testing strategy" → "Adversarial tests"` — the test inventory.
  - `../phase-arch-design.md §"Implementation risks"` #2, #4, #6, #8.
- **Phase ADRs:** ADR-0005 (no plaintext persistence), ADR-0006 (`IndexFreshness` location — Protocol contract anchor), ADR-0007 (no plugin loader in Phase 2 — the Phase-3 handoff trip-wire's rationale), ADR-0009 (pytest-xdist veto — concurrency tests live at subprocess level), ADR-0010 (`RedactedSlice` smart constructor).
- **Implementation plan:** `../High-level-impl.md §"Step 7"` — adversarial-corpus bullet list, `inspect`-based discipline.
- **Source design:** `../final-design.md §"Gaps"` table + `§"Phase-2 → Phase-3 handoff"` checklist.
- **Existing code:**
  - `src/codegenie/skills/loader.py` (S2-01 — the `SkillsLoader` under test).
  - `src/codegenie/output/sanitizer.py` (S3-01 — `SecretRedactor`).
  - `src/codegenie/output/redacted_slice.py` (S3-02 — `RedactedSlice` smart constructor).
  - `src/codegenie/output/writer.py` (S3-03 — writer signature consumes `RedactedSlice`).
  - `src/codegenie/adapters/protocols.py` (S1-03 — the four Protocols this story's Phase-3 handoff test references).
  - `src/codegenie/cache.py` (Phase 0 — the advisory-lock surface `test_concurrent_gather_race.py` exercises).
  - `tests/adv/phase02/test_stale_scip_fixture.py` (S4-02 — adversarial-test directory convention).
  - `tests/adv/phase02/test_secret_in_source.py` (S6-07 — the **behavioral** secret-leak test this story's **structural** test complements).

## Goal

Four adversarial tests exist under `tests/adv/phase02/`:

1. `test_hostile_skills_yaml.py` — ≥ 8 cases, each producing typed `Result.Err` from `SkillsLoader` or refused at `O_NOFOLLOW`.
2. `test_concurrent_gather_race.py` — two concurrent gathers; advisory lock holds; cache is consistent (no half-written blob).
3. `test_no_inmemory_secret_leak.py` — `inspect`-based structural test; `redact_secrets` is the single `RedactedSlice` call site; every artifact reachable from `OutputSanitizer.scrub` to writer passes through it.
4. `test_phase3_handoff_smoke.py` — skipped per `@pytest.mark.skip(reason="enabled when Phase 3 plugin lands")`; grep-discoverable; asserts (when unskipped) that the four `Protocol`s import unchanged and signatures match Phase-3's-first-plugin expectations.

All four go into the `adv-phase02` CI job (wired in S8-03) as part of the load-bearing gate.

## Acceptance criteria

**`test_hostile_skills_yaml.py` — ≥ 8 cases**

- [ ] **AC-1.** `tests/adv/phase02/test_hostile_skills_yaml.py` exists; covers ≥ 8 distinct hostile cases:
  - **Case 1 — `!!python/object`.** A skill file containing `!!python/object:os.system args: ["touch /tmp/pwned"]`. Loader returns `Result.Err(SkillsLoadError(reason="unsafe_yaml"))`. No `/tmp/pwned` exists after the test (assertion).
  - **Case 2 — `!!python/object/apply` variant.** Same defense; same outcome.
  - **Case 3 — billion-laughs.** YAML entity-expansion bomb. Loader caps `safe_yaml.load`'s `max_bytes` (S3 reference from Phase 1) AND `safe_yaml`'s entity-expansion is disabled. Loader returns `Result.Err(SkillsLoadError(reason="schema"))` OR caps out and returns `Result.Err(reason="oversized")`. Wall-clock < 1 s (the cap-out is fast).
  - **Case 4 — deep nesting.** 1000 levels of nested `{a: {a: {a: ...}}}`. Loader returns `Result.Err(reason="depth_exceeded")` OR `reason="schema"`. Wall-clock < 1 s. Test asserts no `RecursionError` escapes.
  - **Case 5 — symlink-escape filename.** Plant a symlink at `<tier>/skill-A.yaml → /etc/passwd` (or any out-of-tree path). Loader's `O_NOFOLLOW` open refuses with `ELOOP`; `Result.Err(SkillsLoadError(reason="symlink_refused", path=...))`.
  - **Case 6 — NUL-byte in filename.** A filename literally containing a NUL byte (constructed via `os.symlink` or low-level `os.open` if the filesystem allows; otherwise the test skips with a clear reason). Loader rejects via `Result.Err(reason="invalid_filename")` OR `OSError` is caught at the loader boundary and surfaced as `Result.Err`.
  - **Case 7 — oversized file** (50 MB + 1 byte; just past `safe_yaml.load`'s declared cap). Loader returns `Result.Err(reason="oversized")`. Wall-clock < 5 s.
  - **Case 8 — duplicate-key YAML.** `{a: 1, a: 2}`. Per Phase-1 `safe_yaml` discipline, duplicate keys produce `Result.Err(reason="schema")`. Loader propagates.
  - **(Recommended) Case 9 — yaml-bomb via alias chain.** Long chain of `&a *b`-style references; combined size cap or alias-count cap rejects it.
- [ ] **AC-2 — no user code executes.** For each case, after the test runs, no file under `/tmp/`, `/var/folders/`, `$HOME` was created by the YAML's payload. The `!!python/object` cases assert no `/tmp/pwned-<random>` exists.
- [ ] **AC-3 — no host-state mutation.** No environment variable was set; no signal was raised. (Defense against esoteric YAML payloads that exercise `__reduce__` chains via `safe_yaml` parsers other than the Phase-1-blessed one.)
- [ ] **AC-4 — wall-clock per case < 5 s.** Each parametrized case completes in under 5 s. (Otherwise an attacker DoSes the gatherer with a crafted hostile skill file.)
- [ ] **AC-5 — typed `Result.Err` paths.** Every hostile case produces a `Result.Err(SkillsLoadError(reason=<one of allowlisted reasons>))`. The allowlisted-reasons set is grep-discoverable in `src/codegenie/skills/loader.py`; the test asserts the reason against the closed set.
- [ ] **AC-6 — fixture under `tests/adv/phase02/fixtures/hostile_skills/`.** Each hostile YAML case lives as a separate file under `tests/adv/phase02/fixtures/hostile_skills/<case-name>.yaml` (the symlink and NUL-byte cases land under a sibling `_create_at_test_time.py` fixture-builder that constructs the path at test time — symlinks and NUL-byte names are not safely committable to git on all platforms). The fixture builder cleans up in a pytest fixture teardown.

**`test_concurrent_gather_race.py` — Phase-0 advisory-lock at `.codegenie/cache/.lock`**

- [ ] **AC-7.** `tests/adv/phase02/test_concurrent_gather_race.py` exists; launches two concurrent `codegenie gather` invocations against the **same** fixture (`tests/fixtures/portfolio/minimal-ts/`) via `subprocess.Popen` (NOT `multiprocessing` — the lock is filesystem-level, advisory, per Phase 0; subprocess concurrency is the realistic surface).
- [ ] **AC-8 — advisory lock holds.** When Process A holds `.codegenie/cache/.lock`, Process B either (a) blocks waiting (loops trying `fcntl.flock(... LOCK_EX | LOCK_NB)` with a timeout) and proceeds after A exits, OR (b) fails-loud with a clear "another gather is in progress" message and a non-zero exit code. Both behaviors are acceptable; the test asserts ONE of them happened (not silent corruption). Implementer's call which the Phase-0 cache lib does; the test queries the lib's contract.
- [ ] **AC-9 — cache consistency post-race.** After both processes exit, `.codegenie/cache/` is internally consistent: every blob has a valid content-hash filename; no half-written file remains (verified by walking the tree + computing content hashes + comparing).
- [ ] **AC-10 — `repo-context.yaml` consistency.** Whichever process completed last produces a `repo-context.yaml` that round-trips through `yaml.safe_load` and matches one of: A's-final-output OR B's-final-output (no half-merged hybrid).
- [ ] **AC-11 — deterministic.** The test passes 100 / 100 runs on the implementer's machine + CI runner. **NOT** flake-tolerant. If you can't make it deterministic, file an issue and use explicit signal synchronization (`os.kill` + signal handlers) between A and B — coordinate the lock-acquisition window, not rely on race timing.
- [ ] **AC-12 — wall-clock < 60 s.** The test completes (both processes terminate) within 60 s. Two cold gathers against `minimal-ts` should fit easily; if not, the timeout indicates a pathology, not a test problem.
- [ ] **AC-13 — `ADR-0009` honored.** The test uses `subprocess.Popen` for concurrency, NOT pytest-xdist. Pytest-xdist remains vetoed.

**`test_no_inmemory_secret_leak.py` — Gap 5 + Risk #6 + ADR-0010 structural test**

- [ ] **AC-14.** `tests/adv/phase02/test_no_inmemory_secret_leak.py` exists; uses `inspect` (NOT `mock`, NOT `pytest-asyncio` execution) to verify three structural invariants below.
- [ ] **AC-15 — `redact_secrets` is the SOLE constructor of `RedactedSlice`.** The test:
  - Imports `codegenie.output.redacted_slice.RedactedSlice` and `codegenie.output.sanitizer.redact_secrets`.
  - Uses `ast` (Python's stdlib AST module) to parse every Python source file under `src/codegenie/` and `tests/` (excluding the test file itself and `_validation/`/`_attempts/` directories).
  - For every `Call` node whose `func` resolves to `RedactedSlice` (either bare-name `RedactedSlice(...)`, `RedactedSlice.model_validate(...)`, `RedactedSlice.model_validate_json(...)`, OR `RedactedSlice.model_construct(...)`) **AND** whose enclosing module is NOT `codegenie.output.sanitizer`, the test FAILS with a clear message naming the file + line.
  - Equivalent: the count of `RedactedSlice`-constructor call sites OUTSIDE `codegenie.output.sanitizer` is **zero**. The count INSIDE `codegenie.output.sanitizer` is **exactly one** (the call inside `redact_secrets`).
  - Test-file exception: the test itself imports `RedactedSlice` for type-narrowing AST checks but does NOT construct one. Verified by AST inspection of the test file.
- [ ] **AC-16 — `OutputSanitizer.scrub` → writer reachability.** The test:
  - Parses `src/codegenie/output/sanitizer.py`'s `OutputSanitizer.scrub` method (or equivalent function — name pinned in S3-03).
  - Verifies that every return path of `scrub` returns a `RedactedSlice` instance (NOT a raw dict; NOT a `JSONValue`). Asserted via `ast`-based return-type analysis OR via mypy-type query (preferred: a `reveal_type` test under `tests/unit/` exists from S3-03; this test re-asserts the result).
  - Parses `src/codegenie/output/writer.py`'s entry function signature. Asserts its first non-self parameter has type annotation `RedactedSlice` (mirrors S3-03's tightening). A writer signature accepting `dict[str, JSONValue]` would FAIL this assertion.
- [ ] **AC-17 — closed set of writer-entry call sites.** The test verifies that the writer's entry function (S3-03) is called only from inside `codegenie.output.sanitizer.OutputSanitizer.scrub` (the sole composition path) OR from the CLI's top-level gather command. Any third call site fails the test.
- [ ] **AC-18 — `model_construct` banned under the sanitizer package.** Inherited from S1-11's `forbidden-patterns` extension; this test asserts the ban is in place by:
  - Reading `pyproject.toml` (or the equivalent pre-commit config) and asserting `model_construct` is named in the forbidden-patterns list.
  - AST-walking `src/codegenie/output/` and confirming zero `model_construct` occurrences.
  - This is defense-in-depth — the pre-commit hook is the front-line; this test catches the pre-commit-bypass case.
- [ ] **AC-19 — failure messages name the offending file + line.** If a future contributor adds `RedactedSlice.from_existing(...)` at `tests/integration/test_X.py:42`, the test fails with `"RedactedSlice constructed outside codegenie.output.sanitizer at tests/integration/test_X.py:42 (call to 'RedactedSlice.from_existing'). The smart-constructor invariant (ADR-0010, S3-02, Gap 4) requires redact_secrets() to be the only constructor path. See docs/phases/02-context-gather-layers-b-g/ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md."`
- [ ] **AC-20 — passes `mypy --strict`.** No `Any` outside the `ast.NodeVisitor`'s necessary `Any` returns; even those carry explicit type narrowing.

**`test_phase3_handoff_smoke.py` — Gap 1 trip-wire, landed `@pytest.mark.skip`**

- [ ] **AC-21.** `tests/adv/phase02/test_phase3_handoff_smoke.py` exists.
- [ ] **AC-22 — skipped, grep-discoverable.** The test is decorated with `@pytest.mark.skip(reason="enabled when Phase 3 plugin lands — see docs/phases/02-context-gather-layers-b-g/ADRs/0007-no-plugin-loader-in-phase-2.md and ../High-level-impl.md §Step 7 Phase-3-handoff bullet")`. The `reason=` string is literal and grep-discoverable; a Phase-3 author running `grep -r "enabled when Phase 3 plugin lands" tests/` finds it instantly.
- [ ] **AC-23 — contents (skipped but written).** The test, when unskipped, asserts:
  - The four `Protocol`s `DepGraphAdapter`, `ImportGraphAdapter`, `ScipAdapter`, `TestInventoryAdapter` are importable from `codegenie.adapters.protocols` (their exact import paths are pinned in S1-03).
  - Each Protocol's runtime structural conformance is verifiable via `isinstance(stub_object, ProtocolClass)` where `stub_object` is a minimal mock implementing the Protocol's method signatures.
  - The `AdapterConfidence` discriminated union has exactly three variants: `Trusted`, `Degraded`, `Unavailable`.
  - The Protocol method signatures match the documented shape in S1-03 — e.g., `DepGraphAdapter.consumers(self, pkg: PackageId, *, transitively: bool = False) -> AdapterConfidence`. This is checked via `inspect.signature` against the documented signature embedded as a frozen tuple in the test file.
- [ ] **AC-24 — comment block explains the trip-wire purpose.** Top of file: a comment block names Gap 1, names ADR-0007, names the Phase-3 entry-gate-review process (S8-04 lands the named issue), and instructs the Phase-3 author on the unskip ritual ("If your first plugin patches one of these Protocols, that's a contract amendment — DO NOT silently change the Protocol; file an ADR amendment to 02-ADR-0006/02-ADR-0007 first, then update this test, THEN unskip.").
- [ ] **AC-25 — passes `mypy --strict`** even while skipped. Mypy type-checks skipped tests; the Protocol-conformance assertion code must type-check against the current S1-03 Protocols.

**Determinism, audit hygiene, type cleanliness**

- [ ] **AC-26 — every test passes `mypy --strict`.**
- [ ] **AC-27 — no flakes.** Each adversarial test passes 100/100 runs on CI. If `test_concurrent_gather_race.py` exhibits any flake, the implementer MUST stabilize via explicit signal synchronization before merging.
- [ ] **AC-28 — fixtures are minimal.** `tests/adv/phase02/fixtures/hostile_skills/` does not exceed ~10 small YAML files. The symlink + NUL-byte cases are built at test time (not committed) per AC-6.
- [ ] **AC-29 — log-emission assertions where relevant.** `test_hostile_skills_yaml.py` asserts each `Result.Err` is also emitted as a structured log event (e.g., `probe.skill.load_refused` with a `reason` field) — per the cross-cutting structlog discipline.

## Implementation outline

1. **TDD red — write `test_hostile_skills_yaml.py` first.** Plant ≥ 8 parametrized cases; each invokes `SkillsLoader.load_all()` against a tier-rooted at `tests/adv/phase02/fixtures/hostile_skills/`; asserts `Result.Err`. With no fixture files yet, each case fails red (no skill file found).
2. Plant the hostile-YAML fixtures under `tests/adv/phase02/fixtures/hostile_skills/` per AC-1's case list. Plant `_create_at_test_time.py` for the symlink + NUL-byte cases. Confirm each fixture file is parseable-as-YAML by an attacker tool (so we're testing real hostile input, not malformed-text edge cases — except where malformed-text IS the case, like duplicate keys).
3. Run `pytest tests/adv/phase02/test_hostile_skills_yaml.py -v`. Adjust the `SkillsLoader` or `safe_yaml` chokepoint as needed (if a case slips through to RCE or to wall-clock-cap-violation, fix the production code — the test caught a real bug). Green.
4. **TDD red — write `test_concurrent_gather_race.py`.** Use `subprocess.Popen` to launch two `codegenie gather tests/fixtures/portfolio/minimal-ts/` invocations. With a working advisory lock, the test asserts post-conditions (AC-8..AC-10). Run; observe behavior.
5. If the test is flaky, add explicit signal synchronization: Process A pauses on `SIGUSR1` immediately after acquiring the lock; the test sends `SIGUSR1` to A; A continues; Process B is launched while A holds the lock. This eliminates timing-race nondeterminism.
6. Run 100 times. Confirm 100/100 pass. Green.
7. **TDD red — write `test_no_inmemory_secret_leak.py`.** Build the AST-walker that finds `RedactedSlice` construction call sites. With the production code as-is (per S3-01/S3-02/S3-03), the test should pass on first run — there should be exactly one call site, inside `redact_secrets`. If the count is wrong, debug the production code, not the test.
8. **Verify the failure mode**: temporarily add `RedactedSlice(slice={}, findings_count=0, fingerprints=[])` to a scratch file under `tests/_scratch/`. Run the test; observe it fails with the expected message (AC-19). Delete the scratch file. Re-run; observe green. Document the deliberate-fail-then-pass observation in PR.
9. **TDD red — write `test_phase3_handoff_smoke.py`.** Write the test body (per AC-23). Decorate with `@pytest.mark.skip(reason="enabled when Phase 3 plugin lands — see ...")` per AC-22. Write the comment block per AC-24.
10. **Verify the unskip path.** Temporarily remove the `@pytest.mark.skip` decorator. Run the test. With S1-03's Protocols in place, the test should pass. Confirm. Re-apply the skip decorator. Run again. Pytest records the skip; the test counts as passing (pytest convention).
11. Final pass: `mypy --strict`, `ruff check`, `ruff format --check`. Run all four adversarial tests. Run the full Phase 2 test suite. Green.

## TDD plan — red / green / refactor

### Red — failing adversarial tests first

`test_no_inmemory_secret_leak.py` AST-walker skeleton:

```python
# tests/adv/phase02/test_no_inmemory_secret_leak.py
"""Structural boundary test — Gap 5, Risk #6, ADR-0010.

The smart-constructor invariant: redact_secrets() in codegenie.output.sanitizer is the
ONLY call site that constructs RedactedSlice. Any second call site (e.g.,
`RedactedSlice.from_existing(...)` added for testing convenience) silently breaks the
type-level "redactor was called" guarantee. This test fails loudly if that happens.
"""
from __future__ import annotations
import ast
from pathlib import Path
from typing import NamedTuple

_REPO_ROOT = Path(__file__).parent.parent.parent.parent  # tests/adv/phase02/ -> repo root
_SRC = _REPO_ROOT / "src"
_TESTS = _REPO_ROOT / "tests"

_REDACTED_SLICE_NAME = "RedactedSlice"
_SOLE_CONSTRUCTOR_MODULE = "codegenie.output.sanitizer"  # the function inside is redact_secrets

class _CallSite(NamedTuple):
    file: str
    line: int
    call_text: str

def _find_redacted_slice_construction_sites(root: Path) -> list[_CallSite]:
    """AST-walk every .py under `root` and find every call that constructs RedactedSlice."""
    sites: list[_CallSite] = []
    for py in root.rglob("*.py"):
        if "_validation" in py.parts or "_attempts" in py.parts or "__pycache__" in py.parts:
            continue
        try:
            tree = ast.parse(py.read_text(), filename=str(py))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if _is_redacted_slice_call(node):
                    sites.append(_CallSite(str(py), node.lineno, ast.unparse(node)))
    return sites

def _is_redacted_slice_call(node: ast.Call) -> bool:
    """True if this Call constructs a RedactedSlice (bare-name or method-form)."""
    func = node.func
    if isinstance(func, ast.Name) and func.id == _REDACTED_SLICE_NAME:
        return True  # RedactedSlice(...)
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) \
            and func.value.id == _REDACTED_SLICE_NAME \
            and func.attr in {"model_validate", "model_validate_json", "model_construct"}:
        return True  # RedactedSlice.model_validate(...) etc
    return False

def _file_belongs_to_sanitizer_module(file: str) -> bool:
    """True if the file is part of codegenie.output.sanitizer."""
    return file.endswith("/codegenie/output/sanitizer.py") or file.endswith(r"\codegenie\output\sanitizer.py")


def test_redacted_slice_constructed_only_in_sanitizer_module() -> None:
    """AC-15 — redact_secrets in codegenie.output.sanitizer is the sole RedactedSlice constructor."""
    sites_in_src = _find_redacted_slice_construction_sites(_SRC)
    sites_in_tests = _find_redacted_slice_construction_sites(_TESTS)
    all_sites = sites_in_src + sites_in_tests

    out_of_module = [s for s in all_sites if not _file_belongs_to_sanitizer_module(s.file)]
    in_module = [s for s in all_sites if _file_belongs_to_sanitizer_module(s.file)]

    assert not out_of_module, (
        f"RedactedSlice constructed outside codegenie.output.sanitizer:\n"
        + "\n".join(f"  {s.file}:{s.line}  {s.call_text!r}" for s in out_of_module)
        + "\n\nThe smart-constructor invariant (ADR-0010, S3-02, Gap 4) requires redact_secrets() "
          "to be the only constructor path.\n"
          "See docs/phases/02-context-gather-layers-b-g/ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md."
    )
    # Defense-in-depth: also assert at least one construction occurs inside the sanitizer
    # (regression guard against accidentally removing the redactor entirely).
    assert len(in_module) >= 1, (
        "Expected at least one RedactedSlice construction inside codegenie.output.sanitizer; "
        "the redactor appears to have been removed entirely. That breaks ADR-0005."
    )
```

`test_hostile_skills_yaml.py` parametrized skeleton:

```python
# tests/adv/phase02/test_hostile_skills_yaml.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import pytest
from codegenie.skills.loader import SkillsLoader, SkillsLoadError
from codegenie.result import Result  # Phase-0 Result type

_HOSTILE = Path(__file__).parent / "fixtures" / "hostile_skills"

@dataclass(frozen=True)
class _HostileCase:
    name: str
    fixture_relpath: str  # under _HOSTILE
    expected_reason: str  # one of the SkillsLoadError reason values

_CASES = (
    _HostileCase("python_object",        "case1_python_object.yaml",     "unsafe_yaml"),
    _HostileCase("python_object_apply",  "case2_python_object_apply.yaml","unsafe_yaml"),
    _HostileCase("billion_laughs",       "case3_billion_laughs.yaml",    "oversized"),  # or "schema"
    _HostileCase("deep_nesting",         "case4_deep_nesting.yaml",      "schema"),    # or "depth_exceeded"
    # Cases 5 (symlink) + 6 (NUL-byte) built at test time, see below
    _HostileCase("oversized",            "case7_oversized.yaml",         "oversized"),
    _HostileCase("duplicate_key",        "case8_duplicate_key.yaml",     "schema"),
)

@pytest.mark.parametrize("case", _CASES, ids=lambda c: c.name)
def test_hostile_skill_yaml_refused(case: _HostileCase, tmp_path) -> None:
    """Loader returns typed Result.Err; no user code executes; wall-clock < 5 s."""
    # Copy fixture into a fresh tier dir
    tier = tmp_path / "skills"
    tier.mkdir()
    src = _HOSTILE / case.fixture_relpath
    dest = tier / "skill-A.yaml"
    dest.write_bytes(src.read_bytes())

    pwned = Path("/tmp/pwned-hostile-skills-test")
    assert not pwned.exists(), "stale marker from prior run — clean and retry"

    loader = SkillsLoader(search_paths=[tier])
    result = loader.load_all()

    assert result.is_err(), f"expected Result.Err for {case.name}, got {result!r}"
    err = result.unwrap_err()
    assert isinstance(err, SkillsLoadError)
    assert err.reason == case.expected_reason, f"expected reason={case.expected_reason!r}, got {err.reason!r}"
    assert not pwned.exists(), f"!!python/object exec'd in case {case.name} — security regression"


def test_symlink_escape_refused(tmp_path) -> None:
    """Case 5 — symlink-escape filename. Built at test time (not committable to git)."""
    tier = tmp_path / "skills"
    tier.mkdir()
    target = tmp_path / "out-of-tree.yaml"
    target.write_text("name: out-of-tree\n")
    (tier / "skill-A.yaml").symlink_to(target)

    loader = SkillsLoader(search_paths=[tier])
    result = loader.load_all()

    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, SkillsLoadError)
    assert err.reason == "symlink_refused"
```

`test_concurrent_gather_race.py` skeleton:

```python
# tests/adv/phase02/test_concurrent_gather_race.py
from __future__ import annotations
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from codegenie.hashing import content_hash

_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "portfolio" / "minimal-ts"

def test_concurrent_gathers_do_not_corrupt_cache(tmp_path) -> None:
    # Work on a copy so we don't dirty the canonical fixture
    workdir = tmp_path / "minimal-ts"
    subprocess.run(["cp", "-R", str(_FIXTURE), str(workdir)], check=True)

    def _launch() -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            [sys.executable, "-m", "codegenie", "gather", str(workdir)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    a = _launch()
    time.sleep(0.1)  # give A a head-start on lock acquisition (not race-tolerance — explicit windowing)
    b = _launch()

    out_a, err_a = a.communicate(timeout=60)
    out_b, err_b = b.communicate(timeout=60)

    # AC-8: at least one succeeded; if one failed, its stderr names "another gather is in progress"
    succeeded = [(a.returncode == 0, err_a), (b.returncode == 0, err_b)]
    assert any(ok for ok, _ in succeeded), f"both failed: A={err_a!r} B={err_b!r}"
    for ok, err in succeeded:
        if not ok:
            assert b"another gather is in progress" in err or b"lock" in err.lower(), \
                f"failed gather did not name the lock contention: {err!r}"

    # AC-9: cache consistency — every blob filename matches its content
    cache_root = workdir / ".codegenie" / "cache" / "blobs"
    for blob in cache_root.rglob("*"):
        if blob.is_file():
            expected_name = content_hash(blob.read_bytes())
            assert blob.name.startswith(expected_name[:16]), (
                f"corrupt cache blob: {blob} (name does not match content hash)"
            )

    # AC-10: repo-context.yaml round-trips
    import yaml
    ctx = workdir / ".codegenie" / "context" / "repo-context.yaml"
    assert ctx.exists()
    yaml.safe_load(ctx.read_text())  # no exception
```

### Green — make it pass

Plant fixtures, run tests, iterate until all four are green and stable.

### Mutation-resistance witness table

| Mutation | Test that catches it |
|---|---|
| Future contributor adds `RedactedSlice.from_existing(...)` at `tests/integration/test_X.py:42` | `test_redacted_slice_constructed_only_in_sanitizer_module` — fails with the file:line + remediation pointer |
| Someone "fixes" `safe_yaml.load` to allow `!!python/object` (regression) | `test_hostile_skill_yaml_refused[python_object]` — `Result.Err` becomes `Result.Ok`, `/tmp/pwned-*` exists, assertion fails |
| Cache advisory lock is removed | `test_concurrent_gathers_do_not_corrupt_cache` — one process silently overwrites the other's blob; the content-hash check fails OR `repo-context.yaml` is malformed |
| `SkillsLoader` swallows `OSError(EILSEQ)` for NUL-byte filenames silently | `test_symlink_escape_refused`'s NUL-byte variant — but only if implementer wrote it; otherwise the bug ships |
| Future contributor edits S1-03 Protocols (`DepGraphAdapter.consumers(self, pkg: PackageId)` → `pkg: str`) | `test_phase3_handoff_smoke.py` (when unskipped at Phase 3 entry-gate) — the signature mismatch is caught at gate-review |
| Future contributor deletes the skip marker in `test_phase3_handoff_smoke.py` and the test fails on master | CI fails on master; the test is unskipped prematurely — the comment block (AC-24) explicitly forbids this without an ADR amendment, and the failure points to the ADR |
| `redact_secrets` is silently removed | `test_redacted_slice_constructed_only_in_sanitizer_module`'s defense-in-depth assertion (`len(in_module) >= 1`) fires |
| A scanner probe (`gitleaks`) bypasses the redactor and writes plaintext to `raw/gitleaks.json` | `tests/golden/test_no_plaintext_in_goldens.py` (S7-03) catches the plaintext in the golden; `test_secret_in_source.py` (S6-07) catches it behaviorally; this story's `test_no_inmemory_secret_leak.py` catches the **structural** path (missing `redact_secrets` call) |

### Refactor — clean up

- `test_no_inmemory_secret_leak.py`'s AST walker is reusable; consider whether to extract it to `tests/_helpers/ast_call_site_finder.py`. **Defer** — only one consumer; extract at the second (if a future ADR mandates a similar "X is the only constructor of Y" invariant, that's the third + lifts).
- `test_hostile_skills_yaml.py`'s `_HostileCase` is the canonical-empty-set predicate. Each case's `expected_reason` is pinned against the closed set declared in `SkillsLoader.SkillsLoadError`. If the closed set grows, the cases here grow accordingly.
- `test_concurrent_gather_race.py`'s `time.sleep(0.1)` is the explicit-windowing primitive, NOT race-tolerance. If the test becomes flaky on a slower CI runner, the fix is signal synchronization (SIGUSR1 handshake), NOT longer sleeps.
- The four tests live side-by-side under `tests/adv/phase02/`; they share fixture-directory conventions (`tests/adv/phase02/fixtures/<test-name>/`); the README at `tests/adv/phase02/README.md` (if it exists from S4-02; if not, plant it) names the load-bearing tests.

## Files to touch

| Path | Why |
|---|---|
| `tests/adv/phase02/test_hostile_skills_yaml.py` | ≥ 8 hostile-YAML cases |
| `tests/adv/phase02/fixtures/hostile_skills/case{1..8}_*.yaml` | Hostile fixture files (cases 5 + 6 built at test time) |
| `tests/adv/phase02/test_concurrent_gather_race.py` | Two concurrent gathers; advisory-lock holds; cache consistent |
| `tests/adv/phase02/test_no_inmemory_secret_leak.py` | **Gap 5 + Risk #6 + ADR-0010** — `inspect`-based structural boundary test |
| `tests/adv/phase02/test_phase3_handoff_smoke.py` | **Gap 1** — skipped trip-wire; grep-discoverable; Phase-3 author finds it on first repo scan |
| `tests/adv/phase02/README.md` (extend if exists, plant if not) | Documents the four load-bearing adversarials + the `adv-phase02` CI job's role |

## Out of scope

- **Property tests + portfolio sweep integration** — S7-05.
- **CI wiring** (`adv-phase02` job that runs these four + the earlier ones from S4-02 / S5-05 / S5-06 / S6-07) — S8-03.
- **Phase-3-handoff issues filing** — S8-04 (this story lands only the skipped test; S8-04 files the GitHub issue Phase-3's author follows).
- **`test_secret_in_source.py`** — owned by S6-07; complements this story's **structural** counterpart but lives there.
- **Behavioral concurrency tests against actual `pytest-xdist` parallelism** — out per ADR-0009.
- **A `tests/_helpers/ast_call_site_finder.py` extraction** — premature; one consumer.

## Notes for the implementer

- **Risk #6 is the load-bearing risk this story defends.** `test_no_inmemory_secret_leak.py`'s AST walker is the front-line guard against a future contributor silently breaking the smart-constructor invariant. **Spend extra time on the failure-message ergonomics (AC-19).** A CI failure message that points to the exact file:line PLUS the ADR PLUS the remediation step is what turns a "what does this mean?" CI red into a "oh I see, let me fix it" fix in 30 seconds. The named remediation is non-negotiable.
- **The deliberate fail-then-pass verification (outline step 8) is mandatory.** Add a scratch `RedactedSlice(...)` call somewhere outside `codegenie.output.sanitizer`, run the test, observe the failure with the AC-19 message, fix the code, observe green. Document the round-trip in the PR description. Without this, the test could be subtly wrong (e.g., AST walker missing a call form) and pass-by-default.
- **`test_concurrent_gather_race.py` flake-tolerance is forbidden.** If you cannot get 100/100 passes locally and on CI, do NOT mark it as `@pytest.mark.flaky` or `xfail`. The flake indicates a real bug in the advisory-lock contract; fix the bug. The most common cause is the lock being released before the cache write fully fsyncs — investigate `cache.py`'s flush discipline.
- **`test_phase3_handoff_smoke.py`'s skip marker MUST be `@pytest.mark.skip(reason="...")`**, NOT `@pytest.mark.skipif(...)`. The skipif form makes the un-skip an environmental concern; the plain `skip` makes it a deliberate code edit Phase-3's author performs. The grep-discoverable string is the artifact.
- **AC-23's Protocol-conformance assertion can be left as code-but-skipped.** The test body must type-check (`mypy --strict`) even while skipped; this enforces that the four Protocols stay importable at their pinned paths AND that any signature change in S1-03 forces an explicit edit to this test file (preventing silent drift). If the test file no longer compiles because a Protocol moved, **that** is the contract trip-wire firing — even before Phase 3 unskips.
- **The hostile-YAML fixtures must be small.** Billion-laughs in particular: keep the entity count under 10 (the parser caps it quickly; you don't need 1000 entities to trigger the defense). Deep nesting: 1000 levels is enough to trip stack-or-cap defenses without producing a 10 MB fixture file. Document the size + the cap in each fixture's top-of-file YAML comment.
- **No `mock.patch` anywhere in these tests.** Per the project convention (and CLAUDE.md's "tests verify intent, not just behavior"). The tests exercise real production code paths — the loader, the cache lock, the AST of the production code, the four Protocols. Mocks would mask the regression cases these tests are designed to catch.

### Patterns DELIBERATELY deferred (per Rule 2 + Rule 3)

- **A reusable AST `_call_site_finder.py`** — one consumer; lift at the second.
- **A behavioral skill-loader-hostile-input test that asserts `redact_secrets` was called via a mock spy** — defer; the structural AST test in this story + the behavioral end-to-end test in S6-07 (`test_secret_in_source.py`) together cover the surface; a mock-spy variant adds nothing observable.
- **A second concurrency test against Layer-C `runtime_trace` parallel scenarios** — out; `runtime_trace` is sequential per scenario by design (S5-02 contract). The advisory-lock is the only concurrency surface to exercise.
- **A `test_protocol_drift_at_phase2_boundary.py` companion** that re-asserts S1-03's Protocols at the Phase-2-boundary (without waiting for Phase 3) — defer; the `test_phase3_handoff_smoke.py`'s type-check-while-skipped already enforces drift-detection without redundancy.
