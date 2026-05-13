# Story S1-01 — Pyproject scaffold + extras shape

**Step:** Step 1 — Establish project skeleton, tooling, and the `fence` CI job
**Status:** Ready (validated 2026-05-12 — HARDENED)
**Effort:** M
**Depends on:** —
**ADRs honored:** ADR-0006, ADR-0002, ADR-0010

## Validation notes

Validated: 2026-05-12
Verdict: HARDENED
Findings addressed: 13 (0 block, 11 harden, 2 nit) across Coverage / Test-Quality / Consistency critics.

Changes applied:
- AC-2 strengthened — added exact-set semantics, version-pin floors (`pydantic>=2`, `jsonschema>=4.21`), and explicit LLM SDK intersection.
- AC-3 restructured — split into structural slot invariants (four `Provides-Extra` slots; `gather`/`service`/`agents` empty by Requires-Dist count) plus a `dev` *floor* (must include the AC-7 toolchain) rather than a brittle exact list that conflicts across `final-design.md §2.2` and `High-level-impl.md §Step 1`.
- AC-6 promoted to a TDD-tested assertion (was: manual `python -c`). The LLM SDK intersection is now executable in this story, not deferred to S1-05.
- AC-8 added — `python -m codegenie --help` returns exit code 0 (goal coverage; was untested).
- AC-9 added — `distribution.metadata["Version"]` equals `codegenie.__version__` (hatchling dynamic-version hook coherence; was untested — a static `version = "0.0.1"` in pyproject combined with `__version__ = "0.1.0"` would have passed every original test).
- TDD Test 2 hardened — exact-set equality (not subset), version specifier assertions, LLM SDK intersection assertion, and `get_all("Provides-Extra")` idiom for `Provides-Extra` extraction (replaces fragile `dict.items()` loop on a multi-valued `Message` header).
- TDD Test 3 hardened — asserts `gather`/`service`/`agents` have **zero** `Requires-Dist` entries (was: only checked that slot names appear).
- TDD Test 5 added — `python -m codegenie --help` subprocess smoke covering AC-8.
- TDD Test 6 added — version-hook coherence covering AC-9.
- Implementation outline version pin: `0.0.1` (was `0.1.0`) — resolves the conflict with `final-design.md §2.2`'s example pyproject block; the dynamic-version hook makes this load-bearing.

Conflict resolutions:
- Dev-extras list: `final-design.md §2.2`, `High-level-impl.md §Step 1`, and the original story all listed different `dev` sets. **Consistency wins, but no source is canonical for this slot's full contents.** Resolution: AC-3 no longer enforces an exact dev list — only the AC-7 toolchain floor — and downstream stories (S1-02 ruff/mypy/pytest, S1-04 pre-commit/mkdocs, S1-05 CI security scanners) add their own entries via extension. Note for the executor: ship at least the union of AC-7's tools + `pre-commit` + `mkdocs-material` so S1-04 / S1-05 don't have to retro-add core tooling.

Full audit log: [`_validation/S1-01-pyproject-scaffold.md`](_validation/S1-01-pyproject-scaffold.md)

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

