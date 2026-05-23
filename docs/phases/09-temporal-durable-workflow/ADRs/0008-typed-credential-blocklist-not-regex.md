# ADR-0008: `RedactedActivityResult.seal()` — typed-credential-class blocklist (not regex; capability is process-level not cryptographic)

**Status:** Accepted
**Date:** 2026-05-23
**Tags:** smart-constructor · secret-redaction · capability-pattern · type-driven-security
**Related:** [ADR-0007](0007-two-task-queue-partitioning-and-expansion-by-addition.md), [production ADR-0008](../../../production/adrs/0008-secret-redaction.md)

## Context

Temporal records every activity input and return value in workflow history. A naive activity that returns `GitHubToken` as a field writes that token into history *forever* — anyone with read access to the cluster can see it. The security-first design [S] proposed two defenses: (1) regex over field names matching `_(KEY|TOKEN|SECRET)_` and (2) HMAC-signed Capability tokens with an in-process secret key.

The critic destroyed both: (1) the field-name regex misses every well-named field — `evidence_digest`, `attempt_id`, `failing_signals`, all carry potentially sensitive bytes under non-suspicious names; the regex catches the bad-naming case but provides no defense against the typed-but-renamed case. (2) the HMAC-signing scheme is decorative — anyone with the worker process's memory mount has the HMAC key, so non-forgeability claims do not hold against the in-process attacker model.

The real attacker model is: a compromised process inside one task queue should not be able to (a) mint Capabilities for actions outside its queue's allowlist, (b) return secrets via activity payloads, (c) signal a workflow on a different task queue. The trust root is **process-level** (task-queue partitioning + K8s ServiceAccount), not cryptographic.

## Options considered

- **Regex over field names.** `re.match(r".*(key|token|secret|password).*", field_name)` rejects matching fields. **Pattern:** name-based filtering. Catches naive cases; misses everything renamed.
- **Regex over field values.** `re.match(r"ghp_[A-Za-z0-9]{36}|AKIA[0-9A-Z]{16}|eyJ.+\..+\..+", value)` rejects matching values. **Pattern:** shape-based filtering. Catches known-shape secrets; misses novel shapes; one-shot per known credential family.
- **Typed-credential-class blocklist.** Inspect Pydantic field `type` annotations; reject any field whose declared type is in `SECRET_TYPES: Final[frozenset[type]]` (`GitHubToken | LlmApiKey | MicroVmCredential | PostgresPassword | SshPrivateKey`). The credential type registry is one frozen set; expanding it is one-line additive. **Pattern:** type-driven security; smart constructor that validates against the *type* not the *name* or *value*.
- **HMAC-signed Capability tokens.** Sign the Capability with a process-secret HMAC key; verify on use. **Pattern:** cryptographic capability. Rejected — in-process secret is forgeable by anyone with the worker mount.

## Decision

`RedactedActivityResult.seal()` applies **three layers in order**: (a) Pydantic `extra="forbid"` rejects unknown fields; (b) **typed-credential-class blocklist** — load-bearing — rejects any field whose declared type is in `codegenie.types.credentials.SECRET_TYPES`; (c) value-shape regex backstop emits `RedactionFired` events for known credential shapes that slipped past the type check. Capability tokens are typed Pydantic records, **not cryptographically signed**; the trust root is task-queue partitioning + K8s ServiceAccount. **Pattern: smart constructor + type-driven validation + process-level capability.**

## Tradeoffs

