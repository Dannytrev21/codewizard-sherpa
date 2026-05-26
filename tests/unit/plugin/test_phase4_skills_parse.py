"""Phase-4 S7-04 — skill ``.md`` parse tests (AC-3, AC-4).

Loads each of the two new skill templates through the existing
Phase-2 :func:`_load_one_skill` kernel parser (unmodified). Asserts:

* ``id == SkillId("<expected slug>")``
* ``applies_to_tasks == [TaskClassId("vulnerability-remediation")]``
* ``applies_to_languages == [Language("javascript")]``  *(not ``node`` — see CN-5)*
* ``body_size`` is within the arch soft-budget range.
* ``body_blake3`` matches the canonical ``^blake3:[0-9a-f]{64}$`` pattern.

No ``kind:`` / ``task_class:`` / ``language:`` / ``build_system:``
frontmatter is permitted by the kernel ``Skill`` model
(``extra="forbid"``); a non-empty additional frontmatter key would fail
to parse before reaching these assertions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.result import Ok
from codegenie.skills.loader import _load_one_skill
from codegenie.skills.model import Skill
from codegenie.types.identifiers import Language, SkillId, TaskClassId

_SKILLS_DIR = (
    Path(__file__).parents[3] / "plugins" / "vulnerability-remediation--node--npm" / "skills"
)


@pytest.mark.parametrize(
    ("filename", "expected_id", "min_body", "max_body"),
    [
        (
            "vuln-major-bump.md",
            "vuln-major-bump-vulnerability-remediation-javascript-npm",
            512,
            4096,
        ),
        (
            "leaf-llm-instruction.md",
            "leaf-llm-instruction-vulnerability-remediation-javascript-npm",
            1024,
            6144,
        ),
    ],
)
def test_phase4_skill_parses_cleanly(
    filename: str, expected_id: str, min_body: int, max_body: int
) -> None:
    """Each skill loads through ``_load_one_skill`` and conforms to the
    Phase-2 ``Skill`` shape with the Phase-4 expected metadata.
    """
    path = _SKILLS_DIR / filename
    assert path.is_file(), f"skill file missing: {path}"

    result = _load_one_skill(path)
    assert isinstance(result, Ok), f"unexpected load error: {result!r}"
    skill: Skill = result.value

    assert skill.id == SkillId(expected_id)
    assert skill.applies_to_tasks == [TaskClassId("vulnerability-remediation")]
    assert skill.applies_to_languages == [Language("javascript")]
    assert min_body <= skill.body_size <= max_body, (
        f"body_size {skill.body_size} not in [{min_body}, {max_body}] for {filename}"
    )
    assert skill.body_blake3.startswith("blake3:")
    # Pydantic Field pattern already enforces ^blake3:[0-9a-f]{64}$;
    # this assert is human-readable confirmation.
    digest = skill.body_blake3.removeprefix("blake3:")
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_phase4_skills_do_not_use_node_language_token() -> None:
    """Validation finding CN-5 — the inner Phase-3 language token is
    ``javascript`` (matches Layer A ``LanguageDetection``), not ``node``.
    The directory slug ``--node--`` is operator-readable only.
    """
    for filename in ("vuln-major-bump.md", "leaf-llm-instruction.md"):
        text = (_SKILLS_DIR / filename).read_text()
        # Find the applies_to_languages line — must contain "javascript",
        # must NOT contain a bare "node" outside string-list context.
        for line in text.splitlines():
            if "applies_to_languages" in line:
                assert "javascript" in line, (
                    f"{filename}: expected 'javascript' in applies_to_languages: {line!r}"
                )
                # Reject the validator finding's literal regression:
                # ``applies_to_languages: ["node"]`` would silently mis-route.
                assert '"node"' not in line and "'node'" not in line, (
                    f"{filename}: regression — 'node' token used where 'javascript' is canonical"
                )
                break
