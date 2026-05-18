# Story S8-02 — CLI summary block on stdout: `secrets_redacted_count`, fingerprints, `skill_shadowed`

**Step:** Step 8 — Confidence section renderer + CI ratchet + advisory benches + Phase-3 handoff
**Status:** HARDENED
**Effort:** S
**Depends on:** S8-01 (`CONTEXT_REPORT.md` rendered alongside `repo-context.yaml`); S3-03 (writer chokepoint already emits `envelope.written` + `secrets_redacted_count` field — this story consumes that, does **not** add a new event); S2-01 (`SkillsLoader` — this story extends `LoadOutcome` additively to surface shadow records as **data**, not just structlog events)
**ADRs honored:** 02-ADR-0005 (no plaintext persistence — fingerprints only, 8-hex BLAKE3 only); 02-ADR-0008 (**no new Phase-2 structlog events** — this story adds zero new events; `tests/unit/test_no_event_stream_in_phase_2.py` discipline is preserved); 02-ADR-0010 (`RedactedSlice.findings_count` + `RedactedSlice.fingerprints` are the persisted-by-construction fields the CLI reads)

## Validation notes (2026-05-18 — phase-story-validator)

This story was hardened by `phase-story-validator`. The draft was substantially restructured because it contradicted three sources of truth in the codebase and the ADRs:

