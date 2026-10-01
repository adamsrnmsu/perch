# perch's own development tasks. Running the apps is `perch` itself:
#   perch projects | init | doctor | hours | monday [--all] | forecast | ...
# (`perch --help`). This file only builds, tests and links.
#
# The other apps are looked for beside this checkout. Anywhere else:
#   make BUDGIE_DIR=/path/to/budgie GB_DIR=/path/to/remote-gitboard <target>
PERCH_DIR  := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
BUDGIE_DIR ?= $(abspath $(PERCH_DIR)/../budgie)
GB_DIR     ?= $(abspath $(PERCH_DIR)/../remote-gitboard)
# A relative override would break after the first cd.
override BUDGIE_DIR := $(abspath $(BUDGIE_DIR))
override GB_DIR     := $(abspath $(GB_DIR))

# The venvs live OUTSIDE the repos (see Budgie's CLAUDE.md for the macOS
# hidden-.pth trap that makes an in-tree venv a bad idea).
PERCH_VENV  ?= $(HOME)/Documents/tools/perch
BUDGIE_VENV ?= $(HOME)/Documents/tools/budgie
BIN         := $(PERCH_VENV)/bin
PERCH       ?= $(BIN)/perch

.DEFAULT_GOAL := help
.PHONY: help install link venv lint format test test-all docs clean

help: ## This menu. Running the apps: perch --help
	@awk 'BEGIN {FS = ":.*## "} \
	  /^##@/ {printf "\n\033[1m%s\033[0m\n", substr($$0, 5)} \
	  /^[a-z-]+:.*## / {printf "  \033[36mmake %-9s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo
	@echo "  Running things: perch projects, perch doctor, perch monday --all"

##@ Setup (once, or after moving the folders)

install: ## (Re)install all three tools. Fixes "No module named perch/budgie"
	$(MAKE) -C $(BUDGIE_DIR) install VENV=$(BUDGIE_VENV)
	test -x $(BIN)/pip || python3 -m venv $(PERCH_VENV)
	$(BIN)/pip install -q -e '$(PERCH_DIR)[dev]'
	$(BIN)/pip install -q -e $(BUDGIE_DIR)
	$(MAKE) -C $(GB_DIR) install
	@echo "installed. 'make link' puts perch and gitboard on your PATH."

link: ## Put `perch` and `gitboard` in ~/.local/bin
	@mkdir -p $(HOME)/.local/bin
	ln -sf $(PERCH) $(HOME)/.local/bin/perch
	$(MAKE) -C $(GB_DIR) link

##@ Development (perch itself, except test-all)

# perch pulls Budgie from GitHub; the editable checkout goes on after so it wins.
venv: ## Create perch's venv: perch with dev + docs, then Budgie from its checkout
	python3 -m venv $(PERCH_VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e '$(PERCH_DIR)[dev,docs]'
	$(BIN)/pip install -e $(BUDGIE_DIR)

lint: ## Lint with ruff
	cd $(PERCH_DIR) && $(BIN)/ruff check .

format: ## Format with ruff
	cd $(PERCH_DIR) && $(BIN)/ruff format .

test: ## Run perch's test suite
	cd $(PERCH_DIR) && $(BIN)/pytest

test-all: ## Run all three test suites: Budgie, perch, gitboard
	$(MAKE) -C $(BUDGIE_DIR) test VENV=$(BUDGIE_VENV)
	cd $(PERCH_DIR) && $(BIN)/pytest -q
	$(MAKE) -C $(GB_DIR) test

docs: ## Build the HTML docs into docs/_build
	cd $(PERCH_DIR) && PYTHONPATH=. $(BIN)/sphinx-build -W -b html docs docs/_build/html

clean: ## Remove caches and build artifacts
	cd $(PERCH_DIR) && rm -rf build *.egg-info .pytest_cache .ruff_cache docs/_build
	cd $(PERCH_DIR) && find . -type d -name __pycache__ -prune -exec rm -rf {} +
