# Story S3-06 — `pytest-recording` cassette discipline + canary rewrite hook + cassettes-reviewed label

**Step:** Step 3 — Ship `LeafLlmAgent` implementations + `EgressProxy` + cassette discipline
**Status:** Ready
**Effort:** M
**Depends on:** S3-02 (`InProcessLeafLlmAgent` — supplies the first real LLM traffic to record)
**ADRs honored:** ADR-P4-012, ADR-P4-008, ADR-P4-007

## Context
Every LLM call in CI must replay deterministically from a recorded cassette — no live API calls, ever. Per ADR-P4-012, Phase 4 uses `pytest-recording` with `--record-mode=none` in CI, **plus** `VCR_BAN_NEW_CASSETTES=1` which turns a cassette miss into a hard failure (printing the recorded request body) so engineers cannot silently add fixtures. Cassettes are content-addressed by `blake3(canonical(system, few_shots, query))` — **the canary is NOT in the key** so canary rotation does not invalidate the corpus. A `before_record_response` hook rewrites the canary on replay so the validator's canary-echo check still passes against rotated canaries. Any change to `tests/fixtures/cassettes/**/*.yaml` requires the `cassettes-reviewed` PR label.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Testing strategy / CI gates` — `VCR_BAN_NEW_CASSETTES=1`, `cassettes-reviewed` label gate, `--record-mode=none`; `§Edge cases #10, #21` — cassette miss + golden-prompt drift on legitimate prompt edits.
- **Phase ADRs:**
  - `../ADRs/0012-vcr-cassette-discipline.md` — ADR-P4-012 — the discipline this story implements.
  - `../ADRs/0008-prompt-injection-structural-defenses.md` — ADR-P4-008 — canary semantics; rewrite hook must preserve canary-echo invariants on replay.
  - `../ADRs/0007-anthropic-model-pin-via-versioned-alias.md` — ADR-P4-007 — cassette key includes `model_id` so model bumps invalidate the corpus cleanly.
- **Source design:** `../final-design.md §Synthesis ledger row "Cassette discipline"` — content-addressed + zstd + `VCR_BAN_NEW_CASSETTES` + `cassettes-reviewed` label + nightly free-tier canary; key includes `(model_id, sdk_minor, prompt_template_hash)`.
- **High-level impl:** `../High-level-impl.md §Step 3` — `pytest-recording` bullet + cassette CI gate bullet.
- **Existing code:** `tests/conftest.py` (Step-0) — VCR config insertion point; `src/codegenie/llm/output_validator.py` (S2-01) — canary-echo check; `src/codegenie/llm/leaf_anthropic/in_process.py` (S3-02) — first consumer.

## Goal
Make every LLM-touching test in CI replay from a deterministic, canary-rotation-resilient cassette under hard-fail-on-miss discipline, with a PR-label gate guarding any cassette change.

## Acceptance criteria
- [ ] `tests/conftest.py` configures `pytest-recording`/`vcrpy` with:
  - `record_mode="none"` when env `CI=1` (or always in CI image);
  - cassette path `tests/fixtures/cassettes/<test_module>/<test_function>.yaml`;
  - `match_on` set to a custom matcher that hashes `(system_blocks_canonical, few_shots_block_canonical, query_block_canonical, model_id, sdk_minor, prompt_template_hash)` via `blake3` and uses the digest as the dispatch key — canary is **excluded** from the matcher inputs.
- [ ] `VCR_BAN_NEW_CASSETTES=1` (set by default in CI) makes a cassette miss raise loudly with the recorded request body shown in the error. Covered by `tests/unit/llm/test_cassette_miss_bans_in_ci.py`.
- [ ] `before_record_response` hook (also applied at replay) **rewrites the canary** in the recorded response body so a cassette recorded with canary `A` validates against a run that minted canary `B`. Covered by `tests/unit/llm/test_cassette_canary_rewrite.py`.
- [ ] Cassette files are deterministic on disk: canonical YAML, sorted keys, LF endings; a stable `serialize` config in `vcrpy`.
- [ ] `.github/workflows/cassettes_review.yml` (new) checks every PR: if any path under `tests/fixtures/cassettes/` is added or modified, the `cassettes-reviewed` PR label MUST be present, else the job fails. Same workflow rejects deletions without the label too.
- [ ] Existing cassettes committed by S3-01 / S3-02 / S3-03 are migrated to the new content-addressed key (one-shot migration script + commit). Document the migration command in `docs/runbooks/cassettes.md`.
- [ ] ruff, ruff format, mypy strict where applicable; pytest green; new CI workflow validated via a dry-run PR description in the runbook.

