"""The Budgie side: everything perch reads out of a Budgie project.

This module and join.rollup are the only places that import budgie.core, so a
Budgie refactor has a short list of things it can break here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from budgie.core.budget import Budget
from budgie.core.person import Person
from budgie.core.plan import AllocationPlan
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
        people=snap.people,
        pto=snap.pto,
        budget_revisions=snap.budget_revisions,
        plan=snap.plan,
    )
