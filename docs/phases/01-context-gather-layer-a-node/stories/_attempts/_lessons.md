# Phase 1 — Cross-story lessons learned

Append-only. Short, reusable takeaways the next story can apply.

---

## L-1 — Verbatim story examples may exceed line-length lint (S1-01)

When a story includes complete code examples (test bodies, class
definitions), the prose-style docstrings can exceed `ruff`'s 100-column
default. Phase 0 conventions (e.g., `ProbeBudgetExceeded`) wrap long
docstrings across 2–4 lines. Match the *Phase 0 wrapping pattern* rather
than the literal example formatting in the story file. The contract is
the substrings the docstring must contain (slug, hard-fail marker), not
the line breaks.

## L-2 — `make fence` fails locally but is green in CI (S1-01)

The local `make fence` target inherits pyproject's `--cov-fail-under=85`
addopt and trips on the 9-test fence subset. CI's fence job overrides
with `-o "addopts="`. Don't try to "fix" this from a story; it's
intentional Phase 0 plumbing. Validate with `make lint typecheck test`
plus `pytest tests/unit/test_pyproject_fence.py -o "addopts="` if needed.

## L-3 — Long ADR-path docstring references must wrap to 100 cols (S1-02)

ADR filenames in this repo run ~80 chars and the docstring reference
form (` - ``docs/phases/.../ADRs/0008-….md`` `) is ~105 — six chars
over `ruff`'s 100-col limit. Mirror the `errors.py` pattern: cite the
ADRs *directory* once, then list per-ADR filenames on continuation
lines (` - ``docs/.../ADRs/`` — ``0008-…``, ``0009-…`` `). The
contract is the substrings each docstring must contain (e.g.,
`adr-0008`, `adr-0009`); the wrapping is style.

## L-4 — TDD parametrize values are contract, not guidance (S1-02)

When a hardened story's TDD plan prescribes specific parametrize
values for a boundary AC (e.g., `[0, 1, 63, 64]` pass / `[65, 70,
200]` fail), those values *are* the boundary the AC ratifies. If the
green impl fails at a prescribed param, the impl is wrong — don't
relax the parametrize to fit the impl. Trace the depth/offset
semantic the story author had in mind, fix the walker, then keep the
story's parametrize verbatim. (Rule 9 — tests verify intent.)

## L-5 — Lift-into-shared-primitive may break tests pinning message text (S1-03)

When a story prescribes lifting an inline defense (e.g., O_NOFOLLOW +
size-cap I/O) into a shared `parsers/_io.py` / `parsers/_depth.py`
primitive, the *typed-exception* contract survives the move but the
*literal exception message* may not — the primitive's message format
becomes the new baseline. Downstream tests that pin
`"short read" in exc.args[0]` will fail. Resolution: relax to
type-only assertions (`pytest.raises(MalformedJSONError)`) where the
test's actual intent is "the right typed exception fires"; keep the
message check only when the message *content* is itself the contract
(e.g., AC asserts the path appears in `args[0]`). Rule 9: tests
verify intent, not implementation strings.

## L-6 — Story field-name values can drift from shipped convention (S1-03)

S1-03 AC-14 prescribed `cap_kind ∈ {"bytes","depth"}`; S1-02 shipped
`cap_kind="size"`. The implementer kept "size" (Rule 11 — match the
codebase) and surfaced the drift as a "Deviations" entry rather than
splitting the cap_kind vocabulary across two parsers. Lesson for the
next validator-and-executor cycle: when a hardened story's literal
field value disagrees with shipped code, the *intent* (a structured
discriminator) is the contract; the *spelling* is conventional. If
the divergence matters, surface it as a deviation in the attempt log
and propose a one-line story-file edit so the next story doesn't
re-litigate.

## L-7 — Hardened-story test snippets can have self-inconsistent payloads (S1-04)

The S1-04 story's TDD plan included
`test_well_balanced_5000_nested_block_comments_parses_under_1s` with the
payload `"{ " + "/* " * 5000 + '"k": 1 ' + " */" * 5000 + " }"` and the
assertion `assert out["k"] == 1`. Under the AC-13 nested-block-comment
contract the `"k": 1` token lives inside the comment block and gets
stripped to `{}` — no correct implementation can satisfy the assertion.
The story author's *intent* (AC-28: "5,000 well-balanced nested block
comments parse in < 1 s") is reachable by moving the payload outside
the comment block; the test's *literal* payload was wrong. Lesson for
the executor: a hardened test snippet is the contract for **what the
test verifies**, not the contract for **what the payload looks like** —
preserve the AC's intent and the asserted post-state; fix the input
shape when it logically contradicts itself. Surface as a deviation in
the attempt log and propose a one-line story-file edit so the next
re-read doesn't re-litigate. (Sibling to L-4: "TDD parametrize values
are contract, not guidance"; L-7 is the inverse — when the payload
itself is impossible, the *intent* is the contract.)

## L-S5-03a — Envelope wraps each probe slice under its own slice-name key (S5-03)

The CLI writer materializes `ProbeOutput.schema_slice` under
`envelope["probes"][probe_name]`, but each probe further wraps its slice
content under a *slice-name* key (`"deployment"`, `"build_system"`,
`"language_stack"`). Story AC text reading
`result.context["probes"]["deployment"]["exposed_ports"]` is wrong by
one layer; the shipped path is
`result.context["probes"]["deployment"]["deployment"]["exposed_ports"]`.
The slice-name wrap is intentional (envelope-level discriminator),
established at each probe's `schema_slice={"<slice_name>": ...}` literal.
Lesson for adversarial-story executors: before writing
`result.context["probes"][probe]["..."]`, grep `schema_slice=` in
`src/codegenie/probes/<probe>.py` — the top-level key in that dict
literal is the inner wrap name. Surface the AC drift as a deviation;
fix the test path; do NOT relax the AC's intent. (Rule 11.)

## L-S5-03b — `_has_kustomize` only detects root-level kustomization (S5-03)

`DeploymentProbe._has_kustomize` checks `root/kustomization.{yaml,yml}`
only. Stories prescribing nested fixtures
(`tmp_path / "k8s" / "kustomization.yaml"`) silently dispatch to
`_parse_raw` instead — the zip-slip defense is `_parse_kustomize`-only.
A nested-kustomization fixture passes the test for the wrong reason
(the defense never runs; the sentinel happens to be skipped because
`_parse_raw` walks well-known dirs without following `resources:`
references). Always anchor kustomization fixtures at the repo root for
zip-slip tests; mirror the S4-02 unit-test pattern at
`tests/unit/probes/test_deployment.py:349`.

## L-9 — `MappingProxyType` mutation API mix `TypeError` + `AttributeError` (S1-05)

`types.MappingProxyType` raises `TypeError` for `__setitem__` and
`__delitem__` but **`AttributeError`** for `.update`, `.pop`, `.clear`,
and `.setdefault` — those methods don't exist on the proxy at all.
Stories prescribing `TypeError` uniformly across all six mutation APIs
will see four of six tests fail at green-run. Resolution: widen the
test's `pytest.raises` to `(TypeError, AttributeError)` — both shapes
mean "mutation rejected", which is the AC's behavioral intent. Identical
shape to L-7: when the story's literal exception identity disagrees with
runtime reality, preserve the AC's behavioral contract; widen the
payload. Surface as a deviation in the attempt log so re-reads don't
re-litigate. (Rule 9: tests verify intent, not implementation strings.)

## L-10 — `typing.get_type_hints` returns fresh parametrized generics each call (S1-05)

