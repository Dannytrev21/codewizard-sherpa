"""Phase 6 S2-01 — typed exception surface for the checkpoint substrate.

Mirrors the Phase-3 ``transforms/outcomes`` discipline: typed exceptions
carry an ``error_id`` matching the project-wide
``^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$`` grammar (Phase-1 ADR-0007) so the
CLI summary + run-record audit anchor can dispatch on a stable slug
rather than the exception class name.

Markers-only: the exception class does **not** override ``__init__``;
detail rides in the formatted message string passed via the single
positional ``args[0]``.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "CheckpointPayloadTooLargeError",
]


class CheckpointPayloadTooLargeError(ValueError):
    """A ``TransitionEvent`` exceeded the per-event canonical-JSON byte cap.

    Raised by :meth:`~codegenie.workflows.checkpoints.CheckpointStore.append`
    when ``event.model_dump_json(sort_keys=True).encode()`` exceeds
    :data:`~codegenie.workflows.checkpoints._MAX_EVENT_BYTES`.

    The orchestrator is expected to write large evidence to the blob-ref
    store (Phase-9 S3-05) and carry a :class:`BlobDigest` reference in
    the transition, rather than inlining the cleartext.
    """

    error_id: Final[str] = "workflows.checkpoint_payload_too_large"
