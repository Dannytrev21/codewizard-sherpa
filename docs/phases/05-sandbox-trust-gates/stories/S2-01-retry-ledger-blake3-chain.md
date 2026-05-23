# Story S2-01 — `RetryLedger` BLAKE3-chained JSONL + `Attempt` model

**Step:** Step 2 — Implement `RetryLedger` and audit-chain extension
**Status:** HARDENED
**Validation:** 2026-05-23 — see [`_validation/S2-01-retry-ledger-blake3-chain.md`](_validation/S2-01-retry-ledger-blake3-chain.md)
**Effort:** M
**Depends on:** S1-01, S1-03, S1-04
**ADRs honored:** ADR-0005, ADR-0007, ADR-0011, ADR-0014

## Context

The `RetryLedger` is one of Phase 5's three load-bearing abstractions (per `phase-arch-design.md §Component design`) and is the only durable checkpoint the retry loop produces. Every attempt appends one **BLAKE3-128**-chained JSONL line tagged `"type": "attempt"` to `.codegenie/remediation/<run-id>/gates/<gate_id>/attempts.jsonl`, and that file plus the sandbox-run sub-directories are what Phase 6's checkpointer will lift unchanged. This story lands the core `record`, `head`, and `attempts` replay surface plus resume-on-reopen recovery; pre-execute marker (S2-02 — additive `"type": "pre_execute"` rows + `LedgerEntry` discriminated-union read API) and Phase 4 chain-head startup check (S2-03 — `chain_head.bin` read + verification) extend it without editing any S2-01 code.

## Validation notes — what changed during hardening (2026-05-23)

