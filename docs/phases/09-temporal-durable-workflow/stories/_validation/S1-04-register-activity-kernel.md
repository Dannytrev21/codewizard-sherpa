# Validation report — S1-04 `@register_activity` registry kernel

**Date:** 2026-07-25
**Story:** [`../S1-04-register-activity-kernel.md`](../S1-04-register-activity-kernel.md)
**Skill:** `phase-story-validator`
**Verdict:** **HARDENED**

## Context brief (Stage 1)

- **Goal.** Ship the module-level `@register_activity(*, name, timeout, task_queue)` decorator + `_ACTIVITIES: dict[ActivityName, ActivityRegistration]` registry under `src/codegenie/durable/activities/__init__.py`. Collision at import time = `TypeError`. Precedent: Phase-0 `@register_probe`.
- **Load-bearing contracts read.**
  - `../phase-arch-design.md §C2 — Activity catalog` (lines 465–486) — `register_activity` signature + activity idempotency & retry semantics (S4-01 territory).
  - `../phase-arch-design.md §Development view — module tree` (lines 262–292) — `activities/__init__.py (@register_activity)` collection point.
  - `../phase-arch-design.md §Stable contracts vs internal` (line 294) — `@register_activity` is a **frozen Open/Closed extension point**.
  - `../phase-arch-design.md §Design patterns applied #6 — Registry pattern` (line 951) — "Same shape as `@register_probe` from Phase 0."
  - `../phase-arch-design.md §Anti-patterns avoided` (line 970) — "Side effects in module import (registries are dicts populated lazily on first decorator invocation; `__init__.py` only imports modules)."
  - `../phase-arch-design.md §Integration with Phase 10` (line 1072) — `@register_activity(task_queue=...)` is the additive seam.
  - `../ADRs/0007-two-task-queue-partitioning-and-expansion-by-addition.md` §Decision + §Consequences — `task_queue: TaskQueueName` is a first-class registration field; new queues expand by addition; `{task-class}-{language}-{package-manager}` naming enforced elsewhere.
  - `../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md` §1 — adding a decorator + one import line is a loud, compiler-policed addition; sanctioned.
  - `src/codegenie/probes/registry.py` — Phase-0 canonical precedent (dual-shape decorator with a bare form because the bare form has viable defaults). Docstring line 4 openly cites `importlib.metadata` in prose (relevant to fence design; see below).
  - `src/codegenie/probes/__init__.py` — explicit-imports collection precedent.
- **Contradictions surfaced.**
  1. **Arch §C2 sample code (line 471) shows the 2-arg form** `register_activity(*, name: ActivityName, timeout: timedelta)`; the story ships the 3-arg form including `task_queue: TaskQueueName`. **The story is right**: ADR-0007 §Consequences and arch line 1072 both cite the 3-arg form, and §C2's excerpt is a stale one-line example. The synthesizer surfaces this as an explicit reconciliation Note in the story.
  2. **The Refactor step's `functools.wraps` advice contradicts AC-3's identity assertion.** AC-3 requires `decorated is fn` (object identity), but `functools.wraps` implies wrapping *another* callable and preserving metadata via copy — the two are mutually exclusive. The correct implementation is: the decorator records `fn` in `_ACTIVITIES` and returns `fn` unchanged; no wrapping happens, so `functools.wraps` is neither needed nor coherent. This is the single BLOCK-level finding; the story is edited to remove the misleading advice.

## Stage 2 — Critic findings

Given the story's tight scope and my already-loaded context (all four reference docs + the Phase-0 registry + the arch's pattern section), the four-critic pass was consolidated inline (token-budget discipline per global Rule 6). Findings are grouped by lens; severity is `block` / `harden` / `nit`.

### Coverage critic

