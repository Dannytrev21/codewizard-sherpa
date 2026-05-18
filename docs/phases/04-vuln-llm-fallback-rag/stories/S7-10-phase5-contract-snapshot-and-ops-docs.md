# Story S7-10 — Phase-5 contract snapshot + ops runbooks

**Step:** Step 7 — Ship plugin wiring: FallbackTierPlanRecipeEngine + harvest + E2E exit criteria
**Status:** Ready
**Effort:** M
**Depends on:** S7-06 (full E2E green — the snapshot is honest only if the contract surface actually works); S6-01 (`FallbackTier.run` signature stable); S3-05 (`cassettes.lock` format stable); S3-02 (`AnthropicLeafAdapter` + `keyring` flow stable); S2-05 (`LlmInvocationGuard.running_total`); S4-06 (`SolvedExampleWriteCapability` mint surface); S4-01 (embeddings bootstrap)
**ADRs honored:** ADR-0009 (`_phase4_local_capability_mint` is interim — Phase 5 supersedes), ADR-0002 (FallbackTier signature stability), production-ADR-0031 (extension by addition; Phase 5 hands-off contract)

## Context

Two related deliverables in one story because they share an owner (Phase-4 → Phase-5 handoff) and a deadline (Step-7 merge gate):

1. **Phase-5 contract snapshot refresh.** `tests/integration/test_phase5_contract_snapshot.py` is the canonical surface that Phase 5 (Sandbox + Trust-Aware Gates) reads against. It pinned Phase 3's surface at the end of Phase 3; this story adds the **additive** Phase-4 entries: `FallbackTier.run(advisory, repo_ctx, recipe_selection, *, prior_attempts=[]) -> RecipeApplication`, `LlmInvocationGuard.running_total() -> BudgetSnapshot`, `FenceWrapper.fence(payload, source_kind) -> FencedSegment`, `SolvedExampleWriteCapability` mint signature, `cassettes.lock` line format. The snapshot test is **byte-equal** — if any of these signatures drift after Step 7 merges, the snapshot diff is the alarm.

2. **Operations runbooks.** Phase 4 introduces three new operator-facing concerns: Anthropic API key (`keyring`) management (S3-02), cassette refresh + steward rotation (S3-06), and embeddings model bootstrap + rebuild (S4-01 + S4-07). The arch §"What's next" calls these out as Phase-9 (Temporal worker) preconditions: the operator needs documented procedures for each before deployment. The three docs land under `docs/operations/`:
   - `docs/operations/secrets.md` — Anthropic key storage, rotation, refuse-to-start on missing key, no env-var fallback (ADR-0006).
   - `docs/operations/cassettes.md` — already started in S3-06; this story finalizes it with the steward rotation cadence, the `make refresh-cassettes` invocation, the CODEOWNERS approval flow, and the BLAKE3 lock refresh.
   - `docs/operations/embeddings.md` — `codegenie embeddings bootstrap`, `codegenie rag rebuild [--reembed]`, the `embeddings_model.lock` sha256 contract, refuse-to-start behavior on drift.

Plus a third deliverable mentioned in the High-level-impl: **publish `tests/fixtures/fallback_tier_callable.py`** as the contract Phase 6 (LangGraph runtime) reads when it lifts `FallbackTier.run` into a graph node — no code change to Phase 4 at that lift.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Stable contracts` — "Stable contracts (versioned by `tests/integration/test_phase5_contract_snapshot.py`): `FallbackTier.run` signature, `LeafLlm` Protocol, `PlanProposal` union members + field names, `LlmInvocationGuard.running_total()` return shape, `RetrievalOutcome` variants, `SolvedExampleWriteCapability` mint surface, `FenceWrapper.fence` signature, `cassettes.lock` line format."
  - `../phase-arch-design.md §What's next — handoff to Phase 5` — the seven hand-off interfaces Phase 5 consumes.
  - `../phase-arch-design.md §Configuration` — the operator-facing concerns this story documents.
  - `../phase-arch-design.md §Component 8 — Embedder` — `codegenie embeddings bootstrap` CLI; `embeddings_model.lock` discipline.
  - `../phase-arch-design.md §Component 12 — CassetteSanitizer` + discipline.
