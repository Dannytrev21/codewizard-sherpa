# Story S6-04 — `ExternalDocsProbe` opt-in skip-cleanly stub

**Step:** Step 6 — Ship Layer D + E + G probes (skills, conventions, ADRs, ownership, scanners)
**Status:** Hardened (ready for executor)
**Effort:** S
**Depends on:** S6-03 (Layer D marker-probe shape established — async `run(repo, ctx)`; `_make_context`/`_make_repo` test helpers; flat schema path; `_PROBE_ID: Final[ProbeId]` constant alongside `name: str` ABC attr; `default_registry._entries` registry lookup; functional-core/imperative-shell split; "absence is the data → `confidence='high'`" precedent from S6-01 empty-install case).
**ADRs honored:** Phase 0 ADR-0007 (`Probe` ABC frozen byte-for-byte against `localv2.md §4` — `name: str`, `async def run(self, repo, ctx)`, `ProbeOutput` six-field shape, `confidence: Literal["high","medium","low"]`), 02-ADR-0003 (`@register_probe(heaviness=…)` is a registry kwarg — NOT a `Probe` ABC field), 02-ADR-0007 (no plugin loader in Phase 2 — and by extension, no Confluence/Notion HTTP clients), 02-ADR-0005 (no plaintext persistence), 02-ADR-0008 (no event stream in Phase 2 — RAG-store handoff deferred to Phase 4)
**Phase-2 deferred decision honored:** [final-design.md "Open Q 4"](../final-design.md) — `external_docs:` allowlist schema lands when the first real user opts in. Phase 2 ships the skip-cleanly stub. **Do NOT invent an allowlist schema speculatively.**

## Validation notes

**Hardened 2026-05-17 via `phase-story-validator`** (see [`_validation/S6-04-external-docs-opt-in.md`](_validation/S6-04-external-docs-opt-in.md) for the full audit log). Twenty in-place edits resolved **nine `block`-severity contract mismatches** between the original draft and the kernel actually shipped (`src/codegenie/probes/base.py:52-96`, `src/codegenie/probes/registry.py:131-238`, `src/codegenie/types/identifiers.py:29`). The biggest structural fix: the original draft built every AC and test around `confidence="unavailable"`, a value that **does not exist** in the frozen `ProbeOutput.confidence: Literal["high","medium","low"]` ABC field (Phase 0 ADR-0007, `src/codegenie/probes/base.py:68`); the harden re-routes the semantics through S6-01's "absence is the data → `confidence='high'`" precedent (the deferred-stub state is one the probe *successfully determined* — not a failure-to-determine), with the typed `opted_in: Literal[False]` + `reason: Literal["not_opted_in"]` slice fields carrying the state and the confidence reporting the *quality of the determination*. Eight further block-severity contract fixes mirror S6-01/S6-02/S6-03 hardenings: `_run(ctx)` → `async def run(self, repo, ctx)`; `probe_id` class attr → `name: str = "external_docs"` ABC attr + module-level `_PROBE_ID: Final[ProbeId] = ProbeId("external_docs")` constant; full frozen Phase-0 ABC field set declared verbatim (`version`, `layer`, `tier`, `requires`, `declared_inputs`, `timeout_seconds`, `cache_strategy`); `tuple[str, ...]` → `list[str]` for `applies_to_*` (ABC requires `list`); `from codegenie.ids` → `from codegenie.types.identifiers` (`codegenie.ids` doesn't exist); `_PROBE_REGISTRY["external_docs"]` → `next(e for e in default_registry._entries if e.cls.name == "external_docs")`; flat sub-schema path (`src/codegenie/schema/probes/external_docs.schema.json` — no `layer_d/` subdir); `ProbeOutput(probe_id=..., …)` → six-field shape (`schema_slice, raw_artifacts, confidence, duration_ms, warnings, errors`) with `duration_ms` via `time.perf_counter()`. Five new ACs cover the raw-artifact emission (mirrors S6-01/02/03 single-raw-artifact discipline), the `_PROBE_ID: Final[ProbeId]` constant, the `pydantic.ValidationError` exception specificity (replaces broad `Exception` catches), the registry-membership smoke (probe runs in every gather), and an extension-by-addition AC: the opted-in variant lands as a tagged-union sibling discriminated on `opted_in`, never as a subclass and never via edits to the existing `NotOptedInExternalDocsSlice` model. The TDD plan now uses `_make_context(tmp_path)` / `_make_repo(tmp_path)` helpers, drops the brittle `Path(__file__).parents[4]` math in favor of a `_PROJECT_ROOT` constant resolved from `conftest.py`, and runs the async probe via `asyncio.run`. The manifest entry in [`./README.md`](README.md) line 194 was updated to reflect the corrected `confidence="high"` semantics. No `NEEDS RESEARCH` findings — every gap traced to in-repo precedent (`src/codegenie/probes/layer_b/index_health.py:298-326` for the full ABC field declaration; S6-01 / S6-02 / S6-03 validation reports for the contract-fix lineage).

## Context

`ExternalDocsProbe` is the only Layer D probe whose data sources live outside the repo and outside `~/.codegenie/` — Confluence, Notion, internal wikis, HTTP doc lists. The full design (`localv2.md` §5.4 D8) is rich: configurable per-source fetchers, normalization to markdown, BM25 indexing (D9), table-of-contents extraction. Shipping all of that in Phase 2 would violate three commitments at once:

1. **"No LLM anywhere in the gather pipeline."** Confluence clients aren't LLMs, but they introduce network I/O the determinism story doesn't support.
2. **"Extension by addition."** A real `external_docs:` config schema has six+ source types (Confluence, Notion, filesystem, URL list, …); each requires its own Pydantic discriminated union variant. Picking that schema before a real user opts in guarantees it will be wrong (the "premature schema" failure mode).
3. **The Phase 0 `fence` job.** `external_docs:` clients use `httpx` / `requests` / `socket`; the fence forbids those imports under `src/codegenie/`. Shipping a real fetcher requires an ADR-amend on the fence allowlist.

