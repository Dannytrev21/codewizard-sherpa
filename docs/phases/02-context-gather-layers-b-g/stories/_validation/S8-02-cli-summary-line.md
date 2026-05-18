# Validation report — S8-02 (CLI summary block on stdout)

**Story:** [S8-02-cli-summary-line.md](../S8-02-cli-summary-line.md)
**Date:** 2026-05-18
**Validator:** phase-story-validator (skill v1.x)
**Verdict:** **HARDENED**

## Summary

The story's *intent* — surface `secrets_redacted_count` + a fingerprint list + `skill_shadowed` warnings on the operator's stdout — traces cleanly to phase-arch-design.md §"Logging", §"Component design" #4, §"Process view" step 9, and the named ADRs 02-ADR-0005 / 02-ADR-0008 / 02-ADR-0010. The draft's *prescriptions*, however, contradicted three sources of truth (ADR-0008's "no new Phase-2 events", arch §"Logging"'s "**one** new log field", the existing `envelope.written` event already shipped by S3-03) and named several phantom code surfaces (a `Phase 0 per-probe Ran/CacheHit/Skipped` stdout table that doesn't exist; a `tests/fixtures/portfolio/secret-seeded` fixture that doesn't exist; a "writer typed result struct" that doesn't exist; event name `probe.skill.shadowed` that doesn't match the actual `skill_shadowed` constant; field `shadowed_by_tier` that doesn't match `shadowed_tier`). One additional bug: the prescribed GREEN code (`print(f"fingerprints={fps!r}")`) emitted single-quoted entries that the prescribed RED test's regex rejected — the story could not pass itself.

Twelve hardenings applied. Verdict: **HARDENED**.

## Context Brief

**What the story promises (Goal, draft):**
1. A four-line stdout block: Phase-0 anchor + 3 new fields.
2. Each new field also emitted as a structured-log event (`secrets.summary`, `fingerprints.summary`, `skills.shadowed.summary`).
3. New `secret_findings` field on the writer's "typed result struct".

**What the phase's exit criteria demand (`phase-arch-design.md` §Goals, §Logging):**
- G5: `SecretRedactor` runs at the writer chokepoint; zero plaintext in any persisted file.
- §Logging: *"Phase 2 adds **one** log field at the writer: `secrets_redacted_count` (int), so a 0-count run is grep-able."* (Singular field, singular event.)

**What the arch + ADRs constrain:**
- 02-ADR-0005: fingerprints are 8-hex BLAKE3, in-memory `list[SecretFinding]` not persisted; CLI summary is the named observable surface.
- 02-ADR-0008: **no new Phase-2 events**; the Phase 0 audit anchor `runs/<utc-iso>-<short>.json` is unchanged; "the discipline is 'no Phase-2 events'; the test enforcing this is `tests/unit/test_no_event_stream_in_phase_2.py`."
- 02-ADR-0010: `RedactedSlice` carries `findings_count: int` + `fingerprints: list[str]` as persisted-by-construction fields. The CLI reads them directly; no plumbing widening required.

## Source-of-truth verifications (grep against master)

