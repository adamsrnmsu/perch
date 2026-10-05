# Research Pace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `perch quarterly` and the history team row gain two model-free figures for research projects: hours booked against hours planned (pace) and issues opened against issues closed (scope).

**Architecture:** Everything lives in `perch/core/quarterly.py` (UI-free): `Position` gains booked and planned hours, `Week` gains an `opened` count, `Quarter` gains `net_scope`, and a public `quarter_to_date()` gives `perch board` the same two figures for history.jsonl without the Monte Carlo forecast. `report_mail.py` renders them in neutral words; `history.rows_for` and `cli.board` carry them into the team row.

**Tech Stack:** Python 3, Budgie (`Money.planned`, `Money.booked`, pace lines), pytest. Tests run with `~/Documents/tools/perch/bin/pytest`; lint with `make lint`.

**Spec:** `docs/superpowers/specs/2026-10-04-research-pace-design.md`

> **Amended after the final review (2026-10-04):** planned hours are `Money.team_planned` (the plan sampled on the reading days), not `Money.planned` over `money.pace`; Task 1's `13 * 7.968` became `7.968 * 95 / 7`. See the spec's Pace section and the ledger.

**Bead:** perch-w1d. One child bead per task below (created before execution).

## Global Constraints

- `perch/core/` stays UI-free: no click, no rich.
- Team level only: no person's name next to a pace or scope figure.
- Neutral wording in the report (it goes to funders): counts and hours only, never "grew", "narrowed", "behind" or "ahead"; no colour, no threshold.
- perch does no fiscal arithmetic: quarters come from `money.span.quarters`.
- perch redoes no Budgie math: planned hours are `Money.planned` (Budgie's pace line), booked hours are `Money.booked` via `_team`.
- Unknown is None, never zero: a week outside the dump, or a dump without `created_at`, has `opened = None`.
- Tests assert numbers worked by hand from `perch/tests/conftest.py`'s world.

## Review Focus

1. A dump with `created_at` on some issues but not all (gitboard upgraded mid-history) -- every `opened` must be None, not a partial count. Pinned in Task 2 (`test_a_dump_missing_some_creation_days_counts_no_opened`).
2. A quarter whose readings stop before it starts (`read_to < start`) -- planned must be None too, not hours planned against nothing booked. Pinned in Task 1.
3. A net change of exactly 0 or ±1 -- the sentence must read "no net change in open issues" / "1 open issue", not "+0 open issues" / "+1 open issues". Pinned in Task 3.
4. `perch board` on a day outside the Budgie year (readings from last year, today in the new one) -- history row gets `pace: null`, `net_scope: null`, no crash. Pinned in Task 4.
5. The throughput table's total row after the new column -- the per-issue figure must stay in the last column (the `rows[-1]` slice shifts by one). Pinned in Task 3 by the exact total-row string.

---

### Task 1: Pace -- booked and planned hours in `Position`

**Files:**
- Modify: `perch/core/quarterly.py` (`Position` dataclass ~line 57; new `_plan` after `_team` ~line 178; `_position` ~line 180)
- Test: `perch/tests/test_quarterly.py`

**Interfaces:**
- Consumes: `Money.planned(name, start, end)`, `Money.pace` (dict of allocated people), existing `_team(money, start, end, cost)`.
- Produces: `Position.booked_quarter: float | None`, `Position.planned_quarter: float | None`; module function `_plan(money: Money, start: date, read_to: date) -> float | None` (Task 4 calls it).

- [ ] **Step 1: Write the failing tests**

Add `from dataclasses import replace` to the imports of `perch/tests/test_quarterly.py`, then append:

```python
def test_pace_is_hours_booked_against_hours_planned(quarter_world):
    """Apr 1-19 holds 13 working days of 7.968 h. Alice and Bob are both
    planned at 0.5 (Bob's cut is May 1), so 2 x 0.5 x 13 x 7.968 = 103.584 h
    planned; booked is the 19 days at 15/7 h."""
    p = make(quarter_world, "2026-Q2").position
    assert p.planned_quarter == pytest.approx(13 * 7.968)
    assert p.booked_quarter == pytest.approx(285 / 7)


def test_without_allocations_nothing_is_planned(quarter_world):
    config = load_config(quarter_world)
    board = load_board(config.board_dump)
    money = replace(load_money(config.budgie_project), pace={})
    q = build(board, money, {}, None, config.people, "2026-Q2", FETCH_DAY, "apollo")
    assert q.position.planned_quarter is None
    assert q.position.booked_quarter == pytest.approx(285 / 7)


def test_readings_that_stop_before_the_quarter_give_no_pace(world):
    # The readings end Apr 19, before Q3: neither figure, not planned alone.
    p = make(world, "2026-Q3").position
    assert (p.booked_quarter, p.planned_quarter) == (None, None)
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `~/Documents/tools/perch/bin/pytest perch/tests/test_quarterly.py -k "pace or planned" -v`
Expected: FAIL with `AttributeError: 'Position' object has no attribute 'planned_quarter'`

- [ ] **Step 3: Implement**

In `Position`, after `non_labor`:

```python
    non_labor: float  # the year's cost lines, in the forecast, not in spent
    # Hours, start of the quarter through read_to; None without readings in it.
    booked_quarter: float | None = None
    # Budgie's pace lines over the same days; None also without allocations.
    planned_quarter: float | None = None
```

After `_team`:

```python
def _plan(money: Money, start: date, read_to: date) -> float | None:
    """Hours Budgie's pace lines plan from `start` through `read_to`, summed
    over the allocated people; None when nobody is allocated."""
    if not money.pace:
        return None
    before = start - timedelta(days=1)
    return sum(money.planned(name, before, read_to) for name in money.pace)
```

In `_position`, compute once and pass both (replace the inline `spent_quarter` condition with `read`):

```python
    read = read_to is not None and read_to >= start
    return Position(
        spent_quarter=_team(money, start, read_to, cost=True) if read else None,
        ...  # the other fields unchanged
        non_labor=money.non_labor,
        booked_quarter=_team(money, start, read_to, cost=False) if read else None,
        planned_quarter=_plan(money, start, read_to) if read else None,
    )
```

- [ ] **Step 4: Run the quarterly tests**

Run: `~/Documents/tools/perch/bin/pytest perch/tests/test_quarterly.py -v`
Expected: all PASS (the three new ones and every existing one).

- [ ] **Step 5: Commit**

```bash
git add perch/core/quarterly.py perch/tests/test_quarterly.py
git commit -m "feat(quarterly): booked and planned hours for the quarter"
```

---

### Task 2: Scope -- opened issues per week, `net_scope`

**Files:**
- Modify: `perch/core/quarterly.py` (`Week` ~line 73, `Quarter.total` ~line 148, new `Quarter.net_scope`, new `_opened` and `_net`, `_weeks` ~line 216, `_previous` ~line 309)
- Test: `perch/tests/test_quarterly.py`

**Interfaces:**
- Consumes: `Board.issues`, `Issue.created_on: date | None`, `Issue.closed_on`.
- Produces: `Week.opened: int | None` (last field, default None); `Quarter.total.opened`; `Quarter.net_scope -> int | None`; module function `_net(weeks) -> int | None` (Task 4 calls it); test helper `created(world, days, default="2026-01-02")` and constant `APRIL` in `test_quarterly.py` (Tasks 3 and 4 import them).

- [ ] **Step 1: Write the failing tests**

Append to `perch/tests/test_quarterly.py`:

```python
# Issues created in Q2; every other issue gets created() 's default, Jan 2.
APRIL = {103: "2026-04-02", 105: "2026-04-07", 106: "2026-04-08", 107: "2026-04-14"}


def created(world, days, default="2026-01-02"):
    """Give every issue in the world's dump a `created_at`: `days` maps an iid
    to its day, the rest get `default`."""
    dump = world.parent / "dump.json"
    meta = json.loads(dump.read_text())
    for record in meta["history"]:
        record["created_at"] = f"{days.get(record['iid'], default)}T09:00:00.000Z"
    dump.write_text(json.dumps(meta))


def test_opened_issues_by_iso_week(quarter_world):
    """#103 on Apr 2 (W14), #105 and #106 on Apr 7 and 8 (W15), #107 on Apr 14
    (W16); closes are Bob's #13 (W14) and Alice's #8 (W15)."""
    created(quarter_world, APRIL)
    q = make(quarter_world, "2026-Q2")
    assert [w.opened for w in q.weeks] == [1, 2, 1]
    assert (q.total.opened, q.total.closed) == (4, 2)
    assert q.net_scope == 2


def test_open_work_can_shrink(quarter_world):
    created(quarter_world, {103: "2026-04-02"})
    q = make(quarter_world, "2026-Q2")
    assert [w.opened for w in q.weeks] == [1, 0, 0]
    assert q.net_scope == -1


def test_a_dump_without_creation_days_counts_no_opened(quarter_world):
    q = make(quarter_world, "2026-Q2")  # the world's dump has no created_at
    assert [w.opened for w in q.weeks] == [None] * 3
    assert q.total.opened is None and q.net_scope is None


def test_a_dump_missing_some_creation_days_counts_no_opened(quarter_world):
    """A partial count would undercount what opened: all or nothing."""
    created(quarter_world, APRIL)
    dump = quarter_world.parent / "dump.json"
    meta = json.loads(dump.read_text())
    del meta["history"][0]["created_at"]
    dump.write_text(json.dumps(meta))
    q = make(quarter_world, "2026-Q2")
    assert [w.opened for w in q.weeks] == [None] * 3
    assert q.net_scope is None


def test_a_week_outside_the_dump_has_no_opened_count(world):
    """Weeks starting before Jan 20 are outside the dump, as for closes. Every
    issue was created Jan 2, so the counted weeks open nothing and close 9."""
    created(world, {})
    q = make(world, "2026-Q1")
    assert [w.opened for w in q.weeks[:4]] == [None] * 4
    assert q.total.opened == 0
    assert q.net_scope == -9


def test_the_previous_quarter_counts_opened_too(world):
    """20 issues in the dump (#1-#13 closed, #101-#107 open); 4 created in
    April, so 16 opened in Q1."""
    created(world, APRIL)
    since(world, "2026-01-01")
    prev = make(world, "2026-Q2").previous
    assert (prev.opened, prev.closed) == (16, 11)
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `~/Documents/tools/perch/bin/pytest perch/tests/test_quarterly.py -k "opened or shrink" -v`
Expected: FAIL with `AttributeError: 'Week' object has no attribute 'opened'`

- [ ] **Step 3: Implement**

`Week` gains a last field (default, so every positional `Week(...)` call keeps working):

```python
    hours: float | None  # None: no readings
    # None: outside the dump, or a dump without every issue's creation day
    opened: int | None = None
```

After `_since`:

```python
def _opened(board: Board, a: date, b: date) -> int | None:
    """Issues created from `a` through `b`. None when any issue in the dump has
    no creation day: a partial count would undercount what opened."""
    if any(i.created_on is None for i in board.issues):
        return None
    return sum(1 for i in board.issues if a <= i.created_on <= b)


def _net(weeks) -> int | None:
    """Opened less closed over the weeks whose opened count is known (a known
    opened count implies a known closed count)."""
    known = [w for w in weeks if w.opened is not None]
    return sum(w.opened - w.closed for w in known) if known else None
```

In `_weeks`, count opened where closed is counted:

```python
        closed = opened = None
        if board is not None and _since(board) <= a and b <= board.fetched_on:
            closed = sum(1 for i in board.closed if a <= i.closed_on <= b)
            opened = _opened(board, a, b)
        ...
        out.append(Week(f"{year}-W{number:02d}", a, b, closed, hours, opened))
```

In `_previous`:

```python
    name = f"{money.span.label}-Q{n}"
    blocked = _blocked_days(board, first, end, board.since)
    opened = _opened(board, first, end)
    return Week(name, first, end, closed, hours, opened), blocked
```

`Quarter.total` sums `opened` like `closed`, and `net_scope` follows it:

```python
    @property
    def total(self) -> Week:
        closed = [w.closed for w in self.weeks if w.closed is not None]
        hours = [w.hours for w in self.weeks if w.hours is not None]
        opened = [w.opened for w in self.weeks if w.opened is not None]
        return Week(
            self.name,
            self.start,
            self.through,
            sum(closed) if closed else None,
            sum(hours) if hours else None,
            sum(opened) if opened else None,
        )

    @property
    def net_scope(self) -> int | None:
        """Issues opened less issues closed in the quarter; None without
        creation days."""
        return _net(self.weeks)
```

- [ ] **Step 4: Run the quarterly tests**

Run: `~/Documents/tools/perch/bin/pytest perch/tests/test_quarterly.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add perch/core/quarterly.py perch/tests/test_quarterly.py
git commit -m "feat(quarterly): issues opened per week and the quarter's net scope"
```

---

### Task 3: The report -- pace rows and an Opened column, in neutral words

**Files:**
- Modify: `perch/core/report_mail.py` (new `_pace` and `_scope` beside `_issue_total` ~line 72; `_blocks` section 1 ~line 145 and section 3 ~line 268)
- Test: `perch/tests/test_report_mail.py` (update four existing table assertions, add new tests)

**Interfaces:**
- Consumes: `Position.booked_quarter`, `Position.planned_quarter` (Task 1); `Week.opened`, `Quarter.total.opened`, `Quarter.net_scope`, `Quarter.closed_span` (Task 2); `created`, `APRIL` from `perch.tests.test_quarterly` (Task 2).
- Produces: report text only.

- [ ] **Step 1: Update the existing assertions and write the failing tests**

The world's dump has no `created_at`, so the new Opened column reads `—` in the existing tables. In `perch/tests/test_report_mail.py` change:

```python
    assert "| 2026-W15 | Apr 6 – Apr 12 | — | 1 | 15 | 15 |" in text
    assert "| 2026-W16 | Apr 13 – Apr 19 | — | 0 | 15 | — |" in text
    assert "| Total | Apr 1 – Apr 19 | — | 2 | 41 | 20 |" in text  # 285/7 h over 2
```

```python
    assert "| Previous quarter, 2026-Q1 | Jan 1 – Mar 31 | — | 11 | 279 | 25 |" in text
```

```python
    assert "| Total, closes counted Jan 26 – Mar 31 | Jan 1 – Mar 31 | — | 9 |" in text
```

(line 45, `"| 2026-W02 | Jan 5 – Jan 11 | — |"`, still matches and stays.)

Change the import line to `from perch.tests.test_quarterly import APRIL, created, make`, then append:

```python
def test_pace_is_planned_and_booked_hours_in_plain_numbers(quarter_world):
    """103.584 h planned and 285/7 = 40.7 h booked, Apr 1-19: 39%."""
    text = render_md(make(quarter_world, "2026-Q2"))
    assert "| Hours planned Apr 1 – Apr 19 | 104 |" in text
    assert "| Hours booked Apr 1 – Apr 19 | 41 |" in text
    assert "Booked 39% of planned hours." in text


def test_without_a_plan_the_report_says_so(quarter_world):
    q = make(quarter_world, "2026-Q2")
    q = replace(q, position=replace(q.position, planned_quarter=None))
    text = render_md(q)
    assert "| Hours planned Apr 1 – Apr 19 | — |" in text
    assert "No plan to compare booked hours with." in text


def test_scope_is_opened_and_closed_with_the_net_change(quarter_world):
    created(quarter_world, APRIL)
    text = render_md(make(quarter_world, "2026-Q2"))
    assert "| 2026-W15 | Apr 6 – Apr 12 | 2 | 1 | 15 | 15 |" in text
    assert "| Total | Apr 1 – Apr 19 | 4 | 2 | 41 | 20 |" in text
    assert (
        "Opened 4, closed 2 in Apr 1 – Apr 19: a net change of +2 open issues."
        in text
    )


def test_a_net_change_of_one_or_none_reads_plainly(quarter_world):
    created(quarter_world, {103: "2026-04-02", 105: "2026-04-07"})
    text = render_md(make(quarter_world, "2026-Q2"))
    assert "Opened 2, closed 2 in Apr 1 – Apr 19: no net change in open issues." in text
    created(quarter_world, {103: "2026-04-02"})
    text = render_md(make(quarter_world, "2026-Q2"))
    assert "Opened 1, closed 2 in Apr 1 – Apr 19: a net change of -1 open issue." in text


def test_a_dump_without_creation_days_says_how_to_count_opened(quarter_world):
    text = render_md(make(quarter_world, "2026-Q2"))
    assert (
        "The board dump has no creation dates; run `perch fetch` to count "
        "opened issues." in text
    )
    assert "net change" not in text
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `~/Documents/tools/perch/bin/pytest perch/tests/test_report_mail.py -v`
Expected: FAIL (the updated table strings and the new lines are not rendered yet).

- [ ] **Step 3: Implement**

Beside `_issue_total` in `perch/core/report_mail.py`:

```python
def _pace(q: Quarter) -> str | None:
    """Booked against planned hours, as a plain share: no verdict."""
    p = q.position
    if p.booked_quarter is None:
        return None  # no readings in the quarter: hours_note already says so
    if not p.planned_quarter:
        return "No plan to compare booked hours with."
    return f"Booked {p.booked_quarter / p.planned_quarter:.0%} of planned hours."


def _scope(q: Quarter) -> str | None:
    """Opened and closed issues and the net change in open work: no verdict."""
    net = q.net_scope
    if net is None:
        if q.total.closed is not None:  # the dump reaches the quarter
            return (
                "The board dump has no creation dates; run `perch fetch` to "
                "count opened issues."
            )
        return None
    t = q.total
    span = _span(*(q.closed_span or (q.start, q.through)))
    if net == 0:
        change = "no net change in open issues"
    else:
        change = f"a net change of {net:+d} open {'issue' if abs(net) == 1 else 'issues'}"
    return f"Opened {t.opened}, closed {t.closed} in {span}: {change}."
```

Section 1, two rows after the year-to-date row:

```python
                (
                    f"Labor spent {_span(q.year_start, to)} (year to date)",
                    _money(p.spent_year),
                ),
                (f"Hours planned {_span(q.start, to)}", _hours(p.planned_quarter)),
                (f"Hours booked {_span(q.start, to)}", _hours(p.booked_quarter)),
```

and, right after the non-labor paragraph:

```python
    if pace := _pace(q):
        out.append(("p", pace))
```

Section 3: an Opened column before Closed in every row, the total row's slice shifted by one, and the scope line after the table's note:

```python
    rows = [
        (
            w.label,
            _span(w.start, w.end),
            _count(w.opened),
            _count(w.closed),
            _hours(w.hours),
            _hours(w.per_issue),
        )
        for w in (*q.weeks, q.total)
    ]
    total = "Total"
    if q.board_partial and q.closed_span:
        total = f"Total, closes counted {_span(*q.closed_span)}"
    rows[-1] = (total, *rows[-1][1:5], _hours(q.total_per_issue))
    if (w := q.previous) is not None:
        rows.append(
            (
                f"Previous quarter, {w.label}",
                _span(w.start, w.end),
                _count(w.opened),
                _count(w.closed),
                _hours(w.hours),
                _hours(w.per_issue),
            )
        )
    header = ("Week", "Dates", "Opened", "Closed", "Hours booked", "Hours per issue")
    out.append(("table", 2, header, rows))
    out.append(("p", ...))  # the existing interpolation note, unchanged
    if scope := _scope(q):
        out.append(("p", scope))
```

- [ ] **Step 4: Run the report and CLI quarterly tests**

Run: `~/Documents/tools/perch/bin/pytest perch/tests/test_report_mail.py perch/tests/test_cli_quarterly.py perch/tests/test_quarterly.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add perch/core/report_mail.py perch/tests/test_report_mail.py
git commit -m "feat(quarterly): pace and scope lines in the funder draft, neutral wording"
```

---

### Task 4: History -- `quarter_to_date`, the team row, `perch board`, docs

**Files:**
- Modify: `perch/core/quarterly.py` (new `_through`; `build` uses it; new public `quarter_to_date`)
- Modify: `perch/core/history.py` (`rows_for`)
- Modify: `perch/cli.py` (`board`, the `rows_for` call ~line 298)
- Modify: `CLAUDE.md` (the `core/quarterly.py` and `core/history.py` bullets), `README.md` (the `perch quarterly` paragraph ~line 173 and the history bullet ~line 223)
- Test: `perch/tests/test_quarterly.py`, `perch/tests/test_history.py`, `perch/tests/test_cli.py`

**Interfaces:**
- Consumes: `_plan`, `_team` (Task 1); `_weeks`, `_net` (Task 2); `created`, `APRIL` (Task 2).
- Produces: `quarter_to_date(board: Board | None, money: Money, today: date) -> dict` with keys `pace: float | None`, `net_scope: int | None`; `rows_for(..., quarter: dict | None = None)`; team row keys `pace`, `net_scope`.

- [ ] **Step 1: Write the failing tests**

In `perch/tests/test_quarterly.py`, extend the import to `from perch.core.quarterly import build, last_complete_quarter, parse_quarter, quarter_to_date` and append:

```python
def test_the_history_figures_for_the_quarter_so_far(quarter_world):
    """The latest reading is Apr 19, so Q2 through Apr 19: the pace and net
    scope the report shows."""
    created(quarter_world, APRIL)
    config = load_config(quarter_world)
    board, money = load_board(config.board_dump), load_money(config.budgie_project)
    got = quarter_to_date(board, money, FETCH_DAY)
    assert got["pace"] == pytest.approx(285 / 7 / (13 * 7.968))
    assert got["net_scope"] == 2


def test_outside_the_budgie_year_there_are_no_history_figures(quarter_world):
    config = load_config(quarter_world)
    board = load_board(config.board_dump)
    money = replace(load_money(config.budgie_project), readings={})
    got = quarter_to_date(board, money, date(2027, 2, 1))
    assert got == {"pace": None, "net_scope": None}


def test_without_a_dump_only_the_pace_is_known(quarter_world):
    money = load_money(load_config(quarter_world).budgie_project)
    got = quarter_to_date(None, money, FETCH_DAY)
    assert got["pace"] == pytest.approx(285 / 7 / (13 * 7.968))
    assert got["net_scope"] is None
```

In `perch/tests/test_history.py` append:

```python
def test_the_team_row_records_the_quarters_pace_and_scope(world):
    from perch.cli import _load
    from perch.core.join import person_rows, rollup

    config, board, money, estimates, rates = _load(world)
    rows = person_rows(board, estimates, rates, config.people, money)
    summary = rollup(rows, money)
    team = rows_for(rows, rates, summary, quarter={"pace": 0.4, "net_scope": 2})[-1]
    assert (team["pace"], team["net_scope"]) == (0.4, 2)
    team = rows_for(rows, rates, summary)[-1]
    assert (team["pace"], team["net_scope"]) == (None, None)
```

In `perch/tests/test_cli.py`, inside `test_board_prints_the_join_and_records_the_week`, after `rows` is read, add:

```python
    team = next(r for r in rows if r["kind"] == "team")
    # Q2 to Apr 19: 285/7 h booked. This world has no plan.csv, so Budgie's
    # pace line is straight across the calendar year: 2 x 0.5 x 1,992 x 19/365
    # = 103.693 h planned (quarter_world's plan.csv gives 103.584 by working
    # days). The dump has no created_at, so no scope.
    assert team["pace"] == pytest.approx(285 / 7 / (1992 * 19 / 365))
    assert team["net_scope"] is None
```

(add `import pytest` to `test_cli.py` if it is not imported.)

- [ ] **Step 2: Run them to make sure they fail**

Run: `~/Documents/tools/perch/bin/pytest perch/tests/test_quarterly.py perch/tests/test_history.py perch/tests/test_cli.py -v`
Expected: FAIL with `ImportError: cannot import name 'quarter_to_date'` (collection error for test_quarterly) and `KeyError: 'pace'` / `TypeError: rows_for() got an unexpected keyword argument 'quarter'`.

- [ ] **Step 3: Implement**

In `perch/core/quarterly.py`, before `build`:

```python
def _through(
    money: Money, start: date, end: date, today: date
) -> tuple[date, date | None]:
    """(through, read_to) for the quarter [start, end] seen on `today`: its end,
    or the latest reading while it runs; and where spent stops."""
    through = min(end, money.as_of or today) if today <= end else end
    through = max(through, start)
    as_of = money.as_of
    return through, (min(through, as_of) if as_of else None)


def quarter_to_date(board: Board | None, money: Money, today: date) -> dict:
    """`pace` (booked over planned hours) and `net_scope` for the quarter
    holding `today`, or the latest reading if that is earlier: the history
    row's figures, from the same window code as `build` and without its
    forecast. Both None outside the Budgie year."""
    day = min(today, money.as_of or today)
    found = [(a, b) for a, b in money.span.quarters if a <= day <= b]
    if not found:
        return {"pace": None, "net_scope": None}
    start, end = found[0]
    through, read_to = _through(money, start, end, today)
    read = read_to is not None and read_to >= start
    booked = _team(money, start, read_to, cost=False) if read else None
    planned = _plan(money, start, read_to) if read else None
    return {
        "pace": booked / planned if booked is not None and planned else None,
        "net_scope": _net(_weeks(board, money, start, through)),
    }
```

In `build`, replace the four window lines

```python
    to_date = today <= end
    through = min(end, money.as_of or today) if to_date else end
    through = max(through, start)

    as_of = money.as_of
    read_to = min(through, as_of) if as_of else None
```

with

```python
    to_date = today <= end
    through, read_to = _through(money, start, end, today)
    as_of = money.as_of
```

In `perch/core/history.py`, `rows_for` gains the parameter and the team row two keys:

```python
def rows_for(
    people: list[PersonRow],
    rates: Rates,
    rollup: Rollup,
    accuracy: list[PersonAccuracy] = (),
    left: float | None = None,
    quarter: dict | None = None,
) -> list[dict]:
    """This run's rows; `left` is the team's planned hours left (for `perch cut`),
    `quarter` the quarter so far's `pace` and `net_scope` (quarterly.quarter_to_date)."""
    quarter = quarter or {}
    ...
            "signal": rollup.signal.label if rollup.signal else None,
            "pace": quarter.get("pace"),
            "net_scope": quarter.get("net_scope"),
        }