Phase 2's contract: the probe **exists**, is registered, runs in every gather, and successfully determines that the feature is not opted in. The state is carried in the typed slice — `opted_in: Literal[False]`, `reason: Literal["not_opted_in"]` — while `confidence="high"` reports the *quality of that determination* (we are certain about what we are reporting: the feature is off; nothing was tried, nothing failed). This mirrors the S6-01 "empty install" hardening precedent: **absence is the data**, not a failure to gather data. When a real user opts in later, the probe's `run` extends — but Phase 2 ships only the inert default path. The full schema for the opted-in variant lands with the first opt-in (Phase 4-or-later); Phase 2's sub-schema covers only the not-opted-in shape and pins `opted_in=False` via the `Literal[False]` discriminator so the eventual opted-in variant lands as a *new* discriminated-union sibling, never as a backward-compatible additive field on the existing model.

Design-pattern lineage the implementer inherits (and must not break):

1. **Null Object pattern** — a non-functional implementation that satisfies the `Probe` ABC so the coordinator, the `confidence` section renderer, and the Planner consume `ExternalDocsProbe` exactly as they consume any other Layer-D probe — no null-checks, no `if probe == "external_docs": skip`, no special-casing.
2. **Tagged union via discriminator** — `opted_in` is *the* discriminator key. The Phase 2 closed shape is `Literal[False]`; the eventual Phase-4+ tagged union is `Annotated[NotOptedInExternalDocsSlice | OptedInExternalDocsSlice, Field(discriminator="opted_in")]`. Picking the discriminator key in Phase 2 is the **only** schema commitment Phase 2 makes; everything else is deferred.
3. **Open/Closed at the file boundary** — when the opted-in branch lands (Phase 4+), the dispatch is `match repo.config.get("external_docs"): case None | {}: _emit_not_opted_in(); case {"sources": _}: _emit_opted_in(...)` with an exhaustive `match` + `assert_never` on the discriminator. **Not** a subclass; **not** an `if`/`else` ladder; **not** edits to the `NotOptedInExternalDocsSlice` model.
4. **Functional core / imperative shell** — `run` is pure (no I/O, no `ctx.config` reads in Phase 2). When the opted-in branch lands, the imperative shell (HTTP fetcher + parser) is a *new* free-function pair under `src/codegenie/probes/layer_d/_external_docs_fetcher.py`; the probe class stays a thin dispatcher.

The discipline this story protects: **don't write a speculative `external_docs:` allowlist schema**. A future maintainer reading this story should see "we deliberately deferred — here is the discriminator key, here is the dispatch shape, here is what lands next" rather than "we sketched a schema and then we'll iterate."

## References — where to look

- **Architecture:**
  - [`../final-design.md` Open Q 4](../final-design.md) — `ExternalDocsProbe` enablement & host allowlist schema deferred.
  - [`../phase-arch-design.md` §"Open questions deferred to implementation"](../phase-arch-design.md) #4 — same deferral.
  - [`../phase-arch-design.md` §"Anti-patterns avoided"](../phase-arch-design.md) "Schema before consumer" — every typed sum has a Phase 2 consumer; the opted-in variant has no Phase 2 consumer, so it does not ship.
- **Phase ADRs:**
  - [`../ADRs/0007-no-plugin-loader-in-phase-2.md`](../ADRs/0007-no-plugin-loader-in-phase-2.md) — the canonical "ship the boundary, defer the implementation" precedent (Protocols-as-contract, no implementations). The same discipline applied to a different surface.
  - [`../ADRs/0008-no-event-stream-in-phase-2.md`](../ADRs/0008-no-event-stream-in-phase-2.md) — the same deferral pattern: ship the boundary, defer the implementation.
  - [`../ADRs/0003-coordinator-heaviness-sort-annotation.md`](../ADRs/0003-coordinator-heaviness-sort-annotation.md) — `heaviness` is a `@register_probe(heaviness=...)` kwarg, NOT a `Probe` ABC field; registry membership verified via `default_registry._entries`.
- **Source design:**
  - [`../High-level-impl.md` §"Step 6"](../High-level-impl.md) — "opt-in skip-cleanly; allowlist schema lands when the first real user opts in."
  - [`../../localv2.md` §5.4 D8](../../../localv2.md) — the full eventual design (for reference only; Phase 2 ships *none* of it beyond the not-opted-in stub).
- **Probe-shape precedents (post-hardening):**
  - [`./S6-01-skills-index-probe.md`](./S6-01-skills-index-probe.md) (HARDENED) — every Layer-D probe-shape convention: async `run(repo, ctx)`; `_make_context` / `_make_repo` test helpers; flat schema path; `_PROBE_ID: Final[ProbeId]` constant alongside `name: str` ABC attr; `ProbeOutput` six-field shape with `duration_ms` via `time.perf_counter()`; raw artifact written to `ctx.output_dir / "<probe_id>.json"`; the **"absence is the data → `confidence='high'`"** precedent that informs this story's confidence policy.
  - [`./S6-02-conventions-probe.md`](./S6-02-conventions-probe.md) (HARDENED) — same lineage.
  - [`./S6-03-layer-d-marker-probes.md`](./S6-03-layer-d-marker-probes.md) (HARDENED) — same lineage.
- **Existing kernel (the authoritative contract for this probe):**
  - `src/codegenie/probes/base.py` (Phase 0) — `Probe` ABC frozen byte-for-byte against `localv2.md §4`. `name: str` (NOT `probe_id`); `layer`, `tier`; `applies_to_tasks: list[str]` / `applies_to_languages: list[str]` (NOT `tuple`); `requires: list[str]`, `declared_inputs: list[str]`, `timeout_seconds: int`, `cache_strategy: Literal["content","none"]`. `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` — `RepoSnapshot` is the FIRST arg (NOT a `ctx` field). **`ProbeOutput.confidence: Literal["high","medium","low"]`** — `"unavailable"` is NOT a permitted value. `ProbeOutput(schema_slice, raw_artifacts, confidence, duration_ms, warnings, errors)` — six fields, no `probe_id`. `ProbeContext` is a stdlib `@dataclass` with `cache_dir, output_dir, workspace, logger, config` plus three optionals; NO `repo_root`, NO `for_test` classmethod.
  - `src/codegenie/probes/registry.py:238` — `default_registry: Registry`. The "look up heaviness" pattern: `next(e for e in default_registry._entries if e.cls.name == "external_docs").heaviness == "light"`. NO `_PROBE_REGISTRY` dict.
  - `src/codegenie/probes/layer_b/scip_index.py:114` (precedent) — `_PROBE_ID: Final[ProbeId] = ProbeId("scip_index")` module-level constant alongside `name: str = "scip_index"`. Dual-form probe identity (str ABC attr + typed Final constant).
  - `src/codegenie/probes/layer_b/index_health.py:298-326` — canonical full-field ABC declaration including `version`, `layer`, `tier`, `requires`, `timeout_seconds`, `cache_strategy`, `declared_inputs`.
  - `src/codegenie/types/identifiers.py:29` — `ProbeId = NewType("ProbeId", str)`. *NOT `codegenie.ids` — that module does not exist.*
  - `src/codegenie/schema/probes/` — **flat** schema layout. Each sub-schema lands at `src/codegenie/schema/probes/<probe_id>.schema.json` (no `layer_d/` subdir).