| Reference in draft | Master surface | Verdict |
|---|---|---|
| "Phase 0 already prints a per-probe `Ran/CacheHit/Skipped` audit anchor" on stdout | `grep -rn "print(\|click.echo" src/codegenie/cli.py` returns zero hits; `coordinator.dispatch.order` is a structlog event, the audit anchor is a JSON file under `.codegenie/context/runs/` | **PHANTOM** — there is no Phase-0 stdout to preserve |
| "the `probe.skill.shadowed` event" + `shadowed_by_tier` field | `src/codegenie/skills/loader.py:86` — `_EVENT_SHADOWED: Final[str] = "skill_shadowed"`; emit payload at lines 430-437 has fields `skill_id, winning_tier, shadowed_tier, winning_path, shadowed_path` | **WRONG NAME + WRONG FIELD** |
| `tests/fixtures/portfolio/secret-seeded` | Directory listing of `tests/fixtures/portfolio/`: `minimal-ts, monorepo-pnpm, distroless-target, native-modules, stale-scip` — no `secret-seeded` | **PHANTOM FIXTURE** |
| "writer already returns a typed result struct (Phase 1); add a `secret_findings` field" | `src/codegenie/output/writer.py:191` — `Writer.write(envelope, raw_artifacts, output_dir) -> None`. No return value, no struct. | **PHANTOM STRUCT** |
| "`secret_findings: list[SecretFinding]`" with `file: ..., line: ...` | `src/codegenie/output/sanitizer.py:258` — `SecretFinding(probe_name, fingerprint, pattern_class, cleartext_len)` — no `file`, no `line` | **STALE SCHEMA** |
| "Fingerprints are CLI-summary-only" (Out-of-scope #3) | ADR-0010 line 47-48 and `src/codegenie/output/redacted_slice.py` — `RedactedSlice.fingerprints` is a persisted top-level slice field | **WRONG SCOPE CLAIM** — fingerprints DO persist (by ADR-0010 design) |
| `_emit_phase2_summary(findings, shadowed_events)` plumbing | `SkillsLoader.load_all` returns `Ok(LoadOutcome(skills, per_file_errors))`; no `shadowed_events` field. `SkillsIndexProbe` (the only consumer) does not surface shadows into `schema_slice` either. | **MISSING PRECONDITION** — `LoadOutcome` does not carry shadow data |
| `secrets.summary` / `fingerprints.summary` / `skills.shadowed.summary` events | 02-ADR-0008 §Decision: "No event stream in Phase 2 ... No event-variant Pydantic union." §Implementation: `tests/unit/test_no_event_stream_in_phase_2.py` is the structural fence. | **ADR VIOLATION** — three new events forbidden |
| `print(f"fingerprints={fps!r}")` (draft GREEN step 3) | `repr(["aaaaaaaa", "bbbbbbbb"])` → `"['aaaaaaaa', 'bbbbbbbb']"` (single-quoted). Draft AC-3 regex `^fingerprints=\[(?:[0-9a-f]{8})?(?:, [0-9a-f]{8})*\]$` rejects quoted entries. | **SELF-INCONSISTENT** — story prescribes code that fails its own test |
| `secrets_redacted_count` "needs to be added" | `src/codegenie/output/writer.py:250-253` ALREADY emits `EVENT_ENVELOPE_WRITTEN` with `SECRETS_REDACTED_COUNT_FIELD` per S3-03. | **DUPLICATE EMISSION** — story re-prescribes already-shipped behavior |

## Critic reports

### Coverage critic

- [block] AC-2/3/4/6: three new events contradict arch §Logging + ADR-0008 — drop them; consume the existing `envelope.written` for the count, stdout-only for the other two.
- [block] AC-2: `secrets_redacted_count` already emitted (writer.py:250) — AC restated as "stdout line == existing event field".
- [block] AC-2/3: `tests/fixtures/portfolio/secret-seeded` does not exist; pick one: in-scope fixture or `tmp_path`-seeded.
- [block] AC-4: wrong event name + field — render `<skill_id>:<shadowed_tier>` (actual field).
- [harden] MISSING: ordering vs `envelope.written` — assert count equality between stdout line and event field.
- [harden] MISSING: non-TTY stdout edge case — `capsys` defaults to non-TTY, so the standard test fixture covers it; surface in implementer notes.
- [harden] MISSING: very large fingerprint list rendered single-line.
- [harden] AC-3: plaintext-boundary regex only covers 2 of 6 pattern classes — iterate `_PATTERNS`.
- [harden] AC-6: "two `gather` runs in one process" tests trivia, not behavior — drop or scope to test harness only.
- [nit] MISSING: stdout UTF-8 encoding for non-ASCII `skill_id` (fingerprints are ASCII-hex; safe).
- [nit] AC-5: `gather.complete` event name — verify it exists.

### Test-Quality critic

- [block] AC-3: `print(f"fingerprints={fps!r}")` vs RED regex mismatch — fix the formatter (use `', '.join(fps)`).
- [block] AC-3: only 2 of 6 pattern classes enumerated — iterate `_PATTERNS` for mutation-resistance.
- [block] AC-3: `SecretFinding` has no `file:line` — dedup must be on fingerprint alone; add metamorphic asserts.
- [harden] AC-2: tautological 1-secret test — parameterize over `(0, 1, 3)` distinct seeds; assert `count == len(set(fps))`.
- [harden] AC-4: sort-key vs render-key mismatch — assert sort is on the rendered entry, not just `skill_id`.
- [harden] AC-6: `Counter == 1` doesn't catch wrong-payload mutations — assert payload schema too.
- [nit] AC-7: assert *only* one `fingerprints=` line on stdout (catches double-emission).
- [nit] AC-5: pin the stream (stdout, not stderr).
- Missing property-based opportunity: sort+dedup is a classic Hypothesis target — generate random 8-hex lists, assert idempotence + sortedness.

### Consistency critic

- [block] AC-2/3/4 + AC-6 + Goal §3: three new structlog events contradict ADR-0008.
- [block] AC-1 + Out-of-scope #1: no Phase-0 stdout exists to preserve byte-identically; reframe as "this story introduces stdout".
- [block] Goal/preamble: "Phase 0 already prints" is false; correct the framing.
- [block] Files-to-touch §writer.py: phantom typed result struct; remove the directive.
- [block] AC-2/3/7 fixture: phantom `secret-seeded` directory; use `tmp_path` inline seeding.
- [harden] Out-of-scope §"Fingerprints CLI-summary-only" contradicts ADR-0010 — rephrase to specify that `list[SecretFinding]` is in-memory-only; fingerprints DO persist via `RedactedSlice`.
- [block] AC-4: wrong event constant name + wrong field name.
- [harden] References "Source design" cites `SecretFinding(..., file=..., line=...)` — stale; drop file:line.
- [harden] Re-emission: state explicitly that the count is consumed off the existing `envelope.written`.
- [harden] Plumbing: `LoadOutcome.shadowed_events` does not exist; either extend it (additive) or scope this AC differently.
- [harden] CLAUDE.md "Extension by addition" / "Facts not judgments" — new events + new writer struct violate this.
- [nit] AC-5: `report.confidence_section.written` + `gather.complete` event names — verify.

### Design-Patterns critic

- [nit] GREEN step 3: pure/impure tangle — split `summary_block(...)` (pure) + `_emit_summary_block(...)` (impure).
- [harden] Goal/AC-2..4: primitive obsession at the summary boundary — introduce a `SummaryBlock` frozen dataclass.
- [harden] Files-to-touch/writer.py: widening writer return couples writer to summary plumbing — collect findings at `_seam_redact_envelope` instead. (Validator note: even simpler — `RedactedSlice` *already* carries `findings_count` + `fingerprints` per ADR-0010; no collection needed, just read.)
- [harden] AC-4: `f"{skill_id}:{tier}"` anaemic — use a `ShadowedSkill` frozen dataclass; format only at the print boundary.
- [nit] Newtype discipline: `SkillId`/`Tier` should be newtypes — surface as a precondition if loader returns raw `str`.
- [nit] Rule 2: three-field summary doesn't yet warrant a registry — codify this in Notes-for-implementer so Phase 3 doesn't redo the analysis.
- [nit] REFACTOR bullet: "triple-quoted f-string" deepens tangle — replace with the pure/impure split.
- [nit] AC-6: with pure split, assert `_emit_summary_block` called once (stronger intent than `Counter`).

### Researcher report

**Skipped** — no findings tagged `NEEDS RESEARCH`. All hardening targets were either codebase-grounded (existing event name, existing slice fields, existing pattern catalog) or rule-of-thumb (pure/impure split, primitive obsession). No external pattern lookup required.

## Conflict resolution

Priority order per the validator skill: **Consistency > Coverage > Test-Quality > Design-Patterns.**

- **Coverage** wanted three structured-log events to make `fingerprints` and `skill_shadowed` machine-readable. **Consistency** (ADR-0008) refused new events. **Consistency wins.** Resolution: stdout-only for those two fields; `envelope.written` (existing) for the count; operators who need machine-readable shadow data read it off the `SkillsIndexProbe`'s slice in `repo-context.yaml`.
- **Design-Patterns** proposed a `@register_summary_field` registry. **Rule 2 (Simplicity First)** refused premature abstraction. **Rule 2 wins** for now; design-pattern note moved to "Notes for the implementer" with the rule-of-three escape hatch documented for Phase 3.
- **Coverage** wanted a portfolio-level `secret-seeded` fixture. **Test-Quality** preferred `tmp_path`-seeded plaintext to keep tests hermetic. The draft itself offered both as a fallback; resolved by **picking one** (tmp_path) and noting reuse of S6-07's adversarial fixture only "if reachable."
- **Coverage** wanted "non-TTY edge case" as a new AC. **Test-Quality** observed `capsys` defaults to non-TTY, so the standard CLI test fixture covers it automatically. Resolved by surfacing the non-TTY guarantee in the implementer notes, not as a separate AC.

## Edits applied to story (before → after)

| Section | Before | After |
|---|---|---|
| Status | `Ready` | `HARDENED` |
| Depends on | "S8-01" only | "S8-01, S3-03, S2-01" — names the existing-event source and the additive loader extension |
| ADRs honored | "02-ADR-0005; 02-ADR-0010" | "02-ADR-0005; **02-ADR-0008**; 02-ADR-0010" — names the no-event-stream ADR this story honors |
| Validation notes block | absent | added 12-item summary documenting every change and why |
| Context — "Phase 0 already prints" | false claim | reframed: this story INTRODUCES stdout; arch §"Logging" already-shipped `envelope.written` is the existing structured-log surface |
| Goal — 4 lines incl. Phase-0 table + 3 new events | "Phase 0 per-probe Ran/CacheHit/Skipped (unchanged) + 3 fields + 3 new events" | "3 lines: count, fingerprints, skill_shadowed; **no new events**; `envelope.written` already carries the count" |
| AC-1 | "Phase 0 per-probe table byte-identical" | "No regression on master baseline (master prints zero stdout); after this story stdout is exactly the three new lines" |
| AC-2 | "new `secrets.summary` event captured exactly once" | "stdout count equals existing `envelope.written` event's `secrets_redacted_count` field; **no** `secrets.summary` event introduced (assert Counter == 0)" |
| AC-3 | "regex assertion that AKIA / ghp_ patterns not in stdout" | "iterate `sanitizer._PATTERNS`; one plaintext per pattern class; assert none in stdout NOR in `envelope.written` payload" |
| AC-4 | "`probe.skill.shadowed` event; `shadowed_by_tier` field" | "`skill_shadowed` event (existing, named constant) with `shadowed_tier` field; data path via new `LoadOutcome.shadowed_skills` + `SkillsIndexSlice.shadowed_skills`" |
| AC-6 | "three new events each captured exactly once" | "no new events introduced — `tests/unit/test_no_event_stream_in_phase_2.py` stays green + baseline-vs-current event-name diff" |
| AC-8 (new) | absent | "pure formatter / impure shell split — `cli_summary.py` has no I/O imports (AST asserted)" |
| AC-9 (new) | absent | "determinism — two consecutive gathers produce byte-identical summary blocks" |
| AC-10 | "mypy --strict + ruff" | "mypy --strict + ruff + lint-imports + fence" |
| TDD plan | 8 RED tests + 4-step GREEN with `!r` formatter | 12 RED tests + 6-step GREEN with explicit `', '.join(...)` formatter; hypothesis property tests for sort+dedup |
| Out of scope | "Fingerprints CLI-summary-only" (wrong) | "Persisting `list[SecretFinding]` to any file" (correct — fingerprints DO persist via `RedactedSlice`); "Adding any new structlog event variant" (newly explicit); "Removing existing `skill_shadowed` per-collision event" (newly explicit) |
| Files to touch — Modified | "`writer.py` add `secret_findings` field" (phantom) | dropped; replaced with "`skills/loader.py`: add `shadowed_skills` to `LoadOutcome`"; "`skills_index.py` + `skills_index.schema.json`: add `shadowed_skills` to slice" |
| Files to touch — New | absent | adds `src/codegenie/cli_summary.py` (pure module); 10 test files (one per AC) |
| Notes for implementer | "If S2-01 already returns `shadowed_events`, consume it" (false hedge) | "S2-01 does NOT surface shadows as data; this story extends `LoadOutcome` additively; document the rule-of-three escape hatch for a future `@register_summary_field` registry; Rule 2 says no registry for three fields" |

## Final verdict

**HARDENED.** The goal is sound and traces to phase arch + ADRs; the *prescriptions* needed substantial correction to align with master and with 02-ADR-0008. The rewritten story is implementable by the executor without any further phantom-surface ambiguity. The key precondition (`LoadOutcome.shadowed_skills`) is named in scope; the AC-4 data path is concrete.

A future contributor reading the rewritten story alongside the master codebase will find: (a) `envelope.written` + `secrets_redacted_count` already shipped; (b) `RedactedSlice.fingerprints` + `RedactedSlice.findings_count` already in scope at `_seam_redact_envelope`; (c) `SkillsLoader._EVENT_SHADOWED` already emitted per collision; (d) one additive extension (`LoadOutcome.shadowed_skills`) needed to bridge probe-slice → CLI; (e) no new structlog events; (f) one new pure module (`cli_summary.py`) and one new impure helper (`_emit_summary_block`). No phantom surfaces, no contradictions with ADRs, no self-inconsistent test/code prescriptions.
