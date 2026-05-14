# Phase 02 — Context gathering — Layers B–G: ADRs

Architecture Decision Records for Phase 2, in Nygard format. Each ADR captures one load-bearing decision: the context, the alternatives considered, what was chosen, the tradeoffs accepted, the consequences, and how reversible the choice is.

**Phase architecture:** [phase-arch-design.md](../phase-arch-design.md) — full architecture spec.
**Source design:** [final-design.md](../final-design.md) — synthesized from three competing lens designs.
**Critique:** [critique.md](../critique.md) — devil's-advocate findings that shaped many of these decisions.
**Production reference:** [docs/production/adrs/](../../../production/adrs/) — the project-level ADR set this phase composes with.
**Prior phase:** [Phase 1 ADRs](../../01-context-gather-layer-a-node/ADRs/) — the spine these decisions extend.

## Index

| # | Title | Tags |
|---|---|---|
| [0001](0001-add-docker-and-security-cli-tools-to-allowed-binaries.md) | Add `docker`, `strace`, and security/SBOM CLIs to `exec.ALLOWED_BINARIES` | registry · tool-use · security · allowlist · localv2-conformance |
| [0002](0002-tree-sitter-grammars-phase-2-amendment.md) | `py-tree-sitter` Phase 2 amendment — the one named-trigger C-extension exception | dependency-policy · supply-chain · cve-surface · named-trigger · amendment |
| [0003](0003-coordinator-heaviness-sort-annotation.md) | `@register_probe(heaviness=, runs_last=)` — registry annotations, not Probe ABC fields | registry · coordinator · scheduling · contract-preservation · open-closed |
| [0004](0004-image-digest-as-declared-input-token.md) | Image digest as a `declared_inputs` special token, not a `cache_key()` override | cache · declared-inputs · chokepoint-preservation · additive-extension |
| [0005](0005-secret-findings-no-plaintext-persistence.md) | Secret findings — no plaintext persistence anywhere in Phase 2 | security · secrets · redaction · chokepoint · threat-model · structural-defense |
| [0006](0006-index-freshness-sum-type-location.md) | `IndexFreshness` sum type lives at `codegenie.indices.freshness` with one Phase-2 consumer | typing · sum-type · domain-modeling · open-closed · honest-confidence |
| [0007](0007-no-plugin-loader-in-phase-2.md) | No Plugin Loader in Phase 2 — Protocols + TCCMLoader skeleton only | roadmap-fidelity · plugin-architecture · scope · phase-boundary · premature-pluggability |
| [0008](0008-no-event-stream-in-phase-2.md) | No event stream in Phase 2 — Phase 0 audit anchor unchanged | observability · audit · scope · phase-boundary · defer · event-sourcing |
| [0009](0009-pytest-xdist-veto-preserved.md) | `pytest-xdist` veto preserved — portfolio CI lane stays serial | ci · testing · phase-fidelity · veto-preservation · flake-budget |
| [0010](0010-redacted-slice-smart-constructor-at-writer-boundary.md) | `RedactedSlice` smart constructor — making "redactor was called" type-checkable | typing · smart-constructor · structural-defense · secrets · chokepoint |

## Conventions

- **Filenames** are `NNNN-kebab-case-title.md` with zero-padded four-digit numbers, numbered locally per phase starting at 0001.
- **Numbers are immutable** — a superseded ADR keeps its number; the new one gets the next number and cross-links.
- **Cross-references** to production ADRs use `../../../production/adrs/NNNN-*.md`. Cross-references to other phase ADRs use the relative filename inside this folder. Cross-references to Phase 0 / Phase 1 ADRs use `../../00-bullet-tracer-foundations/ADRs/NNNN-*.md` and `../../01-context-gather-layer-a-node/ADRs/NNNN-*.md` respectively.
- **The phase-arch-design and final-design documents are the architecture contract**; ADRs are the durable rationale. When the two diverge, the ADR is the *why* and the arch doc is the *what*.

## What got an ADR

These decisions met the bar — a real choice, viable alternatives, load-bearing on Phase 2 implementation or Phase 3+ interfaces, durable enough that a future reader benefits from rationale before changing them:

