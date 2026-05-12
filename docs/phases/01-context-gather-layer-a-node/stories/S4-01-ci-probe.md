# Story S4-01 — `CIProbe` + sub-schema

**Step:** Step 4 — Ship `CIProbe`, `DeploymentProbe`, and `TestInventoryProbe`
**Status:** Ready
**Effort:** M
**Depends on:** S1-03 (`safe_yaml`), S1-05 (catalogs — `ci_providers.yaml`)
**ADRs honored:** ADR-0004 (`additionalProperties: false`), ADR-0007 (warning-ID pattern), ADR-0009 (no new C-extension parser deps), ADR-0010 (Layer A slices optional at envelope)

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

- [ ] `src/codegenie/probes/ci.py` exists, defines `class CIProbe(Probe)`, sets `name = "ci"`, `layer = "A"`, `tier = "base"`, `applies_to_languages = ["*"]`, `applies_to_tasks = ["*"]`, `requires = []`, `timeout_seconds = 10`, `version: str` (e.g., `"1.0.0"`), and `declared_inputs` per `phase-arch-design.md §"Component design" #5` **including `"src/codegenie/catalogs/ci_providers.yaml"`** so a catalog edit invalidates `ci` cache entries (ADR-0006 pattern).
- [ ] `src/codegenie/schema/probes/ci.schema.json` exists, Draft 2020-12, declares `additionalProperties: false` at its root and at every nested object, declares the slice as **optional** at the envelope's `probes.*` level (i.e., the envelope's `properties.probes.required` array does not reference `ci`), and validates the shapes in `phase-arch-design.md §"Data model" CISlice`. Every `warnings[].pattern` matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`.
- [ ] `src/codegenie/probes/__init__.py` adds one explicit import line registering `CIProbe` (additive — no rewrite of the registry list).
- [ ] Red test exists and was committed failing; green tests pass: `tests/unit/probes/test_ci.py` covers (a) single GitHub Actions workflow with image-build detection (`docker build`, `docker buildx`, `docker/build-push-action` — each as a separate test case), (b) GitLab CI parsing, (c) Jenkinsfile bounded-regex extraction with `confidence: low` + `warnings: ["ci.jenkinsfile_regex_only"]`, (d) multi-provider repo → `provider` = highest-precedence (deterministic from `ci_providers.yaml` order), `additional_providers` = rest, `confidence: low`, `warnings: ["ci.multi_provider"]`, (e) `${{ secrets.FOO }}` → `references_secrets: ["FOO"]` literal capture only (no resolution), (f) workflow YAML parse error → that workflow skipped, `warnings: ["ci.workflow_parse_error"]`, gather still produces a slice.
- [ ] `tests/unit/probes/test_ci_schema.py` (or a section in `test_ci.py`) ships an explicit `additionalProperties: false` rejection test: a synthetic envelope with `probes.ci.unknown_field: 1` fails `SchemaValidator` with a `SchemaValidationError` whose JSON Pointer references the unknown field.
- [ ] Definition-of-done items hold: `ruff check`, `ruff format --check`, `mypy --strict` on `src/codegenie/probes/ci.py` and `src/codegenie/schema/probes/ci.schema.json` (via `jsonschema`'s self-validation), `pytest tests/unit/probes/test_ci.py -q` all pass. Per-probe local coverage reported in the PR body (the S6-02 ratchet cannot recover if `ci.py` lands below 85/75).
- [ ] The PR body explicitly notes the open-question outcomes: reusable-workflow `uses:` references captured as paths only (open question #4) — not descended into.

## Implementation outline

1. **Define `CISlice` shape in `ci.schema.json` first** (write the schema before the code). Mirror `phase-arch-design.md §"Data model" CISlice`. `additionalProperties: false` at root. Each `WarningId` constrained by the ADR-0007 pattern.
2. **Implement `CIProbe.run(snapshot, ctx)`:**
   - Iterate `CI_PROVIDERS` from `catalogs`. For each entry, check existence of `marker_paths` under `snapshot.root` (use `Path.is_file()` / `Path.is_dir()` — no walks). First match → `provider`; remaining matches accumulate into `additional_providers`.
   - **GitHub Actions:** glob `.github/workflows/*.yml` and `*.yaml`. For each file, call `safe_yaml.load(path, max_bytes=10*1024*1024, max_depth=64)`. Catch `SizeCapExceeded`/`DepthCapExceeded`/`MalformedYAMLError` per file → warning, continue with the next workflow. Extract: top-level `jobs` keys, each job's `steps[].run` strings, `steps[].uses` strings (recorded by path only). Image-build detection: substring match against the union of all `run:` strings for `"docker build"`, `"docker buildx"`, `"docker/build-push-action"` (the last as a `uses:` match). Secrets: regex `\$\{\{\s*secrets\.([A-Za-z_][A-Za-z0-9_]*)\s*\}\}` (anchored, single capture, no backtracking surface). Test/lint command detection: substring match against canonical script names per `localv2.md §5.1 A4`.
   - **GitLab CI:** `safe_yaml.load(".gitlab-ci.yml", max_bytes=10*1024*1024, max_depth=64)`. Same substring matches over `script:`, `before_script:`.
   - **Jenkinsfile:** presence-only + a single bounded regex `r"sh\s+['\"]([^'\"\n]{1,500})['\"]"` line-by-line. `confidence: low`. **Never** Groovy-parse — the regex is the contract.
   - **CircleCI / Azure Pipelines:** presence-only stub fields; no deep parse.
3. **Failure handling:** every parser exception is caught into a typed warning ID (`ci.workflow_parse_error`, `ci.gitlab_ci_parse_error`, `ci.jenkinsfile_regex_only`, `ci.local_action_unparsed`, `ci.multi_provider`). The `WarningId` pattern is enforced by the sub-schema; the probe just emits strings matching the regex.
4. **Register** in `src/codegenie/probes/__init__.py` with one additive import line.
5. **Wire the sub-schema** into the envelope via `$ref` composition (Phase 0 SchemaValidator already supports this; one envelope edit adds the optional reference under `probes.ci`).

## TDD plan — red / green / refactor

### Red — write failing tests first

Test file: `tests/unit/probes/test_ci.py`. Create fixtures inline via `tmp_path`.

```python
# tests/unit/probes/test_ci.py
"""Pins: CIProbe records provider + workflow + image-build + secrets as facts;
multi-provider downgrades confidence; Jenkinsfile is regex-only with confidence: low.
Traces to: phase-arch-design.md §Component design #5; ADR-0004; ADR-0007."""
import pytest
from pathlib import Path
from codegenie.probes.ci import CIProbe

@pytest.mark.asyncio
async def test_github_actions_image_build_detected(tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "build.yml").write_text(
        "name: build\non: push\n"
        "jobs:\n  b:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: docker buildx build .\n"
    )
    probe = CIProbe()
    out = await probe.run(_snapshot(tmp_path), _ctx(tmp_path))
    assert out.schema_slice["provider"] == "github_actions"
    assert out.schema_slice["builds_image"] is True
    assert "docker buildx" in out.schema_slice["image_build_command"]
    assert out.confidence == "high"

@pytest.mark.asyncio
async def test_multi_provider_low_confidence(tmp_path):
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "x.yml").write_text("name: x\non: push\njobs: {}\n")
    (tmp_path / ".gitlab-ci.yml").write_text("stages: [build]\n")
    out = await CIProbe().run(_snapshot(tmp_path), _ctx(tmp_path))
    assert out.schema_slice["provider"] == "github_actions"  # precedence
    assert "gitlab_ci" in out.schema_slice["additional_providers"]
    assert out.confidence == "low"
    assert any(w == "ci.multi_provider" for w in out.schema_slice["warnings"])

@pytest.mark.asyncio
async def test_secrets_captured_as_literal_names(tmp_path):
    wf = tmp_path / ".github" / "workflows"; wf.mkdir(parents=True)
    (wf / "x.yml").write_text(
        "jobs:\n  b:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: echo ${{ secrets.NPM_TOKEN }}\n"
    )
    out = await CIProbe().run(_snapshot(tmp_path), _ctx(tmp_path))
    assert out.schema_slice["references_secrets"] == ["NPM_TOKEN"]
    # facts, not judgments: the literal name is captured; the value is not resolved.

@pytest.mark.asyncio
async def test_jenkinsfile_regex_only_low_confidence(tmp_path):
    (tmp_path / "Jenkinsfile").write_text("pipeline { stages { stage('t') { steps { sh 'npm test' } } } }")
    out = await CIProbe().run(_snapshot(tmp_path), _ctx(tmp_path))
    assert out.schema_slice["provider"] == "jenkins"
    assert "npm test" in (out.schema_slice["unit_test_command"] or "")
    assert out.confidence == "low"
    assert "ci.jenkinsfile_regex_only" in out.schema_slice["warnings"]

@pytest.mark.asyncio
async def test_malformed_workflow_skipped_gather_continues(tmp_path):
    wf = tmp_path / ".github" / "workflows"; wf.mkdir(parents=True)
    (wf / "bad.yml").write_text("jobs: {\n")  # malformed
    (wf / "good.yml").write_text("jobs:\n  b:\n    runs-on: ubuntu-latest\n    steps: []\n")
    out = await CIProbe().run(_snapshot(tmp_path), _ctx(tmp_path))
    assert "bad.yml" in str(out.schema_slice["warnings"])
    assert any(w.startswith("ci.workflow_parse_error") for w in out.schema_slice["warnings"])

def test_subschema_rejects_unknown_field():
    from codegenie.coordinator.schema_validator import SchemaValidator  # or similar
    envelope = {"probes": {"ci": {"provider": "github_actions", "unknown_field": 1}}}
    with pytest.raises(Exception) as ei:
        SchemaValidator().validate(envelope)
    assert "unknown_field" in str(ei.value)
```

Run `pytest tests/unit/probes/test_ci.py -q`. Expect all tests fail (the probe and schema don't exist yet).

### Green — make it pass

1. Write `src/codegenie/schema/probes/ci.schema.json` mirroring `CISlice`.
2. Write `src/codegenie/probes/ci.py` implementing the steps in **Implementation outline**.
3. Register in `src/codegenie/probes/__init__.py`.
4. Compose the sub-schema into the envelope under `probes.ci` (optional reference).
5. Run tests; iterate until green. The `_snapshot(...)` and `_ctx(...)` helpers should reuse the test harness conventions from Phase 0's `test_language_detection.py`.

### Refactor — clean up

- Extract the GitHub Actions parsing into a private helper `_parse_github_actions(workflow_files: list[Path]) -> _GHAResult` if the body grows past ~30 lines (Rule 2 — Simplicity First).
- Move the `${{ secrets.* }}` regex to a module-level constant; document it inline with a comment pointing at `ci.references_secrets` in the schema.
- Confirm no `pytest.mark.parametrize` smuggles two invariants into one test — adversarial-style discipline applies: one assertion target per test.
- Run `ruff format` and `ruff check`.

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

- The `${{ secrets.X }}` regex is the one regex in this probe that runs on attacker-controllable bytes. Make it bounded: `r"\$\{\{\s*secrets\.([A-Za-z_][A-Za-z0-9_]{0,128})\s*\}\}"`. No `*`, no `+`, no nested groups — anchor the upper bound on the identifier length. Phase 1 has no adversarial test specifically for this regex; if you sense it's not bounded enough, file a Phase 2 follow-up and tighten now.
- `references_secrets` is **literal-names-only**. Never call `os.environ.get(name)`; never call `gh secret list`; never resolve. The arch and ADRs are explicit on this — `production/design.md §2.4` (facts not judgments) and ADR-0007 (warning IDs not prose). If a future PR proposes "but it would be useful to know if the secret is set…" — that's a Phase 4+ concern, not Phase 1.
- The catalog `ci_providers.yaml` is in `declared_inputs`. This means the same ADR-0006 invalidation pattern as `node_manifest`: editing the catalog invalidates `ci`'s cache entries only. The cache-invalidation-scope test (S3-06 extended; or a new test if scope creep allows) can verify this, but it is not load-bearing for this story.
- For the multi-provider precedence, document the deterministic order **in `ci_providers.yaml`** (entries appear in precedence order), not in `ci.py`. The probe walks the catalog in iteration order. This keeps "what does multi-provider precedence mean?" answerable by reading one YAML file.
- The 200-workflow stress case (edge case #14) is not load-bearing for this story; no per-file cap is needed beyond the existing 10 MB per-file cap. If `workflow_files: list[str]` grows large, downstream consumers handle it — `len()` is fine.
- Per `phase-arch-design.md §"Component design" #5`, `confidence` is `high` for clean single-provider GitHub Actions or GitLab CI; `low` for Jenkinsfile, for multi-provider, for any parse error. Encode this explicitly — do not let confidence drift.
- A grep for `import requests`, `import httpx`, `import urllib3`, `import socket` in this file should return empty. The `import-linter` rule (Phase 0) bans them; the probe must work from local filesystem only.
- If you find yourself wanting to add a sixth provider (e.g., Buildkite, Drone CI), add it as a `ci_providers.yaml` entry, not as code. The catalog is the extension point (Rule 2 + extension-by-addition).
