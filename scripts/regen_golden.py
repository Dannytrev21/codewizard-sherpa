"""Regenerate per-probe golden files for the Phase-2 fixture portfolio (S7-03).

Walks ``tests/fixtures/portfolio/<fixture>/`` (skipping ``_``-prefixed
directories), runs ``codegenie gather`` against each, then writes one
canonical-JSON golden per probe per fixture under
``tests/golden/probes/<probe>/<fixture>.json``.

Two modes (mutually exclusive):

- ``--check``  : exit 0 if every golden matches the live output, exit 1 with a
  unified-diff summary on stderr otherwise. Default mode.
- ``--update`` : overwrite every golden with the canonicalized live output.
  ``--update --portfolio`` is the developer-side regeneration command.

The slice for each probe is sourced from the envelope at
``<fixture>/.codegenie/context/repo-context.yaml`` under ``probes.<name>``.
(The original story-text referenced ``raw/<probe>.json`` per probe — the
current gather writer only persists per-probe JSON for ``ci``, ``dep_graph``,
and ``gitleaks``. The YAML envelope is the deterministic single source of
truth for every other probe's slice, so the script reads from there.)

Non-determinism is removed by two complementary tables:

- ``_EXCLUDED_FIELD_NAMES`` — exact field names to drop at any depth.
- ``_EXCLUDED_VALUE_PATTERNS`` — regexes against string values; matched values
  are replaced with a stable sentinel.
- ``_PRESERVED_FIELDS`` — inclusion list that *always wins* over exclusion;
  protects declared-input tokens (image digests, BLAKE3 fingerprints,
  SCIP output-path-relative, etc.) from accidental scrubbing.

The two-runs-byte-identical discipline is enforced by
``tests/golden/test_regen_golden_portfolio_idempotent.py``: after a clean
``--update --portfolio`` pass, a second invocation must produce zero file
changes (Risk #5 — golden-file non-determinism).
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess  # noqa: S404 — script outside the codegenie runtime; scripts/ is exempt from the Layer-C subprocess ban
import sys
import tempfile
from pathlib import Path
from typing import TypeAlias, cast

import yaml

# ---------------------------------------------------------------------------
# Types — recursive JsonValue keeps mypy --strict honest (AC-39)
# ---------------------------------------------------------------------------

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT: Path = Path(__file__).resolve().parents[1]
_PORTFOLIO_DIR: Path = _REPO_ROOT / "tests" / "fixtures" / "portfolio"
_GOLDEN_ROOT: Path = _REPO_ROOT / "tests" / "golden" / "probes"
_COUNT_FILE: Path = _REPO_ROOT / "tests" / "golden" / "probes" / "COUNT.txt"

# ---------------------------------------------------------------------------
# Exclusion + inclusion tables (AC-7, AC-8, AC-37)
# ---------------------------------------------------------------------------

# Field names dropped at any depth. Each entry names the source of
# non-determinism that justifies it.
_EXCLUDED_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "wall_clock_ms",  # per-run elapsed time
        "generated_at",  # envelope-level wall-clock timestamp
        "indexed_at",  # IndexHealth freshness wall-clock
        "last_indexed_at",  # IndexHealth freshness wall-clock
        "current_commit",  # fixture HEAD SHA (varies per CWS commit on shared-git fixtures)
        "run_id",  # per-invocation token
        "duration_ms",  # per-probe elapsed time
        "audit_anchor",  # references a per-run UTC-ISO anchor
    }
)

# Suffix-based exclusion (any field name ending with this is dropped).
_EXCLUDED_FIELD_SUFFIXES: tuple[str, ...] = ("_timestamp",)

# Regex patterns matched against string values. Matched values are replaced
# with the sentinel for that pattern.
_TMP_PATH_RE = re.compile(r"/(tmp|var/folders)/[^\s\"]+")
_TMP_SENTINEL = "<TMPDIR>"
_ABS_REPO_PATH_RE = re.compile(re.escape(str(_REPO_ROOT)))
_ABS_REPO_SENTINEL = "<REPO_ROOT>"

# Inclusion list — fields that must never be scrubbed even if a pattern matches
# (AC-37). Inclusion wins over exclusion.
_PRESERVED_FIELDS: frozenset[str] = frozenset(
    {
        "image_digest",  # ADR-0004 declared-input token
        "output_path_relative",  # SCIP path is fixture-relative + stable
        "fingerprint",  # ADR-0005 BLAKE3 8-hex (deterministic)
        "fingerprints",  # plural form
        "last_indexed",  # stale-scip CommitsBehind.last_indexed (prior fixture SHA)
        "git_commit",  # envelope-level handled by separate carve-out
    }
)

# Per-(probe, field) sort keys for list-of-dict canonicalization (AC-6).
# Keyed by (probe_name, dotted_field_path). The probe_name is the value of
# the top-level ``probes.<name>`` key in the envelope.
_LIST_SORT_KEYS: dict[tuple[str, str], tuple[str, ...]] = {
    ("semgrep", "findings"): ("rule_id", "file", "line", "column"),
    ("ast_grep", "findings"): ("rule_id", "file", "line", "column"),
    ("ripgrep_curated", "findings"): ("rule_id", "file", "line"),
    ("gitleaks", "findings"): ("rule_id", "file", "line", "fingerprint"),
    ("dep_graph", "edges"): ("from", "to"),
}


# ---------------------------------------------------------------------------
# Probe × fixture matrix (AC-25) — single source of truth for which cells
# are expected to produce a golden. Adding or removing a cell here is the
# deliberate edit; COUNT.txt must move in lock-step.
# ---------------------------------------------------------------------------

# All five portfolio fixtures (alphabetical).
_FIXTURE_NAMES: frozenset[str] = frozenset(
    {"distroless-target", "minimal-ts", "monorepo-pnpm", "native-modules", "stale-scip"}
)

# Platform-sensitive probes — adding any of these to ``_UNIVERSAL_PROBES``
# re-tightens AC-16 (forced Linux-only regen, since macOS strace/docker
# diverges or fails the slice). Kept here so the cross-reference is
# grep-discoverable from the matrix definition.
_PLATFORM_SENSITIVE_PROBES: frozenset[str] = frozenset(
    {"runtime_trace", "sbom", "cve", "scip_index", "tree_sitter_import_graph"}
)

# Probes that produce a non-null slice against every fixture (the
# canonical-empty probes — confidence="unavailable" or similar is itself a
# golden cell). This is the slice-producing subset on the current
# Phase-2 portfolio; probes that return ``Skipped`` (and therefore never
# land in the envelope) are not part of the matrix. Adding a new probe
# here is a deliberate edit; ``COUNT.txt`` must move in lock-step
# (enforced by ``tests/golden/test_golden_count_matches.py``).
_UNIVERSAL_PROBES: frozenset[str] = frozenset(
    {
        # Layer A (Phase-1 probes; still surface in Phase-2 fixture gathers)
        "language_detection",
        "node_build_system",
        "node_manifest",
        "ci",
        "deployment",
        "test_inventory",
        # Layer B
        "index_health",
        "dep_graph",
        "generated_code",
        "node_reflection",
        "semantic_index_meta",
        # Layer C
        "certificate",
        "dockerfile",
        "entrypoint",
        "shell_usage",
        # Layer G
        "gitleaks",
        "test_coverage_mapping",
        # Layer E
        "ownership",
    }
)


def _compute_expected_golden_count() -> int:
    """Return the exact number of (probe, fixture) cells that should ship a
    golden under ``tests/golden/probes/`` (AC-25).

    Grep-discoverable; the unit test
    ``tests/golden/test_golden_count_matches.py`` asserts this matches both
    ``COUNT.txt`` and the on-disk file count.
    """
    return len(_UNIVERSAL_PROBES) * len(_FIXTURE_NAMES)


# ---------------------------------------------------------------------------
# Canonicalization
# ---------------------------------------------------------------------------


def _is_excluded_field(name: str) -> bool:
    if name in _PRESERVED_FIELDS:
        return False
    if name in _EXCLUDED_FIELD_NAMES:
        return True
    return any(name.endswith(s) for s in _EXCLUDED_FIELD_SUFFIXES)


def _scrub_string(value: str) -> str:
    """Apply value-pattern scrubbing to a string field."""
    out = _ABS_REPO_PATH_RE.sub(_ABS_REPO_SENTINEL, value)
    out = _TMP_PATH_RE.sub(_TMP_SENTINEL, out)
    return out


def _canonicalize(payload: JsonValue) -> JsonValue:
    """Recursively canonicalize: drop excluded fields, scrub values, sort keys.

    Returns a fresh structure; the input is not mutated. ``mypy --strict``
    exercises the recursive ``JsonValue`` self-reference (no ``Any``).
    """
    if payload is None or isinstance(payload, bool | int | float):
        return payload
    if isinstance(payload, str):
        return _scrub_string(payload)
    if isinstance(payload, list):
        return [_canonicalize(item) for item in payload]
    if isinstance(payload, dict):
        out: dict[str, JsonValue] = {}
        for key in sorted(payload.keys()):
            if _is_excluded_field(key):
                continue
            out[key] = _canonicalize(payload[key])
        return out
    raise TypeError(f"unsupported JsonValue type: {type(payload).__name__}")


def _sort_list_of_dicts(payload: JsonValue, probe_name: str, *, path: str = "") -> JsonValue:
    """Walk and sort any list-of-dict whose (probe_name, dotted-path) appears
    in ``_LIST_SORT_KEYS``. Called after ``_canonicalize`` (keys are already
    sorted; this lifts list ordering).
    """
    if isinstance(payload, dict):
        out: dict[str, JsonValue] = {}
        for key, value in payload.items():
            child_path = f"{path}.{key}" if path else key
            out[key] = _sort_list_of_dicts(value, probe_name, path=child_path)
        return out
    if isinstance(payload, list):
        sort_tuple = _LIST_SORT_KEYS.get((probe_name, path))
        # Recurse first so nested lists/dicts are normalized.
        items = [_sort_list_of_dicts(item, probe_name, path=path) for item in payload]
        if sort_tuple is not None:

            def sort_key(item: JsonValue) -> tuple[object, ...]:
                if isinstance(item, dict):
                    return tuple(
                        (item.get(k) if item.get(k) is not None else "") for k in sort_tuple
                    )
                return ()

            items = sorted(items, key=sort_key)
        return items
    return payload


def _dump_canonical_json(payload: JsonValue) -> str:
    """Serialize ``payload`` to canonical JSON (sorted keys, 2-space indent,
    LF endings, trailing newline)."""
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# Gather invocation (per-fixture)
# ---------------------------------------------------------------------------


def _materialize_fixture(fixture: Path) -> None:
    """Re-run the fixture's ``regenerate.sh`` if present.

    Each fixture under ``tests/fixtures/portfolio/`` owns its
    ``regenerate.sh`` (S7-01 / S7-02 convention). Calling it here:

    * gives ``stale-scip`` a deterministic ``.codegenie/context/raw/scip.json``
      with the pinned ``last_indexed_commit`` value (the load-bearing fact
      the S4-02 adversarial reads);
    * is a no-op-modulo-idempotent for fixtures whose ``regenerate.sh`` only
      ``mkdir -p`` (``minimal-ts``, ``monorepo-pnpm``, ``native-modules``,
      ``distroless-target``).

    Replaces the blanket ``rmtree(.codegenie/context/)`` from the original
    AC-36 sketch: that approach destroyed ``stale-scip``'s seed and forced
    the IndexHealth probe into the ``upstream_scip_unavailable`` fallback
    instead of the load-bearing ``commits_behind`` shape.
    """
    script = fixture / "regenerate.sh"
    if not script.is_file():
        return
    result = subprocess.run(["bash", str(script)], cwd=str(fixture), capture_output=True, text=True)
    if result.returncode != 0:
        # Tolerate environment-specific failures (e.g. Docker absent on a
        # developer's box). The fixture's tracked tree + any previously
        # materialized state still let gather run; the cmd_check / harness
        # tests will catch any golden mismatch downstream. The CI Linux
        # runner has docker; this warning is the developer-box affordance.
        print(  # noqa: T201
            f"WARNING regen.materialize_failed fixture={fixture.name} "
            f"rc={result.returncode} stderr_tail={result.stderr[-200:]!r}",
            file=sys.stderr,
        )
        return
    print(  # noqa: T201 — script status output
        f"INFO regen.materialize fixture={fixture.name}", file=sys.stderr
    )


def _run_gather(fixture: Path) -> None:
    """Run ``codegenie gather <fixture>`` in-process via ``python -m``.

    Uses ``sys.executable`` so the active venv's interpreter is honoured.
    ``shell=False``; ``check=True``.
    """
    cmd = [sys.executable, "-m", "codegenie", "gather", str(fixture)]
    subprocess.run(cmd, cwd=str(_REPO_ROOT), check=True, capture_output=True)


def _load_envelope(fixture: Path) -> dict[str, JsonValue]:
    """Load ``repo-context.yaml`` for *fixture* and cast to JsonValue dict."""
    path = fixture / ".codegenie" / "context" / "repo-context.yaml"
    with path.open("r", encoding="utf-8") as fp:
        raw = yaml.safe_load(fp)
    return cast(dict[str, JsonValue], raw)


# ---------------------------------------------------------------------------
# Fixture iteration
# ---------------------------------------------------------------------------


def _discover_fixtures(portfolio_root: Path) -> list[Path]:
    """Return sorted list of fixture directories under *portfolio_root*,
    skipping ``_``-prefixed entries (AC-3, AC-40)."""
    if not portfolio_root.is_dir():
        raise FileNotFoundError(f"portfolio root not found: {portfolio_root}")
    out: list[Path] = []
    for child in sorted(portfolio_root.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("_"):
            continue
        out.append(child)
    return out


# ---------------------------------------------------------------------------
# Atomic write (AC-34)
# ---------------------------------------------------------------------------


def _atomic_write_text(path: Path, content: str) -> None:
    """Write *content* to *path* atomically: tmpfile + ``os.replace``.

    The parent dir is created if missing. A SIGINT or crash mid-write never
    leaves a partial file on disk.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fp:
            fp.write(content)
        os.replace(tmp_name, path)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


