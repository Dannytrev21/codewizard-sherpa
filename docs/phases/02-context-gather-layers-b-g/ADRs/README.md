# Phase 2 — Context gathering: Layers B–G: ADRs

Architecture Decision Records for Phase 2, in Nygard format. Each ADR captures one load-bearing decision: the context, the alternatives considered, what was chosen, the tradeoffs accepted, the consequences, and how reversible the choice is.

**Phase architecture:** [phase-arch-design.md](../phase-arch-design.md) — full architecture spec.
**Source design:** [final-design.md](../final-design.md) — synthesized from three competing lens designs.
**Critique:** [critique.md](../critique.md) — devil's-advocate findings that shaped many of these decisions.
**Production reference:** [docs/production/adrs/](../../../production/adrs/) — the project-level ADR set this phase composes with.
**Prior phases:** [Phase 0 ADRs](../../00-bullet-tracer-foundations/ADRs/) · [Phase 1 ADRs](../../01-context-gather-layer-a-node/ADRs/) — the spine these decisions extend.

## Index

| # | Title | Tags |
|---|---|---|
| [0001](0001-peer-outputs-binding.md) | `consumes_peer_outputs` class attribute + frozen-snapshot positional arg | coordinator · probe-contract · chokepoint-preservation · peer-data · synthesizer-departure |
| [0002](0002-c4-runtime-trace-class-only-phase-5-impl.md) | `RuntimeTraceProbe` (C4) ships class + sub-schema only in Phase 2; impl deferred to Phase 5 | scope · layer-c · phase-evolution · sandbox-dependency · contract-surface |
| [0003](0003-subprocess-sandbox-profile-extension.md) | Extend Phase 1's `run_in_sandbox` chokepoint; no new `SandboxStrategy` interface | security · sandbox · chokepoint-preservation · scope-discipline · synthesizer-departure |
| [0004](0004-tools-digests-yaml-pin-manifest.md) | `tools/digests.yaml` binary pin manifest with install-gate verification and cache-key inclusion | supply-chain · cache-invalidation · security · catalog · install-gate |
| [0005](0005-allowed-binaries-additions.md) | Add `scip-typescript`, `semgrep`, `syft`, `grype`, `gitleaks`, `docker` to `ALLOWED_BINARIES` | tool-use · security · allowlist · localv2-conformance · extension-seam |
| [0006](0006-output-sanitizer-passes-4-5.md) | `OutputSanitizer` Pass 4 (secret-finding fingerprinter) + Pass 5 (prompt-injection marker tagger) | security · sanitizer · chokepoint · secret-handling · prompt-injection · schema-defense |
| [0007](0007-buildgraph-ignore-scripts-and-resolution-status.md) | `BuildGraphProbe` runs `pnpm list -r --ignore-scripts` with two-stage `resolution_status` output | build-graph · supply-chain · facts-not-judgments · postinstall-rce · synthesizer-departure |
| [0008](0008-conventions-catalog-closed-enum-ci-lint.md) | Conventions catalog `detect.type` is a closed enum with CI lint enforcing schema-code parity | catalog · data-as-code · ci-lint · extension-by-addition · convention-degradation |
| [0009](0009-external-docs-filesystem-only-phase-2.md) | `ExternalDocsProbe` is filesystem-only in Phase 2; URL/Confluence/Notion fetch deferred | scope · ssrf · network-policy · phase-evolution · localv2-conformance |
| [0010](0010-tantivy-as-opt-in-extra.md) | `tantivy` is an opt-in extra (`pip install codegenie[search]`); default BM25 path is ripgrep | dependency-policy · c-extension · simplicity · test-coverage · search-backend |
| [0011](0011-index-health-advisory-budget-and-strict-flag.md) | `IndexHealthProbe` advisory budget (200 ms, no hard kill); `--strict` flag is the CI failure mechanism | honesty-oracle · failure-isolation · budget-policy · cli-flag · synthesizer-departure |
| [0012](0012-audit-chain-blake3-rolling-head.md) | Audit log gains a rolling BLAKE3 chain head; chain breaks are observability, not gather failure | audit · integrity · supply-chain · observability · phase-evolution |
| [0013](0013-scip-node-modules-conditional-mount.md) | `SCIPIndexProbe` conditionally mounts `node_modules` read-only; never invokes `npm install` | scip · node-modules · postinstall-rce · evidence-quality · sandbox-policy · synthesizer-departure |

## Conventions

- **Filenames** are `NNNN-kebab-case-title.md` with zero-padded four-digit numbers, numbered locally per phase starting at 0001.
- **Numbers are immutable** — a superseded ADR keeps its number; the new one gets the next number and cross-links.
- **Cross-references** to production ADRs use `../../../production/adrs/NNNN-*.md`. Cross-references to other phase ADRs use the relative filename inside this folder. Cross-references to Phase 0/1 ADRs use `../../00-bullet-tracer-foundations/ADRs/NNNN-*.md` and `../../01-context-gather-layer-a-node/ADRs/NNNN-*.md`.
- **The phase-arch-design and final-design documents are the architecture contract**; ADRs are the durable rationale. When the two diverge, the ADR is the *why* and the arch doc is the *what*.

