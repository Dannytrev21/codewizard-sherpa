# Story S6-03 — `ADRs` + `RepoNotes` + `RepoConfig` + `Policy` + `Exceptions` Layer D marker probes

**Step:** Step 6 — Ship Layer D + E + G probes (skills, conventions, ADRs, ownership, scanners)
**Status:** Ready
**Effort:** M
**Depends on:** S6-02 (`ConventionsProbe` lands first to establish the Layer D probe shape; this story re-uses the file layout convention but not a shared base class)
**ADRs honored:** 02-ADR-0005 (no plaintext persistence — bodies are not loaded; marker probes record paths + headings only), Phase 1 ADR-0006 (`safe_yaml` for any frontmatter)
**Phase-2 commitment honored:** "Progressive disclosure for context" (CLAUDE.md) and "Organizational uniqueness as data, not prompts" — each probe records *what exists*, not the body content. The Planner reads bodies at decision time.

## Context

Five marker-driven probes ship together because they share three traits and *only* those three: (a) they walk a conventional location for a marker (a YAML file or a docs directory), (b) they emit an index — paths, IDs, headings, last-modified timestamps — but **never** the body content, and (c) each one is structurally trivial (≤ 100 LOC per probe, including the Pydantic slice). They differ in markers, file layout, and slice shape; the Rule-of-Three argument against extracting a shared `MarkerProbe` base class is the same one that argues against a shared `ScannerRunner` for Layer G (final-design Design-patterns row 7). Five probes × ~80 LOC each ≈ 400 LOC; a shared base would save ~150 LOC and introduce one coupling point that every Phase-3-or-later contributor would have to mentally model before adding a sixth marker probe. Not worth it.

The five:

1. **ADRProbe** (`adrs.py`) — walks `docs/adr/`, `docs/architecture/`, `docs/decisions/`; extracts ADR ID + title + status from each markdown file's first heading and (optional) status line.
2. **RepoNotesProbe** (`repo_notes.py`) — walks `.codegenie/notes/`; extracts headings from each markdown file. Tribal-knowledge mechanism.
3. **RepoConfigProbe** (`repo_config.py`) — reads `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`'s frontmatter via `safe_yaml.load` (frontmatter only; never the body).
4. **PolicyProbe** (`policy.py`) — reads `~/.codegenie/config.yaml`'s `policy_repos:` field; emits a list of declared policy-repo paths (does **not** parse the policy itself — that's a Phase-4+ Planner concern).
5. **ExceptionProbe** (`exceptions.py`) — reads `.codegenie/exceptions.yaml` and (optional) `~/.codegenie/exceptions.yaml`; emits a list of unexpired exceptions matching the current repo glob.

