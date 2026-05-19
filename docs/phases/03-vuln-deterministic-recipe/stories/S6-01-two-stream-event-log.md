# Story S6-01 — Two-stream `EventLog` with BLAKE3-chained spanning stream

**Step:** Step 6 — RemediationOrchestrator, TrustScorer, two-stream EventLog, SubgraphNode Protocol, end-to-end happy path
**Status:** HARDENED
**Effort:** L
**Depends on:** S2-04, S5-04, S3-05 (S3-05 already shipped `CacheGcCompletedEvent` as the 9th spanning variant; this story re-imports it rather than redefining)
**ADRs honored:** ADR-0005 (two-stream event log per ADR-0034), ADR-0010 (tagged-union outcomes; newtypes), ADR-0011 (honest-framing — chain is tamper-*evident* not tamper-proof), [Phase 0 ADR-0001](../../00-bullet-tracer-foundations/ADRs/0001-cache-content-hash-algorithm.md) (hashing chokepoint — every BLAKE3/SHA-256 call routes through `codegenie.hashing`), [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md)

## Validation notes (2026-05-19 — phase-story-validator)

Hardened against the as-built repo. Original story carried 7 block-level defects:

1. **False reference to `audit.py::chain_append` / `chain_verify`** — those primitives do not exist; Phase 0's `audit.py` is a flat per-blob SHA-256 anchor writer with no chain. Context + References rewritten honestly: this story **introduces** the chain primitive; what it shares with `audit.py` is the chokepoint discipline (everything hashing routes through `codegenie.hashing`).
2. **Missing 9th spanning variant.** Arch §Data model line 872 lists 9 spanning variants — `cache_gc_completed` was added by S3-05 (already GREEN). The story said 8. Fixed: 9, re-importing the existing `CacheGcCompletedEvent` class from `codegenie.plugins.cache_gc`.
3. **Missing interim-wire-format migration.** S3-05's CLI (`codegenie cache prune`, `src/codegenie/cli.py:925-967`) emits to **uncompressed** `.codegenie/events/spanning/append.jsonl`; the docstring there explicitly slates the absorption for S6-01. Added AC-MIG to flip the emit-site to `EventLog.emit_spanning(...)`.
4. **Missing hashing chokepoint AC.** ADR-0001 forbids `from blake3 import blake3` outside `codegenie.hashing`. Original story prescribed `BLAKE3(prior_head || canonical_json(event))` with no chokepoint mention. Added AC-CHOKE + AST-fence test.
5. **`zstandard` claimed already in `pyproject.toml`.** It is not. Added AC-DEP requiring the explicit dependency addition + level=3 compressor choice.
6. **Discriminator API drift from codebase convention.** Story used `Annotated[..., Discriminator("event_type")]`; every existing discriminated union in the codebase (`transforms/outcomes.py`, `plugins/{bundle,manifest,resolver,errors}.py`) uses `Annotated[..., Field(discriminator="…")]`. The discriminator field name `event_type` is correct per arch §Data model; the API call is what was wrong. Fixed to `Field(discriminator="event_type")`.
7. **Three stub tests (`...` and undefined `_flip_one_payload_byte`).** Filled in or moved to concrete pseudocode.

Coverage adds (12): genesis prev_hash, resume across process restart, empty-stream replay, torn-write `EventLogCorrupted`, idempotent `flush()`, synchronous `flock` + `asyncio.to_thread` contract, clock injection, pure `_chain_step` helper, `GENESIS_CHAIN_HEAD` named constant, tamper-evident-not-proof module docstring, typed-payload-per-variant (tightening over arch §Data model `payload: dict` lower bound), no-`Path`-in-payloads.

Design-pattern surfacings (in Notes-for-implementer): functional core / imperative shell (extract pure `_chain_step`); `EventStreamSink` protocol + `ZstdAppendingFileSink` for testability (two consumers on day one — production + tests — meets the rule-of-three when counting test consumers); `match`/`assert_never` exhaustiveness at consumer sites.

Full report: [`_validation/S6-01-two-stream-event-log.md`](_validation/S6-01-two-stream-event-log.md).

## Context

Production ADR-0034 commits to a **hybrid** event-sourcing backend: Phase 9 lands Temporal for workflow-internal history and Postgres for workflow-spanning audit. All three Phase 3 lens designs proposed a single stream and asserted Phase 9 would "lift unchanged" — the critic flagged this as the cardinal blind spot (see `../critique.md §Cross-design observations`). ADR-0005 resolves it by shipping the two-stream split **now**: per-workflow `.codegenie/events/workflow-internal/<workflow_id>.jsonl.zst` (Phase 9 ports to Temporal history) + shared append-only `.codegenie/events/spanning/append.jsonl.zst` (Phase 9 ports to Postgres `events` table). The on-disk locations are themselves a stable contract (ADR-0005 §Consequences).

The spanning stream is BLAKE3-chained for tamper evidence and `fcntl.flock`-protected so that two concurrent `codegenie remediate` invocations cannot interleave writes. The internal stream is per-workflow, so each workflow owns its file — fsync on workflow end is sufficient. Crossing the taxonomy boundary (emitting a workflow-internal variant on the spanning stream or vice versa) is a contract break gated by ADR amendment.

**Honest framing on what's reused vs. introduced.** This story **introduces** the BLAKE3 chain primitive — there is no pre-existing `chain_append` / `chain_verify` in the repo. Phase 0's `src/codegenie/audit.py` is a flat per-blob SHA-256 / per-YAML anchor writer (no chain); what it shares with this module is the **chokepoint discipline** (ADR-0001): every BLAKE3 / SHA-256 call routes through `codegenie.hashing.content_hash_bytes` / `identity_hash_bytes`. Direct `from blake3 import blake3` outside that chokepoint is forbidden repo-wide. S6-05's `codegenie audit verify` extension will walk the chain via the same `_chain_step` pure helper this story exports.

**Interim wire format absorbed.** S3-05 (already GREEN) ships `src/codegenie/plugins/cache_gc.py::CacheGcCompletedEvent` and emits it via the `codegenie cache prune` CLI to **uncompressed** `.codegenie/events/spanning/append.jsonl` — explicitly tagged as an interim wire format awaiting S6-01 absorption (see `src/codegenie/cli.py:933-936` docstring). This story owns the absorption: re-import `CacheGcCompletedEvent` as the 9th spanning variant, and switch the CLI emit-site from hand-rolled `os.write` to `EventLog.emit_spanning(...)`. Arch §Data model line 872 already enumerates `cache_gc_completed` in the spanning Literal (S3-05 AC-23 additive amendment).

