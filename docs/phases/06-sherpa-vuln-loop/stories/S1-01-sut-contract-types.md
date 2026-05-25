# S1-01 — SUT contract types

**Status:** GREEN
**Validated:** 2026-05-25 — see [`_validation/S1-01-sut-contract-types.md`](_validation/S1-01-sut-contract-types.md).
**Executed:** 2026-05-25 — see [`_attempts/S1-01-sut-contract-types.md`](_attempts/S1-01-sut-contract-types.md).
**Depends on:** Foundation — no upstream story deps (kernel-tier identifier additions to `codegenie.types.identifiers` + a new `codegenie.workflows` package).

**Goal:** Land the stable harness-facing `VulnRemediationSut` Protocol plus the four immutable, sanitized models the Phase-6.5 bench harness will consume — and *only* those — so every later Phase-6 story (ledger, subgraph, HITL, adapter) can target a frozen public surface and Phase-9 can later swap a `TemporalVulnRemediationSut` behind the same Protocol without touching the harness side.

This is the contracts-first story High-level-impl.md §Step 1 mandates. The concrete LangGraph builder, ledger, and adapter land in later stories; this story ships *only* the public surface ADR-0001 names and the kernel-tier substrate ADR-0033 + Phase-3 ADR-0010 require.

## References

- [phase-arch-design.md](../phase-arch-design.md) §Contract boundary, §Failure modes, §Testing strategy.
- [final-design.md](../final-design.md) §"Decisions of record" item 2 (the named symbol list), §"State model" (closed terminal-state set).
- [ADRs/0001-stable-vuln-remediation-sut-contract.md](../ADRs/0001-stable-vuln-remediation-sut-contract.md) — the four-name commitment.
- [High-level-impl.md](../High-level-impl.md) §"Step 1 — Public contracts and typed ledger".
- Production `docs/production/adrs/0033-domain-modeling-discipline.md` — newtypes for every domain identifier; frozen immutable models; sum types for state.
- Phase-3 `docs/phases/03-vuln-deterministic-recipe/ADRs/0010-newtype-identifier-catalog.md` — single canonical declaration site (kernel `codegenie.types.identifiers`).
- Phase-3 precedent: [`src/codegenie/transforms/outcomes.py`](../../../../src/codegenie/transforms/outcomes.py) — `_FROZEN_FORBID: Final[ConfigDict] = ConfigDict(frozen=True, extra="forbid")` constant; tagged unions via `Annotated[..., Field(discriminator="kind")]`.
- Phase-4 precedent: [`src/codegenie/fallback/plan_outcome.py`](../../../../src/codegenie/fallback/plan_outcome.py) — `kind: Literal[...]` discriminator + frozen `ConfigDict`.
- Phase-3 S6-06 contract snapshot precedent: [`tests/unit/transforms/test_sandbox_jail_contract_snapshot.py`](../../../../tests/unit/transforms/test_sandbox_jail_contract_snapshot.py) + the validator report [`docs/phases/03-vuln-deterministic-recipe/stories/_validation/S6-06-phase5-contract-snapshot.md`](../../03-vuln-deterministic-recipe/stories/_validation/S6-06-phase5-contract-snapshot.md) — public-import re-export discipline, additive-vs-breaking handling, `model_json_schema(by_alias=True)` byte-compare.
- Phase-4 redaction precedent: [`src/codegenie/output/sanitizer.py`](../../../../src/codegenie/output/sanitizer.py) + the `RedactedSlice` smart-constructor pattern referenced by Phase-2 ADR-0010 / Phase-4 ADR-0010.
- Phase-9 forward dep: [`docs/phases/09-temporal-durable-workflow/stories/S4-05-run-vuln-subgraph-activity.md`](../../09-temporal-durable-workflow/stories/S4-05-run-vuln-subgraph-activity.md) — `digest()` byte-equality across `LocalVulnRemediationSut` and `TemporalVulnRemediationSut`. This story lands the byte-stability substrate that S4-05 / S6-03 will later assert across SUTs.

## Acceptance criteria

### Public surface (the four ADR-0001 names)

