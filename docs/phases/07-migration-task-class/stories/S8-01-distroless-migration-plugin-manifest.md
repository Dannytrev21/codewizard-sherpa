# Story S8-01 — `plugin.yaml` `PluginManifest` for `distroless-migration--node--npm`

**Step:** Step 8 — `DistrolessMigrationPlugin` manifest + TCCM `derived_queries:` band + plugin loader wiring
**Status:** Ready
**Effort:** S
**Depends on:** S7-04 (`ALLOWED_BINARIES` amendment for `dive` + `docker buildx`), S5-01 (byte-edit allowlist fence exists and authorizes the new plugin directory)
**ADRs honored:** Phase 7 ADR-0001 (no multi-plugin coordinator; the plugin is single-task-class), Phase 7 ADR-0005 (probes live under plugin, manifest is the plugin root), Phase 7 ADR-0009 (the new directory is an additive new file tree; nothing inside Phase 0–6.5 surface is byte-edited), Phase 7 ADR-0015 (the `external_tools` row matches the binaries amendment), production ADR-0031 (plugin manifest shape — `name`, `version`, `scope`, `extends`, `precedence`, `contributes`, `requirements`)

## Context

Phase 7 ships a brand-new task-class plugin tree at `plugins/distroless-migration--node--npm/`. Steps 4 (Alpine + Distroless adapters), 7 (`BaseImageProbe` + `ShellInvocationTraceProbe`), and 9–11 (catalog + recipes + coordination writer) deposit files **under** that tree; this story lays the manifest at the root that names the plugin and pins its scope so the loader (S8-03) and the resolver (S8-04) can find it.

The manifest's `scope` is the single source of truth for resolver routing: `task: distroless-migration`, `language: node`, `build: npm` is the triple that disambiguates this plugin from `vulnerability-remediation--node--npm` (the Phase 3 plugin sharing the `node` + `npm` axes). `precedence: 100` is higher than Phase 3's default (50) — when both plugins technically match a workflow, the resolver picks this one first, and the `Both` provenance variant (S2-04 / S11) is what drives multi-plugin coordination, not precedence collision.

The manifest validates against the existing `PluginManifest` Pydantic schema in `src/codegenie/plugins/manifest.py` — **no schema edits**. The Phase 3 plugin precedent established `extra="forbid"` discipline (`ManifestScope`, `ManifestRequirements`, `PluginManifest` all `frozen=True, extra="forbid"`); any typo in the new manifest surfaces as a typed `SchemaViolation` at load time. The `requirements.external_tools` tuple `(docker, dive, docker-buildx)` mirrors the binaries S7-04 added to `ALLOWED_BINARIES`; the manifest declares what the plugin needs and `ALLOWED_BINARIES` lists what the runtime permits.

