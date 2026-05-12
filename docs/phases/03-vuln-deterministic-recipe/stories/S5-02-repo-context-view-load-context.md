# Story S5-02 — `RepoContextView` + `load_context` + `auto_gather` (`transforms/context.py`)

**Step:** Step 5 — Ship `NpmPackageUpgradeTransform`, `RemediationOrchestrator`, `PatchBranchWriter`, and the `codegenie remediate` CLI surface
**Status:** Ready
**Effort:** M
**Depends on:** S4-05 (`TrustScorer` + index-health consumer surface), S1-08 (Skills frontmatter `applies_to.cve_patterns`); transitively the Phase-0/1/2 gather entry point.
**ADRs honored:** ADR-0002 (`transforms/` package), ADR-0008 (no LLM in this layer), Gap 7 (auto_gather recursion contract)

## Context

`RepoContextView` is the read-only Pydantic projection every Phase-3 component reads from. The selector reads `cve_scan`, `node_manifest`, `depgraph`, `index_health`, and `skills`; the orchestrator reads `index_health` to gate freshness; the transform reads `node_manifest` to check `applies()`. The view is intentionally a *projection* of `repo-context.yaml` (Phase 0/1/2's output artifact) — Phase 3 never writes to it, never mutates it, and never carries it across process boundaries unfrozen.

`load_context(repo_root, *, auto_gather)` is the single entry-point function that turns a `repo_root` path into a validated `RepoContextView`. It enforces two preconditions: (a) the YAML validates against the Phase-0/1/2 schema, (b) `IndexHealthProbe.confidence ≥ medium` on the `cve` domain — meaning the CVE-relevant slice of the index (Grype SBOM + `node_manifest` + the Skills slice) is fresh enough to be trustworthy. If stale and `auto_gather=True`, the function re-runs Phase 0/1/2 gather in-process; if stale and `auto_gather=False`, exit 9.

Per Gap 7 (`phase-arch-design.md §"Gap 7 — auto_gather recursion"`), gather failure during the auto-gather recursion is a hard precondition failure: exit 9 propagates with the gather's own audit slice attached, and both layers append to the same BLAKE3 chain — there is **no chain break**. This is the only place Phase 3 invokes Phase 0/1/2 code; the rest of Phase 3 strictly consumes the artifact.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Logical view" class diagram` — `RepoContextView` projection (cve_scan, node_manifest, depgraph, index_health, skills).
  - `../phase-arch-design.md §"Component design" #9 RemediationOrchestrator` — `ctx = load_context(repo_root, auto_gather=config.auto_gather)` is the first call.
  - `../phase-arch-design.md §"Control flow" — Happy path state diagram` — `LoadContext → [*]: stale + no --auto-gather → exit 9`.
  - `../phase-arch-design.md §"Gap 7 — auto_gather recursion"` — gather failure → exit 9, gather audit slice attached, no chain break.
- **Phase ADRs:**
  - `../ADRs/0002-two-new-top-level-packages-transforms-recipes.md` — `transforms/` houses this module.
  - `../ADRs/README.md "Decisions noted but not yet documented" #1` — Skills frontmatter `applies_to.cve_patterns` additive field.
- **Production ADRs:**
  - `../../../production/adrs/0008-honest-confidence-per-probe.md` — the `IndexHealthProbe.confidence` contract this story reads from.
  - `../../../production/adrs/0006-deterministic-gather-no-llm.md` — auto-gather recursion runs the deterministic Phase 0/1/2 pipeline; no LLM.
- **Source design:**
  - `../final-design.md §"Components" #1 RepoContextView` — read-only Pydantic projection.
  - `../final-design.md §"Open questions" #12` — `auto_gather` policy (default false in CI, true in dev shell).
- **Existing code:**
  - `src/codegenie/probes/index_health.py` (Phase 2 S3-01) — `IndexHealthProbe`; emits the `confidence` per-domain field this story reads.
  - `src/codegenie/cli.py` (Phase 0 + Phase 2 extensions) — exposes `gather` command; `load_context` invokes its underlying in-process entry-point (NOT a subprocess call).
  - `src/codegenie/coordinator.py` (Phase 0/1/2) — the gather coordinator; auto-gather imports its `run_gather(repo_root)` function.
  - `src/codegenie/audit/writer.py` (Phase 2 + S1-07 extension) — append-only audit; gather + remediate share the same chain head.
  - `schemas/repo-context.schema.json` (Phase 0/1/2) — the schema `load_context` validates against.
  - `src/codegenie/skills/loader.py` (Phase 2 + S1-08 amendment) — Skills loader with `applies_to.cve_patterns`.

## Goal

Implement `src/codegenie/transforms/context.py` exposing `RepoContextView` (a frozen Pydantic projection of `repo-context.yaml`) and `load_context(repo_root: Path, *, auto_gather: bool) -> RepoContextView` (the single entry-point Phase 3 uses to acquire it), with stale-context handling that either re-runs Phase 0/1/2 gather in-process (`auto_gather=True`) or raises `StaleContextNotRefreshed` (the orchestrator converts to exit 9 per Gap 7); gather failures during auto-gather propagate as `AutoGatherFailed` carrying the gather's audit slice path without breaking the BLAKE3 chain.

## Acceptance criteria

- [ ] `src/codegenie/transforms/context.py` exports `RepoContextView` (Pydantic, `frozen=True`, `extra="forbid"`) with the exact projection: `cve_scan: GrypeSlice`, `node_manifest: NodeManifestSlice | None`, `depgraph: DepgraphSlice | None`, `index_health: IndexHealthSlice`, `skills: SkillSlice`, `schema_version: Literal["v1"]`.
- [ ] `src/codegenie/transforms/context.py` exports `load_context(repo_root: Path, *, auto_gather: bool) -> RepoContextView`.
- [ ] `load_context` reads `<repo_root>/.codegenie/context/repo-context.yaml`; validates against `schemas/repo-context.schema.json` (re-use Phase 0/1/2's validator — do NOT reimplement); raises `RepoContextNotFound` if file missing OR `RepoContextSchemaInvalid` if schema validation fails.
- [ ] After schema validation, `load_context` projects into `RepoContextView` and checks `view.index_health.per_domain["cve"].confidence ∈ {"medium","high"}`. If `low`, the context is "stale" for Phase 3 purposes.
- [ ] On stale + `auto_gather=True`: invoke `coordinator.run_gather(repo_root, audit_writer=<inherited chain head>)` synchronously, in-process (no subprocess). On gather success, re-read + re-project + re-check. On gather failure, raise `AutoGatherFailed(gather_audit_path=<...>)` — the audit slice path is captured for the CLI to attach to the report.
- [ ] On stale + `auto_gather=False`: raise `StaleContextNotRefreshed(domain="cve", confidence="low")`. The orchestrator converts to exit 9 at the CLI boundary.
- [ ] The gather invocation shares the same `AuditWriter` instance (and therefore the same BLAKE3 chain head) as the remediate run. Per Gap 7: there is no chain break; the gather's `probe.run` / `audit.chain_head_advanced` events interleave with the remediate's `remediate.started` / subsequent events on the same chain.
- [ ] `RepoContextView` is **read-only** — assignment to any field raises `pydantic.ValidationError` (because `frozen=True`); nested slice models are also `frozen=True`. A unit test enforces this.
- [ ] No path in `load_context` writes to `repo-context.yaml`. Re-gather writes via Phase 0/1/2's own writer; `load_context` only re-reads.
- [ ] `tests/unit/transforms/test_context.py` ships ≥ 4 tests: schema-valid context loads → `RepoContextView` instance returned; schema-invalid context → `RepoContextSchemaInvalid`; stale + `auto_gather=False` → `StaleContextNotRefreshed`; stale + `auto_gather=True` + gather succeeds → fresh `RepoContextView` returned.
- [ ] `tests/integration/test_remediate_auto_gather_failure_exit_9.py` pins the Gap 7 path: stale context + `auto_gather=True` + gather fails (synthesized by removing `docker` from PATH) → orchestrator emits exit 9 + the report's `audit_path` references the gather's audit slice.
- [ ] `RepoContextView` is `frozen=True` AND its `__hash__` is non-trivially defined (it's a value object that can be cached as a dict key — Phase 9's Temporal payload depends on hashability).
- [ ] Strict mypy: `IndexHealthSlice.per_domain: Mapping[Literal["scip","sbom","cve","semgrep","gitleaks","runtime_trace"], DomainHealth]` (closed Literal — adding a new domain requires editing the type).
- [ ] The TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Write the failing tests under `tests/unit/transforms/test_context.py` + `tests/integration/test_remediate_auto_gather_failure_exit_9.py` (red).
2. Create `src/codegenie/transforms/context.py` skeleton with the four exception classes (`RepoContextNotFound`, `RepoContextSchemaInvalid`, `StaleContextNotRefreshed`, `AutoGatherFailed`).
3. Define `RepoContextView` and its nested slice models (`GrypeSlice`, `NodeManifestSlice`, `DepgraphSlice`, `IndexHealthSlice`, `SkillSlice`, `DomainHealth`). Slices are **projections** — they re-use Phase 0/1/2's existing Pydantic models where possible, importing rather than redefining. Mark every model `frozen=True, extra="forbid"`.
4. Implement `_read_and_validate(repo_root)` — reads YAML, validates against the JSON schema, projects into `RepoContextView`.
5. Implement `_check_freshness(view) -> bool` — returns True if `view.index_health.per_domain["cve"].confidence ∈ {"medium","high"}`.
6. Implement `_invoke_gather(repo_root, audit_writer)` — imports `codegenie.coordinator.run_gather`; calls it synchronously; on failure raises `AutoGatherFailed` with the gather's audit-slice path. The gather audit-slice path is `<repo_root>/.codegenie/audit/<run-id>.jsonl` — the same path the remediate slice extends.
7. Implement the public `load_context` composing the above: validate → freshness → branch on `auto_gather` + freshness.
8. Wire structured logging — emit `phase3.load_context.started`, `phase3.load_context.stale_detected`, `phase3.load_context.auto_gather_invoked`, `phase3.load_context.completed` (these are structlog events, not BLAKE3-audit events; audit events come from inside `run_gather`).
9. Run pytest, ruff, mypy on touched files.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/transforms/test_context.py`.

```python
# Test signatures only — no implementation.

def test_schema_valid_context_yields_repo_context_view(tmp_path, valid_repo_context_yaml): ...
def test_missing_repo_context_raises_repo_context_not_found(tmp_path): ...
def test_schema_invalid_context_raises_schema_invalid(tmp_path, malformed_yaml): ...
def test_stale_context_no_auto_gather_raises_stale_context_not_refreshed(tmp_path, stale_yaml): ...
def test_stale_context_auto_gather_invokes_run_gather_and_returns_fresh_view(tmp_path, stale_yaml, mock_run_gather): ...
def test_repo_context_view_is_frozen_field_assignment_raises(valid_view): ...
def test_repo_context_view_nested_slices_are_frozen(valid_view): ...
def test_auto_gather_failure_raises_auto_gather_failed_with_audit_path(tmp_path, stale_yaml, mock_run_gather_fail): ...
def test_audit_writer_instance_is_shared_between_remediate_and_gather(tmp_path, captured_chain_head): ...
def test_repo_context_view_hashable_for_temporal_payload_compatibility(valid_view): ...
```

Test file path: `tests/integration/test_remediate_auto_gather_failure_exit_9.py`.

```python
def test_remediate_auto_gather_failure_exits_9_with_gather_audit_slice(tmp_path, stale_fixture, no_docker_env, cli_runner):
    # Stale repo-context.yaml + auto_gather=True + docker missing →
    # CLI exits 9; remediation-report.yaml's audit_path references the gather's audit slice;
    # BLAKE3 chain has NO chain-break event between gather's last event and remediate's first.
    ...
```

Run pytest; confirm failures. Commit as red marker.

### Green — make it pass

Implement the helpers per the outline. The `_invoke_gather` step is the only behaviorally-tricky one: it must share the `AuditWriter` instance so the chain doesn't break. Pass the writer down explicitly — do not rely on a module-level singleton.

The `RepoContextView` projection has its own subtle concern: re-use Phase 0/1/2's Pydantic models verbatim by `from codegenie.context_schema import GrypeSlice as _GrypeSlice` etc. — never copy the field set. If you copy, the schema-evolution policy (Phase 2 S2-07) becomes load-bearing on both definitions in lockstep. Re-export.

### Refactor — clean up

- Hoist the `_AUTO_GATHER_DOMAINS = frozenset({"cve"})` constant; if Phase 4 adds more required domains, the change is one line.
- Module docstring naming ADR-0002, Gap 7, and the freshness invariant.
- Confirm `mypy --strict` on the `IndexHealthSlice.per_domain` Literal — it's the canary for "we added a domain without updating the type." A failing mypy check here is a Phase-0/1/2 schema bump that this story must follow.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/context.py` | New — `RepoContextView` + `load_context` + four exception classes |
| `src/codegenie/transforms/__init__.py` | Append re-exports for `RepoContextView` and `load_context` |
| `tests/unit/transforms/test_context.py` | New — ≥ 4 unit tests (10 listed for safety margin) |
| `tests/integration/test_remediate_auto_gather_failure_exit_9.py` | New — Gap 7 integration test |
| `tests/unit/transforms/fixtures/repo-context-stale.yaml` | New — index_health.per_domain.cve.confidence = "low" |
| `tests/unit/transforms/fixtures/repo-context-valid.yaml` | New — confidence = "high" |
| `tests/unit/transforms/fixtures/repo-context-malformed.yaml` | New — schema-invalid (missing required field) |

## Out of scope

- **The orchestrator that calls `load_context`** — handled by S5-03. This story exposes `load_context` and `RepoContextView`; S5-03's first call invokes it.
- **The CLI's exit-9 mapping** — handled by S5-05. This story raises `StaleContextNotRefreshed` / `AutoGatherFailed`; the CLI maps both to exit 9.
- **`IndexHealthProbe` itself** — Phase 2 (S3-01). This story consumes its output via the `IndexHealthSlice` projection.
- **`run_gather` entry-point** — already exists in Phase 0/1/2 `coordinator.py`. This story imports and invokes it; it does not modify it. If `run_gather` needs an `audit_writer` parameter and currently doesn't accept one, that's a tiny additive edit to `coordinator.py` (gated by ADR-0002's "two new packages; zero edits to Phase 0/1/2 except four ADR-gated additive changes" — this is the implicit fifth additive edit IF it's needed; surface that in the PR description and reference Gap 7).
- **`auto_gather` CLI flag definition** — handled by S5-05 (`--auto-gather/--no-auto-gather`). This story consumes the boolean.
- **Skills `applies_to.cve_patterns`** — handled by S1-08. The `SkillSlice` projection here just surfaces the loaded skills as the recipe selector receives them.
- **`evidence_stale.marked` retraction events** — handled by S2-08. This story does not consume retraction signals; the freshness gate is purely on `IndexHealthProbe.confidence`.

## Notes for the implementer

- **`RepoContextView` is a projection, not a copy.** Import the Phase-0/1/2 slice models. If Phase 0 redefines a field in `GrypeSlice`, this story's `RepoContextView` follows automatically; if you copy the fields, a Phase-0/1/2 evolution breaks this projection silently. The schema-evolution policy (Phase 2 S2-07) is the canonical source.
- **The audit chain must NOT break across the gather-recursion boundary.** Per Gap 7: pass the same `AuditWriter` instance into `run_gather`; the gather appends its events, then the remediate continues appending. A `chain.break` event indicates a bug — and the integration test `test_remediate_auto_gather_failure_exit_9.py` asserts NO `chain.break` event is present, even when the gather *fails*. The contract is: a failing gather produces a partial audit slice + an `AutoGatherFailed` exception with the slice's path; the orchestrator records exit 9 and the chain continues from where the gather left off.
- **Stale = `confidence: low` on the `cve` domain only.** Phase 4 may extend the freshness check to additional domains; Phase 3 only cares about `cve` because that's what the selector reads. Hoist `_AUTO_GATHER_DOMAINS = frozenset({"cve"})` so the extension point is obvious. Do NOT generalize prematurely — a single-element frozenset is the right size today.
- **`auto_gather` is opt-in per ADR.** Per `phase-arch-design.md §"Open questions" #12`, the default config ships with `auto_gather: false` (CI determinism); developer shell overrides set `true`. This story does not make the policy decision — it implements the mechanism. The CLI flag wiring (S5-05) is where the policy default surfaces to the operator.
- **In-process gather, not subprocess.** Re-running `subprocess.run(["codegenie", "gather", repo_root])` is wrong: it (a) forks a fresh Python process, (b) breaks the BLAKE3 chain by spawning a new `AuditWriter`, (c) doubles the import time. `from codegenie.coordinator import run_gather; run_gather(repo_root, audit_writer=writer)` is the right call.
- **Per Rule 3 (Surgical Changes):** if `run_gather` needs an `audit_writer` keyword parameter and doesn't have one, **the smallest possible additive edit** is correct — add the keyword, default it to a freshly-constructed writer for backward compatibility, document the addition in the PR. Do not refactor `coordinator.py` while wiring this story.
- **Per Rule 12 (Fail loud):** if the schema validator silently accepts a partial file (e.g., `node_manifest` missing where Phase 1 always emits it), this layer must NOT paper over the gap by defaulting to `None`. Raise `RepoContextSchemaInvalid`. The contract with the operator is: an invalid `repo-context.yaml` is an actionable bug; re-run gather. Silent defaults make Phase 4 debug its inputs forever.
- **`RepoContextView.__hash__` is non-trivial** because Phase 9 (Temporal Activity payload) requires hashable boundary objects. Pydantic models with `frozen=True` are hashable by default — confirm with `hash(view)` in a unit test; if Pydantic v2's behavior here is surprising, set `model_config = ConfigDict(frozen=True, extra="forbid")` and let the test catch the regression.