1. **ADR-0008 contradiction.** Draft added three new structlog events (`secrets.summary`, `fingerprints.summary`, `skills.shadowed.summary`). 02-ADR-0008 forbids new Phase-2 events: *"the discipline is 'no Phase-2 events'; the test enforcing this is `tests/unit/test_no_event_stream_in_phase_2.py`."* Resolution: zero new events; consume the existing `envelope.written` event for `secrets_redacted_count`; the other two fields are **stdout-only** observability.
2. **Duplicate emission.** Draft re-introduced `secrets_redacted_count` as a new event payload. `src/codegenie/output/writer.py:250-253` already emits it on `envelope.written` (per S3-03 / Phase-1). Resolution: AC-2 now asserts the existing event carries the count once per gather; the stdout line reflects the *same* in-memory value, asserted via equality.
3. **Fictional Phase-0 anchor.** Draft AC-1 asserted "Phase 0 already prints a per-probe `Ran/CacheHit/Skipped` audit anchor" on stdout and required byte-for-byte preservation. `src/codegenie/cli.py` has zero `print()` calls; the audit anchor is the JSON `runs/<utc-iso>-<short>.json` file + the `coordinator.dispatch.order` structlog event. Resolution: this story **introduces** the first stdout surface in `cli.py`; AC-1 reframed as "no stdout regression vs. master baseline (assertion: the *only* lines on stdout during a clean gather are the three this story adds)."
4. **Wrong event name / field.** Draft AC-4 referenced `probe.skill.shadowed` event and `shadowed_by_tier` field. Actual event in `src/codegenie/skills/loader.py:430-437` is `skill_shadowed` (constant `_EVENT_SHADOWED`) with fields `skill_id, winning_tier, shadowed_tier, winning_path, shadowed_path`. Resolution: import the constants by name; render `<skill_id>:<shadowed_tier>` using the real field name; assert names match the loader's module-level constants.
5. **Missing fixture.** `tests/fixtures/portfolio/secret-seeded/` does not exist; S6-07's `tests/adv/phase02/test_secret_in_source.py` is the actual landing spot. Resolution: AC-2/AC-3 use `tmp_path`-seeded inline secrets (the original draft's hedged fallback); no new portfolio fixture introduced unless S6-07's adversarial fixture is already reachable from `tests/integration/cli/` via direct path import.
6. **Phantom writer return struct.** Draft told the implementer to add `secret_findings: list[SecretFinding]` to "the writer's typed result struct." `Writer.write` returns `None`. The redactor's `RedactedSlice.fingerprints` (`list[str]`) and `RedactedSlice.findings_count` (`int`) are already in scope at `_seam_redact_envelope` in `cli.py:349`. Resolution: no writer-struct widening; consume the existing `RedactedSlice` fields directly.
7. **AC-4 plumbing precondition.** `SkillsIndexProbe` (`src/codegenie/probes/layer_d/skills_index.py:197-234`) calls `SkillsLoader().load_all()` during gather but `LoadOutcome` does not surface shadowing as **data** — shadows are only emitted as structlog events. Resolution: this story extends `LoadOutcome` with `shadowed_skills: tuple[ShadowedSkill, ...]` (an additive change to S2-01's API) and threads it through `SkillsIndexSlice` so the CLI reads shadows from the same coordinator-merged envelope. **No** structlog-event-stream interception; data path only.
8. **`!r`-formatter bug.** Draft GREEN code: `print(f"fingerprints={fps!r}")`. `repr(["aaaaaaaa"])` produces `['aaaaaaaa']` (single-quoted). The draft's AC-3 regex rejected quoted entries, so the prescribed implementation could not pass the prescribed test. Resolution: explicit `f"fingerprints=[{', '.join(fps)}]"`; AC-3 regex matches the unquoted shape.
9. **Plaintext-boundary holes.** Draft AC-3 enumerated only `AKIA…` and `ghp_…`. The redactor's `_PATTERNS` catalog has six pattern classes (`aws_access_key`, `github_token`, `jwt`, `rsa_private_key`, `npm_token`, `anthropic_key`) plus entropy. Resolution: the test iterates `sanitizer._PATTERNS` so the boundary check co-evolves with the catalog — single source of truth, mutation-resistant.
10. **Missing determinism property.** Draft mentioned determinism in implementer notes but had no AC. Resolution: AC-9 added — two consecutive gathers on the same fixture produce **byte-identical** summary blocks.
11. **Pure-impure tangle.** Draft `_emit_phase2_summary(findings, shadowed)` mixed sort/dedup/format with `print`. Resolution: pure `summary_block(count, fingerprints, shadowed) -> SummaryBlock` (frozen dataclass with `as_lines() -> tuple[str, str, str]`) + impure `_emit_summary_block(block)` that calls `print`. Pure helper is unit-testable without log-capture, mirrors S8-01's `render_confidence_section` / writer split.
12. **Anaemic shadow strings.** Draft passed shadows as `list[str]` already in `"<skill_id>:<tier>"` shape — re-parsing required by consumers. Resolution: typed `ShadowedSkill` frozen dataclass (already inferred in the loader's emit kwargs); formatting is the last step before `print`, not the carrier shape.

Full critic findings + decision rationale archived at [_validation/S8-02-cli-summary-line.md](_validation/S8-02-cli-summary-line.md). Verdict: **HARDENED**.

## Context

Phase 2 commits to **zero plaintext in any persisted file** (G5; production ADR-0005; phase ADR-0005). The audit-trail for secret findings has to be observable *somewhere*. Three observable surfaces exist in this phase:

- `repo-context.yaml` — the artifact (persisted; secret findings appear as `<REDACTED:fingerprint=BLAKE3_8>` placeholders + `RedactedSlice.fingerprints` carries the deduplicated 8-hex prefixes as a top-level field).
- `CONTEXT_REPORT.md` — the human-readable companion (S8-01; consumes `IndexFreshness`, not `SecretFinding`).
- **`envelope.written` structured-log event** — already emitted by `src/codegenie/output/writer.py:250-253` carrying `secrets_redacted_count: int` per S3-03. This is the *only* structured-log surface 02-ADR-0008 permits for Phase-2 secret-redaction observability.

Plus the operator-facing stdout surface, which is what this story introduces. The CLI summary block is three lines printed to stdout at the end of a clean gather, in this order:

```
secrets_redacted_count=<N>
fingerprints=[<8hex>, <8hex>, ...]
skill_shadowed=[<skill_id>:<shadowed_tier>, ...]
```

The values are computed from data already in scope at the end of the gather pipeline — no new structlog events, no widening of the writer's return type, no new persistence surfaces. The discipline 02-ADR-0008 enforces (`tests/unit/test_no_event_stream_in_phase_2.py`) is preserved.

The `skill_shadowed` line aggregates the three-tier-merge shadowing events that `SkillsLoader` currently emits only via structlog (`src/codegenie/skills/loader.py:430-437`). This story makes shadowing observable as **data** by extending `LoadOutcome` and `SkillsIndexSlice` with a `shadowed_skills: tuple[ShadowedSkill, ...]` field — the structlog event stays in place (operators who tail logs already see it), but the CLI now reads the aggregated list from the coordinator-merged envelope instead of intercepting events.

This is one of the smallest stories in Step 8 but load-bearing for the operator's ability to confirm that the redactor ran and that no skill silently shadowed another in a multi-tier deployment.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md` §"Logging"](../phase-arch-design.md) — *"Phase 2 adds **one** log field at the writer: `secrets_redacted_count` (int), so a 0-count run is grep-able."* Already shipped via S3-03.
  - [`../phase-arch-design.md` §"Component design" #4 `SecretRedactor`](../phase-arch-design.md) — *"The returned `list[SecretFinding]` is collected in-memory for the CLI summary line; it is NOT persisted to any file."* Fingerprint = first 8 hex of BLAKE3.
  - [`../phase-arch-design.md` §"Component design" §"SkillsLoader"](../phase-arch-design.md) — *"first-tier-wins; collisions emit a `skill_shadowed` warning in the CLI summary."*
  - [`../phase-arch-design.md` §"Process view" step 9](../phase-arch-design.md) — CLI exit; *"`ProbeOutput emitted; CONTEXT_REPORT.md printed`"*. This story extends step 9 with the stdout block, **after** `CONTEXT_REPORT.md` is written and **before** the CLI returns.
- **Phase ADRs:**
  - [`../ADRs/0005-secret-findings-no-plaintext-persistence.md`](../ADRs/0005-secret-findings-no-plaintext-persistence.md) — fingerprints, no plaintext; 8-hex BLAKE3.
  - [`../ADRs/0008-no-event-stream-in-phase-2.md`](../ADRs/0008-no-event-stream-in-phase-2.md) — **no new Phase-2 events.** This story honors that. The `tests/unit/test_no_event_stream_in_phase_2.py` discipline must stay green after this story lands.
  - [`../ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md`](../ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md) — `RedactedSlice.findings_count` + `RedactedSlice.fingerprints` are the existing typed fields the CLI reads. Both are persisted by construction; the CLI does **not** invent a parallel data path.
- **Production ADRs:**
  - [`../../../production/adrs/0005-no-llm-in-gather.md`](../../../production/adrs/0005-no-llm-in-gather.md) — Phase 0 fence; CLI summary block is plain Python `print`, no LLM.
  - [`../../../production/adrs/0033-domain-modeling-discipline.md`](../../../production/adrs/0033-domain-modeling-discipline.md) §3 — illegal-states-unrepresentable; `SecretFinding` and `ShadowedSkill` are Pydantic frozen models.
- **Source design:**
  - [`../final-design.md` §"Component design" row 4 (`SecretRedactor`)](../final-design.md) — CLI summary path returned separately by `redact_secrets`, not threaded into a `RedactedSlice`.
- **Existing code (Phase 2 contract — DO NOT WEAKEN):**
  - `src/codegenie/output/sanitizer.py:258` — `SecretFinding(probe_name, fingerprint, pattern_class, cleartext_len)` frozen model; `_PATTERNS` six-class catalog at module level (the test iterates this for the plaintext-boundary check).
  - `src/codegenie/output/redacted_slice.py` — `RedactedSlice(slice, findings_count, fingerprints)`; the CLI reads `fingerprints` and `findings_count` directly.
  - `src/codegenie/output/envelope_redactor.py:274` — `_redact_envelope(envelope) -> RedactedSlice`; called by `cli._seam_redact_envelope`. The returned `RedactedSlice.fingerprints` is deduplicated by insertion order.
  - `src/codegenie/output/writer.py:250-253` — already emits `envelope.written` with `secrets_redacted_count = envelope.findings_count`. **DO NOT** add a parallel event; consume the existing one.
  - `src/codegenie/logging.py` — `EVENT_ENVELOPE_WRITTEN` / `SECRETS_REDACTED_COUNT_FIELD` constants. Import by name; do not hardcode strings at the call site.
  - `src/codegenie/skills/loader.py:86,430-437` — `_EVENT_SHADOWED = "skill_shadowed"` constant; event payload has `skill_id, winning_tier, shadowed_tier, winning_path, shadowed_path`. `LoadOutcome` currently exposes `skills, per_file_errors` only — this story adds `shadowed_skills: tuple[ShadowedSkill, ...]` to `LoadOutcome` (additive).
  - `src/codegenie/probes/layer_d/skills_index.py:197-234` — `SkillsIndexProbe.run`; this story extends `SkillsIndexSlice` with `shadowed_skills: tuple[ShadowedSkill, ...]` and writes the field into `schema_slice`.
  - `src/codegenie/cli.py:349` — `_seam_redact_envelope`; the `RedactedSlice` is already in scope at the call site, so the CLI summary block consumes its `findings_count` and `fingerprints` directly with no further plumbing.
  - `src/codegenie/cli.py:434-639` — `_run_gather_pipeline` (11 steps); this story adds Step 11.5 (the stdout summary block) between the existing Step 11 (audit record) and CLI return.
  - `tests/smoke/conftest.py` — the `_seam_configure_logging` no-op fixture that keeps `structlog.testing.capture_logs()` working during `CliRunner.invoke`. Reuse this style for any new CLI integration test.
  - `tests/smoke/test_cli_end_to_end.py:39,234,256,294,315` — `from structlog.testing import capture_logs` precedent.

## Goal

Extend `src/codegenie/cli.py` to emit a three-line summary block on stdout **after** Step 11 (audit record) succeeds and **before** the CLI returns. The block contains, in this exact order:

1. `secrets_redacted_count=<N>` — `N == redacted_envelope.findings_count` (the same value already emitted on the `envelope.written` structured-log event).
2. `fingerprints=[<8-hex>, <8-hex>, ...]` — `redacted_envelope.fingerprints` (already deduplicated by `_build_redacted_slice_pass`), re-sorted ASCII-lex for determinism. Empty list rendered as `fingerprints=[]`. **Never** the plaintext value, **never** a hash longer than 8 hex.
3. `skill_shadowed=[<skill_id>:<shadowed_tier>, ...]` — one entry per `ShadowedSkill` returned by `LoadOutcome.shadowed_skills` (read off the `SkillsIndexProbe`'s slice), ASCII-sorted by `(skill_id, shadowed_tier)`. Empty list rendered as `skill_shadowed=[]`.

Formatting discipline:

- Pure formatter `summary_block(count: int, fingerprints: tuple[str, ...], shadowed: tuple[ShadowedSkill, ...]) -> SummaryBlock` lives in a new module `src/codegenie/cli_summary.py`. No I/O, no logger, no clock, no env reads.
- Impure shell: `_emit_summary_block(block: SummaryBlock)` calls `print` three times on stdout. This is the **only** new impure code.
- No new structlog events (02-ADR-0008). The existing `envelope.written` carries `secrets_redacted_count`; the other two stdout lines have **no** structured-log counterpart and that is intentional.

## Acceptance criteria

- [ ] **AC-1 (No regression on existing CLI observability — stdout introduced cleanly).** Before this story, `src/codegenie/cli.py` produces zero stdout during a clean gather (verified by `grep -rn "print(\|click.echo" src/codegenie/cli.py` returning empty on master). After this story, stdout contains **exactly** the three lines defined in the Goal, in order, separated by single newlines, with no leading/trailing blank lines. `tests/integration/cli/test_summary_stdout_shape.py::test_only_three_lines` runs a gather against `tests/fixtures/portfolio/minimal-ts` and asserts `len(stdout.strip().split("\n")) == 3`.
- [ ] **AC-2 (`secrets_redacted_count` line and event share the same value).** Stdout contains a line matching `^secrets_redacted_count=\d+$`. The structured-log event captured by `structlog.testing.capture_logs()` shows `Counter(e["event"] for e in captured)["envelope.written"] == 1` and the event's `secrets_redacted_count` field equals the integer parsed from the stdout line. `tests/integration/cli/test_summary_count_matches_event.py::test_count_equals_envelope_written_field` asserts this against `minimal-ts` (count == 0) and against a `tmp_path` fixture seeded with one `AKIA[0-9A-Z]{16}` plaintext in a tracked file (count == 1). **No** new `secrets.summary` event is emitted (asserted by `Counter(...)["secrets.summary"] == 0`).
- [ ] **AC-3 (`fingerprints` line: 8-hex only, sorted, deduplicated, no plaintext — mutation-resistant against the full pattern catalog).** Stdout contains a line matching `^fingerprints=\[(?:[0-9a-f]{8}(?:, [0-9a-f]{8})*)?\]$`. The list is ASCII-sorted (`sorted(set(redacted_envelope.fingerprints))`). The plaintext-boundary assertion iterates `codegenie.output.sanitizer._PATTERNS` and seeds one example per pattern class via `tmp_path`; for each pattern, the captured stdout (and the captured structured-log payload of `envelope.written`) is asserted to NOT contain the seeded plaintext. This is the boundary test for 02-ADR-0005; weakening either side (the iteration over `_PATTERNS` or the assertion) is a build break. `tests/unit/cli/test_summary_fingerprints_format.py` covers the format regex + sort + dedup (with property-based generation via `hypothesis.strategies.text(alphabet="0123456789abcdef", min_size=8, max_size=8)`); `tests/integration/cli/test_summary_plaintext_boundary.py` covers the per-pattern boundary check.
- [ ] **AC-4 (`skill_shadowed` line aggregated from `LoadOutcome.shadowed_skills` — data path, not event interception).** The `SkillsLoader.load_all()` `LoadOutcome` carries a new `shadowed_skills: tuple[ShadowedSkill, ...]` field (additive to S2-01). `ShadowedSkill` is a frozen Pydantic model with fields `skill_id: SkillId, shadowed_tier: Tier, winning_tier: Tier, shadowed_path: str, winning_path: str` — the same fields the existing structlog event already populates. `SkillsIndexProbe` projects this tuple into `SkillsIndexSlice.shadowed_skills` (additive to S2-01's sub-schema with `additionalProperties: false`). The CLI reads it off `gather_result.outputs["skills_index"].schema_slice["shadowed_skills"]`, sorts by `(skill_id, shadowed_tier)` ASCII-lex, formats one entry per shadow as `f"{skill_id}:{shadowed_tier}"`, and renders `skill_shadowed=[entry, entry, ...]`. The existing `skill_shadowed` structlog event continues to fire once per collision (no change to S2-01's emit-once contract). `tests/integration/cli/test_summary_skill_shadowed_data_path.py` builds a `tmp_path`-rooted fixture with two tiers defining the same `skill_id` (one repo, one org), runs a gather, and asserts the stdout line matches the data path AND that `Counter(...)["skill_shadowed"] == 1` (the per-collision event still fires once). Zero collisions → `skill_shadowed=[]`.
- [ ] **AC-5 (summary block emits *after* Step 11 audit record write succeeds, *before* CLI exit code 0).** `tests/integration/cli/test_summary_order_after_audit.py` runs a gather and asserts (a) stdout sequence: the three summary lines appear *after* the captured-log event `envelope.written` (which is itself emitted after the writer's `_atomic_write_bytes` returns — the audit anchor is on disk by the time stdout's first byte is written); (b) the CLI exit code is 0 on a clean gather, irrespective of `secrets_redacted_count` value. The implementation places the summary emission inside the `_run_gather_pipeline` body after the Step 11 `_seam_audit_record` call returns.
- [ ] **AC-6 (no new Phase-2 structlog events introduced — ADR-0008 discipline preserved).** `tests/unit/test_no_event_stream_in_phase_2.py` remains green after this story lands. Additionally, `tests/unit/cli/test_summary_no_new_events.py` runs a gather under `capture_logs()` and asserts `Counter(e["event"] for e in captured)` contains exactly the event names present in the master baseline (a frozen set captured as `_EVENTS_BASELINE` at the top of the test file, sourced from a recent clean gather); no key like `secrets.summary`, `fingerprints.summary`, `skills.shadowed.summary`, or any new event name appears. A mutation that introduces a new event fails this test.
- [ ] **AC-7 (zero-state grep-ability — all three lines always present on a clean gather).** Per phase-arch-design.md §"Logging" — *"a 0-count run is grep-able."* `tests/integration/cli/test_summary_zero_state.py` runs against `minimal-ts` (no seeded secrets, no skill collisions) and asserts stdout contains the literal substrings `secrets_redacted_count=0`, `fingerprints=[]`, and `skill_shadowed=[]`.
- [ ] **AC-8 (pure formatter / impure shell split — `summary_block` is testable without log capture).** `src/codegenie/cli_summary.py` exposes a pure function `summary_block(count: int, fingerprints: tuple[str, ...], shadowed: tuple[ShadowedSkill, ...]) -> SummaryBlock`. `SummaryBlock` is a frozen `@dataclass` with one method `as_lines() -> tuple[str, str, str]`. `tests/unit/cli/test_summary_block_pure.py` constructs `SummaryBlock` instances directly (no gather, no logger, no `tmp_path`) and asserts: (a) format regexes for each line; (b) idempotence — `summary_block(*args) == summary_block(*args)`; (c) sortedness — `block.as_lines()[1]` lists fingerprints in ASCII-lex order; (d) dedup — supplying duplicate fingerprints yields the same output as supplying the deduplicated set. A mutation that makes any field impure (reads clock / env / I/O) is caught by static AST inspection in `test_summary_block_pure.py::test_pure_no_io_imports` (greps `cli_summary.py` for `import os|import time|open(|print(|logger`).
- [ ] **AC-9 (determinism — two consecutive gathers produce byte-identical summary blocks).** `tests/integration/cli/test_summary_determinism.py` runs two gathers back-to-back against `minimal-ts` (same source tree, same cache), captures stdout from each, and asserts `stdout_1 == stdout_2` byte-for-byte. Run against a fixture with three distinct seeded secrets to exercise the sort+dedup branch on a non-empty list.
- [ ] **AC-10 (`mypy --strict` + `ruff` + `lint-imports` + `fence` green).** `mypy --strict src/codegenie/cli_summary.py src/codegenie/cli.py src/codegenie/skills/loader.py src/codegenie/skills/model.py src/codegenie/probes/layer_d/skills_index.py` passes. `ruff check` + `ruff format --check` green on all touched files. `make lint-imports` green (no new cross-package edges; `cli_summary` is a leaf module that imports only `dataclasses`, `codegenie.skills.model.ShadowedSkill`, and stdlib). `make fence` green (no LLM/network imports introduced).

## Out of scope

- Adding any new structlog event variant. 02-ADR-0008 forbids it; `tests/unit/test_no_event_stream_in_phase_2.py` enforces it. The existing `envelope.written` and `skill_shadowed` events are the **only** structured-log surfaces for this story's concerns.
- Persisting the `list[SecretFinding]` (with `pattern_class` / `cleartext_len`) to any file. 02-ADR-0005 forbids this; fingerprints + count already live in `RedactedSlice` and are persisted-by-construction (per ADR-0010).
- Rendering fingerprints or shadowed skills in `CONTEXT_REPORT.md`. The renderer (S8-01) consumes `IndexFreshness`. A future story can extend the renderer; this one does not.
- A `--json` summary-block mode. The stdout block is human-readable; structured-log events ARE the machine-readable surface; future task classes consume the YAML envelope.
- Pagination of `fingerprints` or `skill_shadowed` when the lists are huge. A 1000-fingerprint line is a signal worth surfacing, not hiding.
- Exit-code change on `secrets_redacted_count > 0`. The CLI exits 0; the operator decides if a non-zero count is actionable.
- Removing or relocating the existing `skill_shadowed` per-collision structlog event. It stays; the CLI is now an *additional* observer of the same data via the probe-slice data path.
- A `ShadowedSkill` model in `src/codegenie/types/identifiers.py`. The dataclass lives in `src/codegenie/skills/model.py` next to `Skill` and `Tier`.

## Files to touch

**New:**

- `src/codegenie/cli_summary.py` — pure `SummaryBlock` frozen dataclass + `summary_block(...)` factory + `as_lines()` formatter. ~40 LOC. No I/O.
- `tests/unit/cli/test_summary_block_pure.py` — AC-8 (pure formatter unit tests, hypothesis property tests for sort+dedup).
- `tests/unit/cli/test_summary_no_new_events.py` — AC-6 (baseline-vs-current event-name diff).
- `tests/unit/cli/test_summary_fingerprints_format.py` — AC-3 format regex + property-based dedup/sort.
- `tests/integration/cli/test_summary_stdout_shape.py` — AC-1 (exactly three lines, correct order).
- `tests/integration/cli/test_summary_count_matches_event.py` — AC-2 (stdout int == `envelope.written` field).
- `tests/integration/cli/test_summary_plaintext_boundary.py` — AC-3 (iterates `sanitizer._PATTERNS`; tmp_path-seeded plaintext per pattern; asserts none of the plaintexts appear in stdout or in `envelope.written` event payload).
- `tests/integration/cli/test_summary_skill_shadowed_data_path.py` — AC-4 (tmp_path two-tier collision fixture; asserts stdout line + existing event still fires once).
- `tests/integration/cli/test_summary_order_after_audit.py` — AC-5.
- `tests/integration/cli/test_summary_zero_state.py` — AC-7.
- `tests/integration/cli/test_summary_determinism.py` — AC-9 (two consecutive gathers, byte-identical stdout).

**Modified:**

- `src/codegenie/cli.py` — append a `_emit_phase2_summary(redacted_envelope, skills_slice)` helper invoked at the end of `_run_gather_pipeline` after `_seam_audit_record` returns. ~20 LOC delta. Reads `redacted_envelope.findings_count`, `redacted_envelope.fingerprints` (both already in scope at line 614+), and `gather_result.outputs.get("skills_index", ...).schema_slice.get("shadowed_skills", [])`. Calls `summary_block(...)` then `_emit_summary_block(block)`. Does NOT thread through the writer.
- `src/codegenie/skills/model.py` — add `ShadowedSkill` frozen Pydantic model (`skill_id: SkillId, shadowed_tier: Tier, winning_tier: Tier, shadowed_path: str, winning_path: str`). ~15 LOC.
- `src/codegenie/skills/loader.py` — extend `LoadOutcome` with `shadowed_skills: tuple[ShadowedSkill, ...]` (additive, default empty tuple). Append a `ShadowedSkill(...)` to a local accumulator in the collision branch at line 428-438 *in addition to* the existing `_logger.warning(_EVENT_SHADOWED, ...)` call. Return the accumulator in the `Ok(LoadOutcome(...))` at line 449-454. ~10 LOC delta.
- `src/codegenie/probes/layer_d/skills_index.py` — extend `SkillsIndexSlice` (in the same file or its model module) with `shadowed_skills: tuple[ShadowedSkill, ...]` (default empty). Pass `outcome.shadowed_skills` into the slice constructor at line 218-222. ~5 LOC delta.
- `src/codegenie/schema/probes/skills_index.schema.json` — add a `shadowed_skills` array property; per-item schema mirrors `ShadowedSkill` fields. Maintain `additionalProperties: false`. (Per the project's Phase 1 ADR-0004 sub-schema discipline.)

**Untouched (DO NOT EDIT):**

- `src/codegenie/output/writer.py` — already emits `envelope.written` with `secrets_redacted_count`; do **not** add another field, do **not** widen `Writer.write`'s return.
- `src/codegenie/output/sanitizer.py` (`redact_secrets` signature is frozen by S3-01/S3-02).
- `src/codegenie/output/envelope_redactor.py` (`RedactedSlice` shape frozen by 02-ADR-0010).
- `src/codegenie/logging.py` — `EVENT_ENVELOPE_WRITTEN` / `SECRETS_REDACTED_COUNT_FIELD` constants stay as the single source of truth; the new tests import them by name.
- `CONTEXT_REPORT.md` renderer (S8-01).
- `tests/unit/test_no_event_stream_in_phase_2.py` — must stay green after this story.

## TDD plan — red / green / refactor

**RED (failing tests committed first):**

1. `test_summary_block_pure.py::test_format_regex_each_line` — constructs `SummaryBlock(count=0, fingerprints=(), shadowed=())` and asserts the three lines match their format regexes. Fails red — `cli_summary.py` does not exist yet.
2. `test_summary_block_pure.py::test_sort_and_dedup_property` — hypothesis property test generating `list[str]` of 8-hex strings (with deliberate duplicates and unsorted order); asserts `block.as_lines()[1]` parses to a sorted unique list. Fails red.
3. `test_summary_block_pure.py::test_pure_no_io_imports` — AST/grep assertion that `cli_summary.py` does not `import os | time | open | print | logger | structlog`. Fails red once the module exists if any I/O imports leak in.
4. `test_summary_stdout_shape.py::test_only_three_lines` — runs `codegenie gather minimal-ts` via `CliRunner`; asserts `len(stdout.strip().split("\n")) == 3` and the lines start with `secrets_redacted_count=`, `fingerprints=`, `skill_shadowed=` in order. Fails red — the CLI does not print yet.
5. `test_summary_count_matches_event.py::test_count_equals_envelope_written_field` — same gather under `capture_logs()`; asserts `int(stdout_count_line.split("=")[1]) == captured_event["envelope.written"]["secrets_redacted_count"]`. Fails red.
6. `test_summary_fingerprints_format.py::test_fingerprints_format_regex` — constructs a `SummaryBlock` with three known 8-hex fingerprints; asserts stdout line matches the format regex. Fails red.
7. `test_summary_plaintext_boundary.py::test_no_pattern_class_plaintext_in_stdout` — parameterized over `codegenie.output.sanitizer._PATTERNS`; for each pattern, seeds an example plaintext in a `tmp_path` tracked file, runs gather, asserts the plaintext is NOT in `result.stdout` AND not in any captured-log event payload (serialized to string). Fails red.
8. `test_summary_skill_shadowed_data_path.py::test_collision_renders_stdout_entry` — builds a `tmp_path` fixture with `~/.codegenie/skills-org/foo/SKILL.md` and `<repo>/.codegenie/skills/foo/SKILL.md` (same `skill_id`); runs gather; asserts `skill_shadowed=[foo:org]` (or whatever the actual `shadowed_tier` string is — assert against the loader's `_EVENT_SHADOWED` payload, single source of truth). Asserts `Counter(captured)["skill_shadowed"] == 1`. Fails red — `LoadOutcome.shadowed_skills` does not exist yet.
9. `test_summary_order_after_audit.py::test_stdout_after_envelope_written` — captures stdout + log event timeline; asserts first stdout byte appears after the `envelope.written` event's timestamp. Fails red.
10. `test_summary_no_new_events.py::test_event_names_match_baseline` — runs a clean gather, captures all event names, asserts `set(event_names) == _EVENTS_BASELINE` (a constant defined at the top of the test, sourced from a fresh master-branch gather output). Fails red the moment a new event is introduced.
11. `test_summary_zero_state.py::test_three_zero_lines_present` — runs gather on `minimal-ts`; asserts `secrets_redacted_count=0`, `fingerprints=[]`, `skill_shadowed=[]` all literally in stdout. Fails red.
12. `test_summary_determinism.py::test_byte_identical_across_two_runs` — runs gather twice on the same fixture; asserts byte equality. Fails red.

**GREEN (minimum code to pass):**

1. Create `src/codegenie/cli_summary.py` with the pure `SummaryBlock` dataclass + `summary_block()` factory + `as_lines()` formatter. Use `f"fingerprints=[{', '.join(sorted(set(fingerprints)))}]"` (no `!r`).
2. Add `ShadowedSkill` to `src/codegenie/skills/model.py` (Pydantic frozen model).
3. Extend `LoadOutcome` in `src/codegenie/skills/loader.py` with `shadowed_skills: tuple[ShadowedSkill, ...]`; in the collision branch, append a `ShadowedSkill(skill_id=skill.id, shadowed_tier=tier, winning_tier=prior_tier, shadowed_path=str(skill_md), winning_path=str(prior_path))` to a local accumulator; return it in the `Ok(LoadOutcome(...))`.
4. Extend `SkillsIndexSlice` (in `probes/layer_d/skills_index.py` or its model module) with `shadowed_skills: tuple[ShadowedSkill, ...]`; pass `outcome.shadowed_skills` into the constructor.
5. Add `shadowed_skills` array to `src/codegenie/schema/probes/skills_index.schema.json` (per-item schema; `additionalProperties: false`).
6. In `src/codegenie/cli.py`, at the end of `_run_gather_pipeline` (after `_seam_audit_record` returns), read `redacted_envelope.findings_count`, `redacted_envelope.fingerprints`, and `gather_result.outputs.get("skills_index", ProbeOutput()).schema_slice.get("shadowed_skills", [])`; construct a `SummaryBlock` via `summary_block(...)`; call `_emit_summary_block(block)` which calls `print(line)` for each of `block.as_lines()`.

**REFACTOR:**

- Confirm the pure / impure split holds: `cli_summary.py` has no `import os | time | open | print | logger`; the only import beyond stdlib is `codegenie.skills.model.ShadowedSkill`.
- Confirm `make lint-imports` does not flag a new cross-package edge.
- Confirm `tests/unit/test_no_event_stream_in_phase_2.py` is still green.
- `mypy --strict` across touched files; `ruff format`, `ruff check` clean.
- Manual sanity check: run `codegenie gather <minimal-ts>` and `grep secrets_redacted_count=0` on stdout — both succeed.

## Notes for the implementer

- **No new structlog events. 02-ADR-0008 is binding.** If you find yourself reaching for `_log.info("secrets.summary", ...)` or `_log.info("fingerprints.summary", ...)`, stop. The existing `envelope.written` event carries `secrets_redacted_count`; the other two stdout fields have NO structured-log counterpart, and that is the deliberate decision per ADR-0008 §Decision and `tests/unit/test_no_event_stream_in_phase_2.py`.
- **ADR-0005 boundary test is AC-3's plaintext regex, iterated over `_PATTERNS`.** Non-negotiable. If a future contributor adds a 7th pattern class to `sanitizer._PATTERNS`, the test automatically exercises it. Do NOT enumerate the pattern shapes in the test file — read them off the module-level constant.
- **Fingerprint truncation is 8 hex chars, period.** Not 16, not the full BLAKE3. ADR-0005 chose 8 to make brute-force fingerprint→plaintext infeasible while keeping the line scannable. `RedactedSlice.fingerprints` already enforces 8-hex; do not re-truncate or re-hash.
- **Zero-state grep-ability matters for ops.** `grep secrets_redacted_count=0 <gather.stdout>` should always succeed on a clean gather. Always print all three lines, even when empty.
- **`SkillsIndexProbe` may not run** (the probe registry filters by task type). If `gather_result.outputs.get("skills_index")` is `None`, render `skill_shadowed=[]` — the operator-visible signal is still "no shadowing observed in this gather," even though the underlying reason is "the probe didn't run." A future story can split this signal if the ambiguity becomes load-bearing; today it does not.
- **Determinism: sort fingerprints and shadowed entries ASCII-lex.** The dedup in `RedactedSlice.fingerprints` is insertion-order; this story's `summary_block` does the lex sort. The same gather on the same fixture must produce a byte-identical summary block across runs (AC-9 verifies this).
- **`SkillId` and `Tier` are domain primitives.** If they are not already newtypes in `src/codegenie/types/identifiers.py` (check `git grep "SkillId = NewType"`), `ShadowedSkill` should still use the existing strings from the loader's emit kwargs — do **not** invent a newtype as a side-effect of this story. Surface it as a follow-on if the loader exposes raw `str`.
- **Rule 2 — no registry for three fields.** Three stdout lines with three lines of code each is below the abstraction threshold. If a 4th summary field lands in Phase 3 (e.g., per-plugin metrics from the first plugin), introduce `@register_summary_field(name)` *then*; not now. This pre-empts premature plugin-ification while documenting the OCP escape hatch.
- **Functional core, imperative shell.** `summary_block` is pure (the `test_pure_no_io_imports` AST test enforces this). `_emit_summary_block` is the only impure new code: three `print` calls. The pure helper is unit-testable without any gather setup; the impure shell is integration-tested via `CliRunner`.
- **No new dependency.** `structlog` is Phase 0 baseline; `print` is stdlib. Phase 0 `fence` stays green trivially.
- **Re-use S6-07's adversarial fixture only if it is reachable.** `tests/adv/phase02/test_secret_in_source.py` lands a seeded `AKIA…` somewhere; if its fixture is importable from `tests/integration/cli/`, reuse it. Otherwise use `tmp_path`-seeded inline secrets — do not duplicate fixture files in a new portfolio entry.
- **Re-entrancy: each `codegenie gather` invocation is a fresh process.** In production the CLI runs once per gather; in tests `CliRunner` simulates this. There is no need to engineer for "two gathers in one process" — the structlog `capture_logs` context manager wraps a single invocation and that is the unit of analysis.
- **Plumbing path is `cli.py` → `RedactedSlice` (already in scope at `_seam_redact_envelope`).** Do NOT widen `Writer.write`'s return type. Do NOT thread `list[SecretFinding]` anywhere. The redactor's full findings list lives only inside `envelope_redactor._PassState` and is not surfaced; the CLI consumes `RedactedSlice.findings_count` (`int`) and `RedactedSlice.fingerprints` (`list[str]`) directly.
