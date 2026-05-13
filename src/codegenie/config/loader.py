"""Four-source config loader for Phase 0.

Precedence (lowest → highest):
``defaults < ~/.codegenie/config.yaml < <repo_root>/.codegenie/config.yaml < cli_overrides``

Failure surface (every case raises :class:`codegenie.errors.ConfigError`,
with the original exception chained via ``raise ... from err`` where
applicable):

- unknown key in either YAML or ``cli_overrides``
  (``"unknown key '<k>'; did you mean '<closest>'?"`` — clause omitted if no
  close match found)
- YAML parse error (``yaml.YAMLError`` chained)
- YAML top-level that is not a mapping (file path + actual type named)
- value type does not match declared ``Config`` field type
  (``TypeError`` chained)

**Env-var-off (AC-13):** this module never calls ``os.path.expandvars``,
``string.Template.substitute``, ``os.path.expanduser``, ``os.environ[...]``,
or ``os.getenv(...)`` on any YAML key or value. ``Path.home()`` resolves the
user's home directory via ``pwd`` (or ``HOME``) but does not perform any
expansion on YAML payloads. Re-enabling env-var expansion is explicitly
deferred to Phase 9 (``phase-arch-design.md §Harness engineering / Configuration``,
line 760). See ADR-0012 for the test-side enforcement of the bare-``yaml.load``
ban; AC-5 here scans this module structurally.

``structlog`` is imported lazily inside :func:`load_config` so the module's
top-level import set stays tight (the loader is on the CLI cold-start path —
AC-18).
"""

from __future__ import annotations

import difflib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, get_type_hints

import yaml

from codegenie.errors import ConfigError

from .defaults import Config, _defaults, _known_fields

__all__ = ["load_config"]


def _read_yaml_if_exists(path: Path) -> dict[str, Any]:
    """Read a YAML file and return its top-level mapping.

    - Missing file → ``{}`` (lower-precedence source wins; AC-10).
    - Empty / comment-only / ``null``-only file → ``{}`` (AC-6).
    - Malformed YAML → :class:`ConfigError` with ``__cause__`` = the
      original ``yaml.YAMLError`` (AC-8).
    - Non-mapping top level (list, scalar, sequence) → :class:`ConfigError`
      whose message names the file path and the actual top-level type (AC-7).
    """
    try:
        text = path.read_text()
    except FileNotFoundError:
        return {}
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as err:
        raise ConfigError(f"malformed YAML in {path}: {err}") from err
    if parsed is None:
        return {}
    if not isinstance(parsed, Mapping):
        raise ConfigError(f"top-level of {path} must be a mapping; got {type(parsed).__name__}")
    return dict(parsed)


def _check_unknown_keys(source_name: str, data: Mapping[str, Any], known: frozenset[str]) -> None:
    """Raise :class:`ConfigError` on the first key in ``data`` that is not a
    declared ``Config`` field (AC-11 / AC-12).

    Message format is pinned at
    ``"unknown key '<k>'; did you mean '<closest>'?"``. When
    ``difflib.get_close_matches`` returns ``[]`` (no close match), the entire
    ``"; did you mean ..."`` clause is omitted.
    """
    del source_name  # source provenance is logged at DEBUG, not echoed in errors
    for key in data:
        if key in known:
            continue
        suggestions = difflib.get_close_matches(key, list(known), n=1, cutoff=0.6)
        if suggestions:
            raise ConfigError(f"unknown key '{key}'; did you mean '{suggestions[0]}'?")
        raise ConfigError(f"unknown key '{key}'")


def _typed_construct(merged: dict[str, Any]) -> Config:
    """Build a ``Config`` after a per-field ``isinstance`` check (AC-9).

    Dataclasses do not enforce field types at runtime; a value like
    ``max_concurrent_probes="eight"`` would silently land as a ``str``. We
    enforce types explicitly here, wrapping the resulting :class:`TypeError`
    into a :class:`ConfigError` via ``raise ... from err`` so the original
    traceback survives (Rule 12 — fail loud, preserve cause).
    """
    hints = get_type_hints(Config)
    for name, expected_type in hints.items():
        if name not in merged:
            continue
        value = merged[name]
        if not isinstance(value, expected_type):
            err = TypeError(
                f"expected {expected_type.__name__}, got {type(value).__name__}: {value!r}"
            )
            raise ConfigError(f"invalid value for {name}: {err}") from err
    try:
        return Config(**merged)
    except TypeError as err:
        raise ConfigError(f"invalid Config construction: {err}") from err


def _provenance(
    cli: Mapping[str, Any],
    repo: Mapping[str, Any],
    user: Mapping[str, Any],
) -> dict[str, str]:
    """Build a ``field → source-label`` map covering every declared
    ``Config`` field. Labels are drawn from the closed set
    ``{"defaults", "global", "repo", "cli"}`` matching
    ``final-design.md §2.13`` and ``§4 step 4`` vocabulary (AC-15).
    """
    out: dict[str, str] = {}
    for name in _known_fields():
        if name in cli:
            out[name] = "cli"
        elif name in repo:
            out[name] = "repo"
        elif name in user:
            out[name] = "global"
        else:
            out[name] = "defaults"
    return out


def load_config(repo_root: Path, cli_overrides: dict[str, Any]) -> Config:
    """Assemble a :class:`Config` from the four declared sources.

    Order, lowest → highest precedence:

    1. dataclass defaults
    2. ``~/.codegenie/config.yaml`` (``"global"``)
    3. ``<repo_root>/.codegenie/config.yaml`` (``"repo"``)
    4. ``cli_overrides`` (``"cli"``)

    Each source's keys are validated against ``Config``'s declared fields
    *before* merging — an unknown key in any source raises
    :class:`ConfigError` (AC-11 / AC-12). At DEBUG, the loader emits one
    ``config.loaded`` event whose ``provenance`` kwarg maps every declared
    field to the source label that won the merge (AC-15).
    """
    known = _known_fields()
    user_yaml_path = Path.home() / ".codegenie" / "config.yaml"  # AC-4
    user_data = _read_yaml_if_exists(user_yaml_path)
    repo_data = _read_yaml_if_exists(repo_root / ".codegenie" / "config.yaml")

    # Validate each source's keys *before* merging so error attribution
    # is unambiguous (AC-11 covers both YAML and CLI sources).
    _check_unknown_keys("global", user_data, known)
    _check_unknown_keys("repo", repo_data, known)
    _check_unknown_keys("cli", cli_overrides, known)

    merged: dict[str, Any] = {
        **_defaults(),
        **user_data,
        **repo_data,
        **cli_overrides,
    }

    provenance = _provenance(cli_overrides, repo_data, user_data)

    # AC-18: lazy-import structlog inside the function body so the module's
    # top-level import set stays minimal on the CLI cold-start path.
    import structlog  # noqa: PLC0415

    structlog.get_logger(__name__).debug("config.loaded", provenance=provenance)

    return _typed_construct(merged)
