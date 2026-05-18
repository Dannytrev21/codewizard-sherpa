# Story S<step>-<TT> — Phase NN closeout: cross-doc + registry consistency gate

**Step:** Step <last-step> — <step title from `High-level-impl.md`>
**Status:** Ready
**Effort:** S
**Depends on:** every other Phase NN story in `Done` status
**ADRs honored:** (this phase's ADRs that touch registry/schema/docs surfaces)

> **About this template.** This is a copy-into-place template for the **last story** of every codewizard-sherpa phase. Drop it into `docs/phases/NN-<slug>/stories/S<last>-<TT>-phase-NN-closeout.md`, fill in the bracketed placeholders, and add the resulting story to the manifest as the final entry under the last step.
>
> The story exists because the failure mode it catches is real: a phase can ship every component story to `Done` and *still* leave the system in a half-consistent state — a probe registered but not imported, a sub-schema written but not `$ref`'d into the envelope, a roadmap row that still says `pending redesign` after the design landed, a `docs/index.md` status table that contradicts the roadmap. None of these are bugs in the implementation; they are bugs in *closing the loop*. The closeout story is the loop-closer.
>
> Keep it small: this is a checklist, not new design. If a check needs more than ten minutes to satisfy, the upstream story missed something — fix it there, not here.

## Context

This is the closeout pass for Phase NN. Every component story has shipped to `Done`. This story exists to gate the merge of the final Phase NN PR on a small set of cross-doc and registry invariants — the kind of consistency a casual reviewer wouldn't catch but that compounds painfully if it lands stale.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Integration with Phase NN+1` — the contract this closeout proves is intact
  - `../phase-arch-design.md §Component design` — every component should have a corresponding `Done` story, named here
- **Phase ADRs:**
  - (list every Phase NN ADR — they all need to show up in `../ADRs/README.md`'s index)
- **Production ADRs:**
  - `../../../production/adrs/README.md` — index should mention any new production ADR Phase NN required
- **Doc-consistency fence:**
  - `tests/unit/test_doc_consistency.py` — the doc-lint invariants must pass on `master` before this story closes
- **Roadmap:**
  - `../../roadmap.md` — Phase NN row must be `✅`, not `pending` or empty
- **Index:**
  - `../../index.md` Status table — must agree with the roadmap

## Goal

Phase NN is in a state a fresh reader can pick up cold: every component has a `Done` story, every probe/registry-decorated module is imported at the collection point, every sub-schema is `$ref`'d into the envelope, every cross-doc surface (roadmap, index, phase README) agrees, and `tests/unit/test_doc_consistency.py` passes on `master`.

## Acceptance criteria

The five **structural** checks (delete rows that don't apply to this phase — e.g., a non-probe phase removes the probe-registry checks):

- [ ] **Registry-import parity (per probe/plugin/signal-kind added by this phase):** every module that decorates with `@register_probe` / `@register_signal_kind` / `@register_task_class` / `@register_<X>` is also imported in the corresponding `__init__.py` collection point. (Generalises the `probes/__init__.py` rule; `test_doc_consistency.py::test_every_registered_probe_module_is_imported_in_probes_init` enforces the probe case mechanically.)
- [ ] **Sub-schema parity:** every new `src/codegenie/schema/probes/<name>.schema.json` is referenced via `$ref` from `src/codegenie/schema/repo_context.schema.json` `probes.properties.<name>`.
- [ ] **Smoke-gather output check:** running `python -m codegenie gather <fixtures/...>` against a phase-appropriate fixture produces a `repo-context.yaml` whose `probes.<new_probe>` slice validates against its sub-schema (or — for non-gather phases — whose phase-specific top-level artifact exists and validates).
- [ ] **ADR-index parity:** every file in `docs/phases/NN-<slug>/ADRs/NNNN-*.md` is listed in `docs/phases/NN-<slug>/ADRs/README.md`'s index table; and every new production ADR (if any) is listed in `docs/production/adrs/README.md`.
- [ ] **Cross-doc status parity:** `docs/roadmap.md` Phase NN row shows `✅ [NN-<slug>](phases/NN-<slug>/)`; `docs/index.md` Status table shows the same phase as designed/shipped; the phase's own `docs/phases/NN-<slug>/README.md` does not contradict either.

The two **mechanical** checks:

- [ ] `tests/unit/test_doc_consistency.py` passes on `master` after this story's diff lands.
- [ ] `make check` is green (full local gate: ruff + mypy + pytest + fence). No skips, no `xfail` added by this story.

## Implementation outline

This story should rarely involve writing new code. The flow is:

1. **Audit.** Walk the Acceptance-criteria list against the current `master`. For each red item, locate the upstream story that should have closed it.
2. **Fix at source.** If the gap belongs to an upstream story (probe registered but never imported, sub-schema written but not `$ref`'d), reopen that story for a one-line correction. Don't write the fix in this closeout — the test/diff lives with the component.
3. **Sweep cross-doc surfaces.** The cross-doc checks (roadmap row, index table, phase README) typically *are* this story's diff — they are the small edits no upstream story owned.
4. **Refresh `test_doc_consistency.py` if new invariants apply.** If the phase introduced a new doc surface (e.g., a `bench/<task-class>/` directory contract per Phase 6.5), add a corresponding invariant test in the same file using the existing test pattern.
5. **Run `make check` once green; mark every upstream story's status field unchanged; flip this story's Status from `Ready` to `Done`.**

## TDD plan — red / green / refactor

This story is **test-led, not code-led**. The TDD framing maps to running the existing fence + writing any new invariants the phase introduced.

### Red — write the failing check first

If the phase introduced a new cross-doc surface, add a failing test in `tests/unit/test_doc_consistency.py` mirroring the existing test pattern. Example shape (adapt the regex + path for the actual invariant):

```python
# tests/unit/test_doc_consistency.py
def test_phase_NN_<surface>_consistency() -> None:
    # arrange: load the relevant doc / dir
    # act: scan for the invariant
    # assert: invariant holds — and on failure, the message names the
    #   offending file and a one-sentence fix instruction.
    ...
```

If the phase did NOT introduce a new doc surface, the red phase is simply running the existing fence — the failures it surfaces are the "audit" pass from the Implementation outline.

### Green — make it pass

Apply the smallest diff to each surface:
- Roadmap row → ✅ (or the appropriate status)
- Index table → matches roadmap
- ADR index → lists every ADR file
- (etc.)

Each fix is small. If a fix is large, the gap belongs to an upstream story — close *that* one and rerun.

### Refactor — clean up

- Re-run the full fence (`pytest tests/unit/test_doc_consistency.py -v --no-cov`).
- Confirm `make check` still passes.
- Verify the Phase NN+1 design pipeline can pick up cleanly — `docs/phases/NN-<slug>/README.md` should accurately describe what's shipped and what consumers (Phase NN+1, eval harness, etc.) can rely on.

## Files to touch

| Path | Why |
|---|---|
| `docs/roadmap.md` | Flip Phase NN row to ✅ if not already; ensure linked folder path matches |
| `docs/index.md` | Status table row consistent with roadmap |
| `docs/phases/NN-<slug>/README.md` | Reflect shipped state (component story IDs in `Done`) |
| `docs/phases/NN-<slug>/ADRs/README.md` | Index every ADR file in the folder |
| `tests/unit/test_doc_consistency.py` | Add phase-specific invariants if applicable |
| `src/codegenie/probes/__init__.py` | Import any probe module added this phase (one line per module) |
| `src/codegenie/schema/repo_context.schema.json` | Add `$ref` for any new probe sub-schema |

## Out of scope

- **Code refactors** — closeout is not a license to rewrite.
- **New components** — if the audit finds a missing component, close that gap with a new story, not by widening this one.
- **Phase NN+1 design work** — that's `roadmap-phase-designer`'s job.

## Notes for the implementer

- The five structural checks are deliberately ordered cheap → expensive. Probe-import parity is a one-line `__init__.py` fix; sub-schema `$ref` is a JSON-pointer edit; smoke-gather is a CLI run; ADR-index parity is a markdown table; cross-doc status parity is two file edits. Do them in that order — finding a problem in the cheap check often reveals more at the expensive check.
- If the doc-consistency fence (`test_doc_consistency.py`) was added in a prior phase (≥ Phase 4), this story's job is mostly *running* it and fixing what it finds. If your phase ships a new cross-doc surface that isn't covered yet, **extend the fence** as part of this story — that's the lasting value.
- **The closeout story is small by design.** If it's growing past 100 lines of diff (excluding the new fence-test invariants), an upstream story missed something. Find it, fix it there, rerun.
