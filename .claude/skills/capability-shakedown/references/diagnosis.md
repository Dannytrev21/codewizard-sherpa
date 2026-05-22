# Diagnosis — root-cause buckets + discriminating tests

Every finding from Stage 4 gets exactly one root cause. A misdiagnosis
sends the fix down the wrong route — fixing the codebase for what was
really a sample-app gap, or "documenting" what was really a bug. So a
diagnosis is a **hypothesis you must prove**, never a guess.

## The five buckets

| Bucket | What it means | Route (Stage 6) |
|---|---|---|
| **codebase-bug: no-op** | A feature wired to nothing — produces empty / `unavailable` output regardless of input. | Fix the code. |
| **codebase-bug: incorrect** | Runs, but produces wrong or misleading output. | Fix the code. |
| **environment** | Needs an external tool / Docker / a built image / a service that is not present. | Set it up + document the prerequisite. |
| **sample-app** | The app lacks an input the capability legitimately consumes. | Fix the sample app. |
| **by-design** | The empty/degraded output is correct — honest degradation, or a capability scoped to a later phase. | Document. No code change. |

A single finding can be a **combination** — e.g. a probe that is both
macOS-blocked (by-design) *and* has a wiring bug that would block it on
Linux too. Diagnose every layer; route each.

## The discriminating tests

Run these in order. The first one that resolves the finding wins.

### Test 1 — Is it scoped to a later phase? (→ by-design)

Grep the roadmap and phase docs for the feature. `docs/roadmap.md`, the
phase `final-design.md` files, and `CLAUDE.md` all say what is built vs.
designed-only. If a registry/strategy/probe is *deliberately empty until
phase N* (the way the dep-graph strategy registry is "filled by Phase
3"), the empty output is correct. Document it; do not fix it.

### Test 2 — Does the producer actually emit? (→ codebase-bug: no-op)

If a consumer's output is empty, do not assume the consumer is broken —
run its **producer** in isolation and watch what it writes. The
session's worked example: `entrypoint` read
`.codegenie/context/raw/dockerfile.json`; the `dockerfile` probe ran
fine and produced a high-confidence envelope slice — but returned
`raw_artifacts=[]` and never wrote that sidecar file. The consumer was
correct; the **producer never emitted the thing the consumer reads**.

The test: identify the resource the consumer reads (a file, a slice, a
ctx attribute). Confirm — by listing the directory / inspecting state
after a run — that the resource *exists*. A consumer wired to a resource
nobody produces is a no-op codebase bug, on every platform.

### Test 3 — Is an external tool / Docker / image missing? (→ environment)

If the capability shells out (`grype`, `syft`, `semgrep`, `strace`,
`docker`) or needs a built image, check whether the tool is on `PATH`
and whether Docker is running. A probe that emits `skipped:
tool_missing` or `upstream_unavailable` *because the tool genuinely is
not installed* is an environment finding — set the tool up. But first
rule out Test 2: the session's `sbom`/`cve` chain *looked* like an
environment gap ("needs syft/grype") yet was really a no-op bug —
`runtime_trace` never wrote `raw/runtime_trace.json`, so `sbom` could
never read the image digest **even with syft installed**. Environment is
only the diagnosis once the wiring is proven sound.

### Test 4 — Does the sample app have the input? (→ sample-app)

Check the capability's declared inputs against what the app actually
contains. A probe reporting `unavailable` because the app has no
`Dockerfile`, no lockfile, no `.codegenie/` config is a **sample-app
deficiency** — the code is fine. Fix the app, re-run, confirm the
finding clears.

### Test 5 — Is the output honest degradation? (→ by-design)

Read the producing code's docstring and the relevant ADR. Some
"emptiness" is the *correct* answer: `runtime_trace` on macOS fails every
scenario by design (`runtime_trace.py` — "macOS path is permanent"; no
`strace`). That is not a bug — it is the system being honest about a
platform it cannot trace on. Document it as a known limitation; do not
try to "fix" it.

## After Test 2 says "no-op" — confirm before fixing

A no-op diagnosis must be reproduced as a fact, not asserted. Before
routing to a codebase fix:

1. Run the producer (or the whole capability) and capture the artifact
   list / output state.
2. Point at the specific missing thing: "`raw/dockerfile.json` is absent
   from the raw dir after a gather" — a concrete, checkable claim.
3. Note *why the consumer needs it* — which line reads it, what it
   degrades to when it is absent.

That triad — reproduced, concrete, explained — is what makes the
codebase-fix loop ([`codebase-fix.md`](codebase-fix.md)) able to write a
test that genuinely fails on the bug.

## Output of this stage

A findings table, each row: the finding, its bucket, the evidence that
fixed the bucket, and (for combinations) every layer. This table is
copied verbatim into the report and drives Stage 6 routing.
