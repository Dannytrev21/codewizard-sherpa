# Phase 1 — Context gathering: Layer A (Node.js): High-level implementation plan

**Status:** Implementation plan
**Date:** 2026-05-12
**Architecture reference:** [phase-arch-design.md](phase-arch-design.md)
**ADRs:** [ADRs/](ADRs/)
**Source design:** [final-design.md](final-design.md)
**Roadmap reference:** [docs/roadmap.md](../../roadmap.md) §"Phase 1"

## Executive summary

The engineer populates the Phase 0 spine with five real Layer A probes (`NodeBuildSystem`, `NodeManifest`, `CI`, `Deployment`, `TestInventory`) plus framework + monorepo extensions to `LanguageDetectionProbe`, all flowing through Phase 0's frozen `_ProbeOutputValidator → OutputSanitizer.scrub → SchemaValidator → CacheStore.put` chain unchanged. The two architectural moves carrying the phase are (1) **`src/codegenie/parsers/`** — size + depth-capped JSON/JSONC/YAML loaders with `O_NOFOLLOW` opens — and (2) **`ParsedManifestMemo` on `ProbeContext`** — a per-gather in-coordinator memo eliminating 3× `package.json` parses. Six steps. Contracts-and-shared-modules first (parsers + memo + sub-schema convention + catalogs + three in-place edits), then the five probes layered onto those primitives, then adversarial + integration hardening + golden + coverage ratchet. Every Phase 0 chokepoint stays untouched; the three in-place edits (registry imports, `LanguageDetectionProbe` extension, `ALLOWED_BINARIES += "node"`) are each ADR-gated.

## Order of operations

The ordering principle is **shared primitives first → probes second → adversarial + integration third**. Specifically: (1) Step 1 plants the parsers, the memo seam on `ProbeContext`, the per-probe-sub-schema convention with `additionalProperties: false` at root, the catalog loader, and the three Phase-0 in-place edits — every probe needs these so they must land first. (2) Step 2 extends `LanguageDetectionProbe` and ships `NodeBuildSystemProbe` — the two probes that prove the shared primitives work end-to-end through the existing coordinator + cache + validator chain. (3) Step 3 ships the load-bearing `NodeManifestProbe` plus the three lockfile parsers under `probes/_lockfiles/`; this is the densest step (pnpm + npm + yarn parsing, native-module catalog cross-reference, `pyarn`-vs-hand-rolled decision per ADR-0003). (4) Step 4 ships `CIProbe`, `DeploymentProbe`, and `TestInventoryProbe` — they are structurally similar (YAML-driven) and share the `safe_yaml` + `ci_providers.yaml` plumbing already on disk from Step 1. (5) Step 5 lands the ten-fixture adversarial corpus and the five integration tests against the new fixture portfolio — the load-bearing security surface and the roadmap exit criteria. (6) Step 6 closes the golden file, the coverage ratchet (90/80 with carve-outs per ADR-0005), the bench additions, and the two gap-analysis improvements (input-snapshot pass + raw-artifact budget) — these are the seams Phase 2 inherits. Adversarial tests live with their probe where possible; the dedicated adversarial step exists for cross-cutting fixtures that span multiple probes.

## Step 1 — Plant shared primitives, sub-schema convention, and the three Phase-0 in-place edits

**Goal:** Every primitive every Phase 1 probe consumes — parsers, memo, sub-schema chokepoint, catalogs, `node` binary allowlist entry — exists on disk and is unit-tested in isolation; the three ADR-gated in-place edits to Phase 0 code are landed.

