"""S4-02 — CLI exit-code dispatch table (AC-4, AC-9, AC-11, AC-21).

Pins the ``{CodegenieError-subclass: exit-code}`` mapping with a snapshot
test (mutation defense — a 5↔6 swap would fail loudly) and a parametrized
end-to-end exercise that patches the resolved ``_run_gather_pipeline`` seam
inside :mod:`codegenie.cli`. Lazy-imports mean patching the upstream module
is a no-op — the dispatch happens at the CLI's import-of-the-class shape.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from codegenie.errors import (
    AllProbesFailedError,
    SchemaValidationError,
    SecretLikelyFieldNameError,
    SymlinkRefusedError,
)


@pytest.fixture()
def tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ``Path.home()`` and ``$HOME`` to a fresh tmp dir."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    # ``Path.home()`` on POSIX reads $HOME — but bind it for the duration
    # so resolver caching does not surprise us.
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


def test_dispatch_table_snapshot() -> None:
    """AC-9 — locks the dispatch table contents. Adding a code requires
    a story amendment + this snapshot's update — prevents silent drift."""
    from codegenie.cli import _EXIT_CODE_DISPATCH

    assert _EXIT_CODE_DISPATCH == {
        AllProbesFailedError: 2,
        SchemaValidationError: 3,
        SymlinkRefusedError: 5,
        SecretLikelyFieldNameError: 6,
    }


@pytest.mark.parametrize(
    ("exc_cls", "expected_code"),
    [
        (AllProbesFailedError, 2),
        (SchemaValidationError, 3),
        (SymlinkRefusedError, 5),
        (SecretLikelyFieldNameError, 6),
    ],
)
def test_documented_error_maps_to_documented_exit_code(
    tmp_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exc_cls: type[Exception],
    expected_code: int,
) -> None:
    """AC-9 — each :class:`CodegenieError` subclass maps to its documented
    gather exit code. Swap 5↔6 in the table → this test fails."""
    from codegenie import cli as cli_mod

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.js").write_text("//")

    def _raise(*_a: object, **_kw: object) -> None:
        raise exc_cls("synthetic")

    monkeypatch.setattr(cli_mod, "_run_gather_pipeline", _raise)
    result = CliRunner().invoke(cli_mod.cli, ["gather", str(repo)])
    assert result.exit_code == expected_code, result.output


def test_gather_help_lists_documented_exit_codes_only() -> None:
    """AC-4 — gather's --help text documents codes 0/2/3/5/6 and does NOT
    document code 4 (audit verify's) or code 1 (click fallback)."""
    from codegenie.cli import cli

    out = CliRunner().invoke(cli, ["gather", "--help"]).output.lower()
    for code in ("0", "2", "3", "5", "6"):
        assert f"exit {code}" in out, f"gather --help missing exit code {code}"
    assert "exit 4" not in out, "exit 4 is owned by `audit verify`, not gather"
    assert "exit 1" not in out, "exit 1 is the click fallback, not part of gather's contract"


