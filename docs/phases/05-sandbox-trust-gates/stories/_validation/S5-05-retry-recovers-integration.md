# Validation report: S5-05 — Retry-recovers integration against `breaking-change-cve` fixture

**Validated:** 2026-05-25
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Validator agent run:** automated (story-validation-corrector scheduled task)

## Summary

S5-05 is the load-bearing exit-criterion test for Step 5 and one of two load-bearing tests for the whole phase (§Goal 2: "3-retry loop demonstrated end-to-end with retry-1 fail → retry-2 recover"). The intent is right and the story has serious infrastructure thinking already — VCR cassette, fixture `.expected/` shape, distinct `patch_blake3` assertion, pre-execute marker ordering. The draft would, however, ship a test whose mutation-resistance is shallow: several of its strongest-looking assertions are satisfied by a buggy `GateRunner` that *happens* to never invoke the hook (because the cassette was recorded with a working implementation and the assertion targets "any prompt anywhere in the cassette" rather than "the second invocation specifically"). The contract surface ADR-0002 mandates (`prior_attempts: list[AttemptSummary] = []` kwarg, canary-pattern check, fence size limit) is partly under-asserted, and the cross-phase Gap 2 contract — the orchestrator's concrete `ReplanHook` Protocol implementation — is referenced but never *type-checked* by the test.

