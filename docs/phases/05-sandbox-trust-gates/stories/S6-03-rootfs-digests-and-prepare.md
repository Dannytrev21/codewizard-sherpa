# Story S6-03 — Pinned rootfs + `vmlinux` digest enforcement + `sandbox prepare`

**Step:** Step 6 — FirecrackerClient backend + KVM-gated CI smoke test
**Status:** Ready (HARDENED 2026-05-25)
**Effort:** L (was M; widened by kernel-extract + factory rework + fence widenings)
**Depends on:** S1-01 HARDENED (errors + logging + warning-ID regex + `STARTED/COMPLETED/FAILED` verb canonical-table), S1-02 HARDENED (`SandboxBackendError` + `extra="forbid"` + frozen Pydantic), S1-06 HARDENED (`ALLOWED_BINARIES` this story widens by 4), S1-07 HARDENED (`tools/digests.yaml` scalar-string shape this story preserves + `_SUBPROCESS_ALLOWLIST` this story widens by 1 + fence-test framework this story upgrades from presence-only to byte-validation), S3-01 HARDENED (closed-Literal `reason` discriminator pattern), S3-02 HARDENED (Hexagonal DI port pattern), S3-03 HARDENED (FCS pure-helper + impure-shell split pattern), S6-01 HARDENED (FirecrackerClient surface this story EDITs — replaces string-arg ctor with `from_pinned_digests` factory; widens `reason` Literal by 8; `_BACKEND_NAME` Final convention), S6-02 HARDENED (closed-Literal `reason` cumulative-additive widening; subprocess-fence consume-not-widen discipline)
**ADRs honored:** ADR-0013 (digest-pinned codegenie-owned artifact — this story is the third concrete consumer), ADR-0004 (DinD-default-macOS — `prepare` Linux-only; macOS contributors download release-asset materializations), ADR-0001 (two-chokepoint subprocess discipline — `prepare.py` is the fifth chokepoint), production ADR-0019 (sandbox stack evidence)

## Validation notes (2026-05-25 — phase-story-validator v1, automated)

This story underwent the four-critic validation and was HARDENED from 11 unnumbered checkboxes to ~70 numbered ACs across 16 sections. Thirteen block-tier and thirteen harden/nit-tier weaknesses were resolved. Full report at [`_validation/S6-03-rootfs-digests-and-prepare.md`](_validation/S6-03-rootfs-digests-and-prepare.md). Headlines:

- **YAML-shape contradiction with S1-07.** Draft introduced nested objects (`sandbox.firecracker.binary`) which break S1-07 HARDENED AC-DG-2 / AC-DG-5/6 (`tools/digests.yaml#sandbox.*` is closed-set, scalar-string-only). Resolved by keeping the scalar-string shape and moving URL / build-recipe metadata to a new `tools/firecracker/sources.yaml` (Pydantic `BakeInputs` typed).
- **Fifth consumer of FCS + Hexagonal-DI + closed-Literal-`reason` + `_BACKEND_NAME`-`Final` + module-purity-AST-walker stack** (rule-of-three crossed three times over via S3-01/S3-02/S3-03/S6-01/S6-02). Mandatory pattern inheritance — `runner` / `downloader` / `fs` / `clock` DI ports; pure-helper extraction; new `Prepare*Error(SandboxBackendError)` subclasses; closed-Literal `reason` widened additively by 8 members.
- **Third consumer of ADR-0013's digest-pinning family.** Rule-of-three reached. Kernel-extract is mandatory: `src/codegenie/digests/` (new package) hosts `compute_blake3_streamed`, `diff_digests`, `_DIGEST_HEX_RE`. The per-artifact verifier stays inline; the registry-decorator (`register_digest_pinned_artifact(...)`) is deferred until Phase 7+ when a fifth distinct artifact (e.g., Chainguard image digest) enters the closed-keys set.
- **`--check` mode split.** Draft ambiguity (disk-read vs re-bake) resolved into two flags: `--check` (default — read-from-disk verify; ≤ 5 s; PR-time fence) vs `--check-rebake` (re-bake to tmpdir + compare; ≤ 6 min; operator-bump verification only).
- **`from_digests_yaml` classmethod removed.** Replaced by `load_pinned_digests(*, digests_yaml: Path) -> PinnedDigests` (pure-of-fs read returning frozen Pydantic) + `FirecrackerClient.from_pinned_digests(digests, *, artifacts_root, api_socket_factory=..., process_handle_factory=..., vsock_exec_port=..., clock=...)` factory that forwards every S6-01 HARDENED DI port. The string-arg constructor is **removed** (not `_internal`-tagged — actually removed).
- **Event names** `sandbox.prepare.start` / `done` → `sandbox.prepare.started` / `.completed` / `.failed` (S1-01 verb canonical-table inheritance).
- **Fence widenings:** `_SUBPROCESS_ALLOWLIST` 4 → 5; `ALLOWED_BINARIES` += `{mmdebstrap, qemu-img, tar, curl}`.
- **Determinism three-layer test pyramid:** golden argv (always run) → `RunnerSpy` argv-equality across two `bake_rootfs` calls (always run) → real `mmdebstrap` skip-gated test (CI-only). The first two prove the logic; the third proves the world.
- **Materialization:** LFS deferred (Phase-5 non-goal); artifacts download from a pinned GitHub Release URL when absent. `.gitignore` blocks accidental commits of `tools/firecracker/[0-9a-f]*/`.

## Context

`FirecrackerClient` (S6-01) compares the on-disk `firecracker`, `vmlinux`, and `rootfs.ext4` against constructor-supplied digests, but nothing yet *enforces* those digests against `tools/digests.yaml`. S1-07 HARDENED pinned the four `sandbox.*` placeholder keys (`firecracker`, `vmlinux`, `rootfs`, `policy_yaml`) as scalar-string slots whose value is `"TBD"` (placeholder) or a 64-char hex digest — but did NOT verify that those digests match the on-disk bytes. Without that verification, an operator can silently swap the rootfs and the static CI fence test does not notice — it only checks key presence + value regex shape.

This story is the **third concrete consumer of ADR-0013** (codegenie-owned digest-pinned artifact) — the rule-of-three has landed. It upgrades the fence test to byte-level digest validation, replaces S1-07 `"TBD"` placeholders with real 64-char hex digests, ships the documented bake procedure in `firecracker/rootfs.md`, and adds the `codegenie sandbox prepare --backend firecracker` subcommand so a clean machine can rebuild artifacts idempotently from inputs. The shared `compute_blake3_streamed` + `diff_digests` kernel is extracted to a new `src/codegenie/digests/` package consumed both by this story's fence test and by `FirecrackerClient.health()` (S6-01 EDIT).

Pattern-lineage-wise, this story is also the **fifth concrete consumer** of the FCS + Hexagonal-DI-port + closed-Literal-`reason` + `_BACKEND_NAME`-`Final` + module-purity-AST-walker pattern stack (S3-01/S3-02/S3-03/S6-01/S6-02). From S6-01 HARDENED forward these patterns are **mandatory AC-tier inheritance**.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — FirecrackerClient` (lines 495–502) — `tools/firecracker/<rootfs_digest>/vmlinux + rootfs.ext4` layout; `prepare` subcommand contract; `FirecrackerBinaryMissing` / `FirecrackerRootfsMissing` failure modes.
  - `../phase-arch-design.md §Development view` (line 306) — `tools/digests.yaml` keys (`sandbox.firecracker`, `sandbox.vmlinux`, `sandbox.rootfs`, `sandbox.policy_yaml`); `tests/schema/test_digests_yaml.py` (line 912).
  - `../phase-arch-design.md §Component design — CLI surface` (lines 613–625) — `codegenie sandbox prepare [--backend firecracker]` is "pre-bake Firecracker rootfs (preflight, idempotent)"; performance envelope `≤ 5 min`.
  - `../phase-arch-design.md §Open Q1` (line 1056) — rootfs build cadence is a Phase 14 operational decision; `prepare` must be idempotent so cadence is policy, not mechanism.
  - `../phase-arch-design.md §Edge cases §6` — firecracker binary digest mismatch is non-retryable; surfaces as `FirecrackerBinaryMissing`.
- **Phase ADRs:**
  - `../ADRs/0013-digest-pinned-policy-yaml-codegenie-owned.md` — codegenie-owned + digest-pinned + CI-asserted-at-startup; this story is the third concrete consumer.
  - `../ADRs/0004-dind-default-macos-with-gate-isolation-class.md` — `tools/digests.yaml#sandbox.{firecracker,vmlinux,rootfs}` carries the actual binary + rootfs digests.
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — `prepare` CLI is operator surface; subprocess for `qemu-img`/`tar`/`mmdebstrap`/`curl` lives in the `prepare` code path, not the runtime client.
- **Production ADRs:**
  - `../../../production/adrs/0019-sandbox-stack.md` — pinned rootfs is an explicit input to the eventual stack-resolution evidence.
  - `../../../production/adrs/0021-policy-engine-build-vs-adopt.md` — the digest-pinning archetype.
