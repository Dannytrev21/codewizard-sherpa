# Story S2-02 — `PluginManifest` Pydantic model + YAML loader returning `Result`

**Step:** Step 2 — Plugin Registry kernel, manifest schema, loader, resolver
**Status:** Ready
**Effort:** S
**Depends on:** S2-01
**ADRs honored:** ADR-0002, ADR-0004, ADR-0010, ADR-0011, production ADR-0031

## Context

Every plugin under `plugins/{slug}/` carries a `plugin.yaml` whose shape is fixed by production ADR-0031 §Plugin manifest. Phase 3 ships the **typed loader** for that file: a frozen Pydantic `PluginManifest` model with `extra="forbid"` (so a typo in a manifest field surfaces as a parse error at load time, not as silent ignored config), and a `PluginManifest.from_yaml(path) -> Result[PluginManifest, ManifestError]` smart constructor that returns the discriminated `Ok`/`Err` from `codegenie.result.Result` rather than raising. This story lands the **schema + loader only** — the filesystem walk that *finds* manifests and the integrity-check that *verifies* the surrounding tree are S2-03; the resolver that consumes `scope`/`precedence`/`extends` is S2-04.

The manifest is also the place ADR-0004's discipline lands at the data level: the `contributes.tccm` reference points to the plugin's `tccm.yaml`, where task-class-specific capabilities (`provides.vuln_index_capabilities`, etc.) live — **not** on the kernel `Plugin` Protocol. ADR-0011 says `signature` is honest-framing-relabeled as an integrity check; we keep the manifest field shape but document it as such and stub it as an optional placeholder (Phase 11 substitutes Sigstore verification at the loader, not at the manifest).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C2` — `Plugin.manifest: PluginManifest` is the typed attribute.
  - `../phase-arch-design.md §Data model` — `PluginManifest` schema rows (`name`, `version`, `scope`, `extends`, `precedence`, `contributes.{adapters,tccm,subgraph,skills,recipes}`, `requirements.external_tools`, `signature` stub).
  - `../phase-arch-design.md §Edge cases` — malformed YAML rejection; unknown-field rejection (`extra="forbid"`).
- **Phase ADRs:**
  - `../ADRs/0002-plugin-registry-kernel-instance-with-default-singleton.md` — ADR-0002 — manifest validation is **a loader concern, not a registry one** ("Keep [the registry] dumb; validate on use").
  - `../ADRs/0004-plugin-private-capabilities-via-tccm.md` — ADR-0004 — `contributes.tccm` references the plugin's TCCM file; capability namespaces live there, not in the manifest.
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — ADR-0011 — the `signature` field is honest-framed as "future Sigstore hook" placeholder; do not over-claim.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` §Plugin manifest — the canonical YAML shape; ship every documented field.
- **Existing code:**
  - `src/codegenie/result.py` — the `Result` sum type; pattern (`from codegenie.result import Result, Ok, Err`).
  - `src/codegenie/tccm/loader.py` (if present) or any S1-04 partial-success loader — pattern for `from_yaml(path) -> Result[T, E]` per-file errors.
  - `src/codegenie/types/identifiers.py` — `PluginId`, `RegistryUrl`; never raw `str`.
  - `src/codegenie/plugins/registry.py` — the `Plugin` Protocol's `manifest` attribute references this model.

## Goal

Ship `PluginManifest` (frozen, `extra="forbid"`) covering every ADR-0031 manifest field, plus `PluginManifest.from_yaml(path) -> Result[PluginManifest, ManifestError]` that loads YAML safely (1 MiB cap; `yaml.safe_load`), validates via Pydantic, and returns `Result` rather than raising.

## Acceptance criteria

