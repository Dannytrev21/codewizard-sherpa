"""Pure Dockerfile parser used by :class:`DockerfileProbe`.

Hand-rolled line-by-line. **Never** evaluates shell. **Never** expands
``${VAR}``. **Never** imports ``subprocess`` / ``os.system`` / ``eval`` /
``exec``. The slice carries the literal text of every directive.

Algorithm:

1. Split source into physical lines; join physical lines that end with a
   trailing backslash into a single logical line (line-continuation).
2. Drop comment-only lines (``#`` at column 0 of the joined line) *except*
   parser directives like ``# syntax=docker/dockerfile:1.4`` on the very
   first line.
3. For each logical directive, dispatch on the first whitespace-delimited
   token (case-insensitive per Docker's reference).
"""

from __future__ import annotations

import json
import re
from typing import Final

from codegenie.probes.layer_c._dockerfile_models import (
    ArgDirective,
    CopyDirective,
    DirectiveLine,
    EntrypointForm,
    Healthcheck,
    ParsedDockerfile,
    ParserDirective,
    RunCommand,
    Stage,
)

__all__ = ["parse_dockerfile_text", "tokenize_dockerfile_line"]

_KNOWN_DIRECTIVES: Final[frozenset[str]] = frozenset(
    {
        "FROM",
        "RUN",
        "COPY",
        "ADD",
        "USER",
        "EXPOSE",
        "HEALTHCHECK",
        "CMD",
        "ENTRYPOINT",
        "WORKDIR",
        "ENV",
        "LABEL",
        "ARG",
        "ONBUILD",
        "STOPSIGNAL",
        "SHELL",
        "VOLUME",
        "MAINTAINER",
    }
)
_PARSER_DIRECTIVE_RE: Final[re.Pattern[str]] = re.compile(
    r"^#\s*([A-Za-z][A-Za-z0-9_-]*)\s*=\s*(.+?)\s*$"
)
_HEALTHCHECK_OPT_RE: Final[re.Pattern[str]] = re.compile(r"--([A-Za-z][\w-]*)=(\S+)")
_FROM_RE: Final[re.Pattern[str]] = re.compile(r"^(?P<img>\S+)(?:\s+AS\s+(?P<name>\S+))?\s*$", re.I)
_COPY_FROM_RE: Final[re.Pattern[str]] = re.compile(r"--from=(\S+)")
_KV_RE: Final[re.Pattern[str]] = re.compile(r'([A-Za-z_][\w\.]*)=(?:"((?:[^"\\]|\\.)*)"|(\S+))')


def tokenize_dockerfile_line(line: str) -> DirectiveLine | None:
    """Return ``(directive, payload)`` or ``None`` for non-directive lines."""
    stripped = line.lstrip()
    if not stripped or stripped.startswith("#"):
        return None
    head, _, payload = stripped.partition(" ")
    directive = head.upper()
    if directive not in _KNOWN_DIRECTIVES:
        return None
    return DirectiveLine(kind=directive, payload=payload.strip())


def _join_continuations(text: str) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if line.endswith("\\"):
            buf.append(line[:-1])
            continue
        buf.append(line)
        out.append("\n".join(buf))
        buf = []
    if buf:
        out.append("\n".join(buf))
    return out


def _split_kv_pairs(payload: str) -> dict[str, str]:
    pairs = _KV_RE.findall(payload)
    if pairs:
        return {k: (q or v) for (k, q, v) in pairs}
    # Legacy "ENV A 1" single-pair form.
    head, _, rest = payload.partition(" ")
    rest = rest.strip()
    return {head: rest} if head and rest else {}


def _parse_array_or_shell(payload: str) -> tuple[EntrypointForm, list[str], str | None]:
    p = payload.strip()
    if p.startswith("["):
        try:
            argv = json.loads(p)
        except json.JSONDecodeError:
            return "malformed", [], p
        if isinstance(argv, list) and all(isinstance(s, str) for s in argv):
            return "exec", list(argv), None
        return "malformed", [], p
    return "shell", [], p


