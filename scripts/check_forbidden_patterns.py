#!/usr/bin/env python3
"""Forbidden-patterns enforcement for the `forbidden-patterns` pre-commit hook (story S1-04).

Scans each file path passed on argv for the 11 banned constructs listed in
ADR-0008 (unsafe yaml load/dump) and ADR-0012 (subprocess shell + dangerous
builtins). Exit code is the number of banned-pattern hits, capped at 255 — any
non-zero exit fails the hook. The matching rules are pure regex (no AST parse,
no LLM, no judgment) so the script is fast, deterministic, and trivially
auditable.

The ``print(`` rule is scoped at the pre-commit hook level via ``exclude:``
(see ``.pre-commit-config.yaml``); ``tests/`` and ``scripts/`` legitimately
print to stdout. The ``yaml.Dumper`` rule is anchored so it does NOT match
``yaml.CSafeDumper``/``yaml.SafeDumper`` — those are the ADR-0008-prescribed
writers and blocking them would break the sanitizer.

This script never executes the files it scans — it only reads bytes.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from re import Pattern

# (label, compiled regex, human-readable advice)
# Every pattern is enumerated; adding one is a deliberate PR (per ADR-0012).
_RULES: list[tuple[str, Pattern[str], str]] = [
    (
        "print(",
        re.compile(r"\bprint\("),
        "All logging in src/ goes through structlog (T201). Scoped away from "
        "tests/ and scripts/ via hook `exclude:`.",
    ),
    (
        "yaml.load( without Loader=",
        # Matches yaml.load( ... ) when 'Loader=' does not appear inside the
        # call. Permits yaml.load(s, Loader=SafeLoader).
        re.compile(r"yaml\.load\((?:(?!Loader=).)*?\)", re.DOTALL),
        "ADR-0008: yaml.load requires Loader=yaml.CSafeLoader (or SafeLoader).",
    ),
    (
        "shell=True",
        re.compile(r"\bshell\s*=\s*True\b"),
        "ADR-0012: subprocess shell=True is banned; route through exec.py.",
    ),
    (
        "subprocess.run(..., shell=...)",
        # Catches both shell=True and shell=<dyn>. Anchored at subprocess.run(
        # to avoid clashing with the standalone shell=True rule.
        re.compile(r"subprocess\.run\s*\([^)]*shell\s*="),
        "ADR-0012: subprocess.run with shell= is banned (literal or dynamic).",
    ),
    (
        "yaml.Dumper",
        # Negative lookbehinds anchor the match so yaml.CSafeDumper and
        # yaml.SafeDumper (the ADR-0008-prescribed writers) are preserved.
        re.compile(r"(?<!CSafe)(?<!Safe)yaml\.Dumper\b"),
        "ADR-0008: use yaml.CSafeDumper (preferred) or yaml.SafeDumper, never yaml.Dumper.",
    ),
    (
        "os.system(",
        re.compile(r"\bos\.system\("),
        "ADR-0012: os.system bypasses the subprocess allowlist.",
    ),
    (
        "os.popen(",
        re.compile(r"\bos\.popen\("),
        "ADR-0012: os.popen bypasses the subprocess allowlist.",
    ),
    (
        "pickle.loads(",
        re.compile(r"\bpickle\.loads\("),
        "ADR-0012: pickle.loads enables arbitrary code execution.",
    ),
    (
        "eval(",
        re.compile(r"\beval\("),
        "ADR-0012: eval enables arbitrary code execution.",
    ),
    (
        "exec(",
        # `exec(` the function call, not `__main__` or `if __name__`.
        re.compile(r"\bexec\("),
        "ADR-0012: exec() enables arbitrary code execution.",
    ),
    (
        "__import__(",
        re.compile(r"\b__import__\("),
        "ADR-0012: __import__ enables dynamic import-based escapes.",
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
    for label, pattern, advice in _RULES:
        for match in pattern.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            hits.append((label, line_no, advice))
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
