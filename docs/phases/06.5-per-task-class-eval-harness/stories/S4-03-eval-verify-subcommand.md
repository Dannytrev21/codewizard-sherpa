# Story S4-03 — `codegenie eval verify` subcommand for chain integrity

**Step:** Step 4 — Wire the CLI and the read-only promotion gate
**Status:** Ready
**Effort:** S
**Depends on:** S4-01 (CLI scaffold + exit codes), S2-04 (audit chain extension + `VerifyResult`)
**ADRs honored:** ADR-0002 (`lower_bound_95` is gate signal; verify surfaces partial-record breakdown so partials cannot be miscounted as evidence), ADR-0010 (`isolation_class` annotated on every record — verify surfaces it for operator inspection), Phase 0 ADR-0014 (BLAKE3 chain primitive reuse), Gap #4 (`complete: bool` on `BenchRunReport`)

## Context

`codegenie eval verify` walks the audit chain at `.codegenie/eval/runs/` (and any `--out` override), recomputes BLAKE3 link hashes, and reports a clean / tampered verdict. The audit chain is the load-bearing evidence trail for promotion (S4-04 reads it); a silently-tampered chain corrupts every downstream verdict. Operators run `verify` as a CI gate (nightly) and as a forensics tool after suspected drift. Per Gap #4 / ADR-0004 §Consequences, partial reports (`complete=False`) are real history — `verify` must walk them, but the result must distinguish "verified-complete N" from "verified-incomplete M" so operators see the breakdown and S4-04 knows how many records qualify as promotion evidence.

This story is a thin CLI veneer over S2-04's `audit.verify(out_dir, since) -> VerifyResult`. The exit-code mapping is the load-bearing contract: 0 on clean, 5 on tamper. The `--strict` flag tightens the contract by treating any non-empty `verified_incomplete` count as a non-zero exit (still 0, but with a stderr diagnostic — operators in CI matrix that intentionally exclude partials want a one-flag clean signal).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design → src/codegenie/eval/cli.py` — names `verify [--since=<iso>] [--strict]`.
  - `../phase-arch-design.md §Component design → src/codegenie/eval/audit.py` — `verify(out_dir: Path, since: str | None = None) -> VerifyResult` is the callable.
  - `../phase-arch-design.md §Failure modes #5` — chain-tamper at startup exits code 5 *before* any SUT invocation; `verify` is the dedicated tool for the same check standalone.
  - `../phase-arch-design.md §Gap analysis Gap 4` — `audit.verify(...)` distinguishes "verified-complete N records" from "verified-incomplete M records" via `VerifyResult` fields; the CLI surfaces both.
- **Phase ADRs:**
  - `../ADRs/0002-promotion-gate-keys-on-lower-bound-95.md` §Consequences — partial reports cannot be evidence; `verify`'s incomplete-count surface is how operators see that gap.
  - `../ADRs/0010-isolation-class-annotation-on-bench-run-report.md` §Consequences — `verify --strict` may extend in a follow-up to refuse mixed isolation-class windows; this story does not implement that, but the JSONL output must surface the field per record so the future check is mechanical.
- **Production ADRs:**
  - `../../../production/adrs/0009-humans-always-merge.md` — `verify` is read-only by construction; no flag mutates the chain.
- **Source design:** `../High-level-impl.md §Step 4` — names the flag list (`--since`, `--strict`) and the exit semantics (0 clean / 5 tamper).
- **Phase 0 precedent:** `../../00-bullet-tracer-foundations/ADRs/0014-blake3-audit-chain.md` — the BLAKE3 chain primitives this story walks.

## Goal

Implement `codegenie eval verify [--since=<iso>] [--strict] [--out=<path>] [--format=human|jsonl]` by delegating to `audit.verify(...)` and mapping its `VerifyResult` to exit 0 (clean) or 5 (tamper); surface the "verified-complete N / verified-incomplete M" breakdown on stdout.

## Acceptance criteria

