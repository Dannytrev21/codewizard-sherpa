"""S7-11 preflight — pre-conditions the cassette-recording session needs.

The executor lands these tests without the cassettes existing yet;
they verify the cassette infrastructure (S3-04/S3-05/S3-06) is on
master and the express-cve-2026-1234 fixture (S7-05) is at least
partially planted. A future operator running `make refresh-cassettes
I_UNDERSTAND_THIS_SPENDS_TOKENS=1` reads these tests' output as the
pre-recording sanity gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parents[2]
_CASSETTES_LOCK = _REPO_ROOT / "tests" / "cassettes" / "anthropic" / "cassettes.lock"
_CASSETTE_SCANNER = _REPO_ROOT / "tests" / "security" / "test_cassettes_clean.py"
_EXPRESS_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "repos" / "express-cve-2026-1234"


def test_cassette_sanitizer_module_importable() -> None:
    """S3-04's CassetteSanitizer module must import — the recording session
    routes leaf-LLM calls through this sanitizer to strip
    Authorization headers + sk-ant patterns. Shipped under
    ``codegenie.fallback.cassette`` per S3-04 directory layout."""
    import codegenie.fallback.cassette  # noqa: F401


def test_cassettes_lock_exists_on_master() -> None:
    """S3-05's BLAKE3 manifest must exist; recording session refreshes
    it in place."""
    assert _CASSETTES_LOCK.exists(), (
        f"S3-05 cassettes.lock missing at {_CASSETTES_LOCK}. "
        "Cassette pipeline not operational; cannot record."
    )


def test_cassette_cleanliness_scanner_exists() -> None:
    """S3-05's CI scanner module must exist so recorded cassettes
    flow through its sanitizer-output check on the next CI run."""
    assert _CASSETTE_SCANNER.exists(), (
        f"S3-05 cassette-cleanliness scanner missing at {_CASSETTE_SCANNER}."
    )


def test_makefile_refresh_cassettes_target_exists() -> None:
    """S3-06's `make refresh-cassettes` target must be wired so the
    operator's one-liner works."""
    makefile = _REPO_ROOT / "Makefile"
    assert makefile.exists()
    body = makefile.read_text()
    assert "refresh-cassettes:" in body, (
        "S3-06 `make refresh-cassettes` target missing from Makefile."
    )
    assert "I_UNDERSTAND_THIS_SPENDS_TOKENS" in body, (
        "S3-06 explicit-acknowledgement gate missing from refresh-cassettes target."
    )


def test_express_cve_fixture_at_least_skeleton() -> None:
    """S7-05 ships the express-cve-2026-1234 fixture; the recording
    session needs at minimum a parseable package.json. The fixture
    body (~80 .ts files + Jest suite) is S7-05's content-authoring
    territory; this preflight only requires a minimum skeleton.

    Loud-skips when the fixture directory doesn't exist yet — that's
    S7-05's gate, not S7-11's.
    """
    if not _EXPRESS_FIXTURE.exists():
        pytest.skip(
            "S7-05 express-cve-2026-1234 fixture directory not planted yet — "
            "S7-11 AC-2's cassette recording can't run until S7-05 ships at "
            "least the minimum skeleton (package.json + a CVE-shaped .ts file)."
        )
    pkg = _EXPRESS_FIXTURE / "package.json"
    assert pkg.exists(), (
        "S7-05 express fixture exists but lacks package.json — "
        "cassette recording needs an npm-loadable shape."
    )


def test_phase4_config_yaml_present() -> None:
    """S7-04's phase4-config.yaml is read at plugin-load time during
    cassette recording — its absence would cause the recording session
    to fail before the leaf call."""
    cfg = _REPO_ROOT / "plugins" / "vulnerability-remediation--node--npm" / "phase4-config.yaml"
    assert cfg.exists(), f"S7-04 phase4-config.yaml missing at {cfg}"