`typing.get_type_hints(N)['x'] is tuple[str, ...]` returns **`False`**
even when `N` is `class N(NamedTuple): x: tuple[str, ...]`. Each
parameterized generic (`tuple[str, ...]`, `list[int]`, `dict[str, int]`)
is a fresh PEP-585 / 604 object created at evaluation time. Identity
comparison fails; equality (`==`) succeeds. When introspecting
annotations to drive runtime coercion (e.g., `list -> tuple` for
NamedTuple sequence fields), use `target == tuple[str, ...]`, never
`target is tuple[str, ...]`. Story author's intent (the coercion runs)
is the contract; the comparison operator is implementation detail.

## L-8 — Shared kernel modules can have hidden short-read silences (S1-04)

`parsers/_io.open_capped` returns `os.read(fd, size)` without verifying
`len(data) == size`. For `safe_json` and `safe_yaml` a truncated read
surfaces as `MalformedJSONError` / `MalformedYAMLError` via
`json.loads` / `yaml.load`'s own decode failure, which is "close
enough" to a typed error — S1-03's hardening explicitly relaxed the
safe_json short-read test to a type-only assertion. S1-04's AC-9
demanded the literal `"short read"` substring back. Two options:

1. Add short-read detection to `_io.open_capped` so all three parsers
   surface a uniform typed error. Changes existing parsers' observable
   error path; needs re-tightening their tests; potentially a new
   kernel-level marker.
2. Inline the open + cap + read + close in `jsonc.py` so it detects
   short reads itself. ~10 lines of duplication.

S1-04 picked option 2 (Rule 3: surgical changes; the story's
implementation outline showed inline code). Lesson: when a story's AC
requires a typed-error identity the shared kernel can't deliver,
inlining wins unless the kernel-refactor cost is bounded enough for
the same story. File the kernel-refactor as a follow-up.

## L-11 — Hardened stories are contracts; treat them as such (S1-06)

When `phase-story-validator` has produced a thorough hardening report and
pre-decided every contested call (file location of new types, the
`Any` vs `JSONValue` boundary call, where the sentinel test lives,
which TODO is preserved), the implementer's job collapses to mechanical
execution. **Do not re-litigate hardened decisions** — the validator
already weighed dependency-inversion, cycle risk, fence-widening cost,
and Open/Closed-at-file-boundary. Re-deriving these from scratch costs
attempt budget and may resurface defects the validator already fixed.
Read the validator report once, treat the story body as the contract,
and execute. Surface any *new* defect (one the validator didn't see) as
a deviation in the attempt log. (Sibling to L-4 / L-7: the story is
contract; the executor's judgment call is on payloads that contradict
themselves, not on architectural decisions the validator settled.)

## L-13 — Bound-method `id()` is unstable; identity tests must capture `__self__` (S1-07)

When a story's TDD plan prescribes `id(ctx.parsed_manifest)` (or any other
bound-method attribute) to pin sharing vs. isolation, recognize that Python
builds a *fresh* bound-method object on every attribute access — so
`id(memo.get) != id(memo.get)`, and a freshly-collected bound-method slot
may even be recycled across two distinct memos (yielding spurious
identity-equal). The load-bearing invariant is the *underlying instance*
identity, not the bound-method identity. Resolution: capture
`ctx.parsed_manifest.__self__` (the bound instance) and compare with
`is` / `is not`. Same shape as L-9: when the story's literal identity
assertion disagrees with Python's runtime model, preserve the behavioral
contract and widen the identity check. Surface as a deviation in the
attempt log so the next reader doesn't re-litigate. (Rule 9: tests verify
intent, not implementation strings.)

## L-14 — `FakeProbe.cache_key` short-circuits same-named probes across gathers (S1-07)

`FakeProbe.cache_key` in `tests/unit/_coordinator_fixtures.py` returns
`f"sha256:{self.name}"` — a name-keyed cache identity. Two `gather()` calls
on the *same repo* + *same FakeProbe name* hit the same `CacheStore`
entry, and the second gather short-circuits at the cache lookup before
`probe.run()` executes. For tests whose AC is "two gathers ⇒ two memos"
(AC-17), this collapses the captured-id list from length 2 to length 1.
Resolution: name the two probes distinctly per gather (e.g., `stub-a-1` /
`stub-a-2`) so the cache key differs and each gather goes through the full
dispatch path. The invariant under test is memo-instance identity per
gather, not cache behavior — the renaming is inert to the AC's intent.
Document inline so a future reader doesn't think the distinct names are
load-bearing. (Rule 9 — tests verify intent; the contract is "two memos",
the cache identity is incidental.)

## L-12 — `NamedTuple` > frozen-dataclass for value-keyed set membership (S1-06)

When a contract type's only requirement is to be a member of a
`frozenset` / `dict` key (hashable, value-equality, immutable), reach for
`typing.NamedTuple` before `@dataclass(frozen=True, eq=True)`. Why:

- Auto-hashable via inherited `tuple.__hash__`; no explicit `eq=True` /
  `frozen=True` decoration.
- Value-equality out of the box (`(a, b) == (a, b)` via tuple `__eq__`).
- `__slots__` for free → smaller per-instance memory.
- Picklable + slotted by default.
- One fewer place to drift a hashing convention.

Frozen-dataclass earns its keep when (a) defaults matter, (b) inheritance
matters, (c) `__post_init__` validation runs. None of those apply to a
`(path, mtime_ns, size, content_hash)` value tuple. Choose the shape
that matches the type's actual responsibilities — `NamedTuple` is a
smart constructor for an immutable value record. (Reinforces the design-
patterns lens: pick the narrowest pattern that fits.)

## L-15 — Closure adapters break `__self__` accessor (S1-08)

When a story replaces a bound-method seam on the runtime ctx
(`ctx.parsed_manifest = memo.get`) with a closure adapter
(`ctx.parsed_manifest = make_..._adapter(snapshot, memo)`), every existing
test that pokes through `ctx.parsed_manifest.__self__` to identify the
underlying instance silently breaks: the closure has no `__self__`. The
load-bearing invariant is the underlying instance identity (same memo
within a gather, different memos across), not the accessor name.

Resolution pattern: attach a labelled attribute to the closure
(`_adapter.__memo__ = memo`) and replace the existing accessor in the
test sites. Minimal diff; the instance-identity contract is preserved.
Reinforces L-13 — when the test's literal identity probe disagrees with
the new runtime structure, widen the probe to the underlying object,
not the surface accessor. Same idea, new surface.

## L-16 — Every new `probe.*` log event must pass `run_id=` explicitly (S1-08)

`structlog.testing.capture_logs` (used by every event-assertion test in
this codebase) skips the `merge_contextvars` processor — the ambient
`run_id` bound by `gather()` via `structlog.contextvars.bind_contextvars`
does NOT auto-attach to events at log time under test. The CLI module
calls this out at `src/codegenie/cli.py:579` ("Bind contextvars so child
events inherit `run_id`; ALSO pass it explicitly").

The contract for every new event-emitting site:

```python
run_id = structlog.contextvars.get_contextvars().get("run_id")
_logger.info("probe.foo.bar", probe=name, ..., run_id=run_id)
```

S1-08's three new events (`probe.input_snapshot.computed`,
`probe.input_snapshot.oversize`, `probe.input_snapshot.symlink_refused`)
all follow this contract. The lifecycle-event run-id-coverage test
(`tests/unit/test_coordinator.py::test_every_lifecycle_event_carries_run_id`)
is the integration-tier guard for this discipline — adding a new event
without the `run_id=` kwarg fails this test loudly.

## L-17 — `json.loads(bytes)` raises `UnicodeDecodeError` before `JSONDecodeError` (S1-09)

