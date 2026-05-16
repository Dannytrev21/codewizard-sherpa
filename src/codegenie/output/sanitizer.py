"""Two-pass output sanitizer chokepoint + Phase 2 `redact_secrets` (S3-01).

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

Phase 2 — ``redact_secrets`` (S3-01, see ``phase-arch-design.md §"Component
design" #4 SecretRedactor`` + 02-ADR-0005 + 02-ADR-0010)
-------------------------------------------------------------------------

``redact_secrets`` is the Phase 2 plaintext-redaction chokepoint. It walks
a probe slice (``dict[str, JSONValue]``), replaces matched cleartext
secrets with ``<REDACTED:fingerprint=<8hex>>`` inline, and returns a
``RedactedSlice`` + a sibling in-memory ``list[SecretFinding]``. The
findings list is the audit trail the CLI summary consumes; it is **never**
persisted to disk (02-ADR-0005 — "no plaintext persistence"; the smart
constructor in 02-ADR-0010 closes the type-system bypass surface).

Pattern table:

- ``aws_access_key`` — ``AKIA[0-9A-Z]{16}``
- ``github_token`` — ``ghp_[A-Za-z0-9]{36}``
- ``jwt`` — ``eyJ[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+``
- ``rsa_private_key`` — ``-----BEGIN[ A-Z]*PRIVATE KEY-----[\\s\\S]+?``
  ``-----END[ A-Z]*PRIVATE KEY-----``
- ``npm_token`` — ``npm_[A-Za-z0-9]{36}``
- ``anthropic_key`` — ``sk-ant-[A-Za-z0-9_-]{50,}``

After every named pattern fires, an **entropy fallback** redacts any
remaining string of byte length ``>= 32`` whose Shannon entropy is at
least ``4.5`` bits/char. The threshold + length floor are tuned against
the ``gitleaks`` pattern pack
(``phase-arch-design.md §"Component design" #4``); changes to either
must travel via an ADR amendment and update both the
``_ENTROPY_THRESHOLD_BITS_PER_CHAR`` and ``_ENTROPY_MIN_LEN`` module-level
constants. The mutation-test discipline (see
``tests/unit/output/test_secret_redactor.py``) makes pattern coverage a
build invariant: each weakened regex must fail to redact its canonical
example, so a regression that loosens a pattern is caught at CI time.

The ``_PATTERNS`` table and ``_ENTROPY_THRESHOLD_BITS_PER_CHAR`` constant
are **module-level names by design**. The mutation tests
``monkeypatch.setattr`` against these symbols; moving them function-local
would silently disable the harness.

``pattern_class`` is a closed ``Literal[...]`` set; adding a seventh
class (e.g. ``"slack_webhook"``) is an **ADR amendment**, not Open/Closed
extension, mirroring the discipline ratified in S1-01 (``IndexFreshness``)
and S1-03 (``AdapterConfidence``).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import structlog
from pydantic import BaseModel, ConfigDict

from codegenie.coordinator.validator import (
    SECRET_FIELD_ALLOWLIST,
    SECRET_FIELD_PATTERN,
)
from codegenie.errors import SecretLikelyFieldNameError
from codegenie.hashing import content_hash_bytes
from codegenie.output.redacted_slice import RedactedSlice
from codegenie.parsers import JSONValue
from codegenie.probes.base import ProbeOutput
from codegenie.types.identifiers import ProbeId

__all__ = [
    "OutputSanitizer",
    "SECRET_FIELD_ALLOWLIST",
    "SECRET_FIELD_PATTERN",
    "SanitizedProbeOutput",
    "SecretFinding",
    "redact_secrets",
]

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
                if (
                    isinstance(k, str)
                    and k not in SECRET_FIELD_ALLOWLIST
                    and SECRET_FIELD_PATTERN.search(k)
                ):
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


# ---------------------------------------------------------------------------
# Phase 2 — ``redact_secrets`` (S3-01)
# ---------------------------------------------------------------------------


PatternClass = Literal[
    "aws_access_key",
    "github_token",
    "jwt",
    "rsa_private_key",
    "npm_token",
    "anthropic_key",
    "entropy",
]


class SecretFinding(BaseModel):
    """In-memory audit-trail record produced once per redaction.

    ``cleartext`` is **never** stored on the finding — the plaintext lives
    only inside the regex-substitution closure for the lifetime of one
    ``re.sub`` callback invocation, then is discarded once the BLAKE3
    fingerprint is computed (02-ADR-0005 §Decision).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    probe_name: ProbeId
    fingerprint: str
    pattern_class: PatternClass
    cleartext_len: int


# NOTE: ``_PATTERNS`` and ``_ENTROPY_THRESHOLD_BITS_PER_CHAR`` are module-level
# constants by deliberate design. The mutation-test suite
# (``tests/unit/output/test_secret_redactor.py::test_ac18_*``) calls
# ``monkeypatch.setattr(sanitizer, "_PATTERNS", ...)`` and
# ``monkeypatch.setattr(sanitizer, "_ENTROPY_THRESHOLD_BITS_PER_CHAR", 5.0)``
# to verify that a weakened regex (or a raised entropy floor) causes the
# canonical example to slip through; that mechanism only works against
# module-level bindings.
_PATTERNS: list[tuple[PatternClass, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github_token", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    (
        "jwt",
        re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    ),
    (
        "rsa_private_key",
        re.compile(
            r"-----BEGIN[ A-Z]*PRIVATE KEY-----[\s\S]+?"
            r"-----END[ A-Z]*PRIVATE KEY-----"
        ),
    ),
    ("npm_token", re.compile(r"npm_[A-Za-z0-9]{36}")),
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_-]{50,}")),
]

