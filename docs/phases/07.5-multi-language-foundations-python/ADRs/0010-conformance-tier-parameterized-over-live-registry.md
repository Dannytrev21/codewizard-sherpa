# ADR-0010: `tests/conformance/` is parameterized over the live registry with a collection-completeness guard

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** Parameterized test / open test set · Registry · auto-enrollment · testing-strategy
**Related:** [ADR-0001](0001-languagepack-total-frozen-value-contract-and-freeze.md), [ADR-0002](0002-register-language-validate-all-then-commit-no-unregister.md), [ADR-0006](0006-typescript-retrofit-by-reference-probes-self-registered.md), [ADR-0011](0011-python-search-adapter-tree-sitter-first-scip-deferred.md), [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)

## Context

`mypy --strict` proves a `LanguagePack` is *complete* — every capability field is filled. It cannot prove a capability is *correct*. A `search_adapter_module` pointing at a stub adapter that returns empty results for every query type-checks perfectly and is semantically broken. The roadmap names this exact failure as conformance's reason to exist ([`roadmap.md` §"Phase 7.5"](../../../roadmap.md) row 7.5(a)): "a capability that passes `mypy` but is semantically broken (e.g. a stub search adapter) fails conformance."

The best-practices design proposed parameterizing `tests/conformance/test_language_conformance.py` over the live `default_language_registry.all()` — so a new language auto-enrolls with zero test-file edits. The critic found a hole ([critique.md §Attacks on the best-practices design, hidden assumption 2](../critique.md)): registry-driven parametrization makes pytest *collection* depend on import side effects. If a pack module fails to import (a broken `tree-sitter-python` wheel, an import-order bug), the suite does not *fail* for that language — it **silently collects fewer parameters**. A green run with one language quietly missing looks identical to a green run with all languages present. Auto-enrollment is also auto-*disenrollment* with no guard. The security lens additionally wanted adversarial fixtures as part of conformance; the performance lens wanted a CI budget that does not balloon — but its parallel-fixture-warming mechanism fights pytest and the project bans `pytest-xdist`.

## Options considered

- **Option A — one hand-written conformance test file per language.** An enumerated list. **Pattern:** the same accretion-by-enumeration anti-pattern the byte-edit allowlist exhibits — it grows every phase, no one can reason about it.
- **Option B — parameterize over the live registry, no completeness guard.** Auto-enrollment, but a failed pack import silently drops a language from collection. **Pattern:** Parameterized test — with a silent auto-disenrollment hole.
- **Option C — parameterize over the live registry *plus* a top-of-module collection-completeness guard** (`len(default_language_registry.all()) == EXPECTED_LANGUAGE_COUNT`); adversarial fixtures as first-class cases; session-scoped per-language gather, no `pytest-xdist`. **Pattern:** Parameterized test / open test set + Registry + a loud completeness invariant.

## Decision

