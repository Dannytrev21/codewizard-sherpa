from __future__ import annotations

import subprocess
import sys
from importlib.metadata import PackageNotFoundError, distribution

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet

LLM_SDKS = frozenset({"anthropic", "langgraph", "openai", "langchain", "transformers"})
RUNTIME_DEPS = frozenset(
    {"click", "pyyaml", "jsonschema", "pydantic", "blake3", "structlog"}
)
EMPTY_EXTRAS = frozenset({"gather", "service", "agents"})
DEV_FLOOR = frozenset(
    {
        "pytest",
        "pytest-asyncio",
        "pytest-cov",
        "mypy",
        "ruff",
        "pre-commit",
        "mkdocs-material",
    }
)


def _parse_requires() -> list[Requirement]:
    """Parse ``Requires-Dist`` entries into :class:`packaging.Requirement` objects.

    ``dist.requires`` returns the raw header values, including version specifiers
    and ``; extra == "..."`` markers. Stripping the specifier (as a naive
    implementation might) silently allows version regressions like
    ``pydantic>=1.10``.
    """
    dist = distribution("codewizard-sherpa")
    return [Requirement(r) for r in (dist.requires or [])]


def _runtime_requirements() -> list[Requirement]:
    """Requirements with NO ``extra == "..."`` marker — i.e. ``[project.dependencies]``."""
    return [r for r in _parse_requires() if "extra ==" not in str(r.marker or "")]


def _extra_requirements(extra: str) -> list[Requirement]:
    """Requirements tagged ``; extra == "<extra>"`` — i.e. an optional-dependencies slot."""
    return [
        r for r in _parse_requires() if f'extra == "{extra}"' in str(r.marker or "")
    ]


def test_package_distribution_is_installed() -> None:
    # AC-1: pip install -e . succeeded; `[project].name` is correct.
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
    assert "aiofiles" not in names, (
        "aiofiles removed per ADR-0006 / High-level-impl §Step 1"
    )


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
        f"{ {'gather', 'dev', 'service', 'agents'} - provides_extra }"
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
