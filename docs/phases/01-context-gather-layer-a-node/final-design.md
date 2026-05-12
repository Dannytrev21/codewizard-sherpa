# Phase 01 — Context gathering: Layer A (Node.js): Final design

**Status:** Design of record (synthesized from three competing designs + critique).
**Synthesized by:** Graph-of-Thought synthesizer subagent
**Date:** 2026-05-12
**Sources:** `design-performance.md` [P] · `design-security.md` [S] · `design-best-practices.md` [B] · `critique.md`

Provenance tags below: `[P]`, `[S]`, `[B]` for single-lens; `[P+S]`, `[P+B]`, `[S+B]` for two-lens agreement; `[all]` for unanimous; `[synth]` for synthesizer departure from all three.

---

## Lens summary

Phase 0 built the spine — probe ABC, async coordinator, content-addressed cache, layered JSON Schema, two-pass sanitizer, subprocess allowlist, audit anchor. **Phase 1's job is to populate that spine with five real Node.js probes, not to extend it.**

The three lens designs split cleanly:

- **[B] gets the *shape*:** five new probe files, one new sub-schema per probe, two catalog YAML files, explicit imports, no edits to Phase 0 chokepoints. This matches Phase 0's §12 handoff verbatim. The blind spot is that [B] ignores adversarial input handling and accepts probe-isolation duplication that the perf and security lenses both flag.
- **[S] gets the *threat model*:** Phase 1 is the first phase parsing adversarial bytes from untrusted repos at scale. In-process parse caps, hard size/depth limits, `O_NOFOLLOW` opens, no `node --version` invocation, no `node_modules/*` parsing by default, no Helm/Terraform rendering. The blind spot is the per-probe fork+exec sandbox — a brand-new architectural layer Phase 0 never sanctioned, which the critic correctly attacks as an ABC-bypassing edit-not-add and as a platform-conditional security claim.
- **[P] gets the *seam*:** Phase 0's `ProbeExecution ∈ {Ran, CacheHit, Skipped}` (final-design §2.6) is the right place to share parsed `package.json` across probes — not a msgpack side-channel and not by re-parsing three times. The blind spot is `views.json` forward-compat with an unspecified Phase 8, mmap reopening, hand-rolled `yarn.lock` parser justified by ~16 ms of *average* warm-path latency, and pushing for a `PathIndex` mixin that drifts the frozen ABC.

The synthesis picks **[B]'s shape, [S]'s in-process caps and parse hygiene, [P]'s coordinator-level shared-parse seam** — and refuses the per-probe sandbox, the `views.json` forward dependency, the mmap reopening, the msgpack side-channel, and the hand-rolled yarn parser. Where `localv2.md` and a lens disagree, `localv2.md` wins (Phase 0 §2.3 conformance rule).

---

## Goals (concrete, measurable)

- **Functional (roadmap exit):** `codegenie gather` produces a useful `repo-context.yaml` on a real Node.js repo. All six Layer A probes populate their slices. Schema validation passes. Cache hits on second run (no probe re-executes). `[B+roadmap]`
- **Probe contract conformance:** Zero edits to `codegenie/probes/base.py`; `tests/unit/test_probe_contract.py` snapshot test passes. `[B+all+critic]`
- **Coverage ratchet:** 90% line / 80% branch on `src/codegenie/` excluding `cli.py` and the new `codegenie/probes/*` modules where structurally-narrow branches make 90% gameable; **per-module floor 85% line / 75% branch for `deployment.py` and `ci.py`**, declared explicitly in `pyproject.toml` with the ADR-amendment trigger. `[synth — softer than [B]'s blanket 90/80, harder than [P]'s silence]`
- **Adversarial robustness:** Zero successful parse-driven RCE or OOM against an adversarial fixture corpus (≥ 20 hostile inputs covering YAML bombs, JSON bombs, symlink escape, regex DoS, deep nesting, oversized inputs, hostile filenames). Caps enforced **in-process**, not via per-probe subprocess. `[synth — [S]'s threat coverage, [P]'s no-fork cost shape]`
- **Wall-clock targets (advisory, surfaced via Phase 0 bench infrastructure, not PR-blocking):**
  - Cold (1k-file fixture, all probes miss cache): p50 ≤ 4 s, p95 ≤ 8 s. `[B]`
  - Warm (cache full, all hits): p50 ≤ 0.4 s, p95 ≤ 1 s. `[B+P]`
  - Incremental (`package.json` changed, four hits, two misses): p50 ≤ 1 s, p95 ≤ 2 s. `[synth — softer than [P]'s 250 ms]`
- **Hard caps in every parser (in-process, fail-loud):** `package.json` ≤ 5 MB; lockfile ≤ 50 MB; YAML depth ≤ 64; JSON depth ≤ 64; per-probe parse wall-clock ≤ probe's `timeout_seconds` (Phase 0 coordinator enforces). Exceeding any cap raises a typed exception → `ProbeOutput(confidence="low", errors=[...])`. `[S — without the subprocess fork]`
- **Tokens per run:** 0. `[all]` Phase 0 `fence` CI job continues to assert.
- **Extension by addition:** Phase 1 adds **only new files** under `src/codegenie/probes/`, `src/codegenie/schema/probes/`, `src/codegenie/catalogs/`, `tests/unit/probes/`, `tests/adv/`, `tests/integration/probes/`, `tests/fixtures/`. The only edits to existing Phase 0 files are:
  1. `src/codegenie/probes/__init__.py` — five new `from . import ...` lines (the documented extension seam). `[B+all]`
  2. `src/codegenie/probes/language_detection.py` — Phase 0 deliberately deferred framework hints + monorepo detection to Phase 1; the deferral is documented in Phase 0 final-design §2.10. This is an *in-place extension of a Phase-0 probe that Phase 0 explicitly scoped to Phase 1*, not an extension-by-addition violation. `[synth — addresses critic §3]`
  3. `src/codegenie/exec.py` — one entry added to `ALLOWED_BINARIES` (`"node"`) gated by a new Phase-1 ADR (`docs/phases/01-context-gather-layer-a-node/ADRs/0001-add-node-to-allowed-binaries.md`). `[B]`
- **No new MCP/sandbox/views/streaming-writer infrastructure.** No `_sandbox.py`, no `views.json`, no `PathIndex` mixin, no msgpack side-channel. `[synth — vetoes [P]'s and [S]'s scope creep]`

---

## Architecture

```
                              codegenie gather <path>
                                        │
                                        ▼
                       ┌────────────────────────────┐
                       │  Phase 0 CLI entry (click) │   ← unchanged
                       │  - tool-readiness now      │
                       │    includes optional node  │
                       └──────────────┬─────────────┘
                                      │
                                      ▼
                       ┌────────────────────────────┐
                       │  Phase 0 Coordinator       │   ← unchanged
                       │  - asyncio.Semaphore       │
                       │  - per-probe asyncio.Task  │
                       │  - cache lookup            │
                       │  - ProbeExecution ∈        │
                       │    {Ran, CacheHit, Skipped}│   ← seam [P+synth]
                       │  - _ProbeOutputValidator   │
                       │  - OutputSanitizer.scrub   │
                       │    (Phase 0 two passes,    │
                       │     unchanged)             │
                       └──────────────┬─────────────┘
                                      │
            ┌─────────────────────────┴───────────────────────────────┐
            │  Phase 0 Probe Registry (explicit import — no entry pts)│
            │                                                         │
            │  language_detection (extended in place; Phase 0 scoped  │
            │                       framework + monorepo to Phase 1)  │
            │                                                         │
            │  ┌──────────────── Phase 1 additions ──────────────┐    │
            │  │  node_build_system    [synth + S caps]          │    │
            │  │  node_manifest        [synth + S caps + B catalog]│  │
            │  │  ci                   [synth + S caps]          │    │
            │  │  deployment           [synth + S caps]          │    │
            │  │  test_inventory       [synth + B file-count]    │    │
            │  └──────────────────────────────────────────────────┘   │
            └─────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                       Phase 0 cache + audit + sanitizer + writer
                                      │
                                      ▼
              .codegenie/context/
              ├── repo-context.yaml        (Phase 0 envelope + 6 slices)
              ├── schema-version.txt
              ├── raw/
              │   ├── language_detection.json
              │   ├── node_build_system.json
              │   ├── node_manifest.json
              │   ├── ci.json
              │   ├── deployment.json
              │   └── test_inventory.json
              └── runs/<utc-iso>-<short>.json

              src/codegenie/catalogs/        ← NEW (data, not code) [B]
                native_modules.yaml          ← NodeManifest reads
                ci_providers.yaml            ← CI reads
                _schema.json                 ← catalog self-validation

              src/codegenie/schema/probes/   ← NEW per-probe sub-schemas [B+S+synth]
                language_detection.schema.json (Phase 0, extended)
                node_build_system.schema.json
                node_manifest.schema.json
                ci.schema.json
                deployment.schema.json
                test_inventory.schema.json
                # Each: additionalProperties: false at the per-probe sub-schema root
```

Three things to read from the diagram:

1. **Every Phase-0 box says "unchanged."** This is the test of extension-by-addition. `[B+all]`
2. **Catalogs are a new sibling directory.** They are *data*, loaded by the probes that consume them. Adding a native module is a YAML PR. `[B — production §2.6]`
3. **Each probe owns exactly one slice and one sub-schema.** No probe writes outside its slice. The envelope `additionalProperties: true` under `probes.*` (Phase 0 §2.9) **is preserved** — the strictness lives in each probe's sub-schema root, not at the envelope level. This is the per-probe sub-schema policy the critic identified as the agreed-upon-but-undocumented position across all three lenses. `[synth — explicitly resolves cross-design observation #1]`

---

## Components

### 1. LanguageDetectionProbe (extended in place)

