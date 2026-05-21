# Story S16-02 — Recipe transformation contract amendment: typed gather inputs + refusal-or-diff

**Step:** Step 16 — Refusal taxonomy + recipe transformation contract (G5, M2)
**Status:** Ready
**Effort:** L
**Depends on:** S13-02 (`TargetImageContentProbe` → `TargetImageContentSlice` — supplies `shell_present`, `already_satisfied_run_lines`, preinstalled-package inventory), S14-02 (`NodeManifestProbe` `native_modules` slice extension — supplies `native_modules: tuple[NativeModule, ...]`), S15-01 (`DockerfileSecretPatternProbe` → `SecretPatternSlice` — supplies the `external_script` opaque-secret records), S16-01 (the migration refusal taxonomy — `MigrationRefusal`, `PendingHumanReview`, `RefusedOpaqueSecretScript`, `RefusedNativeModulesUnclassified` constructed here)

**ADRs honored:** [Phase 7 ADR-0025](../ADRs/0025-migration-refusal-taxonomy.md) (the recipe gains the ability to refuse with a typed variant instead of always producing a diff — §Consequences: "stories S10-01/S10-02/S10-03 have their acceptance criteria amended"), [Phase 7 ADR-0013](../ADRs/0013-dockerfile-recipe-engine-dockerfile-parse.md) (pure-Python `dockerfile-parse`; **NO `docker build` in the recipe**), [Phase 7 ADR-0014](../ADRs/0014-multi-stage-refactor-recipe-synchronous.md) (the multi-stage recipe stays synchronous — no `asyncio.gather` over per-stage AST work), [Phase 7 ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) (the recipe modules live under the plugin tree; `outcomes.py` refusal variants are ADR-gated)

## Context

`final-design.md §Amendment A §A.3 departure #2` is explicit: "The recipe consumes gather output it did not before. `DockerfileBaseImageSwapTransform` and `DockerfileMultiStageRefactorTransform` (design-of-record §9–10) gain typed inputs — `SecretPatternInventory`, `TargetImageContents`, `NativeModuleSlice` — and gain the ability to **refuse**. The recipe is no longer 'always produces a diff'; it produces a diff *or* a typed refusal. This amends the still-`Ready` recipe stories S10-01/S10-02/S10-03."

This story is that amendment. Before Amendment A, the recipes (S10-01, S10-02) were context-blind: they read the Chainguard catalog and the Dockerfile AST, and **always** produced a `TransformOutcome.Applied(diff)` or a `NotApplicable`. That is unsafe. A naive `FROM` swap can:

- **drop a secret-acquisition path** — the source `COPY`s a shell script and `RUN`s it to fetch a private-registry token; the swap loses it and the build breaks (or worse, succeeds with stale creds);
- **leave a redundant `RUN apk add ca-certificates`** — the target Chainguard image already ships CA certs; the line is dead weight and, in a distroless runtime stage, may not even have `apk`;
- **pick the wrong builder image** — when the repo has native modules (`binding.gyp`, `*.node`), the multi-stage refactor must build against `cgr.dev/chainguard/node:*-dev` (which has the toolchain), not the bare runtime image;
- **emit a diff for a case it cannot transform deterministically** — an opaque `COPY`'d secret script, or native modules with unclassified build-toolchain packages.

This story rewires both recipes to consume the three new gather slices and to refuse — via the **S16-01 refusal taxonomy** — instead of guessing. **It EXPLICITLY amends the acceptance criteria of S10-01, S10-02, and S10-03** (see `## Amendment to S10-01 / S10-02 / S10-03` below). The gap-G5 entrypoint exec-form rewrite is split into its own story (**S16-03**) because it is a self-contained transformation with its own refusal variant; this story lands the gather-input plumbing and the secret/native-module refusal paths.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — Amendment A §17` — `apk`/`apt` build-toolchain classification catalog + the `NodeManifestProbe` `native_modules` slice; "the multi-stage recipe selects the `cgr.dev/chainguard/node:*-dev` builder image when `native_modules` is non-empty."
  - `../phase-arch-design.md §Component design — Amendment A §15` — `DockerfileSecretPatternProbe`: `external_script` classified opaque (ADR-0018 ships no `tree-sitter-bash`) → the recipe must refuse.
  - `../phase-arch-design.md §Component design — Amendment A §22` — the refusal taxonomy; the six variants; `match`/`assert_never` exhaustiveness.
  - `../phase-arch-design.md §Component design §11` — the original `DockerfileBaseImageSwapTransform` / `DockerfileMultiStageRefactorTransform` interfaces this story amends.
- **Phase ADRs:**
  - [`../ADRs/0025-migration-refusal-taxonomy.md`](../ADRs/0025-migration-refusal-taxonomy.md) — §Consequences: "the recipe is no longer 'always produces a diff' — it produces a diff *or* a typed refusal (`final-design.md §A.3 departure #2`). Stories S10-01/S10-02/S10-03 have their acceptance criteria amended." This story IS that amendment.
  - [`../ADRs/0013-dockerfile-recipe-engine-dockerfile-parse.md`](../ADRs/0013-dockerfile-recipe-engine-dockerfile-parse.md) — pure-Python `dockerfile-parse`; **NO `docker build` in the recipe**.
  - [`../ADRs/0014-multi-stage-refactor-recipe-synchronous.md`](../ADRs/0014-multi-stage-refactor-recipe-synchronous.md) — the multi-stage recipe stays synchronous; the AST-walk fence from S10-02 must stay green after this story's edits.
  - [`../ADRs/0018-dockerfile-secret-pattern-probe.md`](../ADRs/0018-dockerfile-secret-pattern-probe.md) — the `external_script` opaque classification this story refuses against.
  - [`../ADRs/0019-target-image-content-probe.md`](../ADRs/0019-target-image-content-probe.md) — `already_satisfied_run_lines` + `shell_present`.
  - [`../ADRs/0020-build-toolchain-classification-catalog.md`](../ADRs/0020-build-toolchain-classification-catalog.md) — the `native_modules` slice + the `*-dev` builder-image selection rule.
