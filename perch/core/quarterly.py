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
from budgie.core.calendar import YearSpan
from budgie.core.eac import at_completion
from budgie.core.montecarlo import simulate
from budgie.core.plan import AllocationPlan
from budgie.core.signals import SignalResult, evaluate

from perch.core.accuracy import LabelAccuracy, by_label
from perch.core.board import BLOCKED, DONE, Board
from perch.core.estimates import Estimate, issue_key
from perch.core.join import Rates, hours_for
from perch.core.money import Money

DUMP_DAYS = 90  # how far back a dump without `since` reaches (gitboard's HISTORY_DAYS)
NO_DUMP = "no board dump; run `perch fetch`"
RUN_HOURS = "run `perch hours`"
NO_READINGS = f"no hours readings; {RUN_HOURS}"
_QUARTER = re.compile(r"(\d{4}|FY\d{2})-Q([1-4])", re.IGNORECASE)


def parse_quarter(text: str, span: YearSpan) -> tuple[date, date]:
    """`2026-Q3` -> (Jul 1, Sep 30); `FY27-Q1` -> (Oct 1, Dec 31, 2026).

    The quarters are Budgie's year cut in four, so the name must be that
    year's: a calendar project takes `2026-Q3`, a fiscal one `FY27-Q1`.
    """
    match = _QUARTER.fullmatch(text.strip())
    if not match:
        raise ValueError(f"`{text}` is not a quarter; write it like {span.label}-Q3")
    if match[1].upper() != span.label:
        raise ValueError(f"{text} is outside the Budgie project's year, {span.label}")
    return span.quarters[int(match[2]) - 1]


def last_complete_quarter(span: YearSpan, today: date) -> str:
    """The year's last quarter that is over by `today`; Q1 when none is yet."""
    done = sum(1 for _, end in span.quarters if end < today)
    return f"{span.label}-Q{max(done, 1)}"


@dataclass(frozen=True)
class Position:
    spent_quarter: float | None  # labor only; None: no readings in the quarter
    # labor only, the year's first day to the quarter's last reading
    spent_year: float | None
    budget_start: float | None
    budget_end: float | None
    revisions: tuple[BudgetRevision, ...]  # dated inside the quarter
    flat: bool  # a pinned number, so there are no revisions to show
    p10: float
    p50: float
    p90: float
    signal: SignalResult | None
    non_labor: float  # the year's cost lines, in the forecast, not in spent
    # Hours, start of the quarter through read_to; None without readings in it.
    booked_quarter: float | None = None
    # Budgie's pace lines over the same days; None also without allocations.
    planned_quarter: float | None = None


@dataclass(frozen=True)
class Week:
    label: str  # 2026-W15
    start: date  # clipped to the quarter
    end: date
    closed: int | None  # None: no board dump
    hours: float | None  # None: no readings
    # None: outside the dump, or a dump without every issue's creation day
    opened: int | None = None

    @property
    def per_issue(self) -> float | None:
        if not self.closed or self.hours is None:
            return None
        return self.hours / self.closed


@dataclass(frozen=True)
class IssueMiss:
    key: str  # #iid
    estimated: float
    modelled: float  # the closer's rate, not the estimate: MODELLED
    dollars: float | None  # modelled minus estimated at the closer's rate


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
    name: str  # 2026-Q3, or FY27-Q1
    start: date
    end: date
    year_start: date  # the Budgie year's first day: year to date counts from it
    through: date  # the quarter's end, or the latest reading while it runs
    to_date: bool
    as_of: date | None  # the latest hours reading
    read_to: date | None  # where spent stops: the earlier of through and as_of
    position: Position
    # MODELLED. Labels whose last issue closed in the quarter (as the board
    # stood at its end), compared whole;
    # None when there are no estimates or no board to compare them with.
    misses: tuple[LabelAccuracy, ...] | None
    in_progress: tuple[tuple[str, int, int], ...]  # (label, closed by then, issues)
    issue_misses: tuple[IssueMiss, ...]  # `#iid` estimates closed in the quarter
    weeks: tuple[Week, ...]
    blocked_days: int | None
    reopened: int | None
    staffing: tuple[Staffing, ...]
    hours_note: str | None
    board_note: str | None
    board_span: tuple[date, date] | None = None  # what the dump covers of it
    # The quarter before, when the dump's `since` covers all of it (never for Q1,
    # whose previous quarter is outside the Budgie year).
    previous: Week | None = None
    previous_blocked: int | None = None

    @property
    def board_partial(self) -> bool:
        """The dump covers only part of the quarter (so far)."""
        return self.board_span not in (None, (self.start, self.through))

    @property
    def closed_span(self) -> tuple[date, date] | None:
        """First to last day of the weeks whose closes are counted."""
        known = [w for w in self.weeks if w.closed is not None]
        return (known[0].start, known[-1].end) if known else None

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

    @property
    def total_per_issue(self) -> float | None:
        """Hours over issues, from the weeks where both are known."""
        both = [w for w in self.weeks if w.closed is not None and w.hours is not None]
        closed = sum(w.closed for w in both)
        return sum(w.hours for w in both) / closed if closed else None


