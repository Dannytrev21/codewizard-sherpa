# Story S1-07 — Phase-4 `fence` CI extension + AST scan for inline f-string prompts

**Step:** Step 1 — Plant the contracts, the two ADR-gated Phase-3 edits, and the fence-CI rules every Phase 4 component consumes
**Status:** Ready
**Effort:** M
**Depends on:** S1-02, S1-03
**ADRs honored:** ADR-P4-004, ADR-P4-008, ADR-P4-009, ADR-P4-011, ADR-P4-014

## Context

Cross-cutting. The fence-CI rules lock Phase 4's import graph at the package boundary so that "extension by addition" is not silently violated by an innocent `import anthropic` in a new file. They also close NG2 (no `langgraph` runtime in Phase 4) and the prompts-as-data discipline (ADR-P4-009): no inline f-strings constructing LLM message bodies under `codegenie.llm/*` or `engines/rag_llm.py`. Without this story, every Phase-4 story can drift the import topology unnoticed; with it, every PR touching the wrong package is CI-red within seconds.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Development view"` — the six import rules verbatim (`codegenie.transforms ⊥ codegenie.{llm,rag}`, etc.).
  - `../phase-arch-design.md §"Agentic best practices"` — prompts-as-data rationale.
  - `../phase-arch-design.md §"Adversarial tests"` (in §Testing strategy) — fence violation must be CI-red.
- **Phase ADRs:**
  - `../ADRs/0009-prompts-as-versioned-yaml-data.md` — ADR-P4-009 — inline-f-string-prompt ban + auto-fence-wrap discipline.
  - `../ADRs/0011-llm-prompt-context-exfiltration-boundary.md` — ADR-P4-011 — `LlmPromptContext` `extra="forbid"`.
  - `../ADRs/0014-langgraph-leaf-agent-node-minimal-wrap.md` — ADR-P4-014 — `langgraph` is a Phase-6 concern only; fence forbids it in Phase 4.
  - `../ADRs/0004-leaf-llm-agent-protocol-os-tiered.md` — ADR-P4-004 — `anthropic` only under `codegenie.llm.leaf_anthropic.*`.
- **Existing code:**
  - `scripts/fence_imports.py` — Phase-0 AST scan; extend.
  - `tests/fence/test_fence_phase0.py` (or similar) — the Phase-0 fence test the extension piggybacks on.

## Goal

