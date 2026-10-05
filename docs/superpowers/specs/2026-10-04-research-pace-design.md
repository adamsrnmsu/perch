# Research pace: planned vs booked hours and opened vs finished issues

Bead: perch-w1d. Replaces the earned-value design recorded in that bead
(2026-10-02).

## Why not earned value

perch's projects are research. Earned value assumes a fixed scope whose value
is planned up front; research scope grows as the team learns, estimates are
guesses, and a dead end is progress that EV scores as nothing. CPI/SPI would
mostly measure estimate quality. Two figures carry the useful half of EV
without a model:

- **Pace**: hours booked against hours planned (EV's AC against PV, with no
  EV). Both numbers are Budgie's.
- **Scope**: issues opened against issues finished. Whether open work is
  narrowing or widening is the research early warning; a burn-up's scope line.

Cost per finished issue (`total_per_issue`, `previous`) and flow health
(gitboard's `cycle_median`, `stuck`) already exist and are not touched.

## Where it goes

Into `perch quarterly` (the `.eml` draft and its `.md`) and the team row of
history.jsonl. No new module, no new command, no TUI change.

## Core: `perch/core/quarterly.py`

### Pace

`Position` gains two hour figures for the quarter, over the same window as
`spent_quarter` (quarter start through `read_to`):

- `booked_quarter: float | None` -- `_team(money, start, read_to, cost=False)`.
  None when `spent_quarter` is None (no readings in the quarter).
- `planned_quarter: float | None` -- `Money.team_planned(start - 1 day,
  read_to)`: each planned person's Budgie plan (their pace line, or plan.csv's
  `allocated_hours` for someone planned without an allocation, Budgie's rule
  when there is no allocations.csv) sampled on their reading days and
  interpolated between them with Budgie's `spent_at`, exactly as booked hours
  are. The plan counts working days while readings interpolate by calendar
  day; reading the plan at the pace line directly inflated pace in any window
  that starts or ends mid-week (an on-plan team read 143% in a quarter's
  first week; review finding, 2026-10-04). None when nobody is planned or
  `read_to` is None.

The ratio is not stored; renderers compute `booked / planned` when both are
known and planned is above zero.

### Scope

`Week` gains `opened: int | None`: issues whose `created_on` falls in the week.
It is None exactly when `closed` is None (outside the dump's coverage, or no
dump), and also when any issue in the dump has no `created_on` (a dump older
than gitboard's `created_at`): a partial count would undercount what opened.

`Quarter.total` sums `opened` like `closed`. A `Quarter.net_scope` property is
`total.opened - total.closed` when both are known, else None. The previous
quarter's `Week` gets `opened` by the same rule, so it sits beside it.

No new dataclass: scope is the throughput table's weeks, one more column.

### `quarter_to_date(board, money, today) -> dict`

For `perch board`'s history row, without `build()`'s Monte Carlo forecast:
the quarter of `money.span.quarters` containing `min(today, money.as_of or
today)`, `through` and `read_to` as `build()` sets them, and returns
`{"pace": booked / planned or None, "net_scope": int or None}`. Outside the
Budgie year both are None. `build()` and `quarter_to_date()` share the window code (`build()` already has a local named `to_date`), so
the history row and the report never disagree about a quarter.

## Report: `perch/core/report_mail.py`

Neutral wording throughout: counts and hours, never "grew", "narrowed",
"behind" or "ahead". No colour, no threshold.

- **1. Budget position**: two rows after the labor rows:
  `Hours planned <span>` and `Hours booked <span>` (`_hours`, `—` when None),
  then a paragraph `Booked N% of planned hours.` when both are known. When
  planned is None: `No plan to compare booked hours with.`
- **3. Throughput**: an `Opened` column before `Closed`; the total and the
  previous-quarter rows carry it too. Under the table, when `net_scope` is
  known: `Opened N, closed M in <closed_span or quarter span>: a net change of
  +K open issues.` (sign always shown, `0` as `no net change`). When a dump
  lacks creation dates: `The board dump has no creation dates; run
  `perch fetch` to count opened issues.`

## History: `perch/core/history.py`, `perch board`

`rows_for` takes `quarter: dict | None = None` and merges it into the team
row, so the row gains `pace` and `net_scope` (None when unknown). `perch
board` calls `quarterly.quarter_to_date(board, money, board.fetched_on)` (the day the history week is keyed on) and passes it. Existing
history lines without the keys stay valid: `history.figures` already skips
missing values.

## Not changed

TUI, watch, trend, weekly, monday output, emails other than the quarterly
draft. No person-level figure: pace and scope are team totals, and the report
names nobody next to them.

## Tests (against the conftest world, worked by hand)

- Pace for the conftest quarter: planned from the pace line, booked from the
  readings; the ratio in the report text.
- No plan or allocations: `planned_quarter` is None and the report says so.
- A team booking exactly to plan reads a pace of 1 in a quarter that starts
  mid-week; plan.csv without allocations.csv is still planned.
- Scope: conftest issues gain `created_at` for a few; per-week `opened`, the
  total, `net_scope` positive and a negative-net case.
- A dump without `created_at` on any issue: every `opened` is None and the
  report carries the `perch fetch` note.
- A week outside the dump: `opened` None, like `closed`.
- `quarter_to_date`: the history team row's `pace` and `net_scope`; both None outside
  the Budgie year.
- Report wording: the new lines asserted as exact text, so a verdict word
  cannot slip in (a whole-report word scan would trip on Budgie's own signal
  rationale).

## Docs

CLAUDE.md lines for `core/quarterly.py` and `core/history.py`; README and the
docs reference's quarterly section; bead perch-w1d's title and design.

## Follow-up (bead, not this work)

Surface the `pace` / `net_scope` trend for the lead (TUI cell or `trend.py`
spark) once a few weeks are recorded.
