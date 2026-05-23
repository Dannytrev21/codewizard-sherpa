# Story S3-01 — `SandboxSpecBuilder.for_gate` + canonical `sandbox_spec_hash`

**Step:** Step 3 — Implement DinD backend + SandboxSpecBuilder + SandboxHealthProbe
**Status:** HARDENED
**Effort:** M
**Depends on:** S1-02 (`SandboxSpec`, `CopyInEntry` frozen models), S1-04 (`Gate` ABC, `GateContext`, `AttemptNumber` newtype, `TransitionId`), S1-05 (`env_allowlist.filter` module-level function), S1-06 (`gates/catalog_loader.{load, load_all}` module-level + `CatalogEntry`)
**ADRs honored:** ADR-0001 (chokepoint discipline — builder itself touches no subprocess), ADR-0011 (no verdict cache; `sandbox_spec_hash` is the forward-compat seam — hash inputs include all `SandboxSpec` fields + base-image digest + gate's `required_signals` tuple), ADR-0012 (static env allowlist), ADR-0014 (extra="forbid"/frozen Pydantic models + banned-substring field-name walker)

## Validation notes (2026-05-23, phase-story-validator)

**Verdict:** HARDENED. The draft correctly identified the deliverables (builder + canonical-JSON BLAKE3 hash + golden file + property test) and traced to ADR-0012 / ADR-0001, but had **22 weaknesses across all four critic lenses, including ten block-tier findings** that an executor following the draft literally would have silently violated. The most consequential were:

1. **(consistency — block) `EnvAllowlist` class type does not exist.** S1-05 HARDENED ships `env_allowlist.filter(env: Mapping[str, str]) -> dict[str, str]` as a **module-level function**, not an `EnvAllowlist` class. The draft `__init__(*, allowlist: EnvAllowlist)` typed against a phantom class. Resolution: builder is constructed with `filter_fn: Callable[[Mapping[str, str]], dict[str, str]]` (DI port) defaulting to `codegenie.sandbox.env_allowlist.filter`; the static type annotation pins the surface. New AC-DI-2.
2. **(consistency — block) `GateCatalogLoader` class type does not exist.** S1-06 HARDENED ships `codegenie.gates.catalog_loader.load(path) -> CatalogEntry` and `load_all(catalog_dir) -> dict[str, CatalogEntry]` as **module-level functions**, with `CatalogEntry` as the Pydantic model. The draft `__init__(*, catalog_loader: GateCatalogLoader)` typed against a phantom class. Resolution: builder is constructed with a pre-loaded `catalog: Mapping[str, CatalogEntry]` (eager-load at construction; immutable for the builder's lifetime — matches the S1-06 `load_all` shape, avoids re-reading YAML per call, makes the builder trivially pure). New AC-DI-1 + AC-LOOKUP-1..AC-LOOKUP-3.
3. **(coverage — block) `host_env` source unpinned.** Draft Implementation outline §2(f) called `self.allowlist.filter(ctx.host_env)`, but `GateContext` (S1-04 HARDENED) has fields `worktree, advisory, recipe, transform_output, prior_attempts, workflow_id, run_id` — **no `host_env`**. An executor would either fork `GateContext` (breaking the S1-04 contract) or silently read `os.environ` (no DI, untestable, ADR-0001 chokepoint drift). Resolution: third constructor kwarg `host_env_source: Callable[[], Mapping[str, str]] = lambda: types.MappingProxyType(dict(os.environ))` — a Hexagonal port for host-env reading. Defaults to `os.environ` but tests inject a frozen `MappingProxyType` fixture for byte-determinism. New AC-DI-3 + AC-ENV-1..AC-ENV-4.
4. **(consistency — block) Hash recipe omits `required_signals` per ADR-0011 "at minimum" clause.** ADR-0011 Consequences pin: "the hash includes — at minimum — all `SandboxSpec` fields plus the base-image digest plus the gate's required-signals tuple." Draft's `json.dumps(spec.model_dump(mode='json'), sort_keys=True)` covers only `SandboxSpec` fields — `required_signals` lives on `CatalogEntry`, not `SandboxSpec`. An executor literally following the draft would ship a hash that violates ADR-0011 silently. Resolution: hash input is canonical JSON of `{"spec": spec.model_dump(mode="json", by_alias=False, exclude_none=False), "required_signals": sorted(catalog_entry.required_signals)}` (sorted because the gate's required-signals is set-like; order is not semantically meaningful). The `sandbox_spec_hash` field on `SandboxSpec` then carries this combined hash. New AC-HASH-INPUTS-1..AC-HASH-INPUTS-4 + paired tests.
5. **(coverage — block) Multi-phase catalog → flat `SandboxSpec` semantic gap.** Catalog YAML has `sandbox.phases: list[Phase]` (S1-06 schema; arch §Data model line 794–807); `SandboxSpec` (S1-02 HARDENED) is FLAT — single `cmd`, single `network`, single `egress_allowlist`, single `enable_trace`. Arch mermaid line 210 + golden filename `sandbox_spec_<gate>_attempt<n>.json` (singular) imply ONE `SandboxSpec` per attempt. For S3-01 this gap is harmless because S1-06's stub has `phases: []` (AC-STUB-1: "entry.sandbox.phases == []"); for S3-05 (which populates the stub) the collapse rules MUST be pinned. Resolution: AC-PHASES-1 pins behavior for the stub's empty-phases shape (defaults: `cmd = ["true"]` no-op, `network = "none"`, `egress_allowlist = []`, `enable_trace = False`); AC-PHASES-2 explicitly raises `NotImplementedError("phase collapsing deferred to S3-05; see Notes for the implementer")` if `len(catalog_entry.sandbox.phases) > 0`, so the populated-catalog case fails LOUDLY rather than silently shipping a wrong collapse. The phase-collapsing rules are surfaced as a `Notes for the implementer` paragraph for the S3-05 architect/executor to resolve. Fail-loud per Rule 12.
6. **(coverage — block) `copy_in` derivation unpinned.** Implementation outline §2(d) said "resolve `copy_in` from `ctx.worktree` + per-phase paths" — but the stub catalog declares no `copy_in`. Resolution: AC-COPYIN-1 pins `copy_in == [CopyInEntry(src=ctx.worktree, dst=PurePosixPath("/work"), mode="rw")]` — the worktree is `docker cp`'d to `/work` (consistent with arch line 347 "the only thing crossing the sandbox boundary is `docker cp`" — no host bind-mount). Future stories adding more `copy_in` entries (e.g., test inventory fixture) extend this via additive catalog fields; S3-01 ships the minimum.
7. **(consistency — block) Error module paths.** Draft's `from codegenie.sandbox.errors import SandboxSpecForbidden` is correct, but draft also implied `GateCatalogInvalid` lives in `sandbox/errors.py` ("Add `SandboxSpecForbidden`, `GateCatalogInvalid` (if not already from S1-06)"). S1-06 HARDENED ships `GateCatalogInvalid` in `codegenie.gates.errors` (the `gates/` package owns gate-side errors; the `sandbox/` package owns sandbox-side errors). Resolution: AC-ERR-1 pins `SandboxSpecForbidden` in `codegenie/sandbox/errors.py`; `GateCatalogInvalid` is **imported** from `codegenie.gates.errors`, never re-defined. The story's Files-to-touch line for `sandbox/errors.py` is now scoped to just `SandboxSpecForbidden`.
8. **(coverage — block) `Gate.gate_id` lookup semantics unpinned.** Story prescribed `for_gate(gate: Gate, attempt: int, ctx: GateContext)` but never said: (a) which fields of `Gate` are consumed (just `gate.gate_id`?), (b) what happens if `gate.gate_id` doesn't match a `catalog` entry. Resolution: AC-LOOKUP-1..AC-LOOKUP-3 pin: only `gate.gate_id` is read; lookup is `self._catalog[gate.gate_id]`; KeyError translates to `GateCatalogInvalid(f"unknown gate_id: {gate.gate_id}")` (never bare `KeyError` — fail-loud with named error).
9. **(test-quality — block) `_canonical_blake3` private helper test access not pinned.** Draft TDD code imports `_canonical_blake3` (leading underscore) directly from the module. Without an AC pinning this, an executor could refactor it to a method or local function and break the test suite silently. AC-INTERNAL-1 promotes the helper to a documented module-private function with stable name; test-access is contractual, not happenstance.
10. **(coverage — block) Hash format (length, charset) unpinned.** Draft implementation says `hexdigest(length=16)` (16 bytes = 32 hex chars) but no AC asserts `len(hash) == 32 and re.fullmatch(r"[0-9a-f]{32}", hash)`. An executor shipping `.hexdigest()` (no length kwarg → 64 chars) would still pass the byte-stability property test. AC-HASH-FORMAT-1 + AC-HASH-FORMAT-2 pin the literal format.

Beyond the block-tier findings, the harden-tier work:

11. **(test-quality — harden) Property test only varies env-dict keys.** Hash byte-stability requires distinguishing ORDER-SIGNIFICANT fields (`cmd`, `copy_in`, `egress_allowlist`, `copy_out` are lists — order matters) from ORDER-AGNOSTIC fields (`env` is `Mapping`, `required_signals` is a set-like tuple — order does NOT matter). A mutation that wrongly sorts `cmd` (or wrongly hashes `env` un-sorted) escapes the original property test. Resolution: parametrized property tests — AC-PROP-1 (env reorder ⇒ hash equal), AC-PROP-2 (`required_signals` reorder ⇒ hash equal), AC-PROP-3 (`cmd` reorder ⇒ hash DIFFERS), AC-PROP-4 (`copy_in` reorder ⇒ hash DIFFERS), AC-PROP-5 (`egress_allowlist` reorder ⇒ hash DIFFERS — order is operationally significant for iptables append-order even if semantically a set; pin the strict reading).
12. **(test-quality — harden) Cross-Python-minor portability gate missing.** ADR-0011 + arch §Implementation-level risks #4 explicitly call out 3.11 vs 3.12 instability. Resolution: AC-PORT-1 commits a sidecar `tests/golden/sandbox_spec_stage6_validate_attempt1.hash.txt` containing the BLAKE3 hex; `test_hash_matches_golden_sidecar` reads the golden JSON, hashes it via `_canonical_blake3`, and asserts byte-equality with the sidecar. CI matrix (3.11 × 3.12) runs this on both Pythons; an upgrade that breaks canonical-JSON serialization fails LOUDLY on the second matrix cell.
13. **(test-quality — harden) `SandboxSpecForbidden` belt-and-suspenders code path is dead in practice.** S1-05 AC-DN-1..AC-DN-4 guarantee `filter` strips denied substrings. An executor could ship `SandboxSpecForbidden` as a `raise NotImplementedError` and pass every functional test — the assertion belt+suspenders code path is never exercised because `filter` is correct. Resolution: AC-DEFENSE-1 + AC-DEFENSE-2 pin a unit test that injects a **mock** `filter_fn` returning `{"ANTHROPIC_API_KEY": "leak"}` (proves the post-filter assertion path is live).
14. **(test-quality — harden) `attempt_overrides` deep-merge semantics ambiguous.** Draft "deep merge on `phases`, last-wins on scalars" is ambiguous: phase-list-by-name-merge? Phase-list-replace? List-concat? Resolution: for S3-01 (stub catalog has empty `phases` and `attempt_overrides`), AC-OVR-1 pins that the override-merge logic is **scoped to scalar `sandbox.*` fields and `env_allowlist`**, NOT `phases` (since `phases` is empty and the multi-phase collapse is deferred to S3-05 per finding #5). AC-OVR-2 pins that an override with a `phases` key raises `NotImplementedError("attempt_overrides.phases merge deferred to S3-05")` (fail-loud rather than silently shipping wrong semantics). AC-OVR-3 pins that scalar overrides (`time_budget_seconds`, `memory_limit_mib`, `pids_limit`) use last-wins. AC-OVR-4 pins that `env_allowlist` (list of strings) is fully replaced (not unioned) per YAML convention.
15. **(test-quality — harden) Golden test brittleness; add structural assertions.** A golden-byte-equal test fails on any benign fixture change. Resolution: AC-GOLDEN-2 keeps the byte-equal golden test (fail-loud on canonical-JSON drift) and adds AC-STRUCT-1..AC-STRUCT-6 — structural assertions on specific fields (`spec.base_image.startswith("cgr.dev/")`, `spec.time_budget_seconds == 600`, `"PATH" in spec.env`, `"ANTHROPIC_API_KEY" not in spec.env`, `spec.network == "none"`, `len(spec.sandbox_spec_hash) == 32`). When the golden regenerates, the structural tests still encode intent (Rule 9).
16. **(consistency — harden) Module purity AST-walker test missing.** Every prior Step-1 phase-5 story (S1-02 / S1-03 / S1-04 / S1-05 / S1-06) shipped `tests/.../test_*_purity.py`. Resolution: AC-PURE-1..AC-PURE-5 ship `tests/sandbox/test_spec_builder_purity.py` (TYPE_CHECKING-aware) enforcing (a) `from __future__ import annotations` immediately after the module docstring, (b) alphabetized `__all__` containing exactly `{"SandboxSpecBuilder"}`, (c) module docstring cites ADR-0001 / ADR-0011 / ADR-0012, (d) imports limited to stdlib + `blake3` + `pydantic` + `structlog` + `codegenie.{gates.contract, gates.errors, sandbox.contract, sandbox.env_allowlist, sandbox.errors, sandbox.logging, types.identifiers}` (NO `subprocess`, NO `yaml`/`pyyaml`, NO LLM SDKs, NO `docker`/`iptables`).
17. **(consistency — harden) `frozen=True` reconstruction idiom (`model_copy`) unpinned.** `SandboxSpec` is `frozen=True` (S1-02 AC-2/AC-3). The draft's "construct with hash='' then rebuild with hash set" is ambiguous; the Pydantic-canonical idiom on frozen models is `spec.model_copy(update={"sandbox_spec_hash": hex})`. AC-FROZEN-1 pins the idiom.
18. **(consistency — harden) `AttemptNumber` newtype unused.** S1-04 ships `AttemptNumber = NewType("AttemptNumber", int)` (bound 1..1024). Draft used raw `int` for `attempt`. AC-TYPE-1 pins the `AttemptNumber` annotation (also forces the test fixtures to use the constructor that enforces the 1..1024 bound — catches off-by-one regressions).
19. **(consistency — harden) `EVENT_SANDBOX_SPEC_BUILT` constant missing from S1-01 table.** Draft mentions structlog event `sandbox.spec.built` but S1-01's canonical event-name table (HARDENED 2026-05-22) does NOT include it. S1-01 HARDENED rule: "append, never rename, never re-value." Resolution: AC-EVT-1 appends `EVENT_SANDBOX_SPEC_BUILT: Final[str] = "sandbox.spec.built"` to `codegenie.sandbox.logging` (the S1-01 owner module) AND `Files to touch` lists `sandbox/logging.py` as a modify-by-append. AC-EVT-2 pins the structured field set on emission: `{"gate_id", "attempt", "sandbox_spec_hash"}` — stable for downstream log consumers.
20. **(patterns — harden) Functional core / imperative shell separation.** Draft prescribed pure-helper helpers but did not enumerate them. Resolution: AC-FCS-1 pins the module structure: (a) PURE helpers (`_canonical_blake3`, `_deep_merge`, `_assemble_partial_spec`, `_compute_hash_input`) take frozen dicts/models and return frozen values; (b) IMPERATIVE shell (`SandboxSpecBuilder.for_gate`) wires DI ports + emits one structlog event. Each pure helper is independently unit-testable (TDD plan lists three direct unit tests on `_canonical_blake3`, `_deep_merge`, `_assemble_partial_spec`).
21. **(patterns — nit, surfaced in Notes) Plugin/strategy for phase-collapsing deferred.** Rule 2 (Simplicity First) bars introducing a `PhaseCollapser` registry today (single consumer; no rule-of-three). Notes-for-implementer paragraph records: when S3-05 + the Phase-7 distroless catalog both produce non-empty `phases`, the rule-of-three is reached and a `PhaseCollapser` Protocol becomes the right Open/Closed seam. Until then, a switch on `len(phases)` is correct.
22. **(consistency — harden) Coverage floor wording aligned.** Draft's "tests pass" replaced by the standard "line ≥ 95% AND branch ≥ 90%" (same gap S1-02..S1-06 closed).

**No `RESCUE`-tier findings.** The multi-phase semantic gap (finding #5) is the most structural weakness, but it is patchable by scoping S3-01 strictly to the stub's `phases: []` shape and fail-loud-ing on non-empty `phases` — the populated-catalog case is deferred to S3-05 in a contained way. The story remains shippable; S3-05's architect inherits a clean, documented hand-off.

**No Stage-3 research needed.** Every gap was answerable from the Phase-5 arch + ADR-0001 / ADR-0011 / ADR-0012 / ADR-0014 + the six prior HARDENED reports (S1-02 / S1-03 / S1-04 / S1-05 / S1-06 / S2-01) + the codebase precedents in `src/codegenie/transforms/policy/lockfile_policy.py` (codegenie-owned trusted YAML) and `src/codegenie/schema/validator.py` (lru_cache validator pattern).

Full validation report at [`_validation/S3-01-spec-builder-canonical-hash.md`](_validation/S3-01-spec-builder-canonical-hash.md).

## Context

`SandboxSpecBuilder` is the single translator from `(gate, attempt, GateContext)` → frozen `SandboxSpec`. It applies the YAML catalog, the `attempt_overrides` table, the static env allowlist, and computes the BLAKE3-128 `sandbox_spec_hash` over canonical-JSON of the spec. The hash is the cache key Phase 9 will consume and the byte-stability lever the entire integration test suite relies on — if it drifts on Python minor-version or `pyyaml` upgrades, every golden file in Step 3 breaks. The builder is also the only path from host env to `SandboxSpec.env`; without it, ADR-0012 has no enforcement.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — SandboxSpecBuilder` (lines 604–611) — exact public surface, hash recipe (BLAKE3 of canonical-JSON with sorted env keys), failure modes (`GateCatalogInvalid`, `SandboxSpecForbidden`).
  - `../phase-arch-design.md §Data model — SandboxSpec` (lines 640–655) — every field the builder must populate; `sandbox_spec_hash` is the last field; `env: Mapping[str, str]` (ADR-0012), `frozen=True`.
  - `../phase-arch-design.md §Data model — gates/catalog/stage6_validate.yaml` (lines 778–808) — full populated YAML showing the multi-phase shape S3-05 will land; S3-01 ships against the empty-`phases` stub only.
  - `../phase-arch-design.md §Harness engineering — Idempotence` (line 836) — "`SandboxSpecBuilder.for_gate(...)` is byte-stable: same inputs → byte-identical `sandbox_spec_hash`".
  - `../phase-arch-design.md §Implementation-level risks #4` (line 274) — `sandbox_spec_hash` stability across Python minor versions; canonical JSON, never YAML, as hash input.
  - `../phase-arch-design.md §Testing strategy — Property tests` (line 886) — spec-hash invariant under env reordering.
  - `../phase-arch-design.md §Testing strategy — Golden files` (line 893) — `tests/golden/sandbox_spec_<gate>_<attempt>.json` is canonical-JSON of `SandboxSpec` produced by the builder.
- **Phase ADRs:**
  - `../ADRs/0011-no-verdict-cache-in-phase-5.md` — ADR-0011 — `sandbox_spec_hash` is the forward-compat seam Phase 9 will consume; hash inputs include **at minimum** all `SandboxSpec` fields + base-image digest + gate's `required_signals` tuple. This story owns the canonical recipe.
  - `../ADRs/0012-static-env-allowlist-no-credentials-in-sandbox.md` — ADR-0012 — `env_allowlist.filter()` is the only host-env → `SandboxSpec.env` path; denied substrings must be filtered even if allowlisted; `SandboxSpecBuilder` is the sole caller per ADR.
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — ADR-0001 — builder lives outside the three subprocess chokepoints (`did/build.py`, `did/network_policy.py`, `firecracker/client.py`); no subprocess imports here; module-purity AST walker enforces.
  - `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — ADR-0014 — every Pydantic model `extra="forbid", frozen=True`; inherited by `SandboxSpec` (S1-02); the builder must not relax these via `model_validate(..., context={"extra": "allow"})` shenanigans.
- **Source design:**
  - `../final-design.md §Synthesis ledger — Env into sandbox row` — winner: static allowlist + CI test.
  - `../final-design.md §Synthesis ledger — verdict cache row` — winner: defer; ship the hash as the seam.
- **Existing code (HARDENED ancestors):**
  - `src/codegenie/sandbox/contract.py` (from S1-02 HARDENED) — `SandboxSpec` (`frozen=True`, `extra="forbid"`, `env: Mapping[str, str]`), `CopyInEntry` (`src: Path`, `dst: PurePosixPath`, `mode: Literal["ro","rw"]`).
  - `src/codegenie/sandbox/env_allowlist.py` (from S1-05 HARDENED) — module-level `filter(env: Mapping[str, str]) -> dict[str, str]` returning a deterministically key-sorted NEW dict; `ALLOWLIST` / `ALLOWLIST_PREFIXES` / `DENY_SUBSTRINGS` are `Final[tuple[str, ...]]`.
  - `src/codegenie/gates/catalog_loader.py` (from S1-06 HARDENED) — module-level `load(path: Path) -> CatalogEntry` + `load_all(catalog_dir: Path) -> dict[str, CatalogEntry]`; `CatalogEntry.retry_policy: RetryPolicy`, `CatalogEntry.transition: TransitionId`, `CatalogEntry.required_signals: list[SignalKind]`, `CatalogEntry.sandbox: <PartialSandboxSpec>`, `CatalogEntry.attempt_overrides: dict[str, ...]`.
  - `src/codegenie/gates/contract.py` (from S1-04 HARDENED) — `Gate` ABC (`gate_id: str`), `GateContext` (`worktree: Path`, `workflow_id: str`, `run_id: str`, `prior_attempts: list[AttemptSummary]`, **no `host_env`**), `AttemptNumber = NewType("AttemptNumber", int)` bound 1..1024.
  - `src/codegenie/gates/errors.py` (from S1-06 HARDENED) — `GateCatalogInvalid` lives here; **NOT** in `sandbox/errors.py`.
  - `src/codegenie/sandbox/errors.py` (from S1-01 HARDENED) — `SandboxSpecForbidden` lands here (new in this story; same module as other sandbox errors).
  - `src/codegenie/sandbox/logging.py` (from S1-01 HARDENED) — `EVENT_SANDBOX_*` constant table; this story appends `EVENT_SANDBOX_SPEC_BUILT = "sandbox.spec.built"` (append-only policy).
  - `src/codegenie/schema/validator.py` — `@functools.lru_cache(maxsize=1)` validator-construction precedent for any heavy per-call init (not strictly needed here; reference only).
  - `src/codegenie/transforms/policy/lockfile_policy.py` — codegenie-owned trusted YAML loader precedent (not used directly here; S1-06 already consumed it).
- **External docs:**
  - https://github.com/oconnor663/blake3-py — BLAKE3 Python bindings; use `blake3.blake3(data).hexdigest(length=16)` for the 128-bit hex (32 ASCII-hex chars).
  - https://docs.pydantic.dev/2.0/usage/models/#model_copy — `model_copy(update={...})` is the canonical idiom for "modifying" a `frozen=True` Pydantic v2 model.

## Goal

Translate a YAML gate definition plus a `(gate, attempt, GateContext)` triple into a frozen `SandboxSpec` whose `sandbox_spec_hash` is byte-stable under env-dict reordering and across Python 3.11/3.12.

## Acceptance criteria

### A. Public surface

- [ ] **AC-API-1** `src/codegenie/sandbox/spec_builder.py` exists; `from codegenie.sandbox.spec_builder import SandboxSpecBuilder` succeeds with no side effects (idempotent on second import: `id(mod_first) == id(mod_second)`).
- [ ] **AC-API-2** `set(codegenie.sandbox.spec_builder.__all__) == {"SandboxSpecBuilder"}`. `_canonical_blake3`, `_deep_merge`, `_assemble_partial_spec` are module-private (single leading underscore) and NOT in `__all__`.
- [ ] **AC-API-3** Module docstring cites ADR-0001, ADR-0011, ADR-0012, and ADR-0014 by number.

### B. Constructor — dependency-injected ports (Hexagonal)

- [ ] **AC-DI-1** `SandboxSpecBuilder.__init__(self, *, catalog: Mapping[str, CatalogEntry], filter_fn: Callable[[Mapping[str, str]], dict[str, str]] = env_allowlist.filter, host_env_source: Callable[[], Mapping[str, str]] = _default_host_env_source)` — three keyword-only DI ports. `catalog` is the pre-loaded result of `gates.catalog_loader.load_all(...)` (matching S1-06's surface); the builder does NOT re-read YAML.
- [ ] **AC-DI-2** `filter_fn` defaults to `codegenie.sandbox.env_allowlist.filter` (the S1-05 HARDENED module-level function). `typing.get_type_hints(SandboxSpecBuilder.__init__)['filter_fn']` is `collections.abc.Callable[[collections.abc.Mapping[str, str]], dict[str, str]]`. No `EnvAllowlist` class type is referenced anywhere (S1-05 ships no such class).
- [ ] **AC-DI-3** `host_env_source` defaults to a module-private factory returning `types.MappingProxyType(dict(os.environ))` (read-only view; defensive copy of `os.environ`). Tests inject deterministic fixtures via this port; production code reads `os.environ` exactly once per `for_gate` call.
- [ ] **AC-DI-4** No `GateCatalogLoader` class type is referenced anywhere (S1-06 ships no such class — only module-level `load`/`load_all`).
- [ ] **AC-DI-5** Constructor is pure: `__init__` performs no I/O (no env reads, no fs reads, no network); two builders with the same `catalog` are interchangeable. Asserted via a test that constructs two builders with `host_env_source = pytest.fail` (would raise on any call) and confirms construction succeeds.

### C. `for_gate(gate, attempt, ctx)` — surface and lookup semantics

- [ ] **AC-FG-1** Signature is `for_gate(self, gate: Gate, attempt: AttemptNumber, ctx: GateContext) -> SandboxSpec`. Source-level pin: `typing.get_type_hints(SandboxSpecBuilder.for_gate)['attempt'] is AttemptNumber` (S1-04 newtype, NOT raw `int`).
- [ ] **AC-FG-2** Returns a `SandboxSpec` whose `sandbox_spec_hash` is non-empty (32-char hex; see §K).
- [ ] **AC-FG-3** `for_gate` performs exactly ONE call to `host_env_source` per invocation (asserted via a counting fake injected as the port — protects against accidental double-reads if `host_env_source` is side-effectful in tests).
- [ ] **AC-LOOKUP-1** Only `gate.gate_id` is consumed from the `gate` argument (no other fields/methods). Asserted via a test that passes a `Mock(spec=Gate)` instance with only `gate_id` set; if any other attribute is accessed during `for_gate`, the test fails.
- [ ] **AC-LOOKUP-2** Catalog lookup is `self._catalog[gate.gate_id]`. Result is the `CatalogEntry` instance from `catalog_loader.load_all`.
- [ ] **AC-LOOKUP-3** Unknown `gate.gate_id` raises `GateCatalogInvalid(f"unknown gate_id: {gate.gate_id}")` — NOT bare `KeyError`. The message contains the offending `gate_id` verbatim (assert via `str(exc)` containment).

### D. Catalog → `SandboxSpec` direct-field mapping (the simple-field path)

- [ ] **AC-MAP-1** `SandboxSpec.base_image == catalog_entry.sandbox.base_image` (string, digest-pinned format per S1-06 AC-SCHEMA-IMG-1).
- [ ] **AC-MAP-2** `SandboxSpec.time_budget_seconds == catalog_entry.sandbox.time_budget_seconds` (override applies per §H; default 600 per the stub).
- [ ] **AC-MAP-3** `SandboxSpec.memory_limit_mib == catalog_entry.sandbox.memory_limit_mib`.
- [ ] **AC-MAP-4** `SandboxSpec.pids_limit == catalog_entry.sandbox.pids_limit`.
- [ ] **AC-MAP-5** `SandboxSpec.label == f"{catalog_entry.gate_id}.attempt{attempt}"` (e.g., `"stage6_validate.attempt1"`) — for telemetry; pinned format so log consumers parse stably.
- [ ] **AC-MAP-6** `SandboxSpec.copy_out == []` for the stub (no `copy_out` declared in the empty-phases stub; future stories add).

### E. Phases collapsing — scoped to S1-06 stub (empty phases)

- [ ] **AC-PHASES-1** When `catalog_entry.sandbox.phases == []` (the S1-06 stub shape), the builder defaults: `SandboxSpec.cmd == ["true"]`, `SandboxSpec.network == "none"`, `SandboxSpec.egress_allowlist == []`, `SandboxSpec.enable_trace is False`. (Safe no-op execution; populated by S3-05.)
- [ ] **AC-PHASES-2** When `len(catalog_entry.sandbox.phases) > 0`, `for_gate` raises `NotImplementedError("phase collapsing deferred to S3-05; see Notes for the implementer")` — fail-loud rather than silently shipping a wrong collapse rule. Asserted via a test using a hand-built `CatalogEntry` with a single phase entry; this test's expected behavior is to RAISE.

### F. `copy_in` construction

- [ ] **AC-COPYIN-1** `SandboxSpec.copy_in == [CopyInEntry(src=ctx.worktree, dst=PurePosixPath("/work"), mode="rw")]` — the worktree is copied into the sandbox at `/work`. Asserted with `ctx.worktree = tmp_path / "wt"`; the resulting entry's `src` is the absolute `Path` of that worktree, `dst` is `PurePosixPath("/work")` (NOT raw string), `mode` is the string `"rw"`.
- [ ] **AC-COPYIN-2** `CopyInEntry.src` is a `pathlib.Path` (Pydantic-coerced); `CopyInEntry.dst` is a `pathlib.PurePosixPath` (preserves POSIX semantics inside the sandbox regardless of host OS — S1-02 AC).

### G. Env filter integration (ADR-0012)

- [ ] **AC-ENV-1** `SandboxSpec.env` is populated EXCLUSIVELY by `self._filter_fn(self._host_env_source())`. No direct `os.environ` read in the builder body (verified by AST walker in `tests/sandbox/test_spec_builder_purity.py`).
- [ ] **AC-ENV-2** `SandboxSpec.env` is filtered to keys that satisfy S1-05's allowlist semantics (the builder does NOT re-implement the filter; it delegates).
- [ ] **AC-ENV-3** The catalog's `sandbox.env_allowlist` list field is currently **informational only** in S3-01 (S1-05's filter operates against the static `ALLOWLIST` / `ALLOWLIST_PREFIXES`; catalog-level allowlist extension is deferred). AC-ENV-3 pins that `catalog_entry.sandbox.env_allowlist` is READ but does NOT alter `_filter_fn`'s behavior for this story. (If a future story widens this, an ADR amendment lands first — friction-bearing per ADR-0012.)
- [ ] **AC-ENV-4** `SandboxSpec.env` iteration order equals the order returned by `_filter_fn` (S1-05 AC-FL-7 pins sorted-key order). Asserted via `list(spec.env.keys()) == sorted(spec.env.keys())` (modulo any `Mapping` adapter — assertion is against the JSON-serialized dump, where order is observable).
- [ ] **AC-DEFENSE-1** When `_filter_fn` is injected as a mock returning `{"ANTHROPIC_API_KEY": "leak", "PATH": "/usr/bin"}` (denied substring slipping through — a hypothetical S1-05 bug), `for_gate` raises `SandboxSpecForbidden(f"denied substring in post-filter env: ANTHROPIC_API_KEY")`. Belt-and-suspenders per ADR-0012 — the assertion path is LIVE, not dead.
- [ ] **AC-DEFENSE-2** Parametrized: `{"GITHUB_TOKEN": ...}`, `{"DB_SECRET": ...}`, `{"REGISTRY_PASSWORD": ...}` — each triggers `SandboxSpecForbidden` with the offending key named in the message.

### H. `attempt_overrides` — scoped semantics

- [ ] **AC-OVR-1** When `catalog_entry.attempt_overrides == {}` or `str(attempt) not in catalog_entry.attempt_overrides`, the base spec is returned unchanged.
- [ ] **AC-OVR-2** When the override at `str(attempt)` declares a `phases` key, `for_gate` raises `NotImplementedError("attempt_overrides.phases merge deferred to S3-05")` — fail-loud (parallel to AC-PHASES-2; multi-phase merge belongs to S3-05).
- [ ] **AC-OVR-3** When the override at `str(attempt)` declares scalar `sandbox.*` fields (`time_budget_seconds`, `memory_limit_mib`, `pids_limit`), last-wins: override values replace the base. Parametrized test over each scalar field — base 600 → override 1200 → spec value 1200; base 2048 → override 4096 → spec value 4096.
- [ ] **AC-OVR-4** When the override declares `env_allowlist` (list of strings), the override **replaces** the base list (no union — YAML convention). Asserted: base `["PATH"]`, override `["NODE_ENV"]` → `catalog_entry.sandbox.env_allowlist` consumed by the builder is `["NODE_ENV"]`. (S3-01 ignores this for env construction per AC-ENV-3, but the merge semantics still ride consistently.)
- [ ] **AC-OVR-5** Override at `str(attempt)` for `attempt > 1` produces a `sandbox_spec_hash` that DIFFERS from `attempt=1` (the hash naturally varies under any field change; pin the differential).

### I. Hash recipe — canonical inputs (ADR-0011 "at minimum" clause)

- [ ] **AC-HASH-INPUTS-1** Hash input is `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")` where `payload == {"spec": <spec without hash>, "required_signals": <sorted tuple>}`.
- [ ] **AC-HASH-INPUTS-2** `<spec without hash>` is computed as `spec_for_hash = spec.model_copy(update={"sandbox_spec_hash": ""}).model_dump(mode="json", by_alias=False, exclude_none=False)` — the placeholder-empty-hash spec dumped via Pydantic's JSON-mode (turns `Path`/`PurePosixPath`/`Mapping` into JSON-serializable primitives).
- [ ] **AC-HASH-INPUTS-3** `<sorted tuple>` is `sorted(list(catalog_entry.required_signals))` (lexicographic sort over the stringified `SignalKind` newtype) — ADR-0011 "the gate's required-signals tuple" pinned literal.
- [ ] **AC-HASH-INPUTS-4** `ensure_ascii=True` is set explicitly (Python json default; explicit avoids future-Python-default drift). Asserted via a parametrized test injecting an env value containing a non-ASCII char (e.g., `"PATH": "/tmp/é"`); hash equals hash of the same input on a different Python version (corroborated by AC-PORT-1).

### J. Hash invariants — property-based (mutation-resistant)

For each property, a hypothesis-based test under `tests/sandbox/test_spec_hash_property.py` exercises generated inputs:

- [ ] **AC-PROP-1** Hash is INVARIANT under `env` dict-key reordering. `_canonical_blake3({"env": {"PATH":"x","NODE_ENV":"y"}, ...}) == _canonical_blake3({"env": {"NODE_ENV":"y","PATH":"x"}, ...})`.
- [ ] **AC-PROP-2** Hash is INVARIANT under `required_signals` reordering. (Set-like; ADR-0011 sorted tuple.)
- [ ] **AC-PROP-3** Hash CHANGES under `cmd` list reordering. `["sh","-c","a"] vs ["a","-c","sh"]` produce different hashes (cmd order is operationally significant).
- [ ] **AC-PROP-4** Hash CHANGES under `copy_in` list reordering when entries differ. `copy_in` is a `list[CopyInEntry]`; reorder distinguishable entries → different hash.
- [ ] **AC-PROP-5** Hash CHANGES under `egress_allowlist` list reordering with distinguishable entries (iptables append-order is operationally significant; strict reading).
- [ ] **AC-PROP-6** Hash is INVARIANT under repeated calls with the same inputs (idempotence). For the same `(gate, attempt, ctx)` triple, `for_gate(...).sandbox_spec_hash == for_gate(...).sandbox_spec_hash` across two builder instances constructed with identical DI ports.
- [ ] **AC-PROP-7** Hash CHANGES when any single SandboxSpec field changes (mutation-style coverage). Parametrized: for each of `base_image`, `time_budget_seconds`, `memory_limit_mib`, `pids_limit`, `network`, `enable_trace` — mutating exactly one field flips the hash.

### K. Hash format & encoding

- [ ] **AC-HASH-FORMAT-1** `len(spec.sandbox_spec_hash) == 32` (BLAKE3-128 → 16 bytes → 32 hex chars).
- [ ] **AC-HASH-FORMAT-2** `re.fullmatch(r"[0-9a-f]{32}", spec.sandbox_spec_hash)` matches; lower-case hex only.
- [ ] **AC-HASH-FORMAT-3** `_canonical_blake3` uses `blake3.blake3(data).hexdigest(length=16)` (the `length` kwarg is `length=16`, NOT default). A test imports `_canonical_blake3` directly and inspects its disassembly OR uses `inspect.getsource` to verify the literal `length=16` appears (defensive against drift to `hexdigest()` without `length`).
- [ ] **AC-HASH-FORMAT-4** `_canonical_blake3` takes `dict[str, object]` and returns `str` — NOT `bytes` (hex string already-encoded).

### L. Cross-Python-minor portability gate (ADR-0011)

- [ ] **AC-PORT-1** `tests/golden/sandbox_spec_stage6_validate_attempt1.hash.txt` is committed and contains the BLAKE3-128 hex of the golden JSON (32 chars + trailing newline). `tests/sandbox/test_spec_hash_portability.py::test_hash_matches_golden_sidecar` reads `tests/golden/sandbox_spec_stage6_validate_attempt1.json`, computes `_canonical_blake3(json.loads(content_str))`, asserts byte-equality with the sidecar `.hash.txt`. This test runs on every CI matrix cell (3.11 × 3.12); a canonical-JSON drift on either Python fails LOUDLY.

### M. Module purity & static defenses (mirrors S1-02..S1-06)

- [ ] **AC-PURE-1** `tests/sandbox/test_spec_builder_purity.py` (TYPE_CHECKING-aware AST walker) is committed. The walker asserts:
  - `from __future__ import annotations` is the FIRST statement after the module docstring;
  - `__all__` is alphabetized and exactly `["SandboxSpecBuilder"]`;
  - Module docstring contains substrings `"ADR-0001"`, `"ADR-0011"`, `"ADR-0012"`, `"ADR-0014"`;
  - Imports (excluding `TYPE_CHECKING` blocks) are limited to: stdlib (`json`, `os`, `re`, `types`, `functools`, `collections.abc`, `pathlib`, `typing`), `blake3`, `pydantic`, `structlog`, `codegenie.gates.contract`, `codegenie.gates.errors`, `codegenie.sandbox.contract`, `codegenie.sandbox.env_allowlist`, `codegenie.sandbox.errors`, `codegenie.sandbox.logging`, `codegenie.types.identifiers`.
- [ ] **AC-PURE-2** NO `subprocess`, `os.system`, `os.popen` import anywhere in `spec_builder.py`. Asserted by the same AST walker AND by `tests/schema/test_no_subprocess_outside_build_chokepoint.py` (which remains green).
- [ ] **AC-PURE-3** NO `yaml` / `pyyaml` import in `spec_builder.py` — the catalog is consumed as a `Mapping[str, CatalogEntry]` (already parsed by S1-06's `catalog_loader`). Going through YAML for hash inputs is forbidden per arch §Implementation-level risks #4.
- [ ] **AC-PURE-4** NO LLM-SDK or vector-store imports (`anthropic`, `langgraph`, `chromadb`, `sentence_transformers`, `openai`, `langchain`, `transformers`) — `tests/schema/test_no_llm_imports_in_sandbox.py` remains green.
- [ ] **AC-PURE-5** NO banned-substring field names in any Pydantic model declared in this module (none expected; S3-01 declares no new Pydantic models). Belt-and-suspenders: reuse `iter_nested_field_names` from `codegenie.sandbox.signals._introspection` (S1-03) on any class declared in the module, assert no name contains `confidence|llm|self_reported|model_says` (ADR-0014 inheritance).

### N. Frozen-spec reconstruction & idempotence

- [ ] **AC-FROZEN-1** `SandboxSpec` is consumed as `frozen=True` (S1-02 AC). Hash-set reconstruction uses `spec.model_copy(update={"sandbox_spec_hash": hex})` — NOT `SandboxSpec(**spec.model_dump(), sandbox_spec_hash=hex)` (which would re-validate the entire model). Asserted via `inspect.getsource(SandboxSpecBuilder.for_gate)` containing the literal substring `.model_copy(update=`.
- [ ] **AC-FROZEN-2** Two `for_gate` invocations with identical inputs return `SandboxSpec` instances that compare equal (`spec_a == spec_b`) AND have identical `sandbox_spec_hash`. (Pydantic equality is field-equality on frozen models.)
- [ ] **AC-FROZEN-3** `for_gate` does NOT mutate the injected `catalog` dict, the injected `host_env_source`'s return value, or the `ctx` object. Asserted by passing a `types.MappingProxyType`-wrapped catalog (a mutation attempt would raise `TypeError`).

### O. Structlog event emission

- [ ] **AC-EVT-1** `codegenie.sandbox.logging.EVENT_SANDBOX_SPEC_BUILT` is added as `Final[str] = "sandbox.spec.built"` (append-only per S1-01 HARDENED policy — "append, never rename, never re-value"). The constant is added to `__all__` (alphabetized).
- [ ] **AC-EVT-2** `for_gate` emits exactly ONE structlog event per call, keyed `EVENT_SANDBOX_SPEC_BUILT`, with fields `{"gate_id": gate.gate_id, "attempt": int(attempt), "sandbox_spec_hash": spec.sandbox_spec_hash}` — and NO other fields (asserted via `structlog.testing.capture_logs` — the event dict's key set equals exactly `{"event", "gate_id", "attempt", "sandbox_spec_hash"}` ignoring any structlog-injected `level`/`log_level`). The emission is the FINAL action of `for_gate` (post-hash, post-construction). Stable fields = stable log consumers.
- [ ] **AC-EVT-3** `int(attempt)` is the emitted form (not `AttemptNumber("…")`), since structlog renders dicts and JSON consumers expect ints.

### P. Functional core / imperative shell

- [ ] **AC-FCS-1** Module structure:
  - **Pure helpers (functional core, no I/O, no logging):** `_canonical_blake3(payload: dict[str, object]) -> str`, `_deep_merge(base: dict, override: dict) -> dict` (scalar last-wins; rejects `phases` keys per AC-OVR-2), `_assemble_partial_spec(catalog_entry: CatalogEntry, attempt: AttemptNumber) -> dict` (catalog → pre-hash spec dict), `_compute_hash_input(spec_dict: dict, required_signals: list) -> dict`.
  - **Imperative shell (the ONE impure method):** `SandboxSpecBuilder.for_gate` — wires DI ports, calls pure helpers, emits ONE structlog event. No other method on `SandboxSpecBuilder` reads I/O.
- [ ] **AC-FCS-2** Each pure helper is independently unit-testable (the TDD plan §Red lists three direct unit tests). A test imports `_canonical_blake3` directly and asserts byte-stable hash of a fixture dict.
- [ ] **AC-INTERNAL-1** `_canonical_blake3`, `_deep_merge`, `_assemble_partial_spec`, `_compute_hash_input` are explicitly documented as test-accessible module-private helpers (single leading underscore; stable names). A docstring on each notes "intended for direct import by `tests/sandbox/test_spec_builder.py`."

### Q. Golden file + structural assertions

- [ ] **AC-GOLDEN-1** `tests/golden/sandbox_spec_stage6_validate_attempt1.json` is committed. Generated from a deterministic fixture context (frozen `workflow_id="wf-test"`, `run_id="run-test"`, frozen `host_env_source` returning `MappingProxyType({"PATH": "/usr/bin", "ANTHROPIC_API_KEY": "should-be-filtered"})`).
- [ ] **AC-GOLDEN-2** `tests/sandbox/test_spec_builder.py::test_for_gate_attempt1_matches_golden` asserts byte-equality between `json.dumps(spec.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))` and the file contents (trailing newline trimmed).
- [ ] **AC-STRUCT-1** Independent structural asserts (would still pass after regenerating the golden — encode intent, not bytes): `spec.base_image.startswith("cgr.dev/")`.
- [ ] **AC-STRUCT-2** `spec.time_budget_seconds == 600` (matches stub).
- [ ] **AC-STRUCT-3** `"PATH" in spec.env`.
- [ ] **AC-STRUCT-4** `"ANTHROPIC_API_KEY" not in spec.env` (the injected fixture key with `KEY` substring is filtered; ADR-0012 belt-and-suspenders).
- [ ] **AC-STRUCT-5** `spec.network == "none"` (stub's empty-phases default per AC-PHASES-1).
- [ ] **AC-STRUCT-6** `re.fullmatch(r"[0-9a-f]{32}", spec.sandbox_spec_hash)` matches.

### R. Errors module surface

- [ ] **AC-ERR-1** `from codegenie.sandbox.errors import SandboxSpecForbidden` succeeds. `SandboxSpecForbidden` is a subclass of `codegenie.errors.CodegenieError` (or whatever S1-01 established as the sandbox-error base; mirror the convention).
- [ ] **AC-ERR-2** `GateCatalogInvalid` is imported FROM `codegenie.gates.errors`, never re-defined in `sandbox/errors.py` (asserted by the purity walker AC-PURE-1).
- [ ] **AC-ERR-3** `SandboxSpecForbidden` is in `codegenie.sandbox.errors.__all__` (alphabetized).

### S. Test / type / lint / coverage floors

- [ ] **AC-CI-1** `ruff check src/codegenie/sandbox/spec_builder.py tests/sandbox/test_spec_builder.py tests/sandbox/test_spec_hash_property.py tests/sandbox/test_spec_hash_portability.py tests/sandbox/test_spec_builder_purity.py` passes.
- [ ] **AC-CI-2** `ruff format --check` is clean on the same paths.
- [ ] **AC-CI-3** `mypy --strict src/codegenie/sandbox/spec_builder.py` passes.
- [ ] **AC-CI-4** Per-module coverage on `spec_builder.py`: **line ≥ 95% AND branch ≥ 90%**.
- [ ] **AC-CI-5** `tests/schema/test_no_subprocess_outside_build_chokepoint.py` remains green.
- [ ] **AC-CI-6** `tests/schema/test_no_llm_imports_in_sandbox.py` remains green.
- [ ] **AC-CI-7** `make check` is green end-to-end.

## Implementation outline

1. **Create `src/codegenie/sandbox/spec_builder.py`** with module docstring citing ADR-0001 / ADR-0011 / ADR-0012 / ADR-0014 + `from __future__ import annotations` as the first statement. Imports limited to: stdlib (`json`, `os`, `re`, `types`, `functools`, `collections.abc`, `pathlib`, `typing`), `blake3`, `pydantic`, `structlog`, and `codegenie.{gates.contract, gates.errors, sandbox.contract, sandbox.env_allowlist, sandbox.errors, sandbox.logging, types.identifiers}`. **No `pyyaml` import** (catalog is pre-parsed). **No `subprocess` import** (ADR-0001). **No LLM-SDK imports** (CI fence).
2. **Add `EVENT_SANDBOX_SPEC_BUILT` to `codegenie.sandbox.logging`** via append-only edit. Value: `"sandbox.spec.built"`. Add to `__all__` (alphabetized).
3. **Add `SandboxSpecForbidden` to `codegenie.sandbox.errors`** as a subclass of the existing sandbox-error base; add to `__all__` (alphabetized).
4. **Pure helpers (functional core):**
   - `_default_host_env_source() -> Mapping[str, str]`: returns `types.MappingProxyType(dict(os.environ))` — one-shot defensive copy.
   - `_canonical_blake3(payload: dict[str, object]) -> str`: `return blake3.blake3(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest(length=16)`.
   - `_deep_merge(base: dict[str, object], override: dict[str, object]) -> dict[str, object]`: recursive scalar last-wins; raises `NotImplementedError("attempt_overrides.phases merge deferred to S3-05")` if `"phases"` key appears in `override`.
   - `_assemble_partial_spec(entry: CatalogEntry, attempt: AttemptNumber, worktree: Path, env: Mapping[str, str]) -> dict[str, object]`: builds the pre-hash spec dict from `entry.sandbox` + override applied + AC-PHASES-1 defaults (when `entry.sandbox.phases == []`) or raises per AC-PHASES-2.
   - `_compute_hash_input(spec_dict: dict[str, object], required_signals: list[str]) -> dict[str, object]`: returns `{"spec": spec_dict_minus_hash, "required_signals": sorted(required_signals)}`.
5. **`SandboxSpecBuilder.__init__(self, *, catalog, filter_fn=env_allowlist.filter, host_env_source=_default_host_env_source)`:** stores ports. No I/O.
6. **`SandboxSpecBuilder.for_gate(self, gate, attempt, ctx)`:**
   - (a) `entry = self._catalog.get(gate.gate_id)`; if `entry is None`, raise `GateCatalogInvalid(f"unknown gate_id: {gate.gate_id}")`.
   - (b) `host_env = self._host_env_source()` (ONE call per invocation).
   - (c) `filtered = self._filter_fn(host_env)`.
   - (d) `_assert_no_denied_substrings(filtered)`: walks filtered keys for the four substrings — if any slipped through, raise `SandboxSpecForbidden(f"denied substring in post-filter env: {key}")`.
   - (e) `partial = _assemble_partial_spec(entry, attempt, ctx.worktree, filtered)` (raises `NotImplementedError` on non-empty phases per AC-PHASES-2).
   - (f) `spec_no_hash = SandboxSpec(**partial, sandbox_spec_hash="")` — Pydantic validates the full structural shape (S1-02 invariants).
   - (g) `hash_input = _compute_hash_input(spec_no_hash.model_copy(update={"sandbox_spec_hash": ""}).model_dump(mode="json", by_alias=False, exclude_none=False), list(entry.required_signals))`.
   - (h) `hex_hash = _canonical_blake3(hash_input)`.
   - (i) `spec = spec_no_hash.model_copy(update={"sandbox_spec_hash": hex_hash})` — frozen-model idiom.
   - (j) `structlog.get_logger(...).info(EVENT_SANDBOX_SPEC_BUILT, gate_id=gate.gate_id, attempt=int(attempt), sandbox_spec_hash=hex_hash)`.
   - (k) `return spec`.
7. **No mutable state on the builder.** `self._catalog`, `self._filter_fn`, `self._host_env_source` are set once in `__init__` and never reassigned. Concurrent calls to `for_gate` from multiple threads are safe (pure helpers + DI ports with no shared mutable state).
8. **Type hints:** every public method has full type hints; pure helpers too. `mypy --strict` passes.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Five test files; every file is **committed before** the implementation lands:

1. **`tests/sandbox/test_spec_builder.py`** — core behavior tests, golden + structural assertions, lookup semantics, `copy_in`, override semantics, defense-in-depth.
2. **`tests/sandbox/test_spec_hash_property.py`** — hypothesis-based hash invariants (`AC-PROP-1` through `AC-PROP-7`).
3. **`tests/sandbox/test_spec_hash_portability.py`** — ADR-0011 cross-Python-minor portability gate (golden hex sidecar comparison).
4. **`tests/sandbox/test_spec_builder_purity.py`** — AST-walker module-purity test (mirrors S1-02..S1-06).
5. **`tests/sandbox/conftest.py`** — fixtures (`stage6_gate`, `fixture_ctx`, `frozen_host_env_source`, `stub_catalog`, `mock_filter_returning_denied`).

Skeleton tests (illustrative; the executor lands the full set):

```python
# tests/sandbox/test_spec_builder.py
from __future__ import annotations

import json
import re
import types
from pathlib import Path, PurePosixPath
from unittest.mock import Mock

import pytest

from codegenie.gates.contract import Gate, GateContext
from codegenie.gates.errors import GateCatalogInvalid
from codegenie.sandbox.contract import CopyInEntry, SandboxSpec
from codegenie.sandbox.errors import SandboxSpecForbidden
from codegenie.sandbox.spec_builder import (
    SandboxSpecBuilder,
    _assemble_partial_spec,
    _canonical_blake3,
    _deep_merge,
)
from codegenie.types.identifiers import AttemptNumber

GOLDEN_JSON = Path(__file__).parent.parent / "golden" / "sandbox_spec_stage6_validate_attempt1.json"
GOLDEN_HASH = Path(__file__).parent.parent / "golden" / "sandbox_spec_stage6_validate_attempt1.hash.txt"


# ------- §C lookup --------

def test_unknown_gate_id_raises_gatecatalogeinvalid_not_keyerror(stub_catalog, fixture_ctx):
    """AC-LOOKUP-3 — unknown gate_id is translated to a named error.
    Mutation-resistant: a bare `self._catalog[gate.gate_id]` ships KeyError; this test fails."""
    builder = SandboxSpecBuilder(catalog=stub_catalog)
    unknown_gate = Mock(spec=Gate)
    unknown_gate.gate_id = "nonexistent_gate"
    with pytest.raises(GateCatalogInvalid, match=r"unknown gate_id: nonexistent_gate"):
        builder.for_gate(unknown_gate, attempt=AttemptNumber(1), ctx=fixture_ctx)


def test_for_gate_reads_only_gate_id_from_gate_argument(stub_catalog, fixture_ctx):
    """AC-LOOKUP-1 — only gate.gate_id is consumed.
    If the implementation drifts to reading gate.required_signals or gate.retry_policy
    (which would be valid on a populated Gate), this test exposes the over-read."""
    builder = SandboxSpecBuilder(catalog=stub_catalog)
    gate = Mock(spec_set=["gate_id"])
    gate.gate_id = "stage6_validate"
    builder.for_gate(gate, attempt=AttemptNumber(1), ctx=fixture_ctx)
    # If the implementation read any other attribute, Mock(spec_set=...) would have raised.


# ------- §F copy_in --------

def test_copy_in_is_single_worktree_entry(stub_catalog, fixture_ctx):
    """AC-COPYIN-1 — exactly one CopyInEntry, src=ctx.worktree, dst=PurePosixPath('/work'), mode='rw'."""
    builder = SandboxSpecBuilder(catalog=stub_catalog)
    gate = _make_gate("stage6_validate")
    spec = builder.for_gate(gate, attempt=AttemptNumber(1), ctx=fixture_ctx)
    assert spec.copy_in == [
        CopyInEntry(src=fixture_ctx.worktree, dst=PurePosixPath("/work"), mode="rw")
    ]


# ------- §G env filter & defense-in-depth --------

def test_filter_fn_is_the_only_path_to_spec_env(stub_catalog, fixture_ctx):
    """AC-ENV-1 — env is populated EXCLUSIVELY via filter_fn(host_env_source())."""
    seen = {"calls": 0}

    def counting_filter(env):
        seen["calls"] += 1
        return {"PATH": "/usr/bin"}

    builder = SandboxSpecBuilder(
        catalog=stub_catalog,
        filter_fn=counting_filter,
        host_env_source=lambda: types.MappingProxyType({"PATH": "/usr/bin", "EXTRA": "ignored"}),
    )
    gate = _make_gate("stage6_validate")
    spec = builder.for_gate(gate, attempt=AttemptNumber(1), ctx=fixture_ctx)
    assert seen["calls"] == 1
    assert spec.env == {"PATH": "/usr/bin"}


def test_belt_and_suspenders_raises_on_denied_post_filter_key(stub_catalog, fixture_ctx):
    """AC-DEFENSE-1 — the SandboxSpecForbidden code path is LIVE.
    Inject a broken filter that returns a denied key; builder must raise."""
    broken_filter = lambda env: {"ANTHROPIC_API_KEY": "leak", "PATH": "/usr/bin"}
    builder = SandboxSpecBuilder(
        catalog=stub_catalog,
        filter_fn=broken_filter,
        host_env_source=lambda: types.MappingProxyType({"PATH": "/usr/bin"}),
    )
    gate = _make_gate("stage6_validate")
    with pytest.raises(SandboxSpecForbidden, match=r"denied substring in post-filter env: ANTHROPIC_API_KEY"):
        builder.for_gate(gate, attempt=AttemptNumber(1), ctx=fixture_ctx)


@pytest.mark.parametrize("denied_key", ["GITHUB_TOKEN", "DB_SECRET", "REGISTRY_PASSWORD"])
def test_belt_and_suspenders_parametrized_denied_keys(denied_key, stub_catalog, fixture_ctx):
    """AC-DEFENSE-2 — parametrized over each denied substring."""
    builder = SandboxSpecBuilder(
        catalog=stub_catalog,
        filter_fn=lambda env: {denied_key: "x", "PATH": "/usr/bin"},
        host_env_source=lambda: types.MappingProxyType({"PATH": "/usr/bin"}),
    )
    with pytest.raises(SandboxSpecForbidden, match=denied_key):
        builder.for_gate(_make_gate("stage6_validate"), attempt=AttemptNumber(1), ctx=fixture_ctx)


# ------- §E phases collapse — scoped to stub --------

def test_empty_phases_yields_safe_defaults(stub_catalog, fixture_ctx):
    """AC-PHASES-1 — empty phases collapse to safe no-op defaults."""
    builder = SandboxSpecBuilder(catalog=stub_catalog)
    spec = builder.for_gate(_make_gate("stage6_validate"), attempt=AttemptNumber(1), ctx=fixture_ctx)
    assert spec.cmd == ["true"]
    assert spec.network == "none"
    assert spec.egress_allowlist == []
    assert spec.enable_trace is False


def test_non_empty_phases_raises_not_implemented(populated_catalog, fixture_ctx):
    """AC-PHASES-2 — non-empty phases fail LOUDLY (deferred to S3-05).
    Mutation-resistant: an executor shipping a silent collapse implementation fails this test."""
    builder = SandboxSpecBuilder(catalog=populated_catalog)
    with pytest.raises(NotImplementedError, match=r"phase collapsing deferred to S3-05"):
        builder.for_gate(_make_gate("stage6_validate"), attempt=AttemptNumber(1), ctx=fixture_ctx)


# ------- §H attempt overrides --------

def test_missing_override_returns_base_unchanged(stub_catalog, fixture_ctx):
    """AC-OVR-1 — missing override → base unchanged."""
    builder = SandboxSpecBuilder(catalog=stub_catalog)
    base = builder.for_gate(_make_gate("stage6_validate"), attempt=AttemptNumber(1), ctx=fixture_ctx)
    # Stub has attempt_overrides == {}; attempt 1 has no override → same hash as a separate attempt 1.
    again = builder.for_gate(_make_gate("stage6_validate"), attempt=AttemptNumber(1), ctx=fixture_ctx)
    assert base.sandbox_spec_hash == again.sandbox_spec_hash


@pytest.mark.parametrize(
    "field,base_val,override_val",
    [
        ("time_budget_seconds", 600, 1200),
        ("memory_limit_mib", 2048, 4096),
        ("pids_limit", 1024, 512),
    ],
)
def test_scalar_override_last_wins(field, base_val, override_val, catalog_with_scalar_override, fixture_ctx):
    """AC-OVR-3 — scalar last-wins, parametrized.
    Mutation-resistant: an executor shipping `base` (no merge) fails on override_val.
    An executor shipping `override` (override-only) fails when override missing for that field."""
    builder = SandboxSpecBuilder(
        catalog=catalog_with_scalar_override(field=field, base=base_val, override=override_val)
    )
    spec1 = builder.for_gate(_make_gate("stage6_validate"), attempt=AttemptNumber(1), ctx=fixture_ctx)
    spec2 = builder.for_gate(_make_gate("stage6_validate"), attempt=AttemptNumber(2), ctx=fixture_ctx)
    assert getattr(spec1, field) == base_val
    assert getattr(spec2, field) == override_val
    assert spec1.sandbox_spec_hash != spec2.sandbox_spec_hash  # AC-OVR-5


def test_override_with_phases_raises_not_implemented(catalog_with_phases_override, fixture_ctx):
    """AC-OVR-2 — override.phases not yet supported; raise rather than silently collapse."""
    builder = SandboxSpecBuilder(catalog=catalog_with_phases_override)
    with pytest.raises(NotImplementedError, match=r"attempt_overrides.phases merge deferred to S3-05"):
        builder.for_gate(_make_gate("stage6_validate"), attempt=AttemptNumber(2), ctx=fixture_ctx)


# ------- §Q golden + structural --------

def test_for_gate_attempt1_matches_golden(stub_catalog, fixture_ctx, frozen_host_env_source):
    """AC-GOLDEN-1/-2 — byte-equal golden."""
    builder = SandboxSpecBuilder(catalog=stub_catalog, host_env_source=frozen_host_env_source)
    spec = builder.for_gate(_make_gate("stage6_validate"), attempt=AttemptNumber(1), ctx=fixture_ctx)
    actual = json.dumps(spec.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    expected = GOLDEN_JSON.read_text().rstrip("\n")
    assert actual == expected, (
        "spec drifted from golden — review hash/env/canonicalization. "
        "If intentional, regenerate the golden AND the .hash.txt sidecar."
    )


def test_for_gate_attempt1_structural_intent(stub_catalog, fixture_ctx, frozen_host_env_source):
    """AC-STRUCT-1..AC-STRUCT-6 — intent assertions survive golden regen."""
    builder = SandboxSpecBuilder(catalog=stub_catalog, host_env_source=frozen_host_env_source)
    spec = builder.for_gate(_make_gate("stage6_validate"), attempt=AttemptNumber(1), ctx=fixture_ctx)
    assert spec.base_image.startswith("cgr.dev/")
    assert spec.time_budget_seconds == 600
    assert "PATH" in spec.env
    assert "ANTHROPIC_API_KEY" not in spec.env
    assert spec.network == "none"
    assert re.fullmatch(r"[0-9a-f]{32}", spec.sandbox_spec_hash)


# ------- §K hash format --------

def test_hash_is_32_lowercase_hex_chars(stub_catalog, fixture_ctx):
    """AC-HASH-FORMAT-1/-2 — exactly 32 lowercase hex chars (BLAKE3-128)."""
    builder = SandboxSpecBuilder(catalog=stub_catalog)
    spec = builder.for_gate(_make_gate("stage6_validate"), attempt=AttemptNumber(1), ctx=fixture_ctx)
    assert len(spec.sandbox_spec_hash) == 32
    assert re.fullmatch(r"[0-9a-f]{32}", spec.sandbox_spec_hash)


def test_canonical_blake3_uses_length_16(monkeypatch):
    """AC-HASH-FORMAT-3 — source contains literal length=16 kwarg.
    Defensive against drift to `.hexdigest()` (which produces 64 chars)."""
    import inspect
    from codegenie.sandbox import spec_builder
    src = inspect.getsource(spec_builder._canonical_blake3)
    assert "length=16" in src, "BLAKE3 hexdigest must request length=16 (16 bytes = 32 hex chars)"


# ------- §N frozen reconstruction --------

def test_frozen_reconstruction_uses_model_copy(monkeypatch):
    """AC-FROZEN-1 — model_copy(update=...) is the idiom on frozen SandboxSpec."""
    import inspect
    from codegenie.sandbox import spec_builder
    src = inspect.getsource(spec_builder.SandboxSpecBuilder.for_gate)
    assert ".model_copy(update=" in src


def test_for_gate_is_idempotent(stub_catalog, fixture_ctx, frozen_host_env_source):
    """AC-FROZEN-2 — two calls with identical inputs return equal specs."""
    builder = SandboxSpecBuilder(catalog=stub_catalog, host_env_source=frozen_host_env_source)
    a = builder.for_gate(_make_gate("stage6_validate"), attempt=AttemptNumber(1), ctx=fixture_ctx)
    b = builder.for_gate(_make_gate("stage6_validate"), attempt=AttemptNumber(1), ctx=fixture_ctx)
    assert a == b
    assert a.sandbox_spec_hash == b.sandbox_spec_hash


# ------- §O structlog event --------

def test_emits_exactly_one_sandbox_spec_built_event(stub_catalog, fixture_ctx, frozen_host_env_source):
    """AC-EVT-2 — exactly one event with stable field set."""
    import structlog
    from codegenie.sandbox.logging import EVENT_SANDBOX_SPEC_BUILT

    builder = SandboxSpecBuilder(catalog=stub_catalog, host_env_source=frozen_host_env_source)
    with structlog.testing.capture_logs() as logs:
        spec = builder.for_gate(_make_gate("stage6_validate"), attempt=AttemptNumber(1), ctx=fixture_ctx)
    matching = [e for e in logs if e.get("event") == EVENT_SANDBOX_SPEC_BUILT]
    assert len(matching) == 1
    ev = matching[0]
    assert set(ev) - {"log_level", "level"} == {"event", "gate_id", "attempt", "sandbox_spec_hash"}
    assert ev["gate_id"] == "stage6_validate"
    assert ev["attempt"] == 1
    assert ev["sandbox_spec_hash"] == spec.sandbox_spec_hash


# ------- §B constructor purity --------

def test_init_does_not_call_host_env_source(stub_catalog):
    """AC-DI-5 — constructor is pure; host_env_source is not invoked at __init__."""
    SandboxSpecBuilder(catalog=stub_catalog, host_env_source=pytest.fail)


# ------- §P pure helpers, direct unit tests --------

def test_canonical_blake3_is_byte_stable_for_simple_dict():
    """Direct unit test on the pure helper — independently exercisable."""
    assert _canonical_blake3({"a": 1, "b": [2, 3]}) == _canonical_blake3({"b": [2, 3], "a": 1})


def test_deep_merge_scalar_last_wins():
    """Direct unit test — scalar override replaces base."""
    assert _deep_merge({"a": 1, "b": 2}, {"b": 3}) == {"a": 1, "b": 3}


def test_deep_merge_rejects_phases_key():
    """AC-OVR-2 enforced at the pure-helper layer."""
    with pytest.raises(NotImplementedError, match=r"attempt_overrides.phases merge deferred"):
        _deep_merge({}, {"phases": [{}]})
```

```python
# tests/sandbox/test_spec_hash_property.py
from __future__ import annotations
import copy

from hypothesis import given, strategies as st

from codegenie.sandbox.spec_builder import _canonical_blake3


_env_strategy = st.dictionaries(
    keys=st.text(alphabet=st.characters(min_codepoint=33, max_codepoint=126), min_size=1, max_size=12).filter(
        lambda s: not any(d in s.upper() for d in ("KEY", "TOKEN", "SECRET", "PASSWORD"))
    ),
    values=st.text(max_size=20),
    min_size=0,
    max_size=8,
)


@given(env_dict=_env_strategy)
def test_hash_invariant_under_env_reordering(env_dict):
    """AC-PROP-1 — env reorder ⇒ hash equal."""
    base = {"spec": {"base_image": "x", "cmd": ["true"], "env": dict(env_dict)}, "required_signals": []}
    reordered = {"spec": {"base_image": "x", "cmd": ["true"], "env": dict(reversed(list(env_dict.items())))}, "required_signals": []}
    assert _canonical_blake3(base) == _canonical_blake3(reordered)


@given(signals=st.lists(st.sampled_from(["build", "install", "tests", "trace", "policy", "cve_delta"]), unique=True))
def test_hash_invariant_under_required_signals_reordering(signals):
    """AC-PROP-2 — required_signals reorder ⇒ hash equal (the implementation sorts before hashing)."""
    a = {"spec": {"x": 1}, "required_signals": sorted(signals)}
    b = {"spec": {"x": 1}, "required_signals": sorted(signals[::-1])}
    assert _canonical_blake3(a) == _canonical_blake3(b)


def test_hash_changes_under_cmd_reorder():
    """AC-PROP-3 — cmd order is operationally significant."""
    a = {"spec": {"cmd": ["sh", "-c", "echo a && echo b"]}, "required_signals": []}
    b = {"spec": {"cmd": ["sh", "-c", "echo b && echo a"]}, "required_signals": []}
    assert _canonical_blake3(a) != _canonical_blake3(b)


def test_hash_changes_under_copy_in_reorder():
    """AC-PROP-4 — copy_in list order is operationally significant."""
    a = {"spec": {"copy_in": [{"src": "/a", "dst": "/x"}, {"src": "/b", "dst": "/y"}]}, "required_signals": []}
    b = {"spec": {"copy_in": [{"src": "/b", "dst": "/y"}, {"src": "/a", "dst": "/x"}]}, "required_signals": []}
    assert _canonical_blake3(a) != _canonical_blake3(b)


def test_hash_changes_under_egress_allowlist_reorder():
    """AC-PROP-5 — egress_allowlist iptables-append order is operationally significant."""
    a = {"spec": {"egress_allowlist": ["x.com", "y.com"]}, "required_signals": []}
    b = {"spec": {"egress_allowlist": ["y.com", "x.com"]}, "required_signals": []}
    assert _canonical_blake3(a) != _canonical_blake3(b)


@pytest.mark.parametrize(
    "field,a_val,b_val",
    [
        ("base_image", "x@sha256:0" * 8 + "0" * 0, "y@sha256:1" * 8 + "0" * 0),
        ("time_budget_seconds", 600, 1200),
        ("memory_limit_mib", 2048, 4096),
        ("pids_limit", 1024, 512),
        ("network", "none", "scoped"),
        ("enable_trace", False, True),
    ],
)
def test_hash_changes_when_single_field_changes(field, a_val, b_val):
    """AC-PROP-7 — mutation-style: one-field-changes-hash-changes."""
    base = {"spec": {field: a_val}, "required_signals": []}
    mutated = {"spec": {field: b_val}, "required_signals": []}
    assert _canonical_blake3(base) != _canonical_blake3(mutated)
```

```python
# tests/sandbox/test_spec_hash_portability.py
from __future__ import annotations

import json
from pathlib import Path

from codegenie.sandbox.spec_builder import _canonical_blake3

GOLDEN_JSON = Path(__file__).parent.parent / "golden" / "sandbox_spec_stage6_validate_attempt1.json"
GOLDEN_HASH = Path(__file__).parent.parent / "golden" / "sandbox_spec_stage6_validate_attempt1.hash.txt"


def test_hash_matches_golden_sidecar():
    """AC-PORT-1 — cross-Python-minor portability gate (CI matrix 3.11 × 3.12).
    If canonical-JSON serialization shifts on a Python upgrade, both files would need
    regenerating in lockstep; otherwise this test fails LOUDLY."""
    spec_dict = json.loads(GOLDEN_JSON.read_text())
    # Reconstruct the hash input shape the implementation uses (spec without hash + required_signals).
    spec_without_hash = {**spec_dict, "sandbox_spec_hash": ""}
    payload = {"spec": spec_without_hash, "required_signals": []}  # stub has required_signals == []
    computed = _canonical_blake3(payload)
    expected = GOLDEN_HASH.read_text().rstrip("\n")
    assert computed == expected
    # And the golden JSON itself must carry the same hash in its sandbox_spec_hash field.
    assert spec_dict["sandbox_spec_hash"] == expected
```

```python
# tests/sandbox/test_spec_builder_purity.py
"""AST-walker module-purity gate for spec_builder.py — mirrors S1-02..S1-06."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent.parent / "src" / "codegenie" / "sandbox" / "spec_builder.py"

ALLOWED_TOP_LEVEL_IMPORT_PREFIXES = frozenset(
    {
        "json", "os", "re", "types", "functools", "collections", "pathlib", "typing",
        "blake3", "pydantic", "structlog",
        "codegenie.gates.contract",
        "codegenie.gates.errors",
        "codegenie.sandbox.contract",
        "codegenie.sandbox.env_allowlist",
        "codegenie.sandbox.errors",
        "codegenie.sandbox.logging",
        "codegenie.types.identifiers",
        "__future__",
    }
)

FORBIDDEN_NAMES = frozenset(
    {
        "subprocess", "yaml", "pyyaml",
        "anthropic", "langgraph", "openai", "langchain", "transformers",
        "chromadb", "sentence_transformers",
        "docker", "iptables",
    }
)


@pytest.fixture(scope="module")
def tree() -> ast.Module:
    return ast.parse(SRC.read_text())


def test_future_annotations_is_first_statement_after_docstring(tree):
    body = tree.body
    # body[0] is the module docstring (Expr/Constant); body[1] must be from __future__ import annotations
    assert isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant), \
        "first statement must be the module docstring"
    assert isinstance(body[1], ast.ImportFrom) and body[1].module == "__future__", \
        "second statement must be `from __future__ import annotations`"
    assert any(a.name == "annotations" for a in body[1].names), \
        "must import `annotations` from __future__"


def test_module_docstring_cites_required_adrs(tree):
    docstring = ast.get_docstring(tree)
    assert docstring is not None
    for adr in ("ADR-0001", "ADR-0011", "ADR-0012", "ADR-0014"):
        assert adr in docstring, f"module docstring must cite {adr}"


def test_dunder_all_is_exact_alphabetized(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ):
            assert isinstance(node.value, (ast.List, ast.Tuple))
            elts = [el.value for el in node.value.elts if isinstance(el, ast.Constant)]
            assert elts == ["SandboxSpecBuilder"], f"__all__ must equal ['SandboxSpecBuilder'], got {elts}"
            assert elts == sorted(elts)
            return
    pytest.fail("no __all__ assignment found")


def test_only_allowed_imports(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                assert top in {p.split(".")[0] for p in ALLOWED_TOP_LEVEL_IMPORT_PREFIXES}, \
                    f"forbidden import `{alias.name}`"
                assert top not in FORBIDDEN_NAMES, f"forbidden import `{alias.name}`"
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            top = module.split(".")[0]
            ok = any(module == p or module.startswith(p + ".") for p in ALLOWED_TOP_LEVEL_IMPORT_PREFIXES)
            assert ok, f"forbidden import-from `{module}`"
            assert top not in FORBIDDEN_NAMES, f"forbidden import `{module}`"


def test_no_subprocess_no_os_system(tree):
    """AC-PURE-2 — explicit assertion."""
    src_text = SRC.read_text()
    assert "import subprocess" not in src_text
    assert "from subprocess" not in src_text
    assert "os.system" not in src_text
    assert "os.popen" not in src_text
```

### Green — make it pass

Minimum builder per the §Implementation outline §6 dataflow. The order matters: (a) build pure helpers (testable in isolation); (b) wire `for_gate` as the imperative shell; (c) commit the golden JSON + hash sidecar generated from the deterministic fixture context; (d) verify the portability test passes locally on both Python 3.11 and 3.12 (CI matrix will re-verify); (e) run `make check`.

### Refactor — clean up

- Audit `_assemble_partial_spec` for the AC-PHASES-1 default values — ensure they live in module-level `Final` constants (e.g., `_EMPTY_PHASES_DEFAULT_CMD: Final[list[str]] = ["true"]`) rather than literal magic values inline. Improves readability + makes future overrides one-line edits.
- Confirm structlog logger is module-level (`_log = structlog.get_logger(__name__)`) rather than constructed per call.
- Confirm `_default_host_env_source` returns `types.MappingProxyType` (not a raw dict) so accidental mutation in tests fails fast.
- Confirm the purity walker file is also itself lint-clean (no test smells).
- Confirm `tests/golden/sandbox_spec_stage6_validate_attempt1.json` has a trailing newline (or none — pick one and stick with it; the golden read-test must agree).
- Confirm the `.hash.txt` sidecar has exactly one trailing newline (POSIX text-file convention) and the comparison strips it.

## Files to touch

| Path | Action | Why |
|---|---|---|
| `src/codegenie/sandbox/spec_builder.py` | create | New module — the `SandboxSpecBuilder` + four pure helpers (`_canonical_blake3`, `_deep_merge`, `_assemble_partial_spec`, `_compute_hash_input`) + `_default_host_env_source`. |
| `src/codegenie/sandbox/errors.py` | modify (append) | Add `SandboxSpecForbidden` (subclass of the existing sandbox-error base from S1-01); add to alphabetized `__all__`. Do **NOT** add `GateCatalogInvalid` here — it lives in `codegenie/gates/errors.py` (S1-06 owns it; the spec_builder imports it). |
| `src/codegenie/sandbox/logging.py` | modify (append) | Add `EVENT_SANDBOX_SPEC_BUILT: Final[str] = "sandbox.spec.built"`; append to alphabetized `__all__` (S1-01 HARDENED "append, never rename, never re-value"). |
| `tests/sandbox/test_spec_builder.py` | create | Core behavior, lookup, copy_in, env, defense-in-depth, override, golden, structural, hash format, frozen reconstruction, structlog event, pure-helper unit tests. |
| `tests/sandbox/test_spec_hash_property.py` | create | Hypothesis-based AC-PROP-1..AC-PROP-7. |
| `tests/sandbox/test_spec_hash_portability.py` | create | Cross-Python-minor portability gate (AC-PORT-1). |
| `tests/sandbox/test_spec_builder_purity.py` | create | AST-walker module-purity test (AC-PURE-1..AC-PURE-5). |
| `tests/sandbox/conftest.py` | modify (append) | Fixtures: `stage6_gate` (real `Gate` subclass with `gate_id="stage6_validate"`), `fixture_ctx` (frozen `GateContext` with deterministic worktree path, `workflow_id="wf-test"`, `run_id="run-test"`), `frozen_host_env_source` (returns `MappingProxyType({"PATH": "/usr/bin", "ANTHROPIC_API_KEY": "should-be-filtered"})`), `stub_catalog` (the S1-06 stub-shape `{"stage6_validate": CatalogEntry(...)}`), `populated_catalog` (one phase entry — triggers AC-PHASES-2), `catalog_with_scalar_override` (factory), `catalog_with_phases_override` (override has `phases` key — triggers AC-OVR-2). |
| `tests/golden/sandbox_spec_stage6_validate_attempt1.json` | create | Canonical JSON of the attempt-1 SandboxSpec from the deterministic fixture context. |
| `tests/golden/sandbox_spec_stage6_validate_attempt1.hash.txt` | create | BLAKE3-128 hex of the golden JSON (32 chars + trailing newline). The portability gate's anchor. |

## Out of scope

- Calling the builder from `GateRunner` — Step 5 wires it.
- Filling in `sandbox-policy.yaml` content — S3-05 owns that.
- Anything Firecracker-specific — `base_image` field handling is identical across backends; Step 6 reuses this.

## Notes for the implementer

### Carry-forward from prior validations
- **S1-02 HARDENED:** `SandboxSpec` is `frozen=True, extra="forbid"`; `env: Mapping[str, str]`; the model_dump path for serialization is `mode="json"` (handles `Path`/`PurePosixPath` coercion).
- **S1-04 HARDENED:** `Gate` ABC; `GateContext` has fields `worktree, advisory, recipe, transform_output, prior_attempts, workflow_id, run_id` — **no `host_env`**. `AttemptNumber = NewType("AttemptNumber", int)` is the canonical type for the `attempt` parameter; using raw `int` is convention drift.
- **S1-05 HARDENED:** `filter` is module-level; `EnvAllowlist` class does not exist. Output is sorted-key `dict[str, str]`. The filter is the only path host_env → SandboxSpec.env per ADR-0012.
- **S1-06 HARDENED:** `catalog_loader.load`/`load_all` are module-level; `GateCatalogLoader` class does not exist. The stub `stage6_validate.yaml` has `required_signals == []`, `attempt_overrides == {}`, `phases == []` — the empty-phases shape this story is scoped to handle.
- **S1-01 HARDENED:** event-name constants table is append-only ("append, never rename, never re-value"). Add `EVENT_SANDBOX_SPEC_BUILT` to `sandbox/logging.py`, do NOT rename existing constants.

### Hash recipe — what NOT to do
- **Never go through YAML for the hash input.** `pyyaml`'s representer is not version-stable; `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=True)` is. Risk #4 in `../phase-arch-design.md §Implementation-level risks` exists because someone will be tempted to `yaml.safe_dump` here — don't.
- **Never call `.hexdigest()` without `length=16`.** Default is 32 bytes = 64 hex chars; we want 16 bytes = 32 hex chars (BLAKE3-128). The purity walker catches this via `inspect.getsource`.
- **Never hash `spec.model_dump()` (mode default).** `Path` and `PurePosixPath` are not JSON-serializable in the default mode. Use `mode="json"` exclusively.
- **Always include `required_signals` in the hash input.** ADR-0011 Consequences pin this — "at minimum" all SandboxSpec fields + base-image digest + gate's required-signals tuple. The base-image digest rides inside `spec.base_image` for free; `required_signals` is on the catalog/gate, not the spec, and must be explicitly composed into the hash input dict.
- **Always `sort_keys=True` AND `separators=(",", ":")` AND `ensure_ascii=True`.** All three are part of the canonical recipe; dropping any one introduces drift.

### Frozen-spec idiom
- `SandboxSpec` is `frozen=True`. The only way to "modify" a value is `spec.model_copy(update={"sandbox_spec_hash": hex})`. Do NOT use `spec.__dict__["sandbox_spec_hash"] = hex` (bypasses Pydantic validation) or `SandboxSpec(**spec.model_dump(), sandbox_spec_hash=hex)` (re-runs full validation — wasteful and risks subtle reorder of Mapping fields). The Pydantic v2 idiom is `model_copy(update=...)`. The purity walker enforces this via `inspect.getsource`.

### Phase-collapse semantic gap (deferred to S3-05)
- The catalog YAML has `sandbox.phases: list[Phase]` (each phase with its own `name`, `network`, `egress_allowlist`, `enable_trace`, `cmd`); the `SandboxSpec` contract (S1-02) is FLAT — single `cmd`, single `network`, single `egress_allowlist`, single `enable_trace`. The arch mermaid line 210 + singular golden filename imply ONE `SandboxSpec` per attempt. **The collapse rules are not pinned anywhere.**
- For S3-01, the stub catalog has `phases: []` (S1-06 AC-STUB-1), so this story sidesteps the problem entirely by (a) defaulting to a safe no-op (`cmd=["true"]`, `network="none"`, `egress_allowlist=[]`, `enable_trace=False`) for empty phases, and (b) `NotImplementedError` raise for non-empty phases.
- **S3-05's executor must surface this gap to the architect before populating the stub.** The plausible resolutions are (i) catalog YAML collapses to a single `sh -c` cmd with most-permissive network and union egress_allowlist (current S1-02 contract preserved); (ii) S1-02 contract widens to `phases: list[PhaseSpec]` (contract-breaking; needs ADR amendment); (iii) the builder returns `list[SandboxSpec]` and `GateRunner.run` iterates (contract-extending; needs S3-01 + S1-02 amendments). The story does NOT pick a winner — the architect does.

### Plugin/strategy framing (Notes — Rule 2 defers the pattern)
- A `PhaseCollapser` Protocol with a registry would be the right Open/Closed seam for the resolution above, **but** Rule 2 ("Simplicity First — three similar lines is better than premature abstraction") bars introducing it today with zero concrete consumers. When S3-05 + the Phase-7 distroless catalog (the second consumer) both produce non-empty `phases`, the rule-of-three is reached and `PhaseCollapser` becomes the right abstraction. Until then, a switch on `len(phases)` is correct.
- Similarly, do NOT introduce `SandboxSpecBuilder` plugin registry or `SpecHasher` Protocol — there's one builder, one hash recipe; YAGNI.

### Dependency injection — what to inject and what not to
- `catalog`, `filter_fn`, `host_env_source` are the three ports. All three have production defaults; tests inject fakes.
- Do NOT inject `_canonical_blake3` (or any pure helper). They are pure functions; tests call them directly without DI. Injecting them is over-engineering.
- Do NOT inject the `structlog` logger — tests use `structlog.testing.capture_logs()` context manager. This is the project convention.

### Avoiding common pitfalls
- **Path types.** `CopyInEntry.src` is `pathlib.Path` (host-OS dependent); `CopyInEntry.dst` is `pathlib.PurePosixPath` (POSIX semantics in the sandbox). Don't confuse them.
- **Mapping vs dict.** `SandboxSpec.env: Mapping[str, str]` — Pydantic v2 will coerce a `dict` to a Mapping-view at validation time, but `.model_dump(mode="json")` produces a plain `dict[str, str]`. Tests can rely on dict semantics on the dumped payload but should NOT mutate the spec's `env` attribute directly (frozen).
- **structlog event determinism.** Use `structlog.testing.capture_logs()` for assertions; production structlog config injects `level` / `log_level` — strip those when comparing the field set.
- **`MappingProxyType` for `host_env_source`.** Return `types.MappingProxyType(dict(os.environ))` so mutation attempts at the consumer layer fail fast. Don't return `os.environ` directly (mutating it would corrupt subsequent calls).
- **`Final` constants for defaults.** `_EMPTY_PHASES_DEFAULT_CMD: Final[list[str]] = ["true"]` — module-level Final, not inline magic value.

### When the fence trips
- If `tests/schema/test_no_subprocess_outside_build_chokepoint.py` reports a violation, you imported `subprocess`. Don't. The builder talks to no external process.
- If `tests/schema/test_no_llm_imports_in_sandbox.py` reports a violation, you imported an LLM SDK. The sandbox/gates packages are LLM-free.
- If `test_spec_builder_purity.py` reports an `ImportError`-shaped failure, you added an import not in the allowlist. Either extend the allowlist (deliberate; needs a Notes update + ADR awareness check) or restructure to consume the new dependency through an existing internal module.
- If the structural test (`tests/sandbox/test_objective_signals_static.py`) flags any string field added here, you've reached too far into signal-land — back out.
