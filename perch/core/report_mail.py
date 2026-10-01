"""A `Quarter` as markdown and as an Outlook draft (.eml). Nothing is sent.

Both come from one list of blocks (heading, paragraph, table), so the text part
and the HTML part of the draft always say the same thing. The HTML follows the
same Outlook rules as Budgie's emails: tables and inline styles only, since
Outlook renders HTML through Word.
"""

from __future__ import annotations

from email.message import EmailMessage
from html import escape

from perch.core.quarterly import NO_DUMP, Quarter

_FONT = "Arial, Helvetica, sans-serif"
_INK = "#16211c"
_MUTED = "#5d6b62"
_LINE = "#dde5df"


def _money(value: float | None) -> str:
    return "—" if value is None else f"${value:,.0f}"


def _delta(value: float) -> str:
    return f"{'-' if value < 0 else '+'}${abs(value):,.0f}"


def _hours(value: float | None) -> str:
    return "—" if value is None else f"{value:,.0f}"


def _count(value: int | None) -> str:
    return "—" if value is None else str(value)


def _span(a, b) -> str:
    return f"{a:%b} {a.day} – {b:%b} {b.day}"


def title(q: Quarter) -> str:
    when = f" to date (as of {q.as_of or q.through})" if q.to_date else ""
    return f"{q.project}, {q.name}{when}"


def subject(q: Quarter) -> str:
    p = q.position
    signal = p.signal.signal.name if p.signal else "no budget"
    return (
        f"{q.project}, {q.name}: {_money(p.spent_year)} spent of "
        f"{_money(p.budget_end)}; forecast at completion {_money(p.p50)} ({signal})"
    )


def _opening(q: Quarter) -> str:
    p = q.position
    reading = (
        f"the latest hours reading is {q.as_of}" if q.as_of else "no hours readings"
    )
    out = [f"{q.name} runs {_span(q.start, q.end)}; {reading}."]
    if p.spent_quarter is not None:
        out.append(
            f"{_money(p.spent_quarter)} was spent this quarter, "
            f"{_money(p.spent_year)} this year."
        )
    signal = f" ({p.signal.signal.name})" if p.signal else ""
    out.append(
        f"Forecast at completion {_money(p.p50)} against a "
        f"{_money(p.budget_end)} budget{signal}."
    )
    if q.misses:
        miss = sum(a.dollars for a in q.misses)
        out.append(
            f"Issues closed this quarter came in {_delta(miss)} against their "
            "label estimates (modelled)."
        )
    total = q.total
    if total.closed is not None:
        out.append(
            f"{total.closed} issues closed on {_hours(total.hours)} booked hours."
        )
    if q.blocked_days is not None:
        out.append(f"{q.blocked_days} issue-days were spent in Blocked.")
    if q.staffing:
        out.append(f"{len(q.staffing)} staffing change(s).")
    return " ".join(out)


