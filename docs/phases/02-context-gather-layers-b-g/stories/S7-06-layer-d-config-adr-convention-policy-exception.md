# Story S7-06 — Layer D: `RepoConfig`, `ADR`, `Convention`, `Policy`, `Exception` (5 probes)

**Step:** Step 7 — Ship Layer D, Layer E (real + stubs), Layer G; plant per-file findings sub-caches
**Status:** Ready
**Effort:** M
**Depends on:** S2-07, S2-04
**ADRs honored:** ADR-0008 (conventions catalog closed-enum + CI parity lint)

## Context

Five Layer D probes ship together because they share the same structural shape: Tier-0 pure-Python YAML/markdown reads, < 100 ms each, validating against a small Pydantic model + sub-schema. They are: `RepoConfigProbe` (D1, reads `.codegenie/config.yaml`), `ADRProbe` (D3, walks `docs/adr/` for ADR ID + status + title), `ConventionProbe` (D5, applies the conventions catalog), `PolicyProbe` (D4, reads `policy/*.yaml`), `ExceptionProbe` (D6, reads exception registry with `expires:` date-parsing). **`ConventionProbe` is the load-bearing one of the five**: it dispatches over the closed-enum `detect.type` via Python `match/case`, and S2-04's CI parity lint asserts bidirectional symmetry between the `match/case` arms and `_schema.json`'s enum. Phase 7 (Chainguard distroless) will add new `detect.type` values — the lint structurally proves Phase 7 met "extension by addition" or fails the PR.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #20` — Layer D probe inventory; < 80 LOC each; Tier-0 pure-Python.
  - `../phase-arch-design.md §"Logical view"` — `ConventionProbe → CatalogsExpansion: conventions/node.yaml`.
  - `../phase-arch-design.md §"Component design" #4` — Conventions catalog closed-enum CI lint.
  - `../phase-arch-design.md §"Data model" → ConventionRule, ConventionDetect` — closed enum on `detect.type` is `["file_present", "package_dep", "regex_in_file", "tsconfig_field", "dockerfile_directive"]`.
- **Phase ADRs:**
  - `../ADRs/0008-conventions-catalog-closed-enum-ci-lint.md` — ADR-0008 (closed-enum + parity lint).
- **Source design:**
  - `../final-design.md §"Components" §5 Layer D — Organizational`.
  - `../final-design.md §"Conflict-resolution table" D18` — closed-enum + CI lint winner.
- **Existing code:**
  - `src/codegenie/catalogs/conventions/node.yaml` + `_schema.json` (S2-02) — closed-enum catalog.
  - `src/codegenie/catalogs/shell_replacements/node.yaml` (S2-02) — ShellUsageProbe uses this; ConventionProbe does NOT.
  - `src/codegenie/parsers/safe_yaml.py` (Phase 1) — used for YAML loads.
  - `scripts/check_conventions_catalog_parity.py` (S2-04) — CI lint that consumes this probe's `match/case`.

## Goal

Ship five Layer D probes — `src/codegenie/probes/{repo_config,adr,convention,policy,exception}.py` — plus five sub-schemas; `ConventionProbe._apply_detector` dispatches over the closed-enum `detect.type` via Python `match/case` (exhaustive; `_` raises `UnsupportedConventionType`); the parity lint from S2-04 is green when both directions match.

## Acceptance criteria

- [ ] `src/codegenie/probes/repo_config.py` — `RepoConfigProbe`, `name="repo_config"`, `declared_inputs=[".codegenie/config.yaml"]`, `requires=[]`, `applies_to_languages=["*"]`. Reads `.codegenie/config.yaml` via `safe_yaml.load`; validates against `RepoConfig` Pydantic model; if missing → `slice = {"present": false}`; if malformed → `confidence: low` + errors.
- [ ] `src/codegenie/probes/adr.py` — `ADRProbe`, `name="adr"`, `declared_inputs=["docs/adr/**/*.md", "docs/adrs/**/*.md", "docs/architecture/decisions/**/*.md"]`, `requires=[]`. Walks the listed directories; extracts `(adr_id, status, title)` from each markdown file's frontmatter or H1 + "Status:" line. Emits `slice = {"adrs": [{adr_id, status, title, path}]}`. Title only; **body never inlined** (path reference only).
- [ ] `src/codegenie/probes/convention.py` — `ConventionProbe`, `name="convention"`, `declared_inputs=["package.json", "tsconfig.json", "Dockerfile", "src/**/*"]` (filtered by detector type), `requires=["language_detection"]`. Loads `catalogs/conventions/<language>.yaml`; for each rule, `_apply_detector(entry)` dispatches over `entry["detect"]["type"]` via Python `match/case`:
  - `"file_present"` → `os.path.exists` check against `entry["detect"]["args"]["path"]`.
  - `"package_dep"` → consult `ctx.parsed_manifest("package.json")`'s `dependencies` + `devDependencies`.
  - `"regex_in_file"` → ripgrep / `re.search` over file content.
  - `"tsconfig_field"` → consult parsed tsconfig.
  - `"dockerfile_directive"` → consult Dockerfile AST.
  - `_` → `raise UnsupportedConventionType(...)`.
