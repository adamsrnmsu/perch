"""perch doctor: one ok-or-FIX line for each thing that can be wrong before Monday."""

from __future__ import annotations

import shlex
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from perch.core.config import load_config
from perch.core.workspace import CONFIG_FILE, PLACEHOLDER, Home

# (argv, cwd, extra env) -> did it exit 0
Runs = Callable[[Sequence[str], Path, Mapping[str, str]], bool]
READ_TOKEN = "GITLAB_READ_TOKEN"
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


OLD_VENVS = ("Documents/tools/perch", "Documents/tools/budgie")


def old_venv_checks(user_home: Path) -> list[Check]:
    """The venvs make install used before perch/.venv: named, never deleted."""
    return [
        Check(False, f"old install at {old} (perch/.venv replaces it)", f"rm -rf {old}")
        for old in (user_home / rel for rel in OLD_VENVS)
        if old.is_dir()
    ]


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
                f"gitboard {home.gitboard_dir} does not exist",
                "apps/remote-gitboard is missing: run make install in the perch checkout",
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
        return [Check(False, str(exc), f"edit {home.root / CONFIG_FILE}")]
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


OLD_HOME_FILE = "perch-home.yaml"


def _yaml_map(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _old_project(old: Path, gitboard: Path | None, name: str, home: Home) -> list[str]:
    """The lines that bring one project of an old workspace into the checkout."""
    q = shlex.quote
    folder = old / "projects" / name
    conf = _yaml_map(folder / "perch.yaml")
    new = home.projects_dir / name
    lines = [f"mkdir -p {q(str(new / 'board'))}"]

    def move(verb: str, src: Path, dest: Path, what: str) -> None:
        if not src.exists():
            return
        if dest.exists():
            lines.append(f"# {dest} already exists: {what} not moved, do it by hand")
        else:
            lines.append(f"{verb} {q(str(src))} {q(str(dest))}")

    if (new / "perch.yaml").exists():
        lines.append(f"# {new / 'perch.yaml'} already exists: {name} not moved, do it by hand")
    else:
        lines.append(f"mv {q(str(folder))}/* {q(str(new))}/")
    budgie = conf.get("budgie_project")
    budget = (folder / str(budgie)).resolve() if budgie else old / "budget" / name
    move("mv", budget, home.budget_dir(name), "the Budgie project")
    if gitboard is not None:
        seg = str(conf.get("gitlab_project") or name).rsplit("/", 1)[-1]
        for suffix in ("", ".base", ".base.old"):
            move(
                "mv",
                gitboard / "boards" / f"{seg}.yaml{suffix}",
                home.board_dir(name) / f"{name}.yaml{suffix}",
                "the board file",
            )
        move("cp", gitboard / "snapshots.jsonl", home.board_dir(name) / "snapshots.jsonl", "snapshots")
        move("cp", gitboard / "reports" / "stats.jsonl", home.board_dir(name) / "stats.jsonl", "stats.jsonl")
    lines.append(
        f"# then edit {new / 'perch.yaml'}: budgie_project: budget; "
        "board_dump: board/dump.json; estimates: the file's new path"
    )
    return lines


def old_layout_checks(start: Path, home: Home) -> list[Check]:
    """A perch-home.yaml at or above ``start`` is the old workspace: print its moves.

    Detection only, the one place a walk-up remains. Nothing is moved.
    """
    here = start.resolve()
    old = next((d for d in (here, *here.parents) if (d / OLD_HOME_FILE).is_file()), None)
    if old is None:
        return []
    what = f"old workspace at {old}"
    if old == home.root:
        return [Check(False, what, f"delete {old / OLD_HOME_FILE}: the checkout is home now")]
    gb = _yaml_map(old / OLD_HOME_FILE).get("gitboard_dir")
    gitboard = (old / Path(str(gb)).expanduser()).resolve() if gb else None
    projects = old / "projects"
    names = sorted(p.name for p in projects.iterdir() if p.is_dir()) if projects.is_dir() else []
    lines = [line for name in names for line in _old_project(old, gitboard, name, home)]
    return [Check(False, what, "\n".join(lines) or f"nothing under {projects} to move")]


def read_env(path: Path) -> dict[str, str]:
    """KEY=value lines the way python-dotenv reads them; {} for no file.

    Enough of dotenv for doctor to see whether a key is set: comments,
    `export `, quotes and a trailing ` # note`. Values are never printed.
    """
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return {}
    out = {}
    for line in lines:
        line = line.strip().removeprefix("export ").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if value[:1] in ("'", '"') and value[0] in value[1:]:
            value = value[1 : value.index(value[0], 1)]
        else:
            value = value.split(" #", 1)[0].strip()
        if value:
            out[key] = value
    return out


def env_checks(home: Home, name: str, environ: Mapping[str, str]) -> list[Check]:
    """Where this project's read token comes from; never what it is.

    gitboard's order: an exported variable, then the nearest .env walking up
    from projects/NAME (the project's, then the checkout's).
    """
    own = home.env_path(name)
    rel = own.relative_to(home.root)
    if environ.get(READ_TOKEN):
        return [Check(True, f"{name}: read token from the environment")]
    for path, label in ((own, str(rel)), (home.root / ".env", "checkout .env")):
        if path.exists():  # gitboard reads only the first .env it finds
            value = read_env(path).get(READ_TOKEN)
            if value and value != PLACEHOLDER:
                return [Check(True, f"{name}: read token in {label}")]
            break
    return [
        Check(
            False,
            f"{name}: no GitLab read token",
            f"set GITLAB_READ_TOKEN (read_api) in {own} "
            "(or export it, or use the gitlab-read-token keychain item)",
        )
    ]
