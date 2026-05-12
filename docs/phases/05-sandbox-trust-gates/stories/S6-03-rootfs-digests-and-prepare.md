# Story S6-03 — Pinned rootfs + `vmlinux` digest enforcement + `sandbox prepare`

**Step:** Step 6 — FirecrackerClient backend + KVM-gated CI smoke test
**Status:** Ready
**Effort:** M
**Depends on:** S6-01
**ADRs honored:** ADR-0013, ADR-0004, ADR-0001

## Context

`FirecrackerClient` (S6-01) compares the on-disk `firecracker`, `vmlinux`, and `rootfs.ext4` against constructor-supplied digests, but nothing yet *enforces* those digests against `tools/digests.yaml`. Without enforcement, an operator can silently swap the rootfs and the static CI fence test (`tests/schema/test_digests_yaml.py`) does not notice — it only checks key *presence*. This story upgrades the fence test to digest validation, bakes the pinned `vmlinux`+`rootfs.ext4` under `tools/firecracker/<rootfs_digest>/`, ships the documented bake procedure in `firecracker/rootfs.md`, and adds the `codegenie sandbox prepare --backend firecracker` subcommand so a clean machine can rebuild artifacts idempotently from inputs.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — FirecrackerClient` — `tools/firecracker/<rootfs_digest>/vmlinux + rootfs.ext4` layout; `prepare` subcommand contract.
  - `../phase-arch-design.md §Development view` — `tools/digests.yaml` keys (`sandbox.firecracker`, `sandbox.vmlinux`, `sandbox.rootfs`, `sandbox.policy_yaml`); `tests/schema/test_digests_yaml.py`.
  - `../phase-arch-design.md §Open Q1` — rootfs build cadence is a Phase 14 operational decision; `prepare` must be idempotent so cadence is policy, not mechanism.
  - `../phase-arch-design.md §Edge cases §6` — firecracker binary digest mismatch is non-retryable; surfaces as `FirecrackerBinaryMissing`.
- **Phase ADRs:**
  - `../ADRs/0013-digest-pinned-policy-yaml-codegenie-owned.md` — pattern for digest pinning in `tools/digests.yaml`; the four sandbox keys follow the same shape.
  - `../ADRs/0004-dind-default-macos-with-gate-isolation-class.md` — `tools/digests.yaml#sandbox.{firecracker,vmlinux,rootfs}` carries the actual binary + rootfs digests.
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — `prepare` CLI is operator surface; subprocess for `qemu-img`/`tar` lives in the `prepare` code path, not the runtime client.
- **Production ADRs:**
  - `../../../production/adrs/0019-sandbox-stack.md` — pinned rootfs is an explicit input to the eventual stack-resolution evidence.
- **Source design:**
  - `../final-design.md §Synthesis ledger row "tools/digests.yaml"` — digest pinning rationale.
- **Existing code:**
  - `src/codegenie/sandbox/firecracker/client.py` (from S6-01) — `_assert_binary_digest`, `_assert_rootfs_artifacts` currently use the digests passed at construction; this story makes those digests come from `tools/digests.yaml`.
  - `tests/schema/test_digests_yaml.py` (from S1-07) — currently asserts key presence only; this story upgrades to digest-value validation.
  - `src/codegenie/cli/sandbox.py` (from S1-07 or as new) — add the `prepare` subcommand here; full CLI surface lands in S8-01 but this subcommand is co-located now.
  - `tools/digests.yaml` — extend with real digest values (replacing S1-07 placeholders).
- **External docs:**
  - Firecracker kernel-rebuild recipe: <https://github.com/firecracker-microvm/firecracker/blob/main/docs/rootfs-and-kernel-setup.md> — guides the `rootfs.md` content.
  - Reproducible Debian rootfs via `mmdebstrap`: <https://wiki.debian.org/Mmdebstrap> — pinned snapshot URL is what makes the rootfs digest stable.

## Goal

Make `tools/digests.yaml` the single source of truth for Firecracker artifact identity — committed pinned `vmlinux`+`rootfs.ext4`, digest-validating fence test, and an idempotent `codegenie sandbox prepare --backend firecracker` that rebuilds artifacts byte-identically from inputs.

## Acceptance criteria