The manifest schema field is `name: PluginId` (not `id:`) and `scope: {task_class, languages, build_systems}` (not the shorthand `{task, language, build}`). The READMEs and `final-design.md` use the short labels for prose; this story pins the YAML keys to the actual Pydantic schema names so the manifest loads.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md §Component design §11 (DistrolessMigrationPlugin)`](../phase-arch-design.md) — `id`, `scope`, `precedence`, `extends`, `requirements` shape.
  - [`../phase-arch-design.md §Logical view`](../phase-arch-design.md) — the plugin tree sits parallel to `vulnerability-remediation--node--npm/`.
  - [`../phase-arch-design.md §Physical view`](../phase-arch-design.md) — Filesystem layout under `plugins/distroless-migration--node--npm/`.
- **Phase ADRs:**
  - [`../ADRs/0001-no-multi-plugin-coordinator-in-phase-7.md`](../ADRs/0001-no-multi-plugin-coordinator-in-phase-7.md) — single-task-class plugin is the only thing this manifest names.
  - [`../ADRs/0005-probes-live-under-plugin-not-core-tree.md`](../ADRs/0005-probes-live-under-plugin-not-core-tree.md) — the manifest's `contributes.probes` list (if non-empty) carries probe IDs that live under this directory.
  - [`../ADRs/0009-phase-7-byte-edit-allowlist-fence.md`](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) — the directory is an additive new file tree; nothing in this story edits a locked-file row.
  - [`../ADRs/0015-allowed-binaries-amendment-dive-buildx.md`](../ADRs/0015-allowed-binaries-amendment-dive-buildx.md) — `external_tools` mirrors the amendment.
- **Production ADRs:**
  - [`../../../production/adrs/0031-plugin-architecture.md`](../../../production/adrs/0031-plugin-architecture.md) — plugin manifest schema; production §"Plugin manifest" lines 80–110.
- **High-level impl:**
  - [`../High-level-impl.md §Step 8`](../High-level-impl.md) — Features delivered bullet 1.
- **Source:**
  - [`src/codegenie/plugins/manifest.py`](../../../../src/codegenie/plugins/manifest.py) — `PluginManifest`, `ManifestScope`, `ManifestRequirements`, `ManifestContributes` Pydantic models. Read end-to-end before writing the YAML.
  - Phase 3 plugin tree at `plugins/vulnerability-remediation--node--npm/plugin.yaml` (precedent shape) — confirm the canonical key spellings used in tests.

## Goal

Land `plugins/distroless-migration--node--npm/plugin.yaml` such that:

1. `PluginManifest.from_yaml(path)` returns `Ok(manifest)` with `manifest.name == PluginId("distroless-migration--node--npm")`, `manifest.scope.task_class == "distroless-migration"`, `manifest.scope.languages == "node"`, `manifest.scope.build_systems == "npm"`, `manifest.precedence == 100`, `manifest.extends == ()`, and `manifest.requirements.external_tools == ("docker", "dive", "docker-buildx")`.
2. The manifest loads without any edit to `src/codegenie/plugins/manifest.py` — schema is reused as-is.
3. The byte-edit allowlist fence (S5-01) stays green — the new directory is a brand-new tree; no existing file is byte-edited by this story.
4. A unit test pins the loaded manifest values explicitly so a future typo (`precedance:` for `precedence:`) fails CI as `SchemaViolation`, not as silently-ignored config.

The TCCM, `api.py`, probes, adapters, recipes, and catalog are **out of scope** — they ship in S8-02 / S8-03 / S8-04 / earlier steps (S4, S7).

## Acceptance criteria

### A. Manifest file exists and parses

- [ ] `plugins/distroless-migration--node--npm/plugin.yaml` exists as a new file.
- [ ] The YAML's top-level keys are exactly: `name`, `version`, `scope`, `extends`, `precedence`, `contributes`, `requirements` (the closed set `PluginManifest` allows under `extra="forbid"`).
- [ ] `name: distroless-migration--node--npm` — exact string; matches the directory name.
- [ ] `version: "0.1.0"` (or whatever the Phase 7 plugin first-release convention pins; pick once and assert exact-match in the test).
- [ ] `scope.task_class: distroless-migration` (string, not list).
- [ ] `scope.languages: node` (string, not list).
- [ ] `scope.build_systems: npm` (string, not list).
- [ ] `extends: []` (empty list — the manifest does not extend any parent plugin per Phase 7 ADR-0001).
- [ ] `precedence: 100` — exact integer.
- [ ] `contributes.tccm: "./tccm.yaml"` (the default; this story does not ship the TCCM file but the manifest names it).
- [ ] `contributes.probes: []` (the probes are registered via the decorator in S7-01/S7-02; the manifest's `probes:` list is empty per Phase 7 ADR-0005 §Consequences — registry is the source of truth, not the manifest).
- [ ] `requirements.external_tools: [docker, dive, docker-buildx]` — exact three-tuple in the loaded model.
- [ ] `requirements.optional: []` (empty).

### B. PluginManifest.from_yaml loads cleanly

- [ ] `PluginManifest.from_yaml(Path("plugins/distroless-migration--node--npm/plugin.yaml"))` returns `Ok(manifest)`; no `Err(...)`.
- [ ] `manifest.name == PluginId("distroless-migration--node--npm")` (smart-constructor lift via `parse_plugin_id` succeeds).
- [ ] `manifest.requirements.external_tools == ("docker", "dive", "docker-buildx")` (tuple, frozen, exact element order — Pydantic preserves YAML list order).
- [ ] `manifest.precedence == 100` (not 50 — the default).
- [ ] `manifest.extends == ()` (empty tuple).

### C. Schema-drift guards

- [ ] A test feeds the manifest YAML with a deliberately-planted unknown field (`spurious_field: yes`) into `PluginManifest.from_yaml` and asserts the result is `Err(SchemaViolation(...))` with `field_errors` mentioning the unknown field. This pins `extra="forbid"`.
- [ ] A test feeds the manifest YAML with `precedance: 100` (typo) and asserts `Err(SchemaViolation(...))`. This pins the canonical spelling.
- [ ] A test feeds the manifest YAML with `precedence: -1` and asserts the loader either accepts it (if the schema does not constrain sign) or rejects with `SchemaViolation` — pin whichever the existing schema does, do not relax it.

### D. Byte-edit allowlist fence stays green

- [ ] `pytest tests/fence/test_phase7_no_byte_edits_to_locked_files.py` is green after this story. The fence's row counters are unchanged — this story adds files under a new directory and edits zero locked files.
- [ ] `mypy --strict plugins/distroless-migration--node--npm` (or the equivalent path the project's `[tool.mypy.overrides]` covers) is clean.
- [ ] `ruff check plugins/distroless-migration--node--npm/plugin.yaml` is not applicable (YAML), but `make lint` is green.

### E. No Phase 0–6.5 regression

- [ ] `make check` is green.
- [ ] `make lint-imports` is green.
- [ ] **Phase 3–6.5 regression suite is green** (`bench/vuln-remediation/` cassette replay byte-equal, ε ≤ $0.01).
- [ ] No existing test is deleted, disabled, or marked `xfail`.

## Implementation outline

1. **Read `src/codegenie/plugins/manifest.py` end-to-end** (Rule 8 — Read before you write). Confirm the canonical field names — `name`, `scope.task_class`, `scope.languages`, `scope.build_systems`, `requirements.external_tools`. The README in this phase uses prose-shorthand (`{task, language, build}`); the YAML must use the schema-canonical keys.
2. **Create the directory** `plugins/distroless-migration--node--npm/`. This is the new plugin root.
3. **Write `plugin.yaml`** with the exact keys above. Keep it compact — one block per submodel. No comments inside YAML values; a single header comment naming Phase 7 + ADR-0001 / ADR-0031 is acceptable and matches the Phase 3 precedent.
4. **Write `tests/unit/plugins/distroless_migration_node_npm/test_plugin_manifest.py`** — see TDD plan. Cover ACs A–C exhaustively.
5. **Run `pytest tests/unit/plugins/distroless_migration_node_npm/test_plugin_manifest.py`** — green.
6. **Run `pytest tests/fence/test_phase7_no_byte_edits_to_locked_files.py`** — green; this story should not have triggered any row counter.
7. **Run `make check`** — green.

## TDD plan (red → green → refactor)

### Red — write `tests/unit/plugins/distroless_migration_node_npm/test_plugin_manifest.py` first

```python
"""S8-01 — DistrolessMigrationPlugin manifest loads with the canonical fields."""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.plugins.errors import SchemaViolation
from codegenie.plugins.manifest import PluginManifest
from codegenie.types.identifiers import PluginId

