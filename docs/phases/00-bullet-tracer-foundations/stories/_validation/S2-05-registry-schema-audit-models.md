# Validation report: S2-05 — Registry + JSON Schema envelope + audit models

**Validated:** 2026-05-13
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Story:** [`../S2-05-registry-schema-audit-models.md`](../S2-05-registry-schema-audit-models.md)

## Summary

S2-05 is the Step 2 synthesis story: it lands the `@register_probe` decorator + `Registry`, the layered Draft 2020-12 envelope schema + first per-probe sub-schema + cached validator, and the `RunRecord` / `ProbeExecutionRecord` Pydantic audit models with the dual `cache_key` + `blob_sha256` anchors (ADR-0004 Gap 2). The story was largely correct in shape but had four classes of holes the three critics surfaced: (1) a duplicate deliverable — `templates/adr-amendment.md` was already shipped by S2-02 with a five-step checklist, yet AC-8 still claimed this story creates it with four steps; (2) load-bearing caches that were unobservable in tests — `Registry.for_task`'s `lru_cache` and `validator._validator()`'s `lru_cache` would both ship as no-cache mutants without any test failing; (3) thin TDD test bodies, most notably `test_for_task_filters_by_star_semantics` which was literally `...  # detail in implementation`; (4) ambiguous shapes the executor would have to guess at — `RunRecord.os_kernel` vs `os_kernel_sha` (arch §Component design and arch §Data model disagree), the `Skipped` exit_status / empty-blob-sha256 sentinel from ADR-0004 §Consequences, and `Probe.version` (used by `ProbeExecutionRecord.version` and S3-01 but not declared on the frozen ABC).

Three critics returned 31 findings (4 block, 22 harden, 5 nit/informational). No `NEEDS RESEARCH` tags — every finding was answered by docs already in the repo. The validator applied 12 in-place edits: a Validation notes block, a Context-paragraph rewrite (drop the false claim that this story ships the template), AC-2 hardened with a five-row filter-matrix table, AC-7 hardened with explicit `os_kernel_sha` and the `Skipped` blob-sha256 sentinel, AC-8 rewritten as verify-existence-only, AC-9/10/11 each rewritten with mutation-resistant snippets, AC-13 added (validator cache observability), the three TDD red-section snippets rewritten end-to-end with parametrized filter tests and cache_info introspection, Implementation outline step 7 inverted ("do NOT author the template"), Files-to-touch annotated, and an implementer note added for `Probe.version` as a convention. Three architectural inconsistencies are surfaced as follow-ups (not auto-fixed): the manifest README.md description, High-level-impl Step 2's overstated `AuditWriter.record` scope, and arch §Component design's `os_kernel` vs Data model's `os_kernel_sha`.

## Findings by critic

### Coverage critic

14 findings:

- **F1 (block)** — AC-8 duplicates an S2-02 deliverable. `templates/adr-amendment.md` already exists at the repo root (S2-02 commit `1ed09a6`, 56 lines, five-step checklist). AC-8 says ship it with a four-step checklist. Two stories cannot both create the same file, and the count is wrong.
- **F2 (harden)** — `register_probe` return value not pinned. A lazy `def register_probe(cls): default_registry.register(cls); return None` passes the type hint but breaks every consumer.
- **F3 (harden)** — `for_task` AC has rich prose but TDD test 3 is literally `...  # detail in implementation`. The most important contract test in the file is TBD.
- **F4 (harden)** — `lru_cache` hit unobservable. `AC-11` says "lru_cache hit on repeated calls" but no test pins `cache_info().hits`. The no-cache mutant survives every test.
- **F5 (block)** — Schema `_validator()` cache untested. AC-7 says "cached via `functools.lru_cache`" but no test asserts it. The no-cache mutant costs ~30 ms per `validate()` call and would silently ship.
- **F6 (harden)** — No test for envelope `$id` containing `v0.1.0`. ADR-0003 makes this load-bearing for S3-01's `per_probe_schema_version` to scope cache invalidation correctly.
- **F7 (harden)** — No test for `language_detection.schema.json`'s `$id` containing `language_detection/v0.1.0`. Same ADR-0003 hook.
- **F8 (harden)** — `RunRecord` shape AC says "per arch §Data model" but the arch has two contradictory field names: §Component design line 599 says `os_kernel`; §Data model line 722 says `os_kernel_sha`. The executor is left to guess.
- **F9 (harden)** — `ProbeExecutionRecord` `exit_status="skipped"` path unhandled. ADR-0004 §Consequences specifies `blob_sha256=""` (empty-string sentinel) for skipped executions. The story says `blob_sha256: str` is required; nothing pins that `""` is accepted.
- **F10 (harden)** — No structural test for the envelope's layered `additionalProperties` policy (handled behaviorally by AC-9; acceptable, noted for completeness).
- **F11 (nit)** — `importlib.reload()` duplicate-name fire-up not pinned; covered in implementer notes; acceptable as nit.
- **F12 (harden)** — Pydantic `frozen=True` not tested. The `frozen=False` mutant passes every test.
- **F13 (harden)** — `Probe.version` is used by tests as an instance attribute, but it's not declared on the frozen ABC. S3-01's `cache_key(...)` reads `cls.version`. Implementer note doesn't address the mypy-strict friction.
- **F14 (nit)** — Out-of-scope is long, specific, traces; healthy.

