# Bloomberg feel II Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a detail pane, an events calendar, as-of browsing, a tape and lead-only alert rules to `perch tui`, each with a CLI twin, without perch redoing any Budgie math.

**Architecture:** Budgie gains `burn_series` (the monthly spend, plan, budget and P10/P50/P90 fan); perch reads it through `Money.burn`. Two shared UI-free modules, `core/sources.py` (one load of config, history, money, board and `monday.json` per project) and `core/moves.py` (name-free budget and staffing changes), feed `core/detail.py`, `core/events.py` and `core/tape.py`; `core/asof.py` and `core/alerts.py` are pure over history rows. The TUI gets one slow tier (a worker that fills `self.src`, `self.details` and `self.tape_by` per project) so cursor moves only read dicts.

**Tech Stack:** Python 3.13, Textual 8.2.8 (`HORIZONTAL_BREAKPOINTS`, `CellHighlighted`), click, rich `Text`, Budgie (`budgie.core`), pytest through `asyncio.run(app.run_test())`, Sphinx with `-W`.

**Spec:** `docs/superpowers/specs/2026-10-04-bloomberg-ii-design.md`. Epic `perch-zq2`.

## Global Constraints

- Test command: `~/Documents/tools/perch/bin/pytest PATH -v`; Budgie tests run from `apps/budgie` (its own git repo): `cd apps/budgie && ~/Documents/tools/perch/bin/pytest budgie/tests/test_burn.py -v`.
- Lint gate per task that edits code: `cd ~/Documents/git/perch && ~/Documents/tools/perch/bin/ruff check . && ~/Documents/tools/perch/bin/ruff format --check .` (`make lint` is `ruff check .`).
- `perch/core/` is UI-free: no click, rich or textual imports. `perch/cli.py` and `perch/tui.py` stay thin: engine imports inside commands.
- perch never calls GitLab, never redoes Budgie math, never sends anything, never ranks people. Team-level rows only; no person row, no watch data, no person name in any new output.
- Free text from files never reaches the pane: no budget note; error entries are the fixed string `<source> unreadable, run perch doctor`.
- Only `perch/core/money.py` (and the Budgie task) may import `budgie.core` beyond what `perch/tests/test_contract.py` lists; `events.py` reads Budgie through `Money`, `moves` and `federal_holidays` (contract task).
- Block builders live in each feature module; `perch/core/blocks.py` is not edited.
- Attributes on `PerchTUI` never share a name with an imported module (`self.tape_rows`, `self.asof_week`); modules are imported as `from perch.core import asof, detail, sources, tape`.
- Strings go to widgets as `Text`, never rich markup.
- `make docs` runs `sphinx -W`: docstrings in new modules are plain text, no stray `*` or single backticks.
- Hand-checkable numbers come from `perch/tests/conftest.py`: 2026, week(n) is ISO week n's Sunday (week 4 = 01-25, 8 = 02-22, 12 = 03-22, 16 = 04-19), Alice $100/h readings 40, 100, 160, 200, Bob $50/h readings 80 (wk 8) and 120 (wk 16), budget 100,000 pinned, one cost line of 5,000, `seed: 1`, dump fetched 2026-04-20 with 7 open issues.
- Beads: `perch-zq2.1` to `.5` exist. Create `perch-zq2.6` (shared cores), `.7` (command and contract), `.8` (CLI), `.9` (docs) and `.10` (Budgie `burn_series`) with `bd create` under epic `perch-zq2` (see `bd create --help` for `--parent` and `--deps`); `.10` blocks `.1`, `.6` blocks `.1`, `.2`, `.4`, `.5`. Claim each bead when starting its task and close it with a reason when its last task lands.
- Commit messages end with the attribution lines the session's reminder gives. Do not push.

## Review Focus

The five input classes most likely to bite. Each is pinned by a test tagged `# review-focus N` in its owning task.

1. **A project with no hours readings (or no people, or no budget).** The pane, the burn series and events must say why a part is missing, never raise or draw an empty fan. Pinned in Task 1 (`test_no_readings_gives_a_note_and_no_fan`) and Task 3 (`test_no_readings_gives_a_note`).
2. **An unreadable or missing source** (corrupt `monday.json`, no board dump, a Budgie load that raises). One fixed error entry, every other source still reads. Pinned in Task 2 (`test_a_corrupt_failure_file_is_one_error_and_the_rest_load`) and Task 6 (`test_a_corrupt_failure_file_is_one_fixed_error_entry`).
3. **Two identical-looking changes on one day** (two joins both read `a join`). Both must show. Pinned in Task 2 (`test_two_joins_on_one_day_both_stay`) and Task 6 (`test_two_joins_on_one_day_both_show`).
4. **Old or one-week history** (rows without `pace` or `net_scope`, a single recorded week, a stale latest week). `—`, `no data` or `not fresh`, never a guessed figure or a repeat toast. Pinned in Task 3 (`test_pace_and_scope_come_from_the_latest_team_row`), Task 5 (`test_a_project_without_that_week_has_no_team_row`) and Task 7 (`test_a_row_without_pace_is_no_data_and_never_fires`, `test_one_week_and_stale_weeks_are_not_fresh`).
5. **A window that crosses the Budgie year end, or a weekend holiday** (today 12-20; the 4th on a Saturday). The year-end note appears, and only the observed weekday is listed. Pinned in Task 4 (`test_a_window_past_the_year_end_says_so`, `test_weekend_holidays_are_not_listed`).

---

## Wave 0: Budgie (separate repo)