- **Source design:**
  - `../final-design.md §Synthesis ledger row "tools/digests.yaml"` — digest pinning rationale.
- **Prior HARDENED validation reports:**
  - `_validation/S1-07-ci-fence-tests-digests-yaml.md` — `_SUBPROCESS_ALLOWLIST` 4-file frozenset + `_DIGEST_HEX_RE` + scalar-string shape contract (AC-DG-1..AC-DG-6).
  - `_validation/S6-01-firecracker-client-kvm-boot.md` — `from_pinned_digests` factory blueprint + DI-port forwarding (AC-DI-1..AC-DI-3) + `_BACKEND_NAME` Final + closed-Literal `reason` discipline (AC-ERR-1..AC-ERR-2).
  - `_validation/S6-02-firecracker-nftables-policy-gap-4.md` — cumulative `reason` widening discipline + module-purity AST walker template (AC-PURE-1..AC-PURE-8) + subprocess-fence consume-not-widen pattern.
- **Existing code (post-S6-01 HARDENED):**
  - `src/codegenie/sandbox/firecracker/client.py` — replace the string-arg ctor with `from_pinned_digests` factory; consume `digests/` kernel; widen `reason` Literal by 8 in `errors.py`.
  - `src/codegenie/sandbox/errors.py` — add 5 `Prepare*Error(SandboxBackendError)` subclasses with narrowed closed-Literal `reason`.
  - `src/codegenie/sandbox/logging.py` — three new event constants alphabetized into sorted `__all__`.
  - `src/codegenie/exec/__init__.py` — widen `ALLOWED_BINARIES` by 4.
  - `tools/digests.yaml` — replace `"TBD"` with real 64-char hex; KEEP the S1-07 scalar-string shape (do NOT introduce nested objects).
  - `tests/schema/test_digests_yaml.py` — upgrade from presence-only (S1-07 AC-DG-*) to byte-level digest validation; planted-positive flips a digest byte.
  - `tests/schema/test_no_subprocess_outside_build_chokepoint.py` — `_SUBPROCESS_ALLOWLIST` 4 → 5.
- **External docs:**
  - Firecracker kernel-rebuild recipe: <https://github.com/firecracker-microvm/firecracker/blob/main/docs/rootfs-and-kernel-setup.md>
  - Reproducible Debian rootfs via `mmdebstrap`: <https://wiki.debian.org/Mmdebstrap>
  - PAX-format tar reproducibility: <https://reproducible-builds.org/docs/archives/>
- **CLAUDE.md anchors:**
  - "Warning + error IDs match `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`" — namespace regex compliance for all warning IDs in this story (AC-WID-1..AC-WID-4).
  - "Functional core / imperative shell" — `_compute_blake3_streamed` / `_canonical_*_argv` are pure; `bake_rootfs` / `verify_against_digests` are the impure shell.
  - "Newtype identifiers" — `PinnedDigests` is a frozen Pydantic model with per-field validators (not raw `str`).
  - "Extension by addition" — `tools/digests.yaml` widening (placeholder → real value) is in-place edit of an existing closed-keys set, not a schema change. The new `tools/firecracker/sources.yaml` is a brand-new file. Kernel extract is by addition (new `digests/` package).
  - "Open/Closed Principle" — `register_digest_pinned_artifact(...)` registry deferred (consumer set is closed at 4; widening to 5 is the rule-of-three threshold).

## Goal

Make `tools/digests.yaml` the **single source of truth** for Firecracker artifact identity — preserving S1-07's scalar-string shape, replacing `"TBD"` placeholders with real BLAKE3-256 hex digests, upgrading the fence test to **byte-level** digest validation, removing the string-arg `FirecrackerClient` constructor (which silently allowed digest values that disagreed with `tools/digests.yaml`), and shipping an idempotent `codegenie sandbox prepare --backend firecracker` that:
- (default) reads + verifies on-disk artifact bytes against pinned digests in ≤ 5 s (`--check` semantic);
- (operator-bump) re-bakes artifacts byte-identically from inputs in ≤ 6 min (`--check-rebake` semantic);
- (clean-machine) downloads artifacts from a pinned GitHub Release URL when absent (`--download-only` semantic) — LFS is a non-goal for Phase 5.

The shared digest-loading kernel (`src/codegenie/digests/`) is extracted as the third consumer of [ADR-0013](../../ADRs/0013-digest-pinned-policy-yaml-codegenie-owned.md). The string-arg `FirecrackerClient.__init__` is removed (not `_internal`-tagged); construction routes via `FirecrackerClient.from_pinned_digests(digests, *, artifacts_root, ...)` forwarding every S6-01 HARDENED DI port.

## Acceptance criteria

### §A — Public surface + module discipline

- [ ] **AC-MOD-1** `src/codegenie/digests/__init__.py` (new package) — module docstring cites ADR-0013 + ADR-0021 + S1-07 HARDENED + this story; `from __future__ import annotations` first; sorted `__all__` containing exactly `("compute_blake3_streamed", "diff_digests", "PinnedArtifact", "DigestMismatch", "_DIGEST_HEX_RE")`.
- [ ] **AC-MOD-2** `src/codegenie/sandbox/firecracker/prepare.py` (new) — module docstring cites ADR-0001 + ADR-0013 + S1-07 + this story; `from __future__ import annotations` first; sorted `__all__` containing exactly `("bake_rootfs", "verify_against_digests", "download_artifacts", "BakeInputs", "BakeArtifacts", "VerifyOutcome", "Match", "Mismatch")`.
- [ ] **AC-MOD-3** `src/codegenie/_paths.py` (new) — `find_project_root() -> Path` hoisted from `tests/schema/_walkers.py::ROOT` derivation (or, if `_paths.py` exists, extended); module docstring + sorted `__all__`.
- [ ] **AC-CANONICAL-1** `_BACKEND_NAME: Final[str] = "firecracker"` declared at module top of `prepare.py`.
- [ ] **AC-CANONICAL-2** Module-purity AST walker asserts the literal `"firecracker"` does NOT appear in `prepare.py` body outside the `_BACKEND_NAME` declaration; event payloads / error messages reference `_BACKEND_NAME`.
- [ ] **AC-CANONICAL-3** `_DEFAULT_DIGESTS_YAML_RELATIVE: Final[Path] = Path("tools/digests.yaml")` at module top of `digests.py`.
- [ ] **AC-CANONICAL-4** `_DEFAULT_ARTIFACTS_ROOT_RELATIVE: Final[Path] = Path("tools/firecracker")` at module top of `prepare.py`.

### §B — `tools/digests.yaml` shape preservation + new `tools/firecracker/sources.yaml`

- [ ] **AC-YAML-SHAPE-1** `tools/digests.yaml` **preserves** the S1-07 HARDENED shape (AC-DG-2..AC-DG-6): top-level `sandbox:` mapping with exactly four scalar-string keys (`firecracker`, `vmlinux`, `rootfs`, `policy_yaml`). NO nested objects under any of the four keys.
- [ ] **AC-YAML-SHAPE-2** Each of the four values is replaced from `"TBD"` to a real 64-char lowercase hex BLAKE3-256 digest matching `_DIGEST_HEX_RE` (S1-07 contract).
- [ ] **AC-YAML-SHAPE-3** `tests/schema/test_digests_yaml.py` (UPGRADE) — for each of the four keys, computes BLAKE3 of the on-disk artifact (via the new `compute_blake3_streamed` kernel) and asserts equality. Mismatch fails with a message naming the offending key, the expected first 8 hex chars, and the observed first 8 hex chars; all mismatches collected and reported together (no early return on first mismatch).
- [ ] **AC-YAML-SHAPE-4** S1-07's existing presence + shape contract (AC-DG-1..AC-DG-6) stays green after this story; this story is monotone-additive on top of S1-07.
- [ ] **AC-YAML-SHAPE-5** `tools/firecracker/sources.yaml` (new file) carries operator-facing bake metadata (URLs, package list, snapshot pin). NOT in `tools/digests.yaml`. Per `BakeInputs` Pydantic shape (AC-INPUTS-1..AC-INPUTS-4).
- [ ] **AC-INPUTS-1** `BakeInputs` is a frozen Pydantic model (`frozen=True, slots=True, extra="forbid"`) with fields: `snapshot_url: HttpUrl`, `kernel_url: HttpUrl`, `kernel_blake3: str` (64-hex), `package_list: tuple[str, ...]` (alphabetized, deduplicated, validated against Debian package-name regex `^[a-z0-9][a-z0-9+\-.]+$`), `mmdebstrap_variant: Literal["minbase", "essential", "important", "standard"] = "minbase"`, `source_date_epoch: int = 0`, `release_artifact_url: HttpUrl | None = None`.
- [ ] **AC-INPUTS-2** `_parse_inputs_yaml(raw: bytes) -> BakeInputs` and `_render_inputs_yaml(inputs: BakeInputs) -> str` are pure helpers; hypothesis property test asserts `_parse_inputs_yaml(_render_inputs_yaml(x).encode()) == x` for arbitrary `BakeInputs` (canonical YAML round-trip).
- [ ] **AC-INPUTS-3** `BakeInputs.package_list` rejects duplicates at validator time; rejects entries violating the Debian package-name regex; rejects entries containing path separators or whitespace.
- [ ] **AC-INPUTS-4** `tools/firecracker/sources.yaml` is committed with the real bake inputs that produce the digests in `tools/digests.yaml`; a fence-style test asserts `BakeInputs.from_yaml(...)` parses cleanly with no validation errors.

