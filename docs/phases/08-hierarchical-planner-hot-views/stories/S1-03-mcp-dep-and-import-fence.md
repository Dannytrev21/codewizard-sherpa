# Story S1-03 — Pin the mcp SDK and the LLM-SDK import-linter fence group

**Step:** Step 1 — Land the contract primitives and the runtime substrate
**Status:** Ready
**Effort:** S
**Depends on:** S1-01

## Context
Phase 8 ships the first MCP server (`SkillsMcpServer`, Step 8) and four new packages that must stay LLM-free. This story does two cross-cutting substrate jobs: it pins a concrete `mcp` SDK version in `pyproject.toml` (the SDK is young — Open Question 8), and it adds an `import-linter` contract group forbidding every LLM SDK from `codegenie.hotviews`, `codegenie.mcp`, `codegenie.supervisor`, and `codegenie.planner.routing`. The fence is foundational: Goal G3 ("Phase 8 adds `$0.00` of LLM spend") is enforced structurally, not by convention, from the first package onward.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Goals §G3` — Supervisor, hot views, routing, and MCP are 100% deterministic; `import-linter` forbids LLM SDKs from all four new packages; the only LLM seam is `PlannerNode`'s `LeafLlmPort`.
  - `../phase-arch-design.md §Testing strategy §CI gates` — "A new `import-linter` contract group: `codegenie.hotviews`, `codegenie.mcp`, `codegenie.supervisor`, `codegenie.planner.routing` may not import any LLM SDK."
  - `../phase-arch-design.md §C6 — SkillsMcpServer` — the `mcp` SDK is the new dependency; `serve_skills_stdio` runs on an `mcp` SDK `Server`.
  - `../phase-arch-design.md §Open questions deferred to implementation §8` — pin a specific `mcp` version; confirm the stdio transport and tool-advertisement API install cleanly under Python 3.11/3.12.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0012-mcp-skills-server-security-posture.md` — ADR-0012 — the `mcp` SDK version is pinned in `pyproject.toml`; the `MCP_SKILLS_CONTRACT` snapshot (Step 8) guards drift but the initial pin is a deliberate choice.
  - `../ADRs/0001-supervisor-graph-engine.md` — ADR-0001 — Phase 8 ships a plain async pipeline, **not** langgraph; `langgraph` stays forbidden across all four packages with no carve-out.
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0005-no-llm-sdk-in-gather-runtime-closure.md` — the LLM-SDK fence discipline this story extends to the four new packages.
- **Existing code (if any):**
  - `pyproject.toml §[tool.importlinter]` — the existing contract block; the Phase-3 (`codegenie.plugins`/`codegenie.transforms`) and Phase-7 (`codegenie.primitives.vuln_provenance`) LLM-SDK contracts are the precedent — `type = "forbidden"`, `as_packages = true`, `forbidden_modules` mirroring `FORBIDDEN_LLM_SDKS`.
  - `src/codegenie/_fence.py` — `FORBIDDEN_LLM_SDKS` is the canonical five-name set the new contract's `forbidden_modules` must equal.
  - `pyproject.toml §[project.optional-dependencies]` — the `agents = []` "Phase 4+ slot" comment; `mcp` is a real new dep, not an LLM SDK.

## Goal
Pin a concrete `mcp` SDK version in `pyproject.toml` and add an `import-linter` `forbidden` contract group barring every `FORBIDDEN_LLM_SDKS` member from the four new Phase-8 packages, so the LLM-free guarantee is structurally enforced.

## Acceptance criteria
- [ ] A version-pinned `mcp` dependency is declared in `pyproject.toml` (a concrete lower bound and upper cap, e.g. `mcp>=1.x,<2`) with a Phase-8 dep comment; `import mcp` succeeds after `make bootstrap` under Python 3.11 and 3.12.
- [ ] An `import-linter` `[[tool.importlinter.contracts]]` entry of `type = "forbidden"`, `as_packages = true`, names `source_modules` covering `codegenie.hotviews`, `codegenie.mcp`, `codegenie.supervisor`, and `codegenie.planner.routing`, with `forbidden_modules` equal to `codegenie._fence.FORBIDDEN_LLM_SDKS` as a set.
- [ ] `make lint-imports` passes with the new contract (the four packages need not exist yet — the contract is declared ahead of the packages; if `import-linter` requires the modules to exist, the story may add empty `__init__.py` stubs and must record that).
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Research the current `mcp` Python SDK release line; pick a concrete version range that installs cleanly on Python 3.11 and 3.12. Add it to `pyproject.toml` with a Phase-8 + `codegenie.mcp` consumer comment. Record the pinned version and the install verification in the attempt log (Open Question 8).
2. Add a Phase-8 LLM-SDK `import-linter` contract, mirroring the Phase-7 contract's shape (`type = "forbidden"`, `as_packages = true`, `include_external_packages = true`, `forbidden_modules` = the five `FORBIDDEN_LLM_SDKS` names). Use a comment block in the style of the existing Phase-3/Phase-7 contract comments.
3. If `import-linter` cannot resolve not-yet-created `source_modules`, create minimal empty `__init__.py` stubs for the four packages and note this; otherwise leave package creation to Steps 5/6/8.
4. Write the red test asserting the new contract's shape (a sibling of `test_phase7_importlinter_contracts_shape.py`).

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/fence/test_phase8_importlinter_contracts_shape.py`
One red test per behavior; modeled directly on `tests/fence/test_phase7_importlinter_contracts_shape.py`.

