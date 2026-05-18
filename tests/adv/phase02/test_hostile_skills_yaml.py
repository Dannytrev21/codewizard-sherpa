"""Adversarial — hostile YAML against :class:`SkillsLoader`.

Story S7-04, AC-1 → AC-6 + AC-29.

Each parametrized case feeds a hostile ``SKILL.md`` to ``SkillsLoader``
through its public ``load_all()`` API. The closed reason set per
``src/codegenie/skills/loader.py`` is ``{symlink_refused, unsafe_yaml,
frontmatter_unterminated, schema, io_failure}``; the test asserts every
hostile case lands inside that set.

Additional invariants per case:

* No user code executes (no ``/tmp/pwned-*`` marker created).
* No host-state mutation (env / signals).
* Wall-clock per case < 5 seconds (DoS-resistance per AC-4).
* Per-file errors land in ``LoadOutcome.per_file_errors`` (the loader
  uses a partial-success shape — fatal errors are reserved for "all
  tiers unreadable"; per-skill failures are values inside the
  successful outcome).

This is the **behavioural** counterpart to the structural redactor /
writer invariants in ``test_no_inmemory_secret_leak.py``.
"""

from __future__ import annotations

import os
import signal
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest

# Importing ``codegenie.skills`` first triggers a known circular through
# ``probes.layer_b.dep_graph → depgraph.registry → types.identifiers``
# (only partially initialised at that point). Loading the cache + output
# packages first fully initialises the shared types.identifiers module
# and breaks the cycle; the existing unit tests rely on the same
# precondition (their conftest imports ``CacheStore`` / ``OutputSanitizer``
# before ``codegenie.skills``).
from codegenie.cache.store import CacheStore as _CacheStore  # noqa: F401  (ordering import)
from codegenie.output.sanitizer import (
    OutputSanitizer as _OutputSanitizer,  # noqa: F401  (ordering import)
)
from codegenie.result import Ok
from codegenie.skills import SkillsLoader

_FIXTURES_DIR: Final[Path] = Path(__file__).parent / "fixtures" / "hostile_skills"
_PWNED_MARKER: Final[Path] = Path("/tmp/pwned-hostile-skills-test")
_ALLOWED_REASONS: Final[frozenset[str]] = frozenset(
    {
        "symlink_refused",
        "unsafe_yaml",
        "frontmatter_unterminated",
        "schema",
        "io_failure",
    }
)


@dataclass(frozen=True)
class _HostileCase:
    """A parametrized hostile-YAML scenario.

    ``allowed_reasons`` is the *set* of acceptable error reasons (not a
    single value) because some hostile payloads can land in more than
    one bucket depending on parser path — e.g., a deeply-nested mapping
    may either trip the depth cap (``unsafe_yaml`` after the S7-04 fix)
    or violate the schema once parsed (``schema``). The closed-set
    invariant matters; the exact bucket within the closed set does not.
    """

    name: str
    fixture: str  # relative to _FIXTURES_DIR
    allowed_reasons: frozenset[str]


