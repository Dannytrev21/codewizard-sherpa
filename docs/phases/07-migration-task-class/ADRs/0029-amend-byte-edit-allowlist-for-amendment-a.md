# ADR-0029: ADR-0029 amends the ADR-0009 byte-edit allowlist to enumerate every Amendment-A source-file addition

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** extension-by-addition · fence · adr-amendment · immutability · amendment-a · ship-of-theseus
**Related:** [0009](0009-phase-7-byte-edit-allowlist-fence.md), [0015](0015-allowed-binaries-amendment-dive-buildx.md), [0018](0018-dockerfile-secret-pattern-probe.md), [0019](0019-target-image-content-probe.md), [0020](0020-build-toolchain-classification-catalog.md), [0021](0021-runtime-shell-invocation-probe.md), [0022](0022-container-probe-compat-and-blast-radius.md), [0023](0023-runtime-compat-probe.md), [0024](0024-multi-arch-and-external-registry-checks.md), [0025](0025-migration-refusal-taxonomy.md), [0026](0026-migration-confidence-aggregation.md), [0027](0027-migration-observability-bundle.md), [0028](0028-allowed-binaries-amendment-crane.md), [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)

## Context

[ADR-0009](0009-phase-7-byte-edit-allowlist-fence.md) defined a closed, enumerated allowlist of 10 byte-edits to existing (Phase 0–6.5 / Phase 3) files, mechanically enforced by `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` (or equivalent). The fence asserts byte-identity against the Phase 6.5 baseline for every file under `src/codegenie/`, `plugins/`, and the kernel-frozen surface — except the explicitly enumerated rows. This is the **Ship-of-Theseus defense**: without the allowlist, "additive" decays into "any new row is fine," and the kernel is continuously modified without any single phase noticing.

`final-design.md §Amendment A` deepens the distroless-migration gather pipeline. Its stories (`High-level-impl.md` Steps 13–18) create new files — six gather probes, their sub-schemas, data catalogs — and make new additive edits to existing files: `ALLOWED_BINARIES` gains `crane` ([ADR-0028](0028-allowed-binaries-amendment-crane.md)); `outcomes.py` gains refusal variants ([ADR-0025](0025-migration-refusal-taxonomy.md)); the `NodeManifestProbe` slice gains a `native_modules` field ([ADR-0020](0020-build-toolchain-classification-catalog.md)). `final-design.md §A.3 departure #5` states the allowlist must be amended so the fence stays the mechanical definition of "additive."

ADRs are immutable: a superseded ADR keeps its number and is amended in place only with an explicit dated amendment block, or — for a *new structural decision* — gets a new ADR. ADR-0009 already carries a 2026-05-20 amendment block deferring its "grows with each phase" framing to [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md). The Amendment-A allowlist growth is a *new decision within Phase 7* and gets its own number rather than re-issuing ADR-0009.

## Options considered

- **Option A — Re-issue ADR-0009 with a bigger allowlist.** Edit the 10-row list in place to 18+ rows. **Pattern:** Mutable ADR. **Rejected** — ADRs are immutable; the 10-row decision is a historical record. Editing the canonical list in place erases the audit trail of *which* phase added *which* row and breaks the "supersession gets a new number" discipline the codebase enforces everywhere else.
- **Option B — A new ADR-0029 that amends the allowlist, cross-linked from ADR-0009's consequences.** Each new allowance row is enumerated here, gated by its owning ADR; ADR-0009 stays the historical 10-row record; the fence test grows by reading both ADRs' row-sets. **Pattern:** ADR amendment by addition — matches the codebase's ADR-amendment discipline ([ADR-0015](0015-allowed-binaries-amendment-dive-buildx.md) is the in-phase precedent: a focused ADR amending one earlier decision).
- **Option C — Loosen the fence from an enumerated allowlist to a prefix-glob** (e.g. "anything under `plugins/distroless-migration--node--npm/` is fine"). **Pattern:** Coarse policy. **Rejected** — defeats the *mechanical, enumerated* definition of "additive." A glob cannot distinguish an additive new probe module from an accidental edit to an existing one; it reintroduces exactly the Ship-of-Theseus drift ADR-0009 was created to stop.

