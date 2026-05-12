# Story S3-05 — `stage6_validate.yaml` + `stage6_validate_loose.yaml` populated + digest-pinned `sandbox-policy.yaml`

**Step:** Step 3 — Implement DinD backend + SandboxSpecBuilder + SandboxHealthProbe
**Status:** Ready
**Effort:** S
**Depends on:** S3-01 (`SandboxSpecBuilder` consumes these catalogs)
**ADRs honored:** ADR-0013 (digest-pinned codegenie-owned policy YAML), ADR-0014 (`extra="forbid"` invariants — no `confidence` substring in policy field names), Open Q4 (one catalog or two — synthesis: ship both)

## Context

Step 1 shipped an empty `stage6_validate.yaml` stub schema-valid against `gates/catalog/_schema.json`. This story populates **both** the strict catalog (all six signals required, `non_retryable_failures: [trace]`) and the dev-mode loose catalog (`build`, `install`, `tests` only — for `codegenie remediate --gate loose`). It also lands the digest-pinned `tools/policy/sandbox-policy.yaml` (per ADR-0013) and its `tools/digests.yaml#sandbox.policy_yaml` BLAKE3 entry. After this story, `SandboxSpecBuilder.for_gate(stage6_validate, ...)` produces the golden spec asserted in S3-01.

ADR-0013 is the load-bearing reason this story exists: the policy file cannot live in the target repo (an LLM patch could neuter the policy gate). It lives under `tools/policy/` owned by codegenie itself, with its bytes verified against `tools/digests.yaml` at every `SandboxHealthProbe` invocation (S3-06).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Data model — gates/catalog/stage6_validate.yaml` — verbatim YAML this story commits.
  - `../phase-arch-design.md §Data model — tools/policy/sandbox-policy.yaml` — verbatim policy YAML.
  - `../phase-arch-design.md §Component design — Signal collectors` — "Policy YAML source is the digest-pinned `tools/policy/sandbox-policy.yaml` — NOT the repo's `.codegenie/policy.yaml`".
  - `../phase-arch-design.md §Edge case 10` — repo-resident policy ignored.
  - `../phase-arch-design.md §Open questions deferred — Open Q4` — one catalog or two; synthesis ships both.
- **Phase ADRs:**
  - `../ADRs/0013-digest-pinned-policy-yaml-codegenie-owned.md` — ADR-0013 — the policy YAML location, digest pinning, and the adversarial test it justifies.
  - `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — ADR-0014 — no `confidence` substring in policy schema either (consistency); the trace key in policy is `warn_on_low_coverage`, not `coverage_confidence`.
  - `../ADRs/0015-test-inventory-delta-asymmetric-policy.md` — informs `fail_on_negative_delta: true`, `warn_on_positive_delta: false`.
- **Source design:**
  - `../final-design.md §Synthesis ledger — Policy source row` — winner: codegenie-owned, digest-pinned.
- **Existing code:**
  - `src/codegenie/gates/catalog/_schema.json` (from S1-06) — schema both YAMLs validate against.
  - `src/codegenie/gates/catalog/stage6_validate.yaml` (from S1-06) — stub to populate.
  - `tools/digests.yaml` (from S1-07) — placeholder for `sandbox.policy_yaml` to fill.
  - `tests/schema/test_digests_yaml.py` (from S1-07) — presence-only check; this story leaves it presence-only (S6-03 upgrades to digest validation).

## Goal

Populate the two stage-6 YAML catalogs to match `phase-arch-design.md §Data model` verbatim and commit the digest-pinned `tools/policy/sandbox-policy.yaml` with its BLAKE3-128 hex digest in `tools/digests.yaml#sandbox.policy_yaml`.

## Acceptance criteria

