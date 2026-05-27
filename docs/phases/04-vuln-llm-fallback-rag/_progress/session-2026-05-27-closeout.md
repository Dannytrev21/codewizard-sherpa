# Phase-4 session closeout — 2026-05-27 (phase-story-executor)

This artifact records the Phase-4 forward progress from one extended
phase-story-executor session, plus the structural residual gap that
cannot be closed by additional executor turns alone.

## Commits shipped this session (Phase-4 + unblock work)

| Commit | Story / Scope | Net result |
|---|---|---|
| `1a52552` | S6-08 | AttemptAnchor Pydantic model + JSONL anchor_writer (0o700 dir / 0o600 file / O_APPEND + fsync) + refusal-path emission in `FallbackTier.run` + 3 fence tests (schema-version, plan-kind ↔ PlanProposal, terminal-event AST walk). 30+ tests; **GREEN-partial** (AC-ORDER-1 strict-form `index 10 of 11` deferred until S6-01 GREEN-complete). |
| `7776f08` | S6-02 | Retry-bypass branch + `RagSkippedOnRetry` typed event + `select_retry_summary` pure functional-core helper + 3 AST fences (no-fence-in-tier, no-pre-truncate, no-bool-on-PromptBuilder) + `tests/fixtures/adr_links.py` single-source-of-truth + resolve-fence + 4 stale-ADR-ref patches in phase-arch-design.md. 27 tests; **GREEN-partial**. |
| `7ab2afb` | S7-04 | `phase4-config.yaml` + plugin-local `Phase4Config` Pydantic model + tagged-union `Phase4ConfigError` + `load_phase4_config(...) -> Result` loader + 9-named-validator Specification table (12 rules) + two skill templates (`vuln-major-bump.md`, `leaf-llm-instruction.md`) + `tests/_constants/phase4_defaults.py` SSOT. 34 tests; **GREEN-partial** (AC-2/8a/8b BLOCKED on Phase-3 S7-01's `plugin.yaml` + `api.py`, AC-8c surfaced Rule-7 conflict — BandClassifier+LlmInvocationGuard carry arch-literal defaults). |
| `1b7b6e9` | S6-03 | **Attempt #2 — fully Done.** Closed deferred AC-8 (idempotence pre-check) + AC-15 (Hypothesis mutex property). Added 6th `SolvedExampleStore` Protocol method `contains(sid) -> bool` + ChromaPersistentStore impl + Protocol fence test (5→6 members). Wired idempotence pre-check into `FallbackTier.on_validated` between confidence-gate and capability mint per AC-7 dispatch order. 4 idempotence tests + 2 mutex-property tests; 264 tests across S6-03 + rag surface green. **All AC-1..AC-15 closed.** |
| `2e054d4` | S7-10 | Attempt #2 — AC-9 (`FallbackTierCallable` Protocol + fixture instance), AC-10 (behavior test), AC-15 (`mkdocs build --strict` clean). 6 fixture-behavior tests; Rule-7 surface (story spec says `RecipeApplication`, shipped contract is `PlanOutcome`). |
| `3739d14` | S7-09 | partial — typed corpus models (`InjectionPayload`/`RedTeamScenario`/`TruncationProbe`, frozen+extra=forbid) + `load_corpus(name)` loader kernel + 14-row injection corpus seed + 10 model-rejection + load-kernel tests. **AC-10 + AC-11 foundation.** |
| `8697761` | S7-09 | partial — corpus expansion 14→50 unique typed rows (OWASP LLM Top 10, garak, arxiv homoglyph attacks, base64/hex/URL-encoded obfuscation, fence-tag forgery, role-override, prompt-leak, indirect-injection, tool-call forgery, AC-13 deliberate delimiter-backstop row). 15 meta-tests covering AC-9/12/13 (corpus size + source-attribution shape + id+text uniqueness + delimiter-backstop presence). |
| `5e5826d` | S7-05 | partial — Phase-4-local typed `Phase4FixtureSpec` portfolio manifest (5 rows: express-cve-2026-1234, lodash-cve-2026-9876, glibc-on-node, express-rerun, cassette-attempt-1-fails-attempt-2-passes) + `glibc-on-node/` fixture directory (Dockerfile FROM node:20-bullseye, package.json, index.js) + `by_name`/`by_category`/`by_consumer_story` lookup helpers + 19 manifest tests + 1 loud-skip enumerating deferred directories. **Rule-7 surface:** Phase-3 S8-01's `tests/fixtures/repos/_portfolio.py` doesn't exist on master; shadow manifest merges additively when S8-01 lands. |
| `939df6d` | **Phase-3 S6-06 (minimal)** | **Block-unblock work.** Authored from Phase-4 executor as Rule-8 reach-across: shipped `tests/integration/test_phase5_contract_snapshot.py` + `tests/golden/phase5-contract/snapshot.json` + `PHASE5_CONTRACT_GOLDEN_REWRITE=1` env-var regen path so Phase-4 S7-10 AC-1..AC-8 could extend the file in place. Captures 6 of S6-06's 7 named symbols (RemediationReport, TrustSignal, TrustOutcome, AttemptSummary, StageOutcome, TrustScorer) + loud-skips RemediationOrchestrator with `_missing_from_canonical_reexport` block. |
| `9e1ccbf` | S7-10 | Attempt #3 — used the freshly-shipped scaffold to land **AC-1 + AC-2 + AC-3 + AC-4 + AC-6 + AC-7 + AC-17**. Five Phase-4 captures (`FallbackTier.run`, `FallbackTier.on_validated`, `LlmInvocationGuard.running_total`, `FenceWrapper.fence`, `SolvedExampleWriteCapability` + mint_factory sub-pin per AC-4) + 4 PHASE 5 CANNOT SHIP mutation-guard tests + determinism property over Phase-4 captures. Golden refreshed. |
| `07cbd1c` | S7-10 | **Attempt #4 — 17 of 18 ACs Done.** Closed remaining AC-5 mutation guards (running_total return-annotation pin + cassettes.lock format-pinning module presence) + AC-8 (module docstring extension naming Phase 4 + citing ADRs 0002/0009/0010/0013/0014). Only AC-18 (registry-count fence) remains, BLOCKED on Phase-3 S6-06's `@register_snapshot_kind` + `@register_delta_rule` registries shipping. |

Plus 3 CI fixes (`faa0569`, `59931d4`, `336407c`) that unblocked the master CI: ruff UP012 in `tests/adv/phase04/test_injection_corpus_seed.py`, withdrawn `MAL-2026-4750` fastapi advisory ignore (with documented `ignoreUntil` expiry), serial test-aggregator timeout bump 15→20 min.

## Phase-4 story-by-story state after this session

| Story | Status flip | Done ACs | Remaining |
|---|---|---|---|
| **S6-03** | HARDENED → **Done** | AC-1..AC-15 (all) | — |
| **S6-08** | HARDENED → GREEN-partial | 30+ of ~32 | AC-ORDER-1 strict "index 10 of 11" — tied to S6-01 GREEN-complete |
| **S6-02** | HARDENED → GREEN-partial | ~10 of 15 | 10-event tape + cassette integration + canary-fires-past-truncation — tied to S6-01 GREEN-complete |
| **S7-04** | HARDENED → GREEN-partial | 9 of 13 | AC-2 (api.py + tsc external_tools) BLOCKED on Phase-3 S7-01's plugin.yaml; AC-8a/8b runtime witness BLOCKED on same; AC-8c half surfaced as Rule-7 conflict (S5-02 + S2-05 carry arch-literal defaults — out of S7-04's surgical scope) |
| **S7-10** | HARDENED → GREEN-partial (17/18) | AC-1..AC-17 | **AC-18** (registry-count fence) BLOCKED on Phase-3 S6-06 `@register_snapshot_kind` + `@register_delta_rule` registries |
| **S7-09** | HARDENED → partial | AC-10 + AC-11 + AC-9/12/13 (meta-tests) | 200-row corpus expansion (today: 50 rows), 50-row red-team scenarios, 6 main test files (test_injection_corpus.py, test_red_team_prompts.py, test_rag_poisoning_chain_orphan.py, test_rag_poisoning_runtime_inject.py, test_plan_path_escape.py extension, test_canary_bypass_via_truncation.py extension) — multi-session content authoring |
| **S7-05** | HARDENED → partial | manifest + 1 of 5 fixture directories | 4 fixture directories (express-cve-2026-1234 with ~80 .ts files + Jest suite; lodash-cve-2026-9876; express-rerun with seeded RAG records keyed on `codegenie.rag.embeddings.MODEL_DIGEST`; cassette-attempt-1-fails-attempt-2-passes with two cassette stubs) — multi-session content authoring |
| **S6-07** | HARDENED | — | Cassette-replay determinism property — BLOCKED on cassette recording authorization (`make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1`) |
| **S7-06** | HARDENED | — | E2E breaking-change — BLOCKED on S7-05 fixture content + cassette recording authorization |
| **S7-07** | HARDENED | — | E2E replay-lands-RAG — BLOCKED on S7-05 + cassette recording authorization |
| **S7-03** | HARDENED (BLOCKED) | — | vuln-provenance adapter — BLOCKED on upstream Phase-3 provenance adapter completion |
| **S6-01** | GREEN-partial (pre-session) | structural contract pinned | Full 9-step dispatch (provenance → budget-precheck → retrieval → prompt → precharge → invoke → reconcile → transform) — multi-session core implementation |