`json.loads(<bytes>)` auto-detects the encoding (utf-8 / utf-16) via the
stdlib `detect_encoding` helper and decodes the buffer BEFORE the JSON
tokenizer runs. When the input is bytes that aren't a valid encoding
under the detected codec (e.g., `b"\xff..."` autodetected as utf-8),
`json.loads` raises **`UnicodeDecodeError`**, not
`json.JSONDecodeError`. A `try/except json.JSONDecodeError:` block
that intends "parse-or-fallback" will let the `UnicodeDecodeError`
escape — surprising for callers reasoning from the documented exception
type only.

S1-09's `apply_raw_artifact_truncation` widens the catch to
`(json.JSONDecodeError, UnicodeDecodeError)` so the fallback
(`prefix.decode("utf-8", errors="replace")`) is reachable for invalid-
utf-8 prefixes. Rule 9 — tests verify intent: the AC says "non-JSON
prefix → replacement-char string"; the literal exception identity in
the story's outline was the implementation guidance, not the contract.
Same family as L-9 (`MappingProxyType` mutation API mixes `TypeError`
and `AttributeError`) — when the runtime exception identity is wider
than the story's literal, widen the catch and preserve the behavioral
intent.

## L-18 — Single-source-of-truth registry beats N module-local constants (S1-10)

When the same event-name literal appears as a module-local
`_EVENT_*: Final[str] = "probe.foo.bar"` in three separate modules,
plus as two raw `logger.info("probe.foo.baz", ...)` literals
elsewhere, the right structural fix is **lift to `codegenie.logging`
once** and have every emitter import the constant. Trade-off shape:

- **Before:** five edit sites if you rename the event string. Each
  module rediscovers the convention.
- **After:** one edit site in `logging.py` + a lightweight
  `Path.rglob` test (`tests/unit/test_no_event_literal_drift.py`)
  that pins zero literal redeclarations outside `logging.py`. The
  registry is now closed for modification, open for extension
  (Open/Closed at the file boundary).

The structural guard does not need to be AST-grade; `f'"{lit}"' in
text` catches every realistic regression. If false positives surface
in Phase 2+ (e.g., a legitimate test fixture needs the literal), the
test note tells the next reader to upgrade to an AST scan in S6-03's
adversarial sweep rather than weakening the discipline.

Generalization: when N modules each define a `Final[str]` for the same
string, the constants want to live in a registry module. Apply the
same lens whenever you spot module-local copies of a hard-coded
identifier (catalog kind, error code, lifecycle phase, etc.) — the
registry pattern catches drift early and turns a multi-file rename
into a one-file rename + a green CI gate.

## L-19 — `jsonschema` errors use **dotted** json_path, not JSON-Pointer (S2-01)

The project's `codegenie.schema.validator.validate(...)` re-raises
`jsonschema.ValidationError` with `err.json_path` in the message. That
`json_path` attribute is *not* RFC-6901 JSON Pointer (`/probes/foo`)
— it is `jsonschema`'s dotted/bracket form
(`$.probes.language_detection.language_stack`). Story drafts and ADRs
that say "JSON Pointer" are using the term loosely; the actual error
string is dotted.

- **Apply to:** any test that asserts on a slice path in a
  `SchemaValidationError` message. Match the dotted substring
  (`probes.language_detection.language_stack`) plus the rogue key.
- **Don't:** rewrite the validator to emit RFC-6901 pointers just to
  satisfy a story's wording (Rule 3 — surgical changes). The dotted
  form is what jsonschema gives us; preserve it.

## L-20 — A new required slice field breaks every strict-equality test across phases (S2-01)

When S2-01 added `framework_hints` and `monorepo` to the
`language_detection.schema.json` slice's `required` list, two
otherwise-unrelated test files failed (`tests/unit/test_language_detection_probe.py`
and `tests/unit/test_schema_validation.py`) because they asserted
`output.schema_slice == {"language_stack": {"counts": ..., "primary":
...}}` — a strict-equality form that breaks the moment the slice
grows.

