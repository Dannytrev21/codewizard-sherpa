# Story S3-01 — `IndexHealthProbe` (B2) + sub-schema + advisory budget

**Step:** Step 3 — Ship `IndexHealthProbe` (B2) and `BuildGraphProbe` (B5)
**Status:** Ready
**Effort:** L
**Depends on:** S1-11 (`Probe.consumes_peer_outputs` ABC attr + Coordinator dispatch branch), S2-06 (cache-key includes `sub_schema_version`), S2-07 (`SCHEMA-EVOLUTION-POLICY.md`)
**ADRs honored:** ADR-0001 (peer-outputs binding), ADR-0002 (`runtime_trace` deferred / `not_applicable`), ADR-0011 (advisory 200 ms budget + `--strict`), ADR-0004 from Phase 1 (`additionalProperties: false`), Phase 1 ADR-0007 (warning-ID pattern)

## Context

`IndexHealthProbe` is the **honesty oracle** for the entire gather pipeline — the load-bearing roadmap exit-criterion probe (`roadmap.md §"Phase 2"`: "surfaces ≥ 3 staleness cases" via the Phase 2 generalization). It's the only Phase 2 probe that consumes the new `consumes_peer_outputs` coordinator branch (ADR-0001) and therefore the only end-to-end validator of the three-positional-arg `run()` shape that S1-11 just landed. Its **advisory 200 ms budget** plus **never-fail-the-gather** policy (ADR-0011) is the synthesis call: the three lenses split mutually-exclusively on B2's failure mode (`final-design.md "Conflict-resolution table" D4/D5`), and getting this probe on disk early — before its peers in Steps 4–7 — pins the contract so every downstream probe has a well-defined consumer.

The `runtime_trace` domain emits `status: "not_applicable"` (not `not_run`, not `low`) because C4 is deferred-by-design (ADR-0002 + S5-04). This story stubs the consumer side: it reads `not_applicable` from a synthetic peer-output snapshot in unit tests; the real `RuntimeTraceProbe.applies()=False` stub probe lands in Step 5 (S5-04) and the end-to-end wiring confirms in S5-04's test.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #5 IndexHealthProbe (B2) — the honesty oracle` — full interface (`consumes_peer_outputs = True`, `cache_strategy = "none"`, `requires = [scip_index, syft_sbom, grype_cve, semgrep, gitleaks, runtime_trace]`, per-domain rollup, single `git rev-list --count` call, 200 ms advisory budget).
  - `../phase-arch-design.md §"Data model" IndexHealthSlice` — Pydantic-shaped contract: `scip / sbom / cve / semgrep / gitleaks: DomainHealth | None`, `runtime_trace: DeferredDomainHealth`, `confidence_summary: ConfidenceSummary`, `budget_exceeded: bool`.
  - `../phase-arch-design.md §"Control flow"` Wave 6 — B2 runs **last** so peer outputs are already sanitized and frozen.
  - `../phase-arch-design.md §"Failure modes & recovery"` rows 7, 16 — `failed_upstream` per-domain status; budget-exceeded as observability only.
  - `../phase-arch-design.md §"Edge cases"` — `runtime_trace` `not_applicable` distinguishability from `not_run`.
- **Phase ADRs:**
  - `../ADRs/0011-index-health-advisory-budget-and-strict-flag.md` — ADR-0011 — advisory 200 ms budget; `cache_strategy = "none"`; never fails the gather; `--strict` is the supported failure-loud path (S3-04).
  - `../ADRs/0001-peer-outputs-binding.md` — ADR-0001 — frozen `MappingProxyType` third positional argument; `inspect.signature` registration-time check (already enforced by S1-11).
  - `../ADRs/0002-c4-runtime-trace-class-only-phase-5-impl.md` — ADR-0002 — `runtime_trace` domain reads `status: "not_applicable"`; this story uses a synthetic snapshot until S5-04 lands the real stub.
- **Production ADRs:**
  - `../../../production/adrs/0006-deterministic-gather-no-llm.md` — no LLM in gather; per-domain confidence is computed from objective signals only (`commits_behind`, `coverage_pct`, `indexer_errors`, `tool_digest_in_use`).
