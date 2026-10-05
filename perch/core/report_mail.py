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


def _signal(q: Quarter) -> str:
    """Budgie's own word for the signal: GOOD, CAUTION, BAD or NO CHANGE."""
    return q.position.signal.label.upper() if q.position.signal else "no budget"


def _early(q: Quarter) -> str:
    """` through Apr 19` when a finished quarter's readings stop before its end."""
    if q.to_date or q.read_to is None or q.read_to >= q.end:
        return ""
    return f" through {q.read_to:%b} {q.read_to.day}"


def _issues(n: int) -> str:
    return f"{n} issue" if n == 1 else f"{n} issues"


def _uncosted(q: Quarter) -> str:
    """`; 1 issue without a known hourly cost is not in the dollar total`, or ""."""
    n = sum(1 for m in q.issue_misses if m.dollars is None)
    if not n:
        return ""
    verb = "is" if n == 1 else "are"
    return f"; {_issues(n)} without a known hourly cost {verb} not in the dollar total"


def _issue_total(q: Quarter) -> str:
    """The `#iid` rows' dollar sum; — when no row has an hourly cost."""
    costed = [m.dollars for m in q.issue_misses if m.dollars is not None]
    return _delta(sum(costed)) if costed else "—"


def _pace(q: Quarter) -> str | None:
    """Booked against planned hours, as a plain share: no verdict."""
    p = q.position
    if p.booked_quarter is None:
        return None  # no readings in the quarter: hours_note already says so
    if p.planned_quarter is None:
        return "No plan to compare booked hours with."
    if p.planned_quarter <= 0:
        span = _span(q.start, q.read_to or q.through)
        return f"No hours are planned for {span}; {_hours(p.booked_quarter)} booked."
    return f"Booked {p.booked_quarter / p.planned_quarter:.0%} of planned hours."


def _scope(q: Quarter) -> str | None:
    """Opened and closed issues and the net change in open work: no verdict."""
    net = q.net_scope
    if net is None:
        if q.total.closed is not None:  # the dump reaches the quarter
            return (
                "The board dump has no creation dates; run `perch fetch` to "
                "count opened issues."
            )
        return None
    t = q.total
    span = _span(*(q.closed_span or (q.start, q.through)))
    if net == 0:
        change = "no net change in open issues"
    else:
        issues = "issue" if abs(net) == 1 else "issues"
        change = f"a net change of {net:+d} open {issues}"
    return f"Opened {t.opened}, closed {t.closed} in {span}: {change}."


def subject(q: Quarter) -> str:
    p = q.position
    signal = _signal(q)
    return (
        f"{q.project}, {q.name}: {_money(p.spent_year)} labor spent{_early(q)} of "
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
            f"{_money(p.spent_quarter)} of labor was spent this quarter{_early(q)}, "
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
    if q.issue_misses:
        out.append(
            f"Issues with their own estimate came in {_issue_total(q)} "
            f"(modelled{_uncosted(q)})."
        )
    total = q.total
    # A partial dump counts part of the quarter: say which part.
    counted = dumped = ""
    if q.board_partial:
        dumped = f" {_span(*q.board_span)}"
        if q.closed_span:
            counted = f" {_span(*q.closed_span)} (the board dump covers{dumped})"
    if total.closed is not None:
        closed = f"{_issues(total.closed)} closed{counted}"
        if q.total_per_issue is not None:
            out.append(
                f"{closed}, at {_hours(q.total_per_issue)} booked hours per "
                "closed issue."
            )
        elif q.as_of is None or total.closed == 0:
            out.append(f"{closed}.")
        else:
            out.append(f"{closed}; hours per issue not available for these weeks.")
    if q.blocked_days is not None:
        out.append(f"{q.blocked_days} issue-days were spent in Blocked{dumped}.")
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
    forecast = f"Forecast at completion as of {to}"
    out.append(
        (
            "table",
            1,
            ("", "Amount"),
            [
                (f"Labor spent {_span(q.start, to)}", _money(p.spent_quarter)),
                (
                    f"Labor spent {_span(q.year_start, to)} (year to date)",
                    _money(p.spent_year),
                ),
                (f"Hours planned {_span(q.start, to)}", _hours(p.planned_quarter)),
                (f"Hours booked {_span(q.start, to)}", _hours(p.booked_quarter)),
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
                f"Non-labor for the year: {_money(p.non_labor)}, in the forecast "
                "(a cost line with a low/high range is sampled with the labor, as "
                "`budgie forecast` does) and not in labor spent."
            ),
        )
    )
    if pace := _pace(q):
        out.append(("p", pace))
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
                _delta(a.dollars) if a.modelled else "—",  # nothing modelled to cost
            )
            for a in q.misses
        ]
        header = ("Finished label", "Issues", "Estimated h", "Modelled h", "Difference")
        out.append(("table", 1, header, rows))
    if q.in_progress:
        by = f"{q.through:%b} {q.through.day}"
        going = ", ".join(
            f"{label} ({n} of {m} closed by {by})" for label, n, m in q.in_progress
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
        out.append(
            (
                "p",
                (
                    "Issues with their own estimate, total: "
                    f"{_issue_total(q)}{_uncosted(q)}."
                ),
            )
        )
    if q.misses or q.issue_misses:
        out.append(
            (
                "p",
                (
                    "Modelled, not measured: nobody books hours per issue, so an "
                    "issue's hours are its closer's rate. A label is compared whole, "
                    "once its last issue has closed; its early issues may have closed "
                    "before the board dump's history starts and be missing from the "
                    "modelled hours."
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
            _count(w.opened),
            _count(w.closed),
            _hours(w.hours),
            _hours(w.per_issue),
        )
        for w in (*q.weeks, q.total)
    ]
    total = "Total"
    if q.board_partial and q.closed_span:
        total = f"Total, closes counted {_span(*q.closed_span)}"
    rows[-1] = (total, *rows[-1][1:5], _hours(q.total_per_issue))
    if (w := q.previous) is not None:
        rows.append(
            (
                f"Previous quarter, {w.label}",
                _span(w.start, w.end),
                _count(w.opened),
                _count(w.closed),
                _hours(w.hours),
                _hours(w.per_issue),
            )
        )
    header = ("Week", "Dates", "Opened", "Closed", "Hours booked", "Hours per issue")
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
    if scope := _scope(q):
        out.append(("p", scope))

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
    if q.previous is not None:
        out.append(
            (
                "p",
                (
                    f"Previous quarter, {q.previous.label}: {q.previous_blocked} "
                    "issue-days in Blocked."
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
