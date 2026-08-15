# Validation report — S6-02 `SandboxClient.spawn(role=SandboxRole.GATE)` additive parameter

**Date:** 2026-08-15
**Validator:** phase-story-validator (four-critic inline pipeline + synthesizer)
**Verdict:** **HARDENED** — the story's core surface (additive keyword parameter + default-path byte-identity + audit-log `role` field) was sound; four fixable weaknesses landed: (a) `capture_trace` is a **second** additive parameter and ADR-0003 §Decision says "exactly one new parameter" — decision tree spelled out, (b) grep verification of Phase-5 callsites used a false-positive-prone bare-name pattern, (c) equality vs identity slippage on enum audit-event assertions, (d) fence scope did not cover the audit-event model's additive field + method-body drift. Edits applied in place; ready for phase-story-executor once (i) Phase 5's `sandbox/` module lands, (ii) the `capture_trace` Path A / Path B decision is made, (iii) S5-01's fence file's row-#6 comment covers whichever Path is chosen.
**Story:** [`../S6-02-sandbox-spawn-role-parameter.md`](../S6-02-sandbox-spawn-role-parameter.md)

---

## Stage 1 — Context brief

**Read:**
- Story (all sections).
- `docs/phases/07-migration-task-class/ADRs/0003-sandbox-role-additive-enum-on-spawn.md` — primary. §Decision: "`SandboxClient.spawn(...)` **gains exactly one new parameter**: `role: SandboxRole = SandboxRole.GATE`." §Consequences row 3: audit-log payload gains a `role: SandboxRole` field. §Reversibility: fallback is to route `Role.PROBE` through `Role.GATE`.
- `docs/phases/07-migration-task-class/ADRs/0002-shell-invocation-trace-probe-runs-in-microvm.md` — consumer. §Consequences shows the consumer calling `sandbox.spawn(role=Role.PROBE, workspace=..., command=[...], capture_trace=True)` — **note `capture_trace=True`**. §Decision binds `Role.PROBE + capture_trace=True` as the canonical shell-trace-probe shape.
- `docs/phases/07-migration-task-class/ADRs/0009-phase-7-byte-edit-allowlist-fence.md` §Decision row 6: `"src/codegenie/sandbox/client.py — one new role: SandboxRole = Role.GATE parameter on spawn(...) (S6-02)"`. Wording does not name `capture_trace`.
- `docs/phases/07-migration-task-class/ADRs/0001-no-multi-plugin-coordinator-in-phase-7.md` — context for keeping surface minimum.
- `docs/phases/05-sandbox-trust-gates/ADRs/0001-two-chokepoint-sandbox-seam.md` — Phase 5's seam this story extends without touching `run_in_sandbox`.
- `docs/phases/05-sandbox-trust-gates/final-design.md §Components §1 SandboxClient` — Phase 5's canonical name for the method is **`execute(spec: SandboxSpec) -> SandboxRun`**, not `spawn(...)`. This is the Rule-7 conflict the story's Notes-for-implementer named.
- `docs/phases/07-migration-task-class/phase-arch-design.md` §Component design §9 (line 813) — shows the consumer wiring: `sandbox.spawn(role=Role.PROBE, workspace=..., command=[...], capture_trace=True)`.
- `docs/phases/07-migration-task-class/High-level-impl.md §Step 6` — features-delivered lists both the enum block (S6-01) and the parameter (S6-02) under one step.
- Sibling validated stories: `_validation/S6-01-sandbox-role-enum.md`, `_validation/S5-01-phase7-byte-edit-allowlist-fence.md`, `_validation/S5-04-plugins-lock-and-catalog-hash-placeholder.md` — the discipline patterns for planted-violation matrices, `# row 6` inline-comment interpretive load, and Preconditions sections.
- Repo state: `find src -name sandbox -type d` returns `src/codegenie/transforms/sandbox` only — **`src/codegenie/sandbox/` does not exist on `main` as of 2026-08-15.** Phase 5's sandbox module has not shipped.