- **Phase ADRs:**
  - `../ADRs/0009-inline-auto-harvest-confidence-gate.md` — Consequences section: "`tests/fixtures/fallback_tier_callable.py` is published as the contract Phase 6 reads."
  - `../ADRs/0005-no-spki-pin-egress-defense-in-depth.md` — key in keyring; no env-var fallback (operator docs cite this).
  - `../ADRs/0006-egress-guard-no-production-loopback-carveout.md` — operator docs cross-link.
  - `../ADRs/0014-cassette-discipline-security-control.md` — cassette ops runbook anchor.
  - `../ADRs/0007-fastembed-onnx-over-sentence-transformers.md` — embeddings bootstrap ops anchor.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` — Phase 5 hand-off contract framing.
- **Source design:**
  - `../final-design.md §"What's next"` — the seven Phase-5 hand-off items.
- **High-level impl:**
  - `../High-level-impl.md §Step 7 §Done criteria` — "`tests/integration/test_phase5_contract_snapshot.py` updated to capture additive interface lines from Phase 4 ...; `tests/fixtures/fallback_tier_callable.py` published as the contract Phase 6 reads ...; Documentation: `docs/operations/{secrets.md, cassettes.md, embeddings.md}` runbooks landed."
  - `../High-level-impl.md §"What's next — handoff to Phase 5"` — duplicated; the same seven items.
- **Existing code:**
  - `tests/integration/test_phase5_contract_snapshot.py` (Phase 3 S6-06) — the snapshot test scaffolding; read its inspection pattern carefully. **Add to it; do not rewrite.**
  - `tests/fixtures/fallback_tier_callable.py` — does not yet exist; this story creates it.
  - `src/codegenie/fallback/tier.py` (S6-01) — `FallbackTier.run` signature.
  - `src/codegenie/fallback/budget.py` (S2-05) — `LlmInvocationGuard.running_total`.
  - `src/codegenie/fallback/fence/wrapper.py` (S2-02) — `FenceWrapper.fence`.
  - `src/codegenie/rag/ingest.py` (S4-06) — `_phase4_local_capability_mint`.
  - `tests/cassettes/anthropic/cassettes.lock` (S3-05) — format.
  - `docs/operations/cassettes.md` (S3-06 stub) — extend to final form.

## Goal

Extend `tests/integration/test_phase5_contract_snapshot.py` to capture the five Phase-4 additive interface lines as byte-equal snapshot entries; publish `tests/fixtures/fallback_tier_callable.py` as the Phase-6-LangGraph-lift contract; land `docs/operations/{secrets,cassettes,embeddings}.md` as final runbooks each cross-linking their source ADRs.

## Acceptance criteria

- [ ] `tests/integration/test_phase5_contract_snapshot.py` is **extended** (not rewritten) with these additive captures, each as a separate `assert_signature_unchanged(...)` (or equivalent inspection helper) call:
  - `FallbackTier.run` — full signature including `prior_attempts: list[AttemptSummary] = []` keyword-only.
  - `FallbackTier.on_validated` — `(outcome: PlanOutcome, trust: TrustOutcome) -> None`.
  - `LlmInvocationGuard.running_total` — `() -> BudgetSnapshot`.
  - `FenceWrapper.fence` — `(payload: str, source_kind: SourceKind) -> FencedSegment`.
  - `SolvedExampleWriteCapability` — Pydantic model schema (frozen + extra=forbid + the mint factory signature `_phase4_local_capability_mint(workflow_id, chain_head) -> SolvedExampleWriteCapability`).
  - `cassettes.lock` line format — pin via a golden file `tests/golden/cassettes_lock_format.txt` or equivalent (one example line + a regex of the format).
- [ ] The snapshot test's docstring is updated to name Phase 4 as the source of the additive entries; cite each ADR (0002, 0009, 0010, 0013, 0014).
- [ ] `tests/fixtures/fallback_tier_callable.py` exists and exports a single asyncio-compatible callable named `fallback_tier_callable` whose signature **structurally matches** `FallbackTier.run`. The fixture wires `FallbackTier` with mock collaborators so Phase 6 can lift the callable into a LangGraph node by `node(fn=fallback_tier_callable, ...)` mechanically. Document the wiring in the fixture's module docstring; cite the Phase-6 lift path.
- [ ] `docs/operations/secrets.md` exists with sections:
  - **Anthropic key storage** — `keyring set codegenie anthropic_api_key` (one-liner; cite OS keychains for macOS / Linux SecretService).
  - **Refuse-to-start behavior** — `AnthropicLeafAdapter.__init__` raises on missing key; no env-var fallback (cite ADR-0005, ADR-0006).
  - **Rotation cadence** — quarterly; cite the steward rotation in cassettes.md.
  - **`codegenie auth set`** — the operator command (cross-link to S3-02's CLI; if it doesn't exist yet, document the keyring command as the primary path).
- [ ] `docs/operations/cassettes.md` is **finalized** (S3-06 may have shipped a stub) with sections:
  - **Refresh trigger matrix** — (a) nightly drift job flagging any cassette, (b) Anthropic SDK upgrade, (c) prompt template change in `plugins/.../skills/`; each row names the responsible owner.
  - **`make refresh-cassettes` invocation** — full one-liner with `--i-understand-this-spends-tokens` + `CODEGENIE_LIVE_LLM=1`.
  - **CODEOWNERS approval flow** — the cassette-steward role; rotation cadence; how a new steward is named.
  - **BLAKE3 lock refresh** — `cassettes.lock` discipline; CI scanner naming; how to recompute on cassette change.
  - **Sanitizer guarantees** — what `CassetteSanitizer` strips (cite ADR-0014).
- [ ] `docs/operations/embeddings.md` exists with sections:
  - **`codegenie embeddings bootstrap`** — what it downloads (BGE-small-en-v1.5); content-addressed sha256; the `embeddings_model.lock` file's role.
  - **`codegenie rag rebuild [--reembed]`** — when to run (model drift, corpus restore, sqlite corruption per arch edge case #13).
  - **Refuse-to-start on lock drift** — `FastembedEmbedder.__init__` raises (cite ADR-0007); operator runs `bootstrap` to recover.
  - **Cross-architecture float drift** — acknowledged; the two-threshold band absorbs it (cite ADR-0008).
- [ ] Each docs page has a "See also" section cross-linking the relevant ADRs by file path.
- [ ] All three docs are valid Markdown and pass `make docs` (mkdocs --strict).
- [ ] `tests/integration/test_phase5_contract_snapshot.py` is green; running it under deliberate-violation (e.g., temporarily rename `running_total` to `total`) fails-loud with a diagnostic naming the drifted signature.
- [ ] `make check` clean.
- [ ] TDD red test exists, committed, green.

## Implementation outline

1. **Read first**: open the existing `tests/integration/test_phase5_contract_snapshot.py` (Phase 3 S6-06) to confirm its capture pattern (`inspect.signature(...)`, golden YAML, frozen-model schema dump — whatever Phase 3 used). Mirror that style for the Phase-4 additions (Global Rule 11).
2. Add the five additive captures to the snapshot test. Use the same helper functions if available; otherwise extract a private `_capture(name, obj)` helper and use it consistently.
3. Run the snapshot test; if it fails on first run, decide:
   - **Drift in the captured signature** → check the merge; the snapshot is the source of truth as of Step-7 completion.
   - **Snapshot test scaffolding incompatible** → surgical adjustment to the test (Global Rule 3); do not rewrite.
4. Build `tests/fixtures/fallback_tier_callable.py`:
   - Construct `FallbackTier` with mock collaborators wired against minimal in-memory implementations of each Protocol.
   - Export an `async def fallback_tier_callable(advisory, repo_ctx, recipe_selection, *, prior_attempts=None) -> RecipeApplication` that delegates to `tier.run(...)`.
   - Document the Phase-6 lift contract in the module docstring.
5. Write `docs/operations/secrets.md` from scratch; cite ADR-0005 / ADR-0006 / S3-02.
6. Finalize `docs/operations/cassettes.md` (extend the S3-06 stub or write from scratch if it doesn't exist).
7. Write `docs/operations/embeddings.md` from scratch; cite ADR-0007 / ADR-0008 / S4-01 / S4-07.
8. Add `tests/integration/test_ops_docs_exist.py` — a smoke test that asserts the three docs exist and contain the required sections (`Anthropic key storage`, `Refresh trigger matrix`, `codegenie embeddings bootstrap`, etc.).
9. Run `make docs` to confirm mkdocs --strict accepts the three new pages.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/integration/test_phase5_contract_snapshot_phase4_additions.py
"""Phase-4 additive captures for the Phase-5 contract snapshot.

This file is the *new* assertions; the original snapshot test is extended in place.
"""
from __future__ import annotations
import inspect
from codegenie.fallback.tier import FallbackTier
from codegenie.fallback.budget import LlmInvocationGuard
from codegenie.fallback.fence.wrapper import FenceWrapper
from codegenie.rag.ingest import _phase4_local_capability_mint, SolvedExampleWriteCapability


def _sig(obj) -> str:
    return str(inspect.signature(obj))


def test_fallback_tier_run_signature_pinned():
    expected = (
        "(self, advisory: 'CveAdvisory', repo_ctx: 'RepoContext', "
        "recipe_selection: 'RecipeSelection', *, "
        "prior_attempts: 'list[AttemptSummary]' = []) "
        "-> 'RecipeApplication'"
    )
    assert _sig(FallbackTier.run) == expected


def test_fallback_tier_on_validated_signature_pinned():
    expected = "(self, outcome: 'PlanOutcome', trust: 'TrustOutcome') -> 'None'"
    assert _sig(FallbackTier.on_validated) == expected


def test_llm_invocation_guard_running_total_signature_pinned():
    assert _sig(LlmInvocationGuard.running_total) == "(self) -> 'BudgetSnapshot'"


def test_fence_wrapper_fence_signature_pinned():
    expected = "(self, payload: 'str', source_kind: 'SourceKind') -> 'FencedSegment'"
    assert _sig(FenceWrapper.fence) == expected


def test_solved_example_capability_mint_signature_pinned():
    expected = "(workflow_id: 'WorkflowId', chain_head: 'ChainHead') -> 'SolvedExampleWriteCapability'"
    assert _sig(_phase4_local_capability_mint) == expected


# tests/integration/test_ops_docs_exist.py
from pathlib import Path
import pytest


REQUIRED_DOCS = {
    "docs/operations/secrets.md": ["Anthropic key storage", "Refuse-to-start", "Rotation cadence"],
    "docs/operations/cassettes.md": ["Refresh trigger matrix", "make refresh-cassettes", "CODEOWNERS"],
    "docs/operations/embeddings.md": ["codegenie embeddings bootstrap", "codegenie rag rebuild", "Refuse-to-start"],
}


@pytest.mark.parametrize("path,sections", list(REQUIRED_DOCS.items()))
def test_ops_doc_exists_with_sections(path, sections):
    p = Path(path)
    assert p.is_file(), f"missing ops doc: {p}"
    text = p.read_text()
    for s in sections:
        assert s in text, f"{p} missing section: {s}"


def test_fallback_tier_callable_fixture_published():
    from tests.fixtures import fallback_tier_callable as mod
    assert hasattr(mod, "fallback_tier_callable")
    assert inspect.iscoroutinefunction(mod.fallback_tier_callable)
```

