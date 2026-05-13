# Validation report — S3-06 audit writer + `audit verify`

**Validated:** 2026-05-13 by `phase-story-validator` v1
**Story file:** `../S3-06-audit-writer-verify.md`
**Verdict:** **HARDENED**

## Summary

Three parallel critics returned **50 findings** (15 Coverage + 20 Test-Quality + 15 Consistency; 15 block, 29 harden, 6 nit; 0 `NEEDS RESEARCH` — every gap was answerable from in-repo docs, S3-05's hardened story, and the existing `cache/store.py` + `hashing.py` + `audit.py` code). Stage 3 (researcher) was skipped.

The story has the **right Goal** and the right cross-phase framing (Gap 2 closure for ADR-0004), but pre-hardening it had three categories of structural defects that would have silently corrupted the audit anchor in implementation:

1. **Wrong `hashing` chokepoint function named.** Implementation outline #2 said `_blob_sha256` routes through `hashing.identity_hash` — but that function takes variadic strings with arity-byte prefixing (`hashing.py:67-79`). The cache stores `blob_sha256` via `identity_hash_bytes(blob_bytes)` (`cache/store.py:269`). Using `identity_hash` for the audit blob hash produces a hash that NEVER equals the cache's stored hash — every `audit verify` call would report universal mismatches.
2. **`cache_key → blob path` mapping understated.** Cache blobs live at `cache/blobs/<shard>/<blake3-hex>.json` (BLAKE3, not the SHA-256 `cache_key`). The verifier must walk `index.jsonl` to map `cache_key → blob_blake3` first. Story said "reads the cache blob at the claimed `cache_key`" — which has no direct mapping.
3. **Cross-story shape mismatches with the just-hardened S3-05.** S3-05 (commit `8129392`) ships `Ran(output: SanitizedProbeOutput)` and `Skipped(reason: str)` — no `key` field on either. S3-06 AC-3 assumed both variants carried `cache_key`, and an implementer note buried "may need to file a small change in S3-05" — exactly the "don't average two patterns" smell CLAUDE.md Rule 7 names.

All three are fixed below; the fix to (3) ships a **coordinated S3-05 amendment in the same PR** per Rule 7 ("surface conflicts, don't average them").

## Material changes applied (16)

### Type-flow / cross-story contract (blockers)

- **Pinned `Ran(output, key)` extension.** S3-05's `Ran(output: SanitizedProbeOutput)` is extended *in this story's diff* to `Ran(output: SanitizedProbeOutput, key: str)`. `AuditWriter` reads `cache_key` from the field. **Re-derivation via `cache.key_for(...)` at audit-write time is explicitly forbidden** — that would record what-we-would-ask-for-now, not what-the-coordinator-actually-asked. S3-05's existing tests and arch §Data model lines 661-680 are updated in the same PR; the rule of Rule-7 ships in this story's diff. (Coverage F2, Test-Quality F8, Consistency F1 — three critics, one fix.)
- **Pinned `Skipped(reason: str)` → `cache_key=""` sentinel.** The "would-be key (computed at dispatch time)" phrasing in ADR-0004 §Consequences is a pre-S3-05 artifact: S3-05 pins `applies() → key_for → cache.get` ordering, so on `applies()=False` the coordinator short-circuits to `Skipped` *before* `key_for` runs. We commit to `Skipped.cache_key = ""` + `Skipped.blob_sha256 = ""` + `exit_status="skipped"`. ADR-0004 amendment is filed as a follow-up. Phase 13 cost-ledger semantics: skipped probes consume zero cost; no attribution anchor needed. (Coverage F3, Test-Quality F8, Consistency F2.)
- **Pinned `_exit_status_for(execution) -> Literal["ok","error","timeout","skipped"]` mapping helper.** Centralized in `audit.py`:
  - `Skipped` → `"skipped"`
  - `CacheHit` → `"ok"` (a replay of a previously-successful blob)
  - `Ran(output)` with `output.errors == []` → `"ok"`
  - `Ran(output)` with any error string starting with `"timeout:"` → `"timeout"` (the S3-05 AC-10 prefix)
  - `Ran(output)` with non-empty errors and no `"timeout:"` prefix → `"error"`
  Parametrized test asserts all four mappings. Closes the "always-`ok`" mutant. (Coverage F4, Consistency F9.)
- **Pinned errored-`Ran` × cache + audit interaction.** A `Ran(output)` with `output.errors != []` is **not** stored in the cache (errors are not replayable). `AuditWriter` records `cache_key` (from `Ran.key`) and **sets `blob_sha256 = ""` sentinel** (parallels `Skipped`). `audit verify` skips blob recomputation for any record with an empty `blob_sha256`. This resolves the F9-undefined-state: the audit anchor still attributes cost to a `cache_key`, but doesn't promise a blob. Coordinator must `if not ran.output.errors: cache.put(key, sanitized)` — small S3-05 amendment shipped in same PR. (Coverage F9.)

### Hashing chokepoint + blob path

- **Pinned `hashing.identity_hash_bytes` (not `identity_hash`).** The story now names `identity_hash_bytes(blob_bytes)` everywhere — the function with raw-bytes semantics, matching `cache/store.py:269`. ADR-0001 §Decision chokepoint discipline is enforced via a grep test: `'hashlib' not in src/codegenie/audit.py` (modulo docstring mentions) AND `'blake3' not in src/codegenie/audit.py`. (Test-Quality F2, Consistency F6.)
- **Pinned the `cache_key → blob bytes` resolution path.** Verifier walks `<cache_dir>/index.jsonl` for the **latest** record matching `cache_key` (last-write-wins, mirroring `_latest_record_for`), reads the `blob_blake3` field, and reads raw bytes from `<cache_dir>/blobs/<shard>/<blob_blake3-hex>.json` directly via `Path.read_bytes()`. **NOT through `CacheStore.get`** — `get` returns a deserialized `ProbeOutput`, and re-serialization would mask byte-level tampering. The story exposes `CacheStore.get_index_record(cache_key) -> dict | None` (promotes `_latest_record_for` to public) so the verifier doesn't duplicate the index walk. (Test-Quality F3, Consistency F13.)
- **Pinned the shared canonicalization helper.** A new `cache.store._serialize_output(output: ProbeOutput | SanitizedProbeOutput) -> bytes` (lifted from the existing private function, signature widened to a structural protocol on the 6 fields). Both `cache.put` and `AuditWriter._blob_sha256` import it — single source of truth for `sort_keys=True, separators=(",", ":")` canonicalization. Test pins `set(fields(SanitizedProbeOutput)) == set(fields(ProbeOutput))` to defeat future drift. Closes the "phantom mismatch" risk the Refactor checklist named but no AC enforced. (Consistency F7, F8; Test-Quality F16.)

### Verify-path observability

- **Added AC-7 yaml-anchor recomputation.** Exit criterion #12 (`final-design.md §11`) and `High-level-impl.md:145` are explicit: `audit verify` recomputes `yaml_sha256` from `.codegenie/context/repo-context.yaml` and reports mismatches. Story pre-hardening only verified per-probe `blob_sha256`. New AC + new test `test_audit_verify_detects_yaml_tamper`. (Coverage F1, Consistency F4.)
- **Pinned audit event names contract.** `audit.write.ok`, `audit.write.failed`, `audit.verify.ok` (summary), `audit.verify.mismatch` (per-mismatch), `audit.verify.missing_blob`, `audit.verify.yaml_mismatch`. These are a contract surface distinct from the probe-lifecycle events at `phase-arch-design.md:755` — Phase 11 + Phase 13 consumers subscribe by name. A test snapshots the literal event names (frozen). (Coverage F6, Test-Quality F13, Consistency F10.)
- **Pinned missing-blob handling.** `verify_runs` over a `cache_key` whose blob is gone (cache GC'd, `cache.blob.invalid` deleted) counts as a mismatch (1 to the count), emits `audit.verify.missing_blob`, and continues the walk. No `FileNotFoundError` propagates. Red test `test_audit_verify_handles_gc_blob`. (Coverage F7, Test-Quality F17.)

### Atomic write + permissions hardening

- **Pinned `runs/` directory mode `0700`.** AC-1 was silent on the parent directory. Now: `AuditWriter` ensures `<output_dir>/runs/` exists at `0700` via `os.chmod` post-`mkdir`, mirroring `cache/store.py:_ensure_dir`. (Consistency F5.)
- **Made the mode-bit test umask-resistant.** Test sets `os.umask(0o022)` before the write — proves the chmod call is load-bearing, not an accident of the dev's umask. Mirrors `test_output_writer.py:47-56`. (Test-Quality F10.)
- **Pinned atomic-write fsync ordering.** Added a `test_audit_write_fsyncs_before_replace` test using `Mock.attach_mock` (precedent: `test_output_writer.py:60-71`) — kills the "dropped fsync" mutant. (Test-Quality F13.)
- **Pinned the `audit.write.failed` event on OSError.** A `test_audit_write_failed_event_on_oserror` test using `structlog.testing.capture_logs` (NOT `caplog` — S3-05 Validation note precedent: structlog's `WriteLoggerFactory` doesn't route through stdlib logging). (Test-Quality F13.)

### Filename format + portability + collision

- **Pinned the filename format.** `runs/{YYYY}{MM}{DD}T{HHMMSS}Z-{short}.json` via `datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')` + `secrets.token_hex(4)`. Windows-safe (no `:`). Test asserts `re.fullmatch(r'\d{8}T\d{6}Z-[0-9a-f]{8}\.json', path.name)`. The `<short-hash>` misnomer at `phase-arch-design.md:599` is flagged for follow-up arch cleanup (the canonical phrasing is at line 758 + `final-design.md:307`). (Coverage F5, Test-Quality F9, Consistency F3.)
- **Pinned collision retry contract.** Two `record()` calls in the same wall-clock second collide on `<utc-iso>` with probability ~1/65k on the random suffix. Writer uses `os.open(<final_path>, O_CREAT|O_EXCL|O_WRONLY, 0o600)` for the staging `.tmp` then `os.replace`; on `FileExistsError` retries with a fresh `secrets.token_hex(4)` up to 3 times; persistent collision raises `CodegenieError('audit.record.collision')`. Test monkeypatches `secrets.token_hex` to force a collision. Phase 14 webhook fan-out depends on this. (Coverage F14, Test-Quality F14.)

### Output path + per-variant + empty-input

- **Pinned `<output_dir> = .codegenie/context/`.** The `runs/` directory lives at `.codegenie/context/runs/` per `High-level-impl.md:251` — the canonical reference. `final-design.md:65,461`'s ambiguous ASCII tree is flagged as docs cleanup. Test asserts the resolved path contains `/context/runs/`. (Consistency F14.)
- **Parametrized the anchor-population test over four variants.** `[Ran-ok, Ran-error, CacheHit, Skipped]` — bundles in the original test hid mutants. Test asserts each variant's `cache_key`/`blob_sha256`/`exit_status` combo. (Test-Quality F7.)
- **Added empty-`GatherResult` test.** Goal: zero probes still produces a valid run-record (`probes: []`, valid `yaml_sha256` over the empty-envelope YAML); `verify_runs` returns 0. Closes the "first-probe crash" mutant. (Coverage F10, Test-Quality F12.)
- **Added Pydantic round-trip assertion** in every `record(...)` test: `RunRecord.model_validate_json(path.read_text())`. One-line addition; defeats the "wrote bytes but they don't conform" mutant. (Test-Quality F20.)
- **Added idempotence test.** `verify_runs` is pure-read; running it twice on the same clean state returns `(0, 0)` and leaves file mtimes + bytes unchanged. (Test-Quality F6.)
- **Added sanitized-vs-raw blob test.** A `ProbeOutput` with absolute-path in `schema_slice` flows through `OutputSanitizer.scrub`; the audit record's `blob_sha256` matches the *sanitized* serialization, NOT the *raw* `ProbeOutput`. Closes the ADR-0004-violation mutant. (Test-Quality F15.)
- **Rewrote every TDD test with concrete, runnable Python.** No more `...` placeholders — the same antipattern S3-02/03/04 burned and S3-05 explicitly killed in its Validation notes. Defined `path` (was undefined in the first test), pinned imports, pinned fixtures. (Test-Quality F1.)

## Conflict resolutions (Rule 7)

Two cross-story conflicts surfaced; both resolved by **amending the upstream contract in the same PR** rather than averaging:

1. **S3-05 `Ran(output)` → `Ran(output, key)`** — a 2-line change to `coordinator.py`'s dataclass, an updated arch §Data model snippet, and S3-05's test updates. Ships in the S3-06 PR with a `[breaking]` flag on the line surfacing the S3-05 amendment.
2. **S3-05 coordinator must not `cache.put` errored outputs** — a 1-line conditional in `_dispatch_one`'s success branch. S3-05's tests get a new `test_dispatch_does_not_cache_errored_ran` assertion. Same PR.

Both are surgical (Rule 3); neither touches behavior unrelated to the audit-anchor contract. Per Rule 12 (fail loud), the story now states these S3-05 amendments **as ACs**, not as "may need to file" notes.

## Follow-ups filed (separate PRs)

1. **Amend ADR-0004 §Consequences** to drop "would-be key" for `Skipped` and replace with empty-string sentinel rule.
2. **Amend `phase-arch-design.md §Component design / Audit writer` line 599** from `<short-hash>` to `<short>` to match line 758 + `final-design.md:307`.
3. **Amend arch §Component design / Audit writer line 590** from `os_kernel` to `os_kernel_sha` to match §Data model line 722 + `audit.py:82`.
4. **Amend arch §Data model lines 661-680** to declare `Ran(output: SanitizedProbeOutput, key: str)` per the S3-05 amendment shipped in this story.
5. **Amend `final-design.md:65,461`'s ASCII tree** to show `.codegenie/context/runs/` (currently shows `runs/` ambiguously).

## CLI exit-code resolution

AC-5's "non-zero (typically 1 or a dedicated code)" was a Vague-qualitative smell — and exit code 1 collides with arch §Component design line 420's "unhandled-exception via default click handler" slot. Pinned: `verify_runs` returns the integer mismatch count; the CLI stub returns `0` if zero, **`4`** (the currently-reserved slot in `phase-arch-design.md:420`) if non-zero. S4-02 may re-number; this story OWNS the slot rather than deferring to a not-yet-shipped table. Test asserts `exit != 0 AND != 1` on a tampered run. (Coverage F13, Consistency F11.)

## Final verdict

**HARDENED.** The story now has:

- 18 ACs (was 6), grouped A–E by Concern, every AC individually verifiable and traceable to Goal + an ADR / arch line / cross-story contract;
- 14 runnable TDD tests (was 7, all with `...` placeholders), each parametrized or paired with a mutation-killer counterpart;
- An explicit S3-05 amendment surface (Rule 7);
- Three contract-naming follow-ups filed against arch/ADR docs (separate PRs);
- A single-source-of-truth canonicalization helper shared with the cache layer.

Ready for `phase-story-executor`.
