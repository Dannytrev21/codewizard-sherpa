# Story S17-02 — `BaseImageProbe` multi-arch coverage + non-public-registry extension

**Step:** Step 17 — Migration confidence + multi-arch / external-registry checks (M1, G11, G13)
**Status:** Ready
**Effort:** M
**Depends on:** S13-03 (Amendment-A probe sub-schemas + envelope wiring + the ADR-0029 byte-edit-allowlist fence amendment — `base_image.schema.json` and the fence-allowlist row this story's additive schema-field edit consumes both land in S13-03). Implicitly downstream of S7-01 (the still-`Ready` story that ships the *base* `BaseImageProbe` slice — this story **amends S7-01's acceptance criteria**, see below).
**ADRs honored:** Phase 7 ADR-0024 (`BaseImageProbe` is extended, not duplicated, for architecture-coverage delta and non-public-registry detection — this story *is* ADR-0024); Phase 7 ADR-0025 (`RefusedArchitectureLoss` is the closed-taxonomy refusal variant an arch-loss case yields — the recipe emits it, S16-01 defines it); Phase 7 ADR-0026 (`non_public_registry` → `AdapterConfidence.Degraded` feeds the `MigrationConfidence` rollup — S17-01); Phase 7 ADR-0029 (the two additive `base_image.schema.json` fields are an Amendment-A byte-edit allowlisted by row category #2/#6-style additive-schema growth); Phase 7 ADR-0005 (probes live under the plugin); Phase 0 ADR-0007 (frozen Probe ABC — extension is by additive *slice fields*, never an edit to the ABC); production ADR-0043 (extension by addition — additive fields, no silent removal).

## Context

A naive `FROM` swap silently introduces two image-resolution hazards that Amendment A's gap inventory (`../final-design.md §Amendment A §A.2`, rows G11 and G13) names explicitly:

- **G11 — multi-architecture coverage delta.** The *source* image may publish a manifest list covering architectures the Chainguard *target* does not. `node:18-alpine` ships an `armv7` entry; `cgr.dev/chainguard/node` ships `amd64`/`arm64` only. A `FROM` swap that drops `armv7` produces an image that builds clean, passes `DockerfilePolicyGate`, and merges — then **fails to schedule on an `armv7` node in production**. A silently dropped platform; the broken-image outcome `../final-design.md §A.1` forbids.
- **G13 — non-public mirror base image.** A `FROM` referencing an internal mirror (`acmecorp/node:18-alpine-patched`, `internal.registry.example/node:18`) may already carry the target CVE patched *differently* than the public upstream. A migration that assumes the public-registry patch state can regress or duplicate a fix.

Both hazards are answered by facts the **existing** `BaseImageProbe` (`../phase-arch-design.md §Component design §8`; story S7-01) is already 90% of the way to producing. It reads every `FROM`, resolves it to an immutable digest via `ctx.image_digest_resolver`, and classifies the image kind via the `_BASE_IMAGE_KIND_RULES` open/closed catalog. The architecture set is in the resolved manifest list; the registry host is in the `from_image` reference string. ADR-0024 considered adding a second `ArchitectureProbe` (Option A) and rejected it — a second probe re-does the identical digest resolution, doubling the cold-path manifest round-trip the §8 performance envelope budgets, and splits one image's facts across two slices. **The decision (Option B) is to extend the one probe that already holds the digest.** This story does exactly that: it amends `BaseImageProbe` and its slice — **it does not add a new probe.**

`BaseImageStage` (the per-`FROM` record S7-01 ships) gains two additive fields:

- `supported_architectures: tuple[str, ...]` — the architecture set of the **source** image, read from the already-resolved manifest list (no second digest round-trip).
- `non_public_registry: bool` — `True` when the `from_image` registry host is not a recognised public registry (`docker.io`, `ghcr.io`, `gcr.io`, `cgr.dev`, `registry.access.redhat.com`, `quay.io`, …).

Behavioural consequences (ADR-0024 §Decision):

- **G11.** When a source stage's `supported_architectures` is a strict superset of the Chainguard target's set (the target set comes from `TargetImageContentProbe`'s `supported_architectures`, ADR-0019 / S13-02), the migration would drop a platform. The recipe (`DockerfileBaseImageSwapTransform`, S16-02) later **refuses** with `RefusedArchitectureLoss` (ADR-0025 / S16-01), naming the dropped architecture(s). This probe ships the *fact* (`supported_architectures`); the recipe ships the *refusal*.
- **G13.** When `non_public_registry` is `True`, the resolving provenance adapter reports `AdapterConfidence.Degraded` and the probe emits a **WARN** requiring HITL acknowledgement — the operator confirms the mirror's patch state before the migration proceeds. The migration is *not refused* (the mirror may be fine); it is *degraded and surfaced*. That `Degraded` flows into the `MigrationConfidence` rollup (S17-01 / ADR-0026).

**This story explicitly amends story S7-01.** S7-01 (`S7-01-base-image-probe.md`) is still `Status: Ready` — it has not been executed. ADR-0024 §Decision states: "This amends the still-`Ready` story S7-01 — its acceptance criteria gain the two new fields and the `RefusedArchitectureLoss` / `Degraded`-on-mirror behaviour." The amendment is enumerated in `## Acceptance criteria — amendments to S7-01` below. **The implementing executor must apply S17-02's added ACs to S7-01's AC list** (either by landing S7-01 and S17-02 together, or by editing S7-01's ACs in place with a dated amendment note pointing here). The two additive `base_image.schema.json` fields are an Amendment-A additive-schema change allowlisted by ADR-0029 — no envelope `$ref` change (the slice already has one from S7-03).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §8 (BaseImageProbe)` — the *existing* probe: digest resolution via `ctx.image_digest_resolver`, the `_BASE_IMAGE_KIND_RULES` catalog, the per-stage `BaseImageStage` record, the performance envelope (p99 ≤ 60 ms cold).
  - `../phase-arch-design.md §Component design — Amendment A` — resolves G11/G13 as a `BaseImageProbe` *extension*, not a new probe.
  - `../phase-arch-design.md §Amendment A gaps §Sequencing` — "S7-01 amended" by Amendment-A Step-17 work.
  - `../final-design.md §Amendment A §A.2 (G11, G13 rows)` — both name the component as `BaseImageProbe extension`; `§A.1` — governing principle "gather-or-refuse, never ship broken."
- **Phase ADRs:**
  - `../ADRs/0024-multi-arch-and-external-registry-checks.md` — **this story implements ADR-0024 verbatim.** §Decision gives the two field names and the two behaviours; §Consequences names the edited probe file, the additive `base_image.schema.json` properties, and "Story S7-01 acceptance criteria are amended."
  - `../ADRs/0025-migration-refusal-taxonomy.md` — `RefusedArchitectureLoss` is a variant of the closed refusal taxonomy; its payload names the dropped architecture(s) and the source stage. S16-01 defines it; S16-02's recipe emits it.
  - `../ADRs/0026-migration-confidence-aggregation.md` — the `non_public_registry` → `AdapterConfidence.Degraded` channel; the rollup consumes it (S17-01).
  - `../ADRs/0019-target-image-content-probe.md` — `TargetImageContentProbe` ships the *target* image's `supported_architectures`; the recipe compares the two sets.
  - `../ADRs/0028-allowed-binaries-amendment-crane.md` — `crane` is the manifest-list resolver; `crane manifest` reads the architecture set. `crane` is added to `ALLOWED_BINARIES` by S13-02 — this story does not edit `ALLOWED_BINARIES`.
  - `../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md` — the additive `base_image.schema.json` field growth is an allowlisted Amendment-A schema edit.
- **Existing code / precedents:**
  - `plugins/distroless-migration--node--npm/probes/base_image_probe.py` — the *existing* probe file S7-01 ships. This story **byte-edits it** to populate the two new fields. ADR-0024 §Consequences: "no new probe file; `base_image_probe.py` is edited."
  - `plugins/distroless-migration--node--npm/schema/base_image.schema.json` — the existing slice sub-schema (S7-03). This story adds two `properties` rows, both with `additionalProperties: false` discipline preserved at every node (Phase 1 ADR-0004).
  - `src/codegenie/primitives/vuln_provenance/types.py` — `class AdapterConfidence(str, Enum)` with `HIGH`/`DEGRADED`/`UNAVAILABLE` (S1-02). `non_public_registry == True` → the resolving adapter reports `AdapterConfidence.DEGRADED`.
  - `src/codegenie/types/identifiers.py` — `ImageRef` newtype; the registry host is parsed off the `ImageRef` string.
  - `src/codegenie/probes/base.py` — the frozen Probe ABC; this story adds *slice fields*, never touches the ABC.
- **Story-pipeline neighbors:**
  - `S7-01-base-image-probe.md` — **the story this one amends.** Still `Ready`. Read its `## Acceptance criteria` in full — S17-02's added ACs slot into that list.
  - `S13-02-target-image-content-probe.md` — ships `TargetImageContentProbe.supported_architectures` (the *target* arch set) and adds `crane` to `ALLOWED_BINARIES`.
  - `S13-03-amendment-a-schemas-and-fence.md` — owns the `base_image.schema.json` amendment landing + the ADR-0029 fence-allowlist row for it.
  - `S16-01-migration-refusal-taxonomy.md` — defines `RefusedArchitectureLoss` in `outcomes.py`.
  - `S16-02-recipe-contract-amendment.md` — the recipe that *emits* `RefusedArchitectureLoss` by comparing source vs target `supported_architectures`.
  - `S17-01-migration-confidence-aggregator.md` — sibling Step-17 story; consumes the `AdapterConfidence.Degraded` this story produces.

## Goal

Extend the **existing** `BaseImageProbe` (`base_image_probe.py`) and its slice — **without adding a new probe** — so each `BaseImageStage` record additionally carries `supported_architectures: tuple[str, ...]` (the source image's architecture set, read from the already-resolved manifest list with no second digest round-trip) and `non_public_registry: bool` (derived from the `from_image` registry host against a module-level public-registry allowlist). When the source registry is non-public, the resolving adapter reports `AdapterConfidence.Degraded` and the probe emits a WARN requiring HITL acknowledgement. The source `supported_architectures` set is the fact the recipe (S16-02) later compares against the Chainguard target's set to refuse with `RefusedArchitectureLoss` on a strict-superset (arch-loss) case. The two slice fields are an additive `base_image.schema.json` change (ADR-0029 allowlist). This story **amends the still-`Ready` story S7-01's acceptance criteria** — the added ACs are enumerated below. `mypy --strict` clean; the §8 performance envelope (p99 ≤ 60 ms cold) holds — no duplicate manifest round-trip.

## Acceptance criteria

**Slice extension — additive fields (AC-1 through AC-3)**
- [ ] **AC-1** `BaseImageStage` (the per-`FROM` record in `base_image_probe.py`) gains `supported_architectures: tuple[str, ...]` — the architecture set of the **source** image (e.g. `("amd64", "arm64", "arm/v7")`). The field is **additive**: every existing `BaseImageStage` field from S7-01 is unchanged, same key order, with the two new fields appended. Verified by `tests/unit/plugins/distroless_migration_node_npm/probes/test_base_image_multiarch.py::test_supported_architectures_field_present` — constructs a `BaseImageStage` from a resolved multi-arch fixture, asserts `isinstance(stage.supported_architectures, tuple)` and that every element is a `str`.
- [ ] **AC-2** `BaseImageStage` gains `non_public_registry: bool`. Verified by `test_base_image_multiarch.py::test_non_public_registry_field_present` — asserts the field exists, is a `bool`, and defaults are not silently `True`/`False` for an unresolvable host (an unresolvable host follows the AC-9 degraded path, not a silent default).
- [ ] **AC-3** `plugins/distroless-migration--node--npm/schema/base_image.schema.json` gains exactly two additive `properties` entries on the per-stage object — `supported_architectures` (`{"type": "array", "items": {"type": "string"}}`) and `non_public_registry` (`{"type": "boolean"}`) — both added to the stage object's `required` list. `additionalProperties: false` is preserved at every node (Phase 1 ADR-0004). **No envelope `$ref` change** — the `base_image` slice already has its `$ref` from S7-03. Verified by `test_base_image_multiarch.py::test_schema_has_two_additive_fields` — loads the schema JSON, asserts the two property keys are present under the stage object, asserts `additionalProperties` is still `false` at the stage node, and asserts no key was *removed* relative to the S7-01 stage field set (additive-only, production ADR-0043).

**Multi-architecture coverage — G11 (AC-4 through AC-7)**
- [ ] **AC-4** `supported_architectures` is populated from the **already-resolved manifest list** — the same `crane manifest` / `ctx.image_digest_resolver` round-trip `BaseImageProbe` already makes for digest resolution. **No second resolution call.** Verified by `tests/fence/test_base_image_no_duplicate_resolution.py::test_resolver_called_once_per_unique_from` — wraps the resolver/manifest accessor in a call-counting stub, runs the probe over a two-stage fixture with two distinct `FROM` lines, and asserts the resolution path is invoked **exactly once per unique image reference** (not twice — once for digest, once for arch). A second call per image fails this AC (ADR-0024 §Tradeoffs row 1 — "zero duplicate digest resolution").
- [ ] **AC-5** Multi-arch happy path: fixture `tests/fixtures/portfolio/base-image-multiarch/Dockerfile` (`FROM node:18-alpine` whose stubbed manifest list covers `amd64`, `arm64`, `arm/v7`) → the stage's `supported_architectures == ("amd64", "arm/v7", "arm64")` (sorted, deterministic). Verified by `test_base_image_multiarch.py::test_multiarch_source_populated` — asserts the exact sorted tuple.
- [ ] **AC-6** Arch-loss detection — armv7-only-source vs amd64/arm64-target: given a source stage with `supported_architectures` containing `arm/v7` and a (test-supplied) target architecture set `{"amd64", "arm64"}`, the source set is a **strict superset** of the target set — the comparison helper `_architectures_lost(source, target) -> tuple[str, ...]` returns `("arm/v7",)` (the dropped architecture(s), sorted, non-empty). Verified by `test_base_image_multiarch.py::test_armv7_source_against_amd64_arm64_target_detects_loss` — asserts `_architectures_lost(("amd64","arm/v7","arm64"), ("amd64","arm64")) == ("arm/v7",)`. The probe ships the *fact* and the helper; the *refusal* (`RefusedArchitectureLoss`) is the recipe's job (S16-02) — see Out of scope.
- [ ] **AC-7** No-loss path: when the source `supported_architectures` is a subset of (or equal to) the target set, `_architectures_lost(...)` returns the empty tuple `()`. Verified by `test_base_image_multiarch.py::test_no_arch_loss_when_source_subset_of_target` — asserts `_architectures_lost(("amd64",), ("amd64","arm64")) == ()` and `_architectures_lost(("amd64","arm64"), ("amd64","arm64")) == ()`.

**Non-public registry — G13 (AC-8 through AC-11)**
- [ ] **AC-8** Public-registry case → `non_public_registry == False`. Fixture `tests/fixtures/portfolio/base-image-chainguard-public/Dockerfile` (`FROM cgr.dev/chainguard/node:latest`) → the stage's `non_public_registry == False`. Verified by `test_base_image_multiarch.py::test_public_chainguard_registry_flagged_false`. The public-registry host allowlist `_PUBLIC_REGISTRY_HOSTS: Final[frozenset[str]]` covers at minimum `docker.io`, `index.docker.io`, `ghcr.io`, `gcr.io`, `cgr.dev`, `registry.access.redhat.com`, `quay.io`, `mcr.microsoft.com`, `public.ecr.aws`. A bare image name with no host (e.g. `node:18-alpine`) resolves to the implicit `docker.io` → `non_public_registry == False`.
- [ ] **AC-9** Non-public-registry case → `non_public_registry == True` **and** the resolving adapter reports `AdapterConfidence.Degraded` **and** a WARN is emitted. Fixture `tests/fixtures/portfolio/base-image-private-mirror/Dockerfile` (`FROM internal.registry.example/node:18-alpine-patched`) → the stage's `non_public_registry == True`; the probe emits warning `"base_image.non_public_registry"` (matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`, Phase 1 ADR-0007); the adapter-confidence channel reports `AdapterConfidence.DEGRADED` for that stage. Verified by `test_base_image_multiarch.py::test_private_mirror_flagged_and_degraded` — asserts all three: the bool, the warning ID, and the `AdapterConfidence.DEGRADED` value.
- [ ] **AC-10** The non-public registry is **degraded, not refused**. The probe still runs to completion, `kind` is still classified, the digest is still resolved — `non_public_registry == True` does *not* short-circuit the probe or produce a refusal. Verified by `test_base_image_multiarch.py::test_private_mirror_is_degraded_not_refused` — asserts the private-mirror stage still carries a resolved `image_digest` and a non-`unknown` `kind` (the mirror image is still classifiable), and that **no `RefusedExternalRegistryBaseImage` / no refusal** is produced by the probe (the probe gathers; refusal — if any — is the recipe's call). ADR-0024 §Decision: "The migration is not refused (the mirror may be fine); it is degraded and surfaced."
- [ ] **AC-11** Registry-host classification uses the `_PUBLIC_REGISTRY_HOSTS` allowlist (module-level `Final`), iterated/`in`-checked — **never a chained `if/elif` on host strings**. Verified by `tests/unit/plugins/distroless_migration_node_npm/probes/test_registry_classification.py::test_no_if_chain_on_registry_host` — AST-walks `_classify_registry(from_image) -> bool` and asserts ≤ 1 `if` statement and no `elif` arms comparing string equality against literal host names. Adding a new public registry is a one-entry addition to `_PUBLIC_REGISTRY_HOSTS`, not an edit to `_classify_registry` (ADR-0024 §Tradeoffs row 4 — "the allowlist is data, extensible without an ADR").

**Amendments to S7-01 (AC-12)**
- [ ] **AC-12** Story `S7-01-base-image-probe.md` is amended: its `## Acceptance criteria` gains the four AC clauses enumerated in `## Acceptance criteria — amendments to S7-01` below (the two new slice fields, the arch-loss helper, the non-public-registry behaviour). The amendment is applied either by landing S7-01 and S17-02 in the same PR window with S7-01's AC list updated, or by editing S7-01 in place with a dated `> Amended by S17-02 (ADR-0024), 2026-05-20` note. Verified by inspection: `S7-01-base-image-probe.md` references S17-02 / ADR-0024 in its AC section, and the four added clauses are present. (ADR-0024 §Decision + §Consequences: "Story S7-01 acceptance criteria are amended to cover both fields and both behaviours.")

**Fence + lint discipline (AC-13 through AC-15)**
- [ ] **AC-13** Phase 7 ADR-0009 / ADR-0029 byte-edit allowlist fence (`tests/fence/test_phase7_no_byte_edits_to_locked_files.py`) green: the only edits outside `tests/` are to `plugins/distroless-migration--node--npm/probes/base_image_probe.py` and `plugins/distroless-migration--node--npm/schema/base_image.schema.json` — **both Amendment-A allowlisted by ADR-0029** (the probe-file edit under row category #1's "edited to populate the two new fields" allowance per ADR-0024 §Consequences; the additive-schema growth under ADR-0029's additive-schema allowance). **No Phase 0–6.5 / Phase 3 file is byte-edited**, and `src/codegenie/exec/__init__.py` / `ALLOWED_BINARIES` is *not* touched (`crane` is S13-02's edit). The fence-allowlist rows for the two edited files land in S13-03; if S13-03 lags, the executor adds them per ADR-0029 and records the sequencing in the attempt log.
- [ ] **AC-14** `make lint-imports` green; the edit introduces no forbidden import path. `ruff check`, `ruff format --check`, `mypy --strict plugins/distroless-migration--node--npm/probes/base_image_probe.py` all clean. **No `Any` in any annotation** — the `test_no_any_in_plugin_surface` discipline applies; `supported_architectures: tuple[str, ...]` and `non_public_registry: bool` are fully typed.
- [ ] **AC-15** The §8 performance envelope holds — warm-cache p99 ≤ 2 ms, cold p99 ≤ 60 ms (the budget S7-01's perf AC reserves for S12-05). The two new fields ride the existing manifest round-trip (AC-4) — no new I/O. The perf-test *body* lands in S12-05; this AC is **reserved** here and recorded in `_attempts/S17-02.md` so S12-05's executor pulls it in, asserting the post-extension probe still meets the cold/warm budget on the multi-arch fixture.

## Acceptance criteria — amendments to S7-01

These four clauses are **added** to `S7-01-base-image-probe.md`'s `## Acceptance criteria` (per AC-12). They do not replace or alter any existing S7-01 AC — S7-01's slice, kind classification, digest resolution, and parse-failure ACs stand unchanged.

- **S7-01 AC-20 (added)** — Each `BaseImageStage` carries `supported_architectures: tuple[str, ...]` (the source image's architecture set, from the resolved manifest list) and `non_public_registry: bool` (registry-host classification). Both fields are additive — appended after S7-01's existing stage fields, same key order for the originals.
- **S7-01 AC-21 (added)** — `base_image.schema.json` carries the two additive `properties` (`supported_architectures` array-of-string, `non_public_registry` boolean), both in `required`, `additionalProperties: false` preserved. No envelope `$ref` change.
- **S7-01 AC-22 (added)** — A non-public source registry sets `non_public_registry == True`, emits warning `base_image.non_public_registry`, and drives `AdapterConfidence.Degraded` on the resolving adapter. The probe is *degraded, not refused* — it runs to completion.
- **S7-01 AC-23 (added)** — `supported_architectures` is the fact the recipe (S16-02) compares against `TargetImageContentProbe`'s target set to emit `RefusedArchitectureLoss` (ADR-0025) on a strict-superset (arch-loss) case. The probe ships the fact and the `_architectures_lost` helper; it does not itself refuse.

## Implementation outline

1. **Edit the existing probe — do not add a new file.** Touch:
   - `plugins/distroless-migration--node--npm/probes/base_image_probe.py` — extend `BaseImageStage`, add the two helpers, populate the fields in `run()`.
   - `plugins/distroless-migration--node--npm/schema/base_image.schema.json` — two additive `properties` rows.
   - New test files + fixtures (below).

2. **Extend `BaseImageStage` in `base_image_probe.py`:**
   ```python
   class BaseImageStage(_Frozen):   # existing S7-01 fields unchanged, then:
       supported_architectures: tuple[str, ...]   # source image's manifest-list arch set
       non_public_registry: bool
   ```

3. **Public-registry allowlist (module-level data, AC-11):**
   ```python
   from typing import Final
   _PUBLIC_REGISTRY_HOSTS: Final[frozenset[str]] = frozenset({
       "docker.io", "index.docker.io", "ghcr.io", "gcr.io", "cgr.dev",
       "registry.access.redhat.com", "quay.io", "mcr.microsoft.com",
       "public.ecr.aws",
   })
   ```

4. **`_classify_registry(from_image: str) -> bool`** — returns `True` (non-public) when the host is not in `_PUBLIC_REGISTRY_HOSTS`:
   - Parse the registry host off `from_image`: the segment before the first `/` *iff* it contains a `.` or a `:` (Docker reference grammar — a first segment with no `.`/`:` is a Docker Hub namespace, not a host).
   - No host segment → implicit `docker.io` → `return False`.
   - `host in _PUBLIC_REGISTRY_HOSTS` → `return False`; else `return True`.
   - Single early-return-friendly body; no `elif` chain on host literals (AC-11 AST fence).

5. **`_architectures_lost(source: tuple[str, ...], target: tuple[str, ...]) -> tuple[str, ...]`** — pure set helper:
   - Returns `tuple(sorted(set(source) - set(target)))` — the source architectures the target does not cover.
   - Empty tuple ⇒ no loss (AC-7). Non-empty ⇒ the dropped platforms (AC-6). This helper is pure functional-core; the recipe (S16-02) calls it to decide `RefusedArchitectureLoss`.

6. **Populate the fields in `run()`:**
   - `supported_architectures`: read the manifest-list architecture set from the **already-resolved** manifest object the digest-resolution path returns. Do **not** call the resolver a second time. If the resolved manifest is a single-arch image (not a manifest list), `supported_architectures` is the single arch as a one-tuple; if the resolver returned no digest (resolver `None` / unresolvable), `supported_architectures` is `()` and the stage follows S7-01's existing `medium`-confidence degraded path.
   - `non_public_registry`: `_classify_registry(from_image)`.
   - When `non_public_registry` is `True`: append `"base_image.non_public_registry"` to `warnings`; mark the resolving-adapter channel `AdapterConfidence.DEGRADED` for that stage (the exact wiring of how the probe surfaces `AdapterConfidence` to the adapter follows the S7-01 / S1-04 adapter-confidence convention — pin it in the attempt log).

7. **Warning-ID registration:** add `"base_image.non_public_registry"` to the existing `_WARNING_IDS: Final[frozenset[str]]` in `base_image_probe.py`; the import-time `raise AssertionError(...)` regex check (already present from S7-01) covers it.

8. **Schema edit** — `base_image.schema.json`: under the per-stage object's `properties`, add `supported_architectures` and `non_public_registry`; add both to that object's `required`; leave `additionalProperties: false` and every other node untouched.

9. **Fixtures:**
   - `tests/fixtures/portfolio/base-image-multiarch/Dockerfile` — `FROM node:18-alpine`; alongside it a `_manifest_list.json` the resolver-stub returns covering `amd64`, `arm64`, `arm/v7`.
   - `tests/fixtures/portfolio/base-image-chainguard-public/Dockerfile` — `FROM cgr.dev/chainguard/node:latest`.
   - `tests/fixtures/portfolio/base-image-private-mirror/Dockerfile` — `FROM internal.registry.example/node:18-alpine-patched`.

10. **Amend S7-01** (AC-12): edit `S7-01-base-image-probe.md`'s `## Acceptance criteria` to add the four clauses from `## Acceptance criteria — amendments to S7-01`, with a dated `> Amended by S17-02 (ADR-0024)` note.

## TDD plan — red / green / refactor

**Red** — write `test_base_image_multiarch.py::test_supported_architectures_field_present` first. It constructs a `BaseImageStage` (or runs the probe over the multi-arch fixture) and reads `stage.supported_architectures`. Run pytest — fails with `AttributeError` / Pydantic `extra="forbid"` rejection: the field does not exist on `BaseImageStage`. This is the concrete red.

**Green** — add `supported_architectures: tuple[str, ...]` and `non_public_registry: bool` to `BaseImageStage`, and the two `properties` to `base_image.schema.json`. Re-run — the field-present tests (AC-1, AC-2, AC-3) go green; behavior tests still fail (the fields are not populated by `run()`).

**Red+** — write `test_base_image_multiarch.py::test_multiarch_source_populated` with the `base-image-multiarch` fixture + `_manifest_list.json` resolver-stub. Pytest fails — `run()` leaves `supported_architectures` empty.

**Green+** — populate `supported_architectures` in `run()` from the already-resolved manifest list (Step 6). Re-run — AC-5 green.

**Red++** — write `test_base_image_multiarch.py::test_armv7_source_against_amd64_arm64_target_detects_loss`. Pytest fails — `_architectures_lost` is undefined.

**Green++** — implement `_architectures_lost` as the pure set-difference helper. AC-6, AC-7 green.

**Red+++** — write `test_base_image_multiarch.py::test_private_mirror_flagged_and_degraded` with the `base-image-private-mirror` fixture. Pytest fails — `_classify_registry` is undefined / `non_public_registry` not populated / no WARN emitted.

**Green+++** — implement `_classify_registry` + the `_PUBLIC_REGISTRY_HOSTS` allowlist, populate `non_public_registry`, append the warning, mark `AdapterConfidence.DEGRADED`. AC-8, AC-9, AC-10 green.

**Red++++** — write `test_base_image_no_duplicate_resolution.py::test_resolver_called_once_per_unique_from` with a call-counting resolver stub. If the implementation naively resolves twice (digest + arch), the count is 2 and the test fails.

**Green++++** — route `supported_architectures` off the manifest object the *first* resolution already returns. Count drops to 1; AC-4 green.

**Refactor** — AST-assert `_classify_registry` has no `if/elif` chain on host literals (AC-11); confirm `_architectures_lost` is pure (no I/O); confirm the two new fields are appended (additive, key order of originals preserved). Amend S7-01 (AC-12). `mypy --strict` + `ruff` clean.

## Files to touch

**Edited files (Amendment-A allowlisted by ADR-0024 / ADR-0029):**

| Path | Edit |
|---|---|
| `plugins/distroless-migration--node--npm/probes/base_image_probe.py` | Extend `BaseImageStage` with two additive fields; add `_PUBLIC_REGISTRY_HOSTS`, `_classify_registry`, `_architectures_lost`; populate the fields in `run()`; register the new warning ID (ADR-0024 §Consequences — "no new probe file; `base_image_probe.py` is edited") |
| `plugins/distroless-migration--node--npm/schema/base_image.schema.json` | Two additive `properties` rows on the per-stage object + both into `required`; `additionalProperties: false` preserved (ADR-0024 §Consequences; ADR-0029 additive-schema allowance) |
| `docs/phases/07-migration-task-class/stories/S7-01-base-image-probe.md` | Amend `## Acceptance criteria` with the four added clauses (AC-12) |

**New files (no Phase 0–6.5 / Phase 3 byte-edits):**

| Path | Purpose |
|---|---|
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_base_image_multiarch.py` | AC-1..AC-3, AC-5..AC-10 — slice fields, multi-arch, non-public-registry behaviour |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_registry_classification.py` | AC-11 — AST fence on `_classify_registry` (no `if/elif` host chain) |
| `tests/fence/test_base_image_no_duplicate_resolution.py` | AC-4 — resolver called once per unique `FROM` (no duplicate round-trip) |
| `tests/fixtures/portfolio/base-image-multiarch/Dockerfile` (+ `_manifest_list.json`) | Multi-arch source fixture |
| `tests/fixtures/portfolio/base-image-chainguard-public/Dockerfile` | Public Chainguard `FROM` fixture |
| `tests/fixtures/portfolio/base-image-private-mirror/Dockerfile` | Non-public mirror `FROM` fixture |

**Files NOT touched** (would fail the ADR-0009 / ADR-0029 fence): `src/codegenie/exec/__init__.py` (`crane` / `ALLOWED_BINARIES` is S13-02), `src/codegenie/schema/repo_context.schema.json` (no envelope `$ref` change — the slice already has one), `src/codegenie/transforms/outcomes.py` (`RefusedArchitectureLoss` is S16-01), `src/codegenie/probes/base.py` (the frozen ABC — extension is by slice fields).

## Out of scope

- **Emitting `RefusedArchitectureLoss`** — this story ships the *fact* (`supported_architectures`) and the *pure comparison helper* (`_architectures_lost`). The *refusal* — comparing the source set against `TargetImageContentProbe`'s target set and emitting `RefusedArchitectureLoss` — is the recipe's job (`DockerfileBaseImageSwapTransform`, S16-02). ADR-0024 §Consequences: "The recipe consumes `supported_architectures` and compares against `TargetImageContentProbe`'s set; a strict superset → `RefusedArchitectureLoss`."
- **Defining `RefusedArchitectureLoss` / `RefusedExternalRegistryBaseImage`** — S16-01 ships the refusal variants in `outcomes.py`. This story does not define refusal types.
- **The `TargetImageContentProbe` target architecture set** — S13-02 / ADR-0019 ships `TargetImageContentProbe.supported_architectures` (the *target* image's arch set). This story's tests supply the target set as a fixed test value to exercise `_architectures_lost`; it does not implement `TargetImageContentProbe`.
- **`crane` in `ALLOWED_BINARIES`** — S13-02 / ADR-0028 adds `crane`. This story uses the manifest-resolution path that round-trip already exists from S7-01 / S13-02; it does not edit `ALLOWED_BINARIES`.
- **The `MigrationConfidence` rollup** — S17-01 / ADR-0026 ships `aggregate_migration_confidence`, which *consumes* the `AdapterConfidence.Degraded` this story produces. This story produces the `Degraded`; it does not aggregate it.
- **The base `BaseImageProbe` slice, kind classification, digest resolution, parse-failure handling** — all of that is S7-01. This story *extends* S7-01's slice; it does not re-implement it. Do not fork `_BASE_IMAGE_KIND_RULES` or the Dockerfile-discovery helper.
- **The perf-test body** — S12-05 owns the `@pytest.mark.bench` perf test. AC-15 reserves the AC; the body is S12-05.

## Notes for the implementer

- **Rule 3 — surgical changes.** ADR-0024 chose Option B (extend the one probe) over Option A (a second `ArchitectureProbe`) precisely to avoid duplication. The edit to `base_image_probe.py` is *additive*: two fields on `BaseImageStage`, three module-level helpers, a few lines in `run()`. Do **not** restructure `run()`, do **not** rename existing helpers, do **not** touch `_BASE_IMAGE_KIND_RULES` or the kind-classification path. Every existing S7-01 field, helper, and behaviour stands unchanged — the fence (AC-3, AC-13) enforces additive-only.
- **No duplicate resolution — the load-bearing perf invariant.** ADR-0024 §Tradeoffs row 1 and §Reversibility both stress: the two new facts *ride* the `crane manifest` / digest round-trip `BaseImageProbe` already makes. The naive failure mode is calling the resolver once for the digest and again for the manifest list. The manifest list *is* what the digest resolution returns — `supported_architectures` is read off the *same object*. AC-4's call-counting fence is the mechanical guard; if you find yourself adding a second resolver call, stop — the architecture set is already in hand.
- **Rule 9 — tests verify intent.** AC-6 does not merely assert "an arch-loss is detected" — it asserts `_architectures_lost(("amd64","arm/v7","arm64"), ("amd64","arm64")) == ("arm/v7",)`, naming the *exact dropped platform*. The whole point of G11 is that HITL sees *which* architecture is lost, not a runtime scheduling failure weeks later (ADR-0024 §Context). A test that asserts only "loss is truthy" would pass a degenerate helper that returns `("",)` for everything.
- **Degraded, not refused — the G13 honesty principle.** ADR-0024 §Decision: "The migration is not refused (the mirror may be fine); it is degraded and surfaced." A non-public registry is a *yellow flag*, not a *red flag* — the mirror may carry the CVE patched correctly. The probe's job is to *surface* it (`non_public_registry == True`, a WARN, `AdapterConfidence.Degraded`) so HITL acknowledges the mirror's patch state — not to block the migration. AC-10 is the explicit guard: the probe must still resolve the digest, still classify `kind`, still complete. A probe that short-circuits or refuses on a private mirror has over-reached.
- **Open/Closed marker catalog — `_PUBLIC_REGISTRY_HOSTS`.** The registry allowlist is module-level `Final` data, `in`-checked — never a chained `if host == "docker.io" ... elif host == "ghcr.io"`. AC-11's AST fence is the enforcer. Adding a new public registry (a future Chainguard mirror, an org's blessed registry) is one `frozenset` entry, not an edit to `_classify_registry`. ADR-0024 §Tradeoffs row 4: "the allowlist is data, extensible without an ADR."
- **Registry-host parsing is subtle.** The Docker reference grammar: the segment before the first `/` is a *host* only if it contains a `.` or a `:` (or is `localhost`). `node:18-alpine` has no host → implicit `docker.io`. `acmecorp/node:18` — `acmecorp` is a Docker Hub *namespace*, not a host → still `docker.io` → `non_public_registry == False`. `internal.registry.example/node:18` — `internal.registry.example` contains `.` → it *is* a host → not in the allowlist → `non_public_registry == True`. Get this wrong and a Docker Hub namespace is misclassified as a private registry. The fixtures pin all three shapes.
- **Honest confidence ladder.** ADR-0024 §Tradeoffs row 5: registry-host classification is a heuristic — "a private registry with a public-looking host is misclassified." The accepted failure mode is *false-negative degrades to "treated as public"*, caught later by the build gate. Do not over-engineer host detection; the allowlist + the `.`/`:` rule is the decision.
- **Rule 11 — match the convention.** `base_image_probe.py` (S7-01) is the file you are editing — mirror *its* conventions: `_Frozen`-based slice records, module-level `Final` catalogs, the `_WARNING_IDS` import-time regex check, the warning-ID regex. The two new helpers (`_classify_registry`, `_architectures_lost`) are pure functions in the functional-core style S7-01 already uses for `_classify_from`.
- **Rule 12 — fail loud.** A non-public registry that silently rolls up `non_public_registry == False` is the exact G13 failure — the migration assumes the public patch state and can regress a fix. The WARN + `AdapterConfidence.Degraded` are non-optional: if the host is not in the allowlist, the flag, the warning, and the degraded confidence all fire together. AC-9 asserts all three in one test for that reason.
- **Token-budget guard (Rule 6).** Single-session-implementable at ~4k tokens. The probe edit is small (~40 LOC added); the bulk is fixtures + tests. If manifest-list parsing surprises you (e.g. the resolver stub's `_manifest_list.json` shape does not match what the real `crane manifest` returns), STOP and pin the manifest-list JSON shape against S13-02's `crane`-output expectations before writing the parsing code — a drift here breaks the integration test in S12-02.
