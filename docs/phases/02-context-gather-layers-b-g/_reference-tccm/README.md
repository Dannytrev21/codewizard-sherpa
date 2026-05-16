# Reference TCCM for `index-health-self-check`

This directory holds the Phase 2 reference TCCM — a minimal Task-Class Context
Manifest (production ADR-0029) that exercises every field of the `TCCM`
Pydantic model and every variant of the five-primitive `DerivedQuery`
discriminated union (production ADR-0030). It is **documentation**, not a
plugin (02-ADR-0007); it lives under `docs/`, not under `plugins/`, deliberately
outside the namespace Phase 3 owns (production ADR-0031 §Consequences §1).

Consumed by `tests/integration/tccm/test_reference_tccm_roundtrips.py`, which
closes [`../phase-arch-design.md` §"Gap analysis" Gap 1](../phase-arch-design.md)
("Protocols defined, never called in Phase 2") by dispatching each
`DerivedQuery` variant to a mock adapter implementing all four Phase 2
`Protocol`s and asserting every Protocol method is invoked at least once.

Layout:

- `tccm.yaml` — the canonical reference manifest.
- `_invalid/` — single-defect fixtures that pin S1-04's `LoaderReason`
  taxonomy (`parse:`, `schema:`, `unknown_query_primitive:`).
- `_floors/` — minimal sibling manifests differing only in `confidence_floor`;
  cover all three `AdapterConfidence` variants.

Do not move these fixtures without updating the test paths and 02-ADR-0007.