- **Source design:**
  - `../final-design.md §"Components" §3.2 IndexHealthProbe (B2) — the honesty oracle` — synthesizer ledger row.
  - `../final-design.md §"Conflict-resolution table" D4, D5, D6` — the budget + failure + peer-output resolutions this story implements.
- **High-level impl:**
  - `../High-level-impl.md §"Step 3"` deliverable bullet for `index_health.py`.
- **Existing code (Phase 0/1 + Step 1/2 output):**
  - `src/codegenie/probes/base.py` — `Probe` ABC with `consumes_peer_outputs: ClassVar[bool] = False` (landed in S1-11).
  - `src/codegenie/coordinator.py` — `_build_frozen_peer_snapshot()` + dispatch branch (S1-11).
  - `src/codegenie/probes/__init__.py` — explicit additive import seam.
  - `src/codegenie/errors.py` — extended typed exceptions from S1-01.
  - `src/codegenie/logging.py` — `index_health.budget_exceeded` event name registered in S1-01.
  - `tools/digests.yaml` — pinned tool digests; B2 reads each domain's `tool_digest_in_use` for comparison (S1-09).

## Goal

Ship a deterministic, in-process `IndexHealthProbe` that consumes a frozen post-sanitizer peer-output snapshot, emits a per-domain rollup for `scip / sbom / cve / semgrep / gitleaks / runtime_trace`, calls `git rev-list --count` exactly once, never fails the gather, and emits `index_health.budget_exceeded: true` (observability only) when its wall-clock exceeds 200 ms.

## Acceptance criteria

- [ ] `src/codegenie/probes/index_health.py` exists; `class IndexHealthProbe(Probe)` declares `name = "index_health"`, `declared_inputs = ["__git__:HEAD"]`, `applies_to_tasks = ["*"]`, `applies_to_languages = ["*"]`, `requires = ["scip_index", "syft_sbom", "grype_cve", "semgrep", "gitleaks", "runtime_trace"]`, `cache_strategy = "none"`, `consumes_peer_outputs = True`, `timeout_seconds = 30`, and a `version: str` constant (e.g. `"1.0.0"`).
- [ ] `IndexHealthProbe.run(snapshot, ctx, peer_outputs)` has the **three-argument** signature; `peer_outputs` is annotated `Mapping[str, ProbeOutput]`; the registration-time `inspect.signature` check (from S1-11) accepts it without `ProbeRegistrationError`.
- [ ] `src/codegenie/schema/probes/index_health.schema.json` exists, Draft 2020-12, `schema_version: "v1"`, `additionalProperties: false` at the root **and** at every nested object; declares `IndexHealthSlice` with `scip / sbom / cve / semgrep / gitleaks` of `DomainHealth | null`, `runtime_trace` of `DeferredDomainHealth`, `confidence_summary` of `ConfidenceSummary`, and `budget_exceeded: bool`.
- [ ] Per-domain rollup produces `{last_indexed_commit, commits_behind, coverage_pct, indexer_errors, tool_digest_in_use, confidence, status}` for `scip / sbom / cve / semgrep / gitleaks`; for `runtime_trace` it produces `{status: "not_applicable", reason: str}` (matches the `DeferredDomainHealth` shape).
- [ ] Exactly **one** subprocess invocation per gather: `git rev-list --count <last_indexed_commit>..HEAD`. Default path uses `gitpython` in-process; documented subprocess fallback is **deferred** per Open Question #7 (do not implement both paths in this story — `gitpython` only, with a TODO comment pointing at the fallback ADR slot).
- [ ] `confidence_summary: {overall, per_domain}` is computed: `overall = min(per_domain.values())` with the standard `high > medium > low` order; `per_domain` is a dict keyed by domain name (the same six keys) mapping to the per-domain `confidence`.
- [ ] **Never fails the gather** — every exception path inside `run()` (including `gitpython` failure, peer-output absence, schema-mismatch in a peer slice) is caught and rolled into the slice as `status: "failed_upstream"` + `confidence: "low"` for the affected domain. The probe **always returns** a `ProbeOutput`.
- [ ] **Advisory 200 ms budget** — wall-clock measured around the body of `run()`; on overrun, `slice.budget_exceeded = true` + structlog event `index_health.budget_exceeded` fires (event name registered in S1-01); gather proceeds. **No `asyncio.wait_for` hard kill.**
- [ ] `src/codegenie/probes/__init__.py` adds **one** explicit additive import line registering `IndexHealthProbe`; no rewrite of the registry.
- [ ] Red test exists and was committed failing; green tests in `tests/unit/probes/test_index_health.py` cover at least: (a) all-high synthetic snapshot → `confidence_summary.overall == "high"`; (b) one domain `confidence: low` in the snapshot → that domain `low` + `overall == "low"`; (c) missing peer probe (key absent in `peer_outputs`) → that domain `status: "failed_upstream"`, `confidence: "low"`; (d) `runtime_trace` domain always emits `status: "not_applicable"`, `reason` non-empty; (e) `gitpython` raises → that domain `status: "failed_upstream"`, gather still produces a slice (no exception propagates); (f) wall-clock injected past 200 ms → `budget_exceeded: true`, gather still produces a slice; (g) `cve_scan` present in peer outputs ⇒ `slice.cve.confidence` is **not None** (cross-probe `if/then` precondition for S3-03).
- [ ] `mypy --strict src/codegenie/probes/index_health.py` passes; `ruff format --check` and `ruff check` pass; the sub-schema self-validates via `jsonschema`'s meta-schema.

