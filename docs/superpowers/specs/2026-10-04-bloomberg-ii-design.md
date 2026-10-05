# Bloomberg feel II: detail pane, events, as-of, tape, alert rules

Epic `perch-zq2`. The first Bloomberg pass (`2026-10-02-bloomberg-tui-design.md`,
epic `perch-ge0`) gave the TUI a command line, drill-down, a Trend column, a
what-changed strip and stoplight toasts. This pass answers five more questions
without leaving it: "what does this project's money look like over the year"
(detail pane, `perch-zq2.1`), "what is coming" (events, `perch-zq2.2`), "what did
it look like in week N" (as-of, `perch-zq2.3`), "what happened, newest first"
(tape, `perch-zq2.4`) and "tell me when my own threshold is crossed" (alert
rules, `perch-zq2.5`). Shared groundwork is `perch-zq2.6` (sources, moves,
trend), `perch-zq2.7` (command grammar and the Budgie contract), `perch-zq2.8`
(CLI), `perch-zq2.9` (docs) and `perch-zq2.10` (Budgie's `burn_series`).

## Decisions (made without a round-trip; each is cheap to change)

| Decision | Choice | Reason |
|---|---|---|
| Who computes the burn chart | Budgie: `budgie.core.burn.burn_series(snapshot)`, also `Snapshot.burn_series()`; perch reads it through `Money.burn` | CLAUDE.md: a number neither tool produces is added to the tool that owns it. The fan, spent and plan dollars are Budgie math |
| Chart scope | Labor only; cost lines printed as a figure and named inside the chart | `Money.spent_cost` excludes cost lines, and the fan runs without `costs=`; the headline headroom includes them, so the chart says so |
| Plan line after the last reading | `Snapshot.planned_through` at each month-end, never interpolated through `spent_at` | `spent_at` stays flat after the last reading, which would flatten the plan |
| Interpolated spend | Months holding a reading draw `█`, interpolated months `▓` (dim), and the pane prints "n readings" | `spent_at` is a straight line between readings, not measured data |
| Detail pane placement | `#detail` between `#projects` and `#output`, hidden below 160 columns by `HORIZONTAL_BREAKPOINTS`, and `v` toggles it | Textual has no `@media`; 160 keeps `#output` wide enough for the 40-column card floor |
| One slow tier | One worker (`_warm_all`, group `slow`) loads `Sources` once per project, then builds the pane's `Detail` and the tape's entries, posting one project at a time | Money costs about 0.4 s cold; loading it per feature would triple that |
| Slow tier freshness | Skip a project whose input mtimes (`sources.stamp`) are unchanged; focus warms without force, `r` and a finished run force | Every P/B/G hop must not recompute 20 fans |
| Slow tier cancellation | Workers check `get_current_worker().is_cancelled` between projects and swallow `RuntimeError` from a closed app | A cancelled thread worker keeps running; this stops the stack-up |
| Shared loaders | `core/sources.py` (`Sources`, `load`, `stamp`) and `core/moves.py` (name-free budget and staffing moves) | Pane, tape and events each re-derived the same files; tape would have called private `quarterly._staffing`, which carries names and dollars |
| Free text | No budget note, no person name anywhere; error entries are the fixed string `<source> unreadable, run perch doctor`; only milestone names and Budgie's holiday names are file text | A note or an exception message can hold a name |
| Weekend holidays | Only Mon to Fri holidays are listed (Budgie's own `federal_holiday_workdays` rule) | `federal_holidays` returns both the 4th and its observed Friday |
| Events scope | One table: budget, staffing, milestone, quarter end, year end, holiday. No cost-line dates, no issue due dates, no perch Monday | Each is either derived, assignee-bound or not in a file |
| `ALL EVTS` | Rows identical across projects collapse into one with project `all (N)` | 20 projects would repeat every holiday 20 times |
| Overdue milestones | An open milestone due before today is listed, text ends `overdue`, no lower bound | Filtering the worst case out hides it |
| Past the Budgie year | A dim note `NAME: window runs past FY26 end: roll the Budgie year` | Budgie's holidays and quarters stop at `span.last` |
| Events/alerts in the TUI | No widget: `e`, `E` and `ALRT` run perch commands into a RunCard | Avoids a second Input and the `on_input_submitted` trap |
| As-of weeks | The union of team-row weeks across projects; `[` from live goes to the second-latest recorded week, `]` there returns to live | The latest recorded week is what live already shows |
| As-of step cells and Flags | `n/a` (dim), distinct from `—` (no figure) | They are not historical, and the watch is not run |
| As-of mixing weeks | Stoplight flip and Trend only when the project has a row for that week; otherwise `—` and empty | A project without that week must not show a neighbour week's flip |
| As-of and background work | Workers capture `asof_week` and deliver through `_if_current(asof, fn, *args)`, which drops a result for another view | A focus refresh that began in one view must not write cells into another |
| As-of banner | Week only, no date | The `date` field is per project and per run |
| Tape | `#tape` replaces `#changes`: newest first, then project order, then `KINDS` order; hidden when empty; `t` toggles | The strip's job, with more kinds |
| Tape dedupe | None. History weeks are already unique per week; two same-day joins both show | Name-free text makes identical lines normal |
| Tape `hours` | Only each project's latest reading date, dim | Weekly readings would flood an 8-row pane |
| Tape in as-of mode | `project_tape(..., asof=week)` filters rows to that week and caps `today` at the week's Sunday | Row `date` fields cannot be trusted as a cutoff |
| Alert rule shape | `when: FIGURE OP NUMBER` and optional `project`, in `perch-home.yaml` | One shape keeps the grammar small |
| Alert shares | `pace` and `prob_over` need `%` or a value of 1 or less | `pace < 80` would be always true |
| Alert freshness | True now, not true the week before, at least two recorded weeks, and the week is this or last ISO week | A restart must not re-toast an old week, and a project onboarded already under a threshold must not fire |
| Alert dedupe | In memory: `(project, rule index, week)`. Not persisted | The stoplight toast has the same limit; the freshness window bounds it |
| Toast flood | More than 3 pending flips and alerts become one summary toast | A first launch with 20 projects |
| Validation | `Home.alerts()` validates; `load_home` stores the raw value | `load_home` raising would abort `perch doctor`; doctor reports the error |

## Rules

- **Team level only.** Nothing new reads a person row or the watch. No new output
  names a person: staffing shows `a join · FTE 0 → 0.5`, with no name field on
  `Event`, `StaffMove` or `TapeEntry`.
- **Budgie owns every number.** perch reads Budgie's `burn_series`, `Budget`,
  `AllocationPlan` and `federal_holidays`; it adds no budget math and no
  simulation. Anything missing goes in Budgie.
- **Nothing is sent**; an alert is a toast, `perch alerts` prints.
- **Never ranks.** Projects keep `home.projects()` order; everything else is
  chronological. Ties break by plan.csv entry order, never by a figure.
- **Honest absence.** A missing figure is `—`, a missing source is a fixed error
  line, and `n/a` means "not historical". Nothing is guessed.
- **UI-free `core/`**: no click, rich or textual. Block builders live in each
  feature's own module (`detail.blocks`, `events.blocks`, `tape.blocks`,
  `alerts.blocks`); `core/blocks.py` is not edited.
- **Off the UI thread.** `sources.load`, `detail.build` and `tape.project_tape`
  run only in workers; a cursor move reads a dict.
- **Strings are `Text`, never rich markup.**

## Feature 1: Detail pane (`perch-zq2.1`)

### What the lead sees

`#detail` redraws as the cursor changes row; no key to press. `v` toggles it.
Top to bottom: the headroom spark over every recorded week with min, max and
`n weeks`; the burn chart (labor dollars: measured spend, plan line, budget
step line, P10 to P90 fan to year end) with a legend line, `labor only · cost
lines $5,000 excluded · 4 readings · fan seeded`; pace and net scope; freshness
(readings through, board dump, history week). Under 2 weeks the spark line reads
`1 week recorded, need 2 for a trend` (or `no weeks recorded yet`). A missing
part prints why (`no hours readings yet`), never a blank. In as-of mode the pane
keeps the cached live data, cuts the spark at the as-of week and replaces the
chart with `burn chart is live only · L`. `perch detail -p NAME` prints the same
as blocks; `DET` is the command-line mnemonic.

### Budgie: `budgie/core/burn.py` (bead `perch-zq2.10`)

```python
@dataclass(frozen=True)
class BurnSeries:
    months: tuple[date, ...]                    # the 12 month-ends of the span
    spent: tuple[float | None, ...]             # labor $ booked by each month-end; None after as_of
    spent_as_of: tuple[date, float] | None      # the latest reading day and labor $ then
    plan: tuple[float | None, ...]              # labor $ planned through each month-end
    budget: tuple[float | None, ...]            # budget in force at month-end minus non-labor
    p10: tuple[float, ...]; p50: tuple[float, ...]; p90: tuple[float, ...]  # () without a fan
    reading_dates: tuple[date, ...]             # distinct reading days, sorted
    as_of: date | None
    note: str = ""                              # "" or why a part is missing

def burn_series(snap: Snapshot) -> BurnSeries
# Snapshot.burn_series(self) -> BurnSeries
```

- `spent`: per person `spent_at(readings, day, span) * hourly_cost`, summed, only for
  people in `snap.people`. `spent_as_of` is a separate field so the tuples stay 12 long.
- `plan`: per person in `snap.allocated`, `snap.planned_through(name, day) * hourly_cost`
  at each month-end directly; a `None` or a person without a rate is skipped.
- `budget`: `(snap.budget_revisions or snap.budget).monthly_amounts(span)` minus `snap.non_labor`.
- Fan: `at_completion(...)`, then `monthly_simulation(eac.people, span, pto_days, iterations,
  seed, actuals=Actuals(eac.readings, snap.readings, snap.plan))` with no `costs`, then
  `.band(10/50/90)`. Months through `as_of` are booked hours, so the bands are equal there.
- No readings: `as_of=None`, no fan, `note="no hours readings yet"`. No people: `note="no people"`.

### perch: `core/money.py`, `core/detail.py`

`Money` gains `burn: Callable[[], BurnSeries] | None = field(default=None, compare=False)`,
set by `money_from` to `snap.burn_series` (lazy: it simulates).

```python
@dataclass(frozen=True)
class Detail:
    project: str
    headroom: dict[str, float]      # week -> headroom, every recorded week
    burn: BurnSeries | None
    as_of: date | None
    dump_on: date | None
    history_week: str | None
    pace: float | None
    net_scope: int | None
    non_labor: float
    note: str                       # "" or why a part is missing; fixed strings only

def build(project: str, src: Sources) -> Detail
def spark_line(d: Detail, upto: str | None = None) -> str
def lines(d: Detail, upto: str | None = None) -> list[str]
def blocks(d: Detail) -> list[dict]
```

`pace` and `net_scope` are read with `.get()` from the latest team row; `history_week` is
`max(..., default=None)`; `dump_on` is `src.board.fetched_on`. A failing `burn()` sets the
note `fan unavailable, run perch doctor`.

### Data sources

`Sources` (`load(home, name)`): config, history rows, `Money`, `Board`, `monday.json`.
No source of its own: `detail.build` takes a `Sources`.

### CLI

`perch detail -p NAME` (engine import inside the body). Blocks: heading `Detail · NAME`; a
dim text line with the spark; figures (readings through, board dump, history week, pace, net
scope, cost lines); table `month, spent, plan, budget, P10, P50, P90` titled `Labor only · cost
lines excluded`. No chart block: the contract has bars only. `DET` goes in `command.MNEMONICS`.

### TUI integration

`Static#detail`; `_paint_detail()` reads `self.details[name]` (a `Detail`) or draws `loading…`;
`on_data_table_cell_highlighted` repaints when `event.data_table.id == "projects"` (card tables
are DataTables too) and bounds-checks the cursor row against `self.names` (it fires during
`table.clear()`); `_report` repaints too because `move_cursor` to the same cell fires nothing.
`burn_lines(d, width) -> Text` draws 8 rows by 12 month columns: `─` budget, `·` plan, `█`
a measured month of spend, `▓` an interpolated month, `▒` the P10 to P90 band.

### Tests (hand-worked, conftest world, `as_of` 2026-04-19)

- Budgie: `spent_as_of == (2026-04-19, 26000.0)` (Alice 200 h x 100 + Bob 120 h x 50).
  02-28: Alice 100 + 60 x 6/28 = 112.857 h, Bob 80 + 40 x 6/56 = 84.286 h, so 11,285.71 + 4,214.29 =
  15,500.00. 03-31: Alice 160 + 40 x 9/28 = 172.857 h, Bob 80 + 40 x 37/56 = 106.429 h, so
  17,285.71 + 5,321.43 = 22,607.14. 01-31: Alice 40 + 60 x 6/28 = 52.857 h, Bob 80 x 31/53 =
  46.792 h, so 5,285.71 + 2,339.62 = 7,625.34. `budget` is 100,000 - 5,000 = 95,000 in all 12.
  `plan[-1]` is 99,600 + 49,800 = 149,400 (996 h each). P10 <= P50 <= P90; equal through March.
- perch: `lines` for headroom 5,000 then 2,000 reads `headroom █▁  $2,000–$5,000  2 weeks`;
  pace 0.85 and net scope -3 read `pace 85% · net scope -3`; the ranking-word and name ban.
- TUI: `down` shows the second project; a cursor move makes zero `sources.load` calls; `r` makes
  one per project; `v` toggles `off`; `burn_lines` glyph rows for a hand-built series.

## Feature 2: Events (`perch-zq2.2`)

### What the lead sees

`EVTS` is a dated list of what is coming, soonest first: date, project, kind, short fact.
`perch events [-p NAME | --all] [--days N]` (default all projects, 30 days; N is 1 to 366).
Command line: `EVTS`, `EVTS 60`, `ALL EVTS`, `ALL EVTS 60`. Keys: `e` runs `events -p NAME`,
`E` runs `events --all`, both into a RunCard.

### Core: `perch/core/events.py`

```python
KINDS = ("budget", "staffing", "milestone", "quarter end", "year end", "holiday")

@dataclass(frozen=True)
class Event:
    day: date; project: str; kind: str; what: str; n: int | None = None

@dataclass(frozen=True)
class Calendar:
    events: tuple[Event, ...]; notes: tuple[str, ...]; errors: tuple[str, ...]

def build(project: str, money: Money, board: Board | None, today: date, days: int = 30) -> tuple[Event, ...]
def span_note(project: str, money: Money, today: date, days: int) -> str
def build_all(home: Home, today: date, days: int = 30, names: list[str] | None = None) -> Calendar
def blocks(cal: Calendar, today: date, days: int) -> list[dict]
```

Window `[today, today + days]`, inclusive. Budget and staffing come from `moves`; a milestone is
the open issues grouped by `(milestone, due)` (`milestone M1 · 3 open (dump 04-20)`, `n=3`; due
before today adds ` · overdue` and has no lower bound); quarter ends are `money.span.quarters[0..2]`
named `2026-Q2` / `FY27-Q1`; the year end is `span.last` (`2026 ends`); holidays are Budgie's
`federal_holidays(money.span)` on weekdays. `build_all` loads `Sources`, skips a project whose money
failed (error line `NAME: budgie unreadable, run perch doctor`), collapses identical
`(day, kind, what)` rows into project `all (N)`, and sorts by `(day, KINDS index, project rank, what)`
with collapsed rows first. Empty: a dim text `nothing in the next 30 days`.

### CLI and TUI

`events` registered in "Look closer"; `-p` and `--all` are exclusive (`UsageError`); output is one
`table(["date","project","kind","what"], ...)`, then dim notes, then a `list` of errors.
`command.py`: `"EVTS": "events"`, `events` in `ALL`, a `_how` branch (zero tokens, or one integer
1 to 366 giving `--days N`). TUI: `COMMANDS["e"] = "events"`, `Binding("E", "events_all", show=False)`,
`_start(..., refresh=False)` for `E` so a read-only command does not reload every row; the refresh flag
is threaded through `_stream` to `_finished`.

### Tests (today 2026-06-01)

- Holidays: `days=30` gives `2026-06-19 holiday` (a Friday) and `2026-06-30 quarter end` (`2026-Q2`):
  2 events. `days=60` adds `2026-07-03` (Independence Day observed; the Saturday 07-04 is dropped): 3.
- Budget: `budget.csv` with a header, `2026-01-01,100000` and `2026-06-15,120000`, and `budgie.yaml` without
  the pin: one event, `budget $100,000 → $120,000`.
- Staffing (Money built with `dataclasses.replace(plan=...)`): Alice 0.5 → 0.75 on 06-10 is `an FTE change · FTE
  0.5 → 0.75`; Carol 0 → 0.5 is `a join · FTE 0 → 0.5`; Bob 0.5 → 0 is `a leave · FTE 0.5 → 0`; no name in `repr`.
- Milestone: M1 on #101 to #103, due 06-12: `n == 3`, `milestone M1 · 3 open (dump 04-20)`; M0 due 05-20 is overdue.
- Missing pieces, same-day ordering, `all (2)` collapse, ban test (ranking words only in perch templates, names
  nowhere), `days=0`, and a window past the year end (today 12-20: year end 12-31, 12-25, one note).

## Feature 3: As-of browsing (`perch-zq2.3`)

### What the lead sees

`[` steps back one recorded week, `]` forward; from live `[` goes to the second-latest recorded week
(live already shows the latest) and `]` from there returns to live; `[` stops at the first week.
`L`, `ASOF LIVE` and `ASOF NOW` return to live; `ASOF W38`, `AS OF W38` and `AS OF 2026-W38` jump. A bare
`Wnn` resolves to the latest recorded week with that number; an unrecorded week toasts
`no week W50 recorded: W36…W38`. With one recorded week `[` toasts and stays live.
`#asof` banner above the table: `AS OF 2026-W37 · history, not live · [ ] step · L live` (reverse warning
style; `#projects` gets class `historical`). Stoplight, Headroom and Trend show that week's recorded team
figures (`—` when that project has no row for it); the seven step cells and Flags show dim `n/a`. The tape
shows what had happened by that week. No stoplight or alert toasts fire while stepping. `i` on Stoplight,
Headroom or Trend shows `team_lines` up to that week; `i` on a step or Flags cell and Enter anywhere toast
`as of W37: n/a, press L for live` and run nothing. Command keys still run live. There is no `perch asof`.

### Core: `perch/core/asof.py`

```python
def weeks(rows_by_project: Iterable[list[dict]]) -> list[str]
def resolve(text: str, recorded: list[str]) -> str | None      # None: live; ValueError otherwise
def step(recorded: list[str], current: str | None, delta: int) -> str | None
def until(rows: list[dict], week: str) -> list[dict]
def team_as_of(rows: list[dict], week: str) -> dict | None
def week_end(week: str) -> date                                # the week's Sunday
def is_command(text: str) -> bool
def argument(text: str) -> str
```

`step` walks positions `recorded[:-1] + [None]` (live is the last); the current week is the last position
when it is `None` or the latest recorded week; moves are clamped; an empty list gives `None`. `until` compares
ISO week strings (zero padded). `team_as_of` never uses the nearest week.

### TUI

`snapshot(home, name, asof=None)`: with `asof` it skips `status()` and `_flags`, builds `n/a` cells, uses
`until` and `team_as_of`, and honours `change(rows)` only when `moved.after == asof` and the spark only when the
row exists. `PerchTUI.asof_week` (declared by the pane task); `_go(base, delta, text)` in
`@work(thread=True, exclusive=True, group="asof")` resolves the target, snapshots every project, recomputes the
tape from the cached `self.src` and posts `_enter_asof`. Workers `_reload`, `_refresh_behind`, `_row_done`
pass `asof` to `snapshot` only when set, and deliver through `_if_current`. `on_input_submitted` checks
`asof.is_command` before `parse`. Known limit: two rapid `[` can read the same base and lose a step.

### Tests (`_weeks`: apollo W36 to W38 = 5000 green, 2000 yellow with budget 100000, -3000 red with 90000;
beta W36, W37 = 1000 green, 500 green)

