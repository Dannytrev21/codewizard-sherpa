# Story S1-03 — Extend `ALLOWED_BINARIES` and egress allowlist

**Step:** Step 1 — Establish the six additive seams, ADRs, and the contract-surface snapshot canary
**Status:** Ready
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-P7-002 (this phase ADR-0003), ADR-P7-008 (this phase ADR-0001), production ADR-0012

## Context

The Phase 7 transform + signal collectors need to subprocess-launch `docker` (for `buildx`) and `dive` (for layer inspection), and the Docker daemon they invoke must pull base images from `cgr.dev` (Chainguard) and `docker.io` (Docker Hub). Phase 5's sandbox chokepoint enforces a strict allowlist on both the subprocess launcher and the egress proxy; this story extends both lists *additively* — sorted-list appends, two entries on each list, no behavior change for existing entries. It is half of the ADR-P7-002 seam bundle (the other half — `ObjectiveSignals` widening — lives in S1-02).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 13 ADR-P7-002` (the `ALLOWED_BINARIES` + egress allowlist file edits; behavior-preservation note).
  - `../phase-arch-design.md §Agentic best practices ›Tool-use safety` — names the two binaries and two egress hosts being added.
  - `../phase-arch-design.md §Edge cases #7, #16` — `~/.docker/config.json` auth flow and `cgr.dev` cold pull, both of which depend on `cgr.dev` and `docker.io` being allowed.
- **Phase ADRs:**
  - `../ADRs/0003-objective-signals-widening-and-allowlists.md` — ADR-P7-002 — the file-by-file allowlist diff.
  - `../ADRs/0010-credentials-via-docker-config-no-secretd-daemon.md` — ADR-P7-010 — operator-side credentials only; this story does not touch credentials, but the allowlist must permit the binaries that *read* `~/.docker/config.json` (i.e., `docker`).
  - `../ADRs/0001-six-named-additive-seams-and-adr-0028-amendment.md` — ADR-P7-008 — sorted-list append is behavior-preserving additive.
- **Production ADRs:**
  - `../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md` — sandbox chokepoint discipline; allowlist is the chokepoint surface.
- **Existing code (read before writing):**
  - `src/codegenie/sandbox/host/allowed_binaries.py` — read to confirm the sort order, casing convention, and how the list is consumed by the launcher. If the file uses a `frozenset` rather than a `list`, adjust the test accordingly.
  - `src/codegenie/sandbox/host/egress_allowlist.py` — same read-before-write; pay attention to whether hosts are stored as bare hostnames (`cgr.dev`) vs URL-style (`https://cgr.dev`) or with explicit ports.
  - Any Phase 5 chokepoint enforcement (`sandbox/host/launcher.py` or similar) — read to confirm the rejection path raises a specific exception type the test can catch.

## Goal

`docker` and `dive` are members of `ALLOWED_BINARIES`; `cgr.dev` and `docker.io` are members of the egress allowlist; the Phase 5 chokepoint still rejects everything else (a sentinel `not_on_the_list` binary and an unknown host are both refused loudly).

## Acceptance criteria

- [ ] `src/codegenie/sandbox/host/allowed_binaries.py` includes `"docker"` and `"dive"` in the sorted list at the correct alphabetical positions; existing entries are unchanged in name, casing, and order.
- [ ] `src/codegenie/sandbox/host/egress_allowlist.py` includes `"cgr.dev"` and `"docker.io"` in the sorted list at the correct alphabetical positions; existing entries are unchanged.
- [ ] `tests/unit/sandbox/host/test_allowed_binaries_extension.py` is committed and green: (a) both new binaries are in the list; (b) the existing binaries are still in the list (read from a fixture snapshotted from `master`); (c) the launcher's reject path still raises (use whatever exception type Phase 5 raises today — e.g., `BinaryNotAllowed` or equivalent) on a sentinel like `"not_on_the_list_xyz"`; (d) the list is sorted (i.e., `sorted(ALLOWED_BINARIES) == list(ALLOWED_BINARIES)`).
- [ ] `tests/unit/sandbox/host/test_egress_allowlist_extension.py` is committed and green with the symmetric four checks: both new hosts present; existing hosts unchanged; reject path raises on a sentinel host (e.g., `"evil.test"`); list is sorted.
- [ ] `ruff check`, `ruff format --check`, and `mypy --strict` pass on both edited files and both new test files.

