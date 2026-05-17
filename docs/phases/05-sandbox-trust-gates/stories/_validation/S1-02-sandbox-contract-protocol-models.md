# Validation report — S1-02 `sandbox/contract.py` Protocol + four frozen Pydantic models

**Story:** [`../S1-02-sandbox-contract-protocol-models.md`](../S1-02-sandbox-contract-protocol-models.md)
**Validated:** 2026-05-16
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

S1-02 ships the load-bearing public surface of Phase 5: the `SandboxClient` Protocol plus four frozen Pydantic models (`CopyInEntry`, `SandboxSpec`, `SandboxRun`, `SandboxHealth`) that every backend must accept/emit and that Phase 6 lifts unchanged into LangGraph node side-effects. The draft was structurally correct — the goal traced cleanly to ADR-0001 / ADR-0006 / ADR-0012, the field set matched `phase-arch-design.md §Data model` byte-exact (16 + 13 + 6 + 3 fields), and Out-of-scope was disciplined (hash *computation* deferred to S3-01, `env_allowlist.filter` to S1-05, `ObjectiveSignals` to S1-03, backends to Steps 3/6).

But it had **14 weaknesses** spanning all four critic lenses. Most consequentially:

1. **Coverage C-8 (block-tier):** the `(backend, gate_isolation_class)` cross-field correlation that Goals 5/6 mandate was unenforced. `SandboxRun(backend="docker_in_docker", gate_isolation_class="microvm")` would have constructed silently — a contractually nonsense state that would corrupt Phase 13 cost telemetry and break Goals 5/6 traceability.
2. **Tests M-6/M-7 (critical miss):** literal value spellings were tested *negatively* only (`backend="kvm"` rejected). An executor shipping `Literal["dind", "firecracker"]` would have passed every test in the draft TDD plan while breaking the Phase 13 cost ledger's primary-key contract.
3. **Test M-2/M-3:** only `SandboxSpec` was tested for `frozen=True` and `extra="forbid"`. `SandboxRun`, `SandboxHealth`, and `CopyInEntry` could have silently shipped `extra="ignore"` or `frozen=False`.
4. **Consistency #1:** the coverage floor wording conflated "95% branch" with the README's "95/90" — which is actually 95 *line* / 90 *branch*. Inconsistent floors across the project's stories would silently weaken the discipline.
5. **Consistency #2:** the draft prescribed `from typing import Mapping` — `typing.Mapping` is deprecated since Py 3.9 and the codebase is unanimous on `from collections.abc import Mapping` (10+ modules). CLAUDE.md Rule 11.
6. **Design-Patterns #1/#2:** `run_id: str` and `sandbox_spec_hash: str` are domain primitives crossing ≥ 5 module boundaries each. CLAUDE.md's "newtype when crossing ≥ 2 modules" rule + the Phase-2 precedent `TestId = NewType("TestId", str)` in [`src/codegenie/adapters/protocols.py:41`](../../../../src/codegenie/adapters/protocols.py:41) demanded the newtype now.

