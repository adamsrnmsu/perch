"""The TUI command line's grammar: text in, perch argv out.

Nothing here runs perch or reads a file; `parse` only splits and checks the
words, so the TUI can show a bad line as a toast before spawning anything.
`perch cut` still validates names and dates itself.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

MNEMONICS = {
    "BRD": "board",
    "MON": "monday",
    "DOC": "doctor",
    "FCST": "forecast",
    "WTCH": "watch",
    "QTR": "quarterly",
    "CUT": "cut",
    "HRS": "hours",
    "STAT": "status",
    "FTCH": "fetch",
    "DIG": "digest",
    "MAIL": "emails",
    "WKLY": "weekly",
    "BUD": "budget",
    "REV": "review",
    "DET": "detail",
    "EVTS": "events",
    "ALRT": "alerts",
}
ALL = {"monday", "watch", "quarterly", "status", "events", "alerts"}  # what ALL accepts
FROM = ("fetch", "board", "weekly", "digest", "emails")  # monday --from


@dataclass(frozen=True)
class Command:
    project: str | None  # None: every project (ALL)
    args: tuple[str, ...]  # perch's argv after the binary


def amount(token: str) -> float:
    """`700k`, `1.2M`, `$700,000` -> a positive number."""
    text = token.replace("$", "").replace(",", "").lower()
    scale = {"k": 1e3, "m": 1e6}.get(text[-1:], 1)
    try:
        value = float(text[:-1] if scale > 1 else text) * scale
    except ValueError:
        value = 0
    if not 0 < value < math.inf:  # also catches nan
        raise ValueError(f"not an amount: {token!r} (try 700k, 1.2m or $700,000)")
    return value


def _cut(tokens: list[str]) -> list[str]:
    flags: list[str] = []
    for tok in tokens:
        colons = tok.count(":")
        if colons == 0:
            if "--budget" in flags:
                raise ValueError("cut takes one budget amount, given once")
            value = amount(tok)
            flags += ["--budget", str(int(value)) if value.is_integer() else str(value)]
        elif colons == 1:
            flags += ["--leaves", tok]
        elif colons == 2:
            flags += ["--fte", tok]
        else:
            raise ValueError(
                f"bad cut token {tok!r}: AMOUNT, NAME:DATE or NAME:FTE:DATE"
            )
    return flags


def _how(command: str, tokens: list[str]) -> list[str]:
    if command == "bg":  # BG SUB [ARGS...]: Budgie's own table, args passed through
        from perch.core.steps import BG_SUBS

        if not tokens or tokens[0].lower() not in BG_SUBS:
            raise ValueError(f"bg takes a sub: {', '.join(BG_SUBS)}")
        return [tokens[0].lower(), *tokens[1:]]
    if command == "cut":
        return _cut(tokens)
    if command == "monday":
        if not tokens:
            return []
        if len(tokens) > 1 or tokens[0].lower() not in FROM:
            given = " ".join(tokens)
            raise ValueError(f"monday takes one step, not {given!r}: {', '.join(FROM)}")
        return ["--from", tokens[0].lower()]
    if command == "quarterly":
        if len(tokens) > 1:
            raise ValueError("quarterly takes at most one quarter, e.g. 2026-Q3")
        return ["--quarter", tokens[0]] if tokens else []
    if command == "events":
        if not tokens:
            return []
        if len(tokens) > 1 or not (
            tokens[0].isdecimal() and 1 <= int(tokens[0]) <= 366
        ):
            raise ValueError("events takes one number of days, 1 to 366")
        return ["--days", str(int(tokens[0]))]
    if tokens:
        raise ValueError(f"{command} takes no arguments")
    return []


def parse(text: str, projects: Sequence[str], current: str | None) -> Command:
    tokens = text.split()
    if tokens and tokens[-1].upper() in ("<GO>", "GO"):
        tokens.pop()
    if not tokens:
        raise ValueError("empty")
    # Who: a project name, ALL, or the cursor's project.
    by_name = {p.lower(): p for p in projects}
    every = tokens[0].upper() == "ALL"
    project = current
    if every or tokens[0].lower() in by_name:
        project = None if every else by_name[tokens[0].lower()]
        tokens.pop(0)
    elif current is None:
        raise ValueError("no project: give one, e.g. apollo CUT 700k")
    # What: a mnemonic or the perch command's own name.
    if not tokens:
        raise ValueError(f"no command: try {', '.join(MNEMONICS)}")
    word = tokens.pop(0)
    command = MNEMONICS.get(word.upper())
    if command is None and (word.lower() in MNEMONICS.values() or word.lower() == "bg"):
        command = word.lower()
    if command is None:
        raise ValueError(f"unknown command {word!r}: try {', '.join(MNEMONICS)}")
    # How, then build.
    if every:
        if command not in ALL:
            raise ValueError(f"ALL works with {', '.join(sorted(ALL))}, not {command}")
        if command == "monday" and tokens:
            raise ValueError("ALL MON takes no step: --from needs one project")
    flags = _how(command, tokens)
    if every:
        return Command(
            None, ("status",) if command == "status" else (command, "--all", *flags)
        )
    return Command(project, (command, "-p", str(project), *flags))
