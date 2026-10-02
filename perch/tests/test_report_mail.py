import email
from dataclasses import replace
from datetime import date
from email import policy

from perch.core.report_mail import render_eml, render_md, subject
from perch.core.watch import render
from perch.tests.test_quarterly import make


def test_the_markdown_has_every_section(quarter_world):
    text = render_md(make(quarter_world, "2026-Q2"))
    assert text.startswith("# apollo, 2026-Q2 to date (as of 2026-04-19)")
    for heading in (
        "## 1. Budget position",
        "## 2. Estimate misses ($), MODELLED",
        "## 3. Throughput",
        "## 4. Waiting and staffing",
    ):
        assert heading in text
    assert "| Labor spent Apr 1 – Apr 19 | $3,393 |" in text  # 19 days at $1,250/7
    assert "| Labor spent Jan 1 – Apr 19 (year to date) | $26,000 |" in text
    assert "Non-labor for the year: $5,000, in the forecast (a cost line" in text
    assert "| Forecast at completion as of 2026-04-19, P50 |" in text
    assert "against the $120,000 budget in force on 2026-06-30" in text
    assert "| 2026-04-15 | Q2 increase | $120,000 |" in text
    assert "| 2026-W15 | Apr 6 – Apr 12 | 1 | 15 | 15 |" in text
    assert "| 2026-W16 | Apr 13 – Apr 19 | 0 | 15 | — |" in text
    assert "| Total | Apr 1 – Apr 19 | 2 | 41 | 20 |" in text  # 285/7 h over 2
    assert "19 issue-days in Blocked; 1 issue moved back out of Done." in text
    assert "| 2026-05-01 | Bob | FTE change | 0.5 → 0.25 | -333 | -$16,633 |" in text


def test_coverage_and_missing_inputs_are_said_where_they_matter(world):
    text = render_md(make(world, "2026-Q1"))
    assert "covers Jan 20 – Mar 31; the board dump keeps 90 days" in text
    assert (
        "In progress, no comparison yet: epic::billing (4 of 5 closed by Mar 31)."
        in text
    )
    assert "| #1 | 15 | 25 | +$1,000 |" in text
    assert "Issues with their own estimate, total: +$2,000." in text
    assert "hourly cost" not in text
    assert "| 2026-W02 | Jan 5 – Jan 11 | — |" in text  # before the dump: unknown
    assert "The budget is a flat number; no revisions." in text
    bare = render_md(make(world, "2026-Q1", estimates=False))
    assert "No `estimates:` in perch.yaml" in bare


def test_the_previous_quarter_is_a_row_beside_the_total(world):
    from perch.tests.test_quarterly import since

    assert "Previous quarter" not in render_md(make(world, "2026-Q2"))
    since(world, "2026-01-01")
    text = render_md(make(world, "2026-Q2"))
    # 240 + 275/7 = 279.3 h over 11 issues = 25.4 h each.
    assert "| Previous quarter, 2026-Q1 | Jan 1 – Mar 31 | 11 | 279 | 25 |" in text
    assert "Previous quarter, 2026-Q1: 0 issue-days in Blocked." in text


def test_a_pipe_in_a_cell_is_escaped(quarter_world):
    budget = quarter_world.parent / "fy26" / "budget.csv"
    budget.write_text(budget.read_text().replace("Q2 increase", "Q2 | up"))
    assert "| 2026-04-15 | Q2 \\| up | $120,000 |" in render_md(
        make(quarter_world, "2026-Q2")
    )


def test_without_readings_the_opening_says_so_cleanly(world):
    (world.parent / "fy26" / "weekly.csv").unlink()
    text = render_md(make(world, "2026-Q2"))
    opening = text.split("\n\n")[1]
    assert opening.count("no hours readings") == 1
    assert "2 issues closed." in opening
    assert "on — booked hours" not in text


