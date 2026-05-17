# Validation report: S6-05 — `Ownership` + `ServiceTopologyStub` + `SloStub` Layer E

**Validated:** 2026-05-17
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Story:** [`../S6-05-layer-e-probes.md`](../S6-05-layer-e-probes.md)

## Summary

S6-05's *intent* (one real Layer-E marker probe — `OwnershipProbe` reading `CODEOWNERS` — plus two deferred-stub probes — `ServiceTopologyStub` + `SloStub` — registered so Phase 9+ can extend without contract churn) is well-formed and traces cleanly to `localv2.md` §5.5 and the S6-04 deferred-stub precedent. The original draft, however, contradicted the actual frozen Phase-0 `Probe` ABC (`src/codegenie/probes/base.py:64-96`) and the kernel registry (`src/codegenie/probes/registry.py:131-238`) at **nine** load-bearing points — every one a `block`-severity contract mismatch identical in shape to the eight systemic mismatches S6-01 / S6-02 / S6-03 / S6-04 went through hardening to fix (story-authoring drift between the kernel snapshot and the ABC S2-01 actually shipped), plus one structural mismatch unique to this story (the same `confidence="unavailable"` claim S6-04's hardening had to re-route — S6-05's stubs inherit the same misframing, while `OwnershipProbe`'s absent-file case correctly uses `confidence="low"` per the CertificateProbe upstream-absent precedent).

