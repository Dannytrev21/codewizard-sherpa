# Story S6-04 — `ExternalDocsProbe` opt-in skip-cleanly stub

**Step:** Step 6 — Ship Layer D + E + G probes (skills, conventions, ADRs, ownership, scanners)
**Status:** Ready
**Effort:** S
**Depends on:** S6-03 (Layer D marker-probe shape established; this probe re-uses the `confidence="unavailable"`-on-marker-absent pattern but emits a more specific `reason="not_opted_in"`)
**ADRs honored:** 02-ADR-0007 (no plugin loader in Phase 2 — and by extension, no Confluence/Notion HTTP clients), 02-ADR-0005 (no plaintext persistence), 02-ADR-0008 (no event stream in Phase 2 — RAG-store handoff deferred to Phase 4)
**Phase-2 deferred decision honored:** [final-design.md "Open Q 4"](../final-design.md) — `external_docs:` allowlist schema lands when the first real user opts in. Phase 2 ships the skip-cleanly stub. **Do NOT invent an allowlist schema speculatively.**

## Context

`ExternalDocsProbe` is the only Layer D probe whose data sources live outside the repo and outside `~/.codegenie/` — Confluence, Notion, internal wikis, HTTP doc lists. The full design (`localv2.md` §5.4 D8) is rich: configurable per-source fetchers, normalization to markdown, BM25 indexing (D9), table-of-contents extraction. Shipping all of that in Phase 2 would violate three commitments at once:

1. **"No LLM anywhere in the gather pipeline."** Confluence clients aren't LLMs, but they introduce network I/O the determinism story doesn't support.
2. **"Extension by addition."** A real `external_docs:` config schema has six+ source types (Confluence, Notion, filesystem, URL list, …); each requires its own Pydantic discriminated union variant. Picking that schema before a real user opts in guarantees it will be wrong (the "premature schema" failure mode).
3. **The Phase 0 `fence` job.** `external_docs:` clients use `httpx` / `requests` / `socket`; the fence forbids those imports under `src/codegenie/`. Shipping a real fetcher requires an ADR-amend on the fence allowlist.

Phase 2's contract: the probe **exists**, is registered, runs in every gather, and emits `confidence="unavailable", reason="not_opted_in"` when the config key is absent (default state). When a real user opts in later, the probe's `_run` extends — but Phase 2 ships only the inert default path. The slice schema for "opted in" lands with the first opt-in (Phase 4-or-later); Phase 2's sub-schema covers only the unavailable shape.

The discipline this story protects: **don't write a speculative `external_docs:` allowlist schema**. A future maintainer reading this story should see "we deliberately deferred" rather than "we sketched a schema and then we'll iterate."

## References — where to look

- **Architecture:**
  - [`../final-design.md` Open Q 4](../final-design.md) — `ExternalDocsProbe` enablement & host allowlist schema deferred.
  - [`../phase-arch-design.md` §"Open questions deferred to implementation"](../phase-arch-design.md) #4 — same deferral.
  - [`../phase-arch-design.md` §"Anti-patterns avoided"](../phase-arch-design.md) "Schema before consumer" — every typed sum has a Phase 2 consumer; the opted-in variant has no Phase 2 consumer, so it does not ship.
- **Phase ADRs:**
  - [`../ADRs/0008-no-event-stream-in-phase-2.md`](../ADRs/0008-no-event-stream-in-phase-2.md) — the same deferral pattern: ship the boundary, defer the implementation.
- **Source design:**
  - [`../High-level-impl.md` §"Step 6"](../High-level-impl.md) — "opt-in skip-cleanly; allowlist schema lands when the first real user opts in."
  - [`../../localv2.md` §5.4 D8](../../../localv2.md) — the full eventual design (for reference only; Phase 2 ships *none* of it beyond the unavailable stub).
- **Existing kernel:**
  - `src/codegenie/probes/base.py` — `Probe` ABC; `ProbeOutput.confidence` accepts `"unavailable"` (Phase 0).

## Goal

Implement `src/codegenie/probes/layer_d/external_docs.py` as a `@register_probe(heaviness="light")` probe that reads `ctx.repo_config.get("external_docs")` (or equivalent — depends on Phase 0 config plumbing); when absent or empty, emits `confidence="unavailable", reason="not_opted_in"` and a minimal slice. The probe's module docstring states explicitly that the allowlist schema is deferred per final-design Open Q 4. No HTTP clients, no fetchers, no `httpx`/`requests`/`socket` imports.

## Acceptance criteria

**Numbered for traceability to the TDD plan.**

