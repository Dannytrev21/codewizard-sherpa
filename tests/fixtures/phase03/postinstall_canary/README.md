# postinstall_canary fixture

Used by [`test_bwrap_postinstall_canary.py`](../../../integration/transforms/test_bwrap_postinstall_canary.py) (S4-02 AC-12).

The fixture's `package.json` declares a `postinstall` script that writes to the
`CANARY_PATH` env var. Inside the substrate the path is outside the bwrap
`--bind` target, so a *correct* substrate + `--ignore-scripts` defence both
prevent the file from being written.

Two test variants exercise the fixture:

* **Variant A** — CLI flag `--ignore-scripts` AND `NpmEnv` (env var
  `npm_config_ignore_scripts=true`) both engaged. Both halves of the split
  defence.
* **Variant B** — `NpmEnv` only (CLI flag omitted). Proves the env half is the
  load-bearing defence.

S8-04 lands the full adversarial corpus (`tests/adversarial/test_postinstall_canary.py`,
`@pytest.mark.phase03_adv`).
