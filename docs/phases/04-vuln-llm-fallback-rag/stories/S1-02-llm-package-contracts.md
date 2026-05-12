# Story S1-02 — `src/codegenie/llm/` package + `LeafLlmAgent` Protocol + `Plan`/`LlmRequest`/`LlmResponse` Pydantic

**Step:** Step 1 — Plant the contracts, the two ADR-gated Phase-3 edits, and the fence-CI rules every Phase 4 component consumes
**Status:** Ready
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-P4-003, ADR-P4-004, ADR-P4-008, ADR-P4-011

## Context

Foundational. This story stands up the first of Phase 4's two new top-level packages and lands the three load-bearing public contracts (`LeafLlmAgent` Protocol, `LlmRequest`/`LlmResponse`, `Plan` envelope). Every Step 2–7 story imports from `codegenie.llm.contract`. The contracts are **frozen at v0.4.0** — Phase 5's `MicroVmLeafLlmAgent` and Phase 6's LangGraph wrap consume them unchanged (`../phase-arch-design.md §"Development view"`, §"Integration with Phase 5"). Snapshot-tested so drift is conspicuous.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design"` #2 — `LeafLlmAgent` Protocol + `LlmRequest`/`LlmResponse` field shapes verbatim.
  - `../phase-arch-design.md §"Component design"` #3 — `Plan`/`ManualPatch`/`RecipeInvocation` shapes verbatim.
  - `../phase-arch-design.md §"Data model"` — stable-contract list; `*`-marked types must be Pydantic `frozen=True, extra="forbid"`.
  - `../phase-arch-design.md §"Development view"` — package layout and the `codegenie.llm ⊥ chromadb, sentence_transformers` fence rule.
- **Phase ADRs:**
  - `../ADRs/0004-leaf-llm-agent-protocol-os-tiered.md` — ADR-P4-004 — Protocol shape; "frozen at v0.4.0; snapshot tested".
  - `../ADRs/0003-plan-envelope-kind-and-target-files-allowlist.md` — ADR-P4-003 — `Plan.kind` Literal + `target_files` hard-coded npm allowlist as validator constraint.
  - `../ADRs/0008-prompt-injection-structural-defenses.md` — ADR-P4-008 — `canary_token` (32-byte hex) + `canary_echo` field shape.
  - `../ADRs/0015-solved-example-schema-task-class-generic.md` — ADR-P4-015 — `Plan` is shared with `SolvedExample` (consumed by S1-03 too).
- **Source design:**
  - `../final-design.md §"Synthesis ledger"` row "Plan envelope" — XOR invariant rationale.

## Goal

Create `src/codegenie/llm/` with `__init__.py` + `contract.py` containing the `LeafLlmAgent` Protocol, the `LlmRequest`/`LlmResponse` request/response shapes, and the `Plan` envelope (`recipe_invocation` XOR `manual_patch`) with `target_files` constrained to the hard-coded npm allowlist at validator time.

## Acceptance criteria

