# Story S4-02 — Round-trip + idempotence property tests for `DockerfileRecipeEngine`

**Step:** Step 4 — Land `DockerfileRecipeEngine`, `DockerfileBaseImageSwapTransform`, and the multi-stage refactor recipe
**Status:** Ready
**Effort:** M
**Depends on:** S4-01
**ADRs honored:** ADR-P7-004 (handrolled-only), ADR-P7-006 (Recipe.engine Literal extension), ADR-P7-009 (contract-surface snapshot canary)

## Context

This story lights up the load-bearing safety property of the `DockerfileRecipeEngine` (S4-01): `parse(serialize(parse(x))) == parse(x)` across a Hypothesis-generated input space, plus the idempotence property that applying the base-image-swap recipe twice produces the same diff. These two property tests together are the *initial* G14 evidence — the full ≥30-fixture adversarial corpus (G13) doesn't light up until story S6-02, but the property infrastructure must exist now so S4-03/S4-04/S4-05 build on top of green properties.

Property tests sit above the example tests S4-01 already added: they explore the input space Hypothesis generates, plus a small curated fixture set, and catch the kinds of bugs example tests miss (token-reordering, whitespace canonicalization that's not byte-only, non-idempotent mutations).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy ›Property tests` — the four property tests and their inputs.
  - `../phase-arch-design.md §Component design ›4. DockerfileRecipeEngine` — the round-trip safety property statement.
  - `../phase-arch-design.md §Goals#14` — G14 round-trip safety property is what these tests evidence.
  - `../phase-arch-design.md §Edge cases` rows 2, 10 — round-trip failure semantics, BuildKit heredoc edge.
- **Phase ADRs:**
  - `../ADRs/0005-openrewrite-rewrite-docker-deferred.md` — ADR-P7-004 — the round-trip property is the bar `rewrite-docker` would have had to clear.
  - `../ADRs/0007-recipe-engine-literal-extended-with-dockerfile.md` — ADR-P7-006.
- **Source design:**
  - `../final-design.md §"Departures #3 ADR-P7-004"` — names the round-trip property as the deferral rationale.
- **Existing code:**
  - `src/codegenie/recipes/engines/dockerfile_engine.py` — the engine landed in S4-01.
  - `tests/unit/recipes/engines/test_dockerfile_engine.py` — the example tests from S4-01 (don't duplicate; property tests are *additional*).
- **External docs:**
  - https://hypothesis.readthedocs.io/en/latest/data.html — Hypothesis strategies; build a `dockerfile_text()` strategy that emits well-formed `FROM` + `RUN` + `CMD` lines plus the malformed cases the engine should reject.

## Goal

`tests/property/test_dockerfile_engine_roundtrip.py` and `tests/property/test_dockerfile_engine_idempotent.py` both exist, run under a bounded Hypothesis budget, pass against a curated initial fixture set + Hypothesis-generated inputs, and are wired into the property-test CI lane.

## Acceptance criteria

- [ ] `tests/property/test_dockerfile_engine_roundtrip.py` exists; asserts `parse(serialize(parse(x))) == parse(x)` for every input in a curated fixture set under `tests/fixtures/dockerfiles/property/` (≥5 fixtures) **and** for Hypothesis-generated inputs from a `dockerfile_text()` strategy.
- [ ] `tests/property/test_dockerfile_engine_idempotent.py` exists; asserts that running `DockerfileRecipeEngine.apply(...)` twice with the same `ApplyContext` produces byte-identical `patch_bytes` (idempotence under the same target image).
- [ ] Hypothesis budget is bounded: `@settings(deadline=None, max_examples=100)` (or repository-standard equivalent) so the test runs in < 30 s on the CI runner and total property-lane time stays < 120 s per `phase-arch-design.md §Testing strategy ›CI gates #2`.
- [ ] Round-trip property test covers at least: (a) a minimal single-stage `FROM`, (b) a multi-stage `FROM ... AS ...`, (c) `LABEL` with quoted values, (d) `CMD` JSON-array, (e) `RUN` with line continuations.
- [ ] Inputs the engine should *reject* (BOM, CR, `ONBUILD`, > 1 MB, BuildKit heredoc) are tested via `@pytest.mark.parametrize` with the expected `exit_code` (2 or 3) — not via Hypothesis (these are reject-paths, not round-trip-paths).
- [ ] On Hypothesis failure, the test emits a minimized fixture file under `tests/fixtures/dockerfiles/property/_failures/` so the next implementer can reproduce the case deterministically.
- [ ] Both property tests run as part of `pytest tests/property/` and contribute to the CI gate `tests/property/` < 120 s budget.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` clean on the two new test files.

## Implementation outline

1. Create `tests/property/` if it doesn't yet exist; add `__init__.py`.
2. Curate the initial property fixture set under `tests/fixtures/dockerfiles/property/`: 5 well-formed Dockerfiles spanning single-stage, multi-stage, LABEL-quoted, JSON-array CMD, RUN-continuation.
3. Write the `dockerfile_text()` Hypothesis strategy: composes `FROM <image>` (image drawn from a small valid-name strategy), optional `LABEL key=value`, optional `RUN <cmd>`, optional `CMD [...]`. Keep the strategy narrow — Hypothesis-generating *adversarial* inputs is S6-01's job, not this one.
4. Write `test_roundtrip_property(dockerfile_text)`: invoke `tools.dockerfile_parse.parse`, serialize, re-parse, assert equality.
5. Write the reject-path parametrize for BOM/CR/ONBUILD/size>1MB/heredoc cases; assert the engine returns the documented `exit_code`.
6. Write `test_idempotence_property` over the same fixture set: run `apply()` twice with identical `ApplyContext`, assert `patch_bytes` byte-identical.
7. Wire shrinking + minimized-fixture dump: on Hypothesis failure, write the minimized failing input to `tests/fixtures/dockerfiles/property/_failures/<sha>.Dockerfile` for reproducibility (S6-02 will inherit this pattern).
8. Confirm the tests run in budget via local `pytest --collect-only` count + a quick local run.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/property/test_dockerfile_engine_roundtrip.py`

```python
# tests/property/test_dockerfile_engine_roundtrip.py
from hypothesis import given, settings
from codegenie.tools import dockerfile_parse
from .strategies import dockerfile_text  # local module — see below

@given(text=dockerfile_text())
@settings(max_examples=100, deadline=None)
def test_round_trip_ast_equality(text: str) -> None:
    # arrange
    ast1 = dockerfile_parse.parse(text)
    serialized = dockerfile_parse.serialize(ast1)
    ast2 = dockerfile_parse.parse(serialized)
    # act / assert
    assert ast2 == ast1, "parse(serialize(parse(x))) != parse(x)"


def test_round_trip_on_curated_fixtures(curated_dockerfile_fixtures):
    # arrange: parametrized over tests/fixtures/dockerfiles/property/*.Dockerfile
    for fixture in curated_dockerfile_fixtures:
        text = fixture.read_text(encoding="utf-8")
        ast1 = dockerfile_parse.parse(text)
        ast2 = dockerfile_parse.parse(dockerfile_parse.serialize(ast1))
        assert ast2 == ast1, f"round-trip failed on {fixture.name}"
```

Companion red test for idempotence in `tests/property/test_dockerfile_engine_idempotent.py`:

```python
def test_apply_twice_byte_identical(tmp_path, curated_dockerfile_fixtures):
    # arrange: same Dockerfile, same target image, two engine invocations
    for fixture in curated_dockerfile_fixtures:
        ctx = build_apply_context(repo_root=tmp_path, dockerfile=fixture, target="cgr.dev/...")
        engine = DockerfileRecipeEngine()
        # act
        first = engine.apply(ctx)
        second = engine.apply(ctx)
        # assert
        assert first.patch_bytes == second.patch_bytes, f"non-idempotent on {fixture.name}"
```

Run both. They fail because either `tests/property/` doesn't exist, or the `dockerfile_text()` strategy module doesn't exist, or the curated fixtures don't exist. Commit the failing tests as markers.

### Green — make it pass

- Create `tests/property/strategies.py` with the `dockerfile_text()` Hypothesis composite strategy.
- Create the 5 curated fixture files under `tests/fixtures/dockerfiles/property/`.
- Create `conftest.py` with the `curated_dockerfile_fixtures` parametrize fixture.
- Run; both tests should pass on the green S4-01 engine. If round-trip fails on a curated fixture, the engine has a bug — file it before claiming green.

### Refactor — clean up

- Tighten the `dockerfile_text()` strategy: bound depth, bound line count to keep budgets predictable.
- Add shrinking hints (`@example(...)`) for any failing case discovered during green.
- Add a `tests/property/README.md` (≤ 30 lines) explaining the budget convention so S6-02's full-corpus implementer doesn't reinvent it.
- Confirm `pytest tests/property/ -q` finishes < 120 s on the developer machine (CI budget margin will be different; document the actual time observed in the PR body).

## Files to touch

| Path | Why |
|---|---|
| `tests/property/__init__.py` | New empty file — package marker. |
| `tests/property/strategies.py` | New file — `dockerfile_text()` Hypothesis composite strategy. |
| `tests/property/conftest.py` | New file — `curated_dockerfile_fixtures` parametrize fixture. |
| `tests/property/test_dockerfile_engine_roundtrip.py` | New file — G14 initial evidence. |
| `tests/property/test_dockerfile_engine_idempotent.py` | New file — apply-twice byte-identical property. |
| `tests/fixtures/dockerfiles/property/*.Dockerfile` | 5 new curated fixtures spanning single-stage, multi-stage, LABEL, CMD JSON-array, RUN continuation. |
| `tests/property/README.md` | Short note documenting the budget + minimized-fixture-dump convention. |

## Out of scope

- **Full adversarial corpus (≥ 30 fixtures, G13).** — handled by story S6-01.
- **Property tests over the full corpus (G14 fully lit).** — handled by story S6-02.
- **`test_image_name_allowlist.py`, `test_distroless_ledger_serialization.py`, `test_gate_predicates.py`.** — listed under `phase-arch-design.md §Testing strategy ›Property tests` but each belongs to a different step (S6-02 / S5-01 / S5-02).
- **Performance assertions (p95 ≤ 100 ms).** — handled by story S7-04 (`tests/perf/test_dockerfile_engine_p95.py`).
- **Engine bug-fixes surfaced by Hypothesis.** — fix in the engine module (S4-01 scope) and document the case in `tests/fixtures/dockerfiles/property/_failures/`; don't add new mutation primitives here.

## Notes for the implementer

- A property test is only as good as its input strategy. A `dockerfile_text()` strategy that always emits `"FROM alpine\n"` will pass forever and prove nothing. The intent test for the strategy is: it can shrink down to the smallest counterexample that breaks round-trip. If it can't, the strategy is too narrow.
- Hypothesis non-determinism: pin `@settings(database=None)` if cross-runner reproducibility matters; otherwise the Hypothesis database in `.hypothesis/` will diverge between developer and CI. Document the choice in `tests/property/README.md`.
- Don't run the engine's `git format-patch` step inside the round-trip property test — that's expensive and unrelated. Round-trip is a *parse/serialize* property; the engine's `apply()` invokes it but the test should target `tools.dockerfile_parse.parse + serialize` directly.
- The idempotence test does call `engine.apply()` twice — that's expensive (subprocess per call). Cap the curated fixture set at 5 for this test; Hypothesis-generated idempotence is over-scope for this story.
- Per `CLAUDE.md` Rule 9, every test must encode WHY. The round-trip property's WHY is: "if it fails, the engine can corrupt user Dockerfiles silently when re-emitting them". State that in the test docstring.
- When Hypothesis finds a failure, it will minimize and produce a tiny counterexample. *Save that counterexample as a curated fixture* before claiming green — otherwise S6-02 will re-discover it.
- The phase-arch-design names ≥12 unit tests in S4-01 and these two property tests in S4-02 — don't conflate. S4-01 owns example-based tests; this story owns property-based ones. If you find yourself adding example tests here, move them to S4-01.
