# Story S1-01 — Pyproject scaffold + extras shape

**Step:** Step 1 — Establish project skeleton, tooling, and the `fence` CI job
**Status:** Ready
**Effort:** M
**Depends on:** —
**ADRs honored:** ADR-0006, ADR-0002, ADR-0010

## Context

This story lands the `pyproject.toml` that *every* subsequent story builds on. It pins Python `>=3.11`, the `hatchling` build backend, and — most consequentially — the **four-slot extras shape** (`gather` / `dev` / `service` / `agents`) that ADR-0006 designates as the structural separation the `fence` CI job (ADR-0002) will enforce in S1-05. The runtime `dependencies` list shipped here *is* the gather-pipeline closure that downstream phases must never contaminate with an LLM SDK.

This is foundational work: nothing else in Step 1 (toolchain config, Makefile, pre-commit, CI workflow, fence) can be authored until this file exists and the `src/codegenie/` package is importable.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Development view` — file layout under `src/codegenie/`; pyproject is the root-level config.
  - `../phase-arch-design.md §Component design — CLI` — `cli.py` is `click`-based and lazy-imports heavy modules; informs the runtime dep list.
  - `../phase-arch-design.md §Tradeoffs (consolidated)` — row "pydantic v2 in Phase 0" (Phase 0 ships pydantic in `dependencies`, not deferred); row "`aiofiles` removed from deps."
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0006-pyproject-toml-extras-shape.md` — ADR-0006 — four-slot extras shape; the `[gather]` extra is intentionally empty.
  - `../ADRs/0002-fence-ci-job-no-llm-in-gather.md` — ADR-0002 — runtime `dependencies` *is* the closure the fence guards; do not add LLM SDKs.
  - `../ADRs/0010-pydantic-probe-output-validator.md` — ADR-0010 — `pydantic>=2` belongs in runtime deps (lazy-imported), not deferred.
- **Source design:**
  - `../High-level-impl.md §Step 1` — "Features delivered" bullet for `pyproject.toml`; spells out exact deps in `dependencies` and in `dev`.
  - `../final-design.md §2.2` — Tooling and dependencies table.
- **External docs:**
  - https://packaging.python.org/en/latest/specifications/pyproject-toml/ — PEP 621 fields.
  - https://hatch.pypa.io/latest/version/ — `hatchling`'s version hook for reading `src/codegenie/version.py`.

## Goal

`pip install -e .` succeeds from a clean checkout, `python -c "import codegenie; print(codegenie.__version__)"` prints the version, and `python -m codegenie --help` returns exit code 0.

## Acceptance criteria

