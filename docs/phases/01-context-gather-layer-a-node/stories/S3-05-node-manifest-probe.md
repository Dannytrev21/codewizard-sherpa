# Story S3-05 — `NodeManifestProbe` + sub-schema + native-module catalog cross-reference

**Step:** Step 3 — Ship `NodeManifestProbe` and the three lockfile parsers
**Status:** Ready
**Effort:** L
**Depends on:** S3-01 (`_pnpm`), S3-02 (`_npm`), S3-03 (`_yarn`), S1-05 (`catalogs.NATIVE_MODULES`), S1-09 (`declared_raw_artifact_budget_mb`)
**ADRs honored:** ADR-0004 (per-probe sub-schema `additionalProperties: false`), ADR-0006 (native-module catalog versioning via `declared_inputs`), ADR-0007 (warning-ID pattern), ADR-0011 (no `npm ls` / no Helm render)

## Context

`NodeManifestProbe` is **the load-bearing Phase 1 probe for Phase 7** (Chainguard distroless migration). Its job: parse `package.json` + the single canonical lockfile, cross-reference resolved dependencies against `catalogs/native_modules.yaml`, and produce a `manifests` slice with a `native_modules` block that Phase 7 reads to decide which Chainguard image layer to inherit and which system deps to install. The seam this probe creates — "data-as-code catalog cross-reference, no LLM, no `npm ls`" — is what makes Phase 7's distroless migration deterministic six phases later.

The probe is also the first one in Phase 1 to override the default raw-artifact budget. Real `pnpm-lock.yaml` files can hit 20 MB on monorepos; the parsed dump (stored under `.codegenie/context/raw/node_manifest.json`) needs to fit. The default 5 MB cap from S1-09 is too tight; this probe overrides to 25 MB. Budgets > 50 MB would require an ADR amendment.

ADR-0006's invariant is critical: `native_modules.yaml` is in `declared_inputs` so editing the catalog invalidates `node_manifest` cache entries at the file-bytes level. The cross-phase invalidation story (Phase 7 catalog update triggers a fleet-wide re-gather) depends on this.