## Implementation outline

1. Read both allowlist files end-to-end. Note the storage type (list / tuple / frozenset / sorted Python literal), the host-name convention (bare vs URL-style), and where the launcher / egress proxy looks them up.
2. Capture the pre-edit `master` versions of each list as test fixtures (`tests/fixtures/allowlists/allowed_binaries.v0.6.json`, `tests/fixtures/allowlists/egress.v0.6.json`) so the "existing entries unchanged" assertion is real, not asserted against the post-edit list.
3. Write the failing tests (TDD red).
4. Append `"docker"`, `"dive"` to `ALLOWED_BINARIES`; append `"cgr.dev"`, `"docker.io"` to the egress allowlist. Re-sort if the on-disk format requires it; preserve casing and quote style.
5. Refactor: add a comment near each new entry citing ADR-P7-002 (one line — do not over-comment).

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test files:
- `tests/unit/sandbox/host/test_allowed_binaries_extension.py`
- `tests/unit/sandbox/host/test_egress_allowlist_extension.py`

```python
# tests/unit/sandbox/host/test_allowed_binaries_extension.py
import json, pathlib, pytest
from codegenie.sandbox.host.allowed_binaries import ALLOWED_BINARIES
from codegenie.sandbox.host.launcher import launch  # adjust to actual symbol; read launcher.py first


def test_docker_and_dive_added():
    assert "docker" in ALLOWED_BINARIES
    assert "dive" in ALLOWED_BINARIES


def test_existing_entries_unchanged():
    baseline = json.loads(
        pathlib.Path("tests/fixtures/allowlists/allowed_binaries.v0.6.json").read_text()
    )
    for binary in baseline:
        assert binary in ALLOWED_BINARIES, f"existing binary {binary!r} disappeared"


def test_list_is_sorted():
    assert list(ALLOWED_BINARIES) == sorted(ALLOWED_BINARIES)


def test_unlisted_binary_still_rejected_at_chokepoint():
    # use whatever the Phase 5 chokepoint exception class is — read launcher.py
    with pytest.raises(Exception):  # narrow to the real exception type
        launch("not_on_the_list_xyz", argv=["--help"])
```

```python
# tests/unit/sandbox/host/test_egress_allowlist_extension.py
import json, pathlib, pytest
from codegenie.sandbox.host.egress_allowlist import EGRESS_ALLOWLIST
from codegenie.sandbox.host.egress import check_host  # adjust to actual symbol


def test_cgr_dev_and_docker_io_added():
    assert "cgr.dev" in EGRESS_ALLOWLIST
    assert "docker.io" in EGRESS_ALLOWLIST


def test_existing_egress_hosts_unchanged():
    baseline = json.loads(
        pathlib.Path("tests/fixtures/allowlists/egress.v0.6.json").read_text()
    )
    for host in baseline:
        assert host in EGRESS_ALLOWLIST, f"existing host {host!r} disappeared"


def test_egress_list_sorted():
    assert list(EGRESS_ALLOWLIST) == sorted(EGRESS_ALLOWLIST)


def test_unlisted_host_still_rejected():
    with pytest.raises(Exception):  # narrow to the real exception type
        check_host("evil.test")
```

Expected red failure mode: `AssertionError: 'docker' not in ALLOWED_BINARIES` (first test) and the symmetric failure on the egress side. Pre-edit baseline fixtures and unlisted-reject tests pass trivially against `master` — they exist to *stay* green after the edit and would fail loudly if you accidentally deleted an existing entry or weakened the chokepoint.

### Green — make it pass

In `src/codegenie/sandbox/host/allowed_binaries.py`, append `"docker"` and `"dive"` at the right alphabetical positions. In `src/codegenie/sandbox/host/egress_allowlist.py`, append `"cgr.dev"` and `"docker.io"`. If the on-disk format is a Python list literal, keep it human-sortable (one entry per line; commas at end-of-line); preserve the existing quote style.