1. **Hash size aligned with S1-04 HARDENED contract.** Every "32 bytes / 64 hex" rewritten to "16 bytes / 32 hex / BLAKE3-128" — the draft would have constructed `Attempt(prev_hash="00" * 32)` and been rejected by S1-04's `field_validator(prev_hash, mode="after")` regex `^[0-9a-f]{32}$`. Implementation must call `.hexdigest(length=16)`, not the default `.hexdigest()`.
2. **`type: "attempt"` discriminator added at the JSONL-serialization layer, not on the `Attempt` model.** S2-02's draft plans to edit S1-04's frozen `Attempt` to add a `type` field — that violates CLAUDE.md "Extension by addition" against a HARDENED contract. This story writes `{"type": "attempt", **canonical_attempt_minus_chain_hash, "chain_hash": <computed>}` to disk; replay validates and drops the field; the `Attempt` model is never touched. S2-02 then lands `{"type": "pre_execute", ...}` as pure addition.
3. **Resume-on-reopen semantics pinned (the Phase 6 contract).** `__init__` reads any existing `attempts.jsonl`, recovers `_next_attempt_id = max(attempt_id) + 1` and `_last_chain_hash` from the last row, and verifies the recovered chain head against `prev_chain_head` when both are non-None — raising `AuditChainCorrupted` on mismatch. Without this, a second `RetryLedger(...)` over the same gate-dir silently corrupts.
4. **Canonical-JSON boundary for `chain_hash` pinned.** `_canonical_json` excludes `chain_hash` (`model_dump(mode="json", exclude={"chain_hash"})`). The on-disk JSONL line is one-pass: `{**canonical_no_chain_hash, "chain_hash": <computed>}`. Replay recomputes `_compute_chain_hash(prev_hash, canonical_json_excluding_chain_hash)`. Avoids the chicken-and-egg of "hash depends on a field that depends on the hash."
5. **Property test rewritten from tautological (`f(x) == f(x)`) to mutation-witness** — prefix-replay invariance, payload-permutation witness, canonical-bytes determinism.
6. **Pure module-level helpers promoted from Refactor to AC** — `_canonical_json`, `_compute_chain_hash`, `_recover_chain_state` — so S2-02 can reuse via import (not via subclassing or class-method binding).
7. **Tamper test parametrized across multiple fields** (`sandbox_run_id`, `outcome.summary`, `attempt_id`, `prev_hash`) — single-field tamper test would pass a regression that only validates the one field.
8. **fsync verification split** — structural (mocked call-count on file fd + dir fd) vs perf (`bench`-marked timing on tmpfs).
9. **`LedgerAttemptOutOfOrder` semantics relaxed** from "strictly increasing from 1" to "equals `_next_attempt_id`" so resume-on-reopen works.
10. **`AuditChainCorrupted` exposes structured attributes** (`.attempt_id: int | None`, `.row_index: int`) — fragile substring assertions removed.
11. **Replay enforces `extra=forbid`-style strictness** — unknown JSON field on an `"attempt"` row raises `AuditChainCorrupted` (mirrors ADR-0014's `ObjectiveSignals` discipline; mutation-resistance against silent field drift).
12. **`record(attempt)` ignores caller-supplied `prev_hash` / `chain_hash`** — those are placeholder-only; the ledger overwrites with `self.head().hex()` and the computed hash. Removes a caller-side footgun.
13. **`manifest.yaml` shape pinned** — alphabetized keys via `safe_dump(sort_keys=True)`, `open(..., "x")` first-write semantics, idempotent re-open when contents match, `AuditChainCorrupted` when contents mismatch.
14. **Newtype constructors in TDD** — `AttemptNumber(...)` / `RunId(...)` per S1-04 Notes ("tests use the constructor form as intent documentation").
15. **Module-purity test added** — `tests/gates/test_retry_ledger_purity.py` AST-walks imports against an allowlist (S1-02..S1-07 precedent).
16. **`gates/__init__.py` re-export gets a one-line import test** — AC-EX-1.
17. **Adversarial tamper test path added to Files-to-touch** — was AC-only.
18. **Carryforward flags for S2-02 and S2-03 in Notes** — S2-02 must NOT edit `Attempt` (the discriminator now lives at the JSONL layer); S2-03 AC-3 ("≠ 32 bytes") must be amended to ≠ 16 bytes during S2-03 validation.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — RetryLedger` — purpose, file layout, internal structure, failure behavior.
  - `../phase-arch-design.md §Logical view` — `RetryLedger` class diagram with `prev_chain_head` and `Attempt` shape.
  - `../phase-arch-design.md §Process view` — sequence diagram showing `record` write ordering with `GateRunner`.
  - `../phase-arch-design.md §Edge cases §11` — manual `attempts.jsonl` edit triggers `AuditChainCorrupted` on replay.
  - `../phase-arch-design.md §Code contracts and APIs` — the `Attempt` Pydantic model (`attempt_id`, `sandbox_run_id`, `signals`, `outcome`, `started_at`, `ended_at`, `prev_hash`, `chain_hash`).
- **Phase ADRs:**
  - `../ADRs/0005-phase4-chain-head-compatibility.md` — `record` extends a chain that began in Phase 4; `attempts.jsonl` is append-only with BLAKE3 per-line.
  - `../ADRs/0011-no-verdict-cache-in-phase-5.md` — `record` must not double-write on identical `(attempt_id, spec_hash)`; raise `LedgerAttemptOutOfOrder` instead.
- **Production ADRs:**
  - `../../../production/adrs/0014-three-retry-default-per-gate.md` — three attempts is the upper-bound `attempt_id`.
- **Source design:**
  - `../final-design.md §Synthesis ledger row "BLAKE3-chained RetryLedger"`.
- **Existing code:**
  - `src/codegenie/gates/contract.py` (from S1-04) — imports `Attempt`, `TransitionId`, `GateOutcome`.
  - `src/codegenie/gates/errors.py` (from S1-01) — extend with `AuditChainCorrupted` and `LedgerAttemptOutOfOrder`.

## Goal

Implement `RetryLedger` with `record`, `head`, and `attempts` replay verification over a **BLAKE3-128**-chained `attempts.jsonl` file whose every line carries a `"type": "attempt"` discriminator (so S2-02 adds `"pre_execute"` rows additively without editing this story's code), with sibling `manifest.yaml` (alphabetized keys, first-write-only), fsynced per-record writes (file fd + parent dir fd), pure module-level chain-math helpers, and **resume-on-reopen recovery** of `_next_attempt_id` and `_last_chain_hash` from any existing on-disk `attempts.jsonl` (the Phase 6 checkpointer contract per arch §Concurrency-and-checkpoints).

## Acceptance criteria

### A. Hash format (BLAKE3-128 per S1-04 HARDENED contract)

- [ ] **AC-H-1 — `chain_hash` is 32 lowercase hex chars (BLAKE3-128, 16 bytes).** Implementation uses `blake3(prev_hash_bytes + payload_bytes).hexdigest(length=16)` — explicitly truncated, *not* the 64-char default. A unit test asserts `len(payload["chain_hash"]) == 32` and `re.fullmatch(r"[0-9a-f]{32}", payload["chain_hash"])` for every written line. This matches `Attempt.chain_hash`'s S1-04 validator (`^[0-9a-f]{32}$`) — a 64-char hash would be rejected at construction time.
- [ ] **AC-H-2 — `prev_hash` chains via raw bytes, not hex.** `_compute_chain_hash(prev_hex: str, payload: bytes) -> str` decodes `bytes.fromhex(prev_hex)` (16 bytes) and concatenates with payload before hashing; replay does the same. A parametrized test feeds known `(prev_hex, payload) → expected_chain_hash` vectors and asserts byte-equality.
- [ ] **AC-H-3 — `prev_chain_head: bytes | None` is 16 bytes when present.** `__init__` raises `ValueError("prev_chain_head must be 16 bytes; got {n}")` if `prev_chain_head is not None and len(prev_chain_head) != 16`.
- [ ] **AC-H-4 — `head() -> bytes` returns 16 bytes always.** If no lines yet: `prev_chain_head` (if non-None) else `b"\x00" * 16`. If lines present: `bytes.fromhex(_last_chain_hash)` (16 bytes). Test asserts `len(ledger.head()) == 16` in all three branches.

### B. JSONL `"type"` discriminator (forward-compat seam for S2-02)

- [ ] **AC-T-1 — every line written by `record(attempt)` has shape `{"type": "attempt", **canonical_attempt_without_chain_hash, "chain_hash": "<computed>"}`.** The `"type"` field is injected at the JSONL-serialization layer, NOT added to the `Attempt` Pydantic model. S1-04's frozen `Attempt` is untouched. Test asserts `json.loads(line)["type"] == "attempt"` and `set(json.loads(line).keys()) == {"type", *Attempt.model_fields, "chain_hash"} - {"chain_hash"} | {"chain_hash"}` (i.e., exactly: type + all Attempt fields).
- [ ] **AC-T-2 — `attempts()` filters by `type == "attempt"`.** Replay reads each line, asserts `payload["type"] == "attempt"` (any other value raises `AuditChainCorrupted(message=f"unknown ledger row type: {payload['type']!r}")`), pops `"type"`, validates as `Attempt`. This lets S2-02's `"pre_execute"` rows interleave without breaking S2-01 read paths once `attempts()` is taught the filter (which this story ships).
- [ ] **AC-T-3 — type-discriminator participates in the chain.** `_canonical_json` includes the `"type": "attempt"` field as the first key (after `sort_keys=True` ordering, `"type"` sorts after `"started_at"` alphabetically — but the canonicalization is `sort_keys=True` so order is alphabetical, deterministic across runs). Test: tampering the on-disk `"type"` value from `"attempt"` to `"attempt_v2"` raises `AuditChainCorrupted` on replay (both because the chain breaks AND because the type filter rejects it).

### C. Canonical-JSON payload boundary

- [ ] **AC-CJ-1 — `_canonical_json(attempt: Attempt) -> bytes` excludes `chain_hash` from the payload.** Implementation: `attempt.model_dump(mode="json", exclude={"chain_hash"})` → `json.dumps(..., sort_keys=True, separators=(",", ":")).encode()`. With `"type"` injected separately, the final canonical bytes are `json.dumps({"type": "attempt", **dumped_without_chain_hash}, sort_keys=True, separators=(",", ":")).encode()`. The chain_hash is computed over THESE bytes; the on-disk line is the JSON of `{**that_dict, "chain_hash": <computed>}` re-canonicalized.
- [ ] **AC-CJ-2 — replay recomputation is symmetric with write.** `attempts()` reads each line, drops `chain_hash`, re-canonicalizes via the same `_canonical_json` helper applied to the parsed `Attempt`, recomputes `chain_hash`, asserts byte-equality with the on-disk value. Test: a manually-edited `chain_hash` (matching format but wrong value) raises `AuditChainCorrupted`.
- [ ] **AC-CJ-3 — canonical bytes are deterministic across invocations.** Property test: same `Attempt` → byte-identical `_canonical_json` output across 100 independent calls. Catches accidental dict-ordering drift or non-deterministic field iteration.

### D. Resume-on-reopen (Phase 6 contract per arch §236)

- [ ] **AC-RR-1 — `__init__` recovers state from existing `attempts.jsonl` if present.** Reads every line, scans for the maximum `attempt_id` over rows with `type == "attempt"`, sets `_next_attempt_id = max_seen + 1`. Sets `_last_chain_hash` from the file's last line's `chain_hash` (regardless of type — so a trailing orphan `pre_execute` from S2-02 chains correctly).
- [ ] **AC-RR-2 — `__init__` verifies recovered chain head against `prev_chain_head`.** If `prev_chain_head is not None` AND the file is non-empty, the first row's `prev_hash` must equal `prev_chain_head.hex()`. Mismatch raises `AuditChainCorrupted("recovered chain root does not match prev_chain_head")`.
- [ ] **AC-RR-3 — `__init__` over an empty `attempts.jsonl` is equivalent to first-use.** `_next_attempt_id = 1`; `_last_chain_hash = None`. Test: `Path.touch()` an empty `attempts.jsonl`, construct the ledger, `record(Attempt(attempt_id=AttemptNumber(1)))` succeeds.
- [ ] **AC-RR-4 — second `RetryLedger(...)` over the same gate-dir after N records resumes correctly.** Test: construct ledger, record 2 attempts, *discard the instance*, construct a *new* `RetryLedger(...)` over the same `run_dir` + `gate_id`, assert `ledger.head() == <bytes.fromhex(second_record.chain_hash)>`, then `record(Attempt(attempt_id=AttemptNumber(3)))` succeeds and chains correctly. A `record(Attempt(attempt_id=AttemptNumber(1)))` after resume raises `LedgerAttemptOutOfOrder` (recovery sets `_next_attempt_id = 3`).

### E. Out-of-order / duplicate guards

- [ ] **AC-OO-1 — `record(attempt)` accepts iff `attempt.attempt_id == self._next_attempt_id`.** Any other value raises `LedgerAttemptOutOfOrder(f"expected attempt_id={self._next_attempt_id}, got {attempt.attempt_id}")` *before* any disk write. Test: record `attempt_id=1`, then `record(attempt_id=1)` raises and `attempts.jsonl` still has exactly one line; `record(attempt_id=3)` raises (skipping ID 2).
- [ ] **AC-OO-2 — `LedgerAttemptOutOfOrder` exposes structured `.expected: int` and `.got: int` attributes.** Callers can act on the numbers without parsing the message.

### F. Manifest.yaml shape and first-write semantics

- [ ] **AC-MF-1 — `manifest.yaml` keys are alphabetized via `yaml.safe_dump(..., sort_keys=True)`.** Fields: `created_at` (UTC ISO-8601 string), `gate_id`, `prev_chain_head` (hex string, or `null` if `None`). No other keys. Test: `yaml.safe_load(path.read_text())` returns exactly `{"created_at": ..., "gate_id": ..., "prev_chain_head": ...}`.
- [ ] **AC-MF-2 — `__init__` writes `manifest.yaml` exactly once.** Uses `open(manifest_path, "x")` (exclusive-create) on first construction; FileExistsError → fall through to AC-MF-3.
- [ ] **AC-MF-3 — re-opening with a matching `manifest.yaml` is idempotent (no rewrite).** If the existing file's `gate_id` matches AND `prev_chain_head` matches, `__init__` proceeds without rewriting (the original `created_at` is preserved as load-bearing audit metadata).
- [ ] **AC-MF-4 — re-opening with a *mismatched* `manifest.yaml` raises `AuditChainCorrupted`.** If `manifest.yaml` exists with a different `gate_id` or `prev_chain_head` than the one passed to `__init__`, raise `AuditChainCorrupted(f"manifest mismatch: on-disk={...}, constructed-with={...}")`. Test: write a manifest, construct a ledger with a different `prev_chain_head`, assert raise.

### G. Pure module-level helpers (S2-02 reuse seam)

- [ ] **AC-PH-1 — `_canonical_json`, `_compute_chain_hash`, `_recover_chain_state` are module-level pure functions.** No `self`, no `Path` arguments that get opened inside, no logging. Class methods orchestrate I/O around them. `tests/gates/test_retry_ledger_purity.py` AST-walks `retry_ledger.py` and asserts the three function names are at `ast.Module` top level (not nested inside a `ClassDef`).
- [ ] **AC-PH-2 — module-purity import allowlist.** Same test asserts `retry_ledger.py` imports a subset of `{__future__, json, os, errno, datetime, pathlib, typing, blake3, pydantic, yaml, structlog, codegenie.errors, codegenie.types.identifiers, codegenie.gates.errors, codegenie.gates.contract, codegenie.sandbox.signals.models}`. No `subprocess`, no `requests`, no `langchain`, no `anthropic`. Mirrors S1-02..S1-07 module-purity discipline.

### H. Replay strictness (mirrors ADR-0014)

- [ ] **AC-EF-1 — unknown JSON field on an `"attempt"` row raises `AuditChainCorrupted`.** Replay parses the line, drops `"type"`, then calls `Attempt.model_validate(...)` — S1-04's `extra="forbid"` catches the unknown field; the replay catches the `ValidationError` and re-raises as `AuditChainCorrupted(f"row {i}: unknown field(s) {names!r}")`. Test: write a valid line, append `, "rogue": 1` before the closing brace, assert replay raises.

### I. `record(attempt)` ignores caller-supplied chain fields

- [ ] **AC-IG-1 — `record(attempt)` substitutes `prev_hash = self.head().hex()` and `chain_hash = <computed>` regardless of caller-supplied values.** The Attempt is rebuilt via `attempt.model_copy(update={"prev_hash": ..., "chain_hash": ...})` before serialization (S1-04's `frozen=True` allows `model_copy` — it returns a new instance). Test: construct `_make_attempt(2, prev_hash="ff" * 16)` (intentionally wrong), call `record`, assert the on-disk `prev_hash` equals `ledger_head_before_record.hex()`, NOT `"ff" * 16`.
- [ ] **AC-IG-2 — two records with intentionally-wrong caller-supplied hashes still produce a correctly-chained on-disk pair.** Test: `record(attempt_id=1, prev_hash="aa"*16, chain_hash="bb"*16)`, `record(attempt_id=2, prev_hash="cc"*16, chain_hash="dd"*16)`, then `ledger.attempts()` succeeds (no `AuditChainCorrupted`) — confirming the ledger overwrote caller values with chain-correct ones.

### J. Audit-chain tamper detection (the adversarial fence)

- [ ] **AC-AT-1 — `tests/adversarial/test_audit_chain_tamper.py` parametrizes tamper across multiple fields.** For each field in `{sandbox_run_id, started_at, attempt_id, prev_hash, outcome.summary, type}`, the test writes 3 valid attempts, mutates one byte in field-`X` of row 2, runs `attempts()`, asserts `AuditChainCorrupted` is raised with `.attempt_id == 2`. Catches a regression where the walker only re-canonicalizes a subset of fields.
- [ ] **AC-AT-2 — `AuditChainCorrupted` exposes structured attributes.** `.attempt_id: int | None` (None when the failing row has no parseable attempt_id), `.row_index: int` (1-based), `.kind: Literal["chain_mismatch", "unknown_type", "extra_field", "schema_error", "manifest_mismatch", "wrong_chain_root", "short_prev_chain_head"]`. `str(exc)` formats as `f"{kind}: attempt_id={attempt_id}, row={row_index}, {message}"`. Tests assert on attributes, not substrings.

### K. fsync verification (structural + perf)

- [ ] **AC-FS-1 — `record` calls `os.fsync` twice per write.** Once on the JSONL file fd, once on the parent directory fd. Verified by `unittest.mock.patch("codegenie.gates.retry_ledger.os.fsync")` — call count is exactly 2 per `record`, with one call's argument being the JSONL fd and the other being the parent-dir fd (assertable via `fd_path = os.readlink(f"/proc/self/fd/{fd}")` on Linux; on macOS the dir-fsync wraps `errno.EINVAL` swallowing per Notes — assert only call count + ordering). Mock-based, NOT timing-based.
- [ ] **AC-FS-2 — `bench`-marked perf gate (`pytest.mark.bench`).** Over 100 records on tmpfs (`/tmp` on Linux CI, `$TMPDIR` on macOS), p95 latency per `record` ≤ 50 ms. Excluded from default `make test` per `pyproject.toml [tool.pytest.ini_options] addopts -m "not bench"`; runs in the weekly perf cron + on-demand via `pytest -m bench`.

### L. Property tests (mutation-witness, not tautology)

- [ ] **AC-PROP-1 — prefix-replay invariance (hypothesis).** For any N ∈ [1, 5] and any sequence of N valid attempts, replaying `attempts.jsonl` truncated to any prefix M ≤ N reproduces the same `chain_hash` for row M as the full-file replay did. Catches off-by-one prev_hash threading.
- [ ] **AC-PROP-2 — payload-permutation witness (hypothesis).** For any two distinct attempts A and B at positions (1, 2), the head after `record(A); record(B)` is **different** from the head after `record(B); record(A)` (with attempt_ids adjusted). Catches a buggy implementation that hashes only the latest payload without prev_hash.
- [ ] **AC-PROP-3 — canonical-bytes determinism (hypothesis).** For any `Attempt`, `_canonical_json(attempt)` is byte-identical across 100 independent calls. Catches accidental dict-ordering drift.

### M. Export, type-strictness, debug, quality gates

- [ ] **AC-EX-1 — `gates/__init__.py` re-exports `RetryLedger`, `AuditChainCorrupted`, `LedgerAttemptOutOfOrder`.** Test: `from codegenie.gates import RetryLedger, AuditChainCorrupted, LedgerAttemptOutOfOrder` succeeds; `RetryLedger.__module__ == "codegenie.gates.retry_ledger"` (i.e., re-export, not relocation).
- [ ] **AC-NT-1 — TDD factory uses newtype constructors.** `AttemptNumber(attempt_id)` and `RunId(f"run-{attempt_id:04d}")` per S1-04 hardening Note #1245 ("tests use the constructor form as intent documentation"). NewType is a type-checker shim at runtime, but the discipline is the contract.
- [ ] **AC-NT-2 — `__repr__` exposes only `gate_id` and `_next_attempt_id`.** `repr(ledger) == f"RetryLedger(gate_id={self.gate_id!r}, next_attempt_id={self._next_attempt_id})"`. Leak-safe for structlog (no raw paths, no chain bytes).
- [ ] **AC-QG-1 — `pytest tests/gates/test_retry_ledger.py tests/gates/test_retry_ledger_resume.py tests/gates/test_retry_ledger_purity.py tests/adversarial/test_audit_chain_tamper.py` all pass.**
- [ ] **AC-QG-2 — `ruff check src/codegenie/gates tests/gates tests/adversarial/test_audit_chain_tamper.py`** clean.
- [ ] **AC-QG-3 — `ruff format --check src/codegenie/gates tests/gates`** clean.
- [ ] **AC-QG-4 — `mypy --strict src/codegenie/gates`** clean.
- [ ] **AC-QG-5 — coverage on `src/codegenie/gates/retry_ledger.py`: ≥ 95% line / ≥ 90% branch** (canonical form, mirrors S1-04 / High-level-impl §Step 2 done-criteria).
- [ ] **AC-QG-6 — TDD plan's red test exists, is committed, and is green.**

## Implementation outline

1. Add `blake3>=0.4` to `pyproject.toml` dependencies and lock.
2. Extend `src/codegenie/gates/errors.py` (from S1-01) with:
   - `AuditChainCorrupted(GatesError)` carrying `.attempt_id: int | None`, `.row_index: int`, `.kind: Literal[...]` (see AC-AT-2 enum).
   - `LedgerAttemptOutOfOrder(GatesError)` carrying `.expected: int`, `.got: int`.
3. Create `src/codegenie/gates/retry_ledger.py` with **module-level pure helpers first** (AC-PH-1):
   - `_canonical_json(attempt: Attempt) -> bytes` — `payload = {"type": "attempt", **attempt.model_dump(mode="json", exclude={"chain_hash"})}`; returns `json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")`.
   - `_compute_chain_hash(prev_hex: str, payload: bytes) -> str` — returns `blake3(bytes.fromhex(prev_hex) + payload).hexdigest(length=16)` (32 hex chars; BLAKE3-128 per S1-04 contract).
   - `_recover_chain_state(jsonl_path: Path) -> tuple[int, str | None]` — reads existing `attempts.jsonl` if present; returns `(next_attempt_id, last_chain_hash)` where `next_attempt_id = max attempt_id over rows with type=="attempt" + 1` (or 1 if file absent/empty) and `last_chain_hash = chain_hash of the file's final line` (or `None`).
4. `class RetryLedger:` accepts `run_dir: Path`, `gate_id: str`, `prev_chain_head: bytes | None` in `__init__`:
   - Validate `prev_chain_head` is None or 16 bytes (AC-H-3).
   - `self._gate_dir = run_dir / "gates" / gate_id`; `self._gate_dir.mkdir(parents=True, exist_ok=True)`.
   - `self._jsonl_path = self._gate_dir / "attempts.jsonl"`; `self._manifest_path = self._gate_dir / "manifest.yaml"`.
   - Manifest handling per AC-MF-1..AC-MF-4: try `open(self._manifest_path, "x")` and write the alphabetized YAML; on `FileExistsError`, read existing, verify `gate_id` and `prev_chain_head` match (raise `AuditChainCorrupted(kind="manifest_mismatch", ...)` on mismatch).
   - Recover state: `self._next_attempt_id, self._last_chain_hash = _recover_chain_state(self._jsonl_path)`.
   - If `prev_chain_head is not None` AND the file is non-empty, read the first row's `prev_hash` and verify it equals `prev_chain_head.hex()` (raise `AuditChainCorrupted(kind="wrong_chain_root", ...)` on mismatch — AC-RR-2).
   - Store `self._prev_chain_head = prev_chain_head`.
5. `record(attempt: Attempt) -> None`:
   - Validate `attempt.attempt_id == self._next_attempt_id` else raise `LedgerAttemptOutOfOrder(expected=..., got=...)` BEFORE any write (AC-OO-1).
   - Compute `prev_hex = self.head().hex()` (32 chars).
   - Compute `chain_hash = _compute_chain_hash(prev_hex, _canonical_json(attempt.model_copy(update={"prev_hash": prev_hex, "chain_hash": "0"*32})))` — caller-supplied values discarded (AC-IG-1).
   - Build the on-disk line: `record = {"type": "attempt", **attempt.model_copy(update={"prev_hash": prev_hex, "chain_hash": chain_hash}).model_dump(mode="json")}`; `line = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"`.
   - Open `self._jsonl_path` in `"ab"` mode; `f.write(line)`; `f.flush()`; `os.fsync(f.fileno())`; close.
   - `dirfd = os.open(self._gate_dir, os.O_RDONLY); try: os.fsync(dirfd) except OSError as e: if e.errno != errno.EINVAL: raise; finally: os.close(dirfd)`.
   - `self._last_chain_hash = chain_hash`; `self._next_attempt_id += 1`.
   - structlog `gates.ledger.attempt_recorded` with `gate_id`, `attempt_id`, `chain_hash[:8]` (8-char prefix only — leak-safe).
6. `head() -> bytes`:
   - If `self._last_chain_hash is not None`: return `bytes.fromhex(self._last_chain_hash)`.
   - Else if `self._prev_chain_head is not None`: return `self._prev_chain_head`.
   - Else: return `b"\x00" * 16`.
7. `attempts() -> list[Attempt]`:
   - If file absent or empty: return `[]`.
   - For each line, parse JSON; pop `"type"`; if missing or `!= "attempt"`: continue (this story ships only the attempt-filter — see AC-T-2; future row types lift to `entries()` in S2-02).
   - Validate as `Attempt` (S1-04's `extra="forbid"` catches unknown fields — `ValidationError` re-raises as `AuditChainCorrupted(kind="extra_field", ...)` per AC-EF-1).
   - Recompute `chain_hash` over `_canonical_json(parsed_attempt.model_copy(update={"chain_hash": "0"*32}))` chained from previous row's `chain_hash` (or `prev_chain_head.hex()` if first row); compare to on-disk value; mismatch → `AuditChainCorrupted(kind="chain_mismatch", attempt_id=..., row_index=...)`.
   - structlog `gates.ledger.replay_failed` on any raise.
   - Return list of validated `Attempt` instances.
8. The chain-head check against `.codegenie/remediation/<run-id>/chain_head.bin` is S2-03 — this story neither reads nor writes that file.
9. The `record_pre_execute` method, the `entries()` reader, and the `LedgerEntry` discriminated union are S2-02 — they land additively because (a) the `"type"` discriminator is already on disk after S2-01 and (b) the three pure helpers in step 3 are module-level and importable.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/gates/test_retry_ledger.py`

```python
# tests/gates/test_retry_ledger.py
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from codegenie.gates.contract import Attempt, GateOutcome
from codegenie.gates.errors import AuditChainCorrupted, LedgerAttemptOutOfOrder
from codegenie.gates.retry_ledger import RetryLedger
from codegenie.sandbox.signals.models import ObjectiveSignals
from codegenie.types.identifiers import AttemptNumber, RunId


ZERO_16 = "0" * 32  # BLAKE3-128 sentinel as hex (16 bytes -> 32 hex chars; AC-H-1)


def _make_attempt(
    attempt_id: int,
    *,
    prev_hash: str = ZERO_16,
    chain_hash: str = ZERO_16,
) -> Attempt:
    """Factory uses newtype constructors per S1-04 Notes (AC-NT-1).

    Caller-supplied `prev_hash` / `chain_hash` are placeholders; `RetryLedger.record`
    overwrites them per AC-IG-1.
    """
    now = datetime.now(timezone.utc)
    return Attempt(
        attempt_id=AttemptNumber(attempt_id),
        sandbox_run_id=RunId(f"run-{attempt_id:04d}"),
        signals=ObjectiveSignals(),
        outcome=GateOutcome(
            passed=False, attempt=AttemptNumber(attempt_id), failing_signals=[],
            retryable=True, state="failed_retryable", summary="",
            signals=ObjectiveSignals(),
        ),
        started_at=now,
        ended_at=now,
        prev_hash=prev_hash,
        chain_hash=chain_hash,
    )


def test_record_appends_typed_chained_line_with_blake3_128(tmp_path: Path) -> None:
    """AC-H-1, AC-H-4, AC-T-1, AC-T-3, AC-IG-1."""
    ledger = RetryLedger(run_dir=tmp_path, gate_id="stage6_validate", prev_chain_head=None)
    ledger.record(_make_attempt(1))

    jsonl = tmp_path / "gates" / "stage6_validate" / "attempts.jsonl"
    assert jsonl.exists(), "attempts.jsonl must be created"
    lines = jsonl.read_text().splitlines()
    assert len(lines) == 1, "exactly one line per record call"

    payload = json.loads(lines[0])
    assert payload["type"] == "attempt", "AC-T-1: type discriminator at JSONL layer"
    assert payload["attempt_id"] == 1
    assert re.fullmatch(r"[0-9a-f]{32}", payload["chain_hash"]), \
        "AC-H-1: chain_hash is 32 lowercase hex chars (BLAKE3-128)"
    assert payload["prev_hash"] == ZERO_16, "AC-H-4: first record's prev_hash is the zero-16 sentinel"
    assert payload["chain_hash"] != payload["prev_hash"], "chain is derived from prev + payload"


def test_record_overrides_caller_supplied_chain_fields(tmp_path: Path) -> None:
    """AC-IG-1, AC-IG-2: caller-supplied prev_hash/chain_hash are placeholders."""
    ledger = RetryLedger(run_dir=tmp_path, gate_id="g", prev_chain_head=None)
    ledger.record(_make_attempt(1, prev_hash="f" * 32, chain_hash="e" * 32))
    ledger.record(_make_attempt(2, prev_hash="d" * 32, chain_hash="c" * 32))

    # Caller's intentionally-wrong values were replaced; chain still verifies.
    assert [a.attempt_id for a in ledger.attempts()] == [1, 2]
    line1 = json.loads(
        (tmp_path / "gates" / "g" / "attempts.jsonl").read_text().splitlines()[0]
    )
    assert line1["prev_hash"] == ZERO_16, "ledger overrode caller's 'ff..ff'"


@pytest.mark.parametrize(
    "field_to_tamper, old_value, new_value",
    [
        ("sandbox_run_id", "run-0002", "run-XXXX"),
        ("type", "attempt", "attempt_v2"),
        ("prev_hash", None, None),  # special: see body
    ],
)
def test_tamper_on_any_field_is_detected(
    tmp_path: Path, field_to_tamper: str, old_value: str | None, new_value: str | None
) -> None:
    """AC-AT-1, AC-AT-2, AC-T-3."""
    ledger = RetryLedger(run_dir=tmp_path, gate_id="g", prev_chain_head=None)
    ledger.record(_make_attempt(1))
    ledger.record(_make_attempt(2))

    jsonl = tmp_path / "gates" / "g" / "attempts.jsonl"
    lines = jsonl.read_text().splitlines()
    row2 = json.loads(lines[1])
    if field_to_tamper == "prev_hash":
        row2["prev_hash"] = "f" * 32
    elif field_to_tamper == "type":
        row2["type"] = "attempt_v2"
    else:
        row2[field_to_tamper] = new_value
    lines[1] = json.dumps(row2, sort_keys=True, separators=(",", ":"))
    jsonl.write_text("\n".join(lines) + "\n")

    with pytest.raises(AuditChainCorrupted) as excinfo:
        ledger.attempts()
    exc = excinfo.value
    assert exc.row_index == 2, "AC-AT-2: structured row_index attribute"
    # attempt_id may be None for type-discriminator tampers; assert presence path coverage.
    assert exc.kind in {"chain_mismatch", "unknown_type", "extra_field", "schema_error"}


def test_record_rejects_out_of_order_attempt_id_before_writing(tmp_path: Path) -> None:
    """AC-OO-1, AC-OO-2."""
    ledger = RetryLedger(run_dir=tmp_path, gate_id="g", prev_chain_head=None)
    ledger.record(_make_attempt(1))

    with pytest.raises(LedgerAttemptOutOfOrder) as excinfo:
        ledger.record(_make_attempt(1))
    assert excinfo.value.expected == 2 and excinfo.value.got == 1

    jsonl = tmp_path / "gates" / "g" / "attempts.jsonl"
    assert len(jsonl.read_text().splitlines()) == 1, "rejected record must not append"


def test_extra_field_on_attempt_row_raises_audit_chain_corrupted(tmp_path: Path) -> None:
    """AC-EF-1: replay enforces extra=forbid-style strictness per ADR-0014."""
    ledger = RetryLedger(run_dir=tmp_path, gate_id="g", prev_chain_head=None)
    ledger.record(_make_attempt(1))

    jsonl = tmp_path / "gates" / "g" / "attempts.jsonl"
    row = json.loads(jsonl.read_text().splitlines()[0])
    row["rogue_field"] = "x"
    jsonl.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    with pytest.raises(AuditChainCorrupted) as exc:
        ledger.attempts()
    assert exc.value.kind in {"extra_field", "schema_error"}
```

Additional test files (per Files-to-touch):

- `tests/gates/test_retry_ledger_resume.py` — covers AC-RR-1..AC-RR-4: write 2 attempts in one ledger instance, discard, open a second `RetryLedger(...)` over the same gate-dir, assert `head()` matches, assert `record(attempt_id=3)` succeeds, assert `record(attempt_id=1)` raises `LedgerAttemptOutOfOrder(expected=3, got=1)`. Also covers AC-MF-3/MF-4: manifest matching → no rewrite (compare `created_at` byte-equality); manifest mismatching `prev_chain_head` → `AuditChainCorrupted(kind="manifest_mismatch")`.
- `tests/gates/test_retry_ledger_purity.py` — AST-walks `src/codegenie/gates/retry_ledger.py`: asserts `_canonical_json`, `_compute_chain_hash`, `_recover_chain_state` are at `ast.Module` top level (not nested in a `ClassDef`); asserts imports are a subset of the allowlist (AC-PH-1, AC-PH-2). Mirrors S1-02..S1-07 module-purity pattern.
- `tests/gates/test_retry_ledger_properties.py` — Hypothesis-driven properties AC-PROP-1..AC-PROP-3: prefix-replay invariance, payload-permutation witness, canonical-bytes determinism.
- `tests/gates/test_retry_ledger_fsync.py` — AC-FS-1 (mocked `os.fsync` call count = 2 per `record`, ordering = file fd then dir fd). AC-FS-2 lives in a separate `tests/perf/test_retry_ledger_perf.py` marked `pytest.mark.bench`.
- `tests/adversarial/test_audit_chain_tamper.py` — wider tamper parametrization than the unit test, including byte-level mutation (not just JSON-field swap), and the `outcome.summary` nested-field tamper.

### Green — make it pass

Smallest implementation per Implementation outline §3–§7: module-level `_canonical_json` / `_compute_chain_hash` / `_recover_chain_state` first, then `RetryLedger.__init__` (validate `prev_chain_head` byte length, create `_gate_dir`, manifest first-write or match-or-raise, recover state from existing JSONL, verify recovered chain root against `prev_chain_head`); `record` (validate `_next_attempt_id`, override caller hashes via `model_copy`, compute chain, atomic-append + fsync(file fd) + fsync(dir fd), update in-memory state, emit structlog); `head` (3-branch return per AC-H-4); `attempts` (line-by-line, drop `"type"`, validate, recompute chain, raise `AuditChainCorrupted` with structured attributes).

### Refactor — clean up

- Add type hints for every method; `from __future__ import annotations` first line.
- Docstrings citing ADR-0005 (chain extension) and ADR-0007 (forward-compat seam for pre_execute marker) and ADR-0011 (no double-write on duplicate attempt_id).
- Verify the three pure helpers (`_canonical_json`, `_compute_chain_hash`, `_recover_chain_state`) are at module top-level — `tests/gates/test_retry_ledger_purity.py` enforces.
- Replace any `print` (none expected) with structlog `gates.ledger.attempt_recorded` / `gates.ledger.replay_failed` event names from S1-01's event-constants module.
- Edge cases handled in tests: missing `_gate_dir` (mkdir parents=True), empty `attempts.jsonl` (treat as no records, not error — AC-RR-3), trailing newline tolerance (split-and-strip), UTF-8 decode error → `AuditChainCorrupted(kind="schema_error")`.
- `__repr__` exposes only `gate_id` and `_next_attempt_id` (AC-NT-2) — leak-safe for structlog.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/gates/retry_ledger.py` | New module — `RetryLedger` class + 3 module-level pure helpers. |
| `src/codegenie/gates/errors.py` | Add `AuditChainCorrupted(GatesError)` (with `.attempt_id`, `.row_index`, `.kind`) and `LedgerAttemptOutOfOrder(GatesError)` (with `.expected`, `.got`). |
| `src/codegenie/gates/__init__.py` | Re-export `RetryLedger`, `AuditChainCorrupted`, `LedgerAttemptOutOfOrder` at package surface (AC-EX-1). |
| `tests/gates/test_retry_ledger.py` | Core red + write + replay + tamper + extra-field + out-of-order + caller-override tests. |
| `tests/gates/test_retry_ledger_resume.py` | AC-RR-1..AC-RR-4 + AC-MF-3 / AC-MF-4 (manifest mismatch). |
| `tests/gates/test_retry_ledger_purity.py` | AST-walks `retry_ledger.py` — pure helpers at module top level + import allowlist (AC-PH-1, AC-PH-2). Mirrors S1-02..S1-07. |
| `tests/gates/test_retry_ledger_properties.py` | Hypothesis properties AC-PROP-1..AC-PROP-3. |
| `tests/gates/test_retry_ledger_fsync.py` | AC-FS-1 — `unittest.mock.patch("codegenie.gates.retry_ledger.os.fsync")` call-count + ordering. |
| `tests/perf/test_retry_ledger_perf.py` | AC-FS-2 — `pytest.mark.bench` p95 latency on tmpfs. |
| `tests/adversarial/test_audit_chain_tamper.py` | Wider byte-level tamper parametrization including nested-field mutation. |
| `tests/gates/conftest.py` | Shared `_make_attempt` factory using `AttemptNumber` / `RunId` constructors. |
| `pyproject.toml` | Add `blake3 >= 0.4` dependency. |

## Out of scope

- `record_pre_execute(attempt_id, sandbox_spec_hash)` — S2-02 (lands additively because S2-01 already writes the `"type"` discriminator at the JSONL layer; S2-02 must NOT add a `type` field to the `Attempt` Pydantic model — that would edit S1-04's frozen contract).
- `entries() -> list[LedgerEntry]` discriminated-union read API — S2-02 (this story ships `attempts()` filtered to `type == "attempt"` only).
- `LedgerEntry = PreExecuteMarker | Attempt` discriminated union — S2-02.
- Phase 4 chain-head compatibility startup check (read `.codegenie/remediation/<run-id>/chain_head.bin`, byte-compare against `prev_chain_head`) — S2-03 (this story accepts `prev_chain_head: bytes | None` and uses it to verify the recovered chain root, but does not read the on-disk Phase 4 file).
- `codegenie sandbox inspect` CLI surface — S8-01.
- Concurrent-writer locking via `fcntl.flock` on `attempts.jsonl` — S7-04 (the ledger is single-writer by `GateRunner` design).

## Notes for the implementer

### BLAKE3-128 hash size (S1-04 contract)

- `blake3` library default `.hexdigest()` returns 64 hex chars (256-bit / 32-byte). S1-04 HARDENED requires `Attempt.{prev,chain}_hash` to be 32 hex chars (BLAKE3-128 / 16-byte) — validator `^[0-9a-f]{32}$`. **Always call `.hexdigest(length=16)`**; the default would fail `Attempt` construction at `field_validator(mode="after")`.
- Same for raw bytes: `blake3(prev_bytes + payload).digest(length=16)`. `prev_chain_head: bytes | None` is 16 bytes when non-None (AC-H-3 validates).
- The codebase's `src/codegenie/hashing.py` uses full 256-bit BLAKE3 for the cache layer (`blake3:<64-hex>` prefix). The ledger is the divergent layer — smaller JSONL rows. Document the divergence in `retry_ledger.py` module docstring.

### Type discriminator at the JSONL layer (Extension by addition)

- Do NOT add a `type: Literal["attempt"]` field to `Attempt` in `gates/contract.py` — that's S1-04's frozen contract. Inject `"type": "attempt"` at write-time inside `_canonical_json`; strip it at read-time inside `attempts()` before validating as `Attempt`. This keeps S1-04 frozen and lets S2-02 add `{"type": "pre_execute", ...}` rows purely additively.
- Replay's `extra="forbid"`-style strictness (AC-EF-1) mirrors ADR-0014's `ObjectiveSignals` discipline. An unknown JSON field on an `"attempt"` row → `AuditChainCorrupted(kind="extra_field")`. Mutation-resistance against tomorrow's silent field drift.

### Canonical-JSON boundary

- The on-disk JSONL line is the JSON dump of `{**canonical_payload_without_chain_hash, "chain_hash": <computed>}` (one pass, sorted keys). The chain_hash itself is computed over `_canonical_json(attempt)` which EXCLUDES the `chain_hash` field via `model_dump(mode="json", exclude={"chain_hash"})`. Replay does the same: parse, drop `chain_hash`, re-canonicalize via the helper, recompute, byte-compare.
- `Attempt.model_dump(mode="json")` is **required** (not `model_dump()`) so `datetime` becomes ISO-8601 string and `AttemptNumber`/`RunId` newtypes serialize to their underlying primitives — otherwise canonical JSON varies.

### Resume-on-reopen (Phase 6 contract)

- `__init__` is the load-bearing recovery path. The Phase 6 LangGraph checkpointer will lift `attempts.jsonl` unchanged (arch §236). A second `RetryLedger(...)` over the same gate-dir MUST recover `_next_attempt_id` and `_last_chain_hash` from disk; otherwise the second instance silently restarts the chain and either (a) raises out-of-order on the next legitimate record (good) or (b) succeeds with `attempt_id=1` and produces a duplicate row (silent corruption). The helper `_recover_chain_state` is the single point of recovery — kept pure so it's reusable from S2-02's `entries()` reader.

### fsync discipline

- `os.fsync` on the directory fd matters on Linux (ext4) but is a no-op on macOS / non-POSIX FS — call it unconditionally and swallow `OSError` only when `errno == errno.EINVAL`. AC-FS-1 verifies via mock; AC-FS-2 verifies real-disk latency under `pytest.mark.bench` (excluded from default `make test`).

### Carryforward flags for follow-up validation

- **S2-02 needs revalidation.** S2-02's draft Implementation outline step 2 edits S1-04's frozen `Attempt` model to add `type: Literal["attempt"] = "attempt"` as the first field. With this story's hardening, that edit is unnecessary and forbidden — the discriminator lives at the JSONL serialization layer. S2-02 must re-shape to: (a) add a `PreExecuteMarker` frozen Pydantic model with `type: Literal["pre_execute"]`; (b) add `record_pre_execute(...)` that injects `"type": "pre_execute"` at write time; (c) add `entries()` that reads each row, dispatches on `"type"`, returns the discriminated union. The S2-01 golden file is **not** regenerated — it never had a `"type"` discriminator removed.
- **S2-03 needs revalidation.** S2-03's draft AC-3 / AC-4 reference "≠ 32 bytes" for `chain_head.bin`. With S1-04's BLAKE3-128 stance honored, the file is 16 bytes; S2-03's "32 bytes" check is wrong. The S2-03 validator pass must amend `len != 32` → `len != 16` and update the golden Phase-4 chain-head fixture accordingly.

### Discipline misc

- Do not import anything from `sandbox/` other than `sandbox.signals.models.ObjectiveSignals` (transitively required by `Attempt.signals` typing) — `gates/` and `sandbox/` are sibling packages; deeper circular imports here will surface later.
- Resist the urge to cache the entire attempts list in memory — replay reads the file. The only cached state is `_last_chain_hash`, `_next_attempt_id`, and `_prev_chain_head`.
- The 16-byte zero `prev_chain_head` (`b"\x00" * 16`) is a *sentinel for the first ledger ever in any environment*; in real runs `prev_chain_head` comes from Phase 4 (S2-03 reads it).
- `LedgerAttemptOutOfOrder` must raise *before* any disk write to preserve the file-is-truth invariant (AC-OO-1).
