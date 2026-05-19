"""S3-02 — Alembic upgrade fixture (in-process, no subprocess).

AC-E2 — Alembic invocation is pinned to ``alembic.command.upgrade(cfg, "head")``;
ALLOWED_BINARIES is not amended for this story.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def alembic_upgrade():  # type: ignore[no-untyped-def]
    def _upgrade(db: Path) -> None:
        # Lazy imports — keep alembic out of bare ``import codegenie.vuln_index``
        # closure even when the fixture is collected.
        from alembic import command  # noqa: PLC0415
        from alembic.config import Config  # noqa: PLC0415

        cfg = Config()
        cfg.set_main_option(
            "script_location",
            "src/codegenie/vuln_index/migrations",
        )
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
        command.upgrade(cfg, "head")

    return _upgrade