### Task 1: Budgie `burn_series` (bead perch-zq2.10; parallel-safe: yes)

**Files:**
- Create: `apps/budgie/budgie/core/burn.py`
- Modify: `apps/budgie/budgie/core/project.py` (add `Snapshot.burn_series`)
- Test: `apps/budgie/budgie/tests/test_burn.py`

**Interfaces:**
- Consumes (Budgie): `Snapshot` fields `span, people, readings, allocated, planned_through, non_labor, budget, budget_revisions, plan, pto, iterations, seed`; `spent_at`, `Actuals`, `monthly_simulation` (`budgie.core.monthly`); `at_completion` (`budgie.core.eac`); `last_day_of_month` (`budgie.core.csvio`); `Budget.monthly_amounts(span)`.
- Produces: `BurnSeries` (frozen dataclass: `months: tuple[date, ...]`, `spent: tuple[float | None, ...]`, `spent_as_of: tuple[date, float] | None`, `plan: tuple[float | None, ...]`, `budget: tuple[float | None, ...]`, `p10/p50/p90: tuple[float, ...]`, `reading_dates: tuple[date, ...]`, `as_of: date | None`, `note: str = ""`), `burn_series(snap: Snapshot) -> BurnSeries`, `Snapshot.burn_series(self) -> BurnSeries`.

- [ ] **Step 1: Write the failing test**

Create `apps/budgie/budgie/tests/test_burn.py`:

```python
"""burn_series: the monthly chart series, in labor dollars (the conftest world of perch)."""

from datetime import date

import pytest

from budgie.core.burn import BurnSeries, burn_series
from budgie.core.project import load_snapshot


def week(n: int) -> date:
    return date.fromisocalendar(2026, n, 7)


def _write(path):
    (path / "budgie.yaml").write_text("year: 2026\nbudget: 100000\nseed: 1\n")
    (path / "people.csv").write_text(
        "name,hourly_cost,hours_low,hours_mode,hours_high\n"
        "Alice,100,900,1000,1100\nBob,50,900,1000,1100\n"
    )
    (path / "allocations.csv").write_text(
        "name,fte,hours_spent\nAlice,0.5,0\nBob,0.5,0\n"
    )
    (path / "weekly.csv").write_text(
        "name,week,hours_to_date\n"
        "Alice,4,40\nAlice,8,100\nAlice,12,160\nAlice,16,200\nBob,8,80\nBob,16,120\n"
    )
    (path / "costs.csv").write_text(
        "name,category,date,amount,low,high,recurring\n"
        "Laptops,materials,2026-03-15,5000,,,no\n"
    )


@pytest.fixture
def snap(tmp_path):
    _write(tmp_path)
    return load_snapshot(tmp_path)


def test_months_and_readings(snap):
    b = burn_series(snap)
    assert isinstance(b, BurnSeries)
    assert len(b.months) == 12
    assert (b.months[0], b.months[-1]) == (date(2026, 1, 31), date(2026, 12, 31))
    assert b.as_of == week(16) == date(2026, 4, 19)
    assert b.reading_dates == (week(4), week(8), week(12), week(16))


def test_spent_is_booked_dollars_through_as_of_then_none(snap):
    b = burn_series(snap)
    assert b.spent_as_of == (date(2026, 4, 19), 26000.0)  # 200 h x 100 + 120 h x 50
    # 01-31: Alice 40 + 60 x 6/28 = 52.857 h; Bob 80 x 31/53 = 46.792 h
    assert b.spent[0] == pytest.approx(7625.34, abs=0.01)
    # 02-28: 11,285.71 + 4,214.29
    assert b.spent[1] == pytest.approx(15500.0, abs=0.01)
    # 03-31: Alice 160 + 40 x 9/28 = 172.857 h; Bob 80 + 40 x 37/56 = 106.429 h
    assert b.spent[2] == pytest.approx(22607.14, abs=0.01)
    assert all(v is None for v in b.spent[3:])  # 04-30 is after as_of


def test_budget_is_the_labor_budget_every_month(snap):
    assert burn_series(snap).budget == (95000.0,) * 12  # 100,000 - 5,000 of cost lines


def test_plan_reaches_the_allocation_at_year_end_and_never_goes_flat(snap):
    b = burn_series(snap)
    # 996 h each at the end: Alice 99,600 + Bob 49,800. Before as_of is not flat after it.
    assert snap.planned_through("Alice", date(2026, 12, 31)) == pytest.approx(996)
    assert b.plan[-1] == pytest.approx(149400.0)
    assert all(b.plan[i] < b.plan[i + 1] for i in range(11))


def test_fan_is_ordered_and_booked_months_have_no_spread(snap):
    b = burn_series(snap)
    assert len(b.p10) == len(b.p50) == len(b.p90) == 12
    assert all(lo <= mid <= hi for lo, mid, hi in zip(b.p10, b.p50, b.p90, strict=True))
    for i in range(3):  # Jan to Mar are booked hours
        assert b.p10[i] == pytest.approx(b.p90[i])
    assert b.p50[-1] > 26000.0
    assert b.p90[-1] > b.p10[-1]  # the fan opens after as_of


def test_the_snapshot_method_is_the_function(snap):
    assert snap.burn_series() == burn_series(snap)


def test_no_readings_gives_a_note_and_no_fan(tmp_path):  # review-focus 1
    _write(tmp_path)
    (tmp_path / "weekly.csv").unlink()
    b = burn_series(load_snapshot(tmp_path))
    assert b.as_of is None and b.spent_as_of is None and b.reading_dates == ()
    assert all(v is None for v in b.spent)
    assert b.p10 == b.p50 == b.p90 == ()
    assert b.note == "no hours readings yet"
    assert b.budget == (95000.0,) * 12  # the budget and plan still draw
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Documents/git/perch/apps/budgie && ~/Documents/tools/perch/bin/pytest budgie/tests/test_burn.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'budgie.core.burn'`.

