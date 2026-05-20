# Validation report — S7-03 (`plugins/universal--*--*/` universal HITL fallback plugin)

**Validated:** 2026-05-19
**Validator:** `phase-story-validator` skill (automated, scheduled task `story-validation-corrector`)
**Story file:** `docs/phases/03-vuln-deterministic-recipe/stories/S7-03-universal-hitl-fallback-plugin.md`
**Verdict:** **HARDENED** — substantial edits applied. One structural wiring contradiction with the already-hardened S6-04 surfaced and reconciled in place; pervasive API drift against the real as-built code surfaces fixed.

## Why HARDENED, not RESCUE

The story's *goal-intent* — the universal fallback is a registered plugin, a sanitized handoff is written, the workflow exits 7, and a concrete plugin is never silently substituted — is sound and traces cleanly to ADR-0003, ADR-0011, arch goal G7, and Edge case E10. The arch (Scenario B) and the as-hardened sibling S6-04 **agree on that intent**; they disagree only on the *mechanism* (plugin-provided subgraph vs. orchestrator-owned node). That is a Rule-7 "two patterns contradict — pick one, document the other" situation, resolvable by reframing the story's wiring without rewriting its goal. Per the verdict rubric (`editor.md` Step 3) this is HARDENED: the block findings have clear in-place fixes; none requires reshaping the goal or scope.

## Context Brief

