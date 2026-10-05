"""`perch events`: what is coming, soonest first, at the team level.

Budget and staffing changes come from `moves` (no name, no hours); milestones
are the open issues grouped by (milestone, due); quarter ends, the year end and
holidays are Budgie's calendar. Pure over the loaded sources: nothing is sent,
no person is named and nothing is ranked. Chronological order only.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from budgie.core.calendar import federal_holidays

from perch.core import blocks as _blocks
from perch.core import moves, sources
from perch.core.board import Board
from perch.core.money import Money
from perch.core.workspace import Home

KINDS = ("budget", "staffing", "milestone", "quarter end", "year end", "holiday")


@dataclass(frozen=True)
class Event:
    day: date
    project: str
    kind: str
    what: str
    n: int | None = None


@dataclass(frozen=True)
class Calendar:
    events: tuple[Event, ...]
    notes: tuple[str, ...]
    errors: tuple[str, ...]


def build(
    project: str, money: Money, board: Board | None, today: date, days: int = 30
) -> tuple[Event, ...]:
    """Events in [today, today + days], inclusive; an open overdue milestone has no lower bound."""
    end = today + timedelta(days=days)
    span = money.span
    out = [
        Event(m.day, project, "budget", moves.describe_budget(m))
        for m in moves.budget(money, today, end)
    ]
    out += [
        Event(m.day, project, "staffing", moves.describe(m))
        for m in moves.staffing(money, today, end)
    ]
    if board is not None:
        groups: dict[tuple[str, date], int] = defaultdict(int)
        for i in board.open:
            if i.milestone and i.milestone_due and i.milestone_due <= end:
                groups[(i.milestone, i.milestone_due)] += 1
        for (name, due), n in groups.items():
            what = f"milestone {name} · {n} open (dump {board.fetched_on:%m-%d})"
            if due < today:
                what += " · overdue"
            out.append(Event(due, project, "milestone", what, n))
    for n, (_, last) in enumerate(span.quarters[:3], 1):
        if today <= last <= end:
            out.append(Event(last, project, "quarter end", f"{span.label}-Q{n}"))
    if today <= span.last <= end:
        out.append(Event(span.last, project, "year end", f"{span.label} ends"))
    for day, name in federal_holidays(span).items():
        if today <= day <= end and day.weekday() < 5 and span.contains(day):
            out.append(Event(day, project, "holiday", name))
    # stable: same-day same-kind ties keep source (file) order
    return tuple(sorted(out, key=lambda e: (e.day, KINDS.index(e.kind))))


def span_note(project: str, money: Money, today: date, days: int) -> str:
    """The dim note for a window that runs past Budgie's year; '' when it does not."""
    if today + timedelta(days=days) <= money.span.last:
        return ""
    return f"{project}: window runs past {money.span.label} end: roll the Budgie year"


def build_all(
    home: Home, today: date, days: int = 30, names: list[str] | None = None
) -> Calendar:
    names = home.projects() if names is None else names
    rows: list[tuple[int, Event]] = []
    notes: list[str] = []
    errors: list[str] = []
    for rank, name in enumerate(names):
        src = sources.load(home, name)
        errors += [f"{name}: {sources.unreadable(e)}" for e in src.errors]
        if src.money is None:
            continue
        rows += [(rank, e) for e in build(name, src.money, src.board, today, days)]
        if note := span_note(name, src.money, today, days):
            notes.append(note)
    same: dict[tuple[date, str, str], list[tuple[int, Event]]] = defaultdict(list)
    for rank, e in rows:
        same[(e.day, e.kind, e.what)].append((rank, e))
    keyed = []
    for group in same.values():
        projects = {e.project for _, e in group}
        if len(projects) > 1:
            e = group[0][1]
            keyed.append(
                (0, -1, Event(e.day, f"all ({len(projects)})", e.kind, e.what, e.n))
            )
        else:
            keyed += [(1, rank, e) for rank, e in group]
    keyed.sort(key=lambda k: (k[2].day, KINDS.index(k[2].kind), k[0], k[1]))
    return Calendar(tuple(k[2] for k in keyed), tuple(notes), tuple(errors))


def blocks(cal: Calendar, today: date, days: int) -> list[dict]:
    if cal.events:
        out = [
            _blocks.table(
                ["date", "project", "kind", "what"],
                [[e.day.isoformat(), e.project, e.kind, e.what] for e in cal.events],
                title=f"Events, {today.isoformat()} + {days} days",
            )
        ]
    else:
        out = [_blocks.text(f"nothing in the next {days} days", tone="dim")]
    out += [_blocks.text(n, tone="dim") for n in cal.notes]
    if cal.errors:
        out.append(_blocks.bullets(list(cal.errors)))
    return out
