"""The Budgie side: everything perch reads out of a Budgie project.

This module and join.rollup are the only places that import budgie.core, so a
Budgie refactor has a short list of things it can break here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from budgie.core.actuals import load_weekly_actuals, monthly_to_observations
from budgie.core.allocation import load_allocations
from budgie.core.budget import coerce_budget
from budgie.core.calendar import productive_hours
from budgie.core.costs import load_costs, total_cost
from budgie.core.loader import load_people
from budgie.core.monthly import load_monthly_actuals
from budgie.core.plan import load_plan
from budgie.core.workspace import load_workspace

from perch.core.config import BUDGIE_CONFIG

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
    workspace = load_workspace(Path(project) / BUDGIE_CONFIG)
    year = workspace.setting("year")
    if year is None:
        raise ValueError(f"{workspace.config_path}: `year` is not set")
    pto = workspace.setting("pto", 0.0)
    ceiling = productive_hours(year, pto_days=pto)

    people_csv = workspace.resolve("people")
    if people_csv is None:
        raise FileNotFoundError(f"{workspace.root}: no people.csv; perch needs rates")
    people = load_people(people_csv, productive_hours=ceiling)

    # Weekly cumulative readings win over monthly hours, the same as Budgie.
    if weekly := workspace.resolve("weekly"):
        readings = load_weekly_actuals(weekly, year)
    elif monthly := workspace.resolve("actuals"):
        readings = {
            name: monthly_to_observations(year, months)
            for name, months in load_monthly_actuals(monthly).items()
        }
    else:
        readings = {}
    readings = {n: sorted(series) for n, series in readings.items() if series}

    plan_csv = workspace.resolve("plan")
    plan = load_plan(plan_csv) if plan_csv else None
    allocated: dict[str, float] = {}
    spent: dict[str, float] = {}
    if alloc_csv := workspace.resolve("allocations"):
        for alloc in load_allocations(alloc_csv, ceiling, plan=plan):
            allocated[alloc.name] = alloc.allocated_hours
            spent[alloc.name] = alloc.hours_spent
    elif plan is not None:
        allocated = plan.team_hours(year, pto_days=pto)
    # A dated reading beats allocations.csv's undated scalar.
    spent.update({name: series[-1][1] for name, series in readings.items()})

    costs_csv = workspace.resolve("costs")
    pinned = workspace.setting("budget")
    budget_source = pinned if pinned is not None else workspace.resolve("budget")
    return Money(
        year=year,
        hourly_cost={p.name: p.hourly_cost for p in people},
        readings=readings,
        allocated=allocated,
        spent=spent,
        non_labor=total_cost(load_costs(costs_csv)) if costs_csv else 0.0,
        budget=None if budget_source is None else coerce_budget(budget_source).latest,
        iterations=workspace.setting("iterations", 10_000),
        seed=workspace.setting("seed"),
    )
