# Validation report: S1-03 — TaskClass dataclass + registry

**Validated:** 2026-05-26
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S1-03 lands `src/codegenie/eval/registry.py` — the 4th register-helper-backed registry in this codebase (after `probes/registry.py`, `plugins/registry.py`, `transforms/signal_kinds.py`). The story's goal is small and singular, its references all check out, and its TDD plan correctly insists on red-marker-then-green discipline. But the AC list as written treats the precedented kernel-discipline (origin tracking with module.qualname, frame introspection, immutability normalization at the boundary, anti-pattern guards on default-registry mutation) as background knowledge rather than as observable contract. Six structural invariants live in the prose or are implied by the implementation outline without ACs to back them up.

Three blocks, twelve hardens, three nits. No `NEEDS RESEARCH` — every pattern this story needs has at least one direct precedent in this repo (signal_kinds.py:71-145; plugins/registry.py:95-186; probes/registry.py:131-276).

The story's core design choice — **invert the disk-read direction so the decorator stays O(1)** — is a deliberate sharpening of the arch's lines 509-514, not a contradiction. Documented in Notes for implementer as a deliberate divergence flagged for a future doc-sweep PR. The 5-kwarg public signature the story commits to is the contract S2-01 will consume.

Five themes ran through the findings:

1. **Origin-tracking discipline missing as AC** (block — F-DP-1 + F-COV-2 + F-CON-1 + F-TQ-1/F-TQ-2 converged). The story's impl outline retrieves the qualname from `self._by_name[name].rubric_class.__qualname__` — which loses the module path (yields `FirstRubric` not `bench.foo.FirstRubric`). The three sibling registries all store a separate `_origins: dict[name, str]` populated from the caller frame, so collision errors carry the *call site*, not the *class's nominal origin* (which a `from bench.x import R as Y; @register_task_class(...)\nclass R:` shadowing makes useless). Surfaced as new AC-6 + AC-6a + matching tests; the kernel-discipline is Rule-of-three precedent and must be mirrored, not invented.

2. **Immutability normalization not pinned** (block — F-DP-5 + F-COV-9). `@dataclass(frozen=True)` blocks attribute reassignment but does **not** deep-freeze container contents. A caller that retains the original `set` (or `dict`) it passed in can mutate it post-registration; the registry's snapshot moves with the input. Added AC-9 + AC-9a: decorator wraps `breakdown_keys → frozenset(...)`, `failure_mode_taxonomy → MappingProxyType(dict(...))`, `min_cases_for_promotion → MappingProxyType(dict(...))`. Typed-at-the-edge pattern. Test pins `type(...) is frozenset`, `isinstance(..., MappingProxyType)`, and the mutate-then-snapshot independence.

3. **Bad-name surface is under-tested** (block — F-COV-6 + F-TQ-5 + F-DP-10). Original AC-7 tested only `register_task_class(123, ...)`. A `bytes`/`None`/`list`/non-class-target/whitespace-padded-name regression slips. Parameterized into AC-7 (bad name types) + AC-7a (non-class decorator target + re-registration is not idempotent). Whitespace defense is runtime-complementary to fence-CI #4 (which catches non-literal `name` at PR time but doesn't catch `"  foo  "` as a literal).

4. **Direct `register()` path and state-consistency-after-collision not tested** (block-equivalent — F-TQ-7 + F-TQ-8). Added AC-8 (direct `reg.register(tc)` collision-detects, not only the `@register_task_class` helper path) and AC-10 (registry state is consistent after a failed registration — guards a partial-write regression where `_by_name[name] = tc` happens *before* the collision check).

5. **Default-registry mutation in tests is documented as the escape hatch — it's the anti-pattern** (block — F-DP-8). The original Notes-for-implementer guidance read "`default_registry._by_name.clear()` is acceptable inside a fixture; do not expose this as a public method." This is the anti-pattern: it teaches a contributor that touching private state of the production singleton is normal. Rewrote: tests use `TaskClassRegistry()` for isolation; the single place a test must verify the default-targeting path uses `monkeypatch.setattr(codegenie.eval.registry, "default_registry", TaskClassRegistry())` to swap a fresh in. The `Final[TaskClassRegistry]` annotation (AC-4a) is the structural marker that makes reassignment a mypy error in production code; pytest operates below the type-system boundary so the monkeypatch is allowed. Mirrors three sibling registries' conftest discipline.

Hardens covered: `default_registry` typed `Final` (F-DP-3 + AC-4a); `all_task_classes()` returns `tuple` not list (F-TQ-12 + AC-3a); `TaskClassNotFound.available_names` is sorted alphabetically for determinism (F-DP-6 + F-TQ-3 + AC-11); `register(tc)` returns the same instance by identity not equality (AC-3 tightened); registration order preserves correct cardinality after sort (AC-3a `len(...)` check); fresh-instance isolation pins `_by_name is not _by_name` across instances (F-TQ-anti-class-level-state + AC-11a).

