"""S4-02 — AC-3 runtime cold-start invariant.

Spawns a child Python that imports :mod:`codegenie.cli`, invokes ``--help``
and ``--version`` through the :class:`click.testing.CliRunner`, then prints
the leaked heavy modules + both exit codes. A sentinel string guards against
the false-pass shape where the child crashes before the leak check runs.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_help_and_version_keep_heavy_modules_out_of_sys_modules() -> None:
    """AC-3 — exit 0 on both ``--help`` and ``--version`` AND no heavy
    module enters ``sys.modules``. The sentinel ``"OK"`` is required so a
    child-process crash before the leak check is NOT a false-pass."""
    probe = (
        "import sys, json;"
        " from codegenie.cli import cli;"
        " from click.testing import CliRunner;"
        " r1 = CliRunner().invoke(cli, ['--help']);"
        " r2 = CliRunner().invoke(cli, ['--version']);"
        " heavy = {'yaml','jsonschema','pydantic','blake3','structlog'};"
        " leaked = sorted(k for k in sys.modules if k.split('.')[0] in heavy);"
        " print(json.dumps({'leaked':leaked,"
        " 'help_exit':r1.exit_code,'version_exit':r2.exit_code,"
        " 'sentinel':'OK'}))"
    )
    out = subprocess.check_output(
        [sys.executable, "-c", probe],
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=30,
    )
    data = json.loads(out.strip().splitlines()[-1])
    assert data["sentinel"] == "OK", "child process did not reach the leak check"
    assert data["help_exit"] == 0, f"--help exited {data['help_exit']}"
    assert data["version_exit"] == 0, f"--version exited {data['version_exit']}"
    assert data["leaked"] == [], (
        f"--help / --version leaked heavy modules: {data['leaked']}. "
        "Move the offending import inside a command body (use "
        "``importlib.import_module`` so the AST scan stays clean too)."
    )
