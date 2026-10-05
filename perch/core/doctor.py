"""perch doctor: one ok-or-FIX line for each thing that can be wrong before Monday."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from perch.core.config import load_config
from perch.core.workspace import HOME_NAME, Home

# (argv, cwd, extra env) -> did it exit 0
Runs = Callable[[Sequence[str], Path, Mapping[str, str]], bool]
_INSTALL = "make install (in the perch checkout)"
_CONFIG_ERRORS = (OSError, TypeError, ValueError, KeyError)


@dataclass(frozen=True)
class Check:
    ok: bool
    what: str
    fix: str = ""  # the command or edit that fixes it; only shown when not ok


def age(path: Path) -> str:
    if not path.exists():
        return "never"
    return (
        datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        .astimezone()
        .strftime("%Y-%m-%d %H:%M")
    )


def tool_checks(bin_dir: Path, home: Home, runs: Runs) -> list[Check]:
    from perch.core.steps import gitboard

    checks = []
    for tool in ("perch", "budgie"):
        ok = runs([str(bin_dir / tool), "--help"], home.root, {})
        checks.append(
            Check(ok, f"{tool} runs" if ok else f"{tool} does not run", _INSTALL)
        )
    if not home.gitboard_dir.is_dir():
        checks.append(
            Check(
                False,
                f"gitboard_dir {home.gitboard_dir} does not exist",
                f"fix gitboard_dir in {home.root / HOME_NAME}",
            )
        )
    else:
        step = gitboard(home, "gitboard", "--help")
        ok = runs(step.argv, step.cwd, step.env)
        checks.append(
            Check(ok, "gitboard runs" if ok else "gitboard does not run", _INSTALL)
        )
    return checks


def project_checks(home: Home, name: str) -> list[Check]:
    """perch.yaml loads, gitlab_project is set, and people: names exist in Budgie."""
    from perch.core.money import load_money

    path = home.config_path(name)
    try:
        config = load_config(path, require_dump=False)
    except _CONFIG_ERRORS as exc:
        return [Check(False, f"{name}: {exc}", f"edit {path}")]
    checks = [
        Check(True, f"{name}: perch.yaml, Budgie project {config.budgie_project}")
    ]
    checks.append(
        Check(
            bool(config.gitlab_project),
            f"{name}: gitlab_project {config.gitlab_project or 'not set'}",
            f"add gitlab_project: to {path}",
        )
    )
    if not config.people:
        checks.append(
            Check(
                False,
                f"{name}: people: is empty",
                f"map GitLab usernames to names in {path}",
            )
        )
        return checks
    try:
        known = set(load_money(config.budgie_project).hourly_cost)
    except _CONFIG_ERRORS as exc:
        checks.append(
            Check(
                False,
                f"{name}: Budgie cannot read {config.budgie_project}: {exc}",
                f"cd {config.budgie_project} && budgie status",
            )
        )
        return checks
    for user, person in sorted(config.people.items()):
        if person not in known:
            checks.append(
                Check(
                    False,
                    f"{name}: people: maps {user} to {person}, who is not in people.csv",
                    f"fix the name in {path}",
                )
            )
    return checks


def alert_checks(home: Home) -> list[Check]:
    """One check for the alert rules: none set is fine, a bad one names its key."""
    try:
        rules = home.alerts()
    except ValueError as exc:
        return [Check(False, str(exc), f"edit {home.root / HOME_NAME}")]
    return [Check(True, f"alerts: {len(rules)} rule{'s' * (len(rules) != 1)}")]


def freshness(home: Home, name: str) -> list[tuple[str, str]]:
    """When the dump, weekly.csv and history were last written ("never" if not)."""
    try:
        config = load_config(home.config_path(name), require_dump=False)
    except _CONFIG_ERRORS:
        return []  # project_checks already reported it
    return [
        ("board dump", age(config.board_dump)),
        ("weekly.csv", age(config.budgie_project / "weekly.csv")),
        ("history.jsonl", age(config.history)),
    ]
