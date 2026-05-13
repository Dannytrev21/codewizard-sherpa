# Story S2-06 — Cost-tag env shim + Phase 5 ADR-0010 `bench_invocation` amendment

**Step:** Step 2 — Build harness internals: loader, cache, audit chain extension, canary + cost-tag shims
**Status:** Ready
**Effort:** S
**Depends on:** S1-02
**ADRs honored:** ADR-0007 (bench-invocation tagging on `SandboxCostEntry`), Phase 5 ADR-0010 amendment (additive `bench_invocation: bool` field)

## Context

Phase 5 ships `SandboxCostEntry` (one ledger row per `GateRunner` attempt at `.codegenie/cost/sandbox.jsonl`) consumed by Phase 13's ROI dashboard (production ADR-0024). Every nightly bench run invokes the SUT, which invokes Phase 5's sandbox, which writes a `SandboxCostEntry` — indistinguishable from a real production PR-work entry. Without a marker, Phase 13's denominator (`$ spent / $ delivered`) silently inflates. ADR-0007 fixes this with two additive changes: (1) Phase 5's `CostEmitter` reads `CODEGENIE_BENCH_INVOCATION_TAG`; when set, `SandboxCostEntry.workflow_id` becomes the tag and `bench_invocation=True`. (2) `SandboxCostEntry` gains `bench_invocation: bool = False` (additive; default preserves Phase 5's `extra="forbid"` discipline). `src/codegenie/eval/cost_tag.py` exposes the `tag_invocation(...)` context manager that sets/clears the env var around each SUT call. The Phase 5 ADR-0010 amendment lands in the same PR train as this story.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — src/codegenie/eval/cost_tag.py` — public-interface signature, env-var contract, "graceful degradation" if Phase 5's field hasn't landed
  - `../phase-arch-design.md §Edge cases #15` — cross-phase invariant: Phase 13's consumer filters `WHERE bench_invocation IS NOT TRUE`
  - `../phase-arch-design.md §Testing strategy — Adversarial tests` — `test_cost_ledger_pollution.py`
- **Phase ADRs:**
  - `../ADRs/0007-bench-invocation-tagging-on-sandbox-cost-entry.md` — full rationale; env-var name; the four-options rejection trail; reversibility = Medium
- **Production ADRs:**
  - `../../../production/adrs/0024-cost-observability-end-to-end.md` — the downstream consumer that needs the filter
- **Source design:**
  - `../final-design.md §Bench-run cost-ledger tagging` — original synthesis
- **Existing code:**
  - `src/codegenie/sandbox/cost.py` (Phase 5) — `CostEmitter`; `SandboxCostEntry` definition with `extra="forbid"`, `frozen=True`
  - Phase 5 ADR-0010 — `SandboxCostEntry` schema; the file gets an additive amendment

## Goal

`codegenie.eval.cost_tag.tag_invocation(task_class, case_id, run_started_iso)` is a context manager that sets `CODEGENIE_BENCH_INVOCATION_TAG=f"bench:{run_started_iso}:{task_class}:{case_id}"` on entry and clears it on exit; Phase 5's `CostEmitter` reads the env var to mark `SandboxCostEntry.bench_invocation=True` and route `workflow_id` to the tag.

## Acceptance criteria

- [ ] `tag_invocation(task_class: str, case_id: str, run_started_iso: str) -> ContextManager[None]` is importable from `codegenie.eval.cost_tag`.
- [ ] On enter: `os.environ["CODEGENIE_BENCH_INVOCATION_TAG"] = f"bench:{run_started_iso}:{task_class}:{case_id}"`.
- [ ] On exit: the env var is **deleted** (`os.environ.pop(...)`), restoring the previous value if one existed (save/restore in a `try/finally`).
- [ ] **Exception cleanup:** raising inside the `with` block still clears the env var — no leak to the next sandbox invocation.
- [ ] **Nesting / save-restore:** if `CODEGENIE_BENCH_INVOCATION_TAG` was already set before the `with` block (operator override, or accidentally), it is restored to the prior value on exit (not silently overwritten).
- [ ] **Tag shape:** the tag begins literally with `bench:`; this prefix is part of the contract — Phase 13's reader may filter on either `bench_invocation==True` OR `workflow_id.startswith("bench:")`. The redundancy is by design (ADR-0007 §Tradeoffs row 4).
- [ ] **Phase 5 amendment shipped:** `SandboxCostEntry` (Phase 5) gains `bench_invocation: bool = False` (additive field). `CostEmitter` (Phase 5) reads `os.environ.get("CODEGENIE_BENCH_INVOCATION_TAG")`; when present, sets `workflow_id` to the tag and `bench_invocation=True`. ADR-0010's "Consequences" section is updated to enumerate the new field.
- [ ] **Cross-phase contract test:** `tests/unit/test_cost_ledger_tagging.py` — wrap a stubbed `CostEmitter.emit(...)` call in `tag_invocation(...)`; assert the emitted `SandboxCostEntry` carries `bench_invocation=True` and `workflow_id == tag`. Without the wrapper, both revert to defaults.
- [ ] **Adversarial test:** `tests/adv/test_cost_ledger_pollution.py` — assert a bench-tagged entry and a production-tagged entry are filterable by Phase 13's `WHERE bench_invocation IS NOT TRUE` semantics (simulate by filtering the list).
- [ ] **Graceful degradation:** if Phase 5 hasn't landed the `bench_invocation` field yet (in-flight amendment), the env var is silently ignored — the contract test fails loudly, but a runner integration test does not crash. (Document this; do not enforce in code.)
- [ ] TDD red test exists, committed, green.
- [ ] `ruff format`, `ruff check`, `mypy --strict` clean.

## Implementation outline

1. Create `src/codegenie/eval/cost_tag.py`. Module docstring quotes ADR-0007 §Decision and the Phase 5 amendment dependency.
2. The env-var name is a module-level constant: `_ENV_VAR = "CODEGENIE_BENCH_INVOCATION_TAG"`.
3. `@contextlib.contextmanager` `tag_invocation(task_class, case_id, run_started_iso)`:
   - `tag = f"bench:{run_started_iso}:{task_class}:{case_id}"`.
   - `prior = os.environ.get(_ENV_VAR)`.
   - `os.environ[_ENV_VAR] = tag`.
   - `try: yield; finally:` either `os.environ[_ENV_VAR] = prior` or `os.environ.pop(_ENV_VAR, None)` depending on whether `prior is None`.
4. Amend `src/codegenie/sandbox/cost.py` (Phase 5):
   - Add `bench_invocation: bool = False` to `SandboxCostEntry` (mind `extra="forbid"` discipline; this is **additive**, fine).
   - In `CostEmitter.emit(...)` (or whatever the construction site is), read `os.environ.get("CODEGENIE_BENCH_INVOCATION_TAG")`; when truthy, set `workflow_id=tag` and `bench_invocation=True` on the constructed entry.
5. Amend Phase 5 ADR-0010 markdown to document the new field in §Consequences.

## TDD plan — red / green / refactor

### Red

Test file: `tests/unit/eval/test_cost_tag.py`

```python
def test_tag_invocation_sets_env_var():
    with tag_invocation("vuln-remediation", "001-x", "2026-05-12T00:00:00+00:00"):
        v = os.environ["CODEGENIE_BENCH_INVOCATION_TAG"]
        assert v == "bench:2026-05-12T00:00:00+00:00:vuln-remediation:001-x"

def test_tag_invocation_clears_on_normal_exit():
    with tag_invocation("a", "b", "2026-05-12T00:00:00+00:00"):
        assert "CODEGENIE_BENCH_INVOCATION_TAG" in os.environ
    assert "CODEGENIE_BENCH_INVOCATION_TAG" not in os.environ

def test_tag_invocation_clears_on_exception():
    try:
        with tag_invocation("a", "b", "2026-05-12T00:00:00+00:00"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert "CODEGENIE_BENCH_INVOCATION_TAG" not in os.environ

def test_tag_invocation_save_restores_prior_value(monkeypatch):
    monkeypatch.setenv("CODEGENIE_BENCH_INVOCATION_TAG", "prior-value")
    with tag_invocation("a", "b", "2026-05-12T00:00:00+00:00"):
        assert os.environ["CODEGENIE_BENCH_INVOCATION_TAG"].startswith("bench:")
    assert os.environ["CODEGENIE_BENCH_INVOCATION_TAG"] == "prior-value"

def test_tag_format_begins_with_bench_colon():
    with tag_invocation("tc", "case-id", "iso-string"):
        assert os.environ["CODEGENIE_BENCH_INVOCATION_TAG"].startswith("bench:")
```

Cross-phase contract test: `tests/unit/test_cost_ledger_tagging.py`

```python
def test_emitter_marks_bench_invocation_under_tag(stub_cost_emitter):
    with tag_invocation("vuln-remediation", "001-x", "2026-05-12T00:00:00+00:00"):
        entry = stub_cost_emitter.emit(...)  # whatever Phase 5's signature is
    assert entry.bench_invocation is True
    assert entry.workflow_id == "bench:2026-05-12T00:00:00+00:00:vuln-remediation:001-x"

def test_emitter_defaults_outside_tag(stub_cost_emitter):
    entry = stub_cost_emitter.emit(...)
    assert entry.bench_invocation is False
```

Adversarial: `tests/adv/test_cost_ledger_pollution.py`

```python
def test_bench_entries_filterable_from_production_entries(stub_cost_emitter):
    with tag_invocation("a", "b", "iso"):
        bench_entry = stub_cost_emitter.emit(...)
    prod_entry = stub_cost_emitter.emit(...)
    filtered = [e for e in [bench_entry, prod_entry] if not e.bench_invocation]
    assert filtered == [prod_entry]
```

### Green

Smallest impl: §Implementation outline; ~15 lines for the eval shim + small Phase 5 amendment.

### Refactor

- Add structlog `debug cost_tag.env_set` and `cost_tag.env_cleared` events with `tag` attribute — observable during S5-05 integration runs.
- Document the env-var name as a stable cross-phase contract in `cost_tag.py`'s module docstring; future tag flavors (`CODEGENIE_DEV_INVOCATION_TAG`, etc.) follow the same shape (ADR-0007 §Consequences).
- The `_ENV_VAR` constant is exported (e.g., as `BENCH_INVOCATION_ENV_VAR`) so Phase 5's `CostEmitter` can import the name rather than hard-code it.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/cost_tag.py` | New module — `tag_invocation` context manager + env-var name constant |
| `src/codegenie/sandbox/cost.py` | Phase 5 amendment — additive `bench_invocation` field + env-var read in `CostEmitter` |
| `docs/phases/05-sandbox-trust-gates/ADRs/0010-cost-sandbox-run-ledger-schema.md` | Phase 5 ADR amendment — §Consequences updated with new field |
| `tests/unit/eval/test_cost_tag.py` | Red tests for the shim |
| `tests/unit/test_cost_ledger_tagging.py` | Cross-phase contract test |
| `tests/adv/test_cost_ledger_pollution.py` | Adversarial filter test |

## Out of scope

- **Phase 13's reader** — out of scope; `WHERE bench_invocation IS NOT TRUE` is documented but Phase 13 implementation is future work.
- **The eventual S7-03 re-confirmation pass** — the Phase 5 amendment is **landed** here; S7-03 only re-checks that the amendment is merged before the phase merge train.
- **The runner's invocation of `tag_invocation` around each `SUT(case)` call** — handled by S3-02; this story only ships the context manager.
- **Multiple tag flavors** (dev, regression, etc.) — ADR-0007 §Reversibility documents this as future additive ADR work.

## Notes for the implementer

- **Env-var save/restore semantics:** the load-bearing case is the operator who manually sets `CODEGENIE_BENCH_INVOCATION_TAG` for an ad-hoc experiment, then runs `codegenie eval run`. The shim must restore their value on exit, not erase it. Use `os.environ.get(_ENV_VAR)` to snapshot before set; on exit, restore via assignment if the snapshot was non-None, else pop.
- **Cross-phase amendment train:** Per `phase-arch-design.md §Risks #4` and `stories/README.md §Cross-cutting concerns`, the Phase 5 ADR-0010 amendment PR opens *with* this story. Do not wait until S7-03. The pattern mirrors S2-05's Phase 4 amendment.
- **Phase 5's `extra="forbid"` discipline (Phase 5 ADR-0014):** adding `bench_invocation: bool = False` to `SandboxCostEntry` is a Pydantic-frozen-model extension. Every downstream consumer in Phase 5's tests must be re-run; the default value preserves the existing on-disk shape (False is unambiguous; readers that don't read the field aren't affected). This is the explicit "additive only" discipline ADR-0007 enumerates in §Tradeoffs row 2.
- **`workflow_id` collision risk:** the tag value uses colons (`bench:<iso>:<tc>:<case>`); the ISO timestamp also contains colons (`2026-05-12T00:00:00+00:00`). The result has many colons but is unambiguous because the `bench:` prefix is fixed and the remainder is parsed end-to-start when needed. Document the format and do NOT change it without a follow-up ADR (Phase 13 will key on the prefix).
- **Reversibility (from ADR-0007):** Medium. Once Phase 13's ROI math depends on `bench_invocation` being present, removal breaks the dashboard. Treat as one-way additive.
- The graceful-degradation case (Phase 5 hasn't landed the field yet) is **not** an integration test in CI — it's a manual reminder. The `tests/unit/test_cost_ledger_tagging.py` requires Phase 5's amendment to be live; it fails loud if not.
