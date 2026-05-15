# Story S4-01 — `CIProbe` + sub-schema

**Step:** Step 4 — Ship `CIProbe`, `DeploymentProbe`, and `TestInventoryProbe`
**Status:** Done (executed 2026-05-15 — phase-story-executor; see [`_attempts/S4-01.md`](_attempts/S4-01.md))
**Effort:** M
**Depends on:** S1-03 (`safe_yaml`), S1-05 (catalogs — `ci_providers.yaml`)
**ADRs honored:** ADR-0004 (`additionalProperties: false`), ADR-0006 (catalog-in-`declared_inputs` cache invalidation), ADR-0007 (warning-ID pattern), ADR-0009 (no new C-extension parser deps), ADR-0010 (Layer A slices optional at envelope), production ADR-0005 (no LLM in gather)

## Validation notes (2026-05-14, phase-story-validator)

This story was hardened from 7 bundled ACs + 6 TDD tests → **27 individually-verifiable ACs + 22 TDD tests** (most parametrized). Major changes:

- **CN-1 (CRITICAL)** — Resolved arch-vs-ADR-0007 contradiction: arch §"Component design" #5 line 540 prescribed `warnings: ["ci.workflow_parse_error:<path>"]` (colon-suffixed), which violates ADR-0007's `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` pattern. **Resolution per Rule 7 (surface conflicts, don't average)**: drop the path suffix. Per-file parse failures emit the bare `ci.workflow_parse_error` ID and the offending workflow path is *omitted* from `workflow_files`; the path provenance lives in `raw/ci.json` (raw artifact), not in the WarningId. **Arch-doc drift flagged for follow-up cleanup in PR body.**
- **CN-3 / CV-2 / DP-12** — Added explicit AC + test for the no-CI repo case (probe runs on every language because `applies_to_languages = ["*"]`; absent-marker case must produce a slice with `provider: None`, `confidence: "high"`).
- **CV-8 / Outline §2 vs Notes §1** — Resolved internal contradiction: Notes specified `{0,128}`-bounded secrets regex; Implementation outline specified unbounded `[A-Za-z0-9_]*`. The bounded form is security-load-bearing (only regex on attacker-controllable bytes); Outline updated to match. New AC + ReDoS test.
- **CV-1** — The bundled "tests" AC split into seven distinct positive-path ACs (one observable per AC).
- **DP-1 / DP-2 / DP-3 / DP-4 / DP-9 (BLOCK-tier design opportunities)** — Elevated to ACs because extension-by-addition is observably testable: module-level `_CI_PARSERS` dispatch registry keyed on `CIProviderEntry.parser` Literal arms; `_PROVIDER_PRECEDENCE` anchor assertion; `_IMAGE_BUILD_MARKERS` tuple (with run-vs-uses tag — fixes the original outline's run-vs-uses confusion); five pure helpers extracted; module-level `_WARNING_IDS` frozenset with import-time ADR-0007 pattern assertion. Mirrors `_BERRY_MARKERS` / `_LOCKFILE_PRECEDENCE` patterns in `node_build_system.py`.
- **TQ-1 / TQ-2** — Test helpers preamble made explicit (`_snapshot`, `_ctx`, `_run_probe`, `_write_workflow`); contract-attributes test added (T-2) anchoring the verbatim 7-entry `declared_inputs` list.
- **TQ-3 / CV-13** — Multi-provider precedence test parametrized over five marker combinations; sibling test `test_ci_providers_catalog_order_locked` pins catalog YAML order so a refactor that sorts the loader breaks loudly.
- **TQ-15** — Refactor section's "ban `pytest.mark.parametrize`" prescription was wrong (contradicted by sibling `test_node_build_system.py` which uses parametrize for 10+ tests, including the S2-02 hardening's block-tier `test_lockfile_precedence_total_ordering`). Rewritten: parametrize encodes invariants over many inputs (Rule 9); one **invariant** per test, parametrized over all inputs that exercise it.
- **DP-5/6/7/8** — Tagged-union and shared-confidence-helper opportunities surfaced in Notes-for-implementer as deferred (rule-of-three not yet met cross-file; will lift at S4-03 once `Deployment`/`TestInventory` repeat the pattern).

**Conflicts resolved per validator priority (`Consistency > Coverage > Test-Quality > Design-Patterns`):**
1. Arch line 540's `ci.workflow_parse_error:<path>` vs ADR-0007 → ADR-0007 wins; bare ID emitted; arch doc-drift flagged.
2. Outline §2 unbounded regex vs Notes §1 bounded regex → bounded wins (security-load-bearing per Rule 9).
3. Refactor "ban parametrize" vs sibling pattern → sibling wins (Rule 11 — match codebase conventions; Rule 9 — invariants encoded by parametrization).

Full report: [`_validation/S4-01-ci-probe.md`](_validation/S4-01-ci-probe.md).

## Context

The `CIProbe` populates the `ci` slice of `repo-context.yaml` (`localv2.md §5.1 A4`). It identifies which CI system the repo uses (GitHub Actions, GitLab CI, CircleCI, Jenkins, Azure Pipelines), enumerates workflow files, extracts the commands those workflows run (build, test, image-build, smoke), and surfaces any `${{ secrets.* }}` references — **as literal names only, never resolved**. This is a `facts-not-judgments` probe per `production/design.md §2.4`: the probe records what's there; the planner decides what it means.

The probe is structurally the simplest of the three Step 4 probes — it only reads YAML files in well-known locations and dict-looks-up provider markers against `ci_providers.yaml`. But two design tensions concentrate here. First, `localv2.md §5.1 A4` declares `provider` as a singleton; real repos sometimes ship both `.github/workflows/` and `.gitlab-ci.yml`. The arch's resolution (`phase-arch-design.md §"Component design" #5`) is to keep `provider` singleton (first-match wins, deterministic order from `ci_providers.yaml`) and add a Phase-1-additive `additional_providers: list[str]` for the rest, downgrading `confidence` to `low` so the planner sees the multi-provider signal. Second, Jenkinsfile is Groovy — not parseable by `safe_yaml`. Phase 1's compromise is a single bounded regex `sh '...'` / `sh "..."` (single capture group, line-bounded; **no backtracking**) → `confidence: low` + `warnings: ["ci.jenkinsfile_regex_only"]`. CircleCI / Azure Pipelines are presence-only stubs; deepening is a Phase 2 concern.

`coverage carve-out` (ADR-0005, declared in S4-04): `ci.py` ships at 85% line / 75% branch, not 90/80. The structurally-narrow `if provider in ci_providers` branches make a uniform 90/80 gameable per Rule 9; intent-verifying tests carry the load.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #5 CIProbe` — full interface contract (`declared_inputs`, internal structure, performance envelope, failure behavior).
  - `../phase-arch-design.md §"Data model" CISlice` — Python-shaped slice contract, `additional_providers: list[str]` shape resolving the singleton-vs-list disagreement.
  - `../phase-arch-design.md §"Edge cases"` rows 13 (`local-action` reference), 14 (200-workflow stress).
  - `../phase-arch-design.md §"Open questions deferred to implementation" #4` — reusable workflows recorded as paths only.
