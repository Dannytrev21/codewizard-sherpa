# Story S10-03 — `DockerfilePolicyGate` strict-AND across six invariants

**Step:** Step 10 — `DockerfileBaseImageSwapTransform` + `DockerfileMultiStageRefactorTransform` + three gates
**Status:** Ready
**Effort:** M
**Depends on:** S7-05 (probe-contract conformance + envelope-validation integration test — the `@register_signal_kind` registry is loaded by then), S10-01 (`DockerfileBaseImageSwapTransform` produces the rendered Dockerfile this gate consumes)
**ADRs honored:** [Phase 7 ADR-0012](../ADRs/0012-dockerfile-policy-gate-strict-and-no-override.md) (**strict-AND, NO `--allow-policy-violations` flag** — the design decision is hard-fail-no-override), [Phase 5 ADR-0003](../../05-sandbox-trust-gates/ADRs/0003-trustscorer-extension-via-signal-kind-registry.md) (open `@register_signal_kind` registry), [Phase 7 ADR-0013](../ADRs/0013-dockerfile-recipe-engine-dockerfile-parse.md) (pure-Python `dockerfile-parse` for AST parsing)

> **⚠ Amendment A sequencing note (2026-05-20).** This story predates Phase 7 Amendment A ([`../final-design.md` §Amendment A](../final-design.md)). The gate consumes the refusal taxonomy from **[S16-01](S16-01-migration-refusal-taxonomy.md)** and runs after the [S16-02](S16-02-recipe-contract-amendment.md) recipe contract amendment. Do **not** execute before Steps 13–16 land. See [`README.md` §"Stories — Amendment A"](README.md).

## Context

Phase 5 establishes the strict-AND `TrustScorer` discipline: trust score is the conjunction over objective signals; a single failing gate fails the whole score; no thresholds, no overrides. Phase 7 contributes its first static pre-build gate: `DockerfilePolicyGate` — a pure function over rendered Dockerfile text + parsed AST that evaluates six load-bearing invariants:

1. **`USER` is set and is non-root.** No `USER root`, no missing `USER` directive.
2. **No new `--cap-add` instructions** beyond the Phase 6.5 baseline.
3. **No new `--privileged` flag.**
4. **`ENTRYPOINT` is in exec form** (`["cmd", "arg"]`), not shell form (`cmd arg`).
5. **`HEALTHCHECK` is not in shell form** (if present, must be exec form).
6. **No new build-time secret mounts** (`--mount=type=secret`) beyond the Phase 6.5 baseline.

The security-first lens design proposed this gate; the critic concurred. [ADR-0012](../ADRs/0012-dockerfile-policy-gate-strict-and-no-override.md) locks the no-override position. **There is no `--allow-policy-violations` flag**; the CLI's `--help` does not document any override path. Operators reading the audit log see the failing-invariants list and fix the Dockerfile or the recipe; they do not flag-override.

The gate's `isolation_class="none"` is deliberate — this is a pure function over already-rendered text + AST. No microVM is required; no `SandboxClient` is involved (compare S10-04's `DistrolessBuildGate` which DOES use `SandboxClient.spawn(role=Role.GATE)`). Performance envelope: ≤ 10 ms. Failure outcome: `DockerfilePolicyGateFailed(failing_invariants=tuple[Invariant, ...])` — strict-AND in the `TrustScorer` halts the workflow before any sandbox cost is paid.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §12` — three gates declared via `@register_signal_kind`; `DockerfilePolicyGate` is `isolation_class="none"`; six invariants; **no `--allow-policy-violations` override**; failure outcome `DockerfilePolicyGateFailed(failing_invariants=[...])`.
  - `../phase-arch-design.md §Edge cases #7` — `COPY --from=base` referencing removed stage produces broken Dockerfile → policy gate catches via the `--from` resolves-to-existing-stage check.
  - `../phase-arch-design.md §Edge cases #8` — recipe output fails policy gate (USER removed, cap added) → strict-AND fail; HITL with failing-invariant list; **no override**.
  - `../phase-arch-design.md §Control flow §step 8` — policy gate is the first gate in the stack; strict-AND fail halts before `DistrolessBuildGate` even runs (saves the microVM cost).
- **Phase ADRs:**
  - [`../ADRs/0012-dockerfile-policy-gate-strict-and-no-override.md`](../ADRs/0012-dockerfile-policy-gate-strict-and-no-override.md) — the six invariants as a sum type `Invariant`; gate output is `Passed | Failed(failing_invariants: tuple[Invariant, ...])`; **no `--allow-policy-violations` CLI flag** — `--help` does not document any override path.
