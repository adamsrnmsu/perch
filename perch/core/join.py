"""The join: open issues -> hours -> dollars, against the hours and budget left."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from budgie.core.calendar import YearSpan
from budgie.core.montecarlo import simulate
from budgie.core.person import HoursEstimate, Person
from budgie.core.signals import SignalResult, evaluate

from perch.core.board import Board, Issue
from perch.core.estimates import Estimate, issue_key
from perch.core.money import Money, Reading
from perch.core.rate import (
    Closed,
    Rate,
    TypeModel,
    build_intervals,
    fit_types,
    person_rates,
    team_rate,
)

ESTIMATES = "estimates"
TYPE_MODEL = "type model"
UNASSIGNED = "unassigned"
UNMAPPED = "unmapped"
STALE_DAYS = 14


@dataclass(frozen=True)
class Rates:
    people: dict[str, Rate]
    team: Rate | None
    types: TypeModel | None


def calibrate(
    readings: dict[str, list[Reading]],
    board: Board,
    people: dict[str, str],
    span: YearSpan,
) -> Rates:
    """Rates from the year's readings and the issues each mapped person closed.

    Only from where the dump's history starts: earlier closes are not in it.
    """
    closed: list[Closed] = [
        (people[i.assignee], i.closed_on, i.type)
        for i in board.closed
        if i.assignee in people and span.contains(i.closed_on)
    ]
    intervals = build_intervals(readings, closed, span, board.since)
    return Rates(person_rates(intervals), team_rate(intervals), fit_types(intervals))


@dataclass(frozen=True)
class IssueHours:
    issue: Issue
    low: float
    mode: float
    high: float
    basis: str


def hours_for(
    issue: Issue, name: str | None, estimates: dict[str, Estimate], rates: Rates
) -> IssueHours | None:
    """Hours for one issue: its own estimate, else the type model, else a rate.

    Returns None when there is no basis at all. perch does not invent a default
    hours-per-issue.
    """
    estimate = estimates.get(issue_key(issue.iid))
    if estimate is not None:
        return IssueHours(issue, estimate.low, estimate.hours, estimate.high, ESTIMATES)
    own = rates.people.get(name)
    if rates.types is not None:
        mode = rates.types.hours(name, issue.type)
        # The model gives one number; the spread is the person's own observed
        # spread around their flat rate, applied proportionally.
        low, high = (own.low / own.mode, own.high / own.mode) if own else (1.0, 1.0)
        basis = f"{TYPE_MODEL} ({rates.types.intervals} intervals)"
        return IssueHours(issue, mode * low, mode, mode * high, basis)
    rate = own or rates.team
    if rate is None:
        return None
    basis = f"{rate.basis} ({rate.samples} samples)"
    return IssueHours(issue, rate.low, rate.mode, rate.high, basis)


@dataclass(frozen=True)
class PersonRow:
    name: str
    open: int
    low: float
    mode: float
    high: float
    hourly_cost: float | None
    left: float | None
    bases: tuple[str, ...]
    no_basis: int

    @property
    def cost(self) -> float | None:
        return None if self.hourly_cost is None else self.mode * self.hourly_cost

    @property
    def gap(self) -> float | None:
        """Planned hours left after the open board. Negative: it does not fit."""
        return None if self.left is None else self.left - self.mode


def person_rows(
    board: Board,
    estimates: dict[str, Estimate],
    rates: Rates,
    people: dict[str, str],
    money: Money,
) -> list[PersonRow]:
    """One row per mapped person with open issues, then unassigned and unmapped."""
    groups: dict[str, list[Issue]] = {}
    for issue in board.open:
        if issue.assignee is None:
            who = UNASSIGNED
        else:
            who = people.get(issue.assignee, UNMAPPED)
        groups.setdefault(who, []).append(issue)

    costs = list(money.hourly_cost.values())
    blended = sum(costs) / len(costs) if costs else None
    order = sorted(n for n in groups if n not in (UNASSIGNED, UNMAPPED))
    order += [n for n in (UNASSIGNED, UNMAPPED) if n in groups]

    rows = []
    for who in order:
        named = who not in (UNASSIGNED, UNMAPPED)
        found = [
            hours_for(i, who if named else None, estimates, rates) for i in groups[who]
        ]
        known = [h for h in found if h is not None]
        rows.append(
            PersonRow(
                name=who,
                open=len(found),
                low=sum(h.low for h in known),
                mode=sum(h.mode for h in known),
                high=sum(h.high for h in known),
                hourly_cost=money.hourly_cost.get(who) if named else blended,
                left=money.left.get(who) if named else None,
                bases=tuple(dict.fromkeys(h.basis for h in known)),
                no_basis=len(found) - len(known),
            )
        )
    return rows


@dataclass(frozen=True)
class Rollup:
    as_of: date | None
    spent_cost: float
    clear_p10: float
    clear_p50: float
    clear_p90: float
    non_labor: float
    budget: float | None
    signal: SignalResult | None

    @property
    def budget_left(self) -> float | None:
        if self.budget is None:
            return None
        return self.budget - self.spent_cost - self.non_labor

    @property
    def headroom(self) -> float | None:
        left = self.budget_left
        return None if left is None else left - self.clear_p50


def rollup(
    rows: list[PersonRow],
    money: Money,
    iterations: int | None = None,
    seed: int | None = None,
) -> Rollup:
    """Cost to clear the board, simulated and signalled by Budgie's own engine."""
    team = [
        Person(r.name, r.hourly_cost, HoursEstimate(r.low, r.mode, r.high))
        for r in rows
        if r.mode > 0 and r.hourly_cost
    ]
    sim = None
    if team:
        sim = simulate(
            team,
            iterations=iterations or money.iterations,
            seed=money.seed if seed is None else seed,
        )
    p10, p50, p90 = (sim.percentile(p) for p in (10, 50, 90)) if sim else (0.0,) * 3
    result = Rollup(
        as_of=money.as_of,
        spent_cost=money.spent_cost,
        clear_p10=p10,
        clear_p50=p50,
        clear_p90=p90,
        non_labor=money.non_labor,
        budget=money.budget,
        signal=None,
    )
    if sim is None or result.budget_left is None:
        return result
    # The board is tested against what is left for it, not the whole budget:
    # spend to date and planned non-labor are already committed.
    signal = evaluate(sim, result.budget_left)
    return Rollup(**{**result.__dict__, "signal": signal})


def notes(board: Board, rows: list[PersonRow], people: dict[str, str], money: Money):
    """Everything the lead should know about how far to trust this run."""
    out = []
    unmapped = sorted(
        {i.assignee for i in board.issues if i.assignee and i.assignee not in people}
    )
    if unmapped:
        out.append(
            "No entry under `people:` in perch.yaml for: " + ", ".join(unmapped) + "."
        )
    strangers = sorted(set(people.values()) - set(money.hourly_cost))
    if strangers:
        out.append("Not in Budgie's people.csv, so uncosted: " + ", ".join(strangers))
    missing = sum(r.no_basis for r in rows)
    if missing:
        out.append(
            f"{missing} open issue(s) have no estimate and no rate to fall back on; "
            "they are left out of the totals."
        )
    if money.as_of and abs((board.fetched_on - money.as_of).days) > STALE_DAYS:
        out.append(
            f"The board was fetched {board.fetched_on} but the latest hours reading "
            f"is {money.as_of}: the two sides describe different moments."
        )
    return out