- **Phase ADRs:**
  - `../ADRs/0004-per-probe-subschema-additional-properties-false.md` — `ci.schema.json` declares `additionalProperties: false` at root.
  - `../ADRs/0005-coverage-carve-outs-deployment-ci.md` — `ci.py` is at 85/75 (declared in S4-04, enforced in S6-02).
  - `../ADRs/0007-warnings-id-pattern.md` — every typed warning matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`.
  - `../ADRs/0009-no-new-c-extension-parser-dependencies.md` — Phase 1 stays inside the `pyyaml.CSafeLoader` + stdlib `json` + `blake3` closure (plus optional `pyarn`).
  - `../ADRs/0010-layer-a-slices-optional-at-envelope.md` — `ci` slice is **optional** at envelope `probes.*` level (`applies_to_languages = ["*"]` so the probe still runs on non-Node, but slice absence is admitted).
- **Production ADRs:**
  - `../../../production/adrs/0005-no-llm-in-gather-pipeline.md` — `references_secrets` records literal names; the probe never calls out to resolve them.
- **Source design:**
  - `../final-design.md §"Components" #5` — synthesis ledger row for `CIProbe`.
  - `../localv2.md §5.1 A4` — the `ci` slice contract this conforms to.
- **Existing code (Step 1 + 2 output):**
  - `src/codegenie/parsers/safe_yaml.py` (S1-03) — `safe_yaml.load(path, max_bytes=10*1024*1024, max_depth=64)`.
  - `src/codegenie/catalogs/__init__.py` (S1-05) — `CI_PROVIDERS: Mapping[str, CIProviderEntry]` + `CI_PROVIDERS_CATALOG_VERSION: int`.
  - `src/codegenie/catalogs/ci_providers.yaml` (S1-05) — provider catalog entries (`{name, marker_paths, parser}`).
  - `src/codegenie/probes/base.py` (Phase 0) — `Probe` ABC contract.
  - `src/codegenie/probes/__init__.py` — explicit additive import to register.
  - `src/codegenie/errors.py` (S1-01) — `SizeCapExceeded`, `DepthCapExceeded`, `MalformedYAMLError`.
- **External docs:**
  - GitHub Actions workflow syntax — relevant keys: `jobs.*.steps[].run`, `jobs.*.steps[].uses`, `${{ secrets.NAME }}`.
  - GitLab CI YAML structure — `script:`, `before_script:`, `image:`.

## Goal