- **Story snapshot.** Land `plugins/universal--*--*/` (manifest, TCCM, `api.py`, a one-node subgraph), a pure `sanitize_for_handoff` helper, and a `write_handoff` writer, such that no-concrete-match resolutions route to a typed `UniversalFallbackResolution`, a sanitized markdown handoff is written under the analyzed repo's `.codegenie/handoff/`, and `codegenie remediate` exits 7. A negative test proves a concrete plugin's import failure exits 4 *before* resolution.
- **Sibling-family lineage.** 3rd Step-7 plugin story after S7-01 (`vulnerability-remediation--node--npm` scaffold, HARDENED) and S7-02 (npm recipes + adapters, HARDENED). Both prior validations corrected the identical class of defect — `ManifestScope` vs `PluginScope` confusion, pseudo-OO discriminated-union construction, invented Literal members, wrong import paths. S7-03 carried every one of those same defects.
- **Load-bearing commitments implicated.** "Extension by addition" (the universal fallback is a registered plugin, not a resolver branch — ADR-0003). "Humans always merge" (production ADR-0009 — the universal plugin's existence is the type-level enforcement). "No LLM in the gather/transform surface" (G5). Honest framing (ADR-0011 — `SandboxedPath` is in-jail-at-construction; `O_NOFOLLOW` is the second-line defense).
- **Build-order reality.** `_attempts/` reaches only S5-01. Every S6 story (S6-01..S6-06) and S7-01/S7-02 are HARDENED but **not yet executed** — `src/codegenie/plugins/events.py`, `subgraph.py`, `transforms/orchestrator.py`, `transforms/nodes/` do not exist on disk. S7-03 prescribes against story specs, not shipped code, for those dependencies; the as-built resolver/registry/scope/outcomes/sandbox_path/loader/errors WERE verified against source.

## Critic findings (consolidated)

Four lenses — Coverage (`CV`), Test-Quality (`TQ`), Consistency (`CN`), Design-Patterns (`DP`).

### Block-severity (all addressed)

| ID | Finding | Resolution |
|---|---|---|
| CN-1 | **`build_subgraph` is not on the `codegenie remediate` hot path.** S6-04 §Notes "D-P1" pins `Plugin.build_subgraph()` is *intentionally not called* by the Phase-3 orchestrator; S6-04's `IngestCveNode` returns `ShortCircuit(RequiresHumanReview(reason="no_concrete_match"))` directly on a `UniversalFallbackResolution` (S6-04 outline line 207, TDD line 405-409). S7-03 as written had the universal plugin's subgraph drive the entire HITL flow — that subgraph is never invoked outside the bake test. | Reframed Goal + Context + Validation notes §1. The plugin ships `build_subgraph` (one node) **for `test_three_plugin_contract.py` only**; the operational handoff is wired into `IngestCveNode` (AC-13). |
| CN-2 | **Handoff-writing on the real path is unowned.** S6-04's `IngestCveNode` returns `RequiresHumanReview(handoff_path=None)` and writes no file — but G7 + High-level-impl Step 7 line 206 require `.codegenie/handoff/*.md` to exist after `codegenie remediate`. | New `src/codegenie/plugins/handoff_writer.py::write_handoff`; AC-13 explicitly amends `IngestCveNode` to call it and set a non-`None` `handoff_path`. `IngestCveNode`'s S6-04 test updated (Files-to-touch). Surfaced as an explicit, declared cross-story edit (S6-04 not yet built). |
| CN-3 | **`import codegenie.plugins.subgraph` is fenced out of plugin folders** (High-level-impl Step 7 line 270). S7-03's `handoff_node.py` typed `run(state: SubgraphState) -> NodeTransition` — `SubgraphState` lives only in that fenced module. | AC-16 + outline §7 + Notes: the bake-test node guards `SubgraphState`/`NodeTransition` under `if TYPE_CHECKING:` / annotates `Any`; `ShortCircuit` imported from `codegenie.transforms.outcomes` (allowed). |
| CN-4 | **`SubgraphState` has no `jail` and no `event_log`.** S6-03 AC-9 pins its fields exactly; the story's node read `state.jail` / `state.event_log`. | `write_handoff` and `UniversalFallbackNode` take `jail` / `workflow_id` / `event_log` as explicit params / constructor-injected deps (the S6-04 node pattern). Validation notes §2; Notes-for-implementer. |
| CN-5 / TQ-1 | `resolution.reason.kind` does not exist — `UniversalFallbackResolution.reason` is `Literal["no_concrete_match"]`, a plain `str` (`resolver.py:186`). TDD test would `AttributeError`. | AC-6 + TDD rewritten to `resolution.reason == "no_concrete_match"`. |
| CN-6 / TQ-2 | `plugin.manifest.scope.specificity()` does not exist — `manifest.scope` is a `ManifestScope` (raw `str \| list[str]` dims); `specificity()` is a `PluginScope` method. (Identical to S7-01 CN-7.) | AC-7 + TDD: lift via `lift_manifest_scope(plugin.manifest.scope)` → `tuple[PluginScope]` → `.specificity()`. |
| CN-7 | `RemediationOutcome.RequiresHumanReview(reason=NoConcreteMatch, ...)` — pseudo-OO on a `TypeAlias`; no `NoConcreteMatch` symbol exists. `RequiresHumanReview` is a sibling class; `reason` is `HumanReviewReason = Literal["no_concrete_match", ...]`. (Identical to S7-02 CN-4 and S6-04 §Notes line 613.) | AC-13 + outline + Notes: construct `RequiresHumanReview(reason="no_concrete_match", handoff_path=...)` directly. |
| CN-8 | `handoff_path` type mismatch — `RequiresHumanReview.handoff_path: str \| None` (`outcomes.py:281`); story passed a `SandboxedPath`. | AC-12 `write_handoff` returns `str(sandboxed_path)`; AC-13 passes the `str`. |
| CN-9 / DP-1 | Two distinct `RequiresHumanReview` classes (the `RemediationOutcome` variant vs the S6-01 `WorkflowInternalEvent` variant) conflated into one constructor call carrying invented fields (`workflow_id`, `candidates_considered`). | Validation notes §5 + Notes-for-implementer name both; AC-13 (outcome) and AC-15 (event) separated; AC-15 explicitly defers the event's payload fields to S6-01. |

### Harden-severity (addressed)

| ID | Finding | Resolution |
|---|---|---|
| CN-10 | "Loader startup check emits a `PluginRegistryCorrupted` *spanning event*" — the loader has no such check (grep: no `universal` in `loader.py`); and `PluginRegistryCorrupted` is both an *exception* and an S6-01 *spanning event*. The as-built resolver already raises the exception (`resolver.py:524`, `reason="missing_universal"`). | Original "loader startup check" AC **dropped** (Rule 2 — duplicate of the resolver invariant). Replaced by AC-19 pinning the resolver exception. Validation notes §5 + Notes name both `PluginRegistryCorrupted` types. |
| CN-11 / H4 | "exits 4 with `PluginRejected(import_error)`" — `PluginRejected` is the union *alias*; the import-failure variant is `PluginImportError` (`kind="plugin_import_error"`, `errors.py:248`); exit-4 is via `exit_code_for_rejection`. | AC-18 + TDD assert the real variant name / `kind`. |
| CN-12 / H3 | Missing dependency: every integration test runs `codegenie remediate` (an S6-05 subcommand) — `Depends on` omitted S6-05; the subcommand does not exist in `cli.py`. | S6-05 added to `Depends on`. |
| DP-2 | `PluginSubgraph` used freely — it is `TYPE_CHECKING`-only in `protocols.py`, not in `__all__` (S7-01 DP-9). | AC-16: `build_subgraph` return annotated `Any`. |
| TQ-3 | ANSI test used a CSI-only fixture — a CSI-only implementation would pass despite AC-9.2 requiring OSC + bare-`\x1b` stripping. | AC-11 + `test_sanitize_strips_ansi_csi_and_osc` carries **both** CSI and an OSC `\x1b]8;;…\x07` hyperlink. |
| TQ-4 | Adversarial bidi/zero-width literals embedded raw in the `.py` test source — hostile/misleading source, hook-flaggable. | AC-11 mandates explicit `\u…` escapes; TDD `test_sanitize_strips_zero_width` etc. revised. |
| TQ-5 | `test_sanitize_applies_nfkc_normalization` asserted `... .replace("​", "")` with a literal ZWSP — couples the NFKC test to zero-width stripping. | TDD simplified to `== unicodedata.normalize("NFKC", raw)` (input has no ZWSP). |
| TQ-6 / CV-1 | Idempotence property mentioned only in Notes, absent from the TDD plan + Files-to-touch. | AC-10 + a Hypothesis `@given(st.text())` test; `test_handoff_sanitize.py` in Files-to-touch. |
| TQ-7 | `assert not list(Path(".codegenie/handoff").glob("*.md"))` — CWD-relative; brittle + pollutes the repo. | AC-14/AC-18 + TDD target `<repo>/.codegenie/handoff/` (the analyzed-repo namespace). |
| CV-2 / TQ-8 | `--cve CVE-2024-Y` is not `CveId`-parseable; and `IngestCveNode` looks up the CVE in `VulnIndex` *before* plugin resolution — a miss `Escalate`s `vuln_index_corrupted` (exit ≠ 7), never the universal fallback. | AC-14 + Notes: use a `CveId`-parseable id (`CVE-2024-00000`) seeded into the test `VulnIndex`. |
| CV-3 | No AC proved the universal never *shadows* a concrete match. | AC-8 added — concrete (specificity 3) beats universal (specificity 0). |
| CV-4 | Fixture-repo path inconsistent across the story (`rust-cargo-fixture` vs `cargo-fixture`). | Canonicalised to `tests/fixtures/repos/cargo-fixture/` (matches High-level-impl line 206). |
| DP-3 | Plugin instance shape unspecified — S7-01 established a `@dataclass(frozen=True)` mirroring `universal_fallback_fixture._UniversalFallbackPlugin`. | AC-3 + outline §6 pin that shape. |
| DP-4 | `@register_plugin` decorator prose contradicts ADR-0002 ("function call, NOT decorator"). | ADRs-honored line + AC-3 corrected to the `register_plugin(plugin)` function call. |

### Nit-severity

| ID | Finding | Resolution |
|---|---|---|
| CN-13 | Manifest `scope:` shown as a scalar slug (`*--*--*`) — real `ManifestScope` is a nested submodel (S7-01 CN-1). | AC-1 + outline §4 show the nested-dict YAML. |
| DP-5 | `subgraph/__init__.py` listed without a clear role. | Kept (re-exports `UniversalFallbackNode`); role documented in Files-to-touch. |
| N1 | `importlib.import_module` with a literal-`*` directory name unverified. | Notes: works via filesystem lookup like the hyphenated npm slug; confirm against S2-03, don't invent a convention. |

## Research briefs

None — no finding was tagged `NEEDS RESEARCH`. Every defect was resolvable against in-repo source (`resolver.py`, `scope.py`, `registry.py`, `outcomes.py`, `errors.py`, `loader.py`, `sandbox_path.py`) and the HARDENED sibling stories (S6-01, S6-03, S6-04, S7-01, S7-02).

## Conflict resolutions

- **Arch Scenario B vs S6-04 §D-P1 (the central conflict).** The arch draws the universal plugin's *subgraph* writing the handoff; S6-04 (HARDENED) decided the Phase-3 orchestrator does not call `build_subgraph()` and routes the universal short-circuit through `IngestCveNode`. Per the synthesis priority `Consistency > Coverage > Test-Quality > Design-Patterns`, and Rule 7 ("surface conflicts, don't average them"): the as-built S6-04 wins for the operational path (it is the more recently hardened, more concrete decision and the actual integration point), while the arch's plugin-subgraph framing is preserved as the `test_three_plugin_contract.py` bake-test contract. Both routes share one `sanitize_for_handoff`/`write_handoff` helper pair — no averaged "subgraph that also pretends to be a node" hybrid.
- **Drop the loader startup check (Rule 2 vs Coverage).** ADR-0003 §Consequences mentions a loader-time `PluginRegistryCorrupted` check. The as-built resolver already raises that exception on "universal absent + no concrete match". A second loader-time check is duplicate scope; demoted to AC-19 (resolver invariant) only.

## Edits applied

1. **Header** — `Status: Ready → HARDENED`; `Depends on` rewritten (added S6-05; annotated S6-04's `IngestCveNode` amendment, S6-03's no-`jail`/`event_log` fact); `@register_plugin` → `register_plugin(plugin)` function call in ADRs-honored.
2. **`## Validation notes` block** inserted after the header — 5 numbered block-tier closures.
3. **Context** — intro + numbered list reframed off the "plugin subgraph drives the flow" premise; a "Wiring correction" callout added.
4. **Goal** — rewritten to 5 items reflecting the helper-functions + `IngestCveNode`-amendment + bake-test-only-`build_subgraph` reconciliation.
5. **Acceptance criteria** — fully renumbered AC-1..AC-22 (was an unnumbered bullet list), grouped, every API-drift defect fixed, AC-8/AC-10/AC-12/AC-13/AC-15/AC-17/AC-19 added, the loader-startup-check AC dropped.
6. **Implementation outline** — rewritten 10-step; the `UniversalFallbackNode` snippet no longer reads `state.jail`/`state.event_log`; `write_handoff` + the `IngestCveNode` amendment added.
7. **TDD plan** — Red/Green/Refactor rewritten: real APIs, explicit `\u…` escapes, CSI+OSC ANSI fixture, Hypothesis idempotence test, repo-scoped handoff-path assertions, `CveId`-parseable seeded CVE.
8. **Files to touch** — added `handoff_writer.py`, `test_handoff_writer.py`, `test_universal_missing_raises.py`, the `ingest_cve.py` amendment, the `test_ingest_cve.py` update, the `test_three_plugin_contract.py` slice.
9. **Out of scope** — added a bullet scoping S6-04's orchestrator + other four nodes out (this story only amends `IngestCveNode`'s universal arm).
10. **Notes for the implementer** — rewritten: the build_subgraph reconciliation, the two `RequiresHumanReview` / two `PluginRegistryCorrupted` classes, `SubgraphState` has no `jail`/`event_log`, the import fence, `ManifestScope` ≠ `PluginScope`, the CVE-must-exist-in-index gotcha.

