"""The slash commands perch ships: /walk, /listen and a /board that fits the checkout.

`install` writes .claude/commands/NAME.md into the perch checkout (never over
the lead's copy). Claude started in the checkout finds them there, and `apps/`
is already inside its working directory, so .claude/settings.json is never
touched.
"""

from __future__ import annotations

import re
from pathlib import Path

from perch.core.doctor import Check
from perch.core.workspace import Home

COMMANDS = Path(__file__).resolve().parent.parent / "commands"
TOKEN = "@PERCH_DIR@"
# the command files perch itself ships; a name with no file yet is skipped
OWN = ("walk", "listen")
FIX = {"walk": "perch walk", "listen": "perch listen", "board": "perch review"}
# gitboard's own /board runs gitboard from its checkout; from the perch checkout
# the same commands are `perch gb`, and review never pushes (nor has `perch gb`
# an ingest).
_RUNNER = "PYTHONPATH=src .venv/bin/python -m gitboard.cli"
_NEVER = re.compile(rf"Bash\({re.escape(_RUNNER)} (?:push|ingest):\*\)(?:, )?")


def source(home: Home, name: str) -> Path:
    """Where perch's copy of a command comes from: its own, or gitboard's /board."""
    if name == "board":
        return home.gitboard_dir / ".claude" / "commands" / "board.md"
    return COMMANDS / f"{name}.md"


def render(home: Home, name: str = "walk") -> str:
    text = source(home, name).read_text()
    if name == "board":
        text = _NEVER.sub("", text).replace(_RUNNER, "perch gb")
        text = text.replace("Edit(boards/*.yaml)", f"Edit(/{TOKEN}/projects/*/board/*.yaml)")
    return text.replace(TOKEN, str(home.root))


def command_path(home: Home, name: str = "walk") -> Path:
    return home.root / ".claude" / "commands" / f"{name}.md"


def install(home: Home, name: str = "walk") -> list[str]:
    """Write the command if missing; one line saying wrote or kept."""
    path = command_path(home, name)
    if path.exists():
        return [f"kept {path}"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(home, name))
    return [f"wrote {path}"]


def _check(home: Home, name: str) -> Check:
    path = command_path(home, name)
    if not path.exists():
        return Check(
            False, f"{name}: no .claude/commands/{name}.md", FIX.get(name, "")
        )
    if path.read_text() != render(home, name):
        return Check(
            False,
            f"{name}: .claude/commands/{name}.md differs from perch's copy",
            f"delete {path}; the next {FIX.get(name, 'run')} reinstalls it",
        )
    return Check(True, f"{name}: .claude/commands/{name}.md")


def checks(home: Home) -> list[Check]:
    """walk and listen once perch ships them, board once gitboard's file exists."""
    names = [n for n in (*OWN, "board") if source(home, n).is_file()]
    return [_check(home, n) for n in names]