| Sev | Finding |
|---|---|
| harden | **`functools.wraps` metadata preservation is not covered by any AC.** Arch §C2 lists `fn.__name__` as load-bearing for Temporal's `@activity.defn` in Step 4. But the identity contract (`decorated is fn`) *already* preserves `__name__` — the decorator is expected to be a pure recorder, not a wrapper. Add an AC asserting `decorated.__name__ == fn.__name__` so the identity guarantee is *observably* verified. |
| harden | **`clean_activity_registry` pytest fixture is mentioned only in the Refactor prose.** Every Step-4 test file will pollute `_ACTIVITIES`; the fixture is the discipline that keeps Step-4 tests hermetic. Promote it to an AC with a concrete file path so the executor lands it in this story, not later. |
| harden | **AC-4/AC-5 asymmetry.** AC-4 (collision raises) has a TDD test; AC-5 ("same function under two different names is permitted") has no test. Add a TDD test case for it. |
| harden | **Timeout / task-queue threading is minimally tested.** The happy-path TDD test uses `timedelta(seconds=5)` and `"system"` for both fields; a wrong implementation that hard-codes those defaults would pass. Add a test that registers **two** activities with **different** timeouts and different task queues; assert each row carries its correct value. Classic mutation-testing hardening. |
| harden | **`ActivityRegistration` frozen-ness is not tested.** Story says `@dataclass(frozen=True, slots=True)` but no test would fail if `frozen=True` were dropped. Add: `test_activity_registration_is_frozen` asserting `dataclasses.FrozenInstanceError` on mutation. |
| nit | Registration of a **sync** callable is silent (arch's contract types `fn: Callable[..., Awaitable[Any]]`). `mypy --strict` will catch it at Step-4 activity-definition sites; runtime check is not required at this kernel layer. Recorded, not blocking. |

### Test Quality critic

| Sev | Finding |
|---|---|
| harden | **The fence test uses substring-in-file matching.** `assert "importlib.metadata" not in src` false-positives on any docstring that says "*no importlib.metadata entry-point scan*" (the Phase-0 precedent's `probes/registry.py:4` docstring uses exactly this phrase). The story's own instruction "Module docstring citing ADR-0007 + ADR-0043 + naming `@register_probe` as the precedent" makes this collision likely. Rewrite the fence to **parse the module with `ast`** and check for `Import`/`ImportFrom` nodes referencing `importlib.metadata` / `pkgutil` and for `Call(func=Attribute(attr="walk_packages" \| "iter_modules"))`. Mutation-resistant *and* docstring-safe. |
| harden | **Identity test would pass with a wrapper that reuses `__wrapped__`.** Strengthen from `decorated is fn` to `decorated is fn and decorated.__name__ == "fn"` — closes the "wraps a function but preserves identity via `__wrapped__`" attack. |
| harden | **Test 1 mutates the process-wide `_ACTIVITIES` without cleanup.** Step-4 activity-registration tests would later find a stale `test_alpha` row. Use the `clean_activity_registry` fixture in every test. |
| harden | **Registry-index invariant is untested.** If two decorations of the same name happen in the same import (via re-import + module reload), the second must still raise. Add a test that re-decorates the *same* name after the first registration completed. |
| nit | Property-based testing is overkill at this size. Recorded, not adopted. |

### Consistency critic

| Sev | Finding |
|---|---|
| block | **AC-3 identity contradicts Refactor `functools.wraps` advice.** See "Contradictions surfaced" #2 above. Fix: remove `functools.wraps` from Refactor; the decorator is a pure recorder that returns `fn` unchanged; identity preserves `__name__` naturally. |
| harden | **Arch §C2 signature mismatch.** See "Contradictions surfaced" #1. Add a Note reconciling the two arch excerpts and citing ADR-0007 as the authoritative source for the 3-arg form. |
| harden | **`_ACTIVITIES` naming inconsistent with Phase-0 precedent.** Phase-0 exposes `default_registry` (public, no underscore); the story exports `_ACTIVITIES` in `__all__` (underscore-prefix + public export is a smell). Two Rule-11-compliant fixes: (a) rename to `ACTIVITIES` and keep it in `__all__`, or (b) keep `_ACTIVITIES` private and expose an accessor `def all_activities() -> Mapping[ActivityName, ActivityRegistration]` returning `MappingProxyType(_ACTIVITIES)`. Consistency picks **(b)** — the accessor also enforces immutability at the seam, aligning with the "make illegal states unrepresentable" commitment (CLAUDE.md). |
| harden | **`task_queue` default omission is a load-bearing invariant.** Story's Notes says "do not default it (force the caller to be explicit about which pool consumes the activity)". Promote this to an AC — the kernel must not accept a call site that omits `task_queue`. The `*,` keyword-only marker + no default is the mechanism; add a TDD test that a call without `task_queue` raises `TypeError` at the decorator-call site. |
| nit | Docstring citation of ADR-0007 + ADR-0043 + Phase-0 precedent is required by CLAUDE.md convention. Already in the implementation outline. |

### Design Patterns critic

| Sev | Finding |
|---|---|
| harden | **`MappingProxyType` for the public read view.** Downstream (S6-01 worker bootstrap) reads `_ACTIVITIES` to assemble worker pools; if it can mutate, invariants break. Return `MappingProxyType(_ACTIVITIES)` from a public accessor. Kernel stays a plain `dict` internally (Rule 2 — no `Registry` class ceremony); the accessor is one line. |
| harden | **Registry-pattern uniformity with Phase-0.** Phase-0's `@register_probe` supports a dual-shape (bare + kwargs) because `Probe.name` is defined on the class and there are viable defaults. `@register_activity` has *no* viable defaults (name is required at the call site); a single kwargs-only shape is correct and simpler. Document this as an intentional divergence (avoids future confusion / avoids someone "fixing" it to dual-shape). |
| harden | **`Any` in `fn: Callable[..., Awaitable[Any]]`.** Necessary here (heterogeneous registry across nine activities with different arg/return types). Mark the `Any` with a one-line comment citing the arch's C2 heterogeneous-typed-IO justification so a future reviewer doesn't try to introduce a TypeVar. |
| harden | **Open/Closed via decorator preserved.** Adding a tenth activity in a later phase = one new file + one `@register_activity(...)` + one import line in `__init__.py`. No edits to the kernel required. Add an AC that codifies this — "adding a new activity module MUST NOT require editing `activities/__init__.py`'s decorator definition or the `ActivityRegistration` dataclass"; verifiable by inspection at Step-4-story review time. |
| nit | Frozen dataclass with `slots=True` is the right choice (`Pydantic` for domain-facing data, `dataclass(frozen=True, slots=True)` for internal registry rows — Phase-0 precedent at `ProbeRegEntry`). Already in the story. |
| nit | No `Registry` class extraction (Phase-0 has one; this story deliberately keeps a bare dict). Story already notes this. Rule-of-three not met; correct call. |

## Stage 3 — Research

Not fired. No `NEEDS RESEARCH` findings — every finding above resolves against the Phase-0 precedent, arch/ADR text, or the frozen-dataclass idiom.

## Stage 4 — Edits applied

Edit priority: `Consistency > Coverage > Test-Quality > Design-Patterns`.

1. **BLOCK (Consistency):** Removed the `functools.wraps` recommendation from the Refactor section; replaced it with a Note that the decorator is a pure recorder returning `fn` unchanged, and `__name__` is preserved by identity (not by `functools.wraps`).
2. **HARDEN (Consistency, arch reconciliation):** Added a top-of-story reconciliation Note that arch §C2 line 471's 2-arg signature is a stale excerpt; ADR-0007 + arch line 1072 authorise the 3-arg form.
3. **HARDEN (Consistency + Design-Patterns):** Kept `_ACTIVITIES` as the module-private mutable state, added a public `ACTIVITIES: Mapping[ActivityName, ActivityRegistration]` bound to `MappingProxyType(_ACTIVITIES)` (immutable view) as the exported name; updated `__all__` accordingly. This mirrors Phase-0's `default_registry` public accessor pattern.
4. **HARDEN (Coverage):** Promoted `clean_activity_registry` fixture from a Refactor prose bullet to AC + Files-to-touch row; the fixture snapshots and restores `_ACTIVITIES` around each test.
5. **HARDEN (Coverage):** Added ACs for `ActivityRegistration.frozen` (mutation raises `FrozenInstanceError`), for `__name__` preservation (`decorated.__name__ == fn.__name__`), for `task_queue` being non-defaultable at the call site, and for the "second call under the same name still raises `TypeError`" case.
6. **HARDEN (Coverage + Test-Quality):** Added TDD-plan tests: (a) two activities with *different* timeouts + task queues carrying correct row values; (b) same-function-two-names is permitted (AC-5 gains a test); (c) `ActivityRegistration` is frozen; (d) `__name__` preserved by identity; (e) missing-`task_queue` call site is a `TypeError`.
7. **HARDEN (Test-Quality):** Rewrote the explicit-import fence test to use `ast.parse` and walk for `Import`/`ImportFrom` of `importlib.metadata` and `pkgutil`, plus `Call(func=Attribute(attr=…))` for `walk_packages` / `iter_modules`. Removes docstring false-positives while remaining more mutation-resistant than substring matching.
8. **HARDEN (Design-Patterns):** Added a Note codifying "kernel stays a bare dict — do not introduce a `Registry` class unless a later story surfaces test-isolation or pluggable-scheduling needs" (upholding the story's original stance against ceremony, now cross-linked to the Phase-0 precedent and to Rule 2).
9. **HARDEN (Design-Patterns):** Added a Note that `@register_activity` is a **single-shape** decorator (kwargs-only) — a deliberate divergence from Phase-0's dual-shape `@register_probe`, because `name` is not defaultable. Prevents a future reviewer from "fixing" it to dual-shape.
10. **HARDEN (Design-Patterns):** Added an AC for the Open/Closed extension guarantee: adding a new activity must not require editing `activities/__init__.py`'s decorator definition or the `ActivityRegistration` dataclass. Observable at Step-4 review time (grep-friendly: any new activity module lands with a new file, one decorator, one import).
11. **Status.** `Ready` → `HARDENED`. Validation-notes block appended under the story header.

### Before / after — the block-level fix

Before (Refactor bullet 1):
> Use `functools.wraps` so the decorator preserves `__name__`, `__doc__`, etc. — necessary for Temporal's `@activity.defn` to see the original function name when stacked on top in Step 4.

After (Refactor bullet 1 rewritten):
> **Do not use `functools.wraps`** — the decorator returns `fn` unchanged (identity), so `__name__` and `__doc__` are preserved *by construction*. Wrapping via `functools.wraps` would break AC-3's identity assertion (`decorated is fn`). Temporal's `@activity.defn` in Step 4 stacks on top of `@register_activity`; because we return the same callable, `activity.defn` sees the original `fn.__name__` naturally.

## Verdict

**HARDENED.** One block-level self-contradiction fixed; nine harden-level strengthenings (accessor pattern, frozen invariance, fixture uplift, mutation-resistant TDD tests, AST-based fence, Open/Closed AC, arch reconciliation Note). Story is now executable by `phase-story-executor` with confidence that a wrong implementation would fail at least one test in the TDD plan.
