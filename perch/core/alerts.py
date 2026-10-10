"""Alert rules: the lead's own thresholds over the recorded team rows.

`alerts:` in config.yaml, each `when: FIGURE OP NUMBER` and an optional
`project`. Pure over history rows: team level, read only, nothing sent, no
ranking. A missing figure is "no data" (`true=None`), never false.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from operator import eq, ge, gt, le, lt, ne

from perch.core import blocks as _blocks
from perch.core.history import week_key
from perch.core.trend import money, share

FIGURES = (
    "headroom",
    "budget",
    "spent_cost",
    "left",
    "prob_over",
    "pace",
    "net_scope",
    "clear_p10",
    "clear_p50",
    "clear_p90",
)
OPS = {"<": lt, "<=": le, ">": gt, ">=": ge, "==": eq, "!=": ne}
_SHARES = ("pace", "prob_over")
_KEYS = {"when", "project"}
_WHEN = re.compile(r"\s*(\w+)\s*(<=|>=|==|!=|<|>)\s*(\S+)\s*")
_NUM = re.compile(r"(-?)\$?(-?)([\d,]*\.?\d+)([km]?)(%?)", re.IGNORECASE)


@dataclass(frozen=True)
class Rule:
    index: int
    text: str
    figure: str
    op: str
    value: float
    project: str | None


@dataclass(frozen=True)
class State:
    rule: Rule
    project: str
    week: str | None
    figure: float | None
    true: bool | None
    fresh: bool


def _number(text: str) -> tuple[float, bool] | None:
    """(value, had a %) or None when it is not a number."""
    m = _NUM.fullmatch(text)
    if not m:
        return None
    sign, sign2, digits, unit, pct = m.groups()
    try:
        value = float(digits.replace(",", ""))
    except ValueError:
        return None
    value *= {"": 1, "k": 1e3, "m": 1e6}[unit.lower()]
    if pct:
        value /= 100
    return (-value if sign or sign2 else value), bool(pct)


def parse(
    data: object, projects: Sequence[str], source: str = "config.yaml"
) -> tuple[Rule, ...]:
    """The rules of an `alerts:` value; every error names the key."""
    if data is None:
        return ()
    if not isinstance(data, list):
        raise ValueError(f"{source}: `alerts` must be a list")  # noqa: TRY004
    rules = []
    for i, item in enumerate(data):
        key = f"{source}: `alerts[{i}]"
        if not isinstance(item, dict):
            raise ValueError(f"{key}` must be a mapping with `when`")  # noqa: TRY004
        if set(item) - _KEYS:
            raise ValueError(
                f"{key}`: unknown keys {sorted(set(item) - _KEYS)}; expected {sorted(_KEYS)}"
            )
        text = item.get("when")
        m = _WHEN.fullmatch(text) if isinstance(text, str) else None
        if not m or m[1] not in FIGURES:
            raise ValueError(
                f"{key}.when` must be FIGURE OP NUMBER, like `headroom < 50k`; "
                f"figures: {', '.join(FIGURES)}; ops: {', '.join(OPS)}"
            )
        got = _number(m[3])
        if got is None:
            raise ValueError(f"{key}.when`: {m[3]!r} is not a number")
        value, pct = got
        if m[1] in _SHARES and not pct and abs(value) > 1:
            raise ValueError(
                f"{key}.when`: {m[1]} is a share; write {m[3]}% (or a value of 1 or less)"
            )
        project = item.get("project", "ALL")
        if not isinstance(project, str) or (
            project != "ALL" and project not in projects
        ):
            known = ", ".join(projects) or "none yet"
            raise ValueError(
                f"{key}.project` {project!r} is not ALL or a project. Known: {known}"
            )
        rules.append(
            Rule(
                i,
                " ".join(text.split()),
                m[1],
                m[2],
                value,
                None if project == "ALL" else project,
            )
        )
    return tuple(rules)


def evaluate(
    rules: Sequence[Rule], name: str, rows: list[dict], today: date | None = None
) -> list[State]:
    """One State per rule that covers `name`, from the team rows of history."""
    team = sorted((r for r in rows if r["kind"] == "team"), key=lambda r: r["week"])
    team = list({r["week"]: r for r in team}.values())
    last = team[-1] if team else None
    prev = team[-2] if len(team) > 1 else None
    recent = (
        True
        if today is None
        else last is not None
        and last["week"] in (week_key(today), week_key(today - timedelta(days=7)))
    )
    out = []
    for rule in rules:
        if rule.project not in (None, name):
            continue
        op = OPS[rule.op]

        def test(row, rule=rule, op=op):
            got = None if row is None else row.get(rule.figure)
            return got, None if got is None else op(got, rule.value)

        figure, now = test(last)
        _, before = test(prev)
        fresh = bool(now) and prev is not None and before is not True and recent
        out.append(State(rule, name, last and last["week"], figure, now, fresh))
    return out


def _fmt(figure: str, value: float | None) -> str:
    if value is None:
        return "—"
    if figure in _SHARES:
        return share(value)
    return f"{value:g}" if figure == "net_scope" else money(value)


def _week(week: str | None) -> str:
    return "—" if week is None else week.split("-")[-1]


def toast_text(s: State) -> str:
    """`apollo: headroom < 50k (headroom $42,000, W40)`."""
    return (
        f"{s.project}: {s.rule.text} "
        f"({s.rule.figure} {_fmt(s.rule.figure, s.figure)}, {_week(s.week)})"
    )


def _state(s: State) -> str:
    return "no data" if s.true is None else str(s.true).lower()


def lines(states: Sequence[State]) -> list[str]:
    """One line per rule and project: its state and the figure."""
    return [
        f"{s.project}: {s.rule.text}: {_state(s)} "
        f"({s.rule.figure} {_fmt(s.rule.figure, s.figure)}, {_week(s.week)})"
        for s in states
    ]


def blocks(states: Sequence[State]) -> list[dict]:
    if not states:
        return [_blocks.text("no alert rules in config.yaml", tone="dim")]
    rows = [
        [
            s.project,
            s.rule.text,
            _state(s),
            _fmt(s.rule.figure, s.figure),
            _week(s.week),
        ]
        for s in states
    ]
    return [
        _blocks.table(
            ["project", "rule", "state", "figure", "week"],
            rows,
            title="Alerts",
            align=["l", "l", "l", "r", "l"],
        )
    ]
