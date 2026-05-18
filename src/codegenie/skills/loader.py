"""``SkillsLoader`` — three-tier merge with ``O_NOFOLLOW`` + byte-offset body.

Kernel-side loader for ``SKILL.md`` files (Phase 2 S2-01). Routes every
YAML parse through :func:`codegenie.parsers.safe_yaml.load` (Phase 1 ADR-0006
chokepoint) and every hash through :func:`codegenie.hashing.content_hash_fd`
(Phase 0 ADR-0001 chokepoint, extended by addition in S2-01).

Three load-bearing invariants:

1. **Three-tier merge, first-tier-wins.** ``[user, repo, org]`` iteration
   order. A hostile ``~/.codegenie/skills-org/`` cannot override a
   user-trusted skill. Cross-tier or same-tier collisions emit exactly
   one ``skill_shadowed`` structlog event per shadow and the later
   occurrence is dropped.
2. **Progressive disclosure.** The markdown body is byte-offset-recorded,
   hash-streamed in 64 KiB chunks, and *never* materialized as a single
   ``bytes`` value — the tracemalloc budget on a 100 MB body is < 20 KB.
3. **Defense-in-depth.** Per-file ``os.open(path, O_RDONLY | O_NOFOLLOW |
   O_NOCTTY)`` refuses planted symlinks at the SkillsLoader boundary
   (the ``safe_yaml.load`` boundary applies independently to its
   tempfile). ``!!python/object`` and every other ``yaml.YAMLError``
   subclass — :class:`codegenie.errors.MalformedYAMLError` umbrella —
   land in the ``unsafe_yaml`` per-file-error bucket; no code executes.

Per-file failures are non-fatal: one bad ``SKILL.md`` skips, the rest
load (arch §"Failure behavior"). The only :class:`FatalLoadError` path
is catastrophic — no search path readable at all — and is not exercised
by the Phase 2 default factory.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md``
  §"Component design" #9, §"Failure behavior", §"Edge cases" rows 8/9/16.
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0007-no-plugin-loader-in-phase-2.md``
  — kernel-side scaffolding only.
- ``docs/production/adrs/0033-domain-modeling-discipline.md`` §1, §3-4 —
  newtype discipline, illegal-states-unrepresentable for the per-file
  error union.
"""

from __future__ import annotations

import errno
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Final, Literal, cast

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from codegenie.errors import DepthCapExceeded, MalformedYAMLError, SizeCapExceeded
from codegenie.hashing import content_hash_fd
from codegenie.parsers import safe_yaml
from codegenie.result import Err, Ok, Result
from codegenie.skills.model import TIERS, EvidenceQuery, Skill, Tier
from codegenie.types.identifiers import Language, SkillId, TaskClassId

__all__ = [
    "FatalLoadError",
    "FrontmatterUnterminated",
    "IoFailure",
    "LoadOutcome",
    "SchemaViolation",
    "SkillsLoadError",
    "SkillsLoader",
    "SymlinkRefused",
    "UnsafeYaml",
]


# 1 MiB total bytes scanned before locating the closing ``---`` terminator.
# Capping the *scan* (not the body) bounds adversarial-file memory.
_FRONTMATTER_SCAN_CAP: Final[int] = 1 << 20

# Cap on the bytes ``safe_yaml.load`` accepts for the frontmatter tempfile —
# matches the scan cap (frontmatter cannot exceed what we scanned).
_FRONTMATTER_YAML_CAP: Final[int] = 1 << 20

# Default tier search paths (factory: :meth:`SkillsLoader.default`).
_DEFAULT_USER_TIER: Final[Path] = Path("~/.codegenie/skills/").expanduser()
_DEFAULT_REPO_TIER: Final[Path] = Path(".codegenie/skills/")
_DEFAULT_ORG_TIER: Final[Path] = Path("~/.codegenie/skills-org/").expanduser()

# Structlog event names (kept inline per S1-10's rule-of-three threshold).
_EVENT_SHADOWED: Final[str] = "skill_shadowed"
_EVENT_LOAD_FAILED: Final[str] = "skill_load_failed"

_WILDCARD_TASK: Final[TaskClassId] = cast(TaskClassId, "*")
_WILDCARD_LANG: Final[Language] = cast(Language, "*")

_logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Per-file error discriminated union (ADR-0033 §3 illegal-states-unrepresentable).
#
# Marker subclass discipline (CodegenieError) is for *single-file raise-on-error*
# loaders (TCCMLoader, S1-04). SkillsLoader is a *multi-file partial-success*
# loader — per-file errors must round-trip as values inside :class:`LoadOutcome`,
# so a typed Pydantic discriminated union is the correct shape here.
# ---------------------------------------------------------------------------


