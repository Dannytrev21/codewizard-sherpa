# Story S4-03 — `codegenie eval verify` subcommand for chain integrity

**Step:** Step 4 — Wire the CLI and the read-only promotion gate
**Status:** HARDENED (phase-story-validator, 2026-06-01)
**Effort:** S
**Depends on:** S4-01 (CLI scaffold + `eval_group` symbol + `EXIT_SUCCESS`/`EXIT_CHAIN_TAMPER`/`--format` group option), S2-04 (audit chain extension + `VerifyResult(ok, verified_complete, verified_incomplete, tampered_path, reason)`)
**ADRs honored:** ADR-0002 (`lower_bound_95` is the gate signal; verify surfaces partial-record breakdown so partials cannot be miscounted as evidence), ADR-0010 (`isolation_class` annotated on every record — surfaced in human-format table for operator inspection), Phase 0 ADR-0014 (BLAKE3 chain primitive reuse via S2-04), Gap #4 (`complete: bool` on `BenchRunReport`)

## Validation notes (phase-story-validator, 2026-06-01)

This story was hardened in place. All findings (12 — 5 block, 6 harden, 1 nit) are patchable against the hardened sibling contracts; **HARDENED, not RESCUE**. Conflict-resolution priority applied: **Consistency > Coverage > Test-Quality > Design-Patterns**. The dominant lens is Consistency — the story drifted from S2-04's wire shape and S4-01's exported symbol after both were hardened.

### Consistency

- **F-CON-1 (BLOCK) — `tamper_at` does not exist on `VerifyResult`; the field is `tampered_path`.** S2-04 HARDENED AC-4 + AC-13 pin the field name as `tampered_path: Path | None`. The original ACs (lines 36–37), Notes (line 197), and outline used `tamper_at` throughout — a name S4-04 (also `Ready`, not yet validated) shares; that drift is logged for a follow-on S4-04 validator pass but not auto-fixed here (Rule 3 — surgical). Every occurrence in this story is now `tampered_path`. The JSONL key the CLI emits is also `"tampered_path"` (stringified) — the CLI does not invent a synonym.
- **F-CON-2 (BLOCK) — `audit.verify` returns; it never raises.** Outline step 2.b said "`raises ChainTamperDetected` *only* in the synchronous-walk variant" and asked the implementer to "catch and convert." S2-04 AC-4 is explicit: `verify(out_dir, since=None) -> VerifyResult`; tamper is signalled as `VerifyResult(ok=False, tampered_path=…, reason=…)`. The runner (S3-01 AC-4) re-raises `ChainTamperDetected` itself, but the standalone CLI path **never** sees an exception from `verify`. Outline rewritten; the catch-and-convert language is removed.
- **F-CON-3 (BLOCK) — symbol import name.** The TDD plan said `from codegenie.eval.cli import eval as eval_group`. S4-01 HARDENED AC-1 (F-CON-3) renamed the exported symbol to **`eval_group`** directly to avoid shadowing the `eval()` builtin. There is no `eval` alias. All imports → `from codegenie.eval.cli import eval_group`.
- **F-CON-4 (BLOCK) — `--since` lexicographic-vs-ISO mismatch.** S2-04 AC-4a pins `since` as an **inclusive filename-prefix lexicographic** filter against `*.json` files whose names are `f"{utc_iso}-{secrets.token_hex(4)}.json"` with `:` → `-` substitution (S2-04 outline line 144). The original `--since=2099-01-01T00:00:00Z` test value contains literal `:` (ASCII 58) — lexicographically greater than `-` (ASCII 45) — so the filter happened to work by accident for the "after everything" case but would silently misfilter realistic `--since=2026-05-26T14:32:08Z` values (filenames starting `2026-05-26T14-32-08…` sort *below* the search string, excluding records that should match). **Resolution:** the CLI normalizes `--since` at the boundary via `_normalize_since(s: str) -> str` (replace `":"`→`"-"` after a `click.DateTime`-validated parse), then passes the normalized string to `audit.verify`. The normalization is the single coupling point to S2-04's filename convention and is the testable behaviour pinned by AC-3+AC-3a. Invalid ISO → click usage error (exit 2 via click; out of `_map_exception_to_exit_code`).
- **F-CON-5 (BLOCK) — `first_record_iso` / `last_record_iso` are not on `VerifyResult`.** Original ACs (line 36) and Notes (line 198) promised these as JSONL fields. S2-04's `VerifyResult` has five fields: `(ok, verified_complete, verified_incomplete, tampered_path, reason)`. Resolution: the CLI **derives** the bracket-ISO pair from a `sorted(out_dir.glob("*.json"))` walk on the same `out_dir` (cheap — directory listing, no JSON parse) and emits them under the explicit key names `first_record_filename` / `last_record_filename` (since they are filename-prefix ISOs, not the canonical UTC ISO of `run_started_iso` — naming the wire field by its derivation prevents operators mistaking them for a content field). When the chain is empty both are `null`. When the chain has one record both equal that record's filename.
- **F-CON-6 (HARDEN) — test path convention.** Original "Files to touch" placed tests at `tests/integration/test_cli_verify.py` (flat). S4-02 validation F-CON-9 established `tests/integration/eval/` for eval CLI integration tests (mirrors `tests/unit/eval/` from S4-01 F-CON-1). Path → `tests/integration/eval/test_cli_verify.py`; fixtures → `tests/integration/eval/conftest.py`. No existing-file collision either way; convention is load-bearing for discoverability.
- **F-CON-7 (HARDEN) — `--format` is GROUP-level, set on `eval_group`, not on `verify`.** S4-01 AC-4 pinned `--format=human|jsonl` (default `jsonl`) as a **group-level** option whose value lands in `ctx.obj["format"]`. Tests must pass `--format` BEFORE the subcommand (`runner.invoke(eval_group, ["--format=human", "verify"])`), not as a subcommand-local option. Verify's body reads `ctx.obj["format"]`. Documented in outline; the human-format test already gets this right (line 148 of original).

### Coverage

