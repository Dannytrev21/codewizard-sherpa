"""``TestInventoryProbe`` — Layer A, base-tier (S4-03).

Populates the ``test_inventory`` slice (``localv2.md §5.1 A6``) by
enumerating which test framework the repo uses, counting test files,
capturing canonical test-script names from ``package.json#scripts``,
detecting smoke-test scripts, and parsing ``coverage/lcov.info`` (if
present) for line/function/branch totals.

Three load-bearing commitments concentrate here:

1. **The lcov scanner has no regex backtracking.** ``coverage/lcov.info``
   is attacker-controllable bytes; a regex with ``.*`` over crafted input
   is an OOM/CPU-DoS vector. The arch's prescription — 40-LOC stdlib
   state-machine line scanner, 50 MB cap, no regex — lives in
   :mod:`codegenie.probes._lcov_scanner` and is structurally enforced by
   AST-walk tests.
2. **``unit_test_count_is_file_count: True`` is a permanent contract
   flag, not a placeholder.** Phase 1 counts test *files*, not test
   *cases* (counting cases requires the framework's runner — out of
   scope per ADR-0011). Phase 2+ may add ``unit_test_case_count: int |
   null`` additively without breaking the file-count semantics.
3. **``node:test`` requires ``engines.node >= 18`` AND no other
   framework declared.** Avoids false positives on repos that target
   Node 20 but use vitest. Strictly-conservative: any unparseable
   constraint is treated as < 18.

**Open/Closed at the file boundary** — five module-level seams:

- ``_FRAMEWORK_DETECTORS``: precedence-ordered tuple of unit-test
  framework names. Adding a future framework (``uvu``, ``bun:test``)
  is one tuple-entry insertion + one schema-enum bump + one fixture
  row; zero edits to selection logic.
- ``_E2E_FRAMEWORK_DETECTORS``: separate tuple for E2E frameworks.
  ``framework`` and ``e2e_framework`` are orthogonal axes (CN-1 /
  arch line 756) — a repo with jest + playwright populates BOTH.
- ``_CANONICAL_SCRIPT_NAMES``: closed list of recognized
  ``package.json#scripts`` keys.
- ``_TEST_FILE_PATTERNS``: closed list of test-file suffixes.
- ``_SMOKE_PATH_PRECEDENCE``: precedence-ordered tuple for smoke-
  entrypoint detection. First ``Path.exists()`` hit wins.

**Compile-time discipline (Rule 12).** ``_WARNING_IDS`` and
``_ERROR_IDS`` are module-level frozensets pattern-checked against
ADR-0007 at import time; a typo'd ID refuses to load the module rather
than slipping into a slice.

**``coverage_data`` always emitted (CN-2).** When the probe runs, the
field is always a ``CoverageBlock``: ``(present=False, parse_error=False,
totals=None)`` for absent files; ``(present=True, parse_error=False,
totals=...)`` for parsed-OK files; ``(present=True, parse_error=True,
totals=None)`` for parse failures. The Python ``None`` arm is the
unreachable-in-Phase-1 escape hatch reserved for the didn't-run case.

Sources:

- ``docs/phases/01-context-gather-layer-a-node/stories/S4-03-test-inventory-probe.md``
- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Component design" #7; §"Data model" TestInventorySlice
- ``docs/phases/01-context-gather-layer-a-node/ADRs/`` —
  ``0002-parsed-manifest-memo-on-probe-context.md`` (memo seam),
  ``0004-per-probe-subschema-additional-properties-false.md`` (slice strict),
  ``0007-warnings-id-pattern.md`` (ID pattern),
  ``0009-no-new-c-extension-parser-dependencies.md`` (no lcov-parse),
  ``0010-layer-a-slices-optional-at-envelope.md`` (slice optional).
- ``docs/production/adrs/0005-no-llm-in-gather-pipeline.md`` —
  ``commands`` recorded verbatim, never evaluated.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Mapping, Set
from pathlib import Path
from typing import Any, Final, Literal, TypeAlias, TypedDict

import structlog

from codegenie.errors import (
    MalformedJSONError,
    SizeCapExceeded,
    SymlinkRefusedError,
)
from codegenie.logging import (
    EVENT_PROBE_FAILURE,
    EVENT_PROBE_START,
    EVENT_PROBE_SUCCESS,
)
from codegenie.parsers import safe_json
from codegenie.probes._lcov_scanner import LcovTotals, scan as _lcov_scan
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.language_detection import _SKIP_DIRS as _NOISE_DIRS
from codegenie.probes.registry import register_probe

__all__ = ["TestInventoryProbe"]


_log = structlog.get_logger(__name__)


# --- module-level Open/Closed seams -----------------------------------------


FrameworkName: TypeAlias = Literal["vitest", "jest", "mocha", "tap", "node_test"]
E2EFrameworkName: TypeAlias = Literal["playwright", "cypress"]


# Precedence-ordered tuple of unit-test framework names. Adding a future
# framework (``uvu``, ``bun:test``) is one tuple-entry insertion + one
# schema-enum bump + one fixture row; zero edits to ``_select_framework``.
# Alpha order is the synthesis (matches ``_BUNDLERS_SORTED`` in
# ``node_build_system.py``).
_FRAMEWORK_DETECTORS: Final[tuple[FrameworkName, ...]] = (
    "vitest",
    "jest",
    "mocha",
    "tap",
)


# Separate tuple for E2E frameworks (CN-1 / arch line 756). ``framework``
# and ``e2e_framework`` are orthogonal axes; a repo with both jest and
# playwright populates BOTH fields. Alpha-precedence within E2E.
_E2E_FRAMEWORK_DETECTORS: Final[tuple[E2EFrameworkName, ...]] = (
    "playwright",
    "cypress",
)


# Map from E2E framework name → its dep-name in package.json. The unit-
# test detectors share name == dep-name; E2E does not (``playwright``
# the framework lives under the ``@playwright/test`` package).
_E2E_DEP_NAMES: Final[Mapping[E2EFrameworkName, str]] = {
    "playwright": "@playwright/test",
    "cypress": "cypress",
}


_CANONICAL_SCRIPT_NAMES: Final[tuple[str, ...]] = (
    "test",
    "test:unit",
    "test:integration",
    "test:smoke",
    "test:e2e",
    "test:coverage",
)


# File-suffix patterns for unit-test file counting. Closed; adding a new
# extension is one entry. The set covers ``.test.*`` and ``.spec.*``
# across the six recognized JS/TS extensions.
_TEST_FILE_PATTERNS: Final[tuple[str, ...]] = (
    ".test.js",
    ".test.jsx",
    ".test.ts",
    ".test.tsx",
    ".test.mjs",
    ".test.cjs",
    ".spec.js",
    ".spec.jsx",
    ".spec.ts",
    ".spec.tsx",
    ".spec.mjs",
    ".spec.cjs",
)


# Precedence-ordered smoke entrypoint detection. First match wins via
# ``Path.exists()``. Files take precedence over directories.
_SMOKE_PATH_PRECEDENCE: Final[tuple[str, ...]] = (
    "scripts/smoke.sh",
    "scripts/smoke.js",
    "scripts/smoke.ts",
    "tests/smoke",
)


_WARNING_IDS: Final[frozenset[str]] = frozenset(
    {
        "coverage.lcov_parse_error",
        "coverage.size_cap_exceeded",
        "test_framework.ambiguous",
        "e2e_framework.ambiguous",
    }
)


_ERROR_IDS: Final[frozenset[str]] = frozenset(
    {
        "package_json.size_cap_exceeded",
        "package_json.malformed",
        "package_json.symlink_refused",
    }
)


# Map typed parser exception → error ID for ``package.json`` failures.
# Routed to ``ProbeOutput.errors`` (NOT ``slice["warnings"]``) per the
# established errors-vs-warnings discipline (ADR-0007 line 50).
_PKG_JSON_FAILURE: Final[Mapping[type[Exception], str]] = {
    SizeCapExceeded: "package_json.size_cap_exceeded",
    MalformedJSONError: "package_json.malformed",
    SymlinkRefusedError: "package_json.symlink_refused",
}


_PARSE_MAX_BYTES: Final[int] = 5 * 1024 * 1024
_PARSE_MAX_DEPTH: Final[int] = 64


# --- compile-time discipline (Rule 12) --------------------------------------


_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")

for _id in (*_WARNING_IDS, *_ERROR_IDS):
    assert _ID_PATTERN.match(_id), f"ADR-0007 violation: {_id!r}"

assert _FRAMEWORK_DETECTORS[0] == "vitest", (
    "S4-03 _FRAMEWORK_DETECTORS: 'vitest' must be the highest-precedence entry "
    f"(got {_FRAMEWORK_DETECTORS[0]!r})"
)

assert _E2E_FRAMEWORK_DETECTORS == ("playwright", "cypress"), (
    "S4-03 _E2E_FRAMEWORK_DETECTORS drift: expected ('playwright','cypress'), "
    f"got {_E2E_FRAMEWORK_DETECTORS!r}"
)

for _eid in _PKG_JSON_FAILURE.values():
    assert _eid in _ERROR_IDS, f"_PKG_JSON_FAILURE drift: {_eid!r} not in _ERROR_IDS"


# --- coverage block typed shape ---------------------------------------------


class CoverageBlock(TypedDict):
    """Strict ``additionalProperties: false`` shape for ``coverage_data``.

    Always emitted (never the Python ``None``) when the probe ran.
    Four-state matrix:

    - file absent      → ``present=False, parse_error=False, totals=None``
    - file parsed OK   → ``present=True,  parse_error=False, totals=LcovTotals(...)``
    - size cap exceeded → ``present=True, parse_error=True,  totals=None``
    - other parse fail → ``present=True,  parse_error=True,  totals=None``
    """

    present: bool
    parse_error: bool
    totals: dict[str, int] | None


# --- pure helpers (functional core, AC-50) ---------------------------------


def _engines_at_least(constraint: str | None, major: int) -> bool:
    """Conservatively decide whether ``constraint`` admits ``>= major``.

    Accepts the three lower-bound semver operators (``>=``, ``^``, ``~``)
    and parses the leading major integer. Any other operator (``<``,
    ``=``, ``*``, ``||`` ranges) or unparseable garbage returns ``False``
    — strictly conservative per AC-11; ``node:test`` must NOT be
    reported on ambiguous declarations.

    >>> _engines_at_least(">=18", 18)
    True
    >>> _engines_at_least(">=16", 18)
    False
    >>> _engines_at_least("^20", 18)
    True
    >>> _engines_at_least("garbage", 18)
    False
    """
    if not constraint:
        return False
    s = constraint.strip()
    if not s:
        return False
    rest: str
    if s.startswith(">="):
        rest = s[2:]
    elif s[0] in "^~":
        rest = s[1:]
    else:
        return False
    rest = rest.lstrip()
    digit_end = 0
    while digit_end < len(rest) and rest[digit_end].isdigit():
        digit_end += 1
    if digit_end == 0:
        return False
    try:
        parsed_major = int(rest[:digit_end])
    except ValueError:
        return False
    return parsed_major >= major


def _select_framework(deps: Set[str]) -> tuple[FrameworkName | None, bool]:
    """Return ``(framework, ambiguous)`` from ``deps``.

    Walks ``_FRAMEWORK_DETECTORS`` in precedence order. The first hit
    wins; ``ambiguous`` is ``True`` iff more than one detector matched.
    """
    hits = [name for name in _FRAMEWORK_DETECTORS if name in deps]
    if not hits:
        return None, False
    return hits[0], len(hits) > 1


def _select_e2e_framework(deps: Set[str]) -> tuple[E2EFrameworkName | None, bool]:
    """Return ``(e2e_framework, ambiguous)`` from ``deps``.

    Walks ``_E2E_FRAMEWORK_DETECTORS`` in precedence order, looking up
    each framework's dep-name via ``_E2E_DEP_NAMES``.
    """
    hits = [name for name in _E2E_FRAMEWORK_DETECTORS if _E2E_DEP_NAMES[name] in deps]
    if not hits:
        return None, False
    return hits[0], len(hits) > 1


def _count_test_files(root: Path) -> int:
    """Single ``os.walk`` test-file count, deterministic + noise-dir-excluded.

    ``dirs`` is mutated in-place to (a) drop entries in ``_NOISE_DIRS``
    and (b) sort the survivors so iteration order is stable across
    filesystems. Files are sorted before counting for the same reason.
    """
    count = 0
    for current, dirs, files in os.walk(root, topdown=True):
        # In-place mutation pattern: filter then sort. Both required;
        # sorting alone leaves noise-dirs in the recursion frontier.
        dirs[:] = sorted(d for d in dirs if d not in _NOISE_DIRS)
        for fname in sorted(files):
            for pat in _TEST_FILE_PATTERNS:
                if fname.endswith(pat):
                    count += 1
                    break
        # 'current' is unused; iterating is the side-effect we want.
        _ = current
    return count


def _select_smoke_path(root: Path) -> str | None:
    """First-match in ``_SMOKE_PATH_PRECEDENCE``; POSIX repo-relative.

    Returns the precedence string verbatim (already POSIX, no leading
    ``./``, no absolute paths). ``None`` when no entry matches.
    """
    for candidate in _SMOKE_PATH_PRECEDENCE:
        path = root / candidate
        if path.exists():
            return candidate
    return None


def _extract_canonical_scripts(parsed_pkg: Mapping[str, Any]) -> dict[str, str]:
    """Extract ``parsed_pkg["scripts"]`` filtered to ``_CANONICAL_SCRIPT_NAMES``.

    Returns an alpha-sorted dict (insertion order is the sort order).
    Non-string values silently skipped; non-canonical keys silently
    skipped. Verbatim — never evaluated (production ADR-0005).
    """
    scripts_obj = parsed_pkg.get("scripts")
    if not isinstance(scripts_obj, dict):
        return {}
    out: dict[str, str] = {}
    for key in sorted(_CANONICAL_SCRIPT_NAMES):
        if key in scripts_obj:
            value = scripts_obj[key]
            if isinstance(value, str):
                out[key] = value
    return out


def _classify_node_test(
    parsed_pkg: Mapping[str, Any], framework: FrameworkName | None
) -> tuple[FrameworkName | None, list[str]]:
    """Apply the ``node:test`` precedence rule.

    Returns ``(framework, warnings)``. If a framework is already
    selected, returns it unchanged (explicit-framework-wins per AC-10).
    Otherwise checks ``engines.node >= 18``; if so, returns
    ``("node_test", [])``; else ``(None, [])``.
    """
    if framework is not None:
        return framework, []
    engines = parsed_pkg.get("engines")
    if isinstance(engines, dict):
        node_constraint = engines.get("node")
        if isinstance(node_constraint, str) and _engines_at_least(node_constraint, 18):
            return "node_test", []
    return None, []


# --- coverage helpers (imperative-shell adapters) --------------------------


def _read_coverage_block(root: Path) -> tuple[CoverageBlock, list[str]]:
    """Read ``coverage/lcov.info`` into a :class:`CoverageBlock` + warnings.

    Always returns a ``CoverageBlock`` (never ``None``) when the probe
    ran. Four-state matrix per CN-2:

    - File absent → ``(present=False, parse_error=False, totals=None)``, no warnings.
    - Parsed OK → ``(present=True, parse_error=False, totals=...)``, no warnings.
    - ``SizeCapExceeded`` → ``(present=True, parse_error=True, totals=None)``,
      ``coverage.size_cap_exceeded`` warning.
    - Other parse error → ``(present=True, parse_error=True, totals=None)``,
      ``coverage.lcov_parse_error`` warning.
    """
    path = root / "coverage" / "lcov.info"
    # ``Path.exists()`` follows symlinks; symlinked lcov targets a real
    # file, so ``exists()`` is True. ``Path.is_symlink()`` discriminates
    # the symlink case for the four-state matrix.
    is_symlink = path.is_symlink()
    if not is_symlink and not path.exists():
        return CoverageBlock(present=False, parse_error=False, totals=None), []
    try:
        totals: LcovTotals = _lcov_scan(path)
    except SizeCapExceeded:
        return (
            CoverageBlock(present=True, parse_error=True, totals=None),
            ["coverage.size_cap_exceeded"],
        )
    except (SymlinkRefusedError, OSError, UnicodeDecodeError):
        return (
            CoverageBlock(present=True, parse_error=True, totals=None),
            ["coverage.lcov_parse_error"],
        )
    return (
        CoverageBlock(
            present=True,
            parse_error=False,
            totals={
                "lines_found": totals.lines_found,
                "lines_hit": totals.lines_hit,
                "functions_found": totals.functions_found,
                "functions_hit": totals.functions_hit,
                "branches_found": totals.branches_found,
                "branches_hit": totals.branches_hit,
            },
        ),
        [],
    )


def _minimal_slice() -> dict[str, Any]:
    """Slice payload returned when ``package.json`` parse fails.

    Per CN-4: the probe still emits a slice (with no detected framework
    and zero counts) so downstream consumers never see a missing-key
    surprise; the structured error rides on ``ProbeOutput.errors``.
    """
    return {
        "framework": None,
        "e2e_framework": None,
        "unit_test_file_count": 0,
        "unit_test_count_is_file_count": True,
        "commands": {},
        "smoke_test_path": None,
        "coverage_data": {
            "present": False,
            "parse_error": False,
            "totals": None,
        },
        "warnings": [],
    }


# --- the probe --------------------------------------------------------------


@register_probe
class TestInventoryProbe(Probe):
    """Layer A — test framework, file counts, canonical scripts, coverage totals."""

    name: str = "test_inventory"
    version: str = "0.1.0"
    layer = "A"
    tier = "base"
    applies_to_languages: list[str] = ["javascript", "typescript"]
    applies_to_tasks: list[str] = ["*"]
    requires: list[str] = ["language_detection", "node_build_system"]
    timeout_seconds: int = 10
    declared_inputs: list[str] = [
        "package.json",
        "vitest.config.*",
        "jest.config.*",
        "playwright.config.*",
        ".mocharc.*",
        "test/**/*.test.*",
        "tests/**/*.test.*",
        "src/**/*.test.*",
        "**/*.spec.*",
        "coverage/lcov.info",
        "scripts/smoke.*",
        "tests/smoke/**/*",
    ]

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        _log.info(EVENT_PROBE_START, probe=self.name)
        t0 = time.perf_counter()
        warnings: list[str] = []
        errors: list[str] = []

        # --- (1) package.json via memo (ADR-0002) -----------------------
        pkg_path = repo.root / "package.json"
        pkg: Mapping[str, Any] | None = None
        if pkg_path.exists() or pkg_path.is_symlink():
            try:
                if ctx.parsed_manifest is not None:
                    pkg = ctx.parsed_manifest(pkg_path)
                else:
                    pkg = safe_json.load(
                        pkg_path,
                        max_bytes=_PARSE_MAX_BYTES,
                        max_depth=_PARSE_MAX_DEPTH,
                    )
            except (SizeCapExceeded, MalformedJSONError, SymlinkRefusedError) as exc:
                error_id = _PKG_JSON_FAILURE[type(exc)]
                assert error_id in _ERROR_IDS  # Rule 12 — fail loud
                errors.append(error_id)
                duration_ms = max(0, int((time.perf_counter() - t0) * 1000))
                _log.info(
                    EVENT_PROBE_FAILURE,
                    probe=self.name,
                    error=type(exc).__name__,
                    error_id=error_id,
                )
                return ProbeOutput(
                    schema_slice={"test_inventory": _minimal_slice()},
                    raw_artifacts=[],
                    confidence="low",
                    duration_ms=duration_ms,
                    warnings=[],
                    errors=errors,
                )

        pkg = pkg or {}
        assert isinstance(pkg, Mapping)

        # --- (2) framework detection (unit + E2E orthogonal) ------------
        deps_obj_a = pkg.get("dependencies", {})
        deps_obj_b = pkg.get("devDependencies", {})
        all_deps: set[str] = set()
        if isinstance(deps_obj_a, dict):
            all_deps.update(k for k in deps_obj_a if isinstance(k, str))
        if isinstance(deps_obj_b, dict):
            all_deps.update(k for k in deps_obj_b if isinstance(k, str))

        framework, fw_ambiguous = _select_framework(all_deps)
        if fw_ambiguous:
            self._warn(warnings, "test_framework.ambiguous")

        e2e_framework, e2e_ambiguous = _select_e2e_framework(all_deps)
        if e2e_ambiguous:
            self._warn(warnings, "e2e_framework.ambiguous")

        # node:test rule (explicit framework wins)
        framework, node_test_warns = _classify_node_test(pkg, framework)
        for w in node_test_warns:
            self._warn(warnings, w)

        # --- (3) test-file count + canonical scripts + smoke path -------
        unit_test_file_count = _count_test_files(repo.root)
        commands = _extract_canonical_scripts(pkg)
        smoke_test_path = _select_smoke_path(repo.root)

        # --- (4) coverage block (always emitted) ------------------------
        coverage_block, coverage_warns = _read_coverage_block(repo.root)
        for w in coverage_warns:
            self._warn(warnings, w)

        slice_payload: dict[str, Any] = {
            "framework": framework,
            "e2e_framework": e2e_framework,
            "unit_test_file_count": unit_test_file_count,
            "unit_test_count_is_file_count": True,
            "commands": commands,
            "smoke_test_path": smoke_test_path,
            "coverage_data": dict(coverage_block),
            "warnings": warnings,
        }

        duration_ms = max(0, int((time.perf_counter() - t0) * 1000))
        _log.info(
            EVENT_PROBE_SUCCESS,
            probe=self.name,
            confidence="high",
            framework=framework,
            e2e_framework=e2e_framework,
            unit_test_file_count=unit_test_file_count,
            coverage_present=coverage_block["present"],
        )

        return ProbeOutput(
            schema_slice={"test_inventory": slice_payload},
            raw_artifacts=[],
            confidence="high",
            duration_ms=duration_ms,
            warnings=[],
            errors=errors,
        )

    @staticmethod
    def _warn(warnings: list[str], wid: str) -> None:
        """Append a warning with import-time-validated membership.

        Centralizes the ``assert wid in _WARNING_IDS`` discipline so
        every callsite shares one chokepoint (Rule 12 — fail loud).
        """
        assert wid in _WARNING_IDS, f"unknown warning id {wid!r}"
        if wid not in warnings:
            warnings.append(wid)
