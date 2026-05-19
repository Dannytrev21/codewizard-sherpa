# Story S11-03 — `codegenie list-coordination-candidates` CLI subcommand

**Step:** Step 11 — `Both` variant emission + `coordination-summary.yaml` writer + `codegenie list-coordination-candidates` CLI
**Status:** Ready
**Effort:** S
**Depends on:** S11-02 (the writer that puts events into the spanning log this CLI reads + the `coordination-summary.yaml` shape this CLI can cross-reference)
**ADRs honored:** Phase 7 ADR-0001 §Consequences (`codegenie list-coordination-candidates` ships as a tiny operator-facing CLI subcommand — the pre-Phase-8 visibility surface), Phase 7 ADR-0017 §Consequences (`--format yaml|table|json`; default YAML per Open Question §2), production ADR-0034 (spanning log is the source-of-truth; CLI is a read-only projector)

## Context

Per ADR-0001, the `Both`-variant event accumulates unread in `.codegenie/events/spanning/*.jsonl.zst` for ~3 months until Phase 8 lands. Operators running `codegenie remediate <repo> --cve <id>` see exit code 8 (S11-04) and need a way to enumerate pending coordination events without grepping zstd-compressed JSONL by hand. This story ships exactly that: a thin read-only CLI subcommand that walks the spanning-log directory, filters on `kind == "requires_multi_plugin_coordination"`, optionally filters by `--since DATE`, and renders YAML (default) / table / JSON.