## Goal

Implement `src/codegenie/probes/layer_d/external_docs.py` as a `@register_probe(heaviness="light")` probe that:

1. Declares the full frozen Phase-0 `Probe` ABC field set verbatim: `name: str = "external_docs"`, `version: str = "0.1.0"`, `layer = "D"`, `tier = "base"`, `applies_to_tasks: list[str] = ["*"]`, `applies_to_languages: list[str] = ["*"]`, `requires: list[str] = []`, `declared_inputs: list[str] = []`, `timeout_seconds: int = 5`, `cache_strategy: Literal["content"] = "content"`.
2. Declares a module-level `_PROBE_ID: Final[ProbeId] = ProbeId("external_docs")` constant alongside the ABC `name` attr (mirrors `scip_index.py:114`).
3. Implements `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` that **does not read `ctx.config`, does not read `repo.config`, performs no I/O** — Phase 2's path is unconditionally the not-opted-in path. The opted-in branch is deferred until the first real user opts in (final-design Open Q 4); pre-wiring a `config.get(...)` check now is the slippery slope to a real fetcher and is forbidden by AC-7.
4. Returns `ProbeOutput(schema_slice=NotOptedInExternalDocsSlice(opted_in=False, reason="not_opted_in").model_dump(mode="json"), raw_artifacts=[<single JSON>], confidence="high", duration_ms=<perf_counter delta>, warnings=[], errors=[])`. `confidence="high"` because the probe **successfully determined** the feature is not opted in — this is the S6-01 "absence is the data" precedent applied here.
5. Writes a single raw artifact to `ctx.output_dir / "external_docs.json"` containing the JSON-serialized slice (mirrors S6-01 / S6-02 / S6-03 single-raw-artifact discipline).

The module docstring states explicitly that the allowlist schema is deferred per final-design Open Q 4 (the grep-discoverability trip-wire). No HTTP clients, no fetchers, no `httpx`/`requests`/`urllib.request`/`socket`/`aiohttp` imports. No `safe_yaml.load` / `safe_yaml.loads` calls. No `Confluence` / `Notion` / `URLList` / `URLSource` / `FilesystemSource` Pydantic variants — those are the speculative-allowlist anti-pattern AC-7 forbids.

## Acceptance criteria

**Numbered for traceability to the TDD plan.**

### Module layout & types

- [ ] **AC-1.** `src/codegenie/probes/layer_d/external_docs.py` exports exactly `__all__ = ["ExternalDocsProbe", "NotOptedInExternalDocsSlice"]` (alphabetical). The slice is renamed from `ExternalDocsSlice` → `NotOptedInExternalDocsSlice` so the eventual opted-in variant lands as a *new* sibling model (`OptedInExternalDocsSlice`) under the tagged union, never as a backward-compatible additive field on the existing model. This is the extension-by-addition naming discipline the rest of Phase 2 follows (`Fresh` + `Stale` sibling variants, `Pass` + `Fail` + `NotApplicable` sibling variants).
- [ ] **AC-2.** **Module docstring states the deferral explicitly.** The first paragraph of the module docstring contains the exact string `"Phase 2 ships the skip-cleanly stub; the opted-in schema lands when the first real user opts in (final-design.md Open Q 4)"`. An architectural test asserts this — future contributors who add a fetcher without amending the docstring fail the test.
- [ ] **AC-3.** `NotOptedInExternalDocsSlice` is a Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")` carrying exactly two fields:
  - `opted_in: Literal[False]` — the Phase-2 closed discriminator value. The `Literal[False]` choice is load-bearing: it IS the discriminator key for the eventual tagged union `Annotated[NotOptedInExternalDocsSlice | OptedInExternalDocsSlice, Field(discriminator="opted_in")]`. Relaxing to `bool` would silently admit `opted_in=True` slices before the opted-in branch exists in `run`.
  - `reason: Literal["not_opted_in"]` — single-variant in Phase 2; widens to a typed `StrEnum`/`Literal` union if other not-opted-in reasons (e.g., `"config_present_but_empty"`) emerge.
  - When the schema extends to `opted_in: True`, that's a new sibling model + an ADR-amend on `02-ADR-0007` / Phase 0 `fence`, NOT a backward-compatible additive change to this model.

### Probe registration & ABC compliance

- [ ] **AC-4.** `ExternalDocsProbe` is decorated `@register_probe(heaviness="light")` (kwarg form — 02-ADR-0003); class attributes declare the **full frozen Phase-0 `Probe` ABC field set verbatim**:
  - `name: str = "external_docs"` — the ABC field (NOT `probe_id`).
  - `version: str = "0.1.0"`
  - `layer = "D"`
  - `tier = "base"`
  - `applies_to_tasks: list[str] = ["*"]` — `list[str]`, NOT `tuple[str, ...]` (the ABC requires `list`).
  - `applies_to_languages: list[str] = ["*"]` — same.
  - `requires: list[str] = []`
  - `declared_inputs: list[str] = []` — no input files; the probe reads nothing.
  - `timeout_seconds: int = 5`
  - `cache_strategy: Literal["content"] = "content"`

  A module-level `_PROBE_ID: Final[ProbeId] = ProbeId("external_docs")` constant is declared alongside (mirrors `src/codegenie/probes/layer_b/scip_index.py:114`). The `ProbeId` newtype is imported from `codegenie.types.identifiers` — **NOT** `codegenie.ids` (which does not exist).

