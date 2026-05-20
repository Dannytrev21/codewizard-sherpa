# Story S8-01 — Add the e2e Python slice row

**Step:** Step 8 — Wire the e2e proof and close the phase gate
**Status:** Ready
**Effort:** S
**Depends on:** S6-04, S7-03, S7-04
**ADRs honored:** ADR-0010, ADR-0011, ADR-0004

## Context
The phase's headline exit criterion is "the `vulnerability-remediation--python--pip` plugin produces a real diff on a vulnerable Python fixture repo" *end to end*. S6-04 already proves the plugin produces a diff at the integration layer; this story adds the full-path proof: a single row in a table-driven `tests/e2e/` slice harness that exercises `gather → (vuln, python, pip) plugin resolution → diff` against the vulnerable Python fixture, mirroring the `(task_class, fixture, expected_outcome)` row pattern Phase 3 established. The e2e harness is net-new test infrastructure for this repo (`tests/e2e/` does not exist yet), but it is deliberately thin — one parametrized test function over a `Final` tuple of rows.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Testing strategy → Test pyramid` — the `e2e` bullet: "A row added to the table-driven `tests/e2e/` slice harness exercising `gather → (vuln, python, pip) plugin resolution → diff` against the vulnerable Python fixture."
- **Architecture:** `../phase-arch-design.md §Scenarios — Scenario 1` — the happy-path gather sequence (`coordinator → Python probes → pip dep-graph strategy → sanitizer → writer`) the e2e row walks.
- **Architecture:** `../phase-arch-design.md §Integration with Phase 8` — "`repo-context.yaml` slices now carry a per-slice `language` tag" — the slice the e2e assertion can key off.
- **Phase ADRs:** `../ADRs/0010-conformance-tier-parameterized-over-live-registry.md` — ADR-0010 — the table-driven, data-parameterized test idiom this harness reuses (a `Final` tuple of rows, one `pytest.param` per row).
- **Phase ADRs:** `../ADRs/0011-python-search-adapter-tree-sitter-first-scip-deferred.md` — ADR-0011 — the `(vuln, python, pip)` tuple resolves to the tree-sitter-backed adapters; no `ALLOWED_BINARIES` change, no network.
- **Phase ADRs:** `../ADRs/0004-python-detection-as-base-tier-probe-not-prepass.md` — ADR-0004 — the `gather` half of the row runs the `PythonProjectProbe` base-tier prelude that enriches `detected_languages`.
- **Existing code:** `tests/integration/test_provenance_assembly_via_plugins.py` — the precedent for an integration test that resolves a plugin and exercises it; the e2e row is one level wider (full `gather` first).
- **Existing code:** `plugins/vulnerability-remediation--python--pip/` — the plugin S6-02/S6-03 landed; the e2e row resolves it from the `(vuln, python, pip)` tuple.
- **Existing code:** `tests/golden/languages/python/` — the vulnerable Python fixture S6-04/S7-04 landed; the e2e row's `fixture` column points here.
- **Source design:** `../final-design.md §Synthesis ledger` — the e2e proof closing the Python axis.

## Goal
Add a table-driven `tests/e2e/` slice-harness row that runs `gather → (vuln, python, pip) plugin resolution → diff` against the vulnerable Python fixture and asserts a real, non-empty diff is produced end to end.

## Acceptance criteria
- [ ] A new `tests/e2e/test_language_slices.py` (or repo-conventional name) carries a module-level `Final` tuple of `(task_class, fixture, expected_outcome)` rows; the Python row `("vulnerability-remediation", "python", "pip")` against the vulnerable fixture under `tests/golden/languages/python/` is present and is a `pytest.param` with a readable `id`.
- [ ] The harness test runs a full `codegenie gather` on the fixture, resolves the `vulnerability-remediation--python--pip` plugin from the `(vuln, python, pip)` tuple, applies it, and asserts the produced diff is **non-empty and non-degenerate** — not a stub, not an empty patch.
- [ ] The TDD red test (the e2e row asserting a real diff) exists, is committed red, and is green.
- [ ] The e2e run touches no network and spawns no subprocess outside `ALLOWED_BINARIES` (ADR-0011) — assert via the existing network/subprocess monitor fixtures, or reuse `tests/integration`'s monitor.
- [ ] The e2e row completes within `make check`'s wall-clock envelope — one `gather`, no `asyncio.gather` of fixture builds, no `pytest-xdist`.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` pass on every touched file; the full suite (`pytest -q`) is green; Status set to `Done` on completion.

