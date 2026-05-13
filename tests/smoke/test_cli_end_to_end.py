"""S4-04 end-to-end smoke suite — the bullet tracer's load-bearing exit.

Every Phase-0 design doc converges on this single sentence:
``codegenie gather <path>`` runs end-to-end on the three fixtures
(``empty_repo``, ``js_only``, ``polyglot``) and the cache hits on the second
run.  This file is where that sentence becomes runtime evidence.

Test layout:

- The metamorphic pair ``test_cache_hit_on_second_run`` +
  ``test_cache_miss_on_tracked_input_edit`` pins the cache invariant in
  both directions. Alone, either is bypassable by a trivially-wrong
  implementation.
- ``test_help_exits_zero_and_lists_flags__group`` /
  ``test_help_exits_zero_and_lists_flags__gather`` exercise click's two
  ``--help`` surfaces and pin the documented exit codes ``{0, 2, 3, 5, 6}``.
- ``test_gather_empty_repo`` / ``test_gather_js_only`` / ``test_gather_polyglot``
  pin the per-fixture ``language_stack`` output as closed-world dicts.
- ``test_envelope_required_fields_present`` pins Phase-0 Goal #1 envelope
  shape (``schema_version`` / ``generated_at`` / ``repo.root`` /
  ``repo.git_commit``).
- ``test_audit_verify_smoke_run`` exercises Phase-0 Goal #9 (the audit
  verifier walks one real run-record without mismatch).
- ``test_gather_js_only`` also embeds the recursive permission scan
  (ADR-0011) and the YAML sanitizer-substring scan (ADR-0008).
"""

from __future__ import annotations

import json
import re
import stat
import sys
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from structlog.testing import capture_logs

from tests.smoke.conftest import _copy_fixture, _install_scandir_counter

# --------------------------------------------------------------------------
# --help smoke (group + gather)
# --------------------------------------------------------------------------


def test_help_exits_zero_and_lists_flags__group() -> None:
    """``codegenie --help`` lists the three subcommands."""
    from codegenie.cli import cli

    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0, result.output
    for subcmd in ("gather", "audit", "cache"):
        assert subcmd in result.output, f"subcommand {subcmd!r} missing from --help"


def test_help_exits_zero_and_lists_flags__gather() -> None:
    """``codegenie gather --help`` lists every documented flag + exit code.

    Flags live on the group ``cli`` (per S4-02): ``--verbose``, ``--version``,
    ``--refresh-tools``, ``--no-gitignore``, ``--auto-gitignore``. The
    ``gather`` subcommand's own ``--help`` shows the ``PATH`` argument and
    the documented exit codes ``{0, 2, 3, 5, 6}``.
    """
    from codegenie.cli import cli

    result = CliRunner().invoke(cli, ["gather", "--help"])
    assert result.exit_code == 0, result.output
    for code in (0, 2, 3, 5, 6):
        assert re.search(rf"\bexit\s+{code}\b", result.output), (
            f"exit code {code} not documented in `gather --help`"
        )

    # The five global flags are documented on the group's --help, not gather's.
    group_help = CliRunner().invoke(cli, ["--help"])
    assert group_help.exit_code == 0
    for flag in ("--verbose", "--version", "--refresh-tools", "--no-gitignore", "--auto-gitignore"):
        assert flag in group_help.output, f"flag {flag!r} missing from group --help"


# --------------------------------------------------------------------------
# Per-fixture smoke
# --------------------------------------------------------------------------


def _invoke_gather(fixture: Path) -> object:
    """Run ``codegenie --no-gitignore gather <fixture>``. Global flags must
    appear BEFORE the subcommand (per click's left-to-right option binding).
    """
    from codegenie.cli import cli

    return CliRunner().invoke(cli, ["--no-gitignore", "gather", str(fixture)])


def _read_envelope(fixture: Path) -> dict[str, object]:
    yaml_path = fixture / ".codegenie" / "context" / "repo-context.yaml"
    assert yaml_path.exists(), f"envelope missing at {yaml_path}"
    return yaml.safe_load(yaml_path.read_text())