## Verdict rationale

**HARDENED.** Nine block findings, twelve hardens, three nits — but every one had a concrete in-place fix verified against repo source or a HARDENED sibling spec. The headline finding (CN-1/CN-2: `build_subgraph` is not on the hot path) is a genuine architectural collision between the arch and S6-04, not mere API drift — but it is reconciled by reframing *wiring*, not *goal*. The story's intent was never in dispute: the arch and S6-04 both want a registered universal plugin, a sanitized handoff, exit 7, and no silent substitution. After the edits, every AC is individually verifiable, the TDD plan is mutation-resistant, and the prescribed implementation traces to real surfaces.

## Residual risks (flagged, not blocking)

- **S6-04 not yet executed.** AC-13 amends `IngestCveNode`, which S6-04 ships. The executor must run S7-03 *after* S6-04 lands and confirm `IngestCveNode`'s `UniversalFallbackResolution` arm exists as S6-04's outline describes; if S6-04's executor shipped a different short-circuit shape, S7-03's executor must reconcile against the as-built node, not this story's assumption.
- **S6-01's `RequiresHumanReview` event payload is unpinned.** S6-01 lists the variant but does not enumerate its fields. AC-15 deliberately does not invent fields; the executor uses whatever S6-01 ships.
- **The `jail` root for `write_handoff` on the real path.** AC-13 says the jail is "the repo path the orchestrator was invoked against." The executor must confirm how S6-04 threads that path to `IngestCveNode` (constructor vs `SubgraphState`) and wire `write_handoff`'s `jail` argument accordingly.

## Recommended next step

`phase-story-executor` — once S6-01, S6-03, S6-04, S6-05, S7-01 have shipped GREEN. The executor should read this report's "Residual risks" before starting and pin its `IngestCveNode`-amendment decision in the attempt log.
