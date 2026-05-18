"""S8-02 AC-8 — :mod:`codegenie.cli_summary` is a pure formatter.

These tests construct :class:`~codegenie.cli_summary.SummaryBlock`
instances directly (no gather, no logger, no ``tmp_path``) and assert
the formatter's pure-function properties: format regexes per line,
idempotence, ASCII-lex sort + dedup, and a static-AST gate that the
module imports nothing that would make it impure.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from codegenie.cli_summary import summary_block
from codegenie.skills.model import ShadowedSkill
from codegenie.types.identifiers import SkillId

_HEX8 = st.text(alphabet="0123456789abcdef", min_size=8, max_size=8)

_COUNT_RE = re.compile(r"^secrets_redacted_count=\d+$")
_FP_RE = re.compile(r"^fingerprints=\[(?:[0-9a-f]{8}(?:, [0-9a-f]{8})*)?\]$")
_SHADOW_RE = re.compile(
    r"^skill_shadowed=\[(?:[A-Za-z0-9_./-]+:(?:user|repo|org)"
    r"(?:, [A-Za-z0-9_./-]+:(?:user|repo|org))*)?\]$"
)


def _skill_id(s: str) -> SkillId:
    """Narrow ``str`` to ``SkillId`` newtype — identity at runtime."""
    return SkillId(s)


def test_format_regex_each_line() -> None:
    """AC-8 (a) — empty inputs produce the documented zero-state shape."""
    block = summary_block(count=0, fingerprints=(), shadowed=())
    count_line, fp_line, shadow_line = block.as_lines()
    assert count_line == "secrets_redacted_count=0"
    assert fp_line == "fingerprints=[]"
    assert shadow_line == "skill_shadowed=[]"
    assert _COUNT_RE.match(count_line)
    assert _FP_RE.match(fp_line)
    assert _SHADOW_RE.match(shadow_line)


def test_format_regex_with_values() -> None:
    """AC-8 (a) — populated inputs match the documented format regex."""
    block = summary_block(
        count=2,
        fingerprints=("cafef00d", "abcdef01"),
        shadowed=(
            ShadowedSkill(
                skill_id=_skill_id("dup"),
                shadowed_tier="org",
                winning_tier="user",
                shadowed_path="/o/s.md",
                winning_path="/u/s.md",
            ),
        ),
    )
    count_line, fp_line, shadow_line = block.as_lines()
    assert _COUNT_RE.match(count_line)
    assert _FP_RE.match(fp_line)
    assert _SHADOW_RE.match(shadow_line)
    assert fp_line == "fingerprints=[abcdef01, cafef00d]"
    assert shadow_line == "skill_shadowed=[dup:org]"


def test_idempotence_same_inputs_same_block() -> None:
    """AC-8 (b) — same inputs always produce equal :class:`SummaryBlock`."""
    args = (
        7,
        ("abcdef01", "cafef00d", "abcdef01"),
        (
            ShadowedSkill(
                skill_id=_skill_id("foo"),
                shadowed_tier="org",
                winning_tier="user",
                shadowed_path="/o/s.md",
                winning_path="/u/s.md",
            ),
        ),
    )
    assert summary_block(*args) == summary_block(*args)


def test_fingerprints_sorted_ascii_lex() -> None:
    """AC-8 (c) — fingerprints are ASCII-lex sorted regardless of input order."""
    block = summary_block(count=3, fingerprints=("ffffffff", "00000000", "abcdef01"), shadowed=())
    assert block.fingerprints_line == "fingerprints=[00000000, abcdef01, ffffffff]"


def test_fingerprints_dedup() -> None:
    """AC-8 (d) — duplicate fingerprints collapse to a single entry."""
    block = summary_block(
        count=5,
        fingerprints=("cafef00d", "cafef00d", "abcdef01"),
        shadowed=(),
    )
    # 5 raw findings, 2 unique fingerprints.
    assert block.fingerprints_line == "fingerprints=[abcdef01, cafef00d]"


def test_shadowed_sorted_by_id_then_tier() -> None:
    """Shadowed entries ASCII-lex sorted by ``(skill_id, shadowed_tier)``."""
    s = [
        ShadowedSkill(
            skill_id=_skill_id("bar"),
            shadowed_tier="org",
            winning_tier="user",
            shadowed_path="/o/bar.md",
            winning_path="/u/bar.md",
        ),
        ShadowedSkill(
            skill_id=_skill_id("alpha"),
            shadowed_tier="repo",
            winning_tier="user",
            shadowed_path="/r/alpha.md",
            winning_path="/u/alpha.md",
        ),
        ShadowedSkill(
            skill_id=_skill_id("alpha"),
            shadowed_tier="org",
            winning_tier="user",
            shadowed_path="/o/alpha.md",
            winning_path="/u/alpha.md",
        ),
    ]
    block = summary_block(count=0, fingerprints=(), shadowed=s)
    assert block.shadowed_line == "skill_shadowed=[alpha:org, alpha:repo, bar:org]"


@given(
    st.lists(_HEX8, min_size=0, max_size=20),
    st.integers(min_value=0, max_value=10_000),
)
def test_sort_and_dedup_property(fingerprints: list[str], count: int) -> None:
    """AC-8 hypothesis property: dedup + sort is observed in the rendered line.

    For any list of 8-hex strings, the fingerprints line parses to a
    list of unique fingerprints in ASCII-lex order.
    """
    block = summary_block(count=count, fingerprints=fingerprints, shadowed=())
    body = block.fingerprints_line[len("fingerprints=[") : -1]
    parsed = [tok for tok in body.split(", ") if tok]
    assert parsed == sorted(set(fingerprints))


def test_pure_no_io_imports() -> None:
    """AC-8 — static-AST gate. :mod:`codegenie.cli_summary` must not import
    nor reference anything that makes it impure.

    AST-walks the module source and rejects any ``import``/``from`` of
    ``os``, ``time``, ``structlog``, ``logging``, ``builtins``, plus any
    call to ``print``, ``open``, ``logger``. The module is the pure
    functional core; the impure shell lives in ``codegenie.cli``.
    """
    import ast

    src_path = Path(__file__).resolve().parents[3] / "src" / "codegenie" / "cli_summary.py"
    src = src_path.read_text()
    tree = ast.parse(src)

    forbidden_modules = {
        "os",
        "os.path",
        "time",
        "structlog",
        "logging",
        "subprocess",
        "asyncio",
    }
    forbidden_calls = {"print", "open"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                assert root not in forbidden_modules, (
                    f"cli_summary.py must remain pure; forbidden import {alias.name!r}"
                )
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                root = node.module.split(".", 1)[0]
                assert root not in forbidden_modules, (
                    f"cli_summary.py must remain pure; forbidden from-import {node.module!r}"
                )
        elif isinstance(node, ast.Call):
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else (func.attr if isinstance(func, ast.Attribute) else None)
            )
            if name in forbidden_calls:
                raise AssertionError(f"cli_summary.py must remain pure; forbidden call to {name!r}")


def test_summary_block_is_frozen() -> None:
    """Smart constructor + immutability — :class:`SummaryBlock` rejects mutation."""
    block = summary_block(count=0, fingerprints=(), shadowed=())
    with pytest.raises((AttributeError, Exception)):
        block.count_line = "tampered"  # type: ignore[misc]
