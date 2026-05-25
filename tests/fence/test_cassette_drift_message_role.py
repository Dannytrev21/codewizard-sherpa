"""Capability-shakedown 2026-05-25 — cassette drift-message role-name fence.

Post-S3-06, the cassette-CODEOWNERS owner is the single-human
``cassette-steward`` (ADR-0014 §Decision, `.github/CODEOWNERS`,
`docs/operations/cassettes.md`). Earlier text drafts used the team-shaped
token ``cassette-review``; the S3-06 attempt log explicitly records that
rename. The shakedown found two live source-of-truth copies of the
drift-message that still pointed operators at ``cassette-review``:

- ``src/codegenie/cli.py`` — the ``codegenie cassette rebuild-lockfile
  --check`` stderr message.
- ``tests/security/test_cassettes_clean.py`` — the layer-2 CI scanner's
  ``cassette.lock_drift`` diagnostic string.

Both messages tell an operator *which* CODEOWNERS path to follow next.
If they name a role that doesn't exist in CODEOWNERS, the message is
actively misleading. This fence pins the canonical role name in both
files so any future rename (or accidental partial-rename) is caught at
the source level rather than via a downstream operator confusion.

The fence is intentionally narrow: it reads the two file texts and
asserts the literal substrings. Story/ADR/attempt-log docs are out of
scope (they are historical artifacts; the S3-06 attempt log itself
discusses the rename and must continue to mention the old token).
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The two live source-of-truth files that emit the drift message.
_CLI_PATH = _REPO_ROOT / "src" / "codegenie" / "cli.py"
_SCANNER_PATH = _REPO_ROOT / "tests" / "security" / "test_cassettes_clean.py"


def test_cli_drift_message_names_cassette_steward_not_cassette_review() -> None:
    """The ``codegenie cassette rebuild-lockfile --check`` drift message
    points operators at the canonical ``cassette-steward`` CODEOWNERS
    handle (the post-S3-06 single-human role) — never the obsolete
    ``cassette-review`` team token.
    """
    text = _CLI_PATH.read_text(encoding="utf-8")
    assert "cassette-review" not in text, (
        "src/codegenie/cli.py contains the stale role token 'cassette-review'. "
        "Per ADR-0014 §Decision (post-S3-06), the canonical role is "
        "'cassette-steward' (single human). Update the drift-message string."
    )
    # Positive control: the canonical role must be named somewhere in the
    # CLI text — a silent removal of the role name would also be wrong.
    assert "cassette-steward" in text, (
        "src/codegenie/cli.py no longer names 'cassette-steward'. The drift "
        "message must point operators at the canonical CODEOWNERS handle."
    )


def test_scanner_drift_message_names_cassette_steward_not_cassette_review() -> None:
    """The layer-2 CI scanner's ``cassette.lock_drift`` diagnostic carries
    the canonical ``cassette-steward`` role name (and never the obsolete
    ``cassette-review`` token).
    """
    text = _SCANNER_PATH.read_text(encoding="utf-8")
    assert "cassette-review" not in text, (
        "tests/security/test_cassettes_clean.py contains the stale role "
        "token 'cassette-review'. Per ADR-0014 §Decision (post-S3-06), the "
        "canonical role is 'cassette-steward' (single human)."
    )
    assert "cassette-steward" in text, (
        "tests/security/test_cassettes_clean.py no longer names "
        "'cassette-steward'. The scanner's lock_drift diagnostic must "
        "point operators at the canonical CODEOWNERS handle."
    )
