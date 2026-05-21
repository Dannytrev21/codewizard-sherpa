# Story S8-03 — Harden SkillId with a traversal-rejecting smart constructor

**Step:** Step 8 — Ship the MCP Skills server
**Status:** Ready
**Effort:** S
**Depends on:** S8-01 (`SkillsMcpServer.get_skill` is the call site whose `SkillId` argument this story hardens)
**ADRs honored:** ADR-0012 (the `SkillId` regex smart constructor — a traversal-shaped ID fails before any filesystem touch), ADR-0010 (newtype-every-domain-ID discipline; the smart constructor is the only sanctioned builder)

## Context
The MCP `get_skill` tool takes a skill ID supplied by an external caller — an unvalidated ID is a path-traversal vector (`get_skill("../../etc/passwd")`). ADR-0012's signature security control is a **regex smart constructor** for `SkillId`: a traversal-shaped ID can never become a `SkillId`, so it is rejected before any filesystem touch. `SkillId` already exists as a free `NewType` in `types/identifiers.py`; this story adds the parser that gates it, mirroring the shipped Phase-3 smart-constructor pattern. This is security-hardening / closeout work for the MCP server.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C6 — SkillsMcpServer` — "`SkillId` is a newtype validated by a regex smart constructor — a traversal-shaped ID (`../../etc/passwd`) fails the newtype before any filesystem touch"
  - `../phase-arch-design.md §Edge cases` — row 12 (Skills-ID path traversal → rejected by the newtype constructor, no filesystem touch, typed error)
  - `../phase-arch-design.md §Agentic best practices — Tool-use safety` — "`SkillId`/`PluginId` are newtypes validated by a regex smart constructor before any filesystem touch"
  - `../phase-arch-design.md §Testing strategy — Adversarial tests` — "Skills-ID traversal — `get_skill("../../etc/passwd")` rejected by the `SkillId` smart constructor before any filesystem touch"
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0012-mcp-skills-server-security-posture.md` — ADR-0012 — the smart-constructor control; "an over-permissive regex re-opens the traversal vector" is the named cost
- **Existing code (if any):**
  - `src/codegenie/types/parsers.py` — the Phase-3 smart-constructor module; `_regex_parser` helper, `parse_recipe_id` / `parse_plugin_id` are the closest precedents — `parse_skill_id` is one catalog row + one public function in the same shape
  - `src/codegenie/types/errors.py` — `ParseError` — the frozen error carried by the `Err` branch
  - `src/codegenie/result.py` — `Result` / `Ok` / `Err` — the smart constructor returns `Result[SkillId, ParseError]`, never raises
  - `src/codegenie/types/identifiers.py` — `SkillId` (existing free `NewType`); update its catalog docstring to name the new sanctioned constructor
  - `src/codegenie/mcp/server.py` — `SkillsMcpServer.get_skill` — the call site that consumes a validated `SkillId`

## Goal
Add `parse_skill_id(s: str) -> Result[SkillId, ParseError]` — a regex smart constructor that rejects any traversal-shaped or otherwise malformed ID — and route the MCP `get_skill` boundary through it so a traversal-shaped ID never reaches the filesystem.

## Acceptance criteria
- [ ] `from codegenie.types.parsers import parse_skill_id` succeeds; `parse_skill_id` is added to that module's `__all__`.
- [ ] `parse_skill_id("../../etc/passwd")` returns an `Err[ParseError]` — no exception, no filesystem access.
- [ ] `parse_skill_id` rejects path separators (`/`, `\`), `..` segments, leading dots, NUL/control characters, and over-length input; it accepts a well-formed skill ID (the same shape `SkillsLoader` already produces — confirm against `skills/model.py` `Skill.id`).
- [ ] The MCP `get_skill` boundary routes its incoming string through `parse_skill_id` and surfaces a typed error on the `Err` branch **before** any `SkillsMcpServer.get_skill` / filesystem touch.
- [ ] An adversarial test asserts `get_skill("../../etc/passwd")` (or the MCP-tool equivalent) is rejected with a typed error and that no filesystem read occurs (e.g. a loader whose read path records call count: 0).
- [ ] The `SkillId` catalog docstring in `types/identifiers.py` names `parse_skill_id` as the sole sanctioned constructor (matching the `SemverVersion` / `RecipeId` docstring style).
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Add a `_SKILL_ID_RX` regex constant to `types/parsers.py` — a tight allowlist (e.g. `^[a-z0-9][a-z0-9_-]{0,63}$` — confirm against the real `Skill.id` shape produced by `SkillsLoader`).
2. Add a `_skill_id_match = _regex_parser(_SKILL_ID_RX, max_len=..., name="SkillId")` catalog row alongside the existing closures.
3. Add the public `parse_skill_id(s: str) -> Result[SkillId, ParseError]` function (one row, same shape as `parse_recipe_id`); add it to `__all__`.
4. Update the `SkillId` docstring in `types/identifiers.py` to name `parse_skill_id`.
5. Route the MCP `get_skill` boundary (in `mcp/stdio.py`'s tool wrapper, or `mcp/server.py`) through `parse_skill_id` — coerce the external string, return / raise a typed error on `Err`.
6. Write the adversarial test proving rejection-before-filesystem-touch.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/types/test_parse_skill_id.py`