Ship a deterministic, in-process, no-network `CIProbe` that populates a strict `ci` slice (`additionalProperties: false` at root) from `.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, `.circleci/config.yml`, and `azure-pipelines.yml`, emits typed `WarningId`-pattern warnings for every failure mode, and is registered via explicit additive import.

## Acceptance criteria

### Probe contract + registration

- [ ] **AC-1 — Probe contract (verbatim).** `src/codegenie/probes/ci.py` defines `class CIProbe(Probe)` with **list[str]** (not tuple) class attributes matching the frozen `Probe` ABC at `src/codegenie/probes/base.py`: `name = "ci"`, `version = "1.0.0"`, `layer = "A"`, `tier = "base"`, `applies_to_languages = ["*"]`, `applies_to_tasks = ["*"]`, `requires = []`, `timeout_seconds = 10`, and `declared_inputs` exactly equal to:
      ```python
      [
          ".github/workflows/*.yml",
          ".github/workflows/*.yaml",
          ".gitlab-ci.yml",
          ".circleci/config.yml",
          "Jenkinsfile",
          "azure-pipelines.yml",
          "src/codegenie/catalogs/ci_providers.yaml",
      ]
      ```
  The catalog YAML in the list ensures a catalog edit invalidates `ci` cache entries (ADR-0006).
- [ ] **AC-2 — Registry membership.** `src/codegenie/probes/__init__.py` adds **one** explicit additive import line registering `CIProbe` (no rewrite of any list). `default_registry.all_probes()` includes `CIProbe`. `default_registry.for_task("*", langs)` returns a tuple containing `CIProbe` for every `langs ∈ {frozenset({"go"}), frozenset({"javascript"}), frozenset({"python"}), frozenset()}` — the probe is language-agnostic.
- [ ] **AC-3 — Sub-schema strict + envelope-optional.** `src/codegenie/schema/probes/ci.schema.json` exists, Draft 2020-12, declares `additionalProperties: false` at the slice root **and at every nested object** (verified by static schema introspection — a recursive walker asserts the constraint at every `type: object` node). The envelope's `properties.probes.required` array does NOT list `ci`. Validates the shapes in `phase-arch-design.md §"Data model" CISlice`.

### Slice shape — positive paths

- [ ] **AC-4 — GHA image-build via `run: docker build`.** A `.github/workflows/x.yml` with a step `run: docker build -t app .` produces `provider: "github_actions"`, `builds_image: true`, `image_build_command` contains the substring `"docker build"`, `confidence: "high"`.
- [ ] **AC-5 — GHA image-build via `run: docker buildx`.** Same with `run: docker buildx build .` → `image_build_command` contains `"docker buildx"`.
- [ ] **AC-6 — GHA image-build via `uses: docker/build-push-action`.** A step with `uses: docker/build-push-action@v5` produces `builds_image: true`, `image_build_command` contains `"docker/build-push-action"`. (Distinct code path from AC-4/AC-5: `uses:` strings, not `run:` strings — the original outline conflated the two; the registry tags each marker as `"run"` or `"uses"`.)
- [ ] **AC-7 — GHA without image build.** Workflow with `run: docker run hello-world` (Docker invoked, but not as a build) → `builds_image: false`, `image_build_command: null`, `confidence: "high"`.
- [ ] **AC-8 — GitLab CI parse, single provider.** `.gitlab-ci.yml` with `script: ["npm test"]` → `provider: "gitlab_ci"`, `unit_test_command` populated, `confidence: "high"`, `warnings == []`.
- [ ] **AC-9 — Jenkinsfile bounded-regex extraction.** `Jenkinsfile` with `sh 'npm test'` → `provider: "jenkins"`, `unit_test_command` contains `"npm test"`, `confidence: "low"`, `warnings == ["ci.jenkinsfile_regex_only"]`.
- [ ] **AC-10 — CircleCI presence-only stub.** `.circleci/config.yml` present (no parse) → `provider: "circleci"`, `workflow_files == []`, `confidence: "low"`, `warnings == ["ci.circleci_presence_only"]`.
- [ ] **AC-11 — Azure Pipelines presence-only stub.** `azure-pipelines.yml` present → `provider: "azure_pipelines"`, `confidence: "low"`, `warnings == ["ci.azure_pipelines_presence_only"]`.
- [ ] **AC-12 — Empty `.github/workflows/` directory.** Directory exists with zero `*.yml`/`*.yaml` files → `provider: "github_actions"` (catalog marker matched), `workflow_files == []`, `builds_image: false`, `confidence: "low"`, `warnings == ["ci.empty_workflows_dir"]`.
- [ ] **AC-13 — No CI files anywhere.** Repo has none of the marker paths → slice IS produced (probe runs because `applies_to_languages = ["*"]`), `provider: null`, `additional_providers: []`, `workflow_files: []`, `builds_image: false`, all `*_command` fields `null`, `references_secrets: []`, `warnings: []`, `confidence: "high"` (the absence is itself a high-confidence fact). This distinguishes "ran and found nothing" from ADR-0010's "didn't run" (slice absent).

### Multi-provider + precedence

- [ ] **AC-14 — Multi-provider downgrades + warning.** Repo with `.github/workflows/x.yml` AND `.gitlab-ci.yml` AND `.circleci/config.yml` → `provider == "github_actions"` (catalog precedence), `additional_providers == ["gitlab_ci", "circleci"]` (catalog declaration order, NOT alpha — alpha would yield `["circleci", "gitlab_ci"]`), `confidence: "low"`, `warnings` contains `"ci.multi_provider"`.
- [ ] **AC-15 — Catalog precedence pinned at file boundary.** `src/codegenie/probes/ci.py` declares `_PROVIDER_PRECEDENCE: Final[tuple[str, ...]]` at module scope, equal to `("github_actions", "gitlab_ci", "circleci", "jenkins", "azure_pipelines")`. Import-time `assert _PROVIDER_PRECEDENCE == tuple(CI_PROVIDERS.keys())` refuses to load the module if catalog YAML order drifts from file-boundary precedence (Rule 12 — fail loud; mirrors `assert _LOCKFILE_PRECEDENCE[0][1] == "bun"` in `node_build_system.py:256`).
- [ ] **AC-16 — `additional_providers == []` for single-provider sanity.** A `.gitlab-ci.yml`-only repo → `additional_providers == []`, NO `ci.multi_provider` warning, `confidence: "high"`. (Catches a "always emit `ci.multi_provider`" mutation.)

### Secrets capture (facts-not-judgments — production ADR-0005)

- [ ] **AC-17 — Bounded secrets regex.** The secrets regex used in `ci.py` is exactly `r"\$\{\{\s*secrets\.([A-Za-z_][A-Za-z0-9_]{0,128})\s*\}\}"` (a 130-character upper bound on the captured identifier; no `*`, no `+`, no nested groups — anchored upper bound). The regex is a module-level `Final[re.Pattern[str]]` constant `_SECRETS_RE`.
- [ ] **AC-18 — Secrets captured as literal names; sorted + deduplicated.** `references_secrets` is the **lexicographically-sorted, deduplicated** list of distinct literal identifier strings captured by `_SECRETS_RE` across all parsed workflow files. **The probe never resolves a secret value** — no `os.environ.get`, no `gh secret list`, no network call. A workflow with `${{ secrets.B }}` then `${{ secrets.A }}` then `${{ secrets.A }}` again → `references_secrets == ["A", "B"]`.
- [ ] **AC-19 — Secrets regex case-sensitive + scope-sensitive.** `${{ env.FOO }}`, `${{ inputs.BAR }}`, `${{ Secrets.X }}` (capitalized) all do NOT land in `references_secrets`. Only the literal lowercase `secrets.IDENTIFIER` syntax matches.

### Failure handling (typed warnings, ADR-0007)

- [ ] **AC-20 — Typed warning frozenset + import-time pattern assertion.** `ci.py` declares `_WARNING_IDS: Final[frozenset[str]]` at module scope listing exactly: `{"ci.jenkinsfile_regex_only", "ci.multi_provider", "ci.workflow_parse_error", "ci.gitlab_ci_parse_error", "ci.local_action_unparsed", "ci.empty_workflows_dir", "ci.circleci_presence_only", "ci.azure_pipelines_presence_only"}`. Import-time loop asserts every member matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. Mirrors `node_build_system.py:212-254`.
- [ ] **AC-21 — Per-file workflow parse failure: skipped, gather continues.** Directory contains `bad.yml` (malformed YAML) and `good.yml` (valid) → `bad.yml` is OMITTED from `workflow_files`; `good.yml` IS in `workflow_files`; `slice["warnings"]` contains the bare ID `"ci.workflow_parse_error"` (NOT colon-suffixed with the path — see Validation notes CN-1 resolution). The offending file path is recorded in `raw/ci.json` (raw artifact) for operator triage. Slice still produced, `confidence: "high"` for the surviving facts.
- [ ] **AC-22 — `local-action` reference emits warning, does not descend.** A GHA workflow with `uses: ./.github/actions/local-action` parses successfully; `slice["warnings"]` contains `"ci.local_action_unparsed"`; the local action is NOT descended into. (Phase-1 scope per arch §"Edge cases" row 13; arch's `confidence: medium` claim is **rejected for Phase 1** — confidence stays at the surrounding workflow's level. Documented in Notes-for-implementer.)

### Determinism + extensibility

- [ ] **AC-23 — Two-run byte-equal determinism.** Two `await CIProbe().run(...)` invocations on the same fixture produce slices that are byte-equal under `json.dumps(slice, sort_keys=True)`. Specifically: `workflow_files` is sorted lexicographically; `additional_providers` follows `_PROVIDER_PRECEDENCE` order; `references_secrets` is sorted+deduped per AC-18; `warnings` insertion order is reproducible across runs.

### Implementation shape — Open/Closed at file boundary

- [ ] **AC-24 — Parser dispatch registry (`_CI_PARSERS`).** `ci.py` defines a module-level `_CI_PARSERS: Mapping[ParserKind, Callable[[Path, RepoSnapshot], _ParseOutcome]]` keyed on the `CIProviderEntry.parser` Literal arms, where `ParserKind: TypeAlias = Literal["github_actions","gitlab_ci","jenkins","circleci","azure_pipelines"]` (reused/aliased from the catalog). The `run()` body iterates `CI_PROVIDERS` once and looks up `_CI_PARSERS[entry.parser]`. **Adding a sixth parser is one new function + one dict entry — zero edits to the iterate-catalog loop.** Mirrors `_BERRY_MARKERS` in `node_build_system.py:303`. Import-time `assert set(_CI_PARSERS.keys()) == set(get_args(_PARSER_LITERAL))` catches a new catalog `Literal` arm without a corresponding parser.
- [ ] **AC-25 — `_IMAGE_BUILD_MARKERS` table + run-vs-uses tag.** `ci.py` defines `_IMAGE_BUILD_MARKERS: Final[tuple[tuple[str, Literal["run", "uses"]], ...]]` containing exactly `(("docker build", "run"), ("docker buildx", "run"), ("docker/build-push-action", "uses"))`. The probe iterates this tuple in order; first hit wins. **Fixes the original outline's run-vs-uses confusion** (the third marker is `uses:`-shaped, not `run:`-shaped — the table tags the discriminator). Adding `"podman build"` is one tuple-entry insertion.
- [ ] **AC-26 — Pure-helper extraction (functional core).** At minimum five pure helpers are extracted, each independently testable: `_select_provider(present, precedence) -> tuple[str | None, list[str]]`, `_extract_run_strings(workflow_yaml) -> list[str]`, `_extract_uses_strings(workflow_yaml) -> list[str]`, `_extract_secret_names(text) -> list[str]`, `_detect_image_build(runs, uses) -> ImageBuildOutcome | None`. The `run()` body becomes orchestration only: filesystem I/O + dispatch via `_CI_PARSERS` + assembly. Mirrors `_select_package_manager` / `_walk_extends` / `_deps_union` in `node_build_system.py`.

### Definition of done

- [ ] **AC-27 — Quality gates green; per-probe coverage reported.** `ruff check`, `ruff format --check`, `mypy --strict` on `src/codegenie/probes/ci.py` and `src/codegenie/schema/probes/ci.schema.json` (the latter via `jsonschema`'s self-validation), `pytest tests/unit/probes/test_ci.py -q` all pass. Per-probe local coverage reported in the PR body — must land at or above 85% line / 75% branch (the ADR-0005 carve-out for `ci.py`); the S6-02 ratchet cannot recover if it lands below. The PR body explicitly notes: (a) reusable-workflow `uses:` references captured as paths only (open question #4) — not descended into; (b) **arch-doc drift** flagged: `phase-arch-design.md §"Component design" #5` line 540 prescribes `ci.workflow_parse_error:<path>` which violates ADR-0007; this story emits the bare ID; arch doc to be patched in a follow-up.

