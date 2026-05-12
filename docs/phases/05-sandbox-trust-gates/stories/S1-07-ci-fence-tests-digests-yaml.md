# Story S1-07 — Six structural CI fence tests + `tools/digests.yaml` placeholders

**Step:** Step 1 — Scaffold packages, contracts, and CI fences
**Status:** Ready
**Effort:** M
**Depends on:** S1-05, S1-06
**ADRs honored:** ADR-0014, ADR-0012, ADR-0013, ADR-0008, ADR-0001

## Context

The six structural CI fence tests are the **load-bearing invariants** of Phase 5 — they fail at PR time the moment a future story introduces an LLM import, a subprocess outside the allowlist, a banned-substring field on `ObjectiveSignals`, a credential-named env var, a direct `validation.*` callsite, or a missing digest. This story collects them in one place along with the `tools/digests.yaml` placeholder entries `SandboxHealthProbe` will read at startup. Every later Phase 5 story re-runs all six on every change (per `stories/README.md §Definition of done`).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy — CI gates` — exact six file names + the AST/introspection logic each performs.
  - `../phase-arch-design.md §Component design — Signal collectors` — "Policy YAML source is the digest-pinned `tools/policy/sandbox-policy.yaml` — NOT the repo's `.codegenie/policy.yaml`".
  - `../phase-arch-design.md §Edge case 19` — `tools/digests.yaml` missing `sandbox.policy_yaml` → `SandboxHealth(reachable=False, reasons=["policy_digest_missing"])`.
  - `../phase-arch-design.md §Tool-use safety` — subprocess allowlist: only `sandbox/did/build.py`, `sandbox/did/network_policy.py`, `sandbox/firecracker/client.py` may import `subprocess`.
  - `../phase-arch-design.md §Goal 8` — `extra="forbid", frozen=True` + introspection CI test.
  - `../phase-arch-design.md §Goal 13` — zero tokens at the Phase 5 package boundary.
- **Phase ADRs (rules this story honors):**
  - `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — ADR-0014 — the static-introspection test name and forbidden substrings (`confidence`, `llm`, `self_reported`, `model_says`).
  - `../ADRs/0012-static-env-allowlist-no-credentials-in-sandbox.md` — ADR-0012 — the deny-substring test: `KEY`/`TOKEN`/`SECRET`/`PASSWORD` cannot pass even if added to the allowlist.
  - `../ADRs/0013-digest-pinned-policy-yaml-codegenie-owned.md` — ADR-0013 — `tools/digests.yaml#sandbox.policy_yaml` is required; presence is enforced this story, value enforcement is S6-03 (rootfs digest validation upgrade).
  - `../ADRs/0008-llm-judge-persona-deferral.md` — ADR-0008 — fence-CI deny-list (`anthropic`, `langgraph`, `chromadb`, `sentence_transformers`).
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — ADR-0001 — Stage 6 chokepoint: only `gates/runner.py` and the orchestrator may call `validation.*`.
- **Source design:**
  - `../final-design.md §Load-bearing commitments check`.
- **High-level impl:**
  - `../High-level-impl.md §Step 1 — Features delivered` (last bullet) + Step 1 done-criteria bullets 1, 4, 5.

## Goal

Ship the six structural CI fence tests under `tests/schema/` and add the four placeholder entries (`sandbox.firecracker`, `sandbox.vmlinux`, `sandbox.rootfs`, `sandbox.policy_yaml`) to `tools/digests.yaml`.

## Acceptance criteria