def test_gather_empty_repo(tmp_path: Path) -> None:
    fixture = _copy_fixture("empty_repo", tmp_path)
    result = _invoke_gather(fixture)
    assert result.exit_code == 0, result.output
    envelope = _read_envelope(fixture)
    lang_stack = envelope["probes"]["language_detection"]["language_stack"]  # type: ignore[index]
    assert lang_stack["counts"] == {}, f"expected empty counts; got {lang_stack['counts']!r}"
    assert lang_stack["primary"] is None, f"expected primary=None; got {lang_stack['primary']!r}"


def test_gather_js_only(tmp_path: Path) -> None:
    """Per-fixture smoke + ADR-0011 recursive-mode scan + ADR-0008
    sanitizer-substring scan + ADR-0013 schema validation.
    """
    from codegenie.schema.validator import validate

    fixture = _copy_fixture("js_only", tmp_path)
    result = _invoke_gather(fixture)
    assert result.exit_code == 0, result.output

    envelope = _read_envelope(fixture)

    # Closed-world counts: exactly 5 JS files, no ghost zero-count keys.
    lang_stack = envelope["probes"]["language_detection"]["language_stack"]  # type: ignore[index]
    assert lang_stack["counts"] == {"javascript": 5}, (
        f"expected counts == {{'javascript': 5}}; got {lang_stack['counts']!r}"
    )
    assert set(lang_stack["counts"].keys()) == {"javascript"}, "closed-world key set"
    assert lang_stack["primary"] == "javascript"

    # ADR-0013 — strict envelope validates.
    validate(envelope)

    # ADR-0011 recursive permission scan (POSIX only — Phase-0 CI is ubuntu).
    if sys.platform != "win32":
        for p in (fixture / ".codegenie").rglob("*"):
            mode = stat.S_IMODE(p.stat().st_mode)
            if p.is_file():
                assert mode == 0o600, f"file {p} has mode {oct(mode)}; expected 0600"
            elif p.is_dir():
                assert mode == 0o700, f"dir {p} has mode {oct(mode)}; expected 0700"

    # ADR-0008 sanitizer-substring scan: no user-identity prefixes in YAML.
    # ``str(fixture)`` is included as a belt-and-suspenders defense: the
    # CLI redacts ``repo.root`` to the basename, so the full fixture path
    # must not appear anywhere in the rendered envelope.
    yaml_path = fixture / ".codegenie" / "context" / "repo-context.yaml"
    yaml_text = yaml_path.read_text()
    for forbidden in ("/Users/", "/home/", "/root/", str(fixture), str(tmp_path)):
        assert forbidden not in yaml_text, f"substring {forbidden!r} leaked into rendered YAML"


def test_gather_polyglot(tmp_path: Path) -> None:
    fixture = _copy_fixture("polyglot", tmp_path)
    result = _invoke_gather(fixture)
    assert result.exit_code == 0, result.output
    lang_stack = _read_envelope(fixture)["probes"]["language_detection"]["language_stack"]  # type: ignore[index]

    # All five languages, exactly one file each; alpha-tie-break → "go".
    assert lang_stack["counts"] == {
        "go": 1,
        "javascript": 1,
        "python": 1,
        "rust": 1,
        "typescript": 1,
    }, f"unexpected counts: {lang_stack['counts']!r}"
    assert lang_stack["primary"] == "go"


# --------------------------------------------------------------------------
# Envelope-required-fields (Phase-0 Goal #1)
# --------------------------------------------------------------------------