- **Apply to:** any story that adds a required field to a probe slice
  or sub-schema. Before GREEN, `git grep -F 'language_stack' tests/`
  (substitute your slice's key) to enumerate every strict-equality
  site. Update them additively in the same commit — don't let the
  full suite be the discovery mechanism.
- **Why this hurts most when slices grow:** the strict equality test
  is the most natural way to encode "the Phase 0 shape" and the test
  was correct *at the time*. The brittleness only emerges when a
  later story extends the slice. The Phase 0 AC for the slice may say
  "exactly these keys" — re-read it; the right fix is usually to
  loosen the test to "these keys plus whatever later phases add"
  (subset assertion) rather than re-pin to the new shape every time.
- **For Phase 1 / S2-02..S4-04:** every probe slice that grows in
  later phases is going to hit this. Prefer subset assertions or
  per-key assertions in new tests; reserve strict equality for the
  smallest invariant (e.g., "the slice contains *exactly* these
  required keys at this moment", as an explicit shape contract).

## L-21 — `codegenie.exec.run_allowlisted` is `async def` (S2-02)

The allowlist subprocess wrapper is an `async def` (`src/codegenie/exec.py:175`),
not a sync function. Stories that prescribe `monkeypatch.setattr(codegenie.exec,
"run_allowlisted", lambda argv, **kw: SimpleNamespace(...))` are incorrect —
the probe must `await _exec.run_allowlisted(...)`, and awaiting a sync return
raises `TypeError`. The seam contract is still correct (monkeypatch the
attribute on `codegenie.exec`); only the stub shape needs to be awaitable —
`async def _stub(...)` returning the same `ProcessResult`-shaped object.

- **Apply to:** every Phase 1 / Phase 2 probe that invokes an allowlisted
  binary (S3-05, S4-01, S4-02, S5-01..S5-03, S6-01..S6-02, S7-09 …). Each
  story's test stubs need the `async def` shape, not a `lambda`.
- **Don't:** wrap the call in `asyncio.run` inside the probe to "make
  the test stub sync" — the probe is already inside an `async def`; introducing
  a nested event loop is wrong.

## L-22 — `run_allowlisted` exception surface is NOT the literal story set (S2-02)

The story for S2-02 named `(FileNotFoundError, TimeoutExpired, ExecError)` as
the "absent / timeout / exec-error" set for `node --version`. The **actual**
wrapper raises:

- `FileNotFoundError` — only when `cwd` doesn't exist (via `Path.resolve(strict=True)`)
- `ToolMissingError` — when the binary is missing from PATH
- `ProbeTimeoutError` — on timeout
- `DisallowedSubprocessError` — on allowlist miss

Non-zero exit is **not** an exception: the wrapper returns a `ProcessResult`
with `returncode != 0`, so the caller has to check `returncode` to treat it
as a failure. `subprocess.TimeoutExpired` is never raised by the wrapper.

- **Apply to:** any probe that catches "exec failed" — catch
  `(FileNotFoundError, ToolMissingError, ProbeTimeoutError,
  DisallowedSubprocessError)` plus a `returncode != 0` check. Don't import
  `subprocess.TimeoutExpired` unless calling `subprocess` directly (which
  the forbidden-patterns hook will block anyway).
- **Why this hurts:** a `except subprocess.TimeoutExpired:` arm next to the
  real wrapper is dead code; the test stub raising `TimeoutExpired` would
  pass while a real-world timeout (raising `ProbeTimeoutError`) would
  escape the probe and turn `node --version unreachable` into a probe failure.

## L-23 — `parser_kind` field needs a per-probe emit, not only the parser's cap event (S2-02)

`codegenie.parsers.jsonc` emits `parser_kind="jsonc"` only on
`probe.parser.cap_exceeded`. A normal (happy-path) parse logs nothing with
`parser_kind` at all. When a story's AC says "every parse-related log line
includes `parser_kind`", the **probe** must emit the anchor line (e.g.,
`_log.info("probe.tsconfig.parse", path=..., parser_kind="jsonc")`) per
parsed file. Relying on the parser alone leaves the happy path silent and a
`structlog.testing.capture_logs` test asserting `parser_kind` will fail.

- **Apply to:** every Phase 1 / Phase 2 probe that parses via `jsonc.load`
  / `safe_json.load` / `safe_yaml.load`. Emit a `probe.<probe>.parse` line
  per parsed file with the `parser_kind` and `path` fields.
- **Don't:** modify the parser to log on every parse — that pollutes happy
  paths uselessly in callers that don't care, and creates a chatty trace at
  cold-gather scale. The probe knows which slice the parse belongs to and is
  the right emit site.

## L-24 — `codegenie gather <fixture>` writes `.codegenie/` into the analyzed dir (S2-03)

Smoke-running the CLI against a fixture creates `.codegenie/cache/` and
`.codegenie/context/` *inside* the fixture tree (that's its on-disk output
namespace, per CLAUDE.md "Conventions to follow"). For a fixture whose
shape test enforces a closed-set invariant (AC-13 / AC-14 in S2-03), this
**will** dirty the fixture on first developer run and fail the very next
test invocation.

- **Apply to:** S2-05 (cache-hit-on-real-repo), S5-04 (`node_monorepo_turbo/`
  + `non_node_go/` fixture-shape stories), S5-05 (e2e). Any AC-style
  "run `gather` on the fixture as a smoke check" needs a follow-up
  cleanup step OR an `--output` redirect outside the fixture.
- **Don't:** add `.codegenie/` to the fixture's allowlist — it dirties the
  S6-01 golden and breaks the test-isolation invariant.
- **Why this matters:** the smoke check is a developer affordance (AC-22
  in S2-03), not a CI test; the real load-bearing assertions live in
  S2-04 / S2-05 / S5-05 where the temp-dir / `tmp_path` fixture isolates
  the output namespace.

## L-25 — Story slice-path ACs sometimes outdrift the schema (S2-04)

Hardened-story ACs for cross-probe integration tests can reference flat
slice paths (`probes.<name>.errors`, `probes.<name>.confidence`) that the
production schema actually nests one level deeper (`probes.<name>.<wrapper>.warnings`,
where `<wrapper>` is `language_stack` for LD and `build_system` for NBS).
ProbeOutput's `errors[]` / `warnings[]` / `confidence` aren't shallow-merged
into the envelope — only `schema_slice` is. Verify the assertion against the
**rendered envelope shape** (open one YAML before writing the test), not
the field names on `ProbeOutput`.

- **Apply to:** S2-05 (asserting cache-hit slice content), S5-05 (six-probe
  end-to-end), every future cross-probe integration test that consumes the
  envelope.
- **Workaround:** for "no silent degradation" intent, assert via captured
  structlog events — no `probe.failure` events for the probe under test,
  and the probe-emitted `probe.success` event (filter out the
  coordinator-emitted variant that carries `cache_key`) reports
  `confidence == "high"`.
- **Don't:** silently change the schema to flatten the slice — that's an
  ADR-amendable shape change, not an in-story fix. Adapt the test instead
  and document the deviation in the attempt log.

## L-26 — CLI seam `for_task(..., {"unknown"})` excludes language-filtered probes (S2-04)

Phase 0's `_seam_registry_for_task` calls `default_registry.for_task(
"__bullet_tracer__", frozenset({"unknown"}))` — but any probe declaring
`applies_to_languages = ["javascript", "typescript"]` (e.g., `NodeBuildSystemProbe`)
is filtered out at the seam *before* the coordinator runs the Wave-1
language-detection prelude. The coordinator's prelude pass produces
`enriched_snapshot.detected_languages`, but it dispatches the
probes-passed-in list as-is; the seam pre-filter is the wrong place to
gate language applicability.

- **Fix applied (S2-04):** seam returns `default_registry.all_probes()`;
  per-probe `applies()` / no-op-on-missing-inputs is the in-probe gate
  (e.g., NBS without `package.json` emits a minimal slice with
  `package_manager: null`). The coordinator's prelude + topological order
  remains the dispatch authority.
- **Apply to:** every future Phase 1+ probe with non-`["*"]`
  `applies_to_languages`. Phase 1's six Layer A probes (LD, NBS,
  NodeManifest, CI, Deployment, TestInventory) all dispatch through this
  seam.
- **Don't:** rebuild a two-pass seam that runs LD, reads detected
  languages, then re-queries `for_task` — the coordinator already owns the
  Wave-1/Wave-2 model (`phase-arch-design.md §"Control flow"`).

## L-27 — `node --version` cross-check is environment-dependent (S2-04)

`NodeBuildSystemProbe` runs `node --version` via the allowlist exec seam
and compares against the fixture's `.nvmrc`. When the dev/CI machine's
installed Node differs (dev: v25.x; CI ubuntu-24.04 default: v20.x.y), the
probe emits the soft `node.version_declared_resolved_disagree` warning —
correct behavior in production but a flake in tests that assert
"no warnings".

- **Apply to:** every Phase 1 integration test that asserts NBS warnings or
  confidence — S2-05, S5-05, S6-01 (golden regen).
- **Fix pattern:** module-locally rebind `codegenie.probes.node_build_system._exec`
  to a `types.SimpleNamespace` shim whose `run_allowlisted` raises
  `ToolMissingError`. The global `codegenie.exec` is never mutated. Helper:
  `_stub_node_version_check(monkeypatch)` in
  `tests/integration/probes/conftest.py`. Mirrors `_install_scandir_counter`
  from `tests/smoke/conftest.py` (L-14).
- **Don't:** monkeypatch `codegenie.exec.run_allowlisted` globally; that
  mutates the shared module and any test running in the same process that
  needs `git rev-parse` will lose its allowlist seam.

## L-28 — Fixture-immutability snapshots must exclude `<root>/.codegenie/` (S2-05)

Integration tests that run two successive gathers against the same fixture
and want a belt-and-suspenders "fixture inputs did not drift" invariant
need a `_stat_snapshot(root)` pre- and post-gather. The naive `rglob("*")`
walk includes `<root>/.codegenie/{cache,context,runs}` — the codegenie
output namespace, which the gather *legitimately* writes to on every
run. Without an exclusion filter, the invariant always fires (false-RED)
because `cache/index.jsonl`, `cache/blobs/<digest>.json`,
`context/repo-context.yaml`, and `context/runs/<run-id>.json` all
materialise after the cold gather.

- **Apply to:** every integration test that walks the fixture tree for
  drift detection — S2-05's two-probe cache-hit pair, future S5-05's
  six-probe extension, and any S6-* tests asserting fixture invariance.
- **Fix pattern:** in `_stat_snapshot(root)`, compute
  `output_ns = (root / ".codegenie").resolve()` and skip any
  `p` whose `p.resolve().parents` contains `output_ns`. Keys remain
  POSIX-form resolved strings (ADR-0002 macOS Path-equality foot-gun).
- **Don't:** rely on the cache-key byte-equality assertion alone — that
  proves the cache *key* is invariant under identical inputs, not that
  the fixture tree itself stayed put (a flaky filesystem or a
  background `.git` write would still produce a false-positive cache
  hit on warm). The two signals are complementary, not redundant.
- **Don't:** add a `time.sleep()` between gathers to mask mtime
  granularity — ADR-0002 routes cache keys through `content_hash`, not
  live `os.stat`, so there is no mtime-race to wait out. Sleep masks
  real bugs (a content-hash mismatch on identical bytes).


## L-29 — Story-prescribed YAML-alias-amplification fixture does NOT raise `DepthCapExceeded` (S3-01)

**Symptom (S3-01 GREEN):** The S3-01 story TDD plan prescribed a YAML
fixture of the shape

```yaml
a0: &a0 {x: 1}
a1: &a1 {x: *a0, y: *a0}
a2: &a2 {x: *a1, y: *a1}
...
a69: &a69 {x: *a68, y: *a68}
```

and asserted `_pnpm.parse(lockfile)` raises `DepthCapExceeded`. The
phase-story-validator hardening report doubled down on this shape as
"the canonical billion-laughs vector that the `id()`-memoized walker
catches as a logical-depth violation." Both wrong against the actual
walker implementation.

**Cause:** `parsers/_depth.py::_walk` is `id()`-memoized — once a
container is in `seen`, the walker returns without descending. The
loader builds all 70 anchor dicts as direct values of the top-level
mapping, so the walker visits them in insertion order: `a0` first
(scalar value `1`, no recursion), then `a1`..`a69` each at depth 1
with their `*a{i-1}` references already in `seen` (skipped). Max
walked depth = 2. `safe_yaml.load` returns the parsed mapping — no
`DepthCapExceeded` raised. Empirically confirmed by loading the
fixture under `parsers.safe_yaml.load(p, max_bytes=1MB, max_depth=64)`
and observing a successful return with 70 top-level keys.

The `id()` memoization is the **correct** defense per arch §"Edge
cases" row 1 (an alias chain of `k` physical nodes is walked in
`O(k)`, regardless of logical-expansion factor). What it does NOT do
is convert alias amplification into a depth-cap violation — it
prevents the depth from ever growing past the physical-DAG depth.

**Apply to:** every future lockfile-parser story (S3-02 `_npm`, S3-03
`_yarn`, any hypothetical `_bun`) whose AC names "re-raises
`DepthCapExceeded` unchanged from `safe_*.load`". The pass-through
test must use plain deep nesting — flow-style `{k: {k: ... v}}` × 70
matches the proven trigger in
`tests/unit/parsers/test_safe_yaml.py::_nest_dict(70)` (already shipping
in S1-03 and exercising the same `assert_max_depth` walker). The
alias-chain fixture is the right shape for `test_safe_yaml.py`'s
amplification-defense test (where the assertion is *successful parse
under bounded memory*), not for depth-cap re-raise tests.

**Don't:** repeat the alias-chain shape for any future
`DepthCapExceeded` re-raise test. Don't try to "fix" the walker to
raise on alias amplification — id() memoization is the load-bearing
defense; making it cap on logical depth would break arch §"Edge
cases" row 1's stated O(physical) guarantee.

**Carry forward to S3-02 / S3-03:** the depth-cap pass-through test
should reuse the `_nest_dict(70)` shape (or equivalent flow-style
deep nesting) verbatim. The story TDD plans for those stories likely
prescribe the same alias-chain shape (S3-01's plan was inherited
from the validator's S1-03-era reading of arch §"Edge cases"); the
implementer should substitute the deep-nesting fixture and cite L-29
in the attempt log.

## L-30 — Splitting an enum value forces a family-vs-variant comparison discipline (S2-02a)

When a single enum value (`"yarn"`) gets split into variants
(`"yarn-classic"` / `"yarn-berry"`), every existing code path that
compared *against* that value must be audited. The
`package_manager.declaration_lockfile_disagree` check in
`node_build_system.py` previously compared the declared `packageManager`
prefix (e.g. `"yarn"` from `"yarn@1.22.19"`) directly against the
resolved `package_manager`. Once variant detection runs, the resolved
value is `"yarn-classic"`/`"yarn-berry"` — so `"yarn" != "yarn-classic"`
would spuriously flag every legitimate yarn declaration as a
disagreement.

**Fix shape (the load-bearing pattern):** when comparing a declared
manager *family* against a resolved value that may be a *variant*, strip
the variant suffix before the equality check. In this codebase that's
`package_manager.split("-", 1)[0]`. A pinned regression test for *each
variant* + a *negative-control* test (a true cross-family disagreement
must still emit the warning) is the minimum coverage.

**Apply to:** any future enum splits in this codebase (e.g., if pnpm
ever forks into `pnpm-classic` / `pnpm-workspaces`, or if the npm
lockfile-version-6 vs -7+ distinction ever lands as separate enum
values in S3-05). The family-strip approach generalizes only if NO
package-manager family identifier itself contains a hyphen — currently
true; verify before extending.

**Don't:** add an `if package_manager.startswith("yarn-")` special-case
branch. The right shape is the family-strip, not a per-family branch
— it scales to N variants per family for free.

**Carry forward:** S3-03 (yarn lockfile parser) will need to *dispatch*
on variant (`yarn-classic` → `pyarn`; `yarn-berry` → `safe_yaml.load`).
That's a different operation (selection, not comparison) and should use
a small `Mapping[str, Parser]` with the variant strings as keys — no
family-strip needed, because dispatch is exact-match by design.

## L-31 — Use `structlog.testing.capture_logs()`, not ad-hoc `structlog.configure(...)`, in unit tests (S3-03)

For tests that capture structured-log events emitted by code under
test, use `structlog.testing.capture_logs()` as a context manager —
it swaps in a capture chain for the duration of the `with` block and
restores cleanly. Do **not** call `structlog.configure(processors=[...])`
inside a test. The codebase's default `PrintLogger` rejects
`event_dict` kwargs, so ad-hoc reconfiguration with a single
list-appending processor trips on the first structured event with
`TypeError: PrintLogger.msg() got an unexpected keyword argument …`.

**Apply to:** any future structured-event-surfacing test (S3-04
parity divergence events, S3-05 `NodeManifestProbe` warning events,
S4-* probe-lifecycle event capture, S5-* adversarial event capture).

**Don't:** copy/paste the `def capture(logger, method_name, event_dict)`
processor pattern from a story TDD plan into a test verbatim — it
looks idiomatic but breaks against `PrintLogger`. The capture-as-
context-manager pattern is the codebase precedent
(`tests/smoke/conftest.py`, `tests/unit/test_audit_anchors.py`,
`tests/unit/parsers/test_safe_yaml.py`).

**Carry forward:** the S3-03 story TDD plan itself prescribed the
broken processor-replacement pattern. If a future story copies that
TDD shape verbatim, swap to `structlog.testing.capture_logs()` first.

## L-32 — Land-time license check for conditional dependencies (S3-03)

When a phase ADR (e.g., ADR-0003) defers a dependency-adoption
decision to land-time and lists "no open CVE" + "release age" as
heuristic checks, **also verify license compatibility**. The
adopt-or-not heuristic in ADR-0003 omitted license; a real-world
adoption attempt of `pyarn 0.3.0` (GPLv3+) into a `Proprietary`
project is a hard blocker independent of release age or CVE state.

**Apply to:** every future "if maintained at land-time" ADR (ADR-0003
is the only Phase 1 instance; future phases may add more). The
land-time-decision-template ADR shape should include a license-
compatibility row alongside release-age and CVE-scan.

**Don't:** assume "permissively licensed" by default. Read the wheel
`METADATA`'s `Classifier: License :: ...` line; verify the project's
own `pyproject.toml -> license` field; reject incompatibilities loud
(Rule 12). The `_attempts/` log records the verified pyarn API
surface anyway so a future re-adoption (after upstream re-license or
own-project re-license) doesn't repeat the API verification work.

## L-33 — Property-based oracles ship parser bugs on first run (S3-04)

A property-based oracle derived from input bytes (not from the
parser's implementation) is load-bearing precisely because both
parsers can drift together. S3-04's oracle + parity tests landed on
the curated yarn corpus and immediately caught **two** real S3-03
bugs at first parametrize: (1) the hand-rolled scanner raised
`ValueError("no yarn.lock entries parsed")` on comments-only bodies
— the empty fixture pinned the zero-boundary on invariant 3; (2) the
hand-rolled scanner left embedded `", "` separators inside
multi-spec quoted entry-headers — the parity test caught a literal
key-string divergence from pyarn.

**Apply to:** every future parser story (npm package-lock, pnpm
lockfile, Helm chart manifests, etc.). The fixture-based parity test
is necessary but not sufficient — without a bytes-derived oracle,
two parser implementations that share a bug also share a green CI.

**Don't:** patch the oracle invariant to "tolerate" the bug. Per
S3-04's story-text Implementation-outline step 3 ("fix S3-03 — do
not relax the invariant"), bytes-derived invariants are immutable
contracts. If a future yarn-berry locator shape surfaces, add a new
anchor position to `_name_appears_anchored` — do not drop anchoring.

## L-34 — Optional dependencies belong in `mypy.overrides`, not per-line ignores (S3-04)

`# type: ignore[import-not-found]` works only when the optional
package is **uninstalled**. The instant it gets installed (S3-04's
parity-test sanity-check installed `pyarn` locally; CI's parity
matrix job will install it permanently), mypy switches to
`import-untyped` (no `py.typed` marker → still untyped, but the
package resolves). The per-line ignore flips between
`[import-not-found]` and `[import-untyped]` on every install-state
change, and the `[import-not-found,import-untyped]` tuple-form is
treated as a single unit, leaving an "unused" diagnostic on whichever
arm doesn't match.

