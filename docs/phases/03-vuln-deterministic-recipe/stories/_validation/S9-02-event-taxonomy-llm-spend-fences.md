# Validation report: S9-02 — Event-taxonomy completeness fence + `$0.00` LLM-spend assertion

**Validated:** 2026-05-20
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S9-02 ships two `tests/fence/` tests: one asserting event-taxonomy completeness (every declared event variant is emitted; every emit site is a declared variant on the right stream) and one asserting Phase 3 never produces a `remediation-report.yaml` carrying an `llm_cost_usd` field. The *goal* is sound and traces cleanly to `High-level-impl.md §Step 9`, ADR-0005, and ADR-0011.

The *mechanism* was not. The story's AC-1 and its entire §Red TDD plan for the taxonomy fence were written against an `EventLog` API that does not exist. The shipped S6-01 contract (status `HARDENED`, `src/codegenie/plugins/events.py`) makes `WorkflowInternalEvent` / `WorkflowSpanningEvent` **module-level `TypeAlias = Annotated[…]` aliases**, not classes, and `emit_internal` / `emit_spanning` take a **constructed Pydantic event instance**, not an `event_type=` keyword. Both extraction helpers in the TDD plan would therefore have failed against the real codebase — one with an `AssertionError`, one by silently finding zero emit sites and reporting every variant "dead." This is a single block-tier defect with a clear in-place fix, so the verdict is HARDENED, not RESCUE: AC-1, Implementation outline steps 1–3, the §Red test code, and the §Notes escape hatch were all rewritten to the correct model. Eight further harden/nit findings (stale taxonomy enumeration, stale file references, understated dependency list, missing ACs for variable/factory emit sites, unsatisfiable negative-regression ACs) were also closed.

The four critic lenses (Coverage, Test-Quality, Consistency, Design-Patterns) were applied directly by the synthesizer after a full Stage-1 context load (story + S6-01, S6-04, S5-05, S8-02, S9-01 stories + the live codebase layout under `src/codegenie/plugins/`, `src/codegenie/transforms/`, `plugins/`, `tests/fence/`). No Stage-3 research was required — every finding resolves against shipped docs/code.

## Findings by critic

### Consistency critic

**C-F1 — Taxonomy-fence extraction contradicts the shipped S6-01 API.**
- **Severity:** block
- **Smell:** Stale references / wrong model of a dependency.
- **What's wrong:** AC-1 says the fence "extracts the two `Literal[...]` sets for `WorkflowInternalEvent.event_type` and `WorkflowSpanningEvent.event_type`" and "extracts the `event_type=` literal at each call site." Neither matches S6-01:
  - S6-01 AC-6 / AC-7 + Implementation outline ship the unions as `WorkflowInternalEvent: TypeAlias = Annotated[V1 | V2 | …, Field(discriminator="event_type")]` at module scope. There is no `class WorkflowInternalEvent`. The TDD plan's `_extract_literal_set(class_name)` walks for an `ast.ClassDef` of that name with an `event_type` `AnnAssign` — it would hit no `ClassDef` and raise `AssertionError("event_type Literal not found on WorkflowInternalEvent")`.
  - S6-01 AC-3 / AC-4 give `emit_internal(event: WorkflowInternalEvent) -> EventId` / `emit_spanning(event: WorkflowSpanningEvent) -> EventId`. Call sites construct a variant instance (`log.emit_internal(PluginResolved(...))`). The TDD plan's `_extract_emit_sites()` scans for `keyword(arg="event_type")` on the emit calls — there is no such kwarg, so it returns empty sets and `test_every_declared_literal_has_an_emit_site` reports **every** variant as a dead enum.
- **Proposed fix:** Rewrite AC-1, Implementation outline steps 1–3, both §Red test files, and the §Notes escape hatch to: (1) resolve each union alias's `Annotated[…]` `BinOp` tree to its member classes, then read each class's `event_type: Literal["…"]` default; (2) extract emit sites from the **constructed variant class** in `call.args[0]`.
- **Confidence:** high
- **Source:** S6-01 (`docs/phases/03-vuln-deterministic-recipe/stories/S6-01-two-stream-event-log.md`) AC-3/AC-4/AC-6/AC-7/AC-DISC + Implementation outline §3; `grep` confirms no `emit_internal`/`emit_spanning`/`events.py` exists on disk yet (deps are `HARDENED`, not `Done`).

