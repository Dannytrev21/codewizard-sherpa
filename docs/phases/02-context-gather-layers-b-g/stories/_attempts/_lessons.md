# Cross-story lessons — Phase 02 stories

Append-only. Each entry: lesson · source story · how to apply it on the next attempt.

## L1 — `uv.lock` parity test trips on any new `[project.optional-dependencies]` entry
- **Source:** S1-01 (added `hypothesis` to `[dev]`).
- **Symptom:** `tests/unit/test_makefile_targets.py::test_uv_lock_is_in_lockstep_with_pyproject_dep_set` fails with `missing packages: ['<new-pkg>']`.
- **Fix:** After editing `pyproject.toml`'s dep set, run `uv lock` and commit the regenerated `uv.lock` in the same commit.
- **Why it matters:** Phase 2 stories add ≥ 7 new packages (per phase-arch §Step 1). Forgetting `uv lock` will break every story's CI until the next `uv lock` ships.

## L2 — Ruff's `UP007` + `UP017` rewrite Pydantic-discriminator-union sources
- **Source:** S1-01.
- **Symptom:** Story TDD-plan code blocks use `Union[X, Y]` and `timezone.utc` literally; ruff auto-rewrites to `X | Y` and `datetime.UTC` (rules `UP007`, `UP017` are enabled at `[tool.ruff.lint] select`).
- **Fix:** Apply ruff `--fix` after dropping in the story's prescribed code; the rewrites are safe under Pydantic v2 discriminated unions and Python 3.11+. Don't fight the linter; the codebase convention wins.
- **Why it matters:** Saves a round-trip on every Phase 2 story that copy-pastes story-prescribed type-alias blocks.

## L3 — Stale local venv hides missing `[dev]` extras
- **Source:** S1-01 (`hypothesis` and `import-linter` were both missing locally).
- **Symptom:** `pytest` collection fails on `import hypothesis`; `lint-imports` console script not on PATH.
- **Fix:** Before starting a story that adds a new tool to `[dev]`, run `.venv/bin/pip install -e .[dev]` (or `uv sync --extra dev`) so the venv reflects the pyproject. The CI fence catches the gap, but local cycles compound.
- **Why it matters:** Every Phase 2 story that uses Hypothesis (per phase-arch §"Testing strategy") or a new linter will hit this.

## L4 — `@runtime_checkable` `isinstance` silently mutates target classes' `__dict__`
- **Source:** S1-03 (adapter Protocols + `test_no_phase2_module_implements_adapter_protocol_dynamic`).
- **Symptom:** `tests/unit/test_errors.py::test_subclasses_are_markers_only` fails with `MalformedJSONError declares extra class attributes … '__annotations__'`. Reproduces only when `tests/unit/adapters/test_protocols.py` runs first.
- **Fix:** Any pkgutil-style walk that ends in `isinstance(inst, AnyRuntimeCheckableProtocol)` MUST filter out classes that cannot possibly satisfy the protocol *before* the isinstance call. For adapter-tier protocols, `issubclass(cls, BaseException)` is the right pre-filter — exceptions cannot satisfy `confidence()`/`consumers()`/etc., and skipping them sidesteps the side effect entirely.
- **Why it matters:** Phase 2's S4-01/02 will revisit dynamic protocol-conformance scans (`AdapterConfidence` consumers in `IndexHealthProbe`-adjacent code). The same trap fires there.

## L6 — Test subpackage name collides with stdlib (`types`, `pathlib`, …) → leave it without `__init__.py`
- **Source:** S1-05 (`tests/unit/types/` for the ADR-0033 newtypes).
- **Symptom:** `pytest tests/unit/types/` errors with `ModuleNotFoundError: No module named 'types.test_identifiers'; 'types' is not a package`. The stdlib `types` module wins the lookup when `__init__.py` is present.
- **Fix:** Do **not** add `__init__.py` to test subpackages whose name shadows a stdlib module. Pytest's rootdir-relative collection works without it (every other test subpackage in this repo has `__init__.py` only because its name doesn't collide).
- **Why it matters:** Any future Phase-2 test subpackage named after a stdlib module (`types`, `string`, `array`, `json`, …) will hit the same trap. The fix is structural; converting the test file imports to absolute paths does not avoid the collision because pytest registers the package itself.

