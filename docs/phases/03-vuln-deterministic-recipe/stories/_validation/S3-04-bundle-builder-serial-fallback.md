# Validation report — S3-04 `BundleBuilder` with `asyncio.Semaphore` concurrency + deterministic serial fallback

**Story:** [`docs/phases/03-vuln-deterministic-recipe/stories/S3-04-bundle-builder-serial-fallback.md`](../S3-04-bundle-builder-serial-fallback.md)
**Date:** 2026-05-18
**Verdict:** **HARDENED**
**Validator:** `/phase-story-validator` skill (Opus 4.7, scheduled `story-validation-corrector` run)

## Context brief

S3-04 ships `BundleBuilder` — the Phase 3 component that dispatches a plugin's TCCM `must_read` / `should_read` / `may_read` graph queries through Phase 2's language search adapters, applies the **ADR-0008 deterministic serial fallback** rule (NOT hedged-race) when an adapter returns `Degraded` or `Unavailable`, and emits `AdapterDegraded` events for `TrustScorer.confidence` folding.

The load-bearing decision is ADR-0008: production design §2.4 is a veto-strength commitment ("same inputs → same Transform bytes"); hedged-race composition would break it because scheduler noise could pick a different result across runs. The story therefore prescribes (a) bounded concurrency via `asyncio.Semaphore`, (b) serial fallback (primary completes, then if-and-only-if `Degraded`/`Unavailable` AND `fallback is not None` the fallback fires), (c) a property test of 100 Hypothesis runs proving byte-identical Bundle output.

