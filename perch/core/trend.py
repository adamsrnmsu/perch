"""Trend: read-only arithmetic over the team rows of history.jsonl.

Nothing here runs a simulation, reads a person row or ranks anyone; every
figure is a recorded figure or the difference of two recorded figures.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from perch.core.history import figures

WINDOW = 8  # weeks, as `perch weekly` counts them
BARS = "▁▂▃▄▅▆▇█"
_DELTAS = (("headroom", "headroom"), ("budget", "budget"), ("spent_cost", "spent"))


def spark(values: Sequence[float]) -> str:
    """One bar per value, scaled min to max; flat is all mid bars."""
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    if lo == hi:
        return BARS[3] * len(values)
    return "".join(BARS[round((v - lo) / (hi - lo) * (len(BARS) - 1))] for v in values)


def series(rows: list[dict], key: str, window: int = WINDOW) -> dict[str, float]:
    """The team's `key` by week, oldest first, the last `window` weeks."""
    got = figures(rows, "team", "team", key)
    return {week: got[week] for week in sorted(got)[-window:]}


@dataclass(frozen=True)
class Change:
    before: str  # week key, e.g. "2026-W39"
    after: str
    signal: tuple[str, str] | None  # (old, new) when it flipped
    deltas: dict[str, float]  # key -> after - before, nonzero only


def change(rows: list[dict]) -> Change | None:
    """The team row of the last two recorded weeks; None when fewer than two."""
    weeks = sorted({r["week"]: r for r in rows if r["kind"] == "team"}.items())
    if len(weeks) < 2:
        return None
    (before, old), (after, new) = weeks[-2:]
    flip = (old.get("signal"), new.get("signal"))
    deltas = {
        key: new[key] - old[key]
        for key, _ in _DELTAS
        if old.get(key) is not None
        and new.get(key) is not None
        and abs(new[key] - old[key]) >= 0.5
    }
    return Change(
        before, after, flip if all(flip) and flip[0] != flip[1] else None, deltas
    )


def _money(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "—"
    sign = ("+" if signed else "") if value >= 0 else "−"
    return f"{sign}${abs(value):,.0f}"


def describe(name: str, change: Change | None) -> str:
    """`apollo W39→W40: YELLOW→RED, headroom −$12,000`; "" when nothing changed."""
    if change is None:
        return ""
    parts = ["→".join(s.upper() for s in change.signal)] if change.signal else []
    parts += [
        f"{label} {_money(change.deltas[key], signed=True)}"
        for key, label in _DELTAS
        if key in change.deltas
    ]
    if not parts:
        return ""
    return f"{name} {change.before[5:]}→{change.after[5:]}: " + ", ".join(parts)


def team_lines(rows: list[dict]) -> list[str]:
    """The drill text: the latest week's figures, then headroom by week."""
    team = sorted((r for r in rows if r["kind"] == "team"), key=lambda r: r["week"])
    if not team:
        return ["no week recorded yet: run perch board"]
    last = team[-1]
    prob = last.get("prob_over")
    left = last.get("left")
    clear = " / ".join(
        _money(last.get(k)) for k in ("clear_p10", "clear_p50", "clear_p90")
    )
    head = (
        f"{(last.get('signal') or '—').upper()}"
        f" · over {'—' if prob is None else f'{prob:.0%}'}"
        f" · budget {_money(last.get('budget'))}"
        f" · spent {_money(last.get('spent_cost'))}"
        f" · headroom {_money(last.get('headroom'))}"
        f" · left {'—' if left is None else f'{left:,.0f}h'}"
        f" · clear {clear}"
    )
    signals = {r["week"]: (r.get("signal") or "—").upper() for r in team}
    return [head] + [
        f"{week}  {_money(value)}  {signals[week]}"
        for week, value in series(rows, "headroom").items()
    ]
