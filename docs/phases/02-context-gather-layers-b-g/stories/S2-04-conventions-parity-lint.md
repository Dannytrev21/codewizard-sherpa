# Story S2-04 — Conventions parity CI lint script + job wiring

**Step:** Step 2 — Plant skills loader, catalog expansion, schema-evolution policy, and conventions parity lint
**Status:** Ready
**Effort:** S
**Depends on:** S2-02 (the closed `detect.type` enum in `_schema.json` is the lint's oracle)
**ADRs honored:** ADR-0008 (closed `detect.type` enum + CI lint enforcing schema-code parity — this story plants the lint), Phase 1 ADR-0006 (catalog-versioning pattern)

## Context

ADR-0008's load-bearing claim is that **schema-code parity is compiler-enforced, not reviewer-enforced**: when Phase 7's distroless work adds a new `detect.type`, the same PR must add the enum entry in `_schema.json` *and* the `match/case` arm in `_apply_detector`. The mechanism is a CI lint that walks the probe source, extracts the `match/case` branches via Python AST, and set-compares them to the schema enum. Asymmetry in either direction → CI red.

`ConventionProbe` itself lands in Step 7. To keep `main` green from Step 2, this story plants a **skeleton stub** of `_apply_detector` containing all five `case` arms (each body `raise NotImplementedError`) so the lint passes on `main` from now. The Step-7 story replaces the stub bodies with real dispatch logic. The lint script and one synthetic mismatch fixture (asserting the lint actually fails on asymmetry) land here.

## References — where to look

- **Architecture:** `../phase-arch-design.md §"Component design" #4` — closed-enum CI lint section; lint script behavior described in prose.
- **Phase ADRs:** `../ADRs/0008-conventions-catalog-closed-enum-ci-lint.md` — ADR-0008 — explicit lint contract; bidirectional parity; lint must be CI-gating not advisory; ~80 LOC of CI scaffolding expected.
- **Source design:** `../final-design.md "Components" §13 Catalog version policy + closed-enum CI gate` — the design statement.
- **Source design:** `../final-design.md "Conflict-resolution table" D18` — the resolution row.
- **Existing code:** `src/codegenie/catalogs/conventions/_schema.json` (from S2-02) — the lint's oracle for the enum set. Phase 0 / Phase 1's `scripts/` directory (if present) — match the existing CI-script style.
- **CI config:** project-level GitHub Actions / pre-commit config (location TBD; co-locate with other Phase 0/1 lint jobs).

## Goal

Land `scripts/check_conventions_catalog_parity.py` and a stub `src/codegenie/probes/convention.py` with a `_apply_detector` `match/case` whose arms set-equal the `detect.type` enum in `_schema.json` — wired into a new `conventions_catalog_parity` CI job that runs on every PR and goes red on the synthetic-mismatch fixture.

## Acceptance criteria

- [ ] `scripts/check_conventions_catalog_parity.py` is a standalone Python script invokable as `python scripts/check_conventions_catalog_parity.py` (exit 0 on parity; exit 1 on asymmetry); takes no arguments; auto-discovers `src/codegenie/catalogs/conventions/_schema.json` and `src/codegenie/probes/convention.py` from a fixed repo-root relative path.
- [ ] The script uses `ast.parse` + a visitor to find the `_apply_detector` function in `convention.py`, walks its body for `Match` nodes, and extracts the string-literal value of every `case "<value>"` arm (skipping the `_` default). It returns these as a `set[str]`.
- [ ] The script loads `_schema.json` via `json.load` and extracts `properties.conventions.items.properties.detect.properties.type.enum` as a `set[str]`.
- [ ] The script asserts `case_arms == enum_values`. On asymmetry, exits 1 and prints both sides + the symmetric difference to stderr (which side is missing what).
- [ ] `src/codegenie/probes/convention.py` exists with a stub class `ConventionProbe(Probe)` and a stub `_apply_detector(self, entry: Mapping[str, Any]) -> None` whose body contains the `match entry["detect"]["type"]:` with five `case` arms (one per enum value), each body `raise NotImplementedError(f"Phase 7 lands {entry['detect']['type']} dispatch")`, plus a `case _: raise UnsupportedConventionType(...)`. The probe is **not registered** (no `@register_probe` decorator) so it doesn't run.
- [ ] One synthetic mismatch fixture under `tests/conformance/fixtures/synthetic_mismatch/`: a copy of `_schema.json` with an extra enum value (no corresponding `case`) and a copy of `convention.py` with an extra `case` arm (no enum entry). The test runs the lint script against the fixture and asserts exit code 1 in both directions.
- [ ] `tests/conformance/test_catalog_enum_parity.py` runs the lint script against the *real* `_schema.json` + `convention.py` and asserts exit code 0.
- [ ] CI job wired: a new step in the existing Phase 0/1 lint workflow (or a new `conventions_catalog_parity` job; naming preserved per the manifest) runs the script. S2-05 will extend this same job with two more lints.
- [ ] TDD red landed first: `tests/conformance/test_catalog_enum_parity.py` initially fails because the lint script or the stub probe doesn't exist.

## Implementation outline

1. Create `src/codegenie/probes/convention.py` with the stub `ConventionProbe` and the `_apply_detector` `match/case` skeleton. Each arm body is `raise NotImplementedError(...)`. The default arm raises a typed `UnsupportedConventionType(CodegenieError)` (define in `src/codegenie/probes/errors.py` if not already present).
2. Create `scripts/check_conventions_catalog_parity.py`:
   - Resolve repo-root via `Path(__file__).resolve().parents[1]`.
   - Load `_schema.json`; extract the enum set.
   - Parse `convention.py` via `ast.parse(src, type_comments=False)`; find the `_apply_detector` `FunctionDef`; walk for `ast.Match` nodes; for each `match_case`, if the `pattern` is a `MatchValue` whose `value` is a `Constant(str)`, collect the string.
   - Compare the two sets. On mismatch, print a structured diff to stderr; `sys.exit(1)`.
3. Create `tests/conformance/test_catalog_enum_parity.py`:
   - One test that runs the script against the real files; asserts `subprocess.run([...]).returncode == 0`.
   - One test that runs the script against the synthetic-mismatch fixture (point the script at the fixture via env var or a `--schema/--source` flag); asserts `returncode == 1` and stderr contains the offending value.
4. Add the `--schema PATH` and `--source PATH` optional flags to the lint script so the fixture test can point it at the synthetic directory without monkeypatching paths.
5. Create the synthetic-mismatch fixtures under `tests/conformance/fixtures/synthetic_mismatch/`.
6. Wire the lint into CI: add a step to the existing Python-lint workflow (or create `conventions_catalog_parity` as a new job) that runs `python scripts/check_conventions_catalog_parity.py`. The job must run **before** unit tests so reviewers see the lint failure at the top of the CI log, not buried under test output.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/conformance/test_catalog_enum_parity.py`

```python
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_conventions_catalog_parity.py"

def test_real_schema_and_source_in_parity() -> None:
    # arrange: the real _schema.json + convention.py (after this story lands)
    # act
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True)
    # assert
    assert result.returncode == 0, result.stderr.decode()

