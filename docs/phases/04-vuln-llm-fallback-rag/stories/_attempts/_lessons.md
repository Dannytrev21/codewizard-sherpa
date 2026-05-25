# Cross-story lessons — Phase 04

Append-only. Add short lessons that reduce risk for later stories.

## L-1 — Shared identifier catalog exact-set tests must move with `__all__` (S1-01)

Adding a new identifier to `src/codegenie/types/identifiers.py` is a three-site
kernel change: the `NewType` declaration, `__all__`, and `_NEWTYPE_REGISTRY`.
The existing `tests/unit/types/test_identifiers_phase3.py` exact-set and
registry tests are intentionally shared across phases; future identifier stories
should extend that roster in the same commit rather than adding a phase-local
duplicate assertion.

## L-2 — Local macOS full-suite timing can fail outside story scope (S1-01)

`tests/adv/test_tsconfig_pathological.py::test_gather_under_pathological_tsconfig_silently_swallows_under_two_seconds`
is a wall-clock test around the full gather CLI. During S1-01 it failed
reproducibly on local macOS at 2.06-2.65s against a 2.0s cap while the focused
story gates were green and latest `master` CI had passed. Treat this as a
separate timing-flake/performance triage item unless CI reproduces it.

## L-3 — Verbatim TDD-plan snippets aren't always runnable — verify `textwrap.dedent` indentation when generating multi-line code under `match` (S1-02)

The TDD-plan snippet for the mypy-exhaustiveness meta-test interpolated
generated `case` arms into a `textwrap.dedent`-wrapped template; the arms
emitted 8 leading spaces and the surrounding template lines also had 8
leading spaces, so `dedent` stripped 8 from everything — including the
arms — collapsing the `case` lines to column 0 *underneath* a `match p:`
sitting at column 4. mypy reported a `[syntax]` error instead of the
intended exhaustiveness diagnostic, and the F4 assertion fired correctly
("mypy failed but not for an exhaustiveness reason"). Fix: emit arms at 16
leading spaces so dedent leaves them at column 8, matching the catch-all
arm. Future stories generating code under indented blocks via `dedent`
should sanity-print the rendered source once before asserting on mypy
output.

## L-5 — Shared utilities used by two leaf packages must live in the kernel (S1-04)

A reusable validator / type alias shared between `codegenie.rag.models` and
`codegenie.fallback.budget` cannot live in either leaf package — the
`fallback/__init__.py` re-export side-effect creates a transient cycle
(`rag.models` → `fallback.plan_proposal` → `fallback/__init__.py` →
`fallback.budget` → `rag.models`) that mypy does NOT catch but pytest
collection breaks on at runtime. The canonical home is
`codegenie.types/<tiny module>.py` — same precedent as `PackageManager`
moving to `codegenie.types.identifiers` (ADR-0013 Amendment 2026-05-20).
The reverse direction (kernel imports leaf) is forbidden by `import-linter`.

## L-4 — Local `lint-imports` console script is not on the system PATH by default (Phase 4)

`tests/unit/test_lint_imports_canary.py` resolves the `lint-imports` binary
via `shutil.which`, which scans `$PATH` only — not the active venv's `bin/`.
On a default macOS shell where the venv isn't sourced, the canary fails with
`AssertionError: lint-imports console script must be on PATH`. CI passes
because the GitHub Actions runner sources the venv. To reproduce CI locally,
run `PATH="$PWD/.venv/bin:$PATH" pytest …` — or `source .venv/bin/activate`.
This is the same root cause as the macOS-runner-vs-CI drift in L-2: treat
PATH-resolution failures as environment hygiene, not regressions.

## L-5 — Two same-named classes in two import spaces is a smell — pick distinct names early (Phase 4)

S2-02 names both the `CanaryResult` sum-variant *and* the event class
`CanaryCollision`. The validator hardened both ACs without flagging the
collision. At Stage-2 implementation time, importing both classes into a
single test module is structurally impossible. The fix is small but
load-bearing: rename the event to `CanaryCollisionEvent`, keep the
on-the-wire discriminator value (`canary_collision`) intact so the story's
AC-12 wire contract still holds. When two layers naturally want the same
name, prefer suffixing the *outer* (event/wrapper) class and leaving the
*inner* (model/variant) class with the bare name — keeps the rename
reversible if the story author wants the bare name on the event later.

## L-6 — A Hypothesis property that depends on an unguessable secret must construct that secret in the strategy (Phase 4)