def test_gather_happy_path_writes_language_stack(tmp_home: Path, tmp_path: Path) -> None:
    """AC-12 (Goal trace) — happy path produces a YAML whose
    ``probes.language_detection.language_stack`` is a non-empty dict."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.js").write_text("// hi")

    from codegenie.cli import cli

    result = CliRunner().invoke(cli, ["gather", str(repo)])
    assert result.exit_code == 0, result.output
    yaml_path = repo / ".codegenie" / "context" / "repo-context.yaml"
    assert yaml_path.exists()
    envelope = yaml.safe_load(yaml_path.read_text())
    stack = envelope["probes"]["language_detection"]["language_stack"]
    assert isinstance(stack, dict) and stack, f"language_stack must be non-empty; got {stack!r}"
    assert stack.get("primary") == "javascript"
    assert isinstance(stack.get("counts"), dict) and stack["counts"]
    # AC-11 cousin — audit record written alongside the envelope.
    runs = list((repo / ".codegenie" / "context" / "runs").glob("*.json"))
    assert len(runs) == 1


def test_gather_exits_2_leaves_no_yaml_but_writes_audit(
    tmp_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-11 — exit 2 (all probes failed): NO repo-context.yaml; audit
    record IS still written under runs/."""
    from codegenie import cli as cli_mod
    from codegenie.coordinator.coordinator import GatherResult

    # Force coordinator to return empty outputs → AllProbesFailedError → exit 2.
    monkeypatch.setattr(
        cli_mod,
        "_seam_coordinator_gather",
        lambda *a, **kw: GatherResult(outputs={}, executions={}),
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.js").write_text("//")
    result = CliRunner().invoke(cli_mod.cli, ["gather", str(repo)])
    assert result.exit_code == 2, result.output
    ctx_dir = repo / ".codegenie" / "context"
    assert not (ctx_dir / "repo-context.yaml").exists()
    assert any((ctx_dir / "runs").glob("*.json")), "audit record must still be written on exit 2"


def test_exit_3_writes_invalid_only(
    tmp_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-4 — exit 3 writes ``repo-context.yaml.invalid`` AND does NOT
    write ``repo-context.yaml``. The .invalid sibling contains the
    rejected envelope (no empty-file shortcut)."""
    from codegenie import cli as cli_mod

    def _fail_validate(_env: object) -> None:
        raise SchemaValidationError("synthetic")

    monkeypatch.setattr(cli_mod, "_seam_validate_envelope", _fail_validate)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.js").write_text("//")
    result = CliRunner().invoke(cli_mod.cli, ["gather", str(repo)])
    assert result.exit_code == 3, result.output
    ctx_dir = repo / ".codegenie" / "context"
    assert (ctx_dir / "repo-context.yaml.invalid").exists()
    assert not (ctx_dir / "repo-context.yaml").exists()
    parsed = yaml.safe_load((ctx_dir / "repo-context.yaml.invalid").read_text())
    assert parsed and isinstance(parsed, dict)
    assert "probes" in parsed


def test_exit_5_when_output_yaml_is_symlink(tmp_home: Path, tmp_path: Path) -> None:
    """AC-4 + ADR-0008 — Writer refuses to follow the planted symlink and
    surfaces ``SymlinkRefusedError`` → exit 5. Decoy untouched."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.js").write_text("//")
    ctx_dir = repo / ".codegenie" / "context"
    ctx_dir.mkdir(parents=True)
    decoy = tmp_path / "decoy.yaml"
    decoy.write_text("# attacker controlled\n")
    (ctx_dir / "repo-context.yaml").symlink_to(decoy)

    from codegenie.cli import cli

    result = CliRunner().invoke(cli, ["gather", str(repo)])
    assert result.exit_code == 5, result.output
    assert decoy.read_text() == "# attacker controlled\n", "decoy must not be written through"


def test_exit_6_via_sanitizer_when_validator_bypassed(
    tmp_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-21 — Scenario 4 defense-in-depth. Even if
    :class:`_ProbeOutputValidator` is a pass-through no-op, the real
    :meth:`OutputSanitizer.scrub` (running inside the coordinator) repeats
    the secret-field pass and raises :class:`SecretLikelyFieldNameError`,
    which the CLI dispatches to exit 6.

    The test drives the **real** coordinator and the **real** sanitizer.
    Only the Pydantic validator is monkey-patched to a no-op so the
    sanitizer's pass is the only thing that can refuse the bad output."""
    from codegenie import cli as cli_mod
    from codegenie.coordinator import validator as validator_mod
    from codegenie.probes.base import Probe, ProbeOutput

    class _SecretLeakingProbe(Probe):
        name: str = "_secret_leak_test"
        version: str = "0.0.1"
        layer = "A"
        tier = "task_specific"
        applies_to_tasks: list[str] = ["*"]
        applies_to_languages: list[str] = ["*"]
        requires: list[str] = []
        declared_inputs: list[str] = ["**/*.js"]

        async def run(self, repo: object, ctx: object) -> ProbeOutput:
            return ProbeOutput(
                schema_slice={"github_token": "ghp_x"},
                raw_artifacts=[],
                confidence="high",
                duration_ms=1,
                warnings=[],
                errors=[],
            )

    # Bypass the Pydantic validator so the sanitizer is the only barrier.
    class _NoopValidator:
        @classmethod
        def model_validate(cls, _payload: object) -> None:
            return None

    monkeypatch.setattr(validator_mod, "_ProbeOutputValidator", _NoopValidator)

    # Have the registry seam return our secret-leaking probe instance.
    monkeypatch.setattr(cli_mod, "_seam_registry_for_task", lambda: [_SecretLeakingProbe()])

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.js").write_text("//")
    result = CliRunner().invoke(cli_mod.cli, ["gather", str(repo)])
    assert result.exit_code == 6, result.output


@pytest.mark.parametrize(
    ("scenario", "expected_exit"),
    [
        ("one_ran", 0),
        ("one_cachehit", 0),
        ("one_errored_ran", 2),
        ("one_skipped", 2),
        ("mix_ran_and_errored", 0),
    ],
)
def test_exit_code_policy_per_adr_0009(
    tmp_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    expected_exit: int,
) -> None:
    """AC-6 — exit 0 if ``len(outputs) >= 1`` else exit 2 (per ADR-0009).
    CacheHit counts as success; Ran-with-errors contributes to ``outputs``
    only if the coordinator left it there; errored Ran omits the entry."""
    from codegenie import cli as cli_mod
    from codegenie.coordinator.coordinator import (
        CacheHit,
        GatherResult,
        Ran,
        Skipped,
    )
    from codegenie.output.sanitizer import SanitizedProbeOutput

    good = SanitizedProbeOutput(
        schema_slice={"language_stack": {"counts": {"javascript": 1}, "primary": "javascript"}},
        raw_artifacts=[],
        confidence="high",
        duration_ms=1,
        warnings=[],
        errors=[],
    )

    if scenario == "one_ran":
        executions: dict[str, object] = {"p": Ran(output=good, key="k")}
        outputs: dict[str, SanitizedProbeOutput] = {"p": good}
    elif scenario == "one_cachehit":
        executions = {"p": CacheHit(output=good, key="k")}
        outputs = {"p": good}
    elif scenario == "one_errored_ran":
        # Errored Ran does NOT contribute to ``outputs`` per coordinator
        # contract — story Notes for implementer explicitly call this out.
        executions = {"p": Ran(output=good, key="k")}
        outputs = {}
    elif scenario == "one_skipped":
        executions = {"p": Skipped(reason="applies_false")}
        outputs = {}
    else:  # mix_ran_and_errored
        executions = {
            "p1": Ran(output=good, key="k1"),
            "p2": Ran(output=good, key="k2"),  # the "errored" sibling
        }
        outputs = {"p1": good}  # only the clean one contributes

    monkeypatch.setattr(
        cli_mod,
        "_seam_coordinator_gather",
        lambda *a, **kw: GatherResult(outputs=outputs, executions=executions),
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.js").write_text("//")
    result = CliRunner().invoke(cli_mod.cli, ["gather", str(repo)])
    assert result.exit_code == expected_exit, (
        f"{scenario}: expected exit {expected_exit}, got {result.exit_code}\n{result.output}"
    )


def test_exit_2_run_record_reflects_failures(
    tmp_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-11 — the audit record written on exit 2 carries probe entries
    whose ``exit_status`` reflects the failure."""
    import json

    from codegenie import cli as cli_mod
    from codegenie.coordinator.coordinator import GatherResult, Skipped

    monkeypatch.setattr(
        cli_mod,
        "_seam_coordinator_gather",
        lambda *a, **kw: GatherResult(
            outputs={}, executions={"language_detection": Skipped(reason="synthetic")}
        ),
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.js").write_text("//")
    result = CliRunner().invoke(cli_mod.cli, ["gather", str(repo)])
    assert result.exit_code == 2

    runs_dir = repo / ".codegenie" / "context" / "runs"
    records = list(runs_dir.glob("*.json"))
    assert records
    record = json.loads(records[0].read_text())
    assert record["probes"][0]["exit_status"] == "skipped"


# Ensure module fixtures survive the lint pass on os import (used by future
# extension; keep the import to anchor the fixture file's typed dependency).
_ = os
