# Story S6-02 — Round-trip + image-allowlist + ledger + edge-predicate properties

**Step:** Step 6 — Broaden coverage: adversarial Dockerfile corpus, second E2E fixture, HITL path, LLM-fallback path
**Status:** Ready
**Effort:** M
**Depends on:** S6-01
**ADRs honored:** ADR-P7-006 (`Recipe.engine "dockerfile"`), ADR-P7-007 (advisory `dive`), ADR-P7-001 (gate registry), ADR-0009 (snapshot canary discipline — image-name allowlist regex is part of the snapshot)

## Context

S4-02 landed the initial round-trip + idempotence property tests on a small fixture set — enough to anchor the engine's TDD but insufficient for G14. With S6-01's ≥ 30-fixture adversarial corpus in place, this story expands four property tests so they iterate the **full corpus** (round-trip), explore the canonical Chainguard image-name regex with Hypothesis (allowlist), exercise `DistrolessLedger` serialization symmetrically (ledger), and assert that distroless `@pure_edge` predicates are invariant under mutation of fields they do not consume (gate predicates). Together they close G14, the catalog-poisoning defense, the ledger-roundtrip invariant, and the edge-predicate label-invariance check that Phase 6 established for vuln edges and Phase 7 must replay for distroless edges.

This is cross-cutting validation: every later step assumes that an arbitrary Dockerfile from the corpus does not break the engine, every catalog/RAG output that produces an image name is rejected by the regex on the typosquat path, every ledger snapshot survives a JSON round-trip, and the routing graph behaves identically when irrelevant fields change.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Property tests` (lines 1244–1252) — the canonical names and Hypothesis postures for all four tests
  - `../phase-arch-design.md §Edge cases` rows 1, 2, 3, 10 — round-trip failures, hostile Dockerfiles, typosquat catalog
  - `../phase-arch-design.md §Component 6 ›DistrolessLedger` — `schema_version: Literal["v0.7.0"]`, `extra="forbid"`; what serialization round-trip must preserve
  - `../phase-arch-design.md §Component 7 ›build_distroless_loop()` — `route_after_resolve_target` and other `@pure_edge` predicates whose label invariance the gate-predicate property tests
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0007-recipe-engine-literal-extended-with-dockerfile.md` — ADR-P7-006 — round-trip is the engine's safety property; failure → `RoundTripFailure`
  - `../ADRs/0011-distroless-ledger-parallel-to-vuln-ledger.md` — ADR-P7-009 — ledger is `extra="forbid"`, version-pinned; serialization symmetry is the test
- **Existing code:**
  - `src/codegenie/recipes/engines/dockerfile_engine.py` (S4-01) — round-trip is `parse(serialize(parse(input))) == parse(input)`
  - `src/codegenie/graph/state_distroless.py` (S5-01) — `DistrolessLedger` Pydantic model with `extra="forbid"`
  - `src/codegenie/graph/nodes/distroless/resolve_target_image.py` (S5-02) — the image-name allowlist regex lives here
  - `src/codegenie/graph/distroless_loop.py` (S5-04) — `route_after_resolve_target` and other `@pure_edge` predicates
  - `tests/property/test_dockerfile_engine_roundtrip.py` (S4-02) — *extend* this test to iterate the corpus; do **not** rewrite from scratch
- **Phase 6 prior art (for the gate-predicate invariance pattern):**
  - `tests/property/test_vuln_gate_predicates.py` — Phase 6 established the pattern; clone the posture for distroless edges

## Goal

Four Hypothesis-driven property tests iterate the full S6-01 corpus plus generative input spaces and provably hold for every distroless artefact: round-trip safety on every adversarial Dockerfile, the image-name allowlist accepts canonical Chainguard names and rejects everything else, `DistrolessLedger` serialization is byte-symmetric, and every distroless edge predicate's label is invariant under mutation of fields it does not consume.

## Acceptance criteria