_CASES: Final[tuple[_HostileCase, ...]] = (
    _HostileCase("python_object", "case01_python_object.md", frozenset({"unsafe_yaml"})),
    _HostileCase(
        "python_object_apply", "case02_python_object_apply.md", frozenset({"unsafe_yaml"})
    ),
    _HostileCase("deep_nesting", "case03_deep_nesting.md", frozenset({"unsafe_yaml"})),
    _HostileCase("top_level_list", "case04_top_level_list.md", frozenset({"unsafe_yaml"})),
    _HostileCase("schema_missing_id", "case05_schema_missing_id.md", frozenset({"schema"})),
    _HostileCase("schema_extra_field", "case06_schema_extra_field.md", frozenset({"schema"})),
    _HostileCase(
        "unterminated_frontmatter",
        "case07_unterminated_frontmatter.md",
        frozenset({"frontmatter_unterminated"}),
    ),
    _HostileCase(
        "alias_chain",
        "case08_alias_chain.md",
        frozenset({"unsafe_yaml", "schema"}),
    ),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_tier_with(fixture_bytes: bytes, tier_root: Path) -> None:
    """Plant a single ``SKILL.md`` under *tier_root* (the loader walks ``rglob('SKILL.md')``)."""
    skill_dir = tier_root / "hostile-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_bytes(fixture_bytes)


def _snapshot_env() -> tuple[dict[str, str], dict[int, signal.Handlers]]:
    """Capture ``os.environ`` + key signal handlers for AC-3 host-state checks."""
    env_copy = dict(os.environ)
    handlers: dict[int, signal.Handlers] = {}
    # SIGTERM/SIGUSR1/SIGUSR2 — common targets for sneaky payloads.
    for sig in (signal.SIGTERM, signal.SIGUSR1, signal.SIGUSR2):
        handlers[sig] = signal.getsignal(sig)
    return env_copy, handlers


# ---------------------------------------------------------------------------
# Parametrized hostile-YAML cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _CASES, ids=lambda c: c.name)
def test_hostile_skill_yaml_refused(case: _HostileCase, tmp_path: Path) -> None:
    """AC-1 / AC-2 / AC-3 / AC-4 / AC-5 — every hostile case surfaces a typed error."""
    fixture_path = _FIXTURES_DIR / case.fixture
    assert fixture_path.exists(), f"fixture missing: {fixture_path}"

    _PWNED_MARKER.unlink(missing_ok=True)
    assert not _PWNED_MARKER.exists(), "stale pwned marker — clean and retry"

    tier_root = tmp_path / "skills-tier"
    _build_tier_with(fixture_path.read_bytes(), tier_root)

    env_before, handlers_before = _snapshot_env()

    t0 = time.monotonic()
    result = SkillsLoader(search_paths=[tier_root]).load_all()
    elapsed = time.monotonic() - t0

    # AC-4 — DoS-resistance: any case taking > 5 s is a real loader bug.
    assert elapsed < 5.0, (
        f"hostile case {case.name!r} took {elapsed:.3f}s — over the 5-second cap. "
        f"This is a real DoS surface; fix the loader / safe_yaml chokepoint."
    )

    # AC-2 — no user code executed.
    assert not _PWNED_MARKER.exists(), (
        f"!!python/object payload executed in case {case.name!r} — security regression"
    )

    # AC-3 — no host-state mutation.
    assert dict(os.environ) == env_before, (
        f"hostile case {case.name!r} mutated os.environ — host-state mutation"
    )
    for sig, expected in handlers_before.items():
        assert signal.getsignal(sig) == expected, (
            f"hostile case {case.name!r} mutated signal handler for {sig}"
        )

    # ``load_all()`` returns a *successful* outcome containing per-file
    # errors — the FatalLoadError shape is reserved for "every tier
    # unreadable". One bad SKILL.md must NOT escalate to a Result.Err.
    assert isinstance(result, Ok), (
        f"hostile case {case.name!r} produced a fatal Result.Err; the loader "
        f"should isolate per-file errors inside LoadOutcome.per_file_errors"
    )
    outcome = result.value
    assert not outcome.skills, (
        f"hostile case {case.name!r} produced a parsed Skill; expected zero successful skills"
    )
    assert outcome.per_file_errors, (
        f"hostile case {case.name!r} produced no per-file errors — the hostile "
        f"payload was silently accepted"
    )

    # AC-5 — every per-file error has a reason from the closed allowlisted set.
    for err in outcome.per_file_errors:
        assert err.reason in _ALLOWED_REASONS, (
            f"hostile case {case.name!r} produced reason={err.reason!r} "
            f"outside the closed set {sorted(_ALLOWED_REASONS)!r}"
        )

    # AC-5 (case-specific) — the reason must be one of the case's allowed bucket(s).
    reasons_seen = {err.reason for err in outcome.per_file_errors}
    assert reasons_seen & case.allowed_reasons, (
        f"hostile case {case.name!r} produced reasons {sorted(reasons_seen)!r} "
        f"but expected one of {sorted(case.allowed_reasons)!r}"
    )


# ---------------------------------------------------------------------------
# Built-at-test-time cases (symlink-escape, non-UTF8). Not committed to git
# per AC-6 — symlinks and invalid-UTF8 names interact poorly with git on
# non-POSIX platforms.
# ---------------------------------------------------------------------------


def test_symlink_escape_refused(tmp_path: Path) -> None:
    """AC-1 case 5 — symlink-escape filename is refused via ``O_NOFOLLOW``."""
    tier_root = tmp_path / "skills-tier"
    skill_dir = tier_root / "hostile-skill"
    skill_dir.mkdir(parents=True)
    out_of_tree = tmp_path / "out-of-tree.md"
    out_of_tree.write_text("---\nid: out-of-tree\n---\n", encoding="utf-8")
    (skill_dir / "SKILL.md").symlink_to(out_of_tree)

    t0 = time.monotonic()
    result = SkillsLoader(search_paths=[tier_root]).load_all()
    elapsed = time.monotonic() - t0
    assert elapsed < 5.0

    assert isinstance(result, Ok)
    outcome = result.value
    reasons = {err.reason for err in outcome.per_file_errors}
    assert "symlink_refused" in reasons, (
        f"symlink-escape was not refused; per-file reasons: {sorted(reasons)!r}"
    )


def test_non_utf8_payload_refused(tmp_path: Path) -> None:
    """AC-1 case 10 — non-UTF8 bytes inside the frontmatter are refused."""
    tier_root = tmp_path / "skills-tier"
    skill_dir = tier_root / "hostile-skill"
    skill_dir.mkdir(parents=True)
    # Valid frontmatter delimiters but invalid UTF-8 bytes inside; YAML
    # parser surfaces a decoding error → MalformedYAMLError → unsafe_yaml.
    payload = b"---\nid: hostile-non-utf8\nbroken: \xff\xfe\n---\nbody\n"
    (skill_dir / "SKILL.md").write_bytes(payload)

    t0 = time.monotonic()
    result = SkillsLoader(search_paths=[tier_root]).load_all()
    elapsed = time.monotonic() - t0
    assert elapsed < 5.0

    assert isinstance(result, Ok)
    outcome = result.value
    assert not outcome.skills
    reasons = {err.reason for err in outcome.per_file_errors}
    assert reasons & {"unsafe_yaml", "schema"}, (
        f"non-UTF8 payload was not refused; reasons: {sorted(reasons)!r}"
    )
    for err in outcome.per_file_errors:
        assert err.reason in _ALLOWED_REASONS


# ---------------------------------------------------------------------------
# Structured-log-emission assertion — AC-29.
#
# Every per-file error path also emits a ``skill.load_failed`` log event
# (see loader.py:441 ``_logger.warning(_EVENT_LOAD_FAILED, ...)``). This
# is the structured-log discipline the cross-cutting probe contract
# expects; we assert the discipline holds for the hostile-input path.
# ---------------------------------------------------------------------------


def test_load_failed_event_emitted_for_hostile_input(tmp_path: Path) -> None:
    """AC-29 — the loader emits a structured ``skill_load_failed`` event."""
    import structlog.testing

    fixture_path = _FIXTURES_DIR / "case01_python_object.md"
    tier_root = tmp_path / "skills-tier"
    _build_tier_with(fixture_path.read_bytes(), tier_root)

    with structlog.testing.capture_logs() as logs:
        result = SkillsLoader(search_paths=[tier_root]).load_all()

    assert isinstance(result, Ok)
    assert result.value.per_file_errors
    relevant = [
        rec
        for rec in logs
        if rec.get("event") == "skill_load_failed" and rec.get("reason") == "unsafe_yaml"
    ]
    assert relevant, (
        f"expected a 'skill_load_failed' structured event with reason='unsafe_yaml'; "
        f"got logs={logs!r}"
    )


# Defensive: ensure no stale marker survives a test-suite re-run.
@pytest.fixture(autouse=True)
def _cleanup_pwned_marker() -> None:
    _PWNED_MARKER.unlink(missing_ok=True)
    yield
    _PWNED_MARKER.unlink(missing_ok=True)
