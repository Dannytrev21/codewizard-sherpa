"""Initial ``vulnerabilities`` + ``meta`` schema for the VulnIndex sqlite store.

Story: ``docs/phases/03-vuln-deterministic-recipe/stories/S3-02-vuln-index-sqlite.md``
ADRs: phase-3 ADR-0008 (digest-as-cache-key), ADR-0010 (sum-type + newtype),
production ADR-0033 (newtype identifiers).

Revision ID: 0001_initial_schema
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vulnerabilities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cve_id", sa.Text(), nullable=False),
        sa.Column("ecosystem", sa.Text(), nullable=False),
        sa.Column("package", sa.Text(), nullable=False),
        sa.Column("introduced", sa.Text(), nullable=False),
        sa.Column("fixed", sa.Text(), nullable=True),
        sa.Column("last_affected", sa.Text(), nullable=True),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("published_at", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("raw_payload", sa.LargeBinary(), nullable=False),
        # AC-D3 — unique constraint covers the full AffectedRange shape.
        # NULLs in (fixed, last_affected) participate per sqlite semantics;
        # combined with INSERT OR IGNORE at the call site (AC-D4) this gives
        # us idempotent ingest for identical records.
        sa.UniqueConstraint(
            "cve_id",
            "ecosystem",
            "package",
            "introduced",
            "fixed",
            "last_affected",
            name="uq_vuln_full_range",
        ),
    )
    # AC-D2 — composite index column order is (ecosystem, package).
    op.create_index(
        "idx_vuln_pkg_eco",
        "vulnerabilities",
        ["ecosystem", "package"],
        unique=False,
    )
    op.create_table(
        "meta",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    # Phase 3 only exercises ``upgrade head``; rollback is mechanical via
    # ``alembic downgrade`` but not contractually supported in this story.
    op.drop_table("meta")
    op.drop_index("idx_vuln_pkg_eco", table_name="vulnerabilities")
    op.drop_table("vulnerabilities")
