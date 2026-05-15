# Validation report — S1-02 `@register_index_freshness_check` decorator-registry

**Story:** [`../S1-02-freshness-check-registry.md`](../S1-02-freshness-check-registry.md)
**Validated:** 2026-05-15
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

The story implements `@register_index_freshness_check(index_name: IndexName)` — a decorator-registry that closes the Open/Closed gap (`phase-arch-design.md §"Gap 3"`) for `IndexHealthProbe` (B2) by letting every Phase-2 index source register a `(slice, head) -> IndexFreshness` function via a new file + new decorator (never an edit to B2). The draft was structurally sound — no `RESCUE`-tier findings — but had **eight harden-tier gaps** that would have let plausible wrong implementations through the executor's Validator pass:

1. `head`-argument propagation was untested (slice/head argument-swap mutation invisible).
2. Empty-registry `dispatch_all` was untested (would deadlock B2 on first gather).
3. Exception propagation from a check function was undocumented as a runtime contract (story Notes claimed it; no test pinned it).
4. AC-3's "both call sites (`module.qualname`)" requirement was tested only as bare function-name substrings — a regression that strips the module path would pass.
5. Iteration determinism of `dispatch_all` was implicit (audit-chain hashing depends on byte-stable order; non-deterministic dispatch would silently corrupt audit chains).
6. The module-level decorator's return-identity contract was untested (catches a `register_index_freshness_check` that returns `None`).
7. The per-slice routing assertion was weak — original test verified result-key membership but not that each check received *its own* slice (a `dispatch_all` mutation that shuffles slices was invisible).
8. ADR-0006 §Consequences and the story's module-location choice (`registry.py` vs. `freshness.py`) were not explicitly reconciled in the story; the deviation was carried by S1-01's hardening but never recorded as a Notes paragraph in S1-02.

Eight hardening edits were applied in place; the story is now ready for `phase-story-executor`. No `NEEDS RESEARCH` findings (Stage 3 skipped — every gap was answerable from arch + ADR-0006 + Phase 0's `probes/registry.py` precedent + S1-10's sibling-registry story).

## Context Brief (Stage 1)

- **Goal as written:** Implement `src/codegenie/indices/registry.py` exposing `@register_index_freshness_check(index_name: IndexName)` — decorator-registry registering `(slice: dict[str, JSONValue], head: str) -> IndexFreshness` functions, rejects duplicate `index_name` at import time, offers `dispatch_all(slices, head) -> dict[IndexName, IndexFreshness]` total over every registered name.
- **Phase 2 exit criteria touched:** G9 (kernel scaffolding ships before Phase 3), the Open/Closed seam for B2 (`phase-arch-design.md §"Gap 3"`).
- **Load-bearing commitments touched:**
  - CLAUDE.md §"Extension by addition" — this registry IS the extension mechanism for new index sources.
  - CLAUDE.md §"Honest confidence" — the registry's totality (every registered name appears in the output) is what makes B2's freshness reporting honest.
  - `02-ADR-0006 §Consequences` last bullet names the decorator-registry as the Open/Closed fix; story places the registry in `registry.py` rather than the ADR's literal `freshness.py` (deviation documented).
- **Open/Closed seam discipline:**
  - New index source → new file under `src/codegenie/probes/...` + `@register_index_freshness_check(IndexName("..."))` on a free function. Zero edits to `registry.py`, `index_health.py`, or `indices/__init__.py`.
  - New `StaleReason` variant → ADR-amendment-gated (per S1-01 hardening); the `assert_never` arms enforce.