**Load-bearing findings from the context read:**
1. `src/codegenie/sandbox/` does not exist yet — mirrors S6-01. Story is only executable once Phase 5 lands the module.
2. **`capture_trace` is a second additive parameter beyond `role`.** ADR-0002 §Consequences and phase-arch-design §9 both show the consumer using `capture_trace=True`. Story sketches (AC-C, TDD plan) also assume `capture_trace` is settable. ADR-0003 §Decision says "gains exactly **one** new parameter." Either `capture_trace` was already on Phase 5's `SandboxClient` / `SandboxSpec` (Path A — no ADR amendment needed), or S6-02 is landing two additive parameters and ADR-0003 needs a Nygard-shape amendment before the code edit lands (Path B). Neither path was surfaced in the original story. This is the highest-priority finding.
3. Phase 5's `final-design.md` names the method `execute(...)`; ADR-0003 and Phase-7 arch design speak `spawn(...)`. Story's original Notes-for-implementer surfaced this as a Note; it needed to be a Precondition because it blocks the executor.
4. S5-01's fence file's `# row 6` inline comment carries interpretive load (mirrors S6-01's Preconditions §2 for the enum block). Under Path B, the comment must be widened to name both `role` and `capture_trace` — coordinate, do not silently amend ADR-0009.
5. AC-B's grep test scanned the string `spawn(` naked. `asyncio.subprocess.Process.spawn`, `multiprocessing.Process.spawn_context`, and various third-party libraries all match — false positives that would spuriously fail the grep AC. Object-scoped regex is required.

## Stage 2 — Four critics (inline)

Critics run inline (not spawned as subagents) — the story's AC surface, while larger than S6-01's, still concentrates on a single-method amendment with a handful of load-bearing invariants (byte-identity, dispatch propagation, audit-event schema, fence). Marginal signal from four independent subagent reads doesn't justify the token cost when the invariants are enumerable.

### Coverage critic

- **coverage-1 (BLOCK)** — **`capture_trace` is unauthorized surface.** ADR-0003 §Decision caps additive params at one. Story ACs and TDD plan freely use `capture_trace`; if it's not pre-existing, the amendment silently widens the ADR. Need Path A / Path B decision tree in Preconditions.
- **coverage-2 (harden)** — AC-A only asserts signature-shape via `inspect.signature`; a `**kwargs` rewrite could pass the shape check while accepting positional `role`. Need runtime `TypeError` test for `spawn(spec, Role.GATE)` positionally.
- **coverage-3 (harden)** — AC-A "any other diff fails CI" is vague. The `Parameter` map diff must be field-by-field (`name`, `kind`, `default`, `annotation`) not set-difference — a stealth `kind` change (POSITIONAL_OR_KEYWORD → KEYWORD_ONLY on an unrelated param) would pass a set-difference check.
- **coverage-4 (harden)** — AC-D's audit-event assertions did not check that `role` is the **only** new field on the model. An accidental extra field could ship alongside `role` and the ACs would not catch it.
- **coverage-5 (harden)** — AC-C's dispatch-propagation assertions did not check the **orthogonality-negative** case: default path (`role=GATE`, `capture_trace` omitted) must not silently propagate `capture_trace=True` into the backend spec. Positive case alone doesn't prove orthogonality.
- **coverage-6 (harden)** — AC-B's normalized-fields list ("time-dependent fields like `started_at`") was hand-wavy. A stealth addition to the normalization list (e.g., normalizing `exit_status`) would silently mask behavioral drift. Enumerate the list as a `Final[tuple[str, ...]]` and pin it.
- **coverage-7 (harden)** — Concurrency: no test for two concurrent `spawn` calls with different roles. A stealth module-level `_current_role` mutable would swap the tags under contention. Cheap single-test guard.
- **coverage-8 (harden)** — AC-E did not name the method-body-refactor case. A rename of an internal local (`spec_with_role` → `enriched_spec`) is a byte-edit that the fence should reject but AC-E as written only names an "unauthorized additive param."

### Test-quality critic

- **test-1 (harden)** — `e.role == "probe"` sketches in AC-C treat the enum as a string. `SandboxRole(str, Enum)` mixin makes `==` succeed against the underlying string; a stealth `str` bleed (audit event stores raw string, not enum) would silently pass. Use identity: `e.role is SandboxRole.PROBE`.
- **test-2 (harden)** — `pytest.raises(ValueError, match="capture_trace requires role=SandboxRole.PROBE")` uses substring matching. A message like `"capture_trace requires role=SandboxRole.PROBE and network=isolated"` would silently pass. Anchor with `match=r"^capture_trace requires role=SandboxRole\.PROBE$"`.
- **test-3 (harden)** — Round-trip test used `.role` field presence check; identity check on the enum member is a stronger pin against a str-bleed. Same slippage as test-1.
- **test-4 (harden)** — "Property-style test asserts the equivalence across a 5-spec parameter sweep" — the story called this "property-style" but used a hand-crafted sweep. Clarify: this is a fixed-input equivalence check, not `hypothesis` property-based testing. Rename to "hand-crafted 5-spec matrix" so a future maintainer doesn't try to wire up `hypothesis` for what's already the right shape.
- **test-5 (harden)** — Golden-refresh discipline: story updates Phase-5 `tests/golden/sandbox/audit/*.json` additively but no test proves the fence catches a golden refreshed **without** the new `role` field. Add a synthetic-missing-role fixture test.
- **test-6 (harden)** — `test_grep_scope_is_object_scoped` needed: the regex used to walk Phase-5 callsites is itself a load-bearing artifact and deserves its own meta-test seeding both a synthetic false-positive (`Process.spawn(role=1)`) and a synthetic true-positive.

### Consistency critic

- **consistency-1 (BLOCK)** — See coverage-1. `capture_trace` in ACs vs ADR-0003 §Decision's "exactly one new parameter" is a direct contradiction the story blends rather than surfaces. Rule 7 (surface conflicts, don't average them).
- **consistency-2 (BLOCK)** — Method-name reconciliation (`spawn` vs `execute`) was in Notes-for-implementer, not Preconditions. This is a **blocking** decision for the executor — cannot start writing code until this is resolved. Elevate to Preconditions.
- **consistency-3 (harden)** — Preconditions section missing (mirrors S6-01). At minimum: (a) `src/codegenie/sandbox/` doesn't exist yet, (b) `spawn` vs `execute` name, (c) `capture_trace` decision tree, (d) `SpawnDispatchedEvent` class name may be different in Phase 5, (e) fence-comment coordination under Path B, (f) grep pattern scope.
- **consistency-4 (harden)** — `SpawnDispatchedEvent` name was baked into TDD plan imports without hedging. Phase 5 may name it `SandboxRunEvent` or `ExecuteDispatchedEvent`. Grep for the shipped name and use it verbatim.
- **consistency-5 (harden)** — AC-B's grep test path list ("src/codegenie/ excluding sandbox/ and plugins/vulnerability-remediation--node--npm/") was correct scope but the pattern was a bare `spawn(` scan. See test-6 and coverage-8.

