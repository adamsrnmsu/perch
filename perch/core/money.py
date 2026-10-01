"""The Budgie side: everything perch reads out of a Budgie project.

This module, join.rollup and watch's working-day count are the only places
that import budgie.core, so a Budgie refactor has a short list of things it
can break here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from budgie.core.burndown import BurndownStatus, burndown
from budgie.core.monthly import _spent_at  # private until budgie-8u1
from budgie.core.project import load_snapshot

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
    snap = load_snapshot(project)
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
    )
