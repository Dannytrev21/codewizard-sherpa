# Story S18-01 — `transformations_applied` typed list + migration observability events (size / rollback / attestation)

**Step:** Step 18 — Migration observability (G14–G17, M3)
**Status:** Ready
**Effort:** M
**Depends on:** S16-03 (recipe transformation contract — `DockerfileBaseImageSwapTransform` / `DockerfileMultiStageRefactorTransform` produce the structural edits this story labels into `TransformationKind` variants; without it there is no migration record to attach the list to), S17-01 (`MigrationConfidence` rollup + the migration-record shape the orchestrator assembles — this story extends that record additively)
**ADRs honored:** Phase 7 ADR-0027 (migration observability bundle — the typed `transformations_applied` list + the three enrichment events; all WARN/enrichment, none blocks), Phase 7 ADR-0029 (byte-edit allowlist amendment — every net-new source file this story creates is enumerated; the migration-record edit is the one ADR-gated additive field), Phase 7 ADR-0028 (`ALLOWED_BINARIES` amendment for `crane` — the attestation/SBOM fetch path), Phase 7 ADR-0025 (refusal taxonomy — `TransformationKind` mirrors its closed-sum-type discipline), Phase 7 ADR-0026 (`MigrationConfidence` — same "make the outcome a typed value, not a string" pattern), production ADR-0009 (humans always merge — the migration's effect must be legible in the PR or the merge gate is a rubber stamp), production ADR-0034 (event sourcing — the spanning log is canonical, the PR description is a projection)

## Context

A distroless migration is a non-trivial structural change. The recipe swaps the `FROM`, drops `RUN` lines the target Chainguard image makes redundant, may rewrite a `HEALTHCHECK`, may add `--chown` to `COPY` lines, and a multi-stage refactor can quietly balloon the compressed image. `production ADR-0009` ends autonomy at PR creation: a human always merges. If that human cannot see *what the recipe did* and *what risk it carries*, the "humans always merge" gate is a rubber stamp, not a review.

`final-design.md §Amendment A §A.2` catalogs four observability gaps that all resolve to **WARN** (`§A.1` — every gap is GATHER, REFUSE, or WARN; G14–G17 and M3 are all WARN): G14 (image-size delta), G15 (rollback runbook), G16 (compliance attestation diff), M3 (structured `transformations_applied` list). `phase-arch-design.md §Component design — Amendment A §23` names the deliverable a *migration observability bundle*. None of it is a *decision* the system makes — the migration already happened (or refused, ADR-0025); observability *enriches* the PR with what happened.

ADR-0027 §Decision picks **Option B** — a typed `transformations_applied` list plus typed enrichment events; the PR description is *rendered* from the typed data, never hand-authored. ADR-0027 §Options rejects the free-text alternative (Option A) precisely because prose is not machine-readable: Phase 11's merge-gate and Phase 13.5's portal cannot consume it, and an engineer editing the recipe can silently forget to update the prose. **The data is the source of truth; the prose is a view.**

This story ships three things, all WARN, none blocking:

1. **`transformations_applied: tuple[TransformationKind, ...]`** on the migration record. `TransformationKind` is a closed sum type (`FromSwapped`, `RedundantRunDropped`, `HealthcheckRewritten`, `ChownAdded`, `EntrypointRewrittenToExecForm`) — each variant carries the affected Dockerfile instruction index. This is gap **M3**.
2. **Two typed enrichment events** into the spanning log (`production ADR-0034`): `MigrationSizeRegression` (pre/post compressed image size — a multi-stage refactor can balloon the image; gap **G14**), and `pre_migration_image_ref` capture so the PR can carry a rollback runbook — *"to roll back, redeploy `<digest>`"* (gap **G15**).
3. **An attestation diff** (gap **G16**) — Chainguard ships a signed SBOM + SLSA provenance the source image lacks; the PR surfaces the gained attestations. The diff reads the Chainguard-published artifacts via `crane` (ADR-0028).

The PR-description renderer reads `transformations_applied` + the events and emits operator prose plus a rollback line. A goldens fixture locks the rendered shape — ADR-0027 §Decision: *"a goldens fixture catches drift at every PR."*

Two failure modes the story explicitly defends. (1) **Enrichment that silently fails must WARN, not vanish.** If `crane` cannot fetch the attestation, or `dive` cannot weigh the post-migration image, the bundle item is *missing* — the PR description degrades (no size line, no attestation diff) but the migration still produces a PR. Per ADR-0027 §Tradeoffs the failure is loud: a `migration_observability.*` warning ID is emitted, never a swallowed exception. (2) **The migration-record edit is the one ADR-gated additive field.** Per ADR-0029 the byte-edit allowlist enumerates every net-new source file; the `transformations_applied` field is the single additive edit to an existing record type, justified by ADR-0027 §Consequences.

The cross-CVE content-cache reuse of `ShellInvocationTraceProbe` — gap **G17**, the fourth item in ADR-0027's bundle — is **S18-02**, a sibling story, and is explicitly out of scope here.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — Amendment A §23` (lines 1067–1076) — the migration observability bundle: `transformations_applied` list, `MigrationSizeRegression`, `pre_migration_image_ref` capture, attestation diff; "WARN — none of these block."
  - `../phase-arch-design.md §Component design — Amendment A §21` (lines 1043–1048) — the `MigrationConfidence` aggregator + the migration-record shape S17-01 lands; this story extends that record additively.
  - `../phase-arch-design.md §Data model` (lines 1080–1133) — the `_TypedEvent` base + `RequiresMultiPluginCoordination` precedent for a typed Pydantic event; the identifier newtypes (`ImageRef`, `ImageDigest`, `CveId`, `WorkflowId`).
  - `../phase-arch-design.md §Observability` (line 1232) — every event in the spanning log + every warning ID emitted by a probe goes through Phase 0's structured logger.
- **Phase ADRs:**
  - `../ADRs/0027-migration-observability-bundle.md §Decision` — the three-item bundle this story ships; §Tradeoffs (enrichment that fails must WARN visibly); §Consequences (the additive `transformations_applied` field, the three event variants, the renderer + goldens fixture).
  - `../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md` — the byte-edit allowlist; every net-new file below is one enumerated row; the migration-record edit is the ADR-gated additive field.
  - `../ADRs/0028-allowed-binaries-amendment-crane.md` — `crane` is the allowlisted binary the attestation diff (G16) calls.
  - `../ADRs/0025-migration-refusal-taxonomy.md §Decision` — the closed-sum-type discipline `TransformationKind` mirrors.
  - `../ADRs/0026-migration-confidence-aggregation.md` — the `MigrationConfidence` rollup; same "typed value, not a string" pattern.
- **Production ADRs:**
  - `../../../production/adrs/0009-humans-always-merge.md` — autonomy ends at PR creation; the migration's effect must be legible.
  - `../../../production/adrs/0034-event-sourcing-canonical-primitive.md` — the spanning log is canonical; the PR description is a projection, never the source of truth.
- **Existing code:**
  - `src/codegenie/cache/keys.py` / `src/codegenie/cache/store.py` — content-addressed cache; the `crane`/`dive` outputs feeding the size + attestation lines should be derived deterministically (a stale enrichment is a WARN, never a crash).
  - `src/codegenie/exec/__init__.py` — `ALLOWED_BINARIES`; `crane` is added by ADR-0028 (verify the row exists; if not, that is an S-prior-story precondition, not an inline edit here).
- **Sibling stories:**
  - `S11-01-requires-coordination-typed-event.md` — the typed-Pydantic-event precedent (`_TypedEvent` base, `kind` discriminator literal, `emitted_at` tz-aware `field_validator`). Mirror its shape for the new events.
  - `S11-02-emit-coordination-and-summary-writer.md` — the spanning-log `append_spanning(...)` seam + the goldens-fixture + `extra="forbid"` discipline. Mirror it; do not invent a new event-append API.
  - `S7-02-shell-invocation-trace-probe.md` — the heavy probe whose cross-CVE cache reuse is S18-02.
  - `S18-02-trace-probe-cross-cve-cache.md` — the G17 sibling; out of scope here.

## Goal

Land (a) a closed `TransformationKind` sum type + a `transformations_applied: tuple[TransformationKind, ...]` field added additively to the migration record; (b) two typed Pydantic enrichment events — `MigrationSizeRegression` and `MigrationRollbackRefCaptured` (carrying `pre_migration_image_ref`) — plus an `AttestationDiff` event, all appended to the spanning log via the existing `append_spanning(...)` seam; (c) a pure `render_migration_summary(...)` PR-description renderer that turns the typed data into operator prose plus a rollback line; and (d) a goldens fixture locking the rendered shape. Every item is WARN/enrichment — nothing in this story blocks a migration.

## Acceptance criteria

**`TransformationKind` sum type + `transformations_applied` (M3)**

- [ ] **AC-1 — `TransformationKind` closed sum type.** `plugins/distroless-migration--node--npm/subgraph/transformations.py` defines a discriminated union `TransformationKind = Annotated[FromSwapped | RedundantRunDropped | HealthcheckRewritten | ChownAdded | EntrypointRewrittenToExecForm, Field(discriminator="kind")]`. Each variant is a frozen Pydantic model (`model_config = ConfigDict(frozen=True, extra="forbid")`) with a `kind: Literal[...]` discriminator and an `instruction_index: int` field naming the affected Dockerfile instruction. `FromSwapped` additionally carries `from_ref: ImageRef` (old) and `to_ref: ImageRef` (new); `ChownAdded` carries `chown_value: str`. A `match` over `TransformationKind` with all five arms + `assert_never` is `mypy --strict` clean.
- [ ] **AC-2 — `transformations_applied` on the migration record.** The migration record (S17-01's type) gains a field `transformations_applied: tuple[TransformationKind, ...]` defaulting to `()`. The edit is additive — every existing migration-record test round-trips unchanged. The edit is enumerated as one row in the ADR-0029 byte-edit allowlist fence; that fence stays green.
- [ ] **AC-3 — `transformations_applied` populated for a sample migration.** Given a sample migration whose recipe swapped the `FROM`, dropped 3 redundant `RUN` lines, rewrote 1 `HEALTHCHECK`, and added `--chown` to 2 `COPY` lines, the assembled migration record's `transformations_applied` tuple has exactly 7 elements: one `FromSwapped`, three `RedundantRunDropped`, one `HealthcheckRewritten`, two `ChownAdded`. Each element's `instruction_index` matches the Dockerfile line the recipe touched. Asserted against a crafted fixture, not a mock.

**Enrichment events (G14, G15) — spanning log**

- [ ] **AC-4 — `MigrationSizeRegression` typed event.** `plugins/distroless-migration--node--npm/subgraph/events.py` defines `MigrationSizeRegression(_TypedEvent)` with `kind: Literal["migration_size_regression"]`, `workflow_id: WorkflowId`, `cve_id: CveId`, `pre_compressed_bytes: int`, `post_compressed_bytes: int`, `emitted_at: datetime` (UTC tz-aware, `field_validator` mirroring S11-01). `model_config = ConfigDict(frozen=True, extra="forbid")`.
- [ ] **AC-5 — `MigrationSizeRegression` emitted only when post > pre.** A pure helper `size_regression_event_for(workflow_id, cve_id, pre, post, emitted_at) -> MigrationSizeRegression | None` returns the event when `post_compressed_bytes > pre_compressed_bytes`, and `None` when `post <= pre` (a migration that shrank or held the image is not a regression — no event). Parametrized test: `post=120, pre=100` → event; `post=80, pre=100` → `None`; `post=100, pre=100` → `None`.
- [ ] **AC-6 — `MigrationRollbackRefCaptured` event + `pre_migration_image_ref`.** `events.py` defines `MigrationRollbackRefCaptured(_TypedEvent)` with `kind: Literal["migration_rollback_ref_captured"]`, `workflow_id: WorkflowId`, `cve_id: CveId`, `pre_migration_image_ref: ImageRef`, `pre_migration_image_digest: ImageDigest`, `emitted_at: datetime`. The `pre_migration_image_ref` is the pre-swap `FROM` ref captured before the recipe runs; it is the rollback target the PR runbook names.
- [ ] **AC-7 — `pre_migration_image_ref` captured before the swap.** A pure helper `capture_rollback_ref(pre_swap_from_ref, pre_swap_digest, workflow_id, cve_id, emitted_at) -> MigrationRollbackRefCaptured` constructs the event from the *pre-swap* `FROM` ref. Test: given a migration whose source `FROM` was `node:18-alpine@sha256:aaaa...`, the captured `pre_migration_image_ref` equals `ImageRef("node:18-alpine")` and `pre_migration_image_digest` equals `ImageDigest("sha256:" + "a"*64)` — never the post-swap Chainguard ref.

**Attestation diff (G16)**

- [ ] **AC-8 — `AttestationDiff` typed event.** `events.py` defines `AttestationDiff(_TypedEvent)` with `kind: Literal["attestation_diff"]`, `workflow_id: WorkflowId`, `cve_id: CveId`, `gained: tuple[AttestationKind, ...]` where `AttestationKind = Literal["signed_sbom", "slsa_provenance"]`, `lost: tuple[AttestationKind, ...]`, `emitted_at: datetime`. A migration onto a Chainguard image typically yields `gained=("signed_sbom", "slsa_provenance")`, `lost=()`.
- [ ] **AC-9 — Attestation diff is a pure set difference over `crane`-fetched data.** A pure helper `diff_attestations(source_attestations: frozenset[AttestationKind], target_attestations: frozenset[AttestationKind]) -> tuple[tuple[AttestationKind, ...], tuple[AttestationKind, ...]]` returns `(gained, lost)` as sorted tuples. The `crane`-fetch impurity (reading the published Chainguard SBOM + SLSA provenance) is isolated to a thin shell function; `diff_attestations` itself takes already-resolved sets. Test: `source=frozenset()`, `target={"signed_sbom","slsa_provenance"}` → `gained=("signed_sbom","slsa_provenance"), lost=()`.
- [ ] **AC-10 — `crane`-fetch failure WARNs, never crashes.** When the `crane` attestation fetch fails (network error, missing artifact, non-zero exit), the shell function returns `None` and the caller emits a `migration_observability.attestation_fetch_failed` warning ID — the migration record still assembles, no `AttestationDiff` event is appended, and `render_migration_summary` omits the attestation line. Test injects a failing `crane` and asserts: warning ID emitted, no exception propagates, no `AttestationDiff` in the spanning log.

**PR-description renderer (typed projection)**

- [ ] **AC-11 — `render_migration_summary` is a pure projection.** `plugins/distroless-migration--node--npm/subgraph/pr_description.py` defines `render_migration_summary(record: MigrationRecord, size_event: MigrationSizeRegression | None, rollback_event: MigrationRollbackRefCaptured, attestation_event: AttestationDiff | None) -> str`. Pure — no I/O, no `datetime.now()`, no `crane`. The function is `match`-driven over `TransformationKind` with `assert_never` exhaustiveness.
- [ ] **AC-12 — Rendered `transformations_applied` prose.** For the AC-3 sample record, `render_migration_summary` includes the line: `swapped FROM, dropped 3 redundant RUN lines, rewrote 1 HEALTHCHECK, added --chown to 2 COPY lines`. Pluralization is correct: a single dropped `RUN` renders `dropped 1 redundant RUN line` (singular). Parametrized test covers the 7-element sample and a 1-element-each sample.
- [ ] **AC-13 — Rendered rollback line.** The rendered description always includes a rollback runbook line of the exact form `To roll back: redeploy <pre_migration_image_ref>@<pre_migration_image_digest>`. Test: for a `MigrationRollbackRefCaptured` carrying `node:18-alpine` / `sha256:aaaa...`, the output contains `To roll back: redeploy node:18-alpine@sha256:aaaa...` (full 64-hex digest).
- [ ] **AC-14 — Rendered size + attestation lines, gracefully degrading.** When `size_event` is non-`None`, the output includes `Image size regressed: <pre> → <post> compressed` (human-readable byte counts, e.g. `48.2 MB → 61.7 MB`). When `size_event` is `None`, no size line. When `attestation_event` is non-`None` with `gained`, the output includes `Gained attestations: signed SBOM, SLSA provenance`. When `attestation_event` is `None`, no attestation line. Parametrized test covers all four present/absent combinations.
- [ ] **AC-15 — Goldens fixture locks the rendered shape.** `tests/golden/migration-observability/pr-description-full-bundle.md` exists and `render_migration_summary` over a fixed canonical record (the AC-3 sample + a `MigrationSizeRegression` + a `MigrationRollbackRefCaptured` + an `AttestationDiff(gained=("signed_sbom","slsa_provenance"))`) produces byte-identical output (LF line endings, trailing newline). The test renders the same instance and asserts byte-equality.

**Spanning-log append + WARN discipline**

- [ ] **AC-16 — Events appended to the spanning log.** An `emit_observability_events(orch_ctx, record, size_event, rollback_event, attestation_event) -> None` function appends each non-`None` event to the spanning log via the existing `orch_ctx.event_log.append_spanning(...)` seam (the same seam S11-02 uses). `MigrationRollbackRefCaptured` is always appended (rollback ref is always captured); `MigrationSizeRegression` and `AttestationDiff` are appended only when non-`None`. Test mocks `event_log` and asserts the call set for each present/absent combination.
- [ ] **AC-17 — Nothing in this story blocks a migration.** A property/integration test asserts: for a migration whose `crane` fetch fails AND whose post-image ballooned AND whose `transformations_applied` is empty, the migration record still assembles, a PR description still renders (degraded), and the orchestrator's disposition is unchanged — `migration_observability.*` warnings are present, no refusal, no exit-code change. ADR-0027 §Decision: every bundle item is WARN.
- [ ] **AC-18 — Warning IDs match the regex + are declared.** Every emitted warning ID is under the `migration_observability.` namespace and matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` (Phase 1 ADR-0007). A module-level `_WARNING_IDS: Final[frozenset[str]]` enumerates them; an import-time `raise AssertionError(...)` validates each against the regex (bare `assert` is forbidden by the `forbidden-patterns` hook).

**Engineering gates**

- [ ] **AC-19 — `mypy --strict` clean** on `transformations.py`, `events.py`, `pr_description.py`, and the migration-record edit.
- [ ] **AC-20 — `ruff check` + `ruff format --check` clean.**
- [ ] **AC-21 — `make lint-imports` green.** The plugin tree may not import LLM SDKs; the `subgraph/` modules import only from `src/codegenie/` primitives + Pydantic + stdlib.
- [ ] **AC-22 — ADR-0029 byte-edit allowlist fence green.** The migration-record edit + every net-new file is enumerated; the fence stays the mechanical definition of "additive."
- [ ] **AC-23 — Phase 3–6.5 regression suite green** (`make check`); `bench/vuln-remediation/` cassette replay byte-equal (cost-ledger ε ≤ $0.01).
- [ ] **AC-24 — TDD red test landed.** The AC-3 red test (`transformations_applied` populated with the 7 correct typed kinds) was committed in a failing state and is now green.

## Implementation outline

1. **`TransformationKind` sum type.** Create `plugins/distroless-migration--node--npm/subgraph/transformations.py`. Define the five frozen Pydantic variants (`FromSwapped`, `RedundantRunDropped`, `HealthcheckRewritten`, `ChownAdded`, `EntrypointRewrittenToExecForm`), each with a `kind` `Literal` discriminator + `instruction_index: int`. Build the discriminated union `TransformationKind = Annotated[..., Field(discriminator="kind")]`. Module docstring names ADR-0027 + ADR-0025 (the closed-sum-type sibling).
2. **`transformations_applied` on the migration record.** Edit S17-01's migration-record type additively — add `transformations_applied: tuple[TransformationKind, ...] = ()`. Verify the ADR-0029 byte-edit allowlist fence permits this row; if not, add a Phase 7 ADR-0027 §Consequences-justified row. Re-run every existing migration-record test.
3. **Recipe wiring (label, do not transform).** The recipes (S16-03) already emit the structural edits. This story adds a thin pure mapper `label_transformations(recipe_edits) -> tuple[TransformationKind, ...]` that turns the recipe's edit list into typed `TransformationKind` values. This is labeling, not transforming — the recipe still owns the diff.
4. **Enrichment events.** Create `plugins/distroless-migration--node--npm/subgraph/events.py` with `MigrationSizeRegression`, `MigrationRollbackRefCaptured`, `AttestationDiff` (each `_TypedEvent`, frozen, `extra="forbid"`, `kind` literal, tz-aware `emitted_at` `field_validator`). Mirror S11-01's event shape exactly.
5. **Pure helpers.** `size_regression_event_for(...)` (returns event or `None`), `capture_rollback_ref(...)` (constructs the event from the pre-swap `FROM`), `diff_attestations(source, target)` (pure set difference). All functional-core, no I/O.
6. **`crane` attestation shell.** A thin impure shell function `fetch_attestations(image_ref) -> frozenset[AttestationKind] | None` calling `crane` via `run_external_cli`; returns `None` on any failure and the caller emits `migration_observability.attestation_fetch_failed`. Isolate the impurity — `diff_attestations` never touches `crane`.
7. **PR-description renderer.** Create `plugins/distroless-migration--node--npm/subgraph/pr_description.py` with the pure `render_migration_summary(...)`. `match`-driven over `TransformationKind`; correct pluralization; the always-present rollback line; the conditional size + attestation lines.
8. **`emit_observability_events`.** A function appending each non-`None` event to the spanning log via `orch_ctx.event_log.append_spanning(...)`. `MigrationRollbackRefCaptured` always; the other two conditionally.
9. **Goldens fixture.** Hand-write `tests/golden/migration-observability/pr-description-full-bundle.md` for the canonical full-bundle record; the test renders the same instance and asserts byte-equality.
10. **Warning IDs.** Module-level `_WARNING_IDS: Final[frozenset[str]]` with import-time regex validation via `raise AssertionError(...)`.
11. **Tests** under `tests/unit/plugins/distroless_migration_node_npm/subgraph/`, the goldens test, and the WARN-never-blocks integration test.
12. **Run `make check`** + `bench/vuln-remediation/` cassette replay; assert cost-ledger byte-equality.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/plugins/distroless_migration_node_npm/subgraph/test_transformations_applied.py`

```python
from __future__ import annotations

from plugins.distroless_migration_node_npm.subgraph.transformations import (
    ChownAdded,
    FromSwapped,
    HealthcheckRewritten,
    RedundantRunDropped,
    label_transformations,
)
from tests.fixtures.migration import sample_recipe_edits  # crafted fixture, not a mock


def test_transformations_applied_populated_with_correct_typed_kinds():
    """AC-3 — a migration that swapped FROM, dropped 3 RUN lines, rewrote 1
    HEALTHCHECK, added --chown to 2 COPY lines yields exactly 7 typed kinds."""
    edits = sample_recipe_edits()  # fixture: 1 swap + 3 RUN drops + 1 HC + 2 chown
    applied = label_transformations(edits)

    assert len(applied) == 7
    assert sum(isinstance(t, FromSwapped) for t in applied) == 1
    assert sum(isinstance(t, RedundantRunDropped) for t in applied) == 3
    assert sum(isinstance(t, HealthcheckRewritten) for t in applied) == 1
    assert sum(isinstance(t, ChownAdded) for t in applied) == 2

    # each typed kind names the Dockerfile instruction it touched
    run_drops = [t for t in applied if isinstance(t, RedundantRunDropped)]
    assert sorted(t.instruction_index for t in run_drops) == [3, 4, 5]
    swap = next(t for t in applied if isinstance(t, FromSwapped))
    assert swap.instruction_index == 0
```

State why the red test fails: `ModuleNotFoundError: plugins.distroless_migration_node_npm.subgraph.transformations` — the module, the `TransformationKind` variants, and `label_transformations` do not exist.

A second red test for the renderer, `tests/unit/plugins/distroless_migration_node_npm/subgraph/test_pr_description.py`:

```python
def test_render_includes_rollback_line():
    """AC-13 — the rollback runbook line is always present, exact form."""
    description = render_migration_summary(
        record=_sample_record(),
        size_event=None,
        rollback_event=_sample_rollback_event(),  # node:18-alpine @ sha256:aaaa...
        attestation_event=None,
    )
    assert "To roll back: redeploy node:18-alpine@sha256:" + "a" * 64 in description
```

Fails with `ImportError` / `NameError` — `render_migration_summary` does not exist.

### Green — minimal pass

- Create `transformations.py` with the five frozen variants + the discriminated union + `label_transformations`.
- Add `transformations_applied: tuple[TransformationKind, ...] = ()` to the migration record; update the ADR-0029 allowlist row.
- Create `events.py` with the three `_TypedEvent` subclasses.
- Create `pr_description.py` with the pure `render_migration_summary` — `match`-driven, correct pluralization, the rollback line, conditional size/attestation lines.
- Implement the pure helpers + the `crane` shell + `emit_observability_events`.
- Land the goldens fixture.

### Refactor

- Add module docstrings doc-linking ADR-0027 / ADR-0029 / ADR-0034.
- Add a comment on `emit_observability_events` naming ADR-0034 ("spanning log is canonical; the PR description is a projection").
- Add a comment on the `crane` shell naming ADR-0028 + ADR-0027 §Tradeoffs ("enrichment that fails WARNs, never vanishes").
- Verify `make check` clean + Phase 3 regression-suite-green + cassette byte-equal.

## Files to touch

| Path | Why |
|---|---|
| `plugins/distroless-migration--node--npm/subgraph/transformations.py` | NEW — `TransformationKind` closed sum type (5 variants) + `label_transformations`. |
| `plugins/distroless-migration--node--npm/subgraph/events.py` | NEW — `MigrationSizeRegression`, `MigrationRollbackRefCaptured`, `AttestationDiff` typed events. |
| `plugins/distroless-migration--node--npm/subgraph/pr_description.py` | NEW — pure `render_migration_summary` renderer + `migration_observability.*` warning IDs. |
| `plugins/distroless-migration--node--npm/subgraph/observability.py` | NEW — pure helpers (`size_regression_event_for`, `capture_rollback_ref`, `diff_attestations`), the `crane` shell, `emit_observability_events`. |
| `<S17-01 migration-record module>` | EDIT (additive) — add `transformations_applied: tuple[TransformationKind, ...] = ()`. |
| `tests/unit/plugins/distroless_migration_node_npm/subgraph/test_transformations_applied.py` | NEW — `TransformationKind` + `label_transformations` (AC-1..AC-3). |
| `tests/unit/plugins/distroless_migration_node_npm/subgraph/test_observability_events.py` | NEW — the three events + the pure helpers (AC-4..AC-10). |
| `tests/unit/plugins/distroless_migration_node_npm/subgraph/test_pr_description.py` | NEW — renderer prose, pluralization, rollback/size/attestation lines (AC-11..AC-14). |
| `tests/unit/plugins/distroless_migration_node_npm/subgraph/test_pr_description_golden.py` | NEW — goldens-file byte-equality (AC-15). |
| `tests/unit/plugins/distroless_migration_node_npm/subgraph/test_emit_observability_events.py` | NEW — spanning-log append set (AC-16). |
| `tests/integration/test_observability_never_blocks.py` | NEW — WARN-never-blocks invariant (AC-17). |
| `tests/golden/migration-observability/pr-description-full-bundle.md` | NEW — canonical rendered PR-description shape. |
| `tests/fixtures/migration/__init__.py` | NEW/EDIT — `sample_recipe_edits` crafted fixture. |
| `docs/phases/07-migration-task-class/ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md` | EDIT (additive) — enumerate the migration-record edit + the new `subgraph/` files. |

## Out of scope

- **Cross-CVE `ShellInvocationTraceProbe` content-cache reuse (G17)** — `S18-02`. This story ships the `transformations_applied` list + the three enrichment events; the trace-probe cache is the sibling story.
- **The PR-creation mechanism itself** — `render_migration_summary` produces the *body string*; the actual `git`/`gh` PR-open is the orchestrator's job, unchanged by this story.
- **Phase 11's merge-gate consumption of `transformations_applied`** — Phase 11. This story makes the typed data machine-readable; Phase 11 reads it.
- **Phase 13.5's operator portal** — Phase 13.5 reads the spanning-log events; this story emits them.
- **Blocking a migration on a size regression / missing attestation** — explicitly forbidden by ADR-0027 §Decision; every bundle item is WARN. A future ADR could make size-regression blocking; this story does not.
- **Multi-arch attestation diffs** — the attestation diff is per-image; multi-arch coverage delta is G11 (S17, ADR-0024), not this story.
- **`TransformationKind` variants beyond the five named** — `EntrypointRewrittenToExecForm` is included for the exec-form rewrite S16-03 introduces; further variants (e.g. `BuildArgDropped`) are additive future work via the same discriminated-union seam.

## Notes for the implementer

- **The data is the source of truth; the prose is a view.** ADR-0027 §Options rejects Option A (hand-assembled free-text) precisely because prose drifts and is not machine-readable. `transformations_applied` + the three events are the contract; `render_migration_summary` is a *pure projection* over them. Do not let the renderer compute anything the typed data does not already carry — if you find yourself re-deriving the FROM swap inside the renderer, the typed data is missing a field.
- **Every bundle item is WARN — nothing here blocks.** This is the load-bearing invariant. A migration with a ballooned image, a missing attestation diff, or a `crane` that 500s still produces a PR. The PR description degrades; the merge is not blocked. AC-17 is the test that proves it. If any code path in this story can raise past the orchestrator or change a disposition, it is wrong.
- **Enrichment that fails must WARN visibly, never vanish.** ADR-0027 §Tradeoffs is explicit: a swallowed exception is the wrong failure mode. When `crane` cannot fetch the attestation, or `dive` cannot weigh the post-image, emit a `migration_observability.*` warning ID — the operator sees a degraded PR description *and* knows why. Do not `except Exception: pass`.
- **`MigrationSizeRegression` fires only when post > pre.** A migration onto a distroless image usually *shrinks* the image — that is the happy path and is NOT a regression. The event name is `SizeRegression`; emitting it for a shrink would be a lie. `size_regression_event_for` returns `None` for `post <= pre`. The PR description still gets a size *line* for a shrink if you want one — but via a different code path, not this event. (This story renders a size line only on regression; a "shrank by X" line is optional future polish.)
- **`pre_migration_image_ref` is captured *before* the swap.** The rollback target is the *source* `FROM`, not the Chainguard target. Capture it in `capture_rollback_ref` from the pre-swap `FROM` ref; if you capture it after the recipe runs you will record the wrong image and the rollback runbook will tell the operator to redeploy the thing they are migrating *to*. AC-7 pins this.
- **`diff_attestations` is pure; the `crane` fetch is the shell.** Keep the impure `crane` invocation in one thin function (`fetch_attestations`) that returns `frozenset[AttestationKind] | None`. `diff_attestations` takes already-resolved sets — that is what makes it property-testable and what keeps the functional-core/imperative-shell discipline (CLAUDE.md). A `None` from the shell means "fetch failed" → WARN + omit the event.
- **`TransformationKind` mirrors the refusal taxonomy.** ADR-0025's `RemediationOutcome.PendingHumanReview` variant set and ADR-0026's `MigrationConfidence` rollup are the structural siblings — Phase 7's consistent "make the outcome a typed value, not a string." Use the same `Annotated[... , Field(discriminator="kind")]` discriminated-union shape; `match` + `assert_never` everywhere it is consumed.
- **The migration-record edit is the one ADR-gated additive field.** Per ADR-0029 the byte-edit allowlist is the mechanical definition of "additive." Adding `transformations_applied` to S17-01's record is the single edit-to-an-existing-type in this story — it needs an allowlist row justified by ADR-0027 §Consequences. Everything else is net-new files. If the fence rejects the record edit, do not silence it — add the row.
- **Goldens fixture catches renderer drift at every PR.** ADR-0027 §Decision names the goldens fixture as the drift-catcher. Hand-write `pr-description-full-bundle.md` for the canonical record; LF line endings, trailing newline. If a future change reorders the prose, the golden breaks loudly — that is the desired failure mode, not a nuisance.
- **Mirror S11-01 / S11-02 exactly for the events + the spanning-log append.** The `_TypedEvent` base, the `kind` discriminator literal, the tz-aware `emitted_at` `field_validator`, the `append_spanning(...)` seam — all already exist and are tested. Do not invent a new event base class or a new append API. Two consumers, one seam.
- **Closest precedent.** S11-02's `coordination-summary.yaml` writer is the structural twin: typed Pydantic models + a goldens fixture + `extra="forbid"` + the spanning-log append + a plugin-tree home under `subgraph/`. Mirror its shape; do not re-invent.