- [ ] `tools/digests.yaml` exists (create if missing) and contains the four entries under a `sandbox:` top-level key; each carries a string value (placeholder OK for `firecracker`/`vmlinux`/`rootfs`; `policy_yaml` carries the BLAKE3 digest of the real `tools/policy/sandbox-policy.yaml` if S3-05 has shipped it, else a placeholder).
- [ ] `tests/schema/test_no_llm_imports_in_sandbox.py` walks every `*.py` under `src/codegenie/sandbox/` and `src/codegenie/gates/`, parses with `ast`, asserts no `Import`/`ImportFrom` node references `anthropic`, `langgraph`, `chromadb`, or `sentence_transformers`. Test passes today against the Step 1 surface.
- [ ] `tests/schema/test_no_subprocess_outside_build_chokepoint.py` walks every `*.py` under `src/codegenie/sandbox/` and `src/codegenie/gates/`, asserts that the only files importing `subprocess` are exactly `src/codegenie/sandbox/did/build.py`, `src/codegenie/sandbox/did/network_policy.py`, `src/codegenie/sandbox/firecracker/client.py`, `src/codegenie/sandbox/firecracker/network_policy.py`. Test passes today because none of those files exist yet (empty allowlist matches empty actual set; or the allowlist is "files in allowlist OR no subprocess imports yet" — write the assertion in that form).
- [ ] `tests/schema/test_objective_signals_static.py` recursively walks every field reachable from `ObjectiveSignals.model_fields` (including nested models, `Optional[X]`, `Union[X, None]`, dict value types) and asserts no field name (case-insensitive) contains `confidence`, `llm`, `self_reported`, or `model_says`. Uses the `_iter_nested_field_names` helper from S1-03 (re-imports it).
- [ ] `tests/schema/test_env_allowlist_no_credentials.py` constructs a synthetic env dict with keys containing each denied substring (`MY_KEY`, `GITHUB_TOKEN`, `DB_SECRET`, `MY_PASSWORD`, plus mixed-case variants `myToken`, `db_secret`), passes through `env_allowlist.filter`, asserts none of those keys survives.
- [ ] `tests/schema/test_stage6_chokepoint.py` exists as a **placeholder** that asserts the rule's *shape* even before `gates/runner.py` exists: it walks every `*.py` under `src/codegenie/` and asserts that any file containing a `validation.` attribute access either (a) is `src/codegenie/gates/runner.py`, (b) is in the orchestrator allowlist `{"src/codegenie/orchestrator/*.py"}`, or (c) does not exist yet (empty result is acceptable in Step 1). The full AST walk upgrade is S5-04.
- [ ] `tests/schema/test_digests_yaml.py` parses `tools/digests.yaml` and asserts the four keys are present under `sandbox:`. (Value validation is S6-03's upgrade.)
- [ ] All six tests pass (`pytest tests/schema/`) on the Step 1 codebase.
- [ ] TDD plan's red tests exist, are committed, and are green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict tests/schema/` pass (test files are checked too).

## Implementation outline

1. Append (or create) `tools/digests.yaml` with the four placeholder entries.
2. Create `tests/schema/__init__.py` (package marker).
3. Write each of the six fence tests as a standalone module under `tests/schema/`.
4. Each test imports only stdlib (`ast`, `pathlib`, `yaml`, `pydantic`, `typing`) and the Phase 5 modules under scrutiny.

## TDD plan — red / green / refactor

### Red — write the failing test first

Each fence test is written as its own red test. The "red" state for most of them is `FileNotFoundError` (the test file doesn't exist) or `AssertionError` (the file under test has an offending import).

```python
# tests/schema/test_no_llm_imports_in_sandbox.py
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCOPES = [ROOT / "src/codegenie/sandbox", ROOT / "src/codegenie/gates"]
BANNED = {"anthropic", "langgraph", "chromadb", "sentence_transformers"}

def _iter_py(roots):
    for r in roots:
        if not r.exists():
            continue
        yield from r.rglob("*.py")

def test_no_banned_imports_under_sandbox_or_gates():
    offenders = []
    for path in _iter_py(SCOPES):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in BANNED:
                        offenders.append((path, alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in BANNED:
                    offenders.append((path, node.module))
    assert not offenders, f"banned imports found: {offenders}"
```

```python
# tests/schema/test_no_subprocess_outside_build_chokepoint.py
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST = {
    ROOT / "src/codegenie/sandbox/did/build.py",
    ROOT / "src/codegenie/sandbox/did/network_policy.py",
    ROOT / "src/codegenie/sandbox/firecracker/client.py",
    ROOT / "src/codegenie/sandbox/firecracker/network_policy.py",
}
SCOPES = [ROOT / "src/codegenie/sandbox", ROOT / "src/codegenie/gates"]

def _imports_subprocess(path: Path) -> bool:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == "subprocess" for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == "subprocess":
                return True
    return False

def test_subprocess_only_in_allowlisted_chokepoints():
    offenders = []
    for scope in SCOPES:
        if not scope.exists():
            continue
        for py in scope.rglob("*.py"):
            if _imports_subprocess(py) and py not in ALLOWLIST:
                offenders.append(py)
    assert not offenders, f"subprocess imported outside chokepoints: {offenders}"
```

```python
# tests/schema/test_objective_signals_static.py
from codegenie.sandbox.signals.models import ObjectiveSignals, _iter_nested_field_names

FORBIDDEN = ("confidence", "llm", "self_reported", "model_says")

def test_no_forbidden_substring_in_any_field_reachable_from_objective_signals():
    visited = set()
    names = []
    for fname, field in ObjectiveSignals.model_fields.items():
        names.append(fname)
        names.extend(_iter_nested_field_names(field.annotation, visited))
    for n in names:
        for bad in FORBIDDEN:
            assert bad not in n.lower(), f"forbidden substring {bad!r} in field {n!r}"
```

```python
# tests/schema/test_env_allowlist_no_credentials.py
import pytest
from codegenie.sandbox.env_allowlist import filter as env_filter

@pytest.mark.parametrize("k", [
    "MY_KEY", "GITHUB_TOKEN", "DB_SECRET", "MY_PASSWORD",
    "myToken", "db_secret", "user_KEY_id", "OAUTH_password",
])
def test_denied_substring_keys_always_dropped(k):
    out = env_filter({k: "v", "PATH": "/usr/bin"})
    assert k not in out
    assert out["PATH"] == "/usr/bin"
```

```python
# tests/schema/test_stage6_chokepoint.py
"""Step 1 placeholder; full AST walk upgrade in S5-04."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOWED_CALLERS = {
    ROOT / "src/codegenie/gates/runner.py",
}
ORCHESTRATOR_GLOB = "src/codegenie/orchestrator"  # whatever path Phase 3 uses

def _calls_validation_attr(path: Path) -> bool:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "validation":
                return True
    return False

def test_no_module_under_sandbox_or_gates_calls_validation_attr_except_runner():
    src = ROOT / "src/codegenie"
    offenders = []
    if not src.exists():
        return  # nothing to enforce yet
    for py in src.rglob("*.py"):
        if py in ALLOWED_CALLERS:
            continue
        if ORCHESTRATOR_GLOB in str(py):
            continue
        if _calls_validation_attr(py):
            offenders.append(py)
    assert not offenders, f"unexpected validation.* callers: {offenders}"
```

```python
# tests/schema/test_digests_yaml.py
import yaml
from pathlib import Path

DIGESTS = Path(__file__).resolve().parents[2] / "tools/digests.yaml"

def test_digests_yaml_exists():
    assert DIGESTS.exists(), f"{DIGESTS} required"

def test_sandbox_digest_keys_present():
    data = yaml.safe_load(DIGESTS.read_text())
    assert "sandbox" in data
    sb = data["sandbox"]
    for k in ("firecracker", "vmlinux", "rootfs", "policy_yaml"):
        assert k in sb, f"missing sandbox.{k}"
        assert isinstance(sb[k], str) and sb[k]
```

Commit; verify failures (one per missing file or missing entry); implement.

### Green — make it pass

Create `tools/digests.yaml` with placeholder values:

```yaml
# tools/digests.yaml — Phase 5 placeholders
sandbox:
  firecracker: "TBD"          # filled in S6-03
  vmlinux: "TBD"              # filled in S6-03
  rootfs: "TBD"               # filled in S6-03
  policy_yaml: "TBD"          # filled in S3-05
```

The six fence tests above are the implementation — there is no production code to write for this story beyond the digests file.

### Refactor — clean up

- Verify each fence test runs in < 1 second on the Step 1 codebase.
- `test_no_subprocess_outside_build_chokepoint.py` allowlist is intentionally "files that may not exist yet" — paths in `ALLOWLIST` are accepted whether or not they exist at this point.
- ADR-0014 enforcement: re-run `test_objective_signals_static.py` against `ObjectiveSignals` from S1-03. If S1-03 forgot a model_config on a sub-model, this test fails — diagnose by adding a synthetic banned field temporarily.
- The `test_stage6_chokepoint.py` is intentionally a placeholder; the real AST walk on `validation.*` (vs Phase 3's actual API name; the architecture says "calls `validation.*`" — confirm the exact attribute) is S5-04. Note this in the test docstring.
- Logging: fence tests do not log — they assert.

## Files to touch

| Path | Why |
|---|---|
| `tools/digests.yaml` | New/extended file — four `sandbox.*` placeholder entries per ADR-0013 |
| `tests/schema/__init__.py` | New file — package marker |
| `tests/schema/test_no_llm_imports_in_sandbox.py` | New test — Goal 13 fence |
| `tests/schema/test_no_subprocess_outside_build_chokepoint.py` | New test — subprocess allowlist per arch §Tool-use safety |
| `tests/schema/test_objective_signals_static.py` | New test — ADR-0014 introspection fence |
| `tests/schema/test_env_allowlist_no_credentials.py` | New test — ADR-0012 belt-and-suspenders |
| `tests/schema/test_stage6_chokepoint.py` | New test — ADR-0001 Stage 6 chokepoint placeholder (S5-04 upgrades) |
| `tests/schema/test_digests_yaml.py` | New test — `tools/digests.yaml` presence |

## Out of scope

- **Real BLAKE3 digests for `vmlinux`/`rootfs`/`firecracker`/`policy_yaml`** — S3-05 (policy_yaml) + S6-03 (rest); this story keeps "TBD" placeholders.
- **Full AST walk for Stage 6 chokepoint** — S5-04 (once `gates/runner.py` exists).
- **Performance regression tests** — Step 7 (`tests/perf/`).
- **Adversarial tests** (`tests/adversarial/`) — Step 7 (S7-01).
- **Digest VALUE validation** (BLAKE3 hash check) — S6-03 upgrades `test_digests_yaml.py` from presence-only to value-checking.

## Notes for the implementer

- Use `Path(__file__).resolve().parents[2]` to get to repo root in tests; do not hardcode `os.getcwd()`.
- The `BANNED` set in `test_no_llm_imports_in_sandbox.py` matches names from arch §Development view fence-CI rules. Add `openai` or others ONLY with an ADR amendment — do not silently expand the deny-list.
- The `ALLOWLIST` in the subprocess test includes paths that don't exist yet. This is fine — `pathlib.Path` comparison is by string; allowed files simply will never trigger the offending-list because they don't exist.
- The `test_stage6_chokepoint.py` placeholder must not fail when `validation.*` is referenced legitimately (e.g., in Phase 3's existing code). The simplest pragma: limit the walk to `src/codegenie/sandbox` + `src/codegenie/gates` for Step 1. S5-04 widens it to all of `src/codegenie/` once `gates/runner.py` is the legitimate caller.
- For ADR-0014: the recursion in `_iter_nested_field_names` must handle `dict[str, str | int | bool]` — the value annotation is a Union with no `BaseModel`, so it should yield nothing extra. Verify by introducing (temporarily) a `_Foo: BaseModel` field on `ObjectiveSignals` and confirming `_Foo`'s field names are yielded.
- ADR-0013 says the policy YAML's digest is verified at startup. The "presence-only" check this story ships is the cheap predecessor; if you have time, leave a TODO comment in `test_digests_yaml.py` pointing to S6-03 for the value upgrade.
- Performance: every fence test runs in `pytest tests/schema/` on every PR. Keep each test under 1 second. If `test_no_llm_imports_in_sandbox.py` walks too many files, scope it to `src/codegenie/sandbox` and `src/codegenie/gates` only — not the full `src/codegenie/`.
- Coverage: these tests *are* the fences; their pass-rate is the floor, not their own coverage.
