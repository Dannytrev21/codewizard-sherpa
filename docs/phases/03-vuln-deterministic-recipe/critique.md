# Phase 3 — Vuln remediation: deterministic recipe path: Devil's-advocate critique

**Reviewed by:** Devil's-advocate critic subagent
**Date:** 2026-05-12

## Method

I read all three designs and attacked each on its own terms. I do not propose alternatives.

## Attacks on the performance-first design

### Concrete problems

1. **Problem:** The roadmap line for Phase 3 names OpenRewrite as the transform engine ("OpenRewrite recipes for npm dependency updates (or `npm-check-updates` as a simpler first cut...)"). Performance-first not only demotes OpenRewrite but actively reframes it as the wrong default, citing JVM cold start; the design defaults to direct stdlib JSON mutation, bypassing both `ncu` *and* OpenRewrite for the typical case.
   **Why it matters:** Phase 4's recipe → RAG → LLM-fallback chain assumes "the recipe ran and didn't work" is the failure signal; if there is no recipe engine — just an ad-hoc `package.json["dependencies"][pkg] = new_range` mutation — then "recipe failed" reduces to "JSON write failed," which never happens. Phase 4 has no deterministic failure surface to detect-and-fall-back-on. Worse, Phase 7 (Chainguard distroless) and Phase 15 (agentic recipe authoring) both assume an actual engine abstraction with a recipe contract; Phase 15's "the system writes its own deterministic recipes" cannot write a stdlib JSON mutation — it has to write *into* a recipe ecosystem. Performance-first leaves no such ecosystem.
   **Where:** §Components → "Recipe Selector + Recipe Engine"; the "Effective default for the typical CVE: stdlib JSON mutation" sentence.

2. **Problem:** `npm install --package-lock-only` is sold as the diff-generation primitive. The design explicitly contrasts it with `npm ci` (which is reserved for validation). But `--package-lock-only` does **not** prove postinstall behavior is benign, does **not** resolve native modules, and does **not** validate that the new resolution graph is actually installable on the target platform. It is a *paper* lockfile; the diff produced is provably the diff `npm` thinks it should be, not a diff that survives `npm ci`. The design's own data-flow shows `npm ci` is run only inside validation (step 7); by then the cache has already been written and the attempt recorded as if the resolve were authoritative.
   **Why it matters:** The §Components "Lockfile Resolver" cache key (`blake3(package.json_post_bump), blake3(package-lock.json_pre), npm_registry_mirror_digest, npm_version_digest`) is keyed on the *paper* result. A bump that resolves to the cache but explodes during `npm ci` (e.g., `node-gyp` failures, peer-dep manifests rewritten by `npm` 10 during install but not during `--package-lock-only`) will produce the same cache hit on the next attempt — short-circuiting validation entirely on the second run. The design even acknowledges this in the §Risks section under "Lockfile cache poisoning" but resolves it by saying "we let validation be the oracle." Validation is the oracle of the *current* run; the cache survives across runs.
   **Where:** §Components → "Lockfile Resolver"; §Risks #4.

