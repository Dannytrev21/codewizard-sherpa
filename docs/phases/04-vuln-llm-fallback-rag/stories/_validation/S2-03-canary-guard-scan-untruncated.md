# Validation report: S2-03 — CanaryGuard scan-before-truncate + INJECTION_PATTERNS corpus

**Validated:** 2026-05-21
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S2-03's goal is sound and traces cleanly to ADR-0013 (scan-untruncated-first), ADR-0003 (path-scoped fence), and the phase arch §Component 3 / Edge-case 6 / Testing-strategy: ship `CanaryGuard.scan` over a `Final` tuple of `INJECTION_PATTERNS`, a stdlib-only `scan_pure` core, a Hypothesis property proving the scan fires past the 16 KB truncation cap, and a 50+ curated unit corpus. The core design — module path, functional-core/imperative-shell split, scan-then-truncate ordering, denylist-acknowledged-incomplete framing — is fully consistent with the ADR and arch. No structural problem warranting RESCUE.

The draft was not executor-ready for five reasons, all fixable in place:

1. **Stale event API (block).** The TDD plan imported `from codegenie.audit import EventLog`, constructed `EventLog()` with no args, and read `log.events` — none exist. This is the *exact* mistake S2-02 was hardened against (`_validation/S2-02-fence-wrapper.md` Consistency F1).
2. **AC-7 byte arithmetic placed the injection inside the cap (block).** The adversarial test — the load-bearing end-to-end proof of ADR-0013's critic fix — built `benign = b"BENIGN " * (16384 // 7)` = 16 380 bytes, so the injection started at byte 16 381, three bytes *inside* the 16 KB cap. The prose ("× 4000", "exactly cap + 200 bytes") contradicted its own code and was wrong both ways.
3. **No guard against pattern shadowing / duplicate bytes (block).** AC-2 checked only ID uniqueness. Under `scan_pure`'s first-match semantics a duplicate-bytes or substring-shadowed pattern is unreachable, silently breaking AC-6/AC-8's `expected_pattern_id` guarantees and making the refactor-step reorder unsafe.
4. **Refactor step prescribed an unwritable test (block).** "Add a per-category count assertion" against a flat `tuple[tuple[str, bytes], ...]` that carries no category field.
5. **`INJECTION_PATTERNS` shape falsely claimed ADR conformance (block).** The story said it "honors" ADR-0013's `Final[tuple[bytes, ...]]` while shipping `tuple[tuple[str, bytes], ...]`.

All four critics returned actionable findings; none required research (Stage 3 skipped). After hardening, every AC is individually verifiable, the laziest wrong implementation (scan-after-truncate, an unvalidated corpus, a shadowed pattern, a string-surgery redaction assertion) fails at least one AC, and the prescribed implementation extends by addition (a new pattern is one validated row; the import-time `_validate_patterns` guard catches a malformed corpus loud).

## Context brief

- **Story snapshot:** `CanaryGuard.scan(payload, nonce) -> CanaryResult` over `INJECTION_PATTERNS` (50+ curated `bytes`); `scan_pure` pure core; Hypothesis past-the-cap property; 50+ curated unit corpus + 20+ clean corpus. Step 2 of Phase 4.
- **ADRs:** ADR-0013 (scan-untruncated-first; `INJECTION_PATTERNS` frozen `Final` tuple; functional-core/imperative-shell; denylist acknowledged-incomplete), ADR-0003 (path-scoped fence — `src/codegenie/fallback/fence/`).
- **Codebase reality (verified 2026-05-21):** `src/codegenie/fallback/` does not exist yet (S2-01/S2-02 HARDENED, unexecuted). The real event log is `codegenie.plugins.events.EventLog` — constructor `EventLog(root: Path, workflow_id: WorkflowId, *, clock=, sink=)`; write via `emit_internal`, read via `replay()`; events discriminated by `event_type`; variants live in the `WorkflowInternalEvent` union + `_INTERNAL_CLASSES` tuple. `codegenie.audit` ships `AuditWriter`, not `EventLog`. `WorkflowId` / `HexNonce` are `NewType(str)` in `codegenie.types.identifiers`. `tests/property/` exists with `__init__.py`; `tests/adversarial/` does **not** exist — the codebase's adversarial tests live under `tests/adv/`. pytest markers `bench`/`adv`/`phase02_adv` are registered; `--strict-markers` is on.
- **Sibling lineage:** S2-02 (`FenceWrapper` + `fence_pure`, HARDENED) ships the `Scanner` Protocol, the `CanaryResult` sum type (`Annotated[CanaryClean | CanaryCollision, discriminator]`), `FencedSegment` (carries `canary: CanaryResult`, derived `canary_fired`), and the `CanaryCollision`/`FenceApplied` `WorkflowInternalEvent`s. S2-02's validation deferred the `pattern_id` → `CanaryPatternId` newtype decision explicitly to S2-03.
- **Open ambiguities at Stage 1:** none requiring user input.

