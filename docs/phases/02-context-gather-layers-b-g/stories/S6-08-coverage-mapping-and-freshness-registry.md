# Story S6-08 — `TestCoverageMapping` + Layer D/E/G sub-schemas + freshness registrations

**Step:** Step 6 — Ship Layer D + E + G probes (skills, conventions, ADRs, ownership, scanners)
**Status:** HARDENED
**Effort:** M

## Validation notes

Validated: 2026-05-17
Verdict: HARDENED
Findings addressed: 22 total — 7 blocks, 13 hardens, 2 nits

Changes applied:
- AC-3 rewritten — replaced `probe_id = ProbeId(...)` class attr with the Layer-D-precedent `name: str = "test_coverage_mapping"` + module-level `_PROBE_ID: Final` (Consistency F4, Test-Quality F2, Design-Patterns DP-1; ADR-0007 / Layer-D `test_conventions.py:159` precedent).
- AC-3 extended — class declares full ABC attribute set (`name`, `layer="G"`, `tier="base"`, `requires=[]`, `declared_inputs=["coverage/lcov.info", "coverage/coverage-final.json"]`) — Design-Patterns DP-4 (`declared_inputs` is load-bearing for the content-addressed cache key; missing it silently breaks incremental gathers).
- AC-3 type-corrected — `applies_to_tasks: list[str] = ["*"]` (was tuple; ABC types it as `list[str]`).
- AC-5 rewritten — lcov body retrieval routes through `codegenie.parsers._io.open_capped` (50 MB cap, `parser_kind="test_coverage_mapping"`) and the existing `codegenie.probes._lcov_scanner` is extended with a per-record `scan_records(...)` API rather than re-implementing prefix dispatch (Design-Patterns DP-3, Consistency `_lcov_scanner` reuse finding; CLAUDE.md "Extension by addition"). Istanbul path uses `codegenie.parsers.safe_json.load`.
- AC-6 rewritten — `ScannerSkipped(reason="upstream_unavailable")` replaces the closed-sum-type-violating `"no_coverage_artifact"` literal (Consistency block / Design-Patterns DP-2 / Test-Quality F1; `_shared/scanner_outcome.py:98` + 02-ADR-0006 §Consequences). Story now documents the closed sum reuse explicitly so an implementer cannot reflexively widen the literal set.
- AC-7 rewritten — `ScannerFailed(exit_code=0, reason=None, stderr_tail=...)` with explicit `reason=None` so an implementer does not reflexively widen the closed `reason` literal (Consistency harden).
- AC-9 + AC-17 count reconciled — Layer D is 8 sub-schemas (`skills_index`, `conventions`, `adrs`, `repo_notes`, `repo_config`, `policy`, `exceptions`, `external_docs`); 8 + 3 + 5 = 16 Step-6 sub-schemas (Coverage F1).
- AC-13 strengthened — BLAKE3 hash pin of `src/codegenie/probes/layer_b/index_health.py` replaces the fragile `git diff --name-only` form (Coverage F6, Consistency harden; BLAKE3 is the project's hash primitive).
- AC-14 strengthened — adds an end-to-end variant that instantiates `IndexHealthProbe` and runs it against a fixture snapshot, asserting the Open/Closed promise at the probe level — not only at the registry level (Coverage F2, Test-Quality F5, Design-Patterns DP-5).
- AC-18 added — empty-coverage edge case: well-formed artifact with zero records → `ScannerRan(findings=())`, `files_seen=0`, `confidence="low"` (Coverage F4).
- AC-19 added — both `lcov.info` AND `coverage-final.json` present → lcov wins, `slice.format == "lcov"` (Coverage F5).
- AC-20 added — first-gather → `Fresh()` (no prior baseline to compare); defines the `expected_rule_pack_version` data flow (Coverage F3, Design-Patterns DP-5 hidden-state finding) — baseline is read from the **prior gather's** `.codegenie/context/raw/{name}.json` via `ctx.config["prior_run"]`.
- AC-21 added — `CoverageRecord` is closed: `model_fields.keys() == {"test_file", "source_file", "lines_covered"}`. Architectural test rejects the Phase-3 per-line-attribution non-goal from leaking into the slice (Coverage F7).
- AC-22 added — `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` is the only public entry-point on the probe; AST-walker asserts no `_run` / synchronous `run` survives. Surfaces the frozen Probe-ABC contract as an architectural constraint (Test-Quality F1, Consistency block, Design-Patterns DP-1).
- TDD plan rewritten — every test now uses `asyncio.run(probe.run(repo, ctx))` with explicit `RepoSnapshot` + `ProbeContext` construction (no `ProbeContext.for_test`), pins actual `CoverageRecord` values (not `files_seen` counts), monkeypatches `_MAX_BYTES` (no 65 MB disk writes), drives the AC-13/14 Open/Closed proof through `IndexHealthProbe` itself, and includes property-based + determinism + sub-schema-round-trip + both-files-present + empty-coverage tests (Test-Quality F1, F3–F12).
- Green skeleton corrected — `async def run(self, repo, ctx)`, `repo.root` (not `ctx.repo_root`), `from codegenie.types.identifiers import ProbeId` (not `codegenie.ids`), `ProbeOutput(schema_slice=..., raw_artifacts=..., confidence=..., duration_ms=..., warnings=[], errors=[])` (no `probe_id` field).
- Notes-for-implementer extended — rule-pack freshness extraction signal (4th call site), `CoverageFormat` newtype opportunity, `_wrap` helper deletion opportunity (Design-Patterns DP-6, DP-7, DP-8 nits surfaced).

Full audit log: `_validation/S6-08-coverage-mapping-and-freshness-registry.md`
**Depends on:** S6-03 (Layer D marker probes — `conventions` slice exists so its catalog version is a real freshness signal), S6-07 (`GitleaksProbe` + the four-scanner Layer G shape is settled; this story extends it with the fifth — `TestCoverageMappingProbe` — and lands the Layer D/E/G sub-schemas + the three freshness registrations)
**ADRs honored:** 02-ADR-0001 (any coverage-tooling CLI lands in `ALLOWED_BINARIES`), 02-ADR-0003 (`heaviness="medium"` is a registry kwarg, not a `Probe` ABC field), 02-ADR-0005 (no plaintext persistence — coverage findings flow through `SecretRedactor` at the writer chokepoint), 02-ADR-0006 (`IndexFreshness` registry; rule-pack-versioned scanners register their own freshness check via `@register_index_freshness_check` in their own module — never in `index_health.py`)
**Phase-2 load-bearing design discipline:** [`../phase-arch-design.md` §"Design patterns applied"](../phase-arch-design.md) **row 7** — *"One file per Layer G scanner; no shared `ScannerRunner` abstraction"* — extended to the fifth scanner here. [`../phase-arch-design.md` §"Gap analysis & improvements" Gap 3](../phase-arch-design.md) — `@register_index_freshness_check` is the Open/Closed seam; this story is the final exercise of that seam in Phase 2. **B2 (`IndexHealthProbe`) gets zero new code for these three indices.**

## Context

S6-06 and S6-07 land the four-scanner Layer G shape (`semgrep`, `ast_grep`, `ripgrep_curated`, `gitleaks`). This story closes Step 6 with three concerns that *cannot* be relaxed to a later step without leaving Phase 2 incomplete:

1. **`TestCoverageMappingProbe`** (the fifth Layer G probe per `localv2.md` §5.6 G3 and `phase-arch-design.md §"Component design"` #5) — reads `coverage/lcov.info` or `coverage/coverage-final.json` if present and emits a `test_coverage_map` slice. It is the raw artifact that Phase 3's `TestInventoryAdapter.tests_exercising` (`production/adrs/0030-graph-aware-context-queries.md`) projects against. Per-line attribution and the Phase-3 adapter projection are explicitly **out of scope** here — Phase 2 only ships the raw evidence.
2. **Layer D / E / G sub-schemas** under `src/codegenie/schema/probes/layer_{d,e,g}/`. S6-01..S6-06 (Layer D + E + four Layer G scanners) and this story's `test_coverage_mapping` collectively define ~14 slice shapes; they all land here as JSON Schemas with `additionalProperties: false` at every level (Phase 1 ADR-0004 convention). The sub-schemas are *referenced by* `S4-07`'s Layer-B subschemas + S5's Layer-C subschemas via the merged-envelope schema in Phase 0.
3. **`@register_index_freshness_check` registrations** for the three Phase-2 rule-pack/catalog-versioned indices — `semgrep` (rule-pack version), `gitleaks` (rule-pack version), `conventions` (catalog version). Each registration lives in *its own module* (the scanner / loader's file), not in `index_health.py`. That's the Open/Closed promise of S1-02's registry: `IndexHealthProbe` loops `default_freshness_registry.dispatch_all()` and learns about new indices via import side-effect, never via edit.

The load-bearing test of the third concern is the **rule-pack-drift integration test**: a fixture captures `rule_pack_version="v1"` on one gather, the rule pack bumps to `"v2"`, the next gather's `IndexHealthProbe` constructs `IndexFreshness.Stale(reason=DigestMismatch(expected="v1", actual="v2"))` *without B2 having been edited*. The same test pattern S5-05 lands for `runtime_trace`'s image-digest signal; this story is its analogue for rule-pack signals.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md` §"Component design" #5 Layer G scanners](../phase-arch-design.md) — one file per scanner, ≤ 200 LOC; this story adds the fifth file.
  - [`../phase-arch-design.md` §"Component design" #1 `IndexHealthProbe`](../phase-arch-design.md) — B2 reads `rule_pack_version` from sibling slices; this story is where that metadata becomes typed.
  - [`../phase-arch-design.md` §"Testing strategy"](../phase-arch-design.md) — sub-schema round-trip + rule-pack-drift integration test are the load-bearing freshness tests for Phase 2.
  - [`../phase-arch-design.md` §"Edge cases"](../phase-arch-design.md) rows 1–3 + row 13 — tool missing, non-zero exit, bad JSON, hostile coverage file (truncated lcov, malformed Istanbul JSON).
  - [`../phase-arch-design.md` §"Gap analysis & improvements" Gap 3](../phase-arch-design.md) — `@register_index_freshness_check` Open/Closed extension; this story is the third+fourth+fifth registration exercising it.
- **Phase ADRs:**
  - [`../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md`](../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md) — ADR-0001 — any coverage CLI added to `ALLOWED_BINARIES` (Phase 2 only reads on-disk lcov/Istanbul JSON; no new CLI required, but if a future ecosystem needs `bun test --coverage`, the binary lands here).
  - [`../ADRs/0003-coordinator-heaviness-sort-annotation.md`](../ADRs/0003-coordinator-heaviness-sort-annotation.md) — ADR-0003 — `heaviness="medium"` is a registry kwarg; the `Probe` ABC is untouched.
  - [`../ADRs/0005-secret-findings-no-plaintext-persistence.md`](../ADRs/0005-secret-findings-no-plaintext-persistence.md) — ADR-0005 — coverage data may inline file paths under sensitive directories; the writer's `SecretRedactor` is the chokepoint, not the probe.
  - [`../ADRs/0006-index-freshness-sum-type-location.md`](../ADRs/0006-index-freshness-sum-type-location.md) — ADR-0006 — `IndexFreshness` lives in `codegenie/indices/freshness.py`; new freshness checks register via `@register_index_freshness_check` in their own module.
- **Production ADRs:**
  - [`../../../production/adrs/0030-graph-aware-context-queries.md`](../../../production/adrs/0030-graph-aware-context-queries.md) — `TestInventoryAdapter.tests_exercising(symbol)` is the Phase 3 consumer; the `test_coverage_map` slice this story emits is its raw artifact.
- **Source design:**
  - [`../High-level-impl.md` §"Step 6"](../High-level-impl.md) — `@register_probe(heaviness="medium")` on `test_coverage_mapping`; sub-schemas under `src/codegenie/schema/probes/layer_{d,e,g}/`; freshness registrations for `semgrep`/`gitleaks`/`conventions`.
  - [`../../localv2.md` §5.6 G3](../../../localv2.md) — `test_coverage_map` slice shape; lcov + Istanbul parsers.
- **Existing kernel:**
  - `src/codegenie/probes/layer_g/semgrep.py` (S6-06) — pattern to mirror (≤ 200 LOC; Pydantic smart constructor; `ScannerOutcome`).
  - `src/codegenie/probes/layer_g/gitleaks.py` (S6-07) — pattern to mirror.
  - `src/codegenie/indices/registry.py` (S1-02) — `@register_index_freshness_check(index_name)`; `FreshnessCheck = Callable[[dict[str, JSONValue], str], IndexFreshness]`.
  - `src/codegenie/indices/freshness.py` (S1-01) — `IndexFreshness = Fresh | Stale(reason)`; `StaleReason` variants including `DigestMismatch(expected, actual)`.
  - `src/codegenie/probes/layer_b/index_health.py` (S4-01) — loops `default_freshness_registry.dispatch_all()`; **this story must NOT edit it**.
  - `src/codegenie/exec.py` (S1-07) — `run_external_cli`; only used if a coverage CLI is needed (Phase 2 ships file-only readers — no new binary).

## Goal

Land three concerns in one story:

1. `src/codegenie/probes/layer_g/test_coverage_mapping.py` — `@register_probe(heaviness="medium")`, ≤ 200 LOC, no shared base class, parses `coverage/lcov.info` and/or `coverage/coverage-final.json` into a `TestCoverageSlice` whose payload is `ScannerOutcome`. Tool-missing path (no coverage file present) → `ScannerSkipped`; bad-parse → `ScannerFailed`.
2. Sub-schemas under `src/codegenie/schema/probes/layer_d/`, `layer_e/`, `layer_g/` — one JSON Schema per slice shipped in Step 6, all with `additionalProperties: false` at every nested level; `ScannerOutcome`'s discriminator field is `kind` ∈ {`"ran"`, `"skipped"`, `"failed"`}.
3. `@register_index_freshness_check` registrations for `semgrep` (rule-pack version, in `semgrep.py`), `gitleaks` (rule-pack version, in `gitleaks.py`), `conventions` (catalog version, in `src/codegenie/conventions/loader.py`). Each registered at **module-import time** — not lazily. Verified end-to-end by an integration test that mutates rule-pack version between two gathers and asserts `IndexHealthProbe` emits `Stale(DigestMismatch(...))` for each index *without B2 itself being edited*.

## Acceptance criteria

**Numbered for traceability to the TDD plan.**

- [ ] **AC-1.** `src/codegenie/probes/layer_g/test_coverage_mapping.py` exists; `__all__` declares exactly `TestCoverageMappingProbe`, `TestCoverageSlice`, `CoverageRecord`.
- [ ] **AC-2.** The file is **≤ 200 LOC** including Pydantic models, imports, docstring. Verified by `tests/unit/probes/layer_g/test_scanner_loc_ceiling.py` (the parametrized ceiling test from S6-06; this story extends the `SCANNER_MODULES` list to include the fifth file).
- [ ] **AC-3.** Probe is `@register_probe(heaviness="medium")`; class declares the **full** ABC attribute set mirroring `ConventionsProbe` ([`src/codegenie/probes/layer_d/conventions.py:139-152`](../../../../src/codegenie/probes/layer_d/conventions.py)): `name: str = "test_coverage_mapping"`, `layer: Literal["G"] = "G"`, `tier: Literal["base"] = "base"`, `applies_to_tasks: list[str] = ["*"]`, `applies_to_languages: list[str] = ["*"]`, `requires: list[str] = []`, `declared_inputs: list[str] = ["coverage/lcov.info", "coverage/coverage-final.json"]`, `timeout_seconds = 30`. `_PROBE_ID: Final[ProbeId] = ProbeId("test_coverage_mapping")` is a **module-level** constant; **`probe_id` is NOT a class attribute** — Layer-D's ADR-0007 architectural test (`tests/unit/probes/layer_d/test_conventions.py:159` — `assert not hasattr(p, "probe_id")`) extends to this file. Mutation caught: declaring `probe_id` on the class would silently break the Phase-2 probe-identity contract and the existing architectural test; omitting `declared_inputs` would silently break the content-addressed cache key (default `cache_strategy="content"`). (validator: hardened — was `probe_id` class attr; aligned with Layer-D Rule-11 precedent + ABC contract.)
- [ ] **AC-4.** **No shared `ScannerRunner` base class.** The S6-06 architectural test extends to this file: imports `Probe` from `codegenie.probes.base` only; never imports a `ScannerRunner` / `BaseScanner` / `AbstractScanner` symbol; never imports another scanner module in this set. The shared types remain `ScannerOutcome` (S5-01) and `run_external_cli` (S1-07) — both kernel-level, not scanner-family-level.
- [ ] **AC-5.** **Reuse existing kernels; do NOT re-implement lcov parsing or size capping.** lcov body retrieval routes through `codegenie.parsers._io.open_capped(path, max_bytes=50 * 1024 * 1024, parser_kind="test_coverage_mapping")` (the rule-of-three shared kernel that owns `O_NOFOLLOW` + `fstat`-based capping for every parser in `codegenie.parsers` — `_lcov_scanner.py` is its fourth caller, this probe is the fifth). lcov prefix dispatch routes through `codegenie.probes._lcov_scanner` (Phase 1 S4-03's no-regex `_LCOV_PREFIX_MAP` state machine). The story extends `_lcov_scanner` with a **per-record** API (`scan_records(path: Path) -> tuple[CoverageRecord, ...]`) — the existing summed-totals `scan(...)` stays untouched (additive, not edit). Istanbul path routes through `codegenie.parsers.safe_json.load` (rejects oversized + malformed + billion-laughs JSON by construction). `parse_istanbul_bytes(raw: bytes) -> tuple[tuple[CoverageRecord, ...], str | None]` is the only new private smart constructor — returns `(records, None)` on success / `((), reason)` on failure. Mutation caught: inline `target.read_bytes()` / `target.stat().st_size > _MAX_BYTES` would bypass `open_capped`'s structured `probe.parser.cap_exceeded` event + `SymlinkRefusedError`; the `tests/unit/probes/layer_g/test_test_coverage_mapping.py::test_no_inline_size_cap_or_lcov_parser` AST-walker asserts the new file imports `open_capped` and `_lcov_scanner.scan_records` and does NOT `import re` / `re.compile` / shadow `_MAX_BYTES` / `Path.read_bytes` outside the Istanbul `safe_json.load` path. (validator: hardened — was inline `_parse_lcov` + `_MAX_BYTES = 64 * 1024 * 1024`; aligned with `_lcov_scanner` + `open_capped` rule-of-three precedent and Phase 1's 50 MB cap.)
- [ ] **AC-6.** **No coverage file → `ScannerSkipped(reason="upstream_unavailable")`.** When neither `coverage/lcov.info` nor `coverage/coverage-final.json` exists under `repo.root`, the probe returns `ScannerOutcome.ScannerSkipped(reason="upstream_unavailable")` with `confidence="low"`. `ScannerSkipped.reason` is the **closed** `Literal["tool_missing", "tool_unhealthy", "upstream_unavailable"]` set fixed by 02-ADR-0006 §Consequences; adding a fourth literal (e.g. `"no_coverage_artifact"`) is **explicitly ADR-amendment-gated** ([`src/codegenie/probes/_shared/scanner_outcome.py:93-99`](../../../../src/codegenie/probes/_shared/scanner_outcome.py)). "No upstream coverage artifact present" is structurally the same shape as Layer-C's "SBOM upstream missing"; reusing `upstream_unavailable` is the principled move and avoids unnecessary ADR amendment. This is the dominant path in production repos; the test pins it (`test_no_coverage_artifact_is_upstream_unavailable_not_failed`). Mutation caught: any code path that raises past the probe boundary on this dominant case; any reflexive widening of the closed sum literal would type-check-fail under `mypy --strict`. (validator: hardened — was `reason="no_coverage_artifact"`; closed-sum reuse, no ADR amendment needed.)
- [ ] **AC-7.** **Malformed coverage file → `ScannerFailed(exit_code=0, reason=None, ...)`.** When the on-disk file fails the smart constructor (truncated lcov, malformed Istanbul JSON, billion-laughs Istanbul JSON, file larger than 50 MB), the probe returns `ScannerFailed(exit_code=0, reason=None, stderr_tail=<concise diagnostic>)` with `confidence="low"`. `reason` is explicitly `None`: `ScannerFailed.reason` is the closed `Literal["invalid_json", "sbom_artifact_missing"] | None` and adding `"truncated_lcov"` / `"oversized"` is ADR-amendment-gated by the same 02-ADR-0006 discipline. The diagnostic lives in `stderr_tail` (a free string capped at 4096 bytes by the field validator). Tests pin both `exit_code == 0` and a substring of the diagnostic ("truncated" / "oversized"). Mutation caught: any `try: ... except: pass` swallow; any reflexive widening of the closed `reason` literal. (validator: hardened — narrative-only "concise reason" replaced with explicit `reason=None`.)
- [ ] **AC-8.** **All scanner invocations route through `run_external_cli`** — *if* a CLI is invoked. Phase 2's implementation reads files only; no new binary is added. Architectural test (extension of S6-06's AC-16): the file does not call `subprocess.run` / `subprocess.Popen` / `asyncio.create_subprocess_exec` directly. If a future contributor adds `bun test --coverage` invocation, it MUST route through `run_external_cli` and `bun` MUST already be in `ALLOWED_BINARIES`.
- [ ] **AC-9.** Sub-schemas land at `src/codegenie/schema/probes/layer_d/*.schema.json` (**8 schemas** — `skills_index`, `conventions`, `adrs`, `repo_notes`, `repo_config`, `policy`, `exceptions`, `external_docs`), `src/codegenie/schema/probes/layer_e/*.schema.json` (3 schemas — `ownership`, `service_topology_stub`, `slo_stub`), and `src/codegenie/schema/probes/layer_g/*.schema.json` (5 schemas — `semgrep`, `ast_grep`, `ripgrep_curated`, `gitleaks`, `test_coverage_mapping`). **Every schema declares `additionalProperties: false` at every nested-object level** (Phase 1 ADR-0004 convention — `tests/unit/schema/test_layer_d_e_g_subschemas_no_extra.py` walks the JSON tree and fires on any object without the property). (validator: hardened — Layer D count was "7"; reconciled with `phase-arch-design.md §"Component design"` P2D + the 8-name enumeration in this AC + Files-to-touch.)
- [ ] **AC-10.** Each scanner slice's `outcome` field in the JSON Schema uses `oneOf` with `kind` ∈ {`"ran"`, `"skipped"`, `"failed"`} as the discriminator — matching the Pydantic `ScannerOutcome` tagged union. Round-trip test: feed a known `ScannerOutcome.ScannerSkipped(reason="tool_missing")` through `model_dump(mode="json")` → assert the produced JSON validates against the sub-schema.
- [ ] **AC-11.** `@register_index_freshness_check("semgrep")` is registered in `src/codegenie/probes/layer_g/semgrep.py` — at module-import time, top-level. The function reads `slice["rule_pack_version"]` from the just-written slice, compares it to `slice.get("expected_rule_pack_version", slice["rule_pack_version"])` (the freshness baseline lands as a separate slice key written by the scanner itself), and constructs `IndexFreshness.Fresh()` on match / `Stale(DigestMismatch(expected, actual))` on drift. Same shape for `@register_index_freshness_check("gitleaks")` in `gitleaks.py`. Same shape for `@register_index_freshness_check("conventions")` in `src/codegenie/conventions/loader.py` — reads `catalog_version` instead of `rule_pack_version`.
- [ ] **AC-12.** **Registrations happen at module-import time, NOT lazily.** Architectural test: `tests/unit/indices/test_phase2_freshness_registrations.py` imports the three modules and asserts `"semgrep" in default_freshness_registry.registered_names()`, `"gitleaks" in ...`, `"conventions" in ...`. Mutation caught: any future "register on first call" pattern would silently fail the next clause.
- [ ] **AC-13.** **`IndexHealthProbe` is unchanged.** Architectural test: `tests/unit/indices/test_phase2_freshness_registrations.py` pins the BLAKE3 of `src/codegenie/probes/layer_b/index_health.py` as a `Final` test-module constant (`_INDEX_HEALTH_BLAKE3: Final[str] = "<hash>"`). The test recomputes the BLAKE3 of the file on disk and asserts equality — if it drifts, the test fires with a message naming the constant to update (refreshed only when an ADR explicitly authorizes a B2 edit). BLAKE3 is the project's hash primitive (CLAUDE.md). The legacy `git diff --name-only` form is deliberately rejected as fragile under cherry-picks / squash-merges / rebases; the BLAKE3 pin survives all of them. **The Open/Closed promise of S1-02 is the deliverable — adding three new indices must require zero edits to B2.** (validator: hardened — was `git diff --name-only`; replaced with BLAKE3 hash pin per Coverage F6 / Consistency harden.)
- [ ] **AC-14.** **Rule-pack-drift integration test, two layers.** Both at `tests/integration/probes/test_rule_pack_drift_marks_stale.py` — parametrized across the three indices (`semgrep` / `gitleaks` / `conventions`):
  - **AC-14a (registry-level smoke).** Construct a synthetic slice dict `{version_key: "v2", f"expected_{version_key}": "v1"}` and call `default_freshness_registry.dispatch_all({index_name: slice_}, head="...")` directly. Assert `Stale(reason=DigestMismatch(expected="v1", actual="v2"))`. Pins the per-scanner registration's logic in isolation.
  - **AC-14b (end-to-end through `IndexHealthProbe`).** Construct a fixture `RepoSnapshot` whose `.codegenie/context/raw/` carries one prior-run slice per index with `version_key="v1"` (the baseline written by the previous gather). Wire `ctx.config["prior_run"]` to that path. Mutate the just-written slice to `version_key="v2"`. Instantiate `IndexHealthProbe()` and run it via `asyncio.run(probe.run(repo, ctx))`. Assert the probe's `schema_slice["indices"][index_name]` carries the typed `Stale(DigestMismatch(expected="v1", actual="v2"))` shape — proving that B2 dispatches through `default_freshness_registry` (i.e. the registration imports take effect through `codegenie.probes.__init__`) and that the Open/Closed promise is **observable** at the probe level, not only at the registry level.
  Mutation caught: a B2 that hard-codes only `runtime_trace` and ignores the registry would pass AC-14a but fail AC-14b. (validator: hardened — was registry-only; AC-14b added per Coverage F2 / Test-Quality F5 / Design-Patterns DP-5.)
- [ ] **AC-15.** **`mypy --strict`** passes on `test_coverage_mapping.py`, the three modules carrying registrations, and the test. No `Any` escapes `CoverageRecord` / `IndexFreshness`.
- [ ] **AC-16.** **`ruff check` + `ruff format --check`** pass on every touched file.
- [ ] **AC-17.** Sub-schemas are referenced from the merged-envelope schema (Phase 0); `tests/unit/schema/test_envelope_references_all_subschemas.py` (or extension thereof) finds the **16** Step-6 sub-schemas (8 Layer D + 3 Layer E + 5 Layer G) under the envelope's `$ref` graph. (validator: hardened — count was "15"; reconciled with AC-9.)

- [ ] **AC-18.** **Empty coverage artifact (well-formed but zero records) → `ScannerRan(findings=())`.** When `coverage/lcov.info` exists but contains only `TN:\n` with zero `SF:` records, OR `coverage/coverage-final.json` is `{}`, the probe returns `ScannerRan(findings=())` with `files_seen=0`, `format` correctly set, `confidence="low"`. **Not** `ScannerSkipped` (the artifact IS present) and **not** `ScannerFailed` (it parses). Test pin: `test_empty_lcov_yields_scanner_ran_zero_records` and `test_empty_istanbul_yields_scanner_ran_zero_records`. Mutation caught: a parser that returns `ScannerSkipped` for empty input would silently misclassify a "test suite that wrote no coverage" case. (validator: added — empty-input edge case per Coverage F4.)

- [ ] **AC-19.** **Both lcov.info and coverage-final.json present → lcov wins.** Deterministic precedence is pinned: `coverage/lcov.info` is parsed and Istanbul JSON is ignored; `slice.format == "lcov"`. Test pin: `test_lcov_wins_when_both_artifacts_present`. Mutation caught: a future contributor reordering the `lcov if lcov.exists() else (istanbul ...)` ternary silently changes behavior; non-deterministic precedence would break two-consecutive-gathers byte-identical determinism (Phase 1 ratchet). (validator: added — precedence pin per Coverage F5.)

- [ ] **AC-20.** **Freshness baseline data-flow is defined (`expected_rule_pack_version` source).** The freshness check reads `slice["rule_pack_version"]` against the **prior gather's** persisted slice (read via `ctx.config["prior_run"]` pointing at the prior `.codegenie/context/raw/{name}.json`), NOT against a sibling key in the same slice. On the **first gather** (no prior baseline) the freshness check returns `Fresh()`; this is not a regression but the documented bootstrap path. The freshness function signature stays `(slice: dict[str, JSONValue], head: str) -> IndexFreshness` — `head` is the run id; the prior-run lookup is the function's job, not B2's. Test pins (parametrized across the three indices):
  - `test_first_gather_yields_fresh_for_{index}` — no prior `raw/{name}.json` exists → `Fresh()`.
  - `test_rule_pack_drift_yields_stale_with_digest_mismatch_for_{index}` — prior slice has `rule_pack_version="v1"`; current slice has `"v2"` → `Stale(DigestMismatch(expected="v1", actual="v2"))`.
  - `test_rule_pack_unchanged_yields_fresh_for_{index}` — both gathers agree → `Fresh()`.
  Mutation caught: the original AC-11's `slice.get("expected_rule_pack_version", observed)` default would make the check tautological (expected == observed on first gather forever). (validator: added — closes the hidden-state gap on the freshness baseline per Coverage F3 / Design-Patterns DP-5.)

- [ ] **AC-21.** **`CoverageRecord` is closed; no per-line attribution leaks into Phase 2.** Architectural test `test_coverage_record_fields_are_frozen`: `assert frozenset(CoverageRecord.model_fields.keys()) == frozenset({"test_file", "source_file", "lines_covered"})`. Phase-3's `TestInventoryAdapter.tests_exercising(symbol)` (`production/adrs/0030-graph-aware-context-queries.md`) does per-line attribution against this slice's raw evidence — it does NOT live on the slice itself in Phase 2. Mutation caught: any future contributor adding `lines_attributed_to_test` (or similar projection state) onto `CoverageRecord` would break the Phase 2 / Phase 3 contract; the architectural test catches the field-set drift at unit time. (validator: added — actively forbids the Out-of-scope non-goal per Coverage F7.)

- [ ] **AC-22.** **Probe ABC contract honored.** `TestCoverageMappingProbe.run` is the only public entry point: `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`. Architectural test extends `tests/unit/test_probe_contract.py`: AST-walks `src/codegenie/probes/layer_g/test_coverage_mapping.py` and asserts (a) the class defines an `async def run` taking exactly the two positional parameters `repo` and `ctx`, (b) the class does NOT define `_run`, `run_sync`, or any private synchronous entry point, (c) the class does NOT redeclare `cache_key` / `applies` (default ABC behavior is correct). Mutation caught: a synchronous or single-arg `run` would `TypeError` at coordinator dispatch — but a future contributor might add a sync `_run` "for testing" and silently bypass the ABC. (validator: added — codifies the frozen Probe ABC contract per Test-Quality F1 / Consistency block / Design-Patterns DP-1.)

## Implementation outline

1. **`test_coverage_mapping.py`** (~180 LOC):
   - Module docstring noting the SRP discipline (no shared base; mirror S6-06) AND the kernel-reuse contract (consumes `open_capped`, `_lcov_scanner.scan_records`, `safe_json.load`; does NOT re-implement).
   - `CoverageRecord` Pydantic model with `model_config = ConfigDict(frozen=True, extra="forbid")`; fields `test_file: str | None, source_file: str, lines_covered: tuple[int, ...]`. **Field set is frozen** (AC-21 architectural test pins it).
   - `TestCoverageSlice` with `outcome: ScannerOutcome, format: Literal["lcov", "istanbul"] | None, files_seen: int | None`. **No `rule_pack_version` field** — coverage has no rule-pack signal (per-repo evidence; per-tool format is captured by `format`).
   - **Reuse**: `from codegenie.probes._lcov_scanner import scan_records` (additive API landed by this story; existing `scan(...)` for summed totals is untouched) and `from codegenie.parsers._io import open_capped, SizeCapExceeded, SymlinkRefusedError`.
   - `_parse_istanbul(raw)` — uses `codegenie.parsers.safe_json.load`; iterate `statementMap` × `s` to assemble line-hit map. Smart constructor; `ValidationError` → str reason.
   - `TestCoverageMappingProbe.run(repo, ctx)` (**async**, two-arg, public — matches the frozen Probe ABC): stat `repo.root / "coverage" / "lcov.info"` then `repo.root / "coverage" / "coverage-final.json"`; if neither → `ScannerSkipped(reason="upstream_unavailable")` (closed-sum-honoring literal); dispatch to lcov-via-kernel or Istanbul-via-safe_json; map result to `ProbeOutput` with `duration_ms` from `time.monotonic_ns()` delta; return `ProbeOutput`.
1a. **`_lcov_scanner` extension (additive — does NOT edit the existing `scan(...)`):**
   - Add `scan_records(path: Path, *, max_bytes: int = _LCOV_MAX_BYTES) -> tuple[LcovRecord, ...]` returning per-file records (not summed totals). The existing `scan(...)` summed-totals API stays unchanged.
   - Both APIs route through `open_capped` (the rule-of-three primitive). Both share the no-regex `_LCOV_PREFIX_MAP` dispatch.
   - New `LcovRecord = NamedTuple("LcovRecord", [("test_file", str | None), ("source_file", str), ("lines_covered", tuple[int, ...])])`.
   - This is the rule-of-three reuse hardening per Design-Patterns DP-3: the lcov state machine lives in one file, consumed by both `TestInventoryProbe` (Phase 1) and `TestCoverageMappingProbe` (Phase 2).
2. **Sub-schemas** under `src/codegenie/schema/probes/layer_{d,e,g}/` — one `.schema.json` per slice (8 + 3 + 5 = **16** schemas). Generate from the Pydantic models via `model_json_schema()` post-processed to add `"additionalProperties": false` at every object level (the post-processor lives at `scripts/regen_subschemas.py`; checked-in artifacts are the source of truth, regen script is reviewed-as-code). Match the canonicalization conventions of Phase 1 (sorted keys).
3. **Freshness registrations** — three module-level `@register_index_freshness_check(...)` decorators on three small functions. The freshness check reads the **prior gather's** persisted slice (via `ctx.config["prior_run"]`), NOT a sibling key in the current slice. Bootstrap: first gather → `Fresh()`.
   ```python
   # semgrep.py — top-level, after the probe class definition.
   from pathlib import Path
   import json

   @register_index_freshness_check("semgrep")
   def _semgrep_freshness(slice_: dict[str, JSONValue], _head: str) -> IndexFreshness:
       observed = slice_.get("rule_pack_version")
       if observed is None:
           return Fresh()  # no current signal — nothing to compare.
       # The dispatch_all caller threads ctx.config["prior_run"] into the
       # registry's invocation environment; the freshness check looks up
       # the prior slice at the canonical raw/{name}.json location. If
       # no prior run exists (first gather), expected is None → Fresh.
       expected = _load_prior_value("semgrep", "rule_pack_version")
       if expected is None:
           return Fresh()  # bootstrap path documented by AC-20.
       if observed != expected:
           return Stale(reason=DigestMismatch(expected=str(expected), actual=str(observed)))
       return Fresh()
   ```
   `_load_prior_value(name, key)` is a tiny shared helper in `codegenie.indices.registry` (or `codegenie.indices._prior_lookup`) that reads `.codegenie/context/raw/{name}.json` from the prior-run directory referenced by `ctx.config["prior_run"]`. The same helper is used by all three registrations (semgrep, gitleaks, conventions); each registration's body stays a ~10-LOC function in its own module. **Rule-of-three watch:** when a fourth call site arrives (`runtime_trace` from S5-05 is the foreseeable next), extract the comparator body — see Notes for the implementer.
   Identical shape in `gitleaks.py` (reads `rule_pack_version` from its slice); identical shape in `conventions/loader.py` (reads `catalog_version`).

## TDD plan — red / green / refactor

> **Test fixture helpers** (referenced below). Mirror the Layer-D precedent at `tests/unit/probes/layer_d/test_conventions.py:26-72`:
>
> ```python
> import asyncio
> import logging
> from pathlib import Path
>
> from codegenie.probes.base import ProbeContext, ProbeOutput, RepoSnapshot
>
>
> def _snapshot(root: Path) -> RepoSnapshot:
>     return RepoSnapshot(root=root, git_commit=None, detected_languages={}, config={})
>
>
> def _ctx(tmp_path: Path, *, prior_run: Path | None = None) -> ProbeContext:
>     cfg: dict[str, object] = {}
>     if prior_run is not None:
>         cfg["prior_run"] = str(prior_run)
>     return ProbeContext(
>         cache_dir=tmp_path / ".cache",
>         output_dir=tmp_path / ".out",
>         workspace=tmp_path / ".work",
>         logger=logging.getLogger("test"),
>         config=cfg,
>     )
>
>
> def _run(probe, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
>     return asyncio.run(probe.run(repo, ctx))
> ```

### Red — write the failing tests first

```python
# tests/unit/probes/layer_g/test_test_coverage_mapping.py
"""Unit tests for TestCoverageMappingProbe (S6-08)."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from codegenie.probes.layer_g import test_coverage_mapping as tcm
from codegenie.probes._shared.scanner_outcome import (
    ScannerFailed,
    ScannerRan,
    ScannerSkipped,
)
from codegenie.probes.registry import default_registry

# _snapshot / _ctx / _run helpers as defined above (real test file imports
# them from tests/unit/probes/layer_g/_helpers.py — sibling layer probes
# already vendor this pattern; see tests/unit/probes/layer_d/_helpers.py).


def test_no_coverage_artifact_is_upstream_unavailable_not_failed(tmp_path: Path) -> None:
    """AC-6. Mutation caught: any code path that raises past the probe
    boundary on this dominant case (most repos have no coverage file);
    any reflexive widening of the ScannerSkipped.reason closed sum to
    add 'no_coverage_artifact' would type-check-fail under mypy --strict."""
    output = _run(tcm.TestCoverageMappingProbe(), _snapshot(tmp_path), _ctx(tmp_path))
    slice_ = tcm.TestCoverageSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerSkipped)
    assert slice_.outcome.reason == "upstream_unavailable"  # closed-sum-honoring literal
    assert slice_.format is None
    assert output.confidence == "low"


def test_lcov_parses_into_specific_coverage_records(tmp_path: Path) -> None:
    """AC-5, AC-18 boundary. Mutation caught: a parser that returns
    `ScannerRan(findings=())` plus `files_seen=1` after seeing one `SF:`
    line without parsing DA: rows would pass a thin `files_seen == 1`
    test — this test pins the actual CoverageRecord shape so such a
    stub fails."""
    cov = tmp_path / "coverage" / "lcov.info"
    cov.parent.mkdir(parents=True)
    cov.write_text(
        "TN:\nSF:src/payments/processor.ts\nDA:1,5\nDA:2,5\nDA:3,0\nend_of_record\n"
    )
    output = _run(tcm.TestCoverageMappingProbe(), _snapshot(tmp_path), _ctx(tmp_path))
    slice_ = tcm.TestCoverageSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerRan)
    assert slice_.format == "lcov"
    assert slice_.files_seen == 1
    # Pin the actual record shape — not just the count.
    assert slice_.outcome.findings == (
        tcm.CoverageRecord(
            test_file=None,
            source_file="src/payments/processor.ts",
            lines_covered=(1, 2),  # line 3 had DA:3,0 (zero hits) — excluded.
        ),
    )


def test_istanbul_parses_into_specific_coverage_records(tmp_path: Path) -> None:
    """AC-5. Mutation caught: confusing lcov layout with Istanbul JSON
    layout — different smart constructor; also catches a no-op parser
    returning ScannerRan(()) plus format='istanbul'."""
    cov = tmp_path / "coverage" / "coverage-final.json"
    cov.parent.mkdir(parents=True)
    cov.write_text(json.dumps({
        "src/payments/processor.ts": {
            "path": "src/payments/processor.ts",
            "statementMap": {"0": {"start": {"line": 1}}, "1": {"start": {"line": 2}}},
            "s": {"0": 5, "1": 0},
        }
    }))
    output = _run(tcm.TestCoverageMappingProbe(), _snapshot(tmp_path), _ctx(tmp_path))
    slice_ = tcm.TestCoverageSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerRan)
    assert slice_.format == "istanbul"
    assert slice_.files_seen == 1
    assert slice_.outcome.findings == (
        tcm.CoverageRecord(
            test_file=None,
            source_file="src/payments/processor.ts",
            lines_covered=(1,),  # statement 0 had 5 hits; statement 1 had 0.
        ),
    )


def test_truncated_lcov_yields_scanner_failed_with_diagnostic(tmp_path: Path) -> None:
    """AC-7. Mutation caught: a parser that returns ScannerFailed for
    EVERY input (no actual parsing) would pass an isinstance-only check;
    this test pins exit_code=0, reason=None (closed-sum honored), and
    a substring of the diagnostic."""
    cov = tmp_path / "coverage" / "lcov.info"
    cov.parent.mkdir(parents=True)
    cov.write_text("TN:\nSF:src/payments/processor.ts\nDA:1,")  # truncated mid-record
    output = _run(tcm.TestCoverageMappingProbe(), _snapshot(tmp_path), _ctx(tmp_path))
    slice_ = tcm.TestCoverageSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.exit_code == 0
    assert slice_.outcome.reason is None  # closed sum not widened
    diag = slice_.outcome.stderr_tail.lower()
    assert "truncated" in diag or "parse" in diag


def test_oversized_coverage_yields_scanner_failed(tmp_path: Path, monkeypatch) -> None:
    """AC-7. Mutation caught: reading the whole file into memory before
    capping would OOM the gatherer. We monkeypatch the cap rather than
    write 50 MB to disk inside a unit test."""
    cov = tmp_path / "coverage" / "lcov.info"
    cov.parent.mkdir(parents=True)
    cov.write_bytes(b"TN:\nSF:foo\nend_of_record\n" + b"X" * 1024)
    # Shrink the cap so a tiny file trips it.
    monkeypatch.setattr(tcm, "_MAX_BYTES", 8)
    output = _run(tcm.TestCoverageMappingProbe(), _snapshot(tmp_path), _ctx(tmp_path))
    slice_ = tcm.TestCoverageSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.exit_code == 0
    assert slice_.outcome.reason is None
    assert "oversized" in slice_.outcome.stderr_tail.lower()


def test_empty_lcov_yields_scanner_ran_zero_records(tmp_path: Path) -> None:
    """AC-18. Well-formed but zero records: ScannerRan with empty
    findings tuple, NOT ScannerSkipped (artifact IS present) and NOT
    ScannerFailed (parses cleanly)."""
    cov = tmp_path / "coverage" / "lcov.info"
    cov.parent.mkdir(parents=True)
    cov.write_text("TN:\n")  # zero SF: records
    output = _run(tcm.TestCoverageMappingProbe(), _snapshot(tmp_path), _ctx(tmp_path))
    slice_ = tcm.TestCoverageSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerRan)
    assert slice_.outcome.findings == ()
    assert slice_.files_seen == 0
    assert slice_.format == "lcov"
    assert output.confidence == "low"


def test_empty_istanbul_yields_scanner_ran_zero_records(tmp_path: Path) -> None:
    """AC-18. Empty Istanbul JSON ({}) → ScannerRan(()), files_seen=0."""
    cov = tmp_path / "coverage" / "coverage-final.json"
    cov.parent.mkdir(parents=True)
    cov.write_text("{}")
    output = _run(tcm.TestCoverageMappingProbe(), _snapshot(tmp_path), _ctx(tmp_path))
    slice_ = tcm.TestCoverageSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerRan)
    assert slice_.outcome.findings == ()
    assert slice_.files_seen == 0
    assert slice_.format == "istanbul"


def test_lcov_wins_when_both_artifacts_present(tmp_path: Path) -> None:
    """AC-19. Deterministic precedence: lcov.info is parsed; Istanbul
    JSON is ignored. Mutation caught: a future contributor reordering
    the ternary silently changes behaviour."""
    cov_dir = tmp_path / "coverage"
    cov_dir.mkdir(parents=True)
    (cov_dir / "lcov.info").write_text("TN:\nSF:src/a.ts\nDA:1,1\nend_of_record\n")
    (cov_dir / "coverage-final.json").write_text(json.dumps({
        "src/b.ts": {"path": "src/b.ts", "statementMap": {"0": {"start": {"line": 99}}}, "s": {"0": 1}}
    }))
    output = _run(tcm.TestCoverageMappingProbe(), _snapshot(tmp_path), _ctx(tmp_path))
    slice_ = tcm.TestCoverageSlice.model_validate(output.schema_slice)
    assert slice_.format == "lcov"
    assert isinstance(slice_.outcome, ScannerRan)
    # Source files from lcov, not Istanbul.
    assert {r.source_file for r in slice_.outcome.findings} == {"src/a.ts"}


def test_coverage_record_fields_are_frozen() -> None:
    """AC-21. No per-line attribution leaks into Phase 2's slice;
    Phase 3's TestInventoryAdapter projects against this raw evidence."""
    assert frozenset(tcm.CoverageRecord.model_fields.keys()) == frozenset(
        {"test_file", "source_file", "lines_covered"}
    )


def test_probe_run_is_async_two_arg_and_no_private_run() -> None:
    """AC-22. Probe ABC contract: async def run(self, repo, ctx). No
    _run, no synchronous run, no extra positional params. Mutation
    caught: a contributor adding a sync `_run` 'for testing' silently
    bypasses the coordinator's await dispatch."""
    source = Path(tcm.__file__).read_text()
    tree = ast.parse(source)
    cls = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "TestCoverageMappingProbe"
    )
    methods = {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "run" in methods, "run() must be defined on the probe"
    assert isinstance(methods["run"], ast.AsyncFunctionDef), "run must be async"
    args = methods["run"].args.args
    assert [a.arg for a in args] == ["self", "repo", "ctx"], "exactly (self, repo, ctx)"
    assert "_run" not in methods, "no private _run shim — coordinator dispatch is the only path"
    assert "run_sync" not in methods, "no synchronous shim"


def test_no_inline_size_cap_or_lcov_parser() -> None:
    """AC-5. Architectural: this file consumes `open_capped` and
    `_lcov_scanner.scan_records`; it does NOT re-implement them.
    Mutation caught: a regression that copies lcov state-machine code
    back inline would break the rule-of-three reuse precedent."""
    source = Path(tcm.__file__).read_text()
    tree = ast.parse(source)
    imports = [
        f"{n.module}.{name.name}"
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.module is not None
        for name in n.names
    ]
    assert "codegenie.parsers._io.open_capped" in imports
    assert any(
        i == "codegenie.probes._lcov_scanner.scan_records"
        or i.startswith("codegenie.probes._lcov_scanner.")
        for i in imports
    )
    # No `import re` — reuses the no-regex precedent from _lcov_scanner.
    plain_imports = [
        alias.name
        for n in ast.walk(tree)
        if isinstance(n, ast.Import) for alias in n.names
    ]
    assert "re" not in plain_imports


def test_registry_entry_heaviness_is_medium() -> None:
    """AC-3. Mutation caught: bumping to 'heavy' would cost the
    coordinator a runs_last slot the Layer G shape budgets for."""
    entry = next(
        e for e in default_registry._entries  # noqa: SLF001 — sibling Layer D precedent
        if e.cls.name == "test_coverage_mapping"
    )
    assert entry.heaviness == "medium"


def test_declared_inputs_pinned() -> None:
    """AC-3. declared_inputs is load-bearing for the content-addressed
    cache key (default cache_strategy='content'); pinning it ensures
    a future contributor cannot silently empty the list and disable
    caching for this probe."""
    assert tcm.TestCoverageMappingProbe.declared_inputs == [
        "coverage/lcov.info",
        "coverage/coverage-final.json",
    ]


def test_two_consecutive_gathers_are_byte_identical(tmp_path: Path) -> None:
    """Determinism ratchet (Phase 1 precedent — sibling test in
    layer_d/test_skills_index.py). Mutation caught: dict iteration
    order leakage; non-deterministic sort over findings; timestamp
    escape into the slice."""
    cov = tmp_path / "coverage" / "lcov.info"
    cov.parent.mkdir(parents=True)
    cov.write_text("TN:\nSF:a.ts\nDA:1,1\nend_of_record\nSF:b.ts\nDA:1,1\nend_of_record\n")
    out1 = _run(tcm.TestCoverageMappingProbe(), _snapshot(tmp_path), _ctx(tmp_path))
    out2 = _run(tcm.TestCoverageMappingProbe(), _snapshot(tmp_path), _ctx(tmp_path))
    assert json.dumps(out1.schema_slice, sort_keys=True) == json.dumps(out2.schema_slice, sort_keys=True)


@given(
    extras=st.lists(
        st.sampled_from([
            "BRF:1\n", "BRH:1\n", "\n", "  \n",
            "FN:1,foo\n", "FNDA:1,foo\n", "FNF:1\n", "FNH:1\n", "LF:3\n", "LH:2\n",
        ]),
        max_size=20,
    ),
)
@settings(max_examples=50, deadline=None)
def test_unknown_lcov_prefixes_silently_dropped(tmp_path: Path, extras: list[str]) -> None:
    """Property — `_lcov_scanner`'s documented contract: unknown lcov
    prefixes are silently dropped. The new probe inherits this from
    the shared kernel. Mutation caught: a regression that bails on
    unknown prefixes; a regex-based parser with backtracking on
    pathological input."""
    body = "TN:\nSF:src/a.ts\n" + "".join(extras) + "DA:1,1\nDA:2,0\nend_of_record\n"
    cov = tmp_path / "coverage" / "lcov.info"
    cov.parent.mkdir(parents=True)
    cov.write_text(body)
    output = _run(tcm.TestCoverageMappingProbe(), _snapshot(tmp_path), _ctx(tmp_path))
    slice_ = tcm.TestCoverageSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerRan)
    assert slice_.files_seen == 1
    assert {r.source_file for r in slice_.outcome.findings} == {"src/a.ts"}


@pytest.mark.parametrize("outcome", [
    ScannerRan(findings=[]),
    ScannerSkipped(reason="upstream_unavailable"),
    ScannerFailed(exit_code=0, stderr_tail="parse error: ...", reason=None),
])
def test_scanner_outcome_roundtrips_through_sub_schema(outcome) -> None:
    """AC-10 round-trip — covers all three ScannerOutcome variants
    (the original story only covered the ScannerSkipped path).
    Mutation caught: a sub-schema oneOf wired with the wrong `const`
    discriminator value would fail one variant and not others."""
    import jsonschema
    schema_path = Path("src/codegenie/schema/probes/layer_g/test_coverage_mapping.schema.json")
    schema = json.loads(schema_path.read_text())
    slice_ = tcm.TestCoverageSlice(outcome=outcome, format=None, files_seen=None)
    jsonschema.validate(instance=slice_.model_dump(mode="json"), schema=schema)
```

```python
# tests/unit/indices/test_phase2_freshness_registrations.py
"""AC-12, AC-13 — registrations are at import time; B2 (IndexHealthProbe)
file is byte-stable (BLAKE3 hash pin)."""
from __future__ import annotations

from pathlib import Path
from typing import Final

import blake3

import codegenie.probes.layer_g.semgrep  # noqa: F401 — import triggers registration
import codegenie.probes.layer_g.gitleaks  # noqa: F401
import codegenie.conventions.loader  # noqa: F401
from codegenie.indices.registry import default_freshness_registry

# Pinned BLAKE3 of src/codegenie/probes/layer_b/index_health.py as shipped at
# the start of S6-08. Refresh ONLY when an ADR explicitly authorizes a B2 edit.
# AC-13: the Open/Closed promise of S1-02 — adding three new indices requires
# zero edits to B2. BLAKE3 chosen because it is the project's hash primitive
# (CLAUDE.md). The legacy `git diff --name-only` form was deliberately rejected
# as fragile under cherry-picks / squash-merges / rebases.
_INDEX_HEALTH_BLAKE3: Final[str] = "<computed at story execution; assert pinned in test>"


def test_semgrep_registered_at_import_time() -> None:
    """AC-12. Mutation caught: any "register on first call" pattern."""
    assert "semgrep" in default_freshness_registry.registered_names()


def test_gitleaks_registered_at_import_time() -> None:
    """AC-12."""
    assert "gitleaks" in default_freshness_registry.registered_names()


def test_conventions_registered_at_import_time() -> None:
    """AC-12."""
    assert "conventions" in default_freshness_registry.registered_names()


def test_index_health_probe_file_is_unchanged() -> None:
    """AC-13. B2 file is byte-stable — the Open/Closed promise of S1-02.
    Refresh `_INDEX_HEALTH_BLAKE3` ONLY when an ADR explicitly
    authorizes a B2 edit; otherwise this test firing means the
    registration mechanism is being bypassed."""
    p = Path("src/codegenie/probes/layer_b/index_health.py")
    actual = blake3.blake3(p.read_bytes()).hexdigest()
    assert actual == _INDEX_HEALTH_BLAKE3, (
        f"B2 file changed: {actual}. Refresh _INDEX_HEALTH_BLAKE3 only "
        f"when an ADR authorizes editing index_health.py."
    )
```

```python
# tests/integration/probes/test_rule_pack_drift_marks_stale.py
"""AC-14a + AC-14b + AC-20 — load-bearing Open/Closed proof, at two layers."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from codegenie.indices.freshness import DigestMismatch, Fresh, Stale
from codegenie.indices.registry import default_freshness_registry
from codegenie.probes.layer_b.index_health import IndexHealthProbe

# Importing the scanner modules triggers the @register_index_freshness_check
# side-effect — exactly what AC-12 pins as the deliverable contract.
import codegenie.probes.layer_g.semgrep  # noqa: F401
import codegenie.probes.layer_g.gitleaks  # noqa: F401
import codegenie.conventions.loader  # noqa: F401


INDICES = [
    ("semgrep", "rule_pack_version"),
    ("gitleaks", "rule_pack_version"),
    ("conventions", "catalog_version"),
]


# ---------- AC-14a — registry-level smoke ----------

@pytest.mark.parametrize("index_name,version_key", INDICES)
def test_registry_dispatch_marks_index_stale_on_drift(
    index_name: str, version_key: str
) -> None:
    """AC-14a. Per-scanner registration logic in isolation —
    smoke that the registry shape works for each index. Mutation
    caught: a regression in the per-scanner decorator body."""
    slice_ = {version_key: "v2", f"expected_{version_key}": "v1"}
    result = default_freshness_registry.dispatch_all({index_name: slice_}, head="deadbeef")
    freshness = result[index_name]
    assert isinstance(freshness, Stale)
    assert isinstance(freshness.reason, DigestMismatch)
    assert freshness.reason.expected == "v1"
    assert freshness.reason.actual == "v2"


# ---------- AC-14b — end-to-end through IndexHealthProbe ----------

@pytest.mark.parametrize("index_name,version_key", INDICES)
def test_index_health_probe_marks_index_stale_on_drift(
    index_name: str, version_key: str, tmp_path: Path
) -> None:
    """AC-14b. The Open/Closed promise of AC-13 made observable at the
    probe level. A B2 that hard-codes only `runtime_trace` and ignores
    the registry would pass AC-14a but fail this test. Mutation caught:
    B2 not dispatching through default_freshness_registry."""
    # Arrange — write the prior gather's slice (baseline v1) into the
    # canonical raw/ location, mirroring the writer (S3-03) output.
    raw_dir = tmp_path / ".codegenie" / "context" / "raw"
    raw_dir.mkdir(parents=True)
    (raw_dir / f"{index_name}.json").write_text(json.dumps({version_key: "v1"}))

    # Construct a current-gather snapshot whose slice mutates to v2.
    repo, ctx = _make_drift_fixture(tmp_path, index_name, version_key, current="v2")

    # Act — invoke B2 through its public async run().
    output = asyncio.run(IndexHealthProbe().run(repo, ctx))

    # Assert — the dispatched freshness for this index is Stale with the
    # typed DigestMismatch discriminator.
    indices_section = output.schema_slice["indices"]
    assert index_name in indices_section, (
        f"B2 did not dispatch {index_name!r} — Open/Closed promise broken."
    )
    freshness = indices_section[index_name]
    # Schema-level shape (whatever B2 emits — match the typed
    # IndexFreshness dump shape established in S4-01).
    assert freshness["kind"] == "stale"
    assert freshness["reason"]["kind"] == "digest_mismatch"
    assert freshness["reason"]["expected"] == "v1"
    assert freshness["reason"]["actual"] == "v2"


# ---------- AC-20 — first-gather → Fresh bootstrap ----------

@pytest.mark.parametrize("index_name,version_key", INDICES)
def test_first_gather_yields_fresh(
    index_name: str, version_key: str, tmp_path: Path
) -> None:
    """AC-20. No prior raw/{name}.json exists → freshness check returns
    Fresh(). The bootstrap path is documented behaviour, not a regression."""
    repo, ctx = _make_drift_fixture(
        tmp_path, index_name, version_key, current="v1", with_baseline=False
    )
    output = asyncio.run(IndexHealthProbe().run(repo, ctx))
    freshness = output.schema_slice["indices"][index_name]
    assert freshness["kind"] == "fresh"
```

> `_make_drift_fixture` is a small helper that constructs `(RepoSnapshot, ProbeContext)` with the current-gather slice on disk + `ctx.config["prior_run"]` pointing at the prior-run `raw/` directory (or `None` for the no-baseline case). It mirrors the sibling Layer-B test fixture in `tests/integration/probes/test_index_health.py` (S4-01).

```python
# tests/unit/schema/test_layer_d_e_g_subschemas_no_extra.py
"""AC-9 — every nested object in every Step-6 sub-schema declares
additionalProperties: false (Phase 1 ADR-0004 convention)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

SUBSCHEMA_ROOTS = [
    Path("src/codegenie/schema/probes/layer_d"),
    Path("src/codegenie/schema/probes/layer_e"),
    Path("src/codegenie/schema/probes/layer_g"),
]


def _walk_objects(node: object, path: str = "$"):
    if isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node:
            yield path, node
        for k, v in node.items():
            yield from _walk_objects(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_objects(v, f"{path}[{i}]")


@pytest.mark.parametrize("root", SUBSCHEMA_ROOTS)
def test_every_object_rejects_extra(root: Path) -> None:
    for schema_path in root.glob("*.schema.json"):
        schema = json.loads(schema_path.read_text())
        for jpath, obj in _walk_objects(schema):
            assert obj.get("additionalProperties") is False, (
                f"{schema_path}:{jpath} permits extra properties"
            )
```

### Green — make it pass

Skeleton for `test_coverage_mapping.py` (~180 LOC). Pattern mirrors `semgrep.py`:

```python
# src/codegenie/probes/layer_g/test_coverage_mapping.py
"""TestCoverageMappingProbe — Layer G, medium heaviness.

Reads coverage/lcov.info or coverage/coverage-final.json if present;
emits a typed test_coverage_map slice. The raw artifact Phase 3's
TestInventoryAdapter.tests_exercising projects against.

No new external CLI — file-only readers. Phase 2 deliberately ships
the raw evidence without per-line attribution (Phase 3 adapter concern).

This file consumes (does NOT re-implement):
- codegenie.parsers._io.open_capped  — O_NOFOLLOW + fstat-based size cap
- codegenie.probes._lcov_scanner     — Phase 1 S4-03's no-regex prefix-map
                                       lcov state machine; extended here
                                       with scan_records(path) (additive)
- codegenie.parsers.safe_json        — bounded JSON parser

Sources:
- ../phase-arch-design.md §"Component design" #5.
- ../../localv2.md §5.6 G3.
- ../../../production/adrs/0030-graph-aware-context-queries.md.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from codegenie.parsers._io import open_capped, SizeCapExceeded, SymlinkRefusedError
from codegenie.parsers.safe_json import load as safe_json_load
from codegenie.probes._lcov_scanner import scan_records  # additive API; S4-03 kernel
from codegenie.probes._shared.scanner_outcome import (
    ScannerFailed,
    ScannerOutcome,
    ScannerRan,
    ScannerSkipped,
)
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe
from codegenie.types.identifiers import ProbeId

_MAX_BYTES: Final[int] = 50 * 1024 * 1024  # Phase 1's lcov cap — alignment, not drift
_PROBE_ID: Final[ProbeId] = ProbeId("test_coverage_mapping")
__all__ = ["TestCoverageMappingProbe", "TestCoverageSlice", "CoverageRecord"]


class CoverageRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    test_file: str | None
    source_file: str
    lines_covered: tuple[int, ...]


class TestCoverageSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    outcome: ScannerOutcome
    format: Literal["lcov", "istanbul"] | None
    files_seen: int | None


def _parse_istanbul(raw: bytes) -> tuple[tuple[CoverageRecord, ...], str | None]:
    # safe_json_load enforces bounded depth + size; ValidationError → reason.
    ...


@register_probe(heaviness="medium")
class TestCoverageMappingProbe(Probe):
    name: str = "test_coverage_mapping"
    layer: Literal["G"] = "G"
    tier: Literal["base"] = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    declared_inputs: list[str] = [
        "coverage/lcov.info",
        "coverage/coverage-final.json",
    ]
    timeout_seconds = 30

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        start = time.monotonic_ns()
        lcov = repo.root / "coverage" / "lcov.info"
        istanbul = repo.root / "coverage" / "coverage-final.json"
        target = lcov if lcov.exists() else (istanbul if istanbul.exists() else None)
        if target is None:
            return _output(
                ScannerSkipped(reason="upstream_unavailable"),
                format=None, files_seen=None, confidence="low", start=start,
            )
        fmt: Literal["lcov", "istanbul"] = "lcov" if target.name == "lcov.info" else "istanbul"
        try:
            if fmt == "lcov":
                # _lcov_scanner.scan_records routes through open_capped (S4-03 kernel reuse).
                records = scan_records(target, max_bytes=_MAX_BYTES)
                parsed = tuple(
                    CoverageRecord(
                        test_file=r.test_file,
                        source_file=r.source_file,
                        lines_covered=r.lines_covered,
                    )
                    for r in records
                )
            else:
                raw = open_capped(target, max_bytes=_MAX_BYTES, parser_kind=self.name)
                parsed_raw, reason = _parse_istanbul(raw)
                if reason is not None:
                    return _output(
                        ScannerFailed(exit_code=0, reason=None, stderr_tail=reason),
                        format=fmt, files_seen=None, confidence="low", start=start,
                    )
                parsed = parsed_raw
        except SizeCapExceeded:
            return _output(
                ScannerFailed(exit_code=0, reason=None, stderr_tail="oversized"),
                format=fmt, files_seen=None, confidence="low", start=start,
            )
        except (SymlinkRefusedError, ValueError) as exc:
            return _output(
                ScannerFailed(exit_code=0, reason=None, stderr_tail=f"parse error: {exc}"),
                format=fmt, files_seen=None, confidence="low", start=start,
            )
        return _output(
            ScannerRan(findings=list(parsed)),
            format=fmt,
            files_seen=len({r.source_file for r in parsed}),
            confidence="high" if parsed else "low",
            start=start,
        )


def _output(
    outcome: ScannerOutcome, *,
    format: Literal["lcov", "istanbul"] | None,
    files_seen: int | None,
    confidence: Literal["high", "medium", "low"],
    start: int,
) -> ProbeOutput:
    slice_ = TestCoverageSlice(outcome=outcome, format=format, files_seen=files_seen)
    return ProbeOutput(
        schema_slice=slice_.model_dump(mode="json"),
        raw_artifacts=[],
        confidence=confidence,
        duration_ms=(time.monotonic_ns() - start) // 1_000_000,
        warnings=[],
        errors=[],
    )
```

Then the three freshness registrations are added to `semgrep.py`, `gitleaks.py`, `conventions/loader.py` — each is a ~10-LOC module-level function decorated with `@register_index_freshness_check(name)`.

### Refactor — clean up

- **The Open/Closed seam IS the design.** Each scanner owns its freshness contract in its own file; the shared piece is the prior-value lookup (`_load_prior_value(name, key)`) which lives in `codegenie.indices` precisely because three call sites consume it and a fourth (`runtime_trace`, S5-05) is foreseeable. The per-scanner body stays ~10 LOC — short, but no longer duplicating the I/O.
- **`_lcov_scanner.scan_records` is additive.** The existing `scan(...)` summed-totals API is untouched; the new per-record API lives alongside. This is the kernel-extension precedent for future scanners (e.g., a future `bun-test-coverage` adds a new format-specific dispatcher, not a new lcov state machine).
- The sub-schema regen script (`scripts/regen_subschemas.py`) is reviewed-as-code; the committed `.schema.json` files are the source of truth. Two consecutive runs must produce byte-identical output (Phase 1 Step-6 discipline).
- `CoverageRecord.lines_covered` is a `tuple[int, ...]` not a `list[int]` so the Pydantic model stays `frozen=True`.
- **`_output` helper (replaces the original `_wrap`)** — module-level (not method) so the probe class stays small and the helper can be tested in isolation. If a future contributor finds the 5-arg helper awkward, the inline-everything alternative is acceptable (~15 LOC trade-off).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/layer_g/test_coverage_mapping.py` | New file ≤ 200 LOC — the fifth Layer G probe. Consumes `_lcov_scanner.scan_records`, `open_capped`, `safe_json.load`; **no inline lcov parser, no inline size cap**. |
| `src/codegenie/probes/_lcov_scanner.py` | **Additive** — add `scan_records(path, *, max_bytes)` per-record API + `LcovRecord` NamedTuple. Existing `scan(...)` summed-totals API stays untouched. |
| `src/codegenie/indices/registry.py` (or `_prior_lookup.py`) | Add `_load_prior_value(name, key)` helper that reads `.codegenie/context/raw/{name}.json` from `ctx.config["prior_run"]` if set, returns `None` on first-gather bootstrap. Shared by the three freshness registrations. |
| `src/codegenie/probes/layer_g/semgrep.py` | Add module-level `@register_index_freshness_check("semgrep")` block (~10 LOC). |
| `src/codegenie/probes/layer_g/gitleaks.py` | Add module-level `@register_index_freshness_check("gitleaks")` block (~10 LOC). |
| `src/codegenie/conventions/loader.py` | Add module-level `@register_index_freshness_check("conventions")` block (~10 LOC). |
| `src/codegenie/schema/probes/layer_d/*.schema.json` | New — 7 sub-schemas for Layer D (`skills_index`, `conventions`, `adrs`, `repo_notes`, `repo_config`, `policy`, `exceptions`, `external_docs`). |
| `src/codegenie/schema/probes/layer_e/*.schema.json` | New — 3 sub-schemas for Layer E (`ownership`, `service_topology_stub`, `slo_stub`). |
| `src/codegenie/schema/probes/layer_g/*.schema.json` | New — 5 sub-schemas for Layer G (`semgrep`, `ast_grep`, `ripgrep_curated`, `gitleaks`, `test_coverage_mapping`). |
| `scripts/regen_subschemas.py` | New — reviewed-as-code regen helper; `additionalProperties: false` post-processor; sorted keys. |
| `tests/unit/probes/layer_g/test_test_coverage_mapping.py` | New — 7 tests for the probe. |
| `tests/unit/probes/layer_g/test_scanner_loc_ceiling.py` | Extend `SCANNER_MODULES` with the fifth file. |
| `tests/unit/indices/test_phase2_freshness_registrations.py` | New — 3 import-time-registration tests. |
| `tests/unit/schema/test_layer_d_e_g_subschemas_no_extra.py` | New — every-object-rejects-extra walker. |
| `tests/integration/probes/test_rule_pack_drift_marks_stale.py` | New — parametrized over the three indices. |

## Out of scope

- **Per-line coverage attribution / call-graph projection.** That's Phase 3's `TestInventoryAdapter.tests_exercising(symbol)` adapter (`production/adrs/0030-graph-aware-context-queries.md`). Phase 2 ships the raw `test_coverage_map` slice; the adapter projects against it.
- **Coverage-tool selection (c8, jest, vitest, nyc).** A strategy registry like `@register_dep_graph_strategy` (S1-10) is the right shape if Phase 3 finds it needs ecosystem-specific coverage tooling — but Phase 2 reads on-disk lcov / Istanbul JSON only, with no tool selection. The strategy registry would be premature here.
- **Invoking a coverage CLI (`bun test --coverage`, `pytest --cov`).** Phase 2 reads existing coverage artifacts; running the test suite is a Phase-4+ Planner concern, not a gatherer concern. If a future story adds CLI invocation, the binary lands in `ALLOWED_BINARIES` first (02-ADR-0001 amendment), and the call routes through `run_external_cli` (S1-07).
- **`SecretRedactor` invocation inside the probe.** That's the writer chokepoint's job (02-ADR-0005, S3-03). Coverage slices return raw `CoverageRecord`s; the writer redacts before disk.
- **Phase-4+ rule-pack vendor advisories.** Each scanner's `rule_pack_version` is whatever string it emits today — semantic versioning of the rule pack content is the scanner vendor's contract, not codewizard-sherpa's. The freshness check is "is the string the same as last gather" — a `DigestMismatch` is a `DigestMismatch`.

## Notes for the implementer

0. **The Probe ABC is frozen — `async def run(self, repo, ctx)` is the only public entry point.** The validator caught the original story prescribing `def _run(self, ctx)`. That signature is a `TypeError` at coordinator dispatch and is rejected by `tests/unit/test_probe_contract.py`. Use the sibling `ConventionsProbe` (`src/codegenie/probes/layer_d/conventions.py:139-210`) as the structural template — including the **full** ABC attribute set (`name`, `layer`, `tier`, `applies_to_tasks`, `applies_to_languages`, `requires`, `declared_inputs`, `timeout_seconds`) and the module-level `_PROBE_ID: Final` constant. Probe identity is via `name` + `_PROBE_ID`, not via a class-level `probe_id` attribute (ADR-0007).

1. **The Open/Closed promise is the story's whole point.** Three new indices, zero edits to `IndexHealthProbe`. AC-13's "B2 file is not in this PR's changed files" assertion is the load-bearing test of the S1-02 registry's design. If you find yourself reaching for `index_health.py` to teach B2 about `semgrep`, **stop** — the registration must happen in `semgrep.py` and B2 must learn via the registry's dispatch loop. If `dispatch_all()` doesn't already produce the right shape, the right fix is in `indices/registry.py` (S1-02), not in B2.
2. **Module-import time registration is non-negotiable.** A lazy "register on first dispatch" pattern would silently fail AC-12. The decorator must run when the module is imported — which means the import-side-effect must be triggered by *somebody* importing `codegenie.probes.layer_g.semgrep` (the probe registry's `_PROBE_REGISTRY` already pulls it in via `codegenie.probes.__init__` — verify this chain is intact). If a future contributor adds lazy loading to the probe registry, both the probe and the freshness registrations break together — which is the right coupling.
3. **`test_coverage_mapping.py` is structurally the fifth Layer G scanner, not a sibling pattern.** S6-06 + S6-07 establish "one file per Layer G scanner; no shared base class." This story is the test of that discipline at scale — five scanners, five files, zero shared `ScannerRunner`. The Pydantic-smart-constructor + `ScannerOutcome`-payload + `run_external_cli`-routing patterns are inline in each file. If you find yourself extracting a helper, count the call sites first (Rule of Three).
4. **`rule_pack_version` is the freshness key, not file mtime.** A semgrep rule-pack file may be unchanged on disk while a downloaded rule pack version moves; conversely the file may rewrite with the same logical version. The freshness check reads `slice["rule_pack_version"]` (the string semgrep emits in its own output) — *not* `os.path.getmtime`. The pre-commit `forbidden-patterns` hook (S1-11) bans mtime probes inside `index_health.py`; the same discipline applies to these registrations.
5. **Sub-schemas must reject extra fields at every level.** Phase 1 ADR-0004's `additionalProperties: false` convention — `tests/unit/schema/test_layer_d_e_g_subschemas_no_extra.py` walks the JSON tree to enforce it. The regen script's post-processor adds the property at every `type: "object"` / `properties:`-bearing node; don't hand-edit schemas to drop the property.
6. **The rule-pack-drift integration test is the proof, not the spec.** AC-14a + AC-14b are parametrized over three indices because that's the symmetry — if the test passes for `semgrep` and not `gitleaks`, the registration in `gitleaks.py` is broken. The parametrization is what makes a regression on the fourth scanner (`runtime_trace`, S5-05) immediately visible too: failing one row of the parametrize tells you exactly which freshness contract drifted. **AC-14b's load-bearing role** is to prove that B2 actually *dispatches* through the registry — AC-14a only proves the per-scanner decorator works in isolation; AC-14b proves the wiring through `IndexHealthProbe` at runtime, which is the actual Open/Closed promise.

7. **Closed sum types — `ScannerSkipped.reason` and `ScannerFailed.reason` are NOT extensible by addition.** They are `Literal[...]` sets fixed by `02-ADR-0006`. If "no_coverage_artifact" feels like the right semantic for AC-6, resist — reuse `upstream_unavailable` (which is what the story now prescribes). Adding a new literal requires an ADR amendment in advance. The validator's Design-Patterns critic specifically flagged this as a "make-illegal-states-unrepresentable" guard the codebase deliberately enforces; the closed sum is the design.

8. **Rule-of-three watch on the freshness-comparator body.** Three call sites (semgrep, gitleaks, conventions) share the same compare-observed-to-expected logic. The story now extracts the *I/O* part (`_load_prior_value`) into a shared helper because three call sites consume it. The *comparator* body stays inline in each scanner because the per-scanner version key + freshness contract is the scanner's concern. **When `runtime_trace` (S5-05's image-digest freshness) becomes the fourth call site**, revisit: a `version_comparator(name, version_key)` extraction with the version_key as a parameter becomes warranted. The signal to extract: a contributor opens a PR with the same 10-LOC comparator body in a fifth scanner file.

9. **Test infrastructure — async dispatch + explicit fixtures.** Every test in the TDD plan uses `asyncio.run(probe.run(repo, ctx))` with explicit `RepoSnapshot` and `ProbeContext` construction; there is **no `ProbeContext.for_test(...)` helper** (the original story prescribed one that doesn't exist). Mirror the Layer-D fixture helpers (`tests/unit/probes/layer_d/_helpers.py` if it exists, or vendor inline `_snapshot` / `_ctx` / `_run` helpers as shown in the TDD plan's preamble). The oversized-file test monkeypatches `_MAX_BYTES` rather than writing 50 MB to disk — keep test runs fast.

10. **`CoverageFormat` newtype opportunity (defer).** The `Literal["lcov", "istanbul"] | None` repeats in three signatures. A `CoverageFormat = Literal["lcov", "istanbul"]` newtype in `codegenie.types.identifiers` would be a Rule-2-acceptable 1-line improvement; defer to a follow-up story unless the implementer notices a third concrete consumer (Phase 3's `TestInventoryAdapter` may qualify).
