"""perch.yaml: where the two tools' outputs live, and who is who."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONFIG_NAME = "perch.yaml"
BUDGIE_CONFIG = "budgie.yaml"
HISTORY_NAME = "history.jsonl"

_KEYS = {"budgie_project", "board_dump", "estimates", "gitlab_project", "people"}


@dataclass(frozen=True)
class Config:
    """A loaded perch.yaml. Every path is absolute."""

    root: Path
    budgie_project: Path
    board_dump: Path
    estimates: Path | None = None
    people: dict[str, str] = field(default_factory=dict)  # GitLab username -> name
    gitlab_project: str | None = None  # e.g. group/apollo; only `fetch` needs it

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
    return Config(
        root=root,
        budgie_project=project,
        board_dump=dump,
        estimates=estimates,
        people={str(user): str(name) for user, name in people.items()},
        gitlab_project=str(gitlab) if gitlab else None,
    )