- [ ] `pyproject.toml` exists with `[build-system]` declaring `hatchling`, `[project]` declaring `name = "codewizard-sherpa"`, `requires-python = ">=3.11"`, and a `dynamic = ["version"]` entry tied to `src/codegenie/version.py` via `[tool.hatch.version]`.
- [ ] `[project.dependencies]` contains **exactly** `click`, `pyyaml`, `jsonschema>=4.21`, `pydantic>=2`, `blake3`, `structlog` — no LLM SDKs, no `aiofiles` (per ADR-0006 consequences and High-level-impl §Step 1 Features).
- [ ] `[project.optional-dependencies]` declares **all four** keys `gather` (empty list), `dev` (with `pytest`, `pytest-asyncio`, `pytest-cov`, `mypy`, `ruff`, `pre-commit`, `mkdocs-material`, `import-linter`, `pip-audit`), `service` (empty list), `agents` (empty list) per ADR-0006.
- [ ] `src/codegenie/__init__.py`, `src/codegenie/__main__.py`, and `src/codegenie/version.py` exist; `version.py` exposes a single `__version__: str` constant.
- [ ] The TDD red test exists at `tests/unit/test_packaging.py`, was committed at the red phase, and is green after implementation.
- [ ] `python -c "from importlib.metadata import distribution; print(sorted(r for r in distribution('codewizard-sherpa').requires or []))"` lists the runtime closure with **none of** `anthropic`, `langgraph`, `openai`, `langchain`, `transformers` (this is the structural property S1-05's fence test will codify).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/`, and `pytest tests/unit/test_packaging.py` all pass on the touched files.

## Implementation outline

1. Write the failing red test in `tests/unit/test_packaging.py` (see TDD plan below).
2. Create `src/codegenie/version.py` with `__version__ = "0.1.0"`.
3. Create `src/codegenie/__init__.py` that re-exports `__version__`.
4. Create `src/codegenie/__main__.py` as a thin entry point that imports a `main` callable from `codegenie.cli` *lazily* and calls it (placeholder `def main(argv=None): ...` is fine for this story — the full CLI lands in S4-02).
5. Write `pyproject.toml` per the acceptance criteria: PEP 621 `[project]`, `[build-system]` for `hatchling`, `[project.optional-dependencies]` with the four slots, `[tool.hatch.build.targets.wheel]` pointed at `src/codegenie`, `[tool.hatch.version]` pointed at `src/codegenie/version.py`.
6. Verify locally with `pip install -e .[dev]` and re-run the test.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_packaging.py`

```python
# tests/unit/test_packaging.py
from importlib.metadata import distribution, PackageNotFoundError


def test_package_distribution_is_installed() -> None:
    # arrange: the project has been installed editable via `pip install -e .`
    # act: query the metadata for our distribution name
    # assert: it resolves; this proves pyproject.toml's [project].name is correct
    try:
        dist = distribution("codewizard-sherpa")
    except PackageNotFoundError as exc:
        raise AssertionError(
            "pyproject.toml [project].name must be 'codewizard-sherpa'"
        ) from exc
    assert dist.metadata["Name"] == "codewizard-sherpa"


def test_runtime_dependencies_match_adr_0006() -> None:
    # arrange: ADR-0006 fixes the gather-pipeline runtime closure
    expected = {"click", "pyyaml", "jsonschema", "pydantic", "blake3", "structlog"}
    # act: read installed requires (strip version specifiers + extras markers)
    dist = distribution("codewizard-sherpa")
    raw = dist.requires or []
    names = {r.split(";")[0].split("[")[0].split(">")[0].split("=")[0].split("<")[0].strip().lower()
             for r in raw if "extra ==" not in r}
    # assert: the runtime closure exactly matches ADR-0006's table — no LLM SDKs, no aiofiles
    assert expected.issubset(names), f"missing runtime deps: {expected - names}"
    assert "aiofiles" not in names, "aiofiles removed per ADR-0006 / High-level-impl §Step 1"


def test_optional_dependencies_declare_four_slots() -> None:
    # arrange: ADR-0006 requires gather/dev/service/agents to ALL exist in Phase 0
    dist = distribution("codewizard-sherpa")
    raw = dist.requires or []
    extras = {r.split("extra ==")[1].strip(' "\'')
              for r in raw if "extra ==" in r}
    # assert: even though `gather`/`service`/`agents` are empty, their slot names
    # must be reachable so Phase 4+ adds LLM SDKs by *adding lines*, not by refactor.
    # We can detect declared-but-empty extras via the dist's metadata "Provides-Extra"
    provides_extra = {v for k, v in dist.metadata.items() if k == "Provides-Extra"}
    assert {"gather", "dev", "service", "agents"}.issubset(provides_extra)


def test_version_constant_is_importable() -> None:
    # arrange: version.py is the single source of truth (hatchling reads it)
    # act: import the package
    import codegenie

    # assert: __version__ exists and is a str
    assert isinstance(codegenie.__version__, str)
    assert codegenie.__version__  # not empty
```

The test fails before any implementation because (a) the distribution isn't installed, (b) `codegenie` is not importable, (c) no `__version__` attribute. Run `pytest tests/unit/test_packaging.py` — observe `ModuleNotFoundError: No module named 'codegenie'` or `PackageNotFoundError`. Commit the failing test as a red-phase marker.

### Green — make it pass

Minimum needed: create `src/codegenie/{version.py,__init__.py,__main__.py}` (each can be tiny — `__main__.py` may contain a `def main(argv=None): return 0` stub), write `pyproject.toml` with the four-slot extras shape and the `[tool.hatch.version]` hook pointing at `version.py`, then `pip install -e .[dev]`. Do **not** add any other dependency beyond what ADR-0006 names; resist completing tomorrow's work today.

### Refactor — clean up

- Add a module docstring to `version.py` explaining "single source of truth read by `pyproject.toml` via `hatchling`."
- Add type hints (`__version__: str = "0.1.0"`).
- Ensure files end with a final newline (the pre-commit `end-of-file-fixer` from S1-04 will catch this anyway).
- Make sure `__main__.py`'s `main(argv)` signature is the placeholder S4-02 will replace — no logic, just `return 0`.
- Confirm `mypy --strict src/codegenie/` is clean on the three files.

## Files to touch

| Path | Why |
|---|---|
| `pyproject.toml` | New file — PEP 621 `[project]`, `hatchling` build backend, four-slot extras per ADR-0006, runtime deps per High-level-impl §Step 1. |
| `src/codegenie/__init__.py` | New file — package marker; re-exports `__version__`. |
| `src/codegenie/__main__.py` | New file — `python -m codegenie` entry; placeholder `main()` for now. |
| `src/codegenie/version.py` | New file — `__version__: str` single source of truth; read by `hatchling`. |
| `tests/unit/test_packaging.py` | New file — TDD red anchor; pins ADR-0006's runtime closure and four-slot extras shape. |

## Out of scope

- **Ruff / mypy / pytest / coverage config blocks inside `pyproject.toml`** — handled by S1-02.
- **`Makefile` and `uv.lock`** — handled by S1-03.
- **`.pre-commit-config.yaml`, `.editorconfig`, `.gitignore`, `mkdocs.yml`** — handled by S1-04.
- **`.github/workflows/ci.yml` and the `fence` test** — handled by S1-05.
- **`src/codegenie/cli.py` with real `click` subcommands** — full CLI lands in S4-02. This story ships a placeholder `__main__.py` only.
- **`src/codegenie/errors.py` and `logging.py`** — handled by S2-01.
- **Any `src/codegenie/probes/`, `cache/`, `schema/` content** — handled by Step 2 and Step 3 stories.

## Notes for the implementer

- The `[gather]` extra is **intentionally empty** (ADR-0006 §Decision). Its existence is the semantic marker that `dependencies` *is* the gather closure; do not "tidy it up" by removing the empty entry.
- The four extras must all be declared as empty lists *in `pyproject.toml`* (so they appear as `Provides-Extra` in the distribution metadata). An empty TOML list `gather = []` is valid syntax.
- `pydantic>=2` (note the major-version pin) lands in `dependencies` per ADR-0010, not in `dev`. Best-practices lens wanted it deferred; the synthesis rejected that (L3 row 8). If you're tempted to demote it, re-read ADR-0010.
- `aiofiles` appears in `roadmap.md` §"Phase 0" — that's a known documentation bug per Tradeoffs row "`aiofiles` removed from deps." Do **not** add it. S5-02 files the doc-bug issue.
- The fence test in S1-05 will assert `set(distribution(...).requires) ∩ {anthropic, langgraph, openai, langchain, transformers} == set()`. Your job here is to make sure that intersection is already empty by not adding any LLM SDK; S1-05 codifies the rule.
- `hatchling`'s version hook needs `[tool.hatch.version]` with `path = "src/codegenie/version.py"`. The `version.py` file must contain a top-level assignment like `__version__ = "0.1.0"`; hatchling parses the file with AST, not Python execution.
- `mypy --strict` on a near-empty `__init__.py` is trivially clean. But `__main__.py`'s placeholder `main` must have a return type annotation (`def main(argv: list[str] | None = None) -> int:`) or strict mode will complain — set this expectation now so S4-02 inherits it.