- [ ] **Step 3: Write the implementation**

Create `apps/budgie/budgie/core/burn.py`:

```python
"""The monthly burn a chart needs, in labor dollars.

Measured spend at each month-end, the plan's dollars, the budget in force
(minus the cost lines) and a P10, P50 and P90 fan to the year's end. This is
the same estimate-at-completion plus monthly simulation that `budgie
monthly` runs, so a front end reads one function instead of re-deriving it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from budgie.core.csvio import last_day_of_month
from budgie.core.eac import at_completion
from budgie.core.monthly import Actuals, monthly_simulation, spent_at

if TYPE_CHECKING:
    from budgie.core.project import Snapshot


@dataclass(frozen=True)
class BurnSeries:
    """Twelve month-ends of labor dollars; a None is "no figure", never zero."""

    months: tuple[date, ...]
    spent: tuple[float | None, ...]  # booked by each month-end; None after as_of
    spent_as_of: tuple[date, float] | None  # the latest reading day and dollars then
    plan: tuple[float | None, ...]  # planned through each month-end
    budget: tuple[float | None, ...]  # budget in force at month-end, less cost lines
    p10: tuple[float, ...]  # empty when there is no fan
    p50: tuple[float, ...]
    p90: tuple[float, ...]
    reading_dates: tuple[date, ...]  # distinct reading days, sorted
    as_of: date | None
    note: str = ""  # "" or why a part is missing


def burn_series(snap: Snapshot) -> BurnSeries:
    span = snap.span
    ends = tuple(last_day_of_month(y, m) for y, m in span.months)
    rate = {p.name: p.hourly_cost for p in snap.people}
    days = sorted({d for series in snap.readings.values() for d, _ in series})
    as_of = days[-1] if days else None

    def booked(day: date) -> float:
        return sum(
            spent_at(series, day, span) * rate[name]
            for name, series in snap.readings.items()
            if name in rate
        )

    spent = tuple(booked(d) if as_of and d <= as_of else None for d in ends)
    spent_as_of = (as_of, booked(as_of)) if as_of else None

    allocated = snap.allocated

    def planned(day: date) -> float:
        total = 0.0
        for name in allocated:
            hours = snap.planned_through(name, day)
            if hours is not None and name in rate:
                total += hours * rate[name]
        return total

    plan = tuple(planned(d) for d in ends) if allocated else (None,) * 12
    book = snap.budget_revisions or snap.budget
    budget = (
        tuple(a - snap.non_labor for a in book.monthly_amounts(span))
        if book
        else (None,) * 12
    )

    note, fan = "", ((), (), ())
    if as_of is None:
        note = "no hours readings yet"
    elif not snap.people:
        note = "no people"
    else:
        eac = at_completion(snap.people, snap.readings, span, as_of=as_of, plan=snap.plan)
        sim = monthly_simulation(
            eac.people,
            span,
            pto_days=snap.pto,
            iterations=snap.iterations,
            seed=snap.seed,
            actuals=Actuals(eac.readings, snap.readings, snap.plan),
        )
        fan = tuple(tuple(sim.band(q)) for q in (10, 50, 90))
    return BurnSeries(
        months=ends,
        spent=spent,
        spent_as_of=spent_as_of,
        plan=plan,
        budget=budget,
        p10=fan[0],
        p50=fan[1],
        p90=fan[2],
        reading_dates=tuple(days),
        as_of=as_of,
        note=note,
    )
```

In `apps/budgie/budgie/core/project.py`, add this method to `Snapshot` directly after `planned_through` (before the `spent` property), and add `from budgie.core.burn import BurnSeries` under the file's existing `TYPE_CHECKING` block (create the block if absent, with `from typing import TYPE_CHECKING`); the file already has `from __future__ import annotations`:

```python
    def burn_series(self) -> BurnSeries:
        """Monthly spend, plan, budget and the P10/P50/P90 fan (see core.burn)."""
        from budgie.core.burn import burn_series

        return burn_series(self)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/Documents/git/perch/apps/budgie && ~/Documents/tools/perch/bin/pytest budgie/tests/test_burn.py -v`
Expected: 7 passed. If `test_plan_reaches_the_allocation...` fails on `149400`, print `snap.planned_through(n, date(2026,12,31))` for both people, fix the expected figure to the sum of `hours x rate` and update the spec's 149,400 to match; that check was the design's first unverified assumption. Then `cd apps/budgie && ~/Documents/tools/perch/bin/pytest -q` (the whole Budgie suite) must still pass.

- [ ] **Step 5: Commit (in the Budgie repo)**

```bash
cd ~/Documents/git/perch/apps/budgie
git add budgie/core/burn.py budgie/core/project.py budgie/tests/test_burn.py
git commit -m "feat(burn): burn_series, the monthly spend, plan, budget and fan for a chart"
```

Perch pins Budgie by git URL: this commit must reach Budgie's remote before perch's release; `make venv` installs `apps/budgie` editable, so local work needs nothing more.

---

## Wave 1: core modules (separate files; start with Task 2, then Tasks 3 to 8 are parallel-safe)