def _blocks(q: Quarter) -> list[tuple]:
    """("h", text) | ("p", text) | ("table", left_columns, header, rows)."""
    p = q.position
    out: list[tuple] = [("p", _opening(q))]

    out.append(("h", "1. Budget position"))
    if q.hours_note:
        out.append(("p", q.hours_note))
    out.append(
        (
            "table",
            1,
            ("", "Amount"),
            [
                ("Spent this quarter", _money(p.spent_quarter)),
                ("Spent year to date", _money(p.spent_year)),
                (f"Budget on {q.start}", _money(p.budget_start)),
                (f"Budget on {q.end}", _money(p.budget_end)),
                ("Forecast at completion, P10", _money(p.p10)),
                ("Forecast at completion, P50", _money(p.p50)),
                ("Forecast at completion, P90", _money(p.p90)),
            ],
        )
    )
    if p.signal:
        out.append(("p", f"{p.signal.signal.name}: {p.signal.rationale}"))
    if p.flat:
        out.append(("p", "The budget is a flat number; no revisions."))
    elif p.revisions:
        rows = [(str(r.effective_date), r.note, _money(r.amount)) for r in p.revisions]
        out.append(("table", 2, ("Revised", "Note", "Amount"), rows))
    else:
        out.append(("p", "No budget revision is dated in the quarter."))

    out.append(("h", "2. Estimate misses ($), MODELLED"))
    if q.board_note:
        out.append(("p", q.board_note))
    if q.misses is None:
        if q.board_note != NO_DUMP:
            out.append(("p", "No `estimates:` in perch.yaml, so nothing to compare."))
    elif not q.misses:
        out.append(("p", "No issue closed this quarter carries an estimated label."))
    else:
        rows = [
            (
                a.label,
                str(a.issues),
                _hours(a.estimated),
                _hours(a.modelled),
                _delta(a.dollars),
            )
            for a in q.misses
        ]
        header = ("Label", "Closed", "Estimated h", "Modelled h", "Difference")
        out.append(("table", 1, header, rows))
        out.append(
            (
                "p",
                (
                    "Modelled, not measured: nobody books hours per issue, so an "
                    "issue's hours are its closer's rate. The estimate is the "
                    "label's whole estimate."
                ),
            )
        )

    out.append(("h", "3. Throughput"))
    for note in (q.hours_note, q.board_note):
        if note:
            out.append(("p", note))
    rows = [
        (
            w.label,
            _span(w.start, w.end),
            _count(w.closed),
            _hours(w.hours),
            _hours(w.per_issue),
        )
        for w in (*q.weeks, q.total)
    ]
    rows[-1] = ("Total", *rows[-1][1:])
    header = ("Week", "Dates", "Closed", "Hours booked", "Hours per issue")
    out.append(("table", 2, header, rows))
    out.append(("p", "Booked hours between two weekly readings are interpolated."))

    out.append(("h", "4. Waiting and staffing"))
    if q.board_note:
        out.append(("p", q.board_note))
    if q.blocked_days is not None:
        moved = "issue" if q.reopened == 1 else "issues"
        out.append(
            (
                "p",
                (
                    f"{q.blocked_days} issue-days in Blocked; {q.reopened} {moved} "
                    "moved back out of Done."
                ),
            )
        )
    if q.staffing:
        rows = [
            (
                str(s.day),
                s.name,
                s.kind,
                f"{s.fte_before:g} → {s.fte_after:g}",
                f"{s.hours:+,.0f}",
                "—" if s.dollars is None else _delta(s.dollars),
            )
            for s in q.staffing
        ]
        header = ("Date", "Who", "Change", "FTE", "Year's hours", "At their rate")
        out.append(("table", 3, header, rows))
    else:
        out.append(("p", "No staffing change is dated in the quarter."))
    return out


def render_md(q: Quarter) -> str:
    lines = [f"# {title(q)}", ""]
    for block in _blocks(q):
        if block[0] == "h":
            lines += [f"## {block[1]}", ""]
        elif block[0] == "p":
            lines += [block[1], ""]
        else:
            _, left, header, rows = block
            rule = ["---" if n < left else "---:" for n in range(len(header))]
            for row in (header, rule, *rows):
                lines.append("| " + " | ".join(row) + " |")
            lines.append("")
    return "\n".join(lines)


def _html_table(left: int, header, rows) -> str:
    def cell(tag, text, n, weight):
        align = "left" if n < left else "right"
        return (
            f'<{tag} align="{align}" style="padding:5px 8px;border-bottom:1px solid '
            f"{_LINE};font-family:{_FONT};font-size:13px;color:{_INK};"
            f'font-weight:{weight};">{escape(text)}</{tag}>'
        )

    head = "".join(cell("th", h, n, "bold") for n, h in enumerate(header))
    body = "".join(
        "<tr>" + "".join(cell("td", c, n, "normal") for n, c in enumerate(r)) + "</tr>"
        for r in rows
    )
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'style="border-collapse:collapse;"><tr>{head}</tr>{body}</table>'
    )


def render_html(q: Quarter) -> str:
    parts = [
        (
            f'<div style="font-family:{_FONT};font-size:20px;font-weight:bold;'
            f'color:{_INK};padding-bottom:8px;">{escape(title(q))}</div>'
        )
    ]
    for block in _blocks(q):
        if block[0] == "h":
            parts.append(
                f'<div style="font-family:{_FONT};font-size:16px;font-weight:bold;'
                f'color:{_INK};padding:18px 0 6px 0;">{escape(block[1])}</div>'
            )
        elif block[0] == "p":
            parts.append(
                f'<div style="font-family:{_FONT};font-size:14px;color:{_MUTED};'
                f'line-height:1.5;padding:4px 0;">{escape(block[1])}</div>'
            )
        else:
            parts.append(_html_table(*block[1:]))
    return (
        '<html><body style="margin:0;padding:0;background:#ffffff;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'border="0"><tr><td style="padding:20px 24px;">'
        + "\n".join(parts)
        + "</td></tr></table></body></html>"
    )


def render_eml(q: Quarter) -> EmailMessage:
    """A draft: text part (the markdown) and HTML part; X-Unsent opens it unsent."""
    msg = EmailMessage()
    msg["Subject"] = subject(q)
    msg["X-Unsent"] = "1"
    msg.set_content(render_md(q))
    msg.add_alternative(render_html(q), subtype="html")
    return msg
