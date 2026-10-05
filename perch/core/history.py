"""history.jsonl: one run per week, kept so that trends have somewhere to start.

`perch board` writes it; `perch weekly` reads it. Quarterly will too.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from perch.core.accuracy import PersonAccuracy
from perch.core.join import PersonRow, Rates, Rollup


def week_key(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def rows_for(
    people: list[PersonRow],
    rates: Rates,
    rollup: Rollup,
    accuracy: list[PersonAccuracy] = (),
    left: float | None = None,
    quarter: dict | None = None,
) -> list[dict]:
    """This run's rows; `left` is the team's planned hours left (for `perch cut`),
    `quarter` the quarter so far's `pace` and `net_scope`
    (`quarterly.quarter_to_date`)."""
    quarter = quarter or {}
    out: list[dict] = [
        {
            "kind": "person",
            "name": r.name,
            "open": r.open,
            "hours": r.mode,
            "cost": r.cost,
            "left": r.left,
            "gap": r.gap,
            "rate": rates.people[r.name].mode if r.name in rates.people else None,
            "factor": rates.types.factors.get(r.name) if rates.types else None,
        }
        for r in people
    ]
    if rates.types:
        out += [
            {"kind": "type", "name": column, "rate": rate}
            for column, rate in rates.types.rates.items()
        ]
    out += [
        {
            "kind": "accuracy",
            "name": a.name,
            "coverage": a.coverage,
            "ratio": a.ratio,
        }
        for a in accuracy
    ]
    out.append(
        {
            "kind": "team",
            "name": "team",
            "spent_cost": rollup.spent_cost,
            "clear_p10": rollup.clear_p10,
            "clear_p50": rollup.clear_p50,
            "clear_p90": rollup.clear_p90,
            "headroom": rollup.headroom,
            "prob_over": rollup.signal.prob_over_budget if rollup.signal else None,
            "budget": rollup.budget,
            "left": left,
            "signal": rollup.signal.label if rollup.signal else None,
            "pace": quarter.get("pace"),
            "net_scope": quarter.get("net_scope"),
        }
    )
    return out


def record(path: str | Path, day: date, rows: list[dict]) -> None:
    """Write this week's rows, replacing any the same week already has."""
    path = Path(path)
    week = week_key(day)
    kept = []
    if path.is_file():
        kept = [
            line
            for line in path.read_text().splitlines()
            if line.strip() and json.loads(line).get("week") != week
        ]
    fresh = [json.dumps({"week": week, "date": day.isoformat(), **row}) for row in rows]
    path.write_text("\n".join(kept + fresh) + "\n")


def load(path: str | Path) -> list[dict]:
    """Every recorded row; a missing file is an empty history."""
    path = Path(path)
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def latest_week(path: str | Path) -> list[dict]:
    """The rows of the last week recorded; empty when nothing is."""
    rows = load(path)
    last = max((r["week"] for r in rows), default=None)
    return [r for r in rows if r["week"] == last]


def figures(rows: list[dict], kind: str, name: str, key: str) -> dict[str, float]:
    """One recorded figure by week (e.g. Alice's accuracy `ratio`); weeks
    without it are left out."""
    return {
        r["week"]: r[key]
        for r in rows
        if r["kind"] == kind and r["name"] == name and r.get(key) is not None
    }