- [ ] `src/codegenie/plugins/manifest.py` exports `PluginManifest`, `ManifestScope`, `ManifestContributes`, `ManifestRequirements`, `ManifestError`. All Pydantic models are `frozen=True, extra="forbid"`.
- [ ] `PluginManifest` covers: `name: PluginId`, `version: str` (PEP-440-ish, validate non-empty), `scope: ManifestScope` (`task_class`, `languages`, `build_systems` — each is `str | list[str]` where `"*"` is the wildcard literal; sum-type lift to `PluginScope` happens in S2-04, not here), `extends: list[PluginId] = []`, `precedence: int = 50`, `contributes: ManifestContributes`, `requirements: ManifestRequirements = ManifestRequirements()`, `signature: str | None = None` (ADR-0011 stub).
- [ ] `ManifestContributes` covers: `adapters: dict[str, str] = {}` (primitive→`module:Class`), `tccm: str = "./tccm.yaml"` (relative path string), `subgraph: str = "./subgraph/"`, `skills: str = "./skills/"`, `recipes: str = "./recipes/"`, `probes: list[str] = []`.
- [ ] `PluginManifest.from_yaml(path) -> Result[PluginManifest, ManifestError]` reads the file (1 MiB hard cap → `Err(ManifestError(reason="size_cap_exceeded"))`), runs `yaml.safe_load` (`yaml.YAMLError` → `Err(ManifestError(reason="malformed_yaml", detail=...))`), validates via Pydantic (`ValidationError` → `Err(ManifestError(reason="schema_violation", detail=...))`), returns `Ok(manifest)` on success. **Never raises** for any of these failure modes.
- [ ] Round-trip test: hand-built `PluginManifest(...)`, `model_dump_json()` → write to tmp → `from_yaml(...)` → `Ok` with byte-identical reconstruction.
- [ ] Unknown-field test: YAML with `precedance: 50` (typo) → `Err(ManifestError(reason="schema_violation"))` (`extra="forbid"` enforced).
- [ ] `signature` is documented as honest-framed (ADR-0011): allowed but ignored in Phase 3; Phase 11 Sigstore substitutes the verifier (not this loader).
- [ ] TDD red test (`test_unknown_field_returns_err`) committed and green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` clean on `src/codegenie/plugins/manifest.py` and the new tests.

## Implementation outline

1. Define `ManifestScope`, `ManifestContributes`, `ManifestRequirements` Pydantic submodels. Each: `model_config = ConfigDict(frozen=True, extra="forbid")`. Use `Annotated[str, AfterValidator(...)]` for non-empty constraints.
2. Define `PluginManifest`: top-level model composing the submodels.
3. Define `ManifestError`: frozen Pydantic with `reason: Literal["size_cap_exceeded","malformed_yaml","schema_violation","io_error"]` + `detail: str` + `path: Path | None`.
4. Implement `from_yaml(cls, path: Path) -> Result[PluginManifest, ManifestError]`:
   - `path.stat().st_size > 1 << 20` → `Err(ManifestError(reason="size_cap_exceeded"))`.
   - `with path.open("rb") as f: raw = f.read()` — catch `OSError` → `Err(reason="io_error")`.
   - `yaml.safe_load(raw)` — catch `yaml.YAMLError` → `Err(reason="malformed_yaml")`.
   - `PluginManifest.model_validate(data)` — catch `pydantic.ValidationError` → `Err(reason="schema_violation", detail=str(e))`.
   - Else `Ok(manifest)`.
5. Tests:
   - Red: unknown-field rejection.
   - Round-trip: build manifest → dump YAML → load YAML → assert equality.
   - Malformed YAML (e.g., unbalanced braces) returns `Err`.
   - Size cap (synthesize 1.5 MiB file) returns `Err`.
   - I/O error (point at missing path) returns `Err`.
   - `extends`, `precedence`, `signature` round-trip with defaults.

## TDD plan — red / green / refactor

### Red — failing test first

Test file path: `tests/unit/plugins/test_manifest.py`

```python
from pathlib import Path

from codegenie.plugins.manifest import ManifestError, PluginManifest


