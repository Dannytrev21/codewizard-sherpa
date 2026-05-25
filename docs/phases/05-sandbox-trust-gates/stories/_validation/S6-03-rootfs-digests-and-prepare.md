# Validation report: S6-03 — Pinned rootfs + `vmlinux` digest enforcement + `sandbox prepare`

**Validated:** 2026-05-25
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Validator agent run:** automated (`story-validation-corrector` scheduled task)

## Summary

S6-03 closes the gap left by [S1-07 HARDENED](S1-07-ci-fence-tests-digests-yaml.md) (which pinned only **placeholder presence** of the four `sandbox.*` digest keys) and [S6-01 HARDENED](S6-01-firecracker-client-kvm-boot.md) (which raises `FirecrackerBinaryMissing` / `FirecrackerVmlinuxMissing` / `FirecrackerRootfsMissing` on digest mismatch but accepts constructor-supplied digests rather than a single source of truth). It does three things: (a) replaces placeholders with real BLAKE3-256 hex digests in `tools/digests.yaml`; (b) upgrades `tests/schema/test_digests_yaml.py` from **presence-only** to **byte-level digest validation**; (c) adds `codegenie sandbox prepare --backend firecracker` so a clean machine can rebuild artifacts byte-identically from pinned inputs.

Pattern-lineage-wise, S6-03 is the **third concrete consumer of the codegenie-owned digest-pinning family** ([ADR-0013](../../ADRs/0013-digest-pinned-policy-yaml-codegenie-owned.md) is the policy-YAML precedent; S1-07 HARDENED is the second consumer for the four `sandbox.*` placeholders; S6-03 is now where the rule-of-three lands and the digest-loading / digest-validating shared kernel must be **extracted** — not re-invented per-artifact). It is also the **fifth concrete consumer** of the FCS + Hexagonal-DI-port + closed-Literal-`reason` + `_BACKEND_NAME`-`Final` + module-purity-AST-walker pattern stack (S3-01 / S3-02 / S3-03 / S6-01 / S6-02 each shipped explicit consumers; rule-of-three crossed three times over — these are **mandatory AC-tier inheritance**).

The draft correctly identified the surface (real digest values + fence-test upgrade + `prepare` subcommand + `rootfs.md` runbook + byte-identical-bake sanity test) and traced cleanly to ADR-0013 / ADR-0004 / ADR-0001 / production ADR-0019, but had **34 findings across all four critic lenses, including thirteen block-tier weaknesses** that an executor following the draft literally would have shipped silently broken, would have broken S1-07's pinned `tools/digests.yaml` shape, or could not have unit-tested without `mmdebstrap` on the runner. The most consequential:

1. **(consistency — block) Proposed YAML shape silently breaks S1-07 HARDENED AC-DG-2 / AC-DG-5/6.** S1-07 pinned `tools/digests.yaml` to a flat shape: top-level `sandbox:` with exactly four scalar-string keys `firecracker`, `vmlinux`, `rootfs`, `policy_yaml`, each value either `"TBD"` (placeholder) or a 64-char hex digest. The draft's Implementation outline §1 introduces **nested objects** (`sandbox.firecracker.binary`, `sandbox.firecracker.binary_url`, `sandbox.vmlinux.digest`, `sandbox.vmlinux.source_url`, `sandbox.rootfs.digest`, `sandbox.rootfs.build_recipe_path`). That fails `_DIGEST_HEX_RE.fullmatch()` (S1-07 AC-DG-5) at the moment of edit; S1-07's planted-positive (`test_digests_yaml_planted_positive`) would go green for the wrong reason and the live test would fail across CI matrix. Resolution: AC-YAML-SHAPE-1..-5 keep `tools/digests.yaml#sandbox.{firecracker,vmlinux,rootfs,policy_yaml}` as **scalar 64-char hex digests** (replacing only the `"TBD"` placeholder bytes); move URL / build-recipe metadata to a new file `tools/firecracker/sources.yaml` (Pydantic-typed) which is the operator-facing input to `prepare`. S1-07's fence test is **upgraded in place** to add hash-verification on top of presence; the shape contract from S1-07 is monotone-preserved.

2. **(coverage + design-patterns — block) Hexagonal DI port for `runner` / `downloader` / `filesystem` / `clock` missing.** Fifth consumer of the pattern (S3-01 set the precedent → S6-02 made it AC-tier mandatory at the fourth consumer). The draft's Implementation outline calls `subprocess.run("mmdebstrap" ...)`, `subprocess.run("qemu-img" ...)`, `subprocess.run("tar" ...)` and `urllib.request.urlopen(kernel_url)` (or `curl` shellout) inline. Tests use `patch("shutil.which")` (unstable mock boundary; S6-01 AC-DI-1 expressly forbids this idiom). Resolution: AC-DI-1..AC-DI-6 elevate to AC-tier — `bake_rootfs(*, inputs, out_dir, runner=_default_runner, downloader=_default_downloader, fs=_default_fs, clock=_default_clock) -> BakeArtifacts`; `verify_against_digests(*, digests, artifacts_dir, hasher=_default_hasher) -> VerifyOutcome`. `_default_runner` is the **only** function in `prepare.py` that calls `subprocess.run`; AST walker (AC-PURE-3) asserts this. Tests inject `RunnerSpy`, `DownloaderSpy` directly; no `unittest.mock.patch("subprocess.run")`.

3. **(coverage + design-patterns — block) Functional core / imperative shell split missing.** Fifth consumer (S3-01/S3-02/S3-03/S6-01/S6-02 each shipped explicit FCS splits). Resolution: AC-FCS-1..AC-FCS-8 enumerate **pure helpers** — `_compute_blake3_streamed(reader: Callable[[int], bytes]) -> str` (pure: chunked-update, no I/O), `_render_inputs_yaml(inputs: BakeInputs) -> str` (deterministic canonical YAML), `_parse_inputs_yaml(raw: bytes) -> BakeInputs`, `_artifact_paths_for(rootfs_digest: str, root: Path) -> ArtifactPaths` (pure path arithmetic), `_required_tools() -> tuple[str, ...]` (`("mmdebstrap", "qemu-img", "tar", "curl")`), `_diff_digests(want: PinnedDigests, got: PinnedDigests) -> tuple[DigestMismatch, ...]` (pure, returns tagged-union mismatch records), `_canonical_tar_argv(src: Path, dst: Path) -> tuple[str, ...]` (pure — emits `tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner --pax-option=...` etc.), `_canonical_mmdebstrap_argv(inputs: BakeInputs) -> tuple[str, ...]`. **Impure shells**: `bake_rootfs`, `verify_against_digests`, `download_kernel`, `compute_artifact_digests`, `write_artifacts`. Each pure helper unit-tested in isolation with hypothesis property tests where applicable.

