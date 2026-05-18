# Story S7-03 — `vuln_provenance` Phase-3 generalisation

**Step:** Step 7 — Ship plugin wiring: FallbackTierPlanRecipeEngine + harvest + E2E exit criteria
**Status:** Ready
**Effort:** S
**Depends on:** S2-01 (`ProvenanceGate.classify` over seven `Provenance` variants), Phase-3 `NpmVulnProvenanceAdapter` (refuse-mode) shipped
**ADRs honored:** production-ADR-0038 (provenance gate semantics), ADR-0012 (`ProvenanceGate` as tier-0; `BaseImage/RuntimeBundled/Unknown` refuse)

## Context

Phase 3's `NpmVulnProvenanceAdapter` ships in refuse-mode only — it answers "app-layer or not" as a binary, used by S7-05 of Phase 3 (npm app-layer precheck) to short-circuit non-app-layer CVEs without ever building a recipe. Phase 4 lifts the same adapter to its full seven-variant `Provenance` classification (`AppDirect | AppTransitive | AppVendored | BaseImage | RuntimeBundled | Both | Unknown`) — Phase 2's `ProvenanceGate` consumes the full sum type and emits `Refused(PROVENANCE_NOT_APP_LAYER)` for everything not in `{AppDirect, AppTransitive, AppVendored, Both}`.

This is the "surgical per Global Rule 3" generalisation. The Phase-3 adapter already knows everything needed to classify into the seven variants — it currently returns a `bool` (or a refuse-shape) when the underlying logic can produce a richer answer. The job here is to **widen the return type and rewire the call site**, not to rewrite the classification logic. ADR-0038 (production) names this "lifted to an explicit gate."

The risk to manage: this is the *only* story in Step 7 that touches a Phase-3 file. The `test_kernel_frozen.py` allow-list must permit the diff under `plugins/vulnerability-remediation--node--npm/adapters/vuln_provenance.py` (which is plugin-side, not kernel-side); but the *behavior* of the adapter is a Phase-3 contract change. Read Phase-3 ADRs first to confirm the adapter's return shape is plugin-internal (and therefore extensible) rather than a kernel-locked Protocol.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 6 — ProvenanceGate` — "Delegates to plugin's `NpmVulnProvenanceAdapter` (Phase 3 generalised)."
  - `../phase-arch-design.md §Development view` — `p_adapt["adapters/vuln_provenance.py (Phase 3; small generalisation)"]`.
  - `../phase-arch-design.md §Scenario 3` — sequence diagram: `Prov->>NpmProv: classify (Phase 3 refuse-mode shape, generalised)` → `NpmProv-->>Prov: BaseImage`.
  - `../phase-arch-design.md §Edge case #1` — `Provenance.BaseImage / Unknown` → `Refused(PROVENANCE_NOT_APP_LAYER)` before any leaf call.
- **Phase ADRs:**
  - `../ADRs/0012-provenance-gate-explicit-tier-zero.md` — `ProvenanceGate.classify(advisory, repo_ctx) -> Provenance`; refuse-set is `{BaseImage, RuntimeBundled, Unknown}`; **zero LLM tokens spent on refuse**.
- **Production ADRs:**
  - `../../../production/adrs/0038-provenance-gate.md` — provenance gate semantics.
- **Source design:**
  - `../final-design.md §Component 6 — ProvenanceGate`.
- **High-level impl:**
  - `../High-level-impl.md §Step 7` — "small Phase-3 generalisation lifting `NpmVulnProvenanceAdapter` from refuse-mode to full `Provenance` classification. **Surgical per Global Rule 3**."
- **Existing code:**
  - `plugins/vulnerability-remediation--node--npm/adapters/vuln_provenance.py` (Phase 3) — current refuse-mode classifier. **Read this before editing.**
  - `src/codegenie/fallback/provenance_gate.py` (S2-01) — consumer of the seven-variant `Provenance`.
  - `src/codegenie/fallback/types.py` (S1-01) — the `Provenance` sum type definition.
  - Phase-3 story `S7-05-npm-app-layer-precheck.md` — describes the refuse-mode contract this story generalises.

## Goal

Generalise `plugins/vulnerability-remediation--node--npm/adapters/vuln_provenance.py` from a refuse-mode binary classifier to a full seven-variant `Provenance` classifier — keeping the original refuse-mode callers green via a thin adapter shim — so `ProvenanceGate.classify(advisory, repo_ctx)` returns the rich sum type Phase 4 needs to emit `Refused(PROVENANCE_NOT_APP_LAYER)` for `{BaseImage, RuntimeBundled, Unknown}` deterministically.

## Acceptance criteria