The CLI is **not a Phase 8 fragment**. It is operator-facing UX; it does not project state, does not deduplicate by workflow, does not group, does not annotate with Phase 8 routing decisions (because Phase 8 doesn't exist yet). Phase 8's Planner is the canonical projector per ADR-0042; this CLI is the pre-Phase-8 visibility band-aid that ADR-0017 §Consequences explicitly carves out.

Open Question §2 (pinned here per the manifest) sets the **default format to YAML** — the rationale: pipe-friendly (operators commonly chain `codegenie list-coordination-candidates | yq '.[] | select(.cve_id == "CVE-2026-0001")'`), and operator-readable without parsing. `--format table` is for at-a-glance terminal viewing; `--format json` is for machine consumers that prefer JSON. The format flag is the only meaningful operator knob besides `--since`.

The `--since DATE` filter accepts ISO-8601 dates (`2026-05-01`) or datetimes (`2026-05-19T00:00:00+00:00`). Events with `emitted_at < since` are skipped. Default (no `--since`) yields all events.

Subtle correctness risks the story explicitly defends against: (1) **malformed JSONL lines** — the spanning log is append-only across multiple processes (Phase 6 / 6.5 invariant); a partial write at the end of a file may produce an unparsable last line. The CLI skips unparsable lines with a stderr warning (one-line-per-bad-line) and continues — failing loudly on corruption while remaining useful. (2) **Files that are not zstd-compressed** — if a future Phase 9 change adds plain `.jsonl` files alongside `.jsonl.zst`, the CLI globs both extensions defensively. (3) **Schema-version forward-compat** — the CLI filters on `kind == "requires_multi_plugin_coordination"` regardless of `schema_version`; if Phase 8 lands `"phase-8-0"` events, they appear in the listing. The output renders only the fields the CLI knows about (those of S11-01); unknown fields are dropped from the rendered output (with a stderr warning at the file level). Phase 8 will replace this CLI; this is a 3-month interim.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §14` (lines 950–954) — public interface, internal structure ("Walks `.codegenie/events/spanning/*.jsonl.zst`, filters on `kind == "requires_multi_plugin_coordination"`, formats. Tiny script — not a Phase 8 fragment.").
  - `../phase-arch-design.md §Scenario C` (line 486) — explicit "Phase 7 ships the operator-side `codegenie list-coordination-candidates` subcommand … so operators can see pending `Both` events accumulate."
- **Phase ADRs:**
  - `../ADRs/0001-no-multi-plugin-coordinator-in-phase-7.md §Consequences` — names the CLI subcommand explicitly + the `_index.tsv` rollup as complementary surfaces.
  - `../ADRs/0017-both-provenance-exits-code-8-with-coordination-summary.md §Decision (closing paragraph)` — `[--since DATE] [--format yaml|table]` interface; default `--format=yaml` for parseability; `--format=table` for at-a-glance. This story extends with `json` per Step 11's High-level-impl line 325.
- **Production ADRs:**
  - `../../../production/adrs/0034-event-sourcing-canonical-primitive.md` — the spanning log is the source-of-truth; this CLI does NOT mutate.
- **Existing code:**
  - `src/codegenie/cli/__init__.py` — existing CLI surface (`codegenie gather`, `codegenie audit verify`, `codegenie vuln-index refresh`). Pattern for adding a new subcommand: register an `argparse` subparser + dispatch to a module-level `run(args) -> int`.
  - `src/codegenie/primitives/vuln_provenance/events.py` (S11-01) — `RequiresMultiPluginCoordination` typed event; the CLI deserializes JSONL lines through this Pydantic model.

## Goal

Land `src/codegenie/cli/list_coordination_candidates.py` with a `codegenie list-coordination-candidates [--since DATE] [--format yaml|table|json]` subcommand that walks `.codegenie/events/spanning/*.jsonl.zst` (and `.jsonl` plaintext as a defensive fallback), zstd-decompresses each file line-by-line, JSON-parses each line, filters on `kind == "requires_multi_plugin_coordination"` AND `emitted_at >= --since` (if provided), validates through `RequiresMultiPluginCoordination`, and prints the resulting list in the requested format (YAML default). Wires into the main `argparse` dispatcher.

## Acceptance criteria

- [ ] **AC-1** `src/codegenie/cli/list_coordination_candidates.py` exists and exports `add_subparser(subparsers) -> None` and `run(args: argparse.Namespace) -> int`.
- [ ] **AC-2** The main CLI dispatcher (`src/codegenie/cli/__init__.py` or `src/codegenie/__main__.py` — match existing precedent) wires the new subcommand. Running `python -m codegenie list-coordination-candidates --help` prints the usage with the three flags (`--since`, `--format`, `--codegenie-root`).
- [ ] **AC-3 — Flag set + defaults.**
  - `--since DATE` — optional; ISO-8601 date or datetime; events with `emitted_at < since` are dropped.
  - `--format {yaml,table,json}` — optional; defaults to `yaml`.
  - `--codegenie-root PATH` — optional; defaults to `./.codegenie` resolved against `cwd()`; locates the spanning-log directory at `<root>/events/spanning/`.
- [ ] **AC-4 — Reads `.jsonl.zst` files.** The CLI globs `<root>/events/spanning/*.jsonl.zst`, opens each with `zstandard.ZstdDecompressor()`, splits on `\n`, parses each non-empty line as JSON.
- [ ] **AC-5 — Defensive fallback for plain `.jsonl`.** The CLI also globs `<root>/events/spanning/*.jsonl` (plaintext) and reads them directly. Files in both globs are deduplicated by absolute path before processing.
- [ ] **AC-6 — Filter by kind.** Only events with `kind == "requires_multi_plugin_coordination"` are retained.
- [ ] **AC-7 — Filter by `--since`.** When `--since` is provided, events with `emitted_at < since` are dropped. `--since 2026-05-01` parses to `2026-05-01T00:00:00+00:00`; `--since 2026-05-19T12:00:00+00:00` parses as-is. Naive datetimes in `--since` are rejected with `argparse.ArgumentTypeError`.
- [ ] **AC-8 — Pydantic validation per event.** Each filtered line is `RequiresMultiPluginCoordination.model_validate_json(line)`. `ValidationError` on a single line emits a one-line stderr warning (`warning: skipping malformed event at <file>:<lineno>: <err>`) and the line is skipped. Other lines in the same file are still processed.
- [ ] **AC-9 — Sorted output.** Events are sorted by `emitted_at` ascending, then by `workflow_id` ascending (stable tiebreaker).
- [ ] **AC-10 — `--format yaml` output.** Default. Emits a YAML list of dicts via `yaml.safe_dump([e.model_dump(mode="json") for e in events], sort_keys=False)`. Empty result emits `[]\n`.
- [ ] **AC-11 — `--format json` output.** Emits a JSON array via `json.dumps([e.model_dump(mode="json") for e in events], indent=2, default=str)` followed by a trailing newline. Empty result emits `[]\n`.
- [ ] **AC-12 — `--format table` output.** Emits a fixed-column header `emitted_at\tworkflow_id\tcve_id\tapp_kind\tbase_kind\tsummary_path` followed by one tab-separated row per event. (`cve_id` and `app_kind` are derived from `app_record`; `base_kind` from `base_record`.) Empty result emits the header only.
- [ ] **AC-13 — Exit code 0 on success, 1 on unrecoverable error.** Unrecoverable means: spanning-log directory does not exist (the CLI emits `warning: no spanning log directory at <path>` to stderr and exits **0** with an empty result — operator UX preserves the "no pending events" reading). Exit 1 is reserved for argument-parse errors and unhandled exceptions.
- [ ] **AC-14 — Unknown / forward-compat schema versions.** Events with `schema_version != "phase-7-0"` parse through `RequiresMultiPluginCoordination` (which has `Literal["phase-7-0"]`); the resulting `ValidationError` triggers AC-8 skip-with-warning. This is the intended forward-compat behavior — Phase 8 will land its own CLI / projector.
- [ ] **AC-15 — `--help` documents exit code 8 + cross-references the YAML at `.codegenie/coordination/<workflow_id>.yaml`.** The help epilog names: "These events are produced when `codegenie remediate` exits with code 8 (REQUIRES_MULTI_PLUGIN_COORDINATION). The per-workflow operator-readable summary is at `.codegenie/coordination/<workflow_id>.yaml`."
- [ ] **AC-16 — `mypy --strict src/codegenie/cli/list_coordination_candidates.py` clean.**
- [ ] **AC-17 — `ruff check` + `ruff format --check` clean.**
- [ ] **AC-18 — `make lint-imports` green** — the CLI may import from `codegenie.primitives.vuln_provenance.events` (the typed event class); may NOT import from `plugins/`.
- [ ] **AC-19 — TDD plan's red test (`test_list_coordination_candidates.py::test_filter_and_format_yaml`) exists, was committed in a failing state, is now green.**

## Implementation outline

1. Create `src/codegenie/cli/list_coordination_candidates.py`. Module docstring names ADR-0001 §Consequences + ADR-0017 + the "tiny script, not a Phase 8 fragment" disclaimer.
2. Define `add_subparser(subparsers) -> None`:
   ```python
   def add_subparser(subparsers) -> None:
       p = subparsers.add_parser(
           "list-coordination-candidates",
           help="List pending Both-variant coordination events from the spanning log.",
           epilog="Exit code 8 (REQUIRES_MULTI_PLUGIN_COORDINATION) ... <see AC-15>",
       )
       p.add_argument("--since", type=_parse_since, default=None,
                      help="ISO-8601 date or datetime; only events at-or-after are listed.")
       p.add_argument("--format", choices=("yaml", "table", "json"), default="yaml",
                      help="Output format. Default: yaml.")
       p.add_argument("--codegenie-root", type=Path, default=Path(".codegenie"),
                      help="Root containing events/spanning/ and coordination/.")
       p.set_defaults(_handler=run)
   ```
3. `_parse_since(s: str) -> datetime` — accept `YYYY-MM-DD` (defaults to UTC midnight) or full ISO-8601 (must be tz-aware); raise `argparse.ArgumentTypeError` on naive datetimes.
4. `run(args) -> int`:
   - `spanning_dir = args.codegenie_root / "events" / "spanning"`.
   - If not `spanning_dir.is_dir()`: stderr warning + return 0 + emit empty per `--format`.
   - Collect events via `_iter_events(spanning_dir, args.since)` (a generator that handles both `.jsonl.zst` and `.jsonl`, skips malformed lines with stderr warnings).
   - Sort by `(emitted_at, workflow_id)`.
   - Dispatch to `_render_yaml` / `_render_table` / `_render_json` per `args.format`.
   - Return 0.
5. `_iter_events(spanning_dir, since)` — globs both extensions, dedups by absolute path, decompresses (`.jsonl.zst`) or reads plaintext (`.jsonl`), splits on newlines, JSON-parses each line, filters on `kind`, validates through `RequiresMultiPluginCoordination`, applies `--since`.
6. `_render_yaml(events)` / `_render_json(events)` / `_render_table(events)` — pure functions; print to stdout; return None.
7. Wire `add_subparser` into the main CLI in `src/codegenie/cli/__init__.py` (or wherever `gather` and `audit verify` are wired — read the file first to match the convention).
8. Add `zstandard` to runtime deps if not already present (`grep zstandard pyproject.toml`). It probably is — `.jsonl.zst` is a Phase 6 / 6.5 format.
9. Tests under `tests/unit/cli/`:
   - `test_list_coordination_candidates.py` — covers AC-3..AC-14.
   - Use `tmp_path` fixture; hand-write a small `.jsonl.zst` file with two events (one matching, one off-kind); assert filtering, format outputs, malformed-line skip, `--since` filter.
10. Run `mypy --strict src/codegenie/cli/list_coordination_candidates.py` + `pytest tests/unit/cli/test_list_coordination_candidates.py -v`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/cli/test_list_coordination_candidates.py`

```python
from __future__ import annotations

import io
import json
import zstandard as zstd
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from codegenie.cli.list_coordination_candidates import run as list_run, add_subparser
from codegenie.primitives.vuln_provenance.events import RequiresMultiPluginCoordination


def _write_zst(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = ("\n".join(lines) + "\n").encode()
    path.write_bytes(zstd.ZstdCompressor().compress(blob))


def _make_event_json(workflow_id: str, cve: str = "CVE-2026-0001", iso: str = "2026-05-19T00:00:00+00:00") -> str:
    return json.dumps({
        "kind": "requires_multi_plugin_coordination",
        "schema_version": "phase-7-0",
        "workflow_id": workflow_id,
        "app_record": {"kind": "app_direct", "cve_id": cve, "package_id": "express@4.17.0"},
        "base_record": {"kind": "base_image", "image_digest": "sha256:" + "a"*64,
                        "layer_digest": "sha256:" + "b"*64, "distro_pkg": {...}, "stage": "runtime"},
        "summary_path": f"/codegenie/coordination/{workflow_id}.yaml",
        "emitted_at": iso,
    })


def test_filter_and_format_yaml(tmp_path, capsys):
    """AC-6 + AC-10 — kind-filtered events render as YAML list."""
    spanning = tmp_path / ".codegenie" / "events" / "spanning"
    _write_zst(spanning / "events-1.jsonl.zst", [
        _make_event_json("wf-1"),
        json.dumps({"kind": "other_event", "data": "x"}),  # filtered out by kind
        _make_event_json("wf-2"),
    ])
    rc = list_run(_args(tmp_path, format="yaml"))
    assert rc == 0
    out = capsys.readouterr().out
    parsed = yaml.safe_load(out)
    assert isinstance(parsed, list)
    assert {e["workflow_id"] for e in parsed} == {"wf-1", "wf-2"}


def test_since_filter(tmp_path, capsys):
    """AC-7 — --since drops earlier events."""
    spanning = tmp_path / ".codegenie" / "events" / "spanning"
    _write_zst(spanning / "events-1.jsonl.zst", [
        _make_event_json("wf-old", iso="2026-04-01T00:00:00+00:00"),
        _make_event_json("wf-new", iso="2026-05-19T00:00:00+00:00"),
    ])
    rc = list_run(_args(tmp_path, since=datetime(2026, 5, 1, tzinfo=timezone.utc)))
    assert rc == 0
    out = capsys.readouterr().out
    parsed = yaml.safe_load(out)
    assert {e["workflow_id"] for e in parsed} == {"wf-new"}


def test_malformed_line_skipped_with_stderr_warning(tmp_path, capsys):
    """AC-8 — bad line skipped; warning emitted; good lines still output."""
    spanning = tmp_path / ".codegenie" / "events" / "spanning"
    _write_zst(spanning / "events-1.jsonl.zst", [
        _make_event_json("wf-1"),
        "{not valid json",
        _make_event_json("wf-2"),
    ])
    rc = list_run(_args(tmp_path))
    assert rc == 0
    captured = capsys.readouterr()
    assert "warning:" in captured.err
    parsed = yaml.safe_load(captured.out)
    assert {e["workflow_id"] for e in parsed} == {"wf-1", "wf-2"}


def test_format_table(tmp_path, capsys):
    """AC-12 — table format with header + tab-separated rows."""
    spanning = tmp_path / ".codegenie" / "events" / "spanning"
    _write_zst(spanning / "events-1.jsonl.zst", [_make_event_json("wf-1")])
    rc = list_run(_args(tmp_path, format="table"))
    assert rc == 0
    out = capsys.readouterr().out
    lines = out.strip().split("\n")
    assert lines[0].split("\t") == [
        "emitted_at", "workflow_id", "cve_id", "app_kind", "base_kind", "summary_path",
    ]
    assert "wf-1" in lines[1]


def test_format_json(tmp_path, capsys):
    """AC-11 — JSON array output."""
    spanning = tmp_path / ".codegenie" / "events" / "spanning"
    _write_zst(spanning / "events-1.jsonl.zst", [_make_event_json("wf-1")])
    rc = list_run(_args(tmp_path, format="json"))
    out = capsys.readouterr().out
    assert json.loads(out) and isinstance(json.loads(out), list)


def test_missing_spanning_dir_exits_zero_with_empty(tmp_path, capsys):
    """AC-13 — no directory → exit 0, empty output, stderr warning."""
    rc = list_run(_args(tmp_path))
    assert rc == 0
    captured = capsys.readouterr()
    assert "warning:" in captured.err
    assert yaml.safe_load(captured.out) == []


def test_sort_order(tmp_path, capsys):
    """AC-9 — events sorted by (emitted_at, workflow_id)."""
    spanning = tmp_path / ".codegenie" / "events" / "spanning"
    _write_zst(spanning / "events-1.jsonl.zst", [
        _make_event_json("wf-b", iso="2026-05-19T00:00:00+00:00"),
        _make_event_json("wf-a", iso="2026-05-18T00:00:00+00:00"),
    ])
    rc = list_run(_args(tmp_path))
    parsed = yaml.safe_load(capsys.readouterr().out)
    assert [e["workflow_id"] for e in parsed] == ["wf-a", "wf-b"]
```

`_args(tmp_path, format="yaml", since=None)` builds an `argparse.Namespace` carrying `codegenie_root = tmp_path / ".codegenie"`, `format`, `since`.

State why the red tests fail: `ModuleNotFoundError: codegenie.cli.list_coordination_candidates` — module + subcommand do not exist.

### Green — minimal pass

Implement per the outline. Use `zstandard.ZstdDecompressor()` for `.jsonl.zst` reads; `Path.read_text()` for `.jsonl`. Use `yaml.safe_dump(..., sort_keys=False)` for YAML; `json.dumps(..., indent=2, default=str)` for JSON.

### Refactor

- Pull `_render_yaml` / `_render_json` / `_render_table` into pure helpers; pass `events: list[RequiresMultiPluginCoordination]` only.
- Add `--help` epilog naming the exit code 8 + the per-workflow YAML location (AC-15).
- Verify `mypy --strict` clean.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/cli/list_coordination_candidates.py` | NEW — subcommand module: `add_subparser` + `run` + three render helpers. |
| `src/codegenie/cli/__init__.py` (or `__main__.py` — match existing wiring) | EDIT (additive) — register the new subparser. |
| `tests/unit/cli/test_list_coordination_candidates.py` | NEW — covers AC-3..AC-14. |
| `pyproject.toml` | EDIT (only if `zstandard` is not already a runtime dep). |

## Out of scope

- **Mutating the spanning log** — read-only by design per ADR-0034.
- **Aggregating events by workflow_id** — operator-side concern, achievable with `yq` / `jq`. Phase 8's projector will do canonical aggregation.
- **`--watch` / polling mode** — not in ADR-0017's interface; if operators want continuous watch, they can wrap the command in `watch -n 60`.
- **Pretty-printing the `app_record` / `base_record` discriminated unions** — the CLI dumps the JSON-serialized form. Phase 13.5's operator portal handles richer rendering.
- **Filtering by `cve_id` or `workflow_id`** — operator-side concern, achievable with `yq '.[] | select(.cve_id == "...")'`. Adding more flags inflates surface area for a 3-month-interim tool.
- **Schema-version upgrade handling** — when Phase 8 lands `"phase-8-0"`, Phase 8 ships its own CLI (or upgrades this one). For now, `phase-8-0` events are skipped-with-warning per AC-14.

## Notes for the implementer

- **Match the existing CLI wiring convention.** Before editing `src/codegenie/cli/__init__.py`, read it: the project may use `argparse` directly, or `click`, or a custom dispatcher. The existing `codegenie gather`, `codegenie audit verify`, `codegenie vuln-index refresh` subcommands establish the pattern (CLAUDE.md Rule 11). Mirror it; do not invent.
- **Default `--format yaml` per Open Question §2.** The manifest pins this as YAML; ADR-0017 §Decision (closing paragraph) names it for parseability. Resist any urge to default to `table` for "operator friendliness" — pipe-chaining (`codegenie list-coordination-candidates | yq ...`) is the dominant use case in the 3-month-interim. `--format table` exists for ad-hoc terminal viewing; operators learn to type it.
- **`--since` naive-datetime rejection.** Per the same discipline as S11-01 + S11-02. If an operator types `--since 2026-05-19T12:00:00` (no `+00:00`), the CLI errors out at argparse time with a useful message: "`--since` requires a timezone-aware ISO-8601 datetime (e.g., `2026-05-19T00:00:00+00:00`) or a date (e.g., `2026-05-19`, interpreted as UTC midnight)." Date-only is the operator-friendly form; full ISO-8601 is the precision form.
- **`.jsonl.zst` is the established Phase 6 / 6.5 format.** `grep -rn "jsonl.zst\|ZstdCompressor" src/codegenie/` before deciding on the codec. If Phase 6 / 6.5 uses framed zstd (multiple frames per file), the decompressor needs `stream_reader`; if it uses single-frame, plain `decompress()` works. Match whatever Phase 6 / 6.5 produces — read the producer code before writing the consumer.
- **Malformed-line tolerance is deliberate.** The spanning log is append-only across processes; a partial write on a SIGKILL'd process produces a truncated last line. The CLI is operator-facing and must not crash on a single bad line — it warns to stderr and continues. The "fail loud" Rule 12 is satisfied by the stderr warning (operators see corruption), not by aborting the listing.
- **Exit code 0 when the spanning-log directory is missing.** Operator UX: a fresh repo with no `Both` events yet should print `[]\n` and exit 0, not "error: no spanning log." The stderr warning preserves the visibility into the missing directory; the exit code preserves the "no pending events" reading for downstream automation. This is distinct from exit code 8 (S11-04), which is the orchestrator's exit code when a `Both` was just emitted — different code path entirely.
- **Forward-compat schema version handling.** When Phase 8 ships and writes `schema_version="phase-8-0"` events, this CLI's `RequiresMultiPluginCoordination.model_validate_json(...)` raises `ValidationError` (because the Literal is `"phase-7-0"`). The line is skipped-with-warning. Operators see the warning and know the CLI is out of date — they upgrade. Phase 8's CLI replaces this one. The 3-month interim does not need to handle two schema versions gracefully; Phase 8 ships a real solution.
- **Closest precedent.** `src/codegenie/cli/` existing subcommands (`gather`, `audit verify`, `vuln-index refresh`). Mirror their `add_subparser` + `run` shape, their argparse idioms, their exit-code conventions, and their test layout under `tests/unit/cli/`.
- **AC-15 cross-references operator docs.** The `--help` epilog naming exit code 8 + the per-workflow YAML location is the operator's discovery path: they run `codegenie remediate`, get exit 8, look at `codegenie remediate --help` (S11-04 docs exit 8 there), then run `codegenie list-coordination-candidates`. The cross-reference loops the UX. Test that the epilog text is present (`"exit code 8" in p.epilog or in the rendered --help output`).
