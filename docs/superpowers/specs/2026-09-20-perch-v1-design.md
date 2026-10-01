# perch v1: what the open board means for the budget

Date: 2026-09-20. Status: approved and built (amended where the build found something better).

## Purpose

The lead runs two tools. **gitboard** knows the work: open and closed issues,
who holds them, how they moved. **Budgie** knows the money: each person's
hourly cost, planned hours, hours booked so far, and the budget. Neither can
answer the lead's actual question: *given the work that is open right now, where
does the budget land, and who is carrying more than their hours allow?*

perch is the third component that joins them. It owns the join and the views
and nothing else. Budget math stays in Budgie, board logic stays in gitboard.
If perch needs a number neither tool produces, that number is added to the tool
that owns it.

v1 is terminal-only and run by hand by one person (the lead). No HTML page, no
schedule, no network.

## Inputs

| Input | Source | Contract |
|---|---|---|
| Board history | `gitboard stats --dump FILE` | JSON file. Read-only. perch never calls GitLab. |
| Budget project | a Budgie project directory | Library: perch imports `budgie.core`. It does not parse Budgie's terminal output. |
| Estimates (optional) | flat CSV the lead prepares from business exports | `estimates.csv`, shape below |
| Config | `perch.yaml` | paths, year, and the username-to-name map |

The gitboard dump already carries everything v1 needs per issue: `iid`,
`title`, `state`, `assignee` (GitLab username), `labels`, `created_at`,
`closed_at`, `transitions`, `verdicts`. **No change to gitboard is needed.**

Budgie is a library dependency because perch must re-run Budgie's own
simulation and signal with different hours. A frozen export could not do that.
`budgie.core` is UI-free by design, which is what makes this safe.

### perch.yaml

```yaml
budgie_project: ../budgets/budget/fy26   # directory holding budgie.yaml
board_dump: dumps/team.json              # from `gitboard stats --dump`
estimates: estimates.csv                 # optional
people:                                  # GitLab username -> Budgie name
  asmith: Alice
  bjones: Bob
```

Year, PTO, budget, costs and the people/plan/actuals files all come from the
Budgie project's own `budgie.yaml`. perch does not restate them.

A username with no entry in `people:` is reported once, by name, and its issues
are shown under "unmapped" at the team rate. perch does not guess a match.

### estimates.csv

Business estimates arrive as assorted exports, so perch defines one flat shape
and the lead massages exports into it, the same way Budgie treats every input.

```csv
key,hours,low,high
#14,24,,
epic::billing,400,320,520
```

- `key` starting with `#` is one issue, by iid.
- Any other `key` is a label. The estimate covers every issue carrying it.
- `low` and `high` are optional. Blank means the estimate is a single number.
- No comment lines. A duplicate key is an error that names the key.

## The join

### Hours per issue

For an open issue, in order:

1. Its own `#iid` row in `estimates.csv`, if there is one.
2. Otherwise `factor(assignee) x rate(type)` from the type model, when it fits.
3. Otherwise the assignee's flat **calibrated rate**.

Label-grain estimates are not spread across their issues. They are used only
by `perch accuracy`, where the comparison is made at the grain the estimate was
given.

### Calibrated rate

Budgie's actuals are cumulative readings per person: "through week 20, Alice
has booked 480 h". gitboard knows which issues Alice closed and when.

- For each pair of consecutive readings for a person, one sample:
  `hours booked in the interval / issues they closed in the interval`.
  The first interval runs from January 1 of the Budgie year to the first reading.
  Intervals with zero closed issues are merged into the next one.
- `mode` is total hours over total issues closed across the whole window.
- With three or more samples, `low` and `high` are the smallest and largest
  sample. With fewer, `low = mode = high`, and the output says the rate has no
  spread and how many samples it rests on.
- A person with no readings, or no closed issues, gets the **team rate**: all
  mapped people's hours over all their closed issues. The output marks it.

The rate is **loaded**: meetings, review and support are inside the booked
hours, so they are inside the rate. That is the cost the budget actually pays
per issue.

The rate is a property of the join, not a performance score. perch never ranks
people by it.

### Rates by type

An issue's type is its gitboard `type::` scoped label (`type::bug`,
`type::feature`); an issue without one is type `untyped`.

Hours are booked per person, not per issue, so a person-by-type rate cannot be
read off the data directly. It can be **modelled**, and the model is small on
purpose:

    hours(person, interval) = factor(person) x sum over types of
                              rate(type) x issues closed(person, interval, type)

- `rate(type)` is fitted for the team by least squares over every
  person-interval (`numpy.linalg.lstsq`; numpy arrives with Budgie, so no new
  dependency). **The fit alternates:** type rates are fitted on hours divided
  by each person's factor, the factors are recomputed, and this repeats (25
  rounds), with rates rescaled so that a factor of 1.0 reproduces the team's
  total hours. A single pass, as if everyone worked at the same pace, is biased
  towards whoever closed the most of each type: on exact test data it recovers
  1.496x and 3.10x where the truth is 1.5x and 3.0x.
