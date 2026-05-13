"""``python -m codegenie`` entry point.

S1-01 pinned the ``main(argv) -> int`` signature; S4-02 reshapes the body to
dispatch through :data:`codegenie.cli.cli` (the click group that now owns
``gather`` / ``audit verify`` / ``cache gc``). The signature stays stable so
downstream packagers and test fixtures keep working.

The dispatch wraps the click group in ``standalone_mode=False`` and traps
``click.exceptions.Exit`` so the function returns an integer exit code rather
than calling ``sys.exit`` itself; ``python -m codegenie`` (this module's
``__main__`` block) is the only place that escalates the return value to
``sys.exit``.
"""

from __future__ import annotations

import sys

import click

from codegenie.cli import cli


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
        cli.main(args=argv, prog_name="codegenie", standalone_mode=False)
    except click.exceptions.Exit as exc:
        return int(exc.exit_code)
    except SystemExit as exc:
        # The subcommands call ``sys.exit(code)`` directly; click's
        # ``standalone_mode=False`` lets ``SystemExit`` propagate. Translate
        # to a plain return value so callers can compose this function.
        code = exc.code if isinstance(exc.code, int) else (1 if exc.code else 0)
        return code
    except click.ClickException as exc:
        exc.show()
        return exc.exit_code
    return 0


if __name__ == "__main__":  # pragma: no cover — module-as-script entry
    sys.exit(main())
