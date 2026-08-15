# Validation report — S6-01 `SandboxRole` additive enum

**Date:** 2026-08-15
**Validator:** phase-story-validator (four-critic inline pipeline + synthesizer)
**Verdict:** **HARDENED** — real but small fixable weaknesses in AC coverage, TDD mutation-resistance, and consistency-with-ADR-0009 row-#6 wording; edits applied in place; ready for phase-story-executor once Phase 5's `sandbox/` module lands.
**Story:** [`../S6-01-sandbox-role-enum.md`](../S6-01-sandbox-role-enum.md)

---

## Stage 1 — Context brief

**Read:**
- Story (all sections).
- `docs/phases/07-migration-task-class/ADRs/0003-sandbox-role-additive-enum-on-spawn.md` — the primary; §Decision names the exact enum shape `class SandboxRole(str, Enum): GATE = "gate"; PROBE = "probe"`; §Consequences row 1 says the parameter change is "exactly two lines (one signature, one default)".
- `docs/phases/07-migration-task-class/ADRs/0009-phase-7-byte-edit-allowlist-fence.md` §Decision rows 6 + 7 — row 6 wording is scoped to the parameter: `"src/codegenie/sandbox/client.py — exactly one new role: SandboxRole = Role.GATE parameter on spawn(...)"`. The enum-block byte-edit is not literally covered by that wording; a spirit-of-the-rule reading is required.
- `docs/phases/07-migration-task-class/ADRs/0002-shell-invocation-trace-probe-runs-in-microvm.md` — the consumer that binds `Role.PROBE` semantics.
- `docs/phases/07-migration-task-class/ADRs/0001-no-multi-plugin-coordinator-in-phase-7.md` — the context for keeping the surface minimum.
- `docs/phases/05-sandbox-trust-gates/ADRs/0001-two-chokepoint-sandbox-seam.md` — Phase 5's seam this story extends without touching `run_in_sandbox`.
- `docs/phases/07-migration-task-class/High-level-impl.md §Step 6` — Features-delivered bullet 1 explicitly lists both the enum block and the parameter under one step, supporting the spirit-of-the-rule reading of ADR-0009 row #6.
- `docs/phases/07-migration-task-class/phase-arch-design.md §Physical view` (line 264: `SBX["sandbox/client.py<br/>+ role: SandboxRole param"]`).
- Repo state: `find src -name sandbox -type d` returns `src/codegenie/transforms/sandbox` only — **`src/codegenie/sandbox/` does not exist on `main` as of 2026-08-15.** Phase 5's sandbox module has not shipped.
- Sibling `_validation/` reports (S5-01, S5-04) — the discipline for tight ACs, planted-violation matrices, and comment-carrying-load audits.

**Load-bearing findings from the context read:**
1. `src/codegenie/sandbox/` does not exist yet. The story is only executable once Phase 5 lands that module. No test files, no adjacent code to mimic — the executor cannot start until then.
2. ADR-0009 row #6's literal wording covers only the parameter. The enum-block byte-edit needs a spirit-of-the-rule reading that HL-impl Step 6 supports.
3. ADR-0003 §Decision explicitly writes `class SandboxRole(str, Enum)` — not `enum.StrEnum`. The two shapes differ on `str(instance)` and the story has to pin the concrete choice (was previously deferred to "the codebase's choice").

## Stage 2 — Four critics (inline)

Critics run inline (not spawned as subagents) because the story's AC surface is tiny — a two-member enum — and the marginal signal from four independent subagent reads does not justify the token cost. Findings below.

### Coverage critic

- **coverage-1 (harden)** — AC-A's `len(list(Role)) == 2` skips aliases. A stealth `LEGACY = "gate"` would silently pass because Python's `Enum.__iter__` iterates canonical members only. Need a companion check on `SandboxRole.__members__` (which counts aliases).
- **coverage-2 (harden)** — Value uniqueness not asserted. A typo like `PROBE = "gate"` would make `PROBE` a silent alias of `GATE`; the cardinality check (`len(list) == 2`) would drop to 1, but a direct `GATE.value != PROBE.value` assertion is a clearer failure and pairs with the alias check to constrain both sides.
- **coverage-3 (harden)** — Symbol-name stability not tested. A rename `GATE` → `Gate` leaves `.value` untouched and slips past every current assertion. The `.name` is what error messages and `repr()` use, so a rename is a wire-visible event.
- **coverage-4 (harden)** — `.value` type is not asserted. The "wire format is `str`" claim depends on it being a plain `str`, not a subclass or `bytes`. A regression here would silently break Pydantic v2's discriminator machinery on downstream audit-log models.
- **coverage-5 (nit)** — AC-B's "pin the exact string the codebase chooses" defers a decision that must be made now (see test-1 for the reason). Coverage-adjacent.
- **coverage-6 (nit)** — No preconditions section flagging that `src/codegenie/sandbox/` doesn't exist yet — a future executor would hit a wall.

