# ADR-0002: Two new top-level packages (`transforms/`, `recipes/`); `cve/` and `validation/` fold under `transforms/`

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** package-layout · extension-by-addition · scope-discipline · synthesizer-departure
**Related:** ADR-0001, [Phase 2 ADR-0001](../../02-context-gather-layers-b-g/ADRs/0001-peer-outputs-binding.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)

## Context

Best-practices proposed **four** new top-level packages under `src/codegenie/`: `cve/`, `transforms/`, `recipes/`, `validation/` (`final-design.md §"Lens summary"`; `critique.md §"Attacks on the best-practices design" §"Concrete problems" #3`). The Phase 0–2 precedent is a small, orthogonal set (`probes/`, `cache/`, `tools/`, `skills/`, `output/`, `schema/`, `audit/`, `exec/`), and best-practices itself acknowledged "this is the largest new-package footprint since Phase 0." Performance-first added zero; security-first added one (`remediation/`).

The critic flagged the proliferation precedent explicitly: "Phase 4 will want `planning/`. Phase 5 will want `sandbox/` and `gates/`. Phase 6 will want `state_machine/`. The pattern of 'one phase, several new top-level packages' is the wrong precedent to set" (`critique.md §"Attacks on the best-practices design" §"Concrete problems" #3`). The synthesis chose a middle path (`final-design.md §"Conflict-resolution table"` row "New top-level packages"): the two packages that map to the two public ABCs (ADR-0001), and `cve/` + `validation/` fold under `transforms/` as sub-packages because both exist *for* the transform contract.

## Options considered

- **Four packages — `cve/`, `transforms/`, `recipes/`, `validation/` [B].** Maximum cohesion per package; one noun per package. Sets the precedent for future-phase sprawl.
- **One package — `remediation/` [S].** Treats vuln remediation as a single concern, conflating contract (`Transform` ABC), data (CVE advisories), and infrastructure (validators). Future task classes (Phase 7 distroless) can't reuse `transforms/` because it lives under `remediation/`.
- **Zero new top-level packages [P].** Extends existing packages with new submodules. Cheapest. Defeats ADR-0001 — there is no visible home for the two ABCs.
- **Two packages — `transforms/` and `recipes/`; `cve/`, `validation/` as sub-packages of `transforms/` [synth].** One package per public ABC. CVE and validation are infrastructure that exists to serve the transform contract; they fold under it.

## Decision

**Phase 3 adds exactly two top-level packages under `src/codegenie/`:**

```
src/codegenie/transforms/
  contract.py            ← Transform ABC, TransformInput, TransformOutput
  registry.py            ← @register_transform decorator
  coordinator.py         ← linear sync orchestrator (ADR-0006)
  context.py             ← RepoContextView (read-only)
  npm_package_upgrade.py ← THE Phase-3 transform
  cve/
    models.py            ← Advisory, AffectedRange, Provenance
    feeds/{nvd,ghsa,osv}.py
    store.py             ← content-addressed snapshot reader (ADR-0008)
    retraction_probe.py  ← CveRetractionProbe (ADR-0009)
  validation/
    install.py           ← npm ci validator
    test.py              ← npm test validator (single sandbox, overlay; ADR-0005)
    build.py             ← opt-in build validator
    trust_score.py       ← strict-AND scorer (per production ADR-0008)
    lockfile_policy.py   ← LockfilePolicyScanner (ADR-0007)

src/codegenie/recipes/
  engine.py              ← RecipeEngine ABC + Ncu + OpenRewriteStub (ADR-0003)
  selector.py            ← selection logic
  selector.yaml          ← (data) decision table
  models.py              ← Recipe, RecipeApplication, RecipeSelection (ADR-0004)
  digests.yaml           ← per-recipe digest manifest (ADR-0011)
  catalog/npm/*.yaml     ← recipe definitions (data)
```

**No `cve/`, `validation/`, or `remediation/` top-level package.** Phase-0 fence CI extended with the two new packages: `transforms/` and `recipes/` may not import LLM SDKs (`production ADR-0005`).

## Tradeoffs

| Gain | Cost |
|---|---|
| Sets the precedent "one phase, one or two new top-level packages" — every future phase has to argue for more, not assume it | Sub-package boundary inside `transforms/` is less visible than four siblings; sub-package READMEs document the split |
| Each top-level package maps to a public ABC (ADR-0001): `transforms/` ↔ `Transform`, `recipes/` ↔ `RecipeEngine` | `transforms/cve/` is a slightly unintuitive location for advisory-feed code; advisory data fundamentally exists to feed transforms, so the placement defends |
| Phase 7's `DockerfileBaseImageSwapTransform` lives under `transforms/` next to `npm_package_upgrade.py`; no new package | If Phase 7 introduces a non-transform-shaped concern (e.g., image-scan-as-a-service), it cannot reuse `transforms/`; same is true under four-package layout |
| Validators live next to the transform they validate; no `validation/` top-level adds noun for what is functionally a pre-transform fact-emitter | `LockfilePolicyScanner` is conceptually pre-transform but lives under `validation/`; the README explains |
| `production/design.md §2.5` "Extension by addition" honored: zero edits to Phase 0/1/2 packages | The `Recipe` Pydantic model lives under `recipes/models.py`; consumers (selector, engine, transform) import from one canonical location |

## Consequences

- New top-level packages: `src/codegenie/transforms/` and `src/codegenie/recipes/`.
- Phase 0's fence CI matrix gains two entries: `transforms/` and `recipes/` may not import `anthropic`, `openai`, `langgraph`, etc.
- Each sub-package (`transforms/cve/`, `transforms/validation/`) ships a `README.md` describing why it lives where it does — protects against future "move it to a top-level" arguments without ADR amendment.
- `pyproject.toml` adds `codegenie.transforms` and `codegenie.recipes` to the package list; no new console-script entry points (the new CLI subcommands compose into the existing `codegenie` entry point).
- The "four new packages" layout from `design-best-practices.md` is explicitly rejected; this ADR documents why.
- Phase 4's `planning/` package is a future architectural review; this ADR does not pre-judge it but does set the precedent that the bar is "maps to a public ABC."

## Reversibility

**Medium.** Splitting `transforms/cve/` into a top-level `cve/` later is mechanically additive — move files, update imports — but every consumer of `from codegenie.transforms.cve import Advisory` would need to change, plus every reference in Phase 4–7 code. Folding `recipes/` into `transforms/` is similarly mechanical. The decision *not* to ship four packages is the load-bearing piece; reversing it (adding a third or fourth package in Phase 3 retroactively) is a Phase 3 ADR amendment.

## Evidence / sources

- `../final-design.md §"Goals" §"Contract goals"` row 2 — two-package commitment
- `../final-design.md §"Architecture"` package-layout block
- `../final-design.md §"Synthesis ledger" §"Conflict-resolution table"` row "New top-level packages"
- `../phase-arch-design.md §"Development view — module tree"`
- `../critique.md §"Attacks on the best-practices design" §"Concrete problems" #3` — four-package critique
- [Phase 2 README "Decisions noted but not yet documented"](../../02-context-gather-layers-b-g/ADRs/README.md) — Phase 2's discipline of folding cross-cutting concerns into existing packages
