# Story S2-02 — Loader: `load_cases` + BLAKE3 digests + case-id collision

**Step:** Step 2 — Build harness internals: loader, cache, audit chain extension, canary + cost-tag shims
**Status:** Ready
**Effort:** M
**Depends on:** S2-01
**ADRs honored:** ADR-0006 (curation-class split — `case.toml` carries `curation_class`), Phase 0 BLAKE3 hashing chokepoint reuse

## Context

`load_cases` is the **integrity gate** for the bench corpus: it walks every `bench/{task-class}/cases/*/case.toml`, parses each into a `BenchCase`, BLAKE3-verifies the case directory against `cases/digests.yaml`, and orders the result deterministically by `case_id`. This is where poisoned cases (`Scenario 2` in `phase-arch-design.md`) are caught before any SUT invocation, where curator typos collide (`Gap #3` — duplicate `case_id`), and where the deterministic case ordering used by the BCa bootstrap seed (Step 3) originates. The `case_digest` over a case directory intentionally **excludes** `case.toml` (ADR-0005 §Consequences) so editing the `cassette_canary_pin` is identity, not content — a curator can rotate a pin without re-signing the digest.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — src/codegenie/eval/loader.py` — public interface, BLAKE3-over-tarball spec, sorted-by-`case_id` invariant
  - `../phase-arch-design.md §Scenarios — Scenario 2: Bench-case poisoning detected` — exact diagnostic shape and exit-code-6 contract
  - `../phase-arch-design.md §Gap analysis & improvements §Gap 3` — case-id collision rationale (`BenchCaseIDCollision(case_id, [path_a, path_b])`)
  - `../phase-arch-design.md §Edge cases #1, #2, #7, #16` — malformed `case.toml`, missing `input/`, collision, corrupted file
  - `../phase-arch-design.md §Data model` — `BenchCase` field list, including `cassette_canary_pin` and `case_digest`
- **Phase ADRs:**
  - `../ADRs/0005-cassette-canary-seed-parameterization.md §Consequences` — `case_digest` excludes `case.toml`; pin is identity not content
  - `../ADRs/0006-curation-class-split-with-fence-ci-held-out-floor.md` — `curation_class ∈ {rag-corpus-derived, held-out}` is a load-bearing field of `BenchCase`
- **Source design:**
  - `../final-design.md §bench/{task-class}/ directory contract` — required + optional keys in `case.toml`
- **Existing code:**
  - `src/codegenie/eval/loader.py` (S2-01) — extend with `load_cases`
  - `src/codegenie/eval/models.py` (S1-02) — `BenchCase` Pydantic; `extra="forbid"`, `frozen=True`
  - `src/codegenie/eval/errors.py` (S1-01) — `BenchCaseLoadError`, `BenchCaseDigestMismatch`, `BenchCaseIDCollision`
  - `src/codegenie/hashing.py` (Phase 0 S2-03) — `content_hash`; lazy `blake3` import; the only file that imports `blake3` in the repo
  - Phase 0 `localv2.md §6` — `tomllib` available in 3.11+

## Goal

`codegenie.eval.loader.load_cases(task_class)` walks `bench/{task_class.name}/cases/*/case.toml`, validates each into a `BenchCase`, BLAKE3-verifies each case directory against `cases/digests.yaml` (excluding `case.toml` from the digest), enforces `case_id` uniqueness and directory-name-matches-`case_id`, and returns a `tuple[BenchCase, ...]` sorted by `case_id`.

## Acceptance criteria

