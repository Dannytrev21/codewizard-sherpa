# Story S2-04 — PromptBuilder as sole `TrustedPrompt` / `FencedPromptBody` mint site

**Step:** Step 2 — Ship trust-boundary primitives: ProvenanceGate, FenceWrapper/CanaryGuard/PromptBuilder, LlmInvocationGuard/BudgetToken
**Status:** HARDENED
**Effort:** S
**Depends on:** S2-02 (`FenceWrapper`, `FencedSegment`, `SourceKind`, `_TRUNCATION_CAPS`); S2-03 (`CanaryGuard` — the production `Scanner` impl)
**ADRs honored:** ADR-0013 (sole minting site + AST-walking enforcement + functional-core/imperative-shell, this phase), ADR-0003 (path-scoped fence), production ADR-0033 (newtype + smart-constructor discipline)

## Validation notes

Validated: 2026-05-21
Verdict: HARDENED
Findings addressed: 19 — 3 blocks, 12 hardens, 4 nits

Changes applied:
- **Newtype location pinned (block).** S1-01 does not ship `TrustedPrompt` / `FencedPromptBody`; this story now defines them in `prompt_builder.py` and removes the stale `identifiers.py` fallback. The AST sole-mint test remains the enforcement mechanism.
- **Event surface corrected (block).** The story used the stale `codegenie.audit.EventLog` / "event-kind allowlist" model. It now uses `codegenie.plugins.events.EventLog.emit_internal`, `EventLog.replay()`, `WorkflowInternalEvent`, `_INTERNAL_CLASSES`, and `tests/unit/plugins/test_events.py`.
- **Multiplicity behavior pinned (block).** `transitive_dep_meta` over 16 truncates to the first 16 and emits `SegmentCountTruncated`; `rag_few_shots` over 3 fails loud with `ValueError` and emits no `PromptAssembled`. No implementer choice remains.
- **Build signature hardened.** Mutable default `rag_few_shots: list[str] = []` replaced with immutable `Sequence[str] = ()`; list-like inputs remain accepted.
- **All untrusted bytes proof strengthened.** AC-7 now asserts a recording/deterministic fence sees the exact `(SourceKind, payload)` sequence and that no raw untrusted payload appears outside a fenced segment.
- **No-bypass structural AC added.** AC-13 AST-walks `prompt_builder.py` to forbid direct delimiter assembly, `FencedSegment(...)`, `Canary*` result construction, direct `CanaryGuard.scan(...)`, or `_TRUNCATION_CAPS` access.
- **Assembly event shape pinned.** `PromptAssembled` and `SegmentCountTruncated` are workflow-internal events with typed shape-only metadata and generated `EventId`s; prompt content and prompt digests remain forbidden here.

Full audit log: docs/phases/04-vuln-llm-fallback-rag/stories/_validation/S2-04-prompt-builder-sole-mint.md

## Context

ADR-0013 §Decision pins the design: **`TrustedPrompt` and `FencedPromptBody` newtypes are minted *only* by `PromptBuilder`** (asserted by an AST-walking test). The type system enforces "every byte reaching the LLM passed through fencing" — `LeafLlm.invoke(system_prompt: TrustedPrompt, user_message: FencedPromptBody, ...)` from S3-01 will type-error if a caller hand-constructs a `str` and tries to pass it. This is the **Newtype + Smart constructor** pattern: the only way to obtain these types is through `PromptBuilder.build(...)`, which composes `FenceWrapper.fence(...)` over every untrusted source.

S2-04 ships:
- The `TrustedPrompt` and `FencedPromptBody` `NewType` aliases in `src/codegenie/fallback/fence/prompt_builder.py`. S1-01 deliberately did not ship these two; keeping them beside their sole smart constructor avoids exporting an easy-to-call constructor from the global identifier catalog.
- `PromptBuilder.build(...)` returning `(TrustedPrompt, FencedPromptBody)`.
- The AST-walking fence test `tests/unit/fallback/test_prompt_builder_sole_mint_site.py` that asserts only `prompt_builder.py` constructs these newtypes.
- The structural guarantee: at LLM call time, `system_prompt` and `user_message` cannot be raw strings.

