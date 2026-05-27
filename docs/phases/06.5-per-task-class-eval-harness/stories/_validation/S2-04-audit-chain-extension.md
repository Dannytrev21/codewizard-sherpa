# Validation report — S2-04 (audit chain extension)

**Validated:** 2026-05-26
**Validator:** scheduled `story-validation-corrector` task
**Story:** `docs/phases/06.5-per-task-class-eval-harness/stories/S2-04-audit-chain-extension.md`
**Verdict:** HARDENED
**Findings:** 18 total — 4 blocks, 11 hardens, 3 nits

## Stage 1 — Context loaded

Read in this order:

- `S2-04-audit-chain-extension.md` (target)
- `phase-arch-design.md` §Component design → `audit.py`, §Edge cases #17, §Idempotence, §Gap 4, §Gap 5
- `final-design.md` §`src/codegenie/eval/audit.py` (noted divergence with arch on `verify` signature — arch wins; recorded as F-CON-5 nit)
- `stories/S1-01-typed-errors-module.md` (HARDENED) — `ChainTamperDetected` marker-only discipline (AC-8)
- `stories/S1-02-wire-models-frozen-extra-forbid.md` (HARDENED) — confirms 5-type wire contract, `_FROZEN_WIRE_TYPES` cardinality test; **`host_fingerprint` is NOT present**
- `stories/S2-03-content-addressed-cache.md` (HARDENED) — `_cache_write_lock` shape, `_atomic_write_bytes` extraction-deferred-to-rule-of-three note
- `src/codegenie/audit.py` (Phase 0) — confirms NO `chain_append` / `chain_verify` primitives are exposed; only `AuditWriter.record` / `verify_runs`
- `src/codegenie/hashing.py` (Phase 0) — confirms `identity_hash(*parts)` exists with boundary-shift-safe composition; `content_hash_bytes` exists; no `chain_identity` 2-arg specialization yet

**Context Brief:**

S2-04 builds a per-host BLAKE3+SHA-256 chain of `BenchRunReport` records under `.codegenie/eval/runs/`. The original story drafted around aspirational Phase 0 helpers (`chain_append` / `chain_verify`) that do not exist in the current `codegenie/audit.py`. It also used kwargs to raise `ChainTamperDetected`, which contradicts hardened S1-01's marker-only discipline. And it required adding `host_fingerprint` to `BenchRunReport`, which is a wire-contract change to hardened S1-02.

Three structural blockers, plus a substantial set of coverage / test-quality / extension-by-addition hardenings.

## Stage 2 — Critic findings

### Coverage critic

| ID | Severity | Finding | Fix |
|---|---|---|---|
| F-COV-1 | harden | No AC pins `fcntl.flock` discipline. Two concurrent processes both pass the prev-hash check and write conflicting records. | New AC-2a (flock-on-`.lock`-sentinel; direct probe). |
| F-COV-2 | harden | No AC for missing `out_dir`. `Path.glob` on missing dir raises. | AC-1 + AC-4 amended (create-on-write at mode `0o700`; verify-on-missing returns empty `VerifyResult`). |
| F-COV-3 | harden | No AC for malformed JSON in a chain record. | AC-4 amended (parse failure → `ok=False, reason="parse_error: ..."`). |
| F-COV-4 | harden | AC-3 names `SHA-256(prev_hash || blake3_content)` without pinning the byte-representation. | AC-3 rewritten + AC-16 added (composition lives in `codegenie.hashing.chain_identity`, reusing the boundary-safe `identity_hash`). |
| F-COV-5 | harden | No AC that the on-disk record's `chain_head` equals the returned hash. | AC-3a added. |
| F-COV-6 | nit | `since` filter semantics undefined. | AC-4a added (inclusive lexicographic; chain-walk crosses filter boundary). |

### Test-Quality critic

| ID | Severity | Finding | Fix |
|---|---|---|---|
| F-TQ-1 | block (helper) | `_make_report()` / `genesis_report()` referenced with `...`; mutation-resistant tests need a real shape. | Pinned in TDD plan; mirrors S1-02's `_make_report` precedent. |
| F-TQ-2 | harden | Original genesis test asserts only `head.startswith("sha256:")` — passes for `def write_run_record(...): return path, "sha256:" + "0"*64`. | Strengthened to recompute the expected head independently via the oracle (`chain_identity(GENESIS_PREV_HASH, content_hash_bytes(canonical_form))`). |
| F-TQ-3 | harden | "Flip one byte in a non-hash field" is ambiguous; could accidentally target `chain_head` and test a different invariant. | AC-7 pins `run_id` as the mutation target with same-length swap to preserve JSON shape. |
| F-TQ-4 | harden | No property test for chain integrity at varying N. | AC-14 added — hypothesis chain over N=1..20 + metamorphic `since`-filter invariant. |
| F-TQ-5 | (merged into F-TQ-4) | metamorphic | included in AC-14. |
| F-TQ-6 | harden | `test_records_are_mode_0600` does not exercise the umask=0o000 failure path. | AC-10 rewritten under `os.umask(0o000)` fixture; AC-11 added (pre-existing dir mode untouched). |
| F-TQ-7 | harden | No mutation test for the atomic-write *failure* path. | AC-12 added (induced `OSError` mid-fsync; prior file byte-identical; no `.tmp` orphan). |

### Consistency critic