- [ ] `codegenie eval verify` over a clean chain (one `BenchRunReport` from S4-02's test fixture) exits 0; stdout (default `--format=jsonl`) emits a single aggregate line with fields `{"kind": "verify", "ok": true, "verified_complete": <int>, "verified_incomplete": <int>, "first_record_iso": "...", "last_record_iso": "..."}`.
- [ ] `codegenie eval verify` over a tampered chain (one byte flipped in any prior record) exits 5; stdout emits `{"kind": "verify", "ok": false, ...}` plus a `"tamper_at": "<path>"` field naming the first divergent record.
- [ ] `--since=<utc-iso>` filters the walk to records whose `run_started_iso >= <since>`; passing an ISO that excludes all records → exit 0 with `verified_complete=0, verified_incomplete=0`.
- [ ] `--strict`: when set, a non-zero `verified_incomplete` count emits a stderr warning naming the incomplete `run_id`s but the exit code is still 0 (clean chain) or 5 (tamper). The flag does NOT escalate "incomplete records exist" to a tamper; partials are valid history.
- [ ] `--out=<path>` optional override for the chain directory; default `.codegenie/eval/runs/`.
- [ ] **`--format=human`** prints a small table with columns `run_id / run_started_iso / complete / isolation_class / chain_head[:8]`, footer `verified_complete=N verified_incomplete=M`.
- [ ] Empty chain (no records under `out_dir`): exits 0 with `verified_complete=0, verified_incomplete=0`; not an error — first-time runs are clean by definition.
- [ ] **Heavy imports remain deferred:** the `verify` command body imports `audit` lazily; cold-start test from S4-01 stays green.
- [ ] The red test from §TDD plan exists, was committed at the red marker, and is now green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/integration/test_cli_verify.py` all pass on touched files.

## Implementation outline

1. Write red tests in `tests/integration/test_cli_verify.py` — see §TDD plan. The tests need fixtures: (a) a clean chain of two records, (b) a tampered chain (flip a byte after the fact), (c) a chain with one `complete=False` partial record (from cost-cap, per S3-06).
2. Fill in the `verify` subcommand stub from S4-01:
   - Click options: `--since` (`str`, default `None`), `--strict` (flag), `--out` (`Path`, default `Path(".codegenie/eval/runs")`).
   - Body (deferred imports):
     1. `from codegenie.eval.audit import verify as audit_verify`.
     2. `result = audit_verify(out_dir=out, since=since)` — raises `ChainTamperDetected` *only* in the synchronous-walk variant; the documented API returns `VerifyResult` with `ok=False` and `tamper_at` populated. (Confirm with S2-04's actual signature; if the API raises, catch and convert.)
     3. Emit JSONL or human format per `ctx.obj["format"]`.
     4. If `--strict` and `result.verified_incomplete > 0`: write a stderr warning naming the incomplete `run_id`s; exit code unaffected.
     5. `sys.exit(EXIT_SUCCESS if result.ok else EXIT_CHAIN_TAMPER)`.
3. The JSONL aggregate fields come from `VerifyResult` — if S2-04's wire shape differs from §Acceptance criteria, coordinate (S2-04 is the source of truth for the shape; this story consumes it). The contract this story owns is the CLI surface: `{"kind": "verify"}` envelope + the two counts + the boolean.
4. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest`.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/integration/test_cli_verify.py
import json
from pathlib import Path
from click.testing import CliRunner
from codegenie.eval.cli import eval as eval_group


def test_verify_empty_chain_exits_zero(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".codegenie" / "eval" / "runs").mkdir(parents=True)
    runner = CliRunner()
    result = runner.invoke(eval_group, ["verify"], catch_exceptions=False)
    assert result.exit_code == 0
    payload = next(json.loads(ln) for ln in result.output.splitlines() if ln.startswith("{"))
    assert payload["kind"] == "verify"
    assert payload["ok"] is True
    assert payload["verified_complete"] == 0
    assert payload["verified_incomplete"] == 0


def test_verify_clean_two_record_chain_exits_zero(clean_two_record_chain, monkeypatch):
    monkeypatch.chdir(clean_two_record_chain.parent)
    runner = CliRunner()
    result = runner.invoke(eval_group, ["verify"], catch_exceptions=False)
    assert result.exit_code == 0
    payload = next(json.loads(ln) for ln in result.output.splitlines() if ln.startswith("{"))
    assert payload["ok"] is True
    assert payload["verified_complete"] == 2
    assert payload["verified_incomplete"] == 0


def test_verify_tampered_chain_exits_five(tampered_chain, monkeypatch):
    """One byte flipped in the first record after the second was chained."""
    monkeypatch.chdir(tampered_chain.parent)
    runner = CliRunner()
    result = runner.invoke(eval_group, ["verify"], catch_exceptions=False)
    assert result.exit_code == 5  # EXIT_CHAIN_TAMPER
    payload = next(json.loads(ln) for ln in result.output.splitlines() if ln.startswith("{"))
    assert payload["ok"] is False
    assert "tamper_at" in payload


def test_verify_distinguishes_complete_from_incomplete(partial_then_complete_chain, monkeypatch):
    """Chain of two records: first complete=False (cost-capped), second complete=True."""
    monkeypatch.chdir(partial_then_complete_chain.parent)
    runner = CliRunner()
    result = runner.invoke(eval_group, ["verify"], catch_exceptions=False)
    assert result.exit_code == 0  # chain integrity intact
    payload = next(json.loads(ln) for ln in result.output.splitlines() if ln.startswith("{"))
    assert payload["ok"] is True
    assert payload["verified_complete"] == 1
    assert payload["verified_incomplete"] == 1


def test_verify_strict_warns_on_incomplete_but_still_exits_zero(partial_then_complete_chain, monkeypatch):
    monkeypatch.chdir(partial_then_complete_chain.parent)
    runner = CliRunner()
    result = runner.invoke(
        eval_group, ["verify", "--strict"], mix_stderr=False, catch_exceptions=False
    )
    assert result.exit_code == 0
    # Partials surfaced loudly on stderr per --strict
    assert "incomplete" in (result.stderr or "").lower()


def test_verify_since_filters_records(clean_two_record_chain, monkeypatch):
    monkeypatch.chdir(clean_two_record_chain.parent)
    runner = CliRunner()
    # Pick an ISO after both records — should match nothing
    result = runner.invoke(
        eval_group, ["verify", "--since=2099-01-01T00:00:00Z"], catch_exceptions=False
    )
    assert result.exit_code == 0
    payload = next(json.loads(ln) for ln in result.output.splitlines() if ln.startswith("{"))
    assert payload["verified_complete"] == 0
    assert payload["verified_incomplete"] == 0


def test_verify_human_format_table(clean_two_record_chain, monkeypatch):
    monkeypatch.chdir(clean_two_record_chain.parent)
    runner = CliRunner()
    result = runner.invoke(
        eval_group, ["--format=human", "verify"], catch_exceptions=False
    )
    assert result.exit_code == 0
    # Human format: no JSONL on stdout
    assert not any(ln.startswith("{") for ln in result.output.splitlines())
    # Surfaces the two counts
    assert "verified_complete" in result.output
    assert "verified_incomplete" in result.output
```

Fixtures (`clean_two_record_chain`, `tampered_chain`, `partial_then_complete_chain`) belong in `tests/integration/conftest.py` — they construct on-disk audit chains using S2-04's `write_run_record` and then (for the tampered case) flip a byte directly on disk.

Run; confirm failures. Commit as the red marker.

### Green — make it pass

Implement the `verify` command body per §Implementation outline. The JSONL envelope is `{"kind": "verify", "ok": bool, "verified_complete": int, "verified_incomplete": int, "tamper_at": str | None, "first_record_iso": str | None, "last_record_iso": str | None}`. Human format: small `tabulate` or hand-rolled table.

### Refactor — clean up

- Extract `_emit_verify_jsonl` and `_emit_verify_human` into private helpers in `cli.py`.
- Type hints on every helper; `mypy --strict` clean.
- The stderr warning in `--strict` mode lists incomplete `run_id`s with their `run_started_iso` for operator triage. Use `click.echo(..., err=True)`.
- Confirm the cold-start budget from S4-01 still passes after this story (re-run that test in CI).
- Log structured events at `structlog.info` level: `verify_started`, `verify_completed` with `ok`, the two counts, `tamper_at` (if any). These feed the Phase 13 dashboard backfill mentioned in `phase-arch-design.md §Trace export deferred`.
- `--since` parsing: stdlib `datetime.fromisoformat` accepts `2026-05-12T14:32:08+00:00` and the `Z`-suffix form on Python 3.11+. If S2-04 uses a different ISO normalization, mirror it; do not invent a third.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/cli.py` | Fill in the `verify` subcommand body; add verify-emit helpers. |
| `tests/integration/test_cli_verify.py` | New file — clean chain, tampered chain, partial chain, `--since` filter, `--strict` warning, human format. |
| `tests/integration/conftest.py` | Add `clean_two_record_chain`, `tampered_chain`, `partial_then_complete_chain` fixtures (construct with S2-04's writer; tamper by direct byte-flip on disk). |

## Out of scope

- **`audit.verify` internals** — S2-04 owns the `VerifyResult` shape and the BLAKE3 walk. This story consumes the contract.
- **`isolation_class` mixed-window refusal** — ADR-0010 §Open Q reserves a `--allow-isolation-mix` flag for a future refusal-on-mix path; this story emits `isolation_class` per record in human format but does not refuse mixed windows. That refusal lives in `PromotionGate.evaluate` (S4-04) at the evidence-window scope, not in `verify` at the chain scope.
- **`promote-verdict` subcommand** — S4-04/S4-05.
- **`run` subcommand** — S4-02.
- **Tamper diagnostics beyond `tamper_at`** — full forensic traces (expected vs computed BLAKE3, byte offsets) are S7-02 (end-to-end audit integration test) territory; the CLI surface here is operator-facing, not forensics-facing.
- **Genesis-record handling** — S2-04 owns the `prev_hash == "0"*64` semantics; this story walks whatever the chain contains.

## Notes for the implementer

- **`VerifyResult` shape is owned by S2-04.** Read S2-04's story or implementation before writing this one — the fields you depend on are `ok: bool`, `verified_complete: int`, `verified_incomplete: int`, `tamper_at: Path | None`, and per-record metadata for the human table. If S2-04 ships a different field name (e.g., `complete_count` instead of `verified_complete`), the integration test fixtures and the CLI emit code must match; *do not silently rename*. Flag and reconcile.
- **`--strict` is gentler than it sounds.** It does NOT change exit codes. It only escalates the stderr volume. The rationale: partial records are valid history that must remain in the chain; promoting "partials exist" to a chain-integrity failure would conflate two orthogonal concerns. Operators who want a strict-no-partials gate compose `verify --strict | grep -q "verified_incomplete=0"` themselves.
- **Tamper fixture construction:** the cleanest way to build a tampered chain is (a) write two records via S2-04, (b) open the first JSON file in binary mode, flip one byte in the middle of the JSON payload (avoid corrupting the JSON structure — flip inside a digest hex value), (c) re-close. The chain's link hash on the *second* record was computed over the *original* first; after the flip, the recomputed link diverges. `audit.verify` catches this at the first record's link-recomputation.
- **`tamper_at` is a path, not a `run_id`.** Operators investigating tamper need a filesystem coordinate to grep / diff; `run_id` alone (which is content-addressed) is harder to map back to disk. Emit both if cheap.
- **`first_record_iso` / `last_record_iso`** are convenience metadata for `--format=human`'s footer; they cost nothing to compute and save operators a `ls -la` call.
- **Empty-chain semantics are deliberate.** A fresh repo with no runs yet is *clean* by definition (`ok=True, counts=(0,0)`). Do not raise; do not warn. The first run of `verify` on a fresh repo must exit 0 silently — this is the nightly-CI contract.
- **Cold-start budget audit:** after wiring `verify`, re-run S4-01's cold-start test. Importing `audit` inside the function body is the discipline; if you pull `audit.verify` to module top, the test fails.
