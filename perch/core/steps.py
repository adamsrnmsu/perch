"""What each perch command runs, as values. Nothing here executes anything.

The CLI turns a Step into a subprocess. Keeping the commands as data is what
lets the tests check `monday` -- order, working directory, paths -- without
GitLab, Budgie or a terminal. perch runs the other tools as commands, never as
imports, so it still never calls GitLab and never redoes budget math.
"""

from __future__ import annotations

import shlex
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from perch.core.config import Config
from perch.core.workspace import Home, WorkspaceError


@dataclass(frozen=True)
class Step:
    name: str
    argv: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str] = field(default_factory=dict)  # added to os.environ
    makes: tuple[Path, ...] = ()  # directories to create before running

    def shown(self) -> str:
        env = "".join(f"{k}={shlex.quote(v)} " for k, v in self.env.items())
        return f"(cd {shlex.quote(str(self.cwd))} && {env}{shlex.join(self.argv)})"


class StepFailed(Exception):
    def __init__(self, step: Step, code: int):
        super().__init__(f"{step.name} exited {code}")
        self.step = step
        self.code = code


def iso_week(day: date) -> str:
    """`2026-W40`, the same as `date +%G-W%V`."""
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def gitboard(home: Home, name: str, *args: str, makes: tuple[Path, ...] = ()) -> Step:
    """gitboard runs from its checkout: it finds .env and gitboard.toml from there."""
    return Step(
        name,
        (str(home.gitboard_dir / ".venv/bin/python"), "-m", "gitboard.cli", *args),
        home.gitboard_dir,
        {"PYTHONPATH": str(home.gitboard_dir / "src")},
        makes,
    )


def fetch(home: Home, project: str, config: Config) -> Step:
    if not config.gitlab_project:
        raise WorkspaceError(
            f"{project}: perch.yaml has no gitlab_project; "
            f"add e.g. `gitlab_project: group/{project}`"
        )
    return gitboard(
        home,
        "fetch",
        "stats",
        config.gitlab_project,
        # 276 days of history (the summary stays gitboard's 7 days): the last
        # complete quarter and the one before it, for the WHOLE following
        # quarter, so `perch quarterly` can set them side by side.
        "--history-days",
        "276",
        "--dump",
        str(config.board_dump),
        makes=(config.board_dump.parent,),
    )


REVIEW_RULES = (
    "perch's budget picture for this board follows, from the last `perch board` "
    "run. First the team (stoplight · chance the board breaks the budget · "
    "budget · spent · headroom · hours left · cost to clear P10/P50/P90, then "
    "headroom by week). Use it to weigh priority and milestones, and say plainly "
    "when the open board does not fit the money left. Then each person in name "
    "order (name, GitLab username · open cards · hours to clear them · planned "
    "hours left · gap = left minus to clear). Use those only to say who has room "
    "for an unowned or stuck card, or whose load will not fit. Quote the "
    "figures; do not recompute them. Never rank, compare or judge people."
)


