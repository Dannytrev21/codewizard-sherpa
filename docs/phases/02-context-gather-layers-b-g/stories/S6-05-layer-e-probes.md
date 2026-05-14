# Story S6-05 — `Ownership` + `ServiceTopologyStub` + `SloStub` Layer E

**Step:** Step 6 — Ship Layer D + E + G probes (skills, conventions, ADRs, ownership, scanners)
**Status:** Ready
**Effort:** S
**Depends on:** S2-02 (`ConventionsCatalogLoader` pattern-types — establishes the marker-driven probe shape Layer E re-uses)
**ADRs honored:** 02-ADR-0005 (no plaintext persistence — emails / Slack handles in `CODEOWNERS` and `service.yaml` flow through the writer redactor), 02-ADR-0008 (no event stream in Phase 2 — `ServiceTopologyStub` and `SloStub` defer their real implementations to Phase 9+)
**Phase-2 deferred decision honored:** [`localv2.md` §5.5](../../../localv2.md) — "These probes are mostly stubbed for local-dev. They emit 'data unavailable' markers when their data sources aren't configured." Phase 2 ships `OwnershipProbe` for real (it's a simple `CODEOWNERS` parser) and ships `ServiceTopologyStub` + `SloStub` as deferred stubs (mirrors `ExternalDocsProbe` discipline).

## Context

Layer E (Cross-repo / Operational) is mostly forward-looking — most of its data sources are production service catalogs, service meshes, SLO definitions, on-call schedules. None of that is meaningfully available in the local POC. **One** probe in Layer E has a real local-dev consumer today: `OwnershipProbe`, which reads `CODEOWNERS`. The other two — service topology and SLOs — exist as registered stubs so Phase 9+ can extend without contract churn.

`CODEOWNERS` is a stable, line-oriented format (GitHub / GitLab convention): one line per pattern, `pattern @owner1 @team2`. The probe parses the file (if present), emits a `tuple[OwnershipEntry, ...]` keyed by pattern, and notes absent / malformed cases without raising. The repo-root file is the canonical location; `.github/CODEOWNERS`, `docs/CODEOWNERS`, `CODEOWNERS` are the three conventional paths (GitHub's documented search order).

`ServiceTopologyStub` and `SloStub` follow the `ExternalDocsProbe` (S6-04) discipline: register, run, emit `confidence="unavailable", reason="phase_9_or_later"` (or similar typed reason), keep the slice schema deliberately minimal so Phase 9 can extend with an ADR-amend rather than a backward-incompatible break.

Phase 0's secret redactor handles email leakage at the writer chokepoint. The Phase 2 commitment is that the *probe* doesn't pre-filter — it captures evidence honestly, and the writer chokepoint redacts. (`CODEOWNERS` emails aren't AWS keys, but the same chokepoint discipline applies: the probe is honest about what's in the file; the redactor decides what reaches disk.)

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md` §"Anti-patterns avoided"](../phase-arch-design.md) — "Schema before consumer" — `ServiceTopologyStub` ships a minimal schema with one consumer (the unit test); the real schema lands with Phase 9.
  - [`../phase-arch-design.md` §"Edge cases"](../phase-arch-design.md) — typed-reason discriminated unions across every state machine; `OwnershipProbe`'s "no file present" maps to a typed `Result`-shaped slice, not an exception.
- **Phase ADRs:**
  - [`../ADRs/0005-secret-findings-no-plaintext-persistence.md`](../ADRs/0005-secret-findings-no-plaintext-persistence.md) — emails are not secrets per se, but the redactor handles handles/emails at the writer chokepoint.
  - [`../ADRs/0008-no-event-stream-in-phase-2.md`](../ADRs/0008-no-event-stream-in-phase-2.md) — `SloStub`'s real data source (production SLO catalog) is a Phase-9-or-later event consumer.
- **Source design:**
  - [`../High-level-impl.md` §"Step 6"](../High-level-impl.md) — marker-driven; stubs for Phase 9+.
  - [`../../localv2.md` §5.5](../../../localv2.md) — Layer E description; stubs by default.
- **Existing kernel:**
  - `src/codegenie/probes/layer_d/external_docs.py` (S6-04) — the deferred-stub pattern this story re-uses (without sharing code; AC-12 forbids cross-imports).
  - `src/codegenie/probes/base.py` — `Probe` ABC.

## Goal

Ship three files under `src/codegenie/probes/layer_e/`: `ownership.py` (real `CODEOWNERS` parser), `service_topology_stub.py` (deferred stub), `slo_stub.py` (deferred stub). `OwnershipProbe` parses any of the three GitHub-convention locations and emits a typed slice; the two stubs emit `confidence="unavailable"` with a typed reason.

## Acceptance criteria

**Numbered for traceability to the TDD plan.**

- [ ] **AC-1.** Three new files exist under `src/codegenie/probes/layer_e/` plus `__init__.py`. Each file's `__all__` declares exactly the slice model + probe class.
- [ ] **AC-2.** All three probes are `@register_probe(heaviness="light")`; `timeout_seconds=5`; `applies_to_tasks=("*",)`; `applies_to_languages=("*",)`. `probe_id`s are `"ownership"`, `"service_topology"`, `"slo"`.
- [ ] **AC-3.** Each slice Pydantic model has `model_config = ConfigDict(frozen=True, extra="forbid")`.
- [ ] **AC-4.** **`OwnershipProbe` — happy path.** Reads `CODEOWNERS` from the first present of: `<repo>/CODEOWNERS`, `<repo>/.github/CODEOWNERS`, `<repo>/docs/CODEOWNERS`. Emits `OwnershipSlice(source_path: str, entries: tuple[OwnershipEntry, ...])` where `OwnershipEntry = (pattern: str, owners: tuple[str, ...], line_number: int)`.
- [ ] **AC-5.** **`OwnershipProbe` — file absent.** Returns `confidence="low"` (NOT `"unavailable"` — the probe was checked, the data was absent in a way the Planner can act on: "this repo has no CODEOWNERS, route to the default fallback").
- [ ] **AC-6.** **`OwnershipProbe` — malformed line.** A line like `*.py @valid-user` parses to one entry; a line like `*.py` (no owners) parses to `OwnershipEntry(pattern="*.py", owners=(), line_number=N)` and adds `"empty_owners_at_line_N"` to `errors`. Mutation caught: any "silently drop empty-owner lines" — operators need to know about misconfigured patterns.
- [ ] **AC-7.** **`OwnershipProbe` — comment lines + blank lines.** Lines starting with `#` and empty lines are skipped. Mutation caught: any parser that emits them as entries.
- [ ] **AC-8.** **`OwnershipProbe` — three-location search order.** When multiple `CODEOWNERS` files exist (which is operator misconfiguration but allowed), only the first found is parsed; the others are listed in `errors=["additional_codeowners_present_at: <path>", ...]`. Mutation caught: any merge-the-files behavior.
- [ ] **AC-9.** **`ServiceTopologyStub` — always unavailable.** Returns `confidence="unavailable"`, slice `ServiceTopologyStubSlice(opted_in: Literal[False], reason: Literal["phase_9_or_later"])`. No I/O.
- [ ] **AC-10.** **`SloStub` — always unavailable.** Same shape as service topology stub; `reason: Literal["phase_9_or_later"]`.
- [ ] **AC-11.** **No HTTP / service-catalog client imports.** Architectural test (parallel to S6-04 AC-6): the two stub files MUST NOT import `httpx`, `requests`, `aiohttp`, `urllib.request`, `socket`, or any service-mesh / service-catalog client library.
- [ ] **AC-12.** **No cross-probe imports.** `ownership.py`, `service_topology_stub.py`, `slo_stub.py` do not import each other. Also: none imports from `layer_d/` probes. Architectural test parametrized across the three files.
- [ ] **AC-13.** **Sub-schemas validate.** Each of the three slices round-trips through its `src/codegenie/schema/probes/layer_e/{ownership,service_topology,slo}.schema.json` (sub-schemas land in S6-08). `additionalProperties: false` at every level.
- [ ] **AC-14.** **`mypy --strict`** passes on all three files.
- [ ] **AC-15.** **Determinism.** Two consecutive runs on the same fixture produce byte-identical slices for all three probes. `OwnershipProbe` preserves source-file line order (NOT sorted — preserving authoring order is operationally useful when an entry is per-section).
- [ ] **AC-16.** **`OwnershipProbe` — body size cap.** A `CODEOWNERS` larger than `OWNERSHIP_MAX_BYTES = 1 * 1024 * 1024` (1 MB) is rejected with `confidence="low"` and `errors=["codeowners_size_cap_exceeded:<n_bytes>"]`. Mutation caught: any unbounded read would let a hostile repo OOM the gather.

## Implementation outline

1. Create `src/codegenie/probes/layer_e/__init__.py` (empty package marker; docstring).
2. `ownership.py`:
   - `_LOCATIONS = ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS")`.
   - `OWNERSHIP_MAX_BYTES: Final[int] = 1 * 1024 * 1024`.
   - `OwnershipEntry(BaseModel, frozen=True, extra="forbid")` with `pattern, owners, line_number`.
   - `OwnershipSlice(BaseModel, frozen=True, extra="forbid")` with `source_path, entries`.
   - `@register_probe(heaviness="light")` `class OwnershipProbe(Probe):` with `_run` that:
     - finds the first existing location; if none, returns `confidence="low"` with empty slice + `errors=["codeowners_absent"]`.
     - checks `os.path.getsize(path) <= OWNERSHIP_MAX_BYTES`; if exceeded, returns `confidence="low"` per AC-16.
     - reads via bounded line iterator (`itertools.islice` over `open(path)` with a max-lines guard); parses each line; emits entries preserving source order.
3. `service_topology_stub.py` and `slo_stub.py`:
   - Mirror S6-04's `ExternalDocsProbe` shape (Pydantic slice with `Literal[False]` + `Literal["phase_9_or_later"]`; `_run` returns the unavailable slice).
   - Module docstring states the deferral explicitly with the phrase `"deferred to Phase 9 or later"`.
4. Tests per the TDD plan.

## TDD plan — red / green / refactor

### Red — write the failing tests first

```python
# tests/unit/probes/layer_e/test_ownership.py
"""Unit tests for OwnershipProbe (S6-05)."""
from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.probes.base import ProbeContext, _PROBE_REGISTRY
from codegenie.probes.layer_e import ownership as op


def test_ownership_happy_path_parses_repo_root_file(tmp_path: Path) -> None:
    """AC-4. Mutation caught: any parser that emits owners as a single
    string instead of splitting on whitespace would fail the tuple
    length check."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CODEOWNERS").write_text(
        "# Default owners\n"
        "* @platform-team\n"
        "/api/ @api-team @platform-team\n"
        "*.md @docs-team\n"
    )
    ctx = ProbeContext.for_test(repo_root=repo)
    output = op.OwnershipProbe()._run(ctx)
    slice_ = op.OwnershipSlice.model_validate(output.schema_slice)
    assert slice_.source_path == "CODEOWNERS"
    assert len(slice_.entries) == 3
    assert slice_.entries[1].pattern == "/api/"
    assert slice_.entries[1].owners == ("@api-team", "@platform-team")
    assert slice_.entries[1].line_number == 3  # 0-indexed comments still count toward line number


def test_ownership_searches_three_locations_in_order(tmp_path: Path) -> None:
    """AC-8. Mutation caught: any precedence change (e.g.,
    `.github/CODEOWNERS` winning over root) — operators expect GitHub's
    documented order."""
    repo = tmp_path / "repo"
    (repo / ".github").mkdir(parents=True)
    (repo / "docs").mkdir()
    (repo / "CODEOWNERS").write_text("* @root\n")
    (repo / ".github" / "CODEOWNERS").write_text("* @github_dir\n")
    (repo / "docs" / "CODEOWNERS").write_text("* @docs_dir\n")
    ctx = ProbeContext.for_test(repo_root=repo)
    output = op.OwnershipProbe()._run(ctx)
    slice_ = op.OwnershipSlice.model_validate(output.schema_slice)
    assert slice_.source_path == "CODEOWNERS"  # root wins
    assert any("additional_codeowners_present_at" in e for e in output.errors)


def test_ownership_absent_yields_low_confidence_no_raise(tmp_path: Path) -> None:
    """AC-5. Mutation caught: re-raising on a no-CODEOWNERS repo."""
    repo = tmp_path / "repo"
    repo.mkdir()
    ctx = ProbeContext.for_test(repo_root=repo)
    output = op.OwnershipProbe()._run(ctx)
    assert output.confidence == "low"
    slice_ = op.OwnershipSlice.model_validate(output.schema_slice)
    assert slice_.entries == ()
    assert "codeowners_absent" in output.errors


def test_ownership_comment_and_blank_lines_skipped(tmp_path: Path) -> None:
    """AC-7. Mutation caught: emitting comments as entries with empty
    owners (would conflate with AC-6's empty-owners case)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CODEOWNERS").write_text("# header\n\n* @team\n# trailing\n\n")
    ctx = ProbeContext.for_test(repo_root=repo)
    output = op.OwnershipProbe()._run(ctx)
    slice_ = op.OwnershipSlice.model_validate(output.schema_slice)
    assert len(slice_.entries) == 1
    assert slice_.entries[0].pattern == "*"


def test_ownership_empty_owners_line_recorded_with_error(tmp_path: Path) -> None:
    """AC-6. Mutation caught: silently dropping `*.py` (pattern with no
    owners) — operators need to know this is misconfigured."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CODEOWNERS").write_text("*.py\n")
    ctx = ProbeContext.for_test(repo_root=repo)
    output = op.OwnershipProbe()._run(ctx)
    slice_ = op.OwnershipSlice.model_validate(output.schema_slice)
    assert slice_.entries[0].pattern == "*.py"
    assert slice_.entries[0].owners == ()
    assert any("empty_owners_at_line_1" in e for e in output.errors)


def test_ownership_size_cap_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-16. Mutation caught: any unbounded read. Uses `os.stat`
    monkey-patch to assert the cap fires before any read."""
    import os

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CODEOWNERS").write_text("* @team\n")

    real_stat = os.stat

    def fake_stat(path, *args, **kwargs):
        st = real_stat(path, *args, **kwargs)
        if str(path).endswith("CODEOWNERS"):
            class _ST:
                st_size = op.OWNERSHIP_MAX_BYTES + 1
                st_mode = st.st_mode
                st_mtime = st.st_mtime
            return _ST()
        return st

    monkeypatch.setattr(os, "stat", fake_stat)
    monkeypatch.setattr(os.path, "getsize", lambda p: op.OWNERSHIP_MAX_BYTES + 1)
    output = op.OwnershipProbe()._run(ProbeContext.for_test(repo_root=repo))
    assert output.confidence == "low"
    assert any("codeowners_size_cap_exceeded" in e for e in output.errors)


def test_ownership_two_runs_byte_identical(tmp_path: Path) -> None:
    """AC-15. Mutation caught: any sort/reorder — line order preserves
    operator's intent (early lines often override later)."""
    import json

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CODEOWNERS").write_text("/b/ @b\n/a/ @a\n/c/ @c\n")
    ctx = ProbeContext.for_test(repo_root=repo)
    out1 = op.OwnershipProbe()._run(ctx).schema_slice
    out2 = op.OwnershipProbe()._run(ctx).schema_slice
    assert json.dumps(out1, sort_keys=True) == json.dumps(out2, sort_keys=True)
    # Verify line order preserved (NOT sorted alphabetically).
    slice_ = op.OwnershipSlice.model_validate(out1)
    assert [e.pattern for e in slice_.entries] == ["/b/", "/a/", "/c/"]
```

```python
# tests/unit/probes/layer_e/test_stubs.py
"""Unit tests for ServiceTopologyStub + SloStub (S6-05)."""
from __future__ import annotations

import ast
import inspect

import pytest

from codegenie.probes.base import ProbeContext, _PROBE_REGISTRY
from codegenie.probes.layer_e import service_topology_stub as sts
from codegenie.probes.layer_e import slo_stub as slo


@pytest.mark.parametrize(
    ("module", "probe_cls", "slice_cls", "probe_id"),
    [
        (sts, sts.ServiceTopologyStubProbe, sts.ServiceTopologyStubSlice, "service_topology"),
        (slo, slo.SloStubProbe, slo.SloStubSlice, "slo"),
    ],
)
def test_stub_always_unavailable(module, probe_cls, slice_cls, probe_id, tmp_path) -> None:
    """AC-9, AC-10. Mutation caught: any future code that flips to
    `confidence="low"` without an ADR-amend."""
    ctx = ProbeContext.for_test(repo_root=tmp_path)
    output = probe_cls()._run(ctx)
    assert output.confidence == "unavailable"
    slice_ = slice_cls.model_validate(output.schema_slice)
    assert slice_.opted_in is False
    assert slice_.reason == "phase_9_or_later"


@pytest.mark.parametrize("module", [sts, slo])
def test_stub_no_forbidden_imports(module) -> None:
    """AC-11. Mutation caught: any HTTP client import would break the
    Phase-0 fence — and also break the determinism guarantee."""
    forbidden = {"httpx", "requests", "urllib.request", "aiohttp", "socket"}
    tree = ast.parse(inspect.getsource(module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    assert not (forbidden & names)


@pytest.mark.parametrize("module", [sts, slo])
def test_stub_docstring_documents_deferral(module) -> None:
    """Mirrors S6-04 AC-2 — grep-discoverability for Phase 9+."""
    assert module.__doc__ is not None
    assert "deferred to Phase 9 or later" in module.__doc__
```

### Green — make it pass

Skeleton for `ownership.py`:

```python
# src/codegenie/probes/layer_e/ownership.py
"""OwnershipProbe — Layer E, light heaviness.

Parses CODEOWNERS from the three GitHub-convention locations.
Source: ../../localv2.md §5.5 E1.
"""
from __future__ import annotations

import itertools
import os
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict

from codegenie.ids import ProbeId
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, register_probe

__all__ = ["OwnershipProbe", "OwnershipEntry", "OwnershipSlice"]

_LOCATIONS: Final[tuple[str, ...]] = ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS")
OWNERSHIP_MAX_BYTES: Final[int] = 1 * 1024 * 1024  # 1 MB


class OwnershipEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    pattern: str
    owners: tuple[str, ...]
    line_number: int


class OwnershipSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_path: str | None
    entries: tuple[OwnershipEntry, ...]


@register_probe(heaviness="light")
class OwnershipProbe(Probe):
    probe_id = ProbeId("ownership")
    applies_to_tasks: tuple[str, ...] = ("*",)
    applies_to_languages: tuple[str, ...] = ("*",)
    timeout_seconds = 5

    def _run(self, ctx: ProbeContext) -> ProbeOutput:
        found: list[Path] = []
        for loc in _LOCATIONS:
            p = ctx.repo_root / loc
            if p.exists():
                found.append(p)
        if not found:
            return ProbeOutput(
                probe_id=self.probe_id,
                confidence="low",
                schema_slice=OwnershipSlice(source_path=None, entries=()).model_dump(mode="json"),
                errors=["codeowners_absent"],
            )
        primary = found[0]
        errors: list[str] = [
            f"additional_codeowners_present_at:{p.relative_to(ctx.repo_root)}" for p in found[1:]
        ]
        size = os.path.getsize(primary)
        if size > OWNERSHIP_MAX_BYTES:
            return ProbeOutput(
                probe_id=self.probe_id,
                confidence="low",
                schema_slice=OwnershipSlice(
                    source_path=str(primary.relative_to(ctx.repo_root)), entries=()
                ).model_dump(mode="json"),
                errors=[f"codeowners_size_cap_exceeded:{size}"] + errors,
            )
        entries: list[OwnershipEntry] = []
        with open(primary) as fh:
            for idx, line in enumerate(itertools.islice(fh, 50_000), start=1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                tokens = stripped.split()
                if len(tokens) == 1:
                    errors.append(f"empty_owners_at_line_{idx}")
                    entries.append(OwnershipEntry(pattern=tokens[0], owners=(), line_number=idx))
                    continue
                entries.append(
                    OwnershipEntry(pattern=tokens[0], owners=tuple(tokens[1:]), line_number=idx)
                )
        return ProbeOutput(
            probe_id=self.probe_id,
            confidence="high",
            schema_slice=OwnershipSlice(
                source_path=str(primary.relative_to(ctx.repo_root)), entries=tuple(entries)
            ).model_dump(mode="json"),
            errors=errors,
        )
```

`service_topology_stub.py` and `slo_stub.py` mirror the `external_docs.py` shape from S6-04 — a Pydantic slice with `Literal[False]` + `Literal["phase_9_or_later"]`, and a `_run` returning the unavailable slice.

### Refactor

- **Do not extract a shared stub base** between `service_topology_stub`, `slo_stub`, and `external_docs`. Three deferred-stub probes with identical inert shape *would* be the Rule-of-Three trigger — but each one's `reason: Literal[...]` differs (`"not_opted_in"`, `"phase_9_or_later"`, `"phase_9_or_later"`), and that closed-set discriminator must remain visible per-file. Extracting a base would force a string-typed reason or a generic over the Literal — both worse than the duplication.
- The three Phase 2 stubs *together* are the rule-of-three case. The "extract a `DeferredStubProbe` base" conversation lands at Phase 4 if there's a fourth stub at that point. Not now.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/layer_e/__init__.py` | New file — package marker. |
| `src/codegenie/probes/layer_e/ownership.py` | New file — real `CODEOWNERS` parser. |
| `src/codegenie/probes/layer_e/service_topology_stub.py` | New file — deferred stub. |
| `src/codegenie/probes/layer_e/slo_stub.py` | New file — deferred stub. |
| `tests/unit/probes/layer_e/__init__.py` | New file — empty package marker. |
| `tests/unit/probes/layer_e/test_ownership.py` | New file — 7 tests. |
| `tests/unit/probes/layer_e/test_stubs.py` | New file — parametrized across the two stubs. |

## Out of scope

- **Service-catalog HTTP clients** (Backstage, OpsLevel, Cortex). Phase 9+.
- **Service mesh API integration** (Istio, Linkerd, Consul Connect). Phase 9+.
- **OpenAPI / gRPC / GraphQL parsing** (`ServiceContractProbe` — E3 in `localv2.md`). Phase-3-or-later; not Phase 2's scope per the manifest.
- **Production config probe** (E5). Phase 9+ deferred stub.
- **Email / handle redaction.** The writer chokepoint (`SecretRedactor`) handles it via Phase 0's field-name regex + Phase 2's pattern set. The probe captures `@team`/`@user` honestly.

## Notes for the implementer

1. **`OwnershipProbe.confidence` is `"low"` on absent file, not `"unavailable"`.** The distinction matters: "unavailable" means "this data class wasn't checked"; "low" means "we checked and got weak data." Absent CODEOWNERS is data — it means "this repo has no owners declared, route to default."
2. **`itertools.islice(fh, 50_000)` is the line cap.** A `CODEOWNERS` with 50,000+ lines is hostile; bounded iteration is the same discipline as the marker probes (S6-03). The byte-size cap (AC-16) is the first defense; the line cap is belt-and-suspenders.
3. **`OwnershipEntry.line_number` is 1-indexed and includes blank/comment lines in the count.** Operators expect a line number that matches their editor (`vim +N`). Counting only emitted entries would diverge from the actual file.
4. **GitHub's documented search order** is `.github/CODEOWNERS` > `CODEOWNERS` > `docs/CODEOWNERS`. The implementation here uses `CODEOWNERS` > `.github/CODEOWNERS` > `docs/CODEOWNERS`. **This is intentional** — Phase 2's discipline is "the root location wins" because it's the most visible. If an operator wants `.github/CODEOWNERS` to win, they delete the root file. Document this divergence from GitHub in the module docstring; an ADR is not warranted but the comment is.
5. **`OwnershipSlice.source_path: str | None`** is honest about the absent case. A sentinel `""` would be primitive obsession; `None` is the right "no file" representation.
6. **`OwnershipEntry.owners` is `tuple[str, ...]`, not `set[str]`.** A `CODEOWNERS` line `*.py @a @b @a` is operator misconfiguration but is parsed as-given; deduplication is the Planner's responsibility (or a later linter probe).
7. **`ServiceTopologyStub` and `SloStub` are deliberately near-identical.** Resist refactoring them into a single file or a base class — the closed `reason: Literal[...]` discriminator on each will diverge when Phase 9 lands (`SloProbe.reason` will become a Pydantic union over per-source errors; `ServiceTopologyProbe.reason` will become a different union). Their identicality now is a coincidence of "both empty."
8. **Sub-schemas land in S6-08.** This story ships the Pydantic models; S6-08 ships the JSON-Schema files under `src/codegenie/schema/probes/layer_e/`.