**Features delivered:**
- `src/codegenie/parsers/__init__.py`, `safe_json.py`, `safe_yaml.py`, `jsonc.py` per `phase-arch-design.md §"Component design" #8`. `O_NOFOLLOW` open before read; pre-parse size check on fd; `yaml.CSafeLoader` only; post-parse depth-walker (since `_json.c` and `CSafeLoader` lack native depth limits); `jsonc.py` is a ~30-LOC state-machine comment stripper feeding `safe_json`.
- `src/codegenie/errors.py` extended with typed exceptions: `SizeCapExceeded`, `DepthCapExceeded`, `MalformedJSONError`, `MalformedYAMLError`, `MalformedLockfileError`, `CatalogLoadError`. `SymlinkRefusedError` already exists from Phase 0; `O_NOFOLLOW` raises it.
- `src/codegenie/coordinator/parsed_manifest_memo.py` — `ParsedManifestMemo` class keyed by `(absolute_path, mtime_ns, size)`; per-gather lifetime; allowlist `{"package.json"}` in Phase 1; first call parses via `safe_json.load`, subsequent return same `MappingProxyType`-wrapped dict.
- `src/codegenie/probes/base.py` is **NOT edited** (Phase 0 frozen). `ProbeContext` lives in `base.py`; the additive optional field `parsed_manifest: Callable[[Path], Mapping[str, JSONValue] | None] | None = None` is an **ADR-0002-gated** in-place edit — it is the one allowed dataclass extension. Snapshot test (`tests/unit/test_probe_contract.py`) regenerates with the documented addition.
- `src/codegenie/coordinator/coordinator.py` extended: constructs `ParsedManifestMemo` per `gather()`; injects `ctx.parsed_manifest=memo.get` on every `ProbeContext`. The Wave-1 / Wave-2 prelude pass (Phase 0 gap #4) is already in place; no new contract.
- `src/codegenie/exec.py` — `ALLOWED_BINARIES` extended from `{"git"}` to `{"git", "node"}` (ADR-0001). Env-strip + `shell=False` unchanged.
- `src/codegenie/catalogs/__init__.py`, `native_modules.yaml`, `ci_providers.yaml`, `_schema.json`. Catalog YAML loaded once at import via `safe_yaml.load` + self-schema-validated; `MappingProxyType` wraps the top-level dict; **hard fail at CLI startup** on malformed YAML or schema-fail (`CatalogLoadError`). `NATIVE_MODULES_CATALOG_VERSION` exported as a module-level int. Seed `native_modules.yaml` with the 10 entries from `phase-arch-design.md §"Component design" #4` (`bcrypt`, `sharp`, `better-sqlite3`, `node-canvas`, `node-rdkafka`, `node-pty`, `bufferutil`, `utf-8-validate`, `argon2`, `keytar`).
- `src/codegenie/schema/probes/_subschema_convention.md` — internal note documenting ADR-0004: every Phase 1 sub-schema sets `additionalProperties: false` at **its own root**; the Phase 0 envelope `probes.*: additionalProperties: true` is preserved. Slices are **optional** at the envelope's `probes.*` level so non-Node repos validate.
- **Pre-dispatch input-snapshot pass (Gap 1 from `phase-arch-design.md`)** — `ctx.input_snapshot: frozenset[InputFingerprint] | None` added to `ProbeContext` alongside `parsed_manifest` (same ADR-0002 amendment, scoped to two fields). Coordinator computes the snapshot once per probe before dispatch using `(path, mtime_ns, size, content_hash)`. Memo key becomes `input_fingerprint.content_hash`. This closes the TOCTOU window the `phase-arch-design.md §"Gap 1"` describes.
- **Per-probe raw-artifact budget (Gap 2 from `phase-arch-design.md`)** — `Probe.declared_raw_artifact_budget_mb: int = 5` class attribute, additive, default unchanged for Phase 0 probes. Coordinator tracks cumulative bytes written via `ctx.workspace` and truncates with a marker at the budget boundary; emits `probe.raw_artifact.truncated` event.
- ADR files in `docs/phases/01-context-gather-layer-a-node/ADRs/` updated/created per `phase-arch-design.md`: ADR-0001 (add `node` to `ALLOWED_BINARIES`), ADR-0002 (`ParsedManifestMemo` + `input_snapshot` on `ProbeContext`), ADR-0004 (per-probe sub-schema `additionalProperties: false`), ADR-0006 (native-module catalog versioning), ADR-0007 (warning ID pattern).

**Done criteria:**
- [ ] `tests/unit/parsers/test_safe_json.py` covers happy path, `SizeCapExceeded` pre-parse, `DepthCapExceeded` post-parse, `O_NOFOLLOW` symlink-refusal, `MalformedJSONError` on invalid bytes.
- [ ] `tests/unit/parsers/test_safe_yaml.py` covers happy path, `DepthCapExceeded` on billion-laughs-shaped input, `MalformedYAMLError` on a `!!python/object` tag (CSafeLoader refuses), `load_all` over multi-document YAML.
- [ ] `tests/unit/parsers/test_jsonc.py` covers line-comments, block-comments, nested block comments, strings containing `//`, unterminated strings raising `MalformedJSONError` in < 1 s on a pathological fixture.
- [ ] `tests/unit/coordinator/test_parsed_manifest_memo.py` covers first-call parse, second-call same-instance return (identity check), mtime-change re-parse, size-change re-parse, parse-failure no-cache (next call retries).
- [ ] `tests/unit/coordinator/test_input_snapshot.py` covers pre-dispatch fingerprint computation, frozen-set membership in `ctx.input_snapshot`, and that memo key derives from `content_hash` not live `os.stat`.
- [ ] `tests/unit/coordinator/test_raw_artifact_budget.py` covers default 5 MB enforcement, override at 25 MB, truncation marker, `probe.raw_artifact.truncated` event emitted.
- [ ] `tests/unit/test_probe_contract.py` snapshot regenerated with `ProbeContext.parsed_manifest` and `ProbeContext.input_snapshot` fields documented in the ADR-0002 amendment; the snapshot test passes; any further edit fails with the amendment-PR pointer.
- [ ] `tests/unit/catalogs/test_catalog_loader.py` covers successful load, malformed YAML → `CatalogLoadError` at startup (hard fail), duplicate-name rejection, `NATIVE_MODULES_CATALOG_VERSION` exported as int, `MappingProxyType` immutability of the top-level dict.
- [ ] `tests/unit/exec/test_allowed_binaries.py` extended: `node` is in `ALLOWED_BINARIES`; env-strip continues to drop `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`/`GITHUB_TOKEN`/`AWS_*`/`SSH_AUTH_SOCK`.
- [ ] All Step 1 code passes strict mypy.
- [ ] Phase 0 `fence` CI job stays green (no LLM SDK in `dependencies`).

**Depends on:** Phase 0 ships and `main` is green.

**Effort:** L — densest step in the phase. The parsers + memo + input-snapshot + raw-artifact-budget + catalog loader are five independent shared modules; each needs its own focused unit test before any probe consumes it.

**Risks specific to this step:** The `ProbeContext` extension (ADR-0002) is the single Phase-0-contract amendment in the entire phase. **If it gets widened later, the snapshot test must fail.** Encode the field list inside the snapshot regeneration script, not just in the snapshot output. The `O_NOFOLLOW` semantics differ subtly across macOS and Linux for symlink-loop detection — test on both via the existing CI matrix. The `jsonc.py` comment stripper is the only hand-rolled parser in shared code; fuzz it locally with an `atheris`-style hostile input set before opening the Step 1 PR.

## Step 2 — Extend `LanguageDetectionProbe` and ship `NodeBuildSystemProbe`

**Goal:** Two probes flow end-to-end through the existing coordinator + cache + validator + sanitizer + audit chain with the new memo + parsers + sub-schema convention all wired and exercising the warm-path memo + cache-hit logic.

**Features delivered:**
- `src/codegenie/probes/language_detection.py` (extended in place) — adds `framework_hints` and `monorepo` fields per `phase-arch-design.md §"Component design" #1`. `declared_inputs` extended to add `"package.json"`, `"pnpm-workspace.yaml"`, `"lerna.json"`, `"nx.json"`, `"turbo.json"`. Post-walk pass: read `package.json` via `ctx.parsed_manifest(...)`; framework dict-lookup against `dependencies + devDependencies` (`{"@nestjs/core": "nestjs", "express": "express", "fastify": "fastify", "next": "next", "koa": "koa", "@hapi/hapi": "hapi"}`); monorepo detection via marker `Path.exists()` + `package.json#workspaces` presence.
- `src/codegenie/schema/probes/language_detection.schema.json` (extended) — adds `framework_hints: list[str]` and `monorepo: MonorepoBlock | null`; `additionalProperties: false` at root.
- `src/codegenie/probes/node_build_system.py` — `NodeBuildSystemProbe` per `phase-arch-design.md §"Component design" #2`. Lockfile-precedence existence check (no parse: `bun.lockb > pnpm-lock.yaml > yarn.lock > package-lock.json`); `package.json` via memo; `tsconfig.json` via `parsers.jsonc.load`; `extends` chain followed ≤ 4 levels; cycle detection → `tsconfig.extends_cycle`; depth-exceeded → `tsconfig.extends_depth_exceeded`; node-version precedence (`engines.node` → `.nvmrc` → `.node-version` → `.tool-versions`); optional `node --version` cross-check via `exec.run_allowlisted` (5 s timeout, regex `^v\d+\.\d+\.\d+`, garbage → `node.version_unparseable` warning, absent binary → `null`); bundler dict-lookup; `package.json#scripts` verbatim never evaluated.
- **Step 2a — Yarn variant detection (follow-up story `S2-02a`, per [ADR-0013](ADRs/0013-yarn-variants-as-distinct-package-managers.md)):** the shipped S2-02 base probe collapses Yarn Classic and Yarn Berry into a single `"yarn"` value. Production ADR-0031 (plugin architecture) treats them as distinct plugin scopes; Phase 1 ADR-0013 records the gather-layer fix. `S2-02a` lands an additive `_detect_yarn_variant()` function in `node_build_system.py` (~30 lines, priority-ordered: `package.json#packageManager` field → `.yarnrc.yml` → `.yarn/` dir → `.pnp.cjs` → safe-default classic with `yarn_variant_inferred` warning), bumps the schema `$id` to `v0.2.0`, and adds two new fixtures (`node_yarn_berry_pnp/`, `node_yarn_berry_nonpnp/`). Effort: S (~1 working day). The `_LOCKFILE_PRECEDENCE` tuple stays unchanged — Open/Closed seam preserved. **Blocks** S3-03 (the yarn lockfile parser must branch on variant: Berry's `yarn.lock` is YAML, Classic's is custom — different parsers).
- `src/codegenie/schema/probes/node_build_system.schema.json` — `BuildSystemSlice` per `phase-arch-design.md §"Data model"`; `additionalProperties: false` at root; slice declared **optional** at envelope `probes.*` level.
- `src/codegenie/probes/__init__.py` — registers `NodeBuildSystemProbe` via explicit import (one-line additive edit, ADR-gated).
- Fixture: `tests/fixtures/node_typescript_helm/` minimal viable structure (TypeScript + pnpm + tsconfig + `.nvmrc`). Used by both this step and Step 5.

**Done criteria:**
- [ ] `tests/unit/probes/test_language_detection_extended.py` covers framework-hint detection on each seed dict entry; monorepo marker detection; absent `package.json` → counts populated but `framework_hints: []`, `monorepo: null`, `confidence` unaffected for counts.
- [ ] `tests/unit/probes/test_node_build_system.py` covers lockfile-precedence on each of the four scenarios; multi-lockfile → `confidence: low`, `package_manager.multi_lockfile` warning; `tsconfig.extends` depth-cap and cycle detection; node-version precedence on each source; `node --version` absent/timeout/garbage paths.
- [ ] `tests/integration/probes/test_language_detection_warm_path.py` — runs `codegenie gather` against `node_typescript_helm`; asserts `framework_hints == ["express"]` (or whichever the fixture declares); asserts memo is hit on the second probe reading `package.json` (`probe.memo.hit` event count == 1, `probe.memo.miss` == 1).
- [ ] `tests/integration/probes/test_cache_hit_on_real_repo.py` (load-bearing exit criterion #2 from `phase-arch-design.md`) — gather `node_typescript_helm` twice; second-run `os.scandir` invocation count is zero (monkeypatched at the `language_detection` module level); both `LanguageDetectionProbe` and `NodeBuildSystemProbe` report `ProbeExecution.CacheHit`.
- [ ] Sub-schema validation: a synthetic envelope with an extra field in `probes.node_build_system` is rejected with `SchemaValidationError`.
- [ ] All Step 2 code passes strict mypy.

**Depends on:** Step 1 (parsers, memo, sub-schema convention, `node` binary allowlist).

**Effort:** M — straightforward probe wiring on top of Step 1's primitives; the `tsconfig.extends` walker and node-version precedence chain need care.

**Risks specific to this step:** The `os.scandir` monkeypatch for the cache-hit test must be applied at the `language_detection` module level (`monkeypatch.setattr("codegenie.probes.language_detection.os.scandir", ...)`) and additionally a `probe.cache_hit` structlog assertion is used as redundant signal — same risk as Phase 0 Step 4's load-bearing exit. The `node --version` invocation is a new external-process surface; the hostile-shim test (`tests/adv/test_planted_node_on_path_ignored.py`) lands in Step 5 but the env-strip path must be sanity-checked here.

## Step 3 — Ship `NodeManifestProbe` and the three lockfile parsers

**Goal:** The load-bearing probe for Phase 7 is on disk. Each of pnpm, npm, and yarn lockfile formats parses end-to-end with size + depth caps, native-module catalog cross-reference produces hits on a fixture portfolio, and the `pyarn`-vs-hand-rolled decision (ADR-0003) is documented at land-time.

**Features delivered:**
- `src/codegenie/probes/_lockfiles/__init__.py`, `_pnpm.py`, `_npm.py`, `_yarn.py` per `phase-arch-design.md §"Component design" #9`. Each is a thin wrapper around `safe_parse` returning a TypedDict. `_yarn.py` has module-level `_HAS_PYARN: bool` boolean; selects `pyarn` if available, else hand-rolled line-by-line state-machine scanner (no regex over full file).
- `src/codegenie/probes/node_manifest.py` — `NodeManifestProbe` per `phase-arch-design.md §"Component design" #4`. `declared_inputs` includes `src/codegenie/catalogs/native_modules.yaml` (so catalog edits invalidate this probe's cache entries per ADR-0006). `declared_raw_artifact_budget_mb = 25` (override of the default 5 MB from Step 1). `package.json` via memo; lockfile parse via the chosen sibling; native-module catalog cross-reference dict-lookup against resolved deps; multi-lockfile → `confidence: low`, `lockfile.multi_present`; lockfile cap exceeded → `confidence: low` + typed warning ID.
- `src/codegenie/schema/probes/node_manifest.schema.json` — `ManifestsSlice` + `ManifestEntry` + `NativeModulesBlock` + `NativeModuleHit` per `phase-arch-design.md §"Data model"`; `additionalProperties: false` at root and at every nested block.
- `src/codegenie/probes/__init__.py` — registers `NodeManifestProbe`.
- Optional dependency: `pyarn` listed under `[project.optional-dependencies] gather` in `pyproject.toml` per the Phase 0 layout. `security` CI job's `pip-audit` / `osv-scanner` closure includes `pyarn`. The `fence` CI job verifies `pyarn` is not an LLM SDK (it isn't).
- Fixtures: `tests/fixtures/node_pnpm_native/` (pnpm + `bcrypt` + `sharp`); `tests/fixtures/node_yarn_legacy/` (yarn classic + `yarn.lock`).
- ADR-0003 finalized at land-time per `phase-arch-design.md §"Open questions" #1`: implementer checks `pyarn` maintenance status (< 18 months since last release) and fixture conformance; if unmaintained, ships hand-rolled as default.

**Done criteria:**
- [ ] `tests/unit/probes/_lockfiles/test_pnpm.py`, `test_npm.py`, `test_yarn.py` each cover the happy path against fixture lockfiles + a malformed-bytes failure path raising the typed exception.
- [ ] `tests/unit/probes/_lockfiles/test_yarn_parser_parity.py` — fixture-based: both `pyarn` (skipped if unavailable) and hand-rolled produce the same TypedDict on a curated `yarn.lock` corpus.
- [ ] `tests/unit/probes/_lockfiles/test_yarn_parser_oracle.py` (Gap 3 from `phase-arch-design.md`) — property-style: for every `yarn.lock` in the fixture portfolio, both parsers' outputs satisfy invariants derived from the lockfile bytes themselves (every name in output appears in lockfile text; every version against the corresponding name; dependency-block count consistent).
- [ ] `tests/unit/probes/test_node_manifest.py` covers happy path on each fixture; multi-lockfile detection; native-module catalog hits (`bcrypt` + `sharp` resolved); `optionalDependencies` + `bundledDependencies` extraction.
- [ ] `tests/integration/probes/test_node_manifest_pnpm_native.py` — gather `node_pnpm_native`; `manifests.native_modules.detected == True`, `packages` contains entries for `bcrypt` and `sharp` with `requires_node_gyp: true`.
- [ ] `tests/integration/probes/test_node_manifest_yarn_legacy.py` — gather `node_yarn_legacy`; both `pyarn` and hand-rolled fallback paths produce identical slices when re-run with `_HAS_PYARN` monkeypatched.
- [ ] Catalog version invalidation: editing `native_modules.yaml` and re-gathering invalidates only `node_manifest` cache entries — `tests/unit/test_cache_invalidation_scope.py` extended.
- [ ] Raw-artifact budget exercised: a synthetic 30 MB lockfile dump truncates at 25 MB with the `probe.raw_artifact.truncated` event.
- [ ] All Step 3 code passes strict mypy.

**Depends on:** Step 1 (parsers, catalogs, raw-artifact budget) + Step 2 (probe-shape conventions established).

**Effort:** L — three lockfile parsers, the native-module catalog cross-reference logic, the `pyarn`-vs-hand-rolled selector, the parity + oracle tests, and the load-bearing 25 MB raw-artifact budget override all land here.

**Risks specific to this step:** ADR-0003 must be decided at the Step 3 PR (not deferred indefinitely): pin `pyarn`'s last-release date in the PR body and record the decision. The yarn-lock hand-rolled scanner is the single most regex-DoS-prone piece of code in the phase — adversarial fuzzing (`tests/adv/test_regex_dos_yarn_lock.py`) lands in Step 5 but local fuzzing before the Step 3 PR is non-negotiable. The native-module catalog seed list (10 entries) is the contract Phase 7 reads; resist adding speculative entries.

## Step 4 — Ship `CIProbe`, `DeploymentProbe`, and `TestInventoryProbe`

**Goal:** The three remaining Layer A probes — all structurally YAML-driven — exist on disk with their sub-schemas and unit tests, completing the six-probe Layer A inventory.

**Features delivered:**
- `src/codegenie/probes/ci.py` per `phase-arch-design.md §"Component design" #5`. `ci_providers.yaml` lookup; first matching entry → `provider`; rest → `additional_providers`; GitHub Actions parser via `safe_yaml.load` per workflow file (10 MB cap each, depth 64); job + `run:` command extraction; image-build detection via substring match for `docker build`, `docker buildx`, `docker/build-push-action`; `${{ secrets.* }}` references recorded as literal strings in `references_secrets`; GitLab CI via `safe_yaml.load`; Jenkinsfile via bounded regex `sh '...'` / `sh "..."` (single capture group, line-bounded) → `confidence: low`; CircleCI / Azure Pipelines presence-only stubs.
- `src/codegenie/probes/deployment.py` per `phase-arch-design.md §"Component design" #6`. Type detection by file marker (`Chart.yaml` → Helm; `kustomization.yaml` → Kustomize; raw `kind: Deployment` → raw; `*.tf` → Terraform paths-only); Helm parses `Chart.yaml` + `values*.yaml`; multi-env → `environments: list[EnvironmentEntry]`; Kustomize follows resources one level deep with `repo_root` containment check (zip-slip mitigation → `kustomization_resource_path_outside_repo: true`); overlay traversal capped at depth 5 + 50 total files; raw manifests via `safe_yaml.load_all`; Terraform records paths only (no `python-hcl2`).
- `src/codegenie/probes/test_inventory.py` per `phase-arch-design.md §"Component design" #7`. Framework dict-lookup against deps for `vitest`, `jest`, `mocha`, `tap`, `@playwright/test`, `cypress`; `node:test` only if `engines.node >= 18` AND no other framework; single `os.walk` over `*.test.*` + `*.spec.*` patterns with Phase 0 noise-dir exclusions; `unit_test_file_count: int` + `unit_test_count_is_file_count: true` (signals the limitation); `package.json#scripts` extraction (`test`, `test:unit`, `test:integration`, `test:smoke`, `test:e2e`, `test:coverage`); smoke-script presence check; `coverage/lcov.info` parsed by a 40-LOC stdlib line-scanner (50 MB cap, no regex backtracking).
- Sub-schemas: `src/codegenie/schema/probes/ci.schema.json`, `deployment.schema.json`, `test_inventory.schema.json` per `phase-arch-design.md §"Data model"`. `additionalProperties: false` at each root + every nested block. All three slices declared **optional** at envelope `probes.*` level.
- `src/codegenie/probes/__init__.py` — registers the three new probes (explicit imports, additive).

**Done criteria:**
- [ ] `tests/unit/probes/test_ci.py` covers GitHub Actions workflow parsing + image-build detection on each marker; GitLab CI parsing; Jenkinsfile regex extraction; multi-provider repo → `additional_providers` populated, `confidence: low`; `references_secrets` captures literal names only.
- [ ] `tests/unit/probes/test_deployment.py` covers Helm single-env + multi-env (`environments` list with multiple entries); Kustomize one-level resource resolution; zip-slip rejection (`kustomization.resource_outside_repo` warning); raw manifests with `kind ∈ {Deployment, StatefulSet, DaemonSet, Pod}`; Terraform paths-only; type-`none` when no markers present.
- [ ] `tests/unit/probes/test_test_inventory.py` covers framework detection on each seed; `node:test` engaged only on `engines.node >= 18` with no other framework declared; `unit_test_file_count` correct on a fixture with 15 `*.test.ts` files; coverage parser handles a real `lcov.info` and a malformed one (warning emitted, slice still populated).
- [ ] Each sub-schema has at least one `additionalProperties: false` rejection test (synthetic envelope with extra field → `SchemaValidationError` at the right JSON Pointer).
- [ ] Per-module coverage carve-out (85% line / 75% branch) declared in `pyproject.toml` for `probes/deployment.py` and `probes/ci.py` per ADR-0005; rest of `src/codegenie/` at 90/80.
- [ ] All Step 4 code passes strict mypy.

**Depends on:** Step 1 (parsers, catalogs, sub-schema convention) + Step 2 (probe-shape conventions). Does **not** depend on Step 3 (these three probes don't read lockfiles).

**Effort:** M — three probes of comparable complexity; each is largely YAML parsing + dict-lookup against a catalog. Largest surface is `DeploymentProbe`'s Helm + Kustomize + raw-manifest + Terraform branches.

**Risks specific to this step:** The `kustomization.yaml` resource-path containment check is the load-bearing zip-slip mitigation — use `Path.resolve()` (not string concat) and verify the resolved path is under `repo_root` (`Path.is_relative_to` on 3.12, manual walk on 3.11). The `coverage/lcov.info` line-scanner must never use regex with backtracking — write it as a state machine and adversarially test with a 50 MB malformed file in Step 5.

## Step 5 — Adversarial corpus + integration end-to-end + fixture portfolio

**Goal:** The ten adversarial fixtures pin every structural defense, the five integration tests run end-to-end through the CLI against the new fixture portfolio, and the roadmap exit criteria are demonstrably green in CI.

**Features delivered:**
- Adversarial fixtures + tests per `phase-arch-design.md §"Testing strategy" → "Adversarial tests"`:
  1. `tests/adv/test_yaml_billion_laughs.py` — adversarial `pnpm-lock.yaml`; `DepthCapExceeded` fires; gather exits 0.
  2. `tests/adv/test_json_bomb_deep_nesting.py` — 10,000-nested-object `package.json`; depth cap fires.
  3. `tests/adv/test_json_bomb_huge_string.py` — 600 MB single-string `package.json`; size cap fires pre-parse.
  4. `tests/adv/test_yaml_unsafe_tag.py` — `pnpm-lock.yaml` with `!!python/object`; CSafeLoader refuses; sentinel side-effect never observed.
  5. `tests/adv/test_symlink_escape_in_declared_inputs.py` — `package.json` symlink to `/etc/passwd`; `O_NOFOLLOW` open fails; sensitive contents never in YAML output.
  6. `tests/adv/test_zip_slip_kustomize.py` — `kustomization.yaml` with `resources: ["../../etc/passwd"]`; refused; warning emitted; valid resources still processed.
  7. `tests/adv/test_planted_node_on_path_ignored.py` — hostile `node` shim on `$PATH` (writes to a sentinel file when invoked); env-strip verified; no `OPENAI_API_KEY`/`GITHUB_TOKEN`/`AWS_*`/`SSH_AUTH_SOCK` reaches the child.
  8. `tests/adv/test_tsconfig_pathological.py` — deeply nested block comments + unterminated string + circular `extends`; `jsonc.py` either parses or raises typed error in < 1 s.
  9. `tests/adv/test_regex_dos_yarn_lock.py` — pathological `yarn.lock` (active when `_HAS_PYARN = False` is forced); parser completes in < 1 s.
  10. `tests/adv/test_oversized_lockfile.py` — 60 MB `pnpm-lock.yaml`; size cap fires.
- Fixtures `tests/fixtures/node_monorepo_turbo/` (turbo + `package.json#workspaces`) and `tests/fixtures/non_node_go/` (Go-only).
- Integration tests:
  - `tests/integration/probes/test_layer_a_end_to_end.py` — gather `node_typescript_helm` cold; assert all six Layer A slices populated; envelope + six sub-schemas pass; audit anchor re-computes.
  - `tests/integration/probes/test_cache_hit_on_real_repo.py` — already landed in Step 2; extended to assert all six probes (not just two) report `CacheHit` on second run.
  - `tests/integration/probes/test_non_node_repo.py` — gather `non_node_go`; envelope validates with only `language_stack`; the five Phase-1 Node probes filtered out by `for_task`.
  - `tests/integration/probes/test_monorepo_turbo.py` — gather `node_monorepo_turbo`; `language_detection.monorepo` populated; root-level `node_build_system` slice produced (workspaces traversal is Phase 2's concern).
  - `tests/integration/probes/test_coordinator_prelude.py` — assert Wave-1 LD completes before Wave 2 dispatch and `enriched_snapshot.detected_languages` is populated when Wave 2 probes run.
- New structlog event names registered in `src/codegenie/logging.py` constants: `probe.parser.cap_exceeded`, `probe.memo.hit`, `probe.memo.miss`, `probe.catalog.load`, `probe.raw_artifact.truncated`.
- New structured tracing field `parser_kind` added to every parse-related event.

**Done criteria:**
- [ ] All ten adversarial tests pass and run in CI in < 30 s p95 wall-clock combined.
- [ ] All five integration tests pass in CI on Python 3.11 and 3.12.
- [ ] `test_layer_a_end_to_end.py` produces a valid `repo-context.yaml` on `node_typescript_helm` — this is the roadmap Phase 1 exit-criterion-1.
- [ ] `test_cache_hit_on_real_repo.py` extended assertion holds (all six probes `CacheHit` on second run) — roadmap exit-criterion-2.
- [ ] `test_non_node_repo.py` envelope validates with only `language_stack` — exit criterion #3 path for non-Node.
- [ ] The hostile-shim adversarial test (`test_planted_node_on_path_ignored.py`) asserts none of the stripped env vars reaches the child (verified via the sentinel-file mechanism).
- [ ] All Step 5 code passes strict mypy.

**Depends on:** Steps 2 + 3 + 4 (all six probes on disk).

**Effort:** M — adversarial fixtures are mechanical; integration tests are straightforward once the probes work. The single non-mechanical piece is the `test_planted_node_on_path_ignored.py` hostile-shim mechanism, which uses a temporary directory prepended to `$PATH` containing a sentinel-writing shell script.

**Risks specific to this step:** Adversarial tests can mask false-positive-green if the cap-exceeded path is reached via a different mechanism than intended (e.g., the test exercises `O_NOFOLLOW` when it should exercise `DepthCapExceeded`). Assert the **specific** error type and JSON Pointer in each adversarial test, not just exit code 0 + `confidence: low`. The 600 MB JSON bomb fixture is large for CI disk — generate it at test setup time, not as a checked-in file (CI walltime budget per `phase-arch-design.md §"CI gates"` is 120 s p95 absolute ceiling).

## Step 6 — Golden file, coverage ratchet, bench additions, Phase 2 handoff issues

**Goal:** The single golden file anchors Phase 2's expansion convention, the coverage ratchet to 90/80 with documented carve-outs holds in CI, the two new bench canaries run advisory, and the issues Phase 2 needs to pick up are filed.

**Features delivered:**
- `tests/golden/node_typescript_helm.repo-context.yaml` — seed golden; the integration end-to-end test diffs the live output against it; updates require a deliberate PR step via `scripts/regen_golden.py`.
- `scripts/regen_golden.py` — re-runs `codegenie gather` against `tests/fixtures/node_typescript_helm/` and writes the golden in canonical YAML ordering (sorted keys at every level).
- Coverage ratchet: `pyproject.toml` updated to `--cov-fail-under=90` with per-module floors of 85% line / 75% branch for `probes/deployment.py` and `probes/ci.py` declared in `[tool.coverage.report] exclude_also` or equivalent (per ADR-0005). Further carve-outs require their own ADRs.
- `tests/bench/test_warm_path_latency.py` — gather `node_typescript_helm` twice; assert second-run wall-clock ratio ≤ 0.25 of first-run (advisory PR comment only).
- `tests/bench/test_per_probe_rss.py` — `tracemalloc` per probe against the component-section RSS budgets (advisory).
- Phase 2 issues filed in the GitHub Project board:
  - Implement `IndexHealthProbe (B2)` (the load-bearing Phase 2 probe).
  - Promote `WarningId` pattern to a typed enum (`phase-arch-design.md` open question #7).
  - Decide per-probe sub-schema release-versioning policy (`phase-arch-design.md` open question #2).
  - Extend the memo allowlist beyond `{"package.json"}` for Layer B/C/D index manifests.
  - Coverage ratchet to 92/82 in Phase 2 (per Phase 0's documented schedule extension).
- `docs/contributing.md` updated with the "adding a probe" cheat sheet section referencing the Phase 1 probes as canonical examples.
- `docs/phases/01-context-gather-layer-a-node/README.md` updated with the final exit-criteria checklist marked complete.

**Done criteria:**
- [ ] `tests/golden/node_typescript_helm.repo-context.yaml` exists, is canonically ordered, and the integration test diffs against it as a hard CI gate.
- [ ] `scripts/regen_golden.py` produces byte-identical output across two consecutive runs.
- [ ] Coverage gate passes at 90/80 with carve-outs documented; the Step 6 PR shows the actual percentages in the PR body.
- [ ] Both bench canaries run in CI and post advisory PR comments; never block merge.
- [ ] All five Phase 2 follow-up issues exist on the GitHub Project board with milestones aligned to `roadmap.md` §"Phase 2".
- [ ] All six CI jobs (`lint`, `typecheck`, `test`, `security`, `docs`, `fence`) green on `main` on Python 3.11 *and* 3.12 with the full Phase 1 test surface.
- [ ] `docs/contributing.md` builds in `mkdocs build --strict` and remains in the curated `nav`.

**Depends on:** Steps 1–5 complete and merged.

**Effort:** S — most items are configuration files, scripts, and documentation. The golden regeneration script is the only non-trivial piece (canonical YAML ordering is fiddly; `yaml.safe_dump(..., sort_keys=True, default_flow_style=False)` is the load-bearing primitive).

**Risks specific to this step:** Golden files are notoriously brittle to non-determinism. The Phase 0 commitment that gather is deterministic on identical content carries the load here, but **wall-clock fields** (`wall_clock_ms` in the audit record) must be excluded from the golden by the regen script — or written to a separate sidecar that the golden test ignores. Coverage ratchet at 90/80 is tight; if a probe lands at 88/74 in CI, the Step 6 PR cannot merge until the test gap is closed — Step 6 must not be merged with a coverage-floor failure.

## Exit-criteria mapping

Every Phase 1 exit criterion from `roadmap.md` §"Phase 1" and every refined exit criterion from `phase-arch-design.md §"Goals"` traces to a step.

| Exit criterion (verbatim or close) | Step(s) |
|---|---|
| Useful `repo-context.yaml` produced on a real Node.js repo | Step 5 (`test_layer_a_end_to_end.py`); Steps 2, 3, 4 (probes) |
| Cache hits on second run (all six Layer A probes) | Step 2 (initial test), Step 5 (extended to all six) |
| All probes pass schema validation | Steps 2, 3, 4 (per-probe sub-schemas land); Step 5 (envelope validation in integration tests) |
| Per-probe unit tests against fixture repos | Steps 2, 3, 4 (each ships its own unit tests) |
| Integration test against a real small open-source Node.js repo | Step 5 (`node_typescript_helm` is the proxy; substitute a real repo at land-time if available) |
| Schema validation enforced as a CI gate | Step 1 (per-probe sub-schema convention) + Step 5 (integration test) |
| Probe contract `localv2.md §4` preserved (snapshot test green) | Step 1 (ADR-0002 amendment regenerates snapshot) |
| Hard caps in every parser (5 MB / 50 MB / depth 64) | Step 1 (parsers) + Step 5 (adversarial corpus) |
| Adversarial corpus ≥ 20 hostile inputs producing zero RCE / OOM | Step 5 (10 dedicated + ≥ 10 inherited from Phase 0) |
| Coverage ratchet 90/80 with 85/75 carve-outs | Step 4 (carve-outs declared) + Step 6 (gate raised) |
| Wall-clock targets (advisory): cold 4 s / warm 0.4 s / incremental 1 s p50 | Step 6 (bench canaries) |
| Tokens per run = 0 (`fence` job continues to assert) | Step 1 (verified across all new deps) |
| Extension by addition holds (exactly three Phase 0 edits) | Step 1 (the three edits land; all others new files) |
| `ParsedManifestMemo` on `ProbeContext` (ADR-0002) | Step 1 |
| `parsers/` module with `O_NOFOLLOW` opens and depth-walker | Step 1 |
| Native-module catalog seeded with 10 entries; `catalog_version` invalidation | Step 1 (catalog) + Step 3 (consumed by `NodeManifestProbe`) |
| Warning ID pattern (ADR-0007) | Step 1 (convention) + Steps 2–4 (used by each probe) |
| `node` in `ALLOWED_BINARIES` (ADR-0001) | Step 1 (allowlist) + Step 2 (consumed by `NodeBuildSystemProbe`) |
| Per-probe sub-schemas with `additionalProperties: false` at root (ADR-0004) | Step 1 (convention) + Steps 2–4 (each probe ships its sub-schema) |
| Input-snapshot pass closes Gap 1 (TOCTOU window) | Step 1 |
| Per-probe raw-artifact budget closes Gap 2 | Step 1 (mechanism) + Step 3 (exercised by `NodeManifestProbe` at 25 MB override) |
| Yarn-parser two-direction parity (Gap 3) | Step 3 (`test_yarn_parser_oracle.py`) |
| Wave-1 prelude formalized (Phase 0 gap #4 carried forward) | Step 1 (coordinator extension) + Step 5 (`test_coordinator_prelude.py`) |
| Layer A slices declared optional at envelope level | Step 1 (convention) + Step 5 (`test_non_node_repo.py`) |
| Golden file seeded for `node_typescript_helm` | Step 6 |
| Phase 2 follow-up issues filed | Step 6 |

No exit criterion is unmapped.

## Implementation-level risks

Distinct from the design-level risks in `phase-arch-design.md`. These are about *the work*.

1. **Step 1 is overloaded.** Parsers + memo + input-snapshot + raw-artifact budget + catalog loader + three in-place edits + five ADRs all land in one step. **Signal:** the Step 1 PR balloons past 1,500 LOC and the reviewer asks for a split. **What to do:** if Step 1's PR exceeds 1,200 LOC, split it into Step 1a (parsers + errors + catalogs) and Step 1b (memo + input-snapshot + raw-artifact budget + `ProbeContext` extension + ADR-0002 + ADR-0001). Steps 2–6 are unchanged by the split; the dependency edge stays the same.

2. **The `ProbeContext` extension is the only Phase-0-contract amendment.** Two fields are added in one ADR (ADR-0002): `parsed_manifest` and `input_snapshot`. **Signal:** a later contributor proposes adding a third field "while we're amending it." **What to do:** Encode the allowed field list inside the snapshot regeneration script, not just in the snapshot output. Route `ProbeContext` to `CODEOWNERS` so any change requires designated review. The ADR explicitly says "no further extensions in Phase 1."

3. **`pyarn` decision (ADR-0003) can drift past Step 3.** If the implementer ships `_yarn.py` with both paths and defers ADR-0003 finalization, the Phase 2 author inherits an undecided contract. **Signal:** the Step 3 PR ships `_yarn.py` but ADR-0003 is left in draft. **What to do:** Make the Step 3 PR-review checklist explicitly include "ADR-0003 status: accepted, with `pyarn` last-release-date pinned in the ADR body." If `pyarn` is unmaintained, the default flips to hand-rolled before merge.

4. **The yarn-lock hand-rolled scanner is the regex-DoS-prone surface.** **Signal:** Step 3 lands with `_yarn.py` passing happy-path tests, but `tests/adv/test_regex_dos_yarn_lock.py` is deferred to Step 5. **What to do:** Local fuzzing before the Step 3 PR (using `atheris` or a stdlib timeout loop on random byte mutations of a real `yarn.lock`) is non-negotiable. The adversarial test in Step 5 is the CI gate but not the first defense.

5. **Coverage ratchet at 90/80 is tight enough to block Step 6 if any probe falls short.** **Signal:** Step 6 PR fails CI on coverage. **What to do:** Each of Steps 2–4 must run coverage locally for the probe being added and report the per-probe number in the PR body. If `deployment.py` or `ci.py` is below 85/75 at the per-module floor, that probe's PR cannot merge until the test gap is closed — don't push the work into Step 6.

6. **Golden file non-determinism.** **Signal:** Step 6 lands the golden, then a CI run a day later fails the diff. **What to do:** The regen script excludes wall-clock and audit timestamps from the YAML output written for the golden. Run the regen script twice locally and verify byte-identical output before opening the Step 6 PR.

7. **The `os.scandir` monkeypatch target drifts.** Same risk as Phase 0 Step 4. **Signal:** the cache-hit test passes but `strace` shows the second-run still walks the filesystem. **What to do:** Monkeypatch at the `language_detection` module level (`monkeypatch.setattr("codegenie.probes.language_detection.os.scandir", ...)`); assert the patched callable's invocation count is zero on the second run; additionally assert the `probe.cache_hit` structlog event count equals the number of cached probes.

## What's next — handoff to Phase 2

After Phase 1 ships, the system materially changes in these ways. Phase 2 (`roadmap.md` §"Phase 2") picks up here.

- **New artifacts on disk:**
  - `.codegenie/context/repo-context.yaml` now contains six Layer A slices (`language_stack` extended; `build_system`, `manifests`, `ci`, `deployment`, `test_inventory` added).
  - `.codegenie/context/raw/{node_build_system,node_manifest,ci,deployment,test_inventory}.json` per probe.
  - `src/codegenie/catalogs/native_modules.yaml` (10 seed entries) — Phase 7's input.
  - `src/codegenie/catalogs/ci_providers.yaml` — Phase 2 may extend.
  - `tests/golden/node_typescript_helm.repo-context.yaml` — seed golden; Phase 2 extends to its broader portfolio.

- **New contracts ready for Phase 2 consumers:**
  - `ProbeContext.parsed_manifest` callable + `ProbeContext.input_snapshot` (ADR-0002). Phase 2 probes reading `package.json` or any allowlisted manifest reuse the memo at zero implementation cost; extend the allowlist additively when needed.
  - `parsers/safe_json`, `safe_yaml`, `jsonc` (`O_NOFOLLOW` + size + depth caps). Phase 2's `semgrep` JSON-output parsing and `scip-typescript` JSON-line parsing both route through `safe_json.load`; no per-probe duplication.
  - Per-probe sub-schemas with `additionalProperties: false` at root (ADR-0004). Phase 2's Layer B/C/D/G sub-schemas use the same pattern; envelope `$ref` composition continues.
  - `WarningId` pattern `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` (ADR-0007). Phase 2's `IndexHealthProbe` aggregates warnings from every Phase 1 probe and groups by prefix.
  - Native-module catalog versioning pattern (ADR-0006). Phase 7's catalog updates cleanly invalidate Phase 1 cached `node_manifest` entries.
  - `Probe.declared_raw_artifact_budget_mb` (Gap 2 resolution). Phase 2 probes inherit the 5 MB default; SCIP-index dumps and depgraph artifacts override as needed.

- **New CI gates in place:**
  - Coverage ratchet at 90% line / 80% branch on `src/codegenie/` (excluding `cli.py`); per-module 85/75 carve-outs for `probes/deployment.py` and `probes/ci.py` (ADR-0005).
  - Adversarial corpus of ≥ 10 new fixtures (in addition to Phase 0's seven) gating every PR.
  - Golden-file diff gate on `node_typescript_helm`.
  - The `fence` job continues to assert (no LLM SDK creep); `security` job's closure now includes `pyarn` (optional).

- **Implicit assumptions Phase 2 can now make:**
  - Layer A is deterministic end-to-end; same inputs → same six slices.
  - In-process parse caps (size + depth + `O_NOFOLLOW`) are universal across the gather pipeline; Phase 2 inherits the threat closure.
  - The Wave-1 prelude pass populates `enriched_snapshot.detected_languages` before Wave 2 dispatches; Phase 2's language-conditional probes can filter on `applies_to_languages` correctly from day one.
  - The `additional_providers` and `environments` list-shaped fields are stable contracts; Phase 2 consumers handle the list shape.
  - Cache invalidation scope is per-probe-sub-schema (Phase 0 Gap 1 resolution carried forward + extended by ADR-0006 for the catalog); editing one probe's sub-schema or one catalog file invalidates only that probe's cache entries.
  - The TOCTOU window between `declared_inputs` content-hashing and probe parse is closed by the pre-dispatch input-snapshot pass (Gap 1 from `phase-arch-design.md`).