**Apply to:** any conditional dependency (Phase 1 has `pyarn` only;
future phases may add SCIP/LSIF clients, container-build SDKs,
etc.). Use `[[tool.mypy.overrides]]` with `module = ["pkg", "pkg.*"]`
+ `ignore_missing_imports = true` — one declaration covers both
states.

**Don't:** rely on the per-line ignore round-tripping through
install-state changes. Don't add both ignores at once
(`# type: ignore[import-not-found,import-untyped]`); mypy's
unused-ignore logic flags whichever isn't currently triggering.

## L-35 — `cli`-side raw-artifact filename collides across probes (S3-06)

`cli.py` writes raw artifacts under `<output_dir>/raw/<basename>` where
basename = `raw_path.name` (the leaf of the path the probe emitted).
**Two probes can claim the same basename**: e.g., adding `[repo.root /
"pnpm-lock.yaml"]` to `NodeManifestProbe.raw_artifacts` would write
`.codegenie/context/raw/pnpm-lock.yaml`, which then matches
`NodeBuildSystemProbe`'s `declared_inputs = ["pnpm-lock.yaml", ...]` on
the next gather (because `declared_inputs_for` uses `rglob`, not
`glob` — L-36). Result: spurious cache invalidation on the warm run
for an unrelated probe.