def _team(money: Money, start: date, end: date, cost: bool) -> float:
    """Hours (or dollars at each person's rate) booked from `start` through `end`.

    `Money.booked` interpolates between readings with Budgie's own monthly rule.
    """
    before = start - timedelta(days=1)
    return sum(
        (money.hourly_cost.get(name, 0.0) if cost else 1.0)
        * money.booked(name, before, end)
        for name in money.readings
    )


def _plan(money: Money, start: date, read_to: date) -> float | None:
    """Hours Budgie's pace lines plan from `start` through `read_to`, summed
    over the allocated people; None when nobody is allocated."""
    if not money.pace:
        return None
    before = start - timedelta(days=1)
    return sum(money.planned(name, before, read_to) for name in money.pace)


def _position(
    money: Money, start: date, end: date, through: date, read_to: date | None
) -> Position:
    def budget_on(day: date) -> float | None:
        if money.budget_revisions is not None:
            return money.budget_revisions.amount_on(day)
        return money.budget

    revisions = money.budget_revisions.revisions if money.budget_revisions else ()
    # Budgie's estimate at completion, as `budgie forecast --as-of` computes it.
    # The cost lines go in as it passes them: a low/high line is sampled too.
    eac = at_completion(
        money.people, money.readings, money.span, as_of=through, plan=money.plan
    )
    sim = simulate(
        eac.people, iterations=money.iterations, seed=money.seed, costs=money.costs
    )
    budget = budget_on(end)
    year_start = money.span.first
    read = read_to is not None and read_to >= start
    return Position(
        spent_quarter=_team(money, start, read_to, cost=True) if read else None,
        spent_year=_team(money, year_start, read_to, cost=True) if read_to else None,
        budget_start=budget_on(start),
        budget_end=budget,
        revisions=tuple(r for r in revisions if start <= r.effective_date <= end),
        flat=money.budget_revisions is None,
        p10=sim.percentile(10),
        p50=sim.percentile(50),
        p90=sim.percentile(90),
        signal=None if budget is None else evaluate(sim, budget),
        non_labor=money.non_labor,
        booked_quarter=_team(money, start, read_to, cost=False) if read else None,
        planned_quarter=_plan(money, start, read_to) if read else None,
    )


