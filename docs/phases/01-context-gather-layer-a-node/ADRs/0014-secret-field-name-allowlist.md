# ADR-0014: Narrow allowlist for the secret-shaped field-name rejection

**Status:** Accepted
**Date:** 2026-05-15
**Tags:** schema · secrets · facts-not-judgments · structural-defense · allowlist
**Related:** [ADR-0008 (Phase 0) two-pass output sanitizer chokepoint](../../00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md), [ADR-0010 (Phase 0) pydantic probe-output validator](../../00-bullet-tracer-foundations/ADRs/0010-pydantic-probe-output-validator.md), [production ADR-0005 — no LLM in gather](../../../production/adrs/0005-no-llm-in-gather-pipeline.md), [phase-arch-design.md §"Data model" CISlice](../phase-arch-design.md)

## Context

Phase 0 ADR-0008 + ADR-0010 install a defense-in-depth pattern: every dict key inside a `ProbeOutput.schema_slice` (at every nesting depth, through lists) is matched against `SECRET_FIELD_PATTERN = (?i)^.*(secret|token|password|credential|api[_-]?key|auth[_-]?token|bearer|access[_-]?key|private[_-]?key).*$`. Any match raises `SecretLikelyFieldNameError`. The pattern runs in two places — the Pydantic field-validator (coordinator/validator.py `_walk_and_enforce`) and the sanitizer's pass-1 (output/sanitizer.py `_walk_pass1_keys`) — keyed by the exact same compiled regex object so drift is impossible.

S4-01's `CISlice` (per `phase-arch-design.md §"Data model"`) declares a `references_secrets: list[str]` field — the literal identifier names captured from `${{ secrets.NAME }}` workflow expressions. The values under this key are GUARANTEED to be identifier names by construction (production ADR-0005: probes never resolve secret values; CIProbe never calls `os.environ.get`, never invokes `gh secret list`, never makes a network request). The field name itself contains the substring `secret` and trips the defense.

Without an exemption, the slice cannot be emitted: every `gather` run on a real repo with GHA workflows raises `SecretLikelyFieldNameError` at the trust boundary, the slice is dropped, and the envelope fails schema validation (CLI exits 3).

## Options considered

- **Rename the field.** Any name carrying the substring "secret" or "token" trips the regex. Generic alternatives (`vault_refs`, `referenced_workflow_vars`) lose the load-bearing semantic — a downstream Planner querying `references_secrets` knows it is reading the GHA-secrets surface; a renamed field obscures that. Rejected: the architectural data-model contract (`phase-arch-design.md §"Data model"`) names the field; renaming silently is a Rule 11 violation.
- **Loosen the regex.** Adding word-boundary anchors (`\bsecret\b`) would let `references_secrets` through but would also let `git_secrets_scanner_token` through. The defense exists because field names are an attacker-controllable surface (a malicious probe author can name fields anything); a tighter regex narrows the defense rather than honoring an exception. Rejected.
- **Drop the second-pass enforcement on this specific field.** Per-callsite carve-outs scatter the defense; ADR-0008 explicitly chose "single regex, two passes" to keep the policy auditable. Rejected.
- **A narrow, named, frozen allowlist of exempted field names.** One module-level `frozenset[str]`; both passes consult it. Adding a name requires touching the allowlist (a code review signal) and ideally an ADR amendment. Accepted.

## Decision

**Add `SECRET_FIELD_ALLOWLIST: frozenset[str]` at module scope in `coordinator/validator.py`, exported alongside `SECRET_FIELD_PATTERN`. The output sanitizer imports the same identity-shared object.**

Phase 1 contents:

```python
SECRET_FIELD_ALLOWLIST: frozenset[str] = frozenset({"references_secrets"})
```

Both walkers (`_walk_and_enforce` in `coordinator/validator.py` and `_walk_pass1_keys` in `output/sanitizer.py`) consult the allowlist before invoking `SECRET_FIELD_PATTERN.search(key)`:

```python
if (
    isinstance(k, str)
    and k not in SECRET_FIELD_ALLOWLIST
    and SECRET_FIELD_PATTERN.search(k)
):
    raise / on_match
```

The allowlist is **exact-match-by-key-name only** — the regex still runs on every other dict key at every depth. The defense's blast radius is narrowed by exactly the size of the allowlist; the rest of the trust boundary is untouched.

## Tradeoffs

| Gain | Cost |
|---|---|
| `references_secrets` (mandated by `phase-arch-design.md §"Data model" CISlice`) becomes representable; the slice ships | The allowlist is a permanent surface; every entry is a small permanent attack-surface widening that must be justified |
| Single source of truth: both passes import the same `frozenset` by identity, so they cannot drift | An attacker who controls a future probe could name a field exactly `references_secrets` to bypass the regex; the defense is now key-name-equality, not key-name-regex |
| Adding an entry requires an ADR amendment (this ADR is the precedent), which forces a security review | The allowlist's ergonomic temptation is "just add my field to it"; reviewers must push back on additions that don't carry the same construction-time guarantee |
| The probe never resolves a value (production ADR-0005); the values under `references_secrets` are by-construction literal identifier names, not the secret payload | The defense relies on the construction-time guarantee being upheld in every probe that emits `references_secrets`; a future regression in `CIProbe` that *does* resolve a value silently undermines the allowlist |

## Consequences

- The two `_walk_*` functions now check `k not in SECRET_FIELD_ALLOWLIST` before running the regex. The check is cheap (frozenset membership; O(1)) and runs once per dict key.
- `tests/unit/coordinator/test_probe_output_validator.py` and `tests/unit/output/test_sanitizer.py` add tests anchoring the allowlist behavior (allowlisted key passes; non-allowlisted secret-shaped key still raises).
- Adding a new entry to `SECRET_FIELD_ALLOWLIST` requires an ADR amendment naming the field, the construction-time guarantee that makes the values safe, and the probe(s) that emit it.
- The CLI's exit-3 path on `SecretLikelyFieldNameError` is unchanged for every other field-shape.

## Reversibility

**High.** Removing the allowlist (back to the strict regex-only defense) is a one-line revert at each callsite. The `references_secrets` field would have to be renamed across the slice schema, the probe, the data-model docs, and any downstream consumer — a multi-file change that the CISlice contract makes intentional. The forward direction (this ADR) is the looser policy; the reverse (no allowlist) is the stricter one.

## Evidence / sources

- `../phase-arch-design.md §"Data model" CISlice` — `references_secrets: list[str]` mandate
- `../stories/S4-01-ci-probe.md` AC-17, AC-18 — bounded regex + literal-name-only contract
- `../../00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md` — single-regex-two-passes defense
- `../../00-bullet-tracer-foundations/ADRs/0010-pydantic-probe-output-validator.md` — first pass: trust boundary
- `../../../production/adrs/0005-no-llm-in-gather-pipeline.md` — values never resolved