### Task 2: Shared cores: sources, moves, trend (bead perch-zq2.6; parallel-safe: yes, but Tasks 3, 4, 6 and 7 consume it)

**Files:**
- Create: `perch/core/sources.py`, `perch/core/moves.py`
- Modify: `perch/core/trend.py` (add `changes`, public `money` and `share`)
- Test: `perch/tests/test_sources.py`, `perch/tests/test_moves.py`, `perch/tests/test_trend.py` (append)

**Interfaces:**
- Consumes: `load_config(path, require_dump=False)`, `history.load(path)`, `load_money(path)`, `load_board(path)`, `status.failure_path(home, name)`; `Money.budget_revisions`, `Money.plan`, `Money.span`.
- Produces:
  - `Sources(config: Config | None, rows: list[dict], money: Money | None, board: Board | None, failure: dict | None, errors: tuple[str, ...])`; `sources.load(home: Home, name: str) -> Sources`; `sources.stamp(home: Home, name: str) -> float`; `sources.unreadable(source: str) -> str`.
  - `BudgetMove(day, before: float | None, after: float)`; `StaffMove(day, kind: str, fte_before: float, fte_after: float)` with `kind` in `join`, `leave`, `fte`; `moves.budget(money, start, end) -> tuple[BudgetMove, ...]`; `moves.staffing(money, start, end) -> tuple[StaffMove, ...]`; `moves.label(kind) -> str`; `moves.describe(m: StaffMove) -> str`; `moves.describe_budget(m: BudgetMove) -> str`.
  - `trend.changes(rows) -> list[Change]`; `trend.money(value, signed=False) -> str`; `trend.share(value) -> str` (the underscore names stay as aliases).

- [ ] **Step 1: Write the failing tests**

Append to `perch/tests/test_trend.py`:

```python
def _team_rows(*figs):
    return [
        {"week": f"2026-W{36 + i}", "kind": "team", "name": "team",
         "headroom": h, "signal": s}
        for i, (h, s) in enumerate(figs)
    ]


def test_changes_is_every_consecutive_pair_and_change_is_the_last():
    from perch.core.trend import change, changes

    rows = _team_rows((30000, "green"), (20000, "yellow"), (-12000, "red"))
    got = changes(rows)
    assert [(c.before, c.after) for c in got] == [
        ("2026-W36", "2026-W37"),
        ("2026-W37", "2026-W38"),
    ]
    assert got[0].signal == ("green", "yellow") and got[0].deltas == {"headroom": -10000}
    assert got[1].signal == ("yellow", "red") and got[1].deltas == {"headroom": -32000}
    assert change(rows) == got[-1]


def test_changes_needs_two_weeks():
    from perch.core.trend import change, changes

    assert changes(_team_rows((1, "green"))) == [] and changes([]) == []
    assert change([]) is None


def test_money_and_share_are_public_and_the_old_names_stay():
    from perch.core import trend

    assert trend.money(-3000) == "−$3,000" and trend.money(None) == "—"
    assert trend.money(5, signed=True) == "+$5" and trend.share(0.85) == "85%"
    assert trend._money is trend.money and trend._share is trend.share
```

Create `perch/tests/test_moves.py`:

```python
"""Budget and staffing changes, name-free."""

from dataclasses import fields, replace
from datetime import date

from budgie.core.budget import Budget, BudgetRevision
from budgie.core.plan import AllocationPlan, PlanEntry

from perch.core import moves
from perch.core.money import load_money


def _money(world):
    return load_money(world.parent / "fy26")


def _plan(*rows):
    return AllocationPlan(tuple(PlanEntry(n, date.fromisoformat(d), f) for n, d, f in rows))


def test_budget_moves_drop_the_note_and_the_starting_revision(world):
    revs = Budget((
        BudgetRevision(date(2026, 1, 1), 100000.0, "Original"),
        BudgetRevision(date(2026, 4, 15), 120000.0, "backfill for Alice"),
    ))
    money = replace(_money(world), budget_revisions=revs)
    got = moves.budget(money, date(2026, 1, 1), date(2026, 12, 31))
    assert [(m.day, m.before, m.after) for m in got] == [
        (date(2026, 4, 15), 100000.0, 120000.0)
    ]
    assert "note" not in {f.name for f in fields(moves.BudgetMove)}
    assert moves.describe_budget(got[0]) == "budget $100,000 → $120,000"
    assert moves.budget(money, date(2026, 5, 1), date(2026, 6, 1)) == ()
    assert moves.budget(replace(money, budget_revisions=None), date(2026, 1, 1), date(2026, 12, 31)) == ()


def test_staffing_kinds_and_the_starting_team(world):
    plan = _plan(
        ("Alice", "2026-01-01", 0.5),
        ("Alice", "2026-06-10", 0.75),
        ("Bob", "2026-06-10", 0),
        ("Carol", "2026-06-10", 0.5),
    )
    money = replace(_money(world), plan=plan)
    got = moves.staffing(money, date(2026, 6, 1), date(2026, 6, 30))
    # Bob's 0 with nothing before it is not a change; Carol joins
    assert [(m.kind, m.fte_before, m.fte_after) for m in got] == [
        ("fte", 0.5, 0.75),
        ("join", 0.0, 0.5),
    ]
    assert moves.describe(got[0]) == "an FTE change · FTE 0.5 → 0.75"
    assert not {"name", "hours", "dollars"} & {f.name for f in fields(moves.StaffMove)}
    first_day = date(2026, 1, 1)  # a first-day row is the starting team
    assert moves.staffing(money, first_day, first_day) == ()
    assert moves.staffing(replace(money, plan=None), first_day, date(2026, 12, 31)) == ()


def test_a_leave_and_a_join(world):
    plan = _plan(
        ("Bob", "2026-01-01", 0.5),
        ("Bob", "2026-06-10", 0),
        ("Carol", "2026-06-10", 0.5),
    )
    got = moves.staffing(replace(_money(world), plan=plan), date(2026, 6, 1), date(2026, 6, 30))
    assert [(m.kind, m.fte_before, m.fte_after) for m in got] == [
        ("leave", 0.5, 0.0),
        ("join", 0.0, 0.5),
    ]
    assert [moves.describe(m) for m in got] == [
        "a leave · FTE 0.5 → 0",
        "a join · FTE 0 → 0.5",
    ]


def test_two_joins_on_one_day_both_stay(world):  # review-focus 3
    plan = _plan(("Carol", "2026-06-10", 0.5), ("Dave", "2026-06-10", 0.5))
    got = moves.staffing(replace(_money(world), plan=plan), date(2026, 6, 1), date(2026, 6, 30))
    assert [moves.describe(m) for m in got] == ["a join · FTE 0 → 0.5"] * 2
```

