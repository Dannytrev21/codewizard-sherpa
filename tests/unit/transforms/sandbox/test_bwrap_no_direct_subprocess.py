"""AC-4 — AST walk forbidding direct subprocess primitives anywhere under
``src/codegenie/transforms/sandbox/``.

Substring grep is escapable (``from subprocess import run``,
``getattr(subprocess, 'run')(...)``); AST walk is not.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[4] / "src/codegenie/transforms/sandbox"

_FORBIDDEN_EXACT_PAIRS: frozenset[tuple[str, str]] = frozenset(
    {
        ("subprocess", "run"),
        ("subprocess", "Popen"),
        ("subprocess", "call"),
        ("subprocess", "check_call"),
        ("subprocess", "check_output"),
        ("os", "system"),
        ("os", "popen"),
        ("asyncio", "create_subprocess_exec"),
        ("asyncio", "create_subprocess_shell"),
    }
)
_FORBIDDEN_PREFIX_PAIRS: tuple[tuple[str, str], ...] = (
    ("os", "exec"),
    ("os", "spawn"),
    ("os", "posix_spawn"),
)


def _walk_one(path: Path) -> list[str]:
    """Return a list of human-readable violations for *path*. Empty list
    means clean."""
    findings: list[str] = []
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # (a) Attribute-style calls: subprocess.run(...), os.system(...)
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                pair = (node.func.value.id, node.func.attr)
                if pair in _FORBIDDEN_EXACT_PAIRS:
                    findings.append(f"{path}:{node.lineno}: forbidden call {pair}")
                for mod, prefix in _FORBIDDEN_PREFIX_PAIRS:
                    if pair[0] == mod and pair[1].startswith(prefix):
                        findings.append(
                            f"{path}:{node.lineno}: forbidden call {pair} (prefix={prefix})"
                        )
            # (b) getattr(subprocess, ...) indirection
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and node.args
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == "subprocess"
            ):
                findings.append(
                    f"{path}:{node.lineno}: getattr(subprocess, ...) indirection forbidden"
                )
            # (c) shell=True kwarg on any call
            for kw in node.keywords:
                if (
                    kw.arg == "shell"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                ):
                    findings.append(f"{path}:{node.lineno}: shell=True kwarg forbidden")
    return findings


def test_no_direct_subprocess_calls_anywhere_in_sandbox_package() -> None:
    findings: list[str] = []
    for py in SRC_ROOT.rglob("*.py"):
        findings.extend(_walk_one(py))
    assert not findings, "subprocess discipline violations:\n" + "\n".join(findings)


def test_walker_actually_detects_a_planted_violation(tmp_path: Path) -> None:
    """Mutation-resistance: the walker IS the test. If it stops flagging
    planted violations, the live test stops protecting us."""
    planted = tmp_path / "planted.py"
    planted.write_text("import subprocess\ndef go():\n    subprocess.run(['echo', 'x'])\n")
    findings = _walk_one(planted)
    assert findings, "AST walker failed to detect a planted subprocess.run call"


def test_walker_detects_planted_getattr_indirection(tmp_path: Path) -> None:
    planted = tmp_path / "planted_getattr.py"
    planted.write_text(
        "import subprocess\ndef go():\n    getattr(subprocess, 'run')(['echo', 'x'])\n"
    )
    findings = _walk_one(planted)
    assert findings, "AST walker missed getattr(subprocess, ...) indirection"


def test_walker_detects_planted_shell_true(tmp_path: Path) -> None:
    planted = tmp_path / "planted_shell.py"
    planted.write_text("def go(thing):\n    thing(cmd='echo x', shell=True)\n")
    findings = _walk_one(planted)
    assert any("shell=True" in f for f in findings)
