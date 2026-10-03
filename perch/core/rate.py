"""Calibrated hours-per-issue rates from weekly readings and closed issues."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
from budgie.core.calendar import YearSpan

OTHER = "other"
MIN_TYPE_ISSUES = 5
MIN_SAMPLES_FOR_SPREAD = 3

# (person name, date closed, issue type)
Closed = tuple[str, date, str]
# (reading date, cumulative hours through that date)
Reading = tuple[date, float]


@dataclass(frozen=True)
class Interval:
    """One person's hours between two readings, and what they closed in it."""

    name: str
    start: date
    end: date
    hours: float
    closed: dict[str, int] = field(default_factory=dict)  # issue type -> count

    @property
    def issues(self) -> int:
        return sum(self.closed.values())


@dataclass(frozen=True)
class Rate:
    """Hours per issue, as a three-point figure."""

    low: float
    mode: float
    high: float
    samples: int
    basis: str


def window(series: list[Reading], span: YearSpan, since: date | None) -> Reading:
    """Where a person's measurable work opens: (first day, hours booked before it).

    The year's first day with nothing booked, unless the board dump's history starts
    later. Then it is the day after the first reading that leaves no gap
    before ``since``: hours booked before that were spent on issues the dump
    cannot see, so they would inflate hours per issue. ``since`` None (dumps
    from before gitboard wrote it) means no clip.
    """
    start, booked = span.first, 0.0
    for when, cumulative in sorted(series):
        if since is None or start >= since:
            break
        start, booked = when + timedelta(days=1), cumulative
    return start, booked


def build_intervals(
    readings: dict[str, list[Reading]],
    closed: list[Closed],
    span: YearSpan,
    since: date | None = None,
) -> list[Interval]:
    """Cut each person's year into reading-to-reading intervals.

    The first interval opens where ``window`` says. An interval in which the
    person closed nothing is merged into the next one (its hours were still
    spent getting the next issues done); a trailing one is merged backwards.
    """
    out: list[Interval] = []
    for name, series in readings.items():
        series = sorted(series)
        start, previous = window(series, span, since)
        mine: list[Interval] = []
        for when, cumulative in series:
            if when < start:
                continue
            counts = Counter(
                kind
                for who, day, kind in closed
                if who == name and start <= day <= when
            )
            mine.append(
                Interval(name, start, when, cumulative - previous, dict(counts))
            )
            start, previous = when + timedelta(days=1), cumulative
        out.extend(_merge_empty(mine))
    return out


def _merge_empty(intervals: list[Interval]) -> list[Interval]:
    merged: list[Interval] = []
    carry: Interval | None = None
    for interval in intervals:
        if carry is not None:
            interval = Interval(
                interval.name,
                carry.start,
                interval.end,
                carry.hours + interval.hours,
                interval.closed,
            )
            carry = None
        if interval.issues == 0:
            carry = interval
        else:
            merged.append(interval)
    if carry is not None and merged:
        last = merged[-1]
        merged[-1] = Interval(
            last.name, last.start, carry.end, last.hours + carry.hours, last.closed
        )
    return merged


def _rate(intervals: list[Interval], basis: str) -> Rate | None:
    issues = sum(i.issues for i in intervals)
    if issues == 0:
        return None
    mode = sum(i.hours for i in intervals) / issues
    samples = [i.hours / i.issues for i in intervals]
    if len(samples) >= MIN_SAMPLES_FOR_SPREAD:
        low, high = min(min(samples), mode), max(max(samples), mode)
    else:
        low = high = mode
    return Rate(low, mode, high, len(samples), basis)


def person_rates(intervals: list[Interval]) -> dict[str, Rate]:
    """Each person's own rate; people who closed nothing are left out."""
    names = dict.fromkeys(i.name for i in intervals)
    rates = {n: _rate([i for i in intervals if i.name == n], "own rate") for n in names}
    return {n: r for n, r in rates.items() if r is not None}


def team_rate(intervals: list[Interval]) -> Rate | None:
    """Everyone's hours over everyone's closed issues."""
    rate = _rate(intervals, "team rate")
    if rate is None:
        return None
    # The team figure is a fallback, not a distribution: samples from different
    # people are not draws of one quantity.
    return Rate(rate.mode, rate.mode, rate.mode, rate.samples, rate.basis)


