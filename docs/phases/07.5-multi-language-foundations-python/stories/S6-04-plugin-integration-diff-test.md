# Story S6-04 — Plugin integration diff test on a vulnerable fixture (G10)

**Step:** Step 6 — Build the Python search adapter and the `vulnerability-remediation--python--pip` plugin
**Status:** Ready
**Effort:** M
**Depends on:** S6-03 (the wired, resolving plugin), S5-02 (the pip dep-graph strategy the plugin consumes)
**ADRs honored:** production ADR-0031, production ADR-0032, ADR-0011, ADR-0008, ADR-0009

## Context
The headline exit criterion for Phase 7.5's Python plugin is "the `vulnerability-remediation--python--pip` plugin produces a real diff on a vulnerable Python fixture repo" (goal G10). This story lands the integration test that exercises the wired plugin end-to-end against a deliberately vulnerable Python fixture under `tests/golden/languages/python/`, proving the `(vuln, python, pip)` tuple resolves to a *real* diff — not an empty or degenerate one.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Goals — G10` (line 29) — the plugin produces a real diff; *verified by* an integration test against a vulnerable fixture under `tests/golden/languages/python/`.
- **Architecture:** `../phase-arch-design.md §Testing strategy — Integration` (line 681) — the `vulnerability-remediation--python--pip` plugin exercised against a vulnerable Python fixture (G10), a real diff produced.
- **Architecture:** `../phase-arch-design.md §Risks specific to this step` (line 161) — a stub adapter would pass `mypy` and a naive test; the fixture must have ≥ 1 cross-file reference and ≥ 1 dep edge so the not-a-stub assertion has teeth.
- **Phase ADRs:** `../ADRs/0011-python-search-adapter-tree-sitter-first-scip-deferred.md` — ADR-0011 — the diff is produced via the tree-sitter adapters, no external binary.
- **Phase ADRs:** `../ADRs/0008-python-depgraph-pure-parsing-no-resolution.md` — ADR-0008 — the pip dep-graph strategy the diff relies on parses purely, performs zero resolution/I/O.
- **Phase ADRs:** `../ADRs/0009-requirements-txt-directive-language-parsing-contract.md` — ADR-0009 — the `requirements.txt` parse contract underpinning the pip strategy.
- **Production ADRs:** `../../../production/adrs/0031-plugin-architecture.md` — ADR-0031 — plugin resolution + the `extends` chain the integration test exercises end-to-end.
- **Production ADRs:** `../../../production/adrs/0032-language-search-adapters.md §Dispatch` — how a TCCM derived query routes to the resolved plugin's adapter.
- **Existing code:** `plugins/vulnerability-remediation--python--pip/` (S6-02, S6-03) — the plugin under test.
- **Existing code:** `src/codegenie/depgraph/python/pip.py` (S5-02) — the pip dep-graph strategy the plugin consumes to identify the vulnerable dependency.
- **Existing code:** `tests/golden/` — the golden-fixture conventions (`tests/golden/probes/...`, `tests/golden/lockfiles/...`); the new fixtures land under `tests/golden/languages/python/`.

## Goal
Add an integration test that runs the `vulnerability-remediation--python--pip` plugin against a vulnerable Python fixture and asserts it produces a real, non-degenerate diff.