## Implementation outline
1. **VCR config (`tests/conftest.py` extension):**
   - register a custom `match_on` function `_canonical_match(req)` that:
     - parses request body JSON;
     - extracts `system`, `messages` (find few_shots block + query block by role/order convention);
     - canonicalizes (sorted keys, LF, no whitespace);
     - hashes with `blake3` including `model_id` and `prompt_template_hash` (`prompt_template_hash` extracted from a request header the agent sets, e.g. `X-Codegenie-Prompt-Hash`);
     - returns the hex digest — VCR uses this as the cassette dispatch key.
   - register `before_record_response(response)` that scans the body for `<CANARY:[a-f0-9]{64}>` (or whichever canary marker) and replaces with `<CANARY:CASSETTE_PLACEHOLDER>`; also register a replay-time wrapper that substitutes the **current run's canary** back in so `OutputValidator.canary_check` passes.
2. **`VCR_BAN_NEW_CASSETTES` enforcement:** wrap VCR's "record" fallback with a check — if env var is set, raise `CassetteNotFound(request_body_pretty)` instead of recording.
3. **Cassette path / serialization:**
   - cassette path resolver: `tests/fixtures/cassettes/<module>/<function>.yaml` (default vcrpy behavior; assert in a conftest hook).
   - serialization: `serializer="yaml"` with a custom `Dumper` that sorts keys + LF.
4. **CI label gate:**
   - `.github/workflows/cassettes_review.yml`: triggers on `pull_request` with `paths: [tests/fixtures/cassettes/**]`; uses `gh pr view --json labels` to check for `cassettes-reviewed`; fails if missing.
5. **Migration:** one-shot script `tools/cassettes/migrate_to_content_addressed.py` that re-keys existing cassettes; idempotent; documented in the runbook.
6. **Documentation:** add `docs/runbooks/cassettes.md` covering: how to record locally, how the canary-rewrite hook works, why the corpus is content-addressed, how to bump the model pin (Phase 4 cassette regen cost).

## TDD plan — red / green / refactor

### Red
Test file paths:
- `tests/unit/llm/test_cassette_miss_bans_in_ci.py`
- `tests/unit/llm/test_cassette_canary_rewrite.py`
- `tests/unit/llm/test_cassette_content_addressed_key.py`
- `tests/unit/ci/test_cassettes_reviewed_label_required.py`

```python
# test_cassette_miss_bans_in_ci.py
import pytest, os
from codegenie.testing.vcr_config import CassetteNotFound

def test_miss_fails_loudly_when_ban_env_set(monkeypatch, make_in_process_agent):
    monkeypatch.setenv("VCR_BAN_NEW_CASSETTES", "1")
    monkeypatch.setenv("CI", "1")
    agent = make_in_process_agent()
    with pytest.raises(CassetteNotFound) as exc:
        agent.invoke(make_request(system_blocks=[{"text": "novel-system-not-recorded"}]))
    assert "novel-system-not-recorded" in str(exc.value)  # request body surfaced
```

```python
# test_cassette_canary_rewrite.py
def test_canary_rotation_does_not_invalidate_cassette(make_in_process_agent, recorded_cassette_with_canary_A):
    # cassette recorded with canary "a"*64
    fresh_canary = "b" * 64
    agent = make_in_process_agent()
    resp = agent.invoke(make_request(canary_token=fresh_canary))
    # before_record_response hook substituted current canary into the recorded body
    assert resp.canary_echo == fresh_canary
    # OutputValidator's canary check passes
```

```python
# test_cassette_content_addressed_key.py
def test_match_key_is_blake3_of_canonical_system_fewshots_query_model(monkeypatch, request_factory):
    from codegenie.testing.vcr_config import canonical_match_key
    r1 = request_factory(system="X", few_shots="Y", query="Q", model="claude-sonnet-4-7-20260415", canary="a"*64)
    r2 = request_factory(system="X", few_shots="Y", query="Q", model="claude-sonnet-4-7-20260415", canary="b"*64)
    # different canary, same key
    assert canonical_match_key(r1) == canonical_match_key(r2)
    r3 = request_factory(system="X2", few_shots="Y", query="Q", model="claude-sonnet-4-7-20260415", canary="a"*64)
    assert canonical_match_key(r1) != canonical_match_key(r3)  # different system → different key
    r4 = request_factory(system="X", few_shots="Y", query="Q", model="claude-sonnet-4-7-NEW", canary="a"*64)
    assert canonical_match_key(r1) != canonical_match_key(r4)  # model bump → different key
```

