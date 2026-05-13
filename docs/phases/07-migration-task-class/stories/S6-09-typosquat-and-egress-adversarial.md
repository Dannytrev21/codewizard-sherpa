# Story S6-09 — Adversarial typosquat + egress-block tests

**Step:** Step 6 — Broaden coverage: adversarial Dockerfile corpus, second E2E fixture, HITL path, LLM-fallback path
**Status:** Ready
**Effort:** S
**Depends on:** S6-04
**ADRs honored:** ADR-P7-002 (`docker`/`dive` allowlisted; `cgr.dev`/`docker.io` egress allowlist), ADR-P7-010 (operator-side credentials only)

## Context

Phase 7 introduces two attacker-controllable surfaces: the **image-name** the catalog or LLM proposes (poisoned YAML, hallucinated registry hostname, typosquat — `cgr.dev/chamguard/...`), and the **`RUN` commands** inside Dockerfiles (which could attempt arbitrary egress during build). The architecture's defenses are: (a) an image-name allowlist regex enforced in `resolve_target_image` (`^cgr\.dev/chainguard/[a-z0-9-]+(@sha256:[a-f0-9]{64}|:[a-z0-9._-]+)$`); (b) the in-VM egress proxy that drops anything outside Phase 5's egress allowlist + records an audit event `sandbox.egress.blocked`.

This story is the *adversarial-test* counterpart to those defenses. Both tests live under `tests/adversarial/` (separate from the unit/integration trees) so they are easy to enumerate as a security suite. The typosquat test asserts the regex rejects every plausible hostile variant; the egress-block test exercises a real Dockerfile build with a `RUN curl https://evil.test/` line and asserts the proxy drops it + records the audit event.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Edge cases #3` — typosquat allowlist regex (line 1195)
  - `../phase-arch-design.md §Testing strategy ›Adversarial tests` (lines 1298–1311) — adversarial suite enumeration
  - `../phase-arch-design.md §Testing strategy ›Fixture portfolio ›typosquat_lookup` (line 1272) and `›build_egress_blocked` (line 1273)
  - `../phase-arch-design.md §Component 9 ›Pre-rendered base_catalog.json` — the YAML the typosquat case poisons
  - `../phase-arch-design.md §Agentic best practices ›Tool-use safety ›Network egress` (line 1177)
- **Phase ADRs:**
  - `../ADRs/0003-objective-signals-widening-and-allowlists.md` — ADR-P7-002 — `cgr.dev`, `docker.io` are the *only* egress destinations allowed; egress proxy drops everything else
  - `../ADRs/0010-credentials-via-docker-config-no-secretd-daemon.md` — ADR-P7-011 — credentials are operator-side; egress proxy does not affect that
- **Existing code:**
  - `src/codegenie/graph/nodes/distroless/resolve_target_image.py` (S5-02) — the allowlist regex
  - `src/codegenie/sandbox/host/egress_allowlist.py` (S1-03 extension) — the egress allowlist destinations
  - `src/codegenie/sandbox/run_in_sandbox.py` (Phase 5) — the egress proxy and `sandbox.egress.blocked` audit event emitter
  - `src/codegenie/catalogs/distroless/cve_image_recommendations.yaml` (S2-06) — the YAML the typosquat case poisons (fixture, not in-tree mutation)
- **Phase 5 prior art:**
  - `../../05-validation-sandbox/` — egress proxy + audit events shape; the assertion convention this test consumes

## Goal

`tests/adversarial/typosquat_lookup.py` exercises ≥ 5 typosquat-poisoned `base_catalog`/LLM inputs against the image-name allowlist regex and asserts every rejection produces an audit event; `tests/adversarial/build_egress_blocked.py` runs `codegenie migrate run` on a fixture whose `Dockerfile` contains `RUN curl https://evil.test/`, asserts the egress proxy drops the request, and the audit chain contains `sandbox.egress.blocked` with the disallowed destination recorded.

## Acceptance criteria

- [ ] `tests/adversarial/typosquat_lookup.py` exists and is green. It:
  - Loads a fixture poisoned-catalog YAML at `tests/adversarial/fixtures/poisoned_catalog.yaml` containing **at least 5** hostile entries: `cgr.dev/chamguard/node:20`, `cgr.dev.evil/chainguard/node:20`, `evil.cgr.dev/chainguard/node:20`, `cgr.dev/chainguard/../escape:20`, `localhost:5000/chainguard/node:20` (host-bypass), plus an LLM-shaped hallucinated string that contains a Chainguard-like prefix but trailing garbage.
  - For each hostile entry, asserts `resolve_target_image` (or the helper that owns the regex) rejects with the expected reason code (typically `catalog_miss` or `image_name_rejected`).
  - Asserts an audit event `catalog.image_name_rejected` (or whichever name S5-02 emits) is recorded per rejection, with the offending image name preserved.
  - Asserts a canonical entry (e.g., `cgr.dev/chainguard/node:20@sha256:<64-hex>`) **passes** the regex — guards against the test being a regex-reject-everything tautology.