MANIFEST_PATH = Path("plugins/distroless-migration--node--npm/plugin.yaml")


class TestManifestLoads:
    def test_path_exists(self) -> None:
        assert MANIFEST_PATH.is_file()

    def test_loads_ok(self) -> None:
        result = PluginManifest.from_yaml(MANIFEST_PATH)
        assert result.is_ok(), result.error if not result.is_ok() else None

    def test_name(self) -> None:
        manifest = PluginManifest.from_yaml(MANIFEST_PATH).unwrap()
        assert manifest.name == PluginId("distroless-migration--node--npm")

    def test_scope_axes(self) -> None:
        manifest = PluginManifest.from_yaml(MANIFEST_PATH).unwrap()
        assert manifest.scope.task_class == "distroless-migration"
        assert manifest.scope.languages == "node"
        assert manifest.scope.build_systems == "npm"

    def test_precedence_is_100(self) -> None:
        manifest = PluginManifest.from_yaml(MANIFEST_PATH).unwrap()
        # 100 > Phase 3's default 50; resolver tiebreaker picks this plugin.
        assert manifest.precedence == 100

    def test_extends_is_empty(self) -> None:
        manifest = PluginManifest.from_yaml(MANIFEST_PATH).unwrap()
        assert manifest.extends == ()

    def test_external_tools_exact_tuple(self) -> None:
        manifest = PluginManifest.from_yaml(MANIFEST_PATH).unwrap()
        # Order matters — mirrors Phase 7 ADR-0015's binaries amendment.
        assert manifest.requirements.external_tools == ("docker", "dive", "docker-buildx")