- [ ] `src/codegenie/probes/policy.py` — `PolicyProbe`, `name="policy"`, `declared_inputs=["policy/*.yaml", ".codegenie/policy/*.yaml"]`. Reads each file via `safe_yaml.load`; validates against `Policy` Pydantic model. Emits `slice = {"policies": [...]}`.
- [ ] `src/codegenie/probes/exception.py` — `ExceptionProbe`, `name="exception"`, `declared_inputs=[".codegenie/exceptions.yaml", "exceptions.yaml"]`. Reads exception registry; **date-parses `expires:`** (`datetime.date.fromisoformat`); separates active vs expired entries. Emits `slice = {"active": [...], "expired": [...]}`.
- [ ] Five sub-schemas at `src/codegenie/schema/probes/{repo_config,adr,convention,policy,exception}.schema.json` — `additionalProperties: false`; `schema_version: "v1"`.
- [ ] Each probe runs in < 100 ms on its happy-path fixture (asserted in tests via wall-clock).
- [ ] `tests/unit/probes/test_repo_config.py`, `test_adr.py`, `test_convention_dispatch.py`, `test_policy.py`, `test_exception.py` — one unit test per probe + one closed-enum-dispatch coverage test for `ConventionProbe` (one assertion per `detect.type` enum value; **5 cases**).
- [ ] `tests/unit/probes/test_convention_unknown_type_raises.py` — synthetic catalog YAML with `detect.type: "bogus"` → `ConventionProbe._apply_detector` raises `UnsupportedConventionType`; probe surfaces `confidence: low`.
- [ ] `ExceptionProbe`'s date-parsing test: `expires: 2025-01-01` → expired; `expires: 2099-01-01` → active; malformed date → `confidence: low` + error.
- [ ] Five goldens at `tests/golden/{repo_config,adr,convention,policy,exception}/happy/expected.json`.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Create the five probe modules. Pattern is identical for the four small probes; `ConventionProbe` is the one with `match/case` dispatch:
   ```python
   def _apply_detector(self, entry: ConventionRule, snapshot: Snapshot, ctx: ProbeContext) -> bool:
       match entry.detect.type:
           case "file_present":
               return self._detect_file_present(entry.detect.args, snapshot)
           case "package_dep":
               return self._detect_package_dep(entry.detect.args, ctx)
           case "regex_in_file":
               return self._detect_regex_in_file(entry.detect.args, snapshot)
           case "tsconfig_field":
               return self._detect_tsconfig_field(entry.detect.args, ctx)
           case "dockerfile_directive":
               return self._detect_dockerfile_directive(entry.detect.args, ctx)
           case _:
               raise UnsupportedConventionType(entry.detect.type)
   ```