## Findings by critic

### Coverage critic

- **F1 (harden)** — AC-2 *states* `pattern_id` regex `^[a-z][a-z0-9_]*$` but no AC/test enforces it.
- **F2 (block)** — No guard against duplicate pattern *bytes* or substring shadowing; under first-match this silently breaks AC-6/AC-8.
- **F3 (block)** — The refactor-step reorder is safe only if no-shadowing is invariant-enforced.
- **F4 (block)** — The refactor step's per-category count assertion is unwritable against a flat tuple with no category field.
- **F5 (harden)** — No edge AC for empty payload or empty pattern bytes (`b"" in anything` is always `True`).
- **F6 (harden)** — Non-UTF-8 pattern bytes are dead code: `scan_pure` takes `str`, encodes UTF-8, so a non-UTF-8 pattern can never match.
- **F7 (harden)** — AC-7's redaction assertion couples to S2-02 internals via `removeprefix`/`removesuffix`.
- **F8 (nit)** — AC-1 "fence test green" not named.

### Test-Quality critic

- **F1 (block)** — AC-7's `EventLog` API is fabricated (`codegenie.audit`, no-arg ctor, `.events`); the test fails at collection, not on behaviour.
- **F2 (block)** — AC-7 byte arithmetic places the injection 3 bytes inside the cap; prose contradicts code.
- **F3 (harden)** — AC-3's purity test is a denylist; the hardened S2-02 sibling uses an allowlist AST walk.
- **F4 (harden)** — AC-6's `result.pattern_id == pid` silently also asserts no-shadowing — a good invariant, but undocumented.
- **F5 (harden)** — AC-7's `removeprefix`/`removesuffix` redaction check is brittle; assert the `segment.canary` sum type instead.
- **F6 (nit)** — `tests/adv/` marker discipline unstated.
- **F7 (nit)** — AC-9's clean corpus passes trivially against an always-`CanaryClean` stub; add a near-miss row.

### Consistency critic

- **F1 (block)** — `from codegenie.audit import EventLog` — verified `codegenie.audit` has no `EventLog`. Exact mistake S2-02 was blocked on.
- **F2 (block)** — `EventLog()` zero-arg construction + `.events` read are impossible; `replay()` is the read API.
- **F3 (block)** — `tests/adversarial/` does not exist; codebase adversarial tests are under `tests/adv/`. Genuine conflict: the phase-4 arch doc explicitly names `tests/adversarial/` — the story matches the arch but contradicts the codebase.
- **F4 (block)** — `INJECTION_PATTERNS` shape `tuple[tuple[str, bytes], ...]` contradicts ADR-0013/arch's literal `tuple[bytes, ...]`; the story's line-7 claim to *honor* the convention is false as written.
- **F5 (harden)** — The dual-`CanaryCollision` namespace (a `CanaryResult` variant *and* a `WorkflowInternalEvent`, same name, two modules) is a real hazard; AC-7's `type(e).__name__ == "CanaryCollision"` is dangerously loose.
- **F6 (nit)** — `nonce_source=` kwarg unverified against shipped S2-02.
- **Confirmations:** module path (AC-1), scan-untruncated-first ordering, ID regex matching the warning-ID convention, the 50/200 corpus split — all consistent; not flagged.

### Design-Patterns critic

- **F1 (harden)** — `INJECTION_PATTERNS` as a positional 2-tuple is mildly anaemic (`[idx][0]`/`[idx][1]` across 5 sites); a frozen `NamedTuple` is a zero-cost readability win and would make a category field expressible — but a category field / registry is *not* warranted (Rule 2).
- **F2 (nit)** — `pattern_id` newtype (`CanaryPatternId`): drop as premature. The story already (correctly) follows the warning-ID `str` convention; a newtype adds no rename-protection and drags `identifiers.py` reconciliation onto this story.
- **F3 (harden)** — AC-5's "instance *or* class as `Scanner`" hedge leaves the contract ambiguous; pin the instance.
- **F4 / F5 (confirmations)** — functional-core/imperative-shell split (nonce check in the shell, not `scan_pure`) and the honest denylist framing are correctly applied; keep.