Each probe ≤ 100 LOC. Each has its own slice. Each has a happy-path test and a marker-absent test. None imports from another in this set.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md` §"Design patterns applied"](../phase-arch-design.md) row "One file per Layer G scanner; no shared `ScannerRunner`" — the same SRP + Rule-of-Three discipline applies to Layer D marker probes.
  - [`../phase-arch-design.md` §"Anti-patterns avoided"](../phase-arch-design.md) "Inheritance for code reuse" — every Phase 2 class inherits *only* `Probe` or `BaseModel`.
- **Phase ADRs:**
  - [`../ADRs/0005-secret-findings-no-plaintext-persistence.md`](../ADRs/0005-secret-findings-no-plaintext-persistence.md) — exception YAML may carry the approver's email/Slack handle; the redactor at the writer chokepoint handles it. The probes themselves don't pre-redact.
- **Source design:**
  - [`../High-level-impl.md` §"Step 6"](../High-level-impl.md) — marker-driven; each ≤ 100 LOC.
  - [`../../localv2.md` §5.4 D1, D3, D4, D6, D7](../../../localv2.md) — slice shapes for each probe.
- **Existing kernel:**
  - `src/codegenie/parsers/safe_yaml.py` (S1-03) — `load(path, *, max_bytes, max_depth=64)` for frontmatter / exceptions / policy-config reads.
  - `src/codegenie/probes/base.py` — `Probe` ABC.

## Goal

Ship five files under `src/codegenie/probes/layer_d/`: `adrs.py`, `repo_notes.py`, `repo_config.py`, `policy.py`, `exceptions.py`. Each is `@register_probe(heaviness="light")`, ≤ 100 LOC including the slice model, has a happy-path + marker-absent test, and emits a `confidence="low"` slice (not raise) when the marker is missing or malformed. No probe imports another probe in this set.

## Acceptance criteria

**Numbered for traceability to the TDD plan.**

- [ ] **AC-1.** Five new files exist, each with `__all__` declaring exactly the slice model + the probe class. None of the five imports any of the other four.
- [ ] **AC-2.** Each probe's source file is **≤ 100 LOC** including the slice Pydantic model, the `@register_probe` line, the docstring, and the imports. Verified by `wc -l` in `tests/unit/probes/layer_d/test_marker_probes_loc.py`.
- [ ] **AC-3.** Each slice Pydantic model has `model_config = ConfigDict(frozen=True, extra="forbid")`.
- [ ] **AC-4.** Each probe is `@register_probe(heaviness="light")`; `probe_id` matches the file name (`adrs`, `repo_notes`, `repo_config`, `policy`, `exceptions`); `applies_to_tasks = ("*",)`; `applies_to_languages = ("*",)`; `timeout_seconds=5`.
- [ ] **AC-5.** **ADRProbe.** Walks the three conventional locations (`docs/adr/`, `docs/architecture/`, `docs/decisions/`); emits `AdrsSlice(adrs: tuple[Adr, ...], scanned_locations: tuple[str, ...])` where `Adr = (id: str, title: str, status: Literal["proposed", "accepted", "deprecated", "superseded", "unknown"], path: str)`. Title is the first H1; status parsed from a `Status:` line in the first 50 lines (falls back to `"unknown"`).
- [ ] **AC-6.** **RepoNotesProbe.** Walks `.codegenie/notes/`; emits `RepoNotesSlice(notes_dir: str | None, files: tuple[NoteFile, ...])` where `NoteFile = (path: str, headings: tuple[str, ...], char_count: int, last_modified: str)`. Heading extraction is regex on `^#+ ` markdown lines; body is never loaded (only `char_count` and `headings` are captured during a single streaming pass).
- [ ] **AC-7.** **RepoConfigProbe.** Reads frontmatter from `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md` via `safe_yaml.load` (frontmatter only — the body is past the closing `---` separator and is never parsed). Slice: `RepoConfigSlice(files: tuple[RepoConfigFile, ...])` with `RepoConfigFile = (path: str, frontmatter_keys: tuple[str, ...], has_body: bool, body_byte_offset: int)`. Body content is not loaded.
- [ ] **AC-8.** **PolicyProbe.** Reads `~/.codegenie/config.yaml`'s `policy_repos:` field via `safe_yaml.load` (config root, NOT the policy bodies). Slice: `PolicySlice(policy_repos: tuple[PolicyRepoRef, ...])` with `PolicyRepoRef = (path: str, type: str, exists_on_disk: bool)`. Probe does **not** read inside the policy repo (that's Phase-4+ Planner work).
- [ ] **AC-9.** **ExceptionProbe.** Reads `.codegenie/exceptions.yaml` (repo-local) + `~/.codegenie/exceptions.yaml` (org); merges; filters to entries whose `repo_glob` matches the current repo name AND whose `expires:` date is `>= today` (UTC). Slice: `ExceptionsSlice(active: tuple[Exception, ...], expired: tuple[Exception, ...])` — both lists land so the operator can see which exceptions just-expired.
- [ ] **AC-10.** **Marker absent ⇒ low confidence, no raise.** Each probe handles its marker-absent path: `confidence="low"`, empty-or-`None` slice fields, `errors=[<typed_reason>]`. Mutation caught: any `raise FileNotFoundError` would break Phase 0 isolation.
- [ ] **AC-11.** **Body bytes never read.** For each probe, an architectural test asserts the source file does **not** call `path.read_text()` / `path.read_bytes()` / `open(path).read()` on a marker file's body region. Frontmatter reads go through `safe_yaml.load`; ADR titles use a bounded `head -n 50` style read (`itertools.islice(open(path), 50)`) NOT `read_text()`. RepoNotes headings use the same bounded line iterator.
- [ ] **AC-12.** **No cross-probe imports in this set.** Architectural test parametrized across the five files asserts `import` statements never name another probe in this set. Mutation caught: a future refactor extracting a shared `_walk_markers(...)` helper into `adrs.py` and importing it from `repo_notes.py` — that's the Rule-of-Three violation the SRP discipline forbids.
- [ ] **AC-13.** **`safe_yaml` for all YAML reads.** Every YAML read in the five files goes through `codegenie.parsers.safe_yaml.load`. No direct `yaml.safe_load` / `yaml.load`. Architectural test: `inspect.getsource` for each file contains `safe_yaml.load(` or no YAML at all; never `yaml.safe_load`.
- [ ] **AC-14.** **`mypy --strict`** passes on all five files.
- [ ] **AC-15.** **Determinism.** Each probe's two-consecutive-runs produce byte-identical slices. ADR list sorted by `id`; notes sorted by `path`; exceptions sorted by `(repo_glob, expires)`.