2. Create five sub-schemas. `convention.schema.json` declares `findings: list[{rule_id, applied: bool, severity, rationale}]`.
3. Register all five probes in `probes/__init__.py`.
4. Add `UnsupportedConventionType` to `src/codegenie/errors.py` (Step 1 added the bulk; this is one more — if Step 1's ADR-0005 list missed it, add as surgical edit).
5. Plant fixtures: `tests/fixtures/repo_config_fixture/`, `tests/fixtures/adr_fixture/` (3 ADRs), `tests/fixtures/convention_fixture/` (5 rule fixtures, one per `detect.type`), `tests/fixtures/policy_fixture/`, `tests/fixtures/exception_fixture/` (mix of active + expired).

## TDD plan — red / green / refactor

### Red

Path: `tests/unit/probes/test_convention_dispatch.py`.

```python
import pytest
from codegenie.probes.convention import ConventionProbe

@pytest.mark.parametrize("detect_type", [
    "file_present", "package_dep", "regex_in_file",
    "tsconfig_field", "dockerfile_directive",
])
async def test_each_detect_type_has_a_case_arm(detect_type, convention_fixture, ctx):
    out = await ConventionProbe().run(convention_fixture.snapshot, ctx)
    findings = out.slice["findings"]
    # The fixture has one rule per detect_type; assert it dispatched (no UnsupportedConventionType).
    assert any(f["rule_id"].endswith(detect_type) for f in findings)

async def test_unknown_detect_type_low_confidence(synthetic_bogus_catalog, ctx):
    out = await ConventionProbe().run(synthetic_bogus_catalog.snapshot, ctx)
    assert out.confidence == "low"
    assert any("UnsupportedConventionType" in e for e in out.errors)
```

Path: `tests/unit/probes/test_exception.py`.

```python
async def test_expires_date_parsing(exception_fixture, ctx):
    out = await ExceptionProbe().run(exception_fixture.snapshot, ctx)
    assert {"expired_rule_1"} <= {e["id"] for e in out.slice["expired"]}
    assert {"active_rule_1"} <= {a["id"] for a in out.slice["active"]}

async def test_malformed_expires_lowers_confidence(malformed_expires_fixture, ctx):
    out = await ExceptionProbe().run(malformed_expires_fixture.snapshot, ctx)
    assert out.confidence == "low"
```

Similar shapes for `test_repo_config.py`, `test_adr.py`, `test_policy.py` — happy path + missing-file low-confidence + malformed-YAML low-confidence.

### Green

Minimal impl per outline. Each non-Convention probe is < 80 LOC. `ConventionProbe` is ~150 LOC (one helper per detect type + the `match/case` dispatcher).

### Refactor

- Pull the five `_detect_*` helpers in `ConventionProbe` to module-private functions or `@staticmethod`s — keep the dispatcher readable.
- Module docstring naming `phase-arch-design.md §"Component design" #20`, `final-design.md "Conflict-resolution table" D18`, ADR-0008.
- Each probe has a `_resolve_inputs(snapshot) -> Path | None` helper — testable.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/repo_config.py` | New. |
| `src/codegenie/probes/adr.py` | New. |
| `src/codegenie/probes/convention.py` | New — `match/case` dispatcher. |
| `src/codegenie/probes/policy.py` | New. |
| `src/codegenie/probes/exception.py` | New. |
| `src/codegenie/schema/probes/{repo_config,adr,convention,policy,exception}.schema.json` | New — 5 sub-schemas. |
| `src/codegenie/errors.py` | Surgical — add `UnsupportedConventionType` if missing. |
| `src/codegenie/probes/__init__.py` | Register 5 probes. |
| `tests/unit/probes/test_{repo_config,adr,convention_dispatch,policy,exception}.py` | New — 5 test files + 1 dispatch-coverage test. |
| `tests/unit/probes/test_convention_unknown_type_raises.py` | New. |
| `tests/fixtures/{repo_config,adr,convention,policy,exception}_fixture/` | New — 5 fixture trees. |
| `tests/golden/{repo_config,adr,convention,policy,exception}/happy/expected.json` | New — 5 goldens. |

## Out of scope

- **ADR body inlining** — explicitly forbidden (`final-design.md "Goals" #7 Progressive disclosure`); path reference only.
- **Policy semantic evaluation** — `PolicyProbe` *records* the policies; *evaluation* against the codebase is the Planner's job (Phase 3+).
- **Exception expiry notifications** — auto-renew / alerting is Phase 14.
- **`ShellUsageProbe`'s catalog dispatch** — that's a separate probe (Step 5, S5-03); the closed-enum discipline applies there too but is enforced in its own parity lint.
- **Cross-repo ADR aggregation** — Phase 14 portfolio-scale concern.

## Notes for the implementer

- **`match/case` is the load-bearing structural element.** The parity lint (S2-04) parses the AST of `_apply_detector` looking for `case "<value>"` patterns. If you refactor to an `if/elif` chain, the lint won't detect the dispatch and the CI gate weakens. Keep `match/case`.
- **`UnsupportedConventionType`** is the `case _` fallthrough. The exhaustive match assertion (S2-04 lint) means this case is technically unreachable at runtime — but defend it anyway. A future schema-evolution mistake could land a new enum value without updating the probe; the lint catches it in CI, but the runtime guard is belt-and-suspenders.
- **`expires:` is `datetime.date`, not `datetime.datetime`.** YAML's date type auto-parses; `safe_yaml.load` may already return a `date` object. Handle both `date` and `str` inputs — defensive.
- **`ADRProbe`'s frontmatter handling** — most ADRs use Nygard-style markdown with `**Status:** Accepted` lines, not YAML frontmatter. Use a small regex: `r"^\*\*Status:\*\*\s+(\w+)"`. Don't try to parse markdown via `markdown-it-py` for this — overkill.
- **`RepoConfigProbe`'s `present: false`** is `confidence: "high"` (we successfully observed absence), not `"low"`. Absence is a valid fact; the probe didn't fail.
- **All five probes ignore `requires=[]`** except `ConventionProbe` (which needs `language_detection` to pick `node.yaml` vs future `python.yaml`). Don't over-couple.
- **Sub-schema's `additionalProperties: false` at every nested level** — including inside `findings[]`. A common mistake is to enforce it only at the root. Phase 1's ADR-0004 envelope is the contract; carry it deep.
- **The unknown-detect-type test** uses a synthetic catalog YAML in the fixture; the catalog YAML itself has a closed-enum schema (S2-02), so the parity lint *catches this at CI time* — but the synthetic fixture bypasses the lint to test the runtime behavior. Document this in the fixture's README.