Downstream: S3-05 wraps the `Bundle` in a BLAKE3 content-addressed cache (key includes `vuln_index.digest` — ADR-0008's other half); S6-01 owns the `EventLog` that consumes the emitter seam; S7-02 wires the production adapters to the `composed_dispatch` table.

## Stage 1 — Context Loader

Documents read:

- The story itself (261 lines pre-validation).
- `docs/phases/03-vuln-deterministic-recipe/ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md` (Decision, Tradeoffs, Pattern fit, Consequences).
- `docs/phases/03-vuln-deterministic-recipe/phase-arch-design.md` §C7 BundleBuilder, §Goals G4 + G8, §Patterns rejected "No hedged-race in BundleBuilder", §Edge cases.
- `docs/phases/03-vuln-deterministic-recipe/ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` (sum-type discipline, `match` + `assert_never`).
- `src/codegenie/adapters/confidence.py` — actual `AdapterConfidence` shape.
- `src/codegenie/adapters/protocols.py` — actual adapter method surfaces.
- `src/codegenie/errors.py` — `CodegenieError` base.
- `src/codegenie/transforms/_forward.py` — `SandboxedPath` alias.
- `docs/phases/03-vuln-deterministic-recipe/stories/S3-01-tccm-context-query-models.md` + its validation report (`TCCMParseError` precedent).
- `CLAUDE.md` — Extension by addition, Functional core / imperative shell, Newtype identifiers, no raw `dict[str, Any]`.

## Stage 2 — four critics in parallel

### Coverage critic — 12 findings

| # | Tag | Issue | Resolution |
|---|---|---|---|
| F1 | harden | Empty TCCM bands not pinned | AC-26 added |
| F2 | harden | `os.cpu_count() is None` not pinned | AC-10 added |
| F3 | block | `args_canonical` format unverified | AC-13 added with literal-string assertion |
| F4 | harden | Adapter raising — undefined behavior | AC-20 added |
| F5 | harden | `event_emitter` raising — undefined | AC-21 added (fail-loud) |
| F6 | harden | Per-call semaphore unpinned | AC-11 added with two-build test |
| F7 | harden | Entry order = task order, not completion | AC-12 strengthened |
| F8 | harden | Env var edge cases (`""`, `"  "`, `"3.5"`, `"0x4"`, …) | AC-9 parametrized |
| F9 | harden | Determinism test needs scheduler entropy | AC-22 + AC-23 (xfail meta-test) |
| F10 | nit | AST static test too narrow | AC-27 widened to positive allowlist |
| F11 | harden | `AdapterDegradedEvent.reason` source unspecified | AC-19 pins `reason = primary.confidence.reason` |
| F12 | harden | Pydantic `model_dump_json()` round-trip stability | AC-25 added |

### Test-Quality critic — 8 findings

| # | Tag | Issue | Resolution |
|---|---|---|---|
| TQ1 | block | `AdapterConfidence.High` does not exist — tests fail at import | All references replaced with `Trusted` |
| TQ2 | block | Order-equality test cannot prove "no hedged-race" without forced yield + index-based check | TDD plan rewritten: shared `order` log, index-comparison assertions, jitter rng |
| TQ3 | harden | Determinism property without scheduler entropy is tautological | AC-22 injects seeded jitter; AC-23 `xfail(strict=True)` against broken reference proves bite |
| TQ4 | harden | AST defense too narrow (only `gather` substring "fallback") | AC-27 widened to `gather/wait/as_completed/TaskGroup` inside `_resolve_chain` + positive single-dispatch-site check |
| TQ5 | harden | Per-call semaphore claim untested | AC-11 mandates two-concurrent-builds test |
| TQ6 | harden | Recursion at depth ≥ 2 untested | AC-18 (3-deep chain test) + AC-17 boundary (depth 4 vs 5) |
| TQ7 | nit | `os.cpu_count() is None` flagged in Notes only | AC-10 elevated |
| TQ8 | nit | `args_canonical` not regression-tested | AC-13 includes insertion-order-independence test |

### Consistency critic — 14 findings

| # | Tag | Issue | Resolution |
|---|---|---|---|
| C1 | block | `AdapterConfidence.High` does not exist; actual variants `Trusted \| Degraded \| Unavailable` | Rewrote everywhere |
| C2 | block | `confidence in {Degraded, Unavailable}` checks class identity, always False | Replaced with `match` + `assert_never` (AC-14) |
| C3 | harden | `AdapterDegradedEvent.reason` source unspecified | AC-19 pins propagation from `primary.confidence.reason` |
| C4 | harden | `cache_dir: Path` vs arch §C7's `SandboxedPath` | AC-8 changed to `SandboxedPath` (imported from `codegenie.transforms._forward`); `__annotations__` test pins it |
| C5 | harden | `BundleBuilderError(CodegenieError)` markers-only contradicts `.reason` reads | AC-2 redesigned as frozen Pydantic `BaseModel` + thin `BundleBuilderRaise(CodegenieError)` exception wrapper (mirrors S3-01's `TCCMParseError` precedent) |
| C6 | nit | `vuln_index.digest()` vs `vuln_index.digest` form inconsistency | Pinned to `vuln_index.digest` (attribute), per S3-03's `BlobDigest` shape |
| C7 | block | `composed_adapters[primitive].query(args)` — no `.query` method on Phase 2 protocols | Introduced typed `AdapterDispatch = Callable[[ContextQuery], Awaitable[AdapterResult]]` + `composed_dispatch` dict (AC-3, AC-4); production wiring deferred to S7-02 |
| C8 | harden | `Adapter` union type undefined | Resolved by F7: `AdapterDispatch` callable, no `Adapter` sum type needed at this layer |
| C9 | block | `.confidence` attribute vs `.confidence()` method | Resolved by F7: `AdapterDispatch` returns `AdapterResult` with `.confidence: AdapterConfidence` field (attribute), bridging Phase 2's method surface; production adapter wrappers (S7-02) call `adapter.confidence()` and pack into `AdapterResult` |
| C10 | nit | `tests/property/plugins/` subdir doesn't exist | Corrected to flat `tests/property/` (Rule 11) |
| C11 | harden | `plugin_id` source typing unverified | Noted in story; trace to S2-02 left as cross-check during execution |
| C12 | nit | Goal trace — per-call semaphore not in any AC | AC-11 closes |
| C13 | nit | Module docstring AC unenforced | AC-1 + static test `test_bundle_module_docstring.py` |
| C14 | nit | `args_canonical` canonicalization not consolidated with S3-01's `model_dump_json` path | Documented in Notes — S3-01 canonicalizes `ContextQuery` for its own cache concerns; S3-04 canonicalizes `ContextQuery.args` separately (per-entry granularity); S3-05 may consolidate |

### Design-Patterns critic — 10 findings

| # | Tag | Issue | Resolution |
|---|---|---|---|
| DP1 | harden | Primitive obsession on `args_canonical: str` | Noted as `CanonicalArgsJson` newtype opportunity; deferred to S3-05 (rule-of-three not yet met for THIS phase) — flagged in Out-of-scope + Notes-for-implementer |
| DP2 | block | Set-membership defeats sum-type discipline | AC-14 mandates `match` + `assert_never` with static AST test |
| DP3 | block | Semaphore inside recursive `_run_one` halves effective concurrency on degraded chains | AC-16 lifts semaphore acquisition to `_acquire_then_dispatch`; `_resolve_chain` never reacquires; iterative not recursive |
| DP4 | harden | Recursive `_run_one` is wrong shape | Resolved by DP3: iterative `_resolve_chain` |
| DP5 | harden | `Callable[[AdapterDegradedEvent], None]` lock-in | AC-7 introduces `BundleBuilderEvent` tagged union; emitter typed as `Callable[[BundleBuilderEvent], None]` (rule-of-three met: `AdapterDegraded` + `FallbackChainTooDeep` ship here, S6-04 adds cancellation later) |
| DP6 | harden | AST defense narrow | AC-27 widened (positive allowlist + single-dispatch-site assertion) |
| DP7 | nit | Module-global `_DEFAULT_CONCURRENCY_BOUND` is hidden state | AC-9 replaces with pure `_read_concurrency_bound()` |
| DP8 | nit | `AdapterDegradedEvent` placement (S6-01 ownership) | Notes-for-implementer pins: define here now; S6-01 re-exports |
| DP9 | harden | `cache_dir: Path` vs `SandboxedPath` | Resolved by C4 |
| DP10 | nit | Pure `_compose_entry` extraction | AC-28 + AST test in AC-27 (c) |

## Stage 3 — researcher

**Not invoked.** No critic finding tagged `NEEDS RESEARCH`. The strongest non-obvious technique applied — the `xfail(strict=True)` meta-test against a deliberately-broken hedged-race reference to prove the determinism property has bite — is canonical mutation-testing methodology and is referenced inline (AC-23 explanation).

## Stage 4 — synthesizer + editor

Conflict resolution applied per priority `Consistency > Coverage > Test-Quality > Design-Patterns`:

- **C1/C2 (AdapterConfidence shape)** dominate everything else — the story was literally unimplementable as written.
- **C5 (BundleBuilderError shape)** reused S3-01's HARDENED precedent (Pydantic BaseModel + `Literal` reason + thin `BundleBuilderRaise` exception wrapper).
- **DP3 (semaphore scope)** was an internal-correctness bug that the recursion + acquisition pattern would have silently produced; resolved by AC-16's explicit "semaphore acquired exactly once per top-level band-level task" invariant.
- **DP1 (CanonicalArgsJson newtype)** was the only Design-Patterns finding *not* elevated to an AC: rule-of-three not met within Phase 3 today (S3-04 is the first user; S3-05 is the second; nothing else in the phase). Surfaced in Notes + Out-of-scope so a future contributor knows the seam exists.

Story edits applied in-place:

- **Header:** `Status: Ready` → `Status: HARDENED`. ADRs honored list expanded with ADR-0010 (sum-type discipline) and ADR-0011 (honest framing / `SandboxedPath`).
- **Validation notes block:** Added under header summarizing every change.
- **Context:** Updated to reference the tagged-union shape correctly + introduce `AdapterDispatch`/`AdapterResult` + scheduler-jitter wording.
- **References:** Pointed at `confidence.py` + `protocols.py` with the actual variant names and method names; added `SandboxedPath` + `errors.py` pointers; added S3-01 validation-report reference for the BundleBuilderError precedent.
- **Goal:** Strengthened — per-call semaphore explicit, `AdapterDegraded.reason` propagation, seeded scheduler jitter.
- **Acceptance criteria:** Rewritten from 12 unnumbered bullets into 31 numbered ACs grouped by concern (Module + types, Constructor + concurrency, Iteration order, Fallback semantics, Event hand-off, Error propagation, Property tests, Empty bands + structural defenses, Gate).
- **Implementation outline:** Rewritten — explicit imports list, no module-global concurrency bound, iterative `_resolve_chain`, pure `_compose_entry`, `_acquire_then_dispatch` boundary, full event taxonomy.
- **TDD plan — red:** Rewritten — every test snippet now imports the correct names (`Trusted`, `Degraded`, `Unavailable`, `AdapterResult`, `BundleBuilderRaise`); spy adapters return `AdapterResult` instances; tests for env-var parametrization, per-call semaphore, two-level fallback, depth boundaries, error propagation, empty bands, and pure `_compose_entry` are explicit.
- **TDD plan — refactor:** Trimmed (most refactor-list items were promoted to ACs).
- **Files to touch:** Expanded — three new static tests, conftest, hedged-race reference fixture, flat property-test layout.
- **Out of scope:** Added `composed_dispatch` construction, real adapter wiring details, `CanonicalArgsJson` deferral note.
- **Notes for the implementer:** Substantially expanded — concrete guidance on each of the load-bearing invariants (sum-type dispatch, semaphore scope, iterative chain, pure `_compose_entry`, event placement, fail-loud emitter, SandboxedPath import).

## Verdict — HARDENED

The story is now ready for `phase-story-executor`. Every blocker became a typed AC; every harden-level finding became a typed AC or a Notes paragraph; every nit was either elevated or deferred with explicit reasoning. The four veto-strength invariants (no hedged-race, sum-type dispatch, per-call semaphore, fail-loud event emitter) each have at least one AC plus at least one structural / property-based defense.

Open cross-phase items the executor should surface if encountered:

1. **`PluginId` typing on `resolution.plugin.manifest.name`** — verify S2-02 ships `name: PluginId`. If `str`, surface for S2-02 cleanup.
2. **`vuln_index.digest`** as an attribute on the S3-03 `VulnIndex` model — verify S3-03 exposes it as a property returning `BlobDigest`.
3. **`composed_dispatch` schema** — S7-02 must build this. If S7-02 isn't ready when this story lands, document a stub for production paths (tests are unaffected — they construct dispatch tables directly).