- [ ] `src/codegenie/llm/__init__.py` and `src/codegenie/llm/contract.py` exist; `from codegenie.llm.contract import LeafLlmAgent, LlmRequest, LlmResponse, Plan, ManualPatch, RecipeInvocation, CachedBlock, PlainBlock` succeeds.
- [ ] `LeafLlmAgent` is a `typing.Protocol` with two methods: `available(self) -> bool` and `invoke(self, request: LlmRequest) -> LlmResponse`.
- [ ] `LlmRequest`, `LlmResponse`, `Plan`, `ManualPatch`, `RecipeInvocation`, `CachedBlock`, `PlainBlock` are Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")`.
- [ ] `Plan.kind: Literal["recipe_invocation", "manual_patch"]`; XOR invariant enforced via `@model_validator(mode="after")` — exactly one of `recipe_invocation` / `manual_patch` is non-None matching `kind`.
- [ ] `ManualPatch.target_files: list[str]` is validator-enforced to satisfy `set(target_files) ⊆ {"package.json","package-lock.json","yarn.lock","pnpm-lock.yaml","npm-shrinkwrap.json"}`. Empty list rejected.
- [ ] `ManualPatch.target_files` rejects path-traversal — any entry containing `..`, an absolute path, or a separator that isn't a basename is refused with a typed validation error.
- [ ] `LlmRequest` carries `system_blocks: list[CachedBlock]`, `few_shots_block: CachedBlock | None`, `query_block: PlainBlock`, `max_tokens: int` (> 0), `temperature: Literal[0]`, `stop_sequences: list[str]`, `run_id: str`, `prompt_template_id: str`, `prompt_template_version: str`, `canary_token: str` (32-byte hex, length 64), `model: Literal["claude-sonnet-4-7"]`.
- [ ] `LlmResponse` carries `text`, `plan: Plan` (never None), `stop_reason: Literal["end_turn","max_tokens","stop_sequence"]`, the four token counters, `cost_usd: Decimal`, `raw_response_path: Path`, `canary_echo: str`.
- [ ] Snapshot test `tests/contracts/test_llm_contract_snapshot.py` byte-stable for `Plan.model_json_schema()`, `LlmRequest.model_json_schema()`, `LlmResponse.model_json_schema()`, `ManualPatch.model_json_schema()`, `RecipeInvocation.model_json_schema()`. Snapshot committed under `tests/contracts/_snapshots/`.
- [ ] Extra-field-rejection unit test exists for every Pydantic class (one extra key → `ValidationError`).
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` on `src/codegenie/llm/` clean.

## Implementation outline

1. `mkdir -p src/codegenie/llm`; create empty `__init__.py`.
2. Define `CachedBlock` (text + `cache_control: Literal["ephemeral"]`) and `PlainBlock` (text only) Pydantic models.
3. Define `RecipeInvocation` (recipe_id + parameters dict — parameters typed as `dict[str, str | int | bool]` to keep the surface narrow).
4. Define `ManualPatch` with `diff: str`, `target_files: list[str]`, and a `@field_validator("target_files")` that:
   - rejects empty list,
   - rejects any entry not in the hard-coded `_NPM_ALLOWLIST: Final[frozenset[str]] = frozenset({"package.json","package-lock.json","yarn.lock","pnpm-lock.yaml","npm-shrinkwrap.json"})`,
   - rejects path traversal (`".." in entry`, absolute path, or `os.sep`/`/` in entry).
5. Define `Plan` with `kind`, `intent`, `canary_echo`, `recipe_invocation`, `manual_patch`, `rationale`. Add `@model_validator(mode="after")` for the XOR invariant: `kind=="recipe_invocation"` ⇒ `recipe_invocation is not None and manual_patch is None`; mirror for `manual_patch`.
6. Define `LlmRequest` and `LlmResponse` per `../phase-arch-design.md §"Component design"` #2.
7. Define `LeafLlmAgent(Protocol)` with `available()` and `invoke()`. Use `@runtime_checkable` so `isinstance(impl, LeafLlmAgent)` works in tests.
8. Write the snapshot test: dump `model_json_schema()` for each contract; commit to `tests/contracts/_snapshots/llm_contract.json`. CI compares bytes.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/contracts/test_llm_contract_snapshot.py`

```python
import json
from pathlib import Path

from codegenie.llm.contract import (
    LeafLlmAgent, LlmRequest, LlmResponse,
    Plan, ManualPatch, RecipeInvocation,
)

SNAPSHOT = Path(__file__).parent / "_snapshots" / "llm_contract.json"


def test_llm_contracts_match_frozen_snapshot():
    current = {
        "Plan": Plan.model_json_schema(),
        "LlmRequest": LlmRequest.model_json_schema(),
        "LlmResponse": LlmResponse.model_json_schema(),
        "ManualPatch": ManualPatch.model_json_schema(),
        "RecipeInvocation": RecipeInvocation.model_json_schema(),
    }
    expected = json.loads(SNAPSHOT.read_text())
    assert current == expected, (
        "Phase-4 LLM contract drift. If intentional, update the snapshot "
        "AND mark this PR `phase-4-contract-bumped`."
    )


def test_leaf_llm_agent_protocol_runtime_checkable():
    class _Stub:
        def available(self) -> bool: return False
        def invoke(self, request): raise NotImplementedError
    assert isinstance(_Stub(), LeafLlmAgent)


def test_plan_target_files_rejects_source_file():
    with pytest.raises(ValidationError):
        ManualPatch(diff="...", target_files=["src/index.js"])


def test_plan_target_files_rejects_path_traversal():
    with pytest.raises(ValidationError):
        ManualPatch(diff="...", target_files=["package.json", "../../etc/passwd"])


def test_plan_xor_invariant():
    with pytest.raises(ValidationError):
        Plan(
            kind="recipe_invocation",
            intent="x", canary_echo="y", rationale="z",
            recipe_invocation=None, manual_patch=None,
        )


def test_llm_request_rejects_extra_field():
    with pytest.raises(ValidationError):
        LlmRequest.model_validate({
            # ...valid minimum fields...
            "stowaway": "smuggled",
        })
```