**Apply to:** every future probe story that adds `raw_artifacts`
emission. Before landing, check that no basename in the probe's
emitted paths overlaps with any other probe's `declared_inputs`
globs.

**Don't:** add `raw_artifacts` emission piecemeal without a writer-side
namespacing pass. The fix shape lives in `cli.py` (namespace the
filename, e.g., `<probe>.<basename>`) or in `cache.keys.declared_inputs_for`
(exclude the `.codegenie/` output namespace from rglob) — not in the
probe code. Surface the gap and BLOCK on the writer/keys follow-up
rather than working around it from the probe.

## L-36 — `declared_inputs_for` uses `rglob`, not `glob` (S3-06)

`codegenie.cache.keys.declared_inputs_for` walks `snapshot.root.rglob(
pattern)` for every entry in `declared_inputs`. So a literal-looking
entry like `"pnpm-lock.yaml"` matches *every* `pnpm-lock.yaml` anywhere
in the repo tree — including cli-written artifacts under `.codegenie/`.
This bites because the glob *looks* like a literal filename, but it's
recursive.

**Apply to:** every cache-invalidation-scope test; every probe that
adds raw-artifact emission. Before reasoning about cache-key
stability, list `snapshot.root.rglob(pattern)` for every probe's
`declared_inputs` against the repo state you expect at each phase
(cold, warm, after-edit).

**Don't:** assume literal-looking declared_inputs entries match only
the top-level file. Always test "what happens when a sibling probe's
side effect drops a matching basename under `.codegenie/`."

## L-37 — Catalog-edit cache invalidation needs the catalog file in the fixture at the declared-input path (S3-06)

`NodeManifestProbe.declared_inputs` includes `"src/codegenie/catalogs/
native_modules.yaml"`. That pattern is matched against the repo root
via `rglob`, *not* against the codegenie install root. So a fixture
without that path has **zero catalog contribution to the cache key** —
the ADR-0006 cache-invalidation invariant cannot be exercised by
monkey-patching the in-process `_load_catalog` function.

**Apply to:** every test exercising catalog-edit cache invalidation
(S3-06 AC-7; future CIProvider catalog tests in Phase 2; replacement-
catalog tests in Phase 3). Seed the catalog file INTO the fixture at
the declared-input relative path; edit it there; re-gather.

**Don't:** monkey-patch `codegenie.catalogs._load_catalog` and expect
the cache key to change. The constants `NATIVE_MODULES` /
`NATIVE_MODULES_CATALOG_VERSION` are import-time singletons; they
affect the probe's *behavior* but not the cache-key *fingerprint*
(which goes through `declared_inputs_for` → file content hash).

## L-38 — `pytest-mock` is not in dev extras; inline a `_CallCounter` for spy-style tests (S3-06)

Stories prescribing `mocker.spy(target, "attr")` fail collection with
"fixture 'mocker' not found" because pytest-mock is not in
`pyproject.toml`'s dev extras. The shipped equivalent is a 6-line
`_CallCounter` (counts calls + delegates to wrapped) +
`monkeypatch.setattr(target, attr, counter)`. Same behavioral
contract — call-count + call-through — different spelling.

**Apply to:** every future story whose TDD plan prescribes
`mocker.spy`. Inline the helper in the test file; do NOT add
pytest-mock to the dev extras to satisfy a story spelling (Rule 11 —
match the codebase, including the *absence* of a dependency).

**Don't:** copy-paste `mocker.spy(...)` from the story TDD plan
verbatim. The spy *behavior* (observable distinct call paths) is the
AC contract; the *fixture name* is conventional.

## L-42 — `BudgetingContext` is the runtime context, not `ProbeContext` (S4-01)

The probe ABC's `ProbeContext` dataclass (in `src/codegenie/probes/base.py`)
declares `cache_dir`, `output_dir`, `workspace`, `logger`, `config`,
`parsed_manifest`, `input_snapshot`. The runtime per-dispatch object the
coordinator constructs is `BudgetingContext` (in `src/codegenie/coordinator/budget.py`)
which exposes only `workspace`, `raw_artifact_mb`, `bytes_written`,
`parsed_manifest`, `input_snapshot`, `report_bytes`. A probe that touches
`ctx.output_dir`, `ctx.cache_dir`, or `ctx.logger` will pass unit tests
(which build the full ABC dataclass) but `AttributeError` at runtime.

**Apply to:** every new probe. Until the ABC and runtime context are
reconciled, write raw artifacts under
`ctx.workspace / ".codegenie" / "_probe_raw" / <name>.json` — the
`.codegenie/` namespace is already excluded from fingerprinting (L-39).

**Don't:** copy `ctx.output_dir` from the ABC docstring without a
runtime smoke test. The dataclass surface is aspirational; the
runtime surface is `BudgetingContext`.

## L-43 — Field names that match `SECRET_FIELD_PATTERN` need an explicit allowlist (S4-01)

