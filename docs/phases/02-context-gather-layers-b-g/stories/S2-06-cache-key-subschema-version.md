# Story S2-06 — Cache-key derivation includes per-probe `sub_schema_version`

**Step:** Step 2 — Plant skills loader, catalog expansion, schema-evolution policy, and conventions parity lint
**Status:** Ready
**Effort:** S
**Depends on:** S1-11 (Phase 1's cache-key derivation module — the file edited additively here; if S1-11 lands the identity hash, this story extends it)
**ADRs honored:** Phase 1 ADR-0011 (or wherever the Phase 1 cache-key identity hash is specified) — extended additively; Gap 1 / S2-07's SCHEMA-EVOLUTION-POLICY (schema bumps invalidate cache entries) — this story is the mechanism

## Context

Phase 1 derives each probe's `cache_key` from a content-addressed identity hash over the probe's declared inputs (file blobs, tool digests, probe version). The Gap-1 schema-evolution policy (S2-07) says: a `sub_schema_version` minor bump (`v1 → v1.1`) is additive, but **must still flush the affected probe's cache** because consumers expect the new fields. A major bump (`v1 → v2`) is breaking and requires a Phase-level ADR + migration handler; the cache flush is implicit in the version delta.

This story extends the cache-key derivation so per-probe `sub_schema_version` participates **additively** in `cache_key` alongside the Phase 1 identity hash. Any sub-schema version change (minor or major) → cache_key change → cache miss → re-run. The Hypothesis property test makes the contract a load-bearing invariant: `any version change ⇒ key change`.

## References — where to look

- **Architecture:** `../phase-arch-design.md §"Gap analysis & improvements" §Gap 1` — `schema_version` on every sub-schema + per-probe `sub_schema_version` in the cache key + policy doc. This story is the cache-key half.
- **Architecture:** `../phase-arch-design.md §"Data model"` — `ProbeOutput.cache_key: str` shape; the contract is unchanged at the type level.
- **Architecture:** `../phase-arch-design.md §"Testing strategy" §"Cache key invariants"` — Hypothesis property: any tool-digest change ⇒ cache-key change; this story adds the analogous property for `sub_schema_version`.
- **Phase ADRs:** none new; this story extends an existing Phase 1 mechanism by addition.
- **Production ADRs:** `../../../production/design.md §"Progressive disclosure"` — the architectural rationale for cacheability (a regenerated artifact must be byte-identical or honest about why it's not).
- **Source design:** `../final-design.md "Departures from all three inputs"` — the synth call-out on schema versioning.
- **Existing code:**
  - `src/codegenie/coordinator/cache_key.py` (from S1-11; or wherever Phase 1 lands the derivation — verify path).
  - `src/codegenie/probes/base.py` (the `Probe` ABC; check whether `sub_schema_version` is already a class attribute or needs to be added).
  - `src/codegenie/schema/probes/*.schema.json` — each sub-schema declares `schema_version`; the derivation reads it.

## Goal

Extend `src/codegenie/coordinator/cache_key.py` (or wherever the Phase 1 derivation lives) so a per-probe `sub_schema_version` string participates in the BLAKE3 input that produces `cache_key` — proving via a Hypothesis property test that any change to `sub_schema_version` (independent of all other inputs) yields a different `cache_key`.

## Acceptance criteria

- [ ] The `Probe` ABC (or a sibling protocol) exposes a `sub_schema_version: str` class attribute (default `"v1"`). Phase 2 sub-schemas live at `src/codegenie/schema/probes/<probe>.schema.json` and declare `schema_version: "v1"` at root; the class attribute mirrors the declared value.
- [ ] The cache-key derivation function (call it `derive_cache_key(...)`) takes the existing Phase 1 inputs plus the probe's `sub_schema_version`; concatenates them into the BLAKE3 input in a deterministic order; returns the hex digest.
- [ ] The derivation is **additive** to Phase 1: the existing inputs are passed unchanged, the only change is appending `sub_schema_version` to the deterministic-sorted input list (or inserting at a documented position; document the position in a module docstring).
- [ ] A Hypothesis property test in `tests/unit/coordinator/test_cache_key_includes_sub_schema_version.py` generates two probe-input dicts that differ **only** in `sub_schema_version` and asserts the two cache keys differ. The test runs at minimum 100 examples by default and includes a `@settings(deadline=None)` if needed.
- [ ] A second property test asserts the converse weakly: two probe-input dicts with the **same** `sub_schema_version` but otherwise different inputs produce different cache keys (sanity — confirms `sub_schema_version` isn't the *only* input).
- [ ] A regression test asserts a known fixture's cache key matches a frozen golden value (e.g., `tests/golden/cache_keys/probe_x_v1.txt`). If the derivation algorithm changes incidentally, the golden flags it.
- [ ] TDD red landed first: `tests/unit/coordinator/test_cache_key_includes_sub_schema_version.py` initially fails (either because `sub_schema_version` isn't in the derivation or because the ABC doesn't expose it).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/coordinator/cache_key.py` clean.

## Implementation outline

1. Confirm S1-11's location for `cache_key.py`. If absent, treat this story as additive to wherever Phase 1's identity-hash derivation lives. (Likely `src/codegenie/coordinator/cache_key.py` per the manifest reference; verify before editing.)
2. Add `sub_schema_version: ClassVar[str] = "v1"` to the `Probe` ABC in `src/codegenie/probes/base.py`. Document that subclasses override only when their sub-schema bumps.
3. In `derive_cache_key(...)`, accept `sub_schema_version: str` as an additional kwarg. Build the BLAKE3 input as the existing deterministic-sorted list **plus** a final entry `f"sub_schema_version={sub_schema_version}"`. The order is fixed: existing inputs first, `sub_schema_version` last (Append-only; future fields go after).
4. Wire the coordinator's call to `derive_cache_key`: where the coordinator currently passes Phase-1 inputs, also pass `probe.sub_schema_version`.
5. Document the derivation contract in a module docstring at the top of `cache_key.py`: "Inputs are concatenated in this order; new inputs are appended only (never inserted); a minor bump to any sub-schema flushes that probe's cache."

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/coordinator/test_cache_key_includes_sub_schema_version.py`

```python
from hypothesis import given, strategies as st, settings

@given(
    base_inputs=...,                       # Hypothesis strategy: the existing derivation inputs
    version_a=st.text(min_size=2, max_size=10),
    version_b=st.text(min_size=2, max_size=10),
)
@settings(max_examples=200)
def test_any_sub_schema_version_change_changes_cache_key(base_inputs, version_a, version_b):
    if version_a == version_b:
        return  # skip equal cases
    key_a = derive_cache_key(**base_inputs, sub_schema_version=version_a)
    key_b = derive_cache_key(**base_inputs, sub_schema_version=version_b)
    assert key_a != key_b

@given(...)
def test_same_sub_schema_version_alone_does_not_force_equality(...):
    # Two different base_inputs with the same sub_schema_version still produce different keys.
    ...

def test_golden_cache_key_for_known_fixture() -> None:
    # Frozen golden — regression guard on the derivation algorithm.
    inputs = _fixed_fixture_inputs()
    key = derive_cache_key(**inputs, sub_schema_version="v1")
    assert key == (Path("tests/golden/cache_keys/probe_x_v1.txt").read_text().strip())
```

Run; confirm red (derivation doesn't yet take `sub_schema_version`); commit; then Green.

### Green — make it pass

Smallest impl: add the parameter; append to the BLAKE3 input list; thread through the coordinator. Generate the golden via `python -c "from codegenie.coordinator.cache_key import derive_cache_key; print(derive_cache_key(...))"` once, paste into the golden file, lock.

### Refactor — clean up

- Update the existing `test_cache_key_includes_tool_digests.py` (from Phase 1) to assert that both invariants compose: simultaneous changes to tool digests AND `sub_schema_version` yield a different key from changing just one. (Defensive — confirms the additive composition.)
- Add a docstring example showing the order of concatenation.
- `mypy --strict` clean.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/coordinator/cache_key.py` | Add `sub_schema_version` to the derivation; document order. |
| `src/codegenie/probes/base.py` | Add `sub_schema_version: ClassVar[str] = "v1"` to the `Probe` ABC. |
| `src/codegenie/coordinator/<dispatch>.py` (where `derive_cache_key` is called) | Pass `probe.sub_schema_version` through. |
| `tests/unit/coordinator/test_cache_key_includes_sub_schema_version.py` | Hypothesis property + golden regression. |
| `tests/golden/cache_keys/probe_x_v1.txt` | Frozen cache-key value for a known fixture. |

## Out of scope

- **Per-probe sub-schema files declaring `schema_version`** — each probe story (S3-01, S4-*, S5-*, …) lands its own sub-schema. This story owns only the cache-key plumbing.
- **Migration handler for `v1 → v2` breaks** — S2-07's policy doc names the requirement; the *implementation* of a migration handler is deferred until a real `v2` arrives (Phase 3+).
- **CLI-facing flush command** — the cache flushes automatically on a version bump. Manual flush remains `codegenie gather --no-cache` (Phase 0 flag).
- **Open Question #9 alternatives** — the default per `phase-arch-design.md "Open questions"` is "flush on any minor bump"; this story implements that default. Alternative policies (e.g., "keep cache, mark stale") are deferred.

## Notes for the implementer

- **Append-only contract on the BLAKE3 input list.** Document this loudly: any new contributor adding an input must *append* to the end of the deterministic-sorted list, never insert in the middle. Inserting changes the digest of every existing cache entry — a silent universal flush.
- **`sub_schema_version` is a string, not a tuple.** Don't be tempted to parse it into `(major, minor)` for comparison; the derivation must treat it as opaque bytes. "v1" and "v1.0" differ — they hash differently — and that's correct: the schema-evolution policy treats them as distinct versions.
- **The Hypothesis test must skip equal cases**, otherwise the `version_a != version_b` precondition fires too often and Hypothesis reports `Unsatisfied`. Use `assume(version_a != version_b)` from `hypothesis` to filter cleanly.
- **Golden file regeneration is a deliberate act.** If the test fails because the derivation changed, the fix is to *understand why* the change happened — not regenerate the golden by reflex. A regenerate-on-failure pattern defeats Rule 9.
- **`probe.sub_schema_version` is a class attribute, not an instance attribute.** Don't override it per-instance; subclasses with `class Foo(Probe): sub_schema_version = "v1.1"` is the only valid override pattern.
- **The Phase 1 identity hash already covers `probe_version`.** Don't conflate `probe_version` (the *code* version) with `sub_schema_version` (the *output shape* version). They're orthogonal — code can change without changing output shape; output shape can be extended without changing code (e.g., adding a sub-schema field that was already populated by the probe under `extra="allow"`, then tightening).
- **`Path.expanduser()` is still forbidden in this file** — the no-home-expansion contract from S2-01 applies broadly; cache-key derivation must be host-machine-independent.
