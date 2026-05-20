# Fixture — `dockerfile-base-image-swap`

This is the single Phase-7-preview fixture for the `OpenRewriteRecipeEngine`
scaffold (story S5-03). It carries a baseline `Dockerfile` (`FROM
node:20-alpine`), the post-rewrite `expected.Dockerfile` (`FROM
cgr.dev/chainguard/node:latest`), the byte-equal golden `expected.diff`, and a
placeholder `recipe.yml`. The Phase-3 scaffold diffs the two side-by-side
Dockerfiles under a `FakeJail`; the `@pytest.mark.phase_7_preview` integration
test runs the engine against this fixture under a real `SubprocessJail` with
`java` available. **Phase 7 owns the content of `recipe.yml`** — it replaces
the placeholder with the authored OpenRewrite Dockerfile-rewrite recipe and
flips the preview marker to a per-PR-required mark.
