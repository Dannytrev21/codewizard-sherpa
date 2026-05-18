"""Shared static-check kernel for ``regenerate.sh`` allowlist tests (S7-01 AC-31).

This module is the single source of truth for what a fixture's
``regenerate.sh`` is allowed to invoke. It lifts now (at three consumers,
the rule-of-three boundary) because the *policy* is load-bearing — a
copy-pasted tokenizer across three test files is exactly the smell that
allows a future contributor "tidying up" two of three sites to silently
weaken the third (the structural enforcement of 02-ADR-0001 at the
fixture boundary).

Two exported names:

- :data:`_SHELL_COREUTILS_ALLOWLIST` — the small frozenset of bare POSIX
  coreutils that ``regenerate.sh`` scripts may invoke without an
  ADR-0001 amendment (they ship with every Linux/macOS dev environment
  and pose no supply-chain risk).
- :func:`tokenize_invoked_binaries` — the static-check parser. Given the
  bytes of a shell script, returns the set of binary names invoked
  (first whitespace token of each non-blank, non-comment, non-builtin
  line, minus shell variable assignments).

Reused unchanged by S7-02's three additional fixture regen-allowlist
tests (``monorepo-pnpm``, ``stale-scip``).
"""

from __future__ import annotations

from typing import Final

# POSIX coreutils that ship with every Linux/macOS dev environment. These
# are *not* in ``ALLOWED_BINARIES`` (which gates *probe-time* subprocess
# invocation) — they are only callable from review-as-code shell scripts
# that an operator runs deliberately. The set is closed; adding to it is
# a deliberate PR edit reviewed alongside the fixture changes.
_SHELL_COREUTILS_ALLOWLIST: Final[frozenset[str]] = frozenset(
    {
        "mkdir",
        "rm",
        "cp",
        "mv",
        "chmod",
        "cat",
        "sed",
        "awk",
        "grep",
        "sort",
        "uniq",
        "tr",
        "find",
        "xargs",
        "sha256sum",
        "tee",
        "dirname",
        "basename",
        "pwd",
        "head",
        "tail",
        "wc",
        "printf",
        "touch",
    }
)

# Tokens that are shell control-flow / builtins / no-op-from-binary-pov.
# These are stripped from the invoked-binary set so the static check sees
# only the actual external binaries the script reaches for.
_SHELL_BUILTINS: Final[frozenset[str]] = frozenset(
    {
        "set",
        "if",
        "then",
        "fi",
        "elif",
        "else",
        "for",
        "do",
        "done",
        "while",
        "case",
        "esac",
        "function",
        "local",
        "export",
        "declare",
        "readonly",
        "echo",
        "return",
        "exit",
        "true",
        "false",
        "source",
        ".",
        "cd",
        "[",
        "[[",
        "test",
        "trap",
        "shift",
        "break",
        "continue",
        "unset",
        "alias",
        "command",
        "type",
        "hash",
    }
)

# Explicitly forbidden tokens — even if a future contributor wires one
# into the coreutils allowlist by accident, the static check still fails
# loud. ``eval`` is the canonical shell-injection avenue; ``curl``/``wget``
# would let a regen script fetch arbitrary remote bytes (supply-chain).
_SHELL_FORBIDDEN: Final[frozenset[str]] = frozenset(
    {
        "eval",
        "curl",
        "wget",
        "nc",
        "ncat",
        "pnpm",
        "npm",
        "yarn",
        "node-gyp",
        "pip",
        "pip3",
        "easy_install",
    }
)


def _strip_inline_comment(line: str) -> str:
    """Drop the trailing ``# ...`` inline comment from a shell line.

    Naive (does not handle ``# `` inside quoted strings), but sufficient
    for review-as-code regen scripts that never carry quoted ``#`` bytes
    on a binary-invocation line.
    """
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return line[:i]
    return line