```python
def test_phase8_llm_contract_present_and_forbidden_type() -> None:
    # Intent: the Phase-8 LLM-SDK fence must exist as a `forbidden` contract.
    # arrange: tomllib-parse pyproject.toml, find the Phase-8 contract by name
    # act/assert: contract["type"] == "forbidden"
    ...

def test_phase8_contract_covers_all_four_new_packages() -> None:
    # Intent: a missing source module = a silently unfenced package.
    # assert: source_modules covers hotviews, mcp, supervisor, planner.routing
    ...

def test_phase8_contract_forbids_exactly_the_llm_sdk_closure() -> None:
    # Intent: drift from FORBIDDEN_LLM_SDKS = a silently incomplete fence.
    from codegenie._fence import FORBIDDEN_LLM_SDKS
    # assert: set(contract["forbidden_modules"]) == FORBIDDEN_LLM_SDKS

def test_mcp_sdk_is_a_pinned_dependency() -> None:
    # Intent: the young mcp SDK must be version-pinned (Open Question 8).
    # assert: a pyproject dependency starts with "mcp" and carries an
    #         explicit lower bound and upper cap.
```

### Green — make it pass
Add the `mcp` dep line and the one `[[tool.importlinter.contracts]]` block. No `src/` logic.

### Refactor — clean up
Match the Phase-7 contract comment style (an explanatory block above the contract). Confirm `forbidden_modules` is pinned verbatim against `FORBIDDEN_LLM_SDKS` so the contract and the runtime scanner share one source of truth (the Phase-7 test's stated rationale). ADR compliance: `langgraph` is among the forbidden names — no carve-out for `codegenie.supervisor` (ADR-0001 ships a plain async pipeline, not a graph framework).

## Files to touch
| Path | Why |
|---|---|
| `pyproject.toml` | Add the pinned `mcp` dependency and the Phase-8 LLM-SDK `import-linter` contract. |
| `tests/fence/test_phase8_importlinter_contracts_shape.py` | New test file — shape-pin for the new contract; sibling of the Phase-7 test. |
| `src/codegenie/{hotviews,mcp,supervisor}/__init__.py`, `src/codegenie/planner/routing.py` (stubs, only if import-linter requires them) | Minimal stubs so the contract resolves; record if needed. |

## Out of scope
- The `redis` client and the `docker-compose.yml` redis service — S1-02.
- The `tests/fence/` Phase-8 wiring allowlist and the gather-closure fence test — S1-04.
- The `MCP_SKILLS_CONTRACT` snapshot and the real MCP stdio roundtrip — S8-02.
- Any logic inside the four packages — Steps 2–8.

## Notes for the implementer
- The `mcp` SDK is young (Open Question 8). Pin a concrete range, run `make bootstrap` under both Python 3.11 and 3.12, and record the exact version that installs cleanly in the attempt log. If the SDK does not install on one interpreter, surface that loudly before proceeding — it blocks Step 8.
- `forbidden_modules` must equal `FORBIDDEN_LLM_SDKS` as a set, not a hand-typed copy — the Phase-7 test's rationale ("drift between this list and `FORBIDDEN_LLM_SDKS` is the worst-case quiet failure") applies verbatim. The new fence test must compare against the imported constant.
- The contract `source_modules` targets `codegenie.planner.routing` specifically, **not** the whole `codegenie.planner` package — `routing.py` is the LLM-fenced module; the `LeafLlmPort` *Protocol* (in `codegenie.planner.ports`, Step 3) is a seam the concrete LLM adapter plugs into later and is not itself fenced. Pin the source module exactly.
- `import-linter` v2 with external `forbidden_modules` needs `include_external_packages = true` at the `[tool.importlinter]` level (already set) — confirm it stays set.
- If `import-linter` errors on not-yet-created `source_modules`, the minimal fix is empty `__init__.py` stubs; do this only if forced, and note it so Steps 5/6/8 know the package shells already exist.