`tests/conformance/test_language_conformance.py` is **parameterized over `default_language_registry.all()`** — every registered language auto-enrolls with zero test-file edits. A **top-of-module collection-completeness guard** — `assert len(default_language_registry.all()) == EXPECTED_LANGUAGE_COUNT` — fails the suite *loudly* if a pack module fails to import, closing the auto-disenrollment hole. Per-language capability assertions cover `test_grammar_loads`, `test_detector_detects_own_fixture`, `test_layer_a_probes_produce_nonempty_slices`, `test_dep_graph_strategy_resolves`, `test_search_adapter_is_not_a_stub`, `test_golden_matches`, and `test_language_probes_actually_dispatched` (asserting every `pack.layer_a_probes` probe appears in the coordinator's `coordinator.dispatch.order` — [phase-arch-design.md §Gap analysis Gap 3](../phase-arch-design.md#gap-analysis--improvements)). **Adversarial fixtures are first-class** — a hostile `requirements.txt`, an oversized lockfile, a hostile `setup.py` are conformance cases; "fails closed" is part of *passing*. Each language's fixture is gathered **once per session** (`@pytest.fixture(scope="session")`); **no `pytest-xdist`, no `asyncio.gather` of fixture builds.**

## Tradeoffs

| Gain | Cost |
|---|---|
| A new language auto-enrolls in conformance with zero test-file edits — the registry *is* the test set | The conformance suite's parameter set depends on import side effects firing — the guard is what makes that dependency safe |
| The completeness guard turns a silently-dropped language into a loud red suite — auto-disenrollment is closed | `EXPECTED_LANGUAGE_COUNT` is a constant that must be bumped (a loud one-line edit) every time a language lands — a small, deliberate accounting step |
| A semantically-broken capability (stub adapter, no-op detector) fails conformance — the catch `mypy` cannot make | Conformance's catch is only as strong as the fixture — a thin golden lets a degenerate adapter pass `test_search_adapter_is_not_a_stub` (mitigated by the fixture-shape meta-test, [ADR-0011](0011-python-search-adapter-tree-sitter-first-scip-deferred.md)) |
| Adversarial fixtures are part of *passing* — "fails closed on hostile input" is conformance-verified, not assumed | ~5 extra adversarial fixture repos + goldens add a few seconds of CI the performance lens would prefer to avoid — accepted |
| `test_language_probes_actually_dispatched` checks the headline exit criterion at the integration level — a registered-but-never-dispatched probe is caught | Session-scoped fixtures couple tests through shared state — contained because the cached `RepoContext` is an immutable Pydantic value |

## Pattern fit

This is the toolkit's **Parameterized test / open test set** built on the **Registry pattern**: the test set is *derived* from the live registry rather than enumerated, so it grows by addition exactly as the registry does. The toolkit's caution about registries — "a registry that does more than registration is a smell; keep it dumb, validate on use" — is honored: the conformance tier is the "validate on use" side. The anti-pattern avoided is enumeration-by-hand: one conformance file per language is the same accretion failure as the per-phase byte-edit allowlist [ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md) terminates. The *completeness guard* is the critical refinement — an open test set derived from import side effects has a silent-shrinkage failure mode, and the guard converts that silent shrinkage into a loud invariant violation. The performance lens's parallel fixture-warming was rejected because it fights pytest's lazy per-test fixture model and the project bans the obvious workaround (`pytest-xdist`); session-scoped caching is the buildable budget discipline.

## Consequences

- Every registered language is conformance-tested with no per-language test file — Phase 8+ languages auto-enroll.
- A failed pack import (broken wheel, import-order bug) fails the conformance suite loudly via the completeness guard — no green run with a language silently missing (edge case #11, [phase-arch-design.md §Edge cases](../phase-arch-design.md#edge-cases)).
- `EXPECTED_LANGUAGE_COUNT` is a `Final[int]` test-only constant; landing a language bumps it by one — a loud, reviewed edit.
- `test_search_adapter_is_not_a_stub` requires a golden fixture rich enough to defeat a degenerate adapter (≥1 cross-file ref, ≥1 dep edge) — enforced by a fixture-shape meta-test.
- `test_language_probes_actually_dispatched` reads the session gather's `coordinator.dispatch.order` audit event — it costs nothing extra and closes the registered-but-never-dispatched hole at the integration level (Gap 3).
- Adversarial fixtures are committed under `tests/golden/languages/{language}/` and are part of *passing* conformance — a Python pack that OOMs on a 200 MB `poetry.lock` fails conformance.

## Reversibility

**High.** The conformance tier is a test module; restructuring it is a localized edit with no production-code impact. The completeness guard is one assertion. The most durable commitment is the *shape* — a registry-parameterized open test set rather than enumerated per-language files — because reverting to enumeration reintroduces the accretion ADR-0043 exists to stop. Within that shape, the specific assertions and fixtures are freely revisable.

## Evidence / sources

- [final-design.md §Components — `tests/conformance/` tier](../final-design.md#components), §Synthesis ledger CR-8, §Test plan (conformance), §Risks #4
- [phase-arch-design.md §Component design — `tests/conformance/` tier](../phase-arch-design.md#component-design), §Gap analysis Gap 3, §Testing strategy
- [critique.md §Attacks on the best-practices design, hidden assumption 2](../critique.md) — the auto-disenrollment hole; §Attacks on the performance-first design problem 5 — parallel fixture-warming fights pytest
- [`roadmap.md` §"Phase 7.5"](../../../roadmap.md) row 7.5(a); [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md) — enumeration accretion
