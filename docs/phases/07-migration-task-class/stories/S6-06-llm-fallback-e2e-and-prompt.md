# Story S6-06 — Recipe-miss LLM fallback E2E + distroless prompt template

**Step:** Step 6 — Broaden coverage: adversarial Dockerfile corpus, second E2E fixture, HITL path, LLM-fallback path
**Status:** Ready
**Effort:** L
**Depends on:** S6-05
**ADRs honored:** ADR-P7-003 (`FallbackTier.run` `task_type` kwarg), ADR-P7-009 (`DistrolessLedger`), ADR-P7-006 (`Recipe.engine "dockerfile"` reused for canonicalization)

## Context

The recipe-miss → RAG-miss → LLM-fallback path is the safety net for Dockerfiles the catalog cannot handle. It's also the only path in Phase 7 that exits the deterministic substrate and crosses into Phase 4's `FallbackTier`. This story ships two artefacts together: the **prompt template** Phase 4 loads when `task_type="distroless_migration"` (`src/codegenie/planner/prompts/migration_distroless.v1.yaml` — schema-validated, version-pinned), and the **cassette-driven E2E** that exercises the full path end-to-end while asserting the $0.12 budget per G9.

The fixture is S6-05's heredoc Dockerfile (the deterministic recipe-miss trigger). RAG is forced to miss via a controlled `rag_hit.score < 0.85` condition. Phase 4 is invoked once for cassette recording, then replayed deterministically in CI via `pytest-recording`. The produced patch is a distroless-shaped Dockerfile diff that the downstream pipeline (recipe engine canonicalization → sandbox validation) processes through the same exit gates as the recipe path.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Scenarios ›Scenario 2` (lines 409–437) — recipe miss → RAG miss → Phase 4 LLM-fallback sequence diagram; the assertion shape this story implements
  - `../phase-arch-design.md §Agentic best practices ›Prompt template structure` (line 1178) — `prompts/migration_distroless.v1.yaml` is schema-validated, version-pinned, loaded by Phase 4's `PromptBuilder`
  - `../phase-arch-design.md §Testing strategy ›Integration tests ›test_migrate_recipe_miss_llm_fallback` (line 1233)
  - `../phase-arch-design.md §Goals` G9 — `$/PR ≤ $0.12` LLM-fallback budget
  - `../phase-arch-design.md §Implementation-level risks ›Step 6 risks` — "Cassette recording for the LLM-fallback E2E needs a real `anthropic` call once; cassette format drift between cassette-record and cassette-replay environments may show up"
- **Phase ADRs:**
  - `../ADRs/0004-fallback-tier-task-type-kwarg.md` — ADR-P7-003 — `FallbackTier.run(..., task_type="distroless_migration")` selects this prompt + the distroless RAG collection
- **Phase 4 prior art (the cassette pattern — read these carefully):**
  - `../../04-vuln-llm-fallback-rag/design-performance.md §VCR cassettes` (≈ line 224) — `pytest-recording` + custom matcher + `VCR_BAN_NEW_CASSETTES=1` posture
  - `../../04-vuln-llm-fallback-rag/critique.md ›cross-cutting blind spot #1` — VCR is byte-replay; any prompt-text change invalidates cassettes
  - Phase 4's existing `tests/fixtures/cassettes/` directory and matcher conventions
- **Existing code:**
  - `src/codegenie/planner/fallback_tier.py` (Phase 4 + S1-04 widening) — `task_type` kwarg routes prompt + corpus
  - `src/codegenie/planner/prompts/` (Phase 4) — existing prompt template directory; the new YAML lives here
  - `src/codegenie/graph/nodes/distroless/replan_with_phase4.py` (S5-02) — passes `task_type="distroless_migration"`
  - `tests/fixtures/repos/heredoc-buildkit-distroless/` (S6-05) — the recipe-miss trigger fixture this E2E consumes

## Goal

`tests/integration/test_migrate_recipe_miss_llm_fallback.py` runs the heredoc fixture through the full recipe-miss → RAG-miss → Phase 4 LLM-fallback path with the new `migration_distroless.v1.yaml` prompt loaded, produces a distroless-shaped Dockerfile patch, asserts cost ≤ $0.12 per G9, and replays deterministically from the recorded VCR cassette in CI.

## Acceptance criteria

