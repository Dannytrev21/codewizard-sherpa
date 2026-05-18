"""Small structural checks for architecture-document lifecycle drift."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

VALID_ADR_STATUSES = {
    "Proposed",
    "Accepted",
    "Provisional Accepted",
    "Deferred",
    "Superseded",
}

CANONICAL_STALE_CLAIMS = {
    "docs/production/design.md": (
        "Phase 1 target: migrate Node.js services to Chainguard distroless containers.",
    ),
    "docs/index.md": (
        "Phases 3–7 — Designed; implementation pending plugin-architecture redesign",
    ),
    "docs/roadmap.md": (
        "hits RAG, not LLM",
        "bench_score.mean ≥ tier_threshold[bronze]",
    ),
}

_STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*(.+?)\s*$", re.MULTILINE)
_REVIEW_TRIGGER_RE = re.compile(r"^\*\*Review trigger:\*\*\s*(.+?)\s*$", re.MULTILINE)
_SUPERSEDES_RE = re.compile(r"^\*\*Supersedes:\*\*\s*ADR-(\d{4})\s*$", re.MULTILINE)
_SUPERSEDED_BY_RE = re.compile(r"^\*\*Status:\*\*\s*Superseded by ADR-(\d{4})\s*$", re.MULTILINE)


@dataclass(frozen=True)
class AdrRecord:
    path: Path
    number: str
    status: str
    review_trigger: str | None
    supersedes: str | None
    superseded_by: str | None


def parse_adr(path: Path) -> AdrRecord:
    text = path.read_text()
    number = path.name.split("-", 1)[0]
    status_match = _STATUS_RE.search(text)
    if status_match is None:
        status = ""
    else:
        raw_status = status_match.group(1)
        status = "Superseded" if raw_status.startswith("Superseded by ADR-") else raw_status

    review_match = _REVIEW_TRIGGER_RE.search(text)
    supersedes_match = _SUPERSEDES_RE.search(text)
    superseded_by_match = _SUPERSEDED_BY_RE.search(text)
    return AdrRecord(
        path=path,
        number=number,
        status=status,
        review_trigger=review_match.group(1) if review_match else None,
        supersedes=supersedes_match.group(1) if supersedes_match else None,
        superseded_by=superseded_by_match.group(1) if superseded_by_match else None,
    )


def collect_docs_consistency_issues(root: Path) -> list[str]:
    issues: list[str] = []
    adr_dir = root / "docs" / "production" / "adrs"
    records = {
        record.number: record
        for record in (
            parse_adr(path) for path in sorted(adr_dir.glob("[0-9][0-9][0-9][0-9]-*.md"))
        )
    }

    for record in records.values():
        if record.status not in VALID_ADR_STATUSES:
            issues.append(f"{record.path}: invalid ADR status {record.status!r}")
        if record.status == "Provisional Accepted" and not record.review_trigger:
            issues.append(f"{record.path}: provisional ADR missing review trigger")
        if record.status == "Superseded":
            if record.superseded_by is None:
                issues.append(f"{record.path}: superseded ADR missing successor link")
            elif records.get(record.superseded_by, None) is None:
                issues.append(
                    f"{record.path}: superseded ADR points to missing ADR-{record.superseded_by}"
                )
            elif records[record.superseded_by].supersedes != record.number:
                issues.append(
                    f"{record.path}: successor ADR-{record.superseded_by} "
                    "lacks reciprocal supersedes link"
                )
        if record.supersedes is not None:
            prior = records.get(record.supersedes)
            if prior is None:
                issues.append(f"{record.path}: supersedes missing ADR-{record.supersedes}")
            elif prior.superseded_by != record.number:
                issues.append(
                    f"{record.path}: prior ADR-{record.supersedes} "
                    "lacks reciprocal superseded-by link"
                )

    for relpath, claims in CANONICAL_STALE_CLAIMS.items():
        text = (root / relpath).read_text()
        for claim in claims:
            if claim in text:
                issues.append(f"{relpath}: stale claim still present: {claim}")

    return issues
