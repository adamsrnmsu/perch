"""The tape: what changed, newest first, from files only.

One line per event: a stoplight flip or figure move between recorded weeks, a
budget or staffing change, the latest hours reading, the board fetch, the
issues closed on a day, a failed Monday step, an unreadable source. Team
level: no person, note or exception text. Never reads the watch, a person,
type or accuracy row.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from perch.core import asof as _asof
from perch.core import blocks as _blocks
from perch.core import moves, trend
from perch.core.sources import Sources, load, unreadable
from perch.core.workspace import Home

HORIZON_DAYS = 56  # trend.WINDOW (8) weeks
KINDS = (
    "flip",
    "figures",
    "budget",
    "plan",
    "hours",
    "board",
    "closed",
    "failed",
    "error",
)


@dataclass(frozen=True)
class TapeEntry:
    day: date
    project: str
    kind: str
    text: str


def project_tape(
    src: Sources,
    name: str,
    today: date,
    days: int = HORIZON_DAYS,
    asof: str | None = None,
) -> list[TapeEntry]:
    rows = src.rows
    if asof:
        today = min(today, _asof.week_end(asof))
        rows = _asof.until(rows, asof)
    start = today - timedelta(days=days)
    out: list[TapeEntry] = []

    def add(day: date, kind: str, text: str) -> None:
        if start <= day <= today:
            out.append(TapeEntry(day, name, kind, text))

    team = {r["week"]: r for r in rows if r["kind"] == "team"}
    for c in reversed(trend.changes(rows)):
        try:
            day = date.fromisoformat(team[c.after]["date"])
        except (KeyError, TypeError, ValueError):
            continue  # an old row without a date has no place on the tape
        text = trend.describe("", c).strip()
        if text:
            add(day, "flip" if c.signal else "figures", text)
    if src.money:
        for b in moves.budget(src.money, start, today):
            add(b.day, "budget", moves.describe_budget(b))
        for s in moves.staffing(src.money, start, today):
            add(s.day, "plan", "plan: " + moves.describe(s))
        if src.money.as_of:
            add(
                src.money.as_of,
                "hours",
                f"hours reading through {src.money.as_of:%m-%d}",
            )
    if src.board:
        add(src.board.fetched_on, "board", f"board fetched, {len(src.board.open)} open")
        closed = Counter(i.closed_on for i in src.board.closed if i.closed_on)
        for day in sorted(closed, reverse=True):
            n = closed[day]
            add(day, "closed", f"{n} issue{'s' * (n != 1)} closed")
    if src.failure and not asof:  # live files: not history
        try:
            at = datetime.fromisoformat(str(src.failure["at"])).date()
            add(
                at,
                "failed",
                f"monday: {src.failure['step']} exited {src.failure['code']}",
            )
        except (KeyError, ValueError):
            pass
    for source in () if asof else src.errors:
        add(today, "error", unreadable(source))
    return merge({name: out}, [name])


def merge(by_project: dict[str, list[TapeEntry]], order: list[str]) -> list[TapeEntry]:
    rank = {n: i for i, n in enumerate(order)}
    every = [e for n in order for e in by_project.get(n, [])]
    return sorted(
        every, key=lambda e: (-e.day.toordinal(), rank[e.project], KINDS.index(e.kind))
    )


def tape(
    home: Home,
    today: date,
    days: int = HORIZON_DAYS,
    names: list[str] | None = None,
) -> list[TapeEntry]:
    order = names if names is not None else home.projects()
    return merge({n: project_tape(load(home, n), n, today, days) for n in order}, order)


def blocks(entries: list[TapeEntry], days: int = HORIZON_DAYS) -> list[dict]:
    title = f"Tape · last {days} days, from files only"
    if not entries:
        return [_blocks.text(f"{title}: nothing", tone="dim")]
    rows = [[f"{e.day:%m-%d}", e.project, e.kind, e.text] for e in entries]
    return [_blocks.table(["date", "project", "kind", "text"], rows, title=title)]