```python
# test_cassettes_reviewed_label_required.py  (CI workflow simulation)
def test_cassette_change_without_label_fails(simulated_pr_with_cassette_change_no_label):
    result = run_workflow("cassettes_review.yml", pr=simulated_pr_with_cassette_change_no_label)
    assert result.conclusion == "failure"
    assert "cassettes-reviewed" in result.output

def test_cassette_change_with_label_passes(simulated_pr_with_cassette_change_with_label):
    result = run_workflow("cassettes_review.yml", pr=simulated_pr_with_cassette_change_with_label)
    assert result.conclusion == "success"
```

### Green
- Custom `match_on` + canary rewrite hook in conftest; `CassetteNotFound` raised on miss when env set; bare-bones GitHub Actions workflow doing the label gate.

### Refactor
- Extract `codegenie.testing.vcr_config` so the matcher and hooks are reusable from Phase 5 tests.
- Add a Hypothesis property test that `canonical_match_key` is invariant under JSON dict-ordering permutations of `system_blocks`.
- Add the nightly free-tier canary stub: a CI cron that records one cassette against the real API and diffs against the committed corpus (alerts on drift). Skeleton workflow only — full canary tuning lands in Step 7.
- Logging: cassette miss errors print the canonicalized request body, sorted keys, no canary, no API key.

## Files to touch
| Path | Why |
|---|---|
| `tests/conftest.py` | VCR `match_on`, `before_record_response`, `record_mode` config. |
| `src/codegenie/testing/vcr_config.py` | `canonical_match_key`, `CassetteNotFound`, canary rewrite helpers. |
| `.github/workflows/cassettes_review.yml` | New PR-label gate. |
| `tools/cassettes/migrate_to_content_addressed.py` | One-shot migration. |
| `docs/runbooks/cassettes.md` | Operator runbook. |
| `tests/unit/llm/test_cassette_miss_bans_in_ci.py` | Red. |
| `tests/unit/llm/test_cassette_canary_rewrite.py` | Red. |
| `tests/unit/llm/test_cassette_content_addressed_key.py` | Red. |
| `tests/unit/ci/test_cassettes_reviewed_label_required.py` | Red — workflow simulation. |

## Out of scope
- **Nightly real-API canary** — skeleton only here; tuning + alerting in Step 7.
- **Adversarial cassette corpus** — Step 7.
- **Cassette zstd compression** — `final-design.md` mentions zstd; ship plain YAML in Step 3 and reopen compression as a future optimization (avoid muddying the discipline change).
- **EgressProxy cassettes** — proxy is exercised via `httpx` recording in S3-04 tests, not via vcrpy.

## Notes for the implementer
1. **Canary NOT in the cassette key is the load-bearing invariant.** If the canary is in the key, every run mints a new key, every cassette misses, you re-record forever. Test `test_cassette_content_addressed_key.py` proves this — keep it green.
2. **Canary rewrite-on-replay is symmetric.** Record-time: scrub the canary to a placeholder. Replay-time: substitute the **fresh** canary into the response so `OutputValidator.canary_check` passes. Both hooks live in the same module; one without the other is a bug.
3. **`prompt_template_hash` extraction:** the in-process agent must set a request header (e.g. `X-Codegenie-Prompt-Hash`) so the matcher can read it without parsing prompt bodies twice. Coordinate with S3-02 if not already present — small addition.
4. **`VCR_BAN_NEW_CASSETTES=1` is the default for CI, never for local dev.** Local devs run `pytest --record-mode=once` to add a cassette. Document.
5. **YAML determinism.** Use `safe_dump` with `sort_keys=True` and `default_flow_style=False`; tests must assert that re-recording the same response twice produces byte-identical files.
6. **Model bump cost.** Per ADR-P4-007 a model bump invalidates the entire corpus. Add a CLI helper `tools/cassettes/regen.py --model <new>` that prints the affected count and refuses to run without `--really`. Don't ship regen automation in this story — just the warning.
7. **The label gate cannot be skipped by repo admins implicitly.** GitHub Actions runs in the PR context — make sure the workflow file lives at `.github/workflows/`, not `.claude/`, and that branch protection requires this check.
8. **No cassette in this story records real API traffic.** All cassettes in tests here use synthetic responses crafted by the test (`recorded_cassette_with_canary_A` is a fixture that writes the YAML directly, not via vcrpy record-mode). Keeps S3-06 self-contained and CI-friendly.
