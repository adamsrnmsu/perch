---
description: Walk one project's Monday picture (money, board, watch) and stage the follow-ups.
argument-hint: <project>
allowed-tools: Bash(perch brief:*), Bash(perch cut:*), Bash(perch gb show:*), Bash(perch gb report:*), Bash(perch gb stats:*), Bash(perch gb graph:*), Bash(perch gb estimate:*), Bash(perch gb plan:*), Read, Edit(/@GITBOARD_DIR@/boards/*.yaml)
---

You are walking the lead through project `$ARGUMENTS`: money, then board, then
watch, then staging their calls as cards in the pulled board file. They
decide; you suggest.

**There is no GitLab here.** Work only from what has been pulled: `perch
brief`, the board file and the `perch gb` commands in your allowed tools, all
of which read local files. Never run `push`, `pull`, `sync` or `snapshot`.
When data is stale, say how stale and carry on; it cannot be refreshed from
this session.

**Start.** Run `perch brief -p $ARGUMENTS`. If `perch` is not found, say
"perch is not on PATH; activate its venv (see perch's README) and run /walk
again" and stop. If it fails outright, quote its last line and stop. Quote
figures from `perch brief`, `perch cut` and gitboard; never recompute them.

**1. Brief.** At most five lines: the stoplight and money headline (Team and
Forecast); how many board flags (`perch gb stats -p $ARGUMENTS`, Flow); how many
watch flags; how many follow-ups are open; anything stale under Freshness.
Then stop and ask whether to go on to money.

**2. Money.** What moved since last week (headroom by week), the forecast band
against the budget, and whether the open board's cost to clear fits what is
left. Suggest one call. When the lead asks a what-if, run `perch cut -p
$ARGUMENTS` with `--budget N`, `--fte NAME:DATE:FTE` or `--leaves NAME:DATE` and
quote before → after. A money decision is never a board edit: budget, plan and
FTE live in Budgie's files, which you do not write. End with the exact file and
row for the lead to change, and offer a `followup` card naming the decision
(no figures beyond what the team already sees on the board). Stop with the one
decision you need and your suggested default.

**3. Board.** Read the gitboard checkout's `.claude/commands/board.md` (in
`@GITBOARD_DIR@`) and follow its **Offline** rules: the pulled file is the
board. Two changes: run gitboard as `perch gb <sub> -p $ARGUMENTS` (it fills
in the spec, its `.base` and the dump) instead of `PYTHONPATH=src
.venv/bin/python -m gitboard.cli`, and do not run `plan` yet. The board
file is the `board file:` line under Freshness in `perch brief`. Weigh
priority and milestones against the money section. Stage edits. Stop.

**4. Watch.** The Watch section of the brief is private to the lead. Take each
flag with the sample it rests on, as a prompt for a conversation the lead may
want to have, never a verdict. Ask what, if anything, they want to do. The
watch is conversation only: no card, note, label, title or push may carry
anything from it or be staged because of it. If a flag points at a board move,
the lead gives a reason grounded in the board, and the move goes through the
board rules with that reason. Stop.

**5. Track.** Turn the lead's calls into staged edits in the board file: a new
card labelled `followup` (its title says the decision; unassigned and undated
unless the lead names an owner or a date), or a `notes:` entry on an existing
card. A follow-up the lead calls done gets a note and a move into `Verify`;
name it for the lead to close in GitLab (never close anything yourself). Run
`perch gb plan -p $ARGUMENTS` (it diffs against the pull's `.base`) and show
the table verbatim with one reason per row. Then hand back, three lines: the
board file that holds the staged edits; `perch gb push -p $ARGUMENTS` for the
lead to run where GitLab is reachable (gitboard shows the plan again and asks
y/n); and any `migrate-comments` lines from the board rules.

**Throughout.** Never rank, compare or judge people. Person lines answer "who
has room for this card" and "whose load will not fit", nothing else. The lead
can jump between sections or ask anything; the order is the default. Each stop
ends with the one decision you need and your suggested default.
