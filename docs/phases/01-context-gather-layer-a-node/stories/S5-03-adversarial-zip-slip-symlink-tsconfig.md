# Story S5-03 — Zip-slip + symlink escape + tsconfig pathological adversarial corpus

**Step:** Step 5 — Adversarial corpus + integration end-to-end + fixture portfolio
**Status:** Ready
**Effort:** M
**Depends on:** S4-02
**ADRs honored:** ADR-0008 (in-process parse caps, no per-probe sandbox), ADR-0009 (no new C-extension parser dependencies), ADR-0011 (no Helm render / no HCL / no `npm ls`)

## Context

The third and final adversarial-test story in Step 5. S5-03 owns the **path-traversal + hand-rolled-parser-pathology** family: three tests pinning the structural defenses that turn untrusted file paths and untrusted JSONC bytes into bounded failures.

The `O_NOFOLLOW`-on-symlink defense (`phase-arch-design.md §"Adversarial tests"` #5) is what prevents a hostile repo's `package.json` symlink to `/etc/passwd` from ever surfacing sensitive contents in the gather output. The defense lives in `parsers/safe_json.py` and `parsers/safe_yaml.py`; this test exercises the end-to-end path: the symlink is in `declared_inputs`, the probe tries to read it, the parser refuses at `os.open` time, the slice records `confidence: low`, sensitive bytes never reach the sanitizer/writer.

The zip-slip-on-kustomize defense (`phase-arch-design.md §"Adversarial tests"` #6, `phase-arch-design.md §"Edge cases"` row 4) is the load-bearing path-containment check inside `DeploymentProbe`. The mitigation is `Path.resolve()` + `is_relative_to(repo_root)`. The test asserts that a hostile `kustomization.yaml` listing `resources: ["../../etc/passwd"]` results in a skipped resource + warning, while valid resources in the same kustomization are still processed.

The pathological-`tsconfig` test (`phase-arch-design.md §"Adversarial tests"` #8) is the JSONC parser's stress test: deeply nested block comments, unterminated strings, circular `extends`. The defense lives in `parsers/jsonc.py` (the state-machine comment stripper) and `probes/node_build_system.py` (the `extends` walker with depth cap + cycle detection from S2-02). The test asserts the gather never hangs.

The risk specific to this story (`High-level-impl.md §"Step 5 — Risks"`): same as S5-01 — assert the **specific** typed exception or specific in-system outcome, never just exit 0 + `confidence: low`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Adversarial tests"` items 5, 6, 8 — the three tests this story lands.
  - `../phase-arch-design.md §"Edge cases"` rows 3, 4, 5 — the in-system behavior these tests assert (symlink refused; kustomize path outside repo; `tsconfig.extends` cycle).
  - `../phase-arch-design.md §"Component design" #6 (DeploymentProbe)` — zip-slip mitigation (`Path.resolve()` + `is_relative_to`).
  - `../phase-arch-design.md §"Component design" #8 (parsers)` — `O_NOFOLLOW` open before read.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md` — `O_NOFOLLOW` is the symlink-escape defense at parse time, not a separate sandbox layer.
  - `../ADRs/0009-no-new-c-extension-parser-dependencies.md` — `jsonc.py` is hand-rolled stdlib; pathological inputs must not require adding a new parser.
  - `../ADRs/0011-no-helm-render-no-hcl-no-npm-ls.md` — `DeploymentProbe` does Kustomize traversal one level deep with a containment check, not full kustomize-build render.
- **Source design:**
  - `../final-design.md §"Adversarial tests"` items 5, 6, 8.
  - `../final-design.md §"Failure modes & recovery"` rows for "Path traversal in kustomization.yaml#resources" and "package.json is a symlink pointing outside repo" and "tsconfig.json#extends chain exceeds 4 levels".
  - `../High-level-impl.md §"Step 5"` adversarial-test list items 5, 6, 8.
- **Existing code (lands earlier — must be on disk before this story starts):**
  - `src/codegenie/parsers/safe_json.py` (S1-02) — `O_NOFOLLOW`, raises `SymlinkRefusedError`.
  - `src/codegenie/parsers/jsonc.py` (S1-04) — pathological JSONC must complete or raise in < 1 s.
  - `src/codegenie/probes/node_build_system.py` (S2-02) — `tsconfig.extends` walker with depth + cycle check.
  - `src/codegenie/probes/deployment.py` (S4-02) — zip-slip containment check; `kustomization.resource_outside_repo` warning ID.
  - `src/codegenie/errors.py` — `SymlinkRefusedError`, `MalformedJSONError` (S1-01).
- **Style reference:** S5-01 (sister story in same step) for adversarial-test layout and fixture-generation conventions.

## Goal

Three adversarial tests under `tests/adv/` exist and pass: (a) a `package.json` symlink to `/etc/passwd` is refused by `O_NOFOLLOW` and sensitive contents never appear in the gather output; (b) a `kustomization.yaml` listing `resources: ["../../etc/passwd"]` results in the resource being skipped with a `kustomization.resource_outside_repo` warning while valid resources are still processed; (c) a pathological `tsconfig.json` (deeply nested block comments + unterminated string + circular `extends`) is parsed or rejected in under 1 s.

## Acceptance criteria

- [ ] `tests/adv/test_symlink_escape_in_declared_inputs.py` synthesizes a Node-repo skeleton in `tmp_path` where `package.json` is a symlink (`os.symlink("/etc/passwd", tmp_path / "package.json")`); calls `safe_json.load(tmp_path / "package.json")` and asserts `pytest.raises(SymlinkRefusedError)`; then runs `codegenie gather` and asserts (i) exit 0, (ii) `language_stack` slice has `confidence: "low"` and `package_json.symlink_refused` in its warnings, (iii) the gather output (`repo-context.yaml`, all `raw/*.json` files, audit record) does **not** contain the string `root:x:0:0:` (the first line of `/etc/passwd`), proving the sensitive content never reached the writer.
- [ ] `tests/adv/test_zip_slip_kustomize.py` synthesizes a fixture: `tmp_path/k8s/kustomization.yaml` listing `resources: ["../../etc/passwd", "./valid-deployment.yaml"]`, with `tmp_path/k8s/valid-deployment.yaml` being a real-shaped `kind: Deployment` manifest; runs `codegenie gather`; asserts (i) exit 0, (ii) `deployment.confidence == "low"` or `"medium"` with `kustomization.resource_outside_repo` in `warnings`, (iii) the valid deployment is still recorded in the `deployment` slice, (iv) the `/etc/passwd` path or `root:` string is **not** in the slice or `raw/deployment.json`.
- [ ] `tests/adv/test_tsconfig_pathological.py` synthesizes a `tsconfig.json` with three pathology vectors combined in one file: (i) 100 nested `/* /* /* ... */ */ */` block-comment opens at the top; (ii) an unterminated string literal in a key (`"compilerOptions": { "out`); (iii) `"extends": "./tsconfig.cycle.json"` with `tsconfig.cycle.json` having `"extends": "./tsconfig.json"`; calls `jsonc.load(tmp_path / "tsconfig.json")` inside a 1.0 s time-bound; asserts either `MalformedJSONError` is raised or `jsonc.load` returns; never times out.
- [ ] The symlink test additionally asserts the structlog event `probe.parser.cap_exceeded` or `probe.symlink_refused` (whichever Phase 1 emits — confirm at land-time) fires, demonstrating the refusal is observable.
- [ ] The zip-slip test additionally asserts that **`Path.resolve()` was the mechanism** (not string-prefix-match) by including a `kustomization.yaml` that lists a path with `..` segments but whose resolved form is still inside `repo_root` (e.g. `"./subdir/../valid-deployment.yaml"`) — that resource must be processed, not skipped. This canary catches the regression where someone "simplifies" the check to a substring-match on `".."`.
- [ ] Each test asserts the **specific** typed exception or specific in-system warning ID, not just exit code 0 (per `High-level-impl.md §"Step 5 — Risks"`).
- [ ] All three tests are marked with `pytest.mark.adv` and `pytest -m adv tests/adv/test_symlink_escape_in_declared_inputs.py tests/adv/test_zip_slip_kustomize.py tests/adv/test_tsconfig_pathological.py` completes in under 6 s on the developer's machine.

## Implementation outline

1. **`tests/adv/test_symlink_escape_in_declared_inputs.py`:**
   - `os.symlink("/etc/passwd", tmp_path / "package.json")`.
   - Direct parser call: `pytest.raises(SymlinkRefusedError)` on `safe_json.load(tmp_path / "package.json")`.
   - CLI end-to-end: run gather; capture `repo-context.yaml` + `raw/*.json` + audit record; grep all of them for `"root:x:0:0"`; assert no match.
   - Structlog capture; assert `probe.symlink_refused` or `probe.parser.cap_exceeded` with `error_kind="symlink_refused"`.
2. **`tests/adv/test_zip_slip_kustomize.py`:**
   - Build the fixture:
     ```
     tmp_path/k8s/kustomization.yaml      ← resources: [".../etc/passwd", "./valid-deployment.yaml", "./subdir/../valid-deployment.yaml"]
     tmp_path/k8s/valid-deployment.yaml   ← apiVersion: apps/v1; kind: Deployment; ...
     ```
   - Run gather; assert the `deployment` slice contains the valid Deployment.
   - Assert `kustomization.resource_outside_repo` in `warnings`.
   - Assert the canary: the `./subdir/../valid-deployment.yaml` resource (which resolves inside repo) **is** processed — proves `Path.resolve()` is the mechanism, not substring `..`.
   - Grep the gather output for `root:x:0:0` or `/etc/passwd`; assert no match.
3. **`tests/adv/test_tsconfig_pathological.py`:**
   - Synthesize `tsconfig.json`:
     ```
     /* /* /* /* (×100) */ */ */ */
     { "extends": "./tsconfig.cycle.json", "compilerOptions": { "out
     ```
   - `tsconfig.cycle.json`: `{ "extends": "./tsconfig.json" }`.
   - `t0 = time.monotonic(); try: jsonc.load(...) except MalformedJSONError: pass; assert time.monotonic() - t0 < 1.0`.
   - Also exercise the full path via `codegenie gather` and assert that `node_build_system.confidence` is `low` or `medium` with one of `tsconfig.extends_cycle`, `tsconfig.extends_depth_exceeded`, or `tsconfig.malformed` in warnings — whichever path actually fires (the test pins "we never hang", not "exactly which warning").

## TDD plan — red / green / refactor

### Red — write the failing test first

Start with the symlink test (simplest setup), then zip-slip (more fixture surface), then tsconfig (multi-vector).

```python
# tests/adv/test_symlink_escape_in_declared_inputs.py
import os
import pytest

from codegenie.errors import SymlinkRefusedError
from codegenie.parsers import safe_json


def test_package_json_symlink_to_etc_passwd_refused(tmp_path):
    target = "/etc/passwd"
    if not os.path.exists(target):
        pytest.skip("/etc/passwd not present (Windows or restricted container)")
    link = tmp_path / "package.json"
    os.symlink(target, link)
    with pytest.raises(SymlinkRefusedError):
        safe_json.load(link)


def test_symlink_escape_under_gather_no_sensitive_content_in_output(tmp_path, run_gather):
    target = "/etc/passwd"
    if not os.path.exists(target):
        pytest.skip("/etc/passwd not present")
    os.symlink(target, tmp_path / "package.json")
    result = run_gather(tmp_path)
    assert result.exit_code == 0
    blob = result.context_yaml_text + "\n".join(result.raw_jsons.values())
    assert "root:x:0:0" not in blob
    assert "package_json.symlink_refused" in result.context["probes"]["language_stack"]["warnings"]
```

```python
# tests/adv/test_zip_slip_kustomize.py
KUSTOMIZATION = """\
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - "../../etc/passwd"
  - "./valid-deployment.yaml"
  - "./subdir/../valid-deployment.yaml"
"""

VALID_DEPLOY = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: webapp
spec:
  replicas: 1
"""


def test_kustomize_zip_slip_refused_valid_resources_processed(tmp_path, run_gather):
    k8s = tmp_path / "k8s"
    k8s.mkdir()
    (k8s / "kustomization.yaml").write_text(KUSTOMIZATION)
    (k8s / "valid-deployment.yaml").write_text(VALID_DEPLOY)
    (k8s / "subdir").mkdir()  # exists so "./subdir/../valid-deployment.yaml" resolves
    (tmp_path / "package.json").write_text('{"name":"x","version":"0.0.0"}')

    result = run_gather(tmp_path)
    assert result.exit_code == 0
    dep = result.context["probes"]["deployment"]
    assert "kustomization.resource_outside_repo" in dep["warnings"]
    # canary: dot-dot inside repo still processed
    assert any("webapp" in str(e) for e in dep.get("environments", [])) or "webapp" in str(dep)
    blob = result.context_yaml_text + "\n".join(result.raw_jsons.values())
    assert "root:x:0:0" not in blob and "/etc/passwd" not in blob
```

```python
# tests/adv/test_tsconfig_pathological.py
import time
import pytest

from codegenie.errors import MalformedJSONError
from codegenie.parsers import jsonc


def test_tsconfig_pathological_completes_under_one_second(tmp_path):
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig_cycle = tmp_path / "tsconfig.cycle.json"
    tsconfig_cycle.write_text('{"extends": "./tsconfig.json"}')
    body = "/* " * 100 + " */ " * 100 + '\n{ "extends": "./tsconfig.cycle.json", "compilerOptions": { "out'
    tsconfig.write_text(body)

    t0 = time.monotonic()
    try:
        jsonc.load(tsconfig)
    except MalformedJSONError:
        pass
    elapsed = time.monotonic() - t0
    assert elapsed < 1.0, f"jsonc.load took {elapsed:.2f}s on pathological tsconfig"
```

Run reds, commit per file, proceed.

### Green — make it pass

The defenses exist in S1-02, S1-04, S2-02, S4-02. If a red test fails for the wrong reason (e.g. `safe_json` raises a generic `OSError` instead of `SymlinkRefusedError`), surface that as a Step-1 or Step-4 gap in the PR body. The fix is small (correct exception mapping); land it here with the explicit "S1-02 follow-up: ELOOP → SymlinkRefusedError mapping" note.

The zip-slip test's canary — `./subdir/../valid-deployment.yaml` being processed — proves `DeploymentProbe` is using `Path.resolve()` and not substring-match. If this assertion fails, S4-02 must be fixed before this PR merges.

### Refactor — clean up

After green:

- Skip-on-Windows guards (all three tests use POSIX path semantics; mark with `pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only adversarial surface")` even though Windows isn't in scope — explicit > implicit).
- Skip-when-no-`/etc/passwd` guard for the symlink test (Docker-distroless and some CI sandboxes don't have it).
- Verify the `run_gather` fixture exposes both `context` (parsed) and `context_yaml_text` (raw bytes) plus `raw_jsons: dict[str, str]` — if the Phase-0 fixture doesn't, extend it once and reuse.
- Confirm cleanup: symlinks under `tmp_path` are not followed by pytest's `tmp_path` cleanup (`shutil.rmtree` follows symlinks by default — pytest uses `ignore_errors=True` but this is a soft risk on shared CI runners).

## Files to touch

| Path | Why |
|---|---|
| `tests/adv/test_symlink_escape_in_declared_inputs.py` | New test file — `O_NOFOLLOW` refuses symlink; sensitive contents never in output |
| `tests/adv/test_zip_slip_kustomize.py` | New test file — `DeploymentProbe` containment check works; valid resources still processed |
| `tests/adv/test_tsconfig_pathological.py` | New test file — `jsonc.py` + `extends` walker complete in < 1 s on hostile JSONC |

## Out of scope

- **Cap-family adversarial tests (yaml billion-laughs, JSON bombs, oversized lockfile)** — owned by S5-01.
- **Yarn regex-DoS / planted `node` shim / `!!python/object` tests** — owned by S5-02.
- **Refining `DeploymentProbe`'s containment check** — if the test fails because the check is wrong, fix it; otherwise out of scope.
- **Helm template rendering attacks** — explicitly out per ADR-0011 (no Helm render in Phase 1).
- **Property-based fuzzing of `jsonc.py`** — Phase 0 / Step 1 author was responsible for local fuzz before merging S1-04 (`High-level-impl.md §"Step 1 — Risks"`). The Step-5 test is the CI gate, not the first defense.

## Notes for the implementer

- **The `subdir/..` canary in the zip-slip test is the load-bearing assertion that the implementation uses `Path.resolve()`.** Without it, a substring-match-on-`..` implementation passes the negative case (the `../../etc/passwd` path is rejected) but fails on legitimate dot-dot inside repos. If a future refactor "simplifies" `DeploymentProbe` to use a substring check, this canary fails immediately. Do not remove it during refactor.
- **`Path.is_relative_to` is Python 3.9+ and works on 3.11.** For 3.12, prefer the standard library; for 3.11, the manual `Path.resolve()` + `repo_root.resolve()` + check-via-parents loop is the fallback (`phase-arch-design.md §"Component design" #6` calls this out). The test doesn't care which the implementation uses, but the implementation should be consistent — confirm at land-time.
- **The symlink test must run on macOS + Linux CI.** macOS's `/etc/passwd` exists and is readable; Linux containers may or may not — guard with `pytest.skip` if the file is absent.
- **Searching gather output for `root:x:0:0` is the load-bearing data-leak assertion.** A weaker assertion (e.g. "the slice is empty") would let a future bug silently leak content via a different field. Always grep the full output (context YAML + raw JSON files + audit record) for the canary string.
- **The pathological tsconfig combines three vectors in one file to maximize coverage per test.** Splitting into three tests is acceptable if the combined fixture is hard to debug; the single-test approach is more concise. Either is fine — pick what's readable.
- **`jsonc.load` may return successfully on the pathological input** (the unterminated-string + nested-comment combo might parse to a partial result if the comment stripping consumes the malformed bits first). That's acceptable — the test asserts "either returns or raises, in < 1 s." This is the design (`final-design.md §"Adversarial tests"` item 8: "`jsonc.py` either parses or raises a typed error; never hangs").
- **`probe.symlink_refused` vs `probe.parser.cap_exceeded`:** Phase 1 may emit either depending on whether the refusal happens at the parser layer (parser-cap event with `error_kind="symlink_refused"`) or at the probe layer (dedicated `probe.symlink_refused`). Don't be too prescriptive in the assertion; check which constant `logging.py` defines (S1-10) and assert that one.