- **Source design:**
  - `../final-design.md §Amendment A §A.3 departure #2` (the recipe gains typed inputs + the ability to refuse), §A.2 gap M2 + gap G1/G2/G3.
- **Existing code:**
  - `plugins/distroless-migration--node--npm/recipes/dockerfile_base_image_swap.py` (S10-01) — the recipe this story amends. Read its `applicability()` decision tree and `apply()` rebuild path.
  - `plugins/distroless-migration--node--npm/recipes/dockerfile_multi_stage.py` (S10-02) — the second recipe this story amends; synchronous per-stage `for` loop.
  - `src/codegenie/transforms/outcomes.py` (post-S16-01) — `MigrationRefusal`, `PendingHumanReview`, `RefusedOpaqueSecretScript`, `RefusedNativeModulesUnclassified`, `RefusalSourceLocation`.
  - `src/codegenie/transforms/transform.py` — `Transform` ABC; `TransformOutcome` shape.
  - `plugins/distroless-migration--node--npm/data/loader.py` (S9-01) — the catalog loader; the precedent for how a gather slice is loaded / injected.
  - `tests/golden/dockerfile-diffs/alpine-to-chainguard.diff` + `multi-stage-refactor.diff` (S10-01 / S10-02 goldens) — the happy-path diffs that MUST stay byte-equal after this story's gather-input plumbing.

## Amendment to S10-01 / S10-02 / S10-03

Per [ADR-0025 §Consequences](../ADRs/0025-migration-refusal-taxonomy.md) and `final-design.md §A.3 departure #2`, this story **explicitly amends** the acceptance criteria of the three still-`Ready` Step-10 recipe/gate stories. The amendment is *additive* — no existing AC of S10-01/S10-02/S10-03 is deleted; the following ACs are appended:

- **S10-01 (`DockerfileBaseImageSwapTransform`) — amended:**
  - **+AC-20 — typed gather inputs.** `DockerfileBaseImageSwapTransform.__init__` gains three injected slice parameters (`secret_patterns: SecretPatternSlice`, `target_image: TargetImageContentSlice`, `native_modules: tuple[NativeModule, ...]`), DI'd by the plugin's `api.py` exactly as the catalog already is. The four-attribute `Transform` ABC compliance is unchanged.
  - **+AC-21 — redundant `RUN` stripping.** `apply()` strips `RUN` lines whose normalized text matches an entry in `target_image.already_satisfied_run_lines` (e.g. `RUN apk add --no-cache ca-certificates` when the target image already ships CA certs). The S10-01 golden diff is regenerated to include the strip; the regeneration is hand-reviewed.
  - **+AC-22 — refuse on opaque secret.** When `secret_patterns` carries an `external_script` record whose script the probe could not parse, `apply()` returns `RemediationOutcome.PendingHumanReview(refusal=RefusedOpaqueSecretScript(...))` instead of a diff.