def test_the_eml_is_an_outlook_draft(quarter_world):
    q = make(quarter_world, "2026-Q2")
    msg = email.message_from_bytes(bytes(render_eml(q)), policy=policy.default)
    p50 = f"${q.position.p50:,.0f}"
    signal = q.position.signal.label.upper()
    assert msg["Subject"] == (
        f"apollo, 2026-Q2: $26,000 labor spent of $120,000; "
        f"forecast at completion {p50} ({signal})"
    )
    assert msg["X-Unsent"] == "1"
    assert msg.get_content_type() == "multipart/alternative"
    plain, html = msg.get_payload()
    assert plain.get_content_type() == "text/plain"
    assert plain.get_payload(decode=True).decode() == render_md(q)
    assert html.get_content_type() == "text/html"
    body = html.get_payload(decode=True).decode()
    assert "<table" in body and "Q2 increase" in body
    for banned in ("<style", "display:flex", "grid"):
        assert banned not in body


def test_a_finished_quarter_is_not_to_date(world):
    q = make(world, "2026-Q1", today=date(2026, 10, 1))
    assert render_md(q).startswith("# apollo, 2026-Q1\n")


def test_nothing_from_the_private_watch_reaches_the_report(quarter_world):
    from perch.cli import _watch

    q = make(quarter_world, "2026-Q2")
    msg = render_eml(q)
    report = render_md(q) + msg.get_payload()[1].get_content()
    lines = [line for line in render(_watch(quarter_world)).splitlines() if line]
    assert lines and not [line for line in lines if line in report]


def opening(q):
    return render_md(q).split("\n\n")[1]


def test_the_opening_says_why_there_is_no_hours_per_issue(quarter_world):
    q = make(quarter_world, "2026-Q2")
    assert "2 issues closed, at 20 booked hours per closed issue." in opening(q)
    none = replace(q, weeks=tuple(replace(w, closed=0) for w in q.weeks))
    assert "0 issues closed." in opening(none)
    apart = replace(  # the close and the hours in different weeks
        q,
        weeks=(
            replace(q.weeks[0], closed=1, hours=None),
            replace(q.weeks[1], closed=0),
        ),
    )
    text = opening(apart)
    assert "1 issue closed; hours per issue not available for these weeks." in text
    assert "no hours readings" not in text


def test_a_partial_dump_gives_the_span_it_counts(world):
    text = render_md(make(world, "2026-Q1"))
    # Weeks from Jan 26 are wholly inside the dump (it starts Jan 20).
    assert (
        "9 issues closed Jan 26 – Mar 31 (the board dump covers Jan 20 – Mar 31)"
    ) in text
    assert "0 issue-days were spent in Blocked Jan 20 – Mar 31." in text
    assert "| Total, closes counted Jan 26 – Mar 31 | Jan 1 – Mar 31 | 9 |" in text


def test_a_finished_quarter_whose_readings_stop_early_says_through(world):
    q = make(world, "2026-Q2", today=date(2026, 10, 1))
    assert subject(q).startswith(
        "apollo, 2026-Q2: $26,000 labor spent through Apr 19 of $100,000;"
    )
    text = render_md(q)
    assert "was spent this quarter through Apr 19" in text
    assert "| Forecast at completion as of 2026-04-19, P50 |" in text


def test_issues_without_an_hourly_cost_are_named_as_left_out(world):
    q = make(world, "2026-Q1")
    one, two = q.issue_misses  # #1 and #2, +$1,000 each
    q = replace(q, issue_misses=(one, replace(two, dollars=None)))
    left_out = "1 issue without a known hourly cost is not in the dollar total"
    assert (
        f"Issues with their own estimate came in +$1,000 (modelled; {left_out})."
        in opening(q)
    )
    text = render_md(q)
    assert "| #2 | 15 | 25 | — |" in text
    assert f"Issues with their own estimate, total: +$1,000; {left_out}." in text
    none = replace(q, issue_misses=tuple(replace(m, dollars=None) for m in (one, two)))
    assert (
        "Issues with their own estimate came in — (modelled; 2 issues without a "
        "known hourly cost are not in the dollar total)."
    ) in opening(none)
