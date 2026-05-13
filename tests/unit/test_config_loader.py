"""S3-04 — Config loader + defaults.

Anchors the 21 acceptance criteria for `codegenie.config`:

- Section A: frozen `Config` dataclass shape (AC-1, AC-2, AC-19, AC-20)
- Section B: 4-source precedence (AC-3, AC-4)
- Section C: YAML parsing safety (AC-5, AC-6, AC-7, AC-8, AC-9, AC-10)
- Section D: unknown-key check (AC-11, AC-12)
- Section E: env-var-off (AC-13, AC-14)
- Section F: provenance at DEBUG (AC-15, AC-16)
- Section G: code hygiene + metamorphic (AC-17, AC-18, AC-21)
"""

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
    """Redirect ``Path.home()`` to ``tmp_path/home``; yield a writer for the user yaml.

    A test that uses this fixture never touches the developer's real
    ``~/.codegenie/``. The redirect applies for the lifetime of the test only.
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


# ─── Section A — Config dataclass shape ───────────────────────────────────


def test_config_is_frozen_dataclass_with_pinned_defaults() -> None:
    """AC-1, AC-20 — catches the ``frozen=True → frozen=False`` mutant,
    the ``@dataclass → regular class`` mutant, AND silent default-value drift.
    """
    from codegenie.config import Config

    assert dataclasses.is_dataclass(Config)
    assert Config.__dataclass_params__.frozen is True  # type: ignore[attr-defined]

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


def test_config_package_reexports() -> None:
    """AC-2, AC-19 — Config and load_config reachable via codegenie.config."""
    import codegenie.config as pkg

    assert hasattr(pkg, "Config")
    assert hasattr(pkg, "load_config")
    if hasattr(pkg, "__all__"):
        assert {"Config", "load_config"} <= set(pkg.__all__)


# ─── Section B — Source precedence ────────────────────────────────────────


def test_defaults_only_when_no_yaml_and_no_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-3 baseline — return type is Config and default values survive."""
    from codegenie.config import Config, load_config

    fake_home = tmp_path / "no-home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    cfg = load_config(repo_root=tmp_path, cli_overrides={})
    assert isinstance(cfg, Config)
    assert cfg == Config()


@pytest.mark.parametrize(
    "user_val, repo_val, cli_val, expected",
    [
        (None, None, None, 8),
        (4, None, None, 4),
        (None, 2, None, 2),
        (None, None, 1, 1),
        (4, 2, None, 2),
        (4, None, 1, 1),
        (None, 2, 1, 1),
        (4, 2, 1, 1),
    ],
)
def test_precedence_pairwise_matrix(
    tmp_path: Path,
    write_user_yaml,
    write_repo_yaml,
    user_val: int | None,
    repo_val: int | None,
    cli_val: int | None,
    expected: int,
) -> None:
    """AC-3 — every adjacent-swap mutant in the 4-source chain fails ≥1 row."""
    from codegenie.config import load_config

    if user_val is not None:
        write_user_yaml(f"max_concurrent_probes: {user_val}\n")
    if repo_val is not None:
        write_repo_yaml(f"max_concurrent_probes: {repo_val}\n")
    overrides: dict[str, Any] = {} if cli_val is None else {"max_concurrent_probes": cli_val}
    cfg = load_config(repo_root=tmp_path, cli_overrides=overrides)
    assert cfg.max_concurrent_probes == expected


def test_disjoint_keys_across_sources_yield_union(
    tmp_path: Path, write_user_yaml, write_repo_yaml
) -> None:
    """AC-3 — disjoint-key merge is per-field, not wholesale-replace."""
    from codegenie.config import load_config

    write_user_yaml("max_concurrent_probes: 4\n")
    write_repo_yaml("cache_ttl_hours: 12\n")
    cfg = load_config(repo_root=tmp_path, cli_overrides={"enable_audit": False})
    assert cfg.max_concurrent_probes == 4
    assert cfg.cache_ttl_hours == 12
    assert cfg.enable_audit is False


def test_user_yaml_only_field_survives_when_no_repo_yaml(tmp_path: Path, write_user_yaml) -> None:
    """AC-3 — mutant 'reads only repo YAML, ignores user YAML' fails here."""
    from codegenie.config import load_config

    write_user_yaml("cache_ttl_hours: 12\n")
    cfg = load_config(repo_root=tmp_path, cli_overrides={})
    assert cfg.cache_ttl_hours == 12


