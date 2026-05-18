"""S6-08 — Open/Closed proof at the registration boundary.

Three load-bearing assertions:

- **AC-12.** ``@register_index_freshness_check`` for the three Phase-2
  rule-pack / catalog-versioned indices (``semgrep``, ``gitleaks``,
  ``conventions``) runs at **module-import time**, not lazily. The
  import side-effect chain (``codegenie.probes.__init__`` →
  ``layer_g.semgrep`` / ``layer_g.gitleaks`` / ``conventions.loader``)
  is what makes the registrations observable.

- **AC-13.** ``src/codegenie/probes/layer_b/index_health.py`` (B2) is
  byte-stable across S6-08. The Open/Closed promise of S1-02's
  ``FreshnessRegistry``: adding three new indices requires **zero**
  edits to B2. Pinned via a BLAKE3 hash constant; the legacy
  ``git diff --name-only`` form is deliberately rejected (it is fragile
  under cherry-picks, squash-merges, and rebases).

  Refresh ``_INDEX_HEALTH_BLAKE3`` ONLY when an ADR explicitly
  authorizes a B2 edit. If this test fires unexpectedly, the
  registration mechanism is being bypassed.

- **(side benefit)** The dispatch through ``IndexHealthProbe`` is
  exercised at runtime in
  ``tests/integration/probes/test_rule_pack_drift_marks_stale.py``;
  that file is the AC-14b end-to-end proof.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import blake3

# Importing these modules triggers the @register_index_freshness_check
# side-effect — exactly what AC-12 pins as the deliverable contract.
import codegenie.conventions.loader  # noqa: F401
import codegenie.probes.layer_g.gitleaks  # noqa: F401
import codegenie.probes.layer_g.semgrep  # noqa: F401
from codegenie.indices.registry import default_freshness_registry

# BLAKE3 of src/codegenie/probes/layer_b/index_health.py as shipped at
# the start of S6-08. Refresh ONLY when an ADR explicitly authorizes a
# B2 edit.
_INDEX_HEALTH_BLAKE3: Final[str] = (
    "b5c3fc5f3280f32c83f333ade1434e1939cb52e29b9ae62608a56dc9d6d31d67"
)


def test_semgrep_registered_at_import_time() -> None:
    """AC-12. Mutation caught: any 'register on first dispatch' pattern."""
    assert "semgrep" in default_freshness_registry.registered_names()


def test_gitleaks_registered_at_import_time() -> None:
    """AC-12."""
    assert "gitleaks" in default_freshness_registry.registered_names()


def test_conventions_registered_at_import_time() -> None:
    """AC-12."""
    assert "conventions" in default_freshness_registry.registered_names()


def test_index_health_probe_file_is_unchanged() -> None:
    """AC-13. B2 file is byte-stable — the Open/Closed promise of S1-02.

    Refresh ``_INDEX_HEALTH_BLAKE3`` ONLY when an ADR explicitly
    authorizes a B2 edit; otherwise this test firing means the
    registration mechanism is being bypassed.
    """
    p = Path("src/codegenie/probes/layer_b/index_health.py")
    actual = blake3.blake3(p.read_bytes()).hexdigest()
    assert actual == _INDEX_HEALTH_BLAKE3, (
        f"B2 file changed: {actual}. Refresh _INDEX_HEALTH_BLAKE3 only "
        f"when an ADR authorizes editing index_health.py."
    )
