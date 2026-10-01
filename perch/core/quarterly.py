"""`perch quarterly`: one project's quarter for the funder, rebuilt from sources.

Hours come from Budgie's readings, the budget and plan from Budgie's snapshot,
the forecast from Budgie's own engine, and the work from gitboard's dump --
never from perch's history.jsonl, which only starts when perch was first run.
Team level only: no person's name sits next to a number except in staffing
changes, which are facts from plan.csv.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date, timedelta

from budgie.core.budget import BudgetRevision
from budgie.core.eac import at_completion
from budgie.core.montecarlo import simulate
from budgie.core.plan import AllocationPlan
from budgie.core.signals import SignalResult, evaluate

from perch.core.accuracy import LabelAccuracy, by_label
from perch.core.board import BLOCKED, DONE, Board
from perch.core.estimates import Estimate
from perch.core.join import Rates
from perch.core.money import Money, Reading

DUMP_DAYS = 90  # how far back a board dump reaches (gitboard's HISTORY_DAYS)
NO_DUMP = "no board dump; run `perch fetch`"
NO_READINGS = "no hours readings; run `perch hours`"
_QUARTER = re.compile(r"(\d{4})-Q([1-4])", re.IGNORECASE)


def parse_quarter(text: str) -> tuple[date, date]:
    """`2026-Q3` -> (Jul 1, Sep 30): calendar quarters, Q1 is Jan-Mar."""
    match = _QUARTER.fullmatch(text.strip())
    if not match:
        raise ValueError(f"`{text}` is not a quarter; write it like 2026-Q3")
    year, number = int(match[1]), int(match[2])
    start = date(year, 3 * number - 2, 1)
    end = date(year + 1, 1, 1) if number == 4 else date(year, 3 * number + 1, 1)
    return start, end - timedelta(days=1)


def last_complete_quarter(year: int, today: date) -> str:
    """The year's last quarter that is over by `today`; Q1 when none is yet."""
    if today.year > year:
        return f"{year}-Q4"
    done = (today.month - 1) // 3 if today.year == year else 0
    return f"{year}-Q{max(done, 1)}"


def _booked(series: list[Reading], day: date, year: int) -> float:
    """Cumulative hours by the end of `day`, linear between readings.

    The curve starts at 0 on Dec 31 and stays at the last reading after it:
    the same rule as Budgie's `monthly._spent_at`, which is private, so this is
    that reading arithmetic again, not budget math.
    """
    prev_day, prev_hours = date(year, 1, 1) - timedelta(days=1), 0.0
    for when, hours in sorted(series):
        if when >= day:
            share = (day - prev_day).days / (when - prev_day).days
            return prev_hours + (hours - prev_hours) * share
        prev_day, prev_hours = when, hours
    return prev_hours


@dataclass(frozen=True)
class Position:
    spent_quarter: float | None  # None: no readings
    spent_year: float | None
    budget_start: float | None
    budget_end: float | None
    revisions: tuple[BudgetRevision, ...]  # dated inside the quarter
    flat: bool  # a pinned number, so there are no revisions to show
    p10: float
    p50: float
    p90: float
    signal: SignalResult | None


@dataclass(frozen=True)
class Week:
    label: str  # 2026-W15
    start: date  # clipped to the quarter
    end: date
    closed: int | None  # None: no board dump
    hours: float | None  # None: no readings

    @property
    def per_issue(self) -> float | None:
        if not self.closed or self.hours is None:
            return None
        return self.hours / self.closed


@dataclass(frozen=True)
class Staffing:
    name: str
    day: date
    kind: str  # joins, leaves, FTE change
    fte_before: float
    fte_after: float
    hours: float  # change in the year's planned hours
    dollars: float | None  # at the person's rate; None when Budgie has no rate


@dataclass(frozen=True)
class Quarter:
    project: str
    name: str  # 2026-Q3
    start: date
    end: date
    through: date  # the quarter's end, or the latest reading while it runs
    to_date: bool
    as_of: date | None  # the latest hours reading
    position: Position
    misses: tuple[LabelAccuracy, ...] | None  # MODELLED; None: nothing to compare
    weeks: tuple[Week, ...]
    blocked_days: int | None
    reopened: int | None
    staffing: tuple[Staffing, ...]
    hours_note: str | None
    board_note: str | None

    @property
    def total(self) -> Week:
        closed = [w.closed for w in self.weeks if w.closed is not None]
        hours = [w.hours for w in self.weeks if w.hours is not None]
        return Week(
            self.name,
            self.start,
            self.through,
            sum(closed) if closed else None,
            sum(hours) if hours else None,
        )


def _team(money: Money, start: date, end: date, cost: bool) -> float:
    """Hours (or dollars at each person's rate) booked from `start` to `end`."""
    total = 0.0
    for name, series in money.readings.items():
        rate = money.hourly_cost.get(name, 0.0) if cost else 1.0
        before = start - timedelta(days=1)
        total += rate * (
            _booked(series, end, money.year) - _booked(series, before, money.year)
        )
    return total


def _position(money: Money, start: date, end: date, through: date) -> Position:
    def budget_on(day: date) -> float | None:
        if money.budget_revisions is not None:
            return money.budget_revisions.amount_on(day)
        return money.budget

    revisions = money.budget_revisions.revisions if money.budget_revisions else ()
    # Budgie's estimate at completion, as `budgie forecast --as-of` computes it.
    # Non-labor is its fixed total: the snapshot carries no cost lines.
    eac = at_completion(
        money.people, money.readings, money.year, as_of=through, plan=money.plan
    )
    sim = simulate(eac.people, iterations=money.iterations, seed=money.seed)
    sim = replace(sim, total_costs=sim.total_costs + money.non_labor)
    budget = budget_on(end)
    year_start = date(money.year, 1, 1)
    return Position(
        spent_quarter=_team(money, start, through, cost=True)
        if money.readings
        else None,
        spent_year=_team(money, year_start, through, cost=True)
        if money.readings
        else None,
        budget_start=budget_on(start),
        budget_end=budget,
        revisions=tuple(r for r in revisions if start <= r.effective_date <= end),
        flat=money.budget_revisions is None,
        p10=sim.percentile(10),
        p50=sim.percentile(50),
        p90=sim.percentile(90),
        signal=None if budget is None else evaluate(sim, budget),
    )


