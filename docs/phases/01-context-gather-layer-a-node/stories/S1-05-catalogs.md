# Story S1-05 — Catalog loader with self-schema + `native_modules.yaml` + `ci_providers.yaml` seed

**Step:** Step 1 — Plant shared primitives, sub-schema convention, and the three Phase-0 in-place edits
**Status:** Ready
**Effort:** M
**Depends on:** S1-02, S1-03
**ADRs honored:** ADR-0006, ADR-0008

## Context

Two catalogs ship in Phase 1 as YAML data files loaded at module import: `native_modules.yaml` (10 seed entries — the load-bearing input for Phase 7's distroless migration) and `ci_providers.yaml` (markers and parser kinds for the CI providers Phase 1 supports). Both are validated against a self-schema at startup and exposed as `MappingProxyType`-wrapped immutable dicts. Each catalog file is listed in `NodeManifestProbe.declared_inputs` (and similar) so editing a catalog cleanly invalidates only the relevant probe's cache entries — that's the ADR-0006 versioning mechanism in action.

The catalogs are organizational uniqueness expressed as data, not prompts (production design §2.6). The Planner queries structured data; it never has to infer your company's rules from prose.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #10` — interface (`NATIVE_MODULES`, `CI_PROVIDERS`, the `_CATALOG_VERSION` constants), hard-fail at CLI startup on malformed YAML or schema mismatch, `MappingProxyType` immutability.
  - `../phase-arch-design.md §"Component design" #4` — the seed 10 native modules (`bcrypt`, `sharp`, `better-sqlite3`, `node-canvas`, `node-rdkafka`, `node-pty`, `bufferutil`, `utf-8-validate`, `argon2`, `keytar`) and `NativeModuleEntry` shape (name, requires_node_gyp, system_deps_required, binary_artifacts_glob, notes, catalog_entry_version).
  - `../phase-arch-design.md §"Component design" #5` — `CIProviderEntry` shape (name, marker_paths, parser).
  - `../phase-arch-design.md §"Edge cases"` row 9 — malformed catalog YAML at startup is a hard fail, not a degrade.
  - `../phase-arch-design.md §"Data model"` — `NativeModuleEntry` and `CIProviderEntry` as `NamedTuple`s.
- **Phase ADRs:**
  - `../ADRs/0006-native-module-catalog-versioning.md` — ADR-0006 — `catalog_version` field at file top; catalog YAML in `NodeManifestProbe.declared_inputs`; editing catalog invalidates the probe's cache entries only.
  - `../ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md` — caps apply at the parser level; catalog YAMLs route through `safe_yaml.load`.
- **Source design:**
  - `../final-design.md §"Components" #10` — design statement.
- **Existing code:**
  - `src/codegenie/parsers/safe_yaml.py` (S1-03) — used by the catalog loader.
  - `src/codegenie/errors.py` (S1-01) — `CatalogLoadError`.
- **External docs (only if directly relevant):**
  - JSON Schema Draft 2020-12 — `jsonschema.Draft202012Validator`.

## Goal

Load `native_modules.yaml` and `ci_providers.yaml` at import time via `safe_yaml.load` + self-schema validation; expose `NATIVE_MODULES: Mapping[str, NativeModuleEntry]`, `CI_PROVIDERS: Mapping[str, CIProviderEntry]`, and the two `_CATALOG_VERSION: int` constants as module-level immutables; hard-fail at startup with `CatalogLoadError` on any defect.

## Acceptance criteria

- [ ] `src/codegenie/catalogs/__init__.py` exports `NATIVE_MODULES`, `CI_PROVIDERS`, `NATIVE_MODULES_CATALOG_VERSION`, `CI_PROVIDERS_CATALOG_VERSION`, `NativeModuleEntry`, `CIProviderEntry`.
- [ ] `NATIVE_MODULES` and `CI_PROVIDERS` are `MappingProxyType` instances at module scope (immutable); attempting `NATIVE_MODULES["bcrypt"] = ...` raises `TypeError`.
- [ ] `NativeModuleEntry` and `CIProviderEntry` are `typing.NamedTuple` subclasses with the documented fields.
- [ ] `native_modules.yaml` ships the 10 seed entries from `phase-arch-design.md §"Component design" #4`; each entry validates against `_schema.json`.
- [ ] `ci_providers.yaml` ships entries for `github_actions`, `gitlab_ci`, `circleci`, `jenkins`, `azure_pipelines`; each carries `marker_paths` and `parser`.
- [ ] `_schema.json` is JSON Schema Draft 2020-12; validates both catalog files; top-level `catalog_version: int` field required; duplicate names rejected (`uniqueItems` on the entries' names, or post-load duplicate detection).
- [ ] Malformed YAML at startup raises `CatalogLoadError(path=..., detail=...)` propagated to the CLI (hard fail).
- [ ] Schema-mismatch at startup raises `CatalogLoadError`.
- [ ] Duplicate name at startup raises `CatalogLoadError`.
- [ ] Emits one `probe.catalog.load` structlog event per catalog at load time with `catalog_name`, `entries`, `catalog_version` fields.
- [ ] Unit tests cover: successful load, malformed YAML → `CatalogLoadError`, schema-mismatch → `CatalogLoadError`, duplicate-name → `CatalogLoadError`, `MappingProxyType` immutability, `_CATALOG_VERSION` is `int`.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Create `src/codegenie/catalogs/__init__.py` with the loader. Define `NativeModuleEntry` and `CIProviderEntry` as `NamedTuple` subclasses (immutable, hashable, mypy-friendly).
2. Create `src/codegenie/catalogs/_schema.json` — Draft 2020-12 schema supporting both catalogs (one top-level `oneOf` or two distinct definitions). Top-level requires `catalog_version: int` and `entries: list[Entry]` where `Entry` is the relevant tuple shape.
3. Create `src/codegenie/catalogs/native_modules.yaml` with `catalog_version: 1` and the 10 seed entries.
4. Create `src/codegenie/catalogs/ci_providers.yaml` with `catalog_version: 1` and the 5 provider entries.
5. Loader logic:
   - `_load_catalog(path: Path, entry_cls: type, schema_subkey: str) -> tuple[MappingProxyType, int]`:
     - `data = safe_yaml.load(path, max_bytes=1_000_000)` — catch any `CodegenieError` and re-raise as `CatalogLoadError(path=path, detail=...)`.
     - Validate against the relevant `_schema.json` subsection via `jsonschema.Draft202012Validator`.
     - Detect duplicate names → raise `CatalogLoadError`.
     - Construct `dict[name, entry_cls(...)]` then wrap in `MappingProxyType`.
     - Return `(mapping, catalog_version)`.
6. At module scope: call `_load_catalog` twice; assign module-level constants; emit `probe.catalog.load` per catalog.
7. Use `importlib.resources` (or `Path(__file__).parent`) to locate the YAML files — they ship next to `__init__.py`.

## TDD plan — red / green / refactor

### Red — failing test first

Test file: `tests/unit/catalogs/test_catalog_loader.py`.

```python
# tests/unit/catalogs/test_catalog_loader.py
import importlib
from types import MappingProxyType

import pytest

import codegenie.errors as e


def test_native_modules_loaded():
    import codegenie.catalogs as cat
    assert isinstance(cat.NATIVE_MODULES, MappingProxyType)
    # 10 seed entries per phase-arch-design.md §"Component design" #4
    assert {"bcrypt", "sharp", "better-sqlite3", "node-canvas", "node-rdkafka",
            "node-pty", "bufferutil", "utf-8-validate", "argon2", "keytar"} <= set(cat.NATIVE_MODULES)
    bcrypt = cat.NATIVE_MODULES["bcrypt"]
    # NamedTuple shape — every documented field present
    assert hasattr(bcrypt, "requires_node_gyp")
    assert hasattr(bcrypt, "system_deps_required")
    assert hasattr(bcrypt, "binary_artifacts_glob")
    assert hasattr(bcrypt, "catalog_entry_version")

def test_ci_providers_loaded():
    import codegenie.catalogs as cat
    assert {"github_actions", "gitlab_ci", "circleci", "jenkins", "azure_pipelines"} <= set(cat.CI_PROVIDERS)
    gha = cat.CI_PROVIDERS["github_actions"]
    assert ".github/workflows" in " ".join(gha.marker_paths)

def test_catalog_version_constants_are_int():
    import codegenie.catalogs as cat
    assert isinstance(cat.NATIVE_MODULES_CATALOG_VERSION, int)
    assert isinstance(cat.CI_PROVIDERS_CATALOG_VERSION, int)

def test_mappingproxy_immutable():
    import codegenie.catalogs as cat
    with pytest.raises(TypeError):
        cat.NATIVE_MODULES["new"] = None  # type: ignore[index]

def test_malformed_yaml_hard_fails(tmp_path, monkeypatch):
    # arrange: point the loader at a malformed file
    bad = tmp_path / "native_modules.yaml"
    bad.write_text(":\n:\n:invalid")
    # use the loader function directly (assume `_load_catalog` is exposed for tests)
    from codegenie.catalogs import _load_catalog, NativeModuleEntry  # type: ignore[attr-defined]
    with pytest.raises(e.CatalogLoadError):
        _load_catalog(bad, NativeModuleEntry, schema_subkey="native_modules")

def test_duplicate_name_hard_fails(tmp_path):
    bad = tmp_path / "native_modules.yaml"
    bad.write_text(
        "catalog_version: 1\n"
        "entries:\n"
        "  - {name: bcrypt, requires_node_gyp: true, system_deps_required: [],"
        "     binary_artifacts_glob: [], notes: '', catalog_entry_version: 1}\n"
        "  - {name: bcrypt, requires_node_gyp: true, system_deps_required: [],"
        "     binary_artifacts_glob: [], notes: '', catalog_entry_version: 1}\n"
    )
    from codegenie.catalogs import _load_catalog, NativeModuleEntry  # type: ignore[attr-defined]
    with pytest.raises(e.CatalogLoadError):
        _load_catalog(bad, NativeModuleEntry, schema_subkey="native_modules")

def test_schema_mismatch_hard_fails(tmp_path):
    bad = tmp_path / "native_modules.yaml"
    bad.write_text("catalog_version: 1\nentries:\n  - {name: bcrypt}\n")  # missing required fields
    from codegenie.catalogs import _load_catalog, NativeModuleEntry  # type: ignore[attr-defined]
    with pytest.raises(e.CatalogLoadError):
        _load_catalog(bad, NativeModuleEntry, schema_subkey="native_modules")
```

Run; confirm `ImportError` / `AttributeError`. Commit as red.

### Green — minimal impl

Implement `_load_catalog` returning `(MappingProxyType, int)`. Use `jsonschema.Draft202012Validator(schema).iter_errors(data)` and raise `CatalogLoadError` with the first error's `json_path`. Duplicate detection: compare `len(entries) == len({e.name for e in entries})`.

Native modules seed: include `bcrypt` (`requires_node_gyp: true`, `system_deps_required: ["libstdc++"]`), `sharp` (`requires_node_gyp: true`, `system_deps_required: ["libvips"]`), etc. Use reasonable values; the catalog is the contract Phase 7 reads — accuracy matters within the Phase-7-relevant fields, but `notes` is freeform.

CI providers seed:
- `github_actions`: `marker_paths: [".github/workflows/*.yml", ".github/workflows/*.yaml"]`, `parser: github_actions`
- `gitlab_ci`: `marker_paths: [".gitlab-ci.yml"]`, `parser: gitlab_ci`
- `circleci`: `marker_paths: [".circleci/config.yml"]`, `parser: circleci`
- `jenkins`: `marker_paths: ["Jenkinsfile"]`, `parser: jenkins`
- `azure_pipelines`: `marker_paths: ["azure-pipelines.yml"]`, `parser: azure_pipelines`

### Refactor — clean up

- Module docstring naming `phase-arch-design.md §"Component design" #10`, ADR-0006 (versioning), production §2.6 (data, not prompts).
- Expose `_load_catalog` for test reuse but prefix with underscore.
- `NamedTuple`'s `system_deps_required` and `binary_artifacts_glob` are typed `tuple[str, ...]` (not `list`) per the data-model section, so they're immutable.
- The structlog `probe.catalog.load` event fires at module import — careful: if tests don't `configure_logging` before import, structlog's default emits to a default stream. Use `structlog.get_logger().info(...)` which is no-op until configured.
- `mypy --strict`: `jsonschema` may need typed stubs (`types-jsonschema`); add to `dev` extras if not present.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/catalogs/__init__.py` | New — loader, NamedTuples, module-level constants |
| `src/codegenie/catalogs/native_modules.yaml` | New — 10 seed entries |
| `src/codegenie/catalogs/ci_providers.yaml` | New — 5 provider entries |
| `src/codegenie/catalogs/_schema.json` | New — JSON Schema Draft 2020-12 for both catalogs |
| `tests/unit/catalogs/__init__.py` | New (empty) |
| `tests/unit/catalogs/test_catalog_loader.py` | New — 7 test cases |
| `pyproject.toml` | Possibly: add `types-jsonschema` under `dev` if needed |

## Out of scope

- **Catalog-driven cache invalidation** — that's exercised in S3-05 (`NodeManifestProbe.declared_inputs` includes `catalogs/native_modules.yaml`) and tested in S3-06's `test_cache_invalidation_scope.py`. This story loads the catalog; it doesn't wire the probe.
- **`probe.catalog.load` event-name constant** — S1-10 registers it as a `Final[str]`. This story emits the literal.
- **More than 10 native-module entries** — the seed is exactly 10. Adding entries is a YAML PR; resist speculative additions (Rule 2).
- **Catalog versioning across releases** — Phase 1 ships `catalog_version: 1`. Bumping is a future PR concern; ADR-0006 names the mechanism.

## Notes for the implementer

- **Hard fail at import time is the load-bearing invariant** (Edge case #9). Don't catch the `CatalogLoadError` inside `catalogs/__init__.py` — let it propagate. The CLI's top-level catch (`cli.unhandled`, Phase 0 S4-02) turns it into exit-code 2.
- **The two catalogs use the same `_schema.json` with two top-level definitions.** Pick a structure: either `_schema.json` has a top-level `oneOf` matching `native_modules` or `ci_providers`, or it has two named `$def`s and the loader picks the right one. The latter is cleaner; pick that.
- **`MappingProxyType` only wraps the top level.** Each `NamedTuple` is intrinsically immutable; tuple fields (`system_deps_required`, `binary_artifacts_glob`) are also immutable because they're tuples. Don't return `list`s — runtime mutation would be possible.
- **`jsonschema.Draft202012Validator`** — Phase 0 already depends on `jsonschema` (Phase 0 S2-05 schema work). Verify the dep is in the closure; don't add a new direct dep.
- **Per Rule 12 (Fail loud):** the loader must never silently fall back to "no entries." If `safe_yaml.load` raises, the catalog is unloaded — re-raise `CatalogLoadError`. Don't set `NATIVE_MODULES = MappingProxyType({})` and emit a warning.
- **Seed catalog values are the contract Phase 7 reads.** The 10 names are non-negotiable. The `requires_node_gyp` and `system_deps_required` values should be accurate to the real packages — look up each on npm/GitHub before committing. If unsure, set `requires_node_gyp: true` (Phase 7 will validate). `notes` can stay short ("Argon2 password hashing; node-gyp build" etc.).
- **Don't add an `enum` for `parser`** in `ci_providers.yaml` schema yet — Phase 4+ may extend the parser set. The Phase 1 sub-schema for `CIProbe` (S4-01) will close the `provider` literal type.