- **F-COV-1 (HARDEN) — `reason` field is dropped from the JSONL on the failure path.** S2-04 returns `reason: str | None` carrying `"parse_error: …"`, `"content_hash mismatch"`, or `"prev_hash mismatch"` — operator-facing diagnostic that distinguishes byte-flip vs prev-hash divergence vs malformed JSON. The original tamper AC only required `tamper_at`. New AC emits `"reason"` in JSONL on `ok=False` and asserts it is non-empty (separately for tamper vs parse-error cases).
- **F-COV-2 (HARDEN) — stop-on-first-mismatch counts are not asserted.** S2-04 AC-13 pins that on tamper at record k (1-indexed), `verified_complete + verified_incomplete` equals the records *before* k (records 0..k-2 inclusive in zero-indexed terms; k-1 records). The CLI must surface those partial counts in the failure-JSONL so operators see how much of the chain was verified before divergence. New AC asserts `verified_complete + verified_incomplete == k - 1` on the tamper case.
- **F-COV-3 (HARDEN) — malformed-`--since` exit semantics undefined.** A garbage ISO string (`--since=foo`) had no documented exit code. Resolution: declare `--since` via `click.DateTime(formats=["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"])` so click rejects malformed values with its usage-error exit (typically 2). This is **distinct from** `EXIT_COST_CAP=2`; the click usage-error path bypasses `_map_exception_to_exit_code` entirely and is fine. New AC pins both the valid-ISO acceptance and the malformed-ISO rejection.
- **F-COV-4 (HARDEN) — missing-`out` (path doesn't exist) is conflated with empty `out`.** S2-04 AC-4 distinguishes "missing dir" and "empty dir" (both return `ok=True, 0, 0, None, None`). The CLI must treat them identically. New AC tests `--out=/nonexistent/path` explicitly and asserts exit 0, JSONL counts both zero, **without** creating the path (operator-supplied paths are not silently `mkdir`'d).
- **F-COV-5 (HARDEN) — human-format per-record fields require re-globbing, not VerifyResult.** AC-6 promises `run_id / run_started_iso / complete / isolation_class / chain_head[:8]` per row. None of those are on `VerifyResult`. Resolution: `_render_human_table(out_dir, since)` re-globs `out_dir`, lazy-loads each `*.json` once (`json.loads` only — no Pydantic; the rendering is informational, not a re-verify), and emits the table. This is consistent with `_derive_filename_bracket` (F-CON-5). Documented in outline + Notes; not a hidden cost.

### Test-Quality

- **F-TQ-1 (HARDEN) — JSONL type assertions are too loose.** Original tests only check key presence (`payload["ok"] is True`). A mutant emitting `"ok": "true"` (string), `"verified_complete": "0"` (string), or `"tampered_path": null` when there was actual tamper would pass several of the original assertions. Strengthen: `isinstance(payload["ok"], bool)`, `isinstance(payload["verified_complete"], int)`, `isinstance(payload["verified_incomplete"], int)`, and on the tamper path `isinstance(payload["tampered_path"], str) and Path(payload["tampered_path"]).name.endswith(".json")`.
- **F-TQ-2 (HARDEN) — `--strict` test is too weak.** Original asserts `"incomplete" in stderr.lower()` — would pass if the warning just said "incomplete: see docs" without ever naming a run_id. Strengthen: assert *every* `run_id` from `complete=False` records appears in stderr; assert no run_id from `complete=True` records appears (false-positive guard).
- **F-TQ-3 (HARDEN) — `--format=human` test doesn't pin row count or column structure.** Original only checks `"verified_complete" in output`. A mutant that emits an empty table with just the footer would pass. Strengthen: row count equals number of records, every column header is present, each row contains the corresponding record's `run_id` substring.
- **F-TQ-4 (HARDEN) — chain-walked `since` filter semantics need a metamorphic test.** Walking the same chain twice — once unfiltered, once with `since=record_k_name` — must produce verifiable count relationships (`unfiltered.verified_complete + unfiltered.verified_incomplete == N`; `filtered total == N - k + 1` inclusive). Original only tested the "filter excludes everything" edge. Added a 3-record metamorphic case.
- **F-TQ-5 (HARDEN) — empty-chain test mode under `--format=human`.** The default-jsonl empty-chain test exists. Add an empty-chain `--format=human` test asserting a one-line footer with zero counts and no table rows; pins that `_render_human_table` handles the empty case without IndexError.

### Design-Patterns

