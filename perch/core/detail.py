"""The detail pane's data: the headroom history, Budgie's burn series, the
freshness of each input. Read only, team level, no new arithmetic; every
dollar on the chart comes from Budgie's burn_series through Money.burn.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from perch.core import blocks as bk
from perch.core.sources import Sources, unreadable
from perch.core.trend import money, series, share, spark

if TYPE_CHECKING:  # typing only: money.py is where perch imports budgie.core
    from budgie.core.burn import BurnSeries


@dataclass(frozen=True)
class Detail:
    project: str
    headroom: dict[str, float]  # week -> headroom, every recorded week
    burn: BurnSeries | None
    as_of: date | None
    dump_on: date | None
    history_week: str | None
    pace: float | None
    net_scope: int | None
    non_labor: float
    note: str  # "" or why a part is missing; fixed strings only


def build(project: str, src: Sources) -> Detail:
    m = src.money
    notes = [unreadable(s) for s in src.errors]
    burn = None
    if m is not None and m.burn is not None:
        try:
            burn = m.burn()
        except Exception:  # noqa: BLE001 -- a display boundary: say so, never crash
            notes.append("fan unavailable, run perch doctor")
        else:
            if burn.note:
                notes.append(burn.note)
    if src.config is not None and src.board is None:
        notes.append("no board dump yet: run perch fetch")
    team = sorted((r for r in src.rows if r["kind"] == "team"), key=lambda r: r["week"])
    last = team[-1] if team else {}
    return Detail(
        project=project,
        headroom=series(src.rows, "headroom", window=10_000),
        burn=burn,
        as_of=m.as_of if m else None,
        dump_on=src.board.fetched_on if src.board else None,
        history_week=max((r["week"] for r in src.rows), default=None),
        pace=last.get("pace"),
        net_scope=last.get("net_scope"),
        non_labor=m.non_labor if m else 0.0,
        note="; ".join(notes),
    )


def spark_line(d: Detail, upto: str | None = None) -> str:
    values = [v for w, v in d.headroom.items() if upto is None or w <= upto]
    if not values:
        return "no weeks recorded yet"
    if len(values) == 1:
        return "1 week recorded, need 2 for a trend"
    return (
        f"headroom {spark(values)}  {money(min(values))}–{money(max(values))}"
        f"  {len(values)} weeks"
    )


def _scope(d: Detail) -> str:
    return "—" if d.net_scope is None else f"{d.net_scope:+d}"


def lines(d: Detail, upto: str | None = None) -> list[str]:
    """The pane's text, chart excluded (the TUI draws that from `d.burn`)."""
    out = [
        spark_line(d, upto),
        f"pace {share(d.pace)} · net scope {_scope(d)}",
        (
            f"readings through {d.as_of or '—'} · board dump {d.dump_on or '—'}"
            f" · history {d.history_week or '—'}"
        ),
        f"cost lines {money(d.non_labor)} (not in the chart)",
    ]
    if d.note:
        out.append(d.note)
    return out


def _at(values: tuple, i: int) -> str:
    return money(values[i]) if values else "—"


def blocks(d: Detail) -> list[dict]:
    out = [
        bk.heading(f"Detail · {d.project}"),
        bk.text(spark_line(d), tone="dim"),
        bk.figures(
            [
                bk.figure("readings through", str(d.as_of or "—")),
                bk.figure("board dump", str(d.dump_on or "—")),
                bk.figure("history week", d.history_week or "—"),
                bk.figure("pace", share(d.pace)),
                bk.figure("net scope", _scope(d)),
                bk.figure("cost lines", money(d.non_labor), note="not in the table"),
            ]
        ),
    ]
    b = d.burn
    if b is not None and b.months:
        rows = [
            [
                month.strftime("%Y-%m"),
                _at(b.spent, i),
                _at(b.plan, i),
                _at(b.budget, i),
                _at(b.p10, i),
                _at(b.p50, i),
                _at(b.p90, i),
            ]
            for i, month in enumerate(b.months)
        ]
        out.append(
            bk.text("Labor only · cost lines excluded", tone="dim")
        )  # md drops table titles
        out.append(
            bk.table(
                ["month", "spent", "plan", "budget", "P10", "P50", "P90"],
                rows,
                align=["l"] + ["r"] * 6,
            )
        )
    if d.note:
        out.append(bk.text(d.note, tone="warn"))
    return out