## Implementation outline

For each of the five files, mirror the S6-02 structure (Pydantic slice + probe class + `_run`). The probes' bodies look similar; **do not extract a shared base** (AC-12, AC-2 LOC ceiling, final-design Design-patterns row 7).

1. `adrs.py`:
   - Walk `[ctx.repo_root / "docs" / x for x in ("adr", "architecture", "decisions")]`.
   - For each `*.md`: read first 50 lines via `itertools.islice`; extract H1 as `title`; regex-match `^(ADR|adr)-(\d+)` from filename or first line for `id`; regex-match `^Status:\s*(\w+)` for `status`.
   - Emit sorted `tuple[Adr, ...]` by `id`.
2. `repo_notes.py`:
   - Walk `ctx.repo_root / ".codegenie" / "notes"` (recursive).
   - For each `*.md`: stream lines; collect `^#+ ` headings + line count; record `path`, `char_count = os.path.getsize(path)`, `last_modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()`.
3. `repo_config.py`:
   - For each of `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`: if exists, run `safe_yaml.load` over the frontmatter block (delimited by the first two `^---$` lines); record `frontmatter_keys = tuple(sorted(frontmatter.keys()))`, `has_body = body_offset < file_size`, `body_byte_offset = end-of-second-`---``.
4. `policy.py`:
   - `safe_yaml.load(ctx.user_home / ".codegenie" / "config.yaml")` if present; project `policy_repos:` to `tuple[PolicyRepoRef]`; for each, `exists_on_disk = Path(ref.path).expanduser().exists()`.
5. `exceptions.py`:
   - `safe_yaml.load` for both `.codegenie/exceptions.yaml` (repo) and `~/.codegenie/exceptions.yaml` (user) if present.
   - Filter to entries whose `repo_glob` matches `ctx.repo_name` via `fnmatch.fnmatch`.
   - Partition by `expires` (`date.today()`) into `active` vs `expired`.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Each probe gets its own test file. Below is the full `test_adrs.py` to anchor the shape; `test_repo_notes.py`, `test_repo_config.py`, `test_policy.py`, `test_exceptions.py` follow the same pattern.

