# Phase 02 — Context gathering — Layers B–G: Architecture

**Status:** Architecture spec
**Date:** 2026-05-14
**Inputs:** [`final-design.md`](final-design.md) (synthesized design) · [`critique.md`](critique.md) · [`design-performance.md`](design-performance.md) · [`design-security.md`](design-security.md) · [`design-best-practices.md`](design-best-practices.md) · [`docs/production/design.md`](../../production/design.md) · [`docs/roadmap.md`](../../roadmap.md) Phase 2 / Phase 3 · [`docs/localv2.md`](../../localv2.md) §4–5 · Phase 0/1 final designs · ADR-0005, 0006, 0007, 0008, 0012, 0029, 0030, 0031, 0032, 0033, 0034
**Audience:** the engineer implementing this phase

## Executive summary

Phase 2 lands the rest of the kernel-side gather pipeline on top of Phase 0/1's frozen contract surface: every Layer B–G probe that `localv2.md` §5.2–5.6 names as *language-agnostic*, plus four kernel scaffolds Phase 3 will consume on day 1 (`IndexFreshness` sum type, `TCCMLoader`, `SkillsLoader`, ADR-0032 adapter `Protocol`s). The load-bearing citizen is `IndexHealthProbe` (B2): the roadmap's exit criterion is a deliberately-seeded `stale-scip` fixture that B2 must catch in CI — encoded as `tests/adv/phase02/test_stale_scip_fixture.py`, build FAILS otherwise. The synthesis explicitly **rejected** the Plugin Loader (Phase 3 owns it per ADR-0031 §Consequences §1), every `Probe` ABC contract change (registry-side `@register_probe(heaviness=…, runs_last=…)` annotations carry the scheduling concern instead), the cryptographic-anchor freshness ceremony (defends a non-threat against an attacker who already owns `$HOME`), per-repo encryption-key theatre for secret findings (key and ciphertext in the same trust tier — Phase 2 persists **zero plaintext**), and the `pytest-xdist` reversal of Phase 0's veto. The result is a smaller Phase 2 than any of the three input lenses proposed: kernel probes + one tagged-union `IndexFreshness` + four adapter `Protocol`s (documentation as code) + `TCCMLoader` skeleton + writer-chokepoint secret redaction + one `run_external_cli` wrapper over Phase 0's `run_allowlisted`.

## Goals

These are verifiable on Phase-2 exit. Every goal is testable by code that already exists or is named in this document.

- **G1.** Every Layer B–G probe in `localv2.md` §5.2–5.6 that is *language-agnostic* ships with golden-file coverage against the 5-repo portfolio at `tests/fixtures/portfolio/`. Verified by: golden tests under `tests/golden/probes/`, one file per probe per fixture.
- **G2.** `IndexHealthProbe` (B2) surfaces a real staleness case in CI against the deliberately-seeded `tests/fixtures/portfolio/stale-scip/` fixture. Verified by: `tests/adv/phase02/test_stale_scip_fixture.py` asserting `IndexFreshness.Stale(reason=CommitsBehind(n>=1, last_indexed=<known prior commit>))`. **Build FAILS if the probe does not catch it.** This is the roadmap exit criterion.
- **G3.** Phase 0/1 frozen surfaces are unchanged. Verified by: existing Phase 0 contract-freeze snapshot test (`tests/unit/test_probe_contract.py`) still passes; Phase 0's `forbidden-patterns` pre-commit catches edits to `Probe` ABC, `OutputSanitizer.scrub` signature, `run_allowlisted` signature.
- **G4.** Single name, single module, single Phase-2 consumer for the freshness sum type: `IndexFreshness = Fresh | Stale(reason: StaleReason)` at `src/codegenie/indices/freshness.py`. Consumed by `src/codegenie/report/confidence_section.py` with `match` + `assert_never`; `mypy --warn-unreachable` is a build error on a missed case in that module.
- **G5.** Secret findings (`gitleaks`, `semgrep p/secrets`, entropy fallback) are redacted at the writer chokepoint. Verified by: `tests/adv/phase02/test_secret_in_source.py` asserting plaintext is present in **zero** persisted files (`repo-context.yaml`, every `raw/*.json`, the cache blob, the audit anchor).
- **G6.** One subprocess port for Layer B/G external CLIs: `codegenie.exec.run_external_cli`, a wrapper around Phase 0 `run_allowlisted`. Layer C (`docker`, `strace`) keeps using `run_allowlisted` directly with explicit hardening flags. No parallel chokepoint.
- **G7.** Cost target: $0/run; tokens per gather: 0. Phase 0 `fence` CI test continues to assert no LLM SDK import under `src/codegenie/`.
- **G8.** Wall-clock targets (1k-file fixture): cold p50 ≤ 90 s, warm p50 ≤ 1.5 s, incremental (single .ts change) p50 ≤ 10 s. Verified by: `tests/bench/bench_portfolio_walltime.py` (advisory; ≥ 50% regression flag, not gating).
- **G9.** Kernel scaffolding is shipped — adapter `Protocol`s + `TCCMLoader` + `SkillsLoader` + `IndexFreshness` — but **no Plugin Loader, no `plugin.yaml` parser, no `plugins/` directory in source tree**. Phase 3 ships those together with the first plugin (ADR-0031 §Consequences §1).
- **G10.** Nine new ADRs land alongside the code, each Nygard-style, recording an irreversible (or hard-to-reverse) Phase-2 commitment (see §"Path to production end state").

## Non-goals

Each entry says **why-not-in-scope** so a later reader can find the deferred work.

