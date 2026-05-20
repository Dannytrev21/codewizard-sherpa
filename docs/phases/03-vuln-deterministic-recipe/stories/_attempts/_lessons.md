# Phase 3 — cross-story lessons (executor)

Append-only journal of reusable takeaways discovered during
phase-story-executor runs in this phase. New entries at the bottom.

## Lessons

1. **`@runtime_checkable` Protocols do not populate `__abstractmethods__`
   the way `abc.ABC` does** (S2-01). Fence tests that assert a
   Protocol's "exactly N members" must enumerate via the union of
   `dir(Cls)` and `Cls.__annotations__.keys()` — `dir()` alone omits
   attribute-only annotations on every Python version we've tested.

2. **Module-docstring strings are grep-able by Phase 2 fences** (S2-01).
   `test_zero_strategies_registered_in_phase2` does a literal substring
   search for `@register_dep_graph_strategy`. Referencing a sibling
   registry's decorator with the `@` prefix inside narrative prose trips
   it even when the reference is purely informational. Drop the `@` or
   use sufficiently distinct phrasing in cross-registry docstrings.

3. **`TYPE_CHECKING`-only forward-ref stubs still need typed fields**
   when production code reads attributes through them under `mypy
   --strict` (S2-01). A bare `class PluginManifest: ...` stub fails
   `[attr-defined]` on `plugin.manifest.name`. Add the minimal field
   set the kernel actually reads; the downstream story expands the
   stub to the full Pydantic model. **2026-05-19 update (S2-04):** as
   the consuming surface widens past `.name`, replace the stub with
   `if TYPE_CHECKING: from codegenie.plugins.manifest import
   PluginManifest as PluginManifest`. The real Pydantic model is
   only loaded at type-check time, so the kernel stays cold-start
   clean while every documented field is type-known.

4. **Avoid lazy intra-package imports if a fence test pops your
   package mid-session** (S2-04). `tests/fence/test_no_llm_in_transforms.py`
   does `for k in sys.modules: if k.startswith("codegenie.plugins."):
   sys.modules.pop(k)` and re-walks. A method that does
   `from codegenie.plugins import resolver as _resolver` inside its
   body fetches the new (C2) module after the pop, while the test's
   already-bound names hold the old (C1). The `_resolver._unpack`'s
   `case Concrete(...)` then sees a C1 instance of Concrete and trips
   `assert_never`. Bind the symbol at module load instead — the value
   is frozen at registry-load time and stays consistent with the
   test's globals. If you legitimately need a lazy import to break a
   real cycle, the lazy site is also the place a future test's
   module-reload will introduce class-identity drift; surface the
   trade-off.

5. **Pydantic v2 BaseModel with `arbitrary_types_allowed=True` still
   runtime-checks Protocol fields** (S2-04). A field typed as a
   `runtime_checkable` Protocol (e.g.
   `composed_adapters: dict[PrimitiveName, Adapter]`) rejects
   `object()` instances at `model_validate` time because the
   Protocol implements `__instancecheck__`. Test fakes for adapter
   maps need at least the Protocol's attribute set (here,
   `primitive: PrimitiveName`).

6. **Test fakes can — and often should — bypass production
   validators** (S2-04). The S2-02 `PluginManifest.name` validator
   rejects names like `a-plugin` (regex requires three `--`-segments)
   and the literal `universal--*--*` (regex rejects `*`). Resolver
   tests need both: `a-plugin` for sort tie-breakers,
   `universal--*--*` for the fallback fixture. Use
   `PluginManifest.model_construct(...)` in test fixtures; the
   manifest loader's own tests cover the production regex. Coupling
   resolver tests to the production name format would mean every
   sort-tie test ships with three nonsense `--`-segments.

7. **Story preconditions can become stale between HARDENED and GREEN**
   (S3-05). AC-5 declared "the `SemverVersion` newtype does not yet
   exist" but S3-03 had landed it the day before. The right move is
   to honour the AC literally (`plugin_version: str`) and surface the
   elevation opportunity in the attempt log — widening an AC during
   execution erodes the validator's contract. Phase-3 cleanup should
   audit all "X does not yet exist" claims in HARDENED stories at
   execution time.

