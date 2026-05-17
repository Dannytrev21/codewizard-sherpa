# Story S6-05 — `Ownership` + `ServiceTopologyStub` + `SloStub` Layer E

**Step:** Step 6 — Ship Layer D + E + G probes (skills, conventions, ADRs, ownership, scanners)
**Status:** Hardened (ready for executor)
**Effort:** S
**Depends on:** S6-04 (Layer-D deferred-stub probe-shape — `Null Object` + `Tagged union via discriminator` + `Open/Closed at file boundary`; `_PROBE_ID: Final[ProbeId]` constant alongside `name: str` ABC attr; `async def run(repo, ctx)` signature; six-field `ProbeOutput` with `duration_ms` via `time.perf_counter()`; `confidence="high"` for "absence is the data" deferred state; `discriminator="opted_in"` literal in source as grep-trip-wire); S5-03 (Layer-C marker-probe shape established — `_make_repo`/`_make_ctx` test helpers; pure-helper functional-core extracted from imperative-shell `run`); S2-02 (`ConventionsCatalogLoader` pattern-types — Layer-E `OwnershipProbe` re-uses the marker-driven probe discipline).
**ADRs honored:** Phase 0 ADR-0007 (`Probe` ABC frozen byte-for-byte against `localv2.md §4` — `name: str`, `async def run(self, repo, ctx)`, `ProbeOutput` six-field shape, `confidence: Literal["high","medium","low"]`), 02-ADR-0003 (`@register_probe(heaviness=…)` is a registry kwarg — NOT a `Probe` ABC field), 02-ADR-0005 (no plaintext persistence — emails / Slack handles in `CODEOWNERS` and `service.yaml` flow through the writer redactor; the probe captures evidence honestly), 02-ADR-0007 (no plugin loader / no Confluence / Notion / service-catalog HTTP clients — the same "ship the boundary, defer the implementation" discipline S6-04 applied to `ExternalDocsProbe`), 02-ADR-0008 (no event stream in Phase 2 — `ServiceTopologyStub`'s and `SloStub`'s real data sources are Phase-9-or-later event consumers)
**Phase-2 deferred decision honored:** [`localv2.md` §5.5](../../../localv2.md) — "These probes are mostly stubbed for local-dev. They emit 'data unavailable' markers when their data sources aren't configured." Phase 2 ships `OwnershipProbe` for real (it's a simple `CODEOWNERS` parser) and ships `ServiceTopologyStub` + `SloStub` as deferred stubs (mirrors S6-04 `ExternalDocsProbe` discipline; semantics re-routed through `confidence="high"` per the kernel `ProbeOutput.confidence: Literal["high","medium","low"]`).

## Validation notes

**Hardened 2026-05-17 via `phase-story-validator`** (see [`_validation/S6-05-layer-e-probes.md`](_validation/S6-05-layer-e-probes.md) for the full audit log). Twenty-one in-place edits resolved **nine `block`-severity contract mismatches** identical in shape to the S6-04 hardening — every one a drift between this story's draft and the kernel actually shipped (`src/codegenie/probes/base.py:52-96`, `src/codegenie/probes/registry.py:131-238`, `src/codegenie/types/identifiers.py:29`). The biggest structural fix re-routes the stubs' confidence semantics: the original AC-9 / AC-10 built every stub-test on `confidence="unavailable"`, a value that **does not exist** in the frozen `ProbeOutput.confidence: Literal["high","medium","low"]` ABC field (Phase 0 ADR-0007, `src/codegenie/probes/base.py:68`). The harden re-routes the semantics through S6-04's "absence is the data → `confidence='high'`" precedent (the deferred-stub state is one the probe *successfully determined* — not a failure-to-determine), with typed `opted_in: Literal[False]` + `reason: Literal["phase_9_or_later"]` slice fields carrying the state and the confidence reporting the *quality of the determination*. **`OwnershipProbe.confidence` for absent CODEOWNERS stays `"low"`** — that case is a CertificateProbe-style upstream-absent observation (the file *might* exist but doesn't; the answer "no CODEOWNERS" is operationally a low-information signal for the Planner), not an opted-out deferral.

Eight further block-severity contract fixes mirror S6-04 / S6-01 / S6-02 / S6-03 hardenings: `_run(self, ctx)` → `async def run(self, repo, ctx)`; `probe_id` class attrs → `name: str = "ownership"` (etc.) ABC attrs + module-level `_PROBE_ID: Final[ProbeId] = ProbeId("ownership")` (etc.) constants; full frozen Phase-0 ABC field set declared verbatim (`version`, `layer`, `tier`, `requires`, `declared_inputs`, `timeout_seconds`, `cache_strategy`); `tuple[str, ...]` → `list[str]` for `applies_to_*` (ABC requires `list`); `from codegenie.ids` → `from codegenie.types.identifiers` (`codegenie.ids` doesn't exist); `_PROBE_REGISTRY["..."]` → `next(e for e in default_registry._entries if e.cls.name == "...")`; `ProbeContext.for_test(repo_root=...)` (doesn't exist) → `_make_repo(tmp_path) + _make_ctx(tmp_path)` helpers (precedent: `tests/unit/probes/layer_c/test_dockerfile.py:61-74`); `ProbeOutput(probe_id=..., …)` → six-field shape (`schema_slice, raw_artifacts, confidence, duration_ms, warnings, errors`) with `duration_ms` via `time.perf_counter()`.

**Seven new ACs** strengthen the AC set with mutation-resistance trip-wires and extension-by-addition discipline:

- **AC-NEW-1** — `_PROBE_ID: Final[ProbeId]` module constants for all three probes (dual-form identity discipline from S6-01/02/03/04 hardenings; mirrors `src/codegenie/probes/layer_b/scip_index.py:114`).
- **AC-NEW-2** — registry-membership smoke for all three probes (a future contributor removing the `@register_probe` decorator would silently stop the probe from running in every gather; this test is the trip-wire — mirrors S6-04 AC-NEW-3).
- **AC-NEW-3** — tagged-union discriminator key `discriminator="opted_in"` literal in stub-module sources (a future contributor changing the discriminator key from `opted_in` to e.g. `kind` would silently fragment the Phase-9 widening — mirrors S6-04 AC-NEW-4).
- **AC-NEW-4** — no subclass-based extension path on any of the three probes (forbids `class OptedInServiceTopologyProbe(ServiceTopologyStubProbe)` and friends; the eventual opted-in branch must be `match`-dispatched conditional logic, not inheritance — mirrors S6-04 AC-NEW-5).
- **AC-NEW-5** — `OwnershipProbe` inline-comment edge case (`*.py @user # owners are the python team` parses with the inline-`#` and tail tokens stripped; otherwise a contributor "supporting" inline comments by stripping at the first `#` would also strip `#` characters legitimately appearing in patterns).
- **AC-NEW-6** — `OwnershipProbe` line-parser extracted as a pure module-level free function `_parse_codeowners_lines(text: str) -> tuple[tuple[OwnershipEntry, ...], tuple[str, ...]]` (functional-core / imperative-shell discipline — `run` is the only impure code; the parser is testable without an `fd` or a `RepoSnapshot`).
- **AC-NEW-7** — `OwnershipProbe` documents the **intentional divergence** from GitHub's documented `CODEOWNERS` search order (`CODEOWNERS` > `.github/CODEOWNERS` > `docs/CODEOWNERS` in this implementation; GitHub uses `.github/CODEOWNERS` > `CODEOWNERS` > `docs/CODEOWNERS`) in the module docstring with the exact grep-discoverable phrase `"Phase 2 search order intentionally diverges from GitHub"` so a future contributor sees the choice was deliberate, not accidental.

**Three design-pattern hardens** were applied:

1. The Phase-2 stub slices were renamed `ServiceTopologyStubSlice` → `NotOptedInServiceTopologySlice` and `SloStubSlice` → `NotOptedInSloSlice` so the eventual Phase-9+ opted-in variants land as *new sibling models* under a tagged union (`Annotated[NotOptedInServiceTopologySlice | OptedInServiceTopologySlice, Field(discriminator="opted_in")]`) — not as backward-compatible additive fields on the existing models. This is the **Open/Closed at the file boundary** discipline S6-04 settled (`NotOptedInExternalDocsSlice` precedent) and the rest of Phase 2 follows (`Fresh` + `Stale`, `Pass` + `Fail` + `NotApplicable`).
2. The Notes-for-implementer section explicitly names the design patterns each probe deploys: **Null Object** (stubs satisfy the ABC so consumers don't special-case), **Tagged union via discriminator** (`opted_in` is the key choice; Phase 2 makes the discriminator-key commitment now), **Open/Closed at file boundary** (future opted-in branches land via `match` dispatch + new sibling slice models, never via subclass), and **Functional core / imperative shell** (the CODEOWNERS line-parser is pure; `OwnershipProbe.run` is the imperative shell).
3. The Refactor section now shows the exact `match` pattern the Phase-9 extension follows for each stub (`match repo.config.get("service_topology"): case None | {}: …; case {"sources": _}: …; case other: assert_never(other)`) so a Phase-9 contributor reading this story has a typed blueprint, not just a prohibition.

**Schema-naming consistency note (deferred to S6-08):** S6-05 ships Pydantic slice models; the JSON-Schema sub-schema files land in S6-08 under `src/codegenie/schema/probes/layer_e/` (per S6-08 AC-9). S6-08 currently names them `ownership.schema.json`, `service_topology_stub.schema.json`, `slo_stub.schema.json` — the `_stub` suffix on the two stubs is inconsistent with the probe `name` (`"service_topology"`, `"slo"` — no suffix). The convention "schema filename matches probe name" should win; this story pins probe names and slice models without the `_stub` suffix and flags the S6-08 naming for amendment in [`_validation/S6-05-layer-e-probes.md`](_validation/S6-05-layer-e-probes.md). AC-13 in this story is **soft** — it asserts the Pydantic slice contracts (`extra="forbid"`, `Literal` enforcement) here; the JSON-Schema round-trip is an S6-08 concern.

No `NEEDS RESEARCH` findings — every gap traced to in-repo precedent: `src/codegenie/probes/base.py:64-96` for the frozen ABC contract; `src/codegenie/probes/layer_b/index_health.py:298-326` for the canonical full-field ABC declaration; `src/codegenie/probes/layer_b/scip_index.py:114` for the `_PROBE_ID: Final[ProbeId]` dual-form discipline; `src/codegenie/probes/layer_c/certificate.py` and `src/codegenie/probes/layer_c/dockerfile.py` for the marker-probe shape `OwnershipProbe` mirrors; `tests/unit/probes/layer_c/test_dockerfile.py:61-78` for the `_make_repo`/`_make_ctx` helper pattern; S6-04 validation report for the deferred-stub lineage.

## Context

Layer E (Cross-repo / Operational) is mostly forward-looking — most of its data sources are production service catalogs, service meshes, SLO definitions, on-call schedules. None of that is meaningfully available in the local POC. **One** probe in Layer E has a real local-dev consumer today: `OwnershipProbe`, which reads `CODEOWNERS`. The other two — service topology and SLOs — exist as registered stubs so Phase 9+ can extend without contract churn.

`CODEOWNERS` is a stable, line-oriented format (GitHub / GitLab convention): one line per pattern, `pattern @owner1 @team2`. The probe parses the file (if present), emits a `tuple[OwnershipEntry, ...]` keyed by pattern, and notes absent / malformed cases without raising. The repo-root file is the canonical location; `.github/CODEOWNERS`, `docs/CODEOWNERS`, `CODEOWNERS` are the three conventional paths (GitHub's documented search order). **Phase 2's `OwnershipProbe` intentionally diverges from GitHub's order** — it searches `CODEOWNERS` > `.github/CODEOWNERS` > `docs/CODEOWNERS` because the repo-root file is the most visible to operators; an operator who wants `.github/CODEOWNERS` to win simply deletes the root file. Notes for the implementer §4 documents this with the exact grep-discoverable phrase the docstring must carry.

`ServiceTopologyStub` and `SloStub` follow the **S6-04 `ExternalDocsProbe` discipline**: register, run, emit `confidence="high"` (the probe successfully determined the feature is not opted in / not configured — absence is the data) with a typed slice carrying the state (`opted_in: Literal[False]`, `reason: Literal["phase_9_or_later"]`). The discriminator key `opted_in` IS the schema commitment Phase 2 makes; the eventual Phase-9+ opted-in variants land as new sibling models under `Annotated[NotOptedInServiceTopologySlice | OptedInServiceTopologySlice, Field(discriminator="opted_in")]`. The slice schemas are deliberately minimal — Phase 9 extends with an ADR-amend rather than a backward-incompatible break.

**Design-pattern lineage the implementer inherits (and must not break):**

1. **Null Object pattern** (stubs) — non-functional implementations that satisfy the `Probe` ABC so the coordinator, the `confidence` section renderer, and the Planner consume `ServiceTopologyStubProbe` / `SloStubProbe` exactly as they consume any other Layer-E probe — no null-checks, no `if probe.name in {"service_topology", "slo"}: skip`, no special-casing.
2. **Tagged union via discriminator** (stubs) — `opted_in` is *the* discriminator key. The Phase 2 closed shape is `Literal[False]`; the eventual Phase-9+ tagged union is `Annotated[NotOptedInServiceTopologySlice | OptedInServiceTopologySlice, Field(discriminator="opted_in")]`. Picking the discriminator key in Phase 2 is the **only** schema commitment Phase 2 makes for the stubs; everything else is deferred.
3. **Open/Closed at the file boundary** (stubs) — when the opted-in branches land (Phase 9+), the dispatch is `match repo.config.get("service_topology"): case None | {}: _emit_not_opted_in_topology(ctx); case {"sources": _}: _emit_opted_in_topology(repo, ctx); case other: assert_never(other)` with an exhaustive `match` + `assert_never` on the discriminator. **Not** a subclass; **not** an `if`/`else` ladder; **not** edits to the `NotOptedInServiceTopologySlice` model.
4. **Functional core / imperative shell** (ownership) — the CODEOWNERS line-parser `_parse_codeowners_lines(text) -> tuple[tuple[OwnershipEntry, ...], tuple[str, ...]]` is a pure module-level free function: bytes-in, parsed-tuples-out, no `fd`, no `RepoSnapshot`, no `Path`. `OwnershipProbe.run` is the only impure code (filesystem search + size check + atomic write of the raw artifact). This is the precedent S6-01/02/03/04 settled and Layer-C marker probes (`dockerfile.py`, `entrypoint.py`, `shell_usage.py`, `certificate.py`) already follow.

Phase 0's secret redactor handles email leakage at the writer chokepoint. The Phase 2 commitment is that the *probe* doesn't pre-filter — it captures evidence honestly, and the writer chokepoint redacts. (`CODEOWNERS` emails aren't AWS keys, but the same chokepoint discipline applies: the probe is honest about what's in the file; the redactor decides what reaches disk.)

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md` §"Anti-patterns avoided"](../phase-arch-design.md) — "Schema before consumer" — the stubs ship a minimal schema with one consumer (the unit test); the real opted-in schema lands with Phase 9.
  - [`../phase-arch-design.md` §"Edge cases"](../phase-arch-design.md) — typed-reason discriminated unions across every state machine; `OwnershipProbe`'s "no file present" maps to a typed `Result`-shaped slice, not an exception.
- **Phase ADRs:**
  - [`../ADRs/0005-secret-findings-no-plaintext-persistence.md`](../ADRs/0005-secret-findings-no-plaintext-persistence.md) — emails are not secrets per se, but the redactor handles handles/emails at the writer chokepoint.
  - [`../ADRs/0007-no-plugin-loader-in-phase-2.md`](../ADRs/0007-no-plugin-loader-in-phase-2.md) — the canonical "ship the boundary, defer the implementation" precedent S6-04 applied to `ExternalDocsProbe`; same discipline applied here to `ServiceTopologyStub` + `SloStub`.
  - [`../ADRs/0008-no-event-stream-in-phase-2.md`](../ADRs/0008-no-event-stream-in-phase-2.md) — `SloStub`'s real data source (production SLO catalog) is a Phase-9-or-later event consumer.
  - [`../ADRs/0003-coordinator-heaviness-sort-annotation.md`](../ADRs/0003-coordinator-heaviness-sort-annotation.md) — `heaviness` is a `@register_probe(heaviness=...)` kwarg, NOT a `Probe` ABC field; registry membership verified via `default_registry._entries`.
- **Source design:**
  - [`../High-level-impl.md` §"Step 6"](../High-level-impl.md) — marker-driven; stubs for Phase 9+.
  - [`../../localv2.md` §5.5](../../../localv2.md) — Layer E description; stubs by default.
- **Probe-shape precedents (post-hardening):**
  - [`./S6-04-external-docs-opt-in.md`](./S6-04-external-docs-opt-in.md) (HARDENED) — the canonical Phase-2 deferred-stub probe pattern: `confidence="high"` with typed slice carrying state; `opted_in: Literal[False]` discriminator key; Open/Closed at file boundary; no subclass extension; `discriminator="opted_in"` literal in source.
  - [`./S5-03-layer-c-marker-probes.md`](./S5-03-layer-c-marker-probes.md) (HARDENED) — the canonical Layer-C marker-probe pattern: `_make_repo`/`_make_ctx` helpers; pure functional-core parsers extracted from `run`; module-level `_PROBE_ID: Final[ProbeId]` constant.
- **Existing kernel (the authoritative contract for this probe):**
  - `src/codegenie/probes/base.py` (Phase 0) — `Probe` ABC frozen byte-for-byte against `localv2.md §4`. `name: str` (NOT `probe_id`); `layer`, `tier`; `applies_to_tasks: list[str]` / `applies_to_languages: list[str]` (NOT `tuple`); `requires: list[str]`, `declared_inputs: list[str]`, `timeout_seconds: int`, `cache_strategy: Literal["content","none"]`. `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` — `RepoSnapshot` is the FIRST arg (NOT a `ctx` field). **`ProbeOutput.confidence: Literal["high","medium","low"]`** — `"unavailable"` is NOT a permitted value. `ProbeOutput(schema_slice, raw_artifacts, confidence, duration_ms, warnings, errors)` — six fields, no `probe_id`. `ProbeContext` is a stdlib `@dataclass` with `cache_dir, output_dir, workspace, logger, config` plus three optionals; NO `repo_root`, NO `for_test` classmethod.
  - `src/codegenie/probes/registry.py:238` — `default_registry: Registry`. The "look up heaviness" pattern: `next(e for e in default_registry._entries if e.cls.name == "ownership").heaviness == "light"`. NO `_PROBE_REGISTRY` dict.
  - `src/codegenie/probes/layer_b/scip_index.py:114` (precedent) — `_PROBE_ID: Final[ProbeId] = ProbeId("scip_index")` module-level constant alongside `name: str = "scip_index"`. Dual-form probe identity (str ABC attr + typed Final constant).
  - `src/codegenie/probes/layer_b/index_health.py:298-326` — canonical full-field ABC declaration including `version`, `layer`, `tier`, `requires`, `timeout_seconds`, `cache_strategy`, `declared_inputs`.
  - `src/codegenie/probes/layer_c/certificate.py` — Layer-C marker probe; the canonical full ABC field declaration mirror for marker-style probes.
  - `src/codegenie/probes/layer_c/dockerfile.py` (with `_dockerfile_parse.py` sibling) — functional-core extraction precedent; line-by-line parser extracted as a pure free function.
  - `tests/unit/probes/layer_c/test_dockerfile.py:61-78` — canonical `_make_repo` + `_make_ctx` helper pattern for Layer-C/D/E tests.
  - `src/codegenie/types/identifiers.py:29` — `ProbeId = NewType("ProbeId", str)`. *NOT `codegenie.ids` — that module does not exist.*

## Goal

Ship three files under `src/codegenie/probes/layer_e/`:

1. **`ownership.py`** — real `CODEOWNERS` parser. `@register_probe(heaviness="light")`. Pure line-parser extracted as `_parse_codeowners_lines` (functional-core / imperative-shell). Parses any of the three GitHub-convention locations (Phase 2 order: `CODEOWNERS` > `.github/CODEOWNERS` > `docs/CODEOWNERS`); emits a typed `OwnershipSlice`; `confidence="high"` for found-file happy path, `confidence="low"` for absent file (Planner-actionable observation — mirrors `CertificateProbe` upstream-absent pattern).
2. **`service_topology_stub.py`** — deferred stub. Mirrors S6-04 `external_docs.py` precedent: `confidence="high"`, typed `NotOptedInServiceTopologySlice(opted_in: Literal[False], reason: Literal["phase_9_or_later"])`, no I/O beyond a single atomic raw-artifact write. `opted_in` is the eventual tagged-union discriminator key.
3. **`slo_stub.py`** — deferred stub. Same shape as `service_topology_stub.py`: `confidence="high"`, typed `NotOptedInSloSlice(opted_in: Literal[False], reason: Literal["phase_9_or_later"])`, no I/O beyond a single atomic raw-artifact write.

The module docstrings explicitly name the deferral (stubs) and the intentional GitHub-search-order divergence (ownership) as grep-discoverable trip-wires.

## Acceptance criteria

**Numbered for traceability to the TDD plan.**

### Module layout & types

- [ ] **AC-1.** Three new files exist under `src/codegenie/probes/layer_e/` plus `__init__.py`. Each file's `__all__` declares exactly the slice model(s) + probe class (alphabetically sorted). Specifically:
  - `ownership.py` → `__all__ = ["OwnershipEntry", "OwnershipProbe", "OwnershipSlice"]`
  - `service_topology_stub.py` → `__all__ = ["NotOptedInServiceTopologySlice", "ServiceTopologyStubProbe"]`
  - `slo_stub.py` → `__all__ = ["NotOptedInSloSlice", "SloStubProbe"]`

- [ ] **AC-2.** **Each Pydantic slice model has `model_config = ConfigDict(frozen=True, extra="forbid")`.** `OwnershipEntry`, `OwnershipSlice`, `NotOptedInServiceTopologySlice`, and `NotOptedInSloSlice` — all four models. Mutation caught: a future contributor relaxing `extra="forbid"` to `extra="allow"` would silently admit unknown fields, breaking the discriminator-key invariants in AC-9 / AC-10.

- [ ] **AC-3.** **Stub slice types are tagged-union-ready.**
  - `NotOptedInServiceTopologySlice` has exactly `opted_in: Literal[False]` and `reason: Literal["phase_9_or_later"]`. The `Literal[False]` is the discriminator value; relaxing to `bool` would silently admit `opted_in=True` slices before the Phase-9 opted-in branch exists.
  - `NotOptedInSloSlice` has the same two fields with identical types and identical `Literal` values.
  - The eventual tagged unions are `Annotated[NotOptedInServiceTopologySlice | OptedInServiceTopologySlice, Field(discriminator="opted_in")]` and `Annotated[NotOptedInSloSlice | OptedInSloSlice, Field(discriminator="opted_in")]`; Phase 2 ships only the not-opted-in variants.

### Probe registration & ABC compliance

- [ ] **AC-4.** All three probes are decorated `@register_probe(heaviness="light")` (kwarg form — 02-ADR-0003); class attributes declare the **full frozen Phase-0 `Probe` ABC field set verbatim**:

  ```python
  name: str = "ownership"            # or "service_topology" or "slo"
  version: str = "0.1.0"
  layer = "E"
  tier = "base"
  applies_to_tasks: list[str] = ["*"]      # list[str], NOT tuple[str, ...]
  applies_to_languages: list[str] = ["*"]
  requires: list[str] = []
  declared_inputs: list[str] = [...]        # per-probe — see Implementation outline
  timeout_seconds: int = 5
  cache_strategy: Literal["content"] = "content"
  ```

  Probe `name` values are exactly `"ownership"`, `"service_topology"`, `"slo"` (no `_stub` suffix on the stub probes — the probe identity is the long-term concern; the `_stub` suffix appears only on the Phase-2 implementation class names `ServiceTopologyStubProbe` / `SloStubProbe`).

- [ ] **AC-NEW-1.** **`_PROBE_ID: Final[ProbeId]` constants exist.** Each module declares a module-level `_PROBE_ID: Final[ProbeId] = ProbeId("<probe-name>")` constant alongside the class's `name: str` ABC attr. The dual-form discipline (str ABC attr + typed `Final[ProbeId]` constant) mirrors `scip_index.py:114` and S6-01/02/03/04 hardenings. The `ProbeId` newtype is imported from `codegenie.types.identifiers` — **NOT** `codegenie.ids` (which does not exist).

- [ ] **AC-5.** **`OwnershipProbe` — happy path.** `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`. Reads `CODEOWNERS` from the first present of: `<repo>/CODEOWNERS`, `<repo>/.github/CODEOWNERS`, `<repo>/docs/CODEOWNERS`. Emits `OwnershipSlice(source_path: str, entries: tuple[OwnershipEntry, ...])` where `OwnershipEntry = (pattern: str, owners: tuple[str, ...], line_number: int)`. Six-field `ProbeOutput` with `confidence="high"`, `duration_ms=int((time.perf_counter() - t0) * 1000)`, `warnings=[]`, `errors=[]` (errors empty on the pure happy path).

- [ ] **AC-6.** **`OwnershipProbe` — file absent.** `async def run` returns `confidence="low"` (NOT `"unavailable"` — that value does not exist in the kernel `ProbeOutput.confidence: Literal["high","medium","low"]` per Phase 0 ADR-0007 `src/codegenie/probes/base.py:68`; NOT `"high"` — absent CODEOWNERS is a Planner-actionable low-information observation, not a "we determined nothing is opted in" stub state). Slice carries `source_path=None, entries=()`. `errors=["codeowners_absent"]`. Mirrors the `CertificateProbe` upstream-absent precedent (`src/codegenie/probes/layer_c/certificate.py:67-81`).

- [ ] **AC-7.** **`OwnershipProbe` — malformed line.** A line like `*.py @valid-user` parses to one entry; a line like `*.py` (no owners) parses to `OwnershipEntry(pattern="*.py", owners=(), line_number=N)` and adds `"empty_owners_at_line_N"` to `errors`. Mutation caught: any "silently drop empty-owner lines" — operators need to know about misconfigured patterns.

- [ ] **AC-8.** **`OwnershipProbe` — comment lines + blank lines.** Lines starting with `#` (after `.lstrip()`) and lines that strip to empty are skipped — they do NOT emit entries. Line numbers continue to increment over them (per Notes §3 — operators expect `vim +N`-compatible line numbers). Mutation caught: any parser that emits comments/blanks as entries with empty owners (would conflate with AC-7's empty-owners case).

- [ ] **AC-NEW-5.** **`OwnershipProbe` — inline-comment edge case.** A line like `*.py @user # owners are the python team` parses as `OwnershipEntry(pattern="*.py", owners=("@user",), line_number=N)` — the inline `#…` and all subsequent tokens on the line are dropped. The dropping is performed by the pure parser: split on whitespace; if any token starts with `#`, truncate the token list at that token (the `#` token and everything after it is comment-text). Mutation caught: a future contributor "supporting" inline comments by a naive `line.split("#", 1)[0]` would also strip `#` characters legitimately appearing in patterns (e.g., a hypothetical `*#test` pattern); the per-token truncation discipline preserves pattern integrity.

- [ ] **AC-9.** **`OwnershipProbe` — three-location search order.** When multiple `CODEOWNERS` files exist (which is operator misconfiguration but allowed), only the first found in Phase-2 order (`CODEOWNERS` > `.github/CODEOWNERS` > `docs/CODEOWNERS`) is parsed; the others are listed in `errors=["additional_codeowners_present_at:<path>", ...]`. Mutation caught: any merge-the-files behavior; any precedence change.

- [ ] **AC-NEW-7.** **`OwnershipProbe` — intentional GitHub-divergence documented.** The module docstring contains the exact grep-discoverable phrase `"Phase 2 search order intentionally diverges from GitHub"`. An architectural test asserts this. Mutation caught: a future contributor "fixing" the divergence to match GitHub's order without an ADR-amend would silently change operator-observable behavior; the test fires on the docstring change first.

- [ ] **AC-10.** **`ServiceTopologyStub` — always not-opted-in.** `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` returns the six-field `ProbeOutput`:
  ```python
  ProbeOutput(
      schema_slice=NotOptedInServiceTopologySlice(
          opted_in=False, reason="phase_9_or_later"
      ).model_dump(mode="json"),
      raw_artifacts=[ctx.output_dir / "service_topology.json"],
      confidence="high",            # absence is the data; mirrors S6-04 NotOptedIn precedent
      duration_ms=int((time.perf_counter() - t0) * 1000),
      warnings=[],
      errors=[],
  )
  ```
  **`confidence="high"`** (not `"low"`, not `"unavailable"` — the latter is not a permitted `ProbeOutput.confidence` value): the probe successfully determined the feature is not opted in; the state lives in the slice, not in the confidence (mirrors S6-04 `NotOptedInExternalDocsSlice` hardening). **No `repo.config` reads. No `ctx.config` reads. No file I/O beyond the single raw-artifact write.** No network I/O.

- [ ] **AC-11.** **`SloStub` — always not-opted-in.** Same shape as `ServiceTopologyStub`: `confidence="high"`, slice `NotOptedInSloSlice(opted_in=False, reason="phase_9_or_later")`, single raw artifact at `ctx.output_dir / "slo.json"`, no `repo.config` / `ctx.config` reads, no network I/O.

### Stub raw-artifact discipline

- [ ] **AC-NEW-6 (part 1: stubs).** **Each stub writes a single raw artifact atomically.** Each stub probe writes the JSON-serialized slice (`json.dumps(slice.model_dump(mode="json"), sort_keys=True, indent=2)`) to `ctx.output_dir / "<probe-name>.json"` via the `.tmp` → `os.replace` atomic-write pattern (Phase 0 writer chokepoint precedent). `raw_artifacts` is exactly `[ctx.output_dir / "<probe-name>.json"]` — a one-element list, no other files. Mirrors S6-04 AC-NEW-1. Mutation caught: a future contributor adding a body-bytes write would change `raw_artifacts` length and fire the test.

- **OwnershipProbe raw-artifact policy:** `OwnershipProbe` does NOT write a raw artifact (`raw_artifacts=[]`). The slice contents are the complete evidence; there is no separate body to persist. This mirrors the Layer-C marker probes (`certificate.py:76`, `dockerfile.py`'s post-parse path) — when the schema-slice contains 100% of the evidence, no raw artifact is written. The two stubs DO write raw artifacts because S6-04 establishes the deferred-stub raw-artifact discipline (the artifact carries the determination at the persistence boundary, making downstream cache-key derivation explicit).

### Functional core (ownership)

- [ ] **AC-NEW-6 (part 2: ownership pure parser).** **`OwnershipProbe`'s line-parser is a pure module-level free function** with the exact signature `def _parse_codeowners_lines(text: str) -> tuple[tuple[OwnershipEntry, ...], tuple[str, ...]]` — input is the file body as text; output is `(entries, parse_errors)`. The function performs NO `Path`/`open`/`fd` access, takes NO `RepoSnapshot` / `ProbeContext` / `Path` argument, raises NO exception (every malformed input is captured in the `parse_errors` tuple). Architectural test: AST-walk asserts `_parse_codeowners_lines` is a `FunctionDef` at module scope and its parameter annotation is `str`. Mirrors the functional-core extraction discipline `dockerfile.py` + `_dockerfile_parse.py` settled.

### Static integrity & negative invariants

- [ ] **AC-12.** **No HTTP / service-catalog client imports.** The two stub files (`service_topology_stub.py`, `slo_stub.py`) MUST NOT import `httpx`, `requests`, `aiohttp`, `urllib.request`, `socket`, `http.client`, `httplib`, or any service-mesh / service-catalog client library. Architectural test (parametrized across the two stubs; mirrors S6-04 AC-6's seven-member set).

- [ ] **AC-13.** **No cross-probe imports.** `ownership.py`, `service_topology_stub.py`, `slo_stub.py` do not import each other. Also: none imports from `layer_d/` probes. Architectural test parametrized across the three files. Mutation caught: a future contributor extracting a shared "deferred stub" base in one file and importing it from the other (premature abstraction; Rule of Three forbids).

- [ ] **AC-NEW-3.** **Tagged-union discriminator key documented in stub-module source.** Each stub module's docstring (or a code comment / type annotation) contains the literal string `discriminator="opted_in"` as the grep-discoverable trip-wire for the eventual Phase-9+ tagged-union widening. Mutation caught: a future contributor changing the discriminator key from `opted_in` to e.g. `kind` would silently fragment the Phase-9 widening strategy.

- [ ] **AC-NEW-4.** **No subclass-based extension path on any of the three probes.** Architectural test: AST-walk asserts no module under `layer_e/` contains `class X(OwnershipProbe)`, `class X(ServiceTopologyStubProbe)`, or `class X(SloStubProbe)`. The eventual opted-in branches for the stubs land as conditional `match` dispatch inside `run`, not as subclasses. Composition over inheritance; mirrors S6-04 AC-NEW-5.

### Body-size cap (ownership)

- [ ] **AC-14.** **`OwnershipProbe` — body size cap.** A `CODEOWNERS` larger than `OWNERSHIP_MAX_BYTES = 1 * 1024 * 1024` (1 MB) is rejected with `confidence="low"` and `errors=["codeowners_size_cap_exceeded:<n_bytes>"]`. Mutation caught: any unbounded read would let a hostile repo OOM the gather. Implementation: `Path.stat().st_size` (or `os.path.getsize(...)`) check **before** opening the file; on cap-exceeded, return immediately without reading any bytes.

### Registry & determinism

- [ ] **AC-NEW-2.** **Registry-membership smoke** for all three probes. `next((e for e in default_registry._entries if e.cls.name == "<probe-name>"), None)` is not `None` for each of `"ownership"`, `"service_topology"`, `"slo"`. Mutation caught: a future contributor removing the `@register_probe` decorator would silently stop the probe from running in every gather. Mirrors S6-04 AC-NEW-3.

- [ ] **AC-15.** **Determinism.** Two consecutive `await Probe().run(repo, ctx)` calls on the same fixture produce byte-identical `schema_slice` JSON for all three probes. For the two stubs, the `raw_artifacts[0]` file contents are also byte-identical. `OwnershipProbe` preserves source-file line order (NOT sorted — preserving authoring order is operationally useful when an entry is per-section). `duration_ms` is excluded from the byte-identity comparison (it varies by clock).

### Sub-schema deferred to S6-08

- [ ] **AC-16.** **Pydantic slice contracts enforce `additionalProperties: false`-equivalent at type level.** `extra="forbid"` on every slice model is asserted by `pytest.raises(pydantic.ValidationError)` on each slice for an unknown-field payload. The JSON-Schema sub-schema files under `src/codegenie/schema/probes/layer_e/` land in S6-08; the JSON-Schema round-trip is **not** asserted in this story (forward-dependency on S6-08 — a Phase-2 story can't precondition on a downstream artifact). S6-08's schema-naming convention should match the probe `name` (no `_stub` suffix on `service_topology` / `slo`); the validation report flags the S6-08 manifest for amendment.

### Quality gates

- [ ] **AC-17.** **`mypy --strict`** passes on all three probe files and the test module.

- [ ] **AC-18.** **The stub deferrals are grep-able.** A future Phase-9 contributor running `grep -rn "phase_9_or_later" src/codegenie/` MUST find both stub modules. The slice `reason: Literal["phase_9_or_later"]` is the deliberate trip-wire (the literal value is the grep-token).

## Implementation outline

1. Create `src/codegenie/probes/layer_e/__init__.py` (empty package marker; one-line docstring).
2. `ownership.py`:
   - Module docstring with the exact AC-NEW-7 phrase `"Phase 2 search order intentionally diverges from GitHub"`, plus pointers to `localv2.md` §5.5 and the `CertificateProbe` upstream-absent precedent.
   - `_LOCATIONS: Final[tuple[str, ...]] = ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS")`.
   - `OWNERSHIP_MAX_BYTES: Final[int] = 1 * 1024 * 1024`.
   - `_PROBE_ID: Final[ProbeId] = ProbeId("ownership")` (imported from `codegenie.types.identifiers`).
   - `OwnershipEntry(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")` and `pattern, owners, line_number`.
   - `OwnershipSlice(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")`, `source_path: str | None`, `entries: tuple[OwnershipEntry, ...]`.
   - **Pure module-level function `_parse_codeowners_lines(text: str) -> tuple[tuple[OwnershipEntry, ...], tuple[str, ...]]`** (functional core; AC-NEW-6 part 2) — splits on newlines, iterates with 1-indexed line numbers including blanks/comments in the count, skips blank/comment lines, splits each non-skipped line on whitespace, truncates at the first `#`-prefixed token (AC-NEW-5 inline-comment handling), and produces `(entries, parse_errors)`.
   - `@register_probe(heaviness="light")` `class OwnershipProbe(Probe):` with the full ABC field set (per AC-4 — `declared_inputs: list[str] = ["CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"]`) and `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` that:
     - finds the first existing location; if none, returns `confidence="low"` with empty slice + `errors=["codeowners_absent"]` (AC-6).
     - `Path.stat().st_size > OWNERSHIP_MAX_BYTES` check **before** opening the file → returns `confidence="low"` per AC-14.
     - reads the file text; calls `_parse_codeowners_lines(text)`; emits the slice + errors; `raw_artifacts=[]` (per the marker-probe convention — the slice carries all evidence).
3. `service_topology_stub.py`:
   - Module docstring with `"deferred to Phase 9 or later"` and `'discriminator="opted_in"'` literal phrases (AC-NEW-3 grep-trip-wires).
   - `_PROBE_ID: Final[ProbeId] = ProbeId("service_topology")`.
   - `NotOptedInServiceTopologySlice(BaseModel)` per AC-3.
   - `@register_probe(heaviness="light")` `class ServiceTopologyStubProbe(Probe):` with the full ABC field set (per AC-4; `name = "service_topology"`; `declared_inputs: list[str] = []`) and `async def run(self, repo, ctx)` that emits the not-opted-in slice unconditionally with `confidence="high"` and writes a single raw artifact to `ctx.output_dir / "service_topology.json"` atomically (`.tmp` → `os.replace`).
4. `slo_stub.py`:
   - Identical shape to `service_topology_stub.py` with `_PROBE_ID = ProbeId("slo")`, `NotOptedInSloSlice`, `SloStubProbe`, `name = "slo"`, single raw artifact at `ctx.output_dir / "slo.json"`.
5. Add `tests/unit/probes/layer_e/__init__.py` (empty package marker) and `tests/unit/probes/layer_e/conftest.py` with `_make_repo(tmp_path) + _make_ctx(tmp_path)` helpers (precedent: `tests/unit/probes/layer_c/test_dockerfile.py:61-74`). The helpers are local to this test directory; do NOT cross-import from `tests/unit/probes/layer_c/`.
6. Tests per the TDD plan.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/layer_e/__init__.py` | New file — package marker. |
| `src/codegenie/probes/layer_e/ownership.py` | New file — real `CODEOWNERS` parser (≤ 150 LOC including pure parser). |
| `src/codegenie/probes/layer_e/service_topology_stub.py` | New file — deferred stub (≤ 50 LOC). |
| `src/codegenie/probes/layer_e/slo_stub.py` | New file — deferred stub (≤ 50 LOC). |
| `tests/unit/probes/layer_e/__init__.py` | New file — empty package marker. |
| `tests/unit/probes/layer_e/conftest.py` | New file — `_make_repo` and `_make_ctx` helpers (mirrors `tests/unit/probes/layer_c/test_dockerfile.py:61-74`). |
| `tests/unit/probes/layer_e/test_ownership.py` | New file — happy-path + size-cap + absent + malformed + comment + inline-comment + search-order + determinism + registry + pure-parser AST tests. |
| `tests/unit/probes/layer_e/test_stubs.py` | New file — parametrized across the two stubs (Null Object behavior, no forbidden imports, no subclass extension, discriminator-key grep, determinism, raw-artifact byte-identity, registry membership, `_PROBE_ID` constant). |

## TDD plan — red / green / refactor

### Red — write the failing tests first

```python
# tests/unit/probes/layer_e/conftest.py
"""Shared helpers for Layer-E tests (S6-05).

`ProbeContext` is a stdlib @dataclass with no `for_test` classmethod;
constructing it in every test is verbose, so these helpers (mirroring
`tests/unit/probes/layer_c/test_dockerfile.py:61-74`) are the canonical
construction point for Layer-E unit tests.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from codegenie.probes.base import ProbeContext, RepoSnapshot


@pytest.fixture
def _make_repo():
    def _factory(tmp_path: Path, *, config: dict | None = None) -> RepoSnapshot:
        return RepoSnapshot(
            root=tmp_path,
            git_commit=None,
            detected_languages={},
            config=config or {},
        )
    return _factory


@pytest.fixture
def _make_ctx():
    def _factory(tmp_path: Path) -> ProbeContext:
        workspace = tmp_path / "_ws"
        workspace.mkdir(parents=True, exist_ok=True)
        out_dir = tmp_path / "_out"
        out_dir.mkdir(parents=True, exist_ok=True)
        return ProbeContext(
            cache_dir=tmp_path / "_cache",
            output_dir=out_dir,
            workspace=workspace,
            logger=logging.getLogger("test"),
            config={},
        )
    return _factory
```

```python
# tests/unit/probes/layer_e/test_ownership.py
"""Unit tests for OwnershipProbe (S6-05)."""
from __future__ import annotations

import ast
import asyncio
import inspect
import json
from pathlib import Path

import pydantic
import pytest

from codegenie.probes.layer_e import ownership as op
from codegenie.probes.registry import default_registry
from codegenie.types.identifiers import ProbeId


# ----------------------------------------------------------------------
# Pure parser — functional core (AC-NEW-6 part 2)
# ----------------------------------------------------------------------

def test_parse_codeowners_lines_is_pure_module_function() -> None:
    """AC-NEW-6 (part 2). Mutation caught: a future contributor moving
    the parser into the OwnershipProbe class (re-tangling pure / impure).
    """
    src = inspect.getsource(op)
    tree = ast.parse(src)
    found = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_parse_codeowners_lines":
            found = node
            break
    assert found is not None, "_parse_codeowners_lines must be a module-level function"
    # Single positional `text: str` parameter (no `self`, no `Path`, no `RepoSnapshot`).
    assert [a.arg for a in found.args.args] == ["text"]


def test_parse_codeowners_lines_happy_path() -> None:
    """AC-5. Mutation caught: any parser that emits owners as a single
    string instead of splitting on whitespace would fail the tuple
    length check."""
    text = (
        "# Default owners\n"
        "* @platform-team\n"
        "/api/ @api-team @platform-team\n"
        "*.md @docs-team\n"
    )
    entries, errors = op._parse_codeowners_lines(text)
    assert errors == ()
    assert len(entries) == 3
    assert entries[1].pattern == "/api/"
    assert entries[1].owners == ("@api-team", "@platform-team")
    assert entries[1].line_number == 3  # 1-indexed; comment line counts toward number


def test_parse_codeowners_lines_skips_comments_and_blanks() -> None:
    """AC-8. Mutation caught: emitting comments as entries with empty
    owners would conflate with AC-7's empty-owners case."""
    text = "# header\n\n* @team\n# trailing\n\n"
    entries, errors = op._parse_codeowners_lines(text)
    assert len(entries) == 1
    assert entries[0].pattern == "*"
    assert errors == ()


def test_parse_codeowners_lines_records_empty_owners_with_error() -> None:
    """AC-7. Mutation caught: silently dropping `*.py` (pattern with no
    owners) — operators need to know this is misconfigured."""
    text = "*.py\n"
    entries, errors = op._parse_codeowners_lines(text)
    assert entries[0].pattern == "*.py"
    assert entries[0].owners == ()
    assert "empty_owners_at_line_1" in errors


def test_parse_codeowners_lines_inline_comment_truncates_at_hash_token() -> None:
    """AC-NEW-5. Mutation caught: a `line.split('#', 1)[0]` naive
    implementation would also strip `#` characters legitimately
    appearing inside a pattern token; per-token truncation preserves
    pattern integrity."""
    text = "*.py @user # owners are the python team\n"
    entries, errors = op._parse_codeowners_lines(text)
    assert entries[0].pattern == "*.py"
    assert entries[0].owners == ("@user",)
    assert errors == ()


def test_parse_codeowners_lines_never_raises_on_garbage() -> None:
    """AC-NEW-6 (part 2). Pure parser must capture every malformed input
    in the `errors` tuple, never raise."""
    text = "\x00\x01\x02 weird\n@no-pattern-prefix\n  leading-ws @t\n"
    entries, errors = op._parse_codeowners_lines(text)
    # No exception; either some entries parsed or all rejected — the
    # parser's contract is "never raise", and per AC-7 empty-owner lines
    # produce a parse_error rather than silently dropping.
    assert isinstance(entries, tuple)
    assert isinstance(errors, tuple)


# ----------------------------------------------------------------------
# Imperative shell — async probe.run
# ----------------------------------------------------------------------

def test_ownership_happy_path_parses_repo_root_file(
    tmp_path: Path, _make_repo, _make_ctx,
) -> None:
    """AC-5. End-to-end imperative shell."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CODEOWNERS").write_text(
        "# Default owners\n* @platform-team\n/api/ @api-team @platform-team\n*.md @docs-team\n"
    )
    output = asyncio.run(op.OwnershipProbe().run(_make_repo(repo), _make_ctx(tmp_path)))
    assert output.confidence == "high"
    assert output.raw_artifacts == []  # AC: marker-probe convention; no raw artifact
    slice_ = op.OwnershipSlice.model_validate(output.schema_slice)
    assert slice_.source_path == "CODEOWNERS"
    assert len(slice_.entries) == 3
    assert slice_.entries[1].pattern == "/api/"
    assert slice_.entries[1].owners == ("@api-team", "@platform-team")
    assert output.duration_ms >= 0


def test_ownership_searches_three_locations_in_order(
    tmp_path: Path, _make_repo, _make_ctx,
) -> None:
    """AC-9. Mutation caught: any precedence change — operators expect
    the Phase-2 documented order (CODEOWNERS > .github/CODEOWNERS >
    docs/CODEOWNERS), which intentionally diverges from GitHub."""
    repo = tmp_path / "repo"
    (repo / ".github").mkdir(parents=True)
    (repo / "docs").mkdir()
    (repo / "CODEOWNERS").write_text("* @root\n")
    (repo / ".github" / "CODEOWNERS").write_text("* @github_dir\n")
    (repo / "docs" / "CODEOWNERS").write_text("* @docs_dir\n")
    output = asyncio.run(op.OwnershipProbe().run(_make_repo(repo), _make_ctx(tmp_path)))
    slice_ = op.OwnershipSlice.model_validate(output.schema_slice)
    assert slice_.source_path == "CODEOWNERS"  # root wins
    assert any("additional_codeowners_present_at" in e for e in output.errors)


def test_ownership_absent_yields_low_confidence_no_raise(
    tmp_path: Path, _make_repo, _make_ctx,
) -> None:
    """AC-6. Mutation caught: re-raising on a no-CODEOWNERS repo; or
    misframing absent-file as `confidence='high'` (the latter is the
    deferred-stub framing — wrong for this probe; the right precedent
    is the CertificateProbe upstream-absent pattern: confidence='low')."""
    repo = tmp_path / "repo"
    repo.mkdir()
    output = asyncio.run(op.OwnershipProbe().run(_make_repo(repo), _make_ctx(tmp_path)))
    assert output.confidence == "low"
    slice_ = op.OwnershipSlice.model_validate(output.schema_slice)
    assert slice_.entries == ()
    assert slice_.source_path is None
    assert "codeowners_absent" in output.errors


def test_ownership_size_cap_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _make_repo, _make_ctx,
) -> None:
    """AC-14. Mutation caught: any unbounded read. The cap fires
    *before* any read — verified by monkey-patching the size check; if
    the implementation reads bytes before checking size, the test still
    passes (the file is small) but the static design intent is
    documented by Notes §2."""
    import os
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CODEOWNERS").write_text("* @team\n")
    monkeypatch.setattr(os.path, "getsize", lambda p: op.OWNERSHIP_MAX_BYTES + 1)
    output = asyncio.run(op.OwnershipProbe().run(_make_repo(repo), _make_ctx(tmp_path)))
    assert output.confidence == "low"
    assert any("codeowners_size_cap_exceeded" in e for e in output.errors)


def test_ownership_two_runs_byte_identical(
    tmp_path: Path, _make_repo, _make_ctx,
) -> None:
    """AC-15. Mutation caught: any sort/reorder — line order preserves
    operator's intent (early lines often override later)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CODEOWNERS").write_text("/b/ @b\n/a/ @a\n/c/ @c\n")
    probe = op.OwnershipProbe()
    out1 = asyncio.run(probe.run(_make_repo(repo), _make_ctx(tmp_path))).schema_slice
    out2 = asyncio.run(probe.run(_make_repo(repo), _make_ctx(tmp_path))).schema_slice
    assert json.dumps(out1, sort_keys=True) == json.dumps(out2, sort_keys=True)
    slice_ = op.OwnershipSlice.model_validate(out1)
    assert [e.pattern for e in slice_.entries] == ["/b/", "/a/", "/c/"]


# ----------------------------------------------------------------------
# Registration & static integrity
# ----------------------------------------------------------------------

def test_ownership_probe_registered_light() -> None:
    """AC-4, AC-NEW-2."""
    entry = next(
        (e for e in default_registry._entries if e.cls.name == "ownership"),
        None,
    )
    assert entry is not None, "OwnershipProbe must be in default_registry._entries"
    assert entry.heaviness == "light"


def test_ownership_probe_id_constant_exists() -> None:
    """AC-NEW-1. Dual-form identity discipline."""
    assert hasattr(op, "_PROBE_ID")
    assert op._PROBE_ID == ProbeId("ownership")
    assert op.OwnershipProbe.name == "ownership"


def test_ownership_no_subclass_extension_path() -> None:
    """AC-NEW-4. Mutation caught: a `class FancyOwnershipProbe(OwnershipProbe)`
    fragments dispatch into a class hierarchy; composition wins."""
    tree = ast.parse(inspect.getsource(op))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            assert "OwnershipProbe" not in bases, f"Subclass {node.name!r} violates AC-NEW-4"


def test_ownership_docstring_documents_github_divergence() -> None:
    """AC-NEW-7. The intentional divergence from GitHub's documented
    search order is grep-discoverable."""
    assert op.__doc__ is not None
    assert "Phase 2 search order intentionally diverges from GitHub" in op.__doc__


def test_ownership_slice_rejects_extra_fields() -> None:
    """AC-2, AC-16. Mutation caught: relaxing extra='forbid' to 'allow'
    would silently admit unknown fields."""
    with pytest.raises(pydantic.ValidationError):
        op.OwnershipSlice(
            source_path="CODEOWNERS",
            entries=(),
            extra_field="x",  # type: ignore[call-arg]
        )
```

```python
# tests/unit/probes/layer_e/test_stubs.py
"""Unit tests for ServiceTopologyStub + SloStub (S6-05).

Parametrized across the two stub probes — they are deliberately
near-identical (S6-04 deferred-stub precedent); the parametrization
makes the duplication visible without hiding it behind a base class
(Rule of Three forbids — three deferred stubs is the trigger; we have
two stubs in this story plus S6-04's external_docs as the third, so
the rule-of-three discussion can land in a Phase-4 cleanup story
*if* a contributor wants to extract — until then, three similar
modules is cheaper than a premature abstraction).
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import json
from pathlib import Path

import pydantic
import pytest

from codegenie.probes.layer_e import service_topology_stub as sts
from codegenie.probes.layer_e import slo_stub as slo
from codegenie.probes.registry import default_registry
from codegenie.types.identifiers import ProbeId


_STUB_PARAMS = [
    pytest.param(
        sts, sts.ServiceTopologyStubProbe, sts.NotOptedInServiceTopologySlice,
        "service_topology", id="service_topology",
    ),
    pytest.param(
        slo, slo.SloStubProbe, slo.NotOptedInSloSlice,
        "slo", id="slo",
    ),
]


@pytest.mark.parametrize(("module", "probe_cls", "slice_cls", "probe_name"), _STUB_PARAMS)
def test_stub_always_high_confidence_not_opted_in(
    module, probe_cls, slice_cls, probe_name, tmp_path: Path,
    _make_repo, _make_ctx,
) -> None:
    """AC-10, AC-11. Mutation caught: any future code that flips to
    `confidence='low'` (which would signal "we tried and failed")
    without an ADR-amend; or any code that reads `repo.config[...]`
    and bifurcates the response (the slippery slope to a real
    fetcher)."""
    output = asyncio.run(probe_cls().run(_make_repo(tmp_path), _make_ctx(tmp_path)))
    assert output.confidence == "high"
    slice_ = slice_cls.model_validate(output.schema_slice)
    assert slice_.opted_in is False
    assert slice_.reason == "phase_9_or_later"
    assert output.warnings == []
    assert output.errors == []


@pytest.mark.parametrize(("module", "probe_cls", "slice_cls", "probe_name"), _STUB_PARAMS)
def test_stub_writes_single_raw_artifact_atomically(
    module, probe_cls, slice_cls, probe_name, tmp_path: Path,
    _make_repo, _make_ctx,
) -> None:
    """AC-NEW-6 (part 1: stubs). Single canonical raw artifact named
    after the probe."""
    ctx = _make_ctx(tmp_path)
    output = asyncio.run(probe_cls().run(_make_repo(tmp_path), ctx))
    expected = ctx.output_dir / f"{probe_name}.json"
    assert output.raw_artifacts == [expected]
    on_disk = json.loads(expected.read_bytes())
    assert on_disk == output.schema_slice


@pytest.mark.parametrize(("module", "probe_cls", "slice_cls", "probe_name"), _STUB_PARAMS)
def test_stub_two_runs_byte_identical(
    module, probe_cls, slice_cls, probe_name, tmp_path: Path,
    _make_repo, _make_ctx,
) -> None:
    """AC-15. Mutation caught: any timestamp / nonce / per-run ID in
    the not-opted-in slice or the raw artifact."""
    ctx = _make_ctx(tmp_path)
    probe = probe_cls()
    out1 = asyncio.run(probe.run(_make_repo(tmp_path), ctx))
    out2 = asyncio.run(probe.run(_make_repo(tmp_path), ctx))
    assert json.dumps(out1.schema_slice, sort_keys=True) == json.dumps(
        out2.schema_slice, sort_keys=True,
    )
    # Raw artifact was overwritten by run #2; re-read.
    raw_bytes = (ctx.output_dir / f"{probe_name}.json").read_bytes()
    assert json.loads(raw_bytes) == out2.schema_slice


@pytest.mark.parametrize(("module", "probe_cls", "slice_cls", "probe_name"), _STUB_PARAMS)
def test_stub_registered_light_and_in_registry(
    module, probe_cls, slice_cls, probe_name,
) -> None:
    """AC-4, AC-NEW-2."""
    entry = next(
        (e for e in default_registry._entries if e.cls.name == probe_name),
        None,
    )
    assert entry is not None, f"{probe_name} probe must be in default_registry._entries"
    assert entry.heaviness == "light"


@pytest.mark.parametrize(("module", "probe_cls", "slice_cls", "probe_name"), _STUB_PARAMS)
def test_stub_probe_id_constant_exists(
    module, probe_cls, slice_cls, probe_name,
) -> None:
    """AC-NEW-1. Dual-form identity."""
    assert hasattr(module, "_PROBE_ID")
    assert module._PROBE_ID == ProbeId(probe_name)
    assert probe_cls.name == probe_name


@pytest.mark.parametrize(("module", "probe_cls", "slice_cls", "probe_name"), _STUB_PARAMS)
def test_stub_no_forbidden_imports(module, probe_cls, slice_cls, probe_name) -> None:
    """AC-12. Mutation caught: any HTTP/socket client import would
    break the Phase-0 fence — and break the determinism guarantee."""
    forbidden = {
        "httpx", "requests", "urllib.request", "aiohttp",
        "socket", "http.client", "httplib",
    }
    tree = ast.parse(inspect.getsource(module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    assert not (forbidden & names), f"Forbidden imports in {probe_name}: {forbidden & names}"


@pytest.mark.parametrize(("module", "probe_cls", "slice_cls", "probe_name"), _STUB_PARAMS)
def test_stub_no_subclass_extension_path(
    module, probe_cls, slice_cls, probe_name,
) -> None:
    """AC-NEW-4. The eventual opted-in branch is `match` dispatch
    inside `run`, not a subclass."""
    tree = ast.parse(inspect.getsource(module))
    target_name = probe_cls.__name__
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            assert target_name not in bases, (
                f"Subclass {node.name!r} of {target_name} violates AC-NEW-4"
            )


@pytest.mark.parametrize(("module", "probe_cls", "slice_cls", "probe_name"), _STUB_PARAMS)
def test_stub_docstring_names_opted_in_discriminator(
    module, probe_cls, slice_cls, probe_name,
) -> None:
    """AC-NEW-3. Mutation caught: a future contributor changing the
    discriminator key from `opted_in` to e.g. `kind` would silently
    fragment the Phase-9+ tagged-union strategy. The grep token
    `discriminator="opted_in"` is the load-bearing trip-wire."""
    src = inspect.getsource(module)
    assert 'discriminator="opted_in"' in src, (
        f"{probe_name} module must explicitly name `opted_in` as the eventual "
        "tagged-union discriminator key (in a comment, docstring, or code) per AC-NEW-3."
    )


@pytest.mark.parametrize(("module", "probe_cls", "slice_cls", "probe_name"), _STUB_PARAMS)
def test_stub_docstring_documents_deferral(
    module, probe_cls, slice_cls, probe_name,
) -> None:
    """AC-18. The deferral is grep-able via 'phase_9_or_later'."""
    assert module.__doc__ is not None
    assert "deferred to Phase 9 or later" in module.__doc__


@pytest.mark.parametrize(("module", "probe_cls", "slice_cls", "probe_name"), _STUB_PARAMS)
def test_stub_slice_rejects_opted_in_true(
    module, probe_cls, slice_cls, probe_name,
) -> None:
    """AC-3. Mutation caught: relaxing `opted_in: Literal[False]` to
    `bool` would silently accept a True value before the opted-in
    branch exists in `run`."""
    with pytest.raises(pydantic.ValidationError):
        slice_cls(opted_in=True, reason="phase_9_or_later")  # type: ignore[arg-type]


@pytest.mark.parametrize(("module", "probe_cls", "slice_cls", "probe_name"), _STUB_PARAMS)
def test_stub_slice_rejects_extra_fields(
    module, probe_cls, slice_cls, probe_name,
) -> None:
    """AC-2, AC-16. extra='forbid' enforced at Pydantic level."""
    with pytest.raises(pydantic.ValidationError):
        slice_cls(opted_in=False, reason="phase_9_or_later", extra="x")  # type: ignore[call-arg]


def test_no_cross_probe_imports_among_layer_e_files() -> None:
    """AC-13. The three layer_e files do not import each other; none
    imports from layer_d. Mutation caught: a future contributor
    extracting a shared base in one file and importing it in the
    others (premature abstraction; Rule of Three forbids)."""
    import importlib
    own = importlib.import_module("codegenie.probes.layer_e.ownership")
    files_to_check = [own, sts, slo]
    forbidden_substrings = (
        "codegenie.probes.layer_e.ownership",
        "codegenie.probes.layer_e.service_topology_stub",
        "codegenie.probes.layer_e.slo_stub",
        "codegenie.probes.layer_d",
    )
    for mod in files_to_check:
        src = inspect.getsource(mod)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                # Allow self-imports (a module can re-export from itself in __all__)
                for forbidden in forbidden_substrings:
                    if forbidden == mod.__name__:
                        continue
                    assert forbidden not in node.module, (
                        f"{mod.__name__} forbidden-imports from {node.module}"
                    )
```

### Green — make it pass

Skeleton for `ownership.py` (the impure shell is small; the parser is the pure core):

```python
# src/codegenie/probes/layer_e/ownership.py
"""OwnershipProbe — Layer E, light heaviness.

Parses CODEOWNERS from three GitHub-convention locations.

Phase 2 search order intentionally diverges from GitHub:
this implementation prefers <repo>/CODEOWNERS over <repo>/.github/CODEOWNERS
because the repo-root file is the most visible to operators. An operator
who wants .github/CODEOWNERS to win simply deletes the root file.

Functional core / imperative shell:
`_parse_codeowners_lines(text)` is the pure core; `OwnershipProbe.run`
is the only impure code (filesystem search + size cap + file read).

Sources:
- ../../localv2.md §5.5 E1.
- src/codegenie/probes/layer_c/certificate.py:67-81 (CertificateProbe
  upstream-absent precedent: absent expected file → confidence='low').
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe
from codegenie.types.identifiers import ProbeId

__all__ = ["OwnershipEntry", "OwnershipProbe", "OwnershipSlice"]

_LOCATIONS: Final[tuple[str, ...]] = ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS")
OWNERSHIP_MAX_BYTES: Final[int] = 1 * 1024 * 1024  # 1 MB
_PROBE_ID: Final[ProbeId] = ProbeId("ownership")


class OwnershipEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    pattern: str
    owners: tuple[str, ...]
    line_number: int


class OwnershipSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_path: str | None
    entries: tuple[OwnershipEntry, ...]


def _parse_codeowners_lines(text: str) -> tuple[tuple[OwnershipEntry, ...], tuple[str, ...]]:
    """Pure functional-core CODEOWNERS line parser.

    1-indexed line numbers include blank/comment lines in the count
    (operators expect `vim +N`-compatible line numbers).
    """
    entries: list[OwnershipEntry] = []
    errors: list[str] = []
    for idx, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        tokens = stripped.split()
        # AC-NEW-5: truncate at the first `#`-prefixed token (inline comment).
        for i, tok in enumerate(tokens):
            if tok.startswith("#"):
                tokens = tokens[:i]
                break
        if not tokens:
            continue
        pattern = tokens[0]
        owners = tuple(tokens[1:])
        if not owners:
            errors.append(f"empty_owners_at_line_{idx}")
        entries.append(OwnershipEntry(pattern=pattern, owners=owners, line_number=idx))
    return tuple(entries), tuple(errors)


@register_probe(heaviness="light")
class OwnershipProbe(Probe):
    name: str = "ownership"
    version: str = "0.1.0"
    layer = "E"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    declared_inputs: list[str] = list(_LOCATIONS)
    timeout_seconds: int = 5
    cache_strategy: Literal["content"] = "content"

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        found: list[Path] = [repo.root / loc for loc in _LOCATIONS if (repo.root / loc).exists()]
        if not found:
            return ProbeOutput(
                schema_slice=OwnershipSlice(source_path=None, entries=()).model_dump(mode="json"),
                raw_artifacts=[],
                confidence="low",
                duration_ms=int((time.perf_counter() - t0) * 1000),
                warnings=[],
                errors=["codeowners_absent"],
            )
        primary = found[0]
        extra_errors: list[str] = [
            f"additional_codeowners_present_at:{p.relative_to(repo.root)}" for p in found[1:]
        ]
        size = os.path.getsize(primary)
        if size > OWNERSHIP_MAX_BYTES:
            return ProbeOutput(
                schema_slice=OwnershipSlice(
                    source_path=str(primary.relative_to(repo.root)), entries=(),
                ).model_dump(mode="json"),
                raw_artifacts=[],
                confidence="low",
                duration_ms=int((time.perf_counter() - t0) * 1000),
                warnings=[],
                errors=[f"codeowners_size_cap_exceeded:{size}"] + extra_errors,
            )
        text = primary.read_text()
        entries, parse_errors = _parse_codeowners_lines(text)
        return ProbeOutput(
            schema_slice=OwnershipSlice(
                source_path=str(primary.relative_to(repo.root)),
                entries=entries,
            ).model_dump(mode="json"),
            raw_artifacts=[],
            confidence="high",
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=[],
            errors=list(parse_errors) + extra_errors,
        )
```

Skeleton for `service_topology_stub.py` (mirrors S6-04 `external_docs.py` shape):

```python
# src/codegenie/probes/layer_e/service_topology_stub.py
"""ServiceTopologyStubProbe — Layer E, light heaviness, deferred stub.

The real service-topology data source (service mesh / Backstage / OpsLevel /
Cortex) is deferred to Phase 9 or later. Phase 2 ships a registered stub
that emits a typed NotOptedInServiceTopologySlice with `opted_in=False,
reason="phase_9_or_later"` and `confidence="high"` (absence is the data;
S6-04 NotOptedInExternalDocsSlice precedent).

Discriminator key for the eventual tagged union: `discriminator="opted_in"`.
The Phase-9+ opted-in variant lands as a *new* sibling Pydantic model
(`OptedInServiceTopologySlice`) joined under
`Annotated[NotOptedInServiceTopologySlice | OptedInServiceTopologySlice,
Field(discriminator="opted_in")]`, dispatched via `match` on
`repo.config.get("service_topology")` inside `run` — never via subclass.

NONE of the Phase-9 opted-in logic ships in Phase 2.
"""
from __future__ import annotations

import json
import os
import time
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe
from codegenie.types.identifiers import ProbeId

__all__ = ["NotOptedInServiceTopologySlice", "ServiceTopologyStubProbe"]

_PROBE_ID: Final[ProbeId] = ProbeId("service_topology")


class NotOptedInServiceTopologySlice(BaseModel):
    """Phase-2 closed shape — not-opted-in variant of the eventual
    `Annotated[NotOptedInServiceTopologySlice | OptedInServiceTopologySlice,
    Field(discriminator="opted_in")]` tagged union."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    opted_in: Literal[False]
    reason: Literal["phase_9_or_later"]


@register_probe(heaviness="light")
class ServiceTopologyStubProbe(Probe):
    name: str = "service_topology"
    version: str = "0.1.0"
    layer = "E"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    declared_inputs: list[str] = []
    timeout_seconds: int = 5
    cache_strategy: Literal["content"] = "content"

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        slice_ = NotOptedInServiceTopologySlice(opted_in=False, reason="phase_9_or_later")
        payload = slice_.model_dump(mode="json")
        out_path = ctx.output_dir / "service_topology.json"
        tmp_path = out_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(payload, sort_keys=True, indent=2))
        os.replace(tmp_path, out_path)
        return ProbeOutput(
            schema_slice=payload,
            raw_artifacts=[out_path],
            confidence="high",
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=[],
            errors=[],
        )
```

`slo_stub.py` mirrors `service_topology_stub.py` exactly with `_PROBE_ID = ProbeId("slo")`, `NotOptedInSloSlice`, `SloStubProbe`, `name = "slo"`, and `out_path = ctx.output_dir / "slo.json"`. The duplication is deliberate (Rule of Three not yet triggered — three deferred stubs across S6-04 + this story, but each one's eventual divergence will be different; see Notes §7).

### Refactor

- **Do not extract a shared stub base** between `service_topology_stub`, `slo_stub`, and S6-04's `external_docs`. Three deferred-stub probes with identical inert shape *is* the Rule-of-Three trigger threshold, but each one's eventual Phase-9+ divergence will be different: `external_docs` widens to a Confluence/Notion/URL-list tagged union; `service_topology` widens to a service-mesh/Backstage/OpsLevel union; `slo` widens to per-provider SLO catalogs. Extracting a base now would force a generic / `Any`-typed `reason` and erase the per-stub `Literal` invariants — both worse than duplication.
- **When the Phase-9+ opted-in branches land** (one stub at a time), each one's `run` dispatches via exhaustive `match` inside the same file (not via subclass; not via an `if/else` ladder; not via edits to the existing `NotOptedIn…Slice` model):

  ```python
  async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
      match repo.config.get("service_topology"):
          case None | {}:
              return await _emit_not_opted_in_topology(ctx)
          case {"sources": _}:
              return await _emit_opted_in_topology(repo, ctx)
          case other:
              assert_never(other)
  ```

  `_emit_not_opted_in_topology` and `_emit_opted_in_topology` are module-level free functions (functional-core / imperative-shell discipline). The opted-in branch's mesh-fetcher lands as a separate sibling module `_service_topology_fetcher.py`; the probe class stays a thin dispatcher.

- **`OwnershipProbe`'s `_parse_codeowners_lines` is the functional-core extract** — keep it pure (`text: str -> (entries, errors)`). Any temptation to "let the parser open the file directly" or "let the parser take a `Path`" re-tangles pure/impure and breaks the AST test for AC-NEW-6 part 2.

## Out of scope

- **Service-catalog HTTP clients** (Backstage, OpsLevel, Cortex). Phase 9+.
- **Service mesh API integration** (Istio, Linkerd, Consul Connect). Phase 9+.
- **OpenAPI / gRPC / GraphQL parsing** (`ServiceContractProbe` — E3 in `localv2.md`). Phase-3-or-later; not Phase 2's scope per the manifest.
- **Production config probe** (E5). Phase 9+ deferred stub.
- **JSON-Schema sub-schema round-trip tests.** Sub-schemas under `src/codegenie/schema/probes/layer_e/` land in S6-08; this story asserts Pydantic-level `extra="forbid"` + `Literal` enforcement, not JSON Schema.
- **Email / handle redaction.** The writer chokepoint (`SecretRedactor`) handles it via Phase 0's field-name regex + Phase 2's pattern set. The probe captures `@team`/`@user` honestly.
- **`CODEOWNERS` escape sequences** (`\#`, escaped spaces in patterns). Phase 2's parser is whitespace-split + token-truncate; escape handling is a Phase 3+ refinement if real CODEOWNERS files demand it.

## Notes for the implementer

1. **`OwnershipProbe.confidence` is `"low"` on absent file, `"high"` on found-file.** Distinction matters: absent CODEOWNERS is a Planner-actionable observation ("this repo has no owners declared, route to default"); the CertificateProbe upstream-absent precedent applies (`src/codegenie/probes/layer_c/certificate.py:67-81`). This is **different** from the deferred-stub framing used by `ServiceTopologyStub` / `SloStub` (where `confidence="high"` because the probe successfully determined the feature is not opted in — S6-04 `NotOptedInExternalDocsSlice` precedent). Both framings coexist in the codebase; pick the right one per probe.
2. **`Path.stat().st_size` (or `os.path.getsize(...)`) before opening the file.** AC-14 is the first defense. If the file passes the cap, `Path.read_text()` is fine for Phase 2 (CODEOWNERS files are small in practice; bounded line iteration via `itertools.islice` would be belt-and-suspenders but `text.splitlines()` after a size-cap-bounded read is sufficient for the 1 MB cap).
3. **`OwnershipEntry.line_number` is 1-indexed and includes blank/comment lines in the count.** Operators expect a line number that matches their editor (`vim +N`). Counting only emitted entries would diverge from the actual file.
4. **GitHub's documented search order** is `.github/CODEOWNERS` > `CODEOWNERS` > `docs/CODEOWNERS`. The implementation here uses `CODEOWNERS` > `.github/CODEOWNERS` > `docs/CODEOWNERS`. **This is intentional** — Phase 2's discipline is "the root location wins" because it's the most visible. If an operator wants `.github/CODEOWNERS` to win, they delete the root file. AC-NEW-7 requires the exact phrase `"Phase 2 search order intentionally diverges from GitHub"` in the module docstring so a future contributor sees the choice was deliberate.
5. **`OwnershipSlice.source_path: str | None`** is honest about the absent case. A sentinel `""` would be primitive obsession; `None` is the right "no file" representation.
6. **`OwnershipEntry.owners` is `tuple[str, ...]`, not `set[str]`.** A `CODEOWNERS` line `*.py @a @b @a` is operator misconfiguration but is parsed as-given; deduplication is the Planner's responsibility (or a later linter probe).
7. **`ServiceTopologyStub` and `SloStub` are deliberately near-identical.** Resist refactoring them into a single file or a base class — the eventual Phase-9+ divergence (per-source error unions, per-source config schemas) means the closed `reason: Literal[...]` discriminator on each will diverge. Their identicality now is a coincidence of "both empty." Rule-of-three with S6-04 ExternalDocsProbe is the third instance; the cleanup conversation lands at Phase 4 *only if a contributor wants it*; otherwise three similar deferred-stub modules (each ≤ 50 LOC) is cheaper than one shared abstraction.
8. **Design patterns to name explicitly** (mirrors S6-04 Notes §6):
   - **Null Object** — the stubs satisfy the `Probe` ABC so the coordinator, renderer, and Planner consume `ServiceTopologyStubProbe` / `SloStubProbe` exactly as they consume any other Layer-E probe — no null-checks, no `if probe.name in {"service_topology", "slo"}: skip`, no special-casing.
   - **Tagged union via discriminator** — `opted_in` is the discriminator key for the eventual Phase-9+ widening. The Phase-2 commitment is the key choice (`opted_in`, not `kind` or `type`); the variants land later.
   - **Open/Closed at file boundary** — the eventual opted-in branches land via `match` dispatch + new sibling slice models in the same file, never via subclass and never via edits to the existing `NotOptedIn…Slice` models.
   - **Functional core / imperative shell** — `OwnershipProbe._parse_codeowners_lines` is pure; `run` is the imperative shell. Mirrors `dockerfile.py` + `_dockerfile_parse.py`.
9. **`async def run(self, repo, ctx)` — NOT `_run(self, ctx)`.** Phase 0 ADR-0007 freezes the ABC byte-for-byte against `localv2.md §4`: `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`. The `repo` is the first positional arg (not a `ctx` field); the method is public (`run`), not `_run`. Tests use `asyncio.run(probe.run(repo, ctx))` (precedent: `tests/unit/probes/layer_c/test_dockerfile.py:77-78`). The `_make_repo` / `_make_ctx` helpers in `tests/unit/probes/layer_e/conftest.py` are the canonical construction points — `ProbeContext` is a stdlib `@dataclass` with no `for_test` classmethod.
10. **`name: str = "ownership"` ABC attr + `_PROBE_ID: Final[ProbeId]` module constant — the dual-form identity.** S6-01..S6-04 settled this convention: the ABC field is `name: str` (frozen, stringly-typed for ABC compatibility); the module-level `_PROBE_ID: Final[ProbeId]` constant carries the typed `NewType`-wrapped identifier for any in-module use. `ProbeId` is imported from `codegenie.types.identifiers` — `codegenie.ids` does not exist (recurring documentation drift).
11. **`tuple[str, ...]` for `applies_to_*` is wrong — use `list[str]`.** The ABC declares `applies_to_tasks: list[str]` and `applies_to_languages: list[str]`. A `tuple` annotation contradicts the contract and will fail the `tests/unit/test_probe_contract.py` snapshot.
12. **Atomic write via `.tmp` → `os.replace` for the stub raw artifacts.** Mirrors S6-04 GREEN code path. The byte-identity determinism test (AC-15) depends on `json.dumps(..., sort_keys=True, indent=2)` + atomic replace.
13. **Phase 0 ADR-0007 freezes the `Probe` ABC. The full field set is mandatory.** Every probe must declare the full field set (`version`, `layer`, `tier`, `applies_to_*`, `requires`, `declared_inputs`, `timeout_seconds`, `cache_strategy`). The canonical full-field reference is `src/codegenie/probes/layer_b/index_health.py:298-326`; mirror it exactly.
