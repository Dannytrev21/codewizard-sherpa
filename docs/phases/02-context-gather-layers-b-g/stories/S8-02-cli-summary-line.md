# Story S8-02 — CLI summary line: `secrets_redacted_count`, fingerprints, `skill_shadowed`, per-probe `Ran/CacheHit/Skipped`

**Step:** Step 8 — Confidence section renderer + CI ratchet + advisory benches + Phase-3 handoff
**Status:** Ready
**Effort:** S
**Depends on:** S8-01 (`CONTEXT_REPORT.md` rendered alongside `repo-context.yaml`)
**ADRs honored:** 02-ADR-0005 (secret findings — no plaintext persistence; CLI summary line is the **only** observable surface for `secrets_redacted_count` + fingerprints, **fingerprints only**); 02-ADR-0010 (`RedactedSlice` smart constructor — the redactor's in-memory findings list is the producer of the count and the 8-hex fingerprint list)

## Context

Phase 2 commits to **zero plaintext in any persisted file** (G5; production ADR-0005; ADR-0033 §3). The audit-trail for secret findings has to live *somewhere* — and the design's answer is the CLI summary line, returned in-memory by `redact_secrets` (not threaded through any `RedactedSlice` constructor, so it can't be persisted by accident). phase-arch-design.md §"Component design" #4: *"The returned `list[SecretFinding]` is collected in-memory for the CLI summary line; it is NOT persisted to any file."* The summary line is one of three observable surfaces a gather produces — `repo-context.yaml` (artifact), `CONTEXT_REPORT.md` (human-readable, S8-01), and the **summary line on stdout** (operator-facing).

Phase 0 already prints a per-probe `Ran/CacheHit/Skipped` audit anchor; Phase 2 extends it with three new fields:

- `secrets_redacted_count` — total count emitted by the writer chokepoint across all probes.
- `fingerprints` — the 8-hex BLAKE3 prefixes from `SecretFinding.fingerprint` (NEVER plaintext, NEVER the full BLAKE3 — explicit 8-hex truncation per ADR-0005).
- `skill_shadowed` warnings — one per collision surfaced by `SkillsLoader`'s three-tier merge (phase-arch-design.md §"Component design" §"`SkillsLoader`"; ADRs/README §"Decisions noted" #5).

The structured-logging discipline (phase-arch-design.md §"Logging" — `secrets_redacted_count` was already named as the **one** new log field Phase 2 adds at the writer) is the test surface: every field emits **exactly once per gather**. The CLI summary line is the human-readable rendering of those structured events; the test discipline asserts the structured events themselves so the line format stays free to evolve.

This is the smallest story in Step 8 — a CLI extension and a structured-log assertion harness — but it's load-bearing for ADR-0005: if `secrets_redacted_count` isn't observable, the "no plaintext" guarantee is unverifiable.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Logging"` — *"Phase 2 adds **one** log field at the writer: `secrets_redacted_count` (int), so a 0-count run is grep-able."*
  - `../phase-arch-design.md §"Component design" #4` (`SecretRedactor`) — *"The returned `list[SecretFinding]` is collected in-memory for the CLI summary line; it is NOT persisted to any file."* Fingerprint = first 8 hex of BLAKE3.
  - `../phase-arch-design.md §"Component design"` §"`SkillsLoader`" — *"first-tier-wins; collisions emit a `skill_shadowed` warning in the CLI summary."*
  - `../phase-arch-design.md §"Process view"` step 9 — CLI exit; *"`ProbeOutput emitted; CONTEXT_REPORT.md printed`"*.
- **Phase ADRs:**
  - `../ADRs/0005-secret-findings-no-plaintext-persistence.md` — fingerprints, no plaintext; the CLI summary line is the named observable surface.
  - `../ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md` — the redactor's `tuple[RedactedSlice, list[SecretFinding]]` shape; the `list[SecretFinding]` is the producer of this story's `fingerprints` field.