- **Phase 5 (existing code):**
  - `src/codegenie/sandbox/gates/registry.py` — `@register_signal_kind(name, isolation_class)` decorator + the `Gate` ABC. Pattern precedent: Phase 5 ships `build`, `install`, `tests`, `trace`, `policy`, `cve_delta` via the same decorator.
  - `src/codegenie/sandbox/trust_scorer.py` — the strict-AND `TrustScorer`; consumes `GateSignal.kind` and the gate's pass/fail outcome.
- **Existing code:**
  - `plugins/distroless-migration--node--npm/recipes/dockerfile_base_image_swap.py` (S10-01) — produces the rendered Dockerfile this gate evaluates.

## Goal

Land `plugins/distroless-migration--node--npm/recipes/dockerfile_policy_gate.py`. `DockerfilePolicyGate(Gate)` is decorated `@register_signal_kind(name="dockerfile_policy", isolation_class="none")`. It is a pure function over the rendered Dockerfile text + `dockerfile-parse` AST. It evaluates the six invariants and emits `DockerfilePolicyGatePassed | DockerfilePolicyGateFailed(failing_invariants=tuple[Invariant, ...])`. Strict-AND `TrustScorer` halts the workflow on any failure. **No `--allow-policy-violations` flag exists in the CLI** — verified by a CLI inspection test (AC-12). p99 ≤ 10 ms.

## Acceptance criteria

### Gate surface + registration

- [ ] **AC-1 — Module + class location.** `plugins/distroless-migration--node--npm/recipes/dockerfile_policy_gate.py` defines `class DockerfilePolicyGate(Gate)`. The class is decorated `@register_signal_kind(name="dockerfile_policy", isolation_class="none")`. After plugin load, `signal_kind_registry["dockerfile_policy"]` returns this class.
- [ ] **AC-2 — `isolation_class="none"`.** The gate is a pure function — no `SandboxClient`, no `subprocess`, no `docker buildx`, no network. AST-walk fence: `tests/fence/test_policy_gate_purity.py` walks `dockerfile_policy_gate.py` and rejects any import from `codegenie.sandbox.client`, `codegenie.exec.*`, `subprocess`, `os.system`, `os.popen`. (Locks `isolation_class="none"` mechanically.)
- [ ] **AC-3 — `Gate` ABC compliance.** `DockerfilePolicyGate` implements the `Gate` interface Phase 5 ships. `isinstance(g, Gate)` is `True`. Output of the gate's `evaluate(...)` (or whatever Phase 5 names it) is `Passed | Failed(failing_invariants: tuple[Invariant, ...])`.

### The six invariants as a sum type

- [ ] **AC-4 — `Invariant` enum.** Module-level `class Invariant(StrEnum)` with exactly six members (and no more — adding a seventh requires a Phase-7 ADR amendment per ADR-0012):
  - `USER_NOT_SET_OR_ROOT`
  - `CAP_ADD_INTRODUCED`
  - `PRIVILEGED_INTRODUCED`
  - `ENTRYPOINT_NOT_EXEC_FORM`
  - `HEALTHCHECK_SHELL_FORM`
  - `BUILD_TIME_SECRET_MOUNT_INTRODUCED`
- [ ] **AC-5 — `DockerfilePolicyGatePassed` / `DockerfilePolicyGateFailed` Pydantic models.** Frozen, `extra="forbid"`. `DockerfilePolicyGateFailed` carries `failing_invariants: tuple[Invariant, ...]` — tuple, not list (true immutability per Phase 3 S1-04 precedent). Test: `failing_invariants` cannot be `.append()`-ed; tuple coercion from JSON ingest.
- [ ] **AC-6 — Exhaustiveness via `match` + `assert_never`.** Consumers of the gate output use `match` over `Passed | Failed`; the strict-AND scorer's path is exercised in `tests/unit/gates/test_dockerfile_policy_gate.py::test_match_exhaustive` (a deliberately-crafted `match` statement plus `from typing import assert_never` import on the unreachable arm).

### Per-invariant pass/fail evaluation

