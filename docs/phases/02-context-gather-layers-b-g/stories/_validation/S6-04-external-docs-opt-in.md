# Validation report: S6-04 — `ExternalDocsProbe` opt-in skip-cleanly stub

**Validated:** 2026-05-17
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Story:** [`../S6-04-external-docs-opt-in.md`](../S6-04-external-docs-opt-in.md)

## Summary

S6-04's *intent* (a Layer-D probe that ships the boundary now and defers the opted-in implementation until a real user opts in, per final-design Open Q 4 + 02-ADR-0007's "ship the boundary, defer the implementation" precedent) is well-formed and traces cleanly to the architecture. The original draft, however, contradicted the actual frozen Phase-0 `Probe` ABC (`src/codegenie/probes/base.py:52-96`) and the kernel registry (`src/codegenie/probes/registry.py:131-238`) at **nine** load-bearing points — every one a `block`-severity contract mismatch that would have made the story uncompilable against the existing codebase. Eight of the nine are the same systemic mismatches S6-01 / S6-02 / S6-03 went through hardening to fix (story-authoring drift between the kernel snapshot and the ABC S2-01 actually shipped). The ninth is **unique to this story and is the largest structural fix**: the original draft built every AC and every test around `confidence="unavailable"`, but `ProbeOutput.confidence` is `Literal["high","medium","low"]` (Phase 0 ADR-0007 frozen surface, `base.py:68`) — `"unavailable"` is not a permitted value. The harden re-routes the semantics through S6-01's "absence is the data → `confidence='high'`" precedent: the probe successfully **determined** that the feature is not opted in (that's a high-confidence determination), and the state lives in the typed slice (`opted_in: Literal[False]`, `reason: Literal["not_opted_in"]`), not in the confidence field. This preserves the original story's intent (skip-cleanly default; no I/O; no speculation) while making the implementation buildable against the actual kernel.

Twenty in-place edits applied. Five new ACs cover gaps the original draft missed:

- **AC-NEW-1** — single raw artifact written atomically to `ctx.output_dir / "external_docs.json"` (mirrors S6-01/02/03 single-raw-artifact discipline; `raw_artifacts` list-length is an observable mutation-resistance gate).
- **AC-NEW-2** — `_PROBE_ID: Final[ProbeId]` module-level constant exists (dual-form identity discipline from `scip_index.py:114`; preserves the typed `NewType` even though the ABC field is stringly-typed).
- **AC-NEW-3** — registry-membership smoke (a future contributor removing the `@register_probe` decorator would silently stop the probe from running in every gather; this test is the trip-wire).
- **AC-NEW-4** — tagged-union discriminator key (`opted_in`) is named in the module source as a grep-discoverable trip-wire; future contributors changing the discriminator key trip the test.
- **AC-NEW-5** — no subclass-based extension path (`class OptedInExternalDocsProbe(ExternalDocsProbe)` is forbidden via AST walk; the eventual opted-in branch must be `match`-dispatched conditional logic, not inheritance).

Three design-pattern hardens were applied:

1. The Phase-2 slice was renamed `ExternalDocsSlice` → `NotOptedInExternalDocsSlice` so the eventual opted-in variant lands as a *new sibling model* under a tagged union (`Annotated[NotOptedInExternalDocsSlice | OptedInExternalDocsSlice, Field(discriminator="opted_in")]`) — not as a backward-compatible additive field on the existing model. This is the **Open/Closed at the file boundary** discipline the rest of Phase 2 follows (`Fresh` + `Stale` sibling variants, `Pass` + `Fail` + `NotApplicable` sibling variants).
2. The Notes-for-implementer section explicitly names the three design patterns the probe deploys: **Null Object** (satisfies the ABC so consumers don't special-case), **Tagged union via discriminator** (`opted_in` is the key choice; Phase 2 makes the discriminator-key commitment now), and **Open/Closed at file boundary** (future opted-in branch lands via `match` dispatch + new sibling free function `_emit_opted_in`, never via subclass).
3. The Refactor section now shows the exact pattern the Phase-4+ extension follows — `match repo.config.get("external_docs"): case None | {}: …; case {"sources": _}: …; case other: assert_never(other)` — so a Phase-4 contributor reading this story has a typed blueprint, not just a prohibition.

The manifest entry in [`../README.md`](../README.md) line 194 was updated in lock-step to reflect the corrected `confidence="high"` semantics; AC-14's two-place documentation invariant would otherwise have caught the drift on first executor run.

No `NEEDS RESEARCH` findings — every gap traced to in-repo precedent: `src/codegenie/probes/base.py:68` for the frozen `confidence` Literal; `src/codegenie/probes/layer_b/index_health.py:298-326` for the canonical full-field ABC declaration; S6-01 / S6-02 / S6-03 validation reports for the contract-fix lineage; `src/codegenie/probes/layer_b/scip_index.py:114` for the `_PROBE_ID: Final[ProbeId]` dual-form discipline; `src/codegenie/types/identifiers.py:29` for the correct `ProbeId` import path.

## Context Brief (Stage 1)

### Story snapshot

- **Goal:** Land `src/codegenie/probes/layer_d/external_docs.py` as a `@register_probe(heaviness="light")` probe that is **registered and runs in every gather** but performs no I/O — emits a typed `NotOptedInExternalDocsSlice` with `opted_in=False, reason="not_opted_in"` and `confidence="high"`. The probe holds the shape of the eventual opted-in variant via the `opted_in` discriminator key but ships none of the opted-in logic in Phase 2.
- **Non-goals:** HTTP fetchers; Confluence / Notion / URL-list / Filesystem variants; `external_docs:` config schema; BM25 indexing (D9 — deferred with the opt-in flow); `ExternalDocsIndexProbe`.
- **Effort:** S.
- **Depends on:** S6-03 (Layer-D probe-shape; `_make_repo` / `_make_context` test helpers; flat schema path; `_PROBE_ID: Final[ProbeId]` discipline; three-state confidence with "absence is the data → `confidence='high'`" precedent from S6-01).

### Phase / arch constraints touched

- **Phase 0 ADR-0007** — `Probe` ABC frozen byte-for-byte against `localv2.md §4`. `confidence: Literal["high","medium","low"]`. `async def run(self, repo, ctx)`. Six-field `ProbeOutput` with no `probe_id`. `ProbeContext` is stdlib `@dataclass`.
- **02-ADR-0003** — `@register_probe(heaviness=…)` is a registry kwarg; not an ABC field.
- **02-ADR-0005** — no plaintext persistence (this probe writes no body content — it has nothing to write — so the invariant holds trivially).
- **02-ADR-0007** — the canonical "ship the boundary, defer the implementation" precedent. Adapter Protocols are shipped without implementations; this probe is shipped without an opted-in branch. Same discipline.
- **02-ADR-0008** — no event stream; the probe emits a typed slice via `schema_slice`, not events.
- **final-design Open Q 4** — `ExternalDocsProbe` enablement deferred; allowlist schema lands when first real user opts in.
- **phase-arch-design "Anti-patterns avoided" "Schema before consumer"** — every typed sum has a Phase-2 consumer; the opted-in variant has no Phase-2 consumer.
- **CLAUDE.md "Extension by addition"** — adding the opted-in variant later must not require editing `NotOptedInExternalDocsSlice` or the existing `run` body's not-opted-in branch.
- **CLAUDE.md "Honest confidence"** — `confidence="high"` accurately reports the determination quality; the *state* lives in the slice.

### Sibling-family lineage

- **4th Layer-D probe** after S6-01 (skills_index), S6-02 (conventions), S6-03 (marker probes — adrs, repo_notes, repo_config, policy, exceptions). All three preceding stories went through validator hardening that fixed the same systemic kernel-contract drift (S6-01: twelve `block` mismatches; S6-02: thirteen; S6-03: eighteen). This story has nine — fewer than the preceding ones because the probe is structurally simpler (no loader, no I/O, no per-file errors).
- **First Layer-D "deferred stub" probe.** The Rule-of-Three for extracting a shared "deferred stub" base class has not triggered. Notes-for-implementer §6 documents the trigger condition (three deferred stubs in Layer D, *then* revisit).
- **Functional-core precedent.** S6-01/02/03 settled the functional-core / imperative-shell split (pure module-level free helpers; `run` is the imperative shell). This story inherits the discipline trivially — the probe IS pure (no `ctx.config` reads, no I/O beyond a single atomic write).

### Prior validation framings carried forward

- **S6-03 hardening:** the contract-drift lineage; tuple→list `applies_to_*`; `name: str` (not `probe_id`); `default_registry._entries` (not `_PROBE_REGISTRY`); `codegenie.types.identifiers` (not `codegenie.ids`); flat schema path; `_PROBE_ID: Final[ProbeId]` dual-form; six-field `ProbeOutput`; `async def run(repo, ctx)`. Every one of these is fixed identically in S6-04.
- **S6-01 hardening:** "absence is the data → `confidence='high'`" precedent. Empty install / not-opted-in / null-shape states are *successful determinations*, not failures-to-determine. The confidence field reports determination quality; the slice carries state.
- **S5-04 hardening:** mutation-resistance via parametrized smoke; `Final[...]` discipline. S6-04 mirrors via `_PROBE_ID: Final[ProbeId]` and the static-source AST/grep checks.
- **S5-03 hardening:** AST-walk audits supersede source-grep for behavioral assertions. S6-04's `test_no_subclass_extension_path` uses an AST walk (not a grep) because the question is structural ("does any class subclass `ExternalDocsProbe`?"), not lexical.

### Phase exit criteria the story contributes to

- **High-level-impl.md §"Step 6"** — `external_docs.py` ships opt-in skip-cleanly.
- **final-design Open Q 4** — Phase 2 commits to the deferred boundary; Phase 4+ owns the opted-in implementation.
- **CLAUDE.md "Extension by addition"** — the discriminator-key commitment + tagged-union sibling-model discipline operationalize the load-bearing commitment.

### Open ambiguities discovered during Stage 1

- **`confidence="unavailable"` doesn't exist.** Original AC-5 specified `confidence="unavailable"`. The ABC's `ProbeOutput.confidence: Literal["high","medium","low"]` (Phase 0 ADR-0007, `base.py:68`) forbids it. **Resolved at synthesis:** rewrite AC-5 to `confidence="high"` (absence-is-the-data, mirrors S6-01 empty-install). Slice carries `opted_in=False, reason="not_opted_in"`. Update the manifest README to match.
- **`_run(ctx)` doesn't exist.** Original draft specifies `_run(self, ctx)` (sync, private, takes only ctx). Actual ABC is `async def run(self, repo, ctx)`. **Resolved at synthesis:** rewrite AC-5 + GREEN + every test to `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`; tests use `asyncio.run(probe.run(repo, ctx))`.
- **`probe_id = ProbeId(...)` class attr doesn't fit the ABC.** Original AC-4 uses `probe_id` as a class attr. ABC uses `name: str`. **Resolved at synthesis:** rewrite AC-4 to `name: str = "external_docs"` ABC attr + module-level `_PROBE_ID: Final[ProbeId] = ProbeId("external_docs")` (mirrors S6-01/02/03 hardening).
- **`tuple[str, ...]` for `applies_to_*` contradicts ABC.** Original AC-4 specifies `tuple`. ABC requires `list[str]`. **Resolved at synthesis:** rewrite to `list[str] = ["*"]`.
- **`from codegenie.ids import ProbeId` — `codegenie.ids` doesn't exist.** Recurring documentation drift; correct path is `codegenie.types.identifiers`. **Resolved at synthesis:** import path corrected in GREEN.
- **`_PROBE_REGISTRY` doesn't exist.** Original tests reference `_PROBE_REGISTRY["external_docs"]`. Actual registry is `default_registry._entries: list[ProbeRegEntry]` at `registry.py:238`. **Resolved at synthesis:** `next(e for e in default_registry._entries if e.cls.name == "external_docs")`.
- **Schema layout is flat, not nested.** Original AC-8 references `src/codegenie/schema/probes/layer_d/external_docs.schema.json`. Actual layout is flat. **Resolved at synthesis:** flat path `src/codegenie/schema/probes/external_docs.schema.json`; `files("codegenie.schema.probes") / "external_docs.schema.json"`.
- **`ProbeOutput(probe_id=..., …)` doesn't fit the dataclass.** Original GREEN constructs `ProbeOutput` with `probe_id` and only three fields; actual `ProbeOutput` has six required fields: `schema_slice, raw_artifacts, confidence, duration_ms, warnings, errors`. **Resolved at synthesis:** GREEN rewritten with all six fields; `duration_ms` via `time.perf_counter()`.
- **`ProbeContext.for_test(repo_root=…)` doesn't exist.** `ProbeContext` is a stdlib `@dataclass` with no classmethods and no `repo_root` field (fields: `cache_dir, output_dir, workspace, logger, config` + three optionals). **Resolved at synthesis:** introduce `_make_repo` / `_make_context` helpers in `tests/unit/probes/layer_d/conftest.py` (precedent: S6-01 hardening). `repo` is built from `RepoSnapshot(root, git_commit, detected_languages, config)`.
- **Original AC-NEW design opportunity (Open/Closed at file boundary).** The Phase-4+ opted-in branch should land via *tagged-union dispatch in the same file* (new sibling slice model; new free function; new `match` arm), not via subclass. The original draft's refactor section forbade "class hierarchy" but didn't *name* the pattern. **Resolved at synthesis:** rename Phase-2 slice to `NotOptedInExternalDocsSlice`; explicitly name the eventual tagged union; add AC-NEW-4 (discriminator key in source) + AC-NEW-5 (no subclass extension); document the `match` dispatch in the Refactor section.

## Findings by critic

### Coverage critic (K)

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| K1 | block | AC-5 specifies `confidence="unavailable"` — not a permitted `ProbeOutput.confidence` value. Every test built on this AC would fail at import or at runtime. | Rewrite AC-5 to `confidence="high"` with rationale: absence is the data; state lives in the typed slice (`opted_in: Literal[False]`, `reason: Literal["not_opted_in"]`); confidence reports the *quality of the determination*. Mirrors S6-01 empty-install hardening. Update manifest README line 194 in lock-step. |
| K2 | harden | No AC for the single raw artifact written under `ctx.output_dir / "external_docs.json"`. S6-01/02/03 all land this; a future contributor "optimizing" by skipping the raw-artifact write would silently break the cache-key / golden-file pipeline. | New AC-NEW-1: `raw_artifacts == [ctx.output_dir / "external_docs.json"]`; file is the JSON-serialized slice written atomically via `.tmp` → `os.replace`. |
| K3 | harden | No AC for `_PROBE_ID: Final[ProbeId]` module constant. S6-01/02/03 settled the dual-form identity convention; missing here. | New AC-NEW-2: module-level `_PROBE_ID: Final[ProbeId] = ProbeId("external_docs")` alongside the class `name: str` ABC attr. |
| K4 | harden | No AC asserts the probe is actually in `default_registry._entries` (membership smoke). A future contributor removing the `@register_probe` decorator would silently stop the probe from running in every gather; the only enforcement is the runtime behavior, which no test currently exercises. | New AC-NEW-3: registry membership smoke. |
| K5 | harden | The "no speculative allowlist schema" AC is good but doesn't cover the *eventual* tagged-union discriminator key choice — the load-bearing commitment Phase 2 IS making. Without an AC, a future contributor could change the discriminator key to e.g. `kind` and silently fragment the Phase-4 widening. | New AC-NEW-4: module source contains the literal `discriminator="opted_in"` (in code, comment, or docstring) as the grep-discoverable trip-wire. |
| K6 | harden | The Refactor section says "not a class hierarchy" but no AC enforces it. A future contributor introducing `class OptedInExternalDocsProbe(ExternalDocsProbe)` would only be caught at code review. | New AC-NEW-5: AST walk forbids any `class X(ExternalDocsProbe)` declaration in the module. |
| K7 | harden | AC-14's S8-04 dependency is a forward reference — a Phase-2 story can't assert on a downstream artifact. | Soften AC-14: assert only the manifest README two-place documentation (which exists now); the S8-04 backlog entry is owned by S8-04 and is a documentation note here, not a test precondition. |
| K8 | nit | The original "Out of scope" section is correct; no change. | No change. |

### Test-Quality critic (T)

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| T1 | block | All tests call `ed.ExternalDocsProbe()._run(ctx)`. `_run` doesn't exist on the ABC; `run` is `async`, public, takes `(repo, ctx)`. Tests would fail at import. | Rewrite every test to `asyncio.run(ed.ExternalDocsProbe().run(repo, ctx))` (precedent: `tests/unit/probes/layer_b/test_dep_graph.py`). |
| T2 | block | Tests construct `ProbeContext.for_test(repo_root=…)`. Doesn't exist; `ProbeContext` is a stdlib `@dataclass`. | Introduce `_make_repo(tmp_path)` + `_make_context(tmp_path)` helpers in `tests/unit/probes/layer_d/conftest.py` (S6-01 hardening precedent). Tests call these instead. |
| T3 | block | `from codegenie.probes.base import ProbeContext, _PROBE_REGISTRY` — `_PROBE_REGISTRY` is not in `base.py`. | Import `default_registry` from `codegenie.probes.registry`; use `next(e for e in default_registry._entries if e.cls.name == "external_docs")`. |
| T4 | harden | `pytest.raises(Exception)` is too broad. A future bug that raises `RuntimeError` (instead of `pydantic.ValidationError`) for an unrelated reason would still pass the test — the mutation-resistance is weak. | `pytest.raises(pydantic.ValidationError)` — the specific exception type is the contract. |
| T5 | harden | `Path(__file__).parents[4]` path math is brittle against test-tree moves; if `tests/unit/probes/layer_d/test_external_docs.py` ever moves up or down one directory, the test silently passes against the wrong manifest. | Use a `_project_root` fixture in `conftest.py` (computed via `Path(codegenie.__file__).parents[2]` or similar) and pass it as a fixture arg — bind the math to the package, not to the test file's location. |
| T6 | harden | No test asserts the probe does NOT read `repo.config["external_docs"]` (even harmlessly). The "slippery slope to a fetcher" failure mode the design's Notes-for-implementer warns about has no test enforcement. | New test: inject a `repo.config["external_docs"]` value; assert the slice is still `opted_in=False`. Static backstop: module source does not contain `.config.get("external_docs"` or `.config["external_docs"]` literal accesses. |
| T7 | harden | The "no forbidden imports" set is good but could be tighter — `httplib`, `http.client`, `aiohttp` are all relevant. | Extend the forbidden set to `{httpx, requests, urllib.request, aiohttp, socket, http.client, httplib}`. |
| T8 | nit | The `test_two_consecutive_runs_byte_identical` test should also verify the raw artifact file is byte-identical (not just the in-memory slice). | Extend: `(ctx.output_dir / "external_docs.json").read_bytes()` round-tripped through `json.loads` equals the slice. |

### Consistency critic (C)

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| C1 | block | `confidence="unavailable"` contradicts the frozen `ProbeOutput.confidence: Literal["high","medium","low"]` ABC field (Phase 0 ADR-0007). Phase 0 ADR-0007 freezes this byte-for-byte against `localv2.md §4`; "unavailable" is an ABC change not authorized by any ADR. | Rewrite to `confidence="high"`; update manifest README to match. |
| C2 | block | The `_run(self, ctx)` signature contradicts `localv2.md §4` and the Phase 0 ABC `async def run(self, repo, ctx)`. | Rewrite. |
| C3 | block | `probe_id = ProbeId(...)` class attr contradicts the ABC `name: str` field. | Rewrite to `name: str = "external_docs"` + `_PROBE_ID: Final[ProbeId]` module constant. |
| C4 | block | `from codegenie.ids` — module doesn't exist (recurring documentation drift). | Import from `codegenie.types.identifiers`. |
| C5 | block | `tuple[str, ...]` for `applies_to_*` contradicts ABC `list[str]`. | `list[str] = ["*"]`. |
| C6 | block | `_PROBE_REGISTRY` doesn't exist. | `default_registry._entries`. |
| C7 | harden | Schema path with `layer_d/` subdir contradicts the flat schema layout S6-01 / S6-02 / S6-03 settled. | Flat path: `src/codegenie/schema/probes/external_docs.schema.json`. |
| C8 | block | `ProbeOutput(probe_id=..., …)` constructor signature contradicts the six-field dataclass. | Rewrite to `ProbeOutput(schema_slice, raw_artifacts, confidence, duration_ms, warnings, errors)`; `duration_ms` via `time.perf_counter()`. |
| C9 | nit | AC-14's S8-04 forward reference is documentation, not a Phase-2 testable invariant. | Soften per K7. |
| C10 | nit | The manifest README line 194 currently describes `confidence="unavailable"`. Once AC-5 is fixed, the README will be inconsistent until updated. | Update manifest line 194 in lock-step with AC-5. |

### Design-Patterns critic (D)

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| D1 | harden | The probe deploys three established design patterns but the story doesn't name them: **Null Object** (Probe ABC satisfied so consumers don't special-case), **Tagged union via discriminator** (`opted_in` is the load-bearing discriminator key choice), **Open/Closed at file boundary** (future opted-in branch lands as new sibling free function + `match` arm, not as subclass). Naming them makes the design legible to a Phase-4 contributor. | Add a "Design-pattern lineage" paragraph in Context; explicit Notes-for-implementer entries for each pattern. |
| D2 | harden | The Phase-2 slice name `ExternalDocsSlice` precludes the future tagged-union widening. The eventual shape is `Annotated[NotOptedInExternalDocsSlice \| OptedInExternalDocsSlice, Field(discriminator="opted_in")]`; the Phase-2 model should be named for what it *is* (`NotOptedInExternalDocsSlice`), so the future opted-in variant is a sibling, not a "let me edit the existing model" temptation. Sibling-naming is the **Open/Closed at the file boundary** discipline `Fresh` + `Stale`, `Pass` + `Fail` + `NotApplicable` already establish in Phase 2. | Rename. Add AC for the rename. Update Notes. |
| D3 | harden | The Refactor section says "not a class hierarchy" but doesn't show the alternative dispatch pattern. A Phase-4 contributor reading the story has no positive blueprint — only a prohibition. | Show the explicit `match repo.config.get("external_docs"): case None \| {}: …; case {"sources": _}: …; case other: assert_never(other)` dispatch with module-level free functions `_emit_not_opted_in` / `_emit_opted_in`. |
| D4 | info | The probe is correctly avoiding: primitive obsession (`Literal[False]` not raw `bool`); anaemic types (typed slice with discriminator); speculative inheritance (forbidden by AC-NEW-5); hidden state (probe is pure). | No change needed — confirmed and documented. |
| D5 | nit | The functional-core / imperative-shell split is trivially satisfied (the probe is pure) but the design opportunity (where the imperative shell goes when the opted-in branch lands) should be documented for Phase 4. | Add to Refactor / Notes: the opted-in fetcher lands as a sibling module `_external_docs_fetcher.py`; the probe class stays a thin dispatcher. |
| D6 | nit | The Rule-of-Three threshold for extracting a shared "deferred stub" base class needs a documented trigger so a Phase-4 contributor doesn't prematurely extract it on the second deferred stub. | Add Notes §6: revisit at three deferred stubs in Layer D, not before. |