14 hardening edits applied in place; no `RESCUE`-tier findings (every gap was patchable by adding ACs and tightening the TDD plan, not by re-architecting the story's goal or scope). No Stage-3 research needed — every gap was answerable from the phase arch, the three honored ADRs, the High-level-impl Step 1 done-criteria, and codebase precedents (`adapters/protocols.py`, `result.py`).

## Context Brief (Stage 1)

### Story snapshot

- **Goal (verbatim):** Ship `src/codegenie/sandbox/contract.py` exposing the `SandboxClient` Protocol plus the four frozen `extra="forbid"` Pydantic models with the field names and types from `phase-arch-design.md §Data model`.
- **Non-goals (from Out-of-scope):** hash computation (S3-01), env-allowlist filter behavior (S1-05), `SandboxHealthProbe` (S3-06), backend implementations (Step 3/6), `ObjectiveSignals` (S1-03).

### Phase 5 exit criteria touched

- Step 1 done-criteria (High-level-impl.md §Step 1): `pytest tests/sandbox/test_contracts.py` green — every model rejects unknown fields, is frozen, round-trips canonical JSON; `mypy --strict src/codegenie/sandbox src/codegenie/gates` clean; branch coverage on `sandbox/contract.py` ≥ 95% (actually 95/90 — see Consistency #1).
- Goals 5 + 6: `gate_isolation_class: "shared_kernel"` for DinD, `"microvm"` for Firecracker — the Literal *spellings* are downstream-contract-load-bearing.
- Goal 7: `SandboxSpec.env` is the post-filter view (ADR-0012); the *type* (`Mapping[str, str]`) is locked here.

### Load-bearing commitments touched

- **CLAUDE.md "Extension by addition"** — adding a new backend or model must be by *addition* (new Protocol implementer + new `@register_sandbox_backend` entry). The contract module itself stays Open/Closed.
- **CLAUDE.md "Domain identifiers ... newtype when crossing ≥ 2 modules"** — `RunId`, `SandboxSpecHash` cross 5+ modules each.
- **CLAUDE.md Rule 11 (match conventions)** — `Mapping` source, `from __future__ import annotations`, `__all__` discipline, module-purity invariant.
- **ADR-0001** (two-chokepoint sandbox seam) — contract lives in `sandbox/contract.py`, no leak into `validation.*`.
- **ADR-0006** (Protocol vs ABC) — Protocol = purely structural; no `__init__`, no class attrs, no default method bodies. This story is the ADR-0006 reference implementation.
- **ADR-0012** (env allowlist) — `SandboxSpec.env: Mapping[str, str]` is the post-filter view (read-only intent).
- **Phase 6 lift-unchanged commitment** — the four models + Protocol are the seam Phase 6's LangGraph nodes consume. Illegal-states-representable here = illegal-states-inherited downstream.

### Open/Closed boundaries (extension-by-addition contract)

- **New backend** → register via `@register_sandbox_backend` (S1-05). `SandboxClient` Protocol does not change. `SandboxRun.backend: Literal[...]` widens only via ADR-0001 amendment (closed mirror of the open registry — surfaced as a forward-seam note).
- **New field on a model** → ADR amendment + rolling-back-compat plan (frozen + `extra="forbid"` means a producer adding a field crashes consumers — intentional).
- **New `Literal` value** (`network`, `confidence`, `mode`) → ADR amendment. Telemetry consumers in Phase 13 key on the exact spelling.

### Phase 1/2 prior art consulted

- [`src/codegenie/adapters/protocols.py`](../../../../src/codegenie/adapters/protocols.py) — Phase 2's four `runtime_checkable` Protocols. Established `from __future__ import annotations`, module docstring with cross-references, `TestId = NewType("TestId", str)` precedent, and the "no I/O, no logger, no sibling-module imports" module-purity invariant.
- [`src/codegenie/result.py`](../../../../src/codegenie/result.py) — frozen + `extra="forbid"` + `arbitrary_types_allowed=True` pattern; alphabetized `__all__`; module docstring cites the relevant ADR.
- [`src/codegenie/adapters/__init__.py`](../../../../src/codegenie/adapters/__init__.py) — `__all__` discipline; pytest-`Test*`-prefix collision avoidance (`TestInventoryAdapter` aliased on import).

### Open ambiguities (resolved before Stage 2)

- **Should `sandbox_spec_hash` carry hex-shape validation in `contract.py` or in `SandboxSpecBuilder`?** Resolved as builder-side (S3-01 owns shape validation; contract.py uses opaque `SandboxSpecHash` NewType). Rationale: keep the contract a typed envelope, not a guard; aligns with the story's existing Out-of-scope discipline.
- **Should `SandboxRun` be a sum type (`SuccessfulRun | TimedOutRun | OomKilledRun | FailedRun`)?** Resolved as no — the architect's arch §Data model prescribes a flat shape with cross-field `@model_validator`s. Sum-type refactor is a future story's concern; the validators make illegal states unrepresentable at the lower cost-of-change.
- **Should every `str` field get a newtype?** Resolved as no — Rule 2 caps premature abstraction. Only `RunId` and `SandboxSpecHash` cross the rule-of-three threshold today; `base_image`, `label`, etc. wait until their first typed consumer.

## Stage 2 — critic reports

### 2A · Coverage critic (verdict: COVERAGE-RESCUE → patched to HARDEN)

The Coverage critic flagged one `block`-tier finding (C-8) and 12 `harden`-tier findings:

| # | Severity | Finding | Fix applied |
|---|---|---|---|
| C-1 | harden | `extra="forbid", frozen=True` asserted only by side-effect; a class with `extra="ignore", frozen=True` would pass the legacy mutation test | New AC-3 asserts `Cls.model_config['extra'] == 'forbid'` AND `Cls.model_config['frozen'] is True` for every model directly |
| C-2 | harden | `@runtime_checkable` asserted only via `isinstance` — a `Protocol` without the decorator using `__subclasshook__` would pass | New AC-2 asserts `getattr(SandboxClient, "_is_runtime_protocol", False) is True` |
| C-3 | harden | "Defines exactly two methods" — set-subset, not set-equality, leaving room for a 3rd method | New AC-2a uses `typing.get_protocol_members(SandboxClient)` and exact-set equality |
| C-4 | harden | No AC pinned the *byte-exact spellings* of any Literal — `"dind"` would round-trip | New AC-4 asserts `typing.get_args(...)` byte-equal to canonical tuples for all 5 Literal fields |
| C-5 | harden | `SandboxSpec.env: Mapping[str, str]` annotation source unenforced (ADR-0012 dependency) | New AC-5 asserts `typing.get_type_hints(SandboxSpec)['env']` origin is `collections.abc.Mapping`, args `(str, str)` |
| C-6 | harden | `CopyInEntry.dst: PurePosixPath` vs `Path` distinction unenforced | New AC-5a asserts `get_type_hints` returns the exact path types |
| C-7 | harden | `SandboxRun.trace_path = None` JSON round-trip behavior unenforced | New AC-5b asserts `"trace_path":null` in dump + `None` after re-validate |
| **C-8** | **block** | **Cross-field correlation `(backend, gate_isolation_class)` unenforced — Goals 5/6 commitment** | **New AC-7b enforces the four-pair invariant via `@model_validator(mode="after")` on `SandboxRun`; positive + negative paths tested** |
| C-9 | harden | `started_at <= ended_at` unenforced | New AC-7c — same `@model_validator` |
| C-10 | harden | Non-negativity unenforced on numeric fields (`time_budget_seconds`, `memory_limit_mib`, `pids_limit`, `duration_ms`, `microvm_seconds`, `image_pull_bytes`) | New AC-7 + AC-7a with `Annotated[T, Field(gt=0)]` / `Field(ge=0)` constraints |
| C-11 | harden | `sandbox_spec_hash` shape unenforced | **Punted to S3-01** per Tests M-17 reasoning — contract.py stores `SandboxSpecHash` NewType opaquely; shape validation lives in the builder where it's policy, not a typed envelope concern. Documented as a Note + Out-of-scope addition |
| C-12 | harden | `__all__` exactness unenforced | New AC-1a asserts `set(__all__)` equality with the 7-symbol public surface |
| C-13 | harden | ADR-0006 "no shared default behavior" unenforced — a future contributor could add a default `health()` body | New AC-2b: AST walk asserts Protocol method bodies are exactly `Expr(Constant(Ellipsis))` |
| C-14 | nit | "TDD plan's red tests exist..." is a process AC, redundant with DoD | Kept (low-cost reminder) |
| C-15 | nit | Coverage AC said "≥ 95%" without specifying line vs branch (README is 95/90) | Tightened AC-11: "line ≥ 95% AND branch ≥ 90%" |

The block-tier C-8 is patchable — the `@model_validator` lives in `SandboxRun`, not in a re-architected story. Promoted RESCUE → HARDEN.

### 2B · Test-quality critic (verdict: TESTS-HARDEN)

Mutation analysis — 19 plausible wrong implementations evaluated. Headline misses caught in the harden:

| # | Wrong implementation | Caught by draft TDD? | Caught after harden? |
|---|---|---|---|
| M-2 | `SandboxRun`/`SandboxHealth`/`CopyInEntry` use `extra="ignore"` or `frozen=False` | No — only `SandboxSpec` was tested for both | Yes — parametrized `test_each_model_is_frozen_and_extra_forbid_in_config` over all four models |
| M-4 | Drop `@runtime_checkable` decorator | Partial — `TypeError` surface, not a clean failure | Yes — direct `_is_runtime_protocol` assertion |
| M-5 | Rename `health` → `is_healthy` | Partial — only via missing-method side-effect | Yes — `typing.get_protocol_members` set-equality |
| **M-6** | **Ship `Literal["dind", "firecracker"]`** | **No — negative test on `"kvm"` still rejects** | **Yes — `typing.get_args` byte-equal + positive-construction parametrized test** |
| **M-7** | **Ship `Literal["linux_namespace", "microvm"]`** | **No — same gap as M-6** | **Yes — same fix** |
| M-8 | `CopyInEntry.dst: Path` instead of `PurePosixPath` | No — Pydantic coerces strings at runtime | Yes — `get_type_hints` source-level check |
| M-9 | `SandboxSpec.env: dict[str, str]` instead of `Mapping[str, str]` | No | Yes — same source-level check (ADR-0012 enforcement) |
| M-12 | Add a 3rd Protocol method (e.g., `cleanup`) | No | Yes — `get_protocol_members` set-equality |
| M-13 | Give a Protocol method a non-`...` body | No — ADR-0006 violated silently | Yes — AST walk on `cls.body[0].value.value is Ellipsis` |
| M-14 | `SandboxRun(backend="firecracker", gate_isolation_class="shared_kernel")` | No | Yes — `@model_validator` + AC-7b |
| M-16 | `time_budget_seconds=-1` accepted | No | Yes — `Field(gt=0)` + AC-7 |
| M-18 | JSON byte-equality drifts under env reordering | Partial — single fixture round-trip | Yes — hypothesis property test with `dictionaries` strategy |
| M-19 | AC-6 said "property test with hypothesis" but TDD plan had no hypothesis code | **Disconnect** | Yes — explicit `@given`/`@settings` test in TDD plan |

Original tests that survived review:
- `test_spec_rejects_unknown_field` — adequate for `SandboxSpec` (kept, generalized).
- `test_spec_is_frozen` — adequate, but only one model (kept, parametrized).
- `test_copy_in_default_mode_ro` — kept verbatim.

Properties added:
- `test_spec_canonical_json_round_trip_is_byte_stable` — `@given` over env dict, cmd list, allowlist with `@settings(max_examples=50)`. Targets the Phase 9 cache-key seam.
- Parametrized `test_each_model_rejects_unknown_field` and `test_each_model_is_frozen_at_runtime` — uniform coverage across the four models.

### 2C · Consistency critic (verdict: CONSIST-HARDEN)

| # | Severity | Finding | Fix applied |
|---|---|---|---|
| 1 | harden | Coverage floor wording: AC said "≥ 95% branch" but README is 95/90 (95 line / 90 branch) | Tightened AC-11: "line ≥ 95% AND branch ≥ 90%" + sentence in Validation notes |
| 2 | harden | `Mapping` import source: draft prescribed `from typing import ... Mapping` but the codebase is unanimous on `from collections.abc import Mapping` (10+ files); `typing.Mapping` deprecated since 3.9 | Updated Implementation outline §1 + Notes for the implementer; AC-5 now asserts the `Mapping` origin |
| 3 | harden | ADR-0006 "no shared default behavior" rule encoded only in Refactor section (not testable as an AC) | Promoted to AC-2b (AST walk) + AC-2c (no `__init__`, no class attrs) |
| 4 | harden | ADR-0012's `Mapping[str, str]` env type unenforced at AC level | New AC-5 asserts the annotation source |
| 5 | harden | `from __future__ import annotations`, module docstring, `__all__` discipline absent from AC level; codebase precedent in `adapters/protocols.py` consistent | New ACs 1a + 9 + 9a + 9b + a dedicated `test_contract_purity.py` mirroring the Phase-2 precedent |
| 6 | nit | `run_id` documented as UUID7 in arch but story Impl outline doesn't mention | Updated Impl outline §2 to document UUID7 generation as S3-02's job + Note in the NewType docstring |
| 7 | nit | No AC for fence-test non-regression | New AC-12 calls out `tests/schema/test_no_llm_imports_in_sandbox.py` (if present) |

No `RESCUE`-tier findings — no contradiction with any ADR; the gaps were under-specification that promoted-to-AC level fixes.

### 2D · Design-patterns critic (verdict: PATTERNS-HARDEN)

| # | Severity | Finding | Fix applied |
|---|---|---|---|
| 1 | harden | Primitive obsession on `run_id: str` — crosses ≥ 5 module boundaries (contract → ledger S2-01 → runner S5-02 → cost S7-03 → CLI S8-01); CLAUDE.md rule + Phase-2 `TestId` precedent demand a NewType | New `RunId = NewType("RunId", str)` at module top; new AC-6 asserts the annotation + supertype |
| 2 | harden | Same for `sandbox_spec_hash: str` — crosses contract → builder S3-01 → runner S5-02 → Phase 9 cache | New `SandboxSpecHash = NewType("SandboxSpecHash", str)`; AC-6a |
| 3 | harden | Illegal-states-representable on `SandboxRun` (mismatched backend/isolation pair, ended_at < started_at, simultaneous timed_out + killed_by_oom) and `SandboxSpec` (network=none with non-empty egress_allowlist) | `@model_validator(mode="after")` on both classes; AC-7b/c/d/e |
| 4 | harden | Missing numeric range constraints (smart-constructor pattern) | `Annotated[T, Field(gt=0)]` on resource budgets; `Field(ge=0)` on observed counters; AC-7 + AC-7a |
| 5 | nit | `SandboxRun.backend: Literal[...]` is a closed mirror of the open `@register_sandbox_backend` registry — adding a 3rd backend requires editing the Literal | **Forward-seam note** in Notes for the implementer — not an Implementation change; Rule 2 caps the abstraction today |
| 6 | nit | Module purity invariant from Phase-2 [`adapters/protocols.py`](../../../../src/codegenie/adapters/protocols.py:26) should be mirrored | New `test_contract_purity.py` + AC-9a |
| 7 | clean | Hexagonal port (Protocol) + Strategy + plugin-via-registry are correctly framed | — |
| 8 | clean | Functional core (pure data + protocol, no I/O, no methods on models) is the right shape | — |

The two newtype findings (#1, #2) cross the rule-of-three threshold; making them ACs now prevents a future "introduce RunId" cleanup story that would touch every consumer.

## Conflict resolution (Stage 4 synthesizer)

- **Coverage C-11 vs Tests M-17:** Coverage wanted `Field(pattern=r"^[0-9a-f]{32}$")` on `sandbox_spec_hash`. Tests pointed out the story's Out-of-scope already defers hash *computation* to S3-01 — and the hex shape is *part of* the canonical-JSON hashing contract, not an independent invariant. Resolution: hash shape validation lives in `SandboxSpecBuilder` (S3-01), the contract uses the opaque `SandboxSpecHash` NewType. Documented in Out-of-scope + Notes. Consistency wins (the story's own boundary stays consistent).

- **Patterns #5 (forward-seam note vs AC) and Coverage AC-4 (positive Literal pinning):** the closed Literal on `SandboxRun.backend` is the *correct* design today (Rule 2 — two backends don't warrant a registry-of-literals type). Surfaced as a Note, not a code change. The AC-4 byte-exact spelling assertion catches `"dind"` regressions; the Note documents the ADR amendment path for Phase 7.

- **Coverage C-11 (hex shape) vs Patterns #2 (newtype):** complementary, not conflicting. Newtype goes in now; shape validation deferred. Both apply.

## Edits applied (summary)

1. New `Validation notes` block under the story header with 14 numbered headline edits.
2. **Acceptance criteria** rewritten from 9 ACs to 27 (grouped A–J): import surface, Protocol shape, model_config discipline, literal sets byte-exact (positive + negative), source-level annotation pinning, newtype seams, numeric range + cross-field invariants, JSON round-trip property, module purity, process gates.
3. **Implementation outline** rewritten from 7 numbered steps to 8 with explicit code-level prescriptions: `from __future__ import annotations`, `__all__`, `RunId`/`SandboxSpecHash` NewTypes, `Annotated[T, Field(...)]` constraints, `@model_validator` invariants, the canonical `Mapping` import source.
4. **TDD plan** rewritten from 2 test files (~80 LOC of test sketch) to 3 test files (~280 LOC of test sketch) with parametrized fixtures, hypothesis property test, AST walk, and source-level annotation checks. Every AC has a concretely-sketched test.
5. **Files to touch** updated: added `tests/sandbox/test_contract_purity.py`.
6. **Out of scope** updated to make explicit that hash *shape validation* (not just computation) is S3-01's job; `RunId` *generation* (not the type) is S3-02/S6-01's.
7. **Notes for the implementer** rewritten and 4× longer: Pydantic v2 idioms, domain-primitive discipline (CLAUDE.md Rule 11), cross-field invariant rationale (the contract is what Phase 6 lifts unchanged), forward-seam notes (closed Literal + sum-type considered-and-deferred), NewType discipline (rule-of-three applied), coverage process.

No story restructuring; the goal, scope, dependencies (S1-01), and ADR mapping (-0001, -0006, -0012) are unchanged.

## Final verdict

**HARDENED.** Story ready for `phase-story-executor`. Every AC is individually verifiable; the AC set collectively guarantees the Goals 5/6/7 commitment and ADR-0001/0006/0012 invariants; every test in the TDD plan would fail on at least one named mutation; CLAUDE.md Rule 11 (codebase convention) is honored; the design patterns surface (Protocol-as-port, Strategy, plugin-via-registry, NewType, illegal-states-unrepresentable via `@model_validator`, functional core) is explicit; the closed-`Literal`-mirroring-open-registry tension is documented as a forward seam, not silently widened.