Phase-0 ADR-0008 + ADR-0010 install a defense-in-depth regex
(`(?i)^.*(secret|token|password|credential|api[_-]?key|...)[..].*$`)
against any dict key in a `ProbeOutput.schema_slice`. The CISlice
contract names `references_secrets: list[str]` — by construction a list
of literal identifier names (production ADR-0005: probe never resolves a
value). Without an exemption the slice cannot ship.

**Apply to:** any future probe whose data model contains a field name
mandated by the architecture and matching the secret-shape regex. Add
the exact name to `SECRET_FIELD_ALLOWLIST` (in
`src/codegenie/coordinator/validator.py`) and write a fresh phase ADR
naming the construction-time guarantee that makes the values safe
(precedent: ADR-0014, S4-01).

**Don't:** rename the field behind the contract's back; don't loosen
the regex to add word boundaries (that narrows the defense for every
other field). The allowlist is exact-equality only; substring matches
still raise (anchored by a regression test).

## L-44 — Strict `jobs.*.steps[].run` walkers are too narrow for cross-cutting regex coverage (S4-01)

`_extract_run_strings(workflow)` walks `jobs.*.steps[].run` only — that
strictness is load-bearing for AC-25's `_IMAGE_BUILD_MARKERS` `run` vs
`uses` discriminator (`docker/build-push-action` is `uses:`-shaped, not
`run:`-shaped — conflating them flips the AC). But test fixtures
sometimes ship valid YAML that doesn't match the GHA shape (bare
`steps:` without a `jobs:` wrapper), and secrets references can appear
under any key (`env:`, `with:`, top-level expressions).

**Apply to:** any probe that needs a strict-shape walker (for a
specific contract) AND a cross-cutting regex coverage (for a security
or facts-not-judgments invariant). Keep both. Route the strict walker
to its consumer; route the depth-walker (`_collect_string_values`) to
the regex consumer.

**Don't:** widen the strict walker to "all strings" — that breaks the
discriminator the strict consumer needs.

## L-45 — Glob-then-partition beats two glob passes for same-prefix file families (S4-02)

When a file family shares a common prefix but two name shapes need to
be distinguished (Helm baseline `values.yaml` vs. env overlays
`values-prod.yaml` vs. non-conformant `values.prod.yaml`), one wider
glob (`values*.yaml`) plus a post-filter partition by exact name beats
two separate globs (`values.yaml` exact + `values-*.yaml` glob). The
narrower glob silently drops the non-conformant variant the AC
actually requires (S4-02 AC-15 prescribes `values.prod.yaml` →
`environments[0].name == "values.prod"` with the
`helm.values_filename_unrecognized` warning). The wider glob makes
the non-conformant case observable to the conformance check.

**Apply to:** any future probe that processes a file family with a
shared prefix and a "canonical / non-canonical" distinction. Examples:
GitHub Actions composite-action paths (`action.yml` vs.
`action-*.yml`), Kustomize component overlays (`patch.yaml` vs.
`patch-*.yaml`), Pyproject overlay variants. Glob wide; classify
in code; emit conformance warning in the same site.

**Don't:** narrow the glob to "the canonical shape" hoping the
non-canonical case is rare — once an AC pins the non-canonical
behavior the narrow glob is a silent bug. The conformance warning
(ADR-0007) is the correct vehicle, not glob-as-filter.

## L-46 — Cap counters need to advance on the gating event, not on the success event (S4-02)

`_walk_overlays` originally counted resource entries against
`max_files` only when the entry resolved to an existing on-disk file.
A hostile (or broken) `kustomization.yaml` listing 60 non-existent
resource paths would never trip the file-cap warning because the
counter advanced only on the `resolved.is_file()` branch.

The gating event is "resource entry was declared in kustomization
yaml AND passed zip-slip containment" — not "resource resolved to a
real file." The latter is a workload-layer concern; the former is
the declared-inputs cap the AC pins.

**Apply to:** every cap test in this codebase. Verify the counter
advances on the *declaration* event, not on the *success* event.
The TDD fixture for AC-26 creates the kustomization but not the
resources — that’s deliberate; the cap should fire regardless.

**Don't:** count "successfully processed payloads" against caps
intended to bound "declared inputs." The two are different
invariants and conflating them lets adversarial inputs bypass the
cap by supplying paths that fail later.

## L-47 — Default-arg values bind at function definition; use a sentinel for monkeypatchable module constants (S4-03)

`_lcov_scanner.scan(path, *, max_bytes: int = _LCOV_MAX_BYTES)`
captured `50 * 1024 * 1024` at function-def time, so a test that
ran `monkeypatch.setattr(_lcov_scanner, "_LCOV_MAX_BYTES", 16)` and
then called `scan(p)` (no override) saw the original 50 MB cap and
did NOT raise `SizeCapExceeded`.

Switch to a `None` sentinel + module-level lookup at call time:

```python
def scan(path, *, max_bytes: int | None = None) -> LcovTotals:
    effective_cap = _LCOV_MAX_BYTES if max_bytes is None else max_bytes
    body = open_capped(path, max_bytes=effective_cap, parser_kind="lcov")
```

**Apply to:** any module-level constant that doubles as a tunable
default for an external API and a monkeypatchable value in tests.
Sentinel-then-lookup keeps the public default discoverable AND
testable; the bare default-arg form makes the value silently
test-resistant.

**Don't:** ship a default-arg-bound module constant unless you also
ban monkeypatching it in tests. The two use-cases collide; the
sentinel pattern reconciles them.

## L-48 — Strict-by-enumeration beats `additionalProperties: <subschema>` for closed-set object fields (S4-03)

`commands` was first written as `{"type": "object", "additionalProperties": {"type": "string"}}` —
i.e., "an open object whose values must be strings." That fails the
walk-every-object `additionalProperties: false` invariant (AC-45).
The probe already enforces the closed canonical-name set in
`_extract_canonical_scripts`, so the schema can mirror it:

```json
"commands": {
  "type": "object",
  "additionalProperties": false,
  "properties": {"test": {"type": "string"}, "test:unit": {...}, ...}
}
```

Now schema validation rejects non-canonical script names AT the
envelope layer, not just at the probe layer (defense in depth).
Adding a future canonical script name is one tuple entry +
one schema property + one fixture row.

**Apply to:** any object field whose key set is closed by the
producer. Enumerating the keys + `additionalProperties: false`
gives schema-level defense in depth on top of producer-level
filtering.

**Don't:** use `additionalProperties: <subschema>` (the
value-validation form) for closed-key object fields just because
"the values are all strings." That syntax means "any key is
allowed if its value validates," which is the opposite of what
a closed-key field needs.

---

## S4-04 — `coverage.json` summary field naming (real vs synthetic)

**Lesson:** When a script reads JSON emitted by `coverage.py`'s
`--cov-report=json`, **branch coverage lives under
`percent_branches_covered`** in the per-file `summary` dict, **not**
`percent_covered_branch`. The line key (`percent_covered`) is symmetric
across both real and "expected" naming; the branch key is asymmetric.

**Why:** S4-04's synthetic test fixtures used `percent_covered_branch`
intuitively. The script silently read 0% for every real input until
the real `coverage.json` was inspected. If the script had been
deployed without an end-to-end run, every probe would have failed the
carve-out check at every CI run regardless of actual coverage —
exactly the Rule 12 "fail loud" violation S4-04 was designed to
prevent.

**Action:** When writing a verifier that consumes a tool's structured
output, inspect at least one real artifact before committing the
field-access paths. Inline alias-tolerance is cheap (`.get(real,
.get(alias, default))`) and useful when the test harness predates the
field check.

---

## S4-04 — When an old test pins a contract a new ADR overrides

