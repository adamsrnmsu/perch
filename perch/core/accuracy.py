"""How estimates compared with what the work took.

Two tables, and the difference between them matters. By label is *modelled*:
nobody books hours per issue, so an epic's hours are each closer's rate summed.
By person is *measured*: the hours a person booked against the estimates on
the issues they closed.
"""

from __future__ import annotations

from dataclasses import dataclass

from perch.core.board import Board
from perch.core.estimates import Estimate, issue_key
from perch.core.join import Rates, hours_for
from perch.core.money import Money
from perch.core.rate import window

MIN_COVERAGE = 0.5


@dataclass(frozen=True)
class LabelAccuracy:
    label: str
    issues: int
    open: int
    estimated: float
    modelled: float
    dollars: float  # modelled minus estimated, at the blended cost of who did it

    @property
    def ratio(self) -> float | None:
        return self.modelled / self.estimated if self.estimated else None


def by_label(
    estimates: dict[str, Estimate],
    board: Board,
    rates: Rates,
    people: dict[str, str],
    money: Money,
) -> list[LabelAccuracy]:
    out = []
    for estimate in estimates.values():
        if estimate.is_issue:
            continue
        issues = [i for i in board.issues if estimate.key in i.labels]
        hours = cost = 0.0
        for issue in issues:
            name = people.get(issue.assignee)
            # Rates only: comparing an estimate with another estimate is circular.
            found = hours_for(issue, name, {}, rates)
            if found is None:
                continue
            hours += found.mode
            cost += found.mode * money.hourly_cost.get(name, 0.0)
        blended = cost / hours if hours else 0.0
        out.append(
            LabelAccuracy(
                label=estimate.key,
                issues=len(issues),
                open=sum(1 for i in issues if i.is_open),
                estimated=estimate.hours,
                modelled=hours,
                dollars=(hours - estimate.hours) * blended,
            )
        )
    return out


@dataclass(frozen=True)
class PersonAccuracy:
    name: str
    closed: int
    covered: int  # closed issues that had their own estimate
    booked: float  # from where the dump's history starts (see rate.window)
    estimated: float

    @property
    def coverage(self) -> float:
        return self.covered / self.closed if self.closed else 0.0

    @property
    def ratio(self) -> float | None:
        """Booked over estimated, on the covered share of the work.

        None below 50% coverage: a ratio over a minority of someone's work says
        nothing about them.
        """
        if self.coverage < MIN_COVERAGE or not self.estimated:
            return None
        return self.booked * self.coverage / self.estimated


def by_person(
    estimates: dict[str, Estimate], board: Board, people: dict[str, str], money: Money
) -> list[PersonAccuracy]:
    out = []
    for name, series in sorted(money.readings.items()):
        start, before = window(series, money.span, board.since)
        through, booked = series[-1]
        closed = [
            i
            for i in board.closed
            if people.get(i.assignee) == name and start <= i.closed_on <= through
        ]
        covered = [estimates[k] for i in closed if (k := issue_key(i.iid)) in estimates]
        out.append(
            PersonAccuracy(
                name=name,
                closed=len(closed),
                covered=len(covered),
                booked=booked - before,
                estimated=sum(e.hours for e in covered),
            )
        )
    return out
