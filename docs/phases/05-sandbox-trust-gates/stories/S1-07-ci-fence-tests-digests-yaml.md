# Story S1-07 — Six structural CI fence tests + `tools/digests.yaml` placeholders

**Step:** Step 1 — Scaffold packages, contracts, and CI fences
**Status:** HARDENED
**Effort:** M
**Depends on:** S1-02, S1-03, S1-05, S1-06
**ADRs honored:** ADR-0014, ADR-0013, ADR-0012, ADR-0009, ADR-0008, ADR-0001

## Validation notes

Hardened on 2026-05-23 by `phase-story-validator`. See [`_validation/S1-07-ci-fence-tests-digests-yaml.md`](_validation/S1-07-ci-fence-tests-digests-yaml.md) for the full audit log. Highlights:

- **Wrong import path corrected.** Draft `test_objective_signals_static.py` imported `_iter_nested_field_names` from `codegenie.sandbox.signals.models` — but S1-03 ships `iter_nested_field_names` (no leading underscore) in `codegenie.sandbox.signals._introspection`, and S1-03 AC-1b *explicitly forbids* either name from appearing in `models.__all__`. Draft would `ImportError` on first run. Rewritten + AC-OS-1/OS-2 pin the canonical import + type-driven invocation.
- **Subprocess-chokepoint count reconciled to 4.** Draft AC text said 3 chokepoints; draft code listed 4. ADR-0009 (Firecracker host-side nftables) is the resolution — it was accepted *after* the original 3-file decision and adds the 4th. The arch §Tool-use safety bullet (still says 3) is silently amended by ADR-0009; this story's AC text is the post-ADR-0009 source-of-truth (AC-SP-1).
- **Six planted-positive companions added.** Every fence walker scope is empty or near-empty on the Step 1 codebase, so a buggy walker (`for node in []`, an `ast.Imp0rt` typo, a `return` at top of body) passes vacuously. Mirroring `tests/fence/test_no_llm_in_transforms.py` and `tests/fence/test_lint_imports_catches_planted_leak.py`, every fence test now ships an in-test planted-positive companion that constructs a synthetic AST string in-memory and asserts the walker fires (AC-PP-1..AC-PP-6). No committed planted files.
- **ADR-0012 belt-and-suspenders property pinned.** Draft `test_env_allowlist_no_credentials.py` only denied keys that aren't in the allowlist anyway. AC-EA-3 monkeypatches an offending key INTO the allowlist and re-asserts the filter drops it — exercising the actual ADR-0012 invariant (deny runs as an independent gate, not "skip-if-not-in-allowlist").
- **Stage 6 chokepoint placeholder tightened.** Draft was doubly-vacuous (no `validation.<attr>` callsite exists on Step 1; walker also misses `from codegenie.validation import X` + `import … as v`). Out-of-scope now explicitly defers the full ImportFrom + aliased-import walk to S5-04; planted-positive (AC-PP-5) exercises the placeholder shape.
- **Shared `_walkers.py` kernel extracted.** Six fence tests share `ROOT = Path(__file__).resolve().parents[2]`, `_iter_py(roots)`, and the `ast.parse(path.read_text())` template — rule-of-three is cleared on day one. `tests/schema/_walkers.py` ships the kernel; each fence test is a thin "compose walker + assert" body (AC-W-1..AC-W-3).
- **Test-file purity invariant added** (AC-PU-1) — `tests/schema/test_schema_fence_purity.py` AST-walks every `tests/schema/test_*.py` and pins the import set; forbids fence tests from importing the modules they police.
- **`_BANNED_LLM_IMPORTS` divergence vs `FORBIDDEN_LLM_SDKS` documented.** Phase-5 sandbox/gates deny list is `{anthropic, langgraph, chromadb, sentence_transformers}` per arch — deliberately different from gather-pipeline `FORBIDDEN_LLM_SDKS` (`{anthropic, langgraph, openai, langchain, transformers}`). Module docstring + AC-LL-2 sync check pin the byte-equality with arch §"Two new top-level packages."
- **`tools/digests.yaml` root shape pinned** — root must be `dict`; `sandbox` value must be `dict`; values must be exactly `"TBD"` placeholder OR a 64-char hex digest (no mid-partial states). Prevents `yaml.safe_load("- a")` → opaque `TypeError` (AC-DG-3..AC-DG-6).
- **`Path` membership compared via `path.relative_to(ROOT)`** (AC-SP-3) — macOS case-insensitivity + symlinked `ROOT` would otherwise cause silent false-negatives.
- **Quality-gate AC aligned with S1-02..S1-06 hardening pattern** — explicit ruff / mypy / pytest / no-skip-no-xfail bullets.

## Context

The six structural CI fence tests are the **load-bearing invariants** of Phase 5 — they fail at PR time the moment a future story introduces an LLM import, a subprocess outside the allowlist, a banned-substring field on `ObjectiveSignals`, a credential-named env var, a direct `validation.*` callsite, or a missing digest. This story collects them in one place along with the `tools/digests.yaml` placeholder entries `SandboxHealthProbe` will read at startup. Every later Phase 5 story re-runs all six on every change (per `stories/README.md §Definition of done`).

The fence tests live at the **schema tier** (`tests/schema/`) — deliberately distinct from the sandbox/gates unit tests at `tests/sandbox/` and `tests/gates/`. The schema-tier invariants must survive deletion of the sandbox-tier tests; that is what makes them a structural floor rather than a defense-in-depth duplicate. The substring-screen test (AC-OS) is the canonical example: S1-03 already ships a sandbox-tier substring screen (`tests/sandbox/test_objective_signals_introspection.py`), and this story re-asserts the same invariant at `tests/schema/test_objective_signals_static.py` so ADR-0014 is enforced even if the sandbox-tier suite is restructured. Crucially, the schema-tier test **imports the same `iter_nested_field_names` walker** from `sandbox.signals._introspection` — re-declaring the walker locally would silently fork the trust anchor and defeat the cross-tier invariant.

Each fence test ships an in-test **planted-positive companion** (mirroring `tests/fence/test_no_llm_in_transforms.py` + `tests/fence/test_lint_imports_catches_planted_leak.py`) that constructs a synthetic AST string in-memory and asserts the walker fires. Without planted-positives, every fence is silently-vacuous on the Step 1 codebase (the `src/codegenie/sandbox/` and `src/codegenie/gates/` trees are nearly empty) and Rule 9 ("tests verify intent, not just behavior") fails — a regression that deletes the walker body or typos `ast.Import` still passes.

