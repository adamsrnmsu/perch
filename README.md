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
name is not ours), so a plain `pip install` of perch works anywhere. `make venv`
then installs the sibling checkout editable on top (`BUDGIE_DIR=../budgie` to
override), so local Budgie edits show up in perch at once.

## One menu for every pi app

perch is the single place you run things from. Its `Makefile` drives gitboard,
Budgie and perch; each app still lives in its own repo with its own Makefile.

```bash
make               # the menu; `make lost` adds the Monday order
make install       # all three tools
make init          # perch.yaml and a Budgie project under budget/
make doctor        # installs, tokens, config, how fresh the data is
make hours         # paste this week's timesheet totals
make monday        # fetch, board, weekly, digest, emails; nothing is sent
```

The other apps are looked for beside this checkout (`../budgie`,
`../remote-gitboard`). Anywhere else: `make BUDGIE_DIR=... GB_DIR=... <target>`.

A new app joins the menu with a `<APP>_DIR ?=` variable, a `##@` section and a
line in `make lost`. Its code stays in its own repo.

## Use

```bash
gitboard stats group/project --dump dumps/team.json    # in the gitboard repo
perch board                                            # reads ./perch.yaml
perch accuracy
perch weekly [--person NAME] [--out FILE]        # markdown drafts, nothing sent
```

`perch.yaml`:

```yaml
budgie_project: ../budgets/budget/fy26   # the directory holding budgie.yaml
board_dump: dumps/team.json
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
