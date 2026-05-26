# Validation report: S2-01 — Bench import-path resolution (`load_task_class`)

**Validated:** 2026-05-26
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S2-01 lands the first concrete entry point of the eval harness's loader subsystem: it resolves `bench/{name}/registration.py` via `sys.path` prep (phase-arch-design.md Gap 2 Option A), triggers `@register_task_class` exactly once, and returns the registered `TaskClass`. As originally written, the story carried the right *shape* — the call site, the Option A decision, the typed-error families — but accumulated 55 findings across four critics: 14 block, ~30 harden, ~11 nit. The dominant themes:

1. **Public-surface contradiction with S1-05.** AC-1's invented phrase `codegenie.eval.__init__`'s loader-internal seam' directly contradicted S1-05's locked 9-name `__all__`. The CLI (per arch line 826) needs `loader.load_task_class(...)` (sub-module path), not a `codegenie.eval` re-export. Rewrote AC-1 to make the sub-module import path canonical and explicitly forbid widening `__all__`. (F-COV-1 / F-CON-3 / F-CON-10.)

2. **Typed-error / exit-code ambiguity.** AC-5 punted: "raise `BenchCaseLoadError` or `TaskClassNotFound` — pick one". The CLI (S4-02) maps typed exceptions to exit codes — without a pinned choice, S4-02 has to re-decide. Per High-level-impl.md Step 4 (`3 task-class not registered, 4 bench dir missing, 6 digest mismatch`), the right split is: missing `registration.py` file → `BenchCaseLoadError` → exit code 4; ran-but-didn't-register → `TaskClassNotFound` → exit code 3; import-time exception → new `TaskClassRegistrationFailed` → exit code 1. Pinned across AC-10, AC-11, AC-12. (F-COV-2 / F-TQ-4 / F-CON-4 / F-DP-3.)

3. **Comment-only TDD stubs.** All five tests in §Red were `# Arrange: ... # Act: ... # Assert: ...` placeholders with no runnable assertions. A `pass`-body `load_task_class` impl would pass every test. Mutation thinking surfaced ~10 surviving mutants per test: hyphen-replace-first-only, `sys.path.append` instead of `insert(0, ...)`, drop the `default_registry.get(name)` step, `importlib.reload` on the second call (counter-in-module-namespace resets silently), and the disjunction-AC ("error type A *or* B") that lets either choice pass. Rewrote every test with concrete `assert` + `pytest.raises` + `pytest.parametrize` + Hypothesis-style property test for the hyphen→underscore translation; externalized the counter to a file outside the imported module. (F-TQ-1 through F-TQ-15.)

