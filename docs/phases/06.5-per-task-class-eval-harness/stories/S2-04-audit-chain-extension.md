# Story S2-04 — Audit chain extension for `BenchRunReport` (`write_run_record` + `verify`)

**Step:** Step 2 — Build harness internals: loader, cache, audit chain extension, canary + cost-tag shims
**Status:** Ready
**Effort:** M
**Depends on:** S1-02
**ADRs honored:** Phase 0 ADR-0001 (BLAKE3 chokepoint reuse), Phase 0 ADR-0011 (`0600` permissions), local Gap #5 (per-host fingerprinting)

## Context

Phase 0 ships a BLAKE3-chained audit log at `.codegenie/runs/<utc-iso>-<short>.json` with `codegenie.audit.chain_append` / `codegenie.audit.chain_verify` primitives — `BLAKE3(report_canonical_json)` content hash + `SHA-256(prev_hash || blake3_content)` identity per record (`phase-arch-design.md §Component design — audit.py`). Phase 6.5 **extends** this chain (does not fork it): every successful `Runner.run_eval(...)` appends one `BenchRunReport` JSON to `.codegenie/eval/runs/`. Two semantic anchors matter here. (a) **Genesis record** — when the chain is empty, `prev_hash == "0" * 64`; this is the explicit fix for `phase-arch-design.md §Implementation-level risks #5`. (b) **Tamper detection** — a record whose `prev_hash` does not equal the previous record's identity hash raises `ChainTamperDetected(file_path, expected_prev, computed_prev)` from `verify`, before any new record is written.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — src/codegenie/eval/audit.py` — public-interface signatures, BLAKE3+SHA-256 composition, `0600` mode, atomic rename
  - `../phase-arch-design.md §Implementation-level risks #5` — genesis-record semantics (`prev_hash == "0"*64`)
  - `../phase-arch-design.md §Gap analysis & improvements §Gap 5` — per-host chain fingerprinting (`host_fingerprint` field on `BenchRunReport`)
  - `../phase-arch-design.md §Edge cases #17` — two concurrent invocations: second writer's `prev_hash != current_head` → `ChainTamperDetected`-style raise
  - `../phase-arch-design.md §Idempotence` — re-run with identical inputs produces same `run_id` but chain head has moved; runner detects and warns instead of duplicating
