# Validation report — S7-01 fence-CI seven structural assertions

**Story:** [`S7-01-fence-ci-seven-assertions.md`](../S7-01-fence-ci-seven-assertions.md)
**Validated:** 2026-07-26
**Verdict:** HARDENED
**Validator:** phase-story-validator (scheduled `story-validation-corrector` task)

## Executive summary

S7-01 lands the load-bearing PR-time defense that Phase 7+ inherits — every future task class hits these gates. The original draft was well-structured and TDD-shaped but carried **four block-grade inconsistencies** with prior HARDENED stories in this phase and would have let several classes of wrong implementation pass. The four blocks:

1. **File location.** `tests/unit/test_eval_fence.py` violates HARDENED S1-05 F-DP-8 (`tests/fence/` is the eval-subsystem fence-test location; the pyproject fence in `tests/unit/` is a pre-existing exception, not the convention).
2. **Substring-ban source-of-truth.** Assertion #5 inlined the four banned substrings; HARDENED S1-05 AC-6 canonicalised them at `codegenie.eval._smuggling.SMUGGLING_SUBSTRINGS` and S1-05 AC-7 **explicitly names S7-01 as a consumer** that must import — the inline literal set is forbidden.
3. **Missing alias-dodge assertion.** `final-design.md §Fence-CI test extension` requires both a literal-arg check AND a literal-decorator-symbol check ("closes critic's alias-dodge"). Original story covered only the arg check.
4. **Wall-clock canary recursion.** The `subprocess.run(["pytest", ...])` canary would blow the 2s budget on its own pytest cold-start (~1–1.5s alone in CI) and is fragile under matrix builds.