## Implementation outline

1. **Define `CISlice` shape in `ci.schema.json` first** (write the schema before the code). Mirror `phase-arch-design.md §"Data model" CISlice`. `additionalProperties: false` at root **and at every nested object** (per AC-3). Each `WarningId` constrained by the ADR-0007 pattern. Slice declared optional at envelope per ADR-0010.
2. **Module-level constants in `ci.py` (Open/Closed seams — Rule 12 fail-loud).**
   - `_PROVIDER_PRECEDENCE: Final[tuple[str, ...]] = ("github_actions", "gitlab_ci", "circleci", "jenkins", "azure_pipelines")` — pinned at file boundary; import-time anchor `assert _PROVIDER_PRECEDENCE == tuple(CI_PROVIDERS.keys())` (AC-15).
   - `_IMAGE_BUILD_MARKERS: Final[tuple[tuple[str, Literal["run","uses"]], ...]]` per AC-25 — fixes the run-vs-uses confusion.
   - `_TEST_COMMAND_MARKERS: Final[tuple[str, ...]]` — module-level table for substring matching against canonical script names from `localv2.md §5.1 A4`. If this grows past five entries, file a Phase-2 ADR to migrate to a YAML catalog (matches `native_modules.yaml` precedent).
   - `_SECRETS_RE: Final[re.Pattern[str]] = re.compile(r"\$\{\{\s*secrets\.([A-Za-z_][A-Za-z0-9_]{0,128})\s*\}\}")` — bounded; AC-17.
   - `_JENKINS_SH_RE: Final[re.Pattern[str]] = re.compile(r"sh\s+['\"]([^'\"\n]{1,500})['\"]")` — bounded line-by-line; the regex IS the Jenkinsfile contract (no Groovy parser).
   - `_WARNING_IDS: Final[frozenset[str]]` per AC-20.
   - `_PARSER_LITERAL = Literal["github_actions","gitlab_ci","jenkins","circleci","azure_pipelines"]` — `ParserKind` type alias (or import from catalog if exposed).
   - Import-time `for _id in _WARNING_IDS: assert _ID_PATTERN.match(_id), f"ADR-0007 violation: {_id!r}"` (AC-20).
3. **Pure helpers (functional core — AC-26).** Five pure functions extracted, all independently unit-testable:
   - `_select_provider(present_marker_provider_names: Sequence[str], precedence: Sequence[str]) -> tuple[str | None, list[str]]` — first-match-wins; remaining preserve precedence order.
   - `_extract_run_strings(workflow_yaml: Mapping[str, Any]) -> list[str]` — pure dict walk over `jobs.*.steps[].run`.
   - `_extract_uses_strings(workflow_yaml: Mapping[str, Any]) -> list[str]` — pure dict walk over `jobs.*.steps[].uses`.
   - `_extract_secret_names(text_blob: str) -> list[str]` — pure regex over a string; sorted+deduped per AC-18.
   - `_detect_image_build(runs: Sequence[str], uses: Sequence[str]) -> tuple[bool, str | None]` — iterates `_IMAGE_BUILD_MARKERS` in order; first hit wins. Returns `(builds_image, image_build_command)`.
4. **Implement `CIProbe.run(snapshot, ctx)` (impure shell — orchestration only).**
   - Iterate `CI_PROVIDERS` (in catalog/precedence order). For each entry, check existence of `marker_paths` under `snapshot.root` via `Path.is_file()` / `Path.is_dir()` — no walks.
   - First match → `provider`; remaining matches accumulate into `additional_providers` in catalog order. If no match → emit no-CI slice per AC-13.
   - For the chosen `provider`, dispatch via `_CI_PARSERS[entry.parser]` (AC-24). Each parser is responsible for its own reads, parse-with-cap, and per-file warnings.
     - **`_parse_github_actions`**: glob `.github/workflows/*.yml` and `*.yaml` (sorted lexicographically per AC-23). For each file, `safe_yaml.load(path, max_bytes=10*1024*1024, max_depth=64)`. Per-file `SizeCapExceeded`/`DepthCapExceeded`/`MalformedYAMLError` → emit `"ci.workflow_parse_error"` (bare ID per CN-1 resolution; offending path written to `raw/ci.json`), file omitted from `workflow_files`, continue. If directory is empty → emit `"ci.empty_workflows_dir"`. Compose pure helpers: `_extract_run_strings` + `_extract_uses_strings` + `_detect_image_build` + `_extract_secret_names`. `uses: ./...` reference triggers `"ci.local_action_unparsed"` (AC-22; not descended into).
     - **`_parse_gitlab_ci`**: `safe_yaml.load(".gitlab-ci.yml", max_bytes=10*1024*1024, max_depth=64)`. Substring matches via `_TEST_COMMAND_MARKERS` over `script:` and `before_script:`. Total parse-shutdown failure → `"ci.gitlab_ci_parse_error"`.
     - **`_parse_jenkinsfile`**: presence-only + `_JENKINS_SH_RE` line-by-line. `confidence: "low"`, emit `"ci.jenkinsfile_regex_only"`. **Never** Groovy-parse.
     - **`_parse_circleci_stub`**: presence-only; emit `"ci.circleci_presence_only"`; `confidence: "low"`.
     - **`_parse_azure_stub`**: presence-only; emit `"ci.azure_pipelines_presence_only"`; `confidence: "low"`.
   - Multi-provider triggers `"ci.multi_provider"` + `confidence: "low"` (AC-14).
