# ADR-0012: VCR cassette discipline — `pytest-recording`, `--record-mode=none`, content-addressed cassette key, `cassettes-reviewed` label, nightly canary

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** testing · cassettes · ci · supply-chain · synthesizer-departure
**Related:** [ADR-0007](0007-anthropic-model-pin-via-versioned-alias.md), [ADR-0009](0009-prompts-as-versioned-yaml-data.md)

## Context

CI must run deterministically against an Anthropic-touching codebase without an API key. All three lens designs converged on `pytest-recording` + `--record-mode=none` (`final-design.md §"Synthesis ledger"` row "Cassette discipline"); the critic (`critique.md §"Where do all three quietly agree on something questionable"` #1) attacked the cassette-corpus-regen bottleneck this creates: any prompt edit (whitespace, key reordering, additional Skills loaded into the manifest) invalidates every cassette that hit that path, and the workflow becomes a single-engineer review queue.

The synthesizer's answer is a *structured cassette key* that includes `(model_id, sdk_minor, prompt_template_id, prompt_template_version)` — so a prompt bump invalidates one structured surface, not a hash of arbitrary request bytes. Plus a nightly canary against the Anthropic free tier to catch upstream shape drift before it breaks CI.

## Options considered

- **Byte-replay only.** Default `pytest-recording` behavior. Cassette key is the request body hash. Any prompt edit invalidates every affected cassette; corpus drift is opaque.
- **Mocked Anthropic SDK (no cassettes).** Replaces every API call with a fixture. Loses fidelity (cassettes catch real SDK shape drift; mocks don't). Brittle on SDK pin updates.
- **Live-Anthropic in CI.** Real API key in CI; real calls. Cost: $0.05/PR/cassette-touching test × hundreds of CI runs. Plus a non-deterministic CI failure surface.
- **`pytest-recording` + structured cassette key + nightly canary + `cassettes-reviewed` label.** Synth. Three layered defenses: structured key makes invalidations surface as YAML diffs, not body-bytes scrambles; nightly canary catches upstream drift; PR label gates human review of cassette changes.

## Decision

Adopt `pytest-recording` with `--record-mode=none` in CI; misses are hard fails with the recorded request body in the error. **Cassette key** includes a hash of `(resolved_model_id, sdk_minor, prompt_template_id, prompt_template_version)`; bumping any forces a re-record. Cassettes live at `tests/fixtures/cassettes/<test_module>/<test_function>.yaml` (zstd-compressed when corpus crosses 200 files; `phase-arch-design.md §"Open questions"` #4).

**Sanitization pre-commit hook** strips `x-api-key`, `authorization`, `cookie`, `set-cookie`; CI re-runs the sanitizer as a gate.

**`cassettes-reviewed` PR label** gates merge when any `.yaml` under `tests/fixtures/cassettes/` changes. Engineer re-records locally; PR review focuses on cassette diff.

**Nightly free-tier canary** against `api.anthropic.com` (one call against a tiny fixture). Drift in response shape → CI yellow with a Slack/email notification; humans triage. Yellow (warn), not red (block) — closes critic §B.5 ambiguity (`phase-arch-design.md §"Open questions"` #6).

**`VCR_BAN_NEW_CASSETTES=1`** in CI: a new cassette file is a hard fail; cassettes only land via the labeled-review path.

**`before_record_response` hook** rewrites the canary token on replay (the per-run random canary must not break the cassette match).

## Tradeoffs

| Gain | Cost |
|---|---|
| CI is hermetic — zero network egress; no API key required; cost-free | Cassette corpus must be maintained; every prompt edit lands as a cassette regen + label review |
| Structured cassette key (`model_id, sdk_minor, prompt_template_id, prompt_template_version`) makes legitimate bumps surface as YAML diffs, not body-bytes scrambles | The key inputs must be computed *before* the request is built; one ordering bug means cassettes miss for "valid" reasons |
| Nightly canary catches upstream Anthropic API shape drift days before it breaks CI on a random PR | Free-tier canary needs a recorded fixture + Anthropic account; mild operational burden; canary failures land as Slack notifications, not red builds |
| `cassettes-reviewed` PR label means human review focuses on the cassette diff — the load-bearing change, not the test code change | One-engineer-review-queue bottleneck is real; mitigated by the structured key making most bumps mechanical, not surprising |
| Sanitization pre-commit + CI re-run means API key bytes never enter the cassette corpus | Sanitizer must keep up with new auth header conventions; documented as a maintenance burden |
| `VCR_BAN_NEW_CASSETTES=1` means every new cassette is a deliberate act; "let me just add a quick test" hits the gate | Engineer surprise when adding tests; documented in the test-writing guide |
| `before_record_response` canary-rewrite means per-run random canaries don't break replay | The rewrite hook is one more bit of cassette machinery to maintain |

## Consequences

- CI mode: `--record-mode=none` + `VCR_BAN_NEW_CASSETTES=1`. Misses are hard fails with the recorded request body in the error message.
- Cassette path includes the structured key hash: `tests/fixtures/cassettes/<test_module>/<test_function>.<hash>.yaml`.
- Adversarial / canary cassettes (`tests/adversarial/`) are reviewed at the same bar as regular cassettes.
- Cassette regen path: engineer runs `pytest --record-mode=once` locally with a live API key; PR carries `cassettes-reviewed` label; diff is human-reviewed.
- Sanitizer pre-commit: strips `x-api-key`, `authorization`, `cookie`, `set-cookie`. CI re-runs as a gate.
- Phase 5+ may add new cassettes; the discipline doesn't change.
- The Anthropic SDK is pinned to a minor in `pyproject.toml`; an SDK minor bump triggers `sdk_minor` change in the cassette key and a full re-record (closes critic §best-practices hidden assumption #1).

## Reversibility

**Medium.** Switching to live-Anthropic-in-CI requires an API key budget + cassettes-removal. Switching to mocked SDK requires writing the mock layer and accepting fidelity loss. The structured key + label + canary triad is a coherent discipline — partial reversal weakens the whole.

## Evidence / sources

- `../final-design.md §"Synthesis ledger" §"Conflict-resolution table"` row "Cassette discipline"
- `../final-design.md §"Test plan" §"VCR cassette discipline"` — full spec
- `../phase-arch-design.md §"Testing strategy" §"VCR cassette discipline"`
- `../phase-arch-design.md §"Open questions"` #4, #6
- `../critique.md §"Where do all three quietly agree on something questionable"` #1 — cassette regen bottleneck
- `../critique.md §best-practices hidden assumption #1` — SDK shape drift