- **F-DP-1 (HARDEN — Notes only, not AC) — format dispatch should mirror S4-02's `_EMITTERS` map.** S4-02's validation F-DP-2 surfaced the `_EMITTERS: Final[Mapping[str, Callable[..., None]]]` pattern (Strategy via dict, keyed on `ctx.obj["format"]`). S4-03 is the second emitter site. Per Rule 2 (three similar lines is better than premature abstraction), do NOT extract a shared module-level kernel yet — but structure this story's emitters as a **local** `_VERIFY_EMITTERS: Final[Mapping[str, Callable[[VerifyResult, Path, str | None, TextIO], None]]]` dispatch map mirroring S4-02's shape. The third format-emitting subcommand (`promote-verdict` — S4-05's recommendation summary) crosses the rule of three and would extract; until then, intentional duplication is correct. Surfaced as a Notes paragraph; not an AC (pattern-name mandates are not observable).
- **F-DP-2 (NIT) — `_normalize_since` is the single coupling point to S2-04's filename convention.** Naming it explicitly (rather than inlining `s.replace(":", "-")`) makes the coupling visible and testable. Pinned in outline + Notes; tested directly in unit tests so a future S2-04 filename-format change is loud, not silent.

### Cross-story drift surfaced, not auto-fixed
- **S4-04 (`Ready`) uses `tamper_at` in the same way S4-03 originally did.** F-CON-1 fix here renames the field per S2-04 HARDENED; S4-04 will need the same rename when it goes through its validator pass. Flagged; not auto-edited (one story per invocation; Rule 3).
- **`arch design §cli.py`** mentions `codegenie eval verify [--since=<iso>] [--out=<path>]` (line 688) — does NOT include `--strict` or `--format` flags. Story is the canonical reference; arch is stale on flag list. Flag for a follow-on doc-sweep PR; not auto-edited.

Full audit log: this `Validation notes` block + the `_validation/S4-03-eval-verify-subcommand.md` report.

## Context

`codegenie eval verify` walks the audit chain at `.codegenie/eval/runs/` (and any `--out` override), recomputes BLAKE3 link hashes via S2-04's `audit.verify(out_dir, since) -> VerifyResult`, and reports a clean / tampered verdict. The audit chain is the load-bearing evidence trail for promotion (S4-04 reads it); a silently-tampered chain corrupts every downstream verdict. Operators run `verify` as a CI gate (nightly) and as a forensics tool after suspected drift. Per Gap #4 / ADR-0004 §Consequences, partial reports (`complete=False`) are real history — `verify` must walk them, but the result must distinguish "verified-complete N" from "verified-incomplete M" so operators see the breakdown and S4-04 knows how many records qualify as promotion evidence.

This story is a **thin CLI veneer over S2-04's pure `audit.verify(out_dir, since) -> VerifyResult`** (which **returns** a result; it does **not** raise — the runner's tamper-then-raise path is owned by S3-01). The exit-code mapping is the load-bearing contract: `EXIT_SUCCESS=0` on clean, `EXIT_CHAIN_TAMPER=5` on tamper (constants imported from `codegenie.eval.cli`, defined by S4-01). The `--strict` flag tightens diagnostics — when a non-empty `verified_incomplete` count is present and `--strict` is set, the CLI writes a stderr warning naming each incomplete `run_id` and its `run_started_iso`; it does **not** escalate to a non-zero exit (partials are valid history that the chain must retain; operators wanting strict-no-partials gate via `--strict | grep -q 'verified_incomplete=0'` themselves).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design → src/codegenie/eval/cli.py` (line 681–695) — names `verify [--since=<iso>] [--out=<path>]`; this story extends with `--strict` and inherits `--format` from S4-01's group-level option.
  - `../phase-arch-design.md §Component design → src/codegenie/eval/audit.py` (line 618–630) — `verify(out_dir: Path, since: str | None = None) -> VerifyResult` is the callable; returns `VerifyResult`, never raises.
  - `../phase-arch-design.md §Failure modes #11` (line 954) — chain-tamper at startup exits code 5 *before* any SUT invocation; `verify` is the dedicated tool for the same check standalone.
  - `../phase-arch-design.md §Gap analysis Gap 4` (line 1170) — `audit.verify(...)` distinguishes "verified-complete N records" from "verified-incomplete M records" via `VerifyResult` fields; the CLI surfaces both.
- **Phase ADRs:**
  - `../ADRs/0002-promotion-gate-keys-on-lower-bound-95.md` §Consequences — partial reports cannot be evidence; `verify`'s incomplete-count surface is how operators see that gap.
  - `../ADRs/0010-isolation-class-annotation-on-bench-run-report.md` §Consequences — `verify --strict` may extend in a follow-up to refuse mixed isolation-class windows; this story does not implement that, but the human-format table surfaces the field per record so the future check is mechanical.
- **Production ADRs:**
  - `../../../production/adrs/0009-humans-always-merge.md` — `verify` is read-only by construction; no flag mutates the chain.
- **Sibling stories (read these before implementing):**
  - `S2-04-audit-chain-extension.md` (HARDENED) — **source of truth** for `VerifyResult` shape (`ok, verified_complete, verified_incomplete, tampered_path, reason`), `since` semantics (inclusive filename-prefix lexicographic), filename convention (`:` → `-` substitution).
  - `S4-01-cli-scaffold-exit-codes.md` (HARDENED) — exports `eval_group`, `EXIT_SUCCESS`, `EXIT_CHAIN_TAMPER`, group-level `--format`.
  - `_validation/S4-02-eval-run-subcommand.md` (HARDENED) — established the eval CLI integration test path convention (`tests/integration/eval/`) and the `_EMITTERS` format-dispatch idiom this story mirrors.
- **Source design:** `../High-level-impl.md §Step 4` — names the flag list (`--since`, `--strict`) and the exit semantics (0 clean / 5 tamper).
- **Phase 0 precedent:** `../../00-bullet-tracer-foundations/ADRs/0014-blake3-audit-chain.md` — the BLAKE3 chain primitives S2-04 walks (and which S4-03 consumes transitively via `VerifyResult`).

## Goal

Implement `codegenie eval verify [--since=<utc-iso>] [--strict] [--out=<path>]` (`--format=human|jsonl` inherited from `eval_group` at group level) by delegating to S2-04's `audit.verify(out_dir, normalized_since) -> VerifyResult`, normalizing `--since`'s colon to hyphen at the CLI boundary to match S2-04's filename convention, and mapping `VerifyResult.ok` to `EXIT_SUCCESS` (clean) or `EXIT_CHAIN_TAMPER` (tamper). Surface the `(verified_complete, verified_incomplete, tampered_path, reason)` quartet on stdout in either JSONL or human-readable form; on `--strict`, additionally write a stderr warning that names each incomplete `run_id` and its `run_started_iso`.

## Acceptance criteria

