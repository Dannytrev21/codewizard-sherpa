# Validation report — S6-06 (Phase 5 contract snapshot test)

**Date:** 2026-05-19
**Validator:** phase-story-validator (inline four-lens analysis — Coverage, Test-Quality, Consistency, Design-Patterns — applied directly after Stage 1's Context Brief surfaced multiple block-tier Consistency conflicts the four critic lenses would all converge on).
**Verdict:** **HARDENED**
**Story path:** [`docs/phases/03-vuln-deterministic-recipe/stories/S6-06-phase5-contract-snapshot.md`](../S6-06-phase5-contract-snapshot.md)

## Why HARDENED (not STRONG, not RESCUE)

The story's *architectural intent* is correct and well-anchored:

- It is the CI-gating handshake test ADR-0001 §Consequences row 2 mandates.
- It correctly identifies the six ADR-0001 named symbols and the additive-vs-breaking distinction High-level-impl §Risks #4 calls out.
- It correctly proposes the `inspect.signature` + Pydantic `model_json_schema` + golden-file pattern (precedent: `tests/unit/test_probe_contract.py` from Phase 0, `tests/unit/probes/test_repo_context_envelope_extra.py` from Phase 1).
- It correctly anchors the directive-message UX pattern.

But the story was written from the ADR-0001 contract surface alone, *before* its six dependency stories went through validation. It drifted from shipped reality and from those validated stories in multiple block-tier ways an executor without the validator's eye would have followed straight into an `ImportError`:

1. **Wrong import paths** — `from codegenie.transforms.trust_scorer import TrustSignal, TrustOutcome` and `from codegenie.transforms.report import RemediationReport` and `from codegenie.transforms.apply_context import AttemptSummary`. S5-05 validation reached Option A: `TrustSignal`/`TrustOutcome` live in `codegenie/transforms/outcomes.py`, not `trust_scorer.py`. S5-05 also re-exports `RemediationReport` from `codegenie.transforms.__init__`. `AttemptSummary` is already re-exported. Worst, the story's own AC pins "imports via the public re-export path" — but the example code violates it.

2. **`StageOutcome` missing from the snapshot list.** S6-04 validation report C-F2 resolved an ambiguity by introducing `StageOutcome: TypeAlias = TrustOutcome` declared at S6-02's canonical site and re-exported. Phase 5 reads the alias name. The contract snapshot must include it; the story did not.

3. **`Depends on:` too narrow.** Only listed S6-04. Real chain: S5-01 (RecipeEngine Protocol home), S5-05 (RemediationReport + co-located TrustSignal/TrustOutcome), S6-01 (EventLog — constructor-injected into orchestrator), S6-02 (TrustScorer + StageOutcome), S6-03 (SubgraphNode), S6-04 (orchestrator). The test imports symbols owned by all six.

4. **Meta-test surface incomplete vs. Notes.** Notes mentioned `extra="forbid"` → `extra="allow"`, runtime_checkable removal, discriminator changes — but no meta-test case existed for any of them. False-positive additive is the scariest failure mode; a meta-test gap is the exact bug that lets that ship silently.

5. **No determinism, no-silent-rewrite, or CI-strict tests.** AC text mentioned "deterministic" and "intentionally explicit"; no AC pinned a regression test. A future refactor could invert the env-var check and silently regenerate the golden in CI — no test catches it.

6. **Design-Patterns rule-of-three crossed without surfacing.** Today's snapshotter must handle 5 kinds (class, ABC, Protocol, Pydantic, TypeAlias); the classifier must handle 6 rule families (class-method, Pydantic-field, Protocol-method, model_config, decorator, discriminator). The story's sketch is "dispatches on `obj` type" → an if/elif chain. Above the rule-of-three threshold, this should be `@register_snapshot_kind` + `@register_delta_rule` registries (Strategy + Open/Closed) — mirroring the codebase's `@register_probe`, `@register_index_freshness_check`, `@register_dep_graph_strategy` precedents.

7. **No purity fence on the helpers.** AC sketched "pure helpers" but no fence test would catch a future refactor that sneaks `os.environ.get(...)` into `snapshot_symbol` and silently shadows the golden compare.

8. **No Pydantic-version pin awareness.** Pydantic minor-version bumps perturb `model_json_schema` output. Without a recorded version in the snapshot + an exact-minor pin in `pyproject.toml`, the snapshot will drift for the wrong reason and look like a Phase 3 contract regression.

All in-place fixable. The story's structure (TDD plan, file layout, additive-vs-breaking framing, golden under `tests/golden/phase5-contract/`) survives — only the specific shapes that conflict with shipped reality + validated-dep stories + design-pattern best practice need correction. Verdict: HARDENED.

## Context Brief (Stage 1)

### Story snapshot

- **Goal (post-edit):** ship `tests/integration/test_phase5_contract_snapshot.py` + `..._meta.py` + `tests/integration/_phase5_contract_helpers.py` + `tests/golden/phase5-contract/snapshot.json` + `tests/fence/test_phase5_contract_helpers_purity.py` that together freeze the public surface of the 7 ADR-0001-derived named symbols (6 + `StageOutcome`); the test allows additive deltas, rejects breaking deltas, prints a load-bearing directive on failure, and is CI-gating under `make check`.
- **Status pre-validation:** `Ready` — never executed; never validated.
- **Status post-validation:** `HARDENED`.

### Shipped reality (HEAD `ecfff74`)

- `src/codegenie/transforms/__init__.py` re-exports: `Transform`, `TransformProvenance`, `ApplyContext`, `AttemptSummary`, `CapabilityBundle`, `SandboxedPath`, every `outcomes.py` symbol. NOT yet re-exporting `RemediationOrchestrator`, `TrustScorer`, `TrustSignal`, `TrustOutcome`, `RecipeEngine`, `RemediationReport`, `StageOutcome` — those are added by S6-04/S6-02/S5-05/S5-01.
- `src/codegenie/transforms/apply_context.py:138-141` — `ApplyContext` requires `workflow_id: WorkflowId` + `capabilities: CapabilityBundle`; `prior_attempts: tuple[AttemptSummary, ...] = ()` (immutable tuple, not list — S6-04 validation C-F1).
- `src/codegenie/plugins/protocols.py:80-90` — `@runtime_checkable\nclass RecipeEngine(Protocol)` — the canonical home; ADR-0001 mandates re-export from `codegenie.transforms`.
- `src/codegenie/transforms/transform.py:64-115` — `Transform(ABC)` + abstract methods; concrete subclasses to grow over time (Phase 4 adds `LLMProducedTransform`, Phase 7 adds `DockerfileBaseImageTransform`).

### Dependency status (all HARDENED, none GREEN at validation time)

| Story | Status | What S6-06 needs from it |
|---|---|---|
| S5-01 | HARDENED | `RecipeEngine` Protocol home (`plugins/protocols.py`); re-export wiring |
| S5-05 | HARDENED | `RemediationReport` + co-located `TrustSignal`/`TrustOutcome` (Option A); re-exports |
| S6-01 | HARDENED | `EventLog` (constructor-injected into `RemediationOrchestrator`) |
| S6-02 | HARDENED | `TrustScorer` class + `StageOutcome: TypeAlias = TrustOutcome` declaration + re-exports |
| S6-03 | HARDENED | `SubgraphNode` Protocol (used by orchestrator's 5-node loop) |
| S6-04 | HARDENED | `RemediationOrchestrator` + `_validate_stage6` signature + `context: ApplyContext \| None = None` signature |

S6-06 cannot run end-to-end until all six are GREEN. The meta-test, however, has zero dep on shipped code (synthetic local fixtures) and can be written + landed first.

### Cross-phase contract (immutable inputs)

- **ADR-0001 §Decision** — six named symbols. §Consequences row 1: re-export from `codegenie.transforms`. Row 2: this CI-gating test. §Tradeoffs row 5: schema rigidity — every additive Pydantic field is a contract amendment.
- **ADR-0007 §Decision** — `_validate_stage6` body shape; signature pinned for Phase 5 wrap.
- **ADR-0010 §Decision (3)** — discriminated unions via `Annotated[..., Field(discriminator="kind")]`; every dispatch uses `match` + `assert_never`.
- **ADR-0010 Amendment 2026-05-18** — single canonical declaration site (S5-05's `outcomes.py` for `TrustSignal`/`TrustOutcome`).
- **ADR-0011** — honest framing: the snapshot is a *structural pin*, not a behavioural contract. Don't oversell.
- **High-level-impl §Risks #4** — explicit additive-vs-breaking distinction; encoded in the test, not in reviewer judgment.
- **Phase 5 ADR-0001** — two-chokepoint sandbox seam (names `_validate_stage6` as the swap point).
- **Phase 5 ADR-0002** — additive `prior_attempts` kwarg.
- **Phase 5 ADR-0003** — `TrustScorer` extension via `SignalKind` registry (variant additions are additive).

### Open ambiguities resolved before critics

- **Q1 — Where do `TrustSignal`/`TrustOutcome` live?** S5-05 Option A: `codegenie/transforms/outcomes.py`. Re-exported from `codegenie.transforms.__init__`. The story's `codegenie.transforms.trust_scorer` import was wrong. Resolution: use the re-export path everywhere.
- **Q2 — Is `StageOutcome` part of the snapshot?** Yes — per S6-04 validation C-F2, Phase 5 reads the alias name. Snapshot records both the alias name and the qualified name of its target.
- **Q3 — Should the snapshotter / classifier be registry-dispatched?** Rule-of-three test: 5 snapshot kinds + 6 delta-rule families today, with more coming in Phase 4 (Enum snapshots for SignalKind), Phase 6.5 (eval-rubric snapshots may copy the helpers). Yes — both are above the threshold. Codebase precedents: `@register_probe`, `@register_index_freshness_check`, `@register_dep_graph_strategy`.

All three resolved from precedent + shipped code + validated-dep stories; no user clarification needed.

## Findings

Severity legend: **block** (story unshippable without fix) · **harden** (in-place fix applied) · **nit** (small clarification).

### Consistency lens (highest priority — source-of-truth wins)

#### C-F1 (block → fixed) — wrong import paths violate the story's own re-export AC

- **What was wrong:** TDD plan imported `from codegenie.transforms.trust_scorer import TrustSignal, TrustOutcome`, `from codegenie.transforms.apply_context import AttemptSummary`, `from codegenie.transforms.report import RemediationReport` — three deep-import paths. Two of them are wrong (S5-05 Option A puts `TrustSignal`/`TrustOutcome` in `outcomes.py`, not `trust_scorer.py`; `AttemptSummary` is already re-exported), and all three contradict the story's own AC that imports must be via `codegenie.transforms`.
- **Source of truth:** ADR-0001 §Consequences row 1 + S5-05 AC-Surface-2 (Option A decision) + S5-05 AC-Surface-1 (RemediationReport re-export).
- **Fix applied:** All imports rewritten to `from codegenie.transforms import …`. The deep-module map for the re-export-identity check (AC-6) lives only in `_phase5_contract_helpers.py`, where one centralized declaration is acceptable.

#### C-F2 (block → fixed) — `StageOutcome` missing from the snapshot

- **What was wrong:** S6-04 validation C-F2 added `StageOutcome: TypeAlias = TrustOutcome` and recorded that "Phase 5 reads the alias name". The S6-06 story did not include it in `SYMBOLS`. The snapshot would freeze the 6 symbols ADR-0001 names directly, but `_validate_stage6 -> StageOutcome` would not be caught if someone later swapped the alias to `Aliased = SomeOther`.
- **Source of truth:** S6-04 validation report C-F2 + ADR-0010 Amendment 2026-05-18 (single-canonical-declaration-site).
- **Fix applied:** `StageOutcome` added as the 7th named symbol. AC-5 explicitly snapshots both the alias name AND the qualified name of its target. New `SnapshotKind.TYPE_ALIAS` enum member + corresponding snapshotter registration (AC-21).

#### C-F3 (block → fixed) — `Depends on:` only listed S6-04

- **What was wrong:** The test imports symbols owned by S5-01 (RecipeEngine), S5-05 (RemediationReport + TrustSignal/TrustOutcome), S6-01 (EventLog wired via orchestrator constructor), S6-02 (TrustScorer + StageOutcome), S6-03 (SubgraphNode used by orchestrator), S6-04 (orchestrator). An executor following only `Depends on: S6-04` could open the story prematurely.
- **Fix applied:** `Depends on:` expanded to the full chain with a one-line annotation per dep explaining what it owns.

#### C-F4 (harden → fixed) — re-export check uses `hasattr` instead of `is`

- **What was wrong:** Original `test_phase5_named_symbols_re_exported_from_transforms_package` asserted `hasattr(pkg, name)`. A duplicate Protocol declaration (`class RecipeEngine(Protocol): ...` re-defined inside `transforms/__init__.py`) would pass `hasattr` while silently breaking Phase 5's `isinstance(obj, RecipeEngine)` against the deep-imported class — Phase 5 consumers using either import path would see a different class object.
- **Source of truth:** Python's `Protocol` `isinstance` semantics + S6-04 validation D-P2 (dependency-inversion + identity-by-`is`).
- **Fix applied:** AC-6 + `re_export_identity_violations(SYMBOLS)` helper assert `getattr(codegenie.transforms, name) is <deep-module>.<name>`. Identity, not attribute presence.

#### C-F5 (harden → fixed) — ADR-0011 (honest framing) not honored

- **What was wrong:** Story did not mention ADR-0011. Its language ("the most load-bearing test in Phase 3") risks overselling — the snapshot is *structural* pinning only, not a behavioural contract.
- **Fix applied:** ADRs honored line extended with ADR-0011. Notes "What the snapshot does NOT catch (and why that's OK)" section added — explicitly disowns behavioural-bug detection, docstring drift, type-alias collapse.

### Coverage lens

#### C-Cv1 (harden → fixed) — no AC for `model_config` deltas

- **What was wrong:** Notes mentioned `extra="forbid"` → `extra="allow"` is breaking. No AC. The implementer could ship a classifier that ignores `model_config` and the test would still pass; the meta-test would not catch it because there was no meta-test case either.
- **Fix applied:** AC-13 lists `model_config["extra"]` change and `model_config["frozen"]` change as explicit breaking deltas. Meta-test gains `_model_extra_flipped_to_allow` + `_model_frozen_flipped_off` parametric cases.

#### C-Cv2 (harden → fixed) — no AC for `@runtime_checkable` removal

- **Fix applied:** AC-13 lists explicitly. Meta-test gains `_proto_runtime_checkable_removed` + `_proto_method_removed` cases. (`@runtime_checkable` is what makes Phase 5's `isinstance(obj, RecipeEngine)` work at gate-runner time; removal silently turns it into `TypeError`.)

#### C-Cv3 (harden → fixed) — no AC for discriminator removal

- **What was wrong:** Replacing `Annotated[A | B | C, Field(discriminator="kind")]` with a plain `Union` loses static `match` narrowing — Phase 5's `assert_never` exhaustiveness arms regress to runtime errors. No AC. No meta-test.
- **Source of truth:** ADR-0010 §Decision (3) + Phase 5 ADR-0003.
- **Fix applied:** AC-13 lists explicitly. Meta-test gains `_union_lost_discriminator` case + `_union_minus_variant` (variant removal is also breaking).

#### C-Cv4 (harden → fixed) — no AC for required-field type narrowing

- **What was wrong:** Notes obliquely mentioned "extra="forbid"-violating field-type narrowing" with no meta-test case. Narrowing `int | str` → `int` removes a shape consumers were allowed to send — strict-AND breaking.
- **Fix applied:** AC-13 explicit. Meta-test gains `_model_field_type_narrowed` + `_model_field_type_narrowed_after` cases.

#### C-Cv5 (harden → fixed) — no AC for symbol removal from `__all__`

- **Fix applied:** AC-13 lists `__all__` entry removal as breaking; folded into the same rule-family as renames.

#### C-Cv6 (harden → fixed) — no AC for snapshot determinism across invocations

- **What was wrong:** AC text mentioned "deterministic" but no regression test. A future refactor that switches `sort_keys=True` to `sort_keys=False` (or uses a Python-dict-default-order assumption) would silently flake.
- **Fix applied:** AC-8 + `test_phase5_contract_snapshot_is_deterministic` runs the snapshot 10 times in the same process and compares.

#### C-Cv7 (harden → fixed) — no AC for "no silent rewrite when env var unset"

- **Fix applied:** AC-16 + the test's monkeypatch of `Path.write_text` on `GOLDEN_PATH`. A refactor that inverts the env-var check fails immediately.

#### C-Cv8 (harden → fixed) — no AC for CI-strict mode

- **What was wrong:** Notes mentioned "intentionally explicit — a developer must opt in" but did not pin "in CI, the opt-in is ignored". A developer who accidentally sets the env var in a CI workflow could silently regenerate the golden mid-run.
- **Fix applied:** AC-17 + `test_ci_ignores_update_golden_env_var`.

#### C-Cv9 (harden → fixed) — no AC for directive-message format

- **Fix applied:** AC-19/20 + meta-test `test_directive_message_contains_required_sections`. Asserts the seven required substrings.

#### C-Cv10 (harden → fixed) — no AC for Pydantic-version pin awareness

- **What was wrong:** A Pydantic minor-version bump that perturbs `model_json_schema` output silently invalidates the snapshot for the wrong reason. The diff would look like a Phase 3 contract regression; the cause is a transparent dep bump.
- **Fix applied:** AC-11 + snapshot records `_pydantic_version`. `pyproject.toml` carries exact-minor pin.

### Test-quality lens

#### T-Q1 (harden → fixed) — meta-test surface incomplete vs. Notes

Notes mentioned `extra="forbid"` flip, runtime_checkable removal, discriminator changes — none had meta-test cases. **This is the worst class of bug**: false-positive additive ships silently. The classifier could be wrong about any of these and the original meta-test would not catch it.

- **Fix applied:** Meta-test gains 13 new parametric cases — every AC-12 and AC-13 case has at least one fixture (the meta-test is the safety net per Notes). AC-14 adds a meta-meta count check: `_BREAKING_KINDS_COVERED_BY_THIS_FILE` is compared to `DELTA_RULE_REGISTRY.all_breaking_kinds()`. A future PR that adds a classifier rule without a meta-test case is a red test.

#### T-Q2 (harden → fixed) — original meta-test asserts shape, not delta-kind

- **What was wrong:** Original test `assert all(isinstance(d, Additive) for d in deltas)`. A buggy classifier that returns `Additive` for everything passes the additive cases. A more brittle bug: classifier returns `Breaking(kind="random")` for a breaking case — the original `isinstance(d, Breaking)` check still passes, even though the recorded `kind` is meaningless.
- **Fix applied:** Each parametric case now asserts `d.kind == delta_kind` — the exact recorded kind must match. The `Breaking` dataclass's `kind: Literal[...]` discriminator carries the contract; the meta-test pins each.

#### T-Q3 (harden → fixed) — directive-message has no test

- **Fix applied:** `test_directive_message_contains_required_sections` parametric assertion on the seven required substrings.

#### T-Q4 (harden → fixed) — `--update-golden` decision is not unit-testable

- **What was wrong:** Original code read `os.environ.get(...)` inline. Testing AC-17 requires monkeypatching the global env — slow, racy, and leaks state across tests.
- **Fix applied:** Extracted `should_update_golden(env: Mapping[str, str]) -> bool` (AC-15). The CI-strict test (AC-17) calls the pure function directly.

#### T-Q5 (harden → fixed) — registry shape never tested

- **Fix applied:** `test_snapshotter_registry_covers_every_snapshot_kind` + `test_classifier_registry_covers_every_snapshot_kind` (AC-21/22 meta-test).

#### T-Q6 (nit → fixed) — fixture isolation discipline not pinned

- **Fix applied:** Notes explicitly: meta-test fixtures use locally-defined classes, NOT modules under `src/codegenie/` — same isolation as Phase 0 ADR-0002's per-test registry.

### Design-patterns lens

#### D-P1 (harden → fixed) — snapshotter dispatch crosses rule-of-three

- **Observation:** Today's snapshotter must handle 5 kinds: `class`, `abc`, `protocol`, `pydantic_model`, `type_alias`. Phase 4 likely adds `enum` for `SignalKind` registry. Phase 6.5's eval-rubric snapshots may copy the helpers. The original story's sketch is "dispatches on `obj` type" — an if/elif chain that someone has to edit each time. **Above rule-of-three threshold.**
- **Codebase precedents:** `@register_probe` (Phase 0), `@register_index_freshness_check` (Phase 2), `@register_dep_graph_strategy` (Phase 3), `@register_signal_kind` (Phase 5 ADR-0003). CLAUDE.md §"Open/Closed seams".
- **Fix applied:** AC-21 — snapshotter is registry-dispatched via `@register_snapshot_kind(SnapshotKind)`. Adding a 6th kind is one new module-local function + one decorator call, no edits to `snapshot_symbol`. AC-23 — `SnapshotKind` is a `StrEnum` (single canonical home); typos are `KeyError` at registration.

#### D-P2 (harden → fixed) — classifier dispatch crosses rule-of-three

- **Observation:** 7 rule families today (class-method, Pydantic-field, Protocol-method, model_config, decorator-presence, discriminator, type-narrowing). Each is naturally its own module. Above threshold.
- **Fix applied:** AC-22 — classifier is registry-dispatched via `@register_delta_rule(SnapshotKind)`. AC-14's meta-meta count check enforces that adding a rule without a meta-test case is a red test.

#### D-P3 (harden → fixed) — `Delta` shape only loosely typed

- **What was wrong:** Story sketched `Delta = Additive(...) | Breaking(...)`. The implementer could ship `Breaking(message="...")` as a single shape — no `kind` discriminator, no `match` exhaustiveness, no way for AC-14 to enforce coverage.
- **Fix applied:** AC-25 — `Delta` algebra is a frozen tagged union (`@dataclass(frozen=True)` `Additive` and `Breaking`, both carrying `kind: Literal[...]` discriminator). Every dispatch over `Delta` uses `match` + `assert_never` (ADR-0010 §Decision (3)). `format_breaking_delta_message` is a `match` over `delta.kind` — single source of truth for the operator UX.

#### D-P4 (harden → fixed) — functional core / imperative shell not enforced

- **What was wrong:** Story sketched "pure helpers" in passing. A future refactor that sneaks `os.environ.get(...)` into `snapshot_symbol` (to read a debug flag) silently shadows the golden compare.
- **Codebase precedent:** `tests/fence/test_transforms_module_purity.py` AST-walks the production module.
- **Fix applied:** AC-24 + new fence file `tests/fence/test_phase5_contract_helpers_purity.py`. AST-walks `_phase5_contract_helpers.py` and rejects any of `os.environ`, `Path.read_text`, `Path.write_text`, `logging.getLogger`, `subprocess.*`.

#### D-P5 (harden → fixed) — smart constructor for env-var decision

- **What was wrong:** `os.environ.get(...)` inline read makes AC-17 require monkeypatching.
- **Fix applied:** AC-15 — `should_update_golden(env: Mapping[str, str]) -> bool` is testable without monkeypatching. (Capability pattern variant — passing the capability instead of reading it ambiently.)

#### D-P6 (note → surfaced) — `tests/helpers/` would be premature

- **Observation:** A reviewer may suggest extracting `_phase5_contract_helpers.py` to `tests/helpers/contract_snapshot/` for reuse by Phase 5's own contract snapshot or Phase 6.5's rubric snapshot.
- **Decision:** Rule 2 — premature abstraction. The helpers are scoped to this one test pair today. When Phase 5 / Phase 6.5 lands its second consumer, extract then. AC-28 pins the location at `tests/integration/_phase5_contract_helpers.py`.

#### D-P7 (note → surfaced) — Phase 4 / Phase 6.5 will copy this pattern

- **Observation:** Phase 4 will add a snapshot for the `LLMProducedTransform` substrate (Phase 4 ADR-amendments to the kernel). Phase 6.5 will likely want a rubric-snapshot test for its eval harness. Both can copy the registry + Delta + purity-fence pattern.
- **Decision:** Surface as Note; do not pre-emptively extract. The first cross-phase consumer triggers extraction.

#### D-P8 (harden → fixed) — `_pydantic_version` metadata in snapshot

- **What was wrong:** A Pydantic minor-version bump perturbs `model_json_schema` output. Without a recorded version, the resulting diff looks like a Phase 3 contract drift. Confusing operator UX.
- **Fix applied:** AC-11 — snapshot records `_pydantic_version` at top level. A diff that *only* changes the `_pydantic_version` field is a transparent dep bump; a diff that changes the `_pydantic_version` field AND schema content is a contract event.

## Edits applied

All edits in-place. The story file's `Validation notes` block records the changes. Summary:

1. **Status** flipped to `HARDENED` with `_validation/S6-06-phase5-contract-snapshot.md` reference.
2. **Depends on** expanded from `S6-04` only to the full six-dep chain.
3. **ADRs honored** extended with ADR-0010 Amendment 2026-05-18 (single-canonical-declaration-site) + ADR-0011 (honest framing).
4. **Validation notes** block (14 numbered points) inserted after the header.
5. **Acceptance criteria** rewritten and expanded from 14 unnumbered bullets to 31 numbered ACs grouped under: Files + collection / Canonical symbol set / Determinism + canonical encoding / Additive vs breaking classifier / Update-golden mode (safety + opt-in) / Directive message UX / Classifier + snapshotter extension points (rule-of-three) / Functional-core + purity fences / Documentation + CI wiring / Bar.
6. **Implementation outline** rewritten in 11 ordered steps. Meta-test now precedes the main test (the classifier can be proven against synthetic fixtures with zero dep on S6-01..S6-05 actually existing).
7. **TDD plan red tests** rewritten:
   - Meta-test gains 13 new parametric cases covering every AC-12/13 delta kind, the directive-message format (AC-19/20), and the meta-meta registry count check (AC-14).
   - Main test rewritten with corrected imports (re-export only), `should_update_golden` factor, no-silent-rewrite monkeypatch (AC-16), determinism property (AC-8), CI-strict mode test (AC-17), identity-not-hasattr re-export check (AC-6).
8. **Files to touch** rewritten with AC-coverage column; new files added (`tests/fence/test_phase5_contract_helpers_purity.py`, `Makefile`, `pyproject.toml`).
9. **Notes for the implementer** restructured into Operational / Imports + re-export contract (corrected) / Classifier semantics / Design patterns / Snapshot reproducibility / What the snapshot does NOT catch / Out-of-scope reminders — about 35 new bullets that pin every block + harden + note above. The original Notes section's 12 bullets all survive, corrected and re-grouped.

## Verdict

**HARDENED.** Ready for `phase-story-executor` once S5-01, S5-05, S6-01, S6-02, S6-03, S6-04 are all GREEN on the executor's branch. The Consistency closures (C-F1..C-F5) reconcile the story with the validated-dep stories' shipped reality; the Coverage closures (C-Cv1..C-Cv10) pin every AC-12/13 delta kind, the no-silent-rewrite invariant, the CI-strict mode, and the Pydantic-version pin; the Test-Quality closures (T-Q1..T-Q6) ensure a wrong implementation fails an assertion verbatim rather than slipping through a thin test (the meta-test is now a real safety net); the Design-Patterns closures (D-P1..D-P5) elevate the snapshotter + classifier to registry dispatch (Strategy + Open/Closed), pin `Delta` as a tagged union, and fence the helpers as a functional core — making this test extensible by addition for Phase 4 (Enum snapshots, `LLMProducedTransform` subclass) and Phase 6.5 (eval-rubric snapshot) without editing the kernel.
