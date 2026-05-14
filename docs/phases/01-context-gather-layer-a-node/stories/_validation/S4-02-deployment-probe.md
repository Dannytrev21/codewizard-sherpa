# Validation report — S4-02 `DeploymentProbe` + sub-schema with zip-slip mitigation

**Story:** [S4-02-deployment-probe.md](../S4-02-deployment-probe.md)
**Validated:** 2026-05-14
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

S4-02 is the largest probe in Step 4 and the second consumer of the 5-way parser-dispatch pattern S4-01 (CIProbe) just hardened. The story was directionally sound — ADR-0012's four-shape contract was cleanly pinned in the original AC-3, the load-bearing zip-slip mitigation was correctly identified, and the ADR-0011 negative anchors (no `python-hcl2`, no `run_allowlisted`) were in place. But all four critics flagged that the story **did not learn from the S4-01 hardening report it explicitly cites in its dependency chain.** The same Coverage gaps S4-01 closed (registry membership across languages, two-run determinism, schema rejection at exact JSON Pointer, `_WARNING_IDS` frozenset + import-time ADR-0007 conformance loop, walk-every-nested-block schema test, per-branch confidence rules, `additional_providers`-style multi-type evidence tracking, dedup/ordering policy for list fields, contract-attributes test with `list`-vs-`tuple` discipline) all recurred here as gaps. Three load-bearing block-tier bugs were present:

- **CN-1 [CRITICAL]** — Notes §"Cross-cutting confidence rules" final bullet wrote `warnings: ["helm.values_file_parse_error:<path>"]` — the **exact same** colon-suffixed Warning-ID violation S4-01 CN-1 fixed at CRITICAL severity (ADR-0007's pattern `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` admits no colons). The story copies the violation in fresh form. Resolution per Rule 7: bare ID; offending path moves to `raw/deployment.json`. AC-39 + AC-38 (`_WARNING_IDS` frozenset + import-time pattern loop) enforce structurally.
- **TQ-3 [BLOCK / SECURITY]** — The original zip-slip test (`test_kustomize_resource_outside_repo_refused`) monkeypatches `os.open` and asserts `not any("/etc/passwd" in p for p in opened)`. This is a **non-event guard**: `Path.resolve()` on POSIX is pure path manipulation until a symlink forces `lstat()`; the naive wrong impl (`str(root) + str(resource)` + `.startswith` check) bails before any `open()` happens, so the spy never fires and the test passes despite the defense being broken. Resolution: replace with a sentinel-exfiltration fixture (AC-24) where the wrong impl provably leaks `containerPort: 31337` into `exposed_ports`. The naive defense breaks the test because `Path("/tmp/x") / "../sentinel.yaml"` stringifies as `/tmp/x/../sentinel.yaml` which DOES start with `/tmp/x`. The correct `.resolve().is_relative_to(root.resolve())` check correctly identifies the path as outside. Symlink-via-resource variant added at AC-25 for defense-in-depth.
- **TQ-1 + TQ-2 [BLOCK]** — Test-helper preamble undefined while `_snapshot(...)` / `_ctx(...)` referenced 8 times (exact S2-02 / S4-01 block-tier finding); `@pytest.mark.asyncio` used instead of codebase-standard `asyncio.run` (sibling `test_node_build_system.py:93` precedent; Rule 11). Resolution: inlined preamble + `_run(root)` helper using `asyncio.run` verbatim from the sibling.

The synthesizer rewrote ACs from **10 bundled bullets + 7 TDD tests** to **47 individually-verifiable ACs + ~35 TDD tests** (many parametrized). New module-level Open/Closed seams: `_DEPLOYMENT_TYPE` (TypeAlias), `_DEPLOYMENT_DETECTORS` (precedence tuple), `_DEPLOYMENT_PARSERS` (dispatch registry), `_RAW_KIND_FILTER` (frozenset), `_WARNING_IDS` + `_ERROR_IDS` (frozensets), `_demote` + `_CONFIDENCE_RANK` (copied verbatim from `node_build_system.py`), `_ID_PATTERN` (import-time loop), `_ParseResult` (NamedTuple), `ImageRefBlock` + `EnvironmentEntry` (TypedDicts). Pure helpers extracted (functional core / imperative shell): `_is_under`, `_extract_image_ref`, `_select_deployment_type`, `_env_name_from_filename`, `_filter_k8s_kinds`, `_extract_container_specs`, `_aggregate_exposed_ports`, `_aggregate_env_var_names`, `_walk_overlays`. Each pure helper has a corresponding table-driven unit test.

**No `NEEDS RESEARCH` findings.** Every weakness was resolvable from authority docs (Phase 1 arch + ADR-0001..ADR-0012 + production ADR-0005) plus the S4-01 / S2-02 hardened-story precedents. Stage 3 (researcher) skipped per skill's token-economy guidance.

## Most load-bearing fixes (block-tier)

1. **CN-1 (CRITICAL) — ADR-0007 colon contradiction (repeats S4-01 CN-1).** Notes line "Any values-file parse error → that file skipped, `warnings: ["helm.values_file_parse_error:<path>"]`" replaced with bare-ID convention; offending path moves to `raw/deployment.json`. New AC-39 pins per-file degradation with bare ID. New AC-38 (`_WARNING_IDS` frozenset + import-time `_ID_PATTERN.match()` loop) catches future colon-suffix typos at import time, before any test runs.

2. **TQ-3 (BLOCK / SECURITY) — Zip-slip sentinel-exfiltration test (replaces `os.open` spy).** AC-24 now uses a real sentinel-exfiltration fixture (`tmp_path.parent / "SENTINEL_LEAK.yaml"` carrying `containerPort: 31337`). The smoking-gun observable is `31337 not in s["exposed_ports"]` — a structurally-impossible-to-fake check. The naive wrong impl provably leaks 31337; the correct `.resolve().is_relative_to(root.resolve())` defense passes. AC-25 adds the symlink-via-resource defense-in-depth variant.

3. **TQ-1 / TQ-2 (BLOCK) — Test-helper preamble + `asyncio.run`.** TDD plan opens with a complete preamble (`_snapshot`, `_ctx`, `_run`) inlined from `test_node_build_system.py:67-94`. Every `async def`/`await DeploymentProbe().run(...)` switched to `_run(root)` (synchronous; uses `asyncio.run` internally). Matches sibling conventions per Rule 11.

4. **TQ-4 (BLOCK) — Contract-attributes test.** New AC-2 + AC-3 pin every class attribute verbatim including `isinstance(declared_inputs, list)` (the S2-02 frozen-ABC `tuple`-vs-`list` bug) and the 13-entry `declared_inputs` list verbatim against arch line 545.

5. **CV-1 / TQ-14 (BLOCK) — Total-ordering kind filter.** Original AC-5 only tested `Deployment` (positive) + `Service`/`ConfigMap` (negative). The Goal sentence enumerates 4 positive kinds (`Deployment`, `StatefulSet`, `DaemonSet`, `Pod`); the implementer who writes `if kind == "Deployment":` passed. New AC-28 parametrizes over 4 positive + 8 negative kinds (adding `Job`, `CronJob`, `ReplicaSet`, `Secret`, `Ingress`, `Namespace`) with port-shaped negatives that must NOT extract. Module-level `_RAW_KIND_FILTER: Final[frozenset[str]]` with import-time anchor.

6. **CV-2 / CN-2 / CN-3 / TQ-15 (BLOCK) — Multi-type detection + `_TYPE_PRECEDENCE`.** Outline §2 named precedence inline; no AC; no test. The `additional_providers`-style information-survival convention from CIProbe was missing. New AC-22 parametrizes over 5 multi-type combinations asserting (i) highest-precedence winner, (ii) `terraform_files` populated even when `type != "terraform"` (the additive escape hatch), (iii) `confidence: "low"`, (iv) bare `deployment.multi_type` warning. New AC-20 (`_DEPLOYMENT_DETECTORS` precedence tuple) + AC-21 (`_DEPLOYMENT_PARSERS` dispatch registry) make extension by addition observably testable.

7. **CV-3 / CN-6 / TQ-8 (BLOCK) — `type: "none"` slice IS emitted.** Notes mentioned this; no AC. New AC-23 pins: probe runs on a `tmp_path` containing only a README; slice IS emitted with `type: "none"`, all empty fields, `confidence: "high"`. Distinguishes "ran and found nothing" from "didn't run" from "crashed."

8. **CV-4 / TQ-9 / CN-8 (BLOCK) — Two-run byte-equal determinism.** DeploymentProbe is more exposed to nondeterminism than CIProbe (globs `values-*.yaml`, walks Kustomize resources, walks `deploy/**`). New AC-41 fixtures mtime-shuffled inputs and asserts `json.dumps(s1, sort_keys=True) == json.dumps(s2, sort_keys=True)`. Implementer must sort `environments` by `name`, `terraform_files` lex, `exposed_ports` ascending, `required_env_vars` lex.

9. **CV-5 / TQ-11 (BLOCK) — Confidence outcomes per scenario (parametrized).** Notes enumerated 5 confidence rules; only one was tested (12-env `high`). New AC-42 parametrizes over 8 scenarios with expected confidence + warning ID. Catches the constant-`high` or constant-`low` mutation.

10. **CV-7 / TQ-13 (BLOCK) — `values.prod.yaml` non-conforming filename.** Notes prescribed the warning + full-stem name; no AC; no test. New AC-15 pins. AC-18 separately parametrizes over `.yml` filename variants for `kustomization`, `values`, `values-*`.

11. **CV-9 / TQ-5 / DP-5 (BLOCK) — `_WARNING_IDS` frozenset + import-time ADR-0007 conformance loop.** Story enumerated ≥ 5 warning IDs scattered across Outline + Notes; no module-level frozenset; no import-time pattern check. New AC-38 pins a verbatim 9-entry frozenset (3 added: `helm.no_values_files`, `deployment.raw_no_workloads`, `kustomization.depth_cap_exceeded`, `kustomization.file_cap_exceeded`); import-time loop catches typos. AC-40 mirrors for `_ERROR_IDS`.

12. **CV-10 / TQ-6 (BLOCK) — Schema rejection at exact JSON Pointer + walk-every-nested-block.** Original AC-8 said "right JSON Pointer" without anchoring. New AC-8 parametrizes over 4 injection sites (root, `image_reference`, `environments[0]`, `environments[0].image_reference`). AC-7 walks the schema asserting `additionalProperties: false` at every `type: object` node — with **one documented exception**: `security_context` is `additionalProperties: true` (CN-7 / option-a) because Kubernetes `SecurityContext` is a ~30-field open-shape evolving structured type and verbatim pass-through is the load-bearing convention.

13. **CV-11 / TQ-7 (BLOCK) — Registry membership across languages.** Original AC-9 only checked the additive import line. New AC-5 parametrizes `DeploymentProbe in default_registry.for_task("*", langs)` over 5 language sets including `frozenset()` and `{"go"}`. Catches accidental `applies_to_languages` narrowing.

14. **CV-12 / TQ-16 (BLOCK) — Kustomize overlay caps + `_walk_overlays` pure helper.** Outline §4 said "depth 5, 50 files; warning + truncation"; no AC; no test. New AC-26 + AC-27 pin both caps via fixtures (60 resources, depth-6 chain) and unit-test the pure `_walk_overlays` helper in isolation against four fixture shapes.

15. **CV-13 / TQ-17 (BLOCK) — `terraform_files` POSIX paths-relative-to-root.** Original AC-6 said "or relative-path variant" — accepting backslashes / `./` prefix / absolute. New AC-33 pins POSIX forward-slash, no abs, no `./`, with a nested-dir fixture (`modules/network/vpc.tf`).

16. **CV-14 / TQ-10 / CN-8 (BLOCK) — `exposed_ports` / `required_env_vars` sorted + deduped.** Original silent on ordering or dedup. New AC-30 + AC-31 pin sorted-asc-deduped for ports and sorted-alpha-deduped for env names; env-var values never leak into the slice (facts-not-judgments).

17. **CN-9 (HIGH) — `image.repository` + `image.tag` concatenation.** Outline §3 ambiguous when both are present. New AC-17 pins the three shapes: shorthand verbatim; `repository:tag` concatenated; `repository` alone with no colon suffix. AC case (d) tests `image.tag` alone → `image_reference: None`.

18. **CN-7 (MEDIUM) — `security_context` `additionalProperties` policy.** Original AC-2 had "if not `additionalProperties: true`-style" parenthetical — a deferred decision. New AC-7 explicitly: `additionalProperties: false` at slice root, `ImageRefBlock`, `EnvironmentEntry`; `additionalProperties: true` at `security_context` (documented ADR-0004 exception with the schema's `description` field carrying the rationale). New AC-32 fixtures a verbatim k8s `securityContext` and asserts pass-through.

19. **CN-10 (MEDIUM) — `Chart.yaml`-only with no values files.** Edge case not covered. New AC-16 pins `helm.no_values_files` warning + `low` confidence. Mirrors S4-01 `ci.empty_workflows_dir` precedent (marker matched, no consumable content).

20. **CN-14 (INFO) — `errors[]` typed-exception routing.** Original silent on `ProbeOutput.errors`. New AC-40 pins typed-exception routing via `_ERROR_IDS` frozenset + ADR-0007 conformance loop. Routes `SizeCapExceeded` / `DepthCapExceeded` / `MalformedYAMLError` / `SymlinkRefusedError` into `ProbeOutput.errors` (not `slice.warnings`).

## Design-pattern lifts elevated to ACs (Open/Closed at file boundary)

The rule-of-three threshold is decisively met for the dispatch pattern (5 detectors + 5 parsers + 9 warning IDs). Mirrors `node_build_system.py:212-262` and S4-01's hardened shape verbatim.

- **AC-19 — `_DEPLOYMENT_TYPE: TypeAlias = Literal[...]`** with schema-enum equivalence test. (DP-6)
- **AC-20 — `_DEPLOYMENT_DETECTORS: Final[tuple[tuple[_DEPLOYMENT_TYPE, Callable[[Path], bool]], ...]]`** with import-time precedence anchor `("helm","kustomize","raw","terraform")`. Adding a 5th type is one tuple entry + one new predicate. (DP-1)
- **AC-21 — `_DEPLOYMENT_PARSERS: Final[Mapping[_DEPLOYMENT_TYPE, Callable[..., _ParseResult]]]`** with import-time `keys() == set(get_args(_DEPLOYMENT_TYPE))` anchor. Catches a new Literal arm without a parser. (DP-2)
- **AC-27 — `_walk_overlays` pure helper** as the load-bearing zip-slip primitive — tested in isolation, separate from the probe-level integration test. Mirrors `_walk_extends` in `node_build_system.py:373`. (DP-4)
- **AC-38 — `_WARNING_IDS` frozenset + import-time ADR-0007 pattern loop.** 9-entry verbatim set. (DP-5 / CV-9 / TQ-5)
- **AC-43 — `_demote` + `_CONFIDENCE_RANK` copied verbatim** from `node_build_system.py:245+276`. Monotone (downgrade-only). Bare `confidence = "low"` assignments forbidden. (DP-8)
- **AC-44 — Eight pure helpers extracted** (`_is_under`, `_extract_image_ref`, `_select_deployment_type`, `_env_name_from_filename`, `_filter_k8s_kinds`, `_extract_container_specs`, `_aggregate_exposed_ports`, `_aggregate_env_var_names`). Functional core / imperative shell. (DP-3)
- **AC-45 — `_ParseResult` NamedTuple** as the only return shape across all 5 parsers; `run()` does not access parser internals. (DP-9)
- **AC-46 — `ImageRefBlock` + `EnvironmentEntry` TypedDicts.** `mypy --strict` catches missing-field constructions. (DP-7)

## Patterns DELIBERATELY deferred (premature-abstraction guard — Rule 2)

Documented in story Notes §"Deferred patterns":

- **`DeploymentDetector` / `DeploymentParser` ABC + plugin discovery** — lift in Phase 4+.
- **`parsers/_helm.py` / `parsers/_kustomize.py` per-shape module split** — defer to Phase 2+ if a third shape lands.
- **`Slice(BaseModel)` Pydantic class** — defer if slice grows past 12 fields.
- **`SecretName` / `RepoRelativePath` / `YamlPath` `NewType`s** — premature; bare `str` in Phase 1.
- **Discriminated-union `_ParseOutcome`** (`_ParseSuccess | _ParseFailure`) — `_ParseResult` NamedTuple suffices in Phase 1.
- **Shared `probes/_confidence.py` kernel** — copy verbatim from `node_build_system.py`; extract at S4-03 once the 4th consumer lands. Matches S4-01's deferral.
- **Shared `probes/_warning_ids.py`** — extract at ≥ 4 probes; S4-02 is the 3rd.
- **YAML catalog for `_DEPLOYMENT_DETECTORS`** — unlikely 2nd consumer.
- **`_WarningCollector` helper class** — defer until cross-helper aggregation needed.
- **`flux` / `argo-cd` detectors** — explicitly out-of-scope for Phase 1; canonical extension example documented.

## Conflict resolutions surfaced (per Rule 7)

- **Notes `helm.values_file_parse_error:<path>` vs ADR-0007 (CN-1).** Validator priority: `Consistency > Coverage > Test-Quality > Design-Patterns`. ADR-0007 is the authority on warning ID shape. Bare ID; offending path moves to `raw/deployment.json`. S4-01 CN-1 precedent applied verbatim.
- **AC-2's deferred `security_context` decision (CN-7).** Two options surfaced; option-a (pass-through with `additionalProperties: true` at this nested block only) chosen. Documented in schema `description`. ADR-0004 spirit preserved at slice root, `ImageRefBlock`, `EnvironmentEntry`; explicit exception at one nested block.
- **Refactor's two pure helpers vs codebase pure-helper density (DP-3).** Original Refactor named two (`_is_under`, `_extract_image_ref`); sibling `node_build_system.py` has five pure helpers; S4-01 hardened to five. Per Rule 11, S4-02 elevated to eight pure helpers (one more than S4-01 because raw-manifest kind filtering + container-spec walking are deeper than any CIProbe sub-step).
- **`@pytest.mark.asyncio` vs sibling `asyncio.run` (TQ-2).** Sibling wins per Rule 11; no `pytest-asyncio` in declared dev-deps; matches S4-01 / S2-02 hardened precedent.
- **Singleton `type` field vs `additional_providers`-style multi-type tracking (CN-3).** Arch's design is internally consistent — `terraform_files` carries Terraform evidence even when `type != "terraform"` (the additive escape hatch). Story now pins this explicitly in AC-22 + Notes; arch-doc asymmetry flagged for follow-up but story honors verbatim per Rule 11.

## Departures from arch surfaced (per Rule 7)

- **Warning ID format**: Notes originally inherited the arch line 540 `<id>:<path>` style which violates ADR-0007. Story emits bare IDs; arch-doc fix pending.
- **`declared_inputs` asymmetry**: arch line 545 has `kubernetes/**/*.yaml` but no `.yml` variant, while `deploy/**` and `k8s/**` are symmetric. Story honors arch verbatim per Rule 11; flagged for arch-doc follow-up.
- **Singleton `type` discriminator**: cross-slice asymmetry with `CISlice.additional_providers`. Story uses `terraform_files` as the additive escape hatch; consumer convention documented in Notes.

## Context Brief (Stage 1)

**Story intent.** Lands `DeploymentProbe` — the fourth new Phase 1 probe and the largest in Step 4. Populates `deployment` slice from 5 deployment shapes (Helm chart + values files, Kustomize overlay tree, raw Kubernetes manifests in `deploy/`/`k8s/`/`kubernetes/`, Terraform `*.tf` paths, or `none`). Records `image_reference` + `environments: list[EnvironmentEntry]` (per ADR-0012's additive multi-env shape), `chart_path`, `kustomization_resource_path_outside_repo` (zip-slip signal), `terraform_files: list[str]` (paths-only), `exposed_ports`, `required_env_vars`, `security_context` — facts-not-judgments throughout. No Helm template rendering, no `kustomize build`, no `python-hcl2`, no `helm`/`kustomize`/`terraform` binaries (ADR-0011). The load-bearing security pin is zip-slip refusal via `Path.resolve()` + `.is_relative_to(root.resolve())` containment, with a unit-level test at probe-PR-merge time and a system-level test at S5-03.

**Phase-1 exit criteria the story must satisfy.** ADR-0004 (sub-schema `additionalProperties: false` at root + nested), ADR-0007 (warning-ID pattern), ADR-0010 (envelope-level optionality), **ADR-0011 (no Helm render / no HCL / no kustomize build)**, **ADR-0012 (multi-env Helm as `environments: list` with nullable primary)**, ADR-0005 (coverage carve-out 85/75 floor), production ADR-0005 (no LLM in gather). Phase-0 chokepoints (`base.py`, `registry.py`, sanitizer, coordinator) untouched — extension by addition.

**Load-bearing constraints from arch.** Component design #6 (lines 542–555) prescribes 5-way file-marker dispatch; data model (line 734) pins `DeploymentSlice` shape; edge cases row 4 (zip-slip) + row 15 (12-env chart) named explicitly. Failure behavior (line 555) says "Any deployment-file parse error → that file skipped, structured warning; gather continues."

**Sibling pattern to mirror.** `src/codegenie/probes/node_build_system.py` — module-level `_LOCKFILE_PRECEDENCE`, `_BUNDLERS_SORTED`, `_BERRY_MARKERS` precedence-tuples; module-level `_WARNING_IDS` + `_ERROR_IDS` frozensets with import-time ADR-0007 pattern loop; pure-helper extraction (`_select_package_manager`, `_walk_extends`, `_deps_union`, `_demote`); `_CONFIDENCE_RANK` Mapping; test harness conventions (`asyncio.run` over `pytest-asyncio`); contract-attributes test with `isinstance(declared_inputs, list)`. Plus the just-shipped S4-01 (`CIProbe`) hardened shape with `_PROVIDER_PRECEDENCE` + `_CI_PARSERS` + 5 pure helpers + walk-the-schema test.

## Critic reports (Stage 2 — condensed)

### Coverage critic — Verdict: HARDEN

20 findings (11 block, 8 harden, 1 nit). Highlights:
- CV-1 [BLOCK]: Raw-manifest kind filter only tests `Deployment` positive — extend to all 4 positive + 8 negative kinds.
- CV-2 [BLOCK]: Multi-type detection / precedence has no AC; new `_TYPE_PRECEDENCE` + parametrized matrix.
- CV-3 [BLOCK]: `type: "none"` slice-still-emitted not pinned.
- CV-4 [BLOCK]: Two-run byte-equal determinism missing.
- CV-5 [BLOCK]: Confidence outcomes per branch not pinned.
- CV-6 [BLOCK]: `.yml` variants for `kustomization.yml`, `values.yml`, `values-prod.yml` untested.
- CV-7 [BLOCK]: `values.prod.yaml` non-conforming filename has no test.
- CV-8 [BLOCK]: Per-file values-file parse error pinned with colon-suffixed warning (CN-1).
- CV-9 [BLOCK]: `_WARNING_IDS` frozenset + import-time anchor not lifted.
- CV-10 [BLOCK]: Schema-rejection JSON Pointer + walk-every-nested-block missing.
- CV-11 [BLOCK]: Registry membership across languages not pinned.
- CV-12 [HARDEN]: Overlay traversal cap (depth 5 / 50 files) untested.
- CV-13 [HARDEN]: `terraform_files` POSIX paths-relative-to-root unpinned.
- CV-14 [HARDEN]: `exposed_ports` / `required_env_vars` dedup + ordering unspecified.
- CV-15 [HARDEN]: Multi-doc YAML with only non-workload kinds untested.
- CV-16 [HARDEN]: `security_context` shape decision left ambiguous.
- CV-17 [HARDEN]: Kustomize `bases:` (deprecated) Out-of-scope vs warning question.
- CV-18 [HARDEN]: Three-way and four-way multi-type cases not parametrized.
- CV-19 [NIT]: `version: str` value (`"1.0.0"`) not anchored.
- CV-20 [NIT]: `errors: list[WarningId]` field unaddressed.

### Test-Quality critic — Verdict: HARDEN

19 findings (8 block, 11 harden). Highlights:
- TQ-1 [BLOCK]: Test-helper preamble undefined (S2-02 / S4-01 repeated).
- TQ-2 [BLOCK]: `@pytest.mark.asyncio` vs sibling `asyncio.run`.
- TQ-3 [BLOCK / SECURITY]: Zip-slip `os.open` spy is a non-event guard — replace with sentinel-exfiltration.
- TQ-4 [BLOCK]: Contract-attributes test missing (S2-02 frozen-ABC bug).
- TQ-5 [BLOCK]: `helm.values_file_parse_error:<path>` violates ADR-0007 (S4-01 CN-1 repeated).
- TQ-6 [BLOCK]: Schema-rejection test missing despite AC.
- TQ-7 [BLOCK]: Registry membership test missing.
- TQ-8 [BLOCK]: `type: "none"` positive test missing.
- TQ-9 [HARDEN]: Determinism / byte-equal test missing.
- TQ-10 [HARDEN]: `exposed_ports` / `required_env_vars` ordering + dedup unpinned.
- TQ-11 [HARDEN]: Confidence outcomes only tested in one branch.
- TQ-12 [HARDEN]: Per-values-file parse error path missing.
- TQ-13 [HARDEN]: Non-conforming `values.prod.yaml` filename test missing.
- TQ-14 [HARDEN]: Multi-doc YAML with no Deployment kinds test missing.
- TQ-15 [HARDEN]: `additional_providers`-style multi-type test missing.
- TQ-16 [HARDEN]: Kustomize overlay caps untested.
- TQ-17 [HARDEN]: `terraform_files` relative-path-only invariant unpinned.
- TQ-18 [HARDEN]: Static-grep test fragility (replace with AST walk).
- TQ-19 [HARDEN]: `security_context` shape unpinned.

### Consistency critic — Verdict: HARDEN

15 findings (1 critical, 4 high, 4 medium, 2 low, 4 info). Highlights:
- CN-1 [CRITICAL]: `helm.values_file_parse_error:<path>` ADR-0007 violation — resolved (bare ID; arch-doc drift flagged).
- CN-2 [HIGH]: `deployment.multi_type` enumerated in Notes; absent from ACs + TDD.
- CN-3 [HIGH]: Singleton `type` vs CI's `additional_providers` cross-slice asymmetry — terraform_files is the additive escape hatch; document explicitly.
- CN-4 [HIGH]: ADR-0011 enforcement leans on thin grep; broaden to AST walk + subprocess/exec/which checks.
- CN-5 [HIGH]: `declared_inputs` not pinned verbatim — drift risk.
- CN-6 [HIGH]: `type: "none"` emission semantics silent in ACs.
- CN-7 [MEDIUM]: `security_context` `additionalProperties` policy — pick option-a (pass-through).
- CN-8 [MEDIUM]: `exposed_ports` / `required_env_vars` ordering + dedup unpinned.
- CN-9 [MEDIUM]: `ImageRefBlock` with both `image.repository` + `image.tag` ambiguous — pin concatenation.
- CN-10 [MEDIUM]: `Chart.yaml` exists with no `values*.yaml` — `helm.no_values_files` warning.
- CN-11 [LOW]: Arch line 545 `kubernetes/**/*.yaml` lacks `.yml` variant — drift flagged.
- CN-12 [LOW]: `_TYPE_PRECEDENCE` Open/Closed seam not surfaced (deferred to DP-1).
- CN-13 [LOW]: `version: str` value not anchored.
- CN-14 [INFO]: `errors[]` typed-exception routing unaddressed.
- CN-15 [INFO]: `chart_path: str | None` value not anchored.

### Design-Patterns critic — Verdict: HARDEN

11 findings (5 block, 4 harden, 2 nit). Highlights:
- DP-1 [BLOCK]: `_DEPLOYMENT_DETECTORS` precedence tuple replaces inline `_detect_type` chain.
- DP-2 [BLOCK]: `_DEPLOYMENT_PARSERS` dispatch registry replaces inline branch chain.
- DP-3 [BLOCK]: Functional core / imperative shell — extract 8 pure helpers.
- DP-4 [BLOCK]: `_walk_overlays` pure generator for Kustomize traversal.
- DP-5 [BLOCK]: `_WARNING_IDS` frozenset + import-time ADR-0007 loop.
- DP-6 [HARDEN]: `_DEPLOYMENT_TYPE: TypeAlias` alias.
- DP-7 [HARDEN]: `EnvironmentEntry` / `ImageRefBlock` TypedDicts.
- DP-8 [HARDEN]: Reuse `_demote` + `_CONFIDENCE_RANK` from `node_build_system.py`.
- DP-9 [HARDEN]: `_ParseResult` NamedTuple uniform dispatch shape.
- DP-10 [NIT]: `NewType` for paths — deferred (rule of three not met cross-file).
- DP-11 [NIT]: `slice_fields` in-place mutation — collapses naturally with DP-2 + DP-9.

## Final stats

- ACs: 10 → **47** (one observable per AC; all individually-verifiable)
- TDD tests: 7 → **~35** (most parametrized; explicit `asyncio.run` preamble; sentinel-exfiltration zip-slip; AST-walked import check; schema-walk + JSON-Pointer rejection; confidence × warning matrix; pure-helper unit tests)
- New typed warning IDs added: 4 (`helm.no_values_files`, `deployment.raw_no_workloads`, `kustomization.depth_cap_exceeded`, `kustomization.file_cap_exceeded`); total now 9.
- New typed error IDs: 4 (`deployment.size_cap_exceeded`, `deployment.depth_cap_exceeded`, `deployment.malformed_yaml`, `deployment.symlink_refused`).
- New module-level Open/Closed seams: 9 (`_DEPLOYMENT_TYPE`, `_DEPLOYMENT_DETECTORS`, `_DEPLOYMENT_PARSERS`, `_RAW_KIND_FILTER`, `_WARNING_IDS`, `_ERROR_IDS`, `_CONFIDENCE_RANK`, `_ID_PATTERN`, `_ParseResult`).
- Pure helpers required: 8 (functional core / imperative shell; one more than S4-01 because raw-manifest extraction is deeper).
- TypedDicts at slice boundary: 2 (`ImageRefBlock`, `EnvironmentEntry`).
- Critical contradictions resolved: 1 (CN-1 — same colon-suffix shape as S4-01 CN-1).
- Block-tier internal contradictions resolved: 3 (TQ-1 / TQ-2 / TQ-3).
- Arch-doc drifts flagged for follow-up: 3 (CN-1 colon-suffix; CN-11 `kubernetes/**/*.yml` asymmetry; CN-3 cross-slice singleton-vs-list asymmetry).