- [ ] `plugins/vulnerability-remediation--node--npm/adapters/vuln_provenance.py` exposes `class NpmVulnProvenanceAdapter` with `classify(advisory: CveAdvisory, repo_ctx: RepoContext) -> Provenance` returning a value from the closed seven-variant union (`AppDirect | AppTransitive | AppVendored | BaseImage | RuntimeBundled | Both | Unknown`).
- [ ] The existing Phase-3 refuse-mode callers (whatever name they invoke; check the Phase-3 story S7-05 first) continue to work — either via the new method, via a preserved thin `is_app_layer(advisory, repo_ctx) -> bool` wrapper (returning `result in {AppDirect, AppTransitive, AppVendored, Both}`), **or** by call-site update if there is exactly one caller (surface this per Global Rule 7 if ambiguous).
- [ ] Table-driven unit test (`tests/unit/plugin/test_vuln_provenance_adapter.py`) covers all seven `Provenance` variants — one fixture `(advisory, repo_ctx)` pair per variant; each classification is deterministic across calls.
- [ ] Hypothesis property test: for every `(advisory, repo_ctx)` pair, `classify` returns one of the seven variants — no `None`, no exception leaks (other than typed `ProvenanceAdapterFailed` for malformed input).
- [ ] Integration test asserts `ProvenanceGate.classify(...)` returns `BaseImage` for a `glibc-on-Node` fixture and `AppTransitive` for an `express-major-bump` fixture; both fixtures live under `tests/fixtures/provenance/` (small scoped fixtures — do not depend on the S7-05 portfolio).
- [ ] No edits to `src/codegenie/{probes,coordinator,cache,output,schema}/` (asserted by re-running `test_kernel_frozen.py` from S1-07).
- [ ] If Phase-3's previous `classify` returned a non-`Provenance` shape, the change is documented in the adapter's module-level docstring; the docstring explicitly cites Global Rule 3 ("Surgical Changes") and ADR-0012.
- [ ] `make check` clean.
- [ ] TDD red test exists, committed, green.

## Implementation outline

1. **Read first** (Global Rule 8): open the current `adapters/vuln_provenance.py` and Phase-3 story `S7-05-npm-app-layer-precheck.md` to confirm the existing method signature and every caller. List every callsite in the implementer notes.
2. Decide adapter shape based on existing callers:
   - **One caller, no ambiguity** → rename the existing method to `classify` returning `Provenance`; update the single caller.
   - **Multiple callers, mixed shape** → add new `classify(...)  -> Provenance`; keep `is_app_layer(...)` as a thin wrapper computing `result in {AppDirect, AppTransitive, AppVendored, Both}`.
   - Surface the choice in the docstring + story-attempt log; do not blend (Global Rule 7).
3. Extend the classification logic: read `package.json` + `package-lock.json` to detect `AppDirect` (top-level deps) and `AppTransitive` (deeper deps); read `Dockerfile`/`runtime base image` metadata in `repo_ctx` to detect `BaseImage` (vuln package shipped by the OS image) and `RuntimeBundled` (e.g., Node runtime ships the vuln transitively); `Both` if both; `AppVendored` for vendored copies; `Unknown` for "evidence absent" — fail-closed to `Unknown`, not to `AppTransitive`.
4. Implement the seven-variant classification as a single `match` (or named function-per-variant chain); each branch carries a short comment naming the evidence consumed.
5. Add table-driven tests + the Hypothesis property + the integration smoke.
6. Update the `ProvenanceGate` wiring (if it needs the new adapter reference) and re-run `tests/unit/fallback/test_provenance_gate.py` (S2-01) to confirm the seven-variant flow is exercised end-to-end.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/plugin/test_vuln_provenance_adapter.py
from __future__ import annotations
import pytest
from hypothesis import given, strategies as st
from codegenie.fallback.types import (
    Provenance, AppDirect, AppTransitive, AppVendored,
    BaseImage, RuntimeBundled, Both, Unknown,
)
from plugins.vulnerability_remediation_node_npm.adapters.vuln_provenance import (
    NpmVulnProvenanceAdapter,
)


@pytest.fixture
def adapter() -> NpmVulnProvenanceAdapter:
    return NpmVulnProvenanceAdapter()


@pytest.mark.parametrize(
    "fixture_name,expected_type",
    [
        ("app_direct_express", AppDirect),
        ("app_transitive_lodash_through_express", AppTransitive),
        ("app_vendored_old_left_pad", AppVendored),
        ("base_image_glibc_on_node", BaseImage),
        ("runtime_bundled_node_internal_dep", RuntimeBundled),
        ("both_app_and_base_image", Both),
        ("unknown_no_evidence", Unknown),
    ],
)
def test_classifies_each_variant(adapter, request, fixture_name, expected_type):
    advisory, repo_ctx = request.getfixturevalue(fixture_name)
    result = adapter.classify(advisory, repo_ctx)
    assert isinstance(result, expected_type), (
        f"{fixture_name}: expected {expected_type.__name__}, got {type(result).__name__}"
    )


