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
git clone https://github.com/adamsrnmsu/perch.git ~/Documents/git/perch
~/Documents/git/perch/scripts/bootstrap.sh
```

perch is the one repo you clone. `scripts/bootstrap.sh` clones Budgie and
gitboard into `apps/` (ignored by perch's git; each stays its own repo with its
own remote and beads), installs all three and puts `perch` and `gitboard` on
your PATH. It leaves an app already in `apps/` alone, so it is safe to re-run.
It ends by printing the `gitboard_dir:` line for your `perch-home.yaml`.

`pyproject.toml` pins Budgie to its GitHub repo by URL (never PyPI, where the
name is not ours), so `pip install` of perch works anywhere your SSH key can
reach the private repo. `make venv` then installs `apps/budgie` editable on top
(`BUDGIE_DIR=` to override), so local Budgie edits show up in perch at once.

## The suite

    perch tui          # or: perch suite -p apollo, to open on apollo

With tmux installed, `perch tui` starts the suite (or comes back to it):
perch, Budgie and gitboard open side by side. `B` and `G` in perch (and `P`,
`B`, `G` in the others) jump between them at once, and each stays where you
left it. Close the terminal and the suite keeps running: `perch tui` again
picks it up. `q` in perch closes everything. It runs on tmux, which you never
have to touch (`brew install tmux` once); without tmux, or with
`perch tui --no-suite`, you get perch alone. If the suite ever wedges (an app
hangs, or tmux was upgraded while it ran), `tmux -L pi kill-server` resets it;
`perch tui` then starts fresh.

## One entry point for every pi app

`perch` is the single place you run things from. It drives gitboard and Budgie
as separate commands; each app still lives in its own repo. Run it from
anywhere inside a workspace, or set `PERCH_HOME`.

```bash
perch init apollo --home ~/work/pi --gitboard-dir ~/Documents/git/perch/apps/remote-gitboard
perch projects                 # every project, its GitLab project, how fresh its data is
perch doctor                   # tools, config, people names, freshness; FIX lines say what to run
perch status                   # each project's Monday steps: ok, stale, todo or FAIL, and the next command
perch hours -p apollo          # paste this week's apollo timesheet totals
perch fetch -p apollo          # refresh the board dump (one GitLab read)
perch digest -p apollo         # gitboard's team and per-person digest, from the same dump
perch emails -p apollo         # Budgie's per-person hours-left drafts (.eml)
perch budget -p apollo         # which input files Budgie reads, and what each feeds
perch forecast -p apollo       # Budgie's cost forecast with P10/P50/P90
perch monday --all             # fetch, board, weekly, digest, emails for every project
perch monday -p apollo --from weekly  # resume at a step after a failure
perch watch -p apollo          # private: anyone out of line with their own last 8 weeks
perch review -p apollo         # Claude's /board on the pulled board, told the budget picture
perch brief -p apollo          # everything /walk reads: freshness, team, people, forecast, watch, follow-ups
perch gb plan -p apollo        # gitboard for the project, from its checkout (show, plan, ...; push/pull need GitLab)
perch walk -p apollo           # Claude walks you through money, board and watch (/walk)
perch tui                      # every project in one table, inside the suite; single keys run the commands
```

`-p NAME` picks a project. Without it, a `perch.yaml` in the current directory is used, then the project folder you are standing in, then the only project. Nothing is ever sent.

### The workspace

A project is one funded piece of work: one GitLab project, one Budgie project,
one timesheet charge code. Rates are per project (the same person can cost a
different amount on different work), so each Budgie project has its own
`people.csv`.

```
~/work/pi/
  perch-home.yaml      gitboard_dir: /path/to/remote-gitboard
  projects/apollo/     perch.yaml (gitlab_project: group/apollo), history.jsonl, dumps/, weekly/, watch/
  budget/apollo/       the Budgie project: people.csv, plan.csv, weekly.csv, budget.csv
