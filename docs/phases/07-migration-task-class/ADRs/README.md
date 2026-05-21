# Phase 07 — Add migration task class (Chainguard distroless): ADRs

Architecture Decision Records for Phase 7, in Nygard format. Each ADR captures one load-bearing decision: the context, the alternatives considered, what was chosen, the tradeoffs accepted, the consequences, and how reversible the choice is.

**Phase architecture:** [phase-arch-design.md](../phase-arch-design.md) — full architecture spec.
**Source design:** [final-design.md](../final-design.md) — synthesized from three competing lens designs.
**Devil's-advocate critique:** [critique.md](../critique.md) — the why behind several of these decisions.
**Production reference:** [docs/production/adrs/](../../../production/adrs/) — the project-level ADR set this phase composes with.

## Index

| # | Title | Tags |
|---|---|---|
| [0001](0001-no-multi-plugin-coordinator-in-phase-7.md) | No `MultiPluginCoordinator` in Phase 7 — emit `Both` + `RequiresMultiPluginCoordination` and stop | phase-boundary · adr-0042 · event-sourcing · anti-decision · planner |
| [0002](0002-shell-invocation-trace-probe-runs-in-microvm.md) | `ShellInvocationTraceProbe` executes target-repo code inside the Phase 5 microVM (not a Phase-2 reducer, not a `strace` wrapper) | threat-model · sandbox · phase-5-integration · probe-discipline |
| [0003](0003-sandbox-role-additive-enum-on-spawn.md) | Phase 5 `SandboxClient.spawn(...)` gains `role: SandboxRole` (additive enum: `GATE`, `PROBE`); no parallel `probe-control` process | open-closed · phase-5-amendment · enum · sandbox-role |
| [0004](0004-vuln-provenance-primitive-home.md) | `vuln.provenance` primitive lives at `src/codegenie/primitives/vuln_provenance/`; establishes `primitives/` as the additive home for ADR-0039 bounded core | adr-0039 · bounded-primitive · directory-layout · precedent |
| [0005](0005-probes-live-under-plugin-not-core-tree.md) | New probes ship under `plugins/distroless-migration--node--npm/probes/`, not under `src/codegenie/probes/` | adr-0031 · plugin-architecture · probe-placement · open-closed |
| [0006](0006-adapter-dispatch-explicit-final-tuple.md) | Adapter dispatch order is an explicit module-level `Final` tuple `_ADAPTER_DISPATCH_ORDER`; registration order is not load-bearing | strategy-via-data · determinism · critic-bp1 · final-tuple |
| [0007](0007-provenance-adapter-registry-stores-classes.md) | `@register_provenance_adapter` stores adapter **classes**, not instances; construction is dispatch-time with DI-aware kwargs | di · registry · open-closed · critic-bp3 · adr-0032 |
| [0008](0008-no-vuln-provenance-cache-in-phase-7.md) | No `vuln_provenance_cache` in Phase 7; ADR-0038 §Tradeoffs deferral honored; Phase 14 owns caching | adr-0038 · deferral · kernel-purity · cache · phase-14 |
| [0009](0009-phase-7-byte-edit-allowlist-fence.md) | Phase 7 fence allowlist — 10 enumerated byte-edit allowances to existing files; "additive" is mechanically defined, not aspirational | extension-by-addition · fence · §2.5 · ship-of-theseus |
| [0010](0010-chainguard-cve-image-lookup-frozen-yaml.md) | CVE-to-image lookup ships as plugin-internal frozen YAML data file; Sigstore-bundled signed-artifact upgrade deferred | data-as-config · simplicity-first · deferral · critic-sec3 |
| [0011](0011-no-chainguard-credential-class.md) | No `ChainguardPullToken` or STS apparatus in Phase 7; `cgr.dev/chainguard/*` images are public; future ADR if private registries appear | threat-model · simplicity-first · critic-sec4 · supply-chain |
| [0012](0012-dockerfile-policy-gate-strict-and-no-override.md) | `DockerfilePolicyGate` is hard-fail strict-AND across six invariants; no `--allow-policy-violations` flag | strict-and · objective-signals · gate · honest-confidence |
| [0013](0013-dockerfile-recipe-engine-dockerfile-parse.md) | Dockerfile transforms use pure-Python `dockerfile-parse` AST manipulation, not OpenRewrite; engine split formally recorded | strategy · jvm-tax · convention-split · determinism |
| [0014](0014-multi-stage-refactor-recipe-synchronous.md) | `DockerfileMultiStageRefactorTransform` is synchronous; per-stage `asyncio.gather` over CPU-bound AST work is theatrical | honesty · cpu-bound-async · critic · simplicity |
| [0015](0015-allowed-binaries-amendment-dive-buildx.md) | `ALLOWED_BINARIES` gains `dive` and `docker buildx`; `strace` is explicitly NOT added | subprocess-discipline · allowed-binaries · amendment · supply-chain |
| [0016](0016-tccm-derived-queries-band.md) | TCCM gains a `derived_queries:` band that holds derived-callable invocations separately from `must_read` (which is evidence to load) | tccm · adr-0029 · progressive-disclosure · schema-additive · critic-roadmap6 |
| [0017](0017-both-provenance-exits-code-8-with-coordination-summary.md) | When `assemble_provenance` returns `Both`, the CLI exits with code 8 and writes `coordination-summary.yaml`; Phase 7 is "produce evidence, do not sequence" | exit-codes · operator-ergonomics · phase-boundary · adr-0042 |

