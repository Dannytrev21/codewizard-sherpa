# Phase 7.5 — Multi-language foundations + Python: ADRs

Architecture Decision Records for Phase 7.5, in Nygard format. Each ADR captures one load-bearing decision: context, alternatives, choice, tradeoffs, consequences, reversibility.

**Phase architecture:** [phase-arch-design.md](../phase-arch-design.md) — full architecture spec.
**Source design:** [final-design.md](../final-design.md) — synthesized from three competing lens designs.
**Production reference:** [docs/production/adrs/](../../../production/adrs/) — the project-level ADR set this phase composes with.

## Index

| # | Title | Tags |
|---|---|---|
| [0001](0001-languagepack-total-frozen-value-contract-and-freeze.md) | `LanguagePack` — a total, frozen-value capability contract, frozen provisionally | Make illegal states unrepresentable · Value object · Contract + snapshot test |
| [0002](0002-register-language-validate-all-then-commit-no-unregister.md) | `register_language` is validate-all-then-commit with build-then-publish — no `unregister`, no two-phase commit | Build-then-publish · Registry · Open/Closed at the file boundary |
| [0003](0003-grammars-modeled-one-to-many-relation.md) | `LanguagePack.grammars` is a modeled one-to-many relation; `language` reuses the existing `Language` newtype | Modeled relation · Newtype · closed sum type |
| [0004](0004-python-detection-as-base-tier-probe-not-prepass.md) | Python detection is a `tier="base"` probe reusing the coordinator prelude — no `LanguageDetectionPrepass` | Open/Closed Principle · Registry · functional-core-imperative-shell |
| [0005](0005-projectdetector-protocol-shared-marker-catalog.md) | `ProjectDetector` is a `Protocol` returning a sum type; markers live in a shared addition-only catalog | Structural typing (Protocol) · Tagged union · Registry / data-driven catalog |
| [0006](0006-typescript-retrofit-by-reference-probes-self-registered.md) | TypeScript is retrofitted as `LanguagePack` #1 by reference — `probes_self_registered` discriminator | Typed discriminator · Registry · Open/Closed Principle |
| [0007](0007-python-probes-hardened-parse-only-no-exec.md) | Python manifest/lockfile probes are parse-only, byte/depth/timeout-capped; `setup.py` is never executed | Functional core, imperative shell · hard-caps · no-exec |
| [0008](0008-python-depgraph-pure-parsing-no-resolution.md) | Python dep-graph extraction is pure parsing of resolved lockfiles — never resolution, never network, never subprocess | Strategy pattern · Functional core, imperative shell · determinism |
| [0009](0009-requirements-txt-directive-language-parsing-contract.md) | `requirements.txt` is parsed as a directive language with a fail-closed taxonomy — not as a manifest | Tagged union / sum type · fail-closed default-deny · contract |
| [0010](0010-conformance-tier-parameterized-over-live-registry.md) | `tests/conformance/` is parameterized over the live registry with a collection-completeness guard | Parameterized test / open test set · Registry · auto-enrollment |
| [0011](0011-python-search-adapter-tree-sitter-first-scip-deferred.md) | The Python search adapter ships tree-sitter-first; `scip-python` is deferred, `ALLOWED_BINARIES` untouched | Adapter pattern · Structural typing (Protocol) · scope-minimization |
| [0012](0012-languagepack-contract-snapshot-fence-not-byte-edit-allowlist.md) | The category-based extension-by-addition fence is a contract + snapshot test — not a per-phase byte-edit allowlist | Contract + snapshot test · fences · anti-allowlist-accretion |

## Status summary

- **Provisional Accepted (1):** [ADR-0001](0001-languagepack-total-frozen-value-contract-and-freeze.md) — the `LanguagePack` contract is frozen on two near-isomorphic ecosystems (TypeScript, Python); its `Review trigger` is the third `LanguagePack` (the first non-isomorphic language, Java/Maven the named candidate). The early freeze is justified because the roadmap mandates the contract land this phase — the exact escape hatch [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md) commitment 5 permits.
- **Accepted (11):** ADR-0002 through ADR-0012.

## Conventions

- **Filenames** are `NNNN-kebab-case-title.md`, zero-padded, numbered locally per phase from 0001.
- **Numbers are immutable** — a superseded ADR keeps its number; the new one gets the next and cross-links.
- **Cross-references** to production ADRs use `../../../production/adrs/NNNN-*.md`.
- **`Provisional Accepted`** ADRs carry a `**Review trigger:**` line naming the evidence that will promote, supersede, or retire them.

## Decisions noted but not yet documented

These surfaced in [final-design.md](../final-design.md) / [phase-arch-design.md](../phase-arch-design.md) as open questions or implementation-time scoping calls, not as load-bearing decisions with viable alternatives resolved. They are listed here so a future reader knows they were considered, not omitted. None warrants an ADR yet — each is either an unresolved question or a mechanical consequence of an ADR above.

- **`scip-python` fast-follow sequencing.** Whether the deferred `ScipAdapter` lands as a Phase 7.5 closeout story or a Phase 8 preamble is a story-writer sequencing decision (open question 4). The *decision to defer* is [ADR-0011](0011-python-search-adapter-tree-sitter-first-scip-deferred.md); the *timing* is not yet an ADR-worthy choice. When scheduled, the fast-follow needs its own `ALLOWED_BINARIES` amendment under the Phase 2 omnibus ADR-0001.
- **`PythonImportGraphProbe` Layer-B depth.** Whether the single Python import-graph probe also covers `sys.path` / namespace-package resolution to Node's Layer-B depth, or stays minimal, is an implementation-time scoping call (open question 3) — the phase proves the axis, not Python feature-parity.
- **Conformance/golden fixture sizing.** The exact Python fixture (rich enough to defeat a stub adapter, small enough for the session gather) is an implementation choice constrained by the documented golden-fixture spec (open question 1).
- **`tsx`/`javascript` conformance coverage minimum.** [ADR-0003](0003-grammars-modeled-one-to-many-relation.md) models the three-grammar TypeScript relation; the minimum the TypeScript fixture must exercise is a fixture-shape-spec detail (open question 2), not a separate architectural decision.
- **`@register_dep_graph_strategy` pre-registration for Node strategies.** Whether the `PackageManager`-key no-shadow check's source set must account for Node strategies already in `DepGraphRegistry` is a verification step at implementation time (open question 6, [phase-arch-design.md §Gap analysis Gap 1](../phase-arch-design.md#gap-analysis--improvements)) — a refinement of [ADR-0002](0002-register-language-validate-all-then-commit-no-unregister.md), not a new decision.
- **Polyglot-repo adapter dispatch / multi-language workflow coordination.** Which adapter answers which query for a repo detected as both Node and Python is ADR-0032 / Phase-8-Planner territory (open question 5). Phase 7.5 ships a polyglot-isolation conformance assertion but does not own the workflow story.