4. **(consistency — block) `tools/digests.yaml` default-cwd path is brittle and contradicts S6-01 HARDENED's DI / project-root resolution.** The draft hardcodes `Path("tools/digests.yaml")` in both the test (line 106) and the proposed `FirecrackerClient.from_digests_yaml(path: Path = Path("tools/digests.yaml"))` (Implementation §3). Anything invoked outside the repo root breaks silently. Resolution: AC-PATH-1..AC-PATH-3 require a `find_project_root() -> Path` helper at `src/codegenie/_paths.py` (or, if one exists, re-use it; otherwise hoist from S1-07's `_walkers.py::ROOT` derivation), an explicit `--digests-yaml PATH` CLI flag with default `find_project_root() / "tools/digests.yaml"`, and the fence test computes the same way. `from_digests_yaml(*, digests_yaml: Path, artifacts_root: Path | None = None, ...)` always takes an explicit path (no default that resolves to cwd).

5. **(consistency — block) `from_digests_yaml` classmethod silently undoes S6-01 HARDENED DI-port discipline.** S6-01 HARDENED AC-DI-1..AC-DI-4 elevated `api_socket_factory`, `process_handle_factory`, `vsock_exec_port`, `clock` to constructor DI ports. The draft's `FirecrackerClient.from_digests_yaml(path) -> FirecrackerClient` (Implementation §3) reads from disk inside a classmethod, has no way to forward those DI ports, and uses the existing `__init__` (marked `_internal` in the draft) as the back door. That makes the classmethod un-testable on macOS / non-KVM hosts (the very environments S6-04 will route to DinD). Resolution: AC-FACTORY-1..AC-FACTORY-4 split the responsibilities — `load_pinned_digests(*, digests_yaml: Path) -> PinnedDigests` is a **pure-of-fs read** helper in `digests.py` returning a frozen Pydantic model; `FirecrackerClient.from_pinned_digests(digests: PinnedDigests, *, artifacts_root: Path, api_socket_factory=..., process_handle_factory=..., vsock_exec_port=..., clock=...) -> FirecrackerClient` is the factory and forwards every DI port. The string constructor is **removed** (not `_internal`-tagged — actually removed; tests construct via `from_pinned_digests` with hand-built `PinnedDigests`).

6. **(consistency + coverage — block) Event names `sandbox.prepare.start` / `sandbox.prepare.done` violate S1-01 HARDENED `STARTED`/`COMPLETED`/`FAILED` verb canonical-table.** S1-01 pinned an exhaustive verb-triple convention; S6-01 added 6 events, S6-02 added 6 more (`*.applied` / `*.reverted` / `*.apply_failed` / `*.created` / `*.destroyed` / `*.orphan`). The draft uses bare verbs (`start`, `done`). Resolution: AC-EVT-1 appends **three** `Final[str]` constants to `sandbox/logging.py` alphabetized into the sorted `__all__`:
   - `EVENT_SANDBOX_PREPARE_STARTED = "sandbox.prepare.started"`
   - `EVENT_SANDBOX_PREPARE_COMPLETED = "sandbox.prepare.completed"`
   - `EVENT_SANDBOX_PREPARE_FAILED = "sandbox.prepare.failed"`

   Payloads carry `backend`, `rootfs_digest`, `vmlinux_digest`, `firecracker_binary_digest`, `elapsed_seconds`, `mode` (`"bake"` | `"check"`), and on FAILED the structured `reason` (per AC-ERR-1).

7. **(consistency — block) Closed-Literal `SandboxBackendError.reason` widening absent.** S6-01 widened by 9 members (to 20 total); S6-02 widened by 7 more (to 27 total). Phase 11 / 13 cost ledger keys on `(error_class, reason)`; `PrepareToolMissing` as drafted is a plain exception with no closed-Literal `reason` and no `SandboxBackendError` inheritance. Resolution: AC-ERR-1..AC-ERR-6 widen S1-01 `SandboxBackendError.reason` Literal additively by **eight members** — `"sandbox.prepare.tool_missing"`, `"sandbox.prepare.inputs_yaml_invalid"`, `"sandbox.prepare.kernel_download_failed"`, `"sandbox.prepare.kernel_digest_mismatch"`, `"sandbox.prepare.rootfs_bake_failed"`, `"sandbox.prepare.rootfs_digest_mismatch"`, `"sandbox.prepare.artifact_write_failed"`, `"sandbox.prepare.check_failed"`. `PrepareToolMissing(SandboxBackendError)`, `PrepareKernelDownloadFailed(SandboxBackendError)`, `PrepareDigestMismatch(SandboxBackendError)`, `PrepareBakeFailed(SandboxBackendError)`, `PrepareCheckFailed(SandboxBackendError)` each narrow on the relevant subset via `reason: Literal[...]`. `typing.get_args(...)` asserts the cumulative union (27 + 8 = 35 members) byte-exactly.

8. **(consistency — block) Warning IDs / structured-data shape unpinned.** Draft `PrepareToolMissing(tool="...", install_hint="...")` is a free-form constructor — no warning-ID, no namespace-regex compliance. Per S6-01/S6-02 inheritance, every error message field that drives operator action must be machine-readable. Resolution: AC-WID-1..AC-WID-4 pin: each `Prepare*Error` carries `tool: str | None`, `install_hint: str | None`, `expected_digest: str | None` (first 8 hex), `observed_digest: str | None` (first 8 hex), `path: Path | None` — populated only when relevant — and a module-level `_WARNING_IDS: Final[frozenset[str]]` validated at import time via `raise AssertionError(...)` (bare `assert` forbidden per CLAUDE.md `forbidden-patterns`).