def _weeks(board: Board | None, money: Money, start: date, through: date):
    """ISO weeks clipped to the quarter. A week the dump or the readings do not
    wholly cover is unknown (None), not zero."""
    out = []
    monday = start - timedelta(days=start.weekday())
    while monday <= through:
        a, b = max(monday, start), min(monday + timedelta(days=6), through)
        year, number, _ = monday.isocalendar()
        closed = opened = None
        if board is not None and _since(board) <= a and b <= board.fetched_on:
            closed = sum(1 for i in board.closed if a <= i.closed_on <= b)
            opened = _opened(board, a, b)
        read = money.as_of is not None and b <= money.as_of
        hours = _team(money, a, b, cost=False) if read else None
        out.append(Week(f"{year}-W{number:02d}", a, b, closed, hours, opened))
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
    the year's first day is the starting team, not a change.
    """
    plan = money.plan
    if plan is None:
        return ()
    out = []
    for n, entry in enumerate(plan.entries):
        day = entry.effective_date
        if not start <= day <= end or day <= money.span.first:
            continue
        without = AllocationPlan(plan.entries[:n] + plan.entries[n + 1 :])
        name = entry.name
        before_fte = plan.fte_on(name, day - timedelta(days=1))
        hours = plan.allocated_hours(name, money.span, money.pto) - (
            without.allocated_hours(name, money.span, money.pto)
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


def _since(board: Board) -> date:
    """Where the dump's history starts: gitboard's `since`, else its 90 days."""
    return board.since or board.fetched_on - timedelta(days=DUMP_DAYS)


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


def _previous(
    board: Board, money: Money, start: date
) -> tuple[Week | None, int | None]:
    """(totals, blocked issue-days) for the quarter before `start`, or (None,
    None) unless the dump's recorded `since` covers all of it. Q1's previous
    quarter is outside the Budgie year."""
    quarters = money.span.quarters
    n = [a for a, _ in quarters].index(start)
    if n == 0:
        return None, None
    first, end = quarters[n - 1]
    covered = board.since is not None and board.since <= first
    if not covered or end > board.fetched_on:
        return None, None
    closed = sum(1 for i in board.closed if first <= i.closed_on <= end)
    read = money.as_of is not None and end <= money.as_of
    hours = _team(money, first, end, cost=False) if read else None
    name = f"{money.span.label}-Q{n}"
    blocked = _blocked_days(board, first, end, board.since)
    opened = _opened(board, first, end)
    return Week(name, first, end, closed, hours, opened), blocked


def _misses(board, estimates, rates, people, money, start, through):
    """(finished labels, labels in progress, `#iid` rows), all MODELLED.

    Judged by the board as of `through`: an issue closed after it was open then,
    and one created after it was not there (an old dump's issues carry no
    creation day, so they all count). A label is compared whole, and only once
    its last issue closed in the quarter; a label still in progress at
    `through` gets no comparison, never a prorated one. An `#iid` estimate is
    compared on its own issue.
    """
    then = replace(
        board,
        issues=tuple(
            i for i in board.issues if i.created_on is None or i.created_on <= through
        ),
    )
    finished, going = [], []
    for a in by_label(estimates, then, rates, people, money):
        under = [i for i in then.issues if a.label in i.labels]
        # As the board stood on `through`, not at the fetch: closed later is open.
        days = [i.closed_on for i in under if i.closed_on and i.closed_on <= through]
        if not any(start <= d for d in days):
            continue
        if len(days) == len(under):  # by_label's whole-label figures are as of now
            finished.append(a)
        else:
            going.append((a.label, len(days), len(under)))
    issues = []
    for i in board.closed:
        estimate = estimates.get(issue_key(i.iid))
        if estimate is None or not start <= i.closed_on <= through:
            continue
        name = people.get(i.assignee)
        found = hours_for(i, name, {}, rates)  # rates only, as by_label does
        if found is None:
            continue
        rate = money.hourly_cost.get(name)
        diff = found.mode - estimate.hours
        issues.append(
            IssueMiss(
                estimate.key,
                estimate.hours,
                found.mode,
                None if rate is None else diff * rate,
            )
        )
    return tuple(finished), tuple(going), tuple(issues)


def _reopened(board: Board, start: date, through: date) -> int:
    """Issues moved out of Done in the window. A removal on or after the day an
    issue closed is GitLab dropping the list label on close, not a reopen."""
    return sum(
        1
        for i in board.issues
        if any(
            label == DONE
            and action == "remove"
            and start <= day <= through
            and (i.closed_on is None or day < i.closed_on)
            for day, action, label in i.transitions
        )
    )


def _day(day: date) -> str:
    return f"{day:%b} {day.day}"


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
    start, end = parse_quarter(quarter, money.span)
    to_date = today <= end
    through, read_to = _through(money, start, end, today)
    as_of = money.as_of
    if as_of is None:
        hours_note = NO_READINGS
    elif as_of < start:
        hours_note = f"readings run to {_day(as_of)}, before the quarter; " + RUN_HOURS
    elif as_of < end:
        hours_note = (
            f"readings run to {_day(as_of)}; spent covers {_day(start)} – "
            f"{_day(read_to)}; {RUN_HOURS}"
        )
    else:
        hours_note = None

    board_note = misses = blocked = reopened = board_span = None
    previous = previous_blocked = None
    in_progress = issue_misses = ()
    if board is None:
        board_note = NO_DUMP
    else:
        since = _since(board)
        covered = (max(start, since), min(through, board.fetched_on))
        reaches = covered[0] <= covered[1]
        board_span = covered if reaches else None
        if not reaches:
            board_note = f"the board dump is from {board.fetched_on}; run `perch fetch`"
        elif covered != (start, through):
            reach = (
                f"starts {_day(board.since)}"
                if board.since
                else f"keeps {DUMP_DAYS} days"
            )
            board_note = (
                f"covers {_day(covered[0])} – {_day(covered[1])}; "
                f"the board dump {reach}"
            )
        if estimates and rates is not None:
            misses, in_progress, issue_misses = _misses(
                board, estimates, rates, people, money, start, through
            )
        if reaches:
            blocked = _blocked_days(board, start, covered[1], since)
            reopened = _reopened(board, start, through)
        previous, previous_blocked = _previous(board, money, start)

    return Quarter(
        project=project,
        name=f"{money.span.label}-Q{money.span.quarters.index((start, end)) + 1}",
        start=start,
        end=end,
        year_start=money.span.first,
        through=through,
        to_date=to_date,
        as_of=as_of,
        read_to=read_to,
        position=_position(money, start, end, through, read_to),
        misses=misses,
        in_progress=in_progress,
        issue_misses=issue_misses,
        weeks=_weeks(board, money, start, through),
        blocked_days=blocked,
        reopened=reopened,
        staffing=_staffing(money, start, end),
        hours_note=hours_note,
        board_note=board_note,
        board_span=board_span,
        previous=previous,
        previous_blocked=previous_blocked,
    )