- `factor(person)` is that person's booked hours over what the team type rates
  predict for the issues they closed. 1.0 is the team's pace.
- A person-by-type cell is `factor(person) x rate(type)`.

That is P + T numbers instead of P x T, which is what makes it fittable from a
few months of weekly readings. The price is stated in the output: the model
assumes a person's factor is the same across types, so it **cannot** show that
someone is quick on bugs and slow on features. Only hours recorded against
issues could show that, and this team does not record them (see "Decided" at
the end).

Guards: types with fewer than 5 closed issues in the window share an `other`
column; if `other` itself has fewer than 5 it is counted with the commonest
type, because a column resting on a couple of issues fits noise. A column whose
rate comes out negative is merged into `other` (or, if it is `other`, into the
commonest type) and the fit is run again, so no rate is ever below zero. With
fewer person-intervals than columns + 2, the fit is refused and perch falls
back to the per-person rate above, saying why. Every modelled
figure is labelled modelled, with the number of intervals it rests on.

When type rates are available, hours per open issue use
`factor(assignee) x rate(type)` instead of the flat per-person rate.

## Commands

### `perch board`

Per person:

| Column | Meaning |
|---|---|
| Open | open issues assigned to them |
| Hours | sum of hours per issue (estimate or rate), shown as likely with low-high |
| Cost | hours x their Budgie hourly cost |
| Left | planned hours left: Budgie's allocated hours (plan-driven when the project has a plan) minus their latest reading |
| Gap | Left minus Hours. Negative means the open board does not fit in their remaining hours |
| Basis | `estimates`, `type model (n intervals)`, `own rate (n samples)`, or `team rate` |

Then the team roll-up, which is the headline:

```
Spent to date            $212,400   (hours booked x rate, as of 2026-05-17)
Cost to clear the board  $148,900   (P10 $131,200 - P90 $171,500)
Planned non-labor         $36,000
Budget (latest)          $780,000
Headroom after the board $382,700   GOOD - 0% chance the board alone breaks the budget
```

"Cost to clear the board" is simulated with Budgie's own `simulate()`: each
person becomes a Budgie `Person` whose hours estimate is their board hours
(low, likely, high). The signal is Budgie's own `signals.evaluate()` against
the budget left after spend to date and non-labor. perch adds no second
simulator and no second set of thresholds.

This is explicitly **not a year forecast**. A board rarely holds the rest of the
year's work. Budgie's estimate at completion is printed beside it for contrast:
one says where the plan lands, the other says what the known work costs.

### `perch accuracy`

Needs `estimates.csv`. Two tables.

**By label** (label-grain rows only): estimated hours against *modelled*
hours, where modelled is the closer's rate for each closed issue plus the
assignee's rate for each open one. Reports the ratio and the dollar difference.
The table header says "modelled": these are not measured per-issue hours,
because none exist. Single-issue `#iid` rows are left out of this table: one
issue's modelled hours are just the person's average rate, so the comparison
would say nothing about that issue. They feed the by-person table instead.

**By person** (this one is measured, not modelled): over the calibration
window, the hours they actually booked against the sum of the `#iid` estimates
on issues they closed. Reports coverage (what share of their closed issues had
an estimate) and refuses to print a ratio below 50% coverage, because a ratio
over a minority of the work says nothing. The ratio is booked hours scaled to
the covered share, over those estimates. Each week's ratio is recorded in
`history.jsonl`; comparing a person with their own earlier weeks is the weekly
report's job (v1.1). People are never compared with each other.

## History

