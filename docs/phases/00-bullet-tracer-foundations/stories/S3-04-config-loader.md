# Story S3-04 — Config loader + defaults

**Step:** Step 3 — Build the harness internals (cache, coordinator, validator, sanitizer, writer, config)
**Status:** Ready
**Effort:** S
**Depends on:** S2-05
**ADRs honored:** —

## Context

The Coordinator (S3-05), the CacheStore (S3-01), and the CLI (S4-02) all need a `Config` object. Phase 0's `Config` is a frozen dataclass with three fields (`max_concurrent_probes`, `cache_ttl_hours`, `enable_audit`) — additive across phases, not a frozen contract. The loader merges three sources (defaults < `~/.codegenie/config.yaml` < `<repo>/.codegenie/config.yaml` < CLI overrides), with `ConfigError` on unknown keys and a `difflib.get_close_matches` "did you mean?" suggestion. Env-var expansion is **off** (`auto_envvar_prefix=None` at the click level) — a deliberate path-traversal close per `phase-arch-design.md §Harness engineering / Configuration`.

This story is independent of S3-01/02/03 (no shared types beyond `errors.ConfigError`) and lands a small, testable surface that S3-05 and S4-02 consume.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design / Config` — three-source merge, fail-loud-on-unknown-keys, `difflib` suggestion
  - `../phase-arch-design.md §Harness engineering / Configuration` — precedence rules, env-var expansion off, provenance logged at DEBUG
- **Source design:**
  - `../final-design.md §2.13` — Config precedence and unknown-key policy
- **Existing code (if any):**
  - `src/codegenie/errors.py` — `ConfigError`
  - `src/codegenie/logging.py` — `configure_logging` (S2-01); use structlog at DEBUG for provenance

## Goal

`load_config(repo_root, cli_overrides)` returns a frozen `Config` instance assembled from defaults < user YAML < repo YAML < CLI overrides; an unknown key in either YAML or CLI raises `ConfigError("unknown key: <k>; did you mean <suggestion>?")`.

## Acceptance criteria

- [ ] `src/codegenie/config/defaults.py` declares `Config` as a frozen `@dataclass` with fields `max_concurrent_probes: int = 8`, `cache_ttl_hours: int = 24`, `enable_audit: bool = True`.
- [ ] `src/codegenie/config/loader.py` exports `load_config(repo_root: Path, cli_overrides: dict[str, Any]) -> Config`.
- [ ] Source order, lowest to highest precedence: built-in defaults, `~/.codegenie/config.yaml`, `<repo_root>/.codegenie/config.yaml`, `cli_overrides`. Each later source overrides earlier ones on a per-field basis.
- [ ] Both YAML files are parsed via `yaml.safe_load` (never `yaml.load(...)` without `Loader=`).
- [ ] Unknown keys (present in YAML or CLI but not declared on `Config`) raise `ConfigError` whose message includes the offending key **and** a "did you mean: <closest-defaulted-name>?" suggestion from `difflib.get_close_matches`.
- [ ] Env-var expansion in YAML is **off** — `$HOME`, `${FOO}`, etc., are preserved literally (no shell interpolation).
- [ ] Missing files are not errors — each YAML source is optional; absence falls through to lower precedence.
- [ ] At DEBUG level, the loader logs a `config.loaded` structlog event listing each non-default field's *source* (`defaults`, `user_yaml`, `repo_yaml`, `cli`) — provenance per `phase-arch-design.md §Harness engineering / Configuration`.
- [ ] `tests/unit/test_config_loader.py` exercises every branch below and is green; `ruff`, `mypy --strict`, and `pytest` clean on touched files.

## Implementation outline

1. Author `src/codegenie/config/__init__.py` (package marker; re-export `Config`, `load_config`).
2. Author `src/codegenie/config/defaults.py`: the frozen `Config` dataclass and a `_defaults() -> dict[str, Any]` helper returning the field defaults.
3. Author `src/codegenie/config/loader.py`:
   - `_known_fields() -> set[str]` from `dataclasses.fields(Config)`.
   - `_read_yaml_if_exists(path)` returning `{}` on missing file.
   - `_check_unknown_keys(source_name, data)` → walks `data.keys()`; on miss, raises `ConfigError` with `difflib.get_close_matches(key, _known_fields(), n=1, cutoff=0.6)`.
   - `load_config(repo_root, cli_overrides)`: merge dicts in precedence order, validate each source, instantiate `Config(**merged)`, log provenance, return.
4. Write the unit tests.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file path: `tests/unit/test_config_loader.py`

```python
# tests/unit/test_config_loader.py
from pathlib import Path
import pytest
from codegenie.errors import ConfigError

def test_defaults_only_when_no_yaml_and_no_overrides(tmp_path):
    cfg = load_config(repo_root=tmp_path, cli_overrides={})
    assert cfg.max_concurrent_probes == 8
    assert cfg.cache_ttl_hours == 24
    assert cfg.enable_audit is True

def test_repo_yaml_overrides_user_yaml(tmp_path, monkeypatch):
    # arrange: write ~/.codegenie/config.yaml with max_concurrent_probes=4
    #          write <repo>/.codegenie/config.yaml with max_concurrent_probes=2
    # act
    cfg = load_config(repo_root=tmp_path, cli_overrides={})
    # assert
    assert cfg.max_concurrent_probes == 2

