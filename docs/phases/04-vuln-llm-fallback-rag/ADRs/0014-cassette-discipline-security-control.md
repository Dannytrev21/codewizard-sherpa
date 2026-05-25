# ADR-0014: Cassette discipline as a security control — `CassetteSanitizer` + `cassettes.lock` + nightly drift job

**Status:** Accepted
**Date:** 2026-05-18
**Tags:** ci-enforcement · supply-chain · test-determinism · nightly-canary · content-addressed-manifest
**Related:** ADR-0005 (this phase) · ADR-0007 (this phase)

## Context

Phase 4's CI runs LLM-touching tests via `pytest-recording` cassettes (`pytest --record-mode=none`). The cassette layer has two correctness dimensions:

1. **Secret hygiene.** `pytest-recording` records `Authorization` headers verbatim by default. A contributor recording cassettes locally leaks their Anthropic API key into `tests/cassettes/`. The security design ships a sanitizer; performance lens missed it entirely (`critique.md §"Things this design missed"`).
2. **Cassette-vs-reality drift.** Cassettes solve CI determinism but mask SDK upgrades, API shape changes, and prompt-vs-response semantic drift. All three lenses treated cassettes as if they solved the determinism problem completely; the critic correctly flagged this as a shared blind spot (`critique.md §"Where do all three quietly agree"` item 3).

Phase 6.5's bench harness will read per-case cassette hashes for replay-quality verification — but only one design (performance) committed to shipping a `cassettes.lock` BLAKE3 manifest.

The honest framing: cassettes are checked-in source code with the same review discipline source code gets. Sanitization is the secret-hygiene control; the manifest is the integrity control; the nightly drift job is the cassette-vs-reality canary.

## Options considered

- **`record_mode="none"` only, no sanitizer** (performance lens, default). Cassettes record raw headers including secrets. **Pattern:** Trust-the-contributor. One leaked key per careless `pytest --record-mode=all` run.
- **Header scrubbing on record** (best-practices lens, partial). Strip `Authorization`, `x-api-key`, `anthropic-version` headers. **Pattern:** Sanitize at record. Closes header-leak hole; doesn't catch body-shaped secrets or cassette-vs-reality drift.
- **Sanitize-on-record + CI scanner + content-addressed manifest + nightly drift job** (synthesis composite). `pytest-recording before_record_request/response` hooks strip headers; body-scan for `sk-ant-*`/`claude_*` tokens + 40+-char base64; CI test `tests/security/test_cassettes_clean.py` rejects any leakage; `cassettes.lock` BLAKE3 per cassette; nightly real-API CI job flags drift. **Pattern:** Layered control (sanitize + manifest + canary).

## Decision

Phase 4 ships the full layered control:

- **Sanitize at record:** `pytest-recording` `before_record_request/response` hooks strip `Authorization`, `X-API-Key`, `Cookie`, `Set-Cookie`, `anthropic-version` headers; body scans for `sk-ant-*` / `claude_*` patterns and 40+-char base64-shaped header values.
- **CI security scanner:** `tests/security/test_cassettes_clean.py` walks `tests/cassettes/` and fails CI on any leaked pattern (header, body, or shaped token).
- **CODEOWNERS gate:** cassette diffs require the single-human `cassette-steward` CODEOWNERS approval (per Gap 2 in `phase-arch-design.md` — the steward is one named human, not a team alias; rotation is human and quarterly via the CODEOWNERS handle).
- **Content-addressed manifest:** `tests/cassettes/anthropic/cassettes.lock` carries per-cassette BLAKE3; CI compares on-disk hashes to lock and rejects un-committed re-records.
- **Nightly drift job:** budget-capped CI job runs real Anthropic calls against a representative bench fixture and annotates drift (not workflow-blocking; cassette refresh + commit is the recovery).
- **Operator refresh path:** `make refresh-cassettes` requires explicit `--i-understand-this-spends-tokens` flag + CODEOWNERS approval.

**Pattern:** Layered control — Sanitize at record + CI scanner + Content-addressed manifest + Nightly real-API canary. The four together are the cassette-discipline contract; none is sufficient alone.

## Tradeoffs