Every `perch board` run appends one JSON line per person, per type and for the
team to `history.jsonl` (week-keyed, so re-running in the same week replaces
that week's rows rather than duplicating them). It records the rates, factors,
open hours, gap, cost to clear, headroom and accuracy ratios of that run.

Nothing in v1 reads this file. It exists because the weekly and quarterly
feedback below are **trends**, and a trend can only start on the day you begin
recording. Same idea as gitboard's `reports/stats.jsonl`.

## Layout

```
perch/
  core/          pure logic, no click, no rich
    config.py    perch.yaml -> frozen dataclass; path resolution
    board.py     load the gitboard dump -> Issue dataclasses; open/closed queries
    estimates.py load estimates.csv
    rate.py      calibrated rate from readings + closed issues; type-rate fit
    history.py   append/replace this week's rows in history.jsonl
    join.py      hours per issue, per-person rows, team roll-up (calls budgie.core)
    accuracy.py  the two accuracy tables
  cli.py         click adapter: `perch board`, `perch accuracy`
  tests/
    conftest.py  one hand-checkable world, built on disk per test
```

Same rule as Budgie: everything under `core/` is UI-free, and the CLI is a thin
adapter. Dependencies: `click`, `rich`, `pyyaml`, `numpy`, and Budgie -- which
`make venv` installs from the sibling checkout and which is deliberately NOT
listed in `pyproject.toml`: it is not published, and whatever answers to that
name on PyPI is not ours to trust. Python 3.10+. Dev extra: `pytest`, `ruff`.

## Errors

- Missing dump, project or estimates file: name the path and which key in
  `perch.yaml` pointed at it.
- The dump's issues carry GitLab usernames; Budgie people carry names. Every
  mismatch is listed once, in one message, not one error per issue.
- A Budgie project with no actuals: `perch board` still runs on estimates and
  the team rate cannot be computed, so issues without an estimate are listed as
  "no basis" and left out of the totals, with a count. perch does not make up a
  default hours-per-issue.
- Dump `fetched_at` and the latest Budgie reading more than 14 days apart:
  a warning, since the two sides describe different moments.

## Testing

- `rate.py`: hand-computed fixtures for the interval samples, the zero-closed
  merge, the fewer-than-three-samples case, and the team fallback.
- `join.py`: a fixture where the expected Hours, Cost, Left and Gap are worked
  by hand; an estimate overriding the rate; an unmapped username.
- Roll-up: seeded, asserts P10 <= P50 <= P90 and that the signal is Budgie's.
- `accuracy.py`: the 50% coverage refusal; modelled vs measured labelled.
- One contract test that imports the exact `budgie.core` names perch uses, so
  a Budgie refactor that breaks perch fails loudly here first.
- CLI tests with click's `CliRunner` against the world `conftest.py` builds,
  whose docstring carries the arithmetic the expected numbers come from.

## What this is for: weekly and quarterly feedback

v1 builds the join and starts the record. The feedback products come next and
are the reason the record exists.

**Weekly, to each contributor** (`perch weekly`, v1.1). One per-person block,
written as markdown so gitboard's Monday digest and Budgie's per-person draft
can carry it instead of the person getting three mails:

- your open board is about X hours and you have Y planned hours left;
- your hours per issue by type against **your own** trailing 8 weeks;
- how your estimates compared with what the work took;
- what is waiting on someone else, and for how long.

Drafts only. Like Budgie and gitboard, perch never sends.

### `perch weekly` design (v1.1)

`perch weekly [--config F] [--person NAME] [--out FILE]`. Read-only: it runs the
same join as `perch board` on the current dump and reads `history.jsonl`, but
never writes history, calls GitLab or sends anything. Markdown to stdout, or to
`--out`; one `## Name` block per mapped person (all of `people:`, or the one
`--person` names). No cross-person table, ever.

Each block has four parts:

1. **Open board vs plan**: open issues and modelled hours (the `board` figure)
   against planned hours left, and the gap. Current run only.
2. **Hours per issue by type**: the person's modelled `factor x type rate` now,
   against the mean of the same figure over their own trailing 8 weeks in
   history (the current week is excluded from the baseline). Labelled modelled.
3. **Estimate accuracy**: this run's measured booked/estimated ratio against the
   mean of their own trailing ratios, with the direction (more than 10% off the
   baseline reads "above"/"below", else "in line").
4. **Waiting on someone else**: open issues carrying gitboard's `Blocked`
   column label, with days since the last move into it (from the dump's
   transitions), plus open issues with an unanswered `Q:` note, listed with the
   question text (the dump's per-issue `questions`, gitboard gb-b23; absent in
   older dumps, read as none). Board data only, so it needs no history.

Degrade rules: a trailing comparison needs at least 4 prior weeks that hold the
figure in question; with fewer the line says `not enough history: 2 of 8
weeks` and shows only the current figure, never a trend from one or two rows.
No fitted type model, no estimates file, or a ratio withheld for coverage each
get a one-line reason instead of a number. Weeks are counted per figure, so a
type that entered the model recently degrades on its own.

**Quarterly, to management** (`perch quarterly`, v1.2). Thirteen weeks of
`history.jsonl` plus Budgie's budget revisions and plan changes:

- budget position and how it moved: spend, estimate at completion, headroom
  after the board, each budget revision;
- where estimates missed, by epic and by type, in dollars;
- throughput and hours per issue by type, as a trend;
- what waiting and rework cost, in dollars;
- team changes from plan.csv (joins, departures, re-plans) and what they did to
  the numbers.

Team and type level by default. A per-person page shows each person against
their own baseline with the sample sizes beside every figure, so a manager sees
how much evidence a number rests on before acting on it.

## Out of scope for v1

`perch weekly` (v1.1) and `perch quarterly` themselves (v1 only records the data
they need).

HTML page, scheduling, mail, any GitLab call, per-type rates, predictability,
rework and wait-time metrics, budget-to-board ("what no longer fits after a
cut"). The last one is the same join run backwards and is the natural v2.

## Decided: hours stay per person, per week

Nobody on the team tracks time against issues, and asking them to would not
survive a month. So the only hours perch will ever have are the weekly
per-person figures in Budgie's `weekly.csv`, and those are themselves closer to
estimates than to a timesheet. Person-by-type therefore stays a **modelled**
figure, permanently, not as a stopgap:

- every such figure carries the "modelled" label and its interval count;
- the constant-factor limitation is printed wherever a person-by-type cell is;
- no figure is shown to more precision than its inputs have (whole hours, and
  rates to the nearest half hour).

GitLab `/spend` and a typed timesheet column were considered and rejected for
this reason. If per-issue hours ever do exist, they would replace the model;
nothing in v1 prepares for that.
