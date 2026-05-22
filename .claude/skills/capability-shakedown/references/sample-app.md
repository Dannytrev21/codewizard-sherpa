# Acquire the sample app

A capability shakedown is only as honest as the app it runs against. A
sample app that lacks the inputs a capability consumes will make a
perfectly-working capability *look* broken — so the first job is to get
an app that genuinely exercises the capability.

## The sample-apps repo

Sample apps live in the user's repo **`github.com/Dannytrev21/sample-apps`**,
organized by `sample-apps/{language}/{package-manager}/{tool}/` —
e.g. `sample-apps/javascript/npm/esbuild/`.

Clone it once per run into a stable scratch path and reuse it:

```
git clone --depth 1 https://github.com/Dannytrev21/sample-apps.git \
  /tmp/capability-shakedown/sample-apps   # or `git -C … pull` if present
```

If the clone fails (offline, auth), fall back to building a hermetic
sample app under `/tmp/capability-shakedown/<name>/` and **flag the clone
failure in the report** — do not silently proceed as if the user's repo
was used.

## Selecting an existing app

Match the app to the capability's declared inputs, not to its name. For
`gather`, a rich app — one with a `Dockerfile`, a lockfile, CI config,
`src/` with real code, a `.codegenie/` config dir — exercises far more
probes than a bare `package.json`. The esbuild sample
(`sample-apps/javascript/npm/esbuild/`) is the current rich reference.

A good existing app for the capability satisfies: *every input the
capability's spec names is present in the app*. If an app is close but
missing one input, that is a **sample-app deficiency** finding (Stage 5)
— note it, and either pick a better app or fix this one.

## Creating a new app

When no app fits, build one. Keep it **minimal but real** — it should
contain exactly the inputs the capability consumes and nothing
decorative. Derive the input list from the capability's spec
(`localv2.md`, the probe `declared_inputs`, the story docs).

A useful sample app is also *adversarial on purpose*: include a file or
construct that should produce a positive finding, so a probe reporting
"nothing found" is visibly distinguishable from a probe that did not run.
The esbuild sample's `src/unsafe-demo.js` (an intentionally-unimported
file with `eval()` / `child_process.exec()`) is the pattern — it gives
the scanner probes something real to catch.

New apps are created in the cloned repo under the right
`{language}/{package-manager}/{tool}/` path. They stay in the **local
clone** — the skill never pushes. The report tells the user which app was
created or modified and that they need to push it.

## Running the capability writes into the app

`gather` writes its output *into* the sample app at `.codegenie/`. That
is expected. When re-running after a fix, delete `.codegenie/` first so
stale artifacts from the previous run don't mask the new behavior:

```
rm -rf <sample-app>/.codegenie && .venv/bin/python -m codegenie --no-gitignore gather <sample-app>
```

## When the sample app itself is the bug

If Stage 5 diagnoses a finding as a sample-app deficiency, fix the app —
add the Dockerfile, the lockfile, the source file — then re-run from
Stage 3. A capability that goes from `unavailable` to populated purely
because the app gained an input it was always supposed to have is a
sample-app fix, full stop; do not also "fix" the codebase for it. The
discriminating question is in [`diagnosis.md`](diagnosis.md).