- [ ] AC-1: `pyproject.toml` exists with `[build-system]` declaring `hatchling`, `[project]` declaring `name = "codewizard-sherpa"`, `requires-python = ">=3.11"`, and a `dynamic = ["version"]` entry tied to `src/codegenie/version.py` via `[tool.hatch.version]`.
- [ ] AC-2: the parsed set of `[project.dependencies]` distribution names equals **exactly** `{click, pyyaml, jsonschema, pydantic, blake3, structlog}` (neither superset nor subset — no LLM SDKs, no `aiofiles`, no `requests`/`httpx`/etc.). The raw `Requires-Dist` entries for `jsonschema` and `pydantic` MUST carry the version specifiers `>=4.21` and `>=2` respectively (verified by parsing the version specifier from `Requires-Dist` — not stripping it). (validator: hardened from original "exactly … no LLM SDKs, no aiofiles" — original test used `issubset` so adding an extra dep slipped through, and stripped specifiers so `pydantic>=1.10` would have passed.)
- [ ] AC-3: `[project.optional-dependencies]` declares **all four** keys `gather`, `dev`, `service`, `agents` — verifiable by `dist.metadata.get_all("Provides-Extra") == ` superset of `{gather, dev, service, agents}`. Additionally, the count of `Requires-Dist` entries marked `; extra == "gather"`, `; extra == "service"`, and `; extra == "agents"` MUST each be **zero** (these slots are intentionally empty per ADR-0006 §Decision). `dev` MUST at minimum include the AC-7 toolchain (`pytest`, `pytest-asyncio`, `pytest-cov`, `mypy`, `ruff`) plus `pre-commit` and `mkdocs-material` so S1-04/S1-05 inherit a working harness; additional `dev` entries (e.g., `import-linter`, `pip-audit`, `osv-scanner`, `bandit`) are allowed but not enforced by this story (S1-04 and S1-05 own those). (validator: original AC enumerated a specific dev list that conflicts across `final-design.md §2.2` and `High-level-impl.md §Step 1`; relaxed to structural invariants + a floor — see Validation notes "Conflict resolutions".)
- [ ] AC-4: `src/codegenie/__init__.py`, `src/codegenie/__main__.py`, and `src/codegenie/version.py` exist; `version.py` exposes a single `__version__: str` constant declared as a *top-level assignment* (so `hatchling`'s AST-based version hook can parse it without executing the file).
- [ ] AC-5: The TDD red test exists at `tests/unit/test_packaging.py`, was committed at the red phase (verifiable in git history as a commit where the test exists but `src/codegenie/` does not), and is green after implementation.
- [ ] AC-6: `set(parsed_runtime_dependency_names) ∩ {anthropic, langgraph, openai, langchain, transformers} == set()` — this is a load-bearing commitment from `CLAUDE.md` §"No LLM anywhere in the gather pipeline" and [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md). **Asserted by a test in this story's TDD plan** (Test 2 below), not deferred to S1-05; S1-05 codifies a dedicated fence test with a deliberate-negative case but the structural property is verified here as well. (validator: original AC was a manual `python -c` invocation, not an executable assertion — promoted to TDD plan.)
- [ ] AC-7: `ruff check src/ tests/`, `ruff format --check src/ tests/`, `mypy --strict src/codegenie/`, and `pytest tests/unit/test_packaging.py -q` all exit with code 0 on the files this story touches. (Note: configuration for these tools lands in S1-02; this story relies only on CLI defaults, which are sufficient because the source files are deliberately near-empty.)
- [ ] AC-8: `python -m codegenie --help` returns exit code 0 and writes non-empty bytes to stdout. (validator: added — the story's stated goal includes "`python -m codegenie --help` returns exit code 0" but no original AC/test covered it; a `__main__.py` that raised `NotImplementedError` would have passed every original test.)
- [ ] AC-9: `importlib.metadata.distribution("codewizard-sherpa").metadata["Version"]` equals `codegenie.__version__` — proves that `hatchling`'s `[tool.hatch.version]` hook is actually reading `version.py` (not a static literal in `pyproject.toml`). (validator: added — without this, a regression that statically pins `version = "0.0.1"` in `pyproject.toml` while `__version__ = "0.1.0"` lives in `version.py` ships unnoticed; the version-hook is exactly the kind of single-source-of-truth invariant a packaging-scaffold story must lock down.)

## Implementation outline

1. Write the failing red test in `tests/unit/test_packaging.py` (see TDD plan below).
2. Create `src/codegenie/version.py` with `__version__ = "0.0.1"` (top-level assignment so hatchling's AST hook reads it; matches `final-design.md §2.2`'s example pyproject block — the dynamic-version hook makes this load-bearing under AC-9).
3. Create `src/codegenie/__init__.py` that re-exports `__version__`.
4. Create `src/codegenie/__main__.py` as a thin entry point that imports a `main` callable from `codegenie.cli` *lazily* and calls it (placeholder `def main(argv=None): ...` is fine for this story — the full CLI lands in S4-02).
5. Write `pyproject.toml` per the acceptance criteria: PEP 621 `[project]`, `[build-system]` for `hatchling`, `[project.optional-dependencies]` with the four slots, `[tool.hatch.build.targets.wheel]` pointed at `src/codegenie`, `[tool.hatch.version]` pointed at `src/codegenie/version.py`.
6. Verify locally with `pip install -e .[dev]` and re-run the test.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_packaging.py`

```python
# tests/unit/test_packaging.py
from __future__ import annotations

import subprocess
import sys
from importlib.metadata import PackageNotFoundError, distribution

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet

LLM_SDKS = frozenset({"anthropic", "langgraph", "openai", "langchain", "transformers"})
RUNTIME_DEPS = frozenset({"click", "pyyaml", "jsonschema", "pydantic", "blake3", "structlog"})
EMPTY_EXTRAS = frozenset({"gather", "service", "agents"})
DEV_FLOOR = frozenset({"pytest", "pytest-asyncio", "pytest-cov", "mypy", "ruff",
                       "pre-commit", "mkdocs-material"})


def _parse_requires() -> list[Requirement]:
    """Parse `Requires-Dist` entries into `packaging.Requirement` objects.

    `dist.requires` returns the raw header values, including version specifiers
    and `; extra == "..."` markers. Stripping the specifier (as the original
    test did) silently allows version regressions like `pydantic>=1.10`.
    """
    dist = distribution("codewizard-sherpa")
    return [Requirement(r) for r in (dist.requires or [])]


def _runtime_requirements() -> list[Requirement]:
    """Requirements with NO `extra == "..."` marker — i.e. `[project.dependencies]`."""
    return [r for r in _parse_requires() if "extra ==" not in str(r.marker or "")]


def _extra_requirements(extra: str) -> list[Requirement]:
    """Requirements tagged `; extra == "<extra>"` — i.e. `[project.optional-dependencies.<extra>]`."""
    return [r for r in _parse_requires() if f'extra == "{extra}"' in str(r.marker or "")]


def test_package_distribution_is_installed() -> None:
    # AC-1: pip install -e . succeeded; `[project].name` is correct
    try:
        dist = distribution("codewizard-sherpa")
    except PackageNotFoundError as exc:  # pragma: no cover — pre-install state
        raise AssertionError(
            "pyproject.toml [project].name must be 'codewizard-sherpa' and the "
            "package must be installed (`pip install -e .[dev]`)"
        ) from exc
    assert dist.metadata["Name"] == "codewizard-sherpa"


def test_runtime_dependencies_are_exactly_adr_0006_closure() -> None:
    # AC-2 / AC-6: the runtime closure is EXACTLY ADR-0006's set — no extras, no LLM SDKs.
    runtime = _runtime_requirements()
    names = {r.name.lower() for r in runtime}

    # Equality (mutation-resistant): a lazy impl adding `requests` would fail here.
    assert names == RUNTIME_DEPS, (
        f"runtime closure mismatch:\n  unexpected: {names - RUNTIME_DEPS}\n  "
        f"missing: {RUNTIME_DEPS - names}\n"
        f"(ADR-0006 §Decision pins the closure; only S1-05's fence may widen the intersection set)"
    )

    # AC-6: load-bearing — the intersection with LLM SDKs must be empty.
    assert names & LLM_SDKS == set(), (
        f"LLM SDK in gather closure: {names & LLM_SDKS} — violates ADR-0002 / "
        f"production ADR-0005 / CLAUDE.md §'No LLM anywhere in the gather pipeline'"
    )
    assert "aiofiles" not in names, "aiofiles removed per ADR-0006 / High-level-impl §Step 1"


def test_runtime_dependencies_carry_required_version_specifiers() -> None:
    # AC-2: `jsonschema>=4.21` and `pydantic>=2` are pinned by ADR-0010 / High-level-impl §Step 1.
    by_name = {r.name.lower(): r.specifier for r in _runtime_requirements()}

    pydantic_spec: SpecifierSet = by_name["pydantic"]
    jsonschema_spec: SpecifierSet = by_name["jsonschema"]

    # Mutation-resistant: a regression to `pydantic>=1.10` falsifies "2.0.0" ∈ spec
    # while still satisfying "2.7.0"; we check the LOWER bound explicitly.
    assert "2.0.0" in pydantic_spec, (
        f"pydantic requires `>=2` per ADR-0010; got specifier {pydantic_spec}"
    )
    assert "1.99.0" not in pydantic_spec, (
        f"pydantic must reject 1.x per ADR-0010; got specifier {pydantic_spec}"
    )
    assert "4.21.0" in jsonschema_spec, (
        f"jsonschema requires `>=4.21` per High-level-impl §Step 1; got {jsonschema_spec}"
    )
    assert "4.20.0" not in jsonschema_spec, (
        f"jsonschema must reject <4.21 per High-level-impl §Step 1; got {jsonschema_spec}"
    )


def test_optional_dependencies_declare_four_slots_and_empties_are_empty() -> None:
    # AC-3: four `Provides-Extra` slots exist AND the three "reserved-empty" slots
    # are LITERALLY empty (no Requires-Dist entries tagged with that extra).
    dist = distribution("codewizard-sherpa")
    provides_extra = set(dist.metadata.get_all("Provides-Extra") or [])
    assert {"gather", "dev", "service", "agents"}.issubset(provides_extra), (
        f"missing Provides-Extra slots: "
        f"{ {'gather', 'dev', 'service', 'agents'} - provides_extra}"
    )

    # Mutation-resistant: a lazy impl that put `pyyaml` under `[gather]` would fail here.
    for extra in EMPTY_EXTRAS:
        entries = _extra_requirements(extra)
        assert entries == [], (
            f"extra `{extra}` must be empty per ADR-0006 §Decision "
            f"(its existence is the slot marker; the closure is [project.dependencies]); "
            f"found: {[str(r) for r in entries]}"
        )


def test_dev_extra_contains_ac_7_toolchain_floor() -> None:
    # AC-3: dev MUST at minimum contain the AC-7 toolchain + pre-commit + mkdocs-material.
    dev_names = {r.name.lower() for r in _extra_requirements("dev")}
    missing = DEV_FLOOR - dev_names
    assert missing == set(), (
        f"dev extra is missing the toolchain floor: {missing}. "
        f"AC-7 invokes ruff/mypy/pytest; S1-04 needs pre-commit; "
        f"S1-04's `mkdocs build --strict` needs mkdocs-material."
    )


def test_version_constant_is_importable() -> None:
    # AC-4: __version__ is importable and is a non-empty str.
    import codegenie

    assert isinstance(codegenie.__version__, str), (
        f"codegenie.__version__ must be a str (hatchling parses version.py by AST); "
        f"got type {type(codegenie.__version__).__name__}"
    )
    assert codegenie.__version__, "codegenie.__version__ must not be empty"


def test_distribution_version_matches_package_version() -> None:
    # AC-9: hatchling's [tool.hatch.version] hook must read src/codegenie/version.py.
    # Mutation-resistant: a static `version = "0.0.1"` in pyproject combined with
    # `__version__ = "0.1.0"` in version.py would slip past every other test.
    import codegenie

    dist_version = distribution("codewizard-sherpa").metadata["Version"]
    assert dist_version == codegenie.__version__, (
        f"distribution version `{dist_version}` != codegenie.__version__ "
        f"`{codegenie.__version__}` — hatchling's [tool.hatch.version] hook is "
        f"not reading src/codegenie/version.py (or a static `version =` slipped "
        f"into [project])"
    )


def test_python_dash_m_codegenie_help_returns_zero() -> None:
    # AC-8: goal coverage — `python -m codegenie --help` exits 0 with non-empty stdout.
    result = subprocess.run(
        [sys.executable, "-m", "codegenie", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, (
        f"`python -m codegenie --help` exited {result.returncode}; "
        f"stderr={result.stderr!r}"
    )
    assert result.stdout, "expected non-empty --help output"
```

The test fails before any implementation because (a) the distribution isn't installed, (b) `codegenie` is not importable, (c) no `__version__` attribute, (d) no `__main__.py` for the `python -m` smoke. Run `pytest tests/unit/test_packaging.py` — observe `ModuleNotFoundError: No module named 'codegenie'` or `PackageNotFoundError`. Commit the failing test as a red-phase marker.

Note for the implementer: the test imports `packaging.requirements.Requirement` and `packaging.specifiers.SpecifierSet`. `packaging` is a transitive dependency of `pip` / `pytest`'s ecosystem and will already be installed in the dev environment; no need to add it to `dev` extras.

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