```python
# tests/unit/probes/layer_d/test_adrs.py
"""Unit tests for ADRProbe (S6-03)."""
from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.probes.base import ProbeContext
from codegenie.probes.layer_d import adrs as adrs_probe


def test_adrs_happy_path_scans_three_conventional_locations(tmp_path: Path) -> None:
    """AC-5. Mutation caught: dropping `docs/architecture/` or
    `docs/decisions/` — assertion pins the three-location scan."""
    repo = tmp_path / "repo"
    (repo / "docs" / "adr").mkdir(parents=True)
    (repo / "docs" / "architecture").mkdir(parents=True)
    (repo / "docs" / "decisions").mkdir(parents=True)
    (repo / "docs" / "adr" / "0001-use-postgres.md").write_text(
        "# 0001. Use Postgres\n\nStatus: Accepted\n\n## Context\n...\n"
    )
    (repo / "docs" / "architecture" / "0002-microservices.md").write_text(
        "# 0002. Microservices boundaries\n\nStatus: Proposed\n"
    )
    (repo / "docs" / "decisions" / "0003-event-bus.md").write_text(
        "# 0003. Use Kafka\n\nStatus: Superseded\n"
    )
    ctx = ProbeContext.for_test(repo_root=repo)
    output = adrs_probe.ADRProbe()._run(ctx)
    slice_ = adrs_probe.AdrsSlice.model_validate(output.schema_slice)
    assert [a.id for a in slice_.adrs] == ["0001", "0002", "0003"]
    assert [a.status for a in slice_.adrs] == ["accepted", "proposed", "superseded"]
    assert set(slice_.scanned_locations) == {"docs/adr", "docs/architecture", "docs/decisions"}


def test_adrs_marker_absent_yields_low_confidence_no_raise(tmp_path: Path) -> None:
    """AC-10. Mutation caught: re-raising on a repo without an ADR dir."""
    repo = tmp_path / "repo"
    repo.mkdir()
    ctx = ProbeContext.for_test(repo_root=repo)
    output = adrs_probe.ADRProbe()._run(ctx)
    assert output.confidence == "low"
    slice_ = adrs_probe.AdrsSlice.model_validate(output.schema_slice)
    assert slice_.adrs == ()


def test_adrs_unknown_status_falls_back_to_unknown_literal(tmp_path: Path) -> None:
    """AC-5. Mutation caught: any future "raise on missing status" —
    the slice's Literal type would reject a stringly-typed status, and
    the probe needs the explicit `"unknown"` variant."""
    repo = tmp_path / "repo"
    adr_dir = repo / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "0001-foo.md").write_text("# 0001. Foo\n\n(no status line)\n")
    ctx = ProbeContext.for_test(repo_root=repo)
    output = adrs_probe.ADRProbe()._run(ctx)
    slice_ = adrs_probe.AdrsSlice.model_validate(output.schema_slice)
    assert slice_.adrs[0].status == "unknown"


def test_adrs_body_never_loaded(tmp_path: Path) -> None:
    """AC-11. Mutation caught: any `read_text()` of an ADR's body would
    explode memory on a 10 MB ADR (we don't expect such ADRs but the
    discipline holds). The bounded line iterator is the only allowed
    read."""
    import inspect
    src = inspect.getsource(adrs_probe)
    assert "read_text" not in src
    assert "read_bytes" not in src


def test_adrs_two_consecutive_runs_byte_identical(tmp_path: Path) -> None:
    """AC-15. Mutation caught: any iteration order that depends on
    `os.listdir` ordering (which differs across filesystems)."""
    repo = tmp_path / "repo"
    adr_dir = repo / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "0003-c.md").write_text("# 0003. C\nStatus: Accepted\n")
    (adr_dir / "0001-a.md").write_text("# 0001. A\nStatus: Accepted\n")
    (adr_dir / "0002-b.md").write_text("# 0002. B\nStatus: Accepted\n")
    ctx = ProbeContext.for_test(repo_root=repo)
    import json
    out1 = adrs_probe.ADRProbe()._run(ctx).schema_slice
    out2 = adrs_probe.ADRProbe()._run(ctx).schema_slice
    assert json.dumps(out1, sort_keys=True) == json.dumps(out2, sort_keys=True)
```

Equivalent tests for the other four probes live in `test_repo_notes.py`, `test_repo_config.py`, `test_policy.py`, `test_exceptions.py`. Plus the cross-cutting architectural tests:

```python
# tests/unit/probes/layer_d/test_marker_probes_loc.py
"""Architectural tests for the five marker probes (S6-03)."""
from __future__ import annotations

import importlib
import inspect

import pytest

MARKER_MODULES = [
    "codegenie.probes.layer_d.adrs",
    "codegenie.probes.layer_d.repo_notes",
    "codegenie.probes.layer_d.repo_config",
    "codegenie.probes.layer_d.policy",
    "codegenie.probes.layer_d.exceptions",
]


@pytest.mark.parametrize("module_path", MARKER_MODULES)
def test_each_marker_probe_under_100_loc(module_path: str) -> None:
    """AC-2. Mutation caught: a future refactor that bloats a probe past
    100 LOC is the signal that a shared kernel is overdue. The ceiling
    forces the conversation."""
    mod = importlib.import_module(module_path)
    src_path = inspect.getsourcefile(mod)
    assert src_path is not None
    line_count = sum(1 for _ in open(src_path))
    assert line_count <= 100, (
        f"{module_path} has {line_count} LOC; the 100-LOC ceiling forces a "
        "review of whether a shared kernel is now justified (Rule-of-Three)."
    )


@pytest.mark.parametrize("module_path", MARKER_MODULES)
def test_no_cross_probe_imports(module_path: str) -> None:
    """AC-12. Mutation caught: extracting a shared `_walk_markers` into
    one probe and importing it from another — that's the premature-coupling
    failure mode the final-design table forbids for Layer G scanners and
    by symmetry forbids here."""
    mod = importlib.import_module(module_path)
    src = inspect.getsource(mod)
    for sibling in MARKER_MODULES:
        if sibling == module_path:
            continue
        assert sibling not in src, (
            f"{module_path} imports from {sibling}; marker probes share no "
            "Phase-2 kernel beyond `Probe` and `safe_yaml`."
        )


@pytest.mark.parametrize("module_path", MARKER_MODULES)
def test_yaml_reads_route_through_safe_yaml(module_path: str) -> None:
    """AC-13. Mutation caught: any `yaml.safe_load` direct call would
    bypass the size/depth caps from Phase 1 ADR-0009."""
    mod = importlib.import_module(module_path)
    src = inspect.getsource(mod)
    assert "yaml.safe_load" not in src
    assert "yaml.load(" not in src
```