9. **(coverage — block) `--check` mode contract is ambiguous (reads-from-disk vs tmp-bake-and-compare).** Draft AC-5 says "if `--check` is passed, fails non-zero on digest mismatch instead of writing" but does not say whether `--check` (a) computes BLAKE3 over the **already-on-disk** artifacts at `tools/firecracker/<rootfs_digest>/` and compares to `tools/digests.yaml` (cheap, ~3 s on CI; the obvious CI path), or (b) **re-bakes** to a tmpdir and compares (expensive, ~5 min on CI; the operator-bump verification path). These are different operations with different semantic contracts. Resolution: AC-CHECK-MODE-1..AC-CHECK-MODE-4 split into two flags: `--check` (default — read-from-disk verify; ≤ 5 s budget; what CI runs on every PR; matches `tests/schema/test_digests_yaml.py` semantics) vs `--check-rebake` (re-bake to tmpdir + compare; ≤ 6 min budget; what an operator runs after bumping the snapshot URL to confirm the new pin reproduces). `prepare` (no flag) writes; the operator-bump workflow is the explicit composition `prepare → check-rebake → commit`.

10. **(test-quality — block) `test_prepare_check_passes_when_digests_match` runs against the real `tools/digests.yaml` and committed artifacts.** Contributor laptops without committed (or LFS-fetched) artifacts fail this on every PR. The test is environment-coupled. Resolution: AC-TEST-1..AC-TEST-4 split into (a) a unit test using `tmp_path` with synthetic `PinnedDigests` + synthetic artifact bytes + the DI seam, (b) an integration test marked `pytest.mark.integration` + `pytest.mark.skipif(not _committed_artifacts_present())`, (c) a CI-fence test `tests/schema/test_digests_yaml.py` that reads real bytes (runs on every PR, gated by LFS-fetch in CI workflow). The unit test is what proves the logic; the fence test is what proves the artifacts on this commit are intact.

11. **(test-quality — block) The byte-identical determinism test is the load-bearing proof of idempotency and never runs in unit CI.** The draft's `test_prepare_is_byte_identical_across_two_runs` is `pytest.mark.slow` and `pytest.mark.skipif(shutil.which("mmdebstrap") is None)` — meaning on every contributor laptop and the standard CI matrix, the AC-6 idempotency claim is **untested**. Resolution: AC-DETERMINISM-1..AC-DETERMINISM-4 ship three layers — (a) `_canonical_tar_argv` + `_canonical_mmdebstrap_argv` pure-helper golden-fixture tests that pin the exact argv ordering / flag set (always run; no `mmdebstrap` needed); (b) a `RunnerSpy` integration test in `bake_rootfs` that asserts the recorded argv across two runs is byte-identical (always runs; no `mmdebstrap` needed); (c) the existing `pytest.mark.slow` real-world bake test stays as the live-runner sanity check.

12. **(coverage — block) Subprocess fence allowlist widening to 5 chokepoint files unwired.** Per S1-07 HARDENED AC-SP-1, `_SUBPROCESS_ALLOWLIST` is a 4-file frozenset (`did/build.py`, `did/network_policy.py`, `firecracker/client.py`, `firecracker/network_policy.py`). `prepare.py` does subprocess calls (`mmdebstrap`, `qemu-img`, `tar`, `curl`); it is the **fifth** chokepoint file. Resolution: AC-FENCE-1..AC-FENCE-3 explicitly widen S1-07's `_SUBPROCESS_ALLOWLIST` by exactly one entry — `Path("src/codegenie/sandbox/firecracker/prepare.py")` — and document the widening in the `prepare.py` module docstring with citation `ADR-0001 + ADR-0013 + this story`. `tests/schema/test_no_subprocess_outside_build_chokepoint.py` is updated to expect 5 entries; planted-positive re-verifies.

13. **(consistency — block) `ALLOWED_BINARIES` widening for `mmdebstrap` / `qemu-img` / `curl` / `tar` unwired.** Per `codegenie.exec.run_external_cli` (Phase 2 ADR-0001 omnibus + S1-06 extension), every binary `prepare` invokes must be in the closed frozenset `ALLOWED_BINARIES`. The draft lists none of these as widening targets. Resolution: AC-BINARIES-1..AC-BINARIES-4 widen `ALLOWED_BINARIES` additively by exactly four entries: `"mmdebstrap"`, `"qemu-img"`, `"tar"`, `"curl"`. A unit test asserts the four are present; planted-positive removes one and asserts `BinaryNotAllowed` raises.

Beyond the block-tier, harden-tier work:

14. **(consistency — harden) `from __future__ import annotations` + sorted `__all__` discipline absent.** Fifth consumer of the pattern. Resolution: AC-MOD-1..AC-MOD-3 (file header conventions for `digests.py`, `prepare.py`, the new `_paths.py` if hoisted here).

15. **(consistency — harden) `_BACKEND_NAME: Final[str] = "firecracker"` + AST single-occurrence walker missing.** S6-01 / S6-02 pay this rent (AC-CANONICAL-1). Resolution: AC-CANONICAL-1..AC-CANONICAL-2 pin the `Final` constant in `prepare.py` + module-purity AST walker asserts the literal `"firecracker"` does NOT appear outside the `Final` declaration.

16. **(coverage — harden) Module-purity AST walker missing.** S3-03 / S6-02 each shipped `test_*_purity.py`. S6-03 ships `tests/sandbox/firecracker/test_prepare_purity.py` asserting: module docstring cites ADR-0013 + ADR-0001 + S1-07; `from __future__ import annotations` first; sorted `__all__`; `subprocess` + `urllib.request` + `pathlib` are the only stdlib I/O modules; no `os.system` / `os.popen` / `shell=True` / `eval` / `exec` / `__import__` / `pickle.loads`; `_default_runner` is the only function whose body contains a `subprocess.run` call (AST walk).

