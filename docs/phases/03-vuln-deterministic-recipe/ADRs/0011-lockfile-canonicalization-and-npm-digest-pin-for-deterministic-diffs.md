# ADR-0011: Lockfile canonicalization (`LC_ALL=C`, top-level key sort, LF endings) + pinned `npm` digest for byte-deterministic diffs; `recipes/digests.yaml` for recipe immutability

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** determinism · canonicalization · digest-pinning · synthesizer-addition · recipe-versioning
**Related:** ADR-0003, ADR-0010, ADR-0014, [Phase 2 ADR-0004](../../02-context-gather-layers-b-g/ADRs/0004-tools-digests-yaml-pin-manifest.md)

## Context

The critic surfaced a shared blind spot all three designs implicitly assumed: **`npm` produces consistent lockfile output across versions and environments** (`critique.md §"Cross-design observations" §"Where do all three quietly agree on something questionable?"`; performance-first hidden assumption #1 specifically — "`npm install --package-lock-only` is a deterministic function of `(package.json, package-lock.json, registry-state, npm-version)`"). It isn't:

- npm 9 → 10 had lockfile-format churn.
- npm patch releases have silently changed peer-dep resolution.
- Locale and environment leak into output ordering.

Phase 3's exit criterion includes a byte-deterministic diff (`final-design.md §"Determinism" #19`; determinism canary `test_byte_identical_diff_5x.py` asserts byte-identical diffs and branch SHAs over 5 runs). Without explicit canonicalization and version pinning, the canary fails on the first npm patch bump in the host environment.

A second, adjacent concern is **recipe immutability**: recipes are code/data hybrid (YAML data, but the engine acts on them like code). `phase-arch-design.md §"Gap analysis" §"Gap 2"` introduces `recipes/digests.yaml` — analogous to Phase 2's `tools/digests.yaml` — to pin recipe content by SHA-256 and include the digest in the cache key. The two concerns share a discipline (digest-based pinning for reproducibility) and ship as a single ADR.

## Options considered

- **Trust `npm` to produce deterministic output [P, S, B implicit].** Canary fails on first version drift. Cache invalidation surface unbounded.
- **Pin `npm` major version only [naive].** Insufficient — patch releases drift.
- **Pin `npm` minor digest + post-resolve canonicalization (LC_ALL=C, key sort, LF) [synth].** Pinned-digest contains version drift; canonicalization neutralizes locale and ordering noise.
- **Pin `npm` patch digest [stricter].** Better integrity but causes portfolio-wide cache stampedes on every `npm` patch release; rejected by P's open question #6.

For recipe versioning:

- **No recipe digest manifest.** Recipe edits silently invalidate prior cache without explicit tracking; downstream phases cannot verify which recipe version produced a given diff.
- **Per-recipe `digest` field embedded in the YAML itself.** Self-referential hash problem; rejected.
- **Separate `recipes/digests.yaml` manifest, mirroring Phase 2 `tools/digests.yaml` [synth].** External manifest; recipe digest computed over canonicalized YAML.

## Decision

**Phase 3 ships three coupled determinism mechanisms:**

### 1. Pinned `npm` digest

- `tools/digests.yaml` (Phase 2 ADR-0004 manifest) extends with `npm.digest` entry — pinned at **minor** granularity per `final-design.md §"Cost & latency goals"` #8 (cache key includes npm minor-version digest, not patch — avoids portfolio-wide stampedes on every npm patch release).
- All `npm` invocations in `transforms/` run the pinned binary; CI test asserts the version digest matches `tools/digests.yaml`.
- `npm` minor bumps invalidate the lockfile-resolver cache portfolio-wide; pre-warmed during the bump PR's CI run.

### 2. Lockfile canonicalization

Applied after `npm install --package-lock-only` and before the diff is computed:

- **Locale neutralization:** `LC_ALL=C` set in the `npm` invocation's env (suppresses locale-dependent output ordering).
- **`--no-audit --no-fund`** flags on every `npm install`/`npm ci` invocation (suppresses non-deterministic audit/fund output that mixes into stderr).
- **`npm-lockfile-canonicalize`** post-process step — a small synth helper that:
  - Sorts top-level keys of `package-lock.json`.
  - Normalizes line endings to LF.
  - Reserialized output is the canonical form committed to the worktree.

### 3. `recipes/digests.yaml` manifest

- File at `src/codegenie/recipes/digests.yaml`. Per-recipe entry:
  ```yaml
  recipes:
    npm.upgrade.express.4-to-5:
      digest: "sha256:..."   # over canonicalized YAML bytes
      catalog_path: catalog/npm/upgrade-express-4-to-5.yaml
  ```
- `RecipeRegistry` refuses to load any recipe whose on-disk hash mismatches the manifest (`RecipeNotInDigestManifest`).
- `Recipe.digest` carries the digest in-memory.
- **Cache key for transform application includes the recipe digest** — a recipe edit invalidates prior cache entries automatically.
- Adding/updating a recipe requires a reviewed PR that updates both the YAML and the digest manifest in the same commit.
- Phase 15's agentic recipe-authoring loop is responsible for emitting digest updates alongside new YAML.
- The **OpenRewrite stub recipe** (ADR-0003) is pinned the same way; the *jar* digest lives in `tools/digests.yaml` (the binary); the *recipe definition* digest lives in `recipes/digests.yaml`.

### 4. Determinism canary

- `tests/integration/test_byte_identical_diff_5x.py` runs `codegenie remediate` 5× on the same fixture; asserts byte-identical diffs and branch SHAs.
- The canary uses the pinned local registry mirror (ADR-0012); registry drift cannot affect the diff.

## Tradeoffs

| Gain | Cost |
|---|---|
| Determinism canary holds across host environments — `LC_ALL=C` and key-sort neutralize locale and ordering noise that would otherwise flake | The `npm-lockfile-canonicalize` helper is Phase-3 code that must track `npm`'s lockfile schema changes; CI test asserts canonicalization is idempotent |
| Pinning `npm` at minor granularity avoids portfolio-wide cache stampedes on patch releases (a daily occurrence) while contain version drift | npm major or minor bumps invalidate the entire portfolio's lockfile cache; pre-warming on the bump PR is a real operational task |
| `recipes/digests.yaml` makes recipe updates explicitly reviewed — recipe edits flow through PR review, not silent file edits | Adding a recipe is now a two-file change (YAML + digest manifest); CI fixture asserts the pair stays in sync |
| Cache key includes recipe digest — Phase 15's agent-authored recipes invalidate prior cache without manual intervention | Cache GC must consider recipe-digest churn; the per-recipe cache footprint grows as recipes are added/updated |
| OpenRewrite stub recipe pinning (jar digest + recipe digest) mirrors Phase 2 ADR-0004 — same review discipline for any pinned artifact | Two manifests (`tools/digests.yaml` for binaries, `recipes/digests.yaml` for recipes) to maintain; documented loudly |
| `--no-audit --no-fund` is a structural defense against non-determinism; CI test `test_no_audit_no_fund_on_install.py` asserts | Operators who want audit output in CI must run `npm audit` separately; documented |

## Consequences

- `tools/digests.yaml` (existing per Phase 2 ADR-0004) extends with `npm` entry.
- `src/codegenie/transforms/utils/lockfile_canonicalize.py` ships the canonicalization helper.
- `src/codegenie/recipes/digests.yaml` ships with per-recipe digests.
- `src/codegenie/recipes/registry.py` raises `RecipeNotInDigestManifest` on hash mismatch.
- `Recipe.digest` field in `recipes/models.py`.
- Cache key for `transforms/coordinator.py` and `LockfileResolver` includes `(blake3(package.json), blake3(package-lock.json), npm_minor_digest, registry_mirror_digest, recipe_digest)`.
- `tests/unit/test_lockfile_canonicalize_idempotent.py` asserts canonicalization is a fixed point.
- `tests/integration/test_byte_identical_diff_5x.py` is the determinism canary.
- `tests/adv/test_recipes_digests_yaml_drift_breaks_load.py` asserts manifest drift fails loud.
- `tests/unit/test_recipe_digest_in_cache_key.py` asserts the cache-key shape.
- Phase 15's recipe-authoring loop emits digest manifest updates as part of every recipe-authoring PR.
- Phase 7's distroless recipes inherit the same pinning discipline.

## Reversibility

**Medium.** Dropping `LC_ALL=C` or `--no-audit --no-fund` is mechanically easy but **immediately fails the determinism canary**; high-cost in CI breakage. Dropping the `npm-lockfile-canonicalize` helper similarly breaks the canary on the first locale-divergent host. Switching from minor-digest pinning to patch-digest pinning is **operationally expensive** (every npm patch invalidates the portfolio cache); switching the other way (major-only) loosens determinism — both directions are tunable but each has a cost. Dropping `recipes/digests.yaml` is high-cost because the cache-key shape changes and recipe-edit safety regresses; reversal would require explicit re-design.

## Evidence / sources

- `../final-design.md §"Goals" §"Determinism"` #19
- `../final-design.md §"Components" #4 "NpmPackageUpgradeTransform"` (canonicalization step)
- `../final-design.md §"Synthesis ledger" §"Conflict-resolution table"` row "Manifest write-back determinism"
- `../final-design.md §"Departures from all three inputs"` #5 — canonicalization is synth-added
- `../final-design.md §"Shared blind spots considered"` #4
- `../phase-arch-design.md §"Component design" #6 "LockfileCanonicalizer"`
- `../phase-arch-design.md §"Gap analysis" §"Gap 2 — Recipe versioning + immutability"`
- `../critique.md §"Attacks on performance-first" §"Hidden assumptions" #1` — npm determinism assumption
- `../critique.md §"Attacks on best-practices" §"Hidden assumptions" #3` — `ncu` version variability
- [Phase 2 ADR-0004](../../02-context-gather-layers-b-g/ADRs/0004-tools-digests-yaml-pin-manifest.md) — `tools/digests.yaml` precedent
