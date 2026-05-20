# Story S7-03 — Add `test_language_probes_actually_dispatched` (Gap 3)

**Step:** Step 7 — Land the `tests/conformance/` tier and the `LanguagePack` contract-snapshot fence
**Status:** Ready
**Effort:** M
**Depends on:** S7-02
**ADRs honored:** ADR-0010, ADR-0004, ADR-0006

## Context
S7-02's per-language assertions verify each capability *in isolation* — they call the detector, run `probe.run()` directly, exercise the strategy. None of them catch the architect's most dangerous gap (Gap 3): a probe registered but **never dispatched** because the coordinator's `language_filter` filters it out of every wave. A Python `tier="task_specific"` probe with a typo'd `applies_to_languages` (`["py"]` instead of `["python"]`) passes every isolated conformance assertion and still never runs in a real gather. This story closes that hole at the *integration* level — the headline exit criterion "Python and TypeScript both run from the same gather + plugin orchestration" — by reading the coordinator's `coordinator.dispatch.order` audit event, and gives the test teeth with a negative typo case.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Gap analysis & improvements — Gap 3` — the registered-but-never-dispatched hole; the prescribed fix: `test_language_probes_actually_dispatched` reading `coordinator.dispatch.order`, plus the typo'd-`applies_to_languages` negative test that proves teeth.
- **Architecture:** `../phase-arch-design.md §Harness engineering` — the coordinator emits the `coordinator.dispatch.order` audit event; Python probes appear in it as new rows.
- **Architecture:** `../phase-arch-design.md §Control flow — decision points` — `language_filter._admits_languages`: `"*"` always admits; otherwise admission requires overlap with the enriched `detected_languages`.
- **Architecture:** `../phase-arch-design.md §Component design — tests/conformance/ tier` — `test_language_probes_actually_dispatched` is listed among the per-language assertions; it reuses the session-scoped gather, costing nothing extra.
- **Phase ADRs:** `../ADRs/0010-conformance-tier-parameterized-over-live-registry.md` — ADR-0010 — `test_language_probes_actually_dispatched` reads the session gather's `coordinator.dispatch.order` event and closes Gap 3 at the integration level.
- **Phase ADRs:** `../ADRs/0004-python-detection-as-base-tier-probe-not-prepass.md` — ADR-0004 — `PythonProjectProbe` is `tier="base"` (prelude wave); the others are `tier="task_specific"` filtered by `language_filter`.
- **Existing code:** `src/codegenie/coordinator/coordinator.py` — emits the `coordinator.dispatch.order` audit event; confirm its exact shape and where it lands (`.codegenie/context/runs/*.json` audit anchors).
- **Existing code:** `tests/conformance/test_language_conformance.py` (S7-02) — the module this assertion is added to; reuse its session-scoped per-language gather fixture.

## Goal
Add a conformance assertion that every `pack.layer_a_probes` probe appears in the run's `coordinator.dispatch.order` audit event, plus a negative test where a typo'd `applies_to_languages` makes the assertion fail.