- [ ] `tests/property/test_dockerfile_engine_roundtrip.py` is extended (or wrapped via `@pytest.mark.parametrize` over a Hypothesis strategy + corpus loader) to iterate **every** `tests/adversarial/dockerfiles/*` fixture whose `meta.yaml.expected_disposition == "parses_cleanly"`. For each, asserts `parse(serialize(parse(input))) == parse(input)`. **G14**.
- [ ] `tests/property/test_image_name_allowlist.py` exists. Hypothesis strategy generates image-name-like strings (alphanumerics, dots, slashes, `:`, `@sha256:`-prefixed digests, hostile prefixes `cgr.dev/chamguard/`, `cgr.dev.evil/chainguard/`, etc.). For every generated name, asserts the regex from `resolve_target_image` either accepts the **canonical** form `^cgr\.dev/chainguard/[a-z0-9-]+(@sha256:[a-f0-9]{64}|:[a-z0-9._-]+)$` or rejects, with no false-accept on any typosquat-prefix or hostile-suffix case.
- [ ] `tests/property/test_distroless_ledger_serialization.py` exists. Hypothesis strategy `_st_distroless_ledger()` builds `DistrolessLedger` instances with valid `schema_version`, valid `TargetImageRecommendation`s, valid attempts. Asserts `DistrolessLedger.model_validate_json(ledger.model_dump_json()) == ledger` over ≥ 100 generated instances. Ledger's `id()`-diff hook (S5-01) is asserted as untriggered by serialization (read-only path).
- [ ] `tests/property/test_gate_predicates.py` exists. For each distroless `@pure_edge` predicate (minimally `route_after_resolve_target`, `route_after_select_recipe`, `route_after_rag`, `route_after_attempt` — enumerate from `src/codegenie/graph/distroless_loop.py`), Hypothesis generates a ledger that produces a known route label, then mutates a non-consumed field, and asserts the route label is unchanged. The "non-consumed fields" list is captured per-predicate in the test fixture and validated against the predicate's `inspect.getsource` (so the test breaks loudly if a predicate starts reading a new field without updating the test). Replays Phase 6's `tests/property/test_vuln_gate_predicates.py` pattern.
- [ ] `tests/property/conftest.py` exposes a `corpus_fixtures()` fixture-loader so the round-trip test does not re-implement `meta.yaml` parsing.
- [ ] Total Hypothesis budget for property tests, bounded by `pytest tests/property/`, completes < 120 s on the reference Linux DinD runner — per `phase-arch-design.md §Testing strategy ›CI gates #2`.
- [ ] All four property tests are wired into CI's `pytest tests/property/` lane.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` (where applicable to `tests/property/conftest.py` if it imports from `src/`) clean.

## Implementation outline

1. Build the corpus loader fixture in `tests/property/conftest.py`. It reads `tests/adversarial/dockerfiles/*/meta.yaml`, filters by disposition, and yields `(name, dockerfile_bytes)` tuples.
2. Extend `tests/property/test_dockerfile_engine_roundtrip.py`: add a new test `test_roundtrip_holds_on_adversarial_corpus` that consumes the corpus loader and asserts the round-trip property for each `parses_cleanly` fixture. Keep the existing Hypothesis-generated test from S4-02 intact.
3. Author `tests/property/test_image_name_allowlist.py`. Pull the regex constant from `src/codegenie/graph/nodes/distroless/resolve_target_image.py` directly (do not duplicate it). Compose Hypothesis strategies: canonical inputs (always accept), known-bad prefixes (always reject), purely-random ASCII (regex consistent with itself — no flake).
4. Author `tests/property/test_distroless_ledger_serialization.py`. Build the `_st_distroless_ledger()` strategy. Use `hypothesis.given(_st_distroless_ledger())`. Settings: `max_examples=200, deadline=None` (Pydantic round-trips are fast; deadline guard is moot but explicit-`None` documents intent).
5. Author `tests/property/test_gate_predicates.py`. Discover the predicates by importing `src/codegenie/graph/distroless_loop.py` and listing every `@pure_edge` decorated function. For each, build a known ledger that returns a known label, mutate non-consumed fields with Hypothesis, assert label invariance. Use `inspect.getsource` to confirm the "non-consumed" field list is fresh.
6. Run all four tests, watch the corpus expansion light up new failure modes (it usually does), fix any that surface, then commit.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test files (the first reuses an existing file; the other three are new):

```python
# tests/property/test_image_name_allowlist.py
from hypothesis import given, strategies as st
from codegenie.graph.nodes.distroless.resolve_target_image import IMAGE_NAME_REGEX

CANONICAL = st.builds(
    lambda repo, tag: f"cgr.dev/chainguard/{repo}:{tag}",
    repo=st.from_regex(r"[a-z0-9-]+", fullmatch=True).filter(lambda s: 1 <= len(s) <= 50),
    tag=st.from_regex(r"[a-z0-9._-]+", fullmatch=True).filter(lambda s: 1 <= len(s) <= 50),
)
HOSTILE = st.sampled_from([
    "cgr.dev/chamguard/node:20",
    "cgr.dev.evil/chainguard/node:20",
    "evil.cgr.dev/chainguard/node:20",
    "cgr.dev/chainguard/../escape:20",
])

@given(name=CANONICAL)
def test_canonical_image_names_accepted(name: str) -> None:
    assert IMAGE_NAME_REGEX.fullmatch(name) is not None

@given(name=HOSTILE)
def test_hostile_image_names_rejected(name: str) -> None:
    assert IMAGE_NAME_REGEX.fullmatch(name) is None
```

```python
# tests/property/test_distroless_ledger_serialization.py
from hypothesis import given, settings, strategies as st
from codegenie.graph.state_distroless import DistrolessLedger

# Build _st_distroless_ledger() that produces valid instances; details in S5-01's docstring
_st_distroless_ledger: st.SearchStrategy[DistrolessLedger] = ...

@given(ledger=_st_distroless_ledger)
@settings(max_examples=200, deadline=None)
def test_distroless_ledger_json_roundtrip(ledger: DistrolessLedger) -> None:
    rt = DistrolessLedger.model_validate_json(ledger.model_dump_json())
    assert rt == ledger
```