```python
@pytest.mark.parametrize(
    "hostile",
    ["../../etc/passwd", "foo/bar", "foo\\bar", "..", ".hidden", "a\x00b", "x" * 500],
)
def test_parse_skill_id_rejects_traversal_and_malformed(hostile: str) -> None:
    """A traversal-shaped or malformed ID can never become a SkillId."""
    result = parse_skill_id(hostile)
    # assert: Err branch, ParseError payload, never raises
    assert isinstance(result, Err)
    assert isinstance(result.error, ParseError)

def test_parse_skill_id_accepts_a_wellformed_id() -> None:
    """A well-formed skill ID round-trips to an Ok[SkillId]."""
    result = parse_skill_id("vuln-npm-bump")
    assert isinstance(result, Ok)
    assert result.value == SkillId("vuln-npm-bump")
```

Second red test — the adversarial no-filesystem-touch guard — at `tests/unit/mcp/test_skill_id_traversal_guard.py`:

```python
def test_get_skill_rejects_traversal_before_filesystem_touch() -> None:
    """get_skill('../../etc/passwd') is rejected before any SkillsLoader read."""
    loader = _RecordingSkillsLoader(skills=[])  # records every read call
    server = SkillsMcpServer(skills_loader=loader)
    server.start()
    with pytest.raises(<typed error>):
        _get_skill_boundary(server, "../../etc/passwd")  # the parse_skill_id-gated path
    # assert: the traversal string never reached a filesystem read
    assert loader.read_calls == 0
```

### Green — make it pass
Add `_SKILL_ID_RX`, the `_skill_id_match` catalog row, `parse_skill_id`. Route the `get_skill` boundary through it. Smallest change — `parse_skill_id` is structurally identical to `parse_recipe_id`.

### Refactor — clean up
Docstring on `parse_skill_id` naming the external boundary (the MCP `get_skill` tool) and ADR-0012. Confirm the regex is tight — ADR-0012 names "an over-permissive regex re-opens the traversal vector" as the cost; the parametrized hostile cases are the guard. Update the `SkillId` catalog docstring in `identifiers.py`. `mypy --strict` clean.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/types/parsers.py` | `_SKILL_ID_RX`, `_skill_id_match`, `parse_skill_id`, `__all__` entry |
| `src/codegenie/types/identifiers.py` | `SkillId` docstring names `parse_skill_id` as the sole sanctioned constructor |
| `src/codegenie/mcp/stdio.py` (or `server.py`) | The `get_skill` boundary routes its string through `parse_skill_id` |
| `tests/unit/types/test_parse_skill_id.py` | Parser unit tests — traversal + malformed rejection, well-formed acceptance |
| `tests/unit/mcp/test_skill_id_traversal_guard.py` | Adversarial: rejection before any filesystem touch |

## Out of scope
- Hardening `PluginId` with its own traversal guard — `parse_plugin_id` already ships in `types/parsers.py`; if it needs the same treatment that is a separate concern, not this story.
- OS-level confinement of the MCP process — deliberately deferred to Phase 9 (ADR-0012).
- Validating `SkillId`s at the `SkillsLoader` load boundary — the loader already uses `O_NOFOLLOW` defense-in-depth (`skills/loader.py`); this story guards the *MCP `get_skill` request* boundary specifically.

## Notes for the implementer
- Confirm the real `Skill.id` shape before fixing the regex — read what `SkillsLoader` actually produces (`skills/model.py` `Skill.id` is a `SkillId` with no documented grammar today). The regex must accept every legitimately-loaded skill ID and reject every traversal shape; an over-tight regex breaks valid lookups, an over-loose one re-opens the vector (ADR-0012's named cost).
- The smart constructor returns `Result`, never raises — that is the Phase-3 `types/parsers.py` convention (Rule 11 — match it). The *MCP tool boundary* converts the `Err` into the typed error the caller sees.
- "Before any filesystem touch" is the load-bearing property — the `read_calls == 0` assertion proves it. Route `parse_skill_id` *before* `SkillsMcpServer.get_skill` is called, not inside it after a lookup.
- Include `..`, both separator styles (`/` and `\`), leading `.`, NUL/control bytes, and over-length input in the hostile parametrize set — a regex that catches `/` but not `\` or a NUL byte is the classic incomplete-allowlist bug.
- This is a `NewType`, not a Pydantic model — `SkillId` stays a free `NewType` in `identifiers.py` (S1-01 deferred the `RepoId` grammar lift to Phase 10; the same restraint applies — the *parser* is the guard, the `NewType` stays plain).