Extend `scripts/fence_imports.py` (Phase 0's AST-based import scanner) to enforce the seven Phase-4 import rules and add a sibling AST scan for inline f-string prompt construction; plant deliberate-violation fixtures that the test suite uses to prove the fence is gating.

## Acceptance criteria

- [ ] `scripts/fence_imports.py` enforces:
  1. `codegenie.transforms.*` ⊥ `codegenie.llm.*`, `codegenie.rag.*`
  2. `codegenie.recipes.*` ⊥ `codegenie.llm.*`, `codegenie.rag.*` **EXCEPT** `codegenie.recipes.engines.rag_llm`
  3. `codegenie.rag.*` ⊥ `anthropic`
  4. `codegenie.llm.*` ⊥ `chromadb`, `sentence_transformers`
  5. `anthropic` is importable **only** from `codegenie.llm.leaf_anthropic.*` (covers `client.py`, `in_process.py`, `jailed.py`, `egress_proxy.py`, `jail_launcher.py`)
  6. `langgraph` is forbidden anywhere under `src/codegenie/*` (NG2)
  7. `codegenie.probes.*` ⊥ `anthropic`, `chromadb` (probe at `solved_example_health.py` reads `SolvedExampleStore.health()`, not chromadb directly)
- [ ] `tests/fence/test_no_inline_fstring_prompts.py` runs an AST scan that flags any `ast.JoinedStr` (f-string) whose value flows into a function call argument named like `messages=`, `system=`, `prompt=`, `query_block=`, `system_blocks=`, or any positional arg to a function named `*_invoke`, `*_messages_*`, under `codegenie/llm/*.py` and `codegenie/recipes/engines/rag_llm.py`. False-positive heuristic: skip f-strings whose only `FormattedValue` parts are constants (e.g. `f"v{__version__}"`).
- [ ] `tests/fence/test_fence_phase4.py` plants a deliberate violation fixture file under `tests/fence/fixtures/forbidden_imports/` and runs the fence; CI red expected; the test asserts CI red and the violation message names the offending file + offending import.
- [ ] `tests/fence/test_no_inline_fstring_prompts.py` plants a deliberate violation fixture (`f"system: {x}"` used in an `invoke` call) and asserts CI red with a message naming the offending line.
- [ ] Both tests *pass* (i.e. the fence successfully flags the planted violations).
- [ ] The fence runs in CI as part of the `fence` job; the job is wired in Phase 0 and just needs to pick up the extended rules. Document any CI-yaml change.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` on `scripts/fence_imports.py` clean.

## Implementation outline

1. Open `scripts/fence_imports.py`; extend the rule set. Express each rule as a `(producer_pattern, forbidden_imports)` pair where the producer pattern is a module-path glob (`codegenie.transforms.**`) and forbidden_imports is a set of top-level package names to forbid. Add an `exceptions` map for the `engines/rag_llm.py` case.
2. Walk every `*.py` under `src/codegenie/`, parse via `ast.parse`, collect `Import` and `ImportFrom` nodes, project to top-level package names, evaluate against rules.
3. Sibling scanner: also walk every `*.py` matching the prompt-construction predicate (`codegenie/llm/*.py`, `codegenie/recipes/engines/rag_llm.py`), collect `Call` nodes whose `func` is a `Name` or `Attribute` matching a small allowlist of prompt-sink names (`invoke`, `messages.create`, `messages.stream`, `load`), and check each argument for `JoinedStr` with non-constant `FormattedValue` parts.
4. Plant two deliberate-violation fixture files under `tests/fence/fixtures/forbidden_imports/` and `tests/fence/fixtures/forbidden_fstring/`. The fence script must accept a `--include-fixtures` flag (or be runnable against arbitrary paths) so the fixtures don't pollute production scans but the tests can drive them.
5. Wire into the CI `fence` job. The job either runs `python scripts/fence_imports.py src/codegenie/` (production) and the pytest tests separately, or a single pytest invocation drives both.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/fence/test_fence_phase4.py`

```python
from pathlib import Path

import pytest

from scripts.fence_imports import scan, FenceViolation

FIXTURES = Path(__file__).parent / "fixtures" / "forbidden_imports"


@pytest.mark.parametrize("fixture", sorted(FIXTURES.glob("*.py")))
def test_planted_violations_are_flagged(fixture: Path) -> None:
    violations = scan([fixture])
    assert violations, f"fence missed planted violation in {fixture.name}"
    assert any(fixture.name in v.path for v in violations)


def test_production_tree_passes_fence():
    """The real src/codegenie/ tree must be clean against the extended rules."""
    violations = scan([Path("src/codegenie/")])
    assert violations == [], violations
```

Test file path: `tests/fence/test_no_inline_fstring_prompts.py`

```python
from pathlib import Path

from scripts.fence_imports import scan_fstring_prompts

FIXTURES = Path(__file__).parent / "fixtures" / "forbidden_fstring"


def test_planted_fstring_prompt_is_flagged():
    violations = scan_fstring_prompts(sorted(FIXTURES.glob("*.py")))
    assert violations, "AST scanner missed an f-string prompt"
    msg = " ".join(v.detail for v in violations)
    assert "JoinedStr" in msg or "f-string" in msg.lower()


def test_real_llm_tree_is_fstring_free():
    violations = scan_fstring_prompts(list(Path("src/codegenie/llm/").rglob("*.py")))
    assert violations == [], violations
```

Plant fixtures:

`tests/fence/fixtures/forbidden_imports/bad_transforms_imports_llm.py`:

```python
# violates: codegenie.transforms ⊥ codegenie.llm
from codegenie.llm.contract import LlmRequest  # noqa: F401
```

`tests/fence/fixtures/forbidden_imports/bad_rag_imports_anthropic.py`:

```python
# violates: codegenie.rag ⊥ anthropic
import anthropic  # noqa: F401
```

`tests/fence/fixtures/forbidden_imports/bad_anthropic_outside_leaf.py`:

```python
# violates: anthropic only under codegenie.llm.leaf_anthropic.*
import anthropic  # noqa: F401
```

`tests/fence/fixtures/forbidden_imports/bad_anywhere_langgraph.py`:

```python
# violates: NG2 — no langgraph in Phase 4
import langgraph  # noqa: F401
```

`tests/fence/fixtures/forbidden_fstring/bad_inline_prompt.py`:

```python
def call_model(client, user_input: str) -> None:
    client.messages.create(
        system=f"You are an agent. The user input is: {user_input}",  # forbidden
        messages=[],
    )
```

### Green — make it pass

Implement the extended rule evaluator + the JoinedStr scanner. Keep the scanner conservative: only flag JoinedStr in a function-call arg whose name matches the small allowlist; document the false-positive avoidance heuristic.

### Refactor — clean up

- Factor each rule into its own small function so adding rule #8 in Phase 7 is a one-line registration.
- The fence script must run in < 2 seconds on the full `src/codegenie/` tree; profile if necessary. Anchor: Phase-0 fence is fast; do not regress.
- mypy --strict on the script itself.
- The exceptions map for `engines/rag_llm.py` must be by **module path**, not by file-name suffix, to avoid accidentally allowing `engines/rag_llm_test.py` etc.

## Files to touch

| Path | Why |
|---|---|
| `scripts/fence_imports.py` | Extend rule set + add JoinedStr scanner. |
| `tests/fence/test_fence_phase4.py` | Drive Phase-4 import rules from planted fixtures. |
| `tests/fence/test_no_inline_fstring_prompts.py` | Drive JoinedStr prompt-construction rule. |
| `tests/fence/fixtures/forbidden_imports/*.py` | Planted violation fixtures. |
| `tests/fence/fixtures/forbidden_fstring/*.py` | Planted f-string fixture. |

## Out of scope

- **`PromptLoader` auto fence-wrap implementation** — S2-02. (This story bans the inline f-string anti-pattern; S2-02 ships the YAML-driven alternative.)
- **`LlmPromptContext` Pydantic `extra="forbid"` model** — S2-02 / S2-03.
- **Promotion of the fence to a strict CI gate** — S7-06 (this story makes it gating already for new violations, but S7-06 wires the merge-blocking CI check explicitly).
- **Fence rules for `codegenie.transforms` ⊥ Phase-5 / Phase-7 — packages that don't exist yet** — handled when those packages land.

## Notes for the implementer

- The fence is the **only** defense against silent topology drift; if the script has a false negative (a real violation it misses), the entire phase's "extension by addition" claim is hollow. The "production tree passes fence" test plus the "planted violations are flagged" tests together gate that.
- Conservative JoinedStr scanning is intentional: a tighter rule (any f-string anywhere under `llm/`) would block legitimate `f"v{__version__}"`-style metadata strings. The allowlist of sink-function names is the conservative carrier.
- If a Phase-0 fence-test fixture-discovery pattern exists, reuse it (Rule 11). If the script currently passes one path on the CLI, extend that interface — don't introduce a new entrypoint.
- The `codegenie.probes.*` ⊥ `chromadb` rule exists because `SolvedExampleHealthProbe` (S4-06) consumes `SolvedExampleStore.health()`, not chromadb directly. This isolates schema knowledge to `src/codegenie/rag/` (Rule 8 — read before you write — the existing probe pattern reads from typed APIs, not external libs).
- Edge case: `from anthropic import ...` and `import anthropic.X.Y` must both be caught. Project to the top-level package name first.
- Edge case: an exception import inside `codegenie.errors` (Phase 0) for ergonomics is fine — the fence is about **direction**, not module surface. The rules name producer packages; an unrelated module importing from `codegenie.errors` is unaffected.
- The forbidden-fstring fixture file MUST live outside the production scan path so the production-tree test doesn't trip on it. Default the scanner to `src/codegenie/` and let the test point at fixture roots explicitly.
- Verify with a one-off run on `main` that the production tree is clean before merging — if Phase-3 already accidentally imports `langgraph` somewhere, surface it (Rule 12) rather than carving an exception.