`PromptBuilder` accepts:
- A trusted `skill` (string — Phase 4 skill template, repo-controlled; not fenced).
- A trusted `instruction_template` (string — Phase 4 instruction template; not fenced).
- Explicit untrusted segment parameters carrying raw text to be fenced (CVE description, repo README, transitive dep meta sequence, source snippets sequence, prior attempt summary, RAG hit sequence, sandbox stderr).

It assembles:
- `system_prompt: TrustedPrompt` = the joined `skill + instruction_template` (trusted, in caller-controlled order).
- `user_message: FencedPromptBody` = the canonical concatenation of `FenceWrapper.fence(...)`-wrapped untrusted segments, in **deterministic order** (matters for prompt caching + replay determinism — S6-07's property test).

The cardinality constraints from ADR-0013's table flow through here: `transitive_dep_meta` segments are capped at 16, `rag_retrieved` at 3. S2-04 enforces them at the builder; `FenceWrapper` itself doesn't know about the multiplicity (per-segment caps live there). Over-cap `transitive_dep_meta` is data-noisy user context and is truncated with a typed audit event; over-cap RAG hits indicate an upstream retriever bug and fail loud.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 3 — FenceWrapper + CanaryGuard` (lines 486-513) — caps table; `transitive_dep_meta` ×16, `rag_retrieved` ×3 multiplicities.
  - `../phase-arch-design.md §Design patterns applied` row 5 (line 880) — newtype + smart-constructor + functional-core/imperative-shell for `TrustedPrompt` / `FencedPromptBody`.
  - `../phase-arch-design.md §Anti-patterns avoided` ("Stringly-typed identifiers") — newtypes for every domain primitive.
  - `../phase-arch-design.md §Decision points` row 4 (line 806) — "PromptBuilder.build — fence-wraps every untrusted byte, canary-scans untruncated then truncates; mints `TrustedPrompt` + `FencedPromptBody` newtypes."
  - `../phase-arch-design.md §FallbackTier sequence diagram` (line 226+) — `PB-->>Tier: TrustedPrompt + FencedPromptBody` arrow.
- **Phase ADRs:**
  - `../ADRs/0013-fence-wrapper-canary-scan-before-truncation.md` — sole minting site rule + AST-walking test + `tests/fence/test_prompt_newtype_minting_bounded.py` mentioned in §Consequences row 6.
- **Source design:**
  - `../final-design.md §Component 3 — FenceWrapper + CanaryGuard` + §"PromptBuilder is the only minting site".
- **Existing code:**
  - `src/codegenie/fallback/fence/wrapper.py` (S2-02) — `FenceWrapper`, `FencedSegment`, `SourceKind`.
  - `src/codegenie/fallback/fence/canary.py` (S2-03) — `CanaryGuard` for `Scanner` injection.
  - `src/codegenie/plugins/events.py` — **the** event-sourcing surface. `EventLog(root, workflow_id)`, `emit_internal(...)`, `replay()`, `WorkflowInternalEvent`, `_INTERNAL_CLASSES`, and `__all__`. There is no `EventLog` in `src/codegenie/audit.py`.
  - `tests/unit/plugins/test_events.py` — adjacent event-union tests; extend this for `PromptAssembled` and `SegmentCountTruncated`.
  - `docs/phases/04-vuln-llm-fallback-rag/stories/S1-01-newtype-smart-constructor-substrate.md` — confirms S1-01 ships `HexNonce`, `BudgetTokenId`, etc., but **not** `TrustedPrompt` / `FencedPromptBody`.
  - `src/codegenie/probes/` — existing AST-walking test patterns (e.g., functional-core enforcement tests in Phase 2 probes) — mirror the convention.
  - `tests/fence/` — Phase 0/1/2 fence-test conventions to mirror for the AST-walk test placement.

## Goal

Ship `PromptBuilder.build(skill, instruction_template, untrusted_segments) -> tuple[TrustedPrompt, FencedPromptBody]` as the **sole minting site** for these two newtypes, with an AST-walking test that scans every `.py` file under `src/codegenie/` and asserts only `src/codegenie/fallback/fence/prompt_builder.py` constructs `TrustedPrompt(...)` or `FencedPromptBody(...)`.

## Acceptance criteria

- [ ] **AC-1 — Module location.** `src/codegenie/fallback/fence/prompt_builder.py` exists.
- [ ] **AC-2 — `TrustedPrompt` and `FencedPromptBody` newtypes.** Both are `NewType("...", str)` and live in `src/codegenie/fallback/fence/prompt_builder.py`. Do **not** add them to `src/codegenie/types/identifiers.py` in this story: S1-01 did not ship them, and exporting the constructors from the global identifier catalog weakens the "constructor lives beside the sole smart constructor" discipline. The public type import for S3-01's `LeafLlm` is `from codegenie.fallback.fence.prompt_builder import TrustedPrompt, FencedPromptBody`; AC-3 enforces the call-site rule.
- [ ] **AC-3 — AST-walking sole-mint test.** `tests/unit/fallback/test_prompt_builder_sole_mint_site.py` walks every `.py` under `src/codegenie/` using `ast.parse(...)`, looking for any `Call` node whose `func` resolves (textually or via imports) to `TrustedPrompt` or `FencedPromptBody`. It first asserts `_ALLOWED_MINTER.exists()` so an empty walk cannot pass before the module exists. It asserts the **only** module containing such calls is `src/codegenie/fallback/fence/prompt_builder.py`. Test includes a deliberate-failure positive control: a fixture under `tests/fixtures/violators/` containing `TrustedPrompt("forged")` confirms the AST walk would catch a violation (the violator path is excluded from the production scan by file-path filter so it doesn't fail the test; the positive-control test imports the violator's path and asserts the AST walk on that file *would* fire).
- [ ] **AC-4 — `PromptBuilder.build` signature + multiplicity policy.** `@dataclass(frozen=True, slots=True) class PromptBuilder` with fields `fence: FenceWrapper`, `event_log: EventLog` (this is `codegenie.plugins.events.EventLog`, not `codegenie.audit.EventLog`). Method:
   ```python
   from collections.abc import Sequence

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
   ) -> tuple[TrustedPrompt, FencedPromptBody]: ...
   ```
   All untrusted segments flow through `self.fence.fence(payload, source_kind=...)`. **Multiplicity caps** are deterministic, not implementer-choice:
   - `transitive_dep_meta`: if `len(transitive_dep_meta) > 16`, keep the first 16 in caller order, emit exactly one `SegmentCountTruncated(source_kind="transitive_dep_meta", requested=<original count>, kept=16)` workflow-internal event, and continue. Test asserts exactly 16 `transitive_dep_meta` fence calls and one truncation event.
   - `rag_few_shots`: if `len(rag_few_shots) > 3`, raise `ValueError(f"rag_few_shots capped at 3, got {len(rag_few_shots)}")`, emit no `PromptAssembled`, and make no fence calls after detecting the violation. The retriever owns returning at most three examples; over-cap here is a programming error.
- [ ] **AC-5 — Deterministic assembly order.** Untrusted segments are concatenated in this exact order: `cve_description`, `repo_readme`, each `transitive_dep_meta` item in input order after AC-4 truncation, each `source_snippets` item in input order, each `rag_few_shots` item in input order using `source_kind="rag_retrieved"`, `prior_attempt_summary` if not `None`, then `sandbox_stderr` if not `None`. Order documented in the module docstring. Test: with deterministic nonces, the same inputs produce byte-identical `FencedPromptBody` and a `PromptAssembled.source_kinds_used` tuple equal to the exact `SourceKind` sequence above. (S6-07's determinism property relies on this.)
- [ ] **AC-6 — `TrustedPrompt` content.** `system_prompt: TrustedPrompt = TrustedPrompt(skill + "\n\n" + instruction_template)`. Both inputs are caller-trusted (Phase-4 repo-controlled skill + instruction-template strings). No fencing applied. Test asserts the returned `TrustedPrompt` value equals the expected concatenation.
- [ ] **AC-7 — `FencedPromptBody` content and all-untrusted-through-fence proof.** The body is the concatenation of `FencedSegment.content` (which already includes open + body + close delimiters) for each fenced segment, in the deterministic order from AC-5. Test with short unique payloads and deterministic nonces asserts: (i) every untrusted payload appears only inside a returned `FencedSegment.content`, never raw outside delimiters; (ii) the body is exactly `"".join(segment.content for segment in recorded_segments)`; (iii) the recording fence saw the exact `(SourceKind, payload)` sequence from AC-5; (iv) every open delimiter and close delimiter appears exactly once for its nonce; (v) no two segments share a nonce (each `fence.fence(...)` call mints a fresh nonce per S2-02's `nonce_source`). A lazy implementation that concatenates `repo_readme` or `rag_few_shots` directly into the body must fail this test.
- [ ] **AC-8 — Empty optional segments.** If `prior_attempt_summary is None`, the body omits the prior-attempt segment entirely (no empty delimiter pair). Same for `sandbox_stderr`, empty `rag_few_shots`, empty `transitive_dep_meta`, empty `source_snippets`. Test asserts the body for an all-optional-empty case has only `cve_description` + `repo_readme` fenced segments.
- [ ] **AC-9 — `PromptBuilder` does NOT accept a `BudgetToken`.** Cross-cutting reminder: capability flows through exactly two frames (`FallbackTier → LeafLlm.invoke`). `PromptBuilder.build`'s signature must not reference `BudgetToken`. Test inspects `inspect.signature(PromptBuilder.build).parameters` and asserts `"token"` and `"budget_token"` are NOT among them.
- [ ] **AC-10 — Audit event on assembly.** `PromptBuilder.build` emits one `PromptAssembled` workflow-internal event via `self.event_log.emit_internal(...)` after successful assembly. Shape: `model_config = ConfigDict(frozen=True, extra="forbid")`, `event_type: Literal["prompt_assembled"] = "prompt_assembled"`, `event_id: EventId`, `workflow_id: WorkflowId`, `timestamp: datetime`, `segment_count: int`, `source_kinds_used: tuple[SourceKind, ...]`, `system_prompt_byte_length: int`, `fenced_body_byte_length: int`. Event payload does **NOT** include the prompt content or any digest of it (S6-01 owns prompt-digest emission to event log via `LeafInvoked(prompt_digest_blake3)` per arch §Component 4). Test asserts exactly one such event fires per successful `build()` call and reads it via `EventLog.replay()`.
- [ ] **AC-11 — Event-kind registration cannot drift.** `PromptAssembled` and `SegmentCountTruncated` are `WorkflowInternalEvent` variants in `src/codegenie/plugins/events.py`. Wire both into the `WorkflowInternalEvent` discriminated union, `_INTERNAL_CLASSES`, and `__all__`; keep them internal, not spanning, and give them no `prev_hash`. `tests/unit/plugins/test_events.py` asserts both event-type strings appear in `TypeAdapter(WorkflowInternalEvent).json_schema()["discriminator"]["mapping"]` and that both classes construct + round-trip with typed payload fields. There is no audit allowlist and no `tests/fence/test_event_kinds_complete.py` in the current codebase.
- [ ] **AC-12 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean.
- [ ] **AC-13 — No fence bypass inside `prompt_builder.py`.** `tests/unit/fallback/test_prompt_builder_no_fence_bypass.py` AST-walks `src/codegenie/fallback/fence/prompt_builder.py` and fails if the module directly constructs `FencedSegment`, `CanaryClean`, or `CanaryCollision`; imports or calls `CanaryGuard.scan`, `scan_pure`, `fence_pure`, or `_TRUNCATION_CAPS`; or contains the delimiter literals `<UNTRUSTED_INPUT` / `</UNTRUSTED_INPUT`. `PromptBuilder` may call only `self.fence.fence(...)` for untrusted payloads. This is the structural guard that keeps the builder a composition shell over S2-02/S2-03 rather than a second fence implementation.

## Implementation outline

1. **Pre-check dependencies**: S2-02 has shipped `FenceWrapper`, `FencedSegment`, `SourceKind`, `FenceApplied` / `CanaryCollision` events, and deterministic `nonce_source`; S2-03 has shipped `CanaryGuard`. S1-01 has **not** shipped `TrustedPrompt` / `FencedPromptBody`; this story defines them locally in `prompt_builder.py`.
2. **Create `prompt_builder.py`** with `TrustedPrompt`, `FencedPromptBody`, `PromptBuilder`, `_new_event_id() -> EventId`, and a tiny `_iter_segments(...) -> tuple[tuple[SourceKind, str], ...]` pure helper that applies AC-4/AC-5 ordering and multiplicity rules.
3. **Implement `build`** as a short composition shell — derive the trusted system prompt, derive ordered untrusted `(source_kind, payload)` pairs, call `self.fence.fence(...)` once per pair, concatenate `FencedSegment.content`, mint `FencedPromptBody`, emit `PromptAssembled`, return the pair. Do not import or construct `FencedSegment` / `Canary*` / delimiter literals here.
4. **Handle multiplicity before fencing** — over-cap `rag_few_shots` raises before any fence calls; over-cap `transitive_dep_meta` truncates to first 16 and emits `SegmentCountTruncated` before the `PromptAssembled`.
5. **Add events to `plugins/events.py`** — `PromptAssembled` and `SegmentCountTruncated` workflow-internal Pydantic classes, union registration, `_INTERNAL_CLASSES`, `__all__`, plus `tests/unit/plugins/test_events.py` coverage.
6. **Write the AST-walking tests** — the sole-mint test (AC-3) and no-bypass test (AC-13). The sole-mint visitor resolves direct calls and import aliases; it asserts `_ALLOWED_MINTER.exists()` before scanning. The no-bypass visitor rejects delimiter literals and direct fence/canary constructions.
7. **Build the positive-control fixture** under `tests/fixtures/violators/forged_prompt_mint.py` containing `TrustedPrompt("evil")`. The test parses it and asserts the visitor *would* flag it.
8. Run `make check`.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/fallback/test_prompt_builder_sole_mint_site.py
from __future__ import annotations

import ast
from pathlib import Path

import pytest


_SRC_ROOT = Path("src/codegenie")
_ALLOWED_MINTER = _SRC_ROOT / "fallback" / "fence" / "prompt_builder.py"
_FORBIDDEN_NEWTYPES = {"TrustedPrompt", "FencedPromptBody"}


def _calls_to_newtype(tree: ast.AST, names: set[str]) -> list[tuple[str, int]]:
    hits: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in names:
                hits.append((node.func.id, node.lineno))
    return hits


def test_only_prompt_builder_mints_trusted_prompt_and_fenced_body() -> None:
    assert _ALLOWED_MINTER.exists(), "PromptBuilder module must exist before the scan runs."
    violations: list[tuple[Path, str, int]] = []
    for py in _SRC_ROOT.rglob("*.py"):
        if py == _ALLOWED_MINTER:
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for name, lineno in _calls_to_newtype(tree, _FORBIDDEN_NEWTYPES):
            violations.append((py, name, lineno))
    assert violations == [], (
        f"Found {len(violations)} forbidden mint sites — "
        f"only {_ALLOWED_MINTER} may construct TrustedPrompt / FencedPromptBody.\n"
        + "\n".join(f"  {p}:{ln} -> {n}(...)" for p, n, ln in violations)
    )


def test_positive_control_forged_minter_is_caught_by_visitor() -> None:
    """If we forged a minter under tests/fixtures/violators/, the visitor catches it."""
    forged = Path("tests/fixtures/violators/forged_prompt_mint.py")
    assert forged.exists(), "Positive-control fixture must exist."
    tree = ast.parse(forged.read_text(encoding="utf-8"))
    hits = _calls_to_newtype(tree, _FORBIDDEN_NEWTYPES)
    assert len(hits) >= 1, (
        "Positive control failed: visitor did not flag a deliberate violator. "
        "If this passes, the AST walk is broken."
    )
```