class TestSchemaDriftGuards:
    def test_unknown_field_rejected(self, tmp_path: Path) -> None:
        body = MANIFEST_PATH.read_text() + "\nspurious_field: yes\n"
        bad = tmp_path / "plugin.yaml"
        bad.write_text(body)
        result = PluginManifest.from_yaml(bad)
        assert result.is_err()
        assert isinstance(result.error, SchemaViolation)
        # extra='forbid' surfaces the field name in field_errors.
        assert any("spurious_field" in str(loc) for loc in result.error.field_errors)

    def test_precedence_typo_rejected(self, tmp_path: Path) -> None:
        body = MANIFEST_PATH.read_text().replace("precedence:", "precedance:")
        bad = tmp_path / "plugin.yaml"
        bad.write_text(body)
        result = PluginManifest.from_yaml(bad)
        assert result.is_err()
        assert isinstance(result.error, SchemaViolation)
```

Run — fails because `plugin.yaml` does not exist yet. That's red.

### Green — minimum implementation

Create `plugins/distroless-migration--node--npm/plugin.yaml` with the canonical keys. Re-run; all tests pass.

### Refactor

Re-read the YAML against `manifest.py` once more; confirm no spurious whitespace, no `null` defaults written explicitly where the schema default suffices. Keep it compact.

## Files to touch

- `plugins/distroless-migration--node--npm/plugin.yaml` — new file (the plugin manifest).
- `tests/unit/plugins/distroless_migration_node_npm/test_plugin_manifest.py` — new test file.
- `tests/unit/plugins/distroless_migration_node_npm/__init__.py` — new (empty) test package marker if the project uses package-style test dirs.

## Out of scope

- The TCCM (`tccm.yaml`) and its `derived_queries:` entry — **S8-04** owns the YAML; **S8-02** owns the `DerivedQuery` schema.
- The plugin's `api.py` (`register_plugin(...)` side-effect, adapter/probe/recipe imports) — **S8-03**.
- The `chainguard_image_recommendation_table.yaml` catalog and its loader — **Step 9** (S9-01).
- The `PLUGINS.lock` row for this plugin — **S5-04**.
- Editing `src/codegenie/plugins/manifest.py` — schema is reused; any edit is a fence failure under S5-01.

## Notes for the implementer

- **Schema field-name reality check:** the schema names are `task_class`, `languages`, `build_systems` — NOT `task`, `language`, `build`. The Phase 7 README + final-design use prose shorthand; the YAML must spell the canonical Pydantic field names or `PluginManifest.from_yaml` returns `Err(SchemaViolation)`.
- **`name` not `id`:** the schema field is `name: PluginId` (`src/codegenie/plugins/manifest.py` line 222). The README and prose use "id"; the YAML key is `name`. This is the same kind of prose-vs-schema gap that `precedance:` typos exploit — fence it explicitly with AC-C.
- **`contributes.probes` is empty by design:** S7-01 and S7-02 register `BaseImageProbe` and `ShellInvocationTraceProbe` via the `@register_probe` decorator at import time (Phase 7 ADR-0005). Repeating them in the manifest is redundant and risks drift. Phase 3's precedent leaves it empty; mirror that.
- **`version: "0.1.0"`** is a reasonable seed. If the Phase 3 plugin shipped a different first-release string, match it (Rule 11 — match the codebase's conventions). Pin the exact string in AC-A so a future bump is an explicit edit, not a silent drift.
- **No `description:` field exists** under `extra="forbid"`. If you want narrative context, put it in a top-of-file YAML comment; do not invent a `description:` key.
- **Do not import the plugin from `src/codegenie/plugins/loader.py` in this story** — the explicit-import line is allowlist row #7 (S5-01's enumeration) and S8-03 owns it. Adding it here trips the fence on the wrong story.
- **`make lint-imports` interaction:** the import-linter contract Phase 7 plants (S1-06 + S5-03) bars LLM SDKs from the plugin tree. This story's YAML does not import anything; the contract is irrelevant here, but the inherited green status is part of "no Phase 0–6.5 regression."
- **`PLUGINS.lock` and the directory-hash fence:** S5-04 (Step 5) ships the `PLUGINS.lock` entry. Until that lands, the plugin loader will reject this plugin as `UnlockedPlugin`. That is **expected**; this story only proves manifest-shape correctness via direct `PluginManifest.from_yaml(...)` — it does not exercise the full `load_plugins()` path. S8-03's integration test (post-S5-04) closes the loop.