## Implementation outline
1. Create `tests/e2e/` with `__init__.py` and `test_language_slices.py`.
2. Define a module-level `Final` tuple `SLICE_ROWS` of `(task_class, fixture_language, package_manager)` rows — the Phase 3 `(task_class, fixture, expected_outcome)` shape — with the Python `(vulnerability-remediation, python, pip)` row.
3. Write the parametrized test `test_language_slice_produces_diff` that, per row: builds a `RepoSnapshot` from the fixture, runs `codegenie gather`, resolves the plugin from the tuple, applies it, and asserts a real diff.
4. Reuse the existing network/subprocess monitor fixture so the row also proves zero egress.
5. Keep the gather session-scoped per fixture if a future second row shares a fixture; for one row a function-scoped gather is fine.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/e2e/test_language_slices.py`.

Test name: `test_language_slice_produces_diff[vulnerability-remediation-python-pip]`.

```python
# arrange: SLICE_ROWS includes the Python row; the vulnerable fixture
#   lives under tests/golden/languages/python/. Build a RepoSnapshot.
# act: run codegenie gather → resolve vulnerability-remediation--python--pip
#   from the (vuln, python, pip) tuple → apply the plugin.
# assert: the produced diff is a real unified diff — non-empty,
#   touches the vulnerable dependency, and is not the empty/stub patch.
#   (intent: proves the *whole* Python path works end to end, not just
#    that each capability passes in isolation — the headline exit criterion.)
```

This must fail first because `tests/e2e/` does not exist — `pytest` collects nothing for the path. Commit it red (the test exists, the directory/module does not yet, or the row is absent).

### Green — make it pass
Create `tests/e2e/__init__.py` and `tests/e2e/test_language_slices.py` with the `SLICE_ROWS` `Final` tuple and the parametrized test body. Smallest shape: one row, one test function, reuse the S6-04 plugin-resolution + diff helpers rather than re-deriving them. Wire the fixture path to the S7-04 golden fixture. No new production code — this is a test-only story.

### Refactor — clean up
Add type hints to the `SLICE_ROWS` tuple (`Final[tuple[tuple[str, str, str], ...]]` or a small frozen dataclass row), a module docstring naming the harness's purpose and the Phase 3 row pattern it mirrors, and a one-line comment per row. Confirm the network/subprocess monitor assertion is present. Keep the harness open for Step-8-future rows (TypeScript could get its own row later) — but do not add a TypeScript row now (out of scope).

## Files to touch
| Path | Why |
|---|---|
| `tests/e2e/__init__.py` | New — makes `tests/e2e/` a collectible package. |
| `tests/e2e/test_language_slices.py` | New — the table-driven slice harness + the Python `(vuln, python, pip)` row. |
| `tests/golden/languages/python/` | Read-only — the vulnerable fixture the row points at (landed by S6-04/S7-04). |

## Out of scope
- A TypeScript e2e slice row — the harness is built open for it, but adding it is future work (Phase 8 or a fast-follow).
- New runtime code — the plugin, adapters, and dep-graph strategy all already exist (Steps 4–6); this story is wiring + assertion only.
- `make fence` / `import-linter` finalization — that is S8-02.
- The conformance-tier dispatch assertion — that is S7-03; the e2e row is the *integration*-level proof, distinct from conformance.

## Notes for the implementer
- The e2e directory is genuinely new — verify `pyproject.toml`'s `[tool.pytest.ini_options]` `testpaths`/collection picks up `tests/e2e/`; if `testpaths` is enumerated, add `tests/e2e` (a loud, one-line edit, not a violation).
- The diff assertion must be non-degenerate (Risk in `High-level-impl.md §Step 6` — "a stub adapter would pass a naive test"); assert the diff *touches the vulnerable dependency*, not merely that `len(diff) > 0`.
- Reuse S6-04's plugin-resolution and diff machinery — do not re-implement tuple resolution; the `(vuln, python, pip)` resolution path is already proven at the integration layer.
- Keep the harness inside `make check`'s envelope — one `gather` per row; the architecture explicitly forbids `asyncio.gather` of fixture builds and `pytest-xdist` (`phase-arch-design.md §Testing strategy → CI gates`).
- Assert zero egress: the e2e path must touch no network and spawn nothing outside `ALLOWED_BINARIES` (ADR-0011, ADR-0008) — reuse the existing monitor fixtures rather than writing new ones.
- This row is the runtime proof of the headline exit criterion; do not let it collapse into a re-run of the S6-04 integration test — it must run the *full* `gather` first, exercising the coordinator dispatch path, not just the plugin in isolation.