# ---------------------------------------------------------------------------
# Per-fixture sweep
# ---------------------------------------------------------------------------


def _sweep_fixture(fixture: Path) -> dict[str, str]:
    """Return ``{probe_name: canonical_json_text}`` for the cells this fixture
    should ship a golden for (per ``_UNIVERSAL_PROBES``).

    Probes that did not appear in the envelope are silently skipped (the
    fixture's probes set is a runtime fact); a probe in ``_UNIVERSAL_PROBES``
    that produced no slice in the live run raises ``AssertionError`` — the
    matrix and the runtime must agree.
    """
    envelope = _load_envelope(fixture)
    probes_obj = envelope.get("probes")
    if not isinstance(probes_obj, dict):
        raise RuntimeError(f"{fixture.name}: repo-context.yaml has no probes dict")

    out: dict[str, str] = {}
    for probe_name in sorted(_UNIVERSAL_PROBES):
        if probe_name not in probes_obj:
            raise AssertionError(
                f"{fixture.name}: probe {probe_name!r} expected in "
                f"_UNIVERSAL_PROBES but absent from live envelope. Update "
                f"_UNIVERSAL_PROBES + COUNT.txt in lock-step."
            )
        slice_value = probes_obj[probe_name]
        canon = _canonicalize(slice_value)
        canon = _sort_list_of_dicts(canon, probe_name)
        out[probe_name] = _dump_canonical_json(canon)
    return out


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------


