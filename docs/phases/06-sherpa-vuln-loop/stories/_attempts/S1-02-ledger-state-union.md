# Attempt log — S1-02 (Ledger state union + TransitionEvent + chain-head)

## Attempt 1 — 2026-05-25 — GREEN

**Outcome:** All 15 ACs satisfied. Full test suite: **7265 passed, 43 skipped, 9 xfailed (pre-existing)**. Lint (`ruff check`, `ruff format`), `mypy --strict`, `make fence`, and `make lint-imports` all green.

### What landed

#### Kernel-tier identifier (`codegenie.types.identifiers`)
- `TransitionId = NewType("TransitionId", str)` — ULID; chained for replay-determinism. Distinct from `EventId` (forensic event log).
- Added to `__all__` (sorted, byte-equal to existing convention) and `_NEWTYPE_REGISTRY` with one-line docstring citing ADR-0010 + Phase-6 ADR-0001 + Phase-6 ADR-0003.

#### Smart constructor (`codegenie.types.parsers`)
- `parse_transition_id` — routes through `_regex_parser(_ULID_RX, max_len=26, name="TransitionId")` (AC-18 single-helper discipline preserved); per-newtype closure (`_transition_id_match`) gives error messages the right newtype name.

#### `codegenie.workflows.vuln_ledger` (new — 280 lines)
- Seven variant classes: `NeedsPlan`, `PlanReady`, `PatchApplied`, `GateFailedRetryable`, `AwaitingHumanReview`, `Completed`, `FailedUnrecoverable`. Each:
  - `model_config = _FROZEN_FORBID` (imported from S1-01's canonical site — never re-declared).
  - `kind: Literal["..."] = "..."` (per-variant default).
  - Per-variant payload typed against existing newtypes / closed Literals (`BlobDigest`, `SignalKind`, `AttemptNumber`, `HumanReviewReason`, `RemediationError`).
- `LedgerStateKind` — module-level Literal alias for the seven kind slugs.
- `VulnLedgerState = Annotated[NeedsPlan | ... | FailedUnrecoverable, Field(discriminator="kind")]`.
- `_TERMINAL_LEDGER_KINDS` (`{completed, awaiting_human_review, failed_unrecoverable}`) — byte-equal to S1-01's `TerminalState` Literal (AC-6).
- `_NON_TERMINAL_LEDGER_KINDS` (the four non-terminals).
- `FailedUnrecoverableReason` — closed Literal of five reasons (byte-equal to phase-arch-design §"Failure modes" row keys).
- `_LEGAL_TRANSITIONS: Final[frozenset[tuple[LedgerStateKind, LedgerStateKind]]]` — the 14-edge closed legal-transition table from final-design.md §"Main workflow".
- `TransitionEvent` — frozen+extra="forbid" Pydantic model with the seven fields (transition_id, prior_state_id, next_state_id, triggering_outcome, evidence_digest, chain_head, workflow_id); `model_validator(mode="after")` rejects `(prior, next) ∉ _LEGAL_TRANSITIONS` with the ADR-0003 directive substring.
- Module-bottom runtime `assert` cross-checks: `_VARIANT_KINDS == set(get_args(LedgerStateKind))` and `_VARIANT_KINDS == _NON_TERMINAL_LEDGER_KINDS | _TERMINAL_LEDGER_KINDS`.

#### `codegenie.workflows._chain` (new — 60 lines)
- `_compute_chain_head(prior_head, event) -> ChainHead` — pure functional core, routes BLAKE3 through `codegenie.hashing.content_hash_bytes` (ADR-0001 chokepoint).
- Payload composition: `prior_head_bytes + RECORD_SEP (\x1e) + event.model_dump_json_bytes`. Separator defuses boundary-shift collisions (mirrors `codegenie.hashing._RECORD_SEP` discipline).
- Returns `ChainHead` in the existing newtype shape — bare 64-hex (no `"blake3:"` prefix). See "Decisions of record" below.

#### `codegenie.workflows.__init__` (modified)
- `__all__` extended additively from 4 → 15 names (AC-13).
- `TransitionId` re-exported here for harness convenience (canonical declaration still at `codegenie.types.identifiers`).
- Module docstring updated to reference both ADR-0001 (S1-01) and ADR-0003 (S1-02).

#### Tests (8 new files + 4 modified)
- `tests/unit/workflows/test_vuln_ledger_shape.py` — AC-1 + AC-3 (24 tests).
- `tests/unit/workflows/test_vuln_ledger_discriminator.py` — AC-2 (9 tests).
- `tests/unit/workflows/test_transition_event_shape.py` — AC-4 + AC-5 with Hypothesis negative + terminal-closure + non-terminal-liveness (74 tests).
- `tests/unit/workflows/test_vuln_ledger_exhaustiveness.py` — AC-9 `match` + `assert_never` (7 tests).
- `tests/unit/workflows/test_vuln_ledger_roundtrip.py` — AC-10 round-trip + byte-determinism + umbrella discriminator (24 tests).
- `tests/unit/workflows/test_chain_head_properties.py` — AC-8 Hypothesis stability + sensitivity (to event change AND to prior-head change) + chain-forward fold (4 properties).
- `tests/fence/test_chain_head_purity.py` — AC-8 AST no-side-effects fence over `_chain.py`.
- `tests/fence/test_workflows_frozen_forbid.py` — AC-12 AST fence over every `BaseModel` in `codegenie/workflows/*.py`.
- `tests/integration/test_phase6_terminal_state_consistency.py` — AC-6 cross-story membership equality with directive printout.
- Extended `tests/integration/test_phase6_sut_contract_snapshot.py` — AC-15 ledger schema + TransitionEvent schema + sorted `_LEGAL_TRANSITIONS` in the snapshot; classifier extended for the new keys.
- Extended `tests/integration/test_phase6_sut_contract_snapshot_meta.py` — 4 new synthetic deltas (additive edge add, breaking edge removal, breaking ledger-variant removal via $defs, breaking TransitionEvent required-field removal).
- Extended `tests/fence/test_workflows_public_surface.py` — allowlist split into S1-01 + S1-02 partitions (11 new names added).
- Extended `tests/unit/workflows/test_vuln_sut_shape.py` — `__all__` pin amended additively (S1-01 + S1-02 union).
- Extended `tests/unit/types/test_identifiers_phase3.py` — `PHASE6_NEWTYPE_NAMES` grew from 3 → 4 (`TransitionId`).
- Regenerated `tests/golden/phase6-contract/snapshot.json` under `PHASE6_CONTRACT_GOLDEN_REWRITE=1`.

### Mutation-resistance checks performed (per AC mutation-thinking)
- AC-2: `discriminator="kind"` swap → `Field()` → AC-2 round-trip + collision tests fail (Pydantic loses union-tag and falls back to structural matching).
- AC-2: structural-overlap test (`{"kind":"completed","patch_digest":"a"*64}`) — fails with discriminator on (extra fields forbidden); would silently route to `PatchApplied` without it.
- AC-5: replacing `_LEGAL_TRANSITIONS` with `frozenset()` → AC-5 positive parametrize fails on the first edge.
- AC-5: replacing `model_validator` body with `return self` → all `_illegal_pairs` tests fail.
- AC-5: accidentally adding `("completed", "needs_plan")` → operationally-terminal absorbing test fails immediately.
- AC-8: dropping a field from `event.model_dump_json()` (e.g. omitting evidence_digest from payload) → sensitivity property fails on otherwise-identical events that differ only in evidence.
- AC-8: routing chain-head through `time.time()`-tinted bytes → AST fence fails loud.
- AC-12: removing `model_config = _FROZEN_FORBID` from any variant → fence fails with file::class location.

### Decisions of record (one line each)
- **`triggering_outcome: JsonValue` (not a discriminated union of `RecipeOutcome | NodeTransition | TrustOutcome`).** Story prose enumerated all three, but `NodeTransition.Advance.state: SubgraphState` forward-ref forces `model_rebuild()` and couples `vuln_ledger.py` to `codegenie.plugins.subgraph` (out of Phase-6 scope; also closes a kernel cycle). Also, no `GateOutcome` type exists in the codebase — closest is `TrustOutcome` which is a single class, not a sum type. The substrate only needs deterministic JSON bytes for the chain-head — the typed shape lives on the producer side (S3-01 subgraph nodes serialise via `outcome.model_dump(mode='json')` before constructing). Documented in the module docstring + this attempt log. **Surfaced for downstream review.**
- **`ChainHead` returns bare 64-hex (no `"blake3:"` prefix).** Story TDD-Green prose said `ChainHead(f"blake3:{hex}")`, but the existing `ChainHead` newtype is 64-hex without prefix (verified by `parse_chain_head` in `codegenie.types.parsers` + every existing call site in `rag/store.py` and `plugins/events.py`). Rule 11 (match conventions) wins. The `_chain.py` helper strips the `"blake3:"` prefix from `content_hash_bytes`'s return value to keep the newtype shape stable. **Story Green prose has minor inconsistency; behavior matches existing convention.**
- **AC-5 "terminal" has two definitions; AC-3 vs §3 disambiguated.** *Class-level terminal* (used by AC-6 + S1-01 `TerminalState` Literal) = `{completed, awaiting_human_review, failed_unrecoverable}` (three). *Operationally terminal* (used by AC-5 §3 "zero outgoing edges") = `{completed, failed_unrecoverable}` (two). `awaiting_human_review` is class-level terminal AND operationally resumable (`→ plan_ready`, `→ completed`, `→ failed_unrecoverable`). The test split — `test_ac5_operationally_terminal_states_have_zero_outgoing_edges` vs `test_ac6_terminal_partition_byte_equal...` — pins both definitions.
- **AC-12 fence scoped to `codegenie/workflows/*.py` (excludes `_frozen.py`).** The canonical-declaration file for `_FROZEN_FORBID` does not define any `BaseModel` subclasses (it only declares the constant); including it in the AST walk produces a false-positive "no BaseModel found" miss.
- **`_FROZEN_FORBID` is imported, never inlined.** All seven variants + `TransitionEvent` set `model_config = _FROZEN_FORBID`; the AST fence at `tests/fence/test_workflows_frozen_forbid.py` walks every `BaseModel` and requires literal `Name(id="_FROZEN_FORBID")` on the RHS.
- **`_LEGAL_TRANSITIONS` is a `Final` `frozenset`, NOT a registry.** Closed-set Phase-6 data, not pluggable strategies. Rule-of-three threshold for a registry mirrors phase-3 ADR-0010 §grammar table — three concrete ledgers (Phase 6 vuln, Phase 7 migration, future task class) would justify, not two.
- **File name `vuln_ledger.py`, not `ledger.py`.** Open/Closed at the file boundary. Phase 7's `migration_ledger.py` will land beside without editing this file (anti-refactor #4 honored).

### Test counts touched
- Suite-level: **7265 passed, 43 skipped, 9 xfailed** (pre-existing baseline) — net +175 new tests.
- Phase-6 new file counts: 8 new + 4 amended.
- Mypy: 239 source files clean under `--strict`.
- Import-linter: 12 contracts kept, 0 broken.
- Fence: 497 tests, 1 skipped (Phase-6.5 placeholder).

### Notes for downstream stories
- **S2-01 (semantic checkpoints / SQLite store):** writes `TransitionEvent` rows; computes `chain_head` via the helper landed here (do NOT re-implement). The S2-01 attempt log already references this story's helper.
- **S2-02 (replay verification):** walks the chain via `_compute_chain_head` and rejects any divergence with `FailedUnrecoverable(reason="checkpoint_integrity")`. The chain-head purity fence guards against future drift.
- **S3-01 (plugin-local subgraph):** produces `TransitionEvent`s via the conditional edges, dispatches on `LedgerStateKind` for next-node selection, and routes `triggering_outcome` through `outcome.model_dump(mode='json')` before constructing the event (per the JsonValue substrate decision).
- **S4-01 (HITL):** consumes `AwaitingHumanReview.handoff_path` + the `awaiting_human_review → plan_ready` legal transition. The two-definitions-of-terminal nuance matters here: HITL is class-level terminal but operationally resumable.
- **Phase 6.5 / Phase 9 G5:** byte-equality across `LocalVulnRemediationSut` / `TemporalVulnRemediationSut` is reachable because both fold events through the same pure helper. The AST purity fence is the load-bearing guard.
- **Phase 7 migration ledger:** `migration_ledger.py` lands beside `vuln_ledger.py` with its own seven-or-more variants and its own `_LEGAL_TRANSITIONS`. Rule-of-three for a `LedgerStateRegistry` only meaningful at the third concrete ledger (Phase 8+).

### Follow-ups surfaced this attempt
- **Story prose `ChainHead("blake3:<64hex>")` inconsistency** — should be patched in the story or a clarifying note added in the validation report so the next executor doesn't re-derive this decision. (Minor; no code change.)
- **Story prose `GateOutcome` vs codebase `TrustOutcome`** — same fix; the story can name the actual type or explicitly defer the union to S3-01. (Minor; no code change.)
- **Class-level vs operational terminal disambiguation** — could land as a one-paragraph note in the story's "Notes for the implementer" so the next reader (test author, story validator, executor) doesn't trip the same wire. (Minor; no code change.)
