"""Blocks: the output format every pi tool prints when `perch tui` asks.

The contract is docs/superpowers/specs/2026-10-02-tui-blocks-design.md. With
`PI_BLOCKS=1` in the environment a command prints one JSON object per stdout
line; the TUI turns each into a widget and shows any other line as text.
Plain dicts, UI-free: building them is here, drawing them is the TUI's (or,
in a terminal, cli.py's).
"""

from __future__ import annotations

import html
import json
import math
import os
import sys
from collections.abc import Iterable
from typing import TextIO

ENV = "PI_BLOCKS"
TONES = ("good", "warn", "bad", "dim")
TONE_STYLE = {
    "good": "green",
    "warn": "yellow",
    "bad": "red",
    "dim": "dim",
}  # rich styles


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
        and math.isfinite(item[1])
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


def _md(b: dict) -> str:
    """One block as markdown; the block's own `md` wins."""
    if b.get("md") is not None:
        return b["md"]
    kind = b["block"]
    if kind == "heading":
        return f"{'#' * b['level']} {b['text']}"
    if kind == "text":
        return b["text"]
    if kind == "list":
        return "\n".join(f"- {i}" for i in b["items"])
    if kind == "figures":
        return "\n".join(
            f"**{f['label']}:** {f['value']}"
            + (f" ({f['note']})" if "note" in f else "")
            for f in b["items"]
        )
    if kind == "table":
        cols = b["columns"]
        rows = [cols, ["---"] * len(cols), *b["rows"]]
        return "\n".join("| " + " | ".join(r) + " |" for r in rows)
    rows = [
        ["name", "n"],
        ["---", "---"],
        *([k, str(n)] for k, n in b["items"]),
    ]  # bars
    return "\n".join("| " + " | ".join(r) + " |" for r in rows)


def to_md(blocks: list[dict]) -> str:
    """Markdown for a block list: paragraphs split by a blank line, except a
    list straight after text, which hugs it."""
    out = ""
    prev = None
    for b in blocks:
        out += (
            ""
            if prev is None
            else "\n"
            if (prev, b["block"]) == ("text", "list")
            else "\n\n"
        ) + _md(b)
        prev = b["block"]
    return out + "\n"


_CSS = """
:root { --fg: #1d1d1f; --bg: #fff; --dim: #6e6e73; --line: #d2d2d7;
  --good: #1a7f37; --warn: #9a6700; --bad: #cf222e; --bar: #0969da; }
@media (prefers-color-scheme: dark) { :root { --fg: #e6e6e6; --bg: #161618;
  --dim: #9a9aa0; --line: #3a3a3e; --good: #3fb950; --warn: #d29922;
  --bad: #f85149; --bar: #58a6ff; } }
body { font: 15px/1.5 system-ui, sans-serif; color: var(--fg);
  background: var(--bg); max-width: 60rem; margin: 2rem auto; padding: 0 16px; }
table { border-collapse: collapse; margin: 1rem 0; display: block; overflow-x: auto; }
th, td { padding: .25rem .75rem; border-bottom: 1px solid var(--line); }
th { text-align: left; } .r { text-align: right; font-variant-numeric: tabular-nums; }
caption { text-align: left; font-weight: 600; padding: .25rem 0; white-space: nowrap; }
.figures { display: flex; flex-wrap: wrap; gap: .75rem; margin: 1rem 0; }
.figure { border: 1px solid var(--line); border-radius: 6px; padding: .5rem .75rem; }
.figure b { display: block; font-size: 1.2rem; }
.bars div { display: flex; gap: .5rem; align-items: center; }
.bars span:first-child { min-width: 10rem; }
.bars i { display: inline-block; height: .8rem; background: var(--bar); }
.good { color: var(--good); } .warn { color: var(--warn); }
.bad { color: var(--bad); } .dim, small { color: var(--dim); }
"""


def _html(b: dict) -> str:
    """One block as HTML. Every string is escaped: block text comes from files."""
    e = html.escape
    kind = b["block"]
    tone = f' class="{b["tone"]}"' if b.get("tone") else ""
    if kind == "heading":
        return f"<h{b['level']}>{e(b['text'])}</h{b['level']}>"
    if kind == "text":
        return f"<p{tone}>{e(b['text'])}</p>"
    if kind == "list":
        return "<ul>" + "".join(f"<li>{e(i)}</li>" for i in b["items"]) + "</ul>"
    if kind == "figures":
        tiles = "".join(
            f'<div class="figure {f.get("tone", "")}">{e(f["label"])}'
            f"<b>{e(f['value'])}</b>"
            + (f"<small>{e(f['note'])}</small>" if "note" in f else "")
            + "</div>"
            for f in b["items"]
        )
        return f'<div class="figures">{tiles}</div>'
    if kind == "table":
        align = b.get("align") or ["l"] * len(b["columns"])
        cls = ["" if a != "r" else ' class="r"' for a in align]

        def row(cells, tag):
            return (
                "<tr>"
                + "".join(
                    f"<{tag}{c}>{e(v)}</{tag}>" for v, c in zip(cells, cls, strict=True)
                )
                + "</tr>"
            )

        caption = f"<caption>{e(b['title'])}</caption>" if b.get("title") else ""
        return (
            f"<table>{caption}<thead>{row(b['columns'], 'th')}</thead><tbody>"
            + "".join(row(r, "td") for r in b["rows"])
            + "</tbody></table>"
        )
    top = max((n for _, n in b["items"]), default=0) or 1  # bars
    title = f"<h3>{e(b['title'])}</h3>" if b.get("title") else ""
    unit = f" {e(b['unit'])}" if b.get("unit") else ""
    return (
        f'{title}<div class="bars">'
        + "".join(
            f"<div><span>{e(label)}</span>"
            f'<i style="width:{max(n, 0) / top * 20:.2f}rem"></i>'
            f"<span>{n:g}{unit}</span></div>"
            for label, n in b["items"]
        )
        + "</div>"
    )


def to_html(blocks: list[dict], title: str) -> str:
    """A self-contained page for a block list: inline CSS, no script, nothing
    fetched, so the file opens anywhere."""
    body = "\n".join(_html(b) for b in blocks)
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{_CSS}</style></head>"
        f"<body>\n{body}\n</body></html>\n"
    )
