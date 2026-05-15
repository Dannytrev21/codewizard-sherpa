"""Pure language-applicability predicate for task-specific probes.

Lifted out so the three Node-only Phase 1 probes
(``NodeBuildSystemProbe``, ``NodeManifestProbe``, ``TestInventoryProbe``)
share one source of truth for "does this probe apply given the enriched
snapshot's detected languages?" — and so a Phase-2 probe with the same
shape gets the predicate by import, not by copy-paste.

Contract (ADR-0010 — Layer A slices optional at the envelope's
``probes`` map):

* ``"*"`` in ``applies_to_languages`` always admits.
* Otherwise, admission requires non-empty overlap between
  ``applies_to_languages`` and the snapshot's ``detected_languages``.
* An empty ``detected_languages`` (the pre-prelude case the coordinator
  uses for ``tier == "base"`` probes) MUST yield ``False`` for any
  language-filtered probe — those probes belong in
  ``tier == "task_specific"`` so the prelude pass enriches the snapshot
  before this predicate fires.

Keeping the predicate pure makes it trivially unit-testable and keeps
the coordinator free of probe-specific knowledge (Open/Closed at the
file boundary — adding a Phase-2 probe with a new language filter
requires no edits here).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

__all__ = ["_admits_languages", "_admits_node_project"]


def _admits_languages(
    applies_to_languages: Iterable[str],
    detected_languages: Mapping[str, int],
) -> bool:
    """Return True iff the probe's language filter admits ``detected_languages``."""
    declared = set(applies_to_languages)
    if "*" in declared:
        return True
    return bool(declared & set(detected_languages))


def _admits_node_project(
    applies_to_languages: Iterable[str],
    detected_languages: Mapping[str, int],
    repo_root: Path,
) -> bool:
    """Node-probe admission with a ``package.json``-at-root fallback.

    Used by ``NodeBuildSystemProbe`` / ``NodeManifestProbe`` /
    ``TestInventoryProbe``: admit when ``detected_languages`` overlaps the
    probe's ``applies_to_languages`` OR when a ``package.json`` lives at
    the repo root. The fallback preserves the architectural intent — a
    greenfield Node repo that lays out ``package.json`` + lockfile before
    any source file is added is still a Node project — without leaking
    Node-specific knowledge into the coordinator's generic dispatch.
    """
    if _admits_languages(applies_to_languages, detected_languages):
        return True
    return (repo_root / "package.json").is_file()
