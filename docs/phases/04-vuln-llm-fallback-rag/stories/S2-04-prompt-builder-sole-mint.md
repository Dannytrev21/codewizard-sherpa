# Story S2-04 — PromptBuilder as sole `TrustedPrompt` / `FencedPromptBody` mint site

**Step:** Step 2 — Ship trust-boundary primitives: ProvenanceGate, FenceWrapper/CanaryGuard/PromptBuilder, LlmInvocationGuard/BudgetToken
**Status:** Ready
**Effort:** S
**Depends on:** S2-02 (`FenceWrapper`, `FencedSegment`, `SourceKind`, `_TRUNCATION_CAPS`); S2-03 (`CanaryGuard` — the production `Scanner` impl)
**ADRs honored:** ADR-0013 (sole minting site + AST-walking enforcement + functional-core/imperative-shell, this phase), ADR-0003 (path-scoped fence), production ADR-0033 (newtype + smart-constructor discipline)

## Context

ADR-0013 §Decision pins the design: **`TrustedPrompt` and `FencedPromptBody` newtypes are minted *only* by `PromptBuilder`** (asserted by an AST-walking test). The type system enforces "every byte reaching the LLM passed through fencing" — `LeafLlm.invoke(system_prompt: TrustedPrompt, user_message: FencedPromptBody, ...)` from S3-01 will type-error if a caller hand-constructs a `str` and tries to pass it. This is the **Newtype + Smart constructor** pattern: the only way to obtain these types is through `PromptBuilder.build(...)`, which composes `FenceWrapper.fence(...)` over every untrusted source.