### Test-quality critic

- **test-1 (harden)** — AC-B punts on `str(Role.GATE)` semantics ("pin the exact string the codebase chooses"). Under `str, Enum` in Python 3.11+, `str(SandboxRole.GATE)` returns `"SandboxRole.GATE"` (default `Enum.__str__`). Under `StrEnum`, it returns `"gate"`. The story chose `str, Enum` per ADR-0003 — pin `str(...)` to `"SandboxRole.GATE"` explicitly so a future silent refactor to `StrEnum` fails loudly (that's the intended blast radius).
- **test-2 (harden)** — `repr()` not tested. `repr` is what appears in stack traces / error messages — pinning it locks operator-facing surface stability. Cost: one line per member.
- **test-3 (harden)** — Hash equality with the underlying `str` not tested. The `str` mixin makes `hash(Role.GATE) == hash("gate")` true; downstream audit-log correlators using dicts keyed on a mix of enum members and raw wire values depend on it. A regression to plain `Enum` would silently break this. Pinning it prevents the silent-drift failure mode.
- **test-4 (harden)** — `pytest.raises(ValueError)` in `test_unknown_value_raises_value_error` and `test_case_sensitivity` catches ANY `ValueError`. Add a `match=` regex on the canonical Python message (`is not a valid SandboxRole`) so a hypothetical replacement error class or a rewrapped `ValueError("wrong")` doesn't silently pass.
- **test-5 (nit)** — Membership-in-dict cross-test (enum-keyed vs str-keyed) is a good property-style pin for the hash-equality contract. Small marginal cost.

### Consistency critic

- **consistency-1 (harden)** — ADR-0009 row #6 wording is literally scoped to the `role: SandboxRole = Role.GATE` parameter, not the enum block. The story's AC-D calls this "row #6's first half" — an implicit spirit-of-the-rule reading. Anchor the broad reading explicitly (HL-impl Step 6 lists both features under one step; ADR-0003 §Consequences row 1 counts only the parameter as "two lines" *in addition to* the enum). If the S5-01 executor landed the strict reading, this story's `# row 6` inline block-comment in the fence file must be widened — coordinate, do not amend ADR-0009 §Decision. Document.
- **consistency-2 (harden)** — No preconditions flagging that `src/codegenie/sandbox/` doesn't exist as of 2026-08-15 (Phase 5 hasn't shipped). Executor would hit a wall; add explicit precondition.
- **consistency-3 (harden)** — Python version choice not surfaced. ADR-0003 uses `class SandboxRole(str, Enum)`; Python 3.11+ ships `enum.StrEnum` which would be more idiomatic. Story silently chooses the older mixin per ADR-0003. Add a Note explaining why (avoid a future contributor "modernizing" to `StrEnum` silently and shifting `str(...)` semantics).
- **consistency-4 (nit)** — AC-A's `mypy --strict src/codegenie/sandbox/` and `ruff check src/codegenie/sandbox/` targets assume the directory exists. Correct; belongs under Preconditions with the same guard as consistency-2.

### Design-patterns critic

- **design-1 (nit)** — Enum is a sum type per ADR-0033 (correct fit). No metadata on members (`cost_band`, `applies_when`) — correct per ADR-0003 (dumb enum, planner reads). `str, Enum` mixin is the sanctioned newtype-for-wire-values idiom.
- **design-2 (nit)** — Story deliberately splits the enum landing (S6-01) from the parameter landing (S6-02) — correct discipline; each PR's diff is minimal and a `git bisect` isolates regressions. Landed in Notes-for-implementer already.
- **design-3 (nit)** — The `Role` alias vs `SandboxRole` canonical name convention is good: consumers read `from codegenie.sandbox import Role; ...spawn(role=Role.PROBE, ...)`. AC-A tests both entry points. No change.
- **design-4 (harden)** — `enum.StrEnum` is arguably the modern pattern; the story silently rejects it per ADR-0003. Surface the rejection explicitly in Notes so a future reader doesn't "modernize" and silently break `str(...)` semantics.
- **design-5 (nit)** — No opportunity for a registry / plugin extension here — the enum is deliberately closed (adding a `Role.RECIPE` is an ADR-worthy event, per ADR-0003 §Tradeoffs row 3). Rule 2 (Simplicity First) applies: two members, no ceremony. Story respects this.

## Stage 3 — Researcher

**Not fired.** No critic finding tagged `NEEDS RESEARCH`. Every finding pointed at either a Python-language semantic (`Enum.__str__`, `__members__` vs `list()`, str-mixin hash contract) that is documented in the stdlib and needs no external lookup, or at an ADR row-wording ambiguity that a re-read of ADR-0003 and ADR-0009 resolves.

## Stage 4 — Synthesizer + Editor

**Priority:** Consistency > Coverage > Test-Quality > Design-Patterns.

