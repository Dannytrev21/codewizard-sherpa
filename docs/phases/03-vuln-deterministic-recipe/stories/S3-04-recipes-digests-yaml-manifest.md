# Story S3-04 — `recipes/digests.yaml` manifest + registry digest verification

**Step:** Step 3 — Ship the `NcuRecipeEngine` vertical: `tools/npm` + `tools/ncu` wrappers, `LockfileResolver`, `LockfileCanonicalizer`, recipe catalog + selector
**Status:** Ready
**Effort:** M
**Depends on:** S3-03, S1-03
**ADRs honored:** ADR-0001, ADR-0002, ADR-0011

## Context

Phase 3 ships a **second pin manifest** — `src/codegenie/recipes/digests.yaml` — analogous to `tools/digests.yaml` but covering recipe YAML files rather than binaries. The arch's gap analysis flagged that recipes were data files Phase 4/15 would author, and that without a digest manifest a malicious or stale recipe could change `RemediationReport` outputs silently between runs (Gap 2). `RecipeRegistry.load()` refuses to load any recipe whose on-disk SHA-256 mismatches the manifest, raising `RecipeNotInDigestManifest`. The recipe digest also participates in the transform-apply cache key (proven in S3-08), so a recipe edit invalidates prior cache entries.

This story lands the manifest file (empty/single-entry for now), the registry-side verification, the CI `recipes_digests_verify` job, and the two adversarial tests. The first recipe YAML lands in S3-05; the selector that consumes the registry lands in S3-06.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #3 (Recipe, RecipeSelector, catalog)` — registry verifies content hash against manifest.
  - `../phase-arch-design.md §"Gap analysis" #2` — recipe-digest-manifest gap closure rationale.
- **Phase ADRs:**
  - `../ADRs/0011-lockfile-canonicalization-and-npm-digest-pin-for-deterministic-diffs.md` — pin-manifest discipline pattern.
  - `../ADRs/0001-transform-recipe-engine-two-abc-contract.md` + `../ADRs/0002-two-new-top-level-packages-transforms-recipes.md` — `recipes/` package shape.
- **Existing code:**
  - `src/codegenie/catalogs/tools/digests.yaml` (extended in S3-03) — sibling pattern.
  - `src/codegenie/recipes/contract.py` — `RecipeEngine` ABC (landed in S1-03).
  - `src/codegenie/errors.py` — add `RecipeNotInDigestManifest` (Phase-3 typed error).

## Goal

Ship `src/codegenie/recipes/digests.yaml`, `src/codegenie/recipes/registry.py` (with digest verification on load), the `RecipeNotInDigestManifest` typed exception, the `recipes_digests_verify` CI job, and the drift adversarial test. Recipe digest must already be threadable into a transform-apply cache key so S3-08 can consume it.

## Acceptance criteria

- [ ] `src/codegenie/recipes/digests.yaml` exists (initially empty `{}` or with one placeholder; S3-05 fills it).
- [ ] `src/codegenie/recipes/registry.py` exports `RecipeRegistry` with `load(catalog_root: Path, manifest_path: Path) -> dict[str, Recipe]`; refuses on-disk-vs-manifest hash mismatch → `RecipeNotInDigestManifest(recipe_id, observed_sha256, expected_sha256)`.
- [ ] Hash function: SHA-256 over the **canonicalized** YAML bytes (load + dump with sorted keys + LC_ALL=C); documented in the registry docstring so manifest authors can reproduce.
- [ ] `RecipeRegistry.load()` refuses to load any catalog file **not** present in `recipes/digests.yaml` → `RecipeNotInDigestManifest(reason="missing_from_manifest")`.
- [ ] A helper `recipe_digest_for_cache_key(recipe_id: str) -> str` exposes the manifest hash so S3-08's cache key can consume it.
- [ ] `.github/workflows/<file>.yml` adds a `recipes_digests_verify` job that re-hashes every catalog file and refuses parity drift.
- [ ] `tests/adv/test_recipes_digests_yaml_drift_breaks_load.py` — edit a recipe content without updating the manifest; `RecipeRegistry.load()` raises `RecipeNotInDigestManifest`.
- [ ] `tests/unit/test_recipe_digest_in_cache_key.py` — changing a recipe's manifest digest must change the value `recipe_digest_for_cache_key(...)` returns (proves the dependency).
- [ ] `tests/unit/recipes/test_registry_digest_verification.py` — happy load; manifest miss; on-disk mutation; canonicalization stable across whitespace differences.
- [ ] `ruff check`, `mypy --strict`, `pytest` pass.

## Implementation outline

