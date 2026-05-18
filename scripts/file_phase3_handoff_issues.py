"""Impure shell that files the Phase-3 handoff GitHub issues (S8-04).

Two modes:

* ``--dry-run`` (default) — render :data:`ISSUE_SPECS` to
  ``tests/unit/docs/_fixtures/issues.json`` (pretty-printed JSON list). This
  is the path the executor and the unit tests use; it touches zero network.

* ``--live`` — invoke ``gh`` via ``subprocess.run`` to file each issue.
  Idempotent: title-dedupes via ``gh issue list``; updates body via
  ``gh issue edit`` only when the existing body differs. This path is
  **OPERATOR-RUN** at PR-merge time; the executor does not authenticate to
  GitHub.

Flags:

* ``--project <name>`` — optional GitHub Project board. If absent, issues file
  without project association and the script prints a loud warning to stderr
  (Rule 12). If supplied but unknown to ``gh project list``, the script exits
  with code 2.

Pre-flight: list repo milestones via ``gh api repos/:owner/:repo/milestones``;
if ``Phase 3 — Vuln remediation: deterministic recipe path`` is missing,
create it. Idempotent.

This script is the only file in the repo invoking ``gh``; the pure data
module ``_phase3_handoff_issues.py`` carries no subprocess / no os / no
network imports.
"""

from __future__ import annotations

import argparse
import json
import subprocess  # noqa: S404 — required for `gh` CLI invocation; live mode is operator-run.
import sys
from pathlib import Path

# Allow `python scripts/file_phase3_handoff_issues.py --dry-run` from repo root.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _phase3_handoff_issues import (  # noqa: E402 — sys.path injection above is required.
    ISSUE_SPECS,
    IssueSpec,
    milestones_needed,
)

_REPO_ROOT: Path = _SCRIPT_DIR.parent
_DEFAULT_FIXTURE_PATH: Path = _REPO_ROOT / "tests" / "unit" / "docs" / "_fixtures" / "issues.json"
_NO_PROJECT_WARNING: str = (
    "WARNING: no project board provided; issues filed without board association"
)


def render_registry(registry: tuple[IssueSpec, ...]) -> list[dict[str, object]]:
    """Render the IssueSpec tuple to a JSON-serializable list of dicts.

    Pure: identical inputs → byte-identical outputs (sorted labels, ordered
    fields). ``test_idempotent_second_run`` asserts two calls return equal
    objects.
    """
    rendered: list[dict[str, object]] = []
    for spec in registry:
        rendered.append(
            {
                "title": spec.title,
                "milestone": str(spec.milestone),
                "body": spec.body,
                "labels": sorted(spec.labels),
                "phase3_stories": list(spec.phase3_stories),
            }
        )
    return rendered