## Implementation outline

1. **Write the sub-schema first** at `src/codegenie/schema/probes/index_health.schema.json`. Mirror `phase-arch-design.md §"Data model" IndexHealthSlice`. `additionalProperties: false` at root and every nested object; `schema_version: "v1"`; cross-link the SCHEMA-EVOLUTION-POLICY.md in a root-level `$comment` per S2-07.
2. **Define the probe class** at `src/codegenie/probes/index_health.py`:
   - Module-level constants: `INDEX_HEALTH_BUDGET_MS = 200`, `INDEX_HEALTH_VERSION = "1.0.0"`, `INDEX_HEALTH_DOMAINS = ("scip", "sbom", "cve", "semgrep", "gitleaks")`.
   - Class attributes per the acceptance criteria.
   - `async def run(self, snapshot, ctx, peer_outputs)` body:
     - Start a `time.perf_counter()` checkpoint.
     - Build `commits_behind` once via `gitpython` — `git.Repo(snapshot.root).iter_commits(rev_range)` length (or `repo.git.rev_list("--count", rev_range)` — pick the cheaper of the two; the gitpython call is the only "subprocess" — gitpython spawns or libgit2-binds depending on availability; document the chosen call form in a comment).
     - Loop the five standard domains; build `DomainHealth` per `_rollup_one_domain(peer_outputs.get(name), commits_behind_table)`. Missing peer → `failed_upstream` + `low`.
     - `runtime_trace` always: `{"status": "not_applicable", "reason": "C4 deferred to Phase 5 (ADR-0002)"}`.
     - Compute `confidence_summary` from per-domain confidences.
     - Compute wall-clock; if `>= 200`, set `budget_exceeded = True` and fire `structlog.get_logger().info("index_health.budget_exceeded", budget_ms=200, actual_ms=...)`.
     - Return `ProbeOutput(probe_name="index_health", schema_version="v1", confidence=overall, slice=...)` where `confidence` mirrors `confidence_summary.overall` so the envelope-level `cve_scan` ⇒ `index_health.cve.confidence` rule has the field populated.
3. **Defensive exception handling.** Wrap the body in a single `try / except Exception as exc:` outer catch that fills *every* per-domain slot with `failed_upstream` + `low` and emits the slice anyway. **Never re-raise.** This is the architectural contract — B2 never fails the gather (ADR-0011).
4. **Register** in `src/codegenie/probes/__init__.py` with one additive import line.
5. **Cross-probe `if/then` rule** is **not** added in this story (S3-03 owns the envelope edit + the integration test). This story only ensures B2 *populates* `cve.confidence` whenever `cve_scan` peer is present.