def _weeks(board: Board | None, money: Money, start: date, through: date):
    out = []
    monday = start - timedelta(days=start.weekday())
    while monday <= through:
        a, b = max(monday, start), min(monday + timedelta(days=6), through)
        year, number, _ = monday.isocalendar()
        closed = None
        if board is not None:
            closed = sum(1 for i in board.closed if a <= i.closed_on <= b)
        # A week past the latest reading is unknown, not zero.
        read = money.as_of is not None and b <= money.as_of
        hours = _team(money, a, b, cost=False) if read else None
        out.append(Week(f"{year}-W{number:02d}", a, b, closed, hours))
        monday += timedelta(days=7)
    return tuple(out)


def _blocked_days(board: Board, start: date, through: date, since: date) -> int:
    """Issue-days in Blocked inside [start, through], from Blocked moves.

    An issue already Blocked when the dump's history begins (its first move is
    out of Blocked, or it carries the label with no move) counts from `since`.
    """
    stop = through + timedelta(days=1)
    days = 0
    for issue in board.issues:
        moves = [(d, a) for d, a, label in issue.transitions if label == BLOCKED]
        first = moves[0][1] if moves else None
        entered = (
            since if first == "remove" or (not moves and issue.is_blocked) else None
        )
        spans = []
        for day, action in moves:
            if action == "add":
                entered = entered or day
            elif entered is not None:
                spans.append((entered, day))
                entered = None
        if entered is not None:  # still Blocked, or closed while Blocked
            closed = issue.closed_on
            spans.append((entered, closed + timedelta(days=1) if closed else stop))
        for a, b in spans:
            days += max(0, (min(b, stop) - max(a, start)).days)
    return days


def _staffing(money: Money, start: date, end: date) -> tuple[Staffing, ...]:
    """Each plan.csv change dated in the quarter, costed by the year's plan hours.

    Before is the plan without that row; after is the plan as written. A row on
    Jan 1 is the starting team, not a change.
    """
    plan = money.plan
    if plan is None:
        return ()
    out = []
    for n, entry in enumerate(plan.entries):
        day = entry.effective_date
        if not start <= day <= end or day <= date(money.year, 1, 1):
            continue
        without = AllocationPlan(plan.entries[:n] + plan.entries[n + 1 :])
        name = entry.name
        before_fte = plan.fte_on(name, day - timedelta(days=1))
        hours = plan.allocated_hours(name, money.year, money.pto) - (
            without.allocated_hours(name, money.year, money.pto)
        )
        rate = money.hourly_cost.get(name)
        if before_fte == 0:
            kind = "joins"
        elif entry.fte == 0:
            kind = "leaves"
        else:
            kind = "FTE change"
        out.append(
            Staffing(
                name,
                day,
                kind,
                before_fte,
                entry.fte,
                hours,
                None if rate is None else hours * rate,
            )
        )
    return tuple(sorted(out, key=lambda s: (s.day, s.name)))


def _day(day: date) -> str:
    return f"{day:%b} {day.day}"


def build(
    board: Board | None,
    money: Money,
    estimates: dict[str, Estimate],
    rates: Rates | None,
    people: dict[str, str],
    quarter: str,
    today: date,
    project: str,
) -> Quarter:
    """The quarter's report. `board` is None when there is no dump yet."""
    start, end = parse_quarter(quarter)
    if start.year != money.year:
        raise ValueError(
            f"{quarter} is outside the Budgie project's year, {money.year}"
        )
    to_date = today <= end
    through = min(end, money.as_of or today) if to_date else end
    through = max(through, start)

    board_note = misses = blocked = reopened = None
    if board is None:
        board_note = NO_DUMP
    else:
        since = board.fetched_on - timedelta(days=DUMP_DAYS)
        covered = (max(start, since), min(through, board.fetched_on))
        if covered[1] < covered[0]:
            board_note = f"the board dump is from {board.fetched_on}; run `perch fetch`"
        elif covered != (start, through):
            board_note = (
                f"covers {_day(covered[0])} – {_day(covered[1])}; "
                f"the board dump keeps {DUMP_DAYS} days"
            )
        closed = tuple(i for i in board.closed if start <= i.closed_on <= through)
        if estimates and rates is not None:
            found = by_label(
                estimates, replace(board, issues=closed), rates, people, money
            )
            misses = tuple(a for a in found if a.issues)
        blocked = _blocked_days(board, start, covered[1], since)
        reopened = sum(
            1
            for i in board.issues
            if any(
                label == DONE and action == "remove" and start <= day <= through
                for day, action, label in i.transitions
            )
        )

    return Quarter(
        project=project,
        name=f"{start.year}-Q{(start.month + 2) // 3}",
        start=start,
        end=end,
        through=through,
        to_date=to_date,
        as_of=money.as_of,
        position=_position(money, start, end, through),
        misses=misses,
        weeks=_weeks(board, money, start, through),
        blocked_days=blocked,
        reopened=reopened,
        staffing=_staffing(money, start, end),
        hours_note=None if money.readings else NO_READINGS,
        board_note=board_note,
    )