- [x] **AC-1 — Canonical module + re-exports.** A new package `src/codegenie/workflows/` exists with:
  - `vuln_sut.py` declaring `VulnRemediationCase`, `VulnRemediationResult`, `SutDigest`, and `VulnRemediationSut`.
  - `__init__.py` re-exporting exactly those four names (and nothing else from this story) via an explicit `__all__`. No `from .vuln_sut import *`.
  - The Phase-6.5-facing public import path is `from codegenie.workflows import VulnRemediationCase, VulnRemediationResult, SutDigest, VulnRemediationSut`. A test asserts importing from `codegenie.workflows.vuln_sut` and from `codegenie.workflows` yields the same four objects (`is`-identity).
  - **Rule-of-three note (DP-A):** the file is named `vuln_sut.py`, *not* `sut.py`, so the next task class (Phase 7 migration) can add `migration_sut.py` beside it without editing this story's file — Open/Closed at the file boundary, anticipating but not building the SUT registry the rule-of-three would justify only at the third concrete SUT.

- [x] **AC-2 — `VulnRemediationSut` Protocol shape (frozen — ADR-0001).**
  ```python
  @runtime_checkable
  class VulnRemediationSut(Protocol):
      async def run_case(self, request: VulnRemediationCase) -> VulnRemediationResult: ...
      def digest(self) -> SutDigest: ...
  ```
  A static test asserts: (i) two declared methods, no more; (ii) `run_case` is an *async* coroutine function on conforming implementations (verified via `inspect.iscoroutinefunction` on a hand-written conforming stub that the test instantiates); (iii) `digest` is *sync*; (iv) parameter and return annotations match the strings above byte-for-byte (use `typing.get_type_hints` against the Protocol; missing or extra method → fail).

- [x] **AC-3 — `VulnRemediationCase` field shape (frozen Pydantic model, `extra="forbid"`).** Fields:
  - `case_id: VulnCaseId` (new kernel-tier `NewType("VulnCaseId", str)` — ULID; smart-constructed via `parsers.parse_vuln_case_id`).
  - `repo_fixture: RepoFixtureRef` (new kernel-tier `NewType("RepoFixtureRef", str)` — `^[a-z][a-z0-9_-]*$`, ≤ 128 chars; the *name* of a fixture, never an absolute path).
  - `cve: CveId` (existing newtype).
  - `cassette_id: CassetteId` (existing newtype).
  - `execution_mode: ExecutionMode` where `ExecutionMode = Literal["dry_run", "apply", "replay"]` (closed Literal; the test asserts the membership set is byte-equal to that triple — adding a fourth mode is an ADR amendment, never a `str`-widening).
  - All fields required (no defaults); model carries `model_config = _FROZEN_FORBID` (the constant pattern Phase-3 / Phase-4 already use). Frozenness verified by a test that catches `pydantic.ValidationError` on attribute mutation; `extra="forbid"` verified by a test that catches it on construction with an unknown key.

- [x] **AC-4 — `VulnRemediationResult` field shape (frozen Pydantic model, `extra="forbid"`, sanitization-enforcing).** Fields:
  - `case_id: VulnCaseId`.
  - `terminal_state: TerminalState` where `TerminalState = Literal["completed", "awaiting_human_review", "failed_unrecoverable"]`. The closed set maps exactly to the three terminal states of final-design.md §"State model" (`Completed`, `AwaitingHumanReview`, `FailedUnrecoverable`). The three *non-terminal* ledger states (`NeedsPlan`, `PlanReady`, `PatchApplied`, `GateFailedRetryable`) MUST NOT appear in `TerminalState` — a test enumerates the membership and asserts byte-equality (failure surfaces a directive: "Adding a terminal state requires an ADR amendment to ADR-0001").
  - `patch_digest: BlobDigest | None` (existing newtype — present iff `terminal_state == "completed"`; a `model_validator` rejects all other combinations).
  - `gate_summary: GateSummary` (new frozen sub-model: `attempts: AttemptNumber`, `last_outcome: Literal["pass", "fail_retryable", "fail_terminal", "not_run"]`; this is the *summary* the harness consumes, not the full Phase-5 gate transcript).
  - `failure_modes: tuple[ErrorId, ...]` — immutable tuple of dotted-snake-case error IDs (Phase-1 ADR-0007 format); empty tuple iff `terminal_state == "completed"` (model_validator).
  - `cost_summary: CostSummary` (new frozen sub-model: `tokens_in: TokenCount`, `tokens_out: TokenCount`, `cassette_replays: int` non-negative; no provider names, no model slugs — those would couple the harness to Phase-4 internals).
  - `evidence_references: tuple[EvidenceRef, ...]` (new frozen sub-model with one field `ref: str` constructed via a smart constructor that REJECTS absolute paths (no leading `/`, no Windows drive letter), null bytes, control chars, and any path that contains `..` — these are *references* into the per-run artifact directory, never paths to arbitrary disk).
  - `sut_digest: SutDigest` — see AC-7.
  - All sub-models use `_FROZEN_FORBID`; an AST test walking `vuln_sut.py` asserts every `BaseModel` subclass sets `model_config = _FROZEN_FORBID` (no exceptions). The constant is imported once from a single canonical location (`codegenie.workflows._frozen`, or via `from codegenie.transforms.outcomes import _FROZEN_FORBID` if the existing constant is promoted to a kernel home in this story — pick one and document the choice in a one-line code comment).

