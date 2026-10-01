# perch watch Implementation Plan

**Goal:** a private, own-baseline watch per person (`perch watch`, and a file
plus a one-line summary from `perch monday`).

**Spec:** `docs/superpowers/specs/2026-10-01-performance-watch-design.md`.
**Bead:** perch-vgo. Rulings made while building are in the spec's "Changes
during build".

## Constraints

- `perch/core/` has no click/rich; the CLI stays thin.
- No budget math in perch: planned hours are Budgie's
  `BurndownStatus.expected_on`, booked hours Budgie's reading interpolation
  (`budgie.core.monthly._spent_at`), working days Budgie's `workdays_between`.
  Every new `budgie.core` name goes in `perch/tests/test_contract.py`.
- No ranking: people in name order, each against their own figures only.
- `history.py` and `steps.monday` stay unchanged (two other agents edit
  `cli.py`/`history.py`; the CLI change is appended, not reordered).

## Tasks

1. **Board: columns and the last move.** `perch/core/board.py`: `Board.columns`
   (the dump's `columns`), `Issue.last_moved` (last transition stamp).
   Test: `perch/tests/test_board.py`.
2. **Money: Budgie's pace and booked hours.** `perch/core/money.py`:
   `Money.pace` (a `BurndownStatus` per allocation, built with the snapshot's
   readings and `plan`), `Money.booked(name, start, end)`,
   `Money.planned(name, start, end)`. Tests: `perch/tests/test_money.py`,
   `perch/tests/test_contract.py`.
3. **The watch.** `perch/core/watch.py`: constants, `Signal`, `PersonWatch`,
   `Watch`, `watch(...)`, `render(...)`, `summary(...)`; reuses
   `weekly.WINDOW/MIN_WEEKS/_thin/_prior_weeks`. Tests in
   `perch/tests/test_watch.py`: each signal flags and not; 2 of 4 does not flag,
   3 of 4 does; 0 FTE never flags; Blocked ignored, 10 working days flags;
   "not enough history: 3 of 8 weeks"; under 50% coverage no ratio; banned
   words.
4. **CLI.** `perch watch [-p|--all|--config]` (in-process, `--all` through
   `steps.run_projects`); `monday` writes `projects/<name>/watch/<week>.md`
   after its steps and prints the one line. `Home.watch_path`. Tests:
   `perch/tests/test_cli_run.py` (monday writes the file, steps unchanged),
   `perch/tests/test_watch.py` (command, privacy: the weekly draft carries no
   watch text).
5. **Docs.** CLAUDE.md architecture line, README command list,
   `docs/reference.md` automodule, spec "Changes during build".