Consistency: surfaced one stale dependency declaration (`Depends on: S1-02, S1-04` → corrected to `S1-01, S1-04` — S1-01 is the imported errors module; S1-02's wire models aren't imported by registry.py). Surfaced the deliberate 5-kwarg-vs-3-kwarg divergence from the arch's §Component design block; the story's design wins on more-elaborated rationale (decoupled decorator) and the arch sketch is flagged for a future doc-sweep PR.

Design-pattern review surfaced: (a) registry pattern at Rule-of-three with explicit kernel-extract deferral (precedent: signal_kinds.py:16-29); (b) Open/Closed at the decorator boundary — adding a Phase 7 task class is exactly one new file, zero edits to `registry.py`; (c) functional core / imperative shell (decorator is O(1) pure normalization; loader does I/O); (d) typed-at-the-edge for immutability normalization; (e) `TaskClassName` newtype identified as the future-work primitive-obsession target with the consolidation deferred to a later identifier-cleanup story. None of these become ACs (per skill guidance — pattern names are not observable; observable behaviors derived from the pattern are). The "no edit to `registry.py` for Phase 7" property becomes a Notes-for-implementer paragraph naming the trigger condition.

Verdict: **HARDENED.** Three blocks, twelve hardens, three nits. No `NEEDS RESEARCH`. The mutation set the hardened test suite resists includes (non-exhaustive): drop `frozen=True` or `slots=True` from `TaskClass`; add a 7th field to `TaskClass` without ADR; return a `list` from `all_task_classes()`; sort `available_names` by insertion order; collision message that omits the module path; `_by_name[name] = tc` before collision check; `breakdown_keys` stored as `set` not `frozenset`; `failure_mode_taxonomy` stored as mutable `dict`; idempotent re-registration of the same class; class-level (not instance-level) `_by_name` causing cross-instance bleed; decorator that subclasses or wraps the rubric class; decorator that strips whitespace from `name`; non-string/non-class arguments passing silently; `default_registry` reassignment escaping the `Final` annotation.

## Findings by critic

### Coverage critic

#### F-COV-1: AC-2 doesn't pin TaskClass field-set cardinality
- **Severity:** harden
- **Type:** thin AC
- **Where:** AC-2; arch lines 809-818
- **Why it matters:** AC-2 enumerates the six expected fields but doesn't require a test that **rejects a 7th field** added without an ADR amendment. A regression "tidy-up" PR that adds `description: str` (or `version: str`) to `TaskClass` would silently pass; the type's structural contract drifts. The Phase 5 ADR-0014 precedent introspects via `dataclasses.fields(...)`.
- **Proposed fix:** Tighten AC-2 to require introspecting `{f.name for f in dataclasses.fields(TaskClass)} == EXPECTED_TASK_CLASS_FIELDS` against a module-level `Final[frozenset[str]]` catalog. Adding a field is then explicit (one entry in the catalog + the dataclass).
- **Resolution:** Applied — AC-2 hardened; red test `test_task_class_field_set_is_exactly_the_six_documented` added; `EXPECTED_TASK_CLASS_FIELDS` catalog defined at test-module scope.

#### F-COV-2: Origin tracking is implementation detail, not contract
- **Severity:** block (dup with F-DP-1 / F-CON-1 / F-TQ-1 / F-TQ-2)
- **Type:** missing AC for load-bearing kernel-discipline
- **Where:** AC-6 (original collision AC); impl outline raises with `rubric_class.__qualname__`
- **Why it matters:** The collision error's ergonomic value lives in `module.qualname` — an operator running `grep <origin>` in a multi-bench tree finds the offending file. Bare `__qualname__` loses the module path. The three sibling registries (signal_kinds.py:71-75, plugins/registry.py:117-121, probes/registry.py:154-158) all encode this discipline; the story should mirror, not invent.
- **Proposed fix:** Tighten AC-6 to require the args tuple format `(name, existing_origin, incoming_origin)` where each origin is `module.qualname` (verified via `"." in args[1]` and helper-module introspection). Add AC-6a requiring the `_origins: dict[str, str]` companion map populated via caller-frame introspection.
- **Resolution:** Applied — AC-6 + AC-6a + matching tests (including `_register_from_helper_module` to prove caller-frame discipline, not class-introspection).

