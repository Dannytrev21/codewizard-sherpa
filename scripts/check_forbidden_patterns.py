#!/usr/bin/env python3
"""Forbidden-patterns enforcement for the ``forbidden-patterns`` pre-commit hook.

Originally story S1-04 (Phase 0): scans each file path passed on argv for the
11 banned constructs listed in ADR-0008 (unsafe yaml load/dump) and ADR-0012
(subprocess shell + dangerous builtins).

S1-11 (Phase 2) extension: adds a 12th rule that bans ``model_construct`` under
seven Phase-2 packages — refactoring the rule loop so path-scoping is a
first-class predicate (Open/Closed). Adding any future path-scoped rule is
one new ``Rule(...)`` entry — zero edits to ``_scan_file()`` / ``main()``.

Exit code is the number of banned-pattern hits, capped at 255 — any non-zero
exit fails the hook. Matching is pure regex (no AST parse, no LLM, no
judgment) so the script is fast, deterministic, and trivially auditable.

The ``print(`` rule is scoped at the pre-commit hook level via ``exclude:``
(see ``.pre-commit-config.yaml``); ``tests/`` and ``scripts/`` legitimately
print to stdout. The ``yaml.Dumper`` rule is anchored so it does NOT match
``yaml.CSafeDumper``/``yaml.SafeDumper`` — those are the ADR-0008-prescribed
writers and blocking them would break the sanitizer. The Phase-2
``model_construct`` rule is scoped *inside* this script via the rule's
``applies_when`` predicate (so the test surface and the runtime surface are
the same) — NOT in ``.pre-commit-config.yaml``'s ``files:``/``exclude:``.

This script never executes the files it scans — it only reads bytes.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from re import Pattern


@dataclass(frozen=True, slots=True)
class Rule:
    """One row of ``_RULES``.

    ``applies_when`` is the path-scoping predicate: the rule fires only when
    the predicate returns ``True`` for the file under scan. The default
    predicate (``lambda _p: True``) makes a rule repo-wide — the shape used
    by every Phase-0 rule. Path-scoped rules (Phase-2 ``model_construct``,
    and any future kind) override it; adding a new kind is one ``Rule(...)``
    entry — no edits to ``_scan_file()`` or ``main()``.
    """

    label: str
    pattern: Pattern[str]
    advice: str
    applies_when: Callable[[Path], bool] = field(default=lambda _p: True)


# ---------------------------------------------------------------------------
# Phase 2 — model_construct ban (02-ADR-0010 + production ADR-0033)
# ---------------------------------------------------------------------------

_PHASE2_BANNED_PACKAGES: frozenset[str] = frozenset(
    {"indices", "tccm", "skills", "conventions", "adapters", "depgraph", "output"}
)


def _is_under_phase2_banned_package(path: Path) -> bool:
    """Return True iff *path* sits under ``src/codegenie/{one of seven}/`` —
    the seven Phase-2 packages whose smart-constructor invariants
    ``model_construct`` would silently bypass.

    Uses ``pathlib.Path.parts`` so symlinked checkouts and
    Windows path separators behave identically to POSIX ones — do NOT regex
    against the full path string.
    """
    parts = path.parts
    try:
        idx = parts.index("codegenie")
    except ValueError:
        return False
    return idx + 1 < len(parts) and parts[idx + 1] in _PHASE2_BANNED_PACKAGES


# ---------------------------------------------------------------------------
# Phase 2 S5-01 — model_construct ban extended to the sum-type kernels.
# ---------------------------------------------------------------------------


def _is_under_phase2_s5_01_sum_type_modules(path: Path) -> bool:
    """Return True iff *path* sits under
    ``src/codegenie/probes/_shared/**`` or is the load-bearing
    ``src/codegenie/probes/layer_c/scenario_result.py`` — the two pure-
    typing sum-type kernels planted by S5-01.

    These modules are explicitly out-of-scope for
    ``_is_under_phase2_banned_package`` (which keys on the top-level
    package name under ``codegenie/``); the S5-01 sum types live under
    ``probes/`` so they need their own scoping predicate. The
    smart-constructor invariants (``frozen=True``, ``extra="forbid"``,
    ``Literal[...]`` discriminator) are exactly what ``model_construct``
    would bypass.
    """
    parts = path.parts
    try:
        idx = parts.index("codegenie")
    except ValueError:
        return False
    tail = parts[idx + 1 :]
    if len(tail) >= 2 and tail[0] == "probes" and tail[1] == "_shared":
        return True
    if tail[-3:] == ("probes", "layer_c", "scenario_result.py"):
        return True
    return False


# ---------------------------------------------------------------------------
# Phase 2 S4-01 — mtime ban scoped to ``probes/layer_b/index_health.py``
# ---------------------------------------------------------------------------


def _is_index_health_module(path: Path) -> bool:
    """Return True iff *path* is the load-bearing ``index_health.py`` module.

    The ``IndexHealthProbe`` observes a *moving* fact (HEAD vs.
    last_indexed); caching that on filesystem mtime is "the same bug as
    caching ``Date.now()``" — see the module docstring + S4-01 story.
    A future contributor proposing "let's cache B2 for performance" trips
    this rule and gets redirected.
    """
    parts = path.parts
    try:
        idx = parts.index("codegenie")
    except ValueError:
        return False
    tail = parts[idx:]
    return tail[-3:] == ("probes", "layer_b", "index_health.py")


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

_RULES: list[Rule] = [
    # Phase 0 — ADR-0008 + ADR-0012 (repo-wide; default applies_when)
    Rule(
        label="print(",
        pattern=re.compile(r"\bprint\("),
        advice=(
            "All logging in src/ goes through structlog (T201). Scoped away "
            "from tests/ and scripts/ via hook `exclude:`."
        ),
    ),
    Rule(
        label="yaml.load( without Loader=",
        # Catches the literal `yaml.load(` call when `Loader=` does not appear
        # inside. The leading \b excludes wrapper-shaped names — `safe_yaml`,
        # `_yaml`, `my_yaml` — by design: this is defense-in-depth, not a
        # security guarantee. The rule's job is to catch the common slip
        # (someone typing `yaml.load(x)` literally); aliased-import evasion
        # (`import yaml as my_yaml; my_yaml.load(s)`) is out of scope and
        # belongs to import-linter + code review, not this regex.
        pattern=re.compile(r"\byaml\.load\((?:(?!Loader=).)*?\)", re.DOTALL),
        advice="ADR-0008: yaml.load requires Loader=yaml.CSafeLoader (or SafeLoader).",
    ),
    Rule(
        label="shell=True",
        pattern=re.compile(r"\bshell\s*=\s*True\b"),
        advice="ADR-0012: subprocess shell=True is banned; route through exec.py.",
    ),
    Rule(
        label="subprocess.run(..., shell=...)",
        # Catches both shell=True and shell=<dyn>. Anchored at subprocess.run(
        # to avoid clashing with the standalone shell=True rule.
        pattern=re.compile(r"subprocess\.run\s*\([^)]*shell\s*="),
        advice="ADR-0012: subprocess.run with shell= is banned (literal or dynamic).",
    ),
    Rule(
        label="yaml.Dumper",
        # Negative lookbehinds anchor the match so yaml.CSafeDumper and
        # yaml.SafeDumper (the ADR-0008-prescribed writers) are preserved.
        pattern=re.compile(r"(?<!CSafe)(?<!Safe)yaml\.Dumper\b"),
        advice="ADR-0008: use yaml.CSafeDumper (preferred) or yaml.SafeDumper, never yaml.Dumper.",
    ),
    Rule(
        label="os.system(",
        pattern=re.compile(r"\bos\.system\("),
        advice="ADR-0012: os.system bypasses the subprocess allowlist.",
    ),
    Rule(
        label="os.popen(",
        pattern=re.compile(r"\bos\.popen\("),
        advice="ADR-0012: os.popen bypasses the subprocess allowlist.",
    ),
    Rule(
        label="pickle.loads(",
        pattern=re.compile(r"\bpickle\.loads\("),
        advice="ADR-0012: pickle.loads enables arbitrary code execution.",
    ),
    Rule(
        label="eval(",
        pattern=re.compile(r"\beval\("),
        advice="ADR-0012: eval enables arbitrary code execution.",
    ),
    Rule(
        label="exec(",
        # `exec(` the function call, not `__main__` or `if __name__`.
        pattern=re.compile(r"\bexec\("),
        advice="ADR-0012: exec() enables arbitrary code execution.",
    ),
    Rule(
        label="__import__(",
        pattern=re.compile(r"\b__import__\("),
        advice="ADR-0012: __import__ enables dynamic import-based escapes.",
    ),
    # Phase 2 S4-01 — mtime ban scoped to ``probes/layer_b/index_health.py``.
    # B2's ``cache_strategy="none"`` discipline is load-bearing — caching a
    # *moving* fact (HEAD vs. last_indexed) is "the same bug as caching
    # ``Date.now()``". A contributor proposing performance caching gets
    # redirected by failing here.
    Rule(
        label="os.path.getmtime (index_health.py)",
        pattern=re.compile(r"\bos\.path\.getmtime\("),
        advice=(
            "02-S4-01 AC-2: mtime is not a freshness signal. B2 observes a "
            "moving fact (HEAD vs last_indexed); cache_strategy='none' is "
            "load-bearing."
        ),
        applies_when=_is_index_health_module,
    ),
    Rule(
        label="Path.stat().st_mtime (index_health.py)",
        pattern=re.compile(r"\.stat\(\)\.st_mtime\b"),
        advice="02-S4-01 AC-2: mtime is not a freshness signal in B2.",
        applies_when=_is_index_health_module,
    ),
    Rule(
        label="os.stat(...).st_mtime (index_health.py)",
        pattern=re.compile(r"\bos\.stat\([^)]*\)\.st_mtime\b"),
        advice="02-S4-01 AC-2: mtime is not a freshness signal in B2.",
        applies_when=_is_index_health_module,
    ),
    Rule(
        label="lstat(...).st_mtime (index_health.py)",
        pattern=re.compile(r"\blstat\([^)]*\)\.st_mtime\b"),
        advice="02-S4-01 AC-2: mtime is not a freshness signal in B2.",
        applies_when=_is_index_health_module,
    ),
    # Phase 2 — model_construct ban (02-ADR-0010 + production ADR-0033)
    Rule(
        label="model_construct (Phase 2 packages)",
        # Catches `.model_construct(` (instance + class call) AND
        # `model_construct=` (kwarg / assignment). Honest about being a
        # *structural* defense rather than AST-precise: legitimate uses of
        # `model_construct` as a variable name in Phase-2 code are vanishingly
        # rare (Pydantic-reserved surface), and the false-positive cost is a
        # PR comment — cheap relative to the smart-constructor guarantee.
        pattern=re.compile(r"\.model_construct\s*\(|\bmodel_construct\s*="),
        advice=(
            "02-ADR-0010 §Decision + production ADR-0033 §3 — smart "
            "constructors must be the only public path; use "
            "`from_validated_input(...)` or the public model factory."
        ),
        applies_when=_is_under_phase2_banned_package,
    ),
    # Phase 2 S5-01 — same ban extended to the sum-type kernels.
    Rule(
        label="model_construct (Phase 2 S5-01 sum-type modules)",
        pattern=re.compile(r"\.model_construct\s*\(|\bmodel_construct\s*="),
        advice=(
            "02-ADR-0010 §Decision + production ADR-0033 §3 — smart "
            "constructors must be the only public path for the S5-01 sum "
            "types (probes/_shared/** + probes/layer_c/scenario_result.py); "
            "use `Model(...)` or `Model.model_validate(...)`."
        ),
        applies_when=_is_under_phase2_s5_01_sum_type_modules,
    ),
]


def _scan_file(path: Path) -> list[tuple[str, int, str]]:
    """Return (rule_label, line_number, advice) tuples for every hit in *path*.

    Files that can't be decoded as UTF-8 are skipped silently — non-text files
    (binaries, lockfiles with odd encodings) are not in scope for this hook.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    hits: list[tuple[str, int, str]] = []
    for rule in _RULES:
        if not rule.applies_when(path):
            continue
        for match in rule.pattern.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            hits.append((rule.label, line_no, rule.advice))
    return hits


def main(argv: list[str]) -> int:
    """Scan each path in *argv* and report any banned-pattern hits.

    Returns the number of total hits (capped at 255). Zero means clean.
    """
    if not argv:
        return 0

    total = 0
    for raw in argv:
        path = Path(raw)
        if not path.is_file():
            continue
        for label, line_no, advice in _scan_file(path):
            sys.stdout.write(f"{path}:{line_no}: forbidden pattern `{label}` — {advice}\n")
            total += 1
    return min(total, 255)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