- **S10-02 (`DockerfileMultiStageRefactorTransform`) — amended:**
  - **+AC-20 — typed gather inputs** (same three slices as S10-01 +AC-20).
  - **+AC-21 — `*-dev` builder selection.** When `native_modules` is non-empty, the rewritten builder stage's `FROM` is the `cgr.dev/chainguard/node:<tag>-dev` image (the dev variant carries the build toolchain), not the bare runtime image. When `native_modules` is empty, the builder stage selection is unchanged from S10-02.
  - **+AC-22 — refuse on unclassified native modules.** When `native_modules` is non-empty but one or more required build-toolchain packages are absent from the `apk`/`apt` classification catalog, `apply()` returns `PendingHumanReview(refusal=RefusedNativeModulesUnclassified(...))` instead of a diff.
  - **+AC-23 — synchronous shape preserved.** The S10-02 AST-walk fence (`tests/fence/test_dockerfile_multi_stage_no_asyncio_gather.py`) stays green — the gather-input plumbing introduces no `asyncio.gather`.
- **S10-03 (`DockerfilePolicyGate`) — amended:**
  - **+AC-20 — refusal-aware gate.** `DockerfilePolicyGate` accepts a `PendingHumanReview` recipe outcome as a *valid, non-failing* input: a refusal is not a policy violation. The gate `match`es the full `RemediationOutcome` umbrella (five arms post-S16-01) with `assert_never`; a `PendingHumanReview` short-circuits the gate to a pass-through (the human review, not the gate, is the next step).

This story's own ACs below cover the recipe-side implementation; S10-03's +AC-20 is implemented when S10-03 executes against this amended scope.

## Goal

Amend `plugins/distroless-migration--node--npm/recipes/dockerfile_base_image_swap.py` and `dockerfile_multi_stage.py` so both recipes:

1. accept three new DI'd gather slices — `SecretPatternSlice` (S15-01), `TargetImageContentSlice` (S13-02), `native_modules: tuple[NativeModule, ...]` (S14-02) — in their constructors;
2. strip `RUN` lines matching `target_image.already_satisfied_run_lines` (the redundant-layer cleanup);
3. select the `cgr.dev/chainguard/node:*-dev` builder image in the multi-stage recipe when `native_modules` is non-empty;
4. **refuse** — return `RemediationOutcome.PendingHumanReview(refusal=...)` instead of a `TransformOutcome.Applied(diff)` — when the case cannot be transformed deterministically: an opaque `external_script` secret → `RefusedOpaqueSecretScript`; native modules with unclassified build-toolchain packages → `RefusedNativeModulesUnclassified`.