#### F-COV-3: `TaskClassNotFound.available_names` sort discipline unpinned
- **Severity:** harden
- **Type:** missing AC
- **Where:** AC-3 (`available_names: tuple[str, ...]` for diagnosability)
- **Why it matters:** Without sort, error messages are non-deterministic across PRs (dict ordering depends on registration order, which depends on import order, which can drift). Snapshot tests downstream fail flakily; operators see noise.
- **Proposed fix:** Add AC-11 — `available_names == tuple(sorted(self._by_name.keys()))`; tests pin sorted order + empty-registry edge case `available == ()`.
- **Resolution:** Applied — AC-11 + two tests (`test_get_missing_raises_with_sorted_tuple_of_available_names`, `test_get_missing_on_empty_registry_carries_empty_available_tuple`).

#### F-COV-4: No AC for `register(tc)` returning the same instance by identity
- **Severity:** nit
- **Type:** under-tightened AC
- **Where:** AC-3
- **Why it matters:** The plugin precedent (plugins/registry.py:122 returns `plugin`) and signal_kind precedent (signal_kinds.py:103 returns `kind`) both encode return-by-identity. A regression that copies the dataclass before returning would defeat `tc is reg.get(tc.name)`-style assertions consumers might want.
- **Proposed fix:** AC-3 tightened to "`is`, not `==`".
- **Resolution:** Applied — AC-3 says "returns the same `tc` instance (`is`, not `==`)"; red test `test_register_returns_same_task_class_instance` pins identity.

#### F-COV-5: No AC for direct `register(tc)` path
- **Severity:** block (dup with F-TQ-7)
- **Type:** missing AC + missing test
- **Why it matters:** The original tests only exercise the `@register_task_class` helper path. Production code (the loader, S2-01) will construct `TaskClass` from disk and call `reg.register(tc)` directly. A regression that puts the collision check only inside the helper (not in `TaskClassRegistry.register`) would let the loader silently overwrite registrations. Defense must live at the kernel.
- **Proposed fix:** Add AC-8 — direct `reg.register(tc)` (no decorator) collision-detects with the same 3-tuple args shape.
- **Resolution:** Applied — AC-8 + red test.

#### F-COV-6: AC-7 covers only one bad-name type
- **Severity:** harden (dup with F-TQ-5)
- **Type:** thin AC
- **Where:** AC-7
- **Why it matters:** `int 123` is one of many bad-name shapes. `bytes`, `None`, `list`, `float`, empty string, whitespace-padded — each is a distinct mutation surface. Parameterizing across the set hardens the guard.
- **Proposed fix:** Parameterize AC-7 across `[int, bytes, None, list, float]` for `TypeError` and `["", "  ", " foo", "foo ", "  foo  "]` for `ValueError`. The whitespace defense is runtime-complementary to fence-CI #4 (which catches non-literal at PR time, not whitespace-in-literal).
- **Resolution:** Applied — AC-7 rewritten with parameterized cases + matching `pytest.mark.parametrize` tests.

#### F-COV-7: Non-class decorator target unpinned
- **Severity:** harden (dup with F-DP-10)
- **Type:** missing AC
- **Where:** AC-7 / decorator behavior
- **Why it matters:** `@register_task_class(...)\ndef f(): pass` would silently pass because `register_task_class` returns a closure that just calls `registry.register(tc)`. The closure should validate `isinstance(rubric_class, type)` (mirror probes/registry.py:139-145).
- **Proposed fix:** Add AC-7a — decorator rejects non-class target with `TypeError`.
- **Resolution:** Applied — AC-7a + red test (`test_decorator_rejects_non_class_target`).

#### F-COV-8: Re-registration of same class — idempotent path or raise?
- **Severity:** harden
- **Type:** missing AC for kernel-discipline
- **Where:** Original AC-6
- **Why it matters:** signal_kinds.py:95-97 makes this explicit: "there is no idempotent path — every duplicate raises, regardless of caller." Without a test, a future "tidy-up" PR could add `if name in self._by_name and self._by_name[name] is tc: return tc` (silent idempotent) and pass every existing test.
- **Proposed fix:** Extend AC-7a — re-registering the same class still raises.
- **Resolution:** Applied — AC-7a + red test `test_re_registering_same_class_still_raises_no_idempotent_path`.

