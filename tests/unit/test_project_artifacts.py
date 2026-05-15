"""
Phase 0 handoff artifacts must exist, parse, and pin the intent of every AC
in S5-02. GitHub-UI rendering and milestone closure are pinned indirectly via
the on-disk Handoff record (AC-8); CI greenness on main is corroborated by
the workflow-run URL pinned there.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GITHUB_USER_RE = re.compile(r"@[A-Za-z0-9-]+(/[A-Za-z0-9_-]+)?")


def _safe_load_mkdocs(text: str) -> dict[str, object]:
    """Load mkdocs.yml under SafeLoader, treating ``!!python/name:`` tags as opaque.

    The curated `mkdocs.yml` ships
    `!!python/name:pymdownx.superfences.fence_code_format` per pymdownx
    documentation; the default `SafeLoader` rejects the tag. Schema-shape
    tests (nav layout, key presence) don't need the resolved value, so we
    register a constructor that returns the tag suffix as a string. No code
    is evaluated.
    """

    class _MkdocsLoader(yaml.SafeLoader):
        pass

    def _ignore_python_name(loader: yaml.Loader, tag_suffix: str, node: yaml.Node) -> str:
        return str(node.tag)

    _MkdocsLoader.add_multi_constructor("tag:yaml.org,2002:python/name:", _ignore_python_name)
    return yaml.load(text, Loader=_MkdocsLoader)  # type: ignore[no-any-return]


def _flatten_nav(node: object) -> list[str]:
    out: list[str] = []
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, list):
        for item in node:
            out.extend(_flatten_nav(item))
    elif isinstance(node, dict):
        for value in node.values():
            out.extend(_flatten_nav(value))
    return out


# ---- AC-1: issue templates exist with valid frontmatter ----------------------

ISSUE_TEMPLATES = (
    ".github/ISSUE_TEMPLATE/new-probe.md",
    ".github/ISSUE_TEMPLATE/new-skill.md",
    ".github/ISSUE_TEMPLATE/adr-amendment.md",
)


@pytest.mark.parametrize("relpath", ISSUE_TEMPLATES)
def test_issue_template_has_valid_frontmatter(relpath: str) -> None:
    text = (REPO_ROOT / relpath).read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    assert m, f"{relpath}: missing GitHub frontmatter block"
    fm = yaml.safe_load(m.group(1)) or {}
    assert isinstance(fm, dict), f"{relpath}: frontmatter is not a mapping"
    assert fm.get("name"), f"{relpath}: frontmatter `name` missing or empty"
    assert fm.get("about"), f"{relpath}: frontmatter `about` missing or empty"


def test_adr_amendment_template_body_references_workflow() -> None:
    body = (REPO_ROOT / ".github/ISSUE_TEMPLATE/adr-amendment.md").read_text(encoding="utf-8")
    for marker in (
        "ADR-0007",
        "localv2.md §4",
        "probe_contract.v1.json",
        "templates/adr-amendment.md",
    ):
        assert marker in body, f"adr-amendment.md body missing marker: {marker!r}"


# ---- AC-2: dependabot schema --------------------------------------------------


def test_dependabot_yaml_schema() -> None:
    cfg = yaml.safe_load((REPO_ROOT / ".github/dependabot.yml").read_text(encoding="utf-8"))
    assert cfg.get("version") == 2, f"dependabot version != 2: {cfg.get('version')!r}"
    updates = cfg.get("updates") or []
    ecosystems = {u.get("package-ecosystem") for u in updates}
    assert ecosystems == {"pip", "github-actions"}, f"unexpected ecosystems: {ecosystems!r}"
    for u in updates:
        assert (u.get("schedule") or {}).get("interval") == "weekly", f"non-weekly: {u!r}"
        assert u.get("open-pull-requests-limit") == 5, f"PR cap != 5: {u!r}"


# ---- AC-3: CODEOWNERS gates with real owners ---------------------------------

CONTRACT_FROZEN_FILES = (
    "src/codegenie/probes/base.py",
    "tests/snapshots/probe_contract.v1.json",
    "tests/unit/test_pyproject_fence.py",
    "tests/unit/test_project_artifacts.py",
    "localv2.md",
    ".github/CODEOWNERS",
)
CONTRACT_FROZEN_DIRS = ("docs/production/adrs/",)


def _parse_codeowners(text: str) -> list[tuple[str, tuple[str, ...]]]:
    rules: list[tuple[str, tuple[str, ...]]] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        pattern, owners = parts[0], tuple(parts[1:])
        rules.append((pattern, owners))
    return rules


def test_codeowners_gates_contract_frozen_paths() -> None:
    rules = _parse_codeowners((REPO_ROOT / ".github/CODEOWNERS").read_text(encoding="utf-8"))
    patterns = {p: owners for p, owners in rules}

    for path in CONTRACT_FROZEN_FILES:
        assert path in patterns, f"CODEOWNERS missing rule for {path!r}"
        owners = patterns[path]
        assert owners, f"CODEOWNERS rule for {path!r} has no owners (silent no-gate)"
        assert all(GITHUB_USER_RE.fullmatch(o) for o in owners), (
            f"bad owner tokens for {path!r}: {owners!r}"
        )
        assert not path.endswith("/"), f"file path mis-rendered as directory: {path!r}"

    for path in CONTRACT_FROZEN_DIRS:
        assert path in patterns, f"CODEOWNERS missing rule for {path!r}"
        owners = patterns[path]
        assert owners, f"CODEOWNERS rule for {path!r} has no owners"
        assert path.endswith("/"), f"directory pattern missing trailing slash: {path!r}"


# ---- AC-4: PR template — three checkboxes, all paths, all CI jobs ------------

CI_JOBS = ("lint", "typecheck", "test", "security", "docs", "fence")


def test_pr_template_contract_and_ci_jobs() -> None:
    body = (REPO_ROOT / ".github/PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")
    checkboxes = re.findall(r"^- \[ \] .+$", body, flags=re.MULTILINE)
    assert len(checkboxes) >= 3, f"PR template has {len(checkboxes)} checkboxes; want >= 3"
    for path in (
        "src/codegenie/probes/base.py",
        "tests/snapshots/probe_contract.v1.json",
        "tests/unit/test_pyproject_fence.py",
        "localv2.md",
        "docs/production/adrs/",
    ):
        assert path in body, f"PR template missing contract-frozen path {path!r}"
    for job in CI_JOBS:
        assert re.search(rf"\b{job}\b", body), f"PR template missing CI job name {job!r}"
    assert "ADR-0007" in body, "PR template missing ADR-0007 reference"
    assert "ADR amendment" in body or "adr-amendment" in body, (
        "PR template missing ADR-amendment phrasing"
    )


# ---- AC-5: contributing.md sections + load-bearing content -------------------


def test_contributing_md_sections_and_content() -> None:
    body = (REPO_ROOT / "docs/contributing.md").read_text(encoding="utf-8")
    h2s = re.findall(r"^## (.+)$", body, flags=re.MULTILINE)
    section_markers = ("Bootstrap", "Running the harness", "Adding a probe", "Project conventions")
    for marker in section_markers:
        assert any(marker in h for h in h2s), (
            f"contributing.md missing H2 section: {marker!r}; got {h2s!r}"
        )

    for ratchet in ("85/75", "87/77", "90/80"):
        assert ratchet in body, f"contributing.md missing coverage ratchet datapoint: {ratchet!r}"

    for extra in ("gather", "dev", "service", "agents"):
        assert extra in body, (
            f"contributing.md missing [project.optional-dependencies] extra: {extra!r}"
        )
    assert "[agents]" in body, "contributing.md must name the [agents] slot for LLM SDKs (ADR-0006)"

    for marker in ("ADR-0007", "make bootstrap", "codegenie gather", "LanguageDetectionProbe"):
        assert marker in body, f"contributing.md missing required marker: {marker!r}"

    assert "Probe version bumps" in body or "probe-version-bump" in body, (
        "contributing.md missing Q2 resolution (probe-version-bump convention)"
    )

    assert "TODO(S5-02)" not in body, "contributing.md still contains S1-04's TODO(S5-02) marker"


# ---- AC-6: contributing.md is in mkdocs nav exactly once ---------------------


def test_contributing_md_is_in_mkdocs_nav() -> None:
    cfg = _safe_load_mkdocs((REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8"))
    refs = _flatten_nav(cfg.get("nav") or [])
    hits = [p for p in refs if p.endswith("contributing.md")]
    assert len(hits) == 1, (
        f"contributing.md must appear exactly once in nav; got {hits!r} from {refs!r}"
    )


# ---- AC-7: pyproject mirrors the coverage-ratchet comment --------------------
#
# Originally written against the Phase 0 ratchet plan (`85/75 → 87/77 → 90/80`).
# Phase 1's ADR-0005 corrects this: there is no `87/77` intermediate — Phase 1
# raises the global to 90/80 (in S6-02) with 85/75 carve-outs for
# `probes/deployment.py` and `probes/ci.py` (S4-04). Story S4-04 AC-9 rewrote
# the inline pyproject comment to match ADR-0005; this test was updated in
# lockstep to pin the *corrected* contract.


def test_pyproject_mirrors_coverage_ratchet_schedule() -> None:
    lines = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines()
    anchors = [i for i, ln in enumerate(lines) if "--cov-fail-under=85" in ln]
    assert anchors, "pyproject.toml has no `--cov-fail-under=85` line to anchor the comment to"
    for anchor in anchors:
        window = lines[max(0, anchor - 6) : anchor + 7]
        joined = "\n".join(line for line in window if line.lstrip().startswith("#"))
        if (
            "90/80" in joined
            and "S6-02" in joined
            and "ADR-0005" in joined
            and "contributing.md" in joined
            and "87/77" not in joined
        ):
            return
    pytest.fail(
        "pyproject.toml is missing the corrected coverage-ratchet comment near "
        "--cov-fail-under=85 (must reference S6-02, ADR-0005, contributing.md "
        "and NOT contain the stale 87/77 intermediate per ADR-0005 / S4-04 AC-9)"
    )


# ---- AC-8: phase README pins the handoff record ------------------------------

PR_URL_RE = re.compile(r"https://github\.com/[^\s)]+/pull/\d+")
SHA_RE = re.compile(r"\b[0-9a-f]{40}\b")
WORKFLOW_RUN_RE = re.compile(r"https://github\.com/[^\s)]+/actions/runs/\d+")
MILESTONE_RE = re.compile(r"https://github\.com/[^\s)]+/milestone/\d+")
ISSUE_RE = re.compile(r"https://github\.com/[^\s)]+/issues/\d+")


def test_phase_readme_pins_handoff_evidence() -> None:
    readme = (REPO_ROOT / "docs/phases/00-bullet-tracer-foundations/README.md").read_text(
        encoding="utf-8"
    )
    assert re.search(r"^## Exit criteria\b", readme, flags=re.MULTILINE), (
        "README missing `## Exit criteria` section"
    )
    handoff_match = re.search(
        r"^## Handoff record\b(.*?)(?=^## |\Z)", readme, flags=re.MULTILINE | re.DOTALL
    )
    assert handoff_match, "README missing `## Handoff record` section"
    record = handoff_match.group(1)

    assert PR_URL_RE.search(record), "Handoff record missing merged PR URL"
    assert SHA_RE.search(record), "Handoff record missing 40-char main HEAD SHA"
    assert WORKFLOW_RUN_RE.search(record), "Handoff record missing workflow-run URL"
    assert "3.11" in record and "3.12" in record, (
        "Handoff record must name both Python matrix versions"
    )
    assert MILESTONE_RE.search(record), "Handoff record missing Phase 1 milestone URL"

    issue_urls = ISSUE_RE.findall(record)
    assert len(issue_urls) == 8, (
        f"Handoff record must list exactly 8 Phase 1 issue URLs; got {len(issue_urls)}"
    )
