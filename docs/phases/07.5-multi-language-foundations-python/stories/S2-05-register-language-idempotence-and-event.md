# Story S2-05 — Make `register_language` idempotent and emit `language.registered`

**Step:** Step 2 — Land the `register_language` / `validate_pack` kernel and `LanguageRegistry`
**Status:** Ready
**Effort:** S
**Depends on:** S2-03
**ADRs honored:** ADR-0002

## Context
`register_language` runs at import time and may be reached more than once across a process (a re-import, a test that re-touches the collection point). ADR-0002 requires it be **idempotent per `Language`** — re-registering the *same* pack is a no-op — while a re-registration of a *different* pack for the same `Language` must raise, naming both sites. This story also adds the `structlog` `language.registered` event so a startup log shows exactly what each pack contributed.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — register_language() + validate_pack()` — "Idempotent within a process: re-registering the same `Language` is a no-op."
- **Architecture:** `../phase-arch-design.md §Harness engineering — Logging` — `register_language` emits `language.registered{language, probes_fanned_out, strategies_fanned_out}` so a startup log shows each pack's contribution.
- **Architecture:** `../phase-arch-design.md §Harness engineering — Idempotence` — `register_language` is idempotent per `Language`; tests can re-import freely.
- **Phase ADRs:** `../ADRs/0002-register-language-validate-all-then-commit-no-unregister.md` — ADR-0002 — Consequences bullet: "`register_language` is idempotent per `Language` — re-registering the same pack is a no-op; tests can re-import freely."
- **Existing code:** `src/codegenie/languages/registry.py` — `register_language` (S2-03) and `LanguageRegistry` (S2-01); `LanguageRegistry.register` currently raises on a duplicate `Language` — this story makes `register_language` mediate that.
- **Existing code:** `src/codegenie/depgraph/registry.py` — `depgraph.strategy.registered` is the precedent for the `structlog` event shape and field naming.

## Goal
Make `register_language` a no-op when the *same* pack re-registers for an already-registered `Language`, raise `LanguageRegistryError` naming both sites on a *conflicting* re-registration, and emit a structured `language.registered` event on a real registration.

## Acceptance criteria
- [ ] The TDD red test in `tests/unit/languages/test_register_language_idempotence.py` exists, is committed, and was observed failing before implementation.
- [ ] Re-registering the **same** `LanguagePack` value for an already-registered `Language` is a no-op — no exception, no second fan-out, no duplicate `register_probe` call.
- [ ] Re-registering a **different** pack for the same `Language` raises `LanguageRegistryError` whose message names both the prior and the new registration site.
- [ ] A successful (first) registration emits a `structlog` `language.registered` event carrying at minimum `language`, `probes_fanned_out`, and `strategies_fanned_out`; an idempotent no-op does **not** re-emit a misleading event (or emits a clearly-distinguished no-op event).
- [ ] Idempotence is keyed on `Language` *and* pack identity/equality — a unit test confirms the "same pack" path and the "conflicting pack" path are distinguished.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest tests/unit/languages/test_register_language_idempotence.py` pass on touched files.
- [ ] Story `**Status:**` set to `Done`.

## Implementation outline
1. In `register_language`, before calling `validate_pack` / `LanguageRegistry.register`, check whether `pack.language` is already in `default_language_registry`.
2. If present and the existing pack **equals** the incoming pack (`LanguagePack` is a frozen Pydantic value — equality is structural), return early — a no-op. Skip `validate_pack`, the publish, and the fan-out.
3. If present and the existing pack **differs**, raise `LanguageRegistryError` naming both registration sites (the prior origin from `LanguageRegistry._origins`, the current call site).
4. If absent, proceed with the S2-03 sequence (validate → build-then-publish → fan-out).
5. After a successful real registration, emit `structlog`'s `language.registered` event with `language`, `probes_fanned_out` (count, `0` for a self-registered pack), `strategies_fanned_out` (count).
6. Confirm a test that imports the collection point twice does not crash and does not double-fan-out.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/languages/test_register_language_idempotence.py`.

```python
# test_same_pack_reregistration_is_noop
#   arrange: register_language(pack) once into a fresh registry context
#   act:     register_language(pack) again (same value)
#   assert:  no exception; no second probe fan-out (spy on register_probe);
#            registry still has exactly one entry for pack.language

# test_conflicting_pack_for_same_language_raises
#   arrange: register pack_a for Language("python")
#   act/assert: register_language(pack_b)  # different pack, same Language
#               raises LanguageRegistryError naming both sites

# test_successful_registration_emits_language_registered_event
#   arrange: capture structlog events
#   act:     register_language(a probes_self_registered=False pack)
#   assert:  a "language.registered" event with language / probes_fanned_out
#            / strategies_fanned_out is emitted
```

Must fail (`AssertionError` — a duplicate raises instead of no-op, or no event) before implementation.

### Green — make it pass
Add the pre-check at the top of `register_language` distinguishing same-pack (no-op) from conflicting-pack (raise) from absent (proceed). Add the `structlog` event after a successful fan-out.

### Refactor — clean up
Docstring citing ADR-0002's idempotence consequence; precise types; ensure the event field set matches the arch §Harness-engineering spec; confirm the no-op path skips `validate_pack` cleanly; `mypy --strict` clean.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/languages/registry.py` | Add the idempotence pre-check + the `language.registered` event to `register_language`. |
| `tests/unit/languages/test_register_language_idempotence.py` | New — idempotence + event unit tests. |

## Out of scope
- The no-shadow check — S2-04.
- The Hypothesis property test — S2-06.
- `coordinator.dispatch.order` / probe-dispatch audit events — Phase-existing plumbing, consumed by S7-03.

## Notes for the implementer
- Idempotence is keyed on `Language` *and* structural equality of the `LanguagePack`. `LanguagePack` is a frozen Pydantic model, so `==` is structural — the "same pack" check is `existing == incoming`. Do not key idempotence on object identity alone (a re-import constructs a fresh-but-equal value).
- The same-pack no-op path must skip the fan-out entirely — a second `register_probe` call on the same probe raises `ProbeError`. The no-op is what makes re-imports safe.
- A conflicting re-registration (different pack, same `Language`) is a real error — raise, do not silently overwrite. Name both sites so the developer can find the duplicate-definition bug.
- Do not emit a misleading `language.registered` event on the no-op path — either suppress it or emit a clearly distinct `language.registered.noop` so a startup-log reader is not misled about a second fan-out happening.
- The event field set (`language`, `probes_fanned_out`, `strategies_fanned_out`) is named in arch §Harness engineering — match it exactly; for a `probes_self_registered=True` pack `probes_fanned_out` is `0`.
- Keep this change surgical — it adds a pre-check and an event; it does not restructure the S2-03 validate → publish → fan-out body.
