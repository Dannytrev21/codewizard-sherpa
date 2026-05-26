# Validation report — Story S7-03 — `CostEmitter` + `SandboxCostEntry` schema (Gap 5)

**Story:** [`../S7-03-cost-emitter-sandbox-cost-entry.md`](../S7-03-cost-emitter-sandbox-cost-entry.md)
**Validated:** 2026-05-25
**Validator:** `phase-story-validator` (single-agent inline mode)
**Validator agent run:** automated (`story-validation-corrector` scheduled task)
**Verdict:** **HARDENED**

## Summary

S7-03 closes Phase 5 Gap 5 by giving Phase 13 a frozen `SandboxCostEntry` Pydantic contract + a `CostEmitter` that appends one canonical-JSON line per `GateRunner` attempt to `.codegenie/cost/sandbox.jsonl` with a byte-stable golden file. The draft's goal and 11-AC scope were directionally correct — right schema, right append-only contract, right post-`RetryLedger.record` wiring point. But every block-tier finding traced to either (a) consistency drift with HARDENED siblings (S1-02 named this story as the `RunId` consumer; S5-02 froze `GateRunner.__init__` keyword-only and `GateRunner.run` as `async def`; ADR-0004 pairs `backend ↔ gate_isolation_class`), (b) primitive-obsession on identifiers, or (c) implementer-notes invariants that were never pinned as observable ACs.

Counting: **22 findings — 7 block-tier, 11 harden-tier, 4 nit-tier.** The blocks would have produced reachable structural bugs the executor's validator would have missed: a sync `def` test against an `async def run` (vacuous-pass coroutine binding); raw `str` fields where S1-02 explicitly named this story as the `RunId` downstream consumer; a `mode="ab"` append with no `\n` terminator (visible in the splitlines test but unspecified in the contract); a hardcoded `CostEmitter()` default that writes to CWD instead of resolving against `GateContext.workflow_root`; and an illegal `(backend="firecracker", gate_isolation_class="shared_kernel")` pairing that would silently mis-aggregate in Phase 13. The hardens close mutation-resistance gaps (a byte-stable test that derives its golden from the same implementation is vacuous on canonicalization itself — the property test that *kwarg order doesn't change output bytes* is the load-bearing mutation witness); pin clock injection so the golden survives non-deterministic time; and tie loose ends to CLAUDE.md commitments (functional core / imperative shell; "Make illegal states unrepresentable"; structural fence under `tests/fence/`).

**No `RESCUE`-tier findings.** The goal traces cleanly to ADR-0010 + `phase-arch-design.md §Gap 5`; every gap was patchable by pinning against HARDENED siblings (S1-02, S1-04, S2-01, S5-02, S7-02) and the existing `tests/golden/contracts/` + `tools/regenerate_*.py` precedents. **No Stage-3 research needed** — all findings answerable from in-repo sources.

## Context Brief (Stage 1)

### Story snapshot

- **Goal (verbatim):** Land `src/codegenie/sandbox/cost.py` with a frozen `SandboxCostEntry` Pydantic model and a `CostEmitter` that writes one append-only JSONL row per `GateRunner` attempt to `.codegenie/cost/sandbox.jsonl`, with a byte-stable golden-file contract test.
- **Non-goals (Out-of-scope, hardened):** Phase 13's dashboard / cap / `CostReader`; token-cost emission (Phase 4 owns); backend-specific fields (additive ADR-0010 amendments); migrating prior content; introducing `GateId` NewType (S1-04 explicit decision); renaming or removing any S5-02-locked `GateRunner.__init__` parameter; introducing a `Protocol` for `CostEmitter` (Rule 2 cap — only two consumers exist).

### Phase 5 exit criteria touched

- **Step 7 done-criteria (`High-level-impl.md §Step 7`):** "`CostEmitter` emits one row per attempt — Phase 13 contract sample asserted via golden file."
- **`phase-arch-design.md §Gap 5`:** the verbatim schema; the file path; the contract test mandate.
- **ADR-0010:** schema-as-contract; one entry per attempt; `extra="forbid", frozen=True`; field path `.codegenie/cost/sandbox.jsonl`.
- **ADR-0004:** `backend ↔ gate_isolation_class` pairing (`docker_in_docker ↔ shared_kernel`, `firecracker ↔ microvm`).
- **ADR-0014:** `extra="forbid", frozen=True` discipline + static introspection.

