"""S3-02 — AC-L2 cold-start fence.

``import codegenie.vuln_index`` must NOT pull ``alembic`` or ``sqlalchemy``
into ``sys.modules`` — Alembic is lazy-imported inside
:meth:`VulnIndex._upgrade` only.

Run in a fresh subprocess so the result is honest regardless of what the
broader pytest collection has already loaded.
"""

from __future__ import annotations

import subprocess
import sys


def test_importing_vuln_index_does_not_load_alembic() -> None:
    code = (
        "import sys\n"
        "before = set(sys.modules)\n"
        "import codegenie.vuln_index  # noqa: F401\n"
        "after = set(sys.modules) - before\n"
        "leaked = sorted(m for m in after if m.startswith(('alembic', 'sqlalchemy')))\n"
        "if leaked:\n"
        "    print('LEAKED:' + ','.join(leaked))\n"
        "else:\n"
        "    print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, (
        f"subprocess failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    last = result.stdout.strip().splitlines()[-1]
    assert last == "OK", f"AC-L2 violation: import codegenie.vuln_index loaded heavy deps: {last}"