## Research briefs

None. Every finding was resolved by reading in-repo source (`plugins/events.py`, `audit.py`, `pyproject.toml`, `types/identifiers.py`), the ADRs, the arch, and the sibling S2-02 validation report. No `NEEDS RESEARCH` findings — Stage 3 skipped.

## Conflict resolutions

- **Coverage F4 (per-category test) vs Design-Patterns F1 (NamedTuple).** Coverage offered two fixes — (a) add a category data field, (b) drop the per-category assertion and instead assert the 15 mandated IDs each have a corpus row. Coverage recommended (b) as surgical. Design-Patterns F1 (lowest priority) preferred the richer `NamedTuple(category, …)` shape. Per the synthesis priority chain (Coverage > Design-Patterns) and Rule 2, **(b) was taken**: `INJECTION_PATTERNS` stays the flat `(pattern_id, bytes)` 2-tuple; the unwritable per-category assertion is replaced by AC-8's "all 15 mandated IDs have a corpus row" (a *stronger*, load-bearing guard). The `NamedTuple` opportunity is recorded as an optional *Notes-for-implementer* paragraph — it is a legitimate readability win but not mandated, and a `category` field / registry is explicitly warned off as past the Rule-2 threshold.
- **Design-Patterns F3 (drop `@classmethod`, pin instance method) vs the arch.** `phase-arch-design.md §Component 3` explicitly prescribes `@classmethod def scan`. Consistency (arch is source of truth) outranks Design-Patterns. **Resolution:** `scan` keeps `@classmethod` (arch-mandated); Design-Patterns' *valid* sub-point — kill the "instance or class as `Scanner`" ambiguity — is honored by pinning the `CanaryGuard()` **instance** as the sole `Scanner` in AC-5. A classmethod is fully callable on an instance, so both constraints hold simultaneously with no contradiction.
- **Design-Patterns F2 (`CanaryPatternId` newtype) vs Rule 2 / the warning-ID convention.** S2-02's validation deferred this decision here. Resolved in favour of the existing warning-ID `str` convention (`CLAUDE.md`): pattern IDs are validated `str` against module-level `Final` data, not newtypes. Recorded as a *Notes* paragraph closing the deferred decision so S6+ does not reopen it. No AC, no newtype.
- **Consistency F3 (`tests/adversarial/` vs `tests/adv/`) — arch vs codebase.** The phase-4 arch doc consistently names `tests/adversarial/`; the codebase consistently uses `tests/adv/` and `tests/adversarial/` does not exist. Per Rule 11 (match the codebase convention) and Rule 7 (surface the conflict, do not average), the story was hardened to `tests/adv/` with `@pytest.mark.adv`, and the arch doc's stale path flagged as a separate doc-fix (out of this story's scope).

## Edits applied