### Load-bearing commitments touched

- **CLAUDE.md "Newtype identifiers":** `RunId` (S1-02 names this story as a downstream consumer at line 21), `WorkflowId` (`types/identifiers.py:82` per S1-04 line 58). Raw `str` for these violates the rule and breaks the type-checker barrier Phase 13 will rely on.
- **CLAUDE.md "Functional core / imperative shell":** S7-02 HARDENED already established this pattern with `_recorder.py`'s pure/impure split. This story is the second concrete consumer of the pattern in Phase 5.
- **CLAUDE.md "Make illegal states unrepresentable":** the `backend ↔ gate_isolation_class` pairing must be enforced at construction, not at consumer-side aggregation.
- **CLAUDE.md "Structural defenses live under `tests/fence/`":** a new `sandbox/` submodule + a new ADR-locked schema requires a fence test.
- **CLAUDE.md "Match the existing convention":** golden path is `tests/golden/contracts/*.json` (precedent: `sandbox_jail.schema.json`); regen script is `tools/regenerate_*.py` (precedent: `regenerate_probe_schemas.py`).

### Adjacent / prerequisite stories cited

| Story | Status | What S7-03 reuses |
|---|---|---|
| [S1-02](../S1-02-sandbox-contract-protocol-models.md) | HARDENED (2026-05-16) | `RunId` NewType from `codegenie.sandbox.contract` (line 21 names this story); `SandboxRun.microvm_seconds`, `image_pull_bytes`, `build_cache_hit` fields |
| [S1-04](../S1-04-gates-contract-abc-models.md) | HARDENED (2026-05-22) | `GateContext.workflow_root` path source; `WorkflowId` newtype reference (line 58); explicit `gate_id: str` non-newtype decision (line 1237) |
| [S2-01](../S2-01-retry-ledger-blake3-chain.md) | HARDENED | `RetryLedger.record(attempt)` is the predecessor call; `Attempt` model |
| [S5-02](../S5-02-gate-runner-retry-loop.md) | HARDENED (2026-05-25) | `GateRunner(*, client, gate, ledger, spec_builder, max_attempts=3, replan_hook=None)` — keyword-only; `async def run(self, ctx: GateContext) -> GateOutcome`; the post-`record(attempt)` wiring point |
| [S7-02](../S7-02-perf-regression-gates.md) | HARDENED (2026-05-25) | `_recorder.py` pure/impure split precedent; Pydantic-pinned trend-row schema discipline |

## Critic findings

### Critic A — Coverage (does the AC set guarantee the goal?)

| # | Severity | Finding | Resolution |
|---|---|---|---|
| C-A-1 | block | `build_cache_hit` source is unspecified. ADR-0010 §Consequences lists it as a field, but the story's AC #6 wires `microvm_seconds` and `image_pull_bytes` only. A future reader cannot tell whether `build_cache_hit` reads from `SandboxRun` or is set by the runner. | AC-FIELDS-1 pins `build_cache_hit ← SandboxRun.build_cache_hit` (default `False`); AC-FIELDS-2 makes the wiring map a frozen `_FIELD_MAP` constant. |
| C-A-2 | block | Cost-emit failure must not propagate is in Notes #6 but never pinned as an AC. The executor's validator scans ACs, not Notes. | AC-FAIL-NOPROP-1 — `tests/sandbox/test_cost_emit_failure.py` patches `_recorder.append_jsonl_line` to raise `OSError`; asserts (a) outcome returned unaltered, (b) `gates.runner.cost.emit.failed` event emitted, (c) ledger row preserved, (d) no cost row for the failed emit. |
| C-A-3 | harden | `.codegenie/cost/` gitignore is implicit (parent `.codegenie/` ignore). No AC verifies coverage; a future change to `.gitignore` could silently expose the cost ledger to commits. | AC-GITIGNORE-1 / -2 — `git check-ignore -q` returns exit code 0. |
| C-A-4 | harden | `__all__` widening on `sandbox/__init__.py` is unspecified. S1-02 AC-1a pinned a frozen `__all__` set; this story widens it but no AC enforces the additive contract. | AC-EXPORT-1 — frozen-set assertion: `__all__ == EXISTING ∪ {"CostEmitter", "SandboxCostEntry", "to_jsonl_bytes"}`. |
| C-A-5 | nit | No `Status` HARDENED stamp; sibling stories use `Ready (HARDENED YYYY-MM-DD)`. | Status updated to `Ready (HARDENED 2026-05-25)`. |
| C-A-6 | nit | The `# WARNING:` comment requirement (Refactor §3) was only a refactor step, not an AC. | AC-COMMENT-1 promotes it; AC-FENCE-1 provides defense-in-depth. |

