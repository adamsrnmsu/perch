"""The Budgie side: everything perch reads out of a Budgie project.

This module, estimates (csvio), join (rollup, `YearSpan`), rate and cut (`YearSpan`;
cut also `PlanEntry`), quarterly (the forecast, `YearSpan`) and watch (working days)
are the only places that import budgie.core, so a Budgie refactor has a short list
of things it can break here.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from budgie.core.budget import Budget
from budgie.core.burn import BurnSeries
from budgie.core.burndown import BurndownStatus, burndown
from budgie.core.calendar import YearSpan
from budgie.core.costs import CostItem
from budgie.core.monthly import spent_at
from budgie.core.person import Person
from budgie.core.plan import AllocationPlan, PlanEntry
from budgie.core.project import Snapshot, load_snapshot

# (reading date, cumulative hours through that date)
Reading = tuple[date, float]


@dataclass(frozen=True)
class Money:
    span: YearSpan
    hourly_cost: dict[str, float]
    readings: dict[str, list[Reading]] = field(default_factory=dict)
    allocated: dict[str, float] = field(default_factory=dict)
    spent: dict[str, float] = field(default_factory=dict)
    non_labor: float = 0.0  # the year's cost lines, summed
    costs: list[CostItem] = field(default_factory=list)  # for simulate(costs=)
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
    # Budgie's Snapshot.planned_through: a planned person's hours through a day.
    planned_on: Callable[[str, date], float | None] | None = field(
        default=None, compare=False
    )
    # Budgie's Snapshot.burn_series: the chart's monthly series. Lazy: it simulates.
    burn: Callable[[], BurnSeries] | None = field(default=None, compare=False)

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

    def team_planned(self, start: date, end: date) -> float | None:
        """Planned team hours after ``start`` through ``end``, read the way
        `booked` reads hours: sampled on each person's reading days (the team's,
        for someone without readings) and interpolated between them by Budgie's
        `spent_at`. The plan counts working days and readings interpolate by
        calendar day, so only the same sampling makes the two comparable.

        Budgie's planned people are `allocated` (allocations.csv, else the plan
        alone) and their hours its `planned_through`. Someone who books without
        being planned adds to booked hours only. None when nobody is planned or
        nothing has been read.
        """
        planned_on = self.planned_on
        team = sorted({day for series in self.readings.values() for day, _ in series})
        if planned_on is None or not self.allocated or not team:
            return None

        def at(name: str, day: date) -> float:
            days = [d for d, _ in self.readings.get(name, ())] or team
            series = [(d, planned_on(name, d)) for d in days]
            return spent_at(series, max(day, self.span.zero), self.span)

        return sum(at(name, end) - at(name, start) for name in self.allocated)

    def booked(self, name: str, start: date, end: date) -> float | None:
        """Hours booked after ``start`` through ``end``, interpolated between
        readings the way Budgie's monthly view does. None without readings."""
        series = self.readings.get(name)
        if not series:
            return None

        def at(day: date) -> float:
            return spent_at(series, max(day, self.span.zero), self.span)

        return at(end) - at(start)


def load_money(project: str | Path) -> Money:
    """The project as Budgie reads it: every input-precedence rule is Budgie's."""
    return money_from(load_snapshot(project))


def money_from(snap: Snapshot) -> Money:
    """Money from an already-loaded (or what-if) Budgie snapshot."""
    return Money(
        span=snap.span,
        hourly_cost={p.name: p.hourly_cost for p in snap.people},
        readings=snap.readings,
        allocated=snap.allocated,
        spent=snap.spent,
        non_labor=snap.non_labor,
        costs=snap.costs,
        budget=None if snap.budget is None else snap.budget.latest,
        iterations=snap.iterations,
        seed=snap.seed,
        pace={
            a.name: burndown(
                a, snap.span, observations=snap.readings.get(a.name), plan=snap.plan
            )
            for a in snap.allocations
        },
        people=snap.people,
        pto=snap.pto,
        budget_revisions=snap.budget_revisions,
        plan=snap.plan,
        planned_on=snap.planned_through,
        burn=snap.burn_series,
    )


def what_if(
    snap: Snapshot, budget: float | None = None, changes: Sequence[PlanEntry] = ()
) -> Snapshot:
    """Budgie's what-if: a new budget and/or plan changes. Budgie carries a
    changed person who is only in allocations.csv at their flat FTE from the year's first day,
    so `Bob leaves in July` keeps January to June as it was."""
    return snap.what_if(budget=budget, plan_entries=changes)