S2-02 AC-8 says "the close-delimiter never appears in fenced content." A
bare `@given(payload=st.text())` strategy *passes vacuously* against an
implementation that does no in-body delimiter check at all — the 32-hex
nonce is unguessable at 2⁻¹²⁸. The validator caught this. The lesson
generalises: any property of the form "`SECRET not in output`" where
`SECRET` is a per-call random value needs the strategy to draw `SECRET`
itself and embed it in the input — otherwise the strategy is structurally
unable to reach the violation. Same applies to capability tokens,
session IDs, BLAKE3 hashes, anything keyed on a per-call random.

## L-7 — A `# type: ignore[<code>]` on the call site under test silently nullifies the gate (S3-01)

S2-05 shipped `tests/fixtures/typecheck/budget_token_missing.py` with
`# type: ignore[call-arg]` on the very `leaf.invoke(...)` call whose
missing-keyword-argument diagnostic the gate asserts on. While S3-01
hadn't landed, `pytest.importorskip` skipped the test cleanly and
nobody noticed. The moment S3-01 turned the gate live, `mypy --strict`
exited 0 — exactly the regression the gate exists to catch — because
the `[call-arg]` suppression hid it. Lesson: a fixture asserting "mypy
errors with diagnostic X" must NEVER suppress X inline. Suppress the
expected *noise* (placeholder values, unrelated arg-types) but leave
the diagnostic-under-test surfaced. Reviewer heuristic: any
`# type: ignore[<code>]` on the call line a fence test asserts on is a
red flag — the suppression turns the gate into a tautology.

## L-9 — Async httpx bypasses `socket.create_connection` — wrapper is a sync-path defense only (S3-03)

S3-03 AC-18 prose claims `httpx` "ultimately funnels through
`socket.create_connection`". That is only true for **sync** httpx (and
for stdlib `urllib`/`urllib3`). Async httpx delegates to
`asyncio.BaseEventLoop.create_connection` → `loop.sock_connect` on a
raw socket — the `EgressGuard` wrapper does not see it. The Phase-4
adapter's async SDK call inside `AnthropicLeafAdapter` is defended by
the explicit `egress_guard.pinned_to(...)` envelope (the suspenders),
not by the socket wrapper (the belt). Future stories that need to
close the asyncio gap should hook either `asyncio.BaseEventLoop._sock_connect`
or the underlying `socket.socket.connect` (with an IP-allowlist cache
populated by a wrapped `getaddrinfo`). For now, split any "SDK does
not bypass" AC into a sync-client test (genuine wrapper proof) plus a
structural pin of the residual asyncio surface, so a future closure
updates the assertion deliberately rather than letting the gap widen
silently.

## L-10 — `isinstance(x, dict)` fails on third-party `MutableMapping`-only subclasses; use `Mapping` (S3-04)

vcrpy's `HeadersDict` is a `CaseInsensitiveDict` (`MutableMapping`)
subclass but **not** a `dict` subclass. My first-pass
`_normalize_headers` used `isinstance(headers, dict)` and fell through
to the stringify fallback for real `vcr.request.Request` objects —
mangling the whole headers object into one `(repr_string, "")` row.
The unit-shim tests (plain `dict`) passed; only the integration test
against the real type caught the bug. Lesson: when accepting "container
of headers" from a third-party library, type-check against `Mapping`
(or `Iterable[tuple[K, V]]` for the pair-list shape) — `dict` is the
wrong contract because container-type subclassing is library-author's
choice, not the protocol. Same applies to bytes-or-bytearray vs
`bytes`, `Sequence` vs `list`, etc. The integration test that uses the
real third-party type is load-bearing — a dict shim cannot expose this
class of bug.

## L-8 — Reconcile cross-story module-name drafts before the gate flips (S3-01)

S2-05 named the gated-on module `codegenie.fallback.leaf.protocol`;
S3-01 (the contract owner — AC-1 names `port.py`) settled on
`codegenie.fallback.leaf.port`. When the S2-05 gate was written its
target module did not exist yet, so any name "looked correct enough."
When S3-01 GREENed under the canonical name, the `importorskip`
silently kept the test skipped (no error — the path just does not
resolve), defeating the gate's purpose. The S3-01 validator had
already flagged AC-10 for the same class of bug (pointing at a
not-yet-existent sibling test). General rule: "gated-on-next-story"
tests must pin the module path to the *next story's canonical
surface*, not a draft name; the next-story executor's first job is
to re-grep the gating-test for its module path and reconcile it
before declaring GREEN.

