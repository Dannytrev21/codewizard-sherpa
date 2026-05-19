"""S3-03 — AC-N3 + AC-N4 cold-start fences.

``import codegenie.vuln_index.parsers`` must NOT pull ``alembic`` or
``urllib.request`` into ``sys.modules`` — lazy-imported inside
``Feed.fetch`` method bodies + ``_apply_migrations``. ``import
codegenie.cli`` must NOT pull ``alembic`` either.

Run in fresh subprocesses so results are honest regardless of what the
broader pytest collection has already loaded.
"""

from __future__ import annotations

import subprocess
import sys


def _run(code: str) -> str:
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, (
        f"subprocess failed: stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    return proc.stdout.strip().splitlines()[-1]


def test_importing_parsers_does_not_load_alembic_or_urllib_request() -> None:
    code = (
        "import sys\n"
        "before = set(sys.modules)\n"
        "import codegenie.vuln_index.parsers  # noqa: F401\n"
        "after = set(sys.modules) - before\n"
        "leaked = sorted(\n"
        "    m for m in after if m.startswith(('alembic', 'urllib.request', 'sqlalchemy'))\n"
        ")\n"
        "print('LEAKED:' + ','.join(leaked) if leaked else 'OK')\n"
    )
    last = _run(code)
    assert last == "OK", f"AC-N3 violation: parsers import leaked heavy deps: {last}"


def test_importing_cli_does_not_load_alembic() -> None:
    code = (
        "import sys\n"
        "before = set(sys.modules)\n"
        "import codegenie.cli  # noqa: F401\n"
        "after = set(sys.modules) - before\n"
        "leaked = sorted(m for m in after if m.startswith('alembic'))\n"
        "print('LEAKED:' + ','.join(leaked) if leaked else 'OK')\n"
    )
    last = _run(code)
    assert last == "OK", f"AC-N4 violation: cli import leaked alembic: {last}"


def test_importing_vuln_index_package_does_not_load_urllib_request() -> None:
    """Extends S3-02 cold-start: the new feed modules must NOT pull urllib.request."""
    code = (
        "import sys\n"
        "before = set(sys.modules)\n"
        "import codegenie.vuln_index  # noqa: F401\n"
        "after = set(sys.modules) - before\n"
        "leaked = sorted(m for m in after if m.startswith('urllib.request'))\n"
        "print('LEAKED:' + ','.join(leaked) if leaked else 'OK')\n"
    )
    last = _run(code)
    assert last == "OK", (
        f"AC-N3 violation: codegenie.vuln_index import leaked urllib.request: {last}"
    )
