# Story S5-05 — `runtime_trace` freshness-check registration + `image_digest_drift` adversarial

**Step:** Step 5 — Ship Layer C (runtime + container) probes
**Status:** Ready
**Effort:** S
**Depends on:** S5-02 (`RuntimeTraceProbe` emits `last_traced_image_digest` and `built_image_digest`), S1-02 (`@register_index_freshness_check` decorator-registry), S1-01 (`IndexFreshness`, `DigestMismatch`), S4-01 (`IndexHealthProbe` loops the freshness registry)
**ADRs honored:** 02-ADR-0004 (image-digest as `declared_inputs` special token — the adversarial proves cache invalidation), 02-ADR-0006 (sum-type freshness location), 02-ADR-0003 (`IndexHealthProbe` `runs_last=True` — depends on this freshness function executing at the right moment)

## Context

S5-02's `RuntimeTraceProbe` emits two slice fields B2 (`IndexHealthProbe`, S4-01) reads to decide freshness:
- `built_image_digest`: the digest of the image just built (or the cached one).
- `last_traced_image_digest`: the digest of the image actually traced (which equals `built_image_digest` on a clean run, but **differs** when the operator built a new image without re-running the gather — the *drift* case).

When `last_traced_image_digest != built_image_digest`, the runtime-trace index is **stale** — the trace evidence reflects an older image than the one that's currently built. `IndexHealthProbe` must emit `IndexFreshness.Stale(reason=DigestMismatch(expected=built, actual=last_traced))`, not a silent `Fresh`. The mechanism is S1-02's `@register_index_freshness_check("runtime_trace")` registry — `IndexHealthProbe` (S4-01) loops the registry; freshness functions land alongside their probe (Open/Closed at the file boundary — phase-arch-design.md §"Component design" #1 + §"Gap 3").

The load-bearing adversarial: `tests/adv/phase02/test_image_digest_drift.py` mutates the built image between gathers (e.g., `docker build -t <tag>` twice with a Dockerfile edit between) and asserts:
1. The second gather's `built_image_digest` differs from the first.
2. The runtime-trace cache key (via the `image-digest:<resolved>` declared-input token, 02-ADR-0004) invalidates — `RuntimeTraceProbe.run` re-executes scenarios (cache MISS).
3. After the second gather completes, **if** the operator separately rebuilds the image **without** re-running the gather (the drift case), `IndexHealthProbe` emits `Stale(DigestMismatch(...))`.

## References

- [phase-arch-design.md §"Component design" #1 (`IndexHealthProbe`)](../phase-arch-design.md) — registry-dispatched freshness checks.
- [phase-arch-design.md §"Component design" #6 (`RuntimeTraceProbe`)](../phase-arch-design.md) — `last_traced_image_digest` and `built_image_digest` slice fields.
- [phase-arch-design.md §"Edge cases" rows 5, 6, 14](../phase-arch-design.md) — docker-build failure, macOS strace, image-digest resolver returns None.
- [phase-arch-design.md §"Testing strategy" — `test_image_digest_drift.py`](../phase-arch-design.md).
- [02-ADR-0004](../ADRs/0004-image-digest-as-declared-input-token.md) §Consequences — `tests/adv/phase02/test_image_digest_drift.py` (load-bearing adversarial) is named here.
- [02-ADR-0006](../ADRs/0006-index-freshness-sum-type-location.md) — `IndexFreshness` lives at `codegenie.indices.freshness`.
- [High-level-impl.md §"Step 5"](../High-level-impl.md) — registry entry for `@register_index_freshness_check("runtime_trace")` in `runtime_trace.py`.
- [final-design.md §"Adversarial corpus"](../final-design.md) — `test_image_digest_drift.py` listed alongside `test_stale_scip_fixture.py` as load-bearing.

## Goal

Register `@register_index_freshness_check("runtime_trace")` in `runtime_trace.py` — a pure function `(slice, head) -> IndexFreshness` that returns `Stale(DigestMismatch(...))` when `last_traced_image_digest != built_image_digest` and `Fresh(...)` otherwise. Land `tests/adv/phase02/test_image_digest_drift.py` — the load-bearing adversarial proving cache invalidation works against image-digest mutation and that B2 surfaces the drift.

## Acceptance criteria

- [ ] `src/codegenie/probes/layer_c/runtime_trace.py` (the module from S5-02) gains one new top-level function `_check_runtime_trace_freshness(slice_: RuntimeTraceSlice, head: GitSha) -> IndexFreshness`, decorated with `@register_index_freshness_check("runtime_trace")` (S1-02 decorator).
- [ ] The freshness function's body:
  - If `slice_.confidence == "unavailable"` (the upstream probe was skipped or failed) → return `IndexFreshness.Stale(reason=IndexerError(message=f"upstream_runtime_trace_unavailable"))`.
  - If `slice_.built_image_digest is None` → return `IndexFreshness.Stale(reason=IndexerError(message="no_built_image"))`.
  - If `slice_.last_traced_image_digest is None` → return `IndexFreshness.Stale(reason=IndexerError(message="no_trace_recorded"))`.
  - If `slice_.last_traced_image_digest != slice_.built_image_digest` → return `IndexFreshness.Stale(reason=DigestMismatch(expected=built_image_digest, actual=last_traced_image_digest))`.
  - Else → return `IndexFreshness.Fresh(indexed_at=<some-sentinel-or-the-slice-timestamp>)`.
- [ ] The function is **pure** — no I/O, no subprocess, no clock read (the `Fresh.indexed_at` value comes from the slice, not from `datetime.now()`). A grep test asserts `datetime`, `time.time`, `os.path.getmtime`, `Path.stat().st_mtime` are NOT imported into the function's scope.
- [ ] The function appears in the `@register_index_freshness_check` registry after module import; an `IndexHealthProbe` integration test imports `runtime_trace.py`, runs B2 against a fixture slice, and asserts B2's slice contains a `runtime_trace` entry under `index_freshness` with the right discriminated-union variant.
- [ ] `tests/adv/phase02/test_image_digest_drift.py` lands and is **CI-gating** (wired into the `adv-phase02` job in S8-03; this story's PR description notes the dependency).
- [ ] The adversarial test covers three scenarios, each as a separate test function:
  - **Scenario A — cache invalidation on image-digest change.** Two gathers: gather 1 builds image with digest `sha256:abc…`; gather 2 (operator rebuilt the image with a Dockerfile edit between gathers) sees digest `sha256:def…`. Assert: gather 2's `RuntimeTraceProbe.run` is **entered** (cache MISS); the `image-digest:<resolved>` token in `declared_inputs` produced a different cache key. The test mocks `ProbeContext.image_digest_resolver` to return the two distinct digests in sequence.
  - **Scenario B — drift detection.** Construct a `runtime_trace` slice with `built_image_digest="sha256:def…"` and `last_traced_image_digest="sha256:abc…"` (the trace was recorded against an older image; the new image was built but the trace was not re-recorded). Run `IndexHealthProbe.run` against a fixture slice-map containing this; assert the B2 slice's `index_freshness["runtime_trace"]` is `IndexFreshness.Stale(reason=DigestMismatch(expected="sha256:def…", actual="sha256:abc…"))`. **Both inequalities are asserted** — `isinstance(freshness, Stale)`, `isinstance(freshness.reason, DigestMismatch)`, `freshness.reason.expected == "sha256:def…"`, `freshness.reason.actual == "sha256:abc…"` — not just "is stale".
  - **Scenario C — clean run is `Fresh`.** Same digest on both fields → `IndexFreshness.Fresh(...)`; B2's slice carries `index_freshness["runtime_trace"]` as the Fresh variant. Negative-case discipline (Rule 12: fail loud) — the clean case is asserted so silent breakage is caught.
- [ ] **No real `docker build`** runs in the adversarial test — the test mocks `image_digest_resolver`. Phase 0 `fence` job stays green (no actual subprocess invocation in the test); test runs in ≤ 5 s as part of `adv-phase02`.
- [ ] The adversarial test's failure mode is **informative** — if the freshness function returns `Fresh` when it should return `Stale(DigestMismatch)`, the assertion message points at "02-ADR-0004 §Consequences — image-digest declared-input token must invalidate cache".
- [ ] The registry decorator from S1-02 is verified at import time (duplicate-name rejection): a smoke test attempting to register a *second* freshness function under the name `"runtime_trace"` raises `IndexFreshnessRegistryError(reason="duplicate_name")`.
- [ ] `mypy --strict` clean.
- [ ] `forbidden-patterns` stays green.

## Implementation outline

1. Open `src/codegenie/probes/layer_c/runtime_trace.py` (the module from S5-02). At module scope, after the `RuntimeTraceProbe` class, add:
   ```python
   from codegenie.indices.freshness import (
       IndexFreshness, Fresh, Stale, DigestMismatch, IndexerError
   )
   from codegenie.indices.registry import register_index_freshness_check

   @register_index_freshness_check("runtime_trace")
   def _check_runtime_trace_freshness(
       slice_: RuntimeTraceSlice, head: GitSha
   ) -> IndexFreshness:
       # ...the cases listed in AC above...
   ```
2. The function is pure — no I/O. The `head` parameter is unused for runtime_trace (the freshness signal is digest-based, not commit-based) but the registry signature is uniform across all freshness functions per S1-02; accept-and-ignore.
3. Add the freshness function to `__all__` only if the module convention is to export it; otherwise leave it module-private (the decorator registration is what makes it findable).
4. Write `tests/adv/phase02/test_image_digest_drift.py` with the three scenarios above. Use `pytest-subprocess` to mock `run_allowlisted`, and a manual fixture for the `image_digest_resolver` callable.
5. Add the adversarial to the `adv-phase02` CI job spec — the spec lives in S8-03's YAML; this story's PR description notes that the test path must be picked up by that job (`tests/adv/phase02/test_image_digest_drift.py`).

## TDD plan — red / green / refactor

**Red:**

1. `test_runtime_trace_freshness_registered` (`tests/unit/probes/layer_c/test_runtime_trace_freshness.py`): import `runtime_trace`; introspect S1-02 registry; assert `"runtime_trace"` is a key; assert the registered callable is the freshness function.
2. `test_freshness_fresh_when_digests_match`: construct a slice with `built_image_digest == last_traced_image_digest == "sha256:abc"`; call the freshness function; assert `isinstance(result, Fresh)`.
3. `test_freshness_stale_digest_mismatch`: construct a slice with `built = "sha256:def"`, `last_traced = "sha256:abc"`; call freshness function; assert `isinstance(result, Stale)` AND `isinstance(result.reason, DigestMismatch)` AND `result.reason.expected == "sha256:def"` AND `result.reason.actual == "sha256:abc"`.
4. `test_freshness_stale_no_built_image`: `built_image_digest=None`; assert `Stale(reason=IndexerError(message="no_built_image"))`.
5. `test_freshness_stale_no_trace_recorded`: `last_traced_image_digest=None` (and `built_image_digest` present); assert `Stale(reason=IndexerError(message="no_trace_recorded"))`.
6. `test_freshness_stale_upstream_unavailable`: `confidence="unavailable"`; assert `Stale(reason=IndexerError(message="upstream_runtime_trace_unavailable"))`.
7. `test_freshness_function_is_pure`: read the module source; assert the freshness function's body references neither `datetime`, `time.time`, `os.path.getmtime`, nor `Path.stat`.
8. `test_duplicate_registration_rejected`: attempt to register a second freshness function under `"runtime_trace"`; assert `IndexFreshnessRegistryError(reason="duplicate_name")` (or whatever S1-02 named the duplicate-rejection error type).
9. `test_image_digest_drift_scenario_A_cache_invalidation` (`tests/adv/phase02/test_image_digest_drift.py`): mock `image_digest_resolver` to return two distinct digests across two gathers; assert `_execute_scenario` is called on both gathers (cache MISS).
10. `test_image_digest_drift_scenario_B_drift_detection`: construct the drift fixture; run `IndexHealthProbe`; assert the four-part inequality above.
11. `test_image_digest_drift_scenario_C_clean_run_fresh`: same-digest fixture; assert `Fresh`.
12. `test_image_digest_drift_no_real_docker`: instrument the test runner to forbid `subprocess.run`/`asyncio.create_subprocess_exec`; the adversarial completes without invoking either.

**Green:**

1. Implement the freshness function inside `runtime_trace.py`.
2. Implement the adversarial test in `tests/adv/phase02/test_image_digest_drift.py`.

**Refactor:**

1. Confirm the freshness function is < 30 LOC; if longer, the `match`-tree is over-fitted — collapse to the five canonical cases above.
2. Confirm the adversarial test reads cleanly — fixtures named, scenarios separated, assertions narrate ADR-0004 in failure messages.

## Files to touch

- **Extend (existing from S5-02):** `src/codegenie/probes/layer_c/runtime_trace.py` — add the freshness function + its decorator.
- **New tests:** `tests/unit/probes/layer_c/test_runtime_trace_freshness.py`, `tests/adv/phase02/test_image_digest_drift.py`.
- **PR description note:** the new adversarial test path must be picked up by S8-03's `adv-phase02` CI job spec.

## Out of scope

- Other freshness-check registrations — `semgrep`, `gitleaks`, `conventions` register their freshness functions in their own files (S6-08).
- The `stale-scip` fixture full materialization — **S7-02** (the SCIP staleness adversarial is S4-02).
- The `adversarial_dockerfile` container-hardening test — **S5-06**.
- Real `docker build` in CI — the adversarial mocks. A separate Phase-2 `integration` CI job runs real `docker build` against a fixture image (S8-03), but that's not gating on this story's correctness.
- Modifying `IndexHealthProbe` itself — S4-01 already loops the registry; this story plants a new entry the loop will dispatch.

## Notes for the implementer

- **Why the freshness function lives in `runtime_trace.py` and not in `index_health.py`.** Open/Closed at the file boundary (phase-arch-design.md §"Component design" #1; §"Gap 3"). If we put the runtime-trace-freshness check inside `index_health.py`, then adding the SCIP-index freshness check (Phase 3) requires editing `index_health.py`. The registry decorator inverts this: each probe owns its own freshness function; B2 dispatches them all generically. The "S4-01 has a `match index_name:` block that grows every phase" anti-pattern (final-design.md §"Improvement" #14) is exactly what S1-02's registry exists to prevent.
- **The freshness function is pure.** No `datetime.now()`. No `os.path.getmtime`. The signal comes from slice content. The `head` parameter is unused here (it matters for `scip_index` freshness — there, `head != last_indexed_commit` is the signal — but for `runtime_trace`, the signal is digest-based). Accept the parameter to match the registry's uniform `(slice, head) -> IndexFreshness` shape; document the no-op in the function's docstring.
- **Scenario B's four-part assertion** is the load-bearing one. Implementation risk #3 (in the S4-02 stale-scip fixture, but the discipline applies here too) says "asserting only `Stale` is too weak — also assert the *reason* and its inner fields, because a future bug could regress from `DigestMismatch` to a generic `IndexerError("idk")` and the test would still pass on the weaker assertion." Don't weaken to `isinstance(result, Stale)` — assert all four inequalities.
- **The adversarial does not run real `docker`.** Building two real images in CI per PR is too slow and too brittle. Mock the `image_digest_resolver` to return two distinct values; assert the cache key derivation produces two distinct keys; assert the freshness function returns `Stale(DigestMismatch)` against the constructed-slice drift. A separate `integration` CI job (S8-03) optionally runs real `docker build` against the `distroless-target` fixture for end-to-end smoke — but it's not gating on this story.
- **`IndexHealthProbe` integration call.** The adversarial reaches into S4-01's machinery — construct an `IndexHealthProbe` (S4-01), feed it a slice-map containing the constructed `runtime_trace` slice, run it, read its emitted slice's `index_freshness` field. If S4-01's API has not yet stabilized, the test can call the freshness function directly and skip the B2-mediated path — but the manifest's preferred shape is end-to-end through B2.
- **Open question — re-trace on drift.** When the operator rebuilds the image without re-running the gather, B2 surfaces `Stale(DigestMismatch)`. The *response* (re-run `codegenie gather`) is the operator's; this story doesn't auto-re-trace. Document in the freshness function's docstring: "the resolution path is `codegenie gather` re-run; B2's job is detection, not remediation."
- **Open question — multi-image repos.** A repo with `Dockerfile` + `apps/api/Dockerfile` + `apps/web/Dockerfile` could in principle trace all three. Today, `RuntimeTraceProbe` traces only the canonical one (the slice's `built_image_digest` is singular). Multi-image support is a future ADR; the freshness function returns `Stale(IndexerError(message="multi_image_unsupported"))` if `built_image_digest` is somehow plural (defensive — current shape is singular).
- **The duplicate-registration test (`test_duplicate_registration_rejected`)** exercises S1-02's registry hardening — it's not Phase-2-new logic, but it's covered here as a smoke test for the load-bearing behavior. If S1-02 didn't land that hardening, surface it.
- **The adversarial's CI wiring** depends on S8-03's `adv-phase02` job spec. Until that lands, the test runs in the local `pytest` invocation but is not yet gating. Document this in the PR — the test path (`tests/adv/phase02/test_image_digest_drift.py`) must be picked up by the eventual job glob.
