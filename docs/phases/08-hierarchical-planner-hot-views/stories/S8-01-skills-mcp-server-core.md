# Story S8-01 — Implement the transport-agnostic SkillsMcpServer core

**Step:** Step 8 — Ship the MCP Skills server
**Status:** Ready
**Effort:** M
**Depends on:** S1-04 (the Phase-8 fence allowlist + `mcp`/`redis` deps must be wired before `codegenie.mcp` is created)
**ADRs honored:** ADR-0012 (read-only tools, `start()`-built index, no side effects in the constructor), ADR-0010 (`RepoId` newtype used in signatures)

## Context
Phase 8 ships the first concrete MCP server — a local stdio child process serving Skill manifests to the planner. This story builds the **transport-agnostic core** (`SkillsMcpServer`) — pure Python with no `mcp` SDK import — so the index-building and lookup logic is unit-testable with zero transport machinery. The stdio shell (S8-02) and the `SkillId` hardening (S8-03) layer on top of this core. This is foundational MCP-package work: nothing in `codegenie.mcp` exists until this story creates the package.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C6 — SkillsMcpServer (codegenie.mcp)` — the public interface, the "index built once in `start()`, not at import" rule, "tools return manifests, never inlined bodies" (progressive disclosure)
  - `../phase-arch-design.md §Development view` — `mcp/server.py` is the transport-agnostic core; `mcp/stdio.py` and `mcp/contract.py` are separate modules
  - `../phase-arch-design.md §Harness engineering` — "No configuration is read at import time — all DI through constructors"; `_WARNING_IDS` per package
  - `../phase-arch-design.md §Agentic best practices` — "The in-memory index is built in an explicit `start()` call"
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0012-mcp-skills-server-security-posture.md` — ADR-0012 — two read-only tools; `start()`-built index; manifests not bodies; no side effects in the constructor
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0023-mcp-server-topology.md` — `Deferred`; this server is the first worked example of that eventual topology
- **Existing code (if any):**
  - `src/codegenie/skills/loader.py` — `SkillsLoader` — reuse `load_all()` (the shipped three-tier loader); inspect its return shape
  - `src/codegenie/skills/model.py` — `Skill` (frozen, progressive-disclosure: `id`, `applies_to_tasks`, `applies_to_languages`, `body_offset`, `body_size`, `body_blake3` — no inlined body)
  - `src/codegenie/types/identifiers.py` — `RepoId` (added in S1-01), `SkillId`, `TaskClassId`, `Language`

## Goal
Create `codegenie/mcp/server.py` with a `SkillsMcpServer` whose `start()` builds an in-memory `(task_class, language)` index once and whose `list_skills` / `get_skill` are O(1) dict lookups returning `SkillManifest`s — with no I/O or side effects in the constructor.

## Acceptance criteria
- [ ] `from codegenie.mcp.server import SkillsMcpServer, SkillManifest` succeeds; the `codegenie/mcp/` package exists with `__init__.py` and a module-level `__all__`.
- [ ] `SkillsMcpServer.__init__(*, skills_loader: SkillsLoader)` performs **no** I/O and builds **no** index — constructing the server does not call `load_all()` (verifiable by a fake loader whose `load_all` records call count: 0 after `__init__`, 1 after `start()`).
- [ ] `start()` calls `skills_loader.load_all()` exactly once and builds a dict keyed by `(TaskClassId, Language)`; calling `start()` twice does not call `load_all()` twice (idempotent or guarded — implementer's choice, documented).
- [ ] `list_skills(repo: RepoId)` and `get_skill(skill_id: SkillId)` return `SkillManifest` objects carrying only `id`, frontmatter fields, `body_offset`, `body_size`, `body_blake3` — never an inlined skill body.
- [ ] Calling `list_skills` / `get_skill` before `start()` raises a typed error (not an `AttributeError` / `None` deref) — fail loud per Rule 12.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Create `src/codegenie/mcp/__init__.py` and `src/codegenie/mcp/server.py` with `__all__`.
2. Declare `SkillManifest` — a frozen Pydantic model (`ConfigDict(frozen=True, extra="forbid")`) projecting `Skill` to its manifest fields (`id`, `applies_to_tasks`, `applies_to_languages`, `body_offset`, `body_size`, `body_blake3`). Add a pure `_to_manifest(skill: Skill) -> SkillManifest` helper.
3. Declare `SkillsMcpServer`: constructor stores the injected `SkillsLoader` and sets the index to `None` (not built).
4. `start()` — call `load_all()`, build `dict[tuple[TaskClassId, Language], list[SkillManifest]]` (and a `dict[SkillId, SkillManifest]` for `get_skill`); guard against rebuilding on a second `start()`.
5. `list_skills(repo)` / `get_skill(skill_id)` — dict lookups; raise a typed `McpServerNotStarted` error if the index is still `None`; `get_skill` raises a typed `SkillNotFound` on a missing id.
6. Declare the module-level `_WARNING_IDS: Final[frozenset[str]]` validated at import via `raise AssertionError(...)` against `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` (the regex test arrives in S3-05; this story seeds the constant for the `codegenie.mcp` package).

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/mcp/test_skills_mcp_server_core.py`

