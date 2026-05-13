# Story S3-04 — Config loader + defaults

**Step:** Step 3 — Build the harness internals (cache, coordinator, validator, sanitizer, writer, config)
**Status:** Validated
**Effort:** S
**Depends on:** S2-05
**See also (cross-story coupling):** S4-02 — CLI must set `auto_envvar_prefix=None` at the click level; companion close to AC-15 (env-var-off) verified there, not here.
**ADRs honored:** ADR-0012 (subprocess allowlist + forbidden-patterns hook bans bare `yaml.load(...)` — AC-7 is the test-side enforcement)

## Validation notes

Hardened on 2026-05-13 by `phase-story-validator` v1. Three critics returned 13 block / 21 harden / 9 nit findings. Material changes applied here:

- **AC count: 8 → 21** (grouped into seven sections A–G). Every new AC names one observable behavior and traces to either the story Goal, `final-design.md §2.13`, `phase-arch-design.md §Component design / Config` (line 422) and `§Harness engineering / Configuration` (line 760), or an implementer-note that was previously buried.
- **TDD plan: end-to-end concrete-Python rewrite.** All `...` test bodies replaced (the S3-02 and S3-03 validations explicitly closed that antipattern; this story had reverted to it for 3 of 8 sketched tests).
- **Wrong testing harness fixed.** Original test used `caplog` for a `structlog` event assertion — `caplog` does NOT capture this codebase's structlog stream (see `src/codegenie/logging.py` + `tests/unit/test_exec.py:285`). Replaced with `structlog.testing.capture_logs()`.
- **Precedence chain now exercised pairwise.** Original tested 1 of 6 pairwise orderings on a 4-source chain; replaced with a parametrized matrix that kills every adjacent-swap mutant + a separate "user-yaml-only field survives" test (mutant: "reads only repo YAML" used to pass everything).
- **`ConfigError` failure surface broadened.** `final-design.md §2.13` and `phase-arch-design.md §Config / Failure behavior` (line 434) commit the loader to `ConfigError` on **three** failure modes (unknown key, YAML parse error, type mismatch). Originally only the first was ACed. Now all three.
- **Env-var-off invariant promoted from prose to AST scan + spy test.** Same single-source-of-truth idiom S3-03 adopted for `SECRET_FIELD_PATTERN`. The loader source must contain no reference to `os.path.expandvars`, `string.Template`, or reads on `os.environ` for YAML values.
- **`yaml.safe_load`-only invariant promoted from a refactor "confirm" note to an AST scan** (banned: `yaml.load`, `yaml.unsafe_load`, `yaml.full_load`). Closes a CVE-2017-18342-class regression vector.
- **Provenance log scope corrected** to "all fields, not just non-default", matching `final-design.md §2.13` and `phase-arch-design.md §Harness / Configuration` (line 760). Original "non-default only" was a story-local narrowing.
- **Provenance label vocabulary aligned** with `final-design.md §2.13`: `("defaults", "global", "repo", "cli")`. Original story used `("defaults", "user_yaml", "repo_yaml", "cli")` — story-only spelling.
- **Frozen-dataclass invariant pinned.** Original had no test asserting `Config.__dataclass_params__.frozen is True` or `FrozenInstanceError` on mutation. A one-keyword regression (drop `frozen=True`) used to pass.
- **`Path.home()` injection idiom pinned** in the TDD plan so the executor cannot write to the developer's real `~/.codegenie/`.
- **Error-message format pinned** as `"unknown key '<k>'; did you mean '<closest>'?"` — disambiguates the Goal vs AC wording drift. Implementer-note "if no close match, omit the suggestion clause" promoted to AC-12 with a dedicated test.
- **Cross-story coupling surfaced.** AC-15 (env-var-off in the loader) is one half of the system-level guarantee; the other half is `auto_envvar_prefix=None` in `cli.py`, which is S4-02's territory. Added "See also: S4-02" to the header so the executor doesn't ship S3-04 green while S4-02 leaves click expansion on.

