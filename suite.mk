# One menu for the whole suite: gitboard (the work), Budgie (the money) and
# perch (the join). Lost? Run `make` with no target.
#
# Use it from the pi_suite folder, which holds the three checkouts side by side:
#
#   echo 'include perch/suite.mk' > Makefile   # once, in pi_suite/
#   make                                       # the menu
#
# Or without that file:  make -f perch/suite.mk <target>
#
# Every target cd's into the tool that owns the step, because gitboard finds
# .env and gitboard.toml by walking up from the current directory, and Budgie
# finds its project the same way. Paths below are absolute for that reason.

SUITE      ?= $(abspath $(dir $(lastword $(MAKEFILE_LIST)))..)
PERCH_DIR  ?= $(SUITE)/perch
BUDGIE_DIR ?= $(SUITE)/budgie
GB_DIR     ?= $(SUITE)/remote-gitboard

PERCH_VENV  ?= $(HOME)/Documents/tools/perch
BUDGIE_VENV ?= $(HOME)/Documents/tools/budgie
PERCH       ?= $(PERCH_VENV)/bin/perch
BUDGIE      ?= $(BUDGIE_VENV)/bin/budgie
GITBOARD    ?= PYTHONPATH=$(GB_DIR)/src $(GB_DIR)/.venv/bin/python -m gitboard.cli

# The things you set once. PROJECT empty = gitboard.toml's `project`.
CONFIG      ?= $(PERCH_DIR)/perch.yaml
PROJECT     ?=
DUMP        ?= $(PERCH_DIR)/dumps/team.json
SPEC        ?=
BUDGET_NAME ?= team
_BUDGIE_PROJECT := $(shell sed -n 's/^budgie_project:[[:space:]]*\([^\#[:space:]]*\).*/\1/p' $(CONFIG) 2>/dev/null)
BUDGET      ?= $(if $(_BUDGIE_PROJECT),$(if $(filter /%,$(_BUDGIE_PROJECT)),$(_BUDGIE_PROJECT),$(abspath $(dir $(CONFIG))$(_BUDGIE_PROJECT))),$(SUITE)/budget/$(BUDGET_NAME))

WEEK    := $(shell date +%G-W%V)
WEEKLY  ?= $(PERCH_DIR)/weekly/$(WEEK).md
REPORTS ?= $(GB_DIR)/reports

.DEFAULT_GOAL := help
.PHONY: help lost doctor install link init hours fetch board accuracy weekly \
	digest emails monday show tui pull plan land status forecast budget budget-tui test

##@ Lost? Start here

help: ## This menu. Every other target is listed here.
	@awk 'BEGIN {FS = ":.*## "} \
	  /^##@/ {printf "\n\033[1m%s\033[0m\n", substr($$0, 5)} \
	  /^[a-z-]+:.*## / {printf "  \033[36mmake %-11s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo
	@echo "  Monday:  make hours   then   make monday"
	@echo "  Broken?  make doctor"

lost: help ## The menu, the Monday order, and where each tool's own help lives
	@echo
	@echo "Monday, in order:"
	@echo "  0. make hours     paste timesheet totals into Budgie's weekly.csv"
	@echo "  1. make fetch     one GitLab read, saved as $(DUMP)"
	@echo "  2. make board     perch: cost to clear the board vs hours/budget left"
	@echo "  3. make weekly    perch: per-person markdown blocks"
	@echo "  4. make digest    gitboard: team + per-person digest from the same dump"
	@echo "  5. make emails    Budgie: per-person hours-left drafts"
	@echo "  (steps 1-5 are 'make monday'; nothing is ever sent, you send the drafts)"
	@echo
	@echo "Each tool's own help:"
	@echo "  $(BUDGIE)                  commands grouped by when you need them"
	@echo "  $(BUDGIE) guide            building a budget, five steps"
	@echo "  $(PERCH) --help"
	@echo "  cd $(GB_DIR) && make       gitboard's own menu"

doctor: ## Check installs, tokens, config and how fresh the data is
	@ok()   { printf '  \033[32mok\033[0m    %s\n' "$$1"; }; \
	 bad()  { printf '  \033[31mFIX\033[0m   %s  ->  %s\n' "$$1" "$$2"; }; \
	 age()  { [ -e "$$1" ] && stat -f '%Sm' -t '%Y-%m-%d %H:%M' "$$1" || echo never; }; \
	 echo "Tools"; \
	 $(PERCH) --help >/dev/null 2>&1 && ok "perch runs" || bad "perch does not run" "make install"; \
	 $(BUDGIE) --help >/dev/null 2>&1 && ok "budgie runs" || bad "budgie does not run" "make install"; \
	 (cd $(GB_DIR) && $(GITBOARD) --help) >/dev/null 2>&1 && ok "gitboard runs" || bad "gitboard does not run" "make install"; \
	 command -v perch >/dev/null && command -v gitboard >/dev/null && ok "perch + gitboard on PATH" || bad "perch/gitboard not on PATH (optional)" "make link"; \
	 echo "Config"; \
	 [ -f $(CONFIG) ] && ok "perch.yaml: $(CONFIG)" || bad "no perch.yaml" "make init"; \
	 [ -f $(BUDGET)/budgie.yaml ] && ok "Budgie project: $(BUDGET)" || bad "no Budgie project at $(BUDGET)" "make init"; \
	 [ -f $(GB_DIR)/gitboard.toml ] && ok "gitboard.toml: $$(sed -n 's/^project *= *//p' $(GB_DIR)/gitboard.toml)" || bad "no gitboard.toml" "cp $(GB_DIR)/gitboard.toml.example $(GB_DIR)/gitboard.toml"; \
	 echo "Data (last written)"; \
	 echo "  board dump     $$(age $(DUMP))    make fetch"; \
	 echo "  weekly.csv     $$(age $(BUDGET)/weekly.csv)    make hours"; \
	 echo "  history.jsonl  $$(age $(PERCH_DIR)/history.jsonl)    make board"; \
	 echo "GitLab tokens (gitboard config)"; \
	 cd $(GB_DIR) && $(GITBOARD) config 2>&1 | sed 's/^/  /' || true

