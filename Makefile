# perch's own development tasks. Running the apps is `perch` itself:
#   perch projects | init | doctor | hours | monday [--all] | forecast | ...
# (`perch --help`). This file only builds, tests and links.
# The venv lives in .venv here; see install.
#
# Budgie and gitboard live in apps/ (`make install` clones them there).
PERCH_DIR  := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

# One venv for all three apps, inside this checkout. Nothing of ours is built
# or installed into it: scripts/install_env.py pip-installs only the dependencies and
# writes perch/budgie/gitboard wrappers that run the source on PYTHONPATH. An
# editable install would need a .pth file, which macOS's hidden flag breaks
# inside a repo, and a build backend, which an offline machine cannot fetch.
# Offline: PIP_NO_INDEX=1 PIP_FIND_LINKS=/path/to/wheels make install
VENV       ?= $(PERCH_DIR)/.venv
BIN        := $(VENV)/bin
PYTHON     ?= python3
export PYTHONPATH := $(PERCH_DIR):$(PERCH_DIR)/apps/budgie:$(PERCH_DIR)/apps/remote-gitboard/src
NEEDS_311  := import sys; sys.exit(sys.version_info < (3, 11) and "perch needs Python 3.11 or newer: make install PYTHON=python3.12 (and rm -rf $(VENV) if it was made by an older one)")

.DEFAULT_GOAL := help
.PHONY: help bootstrap install link lint format test test-all docs clean

help: ## This menu. Running the apps: perch --help
	@awk 'BEGIN {FS = ":.*## "} \
	  /^##@/ {printf "\n\033[1m%s\033[0m\n", substr($$0, 5)} \
	  /^[a-z-]+:.*## / {printf "  \033[36mmake %-9s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo
	@echo "  Running things: perch projects, perch doctor, perch monday --all"

##@ Setup (once, or after moving the folders)

bootstrap: ## Clone Budgie and gitboard into apps/ (clone only)
	sh $(PERCH_DIR)/scripts/bootstrap.sh

install: bootstrap ## Clone, put every app's dependencies in .venv, write the commands, link them
	$(PYTHON) -c '$(NEEDS_311)'
	test -x $(BIN)/python || $(PYTHON) -m venv $(VENV)
	$(BIN)/python -c '$(NEEDS_311)'
	$(BIN)/python -m pip --version >/dev/null 2>&1 || $(BIN)/python -m ensurepip --upgrade >/dev/null
	-$(BIN)/python -m pip uninstall -q -y perch budgie gitboard
	$(BIN)/python $(PERCH_DIR)/scripts/install_env.py requirements $(PERCH_DIR) > $(VENV)/requirements.txt
	$(BIN)/python -m pip install -q -r $(VENV)/requirements.txt
	$(BIN)/python $(PERCH_DIR)/scripts/install_env.py wrappers $(PERCH_DIR) $(BIN)
	$(MAKE) link
	@echo "installed into $(VENV)."

link: ## Put perch, budgie and gitboard in ~/.local/bin
	@mkdir -p $(HOME)/.local/bin
	for tool in perch budgie gitboard; do ln -sf $(BIN)/$$tool $(HOME)/.local/bin/$$tool; done

##@ Development (perch itself, except test-all)

lint: ## Lint with ruff
	cd $(PERCH_DIR) && $(BIN)/ruff check .

format: ## Format with ruff
	cd $(PERCH_DIR) && $(BIN)/ruff format .

test: ## Run perch's test suite
	cd $(PERCH_DIR) && $(BIN)/pytest

test-all: ## Run all three test suites: Budgie, perch, gitboard
	$(MAKE) -C $(PERCH_DIR)/apps/budgie test VENV=$(VENV)
	cd $(PERCH_DIR) && $(BIN)/pytest -q
	$(MAKE) -C $(PERCH_DIR)/apps/remote-gitboard test

docs: ## Build the HTML docs into docs/_build
	cd $(PERCH_DIR) && $(BIN)/sphinx-build -W -b html docs docs/_build/html

clean: ## Remove caches and build artifacts
	cd $(PERCH_DIR) && rm -rf build *.egg-info .pytest_cache .ruff_cache docs/_build
	cd $(PERCH_DIR) && find . -type d -name __pycache__ -prune -exec rm -rf {} +