def test_envelope_required_fields_present(tmp_path: Path) -> None:
    """The envelope shape is fixture-independent; pin it once against
    ``js_only`` per ADR-0013.
    """
    import datetime as _dt

    fixture = _copy_fixture("js_only", tmp_path)
    result = _invoke_gather(fixture)
    assert result.exit_code == 0, result.output
    envelope = _read_envelope(fixture)

    assert set(envelope.keys()) == {"schema_version", "generated_at", "repo", "probes"}, (
        f"unknown top-level keys: {set(envelope.keys())}"
    )
    assert isinstance(envelope["schema_version"], str) and envelope["schema_version"]

    generated_at = envelope["generated_at"]
    assert isinstance(generated_at, str) and generated_at
    # ISO-8601 UTC: either "+00:00" or "Z" suffix.
    parseable = generated_at.replace("Z", "+00:00")
    _dt.datetime.fromisoformat(parseable)  # raises if not ISO-8601
    assert generated_at.endswith(("Z", "+00:00")), (
        f"generated_at must be UTC (Z or +00:00); got {generated_at!r}"
    )

    repo = envelope["repo"]
    assert isinstance(repo["root"], str) and repo["root"]
    for forbidden_prefix in ("/Users/", "/home/", "/root/"):
        assert not repo["root"].startswith(forbidden_prefix), (
            f"repo.root leaks {forbidden_prefix!r}"
        )
    # The CLI redacts ``repo.root`` to the basename per the S4-04 attempt
    # log; ``str(fixture)`` must therefore not be a prefix.
    assert not repo["root"].startswith(str(fixture)), (
        f"repo.root leaks str(fixture)={str(fixture)!r}"
    )

    git_commit = repo["git_commit"]
    # Copied fixtures live under tmp_path (not a git worktree) → None.
    assert git_commit is None or re.fullmatch(r"[0-9a-f]{7,40}", str(git_commit)), (
        f"git_commit must be None or 7-40 hex chars; got {git_commit!r}"
    )


# --------------------------------------------------------------------------
# Load-bearing cache-hit + cache-miss metamorphic pair
# --------------------------------------------------------------------------


def test_cache_hit_on_second_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario 2 (phase-arch-design.md §Scenarios). The single most
    important test in Phase 0 — the cache invariant in the HIT direction.
    """
    import codegenie.probes.language_detection as ld_mod

    fixture = _copy_fixture("js_only", tmp_path)

    # Run 1 (cold) — populates the cache; capture cold cache_key.
    with capture_logs() as cold_logs:
        result_cold = _invoke_gather(fixture)
    assert result_cold.exit_code == 0, result_cold.output
    assert (fixture / ".codegenie" / "context" / "repo-context.yaml").exists()
    cold_success = [
        e
        for e in cold_logs
        if e.get("event") == "probe.success"
        and e.get("probe") == "language_detection"
        and "cache_key" in e
    ]
    assert len(cold_success) == 1, f"expected 1 probe.success on cold run, got {len(cold_success)}"
    cold_key = cold_success[0].get("cache_key")
    assert cold_key, "probe.success must carry cache_key (coordinator emits it post-S4-04)"

    # Mutate README.md — NOT in declared_inputs, MUST NOT invalidate the cache.
    readme = fixture / "README.md"
    readme.write_text(readme.read_text() + "\nmore content\n")

    calls = _install_scandir_counter(monkeypatch, ld_mod)

    # Run 2 (warm) — must hit the cache.
    with capture_logs() as warm_logs:
        result_warm = _invoke_gather(fixture)

    assert result_warm.exit_code == 0, result_warm.output
    assert calls["count"] == 0, f"scandir invoked {calls['count']} times on warm run"

    warm_hits = [
        e
        for e in warm_logs
        if e.get("event") == "probe.cache_hit" and e.get("probe") == "language_detection"
    ]
    warm_successes = [
        e
        for e in warm_logs
        if e.get("event") == "probe.success"
        and e.get("probe") == "language_detection"
        and "cache_key" in e
    ]
    assert len(warm_hits) == 1, f"expected 1 probe.cache_hit; got {len(warm_hits)}"
    assert len(warm_successes) == 0, (
        "coordinator-emitted probe.success (with cache_key) must NOT fire on cache-hit warm run"
    )
    assert warm_hits[0].get("cache_key") == cold_key, (
        "cache_key invariance broken across runs: warm key differs from cold key"
    )


def test_cache_miss_on_tracked_input_edit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Metamorphic partner of test_cache_hit_on_second_run.

    Edits ``a.js`` (which IS in ``declared_inputs``) between runs. Cache
    MUST miss. Without this test, a buggy impl that always returns CacheHit
    passes every other AC in the story.
    """
    import codegenie.probes.language_detection as ld_mod

    fixture = _copy_fixture("js_only", tmp_path)

    with capture_logs() as cold_logs:
        result_cold = _invoke_gather(fixture)
    assert result_cold.exit_code == 0, result_cold.output
    cold_success = [
        e
        for e in cold_logs
        if e.get("event") == "probe.success"
        and e.get("probe") == "language_detection"
        and "cache_key" in e
    ]
    assert len(cold_success) == 1, (
        f"expected 1 coordinator-emitted probe.success on cold run; got {len(cold_success)}"
    )
    cold_key = cold_success[0].get("cache_key")

    # Edit a tracked input — a.js IS in declared_inputs.
    a_js = fixture / "a.js"
    a_js.write_text(a_js.read_text() + "// changed\n")

    calls = _install_scandir_counter(monkeypatch, ld_mod)

    with capture_logs() as warm_logs:
        result_warm = _invoke_gather(fixture)

    assert result_warm.exit_code == 0, result_warm.output
    assert calls["count"] > 0, "probe must re-walk on tracked-input change"

    warm_hits = [
        e
        for e in warm_logs
        if e.get("event") == "probe.cache_hit" and e.get("probe") == "language_detection"
    ]
    warm_successes = [
        e
        for e in warm_logs
        if e.get("event") == "probe.success"
        and e.get("probe") == "language_detection"
        and "cache_key" in e
    ]
    assert len(warm_hits) == 0, "cache must NOT hit when a tracked input changed"
    assert len(warm_successes) == 1, (
        "coordinator-emitted probe.success must fire exactly once on cache miss; "
        f"got {len(warm_successes)}"
    )
    assert warm_successes[0].get("cache_key") != cold_key, (
        "cache_key must change when inputs change"
    )