## L7 — Surgical type-alias backfills are the right fix when a Phase-2 story imports a Phase-1-owned name that doesn't exist yet
- **Source:** S1-05 (`PackageManager` referenced by AC-2/AC-5 but not previously exported by `codegenie.probes.node_build_system`).
- **Symptom:** `from codegenie.probes.node_build_system import PackageManager` fails at import time; story tests don't even reach AC-1.
- **Fix:** Add a one-line `PackageManager: TypeAlias = Literal["bun","pnpm","yarn-classic","yarn-berry","npm"]` to the Phase-1 module that *owns* the concept (`node_build_system.py`), mirroring the JSON schema enum. Do **not** redefine the alias inside `codegenie/types/` — that violates AC-4 and production ADR-0033. Leave existing `str | None` signatures untouched (`Literal | None` is a structural subtype of `str | None`); the cleanup belongs to a separate Phase-1 ADR amendment.
- **Why it matters:** S1-04 (TCCM model loader) and S1-02 (freshness registry) both import `IndexName` from this story. Any future Phase-2 story that references a Phase-1-owned typed name needs the same surgical-backfill pattern, not a kernel-tier redefinition.

## L8 — Source-file docstrings wrap at column-80; substring assertions must normalize whitespace
- **Source:** S1-06 (`test_exec_module_docstring_phase2_present`).
- **Symptom:** `assert "ten Layer B/C/G tools" in codegenie.exec.__doc__` fails even though the docstring contains the phrase, because Python preserves the source-file `\n` between "B/C/G" and "tools".
- **Fix:** Before the substring check, normalize whitespace with `" ".join(doc.split())`. The pretty-printed phrase you'd read in Sphinx output is the right mental model — but `__doc__` is the raw source text.
- **Why it matters:** Any future docstring-pin AC (S1-07's `run_external_cli`, S5-02's `RuntimeTraceProbe`, etc.) will hit this trap. The fix is structural; pinning shorter substrings just delays the trap until the phrase grows.

## L9 — ADR meta-tests that ban a historical string need rewording in *all* legacy references
- **Source:** S1-06 (`test_adr_0001_enumerates_all_new_binaries`).
- **Symptom:** Pass-2 AC-2's "the string `eight new entries` is absent" assertion failed because (a) the Amendment paragraph historically narrated "the original Decision named eight…" and (b) two §Consequences bullets still said "eight named entries" / "eight new entries" — drift from the original eight-binary scope.
- **Fix:** When the meta-test forbids a substring, rewrite *every* legacy occurrence in the ADR, not just the Decision paragraph. Use semantically equivalent phrasings ("the original Decision named only the named-trigger binaries", "by the ten named entries") rather than count words.
- **Why it matters:** Phase 2 has 10 ADRs; every one will eventually have an amendment whose old wording lives elsewhere in the file. The meta-test pattern is sound, but the executor must `grep` the ADR for *all* legacy phrasings before declaring green.

## L10 — `mock.AsyncMock.await_args` is typed `_Call | None`; mypy strict requires explicit `assert ... is not None`
- **Source:** S1-06 (Pass-2 spawn-spy refactor).
- **Symptom:** `mypy --strict` errors with `Item "None" of "_Call | None" has no attribute "kwargs"` on `spy.await_args.kwargs["env"]`.
- **Fix:** Insert `assert spy.await_args is not None` immediately before the `.kwargs` access. Doubles as a regression guard — if the spy was never awaited, the test was wrong.
- **Why it matters:** Every Phase 2 test asserting on `spy.await_args` (S1-07's `run_external_cli` tests, S5-02's `docker`/`strace` spawn assertions, etc.) needs the same `assert ... is not None` line. Family-precedent files get away without it because their mypy scope is older.

## L5 — Pytest collects any `Test*` class imported into a test file's namespace
- **Source:** S1-03 (`TestInventoryAdapter` raised `PytestCollectionWarning: cannot collect test class … has a __init__ constructor`).
- **Symptom:** Importing `TestInventoryAdapter` (or any `Test*`-named class) into `tests/**/*.py` warns at collection time even when no test instantiates it.
- **Fix:** **Alias on import in the test file** — `from codegenie.adapters import TestInventoryAdapter as InventoryAdapter`. Do **not** set `__test__ = False` on the Protocol class (either inside or after the body): on Python 3.11 (CI), assigning `__test__` post-class-body adds it to `_get_protocol_attrs`, breaking `isinstance` for any stub that doesn't declare `__test__`. CI was green on Python 3.13 (local) and red on Python 3.11 (CI) — the `_get_protocol_attrs` implementation diverges across minor versions.
- **Why it matters:** Any future domain type that begins with `Test` (e.g., `TestMatrix`, `TestSuiteId`) needs the import-alias fix in test files, not a runtime mutation of the source class. Setting `__test__` on a Protocol is a portability trap.