5. **Confidence rules (encoded explicitly).**
   - `"high"` iff: single provider AND zero parse errors AND (no Jenkinsfile, no CircleCI/Azure stub) AND no multi-provider.
   - `"low"` iff: multi-provider OR Jenkinsfile-regex-only OR any per-file parse error OR CircleCI/Azure presence-only stub OR empty `.github/workflows/`.
   - **No `medium`** in Phase 1 (rejecting arch §"Edge cases" row 13's `medium` for `local-action` — see AC-22 + Notes).
6. **Failure-routing convention (CN-10 / S2-02 pattern).** All parser exceptions in Phase 1 are caught and converted to `slice["warnings"]` typed IDs; `ProbeOutput.errors` stays empty for `CIProbe`. Documented in Notes-for-implementer; this is a Phase-1 simplification, may evolve in Phase 2.
7. **Register** in `src/codegenie/probes/__init__.py` with one additive import line (AC-2).
8. **Wire the sub-schema** into the envelope via `$ref` composition (Phase 0 SchemaValidator already supports this; one envelope edit adds the optional reference under `probes.ci`).

## TDD plan — red / green / refactor

### Test helpers preamble (define inline at top of `test_ci.py`)

Mirrors the `test_node_build_system.py:67-94` idiom; **drops `pytest-asyncio`** in favor of explicit `asyncio.run` so the dependency surface stays bounded.

```python
# tests/unit/probes/test_ci.py
"""Pins: CIProbe records provider + workflow + image-build + secrets as facts;
multi-provider + Jenkins + presence-only-stubs downgrade confidence; secrets regex
is bounded against ReDoS; references_secrets is sorted+deduped.
Traces to: phase-arch-design.md §"Component design" #5; ADR-0004; ADR-0006;
ADR-0007; ADR-0010; production ADR-0005."""
from __future__ import annotations
import asyncio
import json
import re
import time
from pathlib import Path
import pytest

from codegenie.probes.base import ProbeContext, RepoSnapshot
from codegenie.probes.ci import CIProbe
from codegenie.catalogs import CI_PROVIDERS

_ADR_0007 = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


def _snapshot(root: Path) -> RepoSnapshot:
    return RepoSnapshot(
        root=root,
        git_commit=None,
        detected_languages={},  # CIProbe is applies_to_languages = ["*"]
        config={},
    )


def _ctx(root: Path) -> ProbeContext:
    return ProbeContext(
        cache_dir=root / ".cache",
        output_dir=root / ".out",
        workspace=root,
        logger=None,        # if the ABC requires a logger, mirror the sibling helper
        config={},
        parsed_manifest=None,
    )


def _run(root: Path) -> "ProbeOutput":
    return asyncio.run(CIProbe().run(_snapshot(root), _ctx(root)))


def _write_workflow(root: Path, body: str, name: str = "x.yml") -> None:
    wf = root / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / name).write_text(body)
```

### Red — write failing tests first

```python
# ----------------------------------------------------------------------
# T-1: registry membership across languages (AC-2).
# ----------------------------------------------------------------------
@pytest.mark.parametrize("langs", [
    frozenset(),
    frozenset({"go"}),
    frozenset({"javascript"}),
    frozenset({"python"}),
])
def test_registry_membership_language_agnostic(langs):
    from codegenie.probes import default_registry
    assert CIProbe in default_registry.all_probes()
    assert CIProbe in default_registry.for_task("*", langs)


# ----------------------------------------------------------------------
# T-2: probe contract attributes — verbatim list[str] match (AC-1).
# ----------------------------------------------------------------------
def test_probe_contract_attributes_match_arch():
    assert CIProbe.name == "ci"
    assert CIProbe.version == "1.0.0"
    assert CIProbe.layer == "A"
    assert CIProbe.tier == "base"
    assert CIProbe.applies_to_languages == ["*"]   # list, not tuple — frozen ABC
    assert CIProbe.applies_to_tasks == ["*"]
    assert CIProbe.requires == []
    assert CIProbe.timeout_seconds == 10
    assert CIProbe.declared_inputs == [
        ".github/workflows/*.yml",
        ".github/workflows/*.yaml",
        ".gitlab-ci.yml",
        ".circleci/config.yml",
        "Jenkinsfile",
        "azure-pipelines.yml",
        "src/codegenie/catalogs/ci_providers.yaml",
    ]


# ----------------------------------------------------------------------
# T-3: catalog precedence pinned at file boundary (AC-15).
# ----------------------------------------------------------------------
def test_ci_providers_catalog_order_locked():
    from codegenie.probes.ci import _PROVIDER_PRECEDENCE
    assert tuple(CI_PROVIDERS.keys()) == _PROVIDER_PRECEDENCE
    assert _PROVIDER_PRECEDENCE == (
        "github_actions", "gitlab_ci", "circleci", "jenkins", "azure_pipelines",
    )


# ----------------------------------------------------------------------
# T-4: image-build detection — parametrized over all three markers + negative (AC-4..AC-7).
# ----------------------------------------------------------------------
@pytest.mark.parametrize("step_yaml,expected_substr,builds", [
    ("- run: docker build -t app .", "docker build", True),
    ("- run: docker buildx build --platform linux/amd64 .", "docker buildx", True),
    ("- uses: docker/build-push-action@v5", "docker/build-push-action", True),
    ("- run: docker run hello-world", None, False),     # negative — uses Docker but doesn't build
])
def test_image_build_detection(tmp_path, step_yaml, expected_substr, builds):
    _write_workflow(tmp_path,
        f"jobs:\n  b:\n    runs-on: ubuntu-latest\n    steps:\n      {step_yaml}\n")
    s = _run(tmp_path).schema_slice
    assert s["builds_image"] is builds
    if expected_substr is None:
        assert s["image_build_command"] is None
    else:
        assert expected_substr in s["image_build_command"]


# ----------------------------------------------------------------------
# T-5: GitLab CI clean single-provider, high confidence (AC-8 + AC-13 negative).
# ----------------------------------------------------------------------
def test_gitlab_only_high_confidence(tmp_path):
    (tmp_path / ".gitlab-ci.yml").write_text("test:\n  script:\n    - npm test\n")
    out = _run(tmp_path)
    assert out.schema_slice["provider"] == "gitlab_ci"
    assert "npm test" in (out.schema_slice.get("unit_test_command") or "")
    assert out.confidence == "high"
    assert out.schema_slice["warnings"] == []


# ----------------------------------------------------------------------
# T-6: provider precedence — parametrized total-ordering (AC-14, AC-16).
# ----------------------------------------------------------------------
@pytest.mark.parametrize("present,provider,additional,expect_multi_warning", [
    ({".github/workflows/x.yml", ".gitlab-ci.yml", ".circleci/config.yml"},
        "github_actions", ["gitlab_ci", "circleci"], True),
    ({".gitlab-ci.yml", "Jenkinsfile"}, "gitlab_ci", ["jenkins"], True),
    ({".gitlab-ci.yml"}, "gitlab_ci", [], False),         # single — no warning
    ({"Jenkinsfile"}, "jenkins", [], False),
    ({".circleci/config.yml", ".gitlab-ci.yml"}, "gitlab_ci", ["circleci"], True),
])
def test_provider_precedence_follows_catalog_order(
    tmp_path, present, provider, additional, expect_multi_warning
):
    if ".github/workflows/x.yml" in present:
        _write_workflow(tmp_path, "jobs: {}\n", name="x.yml")
    if ".gitlab-ci.yml" in present:
        (tmp_path / ".gitlab-ci.yml").write_text("stages: [build]\n")
    if ".circleci/config.yml" in present:
        circ = tmp_path / ".circleci"; circ.mkdir()
        (circ / "config.yml").write_text("version: 2.1\n")
    if "Jenkinsfile" in present:
        (tmp_path / "Jenkinsfile").write_text("pipeline {}")
    if "azure-pipelines.yml" in present:
        (tmp_path / "azure-pipelines.yml").write_text("trigger: none\n")

    s = _run(tmp_path).schema_slice
    assert s["provider"] == provider
    assert s["additional_providers"] == additional   # catalog order, NOT alpha
    if expect_multi_warning:
        assert "ci.multi_provider" in s["warnings"]
    else:
        assert "ci.multi_provider" not in s["warnings"]


# ----------------------------------------------------------------------
# T-7: Jenkinsfile regex-only — bound + multi-quote handling (AC-9).
# ----------------------------------------------------------------------
@pytest.mark.parametrize("body,expect_in_unit", [
    ("pipeline { stages { stage('t') { steps { sh 'npm test' } } } }", "npm test"),
    ("pipeline { stages { stage('t') { steps { sh \"npm run build\" } } } }", "npm run build"),
])
def test_jenkinsfile_regex_extraction(tmp_path, body, expect_in_unit):
    (tmp_path / "Jenkinsfile").write_text(body)
    s = _run(tmp_path).schema_slice
    assert s["provider"] == "jenkins"
    assert expect_in_unit in (s.get("unit_test_command") or "")
    assert s["warnings"] == ["ci.jenkinsfile_regex_only"]
    assert _run(tmp_path).confidence == "low"


def test_jenkinsfile_no_sh_commands_still_low_confidence(tmp_path):
    (tmp_path / "Jenkinsfile").write_text("pipeline { agent any }")
    out = _run(tmp_path)
    assert "ci.jenkinsfile_regex_only" in out.schema_slice["warnings"]
    assert out.confidence == "low"


# ----------------------------------------------------------------------
# T-8: presence-only stubs (AC-10, AC-11).
# ----------------------------------------------------------------------
def test_circleci_presence_only_low_confidence(tmp_path):
    (tmp_path / ".circleci").mkdir()
    (tmp_path / ".circleci" / "config.yml").write_text("version: 2.1\n")
    s = _run(tmp_path).schema_slice
    assert s["provider"] == "circleci"
    assert "ci.circleci_presence_only" in s["warnings"]


def test_azure_pipelines_presence_only_low_confidence(tmp_path):
    (tmp_path / "azure-pipelines.yml").write_text("trigger: none\n")
    s = _run(tmp_path).schema_slice
    assert s["provider"] == "azure_pipelines"
    assert "ci.azure_pipelines_presence_only" in s["warnings"]


# ----------------------------------------------------------------------
# T-9: empty .github/workflows/ directory (AC-12).
# ----------------------------------------------------------------------
def test_empty_workflows_dir(tmp_path):
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    s = _run(tmp_path).schema_slice
    assert s["provider"] == "github_actions"
    assert s["workflow_files"] == []
    assert s["builds_image"] is False
    assert "ci.empty_workflows_dir" in s["warnings"]


# ----------------------------------------------------------------------
# T-10: no CI present at all — slice IS produced (AC-13).
# ----------------------------------------------------------------------
def test_no_ci_present_slice_still_emitted(tmp_path):
    (tmp_path / "README.md").write_text("# repo\n")
    out = _run(tmp_path)
    s = out.schema_slice
    assert s["provider"] is None
    assert s["additional_providers"] == []
    assert s["workflow_files"] == []
    assert s["builds_image"] is False
    assert s["references_secrets"] == []
    assert s["warnings"] == []
    assert out.confidence == "high"


# ----------------------------------------------------------------------
# T-11: secrets — sorted + deduped + literal-only + no env lookup (AC-18, AC-19).
# ----------------------------------------------------------------------
def test_secrets_sorted_deduped_literal_only(tmp_path):
    _write_workflow(tmp_path,
        "steps:\n  - run: echo ${{ secrets.B }} ${{ secrets.A }} ${{ secrets.A }}\n",
        name="a.yml")
    _write_workflow(tmp_path,
        "steps:\n  - run: echo ${{ secrets.C }}\n",
        name="b.yml")
    s = _run(tmp_path).schema_slice
    assert s["references_secrets"] == ["A", "B", "C"]


def test_secrets_regex_does_not_match_env_inputs_or_capitalized(tmp_path):
    _write_workflow(tmp_path,
        "steps:\n  - run: echo ${{ env.FOO }} ${{ inputs.BAR }} ${{ Secrets.X }} ${{ secrets.REAL }}\n")
    assert _run(tmp_path).schema_slice["references_secrets"] == ["REAL"]


def test_secrets_value_never_resolved(tmp_path, monkeypatch):
    """Sentinel: facts-not-judgments — probe must NOT call os.environ.get for any secret name."""
    looked_up: list[str] = []
    real_get = __import__("os").environ.get

    def spy(name, default=None):
        looked_up.append(name)
        return real_get(name, default)

    monkeypatch.setattr("os.environ.get", spy)
    _write_workflow(tmp_path,
        "steps:\n  - run: echo ${{ secrets.NPM_TOKEN }}\n")
    _run(tmp_path)
    assert "NPM_TOKEN" not in looked_up


# ----------------------------------------------------------------------
# T-12: secrets regex bound + ReDoS guard (AC-17).
# ----------------------------------------------------------------------
def test_secrets_regex_bounded_at_129_chars(tmp_path):
    long_name = "A" * 200
    _write_workflow(tmp_path,
        f"steps:\n  - run: echo ${{{{ secrets.{long_name} }}}}\n")
    captured = _run(tmp_path).schema_slice["references_secrets"]
    # Implementation may capture first 129 chars (1 leader + 128 tail) or skip entirely;
    # the load-bearing invariant is that the 200-char pathological identifier is NEVER captured intact.
    assert long_name not in captured
    for c in captured:
        assert len(c) <= 129


def test_secrets_regex_completes_under_one_second(tmp_path):
    """ReDoS guard — 5000 reps of unterminated `${{ secrets.A`."""
    hostile = "${{ secrets.A" * 5000
    _write_workflow(tmp_path,
        f"steps:\n  - run: |\n      {hostile}\n")
    t0 = time.monotonic()
    _run(tmp_path)
    assert time.monotonic() - t0 < 1.0


# ----------------------------------------------------------------------
# T-13: per-file workflow YAML parse failure — bare ID, file omitted (AC-21, CN-1).
# ----------------------------------------------------------------------
def test_malformed_workflow_skipped_gather_continues(tmp_path):
    _write_workflow(tmp_path, "jobs: {\n", name="bad.yml")            # malformed
    _write_workflow(tmp_path,
        "jobs:\n  b:\n    runs-on: ubuntu-latest\n    steps: []\n",
        name="good.yml")
    s = _run(tmp_path).schema_slice
    # bad.yml omitted; good.yml present
    assert s["workflow_files"] == ["good.yml"]
    # bare ID (no colon, no path) — see CN-1 resolution
    assert "ci.workflow_parse_error" in s["warnings"]
    # ADR-0007 pattern conformance for ALL warnings
    for w in s["warnings"]:
        assert _ADR_0007.match(w), f"violates ADR-0007: {w!r}"


# ----------------------------------------------------------------------
# T-14: local-action reference emits warning, doesn't descend (AC-22).
# ----------------------------------------------------------------------
def test_local_action_reference_warning(tmp_path):
    _write_workflow(tmp_path,
        "jobs:\n  b:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - uses: ./.github/actions/local-action\n")
    s = _run(tmp_path).schema_slice
    assert "ci.local_action_unparsed" in s["warnings"]


# ----------------------------------------------------------------------
# T-15: warning ID frozenset + import-time pattern assertion (AC-20).
# ----------------------------------------------------------------------
def test_warning_ids_match_adr_0007():
    from codegenie.probes import ci as ci_mod
    expected = {
        "ci.jenkinsfile_regex_only", "ci.multi_provider",
        "ci.workflow_parse_error", "ci.gitlab_ci_parse_error",
        "ci.local_action_unparsed", "ci.empty_workflows_dir",
        "ci.circleci_presence_only", "ci.azure_pipelines_presence_only",
    }
    assert ci_mod._WARNING_IDS == expected
    for w in ci_mod._WARNING_IDS:
        assert _ADR_0007.match(w)


# ----------------------------------------------------------------------
# T-16: dispatch registry covers every catalog parser arm (AC-24).
# ----------------------------------------------------------------------
def test_ci_parsers_dispatch_registry_complete():
    from typing import get_args
    from codegenie.probes.ci import _CI_PARSERS, _PARSER_LITERAL
    assert set(_CI_PARSERS.keys()) == set(get_args(_PARSER_LITERAL))


# ----------------------------------------------------------------------
# T-17: image-build markers tuple is the file-boundary seam (AC-25).
# ----------------------------------------------------------------------
def test_image_build_markers_table_locked():
    from codegenie.probes.ci import _IMAGE_BUILD_MARKERS
    assert _IMAGE_BUILD_MARKERS == (
        ("docker build", "run"),
        ("docker buildx", "run"),
        ("docker/build-push-action", "uses"),
    )


# ----------------------------------------------------------------------
# T-18: two-run determinism (AC-23).
# ----------------------------------------------------------------------
def test_two_runs_byte_equal(tmp_path):
    _write_workflow(tmp_path,
        "jobs:\n  b:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - run: docker build .\n"
        "      - run: echo ${{ secrets.B }} ${{ secrets.A }}\n")
    (tmp_path / ".gitlab-ci.yml").write_text("script: ['npm test']\n")
    a = _run(tmp_path).schema_slice
    b = _run(tmp_path).schema_slice
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ----------------------------------------------------------------------
# T-19: workflow_files lexicographically sorted (AC-23).
# ----------------------------------------------------------------------
def test_workflow_files_sorted_lex(tmp_path):
    for n in ["zeta.yml", "alpha.yml", "mike.yml"]:
        _write_workflow(tmp_path, "jobs: {}\n", name=n)
    s = _run(tmp_path).schema_slice
    assert s["workflow_files"] == ["alpha.yml", "mike.yml", "zeta.yml"]


# ----------------------------------------------------------------------
# T-20: pure-helper unit tests (AC-26).
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("", []),
    ("${{ secrets.A }}", ["A"]),
    ("${{ secrets.A }} ${{ secrets.B }} ${{ secrets.A }}", ["A", "B"]),
    ("${{ env.FOO }}", []),
    ("${{ Secrets.X }}", []),                                   # case-sensitive
])
def test_extract_secret_names_pure(text, expected):
    from codegenie.probes.ci import _extract_secret_names
    assert _extract_secret_names(text) == expected


def test_select_provider_pure_first_match_wins():
    from codegenie.probes.ci import _select_provider
    p, rest = _select_provider(
        ["circleci", "github_actions"],
        ("github_actions", "gitlab_ci", "circleci", "jenkins", "azure_pipelines"),
    )
    # Implementation pre-sorts `present` by precedence before calling, so order is
    # ["github_actions", "circleci"] when entering — first wins, rest preserves precedence.
    assert p == "github_actions"
    assert rest == ["circleci"]


# ----------------------------------------------------------------------
# T-21: sub-schema rejects unknown field — JSON Pointer assertion (AC-3, TQ-9).
# ----------------------------------------------------------------------
def test_subschema_rejects_unknown_field_at_root():
    from codegenie.errors import SchemaValidationError
    from codegenie.coordinator.validator import SchemaValidator   # adjust import to actual chokepoint
    envelope = _minimal_envelope_with_ci(rogue_root=True)
    with pytest.raises(SchemaValidationError) as ei:
        SchemaValidator().validate(envelope)
    assert "/probes/ci" in str(ei.value)
    assert "rogue_field" in str(ei.value)


def test_subschema_additional_properties_false_at_every_object():
    """Walks the schema; every `type: object` node must declare additionalProperties: false."""
    import json, pathlib
    schema = json.loads(
        pathlib.Path("src/codegenie/schema/probes/ci.schema.json").read_text()
    )
    def walk(node, path):
        if isinstance(node, dict) and node.get("type") == "object":
            assert node.get("additionalProperties") is False, \
                f"missing additionalProperties: false at {path}"
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}/{i}")
    walk(schema, "")


# ----------------------------------------------------------------------
# T-22: registry filter — non-Node repo still validates (AC-3 + ADR-0010).
# ----------------------------------------------------------------------
def test_envelope_optional_at_probes_level():
    """Envelope's properties.probes.required does NOT list `ci`."""
    import json, pathlib
    env = json.loads(
        pathlib.Path("src/codegenie/schema/repo_context.schema.json").read_text()
    )
    required = env.get("properties", {}).get("probes", {}).get("required", [])
    assert "ci" not in required
```

Run `pytest tests/unit/probes/test_ci.py -q`. Expect every test to fail (the probe + schema don't exist yet).

### Green — make it pass

1. Write `src/codegenie/schema/probes/ci.schema.json` mirroring `CISlice` (every nested object declares `additionalProperties: false`).
2. Write `src/codegenie/probes/ci.py` per **Implementation outline** — module-level constants first (Open/Closed seams), pure helpers next, `run()` body last (orchestration only).
3. Compose the sub-schema into the envelope under `probes.ci` (optional reference).
4. Register in `src/codegenie/probes/__init__.py` with one additive import line.
5. Run tests; iterate until green.

### Refactor — clean up

- Verify the five pure helpers (`_select_provider`, `_extract_run_strings`, `_extract_uses_strings`, `_extract_secret_names`, `_detect_image_build`) are independently importable and unit-tested (AC-26 + T-20).
- Use `pytest.mark.parametrize` to encode invariants over multiple inputs (the `test_provider_precedence_follows_catalog_order` test in this file is the local reference; `test_lockfile_precedence_total_ordering` in `test_node_build_system.py` is the sibling reference). **One invariant per test, parametrized over all inputs that exercise it.** Do NOT bundle two distinct invariants into one parametrized test. (This corrects the original story's "ban parametrize" prescription — see Validation notes TQ-15.)
- Confirm import-time `_WARNING_IDS` ADR-0007 assertion exists and fires on a deliberate typo (manual check; do not commit the typo).
- Confirm `_PROVIDER_PRECEDENCE` anchor assertion exists and would fire if `ci_providers.yaml` were reordered (T-3 catches this).
- Run `ruff format` and `ruff check`; run `mypy --strict src/codegenie/probes/ci.py`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/ci.py` | New — `CIProbe` implementation |
| `src/codegenie/schema/probes/ci.schema.json` | New — `additionalProperties: false` strict slice schema |
| `src/codegenie/probes/__init__.py` | Edit — one additive import line registering `CIProbe` |
| `src/codegenie/schema/repo_context.schema.json` | Edit — `$ref` compose `ci.schema.json` under `probes.ci` (optional) |
| `tests/unit/probes/test_ci.py` | New — unit tests covering all branches |
| `tests/fixtures/ci_fixtures/` (or inline in `tmp_path`) | New if needed — minimal GHA + GitLab + Jenkins fixtures |

## Out of scope

- **Reusable workflow descent** — `uses: ./.github/actions/local-action` recorded as a path only with `warnings: ["ci.local_action_unparsed"]` per `phase-arch-design.md §"Edge cases"` row 13. Deferred to Phase 2.
- **Real CI API calls** — no `gh api` / GitLab API / Jenkins API invocations. Phase 1 is filesystem-only.
- **CircleCI / Azure Pipelines deep parsing** — presence-only stubs in Phase 1; deepening when a consumer demands.
- **Coverage gate enforcement** — declared by S4-04, enforced by S6-02.
- **Adversarial fixture for malformed/oversized workflow YAML** — the unit test exercises the malformed path here; the dedicated adversarial fixture (oversized YAML, billion-laughs) lives in S5-01 / S5-03 as cross-cutting.
- **`additional_providers` ordering policy** — derived from `ci_providers.yaml` declaration order; if a future consumer needs a stable alphabetical sort, that's a Phase 2 concern.

## Notes for the implementer

- The `${{ secrets.X }}` regex is the one regex in this probe that runs on attacker-controllable bytes. **Use the bounded form pinned by AC-17**: `r"\$\{\{\s*secrets\.([A-Za-z_][A-Za-z0-9_]{0,128})\s*\}\}"`. No `*`, no `+`, no nested groups — anchor the upper bound on the identifier length. T-12 enforces this (the original Implementation outline shipped an unbounded variant; the story now reconciles to the bounded form per Rule 7 — surface conflicts).
- `references_secrets` is **literal-names-only**. Never call `os.environ.get(name)`; never call `gh secret list`; never resolve. The arch and ADRs are explicit on this — `production/design.md §2.4` (facts not judgments) and production ADR-0005 (no LLM in gather). T-11 installs an `os.environ.get` sentinel spy to enforce this. If a future PR proposes "but it would be useful to know if the secret is set…" — that's a Phase 4+ concern, not Phase 1.
- **Probe `name` vs catalog `provider` name — two namespaces.** `Probe.name = "ci"` (probe identity in the registry, becomes envelope key `probes.ci`). The slice's `provider` field is the catalog entry's `name` (e.g., `"github_actions"`). Don't conflate the two when reading or writing tests.
- The catalog `ci_providers.yaml` is in `declared_inputs`. This means the same ADR-0006 invalidation pattern as `node_manifest`: editing the catalog invalidates `ci`'s cache entries only. The cache-invalidation-scope test (S3-06 extended; or a new test if scope creep allows) can verify this, but it is not load-bearing for this story.
- **Multi-provider precedence is pinned at TWO sites.** The catalog YAML lists entries in precedence order; AC-15 mirrors that order in `_PROVIDER_PRECEDENCE` at the top of `ci.py` and asserts equality at import time. This is deliberate redundancy: a reshuffled catalog without a corresponding `ci.py` edit fails at module import (Rule 12 — fail loud), not at the first multi-provider repo six weeks later.
- The 200-workflow stress case (arch §"Edge cases" row 14) is not load-bearing for this story; no per-file cap is needed beyond the existing 10 MB per-file cap. If `workflow_files: list[str]` grows large, downstream consumers handle it — `len()` is fine.
- **Confidence rules (encoded explicitly per Implementation outline §5).** `"high"` iff: single provider AND zero parse errors AND no Jenkinsfile/CircleCI/Azure stub. `"low"` iff: multi-provider OR Jenkins-regex-only OR per-file parse error OR presence-only stub OR empty workflows dir. **No `medium` in Phase 1** — arch §"Edge cases" row 13 prescribes `medium` for `local-action`, but the resolution is to keep confidence at the surrounding workflow's level (typically `"high"` for an otherwise-clean repo) and rely on the `"ci.local_action_unparsed"` warning to surface the limitation. Re-evaluate in Phase 2 when reusable-workflow descent is in scope.
- A grep for `import requests`, `import httpx`, `import urllib3`, `import socket` in this file should return empty. The `import-linter` rule (Phase 0) bans them; the probe must work from local filesystem only.
- **Failure routing.** All parser exceptions in Phase 1 → `slice["warnings"]` typed IDs; `ProbeOutput.errors` stays empty for `CIProbe`. This is a Phase-1 simplification matching the arch's "per-file warning, gather continues" semantics. May evolve in Phase 2 if a coordinator-level escalation path is needed.
- **Arch-doc drift to flag in PR.** `phase-arch-design.md §"Component design" #5` line 540 prescribes `warnings: ["ci.workflow_parse_error:<path>"]` (colon-suffixed). This violates ADR-0007's `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` pattern. **This story emits the bare ID** (AC-21); the offending workflow path lives in `raw/ci.json`. Flag the arch-doc drift in your PR body so a follow-up patch fixes the arch doc.
- If you find yourself wanting to add a sixth provider (e.g., Buildkite, Drone CI), the **load-bearing extension point is the catalog YAML**. Adding a parser arm to the `Literal` union + a `_CI_PARSERS` entry + a new `_parse_<kind>` function is the per-shape extension; the catalog YAML edit is the data extension. AC-24's import-time assertion (`set(_CI_PARSERS.keys()) == set(get_args(_PARSER_LITERAL))`) catches a catalog `Literal` arm without a parser.

### Patterns DELIBERATELY deferred (premature-abstraction guard — Rule 2)

- **`CIProviderParser` ABC + plugin-discovery registry.** Five parsers in one file is fine; an ABC adds friction without payoff at this scale. Lift in Phase 4+ when external CI plugins land.
- **`_ParseOutcome` sum type** (`Parsed[T] | ParseError | FileNotPresent | CapExceeded`). Five callsites for parse outcomes meets the rule-of-three, but lift only if three-of-five parsers share the exact same try/except/warn shape after the green pass. Defer if outcomes diverge per parser.
- **`CISlice(TypedDict)`** at module scope. Building as `dict[str, Any]` passes schema validation. Lift to `TypedDict` if the slice grows past 12 fields or if mypy starts missing typo'd keys.
- **Shared `probes/_confidence.py` kernel** (`_demote`, `_CONFIDENCE_RANK`). Rule of three is met now (`node_build_system` + `ci` + soon `deployment` + `test_inventory` at S4-02/S4-03). Copy verbatim from `node_build_system.py` here; extract to a shared module at S4-03 once the fourth copy lands. (Rule 3 — surgical changes; do not preemptively extract.)
- **Shared `probes/_warning_ids.py` helper** for the import-time ADR-0007 pattern check. The assertion is 3 lines; copy verbatim from `node_build_system.py:253-254`. Extract only when ≥ 4 probes carry the same idiom.
- **YAML catalog for `_TEST_COMMAND_MARKERS` / `_IMAGE_BUILD_MARKERS`.** Module-level tuples now; lift to a YAML catalog at Phase 2 if a third probe needs the same lists.
- **`SecretName` / `WorkflowPath` `NewType`s.** Premature; bare `str` is fine in Phase 1. Phase 4+ if cross-probe consumers need to distinguish them.