```python
# tests/unit/fallback/test_prompt_builder.py
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from codegenie.fallback.fence.canary import CanaryGuard
from codegenie.fallback.fence.prompt_builder import (
    FencedPromptBody,
    PromptBuilder,
    TrustedPrompt,
)
from codegenie.fallback.fence.wrapper import FenceWrapper
from codegenie.plugins.events import EventLog, PromptAssembled, SegmentCountTruncated
from codegenie.types.identifiers import HexNonce, WorkflowId


def _make_builder(tmp_path: Path) -> tuple[PromptBuilder, EventLog]:
    log = EventLog(root=tmp_path, workflow_id=WorkflowId("01HPRB000000000000000000"))
    nonces = iter([HexNonce(f"{i:032x}") for i in range(100)])
    fence = FenceWrapper(scanner=CanaryGuard(), event_log=log, nonce_source=lambda: next(nonces))
    return PromptBuilder(fence=fence, event_log=log), log


# AC-6
def test_trusted_prompt_is_skill_plus_instruction(tmp_path: Path) -> None:
    builder, _ = _make_builder(tmp_path)
    system, _ = builder.build(
        skill="SKILL",
        instruction_template="INSTRUCTIONS",
        cve_description="CVE-2026-0001",
        repo_readme="readme",
        transitive_dep_meta=[],
        source_snippets=[],
    )
    assert isinstance(system, str)  # NewType erases at runtime
    assert system == "SKILL\n\nINSTRUCTIONS"


# AC-9 — capability does not flow here
def test_build_signature_excludes_budget_token() -> None:
    sig = inspect.signature(PromptBuilder.build)
    params = set(sig.parameters)
    assert "token" not in params
    assert "budget_token" not in params


# AC-4 — multiplicity cap, chosen behavior pinned
def test_transitive_dep_meta_over_16_truncates_with_event(tmp_path: Path) -> None:
    builder, log = _make_builder(tmp_path)
    overflow = [f"dep-{i}" for i in range(20)]
    _, body = builder.build(
        skill="S",
        instruction_template="I",
        cve_description="CVE",
        repo_readme="R",
        transitive_dep_meta=overflow,
        source_snippets=[],
    )
    assert "dep-15" in body
    assert "dep-16" not in body
    truncations = [e for e in log.replay() if isinstance(e, SegmentCountTruncated)]
    assert len(truncations) == 1
    assert truncations[0].source_kind == "transitive_dep_meta"
    assert truncations[0].requested == 20
    assert truncations[0].kept == 16


def test_rag_few_shots_over_3_raises_before_fencing(tmp_path: Path) -> None:
    builder, log = _make_builder(tmp_path)
    with pytest.raises(ValueError, match="rag_few_shots capped at 3, got 4"):
        builder.build(
            skill="S",
            instruction_template="I",
            cve_description="CVE",
            repo_readme="R",
            transitive_dep_meta=[],
            source_snippets=[],
            rag_few_shots=["a", "b", "c", "d"],
        )
    assert not any(isinstance(e, PromptAssembled) for e in log.replay())


# AC-5 — deterministic order
def test_same_inputs_produce_byte_identical_body(tmp_path: Path) -> None:
    # Fixed nonce factory so the fence's random nonces don't differ across runs
    nonces = iter([HexNonce(f"{i:032x}") for i in range(100)])
    log_a = EventLog(root=tmp_path / "a", workflow_id=WorkflowId("01HPRBA00000000000000000"))
    builder = PromptBuilder(
        fence=FenceWrapper(
            scanner=CanaryGuard(),
            event_log=log_a,
            nonce_source=lambda: next(nonces),
        ),
        event_log=log_a,
    )
    _, body_a = builder.build(
        skill="S",
        instruction_template="I",
        cve_description="CVE",
        repo_readme="R",
        transitive_dep_meta=["a", "b"],
        source_snippets=["src1"],
    )
    nonces2 = iter([HexNonce(f"{i:032x}") for i in range(100)])
    log_b = EventLog(root=tmp_path / "b", workflow_id=WorkflowId("01HPRBB00000000000000000"))
    builder2 = PromptBuilder(
        fence=FenceWrapper(
            scanner=CanaryGuard(),
            event_log=log_b,
            nonce_source=lambda: next(nonces2),
        ),
        event_log=log_b,
    )
    _, body_b = builder2.build(
        skill="S",
        instruction_template="I",
        cve_description="CVE",
        repo_readme="R",
        transitive_dep_meta=["a", "b"],
        source_snippets=["src1"],
    )
    assert body_a == body_b
    assembled = [e for e in log_a.replay() if isinstance(e, PromptAssembled)]
    assert assembled[0].source_kinds_used == (
        "cve_description",
        "repo_readme",
        "transitive_dep_meta",
        "transitive_dep_meta",
        "source_snippet",
    )
```