- [ ] **AC-1.** `src/codegenie/probes/layer_d/external_docs.py` exports exactly `__all__ = ["ExternalDocsProbe", "ExternalDocsSlice"]`.
- [ ] **AC-2.** **Module docstring states the deferral explicitly.** The first paragraph of the module docstring contains the exact string `"Phase 2 ships the skip-cleanly stub; the opted-in schema lands when the first real user opts in (final-design.md Open Q 4)"`. An architectural test asserts this — future contributors who add a fetcher without amending the docstring fail the test.
- [ ] **AC-3.** `ExternalDocsSlice` is a Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")` carrying exactly: `opted_in: Literal[False]` (the Phase-2 closed value), `reason: Literal["not_opted_in"]`. When the schema extends to `opted_in: True`, that's an ADR-amend, not a backward-compatible additive change.
- [ ] **AC-4.** `ExternalDocsProbe` is `@register_probe(heaviness="light")`; `probe_id = ProbeId("external_docs")`; `applies_to_tasks = ("*",)`; `applies_to_languages = ("*",)`; `timeout_seconds=5`.
- [ ] **AC-5.** `_run()` returns `ProbeOutput(confidence="unavailable", schema_slice=ExternalDocsSlice(opted_in=False, reason="not_opted_in").model_dump(mode="json"), errors=[])`. No file I/O. No network I/O. No `safe_yaml.load`.
- [ ] **AC-6.** **No forbidden imports.** The probe file does **not** import `httpx`, `requests`, `urllib.request`, `socket`, `aiohttp`, or any HTTP client. Architectural test: parse the module via `ast.parse(inspect.getsource(external_docs))` and assert no `Import`/`ImportFrom` node names any of the forbidden modules. Phase 0's `fence` job catches this too, but this story's test fires in `unit` (faster signal).
- [ ] **AC-7.** **No allowlist schema speculation.** The probe file does NOT define a Pydantic model for an `external_docs:` config entry, an enum of source types, or any `Confluence` / `Notion` / `URLList` / `Filesystem` variants. Architectural test: `inspect.getsource(external_docs)` does not contain any of those substrings.
- [ ] **AC-8.** **Slice schema validates.** `tests/unit/probes/layer_d/test_external_docs.py::test_slice_matches_subschema` round-trips the slice through `src/codegenie/schema/probes/layer_d/external_docs.schema.json` (sub-schema lands in S6-08) — schema asserts `opted_in: false` is the only allowed value, `additionalProperties: false`.
- [ ] **AC-9.** **`heaviness="light"`** — registry-verified.
- [ ] **AC-10.** **Determinism.** Two consecutive `_run()` calls produce byte-identical output; no timestamps, no IDs, no per-run nonces.
- [ ] **AC-11.** **`mypy --strict`** passes.
- [ ] **AC-12.** **Phase 0 `fence` re-check.** The CI `fence` job (Phase 0) still passes after this probe lands — no new forbidden imports under `src/codegenie/`. (This is asserted by an existing CI job, not by a per-story test.)
- [ ] **AC-13.** **The deferral is grep-able.** A future Phase-4 contributor running `grep -rn "Open Q 4" src/codegenie/` MUST find this module. The module docstring's exact phrase `final-design.md Open Q 4` is the deliberate trip-wire.
- [ ] **AC-14.** **Backlog filing.** S8-04 (Phase-2 backlog summary) lands a follow-up entry with the same `Open Q 4` reference. The architectural test from this story also pattern-matches the manifest README's "Decisions noted" #4 entry to ensure the deferral is documented in two places (probe docstring + manifest).

## Implementation outline

1. Create `src/codegenie/probes/layer_d/external_docs.py`:
   - Module docstring with the exact AC-2 phrase, plus pointers to Open Q 4 and ADR-0007.
   - `ExternalDocsSlice(BaseModel)` per AC-3.
   - `@register_probe(heaviness="light")` `class ExternalDocsProbe(Probe):`
     - `probe_id = ProbeId("external_docs")`; rest of attrs per AC-4.
     - `_run()` returns the unavailable slice unconditionally.
2. Write `tests/unit/probes/layer_d/test_external_docs.py` per the TDD plan.

## TDD plan — red / green / refactor

### Red — write the failing tests first