1. Land the three test files (red).
2. Add `RecipeNotInDigestManifest` to `src/codegenie/errors.py` (already declared in S1-01's error extension; confirm).
3. Create `src/codegenie/recipes/digests.yaml` (empty mapping).
4. Implement `src/codegenie/recipes/registry.py`:
   - `_canonicalize_yaml_bytes(b: bytes) -> bytes` — parse, re-dump with `sort_keys=True`, `default_flow_style=False`, encode with LF; deterministic.
   - `_hash_yaml(path: Path) -> str` — `hashlib.sha256(_canonicalize_yaml_bytes(path.read_bytes())).hexdigest()`.
   - `RecipeRegistry.load(catalog_root, manifest_path)` — for each `*.yaml` under `catalog_root`, hash, compare against manifest, parse via `Recipe(**yaml.safe_load(...))`; collect into `dict[str, Recipe]`.
   - `recipe_digest_for_cache_key(recipe_id) -> str` — returns the manifest entry; raises `RecipeNotInDigestManifest` if absent.
5. Wire `recipes_digests_verify` CI job: a small Python entry point that calls `RecipeRegistry.load(...)` and exits non-zero on any failure.
6. Run unit + adversarial suites.

## TDD plan — red / green / refactor

### Red
Path: `tests/adv/test_recipes_digests_yaml_drift_breaks_load.py`
```python
from pathlib import Path
import shutil

import pytest
import yaml

from codegenie.recipes.registry import RecipeRegistry
from codegenie.errors import RecipeNotInDigestManifest


def test_edited_recipe_without_manifest_update_refuses_load(tmp_path: Path):
    catalog = tmp_path / "catalog" / "npm"
    catalog.mkdir(parents=True)
    recipe_yaml = catalog / "test-recipe.yaml"
    recipe_yaml.write_text("id: test\nengine: ncu\nkind: version_bump\n")

    manifest = tmp_path / "digests.yaml"
    # Compute the canonical digest, write manifest with it
    from codegenie.recipes.registry import _hash_yaml
    manifest.write_text(yaml.safe_dump({"test": {"sha256": _hash_yaml(recipe_yaml)}}))

    # Now drift: edit the recipe content; manifest stays old
    recipe_yaml.write_text("id: test\nengine: ncu\nkind: version_bump\npriority: 1\n")

    with pytest.raises(RecipeNotInDigestManifest):
        RecipeRegistry.load(catalog_root=tmp_path / "catalog", manifest_path=manifest)
```

### Green
Implement `_canonicalize_yaml_bytes`, `_hash_yaml`, `RecipeRegistry.load`, and the cache-key helper exactly as outlined. Don't add a "tolerant" mode.

### Refactor
- Defer until S3-06 (selector) consumes the registry; the public surface stays a single class.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/recipes/digests.yaml` | New — manifest |
| `src/codegenie/recipes/registry.py` | New — verified loader |
| `src/codegenie/errors.py` | Add `RecipeNotInDigestManifest` (if not already from S1-01) |
| `.github/workflows/<file>.yml` | New `recipes_digests_verify` job |
| `tests/adv/test_recipes_digests_yaml_drift_breaks_load.py` | New — drift pin |
| `tests/unit/test_recipe_digest_in_cache_key.py` | New — cache-key dependency pin |
| `tests/unit/recipes/test_registry_digest_verification.py` | New — happy + miss + canonical |

## Out of scope

- **First recipe YAML + `Recipe` Pydantic model** — handled by S3-05.
- **Selector that loads via the registry** — handled by S3-06.
- **Cache-key wiring for the transform** — handled by S3-08 (resolver) + S5-01 (transform); this story only exposes the helper.

## Notes for the implementer
- Use `yaml.safe_load` only — never `yaml.load`. The recipe YAML is trust-but-verify-via-digest, not unsanitized.
- The canonicalization step is what makes the hash stable across operator-side whitespace edits in a PR review; document the recipe-author flow: edit YAML → run `scripts/recalc_recipe_digests.py` → commit both YAML + manifest in the same PR.
- Per Rule 12: `RecipeNotInDigestManifest` must carry both observed and expected hash plus the recipe-id; don't truncate.
- The CI job must run before any recipe is parsed in test or production — even an OS-level recipe author can't slip an edit past it.
- The `recipe_digest_for_cache_key` helper is the cleanest way to thread the manifest hash through to S3-08's cache key without coupling `LockfileResolver` to YAML parsing.
- The new manifest sits beside the recipes (under `recipes/`) rather than under `catalogs/` because the digests are tightly coupled to the recipe content; Phase 15's authoring loop must touch both in the same PR.