8. **`from __future__ import annotations` defeats
   `__annotations__["x"] is ExpectedClass`** (S3-04 lesson, S3-05
   repeat). The annotation is stored as the source-text spelling,
   not resolved. Pin the string instead: `assert annotation ==
   "SandboxedPath"`. The canonical precedent is
   `tests/unit/plugins/test_bundle_builder.py:181-189`.

9. **Two atomic-write inlines is still under the rule-of-three**
   (S3-05). `_atomic_write_bytes` (`plugins/cache.py`) and
   `_atomic_write_text` (`plugins/cache_gc.py`) join Phase-0
   `cache/store.py:_atomic_write_bytes` as the third call site by
   spirit but story §Notes DP-G defers extraction explicitly.
   Surface the cleanup when the next atomic-write site lands (likely
   Phase 4 recipe-cache writer); `codegenie._fs_atomic` is the
   pre-blessed home.

10. **Local-raise wrappers have drifted on kwarg name** (S3-05).
    `BundleBuilderRaise(error=...)` (S3-04) vs
    `BundleCacheRaise(model=...)` (S3-05). Both wrap a frozen
    Pydantic value. When a third local-raise class appears,
    standardise on one kwarg name in a sweep — pick `error` (matches
    the rest of `codegenie.errors` taxonomy vocabulary) and update
    S3-05 + every catch site. Not a now-bug; flag as Phase-3 cleanup.

