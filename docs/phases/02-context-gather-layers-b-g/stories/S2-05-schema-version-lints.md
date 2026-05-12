# Story S2-05 — Schema-version CI lints — skills + catalogs

**Step:** Step 2 — Plant skills loader, catalog expansion, schema-evolution policy, and conventions parity lint
**Status:** Ready
**Effort:** S
**Depends on:** S2-01 (`SkillsLoader` + `skill.schema.json` declare `schema_version: ["v1"]`), S2-02 (conventions `_schema.json` + `node.yaml` declare `schema_version: "v1"`), S2-03 (`shell_replacements/_schema.json`, `semgrep_rule_packs.yaml` declare `schema_version: "v1"`)
**ADRs honored:** Gap 2 (versioning of skills frontmatter and conventions YAML) — the policy this lint enforces; ADR-0008 (the parity-lint CI-gating discipline this lint composes onto)

## Context

Gap 2 of `phase-arch-design.md` identifies that catalogs and skill frontmatter need an explicit `schema_version` field per artifact, plus a CI lint asserting **every** Phase-2 artifact declares the field at the value the SCHEMA-EVOLUTION-POLICY (S2-07) requires. Without the lint, a future addition can silently omit `schema_version` and Phase 2's evolution discipline rots away. This story plants two parallel lints — one for SKILL.md frontmatter, one for catalog YAML — and wires them into the same CI job that runs S2-04's conventions-parity lint (the `conventions_catalog_parity` job; the name composes all three Phase-2 lints).

Both lints follow ADR-0008's CI-gating-not-advisory posture: synthetic mismatch fixtures verify each lint actually fails red.

## References — where to look

- **Architecture:** `../phase-arch-design.md §"Gap analysis & improvements" §Gap 2` — the gap statement, the proposed lint, and the load-bearing rationale ("Layer C+G surface area" forces this gap in Phase 2).
- **Architecture:** `../phase-arch-design.md §"Component design" #3` (Skills loader — frontmatter validated against `skill.schema.json` with `schema_version` literal `"v1"`).
- **Architecture:** `../phase-arch-design.md §"Component design" #4` (conventions catalog — `schema_version: "v1"` at root).
- **Phase ADRs:** `../ADRs/0008-conventions-catalog-closed-enum-ci-lint.md` — establishes the CI-gating pattern; this lint composes on the same job.
- **Source design:** `../final-design.md` Synthesis ledger — Gap 2 resolution row.
- **Existing code:** `scripts/check_conventions_catalog_parity.py` (from S2-04) — reuse the lint-script shape and exit-code discipline. `src/codegenie/skills/schema/skill.schema.json` (from S2-01). `src/codegenie/catalogs/conventions/_schema.json` (from S2-02).

## Goal

Land `scripts/check_skill_schema_versions.py` and `scripts/check_conventions_schema_versions.py` wired into the `conventions_catalog_parity` CI job such that every SKILL.md under the pinned skill roots and every catalog YAML/JSON under `src/codegenie/catalogs/` declares `schema_version: "v1"` at root — with synthetic mismatch fixtures verifying each lint goes red on omission or wrong value.

## Acceptance criteria