**Net Phase-4 forward delta:** 6 stories advanced from HARDENED → GREEN-partial-or-better (S6-08, S6-02, S7-04, S6-03 fully Done, S7-10 17-of-18-Done, S7-09 + S7-05 partial); 4 stories carry documented external/multi-session blockers (S6-07, S7-06, S7-07, S7-03); 1 story (S6-01) needs multi-session full-dispatch implementation.

## The three structural residual blockers (cannot be closed by more executor turns)

1. **Cassette-recording token-spend authorization.** S6-07/S7-06/S7-07 each need Anthropic API calls recorded by `make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1`, which spends real tokens. The CODEOWNERS-gated cassette-steward workflow described in `docs/operations/cassettes.md` (which shipped here in S7-10 Attempt #1) is the operator-facing path; the executor cannot self-authorize this spend.
2. **Multi-session content authoring.** S7-05's `express-cve-2026-1234` fixture needs ~80 hand-authored TypeScript source files + ~120 Jest tests + a runnable npm scripts surface + a real CVE-2026-1234-shaped vulnerability that `tsc --noEmit` will surface. S7-09 needs the injection corpus expanded from 50 → 200 attributable payloads sourced from OWASP / arxiv / garak / Llama Guard + a 50-row red-team scenario corpus. Neither decomposes cleanly into small executor commits; both need a dedicated session focused on real content authoring.
3. **Upstream Phase-3 work.** S7-10 AC-18 needs S6-06's `@register_snapshot_kind` + `@register_delta_rule` registries shipping. S7-04 AC-2/8a/8b needs Phase-3 S7-01's kernel `plugin.yaml` + `api.py` shipping. S7-03 needs the Phase-3 provenance adapter completing its seven-variant classification. These are Phase-3 territory, not Phase-4 executor work.

## What unlocks Phase-4 completion

A focused next session of any of these unblocks the corresponding stories:

* `make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1` (operator action) → unblocks S6-07/S7-06/S7-07.
* Phase-3 S6-06 GREEN-complete + Phase-3 S7-01 plugin.yaml + Phase-3 provenance adapter — three Phase-3 stories that together unblock S7-10 AC-18 + S7-04 AC-2/8a/8b + S7-03.
* A dedicated S7-05 fixture-authoring session for the express-cve-2026-1234 + lodash-cve-2026-9876 + express-rerun + cassette-attempt-1-fails-attempt-2-passes content.
* A dedicated S7-09 corpus-expansion session for the 150 additional injection payloads + 50 red-team scenarios.

The executor has now exhausted the in-scope addressable surface for Phase 4 this session. Further phase-story-executor turns on the same stop-hook condition will not change the residual-gap landscape — the next concrete forward step is one of the four bullets above.