- [ ] `tools/digests.yaml` carries real BLAKE3-256 hex digests under `sandbox.firecracker.{binary,binary_url}`, `sandbox.vmlinux.{digest,source_url}`, `sandbox.rootfs.{digest,build_recipe_path}`, replacing the S1-07 placeholders.
- [ ] `tools/firecracker/<rootfs_digest>/vmlinux` and `tools/firecracker/<rootfs_digest>/rootfs.ext4` exist (committed via git-LFS or bare commit per repo policy) and their BLAKE3 digests match `tools/digests.yaml#sandbox.{vmlinux.digest,rootfs.digest}`.
- [ ] `tests/schema/test_digests_yaml.py` upgrades from **presence-only** to **digest-validation**: it computes BLAKE3 of each pinned artifact and asserts equality against the yaml value; mismatch fails the test with a message that names the offending key and shows expected vs observed (first 8 hex chars).
- [ ] `FirecrackerClient.__init__` (or a factory `FirecrackerClient.from_digests_yaml(path)`) reads digest values from `tools/digests.yaml` instead of accepting them as constructor strings; existing constructor stays for tests but is `_internal`-tagged.
- [ ] `codegenie sandbox prepare --backend firecracker` is a Click subcommand at `src/codegenie/cli/sandbox.py` that: (a) reads inputs from `tools/firecracker/inputs.yaml` (snapshot URL pin, kernel config path, package list); (b) builds `rootfs.ext4` via `mmdebstrap` + `qemu-img`; (c) downloads kernel from the pinned URL; (d) computes BLAKE3 of both; (e) writes them to `tools/firecracker/<computed_rootfs_digest>/`; (f) if `--check` is passed, fails non-zero on digest mismatch instead of writing.
- [ ] `codegenie sandbox prepare --backend firecracker` is **idempotent**: running twice against unchanged inputs produces no filesystem changes the second time (`mtime` invariance not required; content invariance required and asserted by digest re-computation).
- [ ] `prepare` emits a structlog event `sandbox.prepare.start` and `sandbox.prepare.done` with `backend`, `rootfs_digest`, `vmlinux_digest`, and elapsed seconds.
- [ ] `prepare` surfaces clear errors for missing host tools: `mmdebstrap`, `qemu-img`, `tar`, `curl`. Each missing tool produces `PrepareToolMissing(tool="<name>", install_hint="<distro hint>")`.
- [ ] `firecracker/rootfs.md` lives at `src/codegenie/sandbox/firecracker/rootfs.md` and documents: (a) the snapshot-URL pin and why, (b) the deterministic bake procedure (`SOURCE_DATE_EPOCH=0`, fixed `mmdebstrap` package list, fixed timestamps for tar entries), (c) the verification recipe (`codegenie sandbox prepare --check`), (d) how to bump the pinned digest via PR.
- [ ] A "clean machine" sanity test (`tests/sandbox/firecracker/test_prepare_byte_identical.py`) runs `prepare` twice in a tmp dir against the same inputs and asserts both runs produce identical BLAKE3 digests — marked `pytest.mark.slow` and `pytest.mark.skipif("MMDEBSTRAP not on PATH")`.
- [ ] `tests/schema/test_digests_yaml.py` runs on every PR (still in the schema fence-test set); large artifact reads are streamed (BLAKE3 chunk-update) so the test runs in ≤ 5 s on the artifacts.
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` on touched modules, `pytest tests/schema/test_digests_yaml.py tests/sandbox/firecracker/test_prepare.py` all pass.

## Implementation outline

1. Replace `tools/digests.yaml` placeholders with the real digest schema:
   ```yaml
   sandbox:
     firecracker:
       binary: "<64-hex>"            # BLAKE3 of the firecracker binary
       binary_url: "https://github.com/firecracker-microvm/firecracker/releases/download/v1.7.0/firecracker-v1.7.0-x86_64.tgz"
     vmlinux:
       digest: "<64-hex>"
       source_url: "https://s3.amazonaws.com/spec.ccfc.min/img/quickstart_guide/x86_64/kernels/vmlinux.bin"
     rootfs:
       digest: "<64-hex>"
       build_recipe_path: "src/codegenie/sandbox/firecracker/rootfs.md"
     policy_yaml: "<64-hex>"          # already pinned by S3-05
   ```
2. Upgrade `tests/schema/test_digests_yaml.py`:
   - Load `tools/digests.yaml`.
   - For each `(key, file_path)` mapping (`sandbox.firecracker.binary` → `tools/firecracker/<rootfs_digest>/firecracker`, etc.), open in `rb`, `blake3.blake3()` streamed update, compare to the yaml value; collect mismatches and fail with all of them in the message.
3. Add `FirecrackerClient.from_digests_yaml(path: Path = Path("tools/digests.yaml")) -> FirecrackerClient` classmethod that parses the yaml and instantiates the client with the right digests + computed `tools/firecracker/<rootfs_digest>/` paths.
4. Create `src/codegenie/cli/sandbox.py` (or extend if S1-07 already created a stub) with:
   ```python
   @click.group()
   def sandbox(): ...
   @sandbox.command()
   @click.option("--backend", type=click.Choice(["firecracker"]), required=True)
   @click.option("--check", is_flag=True)
   def prepare(backend: str, check: bool) -> None: ...
   ```
   Move the heavy lifting into `src/codegenie/sandbox/firecracker/prepare.py` (`bake_rootfs(inputs)` + `verify_against_digests(digests_yaml, artifacts_dir)`).
5. Add `src/codegenie/sandbox/firecracker/rootfs.md` with the documented procedure and the reasoning behind every pin (snapshot URL, package list, timestamps).
6. Wire `prepare` to emit structlog events; raise `PrepareToolMissing` from `shutil.which(tool)` checks at the top of the command.
7. If artifacts must be checked into git via LFS, add the `.gitattributes` entry under `tools/firecracker/**/rootfs.ext4 filter=lfs diff=lfs merge=lfs -text` and `vmlinux filter=lfs ...`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/schema/test_digests_yaml.py` (upgrade) and `tests/sandbox/firecracker/test_prepare.py` (new).