17. **(coverage — harden) LFS-vs-release-asset materialization decision is buried in Notes (line 234) but is operationally load-bearing.** The artifacts are ~50 MB (`vmlinux`) and ~200 MB (`rootfs.ext4`); committing them via LFS adds bandwidth cost to every clone. The draft defers the decision but leaves CI behavior undefined. Resolution: AC-MATERIALIZE-1..AC-MATERIALIZE-3 pin: artifacts are NOT committed to git (no LFS in Phase 5); `prepare` (no-flag) downloads from a pinned GitHub Release URL (configured in `tools/firecracker/sources.yaml`) when artifacts are absent; `--bake` re-bakes from `mmdebstrap` (operator-bump path); `--check` requires artifacts present (`PrepareCheckFailed(reason="sandbox.prepare.check_failed")` if absent with `install_hint="run codegenie sandbox prepare --backend firecracker first"`). `.gitignore` adds `/tools/firecracker/[0-9a-f]*/` so accidental commits are blocked. The CI workflow YAML carries one `codegenie sandbox prepare --backend firecracker --download-only` step before fence tests run.

18. **(coverage — harden) `tools/firecracker/sources.yaml` Pydantic schema not pinned.** Inputs file shape is undefined; the draft mentions `snapshot URL pin, kernel config path, package list` but does not commit to a model. Resolution: AC-INPUTS-1..AC-INPUTS-4 pin `BakeInputs` (Pydantic, `frozen=True`, `extra="forbid"`): `snapshot_url: HttpUrl`, `kernel_url: HttpUrl`, `kernel_blake3: str` (64-hex; the kernel pin is per-source), `package_list: tuple[str, ...]` (alphabetized, deduplicated, validated against a Debian package-name regex), `mmdebstrap_variant: Literal["minbase", "essential", "important", "standard"] = "minbase"`, `source_date_epoch: int = 0`, `release_artifact_url: HttpUrl | None` (the GitHub Release fallback URL per AC-MATERIALIZE-2). A canonical YAML round-trip property test asserts `BakeInputs.from_yaml(BakeInputs.to_yaml(x)) == x`.

19. **(coverage — harden) `tar` / `mmdebstrap` deterministic settings enumerated only in Notes (line 233).** Must be in `_canonical_tar_argv` / `_canonical_mmdebstrap_argv` pure helpers (AC-FCS-7/8). Resolution: AC-DETERMINISM-5 enumerates the exact flag set: `tar --sort=name --mtime=@${SOURCE_DATE_EPOCH} --owner=0 --group=0 --numeric-owner --pax-option='delete=atime,delete=ctime,exthdr.name=%d/PaxHeaders/%f'`; `mmdebstrap --mode=fakechroot --variant=minbase --aptopt='Acquire::Check-Valid-Until "false"' --aptopt='APT::Get::Assume-Yes "true"' --customize-hook='strip /var/cache/apt/archives/*.deb' --hook-helper=...` with env `LC_ALL=C TZ=UTC SOURCE_DATE_EPOCH=0`. Golden-fixture tests pin the rendered argv tuples.

20. **(consistency — harden) Performance budget AC missing.** Arch §Performance envelope says `prepare ≤ 5 min`; `--check` should be ≤ 5 s (matches the fence test). Resolution: AC-PERF-1..AC-PERF-3 pin the budgets: `prepare` (bake) ≤ 360 s on the reference Linux CI runner; `prepare --check` ≤ 5 s on contributor laptop; `prepare --check-rebake` ≤ 600 s. A pytest-perf marker tracks the budget; flake rate ≤ 1% over 30 runs.

21. **(test-quality — harden) Hypothesis property test for `_compute_blake3_streamed` reference-comparison missing.** Resolution: AC-HASH-1..AC-HASH-2 ship a hypothesis property `@given(st.binary(min_size=0, max_size=2**20))` asserting `_compute_blake3_streamed(chunked_reader(bs)) == blake3.blake3(bs).hexdigest()` for arbitrary chunk sizes drawn from `st.integers(min_value=1, max_value=2**20)`. Edge case: `bs == b""` returns the empty-string BLAKE3 hash (known constant).

22. **(test-quality — harden) Goal-AC trace: "single source of truth" is not enforced because the draft retains the string constructor.** AC §The draft AC-4 keeps the string-arg `FirecrackerClient.__init__` as `_internal`-tagged. As long as it exists, the "single source of truth" claim is testimony, not enforcement. Resolution: AC-FACTORY-5 removes the string-arg constructor entirely; tests build via `from_pinned_digests(PinnedDigests(...))`; AST walker asserts no caller outside test code constructs `FirecrackerClient(...)` with string args.

23. **(coverage — harden) Idempotency AC needs strengthening — "produces no filesystem changes" is content-invariance but doesn't pin that the second run **calls no subprocesses** when the artifacts are present and digests match.** The whole point of `prepare`-idempotent is to make it safe to wire into CI as a pre-flight without burning 5 min on every PR. Resolution: AC-IDEMPOTENT-1..AC-IDEMPOTENT-3 strengthen — second `prepare` invocation with matching artifacts results in: zero `runner` calls, zero `downloader` calls, `RunnerSpy.calls == ()`; emits `EVENT_SANDBOX_PREPARE_COMPLETED` with `mode="check"` (auto-promoted from `mode="bake"` since the bake was skipped).

24. **(consistency — harden) Story dependency line lists only S6-01; the actual ancestor chain is far broader.** Resolution: rewritten header `Depends on:` enumerates S1-01 (errors + logging + warning-ID regex + `STARTED/COMPLETED/FAILED` verb convention), S1-02 (`SandboxBackendError` + `extra="forbid"` discipline), S1-06 (allowed-binaries extension this story widens by 4), S1-07 (`tools/digests.yaml` shape + fence-test framework this story upgrades + `_SUBPROCESS_ALLOWLIST` this story widens by 1), S6-01 (FirecrackerClient surface this story EDITs — replaces string-arg constructor with `from_pinned_digests` factory), S6-02 (closed-Literal `reason` cumulative widening this story extends additively by 8).

25. **(consistency — harden) References block is missing line-number anchors for S1-07 AC-DG-* and S6-01 AC-DI-*.** Resolution: References expanded with explicit story-file line anchors so the executor can verify the inherited contract bytes.

26. **(patterns — harden) Anaemic `PinnedDigests` shape risk.** The draft does not pin `PinnedDigests` as a typed shape; the Refactor §195 mentions Pydantic but never as an AC. Resolution: AC-MODEL-1..AC-MODEL-3 pin `PinnedDigests` as a frozen Pydantic model (`frozen=True, slots=True, extra="forbid"`) with fields `firecracker_binary: str` (64-hex, validator), `vmlinux: str` (64-hex), `rootfs: str` (64-hex), `policy_yaml: str` (64-hex). Plus typed `BakeArtifacts(rootfs_digest: str, vmlinux_digest: str, firecracker_binary_digest: str, paths: ArtifactPaths)` and `VerifyOutcome` tagged-union (`Match | Mismatch(differences: tuple[DigestMismatch, ...])`).