## L-11 — The Phase-4 raw-`str` fence treats function-name substrings as domain IDs (S3-05)

`tests/fence/test_phase4_no_raw_str_for_domain_ids.py` walks
`src/codegenie/fallback/` + `src/codegenie/rag/` and flags any
**function** whose name contains a domain keyword (`cassette`,
`cve_id`, `budget_token`, `chain_head`, `nonce`, …) and whose return
annotation is a raw primitive. So `def compute_cassette_digest(...) ->
str` is a fence break — the name carries the domain identity.
Use the existing newtype from
`codegenie.types.identifiers` (here: `BlobDigest`, the
algorithm-agnostic 64-hex digest type the whole repo reuses) rather
than inventing a parallel `CassetteDigest`. The fence applies to
parameter names too — but those usually take `Path`-shaped types, so
breaks land more often on returns.

## L-12 — Local pre-commit hooks backed by a CLI need fence-aware entries (S3-05)

`tests/unit/test_precommit_and_docs_config.py::test_precommit_config_declares_exactly_the_required_hooks`
asserts every `repo: local` hook either points at a real script file
or contains the literal `grep`. A CLI-driven hook
(`python -m codegenie cassette rebuild-lockfile --check`) trips the
fence even though it's plainly not a stub. Per Rule 7 the right fix is
to widen the fence to recognize `python -m <module>` / `python
<script>` rather than wrap the CLI in a shim under `scripts/` — the
shim adds a code path with no semantic value. S3-05 widened the fence;
future CLI-driven hooks need no further change.

---

## L-13 (S3-06) — macOS pre-commit hooks that invoke bare `python` fail locally

S3-05's `cassette-lock-check` hook uses `entry: python -m codegenie cassette
rebuild-lockfile --check`. macOS default Python installs ship `python3` only,
no `python` shim — so `pre-commit run --all-files` fails locally with
"Executable `python` not found". CI Linux runners have `python` available so
the hook passes there (and the S3-05 commit landed green). Three resolution
paths if this ever becomes load-bearing: (a) ship `scripts/<hook>.sh` shim,
(b) widen hook entry to resolve via `sys.executable`-equivalent, (c) document
the divergence in `docs/contributing.md`. Same shape as L-2/L-4 — surfaces
locally, invisible to CI.

## L-14 (S3-06) — fix source data over loosening a literal-spec test

When a story spec writes a literal assertion (e.g. `assert "<" not in text`),
prefer to fix the data the test reads over weakening the test. A test that
strips its own input to pass is no longer a guardrail. S3-06's CODEOWNERS
comment containing `>= 1` violated the AC-16 placeholder-rejection check;
rewording the comment to "at least one" kept the protection intact (Rule 9 —
tests verify intent, not just behavior).

## L-15 (S3-06) — `sys.executable` over bare `"python"` for `subprocess.run`

When a test invokes Python via `subprocess.run`, always use `sys.executable`
unless the test deliberately exercises PATH resolution. Bare `"python"` is
absent on default macOS PATH (`/usr/bin/python3` is the only shipped binary)
and surfaces as `FileNotFoundError` instead of the test's intended diagnostic.
The MIN_ENV pattern (`{"PATH": "/usr/bin:/bin"}`) for gate-isolation testing
strips the venv from PATH — when MIN_ENV is in effect, call `make` (which
finds its own tools); when MIN_ENV is not in effect, use `sys.executable` for
the interpreter.

## L-16 (S4-02) — A 1-byte zero file is NOT a corrupt sqlite db

`sqlite3.connect()` + `PRAGMA journal_mode=WAL` + `CREATE TABLE IF NOT
EXISTS` all succeed on `b"\x00"`. Sqlite permissively treats a near-empty
file as a fresh database. To exercise a `DatabaseError`-trip fixture for
the rebuild-on-corruption path, use a sqlite-shaped-but-malformed file
(`b"SQLite format 3\x00" + b"\xff" * 200`); the magic header forces sqlite
to attempt body parsing, which then fails with `file is not a database`.
Assert your simulator actually raises the targeted exception before
relying on it.

## L-17 (S4-02) — `structlog.testing.capture_logs` not `caplog` for structlog events

The pytest `caplog` fixture only sees stdlib `logging` events; codegenie's
`_log = structlog.get_logger(__name__)` events flow through structlog's
own processor chain. For unit tests of code that emits via `_log.warning`
/ `_log.info`, use `with capture_logs() as logs:` (from
`structlog.testing`) and assert `entry.get("event") == "my_event_name"`.
The smoke suite documents the inverse pin: re-configuring structlog
mid-test clobbers `capture_logs`'s injected processor (see
`tests/smoke/conftest.py::_disable_cli_configure_logging`).

## L-18 (S4-02) — Float32 round-trip equality requires power-of-2 denominators

`tuple(float(i) / 100.0 for i in range(384))` does NOT survive
`float64 → float32 → float64` because `0.01` has no exact float32
representation. Use `float(i) / 256.0` (power-of-2 denominator) when the
test wants exact tuple equality after a `np.float32` round-trip. The
encoder is canonical in float32 — testing against values that lose
precision tests float arithmetic, not the encoder contract.

## L-S403-1 — chromadb's `to_thread(...)` types are invariant (S4-03)

`collection.add(embeddings=[list(...)])` typechecks at *runtime* but
`asyncio.to_thread` propagates the keyword-argument type into
`mypy --strict`. chromadb's `embeddings=` parameter declares
`list[Sequence[float] | Sequence[int]]` and that outer `list[...]` is
invariant — `list[list[float]]` is NOT assignable. Fix: declare the
inner vector as `Sequence[float]` and the outer list with the exact
`list[Sequence[float] | Sequence[int]]` annotation. Same pattern recurs
for `query_embeddings` on the read side. Don't paper over with
`# type: ignore[arg-type]` — the explicit type annotation documents the
contract the chromadb stubs actually require.

