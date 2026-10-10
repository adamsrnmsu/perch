"""The slash commands perch ships: /walk, /listen and a /board that fits the checkout.

`install` writes .claude/commands/NAME.md into the perch checkout (never over
the lead's copy). Claude started in the checkout finds them there, and `apps/`
is already inside its working directory, so .claude/settings.json is never
touched.
"""

from __future__ import annotations

from pathlib import Path

from perch.core.doctor import Check
from perch.core.workspace import Home

COMMANDS = Path(__file__).resolve().parent.parent / "commands"
TOKEN = "@PERCH_DIR@"
# the command files perch itself ships; a name with no file yet is skipped
OWN = ("walk", "listen")
FIX = {"walk": "perch walk", "listen": "perch listen"}


def render(home: Home, name: str = "walk") -> str:
    return (COMMANDS / f"{name}.md").read_text().replace(TOKEN, str(home.root))


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
    return [_check(home, n) for n in OWN if (COMMANDS / f"{n}.md").is_file()]