- **Phase ADRs:**
  - (No new ADR — this story implements infrastructure documented in `phase-arch-design.md`; Gap #5's per-host clarification is logged as an open question to be re-checked in S7-02)
- **Production ADRs:**
  - `../../../production/adrs/0024-cost-observability-end-to-end.md` — downstream cost consumer relies on chain integrity
- **Source design:**
  - `../final-design.md §Audit chain extension` — original spec for record shape
- **Existing code:**
  - `src/codegenie/audit.py` (Phase 0 S3-06) — `AuditWriter`, `RunRecord`, `ProbeExecutionRecord`, atomic-write pattern; **reuse the chain primitives**, do not reimplement
  - `src/codegenie/hashing.py` (Phase 0 S2-03) — `content_hash` (BLAKE3) + `identity_hash` (SHA-256)
  - `src/codegenie/eval/models.py` (S1-02) — `BenchRunReport` includes `prev_hash: str`, `chain_head: str`, `complete: bool`, `isolation_class: Literal["subprocess","microvm"]`
  - `src/codegenie/eval/errors.py` (S1-01) — `ChainTamperDetected`

## Goal

`codegenie.eval.audit.write_run_record(report, out_dir)` extends the BLAKE3 chain by one record (atomic write, mode `0600`); `verify(out_dir, since)` walks the chain and returns a typed `VerifyResult`; both reuse Phase 0's `codegenie.audit` primitives; genesis semantics are explicit (`prev_hash == "0"*64`).

## Acceptance criteria

- [ ] `write_run_record(report: BenchRunReport, out_dir: Path) -> tuple[Path, str]` writes one JSON file at `out_dir / f"{utc_iso}-{short}.json"` (mode `0600`) via atomic-rename and returns `(written_path, new_chain_head)`.
- [ ] The function inspects the existing chain head before writing: if `out_dir` is empty (no `*.json`), `report.prev_hash` MUST equal `"0" * 64`; otherwise `report.prev_hash` MUST equal the current chain head's identity hash. Mismatch raises `ChainTamperDetected(file_path=current_head_path, expected_prev=current_head_identity, computed_prev=report.prev_hash)`.
- [ ] The new record's content hash is `BLAKE3(canonical_json(report))`; the new chain head is `SHA-256(prev_hash || blake3_content)`. The canonical-JSON form sorts keys and uses `separators=(",", ":")` — matching Phase 0 S3-06.
- [ ] `verify(out_dir: Path, since: str | None = None) -> VerifyResult` walks `*.json` lexicographically (UTC ISO names sort correctly); for each record, recomputes content + identity hashes and compares to claimed `prev_hash` chain. Returns `VerifyResult(ok: bool, verified_complete: int, verified_incomplete: int, tampered_path: Path | None, reason: str | None)`.
- [ ] **Gap #4 — incomplete records count separately:** a record with `complete=False` (`run_id` prefixed `partial:`) increments `verified_incomplete`; with `complete=True` increments `verified_complete`. Both are valid; promotion gate (S4-04) is the consumer that rejects incomplete records.
- [ ] **Genesis path:** writing the first-ever record (empty `out_dir`) succeeds when `report.prev_hash == "0" * 64`; the resulting `verify` returns `ok=True, verified_complete=1` (assuming `complete=True`).
- [ ] **Tamper detection:** rewriting any prior record's content (one byte flipped on disk) → `verify(...).ok is False` with `tampered_path` set to the first divergent file and `reason` naming the diverging hash.
- [ ] **Two concurrent writers** (simulated via threading or by manually computing `prev_hash` from a stale head): the second `write_run_record` raises `ChainTamperDetected` because the chain head moved.
- [ ] **Per-host clarification (Gap #5):** the implementation includes a `host_fingerprint` field plumbed through into `BenchRunReport` via S1-02 (if not already there, surface to S1-02 maintainer — see §Notes); `verify` does NOT cross-validate across hosts, by design. The audit chain is documented as **per-host** in module docstring and `phase-arch-design.md` reference.
- [ ] All files written are mode `0600` (`stat.S_IRUSR | stat.S_IWUSR`); a post-write `os.chmod` ensures the bit regardless of umask.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff format`, `ruff check`, `mypy --strict` clean.

## Implementation outline

1. Create `src/codegenie/eval/audit.py`. Module docstring names the per-host scope of the chain and the genesis convention (`"0" * 64`).
2. Define `VerifyResult` as a `@dataclass(frozen=True, slots=True)` with `ok`, `verified_complete`, `verified_incomplete`, `tampered_path`, `reason`.
3. Private helpers reusing Phase 0:
   - `_canonical_json(report)` → bytes (`json.dumps(report.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()`).
   - `_content_hash(canon_bytes)` → `codegenie.hashing.bytes_hash(canon_bytes)` returning `blake3:<hex>` (matches the BLAKE3 chokepoint discipline; share `bytes_hash` with `cache.py` from S2-03).
   - `_chain_identity(prev_hash, content_hash)` → `codegenie.hashing.identity_hash(prev_hash, content_hash)` returning `sha256:<hex>`.
   - `_current_head(out_dir)` → `(head_identity, head_path)` or `("0"*64, None)` if empty.
4. `write_run_record(report, out_dir)`:
   - Compute current head; assert `report.prev_hash` matches (raise `ChainTamperDetected` on mismatch).
   - Compute content + identity hashes for the new record.
   - Build a filename `f"{utc_iso}-{secrets.token_hex(4)}.json"` (UTC ISO with safe colon-replacement: `datetime.now(UTC).isoformat().replace(":", "-")`).
   - Atomic-write JSON via `<path>.tmp` → `os.fsync` → `os.rename`; post-write `os.chmod(path, 0o600)`.
   - Return `(path, new_identity_hash)`.
5. `verify(out_dir, since=None)`:
   - List `sorted(out_dir.glob("*.json"))`; filter by `since` if provided.
   - Walk forward; for each, recompute content + identity from disk JSON; compare claimed `prev_hash` to walking head. Tally complete vs incomplete.
   - Stop and return `ok=False` with `tampered_path` + `reason` on first mismatch; otherwise return `ok=True`.

## TDD plan — red / green / refactor

### Red

Test file: `tests/unit/eval/test_audit_chain.py`

```python
def test_genesis_record_prev_hash_is_64_zeros(tmp_path):
    rpt = BenchRunReport(prev_hash="0"*64, complete=True, ...)
    path, head = audit.write_run_record(rpt, tmp_path)
    assert head.startswith("sha256:") and audit.verify(tmp_path).ok is True

def test_genesis_with_wrong_prev_hash_raises_typed(tmp_path):
    rpt = BenchRunReport(prev_hash="f"*64, ...)
    with pytest.raises(ChainTamperDetected) as ei:
        audit.write_run_record(rpt, tmp_path)
    assert ei.value.expected_prev == "0"*64 and ei.value.computed_prev == "f"*64

def test_two_records_chain_verifies_clean(tmp_path):
    # Write r1 (genesis); write r2 with prev_hash = head_after_r1. verify → ok=True, verified_complete=2.
    ...

def test_tampered_record_makes_verify_return_ok_false(tmp_path):
    # Write r1, r2, r3; mutate r2's JSON file (flip one byte in a non-hash field).
    # verify → ok=False; tampered_path == r2; reason names the hash mismatch.
    ...

def test_concurrent_writer_with_stale_prev_raises(tmp_path):
    # Write r1; compute stale_head; write r2 (advances head); attempt write r2' with prev=stale_head.
    # → ChainTamperDetected.
    ...

def test_incomplete_records_count_separately(tmp_path):
    # Write one complete, one partial:<run_id> with complete=False.
    # verify().verified_complete == 1; verified_incomplete == 1; ok is True.
    ...

def test_records_are_mode_0600(tmp_path):
    path, _ = audit.write_run_record(genesis_report(), tmp_path)
    assert (path.stat().st_mode & 0o777) == 0o600

def test_atomic_write_no_tmp_left_on_success(tmp_path):
    path, _ = audit.write_run_record(genesis_report(), tmp_path)
    assert not list(tmp_path.glob("*.tmp"))

def test_verify_with_since_filter(tmp_path):
    # Three records; verify(since="2026-05-12T00:00:00") returns only the post-cutoff tally.
    ...
```

### Green

Smallest impl: §Implementation outline; ~80 lines.

### Refactor

- Extract `_atomic_write_json` into a shared module (`codegenie.eval._io` or co-locate with `cache.py`'s helper from S2-03) — both `cache.py` and `audit.py` need the same atomic-rename + chmod pattern.
- Add `structlog.info audit.record_written` with `run_id`, `chain_head`, `path` after a successful write.
- Document the per-host scope at module level and link to `phase-arch-design.md §Gap 5` in the docstring.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/audit.py` | New module — `write_run_record`, `verify`, `VerifyResult` |
| `tests/unit/eval/test_audit_chain.py` | Red tests across all 9 paths |
| `src/codegenie/eval/models.py` | (If S1-02 didn't include `host_fingerprint`) surface as a follow-up; do NOT silently edit a contract owned by S1-02 — flag to S1-02 maintainer |

## Out of scope

- **Cross-host chain merging** — explicit non-goal per Gap #5; integration tests in S7-02 will verify the per-host floor.
- **`codegenie eval verify` CLI subcommand** — handled by S4-03; this story exposes the `verify(...)` library function only.
- **Sigstore signing of the chain head** — explicit non-goal `#2` in `phase-arch-design.md`; Phase 16 work.
- **Chain pruning / archival** — out of scope; the chain grows unboundedly and is the operator's manual concern.

## Notes for the implementer

- **Reuse Phase 0's `codegenie.audit` chain primitives** — the existing module path is `src/codegenie/audit.py` (Phase 0 S3-06). If Phase 0 exposes `chain_append` / `chain_verify` as named helpers, call them directly; if it doesn't yet, factor the BLAKE3-content + SHA-256-identity composition into `codegenie.hashing` or a small `codegenie.audit_chain` helper module and reuse it. Coordinate with the Phase 0 maintainer to avoid forking the algorithm — `Cross-cutting concerns` in `stories/README.md` is explicit on this.
- The eval chain lives at `.codegenie/eval/runs/`, separate from Phase 0's `.codegenie/runs/` (gather records). Two distinct directories, same primitives; do not merge.
- Genesis convention `"0" * 64` is a hex string, NOT bytes; the comparison happens after `report.prev_hash` is already a hex string per `BenchRunReport`'s Pydantic schema.
- The UTC ISO timestamp in filenames: use `datetime.now(UTC).isoformat()`; replace `":"` with `"-"` for filesystem-safety (matches Phase 0 S3-06 §AC).
- `verify`'s "stop on first mismatch" semantic means later records aren't validated once tamper is detected; this is the documented design (operator sees a precise pointer to the divergent file).
- For `host_fingerprint` (Gap #5): if `BenchRunReport` doesn't already carry the field as of S1-02, surface this in your review note for the S1-02 author — adding it later requires a wire-type bump. The field is BLAKE3 of `hostname || mac_addr || harness_install_path` OR a UUID generated on first run and persisted to `.codegenie/eval/.host_id` (operator's choice; the loader/runner picks).
- **Two concurrent writers** test: do NOT use real threads — easier to compute a stale `prev_hash` snapshot, write a record (advances head), then attempt a second `write_run_record` with the stale value. This deterministically reproduces the race semantics without flakiness.
- Don't `unlink` corrupt records during `verify` — operators want them on disk for forensic review.