```python
# tests/unit/probes/layer_d/test_external_docs.py
"""Unit + architectural tests for ExternalDocsProbe (S6-04).

This story's tests are unusual: most ACs are *deferrals* — assertions
about what the probe does NOT do. That's load-bearing per the design's
"Schema before consumer" discipline: an opted-in schema with no Phase 2
consumer would be premature.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from codegenie.probes.base import ProbeContext, _PROBE_REGISTRY
from codegenie.probes.layer_d import external_docs as ed


def test_run_returns_unavailable_not_opted_in_by_default() -> None:
    """AC-5. Mutation caught: any future "if `external_docs:` in config:
    fetch …" path that ships without an ADR — the test pins the
    skip-cleanly default."""
    ctx = ProbeContext.for_test(repo_root=Path("/tmp/anything"))
    output = ed.ExternalDocsProbe()._run(ctx)
    assert output.confidence == "unavailable"
    slice_ = ed.ExternalDocsSlice.model_validate(output.schema_slice)
    assert slice_.opted_in is False
    assert slice_.reason == "not_opted_in"
    assert output.errors == []


def test_module_docstring_contains_open_q_4_phrase() -> None:
    """AC-2, AC-13. Mutation caught: a future contributor adding a
    fetcher and removing the deferral docstring — the explicit phrase
    is the grep-discoverability trip-wire."""
    assert ed.__doc__ is not None
    expected = (
        "Phase 2 ships the skip-cleanly stub; the opted-in schema lands when "
        "the first real user opts in (final-design.md Open Q 4)"
    )
    assert expected in ed.__doc__


def test_no_forbidden_http_or_socket_imports() -> None:
    """AC-6. Mutation caught: any `import httpx` (or aiohttp, requests,
    urllib.request, socket) — Phase 0's fence job would also catch this,
    but the test fires in `unit` lane for fast signal."""
    forbidden = {"httpx", "requests", "urllib.request", "aiohttp", "socket"}
    tree = ast.parse(inspect.getsource(ed))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    assert not (forbidden & names), f"Forbidden imports found: {forbidden & names}"


def test_no_speculative_allowlist_schema() -> None:
    """AC-7. Mutation caught: a future contributor adding `Confluence`,
    `NotionSource`, or `URLList` Pydantic variants before the first
    real user opts in — the "Schema before consumer" anti-pattern."""
    src = inspect.getsource(ed)
    speculative = ("Confluence", "Notion", "URLList", "URLSource", "FilesystemSource")
    for token in speculative:
        assert token not in src, (
            f"{token!r} suggests a speculative allowlist schema. The schema "
            "lands when the first real user opts in (final-design Open Q 4)."
        )


def test_slice_rejects_opted_in_true_at_pydantic_level() -> None:
    """AC-3. Mutation caught: relaxing `opted_in: Literal[False]` to
    `bool` would silently accept a True value before the opted-in
    branch exists in `_run` — the validation error is the type-level
    enforcement."""
    with pytest.raises(Exception):  # ValidationError
        ed.ExternalDocsSlice(opted_in=True, reason="not_opted_in")  # type: ignore[arg-type]


def test_slice_rejects_extra_fields() -> None:
    """AC-3. Mutation caught: a future contributor adding a
    `fetched_count` field before the opted-in shape is defined."""
    with pytest.raises(Exception):  # ValidationError on extra="forbid"
        ed.ExternalDocsSlice(
            opted_in=False, reason="not_opted_in", fetched_count=0  # type: ignore[call-arg]
        )


def test_two_consecutive_runs_byte_identical() -> None:
    """AC-10. Mutation caught: any timestamp / nonce / per-run ID in
    the unavailable slice would diverge on the second run."""
    import json
    ctx = ProbeContext.for_test(repo_root=Path("/tmp/anything"))
    out1 = ed.ExternalDocsProbe()._run(ctx).schema_slice
    out2 = ed.ExternalDocsProbe()._run(ctx).schema_slice
    assert json.dumps(out1, sort_keys=True) == json.dumps(out2, sort_keys=True)


def test_registry_heaviness_is_light() -> None:
    """AC-9. Mutation caught: bumping heaviness for a probe that does
    no work would mis-budget the coordinator."""
    assert _PROBE_REGISTRY["external_docs"].heaviness == "light"


def test_slice_matches_subschema_with_strict_additional_properties() -> None:
    """AC-8. Mutation caught: a future schema that admits `opted_in: true`
    without an ADR — the schema is the contract."""
    import json
    from importlib.resources import files

    import jsonschema

    schema = json.loads(
        (files("codegenie.schema.probes.layer_d") / "external_docs.schema.json").read_text()
    )
    good = {"opted_in": False, "reason": "not_opted_in"}
    jsonschema.validate(good, schema)
    bad_opted_in = {"opted_in": True, "reason": "not_opted_in"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad_opted_in, schema)


def test_manifest_readme_documents_deferral() -> None:
    """AC-14. Mutation caught: removing the deferral note from the
    manifest's "Decisions noted" section — the deferral lives in two
    places (probe docstring + manifest) so neither alone can drop the
    discipline silently."""
    manifest = Path(__file__).parents[4] / "docs" / "phases" / (
        "02-context-gather-layers-b-g"
    ) / "stories" / "README.md"
    assert manifest.exists()
    text = manifest.read_text()
    assert "ExternalDocsProbe" in text
    assert "opt-in" in text.lower() or "opted_in" in text.lower()
```

### Green — make it pass