**Conflict resolution:**
- Consistency-2 (missing `sandbox/` module) is the highest-priority finding — surfaced as a new `## Preconditions` section rather than a blocking verdict, because the story itself is well-specified; the block is on an upstream dependency (Phase 5). RESCUE verdict was considered and rejected — the story's Goal and ACs are sound; only the executor's landing conditions are the issue.
- Consistency-1 (ADR-0009 row #6 wording) is resolved by (a) documenting the spirit-of-the-rule reading in Preconditions §2, (b) tightening AC-D to reference that reading, (c) adding a new AC-D bullet about the fence file's `# row 6` inline comment being the interpretive artifact.
- Coverage-1..4 all become new AC-A/AC-B assertions + corresponding TDD tests.
- Test-1..4 land as new TDD tests + AC-B refinements.
- Design-4 lands as a Notes-for-implementer paragraph, not an AC (pattern advice is contextual; AC is observable).

**Edits applied** (see story's `## Validation notes` block for the concise summary):
- Front-matter: `Status` bumped from `Ready` → `HARDENED`; `Depends on` extended with the Phase-5 module-existence dependency; ADRs-honored line extended with the Preconditions §2 pointer.
- New `## Preconditions` section covering (a) `src/codegenie/sandbox/` not existing yet, (b) ADR-0009 row #6 spirit-of-the-rule reading, (c) Python-3.11-floor and `StrEnum` non-adoption.
- New `## Validation notes` block summarizing edits and verdict.
- AC-A: added alias-rejection guard (`len(SandboxRole.__members__) == 2`) and identity-not-equality note for `Role is SandboxRole`; `__all__` alphabetical placement noted.
- AC-B: pinned `str(...)` and `repr(...)` to exact values (was "codebase chooses"); added value-uniqueness (`GATE.value != PROBE.value`), symbol-name stability (`.name == "GATE" | "PROBE"`), `.value` type check (`type(...) is str`); the `Role("anything-else")` ValueError now specifies the canonical Python message substring.
- AC-C: added hash-equality-with-underlying-`str` assertion for both members.
- AC-D: tightened with spirit-of-the-rule anchor; added the `# row 6` inline-comment interpretive-load bullet; added a second planted-edit case on `client.py` (was only on `__init__.py`).
- TDD plan: added `test_no_aliases`, `test_name_stability`, `test_value_is_plain_str`, `test_value_uniqueness`, `test_str_and_repr_stability`, `test_hash_equality_with_underlying_str`, `test_membership_in_str_keyed_dict`; added `match=` on the two `pytest.raises(ValueError)` calls.
- Notes-for-implementer: added "StrEnum alternative" paragraph explaining why `class SandboxRole(str, Enum)` was picked (ADR-0003 authority + intentional `str(...)` divergence pinned by tests) and a "Preconditions link-back" reminder.

**Not edited** (respect for original scope, Rule 3):
- Story's Goal, Context narrative, and References section — the writer's framing is sound; the validator only tightens verification, not intent.
- Files-to-touch list — the two production files + one test file are correct and complete.
- Out-of-scope section — sharply scoped and correct (S6-02 owns the parameter; S6-03 owns the integration proof).
- Implementation outline — already minimum-code; the two-line enum block plus one-line re-export is not something to refactor.

## Strong dimensions (record for future stories to imitate)

- **Deliberate story split** (enum in S6-01, parameter in S6-02) — makes each PR's diff minimal and `git bisect`-isolatable. The Notes-for-implementer paragraph "Why ship the enum in a separate story from the parameter" carries the discipline explicitly.
- **Wire-format-as-value discipline** (`GATE.value == "gate"`) — the story is explicit that the string is the wire format, that renaming is a multi-phase event, and pins it with an AC. Mirrors Phase-3's `IndexName`/`ProbeId` newtype pattern.
- **Pydantic `extra="forbid"` smoke test in the enum's own tests** — proves the enum plays nice with Phase 5's audit-log discipline before Phase 5's own tests need to encode the coupling. Cheap forward-compat guard.
- **Refusal to add metadata to the enum** (no `cost_band`, no `applies_when`) — Rule 2 (Simplicity First) applied correctly; ADR-0003 §Consequences row 4 backs this.
- **Deliberate use of the `Role` alias for callers** while keeping `SandboxRole` as the canonical class name — small, deliberate, well-tested ergonomic choice.

## Provenance / signatures

- Validator: phase-story-validator skill, four-critic inline pipeline (Coverage, Test-Quality, Consistency, Design-Patterns) + synthesizer.
- Runtime evidence: none required — story is not executed, only hardened.
- Edits: applied via Edit tool against `docs/phases/07-migration-task-class/stories/S6-01-sandbox-role-enum.md`.
- No `_attempts/S6-01-*.md` file exists (story not yet executed); this validation report is the pre-executor artifact.