This is the densest probe in Phase 1 and the second-largest LOC contribution (after S4-02's `DeploymentProbe`). Plan a focused PR with the schema, the probe, the unit test, and nothing else — fixtures + integration land in S3-06.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #4 NodeManifestProbe` — full interface spec; the contract for this story.
  - `../phase-arch-design.md §"Data model"` — `ManifestsSlice`, `ManifestEntry`, `NativeModulesBlock`, `NativeModuleHit` Pydantic-shaped definitions.
  - `../phase-arch-design.md §"Edge cases"` rows 1–4, 8 — pnpm depth-cap, multi-lockfile, catalog gap behaviors.
  - `../phase-arch-design.md §"Gap analysis" Gap 2` — raw-artifact budget mechanism (S1-09); exercised here at 25 MB.
- **Phase ADRs:**
  - `../ADRs/0004-per-probe-subschema-additional-properties-false.md` — `additionalProperties: false` at sub-schema root + every nested block.
  - `../ADRs/0006-native-module-catalog-versioning.md` — file-level cache invalidation via `declared_inputs`.
  - `../ADRs/0007-warnings-id-pattern.md` — `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` for warning IDs (`lockfile.multi_present`, etc.).
  - `../ADRs/0011-no-helm-render-no-hcl-no-npm-ls.md` — explicit "no `npm ls`" for this probe.
- **Production ADRs:**
  - `../../../production/adrs/0006-continuous-deterministic-gather.md` — the continuous-gather story Phase 7 depends on; clean cache invalidation is the load-bearing contract.
- **Source design:**
  - `../final-design.md §"Components" #4` — provenance attribution (`[B + S + synth]`).
  - `../final-design.md §"Risks"` #1 — silent catalog staleness; the structural mitigation is this probe + ADR-0006.
  - `../High-level-impl.md §"Step 3"` — features delivered + done criteria for this probe.
- **Existing code:**
  - `src/codegenie/probes/base.py` — `Probe` ABC, `ProbeContext` (extended in S1-06 with `parsed_manifest` + `input_snapshot`).
  - `src/codegenie/parsers/safe_json.py`, `safe_yaml.py` — used directly for `package.json` parse fallback.
  - `src/codegenie/probes/_lockfiles/_pnpm.py`, `_npm.py`, `_yarn.py` — from S3-01/02/03.
  - `src/codegenie/catalogs/__init__.py` — `NATIVE_MODULES`, `NATIVE_MODULES_CATALOG_VERSION` from S1-05.
  - `src/codegenie/schema/probes/_subschema_convention.md` — from S1-10; the `additionalProperties: false` pattern.
  - `src/codegenie/schema/probes/language_detection.schema.json`, `node_build_system.schema.json` — from S2-01, S2-02 — reference for sub-schema shape.

## Goal

Ship `NodeManifestProbe`, its sub-schema, and the native-module catalog cross-reference so `codegenie gather` on a Node repo produces a valid `manifests` slice with `native_modules.detected` correctly set, multi-lockfile drops `confidence` to `low`, and editing `native_modules.yaml` invalidates only this probe's cache.

## Acceptance criteria

- [ ] `src/codegenie/probes/node_manifest.py` defines `NodeManifestProbe(Probe)` with `name = "node_manifest"`, `layer = "A"`, `tier = "base"`, `applies_to_languages = ["javascript", "typescript"]`, `applies_to_tasks = ["*"]`, `requires = ["language_detection"]`, `timeout_seconds = 30`, `version = "0.1.0"`, `declared_inputs = ["package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock", "src/codegenie/catalogs/native_modules.yaml"]`, `declared_raw_artifact_budget_mb = 25`.
- [ ] `declared_inputs` **does NOT** include `node_modules/**` (per `phase-arch-design.md §"Component design" #4`); a unit test pins this absence.
- [ ] `run(snapshot, ctx)` reads `package.json` via `ctx.parsed_manifest(repo_root / "package.json")` (memo path) and falls back to direct `safe_json.load` if `ctx.parsed_manifest` is `None`.
- [ ] Lockfile selection by precedence (existence-check, no parse-for-selection): `pnpm-lock.yaml` > `package-lock.json` > `yarn.lock`. (Per Phase 1's load-bearing slice; `bun.lockb` is detected by `NodeBuildSystemProbe` but not parsed by this probe.)
- [ ] Multiple lockfiles present → `confidence: low`, `warnings: ["lockfile.multi_present"]`; the selected lockfile per precedence is still parsed.
- [ ] On any lockfile parser raising `SizeCapExceeded` / `DepthCapExceeded` / `MalformedLockfileError` / `SymlinkRefusedError`, the probe catches and emits `ProbeOutput(confidence="low", errors=[<typed id>])`; **gather continues**.
- [ ] Native-module catalog cross-reference: for each entry in `NATIVE_MODULES`, check whether the resolved dependency set from the lockfile contains it. If yes, populate `NativeModuleHit(name, version, requires_node_gyp, system_deps_required, binary_artifacts_glob, catalog_entry_version)` from the catalog entry. `native_modules.detected` is `True` iff `len(packages) > 0`.
- [ ] `manifests.catalog_version: int` field populated from `NATIVE_MODULES_CATALOG_VERSION`.
- [ ] `optionalDependencies` and `bundledDependencies` are read from `package.json` and surfaced as `optional_dependencies: int` (count) and `bundled_dependencies: list[str]` per `phase-arch-design.md §"Data model"`.
- [ ] Sub-schema `src/codegenie/schema/probes/node_manifest.schema.json` (JSON Schema Draft 2020-12) sets `additionalProperties: false` at root **and at every nested block** (`primary`, `lockfile`, `native_modules`, each `NativeModuleHit`, `direct_dependencies`).
- [ ] Sub-schema declares each warning ID under `warnings[]` with `pattern: "^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$"` (ADR-0007).
- [ ] `src/codegenie/probes/__init__.py` is edited additively to register `NodeManifestProbe` via explicit import (one-line additive edit; ADR-gated by extension-by-addition).
- [ ] An `additionalProperties: false` rejection test exists: a synthetic envelope with an extra field in `probes.node_manifest` raises `SchemaValidationError` at the correct JSON Pointer (per the cross-cutting convention).
- [ ] A unit test asserts that `declared_inputs` contains `"src/codegenie/catalogs/native_modules.yaml"` (the ADR-0006 invariant; cache invalidation depends on it).
- [ ] No call to `npm ls`, `pnpm list`, `yarn list`, or any subprocess invocation for dep resolution (ADR-0011); a unit test monkeypatches `subprocess.run` and asserts it's never called.
- [ ] TDD red test exists, was committed red, now green; happy-path probe-output assertion + multi-lockfile downgrade + catalog-hit detection all covered.
- [ ] `ruff format --check`, `ruff check`, `mypy --strict`, full unit test suite all pass.
- [ ] Per-probe local coverage report ≥ 90 / 80 (line / branch) included in PR body (per cross-cutting convention).

## Implementation outline

1. **Ship the sub-schema first** — `node_manifest.schema.json` with `additionalProperties: false` at root + every nested block. Adapt from `phase-arch-design.md §"Data model"`'s Pydantic definitions; use Draft 2020-12; `$ref` `ManifestEntry`, `NativeModulesBlock`, `NativeModuleHit` as named definitions. Registering it in the envelope is unchanged-pattern from S2-01/S2-02.
2. **Write the failing test** — see TDD plan.
3. **Implement `node_manifest.py`**:
   - Static class attributes per the acceptance criteria.
   - `run(snapshot, ctx)`: read `package.json` (memo + fallback); detect lockfile presence (precedence list, `Path.exists()`); parse the selected lockfile; reconcile resolved deps into a flat `dict[str, str]` of `name → version`; cross-reference against `NATIVE_MODULES`; assemble `manifests` slice.
   - Build the `manifests` slice as a plain `dict[str, Any]` (Phase 0 convention; Pydantic validation lives in `_ProbeOutputValidator`).
   - Emit warnings via list of strings matching the ADR-0007 pattern.
   - Handle multi-lockfile via the warnings list + `confidence: low`.
   - On parser exception, catch into `ProbeOutput(confidence="low", errors=[…])`.
4. **Write the raw-artifact dump**: serialize the parsed lockfile to `.codegenie/context/raw/node_manifest.json` via the coordinator's raw-artifact write path; the `declared_raw_artifact_budget_mb = 25` class attribute caps it.
5. **Register the probe** — explicit import in `src/codegenie/probes/__init__.py`.
6. **Run the test suite** + local coverage.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/probes/test_node_manifest.py`.

```python
# tests/unit/probes/test_node_manifest.py
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from codegenie.probes.node_manifest import NodeManifestProbe


def _build_repo(tmp_path: Path, *, pnpm_lock: bool = False, npm_lock: bool = False,
                yarn_lock: bool = False, deps: dict[str, str] | None = None) -> Path:
    (tmp_path / "package.json").write_text(
        '{"name":"x","version":"1.0.0","dependencies":'
        + str(deps or {}).replace("'", '"')
        + "}"
    )
    if pnpm_lock:
        (tmp_path / "pnpm-lock.yaml").write_text(
            f"lockfileVersion: '9.0'\npackages:\n  /bcrypt@5.1.1: {{}}\n"
            if deps and "bcrypt" in deps else "lockfileVersion: '9.0'\npackages: {}\n"
        )
    if npm_lock:
        (tmp_path / "package-lock.json").write_text(
            '{"lockfileVersion":3,"packages":{"node_modules/bcrypt":{"version":"5.1.1"}}}'
            if deps and "bcrypt" in deps else '{"lockfileVersion":3,"packages":{}}'
        )
    if yarn_lock:
        (tmp_path / "yarn.lock").write_text(
            'bcrypt@^5.1.0:\n  version "5.1.1"\n' if deps and "bcrypt" in deps else "# empty\n"
        )
    return tmp_path


def test_probe_attributes_pin_contract():
    p = NodeManifestProbe()
    assert p.name == "node_manifest"
    assert p.declared_raw_artifact_budget_mb == 25
    # ADR-0006: catalog YAML must be in declared_inputs for cache invalidation.
    assert "src/codegenie/catalogs/native_modules.yaml" in p.declared_inputs
    # node_modules NOT declared.
    assert not any("node_modules" in inp for inp in p.declared_inputs)


@pytest.mark.asyncio
async def test_happy_path_pnpm_with_bcrypt(tmp_path: Path):
    repo = _build_repo(tmp_path, pnpm_lock=True, deps={"bcrypt": "^5.1.0"})
    ctx = MagicMock()
    ctx.parsed_manifest = None  # exercise the fallback path
    snapshot = MagicMock(root=repo)
    p = NodeManifestProbe()
    out = await p.run(snapshot, ctx)
    assert out.confidence == "high"
    assert out.data["manifests"]["primary"]["native_modules"]["detected"] is True
    pkgs = out.data["manifests"]["primary"]["native_modules"]["packages"]
    assert any(pkg["name"] == "bcrypt" for pkg in pkgs)


@pytest.mark.asyncio
async def test_multi_lockfile_drops_confidence(tmp_path: Path):
    repo = _build_repo(tmp_path, pnpm_lock=True, npm_lock=True, deps={"x": "^1"})
    ctx = MagicMock(); ctx.parsed_manifest = None
    snapshot = MagicMock(root=repo)
    out = await NodeManifestProbe().run(snapshot, ctx)
    assert out.confidence == "low"
    assert "lockfile.multi_present" in out.warnings


@pytest.mark.asyncio
async def test_no_subprocess_for_dep_resolution(tmp_path: Path, monkeypatch):
    import subprocess
    calls: list = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)))
    repo = _build_repo(tmp_path, pnpm_lock=True, deps={"x": "^1"})
    ctx = MagicMock(); ctx.parsed_manifest = None
    await NodeManifestProbe().run(MagicMock(root=repo), ctx)
    assert calls == []  # ADR-0011: no npm ls, no subprocess.