- [ ] `src/codegenie/planner/prompts/migration_distroless.v1.yaml` exists. The file:
  - Has a schema-validated structure matching Phase 4's existing prompt-template schema (`prompts/_schema.json` or equivalent — look at the schema Phase 4 already ships and validate against it).
  - Declares `name: "migration_distroless"`, `version: "v1"`, `task_type: "distroless_migration"`.
  - Has a `system_block` that pins the distroless migration intent: "produce a Dockerfile diff swapping the runtime stage to a Chainguard distroless image; do not introduce shell invocations; preserve the build stage unless explicitly told otherwise".
  - Has a `few_shot_examples` section that loads from `rag/seed_corpus/distroless/` (the same corpus S6-07 seeds).
  - Has a `output_schema` that constrains the LLM output shape (Dockerfile diff format — reuse Phase 4's output validator).
- [ ] `tests/unit/planner/test_migration_distroless_prompt_template.py` exists and asserts the YAML schema-validates against Phase 4's prompt schema; asserts `version` is `"v1"` (no silent bumps).
- [ ] `tests/integration/test_migrate_recipe_miss_llm_fallback.py` exists and is green under `pytest --record-mode=none` (CI default).
- [ ] The test invokes `codegenie migrate run` on the heredoc fixture (S6-05) and asserts:
  - `recipe_selection.matched is False` (recipe miss, per S6-05).
  - `rag_hit.score < 0.85` (forced via a controlled seed or fixture-specific corpus).
  - `replan_with_phase4` was called with `task_type="distroless_migration"` (assert via captured kwargs or a structlog event).
  - `FallbackTier` selected `prompts/migration_distroless.v1.yaml` (assert via the `FallbackTierResult.prompt_template` field or an emitted `GraphEvent`).
  - The produced patch is a *distroless-shaped* Dockerfile diff — assert it touches a `FROM ... ` line whose new value matches the canonical Chainguard image regex from S5-02 / S6-02.
  - `FallbackTierResult.cost_usd ≤ 0.12` (G9). The cost is taken from the cassette's recorded token counts × the pinned model's per-token price.
  - `last_engine == "phase4_llm"`.
- [ ] A VCR cassette is recorded once and committed: `tests/fixtures/cassettes/migrate_recipe_miss_llm_fallback_<hash>.yaml.zst` (or whichever Phase 4 path/format convention). The cassette is content-addressed per Phase 4's matcher.
- [ ] CI runs with `VCR_BAN_NEW_CASSETTES=1` (Phase 4's existing posture). The test fails loudly if the cassette is missing.
- [ ] No `anthropic` import lives under `src/codegenie/{probes,transforms,recipes,catalogs}/` after this story — fence-CI continues to pass.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` clean on the new test + the prompt-template schema validator.

## Implementation outline

1. **Author the prompt template.** Read Phase 4's existing prompt-template schema and at least one of its existing templates (`prompts/vuln_remediation.v1.yaml` or similar). Clone the structure verbatim; rewrite the system block, few-shot example pointers, and output schema for distroless.
2. **Write the prompt template unit test.** Load the YAML; validate against Phase 4's schema; assert version pinning. Run; red because the YAML doesn't exist.
3. **Wire RAG miss.** S6-07 seeds the `distroless_solved_examples_promoted` collection; for *this* test, force a miss either by (a) running before S6-07 seeds (and asserting the *empty corpus* miss), or (b) using a controlled seed that produces `rag_hit.score < 0.85` on the heredoc-fixture's query. Option (b) is more durable; pick it if S6-07's corpus is set up.
4. **Record the cassette.** Run the test once locally with `pytest --record-mode=once` against the real `anthropic` API. This requires `ANTHROPIC_API_KEY` and is intentionally a one-time per engineer / per template-edit operation. Commit the cassette.
5. **Re-run with `--record-mode=none`** to confirm deterministic replay; commit the green test.
6. **Cost assertion.** Read the cassette's recorded `usage.input_tokens` and `usage.output_tokens`, multiply by the model's pinned per-token price (Phase 4's price table, version-pinned), assert ≤ $0.12.

## TDD plan — red / green / refactor

### Red — write the failing tests first

```python
# tests/unit/planner/test_migration_distroless_prompt_template.py
from pathlib import Path
import yaml
import jsonschema

PROMPT = Path("src/codegenie/planner/prompts/migration_distroless.v1.yaml")
SCHEMA = Path("src/codegenie/planner/prompts/_schema.json")

def test_migration_distroless_prompt_schema_validates():
    template = yaml.safe_load(PROMPT.read_text())
    schema = __import__("json").loads(SCHEMA.read_text())
    jsonschema.validate(template, schema)

def test_migration_distroless_prompt_version_pinned():
    template = yaml.safe_load(PROMPT.read_text())
    assert template["version"] == "v1"
    assert template["task_type"] == "distroless_migration"
```

```python
# tests/integration/test_migrate_recipe_miss_llm_fallback.py
import pytest

@pytest.mark.vcr(record_mode="none")
def test_recipe_miss_routes_through_llm_fallback_under_budget(tmp_path, snapshot_runner) -> None:
    repo = snapshot_runner.copy_fixture(HEREDOC_FIXTURE, tmp_path)
    # arrange: force RAG miss via test-mode seed; ensure cassette is on disk

    # act
    result = CliRunner().invoke(migrate, ["run", str(repo), "--target", "distroless",
                                          "--cve", "CVE-2024-FAKE"])

    # assert: clean exit, took LLM path, distroless shape, under budget
    assert result.exit_code == 0, result.output
    ledger = _read_latest_ledger(repo)
    assert ledger.recipe_selection.matched is False
    assert ledger.rag_hit.score < 0.85
    assert ledger.last_engine == "phase4_llm"

    # distroless shape on produced patch
    patch_bytes = (repo / ".codegenie" / "migration" / ledger.run_id / "patch.diff").read_bytes()
    assert b"+FROM cgr.dev/chainguard/" in patch_bytes

    # G9 budget
    assert ledger.last_attempt.cost_usd <= 0.12
```

Red surfaces: prompt YAML doesn't exist; cassette doesn't exist; `recipe_selection.matched` is `True` (oops, the fixture matched a recipe — must be a different fixture); RAG hit > 0.85 (need to force miss).

### Green — make it pass

- Author the prompt YAML.
- Record the cassette once.
- Re-run with `--record-mode=none`.
- Capture the produced ledger shape; align assertions.

### Refactor — clean up

- Pin the cassette's hash in the test (so a silent cassette-content drift fails loudly).
- Document the re-record workflow in a top-level `tests/fixtures/cassettes/README.md` if Phase 4 doesn't already have one — link Phase 4's cassette discipline (the `LABEL_REQUIRED: cassettes-reviewed` convention).
- Confirm the `migration-report.yaml` records the LLM cost in a queryable field; Phase 13 (cost ledger) consumes it.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/planner/prompts/migration_distroless.v1.yaml` | New — distroless prompt template, schema-validated |
| `tests/unit/planner/test_migration_distroless_prompt_template.py` | New — schema validation + version-pin enforcement |
| `tests/integration/test_migrate_recipe_miss_llm_fallback.py` | New — cassette-driven E2E |
| `tests/fixtures/cassettes/<hash>.yaml.zst` (or Phase 4's convention) | New — VCR cassette for the single Anthropic call |
| `tests/fixtures/cassettes/README.md` (if not exists) | Document the record / replay / re-record workflow |

## Out of scope

- **The RAG seed corpus.** S6-07 owns the `distroless_solved_examples_promoted` vector store seeding. This story forces a *miss* — it does not seed solved examples.
- **Multiple cassettes / multiple prompt iterations.** Phase 4's three-retry semantics may invoke the LLM up to three times; this story records the first invocation only. If retries fire in this fixture, expand the cassette set in a follow-up.
- **Phase 4 pricing-table changes.** The cost-per-token table is Phase 4's responsibility; this story consumes it.
- **The `task_type` kwarg on `FallbackTier.run`.** Landed in S1-04. This story uses it via S5-02's `replan_with_phase4`.
- **Distroless RAG corpus top-1 retrieval test.** S6-07 owns it.
- **Task-type-mismatch safety** (vuln advisory + distroless `task_type` → loud failure). S6-08 owns it.

## Notes for the implementer

- **Cassette recording is a one-time, manual step.** Document it explicitly: re-running locally with a different `ANTHROPIC_API_KEY` is fine; CI never records. The recording requires `pytest --record-mode=once` and a fresh API key. Phase 4's existing cassette discipline applies — read `phase-04/critique.md ›cross-cutting blind spot #1` carefully before changing the prompt YAML; any text change invalidates the cassette and forces re-recording.
- **The cost assertion is load-bearing for G9.** If the recorded cassette shows > $0.12 for a single distroless migration, the assertion fails — and the right resolution is to shrink the prompt (fewer few-shot tokens, tighter system block), not to raise the budget. The budget is a roadmap exit criterion.
- **The "distroless-shaped patch" assertion is fragile.** A simple `b"+FROM cgr.dev/chainguard/"` substring check is sufficient *now* but a real downstream validator (Phase 4's `OutputValidator`) is what should structurally accept it. If S6-08's "loud failure on mismatch" relies on the validator, share that validator's posture here — the test can also assert `FallbackTierResult.output_validated is True`.
- **RAG miss forcing**: the cleanest approach is to ensure the heredoc fixture's query doesn't match any seeded example. Verify by reading what S6-07 seeds — if S6-07 happens to seed a heredoc-like example, this test's miss assertion is brittle. Coordinate with S6-07.
- **Prompt template version `v1` is permanent until an ADR amends.** Do not bump to `v2` casually — Phase 4's existing discipline says bumping a template version triggers full cassette re-record. ADR amendment + label-gated PR review.
- **The `replan_with_phase4` node** is in S5-02; this story tests it from the outside via the CLI. Do not re-implement node logic in the test.
- **Fence-CI deny-imports** — the prompt YAML is under `src/codegenie/planner/prompts/` (Phase 4's territory), not Phase 7's restricted modules. Phase 4 is allowed to import `anthropic`; Phase 7 is not. Confirm by running `fence_ci.yaml` after merge.
- Update story `Status:` to `Done` when complete.