**Lesson:** If a Phase 0 test pins a comment string that a Phase 1
ADR (e.g., ADR-0005) explicitly rewrites, the test must be updated in
the same PR that rewrites the comment. Rule 7 (surface conflicts,
don't average them) — keeping both means either the comment drifts
back or the test silently averages two contradictory rules.

**Why:** S4-04 ACs said "PR diff is *only* this story's files" *and*
"rewrite the stale `87/77` comment". Both cannot be true if a test
already pins `87/77`. Surfacing the necessary test update in the
attempt log + commit message + PR description is the only honest
resolution.

**Action:** Before declaring a story's AC-list internally consistent,
`grep` the test suite for *the prior contract's substrings* — any
hit is an implicit dependency the story spec missed.

## L-? — Probe-handler retrofits must cover *every* call-site of the new exception, not just the two the validator named (S5-01)

When a story prescribes a "retrofit on probes A and B for new
exception E", the validator may only audit those two probes — but
the codebase usually has more call-sites that need the symmetric
edit. S5-01 retrofitted `DepthCapExceeded` on `language_detection`
and `node_manifest` per AC-12; **the gather-level test `exit_code == 0`
asserts forced the discovery that `node_build_system` and
`test_inventory` ALSO read `package.json` and ALSO needed the
catch-tuple edit**. Without those, the unhandled `DepthCapExceeded`
crashes the prelude and the gather degrades to `outcome=schema_invalid`.

**Why:** AC-12's "two-line edits per probe" reads tight on the
specific probes named — but the underlying contract is "every
probe that calls `safe_json.load` on `package.json` must catch
`DepthCapExceeded`." That's an exhaustive statement over the
**full** set of call-sites, not just the two named.

**Action:** When validating a retrofit story, grep for `safe_json.load`
(or the relevant entry point) across `src/codegenie/probes/` and
confirm the AC covers every match. If the count > the named probes,
either widen the AC or flag the gap pre-execution.

## L-? — Envelope shape ≠ slice shape ≠ `ProbeOutput` shape (S5-01)

The story's AC text used the path `result.context["probes"][probe]["errors"]`
and `["confidence"]`. Neither exists at that level: errors live
**inside the slice** at varying paths (`["manifests"]["errors"]` for
`node_manifest`; not surfaced at all for `language_detection`),
and `confidence` is **never** in the envelope — it's on
`ProbeOutput` and consumed by the coordinator. The slice schemas
declare `errors`/`warnings` forward-compatibly but Phase 1 emits
typed-exception IDs on `ProbeOutput.errors`, **not** in the slice.

**Why:** The envelope contract is "shallow-merge each output's
`schema_slice` into `envelope["probes"][name]`" (see
`cli._seam_shallow_merge`). Nothing else. Authors of CLI-level
assertions need to walk the slice schema for each probe rather
than assuming a uniform `[name]["errors"]` / `[name]["confidence"]`
shape.

**Action:** For any new gather-level assertion against per-probe
state: open the probe's slice schema first, locate where `errors`
lives (or whether the probe emits them at the slice level at all),
and write the test against the **actual** path. For state not
surfaced in the slice (`confidence`, anything else on `ProbeOutput`),
verify at the unit-test boundary instead.

## L-? — Python's stdlib `json` scanner is recursive; depth fixtures cap at ~500–800 frames (S5-01)

CPython 3.13's `json` C extension exposes `make_scanner` whose object
decoder bottoms out through a Python-level `raw_decode → scan_once`
loop. Default recursion limit is 1000; in pytest contexts the
runway is closer to 500–800 frames. A "10,000-deep package.json"
test as the story prescribed hits `RecursionError` before
`DepthCapExceeded`, masking the actual structural defense.

**Why:** Depth-cap tests need a fixture deeper than the cap they're
probing but shallower than Python's recursion ceiling. With
`max_depth=64` and a pytest stack ~150 frames deep on entry, `200`
is the comfortable middle (5× the cap, well under the ceiling).

**Action:** When sizing a depth-bomb fixture, treat the integer
in the story as a target order of magnitude. Use the smallest
value that comfortably exceeds the cap; document the deviation
inline in the builder's docstring so the next reader doesn't try
to "fix" it back to the story's literal number.

## L-? — Tests-only stories should not pre-emptively edit production code (S5-02)

When a HARDENED story's `Files to touch` table contains only test
files and the validation block explicitly states "production code
already correct, this is a permanent-fixture pin," trust it. The S5-02
green pass landed 5 tests with **zero** production-code changes —
every defense the tests target was already in place from S1-03
(`CSafeLoader`), S2-04 (`run_allowlisted` + `_is_sensitive`), and
S3-03 (`_yarn._parse_handrolled`). Verify the test passes by *running*
it, not by editing production code to "make sure" — Rule 3 (surgical
changes) holds harder when the validator's block has already audited
the production surface.

**Action:** When the story says tests-only, run the tests first; if
they pass on the first try, that is the expected outcome, not a
suspicious sign. Skip to the validator pass; do not pre-emptively
"refactor" or "improve" production code.

## L-? — `SENTINEL_FILE` belongs in `env_extra`, not `monkeypatch.setenv` (S5-02)

The `exec.run_allowlisted` chokepoint builds the child env by *inclusion*
of `{PATH, HOME, LANG, LC_ALL}` plus sanitized `env_extra`. The parent
`os.environ` is **never copied** — so `monkeypatch.setenv("SENTINEL_FILE",
...)` is structurally invisible to any child. The S5-02 validator
caught the original draft's broken sentinel-file plumbing for this
reason.

**Action:** When a test needs an out-of-band communication channel from
a real subprocess back to the parent, pass the channel's path through
`env_extra`. The same rule applies to a `PATH` override (prepend the
shim dir via `env_extra["PATH"]`, not `monkeypatch.setenv("PATH", ...)`).


## L-? — Story ACs may presuppose architecture that does not yet exist (S5-05)

S5-05's AC-NN-3 ("the three Node-only probes are ABSENT on a non-Node
repo") read like a contract test, but the per-probe
`applies_to_languages` filter that would have made it true did not
exist on disk — all six Phase-1 probes declared `tier = "base"` and
ran concurrently against the original (empty) snapshot, so the filter
never engaged. The probes ran, produced empty no-evidence slices, and
were *present* with `type: "none"` shapes (not absent).

The fix was architectural: move `node_build_system` /
`node_manifest` / `test_inventory` to `tier = "task_specific"`, add a
pure `_admits_node_project` predicate (with a `package.json`-at-root
fallback to keep greenfield Node repos working when LD finds no
source files), override `applies()` in the three probes to consult
it, and update three unit tests that pin `tier == "base"`.

**Action:** When a story's ACs read like contract tests that the
current architecture cannot satisfy, surface the gap explicitly. The
story's implementer-notes anticipated 1–3 small probe follow-ups;
expect at least one of them to be a small architectural fix rather
than a probe edit. Prefer hexagonal/Open-Closed solutions (a pure
predicate in a dedicated module) over leaking probe-specific
knowledge into the coordinator.

## L-? — A failure-isolated probe must NOT pollute `envelope.probes[<name>]` (S5-05)

`coordinator._build_failure_output` returns a `ProbeOutput` with
`schema_slice = {}`. `_seam_shallow_merge` historically wrote that
empty dict to `envelope.probes[<probe>]`, which violates the
per-probe sub-schema's `required: ["<slice>"]` contract and
surfaces as a misleading `exit_code=3 schema_invalid` outcome that
masks the real failure.

**Action:** Per ADR-0010 "Layer A slices optional at envelope", the
seam now `continue`s on empty `schema_slice`. The failure is still
visible via the audit run-record's `exit_status = "error"` row —
that is the right place for it, not the envelope.