@dataclass(frozen=True)
class TypeModel:
    """hours = factor(person) x sum(rate(column) x issues in that column).

    A *column* is an issue type with enough history to carry its own rate, or
    ``other``. ``columns`` maps every issue type seen to the column it was
    counted in; a type never seen before uses ``fallback``.
    """

    rates: dict[str, float]  # column -> team hours per issue
    factors: dict[str, float]  # person -> pace relative to the team (1.0)
    columns: dict[str, str]  # issue type -> column
    fallback: str
    intervals: int

    def column(self, issue_type: str) -> str:
        return self.columns.get(issue_type, self.fallback)

    def hours(self, name: str | None, issue_type: str) -> float:
        return self.factors.get(name, 1.0) * self.rates[self.column(issue_type)]


def fit_types(
    intervals: list[Interval], min_issues: int = MIN_TYPE_ISSUES
) -> TypeModel | None:
    """Fit team type rates and one pace factor per person.

    Types with fewer than ``min_issues`` closed issues share an ``other``
    column; if even that is under ``min_issues`` they are counted with the
    commonest type instead, because a column resting on a couple of issues
    fits noise. A column whose rate comes out negative is merged away and the
    fit is run again. Returns None when there are fewer intervals than
    ``columns + 2`` -- too little data to fit honestly.
    """
    totals: Counter[str] = Counter()
    for interval in intervals:
        totals.update(interval.closed)
    if not totals:
        return None

    columns = {t: (t if n >= min_issues else OTHER) for t, n in totals.items()}

    def size(column: str) -> int:
        return sum(n for t, n in totals.items() if columns[t] == column)

    def merge(source: str, target: str) -> None:
        for issue_type, column in columns.items():
            if column == source:
                columns[issue_type] = target

    def commonest(excluding: str) -> str:
        return max((c for c in set(columns.values()) if c != excluding), key=size)

    if 0 < size(OTHER) < min_issues and len(set(columns.values())) > 1:
        merge(OTHER, commonest(excluding=OTHER))

    while True:
        kinds = sorted(set(columns.values()))
        if len(intervals) < len(kinds) + 2:
            return None
        rates, factors = _alternate(intervals, kinds, columns)
        negative = [k for k in kinds if rates[k] < 0]
        if not negative:
            fallback = OTHER if OTHER in kinds else max(kinds, key=size)
            return TypeModel(rates, factors, dict(columns), fallback, len(intervals))
        if len(kinds) == 1:
            return None
        worst = min(negative, key=rates.get)
        target = OTHER if OTHER in kinds and worst != OTHER else commonest(worst)
        merge(worst, target)


def _alternate(
    intervals: list[Interval],
    kinds: list[str],
    columns: dict[str, str],
    rounds: int = 25,
) -> tuple[dict[str, float], dict[str, float]]:
    """Alternating least squares for rates and factors.

    Fitting the type rates once, as if everyone worked at the same pace, biases
    them towards whoever closed the most of each type. So: fit rates on hours
    divided by each person's factor, recompute the factors, repeat. Rates are
    rescaled each round so that a factor of 1.0 reproduces the team's total
    hours -- which is what an unassigned issue is costed at.
    """
    matrix = np.array(
        [[_count(i, k, columns) for k in kinds] for i in intervals], dtype=float
    )
    hours = np.array([i.hours for i in intervals], dtype=float)
    names = [i.name for i in intervals]
    factors = dict.fromkeys(names, 1.0)
    rates = np.zeros(len(kinds))
    for _ in range(rounds):
        pace = np.array([factors[n] for n in names])
        rates, *_ = np.linalg.lstsq(matrix, hours / pace, rcond=None)
        predicted = matrix @ rates
        if predicted.sum() <= 0:
            break
        rates = rates * (hours.sum() / predicted.sum())
        predicted = matrix @ rates
        for name in factors:
            mine = np.array([n == name for n in names])
            if predicted[mine].sum() > 0:
                factors[name] = float(hours[mine].sum() / predicted[mine].sum())
    return {k: float(r) for k, r in zip(kinds, rates)}, factors


def _count(interval: Interval, kind: str, columns: dict[str, str]) -> int:
    """Issues in the interval whose type is counted in column ``kind``."""
    return sum(n for t, n in interval.closed.items() if columns[t] == kind)