One red test per behavior:

```python
def test_constructor_does_no_io() -> None:
    """SkillsMcpServer.__init__ must not call load_all — index is built in start()."""
    loader = _FakeSkillsLoader(skills=[_fixture_skill()])
    server = SkillsMcpServer(skills_loader=loader)
    # arrange: construct only
    # act: nothing
    # assert: load_all was never called
    assert loader.load_all_calls == 0

def test_start_builds_index_once_then_list_skills_is_a_dict_lookup() -> None:
    """start() builds the index; list_skills returns manifests, never bodies."""
    loader = _FakeSkillsLoader(skills=[_fixture_skill(id="vuln-npm-bump")])
    server = SkillsMcpServer(skills_loader=loader)
    server.start()
    manifests = server.list_skills(RepoId("acme/web"))
    # assert: exactly one call to load_all, result is SkillManifest, no body field
    assert loader.load_all_calls == 1
    assert all(isinstance(m, SkillManifest) for m in manifests)
    assert not hasattr(manifests[0], "body")

def test_list_skills_before_start_raises_typed_error() -> None:
    """Calling list_skills before start() fails loud, not AttributeError."""
    server = SkillsMcpServer(skills_loader=_FakeSkillsLoader(skills=[]))
    with pytest.raises(McpServerNotStarted):
        server.list_skills(RepoId("acme/web"))
```

Add a `_FakeSkillsLoader` test double exposing `load_all()` and a `load_all_calls` counter, plus a `_fixture_skill(...)` helper building a valid `Skill`.

### Green — make it pass
Implement `SkillManifest`, `_to_manifest`, `SkillsMcpServer` with a lazily-built `None`-initialized index, `start()`, `list_skills`, `get_skill`, and the `McpServerNotStarted` / `SkillNotFound` typed errors. Smallest shape: two dicts (one `(task,lang)`-keyed, one `SkillId`-keyed) built in `start()`.

### Refactor — clean up
Docstrings on `SkillsMcpServer`, `start`, `list_skills`, `get_skill`, `SkillManifest`. Type hints throughout (`mypy --strict`). Edge case 11 (process death → fallthrough to `SkillsLoader`) is the stdio shell's concern (S8-02) — note it, do not implement it here. `structlog` a `mcp.index_built` event at the end of `start()` per §Harness engineering. Confirm `_WARNING_IDS` is a `Final[frozenset[str]]` validated at import.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/mcp/__init__.py` | New package; `__all__` for the bounded public surface |
| `src/codegenie/mcp/server.py` | `SkillsMcpServer`, `SkillManifest`, `_to_manifest`, typed errors, `_WARNING_IDS` |
| `tests/unit/mcp/__init__.py` | New test package |
| `tests/unit/mcp/test_skills_mcp_server_core.py` | The red tests + `_FakeSkillsLoader` / `_fixture_skill` doubles |

## Out of scope
- The `mcp` SDK stdio transport, the two MCP tools, `MCP_SKILLS_CONTRACT`, the snapshot test, and the real-roundtrip integration test — S8-02.
- The `SkillId` regex smart constructor — S8-03 (this story uses the existing `SkillId` newtype as-is; `get_skill` accepts whatever `SkillId` it is handed).
- The `_WARNING_IDS` import-time regex *validation test* across all four packages — S3-05 (this story seeds the `codegenie.mcp` constant only).

## Notes for the implementer
- Inspect `SkillsLoader.load_all()`'s real return shape before writing `start()` — `loader.py` returns a typed `LoadOutcome`; index off whatever `Skill` collection it surfaces, not an assumed `list[Skill]`.
- `SkillManifest` must **not** carry a body — `Skill` itself already records only `body_offset`/`body_size`/`body_blake3` (progressive disclosure, commitment §7). The `not hasattr(m, "body")` assertion is the guard against regressing that.
- "No side effects in the constructor" is an ADR-0012 consequence — the `load_all_calls == 0`-after-`__init__` assertion is the test that enforces it. Do not move index-building into `__init__` even though it would be one fewer call site.
- Keep the public surface small — `SkillsMcpServer`, `SkillManifest`, and the two typed errors are the only names; helpers stay underscore-prefixed and out of `__all__` (the ≤24-name budget across the four packages is tracked).
- `RepoId` is a free `NewType` (S1-01) — `list_skills(repo: RepoId)` may not actually need `repo` to filter in Phase 8 (the index is `(task,lang)`-keyed); keep the parameter in the signature for the C6 contract and Phase-10 forward-compatibility, and document why it is currently unused if so.
