# codewizard-sherpa — imperative surface for humans + CI.
#
# The `check` chain is ordered lint → typecheck → test → fence per
# phase-arch-design.md §Testing strategy / CI gates. `docs` is its own target
# (path-filtered in CI) so it does not gate every `check` invocation.
#
# Recipe shell is POSIX /bin/sh — bash-isms (`[[ ... ]]`, `function NAME()`)
# are forbidden and asserted against by tests/unit/test_makefile_targets.py
# (story S1-03 AC-9). The CI runner is linux/amd64 (sh-as-dash); macOS-only
# constructs would silently diverge.

.PHONY: bootstrap check lint lint-imports typecheck test docs fence audit-verify clean refresh-cassettes _refresh-cassettes-gate

bootstrap:
	@if command -v uv >/dev/null 2>&1; then \
		uv pip install -e ".[dev]"; \
	else \
		python -m pip install -e ".[dev]"; \
	fi

check: lint typecheck test fence

lint:
	@ruff check .
	@ruff format --check .

# Structural cold-start defense (story S1-05). `--no-cache` defeats stale
# mtime-based cache hits that would otherwise serve a stale "ok" verdict
# after a pyproject.toml edit. The `lint` CI job invokes both `make lint`
# AND `make lint-imports`; do not bundle this under `typecheck`.
lint-imports:
	@lint-imports --config pyproject.toml --no-cache

typecheck:
	@mypy --strict src/

test:
	@pytest -q

docs:
	@mkdocs build --strict

# `--no-cov` mirrors CI's `addopts=` override — running the fence subset
# without it would trip pyproject's `--cov-fail-under=85` (the subset
# doesn't cover enough source). The CI `fence` job invokes the Phase 0
# scan directly with `-o "addopts="`; local `make fence` widens the gate
# to include `tests/fence/` (S1-05 AC-3). Path order matters: the Phase 0
# test `test_fence_recipe_invokes_pytest_on_fence_test_path` checks for the
# exact substring `pytest -q tests/unit/test_pyproject_fence.py`, so we
# keep that as a prefix and append the new path + flag.
fence:
	@pytest -q tests/unit/test_pyproject_fence.py tests/fence/ --no-cov

audit-verify:
	@python -m codegenie audit verify

clean:
	@rm -rf .codegenie/ .mypy_cache/ .ruff_cache/ .pytest_cache/ htmlcov/
	@find . -type d -name __pycache__ -prune -exec rm -rf {} +

# ADR-0014 §Consequences — operator refresh path. The gate is split from the
# action: `_refresh-cassettes-gate` is a cheap, side-effect-free policy check
# (testable without spending tokens); `refresh-cassettes` depends on it and
# carries the expensive recording. ADR-0014 §Decision item 6 writes the
# acknowledgement as a CLI flag `--i-understand-this-spends-tokens`; `make`
# targets cannot accept `--flags`, so the same contract is rendered as the
# make variable I_UNDERSTAND_THIS_SPENDS_TOKENS=1. The intent — an explicit,
# command-line-visible acknowledgement — is preserved.
_refresh-cassettes-gate:
	@if [ "$(I_UNDERSTAND_THIS_SPENDS_TOKENS)" != "1" ]; then \
		echo "ERROR: refresh-cassettes spends real Anthropic API tokens."; \
		echo "Re-run with: make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1"; \
		exit 2; \
	fi
	@echo "ack-ok"

refresh-cassettes: _refresh-cassettes-gate
	@echo "Recording cassettes against live Anthropic API…"
	CODEGENIE_LIVE_LLM=1 .venv/bin/pytest -q --record-mode=all -m "uses_anthropic_cassette"
	.venv/bin/python -m codegenie cassette rebuild-lockfile
	@echo ""
	@echo "Recording complete. Review the cassette diffs and commit alongside cassettes.lock."
	@echo "Cassette diffs require CODEOWNERS approval; tag the current steward."