### Test-Quality critic

11 findings:

- **TQ-F1 (block)** — `test_for_task_filters_by_star_semantics` is a TBD stub. The lazy `def for_task(self, task, languages): return tuple(self._probes)` (filter does nothing) passes the existing snippet.
- **TQ-F2 (block)** — `_validator()` lru_cache untested. Same finding as Coverage F5.
- **TQ-F3 (harden)** — `$ref` resolution not behaviorally pinned. No test crafts a *valid* `probes.language_detection` payload. A broken resolver only surfaces in the bad-type test, which is fragile.
- **TQ-F4 (block)** — `exit_status` literal enforcement claimed by AC-11 but not in the TDD snippets. Bare `exit_status: str` mutant survives.
- **TQ-F5 (harden)** — `frozen=True` mutation test missing. Same as Coverage F12.
- **TQ-F6 (nit)** — `cache_key`/`blob_sha256` test uses `"sha256:" + "0" * 64` (71 chars). Fine while the field is `str`; would break silently if a regex constraint were added later. Acceptable nit.
- **TQ-F7 (harden)** — `register_probe(cls) is cls` not pinned. Same as Coverage F2.
- **TQ-F8 (harden)** — `for_task` cache hit observability. Same as Coverage F4.
- **TQ-F9 (harden)** — `RunRecord` shape never tested at all. Only `ProbeExecutionRecord` has assertions in the TDD plan. Lazy `class RunRecord(BaseModel): ...` (empty model) passes.
- **TQ-F10 (harden)** — "Unknown sub-key under defined probe" not tested. The Phase 0 convention for sub-schema strictness must be pinned (the story doesn't say).
- **TQ-F11 (nit)** — Local style: test imports inside functions vs at module top. Adjacent file `tests/unit/test_hashing.py` uses module-top imports. Aligned in the rewritten snippets.

### Consistency critic

6 findings + 4 informational:

- **C-F1 (block)** — `templates/adr-amendment.md` AC contradicts S2-02. Same as Coverage F1. Verified via grep: file exists at repo root with five-step checklist; S2-02 §AC-6 explicitly ships it; S2-02 validated to HARDENED at commit `513b1d8`; green-implementation at commit `1ed09a6`.
- **C-F2 (block)** — `RunRecord.os_kernel_sha` vs `os_kernel`: two arch sections disagree. Same as Coverage F8.
- **C-F3 (harden)** — High-level-impl Step 2 (line 67) lists `AuditWriter.record(...)` body as a Step 2 deliverable; the story manifest README.md and S3-06 both put the body in Step 3. The manifest is authoritative; High-level-impl needs a corrective sweep — out of scope to fix here.
- **C-F4 (harden)** — `Probe.version` used by `ProbeExecutionRecord.version` and S3-01's `cache_key` but not declared on the frozen ABC. The convention needs to be documented in implementer notes.
- **C-F5 (harden)** — Test fixtures declare `version = "1.0"` as a class attribute; mypy --strict on the implementation's `cls.version` access requires a `cast` or `getattr(...)` strategy. Same issue surface as C-F4.
- **C-F6 (informational)** — Files-to-touch list aligns with arch §Component design; verified paths.
- **C-F7 (informational)** — All ADR references resolve (ADR-0003, ADR-0004, ADR-0007, ADR-0013); decisions match the story's claims.
- **C-F8 (informational)** — CLAUDE.md commitments respected — no LLM call, facts not judgments, determinism, extension by addition (the entire point of ADR-0013's layered policy).
- **C-F9 (informational)** — Goal-to-AC trace: every AC traces (after the AC-8 fix).
- **C-F10 (informational)** — `Depends on: S2-02, S2-03, S2-04` overstates: S2-05 doesn't import `hashing.identity_hash` (the `cache_key` field stores the hash, doesn't compute it — computation lives in S3-06). The dependency is sequencing, not semantic. Acceptable as-is.

## Research briefs

**None.** Stage 3 was skipped — zero `NEEDS RESEARCH` tags. Every finding was answerable from in-repo docs (ADRs, arch design, manifest README, S2-02 source).

## Conflict resolutions

**Coverage F1 ≡ Consistency F1** (the `templates/adr-amendment.md` deliverable): both critics flagged that S2-02 already shipped this file. Per [`editor.md`](../../../../../.claude/skills/phase-story-validator/references/editor.md) Step 2, **Consistency wins over Coverage**. Consistency offered the most-conservative reconciliation: keep AC-8 (do not delete or renumber — editor.md §"What Stage 4 must NOT do" forbids AC deletion), but rewrite it as a verify-existence-only check that explicitly defers to S2-02's delivery and forbids re-authoring. The story manifest's stale description is surfaced as a follow-up doc-correction but not auto-fixed (out of scope per `editor.md` §"What Stage 4 must NOT do" — surgical changes only, no fold-in of adjacent improvements).

**Coverage F5 ≡ Test-Quality F2** (`_validator()` cache untested): merged into one new AC (AC-13) and one concrete TDD snippet asserting `validator_mod._validator.cache_info().hits ≥ 1` after two `validate(...)` calls.

**Coverage F4 ≡ Test-Quality F8** (`for_task` cache untested): merged into a `test_for_task_lru_cache_hits_on_repeated_calls` snippet using `reg_mod._filter.cache_info()` per the implementer note's "factor out a module-level helper" pattern.

**Coverage F12 ≡ Test-Quality F5** (`frozen=True` not tested): one snippet pinning `record.cache_key = "..."` raises `pydantic.ValidationError`.

**Coverage F2 ≡ Test-Quality F7** (`register_probe` return-value): one snippet asserting decorator returns the class object unchanged.

**Coverage F8 ≡ Consistency F2** (`os_kernel_sha` vs `os_kernel`): pinned `os_kernel_sha` in the AC (Data model is the canonical schema source for serialization shape). The §Component design line is surfaced as a follow-up arch-correction action item — not auto-amended.

## Edits applied

### Edit 1 — `Validation notes` block added under the story header
- **Source:** validator convention
- **What:** New `## Validation notes` block recording validation date, verdict, finding totals, the surfaced architectural inconsistencies (manifest, High-level-impl, arch §Component design, `Probe.version`), and a list of every change applied.
- **Rationale:** Breadcrumb for the next reader; per [`editor.md`](../../../../../.claude/skills/phase-story-validator/references/editor.md) template.

### Edit 2 — Context paragraph: template-ownership claim corrected
- **Source:** Coverage F1 + Consistency F1
- **Before:** "The `templates/adr-amendment.md` PR template lands here too — the snapshot test from S2-02 already names it."
- **After:** "The `templates/adr-amendment.md` PR template was already delivered by S2-02 (commit `1ed09a6`, five-step checklist); this story only verifies it remains present."
- **Rationale:** The original Context falsely implied this story is the canonical owner.

### Edit 3 — `Depends on:` line: ADR-0003 added to honored list
- **Source:** Consistency-trace tidying (per-probe `$id` versioning is load-bearing)
- **Rationale:** ADR-0003 is referenced in the story body but was missing from the header's ADR list. Added without renumbering.

### Edit 4 — AC-2 hardened with a five-row filter matrix
- **Source:** Coverage F3 + Test-Quality F1
- **Before:** Prose-only description of `["*"]` semantics.
- **After:** Five-row table pinning probe-attribute × call-argument → included/excluded for the canonical cases (star-on-both, task-mismatch, lang-restricted-no-match, lang-restricted-match, intersection-with-extra-langs).
- **Rationale:** Catches the `for_task` no-filter mutant; matrix doubles as the `pytest.mark.parametrize` body.

### Edit 5 — AC-7 hardened: `RunRecord` shape pinned with `os_kernel_sha`; `Skipped` sentinel pinned
- **Source:** Coverage F8/F9 + Consistency F2
- **Before:** "RunRecord fields per phase-arch-design.md §Data model"; no mention of `Skipped` exit_status sentinel.
- **After:** Field names listed explicitly (including `os_kernel_sha: str`); `Skipped` exit_status accepts `blob_sha256=""` empty-string sentinel per ADR-0004 §Consequences.
- **Rationale:** Two-arch-sections-disagree resolved by picking the Data model convention (canonical for the serialized JSON shape) and surfacing the §Component design mismatch as a follow-up.

### Edit 6 — AC-8 rewritten: template is a verify-only deliverable
- **Source:** Coverage F1 + Consistency F1
- **Before:** "`templates/adr-amendment.md` exists with a four-step checklist..."
- **After:** "`templates/adr-amendment.md` is already present at the repo root (delivered by S2-02 ... canonical five-step checklist); this story only verifies the file exists; it must not be re-authored or overwritten."
- **Rationale:** AC-8 cannot be deleted (editor.md forbids renumbering); rewritten to record the actual deliverable shape.

### Edit 7 — AC-9 expanded with mutation-resistant test bullets
- **Source:** Coverage F2/F4 + Test-Quality F1/F7/F8
- **Adds:** return-value pin (`register_probe(Foo) is Foo`), parametrized filter matrix, `lru_cache.cache_info().hits ≥ 1` observable pin, empty-language-set non-crashing call.
- **Rationale:** Catches the decorator-returns-None mutant, the no-filter mutant, the no-cache mutant.

### Edit 8 — AC-10 expanded with `$id` version pins, `$ref` happy-path, and sub-schema strictness convention
- **Source:** Coverage F6/F7 + Test-Quality F3/F10
- **Adds:** envelope-`$id`-contains-`v0.1.0` test, sub-schema-`$id`-contains-`language_detection/v0.1.0` test, valid-payload-via-`$ref` test, sub-schema strictness convention pinned (`additionalProperties: false` at the probe slice; unknown sub-key fails).
- **Rationale:** ADR-0003 requires per-probe `$id` extraction for S3-01's surgical cache invalidation; ADR-0013 makes sub-schema strictness a probe-author convention that Phase 0 sets the precedent for.

### Edit 9 — AC-11 expanded with `frozen=True`, exit_status literal, `RunRecord` happy-path, `Skipped` sentinel
- **Source:** Coverage F12 + Test-Quality F4/F5/F9
- **Adds:** mutation-raises test for `frozen=True`, explicit `exit_status="bogus"` rejection, `RunRecord` constructed-and-`extra="forbid"` test, `Skipped` empty-blob_sha256 acceptance test.
- **Rationale:** Catches `frozen=False` mutant, `exit_status: str` mutant, missing-`RunRecord` mutant, and the ADR-0004 `Skipped` sentinel gap.

### Edit 10 — AC-13 added: `_validator()` lru_cache observability
- **Source:** Coverage F5 + Test-Quality F2
- **Rationale:** The no-cache mutant ships at ~30 ms per validate call. New AC pins `validator_mod._validator.cache_info().hits ≥ 1` after two `validate(...)` calls.

### Edit 11 — TDD plan red-section snippets rewritten end-to-end
- **Source:** Test-Quality F1/F2/F3/F4/F5/F7/F8/F9/F10
- **What:** All three Python snippets replaced. The `test_for_task_filters_by_star_semantics` stub is now a `pytest.mark.parametrize` matrix. The schema snippets add `$ref` valid-payload, sub-schema strictness, `$id`-version pins, and validator-cache-hit. The audit-model snippets add `frozen=True` mutation, exit_status literal rejection, `RunRecord` happy-path, and `Skipped` sentinel. All imports moved to module top per local convention.
- **Rationale:** Mutation-resistance pattern is now legible to the executor and the next validator.

### Edit 12 — Implementation outline step 7 inverted; step 1 count corrected
- **Source:** Consistency F1
- **Before step 7:** "Author `templates/adr-amendment.md` ... Four-step PR-author checklist..."
- **After step 7:** "Do not author `templates/adr-amendment.md`. It already exists ... Verify the file is present."
- **Before step 1:** "Write all four test files first..."
- **After step 1:** "Write the three new test files first... Add a one-line existence-check assertion for `templates/adr-amendment.md` inside `test_audit_models.py`..."
- **Rationale:** The story's prior instruction to author the template would have overwritten S2-02's deliverable on the executor's first commit.

### Edit 13 — Files-to-touch annotated for `templates/adr-amendment.md`
- **Source:** Consistency F1
- **Rationale:** Row struck-through with annotation "Already exists ... Do NOT modify or overwrite — verify-only" so the executor sees the constraint at the file-listing step too.

### Edit 14 — Implementer notes: `Probe.version` convention added
- **Source:** Coverage F13 + Consistency F4/F5
- **Rationale:** `Probe.version` is read by `ProbeExecutionRecord.version` (this story) and S3-01's `cache_key` (next story) but is not on the frozen ABC. Implementer guidance: every probe class declares `version = "..."` as a convention; under `mypy --strict`, reading `cls.version` from a `type[Probe]` needs an explicit `getattr` or `cast`. Adding `version` to the ABC is an ADR-0007-amendment-workflow change — out of scope here.

## Verdict rationale

**HARDENED.** The story's goal is intact and the deliverables are correctly scoped at the architecture level. The findings clustered around (1) one stale-deliverable contradiction (`templates/adr-amendment.md`) — fixable in place by rewriting AC-8 and the related Implementation outline / Files-to-touch entries without deleting the AC; (2) several load-bearing caches and frozen-model invariants that were declared in ACs but never tested, all fixable with concrete one-shot pytest snippets; (3) two arch-section inconsistencies (`os_kernel_sha`, `AuditWriter.record` Step assignment) that the story does not need to fix but does need to *pin* a position on so the executor doesn't guess. No `block` finding required rewriting the story's goal or scope, so RESCUE was not warranted. The story is now mutation-resistant on every ACR's load-bearing dimension (filter matrix, `lru_cache` hits on both `for_task` and `_validator()`, `frozen=True` on Pydantic, `Skipped` sentinel, `$id` versioning, `$ref` resolution), and the three architectural follow-ups (manifest README, High-level-impl Step 2, arch §Component design `os_kernel`) are tracked in the Validation notes block as known doc-debt without blocking the executor.

## Recommended next step

`phase-story-executor` to implement.

**Follow-ups (separate work — not blocking this story):**

1. Edit `docs/phases/00-bullet-tracer-foundations/stories/README.md` to remove `templates/adr-amendment.md` from S2-05's deliverable description (it was delivered by S2-02).
2. Edit `docs/phases/00-bullet-tracer-foundations/High-level-impl.md` Step 2 (around line 67) to clarify that `AuditWriter.record(...)` body lives in S3-06, not S2-05.
3. Edit `docs/phases/00-bullet-tracer-foundations/phase-arch-design.md §Component design — Audit writer` (line ~599) to use `os_kernel_sha` consistently with the §Data model section (line ~722).
4. Future: open an ADR-amendment for `Probe.version` if the convention's lack of static declaration becomes a `mypy --strict` friction point in Phase 1+ probes.