def _h(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "—"
    sign = ("+" if signed else "") if value >= 0 else "−"
    return f"{sign}{abs(value):,.0f}h"


def people_lines(rows: list[dict], people: Mapping[str, str]) -> list[str]:
    """The latest recorded week's person rows, in name order: load, not pay.

    Hours only, as `perch board` shows them: no rate, cost or accuracy.
    """
    person = [r for r in rows if r["kind"] == "person"]
    if not person:
        return []
    week = max(r["week"] for r in person)
    login = {name: user for user, name in people.items()}
    return [
        r["name"]
        + (f", @{login[r['name']]}" if r["name"] in login else "")
        + f" · open {r['open']} · to clear {_h(r['hours'])}"
        + f" · left {_h(r['left'])} · gap {_h(r['gap'], signed=True)}"
        for r in sorted(person, key=lambda r: r["name"])
        if r["week"] == week
    ]


def review(home: Home, project: str, config: Config, rows: list[dict]) -> Step:
    """Claude's /board on the pulled board, told what perch knows about the money.

    `rows` is history.jsonl: the team lines and the latest week's person
    lines, never the watch. /board stages edits in boards/<name>.yaml, so no
    pull, no review.
    """
    from perch.core.trend import team_lines

    if not config.gitlab_project:
        raise WorkspaceError(
            f"{project}: perch.yaml has no gitlab_project; "
            f"add e.g. `gitlab_project: group/{project}`"
        )
    spec = (
        home.gitboard_dir
        / "boards"
        / f"{config.gitlab_project.rsplit('/', 1)[-1]}.yaml"
    )
    if not spec.is_file():
        raise WorkspaceError(
            f"{project}: no {spec}; pull it first: (cd {shlex.quote(str(home.gitboard_dir))}"
            f" && gitboard pull {config.gitlab_project} --base)"
        )
    people = people_lines(rows, config.people)
    context = "\n".join((REVIEW_RULES, *team_lines(rows), *people))
    return Step(
        "review",
        (
            "claude",
            "--append-system-prompt",
            context,
            f"/board {config.gitlab_project}",
        ),
        home.gitboard_dir,
    )


def board(bin_dir: Path, home: Home, project: str) -> Step:
    config = str(home.config_path(project))
    return Step(
        "board", (str(bin_dir / "perch"), "board", "--config", config), home.root
    )


def weekly(bin_dir: Path, home: Home, project: str, week: str) -> Step:
    out = home.weekly_path(project, week)
    argv = (
        str(bin_dir / "perch"),
        "weekly",
        "--config",
        str(home.config_path(project)),
    )
    return Step("weekly", (*argv, "--out", str(out)), home.root, makes=(out.parent,))


def digest(home: Home, project: str, config: Config) -> Step:
    out = home.reports_dir(project)
    return gitboard(
        home, "digest", "digest", "--from", str(config.board_dump), "--out", str(out),
        makes=(out,),
    )  # fmt: skip


def _budgie(bin_dir: Path, config: Config, name: str, *args: str) -> Step:
    """Budgie runs inside its project, so it reads that project's files."""
    return Step(name, (str(bin_dir / "budgie"), *args), config.budgie_project)


def emails(bin_dir: Path, config: Config) -> Step:
    return _budgie(
        bin_dir, config, "emails", "emails", "--out-dir", "emails", "--no-preview"
    )


def forecast(bin_dir: Path, config: Config) -> Step:
    return _budgie(bin_dir, config, "forecast", "forecast")


def budget(bin_dir: Path, config: Config) -> Step:
    return _budgie(bin_dir, config, "budget", "status")


def hours(editor: str, config: Config) -> Step:
    """$EDITOR may carry flags (`code -w`), so it is split like a shell would."""
    path = config.budgie_project / "weekly.csv"
    return Step("hours", (*shlex.split(editor), str(path)), config.budgie_project)


def budgie_init(bin_dir: Path, home: Home, name: str) -> Step:
    """`budgie init NAME` from the workspace root writes budget/NAME."""
    return Step("budgie init", (str(bin_dir / "budgie"), "init", name), home.root)


MONDAY_STEPS = ("fetch", "board", "weekly", "digest", "emails")


def monday(
    bin_dir: Path,
    home: Home,
    project: str,
    config: Config,
    week: str,
    start: str | None = None,
) -> list[Step]:
    """Steps 1-5, in order, from `start` on. `hours` (step 0) is by hand."""
    if start is not None and start not in MONDAY_STEPS:
        raise ValueError(f"{start!r} is not a step: {', '.join(MONDAY_STEPS)}")
    run = [
        fetch(home, project, config),
        board(bin_dir, home, project),
        weekly(bin_dir, home, project, week),
        digest(home, project, config),
        emails(bin_dir, config),
    ]
    return run[MONDAY_STEPS.index(start) if start else 0 :]


def run_projects(
    names: Iterable[str], run_one: Callable[[str], None]
) -> list[tuple[str, Exception | None]]:
    """Run each project in turn; a failure is recorded and the next one still runs."""
    results: list[tuple[str, Exception | None]] = []
    for name in names:
        try:
            run_one(name)
        except (StepFailed, OSError, TypeError, ValueError) as exc:
            results.append((name, exc))
        else:
            results.append((name, None))
    return results