### Critic B — Test Quality (mutation thinking)

| # | Severity | Finding | Resolution |
|---|---|---|---|
| C-B-1 | block | The byte-stable golden test is vacuous on canonicalization itself: both file and check derive from the same impl. Any deterministic implementation passes its own golden. The real load-bearing property is "kwarg order doesn't change output bytes" — that's what a wrong canonicalization breaks. | AC-MUT-1 — Hypothesis-style property: same field values, kwargs in different orders ⇒ identical bytes. |
| C-B-2 | block | "Two emits append two lines (not overwrite)" passes if implementation writes `lineA\nlineB\n` OR `lineB\nlineA\n` (order swapped) OR with stray whitespace. | AC-APPEND-1 — exact concatenation: `read_bytes() == golden_bytes + golden_bytes`. |
| C-B-3 | block | JSONL newline terminator is unspecified in the contract — only inferred by the `splitlines()` assertion. A reader has to guess at the wire shape. | AC-NL-1 (`to_jsonl_bytes` ends in `b"\n"`); AC-NL-2 (golden file ends in `0x0A`). |
| C-B-4 | harden | The lazy-mkdir invariant ("subsequent emits do not stat the directory") is in the ACs but has no test. | AC-LAZY-DIR-1 + `test_emit_mkdir_called_exactly_once` (monkeypatches `Path.mkdir`). |
| C-B-5 | harden | The naive-datetime failure mode is in implementer Notes #2 but no test pins it. A future Pydantic config change could silently accept naive datetimes; Phase 13's `fromisoformat` would then fail at read time. | AC-DT-1 + `test_cost_entry_naive_datetime_rejected`. |
| C-B-6 | harden | The order test uses "spy/mocks" with no concrete shape. MagicMock interleavings across async boundaries are notoriously flake-prone. | AC-ORDER-1 — single shared `events: list[tuple[str, AttemptNumber]]` that both spies append to; assert the exact flattened sequence across all attempts in a 3-retry scenario. |
| C-B-7 | harden | The `model_copy(update={"microvm_seconds": 1.5})` mutation witness covers float fields; no witness for bool. A boolean serialization bug (e.g., `True` → `"true"` instead of `true`) goes undetected. | AC-MUT-3 — `to_jsonl_bytes(model_copy(update={"build_cache_hit": False})) != to_jsonl_bytes(entry)`. |

### Critic C — Consistency (arch / ADR / commitment)