- **Provenance:** `[B]` (shape, framework + monorepo detection) + `[synth]` (Phase 0 explicitly deferred these to Phase 1).
- **Purpose:** Extend Phase 0's `LanguageDetectionProbe` to populate Node-specific fields from `localv2.md §5.1 A1`: framework hints (NestJS, Express, Fastify, Next.js, Koa, Hapi), monorepo markers (`pnpm-workspace.yaml`, `lerna.json`, `nx.json`, `turbo.json`, `package.json#workspaces`).
- **Interface:** Phase 0 `Probe` ABC unchanged. `declared_inputs` extended to include `package.json` (for framework dep lookup) and the monorepo marker files.
- **Internal design:**
  - Phase 0's `os.scandir` walk + extension counts unchanged.
  - New post-walk pass: read `package.json` via stdlib `json.loads` with a 5 MB size cap and a 64-level depth cap (implemented as a small `parsers.safe_json.load(path, *, max_bytes, max_depth)` helper that lives in `src/codegenie/parsers/safe_json.py` — see Component 8).
  - Framework detection: flat dict lookup of `dependencies + devDependencies` against a small constant set (`{"@nestjs/core": "nestjs", "express": "express", "fastify": "fastify", "next": "next", "koa": "koa", "@hapi/hapi": "hapi"}`).
  - Monorepo detection: `Path.exists()` for the marker files + the `package.json#workspaces` field if present.
- **Why this choice over the alternatives:**
  - Refuses [P]'s `PathIndex` mixin (critic §1.1.1: drifts the frozen ABC).
  - Refuses [P]'s msgpack inter-probe cache (critic §1.1.2: bypasses sanitizer + validator).
  - Refuses [S]'s per-probe sandbox subprocess (critic §2.1.1: brand-new layer Phase 0 never sanctioned).
  - Adopts [B]'s "read `package.json` directly" with [S]'s safe-parse caps (critic §3.6: each probe re-parsing is fine *if* the parse is bounded and cheap; the seam to actually share parsed state lives in Component 2 below).
  - **Extending Phase 0's file in place is licensed by Phase 0 final-design §2.10**, which explicitly defers framework + monorepo detection to Phase 1. The critic flags this as "all three lenses ducked the question"; the synthesizer answers explicitly: this is the one extension-in-place that Phase 0 sanctioned.
- **Tradeoffs accepted:**
  - Two Layer A probes (`language_detection` and `node_manifest`) parse `package.json` independently. Mitigated by the parsed-`package.json` in-coordinator memo (Component 2) so the *second* parse on the same gather is free.
  - Framework detection is shallow (decorator-level AST analysis is Phase 2's `NodeReflectionProbe`'s problem).

### 2. ParsedManifestMemo — in-coordinator parse memo

- **Provenance:** `[synth]` — addresses critic's cross-design observation #3 ("All three accept reading `package.json` more than once per gather; none uses the cheapest, cleanest seam").
- **Purpose:** Avoid the warm-path cost of two or three Layer A probes parsing the same `package.json` on the same gather, without (a) [P]'s msgpack side-channel that bypasses the sanitizer or (b) [B]'s "violates DRY by a small margin" double-parse.
- **Interface:** A typed read-through cache *inside* the coordinator's per-gather context. Probes access it via a single function `ctx.parsed_manifest(path: Path) -> dict[str, JSONValue] | None` exposed on `ProbeContext`. The function is provided by the coordinator at probe-dispatch time; first call parses (with caps), subsequent calls return the same in-memory dict.
- **Internal design:**
  - The memo is keyed by `(absolute_path, mtime_ns, size)` on the coordinator side. If the file changed between probe dispatches (shouldn't happen during a single gather, but TOCTOU-safe), the memo re-parses.
  - The memo only memoizes files inside `repo_root` and only those matching a small allowlist (`{"package.json"}` in Phase 1; extendable in Phase 2).
  - Parsed dicts are **read-only views** (`types.MappingProxyType` at the top level; nested dicts/lists are returned by reference — the contract is "don't mutate," enforced by mypy via `Mapping` typing). Probes mutating returned data is a typed error at lint time.
  - **The memo is per-gather, not per-process.** It lives on the coordinator's per-run state and is discarded after the gather. Phase 9's Temporal lift will not see it; each Activity re-parses (which is correct — Activities are independent units of work).
- **Why this choice over the alternatives:**
  - Refuses [P]'s msgpack-of-parsed-package.json (critic §1.1.2: bypasses validator and sanitizer, treated as a "contract violation by side channel"). The memo here is *inside* the coordinator, never written to disk, never persisted across gathers.
  - Refuses [B]'s "each probe parses independently" (critic §3.6: 3× parse cost on the cache-miss path for zero isolation benefit, since each probe's `declared_inputs` already includes `package.json`).
  - Refuses [S]'s implicit "each sandbox subprocess re-parses" (critic §2.1.2: 1.5 s of pure fork overhead the design admits to).
- **Tradeoffs accepted:**
  - The memo is a small extension to `ProbeContext` (Phase 0 dataclass), specifically the addition of an optional `parsed_manifest: Callable[[Path], dict | None]` field. This **does** touch a Phase 0 dataclass — but the contract addition is *optional* (`= None` default), the function is only present when the coordinator provides it, and probes that don't use it are unaffected. **This is the one Phase 0 dataclass extension Phase 1 makes; it requires a Phase-1 ADR** (`docs/phases/01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md`).
  - Probes must defensive-check `ctx.parsed_manifest is not None` and fall back to direct parsing. This is one if-statement per probe; mypy enforces it.

### 3. NodeBuildSystemProbe

- **Provenance:** `[B]` (shape, lockfile precedence, no script evaluation) + `[S]` (in-process caps, no Helm rendering, no node_modules parsing) + `[synth]` (`node --version` cross-check is **on by default but optional**, resolving the conflict).
- **Purpose:** Populate the `build_system` slice from `localv2.md §5.1 A2`. Determines package manager, engine constraints, npm scripts, bundler, TypeScript compilation setup.
- **Interface:** Standard probe ABC. `name = "node_build_system"`, `layer = "A"`, `applies_to_languages = ["javascript", "typescript"]`, `applies_to_tasks = ["*"]`, `requires = ["language_detection"]`, `timeout_seconds = 30`, `declared_inputs = ["package.json", "pnpm-workspace.yaml", "lerna.json", "nx.json", "turbo.json", ".nvmrc", ".node-version", ".tool-versions", "tsconfig.json", "tsconfig.*.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb"]`.
- **Internal design:**
  - **Package-manager resolution by lockfile precedence:** `bun.lockb` > `pnpm-lock.yaml` > `yarn.lock` > `package-lock.json` (existence check, no parse). Multiple lockfiles drop `confidence` to `low` and emit a typed warning.
  - **`package.json` parsing** via `ctx.parsed_manifest(repo_root / "package.json")` — uses the memo from Component 2; falls back to direct `safe_json.load(...)` if memo is absent.
  - **`tsconfig.json`** parsed via `src/codegenie/parsers/jsonc.py` — a stdlib-only line-comment + block-comment stripper followed by `safe_json.load`. **`json5` is rejected** (`[synth]` — critic §1.1.6: each new C-extension dep is a CVE feed; we have stdlib `json` + ~30 lines of comment-strip). `tsconfig.json#extends` chain followed at most 4 levels deep, only to paths under `repo_root`; cycles or escapes raise typed warnings and downgrade confidence. `[S]`
  - **Node version:** read `package.json#engines.node`, `.nvmrc`, `.node-version`, `.tool-versions` in declared precedence. Each is a small string read.
  - **`node --version` cross-check:** **optional, on by default.** If `node` is in `ALLOWED_BINARIES` and on `$PATH`, call `node --version` via `exec.run_allowlisted(["node", "--version"], cwd=repo_root, timeout_s=5)`. The probe records both the declared constraint and the locally-resolved version; **disagreement is a warning, not an error**, and confidence stays `high` because the constraint is the load-bearing fact. The `node` binary addition to `ALLOWED_BINARIES` is gated by `docs/phases/01-context-gather-layer-a-node/ADRs/0001-add-node-to-allowed-binaries.md`. `[B + localv2.md §5.1 A2 — overrides [S]'s veto per Phase 0 conformance rule]`
  - **Bundler detection:** flat data lookup against `dependencies + devDependencies` (`webpack`, `rollup`, `esbuild`, `vite`, `parcel`, `turbopack`) plus config-file presence (`webpack.config.{js,ts,mjs,cjs}`, `vite.config.{js,ts,mjs,cjs}`, etc.).
  - **Scripts:** read `package.json#scripts` and record verbatim — no evaluation, no interpretation.
- **Why this choice over the alternatives:**
  - The `node --version` decision is the security/best-practices conflict (table row 2). Resolution: `localv2.md §5.1 A2` explicitly specifies the cross-check; Phase 0 §2.3 makes `localv2.md` the source of truth. [S]'s threat (a hostile `$PATH` shim) is mitigated by the existing `exec.run_allowlisted` env-strip (Phase 0 §2.5), short timeout (5 s), no-shell execution, and the fact that the value is only used as a *display field*, never as a control-flow input. **The decision is recorded in a Phase-1 ADR; the security concern is documented but the [S] veto is overridden** per the Rule 11 conformance principle the critic himself invokes.
- **Tradeoffs accepted:**
  - Adds one binary to `ALLOWED_BINARIES`. ADR-gated; future entries follow the same workflow.
  - `tsconfig.json` is parsed by a hand-rolled comment stripper (~30 lines, fuzz-tested in `tests/adv/test_tsconfig_pathological.py`). Far cheaper than adding `json5` as a C-extension dep.

### 4. NodeManifestProbe

