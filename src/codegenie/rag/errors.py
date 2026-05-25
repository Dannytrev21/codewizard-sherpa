"""Phase-4 S4-01 typed errors for the RAG-substrate embedder.

Two error classes carry the failure modes the runtime ``__init__`` raises
when the on-disk ``embeddings_model.lock`` is missing, corrupt, or out of
sync with the on-disk weights cache:

- :class:`EmbeddingsBootstrapRequired` — operator must (re-)run
  ``codegenie embeddings bootstrap``.
- :class:`EmbeddingModelMismatch` — model identity or weight digest
  diverged from what the lock pins. ``kind`` discriminator distinguishes
  the two raise-sites (ADR-0007 §Decision + edge case #3).

Both inherit :class:`Exception` (markers-only — no behaviour beyond
attribute carriage; the CLAUDE.md convention) and stringify via an
explicit ``__str__`` so the diagnostic message is part of the contract
rather than ``args[0]``-folklore.
"""

from __future__ import annotations

from typing import Final, Literal

_RUNBOOK_URL: Final[str] = "docs/operations/embeddings.md"
_BOOTSTRAP_CMD: Final[str] = "codegenie embeddings bootstrap"


class EmbeddingsBootstrapRequired(Exception):
    """Raised at runtime when the embeddings substrate has not been
    bootstrapped (lock missing, lock corrupt, or lock present but
    on-disk weights absent). Same remedy for all three: re-run
    ``codegenie embeddings bootstrap``.

    Attributes
    ----------
    runbook_url:
        Pointer to the operator runbook (``docs/operations/embeddings.md``).
    reason:
        Short human-readable phrase naming which sub-branch raised
        (``"lock file missing"`` / ``"lock file corrupt"`` /
        ``"on-disk weights absent"``). Exposed so callers can branch on
        the cause without parsing ``__str__``.
    """

    __slots__ = ("reason", "runbook_url")

    runbook_url: str
    reason: str

    def __init__(self, *, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.runbook_url = _RUNBOOK_URL

    def __str__(self) -> str:
        return (
            f"embeddings substrate not bootstrapped — {self.reason}; "
            f"run `{_BOOTSTRAP_CMD}` (runbook: {self.runbook_url})"
        )


class EmbeddingModelMismatch(Exception):
    """Raised at runtime when the on-disk embeddings state diverges from
    what the lock pins. ADR-0007 §Decision + arch edge case #3 — halts
    the worker rather than silently embedding into a different vector
    space.

    The ``kind`` discriminator is load-bearing: the same exception type
    is raised at two semantically distinct sites (lock ``model_name`` vs
    ctor ``model_name``; on-disk weights digest vs ``lock.sha256``).
    Without ``kind`` an operator or test cannot tell which.

    Attributes
    ----------
    kind:
        ``"model_name"`` or ``"sha256"`` — which invariant was violated.
    expected:
        The lock-pinned value the runtime expected to see. (For
        ``kind="model_name"`` this is the ctor's ``model_name``; for
        ``kind="sha256"`` this is ``lock.sha256``.)
    found:
        The value that was actually observed on disk.
    runbook_url:
        Pointer to the operator runbook.
    """

    __slots__ = ("expected", "found", "kind", "runbook_url")

    kind: Literal["model_name", "sha256"]
    expected: str
    found: str
    runbook_url: str

    def __init__(
        self,
        *,
        kind: Literal["model_name", "sha256"],
        expected: str,
        found: str,
    ) -> None:
        super().__init__(kind, expected, found)
        self.kind = kind
        self.expected = expected
        self.found = found
        self.runbook_url = _RUNBOOK_URL

    def __str__(self) -> str:
        return (
            f"embeddings model drift — kind={self.kind} "
            f"expected={self.expected!r} found={self.found!r}; "
            f"runbook: {self.runbook_url}"
        )


__all__ = ("EmbeddingModelMismatch", "EmbeddingsBootstrapRequired")