```python
# src/codegenie/probes/layer_d/external_docs.py
"""ExternalDocsProbe — Layer D, light heaviness, deferred-implementation stub.

Phase 2 ships the skip-cleanly stub; the opted-in schema lands when
the first real user opts in (final-design.md Open Q 4). The probe is
registered so it runs in every gather and emits a typed `unavailable`
slice — but it performs no I/O, no network calls, no config parsing
beyond what's already in `ProbeContext`. When a future user wants
Confluence / Notion / URL-list integration, the work is:

1. ADR-amend on the `external_docs:` allowlist schema (host list +
   credential plumbing + size cap).
2. ADR-amend on Phase 0's `fence` job to permit an HTTP client.
3. Extend `ExternalDocsSlice` with an `opted_in: True` variant.
4. Implement `_run` for the opted-in branch.

NONE of those four steps happens in Phase 2. This module is
deliberately inert.

Sources:
- ../final-design.md Open Q 4.
- ../phase-arch-design.md §"Open questions deferred to implementation" #4.
- ../ADRs/0007-no-plugin-loader-in-phase-2.md (the same "ship the
  boundary, defer the implementation" discipline applied to a
  different surface).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from codegenie.ids import ProbeId
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, register_probe

__all__ = ["ExternalDocsProbe", "ExternalDocsSlice"]


class ExternalDocsSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    opted_in: Literal[False]
    reason: Literal["not_opted_in"]


@register_probe(heaviness="light")
class ExternalDocsProbe(Probe):
    probe_id = ProbeId("external_docs")
    applies_to_tasks: tuple[str, ...] = ("*",)
    applies_to_languages: tuple[str, ...] = ("*",)
    timeout_seconds = 5

    def _run(self, ctx: ProbeContext) -> ProbeOutput:
        slice_ = ExternalDocsSlice(opted_in=False, reason="not_opted_in")
        return ProbeOutput(
            probe_id=self.probe_id,
            confidence="unavailable",
            schema_slice=slice_.model_dump(mode="json"),
            errors=[],
        )
```

### Refactor

- The probe is deliberately a one-liner-style stub. Resist refactoring it into a "base" class that the opted-in version will subclass — that's the same speculative-coupling failure mode AC-7 forbids. When the opted-in branch lands, it lands as conditional logic *in this file*, not as a class hierarchy.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/layer_d/external_docs.py` | New file — deferred-implementation stub. |
| `tests/unit/probes/layer_d/test_external_docs.py` | New file — 10 tests, most of which are *negative* (asserting absence of speculation). |

## Out of scope

- **The opted-in `external_docs:` schema.** Phase 4-or-later, gated by ADR-amend on the fence job + at least one real user opting in.
- **HTTP clients, Confluence/Notion API clients, BM25 indexing.** All deferred.
- **`ExternalDocsIndexProbe` (D9 in localv2.md).** Lands with the opt-in flow; there is no Phase-2 consumer.
- **Per-source-type Pydantic variants.** Picking a discriminated union shape before a real user opts in is exactly the "Schema before consumer" anti-pattern.

## Notes for the implementer

1. **The negative tests are doing real work.** A test that says "no `Confluence` substring" looks paranoid; it isn't. The Phase-2 design table calls out "Schema before consumer" as a flag-on-sight anti-pattern, and a speculative Confluence variant is the textbook example. The test fires the moment a contributor types `class Confluence...` — long before review can catch it.
2. **`Literal[False]` is the load-bearing type.** A future contributor relaxing to `bool` would silently allow an `opted_in: True` slice through Pydantic, but the `_run` method would still return `opted_in=False` — the test catches the type relaxation directly. When the opted-in branch eventually lands, the migration is: change to `Literal[True] | Literal[False]` (or just `bool`), add the opted-in variant, ADR-amend.
3. **The docstring phrase is grep-bait.** `grep -rn "Open Q 4" src/codegenie/` MUST find this module after this story lands. Phase-4 contributors will run that grep when they pick up the deferred work; the discoverability is the contract.
4. **No `safe_yaml.load`.** This probe reads no YAML. If a future contributor's gut reaction is "let me at least check if the config key exists," resist — that's the slippery slope to a real fetcher. The opted-in branch reads config *and* fetches; either you ship both with an ADR-amend or you ship neither.
5. **`confidence="unavailable"` is the right level.** Not `"low"` (which means "we tried and got weak data"); not `"high"` (which means "the absence is itself the data"). Unavailable communicates "this probe has nothing to say in this configuration" — which is exactly the truth.
6. **AC-14's two-place documentation is anti-fragile.** A future contributor deleting the docstring deferral *or* removing the manifest entry would have to update both. The probability of a contributor doing both deliberately (vs. silently in a refactor) is much lower; the test fires the moment one or the other goes stale.
