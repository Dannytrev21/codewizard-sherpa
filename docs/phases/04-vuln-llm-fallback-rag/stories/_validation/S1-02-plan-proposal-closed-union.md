# Validation report — S1-02 `PlanProposal` closed discriminated union

**Story:** `docs/phases/04-vuln-llm-fallback-rag/stories/S1-02-plan-proposal-closed-union.md`
**Validated:** 2026-05-21
**Validator:** phase-story-validator (story-validation-corrector scheduled task)
**Verdict:** HARDENED
**Findings:** 20 — 4 blocks, 10 hardens, 6 nits. One critic conflict resolved.

---

## Stage 1 — Context Brief

- **Goal:** ship the `PlanProposal` closed Pydantic v2 discriminated union (`dep_bump | override | callsite_rewrite | refuse`) at `src/codegenie/fallback/plan_proposal.py`, with a `UnifiedDiff` smart constructor (64 KB cap, path-escape, binary, no-op rejection), so every later Phase-4 module consumes the typed shape and the Anthropic SDK can be passed the schema as `response_format`.
- **Depends on:** S1-01 (newtype substrate, currently `HARDENED`, unexecuted).
- **ADRs:** phase ADR-0001 (closed sum type the LLM may emit), ADR-0004 (`PlanProposal` independent of `PlanOutcome`), production ADR-0033 (domain-modeling discipline).

### Docs / code read

- Story file (full), `phase-arch-design.md` (§Data model lines ~700–745, §Edge cases ~930–945, §Component design line ~477–483), phase ADR-0001 + ADR-0004 (full).
- `src/codegenie/types/identifiers.py` — grepped for the three types AC-3 names.
- `src/codegenie/transforms/_forward.py`, `transforms/sandbox_jail.py`, `plugins/sandbox_path.py` references — to identify the real path type.
- 7 discriminated-union sites across `indices/`, `probes/`, `plugins/` — to establish the codebase idiom.
- `tests/unit/probes/layer_c/test_scenario_result.py` — adjacent test conventions.
- `S1-01-newtype-smart-constructor-substrate.md` (full) — the dependency, to confirm what newtypes it actually ships.

### Open ambiguities surfaced during Stage 1

Two type names AC-3 depends on do not exist. This was not an ambiguity in the *story's meaning* but a factual precondition gap — proceeded to critics, resolved in Stage 4.

---

## Stage 2 — Critic findings

Consistency was performed directly by the validator (grep evidence is authoritative). Coverage, Test-Quality, and Design-Patterns ran as parallel subagents. No finding was tagged `NEEDS RESEARCH`; **Stage 3 (researcher) skipped.**

### Consistency (validator)

- **[block] C1 — `SandboxedRelativePath` does not exist.** `grep -rn 'SandboxedRelativePath' src/codegenie/` → 0 hits. The story's References, AC-3, Out-of-scope; S1-01's out-of-scope; and `phase-arch-design.md §Data model` (lines 479, 481, 723, 732–733) all call it a "Phase-3-owned newtype." It is not. The only path type is `codegenie.plugins.sandbox_path.SandboxedPath` — a jail-minted *absolute capability* (`transforms/_forward.py` documents it as "in-jail-at-construction"), structurally unusable as an LLM-emitted relative-path JSON string. S1-01 (the named dependency) ships 11 newtypes — `SandboxedRelativePath` is not among them and S1-01's own Out-of-scope explicitly punts it to "Phase 3 / S1-02."
- **[harden] C2 — `SemverString` does not exist.** The real Phase-3 newtype is `SemverVersion` (`NewType("SemverVersion", str)`, `identifiers.py:129`, smart constructor `parse_semver`).
- **[block] C3 — AC-2's v1/v2 premise is factually wrong.** AC-2 asserts `Field(discriminator=...)` is "Pydantic v1" and mandates `Discriminator(...)`. In Pydantic v2 *both* are valid; `Field(discriminator="kind")` is the recommended form for a plain string discriminator and the codebase's universal convention — 7+ shipped, tested unions: `indices/freshness.py:110`, `probes/_shared/scanner_outcome.py:136`, `probes/layer_c/_sbom_models.py:70`, `scenario_result.py` ×3, `probes/layer_c/_cve_models.py:70`, `plugins/bundle.py:268`. `Discriminator(...)` is a v2 construct for *callable* discriminators. Per Rule 11, the story must use `Field(discriminator="kind")`. The "Rule-7 conflict to surface" the story anticipates is a phantom. `assert_never` exhaustiveness over a `Field(discriminator=...)` union is already proven in-repo by `tests/unit/indices/test_freshness_assert_never.py`.

