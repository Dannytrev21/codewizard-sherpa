"""Pure-function tests for the argv builders + image-ref smart constructor.

These tests do NOT mock ``run_allowlisted`` — each helper is module-private
and importable as-is.
"""

from __future__ import annotations

import pytest

from codegenie.probes.layer_c.runtime_trace import (
    _HARDENING_FLAGS,
    _IMAGE_REF_PREFIX,
    _build_docker_run_argv,
    _build_strace_argv,
    _image_ref_for_digest,
)

# ---------------------------------------------------------------------------
# _image_ref_for_digest
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "digest, expected",
    [
        ("sha256:cafef00ddeadbeef0123456789abcdef", "codegenie-trace:cafef00ddead"),
        ("cafef00ddeadbeef0123456789abcdef", "codegenie-trace:cafef00ddead"),
        ("0123456789abcdef" * 4, "codegenie-trace:0123456789ab"),
    ],
)
def test_image_ref_for_digest_format(digest: str, expected: str) -> None:
    assert _image_ref_for_digest(digest) == expected


@pytest.mark.parametrize("bad", ["", "not-a-digest", "sha256:zzzz", "sha256:"])
def test_image_ref_for_digest_rejects_bad_input(bad: str) -> None:
    with pytest.raises(ValueError):
        _image_ref_for_digest(bad)


def test_image_ref_for_digest_uses_module_prefix_constant() -> None:
    digest = "sha256:" + "0" * 40
    ref = _image_ref_for_digest(digest)
    assert ref.startswith(_IMAGE_REF_PREFIX)


# ---------------------------------------------------------------------------
# _build_docker_run_argv
# ---------------------------------------------------------------------------


def test_docker_run_argv_contains_all_hardening_flags() -> None:
    argv = _build_docker_run_argv("codegenie-trace:abc", ["sh", "-c", "exit 0"])
    # (a) every hardening flag appears exactly once.
    for flag in _HARDENING_FLAGS:
        assert argv.count(flag) == 1, f"flag {flag!r} not found exactly once in argv: {argv}"


def test_docker_run_argv_has_explicit_dash_dash_before_image_ref() -> None:
    argv = _build_docker_run_argv("codegenie-trace:abc", ["sh", "-c", "exit 0"])
    dash_dash_idx = argv.index("--")
    assert argv[dash_dash_idx + 1] == "codegenie-trace:abc"


def test_docker_run_argv_no_concatenated_flag_string() -> None:
    """Catches a mutation that joins flags with spaces."""
    concat = " ".join(_HARDENING_FLAGS)
    argv = _build_docker_run_argv("codegenie-trace:abc", ["sh"])
    assert concat not in argv


# ---------------------------------------------------------------------------
# _build_strace_argv
# ---------------------------------------------------------------------------


def test_strace_argv_explicit_dash_dash_separator() -> None:
    argv = _build_strace_argv("codegenie-trace:abc", ["sh", "-c", "exit 0"])
    # Exactly one literal "--" token separating strace args from the wrapped command.
    assert argv.count("--") == 1
    dash_idx = argv.index("--")
    # The wrapped docker invocation follows the separator.
    assert argv[dash_idx + 1] == "docker"


def test_strace_argv_carries_event_filter() -> None:
    argv = _build_strace_argv("codegenie-trace:abc", ["sh"])
    assert argv[0] == "strace"
    assert "-f" in argv
    assert any(tok.startswith("trace=") for tok in argv)


def test_strace_argv_starts_with_strace_binary() -> None:
    """``argv[0]`` must be the literal ``strace`` so the allowlist check
    sees it."""
    argv = _build_strace_argv("codegenie-trace:abc", ["sh"])
    assert argv[0] == "strace"
