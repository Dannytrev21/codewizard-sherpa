# ADR-0005: Per-case `cassette_canary_pin` + Phase 4 `Canary.mint(seed=...)` additive amendment

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** cassettes · determinism · phase-4-amendment · cross-phase-boundary
**Related:** [ADR-0001](0001-rubric-execution-isolation-via-subprocess.md), [Phase 5 ADR-0016](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md)

## Context

Phase 4 ships cassette-based replay for LLM interactions: `pytest-recording` keyed on `(model_id, sdk_minor, prompt_template_hash, canary_seed)`. Phase 4 also ships a canary defense — `Canary.mint()` generates a 32-byte random token injected into the system prompt; the output validator's `canary_echo` check verifies the model did not echo the token. The canary is a defense against prompt-injection attacks where the model spills the system prompt verbatim.

The critic identified the load-bearing collision (critic shared blind spot #1): byte-for-byte cassette replay requires the canary to be *the same byte sequence* on every replay; the canary defense in production requires the canary to be *different* per invocation. All three Phase 6.5 input designs were silent on this — and silence here is failure: the bench either (a) regenerates cassettes every run because the canary differs (which collapses "no live LLM in CI"), or (b) uses a fixed production canary (which silently disables the prompt-injection defense across the bench corpus).

The eval harness lives downstream of Phase 4; Phase 4 is shipped. The synthesis must reach across the phase boundary to make this work, and any change to Phase 4's `Canary.mint` is an [ADR amendment to Phase 4](../../04-vuln-llm-fallback-rag/final-design.md). The constraint is "additive only" — no production caller passes a `seed` today, and the field's default must preserve current behavior. The cassette key already includes `canary_seed` (per Phase 4's cassette-key shape), so the seed is already a recognized dimension of cassette identity; the missing piece is a way for the bench harness to *pin* the seed per case.

## Options considered

- **Fixed-canary mode in bench** (no Phase 4 change). The bench monkey-patches `Canary.mint` to return a constant. Defeats the canary defense across the bench corpus; bench scores would diverge from production behavior. Rejected.
- **Live LLM regeneration on every cassette miss** (no Phase 4 change). The bench accepts cassette regeneration each run, paying live LLM cost. Violates `--record-mode=none` discipline and "$0.00 per CI run" (`final-design.md §Goals`). Rejected.
- **`Canary.mint(seed: bytes | None = None)` additive kwarg** + per-case `cassette_canary_pin` field on `BenchCase`. Production callers continue to pass nothing (random canary, unchanged). The bench runner injects `seed=bytes.fromhex(case.cassette_canary_pin)` for the duration of one SUT invocation via a thread-local. The cassette key includes `canary_seed`, so per-case pinned canaries disambiguate cleanly. The output validator's `canary_echo` check is unchanged (deterministic seed → deterministic canary string → check still passes).

## Decision

`BenchCase` carries a required `cassette_canary_pin: str` field (32 hex characters; one per case, pinned at curation time). Phase 4's `Canary.mint(...)` is amended additively to accept an optional `seed: bytes | None = None` kwarg; when `None`, behavior is unchanged (cryptographically random 32-byte token). `src/codegenie/eval/canary.py` exposes a `with_pinned_canary(case)` context manager that thread-locally pins the seed for the duration of one `SUT.ainvoke(case)` call. The Phase 4 amendment is a separate ADR (`ADR-P4-006`) drafted as part of Phase 6.5 work; the code diff is one optional kwarg + tests in Phase 4, plus the bench-side shim.

## Tradeoffs

| Gain | Cost |
|---|---|
| Byte-for-byte cassette replay is achievable across bench reruns — `cache_key` composition includes the pin, so identical inputs produce identical scores | Phase 4 ships an ADR amendment (`ADR-P4-006`); even though additive, it crosses a phase boundary and must be reviewed by Phase 4 CODEOWNERS |
| Production canary defense is structurally unchanged — `Canary.mint()` with no seed continues to mint a cryptographically random token; only bench callers pass `seed=...` | The thread-local injection is implementation detail that future async-refactors must respect; an `asyncio.Task` move that loses thread-local context would silently break determinism |
| Cassette key already includes `canary_seed`, so per-case pinned canaries land in distinct cassette files — no collision risk between bench cassettes and production cassettes | The `case.toml#cassette_canary_pin` field is mandatory; missing pins fail at `BenchCase` Pydantic construction (fail loud at load time), but the curator workflow must include "generate a pin" as a step |
| The output validator's `canary_echo` check passes uniformly — deterministic seed → deterministic canary string → check still detects prompt-injection in bench just as in production | Bench cases share the canary-echo *test*, but the *injected token* is per-case; if a future Phase 4 change makes the canary value visible to the rubric, the rubric would need its own per-case awareness |
| Cassette key collision between a bench `cassette_canary_pin` and a real production canary has 2^-128 probability (BLAKE3 / SHA-256 collision floor); Phase 4's `--record-mode=none` discipline catches anything that slips | The mathematical floor is reassuring but is not a *guarantee*; an operator who hand-edits a cassette key could cause confusion |

## Consequences

- `BenchCase.cassette_canary_pin: str` is required, validated as 32 hex characters at Pydantic construction.
- `src/codegenie/eval/canary.py` exposes `with_pinned_canary(case: BenchCase) -> ContextManager[bytes]` — a thread-local shim around Phase 4's `Canary.mint(seed=bytes.fromhex(case.cassette_canary_pin))`.
- Phase 4 ships **`ADR-P4-006-canary-seed-kwarg.md`** as part of Phase 6.5 work: documents the seed kwarg, asserts the production canary path is unchanged when seed is `None`, adds `tests/canary/test_seed_kwarg_deterministic.py` proving `Canary.mint(seed=b'\x00' * 32)` is deterministic across calls.
- `src/codegenie/eval/cache.py` cache-key composition includes `case.cassette_canary_pin` — a curator who edits the pin invalidates only that case's cache entry, not the whole corpus.
- A real production canary cannot collide with a bench pin (2^-128 floor); the cassette key composition makes bench cassettes and production cassettes live at distinct keys in `tests/cassettes/`.
- `tests/unit/test_canary_seed.py` asserts deterministic minting across multiple calls with the same seed; `tests/integration/test_phase4_cassette_replay_canary.py` asserts byte-identical `run_id` across two runs of the same case.
- The curator scaffold tool (`scripts/scaffold_bench_case.py`, `phase-arch-design.md §Open question #8`) generates a fresh pin (`os.urandom(32).hex()`) as part of "create new bench case" — the pin is curated-once, never rotated, durable across the case's lifetime.
- The `case_digest` (BLAKE3 over the case directory) intentionally **excludes** `case.toml` so that a pin update is not a poisoning event; the pin is identity, not content.
- If a future Phase 4 change adds the canary value to the LLM's *output* by design (e.g., echo-mode for explicit attestation), the rubric will see a deterministic string per case — rubrics must avoid depending on its value (the canary is not semantic data).

## Reversibility

**Medium.** Reverting the `Canary.mint(seed=...)` kwarg would require either (a) regenerating every bench cassette under random canary at live LLM cost — practical only at low corpus size, immediately infeasible at portfolio scale; or (b) accepting a permanent "no canary in bench" mode and disabling `canary_echo` for bench paths. Both lose evidence comparability across the audit chain. The Phase 4 amendment is the more durable path; reverting it would force a redesign of bench/production cassette sharing. The bench-side `with_pinned_canary` shim is mechanically easy to delete; the Phase 4 kwarg is the load-bearing externality.

## Evidence / sources

- [final-design.md §Canary-token handling](../final-design.md#canary-token-handling)
- [final-design.md §Departures from all three inputs #7](../final-design.md#departures-from-all-three-inputs)
- [final-design.md §Risks #4](../final-design.md#risks-top-5)
- [final-design.md §Shared blind spots considered #1](../final-design.md#shared-blind-spots-considered)
- [phase-arch-design.md §Component design — `canary.py`](../phase-arch-design.md#srccodegenieevalcanarypy)
- [phase-arch-design.md §Edge cases #6](../phase-arch-design.md#edge-cases)
- [critique.md §"Roadmap-level critiques" #2](../critique.md#roadmap-level-critiques) ("earlier-phase reliance not actually established")
- Phase 4 final design — cassette key shape `(model_id, sdk_minor, prompt_template_hash, canary_seed)`
- `ADR-P4-006-canary-seed-kwarg.md` (to be drafted; Phase 4 amendment shipped as part of Phase 6.5)
