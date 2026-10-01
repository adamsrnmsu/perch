"""The Budgie side: everything perch reads out of a Budgie project.

This module, join.rollup and cut.parse_change (a `PlanEntry`) are the only
places that import budgie.core, so a Budgie refactor has a short list of things
it can break here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from budgie.core.plan import PlanEntry
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
    )


def what_if(
    snap: Snapshot, budget: float | None = None, changes: Sequence[PlanEntry] = ()
) -> Snapshot:
    """Budgie's what-if, with each changed person's current FTE carried from Jan 1.

    Budgie reads a planned person from the plan alone, so `Bob leaves in July`
    for someone only in allocations.csv would zero his whole year. Restating
    his flat FTE as a Jan 1 row first keeps January to June as it was.
    """
    planned = set(snap.plan.names) if snap.plan else set()
    flat = {a.name: a.fte for a in snap.allocations}
    seeds = [
        PlanEntry(name, date(snap.year, 1, 1), flat[name])
        for name in dict.fromkeys(c.name for c in changes)
        if name not in planned and name in flat
    ]
    return snap.what_if(budget=budget, plan_entries=[*seeds, *changes])
