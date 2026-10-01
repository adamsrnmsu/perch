# perch watch: a private, own-baseline performance watch for the lead

Date: 2026-10-01. Status: design approved in conversation; spec awaiting review.
Bead: perch-vgo.

## Purpose

The lead needs to notice when someone on the team has moved away from their
own normal: booking well under plan, taking much longer per issue than they
usually do, work sitting still, or estimates overrunning more than usual. Each
flag is a prompt for a conversation, never a verdict.

## Rules this keeps (from perch's CLAUDE.md)

- **No ranking.** Every signal compares a person with their own trailing 8
  weeks, never with anyone else. People are listed in name order.
- **Sample sizes are always shown.** Below the minimum, a signal says "too few
  issues" or "not enough history: n of 8 weeks", never a guess.
- **Private.** The watch never appears in:
  - the weekly drafts;
  - the emails;
  - the quarterly report;
  - anything gitboard or Budgie writes.
- **Read-only.** Nothing is sent.

## Where it shows

- `perch watch [-p NAME | --all]` prints to the terminal.
- `perch monday` writes `projects/<name>/watch/<ISO week>.md`. `projects/` is
  gitignored in the perch checkout; in a separate workspace, add it to your
  own `.gitignore`. Monday ends with one line: "watch: N flags, run perch
  watch" (or "watch: nothing out of line").

## When a signal flags

A signal is "out of line" for a person in a given week when its condition
holds. It **flags** only when it is out of line in at least 3 of the last 4
weeks, so one bad week never flags. With fewer than 4 weeks of history in
`history.jsonl`, the person's signals read "not enough history: n of 8 weeks".

## The four signals

All thresholds are named constants at the top of `perch/core/watch.py`.
They are not configurable yet.

1. **Hours versus plan.**
   - Hours booked over the last 4 weeks are under 70% (`PLAN_SHARE = 0.7`) of
     the planned hours for those weeks.
   - Planned hours come from Budgie's burn-down, `BurndownStatus.expected_on`,
     which already follows `plan.csv`. A week at 0 FTE plans 0 hours, so leave
     and departures never flag.
   - Booked hours are the differences between Budgie readings, interpolated as
     Budgie's `monthly` does.
2. **Slower than their own baseline.**
   - Their hours per closed issue over the last 4 weeks is more than 1.5×
     (`SLOWER = 1.5`) their own figure over the 8 weeks before that.
   - Both windows need at least 5 closed issues (`MIN_ISSUES = 5`); otherwise
     "too few issues".
   - The rates are the own-rate figures perch already records per week in
     `history.jsonl` (`rate`). The type model's per-person factor is shown
     alongside when it exists, because the issue mix can explain a change.
3. **Work stalling.**
   - An issue of theirs has been in a Doing-type column (not Done, not Blocked)
     with no transition for 10 or more working days (`STALL_DAYS = 10`).
   - Blocked issues never count: blocked is someone else's doing.
   - This signal comes from the current board dump, so the 3-of-4 rule does not
     apply. It lists each stalled issue and its age.
4. **Estimates overrun.**
   - Their booked-to-estimate ratio (`perch.core.accuracy.by_person`) is more
     than 1.3× (`OVERRUN = 1.3`) their own trailing 8-week ratio from the
     `accuracy` rows in `history.jsonl`.
   - It applies only at 50% or more estimate coverage, the same rule
     `perch accuracy` uses.

## Wording

Flags are observations with their numbers:

- "Bob: hours per issue 31 vs own 18 over 8 weeks (6 issues; out of line 3 of
  the last 4 weeks)".
- "Alice: #142 in Doing for 12 working days".

The words "underperforming", "slow", "worst" and "best" are never used, and a
test checks for them. A person with no flags reads "nothing out of line".

## Code

- `perch/core/watch.py` (UI-free) builds `Watch(people: list[PersonWatch])`.
  Each `PersonWatch` holds a `Signal(name, flagged, text, sample)` for each of
  the four signals. The inputs are the history rows, the board, the money
  snapshot, estimates, `people:` and today's date.
- `perch/core/history.py` needs a reader for the person and accuracy rows of
  the last N weeks; the rows themselves already hold what is needed.
- `perch/cli.py` gets a thin `watch` command (with `--all` through
  `steps.run_projects`). `monday` writes the week's file after `weekly` and
  prints the one-line summary.

## Testing

All against the hand-checkable world, with history weeks written by the test:

- **Each signal** flagging and not flagging. The 3-of-4 rule: 2 of 4 weeks
  does not flag, 3 of 4 does.
- **Hours versus plan:** a person at 0 FTE for the window does not flag.
- **Stalling:** a Blocked issue is ignored; a Doing issue unmoved for 10
  working days flags.
- **History minimum:** "not enough history: 3 of 8 weeks" with only 3 weeks.
- **Overrun:** below 50% coverage, no ratio and no flag.
- **Wording:** none of the banned words appears in any output.
- **Privacy:** the weekly draft, the `.eml` drafts and the quarterly report
  contain no watch text.

## Out of scope

- Comparing people with each other, or with any team average.
- Configurable thresholds.
- Sending the watch anywhere.
- Using it in any report another person reads.

## Changes during build

- **Hours per issue is computed, not read from history.** The `rate` in
  `history.jsonl` is the year-to-date own rate and person rows hold no closed
  count, so they cannot give a 4-week window or its 5-issue minimum. The watch
  takes booked hours in each window (Budgie's reading interpolation) over the
  issues the board shows closed in it, for the 4 weeks and the 8 before.
- **Booked hours use `budgie.core.monthly._spent_at`**, Budgie's own
  interpolation, imported while private (listed in the contract test; bead
  budgie-8u1 makes it public). Planned hours are `Money.pace`, Budgie's
  `burndown(...)` per allocation with the snapshot's `plan`. A project with
  only plan.csv (no allocations.csv) has no allocation, so hours vs plan says
  so instead of reading.
- **Weeks are anchored on each person's latest reading**, not today: the week
  in progress has no reading and would book 0. The 3-of-4 rule evaluates each
  condition as of each of the last 4 week-ends (estimates: this run and the
  last 3 recorded weeks, each against the 8 recorded weeks before it).
- **The history minimum** applies to hours vs plan, hours per issue and
  estimates; the stall signal reads the current board and always shows.
- **"A Doing-type column"** is a board list from the dump's `columns` that
  gitboard counts as work in progress (not in its `NOT_WIP`: Backlog, Done,
  Failed) and is not Blocked; no column label is Backlog and never stalls. An
  issue waiting on someone else (Blocked, or an unanswered `Q:`, as `perch
  weekly` lists it) never counts. Its age is
  working days (Budgie's `workdays_between`) from the issue's last transition
  to the board's fetch date; an issue with no transition has no age and is not
  listed.
- **A figure too thin to show cannot flag**: when the latest window has too few
  issues, hours per issue reads "too few issues" and does not flag.
- **Privacy is tested against the weekly draft.** The `.eml` drafts are
  Budgie's (they never read perch files) and the quarterly report was not in
  this branch; perch-efu should add its own check.
- **`monday` writes the watch in-process**, after its five steps: it is
  perch's own read of files it already has, so `steps.monday` is unchanged.