The Phase-5 sandbox/gates banned-LLM set is `{anthropic, langgraph, chromadb, sentence_transformers}` per arch §"Two new top-level packages." This is **deliberately different** from the gather-pipeline `codegenie._fence.FORBIDDEN_LLM_SDKS` (`{anthropic, langgraph, openai, langchain, transformers}`) — different scope: `chromadb`/`sentence_transformers` are RAG-stack libraries that must not appear in deterministic gate code; `openai`/`langchain`/`transformers` are gather-pipeline closures policed by `tests/unit/test_pyproject_fence.py`. A future contributor "fixing" the deny list by importing `FORBIDDEN_LLM_SDKS` would silently narrow + widen the scope; the byte-equality sync AC (AC-LL-2) prevents this.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy — CI gates` (lines 907-914) — exact six file names + the AST/introspection logic each performs.
  - `../phase-arch-design.md §Component design — Signal collectors` — "Policy YAML source is the digest-pinned `tools/policy/sandbox-policy.yaml` — NOT the repo's `.codegenie/policy.yaml`".
  - `../phase-arch-design.md §Edge case 19` — `tools/digests.yaml` missing `sandbox.policy_yaml` → `SandboxHealth(reachable=False, reasons=["policy_digest_missing"])`.
  - `../phase-arch-design.md §Tool-use safety` (line 844) — subprocess allowlist (3 chokepoints there; **post-ADR-0009 the count is 4** — see Notes for the implementer).
  - `../phase-arch-design.md §Goal 8` — `extra="forbid", frozen=True` + introspection CI test.
  - `../phase-arch-design.md §Goal 13` — zero tokens at the Phase 5 package boundary.
- **Phase ADRs (rules this story honors):**
  - `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — ADR-0014 — the static-introspection test name and forbidden substrings (`confidence`, `llm`, `self_reported`, `model_says`).
  - `../ADRs/0013-digest-pinned-policy-yaml-codegenie-owned.md` — ADR-0013 — `tools/digests.yaml#sandbox.policy_yaml` is required; presence is enforced this story, value enforcement is S6-03.
  - `../ADRs/0012-static-env-allowlist-no-credentials-in-sandbox.md` — ADR-0012 — the deny-substring test: `KEY`/`TOKEN`/`SECRET`/`PASSWORD` cannot pass **even if added to the allowlist** (the belt-and-suspenders property exercised by AC-EA-3).
  - `../ADRs/0009-firecracker-network-policy-host-side-nftables.md` — ADR-0009 — adds `firecracker/network_policy.py` as the 4th subprocess chokepoint (post-ADR-0009 source-of-truth for the 4-file allowlist).
  - `../ADRs/0008-llm-judge-persona-deferral.md` — ADR-0008 — the LLM-import deny scope.
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — ADR-0001 — Stage 6 chokepoint: only `gates/runner.py` and the orchestrator may call `validation.*`.
- **Source design:**
  - `../final-design.md §Load-bearing commitments check`.
- **High-level impl:**
  - `../High-level-impl.md §Step 1 — Features delivered` (last bullet) + Step 1 done-criteria bullets 1, 4, 5.
- **Prior validated stories carried forward:**
  - `S1-02-sandbox-contract-protocol-models.md` (HARDENED) — `SandboxSpec.env: Mapping[str, str]` shape this story's `env_allowlist.filter` output must conform to.
  - `S1-03-objective-signals-models.md` (HARDENED) — pins `iter_nested_field_names` (no underscore) in `sandbox.signals._introspection`; the load-bearing import for AC-OS-1.
  - `S1-05-registries-and-env-allowlist.md` (HARDENED) — pins `env_allowlist.filter(env: Mapping[str, str]) -> dict[str, str]` + `ALLOWLIST` constant. AC-EA-3 monkeypatches `ALLOWLIST` to exercise ADR-0012 belt-and-suspenders.
  - `S1-06-gate-catalog-schema-stub.md` (HARDENED) — establishes the "fence test cites ADR in module docstring + `__all__` exact + ban-unsafe-API" module-purity pattern that this story carries forward at the test-file level via `tests/schema/test_schema_fence_purity.py`.
- **Codebase precedents:**
  - [`tests/fence/test_no_llm_in_transforms.py`](../../../../../tests/fence/test_no_llm_in_transforms.py) — Phase 3 — runtime-closure walker with planted-positive subprocess companion; the "mutation-resistance via shared scanner" idiom this story mirrors statically.
  - [`tests/fence/test_lint_imports_catches_planted_leak.py`](../../../../../tests/fence/test_lint_imports_catches_planted_leak.py) — Phase 3 — planted-positive subprocess pattern with `pytest.fail` over `skip` and CODEOWNERS framing. This story inherits the "no skip / no xfail" discipline.
  - [`tests/unit/test_pyproject_fence.py`](../../../../../tests/unit/test_pyproject_fence.py) — Phase 0 — `EXPECTED_FORBIDDEN_SET = frozenset({...})` + sync test asserting equality with `FORBIDDEN_LLM_SDKS`. Precedent for the byte-equality drift-fence pattern; AC-LL-2 mirrors this exactly with the Phase-5 `_BANNED_LLM_IMPORTS` set.

## Goal

Ship under `tests/schema/`: (a) an `__init__.py` package marker, (b) a shared `_walkers.py` kernel (`ROOT`, `iter_py`, `iter_top_level_imports`), (c) six structural fence tests (LLM-import deny, subprocess allowlist, `ObjectiveSignals` substring screen, env-allowlist deny-substring, Stage 6 chokepoint placeholder, `tools/digests.yaml` presence/shape) **each with an in-test planted-positive companion** proving the walker fires, (d) `test_schema_fence_purity.py` pinning the import set of every fence test. Plus: add the four placeholder entries (`sandbox.firecracker`, `sandbox.vmlinux`, `sandbox.rootfs`, `sandbox.policy_yaml`) to `tools/digests.yaml`. The `_BANNED_LLM_IMPORTS` set is `frozenset({"anthropic", "langgraph", "chromadb", "sentence_transformers"})` (Phase-5 scope; **deliberately different from gather-pipeline `FORBIDDEN_LLM_SDKS`**); the subprocess allowlist is the 4-chokepoint set post-ADR-0009 (`did/build.py`, `did/network_policy.py`, `firecracker/client.py`, `firecracker/network_policy.py`). All comparisons use `path.relative_to(ROOT)` (not absolute-Path identity) to survive macOS case-insensitivity and symlinked `ROOT`. The substring-screen test re-imports the canonical `iter_nested_field_names` from `sandbox.signals._introspection` (S1-03) — re-declaring the walker locally is forbidden.

## Acceptance criteria

### A. Shared `_walkers.py` kernel

- [ ] **AC-W-1** `tests/schema/_walkers.py` exists with module docstring (one paragraph) citing this story (S1-07) and naming `tests/fence/test_no_llm_in_transforms.py` as the closest sibling precedent.
- [ ] **AC-W-2** Public surface: `__all__ = ["ROOT", "iter_py", "iter_top_level_imports"]` (alphabetized, exact). `ROOT: Final[Path] = Path(__file__).resolve().parents[2]`. `iter_py(*roots: Path) -> Iterator[Path]` yields every `*.py` under each root that exists (skips non-existent roots silently — Step 1 may not have created every scope yet). `iter_top_level_imports(path: Path) -> Iterator[str]` parses with `ast`, yields the top-level module name (first dot-split segment) for every `ast.Import` alias and every `ast.ImportFrom` (skips `ImportFrom` with `level > 0` — relative imports are scoped, not module-level deps).
- [ ] **AC-W-3** Tests in `tests/schema/test_walkers.py` cover: (a) `iter_py` on a non-existent root yields nothing without raising; (b) `iter_py` yields paths from multiple roots; (c) `iter_top_level_imports` on `"import a.b.c"` yields `"a"`; on `"from a.b import c"` yields `"a"`; on `"from . import x"` (relative) yields nothing; on `"import a, b"` yields both `"a"` and `"b"`; (d) `ROOT` is `Path(__file__).resolve().parents[2]`.

### B. `tests/schema/__init__.py` package marker

