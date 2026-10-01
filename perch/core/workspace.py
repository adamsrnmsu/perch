"""The perch workspace: a perch-home.yaml, and the projects beside it.

    ~/work/pi/
      perch-home.yaml     gitboard_dir: ~/Documents/git/pi_suite/remote-gitboard
      projects/apollo/    perch.yaml, history.jsonl, dumps/, weekly/
      budget/apollo/      the Budgie project (Budgie's own budget/ container)

A project is one funded piece of work: one GitLab project, one Budgie project,
one timesheet charge code. Found by walking up from the working directory,
else $PERCH_HOME -- the same walk-up Budgie and gitboard use.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from perch.core.config import CONFIG_NAME

HOME_NAME = "perch-home.yaml"
HOME_ENV = "PERCH_HOME"
PROJECTS_DIR = "projects"
BUDGET_DIR = "budget"  # Budgie's container: `budgie init NAME` writes budget/NAME
_HOME_KEYS = {"gitboard_dir"}
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")

SCAFFOLD = """\
budgie_project: ../../budget/{name}   # the directory holding budgie.yaml
board_dump: dumps/board.json         # written by `perch fetch`
gitlab_project:                      # the GitLab path, e.g. group/{name}
# estimates: estimates.csv           # optional; key,hours,low,high
people:                              # GitLab username -> name in people.csv
  # asmith: Alice
"""


class WorkspaceError(ValueError):
    """No workspace, no such project, or several projects and none named."""


def check_name(name: str) -> str:
    """A project name is one plain path segment, so it can't leave projects/."""
    if not _NAME.fullmatch(name):
        raise WorkspaceError(
            f"{name!r} is not a project name: letters, digits, - and _ only"
        )
    return name


@dataclass(frozen=True)
class Home:
    """A loaded perch-home.yaml. Both paths are absolute."""

    root: Path
    gitboard_dir: Path

    @property
    def projects_dir(self) -> Path:
        return self.root / PROJECTS_DIR

    def projects(self) -> list[str]:
        """Project names: folders under projects/ that hold a perch.yaml."""
        if not self.projects_dir.is_dir():
            return []
        return sorted(
            p.name for p in self.projects_dir.iterdir() if (p / CONFIG_NAME).is_file()
        )

    def config_path(self, name: str) -> Path:
        return self.projects_dir / name / CONFIG_NAME

    def weekly_path(self, name: str, week: str) -> Path:
        return self.projects_dir / name / "weekly" / f"{week}.md"

    def reports_dir(self, name: str) -> Path:
        return self.gitboard_dir / "reports" / name

    def budget_dir(self, name: str) -> Path:
        return self.root / BUDGET_DIR / name

    def select(self, name: str | None) -> str:
        """The named project, else the only one; several and none named is an error."""
        names = self.projects()
        if name is not None:
            if name not in names:
                known = ", ".join(names) or "none yet"
                raise WorkspaceError(
                    f"no project {name!r} in {self.projects_dir}. Known: {known}"
                )
            return name
        if not names:
            raise WorkspaceError("no projects yet. Run: perch init <name>")
        if len(names) > 1:
            raise WorkspaceError(
                f"several projects: {', '.join(names)}. Pass -p <name>."
            )
        return names[0]

    def scaffold(self, name: str) -> Path:
        """Write projects/NAME/perch.yaml pointing at budget/NAME. Never overwrites."""
        path = self.config_path(check_name(name))
        if path.exists():
            raise FileExistsError(f"{path} exists; edit it instead.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(SCAFFOLD.format(name=name))
        return path


def load_home(path: Path) -> Home:
    """Load and validate a perch-home.yaml; every error names the key."""
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise WorkspaceError(f"{path.name}: not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise WorkspaceError(f"{path.name} must be a mapping")
    unknown = set(data) - _HOME_KEYS
    if unknown:
        raise WorkspaceError(
            f"{path.name}: unknown keys {sorted(unknown)}; expected {sorted(_HOME_KEYS)}"
        )
    if not data.get("gitboard_dir"):
        raise WorkspaceError(f"{path.name}: `gitboard_dir` is required")
    root = path.resolve().parent
    gitboard = (root / Path(str(data["gitboard_dir"])).expanduser()).resolve()
    return Home(root=root, gitboard_dir=gitboard)


def find_home(start: Path, env: Mapping[str, str]) -> Home:
    """The first perch-home.yaml at or above ``start``, else $PERCH_HOME's."""
    here = start.resolve()
    for directory in (here, *here.parents):
        if (directory / HOME_NAME).is_file():
            return load_home(directory / HOME_NAME)
    if env.get(HOME_ENV):
        path = Path(env[HOME_ENV]).expanduser() / HOME_NAME
        if not path.is_file():
            raise WorkspaceError(
                f"${HOME_ENV} is {env[HOME_ENV]}, which has no {HOME_NAME}"
            )
        return load_home(path)
    raise WorkspaceError(
        f"no {HOME_NAME} here or above, and ${HOME_ENV} is not set. "
        "Run: perch init <name> --home <dir> --gitboard-dir <remote-gitboard>"
    )


def create_home(root: Path, gitboard_dir: Path) -> Home:
    """Make ``root`` a workspace. An existing perch-home.yaml is left alone."""
    root.mkdir(parents=True, exist_ok=True)
    path = root / HOME_NAME
    if not path.exists():
        path.write_text(yaml.safe_dump({"gitboard_dir": str(gitboard_dir)}))
    for sub in (PROJECTS_DIR, BUDGET_DIR):
        (root / sub).mkdir(exist_ok=True)
    return load_home(path)
