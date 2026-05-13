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

.PHONY: bootstrap check lint typecheck test docs fence audit-verify clean

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

typecheck:
	@mypy --strict src/

test:
	@pytest -q

docs:
	@mkdocs build --strict

fence:
	@pytest -q tests/unit/test_pyproject_fence.py

audit-verify:
	@python -m codegenie audit verify

clean:
	@rm -rf .codegenie/ .mypy_cache/ .ruff_cache/ .pytest_cache/ htmlcov/
	@find . -type d -name __pycache__ -prune -exec rm -rf {} +
