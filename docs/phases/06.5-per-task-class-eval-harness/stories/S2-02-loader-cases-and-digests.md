# Story S2-02 — Loader: `load_cases` + BLAKE3 digests + case-id collision

**Step:** Step 2 — Build harness internals: loader, cache, audit chain extension, canary + cost-tag shims
**Status:** HARDENED
**Effort:** M
**Depends on:** S1-01 (typed errors — `BenchCaseLoadError`, `BenchCaseDigestMismatch`, `BenchCaseIDCollision`), S1-02 (`BenchCase` Pydantic; `frozen=True`, `extra="forbid"`), S1-03 (`TaskClass` shape — `bench_path` attr), S2-01 (`load_task_class`, locked-loader `__all__`, conftest isolation fixture)
**ADRs honored:** ADR-0005 (`case_digest` excludes `case.toml` — pin is identity, not content), ADR-0006 (curation-class split — `BenchCase.curation_class` is required and surfaced by the loader), Phase 0 ADR-0001 (BLAKE3 hashing chokepoint — `codegenie.hashing` is the only `blake3` importer)

## Validation notes

Validated: 2026-05-26
Verdict: HARDENED
Findings addressed: 32 total — 4 block, 18 harden, 10 nit
Critic reports: Coverage (10), Test-Quality (12), Consistency (6), Design-Patterns (4). No `NEEDS RESEARCH` — every pattern is precedented in this repo (Phase 0 `content_hash`, `tests/unit/parsers/test_safe_yaml.py` for structlog capture, `probes/deployment.py:183-193` for symlink-escape detection, S2-01 conftest discipline).

**Conflict resolutions** (priority: Consistency > Coverage > Test-Quality > Design-Patterns):

