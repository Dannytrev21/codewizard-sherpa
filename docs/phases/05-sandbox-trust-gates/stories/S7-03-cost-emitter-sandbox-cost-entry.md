# Story S7-03 — `CostEmitter` + `SandboxCostEntry` schema (Gap 5)

**Step:** Step 7 — Adversarial test suite + performance regression gates
**Status:** Ready (HARDENED 2026-05-25)
**Effort:** S
**Depends on:** S1-02 (`RunId` NewType in `sandbox/contract.py`), S1-04 (`GateContext`), S2-01 (`RetryLedger.record`), S5-02 (`GateRunner(*, …)` async ctor surface — HARDENED 2026-05-25)
**ADRs honored:** ADR-0010 (cost ledger contract), ADR-0014 (`extra="forbid", frozen=True` discipline), ADR-0004 (`backend ↔ gate_isolation_class` pairing)

## Validation notes (2026-05-25)

Four-critic pass (coverage / test-quality / consistency / design-patterns) run inline. **Verdict: HARDENED.** Original draft's goal + 11-AC scope were directionally correct, but every block-tier finding traced to either (a) pre-S5-02-HARDENED consistency drift, (b) primitive-obsession on identifiers S1-02 explicitly named this story as the downstream consumer for, or (c) a missing observable AC for invariants the implementer notes already imply.

**Counting: 22 findings — 7 block-tier, 11 harden-tier, 4 nit-tier.** No `RESCUE`-tier findings; the goal traces cleanly to ADR-0010 + `phase-arch-design.md §Gap 5`.

