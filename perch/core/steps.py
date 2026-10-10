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
    spec = spec_path(home, project, config)
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
        "--log",
        str(stats_log(home, project)),
        *_spec_flag(spec),
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


def spec_path(home: Home, project: str, config: Config) -> Path:
    """The project's pulled board: projects/NAME/board/NAME.yaml (NAME is the folder)."""
    if not config.gitlab_project:
        raise WorkspaceError(
            f"{project}: perch.yaml has no gitlab_project; "
            f"add e.g. `gitlab_project: group/{project}`"
        )
    return home.board_dir(project) / f"{project}.yaml"


def snapshots(home: Home, project: str) -> Path:
    return home.board_dir(project) / "snapshots.jsonl"


def stats_log(home: Home, project: str) -> Path:
    return home.board_dir(project) / "stats.jsonl"


def _spec_flag(spec: Path) -> tuple[str, ...]:
    """--spec only once the board is pulled: gitboard reads it and fails if absent."""
    return ("--spec", str(spec)) if spec.is_file() else ()


def pull_fix(project: str, spec: Path) -> str:
    """What to run when the board has no .base, without losing staged edits.

    gitboard guards `pull --force` against unpushed edits only through the
    .base, so with none it would overwrite them silently.
    """
    where = "where GitLab is reachable"
    if not spec.exists():
        return f"run perch gb pull -p {project} {where}"
    return (
        f"push or copy it first: --force without a .base discards unpushed "
        f"edits; then perch gb pull -p {project} --force {where}"
    )


# Read only pulled files: what /walk may run, with no GitLab in reach.
GB_OFFLINE = ("show", "report", "stats", "graph", "estimate", "plan", "status")
# push and pull need GitLab: the lead runs them on a connected machine.
GB_SUBS = (*GB_OFFLINE, "push", "pull")
# Flags that move an offline sub's input: --from "" would read GitLab.
GB_TARGET_FLAGS = (
    "--from",
    "--against",
    "--history",
    "--since",
    "--all",
    "--out",
    "--db",
    "--log",
    "--spec",
    "--boards-dir",
)


def gb(
    home: Home, project: str, config: Config, sub: str, args: tuple[str, ...] = ()
) -> Step:
    """gitboard for one project, run from its checkout with the target filled in.

    The offline seven read the pulled spec, its .base, the board dump (the same
    data the money came from) and the snapshot log. `status` takes no target:
    it is every pulled board in the checkout, not only this project's. `sync`
    and `migrate` are not here on purpose.
    """
    if sub not in GB_SUBS:
        raise ValueError(f"{sub!r} is not one of {', '.join(GB_SUBS)}")
    if sub in GB_OFFLINE:
        for a in args:
            if a.split("=", 1)[0] in GB_TARGET_FLAGS:
                raise ValueError(f"gb {sub}: perch fills in {a.split('=')[0]}")
        if args and not args[0].startswith("-"):
            raise ValueError(f"gb {sub}: perch fills in the target, got {args[0]!r}")
    path = spec_path(home, project, config)
    spec, base = str(path), path.with_name(path.name + ".base")
    if sub == "plan" and not base.is_file():
        raise WorkspaceError(f"{project}: no {base}; {pull_fix(project, path)}")
    dump = str(config.board_dump)
    db = ("--db", str(snapshots(home, project)))
    boards = ("--boards-dir", str(home.board_dir(project)))
    target = {
        "show": ("--from", spec, "--markdown", *db, *boards),
        "graph": ("--from", spec),
        "plan": (spec, "--against", str(base)),
        "estimate": (spec, "--history", dump),
        "stats": ("--from", dump, "--log", str(stats_log(home, project)), *_spec_flag(path)),
        "report": ("--since", spec, *db),
        "status": (*db, *boards),
        "push": (spec, *db),
        "pull": (config.gitlab_project, "--out", spec, *db),
    }[sub]
    return gitboard(home, f"gb {sub}", sub, *target, *args)


def review(home: Home, project: str, config: Config, rows: list[dict]) -> Step:
    """Claude's /board on the pulled board, told what perch knows about the money.

    Runs in the perch checkout, where `walk.install(home, "board")` put /board.

    `rows` is history.jsonl: the team lines and the latest week's person
    lines, never the watch. /board stages edits in the project's board file, so no
    pull, no review.
    """
    from perch.core.trend import team_lines

    spec = spec_path(home, project, config)
    if not spec.is_file():
        raise WorkspaceError(
            f"{project}: no {spec}; pull it first: perch gb pull -p {project}"
        )
    people = people_lines(rows, config.people)
    context = "\n".join((REVIEW_RULES, *team_lines(rows), *people))
    return Step(
        "review",
        (
            "claude",
            "--append-system-prompt",
            context,
            f"/board {config.gitlab_project} {shlex.quote(str(spec))}",
        ),
        home.root,
    )


def walk(home: Home, project: str) -> Step:
    """Claude on /walk in the workspace, where .claude/commands/walk.md lives."""
    return Step("walk", ("claude", f"/walk {project}"), home.root)


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
    spec = spec_path(home, project, config)
    return gitboard(
        home, "digest", "digest", "--from", str(config.board_dump), "--out", str(out),
        "--log", str(stats_log(home, project)), *_spec_flag(spec),
        "--boards-dir", str(home.board_dir(project)),
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


# Budgie's read-only tables; its init/emails/forecast/status have their own steps.
BG_SUBS = ("monthly", "hours", "plan", "scenario", "assumptions", "calibrate", "doctor")


def bg(bin_dir: Path, config: Config, sub: str, args: tuple[str, ...] = ()) -> Step:
    """Budgie `SUB` for one project: it runs inside it, so --project is perch's."""
    if sub not in BG_SUBS:
        raise ValueError(f"{sub!r} is not one of {', '.join(BG_SUBS)}")
    if any(a.split("=", 1)[0] == "--project" for a in args):
        raise ValueError(f"bg {sub}: perch fills in --project")
    return _budgie(bin_dir, config, f"bg {sub}", sub, *args)


def hours(editor: str, config: Config) -> Step:
    """$EDITOR may carry flags (`code -w`), so it is split like a shell would."""
    path = config.budgie_project / "weekly.csv"
    return Step("hours", (*shlex.split(editor), str(path)), config.budgie_project)


def budgie_init(
    bin_dir: Path,
    home: Home,
    name: str,
    year: str | None = None,
    year_start: str | None = None,
) -> Step:
    """`budgie init --here` inside projects/NAME/budget writes the Budgie project.

    `year` / `year_start` pass straight through; Budgie validates them."""
    argv = [str(bin_dir / "budgie"), "init", "--here"]
    if year:
        argv += ["--year", year]
    if year_start:
        argv += ["--year-start", year_start]
    return Step("budgie init", tuple(argv), home.budget_dir(name), makes=(home.budget_dir(name),))


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
