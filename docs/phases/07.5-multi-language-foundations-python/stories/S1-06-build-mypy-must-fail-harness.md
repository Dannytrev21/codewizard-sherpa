# Story S1-06 — Build the `mypy`-must-fail test harness

**Step:** Step 1 — Establish the `LanguagePack` contract, the `DetectionResult` sum type, and the `markers.py` catalog
**Status:** Ready
**Effort:** M
**Depends on:** S1-02
**ADRs honored:** ADR-0001

## Context
The phase's core guarantee (G2, the Step 1 exit criterion) is "an incomplete `LanguagePack` fails `mypy --strict`" — totality enforced at the *construction site*, before any test runs. A runtime `pydantic.ValidationError` test (shipped by S1-02) proves runtime totality but **not** the compile-time claim. This story builds the net-new test machinery that runs `mypy` against a snippet constructing an incomplete `LanguagePack(...)` and asserts `mypy` reports an error. It is cross-cutting test infrastructure — the harness future frozen-contract stories can reuse — and the load-bearing proof of the headline Step 1 claim.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Goals` — G2: "an incomplete `LanguagePack(...)` is a `mypy --strict` error at the construction call site … *Verified by:* a `mypy`-must-fail snippet test".
- **Architecture:** `../phase-arch-design.md §Testing strategy → Test pyramid` — "requires all six capabilities (omission → `mypy` *and* runtime error)".
- **High-level-impl:** `../High-level-impl.md §Step 1` done-criteria — "An incomplete `LanguagePack(...)` call is a `mypy --strict` error at the construction site (snippet test: a `mypy`-must-fail fixture)."
- **Phase ADRs (rules to honor):** `../ADRs/0001-languagepack-total-frozen-value-contract-and-freeze.md` — ADR-0001 — the totality guarantee is itself a `mypy` property; "never weaken it with `Any` or `# type: ignore`".
- **Existing code:** `src/codegenie/languages/pack.py` — `LanguagePack` (S1-02), the type under test.
- **Existing code:** `pyproject.toml §[tool.mypy]` — the `--strict` config the harness must reproduce; `Makefile` `typecheck` target invokes `mypy --strict src/`.
- **Existing code:** grep `subprocess` usage in `tests/` and `scripts/` — find an existing in-repo pattern for invoking a tool from a test (e.g. how `make check` sub-steps are exercised); the harness invokes `mypy` as a subprocess on a snippet file.

## Goal
Add snippet-based test machinery that writes an incomplete `LanguagePack(...)` snippet, runs `mypy --strict` on it, and asserts `mypy` reports a construction-site error — failing loudly if an incomplete pack ever type-checks.

## Acceptance criteria
- [ ] A test (e.g. `tests/unit/languages/test_language_pack_mypy_totality.py`) writes a snippet constructing `LanguagePack(...)` with a required field omitted, runs `mypy --strict` on it, and asserts a non-zero exit with an error referencing the missing argument / call site.
- [ ] A companion positive case: a snippet constructing a *complete* `LanguagePack(...)` type-checks clean under the same harness — proving the harness does not always report failure (Rule 9 — the test must have teeth).
- [ ] The harness reproduces the project's `mypy --strict` configuration (uses the repo `pyproject.toml` mypy settings, not ad-hoc flags) so the snippet result matches `make typecheck` semantics.
- [ ] The snippet files are written to a tmp path (`tmp_path` fixture) — no committed snippet that itself fails `make check`'s own `mypy` run; the harness-internal snippet is generated, run, and discarded.
- [ ] The test is marked/located so it does not slow the default `pytest` run unduly; if it is meaningfully slow, document the marker choice.
- [ ] The TDD red test exists, is committed, and is green; `ruff check`, `ruff format --check`, `mypy --strict src/`, `pytest` pass on touched files (the harness module itself type-checks clean).
- [ ] Story `**Status:**` set to `Done` on completion.

