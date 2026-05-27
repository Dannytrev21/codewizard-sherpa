"""Phase-4 S7-05 — Phase-4-local typed fixture portfolio manifest.

**Rule-7 surface (upstream gap).** Phase-3 S8-01's
``tests/fixtures/repos/_portfolio.py`` typed manifest **does not exist
on master** as of 2026-05-27. The S7-05 story's design pivot puts the
Phase-4 fixture metadata into that Phase-3 manifest as five additive
``FixtureSpec`` rows. With the Phase-3 manifest missing, S7-05's
canonical landing site is unavailable.

This module is the **Phase-4-local shadow manifest** — a minimal typed
``FixtureSpec`` model + the five Phase-4 fixture rows, kept in
``tests/fixtures/`` (NOT ``tests/fixtures/repos/``) so a future
Phase-3 S8-01 GREEN commit can absorb these rows additively without
this module being in the canonical scan path. When the merge lands,
this file's rows move into ``_portfolio.py`` and this module is
deleted — that's the documented sunset path.

The dataclass shape is **identical** to the one Phase-3 S8-01
HARDENED specifies (per
``docs/phases/02-context-gather-layers-b-g/stories/S8-01-...``
validation report). Adopting the same shape preserves the additive-
merge invariant — no field-name reconciliation will be needed.

Five fixture rows, each named per S7-05's prose:

* ``express-cve-2026-1234`` — peer-dep transitive + major-bump CVE;
  the headline exit-criterion fixture (S7-06).
* ``lodash-cve-2026-9876`` — major-bump callsite rewrite; smaller for
  faster unit coverage.
* ``glibc-on-node`` — CVE not in app layer; ProvenanceGate refuse
  anchor (S7-03).
* ``express-rerun`` — pre-populated ``.codegenie/rag/records/`` for
  RAG-shapes-LLM second-run test (S7-07).
* ``cassette-attempt-1-fails-attempt-2-passes`` — Phase-5 retry-
  simulator fixture (S6-02).

Each row carries a ``cve_ids`` tuple constructed via
``parse_cve_id`` (S1-04 newtype) so a malformed id surfaces as
``Err`` at module-import time rather than ``KeyError`` mid-test.

Note: the fixture **directories** under ``tests/fixtures/repos/``
are NOT shipped by this commit — the rows here describe their
**intended** shape so downstream tests can iterate on the manifest
even when the directory contents are still being authored. AC-3 / AC-8
through AC-13 of S7-05 require the actual directory contents and
land in a separate commit (~80 .ts files for express-cve-2026-1234,
seeded RAG records for express-rerun, cassette stubs for
cassette-attempt-..., Dockerfile for glibc-on-node).
"""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from codegenie.types.identifiers import CveId

FixtureCategory = Literal[
    "vuln-major-bump",
    "vuln-provenance",
    "vuln-rag-hit",
    "vuln-retry",
]


