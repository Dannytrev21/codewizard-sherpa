"""Phase 6 S2-02 — pure-core replay fold helper (ADR-0003 §Decision second half).

This module is the *pure functional core* of the replay verifier. It
folds :func:`~codegenie.workflows._chain._compute_chain_head` over a
sequence of :class:`~codegenie.workflows.vuln_ledger.TransitionEvent`
records and returns the resulting :class:`ChainHead`. No I/O, no clock,
no env, no filesystem, no SQLite — the AST no-side-effects fence at
``tests/fence/test_chain_head_purity.py`` walks this module and refuses
the same impure-name set that protects ``_chain.py``.

Why the fold lives here and not inline in
:mod:`codegenie.workflows.replay`: the imperative-shell verifier
(``replay.py``) needs to depend on a pure helper so the verifier itself
becomes substrate-agnostic; if the fold were inline, an executor could
sneak ``time.time()`` or ``sqlite3`` into the fold path without the
fence firing (the fence walks *modules*, not statements).

Sanitization-aware fold discipline (story AC-3 — load-bearing): the
fold operates on already-parsed :class:`TransitionEvent` instances. The
caller (the verifier) round-trips persisted bytes through
:meth:`TransitionEvent.model_validate_json` BEFORE calling this fold;
because :func:`~codegenie.output.sanitizer.sanitize_for_persistence`
operates on canonical-JSON bytes and replaces only secret-shaped
substrings with idempotent ``<REDACTED:fingerprint=...>`` sentinels
(themselves valid JSON strings), the reconstructed event produces
byte-equal ``model_dump_json()`` output. The fold is therefore
byte-equivalent to the write-path BLAKE3 input by construction — a
sanitization that triggered on write is a benign no-op on verify, NOT
a chain mismatch.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from codegenie.workflows._chain import _compute_chain_head
from codegenie.workflows.checkpoints import _GENESIS_CHAIN_HEAD

if TYPE_CHECKING:  # pragma: no cover — type-checker-only
    from codegenie.types.identifiers import ChainHead
    from codegenie.workflows.vuln_ledger import TransitionEvent

__all__ = ["_replay_fold"]


def _replay_fold(
    events: Iterable[TransitionEvent],
    *,
    genesis: ChainHead = _GENESIS_CHAIN_HEAD,
) -> ChainHead:
    """Fold :func:`_compute_chain_head` over ``events`` starting at ``genesis``.

    Returns the final :class:`ChainHead`. An empty iterable returns
    ``genesis`` unchanged — the empty-workflow contract.
    """
    head: ChainHead = genesis
    for event in events:
        head = _compute_chain_head(head, event)
    return head