## L-S403-2 — pre-commit mypy hook stays in lockstep with path-scoped admissions (S4-03)

Every Phase-4 ADR-0003 path-scoped admission needs a mirrored entry in
the pre-commit mypy hook's `additional_dependencies` — the isolated
hook does not share the venv's installed packages, so `import chromadb`
fails with `[import-not-found]` until added. S3-02 codified the pattern
for `anthropic`+`keyring`; S4-01 for `fastembed`+`numpy`; S4-03 for
`chromadb`. Promote this from a per-story lesson to a cross-story
checklist: a new path-scoped admission MUST land in three places — the
pyproject fence test, the import-linter contract `ignore_imports`, AND
the pre-commit mypy `additional_dependencies` list.

## L-S403-3 — chromadb 0.6.3 posthog telemetry warnings are inert (S4-03)

`Failed to send telemetry event ...: capture() takes 1 positional
argument but 3 were given` prints to stderr on every chromadb
client/collection/query call under chromadb 0.6.3. They do not fail
tests and cannot be silenced via the documented
`Settings(anonymized_telemetry=False)` (the posthog client-signature
mismatch is upstream). Do not paper over with a logging filter — when
chromadb is bumped the warnings will disappear without code change.


## L-S404-1 — explicit per-field Hypothesis strategies for newtype-rich Pydantic models (S4-04)

`st.builds(SomeModel, ...)` against a Pydantic model whose fields are
`NewType`-wrapped (`SolvedExampleId`, `BlobDigest`, `ChainHead`,
`EmbeddingVector` tuple, `Language`, `ModelId`, ...), closed `Literal`s
(`signing_method`, `origin`), or nested submodels (`RecordProvenance`)
will silently generate degenerate values — or fail construction on the
first draw. Always declare a bound `st.SearchStrategy` for every field
and assemble via an `@st.composite` builder. For mypy --strict
compatibility on closed-Literal fields drawn from `st.sampled_from(...)`,
cast at the construction site (`cast("Literal[..., ...]", draw(...))`)
rather than narrowing the strategy type. First hit: phase-4 S4-04 YAML
roundtrip property.

## L-S404-2 — `schema_version` raw-dict check sequencing matters (S4-04)

A Pydantic model used as a durability artefact with
`ConfigDict(extra="forbid")` + `schema_version: Literal[N]` will reject
a future v(N+1) manifest with a generic `ValidationError` — losing the
intended `StoreCorrupted("unknown manifest schema_version")` diagnostic
that names the upgrade path. The defensive parser MUST inspect the raw
dict's `schema_version` BEFORE `model_validate(...)`. The full Open/
Closed dispatch table only earns its keep when v2 actually exists (Rule
2 — no premature abstraction). First hit: phase-4 S4-04 `_Manifest`
parse path.

## L-S405-1 — internal-variant count test follows the variant (S4-05)