def test_unknown_field_returns_err(tmp_path: Path):
    """`extra="forbid"` is the load-bearing schema discipline (ADR-0002 §Pattern fit
    + ADR-0031 §Schema enforcement). A typo in `precedence` must not silently
    fall back to the default — it must surface as a typed Err at load time."""
    path = tmp_path / "plugin.yaml"
    path.write_text(
        """
        name: vulnerability-remediation--node--npm
        version: 0.1.0
        scope:
          task_class: vulnerability-remediation
          languages: [javascript]
          build_systems: [npm]
        precedance: 50   # typo — should NOT be silently accepted
        contributes:
          tccm: ./tccm.yaml
        """,
        encoding="utf-8",
    )

    result = PluginManifest.from_yaml(path)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, ManifestError)
    assert err.reason == "schema_violation"
    assert "precedance" in err.detail
```

Why it fails: `codegenie.plugins.manifest` doesn't exist yet; the models / `from_yaml` are not defined.

### Green — minimal pass

- Implement the Pydantic models with `extra="forbid"`.
- Implement `from_yaml` with the four-error-mode try/except chain returning `Result`.

### Refactor

- Pull the YAML-read helper into a small `_read_capped_bytes(path, cap)` so the size cap reads cleanly.
- Use `pydantic.ValidationError.errors()` to extract a structured detail string (preserves which field violated).
- Add property test (optional, low priority): for any valid manifest dict, round-trip preserves equality.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/plugins/manifest.py` | `PluginManifest` + submodels + `from_yaml` + `ManifestError`. |
| `tests/unit/plugins/test_manifest.py` | TDD red + round-trip + every error-mode case. |
| `tests/fixtures/plugins/sample_plugin_yaml.py` | Helper to write valid + invalid YAML fixtures into `tmp_path`. |

## Out of scope

- **Filesystem walk over `plugins/*/plugin.yaml`** — handled by S2-03.
- **`PLUGINS.lock` integrity check** — handled by S2-03 (the manifest loader is purely about a single YAML file).
- **Sum-type lift `scope: dict → PluginScope`** — handled by S2-04. Here `scope.task_class` etc. are still raw `str | list[str]`.
- **`extends`-chain walking / cycle detection** — handled by S2-04. Here `extends` is just a `list[PluginId]`.
- **`signature` verification** — Phase 11 (Sigstore). The field exists; nobody reads it in Phase 3.
- **TCCM loader (`tccm.yaml` parsing)** — Step 3.

## Notes for the implementer

- Use `yaml.safe_load`. Do **not** import `yaml.Loader` or `yaml.FullLoader`; the project's `forbidden-patterns` pre-commit hook will catch unsafe loaders, but flag it now rather than waiting for CI.
- The 1 MiB cap (`1 << 20`) matches the existing convention from Phase 2 ingest parsers (S3-03 uses the same cap for CVE records). Cite the precedent in a comment.
- `Result` over raising: this is the pattern the rest of Phase 2/3 uses (`codegenie.result`, S1-04 `TCCMLoader`). A reviewer expecting `try/except FileNotFoundError` would be surprised — the docstring should call out "never raises; always returns `Result`".
- `name: PluginId` — when validating the loaded YAML, lift `str → PluginId` via the S1-01 smart constructor; route failure into `Err(reason="schema_violation")`. Don't `cast()`; that defeats the newtype discipline.
- The `signature` field stub: do **not** add validation logic ("must be 64 hex chars"). Leave it as `str | None` and document that Phase 11 substitutes the verifier. ADR-0011's honest-framing point is exactly that this field is decorative in Phase 3.
- `precedence: int = 50` — match the default from production ADR-0031 §Plugin manifest example. Tests that assert default behavior should pin `50` explicitly.
- The `extends: list[PluginId]` list at the manifest level is unvalidated for cycles here — cycle detection is a *resolver* concern (S2-04). Conflating loader and resolver responsibilities is the exact failure mode ADR-0002 §Pattern fit warns against.
