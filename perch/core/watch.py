"""`perch watch`: has anyone moved away from their own normal? For the lead only.

Every signal compares a person with their own trailing weeks, never with
anyone else, and says what sample it rests on. A signal flags only when it was
out of line in OUT_OF of the last RECENT weeks, so one odd week never flags. A
flag is a prompt for a conversation, not a verdict. The watch never goes into
the weekly drafts, the emails or any report. Pure logic: no click, no rich,
nothing written or sent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean

from budgie.core.calendar import workdays_between

from perch.core import blocks
from perch.core.accuracy import MIN_COVERAGE, PersonAccuracy, by_person
from perch.core.board import BLOCKED, DONE, Board
from perch.core.estimates import Estimate
from perch.core.history import figures, week_key
from perch.core.join import Rates
from perch.core.money import Money
from perch.core.weekly import MIN_WEEKS, WINDOW, _h, _prior_weeks, _rate, _thin

PLAN_SHARE = 0.7  # booked under this share of planned hours is out of line
SLOWER = 1.5  # hours per issue over this multiple of their own is out of line
MIN_ISSUES = 5  # closed issues each window needs before hours per issue is read
STALL_DAYS = 10  # working days in a Doing column without a move
OVERRUN = 1.3  # booked over estimate above this multiple of their own
NOT_DOING = {"Backlog", DONE, "Failed", BLOCKED}  # gitboard's NOT_WIP, and Blocked
RECENT = 4  # weeks: each window's length, and how many weeks the rule counts
OUT_OF = 3  # out of line in this many of the last RECENT weeks flags

PLAN, PER_ISSUE, DOING, ESTIMATES = (
    "hours vs plan",
    "hours per issue",
    "work in Doing",
    "estimates",
)
WEEK = timedelta(days=7)


@dataclass(frozen=True)
class Signal:
    name: str
    flagged: bool
    text: str
    sample: int  # the weeks or issues the figure rests on


@dataclass(frozen=True)
class PersonWatch:
    name: str
    signals: tuple[Signal, ...]

    @property
    def flags(self) -> int:
        return sum(s.flagged for s in self.signals)


@dataclass(frozen=True)
class Watch:
    title: str
    people: list[PersonWatch]
    weeks: int  # the prior weeks of history behind it

    @property
    def thin(self) -> bool:
        """Under MIN_WEEKS of history: no own-baseline signal can flag yet."""
        return self.weeks < MIN_WEEKS

    @property
    def flags(self) -> int:
        return sum(p.flags for p in self.people)


def _tally(outs: list[bool]) -> tuple[bool, str]:
    n = sum(outs)
    return n >= OUT_OF, f"out of line {n} of the last {RECENT} weeks"


def _anchors(money: Money, name: str) -> list[date]:
    """The RECENT week-ends through their latest reading, latest first.

    Anchored on the reading, not today: a week nobody has read yet would book 0.
    """
    end = money.readings[name][-1][0]
    return [end - k * WEEK for k in range(RECENT)]


def _plan(money: Money, name: str) -> Signal:
    if name not in money.pace or not money.readings.get(name):
        return Signal(PLAN, False, "no hours readings or allocation in Budgie", 0)
    span = RECENT * WEEK
    anchors = _anchors(money, name)
    figures = [
        (money.booked(name, a - span, a), money.planned(name, a - span, a))
        for a in anchors
    ]
    # A week at 0 FTE plans 0 hours, so leave and departures are never out of line.
    flagged, tally = _tally([0 < p and b < PLAN_SHARE * p for b, p in figures])
    booked, planned = figures[0]
    # between readings the hours are interpolated, so say how many there were
    read = sum(anchors[0] - span < day <= anchors[0] for day, _ in money.readings[name])
    return Signal(
        PLAN,
        flagged,
        f"booked {_h(booked)} h vs {_h(planned)} h planned over the {RECENT} weeks "
        f"to {anchors[0]} ({read} reading(s)); {tally}",
        read,
    )


def _per_issue(
    money: Money, board: Board, people: dict[str, str], rates: Rates, name: str
) -> Signal:
    if not money.readings.get(name):
        return Signal(PER_ISSUE, False, "no hours readings in Budgie", 0)
    closed = [
        i.closed_on
        for i in board.closed
        if people.get(i.assignee) == name and money.span.contains(i.closed_on)
    ]

    def window(start: date, end: date) -> tuple[float, int]:
        return money.booked(name, start, end), sum(start < d <= end for d in closed)

    pairs = [
        (window(a - RECENT * WEEK, a), window(a - (RECENT + WINDOW) * WEEK, a - RECENT * WEEK))
        for a in _anchors(money, name)
    ]  # fmt: skip

    def out(now: tuple[float, int], before: tuple[float, int]) -> bool:
        if min(now[1], before[1]) < MIN_ISSUES:
            return False
        return now[0] / now[1] > SLOWER * before[0] / before[1]

    (hours, n), (base_hours, base_n) = pairs[0]
    if min(n, base_n) < MIN_ISSUES:
        return Signal(
            PER_ISSUE,
            False,
            f"too few issues: {n} closed in the last {RECENT} weeks, {base_n} in "
            f"the {WINDOW} before (needs {MIN_ISSUES} in each)",
            n,
        )
    flagged, tally = _tally([out(*pair) for pair in pairs])
    end = _anchors(money, name)[0]
    start = end - (RECENT + WINDOW) * WEEK
    read = sum(start < day <= end for day, _ in money.readings[name])
    text = (
        f"{_rate(hours / n)} h over the last {RECENT} weeks vs own "
        f"{_rate(base_hours / base_n)} h over the {WINDOW} before ({n} and {base_n} "
        f"issues, {read} reading(s)); {tally}"
    )
    factor = rates.types.factors.get(name) if rates.types else None
    if factor is not None:
        text += f"; type-model factor {factor:.2f} (the issue mix can explain a change)"
    return Signal(PER_ISSUE, flagged, text, n)


def _doing(board: Board, people: dict[str, str], name: str) -> Signal:
    """Issues in a Doing-type column (a board list gitboard counts as work in
    progress, not Blocked) that have not moved for STALL_DAYS working days.
    Waiting (Blocked, or an unanswered `Q:`) is someone else's doing."""
    doing = [c for c in board.columns if c not in NOT_DOING]
    found = []
    for i in board.open:
        column = next((c for c in doing if c in i.labels), None)
        if people.get(i.assignee) != name or i.is_waiting or column is None:
            continue
        if i.last_moved is None:
            continue
        days = workdays_between(i.last_moved + timedelta(days=1), board.fetched_on)
        if days >= STALL_DAYS:
            found.append(f"#{i.iid} in {column} for {days} working days")
    if not found:
        text = f"nothing in a Doing column unmoved for {STALL_DAYS} working days"
        return Signal(DOING, False, text, 0)
    return Signal(DOING, True, "; ".join(found), len(found))