```python
# tests/schema/test_digests_yaml.py
from __future__ import annotations

from pathlib import Path

import blake3
import yaml

DIGESTS_YAML = Path("tools/digests.yaml")


def _compute_blake3(path: Path) -> str:
    h = blake3.blake3()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def test_sandbox_firecracker_artifacts_match_pinned_digests() -> None:
    digests = yaml.safe_load(DIGESTS_YAML.read_text())
    rootfs_digest = digests["sandbox"]["rootfs"]["digest"]
    artifact_root = Path("tools/firecracker") / rootfs_digest

    expected = {
        artifact_root / "firecracker": digests["sandbox"]["firecracker"]["binary"],
        artifact_root / "vmlinux": digests["sandbox"]["vmlinux"]["digest"],
        artifact_root / "rootfs.ext4": digests["sandbox"]["rootfs"]["digest"],
    }
    mismatches = []
    for path, want in expected.items():
        assert path.exists(), f"pinned artifact missing: {path}"
        got = _compute_blake3(path)
        if got != want:
            mismatches.append(f"{path}: expected {want[:8]}..., got {got[:8]}...")
    assert not mismatches, "digest mismatches:\n" + "\n".join(mismatches)


def test_sandbox_policy_yaml_digest_still_present() -> None:
    # S3-05 contract; regression guard.
    digests = yaml.safe_load(DIGESTS_YAML.read_text())
    assert "policy_yaml" in digests["sandbox"]
    assert len(digests["sandbox"]["policy_yaml"]) == 64
```

```python
# tests/sandbox/firecracker/test_prepare.py
from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from codegenie.cli.sandbox import sandbox as sandbox_cli
from codegenie.sandbox.firecracker.prepare import PrepareToolMissing


def test_prepare_check_passes_when_digests_match(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(sandbox_cli, ["prepare", "--backend", "firecracker", "--check"])
    assert result.exit_code == 0, result.output


def test_prepare_raises_on_missing_host_tool() -> None:
    runner = CliRunner()
    with patch("shutil.which", return_value=None):
        result = runner.invoke(sandbox_cli, ["prepare", "--backend", "firecracker"])
    assert result.exit_code != 0
    assert "mmdebstrap" in result.output or "qemu-img" in result.output


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("mmdebstrap") is None,
                    reason="mmdebstrap not on PATH")
def test_prepare_is_byte_identical_across_two_runs(tmp_path: Path) -> None:
    from codegenie.sandbox.firecracker.prepare import bake_rootfs, _compute_blake3
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    bake_rootfs(out_dir=out_a)
    bake_rootfs(out_dir=out_b)
    assert _compute_blake3(out_a / "rootfs.ext4") == _compute_blake3(out_b / "rootfs.ext4")
```

Use `pytest.mark.skip_if_no_kvm` is not needed here; `prepare` is a host-side operation and runs on any Linux with `mmdebstrap`.

