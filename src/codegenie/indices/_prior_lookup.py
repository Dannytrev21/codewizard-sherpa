"""Prior-run slice lookup for rule-pack / catalog freshness checks (S6-08).

Scanners that emit a freshness signal (``semgrep`` / ``gitleaks`` /
``conventions``) need to know the *prior gather's* version string so the
new gather can embed ``expected_<version_key>`` alongside the current
``<version_key>`` in its slice. The freshness check (registered via
``@register_index_freshness_check``) then compares the two sibling keys
and emits ``Stale(DigestMismatch(...))`` on drift, ``Fresh`` otherwise.

This helper centralizes the I/O so three scanners share one implementation
(the *I/O* part — the *comparator* stays per-scanner since each scanner
owns its version key). When a fourth call site lands (``runtime_trace``
from S5-05 already participates via a different freshness shape; the
foreseeable next consumer of *this* helper is a future Phase-3 scanner
with a rule-pack signal), the helper stays unchanged.

The lookup reads ``<raw_dir>/<name>.json`` (the canonical persisted slice
location), tolerates the two on-disk wrappings sibling scanners use today
(unwrapped — Layer B ``scip.json`` precedent; wrapped — Layer G
``semgrep.json`` precedent), and returns ``None`` on every absence path
(file missing, JSON malformed, key missing, value not a string). Returning
``None`` is the bootstrap signal: the scanner writes
``expected_<key>=None`` into its new slice, and the freshness check
returns ``Fresh()`` because there is no prior to compare against (AC-20).
"""

from __future__ import annotations

import json
from pathlib import Path

__all__ = ["load_prior_value"]


def load_prior_value(raw_dir: Path, name: str, key: str) -> str | None:
    """Return the value of ``key`` from the prior ``raw/<name>.json``, or None.

    ``name`` is the index/probe name; ``key`` is the version-string field
    (``"rule_pack_version"`` for semgrep/gitleaks, ``"catalog_version"`` for
    conventions). The two on-disk wrappings are both accepted:

    - Unwrapped (Layer B convention — ``scip.json``): top-level dict carries
      the keys directly. We look up ``key`` at the top level.
    - Wrapped (Layer G convention — ``semgrep.json``): top-level dict
      carries a single ``name`` key whose value is the slice. We unwrap
      and look up ``key`` inside.

    All non-string values (including missing keys, ``None``, integers,
    nested objects) return ``None`` — the freshness check interprets
    that as "no prior baseline" and emits ``Fresh()``.
    """
    path = raw_dir / f"{name}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    direct = payload.get(key)
    if isinstance(direct, str):
        return direct
    wrapped = payload.get(name)
    if isinstance(wrapped, dict):
        inner = wrapped.get(key)
        if isinstance(inner, str):
            return inner
    return None
