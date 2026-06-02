# Validation report — S4-03 `codegenie eval verify` subcommand

**Validated:** 2026-06-01
**Validator:** phase-story-validator
**Verdict:** HARDENED
**Findings:** 12 total — 5 block, 6 harden, 1 nit

The story's *goal* (thin CLI veneer over `audit.verify` → exit 0 clean / 5 tamper; surface verified-complete vs verified-incomplete breakdown; `--since`, `--strict`, `--out`, group-level `--format`) is sound and traces directly to `phase-arch-design.md §Component design → cli.py` and `phase-arch-design.md §Failure modes #11`. **But the wire-shape claims, the symbol import name, the `--since` ISO-format claim, and the implementation outline's "verify raises" assumption all contradict the hardened S2-04 and S4-01 contracts** (both `HARDENED` as of 2026-05-26 / 2026-05-28). An executor following the story verbatim would (a) name the JSONL key `tamper_at` instead of `tampered_path`, breaking the wire contract Phase 11 will consume; (b) silently misfilter `--since` because filename `:`→`-` substitution is unmodeled; (c) wrap `audit.verify` in a dead `try/except` branch; (d) test against a symbol named `eval` that S4-01 already renamed. Every issue is patchable in place → HARDENED, not RESCUE.

Conflict-resolution priority applied: **Consistency > Coverage > Test-Quality > Design-Patterns**. The dominant lens here is Consistency — the story drifted from contracts that were hardened *after* it was written, identical to the S4-02 precedent.

---

## Critic: Consistency (lens: does the story contradict the hardened arch / ADRs / sibling stories?)

### F-CON-1 (BLOCK) — `tamper_at` is not on `VerifyResult`; the field is `tampered_path`

S2-04 HARDENED AC-4 + AC-13 + outline §4 pin the field name on `VerifyResult` as **`tampered_path: Path | None`**. The original S4-03 used `tamper_at` in three places: AC line 37 (`"tamper_at": "<path>"`), AC line 41 (referenced obliquely), and Notes line 197 (`"tamper_at is a path, not a run_id"`). S4-04 (also `Ready`, not yet validated) shares this drift — flagged for the next validator pass, not auto-fixed here (Rule 3 — surgical). **Resolution:** every occurrence renamed to `tampered_path`; JSONL key emitted by the CLI is `"tampered_path"` (stringified `Path`).

### F-CON-2 (BLOCK) — `audit.verify` returns; it never raises `ChainTamperDetected`

S2-04 AC-4 is explicit: `verify(out_dir, since=None) -> VerifyResult` returns even on tamper (`ok=False`, `tampered_path` populated, `reason` populated). The runner (S3-01 AC-4) is where `ChainTamperDetected` is re-raised — but only on the *run* startup-check path, never inside the standalone `verify` CLI. Original outline step 2.b read "raises `ChainTamperDetected` *only* in the synchronous-walk variant; … if the API raises, catch and convert." That branch is dead code; following it would leave a misleading `try/except` block in the CLI body. **Resolution:** outline rewritten to call `audit_verify(...)` directly and map `result.ok` to exit code; the catch-and-convert language is removed.

### F-CON-3 (BLOCK) — wrong Click symbol name

Every TDD snippet imports `from codegenie.eval.cli import eval as eval_group`. S4-01 HARDENED AC-1 (F-CON-3 in that validation) renamed the exported group to **`eval_group`** (`@click.group(name="eval")`) specifically to avoid shadowing the `eval()` builtin. There is no `eval` symbol and no alias. **Resolution:** all imports → `from codegenie.eval.cli import eval_group`.

### F-CON-4 (BLOCK) — `--since` ISO-vs-filename lexicographic mismatch

S2-04 AC-4a pins `since` as an **inclusive filename-prefix lexicographic** filter against `*.json` files whose names are `f"{utc_iso}-{secrets.token_hex(4)}.json"` with `:` substituted to `-` (S2-04 outline line 144 — FS safety). The original story's `--since=2099-01-01T00:00:00Z` test value contains literal `:` (ASCII 58, higher than `-`'s 45) — the filter happens to work by accident for "exclude everything after this distant date" but would silently misfilter realistic `--since=2026-05-26T14:32:08Z` values: filenames starting `2026-05-26T14-32-08…` sort lexicographically *below* the search string, so records that should match would be excluded.

