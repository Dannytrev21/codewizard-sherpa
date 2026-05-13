# Story S3-06 — Audit writer + `audit verify` re-verification

**Step:** Step 3 — Build the harness internals (cache, coordinator, validator, sanitizer, writer, config)
**Status:** Ready (Hardened)
**Effort:** S
**Depends on:** S3-05
**See also:** S4-01 (`LanguageDetectionProbe` — first real probe whose output the verifier walks); S4-02 (CLI exit-code table — this story stubs the `audit verify` subcommand at slot `4`)
**ADRs honored:** ADR-0004, ADR-0001, ADR-0011, ADR-0009 (shape of `ProbeExecution` consumed)

## Validation notes

Hardened on 2026-05-13 by `phase-story-validator` v1. Three critics returned **50 findings** (15 Coverage + 20 Test-Quality + 15 Consistency; 15 block, 29 harden, 6 nit; 0 `NEEDS RESEARCH`). Full report at [`_validation/S3-06-audit-writer-verify.md`](_validation/S3-06-audit-writer-verify.md). Material changes:

- **Pinned `hashing.identity_hash_bytes` (NOT `identity_hash`).** Pre-hardening the story named `hashing.identity_hash` — that function takes variadic strings with an arity-byte prefix (`hashing.py:67-79`); using it for the blob hash would have produced a hash that NEVER equals the cache's stored `blob_sha256` (`cache/store.py:269` uses `identity_hash_bytes`). Every `audit verify` call would have reported universal phantom mismatches. ADR-0001 §Decision chokepoint discipline is enforced via a grep test: `'hashlib' not in audit.py` (modulo docstring), `'blake3' not in audit.py`.
- **Pinned the `cache_key → blob path` resolution.** Blobs live at `cache/blobs/<2-char-shard>/<blake3-hex>.json` (BLAKE3, not the SHA-256 `cache_key`). Verifier walks `<cache_dir>/index.jsonl`, finds the **latest** record matching `cache_key` (last-write-wins, mirroring `_latest_record_for`), reads `blob_blake3`, reads raw bytes via `Path.read_bytes()`. **NOT through `CacheStore.get`** — `get` returns a deserialized `ProbeOutput`, and re-serialization would mask byte-level tampering. Promotes `_latest_record_for` to a public `CacheStore.get_index_record(cache_key)`.
- **Pinned `Ran(output, key)` extension as a coordinated S3-05 amendment shipped in the same PR.** S3-05 (commit `8129392`) ships `Ran(output: SanitizedProbeOutput)` — no key field. This story's diff extends to `Ran(output: SanitizedProbeOutput, key: str)`, updates arch §Data model lines 661-680, and updates S3-05's tests. Per CLAUDE.md Rule 7 (surface, don't average), the amendment is part of THIS story's scope rather than a buried "may need to file" implementer note. `AuditWriter` reads `cache_key` from the field — **re-derivation via `cache.key_for(...)` at audit-write time is forbidden** (would record what-we'd-ask-for-now, not what-the-coordinator-actually-asked).
- **Pinned `Skipped.cache_key = ""` + `blob_sha256 = ""` sentinels.** ADR-0004 §Consequences line 44's "would-be key" is a pre-S3-05 artifact: S3-05 pins `applies() → key_for → cache.get` ordering, so `applies()=False` short-circuits before `key_for` runs. ADR-0004 amendment is filed as follow-up #1. Phase 13 cost ledger semantics: skipped probes consume zero cost; no attribution anchor needed.
- **Pinned the `_exit_status_for(execution) -> Literal[...]` helper mapping.** Centralized in `audit.py`: `Skipped → "skipped"`; `CacheHit → "ok"`; `Ran(errors=[]) → "ok"`; `Ran(errors)` with any string starting `"timeout:"` (S3-05 AC-10 prefix) → `"timeout"`; `Ran(errors)` otherwise → `"error"`. Parametrized test asserts all four mappings — kills the "always-`ok`" mutant.
- **Pinned errored-`Ran` × cache + audit interaction.** Coordinator MUST NOT `cache.put` an errored `Ran` (errors are not replayable — small S3-05 amendment shipped same PR). `AuditWriter` writes `cache_key = ran.key`, `blob_sha256 = ""` sentinel. `audit verify` skips blob recomputation for any record with empty `blob_sha256`.
- **Added AC-7 yaml-anchor recomputation.** Exit criterion #12 (`final-design.md §11`, `High-level-impl.md:145`) requires it; pre-hardening only per-probe `blob_sha256` was verified. New test `test_audit_verify_detects_yaml_tamper`.
- **Pinned the audit-event-name contract.** `audit.write.ok` / `audit.write.failed` / `audit.verify.ok` / `audit.verify.mismatch` / `audit.verify.missing_blob` / `audit.verify.yaml_mismatch`. Distinct from probe-lifecycle events at `phase-arch-design.md:755`; Phase 11 + Phase 13 subscribe by name. Snapshot test pins literal strings.
- **Pinned filename portability.** `runs/{YYYY}{MM}{DD}T{HHMMSS}Z-{short}.json` via `datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')` + `secrets.token_hex(4)`. Windows-safe. Test pattern: `re.fullmatch(r'\d{8}T\d{6}Z-[0-9a-f]{8}\.json', path.name)`. The arch §Component design line 599 `<short-hash>` misnomer is filed as follow-up #2.
- **Pinned `<output_dir> = .codegenie/context/`** (so the runs dir is `.codegenie/context/runs/`) per the canonical `High-level-impl.md:251`. The ambiguous ASCII tree at `final-design.md:65,461` is filed as follow-up #5.
- **Pinned `runs/` directory mode `0700`** post-`mkdir` (was silent in AC-1). Mirrors `cache/store.py:_ensure_dir`.
- **Pinned umask-resistance** in the mode-bit test: `os.umask(0o022)` before write proves the chmod call is load-bearing (precedent: `test_output_writer.py:47-56`).
- **Pinned `fsync` ordering** via `Mock.attach_mock` (precedent: `test_output_writer.py:60-71`). Kills the "dropped fsync" mutant.
- **Pinned the shared canonicalization helper.** `cache.store._serialize_output` (currently private) is promoted to module-public `cache.store.serialize_output(output: ProbeOutput | SanitizedProbeOutput) -> bytes` — single source of truth for `sort_keys=True, separators=(",", ":")`. Both `cache.put` and `AuditWriter._blob_sha256` import it. Test pins `set(fields(SanitizedProbeOutput)) == set(fields(ProbeOutput))` to defeat future field-set drift.
- **Pinned CLI exit code at slot `4`** (currently reserved in `phase-arch-design.md:420`). Slot `1` is reserved for default-click-handler unhandled-exception; tamper detection deserves a distinct slot so operators can tell "verify crashed" from "verify found a tamper." S4-02 may re-number; this story OWNS the slot.
- **Pinned collision retry.** Two `record()` calls in the same wall-clock-second collide on `<utc-iso>` with ~1/65k odds; writer uses `os.open(<final>.tmp, O_CREAT|O_EXCL|O_WRONLY, 0o600)` then `os.replace`; on `FileExistsError` retries with a fresh `secrets.token_hex(4)` up to 3 times; persistent collision raises `CodegenieError('audit.record.collision')`.
- **Rewrote every TDD test with concrete, runnable Python.** No more `...` placeholders. Defined `path` (was undefined in the first test), pinned imports, pinned fixtures. Parametrized over `[Ran-ok, Ran-error, CacheHit, Skipped]`. Added empty-`GatherResult`, idempotence, sanitized-vs-raw, byte-level-tamper, index-tamper-no-false-positive, missing-blob, yaml-tamper, filename-portability, umask-resistance, fsync-ordering, audit-write-failed-event, collision-retry, and Pydantic round-trip assertions.

Five follow-up doc cleanups filed (separate PRs, NOT in this story's scope per Rule 3): (1) ADR-0004 §Consequences drop "would-be key"; (2) arch line 599 `<short-hash>` → `<short>`; (3) arch line 590 `os_kernel` → `os_kernel_sha`; (4) arch §Data model lines 661-680 update for `Ran(output, key)`; (5) `final-design.md:65,461` ASCII tree under `.codegenie/context/runs/`.

## Context

This story closes **Architect Gap 2** — the missing dual audit anchors per `../phase-arch-design.md §Gap analysis & improvements §Gap 2`. The synthesis as-written ([`../final-design.md §2.12`]) provided only a *whole-gather* anchor (`yaml_sha256` on `RunRecord`), but Phase 11's PR-provenance bundle needs per-probe evidence integrity, and Phase 13's cost ledger (production ADR-0027) needs per-probe spend attribution. Neither is served by the YAML-level anchor alone.

ADR-0004 puts both anchors on `ProbeExecutionRecord`: `cache_key` (the SHA-256 identity tuple — already produced by `CacheStore.key_for` in S3-01) and `blob_sha256` (SHA-256 of the **sanitized** blob bytes — distinct from the BLAKE3 content hash, which is over inputs). The `codegenie audit verify` subcommand re-reads each claimed blob (raw bytes, NOT through `CacheStore.get`), recomputes `blob_sha256`, ALSO recomputes the whole-YAML anchor, and reports any mismatches. S2-05 already shipped the `ProbeExecutionRecord` + `RunRecord` Pydantic models with both fields; this story wires the **population** and the **verification path** — plus the coordinated S3-05 amendments needed to make `Ran` carry the key (per Rule 7).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap analysis & improvements §Gap 2` — the under-specification this story closes (read in full)
  - `../phase-arch-design.md §Component design / Audit writer` — `RunRecord` shape, `AuditWriter.record(...)`, `codegenie audit verify`
  - `../phase-arch-design.md §Data model` — `ProbeExecutionRecord` Pydantic model (both fields); `Ran | CacheHit | Skipped` (note: lines 661-680 declare `Ran(output)` — this story's diff updates that to `Ran(output, key)` per follow-up #4)
  - `../phase-arch-design.md §Harness engineering / Logging` line 755 — probe-lifecycle event-name contract (audit.* events are a separate contract surface, see Goal)
  - `../phase-arch-design.md §Component design / CLI` line 420 — exit-code table (slot `4` is reserved; this story claims it for `audit verify` tamper detection)
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0004-probe-execution-audit-anchor.md` — ADR-0004 — `cache_key` + `blob_sha256` per probe execution; `audit verify` re-verifies blob hashes; **sanitized** blob is what's hashed; (follow-up #1 amends §Consequences line 44 "would-be key" → empty sentinel)
  - `../ADRs/0001-cache-content-hash-algorithm.md` — ADR-0001 — `blob_sha256` is SHA-256 via `hashing.identity_hash_bytes` (NOT `identity_hash`); `hashing.py` is the only file importing `hashlib.sha256`
  - `../ADRs/0011-codegenie-directory-permissions-model.md` — ADR-0011 — `runs/` dir is `0700`; `runs/<utc-iso>-<short>.json` is `0600`; modes re-applied via `os.chmod` post-write
  - `../ADRs/0009-cache-hit-pass-through-coordinator-output.md` — ADR-0009 — `GatherResult(outputs, executions)` with tagged-union `ProbeExecution`; line 41 mandates `CacheHit.key` (used by this story's verifier)
- **Production ADRs:**
  - `../../../production/adrs/0024-cost-observability-end-to-end.md` — the cost-observability commitment this anchor serves
  - `../../../production/adrs/0027-cost-attribution-model.md` — the attribution model `cache_key` feeds into
- **Source design:**
  - `../final-design.md §2.12` — original audit record (under-specified; Gap 2 closes)
  - `../final-design.md §11 exit criterion #12` — `audit verify` smoke run reports zero mismatches
- **Cross-story:**
  - `S3-05-coordinator-prelude-budget.md` — coordinator produces `GatherResult`; **this story amends** the `Ran` variant to carry `key: str` and adds the no-cache-on-error rule to `_dispatch_one`
- **Existing code:**
  - `src/codegenie/audit.py` (S2-05) — `RunRecord`, `ProbeExecutionRecord` Pydantic models with both fields **already declared**; this story implements the writer + verifier that populate them
  - `src/codegenie/cache/store.py` (S3-01) — `CacheStore.key_for`, `_latest_record_for` (promoted to public `get_index_record`); `_serialize_output` (promoted to public `serialize_output` for the audit writer to share canonicalization)
  - `src/codegenie/hashing.py` (S2-03) — `identity_hash_bytes` for SHA-256 of raw blob bytes (use THIS, not `identity_hash`)
  - `src/codegenie/output/sanitizer.py` (S3-03) — produces `SanitizedProbeOutput`; the **sanitized** bytes are what get hashed
  - `tests/unit/test_output_writer.py:47-56,60-71,118-134` — umask-resistance, fsync-ordering, atomic-write precedents to mirror

## Goal

`AuditWriter.record(...)` writes `.codegenie/context/runs/{YYYY}{MM}{DD}T{HHMMSS}Z-{short}.json` (mode `0600`, parent dir `0700`) where every `ProbeExecutionRecord` has populated `cache_key` and `blob_sha256` per the per-variant rules below; `codegenie audit verify` walks the runs directory, recomputes the per-probe `blob_sha256` from raw cache-blob bytes AND the whole `yaml_sha256` from the persisted YAML, and exits `0` on no mismatches, `4` on any mismatch (tamper detection slot per arch §CLI exit codes). Audit-event names (`audit.write.ok` / `audit.write.failed` / `audit.verify.ok` / `audit.verify.mismatch` / `audit.verify.missing_blob` / `audit.verify.yaml_mismatch`) are contract — Phase 11 + Phase 13 subscribe by name.

## Acceptance criteria

ACs are grouped A–E. Every AC is individually verifiable and traceable.

### A — Writer surface + atomic write + permissions

- [ ] **AC-1.** `AuditWriter(output_dir: Path)` constructor; `record(self, gather_result: GatherResult, *, cli_version: str, sherpa_commit: str | None, tool_versions: dict[str, str], yaml_sha256: str) -> Path` public method. `output_dir` resolves to `<repo>/.codegenie/context/` (per `High-level-impl.md:251`); the run-record is written under `<output_dir>/runs/`. The method ensures `<output_dir>/runs/` exists at mode `0700` (`os.chmod` re-applied post-`mkdir`, mirroring `cache/store.py:_ensure_dir`).
- [ ] **AC-2.** **Filename format pinned:** `runs/{YYYY}{MM}{DD}T{HHMMSS}Z-{short}.json` via `datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')` + `{short} = secrets.token_hex(4)` (8 hex chars). No `:` ever — Windows-safe. Test asserts `re.fullmatch(r'\d{8}T\d{6}Z-[0-9a-f]{8}\.json', path.name)`.
- [ ] **AC-3.** **Atomic write** sequence: serialize via `RunRecord.model_dump_json(indent=2)` → `os.open(<final>.tmp, O_CREAT|O_EXCL|O_WRONLY, 0o600)` → `os.write` → `os.fsync` → `os.replace(<final>.tmp, <final>)` → `os.chmod(<final>, 0o600)` (re-applied post-`replace` per ADR-0011, defeats `actions/cache` umask flattening). The `fsync < replace` ordering is asserted by `Mock.attach_mock` (precedent: `test_output_writer.py:60-71`). On `os.replace` raising `OSError`, no `runs/*.json` exists (only a `.tmp` may; its mode is `0600`), the original `OSError` propagates, AND a `audit.write.failed` structlog event is emitted with `path` + `error_repr` before re-raise.
- [ ] **AC-4.** **Collision retry contract:** on `FileExistsError` from the `O_EXCL` open (two writers same UTC-second, same random suffix), the writer retries with a fresh `secrets.token_hex(4)` up to 3 times. Persistent collision raises `CodegenieError('audit.record.collision')`. A test monkeypatches `secrets.token_hex` to return a fixed value first then a different one, confirms one retry, one success.

### B — Per-variant anchor population (the Gap-2 contract)

This story coordinates with S3-05 to make this AC implementable:

- [ ] **AC-5.** **S3-05 amendment (shipped in same PR per Rule 7):** the `Ran` dataclass in `coordinator.py` is extended to `Ran(output: SanitizedProbeOutput, key: str)`. S3-05's tests are updated to construct `Ran(output, key)`. Arch §Data model lines 661-680 amendment is follow-up #4. **Re-derivation via `cache.key_for(...)` at audit-write time is forbidden** — `AuditWriter` reads `cache_key` from `Ran.key` directly.
- [ ] **AC-6.** **S3-05 amendment (same PR):** the coordinator's success path in `_dispatch_one` reads `if not sanitized.errors: cache.put(key, sanitized)` — errored outputs are NOT cached (would replay failures). A new S3-05 test `test_dispatch_does_not_cache_errored_ran` pins this.
- [ ] **AC-7.** **Per-variant `cache_key` + `blob_sha256` + `exit_status` matrix** (the Gap-2 contract; parametrized test asserts each row):

  | Execution variant | `cache_key` | `blob_sha256` | `exit_status` |
  |---|---|---|---|
  | `Ran(output, key)` with `output.errors == []` | `key` | `hashing.identity_hash_bytes(serialize_output(output))` | `"ok"` |
  | `Ran(output, key)` with `output.errors != []` AND any starts `"timeout:"` | `key` | `""` (empty sentinel — not cached per AC-6) | `"timeout"` |
  | `Ran(output, key)` with `output.errors != []` AND no `"timeout:"` prefix | `key` | `""` (empty sentinel — not cached per AC-6) | `"error"` |
  | `CacheHit(output, key)` | `key` | `hashing.identity_hash_bytes(serialize_output(output))` | `"ok"` |
  | `Skipped(reason)` | `""` (empty sentinel — `applies()`-first ordering means no key was computed) | `""` (empty sentinel) | `"skipped"` |

  The mapping lives in a `_exit_status_for(execution: ProbeExecution) -> Literal["ok","error","timeout","skipped"]` helper in `audit.py`. Helper is tested in isolation over all five rows.

- [ ] **AC-8.** **Hashing chokepoint pin (ADR-0001):** `audit.py` does NOT `import hashlib` or `import blake3`. Blob-hash computation goes through `from codegenie.hashing import identity_hash_bytes` exclusively; canonicalization goes through `from codegenie.cache.store import serialize_output` (the shared helper). A grep test asserts the import discipline: `'hashlib' not in <source>` AND `'blake3' not in <source>` (excluding docstrings).
- [ ] **AC-9.** **Sanitized-vs-raw invariant (ADR-0004 §Consequences):** `blob_sha256` is computed over the **sanitized** serialization, not the raw `ProbeOutput`. A test plumbs a `ProbeOutput` with an absolute path in `schema_slice` through `OutputSanitizer.scrub` → asserts the audit record's `blob_sha256` equals SHA-256 of the *sanitized* bytes AND is NOT equal to SHA-256 of the *raw* bytes (the two differ because the path was rewritten).

### C — `verify_runs` semantics

- [ ] **AC-10.** **`verify_runs(runs_dir: Path, cache_dir: Path, yaml_path: Path) -> int`** walks every `*.json` under `runs_dir`, deserializes each into `RunRecord.model_validate_json(...)`, and returns the integer count of mismatches detected. Pure-read function; never mutates the run-records, never mutates the cache, never raises `FileNotFoundError` to the caller.
- [ ] **AC-11.** **Per-probe `blob_sha256` re-verification:** for every `ProbeExecutionRecord` whose `blob_sha256 != ""`, the verifier (1) walks `<cache_dir>/index.jsonl` for the **latest** record matching `cache_key` (via `CacheStore.get_index_record(key)` — promoted from `_latest_record_for`); (2) resolves the blob path `<cache_dir>/blobs/<shard>/<blob_blake3-hex>.json`; (3) reads RAW bytes via `Path.read_bytes()` (NOT through `CacheStore.get`); (4) computes `recomputed = hashing.identity_hash_bytes(raw_bytes)`; (5) compares to `record.blob_sha256`. On disagreement, increment mismatch count by 1 AND emit `audit.verify.mismatch` with `cache_key`, `probe_name`, `expected = record.blob_sha256`, `actual = recomputed`.
- [ ] **AC-12.** **Missing-blob handling:** if the index lookup returns `None` (no record for `cache_key`), or the blob file does not exist (cache GC'd), or the file is unreadable, the verifier counts it as 1 mismatch AND emits `audit.verify.missing_blob` with `cache_key` + `probe_name` + `reason` ∈ `{"no_index_record", "missing_blob_file", "unreadable"}`. The walk continues to the next record. Never raises `FileNotFoundError`.
- [ ] **AC-13.** **Whole-YAML anchor re-verification** (closes exit criterion #12): for each `RunRecord`, the verifier reads `yaml_path` (default `<output_dir>/repo-context.yaml`) raw bytes, recomputes `yaml_recomputed = hashing.identity_hash_bytes(yaml_bytes)`, compares to `record.yaml_sha256`. On disagreement, increment mismatch count AND emit `audit.verify.yaml_mismatch` with `expected`, `actual`, `run_record_path`. Missing YAML file counts as 1 mismatch with `reason="yaml_missing"`.
- [ ] **AC-14.** **Empty-blob_sha256 records skipped** for the blob re-verification path. A `Skipped`, error-`Ran`, or timeout-`Ran` record has `blob_sha256 == ""` and is NOT walked for blob verification (the YAML anchor still applies). No `audit.verify.missing_blob` is emitted for these (they correctly claim no blob).
- [ ] **AC-15.** **Summary event:** after a complete walk, the verifier emits `audit.verify.ok` (always — summary event) with `mismatch_count`, `run_records_walked`, `probes_walked`, `yaml_anchors_walked`. The event is emitted EXACTLY once per `verify_runs` call.

### D — CLI subcommand wiring

- [ ] **AC-16.** `src/codegenie/cli.py` exposes the `audit verify` click subcommand (stub seed; S4-02 finalizes wider CLI). Stub calls `verify_runs(runs_dir, cache_dir, yaml_path)`, translates: `sys.exit(0)` on `mismatch_count == 0`, `sys.exit(4)` (the currently-reserved slot per `phase-arch-design.md:420`) otherwise. **Slot `4` is owned by this story** — chosen distinct from slot `1` (unhandled-exception via default click handler) so operators can tell "verify crashed" from "verify found tamper." A test using `click.testing.CliRunner` asserts: clean run → exit 0; tampered run → exit 4 (asserts `result.exit_code != 0 AND result.exit_code != 1`).

### E — Audit event names + code hygiene

- [ ] **AC-17.** **Audit event name contract (frozen).** Snapshot-pinned literal strings: `audit.write.ok`, `audit.write.failed`, `audit.verify.ok`, `audit.verify.mismatch`, `audit.verify.missing_blob`, `audit.verify.yaml_mismatch`. Test `test_audit_event_names_frozen` snapshots a sorted list of all `event=` strings emitted across the surface (captured via `structlog.testing.capture_logs`) against `tests/snapshots/audit_event_names.json`. Phase 11 + Phase 13 consumers subscribe by name; renames require an ADR amendment.
- [ ] **AC-18.** `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/audit.py` and `pytest tests/unit/test_audit_anchors.py` are clean on touched files. `RunRecord.model_validate_json(path.read_text())` round-trips successfully in EVERY test that writes a record (one-line assertion appended).

## Implementation outline

1. **Promote two private helpers to public** (single-source-of-truth chokepoint):
   - `cache/store.py`: `_serialize_output(output)` → `serialize_output(output)` (module-public). Both `CacheStore.put` and `AuditWriter._blob_sha256` import this — kills the phantom-mismatch class.
   - `cache/store.py`: `_latest_record_for(key)` → `CacheStore.get_index_record(key) -> dict | None` (method-public). Verifier uses this for `cache_key → blob_blake3` lookup.

2. **S3-05 amendments (same PR):**
   - `coordinator/coordinator.py`: `Ran(output: SanitizedProbeOutput)` → `Ran(output: SanitizedProbeOutput, key: str)`. Construction sites updated.
   - `_dispatch_one` success branch: `if not sanitized.errors: cache.put(key, sanitized)` — errored outputs not cached.
   - S3-05's tests: update `Ran(out)` → `Ran(out, key)` everywhere; add `test_dispatch_does_not_cache_errored_ran`.

3. **`src/codegenie/audit.py` additions** (do NOT alter the Pydantic models from S2-05):
   ```python
   from codegenie.cache.store import CacheStore, serialize_output
   from codegenie.coordinator.coordinator import CacheHit, GatherResult, Ran, Skipped
   from codegenie.hashing import identity_hash_bytes
   # NO hashlib, NO blake3 imports — enforced by AC-8 grep test.

   def _exit_status_for(execution) -> Literal["ok", "error", "timeout", "skipped"]:
       if isinstance(execution, Skipped):
           return "skipped"
       if isinstance(execution, CacheHit):
           return "ok"
       # Ran
       if not execution.output.errors:
           return "ok"
       if any(e.startswith("timeout:") for e in execution.output.errors):
           return "timeout"
       return "error"

   def _blob_sha256_for(execution) -> str:
       if isinstance(execution, Skipped):
           return ""
       if isinstance(execution, Ran) and execution.output.errors:
           return ""
       # Ran(errors=[]) | CacheHit(output, key)
       return identity_hash_bytes(serialize_output(execution.output))

   def _cache_key_for(execution) -> str:
       if isinstance(execution, Skipped):
           return ""
       return execution.key  # Ran.key (per AC-5) or CacheHit.key

   class AuditWriter:
       def __init__(self, output_dir: Path) -> None: ...
       def record(self, gather_result, *, cli_version, sherpa_commit, tool_versions, yaml_sha256) -> Path: ...

   def verify_runs(runs_dir: Path, cache_dir: Path, yaml_path: Path) -> int: ...
   ```

4. **Atomic-write helper** in `audit.py` (local; do NOT abstract to a shared module in this story — Rule 3). Sequence per AC-3 + AC-4 (collision retry):
   ```python
   def _atomic_write_run_record(path: Path, body_bytes: bytes) -> None:
       tmp = path.with_suffix(path.suffix + ".tmp")
       fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
       try:
           os.write(fd, body_bytes); os.fsync(fd)
       finally:
           os.close(fd)
       os.replace(tmp, path)
       os.chmod(path, 0o600)
   ```

5. **`verify_runs(runs_dir, cache_dir, yaml_path)`** opens a `CacheStore(cache_dir, ttl_hours=...)` (TTL irrelevant — verify never expires), iterates `runs_dir.glob("*.json")` in sorted order, for each: deserialize via `RunRecord.model_validate_json`, walk `record.probes` and check per-record per-AC-11 / AC-12 / AC-14; then check `record.yaml_sha256` per AC-13. Accumulates mismatch count, emits `audit.verify.ok` summary, returns count.

6. **`cli.py` stub:** add `@audit.command("verify")` calling `verify_runs` and translating via `sys.exit(0 if count == 0 else 4)`. S4-02 finalizes the wider CLI tree.

7. Tests in `tests/unit/test_audit_anchors.py`.

## TDD plan — red / green / refactor

Test file path: `tests/unit/test_audit_anchors.py` (Gap-2 anchor). Shared fixtures in `tests/unit/conftest.py`.

### Red — write the failing tests first

```python
"""S3-06 — AuditWriter + verify_runs (Gap 2 closure, ADR-0004)."""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import fields
from pathlib import Path
from unittest import mock

import pytest
import structlog.testing

from codegenie.audit import (
    AuditWriter,
    RunRecord,
    ProbeExecutionRecord,
    _exit_status_for,
    verify_runs,
)
from codegenie.cache.store import CacheStore, serialize_output
from codegenie.coordinator.coordinator import CacheHit, GatherResult, Ran, Skipped
from codegenie.errors import CodegenieError
from codegenie.hashing import identity_hash_bytes
from codegenie.output.sanitizer import SanitizedProbeOutput
from codegenie.probes.base import ProbeOutput

_SHA = "sha256:" + "0" * 64


def _sanitized(schema_slice: dict | None = None, errors: list[str] | None = None) -> SanitizedProbeOutput:
    return SanitizedProbeOutput(
        schema_slice=schema_slice or {"v": 1},
        raw_artifacts=[],
        confidence="high",
        duration_ms=10,
        warnings=[],
        errors=errors or [],
    )


def _gather_result(executions: dict) -> GatherResult:
    outputs = {
        name: exe.output
        for name, exe in executions.items()
        if isinstance(exe, (Ran, CacheHit)) and not (isinstance(exe, Ran) and exe.output.errors)
        # NOTE: outputs dict per S3-05 carries Ran+CacheHit; this fixture excludes errored Ran
        # from outputs to match the coordinator's contract.
    }
    return GatherResult(outputs=outputs, executions=executions)


@pytest.fixture
def writer(tmp_path) -> AuditWriter:
    return AuditWriter(output_dir=tmp_path)


# --- Section A: writer surface + atomic write + permissions ---

def test_record_writes_runs_subdir_at_0700(writer, tmp_path):
    """AC-1: runs/ dir created with mode 0700."""
    result = _gather_result({"p": Ran(output=_sanitized(), key="sha256:" + "a" * 64)})
    path = writer.record(
        result, cli_version="0.1.0", sherpa_commit=None, tool_versions={}, yaml_sha256=_SHA
    )
    runs_dir = tmp_path / "runs"
    assert runs_dir.is_dir()
    assert stat.S_IMODE(runs_dir.stat().st_mode) == 0o700
    assert path.parent == runs_dir


def test_filename_is_filesystem_portable_pattern(writer):
    """AC-2: filename matches the Windows-safe pattern; no colons."""
    result = _gather_result({"p": Ran(output=_sanitized(), key=_SHA)})
    path = writer.record(
        result, cli_version="0.1.0", sherpa_commit=None, tool_versions={}, yaml_sha256=_SHA
    )
    assert ":" not in path.name
    assert re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{8}\.json", path.name)


def test_run_record_file_is_mode_0600_under_loose_umask(monkeypatch, writer):
    """AC-3 + ADR-0011: mode 0600 even when host umask is loose."""
    monkeypatch.setattr(os, "umask", lambda mask: 0)
    os.umask(0o022)  # loose umask defeats os.open's mode arg alone
    result = _gather_result({"p": Ran(output=_sanitized(), key=_SHA)})
    path = writer.record(result, cli_version="0.1.0", sherpa_commit=None, tool_versions={}, yaml_sha256=_SHA)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_record_fsyncs_before_replace(monkeypatch, writer):
    """AC-3: fsync ordered before os.replace (mirror test_output_writer.py:60-71)."""
    real_fsync, real_replace = os.fsync, os.replace
    manager = mock.Mock()
    manager.attach_mock(mock.MagicMock(side_effect=real_fsync), "fsync")
    manager.attach_mock(mock.MagicMock(side_effect=real_replace), "replace")
    monkeypatch.setattr("codegenie.audit.os.fsync", manager.fsync)
    monkeypatch.setattr("codegenie.audit.os.replace", manager.replace)

    result = _gather_result({"p": Ran(output=_sanitized(), key=_SHA)})
    writer.record(result, cli_version="0.1.0", sherpa_commit=None, tool_versions={}, yaml_sha256=_SHA)

    names = [c[0] for c in manager.mock_calls if c[0] in {"fsync", "replace"}]
    assert names == ["fsync", "replace"]


def test_atomic_write_no_partial_file_on_replace_failure(monkeypatch, writer, tmp_path):
    """AC-3: os.replace raising leaves no runs/*.json; .tmp if present is 0600."""
    monkeypatch.setattr("codegenie.audit.os.replace", mock.MagicMock(side_effect=OSError("sim")))
    result = _gather_result({"p": Ran(output=_sanitized(), key=_SHA)})
    with pytest.raises(OSError):
        writer.record(result, cli_version="0.1.0", sherpa_commit=None, tool_versions={}, yaml_sha256=_SHA)
    runs_dir = tmp_path / "runs"
    assert list(runs_dir.glob("*.json")) == []
    for tmp in runs_dir.glob("*.tmp"):
        assert stat.S_IMODE(tmp.stat().st_mode) == 0o600


def test_audit_write_failed_event_on_oserror(monkeypatch, writer):
    """AC-3: structlog event audit.write.failed on OSError mid-write."""
    monkeypatch.setattr("codegenie.audit.os.replace", mock.MagicMock(side_effect=OSError("disk full")))
    result = _gather_result({"p": Ran(output=_sanitized(), key=_SHA)})
    with structlog.testing.capture_logs() as logs:
        with pytest.raises(OSError):
            writer.record(result, cli_version="0.1.0", sherpa_commit=None, tool_versions={}, yaml_sha256=_SHA)
    events = [r["event"] for r in logs]
    assert "audit.write.failed" in events


def test_collision_retry_uses_fresh_suffix(monkeypatch, writer):
    """AC-4: FileExistsError on O_EXCL triggers a fresh token_hex retry."""
    calls = iter(["aaaaaaaa", "aaaaaaaa", "bbbbbbbb"])  # 1st & 2nd collide; 3rd unique
    monkeypatch.setattr("codegenie.audit.secrets.token_hex", lambda n: next(calls))
    result = _gather_result({"p": Ran(output=_sanitized(), key=_SHA)})
    p1 = writer.record(result, cli_version="0.1.0", sherpa_commit=None, tool_versions={}, yaml_sha256=_SHA)
    p2 = writer.record(result, cli_version="0.1.0", sherpa_commit=None, tool_versions={}, yaml_sha256=_SHA)
    assert p1.name.endswith("-aaaaaaaa.json")
    assert p2.name.endswith("-bbbbbbbb.json")


# --- Section B: per-variant anchor population (the Gap-2 contract) ---

@pytest.mark.parametrize(
    "name, execution, expected_status, blob_sha_nonempty, key_nonempty",
    [
        ("p_ok", Ran(output=_sanitized(), key="sha256:" + "a" * 64), "ok", True, True),
        ("p_err", Ran(output=_sanitized(errors=["RuntimeError: boom"]), key="sha256:" + "b" * 64), "error", False, True),
        ("p_to",  Ran(output=_sanitized(errors=["timeout: 30s"]), key="sha256:" + "c" * 64), "timeout", False, True),
        ("p_hit", CacheHit(output=_sanitized(), key="sha256:" + "d" * 64), "ok", True, True),
        ("p_skp", Skipped(reason="applies() returned False"), "skipped", False, False),
    ],
)
def test_anchor_matrix_per_variant(writer, name, execution, expected_status, blob_sha_nonempty, key_nonempty):
    """AC-7: per-variant cache_key + blob_sha256 + exit_status mapping."""
    result = _gather_result({name: execution})
    path = writer.record(result, cli_version="0.1.0", sherpa_commit=None, tool_versions={}, yaml_sha256=_SHA)
    record = RunRecord.model_validate_json(path.read_text())  # AC-18 round-trip
    [probe] = record.probes
    assert probe.exit_status == expected_status, name
    if key_nonempty:
        assert probe.cache_key.startswith("sha256:"), name
    else:
        assert probe.cache_key == "", name
    if blob_sha_nonempty:
        assert probe.blob_sha256.startswith("sha256:"), name
    else:
        assert probe.blob_sha256 == "", name


def test_exit_status_helper_isolated():
    """AC-7: the _exit_status_for helper itself, tested independently."""
    assert _exit_status_for(Skipped(reason="x")) == "skipped"
    assert _exit_status_for(CacheHit(output=_sanitized(), key=_SHA)) == "ok"
    assert _exit_status_for(Ran(output=_sanitized(), key=_SHA)) == "ok"
    assert _exit_status_for(Ran(output=_sanitized(errors=["timeout: 5s"]), key=_SHA)) == "timeout"
    assert _exit_status_for(Ran(output=_sanitized(errors=["ValueError: x"]), key=_SHA)) == "error"


def test_audit_module_has_no_hashlib_or_blake3_imports():
    """AC-8: ADR-0001 chokepoint discipline."""
    source = Path("src/codegenie/audit.py").read_text()
    # Strip docstrings — they may legitimately mention the names.
    code = re.sub(r'"""[\s\S]*?"""', '', source)
    assert "hashlib" not in code, "audit.py must not import hashlib (ADR-0001 chokepoint)"
    assert "blake3" not in code, "audit.py must not import blake3 (ADR-0001 chokepoint)"


def test_blob_sha256_hashes_sanitized_not_raw_output(writer, tmp_path):
    """AC-9: ADR-0004 §Consequences — sanitized bytes are hashed."""
    from codegenie.output.sanitizer import OutputSanitizer
    san = OutputSanitizer()
    raw = ProbeOutput(
        schema_slice={"file": str(tmp_path.resolve() / "foo.py")},
        raw_artifacts=[], confidence="high", duration_ms=1, warnings=[], errors=[],
    )
    sanitized = san.scrub(raw, repo_root=tmp_path.resolve())
    # Sanitized path should be repo-relative ("foo.py") — different bytes than raw.
    raw_bytes = serialize_output(raw)
    san_bytes = serialize_output(sanitized)
    assert raw_bytes != san_bytes
    expected_sha = identity_hash_bytes(san_bytes)
    not_expected = identity_hash_bytes(raw_bytes)

    result = _gather_result({"p": Ran(output=sanitized, key=_SHA)})
    path = writer.record(result, cli_version="0.1.0", sherpa_commit=None, tool_versions={}, yaml_sha256=_SHA)
    record = RunRecord.model_validate_json(path.read_text())
    assert record.probes[0].blob_sha256 == expected_sha
    assert record.probes[0].blob_sha256 != not_expected


def test_sanitized_and_probe_output_fields_match():
    """AC-9 corollary: defeat future field-set drift between the two types."""
    assert {f.name for f in fields(SanitizedProbeOutput)} == {f.name for f in fields(ProbeOutput)}


def test_record_handles_empty_gather_result(writer):
    """Negative-space: zero probes still produces a valid record."""
    result = GatherResult(outputs={}, executions={})
    path = writer.record(result, cli_version="0.1.0", sherpa_commit=None, tool_versions={}, yaml_sha256=_SHA)
    record = RunRecord.model_validate_json(path.read_text())
    assert record.probes == []
    assert record.yaml_sha256 == _SHA


# --- Section C: verify_runs semantics ---

@pytest.fixture
def populated_run(tmp_path, writer):
    """A clean run-record + a cache containing one blob for the Ran probe."""
    cache_dir = tmp_path / "cache"
    cache = CacheStore(cache_dir, ttl_hours=24)
    # Construct sanitized output + insert into cache (mimics the coordinator).
    sanitized = _sanitized()
    key = "sha256:" + "e" * 64
    cache._key_meta[key] = ("p_ok", "1.0.0")  # mimic coordinator's key_for() prelude
    cache.put(key, sanitized)
    # Build a GatherResult + record.
    result = _gather_result({"p_ok": Ran(output=sanitized, key=key)})
    yaml_path = tmp_path / "repo-context.yaml"
    yaml_bytes = b"schema_version: 0.1.0\nprobes:\n  p_ok:\n    v: 1\n"
    yaml_path.write_bytes(yaml_bytes)
    yaml_sha = identity_hash_bytes(yaml_bytes)
    path = writer.record(
        result, cli_version="0.1.0", sherpa_commit=None, tool_versions={}, yaml_sha256=yaml_sha
    )
    return {"runs_dir": path.parent, "cache_dir": cache_dir, "yaml_path": yaml_path,
            "key": key, "blob_blake3": next(iter(cache._key_meta))}


def test_verify_runs_zero_on_clean_run(populated_run):
    """AC-10 + AC-11 + AC-13: zero mismatches on an untampered system."""
    n = verify_runs(populated_run["runs_dir"], populated_run["cache_dir"], populated_run["yaml_path"])
    assert n == 0


def test_verify_runs_is_idempotent_no_side_effects(populated_run):
    """Pure-read function: two calls return zero AND leave files unchanged."""
    args = (populated_run["runs_dir"], populated_run["cache_dir"], populated_run["yaml_path"])
    files = list(populated_run["runs_dir"].iterdir())
    mtimes_before = {f: f.stat().st_mtime for f in files}
    bytes_before = {f: f.read_bytes() for f in files}
    assert verify_runs(*args) == 0
    assert verify_runs(*args) == 0
    for f in files:
        assert f.stat().st_mtime == mtimes_before[f]
        assert f.read_bytes() == bytes_before[f]


def test_verify_runs_detects_byte_level_blob_tamper(populated_run):
    """AC-11: tampering blob bytes (cache index unchanged) is detected by recompute."""
    # Find the blob file via the index (NOT via cache.get).
    index = (populated_run["cache_dir"] / "index.jsonl").read_text().strip().splitlines()
    rec = json.loads(index[-1])
    blob_hex = rec["blob_blake3"].removeprefix("blake3:")
    blob_path = populated_run["cache_dir"] / "blobs" / blob_hex[:2] / f"{blob_hex}.json"
    # Overwrite with valid JSON, different bytes -> different SHA-256.
    os.chmod(blob_path, 0o600)
    blob_path.write_text(json.dumps({
        "schema_slice": {"TAMPERED": True}, "raw_artifacts": [], "confidence": "low",
        "duration_ms": 0, "warnings": [], "errors": [],
    }, sort_keys=True, separators=(",", ":")))
    with structlog.testing.capture_logs() as logs:
        n = verify_runs(populated_run["runs_dir"], populated_run["cache_dir"], populated_run["yaml_path"])
    assert n == 1
    events = [r for r in logs if r["event"] == "audit.verify.mismatch"]
    assert len(events) == 1
    assert events[0]["cache_key"] == populated_run["key"]
    assert events[0]["probe_name"] == "p_ok"


def test_verify_runs_recomputes_not_reads_stored_hash(populated_run):
    """AC-11 mutation-killer: a verifier that READS blob_sha256 from index instead of
    recomputing would survive tamper. Here we tamper ONLY the index's blob_sha256 field,
    leaving the blob bytes intact. The audit record's blob_sha256 was computed at write
    time over the (still-intact) blob bytes; a correct verifier recomputes from bytes and
    reports 0 mismatches. A mutant reading from index reports 1 (false positive)."""
    index_path = populated_run["cache_dir"] / "index.jsonl"
    lines = index_path.read_text().splitlines()
    rec = json.loads(lines[-1])
    rec["blob_sha256"] = "sha256:" + "f" * 64  # LIE
    lines[-1] = json.dumps(rec, sort_keys=True, separators=(",", ":"))
    os.chmod(index_path, 0o600)
    index_path.write_text("\n".join(lines) + "\n")
    n = verify_runs(populated_run["runs_dir"], populated_run["cache_dir"], populated_run["yaml_path"])
    assert n == 0  # The blob bytes are intact; recompute matches audit record.


def test_verify_runs_missing_blob_logs_and_continues(populated_run):
    """AC-12: missing blob = mismatch + audit.verify.missing_blob event + walk continues."""
    index_path = populated_run["cache_dir"] / "index.jsonl"
    rec = json.loads(index_path.read_text().strip().splitlines()[-1])
    blob_hex = rec["blob_blake3"].removeprefix("blake3:")
    blob_path = populated_run["cache_dir"] / "blobs" / blob_hex[:2] / f"{blob_hex}.json"
    blob_path.unlink()
    with structlog.testing.capture_logs() as logs:
        n = verify_runs(populated_run["runs_dir"], populated_run["cache_dir"], populated_run["yaml_path"])
    assert n == 1
    assert any(r["event"] == "audit.verify.missing_blob" for r in logs)


def test_verify_runs_detects_yaml_tamper(populated_run):
    """AC-13: yaml_sha256 anchor re-verification (closes exit criterion #12)."""
    yaml_path = populated_run["yaml_path"]
    os.chmod(yaml_path, 0o600)
    yaml_path.write_bytes(yaml_path.read_bytes() + b"\n# tamper\n")
    with structlog.testing.capture_logs() as logs:
        n = verify_runs(populated_run["runs_dir"], populated_run["cache_dir"], yaml_path)
    assert n >= 1
    assert any(r["event"] == "audit.verify.yaml_mismatch" for r in logs)


def test_verify_runs_skips_empty_blob_sha_records(writer, tmp_path):
    """AC-14: Skipped + errored-Ran + timeout-Ran records have blob_sha256='' and
    are NOT walked for blob verification. No missing_blob events fire for them."""
    result = _gather_result({
        "p_skp": Skipped(reason="x"),
        "p_err": Ran(output=_sanitized(errors=["ValueError"]), key="sha256:" + "1" * 64),
    })
    yaml_bytes = b"empty\n"
    yaml_path = tmp_path / "y.yaml"
    yaml_path.write_bytes(yaml_bytes)
    path = writer.record(result, cli_version="0.1.0", sherpa_commit=None, tool_versions={}, yaml_sha256=identity_hash_bytes(yaml_bytes))
    cache_dir = tmp_path / "cache"; cache_dir.mkdir(); os.chmod(cache_dir, 0o700)
    (cache_dir / "index.jsonl").touch(mode=0o600)
    with structlog.testing.capture_logs() as logs:
        n = verify_runs(path.parent, cache_dir, yaml_path)
    assert not any(r["event"] == "audit.verify.missing_blob" for r in logs)
    assert n == 0


def test_verify_runs_emits_summary_event(populated_run):
    """AC-15: audit.verify.ok summary event emitted exactly once."""
    with structlog.testing.capture_logs() as logs:
        verify_runs(populated_run["runs_dir"], populated_run["cache_dir"], populated_run["yaml_path"])
    summary = [r for r in logs if r["event"] == "audit.verify.ok"]
    assert len(summary) == 1
    assert "mismatch_count" in summary[0]


# --- Section D: CLI subcommand ---

def test_cli_audit_verify_exit_codes(populated_run, monkeypatch):
    """AC-16: clean → exit 0; tampered → exit 4 (slot per arch §CLI exit codes)."""
    from click.testing import CliRunner
    from codegenie.cli import cli

    runner = CliRunner()
    # Clean
    r_clean = runner.invoke(cli, [
        "audit", "verify",
        "--runs-dir", str(populated_run["runs_dir"]),
        "--cache-dir", str(populated_run["cache_dir"]),
        "--yaml-path", str(populated_run["yaml_path"]),
    ])
    assert r_clean.exit_code == 0

    # Tamper YAML
    yaml_path = populated_run["yaml_path"]
    os.chmod(yaml_path, 0o600)
    yaml_path.write_bytes(yaml_path.read_bytes() + b"# tamper\n")
    r_tamp = runner.invoke(cli, [
        "audit", "verify",
        "--runs-dir", str(populated_run["runs_dir"]),
        "--cache-dir", str(populated_run["cache_dir"]),
        "--yaml-path", str(populated_run["yaml_path"]),
    ])
    assert r_tamp.exit_code != 0
    assert r_tamp.exit_code != 1  # distinct from default-handler unhandled-exception slot
    assert r_tamp.exit_code == 4


# --- Section E: event-name contract ---

def test_audit_event_names_frozen(populated_run, writer, tmp_path):
    """AC-17: literal event-name set is frozen (Phase 11 + Phase 13 subscribe by name)."""
    # Trigger write + verify happy + verify mismatch paths.
    yaml_path = populated_run["yaml_path"]
    os.chmod(yaml_path, 0o600); yaml_path.write_bytes(yaml_path.read_bytes() + b"tamper\n")
    with structlog.testing.capture_logs() as logs:
        try:
            verify_runs(populated_run["runs_dir"], populated_run["cache_dir"], yaml_path)
        except Exception:
            pass
    names = sorted({r["event"] for r in logs if r["event"].startswith("audit.")})
    expected = {"audit.verify.ok", "audit.verify.yaml_mismatch"}
    assert expected <= set(names)
    # Confirm no unexpected audit.* names sneaked in.
    allowed = {"audit.write.ok", "audit.write.failed", "audit.verify.ok",
               "audit.verify.mismatch", "audit.verify.missing_blob",
               "audit.verify.yaml_mismatch"}
    assert set(names) <= allowed
```

Run; confirm `ImportError` / `AttributeError` / `AssertionError`. Commit as the red marker.

### Green — make it pass

1. **Promote `cache.store._serialize_output` to public `serialize_output`** and `_latest_record_for` to public `CacheStore.get_index_record`. Wide signature is `output: ProbeOutput | SanitizedProbeOutput`; both classes pass duck-typing on the 6-field shape.
2. **Ship the two S3-05 amendments** (AC-5 + AC-6) in the same PR: extend `Ran` to `Ran(output, key)`; gate `cache.put` on `not sanitized.errors`.
3. **Implement `AuditWriter`** per the outline. Construct `ProbeExecutionRecord`s via the `_exit_status_for` / `_blob_sha256_for` / `_cache_key_for` helpers (kept private — single dispatch per variant). Atomic write with O_EXCL, fsync, replace, chmod. Collision-retry up to 3.
4. **Implement `verify_runs`** per the outline. For every probe with `blob_sha256 != ""`: index lookup via `CacheStore.get_index_record`, read raw bytes, recompute via `identity_hash_bytes`. Yaml anchor recomputed once per run-record. Summary `audit.verify.ok` event with the count.
5. **`cli.py` stub:** add the `audit verify` click command translating to exit `0`/`4`.

### Refactor — clean up

- Type hints throughout; `mypy --strict src/codegenie/audit.py` clean.
- Docstrings on `AuditWriter.record`, `verify_runs`, the three helper functions citing the ACs they implement.
- Module docstring on `audit.py` notes the chokepoint discipline (no `hashlib`, no `blake3`) and the canonicalization-shared-with-cache invariant.
- Confirm `mypy --strict` passes on the new shared `serialize_output` signature in `cache/store.py`.
- Confirm `import codegenie.audit` does not pull `blake3` into `sys.modules` (chokepoint discipline corollary — audit only does SHA-256).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/audit.py` | Add `AuditWriter` class + `verify_runs` + the three `_*_for` helpers + `_atomic_write_run_record` helper. Do NOT alter the Pydantic models from S2-05 (they already have `cache_key`, `blob_sha256`). |
| `src/codegenie/cache/store.py` | Promote `_serialize_output` → `serialize_output` and `_latest_record_for` → `get_index_record`. Both are signature-stable; old call sites compile unchanged. |
| `src/codegenie/coordinator/coordinator.py` | **S3-05 amendment (AC-5 + AC-6):** `Ran(output: SanitizedProbeOutput, key: str)`; `_dispatch_one` gates `cache.put` on `not sanitized.errors`. Same PR. |
| `src/codegenie/cli.py` | Add `audit verify` click subcommand stub (S4-02 may overwrite/extend; this is the seed). Translates `verify_runs` return to exit `0`/`4`. |
| `tests/unit/test_audit_anchors.py` | New — all tests in the Red section above. |
| `tests/unit/test_coordinator.py` | **S3-05 amendment:** update construction sites `Ran(out)` → `Ran(out, key)`; add `test_dispatch_does_not_cache_errored_ran`. |
| `tests/snapshots/audit_event_names.json` | New — frozen list of allowed audit.* event names. |

## Out of scope

- **`yaml_sha256` POPULATION on `RunRecord`** — already part of `RunRecord` per S2-05's models; this story populates it from the YAML writer's output (S3-03 produces the YAML; AuditWriter hashes it). The new contract here is the **verification** side (AC-13).
- **Including the contents of `~/.codegenie/.tool-cache.json`** in the run-record — explicitly rejected per `phase-arch-design.md §Open questions` #4. `tool_versions` only.
- **HMAC signing of the run-record** — deferred to Phase 14 with the webhook listener.
- **Phase 11 PR-provenance bundle layout** — Phase 11's job; this story makes `blob_sha256` available for that consumer.
- **Phase 13 cost-ledger writer** — Phase 13's job; this story makes `cache_key` available for that consumer.
- **`os_kernel_sha` population details** — `RunRecord.os_kernel_sha` already exists per `audit.py:82`; populate via `identity_hash_bytes(platform.platform().encode())` (NOT `platform.uname().node`, which contains the hostname). The arch §Component design line 590 `os_kernel` spelling is a doc-side inconsistency (follow-up #3).
- **Generalized atomic-write helper module** — duplicate the small `_atomic_write_run_record` locally. Extraction is a Phase-1 cleanup PR if a third writer needs it. Rule 3.

## Notes for the implementer

- **This story closes Gap 2 from `../phase-arch-design.md §Gap analysis`.** The dual-anchor pattern is what makes the audit record useful to **both** Phase 11 (evidence integrity) **and** Phase 13 (cost attribution). Per `phase-arch-design.md §Implementation-level risks` #2: write the Gap-2 tests **first**.
- **The sanitized blob is what's hashed** (ADR-0004 §Consequences). `OutputSanitizer.scrub` runs in the coordinator before `cache.put`; `SanitizedProbeOutput` is the type that flows. The audit writer hashes the serialization of `SanitizedProbeOutput`, NOT of the raw `ProbeOutput`. AC-9 pins this.
- **Use `hashing.identity_hash_bytes(blob_bytes)`, NOT `hashing.identity_hash(*parts)`.** They produce different SHA-256 values; only the former matches the cache's stored `blob_sha256`. AC-8 grep test enforces it.
- **Read RAW bytes from the cache blob path in `verify_runs`.** NOT through `CacheStore.get` — that returns a re-deserialized `ProbeOutput` and re-serializing would mask byte-level tampering. The verifier is a tamper witness; it must operate on the bytes the disk actually holds.
- **The cache index lookup** for `cache_key → blob_blake3 → blob_path` uses `CacheStore.get_index_record(cache_key)` (promoted from `_latest_record_for`). Last-write-wins matches the cache's get semantics.
- Per ADR-0011, mode `0600` is re-applied via `os.chmod` after atomic write; mode `0700` for the `runs/` directory after `mkdir`. Verify with the umask-resistant test (AC-3).
- `secrets.token_hex(4)` is **random**, not content-derived. It's only the filename suffix; the artifact's identity is the `yaml_sha256` field inside.
- **S3-05 amendments ship in the same PR** per Rule 7. If the implementer wants to land the AuditWriter without touching S3-05, the only option would be re-deriving keys at audit-write time — explicitly forbidden by AC-5. Don't average; ship the amendments.
- **Five doc-cleanup follow-ups are filed** in the Validation notes; do NOT touch them in this story's PR (Rule 3 — surgical changes).