- [ ] **AC-1.** `codegenie eval verify` over a clean chain (one or more `BenchRunReport`s from S2-04's test-fixture writers) exits `EXIT_SUCCESS` (0). Stdout (default `--format=jsonl`, inherited from `eval_group`) emits exactly one aggregate line: `{"kind": "verify", "ok": true, "verified_complete": <int>, "verified_incomplete": <int>, "first_record_filename": "<str|null>", "last_record_filename": "<str|null>"}`. Field-type assertions are *typed*: `isinstance(payload["ok"], bool)`, `isinstance(payload["verified_complete"], int)`, `isinstance(payload["verified_incomplete"], int)`, `payload["first_record_filename"]` is either `None` or a `str` ending in `.json`. The `first_record_filename` / `last_record_filename` pair is derived by the CLI from `sorted(out_dir.glob("*.json"))` (F-CON-5) — they are NOT fields of `VerifyResult`.
- [ ] **AC-2.** `codegenie eval verify` over a tampered chain (byte-flipped record per S2-04 AC-7 fixture) exits `EXIT_CHAIN_TAMPER` (5). Stdout emits a single aggregate line with `"ok": false`, plus `"tampered_path": "<filesystem path ending in .json>"` (stringified `Path`, **not** named `tamper_at`) and `"reason": "<non-empty string>"` (the operator-facing diagnostic from `VerifyResult.reason` — substring `"content_hash"`, `"prev_hash"`, or `"parse_error"` depending on failure type). Type assertions: `payload["ok"] is False`, `isinstance(payload["tampered_path"], str)`, `isinstance(payload["reason"], str) and payload["reason"] != ""`.
- [ ] **AC-3.** `--since=<utc-iso>` filters the walk to records whose filename sorts lexicographically `>=` the normalized `since` value. The CLI normalizes the raw `--since` string via `_normalize_since(s: str) -> str` (replaces `":"` with `"-"` — the single coupling point to S2-04's filename convention; mirrors S2-04 outline line 144). `_normalize_since` is unit-tested in isolation so a future filename-convention change in S2-04 is detected loudly. Test: write three records `r1, r2, r3`; `verify --since=<r2_filename>` returns `verified_complete + verified_incomplete == 2` (records `r2`, `r3`); `verify` (no filter) returns `3`. Edge case: a `--since` ISO that excludes all records → exit 0 with `verified_complete=0, verified_incomplete=0`.
- [ ] **AC-3a.** `--since` accepts strict ISO 8601 via `click.DateTime(formats=["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"])`. Click parses, then `str(parsed.replace(tzinfo=…))` is re-emitted as ISO and normalized. **Malformed `--since` (e.g., `--since=garbage`) is rejected by click with its usage-error exit code (typically 2 from click, bypassing `_map_exception_to_exit_code`)**; stderr names the option and a one-line valid-format hint. The verify body is never entered.
- [ ] **AC-4.** `--strict`: when set AND `VerifyResult.verified_incomplete > 0`, the CLI writes a stderr warning that lists **every** incomplete `run_id` paired with its `run_started_iso` (one per line, prefixed `incomplete:`); the exit code is **still** `EXIT_SUCCESS` on a clean chain or `EXIT_CHAIN_TAMPER` on tamper. The flag does NOT escalate "incomplete records exist" to a tamper. False-positive guard: no `run_id` from a `complete=True` record appears in the warning. Implementation note: `verified_incomplete` is a count on `VerifyResult`; surfacing per-record `run_id`/`run_started_iso` requires re-globbing + JSON-loading `*.json` files where `complete is False` (re-uses the same glob `_render_human_table` and `_derive_filename_bracket` use; see Implementation outline).
- [ ] **AC-5.** `--out=<path>` optional override for the chain directory; default `Path(".codegenie/eval/runs")` (relative to CWD; operators are expected to chdir if scripting). When `--out` points to a path that does **not** exist on disk, the CLI does NOT `mkdir` it — instead it propagates S2-04's "missing dir == empty chain" semantic (AC-4): exit 0, both counts zero, `first_record_filename=null`, `last_record_filename=null`. This pins the surgical-changes discipline (Rule 3) — `verify` is read-only and never has a side-effect on the filesystem.
- [ ] **AC-6.** `--format=human` (passed at the group level: `codegenie eval --format=human verify`) prints a table with columns `run_id / run_started_iso / complete / isolation_class / chain_head[:8]` (one row per record in the filtered window) and a footer `verified_complete=N verified_incomplete=M` plus `tampered_path=<path|none>` and `reason=<str|none>` on the failure path. Row count = number of records in the filtered window. Each header literal is present; each row contains the corresponding record's `run_id` as a substring. Empty chain → footer-only output (zero counts, no rows, no IndexError). The per-record fields are derived by the CLI re-globbing `out_dir` and `json.loads`-ing each record (no Pydantic — informational rendering, not re-verification).
- [ ] **AC-7.** Empty chain semantics (missing OR existing-but-empty `out_dir`): exits `EXIT_SUCCESS` with `verified_complete=0, verified_incomplete=0, tampered_path=null, reason=null, first_record_filename=null, last_record_filename=null`. Not an error — first-time runs and pre-existing operators are clean by definition.
- [ ] **AC-8.** **Stop-on-first-mismatch counts surface on tamper.** Given a chain of 5 records where record 3 (1-indexed) is tampered, the failure JSONL satisfies `verified_complete + verified_incomplete == 2` (records 1 and 2 — the records *before* the divergence; mirrors S2-04 AC-13). `tampered_path` is the filename of record 3.
- [ ] **AC-9.** **Heavy imports remain deferred.** The `verify` command body's `from codegenie.eval.audit import verify as audit_verify` (and any model imports) are function-scoped, NOT module-top. S4-01's cold-start guard test (`tests/unit/eval/test_cli_scaffold.py::test_cold_start_no_heavy_imports`) stays green after this story lands — re-running it is part of the CI gate.
- [ ] **AC-10.** **`_normalize_since` is unit-tested directly.** `tests/unit/eval/test_cli_verify_normalize_since.py`: `_normalize_since("2026-05-26T14:32:08Z") == "2026-05-26T14-32-08Z"`; idempotent on already-normalized values; preserves filename suffixes if present. Pins the single coupling point to S2-04's filename convention so a future S2-04 wire change is loud.
- [ ] **AC-11.** The red tests from §TDD plan exist under `tests/integration/eval/` and `tests/unit/eval/`, were committed at the red marker, and are now green.
- [ ] **AC-12.** `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/eval/cli.py`, and `pytest tests/integration/eval/test_cli_verify.py tests/unit/eval/test_cli_verify_normalize_since.py` all pass on touched files.

## Implementation outline

1. **Write red tests first** — see §TDD plan. Fixtures (`clean_two_record_chain`, `tampered_chain`, `partial_then_complete_chain`, `five_record_chain_with_r3_tampered`) belong in `tests/integration/eval/conftest.py`; they construct on-disk chains using S2-04's `write_run_record` and (for tamper cases) flip bytes directly on disk per S2-04 AC-7 (byte-flip the `run_id` text field — preserves JSON validity so BLAKE3 divergence is the only signal).
2. **Add the `_normalize_since` helper at module top of `src/codegenie/eval/cli.py`** (no heavy imports — pure stdlib):
   ```python
   _COLON: Final[str] = ":"
   _DASH: Final[str] = "-"

   def _normalize_since(s: str) -> str:
       """Single coupling point to S2-04's filename convention.

       S2-04 outline line 144: filenames substitute ``:`` -> ``-`` for FS safety.
       A ``--since`` value from the operator is a canonical ISO with colons;
       it must be normalized to match the on-disk filename prefix before
       passing to ``audit.verify``.
       """
       return s.replace(_COLON, _DASH)
   ```
3. **Define `--since` via `click.DateTime`** with the three accepted format strings (AC-3a). Click rejects malformed values with a usage error before the body runs.
4. **Fill in the `verify` subcommand stub from S4-01:**
   - Click options on the subcommand: `--since` (`click.DateTime(...)`, default `None`), `--strict` (flag), `--out` (`click.Path(path_type=pathlib.Path)`, default `Path(".codegenie/eval/runs")` — NOT `click.Path(exists=True)`; we want missing-path → empty-chain semantics per AC-5).
   - Body (deferred imports inside the function):
     1. `from codegenie.eval.audit import verify as audit_verify`.
     2. `from codegenie.eval.cli import EXIT_SUCCESS, EXIT_CHAIN_TAMPER`.
     3. `normalized_since = _normalize_since(since.isoformat()) if since is not None else None`.
     4. `result: VerifyResult = audit_verify(out_dir=out, since=normalized_since)` — **never wrapped in try/except for `ChainTamperDetected`**; S2-04 AC-4 guarantees the return-only contract. (A bare `except` to map unexpected `OSError` from a corrupt filesystem to `EXIT_GENERIC_ERROR` is fine — S4-01's `main()` wrapper handles that.)
     5. Compute `first_fn, last_fn = _derive_filename_bracket(out, normalized_since)` (helper that globs once; cheap).
     6. Dispatch on `ctx.obj["format"]` via the local `_VERIFY_EMITTERS` map → emit JSONL or human format.
     7. If `--strict` and `result.verified_incomplete > 0`: call `_emit_incomplete_warning(out, normalized_since, sys.stderr)` (re-globs, loads `*.json` files where `complete is False`, emits one stderr line per record). Exit code unaffected.
     8. `sys.exit(EXIT_SUCCESS if result.ok else EXIT_CHAIN_TAMPER)`.
5. **Local Strategy via dict** — mirror S4-02 F-DP-2's pattern, but local to verify (Rule 2 — three similar lines is better than premature abstraction; the third format-emitter site will trigger an extract):
   ```python
   _VERIFY_EMITTERS: Final[Mapping[str, Callable[[VerifyResult, Path, str | None, TextIO], None]]] = {
       "jsonl": _emit_verify_jsonl,
       "human": _emit_verify_human,
   }
   ```
   A future `--format=csv` is one row in the map, not a branch.
6. **Helpers (all `_`-prefixed, all function-scoped imports for anything heavy):**
   - `_derive_filename_bracket(out_dir: Path, since: str | None) -> tuple[str | None, str | None]` — `sorted(out_dir.glob("*.json"))`, filtered by `since` prefix; returns the first/last names or `(None, None)` on empty.
   - `_emit_verify_jsonl(result: VerifyResult, out_dir: Path, since: str | None, stream: TextIO) -> None` — writes one JSON line per AC-1 / AC-2 shape.
   - `_emit_verify_human(result: VerifyResult, out_dir: Path, since: str | None, stream: TextIO) -> None` — re-globs, `json.loads`-only each record, renders a small hand-rolled table (no `tabulate` dependency; cold-start budget).
   - `_emit_incomplete_warning(out_dir: Path, since: str | None, stream: TextIO) -> None` — for AC-4; uses `click.echo(..., err=True)`.
7. **Run** `ruff format`, `ruff check`, `mypy --strict`, `pytest tests/integration/eval/test_cli_verify.py tests/unit/eval/test_cli_verify_normalize_since.py tests/unit/eval/test_cli_scaffold.py::test_cold_start_no_heavy_imports`.

## TDD plan — red / green / refactor

### Red — write the failing tests first

```python
# tests/unit/eval/test_cli_verify_normalize_since.py
"""AC-10 — pin the single coupling point to S2-04's filename convention."""
from codegenie.eval.cli import _normalize_since


def test_normalize_since_replaces_colon_with_dash():
    assert _normalize_since("2026-05-26T14:32:08Z") == "2026-05-26T14-32-08Z"


def test_normalize_since_is_idempotent_on_already_normalized():
    assert _normalize_since("2026-05-26T14-32-08Z") == "2026-05-26T14-32-08Z"


def test_normalize_since_preserves_suffixes():
    # The .json suffix is not present in operator-supplied --since, but
    # the helper must not surprise a future caller that does pass one.
    assert _normalize_since("2026-05-26T14:32:08+00:00.json") == "2026-05-26T14-32-08+00-00.json"


def test_normalize_since_preserves_empty_string():
    assert _normalize_since("") == ""
```

```python
# tests/integration/eval/test_cli_verify.py
import json
from pathlib import Path
from click.testing import CliRunner
from codegenie.eval.cli import eval_group  # AC: F-CON-3 — symbol is eval_group, NOT eval


# === AC-7 (empty chain — existing-but-empty out_dir) ========================
def test_verify_empty_chain_exits_zero(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".codegenie" / "eval" / "runs").mkdir(parents=True)
    runner = CliRunner()
    result = runner.invoke(eval_group, ["verify"], catch_exceptions=False)
    assert result.exit_code == 0
    payload = next(json.loads(ln) for ln in result.output.splitlines() if ln.startswith("{"))
    assert payload["kind"] == "verify"
    assert payload["ok"] is True and isinstance(payload["ok"], bool)
    assert payload["verified_complete"] == 0 and isinstance(payload["verified_complete"], int)
    assert payload["verified_incomplete"] == 0 and isinstance(payload["verified_incomplete"], int)
    assert payload["first_record_filename"] is None
    assert payload["last_record_filename"] is None


# === AC-5 + AC-7 (missing-dir is empty-chain, no side-effect mkdir) =========
def test_verify_missing_out_dir_is_empty_chain_no_mkdir(tmp_path, monkeypatch):
    """The CLI must not create operator-supplied paths."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "does" / "not" / "exist"
    assert not target.exists()
    runner = CliRunner()
    result = runner.invoke(
        eval_group, ["verify", "--out", str(target)], catch_exceptions=False
    )
    assert result.exit_code == 0
    assert not target.exists(), "verify must NOT create the path operator supplied"
    payload = next(json.loads(ln) for ln in result.output.splitlines() if ln.startswith("{"))
    assert payload["ok"] is True
    assert payload["verified_complete"] == 0 and payload["verified_incomplete"] == 0


# === AC-1 (clean chain — typed assertions, no untyped key-presence) =========
def test_verify_clean_two_record_chain_exits_zero(clean_two_record_chain, monkeypatch):
    monkeypatch.chdir(clean_two_record_chain.parent)
    runner = CliRunner()
    result = runner.invoke(
        eval_group, ["verify", "--out", str(clean_two_record_chain)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    payload = next(json.loads(ln) for ln in result.output.splitlines() if ln.startswith("{"))
    assert payload["ok"] is True and isinstance(payload["ok"], bool)
    assert payload["verified_complete"] == 2 and isinstance(payload["verified_complete"], int)
    assert payload["verified_incomplete"] == 0
    # AC-1: derived from glob, not from VerifyResult
    assert isinstance(payload["first_record_filename"], str)
    assert payload["first_record_filename"].endswith(".json")
    assert isinstance(payload["last_record_filename"], str)
    assert payload["last_record_filename"].endswith(".json")


# === AC-2 (tamper exit + reason surfacing) ==================================
def test_verify_tampered_chain_exits_five(tampered_chain, monkeypatch):
    """One byte flipped in the first record after the second was chained."""
    monkeypatch.chdir(tampered_chain.parent)
    runner = CliRunner()
    result = runner.invoke(
        eval_group, ["verify", "--out", str(tampered_chain)],
        catch_exceptions=False,
    )
    assert result.exit_code == 5  # EXIT_CHAIN_TAMPER, NOT a hardcoded magic 5 in production code
    payload = next(json.loads(ln) for ln in result.output.splitlines() if ln.startswith("{"))
    assert payload["ok"] is False
    # F-CON-1 — field is tampered_path, NOT tamper_at (S2-04 source of truth)
    assert isinstance(payload["tampered_path"], str)
    assert Path(payload["tampered_path"]).name.endswith(".json")
    # F-COV-1 — reason is the operator's diagnostic; not optional on failure
    assert isinstance(payload["reason"], str) and payload["reason"] != ""
    # The tamper reason from S2-04 AC-7 contains "content_hash" for byte-flip;
    # this asserts the wire passes the diagnostic through faithfully.
    assert "content_hash" in payload["reason"] or "prev_hash" in payload["reason"]


# === AC-8 (stop-on-first-mismatch — partial counts surface) =================
def test_verify_tamper_surfaces_partial_counts(five_record_chain_with_r3_tampered, monkeypatch):
    """S2-04 AC-13 — chain[0..k-2] verified; verify must surface those counts."""
    out = five_record_chain_with_r3_tampered
    monkeypatch.chdir(out.parent)
    result = CliRunner().invoke(
        eval_group, ["verify", "--out", str(out)], catch_exceptions=False
    )
    assert result.exit_code == 5
    payload = next(json.loads(ln) for ln in result.output.splitlines() if ln.startswith("{"))
    assert payload["ok"] is False
    # Records 1, 2 verified before divergence at record 3.
    assert payload["verified_complete"] + payload["verified_incomplete"] == 2
    assert "record-3" in payload["tampered_path"] or payload["tampered_path"].endswith(".json")


# === AC-3 + AC-3a (since filter — metamorphic; valid ISO) ===================
def test_verify_since_filter_inclusive(three_record_chain, monkeypatch):
    """verify() == 3 records; verify(since=r2_iso) == 2 records (r2 + r3)."""
    out, (r1_iso, r2_iso, r3_iso) = three_record_chain  # ISOs in canonical colon form
    monkeypatch.chdir(out.parent)
    runner = CliRunner()
    unfiltered = runner.invoke(
        eval_group, ["verify", "--out", str(out)], catch_exceptions=False
    )
    p_un = next(json.loads(ln) for ln in unfiltered.output.splitlines() if ln.startswith("{"))
    assert p_un["verified_complete"] + p_un["verified_incomplete"] == 3

    filtered = runner.invoke(
        eval_group,
        ["verify", "--out", str(out), "--since", r2_iso],
        catch_exceptions=False,
    )
    p_f = next(json.loads(ln) for ln in filtered.output.splitlines() if ln.startswith("{"))
    assert p_f["verified_complete"] + p_f["verified_incomplete"] == 2


def test_verify_since_excludes_all_records_returns_zero(clean_two_record_chain, monkeypatch):
    monkeypatch.chdir(clean_two_record_chain.parent)
    result = CliRunner().invoke(
        eval_group,
        ["verify", "--out", str(clean_two_record_chain), "--since", "2099-01-01T00:00:00Z"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    payload = next(json.loads(ln) for ln in result.output.splitlines() if ln.startswith("{"))
    assert payload["verified_complete"] == 0
    assert payload["verified_incomplete"] == 0


def test_verify_since_malformed_iso_exits_via_click_usage(tmp_path, monkeypatch):
    """AC-3a — click rejects garbage before the body runs; no body-side mapping."""
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        eval_group, ["verify", "--since", "not-an-iso"], catch_exceptions=False
    )
    # click's usage error exits non-zero (typically 2); the body never runs,
    # so EXIT_CHAIN_TAMPER (5) and EXIT_GENERIC_ERROR (1) are wrong here.
    assert result.exit_code != 0
    assert result.exit_code != 5
    assert "--since" in (result.output + (result.stderr or ""))


# === AC-4 (--strict — every incomplete run_id surfaced; complete ones absent)
def test_verify_strict_lists_every_incomplete_run_id_in_stderr(
    partial_and_complete_chain, monkeypatch
):
    """Chain: r1 complete=False (partial:r1-xxx), r2 complete=True (r2-good)."""
    out, partial_ids, complete_ids = partial_and_complete_chain
    monkeypatch.chdir(out.parent)
    runner = CliRunner()
    result = runner.invoke(
        eval_group,
        ["verify", "--out", str(out), "--strict"],
        mix_stderr=False,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    stderr = result.stderr or ""
    # Every partial run_id surfaced (positive — guards the mutant that just
    # prints "incomplete: see docs" without enumerating).
    for rid in partial_ids:
        assert rid in stderr, f"incomplete run_id {rid!r} not surfaced in --strict stderr"
    # No complete run_id appears (false-positive guard — the mutant that
    # prints every run_id regardless of complete status).
    for rid in complete_ids:
        assert rid not in stderr, f"complete run_id {rid!r} should NOT appear in incomplete warning"


def test_verify_strict_on_clean_complete_chain_emits_no_warning(
    clean_two_record_chain, monkeypatch
):
    monkeypatch.chdir(clean_two_record_chain.parent)
    result = CliRunner().invoke(
        eval_group,
        ["verify", "--out", str(clean_two_record_chain), "--strict"],
        mix_stderr=False,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "incomplete" not in (result.stderr or "").lower()


# === AC-6 (--format=human — table structure, row count, headers) ============
def test_verify_human_format_emits_table_with_one_row_per_record(
    clean_two_record_chain, monkeypatch
):
    monkeypatch.chdir(clean_two_record_chain.parent)
    result = CliRunner().invoke(
        eval_group,
        ["--format=human", "verify", "--out", str(clean_two_record_chain)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    out = result.output
    # No JSONL on stdout.
    assert not any(ln.startswith("{") for ln in out.splitlines())
    # Every column header present.
    for header in ("run_id", "run_started_iso", "complete", "isolation_class", "chain_head"):
        assert header in out
    # Footer counts present.
    assert "verified_complete=2" in out
    assert "verified_incomplete=0" in out
    # Row count check — each known run_id in the fixture appears as a substring.
    from json import loads
    record_files = sorted(clean_two_record_chain.glob("*.json"))
    for p in record_files:
        rid = loads(p.read_bytes())["run_id"]
        assert rid in out, f"run_id {rid!r} missing from human-format table"


def test_verify_human_format_on_empty_chain_emits_footer_only(tmp_path, monkeypatch):
    """AC-6 — empty chain produces footer with zero counts, no IndexError."""
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "empty"
    out.mkdir()
    result = CliRunner().invoke(
        eval_group, ["--format=human", "verify", "--out", str(out)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "verified_complete=0" in result.output
    assert "verified_incomplete=0" in result.output


# === AC-9 (cold-start guard not regressed) ==================================
def test_cli_verify_does_not_regress_cold_start(monkeypatch):
    """The verify command body's audit import must be function-scoped.

    Imports ``codegenie.eval.cli`` fresh and asserts that ``codegenie.eval.audit``
    is NOT loaded (it must only land when ``verify`` runs).
    """
    import sys, importlib
    for k in list(sys.modules):
        if k.startswith("codegenie.eval"):
            sys.modules.pop(k, None)
    importlib.import_module("codegenie.eval.cli")
    assert "codegenie.eval.audit" not in sys.modules, (
        "verify body must defer the audit import; it was loaded at module-top"
    )
```

Fixture sketch (`tests/integration/eval/conftest.py`):

```python
"""Fixtures construct on-disk audit chains via S2-04's write_run_record.

S2-04 AC-7 byte-flip discipline: flip a syntactically-valid same-length character
inside ``run_id`` so JSON validity is preserved and BLAKE3 divergence is the only
signal. Operators can introspect tampered files after the test for forensics.
"""
import json, fcntl
from pathlib import Path
import pytest
from codegenie.eval.audit import write_run_record  # S2-04
# _make_report helper mirrors S2-04's TDD plan §Red shape (BenchRunReport builder)


@pytest.fixture
def clean_two_record_chain(tmp_path):
    out = tmp_path / "runs"
    r1 = _make_report(prev_hash="0" * 64, run_id="r1-clean")
    _, h1 = write_run_record(r1, out)
    r2 = _make_report(prev_hash=h1, run_id="r2-clean")
    write_run_record(r2, out)
    return out


@pytest.fixture
def three_record_chain(tmp_path):
    """Returns (out_dir, (r1_iso, r2_iso, r3_iso))."""
    ...  # filenames already encode ISOs; return canonical colon-form ISOs the CLI normalizes


@pytest.fixture
def tampered_chain(tmp_path):
    """Two records; flip a byte in r1's run_id after r2 is chained."""
    ...


@pytest.fixture
def five_record_chain_with_r3_tampered(tmp_path):
    """Five records; r3 has its run_id byte-flipped after r4, r5 chain on the
    pre-flip version. verify() should stop at r3 with partial counts (2)."""
    ...


@pytest.fixture
def partial_and_complete_chain(tmp_path):
    """Chain: r1 with complete=False (run_id='partial:r1-xxx'), r2 with complete=True
    (run_id='r2-good'). Returns (out, partial_run_ids, complete_run_ids)."""
    ...
```

Run; confirm failures. Commit as the red marker.

### Green — make it pass

Implement the `verify` command body per §Implementation outline. JSONL envelope shapes:

- **Clean:** `{"kind": "verify", "ok": true, "verified_complete": int, "verified_incomplete": int, "first_record_filename": str|null, "last_record_filename": str|null}`.
- **Tamper:** `{"kind": "verify", "ok": false, "verified_complete": int, "verified_incomplete": int, "tampered_path": str, "reason": str, "first_record_filename": str|null, "last_record_filename": str|null}`.

Human format: hand-rolled table (no `tabulate` dep — cold-start budget); one row per record; footer carries the count pair plus tamper diagnostics if any.

### Refactor — clean up

- Extract `_emit_verify_jsonl`, `_emit_verify_human`, `_emit_incomplete_warning`, `_derive_filename_bracket` as private helpers in `cli.py`.
- Type hints on every helper; `mypy --strict` clean.
- The stderr warning under `--strict` mode is one `click.echo(..., err=True)` per incomplete record, prefixed `incomplete: `.
- Re-run S4-01's cold-start guard test (`tests/unit/eval/test_cli_scaffold.py::test_cold_start_no_heavy_imports`) — must stay green.
- Log structured events at `structlog.info`: `verify_completed` with `ok`, the two counts, `tampered_path` (if any), `reason` (if any). Fires on BOTH the success and failure path so the failure is auditable. These feed the Phase 13 dashboard backfill mentioned in `phase-arch-design.md §Trace export deferred`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/cli.py` | Fill in the `verify` subcommand body; add `_normalize_since` (module-top), `_VERIFY_EMITTERS` dispatch map, `_emit_verify_jsonl`, `_emit_verify_human`, `_emit_incomplete_warning`, `_derive_filename_bracket`. |
| `tests/integration/eval/test_cli_verify.py` | **New** — clean chain, tampered chain, five-record-chain stop-on-first-mismatch, partial chain, `--since` valid/invalid/excludes-all, `--strict` per-record-id stderr, human-format row count + headers, missing-out-dir no-mkdir, cold-start guard re-assert. (Path per S4-02 F-CON-9 convention.) |
| `tests/integration/eval/conftest.py` | Fixtures `clean_two_record_chain`, `three_record_chain`, `tampered_chain`, `five_record_chain_with_r3_tampered`, `partial_and_complete_chain` (built via S2-04's `write_run_record`; tamper by direct byte-flip on the `run_id` field per S2-04 AC-7). |
| `tests/unit/eval/test_cli_verify_normalize_since.py` | **New** — pin `_normalize_since` as the single coupling point to S2-04's filename convention (AC-10). |

## Out of scope

- **`audit.verify` internals** — S2-04 owns the `VerifyResult` shape and the BLAKE3 walk. This story consumes the contract.
- **`isolation_class` mixed-window refusal** — ADR-0010 §Open Q reserves a `--allow-isolation-mix` flag for a future refusal-on-mix path; this story emits `isolation_class` per record in human format but does not refuse mixed windows. That refusal lives in `PromotionGate.evaluate` (S4-04) at the evidence-window scope, not in `verify` at the chain scope.
- **`promote-verdict` subcommand** — S4-04/S4-05.
- **`run` subcommand** — S4-02.
- **Tamper diagnostics beyond `tampered_path` + `reason`** — full forensic traces (expected vs computed BLAKE3, byte offsets, hex diffs) are S7-02 (end-to-end audit integration test) territory; the CLI surface here is operator-facing, not forensics-facing.
- **Genesis-record handling** — S2-04 owns the `prev_hash == "0"*64` semantics; this story walks whatever the chain contains.
- **Extracting a shared `_EMITTERS` kernel across S4-02 and S4-03** — Rule 2: three sites is the trigger; S4-05's `promote-verdict` will be the third. Until then, both stories maintain local dispatch maps with identical shape (Design-Patterns F-DP-1; surfaced for follow-up at S4-05 implementation time).

## Notes for the implementer

- **Field name is `tampered_path`, not `tamper_at`.** S2-04 HARDENED AC-4 + AC-13 are the source of truth. The CLI emits `"tampered_path"` in JSONL. If a sibling story (S4-04, currently `Ready`) appears to use `tamper_at`, that story has the drift; do not propagate it here. (See Validation notes F-CON-1.)
- **`audit.verify` *returns*; it does not raise.** S2-04 AC-4 pins the return-only contract. The runner (S3-01) is the place that re-raises `ChainTamperDetected` for the *run* startup-check; the standalone `verify` CLI path always gets a `VerifyResult` back. Do not wrap the call in `try/except ChainTamperDetected:` — that branch is dead code and will mislead a future reader. (See Validation notes F-CON-2.)
- **`--since` is canonical ISO with colons; filenames have hyphens.** The CLI normalizes at the boundary via `_normalize_since` — a single helper that is the only point in the codebase that knows about S2-04's filename-FS-safety convention. Tests pin this directly (AC-10) so a future S2-04 wire change is loud. Do NOT inline the `.replace(":", "-")` — naming the helper is the design discipline. (See Validation notes F-CON-4.)
- **`first_record_filename` / `last_record_filename` are CLI-derived, not VerifyResult fields.** S2-04's `VerifyResult` carries `(ok, verified_complete, verified_incomplete, tampered_path, reason)` — that is the wire contract this story consumes. Filename bracketing comes from a one-line `sorted(out_dir.glob("*.json"))` walk. Naming the JSONL keys `first_record_filename` / `last_record_filename` (rather than `first_record_iso`) honestly signals the derivation — they are filename prefixes, not the canonical `run_started_iso` ISO. (See Validation notes F-CON-5.)
- **Empty chain semantics are deliberate.** A fresh repo with no runs yet AND an operator-supplied `--out` pointing at a path that doesn't exist are both *clean* by definition (`ok=True, counts=(0,0)`). Do not raise; do not warn; do not `mkdir` the operator's path. The nightly-CI contract is "if there's nothing to verify, succeed silently." (See Validation notes F-COV-4.)
- **`--strict` is gentler than it sounds.** It does NOT change exit codes. It only escalates the stderr volume — one `incomplete: <run_id> <run_started_iso>` line per `complete=False` record. The rationale: partial records are valid history that must remain in the chain; promoting "partials exist" to a chain-integrity failure would conflate two orthogonal concerns. Operators who want a strict-no-partials gate compose `verify --strict 2>&1 | grep -q 'incomplete:'` themselves.
- **Tamper fixture construction (per S2-04 AC-7):** the cleanest way to build a tampered chain is (a) write N records via S2-04's `write_run_record`, (b) open the target JSON file, mutate the `run_id` field to a same-length syntactically-valid string (e.g., `"r2-orig"` → `"r2-FAKE"`), (c) re-serialize via the same canonical-JSON form S2-04 uses (`sort_keys=True, separators=(",", ":"), ensure_ascii=False`). Mutating `run_id` (a free-text field, not a hash) preserves JSON validity so the only divergence signal is the recomputed BLAKE3 — exactly what S2-04 AC-7 documents.
- **Cold-start budget audit (AC-9):** the `from codegenie.eval.audit import verify as audit_verify` MUST be function-scoped inside `verify`'s body. Hoisting it to module top regresses S4-01's `test_cold_start_no_heavy_imports` (because `audit` imports `codegenie.eval.models`, which pulls `pydantic`). The cold-start test is a structural defense, not a benchmark — keep it green.
- **`_VERIFY_EMITTERS` is a local Strategy-via-dict (Design-Patterns F-DP-1).** A future `--format=csv` is a one-row data edit. Do NOT introduce a `FormatEmitter` Protocol or registry — the codebase's rule-of-three threshold is not yet met (S4-02 is the first emitter site; S4-03 is the second; S4-05 will be the third and will trigger an extract). Until then, intentional local duplication mirrors S4-02's shape so the future extract is mechanical.
- **`structlog.info` events fire on BOTH paths.** A failed verify is exactly when an operator wants the structured event for incident retrospective — do not gate the log emit on `result.ok`.