### Amendment A — distroless-migration gather / transform / refusal gaps (2026-05-20)

ADRs 0018–0029 are additive per [`final-design.md` §Amendment A](../final-design.md) and [`phase-arch-design.md` §Component design — Amendment A](../phase-arch-design.md). They deepen the gather pipeline so a migration is transformed correctly or refused with typed evidence — never shipped broken.

| # | Title | Tags |
|---|---|---|
| [0018](0018-dockerfile-secret-pattern-probe.md) | `DockerfileSecretPatternProbe` inventories source-side secret acquisition; `COPY`'d external scripts are classified opaque and refused, not parsed | amendment-a · probe · secret-patterns · refuse · gap-g1 |
| [0019](0019-target-image-content-probe.md) | `TargetImageContentProbe` inventories the Chainguard target image via `crane` + published SBOM so the recipe drops redundant layers | amendment-a · probe · target-image · crane · gap-g2 |
| [0020](0020-build-toolchain-classification-catalog.md) | Build-time-only toolchain vs runtime libraries is a frozen data catalog, not a heuristic | amendment-a · data-catalog · native-modules · open-closed · gap-g3 |
| [0021](0021-runtime-shell-invocation-probe.md) | `RuntimeShellInvocationProbe` statically detects app-code shell-out; `src/**` hits block, `tests/**` hits are advisory | amendment-a · probe · tree-sitter · refuse · gap-g4-g12 |
| [0022](0022-container-probe-compat-and-blast-radius.md) | The migration blast radius includes deployment manifests; `ContainerProbeCompatProbe` analyses K8s/Compose/helm probes | amendment-a · probe · blast-radius · deployment-manifests · gap-g6 |
| [0023](0023-runtime-compat-probe.md) | `RuntimeCompatProbe` folds uid/PID-1/filesystem/locale assumptions into one advisory probe | amendment-a · probe · runtime-compat · warn · gap-g7-g10 |
| [0024](0024-multi-arch-and-external-registry-checks.md) | `BaseImageProbe` is extended (not duplicated) for architecture-coverage delta and non-public-registry detection | amendment-a · base-image · multi-arch · extension-by-addition · gap-g11-g13 |
| [0025](0025-migration-refusal-taxonomy.md) | Migration refusal is a closed typed taxonomy of `RemediationOutcome.PendingHumanReview` variants, each carrying source-location evidence | amendment-a · sum-type · refusal · make-illegal-states-unrepresentable · meta-m2 |
| [0026](0026-migration-confidence-aggregation.md) | `MigrationConfidence` is a single sum-type rollup the orchestrator refuses against | amendment-a · sum-type · confidence · functional-core · meta-m1 |
| [0027](0027-migration-observability-bundle.md) | Migration observability — a typed `transformations_applied` list plus enrichment events make the change legible to the human merger | amendment-a · observability · humans-always-merge · warn · gap-g14-g17 |
| [0028](0028-allowed-binaries-amendment-crane.md) | `ALLOWED_BINARIES` gains `crane` for daemonless OCI manifest/config/SBOM fetch | amendment-a · subprocess-discipline · allowed-binaries · amendment |
| [0029](0029-amend-byte-edit-allowlist-for-amendment-a.md) | ADR-0029 amends the ADR-0009 byte-edit allowlist to enumerate every Amendment-A source-file addition | amendment-a · fence · byte-edit-allowlist · extension-by-addition |

### Regression rescue (2026-05-21)

ADR-0030 is a post-Amendment-A remediation, not part of the original design. It re-instates a sound Layer C fix that was reverted for landing as a silent kernel edit — redone here as the loud, ADR-gated path the kernel-frozen fence mandates. Implemented by story [S19-01](../stories/S19-01-layer-c-sidecar-publishing.md).

| # | Title | Tags |
|---|---|---|
| [0030](0030-amend-kernel-allowlist-for-layer-c-sidecar-publishing.md) | Re-apply the Layer C raw-sidecar publishing fix (reverted commit `5055292`); amend the kernel-frozen `_KERNEL_ALLOWLIST` for the eight touched Layer C/G probe files | regression-rescue · fence · kernel-frozen · adr-amendment · layer-c · honest-confidence |

## Conventions