### Green — make it pass

Skeleton for `adrs.py` (≤ 100 LOC; the other four follow the same shape):

```python
# src/codegenie/probes/layer_d/adrs.py
"""ADRProbe — Layer D, light heaviness.

Walks docs/adr/, docs/architecture/, docs/decisions/. Records ID +
title + status only; body bytes are never read past the first 50 lines
(bounded line iterator). Sources: ../phase-arch-design.md §"Design
patterns applied" + ../../localv2.md §5.4 D3.
"""
from __future__ import annotations

import itertools
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from codegenie.ids import ProbeId
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, register_probe

__all__ = ["ADRProbe", "Adr", "AdrsSlice"]

_LOCATIONS = ("docs/adr", "docs/architecture", "docs/decisions")
_ID_RE = re.compile(r"^(?:ADR-|adr-)?(\d+)")
_STATUS_RE = re.compile(r"^[Ss]tatus:\s*(\w+)")
_STATUSES = {"proposed", "accepted", "deprecated", "superseded"}


class Adr(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    title: str
    status: Literal["proposed", "accepted", "deprecated", "superseded", "unknown"]
    path: str


class AdrsSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    adrs: tuple[Adr, ...]
    scanned_locations: tuple[str, ...]


@register_probe(heaviness="light")
class ADRProbe(Probe):
    probe_id = ProbeId("adrs")
    applies_to_tasks: tuple[str, ...] = ("*",)
    applies_to_languages: tuple[str, ...] = ("*",)
    timeout_seconds = 5

    def _run(self, ctx: ProbeContext) -> ProbeOutput:
        adrs: list[Adr] = []
        scanned: list[str] = []
        for loc in _LOCATIONS:
            d = ctx.repo_root / loc
            if not d.exists():
                continue
            scanned.append(loc)
            for md in sorted(d.glob("*.md")):
                adrs.append(self._parse(md))
        if not scanned:
            return ProbeOutput(
                probe_id=self.probe_id,
                confidence="low",
                schema_slice=AdrsSlice(adrs=(), scanned_locations=()).model_dump(mode="json"),
                errors=["adr_dirs_absent"],
            )
        adrs.sort(key=lambda a: a.id)
        return ProbeOutput(
            probe_id=self.probe_id,
            confidence="high",
            schema_slice=AdrsSlice(
                adrs=tuple(adrs), scanned_locations=tuple(scanned)
            ).model_dump(mode="json"),
            errors=[],
        )

    def _parse(self, md: Path) -> Adr:
        title = ""
        status = "unknown"
        adr_id = (_ID_RE.match(md.stem) or _ID_RE.match("")).group(1) if _ID_RE.match(md.stem) else md.stem
        with open(md) as fh:
            for line in itertools.islice(fh, 50):
                if not title and line.startswith("# "):
                    title = line[2:].strip()
                m = _STATUS_RE.match(line)
                if m and m.group(1).lower() in _STATUSES:
                    status = m.group(1).lower()
        return Adr(id=adr_id, title=title, status=status, path=str(md.relative_to(md.parents[2])))
```

The other four (`repo_notes.py`, `repo_config.py`, `policy.py`, `exceptions.py`) follow the same shape — each in its own file, each ≤ 100 LOC, each with its own slice model.

### Refactor

