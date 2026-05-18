"""S8-03 AC-11 — ``ProbeContext`` widening allowlist + ``--check`` flag.

The ``contract-freeze`` CI lane (S8-03) promotes the Phase-0 probe-contract
test to its own top-level job AND runs the regen script with ``--check`` so
a non-allowlisted ``ProbeContext`` field is rejected at PR time (not after
a silent ``regen``).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Ensure the script is importable as a module (it lives in scripts/, not under
# any package). The repo root is two parents up from this file.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO_ROOT / "scripts" / "regen_probe_contract_snapshot.py"
_SNAPSHOT = _REPO_ROOT / "tests" / "snapshots" / "probe_contract.v1.json"

sys.path.insert(0, str(_REPO_ROOT / "scripts"))
import regen_probe_contract_snapshot as regen  # noqa: E402


def test_allowlist_names_exactly_eight_fields() -> None:
    """AC-11(b) — the allowlist matches the Phase-0 base ∪ Phase-1/2 widenings."""
    expected = {
        "cache_dir",
        "output_dir",
        "workspace",
        "logger",
        "config",
        "parsed_manifest",
        "input_snapshot",
        "image_digest_resolver",
    }
    assert regen._PROBE_CONTEXT_FIELD_ALLOWLIST == expected


def test_committed_snapshot_contains_image_digest_resolver() -> None:
    """AC-11(a) — the committed snapshot has the Phase-2 widening field."""
    raw = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))
    fields = raw["structural_signature"]["ProbeContext"]["fields"]
    names = {f["name"] for f in fields}
    assert "image_digest_resolver" in names


@pytest.mark.parametrize("offender", ["foo", "bar", "parsed_manifest_v2", "__init__"])
def test_third_additive_field_raises_value_error_with_adr_pointer(offender: str) -> None:
    """AC-11(c) — a non-allowlisted field triggers ValueError naming the ADR."""
    fake_signature = {
        "ProbeContext": {
            "bases": ["object"],
            "decorators": [],
            "fields": [
                {"name": name, "type": "str", "default": None}
                for name in regen._PROBE_CONTEXT_FIELD_ALLOWLIST
            ]
            + [{"name": offender, "type": "str", "default": None}],
            "methods": [],
            "class_attributes": [],
        }
    }
    with pytest.raises(ValueError, match="02-ADR-0004"):
        regen._enforce_probe_context_allowlist(fake_signature)


def test_check_flag_succeeds_on_master() -> None:
    """AC-11(d) — ``--check`` exits 0 when the committed snapshot is up to date."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--check"],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (
        f"--check must exit 0 on master; got {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_check_flag_detects_snapshot_drift(tmp_path: Path) -> None:
    """AC-11(d) — ``--check`` exits 1 when the snapshot disagrees with live state.

    Implementation detail: we monkey-patch the script's ``SNAPSHOT_PATH`` to
    a tmp file with mutated contents and call ``main`` programmatically.
    """
    drifted = tmp_path / "probe_contract.v1.json"
    real = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))
    real["doc_fingerprint"] = "0" * 64  # mutate so the live build won't match
    drifted.write_text(json.dumps(real, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    orig = regen.SNAPSHOT_PATH
    regen.SNAPSHOT_PATH = drifted
    try:
        rc = regen.main(["--check"])
    finally:
        regen.SNAPSHOT_PATH = orig
    assert rc == 1, "--check must exit 1 on snapshot drift"


def test_contract_freeze_workflow_job_invokes_check() -> None:
    """AC-11(d) — the CI lane runs the regen helper with ``--check``."""
    from tests.unit.ci._workflow_model import WorkflowFile

    wf = WorkflowFile.from_path(_REPO_ROOT / ".github" / "workflows" / "ci.yml")
    cf = wf.jobs["contract-freeze"]
    run_text = "\n".join(s.run or "" for s in cf.steps)
    assert "regen_probe_contract_snapshot.py" in run_text
    assert "--check" in run_text, "contract-freeze lane must invoke the helper with --check"
