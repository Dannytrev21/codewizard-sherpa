"""Phase-4 S2-04 — ``PromptBuilder`` and the ``TrustedPrompt`` /
``FencedPromptBody`` newtypes.

ADR-0013 §Decision pins ``PromptBuilder`` as the **sole minting site** for
:data:`TrustedPrompt` and :data:`FencedPromptBody`. The newtypes live here
beside their only smart constructor; an AST-walking test
(``tests/unit/fallback/test_prompt_builder_sole_mint_site.py``) scans every
``.py`` under ``src/codegenie/`` and asserts only this module constructs
them. S1-01 deliberately did not ship these in the global identifier
catalog — exporting the constructors there would weaken the "constructor
lives beside the sole smart constructor" discipline.

The builder is a **composition shell** over :class:`FenceWrapper` (S2-02)
and :class:`CanaryGuard` (S2-03). It must never:

- assemble the per-nonce open/close delimiters that
  :func:`fence_pure` owns;
- construct :class:`FencedSegment`, :class:`CanaryClean`, or
  :class:`CanaryCollision`;
- import :func:`scan_pure` / :func:`fence_pure` / ``_TRUNCATION_CAPS`` /
  :class:`CanaryGuard`.

``tests/unit/fallback/test_prompt_builder_no_fence_bypass.py`` is the
structural guard (AC-13). Per-segment truncation lives in
:func:`fence_pure`; per-segment-*count* multiplicity caps live here.

Deterministic assembly order (load-bearing for S6-07's 50-run byte-identical
property test):

1. ``cve_description``
2. ``repo_readme``
3. each ``transitive_dep_meta`` item in input order (first 16 only — over-cap
   truncates with one :class:`SegmentCountTruncated` event and continues)
4. each ``source_snippets`` item in input order
5. each ``rag_few_shots`` item in input order — emitted with
   ``source_kind="rag_retrieved"``; over-cap (>3) raises ``ValueError``
   **before** any fence call and emits no :class:`PromptAssembled`
6. ``prior_attempt_summary`` (skipped if ``None``)
7. ``sandbox_stderr`` (skipped if ``None``)

Capability does **not** flow through ``PromptBuilder``: per ADR-0010 the
``BudgetToken`` traverses exactly two frames (``FallbackTier`` → ``LeafLlm.
invoke``). AC-9's signature check is the structural guard against drift.
"""

from __future__ import annotations

import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import NewType

from codegenie.fallback.fence.wrapper import FenceWrapper, SourceKind
from codegenie.plugins.events import EventLog, PromptAssembled, SegmentCountTruncated
from codegenie.types.identifiers import EventId

__all__ = [
    "FencedPromptBody",
    "PromptBuilder",
    "TrustedPrompt",
]

# --- Newtypes (sole-mint site) ---------------------------------------------

TrustedPrompt = NewType("TrustedPrompt", str)
"""Caller-controlled system prompt: ``skill + "\\n\\n" + instruction_template``.

Both inputs are repo-controlled in Phase 4 (skill markdown + instruction
template). No fencing applied — this is *trusted* by construction.
"""

FencedPromptBody = NewType("FencedPromptBody", str)
"""Untrusted-input body: deterministic concatenation of
:class:`FencedSegment.content` produced by :meth:`FenceWrapper.fence` for
every untrusted source kind. Every byte the LLM sees from outside the
trusted skill / instruction template has passed through ``FenceWrapper``.
"""


# --- Multiplicity caps + private helpers -----------------------------------

_TRANSITIVE_DEP_META_CAP: int = 16
_RAG_FEW_SHOTS_CAP: int = 3


def _new_event_id() -> EventId:
    """Mint a deterministic-shape event id for one ``PromptBuilder`` emission.

    Mirrors :func:`codegenie.fallback.fence.wrapper._new_event_id` — the
    exact id is not pinned by tests; the ``01HPRB`` prefix is operator-
    friendly grep bait for prompt-builder events.
    """
    return EventId("01HPRB" + secrets.token_hex(10).upper())


def _ordered_untrusted_segments(
    *,
    cve_description: str,
    repo_readme: str,
    transitive_dep_meta: Sequence[str],
    source_snippets: Sequence[str],
    rag_few_shots: Sequence[str],
    prior_attempt_summary: str | None,
    sandbox_stderr: str | None,
) -> list[tuple[SourceKind, str]]:
    """Project the keyword inputs onto the deterministic ``(SourceKind, payload)`` order.

    Pure — no I/O, no event emission. The caller has already enforced the
    multiplicity caps (over-3 RAG raised; over-16 deps truncated and
    audited) before calling here.
    """
    segments: list[tuple[SourceKind, str]] = []
    segments.append(("cve_description", cve_description))
    segments.append(("repo_readme", repo_readme))
    for dep in transitive_dep_meta:
        segments.append(("transitive_dep_meta", dep))
    for snippet in source_snippets:
        segments.append(("source_snippet", snippet))
    for hit in rag_few_shots:
        segments.append(("rag_retrieved", hit))
    if prior_attempt_summary is not None:
        segments.append(("prior_attempt_summary", prior_attempt_summary))
    if sandbox_stderr is not None:
        segments.append(("sandbox_stderr", sandbox_stderr))
    return segments