## Decision

Adopt **Option B.** ADR-0029 amends — does not replace — the [ADR-0009](0009-phase-7-byte-edit-allowlist-fence.md) byte-edit allowlist. ADR-0009 stays the historical record of the original 10 rows; this ADR enumerates the Amendment-A allowance rows. The fence test (`tests/fence/test_phase7_no_byte_edits_to_locked_files.py`) grows row-by-row, each row gated by the owning ADR:

1. **New plugin-internal probe modules** under `plugins/distroless-migration--node--npm/probes/` — wholly new files, additive (`dockerfile_secret_pattern_probe.py`, `target_image_content_probe.py`, `runtime_shell_invocation_probe.py`, `container_probe_compat_probe.py`, `runtime_compat_probe.py`, and the `MigrationConfidence` aggregator module). Owning ADRs: [0018](0018-dockerfile-secret-pattern-probe.md), [0019](0019-target-image-content-probe.md), [0021](0021-runtime-shell-invocation-probe.md), [0022](0022-container-probe-compat-and-blast-radius.md), [0023](0023-runtime-compat-probe.md), [0026](0026-migration-confidence-aggregation.md).
2. **New probe sub-schemas** under that plugin's `schema/` directory — one `*.schema.json` per new probe slice; wholly new files.
3. **Additive `$ref` insertions into `src/codegenie/schema/repo_context.schema.json`** — exactly one `$ref` per new probe slice wired into `properties.probes` (the precedent ADR-0009 row 4 set for two Phase-3 probes).
4. **`src/codegenie/exec/__init__.py`** — `ALLOWED_BINARIES` gains exactly one new row: `crane` ([ADR-0028](0028-allowed-binaries-amendment-crane.md); extends the `dive` + `docker buildx` rows of [ADR-0015](0015-allowed-binaries-amendment-dive-buildx.md) / ADR-0009 row 8).
5. **`src/codegenie/transforms/outcomes.py`** — additive `RemediationOutcome.PendingHumanReview` refusal variants ([ADR-0025](0025-migration-refusal-taxonomy.md)).
6. **The `NodeManifestProbe` slice schema** — gains exactly one additive field: `native_modules: tuple[NativeModule, ...]` ([ADR-0020](0020-build-toolchain-classification-catalog.md)).
7. **New data catalogs** under the plugin's `data/` directory — `apk_classification.yaml`, `apt_classification.yaml`, and any Amendment-A marker catalogs; wholly new files.
8. **The plugin's `tccm.yaml` `must_read` list** — gains the new probe slice names so the plugin resolver reads the new gather output.

Each row's fence-allowlist entry carries a docstring pointer to its owning ADR. Any byte-edit to a Phase 0–6.5 / Phase 3 file not enumerated here or in ADR-0009 remains a fence failure.

## Tradeoffs

| Gain | Cost |
|---|---|
| ADR-0009 stays an immutable historical record; the audit trail of which phase/amendment added which row is preserved | Two ADRs (0009 + 0029) must be read together to see the full Phase-7 allowlist; the fence file's docstring cross-links both |
| Each Amendment-A allowance row is gated by its owning ADR — the fence stays the mechanical, ADR-reviewed definition of "additive" | The fence file grows by ~8 row-categories; verbose but bounded, and each row is one line of test data |
| Re-using the existing fence mechanism (enumerated rows, not a glob) keeps the Ship-of-Theseus defense intact through Amendment A | Story ordering stays load-bearing — the fence-allowlist rows must land alongside (or before) the files they permit, or the file-adding PR fails CI |
| The allowlist remains *data in a test* — adding a row is an additive edit to a fixture, reversible and reviewable | The fence does not catch *semantic* drift inside an allowed file (e.g. a degenerate `outcomes.py` edit) — that stays `make check`'s job, unchanged from ADR-0009 |