### §C — `PinnedDigests` / `BakeArtifacts` / `VerifyOutcome` models

- [ ] **AC-MODEL-1** `PinnedDigests` is a frozen Pydantic model (`frozen=True, slots=True, extra="forbid"`) with fields `firecracker_binary: str`, `vmlinux: str`, `rootfs: str`, `policy_yaml: str`; per-field validator enforces 64-char lowercase hex via `_DIGEST_HEX_RE`.
- [ ] **AC-MODEL-2** `BakeArtifacts` is a frozen Pydantic model with `rootfs_digest: str`, `vmlinux_digest: str`, `firecracker_binary_digest: str`, `paths: ArtifactPaths`.
- [ ] **AC-MODEL-3** `VerifyOutcome` is a tagged union (`Match | Mismatch(differences: tuple[DigestMismatch, ...])`) — discriminated by literal `kind: Literal["match", "mismatch"]`. `DigestMismatch` carries `key: Literal["firecracker", "vmlinux", "rootfs", "policy_yaml"]`, `expected: str`, `observed: str`, `path: Path`. Illegal states (e.g., `Match` with non-empty differences) unrepresentable.

### §D — Hexagonal DI ports

- [ ] **AC-DI-1** `bake_rootfs(*, inputs: BakeInputs, out_dir: Path, runner: Callable[..., subprocess.CompletedProcess[bytes]] = _default_runner, downloader: Callable[[HttpUrl, Path], None] = _default_downloader, fs: FsPort = _default_fs, clock: Callable[[], datetime] = _default_clock) -> BakeArtifacts` — every external effect goes through an injected port.
- [ ] **AC-DI-2** `verify_against_digests(*, digests: PinnedDigests, artifacts_dir: Path, hasher: Callable[[Path], str] = _default_hasher, fs: FsPort = _default_fs) -> VerifyOutcome` — pure-ish; only fs reads + hash computation.
- [ ] **AC-DI-3** `download_artifacts(*, release_url: HttpUrl, out_dir: Path, downloader=..., fs=...) -> BakeArtifacts` — for the `--download-only` path.
- [ ] **AC-DI-4** `_default_runner` is the **only** function in `prepare.py` whose body contains a `subprocess.run` call; AST walker (AC-PURE-3) asserts this.
- [ ] **AC-DI-5** `_default_downloader` is the **only** function in `prepare.py` whose body contains `urllib.request.urlopen` (or equivalent network call); AST walker asserts this.
- [ ] **AC-DI-6** Tests inject `RunnerSpy`, `DownloaderSpy`, `FsSpy`, frozen `clock` directly via the DI seams; no `unittest.mock.patch("subprocess.run")`, no `unittest.mock.patch("shutil.which")`, no `unittest.mock.patch("urllib.request.urlopen")`. AST walker on test files asserts these patches are absent.

### §E — Functional core / imperative shell

- [ ] **AC-FCS-1** `_compute_blake3_streamed(reader: Callable[[int], bytes], *, chunk_size: int = 1 << 20) -> str` — pure: chunked-update over the reader callable; no fs I/O of its own. Hosted in `src/codegenie/digests/__init__.py` as `compute_blake3_streamed` (public).
- [ ] **AC-FCS-2** `_artifact_paths_for(rootfs_digest: str, root: Path) -> ArtifactPaths` — pure path arithmetic; returns `ArtifactPaths(rootfs=..., vmlinux=..., firecracker=...)`.
- [ ] **AC-FCS-3** `_required_tools() -> tuple[str, ...]` — returns `("mmdebstrap", "qemu-img", "tar", "curl")`; pure.
- [ ] **AC-FCS-4** `_diff_digests(want: PinnedDigests, got: PinnedDigests) -> tuple[DigestMismatch, ...]` — pure; returns tagged-union mismatch records.
- [ ] **AC-FCS-5** `_canonical_tar_argv(src: Path, dst: Path, *, source_date_epoch: int = 0) -> tuple[str, ...]` — pure; emits the exact reproducible-tar flag set per AC-DETERMINISM-5.
- [ ] **AC-FCS-6** `_canonical_mmdebstrap_argv(inputs: BakeInputs, *, out: Path) -> tuple[str, ...]` — pure; emits the exact `mmdebstrap` argv tuple per AC-DETERMINISM-5.
- [ ] **AC-FCS-7** `_parse_inputs_yaml(raw: bytes) -> BakeInputs` / `_render_inputs_yaml(inputs: BakeInputs) -> str` — pure (per AC-INPUTS-2).
- [ ] **AC-FCS-8** `_wrap_subprocess_error(err: subprocess.CalledProcessError | FileNotFoundError | TimeoutExpired, *, reason: Literal[...]) -> SandboxBackendError` — pure adapter; never side-effects.
- [ ] **AC-FCS-9** **Impure shells** are exactly: `bake_rootfs`, `verify_against_digests`, `download_artifacts`, `compute_artifact_digests`, `write_artifacts`. AST walker asserts every other top-level function in `prepare.py` is pure (no `subprocess`, no `urllib`, no `pathlib.Path.write_*` / `Path.read_*`).

### §F — `bake_rootfs` lifecycle

- [ ] **AC-BAKE-1** Order of operations (the impure shell): (a) check all `_required_tools()` present via `shutil.which`; missing → `PrepareToolMissing(tool=..., install_hint=..., reason="sandbox.prepare.tool_missing")` BEFORE any subprocess call; (b) download kernel via `downloader(inputs.kernel_url, tmp/vmlinux)`; (c) verify kernel BLAKE3 == `inputs.kernel_blake3` → `PrepareDigestMismatch(reason="sandbox.prepare.kernel_digest_mismatch", expected=..., observed=...)` on miss; (d) bake rootfs via `runner(_canonical_mmdebstrap_argv(inputs, out=tmp/rootfs.ext4), env={"LC_ALL": "C", "TZ": "UTC", "SOURCE_DATE_EPOCH": str(inputs.source_date_epoch)})`; (e) compute BLAKE3 of `tmp/rootfs.ext4` → `rootfs_digest`; (f) `fs.atomic_rename(tmp/, out_dir/<rootfs_digest>/)`; (g) emit `EVENT_SANDBOX_PREPARE_COMPLETED`.
- [ ] **AC-BAKE-2** On any failure in steps (a)–(f), the partial `tmp/` directory is removed BEFORE the error propagates; `_wrap_subprocess_error` adapts the underlying exception. AST walker asserts every step inside `bake_rootfs` is wrapped in try/finally for the tmp cleanup.
- [ ] **AC-BAKE-3** Step (f) atomicity: `fs.atomic_rename` uses `os.replace` (atomic on POSIX); if `<rootfs_digest>/` already exists with matching contents (idempotent re-run), the bake is short-circuited at step (e) — see AC-IDEMPOTENT-1.
- [ ] **AC-BAKE-4** Step (d) timeout: `runner(..., timeout=_BAKE_TIMEOUT_SECONDS)` where `_BAKE_TIMEOUT_SECONDS: Final[int] = 360` (matches AC-PERF-1); `TimeoutExpired` → `PrepareBakeFailed(reason="sandbox.prepare.rootfs_bake_failed", install_hint="bake exceeded 360 s; check mmdebstrap snapshot URL")`.

### §G — `verify_against_digests`

- [ ] **AC-VERIFY-1** Reads `digests.firecracker_binary` / `.vmlinux` / `.rootfs` from the passed `PinnedDigests`; computes BLAKE3 of each on-disk artifact via `compute_blake3_streamed`; returns `Match()` on full equality, `Mismatch(differences=...)` otherwise.
- [ ] **AC-VERIFY-2** Missing artifact path → returns `Mismatch` with `DigestMismatch(observed="<missing>", ...)` for that key; does NOT raise. The caller (`prepare --check`) translates `Mismatch` → CLI exit code 1.
- [ ] **AC-VERIFY-3** ≤ 5 s on the canonical artifact set on the reference Linux CI runner — asserted by `tests/perf/test_prepare_check_latency.py` (AC-PERF-2).

### §H — CLI flags + project-root resolution