Create `perch/tests/test_sources.py`:

```python
"""Sources: one load of everything a project's files say."""

import os
import time
from datetime import date

from perch.core import sources
from perch.tests.conftest import build_home


def _home(tmp_path):
    return build_home(tmp_path, "apollo")


def test_load_reads_every_source(tmp_path):
    src = sources.load(_home(tmp_path), "apollo")
    assert src.errors == () and src.rows == [] and src.failure is None
    assert src.money.as_of == date(2026, 4, 19)
    assert src.board.fetched_on == date(2026, 4, 20)
    assert src.config.gitlab_project == "grp/apollo"


def test_a_missing_dump_is_no_board_and_no_error(tmp_path):
    home = _home(tmp_path)
    (home.projects_dir / "apollo" / "dump.json").unlink()
    src = sources.load(home, "apollo")
    assert src.board is None and src.errors == () and src.money is not None


def test_a_corrupt_failure_file_is_one_error_and_the_rest_load(tmp_path):  # review-focus 2
    home = _home(tmp_path)
    (home.projects_dir / "apollo" / "monday.json").write_text("{")
    src = sources.load(home, "apollo")
    assert src.errors == ("monday.json",) and src.failure is None
    assert src.money is not None and src.board is not None
    assert sources.unreadable("monday.json") == "monday.json unreadable, run perch doctor"


def test_a_failing_budgie_load_is_named_not_raised(tmp_path, monkeypatch):  # review-focus 2
    def boom(path):
        raise ValueError("people.csv: row 3: Alice is not a number")

    monkeypatch.setattr(sources, "load_money", boom)
    src = sources.load(_home(tmp_path), "apollo")
    assert src.money is None and src.errors == ("budgie",) and src.board is not None
    assert "Alice" not in repr(src.errors)  # the exception text is never kept


def test_a_failure_record_is_read(tmp_path):
    home = _home(tmp_path)
    (home.projects_dir / "apollo" / "monday.json").write_text(
        '{"week": "2026-W17", "step": "board", "code": 2, "at": "2026-04-19T09:00:00"}'
    )
    assert sources.load(home, "apollo").failure["step"] == "board"


def test_stamp_moves_when_an_input_changes(tmp_path):
    home = _home(tmp_path)
    before = sources.stamp(home, "apollo")
    later = time.time() + 1000
    path = home.projects_dir / "apollo" / "history.jsonl"
    path.write_text("")
    os.utime(path, (later, later))
    assert sources.stamp(home, "apollo") == later > before
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `~/Documents/tools/perch/bin/pytest perch/tests/test_sources.py perch/tests/test_moves.py perch/tests/test_trend.py -v`
Expected: FAIL (`ModuleNotFoundError: perch.core.sources`, `ImportError: cannot import name 'changes'`).

- [ ] **Step 3: Implement**

In `perch/core/trend.py`, replace `change` and the two formatters. Replace the whole `def change(...)` function with:

```python
def changes(rows: list[dict]) -> list[Change]:
    """Every consecutive pair of recorded team weeks, oldest first."""
    weeks = sorted({r["week"]: r for r in rows if r["kind"] == "team"}.items())
    out = []
    for (before, old), (after, new) in zip(weeks, weeks[1:], strict=False):
        flip = (old.get("signal"), new.get("signal"))
        deltas = {
            key: new[key] - old[key]
            for key, _ in _DELTAS
            if old.get(key) is not None
            and new.get(key) is not None
            and abs(new[key] - old[key]) >= 0.5
        }
        out.append(
            Change(
                before,
                after,
                flip if all(flip) and flip[0] != flip[1] else None,
                deltas,
            )
        )
    return out


def change(rows: list[dict]) -> Change | None:
    """The team row of the last two recorded weeks; None when fewer than two."""
    got = changes(rows)
    return got[-1] if got else None