3. **Problem:** The 60-minute CVE feed cron silently makes the first hour after a CVE drops invisible to Phase 3. The text claims "CVE-feed event triggers (Phase 14) override the cron for hot CVEs," but Phase 14 is the phase that introduces those triggers. In Phase 3, on its own, the lag is real and uncovered.
   **Why it matters:** The Phase 3 exit criterion is "given a Node.js repo with a known npm CVE, the system writes a working patch diff." A CVE published 15 minutes before a run with the deepest possible NVD lag (NVD already lags upstream by ~24h per the design's own §Risks) is unaddressable. Composing into Phase 14: when continuous-gather goes live, the request path will *also* miss recently-fired-CVE workflows because the local snapshot will be stale. The architecture's "always-fresh" gather property in production design §3.2 doesn't hold for CVE-feed–driven triggers unless the cron interval is sub-trigger-interval — but Phase 14's webhook is supposed to *be* the trigger interval. Performance-first's 60-minute cron locks in a tier of un-fixable staleness.
   **Where:** §Components → "CVE Feed Ingestor" → "Refresh cadence: 60-minute cron."

4. **Problem:** The fast-path test selection is the headline tail-latency lever and it is computed from `RepoContext.depgraph` reverse-reachability. Dynamic `require`, plugin loaders, test-framework lifecycles (jest's setupFiles, mocha hooks), and `npm test`-script chaining are explicitly out of scope for static reachability. Mitigation is "if `repo_notes` says plugin loading, disable fast-path." This forces every probe author to correctly tag plugin-loading patterns across an unbounded surface — the moment one is missed, Phase 3 ships a regression *and* the fast-path full-suite skip means there's no fallback green-or-not signal.
   **Why it matters:** The §Goals section sets time-to-PR with the fast-path-only branch as the dominant case. The exit criterion is "passes the repo's own tests," not "passes the subset that statically imports the bumped package." Performance-first is essentially redefining the exit criterion to be cheaper than what the roadmap says.
   **Where:** §Components → "Validation Pyramid" step 3; §Risks #2.

5. **Problem:** `git worktree` is used for parallel-per-portfolio attempts and to keep the user's working tree clean. But `.codegenie/scratch/<attempt_id>/` is the fallback when the user has uncommitted work, and the design admits "cleanup is fragile if `codegenie` crashes mid-attempt." On a developer laptop where Phase 3 runs locally — exactly the Phase 3 scope — partial worktrees accumulating in `.git/worktrees/` is a footgun that pollutes the user's repository state across runs and across versions of `codegenie`. The atexit handler + startup reaper is a best-effort recovery from a problem that need not exist if the design didn't pretend to parallelize a single-repo POC.
   **Why it matters:** Phase 3 is `roadmap.md` line 79: "Single-repo, local, deterministic." The §Parallelism strategy section dedicates significant complexity to per-portfolio parallelism that isn't in scope until Phase 10, and that parallelism is the load-bearing reason for worktree-per-attempt. Removing it removes the worktree fragility entirely.
   **Where:** §Components → "Attempt Recorder + Branch Writer"; §Parallelism strategy.

### Hidden assumptions

1. **Assumption:** `npm install --package-lock-only` is a deterministic function of `(package.json, package-lock.json, registry-state, npm-version)`. The design pins npm version and includes a `npm_registry_mirror_digest` field in the cache key.
   **What breaks if wrong:** npm 9 → 10 was called out as having lockfile-format churn; npm patch releases have also silently changed peer-dep resolution. The design's lockfile cache becomes silently wrong across portfolio after any npm patch bump; the §Risks section names this as a "stampede" but treats it as operational rather than as a correctness threat. If the cache *does* serve a stale lockfile because the digest didn't change but the resolution did, validation runs against a lockfile that no longer matches what npm would resolve today — and the resulting branch is a lockfile npm itself won't reproduce.

2. **Assumption:** The portfolio shares a single `~/.npm` cache, which is "pre-warmed for top-N packages." Cache poisoning at the npm cache level is treated as out-of-scope.
   **What breaks if wrong:** A single malicious tarball in `~/.npm` taints every workflow that resolves through it. Performance-first defers all of this to Phase 5/14 — but Phase 3 *does* ship code that reads from `~/.npm`. The chokepoint is `run_in_sandbox`; the cache is host-resident. Bridging this in Phase 3's design without admitting it is a gap.

3. **Assumption:** Phase 2's depgraph is high-confidence enough to be ground truth for peer-dep conflict detection. The design halts with an honest error if `IndexHealthProbe` flags low confidence.
   **What breaks if wrong:** IndexHealthProbe's confidence is itself probabilistic about staleness; "medium" confidence is a thing. The design treats `low` as halt and presumably everything else as proceed. For peer-dep conflict detection in non-trivial monorepos, "medium" is exactly the regime where Phase 3 will silently produce wrong bumps.

### Things this design missed that a different lens caught

- The **security-first lockfile policy scanner** entirely. Performance-first parses lockfiles into the depgraph and assumes the lockfile is structurally honest. Registry-redirect (`resolved:` URL pointing at attacker host), missing `integrity:` fields, and `overrides`/`resolutions` redirection are unguarded. `--ignore-scripts` is mentioned only as a flag toggle on the `npm` invocation, not as a structural lockfile property to be enforced pre-install.
- **OpenRewrite ecosystem semantics**, which both other designs at least gesture at as a future engine even when they don't choose it. Performance-first treats OpenRewrite as merely-slow, not as the contract by which Phase 15 will author recipes.
- **Audit chain extension.** Security-first extends Phase 2's BLAKE3 JSONL audit log with phase-3 event types. Best-practices uses `audit.json` per run-id. Performance-first writes `metadata.json` per attempt with no chained-audit semantics — meaning the cache-hit short-circuit on attempt-id has no audit story for the original attempt's evidence.
- **Working-tree safety as a load-bearing security control.** Performance-first uses `git worktree` for parallelism efficiency; both other designs use it (or refuse-dirty-tree) for operator safety. Different goals, same primitive.

---

## Attacks on the security-first design

### Concrete problems

1. **Problem:** Two sandbox profiles is one too many to validate. The design defines Boundary 1 (per-tool subprocess sandbox) and Boundary 2 (`TestSandboxProfile`) that diverge on every dimension that matters: writable overlay, `--ignore-scripts` semantics, network model (scoped vs. hard-none), wall/memory/PID caps. The CI test promise of "≥ 40 hostile fixtures, 0 escapes" must now cover both profiles plus the per-tool allowlist permutations (`npm`, `pnpm`, `yarn`, `ncu`, `jq`, `git`, `java`, OpenRewrite). The combinatorial space of "did we leak credentials" and "did we leak network egress" across both profiles and seven tools is too large for the Phase 3 fixture corpus to plausibly cover, and the design promises CI gating on it.
   **Why it matters:** This is exactly the kind of complexity that goes silently wrong. Phase 5 microVM is supposed to be the real boundary — that's what `production/design.md §4` and ADR-0012 commit to. Two heavyweight, divergent sandbox profiles in Phase 3 mean Phase 5 has to *retire* one of them, not just wrap the chokepoint. Extension by addition fails when one of the additions is itself superseded.
   **Where:** §Components → `TestSandboxProfile`; §Threat model → "Trust boundaries."

2. **Problem:** `LockfilePolicyScanner` produces a **non-retryable** `LockfilePolicyViolation` that "escalates to human review." Two hostile-case mismatches:
   (a) Legitimate npm packages occasionally introduce a `resolved:` host outside `registry.npmjs.org` — e.g., GitHub-tarball deps for forks. Refusing to proceed means a perfectly normal repo cannot be remediated at all without a config change.
   (b) `package.json#publishConfig.registry` overriding the trust root is documented as a hostile shape, but legitimate enterprises set `publishConfig.registry` to their private registry for publishing while still resolving from the public one for installs. Refusing this is a false-positive on a meaningful fraction of real corporate repos.
   The "escape valve" is conspicuously absent — there is no documented `--allow-registry` flag or per-repo policy override; just "human review," which is not a Phase 3 deliverable (Phase 11 is).
   **Why it matters:** Phase 3's stated exit criterion is "the system writes a working patch diff on a local branch that ... installs cleanly and passes the repo's own tests." A pre-install policy that refuses on any non-default registry will make this criterion *fail by design* on a meaningful fraction of real repos. Goal #7 says "non-retryable, hard escalate" which leaves the operator with no recourse other than editing the policy and re-running.
   **Where:** §Goals #7; §Components → `LockfilePolicyScanner`.

3. **Problem:** `tools/maven-mirror/` for OpenRewrite is "pre-populated by a signed-manifest ceremony at install time" — `codegenie tools install-openrewrite-mirror`. Who runs that ceremony? On whose laptop? What's the trust root for the OpenRewrite jar pins listed in `tools/digests.yaml`? When a new OpenRewrite recipe lands upstream (one of Phase 4/15's expected flows), how does the in-repo signing-key trust extend to it without re-running the ceremony per-engineer-per-recipe-update?
   **Why it matters:** The design specifies "fully offline" OpenRewrite with no Maven Central reach-through, but this is a Phase 3 deliverable: a Python POC on a developer laptop. The operational machinery for the ceremony — key custody, mirror update cadence, who signs the manifest — is not specified. The first time someone needs to update a recipe, the design degenerates into "go fetch from Maven Central anyway." The upgrade story is not just "out of scope" — it's "load-bearing and unspecified."
   **Where:** §Goals #6; §Components → `OpenRewriteRunner`.

4. **Problem:** `TestSandboxProfile` enforces `--network=none` HARD with "no escape valve." The design admits that tests requiring a postgres/redis sidecar or external DNS for fetched-during-test mocks "cannot pass this gate; the validation gate declares the patch unverifiable." This is presented as "honest design," but the Phase 3 exit criterion is "passes the repo's own tests." For any repo whose test suite requires *any* outbound DNS resolution — which is the majority of nontrivial Node.js services — the security-first design fails the exit criterion for legitimate reasons and routes to a human reviewer that doesn't exist until Phase 11.
   **Why it matters:** This isn't a forward-deferable concern; it's the load-bearing tension between security posture and what "the repo's own tests" actually means in npm-ecosystem reality. The design's answer is "escalate to human" — but there's no human in Phase 3. So in practice the gate becomes "fail every nontrivial repo and pile up `escalation.human_required` events with no consumer." The blind spot is acknowledged but flagged as a Phase-12 follow-up — meaning Phase 3 ships with a gate that fails real targets and Phase 4 inherits a coverage hole the LLM cannot close (an LLM cannot enable a network egress).
   **Where:** §Goals #8; §Components → `TestSandboxProfile` tradeoffs.

5. **Problem:** The three-retry semantics is redefined from ADR-0014's intent. ADR-0014 says three retries per gate, framed as "give the system a chance to recover before escalating." Security-first reframes this as a "deterministic parameter sweep" — Retry 1 widens the version range, Retry 2 tries the next-up patched version. This is no longer retry-on-flake; it's recipe-parameter-search. The audit log records every parameter, but the actual semantics — "retry with different args" — is a planner-level decision the design itself notes "is planner work, Phase 4+."
   **Why it matters:** Phase 3 is supposed to be the deterministic floor that Phase 4 wraps. Security-first puts what is effectively a Phase-4 planning policy ("if the patched version fails, try the next-up patched version") into Phase 3 and calls it "deterministic parameter sweep." When Phase 4 lands, it now has two layers of "retry with different args" semantics fighting each other — the Phase 3 deterministic sweep and the Phase 4 RAG/LLM fallback. Either Phase 4 has to retire the sweep (editing Phase 3 code, violating extension-by-addition) or live with two retry policies in series.
   **Where:** §Goals #13; §Components → `RecipeExecutor`.

### Hidden assumptions

1. **Assumption:** The CVE feed publishers' signature trust roots are stable and the keys ship in `tools/cve-feeds/*.asc`. The design pins GPG signatures against NIST and GitHub `web-flow` keys.
   **What breaks if wrong:** NIST has rotated NVD signing keys before. GitHub's `web-flow` key rotation is a quiet event. When either rotates, every Phase 3 install is broken until someone updates the in-repo key file. The "fully offline" property of CVE-feed verification is brittle on a multi-year horizon; the design has no story for in-place key-rotation.

2. **Assumption:** `bwrap` (Linux) and `sandbox-exec` (macOS) provide equivalent enforcement of `--network=none`.
   **What breaks if wrong:** The design itself notes "macOS `sandbox-exec` network denial is best-effort at the kernel level (sandbox-exec is deprecated upstream)." If the macOS path is best-effort, then the entire "zero sandbox escape, 0 across 40 hostile fixtures" goal degrades to "0 escapes on Linux, best-effort on macOS." Phase 3 is a developer-laptop POC; macOS is the dominant development OS. The Goal #1 metric is silently false on the dominant target.

3. **Assumption:** "No host credentials reach any sandbox." The design enumerates `NPM_TOKEN`, `NPM_CONFIG_TOKEN`, etc.
   **What breaks if wrong:** Enumeration-based stripping is inherently incomplete. Tomorrow's `NEW_NPM_AUTH_VAR` will leak by default. The design hasn't expressed strip-everything-except-allowlist as a structural invariant — it's enumerated. CI tests for "absence inside each sandbox" can only assert absence of what they enumerate.

### Things this design missed

- **Latency budget for the request path.** Goal #9 sets wall-clock caps per sandbox (npm ci 180s, OpenRewrite JVM 300s, npm test 600s default). Adding them up: a single attempt with three retries could legitimately consume 3 × (180 + 300 + 600) = 33 minutes wall-clock before declaring failure. Performance-first targets p50 18s on the hot path; security-first's worst-case-by-design is two orders of magnitude slower with no acknowledgment of the cost-per-failed-fix.
- **Cache reuse.** Phase 1/2's content-addressed cache discipline is the whole point of `production/design.md §2.7`. Security-first emphasizes audit-chain extension but doesn't address how a cache hit composes with the audit chain. If an attempt result is cached, is the audit replayed? Re-issued? Skipped? The design is silent.
- **The `Transform` ABC entirely.** Security-first introduces `Recipe`, `RecipePlan`, `RecipeExecutor`, `LockfilePolicyScanner` but never names the load-bearing public contract — the abstraction Phase 4, 5, 7, and 15 must compose with. This is the most consequential omission for downstream phases.

---

## Attacks on the best-practices design

### Concrete problems

1. **Problem:** Best-practices explicitly drops OpenRewrite in favor of `ncu`, citing "OpenRewrite's npm story is currently weak ... JVM-on-the-laptop is a heavy dependency." This is the same divergence problem as performance-first, only with the surface-level honesty of an "acknowledged blind spot." The roadmap names OpenRewrite first; the design defers it behind a `RecipeEngine` ABC that ships with exactly one implementation. The Phase 4 LLM fallback assumes a recipe failed; the Phase 15 agentic recipe authoring assumes recipes are *first-class objects* that can be authored by an LLM. With only `NcuRecipeEngine`, Phase 15's authoring target is fundamentally constrained — "agent writes new YAML that parameterizes ncu" is a much shallower deliverable than "agent writes a new OpenRewrite recipe."
   **Why it matters:** The design even surfaces this in Question #1 to the synthesizer — "ncu vs. OpenRewrite as the Phase 3 recipe engine. The roadmap names OpenRewrite first." Surfacing for arbitration does not change the fact that the design ships without an OpenRewrite implementation, and Phase 4–15 inherit that gap.
   **Where:** §Lens summary; §Acknowledged blind spots; §Open questions #1.

2. **Problem:** Three separate ABCs (`Transform`, `Validator`, `Recipe`) plus three registries (transforms registry, validators registry — best-practices argues *for* two registries in Open Question #2 — and the recipe catalog YAML loader). This is proliferation against the §Conventions to follow in CLAUDE.md ("Each probe registers via decorator (`@register_probe`)" — singular pattern). Best-practices justifies the split as "three nouns; three contracts" — but `Recipe` is data (YAML), `Transform` is the actor, and `Validator` is the post-actor judge. The argument that they have different lifecycles is the argument that *will be made* to justify each future proliferation; the discipline is to resist it now.
   **Why it matters:** Phase 7 (Chainguard distroless) will add a Dockerfile transform and a base-image validator. Phase 15 (agentic recipe authoring) will add recipe-authoring transforms. Each will lean on the precedent that "more nouns = more registries." After three or four such additions the surface area is unmaintainable by the standards Phase 0–2 set.
   **Where:** §Architecture; §Components 1, 3, 5; §Open questions #2.

3. **Problem:** Four new top-level packages (`cve/`, `transforms/`, `recipes/`, `validation/`) under `src/codegenie/`. The CLAUDE.md project instructions say "Single Python project, no services, no databases. Filesystem-backed everything" and the Phase 0–2 precedent is a small set of orthogonal packages (`probes/`, `cache/`, `tools/`, `skills/`, `output/`, `schema/`). Four new top-level packages in one phase is the largest expansion since Phase 0, and the design admits as much: "This is the largest new-package footprint since Phase 0. Surfaced because best-practices says fewer is better; the four are non-negotiable."
   **Why it matters:** Phase 4 will want `planning/`. Phase 5 will want `sandbox/` and `gates/`. Phase 6 will want `state_machine/`. Phase 8 will want `views/`. The pattern of "one phase, several new top-level packages" is the wrong precedent to set, and best-practices sets it explicitly.
   **Where:** §Goals → "Net new packages: 4"; §Conventions honored → "Extension by addition."

4. **Problem:** `codegenie cve sync` is "the *only* network-touching command." This means the typical workflow is: developer runs `cve sync` *occasionally*, runs `remediate` *frequently*. The advisory store on disk can be N days stale at any given remediate invocation, and the design's only mitigation is a tradeoff under "Acknowledged blind spots": "the orchestrator records `advisory.provenance[*].fetched_at` and warns if any source is > N days old." Warns is the operative word; the design does not refuse-to-act on stale CVE data.
   **Why it matters:** Phase 3's exit criterion is "given a Node.js repo with a known npm CVE." A developer who synced 60 days ago and then runs `remediate` against today's CVE will get `AdvisoryNotInStore` — and the design's recovery is "hard fail: `AdvisoryNotInStore` with `codegenie cve sync` hint." That's failure-loud for the specifically-named CVE. But the *other* failure mode — sync was 60 days ago, the CVE *is* in the store, but the patched-version is now superseded by a newer CVE on the patched version itself — produces a silently-wrong bump with no failure signal. Best-practices documents only the loud-failure path.
   **Where:** §Conventions honored → "Recipe → RAG → LLM-fallback"; §Acknowledged blind spots → "Cost-feed staleness."

5. **Problem:** Test fixtures are `.bundle` files (git bundles) committed under `tests/fixtures/repos_bundles/`. The design justifies this against submodules; the real problem is that git bundles freeze the *registry resolution* at bundle creation time. A bundle of `repo_clean_express` has the `package-lock.json` from whenever the bundle was made; the test asserts that `ncu` + `npm install` produces the *expected golden diff*. But `npm install` against today's registry can produce a different lockfile than `npm install` against the registry on bundle-creation day (npm may have re-published, transitive deps may have moved). The golden diff is not testing the resolution logic; it's testing the cached frozen resolution.
   **Why it matters:** The §Test plan promises "every recipe ships a golden diff" and "CI diff fails on drift." If the registry is moving under the goldens, drift fails CI on every npm registry mutation — not on actual recipe-logic regressions. The goldens become brittle to the wrong axis; either the team starts mass-regenerating goldens (defeating the discipline) or the tests start green-painting over actual regressions.
   **Where:** §Components → "Test fixture portfolio — git bundles"; §Test plan → "Golden-file tests."

### Hidden assumptions

1. **Assumption:** Phase 4 can wrap the selector's `Optional[Recipe]` return without editing the selector. The design states this explicitly as the extension-by-addition story.
   **What breaks if wrong:** Phase 4's RAG/LLM fallback needs more than "no recipe matched" — it needs the *signals* that say *why* no recipe matched (was the package outside the recipe catalog? was the semver range untranslatable? was the lockfile dialect unsupported?). The current selector returns `Recipe | None` — a binary. To preserve extension-by-addition, Phase 4 either has to expand the return type (edit) or duplicate the diagnostic logic (smell). Best-practices' "Phase 4 wraps the selector" assumes the selector emits a richer return than `Optional[Recipe]` — but the contract says only `Optional[Recipe]`.

2. **Assumption:** `applies_to.cve_patterns` on the Skill YAML schema is a clean, closed extension.
   **What breaks if wrong:** Phase 7 (distroless migration) will need an analogous `applies_to.image_patterns` or `applies_to.base_image_patterns`. Phase 15 (recipe authoring) will need `applies_to.recipe_patterns`. Each future task class adds an axis; the Skill frontmatter becomes a kitchen-sink schema. The §Risks section acknowledges this as a "Trojan horse" risk and the mitigation is "each new axis requires an ADR." But ADR-gating cannot prevent the schema's growth — it can only document it.

3. **Assumption:** `ncu` is on every developer's PATH and behaves consistently across versions. The tool readiness check enforces presence at startup.
   **What breaks if wrong:** `ncu` is a third-party Node CLI; it has had breaking output-format changes between minor versions. Best-practices pins it in `ALLOWED_BINARIES` per ADR but doesn't pin the version digest the way security-first does for `tools/digests.yaml`. Across `ncu` versions, the JSON output the engine consumes may shift; the recipe-engine output parsing breaks silently or loudly depending on the shift.

### Things this design missed

- **Lockfile policy at all.** Best-practices uses `--ignore-scripts` as a flag (§Components 4) but does not gate registry-redirect, missing `integrity:`, `overrides`/`resolutions` redirection. The exit criterion is "passes the repo's own tests" and the design considers an installable lockfile a success — even if it would install a malicious package. Security-first's `LockfilePolicyScanner` is wholly absent.
- **Worktree concurrency safety on dirty trees.** The transform creates `git worktree add` but the design promises "the user's working tree is never touched" — yet a `git worktree add` from a dirty repo state has well-known failure modes (uncommitted changes in the index can prevent worktree creation; `.git/index.lock` collisions). Best-practices acknowledges `WorktreeAlreadyExists` but not `WorkingTreeDirty`.
- **Audit/chain semantics.** Best-practices emits `audit.json` per run-id but does not chain it across runs the way security-first chains BLAKE3 JSONL. The result is that a malicious actor with write access to `.codegenie/remediation/` can rewrite `audit.json` after the fact. Best-practices treats this as out-of-Phase-3 scope; it should at least be named.

---

## Cross-design observations

### Where do the three disagree?

| Dimension | Performance picks | Security picks | Best-practices picks | What's at stake |
|---|---|---|---|---|
| Recipe engine default | stdlib JSON mutation → `npm install --package-lock-only` | OpenRewrite (with `ncu`/`jq` as recipe-language alternatives, all sandboxed) | `ncu` only, OpenRewrite deferred behind `RecipeEngine` ABC | Whether Phase 4 has a deterministic-failure surface; whether Phase 15 has a recipe ecosystem to author into |
| Diff-generation install model | `npm install --package-lock-only` (paper lockfile) | `npm ci --ignore-scripts` (full install in sandbox) | `npm install --ignore-scripts` (full install on worktree) | Whether the diff is provably installable vs. just provably-paper-resolved |
| Validation test gate | Fast-path subset by depgraph reverse-reachability, full-suite conditional | Full `npm test` inside `TestSandboxProfile` with `--network=none` HARD | Full `npm test` in worktree, parser-driven outcome | Tail latency vs. true-positive coverage vs. test-egress feasibility |
| Sandbox boundary count | One (`run_in_sandbox` chokepoint, scoped/none toggle) | Two (Boundary 1 + `TestSandboxProfile`) | Effectively zero new (Phase 0/1/2 chokepoint reused, no new profile) | How much sandbox surface Phase 5's microVM has to wrap or retire |
| CVE feed cadence | 60-min cron, decoupled from request path | Manual `codegenie feeds sync` ceremony with signature verification | Manual `codegenie cve sync` subcommand, signature-unverified | Staleness window vs. operational friction vs. supply-chain trust |
| Lockfile policy gating | None (validation is the oracle) | Hard-fail on registry-redirect, missing integrity, overrides/resolutions, etc. | None | Whether a malicious lockfile silently produces a malicious patch |
| Three-retry semantics | Same recipe, transient-error retry (network, ETIMEDOUT) | Same recipe, parameter sweep across patched-version range | No retries in Phase 3 (Phase 5 owns it) | Whether Phase 5's gate-retry contract is empty or already filled |
| Public ABCs introduced | Recipe registry (YAML manifest), no top-level Transform ABC | `RecipeRegistry`, `RecipeExecutor`, `TestSandboxProfile` — no top-level Transform ABC | `Transform`, `Validator`, `Recipe`, `RecipeEngine` — four ABCs | How Phase 4/5/7/15 compose — what they extend |
| New top-level packages | 0 explicit (extends existing) | 1 (`remediation/`) | 4 (`cve/`, `transforms/`, `recipes/`, `validation/`) | Sprawl vs. cohesion |
| Cache contract | Lockfile cache keyed on `(pkg-json-hash, lock-hash, registry-digest, npm-version)` | CVE-snapshot-digest + recipe-digest + lockfile-pre-state BLAKE3 | Implicit Phase 1/2 cache reused | Cache-poisoning surface, cross-phase cache reuse |
| Audit | `metadata.json` per attempt | BLAKE3-chained JSONL extended from Phase 2 | `audit.json` per run-id, unchained | Tamper-evidence; downstream phase consumption |

### Which disagreement matters most for *this* phase?

The recipe-engine pick. The roadmap names OpenRewrite first; performance-first and best-practices both drop it; security-first keeps it but offline-only with a maven-mirror ceremony of unspecified custody. Phase 3's *first* responsibility is to introduce the recipe-engine contract that Phase 4, Phase 7, and Phase 15 all extend. Two of the three designs ship without that contract being expressive enough to be extended — performance-first writes raw JSON mutations that aren't recipes at all, best-practices writes a `RecipeEngine` ABC with one implementation that can't author the recipes Phase 15 needs to author. Security-first preserves the contract but at an operational cost that may not survive a real install ceremony. Whichever way the synthesizer goes, this is the choice that determines whether four downstream phases inherit a recipe ecosystem or a recipe stub.

### Where do all three quietly agree on something questionable?

1. **Running the repo's tests locally as part of the validation gate.** All three accept that "passes the repo's own tests" means executing attacker code inside whatever sandbox Phase 3 has. Performance-first runs them in `bwrap`/`sandbox-exec` with a scoped network; security-first runs them with `--network=none` HARD; best-practices runs them on the worktree with no sandbox at all. None of the three say "the real validation boundary is Phase 5's microVM; Phase 3 cannot trustworthily run tests at all." The Phase 5 microVM is supposed to be the load-bearing test-execution boundary per ADR-0012 — but Phase 3 ships with test execution as if Phase 5 were already there. If Phase 5 ends up not landing for any reason, Phase 3's "passes the repo's own tests" gate is structurally compromised across all three designs.

2. **Reuse of Phase 2's `run_in_sandbox` chokepoint.** All three assume Phase 2 shipped a `run_in_sandbox` that is restrictive enough to wrap `npm`, `git`, `npm test`, and (for two designs) `java`. If Phase 2's `bwrap` profile turns out to be too restrictive for `npm install` — e.g., npm needs `$HOME` for its cache, needs `/etc/resolv.conf` for DNS, needs `/tmp` for download staging, needs `getuid()` to return a valid user — none of the three designs have a recovery story. The chokepoint is a hard dependency; if it's wrong, Phase 3 cannot run.

3. **CVE feeds as a separable, fetch-once-read-many concern.** All three treat the CVE feed as a snapshot that's "current enough" for the request. None addresses **retraction**. NVD does retract or substantively edit CVE records; GHSA does too. If a CVE entry is retracted between snapshot-time and run-time, all three designs will apply a fix for a CVE that's no longer flagged. Performance-first refreshes hourly. Security-first signature-verifies a snapshot that may already be retracted. Best-practices refreshes manually. The retraction problem is unaddressed across the board.

---

## Roadmap-level critiques

1. **Does this phase set up problems for later phases (4, 5, 7, 11, 15)?**

   - **Phase 4** needs (a) a clean deterministic-failure signal, (b) a "the recipe ran but the gate failed" branch, (c) a confidence floor below which RAG/LLM kicks in. Performance-first gives Phase 4 only a `skipped: no_recipe` signal — no rich "recipe failed for *this* reason." Security-first gives Phase 4 a parameter-sweep that already does Phase-4-flavored work. Best-practices gives Phase 4 a clean `Optional[Recipe]` boundary but no diagnostic signal beyond null/non-null. None of the three give Phase 4 the structured failure surface ADR-0011 implies.

   - **Phase 5** wraps Phase 3's coordinator with microVM + three-retry gates. Performance-first already implements retry-in-coordinator (3x for transient npm errors) — Phase 5 has to *retire* that or live with two retry layers. Security-first already implements three-retry parameter sweep — same conflict. Best-practices explicitly defers retry to Phase 5 — best alignment. The retry-layer collision is a real risk in two of three.

   - **Phase 7** needs to add `DockerfileBaseImageSwapTransform` (or equivalent) without editing Phase 3 code. Best-practices' `Transform` ABC is the cleanest extension point. Performance-first's recipe-registry-as-YAML-manifest extends, but the "engine = stdlib_json" pattern doesn't generalize to Dockerfile parsing. Security-first's `RecipeRegistry` extends but `LockfilePolicyScanner` doesn't compose with Dockerfile policy.

   - **Phase 11** opens real PRs. All three designs converge on "local branch only, no push" — this is the cleanest cross-design agreement. Phase 11 should compose smoothly.

   - **Phase 15** authors new recipes from solved LLM examples. This is the most sensitive phase for the recipe-engine choice. An LLM authoring `stdlib_json` mutations (performance-first) is authoring code, not data — defeating the "recipes are data" property. An LLM authoring `ncu` parameterizations in YAML (best-practices) is constrained to the surface of one CLI. An LLM authoring OpenRewrite recipes (security-first, were the ceremony viable) has the richest ecosystem to author into. Phase 15's deliverable is meaningfully different depending on Phase 3's choice.

2. **Does it rely on something an earlier phase didn't establish?**

   - All three rely on Phase 2's `run_in_sandbox`. Phase 2's design shipped (`docs/phases/02-context-gather-layers-b-g/` exists) but the actual `run_in_sandbox` profile sufficient for `npm install` is a Phase 2 commitment that Phase 3 audits but does not test in any of the three designs.
   - All three rely on Phase 2's `depgraph.json` being accurate enough for peer-dep traversal. Phase 2's `IndexHealthProbe` is supposed to be the canary for this; none of the three designs name a depgraph-confidence floor for proceeding (performance-first names a halt on `low` but not on `medium`).
   - Security-first relies on `tools/digests.yaml` extending with `npm`, `jq`, `git`, `java`, `openrewrite-jar` — these are *new* pins, not pre-existing ones. Whether Phase 0–2 actually established the pinning *mechanism* is one thing; whether the pins themselves are out-of-the-box for Phase 3 is another. The design assumes the mechanism is reusable; this seems right but is unverified.

3. **Does it violate any load-bearing commitment from §2 or CLAUDE.md?**

   - **§2.4 "Determinism over probabilism for structural changes."** Performance-first does this by ditching the recipe abstraction entirely (`stdlib JSON mutation` for the typical case). It is deterministic, yes, but it skips the "recipes (OpenRewrite, internal rulesets)" half of the commitment — the recipe-as-data property. Best-practices preserves recipe-as-data but with one engine. Security-first preserves the spirit fully.
   - **§2.5 "Extension by addition."** Best-practices commits four new top-level packages and an additive Skill-schema field — sprawl, but additive. Security-first commits one new top-level package — most aligned. Performance-first extends existing packages — least sprawl, but at the cost of not establishing the abstractions Phase 4/7/15 will extend.
   - **§2.7 "Progressive disclosure."** All three honor this for `repo-context.yaml` (read-only). Best-practices is most explicit about `remediation-report.yaml` indexing rather than inlining. Performance-first's `attempts/<id>/metadata.json` indexes; security-first's evidence bundle is comprehensive but doesn't strongly distinguish index from inline.
   - **CLAUDE.md "Single Python project, no services, no databases."** Best-practices' four new top-level packages plus `httpx` (the first outbound-network code under `src/`) push the envelope. Security-first's separate `feeds sync` ceremony introduces a second entry point that is operationally a service-like concern. Performance-first's portfolio-wide `~/.npm` cache is the least service-y; it leans on filesystem-only.
   - **CLAUDE.md "Probes register via decorator (`@register_probe`)."** Best-practices' parallel `@register_transform` and `@register_validator` honor the pattern. Performance-first's recipe registry is YAML-only with no decorator. Security-first's `RecipeRegistry` is class-based but reads YAML — closer to best-practices.

   The biggest live violation across all three is **§2.4** as it touches the recipe contract: two of three designs effectively drop OpenRewrite — the roadmap's named structural-transform engine — and the deterministic-recipe-as-data property is weakened in those two. This is the single critique most likely to require synthesizer intervention.