| Draft assumption / shape | Reality / hardened shape |
|---|---|
| The fence-prompt assertion (`re.search(r"<BEGIN_PRIOR_ATTEMPT_[A-F0-9]{16}>", text)`) targets the attempt-2 invocation | The current helper `_extract_phase4_prompts` returns **all** prompts in the cassette as one flat `list[str]`. A buggy runner that skips the second hook invocation but the cassette still holds a fence-bearing prompt (because it was recorded once with a working runner) passes the regex anyway. Hardened: extract `list[Phase4Interaction]` ordered by request index; assert **interaction[1]** (the second call) carries the fence, **and** assert `len(prompts_with_fence) == 1` so a recorder leak — extra prompts — is loud. |
| `outcome.state == "passed" and outcome.attempt == 2` is a sufficient end-state check | A wrong implementation that fabricates `GateOutcome(state="passed", attempt=2)` without ever invoking the hook satisfies this. Hardened: pair the outcome with **ledger inspection** — `attempts[0].attempt_id == 1`, `attempts[1].attempt_id == 2`, `attempts[0].failing_signals[0].kind == "tests"`, and an explicit "the hook was invoked exactly once between attempt 1 and attempt 2 with `len(prior_attempts) == 1`" assertion via a Decorator-pattern `ReplanHookSpy`. |
| Distinct `patch_blake3` is enforced by hashing either `signals.build.details["patch_blake3"]` or `evidence_paths["patch"]` | The fallback path silently passes if both attempts share an `evidence_paths["patch"]` (overwritten or shared workdir). Hardened: pin **distinct `evidence_paths["patch"]` first**, then **distinct content**. The fallback hashes only after asserting paths differ. |
| ADR-0002's "canary-pattern checked" is exercised by recording the cassette | The cassette captures the *outgoing* prompt but does not capture *whether the canary matcher was invoked* — that's an observability question, not a network artifact. Hardened: `phase4_fence.compose_prior_attempts` (the S5-03 helper) is the only legitimate fence producer; a sub-assertion calls into the canary matcher's instrumented hook (the same matcher S5-03 ships with) and asserts `canary_match_count >= 1` for attempt 2. If S5-03's matcher does not yet expose a counter, the executor adds one (additive — no surface change). |
| ADR-0002's `≤ 4 KB` fence-block invariant is implicit | Hardened: the prompt body slice between `<BEGIN_PRIOR_ATTEMPT_…>` and `<END_PRIOR_ATTEMPT_…>` is asserted `≤ 4096` bytes (UTF-8 encoded). This is the load-bearing prompt-injection cap from ADR-0002 §Tradeoffs row 3. |
| AC-10's "chokepoint held — re-running `tests/schema/test_stage6_chokepoint.py` in the same pytest session as a dependency" | pytest has no first-class test-ordering dependency primitive. Hardened: S5-04 (HARDENED) exports a callable `assert_stage6_chokepoint_clean(REPO_ROOT) -> None` from the walker module; this story imports + calls it directly at the end of the integration test. No pytest-ordering magic; it's just a function call. Rule-of-three precedent: S5-04's own test, this story, and Phase-7 S12-02 (distroless E2E, named in Out-of-scope of this story) will be the three callers. |
| `_extract_phase4_prompts` returns `list[str]` of JSON-serialized request bodies | Leaky abstraction. Hardened: return `list[Phase4Interaction]` where `Phase4Interaction = NamedTuple("Phase4Interaction", uri=str, prompt_text=str, prior_attempts_serialized=str)`. The fence regex now targets `interaction.prompt_text` directly, not an unstructured `json.dumps(body)` blob. (Mirrors S5-04's "consume the kernel" — the helper is the kernel for cassette introspection, not the test.) |
| `Depends on: S5-03, S5-04` | Real upstream surface: **S5-01** (the `ReplanHook` Protocol — the type the story's `make_orchestrator_replan_hook` must satisfy at `mypy --strict` time); **S5-02** (`GateRunner.run` — the loop); **S5-03** (the `prior_attempts` kwarg + `compose_prior_attempts` fence helper); **S5-04** (`assert_stage6_chokepoint_clean` — the callable AC-10 consumes). Add S5-01, S5-02 explicitly. |
| The cassette replays offline (`pytest --no-network`) under any record-mode | Hardened: pin the cassette's `record_mode` to `RecordMode.NONE` on replay (or `pytest-recording`'s `--record-mode=none`) AND assert `pytest-recording`'s `block_network` fixture is active. If a network call escapes during replay, the test must fail loud, not silently re-record. |
| Cassette regeneration determinism is mentioned in Refactor (10 consecutive runs) but not pinned as an AC | Hardened: AC-CASS-DET-1 — a separate `tests/integration/gates/test_stage6_retry_recovers_replay_stable.py` marker test (`@pytest.mark.cassette_stability`) runs the same scenario **3 times** in a row in the *same pytest session* (faster than 10 but mutation-resistant against per-run state leakage), asserts identical outcomes byte-for-byte. Property-style assertion: for n in 1..3, `(outcome_n, ledger_n.head())` equals run-1's tuple. |

The validator's response: **harden the fence-prompt assertion to target attempt 2 specifically; add a `ReplanHookSpy` Decorator-pattern test double observing hook-call shape (call_count, `prior_attempts` length); promote canary-match counter + ≤4 KB fence-size invariants to ACs; replace the AC-10 "re-run pytest" coupling with a direct call to S5-04's `assert_stage6_chokepoint_clean`; widen `Depends on:` to S5-01 + S5-02; assert distinct `evidence_paths["patch"]` before hashing; pin VCR replay to block-network mode; add a 3-run cassette-replay-stability test; promote `_extract_phase4_prompts` to a typed `Phase4Interaction` helper from day-1 (it'll be shared with S5-01's contract test and Phase-7 S12-02); surface the `.expected/` fixture shape as a Specification-pattern contract for future retry-recovers fixtures.**

The remaining slice — what S5-05 actually owns:

1. The integration test against the `breaking-change-cve` fixture with all the hardened ACs below.
2. The fixture repo + `.expected/` directory documented as the Specification-pattern *contract* for retry-recovers fixtures (Phase 7's `always-fails`, `test-removes-test`, etc. follow the same shape).
3. The typed `Phase4Interaction` cassette helper under `tests/integration/_helpers/vcr.py` (consumed day-1 by this story; shared from day-1 with S5-01 contract test).
4. The `ReplanHookSpy` Decorator at `tests/integration/_helpers/hooks.py` — three known consumers (S5-01 contract test, this story, S7-01 failed_unrecoverable test) clear the rule-of-three threshold today.
5. Notes paragraphs naming the design seams so the Phase-7 retry-recovers fixtures slot in without editing the helpers or the kernel.

No `RESCUE`-tier escalation: every gap is in-scope to harden in place. **Stage 3 (research) was skipped** — every finding is answerable from in-repo precedents (S5-04 HARDENED report's "consume the kernel" pattern, the `tests/fence/test_no_llm_in_transforms.py` mutation-resistance pattern, ADR-0002 + ADR-0007 invariants, Gap 2's `ReplanHook` Protocol pin).

## Findings by critic

### Coverage critic (9 findings: 3 block, 5 harden, 1 nit)

#### Block-tier

1. **(coverage — block) Failing-signal identity not asserted on attempt 1.** Goal says "asserts attempt 1 fails on `tests`" but AC-5 only asserts `state == "failed_retryable"`. A buggy runner that records `failing_signals=[Signal(kind="build", ...)]` (wrong kind) passes the draft check. **Fix:** AC-SIG-1 — `attempts[0].outcome.failing_signals` is non-empty AND the first failing signal's `kind == "tests"` AND its `details["first_failure"]` references `auth/jwt.test.ts`. (Fixture-controlled — `.expected/` doc names the expected first-failing test file.)
2. **(coverage — block) `prior_attempts` length on attempt 2 not asserted.** ADR-0002's load-bearing invariant — "the orchestrator's `replan_hook` is the only caller that ever passes a non-empty list" — is checked only by the regex match on the cassette. A buggy runner that calls `FallbackTier.run(..., prior_attempts=[])` on attempt 2 still produces a recorded cassette whose pre-existing fence text was baked at record time. **Fix:** AC-PRIOR-1 — use a `ReplanHookSpy` (Decorator) that wraps the real hook and records each call's `ctx.prior_attempts`. Assert: `spy.call_count == 1`, `len(spy.calls[0].prior_attempts) == 1`, `spy.calls[0].prior_attempts[0].attempt_id == 1`.
3. **(coverage — block) Canary-pattern matcher not asserted invoked.** ADR-0002 says "canary-pattern checked"; phase-arch-design Gap 2 says the contract test asserts "(c) the canary pattern matcher is invoked." Story has no AC for this. **Fix:** AC-CANARY-1 — the S5-03 `compose_prior_attempts` helper exposes (or this story additively widens to expose) an instrumented counter on its canary matcher. Assert: `canary_matcher.match_count >= 1` after the test run, recording the count from the in-process matcher (not the cassette).

#### Harden-tier

4. **(coverage — harden) Fence ≤ 4 KB invariant not asserted.** ADR-0002 §Tradeoffs row 3: "`prior_failure_summary` truncation policy (≤ 4 KB)". **Fix:** AC-FENCE-SIZE-1 — extract the byte slice between the first `<BEGIN_PRIOR_ATTEMPT_…>` and the matching `<END_PRIOR_ATTEMPT_…>` from attempt-2's prompt; assert `len(slice.encode("utf-8")) <= 4096`. Boundary fixture: include a truncation-required case under `tests/fence/test_compose_prior_attempts_truncates.py` (out-of-scope here — owned by S5-03 — but cross-referenced).
5. **(coverage — harden) `prior_failure_summary` content not asserted.** Fence delimiters confirmed; payload not. **Fix:** AC-SUMMARY-CONTENT-1 — the extracted slice contains both the string `"tests"` (failing signal kind) and the string `"auth/jwt.test.ts"` (the failing-test path from the fixture). Substring matches, not regex over arbitrary positions — these are summary contract.
6. **(coverage — harden) `Depends on:` understated.** Story says `S5-03, S5-04`. Real surface: **S5-01** (`ReplanHook` Protocol — for the `mypy --strict` Protocol-satisfaction check); **S5-02** (`GateRunner` itself); **S5-03** (fence helper + `prior_attempts` kwarg); **S5-04** (the callable `assert_stage6_chokepoint_clean`). **Fix:** widen to `S5-01, S5-02, S5-03, S5-04`.
7. **(coverage — harden) `ReplanHook` Protocol satisfaction not type-checked.** Story constructs the hook via `make_orchestrator_replan_hook(...)` and passes it to `GateRunner`. ADR-0001 + Gap 2 frames the hook as a typed Protocol. **Fix:** AC-PROTO-1 — a top-of-file `from codegenie.gates.contract import ReplanHook` plus a `hook: ReplanHook = make_orchestrator_replan_hook(...)` annotation in the fixture forces `mypy --strict` to catch a Protocol-shape regression at lint time, not at runtime.
8. **(coverage — harden) Cassette-replay determinism not asserted as a separate test.** Story Refactor § mentions running 10 consecutive replays; not promoted to an AC. **Fix:** AC-CASS-DET-1 — a sibling test `test_stage6_retry_recovers_replay_stable.py` (marker `@pytest.mark.cassette_stability`) runs the scenario 3 times in the same pytest session and asserts byte-identical `(outcome.state, outcome.attempt, ledger.head())` tuples across runs.

#### Nit

9. **(coverage — nit) `evidence_paths["patch"]` distinct path pre-condition.** The `_patch_blake3_for` fallback path hashes the file at `evidence_paths["patch"]`. If both attempts share that path (e.g., overwritten workdir), the fallback silently passes. **Fix:** add a pre-assertion: `attempts[0].evidence_paths["patch"] != attempts[1].evidence_paths["patch"]`. Cheap, mutation-resistant.

### Test-quality critic (7 findings: 3 block, 3 harden, 1 nit)

#### Block-tier

10. **(test-quality — block) Fence-prompt assertion is satisfied by *any* fenced prompt in the cassette.** `_extract_phase4_prompts` returns a flat `list[str]`; the assertion `fenced = [p for p in prompts if re.search(...)]` is non-empty even if attempt 2's hook was never invoked and the fence appeared only in interaction-0 (a stray re-record). **Fix:** AC-FENCE-TARGET-1 — the helper returns an ordered `list[Phase4Interaction]`; the assertion targets **`interactions[1].prompt_text`** specifically (the second call). Pair with AC-FENCE-COUNT-1: `sum(1 for i in interactions if FENCE_RE.search(i.prompt_text)) == 1` — exactly one fenced prompt, in the second slot. Mutation-killer: a runner that skips the second invocation fails AC-FENCE-COUNT-1; a runner that double-fences both calls fails AC-FENCE-COUNT-1; a runner that fences the wrong call fails AC-FENCE-TARGET-1.
11. **(test-quality — block) `outcome.state == "passed"` + `outcome.attempt == 2` is mutation-passing alone.** A buggy `GateRunner.run` that returns `GateOutcome(state="passed", attempt=2)` unconditionally — without ever calling the sandbox or the hook — passes. **Fix:** AC-MUT-OUTCOME-1 — pair with ledger inspection: `attempts[0].attempt_id == 1`, `attempts[0].outcome.state == "failed_retryable"`, `attempts[1].attempt_id == 2`, `attempts[1].outcome.state == "passed"`, AND `spy.call_count == 1` (from AC-PRIOR-1). A runner that fabricates the outcome but does not actually loop fails on `spy.call_count` (zero) and on `len(attempts) == 2` (zero or one).
12. **(test-quality — block) Helper `_extract_phase4_prompts` leaks envelope formatting.** The helper serializes the full JSON request body with `json.dumps(body)` so the regex can run; this couples the test to whatever envelope shape VCR records (headers, model name, system prompt). A VCR upgrade that re-orders keys or adds metadata fields silently changes what the regex sees. **Fix:** AC-HELPER-1 — extract `Phase4Interaction` (`NamedTuple` with `uri: str`, `prompt_text: str` (concatenated user-role message content), `prior_attempts_serialized: str` (the JSON `prior_attempts` kwarg, empty string if absent)). All assertions consume the typed fields. Helper lives at `tests/integration/_helpers/vcr.py` from day-1.

#### Harden-tier

13. **(test-quality — harden) `pytest --no-network` invariance not enforced by the test.** AC-3 says "replays offline (`pytest --no-network`)" but no in-test fixture pins it. A future contributor could record on attempt N silently. **Fix:** AC-OFFLINE-1 — the test consumes `pytest-recording`'s `block_network` fixture (or VCR's `RecordMode.NONE`) and asserts that any escape attempt raises `RuntimeError` (or `vcr.errors.CannotOverwriteExistingCassetteException`).
14. **(test-quality — harden) Wall-clock budget not enforced.** AC-12 names ≤90 s but no `@pytest.mark.timeout`. **Fix:** AC-TIMEOUT-1 — `@pytest.mark.timeout(90)` (pytest-timeout plugin already in `pyproject.toml`'s dev deps per S0 / S1-07). If the plugin is absent at executor time, the executor surfaces the gap; does not silently skip.
15. **(test-quality — harden) Pre-execute marker BLAKE3 chain not verified at body level.** AC-7 covers row-type ordering. ADR-0007 says the marker is BLAKE3-chained into the ledger. **Fix:** AC-CHAIN-MARKER-1 — the test invokes `RetryLedger.verify_chain()` (or the equivalent S2-01 / S2-03 API) post-run and asserts no `AuditChainCorrupted` raised. The chain head advanced check (AC-9) is necessary but not sufficient — a runner that writes a non-chained `pre_execute` row (regression on ADR-0007) silently advances the head but corrupts chain replay.

#### Nit

16. **(test-quality — nit) Docstring citations.** Refactor § says "Add a docstring on the test citing the four ADRs and Goal 2." **Fix:** promote to AC-DOC-1 — module docstring contains substrings `"ADR-0001"`, `"ADR-0002"`, `"ADR-0005"`, `"ADR-0007"`, `"§Goal 2"`. Tested via `inspect.getdoc(test_module)` substring check.

### Consistency critic (5 findings: 1 block, 3 harden, 1 nit)

#### Block-tier

17. **(consistency — block) AC-10 mechanism contradicts pytest semantics.** Story says "re-running `tests/schema/test_stage6_chokepoint.py` in the same pytest session as a dependency." pytest has no first-class same-session dependency primitive (pytest-dependency is third-party and discouraged). **Fix:** AC-CHOKEPOINT-1 — S5-04's HARDENED report commits to exporting `assert_stage6_chokepoint_clean(REPO_ROOT) -> None` from the walker module. This story calls it directly: `from tests.schema.test_stage6_chokepoint import assert_stage6_chokepoint_clean; assert_stage6_chokepoint_clean(REPO_ROOT)` at the end of `test_retry_recovers_against_breaking_change_cve`. If the function is not yet exported when this story executes, the executor escalates (story BLOCKED-on-S5-04 export) — does NOT silently re-implement the walker inline.

#### Harden-tier

18. **(consistency — harden) ADR-0001 subprocess-allowlist defense not re-checked.** ADR-0001 §Consequences: "any module under `sandbox/` or `gates/` that imports `subprocess` must live in one of the three allowlisted chokepoint files; AST-walked by `tests/schema/test_no_subprocess_outside_build_chokepoint.py`." A fixture helper introduced in this story could violate. **Fix:** add a Notes-for-implementer paragraph telling the executor to re-run that fence at the end of implementation; not promoted to AC because the fence is its own dedicated test and re-running CI catches it — but a Notes mention prevents the executor from believing the chokepoint walk in AC-CHOKEPOINT-1 is the only structural defense to check.
19. **(consistency — harden) `.expected/` Specification-pattern contract not surfaced.** Phase 7's Out-of-scope fixtures (`always-fails`, `postinstall-exfil`) will follow the same shape. Story doesn't pin it as a contract. **Fix:** Notes-for-implementer paragraph naming the four canonical entries in `.expected/`: (a) `phase4_chain_head.bin` (seed); (b) `recipe_patch.diff` (canonical recipe output); (c) `llm_patch.diff` (canonical Phase-4 output); (d) `expected_first_failure.txt` (the failing-signal `first_failure` value AC-SIG-1 asserts). Phase 7 fixtures slot in without touching the helpers.
20. **(consistency — harden) Helper home `tests/integration/_helpers/` not yet established as package.** Story Refactor § creates `tests/integration/_helpers/vcr.py` on the fly. **Fix:** AC-HELPER-PKG-1 — `tests/integration/_helpers/__init__.py` exists (empty). Mirrors `tests/fence/__init__.py`, `tests/schema/__init__.py` convention.

#### Nit

21. **(consistency — nit) `Status` line.** Story is `Ready`. After validator pass, status convention is `HARDENED` (per S5-04, S5-03, etc. precedent). **Fix:** Status → `HARDENED`.

### Design-patterns critic (4 findings: 1 block, 2 harden, 1 nit)

#### Block-tier

22. **(design-patterns — block) Missing Decorator/Spy at the `ReplanHook` boundary.** The `ReplanHook` Protocol from Gap 2 is the perfect Decorator-pattern surface — wrap the real hook, observe call shape, delegate. Without a spy, the test cannot answer "was the hook invoked exactly once with one prior attempt?" without inspecting cassette innards (a leaky abstraction). Three concrete consumers today clear the rule-of-three threshold: S5-01 contract test, this story, S7-01 failed_unrecoverable test (Out-of-scope of this story but named). **Fix:** AC-SPY-1 — `tests/integration/_helpers/hooks.py` exports `ReplanHookSpy(inner: ReplanHook) -> ReplanHook` (Decorator). Attributes: `calls: list[GateContext]`, `call_count: int`. This story is the **first consumer** (S5-01 will follow when its contract test lands; S7-01 when failed_unrecoverable lands). Establishes the kernel from day-1.

#### Harden-tier

23. **(design-patterns — harden) `_extract_phase4_prompts` returning `list[str]` of JSON-stringified bodies is leaky.** See finding 12 — promoted from test-quality to design-patterns: the helper IS the cassette-introspection kernel. Typed `Phase4Interaction` NamedTuple with `uri`, `prompt_text`, `prior_attempts_serialized` is the Open/Closed seam. When Phase 7 adds new assertions (e.g., "the model name on attempt 2 differs from attempt 1"), the NamedTuple grows additively.
24. **(design-patterns — harden) `_patch_blake3_for` brittleness invites a strategy registry.** The helper has two source paths (`signals.build.details["patch_blake3"]` and `evidence_paths["patch"]` fallback). With only two paths and one test, Rule-2 simplicity wins — *don't* introduce a registry. **Fix:** Notes-for-implementer — if a third source path arrives (Phase 7's distroless emits `dockerfile_patch_blake3`, etc.), elevate to `@register_patch_blake3_source(...)` and route via a thin lookup. Today, keep the inline `or`-fallback. Records the design opportunity without paying premature-abstraction cost.

#### Nit

25. **(design-patterns — nit) `.expected/` is the Specification pattern in disguise.** Already covered by finding 19. Just naming the pattern explicitly in Notes helps the next fixture author.

## Edits applied to the story

1. **Header:**
   - `Status: Ready` → `Status: HARDENED`
   - `Depends on: S5-03, S5-04` → `Depends on: S5-01, S5-02, S5-03, S5-04`
   - `ADRs honored:` widened with phase-arch-design Gap 2 reference.
2. **Inserted `## Validation notes (2026-05-25)` block** between the header and `## Context` summarizing the eight load-bearing changes.
3. **Acceptance criteria** — rewritten as a graded set: original ACs retained or tightened; new ACs added (AC-SIG-1, AC-PRIOR-1, AC-CANARY-1, AC-FENCE-SIZE-1, AC-FENCE-TARGET-1, AC-FENCE-COUNT-1, AC-SUMMARY-CONTENT-1, AC-PROTO-1, AC-OFFLINE-1, AC-TIMEOUT-1, AC-CHAIN-MARKER-1, AC-CHOKEPOINT-1, AC-CASS-DET-1, AC-SPY-1, AC-HELPER-1, AC-HELPER-PKG-1, AC-DOC-1, AC-MUT-OUTCOME-1).
4. **Implementation outline** — Step 2 expanded to construct the `ReplanHookSpy` and the typed `Phase4Interaction` helper from day-1; Step 4 helper renamed and re-typed.
5. **TDD plan** — red test rewritten: spy fixture, ordered interaction parsing, attempt-2-specific assertions, prior-attempts length, canary-match count, fence size, chain verification, timeout marker, block-network mode.
6. **Files to touch** — added `tests/integration/_helpers/__init__.py`, `tests/integration/_helpers/hooks.py`, `tests/integration/_helpers/vcr.py`; added `tests/fixtures/repos/breaking-change-cve/.expected/recipe_patch.diff`, `…/llm_patch.diff`, `…/expected_first_failure.txt`; added `tests/integration/gates/test_stage6_retry_recovers_replay_stable.py`.
7. **Notes for the implementer** — added paragraphs on the `.expected/` Specification contract, the `ReplanHookSpy` rule-of-three rationale, the `_patch_blake3_for` deferred-registry decision, and the cross-phase Phase-7-fixture compatibility expectation.

## Verdict

**HARDENED.** Every gap is in-scope to fix in place; goal text and overall scope are unchanged. Story is now ready for `phase-story-executor`.