@pytest.mark.asyncio
async def test_oversized_lockfile_degrades_gracefully(tmp_path: Path):
    repo = _build_repo(tmp_path, pnpm_lock=True, deps={"x": "^1"})
    (repo / "pnpm-lock.yaml").write_bytes(b"a: b\n" * (60 * 1024 * 1024 // 5))
    ctx = MagicMock(); ctx.parsed_manifest = None
    out = await NodeManifestProbe().run(MagicMock(root=repo), ctx)
    assert out.confidence == "low"
    assert any("size_cap" in e or "size" in e for e in out.errors)
```

Confirm collection error. Commit red.

### Green — make it pass

Sketch (full implementation is too long for the story; the key shape):

```python
# src/codegenie/probes/node_manifest.py
from pathlib import Path
from typing import Any, Mapping

from codegenie.catalogs import NATIVE_MODULES, NATIVE_MODULES_CATALOG_VERSION
from codegenie.errors import (
    DepthCapExceeded, MalformedLockfileError, SizeCapExceeded, SymlinkRefusedError,
)
from codegenie.parsers import safe_json
from codegenie.probes._lockfiles import _npm, _pnpm, _yarn
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot


class NodeManifestProbe(Probe):
    name = "node_manifest"
    version = "0.1.0"
    layer = "A"
    tier = "base"
    applies_to_languages = ["javascript", "typescript"]
    applies_to_tasks = ["*"]
    requires = ["language_detection"]
    timeout_seconds = 30
    declared_inputs = [
        "package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock",
        "src/codegenie/catalogs/native_modules.yaml",
    ]
    declared_raw_artifact_budget_mb = 25

    async def run(self, snapshot: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        root = snapshot.root
        warnings: list[str] = []
        errors: list[str] = []
        confidence: str = "high"

        # package.json via memo + fallback
        pkg = self._read_package_json(root, ctx, errors)
        if pkg is None:
            return ProbeOutput(
                data={"manifests": None}, confidence="low",
                errors=errors, warnings=warnings,
            )

        # Lockfile selection by precedence.
        lockfiles_present = [
            name for name in ("pnpm-lock.yaml", "package-lock.json", "yarn.lock")
            if (root / name).exists()
        ]
        if len(lockfiles_present) > 1:
            warnings.append("lockfile.multi_present")
            confidence = "low"
        selected = lockfiles_present[0] if lockfiles_present else None

        resolved_deps: dict[str, str] = {}
        if selected:
            try:
                resolved_deps = self._parse_lockfile(root / selected, selected)
            except (SizeCapExceeded, DepthCapExceeded,
                    MalformedLockfileError, SymlinkRefusedError) as e:
                errors.append(self._error_id(selected, e))
                confidence = "low"

        # Native-module catalog cross-reference.
        native_hits = self._cross_reference_native_modules(resolved_deps)

        slice_data = {
            "manifests": {
                "primary": {
                    "path": "package.json",
                    "direct_dependencies": {
                        "runtime": len(pkg.get("dependencies", {})),
                        "dev": len(pkg.get("devDependencies", {})),
                    },
                    "declared_engines": pkg.get("engines", {}),
                    "lockfile": {"name": selected} if selected else None,
                    "native_modules": {
                        "detected": len(native_hits) > 0,
                        "packages": native_hits,
                    },
                    "optional_dependencies": len(pkg.get("optionalDependencies", {})),
                    "bundled_dependencies": list(pkg.get("bundledDependencies", [])),
                },
                "catalog_version": NATIVE_MODULES_CATALOG_VERSION,
                "warnings": warnings,
            }
        }
        return ProbeOutput(
            data=slice_data, confidence=confidence,
            errors=errors, warnings=warnings,
        )

    # ... helpers: _read_package_json, _parse_lockfile (dispatch on filename),
    #     _cross_reference_native_modules, _error_id (maps exception → ADR-0007 ID).
```

The `_parse_lockfile` dispatch reconciles the format-specific `TypedDict` into a flat `name → version` mapping; that's the only place format-asymmetry lives.

### Refactor

- The dep-flattening logic (parse-format-specific shapes → `dict[str, str]`) is one helper per lockfile format inside this module. Don't push them into `_lockfiles/_pnpm.py` etc. — that would violate the "parsers are shape-faithful" boundary from S3-01.
- The warning-ID strings (`"lockfile.multi_present"`, `"pnpm_lock.depth_cap_exceeded"`, etc.) are module-level constants for grep-ability.
- Resist the temptation to add a `commands` sub-key under `manifests` (that's `build_system`'s job — see `NodeBuildSystemProbe` from S2-02).
- The raw-artifact dump (serialized parsed lockfile) writes via the coordinator's raw-artifact channel — no `Path.write_text` calls from inside this probe.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/node_manifest.py` | New file — `NodeManifestProbe` implementation. |
| `src/codegenie/schema/probes/node_manifest.schema.json` | New file — `additionalProperties: false` at root + every nested block. |
| `src/codegenie/probes/__init__.py` | Edit — additive import + registry entry for `NodeManifestProbe`. |
| `tests/unit/probes/test_node_manifest.py` | New file — five-path unit test (contract, happy, multi-lockfile, no-subprocess, oversized). |

## Out of scope

- **Fixtures `node_pnpm_native/`, `node_yarn_legacy/` + integration tests** — S3-06.
- **`tests/unit/test_cache_invalidation_scope.py` extension for the catalog-edit case** — S3-06 (it co-locates with the fixtures that demonstrate the scope).
- **`probe.raw_artifact.truncated` event assertion on a 30 MB synthetic lockfile** — S3-06 (the synthetic fixture is the size-cap exercise).
- **`bun.lockb` parsing** — out of scope for Phase 1 entirely (binary format); `NodeBuildSystemProbe` detects but does not parse.
- **Workspace traversal for monorepos** — `manifests` slice covers the root `package.json` only in Phase 1; workspace expansion is Phase 2's concern (`High-level-impl.md "What's next"`).
- **`overrides` / `resolutions` field handling** — surfaced verbatim, not interpreted (Phase 3+ planner's job).

## Notes for the implementer

- **Per-probe local coverage ≥ 90 / 80 is required in PR body** per cross-cutting convention #6. If the coverage is borderline, write the missing-branch tests in this PR rather than pushing into S6-02.
- The `additionalProperties: false` rejection test belongs in this PR per cross-cutting convention #5 — name a representative subset of synthetic envelopes (root-level extra field, nested in `primary`, nested in `native_modules.packages[0]`) and assert the JSON Pointer the validator returns.
- The `subprocess.run` monkeypatch test is load-bearing for ADR-0011. If a future contributor adds `npm ls` "for richer resolution," this test fails first. Keep the assertion explicit: `assert calls == []`, not `assert len(calls) == 0`.
- ADR-0006's cache-invalidation invariant is encoded in `declared_inputs`. The unit test for it (`test_probe_attributes_pin_contract`) is tiny but load-bearing — Phase 7 depends on it. Do not change `declared_inputs` without surfacing the ADR-0006 reference in the PR.
- The `_error_id(selected, e)` helper maps `(lockfile_filename, exception_type) → "pnpm_lock.size_cap_exceeded"` etc., respecting the ADR-0007 pattern. The full ID list:
  - `pnpm_lock.size_cap_exceeded`, `pnpm_lock.depth_cap_exceeded`, `pnpm_lock.malformed`, `pnpm_lock.symlink_refused`
  - `npm_lock.size_cap_exceeded`, `npm_lock.depth_cap_exceeded`, `npm_lock.malformed`, `npm_lock.symlink_refused`
  - `yarn_lock.size_cap_exceeded`, `yarn_lock.malformed`, `yarn_lock.symlink_refused`
  - `package_json.missing`, `package_json.malformed`
- The `raw_artifact_budget_mb = 25` override is the second non-trivial use of the S1-09 mechanism; the first was S1-09's own test. If the coordinator side of S1-09 hasn't been exercised yet by a real probe before this story, surface that in PR body so reviewers know this is the load-bearing first use.
- Memo behavior: `ctx.parsed_manifest(path)` returns `None` on the parse-failure no-cache path per S1-07's contract. **Defensive-check for `None`** and fall back to direct `safe_json.load` (which will raise the same typed error you can then catalogue).
- Yarn-lock entry keys can be comma-joined (`"foo@^1, foo@^2":`); the resolution-flattening helper must split on `, ` AND strip the `@<range>` suffix to extract package names. Add a small test for this case if not already covered by the multi-spec fixture.
- The native-module cross-reference is a dict-lookup on the resolved-dep map, not a substring search. `"@types/bcrypt"` is **not** a hit for `"bcrypt"`; treat catalog names as exact matches.
- Per `High-level-impl.md §"Implementation-level risks"` #5, coverage on this probe is what blocks the Step 6 ratchet. Don't punt — this is the densest test surface in Phase 1.
- Sub-schema versioning is deferred to Phase 2 (`High-level-impl.md` open question #2). Ship v1 of the sub-schema here; no `$id` versioning gymnastics.
