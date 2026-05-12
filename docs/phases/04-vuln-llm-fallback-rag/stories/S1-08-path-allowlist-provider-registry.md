# Story S1-08 — `NpmPathAllowlistProvider` + `PathAllowlistProvider` registry shape

**Step:** Step 1 — Plant the contracts, the two ADR-gated Phase-3 edits, and the fence-CI rules every Phase 4 component consumes
**Status:** Ready
**Effort:** S
**Depends on:** S1-02
**ADRs honored:** ADR-P4-003, ADR-P4-015

## Context

Foundational; Phase-7 anchor. The `Plan.target_files` allowlist is the single defense that makes "an injected LLM cannot edit source files" structurally true (`../phase-arch-design.md §"Executive summary"`). Phase 4 ships only the npm allowlist (`package.json`, the four lockfile variants); Phase 7 (Chainguard distroless) will register a Dockerfile allowlist; Phase 15 (recipe authoring) may register a third. This story plants the **registry seam** — a `PathAllowlistProvider` Protocol + decorator-based registration — so Phase 7's extension is a new provider class, never an edit to `OutputValidator` or to `ManualPatch`'s validator. Decorator-vs-YAML registration is Open Question #1 in the manifest; this story picks decorator for v0.4.0 with a future-flexible signature.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design"` #3 — "Phase 7 extends the allowlist by registering a `PathAllowlistProvider` — never by editing `OutputValidator`."
  - `../phase-arch-design.md §"Logical view"` "Central abstractions vs scaffolding" — the npm allowlist is named as "the single most consequential decision in Phase 4".
- **Phase ADRs:**
  - `../ADRs/0003-plan-envelope-kind-and-target-files-allowlist.md` — ADR-P4-003 — the policy: hard-coded in Phase 4, extension by registration in Phase 7+.
  - `../ADRs/0015-solved-example-schema-task-class-generic.md` — ADR-P4-015 — `task_class` is the key the registry dispatches on.
  - `../ADRs/README.md` "Decisions noted but not yet documented" #1 — registry shape.
- **Existing code:**
  - `src/codegenie/recipes/engine.py` — Phase-3 engine registry pattern (`@register_recipe_engine`); copy this idiom.
  - `src/codegenie/llm/contract.py` (from S1-02) — `Plan.kind`, `ManualPatch.target_files` hard-coded validator. After this story lands, the validator's allowlist comes from the registry default.

## Goal

Land `src/codegenie/llm/path_allowlists/` with a `PathAllowlistProvider` Protocol, a decorator-based registry, and a default `NpmPathAllowlistProvider` that returns the five npm-allowlist filenames hard-coded today in `ManualPatch.target_files`.

## Acceptance criteria

- [ ] `src/codegenie/llm/path_allowlists/__init__.py` exports `PathAllowlistProvider`, `register_path_allowlist`, `get_allowlist`, `NpmPathAllowlistProvider`.
- [ ] `PathAllowlistProvider` is a `@runtime_checkable` Protocol with `task_class(self) -> str` and `allowed(self) -> frozenset[str]`.
- [ ] `@register_path_allowlist` is a class decorator; it inserts the class instance into a module-level dict keyed by `task_class()`. Duplicate `task_class` registration raises `ValueError` at import time (loud — Rule 12).
- [ ] `NpmPathAllowlistProvider` registers as `task_class="vuln"` and returns `frozenset({"package.json","package-lock.json","yarn.lock","pnpm-lock.yaml","npm-shrinkwrap.json"})`.
- [ ] `get_allowlist(task_class: str) -> frozenset[str]` returns the registered provider's `allowed()` and raises `KeyError` if the task_class isn't registered.
- [ ] `tests/unit/llm/test_path_allowlist_registry.py` covers:
  - default `NpmPathAllowlistProvider` returns the five npm filenames;
  - registering a duplicate `task_class="vuln"` raises at import time;
  - Phase-7-preview: registering a stub `DockerfilePathAllowlistProvider(task_class="chainguard")` succeeds and `get_allowlist("chainguard")` returns the Dockerfile set without disturbing the npm default;
  - registry's set is `frozenset` (immutable so a downstream consumer can't widen the allowlist at runtime — Rule 12, fail loud).
- [ ] No `OutputValidator` or `ManualPatch` validator changes in this story — those swap to the registry in S2-01.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` on `src/codegenie/llm/path_allowlists/` clean.

## Implementation outline

1. `mkdir -p src/codegenie/llm/path_allowlists`; empty `__init__.py` initially.
2. Define the Protocol + the registry dict (`Final[dict[str, PathAllowlistProvider]] = {}`) + the `register_path_allowlist` decorator.
3. Land `NpmPathAllowlistProvider` as a `@register_path_allowlist`-decorated class. Hard-code the five filenames in a `Final[frozenset[str]]` module constant; `allowed()` returns the constant.
4. Re-export at package level. Confirm fence rule from S1-07 still passes (this is pure Python, no SDK).
5. Write the test file covering default + duplicate-rejection + Phase-7-preview registration.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/llm/test_path_allowlist_registry.py`