## Implementation outline
1. Write a helper that takes snippet source text, writes it to `tmp_path`, invokes `mypy` as a subprocess with the project's strict config (point `mypy` at the repo config explicitly), and returns `(exit_code, stdout)`.
2. Write the negative test: an incomplete-`LanguagePack` snippet → assert `exit_code != 0` and the output names the missing field / call site.
3. Write the positive test: a complete-`LanguagePack` snippet → assert `exit_code == 0`.
4. Confirm `mypy` can import `codegenie.languages` from the snippet (the snippet runs against the installed/editable package; ensure `MYPYPATH`/cwd is set so the import resolves).
5. Run red (before the harness exists / before it correctly distinguishes the cases), then green.

### Note on subprocess discipline
The `forbidden-patterns` hook bans `subprocess.run(..., shell=True)`, `os.system`, `os.popen`. Invoke `mypy` with an argument list (`shell=False`) — this is a *test-only* tool invocation, not pipeline code, and does not require an `ALLOWED_BINARIES` amendment (that allowlist governs `codegenie.exec`, not the test suite). If an existing test already shells out to a tool, mirror its pattern.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/languages/test_language_pack_mypy_totality.py` (new).

```python
# _run_mypy(snippet: str, tmp_path) -> tuple[int, str]
#   -- writes snippet to tmp_path/snippet.py, runs mypy --strict against it,
#      returns (returncode, combined output).
#
# test_incomplete_language_pack_fails_mypy
#   snippet = '''
#   from codegenie.languages import LanguagePack
#   from codegenie.types.identifiers import Language
#   LanguagePack(language=Language("python"))   # five required fields omitted
#   '''
#   code, out = _run_mypy(snippet, tmp_path)
#   assert code != 0
#   assert "Missing named argument" in out or "missing" in out.lower()
#
# test_complete_language_pack_passes_mypy  (teeth — Rule 9)
#   snippet = '''<a fully-populated LanguagePack(...) using stub detector + probe>'''
#   code, out = _run_mypy(snippet, tmp_path)
#   assert code == 0, out
```
Red because the harness helper does not exist yet (`NameError`/`ImportError`), then because the snippet/config wiring is not yet correct.

### Green — make it pass
The minimal `_run_mypy` helper invoking `mypy` on a snippet with the repo config, plus the two assertions. The complete-pack snippet may build a `LanguagePack` with locally-defined stub `ProjectDetector` / `Probe` references so the snippet is self-contained.

### Refactor — clean up
Docstring naming G2 / ADR-0001; ensure the helper surfaces `mypy` stdout in the assertion message (Rule 12 — fail loud, show why); pick a deliberate test marker if the subprocess makes it slow; confirm the harness is reusable shape (a future frozen-contract story can call `_run_mypy`).

## Files to touch
| Path | Why |
|---|---|
| `tests/unit/languages/test_language_pack_mypy_totality.py` | new — the `mypy`-must-fail harness + negative/positive cases |

## Out of scope
- The `LanguagePack` type itself — S1-02 (this story tests it).
- The runtime `pydantic.ValidationError` totality test — S1-02 already ships it.
- The contract-snapshot fence (`test_language_pack_contract.py`) — S7-05.
- Generalizing the harness into a shared fixture for *all* frozen contracts — only do that if a second consumer appears; for now one consumer, one module (rule-of-three).

## Notes for the implementer
- This story proves the *compile-time* claim; S1-02's `ValidationError` test proves the *runtime* claim. Both are required by the Step-1 done criteria — do not conflate them.
- The positive snippet test is the teeth (Rule 9): without it, a harness that always returns "error" would pass the negative test and be worthless.
- Do **not** commit a snippet file that fails `mypy` into the repo tree — `make typecheck` runs `mypy --strict src/` and a permanently-broken snippet under `src/` or a collected test path would red the whole suite. Generate snippets into `tmp_path`.
- Invoke `mypy` with an argument list, `shell=False`. This is test machinery, not `codegenie` runtime — the `ALLOWED_BINARIES` chokepoint does not apply, but the `forbidden-patterns` no-`shell=True` rule still does.
- Make the `mypy` invocation reproduce `make typecheck`'s config — an ad-hoc `mypy` with default settings would not be `--strict` and the negative test could pass for the wrong reason.
- Never reach for `# type: ignore` to make a snippet "work" — the harness's entire purpose is to observe `mypy`'s honest verdict (ADR-0001 / Rule 12).