## What got an ADR

These decisions met the bar — a real choice with viable alternatives, load-bearing on Phase 2 implementation or Phase 3+ interfaces, durable enough that a future reader benefits from rationale before changing them.

The 18 conflict-resolution rows in `final-design.md "Synthesis ledger"` and the nine "Departures from all three inputs" each surfaced one or more ADR candidates; the set was consolidated to 13 ADRs covering:

- **Coordinator contract extensions** — `consumes_peer_outputs` opt-in (0001) — the minimal surface change required by `IndexHealthProbe`'s honesty-oracle role. Replaces `[B]`'s `ProbeContext.peer_outputs` Mapping per critic §B-3.
- **Phase 2 scope splits** — C4 RuntimeTrace deferred to Phase 5 (0002), ExternalDocs filesystem-only (0009), tantivy as opt-in extra (0010). Each surgically separates "lands in Phase 2 contract" from "lands in Phase 5/14 implementation" or "lands as opt-in capability."
- **Security chokepoint discipline** — sandbox profile extension instead of `SandboxStrategy` interface (0003), `OutputSanitizer` Pass 4/5 (0006), tools-digests pin manifest (0004), audit BLAKE3 chain head (0012). Each preserves Phase 0/1's single-chokepoint pattern.
- **Tool allowlist extension** — six new binaries (0005) following the Phase 1 per-binary-named precedent.
- **Probe-level invariant decisions** — BuildGraph `--ignore-scripts` + resolution_status (0007), SCIP conditional `node_modules` mount (0013), IndexHealth advisory budget + `--strict` (0011), conventions catalog closed-enum lint (0008). Each closes a specific critic attack or shared blind spot.

## Decisions noted but not yet documented

Surfaced during ADR extraction as plausibly worth ADR-ing, but the documentation in `final-design.md` and `phase-arch-design.md` doesn't develop them enough to write a confident ADR. Flagged for the implementer / next-phase author:

- **`gitleaks --redact` mandatory at wrapper level** (`final-design.md §7.2 GitleaksProbe`, `"Conflict-resolution table" D13`). The discipline is honored by ADR-0005 (gitleaks subsection) and ADR-0006 (Pass 4 belt-and-suspenders); a dedicated ADR was rejected as over-extracting — the policy is contained in those two ADRs and the wrapper's CI test asserts the enforcement.

- **Per-file findings sub-cache shape** (`.codegenie/cache/{semgrep,gitleaks,tree-sitter}/by-file/`) (`final-design.md "Conflict-resolution table" D14`). The cache-key discipline (`(file_content_blake3, rule_pack_version, grammar_version)`) is a Phase-1-cache-shape generalization. A dedicated ADR was rejected as a mechanical consequence of ADR-0004 (digest in cache key) and Phase 1's existing cache pattern; the implementer should surface it as ADR-0014 if the GC lifecycle (`final-design.md "Open questions"` #6) surfaces unresolved tradeoffs.

- **Schema cross-probe dependency rule** (`if cve_scan.* present then index_health.cve.confidence MUST be present`) via Draft 2020-12 `if/then` (`final-design.md "Components" #11`, "Conflict-resolution table" D15-adjacent). A dedicated ADR was rejected as a schema-mechanics detail; the rule lives in the envelope schema and is asserted by `tests/integration/test_schema_cross_probe_dependency.py`. If the rule grows past one cross-probe pair, an ADR may be warranted.

- **Closed-form per-domain confidence rules for `IndexHealthProbe`** (e.g., the formula for `coverage_pct` per domain). ADR-0011 commits to the discipline but defers the per-domain formula bodies to implementation. If the per-domain formulas surface non-trivial tradeoffs at implementation time (e.g., what counts as "coverage" for the `cve` domain when CVE counts can be zero by virtue), an ADR amendment to 0011 captures the choice.

- **`gitpython` vs `git` subprocess for B2's `rev-list --count`** (`final-design.md "Open questions"` #7). Default `gitpython`; subprocess as fallback. ADR-0011 acknowledges the open question; the resolution lands at implementation. If Phase 14 reveals `gitpython` instability at portfolio scale, an ADR amendment captures the switch.

- **`docker buildx` driver choice for `SyftSBOMProbe`** (`final-design.md "Open questions"` #1). The host-daemon socket coupling is unresolved; the implementer picks `docker build` default or `buildx --driver=docker-container` based on what the sandbox can constrain. ADR-0005's `docker` subsection acknowledges the open question; resolution is documented at integration time.

- **Per-probe sub-schema release-versioning policy** (`final-design.md "Open questions"` #2; Phase 1 ADR-0004 deferred this; Phase 1's README "Decisions noted but not yet documented" referenced Phase 2). Phase 2 ships sub-schemas at v1 and defers the policy to Phase 3 when the first cross-phase sub-schema change is anticipated. A Phase 3 ADR or amendment to Phase 1 ADR-0004 captures the policy.
