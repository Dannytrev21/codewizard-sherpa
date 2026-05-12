# Phase 1 — Context gathering: Layer A (Node.js): ADRs

Architecture Decision Records for Phase 1, in Nygard format. Each ADR captures one load-bearing decision: the context, the alternatives considered, what was chosen, the tradeoffs accepted, the consequences, and how reversible the choice is.

**Phase architecture:** [phase-arch-design.md](../phase-arch-design.md) — full architecture spec.
**Source design:** [final-design.md](../final-design.md) — synthesized from three competing lens designs.
**Critique:** [critique.md](../critique.md) — devil's-advocate findings that shaped many of these decisions.
**Production reference:** [docs/production/adrs/](../../../production/adrs/) — the project-level ADR set this phase composes with.
**Prior phase:** [Phase 0 ADRs](../../00-bullet-tracer-foundations/ADRs/) — the spine these decisions extend.

## Index

| # | Title | Tags |
|---|---|---|
| [0001](0001-add-node-to-allowed-binaries.md) | Add `node` to `exec.ALLOWED_BINARIES` for the `--version` cross-check | tool-use · security · allowlist · localv2-conformance |
| [0002](0002-parsed-manifest-memo-on-probe-context.md) | `ParsedManifestMemo` on `ProbeContext` — in-coordinator per-gather parse memo | coordinator · probe-context · performance · chokepoint-preservation |
| [0003](0003-yarn-lock-parser-choice.md) | `yarn.lock` parser — `pyarn` if maintained, else hand-rolled fallback | parser · dependency-policy · maintenance-burden · land-time-decision |
| [0004](0004-per-probe-subschema-additional-properties-false.md) | Per-probe sub-schema `additionalProperties: false` at its own root | schema · validation · extension · contract · chokepoint |
| [0005](0005-coverage-carve-outs-deployment-ci.md) | 90/80 coverage floor with 85/75 carve-out for `deployment.py` and `ci.py` | testing · coverage · ratchet · governance |
| [0006](0006-native-module-catalog-versioning.md) | Native module catalog versioning — `catalog_version` participates in cache key | catalog · data-as-code · cache-invalidation · cross-phase · silent-staleness |
| [0007](0007-warnings-id-pattern.md) | `warnings[]` entries pattern-constrained to structured IDs | schema · facts-not-judgments · structural-defense · pattern-constraint |
| [0008](0008-in-process-parse-caps-not-per-probe-sandbox.md) | In-process parse caps in `parsers/`, no per-probe fork+exec sandbox | security · adversarial-input · parser-hardening · chokepoint · phase-evolution |
| [0009](0009-no-new-c-extension-parser-dependencies.md) | No new C-extension parser dependencies in Phase 1 | dependency-policy · supply-chain · cve-surface · simplicity |
| [0010](0010-layer-a-slices-optional-at-envelope.md) | Layer A slices declared optional at the envelope's `probes.*` level | schema · multi-language · extension · envelope-shape |
| [0011](0011-no-helm-render-no-hcl-no-npm-ls.md) | No Helm template rendering, no HCL parsing, no `npm ls` invocation in Phase 1 | scope · determinism · supply-chain · cve-surface · facts-not-judgments |
| [0012](0012-multi-environment-helm-as-list-with-nullable-primary.md) | Multi-environment Helm emitted as `environments: list` with nullable primary `image_reference` | schema · additive-extension · localv2-conformance · contract-shape |

## Conventions

- **Filenames** are `NNNN-kebab-case-title.md` with zero-padded four-digit numbers, numbered locally per phase starting at 0001.
- **Numbers are immutable** — a superseded ADR keeps its number; the new one gets the next number and cross-links.
- **Cross-references** to production ADRs use `../../../production/adrs/NNNN-*.md`. Cross-references to other phase ADRs use the relative filename inside this folder. Cross-references to Phase 0 ADRs use `../../00-bullet-tracer-foundations/ADRs/NNNN-*.md`.
- **The phase-arch-design and final-design documents are the architecture contract**; ADRs are the durable rationale. When the two diverge, the ADR is the *why* and the arch doc is the *what*.

## What got an ADR

These decisions met the bar — a real choice, viable alternatives, load-bearing on Phase 1 implementation or Phase 2+ interfaces, durable enough that a future reader benefits from rationale before changing them:

- **The three explicit Phase 0 in-place edits.** Each is ADR-gated per `final-design.md "Goals"`: `ALLOWED_BINARIES` += `node` (ADR-0001), `ParsedManifestMemo` on `ProbeContext` (ADR-0002), and the `LanguageDetectionProbe` extension (Phase 0 §2.10 deferral — not separately ADR'd here because Phase 0 final-design §2.10 already licensed it explicitly; the rationale is recorded in `final-design.md "Components"` #1).
- **Yarn-lock parser choice** — the dep-policy boundary case (ADR-0003).
- **Per-probe sub-schema `additionalProperties: false`** — closes critic cross-design observation #1 (ADR-0004).
- **Coverage carve-out for `deployment.py` and `ci.py`** — Rule 9 conformance over coverage-shaped theater (ADR-0005).
- **Native module catalog versioning** — the silent-staleness mitigation cross-phase (ADR-0006).
- **`warnings[]` ID pattern** — closes critic cross-design observation #4 (ADR-0007).
- **In-process parse caps, no per-probe sandbox** — the load-bearing conflict resolution (table row 1) (ADR-0008).
- **No new C-extension parser deps** — the dep-closure policy (table row 8) (ADR-0009).
- **Layer A slices optional at envelope** — non-Node-repo correctness (ADR-0010).
- **No Helm render / no HCL / no `npm ls`** — scope and determinism (ADR-0011).
- **Multi-env Helm as `environments: list`** — additive shape for the singleton-vs-list conflict (ADR-0012).

## Decisions noted but not yet documented

Surfaced during ADR extraction as plausibly worth ADR-ing, but the documentation in `final-design.md` and `phase-arch-design.md` doesn't develop them enough to write a confident ADR. Flagged for the implementer / next-phase author:

- **Pre-dispatch input-snapshot pass on `ProbeContext`** (`phase-arch-design.md "Gap analysis & improvements" Gap 1`). The arch doc proposes a new `ctx.input_snapshot: frozenset[InputFingerprint]` field to close the TOCTOU-across-the-lockfile-read gap. The improvement is concrete but the synthesis didn't land it as a Phase 1 commitment — the arch doc says "Land in Phase 1 — the seam is set now or never" but the final-design "Goals" don't list it. Worth an ADR (Phase 1 or Phase 2 amendment to ADR-0002) once the implementer decides; the residual TOCTOU window must be documented either way.

- **Raw artifact size budget on `Probe`** (`phase-arch-design.md "Gap analysis & improvements" Gap 2`). The arch doc proposes `declared_raw_artifact_budget_mb: int = 5` to bound `.codegenie/context/raw/<probe>.json` writes. `NodeManifestProbe` would need to override to ~25 MB to accommodate typical lockfile dumps. The Coordinator-side enforcement (truncate + emit `probe.raw_artifact.truncated`) is concrete but the synthesis didn't land it; Phase 0 deferred RSS enforcement broadly. Worth an ADR if the lockfile-size pressure surfaces during implementation; otherwise carries to Phase 14's resource-enforcement story.

- **Coordinator Wave-1 prelude formalization for `LanguageDetectionProbe` → `enriched_snapshot.detected_languages`**. The arch doc (`"4+1 architectural views" "Process view"`) describes the prelude pass and says "no new contract" — but the prelude *is* an additive coordinator behavior carried forward from Phase 0's gap #4 resolution. Phase 0's ADR registry notes this as a decision plausibly worth ADR-ing (Phase 0 README "Decisions noted but not yet documented" entry 2). It might earn its own ADR here as the prelude's documented home; the arch doc's stance is "documented behavior, encoded in existing `requires:` topology" which reads as "we don't need an ADR." The implementer should reconsider if the prelude grows beyond `LanguageDetectionProbe` (e.g., Phase 2's `IndexHealthProbe`).

- **Per-probe sub-schema release-versioning policy** (`final-design.md "Open questions"` #2). Deferred to Phase 2 explicitly. When Phase 2 introduces it, an ADR amendment to ADR-0004 (or a Phase 2 ADR cross-referencing this one) captures the policy.

- **Typed warning enum** (`final-design.md "Open questions"` #7). Phase 1 ships the pattern constraint (ADR-0007) as minimum structural defense; Phase 2's `IndexHealthProbe` promotes to enum. The promotion will be a Phase 2 ADR; not actionable in Phase 1.