class SymlinkRefused(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    reason: Literal["symlink_refused"] = "symlink_refused"
    path: Path


class UnsafeYaml(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    reason: Literal["unsafe_yaml"] = "unsafe_yaml"
    path: Path


class FrontmatterUnterminated(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    reason: Literal["frontmatter_unterminated"] = "frontmatter_unterminated"
    path: Path


class SchemaViolation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    reason: Literal["schema"] = "schema"
    path: Path
    # Pydantic ``ValidationError.errors()`` shape — list of detail dicts.
    details: list[dict[str, object]]


class IoFailure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    reason: Literal["io_failure"] = "io_failure"
    path: Path
    errno_name: str


SkillsLoadError = Annotated[
    SymlinkRefused | UnsafeYaml | FrontmatterUnterminated | SchemaViolation | IoFailure,
    Field(discriminator="reason"),
]


class LoadOutcome(BaseModel):
    """Result-of-``load_all`` payload: loaded skills + per-file errors."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    skills: list[Skill]
    per_file_errors: list[SkillsLoadError]


class FatalLoadError(BaseModel):
    """Catastrophic failure — only emitted when *no* search path is usable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: Literal["all_tiers_unreadable"] = "all_tiers_unreadable"
    attempted: list[Path]


# ---------------------------------------------------------------------------
# Pure helpers — functional-core split (no I/O, no monkeypatch needed to test).
# ---------------------------------------------------------------------------


def _split_frontmatter(data: bytes) -> tuple[bytes, int] | None:
    """Split ``data`` at the YAML frontmatter terminator.

    Returns ``(frontmatter_bytes, body_offset)`` on success — ``body_offset``
    is the file offset of the first body byte (immediately after the closing
    ``---\\n``). Returns ``None`` if no opening or closing terminator is
    found in the supplied bytes.

    Pure: no I/O, no logging. Caller decides whether to surface ``None`` as
    :class:`FrontmatterUnterminated`. The hot path is
    :func:`_scan_frontmatter` which avoids materializing the whole scan
    window — this helper exists for the small-bytes unit-test path.
    """
    # Opening fence MUST be on line 0; absent → no frontmatter, refuse.
    if not (data.startswith(b"---\n") or data.startswith(b"---\r\n")):
        return None
    first_newline = data.index(b"\n") + 1  # past the opening "---\n".
    # Closing fence is a line containing only ``---``; locate by line.
    pos = first_newline
    while pos < len(data):
        nl = data.find(b"\n", pos)
        if nl == -1:
            return None
        line = data[pos:nl]
        # Strip trailing \r for CRLF files; the terminator is ``---`` exactly.
        if line.rstrip(b"\r") == b"---":
            frontmatter = data[first_newline:pos]
            body_offset = nl + 1
            return frontmatter, body_offset
        pos = nl + 1
    return None


def _matches(skills: Sequence[Skill], evidence: EvidenceQuery) -> list[Skill]:
    """Pure matching function — testable without a filesystem fixture.

    Matching rule (per story §"Goal" Invariant 7):

    - Tasks-component matches iff the skill carries the wildcard or the
      query's ``task`` is non-``None`` and present in the skill's list.
    - Languages-component matches iff the skill carries the wildcard or
      the skill's list and the query's set intersect.
    - A skill is applicable iff *both* components match (AND).
    """
    out: list[Skill] = []
    for skill in skills:
        tasks_ok = _WILDCARD_TASK in skill.applies_to_tasks or (
            evidence.task is not None and evidence.task in skill.applies_to_tasks
        )
        langs_ok = _WILDCARD_LANG in skill.applies_to_languages or bool(
            set(skill.applies_to_languages) & evidence.languages
        )
        if tasks_ok and langs_ok:
            out.append(skill)
    return out


# ---------------------------------------------------------------------------
# Impure helpers — open, scan, parse, hash. One-call-site each.
# ---------------------------------------------------------------------------


def _open_skill_path(path: Path) -> Result[int, SymlinkRefused | IoFailure]:
    """``os.open`` with the exact flag set required by AC-18.

    On ``ELOOP`` returns :class:`SymlinkRefused`; on any other ``OSError``
    returns :class:`IoFailure` with the errno fingerprint (catches the
    TOCTOU window between ``rglob`` yielding the path and ``os.open``
    seeing it; arch §"Edge cases").
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NOCTTY)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            return Err(error=SymlinkRefused(path=path))
        return Err(
            error=IoFailure(
                path=path,
                errno_name=errno.errorcode.get(exc.errno or 0, "EUNKNOWN"),
            )
        )
    return Ok(value=fd)


def _scan_frontmatter(fd: int, *, scan_cap: int) -> tuple[bytes, int] | None:
    """Stream-scan ``fd`` for the YAML frontmatter delimiters.

    Reads 4 KiB chunks into a single bytearray buffer, early-exits as soon
    as the closing ``---`` line lands. Returns
    ``(frontmatter_bytes, body_offset)`` on success or ``None`` when the
    file lacks the opening fence, lacks the closing fence within
    ``scan_cap`` bytes, or is empty. The memory budget is ``scan_cap +
    chunk`` bytes — the test on a 100 MB body asserts peak < 256 KB.
    """
    os.lseek(fd, 0, os.SEEK_SET)
    buf = bytearray()
    # ``next_search`` advances past bytes we already scanned so a 1 MiB scan
    # still only walks the buffer once.
    next_search = 0
    first_newline: int | None = None
    while len(buf) < scan_cap:
        chunk = os.read(fd, min(4096, scan_cap - len(buf)))
        if not chunk:
            break
        buf.extend(chunk)
        # Opening fence MUST be on line 0; reject as soon as we have enough
        # bytes to decide.
        if first_newline is None:
            if len(buf) < 4:
                continue
            if not (buf[:4] == b"---\n" or buf[:5] == b"---\r\n"):
                return None
            first_newline = buf.index(b"\n") + 1
            next_search = first_newline
        # Search for the closing fence (a line containing only ``---``).
        while True:
            nl = buf.find(b"\n", next_search)
            if nl == -1:
                # Incomplete line; resume after more bytes arrive.
                break
            line = bytes(buf[next_search:nl]).rstrip(b"\r")
            if line == b"---":
                frontmatter = bytes(buf[first_newline:next_search])
                body_offset = nl + 1
                return frontmatter, body_offset
            next_search = nl + 1
    # Edge: file < 4 bytes (no opening fence determinable).
    if first_newline is None:
        return None
    return None


def _load_one_skill(path: Path) -> Result[Skill, SkillsLoadError]:
    """Load a single ``SKILL.md`` — open, scan, parse, hash, validate."""
    open_result = _open_skill_path(path)
    if open_result.is_err():
        # Mypy narrows on is_err() but type-checker is conservative; cast via
        # explicit dispatch.
        if isinstance(open_result, Err):
            return Err(error=open_result.error)
    assert isinstance(open_result, Ok)
    fd = open_result.value
    try:
        try:
            split = _scan_frontmatter(fd, scan_cap=_FRONTMATTER_SCAN_CAP)
            if split is None:
                return Err(error=FrontmatterUnterminated(path=path))
            frontmatter_bytes, body_offset = split
            # ``body_size`` derives from the *total* file size, not the scan window.
            total_size = os.fstat(fd).st_size
            body_size = total_size - body_offset
            # Stream-hash the body via the chokepoint (no full-body materialization).
            body_blake3 = content_hash_fd(fd, offset=body_offset, size=body_size)
        except OSError as exc:
            return Err(
                error=IoFailure(
                    path=path,
                    errno_name=errno.errorcode.get(exc.errno or 0, "EUNKNOWN"),
                )
            )
    finally:
        os.close(fd)

    # Parse frontmatter through the safe_yaml chokepoint. ``safe_yaml.load``
    # takes a Path, so we trampoline through a tempfile; ``delete=False`` +
    # ``finally: unlink`` so cleanup runs on every exit path (AC-26).
    tmp_fd, tmp_name = tempfile.mkstemp(suffix=".yaml")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(tmp_fd, "wb") as tf:
            tf.write(frontmatter_bytes)
        try:
            data = safe_yaml.load(tmp_path, max_bytes=_FRONTMATTER_YAML_CAP)
        except (MalformedYAMLError, SizeCapExceeded, DepthCapExceeded):
            # S7-04 (adversarial corpus) — oversized and deeply-nested
            # frontmatter is hostile YAML; collapse into UnsafeYaml so the
            # loader's closed reason set continues to cover the surface.
            return Err(error=UnsafeYaml(path=path))
    finally:
        tmp_path.unlink(missing_ok=True)

    # safe_yaml.load returns a Mapping[str, JSONValue]; the Pydantic surface
    # accepts ``model_validate`` over a plain dict, which routes through the
    # field-typed coercion (raw ``str`` → ``SkillId``/``TaskClassId``/...
    # newtypes are identity-to-str at runtime).
    raw: dict[str, object] = dict(data)
    raw["body_offset"] = body_offset
    raw["body_size"] = body_size
    raw["body_blake3"] = body_blake3
    try:
        skill = Skill.model_validate(raw)
    except ValidationError as exc:
        details: list[dict[str, object]] = [dict(e) for e in exc.errors()]
        return Err(error=SchemaViolation(path=path, details=details))
    return Ok(value=skill)


# ---------------------------------------------------------------------------
# SkillsLoader — pure-data ``__init__``; first I/O on ``load_all()``.
# ---------------------------------------------------------------------------


class SkillsLoader:
    """Three-tier ``SKILL.md`` loader (kernel-side, no plugin loader).

    The constructor is pure data — no ``os.listdir``, no ``Path.exists``.
    ``load_all()`` is the only entry point that touches the filesystem.
    """

    def __init__(self, search_paths: list[Path]) -> None:
        # Coerce arbitrary path-likes to ``Path`` but do not touch the
        # filesystem (Rule 3 / arch §"Anti-patterns avoided" — no side
        # effects in constructors).
        self._search_paths: list[Path] = [Path(p) for p in search_paths]
        self._skills: list[Skill] = []

    @classmethod
    def default(cls) -> SkillsLoader:
        """Construct with the pinned three-tier ordering ``[user, repo, org]``."""
        return cls(
            search_paths=[
                _DEFAULT_USER_TIER,
                _DEFAULT_REPO_TIER,
                _DEFAULT_ORG_TIER,
            ]
        )

    def load_all(self) -> Result[LoadOutcome, FatalLoadError]:
        """Walk every search path, load each ``SKILL.md``, merge first-tier-wins."""
        # Map SkillId → (tier, path, skill) so collisions surface deterministically.
        winners: dict[SkillId, tuple[Tier, Path, Skill]] = {}
        errors: list[SkillsLoadError] = []
        # Positional tier assignment: position 0 → user, 1 → repo, 2 → org.
        # Callers may pass fewer than three paths (e.g., tests with a single
        # tier under inspection); we truncate to the shorter list rather than
        # requiring callers to pad with sentinels.
        for tier, search_path in zip(TIERS, self._search_paths):  # noqa: B905 — intentional truncation
            if not search_path.exists():
                continue  # missing optional tier silently skipped (AC-3a)
            try:
                # Bind ``search_path`` into a typed local so mypy can infer the
                # lambda's parameter type.
                tier_root: Path = search_path

                def _rel_key(p: Path, root: Path = tier_root) -> str:
                    return p.relative_to(root).as_posix()

                skill_mds = sorted(search_path.rglob("SKILL.md"), key=_rel_key)
            except OSError as exc:
                errors.append(
                    IoFailure(
                        path=search_path,
                        errno_name=errno.errorcode.get(exc.errno or 0, "EUNKNOWN"),
                    )
                )
                continue
            for skill_md in skill_mds:
                outcome = _load_one_skill(skill_md)
                if isinstance(outcome, Ok):
                    skill = outcome.value
                    if skill.id in winners:
                        prior_tier, prior_path, _ = winners[skill.id]
                        _logger.warning(
                            _EVENT_SHADOWED,
                            skill_id=str(skill.id),
                            winning_tier=prior_tier,
                            shadowed_tier=tier,
                            winning_path=str(prior_path),
                            shadowed_path=str(skill_md),
                        )
                        continue  # first-tier-wins; lexicographic-first within tier
                    winners[skill.id] = (tier, skill_md, skill)
                else:
                    assert isinstance(outcome, Err)
                    err = outcome.error
                    errors.append(err)
                    _logger.warning(_EVENT_LOAD_FAILED, **err.model_dump(mode="json"))

        # Insertion order on the dict preserves the iteration sequence;
        # ``list(winners.values())`` gives [user-tier first, then repo, then org].
        self._skills = [s for (_, _, s) in winners.values()]
        return Ok(
            value=LoadOutcome(
                skills=list(self._skills),
                per_file_errors=errors,
            )
        )

    def find_applicable(self, evidence: EvidenceQuery) -> list[Skill]:
        """Return the cached skills matching ``evidence`` — fresh list each call.

        Before ``load_all()`` has been called, ``self._skills`` is empty and
        the result is ``[]``. Calling this does **not** implicitly trigger
        I/O (explicit > implicit, per CLAUDE.md Rule 3).
        """
        return _matches(self._skills, evidence)