Plus nine harden-grade gaps that let mutation-shaped wrong implementations slip through: adversarial tests that assert only "diagnostic fires" (mutation: `assert False` passes), no case-toml filter on `iterdir()` (mutation: `__pycache__` counts as a case), no empty-bench edge case (mutation: fresh checkout crashes), no reject-non-literal-kwargs case (mutation: `min_cases_for_promotion=SOME_CONSTANT` silently passes), tier-ordering unspecified vs YAML (mutation: hardcode silver-index=1 works until Phase 7+ reorders tiers), malformed AST silently upraises `SyntaxError` (mutation: bad file crashes with no context), `case_id == path.parent.name` unpinned to exact-string equality (mutation: substring/case-fold check passes), no `FenceViolation` sum-type discipline (adversarial tests can't introspect fields), no `TaskClassName`/`CaseId` NewTypes (parameter-swap defects).

**Twenty findings applied in this pass — 4 blocks, 10 hardens, 6 nits.** Story now inherits the S1-05 / S2-01 / S5-01 HARDENED patterns faithfully with S7-01-specific adaptations for the alias-dodge fuse, wall-clock instrumentation via a session-stash pytest hook, and paired violation/`_control` adversarial fixtures.

The story remains at exactly 7 assertion-tests (assertion #4 fuses two AST-level rejections into one test); supporting tests (empty-bench edge-case, wall-clock canary) are called out in AC-1 as *not counted* toward the seven. Extension-seam for an 8th+ assertion (registry pattern) is recorded in Notes-for-implementer with a Rule-of-Three trigger, but not applied now.

## Critic lenses run

Four validator lenses (Coverage, Test-Quality, Consistency, Design-Patterns) run inline as one analysis pass against the S1-05 / S2-01 / S5-01 HARDENED baselines and the phase's ADR-0004 / ADR-0006 / ADR-0008 contracts. No `NEEDS RESEARCH` items — every pattern is precedented in HARDENED stories in this phase (S1-05 `_smuggling.py` extraction; S1-05 `tests/fence/` convention; S5-01 diagnostic-content + adversarial-content pattern; `codegenie._fence:FORBIDDEN_LLM_SDKS` pattern). Priority: `Consistency > Coverage > Test-Quality > Design-Patterns`.

## Findings

### Blocking (must fix before executor)

**F-CON-1 [CONSISTENCY] — fence-test location `tests/unit/` violates HARDENED S1-05 convention.**
Story places `test_eval_fence.py` under `tests/unit/`. HARDENED S1-05 F-DP-8 established `tests/fence/` as the canonical location for eval-subsystem fence tests — S1-05 moved `test_bench_score_static.py`, `test_eval_package_imports_no_llm_sdk.py`, `test_eval_static_negatives.py` all to `tests/fence/`. S1-05 AC-7 also names S7-01 explicitly: *"When future stories (S3-04 runtime defense-in-depth, S7-01 fence assertion #5) consume the same list, they import from the same source."* Placing S7-01's tests in `tests/unit/` breaks the convention and makes future eval-fence discovery inconsistent.

**Fix:** Rewrote every reference to `tests/unit/test_eval_fence.py` → `tests/fence/test_eval_fence.py`. Added `tests/fence/conftest.py` for the wall-clock hook and `tests/fence/test_eval_fence_helpers.py` for the helper unit tests. Story title updated; Files-to-touch table restructured; TDD plan updated. Confirmed the pyproject fence's `tests/unit/test_pyproject_fence.py` location is a pre-existing exception (not a convention to follow).

**F-CON-2 [CONSISTENCY] — assertion #5 duplicates the smuggling substrings inline.**
Original TDD plan had `banned = ("confidence", "llm", "self_reported", "model_says")` hardcoded in the test. HARDENED S1-05 AC-6 canonicalised this at `codegenie.eval._smuggling.SMUGGLING_SUBSTRINGS: Final[frozenset[str]]`. S1-05 AC-7 named S7-01 as an explicit consumer that must import — the literal four-string set MUST NOT appear inline; a `grep -E '"confidence"|"llm"|"self_reported"|"model_says"' tests/fence/test_eval_fence.py` MUST return empty. Inlining breaks S1-05's single-source-of-truth invariant; the ban list drifts across three call sites (`_smuggling.py`, `test_bench_score_static.py`, `test_breakdown_keys_static.py`, S7-01 fence #5), and a Phase 16+ expansion (e.g., adding `"model_thinks"`) would leave one site un-updated.

**Fix:** Rewrote assertion #5's AC and TDD-plan test to `from codegenie.eval._smuggling import SMUGGLING_SUBSTRINGS`. Added an explicit AC clause: the grep-for-inline-literals MUST return empty. Added the imperative-import to Notes-for-implementer with reference to S1-05 AC-7's forward-name.

**F-CON-3 [CONSISTENCY] — missing structural check for alias-dodge decorator symbol.**
`final-design.md §Fence-CI test extension` explicitly requires *two* Stage-1 checks: (a) first positional arg is a string literal AND (b) *"we require the literal symbol name `register_task_class` in the decorator position — closes critic's alias-dodge with a one-line lint rule"*. The original story covered only (a). A contributor writing `from codegenie.eval import register_task_class as rtc` then `@rtc("foo")` bypasses assertion #1's AST-walker (which greps for the literal string `"register_task_class"` in `func.id`), and would smuggle in a task class without the fence catching it. This is the exact "alias-dodge" attack the design was written to prevent.

**Fix:** Fused into assertion #4 (renamed `test_fence_4_literal_registration_argname_and_decorator_symbol`) as sub-check (b): walk `ImportFrom` nodes in each `bench/*/registration.py`; if `register_task_class` is imported with `alias.asname != None`, emit a `FenceViolation(assertion_id=4, ...)`. Added `test_fence_aliased_decorator_symbol.py` to the adversarial suite (F-CON-3-adjacent add). Documented acknowledged residuals (getattr-based / local-name dynamic references) in Notes with CODEOWNERS as compensating control, matching ADR-0008 §Tradeoffs posture.

**F-CON-4 [CONSISTENCY] — wall-clock canary recursion pattern is fragile and self-defeating.**
Original canary: `subprocess.run(["pytest", "-q", "tests/unit/test_eval_fence.py", "--deselect", ...])`. Problems:
- **Blows the budget on its own overhead.** pytest cold-start alone is ~1–1.5s in CI; the canary spawns pytest inside a pytest run, doubling the cost. With the assertions themselves adding another 300–800ms, the recursive run trivially exceeds 2s — the canary fails on itself, not on a real assertion regression.
- **CI-matrix fragility.** `["pytest", ...]` resolves via PATH; matrix cells with different Python/uv layouts (Ubuntu 24.04 × Python 3.11/3.12) can resolve to different pytest binaries. `sys.executable + ["-m", "pytest", ...]` is better but still fragile.
- **Recursion detection risk.** A pytest plugin that stops re-entry could deselect the canary silently.
- **Signal loss.** Even if the canary runs, it reports a single scalar; a real regression (assertion #3 grows 10× because of `bench/` growth) is hidden.

**Fix:** Replaced with a `pytest_runtest_call` hookwrapper in `tests/fence/conftest.py` that accumulates per-assertion durations into `session.stash`; a final `test_fence_combined_wall_clock_under_two_seconds` reads the sum. On regression, the diagnostic names the three slowest tests + their individual wall-clock (real signal). No subprocess; no recursion. Added AC-4 with the full contract.

### Hardening (should fix)

**F-COV-1 [COVERAGE] — no AC for empty-bench edge case.**
On a fresh repo checkout or during Phase 6.5 Step 1 landing (before any `bench/foo/registration.py` exists), the fence assertions must not crash. Original tests iterate `walk_registrations(BENCH_ROOT)` — if empty, `for` yields nothing and every test trivially passes. But `walk_registrations` itself must not raise on an empty (or non-existent) `bench/`. Without an explicit test, a defensive `raise FileNotFoundError` in the helper would silently break the fresh-checkout dev loop.

**Fix:** Added AC-5 and `test_fence_empty_bench_returns_no_violations(tmp_path)` — creates an empty `bench/` tmpdir, calls every finder, asserts every returns `()`.

**F-COV-2 [COVERAGE] — no AC for malformed AST diagnostic.**
If a `bench/*/registration.py` has a Python syntax error, `ast.parse` raises `SyntaxError`. Without an AC pinning the fence's reaction, the natural (buggy) implementation would let the `SyntaxError` upraise out of the fence, giving the contributor a stack trace ending in `ast.py:...` with no context about *which* bench file failed. The fence's contract is path-specific diagnostics; a stack trace violates that.

**Fix:** Added AC-8: if any `bench/*/registration.py` fails to parse, fence emits `FenceViolation(..., message="bench/{name}/registration.py failed to parse: {err}")` — the fence does NOT raise `SyntaxError` upward. Applied to assertions #1, #2, #3, #4 (all of which parse registration.py).

**F-COV-3 [COVERAGE] — no AC for non-literal `min_cases_for_promotion` kwarg.**
Assertions #2 and #3 both read `min_cases_for_promotion` from the decorator's `ast.Call.keywords`. If the kwarg value is a name reference (`min_cases_for_promotion=MIN_CASES`) rather than an inline dict literal, a defensive implementation would either (a) fall back to a default and silently under-check, or (b) crash. Without an AC pinning the behavior, both are open.

**Fix:** Added AC-8 clause: the `min_cases_for_promotion` kwarg value MUST be an inline `ast.Dict` with `Constant[str]` keys and `Constant[int]` values; any other shape emits a `FenceViolation` from assertion #4. Rationale: `min_cases_for_promotion` is a load-bearing gate criterion (ADR-0002 references it); allowing it to be dynamically computed silently would violate the same "no hidden state" principle assertion #4 exists to enforce.

**F-COV-4 [COVERAGE] — no `case.toml`-filter on `iterdir()` in AC-2.**
Original AC-2's test: `case_dirs = [p for p in (BENCH_ROOT / tc / "cases").iterdir() if p.is_dir()]`. This counts `__pycache__`, `.pytest_cache`, `_control` (from fixture dirs — see F-COV-5 note), and stray directories as cases. A contributor could accidentally satisfy the 10-case floor with 5 real cases + 5 dot/underscore dirs, silently under-testing.

**Fix:** Added AC-6 (case-dir filter contract): the shared helper `iter_case_dirs(bench_root, tc)` yields only child dirs of `bench/{tc}/cases/` that (a) do not start with `.` or `_`, AND (b) contain a `case.toml` file. Unit-tested separately in `tests/fence/test_eval_fence_helpers.py`. Assertions #2 and #7 both use this helper.

**F-COV-5 [COVERAGE] — no AC for tier-ordering-from-YAML.**
Original notes said "read the YAML, find the index of each tier" but no AC pinned it. A defensive implementer could hardcode `if tier in ("silver", "gold", "platinum")` and pass every test — until Phase 7+ adds `titanium` to `docs/trust-tiers.yaml`, at which point the fence silently under-flags. Without an AC and a `grep -w silver src/codegenie/eval/_fence.py MUST return empty` check, the constraint isn't verifiable.

**Fix:** Added AC-7: silver-tier-index resolved from `docs/trust-tiers.yaml`; no hardcoded tier-name comparison anywhere in `_fence.py`. `grep -w 'silver\|gold\|platinum' src/codegenie/eval/_fence.py` MUST return empty. If the YAML doesn't list `silver`, the fence emits a `FenceViolation` naming the missing-tier config drift (fail loud on YAML drift, not silent).

**F-COV-6 [COVERAGE] — no AC pinning `case_id == path.parent.name` semantics.**
Original AC-1 sub-point 7 said "`case_id` matches its containing directory name" without specifying equality kind. A defensive implementer could ship substring-match (`case_id in path.parent.name`) or case-fold match (`case_id.lower() == path.parent.name.lower()`) and pass every test that only exercises exact-match cases. The semantics matter — case-id is a stable identifier used across audit records; a mismatch that only surfaces case-fold-later would corrupt audit-chain lookups.

**Fix:** Added to AC-1 sub-point 7: "exact string equality — no substring, no case-fold". Rippled to Implementation-outline §9.

**F-TQ-1 [TEST-QUALITY] — adversarial tests only assert "diagnostic fires", not that the message names the path.**
Original AC: "Seven adversarial-failure tests live under `tests/adv/`, each provoking exactly one diagnostic on a synthetic fixture." Mutation: an implementer whose `_fence.py` emits `raise AssertionError("assertion failed")` with no context still satisfies this AC — the adversarial test sees an AssertionError and passes. But the *point* of the fence is path-specific diagnostics; the mutation defeats the whole story goal.

**Fix:** Rewrote AC (now AC-9) to require: each adversarial test asserts BOTH (a) the violation-fixture yields ≥ 1 `FenceViolation` of the expected `assertion_id`, AND (b) `violations[0].message` contains the expected task-class + path substrings. The (b) part is mutation-resistant: an implementer whose message is `"assertion #N failed"` fails the adversarial test.

**F-TQ-2 [TEST-QUALITY] — no control-fixture pairing on adversarial tests.**
Original design has `tests/fixtures/fence/<assertion>/` (one dir per adversarial). Mutation: an implementer whose fence always emits a `FenceViolation` (even on clean bench) passes the adversarial test — the test only checks that violation-fixture fails. Without a control-fixture that must pass, the adversarial suite proves "the check fires" but not "the check fires ONLY on the violation".

**Fix:** Reshaped AC-9 (and Files-to-touch) — each adversarial fixture becomes a directory pair `tests/fixtures/fence/<N>-<name>/{violation,_control}/`. Adversarial test asserts violation-fixture yields a `FenceViolation` AND control-fixture yields `()`. Also fixes a latent bug: without the leading `_` on `_control/`, a raw `iterdir()` on the fixture parent would count the control as a case (feeds F-COV-4).

**F-TQ-3 [TEST-QUALITY] — no meta-test for diagnostic content shape.**
Even with F-TQ-1 fixed on the adversarial side, the *positive* path (`test_fence_N_*` in the main module) has no assertion about diagnostic content — it fires only if the current bench has a real violation, which shouldn't happen in normal CI. A meta-test that instantiates a synthetic violation and asserts the message contains task-class + path is the mutation-resistant complement.

**Fix:** Added AC-3 (diagnostic content): a parametrised meta-test in `test_eval_fence_helpers.py` asserts, for each assertion, that a synthetic violation's stringified message contains BOTH the task-class name AND the path. Enforced via imported template constants (`_DIAG_MISSING_PATH = "task class '{tc}' registered but {path} missing"`) — the tests import the templates, not regex over the emitted message.

**F-DP-1 [DESIGN-PATTERNS] — bare AssertionError raises lose structure.**
Original design raises AssertionError from each test with an f-string message. Adversarial tests then would have to regex-match message substrings to introspect violation type. A structured `FenceViolation` dataclass makes the violation set both greppable and program-checkable (adversarial tests assert on `.path`, `.task_class`, `.assertion_id`), and keeps message templates in one location. It also matches the codebase pattern (`FailureMode` from ADR-0004 is the same shape) — inconsistency between the fence's ad-hoc strings and the eval-runner's `FailureMode` typed sum would be a smell.

**Fix:** Added AC-2 requiring `@dataclass(frozen=True, slots=True) FenceViolation(assertion_id: int, task_class: str, path: Path, message: str)` in `_fence.py`. Every finder returns `tuple[FenceViolation, ...]`; every test collects into a tuple and asserts empty. Rippled through Implementation-outline §2 and the TDD-plan Red test.

**F-DP-2 [DESIGN-PATTERNS] — no NewType identifiers on helper signatures.**
`_fence.py` helpers take/return raw `str` for task-class names, case IDs, and (sometimes) file paths. A three-`str` signature like `_diagnose_case_collision(tc, case_id, other_case_id)` invites parameter-swap defects. This project already uses `NewType` extensively (`codegenie.types.identifiers`); the fence helpers should follow suit.

**Fix:** Added AC-10 requiring `TaskClassName = NewType("TaskClassName", str)` and `CaseId = NewType("CaseId", str)` on helper signatures. Local declaration in `_fence.py` unless the executor finds a natural slot in `codegenie.types.identifiers`. `mypy --strict` (per AC-12) catches parameter swaps.

**F-DP-3 [DESIGN-PATTERNS] — extension seam for 8th+ assertion not documented.**
The seven finder functions live in `_fence.py`; the test file iterates them explicitly. Phase 7+ Out-of-scope calls out possible future assertions (naming conventions, `case_id`-format regex). When these land, the current shape means editing `_fence.py` AND `test_eval_fence.py` for each new assertion — soft violation of "extension by addition". Rule of Three: three fence-families in the repo, each with its own module — no cross-family registry pressure yet. But the 8th assertion within *this* file would force the extraction.

**Fix (deferred — surfaced as Notes, not applied).** Documented in Notes-for-implementer: when Phase 7+ adds an 8th assertion, extract a `FenceAssertion` registry (`@register_fence_assertion(id=N, name=...)`); the test module iterates the registry. Not applied now (Rule 2 — YAGNI at the rule-of-three threshold; three finders is exactly the threshold, four forces it). Elevated the "extension by addition" observation as an *observable* future constraint rather than a pattern-name mandate now.

**F-DP-4 [DESIGN-PATTERNS] — `ast.parse` per-assertion is O(N²) latent.**
Original refactor note mentioned "cache `ast.parse` results across assertions sharing a file." Left as a refactor-hint but not pinned. At current bench size (~20 files) this is fine; at Phase 15's expected 5+ task classes with 10+ cases each and multiple `.py` files, unbounded per-assertion parsing adds up.

**Fix:** Added to refactor section: parse each source file ONCE via an `@functools.cache`-decorated `_parse_registration(path: Path)`. Not a block; a maintainability note. `functools.cache` on module-level function keeps the cache session-scoped (correct: fence runs are short-lived).

### Nits

**F-NIT-1** — `case_count_floor_for` reads awkwardly (cosmetic). Deferred; the name is grep-consistent with `walk_registrations`.

**F-NIT-2** — the `--fence-only` pytest marker in original refactor was speculative (no user-signal for it); dropped from refactor list. `make test` already runs everything; `pytest tests/fence/` is the fence-only sweep.

**F-NIT-3** — story used "seven assertions" in title but then discussed eight (with case-id uniqueness as new). Updated title/text to consistently say "seven assertion tests" (assertion #4 fuses two AST-level rejections into one test) — count is now stable across title/AC/impl-outline.

**F-NIT-4** — `Depends-on` line lacked S1-05 (SMUGGLING_SUBSTRINGS import target) and S4-05 (trust-tiers.yaml). Added both to the story header per F-CON-2 and F-COV-5 dependencies.

**F-NIT-5** — `_fence.py` imports `pyyaml` at module top. `codegenie.eval` is already pyyaml-dependent (per S1-01 / S1-02 ADRs); no additional constraint. Confirmed via `pyproject.toml` — no action.

**F-NIT-6** — the `pytest_runtest_call` hookwrapper stashing durations into `session.stash` is a subtle pytest API. Added an inline note in the TDD-plan conftest.py explaining the intent (per Rule 8 — future-you needs to understand why).

## Mutation set the hardened story resists

The tightened ACs would catch these wrong-implementation mutations:

1. **Place fence in `tests/unit/`** → F-CON-1 AC-1 pins `tests/fence/`.
2. **Inline the four smuggling substrings in the test** → F-CON-2 AC-1 sub-point 5's grep check would fail.
3. **`@rtc("foo")` (aliased decorator symbol) bypasses fence** → F-CON-3 assertion #4b catches it.
4. **Recursive `subprocess.run(pytest ...)` canary** → F-CON-4 AC-4 forbids subprocess-based measurement.
5. **Fence crashes on empty `bench/` tree** → F-COV-1 AC-5 asserts no-crash.
6. **`SyntaxError` upraises from a malformed `bench/*/registration.py`** → F-COV-2 AC-8 requires a named `FenceViolation` instead.
7. **`min_cases_for_promotion=SOME_CONSTANT` silently passes** → F-COV-3 AC-8 rejects non-literal kwarg values.
8. **`__pycache__` counts as a case** → F-COV-4 AC-6's `iter_case_dirs` filter drops it.
9. **Hardcoded `("silver", "gold", "platinum")` tier list** → F-COV-5 AC-7's grep check fails.
10. **`case_id in path.parent.name` (substring)** → F-COV-6 AC-1 sub-point 7 requires exact equality.
11. **`raise AssertionError("assertion failed")` with no context** → F-TQ-1 AC-9 adversarial tests check message content.
12. **Fence always emits a violation (even on clean bench)** → F-TQ-2 AC-9 requires control-fixture to yield `()`.
13. **Bare `raise AssertionError(...)` instead of `FenceViolation` sum type** → F-DP-1 AC-2 requires the frozen dataclass.
14. **Parameter-swap: `_diagnose(case_id, tc, path)` typo** → F-DP-2 AC-10's `NewType`s + `mypy --strict` (AC-12) catch the swap.
15. **Repeated `ast.parse` on the same file per assertion (O(N²))** → F-DP-4 refactor requires `@functools.cache`.
16. **Functional-form `BreakdownKey = StrEnum(...)` bypasses assertion #5** → AC-1 sub-point 5 rejects the functional form at parse time.
17. **`yaml.load` (unsafe) in assertion #6** → assertion #6 uses `yaml.safe_load` only; defense-in-depth mirror of HARDENED S5-01 F-COV-3.
18. **Non-dict top-level in `failure_modes.yaml` (empty file returns `None`)** → assertion #6 asserts top-level is a `dict`.
19. **`case_id` collision only within a task class, not across** → assertion #7 collects `(task_class, case_id)` tuples globally.

## Conflicts resolved

- **Coverage vs Design-Patterns.** Coverage wanted an AC pinning "the fence must not use `subprocess.run(...)` anywhere". Design-Patterns wanted a `FenceRunner` abstraction that could inject a mock timer. Consistency wins (source-of-truth is CLAUDE.md Rule 2 — Simplicity First): the wall-clock hook is a straight pytest hookwrapper, no abstraction; the AC is phrased as an observable constraint ("no subprocess-based measurement in AC-4") rather than a design mandate.
- **Consistency vs Coverage.** Consistency flagged "seven" in the title as inaccurate (the alias-dodge check adds an 8th logical check). Coverage wanted a separate `test_fence_4b_aliased_decorator_symbol` for clarity. Consistency wins (Rule 3 — Surgical Changes): the checks fuse into one test function per phase-arch-design's assertion count; the title stays "seven assertion tests"; the fuse-vs-split rationale is called out in AC-1 and Notes.
- **Design-Patterns vs Rule 2 (YAGNI).** Design-Patterns wanted the extension-seam registry now. Rule 2 wins: three finders is exactly the rule-of-three threshold; four forces the extraction; the current design is documented and the trigger is spelled out.
- **Test-Quality vs Rule 3 (Surgical Changes).** Test-Quality wanted a property-based (`hypothesis`) test generating arbitrary bench trees. Rule 3 wins: not surgical to this story's scope (which is "seven assertions + adversarials"); recorded as a future defense-in-depth in the extension-seam note.

## Post-validation grep checks (verify at executor time)

- `grep -E '"confidence"|"llm"|"self_reported"|"model_says"' tests/fence/test_eval_fence.py` returns empty (F-CON-2 / AC-1 sub-point 5).
- `grep -w 'silver\|gold\|platinum' src/codegenie/eval/_fence.py` returns empty (F-COV-5 / AC-7).
- `grep -E 'subprocess\\.run|subprocess\\.Popen|os\\.system' tests/fence/test_eval_fence.py tests/fence/conftest.py` returns empty (F-CON-4 / AC-4).
- `grep -rE 'from codegenie\\.eval import register_task_class as' tests/adv/` matches `test_fence_aliased_decorator_symbol.py` (only) — the aliased-import test is the only place the alias appears intentionally.

## Files edited

- `docs/phases/06.5-per-task-class-eval-harness/stories/S7-01-fence-ci-seven-assertions.md` (in place per skill contract).
- `docs/phases/06.5-per-task-class-eval-harness/stories/_validation/S7-01-fence-ci-seven-assertions.md` (this file — new).

No source-code edits (validator is not the executor).

## Verdict rationale

**HARDENED** — original story had real, fixable weaknesses (four block-grade consistency violations against prior HARDENED stories in this phase; nine mutation-thin ACs / TDD-plan tests). All fixable in-place with patterns precedented in HARDENED S1-05 / S2-01 / S5-01. Story now traces every AC back to the goal ("seven structural assertions, path-specific diagnostics, ≤2s wall-clock"), every AC is verifiable, every AC would fail on the mutation set above. Ready for the executor.
