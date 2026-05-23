# Story S3-06 — `RedactedActivityResult.seal` — three-layer sanitizer

**Step:** Step 3 — Canonical event log, BlobRef store, and activity-boundary sanitizer
**Status:** Ready
**Effort:** M
**Depends on:** S3-05 (`BlobRef` — sanitizer can return `BlobRef`-shaped payloads); transitively S1-01 (`SECRET_TYPES` registry), S1-02 (`RedactionFired` event variant)
**ADRs honored:** ADR-0008 (typed-credential-class blocklist, NOT regex — **load-bearing**), production ADR-0008 (secret-redaction), ADR-0006 (`RedactionFired` is an event — fires through batched path; only critical variants are sync), production ADR-0043 (ADRs)

## Context

Temporal records every activity input and return value in workflow history. A naive activity that returns `GitHubToken` as a field writes that token into history forever — anyone with cluster read access can see it. The security-first design [S] originally proposed a regex over field names (`_(KEY|TOKEN|SECRET)_`) — but the critic showed the regex misses every well-named field (`evidence_digest`, `attempt_id`, `failing_signals` carry potentially sensitive bytes under non-suspicious names).

**ADR-0008's answer: three layers in order.** `RedactedActivityResult.seal(model: T) -> RedactedActivityResult` is the smart constructor every activity's return value must go through. The layers (a) Pydantic `extra="forbid"`, (b) **typed-credential-class blocklist** (the load-bearing layer — the field's *declared type* is checked against `SECRET_TYPES`; this catches the well-named-but-typed-as-secret field that name-regex misses), (c) value-shape regex backstop for AWS / GitHub PAT / JWT shapes — any match emits a `RedactionFired` event so we learn every contributor's near-miss before any token actually ships into history.

This story ships the kernel `RedactedActivityResult` + `seal` classmethod + the three-layer logic. The fence test that asserts every activity's return type IS `RedactedActivityResult`-derived ships in S4-06 (tests/fence/test_activity_payload_typing.py). The adversarial test that asserts a `GitHubToken`-typed field is rejected ships in S4-07. **This story** is the kernel + the three integration tests (one per layer) + a Hypothesis property test that `seal` is idempotent (`seal(seal(x)) == seal(x)`).

The Capability types live in `src/codegenie/durable/capabilities.py` (S1-06 declared shape; S3-01 / S3-02 / S3-05 land concrete records as needed). This story does NOT re-ship them; it consumes `EventLogWriteCapability` to emit `RedactionFired`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C7 — Activity-boundary sanitizer` (the public interface; three-layer logic; performance envelope; failure behavior).
  - `../phase-arch-design.md §Scenario 4 — Adversarial: secret in activity return → typed-credential blocklist rejects at seal time` (the canonical illustration; the critic's attack on regex-over-field-names; the layer-(b) load-bearing check).
  - `../phase-arch-design.md §Design patterns applied #9` (smart constructor + type-driven security; the capability-pattern as Pydantic record).
  - `../phase-arch-design.md §Non-goals — HMAC-signed capability tokens` (the trust root is process-level, not cryptographic; this story does NOT implement HMAC).
- **Phase ADRs:**
  - `../ADRs/0008-typed-credential-blocklist-not-regex.md` — **load-bearing.** The three-layer order; `SECRET_TYPES` is the source of truth for layer (b); `RedactionFired` events for layer (c) near-misses; the regex catalog is for *AWS / GitHub PAT / JWT*.
  - `../ADRs/0006-critical-event-synchronous-flush-vocabulary.md` — `RedactionFired` is NOT critical (rides batched flush); `WorkflowTerminated` IS critical (sync) — sanitizer escalation via `WorkflowTerminated` is out of scope here.
- **Production ADRs:**
  - `../../../production/adrs/0008-secret-redaction.md` — the production-level commitment this story implements.
- **Existing code:**
  - `src/codegenie/types/credentials.py` (S1-01 should ship this; if not, this story does) — `SECRET_TYPES: Final[frozenset[type]] = frozenset({GitHubToken, LlmApiKey, MicroVmCredential, PostgresPassword, SshPrivateKey})`. The five credential types are themselves frozen Pydantic / dataclass types (S1-01 owns them).
  - `src/codegenie/events/payloads.py` — `RedactionFired` variant (`kind: Literal["redaction_fired"]`, `field_path: str`, `redaction_kind: Literal["typed_credential", "value_shape_aws", "value_shape_github_pat", "value_shape_jwt"]`).
  - `src/codegenie/events/log.py` — `EventLog.append_batch` to emit `RedactionFired` (via `EventBatchWriter.enqueue`).
- **External:**
  - Pydantic v2 `get_type_hints(...)` for field-type introspection.
  - `re` for the three value-shape patterns.

## Goal

Ship `class RedactedActivityResult(BaseModel)` + `seal(model: T) -> RedactedActivityResult` such that `seal` (a) rejects extra fields via Pydantic; (b) rejects fields whose declared type is in `SECRET_TYPES` with `SealError`; (c) scans all `str` fields against AWS / GitHub PAT / JWT regexes — match raises `SealError` AND emits a `RedactionFired` event; (d) is idempotent (`seal(seal(x)) == seal(x)`); (e) is observable (every `RedactionFired` lands in the canonical event log).

## Acceptance criteria

- [ ] **AC-1 — `RedactedActivityResult` base class.** `src/codegenie/durable/sanitizer.py` exports `class RedactedActivityResult(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")`. Subclasses are activity-specific (`RedactedRunSubgraphOutput(RedactedActivityResult)`, etc. — those land in S4-02 / S4-03 / S4-05). The base class carries a `_sanitized: Literal[True] = True` field per `phase-arch-design.md §C7` (a marker that `seal()` produced this instance).
- [ ] **AC-2 — `seal()` classmethod on `RedactedActivityResult`.** `RedactedActivityResult.seal(cls, model: BaseModel) -> RedactedActivityResult`. The `model` argument is the candidate Pydantic model whose fields are checked; `seal` returns either an instance of `cls` populated from `model.model_dump()` OR raises `SealError`.
- [ ] **AC-3 — Layer (a): `extra="forbid"`.** The `cls` configuration forbids extra fields. If `model.model_dump()` contains a key not in `cls.model_fields`, Pydantic raises during the `cls(**dumped)` reconstruction; `seal` catches and re-raises as `SealError(reason="extra_field", field=...)`. Test: a model with an extra field is rejected.
- [ ] **AC-4 — Layer (b): typed-credential-class blocklist (the load-bearing layer).** For each field in `cls.model_fields`, inspect `field_info.annotation`. If the annotation (resolved via `get_type_hints`) is in `SECRET_TYPES` — OR is a `Union` / `Optional` / `Annotated` whose unwrapped types contain a `SECRET_TYPES` member — raise `SealError(reason="typed_credential", field=field_name, type_name=...)`. **The check is on the declared type, not the runtime value.** Test asserts a `cls` declaring `field: GitHubToken` raises at `seal` time regardless of the value.
- [ ] **AC-5 — Layer (c): value-shape regex backstop.** After layers (a) and (b) pass, scan every `str`-typed field value against three patterns:
    - `AWS_PATTERN = re.compile(r"AKIA[0-9A-Z]{16}")` (AWS Access Key ID).
    - `GITHUB_PAT_PATTERN = re.compile(r"ghp_[A-Za-z0-9]{36}")` (GitHub Personal Access Token).
    - `JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}")` (JWT).
    
    A match (a) emits a `RedactionFired(field_path=field_name, redaction_kind="value_shape_aws"|"value_shape_github_pat"|"value_shape_jwt")` event through `EventLog.append_batch` (batched — `RedactionFired` is NOT `@critical_event`); (b) raises `SealError(reason="value_shape", field=field_name, pattern=...)`.
- [ ] **AC-6 — `seal()` is idempotent.** `seal(seal(x)) == seal(x)` — calling `seal` on an already-sealed instance returns a structurally-equal `RedactedActivityResult` (and does NOT re-emit `RedactionFired`). Property test asserts the property over Hypothesis-generated sealed instances.
- [ ] **AC-7 — `SealError` carries typed forensic info.** `codegenie.durable.sanitizer.SealError(Exception)` carries `.reason: Literal["extra_field", "typed_credential", "value_shape"]`, `.field: str`, and one of `.type_name: str | None` (for typed_credential) or `.pattern: str | None` (for value_shape). Tests assert all three reason paths populate the right attributes.
- [ ] **AC-8 — `RedactionFired` emission targets the canonical log.** When layer (c) fires, `RedactionFired` lands in `events.events` via the batched writer (no sync flush). Integration test: construct a `cls` with a `str` field; pass a `model` whose value is `"ghp_" + "a"*36`; `seal` raises; the next batched flush includes one `RedactionFired` row whose `redaction_kind = "value_shape_github_pat"`. **This is the canonical "the sanitizer is observable" assertion.**
- [ ] **AC-9 — Idempotent re-seal does NOT re-fire `RedactionFired`.** AC-6's idempotence implies the `RedactionFired`-emission side effect must not double-fire on the second `seal(seal(x))` call. Implementation: `seal` checks if `model` already has `_sanitized=True`; if so, skip the layers (the instance was already validated). Test asserts only ONE `RedactionFired` row per logical failure.
- [ ] **AC-10 — Hypothesis-generated secret shapes are all rejected.** `tests/property/test_secret_shape_hypothesis.py` generates strings matching each of the three regexes (using `from_regex(...)` Hypothesis strategy); asserts `seal` raises `SealError(reason="value_shape")` for every such string when injected into a `cls` with one `str` field. **This is the canonical "the regex backstop catches every known-shape secret" assertion.**
- [ ] **AC-11 — `SECRET_TYPES` registry is the source of truth.** Adding a new type to `SECRET_TYPES` IS the only legal way to extend the typed-credential blocklist (ADR-0008 §Consequences: "expanding it is a one-line additive change"). A unit test asserts `SECRET_TYPES` is a `frozenset` containing exactly five types: `{GitHubToken, LlmApiKey, MicroVmCredential, PostgresPassword, SshPrivateKey}`. Adding a sixth requires updating this golden — a code-review signal.
- [ ] **AC-12 — `Union` / `Optional` / `Annotated` types are unwrapped.** A field declared `field: GitHubToken | None` is rejected (the `Union` is unwrapped, `GitHubToken` is in `SECRET_TYPES`). Same for `Optional[GitHubToken]` and `Annotated[GitHubToken, ...]`. Tests assert each form raises.
- [ ] **AC-13 — `seal` is stateless and pure (no I/O for layers a + b).** Layers (a) and (b) issue zero Postgres queries. Layer (c) issues at most one batched-emit per scan (multiple regex hits in one model = multiple `RedactionFired` events). The pure path is microsecond-scale (~10-50 µs per `seal`).
- [ ] **AC-14 — Performance envelope: ~10-50 µs per `seal`.** Microbenchmark in test: 10k `seal` calls on a clean (non-secret) 5-field model; assert wall-clock < 1 s (i.e., p50 < 100 µs). NOT a formal G6 perf assertion; just a sanity floor.
- [ ] **AC-15 — `mypy --strict` + lint clean.**

## Implementation outline

1. **`SECRET_TYPES` first.** Verify (or create) `src/codegenie/types/credentials.py` with the five credential types (frozen Pydantic models or simple newtypes — S1-01 nominally owns them). Define `SECRET_TYPES: Final[frozenset[type]] = frozenset({GitHubToken, LlmApiKey, MicroVmCredential, PostgresPassword, SshPrivateKey})`.
2. **`SealError`** in `src/codegenie/durable/sanitizer.py` per AC-7.
3. **`RedactedActivityResult` base class** per AC-1.
4. **`seal` implementation:**
    ```python
    @classmethod
    def seal(cls, model: BaseModel) -> "RedactedActivityResult":
        # Idempotence shortcut: model is already a RedactedActivityResult-derived instance
        if isinstance(model, RedactedActivityResult) and getattr(model, "_sanitized", False):
            return cls.model_validate(model.model_dump())

        # Layer (a) — Pydantic extra="forbid" — handled by cls() reconstruction below
        # Layer (b) — typed-credential blocklist
        hints = get_type_hints(cls, include_extras=False)
        for field_name, field_type in hints.items():
            if field_name.startswith("_"):
                continue
            unwrapped = _unwrap_type(field_type)  # handles Union/Optional/Annotated
            if any(t in SECRET_TYPES for t in unwrapped):
                raise SealError(
                    reason="typed_credential",
                    field=field_name,
                    type_name=next(t.__name__ for t in unwrapped if t in SECRET_TYPES),
                )

        # Layer (c) — value-shape regex backstop on str fields
        dumped = model.model_dump()
        for field_name, value in dumped.items():
            if isinstance(value, str):
                for pattern, kind in _PATTERNS:
                    if pattern.search(value):
                        _emit_redaction_fired(field_name, kind)  # batched
                        raise SealError(
                            reason="value_shape",
                            field=field_name,
                            pattern=kind,
                        )

        # Reconstruct via cls() — layer (a) extra="forbid" fires here
        try:
            return cls.model_validate(dumped)
        except ValidationError as e:
            raise SealError(reason="extra_field", field=str(e.errors()[0]["loc"][0]))
    ```
5. **`_unwrap_type(field_type) -> tuple[type, ...]`** — helper. Handles `Union[A, B]` → `(A, B)`; `Optional[X]` (which is `Union[X, None]`) → `(X, NoneType)`; `Annotated[X, *]` → `_unwrap_type(X)`; bare type `X` → `(X,)`.
6. **`_emit_redaction_fired`** — module-level helper that posts a `RedactionFired` event to a module-singleton `EventLog` reference. **Design decision**: `seal` needs an `EventLog` to emit. Two paths:
    - **(a) Thread an `EventLog` argument** through every call site. Pure but invasive.
    - **(b) Module-level singleton `_REDACTION_LOG: EventLog | None = None`** with an init function `init_sanitizer(log: EventLog) -> None` called once at worker startup (S6-01).
    
    Choose **(b)** for ergonomics — the alternative makes every activity's return annotation pass an event log alongside the model. The init function is the seam; tests use a fake `EventLog` via the init.
    
    The init function and module singleton are documented in the module docstring as the only legal init mechanism; a fence test in S4-06 / S6-01 can assert init happens before any activity dispatch. If init has not happened (singleton is `None`), `_emit_redaction_fired` raises `RuntimeError` — fail loud.
7. **`_PATTERNS`** — module-level `Final` tuple of `(pattern, kind)` pairs per AC-5.
8. **Idempotence shortcut (AC-6, AC-9).** The `if isinstance(model, RedactedActivityResult)` check at the top of `seal` short-circuits. Confirm: if a contributor passes an unsealed `BaseModel` that happens to have `_sanitized=True` (e.g., crafted via subclass), the `isinstance` check fails and full sanitization runs. Defensive.

## TDD plan — red / green / refactor

### Red — failing test first

Test file path: `tests/unit/durable/test_sanitizer_value_shape.py`

Test intent: A `RedactedActivityResult`-derived class with one `str` field, fed a `model` whose value is a known GitHub PAT shape (`"ghp_" + "a"*36`), must raise `SealError(reason="value_shape")` AND the raw secret value must never appear in `model_dump_json()` of any in-process object. **This is the user-requested canonical assertion.**

```python
# Test outline only.
def test_github_pat_shape_value_never_surfaces_in_dump(fake_event_log):
    """ADR-0008 layer (c) — the value-shape regex backstop catches GitHub PAT
    even when the field type is plain `str`. The raw secret MUST NOT survive
    in any output. seal() raises; the model that gets sealed is the one we
    constructed with the bad value, but the SealError carries only the
    field_name + redaction_kind — never the value."""
    init_sanitizer(log=fake_event_log)

    class Candidate(RedactedActivityResult):
        token_field: str

    secret = "ghp_" + "a" * 36
    model = _CandidateInput(token_field=secret)  # an unsealed Pydantic carrier

    with pytest.raises(SealError) as exc_info:
        Candidate.seal(model)

    assert exc_info.value.reason == "value_shape"
    assert exc_info.value.pattern == "value_shape_github_pat"
    assert exc_info.value.field == "token_field"
    # The raw value MUST NOT appear in the exception's representation.
    assert secret not in str(exc_info.value)
    assert secret not in repr(exc_info.value)
    # The fake event log captured a RedactionFired emission.
    emitted = fake_event_log.captured_events
    assert len(emitted) == 1
    assert emitted[0].kind == "redaction_fired"
    assert emitted[0].field_path == "token_field"
    assert emitted[0].redaction_kind == "value_shape_github_pat"
    # And critically — the RedactionFired event MUST NOT carry the raw value.
    assert secret not in emitted[0].model_dump_json()
```

Why it fails: `codegenie.durable.sanitizer` doesn't exist yet.

### Green — minimal pass

- Implement `RedactedActivityResult`, `seal`, `SealError`, `_PATTERNS`, `_emit_redaction_fired`, `init_sanitizer`.
- Red test passes.

### Required follow-on tests (one per AC)

- **`test_extra_field_rejected`** (AC-3) — `model` has a field not in `cls.model_fields`; `SealError(reason="extra_field")`.
- **`test_typed_credential_field_rejected`** (AC-4) — `cls` declares `field: GitHubToken`; `seal` raises regardless of value.
- **`test_union_typed_credential_rejected`** (AC-12) — `cls` declares `field: GitHubToken | None`; raises.
- **`test_optional_typed_credential_rejected`** (AC-12) — `cls` declares `field: Optional[GitHubToken]`; raises.
- **`test_annotated_typed_credential_rejected`** (AC-12) — `cls` declares `field: Annotated[GitHubToken, ...]`; raises.
- **`test_aws_access_key_rejected`** (AC-5) — value matches `AKIA[0-9A-Z]{16}`; raises `value_shape_aws`.
- **`test_jwt_shape_rejected`** (AC-5) — value matches JWT pattern; raises `value_shape_jwt`.
- **`test_seal_is_idempotent`** (AC-6) — `seal(seal(clean_model)) == seal(clean_model)`; only ONE `RedactionFired` if both fail (it never gets to the second `seal` because the first raises — adjust phrasing: the test is on a CLEAN model where both seals succeed; no `RedactionFired` either time).
- **`test_redaction_fired_lands_in_event_log`** (AC-8) — integration with real `EventLog`; `RedactionFired` row exists in `events.events`.
- **`test_secret_types_registry_is_exactly_five`** (AC-11) — `SECRET_TYPES == frozenset({GitHubToken, LlmApiKey, MicroVmCredential, PostgresPassword, SshPrivateKey})`.
- **`test_seal_microbenchmark`** (AC-14) — 10k seals < 1 s.

### Property test (Hypothesis)

`tests/property/test_secret_shape_hypothesis.py` per AC-10:

```python
@given(st.from_regex(r"AKIA[0-9A-Z]{16}", fullmatch=True))
def test_every_aws_key_shape_rejected(value: str, fake_event_log):
    init_sanitizer(log=fake_event_log)
    class Candidate(RedactedActivityResult):
        field: str
    model = _CandidateInput(field=value)
    with pytest.raises(SealError) as exc_info:
        Candidate.seal(model)
    assert exc_info.value.reason == "value_shape"
    # The raw value NEVER surfaces.
    assert value not in str(exc_info.value)
```

Three parametrizations: one per regex pattern. Hypothesis generates 100+ examples each; if any slip past, the test fails with the offending string. **The Hypothesis-generated regex strings will surface boundary cases (e.g., the JWT pattern's `[A-Za-z0-9_-]{20,}` greedy quantifier might let unusual padding through).**

### `seal(seal(x))` property test

`tests/property/test_sanitizer_idempotence.py` per AC-6:

```python
@given(st.text(min_size=1, max_size=100).filter(lambda s: not any(p.search(s) for p, _ in _PATTERNS)))
def test_seal_idempotent_on_clean_model(value: str):
    """seal(seal(x)) == seal(x) for non-secret-shaped values."""
    class Candidate(RedactedActivityResult):
        field: str
    model = _CandidateInput(field=value)
    once = Candidate.seal(model)
    twice = Candidate.seal(once)
    assert once == twice
```

### Refactor

- Extract `_PATTERNS` to a module-level `Final` tuple with named constants (`AWS_PATTERN`, `GITHUB_PAT_PATTERN`, `JWT_PATTERN`) for easy ADR-citation in the module docstring.
- Module docstring on `sanitizer.py` cites ADR-0008's three layers; references the load-bearing layer (b); names the `RedactionFired` weekly-canary report cadence (ADR-0008 §Consequences).
- The `_emit_redaction_fired` helper accepts an injectable `event_log` for testability (the module singleton is a default; the test fakes it via `init_sanitizer(log=fake)`).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/durable/sanitizer.py` | `RedactedActivityResult`, `seal`, `SealError`, `_PATTERNS`, `init_sanitizer`, `_emit_redaction_fired`. |
| `src/codegenie/types/credentials.py` | Verify `SECRET_TYPES` is the load-bearing source of truth (S1-01 may own this; this story verifies & augments if needed). |
| `tests/unit/durable/test_sanitizer_value_shape.py` | Red test + AC-3, AC-5, AC-7. |
| `tests/unit/durable/test_sanitizer_typed_credential.py` | AC-4, AC-12. |
| `tests/integration/durable/test_redaction_fired_emission.py` | AC-8 — `RedactionFired` lands in `events.events`. |
| `tests/property/test_secret_shape_hypothesis.py` | AC-10 — Hypothesis over the three regexes. |
| `tests/property/test_sanitizer_idempotence.py` | AC-6 — `seal(seal(x)) == seal(x)`. |
| `tests/fixtures/durable/sanitizer.py` | `fake_event_log` fixture with `.captured_events: list[EventPayload]`. |

## Out of scope

- **Activity return-type fence** — S4-06 (`tests/fence/test_activity_payload_typing.py`).
- **`GitHubToken`-typed-return adversarial test** — S4-07 (`tests/adv/test_typed_credential_blocklist.py`).
- **Secret-leakage-in-history adversarial sweep** — S4-07 (`tests/adv/test_secret_leakage_in_history.py`).
- **Workflow-level escalation on repeated `RedactionFired` events** — out of scope; ADR-0008 §Consequences mentions a weekly canary report (Phase 13+ observability).
- **Cryptographic-signing of Capability tokens (HMAC)** — explicitly rejected by ADR-0008 §Options-considered. Trust is process-level (K8s ServiceAccount + task-queue partitioning); this story neither implements nor leaves room for HMAC.
- **`ContextVar`-based capability threading** — explicitly rejected by ADR-0008 §Consequences; capabilities are explicit-argument-threaded.
- **Adding a 6th `SECRET_TYPES` member** — additive; not in scope here.
- **Adding a 4th regex pattern** — additive; not in scope here. ADR-0008's three patterns are the Phase-9 baseline.

## Notes for the implementer

### §1 — The load-bearing layer is (b), not (c)

The critic's attack on the security-first design [S] was: regex over field names misses every well-named field (`evidence_digest: GitHubToken`). Layer (b) — typed-credential-class blocklist on the *declared field type* — is the defense. Layer (c) — value-shape regex — is a *backstop*, not the primary defense.

This means: if a contributor's activity declares `evidence_digest: GitHubToken`, the seal raises at the *type-introspection* step, not the regex step. The regex step only ever fires when (i) the contributor declared a `str` field (not a typed credential), AND (ii) the runtime value happens to match a known credential shape.

The Hypothesis property test (AC-10) covers layer (c) thoroughly because the regex backstop must catch every well-formed credential shape Hypothesis can generate. Layer (b) is unit-tested per credential type (AC-4 + AC-12).

### §2 — `get_type_hints` vs `field.annotation`

Pydantic v2's `model.model_fields[name].annotation` may carry the raw annotation including `Annotated[...]` metadata. `typing.get_type_hints(cls)` resolves forward references and (with `include_extras=False`) strips `Annotated`. **Use `get_type_hints`** because:
1. Forward references to `GitHubToken` defined in another module would otherwise be a `ForwardRef` object, not the actual type.
2. `Annotated[GitHubToken, ConfigDict(...)]` should still trigger layer (b) — `get_type_hints(..., include_extras=True)` lets us peek inside.

Implementation: call `get_type_hints(cls, include_extras=True)` once at class-definition time (cache on `cls.__sanitizer_hints__` if cost matters); or call per `seal` (negligible).

### §3 — The module-singleton `EventLog` is the seam

`init_sanitizer(log: EventLog) -> None` sets `_REDACTION_LOG` at worker startup. The S6-01 worker bootstrap calls it. Tests call it with a `FakeEventLog` whose `captured_events: list[EventPayload]` records emissions.

Alternative considered: pass `event_log` as a kwarg to `seal`. Rejected because every activity's return annotation would have to include the event log — invasive and noisy. The module singleton is the boundary.

If `_REDACTION_LOG is None` at `_emit_redaction_fired` time, raise `RuntimeError("sanitizer not initialized; call init_sanitizer at worker startup")`. Fail loud beats silent skip.

### §4 — `RedactionFired` MUST NOT carry the raw secret

The `RedactionFired` event variant declares `field_path: str` and `redaction_kind: Literal[...]` — NOT a `value` field. By construction, the emitted event records that a redaction fired and where, but never what. The red test asserts `secret not in emitted[0].model_dump_json()`.

If a future story wants more forensic detail (e.g., the first 4 characters of the secret for triage), that's an ADR amendment to ADR-0008 — additive but requires explicit justification.

### §5 — The `_sanitized` marker is a Pydantic field, not an attribute

`_sanitized: Literal[True] = True` declared on `RedactedActivityResult` makes it a Pydantic field, which means it appears in `model_dump()` and round-trips via `model_validate`. This is intentional: a sealed instance shipped across the activity boundary is recognizable on the receiving side via `isinstance` + `_sanitized` check.

The underscore prefix is a Python convention for "private-ish", but Pydantic v2 includes underscore-prefixed names in `model_fields` by default for `Literal`-typed annotations. Confirm during implementation; if Pydantic excludes it, rename to `sanitized: Literal[True] = True` (drop the underscore).

### §6 — Idempotence shortcut and emission de-duplication

AC-9 (idempotent re-seal doesn't re-fire `RedactionFired`) is implemented via the early-return:

```python
if isinstance(model, RedactedActivityResult) and getattr(model, "_sanitized", False):
    return cls.model_validate(model.model_dump())
```

A `seal(seal(clean_model))` call:
1. First `seal(clean_model)` — runs all layers, none fire, returns a sealed instance.
2. Second `seal(sealed_instance)` — early-returns; no layer (c) scan; no `RedactionFired`.

A `seal(seal(bad_model))` call cannot happen because the first `seal` raised — there's no sealed instance to pass to the second `seal`.

### §7 — `model_dump_json` MUST NOT leak the secret

The user-supplied requirement: a test that constructs `RedactedActivityResult` with a known secret-shaped field MUST assert the raw value never surfaces in `model_dump_json()`. Because `seal` raises before returning a sealed instance for a secret-shaped value, this is structurally enforced: there is no sealed instance to dump. The red test verifies this by asserting the raw value also doesn't appear in `str(SealError)` / `repr(SealError)` — the error path is the only object the test could capture.

### §8 — Not adopted (YAGNI)

- **`re.compile` once at module load, not per `seal`** — already the design (`_PATTERNS` is module-level `Final`).
- **Async `seal`** — not adopted. `seal` is sync (microsecond-scale); the `RedactionFired` emission is async (calls into `EventLog.append_batch`). Mixing: `seal` schedules the emission via `asyncio.create_task(_emit_redaction_fired(...))` and proceeds to raise. The task fires in the background; the test's `fake_event_log.captured_events` records it. Document this fire-and-forget pattern in the module docstring.
- **Recursive scanning of nested models** — out of scope. ADR-0008's three patterns target flat field structures; nested `BaseModel` fields are scanned recursively because `model_dump()` returns a dict-of-dict; the regex scan only fires on `str` values, not on nested dicts. If a future activity's return has a `Bundle` nested model containing a secret-shaped string, the scan catches it. Confirm in implementation; add a test if uncertain.
- **A `release_sanitizer()` for tests** — not adopted. Tests use a fresh `init_sanitizer(log=new_fake)` to replace the singleton; the `fake_event_log` fixture is function-scoped and re-inits each test.