- [ ] **AC-7 — Each invariant has a pass-fixture and a fail-fixture.** `tests/unit/gates/test_dockerfile_policy_gate.py` has six parametrized test pairs, one per `Invariant`:
  - `USER_NOT_SET_OR_ROOT` — fail: `Dockerfile` with `USER root`; fail: `Dockerfile` with no `USER` directive; pass: `Dockerfile` with `USER nonroot` (uid 65532).
  - `CAP_ADD_INTRODUCED` — fail: `RUN --security=insecure --cap-add=NET_ADMIN ...`; pass: no `--cap-add` flag.
  - `PRIVILEGED_INTRODUCED` — fail: `RUN --privileged ...`; pass: no `--privileged`.
  - `ENTRYPOINT_NOT_EXEC_FORM` — fail: `ENTRYPOINT npm start`; pass: `ENTRYPOINT ["npm", "start"]`.
  - `HEALTHCHECK_SHELL_FORM` — fail: `HEALTHCHECK CMD curl -f http://localhost`; pass: `HEALTHCHECK CMD ["curl", "-f", "http://localhost"]`; pass: absent.
  - `BUILD_TIME_SECRET_MOUNT_INTRODUCED` — fail: `RUN --mount=type=secret,id=npmrc npm install`; pass: no `--mount=type=secret`.