- [ ] `src/codegenie/gates/catalog/stage6_validate.yaml` matches `phase-arch-design.md §Data model — gates/catalog/stage6_validate.yaml` byte-for-byte (modulo the `<pinned>` placeholder replaced by an actual digest pulled from `tools/digests.yaml#sandbox.base_image_node`).
- [ ] `src/codegenie/gates/catalog/stage6_validate_loose.yaml` exists with `required_signals: [build, install, tests]`, `retry_policy.max_attempts: 3`, `non_retryable_failures: []`, and reuses the same `sandbox:` block (DRY via YAML anchor if helpful; otherwise duplicate cleanly).
- [ ] Both files validate against `gates/catalog/_schema.json` (test added to `tests/gates/test_catalog_schema.py` if not already there).
- [ ] `tools/policy/sandbox-policy.yaml` matches `phase-arch-design.md §Data model — tools/policy/sandbox-policy.yaml` byte-for-byte.
- [ ] `tools/digests.yaml#sandbox.policy_yaml` carries the BLAKE3-128 (`blake3.blake3(open(path,"rb").read()).hexdigest(length=16)`) hex of `tools/policy/sandbox-policy.yaml`.
- [ ] `tests/schema/test_digests_yaml.py` is green (presence-only at this stage; S6-03 upgrades to value-validation).
- [ ] `tests/gates/test_catalogs_populated.py` asserts: (a) `stage6_validate.required_signals` contains all six kinds; (b) `non_retryable_failures` contains exactly `["trace"]`; (c) `stage6_validate_loose.required_signals` is exactly `["build","install","tests"]`; (d) the digest in `tools/digests.yaml` matches the actual file's BLAKE3 (re-computed in the test).
- [ ] `tests/adversarial/test_in_repo_policy_ignored.py` is created (or stubbed if S4-03 owns the full test) with a comment pointing forward to S4-03; the file at minimum imports the constant path and asserts it does **not** start with `.codegenie/`.
- [ ] No `confidence` substring in `sandbox-policy.yaml` field names (cross-checked manually; static ObjectiveSignals test does not cover YAML but the consistency invariant matters).
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `pytest` pass. `mypy --strict` not applicable to YAML.

## Implementation outline

1. Populate `src/codegenie/gates/catalog/stage6_validate.yaml` from the architecture spec. Pull the actual base-image digest from `tools/digests.yaml#sandbox.base_image_node` (added in this same story if not present from S1-07 placeholders — placeholder `sha256:0000...` is acceptable for unit tests; the live integration test in S3-07 will exercise a real pull).
2. Create `src/codegenie/gates/catalog/stage6_validate_loose.yaml`:
   ```yaml
   gate_id: stage6_validate_loose
   transition: stage6_validate_loose
   required_signals: [build, install, tests]
   retry_policy:
     max_attempts: 3
     retryable_failures: [build, install, tests]
     non_retryable_failures: []
     timeout_retryable: false
   sandbox:
     # same block as stage6_validate.yaml — duplicated, not anchored,
     # for grep-ability per Rule 11 (match codebase conventions).
     ...
   attempt_overrides: {}
   ```
3. Create `tools/policy/sandbox-policy.yaml` matching the arch spec.
4. Compute BLAKE3-128 of the policy file: `python -c "import blake3; print(blake3.blake3(open('tools/policy/sandbox-policy.yaml','rb').read()).hexdigest(length=16))"`. Write that hex string into `tools/digests.yaml` under `sandbox.policy_yaml`.
5. Write `tests/gates/test_catalogs_populated.py` and `tests/adversarial/test_in_repo_policy_ignored.py` (stub).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths:
- `tests/gates/test_catalogs_populated.py`
- `tests/adversarial/test_in_repo_policy_ignored.py` (stub; full test arrives in S4-03)

```python
# tests/gates/test_catalogs_populated.py
from pathlib import Path
import yaml, blake3
from codegenie.gates.catalog_loader import GateCatalogLoader

CATALOG = Path("src/codegenie/gates/catalog")
POLICY = Path("tools/policy/sandbox-policy.yaml")
DIGESTS = Path("tools/digests.yaml")

def test_stage6_validate_requires_all_six_signals():
    """The strict catalog is the production gate; missing any required signal silently
    weakens the gate. A failing test here is a security-grade regression."""
    data = yaml.safe_load((CATALOG / "stage6_validate.yaml").read_text())
    assert set(data["required_signals"]) == {"build","install","tests","trace","policy","cve_delta"}
    assert data["retry_policy"]["non_retryable_failures"] == ["trace"]
    assert data["retry_policy"]["timeout_retryable"] is False

def test_stage6_validate_loose_is_dev_subset():
    data = yaml.safe_load((CATALOG / "stage6_validate_loose.yaml").read_text())
    assert data["required_signals"] == ["build","install","tests"]
    assert data["gate_id"] == "stage6_validate_loose"

def test_both_catalogs_load_via_schema_validated_loader():
    loader = GateCatalogLoader(catalog_dir=CATALOG)
    loader.load_all()  # must not raise

def test_policy_digest_in_yaml_matches_file_bytes():
    """Catches a stale digest in tools/digests.yaml after a policy edit — the exact
    silent-drift failure ADR-0013 forbids."""
    digests = yaml.safe_load(DIGESTS.read_text())
    declared = digests["sandbox"]["policy_yaml"]
    actual = blake3.blake3(POLICY.read_bytes()).hexdigest(length=16)
    assert declared == actual, f"digest mismatch: {declared=} {actual=}"

def test_policy_yaml_has_no_confidence_substring():
    """Cross-check ADR-0014 invariant on policy schema field names too."""
    text = POLICY.read_text().lower()
    for banned in ("confidence", "self_reported", "model_says", "llm"):
        assert banned not in text, f"banned substring '{banned}' present in policy YAML"
```

