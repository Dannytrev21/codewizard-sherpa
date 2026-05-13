"""``python -m codegenie`` entry point.

Phase 0 ships only a placeholder CLI; the real subcommands
(``gather``, ``audit verify``, ``cache gc``) land in story S4-02.

The function signature pinned here (``main(argv) -> int``) is the contract
S4-02 inherits — keeping ``__main__.py``'s shape stable so subsequent
stories never have to refactor the entry path.
"""

from __future__ import annotations

import sys

import click

from codegenie.version import __version__


@click.command(
    name="codegenie",
    help=(
        "codewizard-sherpa local POC CLI. "
        "Phase 0 ships a placeholder; gather/audit/cache subcommands land in S4-02."
    ),
)
@click.version_option(__version__, prog_name="codegenie")
def _cli() -> None:
    """Placeholder root command.

    Invocations without flags print the help text instead of erroring; this
    keeps ``python -m codegenie`` discoverable while the real subcommand
    surface is still under construction (S4-02).
    """
    click.echo(_cli.get_help(click.get_current_context()))


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return its exit code.

    Parameters
    ----------
    argv:
        Optional argument vector. ``None`` (the default) defers to
        :data:`sys.argv` — the same behaviour ``click`` uses internally.

    Returns
    -------
    int
        Process exit code; ``0`` on success.
    """
    try:
        _cli.main(args=argv, prog_name="codegenie", standalone_mode=False)
    except click.exceptions.Exit as exc:
        return int(exc.exit_code)
    return 0


if __name__ == "__main__":  # pragma: no cover — module-as-script entry
    sys.exit(main())
