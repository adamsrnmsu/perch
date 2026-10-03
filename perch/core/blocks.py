"""Blocks: the output format every pi tool prints when `perch tui` asks.

The contract is docs/superpowers/specs/2026-10-02-tui-blocks-design.md. With
`PI_BLOCKS=1` in the environment a command prints one JSON object per stdout
line; the TUI turns each into a widget and shows any other line as text.
Plain dicts, UI-free: building them is here, drawing them is the TUI's (or,
in a terminal, cli.py's).
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterable
from typing import TextIO

ENV = "PI_BLOCKS"
TONES = ("good", "warn", "bad", "dim")


def wanted() -> bool:
    """True when the caller (the TUI) asked for blocks."""
    return os.environ.get(ENV) == "1"


def _block(kind: str, **fields) -> dict:
    return {
        "pi": 1,
        "block": kind,
        **{k: v for k, v in fields.items() if v is not None},
    }


def heading(text: str, level: int = 2) -> dict:
    return _block("heading", level=level, text=text)


def text(text: str, tone: str | None = None) -> dict:
    return _block("text", text=text, tone=tone)


def figure(
    label: str, value: str, note: str | None = None, tone: str | None = None
) -> dict:
    """One tile of a `figures` block."""
    return {
        k: v
        for k, v in {"label": label, "value": value, "note": note, "tone": tone}.items()
        if v is not None
    }


def figures(items: list[dict]) -> dict:
    return _block("figures", items=items)


def table(
    columns: list[str],
    rows: list[list[str]],
    title: str | None = None,
    align: list[str] | None = None,
) -> dict:
    return _block("table", title=title, columns=columns, rows=rows, align=align)


def bars(
    items: list[tuple[str, float]], title: str | None = None, unit: str | None = None
) -> dict:
    return _block(
        "bars", title=title, items=[[label, n] for label, n in items], unit=unit
    )


def bullets(items: list[str]) -> dict:
    """A `list` block (named so it does not shadow the builtin)."""
    return _block("list", items=items)


def emit(blocks: Iterable[dict], out: TextIO | None = None) -> None:
    """One JSON line per block, to stdout unless told otherwise."""
    out = out or sys.stdout
    for b in blocks:
        out.write(json.dumps(b, ensure_ascii=False) + "\n")
    out.flush()


def _strs(value, n: int | None = None) -> bool:
    return (
        isinstance(value, list)
        and all(isinstance(v, str) for v in value)
        and (n is None or len(value) == n)
    )


def _tone(b: dict) -> bool:
    return b.get("tone") is None or b["tone"] in TONES


def _figure(f) -> bool:
    return (
        isinstance(f, dict)
        and isinstance(f.get("label"), str)
        and isinstance(f.get("value"), str)
        and isinstance(f.get("note", ""), str)
        and _tone(f)
    )


def _bar(item) -> bool:
    return (
        isinstance(item, list)
        and len(item) == 2
        and isinstance(item[0], str)
        and isinstance(item[1], int | float)
        and not isinstance(item[1], bool)
    )


_VALID = {
    "heading": lambda b: b.get("level") in (1, 2, 3) and isinstance(b.get("text"), str),
    "text": lambda b: isinstance(b.get("text"), str) and _tone(b),
    "figures": lambda b: (
        isinstance(b.get("items"), list) and all(map(_figure, b["items"]))
    ),
    "table": lambda b: (
        _strs(b.get("columns"))
        and isinstance(b.get("rows"), list)
        and all(_strs(r, len(b["columns"])) for r in b["rows"])
        and (b.get("align") is None or _strs(b["align"], len(b["columns"])))
    ),
    "bars": lambda b: isinstance(b.get("items"), list) and all(map(_bar, b["items"])),
    "list": lambda b: _strs(b.get("items")),
}


def parse(line: str) -> dict | None:
    """The block on this line, or None: plain text, bad JSON, or a block that
    breaks the contract (the TUI then shows the raw line)."""
    if not line.startswith("{"):
        return None
    try:
        obj = json.loads(line)
    except ValueError:
        return None
    if not isinstance(obj, dict) or obj.get("pi") != 1:
        return None
    valid = _VALID.get(obj.get("block"))
    if valid is None or not valid(obj):
        return None
    if obj.get("title") is not None and not isinstance(obj["title"], str):
        return None
    return obj