class Phase4FixtureSpec(BaseModel):
    """Typed metadata for one Phase-4 fixture repo.

    Shape mirrors the Phase-3 S8-01 HARDENED ``FixtureSpec`` so a
    future merge into ``tests/fixtures/repos/_portfolio.py`` is
    field-rename-free.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    """Filesystem slug under ``tests/fixtures/repos/<name>/``."""

    category: FixtureCategory
    """One of the four Phase-4 ``vuln-*`` categories the arch tags."""

    cve_ids: tuple[CveId, ...]
    """CVE identifiers this fixture covers. ``CveId`` newtype enforces shape."""

    description: str
    """One-line operator-readable description; consumed by failing-test
    diagnostics so a missing fixture surfaces meaningfully."""

    consumer_stories: tuple[str, ...]
    """Phase-4 story ids that read this fixture (S5-04, S6-02, S7-03,
    S7-06, S7-07, …). A future story that adds itself as a consumer
    extends this tuple additively."""


# --- The five Phase-4 fixtures (S7-05 §Goal) ------------------------------


PHASE4_PORTFOLIO: Final[tuple[Phase4FixtureSpec, ...]] = (
    Phase4FixtureSpec(
        name="express-cve-2026-1234",
        category="vuln-major-bump",
        cve_ids=(CveId("CVE-2026-1234"),),
        description=(
            "Peer-dep transitive case + major-version-bump CVE; "
            "~80 .ts files, ~120 Jest unit tests. The headline "
            "roadmap exit-criterion fixture (S7-06)."
        ),
        consumer_stories=("S5-04", "S7-06", "S7-07"),
    ),
    Phase4FixtureSpec(
        name="lodash-cve-2026-9876",
        category="vuln-major-bump",
        cve_ids=(CveId("CVE-2026-9876"),),
        description=(
            "Major-bump callsite rewrite; smaller (~20 files) for "
            "faster unit coverage. Exercises the callsite_rewrite "
            "PlanProposal variant."
        ),
        consumer_stories=("S5-04",),
    ),
    Phase4FixtureSpec(
        name="glibc-on-node",
        category="vuln-provenance",
        cve_ids=(CveId("CVE-2023-4911"),),  # real glibc Looney Tunables
        description=(
            "CVE NOT in app layer — ProvenanceGate refuse anchor. "
            "Dockerfile FROM node:20-bullseye; the CVE is a glibc "
            "vulnerability transitively present via the base image. "
            "Classification assertion lives in S7-03."
        ),
        consumer_stories=("S7-03",),
    ),
    Phase4FixtureSpec(
        name="express-rerun",
        category="vuln-rag-hit",
        cve_ids=(CveId("CVE-2026-1234"),),
        description=(
            "Pre-populated .codegenie/rag/records/<id>.yaml so the "
            "S7-07 'replay-lands-RAG' second-run E2E hits the RAG "
            "path rather than the leaf LLM. The seeded record's "
            "embedding_model must match codegenie.rag.embeddings."
            "MODEL_DIGEST (edge case #19)."
        ),
        consumer_stories=("S7-07",),
    ),
    Phase4FixtureSpec(
        name="cassette-attempt-1-fails-attempt-2-passes",
        category="vuln-retry",
        cve_ids=(CveId("CVE-2026-1234"),),
        description=(
            "Phase-5 retry-simulator fixture. Two cassette stubs: "
            "attempt-1 produces a smart-constructor-failing proposal "
            "(outcome='fail'); attempt-2's prompt body carries the "
            "prior_failure_summary (no RAG few-shot) and produces a "
            "valid proposal (outcome='pass'). Anchor for S6-02's "
            "retry-bypass test."
        ),
        consumer_stories=("S6-02",),
    ),
)


# --- Lookup helpers --------------------------------------------------------


def by_name(name: str) -> Phase4FixtureSpec:
    """Return the fixture row whose ``name`` field equals ``name``.

    Raises :class:`KeyError` with a helpful diagnostic if absent.
    """
    for spec in PHASE4_PORTFOLIO:
        if spec.name == name:
            return spec
    available = sorted(s.name for s in PHASE4_PORTFOLIO)
    raise KeyError(f"no Phase-4 fixture named {name!r}; available: {available}")


def by_category(category: FixtureCategory) -> tuple[Phase4FixtureSpec, ...]:
    """Return all fixtures matching ``category`` (arch §1014 glob shape)."""
    return tuple(s for s in PHASE4_PORTFOLIO if s.category == category)


def by_consumer_story(story_id: str) -> tuple[Phase4FixtureSpec, ...]:
    """Return all fixtures whose ``consumer_stories`` tuple contains ``story_id``."""
    return tuple(s for s in PHASE4_PORTFOLIO if story_id in s.consumer_stories)


__all__ = [
    "PHASE4_PORTFOLIO",
    "FixtureCategory",
    "Phase4FixtureSpec",
    "by_category",
    "by_consumer_story",
    "by_name",
]