11. **Adding a sum-type variant is additive widening** (S4-02).
    `JailedSubprocessResult` grew from five to six variants
    (`JailSetupFailed`). Per S4-01's contract snapshot test policy
    (Step 9 risk #4), additive widening is permitted with: golden
    regen, exhaustiveness-arm addition, variant-count assertion
    update. The subprocess-mypy negative fixture becomes *stricter*
    automatically (omitting any arm still fails mypy). Future Port
    extensions follow this template.

12. **`get_type_hints` strips `Annotated[...]`** (S4-02). When
    pinning a Port's return annotation that uses
    `Annotated[Union[...], Field(discriminator="kind")]`, pass
    `include_extras=True` or the test fails because the resolved
    hint is the bare Union, not the Annotated alias. Cross-ref:
    S4-01 AC-2 / S4-02 AC-1.

13. **mypy treats `sys.platform != "linux"` as a constant on
    darwin** (S4-02). Guarded-early-return shapes
    (`if sys.platform != "linux": return ...; <linux code>`)
    report the linux code as `Unreachable` under `mypy --strict`
    when checked on darwin. Invert to
    `if sys.platform == "linux": <code>; return <default>` for
    bidirectional clean.

14. **Hypothesis + `tmp_path` needs
    `suppress_health_check=[HealthCheck.function_scoped_fixture]`**
    (S4-02). `@given` doesn't reset the fixture between generated
    inputs — fine for capture-style tests (no fixture mutation);
    surprising for tests that mutate fixture state. Suppress
    explicitly + document in the test docstring why it's safe.

15. **Fail-not-skip needs a CI provisioning predecessor**
    (S4-02). The story's `pytest.fail("bwrap missing on Linux")`
    discipline (ADR-0006 §Consequences + High-level-impl L310) is
    the right destination, but it requires the CI YAML to install
    `bubblewrap` first — and that edit is S9-01's scope. Land an
    Adapter story whose loud-fail-on-Linux integration tests
    presume S9-01 has already run, and the integration lane on
    master will hard-fail until S9-01 lands. Resolution mirrors
    AC-15 / S4-02 Attempt 2: `pytest.xfail("S9-01 pending — ...")`
    for the bwrap-missing path; the AC-15 CI-setup fence is the
    gate that flips to a hard fail post-S9-01.

16. **A validator can harden two ACs into a mutual contradiction**
    (S5-02 — BLOCKED). The phase-story-validator's harden pass
    independently (a) strengthened AC-Surface-2 to require a
    `mypy --strict` `RecipeEngine`-Protocol assignment and (b)
    rewrote `apply` to return a 2-tuple `(RecipeOutcome, Transform
    | None)` — never cross-checking that S5-01's *landed*
    `RecipeEngine.apply(...) -> RecipeOutcome` makes those two
    incompatible (a tuple return is not covariantly assignable to
    `RecipeOutcome`). Lesson: when a story both (i) implements a
    Protocol shipped by a prior GREEN story and (ii) changes the
    shape of the implementing method, the executor's Stage-1 must
    diff the method signature against the *as-built* Protocol, not
    the story's prose. The deeper design gap: a `RecipeEngine` has
    no sanctioned channel to surface its produced `Transform`
    object — `Applied` carries only `transform_id` and no
    `TransformRegistry` exists. Decide that (architect scope:
    widen `Applied`, change the Protocol, or add a registry story)
    *before* any engine story can be executed.

17. **One unresolved architecture contradiction blocks every story
    in its dependency cone — not just the one that surfaced it**
    (S5-03 — BLOCKED). S5-03 (`OpenRewriteRecipeEngine` scaffold)
    was `HARDENED` and is the next un-executed story after the
    BLOCKED S5-02, yet it could not run: it carries the *same*
    `apply` 2-tuple vs. `RecipeEngine`-Protocol-conformance
    contradiction (lesson #16), because it implements the same
    S5-01 Protocol the same way. It also fails on secondary
    prerequisites — `NpmLockfileRecipeEngine` and the
    `tests/fence/test_engines_no_*` engine fences are S5-02
    deliverables that never shipped, so S5-03's AC-Surface-2(c),
    AC-Surface-4 and AC-Pure-2 reference artifacts that do not
    exist. Lesson: when a story is BLOCKED on an architecture
    decision, do not advance to the next story in the same cone
    hoping it is independent — first diff the next story's
    contract against the *as-built* code and against what the
    BLOCKED story was supposed to ship. The fix for the whole
    cone is one `/phase-architect` pass, not N executor retries.
    A `HARDENED` status only means the story was self-consistent
    when validated; a *sibling* story later turning BLOCKED can
    still invalidate it.

18. **A two-AC contradiction in a story cone is fixed by one
    architecture decision, not by editing the loudest story**
    (S5-02 / S5-03 unblocked via S5-01b). The S5-02/S5-03 BLOCKED
    contradiction (lesson #16) was the *symptom* of a missing
    component: a `RecipeEngine` had no sanctioned channel to
    surface its produced `Transform`. The resolution was not to
    patch either engine story's ACs in isolation but to (a) take
    the architecture decision (ADR-0014 — a per-workflow
    `TransformRegistry`; `apply` stays `-> RecipeOutcome`), (b)
    write + execute one small new story (S5-01b) for the missing
    component, then (c) de-contradict S5-02/S5-03 against the now-
    existing component. Lesson: when the executor's Stage-1 hard
    gate fires on a cross-story contradiction, look for the
    *missing collaborator* the contradiction implies — the fix is
    usually a new story slotted upstream, plus a surgical AC
    rewrite downstream, not a forced edit to the story that
    happened to surface it.

19. **`scripts/regen_golden.py --check --portfolio` is
    environment-sensitive** (observed 2026-05-20, macOS / Python
    3.13). Run standalone on a clean tree it materializes
    `tsconfig.json` into portfolio fixtures and the live
    `codegenie gather` output diverges from the committed
    (Linux-generated) goldens, failing
    `tests/golden/test_goldens_match.py::test_goldens_match_live_output`.
    The committed goldens were generated under the CI Linux /
    Python-3.11-3.12 toolchain. Lesson: a `make check` failure on
    that one test, on a macOS dev box, is most likely this
    pre-existing toolchain mismatch — confirm by reverting your
    change from the import graph and running the script
    standalone before treating it as a regression. Do not "fix"
    it by committing macOS-regenerated goldens — that breaks CI.