- Filenames are NNNN-kebab-case-title.md with zero-padded four-digit numbers, numbered locally per phase starting at 0001.
- Numbers are immutable — a superseded ADR keeps its number; the new one gets the next number and cross-links.
- Cross-references to production ADRs use `../../../production/adrs/NNNN-*.md`.
- Cross-references to ADRs in this folder use `NNNN-*.md`.
- Cross-references to ADRs in another phase's folder use `../../{phase}/ADRs/NNNN-*.md`.

## Decisions noted but not yet documented

These are decisions identified in `phase-arch-design.md` (especially under Gap analysis) or in `final-design.md` (Departures + Synthesis ledger) that have not yet been extracted into a standalone ADR. Each is a candidate for a future Phase-7 ADR amendment if/when implementation surfaces enough specificity:

- **`coordination-summary.yaml` exact field schema** — Gap 2 in arch spec, Open Question §1. Provisional shape (`workflow_id`, `cve_id`, `app`, `base`, `proposed_plugin_routes`, `awaiting`, `schema_version: "phase-7-0"`) is sketched in `phase-arch-design.md §Component design §13` but the precise Pydantic shape depends on Phase 8's Planner consumer that doesn't yet exist. First implementation story (S0/S1) pins it; until then, the shape is intentionally implementation-defined. The forward-compatibility hook is the `schema_version` field; the fence is `extra="forbid"`.

- **`AdapterFactory` DI-kwarg vocabulary** — Open Question §3. ADR-0007 records the principle ("registry stores classes; construction is dispatch-time with DI-aware kwargs") and lists `{sbom_reader, logger, image_manifest_cache}` as the seed set, but the exact closed set of well-known kwarg names is deferred to the first adapter-implementation story. Promote to an ADR if/when a second wave of adapters (Phase 8+) needs a kwarg ADR-0007 didn't anticipate.

- **`codegenie list-coordination-candidates` CLI shape** — Open Question §2; arch spec §Component design §14. Operator-facing readout; tiny script, not a Phase-8 fragment. Field set + `--format` flag default land in the first implementation story. Not a load-bearing structural decision.

- **`_ADAPTER_DISPATCH_ORDER` for `Layer.RUNTIME`** — Open Question §4. Phase 7 ships no runtime adapter; the tuple row is reserved. First runtime adapter (JRE-bundled, future phase) exercises it. ADR-0006 covers the principle; the `RUNTIME` row's behavior is property-tested but the first concrete runtime adapter's ADR will refine. Not extracted now because the decision is "reserve the slot."

- **Adapter exception-handling policy beyond `ProvenanceError`** — `assemble_provenance` catches typed `ProvenanceError` and converts to `Unknown(reason="adapter_error")`; all other exceptions propagate per Rule 12 (fail loud). This is documented as a single line in ADR-0007 Consequences and the assembly component spec. Surface as a standalone ADR if a future adapter family demands graceful degradation for a non-`ProvenanceError` exception class.

- **`SyftSbom.extra="allow"` byte-level trust** — Gap 3 in arch spec. Phase 2's deliberate decision is carried forward; Phase 7 documents the deferral but does not own it. Phase 12 (validation depth) owns the resolution. Not a Phase-7 ADR.

- **Polyglot adapter resolution tiebreaker** — Gap 4 in arch spec, Open Question §5. Phase 7 ships "first non-`Unknown` per layer, in `Ecosystem`-enum-sorted order" (deterministic). Real polyglot detection (e.g., a workflow that genuinely has both npm and yarn-berry resolutions for the same CVE) is deferred to a future plugin story. ADR-0006 covers the dispatch-order discipline; the tiebreaker enhancement is a separate ADR if/when polyglot detection surfaces.

- **TCCM `derived_queries` arg-template syntax** — Open Question §9. Phase 7 uses `$workflow.cve` style; the exact resolver (`$x.y` vs `${x.y}` vs Jinja-like) is pinned in the first plugin-loader implementation story. ADR-0016 covers the band's existence; the template grammar is a tactical pick.

- **Anti-decision: No LLM in Phase 7** — Goal "$0.00 LLM spend per Phase 7 workflow." Extends production ADR-0005 to the migration task class via `import_linter` contract on `src/codegenie/primitives/vuln_provenance/` and `plugins/distroless-migration--*/`. Treated as a direct extension of the production ADR; not extracted to avoid duplication. ADR-0009's fence allowlist enforces it.

- **Anti-decision: No real PRs in Phase 7** (deferred to Phase 11). Roadmap-level decision; not an architecture choice for this phase.

- **Anti-decision: No portfolio-scale dispatch cost solution** (`applies_to_tasks` filter is dispatch-time, not gather-time). Gap 1 in arch spec; Phase 10 owns the resolution. Phase 7 ships telemetry (`ShellInvocationObserved` event carries `boot_cold_ms`, `boot_warm_ms`, `cache_hit: bool`) so Phase 10's cost model has data. Not a Phase-7 ADR.
