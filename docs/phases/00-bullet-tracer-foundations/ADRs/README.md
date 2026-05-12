# Phase 00 — Bullet tracer + project foundations: ADRs

Architecture Decision Records for Phase 0, in Nygard format. Each ADR captures one load-bearing decision: the context, the alternatives considered, what was chosen, the tradeoffs accepted, the consequences, and how reversible the choice is.

**Phase architecture:** [phase-arch-design.md](../phase-arch-design.md) — full architecture spec.
**Source design:** [final-design.md](../final-design.md) — synthesized from three competing lens designs.
**Critique:** [critique.md](../critique.md) — devil's-advocate findings that shaped many of these decisions.
**Production reference:** [docs/production/adrs/](../../../production/adrs/) — the project-level ADR set this phase composes with.

## Index

| # | Title | Tags |
|---|---|---|
| [0001](0001-cache-content-hash-algorithm.md) | Cache content-hash algorithm — BLAKE3 for content, SHA-256 for identity | cache · hashing · determinism · audit |
| [0002](0002-fence-ci-job-no-llm-in-gather.md) | `fence` CI job enforcing no-LLM-in-gather | ci · determinism · supply-chain · invariant |
| [0003](0003-two-level-cache-key-schema-versioning.md) | Two-level cache-key schema versioning — envelope vs per-probe | cache · schema · invalidation · scalability |
| [0004](0004-probe-execution-audit-anchor.md) | Per-probe audit anchor — `cache_key` + `blob_sha256` in `ProbeExecutionRecord` | audit · provenance · cross-phase · cost-attribution |
| [0005](0005-coordinator-async-from-day-one.md) | Coordinator is async from day one, one probe in Phase 0 | coordinator · concurrency · interface · phase-evolution |
| [0006](0006-pyproject-toml-extras-shape.md) | `pyproject.toml` extras shape — `gather` / `dev` / `service` / `agents` | packaging · dependencies · phase-evolution · supply-chain |
| [0007](0007-probe-contract-frozen-snapshot.md) | Probe contract frozen via byte-for-byte snapshot test against `localv2.md §4` | contract · stability · drift-detection · invariant |
| [0008](0008-output-sanitizer-two-pass-chokepoint.md) | Output sanitizer is the single path from `ProbeOutput` to disk — two-pass, no synchronous gitleaks | security · chokepoint · privacy · provenance |
| [0009](0009-cache-hit-pass-through-coordinator-output.md) | Cache-hit pass-through as a first-class coordinator output (`ProbeExecution = Ran \| CacheHit \| Skipped`) | coordinator · cache · interface · phase-evolution |
| [0010](0010-pydantic-probe-output-validator.md) | Pydantic `_ProbeOutputValidator` as the probe-output trust boundary | validation · trust-boundary · type-safety · security |
| [0011](0011-codegenie-directory-permissions-model.md) | `.codegenie/` permissions model — 0700/0600 with post-CI-cache-restore re-chmod | security · ci · permissions · cross-platform |
| [0012](0012-subprocess-allowlist-chokepoint.md) | Subprocess allowlist — single chokepoint at `codegenie/exec.py` | security · chokepoint · tool-use · phase-evolution |
| [0013](0013-layered-additional-properties-schema.md) | Layered `additionalProperties` schema policy — strict envelope, loose `probes.*`, per-probe sub-schemas | schema · validation · extension · contract |

## Conventions

- **Filenames** are `NNNN-kebab-case-title.md` with zero-padded four-digit numbers, numbered locally per phase starting at 0001.
- **Numbers are immutable** — a superseded ADR keeps its number; the new one gets the next number and cross-links.
- **Cross-references** to production ADRs use `../../../production/adrs/NNNN-*.md`. Cross-references to other phase ADRs use the relative filename inside this folder.
- **The phase-arch-design and final-design documents are the architecture contract**; ADRs are the durable rationale. When the two diverge, the ADR is the *why* and the arch doc is the *what*.

## Decisions noted but not yet documented in arch / final-design

The following decisions surfaced during ADR extraction as plausibly worth ADR-ing, but the documentation in `final-design.md` and `phase-arch-design.md` doesn't develop them enough to write a confident ADR. They are flagged for the orchestrator's attention:

- **Per-probe resource budget enforcement (`Probe.declared_resource_budget`).** `phase-arch-design.md §Gap analysis Gap 3` proposes this — RSS limit, raw-artifact-size limit, wall-clock limit per probe — and says "land in Phase 0 because retrofitting after Phase 2 ships is impractical." But the design doesn't fully specify the budget shape (units, semantics, what happens at overrun: warn vs hard-kill vs degrade-confidence), and the synthesis didn't explicitly conflict-resolve it. Worth promoting to an ADR once those questions are answered.
- **Coordinator prelude pass for `LanguageDetectionProbe` → `RepoSnapshot.detected_languages` write-back.** `phase-arch-design.md §Gap analysis Gap 4` identifies the missing seam: Phase 1's `NodeManifestProbe` can't filter on detected languages without it. The fix is concrete (run base-tier probes in a prelude, construct an enriched snapshot, dispatch remaining probes) but the synthesis didn't land it. Almost certainly an ADR in Phase 1 — possibly worth a Phase 0 ADR if implementation lands in Phase 0.
- **Lazy-import discipline + `import-linter` config as structural CLI cold-start defense.** `final-design.md §2.11` chooses `import-linter` over a flaky cold-start canary as the *structural* defense. The decision is real (it's a conflict resolution row L3 #12) and load-bearing for `--help` performance, but it's framed in `phase-arch-design.md` more as a tooling choice than a strategic decision. An ADR would crystallize "the import-linter ruleset is a contract" — currently it reads as an implementation detail.
- **`forbidden-patterns` regex hook set.** `final-design.md §2.5` and `phase-arch-design.md §Open questions deferred to implementation` Q6 both punt on the exact regex enumeration (e.g., should `marshal.loads`, `dill.loads`, `getattr(... , "__"` be in the initial set?). The decision is real but currently lives as a list in the design doc; an ADR could lift "this is the Phase 0 ban-list and this is the discipline for extending it" out of the design surface.
- **`uv` as the canonical installer with `pip` fallback.** `final-design.md §2.2` makes the choice but frames it as tooling. The decision has phase-evolution implications (Phase 14 CI dep management) that a focused ADR could capture. Currently lives as a row in the tooling table; arguably load-bearing enough for its own ADR.