`tests/unit/plugins/test_events.py::test_all_30_internal_variants_exist`
hardcodes the variant count and is named `test_all_<N>_internal_variants_exist`.
Every new `WorkflowInternalEvent` row needs three coupled edits the
discriminated-union itself does not enforce: (1) add to the
`_INTERNAL_VARIANTS` frozenset at the top of the file, (2) bump the
literal in the assertion, (3) rename the test function (`30` → `31` for
S4-05). Skip any of the three and the union still type-checks; the count
test catches drift between the registry and the test's checklist.
Promote to per-story checklist for any future internal-variant story.

## L-S405-2 — `RecordProvenance.verify` is module-level, NOT a staticmethod (S4-05)

Arch §Component 7 prose names the contract as
`RecordProvenance.verify(record, spanning_log) -> bool`. Implementing it
as a staticmethod on the Pydantic model would import
`codegenie.rag.provenance` (the policy) from `codegenie.rag.models` (the
data shape) and create a `models.py → provenance.py → models.py` cycle
that mypy does NOT catch but pytest collection breaks on. The S4-05
validator preempted this with a "RESCUE" verdict that rewrote AC-1 to
explicitly forbid the staticmethod alias; the executor pinned
the absence with `test_recordprovenance_has_no_verify_staticmethod`.
General rule: when the arch prose names a behaviour as
`Model.method(...)` but `Model` is a frozen data Pydantic model, prefer
a module-level function in a sibling policy module and pin
`assert not hasattr(Model, "method")` so a future drive-by edit can't
silently reintroduce the cycle.


## L-S406-1 — Substring source-guards false-positive on docstring prose (S4-06)

`name in src` substring sweeps over a module's source text trip on
honest docstring mentions: when `rag/ingest.py` documents "writer never
inspects `TrustOutcome.confidence`" or "S6-03 owns `EventLog`
emission", the substring check fires. Rewrite stale-name / forbidden-
import guards as `ast.walk` over `ast.keyword.arg` (constructor
kwargs), `ast.Attribute.attr` (attribute reads), and `ast.Import` /
`ast.ImportFrom` (real imports). The runtime risk is a real kwarg /
attribute / import — not the English word — so AST is both sound and
complete. First hit: S4-06 AC-4 + AC-10 guards.

## L-S406-2 — import-linter `forbidden` sources cannot contain a forbidden descendant (S4-06)

A `[[tool.importlinter.contracts]]` row with
`source_modules = ["codegenie"]` and
`forbidden_modules = ["codegenie.rag._capability_mint"]` fails with
"Modules have shared descendants" at lint time. The honest fix is the
same one the ADR-0010 BudgetToken contract already uses: enumerate
sibling subpackages individually (e.g. every `codegenie.*` package
EXCEPT the forbidden subtree), with the relevant siblings of the
forbidden module spelled out explicitly so the contract still covers
every neighbor. Story drafts that say `source_modules = ["codegenie"]`
are user-intent shorthand — the executor must reach for the
sibling-enumeration shape and update both `pyproject.toml` and the
matching shape test to pin the deviation.

## L-S406-3 — Live-fire planted-violator files must live inside an enumerated source module (S4-06)

The S1-06 / S2-* / S3-* planted-violator pattern (write a temporary
`.py` that imports the forbidden module, run `lint-imports
--config pyproject.toml --no-cache`, assert non-zero exit) only fires
when the planted file lives **inside** one of the contract's
`source_modules` (since `as_packages = true` walks descendants only).
Top-level `src/codegenie/<name>.py` lives outside every enumerated
subpackage and gets silently ignored — the contract reports "KEPT" and
the test green-passes on a bug. Plant under an enumerated sibling
package (e.g. `src/codegenie/probes/<name>.py`); record the choice
inline so a future shape-test edit doesn't bring the planted file back
up to the codegenie root.


## L-S407-1 — chromadb `SharedSystemClient` caches by path; `rmtree` then re-open needs `clear_system_cache()` (S4-07)

`chromadb.PersistentClient(path=p)` registers a process-wide
`SharedSystemClient` system instance keyed by `p`. After
`shutil.rmtree(p)` the cached system survives with stale handles to the
now-deleted sqlite, and the first `collection.add` on a freshly-
constructed client at the same path raises `OperationalError: no such
table: collections`. The fix is one line:
`SharedSystemClient.clear_system_cache()` from
`chromadb.api.client` between the `rmtree` and re-construction. Keep
this helper INSIDE `codegenie.rag.store` (the lone ADR-0003-authorized
chromadb importer) and re-export to callers — leaking a direct
`chromadb.api.client` import to `codegenie.rag.cli` adds a row to the
chromadb `ignore_imports` list that the rebuild does not need (the
call surface fits one helper). First hit: S4-07 `rag rebuild`.