- [ ] **AC-5.** `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` returns the six-field `ProbeOutput`:
  ```python
  ProbeOutput(
      schema_slice=NotOptedInExternalDocsSlice(opted_in=False, reason="not_opted_in").model_dump(mode="json"),
      raw_artifacts=[ctx.output_dir / "external_docs.json"],
      confidence="high",            # absence is the data; mirrors S6-01 empty-install precedent
      duration_ms=int((time.perf_counter() - t0) * 1000),
      warnings=[],
      errors=[],
  )
  ```
  **`confidence="high"`** (not `"low"`, not `"unavailable"` — the latter is not a permitted `ProbeOutput.confidence` value per `src/codegenie/probes/base.py:68`): the probe successfully determined that the feature is not opted in; the state is in the slice, not in the confidence. **No `repo.config` reads. No `ctx.config` reads. No file I/O beyond the single raw-artifact write described in AC-NEW-1. No network I/O. No `safe_yaml.load` / `safe_yaml.loads`.**

- [ ] **AC-NEW-1.** **Single raw artifact written atomically.** The probe writes the JSON-serialized slice (`json.dumps(slice.model_dump(mode="json"), sort_keys=True, indent=2)`) to `ctx.output_dir / "external_docs.json"` via the `.tmp` → `os.replace` atomic-write pattern (Phase 0 writer chokepoint). `raw_artifacts` is exactly `[ctx.output_dir / "external_docs.json"]` — a one-element list, no other files. Mutation caught: a future contributor adding a `raw/cached_external_docs/<source>.md` body-bytes write would change `raw_artifacts` length and fire the test.

- [ ] **AC-NEW-2.** **`_PROBE_ID: Final[ProbeId]` constant exists.** A module-level `_PROBE_ID: Final[ProbeId] = ProbeId("external_docs")` constant lives alongside the class's `name: str = "external_docs"` ABC attr. The dual-form discipline (str ABC attr + typed `Final[ProbeId]` constant) mirrors `scip_index.py:114` and S6-01 hardening.

### Static integrity & negative invariants

- [ ] **AC-6.** **No forbidden imports.** The probe file does **not** import `httpx`, `requests`, `urllib.request`, `socket`, `aiohttp`, `httplib`, `http.client`, or any HTTP client. Architectural test: parse the module via `ast.parse(inspect.getsource(external_docs))` and assert no `Import`/`ImportFrom` node names any of the forbidden modules. Phase 0's `fence` job catches this too, but this story's test fires in the `unit` lane (faster signal).
- [ ] **AC-7.** **No allowlist schema speculation.** The probe file does NOT define a Pydantic model for an `external_docs:` config entry, an enum of source types, or any `Confluence` / `Notion` / `URLList` / `URLSource` / `FilesystemSource` variants. Architectural test: `inspect.getsource(external_docs)` does not contain any of those substrings.
- [ ] **AC-8.** **Slice sub-schema validates (flat path).** `tests/unit/probes/layer_d/test_external_docs.py::test_slice_matches_subschema` round-trips the slice through `src/codegenie/schema/probes/external_docs.schema.json` (flat layout — no `layer_d/` subdir; sub-schema lands in S6-08). The JSON schema asserts `opted_in` is exactly `false` (`{"const": false}` or `{"enum": [false]}`), `reason` is exactly `"not_opted_in"`, `additionalProperties: false`, and `required: ["opted_in", "reason"]`.

### Registry & determinism

- [ ] **AC-9.** **`heaviness="light"`** — registry-verified via `next(e for e in default_registry._entries if e.cls.name == "external_docs").heaviness == "light"`. (NO `_PROBE_REGISTRY` dict — that name does not exist in the kernel.)
- [ ] **AC-NEW-3.** **Registry membership smoke.** `next((e for e in default_registry._entries if e.cls.name == "external_docs"), None)` is not `None`. Mutation caught: a future contributor removing the `@register_probe` decorator (so the probe silently stops running in every gather) would fire this test.
- [ ] **AC-10.** **Determinism.** Two consecutive `await ExternalDocsProbe().run(repo, ctx)` calls produce byte-identical `schema_slice` JSON; the `raw_artifacts[0]` file contents are byte-identical; no timestamps, no IDs, no per-run nonces. `duration_ms` is excluded from the byte-identity comparison (it varies by clock).

### Quality gates

