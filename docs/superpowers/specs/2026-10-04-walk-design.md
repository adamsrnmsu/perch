# /walk: a guided Monday session in Claude Code

Date: 2026-10-04
Bead: `perch-3se`
Status: approved in chat, awaiting spec review
Leaves `perch review` as it is.

## Problem

After `perch monday` the numbers are pulled, and `perch review` opens Claude on
gitboard's `/board` with the team and person lines appended. That covers the
board only. The lead still has to read the forecast, the budget status and the
private watch alone, decide what to do about each, and remember those calls
until next week. Nothing carries the decisions forward.

## Goal

The lead opens Claude Code in the perch workspace and types `/walk apollo`.
Claude walks them through one project in order (money, board, watch), stops
after each section for their calls, and ends by staging those calls as
GitLab cards and notes through gitboard, pushed only on a yes. Next Monday's
`/walk` opens with whatever is still open from last time.

```
$ cd ~/work/pi && claude
> /walk apollo
```

## Decisions

- **Entry point is a slash command in a session the lead already has open**,
  not a CLI that spawns Claude with a hidden system prompt. `perch walk -p NAME`
  and TUI `R` are shortcuts that run `claude "/walk NAME"` in the workspace.
- **One project per session** (`/walk NAME`), like `perch review`.
- **Covers money, board and watch.** The weekly drafts, digest and emails stay
  out: the lead checks those before sending.
- **Tracking lives in GitLab, through gitboard.** Follow-ups are cards and
  notes staged in `boards/<name>.yaml`, shown with `plan`, pushed on a yes.
  They carry a `followup` label so the next session can find them.
- **perch owns the walk.** Money and watch logic stay in perch; gitboard's only
  change is one allowed label. Board rules stay single-sourced in gitboard's
  `.claude/commands/board.md`.
- **`perch review` is unchanged**, so nobody's current habit breaks.

## Pieces

### `perch brief [-p NAME]` (new, read-only)

Prints everything the walk needs as one block, in this order:

1. **Freshness**: the board dump's `fetched_at`, the board YAML's pull time
   (its `.base` mtime), the last week recorded in `history.jsonl`, the ISO
   week today. Claude says so when they lag.
2. **Team**: `team_lines(rows)` as `perch review` uses it (stoplight, chance
   the board breaks the budget, budget, spent, headroom, hours left, cost to
   clear P10/P50/P90, headroom by week).
3. **People**: `people_lines(rows, config.people)`: name order, open cards,
   hours to clear, planned hours left, gap. No rate, cost or accuracy.
4. **Forecast**: Budgie's `forecast` output for the project (the same step
   `perch forecast` runs), captured.
5. **Budget status**: Budgie's `status` output (the step `perch budget` runs),
   captured.
6. **Watch**: this ISO week's `projects/<name>/watch/<week>.md`, verbatim.
7. **Follow-ups**: issues in `<gitboard_dir>/boards/<name>.yaml` labelled
   `followup`: `#iid`, title, column, assignee, due date. `gitboard pull`
   lists only open issues, so a follow-up leaves the brief when it is closed
   in GitLab and the board is pulled again.

Each part that cannot be produced prints one line saying why and what to run
(`watch: none for 2026-W41; run perch monday`, `board: no boards/apollo.yaml;
run perch gb pull -p apollo`), and the rest still prints. A failed Budgie step
prints its last stderr line, not a traceback. perch reads only local files and
runs Budgie; it never calls GitLab, as today.

### `perch gb SUB [-p NAME] [ARGS...]` (new, thin passthrough)

Runs gitboard from its checkout via the existing `steps.gitboard`, with the
target filled in: the spec `boards/<name>.yaml` for `show --from`, `plan`,
`push`, `estimate`, `graph --from`; `--from <board_dump>` for `stats`, so the
board's flag counts come from the same dump as the money (no second GitLab
read); the `gitlab_project` for `report` and `pull --base`. `SUB` is one of `show report stats graph estimate plan
push pull`; anything else is refused. Extra `ARGS` pass through (`push --yes`,
`graph -M <milestone>`).

Without it, Claude in the workspace would `cd` into the gitboard checkout and
the permission patterns would name that path. With it, `allowed-tools` is
`Bash(perch gb show:*)` and so on, the same on every machine.

### `walk.md` (new slash command, shipped in the perch package)

Lives at `perch/commands/walk.md` in this repo and is installed to
`<workspace>/.claude/commands/walk.md`:

- `perch init` writes it when the workspace has none.
- `perch walk` writes it when missing, then launches.
- An installed copy is the lead's file: never overwritten. `perch doctor` flags
  it missing, or different from the shipped copy, with a FIX line (delete it
  and run `perch walk` to reinstall).

Frontmatter `allowed-tools`: `Bash(perch brief:*)`, `Bash(perch cut:*)`,
`Bash(perch gb show:*)`, `report`, `stats`, `graph`, `estimate`, `plan`,
`push` likewise, `Read`, and `Edit(//<gitboard_dir>/boards/*.yaml)` (Claude
Code's absolute-path form; `install` substitutes the path from
`perch-home.yaml`). `pull` is not in the list: a stale board is the lead's
call.

The board YAML stays in the gitboard checkout, where `perch review`, gitboard's
TUI and `snapshots.jsonl` expect it. That directory is outside the session's
working directory, so `install` also adds the gitboard checkout to
`permissions.additionalDirectories` in `<workspace>/.claude/settings.json`
(creating the file, or adding the one entry to an existing list; nothing else
in it is touched). A bare `claude` in the workspace can then edit the board
without `--add-dir`.

### `perch walk [-p NAME]` (new)