### Green — make it pass

Land `contract.py` exactly as outlined. Commit the snapshot file produced by a one-time run of `Plan.model_json_schema()` etc., then re-run the test green.

### Refactor — clean up

- Docstrings on each public class citing the ADR row that froze it ("Frozen at v0.4.0 per ADR-P4-004 / ADR-P4-003").
- Module-level `__all__` listing the exported names so the fence-CI graph in S1-07 has a clear contract to assert against.
- Confirm no inline f-string builds any prompt text in this module (irrelevant here; this module has no prompt construction — but pre-empt the fence rule by avoiding any f-string that interpolates an untrusted variable).
- Edge cases from `../phase-arch-design.md §"Edge cases"`: #5 (invalid `Plan` JSON), #6 (`target_files` outside allowlist), #7 (canary smuggle) — none are validator wiring *here*; this story just gives those rules a place to fire.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/llm/__init__.py` | New package. |
| `src/codegenie/llm/contract.py` | All Phase-4 LLM-side contracts. |
| `tests/contracts/test_llm_contract_snapshot.py` | Frozen-schema gate. |
| `tests/contracts/_snapshots/llm_contract.json` | Frozen JSON Schema dump. |
| `tests/contracts/test_plan_target_files_allowlist.py` | Allowlist + path-traversal + XOR invariant. |

## Out of scope

- **`OutputValidator` chain** — handled by S2-01.
- **`NpmPathAllowlistProvider` registry seam** — handled by S1-08. This story hard-codes the npm allowlist *inline in `ManualPatch.target_files` validator*; S1-08 introduces the registry that the validator will consume in S2-01.
- **`LlmInvocationGuard`** — S2-03.
- **Any concrete `LeafLlmAgent` implementation** — S3-02 (in-process), S3-05 (jailed).
- **Snapshot reflowing on Phase-7 distroless extension** — Phase 7's ADR amendment.

## Notes for the implementer

- The `Plan.target_files` allowlist appears in TWO places: hard-coded in this story's `ManualPatch` validator AND as the default `NpmPathAllowlistProvider` in S1-08. They must agree. Treat S1-08's `NpmPathAllowlistProvider.allowed()` as the single source once it lands; in this story you cannot import it (S1-08 depends on S1-02), so the hard-coded set lives here. S2-01 will swap to the registry lookup.
- `canary_token` is **64 hex chars** (32 bytes); the validator should enforce that shape (`re.fullmatch(r"[0-9a-f]{64}", value)`).
- `cost_usd` is `Decimal`, not `float` — the cost-ledger arithmetic in Phase 13 requires exactness.
- `raw_response_path` is `pathlib.Path`; Pydantic v2 handles it natively. Do *not* serialise to `str` here.
- The `@runtime_checkable` decorator on `LeafLlmAgent` makes `isinstance(stub, LeafLlmAgent)` work at the cost of slightly looser structural matching — fine here because we have a snapshot test for full shape pinning.
- Rule 7 (surface conflicts): if Phase 3's `RecipeApplication.engine_used` already exists as a `Literal`, do **not** alter it here — S1-04 owns that edit. This story stays inside `src/codegenie/llm/`.
- Confirm the snapshot file has stable JSON formatting (sorted keys, LF endings) — otherwise CI thrashes on dict-ordering noise. Use `json.dumps(..., sort_keys=True, indent=2) + "\n"`.
