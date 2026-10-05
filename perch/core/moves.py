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