This story is **load-bearing for everything else in Step 6**: S6-02 (TrustScorer constructor-injects an `EventLog`), S6-03 (subgraph nodes emit via the `EventLog`), S6-04 (orchestrator constructs and owns the `EventLog` lifecycle), S6-05 (`codegenie audit verify` extends to walk the spanning chain), S6-06 (the contract snapshot freezes `EventLog`'s public surface). It is also the **single most attacked architectural decision in Phase 3** — under-specifying it now means Phase 9's migration becomes a re-taxonomize-the-world effort the architecture spec explicitly rejects.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C9` — `EventLog` public interface, both stream paths, the exhaustive `WorkflowInternalEvent` / `WorkflowSpanningEvent` variant lists, fsync-on-workflow-end + BLAKE3-per-emit semantics.
  - `../phase-arch-design.md §Data model` (lines ~846–874) — Pydantic shapes for both discriminated unions including `event_id: EventId`, `workflow_id: WorkflowId`, `prev_hash: BlobDigest` on spanning events.
  - `../phase-arch-design.md §Design patterns applied` row 6 — "Event sourcing as canonical primitive (two-stream split)" — pattern fit + why.
  - `../phase-arch-design.md §Edge cases E13` — concurrent invocation must be detected via `.codegenie/.lock` flock; spanning-stream `fcntl.flock` is the deeper line of defense if the outer lock is somehow bypassed.
  - `../phase-arch-design.md §Harness engineering — Replay / debuggability` — `codegenie audit verify` extends to the spanning stream; replay produces byte-equal post-state (modulo timestamps + `workflow_id`).
- **Phase ADRs:**
  - `../ADRs/0005-two-stream-event-log-per-adr-0034.md` — the decision document. Read §Decision, §Consequences (esp. "spanning stream is the seed source for Phase 6.5"), §Reversibility.
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — the chain is tamper-*evident* not tamper-*proof*; the BLAKE3 chain catches accidental corruption + post-hoc tampering, not a determined real-time attacker.
  - `../ADRs/0001-ship-phase5-contract-surface-by-name.md` §Consequences — `TrustScorer.__init__(event_log: EventLog)` constructor-injects the log; ambient-state rejected.
- **Production ADRs:**
  - `../../../production/adrs/0034-event-sourcing-canonical-primitive.md` — the hybrid backend ADR-0005 aligns to.
- **Existing code to reuse / mirror (NOT reinvent):**
  - `src/codegenie/hashing.py` — **the mandatory chokepoint** (ADR-0001). All BLAKE3 calls go through `content_hash_bytes` (returns `blake3:<64-hex>` — strip the prefix to populate the un-prefixed 64-hex `BlobDigest`). Direct `import blake3` in `events.py` is forbidden by the chokepoint discipline; an AST-fence test enforces it.
  - `src/codegenie/audit.py` — **NOT** a chain primitive (it is a flat per-blob anchor writer); read the module docstring (lines 1-35) for the chokepoint precedent. The S6-05 `verify_runs` extension this story enables will live alongside `audit.py::verify_runs` but is structurally independent (chain walk vs. blob recomputation).
  - `src/codegenie/plugins/cache_gc.py` — **the 9th spanning variant lives here.** Re-import `CacheGcCompletedEvent` into `events.py`'s `WorkflowSpanningEvent` alias; do not redefine.
  - `src/codegenie/cli.py` (`cache_prune` command, lines ~915-967) — interim emit-site this story migrates to `EventLog.emit_spanning(...)`.
  - `src/codegenie/transforms/outcomes.py` and `src/codegenie/plugins/{bundle,manifest,resolver,errors}.py` — **discriminator-API precedent.** Every existing union uses `Annotated[A | B | …, Field(discriminator="kind")]`. Use `Field(discriminator="event_type")` here (the field name is the events-domain convention from arch §Data model; the call form follows codebase convention).
  - `src/codegenie/types/identifiers.py` (S1-01) — `WorkflowId`, `EventId`, `BlobDigest` newtypes.
- **This phase, parallel stories:**
  - S2-04 — `Resolver` is the producer of `PluginResolved` events; this story provides the writer.
  - S5-04 — `LockfilePolicy` violations become the payload of one of the `WorkflowInternalEvent` variants emitted during Stage 6.
  - S6-02 — `TrustScorer` consumes `EventLog.replay()` to fold `AdapterDegraded` into `TrustOutcome.confidence`.

## Goal

Land `src/codegenie/plugins/events.py` exposing `EventLog(root, workflow_id, *, clock=None, sink=None)` with four methods (`emit_internal`, `emit_spanning`, `replay`, `flush`); two Pydantic discriminated unions — `WorkflowInternalEvent` (16 variants) / `WorkflowSpanningEvent` (**9 variants** — including the existing `CacheGcCompletedEvent` from `codegenie.plugins.cache_gc`); on-disk format `jsonl.zst` per stream; BLAKE3 chain (routed through `codegenie.hashing.content_hash_bytes`) + `fcntl.flock` on the spanning stream; pure `_chain_step(prior_head, event_bytes) -> BlobDigest` helper that the S6-05 walker also consumes; replay produces byte-equal post-state modulo timestamps + `workflow_id`. Also migrate the S3-05 `codegenie cache prune` CLI emit-site to use `EventLog.emit_spanning(...)` so the interim uncompressed `append.jsonl` artifact is retired.

## Acceptance criteria

- [ ] **AC-1.** `src/codegenie/plugins/events.py` exists; `from codegenie.plugins.events import EventLog, WorkflowInternalEvent, WorkflowSpanningEvent, ChainTamperDetected, EventLogCorrupted, GENESIS_CHAIN_HEAD` succeeds.
- [ ] **AC-2.** `EventLog.__init__(self, root: Path, workflow_id: WorkflowId, *, clock: Callable[[], datetime] | None = None, sink: EventStreamSink | None = None) -> None` constructs both directory paths (`<root>/events/workflow-internal/` and `<root>/events/spanning/`) with `parents=True, exist_ok=True`. The `clock` defaults to `lambda: datetime.now(UTC)`. The `sink` defaults to a `ZstdAppendingFileSink(...)`; tests pass an `InMemorySink()` for deterministic byte assertions without round-tripping through zstd.
- [ ] **AC-3.** `emit_internal(event: WorkflowInternalEvent) -> EventId` appends one zstd-compressed JSON line to `<root>/events/workflow-internal/<workflow_id>.jsonl.zst`; returns the minted `EventId` (ULID). No BLAKE3 chain on internal — per-workflow file, fsync on `flush()`.
- [ ] **AC-4.** `emit_spanning(event: WorkflowSpanningEvent) -> EventId` appends one zstd-compressed JSON line to `<root>/events/spanning/append.jsonl.zst` under an exclusive `fcntl.flock(self._spanning_fd, LOCK_EX)`. Under lock the writer re-reads the on-disk chain tail (another process may have appended since the last `emit_spanning`); computes `event.prev_hash = _chain_step(prior_chain_head, canonical_json_bytes(event_without_prev_hash))`; rewrites the event with that `prev_hash`; writes the line; releases the lock; updates the in-process `_chain_head`. Returns the minted `EventId`.
- [ ] **AC-5 (cross-channel rejection).** Calling `emit_internal` with a `WorkflowSpanningEvent` (or vice versa) is a `TypeError` at the type-checker level (mypy `--strict` fails) AND a `ValidationError` at runtime (Pydantic discriminated-union validation rejects).
- [ ] **AC-6 (16 internal variants).** `WorkflowInternalEvent` is a Pydantic discriminated union built as `Annotated[V1 | V2 | …, Field(discriminator="event_type")]` (matches codebase convention from `transforms/outcomes.py` et al.) with **all 16 variants** named in `../phase-arch-design.md §Component design C9`: `PluginsLoaded`, `PluginResolved`, `BundleBuilt`, `BundleEntryPromoted`, `RecipeMatched`, `RecipeApplied`, `RecipeSkipped`, `RecipeFailed`, `InstallStageOutcome`, `TestStageOutcome`, `LocalBranchWritten`, `RequiresHumanReview`, `AdapterDegraded`, `StageOutcome`, `FilesystemRaceDetected`, `GitHooksDisabledForRun`. Each variant is `frozen=True`, `extra="forbid"`, with **typed payload fields** (NOT a free-form `payload: dict`) — this is a deliberate tightening over arch §Data model line 859 (which gives the lower bound `payload: dict[str, str | int | bool | float | list[str]]`).
- [ ] **AC-7 (9 spanning variants).** `WorkflowSpanningEvent` is a Pydantic discriminated union (`Field(discriminator="event_type")`) with **all 9 variants** per arch §Data model line 868-873 (as amended by S3-05 AC-23): `WorkflowStarted`, `WorkflowCompleted`, `CostSandboxRun`, `CapabilityMinted`, `CapabilityUsed`, `PluginRegistryCorrupted`, `BenchReplayable`, `StaleVulnIndex`, and `CacheGcCompleted`. Same constraints. Every spanning variant carries `prev_hash: BlobDigest`.
- [ ] **AC-CG (re-import 9th variant).** The 9th variant `CacheGcCompleted` is **re-imported** from `codegenie.plugins.cache_gc` (existing class is `CacheGcCompletedEvent` — the events module re-exports it under both names to preserve S3-05's external contract). NO duplicate class definition; an identity test asserts `events.CacheGcCompleted is cache_gc.CacheGcCompletedEvent`.
- [ ] **AC-MIG (CLI emit-site migration).** `src/codegenie/cli.py:cache_prune` no longer hand-writes `os.write` to `append.jsonl`; it constructs `EventLog(root=…/.codegenie, workflow_id=WorkflowId("operator_cli"))` and calls `event_log.emit_spanning(CacheGcCompletedEvent.from_result(result, trigger="operator_cli"))`. The pre-existing CLI test in `tests/integration/cli/test_cache_prune.py` is updated to decompress `.jsonl.zst` (the file's new on-disk format) and decode one chained `CacheGcCompleted` event. The interim uncompressed `append.jsonl` artifact is no longer produced.
- [ ] **AC-CHOKE (hashing chokepoint).** `src/codegenie/plugins/events.py` does NOT import `blake3` directly. The BLAKE3 chain step routes through `codegenie.hashing.content_hash_bytes(prior_head_bytes + event_bytes)`, with the `blake3:` prefix stripped to populate the un-prefixed 64-hex `BlobDigest` (matches `tree_digest_of_files`'s prefix-stripping precedent in `hashing.py:155-179`). A fence test (`tests/fence/test_events_module_routes_hashing_through_codegenie_hashing.py`) AST-walks the module and fails on any `import blake3` / `from blake3 import …`.
- [ ] **AC-DEP (zstandard dependency).** `pyproject.toml`'s `[project].dependencies` lists `zstandard>=0.22`. Phase 3 import-linter contracts (`codegenie.plugins must not import LLM SDKs`) still pass (`zstandard` is unaffected). A `make check` clean run confirms.
- [ ] **AC-GEN (genesis chain head).** Module-level `GENESIS_CHAIN_HEAD: Final[BlobDigest] = BlobDigest("0" * 64)`. The first `emit_spanning` against an empty file uses `GENESIS_CHAIN_HEAD` as the **prior head input** to `_chain_step`; the resulting event's `prev_hash` is `_chain_step(GENESIS_CHAIN_HEAD, canonical_json_bytes(event_without_prev_hash))` — deterministically reproducible (same event + frozen clock + empty file ⇒ same `prev_hash`). Pinning constant: AC-CORE's `_chain_step` is pure, so this is automatic.
- [ ] **AC-RES (resume across process restart).** Closing an `EventLog`, then re-opening with the same `root + workflow_id`, then calling `emit_spanning(...)` produces an event whose `prev_hash` matches the last on-disk event's recomputed chain head — NOT genesis. The "re-read tail under lock" path is exercised by both the construction-time tail read AND the per-emit re-read.
- [ ] **AC-EMPTY (empty replay).** `EventLog(tmp_path, _wf()).replay()` returns an empty iterator (no exception) before any emit; the directories exist but the files are absent or zero-byte.
- [ ] **AC-TORN (truncated frame).** A spanning file whose trailing zstd frame is truncated mid-record raises `EventLogCorrupted(path, line_number, reason="truncated_frame")` on `replay()` — NOT a silent truncation. The walker stops at the first parse failure and never advances past it.
- [ ] **AC-FLUSH (idempotent flush).** `flush() -> None` `fsync`s both file descriptors. Calling `flush()` twice in a row produces no observable change beyond a second `fsync` syscall; calling `flush()` on a never-emitted `EventLog` is a no-op (no exception, no file created with non-zero size).
- [ ] **AC-ASYNC (sync flock contract).** `emit_spanning` is a synchronous method that blocks on `fcntl.flock(LOCK_EX)`. The orchestrator (S6-04) wraps invocations in `asyncio.to_thread(...)` — mirroring the established `SubprocessJail.run` pattern. The module-level docstring states this contract explicitly.
- [ ] **AC-CLOCK (clock injection).** Tests pass `clock=lambda: datetime(2026, 5, 19, tzinfo=UTC)` to construct a frozen-time `EventLog`; emitted events carry exactly that timestamp; replay round-trips unchanged. Default clock is `lambda: datetime.now(UTC)`.
- [ ] **AC-CORE (pure chain helper).** A module-level pure helper `_chain_step(prior_head: BlobDigest, event_bytes: bytes) -> BlobDigest` (NO `self`; NO I/O; NO state) does the BLAKE3 composition. Both the writer (`emit_spanning`) and the verifier (S6-05's audit-verify extension, future) call this exact function. A unit test pins `_chain_step(GENESIS_CHAIN_HEAD, b"") == _chain_step(GENESIS_CHAIN_HEAD, b"")` (deterministic) and `_chain_step(GENESIS_CHAIN_HEAD, b"a") != _chain_step(GENESIS_CHAIN_HEAD, b"b")` (sensitive to content).
- [ ] **AC-DISC (discriminator API).** `WorkflowInternalEvent` and `WorkflowSpanningEvent` are declared as `Annotated[V1 | V2 | …, Field(discriminator="event_type")]`. NOT `Discriminator("event_type")`. Matches codebase convention (every union in `transforms/outcomes.py`, `plugins/{bundle,manifest,resolver,errors}.py`).
- [ ] **AC-HONEST (tamper-evident-not-proof).** Module-level docstring states explicitly: **"the BLAKE3 chain on the spanning stream is tamper-*evident*, not tamper-*proof*."** An attacker with shell access can re-write the entire chain end-to-end; the chain catches accidental corruption + after-the-fact integrity verification, NOT a real-time MITM. Cites ADR-0011 honest-framing.
- [ ] **AC-NOPATH (no Path in payloads).** No event variant declares a `Path` field — paths are `str` (relative-to-jail) or `BranchName` (`NewType` over `str`). Phase 9's cross-machine projector reads these — absolute paths leak host structure (CLAUDE.md §"Absolute-path scrubbing"). Enforced by the same AST fence as AC-CHOKE.
- [ ] **AC-CHAIN (chain-verify mutation-resistant).** Writing N events (N=10), then walking the file recomputing each `prev_hash`, matches the on-disk values byte-for-byte. **Distinct events have distinct `prev_hash`** (`event_K.prev_hash != event_{K-1}.prev_hash` for K > 1). Tamper test: flip one byte in any event's payload → walker raises `ChainTamperDetected(path, expected_prev, computed_prev)` at the first divergent record.
- [ ] **AC-MUT (metamorphic).** Emitting **the same** event twice (same fields, same frozen-clock timestamp) produces **different** `prev_hash` values on the two on-disk records — because the prior chain head differs. This is the mutation-resistance proof against a wrong implementation that left `prev_hash` constant.
- [ ] **AC-FLOCK (cross-process flock).** A unit test spawns two real `multiprocessing.Process` (start_method `"spawn"`) workers that each call `emit_spanning(...)` 50 times against a shared `root`; the resulting chain verifies via the independent `_chain_step` walker (no interleaving, no broken `prev_hash`). The test does NOT use threads (they share the fd; `flock` would be uncontended).
- [ ] **AC-REPLAY (byte-equal round-trip).** Replay round-trip is byte-equal modulo timestamps + `workflow_id`: `tests/integration/test_event_replay.py` writes a synthetic 20-event workload with a frozen clock, calls `replay()`, re-serializes via the same canonical-JSON helper, and asserts byte-equality on the payload-only bytes.
- [ ] **AC-INTERIM (interim format absorbed).** `codegenie cache prune` integration test (existing in `tests/integration/cli/test_cache_prune.py`) is updated to assert: (a) the new on-disk file is `<cache_dir>/../events/spanning/append.jsonl.zst` (zstd-compressed); (b) exactly one `CacheGcCompleted` spanning event is present; (c) its `prev_hash` is `GENESIS_CHAIN_HEAD` on the first run, and the prior on-disk chain head on subsequent runs.
- [ ] **AC-S6-05-CONTRACT.** `codegenie audit verify` (extended in S6-05) does NOT regress: this story does not edit the existing `verify` entrypoint — it only ships the spanning chain in a shape that S6-05's extension can walk, via the **same** `_chain_step` pure helper (AC-CORE).
- [ ] **AC-TYPED-PAYLOADS.** All event payload fields use **primitives only** (`str | int | bool | float | list[str]` per §C9 spec) AND are typed per variant (NO free-form `payload: dict[str, Any]`, NO `Any` anywhere); the AST fence walks `ast.Name` AND `ast.Attribute` forms (`Any`, `typing.Any`) and fails on any occurrence.
- [ ] **AC-DOC.** Module-level docstring cites `ADR-0005`, `ADR-0001` (chokepoint), `ADR-0011` (honest-framing), and `../phase-arch-design.md §Component design C9` as sources of truth.
- [ ] **AC-RGM.** TDD red test exists, committed, green.
- [ ] **AC-FORMAT.** `ruff format`, `ruff check`, `mypy --strict` clean.

## Implementation outline

1. **Red.** Write `tests/unit/plugins/test_events.py` (red); confirm `ModuleNotFoundError` then `ImportError` on each missing variant as the union grows. Also write `tests/fence/test_events_module_routes_hashing_through_codegenie_hashing.py` (red); confirm it fails with "module does not exist yet."

2. **Add `zstandard` to `pyproject.toml` `[project].dependencies`** (line near `"blake3",`): `"zstandard>=0.22",`. Run `uv lock` / `pip install -e .` to update the lockfile. Confirm `make lint-imports` and `make fence` pass (the Phase 3 import-linter contracts forbid LLM SDKs in `codegenie.plugins`; `zstandard` is unaffected).

3. **Create `src/codegenie/plugins/events.py`:**

   - **Module docstring** cites ADR-0005, ADR-0001 (chokepoint), ADR-0011 (honest-framing — chain is tamper-*evident* not tamper-*proof*), and `../phase-arch-design.md §Component design C9` as sources of truth. Documents the `emit_spanning`-is-synchronous-and-blocks-on-flock contract (orchestrator wraps in `asyncio.to_thread`).
   - **Imports:** `from codegenie.hashing import content_hash_bytes`. **NO** `from blake3 import blake3` — the AST fence will fail. `from codegenie.plugins.cache_gc import CacheGcCompletedEvent as CacheGcCompleted` (and re-export both names from `__all__`).
   - **Module-level constant:** `GENESIS_CHAIN_HEAD: Final[BlobDigest] = BlobDigest("0" * 64)`.
   - **Pure helpers** (module-level, no `self`, no I/O):
     - `def canonical_json_bytes(event: BaseModel) -> bytes` — `model_dump_json(by_alias=False)` with sorted keys + `separators=(",", ":")`. For spanning events, drops the `prev_hash` field before serializing (the chain step computes it). Stable across Pydantic minor versions per `model_dump_json`'s documented ordering.
     - `def _chain_step(prior_head: BlobDigest, event_bytes: bytes) -> BlobDigest` — composes `content_hash_bytes(bytes.fromhex(prior_head) + event_bytes)` and strips the `blake3:` prefix. This is the **shared** helper S6-05's audit-verify extension will call from a stateless walker.
   - **Event variants** (15 internal + 9 spanning, since the 9th spanning `CacheGcCompleted` is re-imported):
     - Each is `frozen=True, extra="forbid"` Pydantic with a `event_type: Literal["<snake>"] = "<snake>"` discriminator field + typed payload fields (NO `dict[str, Any]`, NO `Any`, NO `Path`).
     - Example: `class PluginResolved(BaseModel): model_config = ConfigDict(frozen=True, extra="forbid"); event_type: Literal["plugin_resolved"] = "plugin_resolved"; event_id: EventId; workflow_id: WorkflowId; timestamp: datetime; plugin_id: PluginId; matched_scope: str; specificity: int`.
     - Spanning variants additionally carry `prev_hash: BlobDigest` (which the writer **rewrites** under the chain step — accept any value at construction; the canonical value is computed at emit time).
   - **Discriminated unions** (codebase-convention API):
     ```python
     WorkflowInternalEvent: TypeAlias = Annotated[
         PluginsLoaded | PluginResolved | BundleBuilt | BundleEntryPromoted
         | RecipeMatched | RecipeApplied | RecipeSkipped | RecipeFailed
         | InstallStageOutcome | TestStageOutcome | LocalBranchWritten
         | RequiresHumanReview | AdapterDegraded | StageOutcome
         | FilesystemRaceDetected | GitHooksDisabledForRun,
         Field(discriminator="event_type"),
     ]
     WorkflowSpanningEvent: TypeAlias = Annotated[
         WorkflowStarted | WorkflowCompleted | CostSandboxRun
         | CapabilityMinted | CapabilityUsed | PluginRegistryCorrupted
         | BenchReplayable | StaleVulnIndex | CacheGcCompleted,
         Field(discriminator="event_type"),
     ]
     ```
   - **`EventStreamSink` protocol + `ZstdAppendingFileSink` default** (functional-core / imperative-shell split):
     ```python
     class EventStreamSink(Protocol):
         def append(self, line: bytes) -> None: ...
         def read_all(self) -> Iterator[bytes]: ...  # decompressed
         def fsync(self) -> None: ...
         def tail_chain_head(self) -> BlobDigest: ...
     ```
     Two implementations on day one: `ZstdAppendingFileSink(path, *, level=3)` (production) + `InMemorySink()` (tests). The default sink wraps `zstandard.ZstdCompressor(level=3).stream_writer(...)` with a fresh frame per append (each line is a self-contained frame so partial appends don't corrupt the prior chain).
   - **`class EventLog`:**
     - `__init__(self, root, workflow_id, *, clock=None, sink=None)` — opens both files (or in-memory sinks); `_chain_head = self._spanning_sink.tail_chain_head()` (defaults to `GENESIS_CHAIN_HEAD` on empty file).
     - `emit_internal(event)`: `event.model_validate(...)` (Pydantic does this implicitly via the union); `self._internal_sink.append(canonical_json_bytes(event) + b"\n")`; return `event.event_id`.
     - `emit_spanning(event)`: acquire `fcntl.flock(self._spanning_fd, LOCK_EX)`; under lock, refresh `self._chain_head = self._spanning_sink.tail_chain_head()`; compute `new_prev = _chain_step(self._chain_head, canonical_json_bytes(event_without_prev_hash))`; build a `event = event.model_copy(update={"prev_hash": new_prev})`; `self._spanning_sink.append(canonical_json_bytes(event) + b"\n")`; `self._chain_head = new_prev`; release lock; return `event.event_id`.
     - `flush()`: `self._internal_sink.fsync(); self._spanning_sink.fsync()`. Idempotent (re-calling does no harm).
     - `replay() -> Iterator[WorkflowInternalEvent | WorkflowSpanningEvent]`: open both sinks read-only, decode line-by-line via the typed unions (Pydantic discriminator does the variant dispatch), yield in `(timestamp, event_id)` order. Raise `EventLogCorrupted(path, line_number, reason)` on parse failure or truncated zstd frame.
   - **`__all__`** lists `EventLog`, both unions, every variant class, `EventStreamSink`, `ZstdAppendingFileSink`, `InMemorySink`, `GENESIS_CHAIN_HEAD`, and the exceptions (`ChainTamperDetected`, `EventLogCorrupted`).

4. **Migrate `src/codegenie/cli.py:cache_prune`** to construct an `EventLog` and emit through `emit_spanning(...)`. Replace the hand-rolled `os.write(fd, line.encode("utf-8") + b"\n")` block with `EventLog(root=resolved_cache_dir.parent, workflow_id=WorkflowId("operator_cli")).emit_spanning(event_cls.from_result(result, trigger="operator_cli"))` + `event_log.flush()`. Update the docstring (was: "interim wire format") to reflect the absorbed state. Update `tests/integration/cli/test_cache_prune.py` to decompress `.jsonl.zst` and decode one chained event.

5. **Add fence test** `tests/fence/test_events_module_routes_hashing_through_codegenie_hashing.py` — AST-walks `src/codegenie/plugins/events.py` and fails on `import blake3` / `from blake3 import …`. Mirrors `tests/fence/test_audit_module_has_no_hashlib_or_blake3_imports`.

6. Run `make check` (lint → typecheck → test → fence). Confirm green.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/plugins/test_events.py`.

```python
# tests/unit/plugins/test_events.py
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from codegenie.plugins.events import (
    EventLog, WorkflowInternalEvent, WorkflowSpanningEvent,
    PluginResolved, WorkflowStarted, AdapterDegraded,
    ChainTamperDetected, EventLogCorrupted,
)
from codegenie.types.identifiers import WorkflowId, EventId, PluginId, BlobDigest


def _wf() -> WorkflowId:
    return WorkflowId("01HFEEDFACE0000000000000000")  # ULID-shape stub

def _now() -> datetime:
    return datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)


def test_two_streams_write_to_distinct_paths(tmp_path: Path) -> None:
    log = EventLog(root=tmp_path, workflow_id=_wf())
    log.emit_internal(PluginResolved(event_id=EventId("01H...01"), workflow_id=_wf(),
                                     timestamp=_now(), plugin_id=PluginId("p"),
                                     matched_scope="vuln--node--npm", specificity=3))
    log.emit_spanning(WorkflowStarted(event_id=EventId("01H...02"), workflow_id=_wf(),
                                      timestamp=_now(), prev_hash=BlobDigest("0" * 64)))
    log.flush()
    internal = tmp_path / "events" / "workflow-internal" / f"{_wf()}.jsonl.zst"
    spanning = tmp_path / "events" / "spanning" / "append.jsonl.zst"
    assert internal.exists() and internal.stat().st_size > 0
    assert spanning.exists() and spanning.stat().st_size > 0


def test_internal_event_to_spanning_method_is_rejected(tmp_path: Path) -> None:
    log = EventLog(root=tmp_path, workflow_id=_wf())
    internal_event = PluginResolved(event_id=EventId("01H...01"), workflow_id=_wf(),
                                    timestamp=_now(), plugin_id=PluginId("p"),
                                    matched_scope="*--*--*", specificity=0)
    with pytest.raises((TypeError, ValidationError)):
        log.emit_spanning(internal_event)  # type: ignore[arg-type]


def test_blake3_chain_verifies_then_breaks_on_tamper(tmp_path: Path) -> None:
    log = EventLog(root=tmp_path, workflow_id=_wf(), clock=lambda: _now())
    for i in range(10):
        log.emit_spanning(WorkflowStarted(event_id=EventId(f"01H...{i:02}"), workflow_id=_wf(),
                                          timestamp=_now(), prev_hash=GENESIS_CHAIN_HEAD))
    log.flush()
    # Re-open and walk — should verify (the walker recomputes each prev_hash and
    # asserts it matches the on-disk value).
    events = list(log.replay())  # no exception
    assert len(events) == 10
    # Distinct prev_hash per event (AC-CHAIN mutation guard against a wrong impl
    # that leaves prev_hash constant at GENESIS).
    prev_hashes = [e.prev_hash for e in events]
    assert len(set(prev_hashes)) == 10, f"prev_hash collision: {prev_hashes}"

    # Tamper: zstd-aware byte flip in the first event's payload.
    _flip_one_payload_byte(tmp_path / "events" / "spanning" / "append.jsonl.zst")
    with pytest.raises(ChainTamperDetected):
        list(log.replay())


def _flip_one_payload_byte(spanning_path: Path) -> None:
    """Concrete helper — read zstd file, decompress to JSONL bytes, flip one
    byte inside the first event's payload (NOT inside the prev_hash field),
    recompress, write back. The flip target is the first character of the
    event_id field's value, which is always present in every variant."""
    import zstandard
    raw = spanning_path.read_bytes()
    dctx = zstandard.ZstdDecompressor()
    decompressed = dctx.decompress(raw)
    lines = decompressed.split(b"\n")
    # Flip a byte inside the first non-empty line, in the event_id value
    # (search for `"event_id":"<one-char>"` and bump the char by one).
    import re
    lines[0] = re.sub(
        rb'("event_id":")(.)',
        lambda m: m.group(1) + bytes([(m.group(2)[0] + 1) % 256]),
        lines[0],
        count=1,
    )
    cctx = zstandard.ZstdCompressor(level=3)
    spanning_path.write_bytes(cctx.compress(b"\n".join(lines)))


def test_cross_process_flock_keeps_chain_intact(tmp_path: Path) -> None:
    """AC-FLOCK: two real subprocesses appending 50 events each preserve chain integrity."""
    import multiprocessing as mp
    ctx = mp.get_context("spawn")  # macOS-safe
    def _worker(root: str, wf_suffix: str) -> None:
        # Each process opens its own EventLog instance against the SAME root.
        from codegenie.plugins.events import EventLog, WorkflowStarted, GENESIS_CHAIN_HEAD
        from codegenie.types.identifiers import WorkflowId, EventId, BlobDigest
        from datetime import datetime, UTC
        log = EventLog(root=Path(root), workflow_id=WorkflowId(f"wf-{wf_suffix}"))
        for i in range(50):
            log.emit_spanning(WorkflowStarted(
                event_id=EventId(f"01H{wf_suffix}{i:03}"),
                workflow_id=WorkflowId(f"wf-{wf_suffix}"),
                timestamp=datetime.now(UTC),
                prev_hash=GENESIS_CHAIN_HEAD,
            ))
        log.flush()
    p1 = ctx.Process(target=_worker, args=(str(tmp_path), "a"))
    p2 = ctx.Process(target=_worker, args=(str(tmp_path), "b"))
    p1.start(); p2.start(); p1.join(); p2.join()
    assert p1.exitcode == 0 and p2.exitcode == 0
    # Independent walker (NOT via either process's in-memory _chain_head):
    from codegenie.plugins.events import _chain_step, GENESIS_CHAIN_HEAD, canonical_json_bytes
    import zstandard, json
    raw = (tmp_path / "events" / "spanning" / "append.jsonl.zst").read_bytes()
    lines = [l for l in zstandard.ZstdDecompressor().decompress(raw).split(b"\n") if l]
    assert len(lines) == 100
    head = GENESIS_CHAIN_HEAD
    for line in lines:
        ev = json.loads(line)
        without = {k: v for k, v in ev.items() if k != "prev_hash"}
        # canonical_json_bytes-shape: sorted keys, tight separators
        body = json.dumps(without, sort_keys=True, separators=(",", ":")).encode("utf-8")
        expected = _chain_step(head, body)
        assert ev["prev_hash"] == expected, f"chain break at line {ev['event_id']}"
        head = expected


def test_replay_round_trip_byte_equal_modulo_timestamps(tmp_path: Path) -> None:
    """AC-REPLAY: 20-event workload round-trips byte-equal under a frozen clock."""
    frozen = _now()
    log = EventLog(root=tmp_path, workflow_id=_wf(), clock=lambda: frozen)
    for i in range(20):
        log.emit_internal(PluginResolved(
            event_id=EventId(f"01H...P{i:02}"), workflow_id=_wf(), timestamp=frozen,
            plugin_id=PluginId(f"p{i}"), matched_scope="vuln--node--npm", specificity=3,
        ))
    log.flush()
    events1 = list(log.replay())
    # Re-emit via a fresh log against a fresh path; compare canonical-JSON bytes.
    from codegenie.plugins.events import canonical_json_bytes
    bytes1 = [canonical_json_bytes(e) for e in events1]
    log2 = EventLog(root=tmp_path / "second", workflow_id=_wf(), clock=lambda: frozen)
    for e in events1:
        log2.emit_internal(e)
    log2.flush()
    events2 = list(log2.replay())
    bytes2 = [canonical_json_bytes(e) for e in events2]
    assert bytes1 == bytes2


def test_genesis_prev_hash_on_empty_file(tmp_path: Path) -> None:
    """AC-GEN: first emit on an empty spanning file uses GENESIS_CHAIN_HEAD as the prior head."""
    log = EventLog(root=tmp_path, workflow_id=_wf(), clock=lambda: _now())
    log.emit_spanning(WorkflowStarted(event_id=EventId("01H...G1"), workflow_id=_wf(),
                                      timestamp=_now(), prev_hash=GENESIS_CHAIN_HEAD))
    log.flush()
    first = next(iter(log.replay()))
    # The on-disk prev_hash is _chain_step(GENESIS, canonical_json(event w/o prev_hash)),
    # NOT GENESIS itself (the prev_hash on the emitted event reflects the chain step).
    assert first.prev_hash != GENESIS_CHAIN_HEAD
    # Pin determinism: re-emitting the same event under the same frozen clock
    # against a fresh root produces the SAME prev_hash.
    log2 = EventLog(root=tmp_path / "second", workflow_id=_wf(), clock=lambda: _now())
    log2.emit_spanning(WorkflowStarted(event_id=EventId("01H...G1"), workflow_id=_wf(),
                                       timestamp=_now(), prev_hash=GENESIS_CHAIN_HEAD))
    log2.flush()
    assert next(iter(log2.replay())).prev_hash == first.prev_hash


def test_resume_across_process_restart(tmp_path: Path) -> None:
    """AC-RES: closing + reopening EventLog rehydrates _chain_head from disk."""
    log1 = EventLog(root=tmp_path, workflow_id=_wf(), clock=lambda: _now())
    log1.emit_spanning(WorkflowStarted(event_id=EventId("01H...R1"), workflow_id=_wf(),
                                       timestamp=_now(), prev_hash=GENESIS_CHAIN_HEAD))
    log1.flush()
    head_after_first = next(iter(log1.replay())).prev_hash
    # Drop the first log (simulate process exit).
    del log1
    # New log against same root — must rehydrate.
    log2 = EventLog(root=tmp_path, workflow_id=_wf(), clock=lambda: _now())
    log2.emit_spanning(WorkflowStarted(event_id=EventId("01H...R2"), workflow_id=_wf(),
                                       timestamp=_now(), prev_hash=GENESIS_CHAIN_HEAD))
    log2.flush()
    events = list(log2.replay())
    assert len(events) == 2
    assert events[0].prev_hash == head_after_first
    assert events[1].prev_hash != GENESIS_CHAIN_HEAD
    assert events[1].prev_hash != head_after_first


def test_empty_replay_yields_nothing(tmp_path: Path) -> None:
    """AC-EMPTY: never-emitted EventLog.replay() returns an empty iterator."""
    log = EventLog(root=tmp_path, workflow_id=_wf())
    assert list(log.replay()) == []


def test_truncated_frame_raises_event_log_corrupted(tmp_path: Path) -> None:
    """AC-TORN: a truncated trailing zstd frame raises EventLogCorrupted, not silent truncation."""
    log = EventLog(root=tmp_path, workflow_id=_wf(), clock=lambda: _now())
    log.emit_spanning(WorkflowStarted(event_id=EventId("01H...T1"), workflow_id=_wf(),
                                      timestamp=_now(), prev_hash=GENESIS_CHAIN_HEAD))
    log.flush()
    spanning_path = tmp_path / "events" / "spanning" / "append.jsonl.zst"
    raw = spanning_path.read_bytes()
    # Truncate the last 4 bytes — guarantees a torn zstd frame.
    spanning_path.write_bytes(raw[:-4])
    with pytest.raises(EventLogCorrupted):
        list(log.replay())


def test_flush_is_idempotent_and_noop_on_empty(tmp_path: Path) -> None:
    """AC-FLUSH: flush() is idempotent; flush() on a never-emitted log is a no-op."""
    log = EventLog(root=tmp_path, workflow_id=_wf())
    log.flush()  # never-emitted: no exception
    log.flush(); log.flush()  # idempotent on empty
    log.emit_internal(PluginResolved(event_id=EventId("01H...F1"), workflow_id=_wf(),
                                     timestamp=_now(), plugin_id=PluginId("p"),
                                     matched_scope="*--*--*", specificity=0))
    log.flush(); log.flush()  # idempotent after emit
    # No observable change in on-disk size between the two flushes.
    internal = tmp_path / "events" / "workflow-internal" / f"{_wf()}.jsonl.zst"
    size1 = internal.stat().st_size
    log.flush()
    assert internal.stat().st_size == size1


def test_chain_step_pure_helper_is_deterministic_and_content_sensitive() -> None:
    """AC-CORE: _chain_step is pure (deterministic + content-sensitive)."""
    from codegenie.plugins.events import _chain_step, GENESIS_CHAIN_HEAD
    assert _chain_step(GENESIS_CHAIN_HEAD, b"") == _chain_step(GENESIS_CHAIN_HEAD, b"")
    assert _chain_step(GENESIS_CHAIN_HEAD, b"a") != _chain_step(GENESIS_CHAIN_HEAD, b"b")
    h1 = _chain_step(GENESIS_CHAIN_HEAD, b"a")
    assert _chain_step(h1, b"a") != _chain_step(GENESIS_CHAIN_HEAD, b"a")  # head changes output


def test_metamorphic_same_event_twice_yields_distinct_prev_hash(tmp_path: Path) -> None:
    """AC-MUT: emitting the same event twice yields different prev_hash."""
    log = EventLog(root=tmp_path, workflow_id=_wf(), clock=lambda: _now())
    ev = WorkflowStarted(event_id=EventId("01H...M1"), workflow_id=_wf(),
                          timestamp=_now(), prev_hash=GENESIS_CHAIN_HEAD)
    log.emit_spanning(ev); log.emit_spanning(ev); log.flush()
    events = list(log.replay())
    assert events[0].prev_hash != events[1].prev_hash  # head shifted between emits


def test_cache_gc_completed_is_reimported_not_redefined() -> None:
    """AC-CG: events.CacheGcCompleted is the same class as cache_gc.CacheGcCompletedEvent."""
    from codegenie.plugins import events as ev
    from codegenie.plugins.cache_gc import CacheGcCompletedEvent
    assert ev.CacheGcCompleted is CacheGcCompletedEvent
    assert ev.CacheGcCompletedEvent is CacheGcCompletedEvent  # re-exported under both names


def test_all_16_internal_variants_exist() -> None:
    from codegenie.plugins import events as ev
    expected = {"PluginsLoaded", "PluginResolved", "BundleBuilt", "BundleEntryPromoted",
                "RecipeMatched", "RecipeApplied", "RecipeSkipped", "RecipeFailed",
                "InstallStageOutcome", "TestStageOutcome", "LocalBranchWritten",
                "RequiresHumanReview", "AdapterDegraded", "StageOutcome",
                "FilesystemRaceDetected", "GitHooksDisabledForRun"}
    for name in expected:
        assert hasattr(ev, name), f"missing internal variant: {name}"


def test_all_8_spanning_variants_exist() -> None:
    from codegenie.plugins import events as ev
    expected = {"WorkflowStarted", "WorkflowCompleted", "CostSandboxRun",
                "CapabilityMinted", "CapabilityUsed", "PluginRegistryCorrupted",
                "BenchReplayable", "StaleVulnIndex"}
    for name in expected:
        assert hasattr(ev, name), f"missing spanning variant: {name}"


def test_event_payloads_have_no_dict_any() -> None:
    """AST-fence: no Any / dict[str, Any] on any event variant payload."""
    import ast, inspect
    from codegenie.plugins import events as ev
    src = inspect.getsource(ev)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "Any":
            pytest.fail("Any annotation present in events.py")
```

Run; confirm `ModuleNotFoundError`. Commit the red marker.

### Green — make it pass

Implement `EventLog` with the minimum code to satisfy each test. Resist the urge to factor out a `_BaseEvent` mixin that hides payload fields — every variant is a tiny class, and the discriminated-union pattern requires the `event_type: Literal[...]` field literally on each class. The `_chain_head` is read by decompressing the spanning file's tail; if the file is empty (genesis), `_chain_head = "0" * 64`.

### Refactor — clean up

- Confirm `canonical_json_bytes(model)` is a module-level pure helper that strips the `prev_hash` field when serializing spanning events (so the chain step doesn't fold the field into its own input).
- Confirm `_chain_step(prior_head, event_bytes) -> BlobDigest` is the **only** BLAKE3 call site in the module and routes through `codegenie.hashing.content_hash_bytes` (chokepoint discipline — ADR-0001). The AST fence test will catch a direct `import blake3` regression.
- Document the chain composition: `prev_hash = _chain_step(prior_head, canonical_json_bytes(event_without_prev_hash))`. The S6-05 `codegenie audit verify` extension will call this same helper from a stateless walker.
- Module-level docstring states: **the chain is tamper-evident, not tamper-proof** (ADR-0011). An attacker with shell access can re-write the entire chain end-to-end; the chain catches accidental corruption + after-the-fact integrity verification, not a real-time MITM.
- Document `flush()` as the orchestrator's `finally`-block contract (ADR-0005 §Consequences).
- Confirm `EventStreamSink` is a `Protocol` (not an ABC) and `ZstdAppendingFileSink` / `InMemorySink` satisfy it structurally. `EventLog` accepts the protocol; production constructs `ZstdAppendingFileSink`, tests construct `InMemorySink`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/plugins/events.py` | **New file** — `EventLog`, two discriminated unions, 15 new internal variants + 9 spanning variants (the 9th `CacheGcCompleted` is re-imported from `cache_gc.py`, not redefined), BLAKE3 chain (via `codegenie.hashing`), `fcntl.flock`, `EventStreamSink` protocol + `ZstdAppendingFileSink` + `InMemorySink`, pure `_chain_step` helper, `GENESIS_CHAIN_HEAD` constant, `ChainTamperDetected` + `EventLogCorrupted` exceptions. |
| `src/codegenie/cli.py` | **Edit** — `cache_prune` command migrates from hand-rolled `os.write(...)` on uncompressed `append.jsonl` to `EventLog.emit_spanning(...)` on the chained `append.jsonl.zst`. Update docstring. |
| `tests/unit/plugins/test_events.py` | **New file** — two-stream writer, chain verify, tamper detection (concrete `_flip_one_payload_byte`), real-subprocess cross-process flock, genesis prev_hash, resume across restart, empty replay, torn-frame `EventLogCorrupted`, idempotent flush, pure `_chain_step` helper, metamorphic-prev_hash, all-variants-exist, AST fence on `Any` / `dict[str, Any]`, `CacheGcCompleted` re-import identity. |
| `tests/integration/test_event_replay.py` | **New file** — 20-event replay round-trip byte-equal modulo timestamps + workflow_id (per architecture spec §Harness engineering). |
| `tests/integration/cli/test_cache_prune.py` | **Edit** — update existing assertions to decompress `.jsonl.zst` and decode one chained `CacheGcCompleted` event (instead of reading uncompressed `.jsonl`). |
| `tests/fence/test_events_module_routes_hashing_through_codegenie_hashing.py` | **New file** — AST-walks `events.py`; fails on `import blake3` / `from blake3 import …` (mirrors `test_audit_module_has_no_hashlib_or_blake3_imports`). |
| `pyproject.toml` | **Edit** — add `"zstandard>=0.22",` to `[project].dependencies`. `blake3` is already present. |

## Out of scope

- **`codegenie audit verify` CLI extension** — S6-05 lands this. This story only ships the chain in a shape S6-05 can walk via the **shared** `_chain_step` pure helper (AC-CORE).
- **`TrustScorer` reading `AdapterDegraded` events** — S6-02 lands this. This story only ships the variant + the writer.
- **Phase 9 migration code** — Phase 9 reads these files via separate ingestion jobs; out of scope here.
- **OpenTelemetry / structured-tracing integration** — deferred to Phase 13 per `../phase-arch-design.md §Harness engineering`.
- **Compaction / log rotation of the spanning stream** — Phase 9+ territory; Phase 3 ships unbounded append-only.
- **`PluginsLoaded` emission** — the variant must exist (this story) but the *call site* lives in S2-03 / S7-01 plugin-loader code; no edit here.
- **Smart-constructor validation of `EventId` / `WorkflowId` ULID shape** — both remain raw `NewType` for now; runtime ULID validation is a Phase 6+ amendment.
- **Extracting `canonical_json_bytes` into a shared module** (e.g., `codegenie.canonical_json`) — only one consumer today (`events.py`). Re-extract when a second consumer arrives (rule-of-three).

## Notes for the implementer

- The two streams are **non-fungible**. A reviewer might suggest "why not one method, `emit(event)`, dispatching on type?" — the answer is that `WorkflowInternalEvent` and `WorkflowSpanningEvent` are two **typed channels** to two **different backends** in Phase 9 (Temporal vs. Postgres). Separate methods make the channel a compile-time choice; a single `emit` collapses the categorical distinction back into runtime dispatch — exactly the anti-pattern ADR-0005 was written to avoid.
- The BLAKE3 chain composition is **new in this story** — there is no pre-existing `chain_append` in `audit.py`. Phase 0's `audit.py` is a flat per-blob/per-YAML anchor writer that shares only the **chokepoint discipline** (`codegenie.hashing` is the single import-allowed BLAKE3/SHA-256 module per ADR-0001). Mirror that discipline here: `from codegenie.hashing import content_hash_bytes` is the only sanctioned way to hash. S6-05's `audit verify` extension will call the **same** `_chain_step(prior_head, event_bytes)` pure helper this module exports — that's why AC-CORE pulls it out as a module-level function with no `self`.
- `fcntl.flock(LOCK_EX)` on Linux + macOS only — Windows-CI is out of scope for Phase 3 (the `bwrap` substrate alone forbids it). The lock acquisition is **blocking** by default; the orchestrator's `.codegenie/.lock` outer lock (S6-05) usually means the inner lock is uncontended, but the inner lock is the deeper defense if a future feature lets two workflows share a `root` dir.
- The **25** event variants (16 internal + 9 spanning, including the re-imported `CacheGcCompleted`) are tedious to write — resist the urge to generate them from a single `Literal[...]` and a `dict[str, type]` registry. Each variant carries a **typed payload schema** that downstream readers (Phase 9, `codegenie audit verify`, the contract snapshot in S6-06) rely on. A registry hides the schema behind `Any`. The verbosity is the contract. **Open/Closed across phases** is satisfied not by a registry but by **additive edits** to the union alias: new variant = new class + one name appended to the `Annotated[...]` chain. The S6-06 snapshot pins both the class list and the field set; adding is allowed, renaming is not.
- **Discriminator API.** Use `Annotated[V1 | V2 | …, Field(discriminator="event_type")]` — the codebase convention (see `transforms/outcomes.py`, `plugins/{bundle,manifest,resolver,errors}.py`). NOT `Discriminator("event_type")`. The discriminator field name `event_type` matches the events-domain arch convention; the API call (`Field(discriminator=…)`) matches the codebase elsewhere.
- **Typed-payload tightening over arch §Data model.** Arch line 859 specifies the lower bound `payload: dict[str, str | int | bool | float | list[str]]` on the umbrella. This story tightens that to **typed payload fields per variant** (e.g., `PluginResolved.plugin_id: PluginId`). The S6-06 snapshot will pin the typed shape. Reviewers might suggest "just use the dict" — push back: typed payloads catch the wrong-type-at-emission-site mistake at construction time, not at downstream-consumer time.
- **No `Path` in any event variant payload.** Phase 9's projector reads these from a different machine; absolute paths leak host structure (CLAUDE.md §"Absolute-path scrubbing"). Use `str` (relative-to-jail) or domain newtypes (`BranchName`, `PluginId`). The AC-NOPATH fence catches it.
- **Functional core / imperative shell.** `_chain_step(prior_head, event_bytes) -> BlobDigest` is pure (no I/O, no state, no `self`). The writer's lock acquire / write / fsync sequence is the imperative shell that calls into the pure core. This separation is mandatory because (a) the S6-05 walker must call `_chain_step` from a stateless context (no `EventLog` instance), and (b) testability — `_chain_step` is a one-line property test.
- **Sink protocol.** `EventStreamSink` (with `ZstdAppendingFileSink` + `InMemorySink` on day one) keeps the `EventLog` ignorant of the compression format. Phase 9's port to Postgres is a third sink. Two consumers on day one (production + tests) is the rule-of-three when counting test consumers — this is not premature pluggability, it's "tests need an in-memory variant or they decompress zstd in every assertion."
- **Exhaustiveness at consumer sites.** Downstream code that dispatches on `event.event_type` must use `match` + `assert_never` (mirrors `transforms/outcomes.py` `match`-on-`.kind`). A missing case becomes a static type error.
- **`fcntl.flock(LOCK_EX)` semantics.** The lock is **synchronous and blocking**; the orchestrator (S6-04) calls `emit_spanning` via `asyncio.to_thread(...)` (matches the established `SubprocessJail.run` pattern). The module-level docstring states this contract. The lock is held only during the chain-step + append + fsync — typically <1 ms — so blocking is acceptable. macOS supports `flock` via the BSD variant; tested on both Linux and Darwin runners in CI.
- **Interim wire-format absorption.** S3-05 ships `CacheGcCompletedEvent` to uncompressed `append.jsonl` via `os.write` in `cli.py:cache_prune`. This story:
  1. Re-imports the existing `CacheGcCompletedEvent` class as `CacheGcCompleted` (NO redefinition — preserves the field set).
  2. Replaces the hand-rolled `os.write` block in `cli.py:cache_prune` with `EventLog.emit_spanning(...)`.
  3. Updates `tests/integration/cli/test_cache_prune.py` to decompress `.jsonl.zst` and decode one chained event.
  After this story, the uncompressed `append.jsonl` artifact no longer exists; the only on-disk spanning artifact is `.jsonl.zst`.
- For payload fields, prefer `list[str]` over `tuple[str, ...]` to match the §C9 spec literally (`payload: dict[str, str | int | bool | float | list[str]]`). Pydantic round-trips both, but the spec is the contract.
- The "compact" zstd format with `level=3` is a good default — higher levels (e.g., 19) cost more CPU per event and Phase 3's per-emit budget (event-appender throughput >30k events/s per S9-03) won't tolerate it. Verify with a benchmark before merging.
- If `tests/integration/test_event_replay.py` flakes on timestamp comparison, use a `freezegun` fixture or pass a `clock: Callable[[], datetime]` to `EventLog.__init__` for testability — the latter is preferred (dependency injection beats time-mocking magic).
- The `EventLogCorrupted` exception is the *parse-time* failure (malformed JSON, missing `event_type` discriminator). `ChainTamperDetected` is the *integrity-time* failure (BLAKE3 mismatch). They are categorically different and must not be conflated.
- Avoid `pickle.loads` anywhere in this module — the `forbidden-patterns` pre-commit hook bans it repo-wide (per CLAUDE.md). JSON-only on disk.
- The phrase "Phase 9 lifts unchanged" in lens designs is the **wrong** framing per ADR-0005. The correct framing: "Phase 9 lifts each stream into its destined backend — the categorical split is the lift." If your test names or docstrings imply a single-backend model, rewrite them.