| Gain | Cost |
|---|---|
| Type-based detection catches the well-named-but-typed-as-secret field that regex misses (`evidence_digest: GitHubToken` is rejected) | Adding a new secret type to the codebase requires adding it to `SECRET_TYPES` — easy but must be remembered |
| One-line additive expansion of the registry — additions per ADR-0043 | `SECRET_TYPES` is global mutable state at import; must be `Final` after import |
| Value-shape backstop fires `RedactionFired` events so we *learn* every contributor near-miss — feeds the regex catalog | Backstop is regex; novel-shape credentials slip through and depend on the type check being correct |
| No cryptographic ceremony — no HMAC keys to manage; no key rotation; no "key compromised, rotate everything" drill | Capability cannot be verified by a *different* process (it's a token, not a signed assertion); trust is process-local |
| The Capability *type* is the auditable seam — every activity that takes a `PrOpenCapability` is grep-able | Trust depends on K8s ServiceAccount setup being correct — moves the trust problem to ops, not eliminates it |
| `mypy --strict` + `tests/fence/test_activity_payload_typing.py` catches an unsealed return statically, before the activity ships | Every activity return type must be `RedactedActivityResult`-derived — discipline applied to every new activity |

## Pattern fit

Smart-constructor (toolkit `design-patterns-toolkit.md §Construction-as-validation`) makes "this value has been validated" a type-level guarantee — an `RedactedActivityResult` exists only if `seal()` produced it. Type-driven security (the credential blocklist) puts the security guarantee in the *type* of the field, not the *name* or *value* — which the toolkit's "primitive obsession" entry flags as the cleaner alternative to stringly-typed regex defenses. Process-level capabilities (capability-pattern as a Pydantic record threaded explicitly, max 3 frames worker → activity wrapper → side-effect site) is the right shape when the trust root is the process boundary (K8s ServiceAccount mount) and the cryptographic version is decorative against the actual attacker.

## Consequences

- `codegenie.types.credentials.SECRET_TYPES: Final[frozenset[type]] = frozenset({GitHubToken, LlmApiKey, MicroVmCredential, PostgresPassword, SshPrivateKey})`.
- `codegenie.durable.sanitizer.RedactedActivityResult.seal(model)` is the only legal constructor; activities return `RedactedActivityResult`-derived classes.
- `tests/fence/test_activity_payload_typing.py` introspects every `@activity.defn` function and asserts return type is `RedactedActivityResult`-derived. Caught at `make test`, before CI.
- `tests/adv/test_typed_credential_blocklist.py` constructs an activity with a `GitHubToken`-typed return and asserts `seal()` raises `SealError`.
- `tests/adv/test_secret_leakage_in_history.py` constructs adversarial inputs matching each known shape regex and asserts rejection + `RedactionFired` emission.
- The `RedactionFired` events feed a weekly canary report — surfaces shapes seen in the wild before any token actually lands in history.
- Capability tokens (`EventLogWriteCapability`, `PrOpenCapability`, `LlmSpendCapability`) are frozen Pydantic records minted at worker startup from the K8s ServiceAccount mount; threaded as explicit arguments — no `ContextVar` (rejected — transitive imports break `__all__` discipline; explicit threading is the only safe shape across workflow/activity boundary).
- Per-queue Capability allowlist (`EventLogWriteCapability.allowed_kinds`) restricts which event kinds a worker may write — verified by `tests/adv/test_capability_token_scope.py`.

## Reversibility

**High.** The credential type registry is one frozen set; adding/removing types is trivial. The seal layers are independent; relaxing one (e.g., removing the regex backstop) is a one-line config change. The Capability pattern shape (Pydantic record + explicit threading) is the only invasive piece, and rewriting it to HMAC-signed (should the trust model change) is contained to `codegenie.durable.capabilities` + activity wrappers.

## Evidence / sources

- [`../phase-arch-design.md §C7 — Activity-boundary sanitizer`](../phase-arch-design.md#c7--activity-boundary-sanitizer-codegeniedurablesanitizer)
- [`../phase-arch-design.md §Scenario 4 — Secret in activity return`](../phase-arch-design.md#scenario-4--adversarial-secret-in-activity-return--typed-credential-blocklist-rejects-at-seal-time)
- [`../phase-arch-design.md §Non-goals — HMAC-signed capability tokens`](../phase-arch-design.md#non-goals)
- [`../phase-arch-design.md §Design patterns applied — #9`](../phase-arch-design.md#design-patterns-applied)
- [`../critique.md §Attacks on the security-first design — regex over field names`](../critique.md)
- [`../final-design.md §8 Activity-boundary sanitization`](../final-design.md)
- [production ADR-0008](../../../production/adrs/0008-secret-redaction.md)
