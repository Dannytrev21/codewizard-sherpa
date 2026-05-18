"""S8-02 AC-3 — plaintext-boundary check, iterated over ``_PATTERNS``.

For each pattern class in
:data:`codegenie.output.sanitizer._PATTERNS`, seed a known plaintext
example into a ``tmp_path``-rooted fixture, run ``codegenie gather``,
and assert the plaintext does NOT appear in:

- the CLI's stdout (the new ``fingerprints=[...]`` line carries only
  8-hex BLAKE3 fingerprints, never the cleartext); and
- any captured-log event payload (the existing ``envelope.written``
  event carries only the redacted count, never the cleartext).

The iteration over ``_PATTERNS`` is load-bearing: a future contributor
who adds a 7th pattern class exercises this test automatically. Single
source of truth, mutation-resistant.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner
from structlog.testing import capture_logs

from codegenie.output import sanitizer

# Canonical plaintext examples per pattern class. Each must match the
# corresponding regex in ``sanitizer._PATTERNS``; the entropy fallback
# fires only after the named patterns, so we seed a high-entropy bare
# string for the ``"entropy"`` class.
_PLAINTEXT_BY_CLASS: dict[str, str] = {
    "aws_access_key": "AKIA" + "B" * 16,
    "github_token": "ghp_" + "a" * 36,
    "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
    "rsa_private_key": (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIBOgIBAAJBAKj34GkxFhD90vcNLYLInFEX6Ppy1tPf9Cnzj4p4WGeKLs1Pt8Qu\n"
        "-----END RSA PRIVATE KEY-----"
    ),
    "npm_token": "npm_" + "z" * 36,
    "anthropic_key": "sk-ant-" + "Q" * 80,
    "entropy": "ZXyVqM9PaAcF2hBwS3DfL7tNgR4uHvCjK6oI0eY1lXJ8mUbT5sWnE",
}


def _seed_with_plaintext(tmp_path: Path, plaintext: str, suffix: str) -> Path:
    src = Path(__file__).resolve().parents[2] / "fixtures" / "portfolio" / "minimal-ts"
    dst = tmp_path / "minimal-ts"
    shutil.copytree(src, dst)
    (dst / "src" / f"seeded-{suffix}.ts").write_text(f"export const SEEDED = `{plaintext}`;\n")
    return dst


@pytest.mark.parametrize(
    "pattern_class",
    [pc for pc, _ in sanitizer._PATTERNS] + ["entropy"],
)
def test_no_pattern_class_plaintext_in_stdout_or_events(tmp_path: Path, pattern_class: str) -> None:
    """For every pattern class in ``_PATTERNS`` + entropy: the seeded
    plaintext NEVER appears on stdout or in any captured-log payload."""
    from codegenie.cli import cli

    plaintext = _PLAINTEXT_BY_CLASS[pattern_class]
    fixture = _seed_with_plaintext(tmp_path, plaintext, pattern_class)

    with capture_logs() as captured:
        result = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(fixture)])
    assert result.exit_code == 0, result.output

    assert plaintext not in result.stdout, (
        f"plaintext for {pattern_class} leaked to stdout: {result.stdout!r}"
    )
    serialized_events = " ".join(repr(e) for e in captured)
    assert plaintext not in serialized_events, (
        f"plaintext for {pattern_class} leaked to a captured-log payload"
    )


def test_patterns_table_iterated_not_hardcoded() -> None:
    """Mutation-resistance: every pattern class in ``_PATTERNS`` is covered.

    A future contributor adding a 7th class to ``_PATTERNS`` must also
    add an entry to ``_PLAINTEXT_BY_CLASS`` (else this assertion fails)
    — the test catches "I added a regex but forgot to test it" before CI
    sees it.
    """
    covered = set(_PLAINTEXT_BY_CLASS.keys())
    declared = {pc for pc, _ in sanitizer._PATTERNS} | {"entropy"}
    missing = declared - covered
    assert not missing, f"_PLAINTEXT_BY_CLASS missing entries for: {missing}"