Headline block-tier edits (each one would have produced a structurally-wrong implementation the executor's validator could have missed):

1. **(consistency — block) Primitive obsession on `RunId`.** S1-02 line 21 names this S7-03 story as a downstream consumer of the `RunId` NewType: "crosses ≥ 5 module boundaries (S2-01 ledger, S3-01 builder, S5-02 runner, **S7-03 cost emitter**, S8-01 CLI)." Draft typed `run_id: str` and `sandbox_run_id: str`. Fix: AC-NT-1 / AC-NT-2 pin `run_id: RunId` and `sandbox_run_id: RunId` with `typing.get_type_hints` assertions.

2. **(consistency — block) `WorkflowId` exists in `types/identifiers.py:82` per S1-04 line 58.** Draft typed `workflow_id: str`. Fix: AC-NT-3 pins `workflow_id: WorkflowId`. `gate_id` correctly stays `str` per S1-04 line 1237's explicit Rule-2 non-newtype decision (recorded as `Out of scope`).

3. **(consistency — block) `GateRunner.__init__` is keyword-only with 6 deps locked by S5-02 AC-CTOR-1.** Draft says "Inject `self._cost: CostEmitter` via `__init__` with a default constructor." A default `CostEmitter()` writes to a CWD-relative path — not deterministic, breaks isolation. Fix: AC-WIRE-CTOR-1 pins `cost: CostEmitter | None = None` keyword-only as an **additive seventh** parameter; AC-WIRE-CTOR-2 asserts `cost is None` synthesizes a `CostEmitter` whose `ledger_path` is resolved from `GateContext.workflow_root / ".codegenie" / "cost" / "sandbox.jsonl"` (NOT from CWD); AC-WIRE-CTOR-3 asserts `inspect.signature(GateRunner.__init__)` is keyword-only for every parameter (mirrors S5-02 AC-CTOR-1).

4. **(consistency — block) `GateRunner.run` is `async def`** per S5-02 AC-ASYNC-1. Draft TDD's order test uses sync `def` against `await runner.run(ctx)`; sync invocation binds a coroutine and assertions vacuously succeed. Fix: AC-WIRE-ASYNC-1 — `test_runner_cost_order.py` is `async def`; the repo's `asyncio_mode = "auto"` makes `@pytest.mark.asyncio` redundant.

5. **(test-quality — block) JSONL newline terminator is unspecified.** Draft Implementation step 4 says `mode="ab"` + canonical JSON but never writes `\n`. Without it, two emits produce one merged JSON blob; the draft's own `splitlines() == 2` assertion would catch it but the implementer notes do not surface the contract. Fix: AC-NL-1 pins each emit writes exactly `<canonical-json> + b"\n"`; AC-NL-2 — golden file ends in `\n`; pure helper documents the contract.

6. **(coverage — block) Cost-emit failure must not propagate** is in Notes #6 but unpinned. A `harden` finding in the original notes is invisible to the executor's validator. Fix: AC-FAIL-NOPROP-1 — `tests/sandbox/test_cost_emit_failure.py` patches `_recorder.append_jsonl_line` to raise `OSError("disk full")`; asserts (a) `await GateRunner.run(ctx)` returns its `GateOutcome` unaltered, (b) `gates.runner.cost.emit.failed` structlog event emitted with `attempt_id`, (c) `attempts.jsonl` row IS written (ledger is the source of truth), (d) `.codegenie/cost/sandbox.jsonl` is empty or unchanged.

7. **(consistency — block) `backend ↔ gate_isolation_class` pairing is illegal-state-representable.** Two `Literal`s that must agree (`docker_in_docker ↔ shared_kernel`, `firecracker ↔ microvm` per ADR-0004) but no validator enforces the pairing. A caller can construct `SandboxCostEntry(backend="firecracker", gate_isolation_class="shared_kernel")` and Phase 13's per-isolation-class aggregation silently undercounts. Fix: AC-PAIR-1 — `@model_validator(mode="after")` raises `ValueError("invalid backend/gate_isolation_class pairing")` when the pair is mismatched; AC-PAIR-2 — Hypothesis property test enumerates all 4 combinations and asserts exactly the 2 ADR-0004 pairings construct successfully.

**Headline harden-tier edits** that close mutation gaps + design-pattern opportunities:

8. **(design-patterns — harden) Functional core / imperative shell split (CLAUDE.md commitment).** `CostEmitter.emit` mixes pure canonical-JSON serialization with impure file I/O + fsync. S7-02 HARDENED already established the split pattern (`_recorder.py` with pure `to_jsonl_line` + impure `append_jsonl_line`). Fix: AC-PURE-1 — `src/codegenie/sandbox/cost.py` exports `to_jsonl_bytes(entry: SandboxCostEntry) -> bytes` (pure; deterministic; no I/O imports) and `CostEmitter.emit` is the impure shell that calls it. AC-PURE-2 — AST scan asserts no `open(`, `os.`, `Path.write_*`, or `pathlib` reference inside `to_jsonl_bytes` body.

9. **(design-patterns — harden) Clock injection for determinism.** The golden test pins `emitted_at=datetime(2026, 5, 12, …)` but the `GateRunner` wiring path uses `datetime.now(UTC)` — the golden cannot survive non-deterministic clock. Fix: AC-CLOCK-1 — `CostEmitter.__init__(*, ledger_path: Path, clock: Callable[[], datetime] = lambda: datetime.now(UTC))`; tests inject a deterministic clock; production callsite uses the default. AC-CLOCK-2 — the wiring code in `GateRunner.run` constructs the entry by calling `self._cost.emit_for(attempt, sandbox_run, ctx)` (a thin builder on the emitter) so the clock injection point is the emitter, not the runner.

10. **(coverage — harden) `build_cache_hit` source is unspecified.** Draft AC #6 wires `microvm_seconds` and `image_pull_bytes` from `SandboxRun` but `build_cache_hit` source is silent. Fix: AC-FIELDS-1 — `build_cache_hit` reads `SandboxRun.build_cache_hit` (default `False` if not yet populated by a backend); AC-FIELDS-2 — schema-stability test pins the exact `SandboxRun → SandboxCostEntry` field mapping (the wiring is a pure helper, not inline runner code).

11. **(test-quality — harden) Mutation-witness for canonicalization.** The byte-stable golden test is vacuous if the emitter writes "anything that matches the golden" — both file and check derive from the same impl. Fix: AC-MUT-1 — Hypothesis property test: construct two `SandboxCostEntry` with identical field *values* but kwargs supplied in different orders; assert `to_jsonl_bytes(a) == to_jsonl_bytes(b)` (field-order independence). AC-MUT-2 — `to_jsonl_bytes(entry.model_copy(update={"microvm_seconds": 1.5})) != to_jsonl_bytes(entry)` (any value change ⇒ byte change).

12. **(consistency — harden) Golden file path matches existing convention.** `tests/golden/contracts/sandbox_jail.schema.json` is the established home for contract goldens. Draft `tests/golden/cost_entry_canonical.json` is at the root. Fix: AC-PATH-1 — golden file is `tests/golden/contracts/cost_sandbox_run_entry.json`.

13. **(consistency — harden) `tools/regen_cost_golden.py` naming.** Project precedent is `tools/regenerate_*.py` (`regenerate_probe_schemas.py`). Fix: AC-TOOL-1 — file is `tools/regenerate_cost_golden.py`; uses `argparse`; same shebang as the precedent.

14. **(coverage — harden) `__all__` export contract on `sandbox/__init__.py`.** S1-02 AC-1a pinned the existing `__all__` set. This story widens it. Fix: AC-EXPORT-1 — `set(codegenie.sandbox.__all__) == {existing 7 names} ∪ {"CostEmitter", "SandboxCostEntry", "to_jsonl_bytes"}`; frozen-set assertion catches accidental widening.

15. **(consistency — harden) Structural fence test for the new module.** CLAUDE.md "Structural defenses live under `tests/fence/`. New ... new `src/codegenie/` submodule ... requires conformance." Fix: AC-FENCE-1 — `tests/fence/test_sandbox_cost_module_static.py` asserts (a) module-level `_FIELD_NAMES: Final[frozenset[str]]` matches `set(SandboxCostEntry.model_fields)`; (b) any rename or addition breaks the test (forces ADR-0010 amendment); (c) `extra="forbid"` is set on the model.

16. **(test-quality — harden) Order-test recorder, not stacked mocks.** Draft uses "spy/mocks" — order-fragile (MagicMock interleavings). Fix: AC-ORDER-1 — `tests/gates/test_runner_cost_order.py` instantiates a single shared list `events: list[tuple[str, AttemptNumber]]`; both the spy `RetryLedger` and spy `CostEmitter` append `("ledger.record", n)` / `("cost.emit", n)` respectively; asserts the flattened sequence is `[("ledger.record", 1), ("cost.emit", 1), ("ledger.record", 2), ("cost.emit", 2), …]` for each attempt.

17. **(coverage — harden) Gitignore for `.codegenie/cost/`.** Phase 13 reads this path but local dev shouldn't commit it. Fix: AC-GITIGNORE-1 — confirm `.codegenie/` parent ignore (or `.codegenie/cost/` row) is present in `.gitignore`; AC-GITIGNORE-2 — `tests/sandbox/test_cost_emitter_gitignore.py` asserts `git check-ignore -q .codegenie/cost/sandbox.jsonl` returns exit code 0.

18. **(test-quality — harden) Two-emit append AC strengthened to byte-stream concatenation.** Draft says "two lines, not overwrite" — passes if implementation writes `lineA\nlineB\n` or `lineB\nlineA\n` (order-swapped). Fix: AC-APPEND-1 — `read_bytes() == golden_bytes + golden_bytes` (exact concatenation; preserves order).

**Nit-tier edits** align surface conventions:
- AC stamped onto `Status` line (`HARDENED 2026-05-25`)
- References table extended with newtype source paths and S5-02 ctor surface citation
- `Notes for the implementer` augmented with the functional-core / imperative-shell rationale + the S7-02 `_recorder` precedent
- Cross-link to `tests/golden/contracts/sandbox_jail.schema.json` as the golden-path precedent

**Stage 3 (research):** not invoked. Every gap was answerable from HARDENED sibling reports (S1-02, S1-04, S2-01, S5-02, S7-02) + ADR-0010 + ADR-0004 + CLAUDE.md. No arXiv / library docs needed.

Full audit log: `_validation/S7-03-cost-emitter-sandbox-cost-entry.md`.

## Context

`phase-arch-design.md §Gap 5` documents that Phase 13 reads `cost.sandbox.run` ledger entries from `.codegenie/cost/sandbox.jsonl` but Phase 5 never defined the shape, file path, or contract test — Phase 13 would silently undercount if the shapes drift. ADR-0010 makes the schema a Phase 5 contract. This story lands `sandbox/cost.py` with the `SandboxCostEntry` Pydantic model and the `CostEmitter`, wires `CostEmitter.emit()` into `GateRunner.run` post-`RetryLedger.record`, and ships the byte-stable golden-file contract test Phase 13 will pin against.

## References — where to look

- **Architecture:** `../phase-arch-design.md §Gap 5` — the schema is given verbatim in the gap
- **Architecture:** `../phase-arch-design.md §Component 6 CostEmitter` — wiring point
- **Phase ADRs:** `../ADRs/0010-cost-sandbox-run-ledger-schema.md` — full Decision, Tradeoffs, Consequences
- **Phase ADRs:** `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — frozen/extra=forbid discipline applies here too
- **Production ADRs:** `../../../production/adrs/0024-cost-observability-end-to-end.md` — downstream consumer context
- **Production ADRs:** `../../../production/adrs/0025-per-workflow-cost-cap.md` — Phase 13 will sum from this ledger
- **Implementation plan:** `../High-level-impl.md §Step 7` — lists `sandbox/cost.py` and `tests/sandbox/test_cost_emitter.py`
- **Existing code:** `src/codegenie/gates/runner.py` (from S5-02 HARDENED) — wiring point post-`RetryLedger.record`; `GateRunner.__init__` is keyword-only with 6 deps; `GateRunner.run` is `async def`
- **Existing code:** `src/codegenie/sandbox/contract.py` (from S1-02) — `SandboxRun.microvm_seconds`, `image_pull_bytes`, `build_cache_hit` fields the emitter reads; `RunId` NewType source (S1-02 names this story as a downstream consumer at line 21)
- **Existing code:** `src/codegenie/types/identifiers.py:82` (from S1-04 line 58) — `WorkflowId` NewType source
- **Existing code:** `tests/golden/contracts/sandbox_jail.schema.json` — golden-path convention precedent
- **Existing code:** `tools/regenerate_probe_schemas.py` — `regenerate_*.py` naming + Python-tools convention precedent
- **Sibling validation:** `_validation/S7-02-perf-regression-gates.md` — `_recorder.py` pure/impure split + Pydantic-pinned trend-row schema precedent
- **Sibling validation:** `_validation/S5-02-gate-runner-retry-loop.md` — keyword-only ctor + `async def run` surface
- **CLAUDE.md commitments:** "Newtype identifiers" (`RunId`, `WorkflowId`); "Functional core / imperative shell"; "Structural defenses live under `tests/fence/`"; "Make illegal states unrepresentable"

## Goal

Land `src/codegenie/sandbox/cost.py` with a frozen `SandboxCostEntry` Pydantic model and a `CostEmitter` that writes one append-only JSONL row per `GateRunner` attempt to `.codegenie/cost/sandbox.jsonl`, with a byte-stable golden-file contract test.

## Acceptance criteria

### A. Module surface + exports

- [ ] **AC-EXIST-1** — `src/codegenie/sandbox/cost.py` exists and exports `SandboxCostEntry`, `CostEmitter`, and `to_jsonl_bytes`. `from codegenie.sandbox.cost import …` is idempotent on a second import: `id(mod_first) == id(mod_second)`.
- [ ] **AC-EXPORT-1** — `src/codegenie/sandbox/__init__.py` widens `__all__` additively. Asserted: `set(codegenie.sandbox.__all__) == EXISTING_SET ∪ {"CostEmitter", "SandboxCostEntry", "to_jsonl_bytes"}` where `EXISTING_SET` is read at test time from the pre-S7-03 snapshot. Re-orderings, typos, or accidental widenings fail at unit-test time.

### B. `SandboxCostEntry` schema (Phase 13 contract — ADR-0010)

- [ ] **AC-MODEL-1** — `SandboxCostEntry(BaseModel)` carries `model_config = ConfigDict(extra="forbid", frozen=True)`. Asserted: `SandboxCostEntry.model_config["extra"] == "forbid"` AND `SandboxCostEntry.model_config["frozen"] is True`.
- [ ] **AC-MODEL-2** — exactly these fields, no more, no less (asserted by `set(SandboxCostEntry.model_fields) == {…}`): `entry_type`, `workflow_id`, `run_id`, `gate_id`, `sandbox_run_id`, `backend`, `gate_isolation_class`, `microvm_seconds`, `image_pull_bytes`, `build_cache_hit`, `emitted_at`.
- [ ] **AC-LIT-1** — `entry_type: Literal["cost.sandbox.run"]`; `backend: Literal["docker_in_docker", "firecracker"]`; `gate_isolation_class: Literal["shared_kernel", "microvm"]`. Asserted via `typing.get_type_hints(SandboxCostEntry)`.
- [ ] **AC-NT-1** — `run_id: RunId` (S1-02 NewType from `codegenie.sandbox.contract`). Asserted: `typing.get_type_hints(SandboxCostEntry)["run_id"] is RunId`.
- [ ] **AC-NT-2** — `sandbox_run_id: RunId`. Asserted: `typing.get_type_hints(SandboxCostEntry)["sandbox_run_id"] is RunId`. (S1-02 line 21 names this story as a downstream consumer.)
- [ ] **AC-NT-3** — `workflow_id: WorkflowId` (NewType from `codegenie.types.identifiers`). Asserted: `typing.get_type_hints(SandboxCostEntry)["workflow_id"] is WorkflowId`.
- [ ] **AC-NT-4** — `gate_id: str` (no NewType — per S1-04 line 1237 explicit Rule-2 decision). Documented as "intentionally `str`; Notes for the implementer §3."
- [ ] **AC-PAIR-1** — `@model_validator(mode="after")` enforces ADR-0004 pairing: raises `ValueError("invalid backend / gate_isolation_class pairing: …")` unless `(backend, gate_isolation_class) ∈ {("docker_in_docker", "shared_kernel"), ("firecracker", "microvm")}`. Asserted with all four (backend, gate_isolation_class) combinations: exactly two construct successfully; two raise `ValidationError` whose message names both fields.
- [ ] **AC-PAIR-2** — Hypothesis property test (`@given(backend=st.sampled_from([...]), iso=st.sampled_from([...]))`): enumerates all 4 combinations; legal pairs construct; illegal pairs raise.
- [ ] **AC-DT-1** — `emitted_at: datetime`. A naive datetime (no `tzinfo`) raises `ValidationError` at construction; aware datetimes accepted; serialization via `model_dump(mode="json")` yields ISO-8601 with explicit offset (e.g., `+00:00`).
- [ ] **AC-FORBID-1** — `SandboxCostEntry.model_validate({**fixture, "future_field": 1.0})` raises `ValidationError` whose message names `future_field` as the unknown key (ADR-0014 discipline).

### C. Canonical byte serialization (pure helper)

- [ ] **AC-PURE-1** — Module-level pure function `to_jsonl_bytes(entry: SandboxCostEntry) -> bytes` exists and is referentially transparent: same input ⇒ byte-identical output across processes / runs. The function is the **only** entry point that produces serialized bytes.
- [ ] **AC-PURE-2** — AST scan in `tests/fence/test_sandbox_cost_module_static.py` asserts the `to_jsonl_bytes` body has no `open(`, `os.`, `pathlib.`, `Path(`, `subprocess.`, `time.`, `datetime.now` references — i.e., no I/O, no clock, no environment. Pure relative to its argument.
- [ ] **AC-CANON-1** — `to_jsonl_bytes(entry)` produces `json.dumps(entry.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"`. Asserted via direct comparison against the canonical formula.
- [ ] **AC-NL-1** — Each emit writes exactly one trailing `\n` byte. Asserted: `to_jsonl_bytes(entry).endswith(b"\n")` AND `to_jsonl_bytes(entry).count(b"\n") == 1`.
- [ ] **AC-NL-2** — The golden file at `tests/golden/contracts/cost_sandbox_run_entry.json` ends in `\n` (the final byte is `0x0A`).
- [ ] **AC-MUT-1** — Hypothesis property test: construct two `SandboxCostEntry` with identical field *values* but kwargs supplied in different orders; assert `to_jsonl_bytes(a) == to_jsonl_bytes(b)` (field-order independence of serialization).
- [ ] **AC-MUT-2** — `to_jsonl_bytes(entry.model_copy(update={"microvm_seconds": 1.5})) != to_jsonl_bytes(entry)` (any value change ⇒ byte change).
- [ ] **AC-MUT-3** — `to_jsonl_bytes(entry.model_copy(update={"build_cache_hit": False})) != to_jsonl_bytes(entry)` (Boolean field also covered).

### D. `CostEmitter` (impure shell)

- [ ] **AC-CTOR-1** — `CostEmitter(*, ledger_path: Path, clock: Callable[[], datetime] = lambda: datetime.now(UTC))`. Keyword-only. `inspect.signature(CostEmitter.__init__)` asserts every param except `self` is `KEYWORD_ONLY`.
- [ ] **AC-CLOCK-1** — Tests inject a deterministic clock returning the fixed UTC moment used in the golden fixture; production callsite uses the `datetime.now(UTC)` default.
- [ ] **AC-EMIT-1** — `CostEmitter.emit(entry: SandboxCostEntry) -> None` appends `to_jsonl_bytes(entry)` to `self._ledger_path`. The implementation does (a) lazy `parent.mkdir(parents=True, exist_ok=True)` once, (b) `open(ledger_path, mode="ab")`, (c) `f.write(line)`, (d) `f.flush()`, (e) `os.fsync(f.fileno())` before close, (f) returns `None`.
- [ ] **AC-EMIT-2** — `CostEmitter.emit_for(attempt: Attempt, run: SandboxRun, ctx: GateContext) -> None` (builder convenience) constructs the entry from inputs + the injected clock and delegates to `emit`. The runner wiring calls `emit_for`, not `emit` directly.
- [ ] **AC-LAZY-DIR-1** — Subsequent emits do NOT call `mkdir` again. Asserted by patching `Path.mkdir` and counting calls across two emits == 1.
- [ ] **AC-FIELDS-1** — `microvm_seconds` reads `SandboxRun.microvm_seconds` (default `0.0`); `image_pull_bytes` reads `SandboxRun.image_pull_bytes` (default `0`); `build_cache_hit` reads `SandboxRun.build_cache_hit` (default `False`). For `backend == "docker_in_docker"`, `microvm_seconds == 0.0` is the invariant Phase 13 will pin (ADR-0010 §Consequences).
- [ ] **AC-FIELDS-2** — Schema-stability test pins the `SandboxRun → SandboxCostEntry` field mapping as a frozen dict in `cost.py` (`_FIELD_MAP: Final[Mapping[str, str]]`); the builder consumes it; any rename of a `SandboxRun` field breaks the test (forces an additive ADR-0010 amendment).
- [ ] **AC-APPEND-1** — Two emits of the same entry yield `ledger.read_bytes() == golden_bytes + golden_bytes` (exact byte-stream concatenation; preserves order — not just `splitlines() == 2`).

### E. `GateRunner` wiring (S5-02 additive extension)

- [ ] **AC-WIRE-CTOR-1** — `GateRunner.__init__` extends to add **exactly one** additive keyword-only parameter `cost: CostEmitter | None = None`. All other S5-02 AC-CTOR-1 parameters retain their names, defaults, and order; backward compatibility verified by `inspect.signature` snapshot.
- [ ] **AC-WIRE-CTOR-2** — When `cost is None`, the runner synthesizes a `CostEmitter(ledger_path=ctx.workflow_root / ".codegenie" / "cost" / "sandbox.jsonl")`. Path resolves against `GateContext.workflow_root` (NOT `Path.cwd()`).
- [ ] **AC-WIRE-CTOR-3** — `inspect.signature(GateRunner.__init__)` asserts every parameter except `self` is `KEYWORD_ONLY` (mirrors S5-02 AC-CTOR-1).
- [ ] **AC-WIRE-ASYNC-1** — Wiring call sits inside `async def run`; `tests/gates/test_runner_cost_order.py` is `async def` (repo's `asyncio_mode = "auto"`).
- [ ] **AC-WIRE-ORDER-1** — In each attempt iteration, `self._ledger.record(attempt)` is called BEFORE `self._cost.emit_for(attempt, run, ctx)`. Source: `attempts.jsonl` is the source of truth; `.codegenie/cost/sandbox.jsonl` is an additive ledger.
- [ ] **AC-ORDER-1** — `tests/gates/test_runner_cost_order.py`: instantiates a single shared `events: list[tuple[str, AttemptNumber]]`; spy `RetryLedger` appends `("ledger.record", n)` on each `record`; spy `CostEmitter` appends `("cost.emit", n)` on each `emit_for`; asserts the flattened sequence is `[("ledger.record", 1), ("cost.emit", 1), ("ledger.record", 2), ("cost.emit", 2), …]` across all attempts in a three-retry escalation scenario.
- [ ] **AC-FAIL-NOPROP-1** — `tests/sandbox/test_cost_emit_failure.py` patches `_recorder.append_jsonl_line` (or equivalent) to raise `OSError("disk full")` on every call. Asserts: (a) `await GateRunner.run(ctx)` returns its `GateOutcome` unaltered, (b) the structured event `gates.runner.cost.emit.failed` is emitted with keys `{attempt_id, error_class, error_message_redacted}`, (c) `attempts.jsonl` row IS written for the same attempt (ledger is the source of truth), (d) `.codegenie/cost/sandbox.jsonl` does NOT contain a row for the failed emit.

### F. Golden file + regen tool

- [ ] **AC-PATH-1** — Golden file location: `tests/golden/contracts/cost_sandbox_run_entry.json`. Matches the existing `tests/golden/contracts/sandbox_jail.schema.json` convention.
- [ ] **AC-PATH-2** — `tests/sandbox/test_cost_emitter.py` reads the golden via the project's standard relative path; emit-then-compare succeeds byte-for-byte.
- [ ] **AC-TOOL-1** — `tools/regenerate_cost_golden.py` (NOT `regen_*`): Python with `argparse`; shebang `#!/usr/bin/env python3`; runs the pure `to_jsonl_bytes` on the fixed fixture and atomically writes the bytes to `tests/golden/contracts/cost_sandbox_run_entry.json`; idempotent (`tests/golden/test_regen_golden_portfolio_idempotent.py` extension covers it).

### G. Structural fences + gitignore

- [ ] **AC-FENCE-1** — `tests/fence/test_sandbox_cost_module_static.py` asserts: (a) module-level `_FIELD_NAMES: Final[frozenset[str]]` matches `set(SandboxCostEntry.model_fields)`; (b) any field rename or addition breaks the test (forces ADR-0010 amendment); (c) `extra="forbid"` + `frozen=True` are set; (d) `to_jsonl_bytes` body has no I/O / clock imports (AST scan).
- [ ] **AC-GITIGNORE-1** — `.gitignore` covers `.codegenie/cost/sandbox.jsonl` (existing `.codegenie/` parent-level ignore already covers it; AC asserts coverage). Test `tests/sandbox/test_cost_emitter_gitignore.py` runs `git check-ignore -q .codegenie/cost/sandbox.jsonl` and asserts exit code 0.
- [ ] **AC-COMMENT-1** — A `# WARNING: any field change here requires an ADR-0010 amendment and a regenerated golden.` comment sits directly above the `SandboxCostEntry` class body (defense-in-depth alongside AC-FENCE-1).

### H. Project gates

- [ ] **AC-GATES-1** — `ruff`, `mypy --strict`, `pytest` pass. Story leaves coverage on `src/codegenie/sandbox/cost.py` at ≥ 95% line / ≥ 90% branch (matches Phase 5 §Step 7 done-criteria for `gates/runner.py` and `sandbox/contract.py`).
- [ ] **AC-TDD-1** — The red tests in §TDD plan exist, are committed, and are green after implementation.

## Implementation outline

1. **Create `src/codegenie/sandbox/cost.py`** with the layered shape (top-of-file: NewType imports + the WARNING comment; then `SandboxCostEntry`; then pure helper `to_jsonl_bytes`; then `CostEmitter`).
2. **Imports.** `from codegenie.sandbox.contract import RunId` (S1-02); `from codegenie.types.identifiers import WorkflowId` (S1-04 line 58); `from datetime import datetime, UTC`; `from pydantic import BaseModel, ConfigDict, model_validator, ValidationError`; `from typing import Final, Literal, Callable, Mapping`; `from collections.abc import Mapping as ABCMapping`; `import json, os`; `from pathlib import Path`.
3. **`SandboxCostEntry`.** `BaseModel` with `model_config = ConfigDict(extra="forbid", frozen=True)`. Field order matches the canonical JSON; `Literal` discriminators on `entry_type`, `backend`, `gate_isolation_class`. Domain identifier fields use `RunId` / `WorkflowId` NewTypes. A `@model_validator(mode="after")` enforces the ADR-0004 pairing (AC-PAIR-1). Module-level constants:
   - `_FIELD_NAMES: Final[frozenset[str]] = frozenset({...})` — the AC-FENCE-1 source of truth.
   - `_LEGAL_PAIRS: Final[frozenset[tuple[str, str]]] = frozenset({("docker_in_docker", "shared_kernel"), ("firecracker", "microvm")})` — drives the pairing validator.
4. **Pure helper `to_jsonl_bytes(entry: SandboxCostEntry) -> bytes`.** Returns `json.dumps(entry.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"`. **No I/O, no clock, no `datetime.now`** (AC-PURE-1, AC-PURE-2 — AST scan enforced). `model_dump(mode="json")` serializes `datetime` to ISO-8601 with explicit offset; the trailing `\n` is mandatory (AC-NL-1).
5. **`CostEmitter`.** Keyword-only `__init__(*, ledger_path: Path, clock: Callable[[], datetime] = lambda: datetime.now(UTC))`. Internal state: `_ledger_path: Path`, `_clock: Callable[[], datetime]`, `_parent_made: bool = False` (drives the `mkdir`-once invariant for AC-LAZY-DIR-1).
   - **`emit(entry)`:** if `not self._parent_made`, `self._ledger_path.parent.mkdir(parents=True, exist_ok=True)`; set `self._parent_made = True`. Open `self._ledger_path` with `mode="ab"`; `write(to_jsonl_bytes(entry))`; `flush()`; `os.fsync(f.fileno())`; close.
   - **`emit_for(attempt: Attempt, run: SandboxRun, ctx: GateContext) -> None`:** builds the entry via the `_FIELD_MAP: Final[Mapping[str, str]]` (AC-FIELDS-2), stamps `emitted_at = self._clock()`, delegates to `emit`.
6. **`_FIELD_MAP`.** `Final[Mapping[str, str]] = MappingProxyType({"microvm_seconds": "microvm_seconds", "image_pull_bytes": "image_pull_bytes", "build_cache_hit": "build_cache_hit"})`. Builder code reads `getattr(run, src)` with sensible defaults when the attribute is unset. (Future Phase-6 / Phase-7 additions to `SandboxRun` are picked up by extending `_FIELD_MAP` — no edits to wiring.)
7. **`src/codegenie/sandbox/__init__.py`.** Add `from .cost import CostEmitter, SandboxCostEntry, to_jsonl_bytes` and extend `__all__` to include the three names (AC-EXPORT-1).
8. **Amend `gates/runner.py` (additive, S5-02-preserving).** Extend `GateRunner.__init__` with `*, cost: CostEmitter | None = None` as the seventh keyword-only param (AC-WIRE-CTOR-1). Inside `__init__`, if `cost is None`, set `self._cost = CostEmitter(ledger_path=ctx.workflow_root / ".codegenie" / "cost" / "sandbox.jsonl")` — but since `ctx` is per-call, store `cost` directly and resolve the lazy `CostEmitter` in `run()` once per invocation. **Concretely:** add `self._cost_factory: Callable[[GateContext], CostEmitter] = cost.emit_for if cost else lambda c: CostEmitter(ledger_path=c.workflow_root / ".codegenie" / "cost" / "sandbox.jsonl")`. Inside `run()`, materialize `cost_emitter = self._cost or self._cost_factory(ctx)` once. After every `self._ledger.record(attempt)`, call `cost_emitter.emit_for(attempt, run, ctx)`; wrap that call in `try / except OSError as exc:` that emits the structured event `gates.runner.cost.emit.failed` and continues (AC-FAIL-NOPROP-1). **Do NOT** propagate cost-emit failures.
9. **Golden file.** Run `tools/regenerate_cost_golden.py` once with the fixed fixture (named in a docstring at the head of `test_cost_emitter.py`); commit the resulting bytes verbatim to `tests/golden/contracts/cost_sandbox_run_entry.json`. The regen script is idempotent and covered by `tests/golden/test_regen_golden_portfolio_idempotent.py`.
10. **Tests.** `tests/sandbox/test_cost_emitter.py` (byte-stable + append + extra-forbid + mutation witnesses + pairing property); `tests/sandbox/test_cost_emit_failure.py` (IOError swallow + event emission); `tests/sandbox/test_cost_emitter_gitignore.py` (`.gitignore` coverage); `tests/gates/test_runner_cost_order.py` (shared-list ordering recorder); `tests/fence/test_sandbox_cost_module_static.py` (`_FIELD_NAMES` snapshot + AST purity scan).
11. **Verify `mypy --strict`** is happy with `Literal[...]`, NewType, `Callable`, `Mapping`, `datetime`, and the keyword-only `*` markers.

## TDD plan — red / green / refactor

### Red

Three test files land their failing assertions in this order; each verifies an AC band defined above.

**`tests/sandbox/test_cost_emitter.py`** (covers §B, §C, §D ACs):

```python
import json
from datetime import datetime, UTC
from pathlib import Path

import pytest
from hypothesis import given, strategies as st
from pydantic import ValidationError

from codegenie.sandbox.contract import RunId
from codegenie.sandbox.cost import CostEmitter, SandboxCostEntry, to_jsonl_bytes
from codegenie.types.identifiers import WorkflowId

# Fixture inputs documented here so tools/regenerate_cost_golden.py reproduces.
_FIXED_CLOCK = datetime(2026, 5, 12, 0, 0, 0, tzinfo=UTC)


def _fixed_entry() -> SandboxCostEntry:
    return SandboxCostEntry(
        entry_type="cost.sandbox.run",
        workflow_id=WorkflowId("wf-fixed"),
        run_id=RunId("run-fixed"),
        gate_id="stage6_validate",
        sandbox_run_id=RunId("sb-fixed"),
        backend="docker_in_docker",
        gate_isolation_class="shared_kernel",
        microvm_seconds=0.0,
        image_pull_bytes=0,
        build_cache_hit=True,
        emitted_at=_FIXED_CLOCK,
    )


def test_cost_entry_canonical_byte_stable(tmp_path: Path) -> None:
    """ADR-0010 / AC-PATH-1 — Phase 13 pins this exact byte sequence.

    Schema drift here silently undercounts every workflow's cost on Phase 13's
    dashboard; this is the failure mode the entire story exists to prevent.
    """
    ledger = tmp_path / "sandbox.jsonl"
    emitter = CostEmitter(ledger_path=ledger, clock=lambda: _FIXED_CLOCK)
    emitter.emit(_fixed_entry())
    golden = Path("tests/golden/contracts/cost_sandbox_run_entry.json").read_bytes()
    assert ledger.read_bytes() == golden  # byte-for-byte


def test_to_jsonl_bytes_is_pure_and_deterministic() -> None:
    """AC-PURE-1, AC-CANON-1 — pure helper produces canonical bytes."""
    a = _fixed_entry()
    b = SandboxCostEntry(
        emitted_at=_FIXED_CLOCK, run_id=RunId("run-fixed"),
        workflow_id=WorkflowId("wf-fixed"), gate_id="stage6_validate",
        sandbox_run_id=RunId("sb-fixed"), backend="docker_in_docker",
        gate_isolation_class="shared_kernel", microvm_seconds=0.0,
        image_pull_bytes=0, build_cache_hit=True, entry_type="cost.sandbox.run",
    )
    # AC-MUT-1: field-order independence — same values, different kwarg order.
    assert to_jsonl_bytes(a) == to_jsonl_bytes(b)
    # AC-NL-1: exactly one trailing newline.
    assert to_jsonl_bytes(a).endswith(b"\n")
    assert to_jsonl_bytes(a).count(b"\n") == 1


def test_to_jsonl_bytes_changes_when_value_changes() -> None:
    """AC-MUT-2, AC-MUT-3 — any field-value change ⇒ byte change."""
    a = _fixed_entry()
    assert to_jsonl_bytes(a.model_copy(update={"microvm_seconds": 1.5})) != to_jsonl_bytes(a)
    assert to_jsonl_bytes(a.model_copy(update={"build_cache_hit": False})) != to_jsonl_bytes(a)


def test_cost_entry_extra_field_rejected() -> None:
    """AC-FORBID-1 — ADR-0014 discipline; extra fields raise loudly."""
    with pytest.raises(ValidationError) as excinfo:
        SandboxCostEntry.model_validate(
            {**json.loads(_fixed_entry().model_dump_json()), "future_field": 1.0}
        )
    assert "future_field" in str(excinfo.value)


def test_cost_entry_naive_datetime_rejected() -> None:
    """AC-DT-1 — naive datetime must raise."""
    with pytest.raises(ValidationError):
        SandboxCostEntry.model_validate(
            {**json.loads(_fixed_entry().model_dump_json()),
             "emitted_at": "2026-05-12T00:00:00"}  # no tz offset
        )


@pytest.mark.parametrize(
    ("backend", "iso", "ok"),
    [
        ("docker_in_docker", "shared_kernel", True),
        ("firecracker", "microvm", True),
        ("docker_in_docker", "microvm", False),
        ("firecracker", "shared_kernel", False),
    ],
)
def test_backend_isolation_pairing_invariant(backend: str, iso: str, ok: bool) -> None:
    """AC-PAIR-1, AC-PAIR-2 — illegal pairings unrepresentable (ADR-0004)."""
    kwargs = {**_fixed_entry().model_dump(), "backend": backend, "gate_isolation_class": iso}
    if ok:
        SandboxCostEntry(**kwargs)
    else:
        with pytest.raises(ValidationError) as excinfo:
            SandboxCostEntry(**kwargs)
        msg = str(excinfo.value)
        assert "backend" in msg and "gate_isolation_class" in msg


def test_emit_appends_byte_stream_concatenation(tmp_path: Path) -> None:
    """AC-APPEND-1 — exact concatenation, not just splitlines == 2."""
    ledger = tmp_path / "sandbox.jsonl"
    emitter = CostEmitter(ledger_path=ledger, clock=lambda: _FIXED_CLOCK)
    emitter.emit(_fixed_entry())
    emitter.emit(_fixed_entry())
    golden = to_jsonl_bytes(_fixed_entry())
    assert ledger.read_bytes() == golden + golden


def test_emit_mkdir_called_exactly_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-LAZY-DIR-1 — parent dir created on first emit only."""
    ledger = tmp_path / "cost" / "sandbox.jsonl"
    emitter = CostEmitter(ledger_path=ledger, clock=lambda: _FIXED_CLOCK)
    calls = []
    orig_mkdir = Path.mkdir
    monkeypatch.setattr(Path, "mkdir", lambda self, *a, **kw: (calls.append(self), orig_mkdir(self, *a, **kw))[1])
    emitter.emit(_fixed_entry())
    emitter.emit(_fixed_entry())
    assert sum(1 for c in calls if c == ledger.parent) == 1
```

**`tests/sandbox/test_cost_emit_failure.py`** (covers AC-FAIL-NOPROP-1):

```python
import pytest
from pathlib import Path

@pytest.mark.asyncio  # redundant under asyncio_mode='auto'; kept for clarity
async def test_oserror_does_not_propagate(tmp_path: Path, ...):
    """AC-FAIL-NOPROP-1 — disk-full / IOError must not break the gate.

    Why this matters: the ledger (attempts.jsonl) is the source of truth; the
    cost ledger is observability. A full disk on the cost path must NOT prevent
    the gate from recording its outcome — otherwise a cost-side incident escalates
    into a remediation-side incident.
    """
    # Build a GateRunner with a stubbed CostEmitter whose emit_for raises.
    # Run a passing gate. Assert:
    #   (a) await runner.run(ctx) returns its GateOutcome unaltered,
    #   (b) structlog event 'gates.runner.cost.emit.failed' emitted,
    #   (c) attempts.jsonl row written,
    #   (d) .codegenie/cost/sandbox.jsonl has no row for the failed emit.
    ...
```

**`tests/gates/test_runner_cost_order.py`** (covers AC-WIRE-ORDER-1, AC-ORDER-1, AC-WIRE-ASYNC-1):

```python
async def test_ledger_record_precedes_cost_emit_per_attempt(...):
    """AC-ORDER-1 — shared-list recorder, not stacked MagicMock interleavings.

    Why this matters: the order is the durability contract — ledger row is the
    source of truth; cost row references it by attempt_id. Reversing the order
    leaves a cost row pointing at a non-existent attempt under crash-restart.
    """
    events: list[tuple[str, int]] = []

    class SpyLedger:
        def record(self, attempt):
            events.append(("ledger.record", int(attempt.attempt_id)))
            return ...  # real chain extension

    class SpyCost:
        def emit_for(self, attempt, run, ctx):
            events.append(("cost.emit", int(attempt.attempt_id)))

    # Drive a 3-retry escalation scenario.
    await runner.run(ctx)

    # The flattened sequence must alternate strictly per attempt.
    assert events == [
        ("ledger.record", 1), ("cost.emit", 1),
        ("ledger.record", 2), ("cost.emit", 2),
        ("ledger.record", 3), ("cost.emit", 3),
    ]
```

**`tests/fence/test_sandbox_cost_module_static.py`** (covers AC-FENCE-1, AC-PURE-2):

```python
import ast
from pathlib import Path

from codegenie.sandbox.cost import SandboxCostEntry, _FIELD_NAMES


def test_field_names_snapshot() -> None:
    """AC-FENCE-1 — adding/removing a field forces an ADR-0010 amendment."""
    assert _FIELD_NAMES == frozenset(SandboxCostEntry.model_fields)


def test_to_jsonl_bytes_is_io_free() -> None:
    """AC-PURE-2 — no I/O / clock / env reference in the pure helper."""
    src = Path("src/codegenie/sandbox/cost.py").read_text()
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "to_jsonl_bytes")
    forbidden = {"open", "fsync", "now", "mkdir", "write_text", "write_bytes"}
    for node in ast.walk(fn):
        if isinstance(node, ast.Attribute):
            assert node.attr not in forbidden, f"impure ref in to_jsonl_bytes: {node.attr}"
        if isinstance(node, ast.Name):
            assert node.id not in forbidden, f"impure ref in to_jsonl_bytes: {node.id}"
```

### Green

1. Land `SandboxCostEntry`, `to_jsonl_bytes`, and `CostEmitter` per §Implementation outline.
2. Run `tools/regenerate_cost_golden.py` once to author `tests/golden/contracts/cost_sandbox_run_entry.json`; commit the resulting bytes verbatim.
3. Re-run the byte-stable test; bytes match.
4. Extend `GateRunner.__init__` and `GateRunner.run` per §Implementation outline §8 — additive seventh keyword-only param; lazy ctx-resolved factory; OSError swallowed with structlog event.
5. Run all five test files; confirm green.
6. Run `make lint typecheck test`; confirm green.

### Refactor

- Confirm `tests/sandbox/test_cost_emitter.py` runs in `< 100 ms`.
- Verify the `_FIELD_MAP` shape supports later additive Phase-6 / Phase-7 expansions (e.g., new `SandboxRun` fields) by adding a new key without touching the wiring code.
- Audit that the only impure code path is `CostEmitter.emit` itself (functional-core / imperative-shell — CLAUDE.md commitment).
- Confirm the `# WARNING: any field change here requires an ADR-0010 amendment and a regenerated golden.` comment sits above the `SandboxCostEntry` class body (AC-COMMENT-1).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/cost.py` | New module — `SandboxCostEntry` + pure `to_jsonl_bytes` + impure `CostEmitter` |
| `src/codegenie/sandbox/__init__.py` | Extend `__all__` (AC-EXPORT-1) — add the three new public names |
| `src/codegenie/gates/runner.py` | Additive seventh keyword-only ctor param `cost`; lazy ctx-resolved factory; OSError swallowed (AC-WIRE-CTOR-1..3, AC-WIRE-ORDER-1, AC-FAIL-NOPROP-1) |
| `tests/sandbox/test_cost_emitter.py` | §B + §C + §D ACs (byte-stable, mutation witnesses, pairing invariant, lazy mkdir, naive-datetime rejection) |
| `tests/sandbox/test_cost_emit_failure.py` | AC-FAIL-NOPROP-1 — OSError must not propagate; structlog event emitted; ledger row preserved |
| `tests/sandbox/test_cost_emitter_gitignore.py` | AC-GITIGNORE-2 — `git check-ignore` coverage |
| `tests/gates/test_runner_cost_order.py` | AC-ORDER-1 — shared-list recorder; async; ledger-then-cost across all attempts |
| `tests/fence/test_sandbox_cost_module_static.py` | AC-FENCE-1, AC-PURE-2 — `_FIELD_NAMES` snapshot + AST purity scan |
| `tests/golden/contracts/cost_sandbox_run_entry.json` | AC-PATH-1 — Phase 13 contract anchor (matches `tests/golden/contracts/sandbox_jail.schema.json` convention) |
| `tools/regenerate_cost_golden.py` | AC-TOOL-1 — Python `argparse` (matches `tools/regenerate_probe_schemas.py` precedent); idempotent |
| `.gitignore` | AC-GITIGNORE-1 — confirm `.codegenie/` parent ignore covers `.codegenie/cost/sandbox.jsonl`; add explicit row if uncovered |

## Out of scope

- Phase 13's cost dashboard, aggregation, or per-workflow cap enforcement.
- A `CostReader` for Phase 13 to consume — Phase 13 owns its reader.
- Token-cost emission (Phase 4's LLM-side cost is a separate ledger; Phase 13 will combine).
- Any backend-specific field (e.g., Firecracker kernel feature flag); ADR-0010 requires an additive amendment for additions.
- Migrating prior `.codegenie/cost/sandbox.jsonl` content — the file is new in Phase 5.
- **Introducing a `GateId` NewType.** Per S1-04 line 1237's explicit Rule-2 decision, `gate_id` stays `str` until a third concrete consumer exists. This story is the second; the next one tips the threshold.
- **Renaming or removing any S5-02-locked `GateRunner.__init__` parameter.** The amendment is *additive only* — the seventh keyword-only param `cost`. Renaming or reordering S5-02's 6 existing params is a separate story.
- **Re-flowing existing Phase-5 cost-side observability.** The structured event taxonomy is set by S6-04 (`gates.runner.exit`, `gates.runner.replan_failed`); this story adds exactly one new event: `gates.runner.cost.emit.failed`.
- **Introducing a `Protocol` for `CostEmitter`.** Only one production consumer (the runner) and one test consumer (the spy) exist; Rule 2 (Simplicity First) caps the Protocol at the rule-of-three threshold. Documented in Notes for the implementer for the next story that adds a third consumer.

## Notes for the implementer

1. **`model_dump_json()` does NOT sort keys.** Use `json.dumps(model_dump(mode="json"), sort_keys=True, separators=(",", ":")) + b"\n"` inside `to_jsonl_bytes`. The golden test fails loudly if you forget — that is the point.
2. **`datetime` must be serialized as ISO-8601 with explicit `+00:00`.** Phase 13's reader parses with `datetime.fromisoformat`; naive datetimes raise `ValidationError` at construction (AC-DT-1). The test fixture pins `tzinfo=UTC` and injects a deterministic clock so the golden is reproducible.
3. **`extra="forbid"` is contractually load-bearing.** If you "loosen" it to `extra="ignore"` because a Phase 6 test wants to pass an extra key, you have silently re-opened Gap 5. Bounce that test back.
4. **The append-only invariant is `mode="ab"`, not `"a"`.** Binary append guarantees no surprise text-mode encoding; the trailing `\n` byte is mandatory (AC-NL-1).
5. **Wiring order in `GateRunner.run` is non-negotiable** — ledger first, cost second (AC-WIRE-ORDER-1). If cost emission fails (disk full, fsync EIO), the attempt is still in the ledger and a reviewer can reconcile.
6. **Cost-emission failure must not propagate.** Wrap `cost_emitter.emit_for(...)` in `try / except OSError`; emit the structured event `gates.runner.cost.emit.failed` (keys: `attempt_id`, `error_class`, `error_message_redacted`); continue. The gate's `GateOutcome` is the source of truth (AC-FAIL-NOPROP-1).
7. **NewType discipline (CLAUDE.md "Newtype identifiers").** `RunId` is the load-bearing identifier this story is the named downstream consumer of (S1-02 line 21). `WorkflowId` lives in `codegenie.types.identifiers` (S1-04 line 58). `gate_id` intentionally stays `str` (S1-04 line 1237 — Rule-2 cap on premature abstraction; next story tips the rule-of-three threshold).
8. **Functional core / imperative shell split** is non-negotiable (CLAUDE.md commitment). `to_jsonl_bytes` is pure; `CostEmitter.emit` is the impure shell that calls it. S7-02 HARDENED's `_recorder.py` pattern (`to_jsonl_line` + `append_jsonl_line`) is the immediate precedent — mirror that split.
9. **Make illegal states unrepresentable.** The `backend ↔ gate_isolation_class` pairing (ADR-0004) is enforced by `@model_validator(mode="after")` at construction time (AC-PAIR-1). A caller cannot construct an entry that Phase 13 would silently misclassify.
10. **`GateRunner.__init__` extension is additive only.** S5-02 AC-CTOR-1 froze the existing 6 keyword-only deps. You add exactly one new keyword-only param `cost: CostEmitter | None = None` and resolve the path from `GateContext.workflow_root` inside `run()` (AC-WIRE-CTOR-2). Do NOT change names or defaults of existing S5-02 params.
11. **Golden path convention.** Place the golden under `tests/golden/contracts/cost_sandbox_run_entry.json` (mirrors the existing `tests/golden/contracts/sandbox_jail.schema.json` precedent).
12. **Tooling convention.** Project precedent is `tools/regenerate_*.py` (see `tools/regenerate_probe_schemas.py`); the regen script is `tools/regenerate_cost_golden.py` with `argparse`.
13. **Phase 6 will lift this ledger unchanged.** `attempts.jsonl` + `.codegenie/cost/sandbox.jsonl` are both part of Phase 6's checkpointer surface. Adding fields after the fact is an additive ADR-0010 amendment + golden regen; renaming or removing fields is a Phase 5 + Phase 6 + Phase 13 tri-PR (avoid).
14. **Structural fence is defense-in-depth alongside the WARNING comment.** AC-FENCE-1's `_FIELD_NAMES` snapshot catches accidental additions even if a contributor removes the comment. The two are not redundant — together they make ADR-0010 amendments loud.
15. **No `Protocol` for `CostEmitter` yet.** Only two consumers (the production runner + one test spy). Rule 2 caps premature abstraction at the rule-of-three threshold. If a Phase 13 consumer wants to inject a mock emitter, that's a separate story that lands the Protocol + reroutes both consumers.
