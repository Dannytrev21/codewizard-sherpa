"""Fence: enforce doc-and-code consistency invariants.

Mirrors :mod:`tests.unit.test_pyproject_fence` in spirit — these tests catch
silent drift between three sources of truth that humans must keep aligned by
hand: ``docs/roadmap.md``'s phase-summary table, ``docs/index.md``'s status
table, the ``docs/phases/NN-<slug>/`` artifact folders, and the explicit
probe-collection list in ``src/codegenie/probes/__init__.py``.

Each invariant is one test function whose ``AssertionError`` names the
offending file, the offending text, and a one-sentence fix instruction.

Run-time is pure file-IO + regex; no subprocess, no network.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
ROADMAP_PATH: Final[Path] = REPO_ROOT / "docs" / "roadmap.md"
INDEX_PATH: Final[Path] = REPO_ROOT / "docs" / "index.md"
PHASES_DIR: Final[Path] = REPO_ROOT / "docs" / "phases"
PROBES_INIT_PATH: Final[Path] = REPO_ROOT / "src" / "codegenie" / "probes" / "__init__.py"
PROBES_DIR: Final[Path] = REPO_ROOT / "src" / "codegenie" / "probes"

# Phase-summary table row shape, e.g.:
#   | 3 | **Vuln remediation ...** | vuln | ... | ✅ [03-vuln-...](phases/03-vuln-...) |
# We pin to the Design column being the last `|`-delimited cell on the line.
_ROADMAP_ROW_RE: Final[re.Pattern[str]] = re.compile(
    r"^\|\s*(?P<num>[0-9]+(?:\.[0-9]+)?)\s*\|"  # phase number
    r"(?P<rest>.*)\|\s*(?P<design>[^|]*?)\s*\|\s*$"
)

# A ✅-marked Design cell embeds a folder link of shape:
#   ✅ [NN-<slug>](phases/NN-<slug>/)
_DESIGN_LINK_RE: Final[re.Pattern[str]] = re.compile(
    r"✅\s*\[(?P<slug>[^\]]+)\]\(phases/(?P<folder>[^)\s]+?)/?\)"
)

# A "pending" Design cell wraps the reason in italics, e.g.:
#   *(pending plugin-architecture redesign)*
#   *(pending Phase 7 redesign)*
_PENDING_RE: Final[re.Pattern[str]] = re.compile(
    r"\*\(pending [^)]*redesign\)\*", flags=re.IGNORECASE
)

# Required artifacts for a phase whose Design column shows ✅.
_REQUIRED_DESIGN_ARTIFACTS: Final[tuple[str, ...]] = ("final-design.md",)

# The full design-pipeline contract — if a "pending redesign" phase folder
# contains ALL of these, the roadmap is lying.
_FULL_PIPELINE_ARTIFACTS: Final[tuple[str, ...]] = (
    "final-design.md",
    "phase-arch-design.md",
    "High-level-impl.md",
)
_FULL_PIPELINE_DIRS: Final[tuple[str, ...]] = ("ADRs",)

# Canonical eval metric per Phase 6.5 ADR-0002 (departure from `mean`).
_BANNED_METRIC: Final[str] = "bench_score.mean"
_BANNED_METRIC_TARGETS: Final[tuple[Path, ...]] = (
    ROADMAP_PATH,
    PHASES_DIR / "06.5-per-task-class-eval-harness" / "final-design.md",
)

# Contradiction strings that must NOT appear next to a roadmap-✅ phase
# in docs/index.md's status table.
_INDEX_CONTRADICTION_PHRASES: Final[tuple[str, ...]] = (
    "awaiting redesign",
    "📋 Planned",
)

# index.md row shape (status table). The status cell is the second `|` cell.
_INDEX_ROW_RE: Final[re.Pattern[str]] = re.compile(
    r"^\|\s*(?P<label>[^|]+?)\s*\|\s*(?P<status>[^|]+?)\s*\|\s*$"
)

# A "Phase N" or "Phases N, M" or "Phases N–M" reference inside an index
# status-table row label.
_INDEX_PHASE_REF_RE: Final[re.Pattern[str]] = re.compile(r"Phase[s]?\s+([0-9.,\s–\-]+?)\s*(?:—|$)")


# ---------- helpers ----------


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _roadmap_rows() -> list[tuple[str, str]]:
    """Return [(phase_number, design_cell_text), ...] for every table row."""
    rows: list[tuple[str, str]] = []
    for line in _read(ROADMAP_PATH).splitlines():
        m = _ROADMAP_ROW_RE.match(line)
        if not m:
            continue
        num = m.group("num").strip()
        design = m.group("design").strip()
        rows.append((num, design))
    return rows


def _index_status_rows() -> list[tuple[str, str]]:
    """Return [(label_cell, status_cell), ...] from docs/index.md status table."""
    rows: list[tuple[str, str]] = []
    for line in _read(INDEX_PATH).splitlines():
        m = _INDEX_ROW_RE.match(line)
        if not m:
            continue
        label = m.group("label").strip()
        status = m.group("status").strip()
        # Filter header / separator rows.
        if label in {"What", "---"} or set(label) <= {"-", " "}:
            continue
        rows.append((label, status))
    return rows


def _expand_phase_refs(label: str) -> set[str]:
    """Best-effort extraction of phase numbers referenced in an index label.

    "Phase 0 — ..." → {"0"}
    "Phases 3–5, 6.5 — ..." → {"3", "4", "5", "6.5"}
    "Phases 8–16 — ..." → {"8", "9", ..., "16"}
    Unrecognized → empty set (the test is conservative; misses don't false-fire).
    """
    m = _INDEX_PHASE_REF_RE.search(label)
    if not m:
        return set()
    blob = m.group(1)
    out: set[str] = set()
    for chunk in blob.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "–" in chunk or "-" in chunk:
            sep = "–" if "–" in chunk else "-"
            lo_s, hi_s = (s.strip() for s in chunk.split(sep, 1))
            # Only expand pure-integer ranges; fractional phases are listed
            # individually in the index.
            if lo_s.isdigit() and hi_s.isdigit():
                for n in range(int(lo_s), int(hi_s) + 1):
                    out.add(str(n))
            else:
                out.add(lo_s)
                out.add(hi_s)
        else:
            out.add(chunk)
    return out


def _phase_register_probe_modules() -> dict[str, set[str]]:
    """For each layer directory, return {layer_name: {module_basename, ...}}
    where the module's source file contains an ``@register_probe`` line."""
    out: dict[str, set[str]] = {}
    for layer_dir in PROBES_DIR.glob("layer_*"):
        if not layer_dir.is_dir():
            continue
        mods: set[str] = set()
        for py in layer_dir.glob("*.py"):
            if py.name.startswith("_") or py.name == "__init__.py":
                continue
            if "@register_probe" in py.read_text(encoding="utf-8"):
                mods.add(py.stem)
        if mods:
            out[layer_dir.name] = mods
    return out


def _imports_in_layer_block(layer_name: str) -> set[str]:
    """Parse ``src/codegenie/probes/__init__.py`` for the imports inside the
    ``from codegenie.probes.<layer_name> import (...)`` block."""
    text = _read(PROBES_INIT_PATH)
    pat = re.compile(
        rf"from codegenie\.probes\.{re.escape(layer_name)} import \((?P<body>.*?)\)",
        flags=re.DOTALL,
    )
    m = pat.search(text)
    if not m:
        return set()
    body = m.group("body")
    # Each entry is "<name>,  # noqa: F401 — <reason>\n    " — the next entry
    # follows the newline. Strip comments first so commas split cleanly.
    decommented = re.sub(r"#[^\n]*", "", body)
    names: set[str] = set()
    for raw in decommented.split(","):
        token = raw.strip()
        if token and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token):
            names.add(token)
    return names