| ID | Severity | Finding | Fix |
|---|---|---|---|
| F-CON-1 | **block** | `ChainTamperDetected` per S1-01 AC-8 is a marker-only Exception (no custom `__init__`; `cls.__dict__.keys()` constrained). Story used kwargs and attribute access. | AC-2 / AC-7 / AC-8 rewritten to use positional args (`Exception.__init__` → `.args` tuple). Tests assert `ei.value.args == (...)`. Documented in Notes. |
| F-CON-2 | **block** | `host_fingerprint` on `BenchRunReport` is a wire-contract change to HARDENED S1-02. S1-02 explicitly pins 5 wire types via `_FROZEN_WIRE_TYPES` cardinality test. Cannot silently extend. | Moved to Out of scope with explicit follow-up obligation (Phase 6.5 ADR + S1-02 wire-bump story). AC-9 reduced to documentation-only (module docstring contains `per-host`). |
| F-CON-3 | (folded into F-DP-2) | atomic-write extraction crosses rule of three after S2-03 deferred it | AC-15. |
| F-CON-4 | harden | Concurrent-writer test instructions in Notes (no real threads) contradicted AC wording ("simulated via threading or by...). | AC-8 explicit about thread-free deterministic stale-prev simulation; AC-2a covers the actual race-prevention defense (flock). |
| F-CON-5 | nit | `final-design.md` says `verify(task_class: str, since: datetime | None = None)`; story (and arch) use `verify(out_dir: Path, since: str | None = None)`. | Arch is the canonical source per CLAUDE.md; story follows arch. Final-design divergence recorded; final-design is now stale on this point. No action in this story. |

### Design-Patterns critic

| ID | Severity | Finding | Fix |
|---|---|---|---|
| F-DP-1 | (info) | Free-function module surface for `write_run_record` / `verify` matches S2-03 cache shape — correct (Rule 11). | No action. |
| F-DP-2 | **block** | Refactor step "extract `_atomic_write_json`" is optional; should be AC. S2-03 explicitly deferred to rule of three; S2-04 is the third site. | AC-15 added — `eval/_io.py` is the shared chokepoint; both `cache.py` and `audit.py` consume; fence test pins zero re-implementations. |
| F-DP-3 | (info) | `VerifyResult` flat dataclass — illegal states representable (`ok=True` with `tampered_path != None`). | Surfaced in Notes only; YAGNI for single producer (Rule 2). |
| F-DP-4 | (info) | `_current_head` returns sentinel 2-tuple. | Surfaced in Notes only; trivial today. |
| F-DP-5 | **block** | Chain composition `SHA-256(prev || content)` hardcoded inside `eval/audit.py` would force Phase 9's Temporal-durable event log to copy-paste — extension by editing. | AC-16 added — `codegenie.hashing.chain_identity(prev, content) -> str` as named public primitive; `eval/audit.py` consumes; fence forbids open-coding. |
| F-DP-6 | nit | `"0" * 64` literal scattered. | `GENESIS_PREV_HASH: Final[str]` constant in `codegenie.hashing`; story Notes call it out. |
| F-DP-7 | harden | Story's implementation outline didn't specify the canonical-JSON-with-`chain_head=""`-placeholder ordering needed to make the self-referential hash computable. | AC-3 rewritten with explicit 3-step ordering (placeholder for hashing → hash → repopulate → serialize → write). |

## Stage 3 — Research

Not invoked. No findings tagged `NEEDS RESEARCH`; the canonical patterns (atomic write, flock, BLAKE3+SHA-256 chain identity, hypothesis property test) are all in-repo precedent.

## Stage 4 — Synthesis + edits applied

Conflict resolution: **Consistency wins** in every collision.

- F-CON-1 + (original story's claim that `ChainTamperDetected` carries named attributes) → Consistency wins; positional-args + `.args` tuple discipline applied.
- F-CON-2 + (Coverage instinct to add `host_fingerprint` AC) → Consistency wins; deferred to Out of scope.

Edits applied directly to `S2-04-audit-chain-extension.md`:

- Header — Status `Ready` → `HARDENED`; Depends-on extended to `S1-01, S1-02, S2-03`; ADRs honored line clarified.
- Inserted `Validation notes` block under header with a summary of every change.
- Goal section: left as-is (the goal itself is correct; only the AC formulation needed hardening).
- Acceptance criteria: rewrote 11 ACs (AC-1..AC-9 hardened) and added 9 new ones (AC-2a, AC-3a, AC-4a, AC-10..AC-18). Numbering bumped from 11 unstructured bullets to 18 numbered ACs.
- Implementation outline: rewrote in 7 numbered steps with build order (helpers first, then audit module).
- TDD plan: ~14 named tests with concrete bodies (was 9 sketches with `...`), including the helper `_make_report` shape, a hypothesis chain-integrity property, a flock direct-probe, a failure-path atomic-write test, and a fence test for the shared chokepoint.
- Files to touch: extended from 3 to 6 entries; `models.py` explicitly marked "not touched here" with the deferral rationale.
- Out of scope: extended from 4 to 7 entries; each deferral names the future-story or ADR owner.
- Notes for the implementer: rewrote 8 bullets (was 7), addressing the marker-only Exception, the frozen-Pydantic copy ordering, the flock-not-negotiable, and the rule-of-three extraction rationale.

## Verdict

**HARDENED.** The story now:

- Pins the prev-hash check + `fcntl.flock` as orthogonal defenses (correctness vs atomicity).
- Pins the canonical-JSON-with-placeholder ordering so the self-referential `chain_head` is computable.
- Promotes two cross-cutting kernels (`eval/_io.atomic_write_bytes`, `codegenie.hashing.chain_identity`) so Phase 9's durable workflow can adopt them by addition.
- Uses S1-01's marker-only `ChainTamperDetected` discipline correctly (positional args, `.args` assertions).
- Defers `host_fingerprint` cleanly with a named follow-up path instead of silently editing a HARDENED dependency.
- Has mutation-resistant red tests with independent oracles for the genesis chain head, named field targets for tamper-byte-flips, and a hypothesis property over chain length.

Ready for `phase-story-executor`.