## TDD plan — red / green / refactor

### Red — failing test first

Test file path: `tests/unit/probes/test_index_health.py`.

```python
# tests/unit/probes/test_index_health.py
"""Pins: B2 honest per-domain rollup; runtime_trace = not_applicable; budget advisory
(observability only); B2 never fails the gather; missing peer ⇒ failed_upstream.
Traces to: phase-arch-design.md §Component design #5; ADR-0001; ADR-0002; ADR-0011."""
from __future__ import annotations
import asyncio
from types import MappingProxyType
import pytest

from codegenie.probes.index_health import IndexHealthProbe

@pytest.mark.asyncio
async def test_runtime_trace_domain_always_not_applicable(synth_peers_all_high, snapshot, ctx):
    out = await IndexHealthProbe().run(snapshot, ctx, synth_peers_all_high)
    rt = out.slice["runtime_trace"]
    assert rt["status"] == "not_applicable"
    assert rt["reason"]  # non-empty

@pytest.mark.asyncio
async def test_all_high_rollup_high(synth_peers_all_high, snapshot, ctx):
    out = await IndexHealthProbe().run(snapshot, ctx, synth_peers_all_high)
    assert out.slice["confidence_summary"]["overall"] == "high"
    assert all(d["confidence"] == "high" for d in
               (out.slice[k] for k in ("scip","sbom","cve","semgrep","gitleaks")))

@pytest.mark.asyncio
async def test_missing_peer_failed_upstream(synth_peers_missing_scip, snapshot, ctx):
    out = await IndexHealthProbe().run(snapshot, ctx, synth_peers_missing_scip)
    assert out.slice["scip"]["status"] == "failed_upstream"
    assert out.slice["scip"]["confidence"] == "low"
    assert out.slice["confidence_summary"]["overall"] == "low"

@pytest.mark.asyncio
async def test_budget_exceeded_is_observability_only(monkeypatch, synth_peers_all_high, snapshot, ctx):
    # Inject a slow synthetic gitpython call; assert the gather still succeeds
    monkeypatch.setattr("codegenie.probes.index_health._commits_behind",
                        lambda *_a, **_k: __import__("time").sleep(0.30) or 0)
    out = await IndexHealthProbe().run(snapshot, ctx, synth_peers_all_high)
    assert out.slice["budget_exceeded"] is True
    assert out.confidence in ("high","medium","low")  # gather still produced a slice

@pytest.mark.asyncio
async def test_gitpython_raises_failed_upstream_no_exception_propagates(
    monkeypatch, synth_peers_all_high, snapshot, ctx
):
    def boom(*_a, **_k): raise RuntimeError("git repo corrupted")
    monkeypatch.setattr("codegenie.probes.index_health._commits_behind", boom)
    out = await IndexHealthProbe().run(snapshot, ctx, synth_peers_all_high)
    # No raise; every domain rolled to failed_upstream + low
    for k in ("scip","sbom","cve","semgrep","gitleaks"):
        assert out.slice[k]["status"] == "failed_upstream"

def test_cve_confidence_populated_when_cve_peer_present(synth_peers_all_high, snapshot, ctx):
    # Cross-probe if/then precondition (S3-03 enforces it; here we just ensure B2 produces it).
    out = asyncio.run(IndexHealthProbe().run(snapshot, ctx, synth_peers_all_high))
    assert out.slice["cve"] is not None
    assert "confidence" in out.slice["cve"]
```