def _write_fixture(rendered: list[dict[str, object]], fixture_path: Path) -> None:
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(
        json.dumps(rendered, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def _gh_existing_milestones() -> frozenset[str]:
    """Call ``gh api repos/:owner/:repo/milestones`` and return the title set.

    Live-mode helper. The unit-test suite never reaches this — tests exercise
    the pure ``milestones_needed`` helper directly.
    """
    result = subprocess.run(  # noqa: S603 — `gh` from PATH; argv is fixed.
        ["gh", "api", "repos/:owner/:repo/milestones", "--paginate"],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout) if result.stdout.strip() else []
    if not isinstance(payload, list):
        return frozenset()
    titles: set[str] = set()
    for entry in payload:
        if isinstance(entry, dict):
            title = entry.get("title")
            if isinstance(title, str):
                titles.add(title)
    return frozenset(titles)


def _gh_create_milestone(title: str) -> None:
    """Idempotent milestone creation via ``gh api``."""
    subprocess.run(  # noqa: S603 — `gh` from PATH; argv is fixed.
        [
            "gh",
            "api",
            "repos/:owner/:repo/milestones",
            "-X",
            "POST",
            "-f",
            f"title={title}",
            "--silent",
        ],
        check=False,
    )


def _verify_project(project_name: str) -> bool:
    """Return True if ``project_name`` appears in ``gh project list`` output."""
    result = subprocess.run(  # noqa: S603 — `gh` from PATH; argv is fixed.
        ["gh", "project", "list", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return False
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False
    projects = payload.get("projects") if isinstance(payload, dict) else payload
    if not isinstance(projects, list):
        return False
    for entry in projects:
        if isinstance(entry, dict) and entry.get("title") == project_name:
            return True
    return False


def _live_file_one(spec: IssueSpec, project: str | None) -> None:
    """File or update one issue via ``gh``. Idempotent on second invocation."""
    list_result = subprocess.run(  # noqa: S603 — `gh` from PATH; argv fixed.
        [
            "gh",
            "issue",
            "list",
            "--json",
            "title,body,number",
            "--search",
            spec.title,
            "--state",
            "all",
            "--limit",
            "100",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    matches: list[dict[str, object]] = []
    if list_result.returncode == 0 and list_result.stdout.strip():
        try:
            payload = json.loads(list_result.stdout)
        except json.JSONDecodeError:
            payload = []
        if isinstance(payload, list):
            for entry in payload:
                if isinstance(entry, dict) and entry.get("title") == spec.title:
                    matches.append(entry)

    if matches:
        existing = matches[0]
        existing_body = existing.get("body")
        number = existing.get("number")
        if existing_body == spec.body:
            sys.stderr.write(f"skip (no body diff): #{number} {spec.title}\n")
            return
        if not isinstance(number, int):
            sys.stderr.write(f"skip (no issue number): {spec.title}\n")
            return
        subprocess.run(  # noqa: S603 — `gh` from PATH; argv fixed.
            [
                "gh",
                "issue",
                "edit",
                str(number),
                "--body",
                spec.body,
            ],
            check=False,
        )
        sys.stderr.write(f"edit: #{number} {spec.title}\n")
        return

    argv: list[str] = [
        "gh",
        "issue",
        "create",
        "--title",
        spec.title,
        "--body",
        spec.body,
        "--milestone",
        str(spec.milestone),
    ]
    for label in sorted(spec.labels):
        argv.extend(["--label", label])
    if project is not None:
        argv.extend(["--project", project])
    subprocess.run(argv, check=False)  # noqa: S603 — `gh` from PATH; argv fixed.
    sys.stderr.write(f"create: {spec.title}\n")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="file_phase3_handoff_issues",
        description=__doc__,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Write the rendered registry to the fixture path; do not call `gh`.",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="Invoke `gh` to file (or update) the eight issues. OPERATOR-RUN.",
    )
    parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="Optional GitHub Project board name to associate issues with.",
    )
    parser.add_argument(
        "--fixture-path",
        type=Path,
        default=_DEFAULT_FIXTURE_PATH,
        help="Output path for --dry-run fixture (default: tests/unit/docs/_fixtures/issues.json).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns POSIX exit code."""
    args = _parse_args(argv)
    # Default behaviour: when neither --dry-run nor --live, treat as --dry-run
    # so the executor can run safely without authentication.
    dry_run = args.dry_run or not args.live

    if args.project is None:
        sys.stderr.write(_NO_PROJECT_WARNING + "\n")
    elif not dry_run and not _verify_project(args.project):
        sys.stderr.write(
            f"ERROR: --project {args.project!r} not found in `gh project list`; "
            "supply a known project name or omit --project to file without "
            "board association.\n"
        )
        return 2

    rendered = render_registry(ISSUE_SPECS)

    if dry_run:
        _write_fixture(rendered, args.fixture_path)
        sys.stderr.write(f"wrote {args.fixture_path}\n")
        return 0

    existing_milestones = _gh_existing_milestones()
    for missing in sorted(milestones_needed(existing_milestones, ISSUE_SPECS)):
        sys.stderr.write(f"creating milestone: {missing}\n")
        _gh_create_milestone(missing)

    for spec in ISSUE_SPECS:
        _live_file_one(spec, args.project)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
