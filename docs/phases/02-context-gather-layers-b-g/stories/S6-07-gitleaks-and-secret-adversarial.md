# Story S6-07 — `Gitleaks` scanner + `secret_in_source` adversarial

**Step:** Step 6 — Ship Layer D + E + G probes (skills, conventions, ADRs, ownership, scanners)
**Status:** Done — GREEN 2026-05-18 (phase-story-executor; see [`_attempts/S6-07.md`](_attempts/S6-07.md) for the per-AC evidence table + kernel-drift fixes + gate log)
**Effort:** M
**Depends on:** S6-06 (three sibling Layer G scanners — `gitleaks` is the *fourth* and final scanner; landing it in its own story makes the no-shared-`ScannerRunner` discipline visible in the PR queue), S3-03 (writer signature tightened to `RedactedSlice`; envelope-level `_seam_redact_envelope` is the composition pass at the writer chokepoint)
**ADRs honored:** 02-ADR-0001 (`gitleaks` added to `ALLOWED_BINARIES`), **02-ADR-0005** (no plaintext persistence — this story is the load-bearing test of that ADR), **02-ADR-0010** (`RedactedSlice` smart constructor at writer boundary — the test confirms a caller cannot bypass the redactor)
**Phase-2 LOAD-BEARING ADVERSARIAL:** [`README.md` Step 6 table S6-07](README.md) — "gitleaks finds a seeded secret; `SecretRedactor` replaces it in `repo-context.yaml` + every raw artifact + cache blob + audit anchor. Plaintext in **zero** persisted files."

## Validation notes (2026-05-17 — phase-story-validator)

Verdict: **HARDENED**. The story's *intent* — a load-bearing adversarial test of ADR-0005's zero-plaintext-persistence commitment, the fourth Layer G scanner, and structural reinforcement of ADR-0010's writer-boundary smart constructor — traces cleanly to `phase-arch-design.md §"Goals" G5`, the §"Gap 4 / Gap 5" closures, and `final-design.md §"Failure modes & recovery" row 7`. But the draft's *prescriptions* referenced the pre-Phase-2-evolution kernel shape and a fingerprint format that does not match what S3-01 actually ships. Twelve BLOCK-severity inconsistencies + four Coverage gaps + one critical Design-pattern decision (raw-artifact redaction policy) closed below.

### Block-severity Consistency fixes (kernel-drift, identical in shape to the S6-06 family of fixes)

1. **B1 — Probe ABC contract drift.** Draft prescribed `_run(self, ctx) -> ProbeOutput` (single-arg, synchronous). Frozen Phase-0 ABC (`src/codegenie/probes/base.py:74-96`) requires `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` (two-arg, async). **Fix:** Implementation outline + TDD plan rewritten to use `async def run(self, repo, ctx)`; ACs reworded; the prescribed code block re-emitted with the correct signature.

2. **B2 — Dual-form identity drift.** Draft used `probe_id = ProbeId("gitleaks")` (class attribute). Repo precedent (S5-04 / S6-05 / S6-06) and AC-N1 from S6-06 pin the dual-form: `name: str = "gitleaks"` class attribute (the kernel-introspected identity, ABC contract) + module-level `_PROBE_ID: Final[ProbeId] = ProbeId("gitleaks")` constant (the value passed to `run_external_cli(probe_name=_PROBE_ID, ...)`). **Fix:** AC-3 + AC-N1 (new) pin both forms; the prescribed code re-emits with the dual form.

3. **B3 — Import path drift.** Draft imported `from codegenie.ids import ProbeId` and `from codegenie.exec import ProcessResult, ToolMissingError, run_external_cli`. Master ships `from codegenie.types.identifiers import ProbeId` and `from codegenie.errors import ToolMissingError`. **Fix:** All `from codegenie.ids import ProbeId` → `from codegenie.types.identifiers import ProbeId`; all `from codegenie.exec import ToolMissingError` → `from codegenie.errors import ToolMissingError`.

4. **B4 — `run_external_cli` signature drift.** Draft used `run_external_cli("gitleaks", [...], timeout_seconds=30)` (sync, binary string first, `timeout_seconds=` kwarg). Master (`src/codegenie/exec/__init__.py:485-599`, per S1-07) ships `async def run_external_cli(probe_name: ProbeId, argv: list[str], *, cwd: Path, timeout_s: float, ...) -> ProcessResult` (async, `ProbeId` first-positional, `cwd=`/`timeout_s=` kwargs). **Fix:** AC-4 and the prescribed code rewritten — `await run_external_cli(_PROBE_ID, [..., "--no-banner", ..., "--no-git", ...], cwd=repo.root, timeout_s=30.0)`. `argv[0]` is the binary string `"gitleaks"` (allowlist-checked by `run_external_cli`); the first positional is `_PROBE_ID`.

5. **B5 — `ProbeOutput` constructor drift.** Draft used `ProbeOutput(probe_id=..., confidence=..., schema_slice=..., errors=[])` (4 wrong kwargs: `probe_id=` does not exist on the model; the model is six-field). Master ships `ProbeOutput(schema_slice, raw_artifacts, confidence, duration_ms, warnings, errors)`. **Fix:** `_wrap` helper rewritten — `ProbeOutput(schema_slice=slice_.model_dump(mode="json"), raw_artifacts=raw_artifacts, confidence=confidence, duration_ms=..., warnings=[], errors=[])`. The probe identity flows through `name: str` (ABC class attribute), not a constructor kwarg.

6. **B6 — `applies_to_*` type drift.** Draft used `applies_to_tasks: tuple[str, ...] = ("*",)`. ABC requires `applies_to_tasks: list[str] = ["*"]` (and `applies_to_languages` likewise). **Fix:** AC-3 reworded; prescribed code uses `list[str]`.

7. **B7 — Test fixture phantom.** Draft used `ProbeContext.for_test(repo_root=Path(...))` — this constructor does not exist. Repo precedent (sbom/cve conftest): module-local `_make_repo(tmp_path)` / `_make_ctx(tmp_path)` fixtures returning `RepoSnapshot` and `ProbeContext` instances. **Fix:** TDD plan rewritten with the conftest fixtures; `tests/unit/probes/layer_g/conftest.py` row added to Files-to-touch.

8. **B8 — `pytest-subprocess` (`fp` fixture) is not a dev dep.** Draft used `def test_...(fp)` with `fp.register([...], stdout=..., returncode=...)`. `pyproject.toml`'s `[project.optional-dependencies].dev` does NOT include `pytest-subprocess` (verified during the S6-06 hardening pass). Repo's 10+ call-site precedent (`tests/unit/probes/layer_c/test_sbom.py:140`, `test_cve.py:141-363`) is `monkeypatch.setattr(<module>, "run_external_cli", _spy)` where `_spy` is an `AsyncMock` (or plain coroutine) returning `ProcessResult(returncode, stdout, stderr)` and capturing positional/keyword args for argv assertions. **Fix:** TDD plan rewritten to use the `monkeypatch.setattr` pattern.

9. **B9 — Fingerprint format mismatch (16 hex vs 8 hex).** Draft computed `blake3(SEED.encode()).hexdigest()[:16]` (16 hex chars = 8 bytes) and asserted `<REDACTED:fingerprint={16hex}>` in artifacts. S3-01 AC-13 + AC-14 (the *source of truth* — this story is downstream of S3-01) defines fingerprint format as **first 8 hex characters** of `codegenie.hashing.content_hash_bytes(cleartext.encode("utf-8")).removeprefix("blake3:")`. The redactor produces `<REDACTED:fingerprint=<8hex>>`. The 16-char marker would NEVER appear in the artifact and AC-13 would fail at every gather. **Fix:** AC-5, AC-13, the `GitleaksFinding` model, the `_parse` body, and the test expectation all rewritten to 8 hex chars via the canonical `content_hash_bytes` chokepoint helper (NOT raw `blake3.blake3` — see B10).

10. **B10 — Fingerprint helper bypasses the Phase-0 hashing chokepoint.** Draft imported `from blake3 import blake3` and called `blake3(...).hexdigest()[:16]` directly. Phase-0 ADR-0001 declares `codegenie.hashing.content_hash_bytes` as the BLAKE3-of-bytes chokepoint (returns prefix-tagged `"blake3:<64hex>"`); S3-01 builds the fingerprint by stripping the prefix and slicing `[:8]`. The probe must use the same helper — otherwise a future change to the hashing chokepoint (e.g., a keyed mode or salt) silently desynchronizes the probe's fingerprints from the redactor's markers and AC-13 silently rots. **Fix:** AC-5 + AC-13 + prescribed code import the canonical helper. Specifically: `from codegenie.hashing import content_hash_bytes` and `_fingerprint(b: bytes) -> str` returns `content_hash_bytes(b).removeprefix("blake3:")[:8]`. The `blake3` PyPI package is not imported in `gitleaks.py`; the chokepoint is single.

11. **B11 — Audit-anchor path drift.** Draft test walks `.codegenie/runs/*.json`. CLAUDE.md (load-bearing) and the Phase-0 audit-writer pin the canonical path as `.codegenie/context/runs/*.json` (audit anchors land *under* `.codegenie/context/`, NOT a sibling). AC-15 would fail to find any anchor and the test would either error (no `runs_dir`) or pass vacuously. **Fix:** AC-15 + the audit-anchor test rewritten to walk `.codegenie/context/runs/*.json`.

12. **B12 — CLI invocation drift.** Draft uses `subprocess.run(["codegenie", "gather", ...], check=True)`. The `codegenie` console-script may not be on PATH in CI / fresh venvs; the canonical Phase-0 e2e form (per the Step-4 fixture suite) is `subprocess.run([sys.executable, "-m", "codegenie", "gather", str(repo)], check=True)`. Same shape used by S3-03 AC-2 (mypy fixture) and S4-02. **Fix:** TDD plan rewritten — every `subprocess.run([...])` uses `[sys.executable, "-m", "codegenie", ...]`.

### Coverage hardens

13. **C1 — `GitleaksSlice` is anaemic.** Draft's slice carries only `outcome` + `findings_count` — losing the per-finding rich data (`rule_id`, `file`, `line`, `description`, `match_fingerprint`). AC-12 requires inspecting the gitleaks raw artifact to find an AWS rule, but the *slice* (which feeds `repo-context.yaml` and downstream Phase-3 consumers) drops this data. Per S6-06 AC-9, **per-scanner rich `Finding` lives on the SLICE as `findings_detail`**, with `ScannerRan.findings: list[Finding]` staying as the empty `list[Finding]` from S5-01 (the closed sum's contract). **Fix:** AC-6 hardened — `GitleaksSlice` carries `outcome: ScannerOutcome, findings_count: int, findings_detail: list[GitleaksFinding]`. AC-12 reworded to inspect the slice's `findings_detail` (post-merge into the envelope) for the AWS rule, NOT the raw artifact (which may be absent per RP1).

