"""The perch workspace: the perch checkout is home, and the projects live in it.

    perch/                      the checkout
      config.yaml               optional, gitignored: lead: NAME and alerts:
      apps/budgie/              clones (gitignored), put there by make install
      apps/remote-gitboard/
      projects/apollo/          perch.yaml, history.jsonl, watch/, monday.json
        board/                  the pulled board, its .base, snapshots, stats, dump
        budget/                 the Budgie project (budgie.yaml directly inside)
        reports/                digests from gitboard digest
        listen/                 meeting transcripts

A project is one funded piece of work: one GitLab project, one Budgie project,
one timesheet charge code. Home is where perch is installed from: no file to
find, no environment variable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

import perch
from perch.core.config import CONFIG_NAME

CONFIG_FILE = "config.yaml"
PROJECTS_DIR = "projects"
_HOME_KEYS = {"lead", "alerts"}
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
NOT_A_CHECKOUT = (
    "perch is not running from a checkout: run make install in your perch clone"
)

SCAFFOLD = """\
budgie_project: budget               # the directory holding budgie.yaml
board_dump: board/dump.json          # written by `perch fetch`
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
    """The perch checkout and what config.yaml says. ``root`` is absolute."""

    root: Path
    lead: str | None = None
    alerts_raw: object = field(default=None, compare=False)  # unvalidated `alerts:`

    def alerts(self):
        """The validated alert rules; ValueError naming the key when malformed."""
        from perch.core import alerts

        return alerts.parse(self.alerts_raw, self.projects(), CONFIG_FILE)

    @property
    def gitboard_dir(self) -> Path:
        return self.root / "apps" / "remote-gitboard"

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

    def watch_path(self, name: str, week: str) -> Path:
        """The private watch: under the project, never beside the drafts."""
        return self.projects_dir / name / "watch" / f"{week}.md"

    def reports_dir(self, name: str) -> Path:
        return self.projects_dir / name / "reports"

    def budget_dir(self, name: str) -> Path:
        return self.projects_dir / name / "budget"

    def select(self, name: str | None, here: Path | None = None) -> str:
        """The named project, else the one ``here`` is inside, else the only one.

        Several projects, none named and ``here`` in none of them is an error.
        """
        names = self.projects()
        if name is not None:
            if name not in names:
                known = ", ".join(names) or "none yet"
                raise WorkspaceError(
                    f"no project {name!r} in {self.projects_dir}. Known: {known}"
                )
            return name
        if here is not None:
            try:
                inside = here.resolve().relative_to(self.projects_dir).parts
            except ValueError:
                inside = ()
            if inside and inside[0] in names:
                return inside[0]
        if not names:
            raise WorkspaceError("no projects yet. Run: perch init <name>")
        if len(names) > 1:
            raise WorkspaceError(
                f"several projects: {', '.join(names)}. Pass -p <name>."
            )
        return names[0]

    def scaffold(self, name: str) -> Path:
        """Write projects/NAME/perch.yaml pointing at its budget/. Never overwrites."""
        path = self.config_path(check_name(name))
        if path.exists():
            raise FileExistsError(f"{path} exists; edit it instead.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(SCAFFOLD.format(name=name))
        return path


def checkout_home(root: Path | None = None) -> Home:
    """The perch checkout as a Home; ``root`` is injected by tests only."""
    root = root or Path(perch.__file__).resolve().parents[1]
    if not (root / "pyproject.toml").is_file() or not (root / "apps").is_dir():
        raise WorkspaceError(NOT_A_CHECKOUT)
    path = root / CONFIG_FILE
    if not path.is_file():
        return Home(root=root)
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise WorkspaceError(f"{CONFIG_FILE}: not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise WorkspaceError(f"{CONFIG_FILE} must be a mapping")
    unknown = set(data) - _HOME_KEYS
    if unknown:
        raise WorkspaceError(
            f"{CONFIG_FILE}: unknown keys {sorted(unknown)}; expected {sorted(_HOME_KEYS)}"
        )
    lead = data.get("lead")
    if "lead" in data and (not isinstance(lead, str) or not lead.strip()):
        raise WorkspaceError(f"{CONFIG_FILE}: `lead` must be a name (text)")
    return Home(root=root, lead=lead, alerts_raw=data.get("alerts"))