- **Do not extract a shared `_walk_markers(repo_root, locations) -> Iterable[Path]` helper.** The five probes walk five different layouts (recursive vs. flat, multi-location vs. single-file vs. user-home). The shape similarity is at the *story* level, not the *code* level. AC-12 enforces this with an architectural test.
- The `_STATUSES` set + `_ID_RE` regex stay local to `adrs.py`. Repo-notes headings use a different regex (`^#+ `); policy and exceptions use no regex; repo-config uses `safe_yaml.load`. No shared regex constants.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/layer_d/adrs.py` | New file ≤ 100 LOC. |
| `src/codegenie/probes/layer_d/repo_notes.py` | New file ≤ 100 LOC. |
| `src/codegenie/probes/layer_d/repo_config.py` | New file ≤ 100 LOC. |
| `src/codegenie/probes/layer_d/policy.py` | New file ≤ 100 LOC. |
| `src/codegenie/probes/layer_d/exceptions.py` | New file ≤ 100 LOC. |
| `tests/unit/probes/layer_d/test_adrs.py` | New file — 5 tests. |
| `tests/unit/probes/layer_d/test_repo_notes.py` | New file — 5 tests. |
| `tests/unit/probes/layer_d/test_repo_config.py` | New file — 5 tests. |
| `tests/unit/probes/layer_d/test_policy.py` | New file — 5 tests. |
| `tests/unit/probes/layer_d/test_exceptions.py` | New file — 6 tests (extra one for the expiry-partition logic). |
| `tests/unit/probes/layer_d/test_marker_probes_loc.py` | New file — three parametrized architectural tests across the five modules. |

## Out of scope

- **`ExternalDocsProbe`** — S6-04 (opt-in skip-cleanly; warrants its own story per the "do not invent an allowlist schema speculatively" discipline).
- **`ConventionsProbe`** — S6-02 (separate story; different shape — it runs rules, not just an index).
- **Policy-body parsing.** The probe records a path; reading the policy YAML is Phase 4+ Planner work.
- **Exception approval workflow.** The probe records what's declared; approval / expiry-extension is org-side process.
- **Markdown link extraction from `RepoNotes` bodies.** Bodies are not loaded. If the Planner needs a body, it reads the path directly.

## Notes for the implementer

1. **The 100-LOC ceiling is mutation-resistant by design.** Once a probe creeps to 110 LOC, the ceiling forces a review: is this complexity genuine (then the story is wrong-sized and we split), or is there a shared kernel emerging (then Rule-of-Three has triggered and the helper lands in `_markers/__init__.py`). Don't paper over by deleting tests or comments to shrink LOC.
2. **`safe_yaml.load` is the only YAML door.** `RepoConfigProbe` reads frontmatter via `safe_yaml.load`; `PolicyProbe` and `ExceptionProbe` read whole YAML files via the same loader. Body reads (markdown after the closing `---`) use bounded line iterators, never `read_text()`.
3. **Bounded line iterators, not `read_text()`.** `itertools.islice(open(path), 50)` reads at most 50 lines; even a 100 MB ADR with a corrupted "no newlines" body cannot blow memory. `read_text()` is a 100 MB allocation on the same file.
4. **`_STATUSES = {"proposed", "accepted", "deprecated", "superseded"}`** — the closed set the Pydantic `Literal` enforces. A future contributor adding `"draft"` must update both the set and the `Literal` (the type-check will catch the mismatch).
5. **`RepoConfigProbe`'s `body_byte_offset`** is the same anchor pattern as `SkillsIndexProbe` (S6-01). The Planner reads bodies; the probe records anchors.
6. **`ExceptionProbe`'s `expired:` partition is load-bearing.** A just-expired exception is the operator's signal to either renew it or accept that the previously-blocked task class is about to start running. Hiding expired entries would silently shift policy.
7. **No `pathlib.Path.glob("**/*.md")` recursive globs over the repo root.** Layer A probes already enforce repo-root file-budget caps; the marker probes here scan only specific subdirectories. A `**` glob on the repo root would re-scan every node_modules and break Phase 0's I/O budget.
8. **`PolicyProbe` reads `~/.codegenie/config.yaml`, not in-repo `.codegenie/config.yaml`.** Phase 2's repo-local config (`.codegenie/scenarios.yaml`) is per-probe; the policy-repo declaration is operator-global. The architectural test pins the home path.
9. **Sub-schemas for these five probes ship in S6-08** (`layer_d/{adrs,repo_notes,repo_config,policy,exceptions}.schema.json`). This story ships only the Pydantic models + probe code; sub-schema fixture validation is S6-08's last AC.
10. **`fnmatch.fnmatch` not regex for `repo_glob`.** Exceptions YAML's `repo_glob: "myservice*"` is a glob, not a regex (operator convention; documented in `localv2.md` §5.4 D6). A future migration to regex requires an ADR-amend, not a silent semantic change.