## Pattern fit

Implements **ADR amendment by addition** — a superseded or extended decision keeps its number; a new ADR amends it and is cross-linked, never re-issued. This mirrors [ADR-0015](0015-allowed-binaries-amendment-dive-buildx.md) (a focused ADR amending the `ALLOWED_BINARIES` allowlist) within Phase 7 itself, and the project-wide rule that supersession gets a new number. The decision preserves **Open/Closed at the file boundary** ([ADR-0009](0009-phase-7-byte-edit-allowlist-fence.md)'s pattern): the existing surface stays closed for arbitrary modification; the named, ADR-reviewed extension surface stays open. The allowlist itself remains **data, not branching code** — the fence test reads an enumerated row-set; growth is an additive fixture edit.

## Consequences

- `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` gains the Amendment-A allowance rows enumerated above; its docstring cross-links ADR-0009 and ADR-0029 and each owning ADR.
- [ADR-0009](0009-phase-7-byte-edit-allowlist-fence.md)'s `## Consequences` is updated with a cross-link forward to ADR-0029 (the only edit to ADR-0009 — a pointer, the 10-row list is untouched).
- The fence is CI-required throughout Amendment A; an unanticipated byte-edit to a Phase 0–6.5 / Phase 3 file fails fast.
- Story ordering (`final-design.md §A.4`, `High-level-impl.md` Steps 13–18): the fence-allowlist rows land alongside the files they permit; the empty-allowlist S0 discipline of ADR-0009 §Consequences carries forward to Amendment-A stories.
- Adding an Amendment-A file *not* covered by the eight row-categories requires an amendment to *this* ADR plus the owning structural ADR.
- The fence does NOT catch semantic regressions inside an allowed file — `make check` + the Phase 3 cassette-replay regression gate remain the behavioral defense, unchanged.
- Phase 8+ add no allowlist rows and no new per-phase allowlist fence ([production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)) — Amendment A is the last growth of the Phase 7 allowlist.

## Reversibility

**High.** The allowlist is data in a test fixture — adding or removing a row is a one-line edit to `tests/fence/test_phase7_no_byte_edits_to_locked_files.py`. Reverting an Amendment-A row reverts to a stricter fence (the corresponding file-adding PR would then fail, surfacing the dependency loudly). Restructuring the fence (e.g. splitting per-amendment) is a localized test-file change with no production impact.

## Evidence / sources

- `../final-design.md §Amendment A §A.3 departure #5` ("ADR-0009's byte-edit allowlist is amended (ADR-0029) to enumerate every new source file this amendment's stories create"), §A.4 (sequencing)
- `../phase-arch-design.md §Component design — Amendment A §15–§23` (the new probe modules, sub-schemas, data catalogs, and `outcomes.py` / `NodeManifestProbe` edits this ADR's rows enumerate), §Amendment A gaps ("ADR-0029 amends ADR-0009's byte-edit allowlist for every Amendment-A source file")
- [Phase 7 ADR-0009 — byte-edit allowlist fence](0009-phase-7-byte-edit-allowlist-fence.md) (the 10-row original allowlist this ADR amends)
- [Phase 7 ADR-0015 — `ALLOWED_BINARIES` amendment for `dive` + `buildx`](0015-allowed-binaries-amendment-dive-buildx.md) (precedent: a focused in-phase ADR amending an allowlist)
- [Phase 7 ADRs 0018–0028](0018-dockerfile-secret-pattern-probe.md) — the owning ADRs that gate each Amendment-A allowance row
- [production ADR-0043 — extension by addition means no silent edits](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)
- CLAUDE.md "Load-bearing architectural commitments — Extension by addition"
