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
