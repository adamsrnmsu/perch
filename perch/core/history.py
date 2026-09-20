"""history.jsonl: one run per week, kept so that trends have somewhere to start.

Nothing in v1 reads this file. The weekly and quarterly feedback will.
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
) -> list[dict]:
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