def _parse_healthcheck(payload: str) -> Healthcheck:
    if payload.strip().upper() == "NONE":
        return Healthcheck(kind="none")
    options = dict(_HEALTHCHECK_OPT_RE.findall(payload))
    _, _, after_cmd = payload.partition("CMD")
    return Healthcheck(kind="cmd", options=options, cmd=after_cmd.strip() or None)


def _new_stage(idx: int, payload: str, stages: list[Stage]) -> Stage:
    m = _FROM_RE.match(payload)
    base = m.group("img") if m else payload.strip()
    name = m.group("name") if m else None
    inherits = next((s.name for s in stages if s.name and s.name == base), None)
    return Stage(index=idx, base_image=base, name=name, inherits_from=inherits)


def _replace(stage: Stage, **kw: object) -> Stage:
    return Stage(**{**stage.model_dump(), **kw})


def parse_dockerfile_text(text: str, *, path: str) -> ParsedDockerfile:  # noqa: PLR0912, PLR0915
    """Parse Dockerfile *text* into a :class:`ParsedDockerfile`."""
    lines = _join_continuations(text)
    parser_directive: ParserDirective | None = None
    if lines and lines[0].lstrip().startswith("#"):
        pd = _PARSER_DIRECTIVE_RE.match(lines[0].lstrip())
        if pd is not None:
            parser_directive = ParserDirective(name=pd.group(1), value=pd.group(2))
    stages: list[Stage] = []
    run_cmds: list[RunCommand] = []
    copies: list[CopyDirective] = []
    global_args: list[ArgDirective] = []
    seen_from = False
    for line in lines:
        tok = tokenize_dockerfile_line(line)
        if tok is None:
            continue
        kind, payload = tok.kind, tok.payload
        if kind == "FROM":
            stages.append(_new_stage(len(stages), payload, stages))
            seen_from = True
            continue
        if kind == "ARG" and not seen_from:
            name, _, default = payload.partition("=")
            global_args.append(
                ArgDirective(
                    name=name.strip(), default=default.strip() or None, before_first_from=True
                )
            )
            continue
        if not stages:
            continue
        si = len(stages) - 1
        s = stages[si]
        if kind == "RUN":
            run_cmds.append(RunCommand(command=payload, stage_index=si))
        elif kind == "COPY" or kind == "ADD":
            from_match = _COPY_FROM_RE.search(payload)
            from_stage = from_match.group(1) if from_match else None
            resolved = (
                from_stage is None
                or any(prior.name == from_stage for prior in stages[:si])
                or (from_stage is not None and from_stage.isdigit() and int(from_stage) < si)
            )
            copies.append(
                CopyDirective(
                    raw=payload, from_stage=from_stage, from_stage_resolved=resolved, stage_index=si
                )
            )
        elif kind == "USER":
            s = _replace(s, user=payload.strip())
        elif kind == "WORKDIR":
            s = _replace(s, workdir=payload.strip())
        elif kind == "EXPOSE":
            s = _replace(s, expose=[*s.expose, *payload.split()])
        elif kind == "ENV":
            s = _replace(s, env={**s.env, **_split_kv_pairs(payload)})
        elif kind == "LABEL":
            s = _replace(s, labels={**s.labels, **_split_kv_pairs(payload)})
        elif kind == "HEALTHCHECK":
            s = _replace(s, healthcheck=_parse_healthcheck(payload))
        elif kind == "ENTRYPOINT":
            form, argv, cmd = _parse_array_or_shell(payload)
            s = _replace(s, entrypoint_form=form, entrypoint_argv=argv, entrypoint_command=cmd)
        elif kind == "CMD":
            form, argv, cmd = _parse_array_or_shell(payload)
            s = _replace(s, cmd_form=form, cmd_argv=argv, cmd_command=cmd)
        elif kind == "ARG":
            name, _, default = payload.partition("=")
            s = _replace(
                s, args=[*s.args, ArgDirective(name=name.strip(), default=default.strip() or None)]
            )
        stages[si] = s
    return ParsedDockerfile(
        path=path,
        stages=stages,
        run_commands=run_cmds,
        copy_directives=copies,
        parser_directive=parser_directive,
        global_args=global_args,
    )