1. **Header.** `Status: Ready` → `Status: HARDENED`; added the `Validation notes` block (V1–V6); corrected the `ADRs honored` line so it no longer falsely claims to honor the literal `tuple[bytes, ...]` (Consistency F4).
2. **AC-1.** Named the fence test `tests/fence/test_pyproject_fence_phase4.py` (Coverage F8).
3. **AC-2 — rewritten.** Promoted to import-time structural validation via a pure `_validate_patterns` helper enforcing seven invariants: ≥50, unique IDs, unique bytes, ID regex shape, non-empty bytes, valid-UTF-8 bytes, no substring shadowing (Coverage F1/F2/F5/F6). The unit test must reject *each* violation class with its own bad-tuple fixture (no catch-all). Resolves the false ADR claim by stating the `(pattern_id, bytes)` refinement is necessary (Consistency F4).
4. **AC-3 — hardened.** Denylist purity test → allowlist AST walk mirroring the hardened S2-02 sibling (Test-Quality F3); added an empty-payload row (Coverage F5); clarified `_validate_patterns` may use `re.match` for the import-time shape check.
5. **AC-5 — hardened.** Dropped the "instance or class as `Scanner`" hedge; pinned the `CanaryGuard()` instance as the sole `Scanner`; stated `@classmethod` is retained per the arch and does not weaken the pin (Design-Patterns F3).
6. **AC-6 — hardened.** Documented that asserting the exact `pattern_id` also enforces AC-2's no-shadowing invariant, with an explicit "fix the corpus, do not weaken the test" instruction; added the filler-bytes caveat (Test-Quality F4, Coverage F3).
7. **AC-7 — rewritten (the block fix).** Path → `tests/adv/`, `@pytest.mark.adv` added (Consistency F3); byte arithmetic corrected so the entire injection sits past the cap, contradictory prose removed (Test-Quality F2); assertions switched to the `segment.canary` sum type instead of `removeprefix`/`removesuffix` string-surgery (Coverage F7, Test-Quality F5); the audit-event assertion disambiguated via an aliased import + `isinstance` (Consistency F5).
8. **AC-8 — hardened.** Switched to `CanaryGuard()` instance calls; added the "all 15 mandated IDs have a corpus row" assertion replacing the unwritable per-category test (Coverage F4); noted determinism depends on AC-2's no-shadowing invariant.
9. **AC-9 — hardened.** Pinned the fixed nonce; added a deliberate near-miss benign row so the clean corpus has mutation teeth (Test-Quality F7).
10. **AC-11 — hardened.** Named *which* `CanaryCollision` (the `WorkflowInternalEvent`) is registered by S2-02 and disambiguated it from the same-named `CanaryResult` variant (Consistency F5).
11. **Implementation outline step 2.** Added the `_validate_patterns` import-time-call requirement and the "curate so no pattern shadows another" instruction.
12. **TDD plan — adversarial Red block rewritten.** Real `EventLog` API (`codegenie.plugins.events`, `(root, workflow_id)` ctor, `replay()`), corrected byte arithmetic, `segment.canary` assertions, aliased event import, `tests/adv/` path, `@pytest.mark.adv` (Consistency F1/F2, Test-Quality F1/F2/F5).
13. **Refactor section.** Replaced the unwritable per-category count assertion with the clarification that category grouping is organisational-only; added a post-reorder `_validate_patterns` re-check.
14. **Files to touch.** `_validate_patterns` added to `canary.py`; `tests/adversarial/` → `tests/adv/`; AC mappings updated.
15. **Notes for the implementer.** Added six notes: the `codegenie.plugins.events.EventLog` correction, the dual-`CanaryCollision` namespace, the closed `pattern_id`-stays-`str` decision, the optional `InjectionPattern` NamedTuple opportunity (with a Rule-2 warning off category/registry machinery), the `tests/adv/` directory note, and a "confirm S2-02's surface first" note. Clarified the existing "no regex" note to exempt `_validate_patterns`' import-time check.

## Verdict rationale

HARDENED. The story's goal is valid and traces cleanly to ADR-0013, ADR-0003, and the phase arch — Consistency confirmed the core design has no conflict. The four blockers were a stale-codebase assumption (the `codegenie.audit` event surface — identical to S2-02's blocked F1), a byte-arithmetic error that hollowed out the load-bearing critic-fix proof, an un-guarded first-match/shadowing hazard, and an internally-contradictory refactor step. Each had a surgical in-place fix; none required rewriting the goal or scope, so RESCUE does not apply. After hardening, every AC is individually verifiable, the corpus is structurally validated loud at import, the adversarial test genuinely places injection past the truncation boundary, and the implementation extends by addition (a new pattern is one validated row).

## Recommended next step

`phase-story-executor` can implement S2-03 once S2-02 has landed. The executor should: (1) read `_validation/S2-02-fence-wrapper.md` and the shipped `src/codegenie/fallback/fence/wrapper.py` first — AC-7 depends on S2-02's `FenceWrapper.__init__` kwargs, the `FencedSegment.canary` field, and the `CanaryResult` / `CanaryCollision` shapes; (2) write `_validate_patterns` and AC-2's per-violation-class rejection tests first — the corpus is the load-bearing artifact; (3) write AC-6 (past-the-cap property) and AC-7 (adversarial end-to-end) before the corpus rows — they are the structural guards for ADR-0013's critic fix; (4) run `make check` — adding a module under `src/codegenie/fallback/` exercises the Phase-4 path-scoped fence (AC-1).
