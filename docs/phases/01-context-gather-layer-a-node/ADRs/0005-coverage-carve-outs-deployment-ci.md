# ADR-0005: 90/80 coverage floor with 85/75 carve-out for `deployment.py` and `ci.py`

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** testing · coverage · ratchet · governance
**Related:** [Phase 0 ADR — coverage floor](../../00-bullet-tracer-foundations/final-design.md), ADR-0007

## Context

Phase 0 landed an 85% line / 75% branch coverage floor on `src/codegenie/`. Phase 1 ships five new probes plus shared parsers, lockfile parsers, catalogs, and per-probe sub-schemas — and inherits the ratchet question: bump the floor to 90/80, or accept that the new code drags the floor down.

The best-practices lens proposed a blanket 90/80 ratchet. The critic (Rule 9 — "tests verify intent, not just behavior") flagged a real risk: `deployment.py` and `ci.py` have many structurally-narrow branches (one `if` per supported CI provider, one `if` per deployment file marker) where a blanket 90% line coverage is satisfied by tests that exercise every branch but assert *nothing meaningful* — coverage-shaped theater. The performance lens stayed silent on coverage.

The synthesizer's position: bump the floor to 90/80 but **declare an explicit per-module carve-out** at 85/75 for `deployment.py` and `ci.py`, with the carve-out gated by ADR amendment so it doesn't drift into the rest of the codebase.

## Options considered

- **Blanket 90/80 across all of `src/codegenie/`.** Clean rule; easy to communicate. Drives Rule 9 violations on structurally-narrow modules; tests verify branches, not behaviors.
- **Stay at 85/75 (no ratchet).** Phase 0's bar. Doesn't reflect that Phase 1 ships substantially more deterministic-parser code with clean test fixtures.
- **90/80 with `deployment.py` and `ci.py` carved out at 85/75, declared in `pyproject.toml`, ADR-gated.** Ratchet on the modules that earn it; explicit relaxation where structural branch shape makes the higher floor gameable.

## Decision

**`pyproject.toml` declares two coverage thresholds:**

- **Default (`src/codegenie/` except the exclusions):** **90% line, 80% branch.**
- **Per-module floor for `src/codegenie/probes/deployment.py` and `src/codegenie/probes/ci.py`:** **85% line, 75% branch.**
- **Excluded entirely:** `src/codegenie/cli.py` (entrypoint glue; exercised by integration tests, not unit).

CI fails if any module drops below its declared floor.

**Further carve-outs require their own ADR.** This ADR is the registry root for per-module coverage relaxations. A new probe added in Phase 2+ that wants relaxation must explain (a) why the module's branch shape makes the higher floor gameable, (b) what specific test pattern would satisfy the higher floor and *be theater*, and (c) what intent-verifying tests it ships instead.

## Tradeoffs

| Gain | Cost |
|---|---|
| Real ratchet on the deterministic-parser code (parsers, lockfile helpers, memo, catalogs, probe ABC) where 90/80 is honest | Two modules at a lower floor — explicit relaxation that requires governance discipline |
| `deployment.py` and `ci.py` ship intent-verifying tests rather than branch-checkbox tests — Rule 9 conformance | Per-module floors are more `pyproject.toml` config; the configuration shape is the new convention |
| Explicit ADR-amendment trigger prevents drift — adding a third carved-out module is a public decision | Naive "just lower it" PRs face friction; intentional reviewers see the trigger immediately |
| Phase 2 inherits the convention — Layer B/C/D/G probes can request carve-outs with the same shape | Carve-outs accumulate over time; the ADR registry must be maintained as the surface area grows |
| Adversarial-fixture corpus + property-of-bytes oracle (ADR-0003 / Gap 3) carry the load-bearing weight on `deployment.py` / `ci.py` correctness — coverage is supporting, not load-bearing | Coverage numbers alone don't tell the story; reviewers must read the test names to understand intent |

## Consequences

- `pyproject.toml`'s `[tool.coverage.report]` and `[tool.pytest.ini_options]` declare the per-module floors. The CI `test` job's `--cov-fail-under` and per-file thresholds enforce.
- `tests/unit/probes/test_ci.py` and `tests/unit/probes/test_deployment.py` carry the intent-verifying load: GitHub Actions matrix workflows; multi-provider repos; Helm multi-env values; Kustomize zip-slip path; Terraform paths-only — each test is named for the *behavior* it pins, not the branch.
- A Phase 2 PR proposing a third carved-out module triggers an ADR amendment referencing this one.
- The `regen` for `pyproject.toml`'s per-module coverage table is a script under `scripts/` (deferred to implementer; not load-bearing).
- The CI walltime delta (per `final-design.md` "Resource & cost profile") includes the adversarial corpus, not the coverage check — running coverage is ~1 s on top of the test suite.

## Reversibility

**High.** Relaxing the global floor back to 85/75 is a `pyproject.toml` edit; the carve-outs become redundant and can be removed. Tightening to a uniform 90/80 (no carve-outs) requires adding intent-verifying tests to `deployment.py` and `ci.py` — work the modules would benefit from regardless. No on-disk artifact embeds the coverage floor.

## Evidence / sources

- `../final-design.md "Goals"` — the 90/80 + 85/75 carve-out rule
- `../final-design.md "Departures from all three inputs" #5` — codification rationale
- `../phase-arch-design.md "Goals"` #7 — the same rule in arch shape
- `../phase-arch-design.md "Testing strategy" "CI gates"` — `--cov-fail-under=90` enforcement
- Global Rule 9 — "Tests verify intent, not just behavior"
- ADR-0007 — the warning-ID pattern (related structural defense)
