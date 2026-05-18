# ADR-0009: `RecipeEngine` Protocol ships with TWO implementations on day one — `NpmLockfileRecipeEngine` (production) + `OpenRewriteRecipeEngine` (scaffold)

**Status:** Accepted
**Date:** 2026-05-17
**Tags:** strategy-pattern · premature-pluggability-avoidance · phase-7-readiness · protocol-rent
**Related:** [0004](0004-plugin-private-capabilities-via-tccm.md), [0010](0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md), [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md), [production ADR-0031](../../../production/adrs/0031-plugin-architecture.md)

## Context

Production ADR-0011 commits to recipe-first planning, with **deterministic recipes** as the cheapest and most-reliable transformation tier (OpenRewrite for Java/Dockerfile, hand-rolled AST for tighter scopes, NCU-style for ecosystem package bumps). Phase 3 ships the first plugin (`vulnerability-remediation--node--npm`), so it must define the `RecipeEngine` Protocol that Phase 7's distroless work and every future recipe will implement against.

The design-patterns toolkit explicitly warns against **premature pluggability** (§Anti-patterns to flag explicitly): "Strategy with a single implementation = unnecessary indirection. Wait for the second implementation before extracting." All three Phase 3 lens designs proposed `RecipeEngine` as a Protocol but shipped only **one** implementation (npm-lockfile). Performance demoted OpenRewrite to "Protocol-only future"; security shipped it as a JVM fallback never exercised; best-practices deferred OpenRewrite entirely.

The critic correctly attacked this in `critique.md` and `final-design.md §Shared blind spots #1`: a Protocol with one day-one implementation is the toolkit's anti-pattern by definition. **Phase 7's distroless plugin will need OpenRewrite-style structural transforms** for Dockerfile rewrites (alpine → cgr.dev/chainguard, multi-stage cleanup), and discovering JVM-subprocess infrastructure needs at Phase 7 under a "zero edits" exit criterion would force kernel changes.

The architecture spec resolves it: ship the `OpenRewriteRecipeEngine` as a **scaffold** in Phase 3 — Protocol-conformant, JVM-subprocess shell, with one Phase-7-tagged Dockerfile-base-image-swap fixture, **never invoked by any Phase 3 npm workflow**. The Protocol has two real implementations from day one (`phase-arch-design.md §Component design C12`, §Design patterns applied row 2).

## Options considered

- **Option A — `RecipeEngine` Protocol with one implementation (`NpmLockfileRecipeEngine`); add the second when Phase 7 needs it.** Toolkit-recommended on its face, but the prediction "Phase 7 will need OpenRewrite" is already in flight via production ADR-0011 and `auto-agent-design.md §2.2`. **Pattern:** Premature-pluggability-avoidance, applied too literally.
- **Option B — Concrete `NpmLockfileRecipeEngine` class with no Protocol; extract a Protocol when needed.** Cleaner under the "wait for second impl" rule, but Phase 7 then introduces both the Protocol AND the second impl AND the dispatch refactor — three things at once under a "zero edits" constraint. **Pattern:** YAGNI taken past its useful boundary.
- **Option C — `RecipeEngine` Protocol with TWO implementations: `NpmLockfileRecipeEngine` (production, used by every Phase 3 npm workflow) + `OpenRewriteRecipeEngine` (scaffolded — Protocol-conformant, JVM-subprocess wrapper, one Dockerfile fixture, marked `@pytest.mark.phase_7_preview`).** The Protocol pays rent from day one because two real implementations exercise it. **Pattern:** Strategy pattern with two genuine implementations — not premature.

## Decision

Adopt **Option C.** Ship `RecipeEngine(Protocol)` in `src/codegenie/plugins/protocols.py` with method `async def apply(self, repo, plan, capability) -> RecipeOutcome`. Ship two implementations:

- **`NpmLockfileRecipeEngine`** (`plugins/vulnerability-remediation--node--npm/recipes/`) — pure Python. Parses `package.json` (`orjson`, size cap 1 MiB), edits affected dep version in-mem (key order preserved), writes back via `SandboxedPath` with `O_NOFOLLOW`, runs `SubprocessJail.run(npm install --package-lock-only --ignore-scripts --no-audit --prefer-offline)`, parses the new lockfile (size cap 32 MiB, depth cap 24), returns `RecipeOutcome.Applied(NpmLockfileTransform(...))`.
- **`OpenRewriteRecipeEngine`** (`src/codegenie/transforms/openrewrite_engine.py`) — scaffolded. Protocol-conformant. JVM subprocess invoked via `SubprocessJail`. Ships one fixture (`tests/fixtures/openrewrite/dockerfile-base-image-swap/`) + a `@pytest.mark.phase_7_preview` test. **Not invoked by any Phase-3 npm workflow.**

## Tradeoffs