**C-F2 — §Context taxonomy enumeration is stale.**
- **Severity:** harden
- **Smell:** Stale references.
- **What's wrong:** §Context listed 14 internal + 8 spanning `event_type` values. S6-01 ships **16 internal** (adds `plugins_loaded`, `bundle_entry_promoted`) + **9 spanning** (adds `cache_gc_completed`, the re-imported `CacheGcCompletedEvent` from S3-05). The fence derives the set dynamically from `events.py`, so the staleness does not break the test — but a reader cross-checking the prose against the union would be misled.
- **Proposed fix:** Update §Context to the shipped 16/9 set and explicitly mark the list illustrative: `events.py` is the only runtime source of truth; the fence must never hard-code a count.
- **Confidence:** high
- **Source:** S6-01 AC-6 (16 internal variants) / AC-7 (9 spanning variants).

**C-F3 — Stale reference to `test_phase3_importlinter_contracts.py`.**
- **Severity:** harden
- **Smell:** Stale references.
- **What's wrong:** The References block and §Notes tell the implementer to "mirror" / "match" `tests/fence/test_phase3_importlinter_contracts.py`. That file does not exist. S9-01's own validation notes (AC-11) state the meta-fence is `test_phase3_importlinter_contracts_shape.py` and explicitly say "do not fork a parallel `test_phase3_importlinter_contracts.py`." The real Phase 3 fence files are `test_phase3_importlinter_contracts_shape.py`, `test_phase3_cross_plugin_isolation.py`, `test_phase3_cross_plugin_planted.py`.
- **Proposed fix:** Repoint to `test_phase3_cross_plugin_isolation.py` (the auto-discovering AST-walk precedent — the closest analogue to S9-02's own AST walk) and `test_phase3_importlinter_contracts_shape.py` (docstring/ADR-cross-reference discipline).
- **Confidence:** high
- **Source:** `ls tests/fence/`; S9-01 story AC-11 + References.

**C-F4 — `Depends on:` understates the real prerequisites.**
- **Severity:** harden
- **Smell:** Dependency cliff.
- **What's wrong:** The header declared only `Depends on: S9-01`. The taxonomy fence reads `events.py` (S6-01) and emit sites across `transforms/` (S6-04, S5-02, S6-02) + `plugins/{slug}/` (S7-01, S7-03); the LLM-spend fence reads goldens (S8-02) and locks the absence of a field in the `RemediationReport` schema (S5-05). For the fences to run *green* — not merely exist — all of those must be shipped. §Red acknowledged this in prose, but the header dependency line did not (Rule 12 — fail loud).
- **Proposed fix:** Expand `Depends on:` to name S5-05 / S6-01 / S6-04 / S8-02 + the emit-site stories, and instruct the executor to pause if any is not GREEN.
- **Confidence:** high
- **Source:** story §Red + §Out-of-scope ("Emit-site implementations — owned by S6-04, S5-02, S6-02, S7-01/S7-03").

### Coverage critic

**Cov-F1 — No AC for variable-event emit sites.**
- **Severity:** harden
- **Smell:** Negative-space gap / lazy-impl thought experiment.
- **What's wrong:** With the corrected S6-01 API, `event = SomeVariant(...); log.emit_internal(event)` is a *first-class* call shape, not an exotic one. The original story addressed variable emits only in a §Notes paragraph (and keyed it on the non-existent `event_type=` kwarg). A fence that silently drops variable-arg emits would under-report emit coverage and falsely flag live variants as dead.
- **Proposed fix:** Add an AC requiring the fence to resolve a bare-`Name` emit argument via one-hop intra-function assignment lookup, and to fail loud (with a `# fence-allow:` escape hatch) when resolution is impossible.
- **Confidence:** high
- **Source:** lazy-impl thought experiment against the corrected API.

**Cov-F2 — No AC for factory/classmethod-constructed emits.**
- **Severity:** harden
- **Smell:** Negative-space gap.
- **What's wrong:** S6-01 AC-MIG migrates the `codegenie cache prune` CLI emit site to `event_log.emit_spanning(CacheGcCompletedEvent.from_result(result, trigger="operator_cli"))` — a factory classmethod call. A fence that only recognises bare-`Name` constructors (`Call(func=Name)`) would miss this, falsely flagging `CacheGcCompleted` as a dead spanning variant.
- **Proposed fix:** Add (folded into the same new AC as Cov-F1) a requirement that the fence resolves factory calls via the `Attribute(value=Name(<Class>), attr=…)` receiver.
- **Confidence:** high
- **Source:** S6-01 AC-MIG + Implementation outline §4.

### Test-Quality critic

**TQ-F1 — The negative-regression ACs are unsatisfiable as written.**
- **Severity:** harden
- **Smell:** Coverage-driven / un-runnable test.
- **What's wrong:** AC-3 requires `tmp_path`-scoped negative regression sub-tests that inject a synthetic dead variant and a synthetic undeclared emit. But the TDD plan's helpers (`_extract_literal_set`, `_extract_emit_sites`) read module-level constants `EVENTS` and `SEARCH_ROOTS` — they cannot be pointed at a `tmp_path` fake tree. The negatives could only be written by duplicating the extraction logic, which defeats their purpose (they would not exercise the real fence's code).
- **Proposed fix:** Mandate that the extraction logic is pure, path-parameterised functions — `declared_variants(events_path)` and `emit_sites(search_roots)` — so the real fence and the negatives call identical code.
- **Confidence:** high
- **Source:** story AC-3 vs. TDD plan helper signatures.

**TQ-F2 — The §Red taxonomy-fence test code is wholesale wrong.**
- **Severity:** block (subsumed by C-F1)
- **What's wrong:** Both §Red helpers and both §Red test functions encode the wrong API. An executor following the TDD plan literally would write a red test that is red *for the wrong reason*, then "fix" it into a fence that never fires.
- **Proposed fix:** Replace the `test_event_taxonomy_complete.py` code block entirely (done — see Edits). The `test_no_llm_spend.py` block is correct (YAML-parse-and-walk, not text-grep) and was left intact.
- **Confidence:** high
- **Source:** C-F1.

### Design-Patterns critic

**DP-F1 — Extraction helpers should be pure, path-injected (functional core / imperative shell).**
- **Severity:** harden
- **Smell:** Hidden state (module-level path constants) / pure-impure tangle.
- **What's wrong:** Helpers bound to module-level `EVENTS` / `SEARCH_ROOTS` are not reusable, not unit-testable in isolation, and force the negative tests to duplicate logic (TQ-F1).
- **Proposed fix:** `declared_variants(events_path: Path) -> dict[str, dict[str, str]]` and `emit_sites(search_roots: Sequence[Path]) -> dict[str, set[str]]` as pure functions in `tests/fence/_helpers.py`; the module-level constants become *call arguments*, not *captured state*.
- **Confidence:** high
- **Source:** functional-core/imperative-shell pattern; CLAUDE.md.

**DP-F2 — Affirm the fence's Open/Closed property; never hard-code the variant count.**
- **Severity:** nit (surfaced in story prose)
- **Smell:** Premature/implicit registry temptation.
- **What's wrong:** §Context listing concrete counts (16/9) tempts an implementer to hard-code `assert len(declared) == 16`. That would make every additive S6-01 amendment break the fence for the wrong reason. The fence's value is precisely that it auto-discovers the variant set from `events.py`.
- **Proposed fix:** Mark the §Context list illustrative and state the source-of-truth rule explicitly. (Applied as part of C-F2's edit.)
- **Confidence:** high
- **Source:** CLAUDE.md "Extension by addition"; the fence's own design intent.

## Research briefs

None — every finding resolved against shipped docs and code. Stage 3 skipped.

## Conflict resolutions

No critic conflicts. C-F1 (Consistency, block) is the root cause; TQ-F2 is the same defect seen through the Test-Quality lens and was merged into C-F1's fix. Cov-F1 and Cov-F2 share a single new AC. TQ-F1 and DP-F1 share a single fix (path-parameterised pure helpers) and were applied together. All findings are additive — none required dropping another's proposal.

## Edits applied

1. **Header — `Status` → HARDENED; `Depends on:` expanded** (C-F4) to name S6-01/S6-04/S5-02/S6-02/S7-01/S7-03/S5-05/S8-02 with an executor "pause if not GREEN" instruction.
2. **`Validation notes` block inserted** under the header recording the block-tier closure + seven harden closures.
3. **§Context — taxonomy enumeration rewritten** (C-F2) to the shipped 16/9 set, the `TypeAlias = Annotated[…]` shape called out, and the list marked illustrative with the `events.py`-is-source-of-truth rule (DP-F2).
4. **§Context — failure-mode #2 rewritten** (C-F1) from "emits an event whose `event_type` literal is not in the union" to "constructs an event variant that is not a member of the stream's union," covering mis-stream emits.
5. **References block — `events.py` / orchestrator / fence-precedent entries rewritten** (C-F1, C-F3): the union shape spelled out; emit-site shapes (direct / factory / variable) named; the stale `test_phase3_importlinter_contracts.py` repointed to `test_phase3_cross_plugin_isolation.py` + `test_phase3_importlinter_contracts_shape.py`.
6. **AC-1 rewritten** (C-F1) — declared-variant extraction via the `Annotated[…]` alias; emit-site extraction via the constructed variant class in `args[0]`; explicit "no `event_type=` keyword" note.
7. **New AC added** (Cov-F1, Cov-F2) — variable / factory emit sites are resolved (factory receiver, one-hop assignment lookup) or fail loud with a `# fence-allow:` escape hatch.
8. **Negative-regression AC amended** (TQ-F1, DP-F1) — extraction logic mandated as pure, path-parameterised functions so the real fence and the `tmp_path` negatives drive the same code.
9. **Implementation outline steps 1–3 rewritten** (C-F1) — `AnnAssign`/`Annotated` union walk; `ClassDef` `event_type` Literal read (handling single-member `Constant` slice); emit-site resolution of direct/factory/variable args.
10. **§Red `test_event_taxonomy_complete.py` code block replaced wholesale** (C-F1, TQ-F2, DP-F1) — `declared_variants(events_path)` + `emit_sites(search_roots)` pure path-parameterised helpers; `_union_member_names` walks the `Annotated` `BinOp` tree; `_resolved_class` handles direct/factory/one-hop-variable; two corrected test functions assert on variant classes. `test_no_llm_spend.py` block left intact (already correct).
11. **§Red / §Green / §Refactor prose updated** — "literal" → "variant" terminology; explicit "cannot reach green before prerequisites are GREEN"; `_helpers.py` lift mandated with the S9-01 file-naming correction.
12. **§Files to touch — `_helpers.py` promoted from OPTIONAL to NEW/required** (DP-F1).
13. **§Notes — variable-emit escape hatch + union-resolution note rewritten** (C-F1); fence-shape "match" note repointed off the non-existent file (C-F3).

## Verdict rationale

HARDENED. One block-tier defect (C-F1 / TQ-F2 — the taxonomy fence was specified against a non-existent `EventLog` API) but it has a clean, fully-specified in-place fix: the goal, scope, and the LLM-spend half of the story were always correct, and the corrected extraction model is unambiguous given the shipped S6-01 contract. Not RESCUE — the story's *goal* never needed rewriting, only its *mechanism*. The eight harden/nit findings were all closed in place. The story is now executable, provided its (now-honest) dependency list is GREEN first.

## Recommended next step

`phase-story-executor` — but only once S6-01, S6-04, S5-02, S6-02, S7-01, S7-03, S5-05, and S8-02 are GREEN (all currently `HARDENED`). The fence tests cannot meaningfully run before `src/codegenie/plugins/events.py` and the emit sites exist; the executor should verify prerequisite status and pause rather than weaken the fence.