**Resolution:** the CLI normalizes `--since` at the boundary via `_normalize_since(s: str) -> str` (`replace(":", "-")`) — the single coupling point to S2-04's filename convention; tested directly via AC-10 so a future S2-04 wire change is loud. `--since` is declared via `click.DateTime(...)` for ISO validation; malformed values trigger click's usage-error exit (typically 2, *not* `EXIT_COST_CAP=2` since the body never runs — they're distinct paths).

### F-CON-5 (BLOCK) — `first_record_iso` / `last_record_iso` are not on `VerifyResult`

Original AC line 36 promised JSONL fields `first_record_iso` and `last_record_iso`. Original Notes line 198 promised them as "convenience metadata for `--format=human`'s footer." S2-04's `VerifyResult` has exactly five fields: `(ok, verified_complete, verified_incomplete, tampered_path, reason)`. There are no ISO bracketing fields.

**Resolution:** the CLI **derives** the bracket pair from a `sorted(out_dir.glob("*.json"))` walk (cheap — directory listing, no JSON parse) and emits them under the explicit names `first_record_filename` / `last_record_filename`. The wire-field names reflect their derivation — they are filename prefixes (with `:`→`-` substitution), NOT the canonical `run_started_iso` ISO of the record. Operators reading JSONL see immediately that these are filesystem coordinates, not content fields. Both `null` on empty chain.

### F-CON-6 (HARDEN) — test path convention

Original "Files to touch" placed tests at `tests/integration/test_cli_verify.py` (flat). S4-02 validation F-CON-9 established the convention: eval CLI integration tests under `tests/integration/eval/`, eval unit tests under `tests/unit/eval/` (the latter from S4-01 F-CON-1). No existing-file collision either way, but discoverability is load-bearing. **Resolution:** paths moved to `tests/integration/eval/test_cli_verify.py` + `tests/integration/eval/conftest.py` + `tests/unit/eval/test_cli_verify_normalize_since.py`.

### F-CON-7 (HARDEN) — `--format` is GROUP-level, not subcommand-level

S4-01 AC-4 pinned `--format=human|jsonl` (default `jsonl`) as a **group-level** option on `eval_group`, propagated via `ctx.obj["format"]`. Tests must pass `--format` BEFORE the subcommand: `runner.invoke(eval_group, ["--format=human", "verify", ...])`, not as a verify-local option. The verify body reads `ctx.obj["format"]`. The original story's line 148 already got this right; line 41's wording ("`--format=human`") was ambiguous about scope. **Resolution:** AC-6 explicitly cites the group-level inheritance and the invocation pattern; outline §4 documents the `ctx.obj["format"]` read.

---

## Critic: Coverage (lens: do the ACs collectively guarantee the goal? edge cases?)

### F-COV-1 (HARDEN) — `reason` field dropped from JSONL on the failure path

`VerifyResult.reason: str | None` carries operator-facing diagnostic — `"parse_error: …"`, `"content_hash mismatch"`, `"prev_hash mismatch"` — that distinguishes byte-flip vs prev-hash divergence vs malformed JSON. The original tamper AC only required `tamper_at`. Losing `reason` means an operator running `verify` in a CI gate sees `"ok": false, "tampered_path": "/path/to/record.json"` but cannot tell from JSONL alone whether to escalate to a security incident (BLAKE3 mismatch → forensic concern) or a recovery action (parse error → maybe disk corruption). **Resolution:** new AC-2 emits `"reason"` in JSONL on `ok=False` and asserts it is non-empty; substring assertions on `content_hash` / `prev_hash` / `parse_error` per failure mode.

### F-COV-2 (HARDEN) — stop-on-first-mismatch counts not asserted

S2-04 AC-13 pins that on tamper at record k (1-indexed), `verified_complete + verified_incomplete` equals records 0..k-2 (k-1 records). The CLI must surface those partial counts in the failure-JSONL so operators see how much of the chain was verified before divergence — critical for "scope of compromise" assessment. Original story had no AC pinning this. **Resolution:** AC-8 added (new) — five-record chain with r3 tampered, assert `verified_complete + verified_incomplete == 2`.

### F-COV-3 (HARDEN) — malformed-`--since` exit semantics undefined

A garbage ISO string (`--since=foo`) had no documented exit code. **Resolution:** `--since` declared via `click.DateTime(formats=[…])`; click rejects malformed values with its usage-error exit (typically 2, bypassing `_map_exception_to_exit_code`). AC-3a pins this — the body is never entered, so the click usage path is distinct from `EXIT_CHAIN_TAMPER=5` and `EXIT_COST_CAP=2`.

### F-COV-4 (HARDEN) — missing-`out` (path doesn't exist) conflated with empty `out`

S2-04 AC-4 explicitly handles "missing dir" and "empty dir" identically (`ok=True, 0, 0, None, None`). The CLI must mirror that — and crucially, must NOT `mkdir` an operator-supplied non-existent path (verify is read-only by construction per production ADR-0009; silently creating directories is a side effect). Original story had no AC for the missing-path case. **Resolution:** AC-5 + new test `test_verify_missing_out_dir_is_empty_chain_no_mkdir` pin both the exit-0 result AND the no-mkdir invariant.

### F-COV-5 (HARDEN) — human-format per-record fields require re-globbing

AC-6 promises columns `run_id / run_started_iso / complete / isolation_class / chain_head[:8]`. None of those are on `VerifyResult`. Original outline didn't address how the CLI obtains them. **Resolution:** `_render_human_table(out_dir, since)` re-globs `out_dir`, lazy-loads each `*.json` once (`json.loads` only — no Pydantic; this is informational rendering, not re-verification). Surfaced explicitly in outline + Notes; cost is one filesystem-walk per `verify` invocation (already paid for `_derive_filename_bracket`).

---

## Critic: Test-Quality (lens: would the TDD plan catch a wrong implementation?)

### F-TQ-1 (HARDEN) — JSONL type assertions too loose

Original tests only checked key presence (`payload["ok"] is True`). A mutant emitting `"ok": "true"` (string), `"verified_complete": "0"` (string), or `"tampered_path": null` when there was actual tamper would pass several of the original assertions. **Resolution:** every JSONL assertion now pins type via `isinstance(payload["ok"], bool)`, `isinstance(payload["verified_complete"], int)`, `isinstance(payload["tampered_path"], str) and Path(payload["tampered_path"]).name.endswith(".json")`. Catches "stringify everything" and "skip the failure branch" mutants.

### F-TQ-2 (HARDEN) — `--strict` test too weak

Original asserted `"incomplete" in stderr.lower()` — would pass even if the warning just said "incomplete: see docs" without ever naming a run_id. A mutant that hardcodes the warning string passes. **Resolution:** test now asserts (a) every incomplete `run_id` appears in stderr (positive — guards "stub warning" mutants); (b) no `run_id` from a `complete=True` record appears (false-positive guard — catches "print every run_id regardless of complete" mutants).

### F-TQ-3 (HARDEN) — `--format=human` test doesn't pin row count or column structure

Original only checked `"verified_complete" in output`. A mutant that emits an empty table with just the footer passes. **Resolution:** row count = `len(records)`; every column header asserted present (`run_id`, `run_started_iso`, `complete`, `isolation_class`, `chain_head`); each row contains the corresponding record's `run_id` as a substring (re-loaded from `*.json` for ground-truth comparison).

### F-TQ-4 (HARDEN) — `--since` metamorphic test missing

Walking the same chain twice — once unfiltered, once with `since=record_k_filename` — must produce verifiable count relationships. Original only tested "filter excludes everything" (the easy edge). **Resolution:** new metamorphic test on a 3-record fixture: unfiltered `count == 3`, `since=r2` count `== 2`. Catches a mutant that returns `result.verified_complete` directly without honoring the `since` filter.

### F-TQ-5 (HARDEN) — empty-chain `--format=human` not tested

Default-jsonl empty-chain test exists. Human-format empty-chain test missing — pins that `_render_human_table` handles the empty case without IndexError when there are no records to row-render. **Resolution:** new test asserts footer-only output with zero counts.

---

## Critic: Design-Patterns (lens: easy to extend by addition?)

### F-DP-1 (HARDEN — Notes only, not AC) — format dispatch should mirror S4-02's `_EMITTERS` map

S4-02 validation F-DP-2 surfaced the `_EMITTERS: Final[Mapping[str, Callable]]` pattern (Strategy via dict, keyed on `ctx.obj["format"]`) — the codebase's Open/Closed seam for output formats. S4-03 is the second emitter site. Per Rule 2 ("three similar lines is better than premature abstraction"), do NOT extract a shared module-level kernel yet — but structure this story's emitters as a **local** `_VERIFY_EMITTERS` dispatch map mirroring S4-02's shape. The third format-emitting subcommand (`promote-verdict` — S4-05) crosses the rule of three and will trigger the extract; until then, intentional duplication is correct.

Surfaced as a Notes paragraph + outline §5; **not promoted to an AC** because pattern-name mandates are not observable. The observable form (one row in a `Final` dispatch map per format; no `if format == "jsonl": … elif: …` ladders) is captured implicitly by the outline + tests reading the `_VERIFY_EMITTERS` symbol directly.

### F-DP-2 (NIT) — `_normalize_since` makes the S2-04 coupling visible

Naming the colon-to-hyphen substitution (`_normalize_since`) rather than inlining `since.replace(":", "-")` at the call site makes the coupling to S2-04's filename convention visible and testable. **Resolution:** the helper is module-top (pure, stdlib-only — no cold-start regression) and pinned by AC-10 / a dedicated unit test file. A future S2-04 wire change (different separator, ISO-aware comparison) is then a one-helper-edit visible in code review, not a scavenger hunt across the codebase.

---

## Research

No findings tagged `NEEDS RESEARCH`. Every pattern (`click.DateTime` parsing, dispatch-via-dict, "boundary-normalization helper to isolate a wire-format coupling") is precedented in this repo. Stage 3 skipped.

---

## Edits applied to the story

- **Status** `Ready` → `HARDENED (phase-story-validator, 2026-06-01)`.
- **Depends-on** annotated with the specific S4-01 / S2-04 contracts the story consumes (exported `eval_group` symbol; `VerifyResult(ok, verified_complete, verified_incomplete, tampered_path, reason)` field names).
- **Context** rewrote the second paragraph to anchor "verify *returns*; never raises" explicitly and cite S2-04 as the source of truth.
- **Acceptance criteria** rewritten end-to-end:
  - AC-1: typed assertions; renamed `first_record_iso` → `first_record_filename` (F-CON-5) with explicit "derived, not VerifyResult field" note.
  - AC-2: renamed `tamper_at` → `tampered_path` (F-CON-1); surfaces `reason` (F-COV-1) with substring assertions per failure mode.
  - AC-3 + AC-3a: split — AC-3 pins the filter semantics via `_normalize_since`; AC-3a pins click usage error for malformed input (F-CON-4 / F-COV-3).
  - AC-4: enumerates every incomplete run_id in stderr (F-TQ-2); false-positive guard added.
  - AC-5: no-mkdir invariant explicit (F-COV-4).
  - AC-6: row count + column headers + empty-chain handling (F-TQ-3, F-TQ-5, F-COV-5).
  - AC-7: missing OR existing-but-empty `out_dir` both → exit 0 (F-COV-4).
  - AC-8 (new): stop-on-first-mismatch counts (F-COV-2).
  - AC-9: cold-start re-assertion phrased as a structural defense, not a benchmark.
  - AC-10 (new): `_normalize_since` direct unit test (F-DP-2 + F-CON-4).
- **Implementation outline** rewritten — `_normalize_since` at module top, click `DateTime` parsing, deferred `audit_verify` import, `_VERIFY_EMITTERS` dispatch map mirroring S4-02, helpers listed with types.
- **TDD plan** all code rewritten: `eval_group` import, `tests/integration/eval/` + `tests/unit/eval/` paths, typed assertions, metamorphic `--since`, stop-on-first-mismatch test, false-positive guards on `--strict`, click-usage assertion for malformed `--since`, missing-out-dir no-mkdir test, cold-start re-assertion.
- **Files to touch** corrected paths; added `tests/unit/eval/test_cli_verify_normalize_since.py`.
- **Out of scope** added: extracting a shared `_EMITTERS` kernel across S4-02 and S4-03 (Rule 2 — defer to S4-05 at rule-of-three).
- **Notes for implementer** rewritten — field naming, return-vs-raise contract, `_normalize_since` discipline, CLI-derived filename bracket, empty-chain semantics including no-mkdir, `--strict` discipline, tamper fixture construction per S2-04 AC-7, cold-start budget audit, `_VERIFY_EMITTERS` rationale, structured-log-on-both-paths.

## Surfaced, not auto-fixed

- **S4-04 (`Ready`) uses `tamper_at` in the same way S4-03 originally did.** Confirmed by grep on `docs/phases/06.5-per-task-class-eval-harness/stories/S4-04-*.md` (`tamper_at` appears in S4-04 ACs and example fixtures). The S2-04 HARDENED contract is `tampered_path` — S4-04 has the same drift. Flagged for S4-04's validator pass; not auto-edited here (Rule 3 — one story per invocation).
- **`phase-arch-design.md §cli.py` (line 688)** lists `codegenie eval verify [--since=<iso>] [--out=<path>]` — does NOT include `--strict` or `--format`. The story is the canonical reference; the arch doc is stale on flag list. Flag for a follow-on doc-sweep PR; not auto-edited.
- **The "two emitter sites today; S4-05 will be the third" rule-of-three trigger** is logged in F-DP-1 as the future extraction point. Whoever implements S4-05 should propose extracting a `codegenie.eval._cli_emit` module with the shared `Mapping[str, Callable[..., None]]` shape; until then, intentional duplication is correct per Rule 2.