### Coverage critic

- [block] AC-6 `test_schema_lists_exactly_four_tags` escape hatch (`... or len(tags) == 4`) — a 4-wrong-tag or 4-canonical-plus-a-fifth schema passes.
- [block→harden] No AC verifies `model_json_schema()` output is SDK-`response_format`-shaped (the stated Goal). Downgraded to harden — full SDK wiring is S3-02; a lightweight structural smoke test is the right scope here.
- [harden] `--- /dev/null` new-file marker handling unspecified — would fail with a confusing path-escape error.
- [harden] CRLF line endings unspecified.
- [harden] `manifest_path` has no standalone validation AC.
- [harden] Proposed a *bidirectional* path check (`files` ⊆ diff-paths). **See conflict resolution below.**
- [nit] AC-7 mypy meta-test should assert stdout diagnostic content (also raised, stronger, by Test-Quality).

### Test-Quality critic

- [block] AC-6 schema-tag escape hatch (same as Coverage).
- [block] AC-7 `test_mypy_strict_rejects_incomplete_match` asserts only `returncode != 0`; an unrelated mypy failure (import resolution, missing stubs) green-washes it. Sibling S1-01's mypy-negative test checks stdout substrings — S1-02 dropped that rigor.
- [harden] `test_discriminator_routes` asserts only `isinstance` — an implementation that routes correctly but drops/defaults fields passes.
- [harden] Sad-path `ValidationError` tests don't assert *which* validation fired — a wrong-reason rejection passes.
- [harden] No 64 KB boundary off-by-one test (65 536 accepted / 65 537 rejected).
- [harden] Missing data round-trip property (`model → json → model`).
- [nit] Untyped test signatures vs. the repo's fully-annotated convention.
- [nit] `test_no_rationale_in_prompts.py` skeleton passes vacuously pre-`fallback/` — codebase-wide skeleton convention, nit only.

### Design-Patterns critic

- [block] AC-2 wrong idiom (same as Consistency C3) — confirmed `scenario_result.py` + `bundle.py` both use `Field(discriminator="kind")`.
- [harden] Four variants repeat `ConfigDict(frozen=True, extra="forbid")`; the Refactor section lifts the magic numbers but not the config. Recommend a module-level `_FROZEN_FORBID: Final` constant (cheaper + simpler than a shared base class under `mypy --strict`). Notes-level, not an AC.
- [harden] `PlanProposalRefuse.reason` inline `Literal` is correct per Rule 2 — story should explicitly acknowledge the tradeoff so it reads as intentional.
- [nit] mypy meta-test false-green if mypy absent from the venv — add `importorskip`/skip.
- [nit] `test_no_rationale_in_prompts.py` AST heuristic misses `str.format` / `%`-formatting — S2-04 must extend it.
- Open/Closed assessment: 5th-variant extension path is clean (new class + union member + match arm); the only cliff is the hard-coded `len(tags) == 4` (resolved by the AC-6 strict-set rewrite).

---

## Stage 4 — Synthesis, conflict resolution, edits

### Conflict resolved

**Coverage proposed a bidirectional path check** (every `files` entry must also appear in the diff, making it `files == diff-paths`). **Rejected — Consistency outranks Coverage.** `phase-arch-design.md §Data model` line 734 specifies `diff: UnifiedDiff  # … paths ⊆ files` — a deliberate *subset*, not equality. AC-4 keeps the one-directional `diff paths ⊆ files` check and now states the `⊆` relation explicitly so the executor does not over-tighten it.

### Edits applied to the story (HARDENED)