```

Replace `_money` and `_share` with:

```python
def money(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "—"
    sign = ("+" if signed else "") if value >= 0 else "−"
    return f"{sign}${abs(value):,.0f}"


def share(value: float | None) -> str:
    return "—" if value is None else f"{value:.0%}"


_money, _share = money, share  # the names tui.py and the older tests import
```

(`describe` and `team_lines` keep calling `_money` and `_share`; they resolve the aliases at call time.)

Create `perch/core/sources.py`:

```python
"""One load of everything a project's files say, for the slow tier.

The pane, the tape and the events calendar all read config, history, the
Budgie project, the board dump and the failure record. Money costs about 0.4 s
cold, so it is read once here and shared. Each source is read on its own: one
that fails is named in `errors` and the rest still load. The exception text is
never kept, since a loader's message is built from file contents.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from perch.core import history
from perch.core.board import Board, load_board
from perch.core.config import Config, load_config
from perch.core.money import Money, load_money
from perch.core.status import failure_path
from perch.core.workspace import Home


@dataclass(frozen=True)
class Sources:
    config: Config | None = None
    rows: list[dict] = field(default_factory=list)
    money: Money | None = None
    board: Board | None = None
    failure: dict | None = None
    errors: tuple[str, ...] = ()  # names of the sources that would not read


def unreadable(source: str) -> str:
    """The one line a consumer shows for a source that would not read."""
    return f"{source} unreadable, run perch doctor"


def _failure(path: Path) -> dict:
    got = json.loads(path.read_text())
    if not isinstance(got, dict):
        raise ValueError("not a record")
    return got


def load(home: Home, name: str) -> Sources:
    try:
        config = load_config(home.config_path(name), require_dump=False)
    except Exception:  # noqa: BLE001 -- a display boundary: name it, never crash
        return Sources(errors=("perch.yaml",))
    errors: list[str] = []

    def got(source: str, read, default=None):
        try:
            return read()
        except Exception:  # noqa: BLE001 -- as above: one bad source, the rest read
            errors.append(source)
            return default

    rows = got("history", lambda: history.load(config.history), [])
    money = got("budgie", lambda: load_money(config.budgie_project))
    board = (
        got("board", lambda: load_board(config.board_dump))
        if config.board_dump.is_file()
        else None
    )
    path = failure_path(home, name)
    failure = got("monday.json", lambda: _failure(path)) if path.is_file() else None
    return Sources(config, rows, money, board, failure, tuple(errors))


def stamp(home: Home, name: str) -> float:
    """The newest mtime among the files `load` reads (stat calls only), so the
    slow tier can skip a project nothing has touched. -1 when the config will not read."""
    try:
        config = load_config(home.config_path(name), require_dump=False)
    except Exception:  # noqa: BLE001
        return -1.0
    files = [
        p
        for p in (
            home.config_path(name),
            config.history,
            config.board_dump,
            failure_path(home, name),
        )
        if p.is_file()
    ]
    if config.budgie_project.is_dir():
        files += [p for p in config.budgie_project.rglob("*") if p.is_file()]
    return max((p.stat().st_mtime for p in files), default=0.0)
```

Create `perch/core/moves.py`:

```python
"""Budget revisions and staffing changes, with no name, hours or dollars.

Events and the tape both list these. `quarterly._staffing` carries names and
costs for the quarterly report only; this module reads the same plan and keeps
the team level. A row on the year's first day is the starting team, not a change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from perch.core.money import Money


@dataclass(frozen=True)
class BudgetMove:
    day: date
    before: float | None
    after: float


@dataclass(frozen=True)
class StaffMove:
    day: date
    kind: str  # "join" | "leave" | "fte"
    fte_before: float
    fte_after: float


def budget(money: Money, start: date, end: date) -> tuple[BudgetMove, ...]:
    """Revisions dated in [start, end] after the year's first day that changed the amount."""
    rev = money.budget_revisions
    if rev is None:
        return ()
    out = []
    for r in rev.revisions:
        day = r.effective_date
        if not start <= day <= end or day <= money.span.first:
            continue
        before = rev.amount_on(day - timedelta(days=1))
        if before != r.amount:
            out.append(BudgetMove(day, before, r.amount))
    return tuple(out)


def staffing(money: Money, start: date, end: date) -> tuple[StaffMove, ...]:
    """plan.csv changes dated in [start, end]; ties keep plan.csv entry order."""
    plan = money.plan
    if plan is None:
        return ()
    out = []
    for entry in plan.entries:
        day = entry.effective_date
        if not start <= day <= end or day <= money.span.first:
            continue
        before = plan.fte_on(entry.name, day - timedelta(days=1))
        if before == entry.fte:
            continue
        kind = "join" if before == 0 else "leave" if entry.fte == 0 else "fte"
        out.append(StaffMove(day, kind, before, entry.fte))
    return tuple(sorted(out, key=lambda m: m.day))  # stable: entry order breaks ties


def label(kind: str) -> str:
    return {"join": "a join", "leave": "a leave", "fte": "an FTE change"}[kind]


def describe(m: StaffMove) -> str:
    return f"{label(m.kind)} · FTE {m.fte_before:g} → {m.fte_after:g}"


def describe_budget(m: BudgetMove) -> str:
    before = "—" if m.before is None else f"${m.before:,.0f}"
    return f"budget {before} → ${m.after:,.0f}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `~/Documents/tools/perch/bin/pytest perch/tests/test_sources.py perch/tests/test_moves.py perch/tests/test_trend.py -v`
Expected: all pass (the `test_staffing_kinds...` test with the corrected final assertion shows `("fte", 0.5, 0.75)` and `("join", 0.0, 0.5)`). Then `~/Documents/tools/perch/bin/pytest -q` for the whole suite (`trend` aliases keep `tui.py` importing).

- [ ] **Step 5: Commit**

```bash
git add perch/core/sources.py perch/core/moves.py perch/core/trend.py perch/tests/test_sources.py perch/tests/test_moves.py perch/tests/test_trend.py
git commit -m "feat(core): sources, moves and trend.changes, the shared groundwork for the second Bloomberg pass"
```

### Task 3: Detail core (bead perch-zq2.1; parallel-safe: yes after Tasks 1 and 2)

**Files:**
- Modify: `perch/core/money.py` (a `burn` field, wired in `money_from`)
- Create: `perch/core/detail.py`
- Test: `perch/tests/test_detail.py`

**Interfaces:**
- Consumes: `Sources` (Task 2), `sources.unreadable`, `trend.series/spark/money/share`, `blocks` builders (`heading`, `text`, `figures`, `figure`, `table`), Budgie `BurnSeries` (Task 1) through `Money.burn`.
- Produces: `Money.burn: Callable[[], BurnSeries] | None`; `Detail` (frozen: `project, headroom, burn, as_of, dump_on, history_week, pace, net_scope, non_labor, note`); `detail.build(project: str, src: Sources) -> Detail`; `detail.spark_line(d: Detail, upto: str | None = None) -> str`; `detail.lines(d: Detail, upto: str | None = None) -> list[str]`; `detail.blocks(d: Detail) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

Create `perch/tests/test_detail.py`:

```python
"""The detail pane's data: from Sources and Budgie's burn series."""

import json
from datetime import date

import pytest

from perch.core import blocks as bk
from perch.core import detail, sources
from perch.tests.conftest import build_home
from perch.tests.test_watch import BANNED


def _build(tmp_path, rows=()):
    home = build_home(tmp_path, "apollo")
    path = home.projects_dir / "apollo" / "history.jsonl"
    if rows:
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return home, detail.build("apollo", sources.load(home, "apollo"))


def _team(week, headroom, **more):
    return {"week": week, "date": "2026-09-01", "kind": "team", "name": "team",
            "headroom": headroom, "signal": "green", **more}


def test_money_carries_budgies_burn_series(tmp_path):
    home = build_home(tmp_path, "apollo")
    burn = sources.load(home, "apollo").money.burn()
    assert burn.spent_as_of == (date(2026, 4, 19), 26000.0)


def test_build_from_the_world(tmp_path):
    _, d = _build(tmp_path)
    assert d.project == "apollo" and d.headroom == {}
    assert (d.as_of, d.dump_on, d.history_week) == (date(2026, 4, 19), date(2026, 4, 20), None)
    assert d.non_labor == 5000.0 and d.note == ""
    assert d.burn.budget == (95000.0,) * 12


def test_the_spark_line_needs_two_weeks(tmp_path):
    _, none = _build(tmp_path)
    assert detail.spark_line(none) == "no weeks recorded yet"
    _, one = _build(tmp_path / "a", [_team("2026-W36", 5000)])
    assert detail.spark_line(one) == "1 week recorded, need 2 for a trend"
    _, two = _build(tmp_path / "b", [_team("2026-W36", 5000), _team("2026-W37", 2000)])
    assert detail.spark_line(two) == "headroom █▁  $2,000–$5,000  2 weeks"
    assert detail.spark_line(two, upto="2026-W36") == "1 week recorded, need 2 for a trend"


def test_pace_and_scope_come_from_the_latest_team_row(tmp_path):  # review-focus 4
    _, d = _build(tmp_path, [_team("2026-W36", 5000), _team("2026-W37", 2000, pace=0.85, net_scope=-3)])
    assert d.pace == 0.85 and d.net_scope == -3 and d.history_week == "2026-W37"
    assert "pace 85% · net scope -3" in detail.lines(d)
    _, old = _build(tmp_path / "old", [_team("2026-W36", 5000)])  # a row from before pace
    assert "pace — · net scope —" in detail.lines(old)


def test_no_readings_gives_a_note(tmp_path):  # review-focus 1
    home = build_home(tmp_path, "apollo")
    (home.projects_dir / "apollo" / "fy26" / "weekly.csv").unlink()
    d = detail.build("apollo", sources.load(home, "apollo"))
    assert d.as_of is None and "no hours readings yet" in d.note
    assert detail.lines(d)[-1] == d.note


def test_a_failing_fan_and_unreadable_sources_become_fixed_notes(tmp_path):
    home = build_home(tmp_path, "apollo")
    src = sources.load(home, "apollo")

    def boom():
        raise ValueError("Alice")

    from dataclasses import replace

    bad = replace(src, money=replace(src.money, burn=boom), errors=("monday.json",))
    d = detail.build("apollo", bad)
    assert d.burn is None
    assert d.note == "monday.json unreadable, run perch doctor; fan unavailable, run perch doctor"
    assert "Alice" not in d.note


def test_blocks_are_valid_and_the_table_is_labor_only(tmp_path):
    _, d = _build(tmp_path)
    out = detail.blocks(d)
    assert all(bk.parse(json.dumps(b)) for b in out)
    md = bk.to_md(out)
    assert "Detail · apollo" in md and "Labor only · cost lines excluded" in md
    assert "2026-12" in md and "$149,400" in md


def test_no_ranking_word_and_no_name(tmp_path):
    _, d = _build(tmp_path, [_team("2026-W36", 5000), _team("2026-W37", 2000)])
    text = ("\n".join(detail.lines(d)) + bk.to_md(detail.blocks(d))).lower()
    assert "alice" not in text and "bob" not in text
    assert not [w for w in BANNED if w in text]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/Documents/tools/perch/bin/pytest perch/tests/test_detail.py -v`
Expected: FAIL with `ImportError` (`perch.core.detail`) and `AttributeError: 'Money' has no attribute 'burn'`.

- [ ] **Step 3: Implement**

In `perch/core/money.py` add the import beside the other `budgie.core` imports:

```python
from budgie.core.burn import BurnSeries
```

add this field after `planned_on` in `Money`:

```python
    # Budgie's Snapshot.burn_series: the chart's monthly series. Lazy: it simulates.
    burn: Callable[[], BurnSeries] | None = field(default=None, compare=False)
```

and in `money_from`, next to the existing `planned_on=snap.planned_through` argument, add `burn=snap.burn_series,`.

Create `perch/core/detail.py`:

```python
"""The detail pane's data: the headroom history, Budgie's burn series, the
freshness of each input. Read only, team level, no new arithmetic; every
dollar on the chart comes from Budgie's burn_series through Money.burn.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from perch.core import blocks as bk
from perch.core.sources import Sources, unreadable
from perch.core.trend import money, series, share, spark

if TYPE_CHECKING:  # typing only: money.py is where perch imports budgie.core
    from budgie.core.burn import BurnSeries


@dataclass(frozen=True)
class Detail:
    project: str
    headroom: dict[str, float]  # week -> headroom, every recorded week
    burn: BurnSeries | None
    as_of: date | None
    dump_on: date | None
    history_week: str | None
    pace: float | None
    net_scope: int | None
    non_labor: float
    note: str  # "" or why a part is missing; fixed strings only


def build(project: str, src: Sources) -> Detail:
    m = src.money
    notes = [unreadable(s) for s in src.errors]
    burn = None
    if m is not None and m.burn is not None:
        try:
            burn = m.burn()
        except Exception:  # noqa: BLE001 -- a display boundary: say so, never crash
            notes.append("fan unavailable, run perch doctor")
        else:
            if burn.note:
                notes.append(burn.note)
    if src.config is not None and src.board is None:
        notes.append("no board dump yet: run perch fetch")
    team = sorted((r for r in src.rows if r["kind"] == "team"), key=lambda r: r["week"])
    last = team[-1] if team else {}
    return Detail(
        project=project,
        headroom=series(src.rows, "headroom", window=10_000),
        burn=burn,
        as_of=m.as_of if m else None,
        dump_on=src.board.fetched_on if src.board else None,
        history_week=max((r["week"] for r in src.rows), default=None),
        pace=last.get("pace"),
        net_scope=last.get("net_scope"),
        non_labor=m.non_labor if m else 0.0,
        note="; ".join(notes),
    )


def spark_line(d: Detail, upto: str | None = None) -> str:
    values = [v for w, v in d.headroom.items() if upto is None or w <= upto]
    if not values:
        return "no weeks recorded yet"
    if len(values) == 1:
        return "1 week recorded, need 2 for a trend"
    return (
        f"headroom {spark(values)}  {money(min(values))}–{money(max(values))}"
        f"  {len(values)} weeks"
    )


def _scope(d: Detail) -> str:
    return "—" if d.net_scope is None else f"{d.net_scope:+d}"


def lines(d: Detail, upto: str | None = None) -> list[str]:
    """The pane's text, chart excluded (the TUI draws that from `d.burn`)."""
    out = [
        spark_line(d, upto),
        f"pace {share(d.pace)} · net scope {_scope(d)}",
        f"readings through {d.as_of or '—'} · board dump {d.dump_on or '—'}"
        f" · history {d.history_week or '—'}",
        f"cost lines {money(d.non_labor)} (not in the chart)",
    ]
    if d.note:
        out.append(d.note)
    return out


def _at(values: tuple, i: int) -> str:
    return money(values[i]) if values else "—"


def blocks(d: Detail) -> list[dict]:
    out = [
        bk.heading(f"Detail · {d.project}"),
        bk.text(spark_line(d), tone="dim"),
        bk.figures(
            [
                bk.figure("readings through", str(d.as_of or "—")),
                bk.figure("board dump", str(d.dump_on or "—")),
                bk.figure("history week", d.history_week or "—"),
                bk.figure("pace", share(d.pace)),
                bk.figure("net scope", _scope(d)),
                bk.figure("cost lines", money(d.non_labor), note="not in the table"),
            ]
        ),
    ]
    b = d.burn
    if b is not None and b.months:
        rows = [
            [
                month.strftime("%Y-%m"),
                _at(b.spent, i),
                _at(b.plan, i),
                _at(b.budget, i),
                _at(b.p10, i),
                _at(b.p50, i),
                _at(b.p90, i),
            ]
            for i, month in enumerate(b.months)
        ]
        out.append(
            bk.table(
                ["month", "spent", "plan", "budget", "P10", "P50", "P90"],
                rows,
                title="Labor only · cost lines excluded",
                align=["l"] + ["r"] * 6,
            )
        )
    if d.note:
        out.append(bk.text(d.note, tone="warn"))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/Documents/tools/perch/bin/pytest perch/tests/test_detail.py perch/tests/test_money.py -v` (use whichever money test file exists: `ls perch/tests | grep money`; `Money` equality ignores `burn`, so nothing else changes), then `~/Documents/tools/perch/bin/pytest -q`.
Expected: all pass. The `test_no_readings` world must still load without `weekly.csv`; if Budgie raises there, change the test to remove only `weekly.csv` rows by writing the header alone.

- [ ] **Step 5: Commit**

```bash
git add perch/core/money.py perch/core/detail.py perch/tests/test_detail.py
git commit -m "feat(detail): the pane's data from Budgie's burn series"
```