def test_classify_is_deterministic(adapter, app_transitive_lodash_through_express):
    advisory, repo_ctx = app_transitive_lodash_through_express
    r1 = adapter.classify(advisory, repo_ctx)
    r2 = adapter.classify(advisory, repo_ctx)
    assert r1 == r2


def test_classify_returns_unknown_when_evidence_absent(adapter, empty_repo_ctx, any_advisory):
    """Fail-closed to Unknown, not to a permissive AppTransitive."""
    result = adapter.classify(any_advisory, empty_repo_ctx)
    assert isinstance(result, Unknown)


def test_is_app_layer_wrapper_matches_classify_semantics(
    adapter, app_direct_express, base_image_glibc_on_node,
):
    """If the wrapper is preserved per the chosen migration shape, it must agree with classify."""
    a_adv, a_ctx = app_direct_express
    b_adv, b_ctx = base_image_glibc_on_node
    assert adapter.is_app_layer(a_adv, a_ctx) is True
    assert adapter.is_app_layer(b_adv, b_ctx) is False
```

Run: `pytest tests/unit/plugin/test_vuln_provenance_adapter.py -v` — every test fails (the seven-variant `classify` does not exist yet).

### Green — make it pass

Implement the seven-variant `classify`. Build the fixtures (tiny `RepoContext` literals with the package/manifest/base-image evidence each variant requires). Update / preserve `is_app_layer` per the chosen migration shape.

### Refactor — clean up

- If the classification logic naturally decomposes into "app-layer evidence" + "OS-layer evidence" + "combine" steps, factor those into named private functions: `_app_layer_evidence(advisory, repo_ctx) -> Literal["direct","transitive","vendored","none"]`, `_os_layer_evidence(advisory, repo_ctx) -> Literal["base_image","runtime_bundled","none"]`, `_combine(...) -> Provenance`. Each gets a unit test in isolation.
- Add a module-level docstring with the closed mapping table.
- Re-run `tests/unit/fallback/test_provenance_gate.py` (S2-01) to confirm `ProvenanceGate.classify` now exercises the full seven-variant path.
- Re-run `test_kernel_frozen.py` (S1-07) — must still be green.

## Files to touch

| Path | Why |
|---|---|
| `plugins/vulnerability-remediation--node--npm/adapters/vuln_provenance.py` | Generalise from refuse-mode to full seven-variant `classify`. Single point of behavior change. |
| `plugins/vulnerability-remediation--node--npm/<caller>` (e.g., the Phase-3 app-layer precheck wiring) | Update callsite(s) per the chosen migration shape. |
| `tests/unit/plugin/test_vuln_provenance_adapter.py` | TDD red tests, seven-variant coverage, Hypothesis property, deterministic-classify assertion. |
| `tests/unit/plugin/conftest.py` | Per-variant fixtures (`app_direct_express`, ..., `unknown_no_evidence`) — tiny `RepoContext` literals. |
| `tests/fixtures/provenance/` | Minimal manifest + Dockerfile + base-image stubs (one mini-repo per variant). |

## Out of scope

- The Phase-3 refuse-mode behavior itself — that ships in Phase 3 S7-05; this story extends it without breaking it.
- `ProvenanceGate.classify` — already shipped in S2-01; this story only ensures the adapter it delegates to returns the full sum type.
- E2E `test_phase4_provenance_short_circuits.py` (S7-06's companion); the integration smoke here is scoped to the adapter ↔ gate seam.
- Phase-7-base-plugin discoverability fix for unrecognised base images (deferred per arch §Edge case #1).

## Notes for the implementer

- "Surgical per Global Rule 3" is the load-bearing framing. If you find yourself rewriting more than the classification path, stop and reread the story; the adapter's existing tests must keep passing.
- The choice between (a) renaming `is_app_layer` → `classify` and updating the single caller versus (b) adding a new `classify` and keeping the old wrapper is the *one* decision that needs surfacing. Pick the shape with the fewer callsites disturbed; if it's a coin flip, prefer (b) (preserve the old surface) — Global Rule 11 (match conventions).
- The "fail-closed to `Unknown`" discipline is the security backstop: a missing `Dockerfile`, a malformed `package-lock.json`, or any evidence gap must classify as `Unknown` (which the gate refuses), never as `AppTransitive` (which the gate permits to spend LLM tokens). This is the Phase-3 → Phase-4 ratchet — surface loudly per Global Rule 12 if any branch defaults to a permissive variant.
- Phase 7 distroless will add base-image adapters that turn `Unknown`/`BaseImage` into actionable provenance (per arch §Component 6); this story stops at the seven-variant classification, leaves the actionability to Phase 7.
- The Hypothesis property is intentionally weak ("returns one of seven variants, no exception"). A stronger property — "classification is monotone in evidence" — would require encoding "evidence ordering," which is research-grade and out of scope here.