| Gain | Cost |
|---|---|
| API key exfiltration through committed cassettes is structurally impossible (sanitizer strips before write; CI scanner is the backstop) | A real cassette refresh now requires three discrete steps: regenerate locally (`--i-understand-this-spends-tokens`), pass CI sanitizer, get CODEOWNERS approval — slower than `pytest --record-mode=all` |
| Cassette-vs-reality drift is caught by the nightly job — not in production, in CI annotation form | The nightly job *spends real tokens* (budget-capped CI key); operator manages the budget cap and reviews annotations |
| `cassettes.lock` per-case BLAKE3 is Phase 6.5's contract — bench replay knows which cassette shapes the bench result | The lock file must be updated in lockstep with cassette regeneration; mismatch fails CI; engineers must understand the regeneration workflow |
| Two correctness controls (cassette determinism + nightly drift) are honestly separated — neither claims to solve the other's job | Two failure paths to triage when something breaks; runbook (`docs/operations/cassettes.md`) documents which signal means which |
| The sanitizer + scanner pattern is reusable for Phase 6.5+ — every future LLM-touching cassette gets the same hygiene by inheritance | The denylist of secret-shaped patterns is the same denylist incompleteness as the canary corpus (ADR-0013); grows over time |
| Cassette diffs requiring CODEOWNERS approval prevents accidental "I just regenerated and pushed" PRs from landing | Contributor friction on legitimate cassette updates; mitigated by the `make refresh-cassettes` ergonomic |

## Pattern fit

This is not a textbook design pattern — it's a layered control composition. The closest toolkit fit is the "Functional core / Imperative shell" idea applied to test infrastructure: cassettes are the pure-replay core (deterministic, reviewable, content-addressed); the nightly drift job and the operator refresh workflow are the imperative shell that keeps the core true to reality.

The `cassettes.lock` is a Content-addressed manifest — same shape as `embeddings_model.lock` (ADR-0007) and `.codegenie/rag/manifest.yaml`. The pattern recurs because content-addressing is how this codebase says "this artifact's identity is its bytes."

## Consequences

- `tests/cassettes/anthropic/` is the canonical cassette directory; `cassettes.lock` lives next to it.
- `tests/security/test_cassettes_clean.py` runs in every CI build; failure = hard CI block.
- `tests/fence/test_cassette_discipline.py` asserts `CODEGENIE_LIVE_LLM` is unset in CI.
- `make refresh-cassettes` runs `pytest --record-mode=all` with sanitizer enabled; outputs require CODEOWNERS approval before merge.
- The nightly CI job is configured to run against a representative bench fixture (`fixtures/vuln-major-bump/express-cve-2026-1234/`) with a budget-capped key; annotations land as PR comments on the open drift-flag PR.
- Phase 6.5's bench harness reads `cassettes.lock` to verify cassette identity per case; the contract is "the lock matches the on-disk cassette OR Phase 6.5 reports identity drift."
- `pytest-recording` `record_mode="none"` is the CI default; cassette miss = hard fail with a diagnostic pointing to `make refresh-cassettes`.
- The sanitizer is *also* the way contributor laptops avoid local leakage — the same hooks fire in local recording.
- Future Phase 6+ tests inherit the cassette discipline by writing under `tests/cassettes/<vendor>/`; the sanitizer + scanner extend transparently.

## Reversibility

**Medium.** Disabling individual controls (e.g., removing the nightly job) is config-level; each removal loses one layer of defense. Removing the entire cassette discipline (no sanitizer, no manifest, no nightly) reverts to the "trust the contributor" state — would require a Phase-4 ADR amendment with a clear justification (e.g., a migration to a different replay mechanism). Replacing `pytest-recording` with a different cassette library lands behind the same sanitizer/scanner/manifest contract — adapter swap.

## Evidence / sources

- `../final-design.md §Component 13 — CassetteSanitizer`
- `../final-design.md §Goal "Cassette security scan in CI"`
- `../phase-arch-design.md §Component 12 — CassetteSanitizer`
- `../phase-arch-design.md §Goals — G11`
- `../critique.md §"Things this design missed"` (performance missed cassette sanitization)
- `../critique.md §"Where do all three quietly agree on something questionable"` item 3 (cassette layer "solves CI determinism")
- `roadmap.md §Phase 6.5` (bench harness reads cassette manifests)
