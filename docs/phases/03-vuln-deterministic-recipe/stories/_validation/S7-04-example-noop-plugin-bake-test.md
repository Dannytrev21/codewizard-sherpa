# Validation report — S7-04 (synthetic `example--noop--*` plugin + 3-plugin contract bake test + `PLUGINS.lock` mismatch test)

**Validated:** 2026-05-19
**Validator:** `phase-story-validator` skill (automated, scheduled task `story-validation-corrector`)
**Story file:** `docs/phases/03-vuln-deterministic-recipe/stories/S7-04-example-noop-plugin-bake-test.md`
**Verdict:** **HARDENED** — substantial edits applied. The story carried the same pervasive API-drift defect class as every S7 sibling, plus one genuine structural collision (the loader's hardcoded `plugins.{slug}.api` import prefix vs. a `tests/fixtures/`-rooted fixture plugin) and a dependency cliff. The goal was never in dispute.

## Why HARDENED, not RESCUE

The story's goal-intent — a synthetic third plugin exercising every kernel contract surface, a 3-plugin bake test of the `Plugin` contract, and a `PLUGINS.lock` post-lock-mutation regression — is sound and traces cleanly to High-level-impl §Step 7 done-criteria 1/4/5, the roadmap exit criterion "plugin contract bake-tested against ≥3 plugins", and ADR-0002/0003/0004/0009/0011. All four critics independently confirmed the goal/scope is correct and the defects are mechanism-layer (wrong APIs, wrong imports, under-declared dependencies, a structural loader collision) — every one with a concrete in-place fix verified against `src/` source. Per `editor.md` Step 3 that is HARDENED.

## Context Brief

- **Story snapshot.** Land `tests/fixtures/plugins/example--noop--noop/` (a synthetic plugin exercising `Plugin` / `Adapter` / `RecipeEngine` / `RecipeProtocol` / `SubgraphNode`), `tests/integration/test_three_plugin_contract.py` (loads vuln + universal + noop into one fresh `PluginRegistry()`, walks every contract surface), and `tests/integration/test_plugins_lock_mismatch.py` (mutate a plugin file post-lock → `load_plugins` returns `Err(IntegrityMismatch)`, exit 4).
- **Sibling-family lineage.** 4th Step-7 story after S7-01/S7-02/S7-03 (all HARDENED). Every prior validation corrected the identical defect class: pseudo-OO discriminated-union construction (`Outcome.Variant(...)`), invented `Literal` members, wrong import paths, `ManifestScope` vs `PluginScope` confusion, API drift vs as-built source. S7-04 carried every one again.
- **Build-order reality.** `_attempts/` reaches only S5-01. S5-02..S7-03 are HARDENED but **not yet executed** — `transforms/orchestrator.py`, the `SubgraphNode` Protocol, `SubgraphState`, the `codegenie remediate` CLI, and the production `plugins/` plugin directories do not exist on disk. The story was hardened against the *as-built* surfaces that ARE shipped (loader, registry, resolver, scope, errors, `recipe_registry`, `recipe_engine`, `outcomes`) and against story-specs for the un-built deps, with explicit residual-risk flags.
- **Load-bearing commitments implicated.** "Extension by addition" (the bake test IS the regression for this commitment), "No LLM in the gather/transform surface" (AC-19 `make fence`), ADR-0011 honest framing (the integrity check is the headline regression), ADR-0002 (fresh `PluginRegistry()`, `register_plugin` is a function call), ADR-0004 (the `Plugin` Protocol's four members are frozen).

## Critic findings (consolidated)

Four lenses — Coverage (`CV`), Test-Quality (`TQ`), Consistency (`CN`), Design-Patterns (`DP`). 23 findings: 7 block, 12 harden, 4 nit.

### Block-severity (all addressed)

| ID | Finding | Resolution |
|---|---|---|
| CV-F1 / TQ-F3 / CN-F4.7 / CN-F5 / DP-F2 | **Loader API drift.** Story prescribed `load_plugins(registry, roots=[prod, fixture])`. As-built (`loader.py:191`): `load_plugins(plugin_root: Path, lock_path: Path, *, registry=None, verifier=None) -> Result[LoadReport, PluginRejected]` — single root, single lock, returns a `Result`. No multi-root form. | Every AC + TDD snippet rewritten to the real signature. AC-8 / AC-16 use it correctly; the fixture asserts `.is_ok()`. Validation-notes block 1. |
| CN-F5 / DP-F2 | **Loader import-prefix collision.** `loader.py:291` hardcodes `importlib.import_module(f"plugins.{slug}.api")` — a `tests/fixtures/plugins/`-rooted plugin is not importable by `load_plugins`. The story's "point the loader at production `plugins/` AND `tests/fixtures/plugins/`" premise is unbuildable. | Reframed: the two production plugins are directory-loaded via `load_plugins`; the synthetic is registered directly via `register_plugin(noop_plugin, registry=...)` — the `universal_fallback_fixture.make_universal_fallback` precedent. AC-8, outline §2-3, Out-of-scope, Notes. Validation-notes block 2. |
| CV-F2 / TQ-F2 / CN-F2 / DP-F6 | **`plugin.recipe_registry` does not exist.** The `Plugin` Protocol has exactly four members (`protocols.py:69`, arch §C2). `RecipeRegistry` has no `.iter()`. The story's `plugin.recipe_registry.iter(plan)` is a phantom API. | AC-14 + TDD rewritten: recipe surface reached via `plugin.transforms()` and the fixture-owned `RecipeRegistry` / `match_recipes`. Notes call out the deliberate off-kernel design. |
| CN-F3 / DP-F4 | **Four ADR-0032 adapter Protocols + `confidence()` + `AdapterConfidence.High` do not exist.** As-built `Adapter` Protocol has one member, `primitive: PrimitiveName`. `AdapterConfidence` is `Trusted\|Degraded\|Unavailable` (no `High`). ADR-0032 `confidence()` is a `float`. | AC-5 rewritten: noop adapters conform to the single-member `Adapter` Protocol, one per `PrimitiveName`. The four-Protocol / `confidence()` framing dropped. Notes surface the deferred concrete-adapter-method-surface gap. Validation-notes block 4. |
| CN-F4 / TQ-F8 / DP-F7 | **Pseudo-OO union construction + invented members.** `RecipeOutcome.Skipped(reason=NOOP)` (TypeAlias treated as namespace; `NOOP` not a `SkipReason`; `Skipped` needs `plugin_id`); `Applies(NoopPlan)` (no `NoopPlan`; `Applies.plan: ApplicationPlan`); `register_recipe(..., precedence=100)` (no kwarg). | AC-6 + outline §5 + TDD + Notes rewritten to direct variant construction against `outcomes.py`. `@register_recipe` confirmed correct *as a decorator* and preserved (CN-F8). |
| CN-F4 / TQ-F6 | **Wrong import paths.** `codegenie.transforms.{transitions,applicability,subgraph_state}` do not exist; `Advance`/`Applies`/`Skipped`/`NodeTransition` live in `codegenie.transforms.outcomes`. `SubgraphState.bootstrap_for_testing()` invented. | TDD imports corrected; outline §6 + Notes pin the real homes and gate `SubgraphState` on S6-03. |
| CN-F1 / CV-F7 / TQ-F6 | **Dependency cliff.** `Depends on:` listed only S7-01/02/03. The tests need S2-03 (loader), S5-01 (recipe surface), S6-03 (`SubgraphNode`/`SubgraphState`), S6-05 (`remediate` CLI). | `Depends on:` widened to the full transitive spine with per-dep rationale. AC-1 + outline §1 add an explicit precondition check (set `BLOCKED` if unmet — do not stub fake production plugins). |

### Harden-severity (addressed)

| ID | Finding | Resolution |
|---|---|---|
| TQ-F1 / DP-F5 / CV-F4 | Bake-test assertions mutation-blind — `is not None` / `isinstance(_, dict)` pass against a `{}`-returning or bare-object plugin. | AC-9 rewritten to structural `isinstance` against the `@runtime_checkable` Protocols + non-emptiness; a single reusable `_plugin_contract_walker.py`. |
| TQ-F4 / CV-F3 | Mismatch test had no positive control — could not distinguish "rejected for tampering" from "rejected for setup noise". | AC-16 step (2) adds the un-mutated-tree-loads-`Ok` control. |
| TQ-F5 / TQ-F7 / DP-F3 | Mismatch test went only through `subprocess` against an un-built CLI, coupled to a `b"PluginRejected"` stderr literal. | AC-16 makes the in-process `load_plugins` → `Err(IntegrityMismatch)` boundary the primary assertion; AC-17 the in-process exit-code check; AC-18 the conditional subprocess arm asserting the `kind` literal. |
| CV-F5 | No AC enforced the synthetic must not pollute the production registry / `PLUGINS.lock`. | AC-12 (not in production lockfile) + AC-13 (not in `default_registry`) added. |
| CV-F6 / DP-F1 | The "extension by addition" property — the story's whole purpose — was only a Refactor suggestion. Rule-of-three crossed (vuln+universal+noop; Phase 7 = 4th). | AC-11 added — an *observable* AC: plugin universe is a `Final` tuple, walker is one helper, a 4th plugin is one tuple entry, zero walker edits. |
| CV-F7 | No precondition behavior for unmet S7-01/02/03. | AC-1 + outline §1: confirm preconditions; set `BLOCKED` if unmet. |
| DP-F4 | Four ~5-LOC adapter files = premature fragmentation vs the sibling layout. | Collapsed to one `noop_adapters.py`; Files-to-touch updated; Notes say match S7-02's as-built layout (Rule 11). |
| CN-F6 | `codegenie plugins lock-update` is an orphan deliverable assigned to no story. | Out-of-scope + Notes escalate it; the mismatch test computes the lock in-process instead. |
| CV-F4 | Vuln + universal plugins only got shallow checks; recipe + resolution paths only tested on noop. | AC-9 walks all three; AC-10 asserts both resolution paths; AC-14 exercises the recipe surface. |
| TQ-F9 | `test_three_plugins_registered` used set-membership, not equality. | AC-8 mandates exact set equality + cardinality 3. |
| CV-F8 / TQ-F6 | `asyncio` used but unimported in the red snippet. | TDD red snippet imports `asyncio`. |
| CN-F7 | Exit-4 assertion coupled to the `PluginRejected` union-alias name. | AC-17 asserts `exit_code_for_rejection` directly; AC-18 asserts the `integrity_mismatch` `kind` literal. |

### Nit-severity (addressed)

| ID | Finding | Resolution |
|---|---|---|
| DP-F8 | `README.md` for an ~80-LOC test fixture is ceremony; siblings use a module docstring. | README dropped from Files-to-touch; outline §3 + Refactor mandate an `api.py` module docstring. |
| DP-F9 | Newtype discipline for `adapters()`/`transforms()` dict keys left implicit. | AC-3 pins all `PluginId`/`PrimitiveName`/`TransformKind`/`RecipeId` constructed via newtype constructors at the boundary. |
| CN-F8 | `@register_recipe` is correctly a decorator — flagged so the synthesizer would not "fix" it. | Preserved as-is; Notes explicitly distinguish it from the `register_plugin` function call. |
| TQ-F2 | `plan = ...` literal-ellipsis placeholder in the recipe test. | Removed; AC-14 / TDD construct real fixture inputs. |

## Research briefs

None — no finding was tagged `NEEDS RESEARCH`. CN-F3 carried a `NEEDS RESEARCH` boundary (the deferred concrete `Adapter` method surface), but it is resolvable in-repo: the noop adapters conform to the as-built single-member `Adapter` Protocol today, and the gap is surfaced as a Notes paragraph + attempt-log instruction. No external research required.

## Conflict resolutions

- **Coverage wanted the synthetic directory-loaded by `load_plugins` (full loader exercise); Consistency proved the loader's `plugins.{slug}.api` import prefix makes that impossible from `tests/fixtures/`.** Per `Consistency > Coverage` and Rule 7 (surface conflicts, don't average): the as-built loader wins — the synthetic is registered via `register_plugin`, the two production plugins are directory-loaded. The loader's directory-discovery + integrity gate is still fully exercised by the production-plugin load and by the mismatch test (which stages a `plugins/`-named tmp tree and is rejected at the integrity gate *before* any import runs, so the prefix never bites there).
- **Design-Patterns wanted the contract-walker promoted to a kernel/helper; Rule 2 guards against premature abstraction.** Rule-of-three is genuinely crossed (3 plugins today, Phase 7 = 4th), so the extract is mandated — but as an *observable* AC (AC-11: "one tuple entry, zero walker edits"), not a pattern-name AC.

## Edits applied

1. **Header** — `Status: Ready → HARDENED`; `Depends on:` widened from {S7-01,02,03} to the full transitive spine {S2-03, S5-01, S6-03, S7-01, S7-02, S7-03, + S6-05 conditionally} with per-dep rationale; `ADRs honored` corrected (`register_plugin` is a function call).
2. **`## Validation notes`** block inserted after the header — 7 numbered block-tier closures + the harden/nit summary.
3. **Context** — reframed off the "loader points at two directories" premise; the `register_plugin`-direct reconciliation and the import-prefix gap documented.
4. **References** — added an as-built-source section listing every file the prescribed APIs must be verified against; corrected the ADR-0032 framing.
5. **Goal** — rewritten: one fresh registry, reusable contract-walker, `load_plugins` boundary for the integrity regression.
6. **Acceptance criteria** — fully renumbered AC-1..AC-21 (was an unnumbered bullet list), grouped (synthetic plugin / bake test / mismatch test / hygiene), every API-drift defect fixed, AC-11/12/13/17 added, the four-adapter-Protocol framing removed.
7. **Implementation outline** — rewritten 9-step with a precondition gate.
8. **TDD plan** — Red rewritten against real APIs (correct `load_plugins` signature, `register_plugin`-direct fixture, structural-conformance walker, in-process `Err(IntegrityMismatch)` + positive control); Green/Refactor adjusted.
9. **Files to touch** — dropped `README.md` + the in-fixture `PLUGINS.lock`; collapsed four adapter files to one; added `_plugin_contract_walker.py`.
10. **Out of scope** — added bullets: directory-loading the synthetic, the subprocess exit-4 arm, the orphan `plugins lock-update`.
11. **Notes for the implementer** — rewritten: the loader signature + import-prefix collision, the off-kernel recipe surface, the non-existent adapter Protocols, direct variant construction, the decorator/function-call asymmetry, the S6-03 gate, the in-process integrity assertion, the orphan `lock-update`.

## Verdict rationale

**HARDENED.** Seven block findings, twelve hardens, four nits — but every one had a concrete in-place fix verified against repo source. The headline structural finding (the loader's `plugins.{slug}.api` import prefix vs. a `tests/fixtures/`-rooted plugin) is a genuine collision, not mere API drift — but it is reconciled by reframing the *registration mechanism* (`register_plugin`-direct, an existing precedent), not the *goal*. After the edits every AC is individually verifiable, the bake test fails against a contract-violating plugin (structural `isinstance` checks, exact set equality), the integrity regression has a positive control and tests the pure boundary, and the prescribed implementation traces to real surfaces.

## Residual risks (flagged, not blocking)

- **S5-02..S7-03 are not yet executed.** The story prescribes against the as-built code for shipped surfaces (loader, registry, resolver, scope, errors, `recipe_registry`, `recipe_engine`, `outcomes`) but against story-specs for S6-03 (`SubgraphNode`/`SubgraphState`) and S7-01/02/03 (the two production plugins). The executor must run S7-04 *last* in the phase and reconcile `noop_node.py` against the as-built S6-03 `SubgraphNode.run` signature, and confirm the two production plugins load clean, before relying on the bake test.
- **The loader import-prefix may also affect the mismatch test if the integrity gate's ordering changes.** AC-16 relies on the loader's verify-ALL-before-import-ALL invariant (`loader.py` docstring) so a tampered tree is rejected *before* any `plugins.{slug}.api` import runs. If S2-03's as-built loader does not preserve that ordering, the mismatch test's tmp-tree staging must be revisited.
- **`codegenie plugins lock-update` is unassigned.** The mismatch test sidesteps it (computes the lock in-process), but the orphan deliverable should be given an owning story before Phase 7 — flagged to the architect / story-writer.
- **The concrete `Adapter` method surface is deferred.** `protocols.py` ships a one-member `Adapter` Protocol; the richer ADR-0032 surface (`consumers()`, `confidence()`) lands "with the first concrete adapter in S7" per the protocols module docstring. S7-04 and S7-02 must jointly settle the concrete shape; AC-5 conforms the noop adapters to whatever the `Adapter` Protocol is at implementation time.

## Recommended next step

`phase-story-executor` — once S2-03, S5-01, S6-03, S6-05, S7-01, S7-02, S7-03 have shipped GREEN. The executor should read this report's "Residual risks" first and pin its `SubgraphNode` reconciliation + `Adapter`-surface decision in the attempt log.