### Green — make it pass

Smallest implementation:
- `tools/digests.yaml` gets real digest values committed alongside the artifacts.
- `tests/schema/test_digests_yaml.py` streams BLAKE3 over each artifact.
- `prepare` command path-checks tools, invokes `bake_rootfs`, writes outputs to `tools/firecracker/<digest>/`, and supports `--check` returning non-zero on mismatch.

### Refactor — clean up

- Extract `_compute_blake3` into `src/codegenie/sandbox/firecracker/digests.py` so the test, `prepare`, and `FirecrackerClient.health()` share one implementation.
- Add per-key helpers (`load_pinned_digests() -> PinnedDigests` typed via Pydantic) so consumers do not duck-type the yaml shape.
- Keep `prepare`'s output deterministic — set `SOURCE_DATE_EPOCH=0`, `LC_ALL=C`, `TZ=UTC`, and fixed file ordering when building `rootfs.ext4`.
- Move the snapshot-URL pin to a top-of-file constant in `prepare.py` so a digest bump is one line + a regen.

## Files to touch

| Path | Why |
|---|---|
| `tools/digests.yaml` | Replace S1-07 placeholders with real digest values. |
| `tools/firecracker/<rootfs_digest>/vmlinux` | Committed (likely LFS) pinned kernel. |
| `tools/firecracker/<rootfs_digest>/rootfs.ext4` | Committed (likely LFS) pinned rootfs. |
| `tools/firecracker/inputs.yaml` | Bake inputs (snapshot URL, kernel URL, package list). |
| `.gitattributes` | LFS rules for the two large artifacts. |
| `tests/schema/test_digests_yaml.py` | Upgrade presence-only → digest-validation. |
| `src/codegenie/sandbox/firecracker/digests.py` | New — `load_pinned_digests`, `compute_blake3`. |
| `src/codegenie/sandbox/firecracker/prepare.py` | New — `bake_rootfs`, `verify_against_digests`, `PrepareToolMissing`. |
| `src/codegenie/sandbox/firecracker/rootfs.md` | New — documented bake procedure. |
| `src/codegenie/sandbox/firecracker/client.py` | Add `from_digests_yaml` classmethod; consume `digests.py`. |
| `src/codegenie/cli/sandbox.py` | Add `prepare` Click subcommand (full CLI in S8-01). |
| `tests/sandbox/firecracker/test_prepare.py` | New — Click-runner unit test, tool-missing, byte-identical. |

## Out of scope

- The other `codegenie sandbox` subcommands (`health`, `inspect`, `gc`) — S8-01.
- Auto-detect (`registry.auto_detect`) — S6-04.
- KVM-gated integration smoke + weekly cron — S6-05.
- Rebuild cadence policy (daily/weekly/per-bump) — operational, Phase 14 (Open Q1).
- Multi-architecture rootfs (arm64) — Phase 5 is x86_64 only.

## Notes for the implementer

- The `<rootfs_digest>/` directory naming is intentional: bumping the rootfs digest creates a *new* directory rather than mutating an existing one. Concurrent old/new versions on disk during a rolling bump are then safe.
- `mmdebstrap` is *not* `debootstrap` — the former is unprivileged and reproducible by design; do not substitute.
- BLAKE3 is the project's canonical hash (also used for the audit chain in S2-01). Do not use SHA-256 here — `tools/digests.yaml` is one consistent format.
- The fence-test upgrade is the single most load-bearing piece of this story: presence-only was a security stub, digest-validation is the real check. Treat any reviewer pushback on speed (streamed BLAKE3 is fast) as "make it faster," not "make it skip."
- The `--check` mode is what CI runs on every PR; the no-flag invocation is what an operator runs once to materialize artifacts. Keep them in the same subcommand to make the operator → CI parity obvious.
- Resist documenting "what" in `rootfs.md`; document *why every pin exists* — every reader will eventually want to bump one of them, and `why` is the only thing that survives.
- Do not embed any timestamps or hostnames in the rootfs build; `SOURCE_DATE_EPOCH=0` plus the `mmdebstrap` `--variant=minbase` plus deterministic-tar settings is what makes the digest stable across machines.
- LFS adds bandwidth cost on every clone — if the repo policy is "no LFS for now," fall back to a release-asset pull from the GitHub Release the snapshot was tagged from, and have `prepare` materialize the local path. Surface that decision in `rootfs.md`.