```

In `perch/cli.py` `board`, import inside the command and pass it:

```python
    from perch.core.quarterly import quarter_to_date
    ...
            rows_for(
                rows,
                rates,
                summary,
                accuracy if estimates else (),
                left=sum(money.left.values()),
                quarter=quarter_to_date(the_board, money, the_board.fetched_on),
            ),
```

Docs. `CLAUDE.md`, the `core/quarterly.py` bullet, append:

```
  Pace is Budgie's booked over planned hours (`Money.booked` / the pace
  line); scope is issues opened (`created_on`) against closed per ISO week,
  None for every week when any issue lacks a creation day. Both in neutral
  words: the draft goes to funders. `quarter_to_date` gives `perch board`
  the same two figures for history.jsonl without the forecast.
```

`CLAUDE.md`, the `core/history.py` bullet: `The team row carries budget, left and signal for perch cut, and pace and net_scope (the quarter so far).`

`README.md`, the `perch quarterly` paragraph: after "budget position and Budgie's forecast at completion," insert "hours booked against hours planned,"; change "issues closed and hours booked per ISO week" to "issues opened and closed and hours booked per ISO week, with the net change in open issues". In the history bullet append: "The team row also keeps the quarter so far's pace (booked over planned hours) and net scope (opened less closed issues), so a research trend can start."

- [ ] **Step 4: Run the whole suite, lint and docs**

Run: `make test && make lint && make docs`
Expected: all tests PASS, ruff clean, sphinx builds with `-W` (no warnings from the new docstrings).

- [ ] **Step 5: Commit**

```bash
git add perch/core/quarterly.py perch/core/history.py perch/cli.py perch/tests CLAUDE.md README.md
git commit -m "feat: pace and net scope in the history team row; docs"
```

---

## After the tasks

- File the follow-up bead: surface the `pace` / `net_scope` trend for the lead (TUI cell or a `trend.py` spark) once weeks are recorded, `--deps discovered-from:perch-w1d`.
- Close the task beads and perch-w1d with a reason.