- **Provenance:** `[B]` (shape, lockfile-not-node_modules, hand-curated catalog) + `[S]` (in-process size+depth caps, no `npm ls`, no `node_modules/*/package.json` parsing by default) + `[synth]` (yarn-lock library choice).
- **Purpose:** Populate `manifests` from `localv2.md §5.1 A3`. The single most distroless-relevant Layer A probe — native module enumeration is the largest source of distroless migration failures.
- **Interface:** Standard probe ABC. `name = "node_manifest"`, `layer = "A"`, `applies_to_languages = ["javascript", "typescript"]`, `applies_to_tasks = ["*"]`, `requires = ["language_detection"]`, `timeout_seconds = 30`, `declared_inputs = ["package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock", "src/codegenie/catalogs/native_modules.yaml"]`. **`node_modules/*/package.json` is NOT in `declared_inputs`.** `[S]`
- **Internal design:**
  - **`package.json` parse:** via `ctx.parsed_manifest` (memo) with 5 MB size cap + 64 depth cap.
  - **Lockfile parsers — three small helpers**, each in `src/codegenie/probes/_lockfiles/`:
    - `_pnpm.py` — `yaml.CSafeLoader` (banned via Phase 0 forbidden-patterns to use anything else), 50 MB size cap, 64 depth cap.
    - `_npm.py` — `safe_json.load`, 50 MB size cap, 64 depth cap.
    - `_yarn.py` — **`pyarn` PyPI library if it's maintained (< 18 months since last release) at Phase-1 implementation time, otherwise a ~100-line hand-rolled line-scanner with no regex backtracking.** `[B + S agreement — refuses [P]'s "ship hand-rolled by default" for ~16 ms of average latency that critic §1.1.4 dismantles]`. The decision is recorded in a Phase-1 ADR (`docs/phases/01-context-gather-layer-a-node/ADRs/0003-yarn-lock-parser-choice.md`) at land-time.
  - **Native module catalog:** `src/codegenie/catalogs/native_modules.yaml`, hand-curated, ships with `bcrypt`, `sharp`, `better-sqlite3`, `node-canvas`, `node-rdkafka`, `node-pty`, `bufferutil`, `utf-8-validate`, `argon2`, `keytar`. Each entry: `{name, requires_node_gyp, system_deps_required, binary_artifacts_glob, notes, catalog_entry_version: int}`. Catalog itself versioned via `catalog_version: int` field at file top — included in cache key so catalog updates invalidate cached `NodeManifest` outputs. `[B + synth — resolves [B] Open Question #7]`
  - **No `npm ls` / `pnpm list` / Helm-style template rendering.** Lockfile is the deterministic source. `[B+S]`
  - **`engines`, `optionalDependencies`, `bundledDependencies`** read from the parsed `package.json`.
- **Why this choice over the alternatives:**
  - Refuses [P]'s hand-rolled `yarn.lock` parser by default — critic §1.1.4 establishes the 16 ms of *average* latency win does not justify a 1k-LOC maintenance liability. Hand-rolled is the **fallback** if `pyarn` is unmaintained, not the default.
  - Refuses [P]'s `ruamel.yaml` C-extension dep (critic §1.1.6) — `yaml.CSafeLoader` is the Phase 0 ratified parser and is sufficient.
  - Refuses [S]'s `node_modules/*/package.json` parsing as opt-in feature in Phase 1 — the threat model (attacker-controlled bytes at scale) is real and Phase 1 has no consumer that requires it. Deferred to Phase 2.
- **Tradeoffs accepted:**
  - Native module catalog gaps surface in Phase 7. Mitigation: an `import-linter`-style test ensures each new probe in Phase 2+ ships its own catalog additions if applicable; catalog versioning means a Phase-7 catalog update invalidates Phase-1 cached outputs cleanly. The critic's concern (silent staleness, blast-radius five phases out) is **acknowledged as a real risk** and explicitly logged as a Phase 7 testing precondition.
  - Three lockfile parser files (~150 LOC each) is more code than [P]'s msgpack short-circuit. Acceptable trade for the cache contract.

### 5. CIProbe

- **Provenance:** `[B]` (shape, multi-provider catalog, GitHub Actions parser depth) + `[S]` (`yaml.CSafeLoader` mandatory, Jenkinsfile by regex only, secrets references recorded literally not resolved) + `[synth]` (singleton vs list — singleton with `additional_providers` list).
- **Purpose:** Populate `ci` from `localv2.md §5.1 A4`. Records CI provider, image-build presence, test/lint commands.
- **Interface:** Standard probe ABC. `name = "ci"`, `layer = "A"`, `applies_to_languages = ["*"]`, `applies_to_tasks = ["*"]`, `requires = []`, `timeout_seconds = 10`, `declared_inputs = [".github/workflows/*.yml", ".github/workflows/*.yaml", ".gitlab-ci.yml", ".circleci/config.yml", "Jenkinsfile", "azure-pipelines.yml", "src/codegenie/catalogs/ci_providers.yaml"]`.
- **Internal design:**
  - **Provider catalog** (`ci_providers.yaml`): each entry `{name, marker_paths: [...], parser: <name>}`. First matching entry wins as the `provider`; any **other** matching providers go into a new `additional_providers: list[str]` field. This resolves [B]'s "emit a list" vs `localv2.md §5.1 A4`'s "singleton" tension without violating Phase 0 conformance — `provider` stays a singleton string, `additional_providers` is purely additive. The Phase 1 sub-schema declares both. `[synth — addresses critic §3.4 directly]`
  - **GitHub Actions parser:** `yaml.CSafeLoader` per workflow file (all workflows, not just the primary — [P]'s "skip non-primary" is rejected per critic §1.1.4 since it leaves us blind to multi-workflow setups). 10 MB cap per file, 64 depth cap. Extracts job names, step `run:` commands, looks for `docker build`, `docker buildx`, `docker/build-push-action` → `builds_image: true`. Test/lint commands extracted by simple substring match against `{"npm run test", "pnpm test", "yarn test", "npm test", "pnpm run test", "yarn run test", "vitest", "jest", "playwright test"}`.
  - **GitHub Actions secret references** (`${{ secrets.* }}`) recorded as **literal strings** with a `references_secrets: list[str]` field listing referenced secret names. Secret values are never accessible, so this is record-not-resolve. `[S]`
  - **GitLab CI parser:** same `yaml.CSafeLoader`.
  - **Jenkinsfile:** presence + size + a bounded regex extraction for `sh '...'` and `sh "..."` patterns (single capture group, line-bounded). `confidence: low`, explicit warning. `[B+S]`
  - **CircleCI / Azure Pipelines:** stub recognizers (presence only, `confidence: low`); fuller parsers land when a consumer demands.
- **Why this choice over the alternatives:**
  - Refuses [P]'s "skip non-primary workflow" optimization — critic §1.1.4 establishes the gain (~50 ms per gather) is not worth the coverage loss.
  - Refuses [S]'s implicit "Jenkinsfile parsed by path only" — the bounded regex for `sh '...'` is a small win at zero risk surface (no eval, no backtracking).
  - The singleton-vs-list disagreement is resolved by **adding an additive field** rather than mutating the existing `provider` shape — this honors both `localv2.md §5.1 A4` and the multi-provider reality.
- **Tradeoffs accepted:**
  - Multi-provider repos report `confidence: low` plus an `additional_providers` list. The schema enforces shape; the planner's interpretation is downstream.
  - We do not execute or simulate CI.

### 6. DeploymentProbe

- **Provenance:** `[B]` (shape, no Helm/Kustomize rendering, multi-env Helm as list) + `[S]` (in-process caps, no Helm/Terraform binary invocation, kustomize-traversal cap, path-traversal refusal on `kustomization.yaml#resources:` outside repo root).
- **Purpose:** Populate `deployment` from `localv2.md §5.1 A5`. Records deployment type, image reference path, security context, ports, env vars.
- **Interface:** Standard probe ABC. `name = "deployment"`, `layer = "A"`, `applies_to_languages = ["*"]`, `applies_to_tasks = ["*"]`, `requires = []`, `timeout_seconds = 15`, `declared_inputs = ["deploy/**/*.yaml", "deploy/**/*.yml", "k8s/**/*.yaml", "k8s/**/*.yml", "kubernetes/**/*.yaml", "Chart.yaml", "values.yaml", "values-*.yaml", "kustomization.yaml", "kustomization.yml", "helm/**/*", "charts/**/*", "*.tf"]`.
- **Internal design:**
  - **Type detection by file marker:** `Chart.yaml` → Helm; `kustomization.yaml` → Kustomize; raw `kind: Deployment` YAML → raw; `*.tf` → Terraform.
  - **Helm:** parse `Chart.yaml` + `values*.yaml` with `yaml.CSafeLoader` (10 MB cap each, depth 64). Record the image reference *path* (e.g., `image.repository`) and the value at that path. **Multi-environment Helm** (`values-prod.yaml`, `values-staging.yaml`) recorded as a `environments: list[{name, image_reference, ...}]` field; the primary `image_reference` field stays nullable for the single-env case. **No Helm template rendering** — that's a Planner-time decision in Phase 3+. `[B+S]`
  - **Kustomize:** parse `kustomization.yaml`. Resources list followed one level deep. **Paths in `resources:` that resolve outside `repo_root` are rejected with a `kustomization_resource_path_outside_repo: true` warning** (zip-slip mitigation, `[S]`). Overlay traversal capped at depth 5 and 50 total files.
  - **Raw manifests:** `yaml.CSafeLoader` `safe_load_all` (multi-document). Filter to `kind ∈ {Deployment, StatefulSet, DaemonSet, Pod}`. Extract `spec.template.spec.containers[].image`, `securityContext`, `ports`, `env`, `envFrom`.
  - **Terraform:** `*.tf` files enumerated by path only; no parsing in Phase 1. **`python-hcl2` is NOT added** to deps (`[S]` — historic CVEs; defer to Phase 2 with a richer parser). Slice records `terraform_present: true, terraform_files: list[relative_path]`. `confidence: low` if Terraform is detected and no other deployment type is.
- **Why this choice over the alternatives:**
  - Refuses [P]'s "streaming YAML parse for one key" — fragile (key ordering, anchors), zero meaningful win on 10 MB caps.
  - Adopts [S]'s no-`hcl2` stance; defers to Phase 2.
  - Multi-env-as-list resolves [B] Risk #2 directly: the sub-schema declares the shape, the envelope validation catches drift.
- **Tradeoffs accepted:**
  - Terraform-heavy repos get a `confidence: low` slice with paths-only enumeration. Phase 2 closes when an actual consumer demands.
  - We do not render Helm or Kustomize — by design.

### 7. TestInventoryProbe

- **Provenance:** `[B]` (shape, file count not test count, framework detection from deps) + `[S]` (lcov.info parse caps, test files not parsed — only enumerated).
- **Purpose:** Populate `test_inventory` from `localv2.md §5.1 A6`. Records test framework, test-file count, command paths, coverage data presence.
- **Interface:** Standard probe ABC. `name = "test_inventory"`, `layer = "A"`, `applies_to_languages = ["javascript", "typescript"]`, `applies_to_tasks = ["*"]`, `requires = ["language_detection", "node_build_system"]`, `timeout_seconds = 10`, `declared_inputs = ["package.json", "vitest.config.*", "jest.config.*", "playwright.config.*", ".mocharc.*", "test/**/*.test.*", "tests/**/*.test.*", "src/**/*.test.*", "**/*.spec.*", "coverage/lcov.info", "scripts/smoke.*", "tests/smoke/**/*"]`.
- **Internal design:**
  - **Framework detection:** dict lookup against `dependencies + devDependencies` (via `ctx.parsed_manifest`) for `vitest`, `jest`, `mocha`, `tap`, `@playwright/test`, `cypress`. `node:test` reported if `package.json#engines.node >= 18` and no other framework is declared.
  - **Test-file count:** single `os.walk` with Phase 0 noise-dir exclusions (`node_modules`, `dist`, `build`, `coverage`, `.next`, `.turbo`, `.git`). Match against `*.test.{js,ts,jsx,tsx,mjs,cjs}` and `*.spec.{js,ts,jsx,tsx,mjs,cjs}`. Field: `unit_test_file_count: int`, with `unit_test_count_is_file_count: true` boolean to signal the limitation. `[B+P agreement on counting files; [S] also agrees]`
  - **Command extraction:** read `package.json#scripts` for entries named `test`, `test:unit`, `test:integration`, `test:smoke`, `test:e2e`, `test:coverage`. Record verbatim.
  - **Smoke script presence:** `Path.exists()` for `scripts/smoke.{sh,js,ts}` and `tests/smoke/`.
  - **Coverage data:** if `coverage/lcov.info` exists, parse summary only (totals: lines, functions, branches hit/found) via a small line-scanner (~40 LOC, no regex backtracking, 50 MB cap). The file format is unambiguous; no external lib needed.
- **Why this choice over the alternatives:**
  - Refuses [B]'s `lcov-parser` PyPI dep — the lcov format is simple enough that 40 lines of stdlib is the right size.
  - Files-not-cases is the [P+B+S] convergence the critic flagged as "accidental agreement" — making it explicit closes that gap.
- **Tradeoffs accepted:**
  - File count not test-case count. Dynamic test generation (`describe.each`, `test.each`) is invisible. Signal-not-truth; the planner consumes this as a coarse indicator.

### 8. Safe-parse helpers — `codegenie/parsers/`

- **Provenance:** `[S]` (caps); `[synth]` (placement — one shared helper module, no per-probe duplication).
- **Purpose:** Centralize the in-process parse-with-caps idiom so every probe uses the same bounded parsers. **Without this, each probe re-implements size+depth checks slightly differently, and the security goal degrades to "mostly enforced."**
- **Interface:**
  - `src/codegenie/parsers/safe_json.py`: `def load(path: Path, *, max_bytes: int, max_depth: int = 64) -> dict[str, JSONValue]`. Reads the file once with `O_NOFOLLOW`, size-checked before parse. Uses stdlib `json.loads` with a small post-parse depth-walker (the C scanner has no native depth cap, so the walk is a stdlib-only second pass; bounded by `max_depth`). Raises typed `SizeCapExceeded` / `DepthCapExceeded` / `MalformedJSONError`.
  - `src/codegenie/parsers/safe_yaml.py`: same shape, wrapping `yaml.CSafeLoader` (the Phase 0 ratified loader; Phase 0 `forbidden-patterns` continues to ban `yaml.load`). Depth check after parse; size cap before.
  - `src/codegenie/parsers/jsonc.py`: stdlib-only line-comment + block-comment stripper, then `safe_json.load`. Pathological inputs (unterminated block comments, deeply nested comment levels) fuzz-tested in `tests/adv/test_tsconfig_pathological.py`.
- **Why this choice over the alternatives:**
  - Refuses [S]'s per-probe fork+exec sandbox (critic §2.1.1: ABC bypass, not extension-by-addition; ~1.5 s overhead per cold gather). In-process caps catch ~95% of the threat model (YAML bombs, JSON bombs, depth-DoS, oversized inputs) at ~0 ms of overhead per parse.
  - Refuses [P]'s `orjson`/`pyjson5`/`ruamel.yaml` C-extension drift (critic §1.1.6).
- **Tradeoffs accepted:**
  - **In-process caps do not protect against parser-CVE exploits** that bypass the depth check inside the C extension. Mitigation: Phase 0's `pip-audit` + `osv-scanner` + Dependabot on `pyyaml`/cpython watch this; rlimits at the OS level (Phase 14's production worker) are the future defense. The [S] design's claim that "sandbox catches the remaining 20% (parser CVEs)" is acknowledged; in Phase 1 we accept the 20% in exchange for not violating the Phase 0 ABC. **This is the explicit risk; recorded under "Risks" below.**
  - Two passes (size→parse→depth-walk) is ~5% slower than a hypothetical depth-aware parser. Acceptable.

### 9. Per-probe sub-schemas — strictness at the boundary

- **Provenance:** `[B]` (each probe owns one sub-schema file) + `[S]` (`additionalProperties: false` at sub-schema root) + `[synth]` (resolution of Phase 0 §2.9 layered policy).
- **Purpose:** The schema chokepoint where a typo in a Phase-1 probe's output is rejected at land-time, not at downstream-consumer time.
- **Interface:** Five new JSON files at `src/codegenie/schema/probes/`:
  - `node_build_system.schema.json`
  - `node_manifest.schema.json`
  - `ci.schema.json`
  - `deployment.schema.json`
  - `test_inventory.schema.json`
  - Plus an extension to the existing `language_detection.schema.json`.
- **Internal design:**
  - Each sub-schema has `additionalProperties: false` at its **own root**. The Phase 0 envelope keeps `additionalProperties: true` under `probes.*` (Phase 0 §2.9, conflict-table row 4 winner). The strictness lives **per-probe**, not globally. This is exactly the position the critic identifies as agreed across all three lenses but un-documented; the synthesizer documents it here.
  - Sub-schemas are referenced from the envelope by `$ref` to relative path.
  - Each sub-schema declares required + optional fields with types. Optional fields use `null` for not-present, not field-absence (this lets the schema's `additionalProperties: false` mean what it says).
  - Adding a field is a code change + schema change in the same PR — the friction is the point.
- **Why this choice over the alternatives:**
  - Refuses [S]'s sanitizer third-pass (critic §2.2.5: edits a frozen Phase-0 chokepoint without ADR amendment). The per-sub-schema policy gets the same effect — schema slice that doesn't conform is rejected — at the *validator* boundary, which Phase 0 §2.9 already shaped for layering.
  - Refuses [P]'s implicit "size cap as system invariant" — Phase 0's `OutputSanitizer` has two passes; we don't add a third.
- **Tradeoffs accepted:**
  - A future probe wanting to emit a forward-compat field (e.g., `prompt_injection_marker_count` from [S] Goal #6) must amend its sub-schema in the same PR. This is correct: per-probe sub-schemas are *the* extension hook.

### 10. Catalog loader

- **Provenance:** `[B]` verbatim.
- **Purpose:** Load `native_modules.yaml` and `ci_providers.yaml` once at module import, expose as immutable mappings, self-validate.
- **Interface:** `src/codegenie/catalogs/__init__.py` exports `NATIVE_MODULES: Mapping[str, NativeModuleEntry]` and `CI_PROVIDERS: Mapping[str, CIProviderEntry]`. Entry types are `NamedTuple`s. Catalogs themselves self-validated against `_schema.json` at import.
- **Internal design:** `yaml.safe_load` (banned-without-Loader by Phase 0 forbidden-patterns; we use `yaml.CSafeLoader` via `safe_yaml.load`). `types.MappingProxyType` for freezing. **Fail-loud at CLI startup** if the catalog YAML is malformed or fails self-schema. `[B+all]`
- **Tradeoffs accepted:** ~5 ms import-time cost. Worth it for the conventional shape.

### 11. Cache key — Phase 0 unchanged

- **Provenance:** `[B]` (no change) + `[synth]` (explicit refusal of [S]'s byte-content rewrite).
- **Decision:** The Phase 0 cache key derivation (`SHA-256(probe_name | probe_version | schema_version | inputs_hash_hex)` where `inputs_hash = BLAKE3` over sorted `(path, size)` tuples of files matching `declared_inputs` after exclusion) **is preserved verbatim**. The native module catalog version (`catalog_version` field) participates by being listed in `NodeManifestProbe.declared_inputs` (the catalog YAML is hashed like any other declared input).
- **Why not [S]'s byte-content cache key:** Critic §2.2.3 establishes that this reverses an explicit Phase 0 decision (conflict-table row 14 in Phase 0 final-design) without writing an ADR amendment. The [S] motivation (cache poisoning resistance via attacker-controlled lockfile of same size) is real but is exactly the threat Phase 14's webhook-driven gather creates; Phase 14 redesigns the multi-actor key story (Phase 0 §2.7 commits to revisiting then). Phase 1 inherits Phase 0's choice; the future change is scoped where it belongs.
- **Why not [P]'s PathIndex fingerprint:** Critic §1.1.3 establishes the same governance issue. The PathIndex is also a new class hierarchy the Phase 0 ABC doesn't anticipate.
- **Tradeoffs accepted:** A cache-poisoning attacker who can write to the analyzed repo's `package.json` *and* preserve its size *and* hit the same SHA-256 identity is theoretically possible but vanishingly unlikely under BLAKE3 over `(path, size)` — and the threat model assumes attacker doesn't have write access to the analyzed repo at gather time. **Recorded as risk #4 below.**

---

## Data flow

A representative warm-path run on a real Node.js repo (~1k files, TypeScript, pnpm, GitHub Actions, Helm) where `package.json` changed since last gather:

1. **CLI entry** (Phase 0, unchanged). Path validated, tool-readiness check includes optional `node`.
2. **`RepoSnapshot` construction** (Phase 0, unchanged). `git rev-parse HEAD`. After `LanguageDetectionProbe` finishes, `detected_languages` is populated and the snapshot is frozen for the rest of the gather.
3. **Probe registry filter** (Phase 0, unchanged). Returns six probes for a TypeScript repo: `language_detection`, `node_build_system`, `node_manifest`, `ci`, `deployment`, `test_inventory`. Topological order via `requires`: `language_detection` → wave 2 = `{node_build_system, node_manifest, ci, deployment, test_inventory}` (last two have `requires=[]` but the planner emits them in the same wave).
4. **Coordinator dispatch** (Phase 0, unchanged + `ParsedManifestMemo` provided on `ProbeContext`). One `asyncio.Task` per probe, bounded by `Semaphore(min(cpu_count(), 8))`.
5. **Per-probe cache lookup** (Phase 0, unchanged). For each probe, compute `cache_key = identity_hash(name, version, schema_version, content_hash(declared_inputs))`. `package.json` changed → `language_detection`, `node_build_system`, `node_manifest`, `test_inventory` miss; `ci`, `deployment` hit (their `declared_inputs` did not change).
6. **`language_detection` runs first** (Phase 0 + Phase 1 framework + monorepo extension). ~80 ms p50: scandir walk (50 ms) + `safe_json.load(package.json)` (5 ms, with 5 MB + 64-depth cap) + framework + monorepo classification (5 ms). Parsed `package.json` is now in the memo for the rest of the gather.
7. **Wave 2 dispatches** (Phase 0). `node_build_system`, `node_manifest`, `test_inventory` each call `ctx.parsed_manifest(repo_root / "package.json")` — second call returns the memoized dict, no re-parse. Lockfile parse (`pnpm-lock.yaml`, ~250 ms p50) dominates `node_manifest`. `tsconfig.json` parsed via `jsonc.py` (5 ms). `ci` and `deployment` are LRU/cache hits and skip execution entirely.
8. **Per-probe ProbeOutput** flows through `_ProbeOutputValidator` (Pydantic, JSONValue recursive type, field-name regex) — Phase 0 boundary. Field names like `package_manager`, `native_modules`, `image_reference`, `framework`, `references_secrets`, `additional_providers` — none trip the secret-name regex.
9. **OutputSanitizer.scrub** (Phase 0, two passes unchanged). Absolute paths in lockfile entries (e.g., `binary_artifacts: ["/Users/me/work/.../node_modules/sharp/build/..."]`) get scrubbed to relative. **Load-bearing for Phase 11.**
10. **Cache write** (Phase 0). Each `ProbeOutput` blob written. Index appended.
11. **Output merge + schema validation** (Phase 0 + Phase 1 sub-schemas). Each probe's slice merged; envelope `additionalProperties: false` at root, `true` under `probes.*`, per-probe sub-schema `additionalProperties: false` at its own root catches any typo'd field. `[synth]`
12. **Raw artifacts** written to `.codegenie/context/raw/<probe>.json` (Phase 0). Lockfile dump, parsed Helm values, parsed CI workflow.
13. **YAML write** (Phase 0). Atomic `.tmp` → `os.replace`. `CSafeDumper`, 0600.
14. **Audit record** (Phase 0). Per-probe execution path (`Ran` / `CacheHit` / `Skipped`) — the seam Phase 14 needs.
15. **Exit 0.**

**Second run, no changes:** All six probes hit cache. Coordinator records `CacheHit` for each. No `package.json` parse (memo never populated; nothing to parse). YAML re-written from cached slices. Wall-clock target: p50 ≤ 0.4 s.

---

## Failure modes & recovery

| Failure | Detected by | Containment | Recovery | Source |
|---|---|---|---|---|
| `NodeManifest` lockfile parse error | `_pnpm`/`_npm`/`_yarn` parser raises typed error | Caught by probe `run()`; `ProbeOutput(confidence="low", errors=[...])` | Coordinator continues with degraded slice; planner sees `confidence: low` | `[B]` |
| Lockfile exceeds 50 MB cap | `safe_yaml.load` / `safe_json.load` raises `SizeCapExceeded` | Same as above | Probe failed; gather continues | `[S]` |
| YAML billion-laughs in `pnpm-lock.yaml` | `safe_yaml.load` depth-walker raises `DepthCapExceeded` | Probe-level catch | `confidence: low`, gather continues. **Test fixture exists.** | `[S]` |
| JSON bomb in `package.json` (1 GB string, deep nesting) | `safe_json.load` size cap or `DepthCapExceeded` | Probe-level catch | Same | `[S]` |
| Native module catalog malformed | `CatalogLoadError` at module import | **Hard fail at CLI startup** with path | Operator fixes catalog | `[B]` |
| Path traversal in `kustomization.yaml#resources` | `DeploymentProbe` resolves relative to `repo_root` and refuses if escapes | Path skipped, warning emitted | Probe continues with the rest; slice has `kustomization_resource_path_outside_repo: true` | `[S]` |
| Symlink in `declared_inputs` outside repo | Phase 0 walker (unchanged) | Skipped + logged | Probe sees no file; cache key derivation skips | `[S+P0]` |
| `tsconfig.json#extends` chain exceeds 4 levels | `NodeBuildSystem` internal counter | Probe-level catch | `confidence: medium`, `warnings: ["tsconfig.extends_depth_exceeded"]` | `[S]` |
| `node --version` subprocess fails (binary absent, exec error, timeout) | `exec.run_allowlisted` raises | Probe catches | `node_version_resolved_locally: null`, **confidence unaffected** (constraint is load-bearing) | `[B]` |
| `pyarn` not installed at runtime (decided-to-fall-back path) | `ImportError` at probe module import | `NodeManifest` falls back to hand-rolled yarn-lock parser | Gather continues with `confidence: medium` if hand-rolled returns empty, else `high` | `[synth]` |
| Probe exceeds `timeout_seconds` | Phase 0 coordinator (`asyncio.wait_for`) | Cancel + SIGKILL at `1.5 × timeout_s` | `ProbeOutput(errors=["timeout"], confidence="low")` | `[P0]` |
| Probe slice fails its per-probe sub-schema | `Draft202012Validator` at envelope merge time | YAML written with `.invalid` suffix; CLI exits 3 | Operator inspects diff vs sub-schema | `[B+P0]` |
| Multi-environment Helm: probe emits list when consumer expects scalar | Per-probe sub-schema declares both `image_reference` and `environments: list` shapes | Schema accepts; downstream contract test verifies consumer handles list | Documentation + planner-side handling | `[B+synth]` |
| `LanguageDetection` reports a non-Node repo | Phase 0 `for_task` filter | Five Node-only probes are filtered out; their sub-schemas declare slices as **optional** (not required) at the envelope | YAML envelope omits the Node slices; schema validates | `[synth — addresses [B] blind spot]` |
| ParsedManifestMemo function not provided by coordinator (test path, old wiring) | Each probe defensive-checks | Falls back to direct `safe_json.load` | Same correctness, 3× parse cost on warm path — surfaced in CI canary | `[synth]` |
| `package.json` is a symlink pointing outside repo | `O_NOFOLLOW` open in `safe_json.load` | Open fails with `ELOOP` | Probe records `confidence: low`, `errors: ["symlink_skipped: package.json"]` | `[S]` |

The pattern: **deterministic facts about messy reality, explicit confidence, never silent degradation.** Hard-fails are reserved for load-bearing-invariant violations (catalog corruption, schema sub-schema malformed) per Rule 12.

---

## Resource & cost profile

- **Tokens per run:** 0. Phase 0 `fence` job continues to assert. `[all]`
- **Wall-clock per `codegenie gather` on the 1k-file fixture (M-series Mac, p50 / p95):**
  - Cold (all cache miss): 4 s / 8 s. Dominated by `node_manifest` lockfile parse (~250 ms p50) and `test_inventory` walk (~120 ms p50). `[B]`
  - Warm (all cache hits): 0.4 s / 1 s. Dominated by sanitizer + schema validation + YAML write. `[B+P]`
  - Incremental (`package.json` changed, 4 misses / 2 hits): 1 s / 2 s. `[synth]`
- **Memory (RSS):** ~90 MB peak on a 1k-file repo. ~70 MB idle (Phase 0 baseline). `[B+P0]`
- **Storage per gather:** `repo-context.yaml` ~30 KB; `raw/` ~300 KB (lockfile dump dominates); cache blobs ~50 KB; audit ~5 KB. ~0.4 MB per gather. `[B]`
- **CI walltime delta vs Phase 0:** +25 s p50, +45 s p95. Phase 0 90 s p95 advisory target now slips to ~120 s p95 — surfaced as a dashboard metric, not a gate (Phase 0 §3.2 set the budget as advisory). The slip is documented in the Phase 1 risk register. `[B+synth — softer than [S]'s implicit overrun]`
- **External-dep additions:** `pyarn` (yarn-lock parser, conditional on maintenance status at land-time; otherwise hand-rolled fallback) and **nothing else**. No `orjson`, `pyjson5`, `ruamel.yaml`, `msgpack`, `hcl2`, `python-hcl2`, `lcov-parser`. `[synth — strict refusal of [P]'s extras and [B]'s `lcov-parser`]`

---

## Test plan

The test pyramid is wider at the unit base than the integration top. Each probe is unit-tested exhaustively against fixture inputs *before* the integration test cares whether they compose correctly. Adversarial fixtures land in `tests/adv/` and are CI-gating per Phase 0's adv-tests convention.

### Unit tests (`tests/unit/probes/`)

| Test module | Asserts | Source |
|---|---|---|
| `test_language_detection.py` (extends Phase 0) | New: framework detection from deps; monorepo markers; confidence reporting on weak signals. | `[B]` |
| `test_node_build_system.py` | Lockfile-precedence selection; multi-lockfile drops confidence; `engines.node` precedence; `tsconfig.json` with comments; bundler detection; malformed `package.json` → `confidence: low`; `node --version` cross-check happy + disagreement + absent paths. | `[B+synth]` |
| `test_node_manifest.py` | Each lockfile parser on a format-specific fixture; native-module detection (one fixture per cataloged module); `optionalDependencies` + `bundledDependencies` counting; cache-key stability across runs; **catalog-version invalidates cache**. | `[B+synth]` |
| `test_ci.py` | GitHub Actions parser (build, no-build, matrix); GitLab CI; Jenkinsfile regex extraction; multi-provider repo (`provider` + `additional_providers`); absent CI directory. | `[B+S]` |
| `test_deployment.py` | Helm `Chart.yaml` + `values.yaml`; multi-env Helm (`values-prod.yaml` + `values-staging.yaml`); Kustomize; raw Deployment; raw Pod skipped; multi-env list emission; Terraform paths-only. | `[B+S]` |
| `test_test_inventory.py` | Vitest, Jest, Mocha, Tap, node:test, Playwright, Cypress detection; file count walk honors exclusions; `package.json#scripts` extraction; smoke-script presence; coverage `lcov.info` parsing. | `[B]` |
| `test_catalogs.py` | Catalog YAML parses; catalog schema validates; duplicate names rejected; `catalog_version` is present. | `[B+synth]` |
| `test_probe_registration.py` (extends Phase 0) | Each Phase 1 probe registers once; `requires` graph acyclic; `applies_to_languages` correct; `applies_to_tasks=["*"]`. | `[B]` |
| `test_probe_slice_disjoint.py` (extends Phase 0) | No two probes write to the same top-level slice key. | `[B]` |
| `test_sub_schemas.py` | Each per-probe sub-schema is valid Draft 2020-12; each `$ref` resolves; each sub-schema has `additionalProperties: false` at root. | `[B+synth]` |
| `test_cache_keys.py` (extends Phase 0) | For each Phase 1 probe, modifying a `declared_inputs` file changes the key; modifying a non-declared file does not. | `[B]` |
| `test_parsers_safe_json.py` | Size cap fires; depth cap fires; valid JSON parses; symlink target refused (`O_NOFOLLOW`). | `[S+synth]` |
| `test_parsers_safe_yaml.py` | Same shape; `yaml.CSafeLoader` used; depth cap fires on billion-laughs fixture. | `[S+synth]` |
| `test_parsers_jsonc.py` | Strips line comments; strips block comments; handles trailing commas (per real-world tsconfig); pathological fuzz fixtures complete in < 1 s. | `[synth]` |
| `test_parsed_manifest_memo.py` | First call parses; second call returns memoized; `mtime` change re-parses; falsy memo → fallback. | `[synth]` |

### Adversarial tests (`tests/adv/`) — CI-gating

These are the load-bearing security tests. A regression here is a P0 defect.

- `test_yaml_billion_laughs.py` — fixture `pnpm-lock.yaml` with billion-laughs; assert `DepthCapExceeded` fires; probe marked failed; **gather exits 0**; coordinator never OOMs. `[S]`
- `test_json_bomb_deep_nesting.py` — `package.json` with 10,000 nested objects; depth cap fires. `[S]`
- `test_json_bomb_huge_string.py` — `package.json` with a single 600 MB string; size cap fires (5 MB limit). `[S]`
- `test_yaml_unsafe_tag.py` — `pnpm-lock.yaml` with `!!python/object`; `CSafeLoader` refuses; if a future bug uses unsafe loader, test detects (no sentinel side effect). `[S]`
- `test_symlink_escape_in_declared_inputs.py` — `package.json` symlinks to `/etc/passwd`; `O_NOFOLLOW` open fails; probe records `confidence: low`; sensitive contents never appear in YAML. `[S]`
- `test_zip_slip_kustomize.py` — `kustomization.yaml` with `resources: ["../../etc/passwd"]`; resolution refuses; warning emitted. `[S]`
- `test_planted_node_on_path_ignored.py` — `$PATH` includes a malicious `node` shim. The shim attempts to write a sentinel. `exec.run_allowlisted` env-strip + timeout + the fact that Phase 0 allowlist resolves `node` via `shutil.which` after env strip mean the shim runs in a stripped env without secret access; the sentinel write is *not* prevented by Phase 1 (the binary is allowlisted by name), but the **secrets it might try to steal are not in scope**. Test asserts the env strip and that no secret env var leaks. `[synth — explicit acknowledgement that `node` on `$PATH` is not RCE-proof; the env-strip carries the load-bearing weight]`
- `test_tsconfig_pathological.py` — fixture `tsconfig.json` with deeply nested block comments, unterminated string, circular `extends` chain. `jsonc.py` either parses successfully or raises a typed error; never hangs. `[synth]`
- `test_regex_dos_yarn_lock.py` — pathological `yarn.lock` (if hand-rolled fallback path is active); assert parser completes in < 1 s. `[S]`
- `test_oversized_lockfile.py` — 60 MB lockfile; size cap fires; probe failed; gather continues. `[S]`

### Integration tests (`tests/integration/probes/`)

- `test_layer_a_end_to_end.py` — full `codegenie gather` against `tests/fixtures/node_typescript_helm/`; every Phase 1 probe produces a non-empty slice; envelope schema validates. `[B]`
- `test_cache_hit_on_real_repo.py` — gather twice; second run reports `ProbeExecution.CacheHit` for all six probes; **no `os.scandir` called on second run** (monkey-patched). This is the roadmap's exit-criterion test. `[B+P0]`
- `test_cache_invalidation.py` — gather; modify `package.json`; gather again; assert `language_detection`, `node_build_system`, `node_manifest`, `test_inventory` re-ran; `ci`, `deployment` cache-hit. `[B]`
- `test_real_oss_fixture.py` — clone `expressjs/express` at a pinned SHA; gather; assert schema validity + no native modules + GitHub Actions detected. Cached by `actions/cache` on the SHA. `[B]`
- `test_non_node_repo.py` — gather on a Go-only fixture; Phase 1 probes are filtered out; envelope still validates (Layer A slices are optional). `[synth — addresses [B] blind spot]`

### Golden files (`tests/golden/`)

Phase 2's full golden-file convention. Phase 1 lands one golden — the `tests/fixtures/node_typescript_helm/` expected `repo-context.yaml` — to seed the convention.

### Benchmarks (`tests/bench/`) — advisory only

- `test_warm_path_latency.py` — gather a fixture twice; assert second-run wall-clock ratio ≤ 0.25 of first-run (advisory metric per Phase 0 §7.4).
- `test_per_probe_rss.py` — `tracemalloc` per probe; advisory tracking against per-probe budgets.

### Tests explicitly **not** in Phase 1

- No tests against live CI providers (`gh actions` API calls).
- No tests requiring Docker / `node_modules` to be installed.
- No tests of `IndexHealthProbe` (Phase 2).
- No property tests on lockfile parsers — they're small and well-understood; adversarial coverage carries the weight.
- No fork+exec sandbox tests (no per-probe sandbox exists in this design).
- No `views.json` projection tests (no `views.json` artifact exists).

---

## Risks (top 5)

1. **Native module catalog gap surfaces in Phase 7, five phases out.** The catalog is hand-curated and seeded with ~10 well-known entries. A missed entry → a Phase 7 distroless migration that builds, tests pass, and crashes at runtime because of a missing `system_deps_required`. **Mitigation:** catalog versioning means a Phase-7 catalog update cleanly invalidates cached `NodeManifest` outputs; the `catalog_entry_version` per entry lets us track when each native module was reviewed; Phase 7's integration tests are explicitly tasked with exercising the catalog and surfacing gaps. **The risk is acknowledged as real silent-staleness in the spirit of `production/design.md §2.3`** — but the alternative (auto-derive from npm metadata) is materially worse (npm metadata is itself adversarial input).
2. **In-process parse caps do not protect against parser-CVE exploits in `pyyaml`/cpython.** A future CVE in `yaml.CSafeLoader` or `json.loads` that bypasses our post-parse depth-walker would land RCE in the gather process. **Mitigation:** Phase 0 `pip-audit` + `osv-scanner` + Dependabot watch the parsers; the field-name regex + recursive `JSONValue` typing + path scrubber are belt-and-suspenders structural defenses. **Phase 14's production gather worker adds OS-level rlimits + bwrap.** Phase 1 explicitly chooses *not* to add a per-probe fork sandbox because (a) it's an ABC violation per critic §2.1.1 and (b) the marginal threat closure is ~20% for ~1.5 s of cold-gather overhead per Phase 0 CI cycle.
3. **The `node --version` invocation widens the host-`$PATH` attack surface.** A hostile `node` shim on `$PATH` can write side-effect files. **Mitigation:** `exec.run_allowlisted` strips secrets from env; timeout is 5 s; output is parsed as a version string only (never as code); the value is a display field, never a control-flow input. The ADR documenting the `ALLOWED_BINARIES` addition records this risk explicitly. **The decision overrides [S]'s veto** per Rule 11 conformance with `localv2.md §5.1 A2`.
4. **Cache-key derivation by `(path, size)` is vulnerable to a same-size lockfile poisoning attack.** An attacker with write access to the analyzed repo can substitute a lockfile of the same byte length and cause the cache to return a stale slice. **Mitigation:** Phase 1's threat model assumes the attacker does not have write access to the analyzed repo at gather time (Phase 14's production worker operates on a freshly-cloned worktree); the structural cache-key change ([S]'s byte-content hash) is deferred to Phase 14 when the multi-actor threat model arrives. Recorded as a Phase 14 precondition.
5. **The non-Node repo path emits an envelope with most Layer A slices absent.** Downstream consumers expecting all Layer A slices to be present will break on a Go-only or Python-only repo. **Mitigation:** the envelope sub-schemas declare each Layer A slice as **optional** at the `probes.*` level. The per-probe `applies_to_languages` filter (Phase 0 registry) correctly skips the Node probes on non-Node repos. Phase 2 (Layers B–G) will introduce language-agnostic probes that fill the gap; the envelope shape is forward-compatible. This is the cleanest of the three options the [B] design surfaced ("nullable variants" / "conditional branches" / "separate envelope"): optional slices is the minimum-friction path.

---

## Synthesis ledger

### Vertex count

- Performance `[P]`: ~32 atomic decision vertices (SnapshotBuilder, PathIndex mixin, coordinator extensions, msgpack inter-probe cache, in-process LRU, mmap on Linux, streaming writer, views.json, hand-rolled yarn parser, BLAKE3 fingerprint, hash-validation-skip-on-LRU, per-probe RSS enforcement, ruamel.yaml C-mode, msgpack package.json, pyjson5/orjson, Tier-0/Tier-1 split, explicit DAG, cooperative cancellation, per-probe `parsed.msgpack`, …).
- Security `[S]`: ~38 atomic decision vertices (parser sandbox subprocess, rlimits PRE-exec, bwrap on Linux, sandbox-exec on macOS, env strip, stdin DEVNULL, byte-content cache key, O_NOFOLLOW, third sanitizer pass, additionalProperties false per probe, no node invocation, no node_modules parsing, no hcl2, no Helm template render, yarn-lock hand-rolled no-backtracking, JSON depth cap, YAML depth cap, parse-time cap, stdout cap, prompt-injection markers, audit input byte hashes, adversarial fixture corpus ≥ 50, …).
- Best-practices `[B]`: ~29 atomic decision vertices (extension by addition, ≤12 new files, ≤1100 LOC, 90/80 coverage, catalog YAML, explicit imports, lockfile-precedence ordering, no script eval, multi-lockfile = low confidence, multi-env Helm as list, Jenkinsfile presence-only, file count not test count, pyarn-if-maintained-else-hand-rolled, optional hcl2, node --version cross-check, packageManager-vs-lockfile preference, …).
- Critic-flagged shared blind spots: 4 (warnings shape; `LanguageDetection` extension; reading `package.json` 3× per gather; per-probe sub-schema `additionalProperties: false` undocumented).
- **Total:** ~99 atomic vertices, 35 cross-design edges resolved below.

### Edges

| Class | Count | Examples |
|---|---|---|
| AGREE | 14 | Lockfile-precedence ordering for package-manager; no script evaluation; `yaml.CSafeLoader` mandatory; file count for test inventory; catalog YAML for native modules + CI providers; explicit imports for probe registry; no Helm template rendering; multi-lockfile = confidence drop; no `npm ls`. |
| COMPLEMENT | 9 | [S]'s in-process caps + [B]'s per-probe sub-schemas; [P]'s `ProbeExecution` seam + [B]'s catalog versioning; [S]'s `O_NOFOLLOW` + [B]'s declared_inputs precision; [B]'s multi-env-Helm-as-list + [S]'s path-traversal refusal. |
| SUBSUME | 4 | [B]'s per-probe sub-schema `additionalProperties: false` subsumes [S]'s third sanitizer pass; [synth]'s ParsedManifestMemo subsumes [P]'s msgpack side-channel; [synth]'s in-process safe_parse subsumes [S]'s fork+exec sandbox for caps purposes; Phase 0's existing `_ProbeOutputValidator` subsumes [S]'s coordinator-side prompt-injection filter. |
| CONFLICT | 8 | (See conflict table below.) |
| **Total** | **35 cross-design edges** | |

### Conflict-resolution table

| # | Dimension | [P] picks | [S] picks | [B] picks | Winner | Exit-fit | Roadmap-fit | Commitments-fit | Critic-fit | Sum | Rationale |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Probe execution model | Async-task per probe in coordinator + PathIndex mixin | Per-probe fork+exec subprocess with bwrap/sandbox-exec | Phase 0 unchanged (one asyncio task per probe) | **`[B]` Phase 0 unchanged** | 3 | 3 | 3 (extension by addition §2.5) | 3 | **12** | [P]'s mixin drifts the ABC (critic §1.1.1). [S]'s sandbox is a new architectural layer Phase 0 never sanctioned (critic §2.1.1) and adds ~1.5 s overhead per cold gather. [B]'s "Phase 0 unchanged" is the only option that preserves the load-bearing extension-by-addition commitment. |
| 2 | `node --version` invocation | (silent) | **No** — RCE surface via `$PATH` | **Yes** — read both engines.node and `node --version` | **`[B]` Yes** | 2 (localv2 conformance) | 2 | 2 (Rule 11 conformance > taste) | 2 (resolves the cross-lens disagreement) | **8** | `localv2.md §5.1 A2` explicitly specifies the cross-check; Phase 0 §2.3 makes localv2 the source of truth. [S]'s threat is mitigated by env-strip + timeout + display-only-not-control-flow. Risk recorded; ADR-gated. |
| 3 | Inter-probe parsed-state sharing | **Yes** — msgpack side-channel | (sandbox would block) | **No** — each probe re-parses for isolation | **`[synth]` ParsedManifestMemo in coordinator** | 3 | 3 (preserves cache-hit pass-through seam Phase 14 needs) | 3 (no side-channel; sanitizer + validator preserved) | 3 (resolves critic cross-design obs #3) | **12** | [P]'s msgpack bypasses the sanitizer (critic §1.1.2). [B]'s 3× parse cost is the wrong tradeoff (critic §3.6). The memo lives *inside* the coordinator, never written to disk; one Phase-1 ADR documents the `ProbeContext` extension. |
| 4 | `additionalProperties` per probe sub-schema | (not specified) | **Yes** — load-bearing | **Yes** — friction is the point | **`[B+S]` Yes** | 3 | 3 | 3 (extension by addition) | 3 (resolves critic cross-design obs #1) | **12** | Both lenses agree; the synthesizer documents it at the per-probe sub-schema root (Phase 0 §2.9 layered policy preserved at envelope and `probes.*`). |
| 5 | yarn.lock parser | **Hand-rolled** by default (~200 ms warm win) | Hand-rolled no-backtracking | **`pyarn` if maintained, else hand-rolled fallback** | **`[B]` pyarn-if-maintained** | 3 | 2 (defer maintenance burden until forced) | 3 | 3 (critic §1.1.4 demolishes [P]'s avg-latency math) | **11** | Decision rule encoded in a Phase-1 ADR at land-time; fallback parser exists as backup. |
| 6 | Cache-key derivation | PathIndex packed fingerprint | **File-byte content hash** | Phase 0 unchanged | **`[B]` Phase 0 unchanged** | 3 | 3 (Phase 14 redesigns multi-actor key; this is the right scope) | 3 (Phase 0 chokepoint) | 3 (critic §2.2.3 demolishes [S]'s ADR-bypass) | **12** | Both [P] and [S] rewrite a Phase 0 chokepoint without ADR amendment. Phase 0 final-design §2.7 commits to revisiting at Phase 14. Phase 1 inherits. |
| 7 | Streaming writer + views.json | **Yes** — streaming + Phase-8 projection | (not addressed) | Phase 0 batch write | **`[B]` Phase 0 batch write** | 3 | 2 (no Phase 8 design exists) | 3 (no forward-edit dependency) | 3 (critic §1.1.5 — Phase 8 → Phase 1 edit is the inverse of extension by addition) | **11** | Ship Phase 8 hot views in Phase 8. |
| 8 | New parser C-extension deps | **Yes** — msgpack, pyjson5, ruamel.yaml | (sandbox-only — implicitly stdlib only) | **No** — stdlib + PyYAML (Phase 0) + optional pyarn | **`[B]` stdlib + pyarn** | 3 | 3 | 3 (no CVE-surface growth) | 3 (critic §1.1.6) | **12** | Phase 0 ratified `pyyaml.CSafeLoader` + stdlib `json` + `blake3`. Phase 1 adds only `pyarn` (conditional). |

Tie-breaks (used for #2): localv2.md conformance wins per Phase 0 §2.3.

### Shared blind spots considered

Critic's cross-design observations (carry-forward vs depart):

1. **All three want per-probe `additionalProperties: false` at sub-schema root, none cites Phase 0 §2.9.** **Carried forward and documented** in Component 9. The strictness lives per-probe; the envelope's `probes.*` policy from Phase 0 stays `true`. No release-versioning policy for sub-schemas is added in Phase 1 — declared an open question.
2. **All three duck `LanguageDetectionProbe`'s extension; none argues why in-place modification is allowed.** **Carried forward with explicit rationale:** Phase 0 final-design §2.10 explicitly defers framework + monorepo detection to Phase 1. This is the *one* in-place extension the synthesizer documents as licensed.
3. **All three accept reading `package.json` more than once per gather; none uses Phase 0's `ProbeExecution` seam.** **Departed:** introduces `ParsedManifestMemo` (Component 2), a Phase-1 ADR-gated extension to `ProbeContext`. This addresses the critic's exact phrasing — "the cheapest, cleanest seam goes untouched."
4. **All three under-specify the `warnings: list[str]` and `errors: list[str]` field shapes; `production/design.md §2.2` makes the structural defense load-bearing.** **Acknowledged as deferred** — Phase 1 does not introduce a typed warning enum, but **each per-probe sub-schema's `warnings` field is constrained to a `pattern` that requires structured warning IDs** (`^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`, e.g., `tsconfig.extends_depth_exceeded`). This is the minimum structural constraint that prevents prose-judgment smuggling; full typed warning enum is a Phase 2 task tied to `IndexHealthProbe`.

### Departures from all three inputs

1. **`ParsedManifestMemo` on `ProbeContext`** — none of the three lenses proposed this seam. It addresses critic cross-design observation #3 directly and avoids both the msgpack side-channel and the triple-parse waste.
2. **Per-probe sub-schema strictness with envelope/probes.\* layering preserved** — all three lenses wanted strictness; none documented *where*. The synthesizer reads Phase 0 §2.9's layered policy as the load-bearing seam and places strictness at the sub-schema root only.
3. **Warnings field pattern constraint** — the four-design-wide blind spot the critic flagged; the synthesizer adds the minimum structural constraint without introducing a typed enum.
4. **`safe_parse` helpers as a shared module** — [S] specified caps per-probe; the synthesizer centralizes them in `src/codegenie/parsers/` so each probe uses identical caps. Reduces "security goal degrades to mostly enforced" risk.
5. **Per-probe coverage floor carve-out** — [B] proposed lowering `deployment.py` to 85%. The synthesizer codifies it for `deployment.py` AND `ci.py` (similar structural-narrow-branch shape) and gates further carve-outs by ADR amendment. This is the explicit "not theater" version of [B]'s mitigation that the critic flagged as gameable (Rule 9).

---

## Exit-criteria checklist

- [ ] **`codegenie gather` runs on a real Node.js repo** → integration test `test_layer_a_end_to_end.py` against `tests/fixtures/node_typescript_helm/`.
- [ ] **A useful `repo-context.yaml` is produced** → all six Layer A slices populated; schema validates against envelope + per-probe sub-schemas.
- [ ] **Cache hits on second run** → integration test `test_cache_hit_on_real_repo.py`: all six probes return `ProbeExecution.CacheHit`; `os.scandir` monkey-patched to confirm no re-execution.
- [ ] **All probes pass schema validation** → CI gate: produced YAML must validate against envelope + per-probe sub-schemas, or build fails (Phase 0 exit-code 3 convention).
- [ ] **Probe ABC unchanged** → `tests/unit/test_probe_contract.py` snapshot test passes (Phase 0).
- [ ] **CI green on `main`** including the new adversarial fixture suite.
- [ ] **Coverage floor 90/80 on `src/codegenie/`** (carve-outs for `deployment.py`, `ci.py` at 85/75 declared in `pyproject.toml`).
- [ ] **`fence` CI job continues to assert** dependency closure has no LLM SDK.

---

## Load-bearing commitments check

| Commitment | How honored |
|---|---|
| **§2.1 No LLM in gather** | Phase 0 `fence` CI job extended to cover Phase 1 deps; no LLM SDK added; `pyarn` is a YAML parser, not an LLM SDK. |
| **§2.2 Facts, not judgments** | Probes emit counts, paths, presence flags, version strings, dependency lists. No `safe_for_distroless`, no `production_ready`, no `ci_appropriate`. The `_ProbeOutputValidator`'s recursive `JSONValue` makes judgment-shaped types structurally unrepresentable. Warning IDs constrained to `pattern` matching prevents prose-judgment smuggling. |
| **§2.3 Honest confidence** | Every probe emits `confidence ∈ {high, medium, low}` and an explicit `warnings` list with structured IDs. Multi-lockfile, missing CI, partial Jenkinsfile, Terraform-paths-only — all downgrade confidence and emit a typed warning. |
| **§2.4 Determinism over probabilism** | Parsers are stdlib `json` / `yaml.CSafeLoader` / hand-rolled deterministic line-scanners. No probabilistic classifier. No LLM. |
| **§2.5 Extension by addition** | Phase 1 adds new files under `src/codegenie/probes/`, `src/codegenie/schema/probes/`, `src/codegenie/catalogs/`, `src/codegenie/parsers/`. The three in-place edits (registry imports, LanguageDetection extension Phase 0 explicitly deferred, one `ALLOWED_BINARIES` entry) are each ADR-gated. |
| **§2.6 Org uniqueness as data** | `native_modules.yaml` and `ci_providers.yaml` are YAML data; adding entries is a YAML PR. Catalog self-schema validates structure. |
| **§2.7 Progressive disclosure** | `repo-context.yaml` references raw artifacts at `.codegenie/context/raw/<probe>.json`; doesn't inline lockfile content. |
| **§2.8 Humans always merge** | N/A in Phase 1 (no PRs opened). |
| **§2.9 Cost observable + bounded** | Phase 0 audit anchor extended with per-probe wall-clock for Phase 1 probes. Phase 13's cost ledger reads this same record. |

---

## Roadmap coherence check

- **Prior phases this depends on:**
  - Phase 0 (Bullet tracer + project foundations): probe contract, async coordinator, content-addressed cache, layered JSON Schema, two-pass sanitizer, subprocess allowlist, audit anchor, `ProbeExecution ∈ {Ran, CacheHit, Skipped}` seam, BLAKE3 + SHA-256 hashing, structlog, mypy --strict, ruff, 85/75 coverage floor.
- **What this establishes for later phases:**
  - **Phase 2 (Layers B–G):** `IndexHealthProbe` reads Phase 1's `confidence` outputs and surfaces silent-staleness vectors (the catalog-gap risk especially). The `safe_parse` module is reusable for Phase 2's `semgrep` output parsing and the SCIP index health probe.
  - **Phase 3 (deterministic recipe path):** consumes Phase 1's `manifests` slice + native module catalog directly. The catalog-versioning story unblocks Phase 7.
  - **Phase 7 (Chainguard distroless migration):** the native module catalog from Phase 1 is the primary input. Phase 7's regression precondition: every Phase 1 native module appears in the distroless system-deps lookup; Phase 7's integration tests exercise the catalog.
  - **Phase 8 (Hot views):** the four Phase 8 slices (`available_skills`, `entrypoint`, `risk_flags`, `confidence_summary`) project from `repo-context.yaml` at Phase 8 time, **not at Phase 1 time**. No `views.json` shipped here.
  - **Phase 14 (Continuous gather):** Phase 0's `ProbeExecution` seam (preserved in Phase 1) + Phase 1's per-probe sub-schemas + the audit record's per-probe execution path are exactly what Phase 14's incremental gather needs.
- **New ADRs implied (to be written under `docs/phases/01-context-gather-layer-a-node/ADRs/`):**
  - `0001-add-node-to-allowed-binaries.md` — adds `"node"` to `exec.ALLOWED_BINARIES`; documents threat (`$PATH` shim) and mitigation (env strip + timeout + display-only).
  - `0002-parsed-manifest-memo-on-probe-context.md` — extends `ProbeContext` with optional `parsed_manifest` callable; documents non-persistence and per-gather scope; commits to discarding at gather end.
  - `0003-yarn-lock-parser-choice.md` — decision rule for `pyarn` adoption at land-time; documents the < 18-month-maintenance heuristic + the hand-rolled fallback shape.
  - `0004-per-probe-subschema-additional-properties-false.md` — extends Phase 0's layered `additionalProperties` policy with the per-probe sub-schema strictness rule.
  - `0005-coverage-carve-outs-deployment-ci.md` — codifies 85/75 floor for `deployment.py` and `ci.py`; ADR-amendment required for further carve-outs.
  - `0006-native-module-catalog-versioning.md` — `catalog_version` field at file top participates in cache key; `catalog_entry_version` per entry tracks last review.
  - `0007-warnings-id-pattern.md` — `warnings[]` entries must match `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`; structural defense against prose-judgment smuggling.

---

## Open questions deferred to implementation

1. **`pyarn` adoption rule at land-time.** Per ADR-0003, the implementer confirms `pyarn`'s maintenance status and test-fixture conformance. If unmaintained, ship the ~100-line hand-rolled `yarn.lock` parser as the default.
2. **Per-probe sub-schema versioning policy.** Phase 1 lands v1 sub-schemas. The release-versioning policy for sub-schemas (how a forward-compatible field lands without breaking cached output) is deferred to Phase 2 when the first cross-phase sub-schema change is anticipated.
3. **`packageManager` field handling.** `package.json#packageManager` (e.g., `"pnpm@8.15.0"`) sometimes disagrees with the lockfile. Implementation: prefer the lockfile; emit `warnings: ["package_manager.declaration_lockfile_disagree"]` on mismatch.
4. **GitHub Actions parser depth — reusable workflows.** Phase 1 parses top-level workflows; `uses:` references to reusable workflows are recorded as paths only. Phase 2 may deepen if a consumer demands.
5. **Helm template rendering** stays a Planner-time decision in Phase 3+ (no rendering in Phase 1). Documented in deployment sub-schema.
6. **Multi-environment Helm `image_reference` consumer contract.** The sub-schema declares both `image_reference: nullable` and `environments: list`. Phase 3+ consumers must handle the list shape; documented as an open consumer-contract concern.
7. **Typed warning enum.** Deferred to Phase 2 (`IndexHealthProbe`-driven). Phase 1 ships the `warnings[]` pattern constraint as the minimum structural defense.