## Research findings (Stage 3)

**None.** No `NEEDS RESEARCH` findings. Every gap traced to in-repo precedent:

- `src/codegenie/probes/base.py:68` — `Literal["high","medium","low"]` confidence type (source of truth for K1 / C1).
- `src/codegenie/probes/layer_b/index_health.py:298-326` — canonical full-field ABC declaration; the model for the corrected AC-4 / GREEN.
- `src/codegenie/probes/registry.py:131-238` — `default_registry._entries` registry API.
- `src/codegenie/types/identifiers.py:29` — `ProbeId = NewType("ProbeId", str)` correct import path.
- `src/codegenie/probes/layer_b/scip_index.py:114` — `_PROBE_ID: Final[ProbeId] = ProbeId(...)` dual-form identity precedent.
- S6-01 / S6-02 / S6-03 validation reports — full lineage of the contract-fix patterns; this story repeats them mechanically.

## Edits applied (Stage 4)

Twenty in-place edits to `S6-04-external-docs-opt-in.md`:

| # | Section | Change |
|---|---|---|
| 1 | Header | `Status: Ready` → `Status: Hardened (ready for executor)`; expand `Depends on` to name the inherited probe-shape conventions; add Phase 0 ADR-0007 + 02-ADR-0003 to ADRs honored. |
| 2 | Header | Inserted `## Validation notes` block documenting the audit. |
| 3 | Context | Replaced the `confidence="unavailable"` framing with the `confidence="high"` + typed-slice rationale; expanded with a "Design-pattern lineage" subsection naming Null Object, Tagged union via discriminator, Open/Closed at file boundary, and Functional core / imperative shell. |
| 4 | References | Added 02-ADR-0007 + 02-ADR-0003 references; added probe-shape precedent references (S6-01/02/03); expanded existing-kernel section with the seven authoritative contract surfaces (base.py, registry.py, scip_index.py, index_health.py, identifiers.py, schema layout). |
| 5 | Goal | Rewrote with full ABC field set; explicit `async def run(repo, ctx)` signature; explicit "no `repo.config` reads, no `ctx.config` reads" discipline; single raw artifact write; `confidence="high"` rationale. |
| 6 | AC-1 | Renamed slice `ExternalDocsSlice` → `NotOptedInExternalDocsSlice` per D2. |
| 7 | AC-3 | Added discriminator-key rationale paragraph; pinned `Literal[False]` as the discriminator value AND the load-bearing schema-stability commitment. |
| 8 | AC-4 | Rewrote with full Phase-0 ABC field set verbatim (`name`, `version`, `layer`, `tier`, `applies_to_*` as `list`, `requires`, `declared_inputs`, `timeout_seconds`, `cache_strategy`); added `_PROBE_ID: Final[ProbeId]` constant; corrected import path. |
| 9 | AC-5 | Rewrote with async `run(repo, ctx)`; six-field `ProbeOutput`; `confidence="high"` rationale + manifest pointer to `base.py:68`; explicit forbidden-reads list. |
| 10 | AC-NEW-1 | New AC: single raw artifact `ctx.output_dir / "external_docs.json"` via atomic `.tmp` → `os.replace`. |
| 11 | AC-NEW-2 | New AC: `_PROBE_ID: Final[ProbeId]` module constant. |
| 12 | AC-6 | Tightened forbidden imports set to seven members. |
| 13 | AC-8 | Flat schema path. |
| 14 | AC-9 | `default_registry._entries` access pattern. |
| 15 | AC-NEW-3 | New AC: registry-membership smoke. |
| 16 | AC-10 | Rewrote with async + the byte-identity scope (`schema_slice` + raw artifact; `duration_ms` excluded). |
| 17 | AC-NEW-4 | New AC: tagged-union discriminator key `discriminator="opted_in"` literal in module source. |
| 18 | AC-NEW-5 | New AC: AST walk forbids subclass extension. |
| 19 | AC-14 | Softened: assert only the two-place documentation (manifest README); S8-04 dependency is documentation. |
| 20 | Implementation outline / TDD plan / Refactor / Notes / Files to touch | Wholesale rewrite to match the new contract: `_make_repo`/`_make_context` helpers; `asyncio.run(probe.run(repo, ctx))`; flat schema path; `_PROJECT_ROOT` constant via conftest; explicit `pydantic.ValidationError` exception specificity; `confidence="high"` semantics; `NotOptedInExternalDocsSlice` rename throughout; full GREEN module showing the six-field `ProbeOutput`, the atomic write, the `_PROBE_ID` constant, and the full ABC field declaration; Refactor section now shows the exact `match` dispatch the Phase-4 extension follows. |

One lock-step edit to `docs/phases/02-context-gather-layers-b-g/stories/README.md`:

| # | Section | Change |
|---|---|---|
| 1 | Line 194 (S6-04 row) | Updated manifest description from `confidence="unavailable"` → `confidence="high"` with typed slice rationale; preserved the `opt-in` substring AC-14 pattern-matches against; named `opted_in` as the eventual tagged-union discriminator. |

## Verdict

**HARDENED.**

The story's goal is well-formed and traces to the architecture. The original draft had nine `block`-severity contract mismatches against the actual kernel (eight systemic to the Phase-2 story-authoring lineage, one unique to this story's `confidence="unavailable"` claim). All nine are now resolved in-place. Five new ACs strengthen the AC set with mutation-resistance trip-wires (raw-artifact discipline, `_PROBE_ID` constant, registry-membership smoke, discriminator-key invariant, no-subclass extension). The design-pattern hardens (rename to `NotOptedInExternalDocsSlice`; name Null Object / Tagged union / Open/Closed; show the explicit `match` dispatch the Phase-4 extension follows) make the story legible to a Phase-4 contributor.

Ready for `phase-story-executor`.
