"""``codegenie.cache`` — content-addressed cache (ADR-0001, ADR-0003, ADR-0011).

Two modules:

- :mod:`codegenie.cache.keys` — pure key derivation. Defines the two-version
  distinction (envelope vs per-probe sub-schema) that closes Gap 1 of
  ``phase-arch-design.md §Gap analysis``: a per-probe sub-schema bump
  invalidates *only* that probe's cache entries, never the envelope's
  metadata bump and never a sibling probe's. ADR-0003 §Decision pins this.
- :mod:`codegenie.cache.store` — the durable ``CacheStore``. JSONL index +
  sharded blob files, atomic writes (``<dest>.tmp → fsync → os.replace``),
  ``0700`` directory / ``0600`` file modes re-applied via ``os.chmod`` after
  every write (ADR-0011). Miss-on-error semantics: corrupt blob, hash
  mismatch, missing blob, and TTL-stale all collapse to ``get(...) == None``
  plus a structured log event (``cache.blob.invalid`` / ``cache.stale`` /
  ``cache.miss``); the coordinator's response is to re-run the probe.
"""

from codegenie.cache.keys import (
    declared_inputs_for,
    envelope_schema_version,
    key_for,
    per_probe_schema_version,
)
from codegenie.cache.store import CacheStore

__all__ = [
    "CacheStore",
    "declared_inputs_for",
    "envelope_schema_version",
    "key_for",
    "per_probe_schema_version",
]
