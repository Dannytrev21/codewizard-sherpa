# Validation report — S6-01 Two-stream `EventLog` with BLAKE3-chained spanning stream

**Validated:** 2026-05-19
**Validator:** phase-story-validator skill (autonomous run via story-validation-corrector scheduled task)
**Verdict:** **HARDENED**
**Story file:** `docs/phases/03-vuln-deterministic-recipe/stories/S6-01-two-stream-event-log.md`

---

## Context brief

S6-01 introduces `src/codegenie/plugins/events.py` — the two-stream `EventLog` mandated by phase ADR-0005 (which aligns the local POC's persistence with production ADR-0034's hybrid event-sourcing backend). It is **load-bearing for every other Step-6 story** (S6-02 constructor-injects it, S6-03 emits through it, S6-04 owns its lifecycle, S6-05 walks the BLAKE3 chain via `codegenie audit verify`, S6-06 freezes its public surface). The on-disk contract (paths `.codegenie/events/workflow-internal/<workflow_id>.jsonl.zst` + `.codegenie/events/spanning/append.jsonl.zst`) is itself a stable contract per ADR-0005 §Consequences.

The story claims it "lifts Phase 0's `chain_append` / `chain_verify` primitive from `src/codegenie/audit.py`." Reading `src/codegenie/audit.py` shows there is **no such primitive** — Phase 0's audit module is a per-blob SHA-256 record writer with no chain. The reference is wrong; the chain shape introduced here is the first instance and is what S6-05 will walk.

The story prescribes:

- Two emission methods (`emit_internal`, `emit_spanning`), two Pydantic discriminated unions, on-disk `jsonl.zst` for both streams.
- BLAKE3 chain + `fcntl.flock(LOCK_EX)` on the spanning stream.
- `replay()` yields events from both streams in `(timestamp, event_id)` order.
- `flush()` `fsync`s both file descriptors and is idempotent.

**Load-bearing context the validator pulled in:**

