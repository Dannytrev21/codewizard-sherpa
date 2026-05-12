# Phase 2 — Context gathering — Layers B–G: Devil's-advocate critique

**Reviewed by:** Devil's-advocate critic subagent
**Date:** 2026-05-12

## Method

I read all three designs and attacked each on its own terms. I do not propose alternatives. I cite specific components, sections, and numbers from `design-performance.md`, `design-security.md`, and `design-best-practices.md`, plus the contracts in `roadmap.md` Phase 2, `localv2.md §5`, and `production/design.md §2`.

---

## Attacks on the performance-first design

### Concrete problems (3–5 minimum)

1. **Problem:** The `DaemonPool` (`codegenie/coordinator/daemons.py`, Component §1) silently breaks the determinism invariant by making probe output a function of daemon lifetime, not declared inputs. A `scip-typescript` daemon that has indexed N prior repos in its lifetime is **not** the same indexer as a fresh process — JIT state, in-memory type-decl caches, and Node heap fragmentation all influence behavior. The cache-key composition listed for `SCIPIndexProbe` (`(probe_name, probe_version, sub_schema_version, content_hash_of_ts_sources, tsconfig_hash, lockfile_hash, scip_typescript_version)`) **does not include the daemon's accumulated state**. Two different workers will hash to the same cache key and emit different SCIP bytes.
   **Why it matters:** Violates `production/design.md §2` "determinism over probabilism" and `CLAUDE.md` "No LLM anywhere in the gather pipeline ... reproducible, cacheable, and auditable." Phase 1's whole `ParsedManifestMemo` discipline was about predictable, declared inputs; daemons smuggle hidden inputs back in.
   **Where:** §1 (DaemonPool), §2 (SCIPIndexProbe), §10 (SemgrepProbe daemon-pool path).

2. **Problem:** The `scip-typescript --pipe` / `--stdio` / `--x-language-server` modes the design banks on **may not exist**. Section §1 admits this: *"scip-typescript --stdio may not exist in the upstream release. Fallback: shell wrapper that invokes the indexer's Node.js API as a long-lived script."* — meaning the central performance pillar of Phase 2 is gated on a feature the author has not verified. The Tier-1 vs Tier-2 split, the 12 s "warm daemon" claim, and the 1.5 s "incremental indexing" claim all collapse if the mode is absent.
   **Why it matters:** Headline targets (`workflows/hour ≥ 1,200`, cold p95 ≤ 90 s, warm p95 ≤ 6 s) are derived from these daemon numbers. If `--stdio` doesn't ship, the design is "Phase 1 plus fork+exec costs", which it explicitly says is unviable.
   **Where:** §1 ("scip-typescript daemon"), Goals §"Cold first-run", Goals §"Cold-start daemon budget ≤ 4 s".

3. **Problem:** `IndexHealthProbe`'s 50 ms p95 hard budget (§3) is unachievable as specified. The probe is required to compute `commits_behind` via `git rev-list --count` (an actual subprocess), `coverage_pct` against PathIndex extension counts, image-digest match across multiple upstream probes, *and* rule-pack version comparison — and the design also sets `cache_strategy = "none"` so it must do this work on every gather, including warm-everything-else gathers. A `git rev-list --count` on a Linux box for a non-trivial repo is 20–80 ms by itself; under `asyncio.wait_for(50 ms)` it will trip the timeout, the probe will emit `confidence: low` deterministically on every gather, and **the most important probe in the system will permanently lie**.
   **Why it matters:** The roadmap exit criterion is "IndexHealthProbe surfaces at least one real staleness case in CI." A probe whose own budget makes it routinely degrade-to-low *can't* meet that — every test will see `low` and no test will tell the truth from the false positive.
   **Where:** §3, "Tail-latency budget enforcement"; Goals: "≤ 50 ms p95"; `cache_strategy = "none"`.

4. **Problem:** The Tier-3 gating ("RuntimeTraceProbe is opt-in per task class; gated by `applies_to_tasks=['distroless_migration', 'container_hardening']`", §13) means **`RuntimeTraceProbe` never runs in Phase 2** — there is no task class active in Phase 2 (the first task class is introduced in Phase 3). The probe ships but is dead code until Phase 3 / 7. The "every probe layer runs against real repos" exit criterion is unmet for Layer C dynamic, and `IndexHealthProbe`'s `requires=["runtime_trace"]` makes B2 permanently emit `runtime_trace: not_run` in CI. The fixture-driven staleness signal will be drowned in `not_run`s.
   **Why it matters:** Same exit-criterion failure as the best-practices design, plus the dependency edge makes the noise concrete.
   **Where:** §3 (`requires=["scip_index","syft_sbom","grype_cves","semgrep","runtime_trace"]`), §13 ("applies_to_tasks gating").