- [ ] **AC-11.** **`mypy --strict`** passes on the probe module and its test module.
- [ ] **AC-12.** **Phase 0 `fence` re-check.** The CI `fence` job (Phase 0) still passes after this probe lands — no new forbidden imports under `src/codegenie/`. (This is asserted by an existing CI job, not by a per-story test.)
- [ ] **AC-13.** **The deferral is grep-able.** A future Phase-4 contributor running `grep -rn "Open Q 4" src/codegenie/` MUST find this module. The module docstring's exact phrase `final-design.md Open Q 4` is the deliberate trip-wire.
- [ ] **AC-14.** **Two-place documentation invariant.** The architectural test from this story pattern-matches the manifest README (`docs/phases/02-context-gather-layers-b-g/stories/README.md`) for both the substring `"ExternalDocsProbe"` and the substring `"opt-in"` (case-insensitive) to ensure the deferral is documented in two places (probe docstring + manifest). S8-04 (Phase-2 backlog summary) is expected to land a follow-up entry with the same `Open Q 4` reference; that test is owned by S8-04 and is **not** asserted as a precondition here (a forward dependency a Phase-2 story can't validate).

### Extension-by-addition discipline

- [ ] **AC-NEW-4.** **Tagged-union discriminator is `opted_in`.** The module docstring (or a Notes-for-implementer paragraph carried over into the implementation's docstring) explicitly names `opted_in` as the discriminator for the eventual `Annotated[NotOptedInExternalDocsSlice | OptedInExternalDocsSlice, Field(discriminator="opted_in")]` tagged union. An architectural test asserts the module source contains the string `discriminator="opted_in"` (in a comment, docstring, or eventual code) so a future contributor changing the discriminator key trips the test. Mutation caught: someone introducing a `kind: Literal["not_opted_in"]` discriminator instead and silently fragmenting the tagged-union strategy.
- [ ] **AC-NEW-5.** **No subclass-based extension path.** The architectural test asserts the module source does not contain `class OptedInExternalDocsProbe(ExternalDocsProbe)` or any other `class ... (ExternalDocsProbe)` declaration — the eventual opted-in branch is conditional logic dispatching on the discriminator key inside `run` (via `match`), not a subclass. Composition over inheritance; the toolkit's `Inheritance for code reuse` anti-pattern stays caught.

## Implementation outline

1. Create `src/codegenie/probes/layer_d/external_docs.py`:
   - Module docstring with the exact AC-2 phrase, plus pointers to Open Q 4 and 02-ADR-0007, plus an explicit naming of `opted_in` as the eventual tagged-union discriminator (AC-NEW-4).
   - Module-level `_PROBE_ID: Final[ProbeId] = ProbeId("external_docs")` constant (`ProbeId` imported from `codegenie.types.identifiers`).
   - `NotOptedInExternalDocsSlice(BaseModel)` per AC-3 with `model_config = ConfigDict(frozen=True, extra="forbid")`, `opted_in: Literal[False]`, `reason: Literal["not_opted_in"]`.
   - `@register_probe(heaviness="light")` `class ExternalDocsProbe(Probe):`
     - Full frozen ABC field set per AC-4 (`name`, `version`, `layer`, `tier`, `applies_to_*`, `requires`, `declared_inputs`, `timeout_seconds`, `cache_strategy`).
     - `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` returns the not-opted-in slice unconditionally with `confidence="high"` and writes a single raw artifact to `ctx.output_dir / "external_docs.json"` atomically (`.tmp` → `os.replace`).
   - No `repo.config` reads, no `ctx.config` reads, no I/O beyond the single raw-artifact write.
2. Add (or confirm exists) `tests/unit/probes/layer_d/conftest.py` with `_make_repo(tmp_path)` and `_make_context(tmp_path)` helpers (precedent: S6-01 hardening — `ProbeContext` is a stdlib `@dataclass` with no `for_test` classmethod, so the helper is the canonical construction point; if the conftest already exists from S6-01/S6-02/S6-03, this story imports from it rather than redefining).
3. Write `tests/unit/probes/layer_d/test_external_docs.py` per the TDD plan.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/layer_d/external_docs.py` | New file — deferred-implementation stub. |
| `tests/unit/probes/layer_d/test_external_docs.py` | New file — eleven tests, most of which are *negative* (asserting absence of speculation, absence of forbidden imports, absence of subclass-extension paths). |
| `tests/unit/probes/layer_d/conftest.py` | Extend (or confirm-exists from S6-01/02/03) — `_make_repo` and `_make_context` helpers; `_PROJECT_ROOT` constant for the manifest-README test (replaces brittle `Path(__file__).parents[4]` math). |

## TDD plan — red / green / refactor

### Red — write the failing tests first

```python
# tests/unit/probes/layer_d/test_external_docs.py
"""Unit + architectural tests for ExternalDocsProbe (S6-04).

This story's tests are unusual: most ACs are *deferrals* — assertions
about what the probe does NOT do. That's load-bearing per the design's
"Schema before consumer" discipline: an opted-in schema with no Phase 2
consumer would be premature.
"""
from __future__ import annotations

import asyncio
import ast
import inspect
import json
from importlib.resources import files
from pathlib import Path

import jsonschema
import pydantic
import pytest

from codegenie.probes.layer_d import external_docs as ed
from codegenie.probes.registry import default_registry

# `_make_repo` and `_make_context` live in tests/unit/probes/layer_d/conftest.py
# (or tests/unit/probes/conftest.py); both follow the S6-01 hardening precedent.
# `_PROJECT_ROOT` is a module-level constant in the conftest (or computed via
# `Path(codegenie.__file__).parents[2]`) — never `Path(__file__).parents[N]`,
# which is brittle against test-tree moves.


def test_run_returns_high_confidence_not_opted_in_by_default(
    tmp_path: Path, _make_repo, _make_context,
) -> None:
    """AC-5. Mutation caught: a future "if external_docs key present: fetch …"
    path that ships without an ADR — the test pins the skip-cleanly default
    AND pins the `confidence="high"` policy (absence is the data; mirrors
    S6-01 empty-install precedent). Catching a regression that flips
    confidence to "low" (which would signal "we tried and failed") is the
    load-bearing semantic the test protects.
    """
    repo = _make_repo(tmp_path)
    ctx = _make_context(tmp_path)
    output = asyncio.run(ed.ExternalDocsProbe().run(repo, ctx))
    assert output.confidence == "high"
    slice_ = ed.NotOptedInExternalDocsSlice.model_validate(output.schema_slice)
    assert slice_.opted_in is False
    assert slice_.reason == "not_opted_in"
    assert output.errors == []
    assert output.warnings == []
    assert output.raw_artifacts == [ctx.output_dir / "external_docs.json"]
    assert output.duration_ms >= 0


def test_module_docstring_contains_open_q_4_phrase() -> None:
    """AC-2, AC-13. Mutation caught: a future contributor adding a
    fetcher and removing the deferral docstring — the explicit phrase
    is the grep-discoverability trip-wire."""
    assert ed.__doc__ is not None
    expected = (
        "Phase 2 ships the skip-cleanly stub; the opted-in schema lands when "
        "the first real user opts in (final-design.md Open Q 4)"
    )
    assert expected in ed.__doc__


def test_module_docstring_names_opted_in_discriminator(tmp_path: Path) -> None:
    """AC-NEW-4. Mutation caught: a future contributor changing the
    discriminator key from `opted_in` to e.g. `kind` would silently
    fragment the Phase-4 tagged-union strategy. The grep token
    `discriminator="opted_in"` is the load-bearing trip-wire."""
    src = inspect.getsource(ed)
    assert 'discriminator="opted_in"' in src, (
        "Module must explicitly name `opted_in` as the eventual tagged-union "
        "discriminator key (in a comment, docstring, or code) per AC-NEW-4."
    )


def test_no_subclass_extension_path() -> None:
    """AC-NEW-5. Mutation caught: a future contributor introducing
    `class OptedInExternalDocsProbe(ExternalDocsProbe): ...` would
    fragment the dispatch into a class hierarchy; the eventual
    opted-in branch is conditional `match` dispatch inside `run`,
    not inheritance."""
    src = inspect.getsource(ed)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = [b for b in node.bases if isinstance(b, ast.Name)]
            assert all(
                b.id != "ExternalDocsProbe" for b in bases
            ), f"Subclass {node.name!r} of ExternalDocsProbe violates AC-NEW-5"


def test_no_forbidden_http_or_socket_imports() -> None:
    """AC-6. Mutation caught: any `import httpx` (or aiohttp, requests,
    urllib.request, socket, http.client) — Phase 0's fence job would
    also catch this, but the test fires in the `unit` lane for fast
    signal."""
    forbidden = {
        "httpx", "requests", "urllib.request", "aiohttp",
        "socket", "http.client", "httplib",
    }
    tree = ast.parse(inspect.getsource(ed))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    assert not (forbidden & names), f"Forbidden imports found: {forbidden & names}"


def test_no_speculative_allowlist_schema() -> None:
    """AC-7. Mutation caught: a future contributor adding `Confluence`,
    `NotionSource`, or `URLList` Pydantic variants before the first
    real user opts in — the "Schema before consumer" anti-pattern."""
    src = inspect.getsource(ed)
    speculative = (
        "Confluence", "Notion", "URLList", "URLSource",
        "FilesystemSource", "OptedInExternalDocsSlice",
    )
    for token in speculative:
        assert token not in src, (
            f"{token!r} suggests a speculative allowlist schema. The schema "
            "lands when the first real user opts in (final-design Open Q 4)."
        )


def test_slice_rejects_opted_in_true_at_pydantic_level() -> None:
    """AC-3. Mutation caught: relaxing `opted_in: Literal[False]` to
    `bool` would silently accept a True value before the opted-in
    branch exists in `run` — the validation error is the type-level
    enforcement of the discriminator-key invariant."""
    with pytest.raises(pydantic.ValidationError):
        ed.NotOptedInExternalDocsSlice(opted_in=True, reason="not_opted_in")  # type: ignore[arg-type]


def test_slice_rejects_extra_fields() -> None:
    """AC-3. Mutation caught: a future contributor adding a
    `fetched_count` field before the opted-in shape is defined."""
    with pytest.raises(pydantic.ValidationError):
        ed.NotOptedInExternalDocsSlice(
            opted_in=False,
            reason="not_opted_in",
            fetched_count=0,  # type: ignore[call-arg]
        )


def test_two_consecutive_runs_byte_identical(
    tmp_path: Path, _make_repo, _make_context,
) -> None:
    """AC-10. Mutation caught: any timestamp / nonce / per-run ID in
    the not-opted-in slice (or the raw artifact) would diverge on the
    second run. `duration_ms` is intentionally excluded — it varies by
    clock and is asserted only `>= 0` in the happy-path test."""
    repo = _make_repo(tmp_path)
    ctx = _make_context(tmp_path)
    out1 = asyncio.run(ed.ExternalDocsProbe().run(repo, ctx))
    out2 = asyncio.run(ed.ExternalDocsProbe().run(repo, ctx))
    assert json.dumps(out1.schema_slice, sort_keys=True) == json.dumps(
        out2.schema_slice, sort_keys=True,
    )
    # Raw-artifact byte-identity follows from sort_keys=True, indent=2 in the
    # writer; the file was overwritten by run #2, so we re-read.
    raw_bytes = (ctx.output_dir / "external_docs.json").read_bytes()
    assert json.loads(raw_bytes) == out2.schema_slice


def test_registry_heaviness_is_light() -> None:
    """AC-9. Mutation caught: bumping heaviness for a probe that does
    no work would mis-budget the coordinator."""
    entry = next(
        e for e in default_registry._entries
        if e.cls.name == "external_docs"
    )
    assert entry.heaviness == "light"


def test_registry_membership_present() -> None:
    """AC-NEW-3. Mutation caught: a future contributor removing the
    @register_probe decorator so the probe silently stops running in
    every gather."""
    entry = next(
        (e for e in default_registry._entries if e.cls.name == "external_docs"),
        None,
    )
    assert entry is not None, (
        "ExternalDocsProbe must be in default_registry._entries; "
        "@register_probe(heaviness='light') decorator is load-bearing"
    )


def test_probe_id_constant_exists() -> None:
    """AC-NEW-2. Mutation caught: a future contributor removing the
    module-level _PROBE_ID Final constant (breaking the dual-form
    probe-identity convention S6-01/02/03 established)."""
    from codegenie.types.identifiers import ProbeId
    assert hasattr(ed, "_PROBE_ID")
    assert ed._PROBE_ID == ProbeId("external_docs")
    assert ed.ExternalDocsProbe.name == "external_docs"


def test_slice_matches_subschema_with_strict_additional_properties() -> None:
    """AC-8. Mutation caught: a future schema that admits `opted_in: true`
    without an ADR — the schema is the contract. Flat schema layout per
    S6-01 AC-19 / S6-03 hardening precedent."""
    schema = json.loads(
        (files("codegenie.schema.probes") / "external_docs.schema.json").read_text()
    )
    good = {"opted_in": False, "reason": "not_opted_in"}
    jsonschema.validate(good, schema)
    bad_opted_in = {"opted_in": True, "reason": "not_opted_in"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad_opted_in, schema)
    bad_extra = {"opted_in": False, "reason": "not_opted_in", "fetched_count": 0}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad_extra, schema)


def test_manifest_readme_documents_deferral(_project_root: Path) -> None:
    """AC-14. Mutation caught: removing the deferral note from the
    manifest's "Decisions noted" section — the deferral lives in two
    places (probe docstring + manifest) so neither alone can drop the
    discipline silently. `_project_root` fixture (from conftest.py)
    replaces the brittle `Path(__file__).parents[4]` math."""
    manifest = (
        _project_root / "docs" / "phases" /
        "02-context-gather-layers-b-g" / "stories" / "README.md"
    )
    assert manifest.exists(), f"manifest not found at {manifest}"
    text = manifest.read_text()
    assert "ExternalDocsProbe" in text
    assert "opt-in" in text.lower() or "opted_in" in text.lower()


def test_run_performs_no_repo_or_ctx_config_reads(
    tmp_path: Path, _make_repo, _make_context,
) -> None:
    """AC-5 (negative side). Mutation caught: a future contributor
    pre-wiring `repo.config.get("external_docs")` as a "harmless check
    that does nothing yet" — that's the slippery slope to a real
    fetcher. The probe must be unconditionally inert in Phase 2."""
    repo = _make_repo(tmp_path)
    # Inject a config key that would tempt a fetcher; the probe MUST ignore it.
    repo.config["external_docs"] = {"sources": [{"type": "confluence", "url": "x"}]}
    ctx = _make_context(tmp_path)
    output = asyncio.run(ed.ExternalDocsProbe().run(repo, ctx))
    # Despite the config being present, the probe still emits the not-opted-in
    # slice — there is no Phase 2 config-key handling path. The presence of the
    # key is *user error*; the absence of any read on `repo.config["external_docs"]`
    # in module source backstops this:
    slice_ = ed.NotOptedInExternalDocsSlice.model_validate(output.schema_slice)
    assert slice_.opted_in is False
    # Static backstop: the literal string "external_docs" appears only as the
    # probe name / id / docstring / schema reference — NEVER as a `.config.get`
    # / `.config[` access. (Module-source grep is appropriate here per S5-03
    # AST-walk precedent — a behavioral assertion would be circular.)
    src = inspect.getsource(ed)
    assert ".config.get(\"external_docs\"" not in src
    assert ".config[\"external_docs\"" not in src
    assert ".config['external_docs'" not in src
```

### Green — make it pass

```python
# src/codegenie/probes/layer_d/external_docs.py
"""ExternalDocsProbe — Layer D, light heaviness, deferred-implementation stub.

Phase 2 ships the skip-cleanly stub; the opted-in schema lands when
the first real user opts in (final-design.md Open Q 4). The probe is
registered so it runs in every gather and emits a typed
NotOptedInExternalDocsSlice with `opted_in=False, reason="not_opted_in"`
and `confidence="high"` (the absence-is-the-data precedent from S6-01).
The probe performs no I/O beyond writing a single canonical raw artifact
to `ctx.output_dir / "external_docs.json"`, no network calls, no config
reads.

Discriminator key for the eventual tagged union: `discriminator="opted_in"`.
The Phase-4+ opted-in variant lands as a *new* sibling Pydantic model
(`OptedInExternalDocsSlice`) joined under
`Annotated[NotOptedInExternalDocsSlice | OptedInExternalDocsSlice,
Field(discriminator="opted_in")]`, dispatched via `match` on
`repo.config.get("external_docs")` inside `run` — never via subclass.

When a future user wants Confluence / Notion / URL-list integration:

1. ADR-amend on the `external_docs:` allowlist schema (host list +
   credential plumbing + size cap).
2. ADR-amend on Phase 0's `fence` job to permit an HTTP client.
3. Add a new sibling `OptedInExternalDocsSlice` Pydantic model; widen
   the public `ExternalDocsSlice` to the tagged union (no edits to
   `NotOptedInExternalDocsSlice`).
4. Implement the opted-in branch as a `match` arm in `run`.

NONE of those four steps happens in Phase 2. This module is
deliberately inert.

Sources:
- ../final-design.md Open Q 4.
- ../phase-arch-design.md §"Open questions deferred to implementation" #4.
- ../ADRs/0007-no-plugin-loader-in-phase-2.md (the canonical "ship the
  boundary, defer the implementation" precedent).
"""
from __future__ import annotations

import json
import os
import time
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from codegenie.probes.base import (
    Probe,
    ProbeContext,
    ProbeOutput,
    RepoSnapshot,
)
from codegenie.probes.registry import register_probe
from codegenie.types.identifiers import ProbeId

__all__ = ["ExternalDocsProbe", "NotOptedInExternalDocsSlice"]

_PROBE_ID: Final[ProbeId] = ProbeId("external_docs")


class NotOptedInExternalDocsSlice(BaseModel):
    """Phase-2 closed shape — the not-opted-in variant of the eventual
    tagged union `Annotated[NotOptedInExternalDocsSlice |
    OptedInExternalDocsSlice, Field(discriminator="opted_in")]`."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    opted_in: Literal[False]
    reason: Literal["not_opted_in"]


@register_probe(heaviness="light")
class ExternalDocsProbe(Probe):
    name: str = "external_docs"
    version: str = "0.1.0"
    layer = "D"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    declared_inputs: list[str] = []
    timeout_seconds: int = 5
    cache_strategy: Literal["content"] = "content"

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        slice_ = NotOptedInExternalDocsSlice(opted_in=False, reason="not_opted_in")
        payload = slice_.model_dump(mode="json")

        # Atomic write — Phase 0 writer chokepoint discipline.
        out_path = ctx.output_dir / "external_docs.json"
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

### Refactor

- The probe is deliberately a one-liner-style stub. Resist refactoring it into a "base" class that the opted-in version will subclass — that's the same speculative-coupling failure mode AC-7 / AC-NEW-5 forbid. When the opted-in branch lands, it lands as **tagged-union dispatch via exhaustive `match`** inside `run`:

  ```python
  async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
      match repo.config.get("external_docs"):
          case None | {}:
              return await _emit_not_opted_in(ctx)
          case {"sources": _}:
              return await _emit_opted_in(repo, ctx)
          case other:
              assert_never(other)  # malformed config → typed error
  ```

  `_emit_not_opted_in` and `_emit_opted_in` are module-level free functions (functional-core / imperative-shell discipline). The opted-in branch's HTTP fetcher lands as a separate sibling module (`_external_docs_fetcher.py`), preserving the file-boundary Open/Closed seam (touch this file to register the new arm; touch the sibling module to implement the new behavior).

- Do not extract a shared "deferred stub" base class even if a second deferred-stub probe lands later. Rule-of-three holds: at three deferred stubs, revisit; until then, three similar deferred-stub modules (each ≤ 30 LOC) are cheaper than one shared abstraction that pre-decides what they have in common (CLAUDE.md Rule 2: "three similar lines is better than a premature abstraction").

## Out of scope

- **The opted-in `external_docs:` schema.** Phase 4-or-later, gated by ADR-amend on the fence job + at least one real user opting in.
- **HTTP clients, Confluence/Notion API clients, BM25 indexing.** All deferred.
- **`ExternalDocsIndexProbe` (D9 in localv2.md).** Lands with the opt-in flow; there is no Phase-2 consumer.
- **Per-source-type Pydantic variants.** Picking a discriminated union shape before a real user opts in is exactly the "Schema before consumer" anti-pattern.

## Notes for the implementer

1. **The negative tests are doing real work.** A test that says "no `Confluence` substring" looks paranoid; it isn't. The Phase-2 design table calls out "Schema before consumer" as a flag-on-sight anti-pattern, and a speculative Confluence variant is the textbook example. The test fires the moment a contributor types `class Confluence...` — long before review can catch it.
2. **`Literal[False]` is the load-bearing type AND the discriminator key for the eventual tagged union.** A future contributor relaxing to `bool` would silently allow an `opted_in: True` slice through Pydantic, but the `run` method would still return `opted_in=False` — the test catches the type relaxation directly. When the opted-in branch eventually lands, the migration is: keep `NotOptedInExternalDocsSlice` unchanged (Open/Closed); add a sibling `OptedInExternalDocsSlice` with `opted_in: Literal[True]`; widen the public `ExternalDocsSlice` to `Annotated[NotOptedInExternalDocsSlice | OptedInExternalDocsSlice, Field(discriminator="opted_in")]`. The discriminator key choice (`opted_in`) is the **only** schema commitment Phase 2 makes — making it now means the future tagged-union widening is mechanical.
3. **The docstring phrase is grep-bait.** `grep -rn "Open Q 4" src/codegenie/` MUST find this module after this story lands. Phase-4 contributors will run that grep when they pick up the deferred work; the discoverability is the contract.
4. **No `safe_yaml.load`, no `repo.config` reads, no `ctx.config` reads.** This probe reads NOTHING from the configuration surfaces. If a future contributor's gut reaction is "let me at least check if the config key exists" — resist. That's the slippery slope to a real fetcher. The opted-in branch reads config *and* fetches; either you ship both with an ADR-amend or you ship neither. AC-5's negative test (`.config.get("external_docs"` and friends NOT in module source) backstops this with a static check.
5. **`confidence="high"` is the right level — absence is the data.** Mirrors the S6-01 empty-install hardening precedent: when a probe successfully determines that a feature/install/state isn't present, that determination is itself the high-confidence finding. Not `"low"` (which signals "we tried and got weak data"). Not `"unavailable"` — that value does not exist in the kernel `ProbeOutput.confidence: Literal["high","medium","low"]` (Phase 0 ADR-0007 frozen surface). The probe successfully reports "feature is off"; the slice carries the state; confidence reports the quality of the determination.
6. **Null Object + tagged-union discriminator + Open/Closed at file boundary — name the patterns explicitly.** The probe is a **Null Object** for Phase 2 (satisfies the `Probe` ABC so the coordinator / renderer / Planner consume it without special-casing). The slice carries the **tagged-union discriminator key** for the eventual Phase-4 widening. The future opted-in branch lands as a *new* sibling model + *new* free function via **Open/Closed at the file boundary** — `run` dispatches via exhaustive `match`, never via subclass. Naming these patterns in the docstring is what makes the design legible to a Phase-4 contributor without requiring them to reverse-engineer the intent.
7. **`async def run(self, repo, ctx)` — NOT `_run(self, ctx)`.** Phase 0 ADR-0007 freezes the ABC byte-for-byte against `localv2.md §4`: `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`. The `repo` is the first positional arg (not a `ctx` field); the method is public (`run`), not `_run`. Tests use `asyncio.run(probe.run(repo, ctx))` (precedent: `tests/unit/probes/layer_b/test_dep_graph.py`). The `_make_repo` / `_make_context` helpers in `tests/unit/probes/layer_d/conftest.py` are the canonical construction points — `ProbeContext` is a stdlib `@dataclass` with no `for_test` classmethod.
8. **`name: str = "external_docs"` ABC attr + `_PROBE_ID: Final[ProbeId]` module constant — the dual-form identity.** S6-01 / S6-02 / S6-03 settled this convention: the ABC field is `name: str` (frozen, stringly-typed for ABC compatibility); the module-level `_PROBE_ID: Final[ProbeId]` constant carries the typed `NewType`-wrapped identifier for any in-module use. `ProbeId` is imported from `codegenie.types.identifiers` — `codegenie.ids` does not exist (it's a recurring documentation drift other Layer-D story drafts also hit).
9. **`tuple[str, ...]` for `applies_to_*` is wrong — use `list[str]`.** The ABC declares `applies_to_tasks: list[str]` and `applies_to_languages: list[str]`. A `tuple` annotation contradicts the contract and will fail the `tests/unit/test_probe_contract.py` snapshot.
10. **Atomic write via `.tmp` → `os.replace` is the Phase 0 chokepoint.** Don't `Path.write_text(out_path, ...)` directly; use the same `.tmp` → `os.replace` pattern other probes use (precedent: any `*_writer.py` / probe in the codebase that writes a raw artifact). The byte-identity test depends on this.
11. **AC-14's two-place documentation is anti-fragile.** A future contributor deleting the docstring deferral *or* removing the manifest entry would have to update both. The probability of a contributor doing both deliberately (vs. silently in a refactor) is much lower; the test fires the moment one or the other goes stale.
12. **Phase 0 ADR-0007 freezes the `Probe` ABC. The full field set is mandatory.** Phase-0 contract-freeze means `tests/unit/test_probe_contract.py` regenerates when a Phase ADR adds a documented optional field — but every probe must still declare the full field set (`version`, `layer`, `tier`, `applies_to_*`, `requires`, `declared_inputs`, `timeout_seconds`, `cache_strategy`). The canonical full-field reference is `src/codegenie/probes/layer_b/index_health.py:308-325`; mirror it exactly.