- `../phase-arch-design.md §Component design C9` (L637-665) — public interface, both stream paths, fsync semantics.
- `../phase-arch-design.md §Data model` (L846-875) — both Pydantic discriminated-union shapes; the `event_type` Literal lists; arch line 872 already enumerates **9** spanning variants (including the S3-05 additive `cache_gc_completed`).
- `../ADRs/0005-two-stream-event-log-per-adr-0034.md` §Decision, §Consequences, §Reversibility.
- `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — the BLAKE3 chain is tamper-*evident* not tamper-*proof*.
- `../ADRs/0001-ship-phase5-contract-surface-by-name.md` §Consequences — `TrustScorer.__init__(event_log)` is the constructor-injection contract.
- `src/codegenie/audit.py` — the actual Phase 0 audit module: it is NOT a chain writer; it has no `chain_append` / `chain_verify` functions; it uses `identity_hash_bytes` (SHA-256) for blob anchors and YAML anchors. The S6-01 chain is a **new** primitive.
- `src/codegenie/hashing.py` — the chokepoint required by Phase 0 ADR-0001: every BLAKE3 / SHA-256 call routes through `content_hash_bytes` / `identity_hash_bytes`; the module docstring forbids direct `from blake3 import blake3` outside this file.
- `src/codegenie/plugins/cache_gc.py` and `src/codegenie/cli.py:925-967` — S3-05 already ships `CacheGcCompletedEvent` as a standalone Pydantic class. The S3-05 CLI emits it to `.codegenie/events/spanning/append.jsonl` (uncompressed, no chain) as an **interim wire format** explicitly slated for S6-01 absorption (story S3-05 line 110 + cli.py:933-936 docstring).
- `src/codegenie/transforms/outcomes.py` and `src/codegenie/plugins/{bundle,manifest,resolver,errors}.py` — every existing discriminated union in the codebase uses `Annotated[A | B | …, Field(discriminator="kind")]`. The story uses `Discriminator("event_type")` (Pydantic 2.5+ alternate import). The discriminator field name `event_type` is correct (arch §Data model line 852/868), but the API call (`Field` vs. `Discriminator`) drifts from the established codebase convention.
- `pyproject.toml` `[project].dependencies` — lists `blake3`, but **does NOT list `zstandard`**. The story claims "both should be present from Phase 0 — verify with `grep`"; verification fails.
- `pyproject.toml` `[tool.importlinter.contracts]` — `codegenie.plugins` must not import LLM SDKs (Phase 3 fence). No impact on this story but the fence test must stay green.
- `docs/phases/03-vuln-deterministic-recipe/stories/_validation/S5-01-recipe-registry.md` and `_validation/S5-05-remediation-report-writer.md` — sibling-story validation precedent for: (a) demanding actual codebase API verification before merging; (b) requiring functional-core / imperative-shell split; (c) flagging discriminated-union drift; (d) flagging missing chokepoint discipline.
- `docs/phases/03-vuln-deterministic-recipe/stories/S3-05-bundle-cache-gc.md` AC-23 — already amended the arch to land `"cache_gc_completed"` on the spanning stream; **S6-01 must include this variant or contradict the arch as already amended**.

**Sibling-family lineage.** This is the **first** instance of a BLAKE3-chained on-disk artifact in the codebase. There is no existing kernel to consume; the chain primitive introduced here is itself the new kernel that S6-05's `codegenie audit verify` extension will walk. Three-of-a-kind threshold not yet reached (1st chain primitive); kernel extract not mandatory.

---

## Critic findings

### Coverage critic — `block` / `harden`

- **C-1 (block).** Story names **8** spanning variants. Arch line 872 (as amended by S3-05 AC-23) names **9** — `cache_gc_completed` is the additive 9th. S3-05 has already shipped this variant as `CacheGcCompletedEvent` in `src/codegenie/plugins/cache_gc.py`. Omitting it here contradicts the arch as already amended and leaves a runtime hole (the CLI in cli.py:925-967 emits this event today). Fix: include `CacheGcCompleted` as the 9th spanning variant; **import the existing `CacheGcCompletedEvent` class** from `codegenie.plugins.cache_gc` rather than redefining (Rule 3 — surgical).
- **C-2 (block).** Missing AC: **interim-wire-format migration.** S3-05 emits `CacheGcCompletedEvent` to `.codegenie/events/spanning/append.jsonl` (uncompressed, no chain). cli.py:933-936 docstring explicitly says "interim wire format — S6-01 absorbs this additively into the chained zstd file." S6-01 must either:
  - (a) migrate the CLI emit-site to `EventLog.emit_spanning(...)` (additive edit to `cli.py:cache_prune`), OR
  - (b) ship a one-time migrator that absorbs `.jsonl` into `.jsonl.zst` (preserves chain integrity), OR
  - (c) explicitly out-of-scope and let `codegenie audit verify` handle both formats.
  Without an explicit choice, S6-05 has to invent the migration. Recommend (a) — single-line CLI edit, mirrors how S6-04 will construct an `EventLog` instead of hand-writing to the file.
- **C-3 (block).** Missing AC: **hashing chokepoint discipline (ADR-0001).** The story prescribes `BLAKE3(prior_chain_head || canonical_json(event - {prev_hash}))` but says nothing about routing through `codegenie.hashing.content_hash_bytes`. A direct `from blake3 import blake3` import is a chokepoint violation; the audit module's docstring (`src/codegenie/audit.py:25-29`) forbids this pattern repo-wide. Fix: AC mandating that `events.py` does not import `blake3` directly; the chain step routes through `codegenie.hashing.content_hash_bytes` (whose `blake3:<hex>` prefix gets stripped to populate the un-prefixed 64-hex `BlobDigest`).
- **C-4 (block).** Missing AC: **`zstandard` dependency landed.** Story claims it's already in `pyproject.toml` from Phase 0; it is not. Adding a runtime dependency is itself an AC: update `[project].dependencies` AND verify the Phase 3 import-linter contract still passes (`zstandard` is not in `FORBIDDEN_LLM_SDKS`, so the fence is unaffected, but the addition must be explicit not implicit).
- **C-5 (harden).** Missing AC: **genesis prev_hash.** Refactor §3 calls it out but no AC pins it. Genesis = `"0" * 64`; the first `emit_spanning` on an empty file uses this; round-trips through `replay`.
- **C-6 (harden).** Missing AC: **resume across process restart.** Closing and reopening `EventLog` on the same `root` must rehydrate `_chain_head` from the spanning file's tail — otherwise the second process emits a broken chain starting from genesis. The `__init__` says "Reads spanning-stream tail to compute `_chain_head`" but no AC verifies it.
- **C-7 (harden).** Missing AC: **empty-stream replay.** `replay()` on a never-written `EventLog` yields zero events without raising. This is the common case for S6-02's TrustScorer when no `AdapterDegraded` events have been emitted.
- **C-8 (harden).** Missing AC: **torn-write recovery / `EventLogCorrupted` on truncated trailing record.** Crash mid-write leaves a partial zstd frame; `replay()` must surface this as `EventLogCorrupted(path, line_number, reason="truncated_frame")` rather than silently truncating. The story names the exception but tests no failure mode.
- **C-9 (harden).** Missing AC: **`flush()` ordering + idempotency proof.** Story says "safe to call multiple times; idempotent" but no test pins it. Add: calling `flush()` twice in a row produces no observable change; calling `flush()` on a never-emitted `EventLog` is a no-op.
- **C-10 (harden).** Missing AC: **`fcntl.flock` blocks inside `asyncio.to_thread` only.** S6-04's orchestrator runs under `asyncio`; a synchronous `LOCK_EX` would block the event loop. Implementer notes mention `asyncio.to_thread` but no AC pins the contract. Fix: AC stating `emit_spanning` is **synchronous** (caller wraps in `asyncio.to_thread` per the orchestrator's existing `SubprocessJail.run` pattern); document at the module level.
- **C-11 (harden).** Missing AC: **clock injection.** Implementer notes (line 231) prefer DI over `freezegun`. Promote to AC: `EventLog.__init__(self, root, workflow_id, *, clock: Callable[[], datetime] | None = None)` — default `lambda: datetime.now(UTC)`; tests inject a frozen clock for deterministic `(timestamp, event_id)` round-trips.
- **C-12 (harden).** Missing AC: **payload-typed variants, not free-form `payload: dict`.** Arch §Data model line 859 says `payload: dict[str, str | int | bool | float | list[str]]` on the umbrella; the story's Implementation outline correctly uses **typed payload fields per variant** (e.g., `PluginResolved.plugin_id: PluginId`). This is a deliberate departure (more strictness than the arch snippet). Pin it as an AC + note in the implementer section that the arch snippet is the **lower-bound** contract.
- **C-13 (nit).** Missing AC: **EventId / WorkflowId format note.** Both are `NewType("...", str)` with no runtime validation. The story uses `EventId("01H...01")` in tests — those aren't valid ULIDs, but the newtypes won't catch it. Either generate via `ulid-py` (out of scope) or note explicitly that ULID-shape validation is producer-side discipline + mypy-strict only.

### Test-quality critic — `block` / `harden`

- **T-1 (block).** Three of the six top-level tests in the TDD-plan snippet are **`...` stubs** (`test_cross_process_flock_keeps_chain_intact`, `test_replay_round_trip_byte_equal_modulo_timestamps`, `_flip_one_payload_byte`). Executor will collect these as no-ops if not filled in. Fill them in or move them to the refactor section with concrete pseudocode.
- **T-2 (block).** `_flip_one_payload_byte` helper is named but not defined — the executor will write a `pass` body and the test passes trivially. Specify the helper: read the zstd frame, decompress, flip one byte in the body, recompress, write back; the next `replay()` must raise `ChainTamperDetected`. **Without this, the tamper test is a tautology.**
- **T-3 (block).** Mutation thinking — a wrong implementation that **never writes `prev_hash` at all** (always leaves it `"0" * 64`) would still verify because `recompute(genesis) == genesis` is true. Add a test that asserts **distinct events have distinct `prev_hash`** (`event_N.prev_hash != event_{N-1}.prev_hash` for N > 1). Add a metamorphic test: emitting the same event twice yields **different** `prev_hash` (because the prior head differs).
- **T-4 (harden).** Missing test: **resume-after-close.** Close `EventLog`; reopen with same `root + workflow_id`; emit one more spanning event; verify the chain is intact (the new event's `prev_hash` matches the previously-on-disk `_chain_head`). Without this, the "re-read tail under lock" line in Implementation outline §emit_spanning is untested.
- **T-5 (harden).** Missing test: **empty-stream replay** — `EventLog(tmp_path, _wf()).replay()` returns an empty iterator (no exception) before any emit.
- **T-6 (harden).** Cross-process flock test: must spawn **real subprocesses** (`multiprocessing.Process` with `set_start_method("spawn")` for macOS) — not threads. Threads inherit the same fd; they will not contend on `flock`. The test must use `multiprocessing` and a `tmp_path` shared via the `root` argument. Verify chain integrity by independent walker (not via `EventLog.replay()` of one of the processes — the in-process `_chain_head` is per-process; the walker is the true verifier).
- **T-7 (harden).** Missing property-based test: write `N ∈ [0, 100]` events; `replay()` returns exactly N events in `(timestamp, event_id)` order; recomputing the chain yields the on-disk values byte-for-byte. Use `hypothesis` if installed; otherwise a parametrized loop over `N ∈ {0, 1, 2, 10, 100}`.
- **T-8 (harden).** Missing test: **chokepoint discipline.** AST-fence test (similar to `tests/fence/test_audit_module_has_no_hashlib_or_blake3_imports`): `tests/fence/test_events_module_routes_hashing_through_codegenie_hashing.py` — parses `src/codegenie/plugins/events.py` and asserts no `import blake3` / no `from blake3 import …`. Mirrors the existing audit-module precedent.
- **T-9 (harden).** Missing test: **interim-wire-format migration.** If the chosen migration strategy is (a) edit `cli.py:cache_prune` to use `EventLog.emit_spanning`: add an integration test that `codegenie cache prune` against a populated cache emits one zstd-chained `CacheGcCompleted` spanning event whose `prev_hash` is genesis (first emit) or the prior chain head (subsequent emit).
- **T-10 (nit).** `test_event_payloads_have_no_dict_any` walks `ast.Name` for `"Any"` — but `dict[str, Any]` is an `ast.Subscript` with the inner `Any` as `ast.Name`. Test as written catches it, but should also reject `ast.Attribute` like `typing.Any`. Strengthen to walk both forms.

### Consistency critic — `block` / `harden`

- **K-1 (block).** Story says it "lifts Phase 0's `audit_anchor` chain primitive from `src/codegenie/audit.py`." There is no such primitive in `audit.py`. The actual `audit.py` is per-blob SHA-256 anchors + a per-YAML anchor; there is no chain. Reframe the Context section: this story **introduces** the BLAKE3 chain primitive; S6-05 will walk it via an extension to `codegenie audit verify`. Honest framing matters (ADR-0011).
- **K-2 (block).** Story does not include the 9th spanning variant `CacheGcCompleted`. Arch line 872 already includes it as a result of S3-05's additive amendment. The story must either:
  - import the existing `CacheGcCompletedEvent` from `codegenie.plugins.cache_gc` and include it in the union (preserves S3-05's contract), OR
  - declare a 9th variant matching the existing class's fields exactly (duplicates the contract — anti-pattern).
  Recommend the import-and-include path.
- **K-3 (block).** Discriminator API drift. Codebase precedent (every existing union in `transforms/outcomes.py`, `plugins/{bundle,manifest,resolver,errors}.py`) uses `Annotated[A | B | …, Field(discriminator="kind")]`. The story uses `Annotated[…, Discriminator("event_type")]`. Two issues: (a) the discriminator-field-name is `event_type` per arch §Data model — that name is correct for events — but the codebase convention is `kind` everywhere else; (b) the **API** is `Field(discriminator=…)` not `Discriminator(…)`. The field-name choice is the arch's call (events get `event_type`); the API call must follow codebase convention: `Annotated[…, Field(discriminator="event_type")]`.
- **K-4 (block).** ADR-0001 chokepoint discipline (`codegenie.hashing`) — see Coverage C-3.
- **K-5 (harden).** ADR-0011 honest framing — the story's Refactor section §3 already cites it correctly ("tamper-evident, not tamper-proof"). Promote to an AC so the executor's Validator pass catches it ("module docstring states chain is tamper-evident, not tamper-proof").
- **K-6 (harden).** `zstandard` dep (see Coverage C-4). The phase-arch design line 922 says "BLAKE3 chain on the spanning stream is per-emit but amortized"; per-emit zstd compression is the cost. Document the level=3 choice (implementer note line 230) as an AC: `zstandard.ZstdCompressor(level=3)`. Higher levels burn the per-emit budget (>30k events/s per S9-03).
- **K-7 (harden).** Arch §Data model line 859 says `payload: dict[str, …primitives…]` on the umbrella; story's typed-payload-per-variant departs from that. The departure is **correct** (better typing; matches every other discriminated union in the codebase) — but should be explicit in the story Notes-for-implementer + flagged for the S6-06 contract snapshot (the snapshot pins the typed payload, not the dict). The arch snippet is the lower-bound contract; this story tightens it.

### Design-patterns critic — `harden`

- **DP-1 (harden).** **Functional core / imperative shell** is not separated. `emit_spanning` does:
  1. validate the Pydantic model (pure)
  2. acquire `fcntl.flock` (impure)
  3. re-read the on-disk tail to refresh `_chain_head` (impure)
  4. compute `prev_hash = chain_step(prior_head, canonical_json(event - {prev_hash}))` (**pure**)
  5. rewrite event with `prev_hash` (pure)
  6. write zstd-compressed line (impure)
  7. release lock (impure)
  Extract the pure step (4) into a module-level `def _chain_step(prior_head: BlobDigest, event_bytes: bytes) -> BlobDigest`. This is what S6-05's `audit verify` will call from a stateless walker — the same function the writer used, byte-for-byte. The CLAUDE.md "Functional core / imperative shell" commitment is the precedent; `_indexable_files.py` and `audit.py` follow it.
- **DP-2 (harden).** **Canonical JSON helper** should live alongside `codegenie.hashing` or in a new `codegenie.canonical_json` module — NOT inside `events.py`. The function is reusable (any future module that hashes a structured payload needs the same byte-stable representation); colocating it with hashing also keeps the chokepoint discipline visible (`identity_hash_bytes(canonical_json(payload))` is the obvious shape). Defer to a `_lessons.md` candidate or extract here if `parsers/__init__.py` already has a precedent.
- **DP-3 (harden).** **Adapter / port for the on-disk format.** The story hard-codes `zstandard.ZstdCompressor().stream_writer(...)`. If Phase 9 ports to Postgres `bytea`/`jsonb`, the disk-format-vs-protocol coupling is what changes. Keep `EventLog` ignorant of compression: route writes through a small `EventStreamSink` protocol with two implementations (`ZstdAppendingFileSink`, `InMemorySink` for tests). The test fixture stops needing `tmp_path + zstd decompression` and becomes a `dict[Path, list[bytes]]` recording sink. This is the same pattern S5-05's `_serialize(self) -> bytes` extract (per `_validation/S5-05-remediation-report-writer.md` D-5). One sink-implementation-on-day-one is fine (no premature pluggability); the protocol surface is the cheap insurance.
- **DP-4 (harden).** **Smart-constructor for `BlobDigest` genesis.** `BlobDigest("0" * 64)` is bare; a named constant `GENESIS_CHAIN_HEAD: Final[BlobDigest] = BlobDigest("0" * 64)` at module level removes the magic-string. Mirrors the Phase 0 `audit.py` convention where genesis is a single named anchor, not an inline literal.
- **DP-5 (harden).** **Open/Closed across phases.** Adding a new event variant requires editing the discriminated-union line in `events.py`. The story's Notes-for-implementer line 228 explicitly **rejects** a runtime registry (`Literal[...]` + `dict[str, type]`) and argues for the verbose inline list. That's correct — the verbosity IS the contract. But the OCP cliff (editing the union when a new variant arrives) is real; surface it explicitly: "Adding a new event variant is a **two-line edit** — new class + append to the alias. This is not a registry; the verbosity is the typed-payload contract that S6-06's snapshot pins."
- **DP-6 (harden).** **Tagged union exhaustiveness.** Story does not call out `assert_never` discipline at consumer sites. S6-02 will `match` on `AdapterDegraded`; add a Notes line that consumers must use `match`/`assert_never` for exhaustiveness, mirroring the rest of the codebase (`outcomes.py` `match`-on-`.kind`).
- **DP-7 (nit).** **`replay()` cross-stream ordering.** Story says `(timestamp, event_id)` order. For events with identical `timestamp` (frozen-clock tests, replay under freezegun), `event_id` is the tiebreaker — ULID-ordered. Pin the ordering as: stable, deterministic, and Phase 9's projector reproduces the same order. Not a registry concern; a tagged-union/ordering invariant.
- **DP-8 (nit).** **No event variant should embed a `Path`.** Cross-process replay (Phase 9) reads these from a different machine; absolute paths leak host structure (CLAUDE.md §"Absolute-path scrubbing"). All path fields on event variants are `str` (relative-to-jail) or `BranchName` etc. — never `Path`. Add to Notes-for-implementer.

---

## Edits applied to the story file

| Section | Change |
|---|---|
| Header — `Depends on` | Added `S3-05` (existing `CacheGcCompletedEvent` is reused as the 9th spanning variant). |
| Header — `ADRs honored` | Added Phase 0 ADR-0001 (hashing chokepoint discipline) — was implied but un-cited. |
| Context | Removed the false claim that `audit.py` exposes `chain_append` / `chain_verify`. Reframed as: this story introduces the chain primitive; Phase 0's `audit.py` shares the chokepoint discipline (`codegenie.hashing`) but is a flat per-blob anchor writer, not a chain. Added interim-wire-format migration note (S3-05 cli.py:925-967). |
| References | Added pointers to `src/codegenie/plugins/cache_gc.py`, `src/codegenie/cli.py:cache_prune`, the discriminator API precedents under `transforms/outcomes.py` and `plugins/{bundle,manifest,…}.py`, the hashing module, and the audit module's chokepoint docstring. |
| Goal | Said "9 spanning variants" (was "8"); cited the reused `CacheGcCompletedEvent`. Added clock-injection and `EventStreamSink` adapter to the public surface. |
| Acceptance criteria | Added AC-CG (9th spanning variant via re-import), AC-MIG (CLI emit-site migration), AC-CHOKE (hashing chokepoint), AC-DEP (zstandard dependency), AC-GEN (genesis prev_hash), AC-RES (resume across process restart), AC-EMPTY (empty replay), AC-TORN (`EventLogCorrupted` on truncated frame), AC-FLUSH (idempotent flush), AC-ASYNC (synchronous `flock` + caller `asyncio.to_thread`), AC-CLOCK (clock injection), AC-CORE (pure `_chain_step` helper), AC-DISC (discriminator API alignment), AC-HONEST (module-level tamper-evident-not-tamper-proof note), AC-GENESIS-CONST (`GENESIS_CHAIN_HEAD: Final[BlobDigest]`). |
| Implementation outline | Aligned to `Field(discriminator="event_type")`; explicit `from codegenie.hashing import content_hash_bytes`; explicit `from codegenie.plugins.cache_gc import CacheGcCompletedEvent`; extract pure `_chain_step(prior_head, event_bytes) -> BlobDigest`; introduce `EventStreamSink` protocol + `ZstdAppendingFileSink` default. |
| TDD plan | Filled in stub tests; added `_flip_one_payload_byte` concrete pseudocode; added resume-after-close, empty-replay, torn-write, distinct-prev-hash mutation test, hashing-chokepoint AST fence, interim-wire-format-migration integration test. |
| Files to touch | Added `src/codegenie/cli.py` (cache_prune migration), `pyproject.toml` (zstandard dep), `tests/fence/test_events_module_routes_hashing_through_codegenie_hashing.py` (chokepoint fence). |
| Notes for implementer | Added: typed-payload-per-variant is the deliberate tightening over the arch §Data model snippet; `event_type` discriminator field name is correct (matches arch) but the **API call** must be `Field(discriminator="event_type")`; no `Path` in event payloads; consumers must `match`/`assert_never`; `Annotated[..., Field(discriminator=…)]` is the codebase convention. |
| Validation notes block | Added under the story header recording every change. |

---

## Verdict

**HARDENED.** The story's goal aligns with ADR-0005 + arch §C9; the issues are factual (the `chain_append` reference doesn't exist), counting (8 vs 9 spanning variants), convention (discriminator API), missing-edge-case ACs, and stubbed tests — all fixable in place. Executor can proceed with the hardened story.

Conflict resolutions:
- Coverage C-2 (interim wire format) vs. Rule 3 (surgical changes): chose option (a) — single-line CLI edit — because S3-05 explicitly slated this absorption (cli.py:933 docstring is the contract).
- Design DP-3 (`EventStreamSink` protocol) vs. Rule 2 (three similar lines is better than premature abstraction): kept the protocol because the second implementation (`InMemorySink`) is paid for by the tests on day 1 — `tmp_path + zstd-decompress` in every test is the alternative, which is worse. Two consumers on day one; rule-of-three is met by counting tests + production.
- Design DP-2 (canonical-JSON helper extracted to `codegenie.canonical_json`): downgraded to `_lessons.md` candidate — premature abstraction since there's only one consumer today. Re-extract when the second consumer appears.