def _estimates(
    acc: PersonAccuracy | None, history: list[dict], week: str, name: str
) -> Signal:
    if acc is None:
        return Signal(ESTIMATES, False, "no hours readings, so nothing to measure", 0)
    if acc.ratio is None:
        return Signal(
            ESTIMATES,
            False,
            f"withheld: {acc.covered} of {acc.closed} closed issues had an "
            f"estimate, under the {MIN_COVERAGE:.0%} needed",
            acc.covered,
        )
    ratios = figures(history, "accuracy", name, "ratio")

    def before(w: str) -> list[float]:
        return [ratios[x] for x in _prior_weeks(history, w) if x in ratios]

    def out(w: str) -> bool:
        value, base = (acc.ratio if w == week else ratios.get(w)), before(w)
        return (
            value is not None
            and len(base) >= MIN_WEEKS
            and value > OVERRUN * mean(base)
        )

    base = before(week)
    if len(base) < MIN_WEEKS:
        return Signal(ESTIMATES, False, f"{acc.ratio:.2f}x now; {_thin(len(base))}", 0)
    weeks = [week, *reversed(_prior_weeks(history, week)[-(RECENT - 1) :])]
    flagged, tally = _tally([out(w) for w in weeks])
    return Signal(
        ESTIMATES,
        flagged,
        f"booked over estimate {acc.ratio:.2f}x now vs own {mean(base):.2f}x over "
        f"the {len(base)} weeks before ({acc.covered} of {acc.closed} closed issues "
        f"estimated); {tally}",
        acc.covered,
    )


def watch(
    board: Board,
    money: Money,
    rates: Rates,
    estimates: dict[str, Estimate],
    people: dict[str, str],
    history: list[dict],
) -> Watch:
    """Each person in `people:`, in name order, against their own figures."""
    week = week_key(board.fetched_on)
    weeks = len(_prior_weeks(history, week))
    accuracy = {a.name: a for a in by_person(estimates, board, people, money)}
    out = []
    for name in sorted(set(people.values())):
        if weeks < MIN_WEEKS:
            thin = [Signal(s, False, _thin(weeks), weeks) for s in (PLAN, PER_ISSUE)]
            last = Signal(ESTIMATES, False, _thin(weeks), weeks)
        else:
            thin = [_plan(money, name), _per_issue(money, board, people, rates, name)]
            last = (
                _estimates(accuracy.get(name), history, week, name)
                if estimates
                else Signal(ESTIMATES, False, "no `estimates:` file", 0)
            )
        out.append(PersonWatch(name, (*thin, _doing(board, people, name), last)))
    return Watch(f"{board.project} {board.name}, {week}", out, weeks)


def watch_blocks(result: Watch) -> list[dict]:
    out = [
        blocks.heading(f"Watch, {result.title}", 1),
        blocks.text(
            "Private, for the lead: never for a draft, an email or a report. Each "
            f"person against their own last {WINDOW} weeks; a flag is a prompt "
            "for a conversation, not a verdict.",
            tone="dim",
        ),
    ]
    for person in result.people:
        out.append(blocks.heading(person.name, 2))
        out.append(
            blocks.text(f"{person.flags} flag(s).", tone="warn")
            if person.flags
            else blocks.text("Nothing out of line.", tone="good")
        )
        out.append(
            {
                **blocks.bullets(
                    [
                        f"{'Flag: ' if s.flagged else ''}{s.name}: {s.text}"
                        for s in person.signals
                    ]
                ),
                "md": "\n".join(
                    f"- {'**Flag:** ' if s.flagged else ''}{s.name}: {s.text}"
                    for s in person.signals
                ),
            }
        )
    return out


def render(result: Watch) -> str:
    return blocks.to_md(watch_blocks(result))


def summary(result: Watch) -> str:
    """Monday's last line."""
    if not result.flags:
        return "watch: nothing out of line"
    return f"watch: {result.flags} flags, run perch watch"
