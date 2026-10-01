"""`perch cut`: the join run backwards -- what a budget cut or plan change does.

perch shows the gap and each milestone's open work; it never orders issues or
suggests what to drop. The allocation math is Budgie's (`money.what_if`).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from budgie.core.plan import PlanEntry

from perch.core.board import Board
from perch.core.estimates import Estimate
from perch.core.join import (
    UNASSIGNED,
    UNMAPPED,
    PersonRow,
    Rates,
    hours_for,
    person_rows,
    rollup,
)
from perch.core.money import Money


def parse_change(
    flag: str, names: set[str], year: int, *, leaves: bool = False
) -> PlanEntry:
    """`--leaves NAME:YYYY-MM-DD` (0 FTE from then) or `--fte NAME:YYYY-MM-DD:FTE`."""
    option = "--leaves" if leaves else "--fte"
    shape = "NAME:YYYY-MM-DD" if leaves else "NAME:YYYY-MM-DD:FTE"

    def refuse(why: str) -> ValueError:
        return ValueError(f"{option} {flag}: {why}")

    parts = flag.split(":")
    if len(parts) != (2 if leaves else 3):
        raise refuse(f"expected {shape}")
    name, day = parts[0], parts[1]
    if name not in names:
        known = ", ".join(sorted(names))
        raise refuse(f"{name!r} is not in the Budgie project's people ({known})")
    try:
        when = date.fromisoformat(day)
    except ValueError:
        raise refuse(f"{day!r} is not a YYYY-MM-DD date") from None
    if when.year != year:
        raise refuse(f"{when} is outside {year}")
    try:
        fte = 0.0 if leaves else float(parts[2])
    except ValueError:
        fte = -1.0
    if not 0 <= fte <= 1:
        raise refuse(f"FTE must be between 0 and 1, not {parts[2]!r}")
    return PlanEntry(name, when, fte)


@dataclass(frozen=True)
class Side:
    """The team-level figures on one side of the change."""

    left: float | None  # the team's planned hours left
    budget: float | None
    clear_p50: float | None
    headroom: float | None
    signal: str | None
    people_left: dict[str, float]
    old_row: bool = False  # a history row from before budget/left were recorded


def side_from_money(
    money: Money, rows: list[PersonRow], iterations=None, seed=None
) -> Side:
    summary = rollup(rows, money, iterations=iterations, seed=seed)
    return Side(
        left=sum(money.left.values()),
        budget=summary.budget,
        clear_p50=summary.clear_p50,
        headroom=summary.headroom,
        signal=summary.signal.label if summary.signal else None,
        people_left=money.left,
    )


def side_from_history(week: list[dict]) -> Side:
    """A recorded `perch board` week; a figure it never recorded is None."""
    team = next((r for r in week if r.get("kind") == "team"), {})
    return Side(
        left=team.get("left"),
        budget=team.get("budget"),
        clear_p50=team.get("clear_p50"),
        headroom=team.get("headroom"),
        signal=team.get("signal"),
        people_left={
            r["name"]: r["left"]
            for r in week
            if r.get("kind") == "person" and r.get("left") is not None
        },
        old_row="budget" not in team,
    )


@dataclass(frozen=True)
class PersonCut:
    name: str
    left_before: float | None
    left_after: float | None
    row: PersonRow | None  # their open issues and modelled hours, if any
    issues: tuple[int, ...] = ()  # open issue iids
    leaves: date | None = None


@dataclass(frozen=True)
class Milestone:
    name: str | None  # None: issues with no milestone
    due: date | None
    open: int
    low: float
    mode: float
    high: float


@dataclass(frozen=True)
class Cut:
    before: Side
    after: Side
    board_hours: float
    people: list[PersonCut]
    milestones: list[Milestone]

    @property
    def spare(self) -> float | None:
        """Hours left after the change less the board. Negative: short."""
        return None if self.after.left is None else self.after.left - self.board_hours


def compare(
    before: Money | list[dict],
    after: Money,
    board: Board,
    estimates: dict[str, Estimate],
    rates: Rates,
    people: dict[str, str],
    changes: Sequence[PlanEntry] = (),
    iterations: int | None = None,
    seed: int | None = None,
) -> Cut:
    """Before (a Money, or a recorded history week) against after, on this board."""
    rows = person_rows(board, estimates, rates, people, after)
    if isinstance(before, Money):
        old = person_rows(board, estimates, rates, people, before)
        start = side_from_money(before, old, iterations, seed)
    else:
        start = side_from_history(before)
    end = side_from_money(after, rows, iterations, seed)

    by_name = {r.name: r for r in rows}
    leaving = {c.name: c.effective_date for c in changes if c.fte == 0}
    named = set(start.people_left) | set(end.people_left)
    named |= {r.name for r in rows if r.name not in (UNASSIGNED, UNMAPPED)}
    order = sorted(named) + [n for n in (UNASSIGNED, UNMAPPED) if n in by_name]
    cuts = [
        PersonCut(
            name=name,
            left_before=start.people_left.get(name),
            left_after=end.people_left.get(name),
            row=by_name.get(name),
            issues=tuple(i.iid for i in board.open if people.get(i.assignee) == name),
            leaves=leaving.get(name),
        )
        for name in order
    ]
    return Cut(
        before=start,
        after=end,
        board_hours=sum(r.mode for r in rows),
        people=cuts,
        milestones=_milestones(board, estimates, rates, people),
    )


def _milestones(board, estimates, rates, people) -> list[Milestone]:
    """Each milestone's open issues and hours, earliest due first; no-milestone last."""
    groups: dict[str | None, list] = {}
    for issue in board.open:
        groups.setdefault(issue.milestone, []).append(issue)
    out = []
    for name, issues in groups.items():
        found = [hours_for(i, people.get(i.assignee), estimates, rates) for i in issues]
        known = [h for h in found if h is not None]
        out.append(
            Milestone(
                name=name,
                due=min(
                    (i.milestone_due for i in issues if i.milestone_due), default=None
                ),
                open=len(issues),
                low=sum(h.low for h in known),
                mode=sum(h.mode for h in known),
                high=sum(h.high for h in known),
            )
        )
    return sorted(out, key=lambda m: (m.name is None, m.due or date.max, m.name or ""))