def test_synthetic_mismatch_extra_enum_fails(tmp_path: Path) -> None:
    # arrange: copy real schema, add a bogus enum value; keep real source untouched
    fixture_dir = REPO_ROOT / "tests/conformance/fixtures/synthetic_mismatch_extra_enum"
    # act
    result = subprocess.run([
        sys.executable, str(SCRIPT),
        "--schema", str(fixture_dir / "_schema.json"),
        "--source", str(fixture_dir / "convention.py"),
    ], capture_output=True)
    # assert
    assert result.returncode == 1
    assert b"bogus_extra_type" in result.stderr

def test_synthetic_mismatch_extra_case_fails(tmp_path: Path) -> None:
    fixture_dir = REPO_ROOT / "tests/conformance/fixtures/synthetic_mismatch_extra_case"
    result = subprocess.run([
        sys.executable, str(SCRIPT),
        "--schema", str(fixture_dir / "_schema.json"),
        "--source", str(fixture_dir / "convention.py"),
    ], capture_output=True)
    assert result.returncode == 1
    assert b"orphaned_case_type" in result.stderr
```

Run; confirm red (script doesn't exist, stub probe doesn't exist, fixtures don't exist); commit; then Green.

### Green — make it pass

Smallest impl: stub `convention.py`, lint script with `ast` walk + set comparison, two synthetic-mismatch fixture directories. No more. The whole script is ~80 LOC per ADR-0008's estimate.

### Refactor — clean up

- Extract the AST-walk into a helper function `_extract_case_arms(source_path: Path) -> set[str]` for reuse by S2-05's parallel lints.
- Add a `--strict` flag that elevates a `case _:` arm with anything other than `raise UnsupportedConventionType(...)` to a lint failure (defends the "default arm must fail loud" discipline).
- Docstring at the top of the script explaining ADR-0008 + the bidirectional invariant + how to add a new `detect.type`.
- Pre-commit hook entry (optional; ADR-0008 mentions this as a soft mitigation).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/convention.py` | Stub class + skeleton `_apply_detector` `match/case`; keeps `main` green from Step 2. |
| `src/codegenie/probes/errors.py` | Add `UnsupportedConventionType(CodegenieError)` if not yet present. |
| `scripts/check_conventions_catalog_parity.py` | The lint script; `ast` walk + set comparison; `--schema/--source` flags. |
| `tests/conformance/test_catalog_enum_parity.py` | Real-files parity + two synthetic mismatch directions. |
| `tests/conformance/fixtures/synthetic_mismatch_extra_enum/{_schema.json, convention.py}` | Schema has an extra enum value; source doesn't. |
| `tests/conformance/fixtures/synthetic_mismatch_extra_case/{_schema.json, convention.py}` | Source has an extra `case`; schema doesn't. |
| `.github/workflows/<existing-or-new>.yml` (or `pyproject.toml` pre-commit config) | Wire the lint into a CI job that runs before unit tests. |

