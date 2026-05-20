# Story S7-02 — Scaffold the `tests/conformance/` tier + completeness guard

**Step:** Step 7 — Land the `tests/conformance/` tier and the `LanguagePack` contract-snapshot fence
**Status:** Ready
**Effort:** L
**Depends on:** S7-01
**ADRs honored:** ADR-0010, ADR-0001, ADR-0006

## Context
`mypy --strict` proves a `LanguagePack` is *complete* — every capability filled — but cannot prove a capability is *correct*: a `search_adapter_module` pointing at a stub that returns empty results type-checks perfectly and is semantically broken. This story lands the net-new `tests/conformance/` tier — a *single* parameterized pytest module over the live `default_language_registry.all()` so every registered language auto-enrolls with zero test-file edits — plus the top-of-module collection-completeness guard that converts a silently-dropped language (a pack module that failed to import) into a loud red suite.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — tests/conformance/ tier` — one module parameterized over `default_language_registry.all()` with `Language` as `pytest.param(..., id=lang)`; the per-language capability assertions; the completeness guard; session-scoped per-language gather; no `pytest-xdist`.
- **Architecture:** `../phase-arch-design.md §Testing strategy — CI gates` — the conformance suite is a hard gate; the deliberate stub-adapter negative test must fail conformance.
- **Architecture:** `../phase-arch-design.md §Data model` — `EXPECTED_LANGUAGE_COUNT: Final[int] = 2` is internal test-only machinery.
- **Architecture:** `../phase-arch-design.md §Edge cases #11` — a pack module that fails to import → `default_language_registry.all()` shrinks → the completeness guard fails loudly.
- **Phase ADRs:** `../ADRs/0010-conformance-tier-parameterized-over-live-registry.md` — ADR-0010 — Option C: parameterize over the live registry *plus* the completeness guard; session-scoped gather, no `pytest-xdist`, no `asyncio.gather` of fixture builds.
- **Production ADRs:** `../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md` — enumeration-by-hand (one conformance file per language) is the accretion anti-pattern this tier avoids.
- **Existing code:** `tests/unit/test_probe_contract.py` — the snapshot/anchoring discipline and Rule-9 framing to mirror.
- **Existing code:** `tests/fence/` modules — the `Final` anchor + `REPO_ROOT` resolution pattern for test-infra files.
- **Existing code:** `src/codegenie/languages/registry.py` (S2-01) — `default_language_registry.all()`, the parametrize source.

## Goal
Land `tests/conformance/test_language_conformance.py` parameterized over `default_language_registry.all()` with the per-language capability assertions and the `EXPECTED_LANGUAGE_COUNT` collection-completeness guard.

## Acceptance criteria
- [ ] The TDD red test exists, is committed, and was observed failing (or erroring at collection) before the conformance module existed.
- [ ] `test_language_conformance.py` is parameterized over `default_language_registry.all()`, one `pytest.param` per language with the `Language` as the `id`; it auto-enrolls a language with **no** new parametrize list edit.
- [ ] A top-of-module guard `assert len(default_language_registry.all()) == EXPECTED_LANGUAGE_COUNT` (`EXPECTED_LANGUAGE_COUNT: Final[int] = 2`) fails the suite *loudly* if a pack module fails to import — a negative test simulating a missing pack proves it.
- [ ] Per-language capability assertions exist and pass for both languages: `test_grammar_loads`, `test_detector_detects_own_fixture` (`Detected`, `confidence="high"`), `test_layer_a_probes_produce_nonempty_slices`, `test_dep_graph_strategy_resolves`, `test_search_adapter_is_not_a_stub`, `test_golden_matches`.
- [ ] A deliberate stub-adapter negative test (an adapter returning empty for every query) **fails** `test_search_adapter_is_not_a_stub` — the catch `mypy` cannot make (ADR-0010, G4).
- [ ] The per-language fixture is gathered **once** via `@pytest.fixture(scope="session")`; the module contains **no** `asyncio.gather` of fixture builds and **no** `pytest-xdist` use; the session gather completes inside `make check`'s wall-clock envelope.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` pass on the new module; `make fence` and `import-linter` stay green.

