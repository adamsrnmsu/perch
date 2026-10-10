# perch's own development tasks. Running the apps is `perch` itself:
#   perch projects | init | doctor | hours | monday [--all] | forecast | ...
# (`perch --help`). This file only builds, tests and links.
#
# Budgie and gitboard live in apps/ (`make install` clones them there).
PERCH_DIR  := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

# The venvs live OUTSIDE the repos (see Budgie's CLAUDE.md for the macOS
# hidden-.pth trap that makes an in-tree venv a bad idea).
PERCH_VENV  ?= $(HOME)/Documents/tools/perch
BUDGIE_VENV ?= $(HOME)/Documents/tools/budgie
BIN         := $(PERCH_VENV)/bin
PERCH       ?= $(BIN)/perch

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

install: bootstrap ## Clone, install all three tools and link them. Fixes "No module named perch/budgie"
	test -x $(BUDGIE_VENV)/bin/pip || $(MAKE) -C $(PERCH_DIR)/apps/budgie venv VENV=$(BUDGIE_VENV)
	$(MAKE) -C $(PERCH_DIR)/apps/budgie install VENV=$(BUDGIE_VENV)
	test -x $(BIN)/pip || python3 -m venv $(PERCH_VENV)
	$(BIN)/pip install -q -e '$(PERCH_DIR)[dev,docs]'
	$(BIN)/pip install -q -e $(PERCH_DIR)/apps/budgie
	$(MAKE) -C $(PERCH_DIR)/apps/remote-gitboard install
	$(MAKE) link
	@echo "installed."

link: ## Put `perch` and `gitboard` in ~/.local/bin
	@mkdir -p $(HOME)/.local/bin
	ln -sf $(PERCH) $(HOME)/.local/bin/perch
	$(MAKE) -C $(PERCH_DIR)/apps/remote-gitboard link

##@ Development (perch itself, except test-all)

lint: ## Lint with ruff
	cd $(PERCH_DIR) && $(BIN)/ruff check .

format: ## Format with ruff
	cd $(PERCH_DIR) && $(BIN)/ruff format .

test: ## Run perch's test suite
	cd $(PERCH_DIR) && $(BIN)/pytest

test-all: ## Run all three test suites: Budgie, perch, gitboard
	$(MAKE) -C $(PERCH_DIR)/apps/budgie test VENV=$(BUDGIE_VENV)
	cd $(PERCH_DIR) && $(BIN)/pytest -q
	$(MAKE) -C $(PERCH_DIR)/apps/remote-gitboard test

docs: ## Build the HTML docs into docs/_build
	cd $(PERCH_DIR) && PYTHONPATH=. $(BIN)/sphinx-build -W -b html docs docs/_build/html

clean: ## Remove caches and build artifacts
	cd $(PERCH_DIR) && rm -rf build *.egg-info .pytest_cache .ruff_cache docs/_build
	cd $(PERCH_DIR) && find . -type d -name __pycache__ -prune -exec rm -rf {} +
