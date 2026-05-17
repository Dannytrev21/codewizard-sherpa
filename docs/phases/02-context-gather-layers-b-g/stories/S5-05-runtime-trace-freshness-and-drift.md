# Story S5-05 — `runtime_trace` freshness-check registration + `image_digest_drift` adversarial

**Step:** Step 5 — Ship Layer C (runtime + container) probes
**Status:** Ready (hardened 2026-05-17)
**Effort:** S
**Depends on:** S5-02 (`RuntimeTraceProbe` writes `<raw_dir>/runtime_trace.json` containing `built_image_digest`, `last_traced_image_digest`, `last_traced_at`), S1-02 (`@register_index_freshness_check` decorator-registry — landed at `codegenie.indices.registry`), S1-01 (`IndexFreshness`, `Fresh`, `Stale`, `DigestMismatch`, `IndexerError`), S4-01 (`IndexHealthProbe` loops the freshness registry via `default_freshness_registry.dispatch_all`; `read_raw_slices(raw_dir(repo.root))` is the kernel that hydrates the per-name slice dict), S1-05 (`IndexName` newtype)
**ADRs honored:** 02-ADR-0004 (image-digest as `declared_inputs` special token — the adversarial proves cache invalidation), 02-ADR-0006 (sum-type freshness location), 02-ADR-0003 (`IndexHealthProbe` `runs_last=True` — depends on this freshness function executing at the right moment)

## Validation notes (2026-05-17, phase-story-validator v1 — verdict HARDENED)

The original draft was structurally sound (registry-side Open/Closed seam, freshness function in `runtime_trace.py` not `index_health.py`, four-part `Stale(DigestMismatch(...))` assertion discipline, load-bearing adversarial test path) but encoded six load-bearing contract drifts against code that already exists on disk:

1. **Function signature contradiction (Consistency block).** Draft prescribed `_check_runtime_trace_freshness(slice_: RuntimeTraceSlice, head: GitSha) -> IndexFreshness`. The actual registry contract at [`src/codegenie/indices/registry.py:67`](../../../../src/codegenie/indices/registry.py) is `FreshnessCheck = Callable[[dict[str, object], str], "IndexFreshness"]`; the registered `scip_freshness` precedent at [`src/codegenie/probes/layer_b/index_health.py:144`](../../../../src/codegenie/probes/layer_b/index_health.py) takes `dict[str, object]` and a plain `str` head. There is no `RuntimeTraceSlice` model and no `GitSha` newtype in the codebase (the existing newtypes are `IndexName`, `IndexId`, `SkillId`, `TaskClassId`, `ProbeId`, `Language`, `ConventionId`). A typed-Pydantic-model freshness function would not register and the AC was unachievable. Rewritten to `_check_runtime_trace_freshness(slice_: dict[str, object], head: str) -> IndexFreshness` mirroring `scip_freshness` exactly.
2. **Error class wrong name + wrong constructor shape (Consistency block).** Draft prescribed `IndexFreshnessRegistryError(reason="duplicate_name")`. The actual class is `FreshnessRegistryError` (at [`src/codegenie/errors.py:155`](../../../../src/codegenie/errors.py)); its message is a positional string `f"duplicate index_name {name!r}: {prior} and {origin}"` — no `reason=` kwarg. Existing duplicate-registration test at [`tests/unit/indices/test_freshness_registry.py:78`](../../../../tests/unit/indices/test_freshness_registry.py) asserts the message-string shape (offending name + both call-site qualnames). Story rewritten to match.
3. **Slice-field name `index_freshness` wrong (Consistency block).** Draft AC-6 Scenario B asserted `B2 slice's index_freshness["runtime_trace"]`. The actual `IndexHealthProbe.run` emits `schema_slice={"index_health": results}` where `results[str(name)] = {"freshness": <model_dump>, "confidence": ..., "current_commit": ..., "last_indexed_at": ...}` ([index_health.py:397-404](../../../../src/codegenie/probes/layer_b/index_health.py)). Story rewritten to `out.schema_slice["index_health"]["runtime_trace"]["freshness"]["kind"]` etc.
4. **Upstream-unavailable signal wrong (Consistency block).** Draft branched on `slice_.confidence == "unavailable"`. There is no `confidence` field on the runtime_trace slice; the runtime_trace slice carries `trace_coverage_confidence: Literal["high","medium","low","unavailable"]` (S5-02 AC line 86 + AC line 87) but the **envelope** `confidence` is `Literal["high","medium","low"]` per S5-02's contract-preservation pin (AC line 84). More importantly, the empty-dict sentinel established by `scip_freshness` (line 164) is the registry's canonical upstream-unavailable path — `default_freshness_registry.dispatch_all` passes `slices.get(name, {})` for any name without a slice file. Story rewritten to use the empty-dict sentinel as the primary upstream-unavailable signal, with `trace_coverage_confidence == "unavailable"` as a secondary slice-driven signal.
5. **`Fresh.indexed_at` derivation hand-wave (Consistency block).** Draft said "Fresh(indexed_at=<some-sentinel-or-the-slice-timestamp>)". `Fresh.indexed_at: datetime` requires a real `datetime`; the function is pure (no clock read); there is no slice field today that carries a timestamp. Resolved by pinning **a new S5-02 slice field, `last_traced_at: str` (ISO-8601 UTC)** — added as an explicit upstream dependency in this story's "Notes for the implementer" with the small-AC-patch surface; the freshness function parses it via `_dt.datetime.fromisoformat`, with malformed-string → `Stale(IndexerError("runtime_trace_slice_malformed"))` mirroring `scip_freshness` lines 200–203.
6. **`_check` not added to `__all__` (Consistency harden).** Draft said "leave it module-private". The `scip_freshness` precedent IS exported in `__all__` ([index_health.py:97](../../../../src/codegenie/probes/layer_b/index_health.py)). Story rewritten to require the same export so unit tests can import the function symbolically.

