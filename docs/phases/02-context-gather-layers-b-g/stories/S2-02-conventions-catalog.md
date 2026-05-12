# Story S2-02 — Conventions catalog `node.yaml` + closed-enum `_schema.json`

**Step:** Step 2 — Plant skills loader, catalog expansion, schema-evolution policy, and conventions parity lint
**Status:** Ready
**Effort:** M
**Depends on:** S1-08 (`tools/digests.yaml` pin manifest — referenced by `catalog_version` discipline); Phase 1 `parsers/safe_yaml.py`
**ADRs honored:** ADR-0008 (closed `detect.type` enum + CI lint enforcing schema-code parity), Phase 1 ADR-0006 (catalog-versioning pattern this generalizes), Phase 1 ADR-0004 (`additionalProperties: false` at sub-schema root)

## Context

The conventions catalog is the **data-shaped surface** Phase 7 will extend when Chainguard distroless conventions are added by addition. ADR-0008 elevates the catalog's `detect.type` to a **closed enum** in `_schema.json` so the only way to add a new detector type is to amend the schema and the probe's `match/case` dispatch in the same PR — enforced by the parity lint shipped in S2-04. This story plants the schema and the seed `node.yaml` with the canonical Node.js convention set; the probe (`ConventionProbe`, D5) lands in Step 7 but the lint runs from Step 2 so `main` stays green.

