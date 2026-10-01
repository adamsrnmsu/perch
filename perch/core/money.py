"""The Budgie side: everything perch reads out of a Budgie project.

This module, join.rollup, cut.parse_change (a `PlanEntry`) and watch's working-day
count are the only places that import budgie.core, so a Budgie refactor has a
short list of things it can break here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from budgie.core.budget import Budget
from budgie.core.burndown import BurndownStatus, burndown
from budgie.core.monthly import _spent_at  # private until budgie-8u1
from budgie.core.person import Person
from budgie.core.plan import AllocationPlan, PlanEntry
from budgie.core.project import Snapshot, load_snapshot

# (reading date, cumulative hours through that date)
Reading = tuple[date, float]


@dataclass(frozen=True)
class Money:
    year: int
    hourly_cost: dict[str, float]
    readings: dict[str, list[Reading]] = field(default_factory=dict)
    allocated: dict[str, float] = field(default_factory=dict)
    spent: dict[str, float] = field(default_factory=dict)
    non_labor: float = 0.0
    budget: float | None = None
    iterations: int = 10_000
    seed: int | None = None
    # Budgie's burn-down per allocated person: its pace line follows plan.csv
    pace: dict[str, BurndownStatus] = field(default_factory=dict)
    # Passed through from Budgie for `perch quarterly`; perch never re-reads them.
    people: list[Person] = field(default_factory=list)
    pto: float = 0.0
    budget_revisions: Budget | None = None  # budget.csv; None for a pinned number
    plan: AllocationPlan | None = None  # the project's plan.csv

    @property
    def as_of(self) -> date | None:
        """The latest reading anyone has -- the moment the money side describes."""
        days = [series[-1][0] for series in self.readings.values() if series]
        return max(days) if days else None

    @property
    def left(self) -> dict[str, float]:
        """Planned hours each person has not yet spent."""
        return {n: h - self.spent.get(n, 0.0) for n, h in self.allocated.items()}

    @property
    def spent_cost(self) -> float:
        return sum(
            hours * self.hourly_cost[name]
            for name, hours in self.spent.items()
            if name in self.hourly_cost
        )

    def planned(self, name: str, start: date, end: date) -> float | None:
        """Hours Budgie's pace line plans for ``name`` after ``start``, through ``end``."""
        pace = self.pace.get(name)
        return None if pace is None else pace.expected_on(end) - pace.expected_on(start)

    def booked(self, name: str, start: date, end: date) -> float | None:
        """Hours booked after ``start`` through ``end``, interpolated between
        readings the way Budgie's monthly view does. None without readings."""
        series = self.readings.get(name)
        if not series:
            return None
        before_year = date(self.year, 1, 1) - timedelta(days=1)  # the curve's 0

        def at(day: date) -> float:
            return _spent_at(series, max(day, before_year), self.year)

        return at(end) - at(start)


def load_money(project: str | Path) -> Money:
    """The project as Budgie reads it: every input-precedence rule is Budgie's."""
    return money_from(load_snapshot(project))


def money_from(snap: Snapshot) -> Money:
    """Money from an already-loaded (or what-if) Budgie snapshot."""
    return Money(
        year=snap.year,
        hourly_cost={p.name: p.hourly_cost for p in snap.people},
        readings=snap.readings,
        allocated=snap.allocated,
        spent=snap.spent,
        non_labor=snap.non_labor,
        budget=None if snap.budget is None else snap.budget.latest,
        iterations=snap.iterations,
        seed=snap.seed,
        pace={
            a.name: burndown(
                a, snap.year, observations=snap.readings.get(a.name), plan=snap.plan
            )
            for a in snap.allocations
        },
        people=snap.people,
        pto=snap.pto,
        budget_revisions=snap.budget_revisions,
        plan=snap.plan,
    )


def what_if(
    snap: Snapshot, budget: float | None = None, changes: Sequence[PlanEntry] = ()
) -> Snapshot:
    """Budgie's what-if, with each changed person's current FTE carried from Jan 1.

    Budgie reads a planned person from the plan alone, so `Bob leaves in July`
    for someone only in allocations.csv would zero his whole year. Restating
    his flat FTE as a Jan 1 row first keeps January to June as it was.
    Remove the seeding (and its contract asserts) when perch-22d lands in Budgie.
    """
    planned = set(snap.plan.names) if snap.plan else set()
    flat = {a.name: a.fte for a in snap.allocations}
    seeds = [
        PlanEntry(name, date(snap.year, 1, 1), flat[name])
        for name in dict.fromkeys(c.name for c in changes)
        if name not in planned and name in flat
    ]
    return snap.what_if(budget=budget, plan_entries=[*seeds, *changes])