- **Sibling-family lineage:** **2nd registry in a family of 3** — `probes/registry.py` (1st, Phase 0) is the precedent; S1-10's `depgraph/registry.py` is the 3rd. Rule-of-three threshold for kernel extract NOT yet reached; defer to whoever validates S1-10.
- **Prior validation history (this story):** none. (S1-01's validation established the `registry.py` ≠ `freshness.py` decision.)

## Stage 2 — critic reports

### Coverage (verdict: COVERAGE-HARDEN)

Mutation analysis (plausible wrong implementations vs. draft TDD):

| # | Wrong implementation | Caught by draft TDD? | Severity |
|---|---|---|---|
| 1 | Silently overwrite on duplicate registration | Yes — `test_duplicate_name_rejected_at_registration_time` | — |
| 2 | Raise on duplicate at *dispatch* time, not register time | Yes — `with pytest.raises` wraps the `@reg.register(...)` call | — |
| 3 | `register` does not return `fn` (returns `None`) | Partial — `test_decorator_returns_function_unchanged` covered local registry only; module-level `register_index_freshness_check` was untested | harden |
| 4 | `dispatch_all` returns only checks whose name is in `slices.keys()` (not total) | Yes — `test_dispatch_invokes_check_with_empty_dict_when_slice_missing` | — |
| 5 | Duplicate error message strips `module.qualname` to bare `__qualname__` | **No** — original test only checked `"check_a" in msg` (substring); module path could be dropped | harden |
| 6 | `default_freshness_registry` is a fresh per-import instance | Yes — `test_module_level_decorator_uses_default_singleton` would fail | — |
| 7 | `dispatch_all` swaps slice/head positional args (`fn(head, slices.get(name, {}))`) | **No** — no test captured `head` inside a check | harden |
| 8 | `dispatch_all` shuffles slices (`fn(slices.get(<wrong_name>, {}), head)`) | **No** — original test only verified result-key membership; never per-slice routing | harden |
| 9 | `dispatch_all` on empty registry raises (e.g., divide-by-zero on stats, or `next(iter(...))` on empty) | **No** — no empty-registry test | harden |
| 10 | Check function exception silently swallowed by registry | **No** — story Notes claim propagation; no runtime pin | harden |
| 11 | `dispatch_all` iteration order is non-deterministic (e.g., `frozenset(self._checks)` round-trip) | **No** — no order test; audit-chain hashing silently breaks | harden |
| 12 | `register_index_freshness_check(name)(fn)` returns `None` while registering correctly | **No** — only local `reg.register` return-identity was tested | harden |

**Findings:**

- **Cov-F1 (harden, mutations #7 + #11).** No test verifies `head` is threaded through `dispatch_all` to each check; no test pins iteration determinism. Fix: add AC-12 + `test_dispatch_all_threads_head_unchanged_to_every_check` and AC-14 + `test_dispatch_all_iteration_is_registration_order`.
- **Cov-F2 (harden, mutation #9).** No empty-registry test. Fix: add AC-11 + `test_dispatch_all_on_empty_registry_returns_empty_dict`.
- **Cov-F3 (harden, mutation #10).** No exception-propagation test. Fix: add AC-13 + `test_dispatch_all_propagates_check_exception`.
- **Cov-F4 (harden, mutation #5).** AC-3 message format test is too lenient. Fix: tighten test to assert `module.qualname` dotted shape, not just function-name substrings.
- **Cov-F5 (harden, mutation #8).** Original `test_register_and_dispatch_round_trip` did not verify per-slice routing. Fix: add per-check capture variables; assert each check saw its own slice.
- **Cov-F6 (harden, mutation #12).** Module-level decorator's return-identity untested. Fix: add `test_module_level_decorator_returns_function_unchanged`.
- **Cov-F7 (harden).** `registered_names()` is exercised by tests but not declared in AC-1's public surface. Fix: extend AC-1 to enumerate the `FreshnessRegistry` public methods (`register`, `registered_names`, `dispatch_all`) and clarify `unregister_for_tests` as public-but-test-only.
- **Cov-F8 (harden).** `JSONValue` forward-reference: AC-4 mandates "reuses Phase 0's `codegenie.output.sanitizer.JSONValue`" but Phase 0 does not export it. Fix: AC-4 explicitly accepts `dict[str, object]` as the structural fallback; Notes-for-implementer §JSONValue documents the rebind-by-import discipline.

### Test quality (verdict: TESTS-HARDEN)

Rule 9 (tests verify intent, not just behavior) check:

- The original `test_register_and_dispatch_round_trip` asserts result-key membership and variant types but does NOT assert that the right slice reaches the right function. A `dispatch_all` mutation that always passes the *first* slice to every check would pass — every check's return value depends on what each check chooses to do with `slice_.get(...)`, not on which slice it received. **Fix:** capture per-check slice variables; assert the scip check saw `scip_slice` and the runtime check saw `runtime_slice`.
- `test_decorator_returns_function_unchanged` covers local-registry decoration; the module-level convenience decorator has no return-identity test. A wrong `register_index_freshness_check` that returns `None` after a successful internal registration would silently shadow every decorated name to `None` at every import site. **Fix:** add `test_module_level_decorator_returns_function_unchanged` (return-identity at the singleton entrypoint).
- The duplicate-name error message assertion `"check_a" in msg AND "check_b" in msg` does not pin the `module.qualname` dotted format. **Fix:** assert `check_a.__module__ in msg` AND `f".{check_a.__qualname__}" in msg` (dotted form, both call sites).
- `head` argument is currently invisible to the test suite — the freshness-value identity each check returns is the check's choice, not the registry's. A slice/head argument-swap (`fn(head, slices.get(name, {}))`) would pass every existing test. **Fix:** add `test_dispatch_all_threads_head_unchanged_to_every_check` with a `captured_heads` list pinned to `["cafef00d"]`.
- Iteration order, exception propagation, empty registry — see Coverage findings; these are mutation-resistance gaps as much as test-quality gaps.

No `NEEDS RESEARCH` — Hypothesis property tests would help but the additional unit tests cover the same mutation surface without crossing the rule-of-three threshold for property testing in this phase.

### Consistency (verdict: CONSISTENCY-HARDEN — one ADR-text reconciliation)

- `IndexName` typed key from S1-05 ✓; ADR-0033 newtype discipline honored.
- `FreshnessRegistryError` as a marker subclass per Phase 0/1 convention ✓.
- "Extension by addition" CLAUDE.md commitment ✓ — the registry IS the extension mechanism.
- "No LLM" / "Facts not judgments" / "Honest confidence" CLAUDE.md commitments ✓ — registry is pure code; no judgments.
- `phase-arch-design.md §"Gap 3"` intent ✓ matches the story.
- `unregister_for_tests` test-only naming-as-policy discipline ✓ mirrors S1-10's parallel discipline.
- **Cons-C1 (harden — ADR text reconciliation):** `02-ADR-0006 §Consequences` last bullet says "decorator-registry in `freshness.py`" but the story places it in `registry.py`. S1-01's hardened Notes already documented this deviation as "ADR amendment optional only if friction arises" — but S1-02 itself did not name the deviation explicitly in its Notes-for-implementer. Fix: add a Notes paragraph "ADR-0006 §Consequences location deviation" documenting the reconciliation and the circular-import rationale.
- **Cons-C2 (harden — same as Cov-F4):** AC-3's `module.qualname` requirement was textually present in the AC but not pinned by the test. Reinforces the Coverage finding.
- **Cons-C3 (harden — same as Cov-F8):** `JSONValue` forward-reference. Either acknowledge the fallback in AC-4 or take ownership of introducing the alias. Resolved by Notes-for-implementer §JSONValue forward-reference paragraph + AC-4 rewording.

No `RESCUE`-tier findings.

### Design patterns (verdict: DESIGN-HARDEN — two Notes-for-implementer extensions)

- The registry IS the canonical Registry-pattern / decorator-factory application — properly typed `IndexName` key, fail-loud at import time, no premature pluggability. The shape is idiomatic.
- **DP-D1 (harden — rule-of-three observation):** This is the **2nd registry** in a family of 3 (Phase 0's `probes/registry.py` is the 1st; S1-10's `depgraph/registry.py` is the 3rd). The kernel-extract opportunity (a shared `KernelRegistry[K, V]` base) crosses the rule-of-three threshold when S1-10 lands. **This story does NOT pre-extract — Rule 2 (simplicity first) wins until three concrete consumers exist.** Fix: Notes-for-implementer paragraph naming the deferral and identifying who owns the extract decision (whoever validates S1-10).
- **DP-D2 (harden — Open/Closed at file boundary):** The "new index source = new file + new decorator, never an edit to B2" discipline is the load-bearing extension-by-addition commitment from CLAUDE.md. The story states this in `Out of scope` but no AC or Notes paragraph names the *invariant set* (the three paths that must NOT be touched: `registry.py`, `index_health.py`, `indices/__init__.py`). Fix: Notes-for-implementer paragraph naming the three paths and the in-phase verification by S5-05 / S6-08 git-diff scope.
- **DP-D3 (clean):** Composition over inheritance ✓; functional core / imperative shell ✓ (registry is in-memory state; tests use local instances; renderer is a separate concern); newtype `IndexName` used as key ✓; typed `FreshnessCheck` alias ✓; smart-constructor pattern not applicable (the registry is not a value type).
- **DP-D4 (clean):** No anaemic types, no primitive obsession, no untyped dict-shuffling at the public surface. The `_checks` / `_origins` parallel-dict shape is a minor anti-pattern (could be a single `dict[IndexName, RegisteredCheck]` namedtuple), but probes/registry.py uses a single `list` so the call is consistent with phase precedent. Leave as-is.

## Stage 3 — Researcher

**Skipped.** No `NEEDS RESEARCH` findings. Every gap is answerable from:

- Phase 0's `src/codegenie/probes/registry.py` (the decorator-registry precedent)
- `02-ADR-0006` (the typed-sum + Open/Closed-by-decorator commitment)
- `phase-arch-design.md §"Gap 3"` (the intent for this story)
- S1-10's `depgraph-strategy-registry` story (the sibling registry; shape parity)
- S1-01's prior validation report (the `registry.py` vs. `freshness.py` deviation that this story inherits)

## Stage 4 — Synthesizer resolution

### Conflict resolution

No critic-vs-critic conflicts. Findings cluster:

- Cov-F1 + Cov-F2 + Cov-F3 + Cov-F4 + Cov-F5 + Cov-F6 + Cov-F7 + Cov-F8 are all harden-tier and additive.
- TQ findings reinforce Cov findings (mutation-resistance gaps are both Coverage and Test-Quality concerns).
- Cons-C1 (ADR text reconciliation) and DP-D1 (rule-of-three observation) are Notes-for-implementer additions; not ACs (per editor.md: pattern advice is contextual, not observable as an AC).
- DP-D2 (Open/Closed file-boundary invariant) is a Notes paragraph because the verification crosses story boundaries (S5-05 / S6-08 git diff).

### Edits applied to the story

| Section | Before | After |
|---|---|---|
| Status | `Ready` | `Ready (hardened by phase-story-validator 2026-05-15)` |
| Validation notes block | absent | 9-point summary of structural changes + report link |
| AC-1 | exports list only | + `FreshnessRegistry` public methods enumerated (`register`, `registered_names`, `dispatch_all`); `unregister_for_tests` declared public-but-test-only |
| AC-2 | "returns function unchanged" — local registry only | + identity-return verified at both `FreshnessRegistry.register(...)` AND module-level `register_index_freshness_check(...)` |
| AC-3 | "containing both call sites (`module.qualname`)" — test asserted only function-name substrings | + Test must assert the dotted `module.qualname` shape explicitly (catches a regression that strips the module path) |
| AC-4 | "`dict[str, JSONValue]` reuses Phase 0's recursive type alias (do NOT redefine)" — Phase 0 lacks the alias | + Structural fallback to `dict[str, object]` until S1-06 or later promotes `JSONValue`; rebind by import, never redefine; Notes-for-implementer §JSONValue forward-reference paragraph |
| AC-5 | "is total"; "missing slice → invoked with empty dict" | + `head` is threaded **unchanged** through to every dispatched check; see AC-12 |
| AC-7 | "asserts dispatch returns both, dispatching the right slice to each" | + per-check capture variables; asserts `check_scip` receives the scip slice and `check_runtime` receives the runtime slice (catches a `dispatch_all` mutation that shuffles slices) |
| AC-11 (new) | — | Empty-registry totality: `FreshnessRegistry().dispatch_all({}, head="any") == {}` |
| AC-12 (new) | — | `head` propagation determinism: a synthetic check captures `head`; asserted equal to dispatched value |
| AC-13 (new) | — | Exception-propagation contract: registry does NOT catch / log-and-continue / wrap; `RuntimeError` propagates |
| AC-14 (new) | — | Iteration determinism: `list(result.keys()) == registration_order`; pins audit-hash byte-stability |
| TDD plan — red tests | 5 tests | 10 tests + tightened message-format assertion; added: per-slice routing, head propagation, empty registry, exception propagation, iteration order, module-level return-identity |
| Implementation outline | 6 steps | + explicit `FreshnessCheck` typing language (rebinds by import if Phase 0 promotes `JSONValue`); enumerates the new mutation-resistance tests; `dispatch_all` MUST iterate `self._checks.items()` in declaration order |
| Refactor step | 4 bullets | + module docstring MUST name the `registry.py` ≠ `freshness.py` deviation explicitly |
| Notes for implementer | 6 paragraphs | + 5 paragraphs: `head` propagation, iteration order, JSONValue forward-reference, ADR-0006 location deviation, rule-of-three observation (defer to S1-10), Open/Closed file-boundary invariant |

### Mutation-resistance crosswalk after edits

| # | Wrong implementation | Caught by hardened TDD? |
|---|---|---|
| 1 | Silently overwrite on duplicate registration | Yes (unchanged from draft) |
| 2 | Raise on duplicate at dispatch, not register time | Yes (unchanged) |
| 3 | `register` returns `None` (local registry) | Yes (unchanged) |
| 4 | `dispatch_all` returns only `slices.keys()` subset | Yes (unchanged — `test_dispatch_invokes_check_with_empty_dict_when_slice_missing`) |
| 5 | Duplicate error message strips `module.qualname` | **Yes** — `test_duplicate_name_rejected_at_registration_time` now asserts `f".{check_a.__qualname__}" in msg` (dotted form) |
| 6 | `default_freshness_registry` is per-import fresh | Yes (unchanged) |
| 7 | Slice/head argument swap | **Yes** — `test_dispatch_all_threads_head_unchanged_to_every_check` pins captured-head equality |
| 8 | `dispatch_all` shuffles slices | **Yes** — `test_register_and_dispatch_routes_each_slice_to_its_own_check` captures per-check inputs |
| 9 | Empty registry raises | **Yes** — `test_dispatch_all_on_empty_registry_returns_empty_dict` |
| 10 | Check function exception silently swallowed | **Yes** — `test_dispatch_all_propagates_check_exception` |
| 11 | Non-deterministic iteration order | **Yes** — `test_dispatch_all_iteration_is_registration_order` |
| 12 | Module-level `register_index_freshness_check` returns `None` | **Yes** — `test_module_level_decorator_returns_function_unchanged` |
| 13 | `unregister_for_tests` is broken or absent | Yes — singleton tests' `finally` clause would fail if `unregister_for_tests` is missing/wrong |

### Design-pattern crosswalk after edits

| Concern | Pattern applied | Where documented |
|---|---|---|
| Registry pattern (Open/Closed by decorator) | Decorator-factory + `dict[IndexName, FreshnessCheck]` + typed marker error | AC-1, AC-2, AC-3 |
| Newtype for domain primitive | `IndexName: NewType` (S1-05) used as registry key | AC-1; phase-arch-design.md §"Gap 3" |
| Fail-loud at import time | Duplicate-name detection in `register`, raises typed error | AC-3 |
| Composition over inheritance | `FreshnessRegistry` is a plain class; no inheritance | (implicit in Implementation outline) |
| Functional core / imperative shell | Registry is pure data + decorator; structured-log emit is the only side effect | Refactor step; Notes-for-implementer §Open/Closed |
| Open/Closed at file boundary | New index source = new file + new decorator; zero edits to `registry.py`, `index_health.py`, `indices/__init__.py` | Notes-for-implementer §Open/Closed (new paragraph) |
| Premature pluggability avoided | No factory; no Pydantic-model-with-`__call__`; no kernel-extract until rule-of-three | Notes-for-implementer §Rule-of-three (new paragraph) |
| Avoid primitive obsession (registry-side) | Typed `FreshnessCheck` alias; typed `IndexName` key; typed `FreshnessRegistryError` | AC-1, AC-4 |
| Schema vs. consumer | Consumer = `IndexHealthProbe` at S4-01 (out-of-scope here); story documents the hand-off | Out of scope; Notes-for-implementer §Open/Closed |
| ADR-text reconciliation | Story deviates from ADR-0006 §Consequences (`registry.py` vs. `freshness.py`); deviation explicitly documented | Refactor step; Notes-for-implementer §ADR-0006 §Consequences location deviation (new paragraph) |

## Verdict

**HARDENED.** Story now satisfies the validator's "STRONG" bar:

- Every AC is individually verifiable (binary pass/fail).
- AC set collectively guarantees the goal — registration semantics, dispatch totality, head propagation, iteration determinism, error-message shape, and exception propagation are all observable from outside the registry.
- Every plausible wrong implementation in the mutation matrix is caught by at least one test.
- No tautologies, no "no exception thrown" checks, no qualitative-only assertions.
- No contradictions with arch / ADR-0006 / production design / CLAUDE.md commitments; the ADR-text deviation (`registry.py` ≠ `freshness.py`) is explicitly documented and consistent with S1-01's prior hardening.
- Edge cases covered: empty registry, missing slice, exception from check, duplicate registration at import time, slice/head argument swap, iteration order, message-format regression.
- Implementation consumes existing kernels (`probes/registry.py` shape; `IndexName` newtype from S1-05; `IndexFreshness` from S1-01); introduces no premature abstraction (kernel-extract deferred to rule-of-three at S1-10); leaves explicit Open/Closed seam — new index sources land as new files + new decorators with zero edits to the three named paths.
- Domain identifiers are typed (`IndexName`); illegal combinations (duplicate registration) are unrepresentable at runtime via fail-loud raising; the function-type alias is named and exported, not anaemic.

Ready for `phase-story-executor`.