Plus five harden-tier improvements: replaced source-grep purity check with AST-walk audit (mirrors S5-04 T4/T5 + S5-03 ASTAudit); added a Hypothesis purity / totality property test; added a mutation-resistance suite; added `Final[str]` constants for every `IndexerError.message` value; added an argument-order canary test (registry calls positional `(slice, head)` — swapping silently corrupts every freshness check; this is a structural defense). One design-pattern surfaced in Notes: this is the **rule-of-three threshold** for `@register_index_freshness_check` (scip + runtime_trace + S6-08's three rule-pack-versioned checks). Per Rule 2 / S5-04 D2 precedent, NO kernel extraction in this story — the trigger is recorded for S6-08 authors.

Eighteen in-place edits applied. Full audit trail in [`_validation/S5-05-runtime-trace-freshness-and-drift.md`](_validation/S5-05-runtime-trace-freshness-and-drift.md).

## Context

S5-02's `RuntimeTraceProbe` writes `<raw_dir>/runtime_trace.json` with three fields B2 (`IndexHealthProbe`, S4-01) reads to decide freshness:
- `built_image_digest: str | None` — the digest of the image just built (or the cached one). `None` when the resolver was unbound, returned None, or raised (S5-02 AC line 81–83).
- `last_traced_image_digest: str | None` — the digest of the image actually traced (which equals `built_image_digest` on a clean run, but **differs** when the on-disk slice from a prior gather is stale relative to a freshly-resolved current digest — the *drift* case).
- `last_traced_at: str` — ISO-8601 UTC timestamp of when the trace was recorded (this field is added by S5-02; pinned as a small upstream-dependency AC in Notes-for-implementer below — it does not exist in S5-02's hardened slice today and must be added before this story executes).

When `last_traced_image_digest != built_image_digest`, the runtime-trace index is **stale** — the trace evidence reflects an older image than the one that's currently built. `IndexHealthProbe` must emit `IndexFreshness.Stale(reason=DigestMismatch(expected=built, actual=last_traced))`, not a silent `Fresh`. The mechanism is S1-02's `@register_index_freshness_check("runtime_trace")` registry — `IndexHealthProbe` (S4-01) loops the registry via `default_freshness_registry.dispatch_all`; freshness functions land alongside their probe (Open/Closed at the file boundary — phase-arch-design.md §"Component design" #1 + §"Gap 3"; existing `scip_freshness` precedent at `index_health.py:144`).

The registry's contract is unforgiving and structural: the function takes `slice_: dict[str, object], head: str` (positionally) and returns `IndexFreshness` (a discriminated union of `Fresh | Stale`). The dispatch passes `slices.get(name, {})` so a missing slice file lands as an **empty dict** — the canonical "upstream unavailable" sentinel (mirrors scip_freshness line 164).

The load-bearing adversarial: `tests/adv/phase02/test_image_digest_drift.py` proves three things without invoking real `docker`:
1. Resolving two distinct digests produces two distinct **cache keys** via the `image-digest:<resolved>` declared-input token (02-ADR-0004 / S5-02 step 0 wires `cache/keys.py::_resolve_special_token`). Subject-under-test: cache-key derivation, not `_execute_scenario` invocation count.
2. Constructed `runtime_trace.json` slices with `built ≠ last_traced` cause `IndexHealthProbe` to emit `Stale(DigestMismatch(expected=built, actual=last_traced))` in its `schema_slice["index_health"]["runtime_trace"]["freshness"]`.
3. Slices with `built == last_traced` emit `Fresh(indexed_at=...)` in the same field (Rule 12 — fail loud; negative-case discipline).

## References

- [phase-arch-design.md §"Component design" #1 (`IndexHealthProbe`)](../phase-arch-design.md) — registry-dispatched freshness checks.
- [phase-arch-design.md §"Component design" #6 (`RuntimeTraceProbe`)](../phase-arch-design.md) — `last_traced_image_digest` and `built_image_digest` slice fields.
- [phase-arch-design.md §"Edge cases" rows 5, 6, 14](../phase-arch-design.md) — docker-build failure, macOS strace, image-digest resolver returns None.
- [phase-arch-design.md §"Testing strategy" — `test_image_digest_drift.py`](../phase-arch-design.md).
- [02-ADR-0004](../ADRs/0004-image-digest-as-declared-input-token.md) §Consequences — `tests/adv/phase02/test_image_digest_drift.py` (load-bearing adversarial) is named here.
- [02-ADR-0006](../ADRs/0006-index-freshness-sum-type-location.md) — `IndexFreshness` lives at `codegenie.indices.freshness`.
- [High-level-impl.md §"Step 5"](../High-level-impl.md) — registry entry for `@register_index_freshness_check("runtime_trace")` in `runtime_trace.py`.
- [final-design.md §"Adversarial corpus"](../final-design.md) — `test_image_digest_drift.py` listed alongside `test_stale_scip_fixture.py` as load-bearing.
- [`src/codegenie/indices/registry.py`](../../../../src/codegenie/indices/registry.py) — `FreshnessCheck` signature contract.
- [`src/codegenie/probes/layer_b/index_health.py:143-204`](../../../../src/codegenie/probes/layer_b/index_health.py) — `scip_freshness` precedent (signature, branch shape, malformed-slice handling, `IndexerError.message` discipline).
- [`tests/unit/indices/test_freshness_registry.py:78-106`](../../../../tests/unit/indices/test_freshness_registry.py) — existing duplicate-registration test shape.

## Goal

Register `@register_index_freshness_check(IndexName("runtime_trace"))` in `src/codegenie/probes/layer_c/runtime_trace.py` — a **pure** function `_check_runtime_trace_freshness(slice_: dict[str, object], head: str) -> IndexFreshness` that returns `Stale(DigestMismatch(...))` when `last_traced_image_digest != built_image_digest` and `Fresh(indexed_at=...)` (parsed from the slice's `last_traced_at`) otherwise. Land `tests/adv/phase02/test_image_digest_drift.py` — the load-bearing adversarial proving (a) image-digest mutation produces two distinct cache keys via the declared-input special token and (b) B2 surfaces the drift through `schema_slice["index_health"]["runtime_trace"]`.

## Acceptance criteria

- [ ] **AC-1 (function placement + decorator + signature).** `src/codegenie/probes/layer_c/runtime_trace.py` (the module from S5-02) gains a new top-level function `_check_runtime_trace_freshness(slice_: dict[str, object], head: str) -> IndexFreshness`, decorated with `@register_index_freshness_check(IndexName("runtime_trace"))`. The signature is verbatim — `dict[str, object]` for the slice, plain `str` for the head, NOT a typed `RuntimeTraceSlice` model and NOT a `GitSha` newtype (neither exists). The function is added to `runtime_trace.py`'s `__all__` (mirrors `scip_freshness` in [`index_health.py:97`](../../../../src/codegenie/probes/layer_b/index_health.py)) so unit tests can `from codegenie.probes.layer_c.runtime_trace import _check_runtime_trace_freshness` symbolically. The `head` parameter is unused (freshness signal is digest-based, not commit-based — the registry contract is uniform `(slice, head)` for all freshness checks); document the no-op in a one-line docstring.

- [ ] **AC-2 (branch table — six cases, total over the input domain).** The function body is total: every input produces exactly one `IndexFreshness` value; the function never raises (matches `scip_freshness`'s "never raises" property). Branches, in order:

  | # | Condition | Result |
  |---|---|---|
  | a | `slice_ == {}` (registry sentinel: dispatch passed `slices.get(name, {})` because `runtime_trace.json` was absent on disk) | `Stale(reason=IndexerError(message=_MSG_UPSTREAM_UNAVAILABLE))` where `_MSG_UPSTREAM_UNAVAILABLE: Final[str] = "upstream_runtime_trace_unavailable"` |
  | b | `slice_.get("trace_coverage_confidence") == "unavailable"` (S5-02's tetra-state surfaces when the probe ran but produced no usable trace — build failed, resolver returned None, macOS, etc.) | Same as (a) — `Stale(reason=IndexerError(message=_MSG_UPSTREAM_UNAVAILABLE))`. The sentinel string is shared so a downstream renderer collapses both upstream-degraded paths identically. |
  | c | Any required field missing or wrong-typed (`built_image_digest` not `str | None`; `last_traced_image_digest` not `str | None`; `last_traced_at` not `str`) | `Stale(reason=IndexerError(message=_MSG_SLICE_MALFORMED))` where `_MSG_SLICE_MALFORMED: Final[str] = "runtime_trace_slice_malformed"`. Mirrors `scip_freshness` lines 168-184; isinstance-checks with `bool`-discriminator on the int paths if any are added later. |
  | d | `built_image_digest is None` (resolver was unbound / returned None / raised — S5-02 records this state on disk) | `Stale(reason=IndexerError(message=_MSG_NO_BUILT_IMAGE))` where `_MSG_NO_BUILT_IMAGE: Final[str] = "no_built_image"` |
  | e | `last_traced_image_digest is None` (trace did not complete — e.g., docker build failed) | `Stale(reason=IndexerError(message=_MSG_NO_TRACE_RECORDED))` where `_MSG_NO_TRACE_RECORDED: Final[str] = "no_trace_recorded"` |
  | f | `last_traced_image_digest != built_image_digest` (the drift case) | `Stale(reason=DigestMismatch(expected=built_image_digest, actual=last_traced_image_digest))`. **The argument order is load-bearing**: `expected` = currently-built; `actual` = what-was-traced. A test asserts the swap is wrong. |
  | g | Else (digests match) | `Fresh(indexed_at=parsed_last_traced_at)` where `parsed_last_traced_at = datetime.fromisoformat(slice_["last_traced_at"])` inside a `try / except ValueError → Stale(reason=IndexerError(_MSG_SLICE_MALFORMED))` (mirrors `scip_freshness` lines 200-203). The parsed datetime carries its own tzinfo per S5-02's UTC discipline. |

- [ ] **AC-3 (Final[str] message constants, module-scope).** All four message strings appear as `Final[str]` module-level constants — `_MSG_UPSTREAM_UNAVAILABLE`, `_MSG_NO_BUILT_IMAGE`, `_MSG_NO_TRACE_RECORDED`, `_MSG_SLICE_MALFORMED`. No string literal is duplicated between the function body and the test file (the test imports the constants). Mirrors the `_WARNING_IDS`/`_SCIP_REQUIRED_KEYS` `Final` discipline in `index_health.py`. A test asserts `inspect.getmembers` reports each as `Final[str]`-annotated.

- [ ] **AC-4 (purity — AST-walk audit, NOT source-grep).** `tests/unit/probes/layer_c/test_runtime_trace_freshness_purity.py` AST-walks the `_check_runtime_trace_freshness` function's body and asserts NO `ast.Name` or `ast.Attribute` references `datetime.now`, `datetime.datetime.now`, `datetime.utcnow`, `time.time`, `time.monotonic`, `os.path.getmtime`, `os.stat`, `Path.stat`, `pathlib.Path.stat`, or any subprocess/asyncio call. Mirrors the AST-audit pattern in S5-04 T4/T5 / S5-03 ASTAudit. **Source-grep is bypassable via string concatenation; AST-walk is not.** The walker also asserts the function has no `await` and no `for` loop that iterates a fresh-resolution side-effecting iterator (the body is straight-line `if`/`elif`/`return`).

- [ ] **AC-5 (registry membership + retrieval).** After `runtime_trace.py` is imported, `default_freshness_registry.registered_names()` contains `IndexName("runtime_trace")`. A test imports the module then asserts `default_freshness_registry._checks[IndexName("runtime_trace")] is _check_runtime_trace_freshness` (identity, not equality — the registry stores the function object unchanged, mirroring `scip_freshness`'s identity at `index_health.py:143-144`). Uses the same `clean_freshness_registry` snapshot+restore fixture pattern that `test_index_health_probe.py` uses ([lines 74-87](../../../../tests/unit/probes/layer_b/test_index_health_probe.py)).

- [ ] **AC-6 (B2 end-to-end integration — drift surfaces in `schema_slice["index_health"]`).** A unit test `tests/unit/probes/layer_c/test_runtime_trace_freshness.py::test_b2_emits_drift_for_runtime_trace`:
  1. Imports `codegenie.probes.layer_c.runtime_trace` (planting the registry entry by import side-effect).
  2. Writes a synthetic `runtime_trace.json` to `raw_dir(tmp_path)` with `built_image_digest="sha256:def..."` and `last_traced_image_digest="sha256:abc..."` and `trace_coverage_confidence="high"` and `last_traced_at="2026-05-17T00:00:00+00:00"`.
  3. Monkeypatches `_exec.run_allowlisted` to return `HEAD_SHA` for `git rev-parse HEAD`.
  4. Runs `await IndexHealthProbe().run(repo, ctx)`.
  5. Asserts the **four-part inequality** against `out.schema_slice["index_health"]["runtime_trace"]["freshness"]` (the `model_dump(mode="json")` shape per [index_health.py:370](../../../../src/codegenie/probes/layer_b/index_health.py)):
     - `freshness["kind"] == "stale"`
     - `freshness["reason"]["kind"] == "digest_mismatch"`
     - `freshness["reason"]["expected"] == "sha256:def..."`
     - `freshness["reason"]["actual"] == "sha256:abc..."`
  6. Asserts `out.schema_slice["index_health"]["runtime_trace"]["confidence"] == "medium"` (the `DigestMismatch → "medium"` rule at [index_health.py:259-260](../../../../src/codegenie/probes/layer_b/index_health.py)).
  7. Asserts `"runtime_trace" in default_freshness_registry.registered_names()` survived the run (no transient registration).

  Asserting all four parts (not just `kind == "stale"`) is the load-bearing mutation-resistance pin — a buggy implementation that regressed `DigestMismatch` to `IndexerError("idk")` would still pass `kind == "stale"` (this is S4-02's "implementation risk #3" applied here).

- [ ] **AC-7 (B2 end-to-end integration — clean run is `Fresh`).** Sister test `test_b2_emits_fresh_for_runtime_trace`: same shape as AC-6 but `built_image_digest == last_traced_image_digest == "sha256:abc..."`; asserts `freshness["kind"] == "fresh"`; `freshness["indexed_at"] == "2026-05-17T00:00:00+00:00"`; `confidence == "high"`. Negative-case discipline (Rule 12: fail loud) — the clean case is asserted so silent breakage is caught.

- [ ] **AC-8 (B2 end-to-end integration — upstream-unavailable).** Sister test `test_b2_emits_stale_for_absent_runtime_trace_slice`: no `runtime_trace.json` written to `raw_dir`; assert `freshness["kind"] == "stale"`; `freshness["reason"]["kind"] == "indexer_error"`; `freshness["reason"]["message"] == "upstream_runtime_trace_unavailable"`. Exercises the empty-dict sentinel path.

- [ ] **AC-9 (mutation-resistance suite).** `tests/unit/probes/layer_c/test_runtime_trace_freshness_mutation.py` defines a parametrized table of 5+ intentionally-wrong stub implementations and asserts each fails at least one named test from AC-2/5/6/7/8:
  - `always_fresh`: returns `Fresh(indexed_at=...)` regardless of input → must fail AC-6 (drift case) AND AC-8 (absent slice).
  - `always_stale`: returns `Stale(IndexerError("x"))` regardless of input → must fail AC-7 (clean case).
  - `swap_expected_actual`: emits `DigestMismatch(expected=last_traced, actual=built)` (swapped) → must fail AC-6 (`expected` / `actual` field assertions).
  - `wrong_reason_kind`: returns `Stale(IndexerError("digest_mismatch"))` for the drift case (collapsed) → must fail AC-6 (`reason["kind"] == "digest_mismatch"` discriminator check).
  - `drops_upstream_unavailable_branch`: returns `Stale(IndexerError("scip_slice_malformed"))` for empty-dict input → must fail AC-8 (message string).

  The test parametrizes the stub list; per-stub, it monkeypatches `default_freshness_registry._checks[IndexName("runtime_trace")] = stub` and asserts at least one of the named tests under AC-6/7/8 fails. Mirrors S5-04 T2 / S5-03 T16 mutation-resistance discipline. **The test would itself fail (false-pass) if any stub were behaviorally correct; that is the structural defense.**

- [ ] **AC-10 (Hypothesis property — totality + purity).** `tests/property/test_runtime_trace_freshness_purity.py` uses Hypothesis to generate arbitrary `dict[str, object]` slices (text strategy for digest strings, `none() | text()`, occasional `int`/`bool` to exercise the malformed branch). For every drawn input:
  - `_check_runtime_trace_freshness(slice_, head)` returns exactly one of `Fresh | Stale` (totality — never raises, never returns None).
  - Called twice with the same input, returns equal values (purity — no hidden state).
  - Called twice with the same input from two separate test processes (parametrized with `pytest-xdist -n2` skip if not installed; Rule 11), returns equal values (no hidden mutable globals).
  - Wall-clock between two calls with the same input is < 5 ms (no I/O fallthrough — soft signal; the AST audit at AC-4 is the hard structural defense).

- [ ] **AC-11 (argument-order canary).** `tests/unit/probes/layer_c/test_runtime_trace_freshness.py::test_arg_order_is_slice_then_head` asserts the registry's positional call signature is honored:
  - `_check_runtime_trace_freshness({"built_image_digest": "sha256:abc", "last_traced_image_digest": "sha256:abc", "last_traced_at": "2026-01-01T00:00:00+00:00", "trace_coverage_confidence": "high"}, "deadbeef")` returns `Fresh`.
  - Calling with swapped args `_check_runtime_trace_freshness("deadbeef", {...})` (string as slice, dict as head) raises `TypeError` (or `AttributeError` on `.get`) — explicitly asserted. This pins the positional contract that `FreshnessRegistry.dispatch_all` ([registry.py:174](../../../../src/codegenie/indices/registry.py)) relies on. A silent regression where the function defensively accepts either order is structurally wrong — the registry MUST be the source of order truth.

- [ ] **AC-12 (`tests/adv/phase02/test_image_digest_drift.py` — load-bearing adversarial, three scenarios).** The file lands and is registered for the `adv-phase02` CI job (S8-03). The job glob `tests/adv/phase02/test_*.py` already picks it up — no S8-03 amendment is needed *by this story* (S8-03 lists `test_image_digest_drift.py` explicitly in phase-arch-design.md L953); the story's PR description re-confirms the path.

  - **Scenario A — cache-key invalidation via the image-digest declared-input token.** `tests/adv/phase02/test_image_digest_drift.py::test_image_digest_change_changes_cache_key`:
    - Constructs a `RuntimeTraceProbe` instance (or, if S5-02's cache-key API is not yet stable at execute time, exercises `cache/keys.py::declared_inputs_for` directly with a synthetic `declared_inputs=["Dockerfile", "image-digest:<resolved>"]`).
    - Binds two distinct `image_digest_resolver` callables: one returning `"sha256:abc..."`, one returning `"sha256:def..."`.
    - Computes the cache key under each binding.
    - **Asserts the two cache keys are distinct.** Subject-under-test is the **token-resolution + cache-key derivation** path landed by S5-02's `cache/keys.py::_resolve_special_token` (S5-02 step 0); this story's adversarial proves the structural integrity of that path at the integration boundary.
    - **No `_execute_scenario` is invoked**; no `docker build` is invoked; the test runs in <100 ms.
    - Mutation hint embedded in the assertion message: `"image-digest:<resolved>` token must produce distinct cache keys under distinct resolver returns — see [02-ADR-0004 §Consequences](../../docs/phases/02-context-gather-layers-b-g/ADRs/0004-image-digest-as-declared-input-token.md). If equal, the dispatch arm in `cache/keys.py::_resolve_special_token` is not folding the resolved string into the content-hash tuple."

  - **Scenario B — drift detection through B2 (`schema_slice["index_health"]["runtime_trace"]`).** `test_drift_detected_through_b2`: same shape as AC-6 but lives in `tests/adv/phase02/`; identical four-part assertion against `schema_slice["index_health"]["runtime_trace"]["freshness"]`. The duplication is intentional — the unit-test sibling under `tests/unit/probes/layer_c/` is the development-time safety net; the adversarial under `tests/adv/phase02/` is the **CI-gating** mirror. The two tests share a fixture helper (`_build_drift_slice(built, last_traced) -> dict[str, object]`) imported from a shared `tests/adv/phase02/_helpers.py`.

  - **Scenario C — clean run is `Fresh`.** `test_clean_run_emits_fresh`: same shape as AC-7 (sibling assertion); also CI-gating.

- [ ] **AC-13 (adversarial does NOT invoke real `docker` or any subprocess).** A pytest fixture `_forbid_real_subprocess` (shared with `tests/adv/phase02/_helpers.py`) monkeypatches `subprocess.run`, `subprocess.Popen.__init__`, `asyncio.create_subprocess_exec`, `asyncio.create_subprocess_shell` to raise `AssertionError("real subprocess forbidden in adversarial layer")` if invoked from this file's tests. Each of the three scenario tests `autouse`s this fixture. The Phase 0 `fence` job stays green; the test file completes in ≤ 5 s. Tests use the `clean_freshness_registry` snapshot+restore fixture from the shared conftest.

- [ ] **AC-14 (informative failure messages — ADR-0004 in the assertion narrative).** Every assertion in `test_image_digest_drift.py` that targets the cache-key derivation embeds the substring `"02-ADR-0004"` and `"image-digest"` in the failure message; every assertion targeting B2 drift embeds the substring `"02-ADR-0006"` and `"DigestMismatch"`. A test introspects the file's assertion messages via AST and asserts the coverage (greppable on a build break — operator-side debuggability).

- [ ] **AC-15 (duplicate-registration smoke).** `tests/unit/probes/layer_c/test_runtime_trace_freshness.py::test_runtime_trace_duplicate_registration_rejected`: imports `runtime_trace` (planting the entry), then attempts `default_freshness_registry.register(IndexName("runtime_trace"))(dummy_check)` — assert `FreshnessRegistryError` is raised; `exc_info.value.args[0]` contains `"duplicate index_name"`, `"runtime_trace"`, AND both call-site `module.qualname` strings (mirrors the existing structural test at [tests/unit/indices/test_freshness_registry.py:78-106](../../../../tests/unit/indices/test_freshness_registry.py)). This is a **smoke test** for S1-02's registry hardening at the runtime_trace integration boundary, not a re-test of S1-02 itself. Uses `clean_freshness_registry` to leave the singleton intact.

- [ ] **AC-16 (no edits to `IndexHealthProbe`).** A structural test reads `git diff --name-only origin/master..HEAD` and asserts `src/codegenie/probes/layer_b/index_health.py` is NOT in the diff. **The Open/Closed promise is observable**: adding a new index source must require ZERO edits to B2. Mirrors the registry-symmetry discipline (02-ADR-0006 §Consequences "Gap 3 improvement"; S6-08 will assert the same for semgrep/gitleaks/conventions). If the executor finds a reason to edit `index_health.py`, this AC fails and the executor must escalate to ADR-amend, not silently edit.

- [ ] **AC-17 (`mypy --strict` clean).** New module section + tests pass `mypy --strict`. `_check_runtime_trace_freshness` has no `Any` and no untyped `dict`; the function's return type is the discriminated-union `IndexFreshness`. The repo-wide `--warn-unreachable` (Phase 0) flips a missing `case` arm in any future consumer-side `match` to a build error.

- [ ] **AC-18 (`forbidden-patterns` stays green).** No new pattern violations introduced; the existing layer_c-scope predicate (S5-01) covers the new function and the new test files. No `model_construct`, no plaintext-persistence, no `subprocess.run` literal in the new test files.

## Implementation outline

1. **Add `Final[str]` message constants** at module scope in `src/codegenie/probes/layer_c/runtime_trace.py` (after the existing S5-02 imports, before the `RuntimeTraceProbe` class):
   ```python
   from typing import Final
   _MSG_UPSTREAM_UNAVAILABLE: Final[str] = "upstream_runtime_trace_unavailable"
   _MSG_NO_BUILT_IMAGE: Final[str] = "no_built_image"
   _MSG_NO_TRACE_RECORDED: Final[str] = "no_trace_recorded"
   _MSG_SLICE_MALFORMED: Final[str] = "runtime_trace_slice_malformed"
   ```

2. **Add the freshness function** after the `RuntimeTraceProbe` class. Signature is verbatim per AC-1:
   ```python
   from codegenie.indices.freshness import (
       IndexFreshness, Fresh, Stale, DigestMismatch, IndexerError
   )
   from codegenie.indices.registry import register_index_freshness_check
   from codegenie.types.identifiers import IndexName
   import datetime as _dt

   @register_index_freshness_check(IndexName("runtime_trace"))
   def _check_runtime_trace_freshness(
       slice_: dict[str, object], head: str
   ) -> IndexFreshness:
       """Pure ``(slice, head) -> IndexFreshness`` for runtime_trace.

       The ``head`` parameter is unused (the freshness signal is digest-based,
       not commit-based) but the registry signature is uniform across all
       freshness checks per S1-02; accept-and-ignore.
       """
       # Branch (a): empty dict sentinel — runtime_trace.json absent on disk.
       if not slice_:
           return Stale(reason=IndexerError(message=_MSG_UPSTREAM_UNAVAILABLE))

       # Branch (b): probe ran but produced no usable trace.
       if slice_.get("trace_coverage_confidence") == "unavailable":
           return Stale(reason=IndexerError(message=_MSG_UPSTREAM_UNAVAILABLE))

       # Branch (c): isinstance validation. Mirrors scip_freshness lines 168-184.
       built = slice_.get("built_image_digest")
       last_traced = slice_.get("last_traced_image_digest")
       last_traced_at = slice_.get("last_traced_at")

       if (
           not (built is None or isinstance(built, str))
           or not (last_traced is None or isinstance(last_traced, str))
           or not isinstance(last_traced_at, str)
       ):
           return Stale(reason=IndexerError(message=_MSG_SLICE_MALFORMED))

       # Branch (d): no built image (resolver was unbound / returned None / raised).
       if built is None:
           return Stale(reason=IndexerError(message=_MSG_NO_BUILT_IMAGE))

       # Branch (e): no trace recorded.
       if last_traced is None:
           return Stale(reason=IndexerError(message=_MSG_NO_TRACE_RECORDED))

       # Branch (f): drift case — argument order is load-bearing.
       if last_traced != built:
           return Stale(reason=DigestMismatch(expected=built, actual=last_traced))

       # Branch (g): clean — parse the timestamp. Mirrors scip lines 200-203.
       try:
           parsed = _dt.datetime.fromisoformat(last_traced_at)
       except ValueError:
           return Stale(reason=IndexerError(message=_MSG_SLICE_MALFORMED))
       return Fresh(indexed_at=parsed)
   ```

3. **Add `_check_runtime_trace_freshness` to `__all__`** in `runtime_trace.py` (parallel to `scip_freshness` at `index_health.py:97`). The decorator registration is what makes it findable in the registry; the `__all__` export is what makes it importable in unit tests symbolically.

4. **Write three test files**:
   - `tests/unit/probes/layer_c/test_runtime_trace_freshness.py` — registry-membership / AC-5; B2 integration AC-6 / AC-7 / AC-8; arg-order canary AC-11; duplicate smoke AC-15.
   - `tests/unit/probes/layer_c/test_runtime_trace_freshness_purity.py` — AST-walk audit AC-4; `Final[str]` constant audit AC-3.
   - `tests/unit/probes/layer_c/test_runtime_trace_freshness_mutation.py` — mutation-resistance suite AC-9.
   - `tests/property/test_runtime_trace_freshness_purity.py` — Hypothesis totality + purity AC-10.

5. **Write the adversarial**:
   - `tests/adv/phase02/_helpers.py` — `_build_drift_slice(built, last_traced) -> dict[str, object]`; `_forbid_real_subprocess` autouse fixture; `clean_freshness_registry` shared with the unit-test conftest.
   - `tests/adv/phase02/test_image_digest_drift.py` — three scenarios per AC-12; informative ADR-cross-referenced messages per AC-14.

6. **No edits to `IndexHealthProbe` itself** (AC-16). S4-01 already loops the registry. The whole point of the registry seam is that this story plants a new entry that the loop dispatches generically.

7. **No edits to `cache/keys.py`** unless Scenario A's adversarial demands one — S5-02 step 0 is supposed to have wired `_resolve_special_token`. If it has not landed by execute time, the executor escalates rather than silently fixing it here.

## TDD plan — red / green / refactor

**Red:**

1. `test_runtime_trace_registered_by_module_import` (`tests/unit/probes/layer_c/test_runtime_trace_freshness.py`): import `runtime_trace`; assert `IndexName("runtime_trace")` is in `default_freshness_registry.registered_names()`; assert `_checks[IndexName("runtime_trace")] is _check_runtime_trace_freshness`. (AC-5)
2. `test_freshness_signature_matches_registry_contract`: introspect `_check_runtime_trace_freshness` via `inspect.signature`; assert two positional params named `slice_` and `head`, annotated `dict[str, object]` and `str`. (AC-1)
3. `test_arg_order_is_slice_then_head`: positive call returns `Fresh`; swapped-arg call raises `TypeError` or `AttributeError`. (AC-11)
4. `test_message_constants_are_Final_str` (`test_runtime_trace_freshness_purity.py`): introspect module annotations; assert each of the four `_MSG_*` symbols is `Final[str]`. (AC-3)
5. `test_function_is_pure_via_ast_walk` (`test_runtime_trace_freshness_purity.py`): AST-walk audit. (AC-4)
6. `test_freshness_fresh_when_digests_match`: construct slice with matching digests + valid ISO timestamp; assert `isinstance(result, Fresh)`; assert `result.indexed_at == datetime(2026, 5, 17, tzinfo=UTC)`. (AC-2-g)
7. `test_freshness_stale_digest_mismatch`: `built="sha256:def"`, `last_traced="sha256:abc"`; assert four-part inequality `isinstance(result, Stale)` AND `isinstance(result.reason, DigestMismatch)` AND `result.reason.expected == "sha256:def"` AND `result.reason.actual == "sha256:abc"`. (AC-2-f)
8. `test_freshness_stale_no_built_image`: `built_image_digest=None`; assert `Stale(reason=IndexerError(message=_MSG_NO_BUILT_IMAGE))`. (AC-2-d)
9. `test_freshness_stale_no_trace_recorded`: `last_traced_image_digest=None`; assert `Stale(reason=IndexerError(message=_MSG_NO_TRACE_RECORDED))`. (AC-2-e)
10. `test_freshness_stale_upstream_unavailable_empty_dict`: `slice_={}`; assert `Stale(reason=IndexerError(message=_MSG_UPSTREAM_UNAVAILABLE))`. (AC-2-a)
11. `test_freshness_stale_upstream_unavailable_trace_coverage`: `slice_={"trace_coverage_confidence": "unavailable", "built_image_digest": "sha256:abc", "last_traced_image_digest": "sha256:abc", "last_traced_at": "2026-01-01T00:00:00+00:00"}`; assert the same `Stale(_MSG_UPSTREAM_UNAVAILABLE)`. (AC-2-b)
12. `test_freshness_stale_slice_malformed_wrong_type`: parametrized over field-type errors (e.g., `built_image_digest=123`, `last_traced_at=42`); assert `Stale(_MSG_SLICE_MALFORMED)`. (AC-2-c)
13. `test_freshness_stale_slice_malformed_bad_timestamp`: `last_traced_at="not-a-timestamp"`; matching digests; assert `Stale(_MSG_SLICE_MALFORMED)`. (AC-2-g fallback)
14. `test_b2_emits_drift_for_runtime_trace`: write drift fixture to raw_dir; run `IndexHealthProbe`; four-part assertion on `schema_slice["index_health"]["runtime_trace"]["freshness"]`. (AC-6)
15. `test_b2_emits_fresh_for_runtime_trace`: clean fixture; assert `kind=="fresh"` + `indexed_at` + `confidence=="high"`. (AC-7)
16. `test_b2_emits_stale_for_absent_runtime_trace_slice`: no slice file; assert `message=="upstream_runtime_trace_unavailable"`. (AC-8)
17. `test_runtime_trace_duplicate_registration_rejected`: try to re-register; assert `FreshnessRegistryError` with the expected message-string components. (AC-15)
18. `test_no_edit_to_index_health_module`: `git diff` audit; assert `src/codegenie/probes/layer_b/index_health.py` not in diff. (AC-16)
19. `test_image_digest_change_changes_cache_key` (`tests/adv/phase02/test_image_digest_drift.py`): two resolvers; assert distinct cache keys; failure message names ADR-0004. (AC-12 Scenario A)
20. `test_drift_detected_through_b2` (`tests/adv/phase02/`): adversarial mirror of test 14; failure message names ADR-0006. (AC-12 Scenario B)
21. `test_clean_run_emits_fresh` (`tests/adv/phase02/`): adversarial mirror of test 15. (AC-12 Scenario C)
22. `test_no_real_subprocess_in_adv` (`tests/adv/phase02/`): `_forbid_real_subprocess` autouse triggers `AssertionError` if any subprocess call escapes. (AC-13)
23. `test_assertion_messages_carry_adr_refs` (`tests/adv/phase02/`): AST-introspect the assertion messages in `test_image_digest_drift.py`; assert ADR substring coverage. (AC-14)
24. `test_mutation_resistance_table` (`tests/unit/probes/layer_c/test_runtime_trace_freshness_mutation.py`): parametrized 5+ wrong stubs; assert each fails ≥ 1 named test. (AC-9)
25. `test_hypothesis_totality_and_purity` (`tests/property/test_runtime_trace_freshness_purity.py`): Hypothesis property over arbitrary slice dicts. (AC-10)

**Green:**

1. Add the `Final[str]` constants and `_check_runtime_trace_freshness` to `runtime_trace.py` per the Implementation outline. Update `__all__`.
2. Implement the adversarial test in `tests/adv/phase02/test_image_digest_drift.py` and shared helpers.

**Refactor:**

1. Confirm the freshness function body is < 40 LOC; if longer, collapse to the seven canonical branches above.
2. Confirm `_check_runtime_trace_freshness` reuses `scip_freshness`'s shape verbatim (same isinstance discipline, same `try / except ValueError` for timestamp parsing, same `Stale(IndexerError(_MSG_*))` return path on every failure). Do NOT extract a shared base — the rule-of-three threshold (scip + runtime_trace + the three S6-08 checks = five) is met but the kernel extraction is deferred to S6-08 per Rule 2 (see Notes-for-implementer).
3. Confirm the adversarial reads cleanly — fixtures named, scenarios separated, assertions narrate ADR-0004 and ADR-0006 in failure messages.

## Files to touch

- **Extend (existing from S5-02):** `src/codegenie/probes/layer_c/runtime_trace.py` — add the four `Final[str]` constants, the freshness function, the `@register_index_freshness_check` decorator, and the `__all__` export.
- **New tests:**
  - `tests/unit/probes/layer_c/test_runtime_trace_freshness.py` (AC-5, 6, 7, 8, 11, 15, 16)
  - `tests/unit/probes/layer_c/test_runtime_trace_freshness_purity.py` (AC-3, 4)
  - `tests/unit/probes/layer_c/test_runtime_trace_freshness_mutation.py` (AC-9)
  - `tests/property/test_runtime_trace_freshness_purity.py` (AC-10)
  - `tests/adv/phase02/test_image_digest_drift.py` (AC-12, 13, 14)
  - `tests/adv/phase02/_helpers.py` (shared fixtures + `_build_drift_slice` builder + `_forbid_real_subprocess`)
- **PR description note:** the new adversarial test path is already declared as load-bearing in [phase-arch-design.md §"Testing strategy" L953](../phase-arch-design.md). S8-03's `adv-phase02` job glob `tests/adv/phase02/test_*.py` picks it up by convention; no S8-03 amendment is required *by this story*. The PR description re-confirms the path and verifies the glob via a dry-run `pytest --collect-only tests/adv/phase02/test_image_digest_drift.py`.

## Out of scope

- Other freshness-check registrations — `semgrep`, `gitleaks`, `conventions` register their freshness functions in their own files (S6-08).
- The `stale-scip` fixture full materialization — **S7-02** (the SCIP staleness adversarial is S4-02).
- The `adversarial_dockerfile` container-hardening test — **S5-06**.
- Real `docker build` in CI — the adversarial mocks. A separate Phase-2 `integration` CI job runs real `docker build` against a fixture image (S8-03), but that's not gating on this story's correctness.
- Modifying `IndexHealthProbe` itself — S4-01 already loops the registry; this story plants a new entry the loop will dispatch (AC-16 makes the no-edit promise observable).
- Extracting a shared "freshness-check kernel" base — the rule-of-three threshold is met (scip + runtime_trace + S6-08's three = five total) but per Rule 2 and the S5-04 D2 precedent, the kernel extraction is deferred to S6-08 (where the duplication becomes load-bearing). See Notes-for-implementer.
- Editing `cache/keys.py::_resolve_special_token` — that's S5-02's deliverable (step 0). If the executor finds it absent at execute time, escalate; do NOT silently land it here (would inflate this story past the small-effort budget and split the cache contract across two stories).

## Notes for the implementer

- **Upstream-AC dependency on S5-02 — `last_traced_at` slice field.** This story's AC-2(g) requires the runtime_trace slice to carry `last_traced_at: str` (ISO-8601 UTC) so the freshness function can construct `Fresh.indexed_at: datetime`. Inspection of S5-02's hardened ACs (specifically the slice-key enumeration at AC line 86) shows this field is NOT present today. Before executing S5-05, verify the field is in S5-02's slice. If not, the executor must:
  1. Open an inline AC patch to S5-02 (one new field; the slice key set widens by one; the snapshot test in S5-02 absorbs the addition).
  2. Surface this to the user as a one-line "S5-02 needs `last_traced_at` — patching" before proceeding.
  3. Update both implementations.
  Alternative considered and rejected: using a sentinel datetime (`_dt.datetime.min.replace(tzinfo=_dt.UTC)`) for `Fresh.indexed_at`. Rejected because it regresses the honest-confidence surface — the consumer (`confidence_section.py`, S8-01) would render a misleading timestamp ("indexed at 0001-01-01") on every clean runtime_trace gather.

- **Why the freshness function lives in `runtime_trace.py` and not in `index_health.py`.** Open/Closed at the file boundary (phase-arch-design.md §"Component design" #1; §"Gap 3"). If we put the runtime-trace-freshness check inside `index_health.py`, then adding the SCIP-index freshness check (already landed at `index_health.py:143`) would have set the wrong precedent. The registry decorator inverts this: each probe owns its own freshness function; B2 dispatches them all generically. **AC-16 makes this observable**: zero edits to `index_health.py`. The "S4-01 has a `match index_name:` block that grows every phase" anti-pattern (final-design.md §"Improvement" #14) is exactly what S1-02's registry exists to prevent.

- **The freshness function is pure — no `datetime.now()`, no I/O, no subprocess.** The signal comes from slice content (the `last_traced_at` field S5-02 records at write time). The `head` parameter is unused here (it matters for `scip_index` freshness — there, `head != last_indexed_commit` is the signal — but for `runtime_trace`, the signal is digest-based). Accept the parameter to match the registry's uniform `(slice, head) -> IndexFreshness` shape; document the no-op in the function's docstring. **AC-4's AST-walk audit is the structural defense** against a future contributor sneaking a `datetime.now()` into the function body (source-grep is bypassable via string concatenation; AST-walk is not).

- **Function signature exactness.** The registry's `FreshnessCheck` type alias ([`registry.py:67`](../../../../src/codegenie/indices/registry.py)) is `Callable[[dict[str, object], str], "IndexFreshness"]`. The `scip_freshness` precedent ([`index_health.py:144`](../../../../src/codegenie/probes/layer_b/index_health.py)) uses this verbatim. A typed Pydantic-model slice (the original draft's `RuntimeTraceSlice`) would not register — `mypy --strict` would refuse the assignment because `Callable[[dict[str, object], str], …]` is not a subtype of `Callable[[RuntimeTraceSlice, …], …]`. The function MUST take `dict[str, object]` and do isinstance-checks inline.

- **Scenario B's four-part assertion** is the load-bearing one. Implementation risk #3 (in the S4-02 stale-scip fixture, but the discipline applies here too) says "asserting only `Stale` is too weak — also assert the *reason* and its inner fields, because a future bug could regress from `DigestMismatch` to a generic `IndexerError("idk")` and the test would still pass on the weaker assertion." Don't weaken to `isinstance(result, Stale)` — assert all four inequalities, and assert them against the `model_dump(mode="json")` shape that lands in `schema_slice["index_health"][...]["freshness"]` (NOT the in-process `IndexFreshness` typed value — B2 dumps it before emitting).

- **Argument-order canary (AC-11) is structural defense, not paranoia.** `FreshnessRegistry.dispatch_all` ([registry.py:174](../../../../src/codegenie/indices/registry.py)) calls `check(slices.get(name, {}), head)` — positional. If a freshness function defensively accepts either order, a future registry refactor that reverses the call (or a typo `check(head, slices.get(...))`) would silently corrupt every freshness check in the registry. The canary makes the order load-bearing: the function explicitly fails if called wrong.

- **Rule-of-three threshold reached but NOT extracted in this story.** Five `@register_index_freshness_check` registrations exist by phase-end: `scip` (S4-01), `runtime_trace` (this story), and three more in S6-08 (`semgrep`, `gitleaks`, `conventions`). The duplication across the five would justify a `_FreshnessHelpers` micro-kernel (`_require_str_field`, `_parse_iso_or_stale`, `_empty_dict_sentinel`) — but per Rule 2 / the S5-04 D2 precedent, the extract is deferred to the consumer that triggers it. **S6-08 is the kernel-extraction trigger story**; do NOT extract here. Documented for S6-08 authors via this Notes paragraph + a cross-reference in S6-08's own validation report.

- **The adversarial does not run real `docker`.** Building two real images in CI per PR is too slow and too brittle. AC-13's `_forbid_real_subprocess` fixture is the structural defense — a future "let's quickly add an end-to-end check" contributor cannot silently un-mock the subprocess layer; the fixture's monkeypatched stubs raise `AssertionError` on any escape. A separate `integration` CI job (S8-03) optionally runs real `docker build` against the `distroless-target` fixture for end-to-end smoke — but it's not gating on this story.

- **`IndexHealthProbe` integration call uses `read_raw_slices`.** The adversarial reaches into S4-01's machinery indirectly: write a synthetic `runtime_trace.json` to `raw_dir(tmp_path)`, construct an `IndexHealthProbe` (S4-01), call `await probe.run(repo, ctx)`, read the emitted `schema_slice["index_health"]["runtime_trace"]["freshness"]`. The `read_raw_slices` kernel ([index_health.py:212](../../../../src/codegenie/probes/layer_b/index_health.py)) is what hydrates the per-name slice dict the registry dispatches against. Mirrors S5-04's sibling-slice-read precedent.

- **`Fresh.indexed_at` honesty.** The `Fresh` variant's `indexed_at` is rendered in `CONTEXT_REPORT.md`'s Confidence section (S8-01). A sentinel datetime would render as a confusing "indexed at 0001-01-01"; reading from `slice_["last_traced_at"]` carries the real timestamp the runtime_trace probe recorded. The malformed-timestamp fallback (AC-2-g `try / except ValueError → Stale(_MSG_SLICE_MALFORMED)`) is the honest answer when the upstream writer corrupted the field — better than a sentinel + silent rendering.

- **Open question — re-trace on drift.** When the operator rebuilds the image without re-running the gather, B2 surfaces `Stale(DigestMismatch)`. The *response* (re-run `codegenie gather`) is the operator's; this story doesn't auto-re-trace. Document in the freshness function's docstring: "the resolution path is `codegenie gather` re-run; B2's job is detection, not remediation."

- **Open question — multi-image repos.** A repo with `Dockerfile` + `apps/api/Dockerfile` + `apps/web/Dockerfile` could in principle trace all three. Today, `RuntimeTraceProbe` traces only the canonical one (the slice's `built_image_digest` is singular). Multi-image support is a future ADR; the freshness function does NOT defensively handle `built_image_digest` as a list — if S5-02's slice ever widens this field's type, the AC-2-c `isinstance(...)` check fails fast (`Stale(_MSG_SLICE_MALFORMED)`), which is the right structural answer until a follow-up ADR pins the multi-image shape.

- **The `clean_freshness_registry` fixture is shared.** The `tests/unit/probes/layer_b/test_index_health_probe.py:74-87` fixture pattern (snapshot + restore the singleton's `_checks` and `_origins` dicts in a `finally` block) is the canonical idiom. Reuse it via a shared conftest under `tests/conftest.py` (if not already there — check before adding) or duplicate inline. Do NOT call `unregister_for_tests` and forget to restore — the test pollution propagates to every downstream test in the same process.