| Gain | Cost |
|---|---|
| `RecipeEngine` Protocol pays rent from Phase 3 — two real implementations exercise the contract (no risk of a 1-impl Protocol disguising design errors) | +~250 LOC of OpenRewrite scaffolding (JVM-subprocess wrapper + one fixture) for code not exercised by Phase-3 npm workflows |
| Phase 7's distroless plugin inherits a working `OpenRewriteRecipeEngine` — adding a Dockerfile-rewrite recipe is a *recipe addition*, not an engine + recipe + dispatch invention | JVM tooling shipped at Phase 3 (Java runtime as a `SubprocessJail` payload); the binary becomes a real dependency, added to `ALLOWED_BINARIES` only when Phase 7 enables it (Phase 3 doesn't run the JVM at workflow time) |
| The day-one second implementation forces Protocol questions to be answered at design time (what does `apply` return for a no-op? how does the engine signal `NotApplicable`?) — not at Phase 7's "zero edits" deadline | Reviewers might wonder why the scaffold exists; documentation cost (this ADR) |
| `RecipeProtocol` (4 recipes in Phase 3) underneath `NpmLockfileRecipeEngine` is genuinely polymorphic — `NpmLockfileSemverBumpRecipe`, `NpmPeerDepConflictRecipe`, `NpmTransitiveOverridesRecipe`, `NpmMajorBumpRefuseRecipe`; pluggability earns its keep | Two-level Protocol hierarchy (`RecipeEngine` + `RecipeProtocol`) adds one layer of indirection; mitigated by the 4-recipe count being real |
| The `phase_7_preview` pytest marker is a clear signal — the scaffold is exercised by tests on every CI run, but production paths never invoke it | If the marker is dropped or the fixture rots, Phase 7 inherits broken scaffolding; CI gate `tests/integration/test_recipe_engine_protocol.py` asserts both implementations satisfy the Protocol |

## Pattern fit

Implements **Strategy pattern** (toolkit §Behavioral patterns) with the explicit guardrail: "wait for the second implementation before extracting." Here the second implementation is shipped *with* the Protocol, exercising it from day one. Also implements **Dependency inversion** — plugins depend on the `RecipeEngine` abstraction, not on `NpmLockfileRecipeEngine` directly. Avoids the anti-pattern of `RecipeEngine` Protocol with a single implementation that would be the toolkit's textbook "unnecessary indirection." The architecture spec calibrates the count (`§Design patterns applied`): "Two genuinely different implementations from day one — not 'one + future.' The Protocol pays rent from Phase 3."

## Consequences

- `src/codegenie/plugins/protocols.py` exports `RecipeEngine(Protocol)`.
- `OpenRewriteRecipeEngine` ships in `src/codegenie/transforms/` (not under `plugins/`) because it's a kernel-level recipe engine consumable by any plugin.
- Phase 7's `plugins/distroless-migration--node--npm/recipes/` will instantiate `OpenRewriteRecipeEngine` with its own Dockerfile-rewrite recipes — zero kernel edits.
- The JVM subprocess inside `OpenRewriteRecipeEngine` is jailed via `SubprocessJail` (per ADR-0006); the JVM SecurityManager rejection (per `critique.md §Security — Issue 4`) is honored — `SubprocessJail` is the real defense.
- `tests/fixtures/openrewrite/dockerfile-base-image-swap/` is the inheritance contract from Phase 3 to Phase 7.
- `tests/integration/test_recipe_engine_protocol.py` asserts (a) `NpmLockfileRecipeEngine` satisfies the Protocol, (b) `OpenRewriteRecipeEngine` satisfies the Protocol, (c) both produce typed `RecipeOutcome` discriminated-union variants.
- The `java` binary is **NOT** in Phase 3's `ALLOWED_BINARIES` — added only when Phase 7 enables it (`OpenRewriteRecipeEngine` is scaffolded, but the binary it would spawn is gated).
- Future RecipeEngine implementations (e.g., a Python-AST `LibCST`-based engine for Phase 8+ library upgrades) add as new modules; no edits here.

## Reversibility

**High.** Adding a third RecipeEngine implementation is mechanical. Removing the OpenRewriteRecipeEngine scaffold is also mechanical but would force Phase 7 to invent JVM infrastructure under a "zero edits to existing code" exit criterion — a real regression. The chosen shape is the low-cost-to-extend direction.

## Evidence / sources

- `../phase-arch-design.md §Component design C12`, §Design patterns applied row 2, §Departures from all three inputs #3
- `../final-design.md §Synthesis ledger rows "Default recipe engine"` (score 15/15) and "OpenRewriteRecipeEngine ship-or-defer" (score 15/15), §Shared blind spots #1, §Pattern reconciliation row "Strategy on RecipeEngine"
- `../critique.md §Shared blind spots: all three demoted OpenRewrite`
- [production ADR-0011 — recipe-first planning](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md)
- [production ADR-0031 — plugin architecture](../../../production/adrs/0031-plugin-architecture.md)
- design-patterns-toolkit.md §Strategy pattern, §Anti-patterns (premature pluggability)