Installs `walk.md` if missing, then runs `claude "/walk NAME"` in the
workspace root. TUI `R` on a project row runs it instead of `perch review`;
`REV` stays bound to `perch review`.

### gitboard `board.md` (one-line amendment, in remote-gitboard)

"`stale` and `re-verify` are the follow-up labels" becomes "`stale`,
`re-verify` and `followup` are the follow-up labels". `followup` marks a card
the lead created to track a decision.

## The script (body of `walk.md`)

`$ARGUMENTS` is the project name. Run `perch brief -p $ARGUMENTS` first; if it
fails outright, say so and stop.

1. **Brief.** Five lines at most: stoplight and the money headline; how many
   board flags (from `perch gb stats`); how many watch flags; how many
   follow-ups are still open; anything stale from the freshness lines. Stop.
2. **Money.** What moved since last week (headroom by week, forecast band
   against budget), and whether the open board fits the money left. Suggest
   the call. The lead may ask what-ifs: run `perch cut --budget N`,
   `--fte NAME:DATE:FTE` or `--leaves NAME:DATE` and quote before → after.
   Stop with the decision needed and a suggested default.
3. **Board.** Read gitboard's `.claude/commands/board.md` and follow it, with
   gitboard run as `perch gb <sub> -p $ARGUMENTS` in place of `PYTHONPATH=src
   .venv/bin/python -m gitboard.cli`. Weigh priority and milestones against
   the money section. Use person rows only to say who has room. Stage edits;
   do not `plan` yet. Stop.
4. **Watch.** Each flag, with the sample it rests on, as a prompt for a
   conversation the lead may want to have. Ask what, if anything, they want to
   do. Stop.
5. **Track.** Turn the lead's calls into staged edits: a new card labelled
   `followup` (title says the decision; unassigned and undated unless the lead
   names an owner or a date), or a `notes:` entry on an existing card. A
   follow-up the lead calls done gets a note and a move into `Verify`, and
   Claude names it for the lead to close in GitLab (`board.md`: never close);
   the next pull drops it. Run `perch gb plan -p $ARGUMENTS`, show
   the table verbatim with one reason per row, and push with `perch gb push
   -p $ARGUMENTS --yes` only after a yes in this conversation.

The lead can jump between sections or ask anything; the order is the default,
not a gate. Each stop ends with the one decision Claude needs and its
suggested default.

## Rules (in `walk.md`)

- Quote figures from `perch brief`, `perch cut` and gitboard; never recompute
  them.
- Never rank, compare or judge people. Person rows answer "who has room for
  this card" and "whose load will not fit", nothing else.
- **The watch is conversation only.** No card, note, label, title or push may
  carry anything from it, or be staged because of it. If a flag points at a
  board move, the lead gives a reason grounded in the board, and the move goes
  through the Board rules with that reason. This keeps the watch spec's rule
  that the watch never appears in anything gitboard writes. The `plan` table
  is the lead's check before anything leaves.
- **Money calls are not board edits.** Budget, plan and FTE changes live in
  Budgie's files, which perch never writes. A money decision ends as the
  suggestion plus the exact file and row for the lead to edit, and, if they
  want it tracked, a `followup` card naming the decision (no figures beyond
  what the team already sees on the board).
- Every `board.md` rule holds: one write path, never close or delete, never
  out of Verify, push only a `plan` the lead has just seen.

## Changes to written rules

- Watch spec (`2026-10-01-performance-watch-design.md`), "Private": add that
  the watch reaches Claude in `/walk` for conversation with the lead, and still
  never appears in anything gitboard or Budgie writes.
- `REVIEW_RULES` in `steps.py` stays as it is for `perch review`; `walk.md`
  carries its own copy of the people rule.
- README: `perch brief`, `perch gb`, `perch walk` in the command list; a
  "The walk" paragraph beside `perch review`.

## Out of scope

- Every project in one session. Run `/walk` per project.
- Checking the weekly drafts, digest or emails.
- Writing Budgie files from the session.
- A user-level `/walk` that works from any directory. The command is a
  workspace file; `PERCH_HOME` still lets `perch brief` find the workspace.
- Enforcing the watch rule in code (scanning staged notes for watch text). The
  `plan` review is the gate; add a check if a leak ever happens.

## Testing

- `perch brief` on `projects/test`: sections print in order; a missing watch,
  board YAML and history each print their one-line reason and the rest still
  prints.
- Contract test: `perch brief` output carries no `$`, rate or cost column in
  the people section (same idea as the watch privacy contract test).
- `perch gb`: argv per `SUB` (spec vs `gitlab_project` target, passthrough
  args, cwd and `PYTHONPATH` from `steps.gitboard`); an unknown `SUB` is
  refused.
- `walk.md`: frontmatter parses; every `Bash(perch X:*)` in `allowed-tools`
  names a real perch command; install substitutes the gitboard path; install
  never overwrites an existing file.
- `settings.json`: install creates it with `additionalDirectories`, adds the
  entry to an existing file once, and keeps every other key.
- Doctor: missing and differing `walk.md` each give a FIX line.
- Manual, before calling it done: one bare `claude` + `/walk test` session in
  the workspace, checking that the `allowed-tools` patterns and the board
  `Edit` run without prompting. If the absolute-path `Edit` rule does not
  match, fall back to `perch walk` passing `--add-dir` and say so in the
  README.

## Work split

1. `perch brief` (+ tests).
2. `perch gb` (+ tests).
3. `walk.md`, install in `init`/`walk`, doctor check (+ tests).
4. `perch walk` and TUI `R`.
5. gitboard `board.md`: `followup` label (remote-gitboard repo, its own bead).
6. Docs: README, watch spec amendment.