## Out of scope

- **`ConventionProbe` real dispatch logic** — Phase 7 / Step 7 (S7-04). This story ships the stub; the real implementation replaces each `raise NotImplementedError` body in a future PR that the lint still passes.
- **Shell-replacements parity lint** — Step 5 (S5-04 or equivalent) extends the same script (or adds a sibling) when `ShellUsageProbe` lands. S2-04 keeps the scope to *conventions*.
- **`schema_version: "v1"` lint** — handled by S2-05.
- **Pre-commit hook automation** — optional; ADR-0008 calls it out as a mitigation but CI-gating is the contract.
- **`SCHEMA-EVOLUTION-POLICY.md`** — handled by S2-07.

## Notes for the implementer

- **The stub `_apply_detector` raises `NotImplementedError` per arm, not `pass`.** A `pass` body would let a probe accidentally do nothing if invoked; `NotImplementedError` makes it loud. The probe class is also **unregistered** in Phase 2 — no `@register_probe` decorator — so the coordinator never invokes it. Both safeties together.
- **`ast.Match` is Python 3.10+.** The project pins Python 3.11+ (per `CLAUDE.md`); no compatibility shim needed.
- **`MatchValue` vs `MatchAs`.** `case "file_present":` parses as `MatchValue(value=Constant("file_present"))`. `case "file_present" as x:` would parse differently; reject anything that isn't a pure `MatchValue(Constant(str))` and surface a clear error ("`_apply_detector` case arms must be string literals only"). Keeps the lint contract narrow.
- **`case _:` is the default and must be skipped from the comparison set.** It's the safety net, not an enum member. Detect it via `MatchAs(pattern=None, name=None)` or `pattern is None`.
- **Exit codes matter for CI.** `sys.exit(0)` on parity; `sys.exit(1)` on asymmetry. Never `raise SystemExit`; never print to stdout for the asymmetry (stderr only) so a downstream tool that pipes the lint's stdout doesn't get garbage.
- **Run before unit tests.** ADR-0008's "Failure mode is loud" tradeoff row depends on the lint failing at the top of CI. Don't put it in a post-test stage.
- **The synthetic fixtures must contain `# DO NOT USE — synthetic mismatch fixture` headers** so an editor walking the repo doesn't mistake them for real code.