def _portfolio_paths() -> tuple[Path, Path]:
    return _PORTFOLIO_DIR, _GOLDEN_ROOT


def _cleanup_runtime_artifacts(fixture: Path) -> None:
    """Remove ``.codegenie/`` from *fixture* after slice capture, then
    re-run ``regenerate.sh`` so any seed state (in particular
    ``stale-scip/.codegenie/context/raw/scip.json``) is restored.

    Most fixtures' shape tests treat ``.codegenie/`` as forbidden — gather
    creates it, so we erase the trace. ``stale-scip``'s shape test
    skip-lists ``.codegenie/`` because its materialized seed is expected
    on disk; we re-run ``regenerate.sh`` to put the seed back so
    downstream unit tests (e.g.,
    ``tests/unit/probes/layer_b/test_index_health_empty_registry_adversarial.py``)
    that read ``.codegenie/context/raw/scip.json`` keep passing.
    """
    ctx = fixture / ".codegenie"
    if ctx.exists():
        shutil.rmtree(ctx)
    _materialize_fixture(fixture)


def cmd_update(portfolio_root: Path, golden_root: Path) -> int:
    """Regenerate every golden under ``golden_root`` from a live gather."""
    fixtures = _discover_fixtures(portfolio_root)
    for fixture in fixtures:
        _materialize_fixture(fixture)
        _run_gather(fixture)
        slices = _sweep_fixture(fixture)
        _cleanup_runtime_artifacts(fixture)
        for probe_name, content in slices.items():
            target = golden_root / probe_name / f"{fixture.name}.json"
            _atomic_write_text(target, content)
    # Refresh COUNT.txt
    count = sum(1 for _ in golden_root.rglob("*.json"))
    _atomic_write_text(_COUNT_FILE, f"{count}\n")
    return 0