- [ ] `scripts/check_skill_schema_versions.py` walks all SKILL.md files under the project's pinned skill roots (`src/codegenie/skills/fixtures/` for Phase 2 dev fixtures + any other configured roots — read from a fixed list at the top of the script or from `pyproject.toml`'s `[tool.codegenie]` section). For each file, extracts the YAML frontmatter window, parses it via `safe_yaml.load`, and asserts `frontmatter["schema_version"] == "v1"`. Missing field or wrong value → exit 1 with the offending file path and what was found.
- [ ] `scripts/check_conventions_schema_versions.py` walks all `*.yaml` (and `*.yml`) files under `src/codegenie/catalogs/` recursively, plus all `*.json` schema files under `src/codegenie/catalogs/`. For each YAML, parse root; assert `schema_version == "v1"`. For each `_schema.json`, parse root; assert `properties.schema_version.enum == ["v1"]` (the schema's *declaration*, not a value). Missing or wrong → exit 1.
- [ ] Both scripts exit 0 when all files conform; exit 1 with stderr-listed offenders when any don't.
- [ ] Synthetic mismatch fixtures land under `tests/conformance/fixtures/missing_schema_version/` (a SKILL.md missing the field) and `tests/conformance/fixtures/wrong_schema_version/` (a catalog YAML with `schema_version: "v0"`). Each fixture has its own test that invokes the lint against that fixture and asserts exit code 1.
- [ ] `tests/conformance/test_schema_version_lints.py` covers happy path (real files conform) + the two synthetic mismatches.
- [ ] CI wiring: both scripts run as additional steps in the existing `conventions_catalog_parity` CI job (the same one S2-04 created). All three lints compose into one job, naming preserved.
- [ ] Each lint accepts a `--roots PATH [PATH ...]` flag so the fixture tests can point the lint at a synthetic directory.
- [ ] TDD red landed first: `tests/conformance/test_schema_version_lints.py` initially fails.

## Implementation outline

1. Create `scripts/check_skill_schema_versions.py`:
   - Default roots: `[REPO_ROOT / "src/codegenie/skills/fixtures"]` (extend if other roots become canonical later).
   - For each `SKILL.md`, extract the frontmatter window using the same byte-offset routine as `src/codegenie/skills/loader.py` (or import the helper if S2-01 exposed `_extract_frontmatter_window` — preferred to avoid duplication).
   - Parse frontmatter; assert `schema_version == "v1"`.
   - On any failure: collect offenders into a list; print structured report to stderr; exit 1.
2. Create `scripts/check_conventions_schema_versions.py`:
   - Walk `src/codegenie/catalogs/` for `*.yaml`/`*.yml` (skip files starting with `_` — those are schemas, handled separately).
   - For each catalog YAML, parse via `safe_yaml.load`; assert root `schema_version == "v1"`.
   - For each `_schema.json` (or `*.schema.json`), parse via `json.load`; assert `properties.schema_version.enum == ["v1"]`.
   - Reporting and exit-code discipline match the conventions parity lint.
3. Both scripts: `--roots PATH [PATH ...]` for tests; `--quiet` flag (optional; suppress stdout on success).
4. Create `tests/conformance/test_schema_version_lints.py` covering the three cases per script (real files OK, missing field fails, wrong value fails).
5. Create synthetic mismatch fixtures under `tests/conformance/fixtures/{missing_schema_version_skill, wrong_schema_version_catalog}/`.
6. CI wiring: extend the workflow file from S2-04 — add two more `python scripts/check_...py` steps to the same `conventions_catalog_parity` job.
7. Update `docs/phases/02-context-gather-layers-b-g/stories/README.md`'s reference to "conventions_catalog_parity CI job composes all three Phase-2 lints" — the name is preserved; this story makes the composition real.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/conformance/test_schema_version_lints.py`

```python
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_LINT = REPO_ROOT / "scripts" / "check_skill_schema_versions.py"
CATALOG_LINT = REPO_ROOT / "scripts" / "check_conventions_schema_versions.py"

def test_real_skills_have_schema_version() -> None:
    result = subprocess.run([sys.executable, str(SKILL_LINT)], capture_output=True)
    assert result.returncode == 0, result.stderr.decode()

def test_real_catalogs_have_schema_version() -> None:
    result = subprocess.run([sys.executable, str(CATALOG_LINT)], capture_output=True)
    assert result.returncode == 0, result.stderr.decode()

def test_skill_without_schema_version_fails(tmp_path: Path) -> None:
    fixture = REPO_ROOT / "tests/conformance/fixtures/missing_schema_version_skill"
    result = subprocess.run(
        [sys.executable, str(SKILL_LINT), "--roots", str(fixture)],
        capture_output=True,
    )
    assert result.returncode == 1
    assert b"schema_version" in result.stderr

def test_catalog_with_wrong_schema_version_fails(tmp_path: Path) -> None:
    fixture = REPO_ROOT / "tests/conformance/fixtures/wrong_schema_version_catalog"
    result = subprocess.run(
        [sys.executable, str(CATALOG_LINT), "--roots", str(fixture)],
        capture_output=True,
    )
    assert result.returncode == 1
    assert b"v0" in result.stderr or b"schema_version" in result.stderr
```

Run; confirm red (scripts and fixtures don't yet exist); commit; then Green.

### Green — make it pass

Smallest impl: two scripts (~40–60 LOC each), two synthetic fixtures, one test file. Reuse `safe_yaml.load` and `_extract_frontmatter_window` from S2-01 — do not re-implement.

### Refactor — clean up

- Extract a common helper module `scripts/_phase2_lint_shared.py` containing `discover_repo_root() -> Path`, `report_offenders(offenders: list[tuple[Path, str]]) -> None`, and the `--roots` argparser setup. Both scripts + S2-04's lint import from it.
- Add `# DO NOT USE — synthetic mismatch fixture` headers to fixture files.
- Brief module docstring at the top of each script naming Gap 2 + this story + the policy doc S2-07 lands.

## Files to touch

| Path | Why |
|---|---|
| `scripts/check_skill_schema_versions.py` | The skills-frontmatter lint. |
| `scripts/check_conventions_schema_versions.py` | The catalog YAML/JSON lint. |
| `scripts/_phase2_lint_shared.py` | Shared helpers (repo root, argparser, reporter). |
| `tests/conformance/test_schema_version_lints.py` | Happy paths + two synthetic mismatches. |
| `tests/conformance/fixtures/missing_schema_version_skill/SKILL_demo.md` | Frontmatter omits `schema_version`. |
| `tests/conformance/fixtures/wrong_schema_version_catalog/node.yaml` | Declares `schema_version: "v0"`. |
| `.github/workflows/<lint-workflow>.yml` (or equivalent) | Two more steps in the existing `conventions_catalog_parity` job. |

## Out of scope

- **`SCHEMA-EVOLUTION-POLICY.md` itself** — handled by S2-07. This lint enforces *that the field is declared at `"v1"`*; the policy doc explains *why* and what `"v2"` would require.
- **Per-probe `sub_schema_version` cache-key participation** — handled by S2-06.
- **Per-probe `sub_schema_version` field in each Phase 2 sub-schema** — each probe story (S3-01, S4-*, …) declares its own. This story polices only the root `schema_version: "v1"` for skills + catalogs.
- **Future `v1.1` (additive minor bump) lint** — S2-07's policy doc names the bump rules; the *lint* in this story accepts any value matching `^v\d+(\.\d+)?$` if you want to be permissive. Phase-2 default: strict `"v1"`. Tighten later when the v1.1 case actually arrives.

## Notes for the implementer

- **Reuse `_extract_frontmatter_window` from `src/codegenie/skills/loader.py`** — do not duplicate the byte-offset parsing logic in a script. The lint imports the helper if S2-01 exposed it; if not, this story can add the export.
- **Don't traverse `tests/conformance/fixtures/` when walking real files.** The synthetic mismatch fixtures live there *intentionally* malformed; if the real-files lint walks into them, the real-files run goes red. Use a path exclusion list at the top of each script (skip any dir containing `synthetic_mismatch` or under `tests/conformance/fixtures/`).
- **Catalog `_schema.json` files are JSON, not YAML.** Use `json.load`; check `properties.schema_version.enum == ["v1"]` (a list comparison), not a string equality.
- **Catalog YAMLs declare `schema_version: "v1"` as a value;** schemas declare it as an `enum: ["v1"]` constraint. Don't confuse the two — the lint must check the right thing on each file kind.
- **Exit code 1 on any offender, even if others pass.** The whole job goes red if even one file is non-conformant. Print all offenders before exiting (don't bail on the first) so the developer fixes them in one round.
- **The CI job composes three lints under one name** (`conventions_catalog_parity`). Don't rename the job — the manifest references it. If your CI tool requires separate jobs to parallelize, run all three as steps within one job.
- **Wire the scripts to be runnable locally via `make lint` or `nox`.** The pre-commit hook (optional per ADR-0008) can call them too. The CI gate is the contract; the local invocation is the developer ergonomic.