- **B-DIGEST-PRIMITIVE (F-TQ-1 / F-CON-1 / F-COV-1 — BLOCK).** Consistency wins decisively. The original story said *"Reuse `codegenie.hashing.content_hash_of_inputs`"* — but [src/codegenie/hashing.py:194-211](../../../../src/codegenie/hashing.py#L194) hashes a `(path, st_size)` **manifest**, not file contents. A byte-edit inside `expected/diff.patch` that preserves file size would silently pass the digest check. That **defeats Scenario 2** (the load-bearing reason the digest exists): "A contributor merges a PR that edits `bench/vuln-remediation/cases/003-.../expected/diff.patch` (e.g., loosens the expected diff to make the case easier) without updating `cases/digests.yaml`" must be detected. Pinned the canonical algorithm in AC-3 + new helper spec: walk the case dir via `rglob("*")` (recursive) filtered to regular files, exclude `case.toml`, for each remaining file compute `content_hash(path)` (Phase 0's *per-file content* primitive at [src/codegenie/hashing.py:54](../../../../src/codegenie/hashing.py#L54)), build records `f"{rel_posix}\x1f{content_hash}".encode()` joined by `\x1e`, BLAKE3 the joined bytes, prefix with `blake3:`. This is content-sensitive AND order-stable. The implementer must NOT use `content_hash_of_inputs`.
- **B-RGLOB (F-COV-2 — BLOCK).** Coverage wins. The original Implementation outline said *"every file in the directory except `case.toml`"* and *"`Path.iterdir()`"* — `iterdir()` is shallow but `BenchCase` carries `input_path: Path` and `expected_path: Path` (arch-design §Data model lines 769–770) that point into subdirectories (`input/`, `expected/`). A shallow walk would hash zero files for a real case. Pinned `rglob("*")` filtered to `Path.is_file() and not is_symlink()`. Added AC-3b.
- **B-INPUT-MISSING (F-COV-3 — BLOCK).** Coverage wins via arch Edge case #1 ("Bench case file missing / unreadable → `BenchCaseLoadError(case_dir, 'input/ not found')`; exit code 6 before any SUT invocation"). Story silently dropped this. Added AC-5 + TDD test `test_load_cases_missing_input_directory_typed`.
- **B-INPUT-EXPECTED-FIELDS (F-COV-4 — BLOCK).** Consistency wins via arch-design §Data model lines 769–770 — `BenchCase.input_path: Path` and `expected_path: Path` are required fields. The story is silent on how `case.toml` declares them, whether they're relative to the case dir, and whether they're validated to exist. Pinned: both are required keys in `case.toml`, parsed as `Path` strings relative to the case directory (the loader resolves them via `case_dir / value` and asserts `is_relative_to(case_dir.resolve())` to block path traversal); the loader does NOT stat them at load time (Pydantic accepts any `Path`; existence is checked by AC-5's "input/ not found" guard which validates `(case_dir / "input").is_dir()` since arch Edge #1 specifically names `input/`). Added AC-4.
- **Symlink-escape (F-COV-5 — HARDEN promoted near BLOCK).** Coverage wins. A case dir containing `expected/out -> /etc/passwd` would be walked by `rglob` and `content_hash` would read the link target (`Path.open` follows symlinks). Pinned: any file under the case dir that is a symlink → `BenchCaseLoadError(case_dir, field="symlink", reason=f"symlink not allowed at {relpath}")`. Added AC-9 + TDD test. Precedent: [src/codegenie/probes/deployment.py:183-193](../../../../src/codegenie/probes/deployment.py#L183) (`resolved.is_relative_to(root_resolved)`).
- **digests.yaml schema (F-COV-6 — HARDEN).** Coverage wins. No AC covered: YAML syntax error, non-mapping root, entry value not `blake3:<64 hex>`, entry for a case_id that has no matching directory (extra), case_id directory with no entry in `digests.yaml` (missing). Added AC-6a/AC-6b + four parametrized TDD tests. The `extra` entries are an error (curator forgot to remove a deleted case); `missing` entries are also an error (curator forgot to sign a new case).
- **Failure-ordering (F-COV-7 — HARDEN).** Coverage wins. When two errors could fire (e.g., a case_id collision AND a digest mismatch for one of the same cases), the deterministic firing order is now spec'd in AC-10: (1) `bench_path / "cases"` not a directory → fail; (2) `digests.yaml` missing → fail; (3) `digests.yaml` parse → fail; (4) iterate `sorted(cases_root.iterdir())`: per case dir, (4a) `case.toml` parse / Pydantic validate, (4b) `case_id == dir.name`, (4c) collision check against `seen`, (4d) digest compute + compare, (4e) `input/` exists, (4f) symlink scan. First failure raises; iteration aborts (fail-fast — matches Scenario 2 abort contract).
- **structlog capture (F-TQ-2 — HARDEN).** Test-Quality wins. Original test said `caplog captured 'loader.case_stale' warn event` — `caplog` is the stdlib-logging fixture, but [src/codegenie/](../../../../src/codegenie/) uses `structlog`. Captured events must use [`structlog.testing.capture_logs()`](https://www.structlog.org/en/stable/testing.html), precedented at [tests/unit/parsers/test_safe_yaml.py:32](../../../../tests/unit/parsers/test_safe_yaml.py#L32) and [tests/unit/test_audit_anchors.py:172](../../../../tests/unit/test_audit_anchors.py#L172). Rewrote the test in AC-8 / TDD.
- **Comment-only TDD stubs (F-TQ-3 through F-TQ-12 — HARDEN).** Test-Quality wins (mutation thinking). All nine `# Arrange / # Assert` placeholders rewritten as runnable Python with explicit `pytest.raises(BenchCaseDigestMismatch) as exc_info`, `exc_info.value.case_id == "003-x"`, `exc_info.value.expected == ...`, `exc_info.value.computed == ...` assertions. A `pass`-body `load_cases` would fail every test.
- **Mutation-resistance: deterministic sort property (F-TQ-13 — HARDEN).** Test-Quality wins. Without a property test, a `replace_all` swap of `sorted(cases, key=lambda c: c.case_id)` → `cases` could pass the 3-case fixture (if disk-iteration happens to return them sorted on the developer's box). Added a Hypothesis property test: generate N case_ids (3 ≤ N ≤ 20) drawn from a slug-shaped charset, scaffold them on disk in random order, assert the returned tuple is sorted lexicographically and is non-empty. Precedent: S1-02 used Hypothesis for `case_digest` regex coverage.
- **Stale-not-fail mutation (F-TQ-14 — HARDEN).** Test-Quality wins. A faulty impl could *escalate* stale to error (regress arch Edge #20 + ADR-0016 §Consequences "Phase 16 escalates to error" — Phase 6.5 must warn, not error). Pinned in AC-8: `load_cases` returns a tuple of length N; staleness MUST NOT change the return shape.
- **`last_validated_at` type (F-CON-2 — HARDEN).** Consistency wins. `BenchCase.last_validated_at: datetime` (tz-aware UTC, arch line 768) — not `date`. Pydantic parses the `case.toml` string. The loader's staleness check is `(date.today() - case.last_validated_at.date()).days > 90`. Removed the original Notes-for-implementer suggestion to call `datetime.fromisoformat(...)` ourselves — Pydantic already did that.
- **Zero-cases / cases/ dir missing (F-COV-8 — HARDEN).** Coverage wins. The story said nothing about empty `cases/` directory. Pinned in AC-11: if `bench_path / "cases"` does not exist → `BenchCaseLoadError(case_dir=cases_root, field="cases", reason="directory not found")`; if it exists but contains zero case dirs → return `tuple()` AND emit `structlog.warn loader.zero_cases`. The runner can decide whether zero cases is fatal — the loader is fact-not-judgment (CLAUDE.md load-bearing).
- **Identity vs content (F-CON-3 — HARDEN).** Consistency wins via ADR-0005 §Consequences. The story's `test_load_cases_case_toml_excluded_from_digest` is on the right side of identity-not-content, but the AC was implicit. Made it AC-3c — explicit verifiable property: editing `case.toml#cassette_canary_pin` and re-saving (no other change) MUST NOT trigger `BenchCaseDigestMismatch`. This pins ADR-0005's contract at the loader boundary.
- **Doc-drift surfaced, not auto-fixed (F-CON-4 — surfaced).** [final-design.md §Failure modes line 316](../final-design.md) says `case.toml` malformed exclude-and-continue (exit code 1, `had_load_errors=True`). [phase-arch-design.md §Edge cases #2 line 945](../phase-arch-design.md) + [§Control flow §Bench-case digest mismatch line 835](../phase-arch-design.md) + Scenario 2 say abort fail-fast (exit code 6). Arch is newer and self-consistent (the Scenario 2 sequence diagram is unambiguous). Story follows arch (correct). Flagged for follow-on doc sweep; not auto-edited per Rule 3.
- **`cassette_path` (F-CON-5 — nit).** `BenchCase.cassette_path: Path | None` (arch line 771) is optional. The story didn't address whether the loader validates its existence. Consistency wins via "fact-not-judgment": loader does NOT stat `cassette_path` — Phase 4 cassette layer is responsible for resolution at SUT-invocation time. Pinned as explicit Out-of-scope.
- **Exclude-set hardcoded (F-DP-1 — HARDEN).** Design-Patterns advisory accepted: `_DIGEST_EXCLUDED_FILENAMES: Final[frozenset[str]] = frozenset({"case.toml"})` at module scope so future expansions (`.DS_Store`, `__pycache__/`) are a one-line data edit, not a code edit. NOT promoted to AC (Rule 2 — one excluded name today; Open/Closed by extension via constant). Surfaced in Notes-for-implementer.
- **Premature abstraction — `CaseDigestStrategy` Protocol (F-DP-2 — deferred).** Surfaced and explicitly rejected: there is exactly one digest strategy today (BLAKE3 over per-file content_hash records). Rule 2 — three concrete strategies before abstraction. Notes-for-implementer documents the trigger condition.
- **Newtype `CaseId` / `BlakeHex` (F-DP-3 — deferred).** S1-03 precedent: identifier-consolidation work is deferred phase-wide. Keep `case_id: str` per `BenchCase` Pydantic shape. The original story's "Add type aliases" Refactor bullet is removed — type aliases offer zero protection over `str` and add noise.
- **DI seam for `digests.yaml` loader (F-DP-4 — deferred).** A `_load_digests_yaml(path) -> dict[str, str]` private helper is already in the prescribed refactor; a public Protocol injectable into `load_cases` is YAGNI for one caller. Surfaced in Notes-for-implementer.

Full audit log: `_validation/S2-02-loader-cases-and-digests.md`

## Context

`load_cases` is the **integrity gate** for the bench corpus: it walks every `bench/{task-class}/cases/<case-id>/case.toml`, parses each into a `BenchCase`, BLAKE3-verifies the case directory against `cases/digests.yaml`, and orders the result deterministically by `case_id`. This is where poisoned cases (`Scenario 2` in `phase-arch-design.md`) are caught before any SUT invocation, where curator typos collide (`Gap #3` — duplicate `case_id`), and where the deterministic case ordering used by the BCa bootstrap seed (Step 3) originates. The `case_digest` over a case directory intentionally **excludes** `case.toml` (ADR-0005 §Consequences) so editing the `cassette_canary_pin` is identity, not content — a curator can rotate a pin without re-signing the digest.

The digest is **content-sensitive** (per-file BLAKE3 of bytes, not `(path, size)` manifest) — that is the entire point of Scenario 2 being detectable. The implementer MUST use Phase 0's per-file [`content_hash`](../../../../src/codegenie/hashing.py#L54) primitive composed canonically, NOT [`content_hash_of_inputs`](../../../../src/codegenie/hashing.py#L194) (which hashes only paths + sizes and would silently accept byte-edits that preserve size).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — src/codegenie/eval/loader.py` (line 556) — public-interface signature; sorted-by-`case_id` invariant; failure-behavior mapping (`BenchCaseLoadError`, `BenchCaseDigestMismatch`)
  - `../phase-arch-design.md §Scenarios — Scenario 2: Bench-case poisoning detected` (line 416) — exact diagnostic shape, abort-fail-fast contract, exit-code-6 mapping
  - `../phase-arch-design.md §Gap analysis & improvements §Gap 3` (line 1164) — case-id collision rationale (`BenchCaseIDCollision(case_id, paths)`)
  - `../phase-arch-design.md §Edge cases #1, #2, #7, #20` (lines 944–963) — missing `input/` dir, malformed `case.toml`, collision, stale `last_validated_at`
  - `../phase-arch-design.md §Data model` (lines 757–773) — `BenchCase` field list (`case_id`, `task_class`, `disposition`, `difficulty`, `source`, `curation_class`, `commit_sha`, `added_at`, `last_validated_at`, `input_path`, `expected_path`, `cassette_path`, `cassette_canary_pin`, `case_digest`)
  - `../phase-arch-design.md §Control flow §Decision point #6 (line 835)` — abort exit-code-6 contract on digest mismatch
- **Phase ADRs:**
  - `../ADRs/0005-cassette-canary-seed-parameterization.md §Consequences` — `case_digest` excludes `case.toml`; pin is identity not content
  - `../ADRs/0006-curation-class-split-with-fence-ci-held-out-floor.md` — `curation_class ∈ {rag-corpus-derived, held-out}` is mandatory on `BenchCase` and surfaced unchanged by the loader (the floor check is fence-CI's job, not the loader's)
- **Source design:**
  - `../final-design.md §bench/{task-class}/ directory contract` (line 270) — required + optional keys in `case.toml`
  - `../final-design.md §Failure modes` (line 316) — surfaced doc drift: this row says exclude-and-continue (exit-1), but the newer arch §Scenario 2 + §Control flow §Decision point #6 say abort (exit-6). Story follows arch (correct). Flagged in Validation notes for doc sweep.
- **High-level-impl:**
  - `../High-level-impl.md §Step 2` (line 48) — loader scope: `load_cases` walks the corpus, BLAKE3-verifies, sorts by `case_id`, raises `BenchCaseIDCollision`
  - `../High-level-impl.md §Step 2 exit criteria` (line 56–57) — 3-case fixture: sort + byte-flip mismatch + collision
  - `../High-level-impl.md §Step 4` (line 97) — CLI exit-code partitioning (`6 digest mismatch`) that this story's typed exits feed
- **Existing code (Phase 0 + sibling stories):**
  - [`src/codegenie/eval/loader.py`](../../../../src/codegenie/eval/loader.py) (S2-01) — `load_task_class` already lives here; extend with `load_cases`
  - [`src/codegenie/eval/models.py`](../../../../src/codegenie/eval/models.py) (S1-02) — `BenchCase` Pydantic shape (`frozen=True`, `extra="forbid"`, `case_digest` regex validator already enforces `blake3:<64 hex>`)
  - [`src/codegenie/eval/errors.py`](../../../../src/codegenie/eval/errors.py) (S1-01) — `BenchCaseLoadError(case_dir, field, reason)`, `BenchCaseDigestMismatch(case_id, expected, computed)`, `BenchCaseIDCollision(case_id, paths)`
  - [`src/codegenie/hashing.py:54`](../../../../src/codegenie/hashing.py#L54) (Phase 0 S2-03) — `content_hash(path) -> "blake3:<hex>"` — the **content-sensitive** per-file primitive (use this)
  - [`src/codegenie/hashing.py:194`](../../../../src/codegenie/hashing.py#L194) (Phase 0) — `content_hash_of_inputs(paths) -> "blake3:<hex>"` — hashes a `(path, size)` manifest only. **Do NOT use** for case-dir digest (would silently accept byte-edits that preserve size).
- **Precedents in this repo:**
  - [`tests/unit/parsers/test_safe_yaml.py:32`](../../../../tests/unit/parsers/test_safe_yaml.py#L32) — `from structlog.testing import capture_logs` — the canonical structlog event capture in this repo
  - [`tests/unit/test_audit_anchors.py:172`](../../../../tests/unit/test_audit_anchors.py#L172) — `with structlog.testing.capture_logs() as logs: ...` precedent
  - [`src/codegenie/probes/deployment.py:183-193`](../../../../src/codegenie/probes/deployment.py#L183) — `resolved.is_relative_to(root_resolved)` for symlink-escape detection
  - [`src/codegenie/probes/language_detection.py:291`](../../../../src/codegenie/probes/language_detection.py#L291) — `entry.is_symlink()` precedent for filesystem-walk hygiene
  - S2-01 conftest at `tests/unit/eval/conftest.py` (autouse snapshot/restore of `sys.path`, `sys.modules`, `default_registry`) — this story relies on the same fixture; do NOT redefine
  - `docs/phases/06.5-per-task-class-eval-harness/stories/_validation/S2-01-bench-import-path-resolution.md` — sibling validation discipline (concrete asserts, parametrize, no comment-only stubs)

## Goal

`codegenie.eval.loader.load_cases(task_class)` walks `task_class.bench_path / "cases" / *`, parses each `case.toml` into a `BenchCase`, BLAKE3-verifies each case directory's contents against `cases/digests.yaml` (excluding `case.toml` itself; the digest is the per-file content hash composed canonically), enforces `case_id`-uniqueness and `case_id == directory name`, rejects symlinks inside the case dir, validates `digests.yaml` for missing/extra entries, and returns a `tuple[BenchCase, ...]` sorted by `case_id`. All failure paths raise typed exceptions from `codegenie.eval.errors` whose attributes the S4-02 CLI maps to exit code 6 (digest/poisoning failures) or 1 (everything else). Stale `last_validated_at` warns via structlog but does NOT fail loading (arch Edge #20). Idempotent across repeat invocations.

## Acceptance criteria

- [ ] **AC-1 (public-surface seam):** `load_cases(task_class: TaskClass) -> tuple[BenchCase, ...]` is importable as `from codegenie.eval.loader import load_cases`. It is NOT added to `codegenie.eval.__init__.__all__` (S1-05 locks that surface at 9 names). Fence test asserts `"load_cases" not in codegenie.eval.__all__`.
- [ ] **AC-2 (module-level `__all__` extended):** `codegenie.eval.loader.__all__ == ("load_cases", "load_task_class")` — exact-tuple match, alphabetical (S2-01 left it as `("load_task_class",)`; this story widens to two). Test pins via `assert codegenie.eval.loader.__all__ == ("load_cases", "load_task_class")`.
- [ ] **AC-3 (content-sensitive case digest — composition spec):** For each case directory `case_dir`, the loader computes `case_digest` as follows:
  - (a) collect `paths = sorted(p for p in case_dir.rglob("*") if p.is_file() and not p.is_symlink() and p.name not in _DIGEST_EXCLUDED_FILENAMES)`, where `_DIGEST_EXCLUDED_FILENAMES: Final[frozenset[str]] = frozenset({"case.toml"})`. Sort key is `p.relative_to(case_dir).as_posix()`.
  - (b) For each `p` in `paths`, compute `per_file = codegenie.hashing.content_hash(p)` (= `"blake3:<64 hex>"` of file *contents*, per [hashing.py:54](../../../../src/codegenie/hashing.py#L54)). Build record `f"{rel_posix}\x1f{per_file}".encode("utf-8")`. Join records with `\x1e`. BLAKE3 the joined bytes; result = `f"blake3:{hexdigest}"`. Use the same `blake3` lazy-import discipline as Phase 0 — the helper lives in `codegenie.eval.loader` (private) and imports `blake3` via the Phase-0 chokepoint pattern. Direct `import blake3` in `loader.py` is forbidden by the fence test in AC-13.
  - (c) Compare to `digests[case_id]` (a `blake3:<64 hex>` string read verbatim from `cases/digests.yaml`); on mismatch raise `BenchCaseDigestMismatch(case_id, expected=digests[case_id], computed=case_digest)`. Both `expected` and `computed` are the full prefixed string (`blake3:…`), not the bare hex.
  - **(d) Negative property (mutation guard):** the implementer MUST NOT call `codegenie.hashing.content_hash_of_inputs` for this digest (it hashes `(path, size)` only and would silently accept byte-edits that preserve size — arch Scenario 2 would not be detected). Verified by `tests/fence/test_eval_loader_digest_primitive.py` AST-walk asserting `content_hash_of_inputs` is not referenced from `src/codegenie/eval/loader.py`.
- [ ] **AC-4 (`input_path` / `expected_path` resolution + traversal guard):** `case.toml` must declare `input_path` and `expected_path` as POSIX strings relative to the case directory (e.g., `"input"`, `"expected/diff.patch"`). Pydantic parses them as `Path`. The loader computes `resolved_input = (case_dir / case.input_path).resolve()` and asserts `resolved_input.is_relative_to(case_dir.resolve())`; same for `expected_path`. Path-traversal (e.g., `input_path = "../../etc/passwd"`) → `BenchCaseLoadError(case_dir, field="input_path", reason="path escapes case directory")`. The loader does **not** stat existence of the resolved path here (AC-5 handles the canonical `input/` directory existence check).
- [ ] **AC-5 (missing `input/` directory — arch Edge #1):** If `(case_dir / "input").is_dir()` is False, raise `BenchCaseLoadError(case_dir, field="input", reason="input/ directory not found")`. Fires before digest computation. Parametrized test covers: directory entirely absent; `input` exists but is a regular file; `input` exists but is a symlink.
- [ ] **AC-6a (`digests.yaml` parse + schema):** The loader reads `cases_root / "digests.yaml"` via `yaml.safe_load` (NEVER `yaml.load`). The root must be a `dict[str, str]`; non-mapping root → `BenchCaseLoadError(case_dir=cases_root, field="digests.yaml", reason="root must be a mapping of case_id to digest")`. Each value must match `re.fullmatch(r"blake3:[0-9a-f]{64}", v)`; malformed → `BenchCaseLoadError(case_dir=cases_root, field=f"digests.yaml#{case_id}", reason="not a canonical blake3:<64 lowercase hex> digest")`. YAML syntax errors propagate as `BenchCaseLoadError(case_dir=cases_root, field="digests.yaml", reason=f"YAML parse error: {e}")`. Parametrized test covers: well-formed; non-mapping root (`[ ... ]`); wrong prefix (`sha256:…`); uppercase hex; length−1; length+1; trailing whitespace; YAML syntax error.
- [ ] **AC-6b (`digests.yaml` ↔ filesystem completeness):** After iterating case dirs, the loader cross-checks: every case_id discovered on disk must have a `digests.yaml` entry; every `digests.yaml` entry must have a matching directory. A `case_id` on disk with no entry → `BenchCaseLoadError(case_dir, field="digests.yaml", reason=f"no entry for case_id '{case_id}'")`. An `entry` for a case_id with no on-disk directory → `BenchCaseLoadError(case_dir=cases_root, field=f"digests.yaml#{case_id}", reason="entry references unknown case_id (directory missing)")`. Either condition fires AFTER all individual case dirs have been parsed enough to know their case_ids (so the diagnostic is reliable), but BEFORE any return.
- [ ] **AC-7 (case-id ↔ directory-name cross-check):** If `case.case_id == "A"` but the case lives in `cases/B/`, raise `BenchCaseLoadError(case_dir=cases/B, field="case_id", reason=f"declared 'A' but lives in directory 'B'")`. Defense-in-depth against fence-CI assertion #7 (the AST-walk fence runs at PR time; this is the runtime defense).
- [ ] **AC-8 (collision — Gap #3):** Two `case.toml` files declaring `case_id == "X"` in different directories → `BenchCaseIDCollision(case_id="X", paths=(path_a, path_b))` where `paths` is sorted (`sorted([path_a, path_b], key=lambda p: p.as_posix())`) for deterministic diagnostics. Test asserts identity of every tuple element (not just `==`) and asserts `paths` length == 2. Parametrized test also covers: same case_id but in nested-versus-flat directory layouts (the collision check is by `case_id` value, not by directory depth).
- [ ] **AC-9 (symlink rejection):** Any path under `case_dir.rglob("*")` that `is_symlink()` returns True → `BenchCaseLoadError(case_dir, field="symlink", reason=f"symlink not allowed at {rel_posix}")`, where `rel_posix = path.relative_to(case_dir).as_posix()`. Fires BEFORE digest compute reads any bytes (a malicious symlink to `/etc/passwd` must not be read at all). Test covers: symlink to file outside the case dir; symlink to file inside the case dir (still rejected — uniform rule); symlink to a directory; broken symlink.
- [ ] **AC-10 (failure ordering — fail-fast spec):** When multiple invariants could fire, the deterministic firing order is:
  1. `bench_path / "cases"` exists and `is_dir()` — else `BenchCaseLoadError(field="cases", reason="directory not found")`.
  2. `cases_root / "digests.yaml"` exists and parses — see AC-6a.
  3. Iterate `sorted(p for p in cases_root.iterdir() if p.is_dir(), key=lambda p: p.name)`. Per directory, in order:
     - 3a. `(case_dir / "case.toml").read_text()` + `tomllib.loads(...)` + `BenchCase.model_validate(...)`. Pydantic `ValidationError` → `BenchCaseLoadError(case_dir, field=<first failing field>, reason=<error.errors()[0]['msg']>)`.
     - 3b. `case.case_id == case_dir.name` check (AC-7).
     - 3c. Collision check vs `seen: dict[str, Path]` (AC-8).
     - 3d. `(case_dir / "input").is_dir()` check (AC-5).
     - 3e. Symlink scan (AC-9).
     - 3f. Digest compute + compare (AC-3).
  4. After all dirs OK: `digests.yaml` ↔ disk cross-check (AC-6b).
  5. Return `tuple(sorted(cases, key=lambda c: c.case_id))`.

  The first failure raises and aborts iteration. Test: build a fixture with **two** simultaneous defects (e.g., collision + digest mismatch) and assert the collision raises (3c precedes 3f).
- [ ] **AC-11 (zero-cases handling):** If `cases_root` exists and is a directory but contains zero subdirectories: return `tuple()` AND emit `structlog.warn("loader.zero_cases", task_class=task_class.name, cases_root=str(cases_root))`. The loader is fact-not-judgment (CLAUDE.md) — fence-CI's `min_cases_for_promotion` floor is the bench-floor enforcement seam, not the loader. Test uses `structlog.testing.capture_logs()` to verify the event fires AND that the returned tuple is `()` (literally).
- [ ] **AC-12 (`case.toml` not file or unreadable):** `(case_dir / "case.toml").is_file()` False → `BenchCaseLoadError(case_dir, field="case.toml", reason="file not found")`. `read_text` raises `UnicodeDecodeError` → `BenchCaseLoadError(case_dir, field="case.toml", reason=f"not valid UTF-8: {e}")`. `tomllib.TOMLDecodeError` → `BenchCaseLoadError(case_dir, field="case.toml", reason=f"TOML parse error: {e}")`.
- [ ] **AC-13 (fence — no `blake3` direct import; no `content_hash_of_inputs` reference):** A new fence test at `tests/fence/test_eval_loader_digest_primitive.py` AST-walks `src/codegenie/eval/loader.py` and asserts: (a) no `import blake3` / `from blake3 import …` (the lazy-import via `codegenie.hashing` chokepoint is the only path — Phase 0 ADR-0001); (b) no reference to the name `content_hash_of_inputs` (mutation-guard — if a refactor swaps to the manifest hash, Scenario 2 silently regresses; this fence makes the failure loud). Precedent: `tests/fence/test_eval_loader_no_rubric_import.py` (S2-01).
- [ ] **AC-14 (`cassette_canary_pin` rotation is identity — ADR-0005):** Editing `case.toml#cassette_canary_pin` to a different 32-hex string and re-saving (no other change) MUST NOT trigger `BenchCaseDigestMismatch`. Test: scaffold a 1-case fixture, capture digest computation snapshot, mutate `cassette_canary_pin` to a new valid 32-hex value, re-invoke `load_cases`, assert no exception AND that the returned `BenchCase.cassette_canary_pin` reflects the new value.
- [ ] **AC-15 (stale `last_validated_at` warns, does not fail — arch Edge #20):** `(date.today() - case.last_validated_at.date()).days > 90` → `structlog.warn("loader.case_stale", case_id=case.case_id, days_stale=N)` is emitted but `load_cases` MUST return the case in the result tuple. Mutation-guard: a faulty impl that escalated to error would break Phase 6.5 contract (ADR-0016 §Consequences "Phase 16 escalates to error"; 6.5 warns). Test uses `structlog.testing.capture_logs()`; covers `days == 91` (boundary), `days == 90` (NOT stale — strict `> 90`), `days == 89` (NOT stale), `days == 365` (clearly stale).
- [ ] **AC-16 (deterministic across two calls):** Two back-to-back `load_cases(task_class)` invocations return tuples that are element-wise `==` AND whose iteration order is identical. Stronger: the digest values are byte-identical across calls (the canonical composition is order-stable). Test asserts both tuples and (for stronger mutation-resistance) byte-equality of the BLAKE3 digest of the canonical record stream — exposes any nondeterminism in path-sort or rglob order.
- [ ] **AC-17 (sort property — Hypothesis):** `@hypothesis.given(case_ids=st.lists(st.from_regex(r"^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$", fullmatch=True), min_size=3, max_size=20, unique=True))` scaffolds N case dirs on disk in random shuffle order and asserts the returned tuple is sorted ascending by `case_id`. Closes the "mutate `sorted(...)` to `list(...)`" gap; matches S1-02's Hypothesis precedent.
- [ ] **AC-18 (idempotent / no side effects):** Calling `load_cases(tc)` twice with no fs changes: the second call must NOT mutate the registry, must NOT add to `sys.path`, must NOT cache results in any module-level state. Test: snapshot `sys.path`, `sys.modules`, `len(default_registry.all_task_classes())` before/after each call; assert no growth.
- [ ] **AC-19 (mypy strict + ruff clean):** `mypy --strict src/codegenie/eval/loader.py` and `ruff check src/codegenie/eval/loader.py` and `ruff format --check src/codegenie/eval/loader.py` all green.
- [ ] **AC-20 (structlog event IDs match Phase 1 convention):** Every emitted event ID matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` (Phase 1 ADR-0007). The set this story adds: `loader.case_stale`, `loader.zero_cases`. Pin via a module-level `_WARNING_IDS: Final[frozenset[str]] = frozenset({"loader.case_stale", "loader.zero_cases"})` validated at import time via `raise AssertionError(...)` (bare `assert` is forbidden by the `forbidden-patterns` hook).
- [ ] **AC-21 (TDD red test exists, committed, green** at end of executor run.

## Implementation outline

1. Extend `src/codegenie/eval/loader.py` with `load_cases(task_class: TaskClass) -> tuple[BenchCase, ...]`. Update `__all__` to the exact tuple `("load_cases", "load_task_class")`. Add module-level `_DIGEST_EXCLUDED_FILENAMES: Final[frozenset[str]] = frozenset({"case.toml"})` and `_WARNING_IDS: Final[frozenset[str]] = frozenset({"loader.case_stale", "loader.zero_cases"})`. The startup `raise AssertionError(...)` validates event-ID shape against the Phase 1 regex.
2. Add three private helpers (each unit-testable):
   - `_load_digests_yaml(cases_root: Path) -> dict[str, str]` — `yaml.safe_load`, root-must-be-mapping, value-format regex, returns the verified mapping.
   - `_compute_case_dir_digest(case_dir: Path) -> str` — canonical composition per AC-3: rglob → filter (regular file, not symlink, not in `_DIGEST_EXCLUDED_FILENAMES`) → sort by POSIX relpath → records `f"{rel}\x1f{content_hash(p)}".encode()` joined by `\x1e` → BLAKE3 via Phase 0's `hashing` import chokepoint → return `f"blake3:{hex}"`. Raises nothing on its own; symlink rejection is the caller's responsibility (AC-9) so the diagnostic carries the correct field name.
   - `_scan_for_symlinks(case_dir: Path) -> None` — raises `BenchCaseLoadError(field="symlink", …)` on first symlink encountered; returns `None` if the tree is clean.
3. `load_cases` body (matches AC-10's failure order):
   1. `cases_root = task_class.bench_path / "cases"`; verify `cases_root.is_dir()` (else `BenchCaseLoadError(field="cases", reason="directory not found")`).
   2. `digests = _load_digests_yaml(cases_root)`.
   3. Initialize `seen: dict[str, Path] = {}`, `cases: list[BenchCase] = []`, `discovered_ids: set[str] = set()`.
   4. For each `case_dir` in `sorted((p for p in cases_root.iterdir() if p.is_dir()), key=lambda p: p.name)`:
      - Parse `case.toml` → `BenchCase` (AC-12 + Pydantic-error → `BenchCaseLoadError`).
      - `case.case_id == case_dir.name` check (AC-7).
      - Collision check vs `seen`; on dup, sort the two paths and raise `BenchCaseIDCollision` (AC-8).
      - `(case_dir / "input").is_dir()` check (AC-5).
      - `_scan_for_symlinks(case_dir)` (AC-9).
      - `_validate_subpath` for `case.input_path` and `case.expected_path` (AC-4) — `resolved.is_relative_to(case_dir.resolve())`.
      - `computed = _compute_case_dir_digest(case_dir)`; lookup `expected = digests.get(case.case_id)`; if missing → `BenchCaseLoadError(field="digests.yaml", reason=f"no entry for case_id '{case.case_id}'")`; if `computed != expected` → `BenchCaseDigestMismatch(case_id, expected, computed)`.
      - `discovered_ids.add(case.case_id)`; `seen[case.case_id] = case_dir`; `cases.append(case)`.
      - If `(date.today() - case.last_validated_at.date()).days > 90`, emit `structlog.warn("loader.case_stale", case_id=case.case_id, days_stale=delta)` (AC-15).
   5. Cross-check `digests.keys() - discovered_ids`: any extra → `BenchCaseLoadError(field=f"digests.yaml#{extra}", reason="entry references unknown case_id (directory missing)")` (AC-6b).
   6. If `cases` is empty: emit `structlog.warn("loader.zero_cases", task_class=task_class.name, cases_root=str(cases_root))` and return `tuple()` (AC-11).
   7. Return `tuple(sorted(cases, key=lambda c: c.case_id))` (AC-16, AC-17).
4. Add fence test `tests/fence/test_eval_loader_digest_primitive.py` (AC-13) — AST-walk `loader.py` for `import blake3` / `from blake3` / `content_hash_of_inputs` references; fail loud if any present. Reuse `tests/fence/_phase4_scanner.py:walk_imports` if it covers `Name` references (extend if needed).
5. Add `tests/unit/eval/test_loader_cases_and_digests.py` per the TDD plan below. Reuse the autouse conftest from S2-01 (`tests/unit/eval/conftest.py`) — no additional fixture needed.
6. Add a fixture-builder helper at `tests/unit/eval/_bench_fixtures.py` (or inline in conftest): `make_case(tmp_path, case_id, *, input_files=..., expected_files=..., disposition=..., …) -> Path` — scaffolds a single valid case dir + appends to `digests.yaml`; returns the case dir. Tests compose multi-case fixtures from this primitive. Keeps each test cheap to read.

## TDD plan — red / green / refactor

### Red

Test file: `tests/unit/eval/test_loader_cases_and_digests.py`. Every test is runnable Python (no comment-only stubs); every assertion is concrete.

```python
from __future__ import annotations

import datetime as dt
import textwrap
from pathlib import Path

import hypothesis.strategies as st
import pytest
import structlog.testing
from hypothesis import given, settings

from codegenie.eval.errors import (
    BenchCaseDigestMismatch,
    BenchCaseIDCollision,
    BenchCaseLoadError,
)
from codegenie.eval.loader import load_cases
from codegenie.hashing import content_hash

# `tmp_bench` builds a TaskClass whose bench_path is under tmp_path and seeds
# N case dirs from kwargs. Defined in conftest. Returns (task_class, cases_root).

# --- AC-1, AC-2: surface ---------------------------------------------------

def test_load_cases_is_importable_from_loader_submodule():
    from codegenie.eval.loader import load_cases as fn
    assert callable(fn)

def test_load_cases_not_in_package_all():
    import codegenie.eval as pkg
    assert "load_cases" not in pkg.__all__

def test_loader_all_tuple_pinned():
    import codegenie.eval.loader as mod
    assert mod.__all__ == ("load_cases", "load_task_class")

# --- AC-17 / AC-16: sort + determinism ------------------------------------

def test_load_cases_sorted_by_case_id_three_cases(tmp_bench):
    tc, _ = tmp_bench(case_ids=["002-bravo", "001-alpha", "003-charlie"])
    result = load_cases(tc)
    assert tuple(c.case_id for c in result) == ("001-alpha", "002-bravo", "003-charlie")

def test_load_cases_deterministic_across_two_calls(tmp_bench):
    tc, _ = tmp_bench(case_ids=["b", "a", "c"])
    first = load_cases(tc)
    second = load_cases(tc)
    assert first == second
    assert tuple(c.case_id for c in first) == tuple(c.case_id for c in second)

@given(case_ids=st.lists(
    st.from_regex(r"^[a-z0-9][a-z0-9-]{1,20}[a-z0-9]$", fullmatch=True),
    min_size=3, max_size=10, unique=True,
))
@settings(max_examples=20, deadline=None)
def test_load_cases_sort_property(case_ids, fresh_tmp_bench):
    tc, _ = fresh_tmp_bench(case_ids=case_ids)
    result = load_cases(tc)
    returned = [c.case_id for c in result]
    assert returned == sorted(case_ids)

# --- AC-3 / AC-14: content-sensitive digest -------------------------------

def test_load_cases_digest_mismatch_on_byte_flip_same_size(tmp_bench):
    tc, cases_root = tmp_bench(case_ids=["case-1"])
    target = cases_root / "case-1" / "input" / "main.txt"
    original = target.read_bytes()
    # Same-size byte flip — would NOT trigger content_hash_of_inputs mismatch.
    target.write_bytes(b"X" + original[1:])
    with pytest.raises(BenchCaseDigestMismatch) as exc_info:
        load_cases(tc)
    assert exc_info.value.case_id == "case-1"
    assert exc_info.value.expected.startswith("blake3:")
    assert exc_info.value.computed.startswith("blake3:")
    assert exc_info.value.expected != exc_info.value.computed

def test_load_cases_case_toml_excluded_from_digest_pin_rotation(tmp_bench):
    """ADR-0005: rotating cassette_canary_pin is identity, not content."""
    tc, cases_root = tmp_bench(case_ids=["case-1"])
    case_toml = cases_root / "case-1" / "case.toml"
    content = case_toml.read_text()
    new_pin = "f" * 32
    rewritten = re.sub(r'cassette_canary_pin\s*=\s*"[0-9a-f]{32}"',
                       f'cassette_canary_pin = "{new_pin}"', content)
    case_toml.write_text(rewritten)
    result = load_cases(tc)  # MUST NOT raise.
    assert result[0].cassette_canary_pin == new_pin

# --- AC-8: collision -------------------------------------------------------

def test_load_cases_duplicate_case_id_raises_collision_sorted_paths(tmp_bench):
    tc, cases_root = tmp_bench(
        case_ids=["zeta-original", "alpha-duplicate"],
        force_case_id_for={"alpha-duplicate": "zeta-original"},  # same case_id field
    )
    with pytest.raises(BenchCaseIDCollision) as exc_info:
        load_cases(tc)
    assert exc_info.value.case_id == "zeta-original"
    assert len(exc_info.value.paths) == 2
    # paths are sorted lexicographically:
    sorted_paths = sorted(exc_info.value.paths, key=lambda p: p.as_posix())
    assert tuple(exc_info.value.paths) == tuple(sorted_paths)

# --- AC-7: case_id mismatch -----------------------------------------------

def test_load_cases_case_id_directory_mismatch(tmp_bench):
    tc, cases_root = tmp_bench(
        case_ids=["alpha"],
        force_case_id_for={"alpha": "bravo"},
    )
    with pytest.raises(BenchCaseLoadError) as exc_info:
        load_cases(tc)
    assert exc_info.value.field == "case_id"
    assert "bravo" in exc_info.value.reason
    assert "alpha" in exc_info.value.reason

# --- AC-6a / AC-6b: digests.yaml schema + completeness --------------------

def test_load_cases_missing_digests_yaml_typed(tmp_bench):
    tc, cases_root = tmp_bench(case_ids=["case-1"])
    (cases_root / "digests.yaml").unlink()
    with pytest.raises(BenchCaseLoadError) as exc_info:
        load_cases(tc)
    assert exc_info.value.field == "digests.yaml"
    assert "not found" in exc_info.value.reason or "file not found" in exc_info.value.reason

@pytest.mark.parametrize("bad_yaml,expected_reason_fragment", [
    ("[1, 2, 3]\n", "root must be a mapping"),
    ("case-1: sha256:" + "0" * 64 + "\n", "not a canonical blake3"),
    ("case-1: blake3:" + "0" * 63 + "\n", "not a canonical blake3"),
    ("case-1: blake3:" + "0" * 65 + "\n", "not a canonical blake3"),
    ("case-1: blake3:" + "A" * 64 + "\n", "not a canonical blake3"),
    ("not-yaml: ::: invalid:\n  - oops:::\n - x\n", "YAML parse error"),
])
def test_load_cases_digests_yaml_schema(tmp_bench, bad_yaml, expected_reason_fragment):
    tc, cases_root = tmp_bench(case_ids=["case-1"])
    (cases_root / "digests.yaml").write_text(bad_yaml)
    with pytest.raises(BenchCaseLoadError) as exc_info:
        load_cases(tc)
    assert "digests.yaml" in exc_info.value.field
    assert expected_reason_fragment.lower() in exc_info.value.reason.lower()

def test_load_cases_digests_yaml_extra_entry_for_missing_dir(tmp_bench):
    tc, cases_root = tmp_bench(case_ids=["case-1"])
    digests = cases_root / "digests.yaml"
    digests.write_text(digests.read_text() + "ghost-case: blake3:" + "0" * 64 + "\n")
    with pytest.raises(BenchCaseLoadError) as exc_info:
        load_cases(tc)
    assert "ghost-case" in exc_info.value.field
    assert "unknown case_id" in exc_info.value.reason or "directory missing" in exc_info.value.reason

def test_load_cases_digests_yaml_missing_entry_for_existing_dir(tmp_bench):
    tc, cases_root = tmp_bench(case_ids=["case-1"])
    (cases_root / "digests.yaml").write_text("")  # empty mapping after parse
    with pytest.raises(BenchCaseLoadError) as exc_info:
        load_cases(tc)
    assert "digests.yaml" in exc_info.value.field

# --- AC-12 / Pydantic-edge: malformed case.toml ---------------------------

def test_load_cases_malformed_toml_disposition_field_named(tmp_bench):
    tc, cases_root = tmp_bench(case_ids=["case-1"])
    case_toml = cases_root / "case-1" / "case.toml"
    rewritten = case_toml.read_text().replace(
        'disposition = "positive"', 'disposition = "undecided"'
    )
    case_toml.write_text(rewritten)
    with pytest.raises(BenchCaseLoadError) as exc_info:
        load_cases(tc)
    assert exc_info.value.field == "disposition"

def test_load_cases_case_toml_missing(tmp_bench):
    tc, cases_root = tmp_bench(case_ids=["case-1"])
    (cases_root / "case-1" / "case.toml").unlink()
    with pytest.raises(BenchCaseLoadError) as exc_info:
        load_cases(tc)
    assert exc_info.value.field == "case.toml"

def test_load_cases_case_toml_not_utf8(tmp_bench):
    tc, cases_root = tmp_bench(case_ids=["case-1"])
    (cases_root / "case-1" / "case.toml").write_bytes(b"\xff\xfe\x00bogus")
    with pytest.raises(BenchCaseLoadError) as exc_info:
        load_cases(tc)
    assert exc_info.value.field == "case.toml"
    assert "UTF-8" in exc_info.value.reason or "utf-8" in exc_info.value.reason.lower()

# --- AC-5: missing input/ -------------------------------------------------

def test_load_cases_missing_input_directory(tmp_bench):
    tc, cases_root = tmp_bench(case_ids=["case-1"])
    import shutil
    shutil.rmtree(cases_root / "case-1" / "input")
    with pytest.raises(BenchCaseLoadError) as exc_info:
        load_cases(tc)
    assert exc_info.value.field == "input"
    assert "input/ directory not found" in exc_info.value.reason

# --- AC-9: symlinks -------------------------------------------------------

def test_load_cases_symlink_inside_case_dir_rejected(tmp_bench, tmp_path):
    tc, cases_root = tmp_bench(case_ids=["case-1"])
    target_outside = tmp_path / "elsewhere.txt"
    target_outside.write_text("secret")
    (cases_root / "case-1" / "evil-link").symlink_to(target_outside)
    with pytest.raises(BenchCaseLoadError) as exc_info:
        load_cases(tc)
    assert exc_info.value.field == "symlink"
    assert "evil-link" in exc_info.value.reason

def test_load_cases_symlink_to_inside_also_rejected(tmp_bench):
    tc, cases_root = tmp_bench(case_ids=["case-1"])
    (cases_root / "case-1" / "self-link").symlink_to(cases_root / "case-1" / "input")
    with pytest.raises(BenchCaseLoadError) as exc_info:
        load_cases(tc)
    assert exc_info.value.field == "symlink"

# --- AC-4: input_path/expected_path traversal -----------------------------

def test_load_cases_input_path_traversal_rejected(tmp_bench):
    tc, cases_root = tmp_bench(case_ids=["case-1"])
    case_toml = cases_root / "case-1" / "case.toml"
    rewritten = case_toml.read_text().replace(
        'input_path = "input"', 'input_path = "../../etc/passwd"'
    )
    case_toml.write_text(rewritten)
    with pytest.raises(BenchCaseLoadError) as exc_info:
        load_cases(tc)
    assert exc_info.value.field == "input_path"
    assert "escapes" in exc_info.value.reason.lower()

# --- AC-15: staleness warns, does not fail --------------------------------

@pytest.mark.parametrize("days_back,should_warn", [
    (89, False),
    (90, False),  # boundary: strictly >90
    (91, True),
    (365, True),
])
def test_load_cases_stale_last_validated_at_warns_or_not(tmp_bench, days_back, should_warn):
    stale_dt = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_back)
    tc, _ = tmp_bench(case_ids=["case-1"], last_validated_at=stale_dt)
    with structlog.testing.capture_logs() as logs:
        result = load_cases(tc)
    assert len(result) == 1  # staleness must NOT shorten the tuple
    case_stale_events = [e for e in logs if e.get("event") == "loader.case_stale"]
    if should_warn:
        assert len(case_stale_events) == 1
        assert case_stale_events[0]["case_id"] == "case-1"
    else:
        assert case_stale_events == []

# --- AC-10: failure ordering ----------------------------------------------

def test_load_cases_collision_fires_before_digest_mismatch(tmp_bench, tmp_path):
    """When both defects exist, collision (3c) fires before digest compute (3f)."""
    tc, cases_root = tmp_bench(
        case_ids=["zeta-a", "zeta-b"],
        force_case_id_for={"zeta-b": "zeta-a"},
    )
    # Additionally poison zeta-a's bytes so digest would fail later.
    (cases_root / "zeta-a" / "input" / "main.txt").write_text("POISONED")
    with pytest.raises(BenchCaseIDCollision):  # NOT BenchCaseDigestMismatch
        load_cases(tc)

# --- AC-11: zero cases ----------------------------------------------------

def test_load_cases_zero_subdirectories_returns_empty_and_warns(tmp_bench):
    tc, cases_root = tmp_bench(case_ids=[])  # cases_root exists, digests.yaml is "{}\n"
    with structlog.testing.capture_logs() as logs:
        result = load_cases(tc)
    assert result == ()
    zero_events = [e for e in logs if e.get("event") == "loader.zero_cases"]
    assert len(zero_events) == 1

def test_load_cases_cases_dir_missing_typed(tmp_bench):
    tc, cases_root = tmp_bench(case_ids=["case-1"])
    import shutil
    shutil.rmtree(cases_root)
    with pytest.raises(BenchCaseLoadError) as exc_info:
        load_cases(tc)
    assert exc_info.value.field == "cases"
    assert "directory not found" in exc_info.value.reason

# --- AC-18: idempotence ---------------------------------------------------

def test_load_cases_no_global_state_side_effects(tmp_bench):
    import sys
    from codegenie.eval.registry import default_registry
    tc, _ = tmp_bench(case_ids=["case-1"])
    path_before = list(sys.path)
    modules_before = set(sys.modules)
    registry_count_before = len(default_registry.all_task_classes())
    _ = load_cases(tc)
    _ = load_cases(tc)
    assert list(sys.path) == path_before
    # load_cases must not import new modules dynamically:
    new_modules = set(sys.modules) - modules_before
    assert new_modules == set() or new_modules <= {"yaml", "tomllib"}  # lazy stdlib OK
    assert len(default_registry.all_task_classes()) == registry_count_before
```

Fence test at `tests/fence/test_eval_loader_digest_primitive.py` (AC-13):

```python
import ast
from pathlib import Path

LOADER = Path("src/codegenie/eval/loader.py")
FORBIDDEN_NAMES = frozenset({"content_hash_of_inputs", "blake3"})

def test_loader_uses_content_sensitive_digest_primitive():
    tree = ast.parse(LOADER.read_text())
    referenced = {
        node.id for node in ast.walk(tree)
        if isinstance(node, ast.Name)
    }
    referenced |= {
        node.attr for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    }
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    bad_refs = (referenced | imports) & FORBIDDEN_NAMES
    assert not bad_refs, (
        f"src/codegenie/eval/loader.py must NOT reference {bad_refs}. "
        f"`content_hash_of_inputs` hashes (path, size) only — a byte-edit "
        f"preserving size would silently pass the case-digest check, "
        f"defeating phase-arch-design.md Scenario 2. Direct `blake3` import "
        f"violates Phase 0 ADR-0001's hashing chokepoint."
    )
```

### Green

Smallest impl: §Implementation outline steps 1–6. Target ~120–180 LOC across the four functions (`load_cases` + three helpers). The growth over the original "60–80 lines" is the symlink scan, the cross-check pass, the `digests.yaml` schema validation, and the input-path traversal guard — all driven by hardened ACs.

### Refactor

- Lift the `_DIGEST_EXCLUDED_FILENAMES: Final[frozenset[str]] = frozenset({"case.toml"})` constant so future expansions (`.DS_Store`, `__pycache__/`) are a one-line data edit. This is the Open/Closed seam for digest filtering. NOT promoted to AC (Rule 2 — one excluded name today).
- Surface relative paths in error messages via `path.relative_to(case_dir).as_posix()` so test assertions don't tangle with absolute tmp paths.
- Keep helpers private (`_load_digests_yaml`, `_compute_case_dir_digest`, `_scan_for_symlinks`); unit-test them indirectly through `load_cases` invocations — promoting them to public adds API surface without consumer benefit (Rule 2).
- Do NOT add `CaseId`/`BlakeHex` type aliases — they offer zero protection over `str` and add noise. (S1-03 precedent: identifier-consolidation is deferred phase-wide.)
- Do NOT introduce a `CaseDigestStrategy` Protocol or registry — there is one strategy today; the rule-of-three threshold is not crossed. The fence test in AC-13 is the structural lock that catches the most likely failure mode (swapping primitives).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/loader.py` | Extend with `load_cases` + 3 private helpers (`_load_digests_yaml`, `_compute_case_dir_digest`, `_scan_for_symlinks`); widen `__all__` to `("load_cases", "load_task_class")`; add module-level `_DIGEST_EXCLUDED_FILENAMES` and `_WARNING_IDS` constants with startup `raise AssertionError(...)` shape validation |
| `tests/unit/eval/test_loader_cases_and_digests.py` | All red tests above (AC-1 through AC-18). Uses S2-01's autouse conftest — no new conftest |
| `tests/unit/eval/conftest.py` | Add `tmp_bench` and `fresh_tmp_bench` fixtures that scaffold a `TaskClass` + N case dirs + `digests.yaml` from a parameter list. Extend if S2-01 already created the file |
| `tests/unit/eval/_bench_fixtures.py` *(new)* | `make_case(...)` helper used by the fixture and direct test setup — keeps test bodies readable |
| `tests/fence/test_eval_loader_digest_primitive.py` *(new)* | AC-13 fence: AST-walk `loader.py` rejecting `content_hash_of_inputs` references and direct `blake3` imports |

## Out of scope

- **Runtime case execution** — handled by S3-01/S3-02 (runner). The loader only loads and verifies static facts.
- **Cache-key composition involving `case_digest`** — handled by S2-03 (cache).
- **Fence-CI AST walks for case-id uniqueness across task classes** — handled by S7-01 (PR-time defense in depth; this story is the runtime defense).
- **`cassette_path` existence verification** — the loader does NOT stat `BenchCase.cassette_path` (arch line 771 makes it `Path | None`). Phase 4's cassette layer resolves it at SUT-invocation time; the loader is fact-not-judgment.
- **`min_cases_for_promotion` floor / held-out floor enforcement** — fence-CI assertion #3 (S7-01) checks `count(c for c in cases if c.curation_class == "held-out") ≥ 5` against `task_class.min_cases_for_promotion`. This loader returns the cases unfiltered; promotion-gate readiness is the runner's / fence's check.
- **`commit_sha` required-iff-`source-not-curated` cross-field validation** — `BenchCase` Pydantic owns that rule (S1-02). The loader surfaces any Pydantic violation as `BenchCaseLoadError` via the generic AC-10 path.
- **Newtype `CaseId` / `BlakeHex`** — identifier-consolidation work is deferred phase-wide (S1-03 precedent); revisit when the newtype substrate lands.
- **`CaseDigestStrategy` Protocol or strategy registry** — one strategy today (BLAKE3-of-per-file-content); rule-of-three not crossed. Revisit when a second strategy is proposed.

## Notes for the implementer

- **Digest primitive (load-bearing).** Use `codegenie.hashing.content_hash(path)` — the per-file content BLAKE3 — composed canonically per AC-3. Do NOT use `content_hash_of_inputs` — it hashes only `(path, st_size)` records and would silently pass the Scenario 2 byte-edit attack. The fence test in AC-13 makes this guard structural; if you find yourself wanting to import `content_hash_of_inputs`, the fence will fail and you should re-read this note.
- **`blake3` chokepoint discipline.** All BLAKE3 work goes through `codegenie.hashing` (Phase 0 ADR-0001). `loader.py` must not `import blake3` directly. The canonical composition step uses BLAKE3 via the hashing module — if a chokepoint helper doesn't yet exist for "hash a stream of pre-composed bytes," add one to `hashing.py` rather than importing `blake3` locally.
- **rglob hygiene.** `Path.rglob("*")` traverses symlinks by default. AC-9's symlink scan runs BEFORE the digest compute precisely so that we never `Path.open` a symlink. Implementation order matters: scan first, then collect file paths for digest. Do not collapse the two passes; the symlink scan must be observable separately so its diagnostic carries `field="symlink"`.
- **Failure ordering.** AC-10 spells out the exact firing order. Tests rely on it (`test_load_cases_collision_fires_before_digest_mismatch`). Do not reorder for performance — the order is correctness-load-bearing because it determines which typed exception fires when multiple invariants fail simultaneously. The order is "cheap structural checks first, expensive content checks last."
- **`last_validated_at` is `datetime`, not `date`.** Pydantic parses the TOML string into a tz-aware `datetime` (arch line 768). Convert to `date` via `.date()` for the day-difference comparison; do NOT re-parse with `datetime.fromisoformat`.
- **`structlog` capture in tests.** Use `with structlog.testing.capture_logs() as logs:` (precedent: `tests/unit/parsers/test_safe_yaml.py:32`, `tests/unit/test_audit_anchors.py:172`). The `caplog` fixture is for stdlib `logging` and will not capture structlog events emitted from this loader.
- **`yaml.safe_load`, never `yaml.load`.** The `forbidden-patterns` pre-commit hook bans the unsafe variant. `digests.yaml` is short and flat — `safe_load` is sufficient and CVE-resistant.
- **Collision message determinism.** When raising `BenchCaseIDCollision`, sort the two `Path`s by `as_posix()` so test assertions don't depend on `iterdir` order across platforms.
- **`_DIGEST_EXCLUDED_FILENAMES` as Open/Closed seam.** Today the set is `frozenset({"case.toml"})`. If a future curator workflow lands `.DS_Store` files or local `__pycache__/` artifacts inside case dirs, the fix is one line of data, not a code edit. Document this in the constant's docstring so the next reader sees the extension path.
- **`expected_path` not stat'd at load time.** AC-4 verifies `expected_path` doesn't escape the case dir, but does NOT require it to exist (some rubric kinds may expect-absent-output). The "input/ dir must exist" check (AC-5) is special because arch Edge #1 names it specifically.
- **Idempotence by construction.** `load_cases` reads filesystem state and `BenchCase` is `frozen=True`; the function has no module-level cache. AC-18 verifies this — if you find yourself adding a module-level memo, you've drifted from the design (the runner's cache layer (S2-03) is the right place for any caching).
- **Zero-cases warning vs error split.** The loader returns an empty tuple AND warns; it does NOT raise. This is because some test invocations (a fresh task class being scaffolded) legitimately have zero cases. The runner's `min_cases_for_promotion` floor is the enforcement seam — fence-CI (S7-01 assertion #2) catches this at PR time for production task classes; the loader is permissive at runtime.
- **Surfaced doc drift (not auto-fixed by this story).** `final-design.md §Failure modes` row "case.toml malformed" line 316 says exclude-and-continue (exit code 1). `phase-arch-design.md §Scenario 2` + `§Control flow §Decision point #6` (newer) say abort fail-fast (exit code 6). The story follows arch (correct). Flag for a follow-on doc-sweep PR; do not auto-edit `final-design.md` from this story.