#### F-COV-9: Immutability normalization unpinned
- **Severity:** block (dup with F-DP-5)
- **Type:** missing AC for load-bearing invariant
- **Why it matters:** A caller passing `breakdown_keys=set(...)` (the convenient default) and then mutating it post-registration silently mutates `tc.breakdown_keys` (because `@dataclass(frozen=True)` blocks attribute *reassignment* but the container reference is shared). Same for `failure_mode_taxonomy` as `dict`. The fix is normalization at the decorator boundary.
- **Proposed fix:** Add AC-9 + AC-9a — `breakdown_keys` is normalized to `frozenset`, the two mapping fields are normalized to `MappingProxyType`. Tests pin the post-snapshot independence (mutate input, registry's view unchanged).
- **Resolution:** Applied — AC-9 + AC-9a + three red tests covering each container's normalization independently.

#### F-COV-10: State consistency after collision unpinned
- **Severity:** block (dup with F-TQ-8)
- **Type:** missing AC
- **Why it matters:** A regression that mutates `_by_name[name] = tc` *before* the collision check leaves bad state behind — the existing entry is overwritten, the error is still raised, but `reg.get(name)` returns the *new* (rejected) class. Hidden corruption.
- **Proposed fix:** Add AC-10 — after a collision raises, the existing entry is still retrievable + `all_task_classes()` cardinality unchanged + subsequent unrelated registrations still succeed.
- **Resolution:** Applied — AC-10 + red test `test_state_consistent_after_collision`.

#### F-COV-11: Fresh-instance isolation not pinned at the structural layer
- **Severity:** harden
- **Type:** missing structural AC
- **Where:** AC-4 (singleton); AC-11a (added)
- **Why it matters:** A regression declaring `_by_name: dict[str, TaskClass] = {}` at the **class** scope (not the `__init__` scope) would leak state across every `TaskClassRegistry()` instance — every fresh would silently share registrations. Most tests would still pass; only one structural test catches it.
- **Proposed fix:** AC-11a + a test asserting `a._by_name is not b._by_name` across two fresh instances.
- **Resolution:** Applied — AC-11a + two red tests (`test_fresh_registry_is_empty_and_independent`, `test_by_name_is_per_instance_not_class_level`).

### Test-Quality critic

#### F-TQ-1: Collision test scrapes string, doesn't introspect args
- **Severity:** block (dup with F-COV-2 / F-DP-1)
- **Mutation that slips:** Change the message format from `"duplicate task class 'foo': bench.X and bench.Y"` to `"task class 'foo' already registered (X -> Y)"` — both still pass the `"FirstRubric" in msg` substring check, but the args tuple structure changes and downstream consumers (the CLI exit-code path, S4-01) that introspect `exc.args` break.
- **Proposed fix:** Switch from `str(exc.value) + " ".join(...)` substring scraping to direct `exc.value.args == (name, existing_origin, incoming_origin)` introspection. The args tuple IS the contract; the message format is a presentation concern.
- **Resolution:** Applied — `test_collision_args_tuple_is_3_tuple_with_module_qualified_origins` introspects `args` directly.

#### F-TQ-2: Origin format unpinned
- **Severity:** block (dup with F-COV-2)
- **Mutation that slips:** Use `cls.__qualname__` instead of `f"{cls.__module__}.{cls.__qualname__}"` (or use frame introspection, which is the contract). Two `FirstRubric` classes in different files would collide indistinguishably; the operator has no way to find either file.
- **Proposed fix:** Assert `"." in args[1]`; use a helper module to register the first class and assert the helper's name (not the test's name) appears in `args[1]`.
- **Resolution:** Applied — `_register_from_helper_module` helper proves caller-frame-derived origin.

#### F-TQ-3: `available_names` sort discipline asymmetric test
- **Severity:** harden (dup with F-COV-3)
- **Mutation that slips:** The original test asserted `"a" in rendered and "b" in rendered` — both substrings appear regardless of order. A regression returning `("b", "a")` would pass.
- **Proposed fix:** Pin equality against the exact sorted tuple.
- **Resolution:** Applied — `test_get_missing_raises_with_sorted_tuple_of_available_names`.

#### F-TQ-4: `test_task_class_dataclass_is_frozen_and_slotted` uses broad exception
- **Severity:** nit
- **Mutation that slips:** `with pytest.raises(Exception):` catches anything; a regression that raises `ValueError` from a custom `__setattr__` would still pass even though the intent (`FrozenInstanceError`) is gone.
- **Proposed fix:** Tighten to `(dataclasses.FrozenInstanceError, AttributeError)`.
- **Resolution:** Applied — exception class is now `(dataclasses.FrozenInstanceError, AttributeError)`.

#### F-TQ-5: Bad-name surface under-tested
- **Severity:** harden (dup with F-COV-6)
- **Resolution:** Applied via parameterized tests.

#### F-TQ-6: `test_all_task_classes_returns_deterministic_sorted_tuple` cardinality untested
- **Severity:** harden
- **Mutation that slips:** A regression deduplicating by `name.lower()` or returning every-other entry would still pass the N=2 sort test as long as both names happen to survive.
- **Proposed fix:** Add a third name (e.g., `"mango"`) that sorts between, and assert `len(...) == 3` + `isinstance(..., tuple)`.
- **Resolution:** Applied — three names + length + type assertions.

#### F-TQ-7: No direct-`register(tc)` path test
- **Severity:** block (dup with F-COV-5)
- **Resolution:** Applied via AC-8.

#### F-TQ-8: No state-after-collision test
- **Severity:** block (dup with F-COV-10)
- **Resolution:** Applied via AC-10.