```python
# tests/property/test_gate_predicates.py
import inspect
from hypothesis import given, strategies as st
from codegenie.graph import distroless_loop as dl

PREDICATES = [dl.route_after_resolve_target, dl.route_after_select_recipe,
              dl.route_after_rag, dl.route_after_attempt]

# For each predicate, the test fixture enumerates the fields its source reads.
# Mutate any *other* field; the label must not change.
@given(...)
def test_gate_predicates_invariant_to_non_consumed_field_mutations(...): ...
```

Red: `ImportError: cannot import name 'IMAGE_NAME_REGEX'` (S5-02 hasn't necessarily exported it as a constant) or `AttributeError` on `dl.route_after_*` if `@pure_edge` registration shape differs. Either is a valid red marker.

### Green — make it pass

- Round-trip extension: in the existing test file, add the corpus loop. The implementation is a `for` loop wrapping the existing assertion.
- Image-name regex test: simplest implementation is to import `IMAGE_NAME_REGEX` from `resolve_target_image`. If S5-02 exposed it as an inline literal rather than a module constant, surface a refactor PR-comment to S5-02 — **do not** duplicate the regex.
- Ledger strategy: compose from `st.from_type(DistrolessLedger)` if Pydantic's schema generation supports Hypothesis (`hypothesis.extra.pydantic` if available); otherwise compose manually field-by-field.
- Gate-predicate test: use `inspect.getsource(predicate)` parsed via `ast.NodeVisitor` to enumerate attribute reads on the ledger. Build the "non-consumed" set by subtracting from the full `DistrolessLedger.model_fields` keyset. Mutate any non-consumed field; assert label invariance.

### Refactor — clean up

- Move the corpus loader into `tests/property/conftest.py` as a pytest fixture so test_roundtrip and any future corpus-driven test reuses it.
- Add a CI assertion that `pytest tests/property/` finishes < 120 s; `phase-arch-design.md §Testing strategy ›CI gates #2`.
- Document the `IMAGE_NAME_REGEX` source-of-truth pointer in the test docstring.
- Honour the gate-predicate property test's loud-failure mode: if the AST analysis fails (predicate changed shape), the test must error with a clear message — *not* silently widen the non-consumed set.

## Files to touch

| Path | Why |
|---|---|
| `tests/property/conftest.py` | New — corpus loader fixture |
| `tests/property/test_dockerfile_engine_roundtrip.py` | Extended — iterate the S6-01 corpus |
| `tests/property/test_image_name_allowlist.py` | New — Hypothesis property on `IMAGE_NAME_REGEX` |
| `tests/property/test_distroless_ledger_serialization.py` | New — JSON round-trip property on `DistrolessLedger` |
| `tests/property/test_gate_predicates.py` | New — label-invariance property on distroless `@pure_edge` predicates |
| `src/codegenie/graph/nodes/distroless/resolve_target_image.py` | (Possibly) export `IMAGE_NAME_REGEX` as a module-level constant if S5-02 inlined it |

## Out of scope

- **Mutation of consumed fields** — testing that a *consumed* field change *does* change the label is a separate (and obvious) test; this property is about non-consumed fields specifically.
- **Round-trip on `rejected` fixtures** — they're rejected before the engine ever sees them; the property test only iterates `parses_cleanly`.
- **Authoring new edge predicates** — that's S5-04's job. This story only tests existing ones.
- **RAG retrieval correctness** — handled by S6-07 (`test_rag_distroless_top1.py`).
- **Cross-task ledger invariance** — handled by S5-07 (`test_chain_no_collision_across_tasks.py`).

## Notes for the implementer

- The round-trip property has already lit up bugs in `dockerfile-parse` once during the phase design. If a corpus fixture fails round-trip, the resolution is **strict rejection at S2-01**, not patching upstream. Add the failing fixture to the rejection list, bump its `expected_disposition` in `meta.yaml`, and move on. See `phase-arch-design.md §Implementation-level risks #4`.
- Hypothesis's `deadline` is `200ms` by default; ledger round-trips are fast but `_st_distroless_ledger` composition can be slow during shrinking. Set `deadline=None` explicitly and bound the budget via `max_examples` only.
- The image-name regex test must consume the **same regex** the production code uses — duplicating the regex defeats the purpose. If S5-02 inlined it, the refactor to expose it as `IMAGE_NAME_REGEX` is in-scope here.
- The gate-predicate test's "non-consumed fields" set is the load-bearing part. If a predicate starts reading a new field and the test isn't updated, you want a *loud* test failure, not silent widening. Use `inspect.getsource` + AST parse — not just `getattr`-tracing — so a predicate edit that adds a `getattr` reads through.
- Per ADR-P7-009, `DistrolessLedger` is `extra="forbid"`. The Hypothesis strategy must respect this — generated instances must not include unknown fields. `pydantic` will reject; Hypothesis will then shrink to no instances, masking coverage. Compose the strategy from the model's `model_fields` directly.
- Per the cross-cutting determinism rule, no `random` or `time` in `src/codegenie/{recipes,graph,probes,transforms,catalogs}/`. Hypothesis lives in `tests/`, so the rule doesn't apply to test code — but **do not** import `random` from a `conftest.py` that resolves under `src/`.
- Update story `Status:` to `Done` when complete.
