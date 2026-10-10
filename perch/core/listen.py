"""perch listen: the lead's lines out of a WebVTT transcript."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from perch.core.workspace import Home

_TAG = re.compile(r"<v(?:\.[^\s>]*)?\s+([^>]*)>")
_ANY = re.compile(r"</?[^>]+>")


def _cues(text: str):
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    for block in re.split(r"\n\s*\n", text):
        lines = block.strip("\n").split("\n")
        if not lines or lines[0].startswith(("WEBVTT", "NOTE")):
            continue
        i = next((n for n, line in enumerate(lines) if "-->" in line), None)
        if i is not None:
            yield lines[i + 1 :]


def _segments(joined: str):
    parts = _TAG.split(joined)  # ['', name, text, name, text, ...]
    for name, seg in zip(parts[1::2], parts[2::2], strict=False):
        yield name, _ANY.sub("", seg).strip()


def parse(vtt_text: str, lead: str) -> list[str]:
    """The lead's cues, in order. A cue's speaker is its first line's `<v Name>`
    tag, else a `Name:` prefix; the whole name must match (case aside)."""
    want, out = lead.strip().casefold(), []
    for body in _cues(vtt_text):
        if not body:
            continue
        if _TAG.search(body[0]):
            for name, seg in _segments(" ".join(body)):
                if name.strip().casefold() == want and seg:
                    out.append(seg)
        else:
            name, sep, rest = body[0].partition(":")
            if sep and name.strip().casefold() == want:
                text = _ANY.sub("", " ".join([rest, *body[1:]])).strip()
                if text:
                    out.append(text)
    return out


def write(home: Home, project: str, lines: list[str], today: date) -> Path:
    """projects/P/listen/YYYY-MM-DD.txt, then -2, -3: never overwrites."""
    d = home.projects_dir / project / "listen"
    d.mkdir(parents=True, exist_ok=True)
    path, n = d / f"{today.isoformat()}.txt", 1
    while path.exists():
        n += 1
        path = d / f"{today.isoformat()}-{n}.txt"
    path.write_text("\n".join(lines) + "\n")
    return path
