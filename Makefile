# The venv lives OUTSIDE the repo, next to Budgie's (see Budgie's CLAUDE.md for
# the macOS hidden-.pth trap that makes an in-tree venv a bad idea).
VENV ?= $(HOME)/Documents/tools/perch
BUDGIE ?= ../budgie
BIN := $(VENV)/bin

.PHONY: help venv lint format test docs clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

venv: ## Create the venv, install Budgie from the sibling checkout, then perch
	python3 -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e $(BUDGIE)
	$(BIN)/pip install -e '.[dev,docs]'

lint: ## Lint with ruff
	$(BIN)/ruff check .

format: ## Format with ruff
	$(BIN)/ruff format .

test: ## Run the test suite
	$(BIN)/pytest

docs: ## Build the HTML docs into docs/_build
	PYTHONPATH=. $(BIN)/sphinx-build -W -b html docs docs/_build/html

clean: ## Remove caches and build artifacts
	rm -rf build *.egg-info .pytest_cache .ruff_cache docs/_build
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