5. **Problem:** `tantivy` (§14) is acknowledged as a Rust-backed C-extension that Phase 1's synthesizer "explicitly rejected ... on the same grounds" — and then the design adds it anyway with a hand-wave that "this case is different." The handwave is unjustified: the alternative is `ripgrep` fallback, which the design itself says is "≥ 50 ms per query, acceptable for local-dev." If ripgrep is acceptable, tantivy is the kind of "speculative feature" Rule 2 of the global instruction set forbids; if ripgrep isn't acceptable, the perf claims for it are wrong.
   **Why it matters:** Adds a new C-extension surface (and a new threat: the security lens lists `tree-sitter` grammars as a known RCE-on-import vector — `tantivy`'s wheel pinning will need the same audit) for a capability the Planner *will not query until Phase 8 at the earliest*. The whole index is built ahead of any consumer.
   **Where:** §14, "Tantivy adds a Rust-backed C-extension dep ... Open question for the synthesizer."

### Hidden assumptions (2–3)

1. **Assumption:** Workers in Phase 14 are long-lived enough to amortize the 4 s daemon-prewarm and the 200 MB resident daemon footprint. **What breaks if wrong:** if Phase 14's autoscaling churns workers (e.g., spot instances, K8s evictions, OOMKills caused by the very 200 MB daemons), every gather pays full cold-start cost and the perf model inverts.

2. **Assumption:** Each probe's `declared_inputs` glob captures *all* real inputs. The design's per-file Semgrep cache and per-file tree-sitter cache assume a finding is a pure function of `(file_content_hash, rule_pack_version_hash)`. **What breaks if wrong:** Semgrep rules that use file-set context (taint mode is mentioned as opt-out; but even basic `--enable-experimental` rules can be cross-file) produce stale per-file findings on warm cache, and `IndexHealthProbe` won't catch it because the probe still reports `last_indexed_commit == HEAD`.

3. **Assumption:** The `.codegenie/index/` directory (SCIP index, tree-sitter cache, BM25 index) is durable enough to be trusted across gathers. **What breaks if wrong:** This is a new on-disk state namespace that Phase 0's `cache gc` doesn't know about (§2 admits this is an open question). Stale `.codegenie/index/scip-index.scip` from a prior worker becomes silent input to the next worker — exactly the failure mode `IndexHealthProbe` exists to catch, but now caused by the design's own optimization.

### Things this design missed that a different lens caught

- **Code execution as a threat surface.** The design treats `scip-typescript`, `semgrep`, and `tree-sitter` as "tools that produce JSON we parse" — the security design correctly identifies them as **code-loading interpreters running attacker-controlled bytes**. Performance's DaemonPool is the worst possible posture for that threat: a single long-lived process retains exploit state across repos.
- **Postinstall execution by package managers.** The performance `BuildGraphProbe` (§6) says it computes the graph from manifests alone — good — but the Semgrep / SCIP paths happily run inside a daemon that loads `node_modules` type declarations, and the design never says `--ignore-scripts`. Security catches this explicitly for B5.
- **The `runtime_trace_pending` slice the best-practices design names** — performance just makes B2 emit `not_run` for runtime trace, which is structurally indistinguishable from "we tried and failed."

---

## Attacks on the security-first design

### Concrete problems (3–5)

1. **Problem:** The design **kills BuildGraphProbe (B5)** by forbidding all package-manager invocation (§B5: "this design **forbids invoking the package manager at all in Phase 2** for BuildGraph ... This contradicts `localv2.md §5.2 B5` which calls for invoking the tools. The security lens overrides"). `localv2.md §5.2 B5` is explicit that the *value* of B5 over static parsing is that it captures the *resolved* graph including hoisted dependencies, workspace-level overrides, `pnpm`'s peer-dep resolution, and `turbo`'s pipeline shape. The design proposes static parsing only and accepts `confidence: medium` — but downstream consumers (Phase 12 cross-repo dep analysis is explicitly built on this) will now be reasoning about a graph that is, for any non-trivial pnpm/yarn-workspaces/turbo monorepo, *wrong* (not low-confidence — wrong: missing edges that the resolver would have added).
   **Why it matters:** This is a direct contract violation with `localv2.md §5.2 B5` and breaks the `CLAUDE.md` invariant "Facts, not judgments. Probes capture evidence ... they do not write conclusions." Emitting a fabricated graph with `confidence: medium` is writing a conclusion ("here's the graph") on top of evidence the probe didn't collect.
   **Where:** Components §B5; Goal #5 (B2 confidence rollup is now reading a partially-fabricated B5).

2. **Problem:** `RootlessPodmanContainer` (§"RootlessPodmanContainer strategy") introduces a new strategy abstraction (`SandboxStrategy` interface, `InProcessSubprocess` / `RootlessPodmanContainer` / `DockerInDocker` / `MicroVM` planned implementations) that is **not in Phase 0's surface, not in Phase 1's surface, and is forward-declaring infrastructure for Phase 5** (ADR-0012 microVM, ADR-0019 sandbox stack). This is the gold-plating the global rules forbid: "No abstractions for single-use code" (Rule 2) and "Surgical Changes" (Rule 3). Phase 2 needs *one* new sandbox strategy; the interface, the capability negotiation system, and the three additional planned strategies are speculative.
   **Why it matters:** Adds abstraction tax to every probe author for the next ~3 phases. The four-strategy lattice (`isolation level` × `available capabilities` × `cost class` per Components §SandboxStrategy interface) is the kind of architecture that exists to be admired, not used. ADR-0019 is explicitly deferred; Phase 2 is committing concrete code to a deferred decision.
   **Where:** Components §SandboxStrategy interface, §RootlessPodmanContainer; Architecture diagram TRUST BOUNDARY 2.

3. **Problem:** The design's `scip-typescript` invocation **refuses to run `npm install`** (§B1: "we do not invoke `npm install` ... `node_modules` is mounted as-is if present; if absent, the probe records `node_modules_present: false` and emits `confidence: medium`"). For the *vast majority* of cloned-fresh repos and CI fixtures, `node_modules` is absent. The probe will therefore emit `confidence: medium` (or `low`) on virtually every real repo in CI. The roadmap exit criterion ("IndexHealthProbe surfaces at least one real staleness case in CI") becomes meaningless because **every CI run will be `low` confidence on SCIP for the wrong reason** — not because the index is stale, but because the design refuses to populate the dependency tree. The signal-to-noise on B2 is destroyed.
   **Why it matters:** Evidence quality loss — the SCIP index is the load-bearing Layer B artifact, and the design makes it routinely under-resolved. Downstream `NodeReflectionProbe`, `TestCoverageMappingProbe`, and Stage 3 Planning all consume SCIP symbol resolution that is now mostly `unresolved_imports`.
   **Where:** §B1 ("No `npm install` ⇒ lower coverage for repos that ship without committed `node_modules`").

4. **Problem:** The local-registry-mirror at `127.0.0.1:55300` (§"Local pull-only registry mirror") **is a new always-on background service** that no other design contemplates and that violates `localv2.md`'s "Single Python project, no services, no databases. Filesystem-backed everything" (`CLAUDE.md` Conventions). The design says it's launched by an "out-of-process helper (rootless Podman)" — that is a service. It must be pre-warmed with org-specific base images, managed across gathers, GC'd when stale, restarted when crashed. The operational tax is unbounded.
   **Why it matters:** Phase 2 should be additive to a single Python CLI; the design instead adds a long-lived registry, requires `distribution/registry:2.8.x` to be installed and trusted, and forces every dev box / CI runner to host it. None of this appears in `localv2.md §6` external tool dependencies.
   **Where:** Architecture diagram "Local pull-only registry mirror"; §RootlessPodmanContainer "images pulled at sandbox launch from 127.0.0.1:55300 mirror only".

5. **Problem:** B2 (`IndexHealthProbe`) is over-empowered: §B2 ("B2 *fails the gather* if any required dependency probe failed for a non-explicit reason ... treated as evidence of orchestrator tampering and exits non-zero"). This conflates two failure modes — "an upstream probe legitimately timed out" (normal) and "the orchestrator was tampered with" (rare, hostile) — and resolves both by failing the entire gather. In a Phase 14 portfolio-scale scan, one flaky `scip-typescript` run will hard-fail the gather for that repo and ripple through Stage 1 Assessment. Phase 2 has no recourse: there's no `--allow-degraded` flag in this design.
   **Why it matters:** Violates the spirit of `localv2.md §3` "failure isolation: one probe's exception does not poison the rest." The security lens has converted a hygiene probe into a global circuit breaker without a kill switch.
   **Where:** §B2 "Tradeoffs accepted: B2 fails the gather if any required dependency probe failed".

### Hidden assumptions (2–3)

1. **Assumption:** Rootless Podman is available on every target environment. **What breaks if wrong:** macOS dev path is acknowledged as degraded (§"macOS path is degraded"); the design then admits Docker Desktop is an accepted second-best, which means the entire security claim collapses on macOS — and `CLAUDE.md` doesn't say "Linux only." Phase 14's eventual EKS runners may use containerd directly, not Podman.

2. **Assumption:** A `codegenie/probe-runtime:<digest>` image (built reproducibly from a checked-in Dockerfile) can be pinned and shipped with the project. **What breaks if wrong:** This is a new deliverable Phase 0 / Phase 1 didn't establish. Who builds it? Where is it hosted (the design forbids `docker.io` egress at probe time)? How is the digest rotated when a CVE lands in the bundled `syft` binary? The "supply chain integrity > automatic patching" stance (§B1) becomes "Phase 2 ships with CVE-vulnerable bundled tools indefinitely."

3. **Assumption:** `gitleaks --redact` plus the `OutputSanitizer Pass 4` are belt-and-suspenders enough that the raw bytes of a secret never escape. **What breaks if wrong:** §Goals #4 enumerates a long list of places secrets must never appear; the design also keeps raw artifacts under `.codegenie/context/raw/` (per `localv2.md`). If a future probe author adds a `gitleaks --no-redact` invocation or a probe that captures a `matched_text` field, both walls fail simultaneously. The defense depends on every future probe author honoring the convention — exactly the kind of convention Rule 11 says is hard to enforce.

### Things this design missed

- **The performance cost of Goal #2 ("scip-typescript runs only inside the container sandbox, with $HOME empty, $PATH minimal, --network=none").** The design lists "Container startup cost: ~300–600 ms" per probe — but Phase 2 has 6–8 container-strategy probes, sequentially scheduled within a per-image-digest pipeline group, on every gather. That's 2–5 s of pure sandbox-boot overhead per gather before any work happens. The performance design's `IndexHealthProbe ≤ 50 ms` target becomes laughable in this posture.
- **The compounding effect of fingerprint-only secret storage on debugging.** The best-practices design at least keeps a redacted JSON artifact under `raw/`. Security's "never written to disk, never appear in `repo-context.yaml`, never appear in any audit record, never appear in any cache blob" makes diagnostic work on a real CI failure ("which file/line is the finding?") strictly harder. Goal #4 lists `file`, `line_start`, `line_end` are preserved — but the `entropy_band` rounding throws away information that would matter for a false-positive review.
- **The roadmap exit criterion about real OSS repos.** Best-practices ships `test_real_oss_with_layer_b_g.py` against `nestjs/nest` at a pinned SHA. Security's `--network=none` + "no `npm install`" makes that test impossible: `nestjs/nest` does not ship `node_modules`. The local registry mirror won't have `npm install`. There is no path to running the design against a real OSS repo in CI.

---

## Attacks on the best-practices design

### Concrete problems (3–5)

1. **Problem:** The design **defers `SBOMProbe`, `CVEProbe`, and `RuntimeTraceProbe` to Phase 5** (§Components 3 "Layer C probes — static-only in Phase 2"). This is a direct violation of `roadmap.md` Phase 2 scope, which **names `syft`, `grype` as Phase 2 tools** ("Tooling & setup. External CLIs: `semgrep`, `syft`, `grype`, `gitleaks`, `scip-typescript`, and `tree-sitter` parsers."). `syft` and `grype` exist for *exactly* the SBOM/CVE probes the design defers. The roadmap also commits Phase 3 (`Vuln remediation — deterministic recipe path`) to consume CVE data — Phase 3 depends on Phase 2's Layer C dynamic capability. Deferring breaks the next phase's exit criterion.
   **Why it matters:** This is the literal scope violation. The design author self-flags it as "may not match what the roadmap author intended" (§Acknowledged blind spots) but proceeds anyway. Rule 7 ("Surface conflicts, don't average them") was followed; Rule 4 ("Goal-driven execution. Define success criteria. Loop until verified") was not — the success criterion is the roadmap text, and the design chose not to satisfy it.
   **Where:** Components §3 "Scope decision"; §Acknowledged blind spots first bullet; Goals §"Public API surface" (17 probes, missing C2/C3/C4).

2. **Problem:** The exit criterion "**IndexHealthProbe surfaces at least one real staleness case in CI**" is broken by the deferral. §B2 describes a stale-SCIP fixture (`tests/fixtures/stale_scip_repo/`) and asserts B2 reports `commits_behind > 0` — fine for SCIP. But B2's `requires` field lists `syft_sbom`, `grype_cves`, `runtime_trace` as upstream probes whose freshness it watches; with those probes **deferred to Phase 5**, B2 in Phase 2 has nothing meaningful to report on the SBOM/CVE/trace domains. The stale-SBOM and stale-runtime-trace test cases — the cases that motivated B2's existence in `production/design.md §2` — cannot be written in Phase 2. The exit criterion is met *only* on the SCIP slice, narrowly.
   **Why it matters:** The roadmap text doesn't say "SCIP staleness in CI"; it says "at least one real staleness case." A reviewer who reads B2's domains in `localv2.md §5.2 B2` (which include SBOM and runtime-trace freshness) will conclude the exit criterion is partially-met-at-best.
   **Where:** Component §2.2 "A deliberately-seeded staleness fixture ... Phase 2 roadmap exit-criterion test"; §Acknowledged blind spots.

3. **Problem:** **`ProbeContext.peer_outputs` extension** (Component §2.2) is described as "the one Phase 0 dataclass extension Phase 2 makes" — but the Phase 0 / Phase 1 designs in `00-bullet-tracer-foundations/final-design.md` and `01-context-gather-layer-a-node/final-design.md` froze the `ProbeContext` shape. Adding `peer_outputs` is a structural change to a chokepoint Phase 0/1 explicitly does not touch. The design says it's "ADR-gated, same shape as Phase 1's `ParsedManifestMemo` extension" — but `ParsedManifestMemo` was a probe-internal helper, while `peer_outputs` exposes other probes' outputs and changes the coordinator's contract with probes. The "extension by addition" invariant in `CLAUDE.md` says "Adding Java, Python, or a new task type must be new probes + new Skills, never edits to existing probes or the coordinator." This edits the coordinator.
   **Why it matters:** Sets the precedent that ADR-gated coordinator edits are routine. Once `peer_outputs` lands, the next phase that wants `peer_outputs_streaming` or `peer_outputs_async` will cite this ADR as cover.
   **Where:** Component §2.2 "Internal design — the asymmetry lives in observability, not in code"; Open question #7.

4. **Problem:** The Skills loader (§4.1) reads from `~/.codegenie/skills/`, `.codegenie/skills/`, *and* `~/.codegenie/skills-org/` — three roots — and tests are required to run "with `HOME=/dev/null`-equivalent isolation" (§Risks #2). That's a leak of execution-environment dependency into the test suite, and Phase 1 deliberately avoided `$HOME`-coupled state. The design's mitigation ("the `roots` parameter is explicit") is correct for the loader API but the **`SkillsIndexProbe.declared_inputs`** explicitly lists `"~/.codegenie/skills/**/SKILL.md"` — meaning the cache key resolves `~` against `os.environ["HOME"]` at runtime. Cache invalidation now depends on the user's $HOME existing. Two engineers on the same repo with different `~/.codegenie/skills/` sets will get cache mismatches on `repo-context.yaml`.
   **Why it matters:** The content-addressed cache invariant (declared inputs → deterministic key) is broken by user-scoped roots that aren't reflected in `declared_inputs` in a portable way.
   **Where:** §4.1 "discovery, validation, indexing"; §4.2 "declared_inputs ... resolved against os.environ["HOME"] at cache-key time".

5. **Problem:** The design adds **`tantivy`, `markdown-it-py`, `tree-sitter`, `tree-sitter-typescript`, `tree-sitter-javascript`** as new pip dependencies (§Resource & cost profile "External-dep additions"). Phase 1 had a stated discipline of no new C-extensions for parsers. The design self-flags this in §Acknowledged blind spots ("`tree-sitter` C-extension was unavoidable; I added it but didn't soul-search"), which is honest, but `tantivy` is *not* unavoidable — the same section in §Risks #3 admits "the BM25 ripgrep fallback is the primary path in CI; `tantivy` is opt-in and gated by `pip extras`." If ripgrep is the CI path, **why is tantivy a dependency at all?** Adding an opt-in C-extension that the CI never exercises is the worst possible test-coverage posture — it's dead-code-by-default.
   **Why it matters:** Rule 2 (Simplicity First) and Rule 9 (Tests verify intent) both fail: `tantivy`'s code paths aren't tested, but the dep is in `pyproject.toml`, so every install pays for a Rust toolchain or wheel that nothing runs.
   **Where:** §Resource & cost profile; §Risks #3.

### Hidden assumptions (2–3)

1. **Assumption:** Deferring dynamic Layer C to Phase 5 won't cascade into Phase 3 / 4 work. **What breaks if wrong:** Phase 3 ("Vuln remediation — deterministic recipe path") needs to know whether a given repo's SBOM contains a vulnerable package — that's *exactly* `SBOMProbe` + `CVEProbe`. The design's deferral pushes Phase 3 to either build them itself (Phase 3 isn't budgeted for that) or read CVE data without an SBOM (incorrect by `production/design.md §2.3` which shows SBOM-then-CVE as the Layer C pipeline). The "Phase 5 sandbox makes these cheap" argument assumes Phase 5 lands before Phase 3 needs them — but Phase 3 is the *very next phase*.

2. **Assumption:** The closed `detect.type` enum on the conventions catalog (§4.3 "the dispatch is a single `match/case`") is enough to keep the catalog from becoming a DSL. **What breaks if wrong:** Phase 7 (Chainguard distroless) is named in `CLAUDE.md` as the test of "extension by addition." If distroless requires a `detect.type` not in the closed enum (highly likely — distroless conventions are richer than vuln-remediation conventions), then either the enum is opened (the "no DSL" defense fails) or `convention.py` gets edited (Phase 7's exit criterion "diff touches only new files" fails).

3. **Assumption:** "Boring is good; ADR per change" (§Open question #2) is sustainable when Phase 2 already adds **17 probes, 2 catalogs, 1 loader, 6 tool wrappers, 1 coordinator extension**. **What breaks if wrong:** Each ADR-gated change to the coordinator (the `peer_outputs` extension is one) trains the project to accept coordinator edits as the norm. The discipline degrades; by Phase 8 the coordinator is the Phase 0 file with 12 ADR-gated patches grafted on, and the "extension by addition" invariant is dead in practice.

### Things this design missed

- **Adversarial-bytes-as-input.** §Failure modes & recovery lists "Adversarial markdown in external doc (zip-slip, huge file)" as a single row with "Phase 1 `safe_yaml`/path-traversal guards inherited" — but it doesn't say what guards `semgrep` / `gitleaks` / `tree-sitter` get when run by the probes. The security design correctly identifies these as code-loading, hostile-input surfaces; best-practices treats them as well-behaved JSON producers. The "wrapper raises typed exception" defense doesn't help if `semgrep` ReDoS hangs the wrapper before it raises.
- **B5 monorepo accuracy.** §2.3 says `BuildGraphProbe` "runs `pnpm list -r --depth -1 --json`" — which the security lens flagged as `postinstall`-executing. Best-practices does not say `--ignore-scripts`. A hostile `package.json` with a `postinstall: 'curl ... | sh'` is executed by this probe as designed.
- **The `--strict` CLI flag** (§Component 2.2) is proposed by best-practices alone. The performance design and security design both have ways for B2 confidence to affect downstream behavior (perf via slice projection, security by hard-failing the gather). Best-practices' `--strict` is the *most defensible* of the three but it's introduced casually as an open question; if the synthesizer doesn't pick it up, the only design with a usable failure handle drops it.

---

## Cross-design observations

### Where do the three disagree?

| Dimension | Performance picks | Security picks | Best-practices picks | What's at stake |
|---|---|---|---|---|
| **Dynamic Layer C (SBOM/CVE/RuntimeTrace)** | Ship all three; `RuntimeTraceProbe` gated by `applies_to_tasks` (effectively dead in Phase 2) | Ship behind container sandbox; `npm install` forbidden; B5 forbids package-manager use | Defer all three to Phase 5; Layer C ships static-only | Roadmap Phase 2 exit criterion ("every probe layer runs against real repos") + Phase 3's dependency on CVE data |
| **scip-typescript invocation** | Long-lived daemon via `--stdio`/`--pipe`; aggressive caching | One-shot inside container sandbox, `--network=none`, no `npm install` | Plain subprocess via `tools/scip_typescript.py` wrapper; version-pinned in `pyproject.toml` | Determinism vs perf vs evidence quality; daemon coupling vs sandbox tax vs honesty |
| **BuildGraphProbe (B5)** | `networkx` over parsed manifests; no subprocess | Static-only; explicit "forbids invoking the package manager" | Runs `pnpm list -r --depth -1 --json` (best-practices doesn't say `--ignore-scripts`) | `localv2.md §5.2 B5` compliance; postinstall RCE surface; monorepo accuracy |
| **C-extension dependency posture** | Adds `tantivy` (acknowledged controversial), keeps tree-sitter | Pins tree-sitter grammars by git-SHA + wheel hash; treats as RCE surface | Adds `tantivy` *and* `markdown-it-py` *and* `tree-sitter-*` (self-flagged as Phase 1 discipline drift) | Phase 1's "no new C-extensions for parsers" discipline |
| **`IndexHealthProbe` (B2) posture** | Hard 50 ms budget; `cache_strategy=none`; emits hot-view shape | Honesty oracle; fails the gather on non-explicit dep failure; schema-dependency rule | Structurally identical to peers; `--strict` flag; dedicated dashboard; deliberately-seeded fixture | What "load-bearing probe" means in practice; how strict is too strict |
| **New infrastructure beyond a single Python CLI** | `DaemonPool` (new abstraction); `.codegenie/index/` namespace; per-file sub-caches | `RootlessPodmanContainer`, `SandboxStrategy` interface, local registry mirror, `codegenie/probe-runtime` image | `tools/` wrapper package; `skills/` loader package; that's it | `localv2.md` "Single Python project, no services, no databases" |
| **Sandboxing posture for Phase 2** | None new (relies on Phase 1's in-process subprocess sandbox) | New: rootless Podman + cgroups v2 + `--network=none` + 4 boundaries | None new (inherits Phase 1) | Whether code-execution probes can run on dev laptops at all |

### Which disagreement matters most for *this* phase?

**The dynamic Layer C question.** Performance ships all three but gates `RuntimeTraceProbe` behind a task class that doesn't exist yet (effective deferral disguised as completeness). Security ships them with such heavy isolation that they won't pass the roadmap's implicit "runs against real OSS repos in CI" test (no `npm install`, no `docker.io` egress). Best-practices openly defers, violating the Phase 2 scope text that names `syft` and `grype`. **All three fail the roadmap exit criterion in different ways**, but the failure mode differs: performance fails by emitting `not_run`; security fails by emitting `low confidence`; best-practices fails by emitting nothing. The synthesizer must pick which failure mode is most honest and most repairable in Phase 5 — and must reconcile with Phase 3's hard dependency on Phase 2 producing CVE evidence. The whole determinism-first arc of the roadmap (Phases 0–2 deterministic, Phase 3 first transform) presumes Phase 2 lands Layer C. None of these three designs deliver that cleanly.

### Where do all three quietly agree on something questionable?

1. **The gather pipeline can run on local dev without strong sandboxing for the POC.** Performance assumes Phase 1's in-process subprocess sandbox is enough for the daemon model. Best-practices says "Phase 1's in-process caps + `O_NOFOLLOW` + sanitizer are inherited and applied to every new parser; I will not add a per-probe sandbox layer that Phase 0 never sanctioned." Security adds container sandboxing but **admits the macOS path is degraded to Docker Desktop with "no security claim staked"**. All three are implicitly saying "on a dev laptop running an arbitrary OSS repo from the internet, executing `semgrep` / `scip-typescript` / `gitleaks` / package-manager calls is acceptable risk for the POC." `production/design.md §2` doesn't endorse this, and `CLAUDE.md` doesn't tell us where the line is. If a real attacker plants a hostile `tsconfig.json` in a watched repo, Phase 2 (any version) runs it on the engineer's machine.

2. **`IndexHealthProbe` requires probes whose absence is normal.** Performance's `requires` includes `runtime_trace` (gated by task class, won't run); security's includes `gitleaks` (could be skipped); best-practices' includes `scip_index`, `semgrep` (could be missing on non-Node repos). All three handle "dependency absent" with `not_run` / `low confidence`. **None addresses that B2's signal becomes mostly-`not_run` on the modal repo in CI**, drowning the real staleness signal. The roadmap's "surfaces at least one real staleness case" exit criterion is at risk of being trivially-but-uselessly satisfied.

3. **Catalogs as data, not code — but enforced only by convention.** Best-practices' closed `detect.type` enum, performance's "precompiled rule cache", security's `additionalProperties: false` at module load all rely on **every future contributor** continuing to add data, not code, to the catalogs. None proposes a CI gate that fails when a catalog file's dispatch grows a new branch in `convention.py` without a corresponding schema bump. The discipline is bookkeeping — exactly what Rule 11 warns degrades over time.

---

## Roadmap-level critiques

1. **Does this phase set up problems for later phases?**
   - **Yes, all three do.** Best-practices' deferral of SBOM/CVE/RuntimeTrace pushes scope into Phase 5 (sandbox + trust gates) — but Phase 3 (vuln remediation) is *before* Phase 5 and needs CVE data. The roadmap orders Phases 3 → 4 → 5 deliberately (deterministic recipe → LLM fallback → sandbox); best-practices inverts the dependency.
   - Performance's `DaemonPool` and `.codegenie/index/` namespace bake in optimizations Phase 5 (sandbox) and Phase 14 (continuous gather) will have to either preserve or rip out. Daemons inside a microVM is an architectural awkwardness the design doesn't address.
   - Security's `SandboxStrategy` interface forward-declares the Phase 5 / Phase 16 architecture but commits Phase 2 to scaffolding that ADR-0019 (sandbox stack) explicitly defers. If the deferred ADR resolves against Podman (e.g., picks Firecracker or gVisor without a Podman shim), the Phase 2 strategy code is wasted.

2. **Does it rely on something an earlier phase didn't establish?**
   - **Security** relies on a `codegenie/probe-runtime` container image, a local registry mirror, a pinned `tools/digests.yaml`, and rootless Podman being installed — none of which Phase 0 or Phase 1 set up.
   - **Performance** relies on `scip-typescript --stdio` (unverified upstream feature), on `.codegenie/index/` (new namespace Phase 0's `cache gc` doesn't manage), and on Phase 14-worker shape (long-lived workers amortizing daemons) — but Phase 14 is twelve phases away.
   - **Best-practices** relies on `ProbeContext.peer_outputs` (a Phase 0 coordinator extension dressed up as ADR-gated) and on `~/.codegenie/skills/` discovery semantics that Phase 1 did not pin.

3. **Does it violate any load-bearing commitment?**
   - **`production/design.md §2` "Deterministic gather → No LLM anywhere":** All three honor this textually. Performance's `DaemonPool` puts cross-gather hidden state into a probe execution, which is *probabilism-by-implementation* even if it isn't an LLM. Borderline; not a clean violation, but a structural weakening of "reproducible, cacheable, auditable."
   - **`CLAUDE.md` "Facts, not judgments":** Security's `BuildGraphProbe` emits a *static* graph with `confidence: medium` and calls that "evidence" — but a partially-resolved graph is a judgment ("this is what the resolver would have produced") wearing evidence's clothes. The honest probe output would be "this manifest set; no resolution performed."
   - **`CLAUDE.md` "Extension by addition. Adding ... must be new probes + new Skills, never edits to existing probes or the coordinator":** Best-practices' `ProbeContext.peer_outputs` edits the coordinator. The design acknowledges this and ADR-gates it; the acknowledgement is honest, but the violation is real.
   - **`localv2.md §5.2 B5`:** Security explicitly contradicts it ("This contradicts `localv2.md §5.2 B5` which calls for invoking the tools. The security lens overrides"). That is a direct, named override of a contract.
   - **`localv2.md` "Single Python project, no services, no databases. Filesystem-backed everything":** Security's local registry mirror is a service. Performance's daemons are long-lived processes (a service, lightly).
   - **`roadmap.md` Phase 2 tooling list (`syft`, `grype` named):** Best-practices defers both. Direct scope violation.