### Refactor — clean up

- One-line comment per new entry: `"docker",  # ADR-P7-002 — Phase 7 distroless migration` and the symmetric `# ADR-P7-002` next to the two new egress hosts.
- Re-run the chokepoint's existing test suite (whatever Phase 5 already ships) and confirm zero regressions in the unrelated rejection cases.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/host/allowed_binaries.py` | Append `"docker"` and `"dive"` (ADR-P7-002). |
| `src/codegenie/sandbox/host/egress_allowlist.py` | Append `"cgr.dev"` and `"docker.io"` (ADR-P7-002). |
| `tests/unit/sandbox/host/test_allowed_binaries_extension.py` | New test — TDD red anchor; existing-entry preservation + chokepoint still rejects. |
| `tests/unit/sandbox/host/test_egress_allowlist_extension.py` | New test — same on the egress side. |
| `tests/fixtures/allowlists/allowed_binaries.v0.6.json` | Pre-edit `master` snapshot — anchor for "existing entries unchanged." |
| `tests/fixtures/allowlists/egress.v0.6.json` | Same on the egress side. |

## Out of scope

- **`ObjectiveSignals` widening** — S1-02 (the other half of the ADR-P7-002 bundle).
- **`tools/buildkit.py` and `tools/dive.py` wrappers that actually call `docker` and `dive`** — Step 2 (S2-02, S2-03). This story makes the allowlist *permit* the calls; it does not make them.
- **`tools/digests.yaml` entries for `dive`, `docker buildx`, `strace`, etc.** — S2-07.
- **Contract-surface snapshot regen capturing the new allowlist sorted lists** — S1-07.
- **Operator-credential ergonomics (`~/.docker/config.json` flow)** — Phase 8 / operator-notes; this story merely makes the calls reachable.

## Notes for the implementer

- The chokepoint exception type is the test's load-bearing assertion target. If you write `with pytest.raises(Exception)` and leave it that broad, the test passes even on `ImportError` — *narrow it* to the actual exception class Phase 5 raises (read `sandbox/host/launcher.py` and `sandbox/host/egress.py` first). The contract-surface snapshot (S1-07) will capture the chokepoint's behavior; this test is the runtime backup.
- The two baseline fixtures must come from `master`, not from the post-edit state. The simplest path: on a clean `master` checkout, `python -c "import codegenie.sandbox.host.allowed_binaries as m; import json; print(json.dumps(sorted(m.ALLOWED_BINARIES), indent=2))" > tests/fixtures/allowlists/allowed_binaries.v0.6.json`. Same on the egress side. Commit the fixtures *before* you edit the source files.
- Host-name format: `cgr.dev` and `docker.io` are bare-hostname. If the existing egress list uses URL form (`https://...`), match precedent and add both forms; if it uses bare hostname only, append bare. Do not invent a new format.
- If `ALLOWED_BINARIES` is a `frozenset` rather than a `list`, the "list is sorted" assertion is meaningless and should be replaced with `sorted(tuple(ALLOWED_BINARIES)) == sorted(...)` or removed. Match the actual storage type. Do not change `list` to `frozenset` (or vice-versa) — that's a Phase 5 contract change outside this story's scope.
- ADR-P7-002 bundles three file edits under one ADR. Do not split into three ADRs. This story takes the two allowlist files; S1-02 takes the `ObjectiveSignals` widening; both stories cite ADR-P7-002 in their PR descriptions.
- The Phase 5 chokepoint's rejection path is the actual security boundary. The "unlisted binary still rejected" / "unlisted host still rejected" tests verify the *additive* nature of this change — adding two entries must not weaken the rejection. If those tests get accidentally weakened (e.g., by changing the launcher to accept anything), the whole point of the allowlist disappears. Read these tests in code review with the same scrutiny as the additions themselves.
- Trailing newline / final-newline matters when these files are picked up by the contract-surface snapshot in S1-07. Use `text=True` Python reads, single trailing newline, no trailing whitespace.