| # | Severity | Edit |
|---|---|---|
| F1 | block | AC-12 added — S1-02 defines `SandboxedRelativePath` itself as `Annotated[str, AfterValidator(_validate_sandboxed_relative_path)]` in `plan_proposal.py` (rejects empty, absolute, `..`, NUL, backslash). References / Out-of-scope / Notes / outline corrected. |
| F2 | block | AC-2 rewritten to `Field(discriminator="kind")`; References "verify idiom" bullet, Out-of-scope phantom-conflict bullet, Notes bullet 1, outline step 5, Green section all corrected. |
| F3 | block | AC-6 + TDD `test_schema_lists_exactly_four_tags` rewritten to strict `set(mapping) == {…}`. |
| F4 | block | AC-7 + TDD `test_mypy_strict_rejects_incomplete_match` now assert an exhaustiveness diagnostic substring in stdout; complete-match test asserts no `error:`. |
| F5 | harden | `SemverString` → `SemverVersion` throughout. |
| F6 | harden | AC-5 gains `manifest_path` sad-path tests (`../../etc/passwd`, absolute, empty); AC-12 supplies the validation. |
| F7 | harden | AC-4 + AC-5 + TDD: `--- /dev/null` new-file diffs explicitly rejected. |
| F8 | harden | AC-4 + AC-5 + TDD: CRLF (`\r`) diffs explicitly rejected. |
| F9 | harden | AC-4 mandates distinct error messages; AC-5 + TDD sad-path tests assert a keyword via `_err_text`. |
| F10 | harden | TDD: `test_diff_at_64kb_boundary_accepted` (65 536) + `test_diff_one_byte_over_boundary_rejected` (65 537). |
| F11 | harden | `test_discriminator_routes` asserts every input field is preserved, not just `isinstance`. |
| F12 | harden | AC-6 + TDD `test_json_round_trip_identity` data round-trip over all four variants. |
| F13 | harden | Goal / AC-2 / AC-6 / Context: `PlanProposal.model_json_schema()` → `TypeAdapter(PlanProposal).json_schema()` (`PlanProposal` is an `Annotated` alias). |
| F14 | harden | AC-6 + TDD `test_schema_is_sdk_shaped` structural smoke test. |
| F15 | nit | Notes + Refactor: lift `ConfigDict` to module-level `_FROZEN_FORBID: Final`. |
| F16 | nit | Notes: `PlanProposalRefuse.reason` inline `Literal` is intentional (Rule 2). |
| F17 | nit | Embedded test signatures annotated; Notes bullet mandates `-> None` everywhere. |
| F18 | nit | AC-7 + TDD `pytest.importorskip("mypy")`. |
| F19 | nit | Notes: `test_no_rationale_in_prompts.py` AST heuristic only catches f-strings; S2-04 must extend to `.format` / `%`. |
| F20 | nit | Arch edge-case citations corrected (#6/#20/#21/#22 → #8 / #15; binary + no-op are story-level). |

### Cross-story / cross-doc follow-ups (NOT edited by this validator)

- **`phase-arch-design.md §Data model`** names `SandboxedRelativePath` and `SemverString` as Phase-3 newtypes and shows `Discriminator("kind")`. All three are inaccurate. Recommend the arch doc be corrected: `SandboxedRelativePath` is Phase-4-owned (S1-02), `SemverString` → `SemverVersion`, `Discriminator("kind")` → `Field(discriminator="kind")`.
- **S1-01's Out-of-scope** still says `SandboxedRelativePath` is "Phase-3-owned; this story consumes them." Harmless now that S1-02 owns the definition, but stale — worth a one-line correction if S1-01 is re-touched before execution.

---

## Verdict rationale — why HARDENED, not RESCUE

The `SandboxedRelativePath` precondition gap (F1) is the only finding that approached RESCUE territory. It is **not** RESCUE because: the story's *goal* is sound and every AC traces to it; the gap is a missing precondition, not a goal-vs-arch contradiction; and it is cleanly patchable — S1-02 is the sole consumer, the type is small, and defining it as an `Annotated`-validated sibling of `UnifiedDiff` (which the story already builds) requires no new file and no fenced-surface reconciliation. RESCUE would have discarded all 19 other legitimate hardening edits. The story is now executable and self-consistent.
