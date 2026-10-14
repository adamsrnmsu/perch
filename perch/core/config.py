"""perch.yaml: where the two tools' outputs live, and who is who."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_NAME = "perch.yaml"
BUDGIE_CONFIG = "budgie.yaml"
HISTORY_NAME = "history.jsonl"
BOARD_DIR = "board"
PEOPLE_CSV = "people.csv"

_KEYS = {"budgie_project", "board_dump", "estimates", "gitlab_project", "people"}


@lru_cache(maxsize=64)
def _yaml_people(path: Path, mtime: float) -> tuple[tuple[str, str], ...]:
    """(display name, username) pairs from a board YAML's people:, cached on mtime.

    ponytail: parses the whole board file once per change; read only the
    people: block if boards grow large enough for that to show.
    """
    try:
        data = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError):
        return ()
    people = data.get("people") if isinstance(data, dict) else None
    if not isinstance(people, dict):
        return ()
    return tuple((str(name), str(user)) for name, user in people.items())


def _board_people(root: Path) -> tuple[tuple[str, str], ...]:
    """The pulled board's people: (projects/NAME/board/NAME.yaml), or ()."""
    path = root / BOARD_DIR / f"{root.name}.yaml"
    try:
        return _yaml_people(path, path.stat().st_mtime)
    except OSError:
        return ()


def _budgie_names(project: Path) -> set[str]:
    """The names in the Budgie project's people.csv, read with Budgie's own reader."""
    import csv

    from budgie.core.csvio import read_rows

    try:
        return {
            row["name"] for row in read_rows(project / PEOPLE_CSV, required={"name"})
        }
    except (OSError, ValueError, csv.Error):
        return set()


@dataclass(frozen=True)
class Config:
    """A loaded perch.yaml. Every path is absolute."""

    root: Path
    budgie_project: Path
    board_dump: Path
    estimates: Path | None = None
    people: dict[str, str] = field(default_factory=dict)  # GitLab username -> name
    gitlab_project: str | None = None  # e.g. group/apollo; only `fetch` needs it
    unmatched: tuple[str, ...] = ()  # board-YAML members not in people.csv

    @property
    def history(self) -> Path:
        return self.root / HISTORY_NAME


def load_config(path: str | Path, require_dump: bool = True) -> Config:
    """Load and validate a perch.yaml. Paths resolve against its directory.

    ``require_dump=False`` is for the steps that run before the first fetch
    (doctor, fetch itself): the dump's path is still required, its file is not.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"{path}: no such file. perch reads a {CONFIG_NAME}.")
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"{path.name}: not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise TypeError(f"{path.name} must be a mapping, got {type(data).__name__}")
    unknown = set(data) - _KEYS
    if unknown:
        raise ValueError(
            f"{path.name}: unknown keys {sorted(unknown)}; expected {sorted(_KEYS)}"
        )
    root = path.resolve().parent

    def located(key: str) -> Path:
        if not data.get(key):
            raise ValueError(f"{path.name}: `{key}` is required")
        return (root / str(data[key])).resolve()

    project = located("budgie_project")
    if not (project / BUDGIE_CONFIG).is_file():
        raise FileNotFoundError(
            f"{path.name}: `budgie_project` is {project}, which has no {BUDGIE_CONFIG}"
        )
    dump = located("board_dump")
    if require_dump and not dump.is_file():
        raise FileNotFoundError(
            f"{path.name}: `board_dump` is {dump}, which does not exist. "
            "Write one with `gitboard stats --dump FILE`."
        )
    estimates = located("estimates") if data.get("estimates") else None
    if estimates is not None and not estimates.is_file():
        raise FileNotFoundError(
            f"{path.name}: `estimates` is {estimates}, which does not exist"
        )
    people = data.get("people") or {}
    if not isinstance(people, dict):
        raise TypeError(f"{path.name}: `people` must map GitLab usernames to names")
    gitlab = data.get("gitlab_project")
    explicit = {str(user): str(name) for user, name in people.items()}
    members = [(n, u) for n, u in _board_people(root) if u not in explicit]
    known = _budgie_names(project) if members else set()
    matched = {u: n for n, u in members if n in known}
    unmatched = tuple(sorted(n for n, u in members if n not in known))
    return Config(
        root=root,
        budgie_project=project,
        board_dump=dump,
        estimates=estimates,
        people={**matched, **explicit},
        gitlab_project=str(gitlab) if gitlab else None,
        unmatched=unmatched,
    )
