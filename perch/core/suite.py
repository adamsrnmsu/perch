"""perch suite: the three TUIs in one hidden tmux, and the hop between them.

Pure, like steps.py: every function returns a tmux argv; nothing here runs
one. Budgie (budgie/tui.py) and gitboard (gitboard/cli.py) carry their own
copy of ``in_suite`` and the hop rule, because neither depends on perch: a
change to the rule is a change in all three.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping

SOCKET = "pi"  # tmux -L pi: the suite's own server, never the user's tmux
SESSION = "pi"
SUITE = "PI_SUITE"
TMUX = ("tmux", "-L", SOCKET)

# (set-option flag, option, value), sent before any window exists: tmux reads
# default-terminal when a pane spawns. -s server, -gw window, -g session.
OPTIONS = (
    ("-g", "status", "off"),
    ("-g", "prefix", "None"),
    ("-g", "prefix2", "None"),
    ("-s", "escape-time", "0"),
    ("-s", "focus-events", "on"),
    ("-g", "default-terminal", "tmux-256color"),
    ("-sa", "terminal-features", ",*:RGB"),
    ("-gw", "remain-on-exit", "off"),
    ("-g", "destroy-unattached", "off"),
)


def in_suite(env: Mapping[str, str]) -> bool:
    """Inside perch suite's tmux: $TMUX is "socket-path,pid,session"."""
    return os.path.basename(env.get("TMUX", "").split(",")[0]) == SOCKET


def entry_key(entry: Mapping) -> str:
    """What a window records in @entry: one entry, one text."""
    return json.dumps(entry, sort_keys=True)


def windows() -> list[str]:
    """One line per window: its name, a tab, its @entry (empty if unset)."""
    return [*TMUX, "list-windows", "-t", SESSION, "-F", "#{window_name}\t#{@entry}"]


def entry_of(listing: str, name: str) -> str | None:
    """``name``'s @entry from ``windows()`` output; None when no such window."""
    for line in listing.splitlines():
        window, _, entry = line.partition("\t")
        if window == name:
            return entry
    return None


def _target(name: str) -> str:
    return f"{SESSION}:={name}"


def _start(entry: Mapping, suite_env: str | None) -> list[str]:
    env = ["-e", f"{SUITE}={suite_env}"] if suite_env is not None else []
    return ["-c", entry["cwd"], *env, *entry["argv"]]


def _mark(name: str, entry: Mapping) -> list[str]:
    return [";", "set-option", "-w", "-t", _target(name), "@entry", entry_key(entry)]


def hop(name: str, entry: Mapping, suite_env: str, current: str | None) -> list[str]:
    """Bring ``name`` to the front, running ``entry``.

    ``current`` is ``entry_of`` for that window. The same entry: select it (the
    instant path). None: the app was quit, open it again. Anything else
    (another project, or nothing recorded): restart only that window.
    """
    if current == entry_key(entry):
        return [*TMUX, "select-window", "-t", _target(name)]
    if current is None:
        return [
            *TMUX, "new-window", "-t", f"{SESSION}:", "-n", name,
            *_start(entry, suite_env), *_mark(name, entry),
        ]  # fmt: skip
    return [
        *TMUX, "respawn-window", "-k", "-t", _target(name),
        *_start(entry, suite_env), *_mark(name, entry),
        ";", "select-window", "-t", _target(name),
    ]  # fmt: skip


def launch(perch: Mapping, suite: Mapping | None) -> list[str]:
    """Start the suite detached: options, perch in front, Budgie and gitboard
    warming up behind it. ``suite`` None (a bad project config): perch alone,
    and its hops open the others later."""
    argv = [*TMUX, "-f", "/dev/null", "start-server"]
    for flag, option, value in OPTIONS:
        argv += [";", "set-option", flag, option, value]
    env = json.dumps(suite) if suite is not None else None
    argv += [
        ";",
        "new-session",
        "-d",
        "-s",
        SESSION,
        "-n",
        "perch",
        *_start(perch, env),
    ]
    argv += _mark("perch", perch)
    for name in ("budgie", "gitboard") if suite is not None else ():
        argv += [";", "new-window", "-d", "-t", f"{SESSION}:", "-n", name]
        argv += [*_start(suite[name], env), *_mark(name, suite[name])]
    return [*argv, ";", "select-window", "-t", _target("perch")]


def has_session() -> list[str]:
    return [*TMUX, "has-session", "-t", SESSION]


def attach() -> list[str]:
    return [*TMUX, "attach", "-t", SESSION]


def kill() -> list[str]:
    return [*TMUX, "kill-session", "-t", SESSION]