Three architectural follow-ups surfaced (not auto-fixed — outside this story's surgical scope per Rule 3):

1. **`final-design.md §2.13` line 316** says "Levenshtein" but every Python implementation will reach for `difflib.get_close_matches` (Ratcliff-Obershelp ratio, not edit distance). Either edit the design line to "edit-distance-style suggestion via `difflib.get_close_matches`" or import a real Levenshtein library — pick one and lock it in the design once, not per-story.
2. **Provenance label vocabulary** (`defaults`/`global`/`repo`/`cli`) is referenced across `final-design.md §2.13`, `§4 step 4` (line 418), and `phase-arch-design.md §Harness / Configuration` — lock the spelling in one place and have downstream stories cite it.
3. **No ADR codifies env-vars-off-in-Phase-0 → re-enabled-in-Phase-9 path-traversal close.** Currently a prose commitment in `phase-arch-design.md §Harness / Configuration` (line 760). An ADR-of-record would lock it in before Phase 9 has to revisit.

Full audit trail with critic findings and edit deltas: [`_validation/S3-04-config-loader.md`](_validation/S3-04-config-loader.md).

## Context

The Coordinator (S3-05), the CacheStore (S3-01), and the CLI (S4-02) all need a `Config` object. Phase 0's `Config` is a frozen dataclass with three fields (`max_concurrent_probes`, `cache_ttl_hours`, `enable_audit`) — additive across phases, not a frozen contract. The loader merges four sources (`defaults < ~/.codegenie/config.yaml < <repo>/.codegenie/config.yaml < cli_overrides`), with `ConfigError` on **unknown key, YAML parse error, type mismatch, or non-mapping top level** (`final-design.md §2.13` line 312; `phase-arch-design.md §Config / Failure behavior` line 434).

Env-var expansion is **off**: this loader never calls `os.path.expandvars` or `string.Template` substitution on any YAML value, and never reads `os.environ` for YAML values. (The companion CLI-level close — `auto_envvar_prefix=None` at the click level — is verified by S4-02, not here. AC-15 here pins only the loader's half.) Env-var-off is a path-traversal close per `phase-arch-design.md §Harness engineering / Configuration` (line 760), re-enabled with documented scope in Phase 9.

This story is independent of S3-01/02/03 (no shared types beyond `errors.ConfigError`) and lands a small, testable surface that S3-05 and S4-02 consume.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design / Config` (≈ line 422) — `defaults.py` + `loader.py` shape; `ConfigError` failure surface; `pyyaml` + `errors` + `difflib` deps.
  - `../phase-arch-design.md §Harness engineering / Configuration` (≈ line 760) — precedence chain, env-var-off, provenance-at-DEBUG.
  - `../phase-arch-design.md §Development view` (≈ line 273) — `config/defaults.py` is plain dataclass (not Pydantic).
- **Source design:**
  - `../final-design.md §2.13` — three sources (`defaults < ~/.codegenie/config.yaml < <repo>/.codegenie/config.yaml < CLI flags`), `Config` frozen dataclass, unknown-key fail-loud, `yaml.safe_load` only, provenance logged at DEBUG.
  - `../final-design.md §4 step 4` (≈ line 418) — provenance label vocabulary `(Defaults < global < repo < CLI)`.
- **High-level impl roadmap:**
  - `../High-level-impl.md` Step 3 — three Config fields and their default values.
- **Existing code (deps):**
  - `src/codegenie/errors.py` — `ConfigError` already exists (S2-01).
  - `src/codegenie/logging.py` — `configure_logging` (S2-01); use `structlog.get_logger(...).debug(...)` for provenance.
- **Test idioms (codebase parity):**
  - `tests/unit/test_logging.py` — `structlog.testing.capture_logs` usage.
  - `tests/unit/test_exec.py:285` — `structlog.testing.capture_logs` + `log_level == "debug"` assertion idiom.
  - `tests/unit/test_audit_models.py` — frozen-model parity test pattern.

## Goal

`load_config(repo_root, cli_overrides)` returns a frozen `Config` instance assembled from `defaults < ~/.codegenie/config.yaml < <repo>/.codegenie/config.yaml < cli_overrides`. Any unknown key in either YAML or `cli_overrides` raises `ConfigError("unknown key '<k>'; did you mean '<closest>'?")` (the suggestion clause is omitted when no close match exists). Malformed YAML, non-mapping top-level YAML, and YAML values whose types don't match the dataclass fields all raise `ConfigError` with the original exception chained via `from`. Env-var expansion in the loader is off. At DEBUG, the loader emits one `config.loaded` event whose `provenance` dict maps every declared `Config` field to its winning source label drawn from `("defaults", "global", "repo", "cli")`.

## Acceptance criteria

### Section A — `Config` dataclass shape

- [ ] **AC-1** — `src/codegenie/config/defaults.py` declares `Config` as a frozen `@dataclass` with exactly three fields, types and default values pinned:
  - `max_concurrent_probes: int = 8`
  - `cache_ttl_hours: int = 24`
  - `enable_audit: bool = True`

  `dataclasses.is_dataclass(Config) is True`, `Config.__dataclass_params__.frozen is True`, and attempting `cfg.max_concurrent_probes = 99` on any instance raises `dataclasses.FrozenInstanceError`.
- [ ] **AC-2** — `src/codegenie/config/loader.py` exports `load_config(repo_root: Path, cli_overrides: dict[str, Any]) -> Config`. `src/codegenie/config/__init__.py` re-exports both `Config` and `load_config`. `codegenie.config.__all__`, if defined, contains both names.

### Section B — Source precedence (deterministic merge)

- [ ] **AC-3** — Source order, lowest to highest precedence: `defaults < ~/.codegenie/config.yaml < <repo_root>/.codegenie/config.yaml < cli_overrides`. Each later source overrides earlier ones on a **per-field** basis (a disjoint-key merge yields the union of all sources, never a wholesale replacement).
- [ ] **AC-4** — The user-yaml path is resolved via `Path.home() / ".codegenie" / "config.yaml"` (not via `os.environ["HOME"]` directly). Tests must monkeypatch `Path.home` so they never touch the developer's real home directory.

### Section C — YAML parsing safety

- [ ] **AC-5** — Both YAML files are parsed via `yaml.safe_load` only. An AST scan of `loader.py` confirms no call to `yaml.load`, `yaml.unsafe_load`, or `yaml.full_load`.
- [ ] **AC-6** — An empty YAML file (zero bytes), a comment-only YAML file, and a file containing only `null` are each treated as the empty mapping `{}`; the loader does not raise and lower-precedence sources win.
- [ ] **AC-7** — A YAML file whose top-level value is anything other than a mapping (e.g., a list, a scalar, a sequence) raises `ConfigError` whose message names the offending file path and the actual top-level type. Lower-precedence sources are not silently substituted.
- [ ] **AC-8** — A malformed YAML file (`yaml.safe_load` raises `yaml.YAMLError`) raises `ConfigError` whose message contains the file path; the original `yaml.YAMLError` is preserved via `raise ConfigError(...) from err` (`ConfigError.__cause__` is the original `YAMLError`).
- [ ] **AC-9** — A YAML value whose type does not match the declared `Config` field type (e.g., `max_concurrent_probes: "eight"`) raises `ConfigError("invalid value for <field>: ...")` with the original `TypeError` chained via `raise ... from`. The type check is observable (not silent coercion).
- [ ] **AC-10** — Missing files are not errors. Each YAML source is optional; absence falls through to the lower-precedence source. A `repo_root` that does not exist, is not a directory, or has no `.codegenie/` subdirectory likewise falls through (no `FileNotFoundError`, no `NotADirectoryError`).

### Section D — Unknown-key check (fail-loud)

- [ ] **AC-11** — An unknown key present in either YAML file or in `cli_overrides` (i.e., not a field declared on `Config`) raises `ConfigError` whose message matches the regex `^unknown key '<k>'; did you mean '<closest>'\?$` where `<closest>` is `difflib.get_close_matches(key, _known_fields(), n=1, cutoff=0.6)[0]` when non-empty. The suggestion is the **single closest** declared field — not an enumeration of all fields.
- [ ] **AC-12** — When `difflib.get_close_matches` returns the empty list (no key on `Config` is close enough), the `ConfigError` message contains the offending key but **omits the entire "did you mean" clause** — i.e., the substring `"did you mean"` does not appear in the message.

### Section E — Env-var-off (security invariant)

- [ ] **AC-13** — An AST scan of `loader.py` asserts the source contains:
  - No reference to `os.path.expandvars`, `string.Template`, or `os.path.expanduser` applied to YAML values.
  - No subscript or attribute read on `os.environ` for YAML values. (Top-level `import os` is permitted only to support `Path.home()`/`Path` usage; calling `os.environ[...]` or `os.getenv(...)` on YAML keys/values is forbidden.)
- [ ] **AC-14** — Literal `$ENV_VAR` / `${FOO}` / `~user` strings in any YAML value pass through the loader's merge step unchanged. Verified by introspecting the merged-dict the loader hands to `Config(**merged)` (e.g., via a spy on the internal validator helper) — the literal string is observed, not the expanded value.

### Section F — Provenance (DEBUG observability)

- [ ] **AC-15** — At DEBUG level, the loader emits exactly one `structlog` event with name `config.loaded`. The event's `provenance` kwarg is a `dict[str, str]` containing **every** declared `Config` field (not just non-default fields), with values drawn from the closed set `{"defaults", "global", "repo", "cli"}` (matching `final-design.md §2.13` and `§4 step 4` vocabulary). The `log_level` on the captured event equals `"debug"`.
- [ ] **AC-16** — `tests/unit/test_config_loader.py` uses `structlog.testing.capture_logs()` to assert on the `config.loaded` event — not the stdlib `caplog` fixture. (`caplog` does not capture this codebase's structlog stream; matches the idiom established in `tests/unit/test_exec.py:285`.)

### Section G — Code hygiene

- [ ] **AC-17** — `tests/unit/test_config_loader.py` exercises every AC above and is green. `ruff check` clean on all touched files. `mypy --strict` clean on `src/codegenie/config/**` (zero errors, zero `# type: ignore` comments in new code).
- [ ] **AC-18** — `codegenie.config` (and its submodules `defaults`, `loader`) do **not** import `pydantic`, `jsonschema`, or `blake3` at module top level. The loader is on the CLI cold-start path; the lazy-import discipline `phase-arch-design.md §Component design / CLI` (line 416) protects `--help` p95. `structlog` is imported lazily inside the function body that emits `config.loaded`, not at module top level.
- [ ] **AC-19** — A re-export sanity test in `test_config_loader.py` asserts `from codegenie.config import Config, load_config` succeeds (catches the "forgot to re-export" mutant).
- [ ] **AC-20** — `Config()` with no arguments produces a value equal to `Config(max_concurrent_probes=8, cache_ttl_hours=24, enable_audit=True)`. The default values are pinned by an explicit field-by-field test (catches "silently changed a default" — a load-bearing-commitment-violation alarm).
- [ ] **AC-21** — `load_config(r, {})` and `load_config(r, {"max_concurrent_probes": 8})` produce equal `Config` instances when no YAML files exist (metamorphic relation: a cli override at the default value is semantically a no-op for the resulting Config; provenance is allowed to differ per AC-15, since the second case correctly sources to `cli`).

## Implementation outline

1. Author `src/codegenie/config/__init__.py` (package marker; re-exports `Config` and `load_config`).
2. Author `src/codegenie/config/defaults.py`: the frozen `Config` dataclass; a `_defaults() -> dict[str, Any]` helper returning the field-name → default-value map; a `_known_fields() -> frozenset[str]` helper (used by the loader for the unknown-key check).
3. Author `src/codegenie/config/loader.py`:
   - `_read_yaml_if_exists(path: Path) -> dict[str, Any]` — returns `{}` on missing file. On a present-but-malformed file, raises `ConfigError(...) from yaml.YAMLError`. On a present file whose top-level is not a mapping (list, scalar, sequence), raises `ConfigError(...)` naming the actual type.
   - `_check_unknown_keys(source_name: str, data: dict, known: frozenset[str]) -> None` — walks `data.keys()`; on miss, raises `ConfigError` whose message format is fixed at `"unknown key '<k>'; did you mean '<closest>'?"` (suggestion clause omitted when `get_close_matches` returns `[]`).
   - `_typed_construct(merged: dict) -> Config` — calls `Config(**merged)`; wraps `TypeError` into `ConfigError("invalid value for <field>: ...") from err`.
   - `load_config(repo_root, cli_overrides)`:
     1. Compute `user_yaml_path = Path.home() / ".codegenie" / "config.yaml"`; read.
     2. Compute `repo_yaml_path = repo_root / ".codegenie" / "config.yaml"`; read (no error on missing `repo_root`).
     3. Validate each source's keys via `_check_unknown_keys` *before* merging.
     4. Build `merged = {**defaults, **user, **repo, **cli_overrides}`.
     5. Build `provenance: dict[str, str]` by walking declared fields in `_known_fields()`: for each field, the source label is the highest-precedence source that names that field; default to `"defaults"` when none.
     6. Lazy-import `structlog` and emit `logger.debug("config.loaded", provenance=provenance)`.
     7. Return `_typed_construct(merged)`.
4. Write the unit tests below.

## TDD plan — red / green / refactor

### Test fixtures (shared)

```python
# tests/unit/test_config_loader.py
from __future__ import annotations

import ast
import dataclasses
import inspect
import re
from pathlib import Path
from typing import Any

import pytest
import structlog
import yaml

from codegenie.errors import ConfigError


@pytest.fixture
def write_user_yaml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Redirect Path.home() to tmp_path/home; yield a writer for the user yaml.

    A test that uses this fixture never touches the developer's real
    ~/.codegenie/. The redirect applies for the lifetime of the test only.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    def _write(payload: str) -> Path:
        cfg_dir = fake_home / ".codegenie"
        cfg_dir.mkdir(exist_ok=True)
        p = cfg_dir / "config.yaml"
        p.write_text(payload)
        return p

    return _write


@pytest.fixture
def write_repo_yaml(tmp_path: Path):
    def _write(payload: str) -> Path:
        cfg_dir = tmp_path / ".codegenie"
        cfg_dir.mkdir(exist_ok=True)
        p = cfg_dir / "config.yaml"
        p.write_text(payload)
        return p

    return _write


@pytest.fixture(autouse=True)
def _reset_structlog():
    yield
    structlog.reset_defaults()
```

### Red — write failing tests first

```python
# ─── Section A — Config dataclass shape ───────────────────────────────────

def test_config_is_frozen_dataclass_with_pinned_defaults():
    """AC-1, AC-20 — catches the `frozen=True → frozen=False` mutant,
    the `@dataclass → regular class` mutant, AND silent default-value drift.
    """
    from codegenie.config import Config
    assert dataclasses.is_dataclass(Config)
    assert Config.__dataclass_params__.frozen is True

    defaults = {f.name: f.default for f in dataclasses.fields(Config)}
    assert defaults == {
        "max_concurrent_probes": 8,
        "cache_ttl_hours": 24,
        "enable_audit": True,
    }

    cfg = Config()
    assert cfg == Config(max_concurrent_probes=8, cache_ttl_hours=24, enable_audit=True)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.max_concurrent_probes = 99  # type: ignore[misc]


def test_config_package_reexports():
    """AC-2, AC-19 — Config and load_config are reachable via codegenie.config."""
    import codegenie.config as pkg
    assert hasattr(pkg, "Config")
    assert hasattr(pkg, "load_config")
    if hasattr(pkg, "__all__"):
        assert {"Config", "load_config"} <= set(pkg.__all__)


# ─── Section B — Source precedence ────────────────────────────────────────

def test_defaults_only_when_no_yaml_and_no_overrides(tmp_path, monkeypatch):
    """AC-3 baseline — return type is Config and default values survive."""
    from codegenie.config import Config, load_config
    fake_home = tmp_path / "no-home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    cfg = load_config(repo_root=tmp_path, cli_overrides={})
    assert isinstance(cfg, Config)
    assert cfg == Config()  # equals bare default-constructed instance


@pytest.mark.parametrize(
    "user_val, repo_val, cli_val, expected",
    [
        # (~/.codegenie value, <repo>/.codegenie value, cli_overrides value, winner)
        (None, None, None, 8),    # defaults survive
        (4,    None, None, 4),    # user beats defaults
        (None, 2,    None, 2),    # repo beats defaults
        (None, None, 1,    1),    # cli beats defaults
        (4,    2,    None, 2),    # repo beats user
        (4,    None, 1,    1),    # cli beats user
        (None, 2,    1,    1),    # cli beats repo
        (4,    2,    1,    1),    # cli wins three-way
    ],
)
def test_precedence_pairwise_matrix(
    tmp_path, write_user_yaml, write_repo_yaml,
    user_val, repo_val, cli_val, expected,
):
    """AC-3 — every adjacent-swap mutant in the 4-source chain fails at
    least one row. The 4-source chain has 6 pairwise relationships; the
    matrix exercises all of them."""
    from codegenie.config import load_config
    if user_val is not None:
        write_user_yaml(f"max_concurrent_probes: {user_val}\n")
    if repo_val is not None:
        write_repo_yaml(f"max_concurrent_probes: {repo_val}\n")
    overrides = {} if cli_val is None else {"max_concurrent_probes": cli_val}
    cfg = load_config(repo_root=tmp_path, cli_overrides=overrides)
    assert cfg.max_concurrent_probes == expected


def test_disjoint_keys_across_sources_yield_union(
    tmp_path, write_user_yaml, write_repo_yaml,
):
    """AC-3 — disjoint-key merge is per-field, not wholesale-replace.
    Mutant 'repo YAML *replaces* user YAML wholesale' fails here."""
    from codegenie.config import load_config
    write_user_yaml("max_concurrent_probes: 4\n")
    write_repo_yaml("cache_ttl_hours: 12\n")
    cfg = load_config(repo_root=tmp_path, cli_overrides={"enable_audit": False})
    assert cfg.max_concurrent_probes == 4
    assert cfg.cache_ttl_hours == 12
    assert cfg.enable_audit is False


def test_user_yaml_only_field_survives_when_no_repo_yaml(
    tmp_path, write_user_yaml,
):
    """AC-3 — mutant 'reads only repo YAML, ignores user YAML' fails here.
    The override-chain tests miss this because they always populate repo."""
    from codegenie.config import load_config
    write_user_yaml("cache_ttl_hours: 12\n")
    cfg = load_config(repo_root=tmp_path, cli_overrides={})
    assert cfg.cache_ttl_hours == 12


# ─── Section C — YAML parsing safety ──────────────────────────────────────

def test_loader_uses_only_yaml_safe_load():
    """AC-5 — AST-scan: loader.py calls yaml.safe_load only. Catches a
    yaml.load / yaml.unsafe_load regression (CVE-2017-18342-class)."""
    import codegenie.config.loader as loader_mod
    src = inspect.getsource(loader_mod)
    tree = ast.parse(src)
    yaml_calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "yaml":
                yaml_calls.append(node.func.attr)
    assert yaml_calls, "loader.py must call yaml.<something> somewhere"
    banned = {"load", "unsafe_load", "full_load"}
    leaked = [c for c in yaml_calls if c in banned]
    assert not leaked, (
        f"loader.py uses banned yaml API(s) {leaked}; AC-5 requires yaml.safe_load only"
    )
    assert "safe_load" in yaml_calls


@pytest.mark.parametrize("payload", ["", "\n", "# only a comment\n", "null\n"])
def test_empty_or_null_yaml_treated_as_empty_mapping(
    tmp_path, write_repo_yaml, payload,
):
    """AC-6 — yaml.safe_load returns None on these; loader must coerce to {}."""
    from codegenie.config import Config, load_config
    write_repo_yaml(payload)
    cfg = load_config(repo_root=tmp_path, cli_overrides={})
    assert cfg == Config()


@pytest.mark.parametrize(
    "payload, top_level_type",
    [
        ("- a\n- b\n", "list"),
        ("just a string\n", "str"),
        ("42\n", "int"),
    ],
)
def test_yaml_top_level_must_be_mapping(
    tmp_path, write_repo_yaml, payload, top_level_type,
):
    """AC-7 — non-mapping top level raises ConfigError naming the path
    AND the actual type. Mutant 'silently treats list as {}' fails here."""
    from codegenie.config import load_config
    p = write_repo_yaml(payload)
    with pytest.raises(ConfigError) as ei:
        load_config(repo_root=tmp_path, cli_overrides={})
    msg = str(ei.value)
    assert str(p) in msg or ".codegenie/config.yaml" in msg
    assert top_level_type in msg or "mapping" in msg.lower()


def test_malformed_yaml_wraps_yaml_error_with_cause(tmp_path, write_repo_yaml):
    """AC-8 — yaml.YAMLError is wrapped, original chained via __cause__."""
    from codegenie.config import load_config
    write_repo_yaml(":::\nthis is: not [valid: yaml\n")
    with pytest.raises(ConfigError) as ei:
        load_config(repo_root=tmp_path, cli_overrides={})
    assert ".codegenie/config.yaml" in str(ei.value)
    assert ei.value.__cause__ is not None
    assert isinstance(ei.value.__cause__, yaml.YAMLError)


def test_type_mismatch_wraps_typeerror_with_cause(
    tmp_path, write_repo_yaml,
):
    """AC-9 — string-where-int expected raises ConfigError with the
    original TypeError chained. Mutant 'lets TypeError escape' surfaces a
    raw stack trace and fails this test."""
    from codegenie.config import load_config
    write_repo_yaml('max_concurrent_probes: "eight"\n')
    with pytest.raises(ConfigError) as ei:
        load_config(repo_root=tmp_path, cli_overrides={})
    msg = str(ei.value)
    assert "max_concurrent_probes" in msg
    assert ei.value.__cause__ is not None
    assert isinstance(ei.value.__cause__, TypeError)


def test_missing_files_and_missing_repo_root_fall_through(tmp_path, monkeypatch):
    """AC-10 — neither YAML present, and repo_root has no .codegenie/ — returns defaults."""
    from codegenie.config import Config, load_config
    fake_home = tmp_path / "no-home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    nonexistent_repo = tmp_path / "does-not-exist"  # never mkdir'd
    cfg = load_config(repo_root=nonexistent_repo, cli_overrides={})
    assert cfg == Config()


# ─── Section D — Unknown-key check ────────────────────────────────────────

UNKNOWN_KEY_FORMAT = re.compile(
    r"^unknown key '([^']+)'(?:; did you mean '([^']+)'\?)?$"
)


def test_unknown_yaml_key_format_offender_before_suggestion(
    tmp_path, write_repo_yaml,
):
    """AC-11 — message format pinned: offender first, then suggestion.
    A swapped 'unknown key: <closest>; did you mean <typo>?' fails the regex.
    """
    from codegenie.config import load_config
    write_repo_yaml("max_concurent_probes: 4\n")  # missing 'r'
    with pytest.raises(ConfigError) as ei:
        load_config(repo_root=tmp_path, cli_overrides={})
    m = UNKNOWN_KEY_FORMAT.match(str(ei.value))
    assert m is not None, f"unexpected format: {str(ei.value)!r}"
    assert m.group(1) == "max_concurent_probes"
    assert m.group(2) == "max_concurrent_probes"


def test_unknown_cli_key_format_offender_before_suggestion(tmp_path):
    """AC-11 — same format from cli source, not just yaml source.
    Mutant 'suggestion only emitted for YAML, not CLI' fails here."""
    from codegenie.config import load_config
    with pytest.raises(ConfigError) as ei:
        load_config(repo_root=tmp_path, cli_overrides={"cache_ttl_hour": 1})  # missing 's'
    m = UNKNOWN_KEY_FORMAT.match(str(ei.value))
    assert m is not None, f"unexpected format: {str(ei.value)!r}"
    assert m.group(1) == "cache_ttl_hour"
    assert m.group(2) == "cache_ttl_hours"


def test_unknown_key_suggestion_is_single_closest_match(
    tmp_path, write_repo_yaml,
):
    """AC-11 — suggestion is the single closest match, not an enumeration.
    Mutant 'dumps every known field into the message' fails here because
    only one other field name (the actual closest) appears."""
    from codegenie.config import load_config
    write_repo_yaml("max_concurent_probes: 4\n")
    with pytest.raises(ConfigError) as ei:
        load_config(repo_root=tmp_path, cli_overrides={})
    msg = str(ei.value)
    assert "max_concurrent_probes" in msg
    # The other declared fields are NOT echoed.
    assert "enable_audit" not in msg
    assert "cache_ttl_hours" not in msg


def test_unknown_key_no_close_match_omits_did_you_mean(tmp_path):
    """AC-12 — when get_close_matches returns [], the entire 'did you mean'
    clause is omitted. Mutant 'always appends did you mean: ' (empty) fails."""
    from codegenie.config import load_config
    with pytest.raises(ConfigError) as ei:
        load_config(repo_root=tmp_path, cli_overrides={"zzz_totally_unrelated": 1})
    msg = str(ei.value)
    assert "zzz_totally_unrelated" in msg
    assert "did you mean" not in msg.lower(), (
        f"no close match; suggestion clause must be absent. got: {msg!r}"
    )
    # And the format still matches the regex's no-suggestion branch.
    assert UNKNOWN_KEY_FORMAT.match(msg) is not None


# ─── Section E — Env-var-off (security) ────────────────────────────────────

def test_loader_module_does_not_reference_env_expansion_apis():
    """AC-13 — AST-scan: loader.py contains no reference to expandvars /
    string.Template / expanduser / os.environ. Catches a future regression
    that re-introduces env-var expansion. Mirrors the AST-scan idiom S3-03
    used for SECRET_FIELD_PATTERN's single-source guarantee."""
    import codegenie.config.loader as loader_mod
    src = inspect.getsource(loader_mod)
    tree = ast.parse(src)
    banned_attrs = {"expandvars", "Template", "expanduser", "environ", "getenv"}
    banned_names = {"Template"}  # bare name imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in banned_attrs:
            raise AssertionError(
                f"loader.py references banned env-expansion API '.{node.attr}' "
                f"(line {node.lineno}); AC-13 forbids env-var sourcing for YAML values"
            )
        if isinstance(node, ast.Name) and node.id in banned_names:
            raise AssertionError(
                f"loader.py references banned env-expansion name '{node.id}' "
                f"(line {node.lineno})"
            )


def test_loader_preserves_dollar_literal_in_merged_dict(
    tmp_path, write_repo_yaml, monkeypatch,
):
    """AC-14 — a YAML value literal like '$ENV_VAR' passes through unchanged.

    Strategy: install a process-env value for $ENV_VAR, then write a YAML
    that uses a string value for a *known* field — even though the resulting
    type-check will reject the string, the test catches what the loader did
    BEFORE that check by spying on the internal merged-dict step.
    """
    import codegenie.config.loader as loader_mod
    monkeypatch.setenv("ENV_VAR", "999")
    write_repo_yaml('cache_ttl_hours: "$ENV_VAR"\n')

    captured: dict[str, Any] = {}
    real = loader_mod._typed_construct

    def spy(merged: dict[str, Any]):
        captured.update(merged)
        return real(merged)

    monkeypatch.setattr(loader_mod, "_typed_construct", spy)
    with pytest.raises(ConfigError):  # AC-9 type-mismatch wrap
        loader_mod.load_config(repo_root=tmp_path, cli_overrides={})
    assert captured.get("cache_ttl_hours") == "$ENV_VAR", (
        f"loader expanded $ENV_VAR; expected literal preservation. got: {captured!r}"
    )


# ─── Section F — Provenance (DEBUG observability) ─────────────────────────

def test_provenance_event_covers_every_field_with_correct_source(
    tmp_path, write_user_yaml, write_repo_yaml,
):
    """AC-15, AC-16 — at DEBUG, one config.loaded event whose provenance
    dict covers ALL fields with the source labels from the closed set
    {defaults, global, repo, cli}. Uses structlog.testing.capture_logs,
    not caplog (caplog would silently capture nothing — Rule 12)."""
    import codegenie.logging as cgl
    from codegenie.config import load_config
    cgl.configure_logging(verbose=True)
    write_user_yaml("cache_ttl_hours: 12\n")
    write_repo_yaml("max_concurrent_probes: 2\n")

    with structlog.testing.capture_logs() as events:
        load_config(repo_root=tmp_path, cli_overrides={"enable_audit": False})

    loaded = [e for e in events if e.get("event") == "config.loaded"]
    assert len(loaded) == 1, f"expected one config.loaded event; got {events!r}"
    ev = loaded[0]
    assert ev["log_level"] == "debug"
    # Provenance covers ALL declared fields, not just non-default ones.
    assert ev["provenance"] == {
        "max_concurrent_probes": "repo",
        "cache_ttl_hours": "global",
        "enable_audit": "cli",
    }


def test_provenance_event_when_nothing_overrides_labels_all_as_defaults(
    tmp_path, monkeypatch,
):
    """AC-15 — when no YAML files and no CLI overrides exist, every field's
    provenance source is 'defaults'. Catches a mutant that omits defaults
    from the dict (the original story narrowing) or labels them as 'unknown'."""
    import codegenie.logging as cgl
    from codegenie.config import load_config
    fake_home = tmp_path / "no-home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    cgl.configure_logging(verbose=True)

    with structlog.testing.capture_logs() as events:
        load_config(repo_root=tmp_path, cli_overrides={})

    loaded = [e for e in events if e.get("event") == "config.loaded"]
    assert len(loaded) == 1
    assert loaded[0]["provenance"] == {
        "max_concurrent_probes": "defaults",
        "cache_ttl_hours": "defaults",
        "enable_audit": "defaults",
    }


# ─── Section G — Code hygiene + metamorphic relations ─────────────────────

def test_loader_package_does_not_import_pydantic_or_jsonschema_or_blake3_at_top_level():
    """AC-18 — cold-start budget protection. loader.py and defaults.py
    are on the CLI startup path and must not pull in heavy modules."""
    import codegenie.config.loader as loader_mod
    import codegenie.config.defaults as defaults_mod
    for mod in (loader_mod, defaults_mod):
        src = inspect.getsource(mod)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {(node.module or "").split(".")[0]}
            else:
                continue
            forbidden = names & {"pydantic", "jsonschema", "blake3"}
            assert not forbidden, (
                f"{mod.__name__} top-level import of {forbidden} violates "
                f"cold-start budget (AC-18)"
            )


def test_cli_default_value_override_is_metamorphic_equal_to_no_override(tmp_path, monkeypatch):
    """AC-21 — cli override at the default value yields a Config equal to
    no override (Config equality is field-by-field). Provenance MAY differ
    (cli vs defaults) — that's AC-15's distinct invariant, asserted there."""
    from codegenie.config import load_config
    fake_home = tmp_path / "no-home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    a = load_config(repo_root=tmp_path, cli_overrides={})
    b = load_config(repo_root=tmp_path, cli_overrides={"max_concurrent_probes": 8})
    assert a == b
```

Run; confirm `ImportError` (no `codegenie.config` module yet). Commit the failing tests.

### Green — make it pass

Land `defaults.py` and `loader.py` minimally:

- `defaults.py` — the frozen `Config` dataclass + the two helpers (`_defaults()`, `_known_fields()`).
- `loader.py`:
  - `_read_yaml_if_exists` — try/except on `FileNotFoundError` returning `{}`; try/except on `yaml.YAMLError` raising `ConfigError(...) from`; an `isinstance(parsed, Mapping)` check after parsing.
  - `_check_unknown_keys` — set-diff `data.keys() - known`; on miss, call `difflib.get_close_matches(key, list(known), n=1, cutoff=0.6)` and format the message per AC-11 / AC-12.
  - `_typed_construct` — `try: return Config(**merged) except TypeError as err: raise ConfigError(...) from err`. (Note: `TypeError` from `Config(**merged)` is sufficient for unexpected-keyword arguments and missing-required-positional cases; for *silent* coercion in the rare future case where a dataclass field's default value type is `object`, a separate type-pin would be needed. Phase 0's three fields are all primitive-typed, so `Config(**{"max_concurrent_probes": "eight"})` does *not* raise — the test uses dataclass type enforcement via an explicit per-field `isinstance` check inside `_typed_construct`, raising `TypeError` that the wrapper then turns into `ConfigError`.)
  - `load_config` — orchestration per Implementation outline step 3.
- `__init__.py` — `from .defaults import Config; from .loader import load_config; __all__ = ("Config", "load_config")`.

### Refactor — clean up

- Docstrings on `load_config`, `Config`, and the three private helpers.
- Module docstring on `loader.py` notes the precedence order, the `ConfigError` failure surface (unknown key + parse error + non-mapping + type mismatch), and the env-var-expansion-off invariant — with a `# AC-13` comment near any `import os` that might tempt a future contributor to call `os.environ`.
- `_provenance(merged, sources_seen) -> dict[str, str]` is a small standalone helper returning `dict[field, source]` for the structlog kwarg.
- Confirm `yaml.safe_load` is the only `yaml.*` API referenced (the AC-5 AST scan will catch a slip, but a manual grep belt-and-suspenders is cheap).
- Confirm `mypy --strict` is clean with zero `# type: ignore` comments in new code (AC-17).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/config/__init__.py` | New — package marker; re-exports `Config`, `load_config` |
| `src/codegenie/config/defaults.py` | New — `Config` frozen dataclass + `_defaults()` + `_known_fields()` |
| `src/codegenie/config/loader.py` | New — `load_config` four-source merge + unknown-key check + parse/type wrapping + provenance log |
| `tests/unit/test_config_loader.py` | New — anchors precedence, unknown-key rejection, env-var-off (AST + spy), provenance via `capture_logs`, frozen-dataclass pin, yaml.safe_load AST scan |

## Out of scope

- **CLI flag parsing** — handled by S4-02 in `cli.py`. This story takes a pre-parsed `cli_overrides: dict`.
- **`click.option`s reading env vars** — explicitly **off** at the CLI level (`auto_envvar_prefix=None`); the *system-level* env-var-off close requires that flag in S4-02. This loader's AC-13 + AC-14 anchor only the loader's half. See "See also: S4-02" in the story header.
- **Config schema validation via JSON Schema** — Phase 0 uses the dataclass + unknown-key check as the validator. JSON Schema for `config.yaml` is a Phase 1+ improvement if pain emerges.
- **Re-enabling env-var expansion** — explicitly deferred to Phase 9 (`phase-arch-design.md §Harness engineering / Configuration`). An ADR-of-record for the Phase 0 → Phase 9 transition is a separate-track follow-up (see Validation notes follow-up #3).
- **`schema-version.txt` sidecar handling** — that's a Writer / CLI concern (S3-03 / S4-02), not Config.
- **Property-based testing of the suggestion algorithm** — with three fields and `difflib`'s opaque scoring, a property test would mostly verify `difflib`'s own behavior. Example-based tests (AC-11, AC-12) are stronger here. Re-evaluate when `Config` exceeds ~10 fields.
- **YAML 1.1 boolean truthiness footguns** (`yes`/`no`/`on`/`off`) — `yaml.safe_load` parses these to `bool` by spec; AC-9 catches the case where a *quoted-string* `"yes"` is supplied for a `bool` field. Loosening this to accept string truthiness would be a Phase 9+ ergonomics decision, not a Phase 0 contract.
- **Parent-directory fsync for the YAML reads** — they're read-only operations; no fsync semantics apply.
- **Symlinked `~/.codegenie/config.yaml`** — `Path.home()` is the developer's home; treating symlinks within it as hostile is out of scope for Phase 0. (Symlink-refusal applies to the *analyzed* repo's outputs, owned by S3-03.)

## Notes for the implementer

- `Config` is **additive across phases** (`phase-arch-design.md §Development view`, line 273). Fields will be added in later phases without breaking this story; do **not** freeze the dataclass via ADR — internal helper, not contract.
- The "did you mean?" suggestion is purely a UX nicety; if `difflib.get_close_matches` returns an empty list (no close match), include the key in the error and **omit the entire suggestion clause** (`"did you mean"` string must not appear). AC-12 + `test_unknown_key_no_close_match_omits_did_you_mean` enforce this.
- `yaml.safe_load(None)` returns `None`; `yaml.safe_load("")` also returns `None`; `yaml.safe_load("# comment only")` also returns `None`; `yaml.safe_load("null")` returns `None`. Treat all four as `{}` to keep the merge well-typed.
- The provenance log at DEBUG is what makes "where did this value come from?" debuggable in CI — don't skip it. Structlog kwargs: `event="config.loaded"`, `provenance={...}`. The dict covers **every** declared field (AC-15), with sources from the closed set `{"defaults", "global", "repo", "cli"}` (matches `final-design.md §2.13` and `§4 step 4` vocabulary). Lazy-import structlog inside the function body to keep `loader.py`'s top-level import set tight (AC-18).
- Env-var-off is a security property (closes a path-traversal vector — `phase-arch-design.md §Harness engineering / Configuration` line 760). The loader contributes by *not* calling `os.path.expandvars`, `string.Template.substitute`, `os.path.expanduser`, or `os.environ[...]` / `os.getenv(...)` on any YAML key or value. AC-13's AST scan makes this load-bearing. (`Path.home()` internally consults `pwd` / `HOME`, which is fine — the prohibition is on applying env expansion to *YAML values*.)
- A YAML value that fails type-check (e.g., `max_concurrent_probes: "eight"`, `cache_ttl_hours: 1.5`, `enable_audit: "yes"`) does NOT trigger `TypeError` from `@dataclass(frozen=True)` construction alone — dataclasses don't enforce types at runtime. `_typed_construct` therefore performs an explicit per-field `isinstance(value, field.type)` check **after** unpacking, raising `TypeError("invalid value for <field>: expected <type>, got <repr>")`, then `load_config` wraps that into `ConfigError(...) from err`. AC-9 enforces.
- For the non-mapping check (AC-7), use `isinstance(parsed, Mapping)` (not `isinstance(parsed, dict)`) for safe-load returns. `yaml.safe_load` always returns `dict` for mappings, but the looser check matches the spirit.
- `codegenie.config` must **not** import `pydantic`, `jsonschema`, or `blake3` at module top level — the loader is on the CLI cold-start path. `structlog` is allowed but should be imported lazily inside the function body that emits `config.loaded`, not at module top level. AC-18 + `test_loader_package_does_not_import_pydantic_or_jsonschema_or_blake3_at_top_level` enforce.
- `final-design.md §2.13` line 316 names "Levenshtein"; in Python, the obvious tool is `difflib.get_close_matches`, which uses Ratcliff-Obershelp ratio (not edit distance). The story adopts `difflib` per implementer-friendliness; the design's "Levenshtein" wording is satisfied in spirit ("an edit-distance-style suggestion"). A follow-up to the design doc was filed (see Validation notes follow-up #1).
- Phase 0 has three fields; the unknown-key check works even with a small surface because `get_close_matches(cutoff=0.6)` falls back to "no suggestion" gracefully on truly-unrelated keys (AC-12 covers).