## Acceptance criteria
- [ ] The TDD red test exists, is committed, and was observed failing before the dispatch-order assertion existed.
- [ ] `test_language_probes_actually_dispatched` is parameterized per language; for the session-scoped gather of each language fixture it asserts every probe in `pack.layer_a_probes` appears in that run's `coordinator.dispatch.order` audit event.
- [ ] The assertion reads the *real* emitted audit event (from the gather's `.codegenie/context/runs/*.json` or the captured `structlog` event) — it does not re-derive dispatch order from the registry.
- [ ] A negative test: a Python probe declared with `applies_to_languages=["py"]` (the typo) is filtered out of dispatch → `test_language_probes_actually_dispatched` **fails** for it — proving the assertion has teeth (Rule 9, Gap 3).
- [ ] The negative test isolates the typo'd probe (a local pack/registry instance or a `monkeypatch`'d probe) so it does not pollute `default_probe_registry` or other conformance cases.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` pass on the touched test files; `make fence` and `import-linter` stay green.

## Implementation outline
1. In `test_language_conformance.py`, add `test_language_probes_actually_dispatched(pack, gathered)` parameterized like the other conformance assertions.
2. From the session-scoped gather result, locate the `coordinator.dispatch.order` audit event (parse the run JSON under `.codegenie/context/runs/`, or capture `structlog` events during the gather).
3. Assert `{p.name for p in pack.layer_a_probes} ⊆ <probe names in the dispatch-order event>`.
4. In a separate test module (`tests/unit/coordinator/test_dispatch_order_teeth.py` or under `tests/conformance/`), define a minimal Python-like probe class with `applies_to_languages=["py"]`, register it into an isolated registry/pack, run a gather on a Python fixture, and assert the dispatch-order check fails for it.
5. Confirm the negative probe never reaches the global `default_probe_registry`.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/conformance/test_language_conformance.py` (positive) + `tests/conformance/test_dispatch_order_teeth.py` (negative).
- Positive — `test_language_probes_actually_dispatched`:
```python
def test_language_probes_actually_dispatched(pack, gathered_context) -> None:
    # arrange: read the coordinator.dispatch.order audit event from the session gather
    dispatched = _probe_names_in_dispatch_order(gathered_context.run_audit)
    # act + assert: every layer_a probe of this pack was actually dispatched
    expected = {p.name for p in pack.layer_a_probes}
    assert expected <= dispatched, f"{expected - dispatched} registered but never dispatched"
    # intent: a probe with a typo'd applies_to_languages is in the registry but NOT here
```
- Negative — `test_typoed_applies_to_languages_is_caught`:
```python
def test_typoed_applies_to_languages_is_caught(tmp_python_repo) -> None:
    # arrange: a probe class with applies_to_languages=["py"] (typo), in an isolated pack
    # act: gather the python fixture; read coordinator.dispatch.order
    # assert: the typo'd probe is absent from dispatch order -> the Gap-3 check fails for it
    ...
```
Both fail until the dispatch-order assertion + audit-event reader exist.

### Green — make it pass
Add the dispatch-order reader helper and the positive assertion; both pass once Python probes carry the correct `applies_to_languages=["python"]`. Build the negative test's isolated typo'd probe and assert the check rejects it.

### Refactor — clean up
Extract `_probe_names_in_dispatch_order` as a pure parser over the audit event. Add a docstring on the negative test explaining it is the teeth-proof for Gap 3 (Rule 9) — without it the positive assertion could be vacuously satisfied. Confirm the audit-event shape is read from a stable field, not a brittle log-string match.

## Files to touch
| Path | Why |
|---|---|
| `tests/conformance/test_language_conformance.py` | Add `test_language_probes_actually_dispatched` + the audit-event reader helper. |
| `tests/conformance/test_dispatch_order_teeth.py` | New — the typo'd-`applies_to_languages` negative test. |

## Out of scope
- The golden fixture portfolio / adversarial / polyglot fixtures — S7-04.
- The `LanguagePack` contract-snapshot fence — S7-05.
- Any change to coordinator dispatch logic or the `language_filter` predicate — both are reused unchanged.
- The e2e slice row — S8-01.

## Notes for the implementer
- This assertion must **not** be collapsed into the weaker isolated `test_layer_a_probes_produce_nonempty_slices` — that one calls `probe.run()` directly and bypasses the coordinator's prelude/rest-wave partition and `language_filter` entirely. The architect explicitly flagged this collapse risk.
- The negative test is what gives the positive one teeth (Rule 9): without a probe that *should* fail, the positive assertion could be vacuously true. The typo (`["py"]`) is the canonical Gap-3 bug.
- Isolate the typo'd probe — registering it into the global `default_probe_registry` would leak into every other conformance case and there is no `unregister`. Use a fresh registry instance or `monkeypatch`.
- `PythonProjectProbe` is `tier="base"` — it runs in the prelude wave regardless of `language_filter`; the `tier="task_specific"` probes are the ones the filter gates. The dispatch-order event should show *all* of them; the typo bug only hides a `task_specific` probe.
- Read the audit event from a stable structured field (`coordinator.dispatch.order`), not by string-matching a log line — the latter is brittle and would silently pass if the event were renamed.