- [ ] **AC-IN-1** `tests/schema/__init__.py` exists and is empty (zero bytes — mirrors `tests/fence/__init__.py` and `tests/unit/schema/__init__.py`). Asserted by `Path("tests/schema/__init__.py").read_bytes() == b""`.

### C. `test_no_llm_imports_in_sandbox.py` — Goal 13 fence

- [ ] **AC-LL-1** Module-level constant `_BANNED_LLM_IMPORTS: Final[frozenset[str]] = frozenset({"anthropic", "langgraph", "chromadb", "sentence_transformers"})`. `Final` annotation visible to `mypy --strict`.
- [ ] **AC-LL-2** Sync test (`test_banned_set_matches_arch`) asserts `_BANNED_LLM_IMPORTS == frozenset({"anthropic", "langgraph", "chromadb", "sentence_transformers"})` — byte-equality with arch §"Two new top-level packages." Module docstring documents the divergent scope vs gather-pipeline `codegenie._fence.FORBIDDEN_LLM_SDKS`.
- [ ] **AC-LL-3** Walker scope: `src/codegenie/sandbox/` and `src/codegenie/gates/` only (NOT all of `src/codegenie/`). Catches eager top-level `import`/`from … import` only — `importlib.import_module(...)` / `__import__(...)` are out of scope (documented in module docstring as "static-import-only").
- [ ] **AC-LL-4** Live test `test_no_banned_imports_under_sandbox_or_gates`: iterates `iter_py(ROOT / "src/codegenie/sandbox", ROOT / "src/codegenie/gates")`; for each file, `iter_top_level_imports(path)` ∩ `_BANNED_LLM_IMPORTS` is empty. Asserts an empty offender list. Passes on the Step 1 codebase (S1-01..S1-06 ship no LLM imports).

### D. `test_no_subprocess_outside_build_chokepoint.py` — ADR-0001 + ADR-0009 fence

- [ ] **AC-SP-1** Module-level constant `_SUBPROCESS_ALLOWLIST: Final[frozenset[Path]]` containing exactly four **relative** paths (relative to `ROOT`): `Path("src/codegenie/sandbox/did/build.py")`, `Path("src/codegenie/sandbox/did/network_policy.py")`, `Path("src/codegenie/sandbox/firecracker/client.py")`, `Path("src/codegenie/sandbox/firecracker/network_policy.py")`. Module docstring cites ADR-0001 + **ADR-0009** as the source-of-truth (arch §Tool-use safety predates ADR-0009 and is silently amended).
- [ ] **AC-SP-2** Walker scope: `src/codegenie/sandbox/` and `src/codegenie/gates/` only. Uses `iter_top_level_imports` from `_walkers.py`.
- [ ] **AC-SP-3** Membership comparison is `path.relative_to(ROOT) not in _SUBPROCESS_ALLOWLIST` — NOT `path not in _SUBPROCESS_ALLOWLIST` with absolute paths. Survives macOS case-insensitivity and symlinked `ROOT`. Asserted by a unit test that creates a symlink to `ROOT` and re-runs the walker (skipped on Windows or filesystems without symlink support).
- [ ] **AC-SP-4** Live test `test_subprocess_only_in_allowlisted_chokepoints`: for each `*.py` under scope, if `"subprocess"` ∈ `iter_top_level_imports(path)` and `path.relative_to(ROOT) not in _SUBPROCESS_ALLOWLIST`, append to offenders. Asserts empty. Passes on Step 1 (no chokepoint files exist yet; allowlist membership is "may not exist yet" — the walker simply finds no file importing `subprocess` outside the allowlist).

### E. `test_objective_signals_static.py` — ADR-0014 fence (schema tier)

- [ ] **AC-OS-1** Imports: `from codegenie.sandbox.signals.models import ObjectiveSignals` AND `from codegenie.sandbox.signals._introspection import iter_nested_field_names`. **NOT** `_iter_nested_field_names`; **NOT** from `models.py`. The schema-tier fence reuses the canonical S1-03 walker — re-declaring the walker locally is a story-level failure (re-declaration silently forks the trust anchor for ADR-0014).
- [ ] **AC-OS-2** Live test `test_no_forbidden_substring_in_any_field_reachable_from_objective_signals`: invokes the walker **type-driven** as `names = list(iter_nested_field_names(ObjectiveSignals))` (not via `model_fields[i].annotation`); for each name, asserts `name.lower()` contains none of `("confidence", "llm", "self_reported", "model_says")`. Iterator exhaustion guarded — `len(names) > 0` asserted defensively (a walker that returns nothing would otherwise pass the substring check vacuously).
- [ ] **AC-OS-3** Module docstring explicitly states "schema-tier fence — survives deletion of `tests/sandbox/test_objective_signals_introspection.py`; reuses the canonical walker; does NOT redeclare it (re-declaration is forbidden by S1-03)."

### F. `test_env_allowlist_no_credentials.py` — ADR-0012 belt-and-suspenders fence

- [ ] **AC-EA-1** Module-level constant `_DENIED_SUBSTRING_FIXTURES: Final[tuple[str, ...]]` — exactly twelve keys covering the 4 substring × 3 case combinations:
  - upper: `"MY_KEY"`, `"GITHUB_TOKEN"`, `"DB_SECRET"`, `"MY_PASSWORD"`
  - lower: `"my_key"`, `"github_token"`, `"db_secret"`, `"my_password"`
  - mixed: `"myToken"`, `"db_Secret"`, `"PathKey"`, `"OAUTH_Password"`
- [ ] **AC-EA-2** Live test `test_denied_substring_keys_always_dropped` (parametrized over `_DENIED_SUBSTRING_FIXTURES`): `out = env_filter({k: "v", "PATH": "/usr/bin"}); assert k not in out and out["PATH"] == "/usr/bin"`.
- [ ] **AC-EA-3** Belt-and-suspenders test `test_deny_substring_survives_allowlist_addition` (parametrized over `_DENIED_SUBSTRING_FIXTURES`): uses `monkeypatch` to set `env_allowlist.ALLOWLIST = env_allowlist.ALLOWLIST + (k,)`, calls `env_filter({k: "v", "PATH": "/usr/bin"})`, asserts `k not in out and out["PATH"] == "/usr/bin"`. **This is the ADR-0012 belt-and-suspenders property** — deny runs as an independent gate, not "skip-if-not-in-allowlist." A regression that conditions deny on `k not in ALLOWLIST` passes AC-EA-2 trivially but fails AC-EA-3.
- [ ] **AC-EA-4** Live test `test_path_survives` asserts `env_filter({"PATH": "/usr/bin"})["PATH"] == "/usr/bin"` — guards against a regression that filters everything.

### G. `test_stage6_chokepoint.py` — ADR-0001 placeholder (S5-04 upgrades)