Twenty-one in-place edits applied. **Seven new ACs** cover gaps the original draft missed (mostly mirrors of S6-04's hardening additions, plus two ownership-specific edge cases):

- **AC-NEW-1** — `_PROBE_ID: Final[ProbeId]` module constants for all three probes (dual-form identity discipline from S6-01..S6-04 hardenings; mirrors `src/codegenie/probes/layer_b/scip_index.py:114`).
- **AC-NEW-2** — registry-membership smoke for all three probes (mirrors S6-04 AC-NEW-3).
- **AC-NEW-3** — tagged-union discriminator key `discriminator="opted_in"` literal in stub-module sources (mirrors S6-04 AC-NEW-4).
- **AC-NEW-4** — no subclass-based extension path on any of the three probes (mirrors S6-04 AC-NEW-5).
- **AC-NEW-5** — `OwnershipProbe` inline-comment edge case (a real CODEOWNERS quirk the original story didn't cover; the per-token truncation discipline preserves pattern integrity vs. a naive `line.split("#", 1)[0]`).
- **AC-NEW-6** (two parts) — single canonical raw artifact for stubs (mirrors S6-04 AC-NEW-1), and `OwnershipProbe`'s pure parser extracted as a module-level free function `_parse_codeowners_lines` (functional-core / imperative-shell discipline; mirrors `dockerfile.py` + `_dockerfile_parse.py`).
- **AC-NEW-7** — `OwnershipProbe` documents the **intentional divergence** from GitHub's documented `CODEOWNERS` search order with a grep-discoverable phrase so a future contributor sees the choice was deliberate, not accidental.

**Three design-pattern hardens** were applied:

1. The Phase-2 stub slices were renamed `ServiceTopologyStubSlice` → `NotOptedInServiceTopologySlice` and `SloStubSlice` → `NotOptedInSloSlice` so the eventual Phase-9+ opted-in variants land as *new sibling models* under tagged unions (`Annotated[NotOptedInServiceTopologySlice | OptedInServiceTopologySlice, Field(discriminator="opted_in")]`) — not as backward-compatible additive fields on the existing models. This is the **Open/Closed at the file boundary** discipline S6-04 settled (`NotOptedInExternalDocsSlice` precedent) and the rest of Phase 2 follows (`Fresh` + `Stale`, `Pass` + `Fail` + `NotApplicable`).
2. The Notes-for-implementer section explicitly names the design patterns each probe deploys: **Null Object** (stubs), **Tagged union via discriminator** (`opted_in`), **Open/Closed at file boundary** (eventual `match` dispatch), **Functional core / imperative shell** (pure `_parse_codeowners_lines`).
3. The Refactor section now shows the exact `match` pattern the Phase-9 extension follows for each stub — so a Phase-9 contributor reading this story has a typed blueprint, not just a prohibition.

A **schema-naming consistency note** surfaces a conflict with S6-08: S6-08's plan names the Layer-E schema files `service_topology_stub.schema.json` / `slo_stub.schema.json` (with `_stub` suffix), but S6-05 pins probe `name` as `"service_topology"` / `"slo"` (no suffix — the probe identity is the long-term concern). The "schema filename matches probe name" convention should win; this validation report flags S6-08 for amendment, and AC-13 in S6-05 is **soft**: it asserts Pydantic-level `extra="forbid"` here, deferring the JSON-Schema round-trip to S6-08.

No `NEEDS RESEARCH` findings — every gap traced to in-repo precedent.

## Context Brief (Stage 1)

### Story snapshot

- **Goal:** Ship three files under `src/codegenie/probes/layer_e/`: `ownership.py` (real `CODEOWNERS` parser, marker-probe shape, `confidence="high"`/`"low"` per CertificateProbe precedent), `service_topology_stub.py` + `slo_stub.py` (deferred stubs, `confidence="high"` per S6-04 NotOptedIn precedent, typed slices with `opted_in: Literal[False]` discriminator key, single raw-artifact write).
- **Non-goals:** Service-catalog HTTP, mesh API, OpenAPI/gRPC parsing, production config probe (E5), email/handle redaction (writer chokepoint), `CODEOWNERS` escape sequences, JSON-Schema sub-schema round-trip (deferred to S6-08).
- **Effort:** S.
- **Depends on:** S6-04 (deferred-stub probe-shape precedent), S5-03 (Layer-C marker-probe shape, `_make_repo`/`_make_ctx` helpers, functional-core extraction discipline), S2-02 (marker-driven probe shape).

### Acceptance criteria as originally written (verbatim, numbered)

The original draft had 16 ACs. Critical issues against the kernel:

- AC-2: `probe_id` (should be `name`), `applies_to_tasks=("*",)` tuple (should be `list[str]`).
- AC-9, AC-10: `confidence="unavailable"` (NOT a permitted value).
- AC-13: nested schema path `layer_e/...schema.json` referenced but tests would fail until S6-08 lands (forward dependency).
- TDD plan: `ProbeContext.for_test(repo_root=...)` doesn't exist; `_run(ctx)` doesn't exist; `_PROBE_REGISTRY` doesn't exist; `from codegenie.ids` doesn't exist; `ProbeOutput(probe_id=..., …)` constructor wrong.

### Phase / arch constraints touched

- **Phase 0 ADR-0007** — `Probe` ABC frozen byte-for-byte against `localv2.md §4`. `confidence: Literal["high","medium","low"]`. `async def run(self, repo, ctx)`. Six-field `ProbeOutput` with no `probe_id`. `ProbeContext` is stdlib `@dataclass`.
- **02-ADR-0003** — `@register_probe(heaviness=…)` is a registry kwarg; not an ABC field.
- **02-ADR-0005** — emails/handles are not secrets per se; redactor at writer chokepoint handles them; probe captures honestly.
- **02-ADR-0007** — "ship the boundary, defer the implementation" precedent (S6-04 applied to ExternalDocsProbe; here to ServiceTopologyStub + SloStub).
- **02-ADR-0008** — no event stream; SLO/topology Phase-9 data sources are event consumers.
- **`localv2.md §5.5`** — Layer E description: "stubbed for local-dev; data unavailable markers when their data sources aren't configured".
- **CLAUDE.md "Extension by addition"** — Phase-9 widening must not require editing the Phase-2 `NotOptedIn…Slice` models.
- **CLAUDE.md "Honest confidence"** — `confidence="high"` for stubs reports the determination quality (high); `confidence="low"` for absent CODEOWNERS reports the operational weakness of the observation.

### Sibling-family lineage

- **First Layer-E story.** No prior Layer-E precedent in the codebase; the relevant precedents are Layer-D (S6-01..S6-04 for the probe shape + deferred-stub pattern) and Layer-C (S5-03 for marker-probe shape + `_make_repo`/`_make_ctx` helpers + functional-core extraction).
- **Third deferred-stub probe overall** (after S6-04 `ExternalDocsProbe` for Layer D). Rule-of-Three triggered for "shared deferred-stub base" conversation but NOT for the extract: each stub's eventual Phase-9+ divergence is different (Confluence/Notion union for external_docs; service-mesh/Backstage/OpsLevel union for topology; per-provider SLO catalogs for slo), so a shared base would erase the per-stub `Literal` invariants. Notes §7 documents the decision.
- **Functional-core precedent:** S5-03 + S6-01..S6-04 settled the pure-helper-as-module-level-free-function pattern; this story inherits trivially for the stubs (which are pure) and explicitly via AC-NEW-6 part 2 for `OwnershipProbe`.

### Prior validation framings carried forward

- **S6-04 hardening:** the canonical Phase-2 deferred-stub pattern. Every contract drift mirrored here. The `confidence="high"` + typed-slice re-routing is the largest piece carried.
- **S6-01 hardening:** "absence is the data → `confidence='high'`" precedent. Applied to the two stubs (not the ownership absent-file case, which follows CertificateProbe).
- **S5-03 hardening:** Layer-C marker-probe shape; `_make_repo`/`_make_ctx` helpers; pure-functional-core line parser extracted from imperative-shell `run`. `OwnershipProbe` mirrors this discipline directly (AC-NEW-6 part 2).
- **S5-04 hardening:** mutation-resistance via parametrized smoke; `Final[...]` discipline. Mirrored here via parametrized stub tests and `_PROBE_ID: Final[ProbeId]`.

### Phase exit criteria the story contributes to

- **High-level-impl.md §"Step 6"** — Layer E probes ship; stubs for Phase 9+ topology + SLO.
- **`localv2.md §5.5`** — Layer E E1 (`OwnershipProbe`) is the only Layer-E probe with a real local-dev data source; E2 + E4 are deferred.
- **CLAUDE.md "Extension by addition"** — `opted_in` discriminator key commitment + tagged-union sibling-model discipline operationalize the load-bearing commitment for Phase 9+.

### Open ambiguities discovered during Stage 1

- **`confidence="unavailable"` doesn't exist.** Original AC-9, AC-10 specified `confidence="unavailable"`. ABC field is `Literal["high","medium","low"]`. **Resolved at synthesis:** rewrite to `confidence="high"` (deferred-stub state is one the probe *successfully determined*; mirrors S6-04 NotOptedInExternalDocsSlice). Distinct from `OwnershipProbe`'s `confidence="low"` for absent CODEOWNERS, which correctly mirrors CertificateProbe upstream-absent.
- **All systemic kernel-contract mismatches** (eight per S6-04's hardening): `_run` → `async run(repo, ctx)`; `probe_id` → `name: str` + `_PROBE_ID` constant; `tuple` → `list` for `applies_to_*`; `from codegenie.ids` → `codegenie.types.identifiers`; `_PROBE_REGISTRY` → `default_registry._entries`; `ProbeContext.for_test` → `_make_repo`/`_make_ctx` helpers; `ProbeOutput(probe_id=..., …)` → six-field shape; full ABC field set declared verbatim.
- **Schema layout for Layer E.** S6-08 plans `layer_e/{ownership,service_topology_stub,slo_stub}.schema.json` (with `_stub` suffix on stubs); story originally has `{ownership,service_topology,slo}.schema.json` (no suffix). **Resolved at synthesis:** AC-13 softened to defer JSON-Schema test to S6-08; probe `name` pinned without `_stub` suffix; S6-08 flagged for naming amendment.
- **`OwnershipProbe` happy-path raw-artifact policy.** Original story has GREEN code with `raw_artifacts=[]` (implicit marker-probe shape) but no AC. **Resolved at synthesis:** AC-NEW-6 part 1 explicitly pins stub raw-artifact discipline (`[ctx.output_dir / "<probe>.json"]`) AND documents `OwnershipProbe`'s `raw_artifacts=[]` as the marker-probe convention (slice carries all evidence).

## Findings by critic

### Coverage critic (K)

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| K1 | block | AC-9, AC-10 specify `confidence="unavailable"` — not a permitted `ProbeOutput.confidence` value (`Literal["high","medium","low"]`, `src/codegenie/probes/base.py:68`). | Rewrite to `confidence="high"` with rationale: absence is the data; state lives in typed slice (`opted_in: Literal[False]`, `reason: Literal["phase_9_or_later"]`); confidence reports determination quality. Mirrors S6-04 hardening. |
| K2 | harden | No AC for `_PROBE_ID: Final[ProbeId]` module constants. S6-01..S6-04 settled dual-form identity convention. | New AC-NEW-1 covering all three probes. |
| K3 | harden | No AC for single raw artifact written by stubs. S6-04 lands single-raw-artifact discipline; a future contributor "optimizing" by skipping the raw-artifact write would silently break cache-key / golden-file pipelines downstream. | New AC-NEW-6 part 1: `raw_artifacts == [ctx.output_dir / "<probe>.json"]` for each stub; atomic `.tmp` → `os.replace` write. Also document `OwnershipProbe`'s `raw_artifacts=[]` policy (marker-probe convention). |
| K4 | harden | No AC asserts the probes are actually in `default_registry._entries` (membership smoke). Removing `@register_probe` decorator would silently stop the probe from running. | New AC-NEW-2 for all three probes. Mirrors S6-04 AC-NEW-3. |
| K5 | harden | No AC commits to the discriminator key choice. A future contributor could introduce `kind` and silently fragment the Phase-9 widening. | New AC-NEW-3: `discriminator="opted_in"` literal in source. Mirrors S6-04 AC-NEW-4. |
| K6 | harden | Refactor section forbids "class hierarchy" but no AC enforces it. | New AC-NEW-4: AST-walk forbids any `class X(StubProbe)` declaration. Mirrors S6-04 AC-NEW-5. |
| K7 | harden | AC-6 (malformed line) doesn't cover inline-comment lines (`*.py @user # python team`). GitHub CODEOWNERS allows trailing `#` comments. Story Notes don't mention this edge case. | New AC-NEW-5: per-token truncation at first `#`-prefixed token; mutation caught: naive `line.split("#", 1)[0]` also strips `#` from patterns. |
| K8 | harden | No AC enforces functional-core extraction of the CODEOWNERS line parser. The original Implementation outline mixes parsing with I/O inside `run`. | New AC-NEW-6 part 2: `_parse_codeowners_lines(text: str) -> tuple[...]` is a module-level free function; AST-walk asserts. Mirrors `dockerfile.py` + `_dockerfile_parse.py` precedent. |
| K9 | harden | AC-15 (determinism) doesn't include raw-artifact byte-identity for the stubs (which DO write raw artifacts per the new AC). | Extend AC-15 to assert raw-artifact byte-identity for the stubs (re-read after run #2). |
| K10 | harden | No AC documents the intentional divergence from GitHub's documented CODEOWNERS search order. Notes §4 explains but no test fires if a future contributor "fixes" the divergence. | New AC-NEW-7: docstring contains exact grep-discoverable phrase `"Phase 2 search order intentionally diverges from GitHub"`. |
| K11 | nit | AC-13 references `src/codegenie/schema/probes/layer_e/...schema.json` but those files land in S6-08. The test would fail until S6-08 ships (forward dependency a Phase-2 story can't validate). | Soften AC-13: defer JSON-Schema round-trip to S6-08; assert Pydantic-level `extra="forbid"` here. |

### Test-Quality critic (T)

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| T1 | block | All tests call `probe()._run(ctx)`. `_run` doesn't exist; ABC is `async def run(self, repo, ctx)`. Tests would fail at import. | Rewrite every test to `asyncio.run(probe.run(repo, ctx))` (precedent: `tests/unit/probes/layer_c/test_dockerfile.py:77-78`). |
| T2 | block | Tests construct `ProbeContext.for_test(repo_root=...)`. Doesn't exist; `ProbeContext` is stdlib `@dataclass`. | Introduce `_make_repo(tmp_path) + _make_ctx(tmp_path)` helpers in `tests/unit/probes/layer_e/conftest.py` (precedent: `tests/unit/probes/layer_c/test_dockerfile.py:61-74`). |
| T3 | block | `from codegenie.probes.base import ProbeContext, _PROBE_REGISTRY` — `_PROBE_REGISTRY` is not in `base.py`. | Import `default_registry` from `codegenie.probes.registry`; use `next(e for e in default_registry._entries if e.cls.name == "...")`. |
| T4 | block | Test parametrize parameter name `probe_id`; ABC field is `name`. | Rename parametrize parameter to `probe_name`; access `probe_cls.name`. |
| T5 | block | GREEN code uses `from codegenie.ids import ProbeId` — `codegenie.ids` doesn't exist. | Import from `codegenie.types.identifiers`. |
| T6 | block | GREEN code uses `ProbeOutput(probe_id=..., …)` constructor — six-field dataclass, no `probe_id`. | Rewrite to `ProbeOutput(schema_slice, raw_artifacts, confidence, duration_ms, warnings, errors)`; `duration_ms` via `time.perf_counter()`. |
| T7 | harden | `test_ownership_size_cap_enforced` over-monkey-patches `os.stat` (with custom `_ST` class) AND `os.path.getsize`. The implementation only needs `getsize`; the `os.stat` patch is dead code. | Simplify to monkeypatch `os.path.getsize` only. |
| T8 | harden | Forbidden-imports set in stub test (`{"httpx", "requests", "urllib.request", "aiohttp", "socket"}`) is missing `http.client` and `httplib`. S6-04's hardened set has all seven. | Extend to the seven-member set. |
| T9 | harden | No test for the pure parser `_parse_codeowners_lines` directly. The behavioral assertion is end-to-end via `probe.run(repo, ctx)`; a regression in the pure parser would still fire the end-to-end test, but isolating the pure-core tests makes mutation detection cleaner. | Add direct unit tests for `_parse_codeowners_lines` (happy path, comments/blanks, empty owners, inline comment, garbage). |
| T10 | harden | No test for `_parse_codeowners_lines` "never raises on garbage" property — the pure-core contract is "errors as data, never exceptions". | Add `test_parse_codeowners_lines_never_raises_on_garbage`. |
| T11 | nit | `test_ownership_two_runs_byte_identical` compares JSON via `json.dumps(...)` but should also re-validate via `OwnershipSlice.model_validate(...)` to assert the entries-tuple order. | Extend to validate slice and check `[e.pattern for e in slice_.entries]` order. |

### Consistency critic (C)

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| C1 | block | `confidence="unavailable"` contradicts `Literal["high","medium","low"]` (Phase 0 ADR-0007). | Rewrite per K1. |
| C2 | block | `_run(self, ctx)` contradicts ABC `async def run(self, repo, ctx)` (`localv2.md §4` + `base.py:94`). | Rewrite. |
| C3 | block | `probe_id` class attr contradicts ABC `name: str` field. | Rewrite to `name: str = "<probe>"` + `_PROBE_ID: Final[ProbeId]` module constant. |
| C4 | block | `tuple[str, ...]` for `applies_to_*` contradicts ABC `list[str]`. | `list[str] = ["*"]`. |
| C5 | block | `_PROBE_REGISTRY` doesn't exist. | `default_registry._entries`. |
| C6 | block | `from codegenie.ids` — module doesn't exist (recurring documentation drift). | Import from `codegenie.types.identifiers`. |
| C7 | block | `ProbeOutput(probe_id=..., …)` constructor contradicts six-field dataclass. | Rewrite. |
| C8 | block | AC-2 missing full ABC field set (`version`, `layer`, `tier`, `requires`, `declared_inputs`, `cache_strategy`). | Add full field set verbatim (canonical reference: `src/codegenie/probes/layer_b/index_health.py:298-326`). |
| C9 | block | `ProbeContext.for_test(repo_root=...)` — doesn't exist; `ProbeContext` is stdlib `@dataclass` with `cache_dir, output_dir, workspace, logger, config` + optionals. | Introduce `_make_repo`/`_make_ctx` helpers. |
| C10 | harden | S6-08 plans schema files at `layer_e/{ownership,service_topology_stub,slo_stub}.schema.json`. S6-05 probes have `name = "service_topology"`/`"slo"` (no `_stub` suffix). Schema-name-matches-probe-name convention should win. | Pin S6-05 probe names without `_stub` suffix; flag S6-08 for amendment in this report; soften S6-05 AC-13 to defer JSON-Schema test to S6-08. |
| C11 | nit | OwnershipProbe `confidence="low"` on absent file appears to contradict the S6-04 "absence is the data → high" precedent until you read the framing carefully: `OwnershipProbe` is a CertificateProbe-style upstream-absent observation; stubs are S6-04-style deferred state. Both framings coexist; the story Notes §1 should disambiguate. | Notes §1 (rewritten) explicitly contrasts the two framings and names the precedent for each. |
| C12 | nit | Layer-E schema layout uses nested `layer_e/` subdir (per S6-08), unlike S6-04's hardened "flat" path. The conventions differ between Layer D (flat in S6-04 hardening) and Layer C (subdir, confirmed by `src/codegenie/schema/probes/layer_c/`) and Layer E (subdir, per S6-08). Inconsistency. | Out of scope for this story (the Layer-D vs Layer-C inconsistency is an S6-04/S6-08 reconciliation concern, not S6-05's). Flag in this report for the next pipeline pass. |

### Design-Patterns critic (D)

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| D1 | harden | The probes deploy four established design patterns but the story doesn't name them: **Null Object** (stubs), **Tagged union via discriminator** (`opted_in`), **Open/Closed at file boundary** (eventual `match` dispatch + new sibling slice models), **Functional core / imperative shell** (pure `_parse_codeowners_lines`). Naming makes the design legible to a Phase-9 contributor. | Add Notes §8 listing all four patterns with file references. |
| D2 | harden | Stub slice names `ServiceTopologyStubSlice` / `SloStubSlice` preclude future tagged-union widening. The eventual shapes are `Annotated[NotOptedIn... | OptedIn..., Field(discriminator="opted_in")]`; Phase-2 models should be named for what they *are* (`NotOptedIn...`), so future opted-in variants are siblings. Mirrors S6-04's `NotOptedInExternalDocsSlice` rename. | Rename + add AC + update Notes. |
| D3 | harden | The Refactor section forbids subclass extension but doesn't show the alternative dispatch pattern. A Phase-9 contributor reading this story has no positive blueprint. | Show explicit `match repo.config.get("service_topology"): case None | {}: ...; case {"sources": _}: ...; case other: assert_never(other)` dispatch with module-level free functions `_emit_not_opted_in_topology` / `_emit_opted_in_topology`. Mirrors S6-04 hardening. |
| D4 | harden | `OwnershipProbe`'s line-parser logic mixes pure parsing with I/O inside `run`. Functional-core extraction is the third instance of the pattern in the codebase (S6-01, S6-03, `dockerfile.py` + `_dockerfile_parse.py`) — well past Rule of Three; the extract is mandatory, not optional. | New AC-NEW-6 part 2: `_parse_codeowners_lines(text: str)` module-level free function with AST-asserted signature. |
| D5 | info | The probes correctly avoid: primitive obsession (`Literal[False]`/`Literal["phase_9_or_later"]` not raw `bool`/`str`); anaemic types (typed slice with discriminator); speculative inheritance (forbidden by AC-NEW-4); hidden state (probes are pure or near-pure). | No change — confirmed and documented. |
| D6 | nit | Rule-of-Three for extracting a shared "deferred stub" base. Three deferred stubs now exist: S6-04 `ExternalDocsProbe`, S6-05 `ServiceTopologyStubProbe`, S6-05 `SloStubProbe`. By Rule of Three, the extract conversation is open *but the eventual divergence forbids it* — per-stub Phase-9+ widenings will introduce different reason unions and different opted-in payloads, so a shared base would erase the per-stub `Literal` invariants. Document the decision. | Notes §7 documents Rule-of-Three triggered, decision-not-to-extract, and why. |
| D7 | nit | `OwnershipProbe`'s `OwnershipEntry.pattern: str` is primitive obsession on the CODEOWNERS-pattern domain primitive, but is loop-iterated, never cross-module passed. Not worth a newtype. | No change. |
| D8 | nit | `OwnershipProbe.run` doesn't read `repo.config["ownership"]` (correctly), but unlike S6-04 (which has an AC-5-negative-side test against `.config.get("external_docs")` slippery slope), this story has no equivalent test for stubs. A future contributor could pre-wire `repo.config.get("service_topology")` as a "harmless check that does nothing yet" — slippery slope to a fetcher. | Consider for a future hardening if the slippery-slope failure emerges; not adding now to keep this story tight. |

## Research findings (Stage 3)

**None.** No `NEEDS RESEARCH` findings. Every gap traced to in-repo precedent:

- `src/codegenie/probes/base.py:64-96` — frozen ABC contract.
- `src/codegenie/probes/registry.py:131-238` — `default_registry._entries` API; `register_probe` decorator.
- `src/codegenie/probes/layer_b/index_health.py:298-326` — canonical full-field ABC declaration.
- `src/codegenie/probes/layer_b/scip_index.py:114` — `_PROBE_ID: Final[ProbeId]` dual-form discipline.
- `src/codegenie/probes/layer_c/certificate.py:67-81` — upstream-absent precedent (informs `OwnershipProbe` absent-file `confidence="low"`).
- `src/codegenie/probes/layer_c/dockerfile.py` + `_dockerfile_parse.py` — functional-core extraction precedent.
- `tests/unit/probes/layer_c/test_dockerfile.py:61-78` — `_make_repo`/`_make_ctx` helper pattern.
- `src/codegenie/types/identifiers.py:29` — `ProbeId = NewType("ProbeId", str)` correct import path.
- `docs/phases/02-context-gather-layers-b-g/stories/_validation/S6-04-external-docs-opt-in.md` — the deferred-stub hardening lineage this story mechanically repeats.

## Edits applied (Stage 4)

Twenty-one in-place edits to `S6-05-layer-e-probes.md`:

| # | Section | Change |
|---|---|---|
| 1 | Header | `Status: Ready` → `Status: Hardened (ready for executor)`; expand `Depends on` to name inherited probe-shape conventions (S6-04, S5-03, S2-02); add Phase 0 ADR-0007 + 02-ADR-0003 + 02-ADR-0007 to ADRs honored. |
| 2 | Header | Inserted `## Validation notes` block documenting the audit. |
| 3 | Context | Re-routed stub framing through `confidence="high"` + typed slice; added explicit Phase-2-vs-GitHub search order divergence note; expanded with "Design-pattern lineage" subsection naming Null Object, Tagged union via discriminator, Open/Closed at file boundary, Functional core / imperative shell. |
| 4 | References | Added 02-ADR-0007 + 02-ADR-0003 references; added S6-04 + S5-03 probe-shape precedent references; expanded existing-kernel section with eight authoritative contract surfaces (`base.py`, `registry.py`, `index_health.py`, `scip_index.py`, `certificate.py`, `dockerfile.py`, `test_dockerfile.py`, `identifiers.py`). |
| 5 | Goal | Rewrote with full ABC field set; explicit `async def run(repo, ctx)` signature; explicit "no `repo.config` reads, no `ctx.config` reads" discipline for stubs; single raw artifact write for stubs; `confidence="high"` for stubs / `confidence="low"` for ownership absent (with rationale). |
| 6 | AC-1 | Specified `__all__` declarations per file with alphabetical sorting; renamed slices per D2. |
| 7 | AC-2 | Pinned `extra="forbid"` on all four slice models with mutation-resistance rationale. |
| 8 | AC-3 | Pinned `Literal[False]` + `Literal["phase_9_or_later"]` for both stub slices with discriminator-key rationale. |
| 9 | AC-4 | Rewrote with full Phase-0 ABC field set verbatim; corrected `tuple` → `list[str]` for `applies_to_*`; corrected `probe_id` → `name: str`; corrected `from codegenie.ids` → `codegenie.types.identifiers`. |
| 10 | AC-NEW-1 | New AC: `_PROBE_ID: Final[ProbeId]` constants for all three probes. |
| 11 | AC-5 | Rewrote with async `run(repo, ctx)`; six-field `ProbeOutput`; `confidence="high"` for happy path; `raw_artifacts=[]` (marker-probe convention). |
| 12 | AC-6 | Rewrote absent-file case: `confidence="low"`, slice `source_path=None, entries=()`, `errors=["codeowners_absent"]`; named CertificateProbe upstream-absent precedent. |
| 13 | AC-7, AC-8 | Renumbered original AC-6 → AC-7 (malformed), AC-7 → AC-8 (comments/blanks); preserved original test rationales. |
| 14 | AC-NEW-5 | New AC: inline-comment edge case with per-token truncation. |
| 15 | AC-9 | Renumbered original AC-8 → AC-9 (three-location search order). |
| 16 | AC-NEW-7 | New AC: intentional GitHub-divergence documented with exact grep-discoverable docstring phrase. |
| 17 | AC-10, AC-11 | Rewrote both stub ACs: `confidence="high"` with typed slice; six-field `ProbeOutput`; single raw artifact at `ctx.output_dir / "<probe>.json"`; explicit "no `repo.config` reads / no `ctx.config` reads" discipline. |
| 18 | AC-NEW-6 (parts 1+2) | New AC: stubs write single canonical raw artifact atomically; OwnershipProbe's pure parser `_parse_codeowners_lines` extracted as module-level free function with AST-asserted signature. |
| 19 | AC-12, AC-13, AC-NEW-3, AC-NEW-4 | Renumbered + added AC-NEW-3 (discriminator-key grep) and AC-NEW-4 (no subclass extension). Tightened AC-12 forbidden-imports set to seven members (matches S6-04 hardening). |
| 20 | AC-14, AC-NEW-2, AC-15, AC-16, AC-17, AC-18 | Renumbered remaining ACs; added AC-NEW-2 (registry-membership smoke for all three probes); softened AC-13 (now AC-16) to defer JSON-Schema test to S6-08; added AC-18 (deferral grep-discoverability via `phase_9_or_later`). |
| 21 | Implementation outline / TDD plan / Refactor / Notes / Files to touch | Wholesale rewrite to match the new contract: pure `_parse_codeowners_lines` extracted; `_make_repo`/`_make_ctx` helpers in `conftest.py`; `asyncio.run(probe.run(repo, ctx))`; full GREEN modules with the six-field `ProbeOutput`, atomic writes for stubs, `_PROBE_ID` constants, full ABC field declarations; Refactor section now shows the exact `match` dispatch for the Phase-9 extension; Notes-for-implementer §1 disambiguates the two confidence framings (ownership absent vs stub not-opted-in); Notes §8 names the four design patterns; Notes §9 pins the `async run(repo, ctx)` signature; Files-to-touch updated with `conftest.py` and two test files. |

No lock-step edits required to `docs/phases/02-context-gather-layers-b-g/stories/README.md` (manifest line 195 currently describes "absent-file → `confidence='low'`" for ownership — still correct; no mention of `confidence="unavailable"` for the stubs in that row, so no propagation needed). The S6-08 schema-naming inconsistency (`_stub` suffix on Layer-E schema filenames) is flagged here for an S6-08 validator pass; not edited from this story.

## Verdict

**HARDENED.**

The story's goal is well-formed and traces to the architecture. The original draft had nine `block`-severity contract mismatches against the actual kernel — eight systemic to the Phase-2 story-authoring lineage (identical in shape to the S6-04 hardening) plus one unique-to-this-story `confidence="unavailable"` claim for the stubs (S6-04 already resolved the same issue for `ExternalDocsProbe`). All nine are now resolved in-place. Seven new ACs strengthen the AC set with mutation-resistance trip-wires (raw-artifact discipline for stubs, `_PROBE_ID` constants, registry-membership smoke, discriminator-key invariant, no-subclass extension, inline-comment edge case, GitHub-divergence documentation). The design-pattern hardens (rename stub slices to `NotOptedIn...`; name Null Object / Tagged union / Open/Closed / Functional core; extract pure `_parse_codeowners_lines`; show the explicit `match` dispatch the Phase-9 extension follows) make the story legible to a Phase-9 contributor.

Ready for `phase-story-executor`.
