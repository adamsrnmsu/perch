import io
import json

import pytest

from perch.core import blocks as b

GOOD = [
    b.heading("Open", 2),
    b.text("Trend: cycle median 4.0", tone="dim"),
    b.figures(
        [
            b.figure("Open", "41", note="6 unassigned"),
            b.figure("Done", "7", tone="good"),
        ]
    ),
    b.table(["days", "median"], [["cycle", "4.0"]], title="Time", align=["l", "r"]),
    b.bars([("Review", 2), ("Backlog", 1.5)], title="By column"),
    b.bullets(["Payments: 2 open"]),
]


def test_every_constructor_round_trips_through_emit_and_parse():
    out = io.StringIO()
    b.emit(GOOD, out)
    lines = out.getvalue().splitlines()
    assert len(lines) == len(GOOD)
    assert [b.parse(line) for line in lines] == GOOD


def test_none_fields_are_left_out():
    assert b.text("x") == {"pi": 1, "block": "text", "text": "x"}
    assert b.figure("Open", "41") == {"label": "Open", "value": "41"}


def test_emit_keeps_unicode():
    out = io.StringIO()
    b.emit([b.text("−$12,000 ▲")], out)
    assert "−$12,000 ▲" in out.getvalue()


@pytest.mark.parametrize(
    "line",
    [
        "plain text",
        "{not json",
        "[1, 2]",
        '{"block": "text", "text": "no pi"}',
        '{"pi": 2, "block": "text", "text": "x"}',
        '{"pi": 1, "block": "chart", "text": "x"}',
        '{"pi": 1, "block": "heading", "text": "x"}',
        '{"pi": 1, "block": "heading", "level": 4, "text": "x"}',
        '{"pi": 1, "block": "text", "text": "x", "tone": "loud"}',
        '{"pi": 1, "block": "table", "columns": ["a", "b"], "rows": [["1"]]}',
        '{"pi": 1, "block": "table", "columns": ["a"], "rows": [[1]]}',
        '{"pi": 1, "block": "table", "columns": ["a"], "rows": [], "align": ["l", "r"]}',
        '{"pi": 1, "block": "bars", "items": [["a", "2"]]}',
        '{"pi": 1, "block": "bars", "items": [["a", true]]}',
        '{"pi": 1, "block": "figures", "items": [{"label": "a"}]}',
        '{"pi": 1, "block": "list", "items": "x"}',
        '{"pi": 1, "block": "list", "items": [], "title": 3}',
    ],
)
def test_parse_refuses_what_breaks_the_contract(line):
    assert b.parse(line) is None


def test_wanted_reads_the_env(monkeypatch):
    monkeypatch.delenv(b.ENV, raising=False)
    assert not b.wanted()
    monkeypatch.setenv(b.ENV, "1")
    assert b.wanted()


def test_a_block_may_carry_md():
    line = json.dumps({**b.text("x"), "md": "**x**"})
    assert b.parse(line)["md"] == "**x**"


def test_to_md_renders_each_block_and_md_wins():
    got = b.to_md(
        [
            b.heading("T", 1),
            b.text("intro"),
            b.bullets(["a", "b"]),
            b.figures(
                [b.figure("Open", "41", note="6 unassigned"), b.figure("Done", "7")]
            ),
            b.table(["x", "y"], [["1", "2"]]),
            {**b.text("plain"), "md": "**plain**"},
        ]
    )
    assert got == (
        "# T\n\nintro\n- a\n- b\n\n**Open:** 41 (6 unassigned)\n**Done:** 7\n\n"
        "| x | y |\n| --- | --- |\n| 1 | 2 |\n\n**plain**\n"
    )


def test_non_finite_bar_values_are_not_a_block():
    line = '{"pi": 1, "block": "bars", "items": [["a", 5], ["b", Infinity]]}'
    assert b.parse(line) is None
    assert b.parse(line.replace("Infinity", "NaN")) is None


def test_bars_have_a_pipe_table_markdown_and_md_still_wins():
    bars = b.bars([("a", 5), ("b", 2.5)])
    assert b.to_md([bars]) == "| name | n |\n| --- | --- |\n| a | 5 |\n| b | 2.5 |\n"
    assert b.to_md([{**bars, "md": "x"}]) == "x\n"


def test_markup_in_strings_prints_literally_in_the_terminal(monkeypatch):
    from rich.console import Console

    from perch import cli

    buf = io.StringIO()
    monkeypatch.setattr(cli, "console", Console(file=buf, width=80))
    for blk in (
        b.table(["[/x]"], [["[bold]x[/bold]"]], title="[/t]"),
        b.text("[red]hi"),
        b.heading("[/h]"),
        b.bullets(["[/i]"]),
        b.figures([b.figure("[/l]", "[/v]", note="[/n]")]),
        b.bars([("[/b]", 1)], title="[/t]"),
    ):
        cli._print_block(blk)
    out = buf.getvalue()
    for lit in (
        "[/x]",
        "[bold]x[/bold]",
        "[red]hi",
        "[/h]",
        "[/i]",
        "[/l]",
        "[/v]",
        "[/n]",
        "[/b]",
    ):
        assert lit in out


def test_to_html_escapes_every_string_and_keeps_alignment_and_tone():
    page = b.to_html(
        [
            *GOOD,
            b.text("<script>alert(1)</script>", tone="bad"),
            b.table(["<th>"], [["a & b"]], title="<cap>"),
        ],
        "x <y>",
    )
    assert "<script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert '<p class="bad">' in page
    assert "<title>x &lt;y&gt;</title>" in page
    assert "<caption>&lt;cap&gt;</caption>" in page and "a &amp; b" in page
    assert '<td class="r">4.0</td>' in page  # align "r" survives
    assert "width:20.00rem" in page and "width:15.00rem" in page  # 2 and 1.5 of 2
    assert "<link" not in page and " src=" not in page  # nothing fetched
