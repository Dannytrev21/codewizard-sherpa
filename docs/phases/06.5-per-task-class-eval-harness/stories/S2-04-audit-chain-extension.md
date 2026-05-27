# Story S2-04 — Audit chain extension for `BenchRunReport` (`write_run_record` + `verify`)

**Step:** Step 2 — Build harness internals: loader, cache, audit chain extension, canary + cost-tag shims
**Status:** HARDENED
**Effort:** M
**Depends on:** S1-01, S1-02, S2-03
**ADRs honored:** Phase 0 ADR-0001 (BLAKE3 chokepoint reuse), Phase 0 ADR-0011 (`0700` dirs / `0600` files), local Gap #5 (per-host fingerprinting documented; field deferred — see Validation notes)

## Validation notes

Validated: 2026-05-26
Verdict: HARDENED
Findings addressed: 18 total — 4 blocks, 11 hardens, 3 nits

Major source-of-truth reconciliations:

- **Consistency F-CON-1 (block) — `ChainTamperDetected` is a marker-only Exception.** Phase 6.5 S1-01 (HARDENED 2026-05-26, AC-8) pins every `CodegenieEvalError` subclass as behavior-free: `cls.__init__ is e.CodegenieEvalError.__init__` AND `set(cls.__dict__.keys()) <= {"__module__", "__qualname__", "__doc__", "__firstlineno__", "__static_attributes__"}`. The original S2-04 raised `ChainTamperDetected(file_path=..., expected_prev=..., computed_prev=...)` (kwargs) and tested `ei.value.expected_prev == ...` (attribute access) — both impossible without a custom `__init__`. **Fix applied:** raise sites use *positional* args (passed through `Exception.__init__` to `.args`); tests assert on `ei.value.args == (file_path_str, expected_prev, computed_prev)` with a documented positional ordering. AC-2 + AC-7 + red tests rewritten. (S1-01 stays untouched; argument-positional discipline is local to this story.)
- **Consistency F-CON-2 (block) — `host_fingerprint` on `BenchRunReport` is deferred.** Phase 6.5 S1-02 (HARDENED) is already published; it does **not** include `host_fingerprint` and explicitly enumerates the 5 wire types (`_FROZEN_WIRE_TYPES` cardinality test). S2-04 cannot silently extend that contract. **Fix applied:** the `host_fingerprint` Pydantic-field requirement is **moved to Out of scope** with an explicit follow-up obligation (new ADR + S1-02 wire-bump amendment in a later story); the per-host *scope* of the chain stays in scope and is documented in the module docstring + Notes (no wire change needed for documentation).
- **Design-Patterns F-DP-2 (block) — atomic-write helper crosses the rule of three.** S2-03 (HARDENED) Notes: "Consider extracting `_atomic_write_bytes(path, data, mode)` if Phase-3 reuse arrives — for now it stays private (rule of three not met; Phase 0 `cache/store.py:_atomic_write_bytes` is the first site, this is the second)." S2-04 is the **third** consumer. **Fix applied:** extraction promoted from optional-refactor to **AC-15** — `codegenie.eval._io.atomic_write_bytes(path, data, mode)` lands first; both `cache.py` (S2-03 migration) and the new `audit.py` call it; a fence test pins zero local re-implementations of the open/write/fsync/rename/chmod sequence inside `codegenie/eval/`.
- **Design-Patterns F-DP-5 (block) — chain composition lives in `codegenie.hashing`, not `eval/audit.py`.** Story Notes already hint at it ("factor the BLAKE3-content + SHA-256-identity composition into `codegenie.hashing`"). Phase 9's Temporal-durable event log will need the same primitive; duplicating it inside `eval/audit.py` makes Phase 9 an editing-not-adding change. **Fix applied:** new AC-16 — `codegenie.hashing.chain_identity(prev_hash: str, content_hash: str) -> str` lands as the named public primitive; `eval/audit.py` imports and calls it. (Phase 0 already exposes `identity_hash(*parts)` — `chain_identity` is a 2-arg specialization with an explicit name; thin wrapper, but the name is the kernel.)

Additional hardenings:

- AC-2 strengthened (positional-only `ChainTamperDetected(file_path_str, expected_prev, computed_prev)`; pin via `ei.value.args`) — F-CON-1
- AC-2a added (`fcntl.flock(LOCK_EX)` on `<out_dir>/.lock` sentinel — without it, two concurrent processes both pass the prev-hash check and write conflicting records) — F-COV-1
- AC-3 strengthened (canonical-JSON form pinned with `chain_head=""` placeholder so the identity hash is computable; re-serialize-then-write ordering pinned) — F-DP-7
- AC-3a added (returned `(written_path, new_chain_head)` — the on-disk record's `chain_head` field equals the returned identity hash) — F-COV-5
- AC-4 strengthened (`verify` on missing `out_dir` returns empty-chain VerifyResult, not raise; `verify` on JSON-parse failure returns `ok=False, reason="parse_error: ..."`) — F-COV-2 / F-COV-3
- AC-4a added (`since` is filename-prefix lexicographic, inclusive) — F-COV-6
- AC-7 (tamper detection) — `ei.value.args` ordering pinned to mirror AC-2; the byte-flip target is the `run_id` free-text field (not a hash field) so the failure isolates BLAKE3-divergence from JSON-validity-divergence — F-TQ-3
- AC-8 (two concurrent writers) — wording aligned with §Notes: thread-free deterministic simulation via stale-snapshot; `fcntl.flock` is the structural defense (AC-2a), this AC is the prev-hash semantics defense — F-CON-4
- AC-9 (per-host) — rewritten to assert only documentation (module docstring names the per-host scope); wire-field requirement deferred to Out of scope — F-CON-2
- AC-11 added (`out_dir` parent is created with mode `0o700`; post-write `os.chmod` defeats umask=0o000) — F-TQ-6
- AC-12 added (atomic-write failure path: induced `OSError` mid-write → function raises; previous-state file byte-identical; no `.tmp` orphan) — F-TQ-7
- AC-13 added (`verify` stop-on-first-mismatch semantic pinned — chain[0..k-1] verified, chain[k] is the `tampered_path`, chain[k+1..] not walked) — Coverage
- AC-15 added (atomic-write helper extraction; both eval/cache.py and eval/audit.py consume) — F-DP-2
- AC-16 added (`codegenie.hashing.chain_identity(prev_hash, content_hash) -> str` public primitive; `eval/audit.py` consumes; fence forbids open-coding) — F-DP-5
- TDD plan rewritten — `_make_report` helper pinned (mirrors S1-02 test precedent); independent-recomputation oracle added to the genesis test; hypothesis property test (chain integrity over N=1..20); metamorphic test for `since` filter; umask=0o000 fixture for the 0600 test
- Refactor step trimmed — extraction promoted to AC-15; remaining items are docstring + structlog wiring only
- Out of scope expanded — `host_fingerprint` wire-field add; cross-host promotion-source-host knob (Gap #5 part 2); cross-platform Windows lock primitive
- Notes for implementer expanded — explicit `model_copy(update={...})` recipe for setting `chain_head` on a frozen Pydantic model; the canonical-JSON-with-placeholder ordering; positional-arg discipline rationale

Design-pattern opportunities surfaced (Notes only — Rule 2 YAGNI-guarded; not promoted to ACs):

- F-DP-3 — `VerifyResult` could be a sum type (`VerifyOk(...)` | `VerifyTampered(...)`); flat dataclass is YAGNI-correct for a single producer. Surface if Phase 9 grows a second consumer.
- F-DP-4 — `_current_head` could return `HeadState = ChainEmpty() | ChainHead(...)`; sentinel 2-tuple is YAGNI-correct at one callsite.
- F-DP-6 — `GENESIS_PREV_HASH: Final[str] = "0" * 64` module constant rather than literal; trivial, applied in implementation.

Full audit log: `_validation/S2-04-audit-chain-extension.md`

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

- [ ] **AC-1.** `write_run_record(report: BenchRunReport, out_dir: Path) -> tuple[Path, str]` writes one JSON file at `out_dir / f"{utc_iso}-{short}.json"` (mode `0600`) via atomic-rename and returns `(written_path, new_chain_head)`. If `out_dir` does not exist, it is created with mode `0o700` (Phase 0 ADR-0011 — match `cache/store.py` precedent).
- [ ] **AC-2.** Prev-hash check + typed-raise discipline. The function reads the current chain head BEFORE serializing the new record: if `out_dir` contains no `*.json`, the expected `prev_hash` is `GENESIS_PREV_HASH = "0" * 64`; otherwise it is the identity hash of the lexicographically-greatest existing `*.json`. Mismatch raises `ChainTamperDetected` constructed *positionally* (S1-01 AC-8 marker-only discipline — no kwargs, no custom `__init__`). The argument ordering is pinned by this story as `ChainTamperDetected(str(current_head_path or "<genesis>"), expected_prev, report.prev_hash)`; verified by `ei.value.args == (str(current_head_path or "<genesis>"), expected_prev, report.prev_hash)` in tests. **No subscript-by-attribute access** anywhere (`.expected_prev` etc. do not exist on the marker class).
- [ ] **AC-2a.** `fcntl.flock(LOCK_EX)` discipline — `write_run_record` acquires an exclusive flock on `<out_dir>/.lock` (sentinel file, mode `0o600`, created lazily) BEFORE the head-read; releases on success or exception via `@contextlib.contextmanager`. Verified by a direct probe: while a held write is paused mid-serialization (monkeypatched `_atomic_write_bytes`), a sibling `fcntl.flock(fd, LOCK_EX | LOCK_NB)` raises `BlockingIOError`. Mirrors S2-03's `_cache_write_lock` (HARDENED) — share the helper from `eval/_io.py` (AC-15). The prev-hash check in AC-2 is the *correctness* defense; the flock is the *atomicity* defense. Both required: without flock, two processes can read head=H, both pass the AC-2 check, and both write a record claiming `prev_hash=H`.
- [ ] **AC-3.** Hash composition + serialization ordering. The chain construction has three steps performed in this exact order:
  1. `canon_bytes = canonical_json(report.model_copy(update={"chain_head": ""}))` — the chain_head field is replaced with `""` for hashing so the value is not self-referential. Canonical-JSON form: `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`.
  2. `content_hash = codegenie.hashing.content_hash_bytes(canon_bytes)` → `blake3:<64hex>`.
  3. `new_chain_head = codegenie.hashing.chain_identity(report.prev_hash, content_hash)` (AC-16) → `sha256:<64hex>`.
  Then the on-disk bytes are the canonical-JSON of `report.model_copy(update={"chain_head": new_chain_head})`. The hash is **not** recomputed against the final bytes (which would be circular).
- [ ] **AC-3a.** The returned `new_chain_head` byte-equals the `chain_head` field of the JSON loaded back from `written_path`; verified by `json.loads(written_path.read_bytes())["chain_head"] == new_chain_head` in tests. (Pins that `write_run_record` actually persists the computed head and doesn't write a stale or empty value.)
- [ ] **AC-4.** `verify(out_dir: Path, since: str | None = None) -> VerifyResult`:
  - **Missing dir:** `out_dir` does not exist → returns `VerifyResult(ok=True, verified_complete=0, verified_incomplete=0, tampered_path=None, reason=None)`. Empty chain is valid, not a failure.
  - **Empty dir:** same as missing — `ok=True`, zero counts.
  - **Walk:** `sorted(out_dir.glob("*.json"))` (UTC ISO timestamps with `:` → `-` substitution sort lexicographically by start-time). Filter applied per AC-4a.
  - **Per-record recomputation:** for each file, parse JSON; reconstruct canonical bytes with `chain_head=""` (AC-3 ordering); recompute content + identity hashes; compare against the walking head; tally `complete=True` vs `complete=False`.
  - **Parse failure:** `json.JSONDecodeError`, `pydantic.ValidationError`, or `UnicodeDecodeError` on any record → `VerifyResult(ok=False, verified_complete=k, verified_incomplete=m, tampered_path=record_path, reason=f"parse_error: {short_repr_of_exception}")` where `k`/`m` are counts up to (but not including) the failing record.
  - `VerifyResult` is a `@dataclass(frozen=True, slots=True)` with fields `(ok: bool, verified_complete: int, verified_incomplete: int, tampered_path: Path | None, reason: str | None)`.
- [ ] **AC-4a.** `since` semantics: inclusive lexicographic filename-prefix filter — `[p for p in sorted(out_dir.glob("*.json")) if p.name >= since]`. `since=None` is "no filter". `since=""` is equivalent to `None`. The filter applies before the chain walk; the walking head is initialized from the LAST record before the filtered window (so `verify(..., since=second_record_name)` still validates the chain link between record-1 and record-2; only the *counts* shift).
- [ ] **AC-5.** **Gap #4 — incomplete records count separately:** a record with `complete=False` (`run_id` prefixed `partial:`) increments `verified_incomplete`; with `complete=True` increments `verified_complete`. Both are valid for chain integrity; promotion gate (S4-04) is the consumer that rejects incomplete records.
- [ ] **AC-6.** **Genesis path:** writing the first-ever record (no existing `*.json`) with `report.prev_hash == GENESIS_PREV_HASH` succeeds; the resulting `verify` returns `ok=True, verified_complete=1` (assuming `complete=True`). The returned `new_chain_head` independently equals `codegenie.hashing.chain_identity(GENESIS_PREV_HASH, content_hash_bytes(canonical_json(report.model_copy(update={"chain_head": ""}))))` — verified by recomputation in the test (oracle), not by trusting the function under test.
- [ ] **AC-7.** **Tamper detection — byte flip in `run_id`:** write three records r1, r2, r3; mutate r2's on-disk JSON by replacing the `run_id` value with a syntactically valid but semantically different string (same length to avoid changing file shape; e.g., `"r2-orig"` → `"r2-FAKE"`). The `run_id` field is chosen because (a) it is a free-text wire field (not a hash), so the mutation preserves JSON validity and BLAKE3-hash divergence is the *only* signal, and (b) it does not affect the prev-hash chain semantics directly. `verify(out_dir)` → `ok=False`, `tampered_path == r2_path`, `reason` contains the substring `"content_hash"` (the failing comparison is the recomputed BLAKE3 vs the chain-walked content hash via the next record's `prev_hash`).
- [ ] **AC-8.** **Two concurrent writers — thread-free deterministic simulation:** write r1; snapshot `stale_head = current_chain_head_identity` (read directly from disk); write r2 (advances the head); attempt `write_run_record(r2_prime_with_prev_hash=stale_head, out_dir)` → raises `ChainTamperDetected` with positional args `(str(r2_path), r2_identity, stale_head)`. This pins the *prev-hash semantics* defense (AC-2). The *atomicity* defense (AC-2a flock) prevents the simultaneous-read race that AC-8 cannot deterministically simulate.
- [ ] **AC-9.** **Per-host scope is documented, not wire-enforced.** The `eval/audit.py` module docstring contains the exact substring `per-host`, references `phase-arch-design.md §Gap 5`, and states explicitly that cross-host chains are not merged. Verified by `assert "per-host" in audit.__doc__`. The `host_fingerprint` Pydantic field is **deferred** (Out of scope; see Validation notes F-CON-2) and does not block this story.
- [ ] **AC-10.** All written record files are mode `0600` (`stat.S_IRUSR | stat.S_IWUSR`); the parent `out_dir` is mode `0o700`. Verified under `os.umask(0o000)` (fixture-induced) — a post-write `os.chmod` ensures the bit regardless of umask. Independent of caller-supplied umask.
- [ ] **AC-11.** Idempotent dir creation: `write_run_record` called on a non-existent `out_dir` creates the dir (mode `0o700`); called on an existing `out_dir` does not change its mode. Verified by a test that pre-creates `out_dir` with mode `0o755` and asserts `write_run_record` leaves the mode unchanged. (Surgical-changes discipline; do not silently re-permission an operator's directory.)
- [ ] **AC-12.** **Atomic write — failure path leaves no orphan and no partial overwrite.** Inject an `OSError` in the middle of the write sequence (mock `os.fsync` to raise after the first call). The function raises; the pre-existing chain-head file is byte-identical (assert via SHA-256 snapshot); `out_dir.glob("*.tmp")` is empty within 1 second after the raise (best-effort cleanup); the new record is NOT in the chain (verify shows the previous head). Pins the atomic-rename guarantee on the failure path.
- [ ] **AC-13.** **Stop-on-first-mismatch semantic:** given a chain of 5 records where records 3, 4, 5 are all individually mutated, `verify(out_dir).tampered_path == record_3_path` (the FIRST divergence) and `verified_complete + verified_incomplete == 2` (records 1, 2 counted; record 3 is the divergence point; 4 and 5 are not walked). Documented in the docstring: operators get a precise pointer; later records are not validated once tamper is detected.
- [ ] **AC-14.** Hypothesis property test: for `N ∈ st.integers(min_value=1, max_value=20)` and a deterministic strategy producing `N` valid `BenchRunReport`s with consistent `prev_hash` chaining, writing them in order via `write_run_record` and then calling `verify(out_dir)` returns `ok=True` and `verified_complete + verified_incomplete == N`. The metamorphic invariant: `verify(out_dir)` and `verify(out_dir, since=record_k_name)` agree on `ok`; the latter's `verified_complete + verified_incomplete == N - k_index` (inclusive filter — AC-4a). (Hypothesis is already a dev dep; precedent in S1-02 AC-9, `tests/unit/indices/`.)
- [ ] **AC-15.** **Shared atomic-write helper.** `src/codegenie/eval/_io.py` exists and exports two helpers: `atomic_write_bytes(path: Path, data: bytes, mode: int = 0o600) -> None` and `eval_write_lock(out_dir: Path) -> Iterator[None]` (`@contextlib.contextmanager`-decorated, holds `fcntl.flock(LOCK_EX)` on `<out_dir>/.lock`). Both `src/codegenie/eval/cache.py` (S2-03 — migrated) and `src/codegenie/eval/audit.py` (this story) call them — no duplicated open/fsync/replace/chmod logic anywhere in `src/codegenie/eval/`. Fence test in `tests/fence/test_eval_atomic_write_chokepoint.py`: AST-walks `src/codegenie/eval/*.py`; rejects modules that call `os.replace`, `os.fsync`, or `os.O_CREAT` *outside* `_io.py`. (Rule of three met: Phase 0 `cache/store.py`, S2-03 `eval/cache.py`, S2-04 `eval/audit.py` are three sites — extraction is no longer premature. Phase 0's copy stays in place — it is the gather-pipeline closure and lives under a different import-linter contract.)
- [ ] **AC-16.** **Chain-identity primitive lives in `codegenie.hashing`.** `codegenie.hashing` exports a new public helper `chain_identity(prev_hash: str, content_hash: str) -> str` returning `sha256:<hex>` and implemented in terms of the existing `identity_hash(*parts)` (boundary-shift-safe composition per Phase 0 docstring). `src/codegenie/eval/audit.py` calls `chain_identity` — it does **not** call `hashlib.sha256(...)` directly, and it does **not** open-code `prev_hash + content_hash` concatenation. Fence test rejects any module under `src/codegenie/` calling `hashlib.sha256` on a string that contains `prev_hash` as a substring of the call-site variable name (AST walk; coarse but catches the open-coding regression). Phase 9's Temporal-durable event log will reuse this primitive — extension by addition.
- [ ] **AC-17.** TDD red tests from §TDD plan exist, were committed at the red marker, and are now green.
- [ ] **AC-18.** `ruff format --check`, `ruff check`, `mypy --strict src/codegenie/eval/audit.py src/codegenie/eval/_io.py src/codegenie/hashing.py` clean on touched files; `pytest tests/unit/eval/test_audit_chain.py tests/fence/test_eval_atomic_write_chokepoint.py` clean.

## Implementation outline

Build order is sequenced so the shared kernels land before the consumers.

1. **Land the shared atomic-write helper (AC-15) — `src/codegenie/eval/_io.py`.** Exposes:
   - `atomic_write_bytes(path: Path, data: bytes, mode: int = 0o600) -> None` — `os.open(O_CREAT|O_EXCL|O_WRONLY, mode)` on `<path>.<pid>.<token_hex(4)>.tmp` → `os.write` → `os.fsync` → `os.close` → `os.replace` → post-write `os.chmod(path, mode)`. Mirrors Phase 0 `cache/store.py:_atomic_write_bytes`.
   - `eval_write_lock(out_dir: Path) -> Iterator[None]` — `@contextlib.contextmanager`; ensures `<out_dir>/.lock` exists (mode `0o600`); opens it; `fcntl.flock(fh, LOCK_EX)`; yields; releases.
   - **Migration:** rewrite `src/codegenie/eval/cache.py` (from S2-03) to import + call these. The local `_cache_write_lock` becomes a thin alias re-exported for backward compat or deleted (matching surgical-changes discipline — Rule 3 — delete the local definition and update the one in-package import).
2. **Land the chain-identity primitive (AC-16) — extend `src/codegenie/hashing.py`.** Add:
   ```python
   def chain_identity(prev_hash: str, content_hash: str) -> str:
       """Two-arg specialization of identity_hash for audit chains."""
       return identity_hash(prev_hash, content_hash)
   ```
   Add to `__all__`. Add a `GENESIS_PREV_HASH: Final[str] = "0" * 64` constant in the same module (used by `eval/audit.py` and any future Phase 9 consumer).
3. **Create `src/codegenie/eval/audit.py`.** Module docstring contains the substring `per-host` (AC-9), cites `phase-arch-design.md §Gap 5`, and names the genesis convention (`GENESIS_PREV_HASH`).
4. **`VerifyResult` dataclass** — `@dataclass(frozen=True, slots=True)` with `(ok: bool, verified_complete: int, verified_incomplete: int, tampered_path: Path | None, reason: str | None)`.
5. **Private helpers (all pure):**
   - `_canonical_json_for_hashing(report: BenchRunReport) -> bytes` — serializes `report.model_copy(update={"chain_head": ""})` via `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")` (AC-3).
   - `_current_head(out_dir: Path) -> tuple[str, Path | None]` — returns `(GENESIS_PREV_HASH, None)` if `out_dir` doesn't exist OR is empty of `*.json`; otherwise reads the lexicographically-greatest `*.json` and returns `(parsed["chain_head"], path)`.
   - `_recompute_identity(report_json: dict, prev_hash_for_walk: str) -> tuple[str, str]` → `(content_hash, identity_hash)` per AC-3 ordering.
6. **`write_run_record(report, out_dir) -> tuple[Path, str]`:**
   - `out_dir.mkdir(parents=True, exist_ok=True)`; if newly created, `os.chmod(out_dir, 0o700)` (AC-1 + AC-11 — pre-existing dirs left untouched).
   - Inside `with eval_write_lock(out_dir):` (AC-2a):
     - `expected_prev, head_path = _current_head(out_dir)`.
     - If `report.prev_hash != expected_prev`: raise `ChainTamperDetected(str(head_path or "<genesis>"), expected_prev, report.prev_hash)` — *positional* args only (AC-2).
     - `canon_bytes = _canonical_json_for_hashing(report)`.
     - `content_hash = codegenie.hashing.content_hash_bytes(canon_bytes)`.
     - `new_head = codegenie.hashing.chain_identity(report.prev_hash, content_hash)` (AC-16).
     - `report_with_head = report.model_copy(update={"chain_head": new_head})` — frozen-Pydantic-compatible (AC-3 ordering).
     - `final_bytes = json.dumps(report_with_head.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`.
     - Build filename `f"{utc_iso}-{secrets.token_hex(4)}.json"` (UTC ISO with `:` → `-` replacement for FS-safety; matches Phase 0 S3-06).
     - `atomic_write_bytes(final / filename, final_bytes, mode=0o600)` (AC-10 via the helper).
   - Return `(final_path, new_head)`.
7. **`verify(out_dir, since=None) -> VerifyResult`:**
   - If `not out_dir.exists()`: return `VerifyResult(ok=True, 0, 0, None, None)` (AC-4).
   - `all_paths = sorted(out_dir.glob("*.json"))`; if empty: same as missing.
   - Initialize walking `head = GENESIS_PREV_HASH`; complete = incomplete = 0.
   - Walk forward through `all_paths`:
     - Apply `since` filter to *count contribution* but not to chain integrity: a record before `since` still contributes to `head` advancement but does not increment counters (AC-4a).
     - Try `parsed = json.loads(path.read_bytes())` and `report = BenchRunReport.model_validate(parsed)`. On exception: return `VerifyResult(ok=False, counts, path, f"parse_error: {type(exc).__name__}: {exc}")`.
     - Recompute `content_hash, identity` per AC-3 (using `_canonical_json_for_hashing` on the parsed report, then comparing identity against `parsed["chain_head"]`).
     - If `report.prev_hash != head` OR `parsed["chain_head"] != identity`: return `VerifyResult(ok=False, counts, path, "content_hash mismatch" or "prev_hash mismatch")` (AC-7 / AC-13).
     - Advance: `head = identity`. If filename in filtered window, increment the matching counter (complete vs incomplete by `report.complete`).
   - Return `VerifyResult(ok=True, complete_count, incomplete_count, None, None)`.

## TDD plan — red / green / refactor

### Red

Test files (precedent for the helper-builder pattern: `tests/unit/test_eval_models.py` from S1-02):

`tests/unit/eval/test_audit_chain.py`:

```python
# --- helper pinned by Validation notes (mirrors S1-02 _make_report shape) ---
def _make_report(
    prev_hash: str = "0" * 64,
    chain_head: str = "",            # set by write_run_record; "" before persistence
    complete: bool = True,
    run_id: str = "r-orig",
    **overrides,
) -> BenchRunReport:
    base = dict(
        run_id=run_id,
        task_class="vuln-remediation",
        started_at="2026-05-26T00:00:00Z",
        finished_at="2026-05-26T00:01:00Z",
        per_case=(),
        failure_modes=(),
        block_severity_failure_modes=(),
        mean_score=0.0, lower_bound_95=0.0, score_stddev=0.0,
        passed_count=0, total_cost_usd=0.0,
        isolation_class="subprocess",
        complete=complete,
        prev_hash=prev_hash,
        chain_head=chain_head,
    )
    base.update(overrides)
    return BenchRunReport(**base)


# === AC-6 (genesis + independent-recomputation oracle) ====================
def test_genesis_record_chain_head_matches_independent_oracle(tmp_path):
    rpt = _make_report(prev_hash=GENESIS_PREV_HASH)
    path, head = audit.write_run_record(rpt, tmp_path)
    # Independently recompute the head — do not trust the function under test.
    canon = json.dumps(
        rpt.model_copy(update={"chain_head": ""}).model_dump(mode="json"),
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    expected = chain_identity(GENESIS_PREV_HASH, content_hash_bytes(canon))
    assert head == expected
    assert head.startswith("sha256:")
    res = audit.verify(tmp_path)
    assert res.ok is True and res.verified_complete == 1


# === AC-2 (positional-arg ChainTamperDetected — S1-01 marker-only) =========
def test_genesis_with_wrong_prev_hash_raises_positionally(tmp_path):
    rpt = _make_report(prev_hash="f" * 64)
    with pytest.raises(ChainTamperDetected) as ei:
        audit.write_run_record(rpt, tmp_path)
    # No attribute access — the class is a marker (S1-01 AC-8); only .args works.
    assert ei.value.args == ("<genesis>", GENESIS_PREV_HASH, "f" * 64)


# === AC-3a (chain_head persisted to disk) ==================================
def test_written_chain_head_equals_returned(tmp_path):
    rpt = _make_report(prev_hash=GENESIS_PREV_HASH)
    path, head = audit.write_run_record(rpt, tmp_path)
    on_disk = json.loads(path.read_bytes())["chain_head"]
    assert on_disk == head


# === AC-5 (Gap #4) =========================================================
def test_incomplete_records_count_separately(tmp_path):
    r1 = _make_report(prev_hash=GENESIS_PREV_HASH)
    p1, h1 = audit.write_run_record(r1, tmp_path)
    r2 = _make_report(prev_hash=h1, complete=False, run_id="partial:r2")
    audit.write_run_record(r2, tmp_path)
    res = audit.verify(tmp_path)
    assert res.ok and res.verified_complete == 1 and res.verified_incomplete == 1


# === AC-7 (tamper detection — byte flip in run_id) =========================
def test_tampered_run_id_field_makes_verify_fail(tmp_path):
    r1 = _make_report(prev_hash=GENESIS_PREV_HASH, run_id="r1-orig")
    p1, h1 = audit.write_run_record(r1, tmp_path)
    r2 = _make_report(prev_hash=h1, run_id="r2-orig")
    p2, h2 = audit.write_run_record(r2, tmp_path)
    r3 = _make_report(prev_hash=h2, run_id="r3-orig")
    audit.write_run_record(r3, tmp_path)
    # Mutate r2: same-length swap so JSON shape is preserved.
    raw = json.loads(p2.read_bytes())
    assert raw["run_id"] == "r2-orig"
    raw["run_id"] = "r2-FAKE"
    p2.write_bytes(json.dumps(raw, sort_keys=True, separators=(",", ":")).encode())
    res = audit.verify(tmp_path)
    assert res.ok is False
    assert res.tampered_path == p2
    assert "content_hash" in (res.reason or "")


# === AC-8 (concurrent stale-prev simulation) ===============================
def test_stale_prev_hash_raises_chain_tamper_detected(tmp_path):
    r1 = _make_report(prev_hash=GENESIS_PREV_HASH)
    p1, h1 = audit.write_run_record(r1, tmp_path)
    stale_head = h1
    r2 = _make_report(prev_hash=h1)
    p2, h2 = audit.write_run_record(r2, tmp_path)  # advances head
    r2_prime = _make_report(prev_hash=stale_head, run_id="r2-prime")
    with pytest.raises(ChainTamperDetected) as ei:
        audit.write_run_record(r2_prime, tmp_path)
    assert ei.value.args == (str(p2), h2, stale_head)


# === AC-2a (flock — direct probe) ==========================================
def test_write_run_record_holds_exclusive_flock(tmp_path, monkeypatch):
    """Catches: flock omitted, leaving the head-read/head-write race open."""
    import threading, time
    from codegenie.eval import _io
    real_write = _io.atomic_write_bytes
    paused = threading.Event()
    released = threading.Event()

    def slow_write(*a, **kw):
        paused.set()
        released.wait(timeout=2.0)
        return real_write(*a, **kw)

    monkeypatch.setattr(_io, "atomic_write_bytes", slow_write)
    rpt = _make_report(prev_hash=GENESIS_PREV_HASH)
    out_dir = tmp_path
    out_dir.mkdir(exist_ok=True)
    t = threading.Thread(target=lambda: audit.write_run_record(rpt, out_dir))
    t.start()
    paused.wait(timeout=2.0)
    # Sibling LOCK_NB must fail while the writer holds the lock.
    with open(out_dir / ".lock", "r") as fh:
        with pytest.raises(BlockingIOError):
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    released.set()
    t.join()


# === AC-9 (per-host documentation) =========================================
def test_module_docstring_declares_per_host_scope():
    from codegenie.eval import audit as mod
    assert mod.__doc__ and "per-host" in mod.__doc__


# === AC-10 + AC-11 (mode discipline under umask=0o000) =====================
def test_records_are_0600_and_dir_is_0700_under_zero_umask(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "umask", lambda _m: 0o022)  # restore default in teardown
    os.umask(0o000)
    sub = tmp_path / "fresh"
    rpt = _make_report(prev_hash=GENESIS_PREV_HASH)
    path, _ = audit.write_run_record(rpt, sub)
    assert (path.stat().st_mode & 0o777) == 0o600
    assert (sub.stat().st_mode & 0o777) == 0o700


def test_preexisting_out_dir_mode_is_not_silently_changed(tmp_path):
    sub = tmp_path / "preexisting"
    sub.mkdir(mode=0o755)
    audit.write_run_record(_make_report(prev_hash=GENESIS_PREV_HASH), sub)
    assert (sub.stat().st_mode & 0o777) == 0o755  # untouched


# === AC-12 (atomic write — failure path) ===================================
def test_failed_write_leaves_prior_chain_intact(tmp_path, monkeypatch):
    r1 = _make_report(prev_hash=GENESIS_PREV_HASH)
    p1, h1 = audit.write_run_record(r1, tmp_path)
    snap = hashlib.sha256(p1.read_bytes()).hexdigest()
    # Force OSError mid-write.
    import codegenie.eval._io as _io
    real_fsync = os.fsync
    calls = {"n": 0}
    def boom_after_first(fd):
        calls["n"] += 1
        if calls["n"] >= 2:  # first call is for our induced second write
            raise OSError("simulated disk full")
        return real_fsync(fd)
    monkeypatch.setattr(os, "fsync", boom_after_first)
    r2 = _make_report(prev_hash=h1)
    with pytest.raises(OSError):
        audit.write_run_record(r2, tmp_path)
    assert hashlib.sha256(p1.read_bytes()).hexdigest() == snap
    assert list(tmp_path.glob("*.tmp")) == []


# === AC-13 (stop-on-first-mismatch) ========================================
def test_verify_stops_at_first_tampered_record(tmp_path):
    # Write 5; mutate r3, r4, r5 all in same way; verify returns tampered_path == r3.
    ...


# === AC-4 (missing-dir + parse-error) ======================================
def test_verify_on_missing_dir_is_empty_chain_ok():
    res = audit.verify(Path("/nonexistent/path"))
    assert res.ok and res.verified_complete == 0 and res.verified_incomplete == 0


def test_verify_on_malformed_json_returns_parse_error(tmp_path):
    r1 = _make_report(prev_hash=GENESIS_PREV_HASH)
    p1, _ = audit.write_run_record(r1, tmp_path)
    p1.write_bytes(b"{not valid json")
    res = audit.verify(tmp_path)
    assert res.ok is False and "parse_error" in (res.reason or "") and res.tampered_path == p1


# === AC-4a (since filter — metamorphic) ====================================
def test_verify_since_filter_inclusive_lexicographic(tmp_path):
    # Three records; verify(since=r2_name).verified_complete == 2 (r2 and r3); verify().== 3.
    ...


# === AC-14 (hypothesis — chain integrity over N=1..20) =====================
@given(n=st.integers(min_value=1, max_value=20))
@settings(max_examples=25, deadline=None)
def test_chain_of_N_records_always_verifies(tmp_path_factory, n):
    out = tmp_path_factory.mktemp(f"chain-{n}")
    head = GENESIS_PREV_HASH
    for i in range(n):
        r = _make_report(prev_hash=head, run_id=f"r{i}")
        _, head = audit.write_run_record(r, out)
    res = audit.verify(out)
    assert res.ok is True
    assert res.verified_complete + res.verified_incomplete == n
```

`tests/fence/test_eval_atomic_write_chokepoint.py` (AC-15):

```python
def test_no_module_in_eval_opens_o_creat_outside_io():
    """Fence — only eval/_io.py may call os.open(O_CREAT...), os.fsync, os.replace."""
    ...
```

### Green

Smallest impl: §Implementation outline; ~120 lines across `eval/_io.py` (~30), `eval/audit.py` (~80), and the `chain_identity` + `GENESIS_PREV_HASH` additions to `codegenie/hashing.py` (~10).

### Refactor

- Add `structlog.info("audit.record_written", run_id=..., chain_head=..., path=...)` after each successful `write_run_record`.
- Module docstring on `eval/audit.py` cites `phase-arch-design.md §Gap 5` and the per-host scope verbatim (AC-9).
- (Extraction of `_atomic_write_bytes` is already an AC — AC-15 — not a refactor.)

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/audit.py` | **New** — `write_run_record`, `verify`, `VerifyResult` |
| `src/codegenie/eval/_io.py` | **New** — `atomic_write_bytes`, `eval_write_lock` (AC-15) |
| `src/codegenie/eval/cache.py` | **Edit** — migrate S2-03's `_atomic_write_bytes` + `_cache_write_lock` callsites to `_io` helpers (AC-15) |
| `src/codegenie/hashing.py` | **Edit** — add `chain_identity` + `GENESIS_PREV_HASH` (AC-16) |
| `tests/unit/eval/test_audit_chain.py` | **New** — red tests across AC-2..AC-14 |
| `tests/fence/test_eval_atomic_write_chokepoint.py` | **New** — fence pinning the chokepoint (AC-15) |
| `src/codegenie/eval/models.py` | **Not touched here** — `host_fingerprint` field add is deferred (Out of scope; see Validation notes F-CON-2). S1-02 is HARDENED and should not be edited mid-phase. |

## Out of scope

- **`BenchRunReport.host_fingerprint` Pydantic field.** S1-02 is HARDENED with an exact 5-type wire contract. Adding the field requires a Phase 6.5 ADR amendment and a follow-up S1-02 wire-bump story; defer. The *per-host scope* of the chain is documented in `eval/audit.py`'s docstring (AC-9) — no wire change needed for documentation.
- **Cross-host chain merging.** Explicit non-goal per Gap #5 part 1; integration tests in S7-02 will verify the per-host floor once `host_fingerprint` lands.
- **`--promotion-source-host=<fingerprint>` CLI knob** (Gap #5 part 2). Belongs in S4-03 (`codegenie eval verify` CLI) or a later promotion-gate story; out of scope here.
- **`codegenie eval verify` CLI subcommand.** Handled by S4-03; this story exposes the `verify(...)` library function only.
- **Sigstore signing of the chain head.** Explicit non-goal #2 in `phase-arch-design.md`; Phase 16 work.
- **Chain pruning / archival.** The chain grows unboundedly and is the operator's manual concern.
- **Windows lock primitive.** `fcntl.flock` is POSIX-only; `msvcrt.locking` swap is out-of-roadmap (matches S2-03's deferral).

## Notes for the implementer

- **Phase 0's `codegenie.audit` does NOT expose `chain_append` / `chain_verify`.** The published surface is `AuditWriter.record(...)` (single-record write) + `verify_runs(...)` (whole-set verifier specific to gather runs). There is no per-record chain primitive to reuse. The original story-writer drafted around an aspirational API; the validator confirmed the actual surface. **Therefore:** factor the BLAKE3-content + SHA-256-identity composition into `codegenie.hashing` as `chain_identity(prev, content) -> str` (AC-16). The Phase 0 gather chain stays untouched; this story does not "extend" the existing Phase 0 chain — it builds a *sibling* chain in a different directory using the same primitives. Document this explicitly in the module docstring.
- The eval chain lives at `.codegenie/eval/runs/`, separate from Phase 0's `.codegenie/runs/` (gather records). Two distinct directories, same primitives; do not merge.
- **`ChainTamperDetected` is a marker-only Exception (S1-01 AC-8).** It has no custom `__init__`. Raise it positionally — `raise ChainTamperDetected(head_path_str, expected_prev, computed_prev)` — and pin the argument tuple via `ei.value.args`. **Do not** use keyword arguments and **do not** access fictitious `.expected_prev` / `.computed_prev` attributes. If a future story decides this loss of named-attribute access is too painful, the correct path is a Phase 6.5 ADR amendment that widens S1-01 to permit a custom `__init__` on selected subclasses (with a structured-error contract); not a silent edit here.
- **Frozen Pydantic + chain_head ordering (AC-3).** `BenchRunReport` is `frozen=True` (S1-02 AC-2). To set `chain_head` after computing it: `report.model_copy(update={"chain_head": new_head})`. The canonical-JSON used for hashing must use the *placeholder* `chain_head=""` so the identity is computable; the on-disk JSON uses the *computed* `chain_head=new_head`. Be precise — confusing the two yields a chain that fails its own verify on the next write.
- **`fcntl.flock` is non-negotiable (AC-2a).** Without it, two concurrent processes both read head=H and both write records claiming `prev_hash=H`. The prev-hash check (AC-2) is per-process correctness; the flock is per-host atomicity. Mirror S2-03's `_cache_write_lock` shape — share the helper via `_io.eval_write_lock`.
- **Atomic-write extraction crosses rule-of-three (AC-15).** Phase 0 `cache/store.py:_atomic_write_bytes` is site 1. S2-03 `eval/cache.py` is site 2 (private duplicate). S2-04 is site 3. Three sites → extract. The shared helper lives at `src/codegenie/eval/_io.py` (not in `codegenie/hashing.py`, which is for hashing primitives, not I/O). Migrate S2-03's callsites first to keep both modules pointing at the same code.
- **Chain-identity primitive lives in `codegenie.hashing` (AC-16).** Phase 9's Temporal-durable event log will use the same composition. Putting it inside `eval/audit.py` would make Phase 9 a copy-paste — extension by *editing*, not addition.
- Genesis convention `GENESIS_PREV_HASH = "0" * 64` is a hex string, NOT bytes; the comparison happens after `report.prev_hash` is already a hex string per `BenchRunReport`'s Pydantic schema. Define it in `codegenie.hashing` so future consumers reach for the same constant.
- The UTC ISO timestamp in filenames: use `datetime.now(UTC).isoformat()`; replace `":"` with `"-"` for filesystem-safety (matches Phase 0 S3-06 §AC).
- `verify`'s "stop on first mismatch" semantic means later records aren't validated once tamper is detected; this is the documented design (operator sees a precise pointer to the divergent file). Don't `unlink` corrupt records during `verify` — operators want them on disk for forensic review.
- **`host_fingerprint` is explicitly out-of-scope (see Validation notes F-CON-2).** Do not surface to "the S1-02 maintainer" — S1-02 is HARDENED and locked. The follow-up is a Phase 6.5 ADR + a wire-bump story sequenced after S2-04. The per-host *scope* of the chain is captured in the docstring (AC-9), which is sufficient until cross-host promotion-gate work lands.
- **`VerifyResult` could be a sum type** (`VerifyOk(...)` | `VerifyTampered(...)`) to make `tampered_path = None` when `ok=True` structurally impossible. Today's flat dataclass is YAGNI-correct for a single producer. If Phase 9's event log adds a second consumer that branches on the variant, promote at that point. (Design-Patterns F-DP-3.)
- **`_current_head` could return a sum type** (`ChainEmpty()` | `ChainHead(identity, path)`) instead of a 2-tuple with `None` sentinel. Trivial today; consider only if a third caller of `_current_head` arrives. (Design-Patterns F-DP-4.)
