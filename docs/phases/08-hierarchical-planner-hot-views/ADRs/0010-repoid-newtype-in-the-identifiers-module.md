# ADR-0010: RepoId is a newtype added to the identifiers module

**Status:** Accepted
**Date:** 2026-05-21
**Tags:** Newtype pattern · Open/Closed at the file boundary · domain modeling
**Related:** ADR-0002, [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md), [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)

## Context

Phase 8 threads a repository identifier through every new package — `SupervisorState.repo_id`, `HotViewKey.repo_id`, `HotViewStore.get(repo, ...)`, `HotViewStore.get_all(repo)`, `SkillsMcpServer.list_skills(repo)`. `final-design.md`'s design-patterns table lists `RepoId` among the identifiers "already in `codegenie.types.identifiers`."

It is **not there** — see [phase-arch-design.md §Gap 3](../phase-arch-design.md#gap-3--repoid-does-not-exist-the-synthesis-uses-it-pervasively). `codegenie/types/identifiers.py` ships `SkillId`, `TaskClassId`, `Language`, `PluginId`, `RecipeId`, `WorkflowId`, `EventId`, `CveId`, `BranchName`, `BlobDigest`, `PrimitiveName` — but no `RepoId`. A Phase-8 implementer following the synthesis verbatim would either import a non-existent name (a hard failure) or fall back to `repo_id: str` — the stringly-typed-identifier anti-pattern the toolkit flags on sight: a domain primitive in ~50 call sites with no way to refactor or grep it meaningfully, and no compile-time guard against swapping it for a `WorkflowId`.

## Options considered

- **Option A — Add `RepoId = NewType("RepoId", str)` to `codegenie/types/identifiers.py`.** A loud, compiler-policed additive edit; the name joins `__all__`. **Pattern:** Newtype pattern — a zero-cost wrapper distinguishing a domain identifier from raw `str`.
- **Option B — Use raw `str` for repo identifiers in Phase 8.** **Pattern:** the "stringly-typed identifiers" anti-pattern — the toolkit's explicit "flag on sight" item; the type checker cannot catch a `RepoId`/`WorkflowId` swap.
- **Option C — Add `RepoId` as a full Pydantic smart-constructor type with an `owner/name` grammar now.** **Pattern:** Smart constructor — but Phase 8 has no `owner/name` grammar requirement yet; Phase 10 (Discovery) is where GitHub repo identity is pinned. Building the grammar now is speculative.

## Decision

Phase 8 **adds `RepoId = NewType("RepoId", str)` to `codegenie/types/identifiers.py`**, with the name added to that module's `__all__` — a loud, compiler-policed additive edit (the same class as a new `Literal` member, per commitment §5 / [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)). Every Phase-8 signature uses `RepoId`, never `str`. Whether `RepoId` later carries an `owner/name` grammar and a smart-constructor lift is deferred to Phase 10 Discovery — the newtype is the additive seam where that grammar lands. This is the **Newtype pattern**.

## Tradeoffs

| Gain | Cost |
|---|---|
| Repo identifiers are a distinct type — a `RepoId`/`WorkflowId`/`PluginId` swap is a compile-time error, not a runtime surprise | One additive edit to a shipped file (`identifiers.py` + its `__all__`) — loud and compiler-policed, but still an edit |
| `RepoId` is greppable and refactorable across its ~50 Phase-8 call sites | A bare `NewType` carries no validation — a malformed repo string still type-checks as a `RepoId` until Phase 10 adds a grammar |
| The newtype is the additive seam where Phase 10's GitHub `owner/name` grammar lands — no Phase-8 signature changes when it does | Deferring the grammar means Phase 8 cannot reject a malformed repo identifier at the type boundary yet |
| Consistent with the codebase's universal newtype-for-domain-IDs discipline ([production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md)) | A future smart-constructor lift will need to thread through existing `RepoId(...)` call sites — a (small, compiler-found) migration |

## Pattern fit

The toolkit's "Newtype pattern" entry is unambiguous: "every domain primitive… `RepoId`, `PRNumber`, `RunId`… **especially identifiers that flow across module boundaries**." `RepoId` flows across all four new Phase-8 packages and into the identifiers module shared with the rest of the codebase — it is the textbook case. The failure mode the toolkit names — "swapping a `RepoId` for a `PRNumber` because both are `str`" — is exactly what `repo_id: str` (Option B) would expose. Deferring the `owner/name` grammar (rejecting Option C) avoids the toolkit's "premature" trap: a smart constructor is built when its grammar is known, and Phase 10 owns the GitHub repo-identity shape.

## Consequences

- `codegenie/types/identifiers.py` gains `RepoId = NewType("RepoId", str)` and the name in `__all__` — a fence-enumerated additive edit.
- Every Phase-8 signature carrying a repo identifier uses `RepoId` — `SupervisorState`, `HotViewKey`, `HotViewStore`, `SkillsMcpServer`.
- The story plan must include the `RepoId` addition as an explicit first step (downstream Phase-8 work depends on the name existing).
- Phase 10 Discovery decides whether `RepoId` gains an `owner/name` grammar and a smart-constructor lift — the newtype is the additive seam; no Phase-8 signature changes.
- A bare `NewType` does not validate — Phase 8 accepts that; the grammar is a Phase-10 concern (Open Question 7).
- The per-submodule cold-start fence (`tests/fence/`) covers the additive identifiers edit.

## Reversibility

**Low.** Once `RepoId` is threaded through ~50 Phase-8 call sites and the four new packages' public signatures, removing it would mean reverting every signature to `str` — a wide change, and a regression to a flagged anti-pattern. *Lifting* it later (adding a grammar / smart constructor) is the expected, compiler-assisted evolution. The newtype itself is here to stay; only its *richness* is open.

## Evidence / sources

- ../phase-arch-design.md §Gap 3 — `RepoId` does not exist
- ../phase-arch-design.md §Data model — `RepoId = NewType("RepoId", str)`
- ../phase-arch-design.md §Open question 7 — `RepoId` grammar
- ../final-design.md §design-patterns table — `RepoId` listed (incorrectly) as already shipped
- ../../../production/adrs/0033-domain-modeling-discipline.md — newtype identifiers discipline
- ../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md — additive-edit discipline
- `design-patterns-toolkit.md` §Newtype pattern; §Anti-patterns — "Stringly-typed identifiers"