# ─── Section C — YAML parsing safety ──────────────────────────────────────


def test_loader_uses_only_yaml_safe_load() -> None:
    """AC-5 — AST-scan: loader.py calls yaml.safe_load only."""
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
    tmp_path: Path, write_repo_yaml, payload: str
) -> None:
    """AC-6 — yaml.safe_load returns None on these; loader coerces to {}."""
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
    tmp_path: Path, write_repo_yaml, payload: str, top_level_type: str
) -> None:
    """AC-7 — non-mapping top level raises ConfigError naming path + type."""
    from codegenie.config import load_config

    p = write_repo_yaml(payload)
    with pytest.raises(ConfigError) as ei:
        load_config(repo_root=tmp_path, cli_overrides={})
    msg = str(ei.value)
    assert str(p) in msg or ".codegenie/config.yaml" in msg
    assert top_level_type in msg or "mapping" in msg.lower()


def test_malformed_yaml_wraps_yaml_error_with_cause(tmp_path: Path, write_repo_yaml) -> None:
    """AC-8 — yaml.YAMLError wrapped, original chained via __cause__."""
    from codegenie.config import load_config

    write_repo_yaml(":::\nthis is: not [valid: yaml\n")
    with pytest.raises(ConfigError) as ei:
        load_config(repo_root=tmp_path, cli_overrides={})
    assert ".codegenie/config.yaml" in str(ei.value)
    assert ei.value.__cause__ is not None
    assert isinstance(ei.value.__cause__, yaml.YAMLError)


def test_type_mismatch_wraps_typeerror_with_cause(tmp_path: Path, write_repo_yaml) -> None:
    """AC-9 — string-where-int raises ConfigError with TypeError chained."""
    from codegenie.config import load_config

    write_repo_yaml('max_concurrent_probes: "eight"\n')
    with pytest.raises(ConfigError) as ei:
        load_config(repo_root=tmp_path, cli_overrides={})
    msg = str(ei.value)
    assert "max_concurrent_probes" in msg
    assert ei.value.__cause__ is not None
    assert isinstance(ei.value.__cause__, TypeError)