- Core: `weeks == [W36, W37, W38]`; `step(None, -1) == W37`, `step(W37, -1) == W36`, `step(W36, -1) == W36`,
  `step(W36, +1) == W37`, `step(W37, +1) is None`, `step(None, +1) is None`; one recorded week gives `None`.
- TUI: `[` shows `2026-W37`, apollo `YELLOW`, `$2,000`, `█▁`, reversed (GREEN to YELLOW is that week's flip); beta
  `GREEN`, `$500`, `█▁`; step cells all `n/a`. `[` again: `GREEN`, `$5,000`, `""`. `ASOF W38` on beta: `—`, no
  reverse, no trend. `]` returns to the live cells. No new toast while stepping. Tape at W37 shows
  `W36→W37: GREEN→YELLOW, headroom −$3,000`. `snapshot` runs off the UI thread.

## Feature 4: Tape (`perch-zq2.4`)

### What the lead sees

`#tape`, under the table, newest first, one line per event: `04-19  apollo  failed  monday: board exited 2`.
Hidden when empty; `t` toggles it for the session. `perch tape [-p NAME] [--days N]` prints the same as a
blocks table (default all projects, 56 days, heading `Tape · last 56 days, from files only`).

### Core: `perch/core/tape.py`

```python
HORIZON_DAYS = 56   # trend.WINDOW (8) weeks
KINDS = ("flip", "figures", "budget", "plan", "hours", "board", "closed", "failed", "error")

@dataclass(frozen=True)
class TapeEntry:
    day: date; project: str; kind: str; text: str

def project_tape(src: Sources, name: str, today: date, days: int = HORIZON_DAYS,
                 asof: str | None = None) -> list[TapeEntry]
def merge(by_project: dict[str, list[TapeEntry]], order: list[str]) -> list[TapeEntry]
def tape(home: Home, today: date, days: int = HORIZON_DAYS, names: list[str] | None = None) -> list[TapeEntry]
def blocks(entries: list[TapeEntry], days: int = HORIZON_DAYS) -> list[dict]
```

Entries: `flip`/`figures` from `trend.changes` (newest first; text `describe("", c).strip()`, day = the later row's
`date`); `budget A → B` and `plan: a leave · FTE 0.5 → 0` from `moves`; `hours reading through MM-DD` (latest
reading only); `board fetched, 7 open`; `N issue(s) closed` per `closed_on` day; `failed` from `src.failure`
(`monday: STEP exited CODE`, day of `at`); `error` per `src.errors`. `today - days <= day <= today`; future dated rows
drop. `merge` sorts by `(day desc, project rank, KINDS index)`, stable. In as-of mode `today` is capped at
`asof.week_end(week)` and rows go through `asof.until`. Never read: the watch, person, type or accuracy rows.

### TUI and CLI

`VerticalScroll#tape` holds `Static#tape-body`, under the Horizontal and above the Input. `tape_text(entries)`
renders at most 200 lines as `Text` (hours dim, failed red, error yellow). `trend.changes` is new
(`change()` returns `changes(rows)[-1]`); `trend.money` and `trend.share` become public. `perch tape` in "Look closer".
The existing `#changes` tests (`test_tui.py` lines 1092 to 1116 and 1163) are rewritten against `#tape-body`, and
`_weeks` writes `date.today()` so the 56-day window never rots.

### Tests (today 2026-04-20, window since 02-23)

Board `7 open` on 04-20; the latest reading 04-19 (readings were 01-25, 02-22, 03-22, 04-19); closings: 3 on
03-10 (#5 to #7), 1 on 04-01 (#13), 1 on 04-10 (#8). Order: 04-20 board, 04-19 hours, 04-19 failed, 04-10, 04-01,
03-10. Flips (today 2026-09-10): W36 to W37 `GREEN→YELLOW, headroom −$10,000`, W37 to W38
`YELLOW→RED, headroom −$32,000`. Also budget, plan (no name, no first-day row), two same-day joins both kept, a
duplicated history week, project order, privacy, a corrupt `monday.json` (one fixed error entry).

## Feature 5: Alert rules (`perch-zq2.5`)

### What the lead sees

```yaml
alerts:
  - when: headroom < 50k
    project: apollo      # a project name or ALL; default ALL
  - when: pace < 80%
```

One warning toast per (project, rule, week) when the rule is true on the latest recorded team week, was not
true the week before, there are at least two recorded weeks, and the week is this or last ISO week:
`apollo: headroom < 50k (headroom $42,000, W40)`. `ALRT` (or `apollo ALRT`, `ALL ALRT`) lists every rule with its
state (`true`, `false`, `no data`) and the figure. Read only; nothing is written or sent. `perch doctor` has an
Alerts section.

### Core: `perch/core/alerts.py`

```python
FIGURES = ("headroom", "budget", "spent_cost", "left", "prob_over", "pace", "net_scope",
           "clear_p10", "clear_p50", "clear_p90")
OPS = {"<": lt, "<=": le, ">": gt, ">=": ge, "==": eq, "!=": ne}

@dataclass(frozen=True)
class Rule:  index: int; text: str; figure: str; op: str; value: float; project: str | None
@dataclass(frozen=True)
class State: rule: Rule; project: str; week: str | None; figure: float | None; true: bool | None; fresh: bool

def parse(data: object, projects: Sequence[str], source: str = "perch-home.yaml") -> tuple[Rule, ...]
def evaluate(rules: Sequence[Rule], name: str, rows: list[dict], today: date | None = None) -> list[State]
def toast_text(s: State) -> str
def lines(states: Sequence[State]) -> list[str]
def blocks(states: Sequence[State]) -> list[dict]
```

Errors are `ValueError`s naming the key (`` `alerts[0].when` ``, `` `alerts[0].project` ``, `unknown keys`, `` `alerts` ``).
Numbers take `-`, `$`, `,`, `k`, `m` and `%` (divided by 100); `pace` and `prob_over` need `%` or `abs(value) <= 1`.
A missing figure is `true=None` ("no data"), never false. `fresh` needs `today` to be recent; `today=None`
skips only the recency check.

### Wiring

`workspace.py`: `"alerts"` in `_HOME_KEYS`; `alerts_raw: object = field(default=None, compare=False)` on `Home`;
`Home.alerts()` calls `alerts.parse`. `doctor.alert_checks(home) -> list[Check]`. `command.py`: `"ALRT": "alerts"`,
`alerts` in `ALL`. CLI: `perch alerts [-p NAME | --all]` (default all). TUI: `alert_hits(home, name, rules) ->
list[State]` (returns `[]` on `_ERRORS`), `self.rules` parsed once in `__init__` (a bad file gives `()`), `self.hits`,
`self.fired`, `_set_hits`, and `_report` firing toasts after the flip toasts; skipped in as-of mode.

### Tests

`headroom < 50k` gives value 50,000; `pace < 80%` gives 0.8; `pace < 80` raises; `headroom < -5k` is -5,000. Rows
60,000 then 42,000 in the last two ISO weeks: true and fresh; a third row at 41,000: true, not fresh; one row: not
fresh; stale weeks: not fresh. TUI: exactly one toast, none on `r`, none for a bad file, one summary for four
projects. Workspace and doctor tests as listed in the plan.

## Layout and keys

### Key table

| Key | Action | Notes |
|---|---|---|
| `b` `m` `d` `f` `w` `Q` | run board, monday, doctor, forecast, watch, quarterly on the cursor project | existing |
| `e` | `events -p NAME` | new; `COMMANDS["e"]` |
| `E` | `events --all` | new; hidden in the footer; no row refresh |
| `a` | `monday --all` | existing |
| `:` / `c` | command line / prefilled `CUT ` | existing; adds `EVTS`, `DET`, `ALRT`, `ASOF` |
| `i` | explain the cursor's cell | existing; as-of aware |
| `o` | maximize the newest card | existing |
| `h` / `R` | hours / walk | existing |
| `r` | reload and force the slow tier | existing |
| `v` | toggle `#detail` | new; hidden in the footer |
| `t` | toggle `#tape` | new; hidden in the footer |
| `[` / `]` | as-of one recorded week back / forward | new; `left_square_bracket`, `right_square_bracket`; `]` hidden |
| `L` | back to live | new; hidden |
| `B` / `G` | hop to Budgie / gitboard | existing |
| `?` / `q` / `escape` | help / quit / close the command line | existing |
| Enter | run the cursor's step (toasts in as-of mode) | existing |

`ALRT` and `DET` need no key: `:` runs them.

### Compose tree

```
PerchTUI.compose()                 HORIZONTAL_BREAKPOINTS = [(0, "-narrow"), (160, "-wide")]
  Static#asof                      display none; reverse warning; shown while asof_week is set
  Horizontal                       1fr
    Grid#projects                  3fr   (class `historical` while as-of)
    Static#detail                  2fr   (class `off` toggled by v; hidden by `.-narrow`)
    VerticalScroll#output          2fr
  VerticalScroll#tape              height 8; display none unless it has entries and tape_on
    Static#tape-body
  Input#command                    dock bottom, display none
  Footer
```

`#changes` is gone. `on_mount` paints the grid synchronously, then starts `_warm_all(True)`. State on the app:
`asof_week`, `src`, `stamps`, `details`, `tape_by`, `tape_rows`, `tape_on`, `rules`, `hits`, `fired`
(the existing `changes` and `alerted` stay; attributes never share a name with an imported module).

## Declined

- **Persisting `self.fired` across restarts** (challenge, minor). The freshness window (this or last ISO week) and
  the two-week minimum bound the repeat; a state file is another thing to keep. Documented in the spec and CLAUDE.md.
- **Reading holidays straight from the `holidays` package for next year** (user challenge, important). It would put a
  third-party import in perch; the note `window runs past FY26 end: roll the Budgie year` says it instead.
- **Putting the pane in place of `#output`** (user challenge). Kept beside it; the 160-column breakpoint and the
  existing 40-column card floor are enough.
- **Scrubbing milestone names** (challenge, important, partly). They are the lead's own GitLab milestones. Only error
  text is fixed, and the tests check milestone and error text against the fixture's person names.
- **An "N joins" count line in the tape** (challenge, option). With no dedupe there is nothing to count.
- **`apollo ASOF W38`** (project-prefixed). As-of is one global view; `is_command` requires `ASOF` or `AS OF` first.
- **A `perch asof` command and a tape mnemonic.** View state and a read-only pane need no argv.
- **Fixing the lost step on two rapid `[`.** Cheap to fix later with a pending target; left as a known limit.
- **A durable Budgie-side cache of the fan.** The mtime stamp skips unchanged projects; a disk cache is not needed yet.
