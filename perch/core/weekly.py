"""`perch weekly`: one markdown block per person, from this run plus history.

Draft text for gitboard's digest or Budgie's per-person mail to carry. Pure
logic: no click, no rich, and nothing is written or sent. A trend is only shown
with MIN_WEEKS of the person's own earlier weeks behind it; below that the
block says how many it has instead.
"""

from __future__ import annotations

from statistics import mean

from perch.core import blocks
from perch.core.accuracy import MIN_COVERAGE, PersonAccuracy
from perch.core.board import Board
from perch.core.history import figures, week_key
from perch.core.join import PersonRow, Rates
from perch.core.money import Money

WINDOW = 8  # trailing weeks compared against
MIN_WEEKS = 4  # fewer than this and no comparison is made
FLAT = 0.10  # within 10% of the baseline reads "in line"


def _h(value: float) -> str:
    return f"{value:,.0f}"


def _rate(value: float) -> str:
    return f"{round(value * 2) / 2:g}"


def _thin(n: int) -> str:
    return f"not enough history: {n} of {WINDOW} weeks"


def _prior_weeks(rows: list[dict], week: str) -> list[str]:
    """The (up to) WINDOW weeks before this one. ISO week keys sort as text."""
    return sorted({r["week"] for r in rows if r["week"] < week})[-WINDOW:]


def _type_hours(
    rows: list[dict], weeks: list[str], name: str, column: str
) -> list[float]:
    """The person's modelled hours per issue of a column, in each prior week."""
    found = {(r["week"], r["kind"], r["name"]): r for r in rows}
    out = []
    for w in weeks:
        person, kind = found.get((w, "person", name)), found.get((w, "type", column))
        if person and kind and person.get("factor") is not None:
            out.append(person["factor"] * kind["rate"])
    return out


def _open_line(row: PersonRow | None, left: float | None) -> str:
    if row is None:
        mode, count = 0.0, 0
    else:
        mode, count = row.mode, row.open
    line = f"- **Open board:** {count} issue(s), about {_h(mode)} h"
    if left is None:
        return line + ". No planned hours in Budgie."
    return line + f". Planned hours left: {_h(left)}. Gap: {_h(left - mode)} h."


def _types(name: str, rates: Rates, rows: list[dict], weeks: list[str]) -> list[str]:
    if rates.types is None:
        return [
            "- **Hours per issue by type:** not enough history to fit type rates yet."
        ]
    out = [
        f"- **Hours per issue by type** (modelled, against your own trailing {WINDOW} weeks):"
    ]
    factor = rates.types.factors.get(name, 1.0)
    for column, rate in sorted(rates.types.rates.items()):
        before = _type_hours(rows, weeks, name, column)
        base = (
            _rate(mean(before)) + f" h ({len(before)} weeks)"
            if (len(before) >= MIN_WEEKS)
            else _thin(len(before))
        )
        out.append(f"  - {column}: {_rate(factor * rate)} h now; {base}")
    return out


def _accuracy(
    acc: PersonAccuracy | None, rows: list[dict], weeks: list[str], name: str
) -> str:
    head = "- **Estimate accuracy** (measured, booked over estimated hours): "
    if acc is None:
        return head + "no hours readings for you, so nothing to measure."
    if acc.ratio is None:
        return head + (
            f"withheld: {acc.covered} of {acc.closed} closed issues had an "
            f"estimate, under the {MIN_COVERAGE:.0%} needed."
        )
    ratios = figures(rows, "accuracy", name, "ratio")
    before = [ratios[w] for w in weeks if w in ratios]
    now = f"{acc.ratio:.2f}x now"
    if len(before) < MIN_WEEKS:
        return head + f"{now}; {_thin(len(before))}."
    base = mean(before)
    drift = acc.ratio / base - 1
    way = "in line with" if abs(drift) <= FLAT else "above" if drift > 0 else "below"
    return head + f"{now}, {way} your {base:.2f}x over {len(before)} weeks."


def _plain(line: str) -> str:
    """A markdown bullet line as a list item: no `- `, no bold."""
    return line.replace("**", "").replace("- ", "", 1)


def _waiting(name: str, board: Board, people: dict[str, str]) -> list[str]:
    mine = [i for i in board.open if i.is_waiting and people.get(i.assignee) == name]
    if not mine:
        return ["- **Waiting on someone else:** nothing in Blocked or asked as `Q:`."]
    out = ["- **Waiting on someone else** (in Blocked, or an unanswered `Q:` note):"]
    # blocked longest first, then the question-only issues by number
    for i in sorted(
        mine,
        key=lambda i: (not i.is_blocked, i.blocked_since or board.fetched_on, i.iid),
    ):
        parts = []
        if i.is_blocked:
            parts.append(
                f"{(board.fetched_on - i.blocked_since).days} days"
                if i.blocked_since
                else "unknown time"
            )
        parts += [f'asked "{q}"' for q in i.questions]
        out.append(f"  - #{i.iid} {i.title}: {'; '.join(parts)}")
    return out


def weekly_blocks(
    board: Board,
    money: Money,
    rates: Rates,
    rows: list[PersonRow],
    accuracy: list[PersonAccuracy],
    estimates_given: bool,
    people: dict[str, str],
    history: list[dict],
    only: str | None = None,
) -> list[dict]:
    names = sorted(set(people.values()))
    if only is not None:
        if only not in names:
            raise ValueError(f"{only!r} is not in `people:`; have {', '.join(names)}")
        names = [only]
    week = week_key(board.fetched_on)
    weeks = _prior_weeks(history, week)
    by_row = {r.name: r for r in rows}
    by_acc = {a.name: a for a in accuracy}
    out = [
        blocks.heading(f"Weekly, {board.project} {board.name}, {week}", 1),
        blocks.text(
            f"Draft from the board fetched {board.fetched_on}. Not sent.", tone="dim"
        ),
    ]
    for name in names:
        lines = [_open_line(by_row.get(name), money.left.get(name))]
        lines += _types(name, rates, history, weeks)
        lines.append(
            _accuracy(by_acc.get(name), history, weeks, name)
            if estimates_given
            else "- **Estimate accuracy:** no `estimates:` file, so nothing to compare."
        )
        lines += _waiting(name, board, people)
        out += [
            blocks.heading(name, 2),
            # items: the same lines without markup; a sub-item keeps two spaces
            {
                **blocks.bullets([_plain(line) for line in lines]),
                "md": "\n".join(lines),
            },
        ]
    return out


def weekly(*args, **kwargs) -> str:
    return blocks.to_md(weekly_blocks(*args, **kwargs))