def cmd_check(portfolio_root: Path, golden_root: Path) -> int:
    """Verify every golden equals the canonicalized live output. Exit 0 on
    full match; 1 on any diff (with unified-diff stderr summary)."""
    fixtures = _discover_fixtures(portfolio_root)
    diffs: list[str] = []
    for fixture in fixtures:
        # Run the fixture's own regenerate.sh to restore deterministic
        # seed state (in particular stale-scip's materialized scip.json).
        # Idempotent for fixtures whose script only ``mkdir -p``.
        _materialize_fixture(fixture)
        _run_gather(fixture)
        slices = _sweep_fixture(fixture)
        _cleanup_runtime_artifacts(fixture)
        for probe_name, live_content in slices.items():
            target = golden_root / probe_name / f"{fixture.name}.json"
            if not target.exists():
                diffs.append(
                    f"MISSING: {target.relative_to(_REPO_ROOT)} — run "
                    f"`python scripts/regen_golden.py --update --portfolio`"
                )
                continue
            committed = target.read_text(encoding="utf-8")
            if committed != live_content:
                rel = str(target.relative_to(_REPO_ROOT))
                diff = "\n".join(
                    difflib.unified_diff(
                        committed.splitlines(),
                        live_content.splitlines(),
                        fromfile=f"{rel} (committed)",
                        tofile=f"{rel} (live)",
                        n=3,
                        lineterm="",
                    )
                )
                diffs.append(f"DIFF: {rel}\n{diff}")

    if diffs:
        print(  # noqa: T201
            "Golden mismatch (S7-03). Run "
            "`python scripts/regen_golden.py --update --portfolio` after "
            "investigating each diff:\n",
            file=sys.stderr,
        )
        for entry in diffs:
            print(entry, file=sys.stderr)  # noqa: T201
            print("---", file=sys.stderr)  # noqa: T201
        return 1
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--check",
        action="store_true",
        help="Verify goldens match live output (default; exits 1 on diff).",
    )
    mode_group.add_argument(
        "--update",
        action="store_true",
        help="Regenerate every golden from live output (Linux only).",
    )
    parser.add_argument(
        "--portfolio",
        action="store_true",
        help="Operate on the Phase-2 fixture portfolio (currently the only mode).",
    )
    parser.add_argument(
        "--portfolio-root",
        type=Path,
        default=_PORTFOLIO_DIR,
        help="Override the portfolio root (for tests; default %(default)s).",
    )
    parser.add_argument(
        "--golden-root",
        type=Path,
        default=_GOLDEN_ROOT,
        help="Override the golden root (for tests; default %(default)s).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.portfolio:
        print(  # noqa: T201
            "ERROR: --portfolio is required (S7-03 ships only the portfolio mode).",
            file=sys.stderr,
        )
        return 2

    if args.update and sys.platform != "linux":
        # AC-16: error-out on non-Linux if the matrix includes any
        # platform-sensitive probe (runtime_trace, sbom, cve, scip_index,
        # tree_sitter_import_graph). With the current matrix the regen is
        # platform-agnostic — emit a warning and continue. Adding a
        # platform-sensitive probe to ``_UNIVERSAL_PROBES`` re-tightens
        # this gate.
        platform_risk = _UNIVERSAL_PROBES & _PLATFORM_SENSITIVE_PROBES
        if platform_risk:
            print(  # noqa: T201
                f"ERROR: regen_golden.py --update --portfolio requires "
                f"Linux (CI: ubuntu-24.04). Matrix includes "
                f"platform-sensitive probes: {sorted(platform_risk)}. "
                f"Run on a Linux box or via the CI runner.",
                file=sys.stderr,
            )
            return 2
        print(  # noqa: T201
            f"WARNING: regenerating goldens on {sys.platform!r}; current "
            f"matrix is platform-agnostic so this is safe. Adding any of "
            f"{sorted(_PLATFORM_SENSITIVE_PROBES)} to _UNIVERSAL_PROBES "
            f"will require Linux regen.",
            file=sys.stderr,
        )

    if args.update:
        return cmd_update(args.portfolio_root, args.golden_root)
    return cmd_check(args.portfolio_root, args.golden_root)


if __name__ == "__main__":
    raise SystemExit(main())