# ---------- Invariant 1: ✅ roadmap row points to a real folder w/ final-design.md ----------


def test_roadmap_checkmark_rows_have_folder_and_final_design() -> None:
    rows = _roadmap_rows()
    assert rows, (
        f"Could not parse any rows out of {ROADMAP_PATH} — the phase-summary "
        f"table format changed. Update _ROADMAP_ROW_RE in this file."
    )
    failures: list[str] = []
    for phase_num, design_cell in rows:
        m = _DESIGN_LINK_RE.search(design_cell)
        if not m:
            continue  # Not a ✅ row.
        folder = m.group("folder")
        folder_path = PHASES_DIR / folder
        if not folder_path.is_dir():
            failures.append(
                f"  Phase {phase_num}: roadmap.md links to phases/{folder}/ "
                f"but {folder_path} does not exist."
            )
            continue
        for artifact in _REQUIRED_DESIGN_ARTIFACTS:
            if not (folder_path / artifact).is_file():
                failures.append(
                    f"  Phase {phase_num} ({folder}): missing {artifact}. "
                    f"Either ship the design or remove the ✅ from roadmap.md."
                )
    assert not failures, (
        "roadmap.md ✅ rows lie about phase artifacts (Invariant 1):\n" + "\n".join(failures)
    )


# ---------- Invariant 2: "pending redesign" rows MUST NOT have a complete pipeline ----------


