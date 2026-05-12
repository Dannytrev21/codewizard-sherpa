# ADR-0008: Conventions catalog `detect.type` is a closed enum with CI lint enforcing schema-code parity

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** catalog · data-as-code · ci-lint · extension-by-addition · convention-degradation
**Related:** [Phase 1 ADR-0006](../../01-context-gather-layer-a-node/ADRs/0006-native-module-catalog-versioning.md), [Phase 0 ADR-0008](../../00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md), ADR-0004

## Context

Phase 2 introduces `src/codegenie/catalogs/conventions/<language>.yaml` and `src/codegenie/catalogs/shell_replacements/<language>.yaml`, both with `_schema.json` siblings. `ConventionProbe` (D5) and `ShellUsageProbe` (C5) dispatch on the `detect.type` field of each catalog entry via a Python `match/case` in the probe's `_apply_detector(...)` helper.

The "organizational uniqueness as data, not prompts" load-bearing commitment (`production/design.md §2`, `CLAUDE.md`) is the architectural intent. The critic's cross-design observation #3 (`critique.md`) flagged the recurring failure mode: **all three lenses' catalog discipline is enforced by convention alone.** The closed `detect.type` enum is fine until Phase 7 (Chainguard distroless) adds new detector types; if the implementer adds a `match/case` branch without bumping `_schema.json`, the catalog grows a DSL and the discipline is gone.

Phase 7's `CLAUDE.md`-named role as the test of "extension by addition" makes this concrete: distroless conventions are richer than vuln-remediation conventions; the enum *will* grow; how it grows decides whether the discipline survives.

## Options considered

- **Open `detect.type` field.** Any string accepted; the probe's `_apply_detector` is the only enforcement. Maximum flexibility; the catalog becomes a DSL within two phases.
- **Closed enum enforced by `_schema.json` only.** Schema rejects unknown values; probe code can still grow a `match/case` branch ahead of the schema and the test will pass (with the new value never hitting the schema). No symmetric defense.
- **Closed enum + CI lint asserting `match/case` ↔ `_schema.json` enum parity [synth].** Both directions enforced. Schema changes without code changes fail CI; code changes without schema changes fail CI. The discipline is compiler-enforced.

## Decision

**Phase 2 ships the conventions and shell-replacements catalogs with a closed `detect.type` enum in `_schema.json`, and a CI lint asserting bidirectional parity with the probe's `match/case` dispatch.**

- **Catalog shape.** `src/codegenie/catalogs/conventions/<language>.yaml` and `src/codegenie/catalogs/shell_replacements/<language>.yaml` declare `catalog_version: int` (Phase 1 ADR-0006 pattern) and a list of entries. Each entry's `detect.type` is constrained to the closed enum in `_schema.json`.
- **Probe dispatch.** `ConventionProbe._apply_detector(entry)` (and `ShellUsageProbe._apply_detector`) use Python `match/case` keyed on `entry["detect"]["type"]`. The `match` is *exhaustive*: every enum value has a `case`; `_` raises a typed exception.
- **CI lint.** `scripts/lint_catalog_enum_parity.py` (or `tests/conformance/test_catalog_enum_parity.py`, equivalently) asserts:
  - every `case "<value>"` arm in `_apply_detector` has a corresponding entry in the `_schema.json` enum;
  - every value in the `_schema.json` enum has a corresponding `case` arm in `_apply_detector`.
  - Mismatch in either direction → CI fails. Test runs on every PR.
- **Adding a new `detect.type`.** Requires a *single PR* that:
  1. Adds the new value to `_schema.json`'s enum.
  2. Adds a new `case` arm in `_apply_detector` with the dispatch logic.
  3. Bumps `catalog_version` (minor for additive; major for breaking).
  4. Updates the affected probe's sub-schema if the new dispatch produces a new output shape.