```python
import pytest

from codegenie.llm.path_allowlists import (
    NpmPathAllowlistProvider, PathAllowlistProvider,
    get_allowlist, register_path_allowlist,
)


NPM = frozenset({
    "package.json", "package-lock.json", "yarn.lock",
    "pnpm-lock.yaml", "npm-shrinkwrap.json",
})


def test_default_npm_provider_returns_five_filenames():
    assert get_allowlist("vuln") == NPM


def test_npm_provider_protocol_satisfied():
    assert isinstance(NpmPathAllowlistProvider(), PathAllowlistProvider)


def test_allowlist_is_immutable_frozenset():
    allowed = get_allowlist("vuln")
    assert isinstance(allowed, frozenset)


def test_duplicate_registration_raises_at_import_time():
    with pytest.raises(ValueError):

        @register_path_allowlist
        class _DuplicateNpm:
            def task_class(self) -> str: return "vuln"
            def allowed(self) -> frozenset[str]: return frozenset({"other.json"})


def test_phase7_preview_dockerfile_registration_does_not_disturb_npm(monkeypatch):
    # arrange — register a hypothetical Phase-7 provider in a fresh registry
    @register_path_allowlist
    class _DockerfilePreview:
        def task_class(self) -> str: return "chainguard"
        def allowed(self) -> frozenset[str]: return frozenset({"Dockerfile", "Dockerfile.distroless"})

    # act / assert
    assert get_allowlist("chainguard") == frozenset({"Dockerfile", "Dockerfile.distroless"})
    assert get_allowlist("vuln") == NPM  # npm default unchanged


def test_unknown_task_class_raises():
    with pytest.raises(KeyError):
        get_allowlist("nonexistent_task_class")
```

### Green — make it pass

Land the Protocol, the dict-backed registry, the decorator, and the npm default exactly as outlined.

### Refactor — clean up

- Docstring on `register_path_allowlist` cites ADR-P4-003 and the Phase-7 extension pattern.
- Confirm `mypy --strict` on the decorator (return type preserved, class generic if needed).
- The duplicate-rejection test uses module-import semantics; the duplicate `_DuplicateNpm` registration must run **inside** the `pytest.raises` block. If the registry is genuinely global, dedupe by clearing the registry in a fixture per test, OR by detecting duplicate `task_class` only when both classes are *real* providers (not the test stub). Surface (Rule 12) which pattern Phase-0 uses for `@register_probe` and copy it (Rule 11).
- Consider a `_reset_registry_for_tests()` helper marked `# test-only` to keep tests hermetic without leaking into production.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/llm/path_allowlists/__init__.py` | Re-exports. |
| `src/codegenie/llm/path_allowlists/registry.py` | Protocol + decorator + dict. |
| `src/codegenie/llm/path_allowlists/npm.py` | `NpmPathAllowlistProvider`. |
| `tests/unit/llm/test_path_allowlist_registry.py` | Registry behavior + Phase-7 preview. |

## Out of scope

- **`OutputValidator.action_surface_check` integration with the registry** — S2-01 (S2-01's validator chain reads `get_allowlist(task_class)` instead of the inline literal).
- **`ManualPatch.target_files` validator swap from inline literal to registry lookup** — S2-01 (validator chain) or S5-02 (engine wiring), whichever moves first; either way, NOT this story. This story preserves the inline literal as a safety net until the validator swap lands.
- **Decorator vs YAML decision for v0.5+** — deferred per manifest Open Question #1.
- **Phase-7 `DockerfilePathAllowlistProvider`** — Phase 7 ships the real provider; this story's test stub is preview-only.

## Notes for the implementer

- The decorator must be friendly to mypy --strict; the canonical shape is:
  ```python
  P = TypeVar("P", bound=PathAllowlistProvider)
  def register_path_allowlist(cls: type[P]) -> type[P]:
      instance = cls()
      tc = instance.task_class()
      if tc in _REGISTRY:
          raise ValueError(f"duplicate PathAllowlistProvider for task_class={tc!r}")
      _REGISTRY[tc] = instance
      return cls
  ```
- The decorator instantiates the class at registration time. The Protocol's methods must therefore be parameter-free. If a future provider needs config (Phase 7 might want a config file path), the registry shape can support `register_path_allowlist(config=...)` as a parameterized decorator — but that's Phase 7's problem (Rule 2 — simplicity first).
- The hard-coded npm allowlist appears in **two** places after this story: inline in `ManualPatch.target_files` (from S1-02) AND in `NpmPathAllowlistProvider.allowed()` (here). They must agree; S2-01 collapses them by having the validator delegate to the registry. Until then, the two literals are duplicated — surface (Rule 12) in the PR description that the validator swap in S2-01 is required to remove the duplication.
- `frozenset` is the right type because consumers in `OutputValidator.action_surface_check` only need `set(target_files) ⊆ allowed`. Returning a mutable `set` would let a buggy downstream module `.add(...)` to the allowlist at runtime — a serious safety regression. Tests assert `isinstance(..., frozenset)` to lock this in.
- ADR-P4-015 names `task_class: Literal["vuln","chainguard","recipe_authoring"]` as the canonical enumeration; the registry should accept any string today and let `get_allowlist` raise `KeyError` for unregistered task classes — keeping the surface narrow. Do NOT cross-validate against the Literal here; that coupling lives in `SolvedExample`.
- Edge case from `../phase-arch-design.md §"Edge cases"`: row #6 (`Plan.target_files` outside allowlist) — exit 9 `out_of_scope_action_surface`. S2-01 reads the registry; this story only ships the data source.
- Rule 8 (read before you write): look at `src/codegenie/recipes/engine.py` and copy the `@register_recipe_engine` style if it exists. If the patterns disagree, surface (Rule 7) — don't blend.
