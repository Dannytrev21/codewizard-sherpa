# Plant-a-bug recipe — for evaluating capability-shakedown

`capability-shakedown`'s hardest path is the codebase-fix loop (test-gap
analysis → failing test first → fix → verify). To exercise it in an eval,
the repo needs a real bug planted first. This recipe plants one cleanly
and restores it afterward.

## The bug

Revert the `dockerfile` probe so it stops publishing its raw sidecar —
this makes the `entrypoint` and `shell_usage` probes silently no-op
(they read `.codegenie/context/raw/dockerfile.json`, which no longer
gets written). It is the exact bug class this skill was built from.

## Plant

```bash
# from the repo root, on a clean committed master
git checkout 5055292~1 -- src/codegenie/probes/layer_c/dockerfile.py
```

`5055292` is the commit that introduced the sidecar fix; `~1` is its
parent — the authentic pre-fix file. If that SHA has aged out, instead
edit `src/codegenie/probes/layer_c/dockerfile.py` so `_write_files`
returns `[]` without writing, and both `run()` branches pass
`raw_artifacts=[]`.

Confirm the bug is live: `codegenie --no-gitignore gather <a Node app
with a Dockerfile>` then check `repo-context.yaml` — `probes.entrypoint`
should read `confidence: unavailable`.

## Restore (between every eval run, and at the end)

```bash
git checkout HEAD -- src/codegenie/probes/layer_c/dockerfile.py
git clean -fd docs/_shakedowns/        # remove reports an eval run wrote
# remove any sample-app clone the run created under /tmp
```

## Eval-run discipline

- Run the with-skill and baseline subagents **serially**, never in
  parallel — the skill mutates the working tree.
- Plant the bug fresh before each run; restore after each run.
- The repo is fully committed, so `git reset --hard HEAD` is always a
  safe last-resort recovery.
- The skill's own `--diagnose-only` flag is the safe mode if you want a
  run that does not mutate anything.
