# perch

Where the budgie sits to watch the board.

perch joins two tools that each know half the story. **gitboard** knows the
work: open and closed issues and who holds them. **Budgie** knows the money:
hourly cost, planned hours, hours booked, the budget. perch answers what
neither can alone: *what does the open board cost, against the hours and the
budget that are left?*

It owns the join and the views, nothing else. Budget math stays in Budgie,
board logic stays in gitboard. perch never calls GitLab and never sends mail.

## Install

```bash
make venv          # venv at ~/Documents/tools/perch; Budgie editable from ../budgie
```

`pyproject.toml` pins Budgie to its GitHub repo by URL (never PyPI, where the
name is not ours), so `pip install` of perch works anywhere your SSH key can reach
the private repo. `make venv`
then installs the sibling checkout editable on top (`BUDGIE_DIR=../budgie` to
override), so local Budgie edits show up in perch at once.

## One entry point for every pi app

`perch` is the single place you run things from. It drives gitboard and Budgie
as separate commands; each app still lives in its own repo. Run it from
anywhere inside a workspace, or set `PERCH_HOME`.

```bash
perch init apollo --home ~/work/pi --gitboard-dir ~/Documents/git/pi_suite/remote-gitboard
perch projects                 # every project, its GitLab project, how fresh its data is
perch doctor                   # tools, config, people names, freshness; FIX lines say what to run
perch hours -p apollo          # paste this week's apollo timesheet totals
perch monday --all             # fetch, board, weekly, digest, emails for every project
```

`-p NAME` picks a project; with only one, it can be left off. Nothing is ever sent.

### The workspace

A project is one funded piece of work: one GitLab project, one Budgie project,
one timesheet charge code. Rates are per project (the same person can cost a
different amount on different work), so each Budgie project has its own
`people.csv`.

```
~/work/pi/
  perch-home.yaml      gitboard_dir: /path/to/remote-gitboard
  projects/apollo/     perch.yaml (gitlab_project: group/apollo), history.jsonl, dumps/, weekly/
  budget/apollo/       the Budgie project: people.csv, plan.csv, weekly.csv, budget.csv
```

Board edits (pull, plan, land, tui) are `gitboard` commands, run from the
gitboard checkout with the project's `gitlab_project`.

### Moving a single-team setup in

1. Create `perch-home.yaml` (one line: `gitboard_dir: /path/to/remote-gitboard`).
2. Make `projects/team/`, then move `perch.yaml`, `history.jsonl` and `dumps/`
   into it.
3. In `perch.yaml`, fix `budgie_project` and `board_dump` (they're relative to
   the file) and add `gitlab_project`.

`perch doctor` names any path that is still wrong.

## Use

```bash
gitboard stats group/project --dump dumps/team.json    # in the gitboard repo
perch board [-p NAME]                                 # or --config FILE
perch accuracy
perch weekly [--person NAME] [--out FILE]        # markdown drafts, nothing sent
```

`perch.yaml`:

```yaml
budgie_project: ../budgets/budget/fy26   # the directory holding budgie.yaml
board_dump: dumps/team.json
gitlab_project: group/project            # what perch fetch reads
estimates: estimates.csv                 # optional
people:                                  # GitLab username -> Budgie name
  asmith: Alice
  bjones: Bob
```

`estimates.csv` is one flat shape you massage business exports into. A key
starting with `#` is one issue; anything else is a label covering every issue
that carries it:

```csv
key,hours,low,high
#14,24,,
epic::billing,400,320,520
```

## What the numbers are

- **Hours per open issue**: its own `#iid` estimate; else the type model; else
  the assignee's own rate; else the team rate; else *no basis* (left out of the
  totals, never guessed).
- **A rate** is hours booked (Budgie's weekly readings) over issues closed
  (gitboard), reading to reading. It is *loaded*: meetings and review are in
  it, because the budget pays for them.
- **Rates by type are modelled, not measured.** Nobody books hours per issue,
  so perch fits one rate per `type::` label for the team and one pace factor
  per person. It assumes a person's pace is the same across types and says so
  wherever it prints one.
- **Cost to clear the board** is simulated by Budgie's own engine and tested
  against the budget left after spend to date and planned non-labor. It is not
  a year forecast; `budgie forecast` is.
- Every `perch board` run records the week in `history.jsonl` (ignored by git:
  it is per-person data). Nothing reads it yet. The weekly and quarterly
  feedback will, and a trend can only start the day you begin recording.

perch never ranks people. A rate is a property of the join, not a score.

## Development

```bash
make test          # perch only; make test-all runs all three suites
make lint
make format
```

Design: `docs/superpowers/specs/2026-09-20-perch-v1-design.md`.
Multi-project design: docs/superpowers/specs/2026-10-01-multi-project-design.md.