The happy-path golden diffs stay deterministic and byte-stable (regenerated only where +AC-21's strip changes them). Neither recipe calls `docker build`. The multi-stage recipe stays synchronous.

## Acceptance criteria

### Typed gather inputs

- [ ] **AC-1 — Three new DI'd constructor parameters, both recipes.** `DockerfileBaseImageSwapTransform.__init__` and `DockerfileMultiStageRefactorTransform.__init__` each gain keyword-only parameters `secret_patterns: SecretPatternSlice`, `target_image: TargetImageContentSlice`, `native_modules: tuple[NativeModule, ...]`. The existing `catalog` + `logger` parameters are unchanged. The slices are **injected** — the recipe does NOT load them itself; the plugin `api.py` constructs the recipe with the slices read from the gather output. Test: two recipe instances with different injected slices produce different outcomes for the same `ApplyContext`.
- [ ] **AC-2 — Slice types imported from their owning probe modules.** `SecretPatternSlice` is imported from the S15-01 secret-pattern probe module; `TargetImageContentSlice` from the S13-02 target-image probe module; `NativeModule` from the S14-02 `NodeManifestProbe` slice. The recipe does not re-declare these types. If a slice type is not yet shipped at execution time (S13-02/S14-02/S15-01 land first per `final-design.md §A.4` sequencing), this story is `BLOCKED` until they do — record in the attempt log; do NOT stub the slice types.
- [ ] **AC-3 — `Transform` ABC compliance preserved.** Both recipes still satisfy `isinstance(t, Transform)`; the four class-level ABC attributes (`transform_id`, `diff_bytes`, `files_changed`, `provenance`) and the `applicability()` + `apply()` signatures are unchanged in shape. The added constructor parameters do not break the ABC.

### Redundant `RUN`-line stripping

- [ ] **AC-4 — Redundant `RUN` line stripped from the diff.** Given a Dockerfile containing `RUN apk add --no-cache ca-certificates` and a `target_image` slice whose `already_satisfied_run_lines` contains the normalized form of that line, `apply()` produces a diff that **deletes** that `RUN` line. Test fixture: `tests/fixtures/recipes/dockerfile-redundant-run/Dockerfile` (a base-image-swap candidate with one redundant `RUN`). The diff is byte-equal to a regenerated, hand-reviewed golden.
- [ ] **AC-5 — Normalization is whitespace/flag-order tolerant but conservative.** `RUN  apk   add  --no-cache  ca-certificates` (extra whitespace) matches; `RUN apk add --no-cache ca-certificates curl` (extra package) does NOT match — stripping a line that does more than the satisfied set would drop `curl`. A line is stripped only when its *entire* effect is in `already_satisfied_run_lines`. Test pins both the match and the conservative non-match, with a docstring naming why over-stripping is unsafe.
- [ ] **AC-6 — Non-redundant `RUN` lines untouched.** A `RUN npm ci` or `RUN apk add --no-cache curl` (not in `already_satisfied_run_lines`) survives the diff unchanged. Test fixture covers a Dockerfile with one redundant + one non-redundant `RUN`.

### `*-dev` builder selection (multi-stage recipe)

- [ ] **AC-7 — `*-dev` builder image when native modules present.** Given `native_modules` non-empty (e.g. `(NativeModule(name="bcrypt", ...),)`), `DockerfileMultiStageRefactorTransform.apply()` produces a builder stage whose `FROM` is `cgr.dev/chainguard/node:<tag>-dev@<digest>` (the dev variant — has `gcc`, `make`, `python3`). The `<tag>` and `<digest>` come from the catalog's `*-dev` row. Test fixture: `tests/fixtures/recipes/dockerfile-multi-stage/native-modules/Dockerfile`.
- [ ] **AC-8 — Bare builder image when native modules absent.** Given `native_modules` empty, the builder-stage `FROM` selection is unchanged from S10-02's behavior (the non-dev image). The S10-02 `multi-stage-refactor.diff` golden stays byte-equal — this story's plumbing must not perturb the pure-JS path.
- [ ] **AC-9 — `*-dev` selection is deterministic.** Applying the recipe twice to the same native-module fixture yields a byte-identical diff. The `*-dev` row lookup is O(1) dict access against the injected catalog; no nondeterminism.

### Refusal-or-diff

- [ ] **AC-10 — Opaque secret script → `RefusedOpaqueSecretScript`, not a diff.** Given a `secret_patterns` slice carrying an `external_script` record (a `COPY`'d-then-`RUN` shell script the probe classified opaque), `apply()` returns `RemediationOutcome.PendingHumanReview(refusal=RefusedOpaqueSecretScript(source=..., script_path=...))`. The returned outcome's `refusal.source.file_path` names the Dockerfile and `refusal.source.index` is the 0-based instruction index of the `RUN <script>` line. `apply()` does NOT return a `TransformOutcome.Applied` and does NOT raise. Test fixture: `tests/fixtures/recipes/dockerfile-opaque-secret/` (a `Dockerfile` + a `COPY`'d `fetch-token.sh`).
- [ ] **AC-11 — Unclassified native modules → `RefusedNativeModulesUnclassified`, not a diff.** Given `native_modules` non-empty but at least one required build-toolchain package absent from the `apk`/`apt` classification catalog, `DockerfileMultiStageRefactorTransform.apply()` returns `PendingHumanReview(refusal=RefusedNativeModulesUnclassified(source=..., unclassified_packages=(...,)))`. The `unclassified_packages` tuple is non-empty and names exactly the packages that could not be classified. Test fixture: a native-module Dockerfile referencing an exotic toolchain package not in the catalog.
- [ ] **AC-12 — Refusal carries an accurate source location.** For both refusal paths, the `RefusalSourceLocation` payload is verifiable: `file_path` is a repo-relative path that exists in the fixture, `index` is the correct 0-based instruction/line index of the offending construct. Test asserts the exact `index` value against the known fixture line, with a docstring naming ADR-0025 §A.1 ("naming the exact source location").
- [ ] **AC-13 — Happy path still produces a clean diff.** Given a Dockerfile with no opaque secrets and (for the multi-stage recipe) no unclassified native modules, both recipes still produce a `TransformOutcome.Applied(diff)`. The S10-01 / S10-02 golden diffs (regenerated only for S10-01 +AC-21's strip) are byte-equal. A refusal is the *exception*, not the default — the happy path is unchanged.
- [ ] **AC-14 — `apply()` return type is the union, not a narrowed type.** `apply()`'s annotated return type is widened to admit both `TransformOutcome` and `RemediationOutcome.PendingHumanReview` (whichever umbrella the project's recipe contract uses — see `## Notes for the implementer` on reconciling `TransformOutcome` vs `RemediationOutcome`). The caller (`api.py` / the orchestrator) `match`es the result; the refusal arm is exhaustively handled.

### Invariants preserved

- [ ] **AC-15 — No `docker build` in either recipe.** The S10-01 AST-walk fence (`tests/fence/test_dockerfile_swap_no_docker_build.py`) and an equivalent fence for `dockerfile_multi_stage.py` stay green — this story's edits introduce no `subprocess.run`, no `run_external_cli`, no `docker buildx`. Building is `DistrolessBuildGate`'s job (S10-04), unchanged.
- [ ] **AC-16 — Multi-stage recipe stays synchronous.** The S10-02 AST-walk fence (`tests/fence/test_dockerfile_multi_stage_no_asyncio_gather.py`) stays green — no `asyncio.gather`, no `run_in_executor` introduced by the gather-input plumbing (ADR-0014).
- [ ] **AC-17 — Determinism preserved.** Both recipes remain byte-deterministic: same `ApplyContext` + same injected slices → same diff (or same refusal). The idempotence properties from S10-01 AC-8 / S10-02 AC-10 still hold.

### Gates

- [ ] **AC-18** — `mypy --strict` clean on `plugins/distroless-migration--node--npm/recipes/` and `src/`.
- [ ] **AC-19** — `ruff check` + `ruff format --check` clean on the touched recipe modules and every touched test file.
- [ ] **AC-20** — `make lint-imports` green; `make check` end-to-end green; Phase 3–6.5 regression suite passes; `bench/vuln-remediation/` cassette replay byte-equal.

## Implementation outline

1. **Confirm dependencies shipped.** `SecretPatternSlice` (S15-01), `TargetImageContentSlice` (S13-02), `NativeModule` + the `native_modules` slice (S14-02), and the S16-01 refusal taxonomy must all exist. If any is missing, mark this story `BLOCKED` and record the missing dependency in the attempt log — do NOT stub.
2. **Amend both constructors** — add the three keyword-only slice parameters to `DockerfileBaseImageSwapTransform.__init__` and `DockerfileMultiStageRefactorTransform.__init__`; store them as private attributes. Update the plugin `api.py` (S8-03) construction sites to read the slices from gather output and pass them in.
3. **Redundant `RUN` stripping** — add a pure helper `_strip_satisfied_run_lines(structure, already_satisfied) -> structure` that, for each `RUN` instruction, normalizes its text and drops it iff its *entire* effect is in `already_satisfied_run_lines` (AC-4, AC-5, AC-6). Apply it in `DockerfileBaseImageSwapTransform.apply()` before the diff is computed.
4. **`*-dev` builder selection** — in `DockerfileMultiStageRefactorTransform.apply()`, when `native_modules` is non-empty, resolve the builder-stage `FROM` from the catalog's `*-dev` row instead of the bare row (AC-7, AC-8). The selection is a pure function of `(native_modules_non_empty, catalog)`.
5. **Opaque-secret refusal** — add a pure pre-check `_find_opaque_secret(secret_patterns, structure) -> RefusedOpaqueSecretScript | None`. If `secret_patterns` carries an `external_script` record, build the `RefusalSourceLocation` (Dockerfile path + the `RUN <script>` instruction index) and return the refusal. In `apply()`, if the pre-check returns a refusal, return `PendingHumanReview(refusal=...)` immediately (AC-10).
6. **Unclassified-native-modules refusal** — add a pure pre-check `_find_unclassified_native_modules(native_modules, classification_catalog) -> RefusedNativeModulesUnclassified | None`. If any required build-toolchain package is absent from the `apk`/`apt` catalog, build the refusal naming exactly those packages and return it. In `DockerfileMultiStageRefactorTransform.apply()`, refuse before computing the diff (AC-11).
7. **Widen `apply()`'s return type** — to admit `PendingHumanReview` alongside the existing `TransformOutcome.Applied` / `NotApplicable` (AC-14). Reconcile the `TransformOutcome` vs `RemediationOutcome` umbrella per the Notes.
8. **Regenerate the S10-01 golden** — `tests/golden/dockerfile-diffs/alpine-to-chainguard.diff` changes because +AC-21 now strips a redundant `RUN`. Hand-review the regenerated golden. The S10-02 `multi-stage-refactor.diff` golden stays byte-equal (the pure-JS path is unperturbed — AC-8).
9. **New fixtures + tests** — `dockerfile-redundant-run/`, `dockerfile-multi-stage/native-modules/`, `dockerfile-opaque-secret/`, and the unclassified-native-modules fixture; one paired unit test per fixture; refusal-source-location assertions.
10. **Run the S10-01 / S10-02 fences** — confirm `test_dockerfile_swap_no_docker_build.py` and `test_dockerfile_multi_stage_no_asyncio_gather.py` stay green.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/transforms/recipes/test_recipe_refusal.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest


def _swap_recipe(*, catalog, secret_patterns, target_image, native_modules, logger):
    from plugins.distroless_migration__node__npm.recipes.dockerfile_base_image_swap import (
        DockerfileBaseImageSwapTransform,
    )

    return DockerfileBaseImageSwapTransform(
        catalog=catalog,
        secret_patterns=secret_patterns,
        target_image=target_image,
        native_modules=native_modules,
        logger=logger,
    )


def test_swap_strips_redundant_run_line(
    tmp_path, seeded_catalog, logger,
    redundant_run_dockerfile, target_image_with_ca_certs,
    empty_secret_slice, empty_native_modules,
):
    """+AC-21: the target Chainguard image already ships CA certs, so
    `RUN apk add ca-certificates` is dead weight — strip it from the diff."""
    tx = _swap_recipe(
        catalog=seeded_catalog, secret_patterns=empty_secret_slice,
        target_image=target_image_with_ca_certs,
        native_modules=empty_native_modules, logger=logger,
    )
    ctx = _ctx(tmp_path, redundant_run_dockerfile)
    outcome = tx.apply(ctx)
    assert outcome.kind == "applied"
    diff = outcome.transform.diff_bytes.decode()
    assert "-RUN apk add --no-cache ca-certificates" in diff


def test_swap_refuses_opaque_secret_script(
    tmp_path, seeded_catalog, logger,
    opaque_secret_slice, target_image_default, empty_native_modules,
):
    """+AC-22 / ADR-0025: a COPY'd-then-RUN shell script the secret-pattern
    probe could not parse → RefusedOpaqueSecretScript, NOT a diff. Shipping a
    swap that drops the secret-acquisition path is the unacceptable outcome."""
    from codegenie.transforms import PendingHumanReview, RefusedOpaqueSecretScript

    tx = _swap_recipe(
        catalog=seeded_catalog, secret_patterns=opaque_secret_slice,
        target_image=target_image_default,
        native_modules=empty_native_modules, logger=logger,
    )
    ctx = _ctx(tmp_path, _OPAQUE_SECRET_DOCKERFILE)
    outcome = tx.apply(ctx)
    assert isinstance(outcome, PendingHumanReview)
    assert isinstance(outcome.refusal, RefusedOpaqueSecretScript)
    assert outcome.refusal.source.file_path.endswith("Dockerfile")
    assert outcome.refusal.script_path.endswith("fetch-token.sh")


def test_multi_stage_selects_dev_builder_on_native_modules(
    tmp_path, seeded_catalog, logger,
    empty_secret_slice, target_image_default, bcrypt_native_modules,
):
    """+AC-21 (S10-02) / ADR-0020: native modules need the build toolchain —
    the builder stage must FROM cgr.dev/chainguard/node:<tag>-dev."""
    from plugins.distroless_migration__node__npm.recipes.dockerfile_multi_stage import (
        DockerfileMultiStageRefactorTransform,
    )

    tx = DockerfileMultiStageRefactorTransform(
        catalog=seeded_catalog, secret_patterns=empty_secret_slice,
        target_image=target_image_default,
        native_modules=bcrypt_native_modules, logger=logger,
    )
    ctx = _ctx(tmp_path, _NATIVE_MODULE_DOCKERFILE)
    outcome = tx.apply(ctx)
    assert outcome.kind == "applied"
    diff = outcome.transform.diff_bytes.decode()
    assert "cgr.dev/chainguard/node:" in diff and "-dev@sha256:" in diff


def test_multi_stage_refuses_unclassified_native_modules(
    tmp_path, seeded_catalog, logger,
    empty_secret_slice, target_image_default, exotic_native_modules,
):
    """+AC-22 (S10-02) / ADR-0025: a native module whose build-toolchain
    package is not in the apk/apt classification catalog cannot be staged
    deterministically → RefusedNativeModulesUnclassified, NOT a diff."""
    from codegenie.transforms import (
        PendingHumanReview, RefusedNativeModulesUnclassified,
    )
    from plugins.distroless_migration__node__npm.recipes.dockerfile_multi_stage import (
        DockerfileMultiStageRefactorTransform,
    )

    tx = DockerfileMultiStageRefactorTransform(
        catalog=seeded_catalog, secret_patterns=empty_secret_slice,
        target_image=target_image_default,
        native_modules=exotic_native_modules, logger=logger,
    )
    ctx = _ctx(tmp_path, _NATIVE_MODULE_DOCKERFILE)
    outcome = tx.apply(ctx)
    assert isinstance(outcome, PendingHumanReview)
    assert isinstance(outcome.refusal, RefusedNativeModulesUnclassified)
    assert len(outcome.refusal.unclassified_packages) >= 1
```

State why it fails: `TypeError` — `DockerfileBaseImageSwapTransform.__init__` / `DockerfileMultiStageRefactorTransform.__init__` do not yet accept `secret_patterns` / `target_image` / `native_modules`; `apply()` never returns a `PendingHumanReview`.

### Green — minimal pass

- Add the three keyword-only slice parameters to both constructors; store them.
- Add `_strip_satisfied_run_lines`, `_find_opaque_secret`, `_find_unclassified_native_modules` as pure module-level helpers.
- Wire the helpers into `apply()`: refuse-first (opaque secret, then unclassified native modules), then strip redundant `RUN` lines, then `*-dev` builder selection, then the existing diff path.
- Update `api.py` construction sites to read + inject the slices.
- Regenerate the S10-01 golden; add the new fixtures + paired tests.

### Refactor

- Hoist the refusal pre-checks to pure, independently-testable functions: `_find_opaque_secret(...) -> RefusedOpaqueSecretScript | None` and `_find_unclassified_native_modules(...) -> RefusedNativeModulesUnclassified | None`. Functional core: the impurity stays in `apply()`.
- Pull the `RUN`-line normalization into a `_normalize_run_text(raw: str) -> str` helper with its own unit tests — it is the load-bearing piece of AC-5's conservative match.
- Confirm the S10-01 / S10-02 AST-walk fences (`no_docker_build`, `no_asyncio_gather`) are green after the refactor.
- Confirm the S10-02 pure-JS `multi-stage-refactor.diff` golden is byte-equal (the `*-dev` branch is not taken when `native_modules` is empty).
- Add a module-docstring line to each recipe naming ADR-0025 and the refusal-or-diff contract ("`apply()` returns a diff OR a typed `PendingHumanReview` refusal — it is no longer 'always produces a diff'; see ADR-0025").

## Files to touch

| Path | Why |
|---|---|
| `plugins/distroless-migration--node--npm/recipes/dockerfile_base_image_swap.py` | Amend constructor (3 new slices); add redundant-`RUN` strip; add opaque-secret refusal path; widen `apply()` return type. |
| `plugins/distroless-migration--node--npm/recipes/dockerfile_multi_stage.py` | Amend constructor (3 new slices); add `*-dev` builder selection; add unclassified-native-modules refusal path; widen `apply()` return type. |
| `plugins/distroless-migration--node--npm/api.py` | Read the three gather slices from gather output; pass them to both recipe constructors (S8-03 DI site). |
| `tests/fixtures/recipes/dockerfile-redundant-run/Dockerfile` | NEW — base-swap candidate with a redundant `RUN apk add ca-certificates` (AC-4). |
| `tests/fixtures/recipes/dockerfile-multi-stage/native-modules/Dockerfile` | NEW — native-module multi-stage fixture (AC-7). |
| `tests/fixtures/recipes/dockerfile-opaque-secret/Dockerfile` | NEW — `COPY`'d-then-`RUN` opaque secret script (AC-10). |
| `tests/fixtures/recipes/dockerfile-opaque-secret/fetch-token.sh` | NEW — the opaque script the probe cannot parse. |
| `tests/unit/transforms/recipes/test_recipe_refusal.py` | NEW — anchors TDD red; AC-4..AC-13. |
| `tests/unit/transforms/recipes/test_dockerfile_base_image_swap.py` | Extend — AC-1, AC-5, AC-6 (redundant-`RUN` match/non-match). |
| `tests/unit/transforms/recipes/test_dockerfile_multi_stage.py` | Extend — AC-1, AC-8 (`*-dev` vs bare builder selection), AC-9. |
| `tests/golden/dockerfile-diffs/alpine-to-chainguard.diff` | Regenerate — S10-01 +AC-21's redundant-`RUN` strip changes the diff; hand-reviewed. |

## Out of scope

- **The refusal taxonomy types themselves** — `MigrationRefusal`, `PendingHumanReview`, `RefusedOpaqueSecretScript`, `RefusedNativeModulesUnclassified` are landed by **S16-01**. This story *constructs* them.
- **The gap-G5 entrypoint exec-form rewrite** + `RefusedNonDeterministicEntrypoint` — **S16-03**. This story does not touch `ENTRYPOINT`/`CMD` rewriting beyond what S10-01/S10-02 already do.
- **The gather probes that produce the slices** — `DockerfileSecretPatternProbe` (S15-01), `TargetImageContentProbe` (S13-02), the `NodeManifestProbe` `native_modules` extension (S14-02). This story *consumes* their slices.
- **`DockerfilePolicyGate` becoming refusal-aware** — S10-03's +AC-20 (enumerated above); implemented when S10-03 executes against the amended scope.
- **`docker build` / `docker buildx`** — `DistrolessBuildGate` (S10-04), unchanged. No build in the recipe (ADR-0013).
- **`MigrationConfidence` rollup** — Step 17 / ADR-0026.

## Notes for the implementer

- **This story is the explicit S10-01/S10-02/S10-03 AC amendment.** ADR-0025 §Consequences names it; `final-design.md §A.3 departure #2` names it. The `## Amendment to S10-01 / S10-02 / S10-03` section above enumerates the appended ACs. When you execute this story, the S10-01/S10-02 stories' own ACs are *extended*, not rewritten — both stories' golden tests and fences must still be honored.
- **Refuse-first, then transform.** The control flow in `apply()` is: (1) check for an opaque secret → refuse; (2) check for unclassified native modules → refuse (multi-stage only); (3) only then strip redundant `RUN` lines, select the builder, compute the diff. A refusal must short-circuit *before* any diff work — producing a diff and a refusal is an illegal state. Order the pre-checks deterministically (opaque secret before native modules) so a Dockerfile that trips both refuses the same way every run.
- **`TransformOutcome` vs `RemediationOutcome` — reconcile carefully.** S10-01/S10-02 return `TransformOutcome` (the recipe-engine outcome). The refusal taxonomy lands on `RemediationOutcome.PendingHumanReview` (the orchestrator outcome — S16-01). These are two umbrellas. Resolve the mismatch one of two ways, and **state which in the attempt log**: (a) the recipe returns `TransformOutcome | PendingHumanReview` and `api.py` / the orchestrator lifts the refusal into `RemediationOutcome`; or (b) S16-01's `PendingHumanReview` is reachable from the recipe layer because `RemediationOutcome` is the contract the recipe's caller already `match`es. Read `src/codegenie/transforms/recipe_engine.py` and `transform.py` before deciding — do not guess (Rule 8). The cleaner choice is likely (a): the recipe stays in the `TransformOutcome` domain and emits a refusal variant the engine wraps. Whatever you pick, AC-14's widened return type must be honest and the caller's `match` exhaustive.
- **Conservative `RUN`-line stripping (AC-5) is the safety-critical piece.** Strip a `RUN` line *only* when its entire effect is in `already_satisfied_run_lines`. `RUN apk add --no-cache ca-certificates curl` is NOT redundant just because `ca-certificates` is satisfied — stripping it drops `curl`. The normalization must compare the *full set of packages/effects*, not a substring. Over-stripping ships a broken image — exactly the failure mode Amendment A exists to prevent. Test the conservative non-match explicitly.
- **`*-dev` selection is data, not a branch ladder.** The catalog (S9-01) should carry both the runtime row and the `-dev` row per Chainguard image; the selection is `catalog.dev_row(image)` when `native_modules` is non-empty else `catalog.runtime_row(image)`. If the catalog does not yet carry `-dev` rows, that is an S9-01 / S14-02 gap — surface it; do not hardcode a `-dev` tag string in the recipe.
- **No `docker build`, still.** AC-15's fences are mechanical. The gather slices tell the recipe *what the target image provides* — they do not invite the recipe to build anything. If you reach for `subprocess.run(["docker", ...])`, stop: building is the gate's job (S10-04). ADR-0013 is the citation.
- **The multi-stage recipe stays synchronous.** AC-16 / ADR-0014. The gather-input plumbing is plain attribute reads and pure helper calls — nothing about it needs `async`. The S10-02 AST-walk fence will refuse an `asyncio.gather`; do not introduce one for "consistency."
- **Happy path must stay byte-stable.** AC-13 / AC-8: a Dockerfile with no opaque secrets and no native modules must produce the *same* diff as before (modulo S10-01 +AC-21's redundant-`RUN` strip, which regenerates the S10-01 golden once, hand-reviewed). Refusal is the exception path; the common case is unchanged. If the S10-02 `multi-stage-refactor.diff` golden drifts, the `native_modules`-empty branch was perturbed — that is a bug.
- **DI the slices; do not load them in the recipe.** Same discipline as S10-01's catalog injection: `api.py` reads the gather output once at plugin-load / workflow-setup time and constructs the recipe with the slices. The recipe never reads `.codegenie/context/raw/*.json` itself — that would re-parse on every `apply()` and break determinism if the file mutated mid-workflow.
- **Source-location accuracy matters (AC-12).** The whole value of the refusal taxonomy is that the human merger sees *which line* the recipe declined on. When you build the `RefusalSourceLocation`, the `index` must be the real 0-based Dockerfile-instruction index of the offending `RUN`/`COPY` — `dockerfile-parse`'s `structure` carries `startline`; map it correctly. A wrong index is worse than no index: it points the reviewer at innocent code.
- **If a dependency slice is not shipped, mark `BLOCKED-PARTIAL` and log it.** Per `final-design.md §A.4`, the gather probes (Steps 13–15) land before this Step-16 recipe story. If S13-02/S14-02/S15-01 have not executed when this story is picked up, do NOT stub `SecretPatternSlice` / `TargetImageContentSlice` / `NativeModule` — that forks the contract. Mark the story `BLOCKED-PARTIAL`, name the missing dependency in the attempt log, and stop. Honest blocking beats a stubbed contract (Rule 12).