S2-04 ships:
- The `TrustedPrompt` and `FencedPromptBody` `NewType` aliases (if S1-01 didn't already — pre-check).
- `PromptBuilder.build(...)` returning `(TrustedPrompt, FencedPromptBody)`.
- The AST-walking fence test `tests/unit/fallback/test_prompt_builder_sole_mint_site.py` that asserts only `prompt_builder.py` constructs these newtypes.
- The structural guarantee: at LLM call time, `system_prompt` and `user_message` cannot be raw strings.

`PromptBuilder` accepts:
- A trusted `skill` (string — Phase 4 skill template, repo-controlled; not fenced).
- A trusted `instruction_template` (string — Phase 4 instruction template; not fenced).
- A dict of untrusted segments keyed by `SourceKind` carrying the raw bytes to be fenced (CVE description, repo README, transitive dep meta list, source snippets list, prior attempt summary, RAG hits list).

It assembles:
- `system_prompt: TrustedPrompt` = the joined `skill + instruction_template` (trusted, in caller-controlled order).
- `user_message: FencedPromptBody` = the canonical concatenation of `FenceWrapper.fence(...)`-wrapped untrusted segments, in **deterministic order** (matters for prompt caching + replay determinism — S6-07's property test).

The cardinality constraints from ADR-0013's table flow through here: `transitive_dep_meta` segments are capped at 16, `rag_retrieved` at 3. S2-04 enforces them at the builder; `FenceWrapper` itself doesn't know about the multiplicity (per-segment caps live there).

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
  - `src/codegenie/probes/` — existing AST-walking test patterns (e.g., functional-core enforcement tests in Phase 2 probes) — mirror the convention.
  - `tests/fence/` — Phase 0/1/2 fence-test conventions to mirror for the AST-walk test placement.

## Goal

Ship `PromptBuilder.build(skill, instruction_template, untrusted_segments) -> tuple[TrustedPrompt, FencedPromptBody]` as the **sole minting site** for these two newtypes, with an AST-walking test that scans every `.py` file under `src/codegenie/` and asserts only `src/codegenie/fallback/fence/prompt_builder.py` constructs `TrustedPrompt(...)` or `FencedPromptBody(...)`.

## Acceptance criteria

- [ ] **AC-1 — Module location.** `src/codegenie/fallback/fence/prompt_builder.py` exists.
- [ ] **AC-2 — `TrustedPrompt` and `FencedPromptBody` newtypes.** Both are `NewType("...", str)`. They live in `src/codegenie/fallback/fence/prompt_builder.py` (or `src/codegenie/types/identifiers.py` extended in S1-01 — pre-check; if S1-01 already shipped them, this story imports). If they live in `prompt_builder.py` itself, that placement **is** the structural minting guarantee (importing the constructor inherently scopes it). Either way, AC-3 below enforces the AST-walk constraint.
- [ ] **AC-3 — AST-walking sole-mint test.** `tests/unit/fallback/test_prompt_builder_sole_mint_site.py` walks every `.py` under `src/codegenie/` using `ast.parse(...)`, looking for any `Call` node whose `func` resolves (textually or via imports) to `TrustedPrompt` or `FencedPromptBody`. Asserts the **only** module containing such calls is `src/codegenie/fallback/fence/prompt_builder.py`. Test includes a deliberate-failure positive control: a fixture under `tests/fixtures/violators/` containing `TrustedPrompt("forged")` confirms the AST walk would catch a violation (the violator path is excluded from the production scan by file-path filter so it doesn't fail the test; the positive-control test imports the violator's path and asserts the AST walk on that file *would* fire).
- [ ] **AC-4 — `PromptBuilder.build` signature.** `@dataclass(frozen=True, slots=True) class PromptBuilder` with fields `fence: FenceWrapper`, `event_log: EventLog`. Method:
   ```python
   def build(
       self,
       *,
       skill: str,
       instruction_template: str,
       cve_description: str,
       repo_readme: str,
       transitive_dep_meta: list[str],
       source_snippets: list[str],
       prior_attempt_summary: str | None = None,
       rag_few_shots: list[str] = [],
       sandbox_stderr: str | None = None,
   ) -> tuple[TrustedPrompt, FencedPromptBody]: ...
   ```
   All untrusted segments flow through `self.fence.fence(payload, source_kind=...)`. **Multiplicity caps** enforced inside `build`: `len(transitive_dep_meta) <= 16` and `len(rag_few_shots) <= 3` — raise `ValueError(f"transitive_dep_meta capped at 16, got {len(...)}")` if violated (or truncate the list with a `SegmentCountTruncated(source_kind, requested, kept)` audit event — implementer's choice between hard-reject vs truncate-with-event; ADR-0013 implies truncate-with-event is the friendlier UX since callers may legitimately have 20 transitive deps in a CVE, only the first 16 fit budget; document the choice).
- [ ] **AC-5 — Deterministic assembly order.** Untrusted segments are concatenated in a fixed, documented order (e.g., `cve_description, repo_readme, transitive_dep_meta..., source_snippets..., rag_few_shots..., prior_attempt_summary, sandbox_stderr`). Order documented in module docstring. Test: same inputs → byte-identical `FencedPromptBody`. (S6-07's determinism property relies on this.)
- [ ] **AC-6 — `TrustedPrompt` content.** `system_prompt: TrustedPrompt = TrustedPrompt(skill + "\n\n" + instruction_template)`. Both inputs are caller-trusted (Phase-4 repo-controlled skill + instruction-template strings). No fencing applied. Test asserts the returned `TrustedPrompt` value equals the expected concatenation.
- [ ] **AC-7 — `FencedPromptBody` content.** The body is the concatenation of `FencedSegment.content` (which already includes open + body + close delimiters) for each fenced segment, in the deterministic order from AC-5. Test asserts: (i) every untrusted-segment's open-delimiter appears exactly once, (ii) every close-delimiter appears exactly once, (iii) no two segments share a nonce (each `fence.fence(...)` call mints a fresh nonce per S2-02's `nonce_source`).
- [ ] **AC-8 — Empty optional segments.** If `prior_attempt_summary is None`, the body omits the prior-attempt segment entirely (no empty delimiter pair). Same for `sandbox_stderr`, empty `rag_few_shots`, empty `transitive_dep_meta`, empty `source_snippets`. Test asserts the body for an all-optional-empty case has only `cve_description` + `repo_readme` fenced segments.
- [ ] **AC-9 — `PromptBuilder` does NOT accept a `BudgetToken`.** Cross-cutting reminder: capability flows through exactly two frames (`FallbackTier → LeafLlm.invoke`). `PromptBuilder.build`'s signature must not reference `BudgetToken`. Test inspects `inspect.signature(PromptBuilder.build).parameters` and asserts `"token"` and `"budget_token"` are NOT among them.
- [ ] **AC-10 — Audit event on assembly.** `PromptBuilder.build` emits one `PromptAssembled(segment_count: int, source_kinds_used: tuple[SourceKind, ...], system_prompt_byte_length: int, fenced_body_byte_length: int)` event — operator-portal-visible audit trail. Event payload does **NOT** include the prompt content or any digest of it (S6-01 owns prompt-digest emission to event log via `LeafInvoked(prompt_digest_blake3)` per arch §Component 4). Test asserts exactly one such event fires per `build()` call.
- [ ] **AC-11 — Event-kind registered.** `PromptAssembled` (and `SegmentCountTruncated` if AC-4's implementer chose the truncate-with-event variant) registered in the audit allowlist.
- [ ] **AC-12 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean.

## Implementation outline

1. **Pre-check Step-1**: do `TrustedPrompt` / `FencedPromptBody` live in `src/codegenie/types/identifiers.py` already? S1-01 listed both — they should be there. Import.
2. **Create `prompt_builder.py`** with `PromptBuilder` dataclass + `build` method.
3. **Implement `build`** as a straightforward call chain — fence each non-None untrusted segment, concatenate. The method is short (~40 lines).
4. **Write the AST-walking test** — leverage `ast.walk(tree)` filtering `ast.Call` nodes whose `func` is `ast.Name(id="TrustedPrompt")` or `ast.Name(id="FencedPromptBody")`. Walk all `.py` files under `src/codegenie/` via `pathlib.Path.rglob("*.py")`. Whitelist `prompt_builder.py`. The test is similar in spirit to Phase-0's `tests/unit/test_pyproject_fence.py` AST walk.
5. **Build the positive-control fixture** under `tests/fixtures/violators/forged_prompt_mint.py` containing `TrustedPrompt("evil")`. The test imports the path, parses it, runs the same AST visitor, and asserts the visitor *would* flag it.
6. Register events.
7. Run `make check`.

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

from codegenie.audit import EventLog
from codegenie.fallback.fence.canary import CanaryGuard
from codegenie.fallback.fence.prompt_builder import (
    FencedPromptBody,
    PromptBuilder,
    TrustedPrompt,
)
from codegenie.fallback.fence.wrapper import FenceWrapper


def _make_builder() -> tuple[PromptBuilder, EventLog]:
    log = EventLog()
    fence = FenceWrapper(scanner=CanaryGuard(), event_log=log)
    return PromptBuilder(fence=fence, event_log=log), log


# AC-6
def test_trusted_prompt_is_skill_plus_instruction() -> None:
    builder, _ = _make_builder()
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


# AC-4 — multiplicity cap
def test_transitive_dep_meta_over_16_raises_or_truncates() -> None:
    builder, log = _make_builder()
    overflow = [f"dep-{i}" for i in range(20)]
    # Implementer chooses raise OR truncate-with-event; assert ONE of:
    # ... (test body picks the chosen branch and asserts it)


# AC-5 — deterministic order
def test_same_inputs_produce_byte_identical_body() -> None:
    builder, _ = _make_builder()
    # Fixed nonce factory so the fence's random nonces don't differ across runs
    from codegenie.types.identifiers import HexNonce
    nonces = iter([HexNonce(f"{i:032x}") for i in range(100)])
    builder = PromptBuilder(
        fence=FenceWrapper(
            scanner=CanaryGuard(),
            event_log=EventLog(),
            nonce_source=lambda: next(nonces),
        ),
        event_log=EventLog(),
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
    builder2 = PromptBuilder(
        fence=FenceWrapper(
            scanner=CanaryGuard(),
            event_log=EventLog(),
            nonce_source=lambda: next(nonces2),
        ),
        event_log=EventLog(),
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
| `src/codegenie/fallback/fence/prompt_builder.py` | `PromptBuilder` class + (possibly) `TrustedPrompt` / `FencedPromptBody` newtypes. |
| `src/codegenie/types/identifiers.py` | If S1-01 didn't add the newtypes, add them here so the canonical Newtype catalog stays one file (Global Rule 11). |
| `src/codegenie/audit.py` | Register `PromptAssembled` + (optionally) `SegmentCountTruncated` event kinds. |
| `tests/unit/fallback/test_prompt_builder.py` | AC-4..AC-10. |
| `tests/unit/fallback/test_prompt_builder_sole_mint_site.py` | AC-3 AST-walk + positive control. |
| `tests/fixtures/violators/__init__.py` | Empty (package marker). |
| `tests/fixtures/violators/forged_prompt_mint.py` | Positive-control fixture. |
| `tests/fence/test_event_kinds_complete.py` | Extend with new event kinds. |

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
- **The `transitive_dep_meta` ×16 / `rag_few_shots` ×3 multiplicity caps.** Implementer chooses raise vs. truncate-with-event; the test must assert the chosen behavior. **Recommendation**: truncate-with-event for `transitive_dep_meta` (large CVEs may have 20+ transitive deps; truncating to 16 is the budget-honoring action), and raise for `rag_few_shots` (caller controls how many examples are retrieved; over 3 indicates a bug upstream in S5-01).
- **Determinism is load-bearing for replay.** S6-07's `test_determinism_under_cassette_replay.py` (50-run byte-identical property) requires `PromptBuilder.build` to be deterministic given the same inputs — the only source of nondeterminism is `nonce_source` in `FenceWrapper`. Test fixtures inject a deterministic nonce factory; production uses `secrets.token_hex(16)`. AC-5's test pins this with deterministic nonces.
- **`PromptAssembled` event content.** AC-10 explicitly forbids the event payload from containing the prompt content or any digest of it — that's `LeafInvoked`'s job in S6-01. `PromptAssembled` carries shape-only metadata.
- **Module placement of newtypes.** If S1-01 already shipped `TrustedPrompt` / `FencedPromptBody` in `src/codegenie/types/identifiers.py`, the sole-mint site rule still holds — the AST walk doesn't care where the newtype is defined, only where it's **called**. The placement of the definition is a style call; pick the convention Phase-4 establishes.