- [ ] `load_cases(task_class: TaskClass) -> tuple[BenchCase, ...]` is exported from `codegenie.eval.loader` and returns case directories sorted lexicographically by `case_id`.
- [ ] Each `case.toml` is parsed with `tomllib.loads(...)` and validated into `BenchCase(...)`; any Pydantic `ValidationError` is re-raised as `BenchCaseLoadError(case_dir, field, reason)` with the failing field name extracted from `error.errors()`.
- [ ] For each case directory, `content_hash` (Phase 0's BLAKE3 chokepoint) is computed over the **sorted** set of files inside the case directory **excluding** `case.toml`; the result is compared to `cases/digests.yaml`'s `<case_id>: blake3:<hex>` entry. Mismatch → `BenchCaseDigestMismatch(case_id, expected, computed)`.
- [ ] Two `case.toml` files declaring `case_id == "X"` in different directories under `cases/` → `BenchCaseIDCollision(case_id="X", paths=(Path_A, Path_B))` (Gap #3). The paths in the tuple are sorted for deterministic error messages.
- [ ] If a `case.toml` declares `case_id="X"` but lives in `cases/Y/`, raise `BenchCaseLoadError(case_dir=cases/Y, field="case_id", reason="does not match directory name 'Y'")` (defense-in-depth for the same fence assertion #7 in Step 7).
- [ ] Missing `cases/digests.yaml` raises `BenchCaseLoadError(case_dir=cases, field="digests.yaml", reason="file not found")` with exit-code-6 mapping documented.
- [ ] A `case.toml` schema-invalid in `disposition`, `curation_class`, `cassette_canary_pin` length, or `case_digest` prefix shape raises `BenchCaseLoadError`, **not** a raw Pydantic `ValidationError`.
- [ ] Stale `last_validated_at` (> 90 days from `today`) emits a `structlog.warn loader.case_stale` event but does NOT fail loading (per `phase-arch-design.md §Edge cases #20`; Phase 16 escalates to error).
- [ ] `load_cases` is called twice for the same `task_class`: both return tuples of identical contents and identical iteration order (deterministic sort).
- [ ] TDD red test exists, committed, green.
- [ ] `ruff format`, `ruff check`, `mypy --strict` clean.

## Implementation outline

1. Extend `src/codegenie/eval/loader.py` with `load_cases(task_class)`.
2. Resolve `cases_root = task_class.bench_path / "cases"`; load `digests.yaml` into a `dict[str, str]` (case_id → `blake3:<hex>`); missing file → typed error.
3. Iterate `sorted(cases_root.iterdir())`; for each directory:
   - Read and parse `case.toml`; build `BenchCase`. Catch `ValidationError` → `BenchCaseLoadError`.
   - Assert `case.case_id == dir.name` (cross-check).
   - Compute the directory digest: `content_hash_of_inputs(...)` over every file in the directory except `case.toml` (sorted by `(str(path), size)` for stability — reuse Phase 0's helper).
   - Compare to `digests[case.case_id]`; mismatch → `BenchCaseDigestMismatch`.
   - Append to a list.
4. While appending, maintain a `seen: dict[str, Path]`; on duplicate, raise `BenchCaseIDCollision` with both paths in sorted order.
5. Return `tuple(sorted(cases, key=lambda c: c.case_id))`.
6. Emit `structlog.warn loader.case_stale` when `(date.today() - case.last_validated_at).days > 90`.

## TDD plan — red / green / refactor

### Red

Test file: `tests/unit/eval/test_loader_cases_and_digests.py`

```python
def test_load_cases_sorted_by_case_id(tmp_bench):
    # Arrange 3 case dirs with case_ids "002-a", "001-b", "003-c" — out of disk order.
    # Assert returned tuple's case_ids == ("001-b", "002-a", "003-c").
    ...

def test_load_cases_digest_mismatch_raises_typed(tmp_bench):
    # Flip a byte in input/file.txt for one case.
    # Recompute expected blake3; assert BenchCaseDigestMismatch(case_id, expected, computed) — fields match exactly.
    ...

def test_load_cases_case_toml_excluded_from_digest(tmp_bench):
    # Edit case.toml's cassette_canary_pin to a new 32-hex value (do NOT update digests.yaml).
    # load_cases must NOT raise — pin is identity not content (ADR-0005).
    ...

def test_load_cases_duplicate_case_id_raises_collision(tmp_bench):
    # Two case dirs with the same `case_id` field → BenchCaseIDCollision(case_id, (path_a, path_b)) sorted.
    ...

def test_load_cases_case_id_directory_mismatch(tmp_bench):
    # case.toml declares case_id="A" but lives in cases/B/ → BenchCaseLoadError(field="case_id", ...).
    ...

def test_load_cases_missing_digests_yaml_typed(tmp_bench):
    # Delete digests.yaml; expect BenchCaseLoadError(field="digests.yaml", reason="file not found").
    ...

def test_load_cases_malformed_toml_field_in_error(tmp_bench):
    # case.toml has disposition="bogus" (not in Literal); expect BenchCaseLoadError with field="disposition".
    ...

def test_load_cases_stale_last_validated_at_warns_not_fails(tmp_bench, caplog):
    # last_validated_at = 100 days ago. load_cases returns; caplog captured `loader.case_stale` warn event.
    ...

def test_load_cases_deterministic_across_two_calls(tmp_bench):
    # Two invocations return identical tuples (same objects' field-values, same order).
    ...
```

### Green

Smallest impl: §Implementation outline steps 1–6; ~60–80 lines.

### Refactor

- Split into `_load_digests_yaml`, `_compute_case_dir_digest`, `_validate_case_toml` private helpers; each unit-testable.
- Lift the "exclude `case.toml`" filter into a named constant `_EXCLUDED_FROM_DIGEST = frozenset({"case.toml"})`.
- Defensive: use `Path.relative_to(case_dir)` when reporting paths in errors so messages aren't tied to absolute temp paths in tests.
- Add type aliases: `CaseId = str`, `BlakeHex = str` — keep `mypy --strict` ergonomic.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/loader.py` | Add `load_cases` + 3 private helpers |
| `tests/unit/eval/test_loader_cases_and_digests.py` | Red tests for all 9 paths above |
| `tests/fixtures/bench/stub_task_class/cases/...` | 3-case fixture (good, plus poisoned + collision variants generated dynamically in tests) |

## Out of scope

- **Runtime case execution** — handled by S3-01/S3-02; loader only loads and verifies.
- **Cache-key composition involving `case_digest`** — handled by S2-03.
- **Fence-CI AST walks for case-id uniqueness** — handled by S7-01 (defense-in-depth at PR review; loader is runtime defense).

## Notes for the implementer

- **Reuse `codegenie.hashing.content_hash_of_inputs`** — do NOT import `blake3` here directly; Phase 0 ADR-0001 establishes `hashing.py` as the only `blake3` importer.
- The `digests.yaml` entries are `<case_id>: blake3:<64-hex>` — the prefix tag is part of the contract (Phase 0 S2-03 §AC); compare prefix-tagged strings end-to-end, don't strip it.
- Sort `Path.iterdir()` before iterating — filesystem order is non-deterministic on some platforms (Linux ext4 hash-ordered dirents in particular).
- `BenchCase.cassette_canary_pin` is 32 hex chars; validate length at Pydantic time (S1-02 already does), but document in the test that the loader does NOT re-check.
- `last_validated_at` — parse with `datetime.fromisoformat` then call `.date()`; compare to `date.today()` for the staleness check.
- The "case_id matches directory name" check closes a real curator footgun: someone copies a case dir, edits `case.toml`'s `case_id`, forgets to rename the dir. Without this check, `sorted(by case_id)` produces a result that doesn't match `iterdir()` listing, which is silently confusing.
- For collision messages, sort the two `Path`s deterministically so test assertions don't depend on iteration order.