## L-S407-2 — wipe `manifest.yaml` when wiping `chroma/` (S4-07)

`ChromaPersistentStore.__init__` calls `_load_existing_record_ids()`
which reads `manifest.yaml` into `_record_ids`. A rebuild that calls
`shutil.rmtree(chroma/)` but leaves the manifest in place re-opens
a fresh store whose `_record_ids` is already `[ex-000, ex-001, ex-002]`;
each subsequent `store.add(example)` then `_record_ids.append(...)`s on
top, and the rebuilt manifest carries every record twice. The fix is
to `manifest.yaml.unlink()` immediately after `rmtree`. AC-5's byte-
identical-digest assertion catches the bug, but only because the seed +
rebuild use the same canonical YAML bytes — a bare "rebuild ran without
exceptions" check would silently green-pass on the doubled list. First
hit: S4-07.

## L-S407-3 — `rebuild()` is sync; integration tests calling it must be sync too (S4-07)

`rebuild()` owns an internal `asyncio.run()` boundary so the CLI entry
point stays sync. Under `asyncio_mode = "auto"` an `async def test_...`
function runs inside an event loop, and the inner `asyncio.run()` raises
`RuntimeError: asyncio.run() cannot be called from a running event
loop`. Make the integration test functions **sync** and bracket any
async setup (e.g. seeding records via `store.add`) with
`asyncio.run(_seed_async(...))`. The story Notes §2 anticipated this
posture; the validator-prescribed test code in the story body used
`async def + await store.add` and is the trap. General rule: when a
CLI body uses `asyncio.run` internally, test functions that call it
directly are sync. First hit: S4-07 `tests/integration/test_phase4_rag_rebuild_*.py`.

## L-S408-1 — Don't `**unpack` a `dict[str, str]` into `Literal`-typed kwargs (S4-08)

When a test file uses the same partition triple across every record, the
temptation is to hoist `task_class / language / build_system` into a
`Final[dict[str, str]]` and unpack it into `make_solved_example(...)`.
mypy --strict correctly refuses: `build_system: PackageManager` is a
`Literal[...]` and a `dict[str, str]` does not unify. Three options
land safely: (a) rely on the fixture's defaults when they already match
(this is what S4-08 chose — Rule 11 alignment with the
`tests/integration/test_phase4_store_contention_30s.py` style); (b) pass
the kwargs explicitly at each call site if they need to vary; (c) build
a typed `TypedDict` with the Literal-typed fields. (a) is the smallest
diff when the values are exactly the defaults. First hit: S4-08
`tests/integration/test_phase4_harvest_contention.py`.

## L-S408-2 — `slow_add_a` lock-hijack coroutines must use raw `acquire()`, not `asyncio.wait_for` (S4-08)

For deliberate-timeout integration tests where one coroutine hijacks
`store._add_lock` to force the second coroutine's `wait_for(...,
timeout=...)` to fire, use raw `await store._add_lock.acquire()` (then
`finally: release()`). `asyncio.Lock.acquire()` on a free lock returns
*without suspending*, so the first-scheduled coroutine holds the lock
before its first real `await` — guaranteeing the second coroutine
observes the lock held when it tries to acquire. A `wait_for(acquire(),
timeout=...)` wrapper introduces a yield point that race-conditions the
ordering this test depends on. First hit: S4-08
`test_harvest_contention_timeout_raises_typed_exception`.

## L-S408-3 — `asyncio.to_thread` boundary regression guards belong in their own test (S4-08)

`Mock(wraps=asyncio.to_thread)` + `monkeypatch.setattr(asyncio,
"to_thread", mock)` is the canonical "did we call `to_thread`?" probe.
Keep it in its own test (its own two adds) — folding it into the
contention/correctness tests pollutes the lock-contention semantics and
the AC-9 mutant (unwrap) becomes hard to isolate from the AC-4 mutant
(wrong lock granularity). Also assert each call's first positional
argument's `__name__ == "add"` so the test catches a wrong-target
mutant (count stays, callable changes) as well as the unwrap mutant
(count drops to 0). First hit: S4-08
`test_to_thread_invoked_per_add`.