- [ ] `tests/adversarial/build_egress_blocked.py` exists and is green on the reference Linux DinD runner. It:
  - Loads a fixture at `tests/adversarial/fixtures/egress-blocked-distroless/` — minimal Node app, `Dockerfile` whose `RUN` block contains `curl https://evil.test/` (and *only* that egress so the test is unambiguous).
  - Invokes `codegenie migrate run` against the fixture (or invokes `tools/buildkit.py` directly if a full CLI run is unnecessary).
  - Asserts:
    - The build either fails with a clear egress-block error, *or* the build succeeds (proxy returned a 403) but the resulting image's behaviour is unaffected (because the `RUN` payload didn't materialize) — the test must define which is the system's contract per Phase 5.
    - An audit event `sandbox.egress.blocked` is recorded with `destination_host == "evil.test"`.
    - `evil.test` is NOT in `egress_allowlist`'s destinations.
    - Allowed destinations (`cgr.dev`, `docker.io`) in the same Dockerfile are NOT blocked (positive control — assert at least one allowed-destination pull also happened during the build).
- [ ] Both adversarial tests are wired into a `tests/adversarial/` lane in CI (separate `pytest` invocation if needed, so they can be flagged as security tests).
- [ ] `tests/adversarial/conftest.py` or `tests/adversarial/__init__.py` enumerates and exports the adversarial tests for discoverability.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` clean on both files.

## Implementation outline

1. **Typosquat test.** Author the poisoned catalog YAML with the ≥ 5 hostile entries. Write the red test asserting rejection. Run; red because the regex import or audit-event hook doesn't match the source. Adjust to match the source (do not duplicate the regex).
2. Add the positive control (a canonical entry that *passes*) so a regression that broke the regex into reject-all would fail this test.
3. **Egress-block test.** Author the fixture repo. The `Dockerfile`'s `RUN` block must do *only* the disallowed egress — keep the test signal clean. Optionally include a *second* `RUN` line that pulls from an allowed destination to anchor the positive control.
4. Write the red test asserting the audit event. Run; red because either the build doesn't run, the egress proxy isn't engaged, or the audit-event field naming differs from what the test expects.
5. Align with Phase 5's audit-event shape; commit.
6. Document both tests in `tests/adversarial/README.md` (if not already present from S6-01).

## TDD plan — red / green / refactor

### Red — write the failing tests first

```python
# tests/adversarial/typosquat_lookup.py
"""
Adversarial test: catalog / LLM proposals that try to typosquat or bypass
the canonical Chainguard image-name allowlist regex MUST be rejected, and
each rejection MUST emit an audit event.
"""
from pathlib import Path
import yaml
import pytest

from codegenie.graph.nodes.distroless.resolve_target_image import (
    IMAGE_NAME_REGEX, resolve_target_image
)

POISONED = Path(__file__).parent / "fixtures" / "poisoned_catalog.yaml"

HOSTILE_ENTRIES = [
    "cgr.dev/chamguard/node:20",
    "cgr.dev.evil/chainguard/node:20",
    "evil.cgr.dev/chainguard/node:20",
    "cgr.dev/chainguard/../escape:20",
    "localhost:5000/chainguard/node:20",
    "cgr.dev/chainguard/node:20; rm -rf /",
]

CANONICAL_ENTRY = "cgr.dev/chainguard/node:20@sha256:" + "a" * 64

@pytest.mark.parametrize("entry", HOSTILE_ENTRIES)
def test_typosquat_entries_rejected_by_regex(entry: str) -> None:
    assert IMAGE_NAME_REGEX.fullmatch(entry) is None

def test_canonical_entry_passes_positive_control() -> None:
    assert IMAGE_NAME_REGEX.fullmatch(CANONICAL_ENTRY) is not None

def test_poisoned_catalog_rejection_emits_audit_event(structlog_capture, snapshot_runner) -> None:
    catalog = yaml.safe_load(POISONED.read_text())
    for row in catalog["rows"]:
        result = resolve_target_image(advisory=..., catalog=catalog, image_proposal=row["to_image"])
        assert result.matched is False
    events = [e for e in structlog_capture.events if e["event"] == "catalog.image_name_rejected"]
    assert len(events) >= len(HOSTILE_ENTRIES)
```

```python
# tests/adversarial/build_egress_blocked.py
"""
Adversarial test: a Dockerfile RUN line that egresses to an unallowed
destination MUST be dropped by the in-VM egress proxy and recorded as
`sandbox.egress.blocked` in the audit chain.
"""
from pathlib import Path
from click.testing import CliRunner

from codegenie.cli.migrate import migrate

FIXTURE = Path(__file__).parent / "fixtures" / "egress-blocked-distroless"