_ENTROPY_THRESHOLD_BITS_PER_CHAR: float = 4.5
_ENTROPY_MIN_LEN: int = 32


def _shannon_entropy(s: str) -> float:
    """Return the Shannon entropy of ``s`` in bits-per-character.

    Returns ``0.0`` for the empty string and for single-character
    inputs (and any string whose unique-char count is 1) — the formula
    ``-sum(p * log2(p))`` over a one-element frequency table is zero. The
    function is total over ``str``: it does not raise for any input,
    including non-ASCII / multi-byte codepoints (the iteration is per
    Unicode codepoint, not per byte).
    """
    if not s:
        return 0.0
    counts = Counter(s)
    length = len(s)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def _fingerprint(cleartext: str) -> str:
    """Return the 8-hex BLAKE3 fingerprint of ``cleartext`` bytes.

    ``content_hash_bytes`` returns the prefix-tagged ``"blake3:<64hex>"``
    per Phase-0 ADR-0001; stripping the ``"blake3:"`` prefix then slicing
    yields the 8 lowercase hex chars that survive in persisted artifacts.
    Privacy-preserving by construction: BLAKE3 first-8-hex is not
    reversible to the cleartext.
    """
    return content_hash_bytes(cleartext.encode("utf-8")).removeprefix("blake3:")[:8]


def _redact_string(s: str, probe_name: ProbeId, findings_out: list[SecretFinding]) -> str:
    """Apply each named pattern and the entropy fallback to ``s``.

    The entropy fallback fires only on strings that NO named pattern
    matched. Otherwise a long string containing a named secret (e.g.,
    ``"Authorization: token ghp_<36>"``) would emit two findings — the
    GitHub-token finding plus an entropy finding over the post-regex
    string — silently double-counting one cleartext credential.
    """
    out = s
    matched_any_named = False
    for pattern_class, pattern in _PATTERNS:
        new_out, n = pattern.subn(_make_repl(probe_name, pattern_class, findings_out), out)
        if n:
            matched_any_named = True
        out = new_out

    if matched_any_named:
        return out

    if len(s.encode("utf-8")) >= _ENTROPY_MIN_LEN and (
        _shannon_entropy(s) >= _ENTROPY_THRESHOLD_BITS_PER_CHAR
    ):
        fp = _fingerprint(s)
        findings_out.append(
            SecretFinding(
                probe_name=probe_name,
                fingerprint=fp,
                pattern_class="entropy",
                cleartext_len=len(s.encode("utf-8")),
            )
        )
        return f"<REDACTED:fingerprint={fp}>"
    return out


def _make_repl(
    probe_name: ProbeId,
    pattern_class: PatternClass,
    findings_out: list[SecretFinding],
) -> Any:
    """Build a ``re.sub`` replacement callback for one pattern class."""

    def _repl(m: re.Match[str]) -> str:
        cleartext = m.group(0)
        fp = _fingerprint(cleartext)
        findings_out.append(
            SecretFinding(
                probe_name=probe_name,
                fingerprint=fp,
                pattern_class=pattern_class,
                cleartext_len=len(cleartext.encode("utf-8")),
            )
        )
        return f"<REDACTED:fingerprint={fp}>"

    return _repl


def _walk(node: JSONValue, probe_name: ProbeId, findings_out: list[SecretFinding]) -> JSONValue:
    """Recursively redact every string ``leaf`` reached through values.

    Dict keys are not walked (Phase 0's field-name regex already covers
    that surface — see ``OutputSanitizer.scrub`` pass-1).
    """
    if isinstance(node, str):
        return _redact_string(node, probe_name, findings_out)
    if isinstance(node, dict):
        return {k: _walk(v, probe_name, findings_out) for k, v in node.items()}
    if isinstance(node, list):
        return [_walk(item, probe_name, findings_out) for item in node]
    return node


def redact_secrets(
    slice_: dict[str, JSONValue], probe_name: ProbeId
) -> tuple[RedactedSlice, list[SecretFinding]]:
    """Walk ``slice_`` and replace every matched secret with an in-place token.

    Returns ``(RedactedSlice, list[SecretFinding])``:

    - The :class:`RedactedSlice` is the only thing the writer accepts
      (02-ADR-0010 — type-system defense). It carries the redacted dict,
      the total findings count (each match is one finding, including
      entropy hits), and the deduplicated, stably-ordered list of
      fingerprints.
    - The ``list[SecretFinding]`` is the **in-memory** audit trail
      consumed by the CLI summary. It is **never** persisted (02-ADR-0005).

    The function is stateless across calls: no global accumulators, no
    ``ContextVar``, no module-level findings list. The input ``slice_``
    is not mutated; the returned dict is freshly constructed.
    """
    findings: list[SecretFinding] = []
    redacted = _walk(slice_, probe_name, findings)
    if not isinstance(redacted, dict):
        # Defensive: ``_walk`` returns a dict when its input is a dict.
        raise TypeError(f"redact_secrets expected dict input, got {type(slice_)!r}")
    fingerprints = list(dict.fromkeys(f.fingerprint for f in findings))
    return (
        RedactedSlice(
            slice=redacted,
            findings_count=len(findings),
            fingerprints=fingerprints,
        ),
        findings,
    )
