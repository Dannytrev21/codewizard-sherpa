# Story S7-04 — `ALLOWED_BINARIES` amendment for `dive` + `docker buildx`; `dockerfile-parse` runtime dep

**Step:** Step 7 — `BaseImageProbe` + `ShellInvocationTraceProbe` under the plugin (sandboxed)
**Status:** Ready
**Effort:** S
**Depends on:** S7-03 (sub-schemas + golden files land first — the byte-edit allowlist fence already passes once envelope edits are in, so this story can safely consume rows #8 and #9 without coupling).
**ADRs honored:** Phase 7 ADR-0015 (`ALLOWED_BINARIES` gains exactly `dive` and `docker buildx`; **`strace` is explicitly NOT added by Phase 7** — eBPF host-side is the canonical trace surface); Phase 7 ADR-0009 row #8 (`src/codegenie/exec/__init__.py` `ALLOWED_BINARIES` edit) + row #9 (`pyproject.toml` runtime dep addition); Phase 2 ADR-0001 (omnibus allowed-binaries amendment discipline — every new binary is ratified by ADR, not by quiet edit); Phase 0 ADR-0007 (the closed-frozenset is the supply-chain hygiene line).

## Context

This story is the **smallest byte-edit story in Phase 7** — two rows in `ALLOWED_BINARIES`, one new runtime dependency in `pyproject.toml`, three test-fence guards, and the corresponding negative assertion against `strace` per ADR-0015. Despite the small surface area, the story is **load-bearing for the entire phase**: without `docker buildx` allowlisted, `ShellInvocationTraceProbe` (S7-02) and `DistrolessBuildGate` (S10-04) cannot legally invoke their build command; without `dockerfile-parse`, `BaseImageProbe` (S7-01), `DockerfileBaseImageSwapTransform` (S10-01), and `DockerfileMultiStageRefactorTransform` (S10-02) cannot parse Dockerfiles.

A surfacing note about `strace`: `src/codegenie/exec/__init__.py::ALLOWED_BINARIES` already contains `"strace"` as a pre-Phase-7 entry (Phase 0 / 2 era). Phase 7 ADR-0015 §Decision is explicit that **the Phase-7 amendment does not add `strace`** — the ADR records what Phase 7 adds, not what Phase 7 inherits. The amendment row #8 in ADR-0009 reads "two new rows: `dive` and `docker buildx`." This story (a) keeps `strace` exactly where it is (no removal, no addition), (b) adds the two new rows, (c) adds a fence test that asserts the Phase 7 amendment specifically contributes `dive` and `docker buildx` — and **does not** assert `strace not in ALLOWED_BINARIES` because that would be a falsifying claim against the inherited state. The fence-test posture is: "the Phase 7 amendment is exactly these two rows; future amendments don't sneak in `strace` under a Phase-7 banner." If `strace` is later removed (a Phase 8+ decision), the test stays correct.

The `docker buildx` row warrants a name choice: the actual binary is `docker` (already allowlisted), and `buildx` is a Docker subcommand. The ADR says "`docker buildx`" as a logical entry; the implementer must decide whether this is a single allowlist row `"docker buildx"` (with the allowlist matcher updated to handle space-separated names) or a documentation pointer (since `docker` is already allowlisted). **The ADR's commitment is the public surface** — `ALLOWED_BINARIES` MUST list a row whose presence operators can grep for. Implementation choice (one row `"docker buildx"` vs. two-row decomposition vs. keeping `"docker"` and documenting buildx as a subcommand) is pinned by this story per the existing `codegenie.exec` allowlist semantics — see Notes for the implementer.

`dockerfile-parse` becomes the **one net-new Python runtime dependency** Phase 7 ships. Phase 7 ADR-0013 records this. The dependency is small (pure Python, ~2k LOC, BSD license, used by `atomic-reactor` and similar), and lands in `pyproject.toml [project] dependencies` (not `[project.optional-dependencies]` — the migration plugin loads `dockerfile-parse` unconditionally at import time via `BaseImageProbe`). The `make fence` target's runtime-closure scan (`tests/unit/test_pyproject_fence.py`) must continue to find zero LLM-SDKs in the closure — adding `dockerfile-parse` must not pull a transitive LLM SDK.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §9 (ShellInvocationTraceProbe)` — names `docker buildx` as the build command + `strace` as in-VM informational only.
  - `../phase-arch-design.md §Resource & cost profile` — `dockerfile-parse` named as the one net-new Python runtime dep.
- **Phase ADRs:**
  - `../ADRs/0015-allowed-binaries-amendment-dive-buildx.md` — exact two-binary amendment + `strace` rejection rationale.
  - `../ADRs/0009-phase-7-byte-edit-allowlist-fence.md` rows #8 + #9 (verbatim).
  - `../ADRs/0013-dockerfile-recipe-engine-dockerfile-parse.md` — `dockerfile-parse` is the canonical Dockerfile parser for Phase 7.
- **Existing code:**
  - `src/codegenie/exec/__init__.py` — the `ALLOWED_BINARIES` frozenset. **Read lines 105–130 before editing**: the current set is ordered with `# Phase 3 03-ADR-0012 additions:` comment separator. Mirror that style — add a `# Phase 7 ADR-0015 additions:` comment and the two new rows.
  - `pyproject.toml` — `[project] dependencies` array. Mirror the format of existing rows.
  - `src/codegenie/_fence.py` + `tests/unit/test_pyproject_fence.py` — Phase 0 runtime-closure fence; this story must not break it.
- **Sibling stories:**
  - `S7-01-base-image-probe.md` — consumes `dockerfile-parse`.
  - `S7-02-shell-invocation-trace-probe.md` — consumes the `docker buildx` allowlist permission via `ctx.sandbox_client.spawn(...)`.
  - `S10-01-dockerfile-base-image-swap-recipe.md` and `S10-02` + `S10-04` — also consume.

## Goal

Land the **exactly two-row** amendment to `src/codegenie/exec/__init__.py::ALLOWED_BINARIES` adding `"dive"` and (a row for) `docker buildx`; land the **exactly one-row** amendment to `pyproject.toml [project] dependencies` adding `dockerfile-parse`. Land a fence test that pins the closed-frozenset shape (asserts the Phase 7 amendment contributes exactly these two binaries) and pins the `dockerfile-parse` dep as the only net-new runtime dep. Do not add `strace` (per ADR-0015 §Decision).

## Acceptance criteria

**`ALLOWED_BINARIES` edit — Phase 7 ADR-0009 row #8 (AC-1 through AC-4)**
- [ ] **AC-1** `src/codegenie/exec/__init__.py::ALLOWED_BINARIES` post-edit contains `"dive"` and the `docker buildx` row. Verified by `tests/unit/exec/test_allowed_binaries_phase7_amendment.py::test_dive_present` and `::test_docker_buildx_row_present`.
- [ ] **AC-2** **Closed-frozenset shape pin**: the test reads `ALLOWED_BINARIES` and asserts `len(ALLOWED_BINARIES) == <pre-Phase-7-count> + 2`. The pre-Phase-7 count is read from `tests/fence/_phase7_allowed_binaries_baseline.txt` (one binary per line; the file lists every entry as of Phase 6.5 — `git`, `node`, `semgrep`, `syft`, `grype`, `gitleaks`, `scip-typescript`, `ast-grep`, `rg`, `tree-sitter`, `docker`, `strace`, `npm`, `bwrap`, `sandbox-exec`, `jq`). The Phase-7 amendment adds exactly two. Any further additions in the same PR fail this AC.
- [ ] **AC-3** **`strace` is unchanged (neither added by Phase 7 nor removed)**: `test_strace_phase_7_amendment_does_not_touch_strace` reads the baseline file, asserts `"strace" in baseline`, asserts `"strace" in ALLOWED_BINARIES` post-edit (proves the Phase 7 amendment did not remove `strace`), asserts the Phase 7 amendment's two-row delta is `{"dive", "docker buildx"}` (or the chosen `docker buildx` row name) — i.e., `strace` is **not** in the Phase-7 contribution set. Test name and assertion language must match the ADR-0015 §Decision wording so a future reader's grep finds it.
- [ ] **AC-4** **Diff discipline** (Phase 7 ADR-0009 row #8 enforcement): `git diff src/codegenie/exec/__init__.py` shows only additive lines — two new rows inside the `ALLOWED_BINARIES = frozenset({...})` literal, plus the `# Phase 7 ADR-0015 additions:` comment. **No removed rows. No reordered rows. No `ALLOWED_BINARIES`-adjacent changes** (no edits to `run_allowlisted`, no edits to error messages, no docstring rewrites). Verified by the `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` row-#8 sub-assertion.

**`pyproject.toml` edit — Phase 7 ADR-0009 row #9 (AC-5 through AC-7)**
- [ ] **AC-5** `pyproject.toml [project] dependencies` gains exactly one new entry for `dockerfile-parse` (the line format `"dockerfile-parse>=<min-version>"` mirroring sibling rows; pick the minimum-supported version from PyPI — implementer note: pin a known-stable version, e.g., `>=2.0.0` if 2.x is current; verify by `pip index versions dockerfile-parse`). No other dependency rows are added or modified.
- [ ] **AC-6** **Runtime-closure regression check**: `make fence` (`tests/unit/test_pyproject_fence.py`) green AFTER `dockerfile-parse` is in the closure. Specifically: the FORBIDDEN_LLM_SDKS scanner walks the new dep's transitive closure (via the installed-distribution walker the Phase 0 fence already uses) and asserts no LLM SDK is introduced. **AC fails if `dockerfile-parse` itself or its transitive deps shadow any FORBIDDEN_LLM_SDK** — extremely unlikely but the fence is the binding check.
- [ ] **AC-7** **Diff discipline** (row #9 enforcement): `git diff pyproject.toml` shows exactly one new line under `[project] dependencies` (plus list-comma maintenance if applicable). No edits to `[tool.importlinter]`, `[tool.pytest.ini_options]`, `[tool.mypy]`, or other sections in the same diff. The byte-edit allowlist fence row #9 sub-assertion enforces this.

**Negative-space discipline (AC-8 through AC-10)**
- [ ] **AC-8** **No `strace` invocation in Phase 7 code paths**: `tests/fence/test_no_strace_invocation_in_phase7.py` AST-walks every Python file under `plugins/distroless-migration--node--npm/` AND `src/codegenie/primitives/vuln_provenance/` and asserts no `Call` node references the string literal `"strace"` (in an argv list, as a `binary` kwarg, as a `subprocess.run` first-positional). One planted-violation case (parametrized) plants `subprocess.run(["strace", "-f", "echo"])` into a tmp-path module and asserts the walker fires. **This complements the S7-02 AST fence** — that one rejects all subprocess; this one specifically catches `strace`-string references in `argv` lists even when the surrounding call shape is allowlisted.
- [ ] **AC-9** **No new dep beyond `dockerfile-parse`**: `test_phase7_amendment_pyproject_delta::test_only_one_new_runtime_dep` parses the baseline `pyproject.toml` (committed at `tests/fence/_phase7_pyproject_baseline.toml`) vs current; asserts `set(current.deps) - set(baseline.deps) == {"dockerfile-parse"}` (matching the exact name, version-spec-tolerant). Snuck-in additional deps fail this AC.
- [ ] **AC-10** **`make lint-imports` green** — the existing import-linter contract under `pyproject.toml [tool.importlinter]` is unchanged by this story (Phase 7 contracts for `vuln_provenance` and the migration plugin tree live in S1-06 + S5-03). Importing `dockerfile-parse` from `plugins/distroless-migration--node--npm/probes/base_image_probe.py` is permitted (the contract bars LLM SDKs, not third-party libs at large).

**`docker buildx` row representation pinning (AC-11)**
- [ ] **AC-11** **Pick + pin one of the two implementation strategies** (Notes for implementer below) and add a docstring comment in `src/codegenie/exec/__init__.py` adjacent to the new row(s) referencing Phase 7 ADR-0015 §Decision and the strategy choice. The fence row #8 sub-assertion is parametrized over the chosen strategy:
  - **Strategy A (single-row, space-tolerant matcher)**: add `"docker buildx"` as a single allowlist row; update the `argv[0] in ALLOWED_BINARIES` check (already on line ~274) to handle the `["docker", "buildx", ...]` → `"docker buildx"` lookup. Pro: one logical-entity-one-row; mirrors ADR-0015 wording verbatim. Con: matcher complexity grows; one-line change to `run_allowlisted`'s pre-spawn check that **is itself a byte-edit to a Phase 0–6.5 file** — would need row-#8 expansion or a separate allowlist row.
  - **Strategy B (documentation-only — `"docker"` is already allowlisted)**: add a comment row `# "docker buildx" — see Phase 7 ADR-0015; the existing "docker" allowlist row admits this subcommand` and **do not** add a separate `frozenset` entry for `"docker buildx"`. Pro: zero matcher edit; row #8's "exactly two new rows" becomes "exactly one new `frozenset` row (`dive`) plus a documentation comment for `docker buildx`." Con: the comment is convention, not enforcement — the fence test row-#8 sub-assertion must understand this.
  - **Pinned strategy: A** (single-row, space-tolerant matcher) because the ADR-0015 verbatim wording is "**two** new rows" and Strategy B reduces to one row + a comment, defeating the audit-grep utility of the allowlist. Strategy A's matcher edit (one additional `if` clause) is the minimum surgical change; the byte-edit fence's row #8 wording explicitly includes the matcher-edit line as part of the row-#8 budget. **Implementer note**: if the matcher edit grows beyond one line (e.g., needs a helper function), STOP and surface — that's a Strategy A/B re-vote, not a quiet allowlist-row scope creep.

## Implementation outline

1. **Baseline files first.** Create:
   - `tests/fence/_phase7_allowed_binaries_baseline.txt` — one binary per line (sorted), the exact set as of Phase 6.5. (Generate by running `python -c "from codegenie.exec import ALLOWED_BINARIES; print(*sorted(ALLOWED_BINARIES), sep='\n')"` against the current branch and committing the output verbatim.)
   - `tests/fence/_phase7_pyproject_baseline.toml` — a copy of the current `pyproject.toml` (or a minimal `[project.dependencies]`-only extract). Used by AC-9's diff-shape test.

2. **`src/codegenie/exec/__init__.py` edit (Strategy A):**
   - Add the comment + two rows inside `ALLOWED_BINARIES`:
     ```python
     ALLOWED_BINARIES: frozenset[str] = frozenset(
         {
             # ... existing entries ...
             "jq",
             # Phase 7 ADR-0015 additions:
             "dive",            # supply-chain layer inspection (BaseImageProbe / portfolio assertions)
             "docker buildx",   # buildx is a docker subcommand; the matcher in run_allowlisted
                                # handles space-tolerant lookup. See Phase 7 ADR-0015 §Decision.
         }
     )
     ```
   - Update the matcher in `run_allowlisted` (and `run_external_cli` if it has its own check) so that `argv == ["docker", "buildx", ...]` resolves to `"docker buildx"` in `ALLOWED_BINARIES`. The narrow change is one line:
     ```python
     binary = argv[0] if len(argv) < 2 else (
         f"{argv[0]} {argv[1]}" if f"{argv[0]} {argv[1]}" in ALLOWED_BINARIES else argv[0]
     )
     ```
     (Or extract `_resolve_binary_name(argv)` for clarity; keep it ≤ 5 LOC.) **Do not** change error messages, docstrings, or any other line in the function.

3. **`pyproject.toml` edit:**
   - Open the file; find `[project] dependencies = [`. Insert `"dockerfile-parse>=2.0.0",` (replace version with the actual current-stable pinned minimum) in alphabetic order with siblings.
   - **No other edits.** Specifically: do not touch `[tool.importlinter]` (S1-06 / S5-03 own); do not touch `[tool.mypy]` (no relaxations needed); do not touch `[tool.pytest.ini_options]`.

4. **Tests:**
   - `tests/unit/exec/test_allowed_binaries_phase7_amendment.py` — AC-1, AC-2, AC-3, AC-11.
   - `tests/unit/exec/test_run_allowlisted_handles_docker_buildx.py` — `run_allowlisted(["docker", "buildx", "build", "..."])` is admitted (no `DisallowedSubprocessError`); `run_allowlisted(["dive", "image", "nginx:alpine"])` admitted.
   - `tests/fence/test_no_strace_invocation_in_phase7.py` — AC-8 (AST-walk over plugin tree).
   - `tests/fence/test_phase7_pyproject_delta.py` — AC-7, AC-9.

5. **Locally verify** `dockerfile-parse` is installable: `uv pip install dockerfile-parse`; import in a fresh `python -c "import dockerfile_parse; print(dockerfile_parse.__version__)"`. Confirm the import name `dockerfile_parse` (underscore) — note the dep distribution is `dockerfile-parse` (hyphen); both forms appear in different contexts.

6. **Run** `make check` end-to-end. Expect: `tests/unit/test_pyproject_fence.py` green (the FORBIDDEN_LLM_SDKS scan walks the new closure and finds nothing); `make lint-imports` green; `mypy --strict` green; Phase 3–6.5 regression suite green (the matcher edit must not regress existing `run_allowlisted` callsites — particularly Phase 2's `docker` invocations and Phase 3's `npm`/`bwrap` invocations).

## TDD plan (red → green → refactor)

**Red 1** — write `test_allowed_binaries_phase7_amendment.py::test_dive_present`. Pytest fails: `"dive" not in ALLOWED_BINARIES`.

**Green 1** — add `"dive"` to the frozenset. Test green.

**Red 2** — `test_docker_buildx_row_present`. Fails.

**Green 2** — add `"docker buildx"` (Strategy A); update matcher. Test green.

**Red 3** — `test_run_allowlisted_handles_docker_buildx.py::test_docker_buildx_argv_admitted`. Uses a stub spawner; asserts no `DisallowedSubprocessError`. Currently fails because the matcher returns `"docker"` as `binary`, and the check would pass through the existing `"docker"` row — actually green by accident. **Adversarial sub-case**: parametrize with a fake `("docker", "buildkit-not-a-real-thing", ...)` and assert it falls through to the existing `"docker"` row (admitted), then a `("nosuch", "buildx", ...)` raises `DisallowedSubprocessError`. This pins the matcher's correctness.

**Red 4** — `test_phase7_pyproject_delta.py::test_only_one_new_runtime_dep`. Fails because `pyproject.toml` is unchanged.

**Green 4** — add `dockerfile-parse>=2.0.0`. Test green.

**Red 5** — `test_no_strace_invocation_in_phase7.py` with the planted-violation parametrize case. Initially fails because the walker doesn't exist.

**Green 5** — implement the walker; live-file check green; planted-violation red-by-construction.

**Refactor** — extract `_resolve_binary_name(argv)` helper if the matcher edit grows beyond two lines. Re-run `make check`; verify Phase 3–6.5 regression-cassette replay byte-equal (cost ledger ε ≤ $0.01) — the matcher change could affect `npm`/`docker`/`bwrap` callsites in Phase 3.

**Phase 3–6.5 regression-cassette evidence (Rule 12 fail-loud)** — record the cassette-replay byte-equality output in `_attempts/S7-04.md` as a 3-line block (cassette name, byte-equality verdict, cost-ledger ε). If any cassette diverges, the matcher edit is wrong; surface immediately.

## Files to touch

**New files:**
- `tests/fence/_phase7_allowed_binaries_baseline.txt`
- `tests/fence/_phase7_pyproject_baseline.toml`
- `tests/unit/exec/test_allowed_binaries_phase7_amendment.py`
- `tests/unit/exec/test_run_allowlisted_handles_docker_buildx.py`
- `tests/fence/test_no_strace_invocation_in_phase7.py`
- `tests/fence/test_phase7_pyproject_delta.py`

**Edited files (Phase 7 ADR-0009 byte-edit allowlist):**
- `src/codegenie/exec/__init__.py` — **row #8**: two new `frozenset` entries (`dive`, `docker buildx`) + the matcher's one-line space-tolerant lookup.
- `pyproject.toml` — **row #9**: one new entry under `[project] dependencies` (`dockerfile-parse>=<pinned>`).

## Out of scope

- **Adding `strace`** — Phase 7 ADR-0015 §Decision rejects. **This story explicitly does NOT add `strace`.** The existing pre-Phase-7 entry is unchanged.
- **Removing `strace`** — out of scope. A future phase may revisit (Phase 7 ADR-0015 §Reversibility flags it as straightforward but defers).
- **Adding other `dockerfile-parse` adjacent deps** — `dockerfile-parse` alone. Any pull from `atomic-reactor`'s ecosystem (e.g., `osbs-client`) is out of scope; if `dockerfile-parse` transitively pulls them in, the runtime-closure fence (AC-6) catches it as a non-LLM-SDK closure expansion the story executor should surface.
- **Pinning a `dockerfile-parse` upper bound** — implementer decides; the convention across the repo's `pyproject.toml` is "minimum-supported, no upper cap unless known-broken." Mirror.
- **Loader-side `external_tools` resolver fail-fast** — S8-01 (`plugin.yaml requirements.external_tools: [docker, dive, docker-buildx]`) owns the fail-fast-if-binary-missing path.
- **The sandbox-side `docker buildx` actual invocation** — S7-02 + S10-04 own. This story authorizes the binary; doesn't invoke it.

## Notes for the implementer

- **Rule 3 — surgical.** Two lines in `ALLOWED_BINARIES`. One line in `pyproject.toml`. One line (≤ 5 LOC if extracted) in the matcher. Anything more and the byte-edit fence row #8 / #9 will fail. **Specifically**: do not "improve while you're here" the comment block above `ALLOWED_BINARIES`, do not reorder Phase-2 / Phase-3 amendment groupings, do not edit the error message of `DisallowedSubprocessError`.
- **Rule 7 — surface conflicts.** The pre-existing `"strace"` entry contradicts (in spirit) Phase 7 ADR-0015's anti-`strace` posture. **Do not** quietly remove `"strace"` — that's a Phase 8+ decision per ADR-0015 §Reversibility. Do surface the dissonance in `_attempts/S7-04.md` so a future engineer reading the audit trail sees the conflict + the deferral.
- **Rule 11 — match conventions.** `# Phase 7 ADR-0015 additions:` is the comment style — mirror `# Phase 3 03-ADR-0012 additions:` (line ~124) which is the existing precedent in this file. Two-space indent inside the frozenset literal. Alphabetic sort within an amendment group (so `dive` before `docker buildx`).
- **Rule 12 — fail loud.** If the matcher edit causes a Phase 3 cassette to diverge by even one byte, **stop** and surface. The matcher is on the hot path for every external-CLI call in the codebase; a wrong `binary` resolution silently downgrades supply-chain hygiene.
- **`docker buildx` is a subcommand, not a binary.** The matcher resolves `argv == ["docker", "buildx", ...]` to the allowlist row `"docker buildx"` so operators reading the frozenset can grep for the actual logical entity they're auditing. **Do not** rely on the existing `"docker"` row admitting everything — that's Strategy B (rejected; see AC-11).
- **The `dockerfile-parse` package is import-named `dockerfile_parse`** (underscore). The `pyproject.toml` dep name is `dockerfile-parse` (hyphen). PEP 503 normalization handles this; mention it in the comment above the new dep row.
- **Cost-ledger byte-equality** is a real CI gate from Phase 3 (per High-level-impl S3-03 cassette replay). The matcher edit could plausibly change which binaries are spawned in regression runs. Run `make check` AND `pytest bench/vuln-remediation/cassettes/` (or whatever the cassette-replay invocation is — verify in the repo's `Makefile`) and confirm ε ≤ $0.01.
- **`dockerfile-parse` version pin** — at the time of writing, 2.x is current. Pin `>=2.0.0` unless `pip index versions` reveals a known-broken minor. **Do not** pin a strict `==`; the repo convention is open lower bounds, conservative upper caps only when needed.
- **Token budget (Rule 6).** This story is the smallest in the step. ≈ 1.5k tokens to implement. If you find yourself approaching 3k, you're over-engineering — the fence is doing the work; the code change is genuinely two-and-a-half lines.