Run; expect `ModuleNotFoundError` and AST-walk test failure (likely fail-loudly because `prompt_builder.py` doesn't exist; first `walks` is empty so passes trivially — guard the walk by asserting `_ALLOWED_MINTER.exists()`).

### Green — make it pass

Implement `prompt_builder.py` per AC-4. Add the positive-control fixture file (`tests/fixtures/violators/forged_prompt_mint.py` with one-line `_ = TrustedPrompt("evil")` and a leading `# This file is a deliberate test fixture; not imported by production code.` comment).

### Refactor — clean up

- The `build()` body becomes a short list comprehension over `(source_kind, payload)` pairs — readable; resist refactoring into a Visitor pattern (ADR-0013 §Design patterns row 5: "Not Visitor over PromptSegment + Builder cascade — readable explicit calls beat pattern soup").
- Module docstring documents the deterministic assembly order, multiplicity caps, and the "sole mint site" invariant with a link to ADR-0013.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/fence/prompt_builder.py` | `TrustedPrompt`, `FencedPromptBody`, `PromptBuilder`, `_iter_segments`, `_new_event_id`. |
| `src/codegenie/plugins/events.py` | **MODIFY** — add `PromptAssembled` + `SegmentCountTruncated` `WorkflowInternalEvent` classes; wire each into the union, `_INTERNAL_CLASSES`, and `__all__`. |
| `tests/unit/fallback/test_prompt_builder.py` | AC-4..AC-10, including ordering, multiplicity, and event assertions through `EventLog.replay()`. |
| `tests/unit/fallback/test_prompt_builder_sole_mint_site.py` | AC-3 AST-walk + positive control. |
| `tests/unit/fallback/test_prompt_builder_no_fence_bypass.py` | AC-13 AST-walk forbidding direct delimiter / fence / canary bypasses. |
| `tests/fixtures/violators/__init__.py` | Empty (package marker). |
| `tests/fixtures/violators/forged_prompt_mint.py` | Positive-control fixture. |
| `tests/unit/plugins/test_events.py` | Event-union membership and typed construction for `PromptAssembled` / `SegmentCountTruncated`. |

## Out of scope

- Wiring `PromptBuilder` into `FallbackTier.run` — owned by S6-01.
- Per-source-kind pattern subsetting (e.g., `cve_description` gets a different injection corpus than `source_snippet`) — Phase 7+ if evidence supports.
- Skill / instruction-template loading from disk — owned by S7-04 (`plugin.yaml` + skill markdown).
- Streaming / incremental prompt assembly — single-pass batch build only.
- Anthropic-specific message-list shape (`messages: [{role: "user", content: "..."}, ...]`) — `LeafLlm.invoke` (S3-01 / S3-02) projects `(TrustedPrompt, FencedPromptBody)` into the SDK's shape; this story produces the typed pair only.

## Notes for the implementer

- **Cross-cutting reminder #1 — `BudgetToken` does NOT flow through `PromptBuilder`.** ADR-0010 §Pattern fit pins the two-frame rule: `FallbackTier → LeafLlm.invoke`. AC-9's signature check is the structural guard. If a future story wants prompt-token-counting before precharge, that counting happens inside `LlmInvocationGuard.precharge(requested_tokens=...)` with the count computed in `FallbackTier.run` (potentially via `PromptBuilder` returning a `byte_length` projection, but NOT via threading a `BudgetToken`).
- **Cross-cutting reminder #2 — UNTRUNCATED scan, then truncate.** `PromptBuilder` does not perform truncation itself; it delegates to `FenceWrapper.fence`, which per S2-02 calls `scan_pure` on the untruncated bytes then truncates. This story relies on that contract; do not bypass `fence` by directly building delimited strings.
- **Cross-cutting reminder #3 — Newtypes.** `TrustedPrompt` and `FencedPromptBody` are `NewType(str)`; they erase at runtime but `mypy --strict` enforces. A caller `LeafLlm.invoke(system_prompt="hello", ...)` will type-error.
- **AST-walking caveat.** The visitor in AC-3's test catches direct `TrustedPrompt(...)` calls but **not** reflective constructions like `globals()["TrustedPrompt"]("evil")` or `getattr(module, "TrustedPrompt")("evil")`. These are out of scope for this story's structural guard — the codebase's `forbidden-patterns` pre-commit hook (Phase-0) already bans `eval(`, `exec(`, `__import__(`. Document this limitation in the test's module docstring.
- **The `transitive_dep_meta` ×16 / `rag_few_shots` ×3 multiplicity caps.** The behavior is pinned, not implementer-choice: truncate `transitive_dep_meta` to 16 with `SegmentCountTruncated`, and fail loud on `rag_few_shots > 3`. Large CVEs may legitimately have 20+ transitive deps; truncating that noisy list is budget-honoring. A retriever returning more than three examples violates its own contract, so `PromptBuilder` should reject it before fencing.
- **Determinism is load-bearing for replay.** S6-07's `test_determinism_under_cassette_replay.py` (50-run byte-identical property) requires `PromptBuilder.build` to be deterministic given the same inputs — the only source of nondeterminism is `nonce_source` in `FenceWrapper`. Test fixtures inject a deterministic nonce factory; production uses `secrets.token_hex(16)`. AC-5's test pins this with deterministic nonces.
- **`PromptAssembled` event content.** AC-10 explicitly forbids the event payload from containing the prompt content or any digest of it — that's `LeafInvoked`'s job in S6-01. `PromptAssembled` carries shape-only metadata.
- **Event log — `codegenie.plugins.events.EventLog`, not `audit.py`.** The repo has two unrelated audit surfaces. `src/codegenie/audit.py` is the Phase-0 gather-pipeline run writer and has no `EventLog`. Add `PromptAssembled` / `SegmentCountTruncated` to `src/codegenie/plugins/events.py`, emit through `emit_internal`, and assert through `replay()`.
- **Module placement of newtypes.** S1-01 did not ship `TrustedPrompt` / `FencedPromptBody`. Define them in `prompt_builder.py` for this story. Do not add them to `identifiers.py` unless a future ADR explicitly decides to centralize prompt newtypes and accepts the extra constructor-exposure risk.
- **No second fence implementation.** `PromptBuilder` is a composer, not a fence. It must never assemble `<UNTRUSTED_INPUT ...>` delimiters or call canary/truncation helpers directly. AC-13 exists because duplicating any part of S2-02/S2-03 would break the functional-core/imperative-shell split and make future fence changes non-local.