The hard-fail-at-startup pattern (`SkillLoadError`'s sibling: `CatalogLoadError`) is Phase 1's precedent and the way "data, not prompts" stays honest under malformed YAML.

## References — where to look

- **Architecture:** `../phase-arch-design.md §"Component design" #4` — closed-enum `_schema.json` shape, probe dispatch via `match/case`, lint script behavior, perf envelope.
- **Architecture:** `../phase-arch-design.md §"Data model"` — `ConventionRule`, `ConventionDetect` Pydantic shapes.
- **Phase ADRs:** `../ADRs/0008-conventions-catalog-closed-enum-ci-lint.md` — ADR-0008 — the load-bearing decision; `detect.type` is closed enum; bidirectional CI lint.
- **Production ADRs:** `../../../production/design.md §2` — "organizational uniqueness as data, not prompts" — the architectural intent.
- **Source design:** `../final-design.md "Components" §5.3` + `"Components" §13` — Catalog version policy + closed-enum CI gate.
- **Existing code:** Phase 1's `src/codegenie/catalogs/` parent directory (if planted by S1-05) — match the loader pattern. Phase 1 ADR-0006 governs `catalog_version`.

## Goal

Land `src/codegenie/catalogs/conventions/_schema.json` and `src/codegenie/catalogs/conventions/node.yaml` such that the catalog loader validates `node.yaml` against the schema at module import, every detector entry's `detect.type` is one of the five enum values, and malformed YAML or schema-violating entries hard-fail at CLI startup with a typed `CatalogLoadError`.

## Acceptance criteria

- [ ] `src/codegenie/catalogs/conventions/_schema.json` is Draft 2020-12, declares `schema_version: { enum: ["v1"] }` at root, declares `catalog_version: { type: "integer" }` (Phase 1 ADR-0006 pattern), sets `additionalProperties: false` at root **and** at every nested object (`conventions[]`, `conventions[].detect`, `conventions[].args`-position structure where applicable).
- [ ] The schema's `detect.type` enum is exactly `["file_present", "package_dep", "regex_in_file", "tsconfig_field", "dockerfile_directive"]` — five values, no more, no fewer, alphabetical order is **not** required (preserve the ADR-0008 order).
- [ ] `conventions[].id` is constrained by `pattern: "^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$"` (mirrors Phase 1 ADR-0007 warning-ID pattern).
- [ ] `conventions[].severity` enum: `["info", "warn", "error"]`.
- [ ] `src/codegenie/catalogs/conventions/node.yaml` declares `schema_version: "v1"` and `catalog_version: 1` at root, and seeds the canonical Node.js convention set: at minimum one entry per enum value (5+ entries total), each with a non-empty `rationale`.
- [ ] Catalog loaded via `codegenie.parsers.safe_yaml.load`, validated via `jsonschema.Draft202012Validator`; the result is `MappingProxyType`-wrapped (read-only at runtime).
- [ ] Malformed YAML or schema violation → `CatalogLoadError` (typed); CLI exits 2.
- [ ] TDD red landed first: `tests/unit/catalogs/test_conventions_schema.py` initially fails.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` clean on touched modules.

## Implementation outline

1. If `src/codegenie/catalogs/` doesn't yet exist, plant `__init__.py` and a `loader.py` mirroring the pattern from Phase 1's catalog loader (assume S1-05 landed something analogous; otherwise, copy the shape — Phase 1 ADR-0006's `catalog_version` discipline + `safe_yaml.load` + `jsonschema` validation + `MappingProxyType` wrap).
2. Create `src/codegenie/catalogs/conventions/_schema.json` per the abridged shape in `phase-arch-design.md §"Component design" #4`. Declare `additionalProperties: false` at root and every nested object level. Reference `../../../../docs/phases/02-context-gather-layers-b-g/SCHEMA-EVOLUTION-POLICY.md` in a `$comment` (S2-07).
3. Create `src/codegenie/catalogs/conventions/node.yaml` with seed entries:
   - `node.tsconfig_strict` (type `tsconfig_field`)
   - `node.eslint_present` (type `file_present`)
   - `node.express_dependency` (type `package_dep`)
   - `node.async_void_handler` (type `regex_in_file`)
   - `node.dockerfile_user_set` (type `dockerfile_directive`)
   - Each entry has `severity` and a 1–2 sentence `rationale`.
4. Wire the loader's hard-fail-at-startup behavior: `CatalogLoadError(CodegenieError)` in `src/codegenie/catalogs/errors.py`; module-level catalog load via a `_load_conventions_catalog()` function called from `__init__.py` (lazy via `functools.cache` is acceptable — the contract is loaded-once-per-process, not loaded-at-import).
5. Cross-link: add a `# Schema-evolution policy: ../../../docs/phases/02-context-gather-layers-b-g/SCHEMA-EVOLUTION-POLICY.md` comment at the root of `node.yaml` and `_schema.json` (S2-07 will lint this).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/catalogs/test_conventions_schema.py`

```python
import pytest
from pathlib import Path

def test_node_catalog_loads_and_validates() -> None:
    # arrange: import the loader
    # act: load the seeded node.yaml
    # assert: 5+ entries; every detect.type is in the closed enum
    catalog = load_conventions_catalog("node")
    assert len(catalog["conventions"]) >= 5
    allowed = {"file_present", "package_dep", "regex_in_file", "tsconfig_field", "dockerfile_directive"}
    for entry in catalog["conventions"]:
        assert entry["detect"]["type"] in allowed

def test_schema_version_present_at_root() -> None:
    catalog = load_conventions_catalog("node")
    assert catalog["schema_version"] == "v1"

def test_unknown_detect_type_rejected(tmp_path: Path) -> None:
    # arrange: a synthetic catalog with detect.type = "unknown_kind"
    # act + assert: CatalogLoadError
    with pytest.raises(CatalogLoadError):
        ...

def test_malformed_yaml_raises_catalog_load_error(tmp_path: Path) -> None:
    with pytest.raises(CatalogLoadError):
        ...

def test_extra_field_under_convention_entry_rejected(tmp_path: Path) -> None:
    # additionalProperties: false at the nested level — synth a fixture with an extra key
    with pytest.raises(CatalogLoadError):
        ...

def test_id_pattern_enforced(tmp_path: Path) -> None:
    # synth a fixture with id "BAD-ID" (uppercase + hyphen) — must fail
    with pytest.raises(CatalogLoadError):
        ...
```

Run; confirm red (loader doesn't yet exist or seed catalog absent); commit; then Green.

### Green — make it pass

Smallest impl: write `_schema.json`, write `node.yaml`, write `loader.py` with one function that reads + validates + `MappingProxyType`-wraps. Errors converted to `CatalogLoadError`.

### Refactor — clean up

- Factor `load_conventions_catalog(language: str)` so future `python.yaml`, `java.yaml` land by addition (drop a new file; no loader edits).
- `@functools.cache` on the loader so repeated calls share the parsed result.
- Add a `__all__` export list to `__init__.py`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/catalogs/conventions/_schema.json` | Draft 2020-12 schema with closed `detect.type` enum + `additionalProperties: false`. |
| `src/codegenie/catalogs/conventions/node.yaml` | Seed catalog with one entry per enum value. |
| `src/codegenie/catalogs/loader.py` (or extend if S1-05 planted it) | `load_conventions_catalog(language: str) -> Mapping`. |
| `src/codegenie/catalogs/errors.py` | `CatalogLoadError` typed exception. |
| `src/codegenie/catalogs/__init__.py` | Export `load_conventions_catalog`, `CatalogLoadError`. |
| `tests/unit/catalogs/test_conventions_schema.py` | Happy path + extra-field rejection + unknown enum + malformed YAML + id pattern. |
| `tests/unit/catalogs/fixtures/*.yaml` | Adversarial fixtures (synthetic mismatch / extra field / malformed). |

## Out of scope

- **`ConventionProbe` (D5)** — handled by Step 7. This story plants the catalog; the consumer probe and its `_apply_detector` `match/case` land later. S2-04 plants a stub helper so the parity lint runs from Step 2.
- **Shell-replacements catalog + Semgrep rule packs** — handled by S2-03.
- **Parity CI lint script** — handled by S2-04.
- **`schema_version: "v1"` CI lint** — handled by S2-05.
- **`SCHEMA-EVOLUTION-POLICY.md`** — handled by S2-07.
- **`python.yaml`, `java.yaml`, etc.** — Phase 11+ adds languages by addition (drop new file under `conventions/`); not Phase 2 scope.
- **Phase 7 distroless `detect.type` additions** — Phase 7 amends the enum + adds `match/case` arm + bumps `catalog_version` in one PR per ADR-0008.

## Notes for the implementer

- **Enum order matters for the lint.** S2-04's `check_conventions_catalog_parity.py` uses *set* equality (order-independent), but the ADR-0008 documented order is `["file_present", "package_dep", "regex_in_file", "tsconfig_field", "dockerfile_directive"]`. Preserve it in `_schema.json` for human readability — reviewers compare top-to-bottom.
- **`additionalProperties: false` at every nested object.** It's easy to set it at root and miss the nested entries. Run a quick recursive walk in the test to assert it: every `properties: {…}` block in `_schema.json` has a sibling `additionalProperties: false`.
- **`catalog_version: int` is Phase 1 ADR-0006**, not Phase 2 invention. Additive enum addition → minor bump (Phase 7 will go from `catalog_version: 1` to `catalog_version: 2`). The schema validates the type; the policy enforces the semantics.
- **`schema_version` vs `catalog_version`.** Two different things. `schema_version: "v1"` versions the **shape**; `catalog_version: 1` versions the **contents**. Phase 2 ships both at their first value; S2-07 documents how each evolves.
- **`MappingProxyType` matters.** If the catalog is returned as a mutable `dict`, a downstream probe can accidentally mutate it (especially in tests with `monkeypatch`). Wrap recursively or document that the top-level mutation is what's blocked. Top-level is sufficient for Phase 2 because every consumer reads via dotted keys.
- **Fail loud.** Match Rule 12 — if the catalog has a typo, the CLI must exit with `2` immediately, with the exact JSON Pointer of the violation in the error message. Don't let a "graceful degradation" pattern leak in.