14. **C2 — Raw-artifact persistence policy unpinned (CRITICAL — ADR-0005 vs S6-06 AC-W1 tension).** S6-06 AC-W1 mandates a two-file write split for every Layer G scanner: `<raw_dir>/<scanner>.json` (typed slice) AND `<raw_dir>/<scanner>-raw.json` (raw scanner stdout bytes for audit and re-parse). Gitleaks' raw stdout JSON contains the cleartext in the `"Secret"` field (`[{..., "Secret": "AKIA1234567890ABCDEF"}]`). The envelope-level `_seam_redact_envelope` (S3-03) walks the **dict envelope**, not `raw_artifacts: list[tuple[str, bytes]]`. If the probe writes `gitleaks-raw.json` verbatim, ADR-0005's "plaintext in zero persisted files" is **broken** — AC-10's walk catches it but only at adversarial-test time; the structural failure is in the persistence pathway, not the assertion.

    **Decision:** **Gitleaks is a load-bearing carve-out from S6-06 AC-W1.** The probe MUST redact the `"Secret"` field in its raw bytes BEFORE adding to `ProbeOutput.raw_artifacts`. The substitution is byte-level: for each finding, replace the literal cleartext byte-sequence with `<REDACTED:fingerprint=<8hex>>` (matching the envelope-level redactor's marker format). The probe knows the cleartext (it just computed the fingerprint for each finding); a single-pass `bytes.replace` per finding closes the leak at source. **Rationale:** Structural defense — make the failure mode impossible by construction. The Writer never sees gitleaks cleartext; a "log the raw_artifacts for debugging" PR cannot accidentally log cleartext because the bytes are already redacted by the time they leave the probe. This is the toolkit's "make illegal states unrepresentable" pattern applied at the I/O boundary one rung *earlier* than ADR-0010 (which makes it unrepresentable at the writer; this carve-out makes it unrepresentable at the probe).

    **Fix:** AC-RP1 (new) — pins the carve-out. AC-RP2 (new) — mutation test: the raw bytes after `_run` returns contain zero occurrences of any finding's cleartext byte sequence (verified by re-grepping `ProbeOutput.raw_artifacts[0][1]` against the seeded byte string before any Writer touches the bytes).

15. **C3 — Eight ABC class attributes not pinned.** Mirror S6-06 AC-B1 — every Layer G probe must pin all eight: `name`, `version`, `layer`, `tier`, `applies_to_tasks`, `applies_to_languages`, `requires`, `declared_inputs`, `timeout_seconds`. Draft pins ~5; a `layer = "F"` typo would slip past `mypy --strict`. **Fix:** AC-B1 (new) — all eight asserted per-probe.

16. **C4 — `@register_probe` kwargs incomplete.** Draft uses `@register_probe(heaviness="medium")`. S6-06 AC-3 + 02-ADR-0003 Option D pin the kwargs to `heaviness` + `runs_last` only (and explicitly NOT `requires=`). The `runs_last=False` for gitleaks (Layer G scanners are not run-last per the design table) is implied but unpinned — a regression that silently flips to `True` would break the coordinator's dispatch order. **Fix:** AC-3 hardened — `@register_probe(heaviness="medium", runs_last=False)`. AC-R1 (new) — registry membership smoke: `_PROBE_REGISTRY["gitleaks"].heaviness == "medium"`, `.runs_last is False`; no `requires` kwarg on the registry entry (defensive — `@register_probe(requires=...)` must fail at import per 02-ADR-0003 Option D).

17. **C5 — `declared_inputs` + `cache_strategy` unspecified.** Gitleaks walks the working tree; without explicit `declared_inputs`, the coordinator's snapshot pass cannot derive a stable cache key. **Fix:** AC-B1 pins `declared_inputs: list[str] = ["**/*"]` (working-tree-broad — gitleaks runs over the whole tree) and `cache_strategy: Literal["content"] = "content"` (default; pinned explicitly so a future contributor doesn't quietly flip to `"none"`).

18. **C6 — Timeout path missing.** Mirror S6-06 AC-T1 — when `run_external_cli` raises `ProbeTimeoutError` (`codegenie.errors`), the probe must catch and emit `ScannerFailed(exit_code=124, stderr_tail="gitleaks.timeout")`. A timeout that escapes past the probe boundary breaks the coordinator's per-probe failure isolation. **Fix:** AC-T1 (new) — explicit timeout-path test.

19. **C7 — Exit-code carve-out semantics + non-zero exit not adversarial-tested.** Draft's argv uses `--exit-code 0` to override gitleaks' default-exit-1-on-findings (good — simpler classifier). But what if gitleaks ITSELF crashes (exit ≥ 2 — scan error)? AC-4 covers the happy path; no AC covers the failure path. **Fix:** AC-EX (new) — exit_code ≥ 2 → `ScannerFailed(exit_code=N, stderr_tail=...)` mirror AC-11 of S6-06.

20. **C8 — Malformed JSON paths (missing required keys) not covered.** Draft handles JSON-decode error → `ScannerFailed(reason="invalid_json")`. But what about valid JSON with missing required keys (e.g., a future gitleaks version drops `RuleID`)? **Fix:** AC-12b (new) — JSON missing `RuleID` / `File` / `StartLine` / `Secret` → `ScannerFailed(reason="invalid_json", stderr_tail="<gitleaks.parse_error: ...>")`.

21. **C9 — Argv pinning (negative + positive captures).** S6-06 AC-5 / AC-6 / AC-7 mandate captured-argv spy testing — every flag (`--no-banner`, `--no-git`, `--exit-code 0`, `--report-format=json`, `--report-path=-`) and its position is asserted. Draft's `test_gitleaks_argv_includes_no_banner_and_no_git` covers some but not all and uses `fp.register` (B8). **Fix:** TDD plan rewritten — single `test_argv_pins_all_hardening_flags` using `monkeypatch.setattr` with `_spy = AsyncMock` that captures the call; assertions enumerate every flag.

22. **C10 — Fixture README contains literal seed (self-contamination).** AC-9 lists `tests/adv/phase02/fixtures/secret_in_source/README.md` "documenting the seed pattern" — but if the README contains the literal `AKIA1234567890ABCDEF`, gitleaks' working-tree scan picks it up AND the redactor finds it in three files now (`src/config.ts`, `docs/internal-notes.md`, `README.md`). The fixture README must document the seed via a *placeholder* (e.g., `AKIA<sixteen-uppercase-alphanumerics>`) — never the literal. **Fix:** AC-9 reworded — the README documents the pattern via placeholder syntax; literal seed lives ONLY in `src/config.ts` (source code finding) and `docs/internal-notes.md` (prose / non-source path — exercises the entropy fallback walk).

### Design-pattern notes (Notes-for-implementer)