# --- PromptBuilder (the composition shell) ---------------------------------


@dataclass(frozen=True, slots=True)
class PromptBuilder:
    """Mint :data:`TrustedPrompt` + :data:`FencedPromptBody` from typed inputs.

    Two collaborators — a :class:`FenceWrapper` and an :class:`EventLog`.
    Capability (``BudgetToken``) does **not** flow through here; AC-9's
    signature check is the structural guard.
    """

    fence: FenceWrapper
    event_log: EventLog

    def build(
        self,
        *,
        skill: str,
        instruction_template: str,
        cve_description: str,
        repo_readme: str,
        transitive_dep_meta: Sequence[str],
        source_snippets: Sequence[str],
        prior_attempt_summary: str | None = None,
        rag_few_shots: Sequence[str] = (),
        sandbox_stderr: str | None = None,
    ) -> tuple[TrustedPrompt, FencedPromptBody]:
        """Compose the ``(system_prompt, fenced_body)`` pair the LLM consumes.

        Order of operations (load-bearing for replay determinism):

        1. Enforce multiplicity caps. Over-3 RAG raises **before** any fence
           call and emits no :class:`PromptAssembled`. Over-16 deps truncates
           to the first 16 and emits one :class:`SegmentCountTruncated`.
        2. Derive the trusted system prompt (no fencing).
        3. Iterate the deterministic ``(SourceKind, payload)`` ordering and
           call :meth:`FenceWrapper.fence` once per untrusted segment.
        4. Concatenate :attr:`FencedSegment.content` strings into the body.
        5. Mint the two newtypes and emit one :class:`PromptAssembled`.
        """
        # AC-4 — over-3 RAG raises BEFORE any fence call.
        rag_count = len(rag_few_shots)
        if rag_count > _RAG_FEW_SHOTS_CAP:
            raise ValueError(f"rag_few_shots capped at {_RAG_FEW_SHOTS_CAP}, got {rag_count}")

        # AC-4 — over-16 deps truncates + emits one SegmentCountTruncated.
        dep_count = len(transitive_dep_meta)
        if dep_count > _TRANSITIVE_DEP_META_CAP:
            kept_deps: Sequence[str] = list(transitive_dep_meta[:_TRANSITIVE_DEP_META_CAP])
            self.event_log.emit_internal(
                SegmentCountTruncated(
                    event_id=_new_event_id(),
                    workflow_id=self.event_log.workflow_id,
                    timestamp=datetime.now(UTC),
                    source_kind="transitive_dep_meta",
                    requested=dep_count,
                    kept=_TRANSITIVE_DEP_META_CAP,
                )
            )
        else:
            kept_deps = transitive_dep_meta

        # AC-6 — trusted system prompt: caller-controlled, no fencing.
        system_prompt = TrustedPrompt(skill + "\n\n" + instruction_template)

        # AC-5 / AC-7 — fence every untrusted segment in deterministic order.
        ordered = _ordered_untrusted_segments(
            cve_description=cve_description,
            repo_readme=repo_readme,
            transitive_dep_meta=kept_deps,
            source_snippets=source_snippets,
            rag_few_shots=rag_few_shots,
            prior_attempt_summary=prior_attempt_summary,
            sandbox_stderr=sandbox_stderr,
        )
        fenced_segments = [
            self.fence.fence(payload, source_kind=source_kind) for source_kind, payload in ordered
        ]
        body_str = "".join(segment.content for segment in fenced_segments)
        fenced_body = FencedPromptBody(body_str)

        # AC-10 — one PromptAssembled per successful build; payload is shape-only.
        self.event_log.emit_internal(
            PromptAssembled(
                event_id=_new_event_id(),
                workflow_id=self.event_log.workflow_id,
                timestamp=datetime.now(UTC),
                segment_count=len(fenced_segments),
                source_kinds_used=tuple(source_kind for source_kind, _ in ordered),
                system_prompt_byte_length=len(system_prompt.encode("utf-8")),
                fenced_body_byte_length=len(fenced_body.encode("utf-8")),
            )
        )
        return system_prompt, fenced_body