| # | Severity | Finding | Resolution |
|---|---|---|---|
| C-C-1 | block | Primitive obsession on `RunId`. S1-02 line 21 explicitly names this S7-03 story as a downstream consumer of the `RunId` NewType. Draft types `run_id: str` and `sandbox_run_id: str`. | AC-NT-1, AC-NT-2 — pin `RunId` via `typing.get_type_hints`. |
| C-C-2 | block | Primitive obsession on `WorkflowId`. `WorkflowId` is defined in `types/identifiers.py:82` per S1-04 line 58. Draft types `workflow_id: str`. | AC-NT-3 — pin `WorkflowId`. |
| C-C-3 | block | `GateRunner.__init__` is keyword-only with 6 deps locked by S5-02 AC-CTOR-1. Draft says "Inject `self._cost: CostEmitter` via `__init__` with a default constructor" — wording is ambiguous between (a) `cost: CostEmitter` as a 7th positional/keyword param and (b) `cost: CostEmitter = CostEmitter()` defaulting to a CWD-relative path. Either reading drifts from S5-02. | AC-WIRE-CTOR-1 — additive seventh keyword-only `cost: CostEmitter | None = None`; AC-WIRE-CTOR-2 — when `None`, resolve from `ctx.workflow_root`; AC-WIRE-CTOR-3 — `inspect.signature` keyword-only assertion mirrors S5-02. |
| C-C-4 | block | `GateRunner.run` is `async def` per S5-02 AC-ASYNC-1. Draft TDD's order test uses sync `def` against `await runner.run(ctx)`. | AC-WIRE-ASYNC-1 — order test is `async def`; repo's `asyncio_mode = "auto"` makes `@pytest.mark.asyncio` redundant. |
| C-C-5 | block | `backend ↔ gate_isolation_class` pairing (ADR-0004) is two `Literal`s that must agree — no validator enforces the invariant. A caller can construct `SandboxCostEntry(backend="firecracker", gate_isolation_class="shared_kernel")` and Phase 13's per-isolation-class aggregation silently mis-classifies. | AC-PAIR-1 — `@model_validator(mode="after")` raises `ValueError`; AC-PAIR-2 — parametrized property test enumerates all 4 combinations. |
| C-C-6 | harden | Golden file path drift. Existing convention is `tests/golden/contracts/*.json` (precedent: `sandbox_jail.schema.json`); draft uses `tests/golden/cost_entry_canonical.json` at the root. | AC-PATH-1 — `tests/golden/contracts/cost_sandbox_run_entry.json`. |
| C-C-7 | harden | `tools/regen_cost_golden.py` naming drift. Project precedent is `tools/regenerate_*.py` (`regenerate_probe_schemas.py`). | AC-TOOL-1 — `tools/regenerate_cost_golden.py`. |
| C-C-8 | harden | No `tests/fence/` structural defense for the new module + ADR-locked schema. CLAUDE.md commits: "New ... `src/codegenie/` submodule ... requires conformance." | AC-FENCE-1 — `_FIELD_NAMES` snapshot + AST purity scan on `to_jsonl_bytes`. |
| C-C-9 | nit | References block omitted S5-02-HARDENED, S7-02-HARDENED, and the in-repo NewType source paths. | References block extended with all sibling validation reports + NewType source paths + CLAUDE.md commitment list. |

### Critic D — Design Patterns

