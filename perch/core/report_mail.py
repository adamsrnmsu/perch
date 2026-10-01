"""A `Quarter` as markdown and as an Outlook draft (.eml). Nothing is sent.

Both come from one list of blocks (heading, paragraph, table), so the text part
and the HTML part of the draft always say the same thing. The HTML follows the
same Outlook rules as Budgie's emails: tables and inline styles only, since
Outlook renders HTML through Word.
"""

from __future__ import annotations

from datetime import date
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


def _signal(q: Quarter) -> str:
    """Budgie's own word for the signal: GOOD, CAUTION, BAD or NO CHANGE."""
    return q.position.signal.label.upper() if q.position.signal else "no budget"


def subject(q: Quarter) -> str:
    p = q.position
    signal = _signal(q)
    return (
        f"{q.project}, {q.name}: {_money(p.spent_year)} labor spent of "
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
            f"{_money(p.spent_quarter)} of labor was spent this quarter, "
            f"{_money(p.spent_year)} this year."
        )
    signal = f" ({_signal(q)})" if p.signal else ""
    out.append(
        f"Forecast at completion {_money(p.p50)} against a "
        f"{_money(p.budget_end)} budget{signal}."
    )
    # Like with like: finished labels and single issues are summed apart.
    if q.misses:
        miss = sum(a.dollars for a in q.misses)
        out.append(
            f"Labels finished this quarter came in {_delta(miss)} against their "
            "estimates (modelled)."
        )
    costed = [m.dollars for m in q.issue_misses if m.dollars is not None]
    if costed:
        out.append(
            f"Issues with their own estimate came in {_delta(sum(costed))} (modelled)."
        )
    total = q.total
    if total.closed is not None and q.total_per_issue is not None:
        out.append(
            f"{total.closed} issues closed, at {_hours(q.total_per_issue)} booked "
            "hours per closed issue."
        )
    elif total.closed is not None:
        out.append(f"{total.closed} issues closed; no hours readings.")
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
    to = q.read_to or q.through
    forecast = f"Forecast at completion as of {q.through}"
    out.append(
        (
            "table",
            1,
            ("", "Amount"),
            [
                (f"Labor spent {_span(q.start, to)}", _money(p.spent_quarter)),
                (
                    f"Labor spent {_span(date(q.start.year, 1, 1), to)} (year to date)",
                    _money(p.spent_year),
                ),
                (f"Budget on {q.start}", _money(p.budget_start)),
                (f"Budget on {q.end}", _money(p.budget_end)),
                (f"{forecast}, P10", _money(p.p10)),
                (f"{forecast}, P50", _money(p.p50)),
                (f"{forecast}, P90", _money(p.p90)),
            ],
        )
    )
    out.append(
        (
            "p",
            (
                f"Non-labor for the year: {_money(p.non_labor)}, in the forecast as a "
                "fixed total and not in labor spent."
            ),
        )
    )
    if p.signal:
        out.append(
            (
                "p",
                (
                    f"{_signal(q)} against the {_money(p.budget_end)} budget in force "
                    f"on {q.end}: {p.signal.rationale}"
                ),
            )
        )
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
    elif not (q.misses or q.in_progress or q.issue_misses):
        out.append(("p", "No estimated label or issue finished this quarter."))
    if q.misses:
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
        header = ("Finished label", "Issues", "Estimated h", "Modelled h", "Difference")
        out.append(("table", 1, header, rows))
    if q.in_progress:
        going = ", ".join(
            f"{label} ({n} of {m} closed)" for label, n, m in q.in_progress
        )
        out.append(("p", f"In progress, no comparison yet: {going}."))
    if q.issue_misses:
        rows = [
            (
                m.key,
                _hours(m.estimated),
                _hours(m.modelled),
                "—" if m.dollars is None else _delta(m.dollars),
            )
            for m in q.issue_misses
        ]
        header = ("Issue", "Estimated h", "Modelled h", "Difference")
        out.append(("table", 1, header, rows))
    if q.misses or q.issue_misses:
        out.append(
            (
                "p",
                (
                    "Modelled, not measured: nobody books hours per issue, so an "
                    "issue's hours are its closer's rate. A label is compared whole, "
                    "once its last issue has closed; its early issues may have closed "
                    "before the board dump's 90 days and be missing from the modelled "
                    "hours."
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
    rows[-1] = ("Total", *rows[-1][1:4], _hours(q.total_per_issue))
    header = ("Week", "Dates", "Closed", "Hours booked", "Hours per issue")
    out.append(("table", 2, header, rows))
    out.append(
        (
            "p",
            (
                "Booked hours between two weekly readings are interpolated. "
                "Hours per issue in the total counts only the weeks where both "
                "are known; a week outside the board dump or the readings shows —."
            ),
        )
    )

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
                cells = (c.replace("|", "\\|") for c in row)
                lines.append("| " + " | ".join(cells) + " |")
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
