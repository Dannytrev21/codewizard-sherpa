"""Two-pass output sanitizer chokepoint (ADR-0008, ADR-0010).

ADR-0008 designates :meth:`OutputSanitizer.scrub` as the **single path** from
a :class:`~codegenie.probes.base.ProbeOutput` to a persisted byte:

1. **Pass 1 — secret-name rejection (defense in depth).** Every dict key
   anywhere inside ``schema_slice`` (at any nesting depth, through lists) is
   matched against the canonical
   :data:`codegenie.coordinator.validator.SECRET_FIELD_PATTERN`. A match
   raises :class:`~codegenie.errors.SecretLikelyFieldNameError`. The pattern
   is imported **by identity** — there is exactly one ``re.compile`` for the
   secret regex in ``src/codegenie/`` (ADR-0010 §Decision; ADR-0008
   §Tradeoffs).
2. **Pass 2 — absolute-path scrubbing.** Every string in ``schema_slice``,
   ``errors``, and ``warnings`` is rewritten by a non-anchored regex that
   recognizes absolute paths under ``<repo_root>``, ``/Users/<u>/``,
   ``/home/<u>/``, and ``/root/``. Paths under ``<repo_root>`` become
   repo-relative; paths under a user-home prefix have the user segment
   stripped; ``/root/...`` loses the ``/root/`` prefix. The alternation
   places ``<repo_root>`` first so the **longest-prefix-wins** rule falls
   out of Python's left-to-right alternation matching.

The function returns a :class:`SanitizedProbeOutput` — a frozen dataclass
with the exact field set of ``ProbeOutput``, producible only by this
function. The typed signal "scrubbing ran" lives at *this* step; the
downstream writer (ADR-0008 §Consequences) takes a merged ``dict`` envelope
because the coordinator collapses many ``SanitizedProbeOutput.schema_slice``
values into a single dict before YAML serialization.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from codegenie.coordinator.validator import SECRET_FIELD_PATTERN
from codegenie.errors import SecretLikelyFieldNameError
from codegenie.probes.base import ProbeOutput

__all__ = ["OutputSanitizer", "SECRET_FIELD_PATTERN", "SanitizedProbeOutput"]

_log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SanitizedProbeOutput:
    """Frozen post-scrub probe output.

    Mirrors :class:`~codegenie.probes.base.ProbeOutput` field-for-field. The
    type itself is the typed signal that :meth:`OutputSanitizer.scrub` ran:
    no other producer exists in the package.
    """

    schema_slice: dict[str, Any]
    raw_artifacts: list[Path]
    confidence: str
    duration_ms: int
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _validate_repo_root(repo_root: Path) -> Path:
    if not repo_root.is_absolute():
        raise ValueError(f"repo_root must be absolute, got {repo_root!r}")
    resolved = repo_root.resolve()
    if resolved != repo_root:
        raise ValueError(
            f"repo_root must be already resolved; got {repo_root!r}, resolves to {resolved!r}"
        )
    if repo_root == Path("/"):
        raise ValueError("repo_root must not be filesystem root '/'")
    return repo_root


def _build_path_regex(repo_root: Path) -> re.Pattern[str]:
    """Compile the per-call path-scrub regex.

    Alternation order places ``<repo_root>`` first so Python's left-to-right
    alternation picks the longest-overlapping prefix when ``<repo_root>``
    happens to sit inside ``/Users/<u>/`` (AC-10). Each alternative captures
    its own group so the replacement callback can pick the right rewrite
    rule per match shape.
    """
    repo = re.escape(str(repo_root))
    pattern = (
        rf"(?P<repo>{repo}/?)"
        r"|(?P<users>/Users/[^/]+/)"
        r"|(?P<home>/home/[^/]+/)"
        r"|(?P<root>/root/)"
    )
    return re.compile(pattern)


def _walk_pass1_keys(node: Any, on_match: Any) -> None:
    """Walk ``node`` and call ``on_match(key)`` on any secret-shaped dict key."""
    stack: list[Any] = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if isinstance(k, str) and SECRET_FIELD_PATTERN.search(k):
                    on_match(k)
                stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)


def _scrub_string(value: str, regex: re.Pattern[str]) -> tuple[str, int]:
    """Scrub one string. Returns ``(replaced, n_rewrites)``."""
    n = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal n
        n += 1
        # repo prefix wins by alternation order — drop the whole repo prefix.
        if m.lastgroup in ("repo", "users", "home", "root"):
            return ""
        return m.group(0)

    new = regex.sub(repl, value)
    return new, n


def _scrub_container(node: Any, regex: re.Pattern[str], counter: list[int]) -> Any:
    """Recursively rewrite every string inside ``node``; counter[0] tracks rewrites."""
    if isinstance(node, str):
        new, n = _scrub_string(node, regex)
        if n:
            counter[0] += n
            _log.debug("sanitizer.path.rewritten")
        return new
    if isinstance(node, dict):
        return {k: _scrub_container(v, regex, counter) for k, v in node.items()}
    if isinstance(node, list):
        return [_scrub_container(v, regex, counter) for v in node]
    return node


class OutputSanitizer:
    """Two-pass sanitizer chokepoint (ADR-0008)."""

    def scrub(self, output: ProbeOutput, repo_root: Path) -> SanitizedProbeOutput:
        """Run pass-1 (secret rejection) then pass-2 (path scrub).

        ``repo_root`` must be absolute, already ``.resolve()``-d, and not
        the filesystem root — the CLI normalizes this once for the whole
        run; here it is the second wall.
        """
        repo_root = _validate_repo_root(repo_root)

        def _raise(key: str) -> None:
            _log.warning("sanitizer.secret.rejected", key=key)
            raise SecretLikelyFieldNameError(key)

        _walk_pass1_keys(output.schema_slice, _raise)

        regex = _build_path_regex(repo_root)
        counter = [0]
        scrubbed_slice = _scrub_container(output.schema_slice, regex, counter)
        scrubbed_errors = [_scrub_container(s, regex, counter) for s in output.errors]
        scrubbed_warnings = [_scrub_container(s, regex, counter) for s in output.warnings]

        return SanitizedProbeOutput(
            schema_slice=scrubbed_slice,
            raw_artifacts=list(output.raw_artifacts),
            confidence=output.confidence,
            duration_ms=output.duration_ms,
            warnings=scrubbed_warnings,
            errors=scrubbed_errors,
        )