def test_missing_files_and_missing_repo_root_fall_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-10 — no YAML files and missing repo_root yield defaults."""
    from codegenie.config import Config, load_config

    fake_home = tmp_path / "no-home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    nonexistent_repo = tmp_path / "does-not-exist"
    cfg = load_config(repo_root=nonexistent_repo, cli_overrides={})
    assert cfg == Config()


# ─── Section D — Unknown-key check ────────────────────────────────────────


UNKNOWN_KEY_FORMAT = re.compile(r"^unknown key '([^']+)'(?:; did you mean '([^']+)'\?)?$")


def test_unknown_yaml_key_format_offender_before_suggestion(
    tmp_path: Path, write_repo_yaml
) -> None:
    """AC-11 — message format pinned: offender first, then suggestion."""
    from codegenie.config import load_config

    write_repo_yaml("max_concurent_probes: 4\n")
    with pytest.raises(ConfigError) as ei:
        load_config(repo_root=tmp_path, cli_overrides={})
    m = UNKNOWN_KEY_FORMAT.match(str(ei.value))
    assert m is not None, f"unexpected format: {str(ei.value)!r}"
    assert m.group(1) == "max_concurent_probes"
    assert m.group(2) == "max_concurrent_probes"


def test_unknown_cli_key_format_offender_before_suggestion(tmp_path: Path) -> None:
    """AC-11 — same format from cli source, not just yaml source."""
    from codegenie.config import load_config

    with pytest.raises(ConfigError) as ei:
        load_config(repo_root=tmp_path, cli_overrides={"cache_ttl_hour": 1})
    m = UNKNOWN_KEY_FORMAT.match(str(ei.value))
    assert m is not None, f"unexpected format: {str(ei.value)!r}"
    assert m.group(1) == "cache_ttl_hour"
    assert m.group(2) == "cache_ttl_hours"


def test_unknown_key_suggestion_is_single_closest_match(tmp_path: Path, write_repo_yaml) -> None:
    """AC-11 — suggestion is the single closest match, not an enumeration."""
    from codegenie.config import load_config

    write_repo_yaml("max_concurent_probes: 4\n")
    with pytest.raises(ConfigError) as ei:
        load_config(repo_root=tmp_path, cli_overrides={})
    msg = str(ei.value)
    assert "max_concurrent_probes" in msg
    assert "enable_audit" not in msg
    assert "cache_ttl_hours" not in msg


def test_unknown_key_no_close_match_omits_did_you_mean(tmp_path: Path) -> None:
    """AC-12 — when get_close_matches returns [], entire clause is omitted."""
    from codegenie.config import load_config

    with pytest.raises(ConfigError) as ei:
        load_config(repo_root=tmp_path, cli_overrides={"zzz_totally_unrelated": 1})
    msg = str(ei.value)
    assert "zzz_totally_unrelated" in msg
    assert "did you mean" not in msg.lower(), (
        f"no close match; suggestion clause must be absent. got: {msg!r}"
    )
    assert UNKNOWN_KEY_FORMAT.match(msg) is not None


# ─── Section E — Env-var-off (security) ────────────────────────────────────


def test_loader_module_does_not_reference_env_expansion_apis() -> None:
    """AC-13 — AST-scan: loader.py has no reference to env-expansion APIs."""
    import codegenie.config.loader as loader_mod

    src = inspect.getsource(loader_mod)
    tree = ast.parse(src)
    banned_attrs = {"expandvars", "Template", "expanduser", "environ", "getenv"}
    banned_names = {"Template"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in banned_attrs:
            raise AssertionError(
                f"loader.py references banned env-expansion API '.{node.attr}' "
                f"(line {node.lineno}); AC-13 forbids env-var sourcing for YAML values"
            )
        if isinstance(node, ast.Name) and node.id in banned_names:
            raise AssertionError(
                f"loader.py references banned env-expansion name '{node.id}' (line {node.lineno})"
            )


def test_loader_preserves_dollar_literal_in_merged_dict(
    tmp_path: Path,
    write_repo_yaml,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-14 — a YAML value literal like '$ENV_VAR' passes through unchanged."""
    import codegenie.config.loader as loader_mod

    monkeypatch.setenv("ENV_VAR", "999")
    write_repo_yaml('cache_ttl_hours: "$ENV_VAR"\n')

    captured: dict[str, Any] = {}
    real = loader_mod._typed_construct

    def spy(merged: dict[str, Any]):
        captured.update(merged)
        return real(merged)

    monkeypatch.setattr(loader_mod, "_typed_construct", spy)
    with pytest.raises(ConfigError):
        loader_mod.load_config(repo_root=tmp_path, cli_overrides={})
    assert captured.get("cache_ttl_hours") == "$ENV_VAR", (
        f"loader expanded $ENV_VAR; expected literal preservation. got: {captured!r}"
    )


# ─── Section F — Provenance (DEBUG observability) ─────────────────────────


def test_provenance_event_covers_every_field_with_correct_source(
    tmp_path: Path, write_user_yaml, write_repo_yaml
) -> None:
    """AC-15, AC-16 — one config.loaded event whose provenance covers ALL fields."""
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
    assert ev["provenance"] == {
        "max_concurrent_probes": "repo",
        "cache_ttl_hours": "global",
        "enable_audit": "cli",
    }


def test_provenance_event_when_nothing_overrides_labels_all_as_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-15 — every field's provenance source is 'defaults' when no overrides."""
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


def test_loader_package_does_not_import_pydantic_or_jsonschema_or_blake3_at_top_level() -> None:
    """AC-18 — cold-start budget: no heavy imports at module top level."""
    import codegenie.config.defaults as defaults_mod
    import codegenie.config.loader as loader_mod

    for mod in (loader_mod, defaults_mod):
        src = inspect.getsource(mod)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            names: set[str]
            if isinstance(node, ast.Import):
                names = {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {(node.module or "").split(".")[0]}
            else:
                continue
            forbidden = names & {"pydantic", "jsonschema", "blake3"}
            assert not forbidden, (
                f"{mod.__name__} top-level import of {forbidden} violates cold-start budget (AC-18)"
            )


def test_cli_default_value_override_is_metamorphic_equal_to_no_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-21 — cli override at default value is value-equal to no override."""
    from codegenie.config import load_config

    fake_home = tmp_path / "no-home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    a = load_config(repo_root=tmp_path, cli_overrides={})
    b = load_config(repo_root=tmp_path, cli_overrides={"max_concurrent_probes": 8})
    assert a == b