# --------------------------------------------------------------------------
# Audit-verify smoke (Phase-0 Goal #9)
# --------------------------------------------------------------------------


def test_audit_verify_smoke_run(tmp_path: Path) -> None:
    """One gather → one run-record → audit verify exits 0."""
    from codegenie.cli import cli

    fixture = _copy_fixture("js_only", tmp_path)
    result = _invoke_gather(fixture)
    assert result.exit_code == 0, result.output

    runs_dir = fixture / ".codegenie" / "context" / "runs"
    cache_dir = fixture / ".codegenie" / "cache"
    yaml_path = fixture / ".codegenie" / "context" / "repo-context.yaml"

    run_records = list(runs_dir.glob("*.json"))
    assert len(run_records) == 1, f"expected 1 run-record; got {[p.name for p in run_records]}"
    record_name = run_records[0].name
    # The run-record naming convention is ``<utc-iso>-<short>.json`` per audit.py.
    assert re.match(
        r"\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z-[0-9a-f]+\.json", record_name
    ) or re.match(r"\d{8}T\d{6}Z-[0-9a-f]+\.json", record_name), (
        f"unexpected run-record filename: {record_name!r}"
    )

    # Parse the JSON — actual Phase-0 RunRecord shape per audit.py:
    # cli_version, sherpa_commit, python_version, os_kernel_sha, probes[*],
    # tool_versions, yaml_sha256. Each entry under ``probes`` carries
    # ``blob_sha256`` + ``cache_key``.
    record = json.loads(run_records[0].read_text())
    assert "yaml_sha256" in record, "run-record missing yaml_sha256"
    assert "probes" in record, "run-record missing probes"
    assert all("blob_sha256" in p for p in record["probes"]), (
        "every probes[*] row must carry blob_sha256"
    )

    verify_result = CliRunner().invoke(
        cli,
        [
            "audit",
            "verify",
            "--runs-dir",
            str(runs_dir),
            "--cache-dir",
            str(cache_dir),
            "--yaml-path",
            str(yaml_path),
        ],
        catch_exceptions=False,
    )
    assert verify_result.exit_code == 0, (
        f"audit verify exited {verify_result.exit_code}; output={verify_result.output!r}"
    )