- **Production ADRs:**
  - `../../../production/adrs/0005-no-llm-in-gather.md` — Phase 0 fence; CLI summary line is plain Python `print`, no LLM.
  - `../../../production/adrs/0033-domain-modeling-discipline.md` §3 — illegal-states-unrepresentable; `SecretFinding` is a Pydantic frozen model, fingerprint is `Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{8}$")]`.
- **Source design:**
  - `../final-design.md §"Component design"` row 4 (`SecretRedactor`) — explicit "the CLI summary path (returned separately by `redact_secrets`, not threaded into a `RedactedSlice`)".
- **Existing code (Phase 2 contract from earlier steps — DO NOT WEAKEN):**
  - `src/codegenie/output/sanitizer.py` (S3-01 + S3-02) — `redact_secrets(slice_, probe_name) -> tuple[dict, list[SecretFinding]]`; this story is the **only** consumer of the second tuple element.
  - `src/codegenie/skills/loader.py` (S2-01) — emits a `probe.skill.shadowed` structured-log event per collision; first-tier-wins. This story renders those events on the CLI summary line.
  - `src/codegenie/cli/gather.py` (Phase 0 + Phase 1 extensions) — the existing per-probe `Ran/CacheHit/Skipped` audit anchor; do not edit its format, only append new lines.
  - `src/codegenie/logging.py` (Phase 0) — `structlog`-style logger; the test discipline is "assert event emitted exactly once" via the existing `tests/conftest.py` log-capture fixture.

## Goal

Extend `src/codegenie/cli/gather.py` to emit a four-line summary block on stdout **after** the writer succeeds and `CONTEXT_REPORT.md` is rendered (S8-01), and **before** CLI exit. The block contains, in this order:

1. The existing Phase 0 per-probe table `Ran/CacheHit/Skipped` — unchanged format (Phase 0 audit anchor preserved).
2. `secrets_redacted_count=<N>` — the sum across all probes of `len(SecretFinding)` returned by `redact_secrets`.
3. `fingerprints=[<8-hex>, <8-hex>, ...]` — the deduplicated, sorted list of 8-hex BLAKE3 prefixes. Empty list rendered as `fingerprints=[]`. **Never** the plaintext value, **never** a longer hash.
4. `skill_shadowed=[<skill_id>:<shadowed_by_tier>, ...]` warnings — one entry per collision, ASCII-sorted by `skill_id`. Empty list rendered as `skill_shadowed=[]`.

Each field is also emitted as a structured-log event (`secrets.summary`, `fingerprints.summary`, `skills.shadowed.summary`) exactly once per gather, and the test harness uses log-capture (Phase 0 `tests/conftest.py` fixture) to assert one-and-only-one emission per field.

## Acceptance criteria

