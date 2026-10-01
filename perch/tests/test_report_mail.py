import email
from datetime import date
from email import policy

from perch.core.report_mail import render_eml, render_md
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
    assert "| Spent this quarter | $3,393 |" in text  # 19 days at $1,250/7
    assert "| 2026-04-15 | Q2 increase | $120,000 |" in text
    assert "| 2026-W15 | Apr 6 – Apr 12 | 1 | 15 | 15 |" in text
    assert "| 2026-W16 | Apr 13 – Apr 19 | 0 | 15 | — |" in text
    assert "19 issue-days in Blocked; 1 issue moved back out of Done." in text
    assert "| 2026-05-01 | Bob | FTE change | 0.5 → 0.25 | -333 | -$16,633 |" in text


def test_coverage_and_missing_inputs_are_said_where_they_matter(world):
    text = render_md(make(world, "2026-Q1"))
    assert "covers Jan 20 – Mar 31; the board dump keeps 90 days" in text
    assert "| epic::billing | 4 | 60 | 100 | +$4,000 |" in text
    assert "The budget is a flat number; no revisions." in text
    bare = render_md(make(world, "2026-Q1", estimates=False))
    assert "No `estimates:` in perch.yaml" in bare


def test_the_eml_is_an_outlook_draft(quarter_world):
    q = make(quarter_world, "2026-Q2")
    msg = email.message_from_bytes(bytes(render_eml(q)), policy=policy.default)
    p50 = f"${q.position.p50:,.0f}"
    signal = q.position.signal.signal.name
    assert msg["Subject"] == (
        f"apollo, 2026-Q2: $26,000 spent of $120,000; "
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
