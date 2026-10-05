"""The TUI command line: text in, perch argv out."""

import pytest

from perch.core.command import ALL, MNEMONICS, amount, parse

PROJECTS = ["apollo", "Borealis"]


def run(text, current="apollo"):
    return parse(text, PROJECTS, current)


@pytest.mark.parametrize(("mnemonic", "name"), MNEMONICS.items())
def test_every_mnemonic_and_full_name(mnemonic, name):
    want = (name, "-p", "apollo")
    assert run(mnemonic).args == want
    assert run(mnemonic.lower()).args == want
    assert run(name).args == want
    assert run(f"apollo {mnemonic}").project == "apollo"


def test_project_first_cursor_default_and_spelling():
    assert run("borealis BRD", current="apollo").args == ("board", "-p", "Borealis")
    assert run("BRD", current="Borealis").project == "Borealis"


def test_all():
    assert run("ALL MON").args == ("monday", "--all")
    assert run("all wtch").project is None
    assert run("ALL STAT").args == ("status",)
    assert run("ALL QTR 2026-Q3").args == ("quarterly", "--all", "--quarter", "2026-Q3")
    assert ALL == {"monday", "watch", "quarterly", "status", "events", "alerts"}


@pytest.mark.parametrize(
    ("text", "value"),
    [("700k", 700000), ("1.2m", 1200000), ("$700,000", 700000), ("5", 5)],
)
def test_amount(text, value):
    assert amount(text) == value


@pytest.mark.parametrize("bad", ["", "k", "abc", "0", "-5k", "$", "inf", "nan"])
def test_amount_refuses(bad):
    with pytest.raises(ValueError, match="amount"):
        amount(bad)


def test_cut_flags():
    assert run("CUT 700k").args == ("cut", "-p", "apollo", "--budget", "700000")
    assert run("CUT 1.2m").args[-1] == "1200000"
    assert run("CUT $700,000").args[-1] == "700000"
    assert run("CUT $1,250.5").args[-1] == "1250.5"
    assert run("CUT ana:2026-05-01").args[3:] == ("--leaves", "ana:2026-05-01")
    assert run("CUT ana:0.5:2026-05-01").args[3:] == ("--fte", "ana:0.5:2026-05-01")
    both = run("apollo CUT 700k bo:2026-05-01 ana:0.5:2026-05-01").args
    assert both[3:] == (
        "--budget", "700000", "--leaves", "bo:2026-05-01",
        "--fte", "ana:0.5:2026-05-01",
    )  # fmt: skip


def test_monday_and_quarterly():
    assert run("MON weekly").args == ("monday", "-p", "apollo", "--from", "weekly")
    assert run("MON FETCH").args[-2:] == ("--from", "fetch")
    assert run("QTR 2026-Q3").args[-2:] == ("--quarter", "2026-Q3")


def test_go_dropped():
    assert run("BRD <GO>").args == ("board", "-p", "apollo")
    assert run("brd go").args == ("board", "-p", "apollo")
    assert run("CUT 700k <go>").args[-2:] == ("--budget", "700000")


@pytest.mark.parametrize(
    ("text", "current", "message"),
    [
        ("", "apollo", "empty"),
        ("<GO>", "apollo", "empty"),
        ("apollo", "apollo", "FCST"),
        ("ZZZ", "apollo", "ZZZ"),
        ("BRD", None, "no project"),
        ("CUT 700k 800k", "apollo", "once"),
        ("ALL CUT", "apollo", "ALL"),
        ("ALL MON weekly", "apollo", "--from"),
        ("BRD extra", "apollo", "no arguments"),
        ("MON nope", "apollo", "nope"),
        ("MON weekly digest", "apollo", "one"),
        ("QTR a b", "apollo", "one"),
    ],
)
def test_refusals(text, current, message):
    with pytest.raises(ValueError, match=message):
        run(text, current)


def test_detail_events_alerts_grammar():
    assert run("DET").args == ("detail", "-p", "apollo")
    assert run("EVTS").args == ("events", "-p", "apollo")
    assert run("apollo EVTS 60").args == ("events", "-p", "apollo", "--days", "60")
    assert run("ALL EVTS 7").args == ("events", "--all", "--days", "7")
    assert run("ALL ALRT").args == ("alerts", "--all")
    assert run("ALRT").args == ("alerts", "-p", "apollo")
    for bad in ("EVTS 0", "EVTS 367", "EVTS x", "EVTS 1 2", "DET 5", "ALRT 1"):
        with pytest.raises(ValueError):
            run(bad)
    with pytest.raises(ValueError, match="ALL works with"):
        run("ALL DET")
