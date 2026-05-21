# Story S8-02 — Serve the MCP stdio transport and pin the contract snapshot

**Step:** Step 8 — Ship the MCP Skills server
**Status:** Ready
**Effort:** M
**Depends on:** S8-01 (`SkillsMcpServer` core must exist before the stdio shell wraps it)
**ADRs honored:** ADR-0012 (exactly two read-only tools, `MCP_SKILLS_CONTRACT` snapshot, no write/exec/filesystem-path tool, OS confinement deliberately deferred to Phase 9)

## Context
S8-01 built the transport-agnostic `SkillsMcpServer` core. This story attaches it to a real `mcp` SDK `Server` running **stdio transport**, exposes exactly the two read-only tools ADR-0012 sanctions (`list_skills`, `get_skill`), and pins the advertised tool surface as `MCP_SKILLS_CONTRACT` — snapshot-tested so any drift is a loud CI failure. This closes the `roadmap.md` §Phase 8 deliverable "the Skills server runs as a local MCP stdio process". It carries real integration risk against a young SDK, so a live stdio roundtrip is part of the done-criteria.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C6 — SkillsMcpServer (codegenie.mcp)` — `serve_skills_stdio`, `MCP_SKILLS_CONTRACT`, "two read-only MCP tools on an `mcp` SDK `Server` running stdio transport. No write tool, no exec tool, no filesystem-path tool"
  - `../phase-arch-design.md §C6 — Failure behavior` — "If the stdio process dies, leaf skill lookups fall through to a direct `SkillsLoader` read … `serve_skills_stdio` logs the death" (edge case 11)
  - `../phase-arch-design.md §Testing strategy — Golden files` — `tests/golden/mcp/` holds the `MCP_SKILLS_CONTRACT` snapshot
  - `../phase-arch-design.md §Testing strategy — CI gates` — "The MCP contract snapshot test — breaking the tool surface fails CI"
  - `../phase-arch-design.md §Edge cases` — row 11 (MCP subprocess dies → fallthrough, logged)
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0012-mcp-skills-server-security-posture.md` — ADR-0012 — Option C: stdio + two read-only tools + `MCP_SKILLS_CONTRACT` snapshot; OS-level confinement (seccomp, bind-mounts) is **deliberately not built** — that anti-decision must not be re-introduced
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0023-mcp-server-topology.md` — `Deferred`; this stdio server is the first worked example
- **Existing code (if any):**
  - `tests/unit/transforms/test_sandbox_jail_contract_snapshot.py` — the codebase's contract-snapshot idiom — mirror its structure for `MCP_SKILLS_CONTRACT`
  - `src/codegenie/mcp/server.py` — `SkillsMcpServer` (from S8-01) — the shell delegates to it
  - `pyproject.toml` — the `mcp` SDK row pinned in S1-03 (Open Question 8) — confirm the pinned version's stdio + tool-advertisement API matches before writing the snapshot

## Goal
Create `codegenie/mcp/stdio.py` and `codegenie/mcp/contract.py` so `serve_skills_stdio` runs an `mcp` SDK `Server` over stdio advertising exactly two read-only tools, with the advertised surface pinned by `MCP_SKILLS_CONTRACT` and guarded by a golden snapshot test.

## Acceptance criteria
- [ ] `from codegenie.mcp.stdio import serve_skills_stdio` and `from codegenie.mcp.contract import MCP_SKILLS_CONTRACT` succeed.
- [ ] `MCP_SKILLS_CONTRACT: Final[McpServerContract]` is a frozen model pinning exactly two tools — `list_skills` and `get_skill` — and **no** write / exec / filesystem-path tool.
- [ ] A golden snapshot test in `tests/golden/mcp/` asserts the live `mcp` `Server`'s advertised tool surface byte-matches `MCP_SKILLS_CONTRACT`; introducing a third tool or renaming one fails the test.
- [ ] One integration test exercises a real `mcp` stdio roundtrip — start the server, call `list_skills` and `get_skill` over the transport, assert typed manifests come back.
- [ ] `serve_skills_stdio` logs a typed `structlog` event on process death — the outage is visible, never silent (edge case 11, Rule 12).
- [ ] `make lint-imports` is green — `codegenie.mcp` imports no LLM SDK (the S1-03 fence group).
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Create `src/codegenie/mcp/contract.py`: declare `McpToolSpec` (frozen — `name`, `description`, declared input/output shape) and `McpServerContract` (frozen — `tools: tuple[McpToolSpec, ...]`), then `MCP_SKILLS_CONTRACT: Final[McpServerContract]` with the two read-only tool specs.
2. Create `src/codegenie/mcp/stdio.py`: `serve_skills_stdio(*, skills_loader: SkillsLoader) -> None` — build a `SkillsMcpServer`, call `start()`, register the two tools on an `mcp` SDK `Server`, and run it over the SDK's stdio transport.
3. Each registered tool delegates to `SkillsMcpServer.list_skills` / `.get_skill` — no logic in the tool wrapper beyond argument coercion to the typed inputs.
4. Wrap the run loop so a transport error / process death is caught and logged via `structlog` (edge case 11) before re-raising or returning.
5. Write the contract snapshot test against `tests/golden/mcp/mcp_skills_contract.json` (or the codebase's snapshot format) — regenerate-and-diff like `test_sandbox_jail_contract_snapshot.py`.
6. Write the real stdio roundtrip integration test under `tests/integration/`.
7. Add the two new public names to the package `__all__`; confirm the ≤24-name surface budget is not exceeded (record in the attempt log if it is).

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/golden/mcp/test_mcp_skills_contract_snapshot.py`