| # | Severity | Finding | Resolution |
|---|---|---|---|
| C-D-1 | harden | Functional core / imperative shell split missing (CLAUDE.md commitment). `CostEmitter.emit` mixes pure canonical-JSON serialization with impure file I/O. S7-02 HARDENED established the pattern with `_recorder.py` — this story is the second concrete consumer; not yet rule-of-three but the split is cheap and standard. | AC-PURE-1 — `to_jsonl_bytes` is a module-level pure function; AC-PURE-2 — AST scan asserts no I/O / clock references in its body. |
| C-D-2 | harden | Clock injection missing — golden test pins fixed `datetime(2026, 5, 12, …)` but the runner-wiring path calls `datetime.now(UTC)`. Without injection, the golden cannot survive non-deterministic clock; the test will pass only because the test sets `emitted_at` explicitly in the fixture, not because the wiring is testable. | AC-CLOCK-1 — `CostEmitter.__init__(*, ledger_path, clock=lambda: datetime.now(UTC))`; AC-CLOCK-2 — wiring path constructs entries via `emit_for(attempt, run, ctx)` which uses the injected clock. |
| C-D-3 | harden | "Make illegal states unrepresentable" applies to the `backend ↔ gate_isolation_class` pair. The validator-side fix (AC-PAIR-1) lands the invariant at construction time — illegal pairs simply cannot exist. Pure tagged-union encoding was considered and rejected: Phase 13's JSON reader expects a flat schema; pair validator delivers the same guarantee without breaking the wire format. | AC-PAIR-1, AC-PAIR-2 (also classified under Consistency block C-C-5; design-patterns lens reinforces the choice). |
| C-D-4 | harden | The wiring path inside `GateRunner.run` mixes pure entry-construction with impure file I/O. The `emit_for(attempt, run, ctx)` builder convenience keeps the runner code at the imperative-shell layer; entry construction (pure) lives inside the emitter. | AC-EMIT-2 — `emit_for` builder convenience; runner calls `emit_for`, not `emit` directly. |
| C-D-5 | harden | `_FIELD_MAP` as a `Final[Mapping]` is the Open/Closed seam: future additive ADR-0010 amendments add a key, no edits to runner wiring. | AC-FIELDS-2 — `_FIELD_MAP` constant; the builder consumes it. |
| C-D-6 | nit | No `Protocol` for `CostEmitter` proposed — and that's intentionally correct (Rule 2 cap; only two consumers exist). Story should document this for the next consumer to know when to lift. | Notes for the implementer §15 — explicit Rule-2 commentary. |
| C-D-7 | nit | The structural fence test (`tests/fence/test_sandbox_cost_module_static.py`) is the canonical extension-by-addition guard. Worth documenting that adding a new field requires *both* an ADR-0010 amendment AND a golden regen AND a `_FIELD_NAMES` snapshot bump — three loud failures, not one. | Notes for the implementer §14 — defense-in-depth between AC-COMMENT-1 + AC-FENCE-1. |

## Stage 3 — Research

**Not invoked.** Every gap was answerable from HARDENED sibling validation reports (S1-02, S1-04, S2-01, S5-02, S7-02) + the ADRs (0004, 0010, 0014) + CLAUDE.md commitments + the existing in-repo precedents (`tests/golden/contracts/`, `tools/regenerate_*.py`). No arXiv / library docs / external research required.

## Conflict resolutions