def test_pending_redesign_rows_do_not_have_complete_design_pipeline() -> None:
    rows = _roadmap_rows()
    failures: list[str] = []
    for phase_num, design_cell in rows:
        if not _PENDING_RE.search(design_cell):
            continue
        # The folder may exist as an archive; we only fail if the FULL
        # pipeline is present (which would mean the row is misleading).
        for entry in PHASES_DIR.iterdir():
            if not entry.is_dir():
                continue
            # Match by phase-number prefix (e.g. "07-" or "7-" or "06.5-").
            stem = entry.name.split("-", 1)[0]
            if stem != phase_num and stem.lstrip("0") != phase_num:
                continue
            has_all_files = all((entry / f).is_file() for f in _FULL_PIPELINE_ARTIFACTS)
            has_all_dirs = all((entry / d).is_dir() for d in _FULL_PIPELINE_DIRS)
            if has_all_files and has_all_dirs:
                failures.append(
                    f"  Phase {phase_num} ({entry.name}): roadmap.md marks "
                    f"this phase as 'pending redesign' but the folder contains "
                    f"the full design pipeline "
                    f"({', '.join(_FULL_PIPELINE_ARTIFACTS)} + ADRs/). "
                    f"Either flip the Design cell to ✅ or remove the stale "
                    f"artifacts."
                )
    assert not failures, (
        "roadmap.md 'pending redesign' rows contradict on-disk artifacts "
        "(Invariant 2):\n" + "\n".join(failures)
    )


# ---------- Invariant 3: roadmap ✅ vs docs/index.md status disagreement ----------


def test_index_md_does_not_contradict_roadmap_checkmark() -> None:
    rows = _roadmap_rows()
    checkmark_phases: set[str] = {num for num, design in rows if _DESIGN_LINK_RE.search(design)}
    assert checkmark_phases, (
        f"Sanity: no ✅ rows parsed out of {ROADMAP_PATH} — parser likely broken."
    )
    failures: list[str] = []
    for label, status in _index_status_rows():
        refs = _expand_phase_refs(label)
        if not refs:
            continue
        contradicted = refs & checkmark_phases
        if not contradicted:
            continue
        for phrase in _INDEX_CONTRADICTION_PHRASES:
            if phrase.lower() in status.lower() or phrase in status:
                failures.append(
                    f"  index.md row '{label}' has status '{status}' but "
                    f"roadmap.md marks phase(s) "
                    f"{sorted(contradicted)} as ✅. "
                    f"Update docs/index.md to reflect that the design has shipped."
                )
                break
    assert not failures, (
        "docs/index.md contradicts roadmap.md's ✅ status (Invariant 3):\n" + "\n".join(failures)
    )


# ---------- Invariant 4: canonical eval-metric string ----------


def test_bench_score_mean_is_not_used_as_promotion_threshold() -> None:
    failures: list[str] = []
    for path in _BANNED_METRIC_TARGETS:
        text = _read(path)
        # Walk line-by-line so the error names the offending line.
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _BANNED_METRIC in line:
                failures.append(
                    f"  {path}:{lineno}: contains '{_BANNED_METRIC}'. "
                    f"Phase 6.5 ADR-0002 made 'bench_score.lower_bound_95' the "
                    f"canonical promotion threshold; replace it."
                )
    assert not failures, (
        f"'{_BANNED_METRIC}' must not appear in canonical design docs "
        "(Invariant 4):\n" + "\n".join(failures)
    )


# ---------- Invariant 5: every @register_probe module is imported in probes/__init__.py ----------


def test_every_registered_probe_module_is_imported_in_probes_init() -> None:
    by_layer = _phase_register_probe_modules()
    assert by_layer, (
        f"Sanity: no @register_probe modules found under {PROBES_DIR}. Did the layout change?"
    )
    failures: list[str] = []
    for layer_name, modules in by_layer.items():
        imported = _imports_in_layer_block(layer_name)
        if not imported:
            failures.append(
                f"  {PROBES_INIT_PATH}: no `from codegenie.probes.{layer_name} "
                f"import (...)` block found, but {layer_name}/ contains "
                f"@register_probe modules {sorted(modules)}. "
                f"Add the import block."
            )
            continue
        missing = modules - imported
        for mod in sorted(missing):
            failures.append(
                f"  {PROBES_INIT_PATH}: layer {layer_name} imports "
                f"{sorted(imported)} but {mod}.py registers a probe and is "
                f"NOT imported. The coordinator will not see it. "
                f"Add `{mod},  # noqa: F401 — registration` to the "
                f"`from codegenie.probes.{layer_name} import (...)` block."
            )
    assert not failures, (
        "Probe registered but not collected — coordinator-blind probes "
        "(Invariant 5):\n" + "\n".join(failures)
    )