## Implementation outline
1. Create `tests/conformance/__init__.py` and `tests/conformance/test_language_conformance.py`.
2. At module top: import `default_language_registry`, define `EXPECTED_LANGUAGE_COUNT: Final[int] = 2`, and assert `len(default_language_registry.all()) == EXPECTED_LANGUAGE_COUNT` with a message routing the reader to a likely failed pack import.
3. Add a session-scoped fixture, parameterized over `default_language_registry.all()`, that runs one `codegenie gather` per language fixture (consuming the per-language fixture dirs S7-04 will fill — until then, a minimal inline/placeholder fixture is acceptable; S7-04 supersedes it) and returns the cached `RepoContext`.
4. Write the six per-language capability tests, each reading the cached `RepoContext` / the pack's capability references.
5. Write `test_search_adapter_is_not_a_stub` so a known query returns a non-empty, non-degenerate result; pair it with a stub-adapter negative test asserting the stub fails it.
6. Wire `tests/conformance/` into `make check` / pytest collection (it runs under the default `pytest -q`).

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/conformance/test_language_conformance.py` itself is the deliverable; the red proof is a meta-test in `tests/conformance/test_conformance_meta.py` (or a `tests/unit/` guard) asserting the tier exists and is registry-driven.
- `test_conformance_is_parameterized_over_live_registry` — collect `test_language_conformance.py` and assert its parametrize ids equal the live `default_language_registry.all()` language names.
```python
def test_conformance_completeness_guard_fires_on_missing_pack(monkeypatch) -> None:
    # arrange: shrink the live registry to one language (simulate a failed pack import)
    # act: re-evaluate the module-top guard
    # assert: it raises AssertionError naming EXPECTED_LANGUAGE_COUNT vs actual
    ...
```
The guard test fails until the guard exists; the parametrize test fails until the conformance module exists.

### Green — make it pass
Write the conformance module with the registry-driven `pytest.mark.parametrize`, the module-top guard, the session-scoped gather fixture, and the six capability tests. Keep `test_search_adapter_is_not_a_stub` honest — a real non-degenerate assertion, not `assert result is not None`.

### Refactor — clean up
Extract the per-capability assertion helpers into pure functions taking the pack + cached `RepoContext`. Add a module docstring explaining the auto-enrollment property and ADR-0010. Ensure the guard's failure message names the *likely cause* (a pack module failed to import) and `EXPECTED_LANGUAGE_COUNT`. Confirm no test mutates the shared session `RepoContext`.

## Files to touch
| Path | Why |
|---|---|
| `tests/conformance/__init__.py` | New — package marker for the net-new tier. |
| `tests/conformance/test_language_conformance.py` | New — the parameterized conformance suite + completeness guard. |
| `tests/conformance/test_conformance_meta.py` | New — the red meta-test (registry-driven parametrize + guard-fires). |
| `pyproject.toml` / `Makefile` | Only if `tests/conformance/` needs explicit pytest path/collection wiring. |

## Out of scope
- `test_language_probes_actually_dispatched` (the dispatch-order assertion / Gap 3) — S7-03.
- The full golden fixture portfolio, the adversarial set, the polyglot fixture, the fixture-shape meta-test — S7-04 (this story may use minimal placeholder fixtures).
- The `LanguagePack` contract-snapshot fence — S7-05.

## Notes for the implementer
- The completeness guard is the *load-bearing* refinement (ADR-0010): registry-driven parametrize depends on import side effects; a failed pack import silently collects fewer params and a green run looks identical to a complete one. The guard must run at module *import/collection* time so a missing language fails collection, not just a test.
- Do **not** enumerate languages by hand anywhere — the parametrize source is the live registry. One hand-written file per language is the exact accretion ADR-0043/ADR-0010 reject.
- Session-scoped fixtures couple tests through shared state — contained only because the cached `RepoContext` is an immutable Pydantic value; never mutate it in a test.
- `test_search_adapter_is_not_a_stub` is only as strong as the fixture (≥1 cross-file ref, ≥1 dep edge) — S7-04's fixture-shape meta-test backs it. Until S7-04, write the assertion to require a genuinely non-degenerate result so it gains teeth when the real fixture lands.
- No `pytest-xdist`, no `asyncio.gather` of fixture builds — the project bans parallel fixture-warming; session-scoped caching is the only budget discipline allowed.
- Adversarial fixtures are *first-class* conformance cases (S7-04 supplies them) — "fails closed" is part of *passing*; leave the assertion seams ready for them.