Run: `pytest tests/integration/test_phase5_contract_snapshot_phase4_additions.py tests/integration/test_ops_docs_exist.py -v`. All assertions fail before the new artifacts land.

### Green — make it pass

1. Add the five `_sig`-pinned tests to the contract snapshot file (or extend the original; check the existing pattern first).
2. Build `tests/fixtures/fallback_tier_callable.py`.
3. Write the three ops docs.
4. Iterate until green.

### Refactor — clean up

- If the existing contract snapshot test uses a YAML / JSON golden file rather than `inspect.signature` strings, mirror that pattern instead of the above sketch.
- Cross-link each ops doc from `docs/index.md` (the mkdocs nav) — add a "Operations" section if it doesn't exist.
- Confirm `make docs` clean.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_phase5_contract_snapshot.py` | Extend with Phase-4 additive captures. |
| `tests/integration/test_ops_docs_exist.py` | New smoke test for ops doc structure. |
| `tests/fixtures/fallback_tier_callable.py` | Phase-6 LangGraph lift contract. |
| `docs/operations/secrets.md` | Anthropic key + keyring + refuse-to-start runbook. |
| `docs/operations/cassettes.md` | Cassette refresh + CODEOWNERS + BLAKE3 runbook (finalize). |
| `docs/operations/embeddings.md` | Bootstrap + rebuild + refuse-on-drift runbook. |
| `docs/index.md` (or mkdocs nav) | Add "Operations" section. |

## Out of scope

- Phase 6 LangGraph lift itself (Phase 6 owns it; this story only publishes the contract fixture).
- Adversarial corpus (S7-09).
- E2E tests (S7-06 / S7-07).
- Cassette steward initial assignment (S3-06); this story documents the rotation cadence only.

## Notes for the implementer

- The contract snapshot test is **byte-equal** — `inspect.signature(...)` strings change with Python version (3.11 vs 3.12 may format `list[X] = []` defaults differently). Pin the test's expected strings against the Python version the CI matrix runs (read `pyproject.toml` for the supported versions); if cross-version stability is hard, dump the signature to a golden file and compare files rather than inline strings.
- The `_phase4_local_capability_mint` capture name is intentional — its name is part of the contract (Phase 5 needs to know what to *replace*). If Phase 5 renames it on swap-in, that's a known follow-up in ADR-0009; this snapshot pins the **interim** name explicitly.
- The `fallback_tier_callable.py` fixture must be importable from `tests.fixtures.fallback_tier_callable` — verify the package path / `__init__.py` discipline matches the repo's existing fixture-package structure.
- The three ops docs should be operator-readable in plain language, not engineer-internal. Cross-link ADRs but don't quote them verbatim; the docs are *how to operate*, not *why the design is this shape*.
- `make docs --strict` will fail on broken links and missing referenced files — run early and fix iteratively.
- The "Phase 5 handoff" framing means the consumers of this story's outputs are Phase 5 implementers (who haven't started yet). Write for that audience; document obvious gotchas (e.g., "Phase 5 will replace `_phase4_local_capability_mint` — track the TODO in `src/codegenie/rag/ingest.py`'s docstring").
- Resist scope creep: this story does **not** add `LeafLlm` Protocol or `RetrievalOutcome` to the snapshot — they were already implicitly captured by Phase 3's snapshot infrastructure consuming their imports. If review reveals they're missing, add them (Global Rule 12), but don't include them as primary acceptance criteria unless the existing snapshot test demonstrably doesn't pick them up.
