# Story S6-04 — `grype db update` scoped-egress adversarial test

**Step:** Step 6 — Ship Layer C dynamic probes: `SyftSBOMProbe`, `GrypeCVEProbe`
**Status:** Ready
**Effort:** S
**Depends on:** S6-02 (`GrypeCVEProbe` implementation; the probe-level allowlist-size unit test is the probe-PR gate, and this story is the **system-level** gate that asserts the negative case — attempted egress to a non-allowlisted host is refused at the sandbox boundary)
**ADRs honored:** ADR-0003 (the per-tool scoped-egress allowlist mechanism is the load-bearing defense; `grype db update` is the **only** default outbound network in Phase 2 — Goals #12; the allowlist size = 1 invariant is CI-gating)

## Context

Phase 2's outbound-network claim is narrow and load-bearing: **the only default outbound network is `grype db update`, with `network="scoped"` allowlisted to exactly one host** (the grype vuln-DB host, pinned in `src/codegenie/catalogs/tools/grype-db-listing.signed.json`). Every other Phase-2 subprocess runs with `network="none"`. Goals #12 names this constraint; ADR-0003 codifies the mechanism; S6-02's probe-level test pins the **positive** case (the allowlist contains exactly one host). This story pins the **negative** case end-to-end: an attempt to reach a *non-allowlisted* host from inside `tools.grype.db_update` must surface as a `ToolNonZeroExit` with `confidence: low` on the slice, **never** as a successful network round-trip the gather then trusts.

The system-level test is small but disjoint from the probe-level test. The probe-level test asserts the allowlist *is configured correctly*; this test asserts the **sandbox actually enforces** the allowlist. They are two different defense layers — configuration drift (allowlist accidentally widened in config) is closed by the probe-level test; mechanism breakage (the sandbox no longer enforces what the allowlist names) is closed by this one. Both are required.

The test invokes `codegenie gather` end-to-end against a fixture where `ctx.config["grype"]["db_host"]` is **deliberately misconfigured** to a host the test setup proves is unreachable (e.g., a locally-bound port that exits immediately, or a known-blackhole IP). The probe attempts `grype db update`; the wrapper raises `ToolNonZeroExit`; the probe records `confidence: low` + `warnings: ["grype.db_update_failed"]` per the rule sheet in S6-02; the gather completes exit-0; the slice still validates. The cross-link in this story's test to ADR-0003's scoped-egress subsection is explicit — a future engineer who weakens the scoped-egress mechanism finds this test, and this test points them at the ADR that justifies the constraint.

This is the smallest story in Step 6 (effort S) but it is **CI-gating**. Step 8 (S8-06) wires the workflow; this story owns the test.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Goals" #12` — "No outbound network from `codegenie/`. The only Phase 2 outbound network is `grype db update` invoked via the sandboxed subprocess on cache miss."
  - `../phase-arch-design.md §"Edge cases"` row 5 — `grype db update` non-zero exit; wrapper raises `ToolNonZeroExit`; probe catches; `confidence: medium` (with stale DB) or `low` (no DB). This story's test exercises the network-blocked path; the wrapper-level translation is the same.
  - `../phase-arch-design.md §"Component design" #9 GrypeCVEProbe`§"Vuln DB lifecycle" — `network="scoped"` allowlisted to the grype DB host.
  - `../phase-arch-design.md §"Component design" #2 tools/grype.py` — `grype db check / update` lifecycle.
- **Phase ADRs:**
  - **`../ADRs/0003-subprocess-sandbox-profile-extension.md`** — the load-bearing ADR for this test. §"Decision" lists `network="scoped"` semantics; §"Consequences" names `tests/adv/test_no_unscoped_network_egress.py` and the per-tool allowlist mechanism. **Cross-link this ADR explicitly in the test file's module docstring** so any future weakening of the allowlist mechanism brings a reader here.
  - `../ADRs/0004-tools-digests-yaml-pin-manifest.md §"grype-db-listing.signed.json"` — the in-tree pin's host field is the canonical allowlist value.
  - `../ADRs/0005-allowed-binaries-additions.md §"grype"` — `network="scoped"` for `db update` only.
- **Production ADRs:**
  - `../../../production/adrs/0005-no-llm-in-gather-pipeline.md` — `confidence: low` on network-blocked egress is honest evidence, not a probe bug.
- **Source design:**
  - `../final-design.md §"Goals — No outbound network in codegenie itself"` — "The only Phase 2 process that touches the network is `grype db update`, invoked exactly once per gather on cache miss via the sandboxed subprocess."
  - `../final-design.md §"Conflict-resolution table" D9` — refuses [S]'s local registry mirror; the scoped allowlist + sandboxed call is the entire defense.
- **Existing code (post S6-02):**
  - `src/codegenie/probes/grype_cve.py` — `GrypeCVEProbe`; rule sheet in S6-02 §Notes maps `db_state == "stale_update_failed"` → `confidence: medium` (DB present, update refused) or `confidence: low` (DB missing entirely).
  - `src/codegenie/tools/grype.py` — `tools.grype.db_update(host_allowlist=[...])` raises `ToolNonZeroExit` when the sandbox refuses egress.
  - `src/codegenie/exec.py` — `run_in_sandbox(..., network="scoped", scoped_egress_hosts=[...])`; `bwrap` enforces via `--unshare-net` + a network namespace with a single-host route; `sandbox-exec` enforces via `(allow network-outbound (remote ip ...))` profile fragment (best-effort on macOS per ADR-0003).
  - `tests/adv/conftest.py` (extended by S6-03) — `gather_run(fixture_dir)` helper.

## Goal

Ship one CI-gating system-level adversarial test that proves the Phase-2 scoped-egress allowlist actually refuses egress to a non-allowlisted host: with the test's `grype.db_host` configured to an unreachable target and the local grype DB stale, the probe's `db update` invocation raises `ToolNonZeroExit`, the probe emits `confidence: low` + `warnings: ["grype.db_update_failed"]`, the gather completes exit-0, and the slice validates.

## Acceptance criteria

- [ ] `tests/adv/test_grype_db_update_blocked.py` exists and is CI-gating (no `@pytest.mark.skip`, no `@pytest.mark.xfail` beyond the documented macOS-skip).
- [ ] The test's module docstring **explicitly cross-links** ADR-0003 §"Decision" and ADR-0003 §"Consequences" — a reader removing or weakening the test discovers the architectural justification.
- [ ] The test fixture lives at `tests/fixtures/grype_db_update_blocked/` and contains a minimal Dockerfile (so `SyftSBOMProbe` produces a valid SBOM the CVE probe consumes) + a config snippet (or env-var override) that sets `grype.db_host` to a deliberately unreachable host. Acceptable choices for the unreachable host: (a) `127.0.0.1:1` (the smallest unprivileged port; nothing listens), (b) a locally-bound socket the test setup binds and then closes (RST on connect), or (c) a known-blackhole IP (`192.0.2.1` is the IANA TEST-NET-1; never routable). Document the choice in the fixture README.
- [ ] Test setup forces a `db update` attempt: either (a) pre-seed `.codegenie/cache/` with a sentinel that marks the local grype DB as stale (`age_hours > 24`), or (b) monkeypatch `tools.grype.db_status` to return `age_hours = 25` for this single invocation. Choice (a) is cleaner for end-to-end fidelity; choice (b) requires plumbing a test hook through the CLI. Pick (a) and document.
- [ ] Test asserts:
  - [ ] Process exit code is `0` (per S6-02 §Notes: gather completes; `--strict` is the CI hammer, default is exit-0 with honest evidence).
  - [ ] `repo-context.yaml` parses and validates.
  - [ ] `repo-context.yaml#probes.grype_cve.confidence in {"medium", "low"}` — `medium` if the local DB is present-but-stale (scan still runs against stale DB per S6-02 §Notes rule sheet), `low` if no local DB at all. Both are acceptable for this test; the test asserts the set membership.
  - [ ] `repo-context.yaml#probes.grype_cve.warnings` contains `"grype.db_update_failed"`.
  - [ ] The slice validates against `grype_cve.schema.json` (no `extra` fields, severity enum honored).
  - [ ] The audit log records a `grype.db_update_attempted` event with `network="scoped"`, `host_allowlist=[<unreachable host>]`, `outcome="non_zero_exit"`. (The audit event family is from Phase 0/1; this assertion is on the JSONL audit chain.)
  - [ ] No unhandled exception in gather stderr.
- [ ] The test demonstrates the **single-host allowlist** invariant: the allowlist length recorded in the audit event is exactly 1. A regression that widens the allowlist (e.g., a wildcard added "for development convenience") fails this test.
- [ ] macOS handling is explicit: `pytestmark = pytest.mark.skipif(sys.platform == "darwin", reason="macOS sandbox-exec network constraint is best-effort; see ADR-0003. Linux CI is the authoritative gate.")` — or assert the macOS behavior matches Linux (both are acceptable; the skip is the simpler choice).
- [ ] Test wall-clock is bounded by `pytest.timeout(60)`; if the sandbox doesn't refuse egress and the network call hangs, the timeout fails the test for the right reason.
- [ ] Definition-of-done: `ruff check` + `ruff format --check` on the test pass; `pytest tests/adv/test_grype_db_update_blocked.py -q` passes on Linux CI; on macOS, the test skips with the ADR-referencing reason.

## Implementation outline

1. **Ship the fixture.** `tests/fixtures/grype_db_update_blocked/` containing:
   - `Dockerfile` — a minimal valid Dockerfile so `SyftSBOMProbe` runs successfully and produces an SBOM for `GrypeCVEProbe` to consume (e.g., `FROM alpine:3.19\nRUN apk add --no-cache curl\n` — the `RUN` line is fine because the *image* will be built and scanned in the Step 1 sandbox at `network="none"`; we *want* `apk add` to fail and `SyftSBOMProbe` to record honest evidence — wait, that conflicts with this test's purpose; use instead a Dockerfile that doesn't need network at build time: `FROM alpine:3.19\nCOPY app.txt /app.txt\n` with a one-byte `app.txt`).
   - `app.txt` — one-byte file.
   - `.codegenie/config.yaml` (or equivalent) — sets `grype.db_host: "127.0.0.1:1"` (or chosen unreachable target).
   - `README.md` — documents the fixture's purpose + the unreachable-host choice.
2. **Pre-seed grype DB staleness.** Pick implementation (a) from Acceptance §3: at fixture-build time, commit a `.codegenie/cache/grype_db_state.json` (or equivalent) with `last_update_at: 1970-01-01T00:00:00Z`. The Phase 0 cache layer reads this; `tools.grype.db_status` derives `age_hours` from it (or the equivalent path — verify against S6-02's wrapper implementation).
3. **Author the test.**
   ```python
   """Pins:
   - Scoped-egress allowlist refuses non-allowlisted host (the mechanism, not just the config).
   - grype db update is the ONLY default outbound network in Phase 2 (Goals #12).
   - Allowlist length == 1 — recorded in audit event.
   Traces to: ADR-0003 §Decision + §Consequences (scoped-egress mechanism);
   ADR-0004 §grype-db-listing.signed.json (allowlist source);
   phase-arch-design.md §Goals #12 + §Edge cases row 5."""
   ```
   - `pytestmark = pytest.mark.skipif(sys.platform == "darwin", reason="ADR-0003 best-effort on macOS")`.
   - `@pytest.mark.timeout(60)` on the test function.
   - Use the `gather_run` fixture from `tests/adv/conftest.py` (S6-03's deliverable).
   - Assertions per Acceptance §4.
4. **Audit-event assertion.** Open the audit JSONL at `.codegenie/audit.jsonl`; find the `grype.db_update_attempted` event; assert `event.network == "scoped"`, `len(event.host_allowlist) == 1`, `event.outcome == "non_zero_exit"`. The audit-event family is Phase 0/1's; this test's assertion is on three event fields.

## TDD plan — red / green / refactor

### Red

Path: `tests/adv/test_grype_db_update_blocked.py`

```python
"""Pins:
- Sandbox refuses egress to non-allowlisted host (mechanism not config).
- grype db update is the ONLY default outbound network in Phase 2 (Goals #12).
- Audit event records network="scoped", allowlist length == 1, outcome="non_zero_exit".
Traces to: ADR-0003 (scoped-egress mechanism, §Decision + §Consequences);
ADR-0004 §grype-db-listing.signed.json; phase-arch-design.md §Goals #12 + §Edge cases row 5."""
import json
import shutil
import sys
from pathlib import Path
import pytest
import yaml

FIXTURE = Path("tests/fixtures/grype_db_update_blocked")

pytestmark = pytest.mark.skipif(
    sys.platform == "darwin",
    reason="macOS sandbox-exec network constraint is best-effort; see ADR-0003. "
           "Linux CI is the authoritative gate.",
)

@pytest.mark.timeout(60)
def test_grype_db_update_refused_to_non_allowlisted_host(tmp_path, gather_run):
    # ARRANGE: copy fixture (including the pre-seeded stale-DB sentinel) to tmp_path
    shutil.copytree(FIXTURE, tmp_path, dirs_exist_ok=True)

    # ACT
    result = gather_run(tmp_path, timeout_s=60)

    # ASSERT: exit + slice
    assert result.exit_code == 0
    ctx = yaml.safe_load(result.repo_context_yaml_path.read_text())
    grype = ctx["probes"]["grype_cve"]
    assert grype["confidence"] in {"medium", "low"}
    assert "grype.db_update_failed" in grype["warnings"]

    # ASSERT: audit event
    audit_path = tmp_path / ".codegenie" / "audit.jsonl"
    events = [json.loads(line) for line in audit_path.read_text().splitlines()]
    db_update_events = [e for e in events if e.get("event") == "grype.db_update_attempted"]
    assert len(db_update_events) == 1
    ev = db_update_events[0]
    assert ev["network"] == "scoped"
    assert len(ev["host_allowlist"]) == 1
    assert ev["outcome"] == "non_zero_exit"

    # ASSERT: no traceback
    assert "Traceback" not in result.stderr
```

Run `pytest tests/adv/test_grype_db_update_blocked.py -q`. Fails — fixture doesn't exist (or audit event isn't being emitted yet, if S6-02 didn't emit one). If the latter, file a small follow-up against S6-02 to add the audit event; the audit-event family is already defined in Phase 0/1 (`AuditWriter.emit(event_name, **fields)`).

### Green

Implement per the **Implementation outline**: fixture → stale-DB seed → test. Run on Linux CI; verify the bwrap sandbox actually refuses egress to `127.0.0.1:1` (it should — `--unshare-net` puts the subprocess in a fresh network namespace where the loopback is empty).

### Refactor

- Confirm the test file does **not** import or invoke anything that would itself egress (no `requests`, no `socket`, no `httpx`). The `fence` CI job already enforces this at `src/codegenie/`; tests are not covered, so be disciplined.
- Confirm the `gather_run` helper from S6-03 is used; do not fork the harness.
- `ruff check` + `ruff format` on the test file.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/grype_db_update_blocked/Dockerfile` | New — minimal Dockerfile so SyftSBOMProbe produces an SBOM. |
| `tests/fixtures/grype_db_update_blocked/app.txt` | New — one-byte file referenced by `COPY` in the Dockerfile. |
| `tests/fixtures/grype_db_update_blocked/.codegenie/config.yaml` | New — sets `grype.db_host` to the chosen unreachable host. |
| `tests/fixtures/grype_db_update_blocked/.codegenie/cache/grype_db_state.json` | New — pre-seeded stale-DB sentinel so `tools.grype.db_status` reports `age_hours > 24`. |
| `tests/fixtures/grype_db_update_blocked/README.md` | New — documents fixture purpose + unreachable-host choice. |
| `tests/adv/test_grype_db_update_blocked.py` | New — system-level scoped-egress adversarial test (CI-gating). |

## Out of scope

- **The probe-level allowlist-size unit test** — owned by S6-02. This story is the system-level negative-case gate.
- **`tests/adv/test_no_unscoped_network_egress.py`** — owned by Step 1 / S1-06 root adversarial sweep; that test asserts the *broader* "no other Phase-2 wrapper egresses" claim across all tools. This story's test is narrower: it asserts the mechanism enforces the allowlist for the one tool that has a documented egress.
- **Hostile-Dockerfile + zip-bomb adversarial tests** — S6-03's deliverable; disjoint threat surface.
- **macOS sandbox-exec hardening to enforce scoped-egress at parity with Linux `bwrap`** — refused at the ADR-0003 level; Linux CI is the authoritative gate.
- **CVE-feed-triggered selective invalidation** — Phase 14 (S6-02 §"Out of scope"); this story does not touch the cache-invalidation mechanism.
- **Coverage gate enforcement** — wired by S8-06.

## Notes for the implementer

- **Two defense layers, two tests, both required.** The probe-level test (S6-02) catches a misconfigured allowlist; this test catches a broken enforcement mechanism. Reviewers occasionally argue these duplicate each other — they do not. Defense-in-depth is the point.
- **The audit-event assertion is the load-bearing part.** Even if the slice fields read correctly, an absent or misshapen audit event means a portfolio-scale rerun couldn't *prove* what happened. The audit JSONL is the forensic trail; this test pins three fields of one event.
- **`127.0.0.1:1` vs. `192.0.2.1` choice.** `127.0.0.1:1` is fast (connection refused, immediate RST) and works on every Linux/macOS dev box. `192.0.2.1` (TEST-NET-1) is slower (no route, eventual timeout) and tests the "no route" case. Pick `127.0.0.1:1` — the failure mode the sandbox must refuse is "any host other than the allowlisted one", and the speed matters for CI. Document the choice.
- **The fixture's `Dockerfile` must succeed under `--network=none`.** If you pick `FROM alpine:3.19\nRUN apk add curl`, the build itself fails inside Step 1's sandbox (`apk add` needs network) and `SyftSBOMProbe` records `build_status: failed` — and then `GrypeCVEProbe.applies()` returns `False` (per S6-02's `applies()` rule) and the entire test target probe is skipped. The fixture must build cleanly so the test reaches the `GrypeCVEProbe` code path. Use `FROM alpine:3.19\nCOPY app.txt /app.txt\n` — no network needed.
- **Pre-seeding the stale-DB sentinel.** S6-02's `tools.grype.db_status` reads a metadata file the grype binary maintains in its DB directory; the stale sentinel needs to map to that file's actual format. If the format is opaque, plumb a `--db-cache-dir` override and the test sets it to a tmpdir containing the right files. Verify against S6-02's wrapper implementation; do not invent a new sentinel format here.
- **`network="scoped"` on macOS is best-effort.** ADR-0003 §"Consequences" is explicit: `sandbox-exec`'s network constraints are weaker than Linux `bwrap`'s. The macOS skip is the right call; if a future engineer wants to *not* skip on macOS, they need to first strengthen `exec.py`'s `sandbox-exec` profile, and that's a separate ADR amendment.
- **Cross-link ADR-0003 in the docstring, not just in the references.** A future engineer hunting "why does this test exist?" reads the test file first; the docstring brings them to ADR-0003 §"Decision" + §"Consequences", which is where they discover that weakening this test means re-litigating the entire Phase 2 outbound-network claim.
- **Exit-0 vs `--strict`.** The test runs without `--strict`. `--strict` is the CI flag that elevates `confidence: low | medium` into exit-3 — it lives in the workflow, not in this test. Step 8 (S8-03) ships `test_strict_flag_fails_on_low_confidence.py`; this story is orthogonal.
- **This is the smallest story in Step 6, and it is the most cross-architectural one.** Effort S, but it cross-cuts ADR-0003 (sandbox mechanism), ADR-0004 (signed listing → allowlist value), ADR-0005 (`grype` ADR-gating), Goals #12 (single default outbound network), and the audit-event family from Phase 0/1. A regression here invalidates the Phase-2 threat-model claim wholesale; treat the green CI run as load-bearing.