- [ ] **AC-CHECK-MODE-1** `prepare` (no flag) writes/refreshes artifacts under `<artifacts_root>/<rootfs_digest>/`; idempotent on identical digests (per AC-IDEMPOTENT-1).
- [ ] **AC-CHECK-MODE-2** `prepare --check` reads on-disk artifacts and verifies against `tools/digests.yaml`; exit 0 on `Match`, exit 1 on `Mismatch`, exit 2 on artifacts-absent (`PrepareCheckFailed(reason="sandbox.prepare.check_failed", install_hint="run codegenie sandbox prepare --backend firecracker first")`). ≤ 5 s budget.
- [ ] **AC-CHECK-MODE-3** `prepare --check-rebake` re-bakes into a tmp dir, computes digests, compares to `tools/digests.yaml`; exit 0 on `Match`, exit 1 on `Mismatch` (with operator-actionable diff including expected vs observed first 8 hex). ≤ 6 min budget. Does NOT touch `<artifacts_root>/`.
- [ ] **AC-CHECK-MODE-4** `prepare --download-only` fetches release-asset materializations from `BakeInputs.release_artifact_url` (if set; else exit 3 + `PrepareKernelDownloadFailed`) without baking. ≤ 60 s budget on broadband.
- [ ] **AC-PATH-1** `find_project_root()` lives in `src/codegenie/_paths.py`; walks up from `Path.cwd()` looking for `pyproject.toml`; raises `ProjectRootNotFound` (a `RuntimeError` subclass) if none found.
- [ ] **AC-PATH-2** `prepare --digests-yaml PATH` flag overrides the default `find_project_root() / "tools/digests.yaml"`; the fence test `tests/schema/test_digests_yaml.py` uses the same resolver.
- [ ] **AC-PATH-3** `prepare --artifacts-root PATH` flag overrides the default `find_project_root() / "tools/firecracker"`; defaults are resolved at click-callback time (not at module import).

### §I — Errors + closed-Literal `reason`