- [ ] **AC-S6-1** Module docstring explicitly states: "Step 1 placeholder; full ImportFrom + aliased-import walk for `validation.*` is **S5-04** (once `gates/runner.py` exists as a legitimate caller). This placeholder catches **only** `validation.<attr>` attribute access where `validation` is an unqualified `Name`. Missing: `from codegenie.validation import X; X()` (no `validation` Name node), `import codegenie.validation as v; v.<attr>` (rebinds the Name). Documented as the surface-area gap S5-04 closes."
- [ ] **AC-S6-2** Walker scope: `src/codegenie/sandbox/` and `src/codegenie/gates/` only (NOT all of `src/codegenie/` — limits the placeholder's blast radius until S5-04). The arch §CI gates says "no module under `src/codegenie/`" — S5-04 widens; this story narrows for Step 1 safety (legitimate `validation.*` callsites in Phase 3 / Phase 4 must not fail this fence).
- [ ] **AC-S6-3** Live test `test_no_module_under_sandbox_or_gates_calls_validation_attr`: iterates `iter_py(ROOT / "src/codegenie/sandbox", ROOT / "src/codegenie/gates")`; for each file, `_calls_validation_attr(path)` returns False unless the relative path equals `Path("src/codegenie/gates/runner.py")`. Passes on Step 1 (no `validation.*` callsites in sandbox/gates yet).
- [ ] **AC-S6-4** Out-of-scope assertion in module docstring: "This story does NOT resolve the actual Phase 3 Stage 6 entrypoint name — it could be `validation.X`, `validate(...)`, or another shape. S5-04 reconciles."

### H. `test_digests_yaml.py` — ADR-0013 presence floor

- [ ] **AC-DG-1** Live test `test_digests_yaml_exists`: `Path(ROOT / "tools/digests.yaml").exists()` is True.
- [ ] **AC-DG-2** `tools/digests.yaml` contains a top-level `sandbox:` key under which exist exactly four keys (no extras enforced at this story; S6-03 widens): `firecracker`, `vmlinux`, `rootfs`, `policy_yaml`.
- [ ] **AC-DG-3** Live test `test_digests_yaml_root_is_dict`: `yaml.safe_load(content)` returns a `dict` (not None, list, str, int). Catches `yaml.safe_load("- a")` → list → opaque `TypeError` regression.
- [ ] **AC-DG-4** Live test `test_sandbox_key_value_is_dict`: `data["sandbox"]` is a `dict`. Catches the regression where `sandbox: TBD` (scalar value) round-trips and downstream `data["sandbox"]["firecracker"]` raises.
- [ ] **AC-DG-5** Live test `test_sandbox_digest_values_are_placeholder_or_hex` (parametrized over the four keys): each value matches either exactly `"TBD"` OR `^[a-f0-9]{64}$` (BLAKE3 hex). The exact-`"TBD"` path is the Step 1 expectation; the hex path is the S6-03 forward-compatible upgrade. Forbids partial-real partial-TBD states (catches an executor who replaces `firecracker: TBD` with `firecracker: ""` or `firecracker: not-a-digest`).
- [ ] **AC-DG-6** Module-level constant `_BLAKE3_DIGEST_RE: Final[re.Pattern[str]] = re.compile(r"^[a-f0-9]{64}$")` — re-used by S6-03 when value validation upgrades (forward-compatible single-source-of-truth).

### I. Planted-positive companions (mutation-resistance)

- [ ] **AC-PP-1** `test_no_llm_imports_in_sandbox.py::test_walker_detects_planted_anthropic_import`: builds an in-memory synthetic file via `tmp_path / "planted.py"`, writes `"import anthropic\n"`, asserts `_BANNED_LLM_IMPORTS & set(iter_top_level_imports(planted_path)) == {"anthropic"}`. Proves the walker fires; no committed planted file.
- [ ] **AC-PP-2** `test_no_subprocess_outside_build_chokepoint.py::test_walker_detects_planted_subprocess_import`: writes `"import subprocess\n"` to `tmp_path`, asserts `"subprocess" in iter_top_level_imports(planted_path)`.
- [ ] **AC-PP-3** `test_objective_signals_static.py::test_walker_detects_planted_forbidden_field`: defines an in-test `class _Planted(BaseModel): model_config = ConfigDict(extra="forbid", frozen=True); confidence: int = 0`. Asserts `"confidence" in {n.lower() for n in iter_nested_field_names(_Planted)}`. Proves the canonical walker fires on the substring it polices.
- [ ] **AC-PP-4** `test_env_allowlist_no_credentials.py::test_planted_credential_key_is_filtered`: asserts a hand-crafted `env_filter({"PLANTED_TOKEN_KEY": "v"})` returns `{}` — independent positive control that the filter API is callable + denies.
- [ ] **AC-PP-5** `test_stage6_chokepoint.py::test_walker_detects_planted_validation_call`: writes `"validation.run_x()\n"` to `tmp_path`, asserts `_calls_validation_attr(planted_path) is True`.
- [ ] **AC-PP-6** `test_digests_yaml.py::test_yaml_parse_rejects_planted_list_root`: `tmp_path / "planted.yaml"` contains `"- a\n- b\n"`; asserts `yaml.safe_load(planted.read_text())` returns a `list` (proves the parser distinguishes shapes — guards the AC-DG-3 assertion from a regression that special-cases the real file).

### J. Test-file purity (mirror S1-02..S1-06 module-purity pattern)

- [ ] **AC-PU-1** `tests/schema/test_schema_fence_purity.py` exists; AST-walks every `tests/schema/test_*.py` (excluding itself); asserts top-level imports for each are a subset of `{"__future__", "ast", "pathlib", "typing", "re", "pydantic", "yaml", "pytest", "codegenie.sandbox.signals._introspection", "codegenie.sandbox.signals.models", "codegenie.sandbox.env_allowlist", "tests.schema._walkers"}`. **Forbids fence tests from importing any module under `src/codegenie/sandbox/` or `src/codegenie/gates/` other than the three exact modules listed** — catches the future contributor who short-circuits a fence by importing the very module it's policing.

### K. Quality gates

- [ ] **AC-QG-1** `ruff check tests/schema/` and `ruff format --check tests/schema/` pass.
- [ ] **AC-QG-2** `mypy --strict tests/schema/` clean (test files included).
- [ ] **AC-QG-3** `pytest tests/schema/` green. No `pytest.mark.skip` or `pytest.mark.xfail` markers in any `tests/schema/test_*.py` — mirrors `tests/fence/` discipline. Asserted by `tests/schema/test_schema_fence_purity.py::test_no_skip_or_xfail_markers` (AST walk).
- [ ] **AC-PG-1** All six fence live-tests pass on the Step 1 codebase.
- [ ] **AC-PG-2** All six planted-positive companion tests pass independently.
- [ ] **AC-PG-3** Each `tests/schema/test_*.py` collects + executes in < 1 s on the Step 1 codebase (asserted by `tests/schema/test_schema_perf.py` — `pytest --collect-only` time + `pytest -q` time per file, with a 1-second per-file budget). The schema fence runs on every PR; this is the critical-path floor.

## Schema fence design notes

### The kernel + Strategy-per-fence-test composition

`tests/schema/_walkers.py` is the kernel — `ROOT` constant + two pure functions (`iter_py`, `iter_top_level_imports`). Each of the six fence tests is a thin "compose walker + per-fence predicate + assert" body. The rule-of-three is cleared on day one (six callers); extracting at introduction is cheaper than refactoring after four siblings already inline the same `Path(__file__).resolve().parents[2]` + `ast.parse(path.read_text())` template. Future Phase 7 fences (`test_no_pip_in_distroless_layer.py`, `test_no_setuptools_in_distroless_layer.py`) add by importing the kernel — zero edits to existing fences.

### Why schema-tier survives sandbox-tier deletion

The `tests/schema/` namespace is a structural floor: invariants here must remain in force even if `tests/sandbox/` or `tests/gates/` is restructured, deleted, or replaced. The substring-screen fence is the canonical example — S1-03 already ships a sandbox-tier substring screen, and this story re-asserts the same invariant at the schema tier. Crucially, the schema-tier test **imports the canonical walker** (`iter_nested_field_names` from `_introspection`) rather than re-declaring it — re-declaration silently forks the trust anchor for ADR-0014 (the very risk S1-03 hardened against per its AC-1b ban on `_iter_nested_field_names` in `models.__all__`).

### Why the deny set diverges from `FORBIDDEN_LLM_SDKS`

Two different scopes:

- **Gather-pipeline (`codegenie._fence.FORBIDDEN_LLM_SDKS`):** `{anthropic, langgraph, openai, langchain, transformers}` — closes the runtime closure of `codegenie/gather/` and friends. Policed by `tests/unit/test_pyproject_fence.py`.
- **Sandbox + gates (this story's `_BANNED_LLM_IMPORTS`):** `{anthropic, langgraph, chromadb, sentence_transformers}` — closes the runtime closure of `codegenie/sandbox/` and `codegenie/gates/`. `chromadb`/`sentence_transformers` are Phase-4 RAG-stack libraries that must not appear in deterministic gate code; `openai`/`langchain`/`transformers` are gather-pipeline closures policed elsewhere.

A future contributor "fixing" the deny list by importing `FORBIDDEN_LLM_SDKS` would silently both narrow and widen. AC-LL-2 prevents this with byte-equality.

### Why planted-positive companions are non-negotiable

Every fence walker's scope is empty or near-empty on the Step 1 codebase. Without a planted-positive, the live test passes vacuously and Rule 9 fails (the test verifies "walker walks empty list" instead of "walker detects the offense"). The codebase precedent (`tests/fence/test_no_llm_in_transforms.py`) ships a planted-positive subprocess companion exactly for this reason — S1-07 inherits the idiom. The planted-positive is in-memory only (synthetic AST strings written to `tmp_path`); no committed planted files (CODEOWNERS-evasion mitigations are inherited from `tests/fence/`).

## Implementation outline

1. **Create `tests/schema/__init__.py`** (zero bytes).
2. **Create `tests/schema/_walkers.py`** with `ROOT`, `iter_py`, `iter_top_level_imports`, and `__all__`. Module docstring cites S1-07 + `tests/fence/test_no_llm_in_transforms.py` precedent.
3. **Create `tests/schema/test_walkers.py`** covering the kernel's AC-W-3 cases.
4. **Write each of the six fence tests** under `tests/schema/`:
   - `test_no_llm_imports_in_sandbox.py` — declare `_BANNED_LLM_IMPORTS`; live test + planted-positive + sync test (AC-LL-2).
   - `test_no_subprocess_outside_build_chokepoint.py` — declare `_SUBPROCESS_ALLOWLIST` (4 relative paths); live test + planted-positive + (skipped-on-no-symlinks) symlink test.
   - `test_objective_signals_static.py` — import `iter_nested_field_names` from `_introspection`; live test + planted-positive `_Planted(BaseModel)` with `confidence` field.
   - `test_env_allowlist_no_credentials.py` — declare `_DENIED_SUBSTRING_FIXTURES`; parametrized live test + parametrized monkeypatch-into-allowlist test (AC-EA-3) + planted-positive + PATH-survives.
   - `test_stage6_chokepoint.py` — narrow scope to sandbox + gates; live test + planted-positive; module docstring documents S5-04 deferral.
   - `test_digests_yaml.py` — declare `_BLAKE3_DIGEST_RE`; live tests for exists / root-is-dict / sandbox-is-dict / four-keys-present / each-value-is-placeholder-or-hex + planted-positive (list-root rejection).
5. **Create `tests/schema/test_schema_fence_purity.py`** — AST-walks every `tests/schema/test_*.py`; asserts import set is a subset of the allowed set + no `pytest.mark.skip`/`xfail`.
6. **Create `tests/schema/test_schema_perf.py`** — per-file < 1 s budget (AC-PG-3).
7. **Append (or create) `tools/digests.yaml`** with the four `sandbox.*` placeholder entries.
8. Each fence test imports only stdlib (`ast`, `pathlib`, `typing`, `re`), `pydantic`, `yaml`, `pytest`, and the three exact Phase-5 modules under scrutiny (`sandbox.signals._introspection`, `sandbox.signals.models`, `sandbox.env_allowlist`) — pinned by AC-PU-1.

## TDD plan — red / green / refactor

### Red — write the failing test first

Each fence test + planted-positive is committed and verified red before implementation. The "red" state for the planted-positives is `ModuleNotFoundError` (the `_walkers.py` kernel doesn't exist) or `ImportError` (`iter_nested_field_names` import target missing). The "red" state for the live tests is the same plus the missing `tools/digests.yaml`.

```python
# tests/schema/_walkers.py
"""Shared kernel for Phase 5 schema-tier fence tests (S1-07).

Mirrors `tests/fence/test_no_llm_in_transforms.py` precedent: small,
explicit, pure walkers; per-fence predicate stays in the calling test.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path
from typing import Final

__all__ = ["ROOT", "iter_py", "iter_top_level_imports"]

ROOT: Final[Path] = Path(__file__).resolve().parents[2]


def iter_py(*roots: Path) -> Iterator[Path]:
    """Yield every ``*.py`` under each existing root.

    Skips non-existent roots silently — Step 1 may not have created every
    scope yet; a missing scope is not an offense.
    """
    for r in roots:
        if not r.exists():
            continue
        yield from r.rglob("*.py")


def iter_top_level_imports(path: Path) -> Iterator[str]:
    """Yield the top-level module name for every ``import`` / ``from … import``.

    Catches eager AND function-body imports (any depth). Skips relative
    imports (``level > 0``) and dynamic ``importlib.import_module(...)`` /
    ``__import__(...)`` — those belong to a future runtime-import fence
    (phase-arch-design.md §"AST walk" is authoritative for static-import scope).
    """
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                yield node.module.split(".")[0]
```

```python
# tests/schema/test_no_llm_imports_in_sandbox.py
"""ADR-0008 + Goal 13 fence: no LLM SDK imports under sandbox/ or gates/.

Deny set is **Phase-5 sandbox/gates scope** — deliberately different from
gather-pipeline ``codegenie._fence.FORBIDDEN_LLM_SDKS`` (different scope:
``chromadb``/``sentence_transformers`` are RAG-stack libraries that must
not appear in deterministic gate code; ``openai``/``langchain``/
``transformers`` are gather-pipeline closures policed by
``tests/unit/test_pyproject_fence.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from tests.schema._walkers import ROOT, iter_py, iter_top_level_imports

_BANNED_LLM_IMPORTS: Final[frozenset[str]] = frozenset(
    {"anthropic", "langgraph", "chromadb", "sentence_transformers"}
)
_SCOPES: Final[tuple[Path, ...]] = (
    ROOT / "src/codegenie/sandbox",
    ROOT / "src/codegenie/gates",
)


def test_banned_set_matches_arch() -> None:
    # AC-LL-2 — sync fence against arch §"Two new top-level packages."
    assert _BANNED_LLM_IMPORTS == frozenset(
        {"anthropic", "langgraph", "chromadb", "sentence_transformers"}
    )


def test_no_banned_imports_under_sandbox_or_gates() -> None:
    offenders: list[tuple[Path, str]] = []
    for path in iter_py(*_SCOPES):
        hits = _BANNED_LLM_IMPORTS & set(iter_top_level_imports(path))
        offenders.extend((path, name) for name in hits)
    assert not offenders, f"banned imports found: {offenders}"


def test_walker_detects_planted_anthropic_import(tmp_path: Path) -> None:
    # AC-PP-1 — proves the walker fires on the substring it polices.
    planted = tmp_path / "planted.py"
    planted.write_text("import anthropic\n")
    assert _BANNED_LLM_IMPORTS & set(iter_top_level_imports(planted)) == {"anthropic"}
```

```python
# tests/schema/test_no_subprocess_outside_build_chokepoint.py
"""ADR-0001 + ADR-0009 fence: subprocess imports only in the 4 chokepoint files.

ADR-0009 adds ``firecracker/network_policy.py`` (host-side nftables) as
the 4th chokepoint post the original 3-file decision in arch §Tool-use
safety. This module's allowlist is the post-ADR-0009 source-of-truth.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from tests.schema._walkers import ROOT, iter_py, iter_top_level_imports

_SUBPROCESS_ALLOWLIST: Final[frozenset[Path]] = frozenset(
    {
        Path("src/codegenie/sandbox/did/build.py"),
        Path("src/codegenie/sandbox/did/network_policy.py"),
        Path("src/codegenie/sandbox/firecracker/client.py"),
        Path("src/codegenie/sandbox/firecracker/network_policy.py"),
    }
)
_SCOPES: Final[tuple[Path, ...]] = (
    ROOT / "src/codegenie/sandbox",
    ROOT / "src/codegenie/gates",
)


def test_subprocess_only_in_allowlisted_chokepoints() -> None:
    offenders: list[Path] = []
    for path in iter_py(*_SCOPES):
        if "subprocess" in iter_top_level_imports(path):
            rel = path.relative_to(ROOT)
            if rel not in _SUBPROCESS_ALLOWLIST:
                offenders.append(rel)
    assert not offenders, f"subprocess imported outside chokepoints: {offenders}"


def test_walker_detects_planted_subprocess_import(tmp_path: Path) -> None:
    # AC-PP-2
    planted = tmp_path / "planted.py"
    planted.write_text("import subprocess\n")
    assert "subprocess" in set(iter_top_level_imports(planted))
```

```python
# tests/schema/test_objective_signals_static.py
"""ADR-0014 schema-tier fence — survives deletion of tests/sandbox/.

Reuses the canonical ``iter_nested_field_names`` from S1-03's
``_introspection`` module; does NOT redeclare the walker
(re-declaration silently forks the trust anchor — forbidden by S1-03
AC-1b which bans the name from ``models.__all__``).
"""

from __future__ import annotations

from typing import Final

import pytest
from pydantic import BaseModel, ConfigDict

from codegenie.sandbox.signals._introspection import iter_nested_field_names
from codegenie.sandbox.signals.models import ObjectiveSignals

_FORBIDDEN: Final[tuple[str, ...]] = ("confidence", "llm", "self_reported", "model_says")


def test_no_forbidden_substring_in_any_field_reachable_from_objective_signals() -> None:
    names = list(iter_nested_field_names(ObjectiveSignals))
    assert names, "walker yielded zero names — would pass vacuously; refusing"
    for n in names:
        lowered = n.lower()
        for bad in _FORBIDDEN:
            assert bad not in lowered, f"forbidden substring {bad!r} in field {n!r}"


class _Planted(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    confidence: int = 0  # the substring the walker polices


def test_walker_detects_planted_forbidden_field() -> None:
    # AC-PP-3 — proves the canonical walker fires.
    names = {n.lower() for n in iter_nested_field_names(_Planted)}
    assert "confidence" in names
```

```python
# tests/schema/test_env_allowlist_no_credentials.py
"""ADR-0012 belt-and-suspenders fence.

The load-bearing property is **deny runs as an independent gate**, not
"skip-if-not-in-allowlist." AC-EA-3 monkeypatches an offending key INTO
the allowlist and re-asserts the filter drops it.
"""

from __future__ import annotations

from typing import Final

import pytest

from codegenie.sandbox import env_allowlist
from codegenie.sandbox.env_allowlist import filter as env_filter

_DENIED_SUBSTRING_FIXTURES: Final[tuple[str, ...]] = (
    "MY_KEY", "GITHUB_TOKEN", "DB_SECRET", "MY_PASSWORD",
    "my_key", "github_token", "db_secret", "my_password",
    "myToken", "db_Secret", "PathKey", "OAUTH_Password",
)


@pytest.mark.parametrize("k", _DENIED_SUBSTRING_FIXTURES)
def test_denied_substring_keys_always_dropped(k: str) -> None:
    out = env_filter({k: "v", "PATH": "/usr/bin"})
    assert k not in out
    assert out["PATH"] == "/usr/bin"


@pytest.mark.parametrize("k", _DENIED_SUBSTRING_FIXTURES)
def test_deny_substring_survives_allowlist_addition(
    k: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AC-EA-3 — the ADR-0012 belt-and-suspenders property.
    monkeypatch.setattr(env_allowlist, "ALLOWLIST", env_allowlist.ALLOWLIST + (k,))
    out = env_filter({k: "v", "PATH": "/usr/bin"})
    assert k not in out, f"deny was conditional on absence from ALLOWLIST — regression"
    assert out["PATH"] == "/usr/bin"


def test_planted_credential_key_is_filtered() -> None:
    # AC-PP-4 — independent positive control on the filter API.
    assert env_filter({"PLANTED_TOKEN_KEY": "v"}) == {}


def test_path_survives() -> None:
    # AC-EA-4 — guard against a "filter everything" regression.
    assert env_filter({"PATH": "/usr/bin"})["PATH"] == "/usr/bin"
```

```python
# tests/schema/test_stage6_chokepoint.py
"""ADR-0001 placeholder — full ImportFrom + aliased-import walk is S5-04.

This placeholder catches **only** ``validation.<attr>`` attribute access
where ``validation`` is an unqualified ``Name``. Missing (deferred to S5-04):
``from codegenie.validation import X; X()`` (no ``validation`` Name node),
``import codegenie.validation as v; v.<attr>`` (rebinds the Name),
``getattr(validation, "x")()`` (Call → Attribute → Name pattern).

Scope narrowed to sandbox/ + gates/ for Step 1 safety — legitimate
``validation.*`` callsites in Phase 3 / Phase 4 must not fail this fence.
S5-04 widens to all of ``src/codegenie/`` once ``gates/runner.py`` is the
legitimate caller. This story does NOT resolve the actual Phase 3 Stage 6
entrypoint name — could be ``validation.X``, ``validate(...)``, or another
shape. S5-04 reconciles.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

from tests.schema._walkers import ROOT, iter_py

_SCOPES: Final[tuple[Path, ...]] = (
    ROOT / "src/codegenie/sandbox",
    ROOT / "src/codegenie/gates",
)
_ALLOWED_CALLER: Final[Path] = Path("src/codegenie/gates/runner.py")


def _calls_validation_attr(path: Path) -> bool:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "validation":
                return True
    return False


def test_no_module_under_sandbox_or_gates_calls_validation_attr() -> None:
    offenders: list[Path] = []
    for path in iter_py(*_SCOPES):
        rel = path.relative_to(ROOT)
        if rel == _ALLOWED_CALLER:
            continue
        if _calls_validation_attr(path):
            offenders.append(rel)
    assert not offenders, f"unexpected validation.* callers: {offenders}"


def test_walker_detects_planted_validation_call(tmp_path: Path) -> None:
    # AC-PP-5 — proves the placeholder walker fires.
    planted = tmp_path / "planted.py"
    planted.write_text("def f():\n    return validation.run_x()\n")
    assert _calls_validation_attr(planted) is True
```

```python
# tests/schema/test_digests_yaml.py
"""ADR-0013 presence + shape fence — BLAKE3 value validation is S6-03."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest
import yaml

from tests.schema._walkers import ROOT

_DIGESTS: Final[Path] = ROOT / "tools/digests.yaml"
_BLAKE3_DIGEST_RE: Final[re.Pattern[str]] = re.compile(r"^[a-f0-9]{64}$")
_REQUIRED_KEYS: Final[tuple[str, ...]] = ("firecracker", "vmlinux", "rootfs", "policy_yaml")


def test_digests_yaml_exists() -> None:
    assert _DIGESTS.exists(), f"{_DIGESTS} required"


def test_digests_yaml_root_is_dict() -> None:
    data = yaml.safe_load(_DIGESTS.read_text())
    assert isinstance(data, dict), f"root must be dict, got {type(data).__name__}"


def test_sandbox_key_value_is_dict() -> None:
    data = yaml.safe_load(_DIGESTS.read_text())
    assert isinstance(data["sandbox"], dict), "sandbox value must be a dict"


def test_sandbox_digest_keys_present() -> None:
    data = yaml.safe_load(_DIGESTS.read_text())
    sb = data["sandbox"]
    for k in _REQUIRED_KEYS:
        assert k in sb, f"missing sandbox.{k}"


@pytest.mark.parametrize("k", _REQUIRED_KEYS)
def test_sandbox_digest_values_are_placeholder_or_hex(k: str) -> None:
    # AC-DG-5 — exactly "TBD" OR a 64-char hex BLAKE3 digest. No mid-states.
    v = yaml.safe_load(_DIGESTS.read_text())["sandbox"][k]
    assert isinstance(v, str) and v, f"sandbox.{k} must be non-empty string"
    assert v == "TBD" or _BLAKE3_DIGEST_RE.fullmatch(v), (
        f"sandbox.{k}={v!r} must be exactly 'TBD' (Step 1) or 64-char hex (S6-03)"
    )


def test_yaml_parse_rejects_planted_list_root(tmp_path: Path) -> None:
    # AC-PP-6 — guards AC-DG-3 from a regression that special-cases the real file.
    planted = tmp_path / "planted.yaml"
    planted.write_text("- a\n- b\n")
    assert isinstance(yaml.safe_load(planted.read_text()), list)
```

```python
# tests/schema/test_schema_fence_purity.py
"""Pin the import set of every tests/schema/test_*.py."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest

from tests.schema._walkers import ROOT, iter_top_level_imports

_SCHEMA_DIR: Final[Path] = ROOT / "tests/schema"
_ALLOWED_IMPORTS: Final[frozenset[str]] = frozenset(
    {
        "__future__", "ast", "pathlib", "typing", "re",
        "pydantic", "yaml", "pytest",
        "codegenie",  # exact submodule policed below
        "tests",  # only tests.schema._walkers permitted
    }
)
_ALLOWED_CODEGENIE_SUBMODULES: Final[frozenset[str]] = frozenset(
    {
        "codegenie.sandbox.signals._introspection",
        "codegenie.sandbox.signals.models",
        "codegenie.sandbox.env_allowlist",
        "codegenie.sandbox",  # `from codegenie.sandbox import env_allowlist`
    }
)


def _full_imports(path: Path) -> set[str]:
    """Yield FULL dotted module names — not just the first segment."""
    tree = ast.parse(path.read_text())
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                out.add(node.module)
    return out


def _test_files() -> list[Path]:
    return [p for p in _SCHEMA_DIR.glob("test_*.py") if p.name != "test_schema_fence_purity.py"]


@pytest.mark.parametrize("path", _test_files(), ids=lambda p: p.name)
def test_import_set_within_allowed(path: Path) -> None:
    for mod in _full_imports(path):
        top = mod.split(".")[0]
        if top == "codegenie":
            assert mod in _ALLOWED_CODEGENIE_SUBMODULES, (
                f"{path.name} imports {mod!r} — fence tests may only import "
                f"the modules they police: {sorted(_ALLOWED_CODEGENIE_SUBMODULES)}"
            )
        elif top == "tests":
            assert mod == "tests.schema._walkers", (
                f"{path.name} imports {mod!r} — only tests.schema._walkers permitted"
            )
        else:
            assert top in _ALLOWED_IMPORTS, (
                f"{path.name} imports {mod!r} — not in allowed top-level set"
            )


def test_no_skip_or_xfail_markers() -> None:
    """Mirror tests/fence/ discipline — fail loud, never skip."""
    for path in _test_files() + [_SCHEMA_DIR / "test_schema_fence_purity.py"]:
        text = path.read_text()
        assert "pytest.mark.skip" not in text, f"{path.name} uses skip — forbidden"
        assert "pytest.mark.xfail" not in text, f"{path.name} uses xfail — forbidden"
```

Commit; verify failures (`_walkers.py` not found; `iter_nested_field_names` not found if S1-03 not yet shipped; `tools/digests.yaml` missing); implement.

### Green — make it pass

Create `tools/digests.yaml` with placeholder values:

```yaml
# tools/digests.yaml — Phase 5 placeholders
# Real digests filled in: policy_yaml by S3-05; firecracker/vmlinux/rootfs by S6-03.
# Each value must be exactly "TBD" (Step 1) or a 64-char lowercase hex BLAKE3 digest.
sandbox:
  firecracker: "TBD"          # filled in S6-03
  vmlinux: "TBD"              # filled in S6-03
  rootfs: "TBD"               # filled in S6-03
  policy_yaml: "TBD"          # filled in S3-05
```

The eight test files above (six fences + walkers kernel test + purity test) are the implementation — there is no production code to write for this story beyond the digests file.

### Refactor — clean up

- Re-run all six fence live-tests + all six planted-positive companions + the purity test + the walkers-kernel test on the Step 1 codebase — every test < 1 second.
- AST-walk in `iter_top_level_imports` skips relative imports (`level > 0`) — confirm by parsing `"from . import x"` and asserting empty yield.
- `_SUBPROCESS_ALLOWLIST` uses relative `Path` objects so `path.relative_to(ROOT) in _SUBPROCESS_ALLOWLIST` works on macOS case-insensitive filesystems and through symlinked `ROOT`. Confirm by symlinking `ROOT` in a tmp_path and re-running the live test (skipped on filesystems without symlink support).
- `_BLAKE3_DIGEST_RE` is a `Final[re.Pattern[str]]` — S6-03 will import it when the value-shape upgrade lands.
- ADR-0014 enforcement: re-run `test_objective_signals_static.py` against `ObjectiveSignals` from S1-03. If S1-03's `iter_nested_field_names` is broken (returns empty), the `assert names` defensive check catches it.
- `test_stage6_chokepoint.py` placeholder must NOT fail when `validation.*` is referenced legitimately elsewhere in `src/codegenie/` (Phase 3/4 may use the name). The narrowed `_SCOPES` (sandbox + gates only) closes this. Docstring documents the deferral to S5-04.
- Logging: fence tests do not log — they assert.

## Files to touch

| Path | Why |
|---|---|
| `tools/digests.yaml` | New/extended file — four `sandbox.*` placeholder entries per ADR-0013 |
| `tests/schema/__init__.py` | New file — empty package marker (AC-IN-1) |
| `tests/schema/_walkers.py` | New shared kernel — `ROOT`, `iter_py`, `iter_top_level_imports` (AC-W-1..AC-W-3) |
| `tests/schema/test_walkers.py` | New test — covers kernel's AC-W-3 cases |
| `tests/schema/test_no_llm_imports_in_sandbox.py` | New test — Goal 13 fence + planted-positive + sync test |
| `tests/schema/test_no_subprocess_outside_build_chokepoint.py` | New test — 4-chokepoint allowlist per arch §Tool-use safety + ADR-0009 + planted-positive |
| `tests/schema/test_objective_signals_static.py` | New test — ADR-0014 schema-tier introspection fence + planted-positive |
| `tests/schema/test_env_allowlist_no_credentials.py` | New test — ADR-0012 belt-and-suspenders fence (monkeypatch-into-allowlist) + planted-positive |
| `tests/schema/test_stage6_chokepoint.py` | New test — ADR-0001 Stage 6 chokepoint placeholder (S5-04 upgrades) + planted-positive |
| `tests/schema/test_digests_yaml.py` | New test — `tools/digests.yaml` presence + shape + placeholder-or-hex value + planted-positive |
| `tests/schema/test_schema_fence_purity.py` | New test — pins import set of every fence test; bans skip/xfail (AC-PU-1, AC-QG-3) |
| `tests/schema/test_schema_perf.py` | New test — per-file < 1 s budget (AC-PG-3) |

## Out of scope

- **Real BLAKE3 digests for `vmlinux`/`rootfs`/`firecracker`/`policy_yaml`** — S3-05 (policy_yaml) + S6-03 (rest); this story keeps `"TBD"` placeholders exactly.
- **Full AST walk for Stage 6 chokepoint covering `from codegenie.validation import X` + `import … as v.<attr>` + widening scope to all of `src/codegenie/`** — S5-04 (once `gates/runner.py` exists as a legitimate caller and the actual Phase 3 entrypoint name is reconciled).
- **Digest VALUE validation** (BLAKE3 hash check) — S6-03 upgrades `test_digests_yaml.py` from presence-only to value-checking using `_BLAKE3_DIGEST_RE`.
- **Runtime-import fences for `importlib.import_module(...)` / `__import__(...)`** — intentionally NOT assigned to any story; the runtime defense lives in chokepoint discipline + the import-linter contracts, NOT in this static fence.
- **Performance regression tests** — Step 7 (`tests/perf/`).
- **Adversarial tests** (`tests/adversarial/`) — Step 7 (S7-01).

## Notes for the implementer

- **Wrong import — read this first.** S1-03 ships `iter_nested_field_names` (no leading underscore) in `codegenie.sandbox.signals._introspection`. The draft of this story (now corrected) imported `_iter_nested_field_names` from `codegenie.sandbox.signals.models` — a name S1-03 AC-1b *explicitly bans* from `models.__all__` and a module where the walker has never lived. **Importing the canonical walker is non-negotiable**: re-declaring the walker locally silently forks the trust anchor for ADR-0014. The schema-tier fence's load-bearing property is "uses the same walker the sandbox tier uses."
- **4 subprocess chokepoints, not 3.** ADR-0009 (Firecracker host-side nftables) was accepted after the original 3-file decision in arch §Tool-use safety. The post-ADR-0009 allowlist is `{did/build.py, did/network_policy.py, firecracker/client.py, firecracker/network_policy.py}`. Cite ADR-0009 in the module docstring.
- **Planted-positive idiom.** Mirror `tests/fence/test_no_llm_in_transforms.py`: every fence walker ships a companion test that constructs a synthetic input (in-memory AST string written to `tmp_path`; an in-test `BaseModel`; a hand-crafted env dict) and asserts the walker fires. NO committed planted files — the CODEOWNERS-evasion mitigations from `tests/fence/` apply. Without planted-positives, every fence is silently-vacuous on Step 1 and Rule 9 fails.
- **`_BANNED_LLM_IMPORTS` is NOT `FORBIDDEN_LLM_SDKS`.** Different scope. Phase-5 sandbox/gates: `{anthropic, langgraph, chromadb, sentence_transformers}`. Gather-pipeline: `{anthropic, langgraph, openai, langchain, transformers}`. A "fix" that imports `FORBIDDEN_LLM_SDKS` silently narrows and widens. AC-LL-2 enforces byte-equality with the arch set; module docstring explains why.
- **`Path.relative_to(ROOT)` comparison is mandatory.** macOS default filesystems are case-insensitive; symlinked `ROOT` produces different absolute paths than `rglob` returns. `set` membership of absolute `Path` objects silently fails open. The subprocess allowlist stores **relative paths** and the live test compares via `path.relative_to(ROOT)`. Test on a tmp_path symlink if available; skip the symlink test on Windows / no-symlink filesystems.
- **`_walkers.py` is the ONLY shared helper.** Per-fence predicates (the `_BANNED_LLM_IMPORTS` set intersection, the `_calls_validation_attr` AST check, the `_DENIED_SUBSTRING_FIXTURES` matrix) stay inline in each fence test. Resist the temptation to abstract further — the rule-of-three is cleared on `ROOT` + `iter_py` + `iter_top_level_imports`, not on the per-fence predicate.
- **`_BLAKE3_DIGEST_RE` constant is forward-compatible.** S6-03 will import it from this module when value validation upgrades. Single source of truth for the digest shape.
- **`tools/digests.yaml` values are exactly `"TBD"` or 64-char hex.** AC-DG-5 forbids `""`, `"not-a-digest"`, integers, booleans, lists. A partial S6-03 rollout (real digest for `firecracker` but `"TBD"` for `vmlinux`) is allowed by the regex; a malformed mid-state is not.
- **No skip / no xfail.** Mirrors `tests/fence/` discipline (`tests/fence/test_lint_imports_catches_planted_leak.py` uses `pytest.fail` over `skip`). Fence tests fail loud or pass; the in-between is forbidden. `test_schema_fence_purity.py::test_no_skip_or_xfail_markers` enforces.
- **Per-test < 1 s budget.** `tests/schema/` runs on every PR — this is the critical-path floor. `test_schema_perf.py` enforces. If a future addition exceeds 1 s, propose a scope narrowing (e.g., walk only one of `sandbox/` or `gates/`) before relaxing the budget.
- **ADR-0014 details: dict typing.** The recursion in `iter_nested_field_names` (S1-03) handles `dict[str, str | int | bool]` — value annotation is a Union of primitives with no `BaseModel`, so it yields nothing extra. Verify by introducing a temporary `_Foo(BaseModel)` field on `ObjectiveSignals` LOCALLY and confirming `_Foo`'s field names are yielded; do NOT commit the temp field.
- **ADR-0013 startup digest verification is S6-03's job.** The "presence-only" check this story ships is the cheap predecessor.
- **Coverage:** these tests *are* the fences; their pass-rate is the floor, not their own coverage. No `--cov-fail-under` gate on `tests/schema/`.
