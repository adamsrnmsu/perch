from datetime import date

from perch.core.listen import parse, write
from perch.tests.conftest import build_home

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