##@ Setup (once, or after moving the folders)

install: ## (Re)install all three tools. Fixes "No module named perch/budgie"
	$(MAKE) -C $(BUDGIE_DIR) install VENV=$(BUDGIE_VENV)
	test -x $(PERCH_VENV)/bin/pip || python3 -m venv $(PERCH_VENV)
	$(PERCH_VENV)/bin/pip install -q -e $(BUDGIE_DIR) -e '$(PERCH_DIR)[dev]'
	$(MAKE) -C $(GB_DIR) install
	@echo "installed. 'make link' puts perch and gitboard on your PATH."

link: ## Put `perch` and `gitboard` in ~/.local/bin
	@mkdir -p $(HOME)/.local/bin
	ln -sf $(PERCH) $(HOME)/.local/bin/perch
	$(MAKE) -C $(GB_DIR) link

init: ## Scaffold perch.yaml and a Budgie project: make init BUDGET_NAME=fy26
	@test -f $(BUDGET)/budgie.yaml || { \
	  mkdir -p $(BUDGET) && cd $(BUDGET) && $(BUDGIE) init --here; }
	@test ! -f $(CONFIG) || { echo "$(CONFIG) exists; edit it instead." >&2; exit 1; }
	@mkdir -p $(dir $(DUMP))
	@printf '%s\n' \
	  'budgie_project: $(BUDGET)   # the directory holding budgie.yaml' \
	  'board_dump: $(DUMP)' \
	  '# estimates: estimates.csv   # optional; key,hours,low,high' \
	  'people:                      # GitLab username -> Budgie name' \
	  '  # asmith: Alice' > $(CONFIG)
	@echo "wrote $(CONFIG). Next: fill in people:, set project in $(GB_DIR)/gitboard.toml, make doctor"

##@ Monday (in order; nothing is ever sent)

hours: ## 0. Open Budgie's weekly.csv to paste this week's timesheet totals
	@echo "One row per person: name,week,hours_to_date (cumulative, ISO week $$(date +%V))."
	@echo "Skip this and perch rates go stale. Columns: $(BUDGIE) guide weekly"
	$${EDITOR:-vi} $(BUDGET)/weekly.csv

fetch: ## 1. One GitLab read: board history saved as DUMP for every later step
	@mkdir -p $(dir $(DUMP))
	cd $(GB_DIR) && $(GITBOARD) stats $(PROJECT) --dump $(DUMP)

board: ## 2. perch: cost to clear the open board vs hours and budget left
	$(PERCH) board --config $(CONFIG)

accuracy: ## perch: estimates vs what the work took (needs estimates:)
	$(PERCH) accuracy --config $(CONFIG)

weekly: ## 3. perch: per-person markdown drafts into weekly/<week>.md
	@mkdir -p $(dir $(WEEKLY))
	$(PERCH) weekly --config $(CONFIG) --out $(WEEKLY)
	@echo "wrote $(WEEKLY)"

digest: ## 4. gitboard: team + per-person digest from the same dump
	cd $(GB_DIR) && $(GITBOARD) digest --from $(DUMP) --out $(REPORTS)
	@echo "preview: open $$(ls -td $(REPORTS)/*/*/ | head -1)index.html"

emails: ## 5. Budgie: per-person hours-left drafts (.eml for Outlook)
	cd $(BUDGET) && $(BUDGIE) emails --out-dir emails --no-preview
	@echo "drafts in $(BUDGET)/emails/"

monday: fetch board weekly digest emails ## Steps 1-5 in one go (do `make hours` first)
	@echo
	@echo "Done. Review, then send yourself:"
	@echo "  $(WEEKLY)"
	@echo "  $(REPORTS)/ (newest dated folder)"
	@echo "  $(BUDGET)/emails/"

##@ Board changes (gitboard; the YAML is the staged change)

show: ## The live board as a tree
	cd $(GB_DIR) && $(GITBOARD) show $(PROJECT)

tui: ## The board, interactive: move, assign, comment, then plan/apply
	cd $(GB_DIR) && $(GITBOARD) tui $(PROJECT)

pull: ## Save the live board as boards/<name>.yaml (+ .base for three-way plan)
	cd $(GB_DIR) && $(GITBOARD) pull $(PROJECT) --base

plan: ## Preview your YAML edits vs live: make plan SPEC=boards/x.yaml
	cd $(GB_DIR) && $(GITBOARD) plan $(SPEC)

land: ## Plan, y/n, apply, snapshot, rotate base: make land SPEC=boards/x.yaml
	cd $(GB_DIR) && $(GITBOARD) land $(SPEC)

status: ## Every local board YAML at a glance, no network
	cd $(GB_DIR) && $(GITBOARD) status

##@ Budget (Budgie)

forecast: ## Cost forecast with P10/P50/P90 and the stoplight
	cd $(BUDGET) && $(BUDGIE) forecast

budget: ## Which input files Budgie is reading, and what each feeds
	cd $(BUDGET) && $(BUDGIE) status

budget-tui: ## Budgie interactive: inputs, plan, live forecast
	cd $(BUDGET) && $(BUDGIE) tui

##@ Development

test: ## Run all three test suites
	$(MAKE) -C $(BUDGIE_DIR) test VENV=$(BUDGIE_VENV)
	cd $(PERCH_DIR) && $(PERCH_VENV)/bin/pytest -q
	$(MAKE) -C $(GB_DIR) test