- **Plugin Loader, universal fallback plugin, `plugin.yaml` parser, `plugins/universal--*--*/` directory.** Why-not: ADR-0031 §Consequences §1 explicitly states "the first plugin doubles as the proof that the plugin loader works" — and the first plugin ships in Phase 3. Pulling the loader forward hollows Phase 3's exit criterion.
- **Adapter implementations** (`DepGraphAdapter`, `ImportGraphAdapter`, `ScipAdapter`, `TestInventoryAdapter`). Why-not: ADR-0032 places adapters at `plugins/{slug}/adapters/*.py` *inside the plugin*. Phase 2 ships only the `Protocol` typing surface; the first real adapter is `plugins/vulnerability-remediation--node--npm/adapters/` in Phase 3.
- **Bundle Builder, Hierarchical Planner, Supervisor.** Why-not: Phase 8 (and 9) owns these. The `TCCM` schema lands now so Phase 8 inherits a typed target.
- **Canonical event log, `.codegenie/events/` JSONL, hash-chained audit.** Why-not: ADR-0034 §Consequences §1 anchors the event log in Phase 9 (or 13). Phase 0's `runs/<utc-iso>-<short>.json` audit anchor is unchanged.
- **Cleartext secret persistence + per-repo encryption keys.** Why-not: key + ciphertext in the same trust tier ($HOME) is obfuscation, not security (critic [S] finding #5). The Phase 5 microVM is the named escalation door if any downstream stage genuinely needs cleartext.
- **`msgpack` SCIP projection, `scip-python` reader, `tantivy` default, `gitleaks-python` library, `gitpython`.** Why-not: each is rejected. `msgpack`/`scip-python` create format-coupling Phase 3 adapters would have to agree on; `tantivy` is opt-in with `ripgrep`-via-`run_allowlisted` as the tested default; `gitleaks` and `git` ship as binaries through `run_allowlisted`. Phase 1 ADR-0009 (no new C-extension parser deps) is amended **only** for `py-tree-sitter` (the one named trigger).
- **`pytest-xdist`.** Why-not: Phase 0 vetoed it 10/4 with a recorded rationale. Portfolio CI lane is small enough to run serial in ≤ 6 minutes; bench canary asserts.
- **Probe ABC changes (`cost_tier`, `capabilities: ProbeCapabilities`).** Why-not: scheduling data belongs to the registry annotation, not the contract. `localv2.md` §4 is frozen.
- **`mypy --warn-unreachable` repo-wide retrofit.** Why-not: Phase 0/1 retrofit blast radius. Phase 2 enables `--warn-unreachable` per-module on `codegenie.{indices, probes/index_health.py, report, adapters, tccm}/**` only.
- **Stage 7 Learning telemetry hooks, cost ledger, ROI dashboard.** Why-not: Phases 9, 11, 13.

## Architectural context

Phase 2 sits between Phase 1 (Layer A — Node manifests, build system, CI, deployment, test inventory) and Phase 3 (first plugin: `vulnerability-remediation--node--npm`). It is **gather-layer only** — no transforms, no LLMs, no autonomy gates. Its outputs feed two distinct downstream consumers: (a) the human-facing `CONTEXT_REPORT.md` (rendered each gather), and (b) Phase 3's first plugin (which imports the adapter `Protocol`s, the `IndexFreshness` sum type, the `TCCMLoader`, and the `run_external_cli` port).

```mermaid
flowchart LR
    P0["Phase 0<br/>Bullet tracer<br/>(ABC + Coordinator<br/>+ Cache + Sanitizer<br/>+ run_allowlisted)"]
    P1["Phase 1<br/>Layer A probes<br/>(Node manifests,<br/>parsed_manifest memo,<br/>safe_yaml.load)"]
    P2["Phase 2 (this)<br/>Layers B-G<br/>+ kernel scaffolding<br/>+ IndexFreshness<br/>+ SecretRedactor"]
    P3["Phase 3<br/>First plugin +<br/>Plugin Loader +<br/>4 adapters +<br/>universal fallback"]
    P5["Phase 5<br/>microVM sandbox<br/>(replaces direct docker;<br/>cleartext escalation door)"]
    P9["Phase 9<br/>Canonical event log<br/>(projects Phase 0 audit)"]

    P0 --> P1 --> P2 --> P3
    P2 -. defers cleartext .-> P5
    P2 -. emits slice metadata .-> P9
```

Phase 2's role in the broader 7-stage pipeline (`production/design.md` §3): it completes the **continuous-deterministic-gather** layer (commitment §2.6, ADR-0006) for everything that does **not** require a specific task class. Phase 3 begins introducing task-class-specific evidence on top of this kernel.

## 4+1 architectural views

### Logical view — what components exist and how they relate

```mermaid
classDiagram
    class Probe {
      <<abstract, Phase 0 — frozen>>
      +ProbeId name
      +list~str~ applies_to_tasks
      +list~str~ applies_to_languages
      +list~ProbeId~ requires
      +list~str~ declared_inputs
      +Literal cache_strategy
      +int timeout_seconds
      +run(ProbeContext) ProbeOutput
    }

    class ProbeRegistry {
      <<Phase 0 — extended via decorator kwargs>>
      +register(probe, heaviness, runs_last)
      +sorted_for_dispatch() list~ProbeRegEntry~
    }

    class Coordinator {
      <<Phase 0 — sort-order edit only>>
      +Semaphore single_budget
      +dispatch(probes) dict~ProbeId, ProbeExecution~
    }

    class OutputSanitizer {
      <<Phase 0 — extended by composition>>
      +scrub(slice) SanitizedSlice
    }

    class SecretRedactor {
      <<Phase 2 — new pass>>
      +redact_secrets(slice, probe_name) tuple
    }

    class run_external_cli {
      <<Phase 2 — new module function>>
      +__call__(probe_name, argv, cwd, timeout, egress) ProcessResult
    }

    class IndexHealthProbe {
      <<Phase 2 — load-bearing>>
      +cache_strategy = "none"
      +runs_last = True
      +run(ctx) ProbeOutput
    }

    class IndexFreshness {
      <<Phase 2 — sum type>>
      Fresh | Stale(reason)
    }

    class StaleReason {
      <<Phase 2 — sum type>>
      CommitsBehind | DigestMismatch | CoverageGap | IndexerError
    }

    class RuntimeTraceProbe {
      <<Phase 2 — Layer C>>
      +heaviness = "heavy"
      +run(ctx) ProbeOutput
    }

    class LayerGScanner {
      <<Phase 2 — Semgrep|Syft|Grype|Gitleaks>>
      +run(ctx) ProbeOutput
    }

    class DepGraphProbe {
      <<Phase 2 — Layer B>>
      +run(ctx) ProbeOutput
    }

    class DepGraphStrategy {
      <<Phase 2 — registry>>
      +build_for_ecosystem(PackageManager, ctx)
    }

    class AdapterProtocols {
      <<Phase 2 — kernel scaffolding>>
      DepGraphAdapter
      ImportGraphAdapter
      ScipAdapter
      TestInventoryAdapter
    }

    class TCCMLoader {
      <<Phase 2 — kernel scaffolding>>
      +load(path) Result~TCCM, TCCMLoadError~
    }

    class SkillsLoader {
      <<Phase 2 — kernel scaffolding>>
      +load_all(search_paths) Result~list~Skill~~
    }

    class ConfidenceSectionRenderer {
      <<Phase 2 — only consumer of IndexFreshness in Phase 2>>
      +render(slices) str
    }

    Probe <|.. IndexHealthProbe
    Probe <|.. RuntimeTraceProbe
    Probe <|.. LayerGScanner
    Probe <|.. DepGraphProbe
    ProbeRegistry o-- Probe
    Coordinator --> ProbeRegistry
    Coordinator --> OutputSanitizer
    OutputSanitizer ..> SecretRedactor : composes
    RuntimeTraceProbe --> run_external_cli
    LayerGScanner --> run_external_cli
    IndexHealthProbe --> IndexFreshness : returns typed
    IndexFreshness ..> StaleReason : Stale carries
    DepGraphProbe --> DepGraphStrategy : dispatches via
    ConfidenceSectionRenderer --> IndexFreshness : pattern-matches
    TCCMLoader ..> AdapterProtocols : Phase 3 will wire
```

**Reading guide.** The kernel (`Probe`, `ProbeRegistry`, `Coordinator`, `OutputSanitizer`, `Cache` — all Phase 0) is unchanged in *interface*. Phase 2 extends by composition: `SecretRedactor` is a new pass added to the sanitizer pipeline; `run_external_cli` is a new function over `run_allowlisted`; registry annotations (`heaviness`, `runs_last`) are decorator kwargs that the coordinator reads when sorting. New types (`IndexFreshness`, `StaleReason`, four adapter `Protocol`s, `TCCM`, `Skill`) live in their own packages and are imported, not inherited from kernel ABCs.

### Process view — runtime behavior

Representative incremental gather on a 5k-file TypeScript repo where `src/payments/processor.ts` changed since last gather, image rebuilt with same `FROM`-digest, `.git/` unchanged.

```mermaid
sequenceDiagram
    autonumber
    participant CLI as codegenie gather
    participant TR as Tool-readiness
    participant CO as Coordinator
    participant SCIP as SCIPIndexProbe (heavy)
    participant RT as RuntimeTraceProbe (heavy)
    participant SEM as SemgrepProbe (medium)
    participant LIGHT as Light probes (B/D/E)
    participant B2 as IndexHealthProbe (runs_last)
    participant SAN as OutputSanitizer
    participant SR as SecretRedactor
    participant WR as Writer + Cache
    participant CR as ConfidenceSection Renderer

    CLI->>TR: check semgrep/syft/grype/gitleaks/scip-typescript/docker/strace on PATH
    TR-->>CLI: ok (or typed MissingToolError + install hint)
    CLI->>CO: dispatch Phase 1 + Phase 2 probes
    Note over CO: sorted by registry heaviness annotation;<br/>single Semaphore(min(cpu_count(), 8))
    par heavy probes start first
        CO->>SCIP: run() — MISS (.ts changed); ~8s
        CO->>RT: run() — HIT (image-digest unchanged); ~0.1s
    and medium then light fill slots
        CO->>SEM: run() — incremental MISS; ~3s
        CO->>LIGHT: run() — mix of HIT/MISS
    end
    Note over B2: dispatched LAST because runs_last=True
    CO->>B2: run() — reads sibling slices
    B2->>B2: construct IndexFreshness for each index
    B2-->>CO: ProbeOutput with typed freshness
    CO->>SAN: scrub(merged_envelope)
    SAN->>SR: redact_secrets(slice, probe_name)
    SR-->>SAN: (redacted_slice, in-memory findings)
    SAN-->>WR: SanitizedSlice
    WR->>WR: atomic .tmp → os.replace<br/>(repo-context.yaml + raw/*)
    CR->>CR: render Confidence section<br/>(match on every IndexFreshness)
    CR-->>WR: CONTEXT_REPORT.md
    WR-->>CLI: exit 0 (~10s total)
```

**Three load-bearing properties this diagram encodes:**

1. `IndexHealthProbe` dispatches **after** every sibling probe — enforced by the `runs_last=True` registry annotation, not by topological `requires=[every_probe]` hack (which the performance lens proposed and the synthesis rejected).
2. Sanitizer + Redactor + Writer form a **single chokepoint**. There is no second pathway from `ProbeOutput` to disk. The `SecretRedactor` is composition inside the existing Phase 0 sanitizer, not a parallel pipeline.
3. No `pytest-xdist`, no internal `ThreadPoolExecutor` inside any probe. The Phase 0 single `Semaphore(min(cpu_count(), 8))` is the only concurrency budget; heavy probes simply *start first* under it.

### Development view — package tree

```mermaid
graph TD
    subgraph CG["src/codegenie/ — Phase 0/1 frozen + Phase 2 additions"]
        direction TB
        CLI["cli.py — Phase 0; tool-readiness extended"]
        EXEC["exec.py — Phase 0 run_allowlisted +<br/>NEW run_external_cli"]
        COORD["coordinator.py — Phase 0 + sort-order edit<br/>(reads heaviness from registry)"]
        CACHE["cache.py — Phase 0 (declared_inputs unchanged)"]
        OUT["output/sanitizer.py — Phase 0 + SecretRedactor pass<br/>output/writer.py — Phase 0 unchanged"]

        subgraph PROBES["probes/ — Phase 0 +1 +2"]
            P1["layer_a/* — Phase 1"]
            P2B["layer_b/<br/>scip_index.py, index_health.py,<br/>dep_graph.py, tree_sitter_import_graph.py,<br/>generated_code.py, node_reflection.py,<br/>semantic_index_meta.py"]
            P2C["layer_c/<br/>dockerfile.py, sbom.py, cve.py,<br/>runtime_trace.py, certificate.py,<br/>entrypoint.py, shell_usage.py"]
            P2D["layer_d/<br/>skills_index.py, conventions.py, adrs.py,<br/>policy.py, exceptions.py, repo_notes.py,<br/>repo_config.py, external_docs.py"]
            P2E["layer_e/<br/>ownership.py, service_topology_stub.py,<br/>slo_stub.py"]
            P2G["layer_g/<br/>semgrep.py, ast_grep.py,<br/>ripgrep_curated.py, gitleaks.py,<br/>test_coverage_mapping.py"]
        end

        subgraph KERNEL["NEW Phase 2 kernel packages"]
            INDICES["indices/<br/>freshness.py — IndexFreshness sum type"]
            ADAPT["adapters/<br/>protocols.py — 4 Protocols (zero impls)<br/>confidence.py — AdapterConfidence placeholder"]
            TCCM["tccm/<br/>loader.py, model.py, queries.py"]
            SKILLS["skills/<br/>loader.py, model.py"]
            CONV["conventions/<br/>catalog.py, model.py"]
            DEP["depgraph/<br/>builder.py, model.py, registry.py"]
            REPORT["report/<br/>confidence_section.py"]
        end

        PARSERS["parsers/safe_yaml.py — Phase 1<br/>(reused by SkillsLoader)"]
    end

    subgraph TESTS["tests/"]
        UNIT["unit/{probes,indices,adapters,tccm,skills,conventions,depgraph,report}/"]
        INT["integration/{portfolio,tccm}/"]
        GOLDEN["golden/probes/<probe>/<fixture>.json"]
        PROP["property/"]
        ADV["adv/phase02/<br/>test_stale_scip_fixture.py (LOAD-BEARING)"]
        FIX["fixtures/portfolio/<br/>minimal-ts/, native-modules/,<br/>monorepo-pnpm/, distroless-target/,<br/>stale-scip/  (LOAD-BEARING)"]
        BENCH["bench/bench_portfolio_walltime.py (advisory)"]
    end

    subgraph DOCS["docs/phases/02-context-gather-layers-b-g/"]
        ADRs["ADRs/0001..0009 (9 new ADRs)"]
        REF["_reference-tccm/tccm.yaml<br/>(documentation, NOT a plugin)"]
    end

    CLI --> COORD
    COORD --> PROBES
    PROBES --> EXEC
    PROBES --> OUT
    PROBES --> INDICES
    PROBES --> DEP
    P2D --> SKILLS
    P2D --> CONV
    P2D --> TCCM
    REPORT --> INDICES
```

**Reading guide.** The Phase 0/1 layout is preserved. Six new top-level packages (`indices`, `adapters`, `tccm`, `skills`, `conventions`, `depgraph`) + one render package (`report`) land — fewer than the best-practices lens proposed (seven, plus generic ambiguity), because `runtime/` and `security/` from that lens are folded into `probes/layer_c/` and `probes/layer_g/` respectively. The probe-by-layer subdirectory pattern (`probes/layer_a/`, `probes/layer_b/`, …) follows production-design §8.3's "organize by architectural layer, not by feature."

### Physical view — deployment topology (developer / CI)

```mermaid
graph LR
    subgraph DEV["Developer host (macOS or Linux)"]
        direction TB
        DEVPATH["$PATH must contain:<br/>git, node, npm/pnpm/yarn/bun,<br/>semgrep, syft, grype, gitleaks,<br/>scip-typescript, tree-sitter,<br/>docker (optional), strace (Linux only)"]
        REPO["~/work/some-node-repo/<br/>(analyzed repo)"]
        OUT_DEV[".codegenie/ inside analyzed repo<br/>0700 dir, 0600 files<br/>context/raw/*.json (redacted)<br/>context/repo-context.yaml<br/>cache/blobs/<br/>runs/<utc-iso>-<short>.json"]
        HOME["~/.codegenie/<br/>skills/, conventions/, config/,<br/>tool_cache/<br/>(0700/0600)"]
    end

    subgraph CI["GitHub Actions (ubuntu-24.04, canonical)"]
        direction TB
        CIRUN["Job: gather-portfolio<br/>(serial; no xdist; ≤6 min)"]
        CIIMG["actions image:<br/>preinstalled binaries above<br/>+ bubblewrap (best-effort hardening)"]
        CIFIX["tests/fixtures/portfolio/<br/>(regenerated each run;<br/>NO committed .codegenie/cache/)"]
        CIADV["Job: adv-phase02<br/>(stale-scip fixture is BUILD-GATING)"]
    end

    DEVPATH -. invoked by .-> REPO
    REPO --> OUT_DEV
    HOME -. read by .-> OUT_DEV
    CIIMG --> CIRUN
    CIFIX --> CIRUN
    CIFIX --> CIADV
```

**Reading guide.** Phase 2 is still a local CLI (no service yet, per `production/design.md` §6 POC-to-service). The analyzed repo's `.codegenie/` is the only writable workspace; `~/.codegenie/` is read-mostly (skills, conventions, config) at 0700/0600 (Phase 0 ADR-0011). CI runs on `ubuntu-24.04` (the only image guaranteed to ship `bwrap`); macOS dev hosts skip the `bubblewrap` wrap with a single-line startup warning. **Layer C (`docker`, `strace`)** runs the analyzed-repo container under `--network=none --cap-drop=ALL --security-opt=no-new-privileges`; ADR-0012 (microVM, Phase 5) replaces those direct `docker` invocations later.

### Scenarios (+1)

#### Scenario 1: Cold gather on a 50k-LOC TypeScript service (no built image)

```mermaid
sequenceDiagram
    participant U as Operator
    participant CLI as codegenie gather
    participant CO as Coordinator
    participant SCIP as SCIPIndexProbe
    participant RT as RuntimeTraceProbe
    participant SY as SyftProbe
    participant GR as GrypeProbe
    participant SE as SemgrepProbe
    participant GL as GitleaksProbe
    participant LIGHT as light probes
    participant B2 as IndexHealthProbe
    participant SR as SecretRedactor
    participant WR as Writer

    U->>CLI: codegenie gather ~/work/svc-payments
    CLI->>CO: dispatch (heavy first)
    CO->>SCIP: ~10s re-index whole repo
    CO->>RT: docker build (~47s) + 5 trace scenarios sequential (~75s)
    CO->>SY: syft on built image (~5s)
    Note right of SY: requires RT image; serialized by registry "requires"
    CO->>GR: grype on syft SBOM (~3s)
    CO->>SE: semgrep --metrics=off (~8s)
    CO->>GL: gitleaks on repo + .git history (~4s)
    CO->>LIGHT: ConventionProbe, SkillsIndex, etc. (~2s aggregate)
    CO->>B2: read sibling freshness; construct IndexFreshness per index
    CO->>SR: redact_secrets — replaces any AKIA... with <REDACTED:fp=…>
    SR->>WR: persist (atomic .tmp → os.replace)
    WR-->>U: exit 0 (~110-140s; meets <=180s p95 cold target)
```

#### Scenario 2: Stale-SCIP fixture catches in CI (the load-bearing exit criterion)

```mermaid
sequenceDiagram
    participant CI as GitHub Actions
    participant FX as tests/fixtures/portfolio/stale-scip/
    participant CLI as codegenie gather
    participant SCIP as SCIPIndexProbe
    participant B2 as IndexHealthProbe
    participant T as test_stale_scip_fixture.py

    CI->>FX: checkout fixture (HEAD has moved; cached SCIP from prior commit)
    CI->>CLI: codegenie gather $fixture
    CLI->>SCIP: cache lookup — HIT against prior commit's index
    Note right of SCIP: cache HIT writes slice with<br/>last_indexed_commit = <prior>
    CLI->>B2: runs_last; reads SCIP slice
    B2->>B2: last_indexed_commit != current HEAD ⇒<br/>IndexFreshness.Stale(reason=CommitsBehind(n>=1, last_indexed=<prior>))
    CLI-->>T: ProbeOutput emitted; CONTEXT_REPORT.md printed
    T->>T: assert isinstance(slice.freshness, Stale)
    T->>T: assert isinstance(slice.freshness.reason, CommitsBehind)
    T->>T: assert slice.freshness.reason.n >= 1
    T-->>CI: PASS — Phase 2 exit gate cleared
    Note over CI: If B2 fails to construct Stale, test FAILS and Phase 2 build fails.
```

#### Scenario 3: Hostile YAML in a SKILL.md (adversarial)

```mermaid
sequenceDiagram
    participant SK as SkillsLoader
    participant OS as os.open(O_NOFOLLOW)
    participant YAML as parsers.safe_yaml.load
    participant CR as Coordinator
    participant CLI as CLI summary

    SK->>OS: open(~/.codegenie/skills/x/SKILL.md, O_NOFOLLOW|O_NOCTTY)
    alt symlink detected
        OS-->>SK: ELOOP
        SK->>SK: SkillsLoadError(reason="symlink_refused")
        SK-->>CR: load_all() returns Result.Err on this skill;<br/>other skills load
        CR-->>CLI: print loud warning "skill x refused (symlink)"
    else !!python/object payload
        OS-->>SK: fd ok
        SK->>YAML: safe_yaml.load(fd, size_cap, depth_cap)
        YAML-->>SK: yaml.YAMLError (unknown tag)
        SK->>SK: SkillsLoadError(reason="unsafe_yaml")
        SK-->>CR: load_all() returns Result.Err on this skill;<br/>other skills load
        CR-->>CLI: print loud warning "skill x refused (unsafe yaml)"
    end
```

#### Scenario 4: Secret in `.git/` history found by gitleaks

```mermaid
sequenceDiagram
    participant GL as GitleaksProbe
    participant SR as SecretRedactor
    participant WR as Writer + Cache
    participant AUD as Audit anchor

    GL->>GL: run_external_cli("gitleaks", ["detect", "--source", ".", "--report-format=json", "--no-banner"])
    GL-->>SR: ProbeOutput.schema_slice contains {finding: {match: "AKIAIOSFODNN7EXAMPLE", file: ".git/refs/...", line: 42}}
    SR->>SR: pattern AKIA[0-9A-Z]{16} matches; replace with <REDACTED:fingerprint=BLAKE3_8>
    SR->>SR: in-memory SecretFinding(probe="gitleaks", fingerprint, pattern="aws_access_key", file=".git/...", line=42) — NOT persisted
    SR-->>WR: redacted slice
    WR->>WR: write raw/gitleaks-findings.json (redacted)
    WR->>WR: write repo-context.yaml (redacted)
    WR->>AUD: per-probe Ran/CacheHit/Skipped (no plaintext)
    Note over WR,AUD: Plaintext present in ZERO persisted files.<br/>CLI summary prints fingerprint count + file:line list.
```

## Component design

### 1. `IndexHealthProbe` (B2 — the load-bearing one)

- **Purpose.** Detect and surface index staleness for every index Phase 2 produces (SCIP, runtime trace, SBOM, semgrep, conventions, skills). Silent staleness is the worst failure mode of the entire system (`production/design.md` §2.3, `CLAUDE.md`). The probe is *what makes commitment §2.3 real* in Phase 2.
- **Public interface.**
  ```python
  # src/codegenie/probes/layer_b/index_health.py
  @register_probe(runs_last=True)  # heaviness defaults to "light"
  class IndexHealthProbe(Probe):
      name: ProbeId = ProbeId("index_health")
      layer: Literal["B"] = "B"
      tier: Literal["base"] = "base"
      applies_to_tasks: list[str] = ["*"]
      applies_to_languages: list[str] = ["*"]
      requires: list[ProbeId] = []          # reads sibling OUTPUTS via the
                                            # coordinator-provided slice map,
                                            # not via topological ordering
      declared_inputs: list[str] = [".codegenie/context/raw/*.json",
                                    ".git/HEAD",
                                    "<scip-index-output>",
                                    "<image-digest-token>"]
      cache_strategy: Literal["none"] = "none"  # forbidden via mypy flag in this module
      timeout_seconds: int = 10

      async def run(self, ctx: ProbeContext) -> ProbeOutput: ...
  ```
- **Internal structure.** Reads (a) sibling probes' just-written `last_indexed_commit`, `files_indexed`, `files_in_repo`, `indexer_errors`, `last_traced_image_digest`, `built_image_digest`, `rule_pack_version`; (b) current `git rev-parse HEAD` via `run_allowlisted("git", "rev-parse", "HEAD")`. For each source, constructs an `IndexFreshness` value via a smart constructor in `codegenie.indices.freshness`. Pattern-matches on the result to derive the human-readable `confidence: "high" | "medium" | "low"` for `repo-context.yaml`. **Forbidden by per-module pre-commit hook in `src/codegenie/probes/layer_b/index_health.py`**: `os.path.getmtime`, `Path.stat().st_mtime` — mtime is not a freshness signal.
- **Dependencies.** Only `codegenie.indices.freshness`, `codegenie.exec.run_allowlisted`, and Phase 0 `Probe` ABC. No imports from sibling probe modules.
- **State.** Stateless. Reads sibling slices from the coordinator-provided context.
- **Performance envelope.** `timeout_seconds=10`. Wall-clock typically < 200 ms (O(1) string compares + git rev-parse). Memory: < 20 MB.
- **Failure behavior.** If git rev-parse fails (e.g., the analyzed repo is not a git work tree), the probe emits `IndexFreshness.Stale(reason=IndexerError(message="repo_not_a_git_workdir"))` for every index source. If a sibling slice is missing (the upstream probe failed), the probe emits `Stale(reason=IndexerError(message=f"upstream_{name}_unavailable"))`. The probe never raises an exception for an absent upstream; it produces a typed value.

### 2. `IndexFreshness` sum type (`src/codegenie/indices/freshness.py`)

- **Purpose.** One name, one module, one variant set for "is index X stale, and if so, why?" Phase 2's typed answer to commitment §2.3.
- **Public interface.**
  ```python
  # frozen, discriminated unions; smart constructor at module level
  Fresh(indexed_at: datetime)
  Stale(reason: StaleReason)
  StaleReason = CommitsBehind(n, last_indexed) | DigestMismatch(expected, actual)
              | CoverageGap(files_indexed, files_in_repo) | IndexerError(message)
  IndexFreshness = Fresh | Stale
  ```
  `__init__.py:__all__ = ["IndexFreshness", "Fresh", "Stale", "StaleReason", "CommitsBehind", "DigestMismatch", "CoverageGap", "IndexerError"]`.
- **Internal structure.** Pure Pydantic models, `extra="forbid"`, `frozen=True`, `Literal["..."]` discriminator on `kind`. Round-trips through `model_dump_json` ↔ `model_validate_json` identity-equal.
- **Dependencies.** stdlib + pydantic (Phase 0 baseline).
- **State.** None. Pure data.
- **Performance envelope.** ~1 µs per construct; trivially negligible.
- **Failure behavior.** Construction raises `ValidationError` on a bad payload (the `extra="forbid"` discipline). Caller wraps as `Result.Err` per Phase 2 new-code discipline (Phase 0/1 code is NOT retrofit).
- **Why not co-located in `probes/layer_b/index_health.py`.** The Phase-2 consumer is `src/codegenie/report/confidence_section.py`, which is intentionally outside `probes/` so a CONTEXT_REPORT render does not require pulling in the probe registry. One additional package (`indices/`) is the smallest separation that makes the consumer real. Phase 3 adapters and Phase 8 Bundle Builder will also import this without a circular-dependency risk.

### 3. `run_external_cli` (`src/codegenie/exec.py` — extends Phase 0)

- **Purpose.** Single subprocess port for Layer B/G external CLIs (`scip-typescript`, `syft`, `grype`, `semgrep`, `ast-grep`, `ripgrep`, `gitleaks`, `tree-sitter`). Wraps Phase 0 `run_allowlisted`; never duplicates it. **Layer C (`docker`, `strace`) does NOT route through this** — those go through `run_allowlisted` directly with explicit hardening flags.
- **Public interface.**
  ```python
  async def run_external_cli(
      probe_name: ProbeId,
      argv: list[str],
      *,
      cwd: Path,
      timeout_s: float,
      allowlisted_egress: frozenset[str] = frozenset(),
      max_stdout_bytes: int = 64 * 1024 * 1024,
  ) -> ProcessResult: ...
  ```
- **Internal structure.** Delegates to `run_allowlisted(argv, ...)` with three additions: (a) env strip to Phase 0 allowlist (`PATH`, `HOME`, `LANG`, `LC_ALL`, `TERM`, `CODEGENIE_*`); (b) on **Linux only**, *optional* `bubblewrap --unshare-net --ro-bind <repo> /work --bind <tmpdir> /tmp/probe` wrap when `bwrap` is on PATH (graceful no-op when missing); (c) `stdout`/`stderr` capped, tail-included in failures.
- **Dependencies.** Phase 0 `run_allowlisted`. No new third-party deps.
- **State.** None.
- **Performance envelope.** Overhead vs raw `run_allowlisted`: < 5 ms (env strip + optional bwrap fork). Bandwidth-bound by tool's stdout (cap 64 MB).
- **Failure behavior.** Non-zero exit → `ProcessResult(exit_code=N, stderr_tail=...)`. Caller (a scanner probe) wraps as `ScannerOutcome.ScannerFailed`. `bwrap` missing on Linux → single startup warning, no failure. Timeout via `asyncio.wait_for`.

### 4. `SecretRedactor` (extension of `src/codegenie/output/sanitizer.py`)

- **Purpose.** Intercept every string in every `ProbeOutput.schema_slice` before it lands in `repo-context.yaml`, raw artifacts, cache, or audit; replace anything matching a secret pattern with `<REDACTED:fingerprint=BLAKE3_8>`. **Phase 2 persists zero plaintext.**
- **Public interface.**
  ```python
  # added to codegenie/output/sanitizer.py
  def redact_secrets(slice_: dict[str, JSONValue], probe_name: ProbeId
                     ) -> tuple[dict[str, JSONValue], list[SecretFinding]]: ...
  ```
  The returned `list[SecretFinding]` is collected in-memory for the CLI summary line; it is NOT persisted to any file.
- **Internal structure.** Runs after Phase 0's field-name regex and the `JSONValue` tree walk. Patterns: AWS `AKIA[0-9A-Z]{16}`, GitHub `ghp_[A-Za-z0-9]{36}`, JWT, RSA private-key block, NPM `npm_…`, Anthropic `sk-ant-…`, plus Shannon-entropy ≥ 4.5 bits/char for `len ≥ 32` unknowns. Fingerprint = first 8 hex of BLAKE3 of the cleartext.
- **Dependencies.** `codegenie.hashing.content_hash` (Phase 0 — BLAKE3 helper).
- **State.** Stateless function. The in-memory findings list is the *caller's* state.
- **Performance envelope.** ~50 MB/s scan; for a typical merged envelope (~10 MB) ~0.2 s.
- **Failure behavior.** Mutation test: a deliberately weakened pattern (e.g., `AKIA[0-9A-Z]{15}`) must cause `tests/unit/test_secret_redactor.py::test_aws_key_mutation` to FAIL. Pattern failure is a build failure.

### 5. Layer G scanners — `SemgrepProbe`, `SyftProbe`, `GrypeProbe`, `GitleaksProbe`

- **Purpose.** Run third-party security/SBOM scanners; parse JSON output into typed `ProbeOutput.schema_slice` via Pydantic smart constructors.
- **Public interface.** Each is a `Probe` subclass `@register_probe(heaviness="medium")` (with `runs_last=False`, default). Slices follow `localv2.md` §5.6.
- **Internal structure.** One file per scanner, ≤ 200 LOC each, no shared `ScannerRunner` abstraction. Common pattern: (a) check tool availability via Phase 0 `tool_cache`; (b) invoke via `run_external_cli` with explicit argv (no shell, `--metrics=off` for `semgrep`); (c) parse stdout JSON via Pydantic; (d) return `ProbeOutput`. Outcome is a discriminated union `ScannerOutcome = ScannerRan | ScannerSkipped | ScannerFailed`.
- **Dependencies.** `run_external_cli`, Pydantic.
- **State.** None.
- **Performance envelope.** Per-probe `timeout_seconds`: semgrep 60s, syft 30s, grype 30s, gitleaks 30s. Memory dominated by the scanner subprocess (semgrep ~200 MB, others < 100 MB).
- **Failure behavior.** Tool missing → `ScannerOutcome.ScannerSkipped(reason="tool_missing")` + `confidence="low"`. Bad JSON → `ScannerFailed(reason="invalid_json", stderr_tail=…)`. All findings flow through `SecretRedactor` at the writer chokepoint.

### 6. `RuntimeTraceProbe` (C4 — multi-scenario harness)

- **Purpose.** Capture syscalls, loaded shared libraries, network endpoints, shell invocations of the analyzed-repo's container under 5 scenarios (`startup`, `smoke_test`, `healthcheck`, `shutdown`, `error_path`).
- **Public interface.** `@register_probe(heaviness="heavy")`. Reads `.codegenie/scenarios.yaml` (Pydantic-validated; defaults to 5 if absent).
- **Internal structure.** Sequential per-scenario execution (no concurrency; multiple `docker run` of the same image race resources). Per scenario: `docker build` → `docker run --network=none --cap-drop=ALL --security-opt=no-new-privileges` + `strace -f` (Linux) / typed `StraceUnavailable` (macOS). All `docker`/`strace` calls via `run_allowlisted` (Phase 2 ADR-0001 extends `ALLOWED_BINARIES`). Per-scenario timeout 120 s; aggregate 600 s. Per-scenario outcome: `ScenarioResult = TraceScenarioCompleted | TraceScenarioFailed | TraceScenarioSkipped`.
- **Cache key.** `declared_inputs` includes `Dockerfile`, `.codegenie/scenarios.yaml`, AND a **special declared-input token** `image-digest:<resolved>` (Phase-2 ADR-gated via optional `ProbeContext.image_digest_resolver: Callable[[Path], str | None] | None = None` mirroring Phase 1 ADR-0002's `parsed_manifest` precedent — the **one** ProbeContext field Phase 2 adds; the `Probe` ABC is untouched).
- **Dependencies.** `run_allowlisted`, `codegenie.indices.freshness` (emits `IndexFreshness.Stale(IndexerError("strace_unavailable"))` on macOS path).
- **State.** None.
- **Performance envelope.** Cold p50 ~90 s for 5 scenarios; warm hits cache on image-digest equality.
- **Failure behavior.** macOS deterministically emits `TraceScenarioFailed(StraceUnavailable())` per scenario (no sudo prompt). `docker build` failure → all scenarios skip with `confidence="unavailable"`.

### 7. Adapter `Protocol` definitions (`src/codegenie/adapters/protocols.py`)

- **Purpose.** Documentation as code. The four Protocols are the typed target Phase 3's first plugin must implement against.
- **Public interface.**
  ```python
  @runtime_checkable
  class DepGraphAdapter(Protocol):
      def consumers(self, pkg: str) -> list[str]: ...
      def producers(self, pkg: str) -> list[str]: ...
      def confidence(self) -> AdapterConfidence: ...

  @runtime_checkable
  class ImportGraphAdapter(Protocol):
      def reverse_lookup(self, module: str) -> list[str]: ...
      def confidence(self) -> AdapterConfidence: ...

  @runtime_checkable
  class ScipAdapter(Protocol):
      def refs(self, symbol: str) -> list[Occurrence]: ...
      def confidence(self) -> AdapterConfidence: ...

  @runtime_checkable
  class TestInventoryAdapter(Protocol):
      def tests_exercising(self, symbol: str) -> list[TestId]: ...
      def confidence(self) -> AdapterConfidence: ...
  ```
  `AdapterConfidence = Trusted | Degraded(reason: str) | Unavailable(reason: str)` lives in `codegenie/adapters/confidence.py` as a placeholder; Phase 3 may extend on first concrete adapter.
- **Internal structure.** Pure typing, ~80 LOC total, stdlib + `typing` only.
- **Dependencies.** stdlib.
- **State.** None.
- **Performance envelope.** N/A — zero runtime cost; type-only.
- **Failure behavior.** None — type definitions cannot fail at runtime. `mypy --strict` enforces conformance at type-check time when Phase 3 adapters land.

### 8. `TCCMLoader` (`src/codegenie/tccm/`)

- **Purpose.** Load and Pydantic-validate Task-Class Context Manifests (ADR-0029). Schema only; no Bundle building (Phase 8).
- **Public interface.** `TCCMLoader.load(path: Path) -> Result[TCCM, TCCMLoadError]`. `TCCM` is a Pydantic model. `DerivedQuery` is a Pydantic discriminated union over the **five** ADR-0030 primitives — no `Unknown` variant (ADR-amend on a sixth).
- **Internal structure.** `loader.py` (I/O + `safe_yaml.load`), `model.py` (`TCCM`, `DerivedQuery`), `queries.py` (the five-variant discriminated union).
- **Dependencies.** `codegenie.parsers.safe_yaml` (Phase 1 chokepoint), Pydantic.
- **State.** None.
- **Performance envelope.** < 50 ms per TCCM load (size capped by `safe_yaml`).
- **Failure behavior.** Unknown `compute:` variant → `Result.Err(TCCMLoadError(reason="unknown_query_primitive"))`. Schema violation → `Result.Err(TCCMLoadError(reason="schema", details=ValidationError.errors()))`.
- **Phase-2 consumer.** `docs/phases/02-context-gather-layers-b-g/_reference-tccm/tccm.yaml` is an illustrative manifest for an `index-health-self-check` task class. It is **documentation, not a plugin** — it does not live under `plugins/`, has no probes or subgraph, and exists only to (a) exercise every field of the `TCCM` Pydantic model and (b) give `tests/integration/tccm/test_reference_tccm_roundtrips.py` a real input.

### 9. `SkillsLoader` (`src/codegenie/skills/`)

- **Purpose.** Load and index YAML-frontmatter `SKILL.md` files from three trust tiers (`~/.codegenie/skills/`, `.codegenie/skills/`, optional `~/.codegenie/skills-org/`). Validate frontmatter; record body byte-offset only (progressive disclosure).
- **Public interface.** `SkillsLoader(search_paths: list[Path]).load_all() -> Result[list[Skill], SkillsLoadError]`. `Skill` is a Pydantic model. Constructor is pure data; first I/O is `load_all()`.
- **Internal structure.** Per `SKILL.md` file: `os.open(path, O_NOFOLLOW | O_NOCTTY)` → `os.fdopen` → pass to `codegenie.parsers.safe_yaml.load` (Phase 1 chokepoint). NO parallel YAML loader. Three-tier merge: first-tier-wins; collisions emit a `skill_shadowed` warning in the CLI summary.
- **Dependencies.** `codegenie.parsers.safe_yaml`, stdlib.
- **State.** None.
- **Performance envelope.** ~5 ms per skill; ~100 skills typical = < 1 s.
- **Failure behavior.** `O_NOFOLLOW` ELOOP → `Result.Err(SkillsLoadError(reason="symlink_refused", path))`. `safe_yaml.load` raises → wrapped as `SkillsLoadError(reason="unsafe_yaml")`. Both cases: this skill skipped; loud CLI warning; other skills load.

### 10. `ConventionsCatalogLoader` (`src/codegenie/conventions/`)

- **Purpose.** Load org convention catalog (`~/.codegenie/conventions/*.yaml`); emit typed `ConventionResult = Pass | Fail | NotApplicable` per rule.
- **Public interface.** `ConventionsCatalogLoader(search_paths).load_all() -> Result[Catalog, ConventionsError]`; `Catalog.apply(repo: RepoSnapshot) -> list[ConventionResult]`.
- **Internal structure.** Pure functions over Pydantic-modeled rules. Pattern types (`dockerfile_pattern`, `dockerfile_pattern_inverted`, `file_pattern`, `missing_file`) are themselves a Pydantic discriminated union; one `match` per pattern type with `assert_never` on the unreachable branch.
- **Dependencies.** `safe_yaml`, Pydantic.
- **State.** None.
- **Performance envelope.** < 100 ms for a typical catalog.
- **Failure behavior.** Unknown pattern type → `Result.Err(ConventionsError(reason="unknown_pattern_type"))`. OPA/Rego ships in Phase 16 (ADR-0021).

### 11. `DepGraphProbe` (B5 — kernel skeleton with strategy registry)

- **Purpose.** Build a `networkx.DiGraph` of the repo's internal package dependencies (monorepo modules + cross-references). Ecosystem-specific resolution lives in Phase 3 plugin adapters; Phase 2 stitches Phase 1's already-parsed manifests into the graph.
- **Public interface.** `@register_probe`. Slice follows `localv2.md` §5.2 B5.
- **Internal structure.** Reads Layer A's `manifests` and `build_system` slices. Dispatches via a typed registry decorator:
  ```python
  @register_dep_graph_strategy(ecosystem=PackageManager.PNPM)
  def build_pnpm(ctx, manifests) -> networkx.DiGraph: ...
  ```
  `PackageManager` is the Phase 1 ADR-0013 enum (`bun | pnpm | yarn-classic | yarn-berry | npm`) — imported, not redefined. Adding Maven (Phase 8+) is a new file + new decorator + ADR-amend on `PackageManager`.
- **Dependencies.** `networkx`, Phase 1 `PackageManager` enum.
- **State.** None.
- **Performance envelope.** O(N_manifests + N_internal_edges); typical ~200 ms on monorepo-pnpm fixture.
- **Failure behavior.** Unknown ecosystem (no registered strategy) → typed `DepGraphProbeOutput(confidence="low", reason="no_strategy_for_ecosystem")`.

### 12. `TreeSitterImportGraphProbe` (B3 — kernel skeleton)

- **Purpose.** Extract file-level import edges using `tree-sitter` grammars; emit `networkx.DiGraph`-serializable JSON to `raw/import-graph.json`. Forward-only adjacency in Phase 2; reverse projection is a Phase 3 adapter concern.
- **Public interface.** `@register_probe(heaviness="medium")`. Slice follows `localv2.md` §5.2 B3.
- **Internal structure.** `py-tree-sitter` bindings (the **one** C-extension dep Phase 2 accepts via Phase 2 ADR-0002 amending Phase 1 ADR-0009). **No internal `ThreadPoolExecutor`** — the probe is one slot under the Phase 0 single semaphore; hidden parallelism lies to the coordinator's budget. Grammar `.so`/`.dylib` BLAKE3-pinned in `tools/grammars.lock`; load-time mismatch is `GrammarLoadRefused`. In-process load (not a sidecar subprocess — the grammar pin is the supply-chain defense).
- **Dependencies.** `py-tree-sitter`, grammar packs (vendored).
- **State.** None.
- **Performance envelope.** ~5 ms/file × 2k files ≈ 10 s sequential cold.
- **Failure behavior.** Grammar pin mismatch → `GrammarLoadRefused`; probe slice marked `confidence="low"`; no grammar code executes.

### Component summary table

| # | Component | Location | Owner ADR |
|---|---|---|---|
| 1 | `IndexHealthProbe` | `src/codegenie/probes/layer_b/index_health.py` | 02-ADR-0006 |
| 2 | `IndexFreshness` | `src/codegenie/indices/freshness.py` | 02-ADR-0006 |
| 3 | `run_external_cli` | `src/codegenie/exec.py` (extends Phase 0) | 02-ADR-0001 |
| 4 | `SecretRedactor` | `src/codegenie/output/sanitizer.py` (extends Phase 0) | 02-ADR-0005 |
| 5 | Layer G scanners | `src/codegenie/probes/layer_g/{semgrep,syft,grype,gitleaks}.py` | 02-ADR-0001 |
| 6 | `RuntimeTraceProbe` | `src/codegenie/probes/layer_c/runtime_trace.py` | 02-ADR-0001, 02-ADR-0004 |
| 7 | Adapter `Protocol`s | `src/codegenie/adapters/protocols.py` | 02-ADR-0007 |
| 8 | `TCCMLoader` | `src/codegenie/tccm/` | 02-ADR-0007 |
| 9 | `SkillsLoader` | `src/codegenie/skills/` | (Phase 1 ADR-0006 — safe_yaml chokepoint preserved) |
| 10 | `ConventionsCatalogLoader` | `src/codegenie/conventions/` | — |
| 11 | `DepGraphProbe` + strategy registry | `src/codegenie/depgraph/`, `probes/layer_b/dep_graph.py` | — |
| 12 | `TreeSitterImportGraphProbe` | `src/codegenie/probes/layer_b/tree_sitter_import_graph.py` | 02-ADR-0002 |

## Data model

Annotation key: **[contract]** = visible to Phase 3+ consumers; **[internal]** = Phase 2 implementation detail.

```python
# ---------- [contract] codegenie/indices/freshness.py ----------
class CommitsBehind(BaseModel):              # frozen, extra="forbid"
    kind: Literal["commits_behind"] = "commits_behind"
    n: int
    last_indexed: str  # commit sha at the I/O boundary; raw str by design

class DigestMismatch(BaseModel):             # frozen, extra="forbid"
    kind: Literal["digest_mismatch"] = "digest_mismatch"
    expected: str
    actual: str

class CoverageGap(BaseModel):                # frozen, extra="forbid"
    kind: Literal["coverage_gap"] = "coverage_gap"
    files_indexed: int
    files_in_repo: int

class IndexerError(BaseModel):               # frozen, extra="forbid"
    kind: Literal["indexer_error"] = "indexer_error"
    message: str

StaleReason = Annotated[Union[CommitsBehind, DigestMismatch, CoverageGap, IndexerError],
                        Field(discriminator="kind")]

class Fresh(BaseModel):                       # frozen, extra="forbid"
    kind: Literal["fresh"] = "fresh"
    indexed_at: datetime

class Stale(BaseModel):                       # frozen, extra="forbid"
    kind: Literal["stale"] = "stale"
    reason: StaleReason

IndexFreshness = Annotated[Union[Fresh, Stale], Field(discriminator="kind")]

# ---------- [contract] codegenie/adapters/protocols.py ----------
@runtime_checkable
class DepGraphAdapter(Protocol): ...     # see §Component 7
@runtime_checkable
class ImportGraphAdapter(Protocol): ...
@runtime_checkable
class ScipAdapter(Protocol): ...
@runtime_checkable
class TestInventoryAdapter(Protocol): ...

# ---------- [contract] codegenie/adapters/confidence.py ----------
class Trusted(BaseModel): kind: Literal["trusted"]; ...
class Degraded(BaseModel): kind: Literal["degraded"]; reason: str
class Unavailable(BaseModel): kind: Literal["unavailable"]; reason: str
AdapterConfidence = Annotated[Union[Trusted, Degraded, Unavailable], Field(discriminator="kind")]
# Phase 3 plugin may extend; revise on first adapter.

# ---------- [contract] codegenie/tccm/model.py ----------
class TCCM(BaseModel):                        # frozen, extra="forbid"
    schema_version: Literal["1"]
    task_class: TaskClassId
    required_probes: list[ProbeId]
    required_skills: list[SkillId]
    derived_queries: list[DerivedQuery]
    confidence_floor: AdapterConfidence

# ---------- [contract] codegenie/tccm/queries.py ----------
# 5 primitives per ADR-0030; no Unknown variant; ADR-amend on a 6th.
DerivedQuery = ConsumersOf | ProducersOf | ReverseLookup | RefsTo | TestsExercising

# ---------- [contract] codegenie/skills/model.py ----------
class Skill(BaseModel):                       # frozen, extra="forbid"
    id: SkillId
    applies_to_tasks: list[str]
    applies_to_languages: list[str]
    body_offset: int                          # progressive disclosure
    body_size: int
    body_blake3: str

# ---------- [internal] codegenie/probes/layer_g/scanner_outcome.py ----------
class ScannerRan(BaseModel):
    kind: Literal["ran"] = "ran"; findings: list[Finding]
class ScannerSkipped(BaseModel):
    kind: Literal["skipped"] = "skipped"; reason: str
class ScannerFailed(BaseModel):
    kind: Literal["failed"] = "failed"; exit_code: int; stderr_tail: str
ScannerOutcome = Annotated[Union[ScannerRan, ScannerSkipped, ScannerFailed],
                           Field(discriminator="kind")]

# ---------- [internal] codegenie/probes/layer_c/scenario_result.py ----------
TraceScenarioCompleted | TraceScenarioFailed | TraceScenarioSkipped

# ---------- [internal] codegenie/conventions/model.py ----------
ConventionResult = Pass | Fail | NotApplicable

# ---------- [contract — additive] codegenie/probes/base.py (Phase 0 + 1 frozen) ----------
# ONLY new field in ProbeContext (Phase-2-ADR-gated):
@dataclass(frozen=True)
class ProbeContext:
    # ... Phase 0 fields unchanged ...
    parsed_manifest: Callable[[], dict | None] | None = None      # Phase 1
    image_digest_resolver: Callable[[Path], str | None] | None = None  # Phase 2 (NEW)
```

The `Probe` ABC itself is **not edited**. The Phase 0 contract-freeze snapshot test (`tests/unit/test_probe_contract.py`) catches any drift.

## Control flow

**Happy path** (warm gather, incremental `.ts` change, image unchanged):

1. CLI tool-readiness checks `$PATH` for all Layer B/G binaries; missing-mandatory → exit with install hint; missing-optional → flag for `confidence="low"` slice.
2. `RepoSnapshot` built (Phase 0). `parsed_manifest` memo seeded (Phase 1). `image_digest_resolver` callable bound at coordinator setup.
3. Coordinator reads registry, sorts by `heaviness` (heavy first), reserves the last slot for `runs_last=True` probes.
4. Probes dispatch under the single `Semaphore(min(cpu_count(), 8))`. `SCIPIndexProbe` MISS → re-index. `RuntimeTraceProbe` HIT (image-digest token in `declared_inputs` matches). Layer G scanners MISS on changed files.
5. All sibling probes finish. `IndexHealthProbe` runs last, reads sibling slices via the coordinator-provided slice map, constructs `IndexFreshness` per index source.
6. Merged envelope flows through `OutputSanitizer.scrub` → `SecretRedactor.redact_secrets` → writer. Atomic `.tmp` → `os.replace`.
7. `CONTEXT_REPORT.md` rendered alongside via `confidence_section.py`; pattern-matches every `IndexFreshness` value with `assert_never`.
8. Audit anchor (`runs/<utc-iso>-<short>.json`) records per-probe `Ran/CacheHit/Skipped` (Phase 0 unchanged).
9. Exit 0.

**Decision points:**

- **Step 1, tool missing.** Mandatory → `MissingToolError` typed, CLI exits 4 with install command from `localv2.md §6`. Optional → continue; probe emits `confidence="low"`.
- **Step 4, probe times out.** `asyncio.wait_for` cancels; probe slice has `confidence="low"` and `errors=[…]`; coordinator continues (Phase 0 isolation).
- **Step 5, sibling slice missing.** `IndexHealthProbe` emits `Stale(reason=IndexerError(message=f"upstream_{name}_unavailable"))`.
- **Step 6, secret pattern matches.** `SecretRedactor` replaces inline; in-memory `SecretFinding` collected; CLI summary prints count + file:line list at gather end.
- **Step 8, audit-anchor write fails.** Exit 6 (Phase 0 audit-failure exit code); the gather is invalidated even if all probes succeeded.

## Harness engineering

- **Logging.** Phase 0 `codegenie/logging.py` unchanged. Phase 2 probes use the existing `structlog`-style logger; per-probe lifecycle events (`dispatch`, `finish`, `cache_hit`) are already emitted. Phase 2 adds **one** log field at the writer: `secrets_redacted_count` (int), so a 0-count run is grep-able.
- **Tracing.** No OpenTelemetry yet (Phase 9 ships it). Phase 2 emits per-probe `gathered_at`, `last_indexed_commit`, `built_image_digest`, `rule_pack_version` *into the slice itself* — this slice metadata is what Phase 9 will project into the canonical event log.
- **Idempotence.** Every probe is idempotent given the same `declared_inputs`. `IndexHealthProbe` is `cache_strategy="none"` because it observes a *moving* fact (HEAD vs. last_indexed) — caching that is the same bug as caching `Date.now()`. The deterministic-gather commitment (§2.6, ADR-0006) requires `(same repo state) → (same RepoContext)` byte-for-byte (modulo `generated_at` timestamp).
- **Determinism vs. probabilism.** Phase 2 is deterministic end-to-end (commitment §2.1, ADR-0005). The `gather` extras Phase 0 `fence` job asserts is unchanged: no `anthropic`, `openai`, `langgraph`, `httpx`, `requests`, `socket` import under `src/codegenie/`. The one new C-extension dep — `py-tree-sitter` — has a Phase 2 ADR (02-ADR-0002) amending Phase 1 ADR-0009 with the named trigger.
- **Replay.** `RepoContext` re-derives from the analyzed-repo + `.codegenie/cache/` blobs. There is no event log to replay (deferred to Phase 9 per ADR-0034). The Phase 0 audit anchor lets an operator reproduce a given gather invocation's per-probe outcomes.
- **Configuration.** `.codegenie/config.yaml` (Phase 0) + `.codegenie/scenarios.yaml` (Phase 2; RuntimeTraceProbe — Pydantic-validated; falls back to 5 default scenarios). `~/.codegenie/config.yaml` for user defaults (skills paths, conventions paths). `ExternalDocsProbe` allowlist (`external_docs:` key) lands when the first real user opts in.

## Agentic best practices

Phase 2 has **no LLM call** (commitment §2.1) — but it lands the surfaces Phase 4+ LLM consumers will depend on.

- **Typed state.** Every state machine is a Pydantic discriminated union: `IndexFreshness`, `ScannerOutcome`, `ScenarioResult`, `ConventionResult`, `AdapterConfidence`. ADR-0033 §3 (make-illegal-states-unrepresentable) is the binding discipline; `mypy --warn-unreachable` enforces exhaustiveness on the consumer (`confidence_section.py`) from day 1.
- **Tool-use safety.** All external CLI invocations route through `run_external_cli` (Layer B/G) or `run_allowlisted` directly (Layer C). `ALLOWED_BINARIES` is the auditable list (Phase 2 ADR-0001 amends). `--metrics=off` on `semgrep` to refuse phone-home. `gitleaks` `--no-banner` for deterministic stdout.
- **Prompt template structure.** N/A — no prompts in Phase 2. Phase 4 will consume the `SecretRedactor`'s chokepoint guarantee (zero plaintext in any artifact an LLM might see).
- **Confidence handling.** `IndexFreshness` IS the confidence handling. The probe never says "safe" or "unsafe"; it says `Fresh(indexed_at=…)` or `Stale(reason=CommitsBehind(n=17, last_indexed=<sha>))`. The Planner (Phase 4+) decides.
- **Error escalation.** Every failure is a typed value, not a thrown exception (Rule 12 — fail loud, structural). Exceptions are reserved for bugs, OOM, signals.

## Design patterns applied

| Decision | Pattern | Why here | Pattern NOT applied (and why) |
|---|---|---|---|
| `IndexFreshness = Fresh \| Stale(reason)` + every state machine as discriminated union | Sum type / Make-illegal-states-unrepresentable (ADR-0033 §3–4) | Silent "stale-without-reason" is the load-bearing failure mode B2 exists to prevent; `mypy --warn-unreachable` enforces exhaustiveness | Null Object — loses the *reason*; `Optional[str]` — stringly-typed |
| `run_external_cli` for B/G; direct `run_allowlisted("docker", …)` for C | Command pattern at value-typed argv | One auditable chokepoint per family; "every external CLI call is `grep run_external_cli`" works | Hexagonal Port/Adapter — one Adapter is a function; "Port" labeling is ceremony |
| Adapter `Protocol` classes in `codegenie/adapters/protocols.py` (zero implementations) | Structural subtyping (PEP 544) | Plugins are external (ADR-0031); inheriting from our ABC would couple plugin authors to our class hierarchy | Abstract Factory — too heavyweight for "the class named in `plugin.yaml`" |
| `@register_probe(heaviness=…, runs_last=…)` decorator kwargs | Registry + decorator-data over ABC fields | Scheduling data is coordinator-side; matches Phase 0's existing decorator-registry primitive | `cost_tier: Literal[0..3]` on the `Probe` ABC — ABC churn for a scheduling optimization |
| `@register_dep_graph_strategy(ecosystem: PackageManager)` | Open/Closed at the file boundary | Adding Maven (Phase 8+) is a new file + decorator, never an edit to `DepGraphProbe` | String-keyed dict — Phase 3 deferral was the exact ADR-0033 violation the critic flagged |
| `SecretRedactor` as a pass in the existing sanitizer pipeline | Chain of responsibility / pipeline composition | Single chokepoint discipline survives; one pass added by composition | Capability pattern across LLM boundary — LLM never holds the token; authorization with a fancier name |
| One file per Layer G scanner; no shared `ScannerRunner` abstraction | SRP + Rule of Three | Four scanners with four genuinely different I/O shapes; ~60 LOC saved by sharing isn't worth the speculative coupling | Template Method / Generic ScannerRunner |
| Reference TCCM under `docs/_reference-tccm/`, not `plugins/` | Documentation as code, deliberately outside the plugin namespace | Phase 3 owns the plugin namespace; Phase 2 ships the schema with one consumer (the integration test) | Synthetic plugin fixture under `tests/fixtures/plugins/` — implies pluggability Phase 3 owns |

### Patterns considered and deliberately rejected

1. **Plugin Loader in Phase 2.** Roadmap and ADR-0031 §Consequences §1 assign the loader to Phase 3 *alongside* the first plugin ("the first plugin doubles as the proof the loader works"). Pulling forward hollows Phase 3's exit.
2. **`cost_tier: Literal[0,1,2,3]` on the `Probe` ABC.** Coordinator scheduling concern smuggled onto the contract. Registry-side annotation does the same job at the right layer.
3. **`ProbeContext.capabilities: ProbeCapabilities` discriminated union.** Every Phase 0/1 probe would need to `match` exhaustively to stay type-clean — coordinated every-file edit dressed as "additive."
4. **Cryptographic anchoring + audit-log hash chain on B2.** Defends against an attacker who can write to `.codegenie/cache/` — which per Phase 0 ADR-0011 requires having already compromised the host. Ceremony against a non-threat.
5. **Per-repo encryption key for secret findings under `~/.codegenie/keys/`.** Key + ciphertext in the same trust tier ($HOME). Structural fix: don't persist plaintext.
6. **`pytest-xdist` for the portfolio test lane.** Phase 0 vetoed it 10/4. Portfolio fits serial CI ≤ 6 minutes.
7. **`AdapterConfidence` as the type of every probe's freshness output.** Conflates ADR-0033's prescription for *adapter outputs* (Phase 3) with Phase 2's *probe outputs*.
8. **Event stream (`.codegenie/events/`) with hash-chained JSONL.** ADR-0034 §Consequences §1 defers canonical event log to Phase 9 (or 13).
9. **`scip-python` parser + msgpack-on-disk projection.** Adapter consumption shape is a Phase 3 concern; binary on-disk format would force Phase 3 adapters to agree on it.
10. **Out-of-process `_grammar_runner` subprocess for tree-sitter.** Grammar pin already guards supply-chain; in-process load is the boring shape.
11. **`SkillsLoader` auto-discovery via env vars.** Explicit search paths at construction; loader doesn't peek at env or import paths.
12. **`gitpython` dep.** `git` is already in `ALLOWED_BINARIES`; we shell out via `run_allowlisted`.

### Anti-patterns avoided (from the toolkit's flag-on-sight list)

- **Premature pluggability.** No Plugin Loader; no universal-fallback plugin; no `NullAdapter` fixtures. Adapter Protocols ship as documentation; first real consumer (Phase 3) is the proof.
- **Pattern soup.** Three explicit pattern decisions (sum types, decorator-registry, single-chokepoint composition). No `FooFactory`, no `BarStrategy`, no `BazBuilder`.
- **Inheritance for code reuse.** Every Phase 2 class inherits *only* `Probe` (the contract) or `BaseModel` (Pydantic). No "shared scanner base class" because the scanners aren't actually share-able.
- **Stringly-typed identifiers.** `ProbeId`, `TaskClassId`, `SkillId`, `PackageManager` are typed; `ecosystem: PackageManager` is the registry key, not `ecosystem: str`.
- **Untyped `dict[str, Any]`.** The one inherited surface (`ProbeOutput.schema_slice: dict[str, JSONValue]`) is bounded by Phase 0's recursive `JSONValue`. Phase 2 doesn't extend it.
- **Boolean flags on public methods.** `register_probe(heaviness=…, runs_last=…)` uses `Literal["light","medium","heavy"]` and a typed bool with one purpose; no `force=`, `strict=`, `dry_run=` proliferation.
- **Tag-and-dispatch without a tagged union.** All `kind`-style discriminators are Pydantic discriminated unions (`Field(discriminator="kind")`).
- **Capability passed through ten frames.** No `capability_token` threaded through `run`; `run_external_cli` is the registry the toolkit prescribed.
- **Side effects in constructors.** Every loader (`SkillsLoader`, `TCCMLoader`, `ConventionsCatalogLoader`) is pure data at `__init__`; first I/O is `load_all()` / `load()`.
- **Hexagonal sandbox that smuggles subprocess into the core.** `run_external_cli` is honestly a Command-pattern wrapper; we don't claim what we didn't build.
- **Schema before consumer.** Every typed sum has at least one Phase 2 consumer: `IndexFreshness` ← `confidence_section.py`; `TCCM` ← reference-TCCM integration test; `ScannerOutcome` ← every Layer G probe's caller; Adapter `Protocol`s ← Phase 3 exit contract (documented exception).
- **`model_construct()` bypass.** Phase 0's `forbidden-patterns` pre-commit (extended in Phase 2) bans `model_construct` under `src/codegenie/{indices,tccm,skills,conventions,adapters,depgraph}/**`.

## Edge cases

| # | Edge case | Probe / Component | Detection | Containment | Source |
|---|---|---|---|---|---|
| 1 | External CLI not on `$PATH` | Tool-readiness check at startup | `MissingToolError` typed; CLI exits with install hint | Mandatory → exit 4; optional → `confidence="low"` slice; build continues | final-design [B] |
| 2 | External CLI exits non-zero | `run_external_cli` | `ProcessResult(exit_code != 0, stderr_tail)` | `ScannerOutcome.ScannerFailed`; coordinator continues per Phase 0 isolation | final-design |
| 3 | External CLI emits invalid JSON | Layer G scanner Pydantic smart constructor | `Result.Err(ParseError(stdout_tail))` | Slice `confidence="low"`; stdout/stderr tail in audit | [B] |
| 4 | `scip-typescript` timeout on huge monorepo | `asyncio.wait_for(timeout_seconds=300)` | `IndexFreshness.Stale(reason=IndexerError(message="timeout"))` | Phase 3 adapter falls back to tree-sitter per ADR-0032 declared fallback | final-design |
| 5 | `docker build` fails (adversarial Dockerfile) | Subprocess exit code | C-tier probes `confidence="unavailable"`; gather completes degraded | Operator fixes Dockerfile; re-runs | [P] |
| 6 | `strace` exec fails (macOS) | `run_external_cli` raises typed `StraceUnavailable` | `TraceScenarioFailed(StraceUnavailable())` per scenario; B2 emits `Stale(IndexerError("strace_unavailable"))` for runtime_trace | macOS path is permanent; CI is Linux-canonical | [P+B+S] |
| 7 | `gitleaks` finds AWS key in `.git/` history | `gitleaks` parses; `SecretRedactor` matches `AKIA…` | Plaintext replaced with `<REDACTED:fp=…>` in `repo-context.yaml`, raw artifact, cache. **Plaintext in zero persisted files** | Reviewer runs `gitleaks` manually at PR time for cleartext | [S, scaled] |
| 8 | Hostile YAML in Skill (`!!python/object`, billion-laughs) | `safe_yaml.load` (Phase 1 chokepoint) | `SkillsLoadError(reason="unsafe_yaml")`; this skill skipped, others load | Loud CLI warning; operator investigates supply chain | [B+S] |
| 9 | Symlink `~/.codegenie/skills/x/SKILL.md → /etc/passwd` | `os.open(O_NOFOLLOW)` → ELOOP | `SkillsLoadError(reason="symlink_refused")`; loud CLI warning | Operator investigates planted symlinks | [S] |
| 10 | `tree-sitter` grammar BLAKE3 mismatch | Pre-load hash check against `tools/grammars.lock` | `GrammarLoadRefused`; probe slice `confidence="low"`; no grammar code executes | Operator deliberately bumps pin (PR-reviewable) or investigates supply chain | [S] |
| 11 | Stale-SCIP fixture in CI (deliberate seed) | `IndexHealthProbe` reads `last_indexed_commit` mismatch | `IndexFreshness.Stale(reason=CommitsBehind(n>=1, last_indexed=<prior>))`; `test_stale_scip_fixture.py` asserts exact typed outcome | **Roadmap exit criterion** | final-design |
| 12 | Concurrent gather race against same repo | Phase 0 advisory lock at `.codegenie/cache/.lock` | Second invocation waits or fails fast (config) | — | [P] |
| 13 | Hostile semgrep/grype/gitleaks JSON (truncated, oversized, deeply nested) | Pydantic smart constructor + `JSONValue` depth cap | `ScannerFailed(reason="invalid_json", stderr_tail)`; sanitizer rejects oversized payloads upstream | Operator inspects audit | [B+S] |
| 14 | Image-digest resolver returns `None` (no built image) | `ProbeContext.image_digest_resolver` callable | C-tier probes skip with `confidence="unavailable"`; cache key falls back to declared inputs without the token | Operator builds image; re-runs | final-design |
| 15 | `cpu_count()` returns 2 (GitHub-hosted runner) | `Semaphore(min(2, 8))` | All probes serialize through 2 slots; heavy probes still sort-first via `heaviness` annotation | No starvation explosion (vs. per-tier semaphores from [P]) | critic [P] hidden-assumption #2 |
| 16 | Skill collision across three trust tiers | `SkillsLoader` three-tier merge | First-tier-wins + loud `skill_shadowed` warning in CLI summary | Per-tier signing (Sigstore) is a Phase 14 concern | [S] |

## Testing strategy

### Test pyramid

```
                 ▲
        adversarial (≥ 5 cases — including the LOAD-BEARING stale-scip)
        ─────────────
        e2e (1 — full gather against pinned Node fixture)
        ─────────────────
        integration (~12 — one per scanner + portfolio + TCCM roundtrip)
        ──────────────────────
        golden (~70 — one per probe × 5 portfolio fixtures)
        ─────────────────────────
        property (~6 — IndexFreshness round-trip, monotonicity, well-formedness)
        ──────────────────────────────
        unit (~40 — every component in §"Component design")
                 ▼
```

### Unit tests

| Test module | Asserts |
|---|---|
| `tests/unit/probes/layer_b/test_index_health_probe.py` | Per-source freshness; every `IndexFreshness` variant constructible; `cache_strategy="none"` enforced; `runs_last` annotation respected |
| `tests/unit/indices/test_freshness.py` | `IndexFreshness` round-trip (`model_dump_json` → `model_validate_json` = identity); exhaustive `match` test with `assert_never` (missing case is a `mypy --warn-unreachable` build error) |
| `tests/unit/probes/layer_b/test_scip_index.py` | `scip-typescript` invocation; output binary present; cache-key sensitivity to tool-version + Merkle of `.ts` files; timeout → `IndexerError` |
| `tests/unit/probes/layer_c/test_runtime_trace.py` | Per-scenario sequential execution; per-scenario timeout; macOS `StraceUnavailable` deterministic path |
| `tests/unit/probes/layer_b/test_dep_graph.py` | `@register_dep_graph_strategy` registry works; one strategy per `PackageManager` variant; monorepo graph correct |
| `tests/unit/probes/layer_b/test_tree_sitter_import_graph.py` | Per-file extraction; no internal thread pool; grammar pin verified at load |
| `tests/unit/probes/layer_g/test_{semgrep,syft,grype,gitleaks}.py` | Pydantic smart constructor; subprocess mocked via `pytest-subprocess`; `ScannerOutcome` variants |
| `tests/unit/skills/test_loader.py` | Frontmatter parsing; `O_NOFOLLOW` symlink refusal; three-tier merge + shadowing warning; body byte-offset not loaded into memory |
| `tests/unit/conventions/test_catalog.py` | One test per pattern type; `NotApplicable` path; `assert_never` on unknown |
| `tests/unit/tccm/test_loader.py` | Loads reference TCCM from `docs/_reference-tccm/`; unknown `compute:` variant fails fast; five `DerivedQuery` variants round-trip |
| `tests/unit/adapters/test_protocols.py` | Protocol structural typing (no-op stub passes `isinstance` via `runtime_checkable`); `AdapterConfidence` variants construct |
| `tests/unit/output/test_secret_redactor.py` | Each pattern class matches; entropy threshold catches generic high-entropy strings; **mutation test**: weakened regex causes a test to fail |
| `tests/unit/exec/test_run_external_cli.py` | Env strip; allowlisted-egress respected; stdout cap; `bubblewrap` graceful no-op on macOS |

### Property tests (`tests/property/`)

- `test_index_freshness_roundtrip.py` — Hypothesis: any `IndexFreshness` round-trips through `model_dump_json` / `model_validate_json` identity-equal.
- `test_skills_loader_monotone.py` — `SkillsLoader.find_applicable(evidence_keys)` is monotone in `evidence_keys` (adding a key never removes a match).
- `test_trace_coverage_well_formed.py` — for any combination of `ScenarioResult` variants, `TraceCoverage` is well-formed.
- `test_scanner_outcome_roundtrip.py` — `ScannerOutcome` ↔ JSON identity.
- `test_dep_graph_strategy_dispatch.py` — registry dispatch is total over `PackageManager` enum members.

### Golden files (`tests/golden/probes/<probe>/<fixture>.json`)

One golden per probe per portfolio fixture. CI diffs live output vs. committed expected. `pytest --update-golden` regenerates. Updating a golden is a deliberate PR step (the diff must be reviewed). Five-fixture portfolio:

| Fixture | Exercises |
|---|---|
| `minimal-ts` | Smallest happy path; smoke for every probe |
| `native-modules` | C-extension manifest edge cases (e.g., `node-gyp`) |
| `monorepo-pnpm` | `DepGraphProbe` cross-package edges; pnpm workspace |
| `distroless-target` | Layer C runtime trace against an already-distroless base image (Phase 7 forward-looking) |
| `stale-scip` | **LOAD-BEARING** — pre-populated SCIP from a prior commit; HEAD has moved |

### Fixture portfolio engineering

- Fixtures are tiny (≤ 200 files each). Generation scripts under `tests/fixtures/portfolio/<name>/regenerate.sh` are reviewed-as-code.
- `.codegenie/cache/` is **NOT committed** to fixtures (regenerated each CI run; transparent diff). Open question §6 in the synthesis names the alternative if CI walltime regresses past 8 min.
- `stale-scip` has a `README.md` documenting the regeneration policy: the structural assertion is `CommitsBehind.n >= 1`, tool-version-agnostic.

### CI gates

1. **`fence` job (Phase 0).** Asserts no `anthropic`/`openai`/`langgraph` imports under `src/codegenie/`. Unchanged.
2. **`contract-freeze` job (Phase 0).** `tests/unit/test_probe_contract.py` snapshots the `Probe` ABC against `tests/snapshots/probe_contract.v1.json`. Unchanged — Phase 2 makes no edit.
3. **`unit` job.** Pytest serial. ≤ 90 s.
4. **`integration` job.** Real-tool invocations against tiny fixtures. CI-gated on tool presence; skip-with-loud-warning if missing.
5. **`portfolio` job.** Five-fixture sweep + golden diff. Serial (no xdist). ≤ 6 min budget.
6. **`adv-phase02` job.** **LOAD-BEARING.** Includes `test_stale_scip_fixture.py`, `test_hostile_skills_yaml.py`, `test_secret_in_source.py`, `test_image_digest_drift.py`, `test_concurrent_gather_race.py`. Build FAILS on any.
7. **`mypy` job.** `mypy --strict` repo-wide; `--warn-unreachable` per-module on `codegenie.{indices, probes/index_health.py, report, adapters, tccm}/**` via `pyproject.toml` overrides.
8. **`bench` job (advisory, not gating).** `tests/bench/bench_portfolio_walltime.py`. Flags ≥ 50% regression on cold/warm p50; comment-on-PR, no block.

### Performance regression tests

- `bench_portfolio_walltime.py` — five-fixture cold + warm p50 captured per run; baseline JSON committed in `tests/bench/baselines/`. ≥ 50% delta = comment-on-PR (per Phase 0 §3.2 advisory discipline).
- `bench_index_health_overhead.py` — `IndexHealthProbe` walltime must be < 5% of total cold gather on `minimal-ts`. ≥ 10% = comment-on-PR.

### Adversarial tests (`tests/adv/phase02/`) — the load-bearing exit

| Test | What it proves |
|---|---|
| **`test_stale_scip_fixture.py`** | **Roadmap exit criterion.** `IndexHealthProbe` returns `IndexFreshness.Stale(reason=CommitsBehind(n>=1, last_indexed=<prior>))`. Build FAILS otherwise. |
| `test_hostile_skills_yaml.py` | `!!python/object`, billion-laughs, deep nesting, symlink-escape filenames. ≥ 8 cases. None executes user code. |
| `test_secret_in_source.py` | gitleaks finds seeded secret; `SecretRedactor` replaces in `repo-context.yaml` + every raw artifact + cache + audit. Plaintext in **zero** persisted files. |
| `test_image_digest_drift.py` | Mutating built image between gathers invalidates tier-C caches via the image-digest declared-input token. |
| `test_concurrent_gather_race.py` | Two concurrent gathers don't corrupt cache; Phase 0 advisory lock holds. |
| `test_adversarial_dockerfile.py` | Forkbomb / infinite-loop Dockerfile: probe times out; container `--cap-drop=ALL --network=none --no-new-privileges` contains it; coordinator continues. |

## Integration with Phase 3 (next phase)

Phase 3 is "Vuln remediation: deterministic recipe path" (roadmap line 82). It is **also** the phase that ships the Plugin Loader, the universal fallback plugin, the first concrete plugin (`plugins/vulnerability-remediation--node--npm/`), the four ADR-0032 adapter implementations, Skills, and OpenRewrite recipes — all together, as ADR-0031 §Consequences §1 prescribes.

**What Phase 3 inherits from Phase 2 on day 1, unchanged:**

| Surface | Where Phase 3 finds it | What Phase 3 does with it |
|---|---|---|
| `codegenie.adapters.protocols.DepGraphAdapter` | `src/codegenie/adapters/protocols.py` | `plugins/vulnerability-remediation--node--npm/adapters/dep_graph_npm.py` implements it |
| `codegenie.adapters.protocols.ImportGraphAdapter` | same | `adapters/import_graph_node.py` implements it (consumes `raw/import-graph.json`) |
| `codegenie.adapters.protocols.ScipAdapter` | same | `adapters/scip_node.py` implements it (consumes the SCIP binary blob — Phase 3 decides project/mmap/walk) |
| `codegenie.adapters.protocols.TestInventoryAdapter` | same | `adapters/test_inventory_node.py` implements it (consumes Phase 1 `TestInventory` slice) |
| `codegenie.adapters.confidence.AdapterConfidence` | `src/codegenie/adapters/confidence.py` | Phase 3 adapter `confidence()` returns these variants; may extend with ADR if first adapter needs more |
| `codegenie.indices.freshness.IndexFreshness` | `src/codegenie/indices/freshness.py` | Phase 3 plugin renders into bundle metadata; potentially layered over `AdapterConfidence` |
| `codegenie.tccm.TCCM` + `DerivedQuery` | `src/codegenie/tccm/` | `plugins/vulnerability-remediation--node--npm/tccm.yaml` is parsed by this loader |
| `codegenie.skills.SkillsLoader` | `src/codegenie/skills/` | Phase 3 plugin's Skills are loaded through this; three-tier merge already works |
| `codegenie.exec.run_external_cli` | `src/codegenie/exec.py` | Phase 3's `npm`, `jq` invocations route through it (`ALLOWED_BINARIES` amended) |
| `PackageManager` enum + `@register_dep_graph_strategy` | `src/codegenie/depgraph/registry.py` | Phase 3 registers `build_npm`, `build_pnpm` etc. via new files; never edits `DepGraphProbe` |
| Layer A–G probe outputs | `.codegenie/context/repo-context.yaml` + `raw/*` | Phase 3 plugin reads these as evidence input |
| `SecretRedactor` chokepoint | Sanitizer | Phase 3 LLM-adjacent flows (still no LLM in Phase 3 — but Phase 4's RAG store builds atop Phase 3 outputs) inherit the guarantee |
| Phase 2 fixture portfolio | `tests/fixtures/portfolio/` | Phase 3 reuses `monorepo-pnpm` + `minimal-ts` as the first-recipe targets |

**Implicit guarantees Phase 3 will rely on (and we must preserve):**

1. The `Probe` ABC and `ProbeContext` are append-only. Phase 3 may add probes (npm-specific) inside the plugin; the kernel ABC is unchanged.
2. `IndexFreshness` variant set is stable. If Phase 3 needs a fifth `StaleReason`, it requires an ADR amendment to 02-ADR-0006, not a silent extension.
3. `SecretRedactor` runs before any artifact is persisted. Phase 3 cannot bypass it; the only path from `ProbeOutput` to disk is `OutputSanitizer.scrub` (Phase 0 chokepoint).
4. `run_external_cli` is the only way to add a new external CLI for B/G families. Phase 3 amends `ALLOWED_BINARIES` for `npm`, `jq`; everything else stays through `run_allowlisted` directly (`git`) or via `run_external_cli` (security scanners).
5. The image-digest declared-input token mechanism (Phase 2 ADR-0004) is reusable. Phase 3 transforms that change the analyzed image inherit the cache-correctness story.

**New artifacts Phase 2 produces that Phase 3 consumes:**

- `.codegenie/context/raw/scip-index.scip` — binary SCIP blob; Phase 3's `ScipAdapter` decides consumption shape.
- `.codegenie/context/raw/import-graph.json` — forward-only adjacency; Phase 3's `ImportGraphAdapter` decides projection.
- `.codegenie/context/raw/dep-graph.json` — `networkx`-serializable monorepo dep graph.
- `.codegenie/context/raw/syft-sbom.json` + `grype-cves.json` — Phase 3's deterministic recipe path reads these as the *vulnerability evidence*.
- `.codegenie/context/raw/runtime-trace-{scenario}.{strace,json}` — Phase 3 reads `shared_libs_loaded` and `shell_invocations_observed` for distroless feasibility checks.
- `.codegenie/context/raw/semgrep-findings.json` + `gitleaks-findings.json` — both **redacted at the writer chokepoint**.

## Path to production end state

**Capabilities now possible (not necessarily wired in until later phases):**

- A Planner reading a slice and knowing whether the slice is trustworthy (`IndexFreshness`). The Planner doesn't exist yet (Phase 8), but the typed answer it will consume does.
- A plugin author writing against ADR-0032 adapter Protocols without guessing the shape (Phase 3).
- A microVM (Phase 5) re-deriving cleartext for a secret finding without Phase 2 having persisted plaintext anywhere it could reach.
- A canonical event log (Phase 9) projecting Phase 0's audit anchor + Phase 2's per-probe slice metadata (`gathered_at`, `last_indexed_commit`, etc.) into a typed Postgres event log without schema drift.
- A cost ledger (Phase 13) attributing per-probe wall-clock and external-CLI runtime cost via the existing `Ran/CacheHit/Skipped` outcomes.

**What's still missing (deliberate, named non-goals):**

- The Plugin Loader (Phase 3).
- LLM-fallback adjudication (Phase 4).
- Sandbox + Trust-Aware gates (Phase 5).
- SHERPA state machine (Phase 6).
- The second task class — Chainguard distroless migration (Phase 7).
- Hierarchical Planner + pre-rendered hot views (Phase 8).
- Temporal envelope (Phase 9).

**Deferred ADRs this phase makes resolvable:**

- **ADR-0015 (trust-score threshold calibration).** Phase 2's `IndexFreshness` + (forthcoming Phase 3) `AdapterConfidence` are the typed inputs the calibration will consume. Phase 6.5's eval harness can now ground its calibration runs on concrete typed signals.
- **ADR-0017 (knowledge-graph backend).** Phase 2's `TCCM` loader gives the KG a typed schema target for the "what evidence does this task class need" question.
- **ADR-0021 (policy engine).** Phase 2's `ConventionsCatalogLoader` is the boring-default that decides ADR-0021's "build vs. adopt" question by example — if conventions stay this simple through Phase 7, OPA/Rego is over-engineered.
- **ADR-0023 (MCP server topology).** Phase 2's `.codegenie/context/` artifact shape is the input the Context MCP will serve in the service.

**New ADRs landing in Phase 2** (numbered under `docs/phases/02-context-gather-layers-b-g/ADRs/`):

| # | ADR | Records |
|---|---|---|
| 02-ADR-0001 | Add docker + security-CLI tools to `ALLOWED_BINARIES` | Mirrors Phase 1 ADR-0001 `node` addition |
| 02-ADR-0002 | `py-tree-sitter` grammars — Phase 2 amendment to Phase 1 ADR-0009 | Named-trigger fired: `localv2.md` §5.2 B3 requires tree-sitter |
| 02-ADR-0003 | `@register_probe(heaviness=, runs_last=)` registry annotations | Coordinator sort-order edit; preserves single Semaphore + ABC contract |
| 02-ADR-0004 | Image digest as declared-input token | Extends `localv2.md` §4 special-token mechanism; introduces optional `ProbeContext.image_digest_resolver` |
| 02-ADR-0005 | Secret findings — no plaintext persistence | Phase 5 microVM is the named cleartext escalation door |
| 02-ADR-0006 | `IndexFreshness` sum-type location | Lives at `codegenie.indices.freshness`; documents why `AdapterConfidence`/`IndexConfidence` are NOT Phase 2 |
| 02-ADR-0007 | No Plugin Loader in Phase 2 | Phase 3 ships loader + first plugin + adapters + universal fallback together |
| 02-ADR-0008 | No event stream in Phase 2 | Defers to ADR-0034 §Consequences §1 |
| 02-ADR-0009 | `pytest-xdist` veto preserved | Re-affirms Phase 0's 10/4 vote; portfolio fits serial CI |

## Tradeoffs (consolidated)

| Decision | Gain | Cost | Source |
|---|---|---|---|
| `IndexFreshness` sum type with one Phase-2 consumer (`confidence_section.py`) | Variant set is exercised from day 1; no schema-without-consumer | One extra package (`indices/`); slightly more LOC than co-locating in B2 | final-design §2 |
| Registry annotations (`heaviness`, `runs_last`) instead of ABC fields | Scheduling concern at the right layer; zero ABC churn; preserves contract freeze | ~15 LOC sort-order edit to Phase 0 coordinator (ADR-gated) | final-design §13 |
| Reject Plugin Loader; ship Protocols + TCCMLoader skeleton only | Roadmap-honest; Phase 3 exit ("first plugin doubles as loader proof") stays intact | Adapter Protocols ship with zero implementations — risk of Phase 3 discovering wrong shape | final-design §7 |
| Reject per-repo encryption key for secrets; persist zero plaintext | Eliminates trust-tier theatre; no key-management fragility | Reviewer must run `gitleaks` manually at PR time for cleartext; no inline rotation suggestions until Phase 4+ | final-design §4 |
| Reject `pytest-xdist` reversal | Phase 0 veto holds; no shared-fixture race surface | Portfolio CI lane is serial (≤ 6 min budget) | final-design Goals §10 |
| Reject in-probe `ThreadPoolExecutor` for TreeSitterImportGraphProbe | Honesty to coordinator's single semaphore | ~10 s sequential vs. ~3 s threaded (~7 s tax) | final-design §12 |
| Sequential RuntimeTraceProbe scenarios | Avoid resource-race + attribution confusion across `docker run` instances | ~75 s wall-clock floor vs. theoretical ~15 s parallel | final-design §6 |
| `bubblewrap` opt-in-on-availability, not mandatory | Dev/CI parity preserved; honest about macOS gap | Less host isolation on macOS dev hosts than on Linux CI | final-design §3 |
| One file per Layer G scanner; no shared abstraction | Each probe reviewable in one sitting; no speculative coupling | ~200 LOC duplicated across four scanners | final-design §5 |
| Image digest as a declared-input *token*, not a `cache_key()` override | Phase 0 `declared_inputs` discipline survives; no second cache-key pathway | One optional callable on `ProbeContext` (mirrors Phase 1 `parsed_manifest` precedent) | final-design §6 |
| `mypy --warn-unreachable` per-module (not repo-wide) | Surgical-changes discipline (Rule 3); zero blast radius into Phase 0/1 | Phase 0/1 don't get the protection; backlog item to roll out later | final-design §"Design patterns applied" row 9 |

## Gap analysis & improvements

### Gap 1: Adapter Protocol drift between Phase 2 and Phase 3

The synthesis ships four `Protocol` classes with **zero implementations** in Phase 2; the only Phase-2-internal proof they're shaped correctly is the integration test loading the reference TCCM and dispatching to a mock. Phase 3's first adapter (`adapters/scip_node.py`, etc.) may discover the Protocol signature is wrong (e.g., `consumers(self, pkg: str)` should be `consumers(self, pkg: PackageId, *, transitively: bool = False)`). Discovering it at Phase 3 land means amending a Phase 2 module, which ripples through `report/confidence_section.py` and any Phase 3 plugin code that was prototyped against the wrong shape.

**Improvement.** Add an explicit Phase 3 entry-gate test: `tests/integration/adapters/test_phase3_handoff_smoke.py` lands in Phase 2 as **skipped** (with `@pytest.mark.skip(reason="enabled when Phase 3 plugin lands")`). The test, when unskipped at Phase 3, MUST import the Phase 2 Protocols *unchanged* and pass against `plugins/vulnerability-remediation--node--npm/adapters/`. Any drift requires an explicit ADR amendment to 02-ADR-0006/02-ADR-0007; the test naming makes the contract violation discoverable at PR review. The test stub also forces the reference TCCM to exercise every Protocol method via the mock dispatcher — closing the "Protocols defined, never called in Phase 2" critique fully.

### Gap 2: `cpu_count()=2` (GitHub-hosted runner) and heavy probes still serialize hard

The synthesis explicitly rejected per-tier semaphores because `cpu_count()=2` would degenerate them to 2-vs-2 starvation. But the single `Semaphore(min(cpu_count(), 8))` with `cpu_count()=2` *also* means cold gather on a hosted runner serializes through 2 slots — `SCIPIndexProbe` (~10 s) + `RuntimeTraceProbe` (~90 s) + `SemgrepProbe` (~3 s) + the rest = ~110+ s, which still hits the ≤180 s p95 cold target but only barely. If the bench canary regresses by 50 %+, Phase 2 fails its own budget on hosted runners specifically.

**Improvement.** Add `tests/bench/bench_portfolio_walltime_hosted_runner.py`, configured to emulate `cpu_count()=2` via `CODEGENIE_FORCE_CPU_COUNT=2` env var (read by `Semaphore` sizing). Run nightly (not per-PR) on the actual hosted-runner image. Comment-on-PR threshold ≥ 50 %; build-fail threshold ≥ 100 % (i.e., > 360 s p95). This makes the hidden assumption (critic [P] hidden-assumption #2) measurable instead of asserted. Also document the **escape valve**: if hosted-runner walltime regresses past the build-fail threshold, the operator option (not Phase 2's choice) is to commit per-fixture `.codegenie/cache/` blobs (open question §6 in the synthesis), which would re-flip the regenerate-each-run policy.

### Gap 3: `IndexHealthProbe` couples to every sibling probe's slice shape

B2 reads `last_indexed_commit`, `files_indexed`, `files_in_repo`, `last_traced_image_digest`, `built_image_digest`, `rule_pack_version` from sibling slices. The synthesis defends this as "inverted coupling — B2 reads slice metadata that is already part of the schema." But adding a new index source (Phase 3's SCIP-per-language, Phase 7's distroless-target manifest, Phase 14's cross-repo SCIP) silently *requires* editing B2 to know about the new freshness signal. Today B2 has a `match index_name:` block; tomorrow that block grows every phase. The toolkit's Open/Closed failure mode names this exactly.

**Improvement.** Apply the same `@register_dep_graph_strategy` discipline to B2: introduce `@register_index_freshness_check(index_name: IndexName)` in `src/codegenie/indices/freshness.py` as a decorator-registry. Each Phase 2 index source registers a small function `(slice: dict[str, JSONValue], head: str) -> IndexFreshness`. B2's `run()` loops over the registry. Phase 3 adds new index sources by **new file + new decorator**, never by editing B2. This closes the Open/Closed gap before it widens. Cost: ~30 LOC in `freshness.py` + 5–10 LOC per Phase-2 index source. The pattern symmetry with `@register_probe` and `@register_dep_graph_strategy` is itself a documentation win.

### Gap 4: `SecretRedactor` runs *after* the writer chokepoint conceptually, but the in-memory `SecretFinding` list flows in band with the slice

The synthesis says `redact_secrets` returns `tuple[redacted_slice, list[SecretFinding]]`. The caller is responsible for not persisting the findings list. But that's a convention enforced by code review, not by types — a future contributor could thread the findings into a debug log or audit anchor and silently leak plaintext. The critic ("Smart-constructor pattern missed at the secret-redactor boundary") named this verbatim.

**Improvement.** Apply the smart-constructor pattern at the redaction boundary:
```python
class RedactedSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    slice: dict[str, JSONValue]
    findings_count: int
    fingerprints: list[str]   # 8-hex fingerprints only
# Construction is private; ONLY `redact_secrets(...)` can produce a RedactedSlice.
# The writer accepts ONLY RedactedSlice.
```
A caller that drops the findings list cannot fake a `RedactedSlice` without going through `redact_secrets`, which by construction produces only fingerprints. The plaintext-cleartext audit-trail lives in the CLI summary path (returned separately by `redact_secrets`, not threaded into a `RedactedSlice`). This makes "redactor was called" type-checkable. Cost: ~20 LOC in `output_sanitizer.py`; the writer's signature tightens from `dict` to `RedactedSlice`.

### Gap 5: No explicit Phase-4 RAG-store handoff contract

Phase 4 (LLM fallback + solved-example RAG, roadmap §96) builds a vector store of solved examples atop Phase 3 outputs. But the vector-store *input shape* — what gets embedded — is not pinned by Phase 2. If Phase 4 embeds raw `repo-context.yaml`, the `SecretRedactor` chokepoint guarantee (G5) carries; if Phase 4 embeds intermediate `raw/*.json` artifacts, the same guarantee carries; if Phase 4 invents a new "RAG document" shape that pulls fields directly from in-memory probe outputs (bypassing the sanitizer), the chokepoint is silently broken.

**Improvement.** Phase 2 lands a `tests/adv/phase02/test_no_inmemory_secret_leak.py` that asserts **at the boundary**: every artifact reachable from the Phase 0 writer chokepoint passes through `redact_secrets`; no probe output is exposed to any consumer outside the sanitizer pipeline. The test reads the `OutputSanitizer.scrub` source via `inspect` and asserts the call to `redact_secrets` is present and unbypassable. This is a textual / structural test (Phase 0 already uses this pattern for `forbidden-patterns`); it makes the Phase 4 contract explicit at Phase 2 land time, before Phase 4 designs its RAG ingestion path.

## Open questions deferred to implementation

1. **Phase 5 microVM cleartext-access protocol.** The exact handoff (does the microVM receive `(file:line, pattern_class, fingerprint)` and re-scan? a one-time decryption capability tied to the workflow ID?) is a Phase 5 design concern. Phase 2's commitment is only "no plaintext anywhere Phase 4 can reach it." (Final-design §Open Q 1.)
2. **`TreeSitterImportGraphProbe` projection shape.** Phase 2 emits forward-only adjacency; Phase 3's first `ImportGraphAdapter` decides whether to pre-compute reverse, mmap a binary, or walk at query time. (Final-design §Open Q 2.)
3. **`SkillsLoader` org-shared tier signing.** Per-tier Sigstore signing for `~/.codegenie/skills-org/` is a Phase 14 multi-tenant concern. (Final-design §Open Q 3.)
4. **`ExternalDocsProbe` enablement & host allowlist schema.** Phase 2 ships opt-in skip-cleanly; the `external_docs:` config key shape lands when the first real user opts in. (Final-design §Open Q 4.)
5. **`mypy --warn-unreachable` rollout beyond Phase 2 modules.** Per-module config only in Phase 2; full-repo rollout is a tracked backlog item. (Final-design §Open Q 5.)
6. **Per-fixture cache pre-warming for CI walltime.** Phase 2 picks regenerate-on-every-run; if CI walltime regresses past 8 min, this flips to commit `.codegenie/cache/` blobs. The hosted-runner bench (Gap 2 above) is the trigger. (Final-design §Open Q 6.)
7. **`stale-scip` fixture regeneration policy.** Documented in `tests/fixtures/portfolio/stale-scip/README.md`; the structural assertion (`CommitsBehind.n >= 1`) is tool-version-agnostic — but the fixture regeneration ritual is implementer-time work. (Final-design §Open Q 7.)
8. **Whether to introduce `@register_index_freshness_check` (Gap 3 improvement) in Phase 2 or defer to Phase 3.** Phase 2 makes B2 the Open/Closed example; Phase 3 will discover the cost in practice. Defaulting to Phase 2 introduction; revisit at Phase 3 entry if the decorator-registry adds friction the synthesis didn't anticipate.