```python
def test_live_server_tool_surface_matches_pinned_contract() -> None:
    """The live mcp Server advertises exactly the tools MCP_SKILLS_CONTRACT pins."""
    # arrange: build the mcp Server via the same path serve_skills_stdio uses
    advertised = _advertised_tool_surface(skills_loader=_FakeSkillsLoader(skills=[]))
    # act + assert: byte-match against the pinned snapshot
    assert advertised == _read_golden("tests/golden/mcp/mcp_skills_contract.json")
    # and the contract pins exactly two read-only tools
    assert {t.name for t in MCP_SKILLS_CONTRACT.tools} == {"list_skills", "get_skill"}
```

Second red test — the live integration roundtrip — at `tests/integration/test_mcp_stdio_roundtrip.py`:

```python
async def test_stdio_roundtrip_list_and_get_skill() -> None:
    """A real mcp stdio client can call list_skills and get_skill end to end."""
    # arrange: spawn serve_skills_stdio as a child process over stdio
    # act: call list_skills(repo) then get_skill(skill_id) over the transport
    # assert: both return typed SkillManifest payloads matching the loaded fixture
```

A drift guard: a test that adding a hypothetical third tool to the live server (without updating the snapshot) makes the snapshot test fail — encoded as a comment / a parametrized negative case, not a real third tool.

### Green — make it pass
Implement `McpToolSpec`, `McpServerContract`, `MCP_SKILLS_CONTRACT`, and `serve_skills_stdio`. Register the two tools on the `mcp` SDK `Server`; expose a small `_advertised_tool_surface(...)` helper the snapshot test calls without spawning a process. Smallest shape that makes both red tests green.

### Refactor — clean up
Docstrings on `serve_skills_stdio`, `McpServerContract`, `MCP_SKILLS_CONTRACT`. Edge case 11 logging wired and asserted. Confirm `mypy --strict` on the `mcp` SDK call sites (add a `[tool.mypy.overrides]` entry only if the SDK genuinely lacks stubs — note it in the attempt log). Confirm the `import-linter` LLM-SDK fence still passes. Keep `MCP_SKILLS_CONTRACT` a `Final`.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/mcp/contract.py` | `McpToolSpec`, `McpServerContract`, `MCP_SKILLS_CONTRACT` |
| `src/codegenie/mcp/stdio.py` | `serve_skills_stdio` — the `mcp` SDK stdio shell, two read-only tools |
| `src/codegenie/mcp/__init__.py` | Export `serve_skills_stdio`, `MCP_SKILLS_CONTRACT` |
| `tests/golden/mcp/mcp_skills_contract.json` | The pinned tool-surface snapshot |
| `tests/golden/mcp/test_mcp_skills_contract_snapshot.py` | The snapshot drift test |
| `tests/integration/test_mcp_stdio_roundtrip.py` | The real stdio roundtrip |

## Out of scope
- OS-level confinement of the MCP child process (seccomp, bind-mounts, `no_new_privileges`) — **deliberately deferred to Phase 9** per ADR-0012; do not re-introduce it as a "while we're here" hardening.
- The `SkillId` traversal-rejecting smart constructor — S8-03.
- Process supervision / restart-on-death — Phase 9's Temporal envelope owns it; this story only logs the death.
- Wiring the planner to *consume* the MCP server — the planner falls through to `SkillsLoader` directly today (C6 §Failure behavior); MCP consumption is a later integration.

## Notes for the implementer
- **Validate the pinned `mcp` SDK version first.** Open Question 8 / implementation risk 2: the young `mcp` SDK's stdio transport and tool-advertisement API may not match the contract's assumptions. Confirm against the S1-03-pinned version *before* writing the snapshot — if the SDK's real shape diverges, adjust `MCP_SKILLS_CONTRACT` to the SDK's shape rather than forcing the SDK (ADR-0012's Reversibility note sanctions this).
- The snapshot must be derived from the **live** server's advertised surface, not hand-written — a hand-written snapshot that drifts from the SDK's real advertisement defeats the test. Build the surface via the same code path `serve_skills_stdio` uses.
- Exactly **two** tools — no write, no exec, no filesystem-path tool. Adding a write tool is a new ADR (ADR-0012 Reversibility); the snapshot test is the structural guard against silently adding one.
- The stdio roundtrip test spawns a child process — keep it under `tests/integration/` and make it robust to slow process startup; it is one test, not a perf gate.
- `structlog` the process-death event with an ID matching `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` (e.g. `mcp.process_died`) — it must be in the `codegenie.mcp` package's `_WARNING_IDS` frozenset (S8-01 seeded the constant).
