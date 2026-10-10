from datetime import date
from pathlib import Path

from click.testing import CliRunner

from perch.cli import cli
from perch.core.listen import parse, write
from perch.tests.conftest import build_home
from perch.tests.test_cli_run import recorder

VTT = """WEBVTT

NOTE a note
still note

1
00:00:01.000 --> 00:00:03.000
<v Ryan Adams>Move login to Review.</v>

2
00:00:03.000 --> 00:00:05.000
<v Sam>Agreed.</v>

3
00:00:05.000 --> 00:00:07.000
ryan adams: Close the cache ticket.
"""


def cue(body):
    return f"WEBVTT\n\n1\n00:00:01.000 --> 00:00:03.000\n{body}\n"


def test_voice_tag_cues_by_lead_are_kept():
    assert "Move login to Review." in parse(VTT, "Ryan Adams")


def test_name_prefix_lines_are_kept():
    assert "Close the cache ticket." in parse(VTT, "Ryan Adams")


def test_match_is_case_insensitive():
    assert parse(VTT.replace("Ryan Adams>", "RYAN ADAMS>"), "ryan adams")


def test_other_speakers_are_dropped():
    assert all("Agreed" not in line for line in parse(VTT, "Ryan Adams"))


def test_timing_ids_notes_and_header_are_skipped():
    assert parse(VTT, "Ryan Adams") == [
        "Move login to Review.",
        "Close the cache ticket.",
    ]


def test_multiline_cue_kept_whole():
    v = cue("<v Ryan Adams>First line\nNote: second line</v>")
    assert parse(v, "Ryan Adams") == ["First line Note: second line"]


def test_multi_voice_cue_keeps_only_lead():
    assert parse(cue("<v Sam>Hi</v><v Ryan Adams>Hello</v>"), "Ryan Adams") == ["Hello"]


def test_class_voice_tag():
    assert parse(cue("<v.loud Ryan Adams>Ship it.</v>"), "Ryan Adams") == ["Ship it."]


def test_crlf_and_bom_are_handled():
    assert parse("﻿" + VTT.replace("\n", "\r\n"), "Ryan Adams")


def test_short_name_does_not_match():
    assert parse(VTT, "Ryan") == []


def test_transcript_is_written_dated_never_overwritten(tmp_path):
    home = build_home(tmp_path, "apollo")
    a = write(home, "apollo", ["x"], date(2026, 10, 9))
    b = write(home, "apollo", ["y"], date(2026, 10, 9))
    assert a.name == "2026-10-09.txt" and b.name == "2026-10-09-2.txt"
    assert a.read_text().strip() == "x" and a.parent.name == "listen"


def setup_cli(tmp_path, monkeypatch, lead="Ryan Adams", text=VTT):
    home = build_home(tmp_path, "apollo")
    if lead:
        (home.root / "config.yaml").write_text(f"lead: {lead}\n")
    monkeypatch.chdir(home.root)
    vtt = tmp_path / "MEETING.vtt"
    vtt.write_text(text)
    return home, vtt


def listen(vtt, *extra):
    return CliRunner().invoke(cli, ["listen", str(vtt), "-p", "apollo", *extra])


def test_no_lead_stops_and_says_so(tmp_path, monkeypatch):
    _, vtt = setup_cli(tmp_path, monkeypatch, lead=None)
    ran = recorder(monkeypatch)
    r = listen(vtt)
    assert r.exit_code == 1 and 'no lead set: add "lead: NAME" to' in r.output
    assert "config.yaml" in r.output and not ran


def test_no_lines_stops_and_names_the_lead(tmp_path, monkeypatch):
    _, vtt = setup_cli(tmp_path, monkeypatch, lead="Ryan")
    ran = recorder(monkeypatch)
    r = listen(vtt)
    assert r.exit_code == 1 and not ran
    assert 'no lines from "Ryan" in MEETING.vtt: check the speaker name' in r.output


def test_unreadable_file_stops(tmp_path, monkeypatch):
    setup_cli(tmp_path, monkeypatch)
    ran = recorder(monkeypatch)
    r = listen(tmp_path / "gone.vtt")
    assert r.exit_code == 1 and "cannot read gone.vtt" in r.output and not ran


def test_listen_opens_claude_with_slash_listen(tmp_path, monkeypatch):
    home, vtt = setup_cli(tmp_path, monkeypatch)
    ran = recorder(monkeypatch)
    r = listen(vtt)
    assert r.exit_code == 0, r.output
    assert ran[0].argv == ("claude", "/listen apollo") and ran[0].cwd == home.root
    (kept,) = (home.root / "projects/apollo/listen").glob("*.txt")
    assert kept.read_text().splitlines()[0] == "Move login to Review."
    assert (home.root / ".claude/commands/listen.md").is_file()
    assert listen(vtt).exit_code == 0
    assert len(list((home.root / "projects/apollo/listen").glob("*.txt"))) == 2


def listen_md():
    return (Path(__file__).parents[1] / "commands" / "listen.md").read_text()


def test_listen_md_never_pushes_pulls_or_syncs():
    allowed = next(x for x in listen_md().splitlines() if x.startswith("allowed-tools"))
    for bad in ("push", "pull", "sync", "snapshot"):
        assert f"perch gb {bad}" not in allowed


def test_listen_md_contains_template_fields():
    t = listen_md()
    for f in (
        "Goal:",
        "Done when:",
        "Context:",
        "Out of scope:",
        "Links:",
        "Source: meeting",
    ):
        assert f in t


def test_html_entities_are_unescaped():
    tagged = "WEBVTT\n\n00:00.000 --> 00:01.000\n<v Ryan Adams>R&amp;D is late</v>\n"
    prefixed = "WEBVTT\n\n00:00.000 --> 00:01.000\nRyan Adams: a &lt;b&gt;\n"
    assert parse(tagged, "Ryan Adams") == ["R&D is late"]
    assert parse(prefixed, "Ryan Adams") == ["a <b>"]
