# Phase 02 — Context gathering — Layers B–G: High-level implementation plan

**Status:** Implementation plan
**Date:** 2026-05-14
**Architecture reference:** [phase-arch-design.md](phase-arch-design.md)
**ADRs:** [ADRs/](ADRs/)
**Source design:** [final-design.md](final-design.md)
**Roadmap reference:** [docs/roadmap.md](../../roadmap.md) §"Phase 2 — Context gathering — Layers B–G"

## Executive summary

The engineer lands seven new top-level packages on top of the Phase 0/1 spine (`indices/`, `adapters/`, `tccm/`, `skills/`, `conventions/`, `depgraph/`, `report/`) plus every language-agnostic Layer B–G probe `localv2.md` §5.2–5.6 names. The phase is sequenced as **contracts → kernel scaffolding → writer-chokepoint redaction → probes → adversarial gates → fixtures + CI ratchet**. The load-bearing exit is `tests/adv/phase02/test_stale_scip_fixture.py`, a CI-gating assertion that `IndexHealthProbe` (B2) catches a deliberately-seeded staleness case in the `tests/fixtures/portfolio/stale-scip/` fixture. Eight steps. The `Probe` ABC stays frozen; scheduling concerns ride on `@register_probe(heaviness=…, runs_last=…)` decorator kwargs; the **one** Phase-0-contract amendment is the optional `ProbeContext.image_digest_resolver` callable (ADR-0004, mirroring Phase 1's `parsed_manifest` precedent). No Plugin Loader, no `plugin.yaml` parser, no plaintext secrets persisted anywhere.

## Order of operations

The ordering principle is **types first → kernel scaffolds second → security chokepoint third → probes fourth → adversarial + fixtures + CI fifth**. Step 1 plants the new domain primitives — `IndexFreshness` sum type, ADR-0033 newtypes (`IndexId`, `SkillId`, `TaskClassId`, `PackageManager` import), adapter `Protocol`s, `TCCM` Pydantic model, `run_external_cli`, `@register_probe` heaviness annotations, the `ProbeContext.image_digest_resolver` extension, and the nine new ADRs — *before any probe ships*. Without these, every subsequent probe would either re-invent the typing or couple to wrong shapes. Step 2 lands the kernel-side loaders (`TCCMLoader`, `SkillsLoader`, `ConventionsCatalogLoader`, `@register_index_freshness_check` and `@register_dep_graph_strategy` registries) so the probes consuming them in Steps 4–6 have a typed target. Step 3 lands `SecretRedactor` + `RedactedSlice` smart constructor at the writer chokepoint *before* any scanner probe persists output — security must precede the first user of the security chokepoint. Step 4 ships the load-bearing `IndexHealthProbe` (B2) plus the SCIP, tree-sitter, depgraph, and other Layer B probes, with B2's stale-scip fixture wired as a build-gating adversarial test the moment it can run. Step 5 ships the Layer C runtime/security probes (`RuntimeTraceProbe`, `Dockerfile`, `SBOM`, `CVE`, certificate, entrypoint, shell-usage). Step 6 ships the Layer D/E/G probes (skills index, conventions, ADRs, ownership stub, semgrep/ast-grep/ripgrep-curated/gitleaks/test-coverage-mapping). Step 7 lands the five-repo fixture portfolio + per-probe golden files + remaining adversarial corpus. Step 8 closes the Confidence section renderer, the CI ratchet (`mypy --warn-unreachable` per-module, eight CI jobs), advisory benches, and the Phase-3 handoff smoke test (skipped). Heaviness annotation lands with the registry change in Step 1, not separately. The allowlist additions (`semgrep`, `syft`, `grype`, `gitleaks`, `tree-sitter`, `docker`, `strace`, `scip-typescript`) land in Step 1 alongside `run_external_cli` because they're prerequisites for Steps 5/6.

## Step 1 — Plant new domain primitives, kernel contracts, and the nine new ADRs

**Goal:** Every typed surface every Phase 2 component will consume — `IndexFreshness`, adapter `Protocol`s, `AdapterConfidence`, `TCCM`/`DerivedQuery` models, ADR-0033 newtypes, `run_external_cli`, `@register_probe(heaviness=, runs_last=)` decorator kwargs, the `ProbeContext.image_digest_resolver` extension, and the nine new ADRs — exists on disk, type-strict, and unit-tested in isolation before any probe ships.

**Features delivered:**

- `src/codegenie/indices/__init__.py`, `freshness.py` per `phase-arch-design.md §"Component design" #2` and §"Data model" — `Fresh`, `Stale`, `CommitsBehind`, `DigestMismatch`, `CoverageGap`, `IndexerError`, `StaleReason`, `IndexFreshness`. All Pydantic `frozen=True, extra="forbid"`, `Literal["..."]` discriminator on `kind`, `Annotated[Union[...], Field(discriminator="kind")]`. `__all__` exports the full variant set.
- `src/codegenie/indices/registry.py` — `@register_index_freshness_check(index_name: IndexName)` decorator-registry per `phase-arch-design.md §"Gap 3"`. Each Phase-2 index source will register a small function `(slice: dict[str, JSONValue], head: str) -> IndexFreshness`. Open/Closed seam for B2 lands here, not in Step 4.
- `src/codegenie/adapters/__init__.py`, `protocols.py`, `confidence.py` per §"Component design" #7. Four `@runtime_checkable Protocol` classes (`DepGraphAdapter`, `ImportGraphAdapter`, `ScipAdapter`, `TestInventoryAdapter`); `AdapterConfidence = Trusted | Degraded | Unavailable` discriminated union. Zero implementations. Pure typing, ~80 LOC total.
- `src/codegenie/tccm/__init__.py`, `model.py`, `queries.py`, `loader.py` per §"Component design" #8. `TCCM` Pydantic model (`frozen=True, extra="forbid"`); `DerivedQuery = ConsumersOf | ProducersOf | ReverseLookup | RefsTo | TestsExercising` — five variants, no `Unknown` (ADR-amend on a sixth). `TCCMLoader.load(path) -> Result[TCCM, TCCMLoadError]`. Routes through `codegenie.parsers.safe_yaml.load` (Phase 1 chokepoint).
- `src/codegenie/types/identifiers.py` — ADR-0033 newtypes: `IndexId = NewType("IndexId", str)`, `SkillId = NewType("SkillId", str)`, `TaskClassId = NewType("TaskClassId", str)`, `IndexName = NewType("IndexName", str)`. `PackageManager` is imported from Phase 1 ADR-0013 (`codegenie.probes.layer_a.node_build_system`), **never redefined**.
- `src/codegenie/exec.py` extended — `run_external_cli` per §"Component design" #3. Wraps Phase 0 `run_allowlisted`; env strip to Phase 0 allowlist; optional `bubblewrap --unshare-net --ro-bind <repo> /work --bind <tmpdir> /tmp/probe` wrap on Linux when `bwrap` is on PATH (graceful no-op on macOS or when missing); `stdout`/`stderr` capped 64 MB tail-included. Layer C (`docker`, `strace`) calls `run_allowlisted` directly with `--network=none --cap-drop=ALL --security-opt=no-new-privileges`.
- `src/codegenie/exec.py` allowlist amendment — `ALLOWED_BINARIES` extended from Phase 0/1's `{"git", "node"}` to `{"git", "node", "semgrep", "syft", "grype", "gitleaks", "scip-typescript", "ast-grep", "ripgrep", "tree-sitter", "docker", "strace"}` (ADR-0001).
- `src/codegenie/probes/registry.py` extended — `@register_probe(heaviness: Literal["light","medium","heavy"]="light", runs_last: bool=False)` decorator kwargs land per §"Component design" #1 and ADR-0003. The `Probe` ABC is **not** edited. `ProbeRegistry.sorted_for_dispatch()` returns `list[ProbeRegEntry]` ordered heavy-first with `runs_last=True` reserved for the tail. Coordinator reads this sort order.
- `src/codegenie/coordinator/coordinator.py` extended (ADR-gated sort-order edit only) — reads `heaviness` + `runs_last` from registry; single `Semaphore(min(cpu_count(), 8))` is preserved (no per-tier semaphores, no `pytest-xdist`); `runs_last=True` probes dispatch after every sibling.
- `src/codegenie/probes/base.py` extended — **one** additive field on `ProbeContext`: `image_digest_resolver: Callable[[Path], str | None] | None = None` (ADR-0004, mirroring Phase 1 ADR-0002's `parsed_manifest` precedent). The `Probe` ABC itself is **not edited**. Phase 0 contract-freeze snapshot (`tests/unit/test_probe_contract.py`) regenerates with this single documented addition; further edits fail with the ADR-0004 pointer.
- `src/codegenie/depgraph/__init__.py`, `model.py`, `registry.py` — `@register_dep_graph_strategy(ecosystem: PackageManager)` decorator-registry per §"Component design" #11. Zero strategies in Phase 2 (the strategy registry is the Open/Closed seam Phase 3 consumes). `PackageManager` is imported from Phase 1 ADR-0013, not redefined.
- `src/codegenie/output/sanitizer.py` extended — `forbidden-patterns` pre-commit (Phase 0) extended to ban `model_construct` under `src/codegenie/{indices,tccm,skills,conventions,adapters,depgraph}/**` (§"Anti-patterns avoided" row 12). `mypy --warn-unreachable` per-module enabled in `pyproject.toml` for `codegenie.{indices, probes.layer_b.index_health, report, adapters, tccm}/**`.
- ADR files in `docs/phases/02-context-gather-layers-b-g/ADRs/` (Nygard format) per §"Path to production end state":
  - 02-ADR-0001 — Add `docker` + security-CLI binaries to `ALLOWED_BINARIES`.
  - 02-ADR-0002 — `py-tree-sitter` C-extension amendment to Phase 1 ADR-0009 (the **one** named trigger).
  - 02-ADR-0003 — `@register_probe(heaviness=, runs_last=)` registry annotations; coordinator sort-order edit.
  - 02-ADR-0004 — Image digest as declared-input token; introduces `ProbeContext.image_digest_resolver`.
  - 02-ADR-0005 — Secret findings: no plaintext persistence; Phase 5 microVM is the cleartext escalation door.
  - 02-ADR-0006 — `IndexFreshness` sum-type location at `codegenie.indices.freshness` (consumer is `report/confidence_section.py`).
  - 02-ADR-0007 — No Plugin Loader in Phase 2; Phase 3 ships loader + first plugin + adapters together.
  - 02-ADR-0008 — No event stream in Phase 2 (defers to ADR-0034 §Consequences §1).
  - 02-ADR-0009 — `pytest-xdist` veto preserved (re-affirms Phase 0's 10/4 vote).

**Done criteria:**

- [ ] `tests/unit/indices/test_freshness.py` covers every variant constructible; round-trip identity (`model_dump_json` ↔ `model_validate_json`); exhaustive `match` test with `assert_never` on every `StaleReason`; `mypy --warn-unreachable` build error fires when a `match` arm is removed.
- [ ] `tests/unit/indices/test_freshness_registry.py` covers `@register_index_freshness_check` registry; duplicate-name rejection; total dispatch over registered index names.
- [ ] `tests/unit/adapters/test_protocols.py` covers `runtime_checkable` structural conformance for each of the four Protocols (a minimal stub satisfies `isinstance`); `AdapterConfidence` variants construct and round-trip.
- [ ] `tests/unit/tccm/test_loader.py` covers `safe_yaml` chokepoint usage; happy-path load; unknown `compute:` variant → `Result.Err(TCCMLoadError(reason="unknown_query_primitive"))`; schema violation → `Result.Err(reason="schema")`.
- [ ] `tests/unit/tccm/test_queries.py` covers the five `DerivedQuery` variants round-trip through `model_dump_json`/`model_validate_json`.
- [ ] `tests/unit/exec/test_run_external_cli.py` covers env strip (no `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`/`GITHUB_TOKEN`/`AWS_*`/`SSH_AUTH_SOCK` reaches the child); stdout cap at 64 MB with tail; `bubblewrap` graceful no-op on macOS; timeout via `asyncio.wait_for`; non-zero exit → `ProcessResult(exit_code=N, stderr_tail=...)`.
- [ ] `tests/unit/exec/test_allowed_binaries.py` extended — all eleven new binaries present in `ALLOWED_BINARIES`; env-strip continues to drop the existing sensitive var list.
- [ ] `tests/unit/probes/test_registry.py` extended — `@register_probe(heaviness="heavy", runs_last=True)` sorts heavy-first with `runs_last` reserved for the tail; default `heaviness="light"`, `runs_last=False`.
- [ ] `tests/unit/coordinator/test_coordinator_sort_order.py` — synthetic registry of light + medium + heavy + `runs_last` probes dispatches in the asserted order under `Semaphore(min(cpu_count(), 8))`.
- [ ] `tests/unit/test_probe_contract.py` snapshot regenerated with `ProbeContext.image_digest_resolver` documented in the ADR-0004 amendment; any further edit fails with the ADR pointer.
- [ ] `tests/unit/depgraph/test_registry.py` — `@register_dep_graph_strategy(ecosystem=PackageManager.PNPM)` registers; unknown ecosystem → typed error; `PackageManager` enum is imported from Phase 1, not redefined.
- [ ] `forbidden-patterns` pre-commit hook updated and CI green: `model_construct` under the new packages fails CI.
- [ ] All nine ADR files exist, are Nygard-format, and link from `docs/phases/02-context-gather-layers-b-g/README.md`.
- [ ] `mypy --strict` passes repo-wide; `mypy --warn-unreachable` per-module overrides pass for the four named modules.
- [ ] `ruff` clean on all Step 1 code.
- [ ] Phase 0 `fence` job stays green (no `anthropic`/`openai`/`langgraph`/`httpx`/`requests`/`socket` import under `src/codegenie/`).
- [ ] Phase 0 `contract-freeze` job stays green (the only documented amendment is the ADR-0004 field).

**Depends on:** Phase 1 ships and `main` is green; the Phase 1 `parsers.safe_yaml`, `PackageManager` enum, and `ParsedManifestMemo` are on disk.

**Effort:** L — the densest step in the phase. Seven new packages, nine ADRs, one Phase-0-contract amendment, eleven allowlist additions, two new decorator-registries, the coordinator sort-order edit, and the `mypy --warn-unreachable` per-module rollout all land here. Every probe in Steps 4–6 depends on these primitives.

**Risks specific to this step:** The `ProbeContext.image_digest_resolver` extension is the only Phase-0-contract amendment in the entire phase — encode the allowed field list inside the snapshot-regeneration script (same discipline as Phase 1 Step 1) so a later contributor cannot widen it silently. The `@register_probe(heaviness=, runs_last=)` kwargs are decorator-data, not ABC fields — if any reviewer suggests "promote heaviness onto the `Probe` ABC for type-safety," the answer is ADR-0003 (and the design-patterns toolkit row 4). The `mypy --warn-unreachable` per-module rollout must NOT be applied repo-wide — Phase 0/1 blast radius (final-design §"Open Q 5"). The eleven allowlist additions are auditable surface; do not add a binary speculatively — every entry must have a Step-4/5/6 consumer named in this plan.

## Step 2 — Plant kernel-side loaders (`SkillsLoader`, `ConventionsCatalogLoader`) and reference TCCM

**Goal:** The three loaders (`TCCMLoader` from Step 1, plus `SkillsLoader` and `ConventionsCatalogLoader` here) all exist with `O_NOFOLLOW` opens, safe_yaml-chokepointed parsing, three-tier merge semantics, and typed `Result.Err` failure paths. A reference TCCM under `docs/_reference-tccm/tccm.yaml` round-trips through `TCCMLoader` so the typed surface has a Phase-2 consumer from day one.

**Features delivered:**

- `src/codegenie/skills/__init__.py`, `model.py`, `loader.py` per §"Component design" #9. `Skill` Pydantic model (`frozen=True, extra="forbid"`): `id: SkillId`, `applies_to_tasks: list[str]`, `applies_to_languages: list[str]`, `body_offset: int`, `body_size: int`, `body_blake3: str`. `SkillsLoader(search_paths: list[Path])` is pure data at `__init__`; first I/O is `load_all() -> Result[list[Skill], SkillsLoadError]`. Per `SKILL.md` file: `os.open(path, O_NOFOLLOW | O_NOCTTY)` → `os.fdopen` → `codegenie.parsers.safe_yaml.load` (Phase 1 chokepoint). Body byte-offset recorded only; body is **not** loaded into memory (progressive-disclosure commitment). Three-tier merge across `~/.codegenie/skills/`, `.codegenie/skills/`, optional `~/.codegenie/skills-org/`: first-tier-wins; collisions emit a `skill_shadowed` warning in the CLI summary.
- `src/codegenie/conventions/__init__.py`, `model.py`, `catalog.py` per §"Component design" #10. `ConventionResult = Pass | Fail | NotApplicable` discriminated union. Pattern types (`dockerfile_pattern`, `dockerfile_pattern_inverted`, `file_pattern`, `missing_file`) are a Pydantic discriminated union; one `match` per pattern type with `assert_never` on unreachable. `ConventionsCatalogLoader(search_paths).load_all() -> Result[Catalog, ConventionsError]`; `Catalog.apply(repo: RepoSnapshot) -> list[ConventionResult]`. Routes through `safe_yaml.load`.
- `docs/phases/02-context-gather-layers-b-g/_reference-tccm/tccm.yaml` — illustrative manifest for an `index-health-self-check` task class. **Documentation, not a plugin**: lives under `docs/`, not `plugins/`. Exercises every field of `TCCM` + every `DerivedQuery` variant.
- `tests/integration/tccm/test_reference_tccm_roundtrips.py` — loads the reference TCCM via `TCCMLoader`; asserts the loaded model equals an expected hand-constructed Pydantic instance; exercises every Protocol method via a mock dispatcher (closes the "Protocols defined, never called in Phase 2" critique from `phase-arch-design.md §"Gap 1"`).

**Done criteria:**

- [ ] `tests/unit/skills/test_loader.py` covers frontmatter parsing happy path; `O_NOFOLLOW` ELOOP → `Result.Err(SkillsLoadError(reason="symlink_refused", path))`; `!!python/object` payload → `SkillsLoadError(reason="unsafe_yaml")` (via `safe_yaml`); three-tier merge first-tier-wins; `skill_shadowed` warning on collision; body byte-offset recorded but body **not** loaded into memory (verified by `tracemalloc` peak < 20 KB on a 100 MB-body fixture).
- [ ] `tests/unit/conventions/test_catalog.py` covers one test per pattern type; `NotApplicable` path; `assert_never` on an unknown pattern type → `Result.Err(ConventionsError(reason="unknown_pattern_type"))`.
- [ ] `tests/property/test_skills_loader_monotone.py` (Hypothesis) — `SkillsLoader.find_applicable(evidence_keys)` is monotone: adding a key never removes a match.
- [ ] `tests/integration/tccm/test_reference_tccm_roundtrips.py` passes; every Protocol method is invoked at least once via the mock dispatcher.
- [ ] All Step 2 code passes `mypy --strict` + `mypy --warn-unreachable` (per-module on `codegenie.tccm/**`).
- [ ] `forbidden-patterns` continues to ban `model_construct` under the new packages.

**Depends on:** Step 1 (newtypes, `IndexFreshness`, adapter Protocols, `TCCM` model, `safe_yaml` already in Phase 1).

**Effort:** M — three loaders, one of which is a Phase-1 pattern repeat (`safe_yaml` + `O_NOFOLLOW`). The reference-TCCM roundtrip integration test is the load-bearing piece — it gives `TCCM`/`DerivedQuery` a real consumer in Phase 2.

**Risks specific to this step:** The progressive-disclosure commitment for skills (body byte-offset, not loaded) must be verified by `tracemalloc`, not just by visual code inspection — a future contributor adding `body: str` to `Skill` would silently break the commitment without that test. The three-tier merge order (`~/.codegenie/skills/` first vs. `.codegenie/skills/` first) is a one-line decision but its inversion is a security regression; lock it down by enumerating the three tiers in `SkillsLoader.__init__` argument order and asserting the order in tests.

## Step 3 — Plant `SecretRedactor` + `RedactedSlice` smart constructor at the writer chokepoint

**Goal:** Every byte that flows from a `ProbeOutput.schema_slice` to `repo-context.yaml`, `raw/*.json`, the cache blob, and the audit anchor passes through `redact_secrets`. Plaintext is in **zero** persisted files. The `RedactedSlice` smart constructor makes "redactor was called" type-checkable (`phase-arch-design.md §"Gap 4"`).

**Features delivered:**

- `src/codegenie/output/sanitizer.py` extended with `SecretRedactor` per §"Component design" #4 and §"Gap 4". `redact_secrets(slice_, probe_name) -> RedactedSlice` (the **only** function that can construct a `RedactedSlice`). Patterns: AWS `AKIA[0-9A-Z]{16}`, GitHub `ghp_[A-Za-z0-9]{36}`, JWT, RSA private-key block, NPM `npm_…`, Anthropic `sk-ant-…`, plus Shannon-entropy ≥ 4.5 bits/char for `len ≥ 32` unknowns. Fingerprint = first 8 hex of BLAKE3 of the cleartext (`codegenie.hashing.content_hash` — Phase 0).
- `src/codegenie/output/redacted_slice.py` per §"Gap 4". `RedactedSlice` Pydantic model (`frozen=True, extra="forbid"`): `slice: dict[str, JSONValue]`, `findings_count: int`, `fingerprints: list[str]` (8-hex only — no plaintext). Construction is private (`model_construct` banned by Step 1's `forbidden-patterns` extension); the **only** public path is `redact_secrets(...)`.
- `src/codegenie/output/writer.py` extended — writer signature tightens from `dict[str, JSONValue]` to `RedactedSlice`. The chokepoint is type-enforced: a caller that drops the findings list cannot fake a `RedactedSlice`.
- `OutputSanitizer.scrub` composition — Phase 0's field-name regex + `JSONValue` tree walk runs **before** `redact_secrets`; the order is documented in the module docstring and verified by Step 7's `test_no_inmemory_secret_leak.py`.
- `src/codegenie/logging.py` — one new log field at the writer: `secrets_redacted_count: int` (a 0-count run is grep-able). Per §"Harness engineering".

**Done criteria:**

- [ ] `tests/unit/output/test_secret_redactor.py` covers each pattern class matches (AWS, GitHub, JWT, RSA, NPM, Anthropic); entropy threshold catches a generic high-entropy string of length 32+; fingerprint is exactly 8 hex chars; **mutation test**: a deliberately weakened regex (`AKIA[0-9A-Z]{15}`) causes the test to FAIL — pattern failure is a build failure.
- [ ] `tests/unit/output/test_redacted_slice.py` covers construction is private; `model_construct` raises (banned by `forbidden-patterns`); `redact_secrets` is the only public path; round-trip identity through `model_dump_json` / `model_validate_json`.
- [ ] `tests/unit/output/test_writer_signature.py` — writer accepts `RedactedSlice` and refuses raw `dict` at type-check time (verified by `reveal_type` in a `mypy`-only test file).
- [ ] `tests/unit/output/test_sanitizer_composition.py` — `OutputSanitizer.scrub` invokes `redact_secrets` as its final pass; the call ordering is verified by mock spy.
- [ ] `secrets_redacted_count` log field present in `logging.py` constants and emitted on every gather.
- [ ] All Step 3 code passes `mypy --strict` + `mypy --warn-unreachable` repo-module overrides.

**Depends on:** Step 1 (`ProbeId` newtype, `forbidden-patterns` extension covers the new package).

**Effort:** S — six secret-pattern classes + one smart-constructor model + one type-tightening of the writer signature. The mutation-test discipline is the largest piece (one mutation per pattern class).

**Risks specific to this step:** The `RedactedSlice` smart constructor is the type-level "redactor was called" proof — if a future contributor adds a second public constructor path (`RedactedSlice.from_existing(...)`), the guarantee silently breaks. Document the invariant in the module docstring and add a Step 7 `inspect`-based structural test asserting `RedactedSlice.__init__` is the only public factory and `redact_secrets` is the only call site. The entropy threshold (≥ 4.5 bits/char) is empirically chosen — tune by adversarially diffing against the gitleaks pattern pack at land-time and document the threshold's source in the module docstring, not just in the test.

## Step 4 — Ship `IndexHealthProbe` (B2) + Layer B structural probes

**Goal:** The load-bearing roadmap exit probe (`IndexHealthProbe`) ships with the stale-scip adversarial test green-or-failing-build; the other Layer B probes — SCIP-index, tree-sitter import-graph, dep-graph, generated-code, node-reflection, semantic-index-metadata — round out the structural-layer evidence Phase 3 consumes.

**Features delivered:**

- `src/codegenie/probes/layer_b/index_health.py` per §"Component design" #1. `@register_probe(runs_last=True)`; `cache_strategy="none"` (forbidden by per-module pre-commit hook: `os.path.getmtime`, `Path.stat().st_mtime` are not freshness signals). `timeout_seconds=10`. Reads sibling slices (`last_indexed_commit`, `files_indexed`, `files_in_repo`, `indexer_errors`, `last_traced_image_digest`, `built_image_digest`, `rule_pack_version`) + `git rev-parse HEAD` via `run_allowlisted`. Dispatches via Step 1's `@register_index_freshness_check` registry (Open/Closed seam); the probe's `run()` loops the registry. Phase-2 index sources register their freshness-check functions here (one new file each, never an edit to `index_health.py`). Construction failures emit `IndexFreshness.Stale(reason=IndexerError(...))` (never raises).
- `src/codegenie/probes/layer_b/scip_index.py` per `localv2.md` §5.2 B1. `@register_probe(heaviness="heavy")`. `run_external_cli("scip-typescript", ...)`; emits binary blob to `.codegenie/context/raw/scip-index.scip` (Phase 3's `ScipAdapter` decides consumption shape — Phase 2 emits only). Cache key sensitive to tool-version + Merkle of `.ts` files. Timeout 300 s → `IndexerError(message="timeout")`.
- `src/codegenie/probes/layer_b/tree_sitter_import_graph.py` per §"Component design" #12 and ADR-0002. `@register_probe(heaviness="medium")`. `py-tree-sitter` in-process; **no internal `ThreadPoolExecutor`** (honesty to coordinator's single semaphore). Grammar `.so`/`.dylib` BLAKE3-pinned in `tools/grammars.lock`; load-time mismatch → `GrammarLoadRefused`; probe slice `confidence="low"`; no grammar code executes. Emits forward-only adjacency to `raw/import-graph.json`.
- `src/codegenie/probes/layer_b/dep_graph.py` per §"Component design" #11. `@register_probe`. Reads Phase 1 `manifests` + `build_system` slices; dispatches via Step 1's `@register_dep_graph_strategy` registry (zero strategies in Phase 2 — strategy registry is the Open/Closed seam Phase 3 fills). Unknown ecosystem → typed `DepGraphProbeOutput(confidence="low", reason="no_strategy_for_ecosystem")`. Emits `raw/dep-graph.json`.
- `src/codegenie/probes/layer_b/generated_code.py`, `node_reflection.py`, `semantic_index_meta.py` per `localv2.md` §5.2 — each ≤ 100 LOC, marker-based detection, no parsing beyond what Phase 1 parsers already supply.
- `src/codegenie/schema/probes/{index_health,scip_index,tree_sitter_import_graph,dep_graph,generated_code,node_reflection,semantic_index_meta}.schema.json` — `additionalProperties: false` at each root (Phase 1 ADR-0004 convention).
- `src/codegenie/probes/__init__.py` — explicit registration of each Layer B probe (additive imports).
- `tools/grammars.lock` — BLAKE3-pinned grammar files for the languages Phase 2 supports (TypeScript + JavaScript at minimum). Regeneration script under `tools/regenerate_grammars_lock.sh` (reviewed-as-code).
- **The load-bearing adversarial test** — `tests/adv/phase02/test_stale_scip_fixture.py` lands here. Fixture `tests/fixtures/portfolio/stale-scip/` (planted in Step 7's fixture portfolio, but stub here for now): pre-populated SCIP from prior commit; HEAD has moved. Asserts `IndexFreshness.Stale(reason=CommitsBehind(n >= 1, last_indexed=<prior>))`. **Build FAILS if B2 does not catch it.** This is the roadmap exit criterion.

**Done criteria:**

- [ ] `tests/unit/probes/layer_b/test_index_health_probe.py` — per-source freshness construction; every `IndexFreshness` variant constructible from synthetic sibling slices; `cache_strategy="none"` enforced (pre-commit hook fires on a deliberate attempt to add caching); `runs_last=True` registry annotation present; sibling-missing path emits `Stale(IndexerError(message=f"upstream_{name}_unavailable"))`.
- [ ] `tests/unit/probes/layer_b/test_scip_index.py` — `scip-typescript` invocation argv; cache-key sensitivity to tool-version + `.ts` Merkle; timeout → `IndexerError`.
- [ ] `tests/unit/probes/layer_b/test_tree_sitter_import_graph.py` — per-file extraction; no internal thread pool (verified by `tracemalloc`/thread-count assertion); grammar pin verified at load (mismatched `.so` → `GrammarLoadRefused`).
- [ ] `tests/unit/probes/layer_b/test_dep_graph.py` — `@register_dep_graph_strategy` registry exercised with a mock strategy; unknown ecosystem → typed low-confidence output.
- [ ] `tests/unit/probes/layer_b/test_generated_code.py`, `test_node_reflection.py`, `test_semantic_index_meta.py` — happy-path + marker-absent paths.
- [ ] **`tests/adv/phase02/test_stale_scip_fixture.py`** asserts `isinstance(slice.freshness, Stale)`, `isinstance(slice.freshness.reason, CommitsBehind)`, `slice.freshness.reason.n >= 1`. **CI-gating.**
- [ ] All Step 4 code passes `mypy --strict` + `mypy --warn-unreachable` (per-module on `codegenie.probes.layer_b.index_health`).
- [ ] `tools/grammars.lock` BLAKE3 hashes verified against the vendored grammar binaries.

**Depends on:** Steps 1–3 (newtypes, freshness registry, run_external_cli, redaction chokepoint).

**Effort:** L — seven Layer B probes; `IndexHealthProbe` is the load-bearing one but the SCIP + tree-sitter + dep-graph trio is the densest implementation work. The `py-tree-sitter` integration is the **only** C-extension dep accepted in Phase 2 (ADR-0002 named trigger).

**Risks specific to this step:** The `stale-scip` fixture is structurally asserted (`CommitsBehind.n >= 1`, tool-version-agnostic). Do **not** assert on a specific commit count — the fixture regeneration policy lives in `tests/fixtures/portfolio/stale-scip/README.md` (Step 7) and the test must survive regeneration. The `cache_strategy="none"` discipline on `IndexHealthProbe` is the load-bearing correctness invariant — caching freshness is "the same bug as caching `Date.now()`" (§"Harness engineering"); a future contributor proposing "let's cache B2 for performance" must be redirected to the per-module pre-commit hook. The `tree_sitter_import_graph` no-internal-`ThreadPoolExecutor` rule is the honesty-to-the-coordinator commitment — verify by enumerating thread count, not just by absence of `threading` import.

## Step 5 — Ship Layer C (runtime + container) probes

**Goal:** The container/runtime evidence Phase 3's distroless and runtime-trace consumers (Phases 3 + 7) need is gathered. `RuntimeTraceProbe` is the densest piece; the remaining Layer C probes (`Dockerfile`, `SBOM`, `CVE`, certificate, entrypoint, shell-usage) are marker-driven and shallower.

**Features delivered:**

- `src/codegenie/probes/layer_c/runtime_trace.py` per §"Component design" #6. `@register_probe(heaviness="heavy")`. Reads `.codegenie/scenarios.yaml` (Pydantic-validated; falls back to 5 defaults: `startup`, `smoke_test`, `healthcheck`, `shutdown`, `error_path`). Sequential per-scenario execution (multiple `docker run` of the same image race resources). Per scenario: `docker build` → `docker run --network=none --cap-drop=ALL --security-opt=no-new-privileges` + `strace -f` (Linux) / `TraceScenarioFailed(StraceUnavailable())` (macOS). All `docker`/`strace` calls via `run_allowlisted` directly (not `run_external_cli`). Per-scenario timeout 120 s; aggregate 600 s. `ScenarioResult = TraceScenarioCompleted | TraceScenarioFailed | TraceScenarioSkipped`.
- `RuntimeTraceProbe.declared_inputs` includes `Dockerfile`, `.codegenie/scenarios.yaml`, AND a special declared-input token `image-digest:<resolved>` resolved via `ProbeContext.image_digest_resolver` (Step 1 ADR-0004 amendment). On cache HIT against image-digest token, scenarios skip.
- `src/codegenie/probes/layer_c/dockerfile.py` — Dockerfile parser (marker + line-by-line; no shell evaluation). Captures `FROM` chain, `USER`, `EXPOSE`, `HEALTHCHECK`, `CMD`/`ENTRYPOINT` literals. Sub-schema per `localv2.md` §5.3.
- `src/codegenie/probes/layer_c/sbom.py` — `@register_probe(heaviness="medium")`. `run_external_cli("syft", [<image>, "-o", "json"])` with `--metrics=off`-equivalent flag. 30 s timeout. Requires `RuntimeTraceProbe` image; `requires=["runtime_trace"]` enforces dispatch order. `ScannerOutcome` discriminated union per §"Component design" #5.
- `src/codegenie/probes/layer_c/cve.py` — `@register_probe(heaviness="medium")`. `run_external_cli("grype", ["sbom:<syft-output>", "-o", "json"])`. 30 s timeout. Reads `sbom` slice; emits `raw/grype-cves.json`.
- `src/codegenie/probes/layer_c/certificate.py`, `entrypoint.py`, `shell_usage.py` per `localv2.md` §5.3 — marker-and-parse, ≤ 80 LOC each.
- `src/codegenie/probes/layer_c/scenario_result.py` — `TraceScenarioCompleted | TraceScenarioFailed | TraceScenarioSkipped` Pydantic discriminated union.
- `src/codegenie/probes/layer_c/scanner_outcome.py` — `ScannerRan | ScannerSkipped | ScannerFailed` shared with Layer G; lives in `codegenie/probes/_shared/scanner_outcome.py` so both layers import the same type.
- Sub-schemas under `src/codegenie/schema/probes/layer_c/`.
- Registry entry for `@register_index_freshness_check("runtime_trace")` in `runtime_trace.py` — checks `last_traced_image_digest == built_image_digest`; mismatch → `Stale(DigestMismatch(...))`.

**Done criteria:**

- [ ] `tests/unit/probes/layer_c/test_runtime_trace.py` covers per-scenario sequential execution (no concurrency); per-scenario timeout (120 s); aggregate timeout (600 s); macOS `TraceScenarioFailed(StraceUnavailable())` deterministic path (no sudo prompt); `docker build` failure → all scenarios skip with `confidence="unavailable"`.
- [ ] `tests/unit/probes/layer_c/test_dockerfile.py` covers `FROM` chain extraction; multi-stage; `USER` directive parsing; `HEALTHCHECK` literal capture; no shell evaluation.
- [ ] `tests/unit/probes/layer_c/test_sbom.py`, `test_cve.py` cover `run_external_cli` invocation; Pydantic smart constructor on stdout JSON; tool-missing → `ScannerSkipped(reason="tool_missing")`; bad JSON → `ScannerFailed(reason="invalid_json", stderr_tail=…)`.
- [ ] `tests/unit/probes/layer_c/test_certificate.py`, `test_entrypoint.py`, `test_shell_usage.py` cover marker presence/absence paths.
- [ ] `tests/adv/phase02/test_image_digest_drift.py` (load-bearing adversarial) — mutating the built image between gathers invalidates tier-C caches via the image-digest declared-input token.
- [ ] `tests/adv/phase02/test_adversarial_dockerfile.py` — forkbomb / infinite-loop Dockerfile times out; container `--cap-drop=ALL --network=none --no-new-privileges` contains it; coordinator continues.
- [ ] `@register_index_freshness_check("runtime_trace")` registered; `IndexHealthProbe` constructs `Stale(DigestMismatch(...))` on a digest mismatch fixture.
- [ ] All Step 5 code passes `mypy --strict`.

**Depends on:** Steps 1–4 (`run_allowlisted` allowlist additions, `run_external_cli`, `IndexFreshness`, `image_digest_resolver` extension, `IndexHealthProbe`).

**Effort:** L — `RuntimeTraceProbe` is the largest single probe in the phase (5-scenario harness, container-hardening flags, macOS branch, image-digest token, sequential execution discipline). The five marker probes are mechanical.

**Risks specific to this step:** Per-scenario sequential execution is the load-bearing correctness invariant — concurrent `docker run` of the same image races resources and confuses attribution. A future contributor proposing parallel scenarios must be redirected to §"Component design" #6 and the tradeoff table. The macOS `StraceUnavailable` path must be **deterministic** — no sudo prompt (the test asserts no TTY interaction). The container-hardening flags (`--network=none --cap-drop=ALL --security-opt=no-new-privileges`) are non-negotiable; the `test_adversarial_dockerfile.py` is the proof.

## Step 6 — Ship Layer D + E + G probes (skills index, conventions, ADRs, ownership, semgrep/ast-grep/ripgrep/gitleaks/test-coverage)

**Goal:** The remaining language-agnostic probes ship — Layer D evidence-from-docs (skills index, conventions, ADRs, policy stubs, exceptions, repo notes, repo config, external docs), Layer E ownership and topology stubs, Layer G security/curated scanners (semgrep, ast-grep, ripgrep-curated, gitleaks, test-coverage-mapping). Each Layer G scanner produces output that flows through `SecretRedactor` at the writer chokepoint.

**Features delivered:**

- `src/codegenie/probes/layer_d/skills_index.py` — `@register_probe` (light). Calls `SkillsLoader` (Step 2); indexes `applies_to_tasks` and `applies_to_languages`. Emits slice with skill IDs only (body byte-offsets recorded; bodies not loaded).
- `src/codegenie/probes/layer_d/{conventions,adrs,policy,exceptions,repo_notes,repo_config,external_docs}.py` per `localv2.md` §5.4. Conventions uses `ConventionsCatalogLoader` (Step 2). `external_docs.py` ships opt-in skip-cleanly (final-design §"Open Q 4"); allowlist schema lands when the first real user opts in.
- `src/codegenie/probes/layer_e/{ownership,service_topology_stub,slo_stub}.py` per `localv2.md` §5.5 — marker-driven (`CODEOWNERS`, `service.yaml`, etc.); stubs for Phase 9+ topology + SLO.
- `src/codegenie/probes/layer_g/semgrep.py`, `syft.py` (already shipped in Step 5 under Layer C), `grype.py` (Step 5), `gitleaks.py`, `ast_grep.py`, `ripgrep_curated.py`, `test_coverage_mapping.py` per §"Component design" #5 and `localv2.md` §5.6.
  - Each is ≤ 200 LOC, **no shared `ScannerRunner` abstraction** (final-design §"Design patterns applied" row 7 — SRP + Rule of Three; four scanners with four genuinely different I/O shapes).
  - Pattern per scanner: (a) check tool via Phase 0 `tool_cache`; (b) invoke via `run_external_cli` with explicit argv (no shell; `--metrics=off` for `semgrep`; `--no-banner` for `gitleaks`); (c) parse stdout JSON via Pydantic smart constructor; (d) return `ProbeOutput` with `ScannerOutcome` discriminated union.
  - Per-probe timeouts: semgrep 60 s, gitleaks 30 s, ast-grep 30 s, ripgrep-curated 30 s.
  - All findings flow through `SecretRedactor` at the writer chokepoint (Step 3).
- Sub-schemas under `src/codegenie/schema/probes/layer_{d,e,g}/`.
- `@register_probe(heaviness="medium")` on every scanner probe (`semgrep`, `ast_grep`, `gitleaks`, `test_coverage_mapping`); `heaviness="light"` on the marker-driven Layer D/E probes.
- `@register_index_freshness_check` registrations for `semgrep` (rule-pack version), `gitleaks` (rule-pack version), `conventions` (catalog version).

**Done criteria:**

- [ ] `tests/unit/probes/layer_d/test_skills_index.py` — `SkillsLoader` integration; `applies_to_tasks` indexing; body byte-offsets recorded; bodies not loaded into memory.
- [ ] `tests/unit/probes/layer_d/test_conventions.py`, `test_adrs.py`, `test_repo_notes.py` cover happy path + marker-absent paths.
- [ ] `tests/unit/probes/layer_e/test_ownership.py` covers `CODEOWNERS` parsing; absent file → `confidence="low"`.
- [ ] `tests/unit/probes/layer_g/test_semgrep.py`, `test_gitleaks.py`, `test_ast_grep.py`, `test_ripgrep_curated.py`, `test_test_coverage_mapping.py` cover `run_external_cli` invocation argv; Pydantic smart constructor; `ScannerOutcome` variants; tool-missing path; bad-JSON path; mocked via `pytest-subprocess`.
- [ ] `tests/adv/phase02/test_secret_in_source.py` (load-bearing adversarial) — gitleaks finds a seeded secret; `SecretRedactor` replaces in `repo-context.yaml` + every raw artifact + cache blob + audit anchor. Plaintext in **zero** persisted files.
- [ ] `@register_index_freshness_check` registrations exercised — `IndexHealthProbe` constructs `Stale(...)` when a rule-pack version drifts between gathers.
- [ ] All Step 6 code passes `mypy --strict`.

**Depends on:** Steps 1–5 (loaders, run_external_cli, SecretRedactor, IndexHealthProbe).

**Effort:** L — ten+ probes, but each is shallow and structurally similar (run external CLI, parse JSON, return slice). The repeat-structure means most of the work is sub-schema authoring + Pydantic smart constructors, not algorithm.

**Risks specific to this step:** Resisting the urge to extract a "shared `ScannerRunner`" abstraction across the four Layer G scanners is the load-bearing discipline (final-design §"Design patterns applied" row 7). The ~60 LOC saved by sharing is not worth the speculative coupling — each scanner has a different I/O shape, error model, and rule-pack version. If a reviewer asks "why is there duplication," the answer is Rule-of-Three + the design table. The `external_docs.py` probe ships opt-in skip-cleanly — do **not** invent an allowlist schema speculatively; it lands when a real user opts in (final-design §"Open Q 4").

## Step 7 — Plant five-repo fixture portfolio + per-probe golden files + remaining adversarial corpus

**Goal:** The five fixture repos exist on disk with regeneration scripts; one golden file per probe per fixture lives under `tests/golden/probes/<probe>/<fixture>.json` and CI diffs are gating; the remaining adversarial corpus (`test_hostile_skills_yaml.py`, `test_concurrent_gather_race.py`, `test_no_inmemory_secret_leak.py`) lands.

**Features delivered:**

- `tests/fixtures/portfolio/minimal-ts/` — smallest happy path; smoke for every probe; ≤ 200 files.
- `tests/fixtures/portfolio/native-modules/` — C-extension manifest edge cases (e.g., `node-gyp`).
- `tests/fixtures/portfolio/monorepo-pnpm/` — `DepGraphProbe` cross-package edges; pnpm workspace.
- `tests/fixtures/portfolio/distroless-target/` — Layer C runtime trace against an already-distroless base image (Phase 7 forward-looking).
- `tests/fixtures/portfolio/stale-scip/` — **LOAD-BEARING.** Pre-populated SCIP from a prior commit; HEAD has moved. `README.md` documents the regeneration policy: structural assertion is `CommitsBehind.n >= 1`, tool-version-agnostic. Already referenced by Step 4's `test_stale_scip_fixture.py`; the fixture lands here.
- `tests/fixtures/portfolio/<name>/regenerate.sh` per fixture — reviewed-as-code. `.codegenie/cache/` is **NOT committed** to fixtures (regenerated each CI run; transparent diff).
- `tests/golden/probes/<probe>/<fixture>.json` per probe per fixture (~70 goldens total: ~14 probes × 5 fixtures). CI diffs live output vs. committed expected; `pytest --update-golden` regenerates; updating is a deliberate PR step.
- `scripts/regen_golden.py` — re-runs `codegenie gather` against each fixture and writes canonical JSON (sorted keys at every level). Wall-clock + audit-timestamp fields excluded.
- Adversarial corpus completion under `tests/adv/phase02/`:
  - `test_hostile_skills_yaml.py` — `!!python/object`, billion-laughs, deep nesting, symlink-escape filenames. ≥ 8 cases. None executes user code.
  - `test_concurrent_gather_race.py` — two concurrent gathers don't corrupt cache; Phase 0 advisory lock at `.codegenie/cache/.lock` holds.
  - `test_no_inmemory_secret_leak.py` (`phase-arch-design.md §"Gap 5"`) — boundary test asserting (via `inspect`) that every artifact reachable from `OutputSanitizer.scrub` passes through `redact_secrets`; the call is present and unbypassable.
  - `test_phase3_handoff_smoke.py` — lands `@pytest.mark.skip(reason="enabled when Phase 3 plugin lands")` per §"Gap 1". Enforces that Phase 3's first adapter implementation imports Phase 2's Protocols unchanged at Phase 3 entry-gate review.
- Property tests under `tests/property/`:
  - `test_index_freshness_roundtrip.py` (already may exist from Step 1's freshness tests; extended here for portfolio-wide round-trip).
  - `test_scanner_outcome_roundtrip.py` — `ScannerOutcome` ↔ JSON identity.
  - `test_dep_graph_strategy_dispatch.py` — registry dispatch total over `PackageManager` enum members.
  - `test_trace_coverage_well_formed.py` — `TraceCoverage` well-formed across any combination of `ScenarioResult` variants.

**Done criteria:**

- [ ] All five fixture repos exist; each `regenerate.sh` produces byte-identical output across two consecutive runs.
- [ ] `.codegenie/cache/` is **not** committed to any fixture (verified by `.gitignore` + CI check).
- [ ] ~70 golden files exist; CI diffs are gating; `pytest --update-golden` regenerates canonically.
- [ ] `scripts/regen_golden.py` excludes `wall_clock_ms`, `generated_at`, and audit-timestamp fields.
- [ ] Each adversarial test passes; `test_no_inmemory_secret_leak.py` uses `inspect` to verify `redact_secrets` is the only path from `ProbeOutput` to writer.
- [ ] `test_phase3_handoff_smoke.py` is skipped with the documented reason; the Phase 3 author finds it on first repo scan.
- [ ] All property tests pass under Hypothesis with `--max-examples=200`.
- [ ] All Step 7 code + fixtures + scripts pass `mypy --strict`, `ruff`, and the `forbidden-patterns` pre-commit.

**Depends on:** Steps 4–6 (every probe must exist before goldens can be generated).

**Effort:** M — five fixtures (mechanical) + 70 goldens (mechanical via regen script) + four adversarial tests + four property tests. The non-mechanical pieces are `test_no_inmemory_secret_leak.py` (`inspect`-based structural check) and the `stale-scip` regeneration policy documentation.

**Risks specific to this step:** Golden-file non-determinism is the recurring hazard — wall-clock, audit timestamps, BLAKE3 fingerprints of cleartext (in the redacted output), `tmp` paths, and any environment-derived value must be excluded by `regen_golden.py`. Run the regen script twice locally and verify byte-identical output before opening the Step 7 PR (same Phase 1 Step 6 discipline). The `stale-scip` fixture regeneration policy lives in its `README.md` — if a future contributor regenerates the SCIP from current HEAD, the fixture stops exercising the staleness path; the `README.md` must explicitly forbid this and the regen script must error out when re-targeted against current HEAD. The `test_phase3_handoff_smoke.py` skip-reason is the contract trip-wire — Phase 3's author must see it at first repo scan (verify by `grep`-discoverability).

## Step 8 — Confidence section renderer + CI ratchet + advisory benches + Phase-3 handoff

**Goal:** The `CONTEXT_REPORT.md` Confidence section renders every `IndexFreshness` with exhaustive `match` + `assert_never`; the eight CI jobs (`fence`, `contract-freeze`, `unit`, `integration`, `portfolio`, `adv-phase02`, `mypy`, `bench`) gate every PR; advisory bench canaries comment on PRs; the Phase-3 handoff issues are filed.

**Features delivered:**

- `src/codegenie/report/__init__.py`, `confidence_section.py` per §"Component design" §"Reading guide". The **only Phase-2 consumer** of `IndexFreshness`. Exhaustive `match` on every variant with `assert_never`; `mypy --warn-unreachable` per-module enforced (Step 1's `pyproject.toml` override). Renders into `CONTEXT_REPORT.md` alongside `repo-context.yaml`.
- CLI extension — after writer succeeds, render `CONTEXT_REPORT.md` and print CLI summary line with: `secrets_redacted_count`, `fingerprints` (8-hex list), `skill_shadowed` warnings, per-probe `Ran/CacheHit/Skipped` (Phase 0 audit anchor unchanged).
- CI jobs per §"CI gates" — eight jobs:
  1. `fence` (Phase 0, unchanged).
  2. `contract-freeze` (Phase 0; Phase 2 amendment in Step 1).
  3. `unit` (≤ 90 s pytest serial).
  4. `integration` (real-tool invocations; CI-gated on tool presence; skip-with-loud-warning if missing).
  5. `portfolio` (five-fixture sweep + golden diff; serial; ≤ 6 min budget; no `pytest-xdist`).
  6. `adv-phase02` (**LOAD-BEARING**: `test_stale_scip_fixture.py`, `test_hostile_skills_yaml.py`, `test_secret_in_source.py`, `test_image_digest_drift.py`, `test_concurrent_gather_race.py`, `test_adversarial_dockerfile.py`, `test_no_inmemory_secret_leak.py`).
  7. `mypy` (`mypy --strict` repo-wide; `--warn-unreachable` per-module overrides for `codegenie.{indices, probes.layer_b.index_health, report, adapters, tccm}/**`).
  8. `bench` (advisory; not gating).
- Advisory bench canaries:
  - `tests/bench/bench_portfolio_walltime.py` — five-fixture cold + warm p50 captured per run; baseline JSON committed in `tests/bench/baselines/`; ≥ 50% delta → comment-on-PR, no block.
  - `tests/bench/bench_index_health_overhead.py` — `IndexHealthProbe` walltime must be < 5 % of total cold gather on `minimal-ts`; ≥ 10 % → comment-on-PR.
  - `tests/bench/bench_portfolio_walltime_hosted_runner.py` (`phase-arch-design.md §"Gap 2"`) — nightly (not per-PR); emulates `cpu_count()=2` via `CODEGENIE_FORCE_CPU_COUNT=2`; comment-on-PR ≥ 50 %; build-fail ≥ 100 % (> 360 s p95).
- Phase-3 handoff issues filed on the GitHub Project board:
  - Implement Plugin Loader + `plugin.yaml` parser (Phase 3 owns).
  - Implement first plugin `plugins/vulnerability-remediation--node--npm/` + four ADR-0032 adapter implementations.
  - Implement universal `(*, *, *)` fallback plugin (HITL escalation).
  - Unskip `tests/adv/phase02/test_phase3_handoff_smoke.py` and assert Phase 2 Protocols are imported **unchanged**; any drift requires an explicit amendment to 02-ADR-0006/02-ADR-0007.
  - Extend `ALLOWED_BINARIES` for `npm`, `jq`.
- `docs/contributing.md` updated — "adding a Layer B/C/D/E/G probe" cheat-sheet referencing the Phase 2 probes as canonical examples.
- `docs/phases/02-context-gather-layers-b-g/README.md` updated with the final exit-criteria checklist marked complete.

**Done criteria:**

- [ ] `tests/unit/report/test_confidence_section.py` covers exhaustive `match` on every `IndexFreshness` variant; `assert_never` fires on a missing case (verified by deliberately removing a `case`).
- [ ] `mypy --warn-unreachable` per-module override enforces exhaustiveness on `confidence_section.py` — a missing case is a CI build error.
- [ ] All eight CI jobs green on `main` on Python 3.11 *and* 3.12 with the full Phase 2 test surface.
- [ ] `adv-phase02` job is the load-bearing gate — `test_stale_scip_fixture.py` failing turns the build red.
- [ ] All three bench canaries run and post advisory PR comments; never block merge.
- [ ] All five Phase-3 handoff issues exist on the GitHub Project board with milestones aligned to `roadmap.md` §"Phase 3".
- [ ] `docs/contributing.md` builds in `mkdocs build --strict` and remains in curated nav.
- [ ] `docs/phases/02-context-gather-layers-b-g/README.md` checklist marked complete and committed.

**Depends on:** Steps 1–7 complete and merged.

**Effort:** S — the renderer is ~150 LOC; the CI jobs are YAML configuration; benches reuse Phase 1's pattern. The Phase-3 handoff is documentation work.

**Risks specific to this step:** The `assert_never` discipline on `confidence_section.py` is the type-level enforcement of B2's load-bearing role — if `mypy --warn-unreachable` is mis-configured (e.g., per-module override mistakenly broadened or narrowed), exhaustiveness silently breaks. Verify by deliberately removing a `case` and confirming CI fails. The `bench_portfolio_walltime_hosted_runner.py` runs nightly, not per-PR — make sure the nightly cron is configured and the comment-on-PR fires when a developer pushes a change that would regress on a hosted runner without their knowledge.

## Exit-criteria mapping

Every Phase 2 exit criterion from `roadmap.md` §"Phase 2" and every refined goal from `phase-arch-design.md §"Goals"` traces to a step.

| Exit criterion (verbatim or refined) | Step(s) |
|---|---|
| **`IndexHealthProbe` surfaces a real staleness case in CI against a deliberately-seeded fixture** (roadmap exit) | Step 4 (`test_stale_scip_fixture.py`) + Step 7 (fixture lands) |
| Every Layer B–G language-agnostic probe runs against real repos | Steps 4 (Layer B) + 5 (Layer C) + 6 (Layer D/E/G); Step 7 (portfolio integration) |
| Golden-file tests per probe; CI diffs against committed expected | Step 7 (~70 goldens + regen script) + Step 8 (`portfolio` CI job) |
| Integration tests against 3–5 small fixture repos (multi-repo portfolio) | Step 7 (5 fixtures) + Step 8 (`portfolio` CI job) |
| `Probe` ABC + Phase 0/1 frozen surfaces unchanged (G3) | Step 1 (one ADR-0004 amendment; contract-freeze regenerates with this single field) + Step 8 (`contract-freeze` CI job) |
| `IndexFreshness` sum type at `src/codegenie/indices/freshness.py`; `match` + `assert_never` enforced (G4) | Step 1 (type lands) + Step 8 (`confidence_section.py` consumer + `mypy --warn-unreachable` enforcement) |
| Secret findings redacted at writer chokepoint; plaintext in zero persisted files (G5) | Step 3 (`SecretRedactor` + `RedactedSlice` smart constructor) + Step 6 (`test_secret_in_source.py`) + Step 7 (`test_no_inmemory_secret_leak.py`) |
| One subprocess port for B/G external CLIs (`run_external_cli`); Layer C uses `run_allowlisted` directly (G6) | Step 1 (`run_external_cli` + allowlist additions) + Step 5 (Layer C direct usage) + Step 6 (Layer G usage) |
| Cost target $0/run; tokens per gather 0 (G7) | Step 1 (no LLM deps added) + Step 8 (`fence` CI job) |
| Wall-clock targets (advisory) cold p50 ≤ 90 s / warm p50 ≤ 1.5 s / incremental p50 ≤ 10 s (G8) | Step 8 (`bench_portfolio_walltime.py` + hosted-runner bench) |
| Kernel scaffolding ships — adapter Protocols + `TCCMLoader` + `SkillsLoader` + `IndexFreshness`; **no Plugin Loader, no `plugin.yaml`, no `plugins/`** (G9) | Step 1 (Protocols + TCCM model + freshness) + Step 2 (loaders) + ADR-0007 |
| Nine new ADRs land alongside the code (G10) | Step 1 (all nine ADRs land before any probe ships) |
| `@register_probe(heaviness=, runs_last=)` decorator kwargs; coordinator sort-order edit | Step 1 (decorator + sort edit, ADR-0003) |
| Image digest as declared-input token; `ProbeContext.image_digest_resolver` (the **one** Phase-0 amendment) | Step 1 (extension + ADR-0004) + Step 5 (`RuntimeTraceProbe` consumes) |
| `@register_index_freshness_check` Open/Closed seam (Gap 3) | Step 1 (registry) + Steps 4–6 (per-probe registrations) |
| `RedactedSlice` smart constructor closes Gap 4 (type-level "redactor was called") | Step 3 |
| `test_no_inmemory_secret_leak.py` boundary test closes Gap 5 (Phase 4 RAG contract) | Step 7 |
| `test_phase3_handoff_smoke.py` (skipped) closes Gap 1 (Adapter Protocol drift) | Step 7 (lands skipped) + Step 8 (Phase 3 unskips at entry-gate review) |
| Five-fixture portfolio: `minimal-ts`, `native-modules`, `monorepo-pnpm`, `distroless-target`, `stale-scip` | Step 7 |
| Adversarial corpus ≥ 6 cases under `tests/adv/phase02/` | Steps 4 (`stale_scip`) + 5 (`image_digest_drift`, `adversarial_dockerfile`) + 6 (`secret_in_source`) + 7 (`hostile_skills_yaml`, `concurrent_gather_race`, `no_inmemory_secret_leak`) |
| `pytest-xdist` veto preserved (ADR-0009) | Step 1 (ADR) + Step 8 (CI is serial) |
| `mypy --warn-unreachable` per-module on `codegenie.{indices, probes.layer_b.index_health, report, adapters, tccm}/**` | Step 1 (pyproject override) + Step 8 (`mypy` CI job) |
| `py-tree-sitter` C-extension dep (ADR-0002 amendment to Phase 1 ADR-0009) | Step 1 (ADR) + Step 4 (`tree_sitter_import_graph.py`) |
| Hosted-runner bench (`cpu_count()=2`) closes Gap 2 | Step 8 |
| Phase-3 handoff issues filed; reference TCCM exercises every Protocol method via mock | Step 2 (reference TCCM roundtrip) + Step 8 (issues filed) |

No exit criterion is unmapped.

## Implementation-level risks

Distinct from design-level risks in `phase-arch-design.md`. These are about *the work*.

1. **Step 1 is overloaded.** Seven packages + nine ADRs + one Phase-0-contract amendment + eleven allowlist additions + two decorator-registries + the coordinator sort-order edit all land here. **Signal:** the Step 1 PR balloons past 2,000 LOC and reviewers ask for a split. **What to do:** if Step 1 exceeds 1,800 LOC, split into Step 1a (types: `indices/`, `adapters/`, `tccm/`, `types/identifiers.py`, ADRs 0006/0007/0008/0009) and Step 1b (kernel edits: `exec.py` extensions, `coordinator.py` sort edit, `probes/registry.py` decorator kwargs, `ProbeContext` amendment, ADRs 0001/0002/0003/0004/0005). Steps 2–8 are unchanged by the split; the dependency edge stays the same.

2. **The `ProbeContext.image_digest_resolver` extension is the only Phase-0-contract amendment in the entire phase.** **Signal:** a later contributor proposes adding a second field "while we're amending it." **What to do:** encode the allowed field list inside the snapshot-regeneration script (same Phase 1 Step 1 discipline) so further widening fails CI with the ADR-0004 pointer. Route `ProbeContext` to `CODEOWNERS` so any change requires designated review.

3. **The `stale-scip` fixture regeneration policy can silently break the load-bearing exit.** **Signal:** a contributor regenerates the SCIP fixture against current HEAD; the test still passes (because `CommitsBehind.n >= 0` is satisfied trivially) but no longer exercises staleness. **What to do:** `tests/fixtures/portfolio/stale-scip/regenerate.sh` must explicitly forbid retargeting against current HEAD (script errors out); the `README.md` documents the structural assertion (`CommitsBehind.n >= 1` and `last_indexed != current_HEAD`); the adversarial test asserts both inequalities, not just `n >= 1`.

4. **`mypy --warn-unreachable` per-module misconfiguration silently disables exhaustiveness on `confidence_section.py`.** **Signal:** a future contributor removes a `case` and CI still passes. **What to do:** Step 8 includes a deliberate "remove a case, verify CI fails" smoke test as part of the Step 8 PR-review checklist. The `pyproject.toml` override list is itself reviewed at Step 1 and re-verified at Step 8.

5. **Golden-file non-determinism.** Same risk as Phase 1 Step 6. **Signal:** Step 7 lands ~70 goldens, then a CI run a day later fails the diff. **What to do:** `regen_golden.py` excludes `wall_clock_ms`, `generated_at`, audit-timestamps, `tmp` paths, and any environment-derived value. Run the regen script twice locally and verify byte-identical output before opening the Step 7 PR.

6. **The `RedactedSlice` smart-constructor guarantee can be silently broken by a second factory path.** **Signal:** a future contributor adds `RedactedSlice.from_existing(...)` for testing convenience. **What to do:** Step 7's `test_no_inmemory_secret_leak.py` uses `inspect` to assert `redact_secrets` is the only call site that constructs `RedactedSlice`; any second factory adds to the call-site count and fails the test.

7. **Per-scenario sequential `RuntimeTraceProbe` execution can be silently parallelized by a future contributor.** **Signal:** a reviewer suggests "scenarios are independent, let's parallelize for speed." **What to do:** the design table (§"Tradeoffs") names this exact tradeoff; Step 5's unit test enumerates `asyncio.current_task()` counts and asserts ≤ 1 scenario in flight at any time.

8. **The four adapter `Protocol` signatures are shipped with zero Phase-2 implementations.** Phase 3 may discover the shape is wrong (e.g., `consumers(self, pkg: str)` should be `consumers(self, pkg: PackageId, *, transitively: bool = False)`). **Signal:** Phase 3 lands and the first plugin patches Phase 2's Protocols. **What to do:** `tests/adv/phase02/test_phase3_handoff_smoke.py` is the contract trip-wire — landed skipped at Step 7, unskipped at Phase 3 entry-gate review. Any Protocol drift requires an explicit ADR amendment to 02-ADR-0006/02-ADR-0007; the test's skip-reason names this contract.

## What's next — handoff to Phase 3

After Phase 2 ships, the system materially changes in these ways. Phase 3 (`roadmap.md` §"Phase 3 — Vuln remediation: deterministic recipe path") picks up here.

- **New artifacts on disk Phase 3 consumes:** `.codegenie/context/raw/scip-index.scip` (Phase 3's `ScipAdapter` decides consumption shape); `raw/import-graph.json` (forward-only adjacency; `ImportGraphAdapter` projects); `raw/dep-graph.json` (networkx-serializable; `DepGraphAdapter`); `raw/syft-sbom.json` + `raw/grype-cves.json` (deterministic recipe path's **vulnerability evidence**); `raw/runtime-trace-{scenario}.{strace,json}` (distroless feasibility checks); `raw/semgrep-findings.json` + `raw/gitleaks-findings.json` (both **redacted** at writer chokepoint).

- **New contracts ready for Phase 3 consumers:** Four adapter `Protocol`s at `src/codegenie/adapters/protocols.py` (Phase 3's first plugin implements all four); `AdapterConfidence` discriminated union (Phase 3 may extend with an ADR if needed); `IndexFreshness` (Phase 3 renders into bundle metadata); `TCCM` + `DerivedQuery` (Phase 3's `plugins/vulnerability-remediation--node--npm/tccm.yaml` parses through this loader); `SkillsLoader` three-tier merge (Phase 3 plugin's Skills route through it); `run_external_cli` (Phase 3 amends `ALLOWED_BINARIES` for `npm`, `jq`); `@register_dep_graph_strategy` (Phase 3 registers `build_npm`, `build_pnpm` via new files — never edits `DepGraphProbe`); `@register_index_freshness_check` (Phase 3 npm-specific index sources register their freshness signal here — never edit `IndexHealthProbe`).

- **New CI gates in place Phase 3 inherits:** Eight CI jobs (`fence`, `contract-freeze`, `unit`, `integration`, `portfolio`, `adv-phase02`, `mypy`, `bench`); `adv-phase02` is the load-bearing gate; `mypy --warn-unreachable` per-module on the five named modules; `forbidden-patterns` extended to ban `model_construct` under the new packages; coverage ratchet inherited from Phase 1.

- **Implicit assumptions Phase 3 can now make:** Plugin Loader + `plugin.yaml` parser are Phase 3's to build (ADR-0007 / final-design §G9 deliberately defers); the first plugin "doubles as the proof the loader works" per ADR-0031 §Consequences §1. Layer B–G evidence is deterministic end-to-end; same repo state → same `raw/*` byte-for-byte (modulo timestamp). The `SecretRedactor` chokepoint guarantee carries — Phase 3's LLM-adjacent flows (and Phase 4's RAG store atop Phase 3 outputs) inherit "plaintext in zero persisted files." `IndexFreshness` variant set is stable; a fifth `StaleReason` requires ADR amendment to 02-ADR-0006. Image-digest declared-input token mechanism (ADR-0004) is reusable for Phase 3 transforms that change the analyzed image.

- **What Phase 3 picks up materially:** Plugin Loader + `plugin.yaml` parser; first plugin (`plugins/vulnerability-remediation--node--npm/`) with TCCM, four adapter implementations, npm/Node-specific probes, Skills, OpenRewrite recipes; universal `(*, *, *)` fallback plugin (HITL escalation); the unskip + assertion of `test_phase3_handoff_smoke.py` as the Phase 2 → Phase 3 contract trip-wire.

- **Deferred to Phase 4+:** LLM-fallback adjudication (Phase 4); sandbox + Trust-Aware gates (Phase 5 — also the named cleartext-escalation door for secret findings); SHERPA state machine (Phase 6); Chainguard distroless migration (Phase 7); Hierarchical Planner + pre-rendered hot views (Phase 8); canonical event log (Phase 9, projects Phase 0 audit + Phase 2 slice metadata).