- [x] **AC-5 — Sanitization is enforced by construction, not by convention.** Three property-based tests (Hypothesis):
  - For any drawn `evidence_references` tuple containing at least one absolute path (`st.text().filter(lambda s: s.startswith("/"))`), `VulnRemediationResult(...)` raises `pydantic.ValidationError`. The reason field of the error names `EvidenceRef` and the rejected substring (so the directive is actionable).
  - For any drawn `evidence_references` element matching one of the secret-shaped patterns (`^(?i)(.*_)?(KEY|TOKEN|SECRET|PASSWORD|PAT|JWT|CRED)(_.*)?$` *as a substring*, or matching the JWT / AWS / GitHub-PAT regexes from `codegenie/output/sanitizer.py`), construction is rejected with a directive-shaped error.
  - For any drawn `failure_modes` element NOT matching `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` (Phase-1 ADR-0007), construction is rejected.
  Two example-based negative tests pin the directive text on `"/etc/passwd"` and `"GITHUB_TOKEN=ghp_..."`. **Mutation thinking:** a `regex.search` swapped for `regex.fullmatch` would let `"foo /etc/passwd"` slip through; the property-test substring draws catch that.

- [x] **AC-6 — Phase-6.5 import fence (static structural defense).** A new fence test at `tests/fence/test_workflows_public_surface.py` asserts:
  - The four named symbols are *importable* from `codegenie.workflows`.
  - The four named symbols are *not* importable from any private path: a glob over `src/codegenie/workflows/_*.py` returns no module that re-exports them.
  - An AST walk over `src/codegenie/workflows/__init__.py` asserts `__all__` is exactly the set `{"VulnRemediationCase", "VulnRemediationResult", "SutDigest", "VulnRemediationSut"}` (anticipates future expansion: a comment in the test names the file as the seam where future SUTs land).
  - **Phase-6.5 substrate fence:** a stub `tests/fence/test_phase6_no_graph_imports_from_phase65.py` walks every Python file under a hypothetical `tests/integration/phase65_harness/` *if it exists* (skipped when absent; the actual fence lands in Phase-6.5's S1), and asserts no import touches `plugins.vulnerability_remediation__node__npm.subgraph`, `codegenie.workflows.vuln_ledger`, or any module name beginning with `_`. This story ships the *placeholder* fence so the executor cannot forget it; Phase-6.5 fills the harness side.

- [x] **AC-7 — `SutDigest` byte-stability + sensitivity (Hypothesis property tests).** `SutDigest = NewType("SutDigest", str)`; a smart constructor `parsers.parse_sut_digest` accepts only `^blake3:[0-9a-f]{64}$` (mirrors Phase-3 `BundleCacheKey` shape). Three properties:
  - **Stability:** for any drawn `VulnRemediationCase` `c`, computing the digest substrate `_compute_sut_digest_input(c)` twice yields byte-equal bytes (functional core determinism).
  - **Sensitivity:** for any two drawn cases `c1 ≠ c2` (different on at least one field), `_compute_sut_digest_input(c1) != _compute_sut_digest_input(c2)`. Encoded via Hypothesis `assume(c1 != c2)`; mutation thinking — a buggy implementation that omits one field from the digest would silently collide and fail this property.
  - **No-side-effects:** `digest()` does not touch the filesystem, network, env, or clock — verified by an AST test that walks any future `digest` implementation and forbids the names `open`, `socket`, `urllib`, `httpx`, `requests`, `time.time`, `time.monotonic`, `datetime.now`, `os.environ`, `os.getenv`. (No concrete implementation lands in this story — the AST test is a placeholder asserting that *if* `digest` is defined on a `VulnRemediationSut` implementation under `codegenie/workflows/`, it does not import any of those names. Will start passing trivially because no implementation exists yet, and will start *biting* in S5-01 when the concrete adapter lands.)

- [x] **AC-8 — JSON round-trip preserves byte-equality (determinism floor).** For any drawn `VulnRemediationCase` / `VulnRemediationResult`, `Model.model_validate_json(m.model_dump_json()) == m` AND `m.model_dump_json()` is byte-deterministic across two independent dumps (sorted keys; Pydantic v2 does this by default but the test pins it explicitly — a future config flip flag-day catches here, not in Phase-6.5).

- [x] **AC-9 — Contract snapshot (CI-gating).** A test at `tests/integration/test_phase6_sut_contract_snapshot.py` byte-compares `model_json_schema(by_alias=True)` for `VulnRemediationCase` + `VulnRemediationResult` + a structural snapshot of the `VulnRemediationSut` Protocol (`inspect.signature` of each method + the four `__all__` names) against a golden at `tests/golden/phase6-contract/snapshot.json`. The test:
  - Fails byte-exact on any change.
  - On failure, prints a directive: *"Phase-6 SUT contract drift. If additive (new optional field with default / new sub-model class added without removing or renaming an existing field), regenerate the golden under `PHASE6_CONTRACT_GOLDEN_REWRITE=1 pytest tests/integration/test_phase6_sut_contract_snapshot.py` and amend ADR-0001 §Consequences. If breaking (rename, removal, required-without-default, runtime_checkable removal, Literal narrowing), this is an ADR-0001 amendment + downstream Phase-6.5 / Phase-9 review per ADR-0001 §Consequences."*
  - A *meta-test* `tests/integration/test_phase6_sut_contract_snapshot_meta.py` constructs two synthetic snapshots (one additive, one breaking) and asserts the helper classifies them correctly — guards the directive logic itself (mutation thinking: a `==` swapped for `!=` would silently let breaking changes through; the meta-test catches that. This is the exact gap the Phase-3 S6-06 validation report flagged as "the scariest failure mode").

- [x] **AC-10 — Newtype registry registration.** The new identifiers introduced by this story (`VulnCaseId`, `RepoFixtureRef`, `SutDigest`) are added to:
  - `codegenie.types.identifiers.__all__`,
  - the `_NEWTYPE_REGISTRY` mapping with a one-line docstring naming ADR-0010 + Phase-6 ADR-0001,
  - their smart constructors land in `codegenie.types.parsers`.
  The existing identifier registry drift test (`tests/unit/types/test_identifiers_phase3.py::test_newtype_registry_matches_all` and the Phase-4 / Phase-7 equivalents) is extended (or a Phase-6 sibling added) so an unregistered newtype fails CI.

- [x] **AC-11 — `mypy --strict` clean.** All new modules pass `make typecheck` with no `Any`, no untyped `dict`, no `# type: ignore` without a comment naming the upstream issue. CLAUDE.md "Type everything, strictly" precedent.

- [x] **AC-12 — Public-surface allowlist sentinel.** A static test enumerates every public name exported from `codegenie.workflows` (via `dir()` filtered to non-underscore names) and asserts it equals the set in AC-1. This is the "extension by addition" enforcement mechanism CLAUDE.md names as load-bearing: a new public name lands by additive ADR amendment + this test's allowlist edit, never by accident.

## Files to touch

- `src/codegenie/workflows/__init__.py` (new) — re-export the four names.
- `src/codegenie/workflows/vuln_sut.py` (new) — Protocol + the four models + sub-models.
- `src/codegenie/types/identifiers.py` — add `VulnCaseId`, `RepoFixtureRef`, `SutDigest` newtypes + `_NEWTYPE_REGISTRY` entries.
- `src/codegenie/types/parsers.py` — add `parse_vuln_case_id`, `parse_repo_fixture_ref`, `parse_sut_digest` smart constructors.
- `tests/unit/workflows/test_vuln_sut_shape.py` (new) — AC-2 protocol shape; AC-3, AC-4 field shapes; AC-8 round-trip; frozenness; extra-forbid.
- `tests/unit/workflows/test_sanitization_properties.py` (new) — AC-5 Hypothesis properties.
- `tests/unit/workflows/test_sut_digest_properties.py` (new) — AC-7 stability + sensitivity + no-side-effects.
- `tests/fence/test_workflows_public_surface.py` (new) — AC-1 import-identity; AC-6 import fence; AC-12 allowlist sentinel.
- `tests/fence/test_phase6_no_graph_imports_from_phase65.py` (new, placeholder per AC-6).
- `tests/integration/test_phase6_sut_contract_snapshot.py` + `..._meta.py` (new) — AC-9 contract snapshot + meta.
- `tests/golden/phase6-contract/snapshot.json` (new) — golden.
- `tests/unit/types/` — extend the newtype-registry drift test (AC-10) for the three additions.

## TDD plan

**Red.** Land in this order — every step writes a failing test first, then asserts the failure mode is meaningful before writing any production code:
1. AC-1 import-identity test (fails: module doesn't exist).
2. AC-2 Protocol shape test (fails: name unbound).
3. AC-3 / AC-4 field-shape + frozen + extra-forbid tests, asserting member set, types, model_config (fails: classes don't exist).
4. AC-5 sanitization property tests (fails: validators don't exist; assert the *directive* text in the rejection message so a too-generic `ValidationError` still fails the test).
5. AC-7 digest stability + sensitivity property tests; AC-7 no-side-effects AST test (fails: helper doesn't exist; AST test starts trivially passing because no implementation exists — that's correct, will start biting in S5-01).
6. AC-8 JSON round-trip + byte-determinism test.
7. AC-9 contract snapshot test pointing at a *missing* golden file (fails on first run with the directive); meta-test for the additive-vs-breaking classifier.
8. AC-6 import fence + AC-12 allowlist sentinel.

**Green.** Implement the minimum that makes all red tests pass:
- Add the three newtypes + smart constructors. Land their `_NEWTYPE_REGISTRY` entries in the same commit (AC-10) — the existing drift test will fail otherwise.
- Define `_FROZEN_FORBID` exactly once in `codegenie.workflows._frozen` (single canonical declaration site, ADR-0010 Amendment 2026-05-18) and import it in `vuln_sut.py` — *or* re-export the existing constant from `transforms.outcomes`. Document the choice in a one-line comment.
- Implement the four models + sub-models with field validators + model_validators for the cross-field invariants (terminal_state ↔ patch_digest, terminal_state ↔ failure_modes).
- Implement the `EvidenceRef` smart constructor (path + secret-shape rejection) by importing the existing canonical regex set from `codegenie.output.sanitizer` (do NOT fork them — a forked regex is a Phase-9 critique-report-pattern failure mode).
- Implement `_compute_sut_digest_input(case)` as a *pure* helper (functional core / imperative shell): take a case, serialize via `model_dump_json(sort_keys=True)`, feed to BLAKE3, return `SutDigest(f"blake3:{hex}")`. The Protocol method `digest()` is not implemented in this story — no concrete adapter exists yet.
- Generate the contract golden via the directive flag, commit it.

**Refactor.** Only cleanup — no new behaviour. Specifically:
- Confirm no public name leaked from `vuln_sut.py` beyond the four (AC-12 catches drift).
- If two or more sub-model classes share a `model_config` line, extract to module-level `_FROZEN_FORBID` (already done — sanity check).
- Verify every `ConfigDict(frozen=True, extra="forbid")` was replaced by the imported constant (matches Phase-3 / Phase-4 convention; CLAUDE.md "match the existing convention").

**Anti-refactor (Rule 2 — "three similar lines is better than premature abstraction"):** do NOT introduce a `SutRegistry` or a `BaseSut` abstract class in this story. The rule-of-three threshold for that registry will be hit when Phase 9 lands `TemporalVulnRemediationSut` *and* Phase 6.5 lands its bench-side test double (third concrete user). Surfacing the opportunity now is a Notes-for-implementer concern, not an AC.

## Out of scope

- The concrete LangGraph subgraph (Phase-6 S3-01) and adapter (Phase-6 S5-01) — they implement `VulnRemediationSut` but are not part of this story.
- The ledger sum-type (Phase-6 S1-02) — referenced via `TerminalState` only.
- HITL resume validation (Phase-6 S4-01).
- The Phase-6.5 harness fixtures — they import from `codegenie.workflows` *only* once that phase opens; this story ships the fence stub.
- A SUT registry / `BaseSut` class — see Anti-refactor above; deferred to Phase 9 (rule-of-three).

## Notes for the implementer

- **Why the four names matter so much:** ADR-0001 commits the harness across Phases 6 + 6.5 + 9 + 10 to those exact symbols. Adding a fifth public name in this story is a contract amendment — the AC-12 allowlist test will fail loud if you do. If you genuinely need a fifth, surface it via a PR comment and an ADR amendment proposal; do not silently expand `__all__`.

- **Why `terminal_state` is a Literal, not an enum or sum type with payload:** the harness reads `Result.terminal_state` for grouping in scorecards. A `Literal` reads as a string in tests, JSON dumps without serializer code, and adds-zero-bytes to the contract snapshot. The full payload-carrying terminal-state union belongs *inside* the ledger (S1-02), not the public Result.

- **Why `EvidenceRef` rejects absolute paths and secret shapes at construction:** the failure-modes table in phase-arch-design.md lists "SUT result leaks prompt/raw path → contract serialization test → CI failure." Enforcing at the Pydantic field level makes the contract impossible to violate from inside the SUT (`vuln_sut.py`) — a sanitization bug in the LangGraph node produces a `ValidationError` *before* the Result reaches the harness, not after. Borrow the canonical regex set from `codegenie.output.sanitizer`; do not fork.

- **Why `_compute_sut_digest_input` is a free function, not a method:** functional core / imperative shell. The Protocol's `digest()` will be an impure-shell method on the concrete adapter (S5-01), but the byte-stable computation lives in a pure helper this story ships and tests. Phase 9's `TemporalVulnRemediationSut` and Phase 6's `LocalVulnRemediationSut` both call the same helper; that's how Phase 9 S4-05's G5 invariance becomes reachable.

- **SUT-registry rule-of-three (DP-A / DP-B opportunity).** Today there is one SUT (the to-be-built `LocalVulnRemediationSut`). Phase 9 adds `TemporalVulnRemediationSut` (second). Phase 6.5 + Phase 10 add bench-fixture SUTs (third — depending on how the harness shapes its test doubles). At that point, a `@register_sut_kind` registry mirroring `@register_probe` / `@register_index_freshness_check` / `@register_dep_graph_strategy` would let new SUTs land without editing the kernel. This story deliberately does NOT build the registry — but the file naming (`vuln_sut.py`, not `sut.py`) and the `__all__` allowlist sentinel (AC-12) are written so the registry can be introduced additively when the threshold is reached. If you find yourself wanting to add a second SUT in this story, stop and re-scope.

- **Why the contract snapshot meta-test is non-negotiable.** The S6-06 (Phase 5) validation report singled this out: "false-positive additive is the scariest failure mode." A snapshot test that classifies a *breaking* change as additive lets the contract drift silently across Phases 6 → 6.5 → 9 → 10. The meta-test (synthetic snapshots fed to the classifier) is the mutation guard. Land it in Red, not Refactor.

- **Why the digest helper has an AST no-side-effects fence even though no implementation exists yet.** Phase 9 S4-05 §G5 explicitly says the digest must be byte-identical across `LocalVulnRemediationSut` and `TemporalVulnRemediationSut`. The two SUTs run in radically different environments (in-process LangGraph vs. Temporal Activity in a worker). A digest that touches the clock, env, or filesystem would diverge silently across substrates. The AST test is cheap, starts passing trivially, and starts biting *exactly* when a future story adds the first concrete adapter — that's a Rule-12-fail-loud pattern.