def test_build_egress_to_evil_test_is_dropped_and_audited(tmp_path, snapshot_runner) -> None:
    repo = snapshot_runner.copy_fixture(FIXTURE, tmp_path)
    runner = CliRunner()
    result = runner.invoke(migrate, ["run", str(repo), "--target", "distroless",
                                     "--cve", "CVE-2024-FAKE"])

    # The build itself may have succeeded with a curl-failure mid-RUN, or failed at the gate.
    # Either way, the audit chain must record the block.
    ledger = _read_latest_ledger(repo)
    blocked = [e for e in ledger.audit_chain if e.kind == "sandbox.egress.blocked"]
    assert blocked, "expected at least one sandbox.egress.blocked audit event"
    assert any(e.fields["destination_host"] == "evil.test" for e in blocked)

    # Positive control: allowed destination was not blocked
    allowed = [e for e in ledger.audit_chain if e.kind == "sandbox.egress.allowed"]
    assert any(e.fields["destination_host"] in ("cgr.dev", "docker.io") for e in allowed)
```

Red: `IMAGE_NAME_REGEX` might not be a module-level constant (S5-02 / S6-02 surface it if needed); `sandbox.egress.blocked` field naming may differ from Phase 5 — match the source.

### Green — make it pass

- Author the poisoned catalog YAML.
- Author the egress-block fixture.
- Run both; align the assertions with the actual source code.
- If a hostile entry the test claims should fail *actually passes*, the regex needs strengthening — surface a follow-up to S5-02 / S6-02 immediately; do not soften the test.

### Refactor — clean up

- Add a docstring to each test referencing the ADR (P7-002, P7-010) and the architecture edge-case row (#3).
- Update `tests/adversarial/README.md` (created by S6-01) with both new files listed in its enumeration.
- If `structlog_capture` is a Phase 4 / Phase 5 test fixture, reuse it — do not re-implement structlog capture.

## Files to touch

| Path | Why |
|---|---|
| `tests/adversarial/typosquat_lookup.py` | New — image-name allowlist regex adversarial |
| `tests/adversarial/build_egress_blocked.py` | New — in-VM egress proxy adversarial |
| `tests/adversarial/fixtures/poisoned_catalog.yaml` | New — ≥ 5 hostile catalog entries |
| `tests/adversarial/fixtures/egress-blocked-distroless/Dockerfile` | New — contains `RUN curl https://evil.test/` |
| `tests/adversarial/fixtures/egress-blocked-distroless/server.js` | New — minimal Node app |
| `tests/adversarial/fixtures/egress-blocked-distroless/package.json` | New |
| `tests/adversarial/fixtures/egress-blocked-distroless/README.md` | New — adversarial purpose |
| `tests/adversarial/fixtures/advisories/cve-2024-fake.yaml` (if reuse from elsewhere doesn't exist) | New — synthetic advisory |

## Out of scope

- **The image-name allowlist regex itself.** Authored in S5-02; this story is the adversarial test for it.
- **The in-VM egress proxy.** Owned by Phase 5; this story is the adversarial test for it.
- **`cve_image_recommendations.yaml` schema-level validation against typosquats.** S2-06 ships the catalog with valid entries; this story poisons it at test time, not at production-load time. Production-load-time poisoning defense is the catalog schema validator (S2-06's `_schema.json`).
- **Cosign signature verification of the pulled base images.** Deferred to Phase 16 per `phase-arch-design.md §Adversarial tests ›Deferred`.
- **Cross-host cache poisoning across distributed workers.** Deferred to Phase 9 Temporal idempotency.
- **Prompt-injection in LABEL/RUN comments.** Asserted in S3-02's sanitizer test (Pass 5); the corpus fixture in S6-01 also covers it.

## Notes for the implementer

- The image-name regex is the *first* defense; a regression here unlocks every subsequent risk. Run this test in CI **always**, not as a "slow security suite that runs on cron". Adversarial tests are gating, not advisory.
- The egress-block test depends on Phase 5's in-VM egress proxy being engaged when `tools/buildkit.py` runs. Confirm that `validate_in_sandbox` invokes the build *through* the sandbox runner, not bare-metal. If it does not, this is a Phase 5 regression — surface and block.
- `evil.test` is in the `.test` TLD reserved by RFC 2606 — it never resolves on real DNS. This makes the test deterministic on any runner. **Do not** use a real hostile-looking domain (e.g., `evilcorp.com`); the test must be inherently safe.
- The poisoned catalog YAML is *not* a production catalog. Keep it under `tests/adversarial/fixtures/` so it cannot be loaded by production code paths.
- The `sandbox.egress.allowed` positive-control event may not exist as a separate audit type — Phase 5 may emit only `blocked` events. Adjust the assertion to "no `sandbox.egress.blocked` event lists `cgr.dev` or `docker.io` as the destination" if the positive event doesn't exist. The point is to prove the test signal is *specific* to `evil.test`, not a broad reject-all.
- The audit-chain field naming (`destination_host`, `kind`, `fields`) must match Phase 5's emitter exactly. Read Phase 5's audit-event source and align — do not invent field names.
- Per the cross-cutting determinism rule: this test runs subprocesses (docker, buildkit) so wall-clock variability is unavoidable; bound the test's timeout generously (e.g., `pytest.mark.timeout(300)`) and document.
- Update story `Status:` to `Done` when complete.