- **Coverage vs Design-Patterns on `_FIELD_MAP`.** Coverage wanted an explicit field-mapping AC (C-A-1); Design-Patterns wanted an Open/Closed seam (C-D-5). The two converge on the same `_FIELD_MAP: Final[Mapping[str, str]]` constant — Coverage gets an observable AC (AC-FIELDS-2), Design-Patterns gets the extension seam recorded in Notes for the implementer §13.
- **Design-Patterns vs Rule 2 on a `Protocol` for `CostEmitter`.** Only two consumers exist; Rule 2 wins. Pattern advice landed in Notes for the implementer §15 ("if a third consumer arrives, lift the Protocol then"), NOT as an AC.
- **Consistency vs Design-Patterns on tagged-union vs flat-schema for the backend/iso-class pair.** Consistency wins (Phase 13's reader expects a flat schema per ADR-0010 §Consequences). Design-Patterns' "make illegal states unrepresentable" is delivered via the model_validator instead (AC-PAIR-1) — same guarantee, flat wire shape preserved.

## Edits applied

The story file at [`../S7-03-cost-emitter-sandbox-cost-entry.md`](../S7-03-cost-emitter-sandbox-cost-entry.md) was edited in place. Summary:

### 1. Status line
- Before: `**Status:** Ready`
- After: `**Status:** Ready (HARDENED 2026-05-25)`

### 2. Depends-on expanded
- Before: `S5-02`
- After: `S1-02 (RunId), S1-04 (GateContext), S2-01 (RetryLedger.record), S5-02 (GateRunner ctor + async run — HARDENED)`

### 3. New `Validation notes (2026-05-25)` block
Appended after the header. Cross-links every block-tier finding to the AC that resolves it.

### 4. References block
Extended with: S5-02-HARDENED ctor surface; `RunId` source (S1-02 line 21 naming this story as consumer); `WorkflowId` source (`types/identifiers.py:82`); `tests/golden/contracts/sandbox_jail.schema.json` precedent; `tools/regenerate_probe_schemas.py` precedent; sibling `_validation/S7-02` (pure/impure split); CLAUDE.md commitments enumerated.

### 5. Acceptance criteria — replaced the 11-AC draft with a sectioned 35-AC hardened set
Headers: **A.** Module surface + exports (2) | **B.** `SandboxCostEntry` schema (10) | **C.** Canonical byte serialization (7) | **D.** `CostEmitter` (7) | **E.** `GateRunner` wiring (6) | **F.** Golden file + regen tool (3) | **G.** Structural fences + gitignore (3) | **H.** Project gates (2). Every AC carries an `AC-XX-N` ID; every observable claim has a paired test in the rewritten TDD plan.

### 6. Implementation outline — replaced the 8-step prose with a numbered 11-step outline
Names: pure `to_jsonl_bytes` helper; `_FIELD_NAMES` + `_LEGAL_PAIRS` + `_FIELD_MAP` module constants; `CostEmitter(*, ledger_path, clock=...)` keyword-only with `emit_for(attempt, run, ctx)` builder; additive seventh `cost: CostEmitter | None = None` keyword-only param on `GateRunner.__init__`; lazy ctx-resolved factory; OSError-swallowed wiring with `gates.runner.cost.emit.failed` event.

### 7. TDD plan rewrite
Red examples now: (a) NewType-typed fixtures; (b) `to_jsonl_bytes` purity + field-order-independence + value-change witnesses; (c) parametrized pairing-invariant test (4 combinations); (d) naive-datetime rejection; (e) byte-stream concatenation assertion (not splitlines); (f) lazy-mkdir witness; (g) async failure-doesn't-propagate test; (h) shared-list recorder for ledger-then-cost ordering across 3 retries; (i) AST purity scan on the pure helper.

### 8. Files to touch
Extended with: `test_cost_emit_failure.py`; `test_cost_emitter_gitignore.py`; `test_sandbox_cost_module_static.py` (fence); `tools/regenerate_cost_golden.py` (renamed); golden path corrected to `tests/golden/contracts/cost_sandbox_run_entry.json`; `.gitignore` row.

### 9. Out of scope
Added: editing S5-02-locked `GateRunner.__init__` parameters beyond additive `cost=`; introducing `GateId` NewType (S1-04 explicit Rule-2 decision); introducing a `Protocol` for `CostEmitter` (Rule 2 cap — only two consumers); re-flowing existing structured-event taxonomy (only one new event added: `gates.runner.cost.emit.failed`).

### 10. Notes for the implementer
Expanded from 6 prose notes to 15 sections covering: serialization formula + trailing newline; ISO-8601 + naive-datetime rejection; `extra="forbid"` contract weight; `mode="ab"` rationale; wiring order; failure-no-propagate idiom; NewType discipline + the deliberate `gate_id: str` exception; functional core / imperative shell with the S7-02 precedent named; illegal-states-unrepresentable framing; `GateRunner.__init__` additive-only extension; golden path + tools naming conventions; Phase 6 lift implications; structural fence + WARNING comment defense-in-depth; the deliberate absence of a `Protocol` (Rule 2 commentary for the next consumer).

## Verdict

**HARDENED.** The goal is sound and traces to ADR-0010 + `phase-arch-design.md §Gap 5`; the prescribed implementation had primitive-obsession reachability bugs, an unspecified wire-format byte contract, missing observable ACs for implementer-notes invariants, and an illegal-state-representable schema pair. All 22 findings are now closed by ACs that reference HARDENED siblings (S1-02, S1-04, S2-01, S5-02, S7-02) + the existing golden / tools / fence precedents. The executor's first attempt has a fighting chance.

**Pre-conditions to flag for the executor:**
- S1-02 (`RunId` NewType), S1-04 (`GateContext.workflow_root`), S2-01 (`RetryLedger.record`), and S5-02 (`GateRunner` async + keyword-only ctor) must be GREEN before this story can execute.
- If any of the above is still BLOCKED or pre-GREEN at executor time, this story is blocked; do not stub. The executor's attempt log should record the missing precondition and stop.

## Recommended next step

`phase-story-executor` to implement.