- [ ] **AC-8 — Combinatorial failure case.** Fixture with three invariants violated simultaneously → `failing_invariants` carries all three in deterministic order (sorted by `Invariant`'s declaration order — NOT alphabetical, NOT input order). Test pins ordering.
- [ ] **AC-9 — Happy path.** Fixture with a clean distroless-target Dockerfile (`FROM cgr.dev/chainguard/node`, `USER nonroot`, exec-form `CMD`, no `--cap-add`/`--privileged`/`--mount=type=secret`, no `HEALTHCHECK` or exec-form `HEALTHCHECK`) → `DockerfilePolicyGatePassed`.

### No override flag

- [ ] **AC-10 — No `--allow-policy-violations` flag in the CLI.** `tests/fence/test_no_policy_override_flag.py` invokes `codegenie --help` and `codegenie remediate --help` (or whichever subcommand orchestrates Phase 7); asserts the string `--allow-policy-violations` does NOT appear in either stdout. Also asserts the string does NOT appear anywhere under `src/codegenie/cli/` via grep-style source scan. (Locks ADR-0012 §Decision mechanically.)
- [ ] **AC-11 — No threshold tunable.** No `policy_gate_threshold` or similar field in the gate's `__init__` or in any config Pydantic model. Strict-AND is the only mode. Test: `inspect.signature(DockerfilePolicyGate.__init__)` carries no `threshold`/`tolerance`/`allow_failures` parameter.
- [ ] **AC-12 — No per-invariant warning mode.** No `Invariant.{ENUM}.severity` field; no `warning_only: bool` parameter. Every invariant is hard-fail. (ADR-0012 §Decision: "no per-invariant warning mode".)

### Audit + diagnostic

- [ ] **AC-13 — Failing-invariants list flows to audit log.** `DockerfilePolicyGateFailed(rendered_dockerfile_digest, failing_invariants)` is emitted as a typed event to the spanning log (audit-tier). The `remediation-report.yaml` writer (Phase 3 / Phase 7 reused) includes the failing-invariants list. Test: integration test in `tests/integration/test_policy_gate_audit_trail.py` runs the gate against a fail-fixture, asserts the spanning log carries the typed event with the exact `failing_invariants` tuple.
- [ ] **AC-14 — `_WARNING_IDS`** `Final[frozenset[str]]` validated at import via `raise AssertionError(...)` (NOT bare `assert`). IDs include `dockerfile_policy.user_not_set_or_root`, ..., `dockerfile_policy.build_time_secret_mount_introduced` (one per invariant). Pattern `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`.

### Perf + gates

- [ ] **AC-15 — p99 ≤ 10 ms.** `tests/perf/test_dockerfile_policy_gate.py::test_policy_p99_under_10ms` over 1000 trials on a representative Dockerfile. Marked `@pytest.mark.bench`.
- [ ] **AC-16** — `mypy --strict plugins/distroless-migration--node--npm/recipes/` clean.
- [ ] **AC-17** — `ruff check ... && ruff format --check` clean.
- [ ] **AC-18** — `make lint-imports` green.
- [ ] **AC-19** — Phase 3–6.5 regression suite + `bench/vuln-remediation/` cassette replay byte-equal.

## Implementation outline

1. **`plugins/distroless-migration--node--npm/recipes/dockerfile_policy_gate.py`** — define `class Invariant(StrEnum)` with six members; define `class DockerfilePolicyGatePassed(BaseModel)` (frozen, `extra="forbid"`) carrying `rendered_dockerfile_digest: str`; define `class DockerfilePolicyGateFailed(BaseModel)` carrying `rendered_dockerfile_digest: str, failing_invariants: tuple[Invariant, ...]`; define `class DockerfilePolicyGate(Gate)` decorated `@register_signal_kind(name="dockerfile_policy", isolation_class="none")`.
2. **`evaluate()` implementation** — pure function:
   - Parse the rendered Dockerfile via `dockerfile-parse`.
   - For each invariant, a module-level pure predicate (`_check_user_nonroot`, `_check_no_cap_add`, ...) returns `bool` (passes) given the parsed AST + raw text.
   - Iterate the six predicates via a module-level `_INVARIANT_PREDICATES: Final[tuple[tuple[Invariant, Callable[[ParsedDockerfile, str], bool]], ...], ...]` (data-driven; iterated, NOT branched).
   - Collect failing invariants in declaration order; return `Passed` if empty, `Failed(...)` otherwise.
3. **Six per-invariant fixtures** under `tests/fixtures/recipes/dockerfile-policy-gate/`: one pass-fixture + one (or two) fail-fixtures per invariant. Plus the combinatorial 3-fail fixture (AC-8) and the all-pass happy fixture (AC-9).
4. **`tests/unit/gates/test_dockerfile_policy_gate.py`** — parametrized over fixtures.
5. **`tests/fence/test_policy_gate_purity.py`** — AST-walk asserts no `subprocess`/`sandbox.client`/`exec.*` imports.
6. **`tests/fence/test_no_policy_override_flag.py`** — CLI `--help` inspection + source-tree grep for `--allow-policy-violations`.
7. **`tests/integration/test_policy_gate_audit_trail.py`** — typed event flows to spanning log.
8. **`tests/perf/test_dockerfile_policy_gate.py::test_policy_p99_under_10ms`** — bench.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/unit/gates/test_dockerfile_policy_gate.py`

```python
import pytest

# Will fail with ImportError until the module exists.
from plugins.distroless_migration__node__npm.recipes.dockerfile_policy_gate import (
    DockerfilePolicyGate,
    DockerfilePolicyGateFailed,
    DockerfilePolicyGatePassed,
    Invariant,
)


_PASS_DOCKERFILE = """\
FROM cgr.dev/chainguard/node:20@sha256:deadbeef
USER nonroot
WORKDIR /app
COPY --from=builder /app/dist /app/dist
CMD ["node", "/app/dist/server.js"]
"""


_FAIL_USER_ROOT = _PASS_DOCKERFILE.replace("USER nonroot", "USER root")
_FAIL_SHELL_CMD = _PASS_DOCKERFILE.replace(
    'CMD ["node", "/app/dist/server.js"]',
    "CMD node /app/dist/server.js",
)
_FAIL_SECRET_MOUNT = _PASS_DOCKERFILE.replace(
    "WORKDIR /app",
    "RUN --mount=type=secret,id=npmrc npm install",
)


def test_pass_dockerfile_is_passed() -> None:
    gate = DockerfilePolicyGate()
    result = gate.evaluate(rendered_text=_PASS_DOCKERFILE)
    assert isinstance(result, DockerfilePolicyGatePassed)


@pytest.mark.parametrize(
    "rendered,expected_invariant",
    [
        (_FAIL_USER_ROOT, Invariant.USER_NOT_SET_OR_ROOT),
        (_FAIL_SHELL_CMD, Invariant.ENTRYPOINT_NOT_EXEC_FORM),
        (_FAIL_SECRET_MOUNT, Invariant.BUILD_TIME_SECRET_MOUNT_INTRODUCED),
    ],
)
def test_each_invariant_individually(rendered: str, expected_invariant: Invariant) -> None:
    gate = DockerfilePolicyGate()
    result = gate.evaluate(rendered_text=rendered)
    assert isinstance(result, DockerfilePolicyGateFailed)
    assert expected_invariant in result.failing_invariants


def test_combinatorial_failure_ordering_is_deterministic() -> None:
    """Three invariants violated; failing_invariants is sorted by Invariant declaration order."""
    multi_fail = _FAIL_USER_ROOT.replace(
        'CMD ["node", "/app/dist/server.js"]',
        "CMD node /app/dist/server.js",
    ).replace(
        "WORKDIR /app",
        "RUN --mount=type=secret,id=npmrc npm install",
    )
    gate = DockerfilePolicyGate()
    result = gate.evaluate(rendered_text=multi_fail)
    assert isinstance(result, DockerfilePolicyGateFailed)
    assert result.failing_invariants == (
        Invariant.USER_NOT_SET_OR_ROOT,
        Invariant.ENTRYPOINT_NOT_EXEC_FORM,
        Invariant.BUILD_TIME_SECRET_MOUNT_INTRODUCED,
    )


def test_failing_invariants_is_tuple_not_list() -> None:
    gate = DockerfilePolicyGate()
    result = gate.evaluate(rendered_text=_FAIL_USER_ROOT)
    assert isinstance(result, DockerfilePolicyGateFailed)
    assert isinstance(result.failing_invariants, tuple)
    with pytest.raises(AttributeError):
        result.failing_invariants.append(Invariant.PRIVILEGED_INTRODUCED)  # type: ignore[attr-defined]


def test_gate_registers_via_register_signal_kind() -> None:
    """ADR-0012 + Phase 5 ADR-0003: `@register_signal_kind(name="dockerfile_policy", isolation_class="none")`."""
    from codegenie.sandbox.gates.registry import signal_kind_registry
    assert "dockerfile_policy" in signal_kind_registry
    assert signal_kind_registry["dockerfile_policy"].isolation_class == "none"
```

State why it fails: `ModuleNotFoundError` — the gate module does not exist yet.

### Green — minimal pass

- Land `dockerfile_policy_gate.py` with the `Invariant` enum (six members), `DockerfilePolicyGatePassed` / `Failed` Pydantic models, and `DockerfilePolicyGate(Gate)` class decorated `@register_signal_kind(name="dockerfile_policy", isolation_class="none")`.
- Implement six pure predicate functions (one per invariant) iterated via the `_INVARIANT_PREDICATES` `Final` tuple.
- Land the per-invariant fail-fixtures + pass-fixtures under `tests/fixtures/recipes/dockerfile-policy-gate/`.

### Refactor

- Hoist each predicate into a documented pure function (`_check_user_nonroot(parsed: DockerfileParser, raw: str) -> bool`). Each carries a one-line docstring with the canonical citation (`ADR-0012 §Decision-§{n}`).
- Pin the `Invariant` enum's order — declaration order = `failing_invariants` tuple order. Document the no-reorder invariant in the enum's docstring.
- Add the CLI-help fence (`tests/fence/test_no_policy_override_flag.py`) and the source-tree grep.
- Confirm the audit-event flow integration test (`tests/integration/test_policy_gate_audit_trail.py`) is green.
- Confirm AST-walk purity fence is green.

## Files to touch

| Path | Why |
|---|---|
| `plugins/distroless-migration--node--npm/recipes/dockerfile_policy_gate.py` | NEW — `DockerfilePolicyGate(Gate)` + `Invariant` enum + `Passed`/`Failed` Pydantic models; `@register_signal_kind(name="dockerfile_policy", isolation_class="none")`. |
| `plugins/distroless-migration--node--npm/recipes/__init__.py` | Extend — additive import line for side-effect registration. |
| `tests/fixtures/recipes/dockerfile-policy-gate/pass/*.Dockerfile` | NEW — happy-path fixture (AC-9). |
| `tests/fixtures/recipes/dockerfile-policy-gate/fail/*.Dockerfile` | NEW — one fail fixture per invariant + the combinatorial fixture. |
| `tests/unit/gates/test_dockerfile_policy_gate.py` | NEW — AC-4..AC-9 + AC-12 suite. |
| `tests/fence/test_policy_gate_purity.py` | NEW — AST-walk rejects `subprocess` / `sandbox.client` / `exec.*` imports (AC-2). |
| `tests/fence/test_no_policy_override_flag.py` | NEW — CLI `--help` inspection + source-tree grep (AC-10). |
| `tests/integration/test_policy_gate_audit_trail.py` | NEW — typed event flows to spanning log (AC-13). |
| `tests/perf/test_dockerfile_policy_gate.py` | NEW — p99 ≤ 10 ms bench (AC-15). |

## Out of scope

- **`docker buildx build`** — `DistrolessBuildGate` (S10-04). This gate is pre-build; the build happens after the policy gate passes.
- **`ShellInvocationDeltaGate`** — S10-05. Different gate kind, different `isolation_class` (`microvm`).
- **CLI-level orchestration of the three gates** — the strict-AND `TrustScorer` from Phase 5 composes; this story ships the gate, not the orchestration.
- **Widening the invariant set** — adding a seventh invariant is a Phase-7-ADR amendment + a new `Invariant` enum value + a new predicate + a new fixture pair. Out of this story's scope.

## Notes for the implementer

- **ADR-0012 is the canonical citation. NO `--allow-policy-violations` flag.** This is the design decision; it is non-negotiable; AC-10 is the mechanical enforcement (CLI `--help` inspection + source-tree grep). If a future ticket asks for an override flag, the answer is "file an ADR amendment per ADR-0012 §Reversibility (Low)". The flag does not exist; it does not appear in `--help`; it does not appear in any config Pydantic; it does not appear in any env var. The policy lives in code.
- **Strict-AND is the only mode.** No thresholds. No "warning-only" mode. No "soft fail". Every invariant is hard-fail. If you find yourself adding a `severity: Literal["error", "warning"]` field to `Invariant`, stop — that contradicts ADR-0012 §Decision. Phase 5's strict-AND `TrustScorer` consumes pass/fail; there's no third state.
- **`isolation_class="none"` is load-bearing.** This gate is a pure function — it does NOT spawn a microVM. Compare S10-04's `DistrolessBuildGate` which is `isolation_class="microvm"`. The purity fence (AC-2) is the mechanical enforcement. If you reach for `SandboxClient.spawn(...)` here, stop — that's a different gate.
- **`failing_invariants: tuple[Invariant, ...]` — tuple, not list.** Pydantic v2 `frozen=True` does NOT freeze in-place mutation of `list` containers (see Phase 3 S1-04 V-D-F2 closure). Tuples are truly immutable. Validator coerces `list` input to `tuple` for YAML/JSON ingest. Same convention as `AttemptSummary.failing_signals`.
- **Deterministic ordering** of `failing_invariants` is by `Invariant` declaration order — NOT alphabetical, NOT input order, NOT first-fail order. Iterate `_INVARIANT_PREDICATES` (which is in declaration order) and append in that order. Test (AC-8) pins this.
- **Exhaustiveness via `match` + `assert_never`** — the strict-AND `TrustScorer` consumer must handle both `Passed` and `Failed` arms. Phase 5 ADR-0003 + Phase 3 ADR-0010 + production ADR-0033 (Domain modeling discipline) all converge here. Include `assert_never` import in any consumer module that `match`-es on the gate output.
- **Predicates are pure functions** — each takes `(parsed: DockerfileParser, raw: str) -> bool` and returns `True` if the invariant is upheld (passes), `False` if violated. Pure means: no `subprocess`, no `Path.read_text`, no module-level mutable state. Tested in isolation.
- **`dockerfile-parse` API.** Use `DockerfileParser(fileobj=io.StringIO(rendered))` (or equivalent). Walk `parser.structure` for `RUN`/`USER`/`CMD`/`ENTRYPOINT`/`HEALTHCHECK` instructions. Some invariants (e.g., `--cap-add`, `--privileged`, `--mount=type=secret`) live in `RUN` flag positions that `dockerfile-parse` may not extract directly — use regex over the raw `value` field for those. Document each predicate's parsing strategy in its docstring.
- **`USER nonroot`** — the canonical Chainguard non-root user is `nonroot` (uid 65532). Accept that, accept `USER 65532`, accept any non-`root` non-`0` value. Reject `USER root`, `USER 0`, missing `USER` directive (treat as `root` by Docker default).
- **`HEALTHCHECK` absent is acceptable** — only shell-form `HEALTHCHECK` is the violation; absence passes the invariant. Document this in the predicate.
- **Audit-event shape.** `DockerfilePolicyGateFailed(rendered_dockerfile_digest, failing_invariants)` — the digest is `hashlib.sha256(rendered.encode("utf-8")).hexdigest()` (deterministic; correlates with downstream events that reference the same diff). The spanning event log integration test (AC-13) asserts this digest matches between the gate event and the transform event.
- **Performance — ≤ 10 ms is easy.** `dockerfile-parse` is fast on small files; six O(N) walks over a parsed structure (N = number of instructions, typically < 50) is microseconds. The bench is a sanity check, not a hot-path optimization target.
- **Match Phase 5's `@register_signal_kind` precedent.** Phase 5 ships `@register_signal_kind("build")`, `@register_signal_kind("tests")`, etc. Phase 7's three gates follow the same shape. The decorator stores the class; instantiation happens at gate-run time. Don't pre-instantiate.