23. **DP1 — `Fingerprint` newtype rule-of-three threshold REACHED.** Production ADR-0033 §3 names primitive obsession on cross-module identifiers. S3-01 (validation #11), S3-02 (validation #12), S3-03 (validation #19) all deferred `Fingerprint = NewType("Fingerprint", str)` to S8-02's CLI-summary cross-cutting story. S6-07 is the *fourth* consumer of 8-hex fingerprints (probe → slice → writer → CLI summary → gitleaks finding model). The rule-of-three threshold is now crossed in earnest. **Decision:** Still defer to S8-02 — S6-07 lands the consumer; S8-02 lands the type concurrently. Pinned in Notes-for-implementer §"Deferred primitives".

24. **DP2 — `_parse` return shape uses Result-as-`tuple | str`.** Draft returns `tuple[tuple[GitleaksFinding, ...], int] | str` where `str` is the failure tail. This is a non-idiomatic Result type. Per S6-06's AC-12 + the closed `Literal["invalid_json", "sbom_artifact_missing"] | None` reason set (ADR-0006), the cleaner shape is `tuple[tuple[GitleaksFinding, ...], int] | ScannerFailed`. The caller pattern-matches on `isinstance(parsed, ScannerFailed)` instead of `isinstance(parsed, str)` — `mypy --strict --warn-unreachable` enforces exhaustiveness. **Fix:** prescribed `_parse` rewritten to return `tuple[...] | ScannerFailed`; `_run` pattern-matches.

25. **DP3 — Pure / impure split holds at module level.** The `_parse` helper is pure (bytes → typed result). `_fingerprint(b: bytes) -> str` is pure (delegates to `content_hash_bytes`). The byte-substitution pass `_redact_raw_bytes(raw: bytes, findings: tuple[GitleaksFinding, ...], cleartexts: tuple[bytes, ...]) -> bytes` is pure. Only `run()` is impure (it awaits the subprocess). The functional-core / imperative-shell discipline is preserved. **Note for implementer:** the cleartext bytes appear in `_run` as `f["Secret"]` (local-var in the parser closure); the redaction pass uses them immediately to substitute the raw bytes and then drops the reference — cleartext lifetime is bounded to one stack frame. Mirror S3-01 Notes #198–200.

26. **DP4 — No shared `ScannerRunner` discipline holds across all four scanners.** Story explicitly rejects shared base class; trace cleanly to row 7 of design-patterns table. The AST audit (S6-06 AC-8) extends to gitleaks via `test_scanner_loc_ceiling.py`'s parametrize — same source-grep → AST audit promotion S6-06 mandated. **Fix:** AC-7 hardened — AST audit (not source-grep) over `gitleaks.py` parses the source with `ast.parse`; asserts no `ClassDef` named `ScannerRunner` / `BaseScanner` / `AbstractScanner`; asserts no `ImportFrom` whose module is another sibling scanner module; asserts `GitleaksProbe.bases` resolves to `Probe` only.

### Scope: 20 ACs original → 28 ACs after hardening

- **8 ACs added:** AC-N1 (dual-form identity), AC-B1 (eight ABC attrs), AC-R1 (registry smoke), AC-T1 (timeout path), AC-EX (non-zero exit), AC-RP1 (raw-artifact carve-out), AC-RP2 (raw-bytes redaction mutation test), AC-12b (malformed-JSON missing-keys).
- **12 ACs reworded:** AC-1, AC-3, AC-4, AC-5, AC-6, AC-7, AC-9, AC-12, AC-13, AC-15, AC-17, AC-20 (kernel-drift + fingerprint-format + path-correction fixes).
- **8 ACs preserved as-is:** AC-2 (LOC ceiling), AC-8 (CI lane), AC-10 (zero-plaintext walk), AC-11 (seed-present pre-check), AC-14 (warm cache), AC-16 (no SecretFinding shape persisted), AC-18 (CI gate), AC-19 (determinism).
- 0 RESCUE conditions. The story's goal, scope, and structural intent are sound; the prescriptions just need to match the post-S6-06 kernel.

Stage 3 research **skipped** — no `NEEDS RESEARCH` findings. Every gap was answerable from `phase-arch-design.md §"Goals" G5` + §"Gap 4 / Gap 5", the ADR pair (02-ADR-0005, 02-ADR-0010), the sibling-story validation logs (S3-01, S3-03, S6-06), and CLAUDE.md's pinned paths.

## Context

`GitleaksProbe` is the fourth Layer G scanner, structurally similar to S6-06's three (`run_external_cli` → JSON → `ScannerOutcome`). What makes it warrant its own story is the **`test_secret_in_source.py` adversarial test** — the load-bearing CI gate for the entire phase's security commitment. Phase 2's design ledger states: "secret findings redacted at writer chokepoint; plaintext in zero persisted files (G5)." That commitment is enforced by exactly this test: seed a known secret in a fixture repo, run the full gather, walk every file in the output directory (artifact, raw, cache, audit anchor), and assert the seeded plaintext appears in **zero** of them. Mutation of the test catches any future change that bypasses the redactor.

Two design discipline notes:

1. **The fourth scanner does NOT trigger a shared `ScannerRunner` extraction.** Gitleaks has its own JSON shape (`[{Description, RuleID, File, StartLine, Match, Secret}]`), its own flag set (`--no-banner`, `--report-format=json`, `--report-path=-`), its own error model (exit 1 = leaks found; exit 0 = none; exit ≥ 2 = scan error — same shape as semgrep), and its own runtime considerations (it walks git history if pointed at a `.git`; the probe constrains it to working-tree scan via `--source <repo>` + omitting `--git`). Final-design Design-patterns row 7 holds: four scanners, four shapes.
2. **The redactor is the chokepoint, not the probe.** `GitleaksProbe._run` returns *raw* findings — the writer's `SecretRedactor` composition pass (S3-03) walks the slice and replaces matches before any persistence. The adversarial test verifies this end-to-end: feed a secret in, walk every output file, find no plaintext anywhere. The probe code itself is dumb; the security boundary lives at the writer.

The fixture is `tests/adv/phase02/fixtures/secret_in_source/`: a tiny repo with `src/config.ts` containing `const AWS_KEY = "AKIA1234567890ABCDEF";` (a regex-matchable AWS Access Key ID — high precision, deliberately constructed to match the AWS pattern in `SecretRedactor`). The fixture is committed; the test reads it, runs `codegenie gather`, then grep-walks the output.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md` §"Component design" #4 `SecretRedactor`](../phase-arch-design.md) — pattern set; chokepoint discipline.
  - [`../phase-arch-design.md` §"Gap analysis" Gap 4](../phase-arch-design.md) — the `RedactedSlice` smart-constructor improvement; this story's adversarial test is what makes Gap 4's improvement observable.
  - [`../phase-arch-design.md` §"Gap analysis" Gap 5](../phase-arch-design.md) — no in-memory secret leak (S7-04 ships the boundary test; this story ships the on-disk test).
  - [`../phase-arch-design.md` §"Design patterns applied"](../phase-arch-design.md) row 7 — final scanner; discipline holds across all four.
- **Phase ADRs:**
  - [`../ADRs/0005-secret-findings-no-plaintext-persistence.md`](../ADRs/0005-secret-findings-no-plaintext-persistence.md) — the ADR this story tests.
  - [`../ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md`](../ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md) — type-level enforcement.
  - [`../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md`](../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md) — `gitleaks` in the allowlist.
- **Source design:**
  - [`../High-level-impl.md` §"Step 6"](../High-level-impl.md) — gitleaks 30s timeout; `--no-banner` for deterministic stdout.
  - [`../../localv2.md` §5.6](../../../localv2.md) — gitleaks is a Layer G scanner.
- **Existing kernel:**
  - `src/codegenie/output/sanitizer.py` (S3-01..03) — `redact_secrets(...) -> tuple[RedactedSlice, list[SecretFinding]]`.
  - `src/codegenie/output/writer.py` (S3-03) — accepts `RedactedSlice`, not raw `dict`.
  - `src/codegenie/probes/_shared/scanner_outcome.py` (S5-01) — `ScannerOutcome` union.
  - `src/codegenie/exec.py` (S1-07) — `run_external_cli`.
  - `src/codegenie/probes/layer_g/semgrep.py` (S6-06) — sibling pattern (also handles exit-code-1-is-findings).

## Goal

1. Ship `src/codegenie/probes/layer_g/gitleaks.py` as the fourth Layer G scanner, ≤ 200 LOC, no shared base with S6-06's three siblings, `@register_probe(heaviness="medium")`, 30 s timeout, `--no-banner` flag.
2. Ship `tests/adv/phase02/test_secret_in_source.py` — the load-bearing adversarial test that seeds an AWS key in a fixture repo, runs the full gather, and asserts the plaintext appears in **zero** persisted files.

## Acceptance criteria

**Numbered for traceability to the TDD plan.** ACs are corrected against the frozen Phase-0 `Probe` ABC (`src/codegenie/probes/base.py:74-96`), the actual `run_external_cli` signature (`src/codegenie/exec/__init__.py:485-599`), the closed `ScannerOutcome` variant set (`src/codegenie/probes/_shared/scanner_outcome.py`), the S5-04 sbom/cve sibling-precedent, and the **S6-06 hardening pass** (every kernel-drift fix from S6-06 applies here verbatim).

- [ ] **AC-1.** `src/codegenie/probes/layer_g/gitleaks.py` exports exactly `__all__ = ["GitleaksProbe", "GitleaksFinding", "GitleaksSlice"]`.
- [ ] **AC-2.** Module is **≤ 200 LOC** including Pydantic models, imports, docstring (verified by `tests/unit/probes/layer_g/test_scanner_loc_ceiling.py` from S6-06 — this story extends that parametrize to include gitleaks).
- [ ] **AC-3.** `@register_probe(heaviness="medium", runs_last=False)` — both kwargs explicit (mirror S6-06 AC-3; the decorator's ONLY kwargs are `heaviness` + `runs_last` per 02-ADR-0003 Option D; `requires=` is NOT a decorator kwarg). Class-level `name: str = "gitleaks"` matches the filename stem. `applies_to_tasks: list[str] = ["*"]` and `applies_to_languages: list[str] = ["*"]` — **`list[str]`**, not tuple. `timeout_seconds: int = 30`.
- [ ] **AC-4.** Invokes `await run_external_cli(_PROBE_ID, ["gitleaks", "detect", "--source", str(repo.root), "--no-banner", "--report-format=json", "--report-path=-", "--no-git", "--exit-code", "0"], cwd=repo.root, timeout_s=30.0)`. The first positional argument is the `ProbeId` (`_PROBE_ID: Final[ProbeId] = ProbeId("gitleaks")`), NOT the binary string. The binary `"gitleaks"` is `argv[0]` (`run_external_cli` allowlist-checks it). **Flag rationale:** `--no-banner` for deterministic stdout (mutation: dropping it injects ANSI banner into stdout, breaking JSON parse); `--report-path=-` writes JSON to stdout (not a temp file); `--no-git` constrains to working-tree (we don't want history scanning in Phase 2 — that's a Phase 3+ feature); `--exit-code 0` overrides gitleaks' default exit-1-on-findings (we prefer to treat findings via parsed JSON; unlike semgrep, we *can* override gitleaks' exit code, so we do — for a simpler conditional in `run`). Captured-argv spy asserts every flag and its position.
- [ ] **AC-5.** `GitleaksFinding` Pydantic `BaseModel(frozen=True, extra="forbid")` with `rule_id: str, file: str, line: int, description: str, match_fingerprint: str`. **`match_fingerprint` is exactly 8 lowercase hex characters** — the first 8 hex chars of `codegenie.hashing.content_hash_bytes(secret_cleartext.encode("utf-8")).removeprefix("blake3:")` (the canonical Phase-0 hashing chokepoint helper; matches S3-01 AC-13 + AC-14 fingerprint format **byte-for-byte**). **The `blake3` PyPI package is NOT imported in `gitleaks.py`**; the chokepoint helper is the only path. Mutation caught: (a) any future `match: str` / `cleartext: str` field that ships cleartext through the probe; (b) any direct `blake3(...).hexdigest()[:N]` call bypassing the chokepoint; (c) any slice length other than 8 (a `[:16]` slip silently desynchronizes the probe from the redactor's marker format and AC-13 would never match).
- [ ] **AC-6.** `GitleaksSlice` Pydantic `BaseModel(frozen=True, extra="forbid")` with `outcome: ScannerOutcome, findings_count: int, findings_detail: list[GitleaksFinding]`. Per S6-06 AC-9, the rich per-scanner finding shape lives on the SLICE as `findings_detail` (NOT on `ScannerRan.findings` — that field stays as the empty `list[Finding]` from S5-01 per the closed sum's contract). Mutation caught: collapsing `findings_detail` away (losing rule_id / file / line in the persisted artifact) breaks AC-12.
- [ ] **AC-7.** **No shared base class with S6-06's scanners — AST audit, not source-grep.** Architectural test (extending `test_scanner_loc_ceiling.py`'s parametrize to include gitleaks) parses the source with `ast.parse`; asserts no `ClassDef` named `ScannerRunner` / `BaseScanner` / `AbstractScanner`; asserts no `ImportFrom` whose module is another sibling scanner module (`semgrep`, `ast_grep`, `ripgrep_curated`); asserts `GitleaksProbe.bases` resolves to `Probe` only. The shared types are `ScannerOutcome` (S5-01, `_shared/scanner_outcome.py`) and `run_external_cli` (S1-07, `exec/__init__.py`) — both at the **kernel** level, not the scanner-family level.
- [ ] **AC-8.** **`test_secret_in_source.py` exists at `tests/adv/phase02/test_secret_in_source.py`** and is part of the `adv-phase02` CI lane (S8-03). It is **NOT** skipped under any condition; if gitleaks is not on PATH, the test **fails** (because the adversarial guarantee requires gitleaks to actually find the seed). The CI image for `adv-phase02` installs gitleaks unconditionally.
- [ ] **AC-9.** **Fixture exists.** `tests/adv/phase02/fixtures/secret_in_source/` contains:
  - `src/config.ts` with the literal text `const AWS_KEY = "AKIA1234567890ABCDEF";` (a regex-matchable AWS Access Key ID).
  - `package.json` (minimal — so Phase 1's Layer A probes engage).
  - `README.md` documenting the seed pattern **using a placeholder, NEVER the literal seed** — `README.md` must contain a documentation block like *"This fixture seeds a deliberate AWS Access Key ID of the form `AKIA<sixteen-uppercase-alphanumerics>` in `src/config.ts`. Do NOT 'fix' it — the test depends on it."* The literal `AKIA1234567890ABCDEF` MUST NOT appear in `README.md` (the test asserts this via `assert SEED not in (FIXTURE / "README.md").read_text()`) — otherwise gitleaks' working-tree scan picks the README up too and self-contaminates the fixture.
  - `docs/internal-notes.md` — a **second** instance of the literal seed inside markdown prose (NOT inside a code fence). This proves the envelope-level redactor's *non-gitleaks-found* coverage: gitleaks's rules may or may not pick up prose-form occurrences depending on rule-pack version, but the entropy-fallback / pattern-class regex sweep in S3-01's `redact_secrets` catches it regardless. If only the gitleaks-found instance were redacted and the markdown-prose one persisted, AC-10 would fail. This is the **load-bearing two-pathway test**: gitleaks-found AND entropy/pattern-found both reach the redactor.
- [ ] **AC-10.** **End-to-end gather → walk → assert zero plaintext.** The test runs `gather` on the fixture via `subprocess.run([sys.executable, "-m", "codegenie", "gather", str(fresh_fixture)], check=True)` (NOT `["codegenie", ...]` — the console-script may not be on PATH), then walks every file under `.codegenie/`:
  - `.codegenie/context/repo-context.yaml`
  - `.codegenie/context/raw/*.json` (every probe's raw artifact, including `gitleaks-raw.json` if present per AC-RP1)
  - `.codegenie/cache/**/*` (every cache blob, recursive)
  - `.codegenie/context/runs/*.json` (audit anchors — canonical path per CLAUDE.md, NOT `.codegenie/runs/`)
  - asserts `"AKIA1234567890ABCDEF"` (as bytes) appears in **zero** of them. The assertion is **byte-level** (`SEED.encode() in path.read_bytes()`), not text-level — a future probe that ships a binary blob (e.g., a SCIP index) is still walked correctly.
- [ ] **AC-11.** **The seed *is* present in the input fixture.** The test asserts `"AKIA1234567890ABCDEF" in (fixture_root / "src" / "config.ts").read_text()` AND `"AKIA1234567890ABCDEF" in (fixture_root / "docs" / "internal-notes.md").read_text()` BEFORE the gather — so a future contributor who "fixes" either fixture file fails the pre-check immediately, rather than silently invalidating the test.
- [ ] **AC-12.** **Gitleaks DID find the seed.** The test reads `repo-context.yaml`, parses it via `yaml.safe_load`, navigates to the `gitleaks` probe slice (`envelope["probes"]["gitleaks"]["findings_detail"]`), and asserts at least one entry whose `rule_id` matches the case-insensitive regex `r"aws[-_]?(access[-_]?)?token|aws[-_]?key"` (gitleaks' AWS-key rule name has varied across versions — `aws-access-token`, `aws_access_key`, `aws-access-key-id` are all observed). Mutation caught: a future config change that disables AWS rules would silently kill the test's coverage even if the entropy fallback still redacted the cleartext.
- [ ] **AC-12b.** **Malformed JSON missing required keys → `ScannerFailed(reason="invalid_json")`.** Unit test: spy returns `stdout = b'[{"RuleID": "x"}]'` (missing `File`, `StartLine`, `Secret`). Probe returns `ScannerFailed(exit_code=0, stderr_tail=<tail>, reason="invalid_json")`. Mutation caught: a future contributor who silently swallows `KeyError` would land a probe that emits `ScannerRan(findings=[])` on a malformed gitleaks output — silently masking the real bug.
- [ ] **AC-13.** **Fingerprint reproducibility (8-hex, chokepoint-derived).** The test independently computes `expected = content_hash_bytes(b"AKIA1234567890ABCDEF").removeprefix("blake3:")[:8]` (using the canonical Phase-0 helper — NOT raw `blake3`) and asserts `f"<REDACTED:fingerprint={expected}>"` appears in `repo-context.yaml`. The marker format matches S3-01 AC-14 exactly (literal `<REDACTED:fingerprint=`, 8 lowercase-hex chars, literal `>`). This proves: (a) the probe and the redactor compute identical fingerprints; (b) the redactor saw the exact seed (not a near-match — a near-match would produce a different fingerprint).
- [ ] **AC-14.** **Cache lane is covered.** The test asserts that running `gather` a second time (warm cache) ALSO produces zero plaintext under the same AC-10 walk. Strengthening over the trivial replay: the test ALSO deletes `.codegenie/context/repo-context.yaml` between the two gathers (forcing re-write of the envelope from cache-served probe outputs), to confirm the cache-hit path is not "the first gather wrote redacted bytes; the second served them" — but rather "the cache contains redacted slices and the second gather's envelope-write redactor is still firing." Mutation caught: any cache-hit path that writes the cache blob BEFORE the per-probe scrub (or BEFORE gitleaks' raw-bytes carve-out per AC-RP1) would leak plaintext to the cache file, which the second gather's walk catches.
- [ ] **AC-15.** **Audit anchor lane is covered.** Phase 0's audit writer lands `Ran/CacheHit/Skipped` records to `.codegenie/context/runs/<utc-iso>-<short>.json` (canonical path per CLAUDE.md — NOT `.codegenie/runs/`). The test verifies every file under `.codegenie/context/runs/` contains zero `SEED.encode()` bytes. Mutation caught: a future debug-logging change that includes raw slice content or a `SecretFinding.cleartext_len` payload with the actual cleartext.
- [ ] **AC-16.** **`SecretFinding` shape is NOT persisted with cleartext.** The test reads every file in `.codegenie/` and asserts: (a) no SEED byte sequence appears (already AC-10); (b) the literal field-name `"cleartext"` does not appear (a regression that persists `SecretFinding` model dumps with a `cleartext: str` field would be caught); (c) `"<REDACTED:fingerprint="` DOES appear in `repo-context.yaml` (positive control — the redactor ran). The in-memory `list[SecretFinding]` returned by S3-01's `redact_secrets` is for the CLI summary path only — its persistence would defeat the chokepoint per Gap 4 / ADR-0010.
- [ ] **AC-17.** **`mypy --strict`** passes on `gitleaks.py`. The per-scanner `findings_detail: list[GitleaksFinding]` type makes every consumer position-typed; `Any` escapes only via documented seam boundaries.
- [ ] **AC-18.** **CI gate.** `adv-phase02` job (defined in S8-03) imports this test file's lane; failure is build-fail (not advisory).
- [ ] **AC-19.** **Determinism.** Two gathers on the same fixture (cleared `.codegenie/` between, OR via two `tmp_path` copies of the fixture) produce byte-identical `repo-context.yaml` (modulo `generated_at` timestamp; modulo any per-run UUID field — the test strips both before comparison). Fingerprints are deterministic (BLAKE3 is deterministic; the same cleartext → same 8-hex fingerprint via the chokepoint helper).
- [ ] **AC-20.** **`secrets_redacted_count` log field positive AND ≥ 2.** The CLI's `secrets_redacted_count` structured-log field (per S3-03 AC-10 — emitted on the `event="envelope.written"` event) is `>= 2` on the gather (one for `src/config.ts`, one for `docs/internal-notes.md` — both seeded with the same cleartext, which yields `findings_count == 2` and `len(fingerprints) == 1` per S3-01 AC-26 dedupe contract). The test parses CLI stderr JSON lines, filters by `event == "envelope.written"`, and asserts the field value. Mutation caught: any redactor short-circuit that returns the slice unchanged would log 0; a `set`-based dedupe at finding-level (instead of fingerprint-level) would log 1.
- [ ] **AC-N1.** **Dual-form identity discipline.** The module declares `_PROBE_ID: Final[ProbeId] = ProbeId("gitleaks")` at module scope (the value passed to `run_external_cli`). The class declares `name: str = "gitleaks"` as a class attribute (the kernel-introspected identity, ABC contract). Both strings equal the filename stem `"gitleaks"`. Mutation caught: drift between `name`, `_PROBE_ID`, filename — any one of three silently breaks either dispatch or argv-validation.
- [ ] **AC-B1.** **Eight ABC class attributes pinned.** Mirror cve.py:177-185 / S6-06 AC-B1: `name: str = "gitleaks"`, `version: str = "0.1.0"`, `layer = "G"`, `tier = "base"`, `applies_to_tasks: list[str] = ["*"]`, `applies_to_languages: list[str] = ["*"]`, `requires: list[str] = []` (class attribute — empty list; per 02-ADR-0003 Option D `requires` is metadata-only, not load-bearing for dispatch), `declared_inputs: list[str] = ["**/*"]` (gitleaks walks the working tree), `cache_strategy: Literal["content"] = "content"` (pinned explicitly; default ABC value), `timeout_seconds: int = 30`. A per-probe test asserts every one — a `layer = "F"` typo slips past `mypy --strict` otherwise.
- [ ] **AC-R1.** **Registry-membership smoke.** `_PROBE_REGISTRY["gitleaks"].heaviness == "medium"`; `_PROBE_REGISTRY["gitleaks"].runs_last is False`; the entry has **no** `requires` key (defensive — `@register_probe(requires=...)` is NOT a kernel kwarg per 02-ADR-0003 Option D; passing it must fail at import). Per S5-04 K2 / S6-06 AC-R1 precedent.
- [ ] **AC-T1.** **Timeout → `ScannerFailed(exit_code=124, stderr_tail="gitleaks.timeout")`.** When `run_external_cli` raises `ProbeTimeoutError` (from `codegenie.errors`), the probe catches it and emits `ScannerFailed(exit_code=124, stderr_tail="gitleaks.timeout")` with `confidence="low"`. Mirror sbom.py:275-276 / cve.py:246-247 / S6-06 AC-T1. Mutation caught: any timeout that escapes past the probe boundary breaks the coordinator's per-probe failure isolation.
- [ ] **AC-EX.** **Non-zero exit (≥ 2) → `ScannerFailed(exit_code, stderr_tail)`.** When `result.returncode >= 2` (a real gitleaks crash — distinct from the `--exit-code 0` overridden "findings present" carve-out), the probe emits `ScannerFailed(exit_code=result.returncode, stderr_tail=<tail>)` with `confidence="low"`. Unit test: spy returns `ProcessResult(returncode=2, stdout=b"", stderr=b"gitleaks: panic: ...")`. Mutation caught: a default-treat-non-zero-as-empty-findings convention applied to gitleaks would silently mask a real scanner crash.
- [ ] **AC-RP1.** **Raw-artifact persistence — gitleaks-only carve-out from S6-06 AC-W1.** Per ADR-0005, plaintext present in **zero** persisted files is the load-bearing invariant. Gitleaks' raw stdout JSON contains the cleartext in the `"Secret"` field; the envelope-level `_seam_redact_envelope` (S3-03) walks the dict envelope only — it does NOT touch `raw_artifacts: list[tuple[str, bytes]]`. **Decision:** the gitleaks probe MUST redact the cleartext in its raw bytes BEFORE adding to `ProbeOutput.raw_artifacts`. For each finding, the probe performs a byte-level substitution: `raw = raw.replace(f["Secret"].encode("utf-8"), f"<REDACTED:fingerprint={_fingerprint(f['Secret'].encode())}>".encode())`. The redacted raw bytes ARE persisted (audit value preserved — one can still see what gitleaks found and how, just with cleartext replaced); the unredacted bytes are dropped after substitution. This makes the structural defense one rung *earlier* than ADR-0010: the Writer never sees gitleaks cleartext; the failure mode is impossible by construction. Pattern: **Make illegal states unrepresentable at the I/O boundary** (toolkit reference).
- [ ] **AC-RP2.** **Raw-bytes redaction mutation test.** Unit test (with spied `run_external_cli`): spy returns a stdout containing two findings, each with a distinct `"Secret"` cleartext. After `await probe.run(repo, ctx)`, assert: (a) `len(probe_output.raw_artifacts) == 1`; (b) the bytes payload contains **zero** occurrences of either cleartext byte sequence; (c) the bytes payload contains both expected `<REDACTED:fingerprint=<8hex>>` markers; (d) the bytes payload is valid JSON (parseable back into a list of dicts with the `Secret` field replaced by the marker string). Mutation caught: any future "just write the raw bytes" PR that bypasses the per-finding substitution.

## Implementation outline

1. `src/codegenie/probes/layer_g/gitleaks.py`:
   - Mirror `semgrep.py` shape from S6-06 (separate file, no base class, dual-form identity, async `run(self, repo, ctx)`).
   - Module-level: `_PROBE_ID: Final[ProbeId] = ProbeId("gitleaks")` (AC-N1); `_GITLEAKS_ARGV_BASE: Final[tuple[str, ...]]` capturing the fixed flag prefix (`("gitleaks", "detect", "--no-banner", "--report-format=json", "--report-path=-", "--no-git", "--exit-code", "0")`) so AC-4's argv-pinning test enumerates a single source of truth.
   - Pure helpers:
     - `_fingerprint(b: bytes) -> str` — `content_hash_bytes(b).removeprefix("blake3:")[:8]`. Uses Phase-0 hashing chokepoint. **NOT** raw `blake3`.
     - `_parse(raw: bytes) -> tuple[tuple[GitleaksFinding, ...], int] | ScannerFailed` — parses gitleaks' JSON array; per finding, computes `match_fingerprint = _fingerprint(f["Secret"].encode("utf-8"))`; returns `ScannerFailed(reason="invalid_json", ...)` on JSON decode error OR missing required keys (`RuleID` / `File` / `StartLine` / `Secret`). **Caller pattern-matches via `isinstance(parsed, ScannerFailed)` — closed sum-type Result shape.**
     - `_redact_raw_bytes(raw: bytes, findings: tuple[GitleaksFinding, ...], cleartexts: tuple[bytes, ...]) -> bytes` — pure byte-level substitution; for each `(finding, cleartext)` pair, replaces the cleartext byte sequence with `f"<REDACTED:fingerprint={finding.match_fingerprint}>".encode()`. Returns the redacted bytes. **Cleartexts are passed in as `tuple[bytes, ...]` — they exist only as locals in `run()` and are dropped after the substitution returns.** (AC-RP1.)
   - `run(self, repo, ctx)` (async): invokes `await run_external_cli(_PROBE_ID, list(_GITLEAKS_ARGV_BASE) + ["--source", str(repo.root)], cwd=repo.root, timeout_s=30.0)`; pattern-matches:
     - `ToolMissingError` → `ScannerSkipped(reason="tool_missing")`, `confidence="low"`.
     - `ProbeTimeoutError` → `ScannerFailed(exit_code=124, stderr_tail="gitleaks.timeout")`, `confidence="low"`. (AC-T1.)
     - `result.returncode >= 2` → `ScannerFailed(exit_code=result.returncode, stderr_tail=_stderr_tail(result.stderr))`, `confidence="low"`. (AC-EX.)
     - happy path → `_parse(result.stdout)`; if `ScannerFailed`, return it; else, harvest the cleartexts as a parallel `tuple[bytes, ...]` (from the parsed JSON, BEFORE the `GitleaksFinding` objects are built — the cleartext lifetime is bounded to this stack frame), call `_redact_raw_bytes`, build `ProbeOutput(schema_slice=GitleaksSlice(...).model_dump(mode="json"), raw_artifacts=[("gitleaks-raw.json", redacted_bytes)], confidence="high", duration_ms=..., warnings=[], errors=[])`.
   - Six-field `ProbeOutput` constructor (AC-5 / S6-06 B5 fix). No `probe_id=` kwarg.
2. `tests/adv/phase02/fixtures/secret_in_source/`:
   - `src/config.ts` with literal `const AWS_KEY = "AKIA1234567890ABCDEF";`.
   - `package.json` (minimal valid Node manifest — so Phase 1's Layer A probes engage).
   - `docs/internal-notes.md` with a **second** literal instance of `AKIA1234567890ABCDEF` inside markdown prose (NOT inside a code fence — exercises the non-gitleaks-found redaction pathway).
   - `README.md` documenting the seed via a **placeholder pattern** (`AKIA<sixteen-uppercase-alphanumerics>`); the literal `AKIA1234567890ABCDEF` MUST NOT appear here.
3. `tests/unit/probes/layer_g/test_gitleaks.py` — six unit tests covering AC-3, AC-4, AC-5, AC-6, AC-7, AC-12b, AC-T1, AC-EX, AC-N1, AC-B1, AC-R1, AC-RP2 (mutation table). Mocking via `monkeypatch.setattr(gitleaks_mod, "run_external_cli", _spy)` per S6-06 AC-19. The `_spy` is an `AsyncMock`/coroutine returning `ProcessResult` and capturing `(probe_name, argv, cwd, timeout_s)` for argv-pinning assertions.
4. `tests/unit/probes/layer_g/conftest.py` — `_make_repo(tmp_path) -> RepoSnapshot` and `_make_ctx(tmp_path) -> ProbeContext` fixtures (mirror sbom/cve conftest precedent — sbom.py adjacent tests).
5. `tests/unit/probes/layer_g/test_scanner_loc_ceiling.py` — extend the existing parametrize from S6-06 to include `gitleaks`; the AST audit (AC-7) is the same shape used for the three siblings.
6. `tests/adv/phase02/test_secret_in_source.py`:
   - Pre-check: confirm seed present in both fixture files (AC-11).
   - Run: `subprocess.run([sys.executable, "-m", "codegenie", "gather", str(fresh_fixture)], check=True)` (AC-10 / B12 fix).
   - Walk: enumerate every file under `fresh_fixture / ".codegenie"`; for each, assert `SEED.encode() not in path.read_bytes()` (AC-10).
   - Verify gitleaks finding present (AC-12): parse `repo-context.yaml`, walk to `envelope["probes"]["gitleaks"]["findings_detail"]`, regex-match an AWS rule.
   - Verify fingerprint reproducibility (AC-13): independently compute `_fingerprint(SEED.encode())` via the chokepoint helper; assert the `<REDACTED:fingerprint={expected}>` marker appears in `repo-context.yaml`.
   - Cache lane (AC-14): delete `repo-context.yaml` between two gathers; re-walk after the second.
   - Audit anchor (AC-15): walk `.codegenie/context/runs/*.json` (canonical path); assert no SEED bytes.
   - Negative (AC-16): assert `"cleartext"` substring absent; `<REDACTED:fingerprint=` substring present (positive control).
   - Log field (AC-20): parse stderr JSON; filter `event == "envelope.written"`; assert `secrets_redacted_count >= 2`.
   - Determinism (AC-19): two gathers under two `tmp_path` copies; strip `generated_at` from both YAML payloads; assert byte-identity.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Mocking is via `monkeypatch.setattr(gitleaks_mod, "run_external_cli", _spy)` per S6-06 AC-19 — `pytest-subprocess` (the `fp` fixture) is NOT in `pyproject.toml`'s dev deps. The spy is an async callable that returns `ProcessResult` and captures positional/keyword args for argv-pinning assertions.

```python
# tests/unit/probes/layer_g/test_gitleaks.py
"""Unit tests for GitleaksProbe (S6-07)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from codegenie.errors import ProbeTimeoutError, ToolMissingError
from codegenie.exec import ProcessResult
from codegenie.hashing import content_hash_bytes
from codegenie.probes.base import _PROBE_REGISTRY
from codegenie.probes.layer_g import gitleaks as gl_mod
from codegenie.probes._shared.scanner_outcome import (
    ScannerFailed,
    ScannerRan,
    ScannerSkipped,
)
from codegenie.types.identifiers import ProbeId


_SEED = "AKIA1234567890ABCDEF"
_EXPECTED_FP = content_hash_bytes(_SEED.encode("utf-8")).removeprefix("blake3:")[:8]


# Fixtures _make_repo / _make_ctx live in tests/unit/probes/layer_g/conftest.py
# (mirror tests/unit/probes/layer_c/conftest.py shape).


def _process_result(*, returncode: int = 0, stdout: bytes = b"[]", stderr: bytes = b"") -> ProcessResult:
    return ProcessResult(returncode=returncode, stdout=stdout, stderr=stderr)


def _spy_returning(result: ProcessResult) -> AsyncMock:
    spy = AsyncMock(return_value=result)
    return spy


# ---- AC-4 + AC-N1: argv pinning via captured spy -----------------------

async def test_argv_pins_all_hardening_flags(monkeypatch, tmp_path, _make_repo, _make_ctx) -> None:
    """AC-4 + AC-N1. Mutations caught: dropping `--no-banner` (ANSI banner
    breaks JSON parse); omitting `--no-git` (silently scans history);
    omitting `--exit-code 0` (gitleaks exits 1 on findings, mis-classified
    as failure); wrong first positional (binary string instead of _PROBE_ID);
    wrong cwd; wrong timeout_s."""
    spy = _spy_returning(_process_result(stdout=b"[]"))
    monkeypatch.setattr(gl_mod, "run_external_cli", spy)

    repo = _make_repo(tmp_path)
    ctx = _make_ctx(tmp_path)
    await gl_mod.GitleaksProbe().run(repo, ctx)

    args, kwargs = spy.call_args
    assert args[0] == gl_mod._PROBE_ID            # AC-N1: dual-form identity
    assert args[0] == ProbeId("gitleaks")
    argv = args[1]
    assert argv[0] == "gitleaks"                  # binary string is argv[0]
    assert argv[1] == "detect"
    for required in ("--no-banner", "--no-git", "--report-format=json",
                     "--report-path=-", "--exit-code", "0", "--source", str(repo.root)):
        assert required in argv
    assert kwargs["cwd"] == repo.root
    assert kwargs["timeout_s"] == 30.0


# ---- AC-5 + AC-RP2: fingerprint is chokepoint-derived; cleartext absent -

async def test_finding_carries_8hex_fingerprint_and_raw_bytes_redacted(monkeypatch, tmp_path, _make_repo, _make_ctx) -> None:
    """AC-5 + AC-RP2. Mutations caught: any `[:16]` slice that desynchronizes
    from the redactor's marker (B9); any raw-bytes payload that retains
    cleartext (RP1 carve-out violation); any `match: str` / `cleartext: str`
    field that ships cleartext through the probe."""
    raw_json = json.dumps([{
        "RuleID": "aws-access-token",
        "Description": "AWS Access Token",
        "File": "src/config.ts",
        "StartLine": 1,
        "Secret": _SEED,
    }]).encode("utf-8")
    spy = _spy_returning(_process_result(stdout=raw_json))
    monkeypatch.setattr(gl_mod, "run_external_cli", spy)

    output = await gl_mod.GitleaksProbe().run(_make_repo(tmp_path), _make_ctx(tmp_path))
    slice_ = gl_mod.GitleaksSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerRan)
    assert len(slice_.findings_detail) == 1
    f = slice_.findings_detail[0]

    # AC-5: 8 lowercase hex chars; chokepoint-derived; no cleartext in model.
    assert len(f.match_fingerprint) == 8
    assert all(c in "0123456789abcdef" for c in f.match_fingerprint)
    assert f.match_fingerprint == _EXPECTED_FP
    assert _SEED not in json.dumps(slice_.model_dump(mode="json"))

    # AC-RP2: raw bytes payload contains the redaction marker AND zero
    # occurrences of the cleartext byte sequence.
    assert len(output.raw_artifacts) == 1
    name, raw_bytes = output.raw_artifacts[0]
    assert name == "gitleaks-raw.json"
    assert _SEED.encode("utf-8") not in raw_bytes
    assert f"<REDACTED:fingerprint={_EXPECTED_FP}>".encode("utf-8") in raw_bytes
    # AC-RP2(d): the redacted raw is still valid JSON re-parseable as list[dict].
    reparsed = json.loads(raw_bytes)
    assert isinstance(reparsed, list)
    assert reparsed[0]["Secret"] == f"<REDACTED:fingerprint={_EXPECTED_FP}>"


# ---- AC-T1: timeout path -----------------------------------------------

async def test_timeout_yields_scanner_failed(monkeypatch, tmp_path, _make_repo, _make_ctx) -> None:
    """AC-T1. Mutation caught: timeout escapes past the probe boundary."""
    async def _raise_timeout(*args, **kwargs):
        raise ProbeTimeoutError("gitleaks timed out")
    monkeypatch.setattr(gl_mod, "run_external_cli", _raise_timeout)

    output = await gl_mod.GitleaksProbe().run(_make_repo(tmp_path), _make_ctx(tmp_path))
    slice_ = gl_mod.GitleaksSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.exit_code == 124
    assert "gitleaks.timeout" in slice_.outcome.stderr_tail
    assert output.confidence == "low"


# ---- AC-EX: exit_code >= 2 → ScannerFailed -----------------------------

async def test_real_crash_exit_2_yields_scanner_failed(monkeypatch, tmp_path, _make_repo, _make_ctx) -> None:
    """AC-EX. Mutation caught: default-treat-non-zero-as-empty-findings
    convention would silently mask a real scanner crash."""
    spy = _spy_returning(_process_result(returncode=2, stdout=b"", stderr=b"gitleaks: panic"))
    monkeypatch.setattr(gl_mod, "run_external_cli", spy)

    output = await gl_mod.GitleaksProbe().run(_make_repo(tmp_path), _make_ctx(tmp_path))
    slice_ = gl_mod.GitleaksSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.exit_code == 2
    assert output.confidence == "low"


# ---- AC-12b: malformed JSON (missing required keys) -------------------

async def test_malformed_json_missing_required_keys(monkeypatch, tmp_path, _make_repo, _make_ctx) -> None:
    """AC-12b. Mutation caught: silent KeyError swallow that emits
    ScannerRan(findings=[]) on malformed gitleaks output."""
    spy = _spy_returning(_process_result(stdout=b'[{"RuleID": "x"}]'))  # missing File/StartLine/Secret
    monkeypatch.setattr(gl_mod, "run_external_cli", spy)

    output = await gl_mod.GitleaksProbe().run(_make_repo(tmp_path), _make_ctx(tmp_path))
    slice_ = gl_mod.GitleaksSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.reason == "invalid_json"


# ---- AC-10 (tool missing): ScannerSkipped ------------------------------

async def test_tool_missing_yields_scanner_skipped(monkeypatch, tmp_path, _make_repo, _make_ctx) -> None:
    """Mirror S6-06 AC-10. Mutation caught: raise past the probe."""
    async def _raise_missing(*args, **kwargs):
        raise ToolMissingError("gitleaks")
    monkeypatch.setattr(gl_mod, "run_external_cli", _raise_missing)

    output = await gl_mod.GitleaksProbe().run(_make_repo(tmp_path), _make_ctx(tmp_path))
    slice_ = gl_mod.GitleaksSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerSkipped)
    assert slice_.outcome.reason == "tool_missing"
    assert output.confidence == "low"


# ---- AC-3 + AC-B1 + AC-R1: registry + ABC class-attribute pinning ------

def test_registry_membership_and_abc_attributes() -> None:
    """AC-3 + AC-B1 + AC-R1. Mutation caught: heaviness drift, runs_last
    flip, accidental `requires` kwarg, ABC-attribute typo."""
    entry = _PROBE_REGISTRY["gitleaks"]
    assert entry.heaviness == "medium"
    assert entry.runs_last is False
    # `requires` is metadata-only — never a decorator kwarg.
    assert not hasattr(entry, "requires_via_decorator")

    p = gl_mod.GitleaksProbe()
    assert p.name == "gitleaks"
    assert p.version == "0.1.0"
    assert p.layer == "G"
    assert p.tier == "base"
    assert p.applies_to_tasks == ["*"]
    assert p.applies_to_languages == ["*"]
    assert p.requires == []
    assert p.declared_inputs == ["**/*"]
    assert p.cache_strategy == "content"
    assert p.timeout_seconds == 30
```

```python
# tests/adv/phase02/test_secret_in_source.py
"""LOAD-BEARING adversarial test (S6-07).

Seeds a known AWS key in a fixture repo, runs `codegenie gather`, and
asserts the plaintext appears in ZERO persisted files. This is the
test the writer-chokepoint commitment (G5 / ADR-0005 / ADR-0010) is
verified by.

If this test fails, the phase fails its security commitment. No
"flake retry" — the build is broken.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from codegenie.hashing import content_hash_bytes

SEED = "AKIA1234567890ABCDEF"
EXPECTED_FP = content_hash_bytes(SEED.encode("utf-8")).removeprefix("blake3:")[:8]
EXPECTED_MARKER = f"<REDACTED:fingerprint={EXPECTED_FP}>"
FIXTURE = Path(__file__).parent / "fixtures" / "secret_in_source"


@pytest.fixture
def fresh_fixture(tmp_path: Path) -> Path:
    """Copy the committed fixture into tmp_path so the gather writes
    `.codegenie/` artifacts under an isolated location."""
    dst = tmp_path / "repo"
    shutil.copytree(FIXTURE, dst)
    return dst


def _walk_all_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            out.append(Path(dirpath) / fn)
    return out


def _run_gather(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "codegenie", "gather", str(repo)],
        check=True, capture_output=True, text=True,
    )


# ---- AC-11: seed is present in fixture input (pre-checks) --------------

def test_seed_is_present_in_fixture_input() -> None:
    """AC-11. Mutation caught: a future contributor "fixing" the
    fixture by removing the seed — the test fires immediately, not at
    the misleading "no plaintext found in output" success it would
    otherwise produce."""
    src = (FIXTURE / "src" / "config.ts").read_text()
    notes = (FIXTURE / "docs" / "internal-notes.md").read_text()
    assert SEED in src, (
        f"Test fixture src/config.ts must contain {SEED!r}. If you 'fixed' "
        "the fixture, restore the seed — this test depends on it."
    )
    assert SEED in notes, (
        f"Test fixture docs/internal-notes.md must contain {SEED!r}."
    )
    # README must NOT contain the literal seed (self-contamination guard).
    readme = (FIXTURE / "README.md").read_text()
    assert SEED not in readme, (
        f"README.md must not contain the literal {SEED!r} — use a placeholder. "
        "The literal would self-contaminate gitleaks' working-tree scan."
    )


# ---- AC-10 + AC-15 + AC-16: the load-bearing assertion -----------------

def test_gather_produces_zero_plaintext_in_any_persisted_file(fresh_fixture: Path) -> None:
    """AC-10, AC-15, AC-16. The load-bearing assertion. Walks EVERY
    file under .codegenie/ as bytes; asserts zero occurrences of the
    seed; asserts SecretFinding shape is not persisted."""
    _run_gather(fresh_fixture)

    codegenie_dir = fresh_fixture / ".codegenie"
    assert codegenie_dir.exists(), "gather did not produce .codegenie/"

    plaintext_found_in: list[str] = []
    cleartext_field_in: list[str] = []
    for path in _walk_all_files(codegenie_dir):
        try:
            content = path.read_bytes()
        except OSError:
            continue
        if SEED.encode("utf-8") in content:
            plaintext_found_in.append(str(path.relative_to(fresh_fixture)))
        if b"cleartext" in content:
            cleartext_field_in.append(str(path.relative_to(fresh_fixture)))

    assert not plaintext_found_in, (
        f"Plaintext seed appeared in {len(plaintext_found_in)} persisted "
        f"files: {plaintext_found_in}. ADR-0005 / ADR-0010 violated."
    )
    assert not cleartext_field_in, (
        f"SecretFinding 'cleartext' field appeared in: {cleartext_field_in}. "
        "The in-memory findings list was persisted in violation of Gap-4."
    )

    # Positive control (AC-16): the redactor DID run.
    yaml_bytes = (codegenie_dir / "context" / "repo-context.yaml").read_bytes()
    assert b"<REDACTED:fingerprint=" in yaml_bytes, (
        "No redaction marker found — the redactor was bypassed entirely."
    )


# ---- AC-13: fingerprint reproducibility (8-hex, chokepoint-derived) ---

def test_gather_redacted_marker_carries_expected_fingerprint(fresh_fixture: Path) -> None:
    """AC-13. Mutation caught: the redactor saw a *different* secret
    (regex matched something adjacent) — the fingerprint would diverge.
    Also catches B9 (16-char fingerprint drift) and B10 (raw-blake3
    bypass of the chokepoint) — both would produce a non-matching
    EXPECTED_MARKER."""
    _run_gather(fresh_fixture)
    artifact = (fresh_fixture / ".codegenie" / "context" / "repo-context.yaml").read_text()
    assert EXPECTED_MARKER in artifact, (
        f"Expected redaction marker {EXPECTED_MARKER!r} (8-hex chokepoint-"
        "derived) not found. The redactor either missed the seed, matched "
        "a different cleartext, or used a different fingerprint shape."
    )


# ---- AC-12: gitleaks itself contributed to the redaction --------------

def test_gitleaks_actually_found_the_seed(fresh_fixture: Path) -> None:
    """AC-12. Mutation caught: a future config change disabling AWS
    rules in gitleaks — AC-10 would still pass (entropy/pattern fallback
    redacts), but the gitleaks-rule contribution would vanish silently."""
    import re
    _run_gather(fresh_fixture)
    envelope = yaml.safe_load(
        (fresh_fixture / ".codegenie" / "context" / "repo-context.yaml").read_text()
    )
    gl_slice = envelope.get("probes", {}).get("gitleaks", {})
    findings_detail = gl_slice.get("findings_detail", [])
    aws_rule_re = re.compile(r"aws[-_]?(access[-_]?)?token|aws[-_]?key", re.IGNORECASE)
    aws_findings = [f for f in findings_detail if aws_rule_re.search(f.get("rule_id", ""))]
    assert aws_findings, (
        f"Gitleaks did not flag the seed as an AWS token. findings_detail={findings_detail}"
    )
    # Each AWS finding carries an 8-hex fingerprint (NOT the cleartext).
    for f in aws_findings:
        assert len(f["match_fingerprint"]) == 8
        assert SEED not in str(f)


# ---- AC-14: warm-cache lane still zero plaintext ---------------------

def test_warm_cache_lane_still_zero_plaintext(fresh_fixture: Path) -> None:
    """AC-14. Mutation caught: a cache-hit path that writes the cache
    blob BEFORE the per-probe redaction (RP1) runs, so a subsequent
    warm gather serves pre-redactor bytes from cache."""
    _run_gather(fresh_fixture)
    # Delete the envelope between gathers so the second one re-writes
    # from cache-served probe outputs (strengthens over trivial replay).
    (fresh_fixture / ".codegenie" / "context" / "repo-context.yaml").unlink()
    _run_gather(fresh_fixture)

    plaintext_found_in: list[str] = []
    for path in _walk_all_files(fresh_fixture / ".codegenie"):
        try:
            content = path.read_bytes()
        except OSError:
            continue
        if SEED.encode("utf-8") in content:
            plaintext_found_in.append(str(path.relative_to(fresh_fixture)))
    assert not plaintext_found_in, (
        f"Warm-cache gather leaked plaintext in: {plaintext_found_in}"
    )


# ---- AC-15: audit anchor lane (canonical path) ----------------------

def test_audit_anchor_contains_no_plaintext(fresh_fixture: Path) -> None:
    """AC-15. Mutation caught: any debug-logging change that includes
    raw slice content in the audit record. Canonical path per CLAUDE.md:
    .codegenie/context/runs/, NOT .codegenie/runs/."""
    _run_gather(fresh_fixture)
    runs_dir = fresh_fixture / ".codegenie" / "context" / "runs"
    assert runs_dir.exists(), f"Audit anchor directory missing at {runs_dir}"
    anchors = list(runs_dir.glob("*.json"))
    assert anchors, "No audit anchors written"
    for anchor in anchors:
        content = anchor.read_bytes()
        assert SEED.encode("utf-8") not in content, (
            f"Audit anchor {anchor.name} contains plaintext"
        )


# ---- AC-20: secrets_redacted_count >= 2 on the envelope.written event -

def test_secrets_redacted_count_field_on_envelope_written(fresh_fixture: Path) -> None:
    """AC-20. The fixture seeds the SAME cleartext at two locations
    (src/config.ts + docs/internal-notes.md). Per S3-01 AC-26 dedupe
    contract: findings_count == 2, len(fingerprints) == 1. So the
    secrets_redacted_count field must be >= 2.

    Mutations caught:
      - redactor short-circuit returning slice unchanged → count == 0;
      - set-based dedupe at finding-level (not fingerprint-level) → count == 1;
      - regression that emits envelope.written before redaction ran → 0.
    """
    result = _run_gather(fresh_fixture)
    log_lines = []
    for ln in result.stderr.splitlines():
        ln = ln.strip()
        if ln.startswith("{"):
            try:
                log_lines.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    written_events = [ln for ln in log_lines if ln.get("event") == "envelope.written"]
    assert written_events, (
        "No envelope.written event found in CLI stderr — S3-03 AC-11 "
        "regression OR the gather did not emit structured logs."
    )
    counts = [ln.get("secrets_redacted_count") for ln in written_events]
    assert all(c is not None for c in counts), (
        f"envelope.written event missing secrets_redacted_count field: {written_events}"
    )
    assert max(counts) >= 2, (
        f"secrets_redacted_count={max(counts)} — expected >= 2 "
        f"(both src/config.ts and docs/internal-notes.md must be redacted). "
        f"A set-based finding-level dedupe would silently emit 1; a redactor "
        "short-circuit would emit 0."
    )


# ---- AC-19: determinism --------------------------------------------

def test_two_gathers_byte_identical_modulo_generated_at(tmp_path: Path) -> None:
    """AC-19. Two gathers under two tmp_path copies; strip generated_at;
    assert byte-identity of the YAML payload."""
    def _gather_and_strip(dst: Path) -> bytes:
        shutil.copytree(FIXTURE, dst)
        _run_gather(dst)
        text = (dst / ".codegenie" / "context" / "repo-context.yaml").read_text()
        # Strip the lines containing volatile fields.
        kept = [ln for ln in text.splitlines()
                if not ln.lstrip().startswith(("generated_at:", "run_id:"))]
        return "\n".join(kept).encode("utf-8")

    a = _gather_and_strip(tmp_path / "a")
    b = _gather_and_strip(tmp_path / "b")
    assert a == b, "Two gathers produced divergent envelopes (modulo generated_at)"
```

### Green — make it pass

Skeleton for `gitleaks.py`. The shape is the **post-S6-06-hardening** kernel-conformant form (async `run`, dual-form identity, six-field `ProbeOutput`, chokepoint-derived 8-hex fingerprint, byte-level raw-artifact redaction).

```python
# src/codegenie/probes/layer_g/gitleaks.py
"""GitleaksProbe — Layer G, medium heaviness, fourth Layer G scanner.

NO shared base class with semgrep / ast_grep / ripgrep_curated per
final-design Design-patterns row 7 (SRP + Rule of Three). The probe
emits findings as `match_fingerprint` (8-hex BLAKE3 prefix derived via
the canonical Phase-0 hashing chokepoint) — never the cleartext itself.

CRITICAL DESIGN: gitleaks is a load-bearing carve-out from S6-06 AC-W1.
Gitleaks' raw stdout JSON contains the matched cleartext in the
"Secret" field. The envelope-level _seam_redact_envelope (S3-03) walks
the dict envelope only — it does NOT scrub raw_artifacts bytes. So
this probe MUST redact the "Secret" cleartext from its own raw bytes
BEFORE adding to ProbeOutput.raw_artifacts (AC-RP1). The Writer never
sees gitleaks cleartext; the failure mode is impossible by construction.

Sources:
- ../phase-arch-design.md §"Goals" G5 + §"Gap 4" + §"Gap 5".
- ../ADRs/0005-secret-findings-no-plaintext-persistence.md.
- ../ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md.
- ../stories/S3-01-secret-redactor.md AC-13 / AC-14 (fingerprint format).
"""
from __future__ import annotations

import json
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from codegenie.errors import ProbeTimeoutError, ToolMissingError
from codegenie.exec import ProcessResult, run_external_cli
from codegenie.hashing import content_hash_bytes
from codegenie.probes._shared.scanner_outcome import (
    ScannerFailed,
    ScannerOutcome,
    ScannerRan,
    ScannerSkipped,
)
from codegenie.probes.base import (
    Probe,
    ProbeContext,
    ProbeOutput,
    RepoSnapshot,
    register_probe,
)
from codegenie.types.identifiers import ProbeId

__all__ = ["GitleaksProbe", "GitleaksFinding", "GitleaksSlice"]


_PROBE_ID: Final[ProbeId] = ProbeId("gitleaks")

# Fixed argv prefix — single source of truth for AC-4's argv-pinning test.
_GITLEAKS_ARGV_BASE: Final[tuple[str, ...]] = (
    "gitleaks",
    "detect",
    "--no-banner",
    "--report-format=json",
    "--report-path=-",
    "--no-git",
    "--exit-code", "0",
)


def _fingerprint(b: bytes) -> str:
    """Phase-0 hashing chokepoint — 8 lowercase hex chars. Matches
    S3-01 AC-13 / AC-14 fingerprint format byte-for-byte."""
    return content_hash_bytes(b).removeprefix("blake3:")[:8]


class GitleaksFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    rule_id: str
    file: str
    line: int
    description: str
    match_fingerprint: str  # 8-hex; NEVER the cleartext


class GitleaksSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    outcome: ScannerOutcome
    findings_count: int
    findings_detail: list[GitleaksFinding]


def _parse(raw: bytes) -> tuple[tuple[GitleaksFinding, ...], tuple[bytes, ...], int] | ScannerFailed:
    """Pure parser. Returns either (findings, cleartexts, count) on
    success — the parallel `cleartexts` tuple feeds `_redact_raw_bytes`
    and is dropped from the caller's stack frame after substitution —
    OR a `ScannerFailed` on any JSON / schema error (AC-12b)."""
    try:
        data = json.loads(raw) if raw else []
    except json.JSONDecodeError as e:
        return ScannerFailed(exit_code=0, stderr_tail=f"invalid_json: {str(e)[:200]}", reason="invalid_json")
    if not isinstance(data, list):
        return ScannerFailed(exit_code=0, stderr_tail="invalid_json: top-level not a list", reason="invalid_json")
    findings: list[GitleaksFinding] = []
    cleartexts: list[bytes] = []
    for f in data:
        try:
            cleartext_bytes = f["Secret"].encode("utf-8")
            findings.append(GitleaksFinding(
                rule_id=f["RuleID"],
                file=f["File"],
                line=int(f["StartLine"]),
                description=f.get("Description", ""),
                match_fingerprint=_fingerprint(cleartext_bytes),
            ))
            cleartexts.append(cleartext_bytes)
        except (KeyError, TypeError, ValueError) as e:
            return ScannerFailed(exit_code=0, stderr_tail=f"invalid_json: {str(e)[:200]}", reason="invalid_json")
    return tuple(findings), tuple(cleartexts), len(findings)


def _redact_raw_bytes(
    raw: bytes,
    findings: tuple[GitleaksFinding, ...],
    cleartexts: tuple[bytes, ...],
) -> bytes:
    """Pure byte-level substitution. For each (finding, cleartext)
    pair, replace the cleartext byte sequence with the marker. After
    this returns, the cleartext byte references are dropped (the
    caller's `cleartexts` local goes out of scope when `run` exits)."""
    out = raw
    for finding, cleartext in zip(findings, cleartexts, strict=True):
        marker = f"<REDACTED:fingerprint={finding.match_fingerprint}>".encode("utf-8")
        out = out.replace(cleartext, marker)
    return out


def _stderr_tail(stderr: bytes, *, cap: int = 1024) -> str:
    return stderr[-cap:].decode("utf-8", errors="replace")


@register_probe(heaviness="medium", runs_last=False)
class GitleaksProbe(Probe):
    name: str = "gitleaks"
    version: str = "0.1.0"
    layer: Literal["G"] = "G"
    tier: Literal["base"] = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    declared_inputs: list[str] = ["**/*"]
    cache_strategy: Literal["content"] = "content"
    timeout_seconds: int = 30

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        argv = list(_GITLEAKS_ARGV_BASE) + ["--source", str(repo.root)]
        try:
            result: ProcessResult = await run_external_cli(
                _PROBE_ID, argv, cwd=repo.root, timeout_s=float(self.timeout_seconds),
            )
        except ToolMissingError:
            return self._wrap(ScannerSkipped(reason="tool_missing"), [], b"", "low")
        except ProbeTimeoutError:
            return self._wrap(
                ScannerFailed(exit_code=124, stderr_tail="gitleaks.timeout"),
                [], b"", "low",
            )
        if result.returncode >= 2:
            return self._wrap(
                ScannerFailed(exit_code=result.returncode, stderr_tail=_stderr_tail(result.stderr)),
                [], b"", "low",
            )
        parsed = _parse(result.stdout)
        if isinstance(parsed, ScannerFailed):
            return self._wrap(parsed, [], b"", "low")
        findings, cleartexts, count = parsed
        # Redact raw bytes BEFORE adding to raw_artifacts — AC-RP1.
        redacted_raw = _redact_raw_bytes(result.stdout, findings, cleartexts)
        # `cleartexts` goes out of scope at the end of this method;
        # no other reference is held.
        return self._wrap(
            ScannerRan(findings=[]),  # closed-set; rich detail lives on slice
            list(findings),
            redacted_raw,
            "high",
        )

    def _wrap(
        self,
        outcome: ScannerOutcome,
        findings_detail: list[GitleaksFinding],
        raw_bytes: bytes,
        confidence: Literal["high", "medium", "low"],
    ) -> ProbeOutput:
        slice_ = GitleaksSlice(
            outcome=outcome,
            findings_count=len(findings_detail),
            findings_detail=findings_detail,
        )
        raw_artifacts: list[tuple[str, bytes]] = (
            [("gitleaks-raw.json", raw_bytes)] if raw_bytes else []
        )
        return ProbeOutput(
            schema_slice=slice_.model_dump(mode="json"),
            raw_artifacts=raw_artifacts,
            confidence=confidence,
            duration_ms=0,  # populated by coordinator wrapper
            warnings=[],
            errors=[],
        )
```

### Refactor

- The temptation here is high: at four scanners, the duplicate `try: run_external_cli except ToolMissingError` block is the fourth copy of the same code. **Do not extract.** Each scanner's error model and argv contract differ; the inline shape keeps the code readable as a single sitting. Final-design Design-patterns row 7 holds.
- The `_parse` helper is local to each scanner. Different stdout shapes; no kernel.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/layer_g/gitleaks.py` | New file ≤ 200 LOC — fourth scanner, no shared base; async `run`; chokepoint-derived 8-hex fingerprint; AC-RP1 raw-bytes redaction. |
| `src/codegenie/probes/__init__.py` | One additive import line (collection-point pattern per Phase 0). |
| `tests/unit/probes/layer_g/conftest.py` | NEW — `_make_repo` / `_make_ctx` fixtures (mirror layer_c conftest precedent). May already exist from S6-06; extend if so. |
| `tests/unit/probes/layer_g/test_gitleaks.py` | NEW — 7 unit tests (argv-pinning + fingerprint/raw-redaction + timeout + exit-2 + malformed-JSON + tool-missing + registry/ABC). |
| `tests/unit/probes/layer_g/test_scanner_loc_ceiling.py` | EXTEND — add `"gitleaks"` to the `SCANNER_MODULES` parametrize so the AST-audit + LOC-ceiling tests cover all four scanners. |
| `tests/adv/phase02/test_secret_in_source.py` | NEW — load-bearing adversarial; 8 tests including the AC-19 determinism check. |
| `tests/adv/phase02/fixtures/secret_in_source/src/config.ts` | New fixture file with the literal seed. |
| `tests/adv/phase02/fixtures/secret_in_source/package.json` | New fixture file (minimal valid Node manifest). |
| `tests/adv/phase02/fixtures/secret_in_source/docs/internal-notes.md` | New fixture file (second literal-seed instance, markdown prose). |
| `tests/adv/phase02/fixtures/secret_in_source/README.md` | New fixture file documenting the seed via **placeholder pattern only** (literal MUST NOT appear here — AC-11 enforces). |
| `src/codegenie/schema/probes/layer_g/gitleaks.schema.json` | NEW sub-schema (mirror S6-06 / S4-07 precedent) — `additionalProperties: false` at every level; `findings_detail` array typed; `outcome` discriminator `kind` ∈ {`"ran"`, `"skipped"`, `"failed"`}. May be deferred to S6-08 if the sibling schemas are also batched there — confirm at implementation time. |

## Out of scope

- **`test_no_inmemory_secret_leak.py`** — S7-04 (the *boundary* check via `inspect`; this story is the *on-disk* check). The two together close Gap 4 + Gap 5.
- **Gitleaks rule-pack version recording.** That's S6-08 (`@register_index_freshness_check` for `gitleaks`).
- **Gitleaks git-history scanning.** Phase 2 uses `--no-git` (working tree only); history scanning is Phase 3+ if it lands at all.
- **Cross-scanner secret correlation.** Gitleaks finds X; semgrep's `p/secrets` may find Y. Phase 2 keeps them separate; the Planner correlates.

## Notes for the implementer

1. **The fingerprint contract is exact.** `match_fingerprint = content_hash_bytes(cleartext.encode("utf-8")).removeprefix("blake3:")[:8]` (8 lowercase hex chars, chokepoint-derived). This MUST be byte-for-byte identical to S3-01 AC-13 / AC-14's format. If the formats diverge (e.g., the probe uses 16 hex chars; the redactor uses 8), `<REDACTED:fingerprint=...>` markers from probe-side substitution will not match the envelope-side redactor's markers and AC-13 fails on every gather. The `blake3` PyPI package MUST NOT be imported in `gitleaks.py`; the chokepoint helper is the single source of truth.

2. **Raw-artifact redaction is the load-bearing carve-out.** S6-06 AC-W1 mandates a two-file write split (typed slice + raw scanner bytes) for every Layer G scanner. Gitleaks deviates: the raw bytes contain cleartext in the `"Secret"` field, and the envelope-level `_seam_redact_envelope` (S3-03) does NOT scrub `raw_artifacts: list[tuple[str, bytes]]`. So the probe redacts in-place via `_redact_raw_bytes` BEFORE adding to `ProbeOutput.raw_artifacts`. This is structural defense one rung *earlier* than ADR-0010: the Writer never sees gitleaks cleartext. Pattern reference: **Make illegal states unrepresentable at the I/O boundary** (toolkit). Do NOT extend the envelope redactor to scrub raw_artifacts bytes — that would couple the redactor to bytes-level pattern detection, defeating the chokepoint discipline; the carve-out at source is the right shape.

3. **Cleartext lifetime is bounded to one stack frame.** Inside `run()`, the parsed cleartexts appear as `tuple[bytes, ...]` (the second element of `_parse`'s return). They feed `_redact_raw_bytes` and then go out of scope when `run()` returns. **Do NOT** stash cleartexts on the `GitleaksFinding` model, on `ProbeOutput.warnings`, in a debug log, or in a closure that escapes the method. Mirror S3-01 Notes #198–200 cleartext-lifetime discipline.

4. **`--no-git` is non-negotiable in Phase 2.** History scanning requires a different threat model (the secret may have been committed and removed; do we redact past commits in audit anchors?) — a Phase-3+ design discussion. Phase 2 scans working tree only. The argv-pinning test (AC-4) catches any future drop.

5. **The fixture's second seed instance** (in `docs/internal-notes.md`) is what proves the **two-pathway** redaction coverage. Gitleaks may or may not detect prose-form occurrences depending on rule-pack version, but the envelope-level redactor's pattern-class regex sweep + entropy fallback (S3-01) catches it regardless. If only the gitleaks-found instance were redacted and the markdown one persisted, AC-10 would fail. This is what makes AC-20's `secrets_redacted_count >= 2` load-bearing — two distinct file locations, two findings, but the SAME cleartext means ONE deduplicated fingerprint (per S3-01 AC-26).

6. **`--exit-code 0` overrides gitleaks' default.** Without it, gitleaks exits with code 1 on findings (like semgrep). With `--exit-code 0` set, we get exit 0 on findings + exit ≥ 2 on actual error — a simpler conditional. We can't do this trick for semgrep (no equivalent flag), which is why semgrep has the exit-1-is-findings carve-out (S6-06 AC-15) and gitleaks does not.

7. **Subprocess shells out via `python -m codegenie` in the adversarial test.** It does NOT call `codegenie.gather()` in-process. The reason: the test is verifying the *persisted-file* boundary; any in-process call could accidentally hold the slice in memory in a way that escapes the typed `RedactedSlice` chokepoint. The subprocess form forces the gather through the same surface a real user invokes. **Do NOT** use `["codegenie", ...]` (the console-script may not be on PATH in fresh venvs); always `[sys.executable, "-m", "codegenie", ...]`.

8. **`subprocess.run(..., check=True)` is OK in the adversarial test.** Inside source code (`gitleaks.py`), the discipline is "no `subprocess.run` for external tools" — `run_external_cli` is the single chokepoint. Inside the adversarial test, we are *invoking the CLI itself* — that's appropriate; the `codegenie` binary is the SUT, not an external tool.

9. **AC-19 determinism uses two `tmp_path` copies** of the fixture (NOT two gathers in the same directory). Two gathers in the same directory would cache-hit on the second; determinism is most meaningfully observed across two cold starts. Strip both `generated_at:` and `run_id:` lines before byte-comparison.

10. **The fixture's `README.md` is documentation as code with a self-contamination guard.** A contributor who runs `git grep AKIA` on the repo will find the fixture's README explaining "this is a deliberate seed; do not fix." The README MUST use a *placeholder* (e.g., `AKIA<sixteen-uppercase-alphanumerics>`) and NOT the literal `AKIA1234567890ABCDEF` — otherwise gitleaks scans the README too and pollutes the test's intended two-finding count. AC-11 enforces.

11. **`adv-phase02` is build-fail, not advisory.** S8-03 lands the CI job; this story's tests are the load-bearing portion of that lane. If this test flakes, fix the root cause; do **NOT** add a retry decorator.

12. **The 100 % grep walk is the right shape.** A "smart" version that knows which file types might contain plaintext is fragile — a future probe ships a binary blob (e.g., SCIP index), and the smart walker skips it, and the seed leaks through. `os.walk` + `read_bytes` + `in` is the dumbest, most-mutation-resistant check.

### Design patterns — deferred opportunities surfaced (not promoted to ACs)

13. **`Fingerprint = NewType("Fingerprint", str)` — rule-of-three threshold CROSSED, deferred to S8-02.** S3-01 (Validation #11), S3-02 (#12), S3-03 (#19), and this story together involve six consumer surfaces for the 8-hex fingerprint: `sanitizer.py::_fingerprint`, `RedactedSlice.fingerprints`, `Writer.write` (consumes `envelope.fingerprints`), `gitleaks.py::GitleaksFinding.match_fingerprint`, gitleaks's redaction marker, and the upcoming CLI summary line (S8-02). Production ADR-0033 §3 names primitive obsession on cross-module identifiers as a review-blocker. **Decision:** still defer to S8-02 (the natural concurrent-landing site with the fourth consumer). This story uses `str` deliberately; the format invariant (8 lowercase hex chars; chokepoint-derived) is the structural defense for now. When `Fingerprint` lands, every `match_fingerprint: str` in this module narrows to `match_fingerprint: Fingerprint` in lock-step; no probe-side semantics change.

14. **`_PASSES` registry — speculative; refused.** A `_PASSES: tuple[Callable[[bytes, tuple[GitleaksFinding, ...], tuple[bytes, ...]], bytes], ...]` registry for the byte-redaction step would be premature. There is exactly ONE pass (single-cleartext-substitution); rule-of-three is not crossed. The pure function `_redact_raw_bytes` is the right shape. A future scanner with its own raw-bytes leak (none currently planned) would either get its own carve-out or promote the helper to `codegenie.probes._shared.scanner_redaction`. Toolkit Rule 2 + "three similar lines is better than premature abstraction" applies.

15. **`ParseResult` sum type via `dataclass` — alternative considered, rejected.** Returning `tuple[...] | ScannerFailed` from `_parse` is the closed-set Result shape S6-06 / sbom.py / cve.py already use; introducing a new `ParseResult` ADT would add boilerplate without payoff at one call site. If a Phase-3+ probe needs the same shape, it lifts to `_shared/parse_result.py`. Toolkit Rule 2 applies.

16. **Pure / impure split holds at module level.** `_parse`, `_fingerprint`, `_redact_raw_bytes`, `_stderr_tail` are all pure (bytes/str in, bytes/str out). Only `run` is impure (awaits the subprocess + Phase-0 hashing chokepoint side-effects are bounded). Functional-core / imperative-shell discipline is preserved per CLAUDE.md.

17. **`@register_index_freshness_check(IndexName("gitleaks"))` — owned by S6-08.** This story does NOT register gitleaks' rule-pack version as an index source. S6-08 owns the freshness-registry wiring for every Layer G scanner.
