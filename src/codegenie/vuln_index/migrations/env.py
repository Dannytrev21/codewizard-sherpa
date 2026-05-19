"""Alembic environment for the ``VulnIndex`` sqlite store (S3-02).

The Alembic ``Config`` passed in by :meth:`VulnIndex._upgrade` (and by the
``alembic_upgrade`` test fixture) sets ``sqlalchemy.url`` directly — no
``.ini`` file is consumed. Online mode is what production uses; offline
mode is supported for completeness but unused by the gather pipeline.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool


def _run_migrations_online() -> None:
    cfg = context.config.get_section(context.config.config_ini_section, {})
    connectable = engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


def _run_migrations_offline() -> None:
    url = context.config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=None, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    _run_migrations_offline()
else:
    _run_migrations_online()
