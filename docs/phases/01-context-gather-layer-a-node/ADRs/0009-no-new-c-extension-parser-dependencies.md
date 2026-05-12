# ADR-0009: No new C-extension parser dependencies in Phase 1

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** dependency-policy · supply-chain · cve-surface · simplicity
**Related:** ADR-0003, ADR-0008, [Phase 0 ADR-0006](../../00-bullet-tracer-foundations/ADRs/0006-pyproject-toml-extras-shape.md)

## Context

The performance lens (`design-performance.md`) proposed three new C-extension parser dependencies — `msgpack` (for the rejected inter-probe side-channel; see ADR-0002), `pyjson5` or `orjson` (for `tsconfig.json` parsing — JSON-with-comments), and `ruamel.yaml` in C-mode (for faster YAML parsing) — plus an unresolved bench-the-winner-later open question between `pyjson5` and `orjson + strip-comments-pass`. The justification was warm-path latency wins.

The critic (`critique.md "Attacks on the performance-first design"` #6) framed this directly: each new C extension is a new CVE feed to follow, a new wheel build for every platform in the matrix, a new mypy-stubs problem, and the `fence` job verifies *no LLM SDKs* — not *no fast-parser drift*. Phase 0 ratified `pyyaml.CSafeLoader` + stdlib `json` + `blake3`; adding three more without a named-trigger threshold is dependency creep with structural cost.

The synthesizer (`final-design.md "Conflict-resolution table"` row 8) refused all three. The only Phase 1 dep addition is `pyarn` (a pure-Python YAML-format-adjacent parser, ADR-0003), conditionally and with a hand-rolled fallback.

This ADR documents the **policy** so the closure stays bounded across future phases.

## Options considered

- **Allow C extensions whenever performance wins justify (the performance lens).** Maximum flexibility; every dep is a separate cost-justification PR. CVE-feed surface grows linearly with deps; mypy-stub problems compound.
- **Hard ban on all C extensions.** Simple rule. Rules out `blake3` (Phase 0 ratified for fast content hashing); too strict.
- **Inherit Phase 0's ratified parser closure (`pyyaml.CSafeLoader` + stdlib `json` + `blake3`); new C extensions land only via ADR amendment with a named trigger.** Closed default; explicit extension path.

## Decision

**Phase 1's parser dependency closure is exactly Phase 0's plus `pyarn` (conditional):**

- **Allowed:** `pyyaml` (via `CSafeLoader`), stdlib `json`, stdlib `os` + `pathlib` (for `O_NOFOLLOW`), `blake3` (Phase 0 ratified), `jsonschema` (Phase 0 ratified), `Pydantic` (Phase 0 ratified for `_ProbeOutputValidator`), `click` (Phase 0 CLI).
- **Conditionally allowed:** `pyarn` (pure-Python `yarn.lock` parser, per ADR-0003 — selection by maintenance heuristic at land-time; hand-rolled fallback ships either way).
- **Not allowed in Phase 1:** `orjson`, `pyjson5`, `ruamel.yaml`, `msgpack`, `python-hcl2` / `hcl2`, `lcov-parser`, and any other C-extension parser regardless of performance claim.

**A new C-extension parser dep in any future phase requires:**
1. A named-trigger threshold (e.g., "p95 cold-gather latency exceeds 8 s on the 1k-file fixture for ≥ N consecutive CI runs").
2. The threshold is measured against the existing parser closure first (often the answer is "tune the existing path").
3. If the trigger fires, an ADR amends this one with the specific dep added and the CVE-feed / wheel-matrix / stubs cost accepted.

The `fence` CI job (Phase 0 ADR-0002) extends in Phase 1 to assert no LLM SDK is in the closure. A future amendment may extend `fence` to assert no new C-extension parser is added without ADR — currently scope-creep, deferred.

## Tradeoffs

| Gain | Cost |
|---|---|
| CVE-feed surface stays bounded — `pip-audit` + `osv-scanner` watch a small, known closure | Performance wins from `orjson` (~3× JSON parse) and `ruamel.yaml C-mode` are not captured; cold-path latency is at stdlib pace |
| `lcov-parser` rejected — `coverage/lcov.info` parsed by a 40-LOC stdlib line-scanner; the format is simple enough | Coverage data parsing is hand-rolled; tested in `tests/unit/probes/test_test_inventory.py` |
| Hand-rolled `jsonc` (line + block comment stripper, ~30 LOC) avoids the `pyjson5`-vs-`orjson` indecision | `jsonc.py` is custom code with adversarial-input risk; mitigated by `tests/adv/test_tsconfig_pathological.py` |
| `pyarn` (pure-Python) is the only Phase 1 addition; if it abandons, the hand-rolled fallback covers (ADR-0003) | Two implementations to maintain (parity-tested per ADR-0003 Gap 3) |
| The "named trigger" rule converts dep-creep into a deliberate cost-justification | Future engineers may experience friction adding a dep that obviously helps; the friction is the point |
| Wheel-matrix stays stable across CI platforms; mypy stubs stay simple | Some future probe class may genuinely need a C-extension parser (e.g., SBOM parsing in Phase 2); that's the ADR-amendment path |
| Composes with ADR-0008's in-process caps — the caps work uniformly because we control the parser entry points | A future C-extension parser added via amendment must integrate with `parsers/` and obey the cap contract |

## Consequences

- `pyproject.toml`'s `gather` extras (per Phase 0 ADR-0006) lists exactly the ratified deps plus optional `pyarn`. No `orjson`, `pyjson5`, `ruamel.yaml`, `msgpack`, `hcl2`.
- The `fence` CI job's import-graph assertion continues to bind: no LLM SDK in `src/codegenie/`. Parser CVE-feed watching is delegated to `pip-audit` + `osv-scanner` + Dependabot, not to `fence`.
- `src/codegenie/parsers/jsonc.py` ships a hand-rolled comment stripper. Fuzz-tested in `tests/adv/test_tsconfig_pathological.py` against unterminated strings, deeply nested block comments, circular `extends` chains.
- `src/codegenie/probes/test_inventory.py` parses `coverage/lcov.info` with a 40-LOC stdlib line-scanner. No `lcov-parser` dep.
- `src/codegenie/probes/deployment.py` does not parse Terraform `*.tf` files (no `python-hcl2`); records paths only. The "no Helm template rendering / no HCL parsing" decision is recorded in ADR-0011.
- Phase 2's `IndexHealthProbe` and other probes inherit the same closure; new C-extension deps in Phase 2+ trigger an ADR amendment to this one.

## Reversibility

**High.** Adding any of `orjson`/`pyjson5`/`ruamel.yaml`/`msgpack`/`hcl2` later is a `pyproject.toml` edit plus a parser-module integration plus an ADR amendment to this one. The hand-rolled `jsonc` and `lcov` paths continue to work; the new dep would replace them at the parser-module level if the trigger justifies. Nothing in cached `repo-context.yaml` outputs depends on the parser identity — the slice shapes are parser-agnostic.

## Evidence / sources

- `../final-design.md "Resource & cost profile" "External-dep additions"` — strict refusal of [P]'s extras and [B]'s `lcov-parser`
- `../final-design.md "Conflict-resolution table" row 8` — the resolution
- `../phase-arch-design.md "Non-goals" #9` — explicit C-extension drift rejection
- `../phase-arch-design.md "Component design" #8 Safe-parse helpers` — `jsonc.py` hand-rolled rationale
- `../critique.md "Attacks on the performance-first design"` #6 — the framing
- ADR-0003 — `pyarn` conditional adoption (the one exception)
- ADR-0008 — in-process caps that depend on a controlled parser entry-point set
- [Phase 0 ADR-0006](../../00-bullet-tracer-foundations/ADRs/0006-pyproject-toml-extras-shape.md) — the extras shape this lives inside
