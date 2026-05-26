# Validation report: S2-02 — Loader: `load_cases` + BLAKE3 digests + case-id collision

**Validated:** 2026-05-26
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S2-02 is the **integrity gate** for the bench corpus: walks `bench/{tc}/cases/<case-id>/case.toml`, parses each into a `BenchCase`, content-hash-verifies every case dir against `cases/digests.yaml`, surfaces collisions, and returns a deterministically sorted tuple. The original story carried the right *shape* (the references, the typed errors, ADR-0005 identity-not-content semantics) but accumulated 32 findings across four critics: 4 block, 18 harden, 10 nit. The dominant themes:

1. **Wrong hashing primitive — silent regression of Scenario 2.** The Notes-for-implementer instructed *"Reuse `codegenie.hashing.content_hash_of_inputs`"*. That helper hashes a `(path, st_size)` manifest only ([src/codegenie/hashing.py:194-211](../../../../../src/codegenie/hashing.py#L194)), not file contents. A byte-edit inside `expected/diff.patch` that preserves file size — the exact attack described by `phase-arch-design.md §Scenario 2` — would have **silently passed** the digest check, defeating the entire reason the digest exists. Pinned the content-sensitive composition in AC-3: `rglob` regular files (minus `case.toml`), per-file `content_hash(p)`, canonical record stream `f"{rel}\x1f{per_file}".encode()` joined by `\x1e`, BLAKE3 over the joined bytes. Added a structural fence test (AC-13) AST-walking `loader.py` for forbidden references to `content_hash_of_inputs` or direct `blake3` imports — mutation-resistant against future refactors.

2. **Shallow walk against a real directory shape.** Implementation outline said `Path.iterdir()` — but `BenchCase.input_path: Path` and `expected_path: Path` (arch-design §Data model lines 769–770) point at sub-directories like `input/`, `expected/`. A shallow walk would hash zero files for a real case. Pinned `rglob("*")` filtered to `is_file() and not is_symlink()` (AC-3b).

3. **Missing edge-case coverage.** No AC covered (a) missing `input/` directory — explicitly listed as arch Edge #1, mapped to `BenchCaseLoadError(case_dir, "input/ not found")`; (b) `digests.yaml` schema (non-mapping root, wrong prefix, uppercase hex, length errors, YAML syntax errors); (c) `digests.yaml` ↔ filesystem completeness (extra entries / missing entries); (d) symlink escape (a `cases/X/evil-link -> /etc/passwd` would be traversed by `rglob` and read by `content_hash`); (e) `cases/` directory entirely missing; (f) zero-case directories; (g) `input_path` / `expected_path` traversal beyond the case dir; (h) `case.toml` UTF-8 / TOML parse errors. Added ACs 5, 6a, 6b, 9, 11, 12, 4 + parametrized tests for each.

4. **Comment-only TDD stubs.** All nine `# Arrange / # Assert` placeholders mirrored the S2-01 anti-pattern: a `pass`-body `load_cases` impl would pass every test. Rewrote each test as runnable Python with concrete `pytest.raises(BenchCaseDigestMismatch) as exc_info: ... exc_info.value.case_id == "case-1"; exc_info.value.expected != exc_info.value.computed`. Added a Hypothesis property test for the sort invariant (AC-17), pinning N case_ids drawn from a slug regex, scaffolding them in random shuffle order, asserting lexicographic return order — kills the "swap `sorted(...)` → `list(...)`" mutant that the 3-case fixture might miss on certain platforms.

5. **`structlog` capture wrong fixture.** Original test asserted `caplog captured 'loader.case_stale' warn event` — but `caplog` is for stdlib `logging`. This codebase uses `structlog` (e.g., `tests/unit/parsers/test_safe_yaml.py:32`, `tests/unit/test_audit_anchors.py:172`). Rewrote with `with structlog.testing.capture_logs() as logs:`. Also strengthened: parametrized at `days_back ∈ {89, 90, 91, 365}` to pin the `> 90` boundary (a faulty `>= 90` would slip past a single-value test).

6. **Failure ordering left implicit.** When two defects exist simultaneously (e.g., collision + digest mismatch), the original story didn't say which fires first. The deterministic order matters because the typed error the CLI sees → the exit code → the operator's diagnostic. Pinned the firing order in AC-10: cheap structural checks first (cases-dir existence → digests.yaml parse → case.toml parse → case_id-vs-dir → collision → input/ → symlink), expensive content compute last (digest). Added a positive test: build a fixture with BOTH a collision AND a poisoned byte, assert `BenchCaseIDCollision` raises (not `BenchCaseDigestMismatch`).

7. **`last_validated_at` type confusion.** Story said *"parse with `datetime.fromisoformat` then call `.date()`"* — but `BenchCase.last_validated_at: datetime` (arch line 768) and Pydantic already does the parsing. The loader just needs `(date.today() - case.last_validated_at.date()).days > 90`. Removed the redundant parsing instruction.

8. **Surface conflict between docs (surfaced, not auto-fixed).** `final-design.md §Failure modes` line 316 says `case.toml` malformed → exclude-and-continue (exit code 1, `had_load_errors=True`). The newer `phase-arch-design.md §Edge cases #2 line 945` + `§Control flow §Decision point #6 line 835` + Scenario 2 sequence diagram all say abort fail-fast (exit code 6). Story follows arch (consistent + more recent + self-consistent in the sequence diagrams). Flagged for a follow-on doc-sweep PR; not auto-edited (Rule 3 — surgical changes).

**Design-pattern endorsements (deferred, surfaced in Notes for implementer):** `CaseDigestStrategy` Protocol / registry (F-DP-2 — rule-of-three not crossed; the fence test is the structural lock); `CaseId` / `BlakeHex` newtypes (F-DP-3 — phase-wide identifier work deferred); DI seam for `digests.yaml` loader (F-DP-4 — one caller; private helper is sufficient). The `_DIGEST_EXCLUDED_FILENAMES: Final[frozenset[str]]` constant IS adopted as a module-level Open/Closed seam, but NOT promoted to AC (Rule 2 — one excluded name today; data-driven extension is sufficient).

**No `NEEDS RESEARCH` items.** Every pattern this story needs is precedented in this repo:
- [src/codegenie/hashing.py:54](../../../../../src/codegenie/hashing.py#L54) — `content_hash` (the right primitive for per-file BLAKE3 of content)
- [src/codegenie/hashing.py:194](../../../../../src/codegenie/hashing.py#L194) — `content_hash_of_inputs` (path+size only; explicitly NOT to be used — fence-guarded)
- [tests/unit/parsers/test_safe_yaml.py:32](../../../../../tests/unit/parsers/test_safe_yaml.py#L32), [tests/unit/test_audit_anchors.py:172](../../../../../tests/unit/test_audit_anchors.py#L172) — `structlog.testing.capture_logs()` canonical fixture
- [src/codegenie/probes/deployment.py:183-193](../../../../../src/codegenie/probes/deployment.py#L183) — `resolved.is_relative_to(root_resolved)` symlink-escape detection
- [src/codegenie/probes/language_detection.py:291](../../../../../src/codegenie/probes/language_detection.py#L291) — `entry.is_symlink()` filesystem-walk hygiene
- S2-01 conftest at `tests/unit/eval/conftest.py` — autouse `sys.path`/`sys.modules`/`default_registry` snapshot/restore (reused, not duplicated)
- S1-02 — Hypothesis property test precedent for digest regex coverage
- `tests/fence/_phase4_scanner.py:walk_imports` — AST-walk kernel for fence tests (reuse for AC-13)

## Critic reports (condensed)

### Coverage (10 findings: 4 block, 5 harden, 1 nit)

| ID | Severity | Theme | Resolution |
|---|---|---|---|
| F-COV-1 | block | `content_hash_of_inputs` wrong primitive — same-size byte flip silently passes Scenario 2 | Pinned AC-3 canonical composition over `content_hash` (per-file); fence AC-13 |
| F-COV-2 | block | `iterdir()` shallow walk vs real `input/`, `expected/` subdirs | Pinned `rglob("*")` in AC-3a |
| F-COV-3 | block | Arch Edge #1 (`input/` missing) not in TDD plan | Added AC-5 + parametrized test |
| F-COV-4 | block | `input_path` / `expected_path` BenchCase fields silently ignored | Added AC-4 (traversal guard via `is_relative_to`) |
| F-COV-5 | harden | Symlink-escape unguarded | Added AC-9 + 4-variant parametrized test (outside, inside, dir, broken) |
| F-COV-6 | harden | `digests.yaml` schema unguarded (wrong prefix, length, uppercase, syntax, non-mapping root, extra/missing entries) | Added AC-6a + AC-6b + 6-variant parametrized test |
| F-COV-7 | harden | Failure ordering ambiguous when multiple defects fire | Added AC-10 (deterministic order spec) + ordering test |
| F-COV-8 | harden | Zero-case directory / `cases/` dir missing | Added AC-11 (empty tuple + warn) + AC for cases-dir-missing |
| F-COV-9 | harden | `case.toml` parse edge cases (UTF-8, TOML syntax) | Added AC-12 |
| F-COV-10 | nit | `cassette_path` validation scope unclear | Out-of-scope (loader is fact-not-judgment; Phase 4 owns) |

### Test Quality (12 findings: 0 block, 9 harden, 3 nit)

| ID | Severity | Theme | Resolution |
|---|---|---|---|
| F-TQ-1 | harden | Notes prescribed `content_hash_of_inputs` — mutation surface | Mutation-locked via AC-13 fence; AC-3 spells out correct primitive |
| F-TQ-2 | harden | `caplog` is wrong fixture for structlog | Rewrote AC-8/AC-15 tests to use `structlog.testing.capture_logs()` |
| F-TQ-3 | harden | All 9 TDD stubs comment-only — `pass`-body impl passes them | Rewrote every test with concrete asserts + `pytest.raises(...) as exc_info` + attribute checks |
| F-TQ-4 | harden | Disjunction-ACs ("flip a byte... assert mismatch") could be satisfied by `if random(): raise Mismatch` | Pinned: `expected.startswith("blake3:"); expected != computed` |
| F-TQ-5 | harden | No mutation test for sort order — 3-case fixture might be fs-sorted on dev box | Added Hypothesis property test AC-17 |
| F-TQ-6 | harden | Stale-case test has only one `days = 100` value — `>= 90` mutant slips | Parametrized over `{89, 90, 91, 365}` pinning `> 90` boundary |
| F-TQ-7 | harden | "Identity not content" test was a side note, not a verifiable claim | Promoted to AC-14 with concrete asserted property |
| F-TQ-8 | harden | Collision test didn't pin sort order of `paths` tuple | Added `assert tuple(exc_info.value.paths) == tuple(sorted(...))` |
| F-TQ-9 | harden | No assertion that idempotent calls don't grow `sys.path` | Added AC-18 + side-effect snapshot test |
| F-TQ-10 | nit | Test file path naming convention | Pinned `tests/unit/eval/test_loader_cases_and_digests.py` |
| F-TQ-11 | nit | Fixture-builder API undefined | Pinned `make_case(...)` + `tmp_bench(...)` shape |
| F-TQ-12 | nit | Hypothesis case_id charset undefined | Pinned `r"^[a-z0-9][a-z0-9-]{1,20}[a-z0-9]$"` slug regex |

### Consistency (6 findings: 0 block, 5 harden, 1 nit)

| ID | Severity | Theme | Resolution |
|---|---|---|---|
| F-CON-1 | harden | Notes told implementer to use the WRONG hashing primitive — would silently regress Scenario 2 | Rewrote Notes to make `content_hash` the canonical primitive; AC-13 makes it structural |
| F-CON-2 | harden | `last_validated_at` parsing — Pydantic already does it, loader should not re-parse | Removed `datetime.fromisoformat` from Notes; pinned `.date()`-based comparison |
| F-CON-3 | harden | ADR-0005 identity-not-content semantics implicit | Promoted to AC-14 (verifiable assertion) |
| F-CON-4 | harden | Doc drift: final-design says exclude-and-continue; arch says abort | Story aligns with arch (correct). Surfaced in Validation notes for doc-sweep follow-on; not auto-edited (Rule 3) |
| F-CON-5 | harden | `cassette_path` existence-check ownership ambiguous | Out-of-scope; Phase 4 cassette layer owns resolution at SUT-invocation time |
| F-CON-6 | nit | `BenchCase.case_digest` validator from S1-02 — confirm loader doesn't re-validate | Documented in Notes-for-implementer |

### Design Patterns (4 findings: 0 block, 1 harden, 3 nit)

| ID | Severity | Theme | Resolution |
|---|---|---|---|
| F-DP-1 | harden | Exclude-set hardcoded in body | Lifted to module-level `_DIGEST_EXCLUDED_FILENAMES: Final[frozenset[str]]` — Open/Closed seam by data |
| F-DP-2 | nit | `CaseDigestStrategy` Protocol opportunity | Deferred — rule-of-three not crossed; AC-13 fence is the structural lock |
| F-DP-3 | nit | `CaseId` / `BlakeHex` newtype | Deferred — phase-wide identifier work (S1-03 precedent) |
| F-DP-4 | nit | DI seam for `digests.yaml` loader | Deferred — one caller; private helper sufficient |

## Conflict resolution log

- **Coverage F-COV-1 (BLOCK) vs Notes-for-implementer (original).** Original Notes told the implementer to use `content_hash_of_inputs`. The arch Scenario 2 requires content-sensitive digest detection. Consistency wins — pinned `content_hash` (per-file content) composition; fence test AC-13 makes the mutation guard structural.
- **Coverage F-COV-3 vs Implementation outline (original).** Original outline did not mention Edge #1 (`input/` missing); the arch table explicitly does. Consistency wins (arch is source of truth for edge-case behavior); added AC-5.
- **Test-Quality F-TQ-5 (Hypothesis sort property) vs Rule 2 (Simplicity First).** The 3-case fixture-based test is what the original story had. Adding a Hypothesis property test increases test mass. Test-Quality wins narrowly: the `sorted(...) -> list(...)` mutation is the most likely refactor regression in this file, and a property test costs ~10 lines while killing the mutant decisively. Precedent: S1-02 used Hypothesis for `case_digest` regex.
- **Design-Patterns F-DP-1 (lift constant) vs Rule 2.** Promoted to module-level constant (not to an AC) — this is the smallest possible Open/Closed gesture and costs one line. Noted in Refactor section; the AC test set verifies the behavior, not the file structure.
- **Coverage F-COV-4 (input_path/expected_path traversal) vs Out-of-scope split.** The loader doesn't *resolve* or *open* these paths at load time (Phase 4 / runner layer responsibility), but it MUST reject traversal at load time (the value is a static fact in `case.toml`, not a runtime resolution). Compromise: AC-4 checks `is_relative_to(case_dir)` but does NOT stat the resolved path — fact-validation, not existence-validation.

## Edits applied to the story file

- **Status:** `Ready` → `HARDENED`.
- **Depends on:** broadened from `S2-01` to `S1-01, S1-02, S1-03, S2-01` (each is a real prerequisite — typed errors, BenchCase Pydantic, TaskClass shape, conftest fixture).
- **ADRs honored:** added Phase 0 ADR-0001 (BLAKE3 chokepoint) explicitly.
- **Validation notes block:** added (per editor.md template).
- **Context paragraph:** explicit warning about which hashing primitive to use.
- **References:** restructured into Architecture / ADRs / Source design / High-level-impl / Existing code / Precedents (mirrors S2-01).
- **Goal:** rewrote to enumerate the full set of invariants (digest, collision, case_id↔dir, symlink, traversal, schema, fail-fast).
- **Acceptance criteria:** 10 ACs → 21 ACs. Every AC is individually verifiable; collectively they constrain the goal; no escape hatches.
- **Implementation outline:** expanded from 6 steps to 6 steps with the failure-order spec inline + 3 private helpers + 1 fence test + 2 new test files.
- **TDD plan:** comment-only stubs → ~250 LOC of runnable Python with concrete asserts, parametrized tests, Hypothesis property test, structlog capture, AST fence.
- **Files to touch:** 3 rows → 5 rows.
- **Out of scope:** 3 bullets → 8 bullets (added cassette_path, held-out floor, commit_sha cross-validation, newtype/protocol/DI deferrals).
- **Notes for implementer:** rewrote — wrong primitive guidance removed; failure-order load-bearing-ness explained; structlog testing precedent named; `_DIGEST_EXCLUDED_FILENAMES` extension path documented; doc-drift surfaced.

## Verdict

**HARDENED.** The story now satisfies the "good" criteria:

- Every AC is individually verifiable (concrete `pytest.raises(...) as exc_info: exc_info.value.field == "..."`).
- The AC set collectively guarantees the goal — every arch edge case for the loader (#1, #2, #7, #20) plus Scenario 2 contract has a corresponding AC + test.
- Every AC has a mutation-resistant test in the TDD plan; the AC-13 fence forecloses the most likely regression (swapping to the wrong primitive).
- No tautological / vague ACs remain. The original "TDD red test exists" lone-AC was rewritten with structural backing in AC-19/AC-20/AC-21.
- The story does not contradict the phase arch, any ADR, or CLAUDE.md commitments (one cross-doc drift surfaced in Notes for follow-on, not auto-fixed).
- Domain identifiers stay typed via `BenchCase` Pydantic; the loader doesn't tangle with raw `str` shapes.
- The Open/Closed seam (`_DIGEST_EXCLUDED_FILENAMES`) is data-driven; adding files to exclude in future is one-line.
- Pure / impure split is honored: `_compute_case_dir_digest` is data-in → digest-out, `_load_digests_yaml` is path-in → mapping-out, `_scan_for_symlinks` is path-in → raises-or-returns; `load_cases` is the imperative shell.

Ready for `phase-story-executor`.
