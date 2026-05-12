# Story S3-06 — Audit writer + `audit verify` re-verification

**Step:** Step 3 — Build the harness internals (cache, coordinator, validator, sanitizer, writer, config)
**Status:** Ready
**Effort:** S
**Depends on:** S3-05
**ADRs honored:** ADR-0004, ADR-0001, ADR-0011

## Context

This story closes **Architect Gap 2** — the missing dual audit anchors per `../phase-arch-design.md §Gap analysis & improvements §Gap 2`. The synthesis as-written ([`../final-design.md §2.12`]) provided only a *whole-gather* anchor (`yaml_sha256` on `RunRecord`), but Phase 11's PR-provenance bundle needs per-probe evidence integrity, and Phase 13's cost ledger (production ADR-0027) needs per-probe spend attribution. Neither is served by the YAML-level anchor alone.

ADR-0004 puts both anchors on `ProbeExecutionRecord`: `cache_key` (the SHA-256 identity tuple — already produced by `CacheStore.key_for` in S3-01) and `blob_sha256` (SHA-256 of the **sanitized** blob bytes — distinct from the BLAKE3 content hash, which is over inputs). The `codegenie audit verify` subcommand re-reads each claimed blob, recomputes `blob_sha256`, and reports any mismatches. S2-05 already shipped the `ProbeExecutionRecord` Pydantic model with both fields; this story wires the **population** and the **verification path**.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap analysis & improvements §Gap 2` — the under-specification this story closes (read in full)
  - `../phase-arch-design.md §Component design / Audit writer` — `RunRecord` shape, `AuditWriter.record(...)`, `codegenie audit verify`
  - `../phase-arch-design.md §Data model` — `ProbeExecutionRecord` Pydantic model (both fields)
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0004-probe-execution-audit-anchor.md` — ADR-0004 — `cache_key` + `blob_sha256` per probe execution; `audit verify` re-verifies blob hashes; sanitized blob is what's hashed
  - `../ADRs/0001-cache-content-hash-algorithm.md` — ADR-0001 — `blob_sha256` is SHA-256 (computed via `hashing.identity_hash` or stdlib `hashlib.sha256` routed through `hashing.py`); the only file importing `hashlib.sha256` is `hashing.py`
  - `../ADRs/0011-codegenie-directory-permissions-model.md` — ADR-0011 — `runs/<utc-iso>-<short>.json` is written `0600`
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0024-cost-observability-end-to-end.md` — the cost-observability commitment this anchor serves
  - `../../../production/adrs/0027-cost-attribution-model.md` — the attribution model `cache_key` feeds into
- **Source design:**
  - `../final-design.md §2.12` — original audit record (under-specified; Gap 2 closes)
- **Existing code:**
  - `src/codegenie/audit.py` (S2-05) — `RunRecord`, `ProbeExecutionRecord` Pydantic models with both fields **already declared**; this story implements the writer + verifier that populates them
  - `src/codegenie/coordinator/coordinator.py` (S3-05) — produces `GatherResult` with `Ran(output)` / `CacheHit(output, key)` / `Skipped(reason)`
  - `src/codegenie/cache/store.py` (S3-01) — `CacheStore.key_for`; the `cache_key` value comes from here
  - `src/codegenie/hashing.py` (S2-03) — `identity_hash` for SHA-256 (route `blob_sha256` through this)
  - `src/codegenie/output/sanitizer.py` (S3-03) — produces `SanitizedProbeOutput`; the **sanitized** bytes are what get hashed

## Goal

`AuditWriter.record(...)` writes `<output_dir>/runs/<utc-iso>-<short>.json` (mode `0600`) where every `ProbeExecutionRecord` has populated `cache_key` **and** `blob_sha256`; `codegenie audit verify` walks the runs directory, re-reads claimed blobs, recomputes `blob_sha256`, and exits 0 on no mismatches, non-zero on tamper detection.

## Acceptance criteria

- [ ] `AuditWriter.record(run_record: RunRecord, output_dir: Path) -> Path` writes the run-record file atomically (`.tmp` → `fsync` → `os.replace`) and re-applies mode `0600` post-write (ADR-0011).
- [ ] The output filename matches `runs/<utc-iso>-<short>.json` where `<utc-iso>` is `datetime.now(UTC).isoformat()` (with the colons safe-replaced if needed for filesystem compatibility) and `<short>` is `secrets.token_hex(4)`.
- [ ] `AuditWriter` accepts a `GatherResult` and constructs `ProbeExecutionRecord`s — populating both `cache_key` and `blob_sha256` for every probe execution.
  - `Ran(output)` → `cache_key` is the key computed by the cache layer for this run; `blob_sha256` is `hashing.identity_hash(<sanitized_blob_bytes>)`.
  - `CacheHit(output, key)` → `cache_key = key`; `blob_sha256` is recomputed over the sanitized blob (must match the cache's stored hash).
  - `Skipped(reason)` → `cache_key` is the would-be key (computed at dispatch time); `blob_sha256 = ""` sentinel; `exit_status = "skipped"`.
- [ ] `codegenie audit verify` CLI subcommand walks every `*.json` under `<repo>/.codegenie/runs/`, deserializes each `RunRecord`, for every `ProbeExecutionRecord` with non-empty `blob_sha256` reads the cache blob at the claimed `cache_key`, recomputes the blob's SHA-256, and reports mismatches.
- [ ] Exit codes for `audit verify`: 0 on no mismatches; non-zero (per the CLI exit table — typically 1 or a dedicated code) on any mismatch; structured `audit.verify.mismatch` log event for each.
- [ ] All tests below pass; `ruff`, `mypy --strict`, `pytest` clean on touched files.

## Implementation outline

1. Author `AuditWriter` in `src/codegenie/audit.py` (extending S2-05's models with the writer class — keep models intact). Public surface:
   ```python
   class AuditWriter:
       def __init__(self, output_dir: Path) -> None: ...
       def record(self, gather_result: GatherResult, cli_version: str, sherpa_commit: str | None, tool_versions: dict[str, str], yaml_sha256: str) -> Path: ...
   ```
   The `record` method builds a `RunRecord` from the `GatherResult` and the meta-fields, walks `executions.items()` constructing `ProbeExecutionRecord`s with both anchors populated, serializes via `RunRecord.model_dump_json(...)`, and writes atomically.
2. Add a `_blob_sha256(sanitized: SanitizedProbeOutput) -> str` helper that JSON-serializes the sanitized output (`sort_keys=True`, compact separators — same canonicalization as the cache store) and routes through `hashing.identity_hash`. The function must return the same hex string the cache's stored SHA-256 has, because `audit verify` will compare them.
3. Add `verify_runs(runs_dir: Path) -> int` (returns mismatch count) in `audit.py`. The function reads every `runs/*.json`, looks up each `cache_key` in the cache index, reads the blob, recomputes SHA-256, and yields mismatches.
4. Wire `audit verify` as a `click` command in `src/codegenie/cli.py` (S4-02 owns the wider CLI but this story stubs the subcommand if S4-02 isn't merged yet — coordinate via dependency on S4-02 if needed; the manifest places this story before S4-02 so the subcommand entry-point lives here).
5. Tests for population, atomic write, mode bits, mismatch detection.

## TDD plan — red / green / refactor

Two anchored behaviors, each Gap-2 critical: (a) **`cache_key` populated for every variant**, (b) **`blob_sha256` populated and re-verifiable** via `audit verify`. Each gets its own red test.

### Red — write the failing tests first

Test file path: `tests/unit/test_audit_anchors.py` (Gap-2 anchor).

```python
# tests/unit/test_audit_anchors.py
import json
from pathlib import Path
from codegenie.audit import AuditWriter, verify_runs

def test_cache_key_populated_for_ran_cachehit_skipped(tmp_path):
    """Gap 2: every ProbeExecutionRecord has a non-empty cache_key (except Skipped's
    must still carry the would-be key)."""
    # arrange: construct a GatherResult with one Ran, one CacheHit, one Skipped probe.
    # act: writer.record(gather_result, ...) → path
    # assert:
    record = json.loads(path.read_text())
    for probe in record["probes"]:
        assert probe["cache_key"], f"cache_key empty for {probe['name']}"
        if probe["exit_status"] == "skipped":
            assert probe["blob_sha256"] == ""
        else:
            assert probe["blob_sha256"], f"blob_sha256 empty for {probe['name']}"

def test_blob_sha256_matches_recomputation(tmp_path):
    """Gap 2: blob_sha256 in the run-record matches a fresh recompute of the
    sanitized blob bytes via hashing.identity_hash."""
    # arrange: run one probe through the (mocked or real) coordinator; record the audit
    # act: read back the run-record; locate the cache blob at the claimed cache_key;
    #      recompute SHA-256 over the blob bytes the same way AuditWriter did.
    # assert: stored blob_sha256 == recomputed value
    ...

def test_audit_verify_reports_zero_mismatches_on_clean_run(tmp_path):
    """audit verify exits 0 when nothing has been tampered with."""
    # arrange: do a normal record(...) → fresh run-record + intact cache blob.
    # act: mismatch_count = verify_runs(tmp_path / ".codegenie" / "runs")
    # assert: mismatch_count == 0
    ...

def test_audit_verify_detects_tampered_blob(tmp_path, caplog):
    """audit verify reports a mismatch when the cache blob's bytes have been
    rewritten after the run-record was sealed."""
    # arrange: record a normal run; then overwrite the cache blob bytes with
    #          a different valid JSON payload (so the SHA-256 changes).
    # act: mismatch_count = verify_runs(...)
    # assert: mismatch_count == 1; caplog contains an "audit.verify.mismatch" event
    #         naming the probe and the cache_key.
    ...

def test_run_record_file_is_mode_0600(tmp_path):
    # arrange + act: AuditWriter(out).record(...)
    # assert: oct(path.stat().st_mode)[-3:] == "600"
    ...

def test_atomic_write_no_partial_file(tmp_path, monkeypatch):
    # arrange: patch os.replace to raise mid-call.
    # act + assert: record(...) raises; the runs/*.json file does NOT exist
    #               (only a .tmp may); no half-written record visible.
    ...
```

Run; confirm `ImportError`/`AttributeError`/`AssertionError`. Commit as the red marker.

### Green — make it pass

1. Implement `AuditWriter.record(...)` populating both anchors from `GatherResult`.
2. Implement `_blob_sha256` routing through `hashing.identity_hash`; canonicalize the sanitized output with `json.dumps(..., sort_keys=True, separators=(",", ":"))` so the recomputation matches.
3. Implement `verify_runs(runs_dir)` reading every run-record, mapping `cache_key` → blob path via the cache store, recomputing SHA-256, returning the mismatch count.
4. Atomic write helper: same shape as S3-01's `_atomic_write` + chmod (consider extracting a shared helper in a follow-up; for this story, duplicate the small function locally — not worth the abstraction).
5. Stub the `audit verify` click subcommand in `cli.py` if S4-02 hasn't merged yet (a 5-line stub that calls `verify_runs` and translates to exit codes). S4-02 finalizes the CLI wiring.

### Refactor — clean up

- Type hints throughout; `mypy --strict` clean.
- Docstrings on `AuditWriter.record` and `verify_runs` citing ADR-0004 §Decision.
- Module docstring on `audit.py` notes that `_blob_sha256` canonicalization (sort_keys + compact separators) must stay byte-identical to the cache's storage canonicalization (S3-01) — otherwise verification produces phantom mismatches.
- Verify the filename's UTC-ISO format is filesystem-safe (some platforms reject `:`). Either replace colons with `-` or use `T<HHMMSS>` style. Tests pin the chosen format.
- `<short>` is `secrets.token_hex(4)` (8 hex chars), matching `phase-arch-design.md §Component design / Audit writer`.
- Structured log events: `audit.write.ok` on success, `audit.write.failed` on disk-IO error, `audit.verify.mismatch` per mismatch (with `cache_key`, `probe_name`, `expected`, `actual`).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/audit.py` | Extend with `AuditWriter` class + `verify_runs` function; do NOT alter the existing Pydantic models from S2-05 (they already have `cache_key`, `blob_sha256`) |
| `tests/unit/test_audit_anchors.py` | New — Gap-2 anchor with separate tests for `cache_key` population, `blob_sha256` re-verification, tamper detection, modes, atomic write |
| `src/codegenie/cli.py` | Stub `audit verify` subcommand here (S4-02 may overwrite/extend; if so, this story's stub becomes the seed) — minimal: import `verify_runs`, exit with mismatch count |

## Out of scope

- **`yaml_sha256` on `RunRecord`** — already part of `RunRecord` per S2-05's models; this story populates it from `Writer.write`'s output (S3-03 produces the YAML; AuditWriter hashes it). No new contract.
- **Including the **contents** of `~/.codegenie/.tool-cache.json` in the run-record** — explicitly rejected per `phase-arch-design.md §Open questions` #4. `tool_versions` only.
- **HMAC signing of the run-record** — deferred to Phase 14 with the webhook listener.
- **Phase 11 PR-provenance bundle layout** — Phase 11's job; this story makes `blob_sha256` available for that consumer to use.
- **Phase 13 cost-ledger writer** — Phase 13's job; this story makes `cache_key` available for that consumer.
- **`os_kernel` SHA prefix details** — already part of `RunRecord` per `phase-arch-design.md §Component design / Audit writer`; populate via `platform.platform()` SHA-256'd to redact hostname.

## Notes for the implementer

- **This story closes Gap 2 from `../phase-arch-design.md §Gap analysis`.** The dual-anchor pattern is what makes the audit record useful to **both** Phase 11 (evidence integrity) **and** Phase 13 (cost attribution). Per `phase-arch-design.md §Implementation-level risks` #2: write the Gap-2 tests **first**.
- The **sanitized** blob is what's hashed, not the raw probe output (ADR-0004 §Consequences). The path-scrubbed, field-name-filtered representation is what's hashable; anything else makes verification depend on data the system has by design discarded.
- The blob-SHA-256 canonicalization must match the cache store's (S3-01) byte-for-byte — same `json.dumps(..., sort_keys=True, separators=(",", ":"))`. If S3-01 used a different canonicalization, *converge* on one and update both; the verification path **must** recompute to the same bytes.
- A `CacheHit` carries `cache_key` explicitly (ADR-0009 §Decision). For `Ran`, the coordinator must surface the key somehow — the cleanest seam is to extend the coordinator to write the key into a sidecar (e.g., return `Ran(output, key)` rather than `Ran(output)`). **Coordinate with S3-05**: this story may need to file a small change in S3-05's `Ran` shape if S3-05 didn't include the key. Surface the conflict, don't average — per Rule 7.
- The `audit verify` exit-code contract belongs to the CLI table in S4-02. For this story, the function returns the mismatch count; the CLI translates to 0/1.
- Per ADR-0011, mode `0600` is re-applied via `os.chmod` after atomic write. Verify with a test.
- `verify_runs` should be resilient to missing cache blobs — a missing blob counts as a mismatch (the audit record claims a hash but the blob is gone), not a hard failure. Log `audit.verify.missing_blob` and continue.
- `secrets.token_hex(4)` is **random**, not content-derived. It's only the filename suffix; the artifact's identity is the `yaml_sha256` field inside.