## Acceptance criteria
- [ ] The TDD red integration test exists, is committed, and starts failing for the right reason (no vulnerable fixture / no diff yet).
- [ ] A vulnerable Python fixture lands under `tests/golden/languages/python/` with a `requirements.txt` pinning a known-vulnerable package, ≥ 1 cross-file import, and ≥ 1 dep edge (so a stub adapter cannot pass).
- [ ] The integration test resolves the `(vulnerability-remediation, python, pip)` tuple to the plugin and produces a **non-empty, non-degenerate diff** touching the vulnerable dependency.
- [ ] The diff is real — it changes the pinned-vulnerable version (or the file the vulnerability lives in), asserted on diff content, not just diff non-emptiness.
- [ ] No external binary is invoked and no network call is made (ADR-0011 / ADR-0008) — assert via subprocess/network monitors or the existing zero-egress harness.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` pass on touched files; `pytest` green for the new integration test and fixture.

## Implementation outline
1. Build the vulnerable Python fixture under `tests/golden/languages/python/` — a small repo: `requirements.txt` pinning a CVE-bearing package version, ≥ 2 Python files with a cross-file import, and a manifest so the Python detector returns `Detected(confidence="high")`.
2. Write the integration test: gather the fixture → resolve the `(vuln, python, pip)` tuple → run the plugin → capture the produced diff.
3. Assert the diff is real — it modifies the vulnerable pin (or its consuming file), not an empty/whitespace diff.
4. Assert zero external-binary spawns and zero outbound connections during the run.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/integration/plugins/test_python_pip_plugin_diff.py`.
Test name: `test_vuln_python_pip_plugin_produces_real_diff_on_vulnerable_fixture` — asserts the plugin produces a non-degenerate diff against the vulnerable fixture.
```python
# arrange: the vulnerable Python fixture under tests/golden/languages/python/<name>/
#          (requirements.txt with a known-vulnerable pin + a cross-file import)
# act:    diff = run vulnerability-remediation--python--pip plugin on the gathered fixture
# assert: diff is not empty and not whitespace-only
#         diff touches the vulnerable dependency (version bump or affected file)
#         no subprocess spawned, no outbound socket opened during the run
```
Must fail because the vulnerable fixture and/or the plugin diff path do not exist yet.

### Green — make it pass
Land the vulnerable fixture (deliberately CVE-bearing pin + cross-file structure). Wire the test through plugin resolution → adapter dispatch → diff production. The smallest path that yields a real diff touching the vulnerable dependency.

### Refactor — clean up
Add the zero-egress / zero-subprocess assertions if not already in the red test. Add the fixture to the golden-fixture conventions so S7-04's portfolio and fixture-shape meta-test can consume it. Docstring the test against G10. Confirm the diff assertion checks *content*, not just non-emptiness (Rule 9 — a test that passes on a hardcoded diff is worthless).

## Files to touch
| Path | Why |
|---|---|
| `tests/golden/languages/python/<vuln-fixture>/` | New — the vulnerable Python fixture (`requirements.txt` + ≥ 2 `.py` files with a cross-file import + a manifest). |
| `tests/integration/plugins/test_python_pip_plugin_diff.py` | New — the red integration test (real diff + zero-egress assertions). |

## Out of scope
- The full golden-fixture portfolio (clean + adversarial + polyglot per language) and the fixture-shape meta-test — S7-04 (this story lands one vulnerable fixture; S7-04 generalizes).
- The conformance-tier `test_golden_matches` / `test_search_adapter_is_not_a_stub` assertions — S7-02.
- The e2e slice row exercising `gather → resolution → diff` in the `tests/e2e/` harness — S8-01.
- The `distroless-migration--python--pip` plugin — deliberate fast-follow (out of phase scope).

## Notes for the implementer
- **The diff must be real (Rule 9 + Rule 12).** Assert on diff *content* — the vulnerable version pin changed, or the affected file changed. A test that only checks `diff != ""` would pass on a hardcoded or wrong diff. "The plugin works" is false if you did not verify the diff actually touches the vulnerability.
- **The fixture must defeat a stub adapter.** ≥ 1 cross-file import + ≥ 1 dep edge is mandatory (arch §Risks line 161) — a thin single-file fixture lets a stub `ImportGraphAdapter` pass and silently rots S6-01's not-a-stub guarantee.
- **Zero egress, zero spawn.** ADR-0011 (tree-sitter-first, no binary) + ADR-0008 (pure-parse dep-graph) mean the whole run touches no network and no subprocess — assert it, do not assume it.
- **Reuse the pip dep-graph strategy as-is.** S5-02's `pip.py` resolves the `requirements.txt` to the dep graph the plugin reads to find the vulnerable dependency — do not re-parse the lockfile in the test.
- **Keep the fixture inside `make check`'s wall-clock envelope.** Small but stub-defeating (OQ1) — the conformance session gather in S7-04 will reuse this fixture, so oversizing it now costs there too.
- **Fixture placement is a contract.** `tests/golden/languages/python/` is the mandatory per-language golden home (arch §Testing strategy line 690) — land the fixture there so S7-04's portfolio and the golden-regen idempotence test pick it up.