- **`ALLOWED_BINARIES` additions for Phase 2.** Eight new entries (`docker`, `strace`, `semgrep`, `syft`, `grype`, `gitleaks`, `scip-typescript`, `tree-sitter`) governed by one omnibus ADR with the policy stated once (ADR-0001).
- **`py-tree-sitter` as the one named-trigger C-extension amendment** to [Phase 1 ADR-0009](../../01-context-gather-layer-a-node/ADRs/0009-no-new-c-extension-parser-dependencies.md) (ADR-0002).
- **Coordinator `heaviness` and `runs_last` annotations** as registry kwargs on `@register_probe` — preserves the Phase 0 frozen `Probe` ABC against [P] and [S]'s contract-edit proposals (ADR-0003).
- **Image digest as a `declared_inputs` special token** — preserves Phase 0's universal-cache-key discipline against [P]'s `cache_key()` override hook (ADR-0004).
- **Secret findings — no plaintext persistence** — structural fix against [S]'s encrypt-at-rest theatre; Phase 5 microVM as the named escalation door (ADR-0005).
- **`IndexFreshness` module location + one Phase-2 consumer** — closes shared-blind-spot #1 (schema-without-consumer); `AdapterConfidence` deferred to Phase 3 (ADR-0006).
- **No Plugin Loader in Phase 2** — [production ADR-0031](../../../production/adrs/0031-plugin-architecture.md) §Consequences §1 honored verbatim; Phase 3 ships loader + first plugin + four adapters together (ADR-0007).
- **No event stream in Phase 2** — [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md) §Consequences §1 honored; Phase 9 owns the canonical event log; Phase 0 audit anchor + slice metadata sufficient (ADR-0008).
- **`pytest-xdist` veto preserved** — re-affirms Phase 0's recorded 10/4 veto against [P]'s unilateral reversal; advisory bench canaries + named escape valve (ADR-0009).
- **`RedactedSlice` smart constructor at the writer boundary** — Gap 4 closure; makes "redactor was called" type-checkable; structural defense layered atop ADR-0005 (ADR-0010).

## Decisions noted but not yet documented

Surfaced during ADR extraction as plausibly worth ADR-ing, but the documentation in `final-design.md` and `phase-arch-design.md` doesn't develop them enough to write a confident ADR. Flagged for the implementer / next-phase author:

- **`@register_index_freshness_check(index_name: IndexName)` decorator-registry inside `codegenie.indices.freshness`** (`phase-arch-design.md "Gap analysis & improvements" Gap 3`). Applies Open/Closed at B2's `match index_name:` block before it grows every phase; ~30 LOC. The arch doc defaults to Phase 2 introduction but flags "revisit at Phase 3 entry if the decorator-registry adds friction the synthesis didn't anticipate." Worth an ADR amendment to ADR-0006 once the implementer decides whether to land in Phase 2 or defer.

- **Per-module `mypy --warn-unreachable` rollout policy** (`phase-arch-design.md "Open questions deferred to implementation" §5`). Phase 2 enables it on `codegenie.{indices, probes/index_health.py, report, adapters, tccm}/**` via `pyproject.toml` overrides. Full-repo rollout is a tracked backlog item; Phase 3 or a later phase will earn its own ADR when the rollout fires.

- **Reference TCCM regeneration policy + `stale-scip` fixture regeneration ritual** (`phase-arch-design.md "Open questions deferred to implementation" §7`). The structural assertion (`CommitsBehind.n >= 1`) is tool-version-agnostic, but the regeneration ritual is implementer-time work. A Phase 2 ADR may earn its place if upstream `scip-typescript` header-format changes start triggering fixture drift. For now, `tests/fixtures/portfolio/stale-scip/README.md` documents the policy.

- **`ExternalDocsProbe` enablement + host-allowlist config schema** (`phase-arch-design.md "Open questions deferred to implementation" §4`). Phase 2 ships opt-in skip-cleanly; the `external_docs:` config-key shape lands when the first real user opts in. Worth a phase-level ADR (Phase 2 amendment or Phase 4 entry) once the use case surfaces.

- **`SkillsLoader` org-shared tier per-tier signing (Sigstore-style)** (`phase-arch-design.md "Open questions deferred to implementation" §3`). Phase 14 multi-tenant concern; not actionable in Phase 2. The three-tier merge with first-tier-wins + loud `skill_shadowed` warning is the Phase 2 commitment.

- **Phase 5 microVM cleartext-access protocol** (`phase-arch-design.md "Open questions deferred to implementation" §1`). The exact handoff (`(file:line, pattern_class, fingerprint)` and re-scan? one-time decryption capability tied to workflow ID?) is a Phase 5 design concern. Phase 2's commitment is named in ADR-0005: no plaintext anywhere Phase 4 can reach it. Phase 5 will earn its own ADR(s).