Run `pytest tests/unit/probes/test_index_health.py -q`. Expect import failure (module doesn't exist yet). Commit the red marker on a branch.

### Green — smallest impl shape

1. Write `src/codegenie/schema/probes/index_health.schema.json` mirroring `IndexHealthSlice`.
2. Write `src/codegenie/probes/index_health.py` per the **Implementation outline**.
3. Register in `src/codegenie/probes/__init__.py`.
4. Iterate tests until green.

### Refactor — bounded cleanup

- Extract `_rollup_one_domain(peer: ProbeOutput | None, commits_behind: int) -> DomainHealth` to a module-private helper if the inline form passes ~20 LOC.
- Pull the `INDEX_HEALTH_DOMAINS` tuple alongside the constants block; do not move it into `catalogs/` (the closed-set domain list is a probe-internal invariant, not a catalog-extensible knob).
- The `gitpython` call site should have **one** comment pointing at Open Question #7 in `final-design.md` for the eventual subprocess-fallback path.
- Confirm `import requests / import httpx / import urllib3` greps return empty.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/index_health.py` | New — `IndexHealthProbe` implementation |
| `src/codegenie/schema/probes/index_health.schema.json` | New — strict sub-schema (`additionalProperties: false`, `schema_version: "v1"`) |
| `src/codegenie/probes/__init__.py` | Edit — one additive import line registering `IndexHealthProbe` |
| `src/codegenie/schema/repo_context.schema.json` | Edit — `$ref` compose `index_health.schema.json` under `probes.index_health` (the `if/then` rule is added by S3-03) |
| `tests/unit/probes/test_index_health.py` | New — unit-test corpus per the TDD plan |
| `tests/unit/probes/conftest.py` | Edit — fixtures `synth_peers_all_high`, `synth_peers_missing_scip`, `snapshot`, `ctx` (reusable across S3-04, S3-03) |

## Out of scope

- **`--strict` + `--strict-domains` CLI exit-code mapping** — S3-04 owns the CLI side; this story only **populates** the slice that S3-04 reads.
- **Envelope cross-probe `if/then` schema rule** — S3-03 adds it; this story only ensures `cve.confidence` is populated whenever the `cve_scan` peer is present.
- **Three seeded-staleness integration fixtures** — `stale_scip_repo/`, `stale_sbom_repo/`, `stale_semgrep_rulepack_repo/` land in Step 8 (S8-04) as roadmap exit-criterion proof.
- **B2 wall-clock bench gate (200 ms p99 + 25%-regression on PRs touching `index_health.py`)** — Step 8 (`tests/bench/test_index_health_budget.py`).
- **`RuntimeTraceProbe` actual stub class** — S5-04. This story consumes a synthetic snapshot in unit tests; the live integration with the stub probe verifies in S5-04 + S8-01.
- **Subprocess-fallback for `git rev-list`** — Open Question #7. Default `gitpython` only; comment-marker for the eventual Phase 14 re-evaluation.

## Notes for the implementer

- B2's per-domain `confidence` is computed **from objective signals only** (`commits_behind`, `coverage_pct`, `indexer_errors`, `tool_digest_in_use`). The probe **must not** ask the peer's own `confidence` field whether it's "really" `low` — peer-self-reported confidence is one signal among the four, not the source of truth. This is `production/adrs/0006` honored at the implementation level.
- The `runtime_trace` reason string should reference ADR-0002 by name so a downstream consumer reading the YAML can grep for it. Keep it short — `"C4 deferred to Phase 5 (ADR-0002)"`.
- `cache_strategy = "none"` is non-negotiable per ADR-0011. The probe **always** re-runs; do not add cache-key derivation. The S2-06 cache-key extension does not apply to B2.
- `inspect.signature` registration-time check (from S1-11) will fail with `ProbeRegistrationError` if you accidentally use `def run(self, snapshot, ctx)` (two-arg) on the class — that's the loud signal. If you see a registration error in CI, you forgot the third positional argument.
- The `gitpython` import lives **inside** `_commits_behind` (lazy import) so that probe registration time stays cheap. Don't import `git` at module top level.
- **Never re-raise from `run()`.** This is the hardest invariant to keep — every Python idiom wants you to let exceptions propagate. The outer `try / except Exception` is the architectural contract. If a test asserts `pytest.raises(...)` against `IndexHealthProbe.run()`, the test is wrong — file a follow-up, don't loosen the catch.
- The structlog event name `index_health.budget_exceeded` is one of the eight event names registered in S1-01 — do not register it again here.
- B2 emits `confidence_summary` and `risk_flags` slices pre-shaped for Phase 8's hot-view projection (per ADR-0011 consequences). Phase 2 ships **only** `confidence_summary`; `risk_flags` is **not** in the v1 sub-schema (it's a Phase 8 add). Do not add it speculatively.
