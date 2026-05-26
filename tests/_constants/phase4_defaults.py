"""S7-04 AC-11 — single source of truth for Phase-4 plugin-config defaults.

Every test that pins the arch-default Phase-4 calibration values imports
the constants from this module. Duplicating these literals across N tests
is what F10 (validation finding) prohibits — a missed update in one of
N sites would silently mask a default change.

The arch source for these values is
``docs/phases/04-vuln-llm-fallback-rag/phase-arch-design.md §Configuration``;
the live values live in
``plugins/vulnerability-remediation--node--npm/phase4-config.yaml``.
The integration smoke (AC-7) asserts the YAML file matches these
constants byte-for-byte (after Decimal normalization).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

# Thresholds — ADR-04-0008 two-threshold calibration band.
PHASE4_HIGH_FLOOR: Final[float] = 0.85
PHASE4_DEGRADED_FLOOR: Final[float] = 0.65

# Budget caps — ADR-04-0010 BudgetToken capability values.
PHASE4_MAX_TOKENS: Final[int] = 250_000
PHASE4_MAX_DOLLARS: Final[Decimal] = Decimal("1.50")
PHASE4_PER_CALL_MAX_TOKENS: Final[int] = 32_000

# Embeddings — ADR-04-0007 fastembed model pin.
PHASE4_EMBEDDINGS_MODEL: Final[str] = "BAAI/bge-small-en-v1.5"

# Cassettes — ADR-04-0014 cassette directory.
PHASE4_CASSETTES_DIR: Final[str] = "tests/cassettes/anthropic"
