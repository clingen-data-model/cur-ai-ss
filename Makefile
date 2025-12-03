# Typical usages of make for this project are listed below.
# 	make				: see `make ci`
#	make ci				: run most checks required for completing pull requests
#	make test			: run all tests and generate coverage report
#	make lint			: run all linter rules required for completing pull requests

PY_DIRS_MAIN := lib
PY_DIRS_TEST := test
PY_DIRS_ALL := $(PY_DIRS_MAIN) $(PY_DIRS_TEST)

ANSI_GREEN := \033[0;32m
ANSI_RESET := \033[0;0m

# Run all CI checks.
.DEFAULT_GOAL := ci
.PHONY: ci
ci: all-lint test
	@echo
	@echo "$(ANSI_GREEN)====== All linters, tests, and security checks PASS ======$(ANSI_RESET)"

# Run all linters.
.PHONY: all-lint
all-lint: lint type format
	@echo
	@echo "$(ANSI_GREEN)====== All linters PASS ======$(ANSI_RESET)"

# Individual task definitions.

.PHONY: test
test:
	@uv run pytest $(PY_DIRS_TEST) --cov=$(PY_DIRS_MAIN) --cov-report=term-missing --cov-report=xml

.PHONY: lint
lint:
	@uv run ruff check $(PY_DIRS_MAIN)

.PHONY: format
format:
	@uv run ruff format --check $(PY_DIRS_ALL)

.PHONY: type
type:
	@uv run mypy $(PY_DIRS_MAIN)