def _is_variable_assignment(token: str) -> bool:
    """Return ``True`` if *token* looks like ``NAME=value``.

    Matches the shell-variable-assignment shape ``^[A-Za-z_][A-Za-z0-9_]*=``.
    Drops the assignment from the invoked-binary set so ``FOO=bar cmd ...``
    doesn't get parsed as a binary invocation of ``FOO=bar``.
    """
    if "=" not in token:
        return False
    name = token.split("=", 1)[0]
    if not name:
        return False
    if not (name[0].isalpha() or name[0] == "_"):
        return False
    return all(c.isalnum() or c == "_" for c in name)


def _extract_subshell_commands(line: str) -> tuple[str, list[str]]:
    """Strip ``$(...)`` subshell substitutions; return cleaned line + commands.

    For a line like ``PARENT=$(git rev-parse HEAD)``:
    - Returns ``("PARENT=", ["git"])``.

    The first token inside each ``$(...)`` block is the invoked binary;
    the rest are its args (NOT invoked binaries themselves). The outer
    line is left with the subshell replaced by an empty string so the
    rest of the tokenizer (variable-assignment, builtin detection) sees
    a sensible residue.

    Nested ``$(...)`` blocks are handled by depth tracking; backslash-
    escaped quotes inside subshells are NOT modeled (review-as-code
    regen scripts don't need that).
    """
    cleaned: list[str] = []
    commands: list[str] = []
    i = 0
    depth = 0
    inner_start = 0
    inner: list[str] = []
    while i < len(line):
        ch = line[i]
        if depth == 0 and ch == "$" and i + 1 < len(line) and line[i + 1] == "(":
            depth = 1
            inner_start = i + 2
            i += 2
            continue
        if depth > 0:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    inner_text = line[inner_start:i].strip()
                    inner.append(inner_text)
                    i += 1
                    continue
            i += 1
            continue
        cleaned.append(ch)
        i += 1
    for inner_text in inner:
        tokens = inner_text.split()
        if tokens:
            commands.append(tokens[0])
    return "".join(cleaned), commands


def tokenize_invoked_binaries(script_bytes: bytes) -> frozenset[str]:
    """Return the set of binary tokens invoked by *script_bytes*.

    The parser is deliberately conservative: each non-blank,
    non-``#``-only line is scanned for its first non-builtin,
    non-assignment token. ``$(...)`` subshell substitutions are
    handled by extracting the inner command token (not its args) and
    treating the surrounding line as if the substitution were empty,
    so ``PARENT=$(git rev-parse HEAD)`` contributes ``git`` to the
    invoked set and nothing else.

    Lines that start with a shebang (``#!/...``) are skipped.

    Args:
        script_bytes: Raw bytes of a ``regenerate.sh`` file. UTF-8 decode
            is used; non-UTF-8 bytes raise ``UnicodeDecodeError`` (loud
            failure — fixtures must be UTF-8).

    Returns:
        Frozen set of bare-binary tokens. Membership testing against
        ``ALLOWED_BINARIES ∪ _SHELL_COREUTILS_ALLOWLIST`` is the static
        check the caller performs.
    """
    text = script_bytes.decode("utf-8")
    invoked: set[str] = set()
    continuation = False
    for raw_line in text.splitlines():
        line = _strip_inline_comment(raw_line)
        # Backslash-continuation: a line ending in ``\`` continues onto
        # the next. We treat the following physical line as a
        # continuation (not a fresh command-line) and skip its first-
        # token analysis.
        ends_with_backslash = line.rstrip().endswith("\\")
        line = line.strip()
        if continuation:
            continuation = ends_with_backslash
            continue
        continuation = ends_with_backslash
        if not line:
            continue
        if line.startswith("#"):
            continue
        cleaned, sub_commands = _extract_subshell_commands(line)
        invoked.update(sub_commands)
        cleaned_line = cleaned.strip()
        if not cleaned_line:
            continue
        # Drop leading variable-assignment prefixes like ``FOO=bar BAZ=qux cmd ...``
        # to expose the actual command token.
        tokens = cleaned_line.split()
        while tokens and _is_variable_assignment(tokens[0]):
            tokens = tokens[1:]
        if not tokens:
            continue
        first = tokens[0]
        if first in _SHELL_BUILTINS:
            continue
        if _is_variable_assignment(first):
            continue
        invoked.add(first)
    return frozenset(invoked)