27. **(patterns — nit, deferred) `register_digest_pinned_artifact(name, computer, schema)` decorator** — third consumer of digest-pinning family (ADR-0013 policy_yaml, S1-07 placeholders, S6-03 real values + verifier). Rule-of-three reached; the kernel-extract opportunity is real. But the consumer set is closed (the four `sandbox.*` keys are known and stable) and the verifier is the same `_compute_blake3_streamed` for every artifact. Resolution: Notes-for-implementer records the opportunity; defer the decorator to Phase 7+ when (e.g.) `sandbox.distroless_base_image` enters the picture. Hoist `_compute_blake3_streamed` + `_diff_digests` + `_DIGEST_HEX_RE` into `src/codegenie/digests/` (new package) as the shared kernel — this is the **single-namespace** part of the rule-of-three; the **per-artifact** part stays inline until a third sibling exists.

28. **(patterns — nit) `_BACKEND_NAME` echo from S6-01.** Single-line `Final` at module top; AST walker. Mandatory inheritance (fifth consumer).

29. **(patterns — nit) `Final` constant for `_DEFAULT_DIGESTS_YAML_RELATIVE = Path("tools/digests.yaml")` + `Final` for `_DEFAULT_ARTIFACTS_ROOT = Path("tools/firecracker")` at module top.** Defends against inline-string typos.

30. **(coverage — nit) `sources.yaml` itself should be digest-pinned in `tools/digests.yaml#sandbox.sources_yaml`** so the bake-inputs cannot be silently swapped. Resolution: defer — Phase 5 ships exactly four `sandbox.*` keys per S1-07 HARDENED; widening the catalog is a follow-on story (S6-03b or S8-01 amendment). Add a Notes-for-implementer paragraph + a FORWARD-COMPAT anchor at the end of the validation report.

31. **(test-quality — nit) structlog `capture_logs()` convention.** AC-EVT-3 adopts the project-standard idiom.

32. **(consistency — nit) `pyproject.toml` change?** Resolution: AC-DEP-1 confirms no new dependencies (stdlib `subprocess` + stdlib `urllib.request` + `blake3` already in closure + `pydantic` already in closure + `click` already in closure + `pyyaml` already in closure).