### Design-patterns critic

- **design-1 (nit)** — Additive keyword parameter with sum-type-enum default is the correct Open/Closed pattern for this API (mirrors ADR-0043). Story respects.
- **design-2 (harden)** — `SandboxSpec.model_copy(update=...)` is Pydantic v2's canonical update primitive but it **bypasses `extra="forbid"` at copy time** — silently adds keys the model doesn't declare. If the backend dispatcher inspects `spec.role` and `spec.capture_trace` via attribute access it silently succeeds; if it re-parses via `model_dump()` it catches drift. Either extend `SandboxSpec`'s class definition (respecting Phase 5's `extra="forbid"`) or land a matching amendment PR that adds the fields as first-class. Do not rely on `model_copy(update=...)` as the schema-extension mechanism.
- **design-3 (nit)** — Orthogonality of `role` and `capture_trace` is a good ports-and-adapters shape: the API surfaces two independent concerns; the impossible combination (`GATE + capture_trace`) is rejected at the boundary. Sound design.
- **design-4 (nit)** — `Role` alias vs `SandboxRole` canonical name: same convention as S6-01. No change.
- **design-5 (harden)** — Concurrency: default is that a shared-mutable-state introduction is invisible until CI runs against a real backend. A single concurrency test in the same story is cheap insurance and pins the invariant. See coverage-7.
- **design-6 (nit)** — Command pattern shape: the `SandboxSpec` is a value object that flows through the client to the backend dispatcher. Story keeps that discipline (the amendment enriches the spec, doesn't add a side-channel). Good.

## Stage 3 — Researcher

**Not fired.** No critic finding tagged `NEEDS RESEARCH`. Every finding pointed at:
- ADR-row-wording ambiguity resolved by re-reading ADR-0002 §Consequences alongside ADR-0003 §Decision.
- Python-stdlib semantics (`inspect.signature`, `Enum` identity vs equality, `str, Enum` hash contract) documented in the stdlib.
- Pydantic v2 `model_copy(update=...)` semantics documented in Pydantic's own migration guide (no external lookup needed — the invariant is that `update=` bypasses field validation).
- A regex meta-test (`test_grep_scope_is_object_scoped`) that pins its own surface — no research cost.

## Stage 4 — Synthesizer + Editor

**Priority:** Consistency > Coverage > Test-Quality > Design-Patterns.

**Conflict resolution:**
- **coverage-1 + consistency-1 (both BLOCK on `capture_trace`)** — resolved by adding Preconditions §3 with an explicit Path A / Path B decision tree. Path A: `capture_trace` pre-existing on Phase 5 → no ADR amendment. Path B: `capture_trace` new here → file `ADRs/0003-amendment-capture-trace.md` **before** landing code. Both paths preserve the arch design (line 813); the choice is which artifact carries the audit trail.
- **consistency-2 (BLOCK on method name)** — resolved by elevating to Preconditions §2 (was Notes-for-implementer). The executor must resolve the name before writing code; a Note is too weak.
- **coverage-2..8 + test-1..6** — landed as tightened ACs and new TDD tests. New AC-G (Concurrency safety) is a single-test invariant guard.
- **design-2 (Pydantic `model_copy(update=...)` subtlety)** — landed as a Notes-for-implementer paragraph. Not an AC because the exact schema-extension mechanism is Path-dependent (Path A the field exists; Path B the amendment adds it) — the Note steers the executor.

**Edits applied** (see story's `## Validation notes` block for the concise summary):
- Front-matter: `Status` bumped from `Ready` → `HARDENED`; `Depends on` extended with the Phase-5 module-existence dependency + link to Preconditions §1; `ADRs honored` line extended with pointers to Preconditions §3 (ADR-0003 amendment gate) and Preconditions §4 (S5-01 fence file's row-#6 comment coordination).
- New `## Preconditions` section (six items): (1) module existence, (2) `spawn` vs `execute` reconciliation, (3) `capture_trace` Path A / Path B tree, (4) row-#6 fence-comment coordination, (5) `SpawnDispatchedEvent` class-name contingency, (6) object-scoped grep regex.
- New `## Validation notes` block summarizing edits and verdict.
- AC-A: added `test_positional_role_raises_type_error` runtime AC; specified `inspect.Parameter` field-by-field diff (not set-difference); qualified the method name with `(or .execute per Preconditions §2)`.
- AC-B: enumerated the exact sentinel-normalized field list as a `Final[tuple[str, ...]]` + `test_normalized_fields_enumerated` companion; renamed "property-style" to "hand-crafted 5-spec matrix"; changed grep AC to reference the Preconditions §6 object-scoped regex + `test_grep_scope_is_object_scoped` meta-test seeded with both a synthetic false-positive and true-positive; added the redundant-identity check `client.spawn(spec) == client.spawn(spec, role=SandboxRole.GATE)` explicitly.
- AC-C: pinned exact `ValueError` message with anchored regex; added positive dispatch-propagation AC (backend spec carries `capture_trace=True` when `role=PROBE, capture_trace=True`); added orthogonality-negative dispatch AC (backend spec has `capture_trace=False` when default path taken); changed `e.role == "probe"` → `e.role is SandboxRole.PROBE`.
- AC-D: added "role is the *only* new field" AC using `PRE_FIELDS` frozenset comparison; changed round-trip to `is SandboxRole.PROBE` (identity); added coordinated-golden-refresh companion test that seeds a golden file with missing `role` and asserts the fence flags it.
- AC-E: added the "planted `capture_trace` case is Path A's failing case" explicit wording; added the "planted method-body refactor" case (rename of internal local).
- New AC-G — Concurrency safety: two concurrent `spawn(...)` calls with different roles emit audit events with correct, un-swapped role tags. Cheap `asyncio.gather` test against `RecordingBackend` stub.
- TDD plan: added `test_positional_role_raises_type_error`, `test_no_other_signature_changes` (`inspect.Parameter` map diff), `test_capture_trace_dispatch_propagation`, `test_capture_trace_not_leaked_when_role_gate`, `test_audit_event_role_is_only_new_field`, `test_round_trip_identity_not_equality`, `test_concurrent_spawn_role_tags_correct`, `test_grep_scope_is_object_scoped`, `test_normalized_fields_enumerated`; anchored `match=r"^capture_trace requires role=SandboxRole\.PROBE$"` on all `pytest.raises(ValueError)` calls.
- Notes-for-implementer: added "`capture_trace` amendment dance" paragraph (Path A vs Path B), "Method-name Precondition link-back" paragraph, "Grep false-positive risk" paragraph, "`SandboxSpec.model_copy(update=...)` subtlety" paragraph (design-2).

**Not edited** (respect for original scope, Rule 3):
- Story's Goal, Context narrative, References section — writer's framing is sound; validator only tightens verification, not intent.
- Files-to-touch list — the production files + one test file are correct and complete.
- Out-of-scope section — sharply scoped (S6-02 owns the parameter; S6-03 owns the integration proof).
- Implementation outline's ordered steps — already minimum-code; the wrapper + spec-enrichment + dispatch pattern is correct.
- Reversibility ADR-0003 §Reversibility (route `Role.PROBE` through `Role.GATE`) — deliberately out of scope for S6-02 per Notes.

## Strong dimensions (record for future stories to imitate)

- **Byte-identity as the load-bearing invariant** — the story is explicit that a stealth behavioral change on the default path is the single largest risk, and the golden-file baseline + hand-crafted 5-spec matrix nails this. Mirrors S5-04's `plugins.lock` hash-fence discipline.
- **Additive-parameter discipline paired with byte-edit fence** — a keyword-only parameter with a safe default (`Role.GATE`) plus an S5-01 fence row that scopes the allowed diff makes the amendment's blast radius auditable at the byte level. Extension-by-addition (ADR-0043) with explicit rails.
- **Orthogonality-at-the-API discipline** — `role` and `capture_trace` are two independent concerns; the impossible combination raises `ValueError` at the boundary rather than silently degrading. Ports-and-adapters framing.
- **Reader-first Preconditions** — the six-item Preconditions section front-loads the six things that block or reshape execution before any code is written. Mirrors S5-04 / S6-01's discipline.
- **Meta-test on the load-bearing grep regex** — `test_grep_scope_is_object_scoped` pins the regex itself with a synthetic false-positive and true-positive, so a maintainer who "simplifies" the regex fails a test rather than silently narrowing scope.
- **Sentinel-normalization allow-list as `Final[tuple[str, ...]]`** — makes the "which fields are normalized" question observable in code and testable; a stealth addition to the list fails a companion test rather than silently masking drift.

## Provenance / signatures

- Validator: phase-story-validator skill, four-critic inline pipeline (Coverage, Test-Quality, Consistency, Design-Patterns) + synthesizer.
- Runtime evidence: none required — story is not executed, only hardened.
- Edits: applied via Edit tool against `docs/phases/07-migration-task-class/stories/S6-02-sandbox-spawn-role-parameter.md`.
- ADR touchpoints surfaced (not amended): ADR-0003 §Decision "exactly one new parameter" gates on Preconditions §3 Path B; ADR-0009 §Decision row 6 wording gates on Preconditions §4 Path B.
