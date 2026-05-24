# Story S6-07 — Determinism-under-cassette-replay property test

**Step:** Step 6 — Compose FallbackTier + register typecheck.typescript SignalKind + integration
**Status:** HARDENED
**Effort:** M
**Depends on:** S6-01 (FallbackTier shell + ten-event-tape contract + `make_fallback_tier_for_fixtures` factory + event registry in `src/codegenie/plugins/events.py`), S6-02 (retry-bypass branch + `RagSkippedOnRetry` event + `Sequence[AttemptSummary] = ()` signature), S3-05 (`tests/cassettes/anthropic/cassettes.lock` BLAKE3 manifest), S3-06 (`make refresh-cassettes` operator workflow + cassette-steward CODEOWNERS)
**ADRs honored:** ADR-04-0002 (Pipeline; "the chain order *is* the policy"; deterministic when cassette is fixed; every step one audit event — debuggability is a sequence), ADR-04-0014 (cassette discipline + `cassettes.lock` BLAKE3 manifest supports deterministic replay), ADR-04-0008 (two-threshold band is pure; degraded/hit/miss classification is config-driven), ADR-04-0011 (retry-bypass path must be just as deterministic as initial-plan path)

## Validation notes (phase-story-validator v1, 2026-05-23)

Hardened via `phase-story-validator` (verdict: **HARDENED**). Four block-tier and ~14 harden-tier findings resolved against arch / ADRs / sibling-story-validation lineage (S6-01, S6-02). Full report: [`_validation/S6-07-determinism-cassette-replay-property.md`](_validation/S6-07-determinism-cassette-replay-property.md).

Most consequential changes:

1. **Determinism key tuple reconciled — arch (four-tuple) vs final-design (eight-tuple).** Per Global Rule 7 (surface conflicts), the story now pins the **eight-tuple** from `final-design.md §Phase 4 Goals` (`repo_snapshot_sha, cve_record_digest, plugin_version, recipe_version, vuln_index_digest, store_digest, embedding_model_digest, cassette_blake3`) as the constancy contract, with the four-tuple from `phase-arch-design.md §Idempetence` recognised as a *projection* — the four critical legs that admit the most failure modes. Group A AC-TUPLE-1..-3 require all eight legs to be captured, logged via `structlog`, and asserted constant across all 50 runs.
2. **Allowlist replaced with closed-set `NonDeterministicField: StrEnum` (Design-Patterns #1).** `ALLOWED_NONDET_FIELDS: Final[tuple[str, ...]]` was raw `str` — typos would silently expand the allowlist and pass `mypy --strict`. Group B AC-ENUM-1..-3 specifies `class NonDeterministicField(StrEnum)` with explicit members (`EMITTED_AT`, `AUDIT_EVENT_ID`, `BUDGET_TOKEN_ID`, `WORKFLOW_ID`, `LEAF_RESPONSE_ID`). A module-level fence test (`tests/fence/test_determinism_allowlist_exhaustive.py`) walks every event class declared in `src/codegenie/plugins/events.py`'s `_INTERNAL_CLASSES` and asserts that every `uuid4`-defaulted field, every `datetime`-typed field, and every `Field(default_factory=...)` field of non-deterministic shape **is** in the enum — catching the "new event kind added with a clock-derived field, allowlist not updated" regression.
3. **`payload_digest_blake3` clarified as in-test computed (Coverage #2).** S6-01's event types do not all carry a `payload_digest_blake3` field — the original AC3 was ambiguous. Group C AC-DIGEST-1..-3 introduces a pure helper `_deterministic_digest(event: WorkflowInternalEvent) -> BlobDigest` that calls `_strip_nondet`, canonically serialises to JSON via `_canonical_json` (sorted keys, no whitespace, UTF-8, `default=_to_dict_recursive`), and BLAKE3-rolls the bytes. AC requires the helper itself be pure (AST-walked: no `time.*`, no `random.*`, no `os.urandom`).
4. **`CompareReport` sum type — functional core / imperative shell (Design-Patterns #5, #9).** Replaces `assert len(distinct_diffs) == 1` and `_diff_runs(...)` ad-hocery with a pure sum type `CompareReport = AllRunsIdentical | DiffBytesDiverged(run_index, byte_offset, len_lhs, len_rhs) | EventTapeDiverged(run_index, event_index, kind_lhs, kind_rhs, payload_diff) | StateLeakDetected(reason)` (frozen Pydantic, `extra="forbid"`). The test body becomes: `report = _compare_runs(results, event_tapes); assert isinstance(report, AllRunsIdentical), report.format_diagnostic()`. **Makes illegal states unrepresentable** — a "both equal and diverged" verdict cannot exist. Pure helpers tested in isolation in `tests/unit/test_determinism_compare.py`.
5. **Three branch coverage: happy-path / retry / RagDegraded (Coverage #6).** Original story covered initial-plan + retry-bypass only. ADR-04-0008's `RetrievalOutcome = RagHit | RagDegraded | RagMiss` discriminated union has *three* arms; determinism must hold across all three. Group D AC-BRANCH-1..-4 parametrizes over `(initial, RagHit)`, `(initial, RagDegraded)`, `(initial, RagMiss)`, `(retry, RagSkippedOnRetry)` — four cassette sub-directories, each with its own 50-iteration determinism property. AC-BRANCH-5 asserts the **same** `CompareReport.AllRunsIdentical` shape regardless of branch — determinism is *structural*, not branch-specific.
6. **Cassette-vs-`cassettes.lock` BLAKE3 integrity (Consistency #5).** ADR-04-0014 pins per-cassette BLAKE3 in `cassettes.lock` as a content-addressed manifest; a contributor re-recording without updating the lock is a CI-block. Group E AC-LOCK-1..-3 adds: (a) every cassette this story creates ships a `cassettes.lock` entry the same commit, (b) a session-scoped autouse fixture asserts `blake3(open(cassette_path).read()) == cassettes.lock[entry]` before each iteration, (c) cassette-miss diagnostic names `make refresh-cassettes` per CLAUDE.md "fail loud" Rule 12.
7. **Memoized-`Transform` cheat detection (Test-Quality #6).** A `return self._cached_transform` implementation would trivially pass the original byte-equality check. Group F AC-FRESH-1..-3 asserts: (a) `len({id(r) for r in results}) == ITERATIONS` (every result is a distinct Python object), (b) `tier` is re-constructed via `make_fallback_tier_for_fixtures(...)` *inside* the loop (no hoist), (c) module-level state assertion — `_MODULE_STATE_BEFORE = pickle.dumps(_capture_module_state())` before the loop, `assert _capture_module_state() == _MODULE_STATE_BEFORE` after, where `_capture_module_state` walks `sys.modules['codegenie.fallback.*'].__dict__` for any non-`Final` mutable dict / set / list and digests them.
8. **Cross-arch ONNX drift pin (Coverage #3).** ADR-04-0008 acknowledges 5th-decimal cross-arch ONNX drift. The cassette was recorded on one architecture; replaying on another may produce a `RagHit` vs `RagDegraded` outcome flip at the band boundary. Group G AC-PLATFORM-1..-2 adds: (a) `_assert_recording_arch_compatible(cassette_path)` reads a `recording_arch` sidecar (`tests/cassettes/anthropic/test_determinism/{branch}/recording_arch.json` with `platform.machine()` + `platform.system()`) and skips with a structured `pytest.skip` reason if mismatched, (b) the test marks `pytest.mark.platform_recorded` so CI can route appropriately.
9. **Per-iteration parametrize for actionable failure isolation (Test-Quality #10).** Original test asserted `len(distinct_diffs) == 1` in bulk — when it fails, only "they differ" is known. Group H AC-PARAM-1 parametrizes the per-iteration assertion via `@pytest.mark.parametrize("iteration", range(ITERATIONS))` with a session-scoped `_first_run_results` fixture — pytest reports "iteration 37 first diverged from iteration 0", not "the set has size 2".
10. **Cross-event payload identity (Test-Quality carry-forward from S6-01 + S6-02).** Sibling-story validation lineage requires: `PromptBuilt.prompt_digest_blake3 == LeafInvoked.prompt_digest_blake3` and `BudgetPrecharged.token_id == BudgetReconciled.token_id` (modulo `token_id` being in `NonDeterministicField`). Group I AC-IDENT-1..-2 carries the identity invariants forward as determinism-property sub-cases — the test runs once with a "freeze `token_id`" patch (deterministic-uuid generator) and asserts the cross-event-identity property *separately* from the byte-equality property, so a regression that breaks identity is distinguishable from a regression that breaks pipeline determinism.
11. **AST property test for non-deterministic iteration (Coverage #9).** ADR-04-0002's "the chain order *is* the policy" depends on no hidden ordering surprise. Group J AC-AST-1 adds `tests/fence/test_no_set_iter_in_fallback.py` — AST-walks every module under `src/codegenie/fallback/` and `src/codegenie/rag/` for `ast.Set()` literals used as iteration sources, raw `dict.keys()`/`dict.values()`/`dict.items()` not wrapped in `sorted(...)` at module-level data, and `os.environ` reads outside `__init__` startup. A deny-list with a small per-module `_ALLOWED_NONDET_SITES: Final[frozenset[tuple[str, int]]]` lets honest exceptions through (e.g., a `set` used purely for membership test).
12. **Hypothesis property over input-shape variation (Test-Quality #5).** The original test pinned one fixture per branch. Group K AC-HYP-1 adds `tests/property/test_determinism_under_cassette_replay_hypothesis.py` — Hypothesis draws `(advisory_within_one_cve_id, repo_ctx_with_shuffled_dep_order, recipe_selection)` variations from a small bounded domain (since cassettes are fixed, the LLM call must hit-cache) and asserts the determinism property holds. `max_examples=10` (cassette-bounded). A `HealthCheck.too_slow` allowance is whitelisted with rationale.
13. **Seed discipline + random sources (Test-Quality #9).** A `pytest.fixture(autouse=True, scope="module")` `_freeze_nondet_sources` seeds `random.seed(0)`, `numpy.random.seed(0)` (if numpy importable), and monkey-patches `uuid.uuid4` only inside the "freeze `token_id`" sub-test path — outside that path, real uuid4 is used and the allowlist absorbs it. Group L AC-SEED-1..-2 pin this.
14. **Performance budget made deterministic (Coverage #8).** "Drop to ≥ 20 if 50 overruns" was hand-wavy. Group M AC-PERF-1..-3 pin: (a) `ITERATIONS: Final[int] = 50`, with an env-override `CODEGENIE_DETERMINISM_ITERATIONS` honored only if value is in `{20, 25, 30, 40, 50}` — closed enum, no arbitrary value; (b) wall-clock cap emitted as a structured `pytest.warning` (visible in CI logs) when iteration time > 60 s; (c) if `ITERATIONS < 50`, a deterministic `WARN_REDUCED_ITERATIONS(actual, reason)` event is logged via `structlog` with the rationale string — fails loud per Global Rule 12 rather than silently passing with a weak test.
15. **`_first_divergence` and `_diff_runs` signatures pinned (Coverage #10, Design-Patterns #4).** Both helpers had ambiguous signatures. Now declared as pure module-level functions: `_first_divergence(results: Sequence[bytes]) -> int | None` (returns lowest index `i` where `results[i] != results[0]`, or `None`); `_diff_two_tapes(a: Sequence[dict], b: Sequence[dict]) -> EventTapeDiff` (returns the sum-type variant). Both AST-walked side-effect-free.
16. **Iteration-level event-count guard (Test-Quality #3).** Adds AC requiring `len(event_log.recorded) == EXPECTED_EVENT_COUNT_PER_RUN` per iteration (10 for happy-path / retry-bypass; per-branch constant per S6-01) — catches "tier-reused-across-iterations accidentally accumulates events" mutation.
17. **Default-suite vs `-m bench` tension surfaced (Consistency #1).** AC9 made the test default-suite — but a 60-second test on every PR is friction. Resolution per CLAUDE.md `pyproject.toml` markers (no `slow` marker exists; `bench` is `addopts`-excluded by default): the **happy-path** branch runs in the default suite (≤ 30 s for 50 iters under cassette-replay), the **retry / degraded / miss** branches run under a new `@pytest.mark.determinism` marker registered in `pyproject.toml` (CI runs both lanes; `make test-fast` excludes `-m determinism`). The marker registration is itself an AC.
18. **`EventDeterministicProjection` design opportunity (Design-Patterns #3, Notes-for-implementer).** With 10+ event kinds, the per-event "what's non-deterministic" knowledge belongs *on the event class*, not in a test-side allowlist. **Rule of three is not yet reached** (this is the first deterministic-projection consumer) — `Notes for the implementer` surfaces the opportunity to add a `nondet_fields: ClassVar[frozenset[str]]` to each event class in S6-08+ work. AC-LATER-1 records this as a deferred refactor, not a current-story deliverable. Story does not introduce premature abstraction (Rule 2).

## Context

Phase-arch-design §Harness §Determinism vs probabilism (lines 832–835) commits Phase 4 to deterministic behavior across every component **except** the probabilistic leaf, which becomes deterministic under cassette replay. Phase-arch-design §Idempotence (line 827) names the load-bearing key tuple: `(cassette_id, store_digest, repo_snapshot_sha, embedding_model_digest)` constant ⇒ byte-identical outcomes.

The risk is real: a flaky `dict` iteration order, a sort instability in the retriever, or a clock-based audit field that leaks into a digest can turn deterministic-by-construction into "passes locally, flakes in CI". The property test is the contract: 50 runs with the four-tuple constant must produce byte-identical `Transform.diff_bytes` and byte-identical event order (modulo timestamps and other allowlisted non-deterministic fields).

This story lands `tests/property/test_determinism_under_cassette_replay.py` as the contract test. Phase 6.5 (bench replay) and Phase 7 (E2E) both read this contract; a regression here is a Phase-4-merge blocker.

## References — where to look

- **Architecture:** [phase-arch-design.md §Harness §Determinism vs probabilism](../phase-arch-design.md) (lines 832–835); §Idempotence (line 827); §Concurrency (line 269 — single-async-event-loop); §Goals — G6 (replay).
- **Phase ADRs:** [ADR-04-0002](../ADRs/0002-fallback-tier-pipeline-no-langgraph.md) §Tradeoffs (every step one audit event — debuggability is a sequence); [ADR-04-0014](../ADRs/0014-cassette-discipline-security-control.md) (cassettes are the determinism mechanism for the leaf); [ADR-04-0008](../ADRs/0008-two-threshold-calibration-band.md) (threshold band classifier is pure).
- **Source design:** [final-design.md §Phase 4 Goals — "Deterministic under cassette replay"](../final-design.md); §"Three load-bearing structural lines" item 1.
- **High-level impl:** [High-level-impl.md §Step 6](../High-level-impl.md) Done criteria — "Determinism property `tests/property/test_determinism_under_cassette_replay.py` — 50 runs with `(cassette_id, store_digest, repo_snapshot_sha, embedding_model_digest)` constant: byte-identical `Transform.diff_bytes` and event order (modulo timestamps)".
- **Existing code (after S6-01/02):** `src/codegenie/fallback/tier.py`; `tests/cassettes/anthropic/`; `tests/fixtures/fallback_tier_callable.py`.

## Goal

Land `tests/property/test_determinism_under_cassette_replay.py`: run `FallbackTier.run` 50 times with the four-tuple `(cassette_id, store_digest, repo_snapshot_sha, embedding_model_digest)` held constant; assert byte-identical `Transform.diff_bytes` across all 50 runs AND byte-identical event-kind-sequence (modulo a documented allowlist of non-deterministic fields like timestamps and randomly-generated audit-event UUIDs).

## Acceptance criteria

### Group A — Constancy contract (the eight-tuple)

- [ ] **AC-TUPLE-1: The eight-leg constancy tuple is captured at test start.** A `DeterminismKey` Pydantic `frozen=True, extra="forbid"` model carries `(repo_snapshot_sha: RepoSnapshotSha, cve_record_digest: BlobDigest, plugin_version: PluginVersion, recipe_version: RecipeVersion, vuln_index_digest: BlobDigest, store_digest: StoreDigest, embedding_model_digest: ModelId, cassette_blake3: BlobDigest)`. The test computes the key **once** before the loop from the actual fixtures and logs it via `structlog.get_logger("phase4.determinism").info("determinism.key.computed", key=key.model_dump())`. (Source-of-truth conflict between phase-arch four-tuple and final-design eight-tuple resolved in favour of final-design per Notes-for-implementer.)
- [ ] **AC-TUPLE-2: Per-iteration constancy.** Each iteration recomputes the eight legs from the live fixture instances (not cached strings) and asserts `key_i == key_0`. Catches "fixture mutates `store_digest` mid-test" regressions.
- [ ] **AC-TUPLE-3: Tuple cardinality is locked.** A unit test in `tests/unit/test_determinism_key_shape.py` asserts `len(DeterminismKey.model_fields) == 8` exactly; adding a leg requires an ADR amendment + this AC update.

### Group B — Closed-set non-deterministic-field enum

- [ ] **AC-ENUM-1: `NonDeterministicField` is a `StrEnum`** under `tests/_determinism/nondet_fields.py` with explicit members: `EMITTED_AT`, `AUDIT_EVENT_ID`, `BUDGET_TOKEN_ID`, `WORKFLOW_ID`, `LEAF_RESPONSE_ID`. Each member has a one-line docstring (Pydantic `Field(description=...)` is not applicable to enums; comment per member). Raw `str` field names are forbidden — pin `_strip_nondet` so it accepts only `NonDeterministicField` values.
- [ ] **AC-ENUM-2: Exhaustiveness fence.** `tests/fence/test_determinism_allowlist_exhaustive.py` imports every class in `codegenie.plugins.events._INTERNAL_CLASSES`, walks `model_fields`, and asserts that **every** field whose default is `Field(default_factory=uuid4)` OR whose annotation is `datetime` is **in** `NonDeterministicField`. A new event kind with a clock-derived field that the author forgot to allowlist fails CI loudly, not silently.
- [ ] **AC-ENUM-3: No raw-`str` test-side allowlist.** The original `ALLOWED_NONDET_FIELDS: Final[tuple[str, ...]]` shape is forbidden — AST-walking test in `tests/fence/test_no_raw_str_nondet_allowlist.py` asserts no module under `tests/property/` declares a `Final[tuple[str, ...]]` named `*NONDET*` or `*ALLOWED*` outside the canonical `tests/_determinism/nondet_fields.py`.

### Group C — Deterministic event digest (clarifies original AC3)

- [ ] **AC-DIGEST-1: `_deterministic_digest(event)` is pure.** Helper under `tests/_determinism/digest.py`: `def _deterministic_digest(event: WorkflowInternalEvent) -> BlobDigest: data = _strip_nondet(event.model_dump()); canonical = _canonical_json(data); return BlobDigest(blake3(canonical).hexdigest())`. `_canonical_json` uses `json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_to_dict_recursive, ensure_ascii=False).encode("utf-8")`.
- [ ] **AC-DIGEST-2: AST-asserted purity.** `tests/fence/test_determinism_helpers_pure.py` walks `tests/_determinism/` modules: rejects `Import`/`ImportFrom` of `{time, random, os.urandom, secrets}`; rejects any `Attribute` access on `time`, `datetime.datetime.now`, `uuid.uuid4`, `os.environ`.
- [ ] **AC-DIGEST-3: Round-trip identity.** Property test (Hypothesis-drawn): for any two `WorkflowInternalEvent` instances `a, b` that differ **only** in `NonDeterministicField` members, `_deterministic_digest(a) == _deterministic_digest(b)`. Conversely, any difference in a *non*-allowlisted field changes the digest.

### Group D — Per-branch coverage (RagHit / RagDegraded / RagMiss / RetryBypass)

- [ ] **AC-BRANCH-1: Happy-path RagHit determinism.** Cassette `tests/cassettes/anthropic/test_determinism/rag_hit/cassette.yaml` + seeded store; 50 iterations; `CompareReport.AllRunsIdentical`.
- [ ] **AC-BRANCH-2: RagDegraded determinism.** Cassette `tests/cassettes/anthropic/test_determinism/rag_degraded/cassette.yaml` + seeded store with a near-match (similarity ∈ `[degraded_floor, high_floor)`); 50 iterations; same verdict shape.
- [ ] **AC-BRANCH-3: RagMiss determinism.** Cassette `tests/cassettes/anthropic/test_determinism/rag_miss/cassette.yaml` + empty store; 50 iterations; same verdict shape.
- [ ] **AC-BRANCH-4: Retry-bypass determinism.** Cassette `tests/cassettes/anthropic/test_determinism/retry_bypass/cassette.yaml` + `prior_attempts=(attempt_summary_fix,)`; 50 iterations; `retriever.query.assert_not_awaited()` per S6-02; `RagSkippedOnRetry` in event tape per S6-02; same verdict shape.
- [ ] **AC-BRANCH-5: Verdict shape is branch-invariant.** A `tests/property/test_determinism_verdict_shape.py` asserts `type(report) is AllRunsIdentical` regardless of which branch was exercised — determinism is *structural*, not branch-specific.

### Group E — `cassettes.lock` BLAKE3 integrity (ADR-04-0014)

- [ ] **AC-LOCK-1: Every new cassette ships a `cassettes.lock` entry in the same commit.** Pre-commit + CI assert: for each `tests/cassettes/anthropic/test_determinism/{branch}/cassette.yaml`, an entry `tests/cassettes/anthropic/test_determinism/{branch}/cassette.yaml: <blake3>` exists in `tests/cassettes/anthropic/cassettes.lock`.
- [ ] **AC-LOCK-2: Session-scoped lock verification.** `@pytest.fixture(scope="session", autouse=True)` `_verify_cassettes_lock`: parses `cassettes.lock`, computes `blake3` of each on-disk cassette, raises `LockMismatch(path, expected, actual)` on first mismatch (CI-block) with a fix-it message pointing at `make refresh-cassettes`.
- [ ] **AC-LOCK-3: Cassette-miss diagnostic per Global Rule 12.** When VCR cannot find a cassette, the test fails with the exact message `Cassette not found: {path}. Run 'make refresh-cassettes BRANCH={branch}' to regenerate (requires --i-understand-this-spends-tokens + CODEOWNERS approval per ADR-04-0014).`

### Group F — Fresh-tier-per-iteration + module-state guard (catches memoized-`Transform` cheat)

- [ ] **AC-FRESH-1: Result identity disparity.** `assert len({id(r) for r in results}) == ITERATIONS` — every iteration produced a distinct `Transform` object (catches `return self._cached_transform`).
- [ ] **AC-FRESH-2: Tier is constructed inside the loop.** AST-walking test `tests/fence/test_tier_constructed_per_iteration.py` parses `tests/property/test_determinism_under_cassette_replay.py` AST and asserts the `make_fallback_tier_for_fixtures(...)` call lives **inside** the `for` loop body (not hoisted above).
- [ ] **AC-FRESH-3: Module-state non-mutation across iterations.** `_capture_module_state() -> bytes` walks `sys.modules` for every module whose `__name__.startswith("codegenie.fallback")` or `.startswith("codegenie.rag")`, collects `__dict__` entries that are mutable (`dict | set | list`) **and** are not annotated `Final`, and BLAKE3-rolls a canonical serialisation. `before = _capture_module_state(); ...loop...; assert _capture_module_state() == before`. Catches "module-level cache accumulates across iterations" (Coverage #5).

### Group G — Cross-arch ONNX drift pin (ADR-04-0008)

- [ ] **AC-PLATFORM-1: Recording-arch sidecar.** Each cassette directory ships `recording_arch.json: {"machine": "<arch>", "system": "<os>", "embedder_model_digest": "<digest>"}`. The test reads it via `_assert_recording_arch_compatible(branch)` and `pytest.skip(reason="Cassette recorded on {arch}, running on {current}; ONNX 5th-decimal cross-arch drift documented in ADR-04-0008")` on mismatch.
- [ ] **AC-PLATFORM-2: `pytest.mark.platform_recorded` marker.** The marker is registered in `pyproject.toml` `[tool.pytest.ini_options].markers` and applied to the test; CI matrix routes platform-recorded tests to the matching runner; non-matching runners report a `pytest.skip` with the structured reason.

### Group H — Per-iteration parametrize for failure isolation

- [ ] **AC-PARAM-1: `@pytest.mark.parametrize("iteration", range(ITERATIONS))`.** A session-scoped `_first_run_artifacts` fixture computes results-for-iteration-0 once; each parametrized iteration `i > 0` builds a fresh tier, runs, and asserts `_compare_runs([result_0, result_i], [tape_0, tape_i])` is `AllRunsIdentical`. pytest reports "iteration 37 first diverged" rather than "the set has size 2."

### Group I — Cross-event payload identity (carry-forward from S6-01/S6-02 hardening)

- [ ] **AC-IDENT-1: Token-id identity.** With `BUDGET_TOKEN_ID` temporarily removed from `NonDeterministicField` (sub-test scope only) **and** `uuid.uuid4` monkeypatched to a deterministic sequence, a single-iteration sub-test asserts `BudgetPrecharged.token_id == BudgetReconciled.token_id`.
- [ ] **AC-IDENT-2: Prompt digest identity.** `PromptBuilt.prompt_digest_blake3 == LeafInvoked.prompt_digest_blake3` (no monkeypatch needed; these are derived, not generated). A regression that hashes the prompt twice with different canonicalisations fails here.

### Group J — AST property test against hidden non-determinism in source modules

- [ ] **AC-AST-1: `tests/fence/test_no_set_iter_in_fallback.py`** AST-walks every `*.py` under `src/codegenie/fallback/` and `src/codegenie/rag/`; flags (a) `ast.Set` literals used in `for` loops, (b) `dict.keys()` / `dict.values()` / `dict.items()` calls **not** wrapped in `sorted(...)` when the dict is at module-level scope, (c) `os.environ` reads outside `if __name__ == "__main__"` or module `__init__`. A small `_ALLOWED_NONDET_SITES: Final[frozenset[tuple[str, int]]]` per module lets pure-membership-test sets through; growth requires reviewer comment.

### Group K — Hypothesis property over input variation

- [ ] **AC-HYP-1: `tests/property/test_determinism_under_cassette_replay_hypothesis.py`.** Hypothesis draws `repo_ctx` variations (shuffled dep-list order; identical content) within one `cve_id`; `max_examples=10` (cassette-bounded); `HealthCheck.too_slow` whitelisted with rationale comment citing AC-PERF-1; property: for every drawn `repo_ctx`, the eight-tuple is constant AND `_compare_runs(...)` returns `AllRunsIdentical`. Catches "dep-list iteration order leaks into prompt body."

### Group L — Seed discipline

- [ ] **AC-SEED-1: Auto-use seed fixture.** `@pytest.fixture(autouse=True, scope="module")` `_freeze_nondet_sources`: `random.seed(0)`; `try: import numpy; numpy.random.seed(0); except ImportError: pass`; logs `structlog.get_logger().info("determinism.seed.frozen", seeds={...})`.
- [ ] **AC-SEED-2: `uuid.uuid4` policy.** Outside identity sub-tests (AC-IDENT-1), real `uuid.uuid4` is used and absorbed by `NonDeterministicField.AUDIT_EVENT_ID|BUDGET_TOKEN_ID|...`. Inside AC-IDENT-1, a deterministic-uuid generator is injected via `monkeypatch.setattr("uuid.uuid4", ...)`.

### Group M — Performance budget — closed-set, fail-loud

- [ ] **AC-PERF-1: `ITERATIONS: Final[int] = 50`** as the module-level default. The env-override `CODEGENIE_DETERMINISM_ITERATIONS` is honored **only** for values in `{20, 25, 30, 40, 50}` (`Literal[20, 25, 30, 40, 50]` validation); other values raise `ValueError` at module import.
- [ ] **AC-PERF-2: Wall-clock cap surfaces, does not skip.** When elapsed > 60 s, the test emits `structlog.warning("determinism.iteration_over_budget", elapsed=...)` and a `pytest.warns(UserWarning)`-visible warning — the test still asserts AC-BRANCH-* (no silent skip). The default-suite `pyproject.toml` `filterwarnings` does not suppress this category.
- [ ] **AC-PERF-3: Reduced-iteration audit.** If `ITERATIONS < 50`, the test emits `structlog.warning("determinism.iterations_reduced", actual=ITERATIONS, default=50, reason=<str>)` and includes the reduction in the per-test stdout summary. Fails CI if no `reason` is provided.

### Group N — Pinned helper signatures

- [ ] **AC-HELPER-1: `_first_divergence(results: Sequence[bytes]) -> int | None`** returns the lowest index `i` where `results[i] != results[0]`, or `None` if all equal. Pure; AST-asserted side-effect-free.
- [ ] **AC-HELPER-2: `_diff_two_tapes(a: Sequence[dict], b: Sequence[dict]) -> EventTapeDiff`** returns the `EventTapeDiff` sum-type variant (`Identical | LengthMismatch(len_a, len_b) | KindDiverged(event_index, kind_a, kind_b) | PayloadDiverged(event_index, key, value_a, value_b)`). Pure.
- [ ] **AC-HELPER-3: `_compare_runs(diffs: Sequence[bytes], tapes: Sequence[Sequence[dict]]) -> CompareReport`** is the top-level sum-type-returning verdict producer; `CompareReport = AllRunsIdentical | DiffBytesDiverged | EventTapeDiverged | StateLeakDetected`. Pure; tested in isolation in `tests/unit/test_determinism_compare.py` with crafted inputs that exercise every variant.

### Group O — Event-count guard per iteration

- [ ] **AC-COUNT-1: Per-iteration event count is exact.** `assert len(event_log.recorded) == EXPECTED_EVENT_COUNT_PER_BRANCH[branch]` per iteration; `EXPECTED_EVENT_COUNT_PER_BRANCH: Final[dict[Literal["rag_hit", "rag_degraded", "rag_miss", "retry_bypass"], int]] = {...}` derived from S6-01/S6-02 hardened tape contracts (10 for happy-path; 10 for retry-bypass per S6-02 AC). Catches tier-reused-across-iterations accumulation.

### Group P — Marker registration + suite routing

- [ ] **AC-MARKER-1: `@pytest.mark.determinism`** is registered in `pyproject.toml § [tool.pytest.ini_options].markers` with the description `"Determinism-under-cassette-replay property tests; opt-in via -m determinism for non-default lanes (rag_degraded, rag_miss, retry_bypass)."`
- [ ] **AC-MARKER-2: Default-suite vs opt-in lanes.** The `rag_hit` branch test (≤ 30 s p95) runs in the default `make test` suite; `rag_degraded`, `rag_miss`, `retry_bypass` are marked `@pytest.mark.determinism` and run in CI but not in `make test-fast`. Captured in `Makefile`: `test-fast: ; pytest -q -m "not bench and not determinism"`.

### Group Q — Make-check + closing invariants

- [ ] **AC-CLOSE-1: `make check` green** — including all four cassette-replay branches, all fence tests, the Hypothesis property test, and the AST guards under Groups B, D, E, F, J.
- [ ] **AC-CLOSE-2: `make lint-imports` green** — no new contracts violated; the test files import only from approved packages (`pytest`, `pytest-recording`, `hypothesis`, `structlog`, `codegenie.*`, `blake3`, `tests._determinism.*`).
- [ ] **AC-CLOSE-3: ≥ 20 iterations is the FAIL-loud floor.** If `ITERATIONS < 20`, the test fails at module import with `RuntimeError("ITERATIONS must be ≥ 20; got {n}; goal is 50; truthful 20 beats fake 50 per Global Rule 12.")`. No silent acceptance of 10.

## Implementation outline

1. **New helper package** `tests/_determinism/`:
   - `nondet_fields.py` — `class NonDeterministicField(StrEnum)` (AC-ENUM-1).
   - `digest.py` — pure `_deterministic_digest`, `_canonical_json`, `_strip_nondet`, `_to_dict_recursive` (AC-DIGEST-*).
   - `compare.py` — sum types `CompareReport`, `EventTapeDiff`; pure `_first_divergence`, `_diff_two_tapes`, `_compare_runs` (AC-HELPER-*).
   - `key.py` — `DeterminismKey` Pydantic `frozen=True, extra="forbid"` (AC-TUPLE-*).
   - `module_state.py` — `_capture_module_state()` (AC-FRESH-3).
   - `recording_arch.py` — `_assert_recording_arch_compatible(branch)` (AC-PLATFORM-1).
2. **New test file** `tests/property/test_determinism_under_cassette_replay.py`:
   - `ITERATIONS: Final[int] = int(os.environ.get("CODEGENIE_DETERMINISM_ITERATIONS", "50"))`; module-import guard rejects values outside `{20, 25, 30, 40, 50}` (AC-PERF-1, AC-CLOSE-3).
   - Module-scope `pytestmark = [pytest.mark.platform_recorded]`.
   - `_freeze_nondet_sources` autouse fixture (AC-SEED-1).
   - `_verify_cassettes_lock` session-autouse fixture (AC-LOCK-2).
   - Parametrize over the four branches (`rag_hit`, `rag_degraded`, `rag_miss`, `retry_bypass`); `rag_degraded`/`rag_miss`/`retry_bypass` carry `pytest.mark.determinism` (AC-MARKER-2).
   - Per-iteration parametrize (AC-PARAM-1).
3. **Test body skeleton** (per branch, per iteration):
   ```python
   _assert_recording_arch_compatible(branch)
   key = _compute_determinism_key(advisory, repo_ctx, sel, store, embedder, cassette_path)
   tier = make_fallback_tier_for_fixtures(store=seeded_store_for(branch), embedder=fastembed_real)
   before_state = _capture_module_state()
   event_log = tier.event_log
   result = asyncio.run(tier.run(advisory, repo_ctx, sel, prior_attempts=prior_attempts_for(branch)))
   assert _capture_module_state() == before_state, "module-level state mutated across iteration"
   assert len(event_log.recorded) == EXPECTED_EVENT_COUNT_PER_BRANCH[branch]
   key_now = _compute_determinism_key(advisory, repo_ctx, sel, store, embedder, cassette_path)
   assert key_now == key, "constancy tuple drifted mid-test"
   return (result.transform.diff_bytes, [_strip_nondet(e.model_dump()) for e in event_log.recorded])
   ```
4. **Verdict via sum type**:
   ```python
   report: CompareReport = _compare_runs(diff_bytes_per_iter, event_tapes_per_iter)
   assert isinstance(report, AllRunsIdentical), report.format_diagnostic()
   ```
   `format_diagnostic()` returns a structured `unittest.TestCase.assertDictEqual`-style diff (NOT `pprint.pformat` — too lossy on big dicts; Consistency #8).
5. **`_strip_nondet`** consumes `NonDeterministicField` (the enum, not raw strings) and recurses into nested dicts via `_to_dict_recursive` (handles Pydantic, dataclasses, lists).
6. **Retry-bypass branch** mirrors the same structure with `prior_attempts=(attempt_summary_fix,)` (`Sequence` not `list` per S6-01 / S6-02 hardening) and `EXPECTED_EVENT_COUNT_PER_BRANCH["retry_bypass"]` from S6-02.
7. **Marker registration**: extend `pyproject.toml § [tool.pytest.ini_options].markers` with `determinism` and `platform_recorded` (AC-MARKER-1, AC-PLATFORM-2). `Makefile` adds `test-fast`.
8. **Cassettes** + `cassettes.lock`: create four cassette sub-directories under `tests/cassettes/anthropic/test_determinism/`; each ships `recording_arch.json` + an entry in `tests/cassettes/anthropic/cassettes.lock`. Recording is operator-touch via `make refresh-cassettes BRANCH=<branch>` (S3-06).

## TDD plan — red / green / refactor

### Red — write the failing tests first

**Test 1 — `tests/unit/test_determinism_compare.py` (pure-helper unit tests; verify intent not behavior — Rule 9):**

```python
# Exercises every CompareReport variant in isolation.
# AC-HELPER-1, AC-HELPER-2, AC-HELPER-3, AC-DIGEST-3.
from tests._determinism.compare import (
    AllRunsIdentical, DiffBytesDiverged, EventTapeDiverged, StateLeakDetected,
    _first_divergence, _diff_two_tapes, _compare_runs,
)

def test_first_divergence_none_when_all_equal():
    assert _first_divergence([b"x", b"x", b"x"]) is None

def test_first_divergence_returns_smallest_diverging_index():
    assert _first_divergence([b"x", b"x", b"y", b"x"]) == 2

def test_compare_runs_all_identical():
    assert isinstance(_compare_runs([b"x", b"x"], [[{"k": "A"}], [{"k": "A"}]]), AllRunsIdentical)

def test_compare_runs_diff_bytes_diverged_reports_offset():
    rpt = _compare_runs([b"abc", b"abd"], [[{"k": "A"}], [{"k": "A"}]])
    assert isinstance(rpt, DiffBytesDiverged)
    assert rpt.run_index == 1 and rpt.byte_offset == 2

def test_compare_runs_event_tape_kind_diverged():
    rpt = _compare_runs([b"x", b"x"], [[{"k": "A"}], [{"k": "B"}]])
    assert isinstance(rpt, EventTapeDiverged)
    assert rpt.event_index == 0 and rpt.kind_lhs == "A" and rpt.kind_rhs == "B"

def test_format_diagnostic_names_run_index_event_index_field():
    rpt = _compare_runs([b"x", b"x"], [[{"k": "A", "p": 1}], [{"k": "A", "p": 2}]])
    msg = rpt.format_diagnostic()
    # AC-CLOSE: actionable message — names every fact a human needs.
    assert "run 1" in msg and "event 0" in msg and "'p'" in msg and "1" in msg and "2" in msg
```

**Test 2 — `tests/property/test_determinism_under_cassette_replay.py` (the property, per-branch parametrize):**

```python
# AC-TUPLE, AC-ENUM, AC-DIGEST, AC-BRANCH-1..-5, AC-LOCK, AC-FRESH-*,
# AC-PLATFORM, AC-PARAM, AC-COUNT, AC-PERF, AC-CLOSE.
import asyncio
import os
from typing import Final, Literal

import pytest
import structlog
from blake3 import blake3

from codegenie.plugins.events import _INTERNAL_CLASSES  # noqa: F401
from tests._determinism.compare import AllRunsIdentical, _compare_runs
from tests._determinism.digest import _deterministic_digest, _strip_nondet
from tests._determinism.key import DeterminismKey
from tests._determinism.module_state import _capture_module_state
from tests._determinism.nondet_fields import NonDeterministicField  # AC-ENUM-1
from tests._determinism.recording_arch import _assert_recording_arch_compatible
from tests.fixtures.fallback_tier_callable import make_fallback_tier_for_fixtures

_ALLOWED_ITERATIONS: Final[frozenset[int]] = frozenset({20, 25, 30, 40, 50})
_RAW = int(os.environ.get("CODEGENIE_DETERMINISM_ITERATIONS", "50"))
if _RAW not in _ALLOWED_ITERATIONS:
    raise RuntimeError(
        f"CODEGENIE_DETERMINISM_ITERATIONS={_RAW} not in {sorted(_ALLOWED_ITERATIONS)}; "
        "ITERATIONS must be ≥ 20; goal is 50; truthful 20 beats fake 50 per Global Rule 12."
    )
ITERATIONS: Final[int] = _RAW

EXPECTED_EVENT_COUNT_PER_BRANCH: Final[dict[str, int]] = {
    "rag_hit": 10,          # S6-01 happy-path tape
    "rag_degraded": 10,     # same shape; RagDegraded substitutes for RagHit
    "rag_miss": 10,         # same shape; RagMiss substitutes
    "retry_bypass": 10,     # S6-02 retry-path tape
}

pytestmark = [pytest.mark.platform_recorded]

_LOG = structlog.get_logger("phase4.determinism")


def _compute_determinism_key(
    advisory, repo_ctx, sel, store, embedder, cassette_path,
) -> DeterminismKey:
    return DeterminismKey(
        repo_snapshot_sha=repo_ctx.snapshot_sha,
        cve_record_digest=advisory.record_digest,
        plugin_version=sel.plugin_version,
        recipe_version=sel.recipe_version,
        vuln_index_digest=advisory.vuln_index_digest,
        store_digest=store.digest(),
        embedding_model_digest=embedder.model_digest(),
        cassette_blake3=blake3(cassette_path.read_bytes()).hexdigest(),
    )


@pytest.mark.parametrize(
    "branch,marks",
    [
        ("rag_hit", ()),
        pytest.param("rag_degraded", marks=pytest.mark.determinism),
        pytest.param("rag_miss", marks=pytest.mark.determinism),
        pytest.param("retry_bypass", marks=pytest.mark.determinism),
    ],
)
def test_determinism_under_cassette_replay(
    branch: Literal["rag_hit", "rag_degraded", "rag_miss", "retry_bypass"],
    marks,
    advisory_fix, repo_ctx_fix, recipe_selection_fix, attempt_summary_fix,
    seeded_rag_store_for_branch, fastembed_real, cassette_path_for_branch,
    request,
):
    """AC-BRANCH-*: the determinism property must hold across all four control-flow branches.

    Why this matters (Rule 9 — intent not behavior): a regression in any of these branches
    silently invalidates Phase 6.5 bench replay AND Phase 7 E2E exit criterion #2
    ('replay-lands-RAG, lower cost'). The test does not just check 'outputs match';
    it checks that the *eight-leg constancy tuple* drives the equivalence — a regression
    that breaks one leg (e.g., store_digest drifts mid-test) is reported with the
    diverging leg named, not as a generic 'outputs differ.'"""
    _assert_recording_arch_compatible(branch)
    cassette_path = cassette_path_for_branch(branch)
    store = seeded_rag_store_for_branch(branch)
    prior_attempts = (attempt_summary_fix,) if branch == "retry_bypass" else ()

    key_initial = _compute_determinism_key(
        advisory_fix, repo_ctx_fix, recipe_selection_fix, store, fastembed_real, cassette_path,
    )
    _LOG.info("determinism.key.computed", branch=branch, key=key_initial.model_dump())

    before_state = _capture_module_state()
    diffs: list[bytes] = []
    tapes: list[list[dict]] = []
    for iteration in range(ITERATIONS):
        tier = make_fallback_tier_for_fixtures(store=store, embedder=fastembed_real)
        event_log = tier.event_log
        result = asyncio.run(tier.run(
            advisory_fix, repo_ctx_fix, recipe_selection_fix,
            prior_attempts=prior_attempts,
        ))
        # AC-COUNT-1: event count is exact per branch.
        assert len(event_log.recorded) == EXPECTED_EVENT_COUNT_PER_BRANCH[branch], (
            f"iteration {iteration} branch={branch}: emitted {len(event_log.recorded)} events; "
            f"expected {EXPECTED_EVENT_COUNT_PER_BRANCH[branch]}"
        )
        # AC-TUPLE-2: constancy tuple stays put.
        key_now = _compute_determinism_key(
            advisory_fix, repo_ctx_fix, recipe_selection_fix, store, fastembed_real, cassette_path,
        )
        assert key_now == key_initial, (
            f"iteration {iteration}: constancy tuple drifted: {key_initial} -> {key_now}"
        )
        diffs.append(result.transform.diff_bytes)
        tapes.append([_strip_nondet(e.model_dump()) for e in event_log.recorded])

    # AC-FRESH-1: every Transform is a distinct object (catches memoized-cheat).
    assert len({id(d) for d in diffs}) == ITERATIONS, "results memoized — same object across iterations"

    # AC-FRESH-3: module state did not mutate across the loop.
    assert _capture_module_state() == before_state, (
        f"module-level state mutated across {ITERATIONS} iterations under branch={branch}"
    )

    # AC-HELPER-3 + AC-BRANCH-5: pure sum-type verdict.
    report = _compare_runs(diffs, tapes)
    assert isinstance(report, AllRunsIdentical), report.format_diagnostic()
```

**Test 3 — `tests/property/test_determinism_verdict_shape.py` (AC-BRANCH-5; structural assertion):**

```python
# The verdict shape is branch-invariant — determinism is structural.
@pytest.mark.parametrize("branch", ["rag_hit", "rag_degraded", "rag_miss", "retry_bypass"])
def test_verdict_shape_is_all_runs_identical(...): ...  # mirrors Test 2 but returns/inspects only the report type
```

**Test 4 — `tests/property/test_determinism_under_cassette_replay_hypothesis.py` (AC-HYP-1):**

```python
from hypothesis import given, settings, strategies as st, HealthCheck

@settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(repo_ctx_variation=_st_shuffled_dep_order())
def test_determinism_robust_to_input_order(repo_ctx_variation, ...):
    """AC-HYP-1: shuffling dep-list order within one cve_id must not change the verdict.
    Catches 'dep-list iteration leaks into prompt body' (the canonical source of
    flake-under-replay)."""
    # 10 inner iterations per Hypothesis-drawn example (cassette-bounded).
    ...
```

**Test 5 — `tests/property/test_determinism_identity_invariants.py` (AC-IDENT-1, AC-IDENT-2):**

```python
def test_token_id_identity_across_precharge_reconcile(monkeypatch, ...):
    # Monkeypatch uuid.uuid4 to a deterministic counter; remove BUDGET_TOKEN_ID
    # from NonDeterministicField in this sub-test only.
    ...
    assert events_by_kind["BudgetPrecharged"].token_id == events_by_kind["BudgetReconciled"].token_id

def test_prompt_digest_identity_across_built_invoked(...):
    # No monkeypatch — prompt_digest_blake3 is derived, not generated.
    ...
    assert events_by_kind["PromptBuilt"].prompt_digest_blake3 == events_by_kind["LeafInvoked"].prompt_digest_blake3
```

**Test 6 — `tests/fence/test_determinism_allowlist_exhaustive.py` (AC-ENUM-2):**

```python
def test_every_uuid_field_is_in_nondet_enum():
    from codegenie.plugins.events import _INTERNAL_CLASSES
    from tests._determinism.nondet_fields import NonDeterministicField
    nondet_members = {m.value for m in NonDeterministicField}
    for cls in _INTERNAL_CLASSES:
        for fname, finfo in cls.model_fields.items():
            if _is_uuid_or_datetime_field(finfo) and fname not in nondet_members:
                pytest.fail(
                    f"{cls.__name__}.{fname} is uuid4/datetime-shaped but NOT in "
                    f"NonDeterministicField — add it or refactor to a deterministic field."
                )
```

**Test 7 — `tests/fence/test_no_set_iter_in_fallback.py` (AC-AST-1):**

```python
def test_no_unsorted_dict_iter_in_fallback_or_rag():
    for module_path in _walk_modules(["src/codegenie/fallback", "src/codegenie/rag"]):
        tree = ast.parse(module_path.read_text())
        for node in ast.walk(tree):
            if _is_unsorted_dict_iter_at_module_scope(node):
                pytest.fail(f"{module_path}:{node.lineno}: dict.keys()/values()/items() not wrapped in sorted(...)")
```

**Test 8 — `tests/fence/test_tier_constructed_per_iteration.py` (AC-FRESH-2):**

```python
def test_tier_factory_call_inside_loop():
    src = Path("tests/property/test_determinism_under_cassette_replay.py").read_text()
    tree = ast.parse(src)
    # Walk every For node; assert at least one call to make_fallback_tier_for_fixtures
    # is *inside* its body (not at module scope or before-loop).
    ...
```

**Test 9 — `tests/fence/test_determinism_helpers_pure.py` (AC-DIGEST-2):**

```python
def test_determinism_helpers_import_no_clocks():
    for module_path in _walk_modules(["tests/_determinism/"]):
        tree = ast.parse(module_path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imported = _imported_names(node)
                forbidden = {"time", "random", "secrets"}
                assert not (imported & forbidden), (
                    f"{module_path}: forbidden non-deterministic import {imported & forbidden}"
                )
```

### Green — make it pass

The first time the test runs, it WILL surface a real non-determinism (Rule 12 — fail loud). Likely sources, in priority order:
1. **`dict` iteration order leaking into prompt body** — `PromptBuilder` serialises with `sorted(...)` on every dict before `json.dumps`. Fix the source.
2. **`set` iteration leaking into fence-segment order** — wrap with `sorted(...)`.
3. **`time.time()` call leaking into prompt** — replace with a deterministic field; move clock-derived values to the `NonDeterministicField` allowlist *only* if they're emitted as audit metadata, never if they cross into prompt text.
4. **A `uuid4` other than the four allowlisted fields** — surface and refactor to deterministic input or add to `NonDeterministicField` with an ADR amendment justifying it.
5. **`asyncio.gather(*coros)` with non-deterministic completion order** — sort results by stable key.

**Do not weaken the test to make it pass** (Rule 12, Rule 9). Do not add fields to `NonDeterministicField` without an ADR amendment.

### Refactor — clean up

- The `tests/_determinism/` package is small and pure; keep it that way (`tests/fence/test_determinism_helpers_pure.py` is the structural defense).
- Every `NonDeterministicField` member needs a docstring explaining *why* it's allowed to differ (clock vs uuid vs cross-process-id).
- If a real source of non-determinism is found, fix it; do not add it to the allowlist.
- **Do not** prematurely abstract the per-event `nondet_fields` declaration onto the event class — that's the rule-of-three deferred refactor in Notes-for-implementer. Three test-side test files (this story) is not enough signal; the fourth deterministic-projection consumer (Phase 5 sandbox determinism? Phase 9 Temporal replay?) triggers the kernel extract.

## Files to touch

| Path | Why |
|---|---|
| `tests/_determinism/__init__.py` | New — package marker for pure determinism helpers. |
| `tests/_determinism/nondet_fields.py` | New — `class NonDeterministicField(StrEnum)` (AC-ENUM-1). |
| `tests/_determinism/digest.py` | New — pure `_deterministic_digest`, `_strip_nondet`, `_canonical_json`, `_to_dict_recursive` (AC-DIGEST-*). |
| `tests/_determinism/compare.py` | New — `CompareReport` sum type + `_first_divergence`, `_diff_two_tapes`, `_compare_runs` (AC-HELPER-*). |
| `tests/_determinism/key.py` | New — `DeterminismKey` Pydantic frozen-extra-forbid model (AC-TUPLE-*). |
| `tests/_determinism/module_state.py` | New — `_capture_module_state` (AC-FRESH-3). |
| `tests/_determinism/recording_arch.py` | New — `_assert_recording_arch_compatible` (AC-PLATFORM-1). |
| `tests/property/test_determinism_under_cassette_replay.py` | New — the per-branch property test. |
| `tests/property/test_determinism_under_cassette_replay_hypothesis.py` | New — Hypothesis property over input-shape variation (AC-HYP-1). |
| `tests/property/test_determinism_verdict_shape.py` | New — branch-invariant verdict shape (AC-BRANCH-5). |
| `tests/property/test_determinism_identity_invariants.py` | New — cross-event payload identity (AC-IDENT-*). |
| `tests/unit/test_determinism_compare.py` | New — pure unit tests of every `CompareReport` variant. |
| `tests/unit/test_determinism_key_shape.py` | New — `DeterminismKey` cardinality lock (AC-TUPLE-3). |
| `tests/fence/test_determinism_allowlist_exhaustive.py` | New — walks `_INTERNAL_CLASSES` for uuid/datetime fields (AC-ENUM-2). |
| `tests/fence/test_no_raw_str_nondet_allowlist.py` | New — bans `Final[tuple[str, ...]]` named `*NONDET*` outside `tests/_determinism/` (AC-ENUM-3). |
| `tests/fence/test_determinism_helpers_pure.py` | New — AST purity of `tests/_determinism/` (AC-DIGEST-2). |
| `tests/fence/test_no_set_iter_in_fallback.py` | New — AST guard against unsorted dict/set iter in `fallback/` + `rag/` (AC-AST-1). |
| `tests/fence/test_tier_constructed_per_iteration.py` | New — AST guard that factory call lives inside the loop body (AC-FRESH-2). |
| `tests/cassettes/anthropic/test_determinism/{rag_hit,rag_degraded,rag_miss,retry_bypass}/cassette.yaml` | New — four cassettes; record via `make refresh-cassettes BRANCH=<branch>`. |
| `tests/cassettes/anthropic/test_determinism/{rag_hit,rag_degraded,rag_miss,retry_bypass}/recording_arch.json` | New — sidecar pinning recording arch + embedder model digest (AC-PLATFORM-1). |
| `tests/cassettes/anthropic/cassettes.lock` | Modify — add four new BLAKE3 entries (AC-LOCK-1). |
| `pyproject.toml § [tool.pytest.ini_options].markers` | Modify — register `determinism` and `platform_recorded` markers (AC-MARKER-1, AC-PLATFORM-2). |
| `Makefile` | Modify — add `test-fast` target excluding `-m "bench or determinism"` (AC-MARKER-2). |
| `src/codegenie/fallback/tier.py` (only if real non-determinism is uncovered) | Fix the source; do not weaken the test. |
| `src/codegenie/rag/retriever.py` (only if real non-determinism is uncovered) | Same — sort iteration orders. |
| `src/codegenie/fallback/fence/prompt_builder.py` (only if real non-determinism is uncovered) | Same — `sorted(...)` over dicts before `json.dumps`. |

## Out of scope

- The full E2E roadmap-exit tests — **S7-06**, **S7-07** read this property as a precondition.
- Phase 6.5 bench replay determinism — that's a higher-order assertion that depends on this property holding.
- Cross-architecture float-drift handling for the *embedder* path — already mitigated by the two-threshold band (ADR-04-0008); the determinism test gates on `_assert_recording_arch_compatible` and SKIPS on arch mismatch.
- The `make refresh-cassettes` workflow itself — S3-06.
- Per-event `nondet_fields: ClassVar[frozenset[str]]` migration — deferred to the next deterministic-projection consumer (rule-of-three not yet reached; see Notes-for-implementer).
- The CI matrix configuration that routes `pytest.mark.platform_recorded` to the matching runner — operator concern; the marker registration in this story is enough.

## Notes for the implementer

- **Fail loud is the contract.** If the property fails the first time you run it, that's the test working — there's real non-determinism somewhere. Find it. Do not add fields to `NonDeterministicField` to make the test pass (Global Rule 12). Adding a member to `NonDeterministicField` requires an ADR amendment justifying it.
- **Determinism key tuple — surface a conflict between docs (Global Rule 7).** Phase-arch-design §Idempotence (line 827) names a *four*-tuple as the constancy contract. Final-design.md line 37 names an *eight*-tuple. This story adopts the **eight-tuple** as the source-of-truth per the validator's Consistency-wins-over-Coverage priority resolution. If, at implementation time, you find that some of the eight legs are derivable from each other (e.g., `cve_record_digest` is a deterministic function of `repo_snapshot_sha` for a given CVE-in-repo pair), surface that to me — do not silently collapse the tuple. The cardinality lock in AC-TUPLE-3 will fail if you do.
- **`RecipeApplication` shape (carry-forward from S6-01 validation).** S6-01 surfaced a Global-Rule-7 conflict: Phase 4 arch names `RecipeApplication.Applied | RecipeApplication.Refused(reason=...)`; Phase 5 stories speak of `RecipeApplication.diff: bytes` as a single attribute. This story assumes the discriminated-union shape and accesses `result.transform.diff_bytes`. If Phase 5's already-merged type is the single-attribute shape, surface and amend BEFORE writing the test. Do not blend.
- **50 iterations is the goal, ≥ 20 the floor.** The `ITERATIONS` value is closed-set `{20, 25, 30, 40, 50}` — no arbitrary value. Anything below 20 fails at module import per AC-CLOSE-3.
- **The retry-bypass + RagDegraded + RagMiss branches matter.** A regression that only affects one branch would be invisible to E2E #1 (S7-06) which exercises one path. Four cassettes is the cost of correctness.
- **`asyncio.run(...)` per iteration** is intentional — it surfaces leaked module-level state. AC-FRESH-3 makes the leak detection structural via `_capture_module_state`, not merely an artifact of fresh event loops.
- **Cassette recording** (`make refresh-cassettes BRANCH=<branch>` from S3-06) is operator-touch — coordinate with the cassette-steward (CODEOWNERS entry from S3-06) before re-recording. The cassettes for the determinism test must NOT be re-recorded casually; they're the immutable substrate for the property. Each re-record must update `cassettes.lock` (AC-LOCK-1) in the same commit.
- **Diagnostic quality matters.** `assert a == b` on big dicts truncates output. `pprint.pformat` is lossy (Consistency #8). Use `unittest.TestCase.assertDictEqual`-style structured diff via `CompareReport.format_diagnostic()`. The sum type makes the failure machine-readable for future debug tooling.
- **Pure helpers are the contract.** `tests/_determinism/` is functional-core: no I/O, no clocks, no env reads. `tests/fence/test_determinism_helpers_pure.py` is the structural defense — adding `import time` to those modules fails CI.
- **Rule-of-three deferred refactor (design opportunity).** With ~10 event kinds, the per-event "what's non-deterministic" knowledge belongs *on the event class* as a `nondet_fields: ClassVar[frozenset[str]]`, not in a test-side `NonDeterministicField` enum. This is the **Specification pattern** applied to determinism. **Do not extract now** — this is the first deterministic-projection consumer; premature abstraction (Rule 2). When the second consumer lands (likely Phase 9 Temporal replay test or Phase 6.5 bench replay), revisit. AC-LATER-1 in the validation report records the deferred refactor.
- This property test makes the Phase-6.5 bench replay and Phase-7 E2E tests *trustworthy*. A weak version of this test invalidates the downstream claims — and Phase 6.5 ships pinned to `cassettes.lock` (ADR-04-0014 §Consequences) which this test enforces.
- **`pytest-recording` configuration.** The `record_mode="none"` posture is set at the project level (S3-04 already lands cassette infra); per-test `@pytest.mark.vcr` decorators are not needed if conftest configures it globally. Verify S3-04's conftest before this story executes; if S3-04 did not set it, add `@pytest.mark.vcr(record_mode="none")` per test branch.