33. **(consistency — nit) `tools/firecracker/<rootfs_digest>/` directory naming + collision policy.** Notes line 227 is correct that the digest-prefixed directory makes concurrent old/new versions safe. AC-LAYOUT-1 pins the directory shape and a `gc` candidate (orphan-pruning is S8-01's job; this story leaves the directories in place).

34. **(coverage — nit) Multi-arch (arm64) explicitly Out-of-scope (Phase 5 is x86_64 only).** Good. Keep as-is.

## Findings by critic

### Coverage critic (5 block-tier, 7 harden-tier, 2 nit)

| Severity | Finding | Resolution |
|---|---|---|
| block | YAML shape contradicts S1-07 HARDENED scalar-string contract | AC-YAML-SHAPE-1..-5 + new `tools/firecracker/sources.yaml` |
| block | `--check` mode contract ambiguous (disk-read vs re-bake) | AC-CHECK-MODE-1..-4 |
| block | Subprocess fence allowlist 5th-file widening unwired | AC-FENCE-1..-3 |
| block | `ALLOWED_BINARIES` widening for `mmdebstrap`/`qemu-img`/`curl`/`tar` | AC-BINARIES-1..-4 |
| block | FCS pure-helper split missing | AC-FCS-1..-8 |
| harden | Idempotency AC silent on subprocess-call count | AC-IDEMPOTENT-1..-3 |
| harden | LFS-vs-release-asset decision buried in Notes | AC-MATERIALIZE-1..-3 |
| harden | `BakeInputs` Pydantic schema unpinned | AC-INPUTS-1..-4 |
| harden | Performance budget AC missing | AC-PERF-1..-3 |
| harden | Module-purity AST walker absent | AC-MOD-1..-3 + test file |
| harden | `from __future__ import annotations` + sorted `__all__` | AC-MOD-1..-3 |
| harden | Coverage floor wording missing | AC-COV-1..-2 (95/90 on `digests.py`; 90/80 on `prepare.py`) |
| nit | `tools/firecracker/<rootfs_digest>/` layout + collision policy | AC-LAYOUT-1 |
| nit | Multi-arch arm64 explicit non-goal — already Out-of-scope | Unchanged |

### Test-Quality critic (4 block-tier, 4 harden-tier, 1 nit)

| Severity | Finding | Resolution |
|---|---|---|
| block | Hexagonal DI port for `runner` / `downloader` / `fs` / `clock` missing (5th consumer) | AC-DI-1..-6 |
| block | `test_prepare_check_passes_when_digests_match` is environment-coupled | AC-TEST-1..-4 split (unit + integration + fence) |
| block | Byte-identical determinism test never runs in unit CI (skip-without-mmdebstrap) | AC-DETERMINISM-1..-4 (golden argv + RunnerSpy) |
| block | Tests use `patch("shutil.which")` (unstable boundary) | AC-DI-1..-6 + tests inject `RunnerSpy` |
| harden | Hypothesis property for `_compute_blake3_streamed` reference comparison | AC-HASH-1..-2 |
| harden | Goal "single source of truth" unenforced — string ctor remains | AC-FACTORY-5 removes string ctor |
| harden | `_canonical_tar_argv` / `_canonical_mmdebstrap_argv` flag enumeration | AC-DETERMINISM-5 |
| harden | structlog `capture_logs()` convention | AC-EVT-3 |
| nit | `pyproject.toml` no-change confirmation | AC-DEP-1 |

### Consistency critic (5 block-tier, 5 harden-tier, 2 nit)

| Severity | Finding | Resolution |
|---|---|---|
| block | YAML shape breaks S1-07 HARDENED AC-DG-2 / AC-DG-5/6 | AC-YAML-SHAPE-1..-5 |
| block | `from_digests_yaml` classmethod undoes S6-01 DI-port discipline | AC-FACTORY-1..-4 split |
| block | Default `Path("tools/digests.yaml")` is cwd-brittle | AC-PATH-1..-3 |
| block | Event names violate S1-01 STARTED/COMPLETED/FAILED canonical-table | AC-EVT-1..-3 |
| block | Closed-Literal `SandboxBackendError.reason` widening absent | AC-ERR-1..-6 (+8 members) |
| harden | Story `Depends on:` line under-enumerates ancestors | Header rewritten |
| harden | References block missing line-number anchors | References expanded |
| harden | `_BACKEND_NAME` Final constant + AST single-occurrence walker | AC-CANONICAL-1..-2 |
| harden | Warning IDs / structured error fields unpinned | AC-WID-1..-4 |
| harden | `sources.yaml` digest-pinning candidate (closed-set widening) | Notes + FORWARD-COMPAT anchor |
| nit | `pyproject.toml` no-change | AC-DEP-1 |
| nit | `Final` constants for default paths | AC-CANONICAL-3..-4 |

### Design-Patterns critic (3 block-tier, 4 harden-tier, 3 nit)

| Severity | Finding | Resolution |
|---|---|---|
| block | Hexagonal DI port (5th consumer; rule-of-three crossed three times over) | AC-DI-1..-6 |
| block | Functional core / imperative shell split (5th consumer) | AC-FCS-1..-8 |
| block | Closed-Literal `reason` discriminator | AC-ERR-1..-6 |
| harden | Anaemic `PinnedDigests` / `BakeArtifacts` / `VerifyOutcome` shapes | AC-MODEL-1..-3 (Pydantic frozen + tagged-union for verify outcome) |
| harden | `_BACKEND_NAME` Final + AST walker (S6-01/S6-02 inheritance) | AC-CANONICAL-1..-2 |
| harden | Module-purity AST walker missing | AC-PURE-1..-8 |
| harden | `_wrap_subprocess_error(err, *, reason)` adapter pattern | AC-FCS-9 |
| nit | `register_digest_pinned_artifact(...)` registry decorator — RoT reached BUT consumer set closed | Notes — extract kernel (`_compute_blake3_streamed` + `_diff_digests`) to `src/codegenie/digests/`; defer the decorator until 5th distinct artifact (Phase 7+) |
| nit | `_DEFAULT_*` `Final` constants for path defaults | AC-CANONICAL-3..-4 |
| nit | Hoist `find_project_root()` to `_paths.py` (S1-07 has a candidate seam at `_walkers.py::ROOT`) | AC-PATH-1 |

## Conflict resolutions

- **Coverage (want `tools/firecracker/sources.yaml` digest-pinned) vs Consistency (S1-07 HARDENED pins exactly four `sandbox.*` keys).** Widening the digest-pin catalog now would re-open S1-07 AC-DG-2 (closed-keys list). Resolution: **defer**. Notes-for-implementer + FORWARD-COMPAT anchor record the opportunity for a follow-on story.

- **Design-Patterns (`register_digest_pinned_artifact(...)` registry — rule-of-three reached) vs Rule 2 (consumer set is closed at four; three of them already shipped; one more in this story).** A registry for a closed set is anti-Rule-2. The **kernel-extract** part (shared `_compute_blake3_streamed` + `_diff_digests` + `_DIGEST_HEX_RE` in a `src/codegenie/digests/` package) is the half that pays the rent — the per-artifact verifier stays inline. Resolution: extract the kernel (mandatory); skip the decorator.

- **Coverage (want `--check` to re-bake by default) vs CI cost (re-bake is 5 min/run × every PR ≈ phase-blocker).** Re-bake is the operator-bump verification; disk-read is the PR-time invariant. Resolution: two flags (`--check` = read-from-disk; `--check-rebake` = re-bake to tmpdir). PR-time uses `--check`; the operator-bump workflow uses `--check-rebake` once.

- **Test-Quality (want determinism property always-run) vs Reality (`mmdebstrap` not on contributor laptops or default CI runners).** Resolution: **three-layer test pyramid** — pure-helper golden argv (always runs) → RunnerSpy integration (always runs; argv-equality across two `bake_rootfs` calls) → real `mmdebstrap` skip-gated test (CI-only on a dedicated runner). The first two prove the logic; the third proves the world.

- **Consistency (want string `FirecrackerClient.__init__` removed entirely) vs Surgical-edit (S6-01 HARDENED kept it `_internal`-tagged so tests don't churn).** S6-01's HARDENED constructor already takes `digests` as constructor args, plus the DI ports — the path forward is to **rename** the constructor to `_FirecrackerClient__init__` (Python name-mangled, signals internal) and route every call site through `from_pinned_digests`. Resolution: **remove the string-arg constructor signature** (rename + delete the public `(firecracker_path, vmlinux_digest, rootfs_digest)` shape); tests build via `from_pinned_digests(PinnedDigests(...))`. Where S6-01 HARDENED tests already use `from_pinned_digests`-equivalent factories, no churn; where they use the string constructor, they get migrated in the same PR (counted as an AC-CLIENT-EDIT-* item).

- **Coverage (want `prepare` run-id-keyed for parallelism) vs Reality (`prepare` is operator-one-shot; no `run_id` involved).** Resolution: no `run_id` needed. `prepare` is single-threaded; a `--out-dir` flag (defaults to `find_project_root() / "tools/firecracker"`) lets operators bake into a tmpdir for the `--check-rebake` flow.

## Edits applied to the story

**Header / status:**
- `Status: Ready` → `Status: Ready (HARDENED 2026-05-25)`
- `Depends on: S6-01` → `Depends on: S1-01 (errors + logging + warning-ID regex + STARTED/COMPLETED/FAILED verb convention), S1-02 (SandboxBackendError + extra="forbid"), S1-06 HARDENED (ALLOWED_BINARIES this story widens by 4), S1-07 HARDENED (tools/digests.yaml shape this story preserves + _SUBPROCESS_ALLOWLIST this story widens by 1 + fence-test framework this story upgrades from presence-only to byte-validation), S6-01 HARDENED (FirecrackerClient surface this story EDITs — replaces string-arg ctor with from_pinned_digests factory; widens reason Literal by 8), S6-02 HARDENED (closed-Literal reason cumulative-additive widening this story extends)`
- `ADRs honored:` annotated with the aspect each enforces.

**Validation notes (new, ~85 lines):** Thirteen block-tier + thirteen harden/nit findings summarized; rationale for every AC change; pattern-lineage callouts (ADR-0013 → S1-07 → S6-03 third consumer of digest-pinning family; S3-01/S3-02/S3-03/S6-01/S6-02 → S6-03 fifth consumer of FCS+DI+closed-Literal+canonical-Final+purity-walker stack).

**Context (light edit):** Names this story as the third digest-pinning consumer (kernel extract mandatory) AND fifth FCS+DI consumer (mandatory pattern inheritance, rule-of-three crossed three times over).

**References (expanded):** Added explicit line-number anchors into S1-07 AC-DG-*, S6-01 AC-DI-*, S6-02 AC-FCS-*; added prior-HARDENED-report references (S1-07 / S6-01 / S6-02); added CLAUDE.md anchors for warning-ID regex / FCS / Newtype identifiers / Extension by addition / Open/Closed Principle (registry-for-closed-set anti-pattern).

**Goal (light edit):** Tightened "single source of truth for Firecracker artifact identity" → "single source of truth for Firecracker artifact identity (string-arg constructor removed); deterministic bake-from-inputs reproducible byte-identically across machines; `--check` (disk-read) is the PR-time fence and `--check-rebake` (tmp-bake) is the operator-bump verification; shared digest-loading kernel (`src/codegenie/digests/`) extracted as the third consumer of ADR-0013."

**Acceptance criteria (full rewrite from 11 unnumbered checkboxes to ~70 numbered ACs across 16 sections):**
- §A — Public surface + module discipline (AC-MOD-1..-3 + AC-CANONICAL-1..-4)
- §B — `tools/digests.yaml` shape preservation (AC-YAML-SHAPE-1..-5) + new `tools/firecracker/sources.yaml` schema (AC-INPUTS-1..-4)
- §C — `PinnedDigests` / `BakeArtifacts` / `VerifyOutcome` models (AC-MODEL-1..-3)
- §D — Hexagonal DI ports (AC-DI-1..-6)
- §E — Functional core / imperative shell (AC-FCS-1..-9)
- §F — `bake_rootfs` lifecycle (AC-BAKE-1..-4)
- §G — `verify_against_digests` (AC-VERIFY-1..-3)
- §H — CLI flags + project-root resolution (AC-CHECK-MODE-1..-4 + AC-PATH-1..-3)
- §I — Errors + closed-Literal `reason` (AC-ERR-1..-6)
- §J — Events (AC-EVT-1..-3)
- §K — Idempotency (AC-IDEMPOTENT-1..-3)
- §L — Determinism (AC-DETERMINISM-1..-5)
- §M — Materialization (LFS vs release-asset) (AC-MATERIALIZE-1..-3)
- §N — Fence widenings (AC-FENCE-1..-3 + AC-BINARIES-1..-4 + AC-PURE-1..-8)
- §O — FirecrackerClient EDITs (AC-FACTORY-1..-5 + AC-CLIENT-EDIT-1..-3)
- §P — Performance + Coverage (AC-PERF-1..-3 + AC-COV-1..-2) + Deps (AC-DEP-1)

**Implementation outline (expanded 7→13 steps):** Each step numbered, error-paths enumerated, references the AC numbers; renumbered to fit the new ordering (kernel extract before consumer wiring).

**TDD plan (expanded from 2 to 6 test files):**
- `tests/sandbox/firecracker/test_prepare_core.py` — `bake_rootfs` + `verify_against_digests` end-to-end with `RunnerSpy` + `DownloaderSpy` + `FsSpy` + frozen `clock`
- `tests/sandbox/firecracker/test_prepare_helpers.py` — pure-helper unit tests (`_compute_blake3_streamed` hypothesis property, `_canonical_tar_argv` / `_canonical_mmdebstrap_argv` golden fixtures, `_artifact_paths_for`, `_diff_digests`)
- `tests/sandbox/firecracker/test_prepare_lifecycle.py` — idempotency + check-mode + check-rebake-mode + partial-bake rollback
- `tests/sandbox/firecracker/test_prepare_errors.py` — closed-Literal `reason` set, error message shape, every `Prepare*Error` raise path
- `tests/sandbox/firecracker/test_prepare_purity.py` — module-purity AST walker
- `tests/schema/test_digests_yaml.py` (UPGRADE) — presence-only → byte-validation; planted-positive flips a digest byte and asserts the fence fires
- `tests/integration/sandbox/test_prepare_real_mmdebstrap.py` (CI-only) — `pytest.mark.slow + skipif(not _has_mmdebstrap())` — real-world bake equality
- `tests/cli/test_sandbox_prepare_cli.py` — Click-runner unit tests (`--check`, `--check-rebake`, `--bake`, `--download-only`, missing-tool, wrong-backend)
- `tests/sandbox/firecracker/test_from_pinned_digests.py` — `FirecrackerClient.from_pinned_digests` factory + DI-port forwarding

**Files to touch (expanded 12→17 entries):** Adds `src/codegenie/digests/__init__.py` (new package — kernel extract: `compute_blake3_streamed`, `diff_digests`, `_DIGEST_HEX_RE`, `PinnedArtifact`); `src/codegenie/_paths.py` (new — `find_project_root()` hoisted from S1-07 `_walkers.py::ROOT`); `src/codegenie/sandbox/logging.py` (EDIT — three new event constants alphabetized into sorted `__all__`); `src/codegenie/sandbox/errors.py` (EDIT — widen `reason` Literal by 8 + add 5 `Prepare*Error` subclasses); `src/codegenie/sandbox/firecracker/client.py` (EDIT — replace string-arg ctor with `from_pinned_digests` factory; consume `digests/` kernel); `src/codegenie/exec/__init__.py` (EDIT — widen `ALLOWED_BINARIES` by 4); `tests/schema/test_no_subprocess_outside_build_chokepoint.py` (EDIT — `_SUBPROCESS_ALLOWLIST` 4 → 5); `tools/firecracker/sources.yaml` (new — `BakeInputs`-typed). Removes `tools/firecracker/inputs.yaml` from the draft (replaced by `sources.yaml`).

**Out of scope (clarified):** The other `codegenie sandbox` subcommands → S8-01; auto-detect → S6-04; KVM-gated integration smoke + weekly cron → S6-05; rebuild cadence policy → operational, Phase 14 (Open Q1); multi-architecture rootfs (arm64) → Phase 5 is x86_64 only; `register_digest_pinned_artifact(...)` decorator → Phase 7+; widening `tools/digests.yaml` closed-keys set to include `sandbox.sources_yaml` → follow-on story; LFS adoption → explicit Phase-5 non-goal (release-asset pull is the materialization path).

**Notes for the implementer (expanded ~9→24 paragraphs):** Kernel-extract opportunity for `src/codegenie/digests/` (third consumer of digest-pinning); `--check` vs `--check-rebake` semantic split (PR-time vs operator-bump); release-asset materialization rationale (LFS deferred); `mmdebstrap` vs `debootstrap` (do not substitute); BLAKE3 canonical hash project-wide; `_canonical_tar_argv` / `_canonical_mmdebstrap_argv` flag rationale; `tar` `--pax-option` PAX-header deletion for reproducibility; `SOURCE_DATE_EPOCH` semantics; deterministic file ordering; subprocess fence is **widened by exactly one entry** (`prepare.py`) — keep the diff tight; `ALLOWED_BINARIES` widened by exactly four entries; pattern lineage callouts (S6-01 host client + S6-02 network policy + S1-07 fence framework); FORWARD-COMPAT anchor for S6-04 / S6-05 / S8-01 / Phase 7+.

## Pattern lineage anchors

| Phase-5 ancestor | Pattern inherited | This story's AC |
|---|---|---|
| ADR-0013 (production ADR-0021) | Digest-pinned codegenie-owned artifact | AC-YAML-SHAPE-1..-5 + AC-MATERIALIZE-1..-3 + kernel-extract |
| S1-01 HARDENED | Warning-ID namespace regex; `STARTED/COMPLETED/FAILED` event-verb canonical-table | AC-WID-1..-4 + AC-EVT-1..-3 |
| S1-02 HARDENED | `SandboxBackendError` + `extra="forbid"` + frozen Pydantic | AC-ERR-1..-6 + AC-MODEL-1..-3 |
| S1-06 HARDENED | `ALLOWED_BINARIES` extension pattern | AC-BINARIES-1..-4 |
| S1-07 HARDENED | `tools/digests.yaml` scalar-string shape + `_SUBPROCESS_ALLOWLIST` 4-file frozenset + fence-test framework + planted-positive convention | AC-YAML-SHAPE-1..-5 + AC-FENCE-1..-3 + AC-VERIFY-1..-3 (upgrade) |
| S3-01 HARDENED | Closed-Literal `reason` discriminator | AC-ERR-1..-6 |
| S3-02 HARDENED | Hexagonal DI port pattern (`docker_factory`) — 2nd consumer | AC-DI-1..-6 |
| S3-03 HARDENED | FCS pure-helper + impure-shell split — 2nd consumer | AC-FCS-1..-9 |
| S6-01 HARDENED | `FirecrackerClient` surface this story EDITs additively — `from_digests_yaml` factory routes through `from_pinned_digests`; widens `reason` Literal by 8; `_BACKEND_NAME` Final convention | AC-FACTORY-1..-5 + AC-CLIENT-EDIT-1..-3 + AC-ERR-1..-6 + AC-CANONICAL-1..-4 |
| S6-02 HARDENED | `network_policy.py` sibling — cumulative `reason` widening monotone-additive; subprocess fence consume-not-widen discipline; module-purity AST walker template | AC-ERR-1..-6 + AC-PURE-1..-8 |

## Forward-compat anchor (for downstream stories)

- **S6-04 (auto-detect):** `prepare --check` exit-code 0 is what `auto_detect()` queries to confirm Firecracker is locally ready before routing to `FirecrackerClient`. Do NOT re-implement the digest check in S6-04; call `verify_against_digests(...)`. The new `sandbox.prepare.tool_missing` / `sandbox.prepare.check_failed` reasons are what `auto_detect()` keys on to fall back to DinD.
- **S6-05 (KVM smoke + weekly cron):** the `prepare --download-only` flag this story ships is the CI workflow's pre-flight step; the weekly cron also runs `prepare --check-rebake` to detect snapshot-URL drift before the smoke fires.
- **S7-* (perf gates):** `prepare` performance budgets land in `tests/perf/test_prepare_latency.py` per AC-PERF-1..-3.
- **S8-01 (`sandbox gc`):** orphan-pruning of `tools/firecracker/<old_rootfs_digest>/` directories (left behind after a digest bump) is owned by `sandbox gc`; this story leaves the directories in place and emits a `sandbox.prepare.completed` event with both old and new digests for `gc` to consume.
- **Phase 7+ fourth digest-pinned artifact (e.g., `sandbox.distroless_base_image`):** widens `tools/digests.yaml#sandbox.*` closed-keys set by one entry; widens `_BANNED_LLM_IMPORTS` test set if needed; introduces the fourth consumer of `src/codegenie/digests/` — at that point the `register_digest_pinned_artifact(...)` decorator becomes the rule-of-three threshold for the registry pattern (currently deferred). Add a `tools/digests.yaml#sandbox.sources_yaml` widening as a follow-on story when a second `sources.yaml`-shaped catalog enters scope.

## Cross-cutting consumers (where the patterns this story enforces are read downstream)

- **Phase 7 (distroless migration):** `tools/digests.yaml` widens with a Chainguard image-digest key; `prepare` widens with a `--backend chainguard` mode; the `digests/` kernel and `verify_against_digests` are reused.
- **Phase 8 (cost ledger):** `Prepare*Error.reason` rows feed the per-failure cost-attribution table; `(error_class, reason)` is the load-bearing key.
- **Phase 11 (evidence bundle):** rootfs/vmlinux/firecracker-binary digests are bundle-included as the canonical "what ran" evidence for an audited remediation.
- **Phase 13 (multi-language):** language-specific runtime artifacts (e.g., Python wheel-cache digests) extend the digest-pinning catalog via the same `src/codegenie/digests/` kernel.