- [ ] **AC-1 (Phase 0 per-probe `Ran/CacheHit/Skipped` audit anchor format unchanged).** The existing per-probe table format is byte-identical to Phase 0 / Phase 1 output. `tests/integration/cli/test_summary_phase0_anchor_unchanged.py` snapshots the Phase 0 portion against a frozen string and asserts equality. Phase 2 only **appends** lines below it; no edit to the existing format.
- [ ] **AC-2 (`secrets_redacted_count` emitted on stdout AND as structured-log event, exactly once).** After a gather completes, stdout contains a line matching `^secrets_redacted_count=\d+$`. The structured-log event `secrets.summary` is captured exactly once with `count: int >= 0`. `tests/unit/cli/test_summary_secrets_count.py::test_count_emitted_once` asserts both. Verified across `minimal-ts` (count likely 0) and `tests/fixtures/portfolio/secret-seeded` (S6-07 — seeded `AKIA...` secret; count ≥ 1).
- [ ] **AC-3 (`fingerprints` line: 8-hex only, sorted, deduplicated, no plaintext).** Stdout contains a line matching `^fingerprints=\[(?:[0-9a-f]{8})?(?:, [0-9a-f]{8})*\]$`. The list is ASCII-sorted and deduplicated (same secret appearing twice → one fingerprint). The structured-log event `fingerprints.summary` is captured exactly once with a `list[str]` payload. `tests/unit/cli/test_summary_fingerprints.py::test_fingerprints_eight_hex_only` asserts: (a) every fingerprint matches `^[0-9a-f]{8}$`; (b) sorted; (c) deduplicated; (d) **no plaintext** — explicit regex assertion that none of the originally-redacted secret strings (`AKIA[0-9A-Z]{16}`, `ghp_[A-Za-z0-9]{36}`) appear anywhere in stdout OR in any structured-log event payload (this is the boundary test for ADR-0005).
- [ ] **AC-4 (`skill_shadowed` warnings emitted from three-tier merge collisions).** When `SkillsLoader` (S2-01) encounters a collision (same `skill_id` in repo-local tier and org-shared tier), it emits a `probe.skill.shadowed` event; the CLI summary aggregates these into `skill_shadowed=[<skill_id>:<shadowed_by_tier>, ...]`, ASCII-sorted by `skill_id`. The structured-log event `skills.shadowed.summary` is captured exactly once per gather. `tests/integration/cli/test_summary_skill_shadowed.py` uses a fixture with two tiers defining the same `skill_id` and asserts the warning line + log event. Zero collisions → `skill_shadowed=[]`.
- [ ] **AC-5 (summary block emits *after* `CONTEXT_REPORT.md` write succeeds, *before* CLI exit).** `tests/integration/cli/test_summary_order_after_report.py` runs a gather and captures stdout + filesystem order: the summary block lines appear *after* the `CONTEXT_REPORT.md` write log event (`report.confidence_section.written`) and *before* the `gather.complete` event. The CLI exit code is 0 on a clean gather, irrespective of whether `secrets_redacted_count > 0` (count is informational, not gating).
- [ ] **AC-6 (one-and-only-one emission per structured-log event).** Each of the three new events (`secrets.summary`, `fingerprints.summary`, `skills.shadowed.summary`) is emitted exactly once per gather. The test harness captures the full event stream and asserts `Counter(events_by_name)["secrets.summary"] == 1` (and the same for the other two). A re-entrant CLI invocation (two `gather` runs in one process) produces two emissions (one per run); the discipline is per-gather, not per-process. Validated by `tests/unit/cli/test_summary_idempotent_per_gather.py`.
- [ ] **AC-7 (zero-state grep-ability — `secrets_redacted_count=0` always emitted on a clean gather).** Per phase-arch-design.md §"Logging" — *"a 0-count run is grep-able."* Even when no secret is found, the line must appear. `tests/integration/cli/test_summary_zero_state.py` runs against `minimal-ts` (no seeded secrets), asserts `secrets_redacted_count=0` literally present, asserts `fingerprints=[]` literally present, asserts `skill_shadowed=[]` literally present.
- [ ] **AC-8 (`mypy --strict` + `ruff` green on touched CLI module).** `mypy --strict src/codegenie/cli/` passes. `ruff check src/codegenie/cli/` and `ruff format --check` green. Phase 0 `fence` job still green (no LLM/network imports introduced).

## Out of scope

- Editing the format of the Phase 0 per-probe `Ran/CacheHit/Skipped` table. AC-1 is "byte-identical"; do not touch.
- Persisting `secrets_redacted_count` or fingerprints to any file. ADR-0005 forbids this; this story's `fingerprints` are stdout-only. If a future task class needs a persisted audit trail, that's a Phase 5 microVM concern (ADR-0005 §Consequences).
- Rendering fingerprints in `CONTEXT_REPORT.md`. The renderer (S8-01) consumes `IndexFreshness`, not `SecretFinding`. Fingerprints are CLI-summary-only.
- `--json` summary-line mode. The CLI is human-readable; structured-log events ARE the machine-readable surface. Do not invent a parallel JSON path.
- Pagination of `fingerprints` when the list is huge. If a run produces 1000+ fingerprints, the line is long — that's a signal worth surfacing, not hiding.
- Exit-code on `secrets_redacted_count > 0`. The CLI exits 0; the operator decides if a non-zero secret count is actionable.

## Files to touch

**New:**