4. **Missing edge-case coverage.** No AC for: `name` validation (empty, uppercase, traversal, reserved module names), missing `bench_root`, `registration.py` raising at import time, second call with a *different* `bench_root` for the same `name`, symlinked `bench_root`, relative-vs-absolute path equivalence, `registration.py` registering a *different* slug than expected. Added ACs 3, 4, 7, 11–14 + `BenchRootNotFound`, `InvalidTaskClassName`, `TaskClassRegistrationFailed`, `TaskClassRootConflict` typed errors (additive to S1-01's errors.py).

5. **Design-pattern issues fixable in this story.** `__all__ = ("load_task_class", "load_cases")` placeholder names `load_cases` which doesn't exist yet — breaks `from … import *` and pydoc until S2-02 lands; tightened to single-element tuple (F-DP-2). DI kwarg `registry=None` missing — mirrors `plugins/registry.py:189-202` and S1-03's `register_task_class(..., registry=...)`; added AC-16 (F-DP-4). No structural fence test for ADR-0001's "loader must not import rubric"; added AC-21 with AST-walk via `tests/fence/_phase4_scanner.py`'s `walk_imports` kernel (F-CON-5 / F-DP-9). Caller-frame origin capture + `available_names` from registry-delta — piggy-backs on S1-03's existing `available_names` field, no new error attribute needed (F-DP-8).

6. **Test-isolation gap.** `sys.path` + `sys.modules` are process globals; without a conftest snapshot/restore fixture, tests pollute each other and become order-dependent flake bait. The original story explicitly disclaimed responsibility ("`sys.modules` cleanup is not required"). Pinned AC-22 + autouse `tests/unit/eval/conftest.py` fixture mirroring S1-03's discipline of "tests use fresh `TaskClassRegistry()` for isolation; never mutate `default_registry._by_name` directly". (F-TQ-7 / F-CON-9.)

7. **Doc drift surfaced, not auto-fixed.** Three cross-doc contradictions exposed: (a) `final-design.md` line 186/289 says `import_module("vuln_remediation.registration")` (no `bench.` prefix; stale wording — arch line 1159 says `bench.{name}.registration` per Option A); (b) `phase-arch-design.md` line 1159 calls `bench/` an `__init__.py`-bearing implicit namespace package (PEP 420 explicitly forbids `__init__.py` in implicit namespace packages); (c) `phase-arch-design.md` line 866 claims "registry rejects duplicates" as the no-op mechanism, but S1-03 made the registry RAISE on duplicate — the actual no-op comes from `sys.modules` caching preventing the decorator from firing twice. All three flagged in Validation notes as spawn-task candidates; not auto-edited per Rule 3.

**Design-pattern endorsements (deferred, surfaced in Notes for implementer):** `TaskClassName` newtype (F-DP-1, S1-03 precedent), `slugify_taskclass_name` helper extract (F-DP-5, rule of three not crossed), `LoaderProtocol` (F-DP-7, no third consumer needs a fake loader yet), context-manager `sys.path` shape (F-DP-6, would break AC-6's sys.modules cache dependency). All four explicitly explain *when* to revisit.

**No `NEEDS RESEARCH` items.** Every pattern this story needs is precedented in this repo:
- `src/codegenie/probes/registry.py:139-158` — caller-frame origin capture for collision diagnostics
- `src/codegenie/plugins/registry.py:189-202` — DI `registry=` kwarg pattern
- `src/codegenie/probes/__init__.py` — explicit-imports collection point
- `tests/fence/_phase4_scanner.py:walk_imports` — single AST kernel for fence tests
- S1-03 hardened story — `available_names`, `_origins`, `Final` discipline, monkeypatch isolation
- `tests/static/test_universal_fallback_id_single_source.py` — single-source-of-truth precedent

## Critic reports (condensed)

### Coverage (15 findings: 5 block, 7 harden, 3 nit)

| ID | Severity | Theme |
|---|---|---|
| F-COV-1 | block | AC-1 contradicts S1-05's locked 9-name `__all__` |
| F-COV-2 | block | AC-5 punts typed-error choice; CLI exit-code mapping blocked |
| F-COV-3 | block | No AC for `registration.py` raising during import |
| F-COV-4 | block | No AC pins resolved module's `__file__` |
| F-COV-5 | block | Idempotence undefined for different `bench_root` same name |
| F-COV-6 | block | No `name` validation surface |
| F-COV-7 | harden | No AC for missing/non-dir `bench_root` |
| F-COV-8 | harden | Concurrency contract undefined |
| F-COV-9 | harden | Relative vs absolute `bench_root` equivalence not pinned |
| F-COV-10 | harden | Second call must NOT raise `TaskClassAlreadyRegistered` — not asserted |
| F-COV-11 | harden | "Registered different name" case not covered |
| F-COV-12 | harden | Log-event ACs missing (only in refactor step) |
| F-COV-13 | harden | Typed-error attributes not pinned as machine-readable |
| F-COV-14 | nit | Symlink behavior in notes only, no AC |
| F-COV-15 | nit | AC-2 prose embeds partial-edit artefacts |

### Test-Quality (15 findings: 8 block, 7 harden)

| ID | Severity | Theme |
|---|---|---|
| F-TQ-1 | block | TDD plan tests are comment-only — `pass`-body impl passes every test |
| F-TQ-2 | block | Identity not pinned; `result1 == result2` survives `result1 is result2` |
| F-TQ-3 | block | Hyphen test uses single example; `replace("-", "_", 1)` mutant passes |
| F-TQ-4 | block | AC-5 disjunction lets either error type pass |
| F-TQ-5 | block | `sys.path[0]` index + count not pinned; `append` mutant passes |
| F-TQ-6 | block | `looked_up_in` attribute access not asserted |
| F-TQ-7 | block | No `sys.modules` / `sys.path` teardown between tests |
| F-TQ-8 | block | Different-bench_root case not tested |
| F-TQ-9 | harden | Symlink test missing |
| F-TQ-10 | harden | `registration.py` raising test missing |
| F-TQ-11 | harden | Mutant skipping `default_registry.get(name)` undetected |
| F-TQ-12 | harden | No `TypeError` test for non-str `name` |
| F-TQ-13 | harden | Counter in module namespace silently survives `importlib.reload` |
| F-TQ-14 | harden | Fixture path collision with S3-01 — needs `_bench_factory.py` |
| F-TQ-15 | harden | INTENT test missing (registry-side-effect probe) |

### Consistency (12 findings: 1 block, 8 harden, 3 nit)

| ID | Severity | Theme |
|---|---|---|
| F-CON-3 | block | `loader-internal seam` phrase contradicts S1-05's `__all__` lock |
| F-CON-1 | harden | `final-design.md` line 289 stale wording vs arch Gap 2 Option A |
| F-CON-2 | harden | `phase-arch-design.md` line 1159 internally contradictory (PEP 420) |
| F-CON-4 | harden | Typed-error / CLI exit-code mapping must be pinned |
| F-CON-5 | harden | ADR-0001 compliance in Notes only — needs structural AC |
| F-CON-6 | harden | Idempotence mechanism (`sys.modules` cache, not "registry rejects") |
| F-CON-7 | harden | `Depends on: S1-02` is stale; should be S1-01, S1-03, S1-05 |
| F-CON-8 | harden | Fixture dir naming convention (hyphen, not underscore) |
| F-CON-9 | harden | Test isolation contract missing |
| F-CON-10 | nit | "loader-internal seam" is invented vocabulary |
| F-CON-11 | nit | Failure-path log events unspecified |
| F-CON-12 | nit | `Final` discipline for `default_registry` not surfaced |

### Design-Patterns (13 findings: 2 block, 6 harden, 5 nit)

| ID | Severity | Theme |
|---|---|---|
| F-DP-2 | block | `__all__` placeholder lists undefined `load_cases` |
| F-DP-3 | block | Typed-error choice ambiguity (re: F-COV-2 / F-CON-4) |
| F-DP-4 | harden | DI `registry=` kwarg missing |
| F-DP-5 | harden | `slugify_taskclass_name` deferral needs explicit trigger |
| F-DP-6 | harden | Prepend-and-leave vs context-manager trade-off needs note |
| F-DP-7 | harden | `LoaderProtocol` deferral needs explicit trigger |
| F-DP-8 | harden | `TaskClassNotFound.available_names` from delta — better diagnostic |
| F-DP-9 | harden | Structural fence test for ADR-0001 missing |
| F-DP-1 | nit | `TaskClassName` newtype deferral should be restated here |
| F-DP-10 | nit | `loader.task_class_cache_hit` event missing |
| F-DP-11 | nit | `Path("bench")` default ties loader to CWD |
| F-DP-12 | nit | Functional-core / imperative-shell separation needs explicit endorsement |
| F-DP-13 | nit | "Loader reads, never mutates default_registry" not surfaced |

## Changes applied

The story was rewritten in place. Key changes:

1. **AC list expanded from 9 unnumbered checkboxes to 24 explicit AC-N entries.** Every AC is individually verifiable by attribute access or runnable test assertion.
2. **Original AC-1's ambiguous public-surface seam REPLACED** with explicit sub-module-import path + fence assertion that `__all__` is not widened.
3. **AC-5's typed-error punt RESOLVED** into three distinct typed exits (AC-10, AC-11, AC-12) mapped to CLI exit codes 4, 3, 1.
4. **Four new typed errors added to S1-01 surface (additive)**: `BenchRootNotFound`, `InvalidTaskClassName`, `TaskClassRegistrationFailed`, `TaskClassRootConflict`. Each carries machine-readable named attributes (not just `.args`).
5. **`Depends on` corrected** from `S1-02, S1-03` to `S1-01, S1-03, S1-05` (mirroring S1-03's own correction).
6. **TDD plan rewritten** with concrete runnable Python. Comment-only stubs replaced by ~7 parametrized test functions in two files (`test_loader_import_path.py` + `test_loader_errors.py`), each with explicit `assert` / `pytest.raises` lines.
7. **Test-isolation infrastructure pinned** via AC-22 + new `tests/unit/eval/conftest.py` autouse fixture.
8. **Fixture builder helper** `_bench_factory.py` introduced (replaces hard-coded fixture; reusable by S3-01 per F-TQ-14).
9. **Structural fence test added** for ADR-0001 rubric-isolation (AC-21).
10. **`__all__` placeholder collapsed** to `("load_task_class",)` (F-DP-2 block resolved).
11. **DI `registry=` kwarg added** (AC-16, mirroring `plugins/registry.py:189-202`).
12. **Fixture dir renamed** `stub_task_class/` → `stub-task-class/` (matches the broader convention).
13. **Structured-log event taxonomy** pinned across success + cache-hit + 6 failure paths (AC-19).
14. **Concurrency contract** documented as `caller-serialized` (AC-20).
15. **Doc drift** in `final-design.md` lines 186/289 and `phase-arch-design.md` lines 866, 1159 surfaced for a future doc-sweep (NOT auto-edited per Rule 3).
16. **Out-of-scope expanded** with five explicit deferrals + trigger conditions (`TaskClassName` newtype, slugify helper, `LoaderProtocol`, context-manager sys.path shape, threading lock).
17. **Notes for implementer** restructured to explicitly endorse: PEP 420 (no `__init__.py`), the one-place hyphen→underscore translation, prepend-and-leave sys.path discipline, test-isolation contract, "loader reads, never mutates", `Final[TaskClassRegistry]` discipline, functional-core/imperative-shell split, and the `Path("bench")` default's test-only intent.

Total story length grew from ~125 lines to ~310 lines (incl. concrete TDD examples) — the executor now has ZERO ambiguity to resolve. Acceptance criteria are individually verifiable; the TDD plan would catch every mutant identified by the Test-Quality critic.

## Verdict rationale: HARDENED

- The original story had real but fixable weaknesses (8 of 14 block-level findings traced to ambiguous AC wording or TDD stubs, not structural problems with the goal).
- No critic surfaced a contradiction with the phase's arch / final-design / ADRs that *couldn't* be fixed by tightening the story (the three doc-drift items are stale wording in *other* docs, not in S2-01 itself).
- No `NEEDS RESEARCH` items — every pattern was precedented in this repo.
- After edits, every AC is individually verifiable, the TDD plan provides runnable Python with mutation-resistant assertions, and the prescribed implementation preserves extension-by-addition (a new task class is `bench/<new>/registration.py` + nothing else — loader stays put).

The story is now ready for `phase-story-executor`.
