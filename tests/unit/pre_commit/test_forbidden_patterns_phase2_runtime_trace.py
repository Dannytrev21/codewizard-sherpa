"""Forbidden-patterns coverage for ``probes/layer_c/runtime_trace.py``.

Mirrors S5-01 AC-11's shape: synthesize source under a Layer C path and
assert the hook script exits non-zero. Negative coverage: same source
under ``probes/layer_a/`` exits zero (the predicate is path-scoped).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK_SCRIPT = REPO_ROOT / "scripts" / "check_forbidden_patterns.py"


def _run_hook(target: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


@pytest.mark.parametrize(
    "snippet",
    [
        "SomeModel.model_construct(value=1)\n",
        "import subprocess\nsubprocess.run(['true'])\n",
        "import asyncio\nasyncio.create_subprocess_exec('true')\n",
    ],
    ids=["model_construct", "subprocess_run", "create_subprocess_exec"],
)
def test_layer_c_synthetic_source_trips_hook(
    tmp_path: Path,
    snippet: str,
) -> None:
    """Synthetic source under ``probes/layer_c/`` trips the hook non-zero
    and emits both ``02-ADR-0010 §Decision`` and ``production ADR-0033 §3``
    substrings (the two cited references in the rule's advice).
    """
    target = tmp_path / "codegenie" / "probes" / "layer_c" / "synth_runtime_trace.py"
    target.parent.mkdir(parents=True)
    target.write_text(snippet)

    rc, out = _run_hook(target)
    assert rc != 0, f"hook should reject Layer C synthetic source; got rc=0, out={out!r}"
    assert "02-ADR-0010" in out
    assert "production ADR-0033 §3" in out


@pytest.mark.parametrize(
    "snippet",
    [
        "SomeModel.model_construct(value=1)\n",
        "import subprocess\nsubprocess.run(['true'])\n",
        "import asyncio\nasyncio.create_subprocess_exec('true')\n",
    ],
    ids=["model_construct", "subprocess_run", "create_subprocess_exec"],
)
def test_layer_a_synthetic_source_does_not_trip_layer_c_rules(
    tmp_path: Path,
    snippet: str,
) -> None:
    """Negative coverage: the same source under ``probes/layer_a/`` does NOT
    fire the Layer C-scoped rules. (Other repo-wide rules may fire; this
    test only asserts the layer-C predicate is path-scoped — checks the
    advice substring is absent.)"""
    target = tmp_path / "codegenie" / "probes" / "layer_a" / "synth.py"
    target.parent.mkdir(parents=True)
    target.write_text(snippet)

    _rc, out = _run_hook(target)
    # The Layer C-rule's specific advice cites ``probes/layer_c/**``.
    assert "probes/layer_c/**" not in out