#### F-TQ-9: `default_registry` singleton test doesn't verify default-targeting path
- **Severity:** harden
- **Mutation that slips:** The original `test_default_registry_is_module_singleton_separate_from_fresh_instances` only proved a fresh != default. It did NOT prove that omitting `registry=` from `register_task_class` actually targets the default. A regression making the kwarg required (no default) would slip.
- **Proposed fix:** Add `test_register_without_kwarg_writes_into_default_registry` using `monkeypatch` to swap the default with a fresh and asserting the omitted-kwarg call lands in the swapped fresh.
- **Resolution:** Applied.

#### F-TQ-10: `Final[TaskClassRegistry]` annotation runtime tripwire missing
- **Severity:** harden (dup with F-DP-3)
- **Mutation that slips:** A regression dropping the `Final` annotation entirely passes every existing test (mypy catches the static error, but mypy isn't run in every test cycle).
- **Proposed fix:** Add runtime introspection via `typing.get_type_hints(...)`.
- **Resolution:** Applied — `test_default_registry_is_annotated_Final`.

#### F-TQ-11: No fresh-instance independence test
- **Severity:** harden (dup with F-COV-11)
- **Resolution:** Applied via two tests under AC-11a.

#### F-TQ-12: `all_task_classes()` tuple-vs-list type discipline unpinned
- **Severity:** harden
- **Mutation that slips:** Returning `sorted(...)` (a list, not tuple); downstream consumers that do `for tc in result` still work, but `result + (new,)` operations break.
- **Proposed fix:** `isinstance(result, tuple)`.
- **Resolution:** Applied — AC-3a + matching test.

#### F-TQ-13: Decorator-returns-class-unmodified test relies on identity but doesn't pin attribute-preservation
- **Severity:** nit
- **Proposed fix:** Add a sentinel class attribute and assert it survives the decoration.
- **Resolution:** Applied — `test_decorator_returns_class_unmodified` now declares `sentinel: str = "marker"` and asserts post-decoration access.

### Consistency critic

#### F-CON-1: Origin-tracking discipline matches arch but not impl outline
- **Severity:** block (dup with F-COV-2 / F-DP-1)
- **Where:** arch line 523 ("collision raises `TaskClassAlreadyRegistered(name, existing_qualname, incoming_qualname)` — mirrors `SignalKindAlreadyRegistered` from Phase 5 ADR-0003") + signal_kinds.py:71-75 + impl outline
- **Verdict:** The arch's "qualname" phrasing is ambiguous; the load-bearing precedent (signal_kinds.py + plugins/registry.py + probes/registry.py) is `module.qualname`. Story's impl outline saying `rubric_class.__qualname__` diverges from precedent. Story-as-truth: the precedent wins.
- **Resolution:** Applied — impl outline + AC-6/AC-6a all updated to `module.qualname` via caller-frame introspection.

#### F-CON-2: `Depends on: S1-02, S1-04` is stale
- **Severity:** info → harden
- **Where:** Story header
- **Verdict:** S1-02 (wire models — `BenchScore`, `BenchCase`, etc.) is NOT imported by `registry.py`. The imports per the impl outline are `from codegenie.eval.errors import ...` (S1-01) and `from codegenie.eval.rubric import Rubric` (S1-04). The `Depends on:` line should read `S1-01, S1-04`. S1-04 transitively depends on S1-02 (the Rubric Protocol's `score` signature references `BenchCase` / `BenchScore`), but this story doesn't import them.
- **Resolution:** Applied — corrected to `S1-01 (errors), S1-04 (Rubric Protocol)`.

#### F-CON-3: Public-signature divergence from arch lines 509-514
- **Severity:** harden (surface, no auto-fix to arch)
- **Where:** arch §Component design → registry.py public-interface block (3 kwargs); story's impl + AC-5 (5 kwargs)
- **Verdict:** The arch sketches the decorator with `name`, `bench_path`, `min_cases_for_promotion` only; the story adds `breakdown_keys` + `failure_mode_taxonomy` as explicit kwargs. The arch's authoring assumption (line 523) was that the decorator reads `breakdown_keys.py` and `failure_modes.yaml` from disk via `loader.py` helpers; the story **flips the read direction** (loader reads, then calls decorator with kwargs) so the decorator stays O(1) and stdlib-only. The story's design wins on more-elaborated rationale (decoupled decorator; loader-as-the-I/O-boundary; production-ADR-style "heavy work moves to load time"). The divergence is deliberate sharpening, not contradiction.
- **Resolution:** Applied — Notes for implementer documents the divergence explicitly; flagged for a future doc-sweep PR but do not auto-edit `phase-arch-design.md`.

#### F-CON-4: ADRs referenced all check out
- **Severity:** info
- **Verdict:** ADR-0004, ADR-0008, Phase 5 ADR-0003, Phase 5 ADR-0006 all exist; arch sections cited (§Component design → registry.py, §Data model — TaskClass, §Edge cases #7, #8) all present. Cross-phase precedent ADR (Phase 5 ADR-0003) and Phase 0 probe_registry mention check out. No stale refs.

#### F-CON-5: CLAUDE.md commitments respected
- **Severity:** info
- **Verdict:** "Facts, not judgments" → preserved (registry stores facts; judgments live in promotion gate). "Extension by addition" → adding a task class is one new file, zero edits to `registry.py`. "Honest confidence" → not applicable directly. "Make illegal states unrepresentable" → tagged-union-style is N/A but newtype-pattern target identified for future work (`TaskClassName`). "Fail loud" → bad-name types/values/non-class targets all raise eagerly; default-registry mutation discipline anti-pattern surfaced and forbidden.

#### F-CON-6: Story's `_origins` storage discipline aligns with sibling registries
- **Severity:** info
- **Verdict:** `plugins/registry.py:101` ("`Origin strings ... are kept alongside so duplicate errors can name BOTH call sites without re-introspecting the prior plugin (which a caller could have mutated)`") is the exact rationale. Mirrored in this story's impl outline + Notes for implementer.

### Design-Patterns critic

#### F-DP-1: Origin tracking via caller-frame is the kernel-discipline; story under-specifies
- **Severity:** block (dup with F-COV-2 / F-CON-1 / F-TQ-1/F-TQ-2)
- **Smell:** Implicit kernel discipline → not enforced as observable contract
- **What's wrong:** Three sibling registries store `_origins: dict[name, str]` from caller-frame introspection; the story's impl outline retrieves from class-introspection (`rubric_class.__qualname__`), which is structurally weaker (loses module path; doesn't survive `import as` aliasing of the class object). This is the **Rule-of-three precedent** — the registry pattern is now in its 4th instance; mirror, don't invent.
- **Proposed fix:** Inject `_origins` companion dict + caller-frame introspection in `register_task_class`; AC pins both.
- **Resolution:** Applied — AC-6a + impl outline rewritten + helper-module test in TDD plan.

#### F-DP-2: Rule-of-three crossed for registry pattern; defer kernel-extract
- **Severity:** info
- **Verdict:** Per signal_kinds.py:16-29 explicit YAGNI rationale, the four registries' dispatch surfaces diverge (`for_task` + heaviness sort; resolve-by-scope; plain `__contains__`; plain `get`/`all_task_classes`). A shared `KernelRegistry[K, V]` base would couple them artificially. **Defer.** Surfaced in Notes for implementer as the future-trigger condition (when a 6th register-helper-backed registry appears, the kernel-extract has 5 precedents to grep and the design conversation has more leverage).
- **Resolution:** Notes for implementer paragraph added.

#### F-DP-3: `default_registry: Final[TaskClassRegistry]` annotation missing
- **Severity:** harden (dup with F-TQ-10)
- **Smell:** Implicit immutability of module-level singleton; production code could rebind silently
- **Proposed fix:** AC-4a — `Final` annotation + runtime introspection tripwire.
- **Resolution:** Applied.

#### F-DP-4: `all_task_classes()` sort-by-name diverges from plugin precedent (insertion order); deliberate
- **Severity:** info
- **Verdict:** plugins/registry.py:140-154 preserves insertion order because the audit chain depends on it. Task class registry has no chain dependency; sort-by-name gives fence-CI a deterministic walk surface. The divergence is correct; documented in the Notes for implementer paragraph about precedent.

#### F-DP-5: Immutability normalization (typed-at-the-edge) missing
- **Severity:** block (dup with F-COV-9)
- **Resolution:** Applied via AC-9 + AC-9a.

#### F-DP-6: `available_names` sort discipline for `TaskClassNotFound`
- **Severity:** harden (dup with F-COV-3 / F-TQ-3)
- **Resolution:** Applied via AC-11.

#### F-DP-7: `_by_name` per-instance discipline
- **Severity:** harden (dup with F-COV-11)
- **Smell:** Class-attribute-state aliasing across instances
- **Resolution:** Applied via AC-11a + the class-vs-instance state test.

#### F-DP-8: Default-registry mutation documented as escape hatch — anti-pattern
- **Severity:** block
- **Smell:** Anti-pattern documented as sanctioned in Notes for implementer
- **What's wrong:** Original Notes-for-implementer wrote "`default_registry._by_name.clear()` is acceptable inside a fixture; do not expose this as a public method." This teaches contributors to touch private state of the production singleton — the exact pattern the three sibling registries forbid. Three sibling registries enforce: tests use `fresh()` constructor or session-scoped conftest fixtures; never mutate `_by_name`.
- **Proposed fix:** Rewrite Notes for implementer to forbid `_by_name` mutation; document `monkeypatch.setattr(...)` as the only sanctioned way to verify default-targeting path; cite the `Final[TaskClassRegistry]` annotation as the structural marker.
- **Resolution:** Applied — Notes for implementer rewrote the paragraph; AC-4a pins the `Final` annotation.

#### F-DP-9: Open/Closed at the decorator boundary (no edit)
- **Severity:** info
- **Verdict:** The story's design correctly establishes Open/Closed: adding a Phase 7 task class is exactly one new `bench/migration-chainguard-distroless/registration.py` file + one `@register_task_class(...)` call; **zero edits** to `registry.py`. Surfaced as a Notes-for-implementer paragraph naming the trigger condition for a future implementer who might be tempted to add a Phase-7 special case here.

#### F-DP-10: Non-class decorator target check
- **Severity:** harden (dup with F-COV-7)
- **Resolution:** Applied via AC-7a.

#### F-DP-11: `TaskClassName` newtype primitive-obsession surface
- **Severity:** info
- **Verdict:** Task-class slug is a domain identifier crossing ≥ 2 module boundaries (registry, loader, runner, audit chain). A `TaskClassName = NewType("TaskClassName", str)` (mirroring `PluginId`, `SignalKind`, `ProbeId` in `codegenie.types.identifiers`) would close primitive-obsession on `name: str`. **Not landing here** — the surface is bounded to one task class in Phase 6.5; the consolidation has higher leverage when Phase 7 ships the second task class. Surfaced in Notes for implementer as the future-work trigger.

#### F-DP-12: Functional core / imperative shell — decorator is pure
- **Severity:** info
- **Verdict:** Decorator is O(1) container normalization + registration. No I/O, no side effects beyond the registry mutation (which is the explicit purpose). Loader (S2-01) is the impure shell that reads disk and calls the decorator. Correct shape.

#### F-DP-13: `TaskClass` as plain dataclass vs Pydantic
- **Severity:** info
- **Verdict:** The arch explicitly motivates this choice (line 533): "`TaskClass` … plain dataclass because it carries a `type[Rubric]` object that doesn't serialize cleanly and doesn't need validation (best-practices-lens choice, consistent with `final-design.md §Components → models.py`)." Correct. No edit.

#### F-DP-14: Whitespace defense (`name.strip()`) is fail-loud, not silent-normalize
- **Severity:** info
- **Verdict:** The decision to *raise* on whitespace-padded names rather than silently strip them is the right fail-loud posture (CLAUDE.md). Silent normalization would let a typo'd `" foo "` registration silently mismatch the bench directory `foo`. Documented in AC-7 + Notes for implementer.

## Conflict resolution

| Conflict | Resolution |
|---|---|
| Coverage F-COV-2 + Test-Quality F-TQ-1/F-TQ-2 + Consistency F-CON-1 + Design-Patterns F-DP-1 all propose the same origin-tracking fix. | Merged into single AC-6 + AC-6a + matching tests + impl outline rewrite. Design-Patterns framing (caller-frame introspection mirror of signal_kinds.py) cited in the Notes for implementer; the ACs themselves are observable contracts (`"." in args[1]`; helper-module proves caller-frame discipline). |
| Design-Patterns F-DP-2 (extract `KernelRegistry[K,V]` base) vs YAGNI / signal_kinds.py:16-29 precedent. | YAGNI wins. Documented in Notes for implementer as deferred extract with future-trigger condition (6th register-helper-backed registry). |
| Design-Patterns F-DP-11 (`TaskClassName` newtype) vs Rule 2 (YAGNI) + scope discipline. | YAGNI wins for this story; surfaced as deferred-extract future-trigger in Notes for implementer. |
| Coverage F-COV-7/F-COV-8 (semantic validation in decorator) vs separation of concerns (validation belongs at loader/fence-CI per ADR-0008 + ADR-0004). | Separation-of-concerns wins. Decorator does structural normalization (immutability, type/value guards on `name` and `rubric_class`) only; semantic validation of `breakdown_keys` substrings / severity Literal closure / `min_cases_for_promotion` bounds lives at S2-01 + fence-CI #5/#6. Out of scope expanded with explicit deferrals. |
| Consistency F-CON-3 (arch lines 509-514 sketch 3 kwargs vs story uses 5 kwargs). | Story wins on more-elaborated rationale (decoupled decorator; O(1) decoration; loader does I/O). Flagged in Notes for implementer for a future doc-sweep PR; no auto-edit to `phase-arch-design.md`. |
| Design-Patterns F-DP-8 (anti-pattern: documenting `default_registry._by_name.clear()` as a sanctioned escape hatch in tests). | Forbid the pattern. Rewrote Notes for implementer; introduced `monkeypatch.setattr(...)` as the only sanctioned default-targeting verification path; `Final[TaskClassRegistry]` annotation pinned as the structural marker. |
| No critic-to-critic conflicts otherwise. | — |

## Edits applied

Story file edited in place. New `Validation notes` block under the story header. ACs renumbered from 9 unnumbered checkboxes to 17 explicit AC-N entries. Implementation outline rewritten to incorporate origin-tracking via caller-frame introspection, immutability normalization via `MappingProxyType` + `frozenset`, `Final[TaskClassRegistry]` annotation, and fail-loud validation on bad `name` types/values + non-class decorator targets. TDD plan rewritten — original 7 tests grew to 24 (parameterized cases counted as single tests; in practice the suite expands to ~32 parameterized invocations). Out of scope grew from 5 to 9 bullets. Notes for implementer grew from 7 bullets to 14, with the anti-pattern guard on default-registry mutation prominently rewritten. Refactor step bullets expanded from 5 to 6.

Pre/post diff summary:

| Section | Before | After |
|---|---|---|
| Status | `Ready` | `HARDENED` |
| Depends on | `S1-02, S1-04` (stale) | `S1-01 (errors), S1-04 (Rubric Protocol)` |
| ACs | 9 unnumbered checkboxes | 17 explicit AC-N (AC-1..AC-13 + AC-3a/AC-4a/AC-6a/AC-7a/AC-9a/AC-11a) |
| TDD plan red tests | 7 unit tests | 24 unit tests (7 original + 17 new), with two parameterized — `bad name types` (5 cases) and `whitespace-padded names` (5 cases) |
| Implementation outline | 3 steps | 4 steps; decorator now declares 5 kwargs + origin capture + immutability normalization + non-class guard + name validation |
| Out of scope items | 5 bullets | 9 bullets (added: `breakdown_keys` substring ban deferral; severity Literal closure deferral; `min_cases_for_promotion` bounds deferral; `TaskClassName` newtype deferral; `bench_path` normalization deferral; Sigstore deferral) |
| Notes for implementer | 7 bullets | 14 bullets (added: collision-error format contract; origin-tracking via caller-frame; immutability normalization; default-registry mutation **forbidden** with sanctioned monkeypatch escape; public-signature deliberate divergence from arch; registry-pattern lineage + kernel-extract deferral; Open/Closed at decorator boundary; `TaskClassName` future-trigger; no `Protocol[TaskClassRegistry]` rationale; ~60-LOC implementation envelope) |
| Refactor step bullets | 5 | 6 (added: anti-pattern guard on default-registry mutation; expanded docstring to cite all four ADRs + lineage + signature sharpening rationale) |

## Verdict rationale

**HARDENED.** Three blocks (F-COV-2 / F-CON-1 / F-TQ-1 / F-TQ-2 / F-DP-1 converged on origin-tracking; F-COV-9 / F-DP-5 converged on immutability normalization; F-DP-8 anti-pattern guard rewrite — all in-place-fixable with precedented patterns). Twelve hardens. Three nits. No `NEEDS RESEARCH` — every pattern is precedented in this repo: caller-frame introspection (`transforms/signal_kinds.py:125-145`); `_origins` companion dict (`plugins/registry.py:95-123`); `Final[Registry]` annotation (`plugins/registry.py:172`); `tuple` return + sort discipline (`probes/registry.py:189-196`); fresh-instance isolation via constructor (signal_kinds.py:109-112; plugins/registry.py:175-186); the typed-at-the-edge `MappingProxyType` + `frozenset` boundary pattern is in `tccm/` (multiple) and `pyproject.toml` config models. The mutation set the hardened suite resists is enumerated in the Summary section.

Design-pattern posture: validator endorses (a) the registry-pattern lineage at Rule-of-three with explicit kernel-extract deferral; (b) functional core / imperative shell (decorator pure; loader impure); (c) Open/Closed at the decorator boundary (extension by addition for Phase 7+); (d) typed-at-the-edge immutability normalization; (e) anti-pattern guard against default-registry mutation. None elevated to ACs (per skill guidance — pattern names are not observable; observable behaviors derived from them are). `TaskClassName` newtype identified as the deferred-extract target.

## Recommended next step

`phase-story-executor` to implement. Story is ready: every AC is individually verifiable; the AC set collectively guarantees the goal (registry + decorator + `default_registry` singleton with structural disciplines pinned, not merely sampled); every test in the TDD plan would fail under a wrong implementation; the prescribed implementation pattern is precedented in three sibling registries; the anti-pattern (default-registry mutation in tests) is forbidden and the monkeypatch escape is documented; the future-extract opportunities (`TaskClassName` newtype, shared `KernelRegistry[K,V]` base) are flagged with clear trigger conditions but explicitly deferred.