- **Removing a `detect.type`.** Requires deprecation: keep the schema enum value, keep the case arm, mark deprecated for one major-version cycle. CI lint passes throughout.

## Tradeoffs

| Gain | Cost |
|---|---|
| Catalog can never grow a code branch without a schema bump — Phase 7 distroless additions will pass the lint or fail loud | Adding a new `detect.type` becomes a 3-4 file PR; encourages thinking before adding |
| Schema-code parity is compiler-enforced rather than reviewer-enforced — the "convention degrades over time" failure mode is closed (critic cross-design obs #3) | The lint adds a CI step (~3 s); adds a new test artifact to maintain |
| Phase 7's `CLAUDE.md`-named "extension by addition" test now has a structural witness — the lint passes iff Phase 7 added types correctly | The lint script must understand Python `match/case` AST (use `ast.parse` + visitor); ~80 LOC of CI scaffolding |
| `catalog_version` discipline (Phase 1 ADR-0006) generalizes — additions are minor bumps; removals are major bumps with deprecation cycles | Multi-language catalogs (`conventions/node.yaml`, `conventions/python.yaml`, …) all share the same `_schema.json#enum`; cross-language type additions require coordination |
| The closed-enum stance is documented and defended; future "let's make this a DSL" temptations are blocked | A reviewer wanting a quick fix without an enum bump may be tempted to bypass the lint; the lint must be CI-gating, not advisory |
| Failure mode is loud (lint fails at PR time, not at runtime when a probe sees an unknown type) | Lint runs after CI install; failing late in CI is annoying; mitigated by pre-commit hook (optional) |

## Consequences

- `src/codegenie/catalogs/conventions/_schema.json` declares `detect.type` as a closed enum (initial Phase-2 entries; documented).
- `src/codegenie/catalogs/shell_replacements/_schema.json` ditto.
- `src/codegenie/probes/convention.py` and `shell_usage.py` use Python `match/case` for dispatch; `_` raises `UnsupportedConventionType` (typed exception).
- `tests/conformance/test_catalog_enum_parity.py` (or `scripts/lint_catalog_enum_parity.py` invoked from a `pytest` runner) asserts bidirectional parity for each `(probe, catalog)` pair.
- The lint is wired into the `phase2-lint` CI job alongside the existing `fence` (no-LLM) check.
- Phase 7 (Chainguard distroless) extends the enum by addition; the lint structurally proves Phase 7 met "extension by addition" — the same PR adds schema, code, and sub-schema. If Phase 7 fails to do so, the lint fails the PR.
- Future catalogs (e.g., Phase 3's `vuln_remediation/<language>.yaml` recipes catalog if it adopts the same shape) inherit this discipline by extension.
- The "data, not code" architectural commitment in `production/design.md §2` is now testable.

## Reversibility

**High.** Removing the lint is a one-script deletion. Removing the closed-enum constraint is a one-line `_schema.json` edit (changing `enum` to omitting it). The structural defense disappears at that moment; the code keeps working. The reversibility is high; the *cost of reversal* is the failure mode this ADR exists to prevent — silent DSL growth — which is why the lint must be CI-gating.

## Evidence / sources

- `../final-design.md "Components" §13 Catalog version policy + closed-enum CI gate` — the design statement
- `../final-design.md "Conflict-resolution table" D18` — the resolution
- `../final-design.md "Departures from all three inputs" #6` — synth call-out (addresses critic shared blind spot #3)
- `../final-design.md "Shared blind spots considered" #3` — the framing
- `../phase-arch-design.md "Components" §13` — implementation specifics
- `../critique.md "Cross-design observations"` "Where do all three quietly agree on something questionable?" #3 — the framing
- [Phase 1 ADR-0006](../../01-context-gather-layer-a-node/ADRs/0006-native-module-catalog-versioning.md) — the catalog-versioning pattern this generalizes
- `CLAUDE.md` "Extension by addition" — the load-bearing commitment this defends
