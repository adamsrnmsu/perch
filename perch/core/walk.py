"""The /walk slash command: perch ships it, the workspace holds it.

`install` writes .claude/commands/walk.md (never over the lead's copy) and adds
the gitboard checkout to .claude/settings.json's additionalDirectories, so a
bare `claude` in the workspace can edit the board file.
"""

from __future__ import annotations

import json
from pathlib import Path

from perch.core.doctor import Check
from perch.core.workspace import Home

COMMAND = Path(__file__).resolve().parent.parent / "commands" / "walk.md"
TOKEN = "@GITBOARD_DIR@"


def render(home: Home) -> str:
    return COMMAND.read_text().replace(TOKEN, str(home.gitboard_dir))


def command_path(home: Home) -> Path:
    return home.root / ".claude" / "commands" / "walk.md"


def _settings_path(home: Home) -> Path:
    return home.root / ".claude" / "settings.json"


def _settings(home: Home) -> dict | None:
    """The workspace's settings, {} when absent, None when perch must not touch them."""
    path = _settings_path(home)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    perms = data.get("permissions", {})
    if not isinstance(perms, dict) or not isinstance(
        perms.get("additionalDirectories", []), list
    ):
        return None
    return data


def install(home: Home) -> list[str]:
    """Write what is missing; one line per thing done or left for the lead."""
    lines = []
    path = command_path(home)
    if path.exists():
        lines.append(f"kept {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(home))
        lines.append(f"wrote {path}")
    gitboard = str(home.gitboard_dir)
    settings = _settings(home)
    if settings is None:
        lines.append(
            f"left {_settings_path(home)} alone (not a settings object perch can "
            f"edit); add {gitboard} to permissions.additionalDirectories by hand"
        )
        return lines
    extra = settings.setdefault("permissions", {}).setdefault(
        "additionalDirectories", []
    )
    if gitboard not in extra:
        extra.append(gitboard)
        _settings_path(home).parent.mkdir(parents=True, exist_ok=True)
        _settings_path(home).write_text(json.dumps(settings, indent=2) + "\n")
        lines.append(f"added {gitboard} to {_settings_path(home)}")
    return lines


def checks(home: Home) -> list[Check]:
    path = command_path(home)
    if not path.exists():
        command = Check(False, "walk: no .claude/commands/walk.md", "perch walk")
    elif path.read_text() != render(home):
        command = Check(
            False,
            "walk: .claude/commands/walk.md differs from perch's copy",
            f"delete {path}; the next perch walk reinstalls it",
        )
    else:
        command = Check(True, "walk: .claude/commands/walk.md")
    settings = _settings(home)
    if settings is None:
        return [
            command,
            Check(
                False,
                "walk: .claude/settings.json is not a settings object perch can edit",
                f"fix it, or add {home.gitboard_dir} to "
                "permissions.additionalDirectories by hand (perch walk leaves it alone)",
            ),
        ]
    listed = str(home.gitboard_dir) in settings.get("permissions", {}).get(
        "additionalDirectories", []
    )
    board = Check(
        listed,
        "walk: gitboard checkout in .claude/settings.json"
        if listed
        else "walk: gitboard checkout not in .claude/settings.json",
        f"perch walk, or add {home.gitboard_dir} to permissions.additionalDirectories",
    )
    return [command, board]