- `tests/unit/cli/test_summary_secrets_count.py` — AC-2.
- `tests/unit/cli/test_summary_fingerprints.py` — AC-3 (including the plaintext-boundary assertion).
- `tests/unit/cli/test_summary_idempotent_per_gather.py` — AC-6.
- `tests/integration/cli/test_summary_phase0_anchor_unchanged.py` — AC-1.
- `tests/integration/cli/test_summary_skill_shadowed.py` — AC-4 (fixture-driven).
- `tests/integration/cli/test_summary_order_after_report.py` — AC-5.
- `tests/integration/cli/test_summary_zero_state.py` — AC-7.
- `tests/fixtures/portfolio/skills-collision/` (small fixture: two tiers of `.codegenie/skills/`, same `skill_id`) — fixture for AC-4. If S6-01's fixture already covers this, reuse it and note the reuse in "Notes for the implementer"; do not duplicate.

**Modified:**

- `src/codegenie/cli/gather.py` — append a `_emit_phase2_summary(redactor_findings, skill_shadowed_events)` helper invoked after `report.confidence_section.written`. ~40 LOC.
- `src/codegenie/output/writer.py` — pass the merged `list[SecretFinding]` (collected from each `redact_secrets` call across probes) up to the CLI return value; ensure it is **not** persisted. The writer already returns a typed result struct (Phase 1); add a `secret_findings: list[SecretFinding]` field to that struct.
- `src/codegenie/skills/loader.py` — ensure the `probe.skill.shadowed` event emission already in place (S2-01) returns its records up to the gather entry point (in-memory; not persisted). If S2-01 already exposes this via a typed return, no edit needed beyond consumption.

**Untouched (DO NOT EDIT):**

