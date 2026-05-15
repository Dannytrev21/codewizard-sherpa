"""Shared helpers for the Phase-1 adversarial-fixture corpus (S5-01/02/03).

Three pure-ish entry points the cap-family tests share:

- :func:`invoke_gather` — single seam for driving the CLI; parses the
  emitted ``repo-context.yaml`` so callers can assert on
  ``result.context["probes"][probe_name]`` directly.
- :func:`assert_parser_cap_event` — exactly-one-event filter on
  ``probe.parser.cap_exceeded`` with a four-field keyword-argument pin.
- :func:`expected_lockfile_error_id` — drift-guard wrapper around
  ``node_manifest._ERROR_PREFIX_BY_KIND`` / ``_ERROR_SUFFIX_BY_EXC``.

The lift-out is required (not optional) — the rule-of-three threshold is
met across the four adversarial-cap stories (S5-01 lands four tests
today; S5-02 / S5-03 inherit). Per ``S5-01-adversarial-parser-caps.md``
AC-7 / AC-8 / AC-9.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml as _yaml
from click.testing import CliRunner, Result

from codegenie.cli import cli
from codegenie.probes.node_manifest import (
    _ERROR_PREFIX_BY_KIND,
    _ERROR_SUFFIX_BY_EXC,
    ParserKind,
)

__all__ = [
    "GatherResult",
    "assert_parser_cap_event",
    "expected_lockfile_error_id",
    "invoke_gather",
]


@dataclass(frozen=True)
class GatherResult:
    """Thin envelope around :class:`click.testing.Result` with parsed context.

    - ``context`` is the parsed ``.codegenie/context/repo-context.yaml``;
      callers index into it directly (``result.context["probes"][name]``).
    - ``context_yaml_text`` is the raw bytes-as-text of that YAML, for
      sentinel-substring no-leak assertions (S5-03 AC-3).
    - ``raw_jsons`` maps each raw-artifact filename under
      ``.codegenie/context/raw/`` to its text contents, for the same
      no-leak invariant against any per-probe raw output. Missing dir →
      empty dict.
    """

    exit_code: int
    output: str
    context: dict[str, Any]
    context_yaml_text: str
    raw_jsons: dict[str, str]


def invoke_gather(repo: Path) -> GatherResult:
    """Run ``codegenie --no-gitignore gather <repo>`` and parse the envelope.

    Mirrors :func:`tests.smoke.test_cli_end_to_end._invoke_gather` and
    additionally reads ``.codegenie/context/repo-context.yaml`` so the
    adversarial tests can assert closed-world equality on the slice's
    ``errors`` / ``warnings`` fields without re-parsing in every caller.
    Also collects the raw YAML text plus every raw-artifact JSON under
    ``.codegenie/context/raw/`` so S5-03's no-leak canary can scan every
    byte the gather emits.
    """
    res: Result = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])
    ctx_path = repo / ".codegenie" / "context" / "repo-context.yaml"
    parsed: dict[str, Any] = {}
    yaml_text = ""
    if ctx_path.exists():
        yaml_text = ctx_path.read_text(encoding="utf-8")
        loaded = _yaml.safe_load(yaml_text)
        if isinstance(loaded, dict):
            parsed = loaded
    raw_dir = repo / ".codegenie" / "context" / "raw"
    raw_jsons: dict[str, str] = {}
    if raw_dir.is_dir():
        for raw_path in sorted(raw_dir.iterdir()):
            if raw_path.is_file():
                raw_jsons[raw_path.name] = raw_path.read_text(encoding="utf-8")
    return GatherResult(
        exit_code=res.exit_code,
        output=res.output,
        context=parsed,
        context_yaml_text=yaml_text,
        raw_jsons=raw_jsons,
    )


def assert_parser_cap_event(
    logs: Sequence[Mapping[str, Any]],
    *,
    parser_kind: str,
    cap_kind: Literal["size", "depth"],
    cap: int,
    path: Path,
) -> None:
    """Pin the ``probe.parser.cap_exceeded`` structlog event payload.

    Filters ``logs`` for the cap-exceeded event, asserts exactly one
    match, and pins the four structured fields (``parser_kind``,
    ``cap_kind``, ``cap``, ``path``). The ``Literal["size", "depth"]`` on
    ``cap_kind`` is a type-level guard against a ``cap_kind="bytes"``
    drift (see S1-03 validation §AC-14 footnote).
    """
    matches = [e for e in logs if e.get("event") == "probe.parser.cap_exceeded"]
    assert len(matches) == 1, (
        f"expected exactly 1 cap_exceeded event, got {len(matches)}: {matches!r}"
    )
    ev = matches[0]
    assert ev["parser_kind"] == parser_kind, ev
    assert ev["cap_kind"] == cap_kind, ev
    assert ev["cap"] == cap, ev
    assert ev["path"] == str(path), ev


def expected_lockfile_error_id(parser_kind: ParserKind, exc_type: type[BaseException]) -> str:
    """Construct the expected lockfile error_id from the registry — drift guard.

    Imports ``_ERROR_PREFIX_BY_KIND`` and ``_ERROR_SUFFIX_BY_EXC`` from
    :mod:`codegenie.probes.node_manifest` so a future vocabulary change
    (``pnpm_lock`` → ``pnpm``) flips every adversarial-test expectation
    in lockstep with the implementation rather than silently masking the
    drift.
    """
    return f"{_ERROR_PREFIX_BY_KIND[parser_kind]}.{_ERROR_SUFFIX_BY_EXC[exc_type]}"