def test_cli_overrides_repo_yaml(tmp_path):
    # arrange: repo yaml sets max_concurrent_probes=2
    # act: load_config(..., cli_overrides={"max_concurrent_probes": 1})
    # assert: cfg.max_concurrent_probes == 1
    ...

def test_unknown_key_in_repo_yaml_raises_with_did_you_mean(tmp_path):
    # arrange: <repo>/.codegenie/config.yaml has "max_concurent_probes: 4" (typo)
    # act + assert
    with pytest.raises(ConfigError) as ei:
        load_config(repo_root=tmp_path, cli_overrides={})
    assert "max_concurent_probes" in str(ei.value)
    assert "max_concurrent_probes" in str(ei.value)  # the suggestion

def test_unknown_key_in_cli_overrides_raises():
    with pytest.raises(ConfigError):
        load_config(repo_root=Path("/tmp"), cli_overrides={"nope": 1})

def test_env_var_expansion_off(tmp_path):
    # arrange: <repo>/.codegenie/config.yaml has "cache_ttl_hours: $ENV_VAR"
    #          env $ENV_VAR=999
    # act
    cfg = load_config(...)
    # assert: cfg.cache_ttl_hours has been read as the literal string "$ENV_VAR"
    #         (will likely raise a TypeError during Config construction since the
    #         field is typed int; capture that and reframe as "loader does not expand")
    ...

def test_missing_yaml_files_are_not_errors(tmp_path):
    # neither user nor repo YAML exists; load_config returns defaults cleanly
    assert load_config(repo_root=tmp_path, cli_overrides={}) is not None

def test_provenance_logged_at_debug(tmp_path, caplog):
    # arrange: configure_logging(verbose=True); repo yaml sets one field
    # act: load_config(...)
    # assert: caplog contains a "config.loaded" event with per-field source labels
    ...
```

Run; confirm `ImportError`. Commit.

### Green — make it pass

Land `defaults.py` and `loader.py` minimally. The merge is two `dict.update` calls; the unknown-key check is one set diff + `difflib.get_close_matches`. The provenance log is one structlog `bind`/`info` call.

### Refactor — clean up

- Docstrings on `load_config` and `Config`.
- Module docstring on `loader.py` notes the precedence order and the env-var-expansion-off invariant.
- Confirm `yaml.safe_load` is used (not `yaml.load` without `Loader=` — the pre-commit hook would fail otherwise).
- Add a small `_provenance(merged, sources)` helper that returns `dict[field, source]` for the log event.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/config/__init__.py` | New — package marker; re-exports `Config`, `load_config` |
| `src/codegenie/config/defaults.py` | New — `Config` frozen dataclass |
| `src/codegenie/config/loader.py` | New — `load_config` three-source merge + unknown-key check |
| `tests/unit/test_config_loader.py` | New — anchors precedence, unknown-key rejection, env-var-off, provenance |

## Out of scope

- **CLI flag parsing** — handled by S4-02 in `cli.py`. This story takes a pre-parsed `cli_overrides: dict`.
- **`click.option`s reading env vars** — explicitly **off** at the CLI level (`auto_envvar_prefix=None`); reaffirmed in S4-02.
- **Config schema validation via JSON Schema** — Phase 0 uses the dataclass + unknown-key check as the validator. JSON Schema for `config.yaml` is a Phase 1+ improvement if pain emerges.
- **Re-enabling env-var expansion** — explicitly deferred to Phase 9 (`phase-arch-design.md §Harness engineering / Configuration`).
- **`schema-version.txt` sidecar handling** — that's a Writer / CLI concern (S3-03 / S4-02), not Config.

## Notes for the implementer

- `Config` is **additive across phases** (`phase-arch-design.md §Development view`). Fields will be added in later phases without breaking this story; do not freeze the dataclass via ADR — internal helper, not contract.
- The "did you mean?" suggestion is purely a UX nicety; if `difflib.get_close_matches` returns an empty list (no close match), include the key in the error but omit the suggestion clause.
- `yaml.safe_load(None)` returns `None`; `yaml.safe_load("")` also returns `None`. Treat both as `{}` to keep the merge well-typed.
- The provenance log at DEBUG is what makes "where did this value come from?" debuggable in CI — don't skip it. Structlog kwargs: `event="config.loaded"`, `provenance={...}`.
- Env-var-off is a security property (closes a path-traversal vector — `phase-arch-design.md §Harness engineering / Configuration` notes `auto_envvar_prefix=None` at the click level). Even though that lives in S4-02's CLI code, this loader contributes by *not* calling `os.path.expandvars` or `string.Template` substitution on any YAML value.
- A YAML value that fails dataclass type-check (e.g., `max_concurrent_probes: "eight"`) will raise `TypeError` from `Config(**merged)`. Wrap that into `ConfigError("invalid value for <field>: ...")` for a clean message — but keep the original exception via `raise ... from`.
- Phase 0 has three fields; the unknown-key check works even with a small surface because `get_close_matches` falls back to "no suggestion" gracefully.