- [ ] **AC-ERR-1** `SandboxBackendError.reason: Literal[...]` widens additively by **eight** members (cumulative from S6-02's 27 → 35 total): `"sandbox.prepare.tool_missing"`, `"sandbox.prepare.inputs_yaml_invalid"`, `"sandbox.prepare.kernel_download_failed"`, `"sandbox.prepare.kernel_digest_mismatch"`, `"sandbox.prepare.rootfs_bake_failed"`, `"sandbox.prepare.rootfs_digest_mismatch"`, `"sandbox.prepare.artifact_write_failed"`, `"sandbox.prepare.check_failed"`.
- [ ] **AC-ERR-2** Five `Prepare*Error(SandboxBackendError)` subclasses each narrow `reason` to its relevant subset via `reason: Literal[...]`:
   - `PrepareToolMissing` → `"sandbox.prepare.tool_missing"`
   - `PrepareKernelDownloadFailed` → `"sandbox.prepare.kernel_download_failed"`
   - `PrepareDigestMismatch` → `"sandbox.prepare.kernel_digest_mismatch" | "sandbox.prepare.rootfs_digest_mismatch"`
   - `PrepareBakeFailed` → `"sandbox.prepare.rootfs_bake_failed" | "sandbox.prepare.artifact_write_failed"`
   - `PrepareCheckFailed` → `"sandbox.prepare.check_failed"`
- [ ] **AC-ERR-3** `typing.get_args(SandboxBackendError.__fields__["reason"].annotation)` is asserted byte-exactly against the cumulative 35-member set in `tests/sandbox/test_errors_reason_cumulative.py`; planted-positive removes one member and asserts the test fires.
- [ ] **AC-ERR-4** Each `Prepare*Error` carries (only when relevant): `tool: str | None`, `install_hint: str | None`, `expected_digest: str | None` (first 8 hex), `observed_digest: str | None` (first 8 hex), `path: Path | None`.
- [ ] **AC-ERR-5** `_wrap_subprocess_error(err, *, reason)` adapter — unifies `subprocess.CalledProcessError`, `FileNotFoundError`, `TimeoutExpired` into the relevant `Prepare*Error` with `install_hint` populated from a `_INSTALL_HINTS: Final[Mapping[str, str]]` table.
- [ ] **AC-ERR-6** Module-level `_WARNING_IDS: Final[frozenset[str]] = frozenset({...})` validated at import time via `if not all(_WARNING_ID_RE.fullmatch(w) for w in _WARNING_IDS): raise AssertionError(...)` (bare `assert` forbidden per CLAUDE.md `forbidden-patterns`).

### §J — Events

- [ ] **AC-EVT-1** `src/codegenie/sandbox/logging.py` (EDIT) gains three `Final[str]` constants alphabetized into the sorted `__all__`:
   - `EVENT_SANDBOX_PREPARE_COMPLETED = "sandbox.prepare.completed"`
   - `EVENT_SANDBOX_PREPARE_FAILED = "sandbox.prepare.failed"`
   - `EVENT_SANDBOX_PREPARE_STARTED = "sandbox.prepare.started"`
- [ ] **AC-EVT-2** `prepare` emits `EVENT_SANDBOX_PREPARE_STARTED` once at command entry, `EVENT_SANDBOX_PREPARE_COMPLETED` at clean exit, `EVENT_SANDBOX_PREPARE_FAILED` at any error exit. Payload schema: `backend: str`, `mode: Literal["bake", "check", "check-rebake", "download-only"]`, `rootfs_digest: str | None`, `vmlinux_digest: str | None`, `firecracker_binary_digest: str | None`, `elapsed_seconds: float`, and on FAILED: `reason: Literal[...]` + `error_class: str`.
- [ ] **AC-EVT-3** Test uses `structlog.testing.capture_logs()` (project-standard idiom); asserts byte-stable event names and exhaustive payload field set across all four modes.

### §K — Idempotency

- [ ] **AC-IDEMPOTENT-1** Second `prepare` invocation (no flag) when `<artifacts_root>/<rootfs_digest>/{vmlinux,rootfs.ext4,firecracker}` are all present AND their BLAKE3 matches `tools/digests.yaml`: zero `runner` calls, zero `downloader` calls, `RunnerSpy.calls == ()`, `DownloaderSpy.calls == ()`. Emits `EVENT_SANDBOX_PREPARE_COMPLETED` with `mode="bake"` and a payload field `short_circuited: bool = True`.
- [ ] **AC-IDEMPOTENT-2** Content invariance asserted via re-computing BLAKE3 after the second run; mtime invariance NOT required.
- [ ] **AC-IDEMPOTENT-3** A third `prepare --check` immediately after the second bake completes in ≤ 5 s on the reference runner; exit 0.

### §L — Determinism

- [ ] **AC-DETERMINISM-1** Three-layer test pyramid:
   - **Layer 1 (always runs):** Pure-helper golden-fixture tests pin the exact argv tuples emitted by `_canonical_tar_argv` and `_canonical_mmdebstrap_argv` for canonical fixture inputs.
   - **Layer 2 (always runs):** `RunnerSpy` integration test — `bake_rootfs(..., runner=spy_a)` and `bake_rootfs(..., runner=spy_b)` against identical `BakeInputs` are byte-identical in `spy.recorded_argv_tuples`.
   - **Layer 3 (CI-only):** real `mmdebstrap` test marked `pytest.mark.slow + skipif(not _has_mmdebstrap())` — runs `bake_rootfs` twice into distinct tmpdirs, asserts identical BLAKE3 of both `rootfs.ext4` outputs.
- [ ] **AC-DETERMINISM-2** Layer 1 + Layer 2 are part of the regular `pytest -q` set; flake rate ≤ 0.1%.
- [ ] **AC-DETERMINISM-3** Layer 3 is gated to one self-hosted CI runner with `mmdebstrap` installed; failure pages the runner owner.
- [ ] **AC-DETERMINISM-4** No file-system state is required for Layer 1 or Layer 2.
- [ ] **AC-DETERMINISM-5** `_canonical_tar_argv` emits (exact ordering, no flag drift): `("tar", "--sort=name", f"--mtime=@{source_date_epoch}", "--owner=0", "--group=0", "--numeric-owner", "--pax-option=delete=atime,delete=ctime,exthdr.name=%d/PaxHeaders/%f", "-cf", str(dst), "-C", str(src), ".")`. `_canonical_mmdebstrap_argv` emits: `("mmdebstrap", "--mode=fakechroot", f"--variant={inputs.mmdebstrap_variant}", "--aptopt=Acquire::Check-Valid-Until \"false\"", "--aptopt=APT::Get::Assume-Yes \"true\"", "--include=" + ",".join(inputs.package_list), inputs.snapshot_url, str(out))`.

### §M — Materialization (LFS vs release-asset)

- [ ] **AC-MATERIALIZE-1** Artifacts are NOT committed to git (no `.gitattributes` LFS rule; explicit Phase-5 non-goal). `.gitignore` adds `/tools/firecracker/[0-9a-f]*/` so accidental commits are blocked.
- [ ] **AC-MATERIALIZE-2** `prepare --download-only` materializes artifacts from `BakeInputs.release_artifact_url` (a tarball of the canonical `<rootfs_digest>/` directory hosted on a pinned GitHub Release).
- [ ] **AC-MATERIALIZE-3** CI workflow YAML carries one `codegenie sandbox prepare --backend firecracker --download-only` step BEFORE `tests/schema/test_digests_yaml.py` runs.

### §N — Fence widenings + module purity

- [ ] **AC-FENCE-1** S1-07's `_SUBPROCESS_ALLOWLIST` (in `tests/schema/test_no_subprocess_outside_build_chokepoint.py`) widens additively by exactly one entry: `Path("src/codegenie/sandbox/firecracker/prepare.py")`. The frozenset is now 5 members.
- [ ] **AC-FENCE-2** `prepare.py` module docstring cites the widening: `# Fifth subprocess chokepoint per ADR-0001 + ADR-0013 + S6-03 HARDENED`.
- [ ] **AC-FENCE-3** Planted-positive test removes the new entry, asserts the live test fires offenders == `{Path("src/codegenie/sandbox/firecracker/prepare.py")}`.
- [ ] **AC-BINARIES-1** `codegenie.exec.ALLOWED_BINARIES` widens additively by exactly four entries: `"mmdebstrap"`, `"qemu-img"`, `"tar"`, `"curl"`.
- [ ] **AC-BINARIES-2** Unit test asserts the four are present in `ALLOWED_BINARIES`.
- [ ] **AC-BINARIES-3** Planted-positive removes one entry and asserts `BinaryNotAllowed` raises when `prepare` is invoked.
- [ ] **AC-BINARIES-4** ADR-0013 cross-reference appears in the `ALLOWED_BINARIES` widening commit message and in the `prepare.py` module docstring.
- [ ] **AC-PURE-1** `tests/sandbox/firecracker/test_prepare_purity.py` asserts: module docstring cites ADR-0013 + ADR-0001 + S1-07; `from __future__ import annotations` first; sorted `__all__`; only `subprocess`, `urllib.request`, `pathlib`, `shutil`, `os`, `tempfile`, `datetime`, `typing`, `pydantic`, `yaml`, `click`, `blake3`, `structlog`, `codegenie.*` stdlib/closure imports allowed.
- [ ] **AC-PURE-2** No `os.system` / `os.popen` / `shell=True` / `eval(` / `exec(` / `__import__(` / `pickle.loads` anywhere in `prepare.py` or `digests.py`.
- [ ] **AC-PURE-3** AST walker asserts `_default_runner` is the only function whose body contains `subprocess.run`; `_default_downloader` is the only function whose body contains `urllib.request.urlopen`.
- [ ] **AC-PURE-4** AST walker asserts no test file under `tests/sandbox/firecracker/test_prepare_*.py` contains `unittest.mock.patch("subprocess.*")`, `patch("shutil.which")`, or `patch("urllib.request.*")`.
- [ ] **AC-PURE-5..AC-PURE-8** Module-purity walker checks mirror S6-02's AC-PURE-3..AC-PURE-8 (function-body-import discipline, sorted-`__all__` enforcement, single-canonical-string enforcement for `"firecracker"`, no anaemic raw `dict` for API payload shapes).

### §O — FirecrackerClient EDITs (S6-01 surface amendments)

- [ ] **AC-FACTORY-1** `load_pinned_digests(*, digests_yaml: Path) -> PinnedDigests` lives in `src/codegenie/digests/` (the kernel-extract package); reads YAML, validates via Pydantic, returns frozen model.
- [ ] **AC-FACTORY-2** `FirecrackerClient.from_pinned_digests(digests: PinnedDigests, *, artifacts_root: Path, api_socket_factory: ApiSocketFactory = _default_api_socket_factory, process_handle_factory: ProcessHandleFactory = _default_process_handle_factory, vsock_exec_port: VsockExecPort = _default_vsock_exec_port, clock: Callable[[], datetime] = _default_clock) -> FirecrackerClient` is the canonical factory and forwards every S6-01 HARDENED DI port.
- [ ] **AC-FACTORY-3** `FirecrackerClient.from_pinned_digests` resolves artifact paths via `_artifact_paths_for(digests.rootfs, artifacts_root)`; raises `FirecrackerRootfsMissing` / `FirecrackerVmlinuxMissing` / `FirecrackerBinaryMissing` (existing S6-01 HARDENED errors) when any artifact is missing or digest mismatches.
- [ ] **AC-FACTORY-4** A convenience helper `FirecrackerClient.from_project(project_root: Path | None = None, **di_ports) -> FirecrackerClient` composes `find_project_root()` + `load_pinned_digests` + `from_pinned_digests`; this is what the CLI uses.
- [ ] **AC-FACTORY-5** The string-arg `FirecrackerClient.__init__(self, *, firecracker_path, vmlinux_digest, rootfs_digest)` constructor is **removed** — not `_internal`-tagged. Tests build via `from_pinned_digests(PinnedDigests(...))`. AST walker on test code asserts no caller constructs `FirecrackerClient(...)` with `firecracker_path=` / `vmlinux_digest=` / `rootfs_digest=` string args.
- [ ] **AC-CLIENT-EDIT-1** Enumerates every S6-01 AC modified: AC-API-1 (constructor signature replaced), all DI-port AC-DI-1..AC-DI-4 (now forwarded by `from_pinned_digests`), AC-RUN-1..AC-RUN-17 (test fixtures updated to use new factory).
- [ ] **AC-CLIENT-EDIT-2** `FirecrackerClient.health()` now consumes `digests/` kernel — uses `compute_blake3_streamed` for the binary/vmlinux/rootfs precondition check rather than the previous in-class helper. The S6-01 HARDENED in-class `_compute_blake3` is removed (kernel-extract consolidation).
- [ ] **AC-CLIENT-EDIT-3** S6-01 HARDENED's `tests/sandbox/firecracker/test_client_*.py` files are updated in this PR — every fixture switches to `from_pinned_digests(PinnedDigests(...))`. The diff is mechanical; coverage stays green.

### §P — Performance + Coverage + Deps

- [ ] **AC-PERF-1** `prepare` (bake) ≤ 360 s on the reference Linux CI runner (8-core, SSD); `tests/perf/test_prepare_bake_latency.py` (CI-only marker) tracks this.
- [ ] **AC-PERF-2** `prepare --check` ≤ 5 s on contributor laptop; `tests/perf/test_prepare_check_latency.py` tracks this; flake rate ≤ 1% over 30 runs.
- [ ] **AC-PERF-3** `prepare --check-rebake` ≤ 600 s on the reference runner.
- [ ] **AC-COV-1** ≥ 95% line / ≥ 90% branch on `src/codegenie/digests/` (this is the kernel — high bar).
- [ ] **AC-COV-2** ≥ 90% line / ≥ 80% branch on `src/codegenie/sandbox/firecracker/prepare.py`.
- [ ] **AC-DEP-1** `pyproject.toml` is unchanged. Stdlib `subprocess` + stdlib `urllib.request` + `blake3` (already in closure) + `pydantic` (already in closure) + `click` (already in closure) + `pyyaml` (already in closure) + `structlog` (already in closure). No new dependencies.

### §Q — TDD plan landed + Lint/typecheck/test green

- [ ] **AC-FIX-1** TDD plan's red test exists in each of the six new test files, is committed, and is green after implementation.
- [ ] **AC-FIX-2** `ruff check`, `ruff format --check`, `mypy --strict` on every touched module (no per-module relax in `[tool.mypy.overrides]`).
- [ ] **AC-FIX-3** `pytest tests/schema/test_digests_yaml.py tests/schema/test_no_subprocess_outside_build_chokepoint.py tests/sandbox/firecracker/test_prepare_*.py tests/cli/test_sandbox_prepare_cli.py tests/sandbox/test_errors_reason_cumulative.py` all pass.

## Implementation outline

1. **Extract the digest-loading kernel.** Create `src/codegenie/digests/__init__.py` with `compute_blake3_streamed(reader)`, `diff_digests(want, got)`, `_DIGEST_HEX_RE: Final[re.Pattern]`, `PinnedArtifact` Pydantic model, `DigestMismatch` Pydantic model. Sorted `__all__`. Module docstring cites ADR-0013 + S1-07 + this story.
2. **Hoist project-root resolver.** Create (or extend) `src/codegenie/_paths.py` with `find_project_root() -> Path`. Re-use from `tests/schema/_walkers.py::ROOT` derivation logic (S1-07).
3. **Widen the errors module.** `src/codegenie/sandbox/errors.py` — append 8 members to `SandboxBackendError.reason` Literal (cumulative-additive from S6-02's 27 → 35). Add five `Prepare*Error(SandboxBackendError)` subclasses.
4. **Widen the logging module.** `src/codegenie/sandbox/logging.py` — add `EVENT_SANDBOX_PREPARE_{STARTED,COMPLETED,FAILED}` `Final[str]` constants alphabetized into sorted `__all__`.
5. **Widen `ALLOWED_BINARIES`.** `src/codegenie/exec/__init__.py` — add `{mmdebstrap, qemu-img, tar, curl}` to the closed frozenset.
6. **Author `prepare.py`.** Pure helpers first: `_canonical_tar_argv`, `_canonical_mmdebstrap_argv`, `_compute_blake3_streamed` (re-exported from kernel), `_artifact_paths_for`, `_diff_digests`, `_required_tools`, `_parse_inputs_yaml`, `_render_inputs_yaml`, `_wrap_subprocess_error`. Then impure shells: `bake_rootfs`, `verify_against_digests`, `download_artifacts`, `compute_artifact_digests`, `write_artifacts`. `_default_runner`, `_default_downloader`, `_default_fs`, `_default_clock` are the only functions with side-effecting code.
7. **Replace placeholders.** `tools/digests.yaml` — replace the four `"TBD"` with real 64-char hex BLAKE3 digests. KEEP the scalar-string shape; do NOT introduce nested objects.
8. **Author `sources.yaml`.** `tools/firecracker/sources.yaml` carries `BakeInputs`-shaped operator-facing metadata (URLs, package list, snapshot pin, release-asset URL).
9. **Upgrade fence test.** `tests/schema/test_digests_yaml.py` — preserve S1-07 AC-DG-1..AC-DG-6 contract; ADD byte-level digest verification via `compute_blake3_streamed` against each of the four pinned artifacts. Planted-positive flips a digest byte and asserts the test fires.
10. **Widen subprocess allowlist.** `tests/schema/test_no_subprocess_outside_build_chokepoint.py` — 4 → 5 entries; planted-positive removes the new entry.
11. **EDIT S6-01 client.** Replace string-arg constructor with `from_pinned_digests` factory; remove the in-class `_compute_blake3` (kernel-extract); migrate every S6-01 HARDENED test fixture to use the new factory.
12. **Author CLI subcommand.** `src/codegenie/cli/sandbox.py` — Click subcommand `prepare` with `--backend firecracker` (required), `--check`, `--check-rebake`, `--download-only`, `--digests-yaml PATH`, `--artifacts-root PATH`, `--out-dir PATH` (for `--check-rebake`). Default flag combinations resolve at click-callback time (not at module import).
13. **Author `rootfs.md`.** `src/codegenie/sandbox/firecracker/rootfs.md` — document the snapshot-URL pin rationale (why this Debian snapshot), the deterministic bake procedure (`SOURCE_DATE_EPOCH=0`, fixed `mmdebstrap` package list, PAX-tar reproducibility), the verification recipe (`codegenie sandbox prepare --check`), how to bump the pinned digest via PR (`prepare --check-rebake` confirms the new pin), and the LFS-deferred / release-asset-materialization rationale.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Six test files:

#### 1. `tests/sandbox/firecracker/test_prepare_core.py`

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Final

import pytest

from codegenie.digests import PinnedArtifact
from codegenie.sandbox.firecracker.prepare import (
    BakeArtifacts,
    BakeInputs,
    Match,
    Mismatch,
    bake_rootfs,
    verify_against_digests,
)
from codegenie.sandbox.errors import (
    PrepareBakeFailed,
    PrepareDigestMismatch,
    PrepareToolMissing,
)

# Test doubles defined inline (not unittest.mock).
class RunnerSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], dict[str, object]]] = []
        self.return_codes: list[int] = []
    def __call__(self, argv, *, timeout=None, env=None, check=True, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append((tuple(argv), {"timeout": timeout, "env": env, **kwargs}))
        ...

# AC-DI-1, AC-DI-6
def test_bake_rootfs_uses_injected_runner(tmp_path: Path) -> None:
    inputs = _valid_bake_inputs()
    spy = RunnerSpy()
    bake_rootfs(inputs=inputs, out_dir=tmp_path, runner=spy, downloader=_NoopDownloader(), fs=_FakeFs(), clock=lambda: datetime(2026, 1, 1))
    assert len(spy.calls) >= 1  # at least mmdebstrap invocation
    assert spy.calls[0][0][0] == "mmdebstrap"  # AC-DETERMINISM-5

# AC-DETERMINISM-2 (Layer 2)
def test_bake_rootfs_argv_byte_identical_across_two_runs(tmp_path: Path) -> None:
    inputs = _valid_bake_inputs()
    spy_a, spy_b = RunnerSpy(), RunnerSpy()
    bake_rootfs(inputs=inputs, out_dir=tmp_path / "a", runner=spy_a, downloader=_NoopDownloader(), fs=_FakeFs(), clock=lambda: datetime(2026, 1, 1))
    bake_rootfs(inputs=inputs, out_dir=tmp_path / "b", runner=spy_b, downloader=_NoopDownloader(), fs=_FakeFs(), clock=lambda: datetime(2026, 1, 1))
    assert [c[0] for c in spy_a.calls] == [c[0] for c in spy_b.calls]  # argv tuples byte-identical

# AC-BAKE-1(a), AC-ERR-1, AC-ERR-2, AC-FCS-3
def test_bake_rootfs_raises_prepare_tool_missing_before_any_subprocess(tmp_path: Path) -> None:
    inputs = _valid_bake_inputs()
    spy = RunnerSpy()
    fs = _FakeFs(missing_tools={"mmdebstrap"})
    with pytest.raises(PrepareToolMissing) as exc_info:
        bake_rootfs(inputs=inputs, out_dir=tmp_path, runner=spy, downloader=_NoopDownloader(), fs=fs, clock=lambda: datetime(2026, 1, 1))
    assert exc_info.value.reason == "sandbox.prepare.tool_missing"
    assert exc_info.value.tool == "mmdebstrap"
    assert exc_info.value.install_hint is not None
    assert spy.calls == []  # AC-IDEMPOTENT-1 style: no subprocess fired

# AC-VERIFY-1, AC-MODEL-3 (tagged-union exhaustiveness)
def test_verify_against_digests_returns_match_on_equality(tmp_path: Path) -> None:
    digests, fake_paths = _materialize_synthetic_artifacts(tmp_path)
    outcome = verify_against_digests(digests=digests, artifacts_dir=tmp_path, hasher=_byte_perfect_hasher, fs=_FakeFs())
    assert isinstance(outcome, Match)

def test_verify_against_digests_returns_mismatch_on_byte_flip(tmp_path: Path) -> None:
    digests, fake_paths = _materialize_synthetic_artifacts(tmp_path)
    fake_paths.flip_byte_in("vmlinux")
    outcome = verify_against_digests(digests=digests, artifacts_dir=tmp_path, hasher=_byte_perfect_hasher, fs=_FakeFs())
    assert isinstance(outcome, Mismatch)
    assert any(d.key == "vmlinux" for d in outcome.differences)

# AC-IDEMPOTENT-1
def test_bake_rootfs_short_circuits_on_idempotent_second_call(tmp_path: Path) -> None:
    inputs = _valid_bake_inputs()
    spy = RunnerSpy()
    bake_rootfs(inputs=inputs, out_dir=tmp_path, runner=spy, downloader=_NoopDownloader(), fs=_FakeFs(), clock=lambda: datetime(2026, 1, 1))
    n_calls_first = len(spy.calls)
    bake_rootfs(inputs=inputs, out_dir=tmp_path, runner=spy, downloader=_NoopDownloader(), fs=_FakeFs(), clock=lambda: datetime(2026, 1, 1))
    assert len(spy.calls) == n_calls_first  # zero additional calls

# AC-IDEMPOTENT-1 (the strong form: not just "no new bake", but "no subprocess at all")
def test_bake_rootfs_second_call_records_zero_runner_calls_when_artifacts_present_and_match(tmp_path: Path) -> None:
    inputs = _valid_bake_inputs()
    _materialize_synthetic_artifacts_under(tmp_path, inputs=inputs)
    spy = RunnerSpy()
    bake_rootfs(inputs=inputs, out_dir=tmp_path, runner=spy, downloader=_NoopDownloader(), fs=_FakeFs(), clock=lambda: datetime(2026, 1, 1))
    assert spy.calls == ()
```

#### 2. `tests/sandbox/firecracker/test_prepare_helpers.py`

```python
from __future__ import annotations

import hashlib
from io import BytesIO

import blake3
import pytest
from hypothesis import given, strategies as st

from codegenie.digests import compute_blake3_streamed, diff_digests
from codegenie.sandbox.firecracker.prepare import (
    _artifact_paths_for,
    _canonical_mmdebstrap_argv,
    _canonical_tar_argv,
    _required_tools,
)

# AC-FCS-1, AC-HASH-1
@given(payload=st.binary(min_size=0, max_size=2**20), chunk_size=st.integers(min_value=1, max_value=2**20))
def test_compute_blake3_streamed_matches_oneshot_blake3(payload: bytes, chunk_size: int) -> None:
    reader = BytesIO(payload).read
    streamed = compute_blake3_streamed(lambda n: reader(min(n, chunk_size)))
    one_shot = blake3.blake3(payload).hexdigest()
    assert streamed == one_shot

# AC-HASH-2 (edge: empty input)
def test_compute_blake3_streamed_empty_bytes_known_constant() -> None:
    reader = BytesIO(b"").read
    assert compute_blake3_streamed(reader) == blake3.blake3(b"").hexdigest()

# AC-DETERMINISM-5 (Layer 1: golden argv fixture for tar)
def test_canonical_tar_argv_is_byte_stable_golden() -> None:
    argv = _canonical_tar_argv(src=Path("/src"), dst=Path("/dst.tar"), source_date_epoch=0)
    expected = (
        "tar", "--sort=name", "--mtime=@0", "--owner=0", "--group=0", "--numeric-owner",
        "--pax-option=delete=atime,delete=ctime,exthdr.name=%d/PaxHeaders/%f",
        "-cf", "/dst.tar", "-C", "/src", ".",
    )
    assert argv == expected

# AC-DETERMINISM-5 (Layer 1: golden argv fixture for mmdebstrap)
def test_canonical_mmdebstrap_argv_is_byte_stable_golden() -> None:
    inputs = _valid_bake_inputs()
    argv = _canonical_mmdebstrap_argv(inputs=inputs, out=Path("/out.ext4"))
    assert argv[0] == "mmdebstrap"
    assert "--mode=fakechroot" in argv
    assert f"--variant={inputs.mmdebstrap_variant}" in argv
    assert str(inputs.snapshot_url) in argv  # snapshot URL pin literally on argv

# AC-FCS-3
def test_required_tools_is_the_canonical_quadruple() -> None:
    assert _required_tools() == ("mmdebstrap", "qemu-img", "tar", "curl")

# AC-FCS-2 (pure path arithmetic)
def test_artifact_paths_for_returns_digest_prefixed_subdir() -> None:
    paths = _artifact_paths_for(rootfs_digest="abcdef1234567890" * 4, root=Path("/r"))
    assert paths.rootfs == Path("/r") / ("abcdef1234567890" * 4) / "rootfs.ext4"
    assert paths.vmlinux == Path("/r") / ("abcdef1234567890" * 4) / "vmlinux"
    assert paths.firecracker == Path("/r") / ("abcdef1234567890" * 4) / "firecracker"

# AC-FCS-4
def test_diff_digests_returns_per_key_mismatches() -> None:
    want = _make_pinned_digests(firecracker_binary="a" * 64, vmlinux="b" * 64, rootfs="c" * 64, policy_yaml="d" * 64)
    got = _make_pinned_digests(firecracker_binary="a" * 64, vmlinux="X" * 64, rootfs="c" * 64, policy_yaml="d" * 64)
    diffs = diff_digests(want=want, got=got)
    assert len(diffs) == 1
    assert diffs[0].key == "vmlinux"
```

#### 3. `tests/sandbox/firecracker/test_prepare_lifecycle.py`

```python
# AC-CHECK-MODE-1..-4, AC-BAKE-1..-4, AC-IDEMPOTENT-1..-3
# Exhaustive table of (state-of-disk, flag-passed) → (exit_code, runner_calls, downloader_calls, event_name)
# A 5-cell partial-bake-failure rollback grid using parametrized RunnerSpy that raises at step k.
...
```

#### 4. `tests/sandbox/firecracker/test_prepare_errors.py`

```python
# AC-ERR-1..-6, AC-WID-1..-4
# Each of the 8 new reason strings has a positive-raise test;
# typing.get_args(SandboxBackendError.__fields__["reason"].annotation) is asserted byte-exactly;
# planted-positive removes one member and asserts the test fires;
# every Prepare*Error carries the documented structured fields populated correctly.
...
```

#### 5. `tests/sandbox/firecracker/test_prepare_purity.py`

```python
# AC-PURE-1..-8, AC-CANONICAL-1..-4, AC-MOD-1..-3
# AST walker over prepare.py + digests.py:
# - docstring contains "ADR-0013" and "ADR-0001" and "S1-07"
# - from __future__ import annotations first non-comment line
# - sorted __all__ matches expected tuple
# - only _default_runner contains subprocess.run
# - only _default_downloader contains urllib.request.urlopen
# - no os.system / os.popen / shell=True / eval / exec / __import__ / pickle.loads
# - literal "firecracker" appears ONLY in _BACKEND_NAME declaration
# - planted-positive variants verify each rule fires
```

#### 6. `tests/schema/test_digests_yaml.py` (UPGRADE)

```python
# AC-YAML-SHAPE-3, AC-YAML-SHAPE-4
# Preserves S1-07 AC-DG-1..AC-DG-6 (already-green) and adds:
def test_sandbox_pinned_digests_match_on_disk_artifact_bytes() -> None:
    digests = load_pinned_digests(digests_yaml=find_project_root() / "tools/digests.yaml")
    artifacts_dir = find_project_root() / "tools/firecracker" / digests.rootfs
    outcome = verify_against_digests(digests=digests, artifacts_dir=artifacts_dir, hasher=compute_blake3_streamed_from_path)
    assert isinstance(outcome, Match), (
        "Pinned digests do not match on-disk artifact bytes:\n" + "\n".join(f"  {d.key}: expected {d.expected[:8]}..., got {d.observed[:8]}..." for d in outcome.differences)
    )

# Planted-positive — flip a byte in vmlinux, assert the test fires.
def test_sandbox_pinned_digests_planted_positive_byte_flip(tmp_path: Path) -> None:
    ...
```

Plus a CI-only `tests/integration/sandbox/test_prepare_real_mmdebstrap.py` (AC-DETERMINISM-3 Layer 3) marked `pytest.mark.slow + skipif(not _has_mmdebstrap())` doing real bake-twice digest equality.

Plus `tests/cli/test_sandbox_prepare_cli.py` covering every flag combination via `click.testing.CliRunner` with the DI ports injected through a custom `click.Context.obj`.

Plus `tests/sandbox/firecracker/test_from_pinned_digests.py` covering AC-FACTORY-1..AC-FACTORY-5 — the factory forwards every S6-01 HARDENED DI port; the string-arg constructor is removed (AST walker fires on hypothetical re-introduction).

Plus `tests/sandbox/test_errors_reason_cumulative.py` covering AC-ERR-3 — the cumulative 35-member set asserted byte-exactly.

### Green — make it pass

Smallest implementation:
- Extract the digest kernel first (no consumers yet; unit-test in isolation).
- Wire `errors.py` / `logging.py` / `ALLOWED_BINARIES` widenings.
- Author `prepare.py` pure helpers first, impure shells next, CLI last.
- Replace `tools/digests.yaml` `"TBD"` with real digests (computed by running the prepared `prepare --bake` once locally on a Linux machine with `mmdebstrap`).
- Author `sources.yaml`.
- Upgrade fence test (preserving S1-07 contract).
- EDIT S6-01 client to use `from_pinned_digests`; migrate every existing S6-01 test fixture in the same PR.
- Author CLI subcommand.
- Author `rootfs.md`.

### Refactor — clean up

- Extract `_compute_blake3_streamed` to the `digests/` kernel (already done at step 1; cross-check consumers).
- Pin per-key helpers (`load_pinned_digests` / `diff_digests`) so consumers do not duck-type the yaml shape.
- Confirm `_canonical_tar_argv` / `_canonical_mmdebstrap_argv` flag set matches the documented PAX-tar / fakechroot-mmdebstrap reproducibility recipe.
- Move the snapshot-URL pin to `sources.yaml` so a digest bump is one PR (`sources.yaml` edit + `tools/digests.yaml` edit + new `tools/firecracker/<digest>/` artifacts).
- Confirm `RunnerSpy` / `DownloaderSpy` / `FsSpy` test-double shapes live in `tests/sandbox/firecracker/_spies.py` (not duplicated across files).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/digests/__init__.py` | New package — kernel extract (`compute_blake3_streamed`, `diff_digests`, `_DIGEST_HEX_RE`, `PinnedArtifact`, `DigestMismatch`). |
| `src/codegenie/_paths.py` | New (or extend) — `find_project_root()` hoisted from `tests/schema/_walkers.py::ROOT`. |
| `src/codegenie/sandbox/errors.py` | EDIT — widen `SandboxBackendError.reason` Literal additively by 8 + add 5 `Prepare*Error(SandboxBackendError)` subclasses. |
| `src/codegenie/sandbox/logging.py` | EDIT — add 3 `EVENT_SANDBOX_PREPARE_*` `Final[str]` constants alphabetized into sorted `__all__`. |
| `src/codegenie/exec/__init__.py` | EDIT — widen `ALLOWED_BINARIES` by 4 (`mmdebstrap`, `qemu-img`, `tar`, `curl`). |
| `src/codegenie/sandbox/firecracker/prepare.py` | New — pure helpers + impure shells + `_default_runner` / `_default_downloader` / `_default_fs` / `_default_clock`. |
| `src/codegenie/sandbox/firecracker/rootfs.md` | New — documented bake procedure + materialization rationale + bump workflow. |
| `src/codegenie/sandbox/firecracker/client.py` | EDIT — replace string-arg `__init__` with `from_pinned_digests` factory; consume `digests/` kernel. |
| `src/codegenie/cli/sandbox.py` | New (or EDIT if S1-07 left a stub) — `prepare` subcommand with 5 flags. |
| `tools/digests.yaml` | EDIT — replace 4 `"TBD"` with real 64-char hex BLAKE3; KEEP scalar-string shape. |
| `tools/firecracker/sources.yaml` | New — `BakeInputs`-typed operator metadata. |
| `.gitignore` | EDIT — add `/tools/firecracker/[0-9a-f]*/` to block accidental commits. |
| `tests/schema/test_digests_yaml.py` | EDIT — upgrade from presence-only to byte-level digest validation; preserve S1-07 AC-DG-*. |
| `tests/schema/test_no_subprocess_outside_build_chokepoint.py` | EDIT — `_SUBPROCESS_ALLOWLIST` 4 → 5. |
| `tests/sandbox/firecracker/test_prepare_core.py` | New — DI-seam end-to-end. |
| `tests/sandbox/firecracker/test_prepare_helpers.py` | New — pure-helper hypothesis + golden tests. |
| `tests/sandbox/firecracker/test_prepare_lifecycle.py` | New — flag matrix + rollback grid. |
| `tests/sandbox/firecracker/test_prepare_errors.py` | New — closed-Literal `reason` + structured-field shape. |
| `tests/sandbox/firecracker/test_prepare_purity.py` | New — module-purity AST walker. |
| `tests/sandbox/firecracker/test_from_pinned_digests.py` | New — factory + DI-port forwarding. |
| `tests/sandbox/firecracker/_spies.py` | New — shared `RunnerSpy`, `DownloaderSpy`, `FsSpy`. |
| `tests/sandbox/test_errors_reason_cumulative.py` | New — `typing.get_args` cumulative-set assertion. |
| `tests/cli/test_sandbox_prepare_cli.py` | New — Click-runner unit tests for every flag combination. |
| `tests/integration/sandbox/test_prepare_real_mmdebstrap.py` | New (CI-only) — `pytest.mark.slow` real-world bake equality. |
| `tests/perf/test_prepare_check_latency.py` | New — `--check` ≤ 5 s budget tracker. |
| `tests/perf/test_prepare_bake_latency.py` | New (CI-only) — `--bake` ≤ 360 s budget tracker. |

## Out of scope

- The other `codegenie sandbox` subcommands (`health`, `inspect`, `gc`) — S8-01.
- Auto-detect (`registry.auto_detect`) — S6-04.
- KVM-gated integration smoke + weekly cron — S6-05.
- Rebuild cadence policy (daily/weekly/per-bump) — operational, Phase 14 (Open Q1).
- Multi-architecture rootfs (arm64) — Phase 5 is x86_64 only.
- `register_digest_pinned_artifact(...)` registry decorator — deferred until Phase 7+ when the fifth distinct digest-pinned artifact enters the closed-keys set (rule-of-three not closed at 4).
- Widening `tools/digests.yaml` closed-keys set to include `sandbox.sources_yaml` (so `sources.yaml` itself is digest-pinned) — follow-on story when a second `sources.yaml`-shaped catalog enters scope.
- LFS adoption — explicit Phase-5 non-goal; release-asset pull from a pinned GitHub Release is the materialization path.
- `tools/firecracker/<rootfs_digest>/` orphan-pruning (left after a digest bump) — `sandbox gc` (S8-01).

## Notes for the implementer

- **Kernel-extract opportunity for `src/codegenie/digests/` is the load-bearing payoff of this story.** It is the third concrete consumer of ADR-0013's digest-pinning pattern; rule-of-three reached. Extract `compute_blake3_streamed` + `diff_digests` + `_DIGEST_HEX_RE` to the new package — they will be re-consumed by S6-01 `FirecrackerClient.health()`, by the fence test, by `prepare`, and by Phase 7's distroless image-digest verification. Resist the temptation to also ship `register_digest_pinned_artifact(...)` registry decorator — the consumer set is closed at 4 (`firecracker`, `vmlinux`, `rootfs`, `policy_yaml`); widening to 5 is the rule-of-three threshold for the registry.
- **`--check` vs `--check-rebake` semantic split is non-negotiable.** Re-baking on every PR would cost ~5 min/run × every PR ≈ phase-blocker. `--check` (disk-read) is the PR-time fence; `--check-rebake` (re-bake to tmpdir) is the operator-bump verification only. Document this in `rootfs.md` with a "When to run which" decision table.
- **Release-asset materialization, not LFS, is the Phase-5 path.** The artifacts are large (~250 MB combined); committing via LFS would slow every clone. Hosting them as a GitHub Release asset is one fetch on CI per workflow; contributor laptops never need them unless they want to run the real-mmdebstrap test. Document in `rootfs.md`.
- **`mmdebstrap` is NOT `debootstrap`** — the former is unprivileged, reproducible by design, and is the only tool that makes `SOURCE_DATE_EPOCH=0` byte-stable across machines. Do not substitute.
- **BLAKE3 is the project's canonical hash** (also used for the audit chain in S2-01). Do not use SHA-256 here; `tools/digests.yaml` is one consistent format.
- **The fence-test upgrade is the single most load-bearing piece of this story.** Presence-only (S1-07) was a security stub; byte-level digest validation is the real check. Treat any reviewer pushback on test speed (streamed BLAKE3 is fast — `_compute_blake3_streamed` is ≤ 1 s on 250 MB) as "make it faster," not "make it skip."
- **The `--check` invocation is what CI runs on every PR; the no-flag invocation is what an operator runs once to materialize artifacts.** Keep them in the same subcommand to make the operator → CI parity obvious.
- **Resist documenting "what" in `rootfs.md`; document `why every pin exists`** — every reader will eventually want to bump one of them, and `why` is the only thing that survives.
- **Do not embed any timestamps or hostnames in the rootfs build;** `SOURCE_DATE_EPOCH=0` plus the `mmdebstrap` `--variant=minbase` plus deterministic-tar settings (per AC-DETERMINISM-5) is what makes the digest stable across machines.
- **Subprocess fence is widened by exactly one entry** (`prepare.py`); `ALLOWED_BINARIES` is widened by exactly four entries (`mmdebstrap`, `qemu-img`, `tar`, `curl`). Keep the diff tight; reviewers approve based on the diff scope.
- **`from_pinned_digests` is the only public construction surface** for `FirecrackerClient` after this story. S6-01 HARDENED's string-arg `__init__` is removed (not `_internal`-tagged). Migrate every S6-01 test fixture in the same PR as a mechanical edit — the executor will write a per-test `_make_client()` helper.
- **Pattern lineage** — S3-01 (closed-Literal `reason`) → S3-02 (DI port) → S3-03 (FCS split) → S6-01 (host client; first multi-port consumer) → S6-02 (network policy; mandatory pattern inheritance) → S6-03 (this story; fifth consumer; mandatory). Five examples justify a kernel-extract for the *shared digest-loading logic* but NOT for the DI-port plumbing (each backend's port set is per-backend; sharing them would couple unrelated backends).
- **Test-double convention:** `RunnerSpy`, `DownloaderSpy`, `FsSpy` live in `tests/sandbox/firecracker/_spies.py` and are imported from there. No `unittest.mock` anywhere in this story's tests.
- **`_paths.find_project_root()` is hoisted** from `tests/schema/_walkers.py::ROOT` derivation. If the test-side helper is more featureful, the production helper is a strict subset (just the `pyproject.toml`-upwalk). Reuse, do not re-vendor.
- **`tools/firecracker/sources.yaml` is operator-facing**; keep field names in `BakeInputs` aligned with what an operator types when bumping. Validator messages should be human-readable.
- **PAX-tar reproducibility settings** are documented at <https://reproducible-builds.org/docs/archives/>; the AC-DETERMINISM-5 flag set is the canonical "no extended attributes, fixed mtime, fixed ownership, sorted filenames" recipe.
- **`SOURCE_DATE_EPOCH=0`** is the [reproducible-builds.org canonical](https://reproducible-builds.org/docs/source-date-epoch/) build timestamp. `mmdebstrap` honors it; `tar --mtime=@${SOURCE_DATE_EPOCH}` honors it; `mkfs.ext4` (called inside `mmdebstrap`'s rootfs construction) honors it.
- **Forward-compat anchor** — when Phase 7's Chainguard distroless work adds a fifth `sandbox.*` digest key (`sandbox.distroless_base_image`), that story will close the rule-of-three on `register_digest_pinned_artifact(...)` registry. This story leaves the registry-decorator opportunity as a Notes-for-implementer for the Phase 7 author to pick up; do NOT preemptively ship the decorator here.
- **CI workflow YAML** must invoke `codegenie sandbox prepare --backend firecracker --download-only` BEFORE `tests/schema/test_digests_yaml.py` runs. Sequence: (1) checkout, (2) bootstrap, (3) `prepare --download-only`, (4) `make check`. If `--download-only` is omitted, the fence test fails with `PrepareCheckFailed(reason="sandbox.prepare.check_failed")` and the failure message tells the workflow author to add the step.
- **The `Prepare*Error` subclasses inherit from `SandboxBackendError`** — they are NOT plain `RuntimeError` / `ValueError`. This guarantees Phase 13's cost ledger (which keys on `(error_class, reason)`) sees them as part of the sandbox-error taxonomy. Mismodeling them would orphan the rows.