- `src/codegenie/output/sanitizer.py` (`redact_secrets` signature is frozen by S3-01/S3-02; consume what it returns, don't change it).
- Phase 0 per-probe table emission code.
- `CONTEXT_REPORT.md` renderer (S8-01).

## TDD plan — red / green / refactor

**RED (failing tests committed first):**

1. `test_summary_phase0_anchor_unchanged.py` — captures stdout of a current Phase 1 gather (snapshot baseline), then asserts the Phase 2 build produces a stdout whose first N lines match byte-for-byte. Fails red after the CLI starts emitting new lines until the snapshot is correctly anchored to the *prefix* of the new output.
2. `test_summary_secrets_count.py::test_count_emitted_once` — runs a gather against `tests/fixtures/portfolio/secret-seeded` (or a tiny ad-hoc fixture with `os.environ["FAKE_AKIA"] = "AKIA" + "A"*16` seeded in a tracked file via `tmp_path`), asserts `secrets_redacted_count=1` line on stdout AND exactly one `secrets.summary` event. Fails red — the CLI does not emit the line.
3. `test_summary_fingerprints.py::test_fingerprints_eight_hex_only` — same fixture; asserts the `fingerprints=[...]` line is present, every entry matches `^[0-9a-f]{8}$`, and the seeded plaintext (`AKIA` prefix) is NOT in stdout. Fails red.
4. `test_summary_fingerprints.py::test_fingerprints_sorted_and_deduplicated` — fixture with the same secret in two files → one fingerprint; fixture with two different secrets → two fingerprints, ASCII-sorted. Fails red.
5. `test_summary_idempotent_per_gather.py` — captures the structured-log stream, asserts each of the three Phase 2 events appears exactly once. Fails red.
6. `test_summary_skill_shadowed.py` — fixture with `tests/fixtures/portfolio/skills-collision/` defining two tiers of the same `skill_id`; asserts `skill_shadowed=["my_skill:repo_local_shadows_org_shared"]` on stdout and `skills.shadowed.summary` event emitted exactly once. Fails red.
7. `test_summary_order_after_report.py` — captures stdout + log-event order; asserts the summary block emits after `report.confidence_section.written` and before `gather.complete`. Fails red.
8. `test_summary_zero_state.py` — runs against `minimal-ts`; asserts the three zero-state lines (`=0`, `=[]`, `=[]`) all present. Fails red.

**GREEN (minimum code to pass):**

1. Edit `src/codegenie/output/writer.py`'s return struct to include `secret_findings: list[SecretFinding]` (in-memory only — write-path does not persist this field).
2. In `src/codegenie/cli/gather.py`, collect the in-memory `secret_findings` and the captured `probe.skill.shadowed` event records, and call `_emit_phase2_summary(findings, shadowed)` after `report.confidence_section.written` emits.
3. Implement `_emit_phase2_summary`:
   - Compute `count = len(findings)`; emit `secrets.summary` with `count=count`; print `secrets_redacted_count={count}`.
   - Compute `fps = sorted({f.fingerprint for f in findings})`; emit `fingerprints.summary` with `fingerprints=fps`; print `fingerprints={fps!r}` (use a compact `[x, y, z]` rendering).
   - Compute `shadowed = sorted(f"{e.skill_id}:{e.shadowed_by_tier}" for e in shadowed_events)`; emit `skills.shadowed.summary` with `entries=shadowed`; print `skill_shadowed={shadowed!r}`.
4. Ensure each `structlog` emission carries a unique event-name string so the test harness can `Counter` them.

**REFACTOR:**

- Pull the four print statements into a single triple-quoted `f"""..."""` if it improves readability; structured-log events stay separate from the print formatting.
- Confirm the test harness's log-capture fixture (`tests/conftest.py`) caps event names per gather; if Phase 0's fixture doesn't expose `Counter`-style assertions, extend it minimally (one helper function).
- `mypy --strict src/codegenie/cli/`, `ruff format`, `ruff check` clean.
- Verify the AC-3 plaintext-boundary check by `grep -E 'AKIA[A-Z0-9]{16}' <captured_stdout>` returning empty.

## Notes for the implementer

- **ADR-0005 boundary test is AC-3's plaintext regex.** This is non-negotiable. If your gather output ever contains the seeded plaintext, the redactor is broken or this story bypassed it. Surface the failure loud (Rule 12); do not weaken the regex to make the test pass.
- **Fingerprint truncation is 8 hex chars, period.** Not 16, not the full BLAKE3. ADR-0005 chose 8 to make brute-force fingerprint→plaintext infeasible while keeping the line scannable. Do not "improve" this by extending.
- **`Counter`-style log assertion vs grep-style.** Phase 0 likely captures events as a list; convert via `collections.Counter([e["event"] for e in captured])` in tests. Don't introduce a new logging framework.
- **Zero-state grep-ability matters for ops.** `grep secrets_redacted_count=0 <gather.log>` should always succeed on a clean gather. If you omit the line on zero state, ops loses the ability to verify the redactor ran.
- **Re-use the S6-07 secret-seeded fixture if it already exists.** S6-07 lands `test_secret_in_source.py`'s fixture (a tracked file with `AKIA...`); if that fixture is reachable from `tests/integration/cli/`, re-import. Do not duplicate fixture files.
- **`SkillsLoader`'s collision-emission shape from S2-01.** If S2-01's `loader.py` already returns a typed result with `shadowed_events: list[ShadowedSkill]`, consume that directly. If it only emits structured-log events without surfacing a return value, *minimally* extend the return type (additive, not breaking) and note the extension in this story's "Notes for the implementer" diff.
- **No new dependency.** `structlog` is Phase 0 baseline; `print` is stdlib. Phase 0 `fence` stays green trivially.
- **CLI return-struct widening — Phase 0 contract.** Adding `secret_findings: list[SecretFinding]` to the writer's in-memory return is a *Phase 2 internal* struct, not the `Probe` ABC or `ProbeContext`. ADR-0004's snapshot regen does not cover this struct; no contract amendment needed. Confirm with `tests/unit/test_probe_contract.py` still green.
- **Determinism:** sort fingerprints and shadowed-skill IDs ASCII-lex. The same gather against the same fixture must produce a byte-identical summary block across runs (Rule 9 — tests verify intent; the intent is determinism).