```

In `perch tui`, `:` opens a command line: `apollo CUT 700k`, `ALL MON`, `MON weekly`
(the project defaults to the cursor's; `c` opens it with `CUT `). Mnemonics:
BRD board, MON monday, DOC doctor, FCST forecast, WTCH watch, QTR quarterly,
CUT cut, HRS hours, STAT status, FTCH fetch, DIG digest, MAIL emails, WKLY
weekly, BUD budget, REV review (it hands the terminal to Claude; `R` hands it to the walk instead); perch's own command names work too, and `ALL` takes MON,
WTCH, QTR and STAT. `i` explains the cell under the cursor (checks, the team's
recent weeks, a step's state). `o` opens the newest output card full screen. The Trend column is the team's headroom over its
last 8 recorded weeks, the line above the table says what moved since the week
before, and a stoplight that flipped shows in reverse and toasts once per
session. All of it comes from the team row of `history.jsonl`: no names, nothing
from the watch, nothing sent.

Board edits (pull, plan, push, tui) are `gitboard` commands, run from the
gitboard checkout with the project's `gitlab_project`.

`perch review` is the review after a pull: it opens Claude in the gitboard
checkout on `/board <gitlab_project>` (label, prioritise, flag; stage the edits,
show `plan`, push only on your yes) and appends perch's team line from
history.jsonl (stoplight, budget, headroom, hours left, cost to clear, headroom
by week) so the priority calls weigh the money, plus the latest week's person
rows in name order (open cards, hours to clear, hours left, gap; no rate, cost
or accuracy) so it can say who has room for a stuck or unowned card. Claude is
told never to rank, compare or judge people; nothing from the watch goes in.
It refuses until `boards/<name>.yaml` is pulled and names the
`gitboard pull` to run; run `perch board` first or Claude is told there is no
week recorded.

`perch walk` (or `/walk apollo` in a Claude session opened in the workspace)
is the Monday walk-through. Claude reads `perch brief`, then goes money →
board → watch, stopping after each for your call, and ends by staging your
calls as `followup` cards and notes in the pulled board file, with gitboard's
plan table. The session needs no GitLab: it works from what `perch monday`
and `perch gb pull` already wrote. Push later where GitLab is reachable:
`perch gb push -p apollo`. Next week's brief lists the follow-ups still open;
close one in GitLab and the next pull drops it. Money calls end as the file
and row for you to edit (perch never writes Budgie's files), and the watch is
talked through, never written anywhere. `perch init` and `perch walk` install
`.claude/commands/walk.md` into the workspace and add the gitboard checkout to
`.claude/settings.json` so Claude can edit the board file; an installed
`walk.md` is yours and is never overwritten (`perch doctor` says when it
differs from perch's copy). `perch` must be on the session's PATH.

### Moving a single-team setup in

1. Create `perch-home.yaml` (one line: `gitboard_dir: /path/to/remote-gitboard`).
2. Make `projects/team/`, then move `perch.yaml`, `history.jsonl` and `dumps/`
   into it.
3. In `perch.yaml`, fix `budgie_project` and `board_dump` (they're relative to
   the file) and add `gitlab_project`.

`perch doctor` names what is still wrong; `perch fetch` rewrites the board dump.
It asks gitboard for about nine months of history (`gitboard stats
--history-days 276`; the stats summary stays 7 days), so `perch quarterly` can
set a quarter beside the one before it.

### Layout and cross-repo work

    ~/Documents/git/perch/        this repo
      apps/budgie/                Budgie's repo (git@github.com:adamsrnmsu/budgie.git)
      apps/remote-gitboard/       gitboard's repo

Suite-level docs and decisions live in perch's `docs/`. A change that spans
repos is one perch epic with a child bead in each repo it touches, each
naming the epic; each repo is branched, merged and pushed on its own.

## Use

```bash
gitboard stats group/project --history-days 276 --dump dumps/team.json  # gitboard
perch board [-p NAME]                                 # or --config FILE
perch accuracy
perch weekly [--person NAME] [--out FILE]        # markdown drafts, nothing sent
perch cut [--budget N] [--leaves NAME:DATE]... [--fte NAME:DATE:FTE]...
perch quarterly [-p NAME | --all] [--quarter 2026-Q3] [--out DIR]
```

`perch cut` is the join run backwards: what no longer fits after a budget cut
or a plan change. With flags it is a what-if (today's files, then today's
files with the change; nothing is written). With none it compares the last
week `perch board` recorded against today's files. It shows the team's hours
left, budget, cost to clear, headroom and stoplight before → after, each
person's hours left in name order, whose open issues need a new owner, and
each milestone's open work. It never says which issues to drop.

`perch quarterly` writes the funder's quarterly report as an Outlook draft,
`projects/<name>/quarterly/<quarter>.eml`, plus a `.md` copy: budget position
and Budgie's forecast at completion, estimate misses in dollars (MODELLED),
issues closed and hours booked per ISO week, blocked issue-days, and the
quarter's `plan.csv` changes. The default is the last complete quarter of the
Budgie year. Quarters follow the Budgie project's `year_start`: a calendar year
names them `2026-Q3`, a fiscal year `FY27-Q1`. It is rebuilt from the readings, budget.csv, plan.csv and the
board dump, so a source that does not cover the quarter says so in the report.
When the dump's history (gitboard's `since`) reaches back over the whole
previous quarter of the same year, its totals (issues closed, hours, hours per
issue, blocked issue-days) sit beside this quarter's.
Team level only; nothing is sent.

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
  it is per-person data). `perch weekly` and `perch cut` read it, and a trend
  can only start the day you begin recording.

perch never ranks people. A rate is a property of the join, not a score.

### The watch (private)

`perch watch [-p NAME | --all]` prints, and `perch monday` writes
`projects/<name>/watch/<ISO week>.md` and ends with one line (`watch: N flags,
run perch watch`). It is for the lead only: it never goes into the weekly
drafts, the emails or a report. Each person is compared only with their own
figures; a signal flags only when it was out of line in 3 of the last 4 weeks,
and each line shows the sample it rests on:

- **hours vs plan**: hours booked over 4 weeks under 70% of what Budgie's
  burn-down plans for them (plan.csv; a week at 0 FTE plans 0 hours);
- **hours per issue**: over 4 weeks, more than 1.5x their own over the 8
  weeks before, with 5 closed issues in each window;
- **work in Doing**: an issue in a work-in-progress board list (not Backlog,
  Done, Failed or Blocked) that has not moved for 10 working days; waiting on
  an answer (`Q:`) never counts (this one reads the current board);
- **estimates**: booked over estimate above 1.3x their own trailing ratio, at
  50% estimate coverage or more.

With under 4 weeks in `history.jsonl` the first, second and fourth read `not
enough history: n of 8 weeks`.

## Development

```bash
make test          # perch only; make test-all runs all three suites
make lint
make format
```

Design: `docs/superpowers/specs/2026-09-20-perch-v1-design.md`.
Multi-project design: docs/superpowers/specs/2026-10-01-multi-project-design.md.