```python
# tests/adversarial/test_in_repo_policy_ignored.py
# Stub — full behavioral test in S4-03 (needs collect_policy_signal).
from codegenie.sandbox.signals.policy import POLICY_PATH  # constant import

def test_policy_path_is_not_repo_resident():
    """ADR-0013: the policy collector must never reach into the target repo's .codegenie/."""
    assert ".codegenie" not in str(POLICY_PATH)
    assert str(POLICY_PATH).startswith("tools/policy/") or "policy/sandbox-policy.yaml" in str(POLICY_PATH)
```

### Green — make it pass

- Populate the two YAML files.
- Commit `tools/policy/sandbox-policy.yaml`.
- Compute the BLAKE3 digest and write it under `tools/digests.yaml#sandbox.policy_yaml`.
- Add the `POLICY_PATH` constant to `src/codegenie/sandbox/signals/policy.py` (a one-line module if it doesn't exist yet — full collector lives in S4-03).

### Refactor — clean up

- Re-run `ruff format --check` on Python; YAML linted via `yamllint` if available.
- Verify `pytest -k catalogs_populated` and `-k in_repo_policy_ignored` both green.
- Add a CHANGELOG or commit message note: "Phase 5 policy digest pinned to `<hex>`; future updates require ADR amendment + digest re-computation."

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/gates/catalog/stage6_validate.yaml` | Populate per arch spec. |
| `src/codegenie/gates/catalog/stage6_validate_loose.yaml` | New — dev-mode loose catalog. |
| `tools/policy/sandbox-policy.yaml` | New — codegenie-owned, digest-pinned policy. |
| `tools/digests.yaml` | Edit `sandbox.policy_yaml` to actual BLAKE3-128 hex. |
| `src/codegenie/sandbox/signals/policy.py` | One-line module exposing `POLICY_PATH` constant (full collector in S4-03). |
| `tests/gates/test_catalogs_populated.py` | New — populated + schema + digest tests. |
| `tests/adversarial/test_in_repo_policy_ignored.py` | New stub — full test in S4-03. |

## Out of scope

- The `collect_policy_signal` implementation that reads `POLICY_PATH` — S4-03.
- Upgrading `tests/schema/test_digests_yaml.py` from presence-only to value-validation — S6-03 covers it (it's broader than this story).
- Per-team or per-org policy overrides — explicitly disallowed by ADR-0013.
- Schema evolution (`schema_version: 1` → `2`) — future ADR.

## Notes for the implementer

- The base-image digest in `stage6_validate.yaml#sandbox.base_image` is a real `cgr.dev/chainguard/node@sha256:...` value. Look it up from `tools/digests.yaml#sandbox.base_image_node` (added if absent — placeholder `sha256:0000...` is OK for unit tests but the integration test in S3-07 needs a real one; coordinate with the operator running S3-07's first execution).
- **Do not** anchor-and-merge YAML keys across the two catalogs unless the codebase already does it elsewhere — grep first. Rule 11: match conventions.
- The policy YAML uses `warn_on_low_coverage` (per arch spec) — **not** `low_coverage_confidence`. ADR-0014's banned-substring list covers code field names but consistency demands it apply here too; the test in this story enforces it.
- `tools/digests.yaml` is multi-section (likely `images:`, `binaries:`, `sandbox:`); preserve existing structure when adding `sandbox.policy_yaml`. Run `git diff tools/digests.yaml` and confirm the diff is one-line minimal.
- BLAKE3-128 hexdigest (32 chars) is the convention from S3-01. Do not use BLAKE3-256 or BLAKE2 — they would mismatch `SandboxHealthProbe`'s digest verifier (S3-06).
- If you change `sandbox-policy.yaml` even by a whitespace character, the digest changes and CI fails. This is intentional. To update the policy: edit YAML → recompute digest → update `tools/digests.yaml` → file a follow-up ADR amendment per ADR-0013.
